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
| `web/admin/files/files.py` | 补齐历史上遗漏的 `/files/get_speed` 路由（支持 GET/POST，受登录态保护），打通前端读内存进度的完整链路。 |
| `web/static/app/public.js` | 优化 `getSpeed()`：增加 DOM 存在性双重校验（弹窗关闭后立即终止递归，杜绝僵尸轮询）；兼容包装与扁平响应结构；增加 `.fail()` 容错降频。 |

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

---
---

# task.md —— 第 1 层「安全 / 可靠性 / 性能」收口记录

> 来源：本轮全仓安全·可靠性·性能复审（对照《参考/优化260910.md》剔除已落地项后的**剩余问题**）。
> 纪律：每修完一类代码即跑 `python testsuite/run_all.py` 全量门禁，不通过则继续修正，直至全绿。
> 基线：154 模块 / 1074 用例 / 4 个既有隔离项，全部通过。

## A. 安全性 — 注入收口（P0）

- [x] A1 插件 zip 安装接口命令注入：`web/utils/plugin.py:inputZipApi()` 的 `plugin_name`/`tmp_path` 未过滤即拼进 `execShell`
- [x] A2 webssh 插件 `eval("classApp."+func+"()")` 任意代码执行：`plugins/webssh/index.py:__main__`
- [x] A3 Docker 插件 `eval(ports)`：`plugins/docker/index.py:852`
- [x] A4 插件 `/run` 路径穿越执行任意 `.py`：`web/utils/plugin.py:run()` 未校验 `name`/`script`
- [x] A5 站点路径未加引号拼接进 shell：`web/utils/site.py` 多处 `chattr ±i " + path`

> A 类验证：新增 `testsuite/test_p3_injection_hardening.py`（9 用例，含恶意输入拒绝 + 源码危险写法断言）；
> `python testsuite/run_all.py` → **155 模块 / 1083 用例全部通过**。

## B. 安全性 — 凭据处理（P0）

- [x] B1 快捷登录绕过限流/会话固定/仅支持 MD5：`web/admin/dashboard/dashboard.py:admin_safe_path()`
- [x] B2 关联面板密码明文入库并明文上 URL：`web/admin/setting/panel_bookmark.py`

> B 类验证：新增 `testsuite/test_p3_credential_hardening.py`（9 用例）。
> B1：快捷登录改用 `_is_banned/_register_login_failure/_reset_login_failure/_password_matches`，`session.clear()`，双向时间窗。
> B2：密码落库 `enDoubleCrypt`；`get_panel_list` 不再回传 `password`；新增 `/setting/get_panel_login` 服务端现签；前端去除 `data-pw`。

## C. 安全性 — SSRF 与传输（P1）

- [x] C1 计划任务下载 SSRF 可被 302 绕过 + `socket.setdefaulttimeout` 全局副作用：`panel_task.py:downloadFile()`
- [x] C2 出口 HTTPS 不校验证书，改为「先验证、失败再降级」双重策略：`web/core/yf.py:_insecure_ssl_context()`

> C 类验证：新增 `testsuite/test_p3_ssrf_and_transport.py`（6 用例，含重定向处理器运行时拒绝 169.254/127.0.0.1）。

## D. 可靠性（P1）

- [x] D1 重型任务无超时，卡死任务永久堵队列：`panel_task.py:execShell()` / `runPanelTask()`
- [x] D2 插件 `uninstall` 同步执行且无超时，占死 gunicorn 线程：`web/utils/plugin.py:uninstall()`
- [x] D3 `plugin.run()` 固定 30s 超时误杀正常启停：`web/utils/plugin.py:run()`
- [x] D4 内存态进度强依赖 `workers=1`，缺少启动告警：`web/setting.py`
- [x] D5 `_table_fields_cache` 永不失效，`ALTER TABLE` 后字段错位：`web/core/db.py`

> D 类验证：新增 `testsuite/test_p3_reliability_timeouts.py`（7 用例，含实时验证 `execShell` 2s 杀掉 60s 睡眠进程）。
> 同步更新了旧用例 `test_p1_reliability_and_perf.py` 对调用签名的字面断言（追加 timeout 参数，语义不变）。

## E. 执行性能（P2）

- [x] E1 `RUN_CACHE` 无上限且 key 含用户可控 `args`，可致内存单调增长：`web/admin/plugins/__init__.py`
- [x] E2 `run_batch` 硬编码 10 并发子进程，低配打满单核：`web/admin/plugins/__init__.py`
- [x] E3 gunicorn `threads=4` 硬编码 + 缺少 `MAX_CONTENT_LENGTH`：`web/setting.py` / `web/admin/__init__.py`

> E 类验证：新增 `testsuite/test_p3_perf_hardening.py`（6 用例，含 RUN_CACHE TTL/容量上限行为断言）。

## F. 经复核「已实现 / 接受现状」

- [x] F1 语言包按主菜单分片懒加载（P-3）——**已实现**：`web/core/i18n.py` `_MENU_NAMES` + `template.<menu>.json`
- [x] F2 出口 HTTPS 证书校验（C2）改为验证优先 + 降级兜底后即闭环
- [x] F3 `os.system` 收口、`flock`、SSRF urlguard、`FileSystemCache`、资源分档自适应等（《优化260910.md》S-1/R-2/S-3/P-1/H-*）——**已实现**，本轮不重复

---

## 验证记录

| 阶段 | 命令 | 结果 |
|------|------|------|
| 基线 | `python testsuite/run_all.py` | 154 模块 / 1074 用例，全绿 |
| A 类后 | 同上 | **155 模块 / 1083 用例，全绿** |
| B 类后 | 同上 | **156 模块 / 1092 用例，全绿** |
| C 类后 | 同上 | **157 模块 / 1098 用例，全绿** |
| D 类后 | 同上 | **158 模块 / 1105 用例，全绿**（含修正 1 处旧断言） |
| E 类后 | 同上 | **159 模块 / 1111 用例，全绿**（4 个隔离项为改动前既有语言包问题，未新增） |

新增回归用例（均纳入门禁）：
- `testsuite/test_p3_injection_hardening.py`（9）
- `testsuite/test_p3_credential_hardening.py`（9）
- `testsuite/test_p3_ssrf_and_transport.py`（6）
- `testsuite/test_p3_reliability_timeouts.py`（7）
- `testsuite/test_p3_perf_hardening.py`（6）

运行时/构建校验：所有改动文件 `py_compile` 通过；`web/static/app/public.js` `node --check` 通过；
全部保持 UTF-8 无 BOM + LF。

