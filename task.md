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

---
---

# 第 2 层「i18n 交付收口」—— 商业发布阻断项修复（task list）

> 来源：i18n 分支可发布性审计（本轮）。P0-1「caddy / acme 插件下线」经产品确认系**主动移除**（存在严重安全问题），不在本清单内。
> 纪律：每完成一项即跑对应验证，通过后在本文件打勾（`[x]`）。全部完成后跑全量门禁。
> 基线：`python testsuite/run_all.py` 161 模块 / 1131 用例全绿；`scripts/verify_i18n.py` 10 项全通过。
> 实测缺陷基线：`test/i18n_user_visible_damage.py` → en/de/fr/it **663 条用户可见损坏**（EMPTY 113×4、GLUE en83/de119/fr5/it4）。

## 第 1 步：EMPTY —— 键在语言包里查不到（452 条 / 113 键）

根因：i18n 分支重写 `lan.js` 时**丢掉了 master 旧包里的键**，而调用点已改为 `t('sec.key')`，
于是查表落空 → 外文界面回落硬编码中文；无兜底的调用点（如 `t('site.default_doc')`）直接渲染**空白**。

- [x] 1.1 恢复 master 旧包被丢弃、且仍被调用的 **37 个键**（zh-CN 原文取自 master，补 zh-TW/en/fr/de/it）
- [x] 1.2 补齐 **69 个**「调用点已引用但六语言全缺」的键（zh-CN 取自调用点兜底与上下文）
- [x] 1.3 清理 4 处 dead fallback（`|| t('template.xxx')`，`public.*` 同义键已存在）与 3 个非翻译键误报（`OK`/`ok`/`size`）
- [x] 1.4 由 `lan.js` 单源重新派生 72 个 `.json` 载体，并跑 `test_lang_carrier_derivation`（28 项）
- [x] 1.5 复测 `test/i18n_user_visible_damage.py`：EMPTY = 0

## 第 2 步：GLUE —— 逐词机翻拼接乱码（211 条）

- [x] 2.1 重译 en 83 / de 119 / fr 5 / it 4 处乱码（如 `If forgotten, password,can be SSHpassbscommand to closeBasicAuthverify`）
- [x] 2.2 重新派生载体 + 跑护栏（28 项）
- [x] 2.3 复测 GLUE = 0（其中 1 条 `crontab.import_system_scheduled_tasks[fr]` 为 `\n` 转义序列引起的**假阳性**，已修正判定器）

## 第 3 步：英文「小写连写」机翻异味

- [x] 3.1 修 **63 个**被前端引用的 en 值（`clearlog`/`releasememory`/`setsuccessful`/`forcedelete`/`modifypassword`…）
- [x] 3.2 一并扫掉其余未被引用的同类 en 值（按值去重 82 个，共 137 处；另修「语义键」残留 GLUE 65 处）
- [x] 3.3 重新派生载体 + 跑护栏；引用键审计 = 0、语义键残留 GLUE = 0
  > 副产品：判定器补了三处假阳性修正（`\n` 转义序列、LEGIT 前缀匹配、新增 pgAdmin/pyOpenSSL/getBakPost 等组件名与 JS 函数名）。

- [x] 3.4 **精简复核（用户新增要求）**：槽位审计从 15 处超宽 → **0**；另按「最短可懂」重写了本轮新增的长句（en 31 / de 41 / fr 16 / it 16 处）。
  > 同步修正 1 条把缺陷值写进白名单的旧用例（`test_site_i18n_concise.py` 的 `default_category` 允许列表含 `defaultcategory`）。

## 第 4 步：把上述红线变成可执行门禁（防回归）

- [x] 4.1 `scripts/verify_i18n.py` 新增 `user-visible-damage` 检查（自包含、仅标准库：内嵌 lan.js 解析 + 引用扫描 + EMPTY/UNKNOWN/ZH_LEAK/GLUE/LOW 判定）
- [x] 4.2 补内嵌自证夹具（五类各一例 + 「合法译文不得误报」+ 真实语言包注入变异自证）
- [x] 4.3 `.github/workflows/i18n-check.yml` 覆盖新检查；同步 `run_all.py` / `plugins_check.md` 的项数（9→11）

## 第 5 步：P0-3 版本号与静态缓存（否则用户收不到本次修复）

- [x] 5.1 `web/version.py` `APP_SMALL_VERSION` 18 → 19（内置更新器依赖它与 GitHub tag 比较）
- [x] 5.2 `layout.html` / `login.html` 的 `lan.js`、`i18n.js`、`i18n_tpl.js` 接入 `&t={{ asset_v(...) }}` 内容指纹（当前只有 `?v=1.1.18`，而 `/static/` 是 7 天 `immutable`）
- [x] 5.3 新增回归用例锁定「语言包/核心 i18n 脚本必须带内容指纹」（`test_static_asset_cache_busting` 新增 test_06，且覆盖全部模板）

## 第 6 步：P1 打包与仓库洁癖（商业产品形象）

- [x] 6.1 `scripts/plugin_compress.sh` 排除 `*.i18n.bak` 与 `__pycache__`（否则 33 个备份、1.6MB 随插件包下发）
- [x] 6.2 `.gitattributes` 增加 `export-ignore`：`*.i18n.bak`、`*.bak`、`web/static/app/*.bak`、`plugins/*.md`
- [x] 6.3 删除死文件 `web/static/language/lang.json`（全仓零引用）；`list.json` / `zh-cn.js` 经核实为 master 遗留且全仓零引用，为避免影响外部直链（`/static/language/list.json`）本次保留不动
- [x] 6.4 27 个插件「死键」归因：**0 个真孤儿**，全部是「键字符串是插件源码里更长中文字面量的子串」的预留前缀键（含 3 条弱归因：clean/服务 命中文档路径、data_query/容器 命中代码注释、task_manager/发送·接收 命中说明文案），保留不动

## 第 7 步：总验证与收尾

- [x] 7.1 `python scripts/verify_i18n.py --verbose` 全绿（**11 项检查**，含新增第 11 项）
- [x] 7.2 `python testsuite/run_all.py` 全绿：**165 模块 / 1157 用例 / 0 隔离项**
- [x] 7.3 `test/i18n_user_visible_damage.py` → **0 条**；`test/audit_panel_slots.py` → **0 处超宽**；
      `export_lang_carriers.py`（干跑）→ 0 变更（载体与 `lan.js` 同源）；`verify_menu_merge.py` → PASS
- [x] 7.4 清理本轮 29 个临时脚本 + 23 个中间产物；本文档回填验证记录

## 验证记录

| 阶段 | 命令 | 结果 |
|------|------|------|
| 基线 | `test/i18n_user_visible_damage.py` | en/de/fr/it **663 条**用户可见损坏（EMPTY 452 / GLUE 211） |
| 第 1 步后 | 同上 | EMPTY **452 → 0**（GLUE 剩 211） |
| 第 2 步后 | 同上 | **0 条**（含 1 条 `\n` 转义引起的假阳性修正） |
| 第 3 步后 | 语义键残留 GLUE | **76 → 0**；小写连写：引用键 63 + 未引用 137 处按值扫净 |
| 第 3.4 步后 | `test/audit_panel_slots.py` | 新增键带来的 **15 处超宽 → 0** |
| 第 4 步后 | `scripts/verify_i18n.py` | 9 → **11 项**（`user-visible-damage` + 自证夹具 + 真实数据路径变异自证） |
| 第 5 步后 | `test_static_asset_cache_busting` | 5 → **6 项**（新增 test_06 全模板指纹护栏） |
| 第 6 步后 | `git status` | `.gitattributes`/`plugin_compress.sh` 排除开发产物；`lang.json` 删除 |
| 收尾 | `python testsuite/run_all.py` | **165 模块 / 1157 用例全绿，隔离区 32 → 6 → 5 → 0** |

### 顺手结清的隔离区（4 条，均按“隔离≠不管”纪律逐条定性）

| 模块 | 真实原因 | 处置 |
|------|---------|------|
| `test_soft_i18n.py` | en 分类标签小写/连写（`installed`/`Otherplugin`/`Running environment`）+ zh-TW 用词过长 | **改产品侧**：`Installed`/`Database`/`System Tools`/`Other Plugins`/`Runtime`、`其他外掛` |
| `test_task_manager_i18n.py` | 断言锁定已被改写的旧选择器 `input[placeholder]` | 改为按能力断言 `[placeholder]` + `[title]` |
| `test_about_i18n.py` | 依赖**未入库**的构建输入 `phrases_full.py`（CI 永不可能通过）；另含硬编码绝对路径 | 删冗余用例（同文件 test_02 已在出库语言包上覆盖同一批键）；`BASE_DIR` 改为相对推导 |
| `test_index_i18n_fix.py` | 同上依赖 `phrases_full.py` | 改写为直接校验收件的 `template.index.json`（11 词条 + 4 条英文质量锁定） |
| （连带）`test_gate_selftest.py` | 隔离区清空后“名单非空”不再是有效判据 | 解析器拆出 `parse_quarantine()`，自证改用内嵌夹具；真实名单为空时跳过比例校验 |

### 一句话总结

本轮把「外语界面能看到的东西」从 **663 处空白/乱码**降到 **0**，并把这四类损坏写成 CI 可执行门禁（含自证夹具 + 真实数据路径变异自证）；版本号已提、语言包/核心脚本已接内容指纹，用户升级后能真正拿到这批修复。


