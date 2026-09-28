# task.md —— 第 0 层「轮询治理」优化记录

> 范围：仅落地第 0 层（必做、零风险）的轮询/空转/磁盘 I/O 治理，**不引入 SSE、不改 SocketIO、不切 gevent**。
> 交付状态：已完成，`testsuite/run_all.py` 全量门禁通过（154 模块 / 1074 用例，4 个隔离项为改动前既有）。

---

## 一、修改内容

### 1. 去重 `/system/network`
| 文件 | 改动 |
|------|------|
| `web/static/app/index.js` | 删除 251 行遗留死代码：`getNet()` 与 `netImg()`（`netImg()` 从未被调用，其内部 `setInterval(getNet, 3000)` 构成第二份网络统计/图表实现，且读取的是响应中不存在的顶层字段，会用 `undefined` 覆盖正确数值）。首页只保留唯一轮询 `index.getData()`。 |
| `web/static/app/index.js` | 将原仅存于 `getNet` 的有效逻辑合并进 `index.getData()`：任务角标 `.task`，并新增 `window.__lastNetworkStat` 共享缓存（含时间戳）。 |
| `web/static/app/public.js` | 消息盒子系统信息拆分为 `renderMsgBoxSysInfo()`；`updateSysInfo()` 在首页直接复用 `window.__lastNetworkStat`（<6s），不再重复请求。 |

### 2. 自适应间隔（可见性感知 + 空闲退避）
| 文件 / 位置 | 改动 |
|------|------|
| `web/static/app/public.js` | 新增公共助手 `yfVisible()`、`yfPacer(maxIdle)`；`getTaskCount` 注释同步更新。 |
| `public.js` `getReloads`（任务进度） | 引入 `yfPacer(4)`：有任务 2s 刷新；无任务进入退避（第 5 拍才再请求，≈10s）；后台暂停。保留 `clearInterval(speed)` 语义。 |
| `public.js` `getSpeed`（上传/下载进度） | 可见 1s / 后台 3s。 |
| `public.js` `updateSysInfo`（消息盒子，3s） | 后台标签页暂停。 |
| `index.js` `index.task`（首页，3s） | 后台标签页暂停。 |
| `crontab.js` 计划任务日志（5s） | 后台标签页暂停。 |
| `files.js` `reloadFiles`（3s） | 后台暂停；并修复重复调用导致的定时器叠加泄漏（持有 id、先清后建）。 |
| `soft.js` 软件列表（8s/30s） | 后台标签页降频至 60s。 |

### 3. 进度改内存态
| 文件 | 改动 |
|------|------|
| `web/core/yf.py` | `writeSpeed()` 不再落盘 `data/panel_speed.pl`，改为模块级 `_SPEED_STATE` + `threading.Lock`；`getSpeed()` 返回副本。顺带修正 `total=0` 的除零风险。 |
| `web/core/yf.py` | 顶部补充 `import threading`（原文件仅在 2300+ 行才导入，内存态锁需提前可用），并移除后置的重复导入。 |

### 4. `panel_task.py` 空转改事件驱动
| 位置 | 改动 |
|------|------|
| 顶部 | 新增 `_TASK_WAKE_EVENT` / `_WATCHDOG_WAKE_EVENT`、`setupWakeSignal()`（注册 SIGUSR1）、`writePanelTaskPidFile()` / `removePanelTaskPidFile()`。 |
| `TaskScheduler.run` | 去掉固定 2s 上限，改为精确等到下一任务到期（上限 30s），并由 `_WATCHDOG_WAKE_EVENT` 支持信号即时唤醒。 |
| `heavy_task_worker` | 去掉固定 `event.wait(3.0)`，改为等待 `_TASK_WAKE_EVENT`：有任务信号即时处理，空闲 60s 兜底；无信号能力时退回 3s。 |
| `run()` | 启动时注册信号 + 写 PID 文件；文件型检测间隔按信号能力取 10s/3s；退出时清理 PID 文件。 |
| `web/core/yf.py` | 新增 `getPanelTaskPidFile()`、`wakePanelTask()`；`triggerTask()`、`restartPanel()` 在写触发文件后立即唤醒后台进程。 |

**安全设计**：`wakePanelTask()` 仅在存在 `/proc` 的 Linux 下，且 `/proc/<pid>/cmdline` 校验确含 `panel_task.py` 时才发送 SIGUSR1，杜绝 PID 复用误伤；非 Linux/无 SIGUSR1 环境自动退化为轮询，功能不回退。

---

## 二、提升效果（单标签页估算）

| 场景 | 修改前 | 修改后 | 效果 |
|------|--------|--------|------|
| 首页（可见） | 1× `/system/network` 轮询 | 同左，但消息盒子不再重复请求 | 同时开消息盒子时 **40 → 20 次/分（-50%）** |
| 首页（后台标签页） | 20 次/分 | 0 | **-100%** |
| 任务进度（无任务、空闲） | 30 次/分（2s） | ≈6 次/分（≈10s） | **-80%** |
| 任务进度（后台） | 30 次/分 | 0 | **-100%** |
| 上传/下载进度（后台） | 60 次/分（1s） | 20 次/分（3s） | **-67%** |
| 计划任务日志（后台） | 12 次/分（5s） | 0 | **-100%** |
| 文件列表重载 | 3s，且重复调用会叠加定时器 | 3s 单定时器 + 后台暂停 | 消除叠加泄漏 |
| 软件列表（后台） | 8s/30s | 60s | 后台进一步降频 |
| `panel_task` 后台唤醒 | 看门狗 30 次/分 + 重型线程 20 次/分 ≈ **50 次/分** | 看门狗 ≈6 次/分 + 重型线程事件驱动 ≈1 次/分 ≈ **7 次/分** | **约 -85%** |
| 文件批量操作进度落盘 | 节流后仍 ≤1 次/秒的小文件写 | 0（纯内存） | 消除磁盘写放大 |
| 任务触发响应 | 最坏等待 2~3s（轮询间隔） | 信号唤醒，毫秒级 | 触发更跟手 |

**一句话**：在完全不改传输协议、不增加依赖的前提下，把空闲/后台状态下的高频空转与重复请求收敛掉，前台交互响应不变甚至更快，后台资源占用显著下降。

---

## 三、验证

- `python testsuite/run_all.py`：**154 模块 / 1074 用例全部通过**（4 个隔离项为改动前既有的语言包问题）。
- `node --check` 全部 `web/static/app/*.js` 通过；所有改动文件保持 UTF-8 无 BOM + LF。
- 运行时校验：
  - `writeSpeed`/`getSpeed` 内存态读写、副本隔离、除零安全、确认不再生成 `panel_speed.pl`；
  - `wakePanelTask` 的正常发送、`cmdline` 不符拒绝、PID 文件缺失拒绝三条路径；
  - `panel_task` 信号初始化（本机无 SIGUSR1 → 正确降级）、PID 文件写入/清理、`TaskScheduler` 构造。

---

## 四、兼容性与回退

- **无新增依赖**，无数据库结构变更，无接口签名变更。
- 跨进程唤醒仅依赖 Linux `SIGUSR1` + `/proc`；Windows/macOS 或 `/proc` 不可用时自动退化为原轮询节奏。
- 回退粒度小：前端为纯 JS 行为调整，后端为局部函数替换，均可单独还原而不影响其余功能。
