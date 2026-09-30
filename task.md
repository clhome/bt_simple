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

---
---

# 第 3 层「商业化收口」—— 安全红线 / 工程化底座 / 发布卫生（方案待评审）

> 来源：本轮「标准商业化产品」全仓复审（诊断见下「零、诊断摘要」）。
> 已确认前提（用户 2026-09-28 决策）：
> 1. 商业形态 = **开源社区版 + 商业增强版分层**（本轮不做 RBAC/License 激活，只定分层边界）。
> 2. 本轮聚焦三条线：**P0 安全红线 + 工程化底座 + 仓库与发布卫生**。
> 3. 改动约束 = **可改 DB schema + 可新增运行时依赖**。
> 4. 推进方式 = **先出方案清单，评审通过后再动手**（本文档即清单，`[ ]` 为未开工）。
>
> 基线：`python testsuite/run_all.py` → 165 模块 / 1157 用例 / 0 隔离项全绿。
> 纪律：每完成一项即跑对应验证 + 全量门禁，通过后在本文件打勾。

---

## 零、诊断摘要（商业化视角）

| 维度 | 就绪度 | 一句话判断 |
|---|---|---|
| 功能完整度 | ★★★★☆ | 36 插件 + 站点/计划任务/防火墙，够用 |
| 应用安全 | ★★★☆☆ | 框架层已收口，CSRF/会话/错误脱敏仍有硬伤 |
| **供应链安全** | **★☆☆☆☆** | 安装即执行第三方代理下发的 root 脚本 —— **最大风险** |
| 权限与审计 | ★★☆☆☆ | 单管理员、审计日志无身份且有「一键清空」 |
| 可靠性/可运维 | ★★★☆☆ | ORM 异常当返回值、174 处裸 except、无迁移框架 |
| 工程化/可维护 | ★★☆☆☆ | 5273 行单文件、自研测试 runner、无依赖锁定/CVE 扫描 |
| 仓库/发布卫生 | ★★☆☆☆ | clone 即下发 794MB 工作区、无签名校验 |

**与总目标的三条对应关系**：
- 「安全」→ G 组（供应链 + 请求安全 + 审计）
- 「可靠」→ H 组（迁移框架 + 异常语义 + 可观测性）
- 「高效」→ H4/H5 + I 组（发布体积 794MB → 5.6MB）

**本轮已核对并更正的两处既有认知（避免方案写错前提）**：
- `参考/` 目录**未入库**（`.gitignore` 已忽略），无需处理。
- `plugins/*/js/*.i18n.bak` 是**已决策保留**的 i18n 回滚快照（`.workbuddy-ai/memory/MEMORY.md` 明确「禁止删除」）→ 本方案**不删**，改由 G1 的 tarball 发布形态让 `export-ignore` 生效，进而不再下发给客户。

---

## G. P0 安全红线

### G1 发布链路改为「签名 tarball + 强制验签」，替代裸 `git clone`（本轮核心）

> ⚠️ **前置约束（用户 2026-09-28 明确）**：中国大陆服务器直连 GitHub 经常失败，项目内置多套代理。
> **修改必须保证所有现存代理地址继续可用**。因此本项设计反转为：
> **代理全部保留、可继续随便换；安全性由「发布包签名」保证，而不靠限制代理。**
> 代理只是传输层，签名校验在下载之后、解压之前——**走哪个代理都与安全无关**。
> 这也让仓库里 420 处 `wget --no-check-certificate` / `curl --insecure`（大陆网络必需）
> 从「致命嗅探洞」降为「可接受的传输层风险」。

**现状（已在代码中逐条核实）**：
- `deploy.sh:20-31`：本地无 `scripts/github_download.sh` 时，从 `raw.githubusercontent.com` **或第三方代理**下载后 `source` 执行（root 权限）——这是**未验签就执行代码**的唯一路径。
- `deploy.sh:745-816`：主程序走 `git clone`，tag 不做签名/校验和验证。
- `deploy.sh:240`：`curl ... | sh` 安装 acme.sh。
- `web/core/yf.py:429-440`：运行期在 5 个第三方代理间测速切换。
- 实测：`git archive HEAD` 发布包 **5.6MB**；`git clone` 落地 **794MB**（含 94MB `.git`、`文档/` 14.4MB、`testsuite/` 2MB、`cl_tasks/` 0.8MB、`.i18n.bak` 1.6MB）。
- **代理列表在 3 处重复且已不一致**：`scripts/github_download.sh:_GH_PROXY_LIST`（5 条，含 `gh.ddlc.top`）、
  `deploy.sh`（第 108/133-136/229 行硬编码，**缺 `gh.ddlc.top`**）、`web/core/yf.py`（4 条）。
  曾经导致「同一个包在脚本里能下、在面板里不能下」。

**目标**：
- [x] G1.1 新增 `scripts/tools/yf_release_sign.py`（Ed25519/minisign 布局签名器，含 `genkey` / `sums` / `sign` / `release`）与 `keys/` 目录约定（公钥入库、私钥只进 CI Secrets）。
- [x] G1.2 新增 `scripts/tools/yf_release_verify.py`：纯 Python + `cryptography` 的引导级校验器，**刻意不依赖 `minisign`/`gpg`/`openssl` 二进制**（避免「校验工具本身怎么可信」的死循环）。
- [x] G1.3 自证：`testsuite/test_release_signature.py`（**12 项**，含往返 + 5 类篡改拒绝 + 占位公钥拒绝 + CLI 退出码）。
- [ ] G1.4 `.github/workflows/release.yml`：tag 推送时用 `git archive` 产出 `yf-panel-<ver>.tar.gz`（**自动应用 `export-ignore`**，实测 5.6MB）+ `SHA256SUMS` + 签名，一并作为 Release 附件。
- [ ] G1.5 `deploy.sh`：改为「用**现有代理机制**下载 tarball + `SHA256SUMS` + `.minisig` → **验签通过才解压**」；验签失败立即中止。
  - [x] 引导级辅助函数已落地：`yf_bootstrap_download` / `yf_verify_release` / `yf_fetch_signed_release` / `yf_load_download_lib_from_release`
  - [ ] `download_code()` 接入上述路径（目前函数已就位但尚未被调用）
- [x] G1.6 `deploy.sh` 删除「从网络拉脚本并 `source`」路径：引导阶段改用**内联最小下载器**（同代理列表），拿到已签名 tarball 后，后续一律使用**包内**的 `scripts/github_download.sh`。
- [x] G1.7 代理列表**漂移守卫**：`testsuite/test_deploy_bootstrap.py::test_04` 断言 `deploy.sh` 内联列表与 `scripts/github_download.sh:_GH_PROXY_LIST` 严格一致；内嵌校验器/公钥同样逐字节守卫（`test_01` / `test_02`）；`test_05` 守住「不得再出现下载脚本后 source」红线。
- [x] G1.9 **验签范围守卫**（用户 2026-09-28 追加口径）：
  本发布密钥**只能**用于校验面板自身产物 `yf-panel-<版本>.tar.gz`；
  插件拉取的 openresty / php / mysql / jdk / acme.sh / docker 等**第三方仓库一律不验签**。
  由 `test_08_verification_scope_is_panel_release_only` 锁死（调用点唯一性 + 产物名固定 + 插件目录不得出现发布公钥/校验器）。
  - 理由：拿不到也不该拿第三方的私钥；且我们不掌握其发布节奏，强制验签会把上游升级全部卡死。
  - **已知残留风险（不在本轮范围）**：被劫持的代理仍可能下发恶意第三方包。缓解手段（可选、后续）：
    插件内校验上游官方 checksum（`plugins/php/versions/*/install.sh` 已有 `sha256sum` 雏形），或按插件版本内置已知良好哈希。
- [ ] G1.8 保留自定义源能力（`BT_SIMPLE_REPO`），自定义源**同样必须提供签名**；仅允许 `YF_ALLOW_UNSIGNED=1` 显式降级，降级时打印醒目警告并写审计日志。

> ❗**上线顺序警告**：真实密钥生成前，`keys/yf-release.pub` 为占位符，`deploy.sh` 会 **fail-closed 拒绝安装**。
> 落地顺序必须是：先跑 `release.yml` 产出签名包 → 再启用 `deploy.sh` 强制验签。一次性密钥步骤见 `keys/README.md`。

### G2 自动更新改为可控 + 可回滚

- [ ] G2.1 `web/admin/setup/init_cron.py:78` 的「[可删]面板自动更新」改为**默认不创建**（新装不再静默自动升级）。
- [ ] G2.2 面板设置页新增「自动更新」开关 + 维护窗口（星期/时间）。
- [ ] G2.3 更新前自动备份 `web/` + `data/panel.db` + `data/*.pl` 到 `/www/backup/yf_panel_<ver>_<ts>/`，并记录版本。
- [ ] G2.4 新增 `yf rollback`，回滚到上一版本目录 + 数据备份（与 G1 的版本化 tarball 配套）。

### G3 状态变更强制 POST + CSRF Token

**现状**：CSRF 仅校验 POST 的 Referer；以下端点可 GET 改状态并绕过：
`/plugins/run`（`web/admin/plugins/__init__.py:328`，参数取自 `request.args`）、`/plugins/callback`（:399）、`/plugins/clear_cache`（GET）、`web/admin/site/ssl.py:94 /remove_cert`、`/login?signout=True`。
`SameSite=Lax` 只挡跨站子资源请求，**顶层导航型 CSRF 仍可触发**。

- [x] G3.1 全部状态变更端点强制 `methods=['POST']`；并**只从表单取参**。
  - 实测前端这些端点**全部已是 `$.post`**（无 `$.get`/`href` 调用）→ **零前端破坏面**。
  - 已改：`/plugins/run`、`/plugins/callback`、`/plugins/clear_cache`、
    `ssl/set_dnsapi|set_cert_to_site|remove_cert|http_to_https|close_to_https`、`/del_panel_info`。
- [x] G3.2 双提交 CSRF Token：会话级 token → 模板 `meta` → 前端 `$.ajaxSetup` 统一带 `X-CSRF-Token`。
  - 判定逻辑抽到 `web/core/security.py::csrf_decision()`（**纯函数、无 Flask 依赖**），便于真值表单测。
- [x] G3.3 **OR 语义（关键设计，保证零回归）**：`token ∥ referer/origin ∥ App-Id ∥ 豁免路径`。
  任何今天能过的请求明天还能过；同时**修好了「隐私插件/反向代理剥掉 Referer 导致正常用户被拦」**。
  仅靠单侧通过时会打 debug 日志，作为「何时收紧为强制 Token」的度量依据。
- [x] G3.4 Referer/Origin 校验**保留**作为纵深防御（未删除）。
- [x] G3.5 回归用例：`testsuite/test_request_security_hardening.py`（**23 项**），
  CSRF 部分为 11 条真值表（安全方法 / token-only / referer-only / 双错 / API 头 / 豁免 / 常量时间比较…）。

### G4 审计日志可信化（为商业版合规打底）

**现状**：`web/core/yf.py:1620` `writeLog()` **硬编码 `uid=0`**（取值代码被注释掉），无来源 IP / UA / 请求指纹；`/logs/del_panel_logs` 允许一键物理清空。

- [ ] G4.1 `writeLog()` 补齐 `uid / username / ip / ua / request_path / result`，`uid` 从 session 取。
- [ ] G4.2 新增 `panel_audit` 表（append-only）：`id, ts, uid, username, ip, ua, path, method, action, target, result, detail`。
- [ ] G4.3 写操作类接口统一落审计：插件启停/卸载、文件删除/重命名、站点增删、DB 操作、设置变更、计划任务增删。
- [ ] G4.4 `del_panel_logs` 由「物理删除」改为「归档」（导出 CSV/JSON + 打标记），**归档动作本身也记审计**。
- [ ] G4.5 商业增强版预留（本轮只留表结构与接口，不实现）：审计**哈希链**（含前一条 hash）+ 远端 syslog 转发。

### G5 错误信息脱敏 + 全局异常兜底

- [x] G5.1 新增 `core/yf.py::userSafeError()`：内部细节（绝对路径/SQL/依赖版本）只进日志，
  前端只拿「操作失败 + 追踪号」。已接入 `/plugins/run` 与 `/plugins/callback`。
- [x] G5.2 新增 `@app.errorhandler(500)` + `@app.errorhandler(Exception)`（保留 HTTPException 原语义），
  兜底页不回显堆栈。
- [x] G5.3 回归用例：断言脱敏后不含内部路径/组件名且带追踪号；兜底页无异常插值。

---

## H. 工程化底座

### H1 DB 迁移框架（已完成，含「自愈」语义）

**现状（已核实）**：`web/thisdb/user.py`、`crontab.py`、`firewall.py` 顶层每次导入都执行
`ALTER TABLE ... ADD COLUMN` 并 `except: pass`；而 `core/db.py::Sql.execute()` 失败时
只返回 `"error: ..."` 字符串、**从不抛异常** —— 那层 except 是摆设，失败即静默半残库。

> 实测发现（重要）：`web/admin/setup/sql/default.sql` **缺** crontab 的
> `min_start_en / min_start_h / min_start_m / min_end_en / min_end_h / min_end_m` 六个字段，
> 也就是说**全新安装也会缺**，全靠那批 import 期 ALTER 兜底。已由新框架补齐。

- [x] H1.1 新增 `web/core/migrations/`（纯标准库 + 复用 `core.resources` 的 SQLite 调优）：
  `schema.py`（期望结构真值）/ `steps.py`（版本化数据迁移）/ `runner.py`（引擎）/ `__init__.py`（对外 API）。
- [x] H1.2 结构对齐与版本解耦 —— **自愈的关键**：
  结构对齐（缺表/缺列）**每次启动都跑、不查版本号**；只有数据迁移走版本号。
  这样「上次迁移被 kill」「从旧备份恢复库」「版本表丢失」都能自动收敛。
- [x] H1.3 改结构前自动备份（sqlite3 在线备份 API，含 WAL 已提交页，保留最近 5 份）；
  **无变更时零备份开销**（先只读探测再决定是否写）。
- [x] H1.4 跨进程串行化（`BEGIN IMMEDIATE`）+ 每步 `SAVEPOINT` 子事务隔离；
  单步失败只回滚该步、不牵连结构对齐成果，且**不记版本**（下次启动自动重试）。
- [x] H1.5 降级不破坏：库版本 > 代码版本时只告警、不动数据。
- [x] H1.6 失败可观测：写 `data/migration_failed.pl` 标记 + 落 `schema_migration_log` 表；
  引擎**永不抛异常**（面板哪怕 schema 不全也要能起来）。
- [x] H1.7 接入点：`web/thisdb/__init__.py` 在导入子模块**之前**调 `_bootstrap_schema()`，
  因此 web / `panel_task.py` / `panel_tools.py` 任何入口碰面板库都会先自愈。
- [x] H1.8 回归用例 `testsuite/test_db_migration_selfheal.py`（**14 项**）：
  缺列/缺表/半途状态收敛、幂等、无变更不备份、降级不丢数据、失败回滚+重试、
  损坏库不抛异常、只读探测、隔离不碰真实库、短路与 force。

### H2 ORM 异常语义修正（本层风险最高）

**现状（本轮实测统计）—— 两套 DB 层的失败语义不同，不能混改：**

| 层 | 实现 | 失败时返回 | 涉及文件 | 调用点 | 其中丢弃返回值 |
|---|---|---|---|---|---|
| **A. 站点/插件 DB** | `web/core/orm.py::ORM` | **异常对象**（`return ex`） | 8 | 470 | 172 |
| **B. 面板 SQLite** | `web/core/db.py::Sql` | `"error: ..."` **字符串** | 29 | 125 | 53 |

A 层重灾区（按调用点）：`plugins/mysql/index.py` 189、`plugins/mariadb/index.py` 180、
`plugins/data_query/sql_mysql.py` 41、`plugins/postgresql/index.py` 29、`web/core/yf.py` 15、
`plugins/sphinx/...` 11、`plugins/gitea/index.py` 3。

**两类真实故障形态：**
1. **静默失败**：172（A）+ 53（B）处直接丢弃返回值。写操作失败时**没有任何信号**，
   表现为「界面提示成功、数据没落库」。
2. **异常被当数据用**：若调用方只做真值判断（`if row:`），异常对象是 **truthy**，
   会直接被当成「查到了数据」，后续取字段时报 `AttributeError` 或得到无意义值。

- [x] H2.1 产出调用点清单与风险分级（即上表）。
- [ ] H2.2 引入 `ORMError`，`ORM.execute/query` 改为抛出；按上表逐层、逐文件适配。
- [ ] H2.3 `Sql.execute/query` 保持返回字符串（兼容面太大），但**新增** `Sql.executeStrict()`
  供新代码使用，并给旧调用点逐步迁移到 strict。
- [ ] H2.4 回归用例：连接失败 / SQL 错误 / 正常三条路径的返回类型断言。

> 为何不在本轮直接改：A+B 共 **595 个调用点、37 个文件**，包含本仓最大的两个文件
> （`mysql/index.py` 5273 行、`mariadb/index.py` 4371 行）。一次性改语义会把这轮改动
> 从「可审查的安全收口」变成「不可审查的大规模重构」，风险与收益不匹配。
> 正确做法是先把清单钉死，下一轮按「A 层先、B 层后」分文件推进。

> ❓**决策点 3（待确认）**：下一轮是否按上述顺序开工？

### H3 裸 except 收口（棘轮机制，不搞一刀切）

- [x] H3.2 新增 `scripts/verify_code_quality.py`：三个指标（`bare_except` / `silent_except` / `print_in_web`）
  的**只减不增**棘轮，基线存 `scripts/code_quality_baseline.json`，已挂进 `run_all.py --static`（静态门禁 2 → **4 项**）。
  - **用 `ast` 而不是正则**：正则分不清「真裸 except」与「字符串/注释里的 except」，
    也数不准字符串里的 `print(`；一旦误报就会被人当噪音忽略，门禁也就废了。语法解析失败才降级为正则。
  - 自带 `--self-test` 夹具（三类各命中 1 + 合法写法零误报）。
  - 基线：`bare_except 172` / `silent_except 518` / `print_in_web 46`。
  - `--update` 默认**拒绝上调**，需显式 `--allow-increase` 并写明理由。
- [ ] H3.1 存量 172 处裸 `except:` / 518 处静默 `except: pass` 的**逐批清理**（棘轮已锁死不再恶化，
  后续每轮清一批并把基线调低即可）。

### H6 路径守卫（新增：根因于本轮清理的工作区垃圾）

**现象**：源码树里出现了 `web/MagicMock/mock()/<id>/…` 与 `web/{}/redis/data/redis.log` 两个垃圾目录。
**根因**：测试里对 `getPanelDir()` / `getServerDir()` 的 mock 未完全配置（返回 `MagicMock`）或格式化串缺少参数（留下字面量 `{}`），
而生产代码**不做路径合法性校验就 `makedirs`**，把非法路径当真写进了源码树。
**风险**：同类问题在真实运行中表现为「把数据写到了意外位置」（尤以 root 身份运行时危害更大），且极难排查。

- [ ] H6.1 在统一的目录创建入口（`yf.makeDirs` / 路径拼接处）加守卫：必须为**绝对路径**、无 `{}` 等未展开占位符、位于允许的根（`/www` 或工作区）之下；不满足则报错而非静默创建。
- [ ] H6.2 回归用例：非法路径（含 `MagicMock`/`{}`/相对路径）必须被拒绝，且不产生任何目录。

### H4 依赖与 CI 安全门禁

- [ ] H4.1 `requirements.txt` 拆分运行/开发依赖，并生成带哈希的 `requirements.lock`。
- [ ] H4.2 CI 新增：`pip-audit`（CVE 扫描）、`bandit`（重点盯 `os.system` / `shell=True`）、`ruff`（先宽松规则起步）。
- [ ] H4.3 Release 附带 SBOM（`cyclonedx-bom`）。
- [ ] H4.4 （可选）`os.system` 存量（mysql/mariadb/php/pureftp/rsyncd…）分批替换为 `safeExecShell`，先出清单定优先级。

### H5 可观测性最小闭环

- [ ] H5.1 `web/` 下 47 处 `print()` → `logging`（按模块分档）。
- [ ] H5.2 请求级 `X-Request-Id` 贯穿响应头与日志。
- [ ] H5.3 新增 `/healthz`（进程 + DB + 关键目录可写 + 磁盘余量）；`/metrics`（Prometheus 文本，默认关闭）预留。

---

## I. 仓库与发布卫生

- [x] I0 更正既有认知：`参考/` 未入库（无需处理）；`.i18n.bak` 为已决策保留的回滚快照（**不删**，由 G1 的 `export-ignore` 生效解决下发问题）。
- [x] I1 清理工作区垃圾：已删 `grep.exe.stackdump`、空目录 `web/MagicMock/mock()/`、`web/{}/redis/`；`.gitignore` 已补 `*.stackdump` 与 `/keys/*.key`。
  > 根因并入 H6：这两个目录是**测试 mock 未配置**时，生产代码把非法路径（`MagicMock/mock()`、`{}`）当真写进了源码树——缺路径守卫。
- [ ] I2 发布流程规范化：`RELEASE_TEMPLATE.md` 增加「变更类型（安全/功能/修复）」「升级说明」「回滚方法」必填段；CI 断言 `tag == APP_VERSION`。
- [ ] I3 `文档/` 瘦身：`文档/待审核插件/zabbix/data/*.sql.gz`（8.2MB）移出仓库或改挂 Release 附件。
  > ❓**决策点 2**：该 zabbix 数据是否属于交付内容？
- [ ] I4 商业版分层**边界约定**（本轮只落地骨架，不实现 RBAC/激活）：`web/core/edition.py`（`EDITION` 常量 + `is_pro` 探测）+ 商业专属代码目录约定 + `git archive` 剔除脚本；配一个示例探测器与回归用例。

---

## 验证门禁（本层新增）

- `python testsuite/run_all.py`（全量，基线 165 模块 / 1157 用例 / 0 隔离项）
- `scripts/verify_code_quality.py`（裸 except / print 棘轮）
- `scripts/verify_release_integrity.py`（发布包签名校验三路径自证）
- CSRF / HTTP 方法 / 错误脱敏 / 迁移幂等 回归用例
- 所有改动保持 **UTF-8 无 BOM + LF**

---

## 建议实施顺序（每步独立可验证、可回退）

| 批次 | 内容 | 理由 |
|---|---|---|
| 1 | G1 + G2 + I1 + I2 | 供应链与发布形态，收益最大且互相配套 |
| 2 | G3 + G5 + H3 | 请求安全与错误面，纯代码层、风险可控 |
| 3 | G4 + H1 | 审计与迁移，含改表，需要第 1 批的发布可回滚能力兜底 |
| 4 | H4 + H5 + I3 + I4 | 工程化与分层的长期底座 |

## 待你确认的 3 个决策点

1. ✅ **G1 签名方案 = minisign 完整签名**（用户 2026-09-28 已拍板）。
2. ⏸️ **I3（zabbix 8.2MB sql.gz）**：未答，**按推荐默认执行 → 不动**（`文档/` 已 export-ignore，换 tarball 发布后本就不下发）。
3. ⏸️ **H2（ORM 异常语义）**：未答，**按推荐默认执行 → 本轮只出调用点清单**，完整修正留下一轮。

---

## 本层进度记录

| 批次 | 项 | 状态 | 验证 |
|---|---|---|---|
| 1 | G1.1 签名器 `scripts/tools/yf_release_sign.py` | ✅ | 被下述用例覆盖 |
| 1 | G1.2 引导级校验器 `scripts/tools/yf_release_verify.py` | ✅ | 纯 Python + `cryptography`，无二进制依赖 |
| 1 | G1.3 签名链路自证 `testsuite/test_release_signature.py` | ✅ | **12 用例全绿**（往返 + 5 类篡改拒绝 + 占位公钥拒绝 + CLI 退出码 + SHA256SUMS 兼容解析） |
| 1 | `keys/` 目录约定 + `.gitignore` 屏蔽私钥 | ✅ | `keys/README.md` 含一次性激活三步 |
| 1 | I0 认知更正（`参考/` 未入库、`.i18n.bak` 不删） | ✅ | 见上文 |
| 1 | I1 工作区垃圾清理 | ✅ | 已删 `grep.exe.stackdump`、`web/MagicMock/`、`web/{}/`；`.gitignore` 补两条 |
| — | 门禁回归 | ✅ | `run_all.py --static` 全绿；`-k release_signature` → 12/12 |
| 1 | G1.4 `release.yml` 产出签名 tarball | ✅ | `git archive` 实测 **5.4MB / 1943 条目**，`文档/`/`testsuite/`/`.i18n.bak` 全部 export-ignore 生效；版本断言本地试跑 PASS |
| 1 | G1.5/G1.6 `deploy.sh` 内嵌公钥+校验器、内联代理下载器、删除远端 source | 🟡 函数就位 | `test_deploy_bootstrap.py` **8 项全绿**（含逐字节漂移守卫；语法检查在 Windows 下跳过，`bash -n` 已手工确认 OK） |
| 1 | G1.5 `download_code()` 接入签名路径 | ✅ | 默认**放行**（用户口径）；回退带醒目告警与 `YF_REQUIRE_SIGNATURE=1` 指引 |
| 1 | G1.7 代理列表漂移守卫 | ✅ | `test_04` 锁死两处列表一致 |
| 1 | G1.9 验签范围守卫（仅面板自身产物） | ✅ | `test_08` 锁死 |
| 1 | 真实发布密钥生成与验证 | ✅ | 用户已 `genkey`；探针 `test/verify_real_pubkey_negative.py` **14/14**（含正向对照 + 10 类伪造全拒） |
| 3 | H1 面板库自愈迁移框架 | ✅ | `test_db_migration_selfheal.py` **14 项**；实测补出 `default.sql` 缺失的 **6 列**，且不碰仓库真实库 |
| 2 | G2 自动更新可控 + 回滚 | ✅ | 默认关闭 + 移除历史任务 + `yf rollback`（回滚本身可回滚）；**并堵住更严重的洞**：`yf update` 原为「从 panel.yftec.top 拉脚本无校验执行」 |
| 2 | G3 状态变更强制 POST + CSRF Token | ✅ | `test_request_security_hardening.py` **23 项**；OR 语义保证零回归 |
| 2 | G5 错误脱敏 + 500 兜底 | ✅ | `userSafeError()` 追踪号机制 |
| 2 | H3.2 代码质量棘轮 | ✅ | 静态门禁 2 → **4 项**；基线 172/518/46 |
| 4 | G2.2 自动更新 UI 开关 | ⏳ 待做 | 后端 option + 端点已就位，缺前端开关与 6 语言词条 |
| 4 | H2/H4/H5/H6、I2/I4 | ⏳ 待做 | — |

### 全量门禁

| 阶段 | 命令 | 结果 |
|------|------|------|
| 基线 | `python testsuite/run_all.py` | 165 模块 / 1157 用例 / 0 隔离 / 2 静态门禁 |
| 第 1 批后 | 同上 | 168 模块 / 1194 用例 |
| 第 2 批后 | 同上 | **170 模块 / 1227 用例 / 0 隔离 / 4 静态门禁 全绿** |

### 本轮新发现（已并入清单）

- **H6 路径守卫**（P1）：源码树里凭空出现 `web/MagicMock/mock()/<id>/` 与 `web/{}/redis/data/redis.log`，
  根因是测试 mock 未配置 / 格式化串缺参时，**生产代码不校验路径就 `makedirs`**。真实运行下表现为「把数据写到意外位置」，
  以 root 运行时尤危。已清理现场，并新增 H6 防御项。
- **代理列表 3 处重复且已不一致**（P1）：`deploy.sh` 硬编码了 3 组代理串，且**缺 `gh.ddlc.top`**；
  与 `scripts/github_download.sh:_GH_PROXY_LIST`、`web/core/yf.py` 各自为政。已升为 G1.7 单一真源 + 漂移守卫。
- **420 处 `wget --no-check-certificate` / `curl --insecure`**（已被 G1 降级为可接受）：
  大陆网络+代理环境下无法普遍开启 TLS 强校验，**保留不动**；安全性改由发布包签名兜底。
  这也正是 G1 的核心价值论证：**验签后，不可信代理变得可以接受**。


---

# 第 4 层「供应链门禁红灯修复」—— `security-scan.yml` 首次运行后的 triage

> 触发：推送「安全增强」提交后，`供应链安全扫描` 的两个阻断型 job 变红。
> 口径：这是扫描器在干活，按报告 triage 后再合并，**不把 job 改成 `continue-on-error`**。

## 一、依赖漏洞扫描（pip-audit：21 条 / 3 包）

| 包 | 修复前 | 修复后（py≥3.9） | 依据 |
|----|--------|------------------|------|
| flask | 2.3.3 | 3.1.3 | PYSEC-2026-2151（会话页缺 `Vary: Cookie`，可被缓存投毒）；2.x 无修复版 |
| Werkzeug | 2.3.8 | 3.1.9 | 调试器 RCE / multipart 资源耗尽 / `safe_join` 处理 Windows 设备名 |
| cryptography | 46.0.7 | 50.0.1 | PKCS#7 预言机、证书链指数膨胀、通配符越权；GHSA-537c 为 wheel 内置 OpenSSL |
| pyOpenSSL | 26.0.0 | 26.4.0 | 26.0.0 写死 `cryptography<47`，是 cryptography 卡在 46.x 的直接原因 |

核心矛盾：**修复版本全部要求 Python≥3.9**，而面板仍需支持 CentOS 7.9 / Debian 10 这类只自带
Python 3.6~3.8 的系统。故采用**环境标记分档**（与仓库既有 `version/r3.x.txt` 分档思路一致）：

```
flask>=3.1.3,<4.0.0; python_version >= '3.9'
flask>=2.0.3,<3.0.0; python_version < '3.9'      # 老系统：上游已无修复版，已知残留风险
```

CI 在 Python 3.11 解析，只看得见 `>=3.9` 分支 → 门禁真实有效，且不会把老系统装不上面板。

- [x] `requirements.txt` 四处依赖（flask / Werkzeug / pyOpenSSL / cryptography）改为 `python_version` 分档
- [x] `pip-audit -r requirements.txt --strict` 本地复跑：**No known vulnerabilities found**
- [x] 实测解析结果：flask 3.1.3 / Werkzeug 3.1.9 / pyOpenSSL 26.4.0 / cryptography 50.0.1

## 二、安全静态扫描（bandit：33 条 HIGH）

逐条 triage，**不用全局 skip**（全局 skip 等于把门禁废掉），全部以行内 `# nosec Bxxx  # 理由` 记录：

| 规则 | 数量 | 处置 |
|------|------|------|
| B605/B602 shell 调用 | 25 | **豁免**：面板本职即执行 shell；`panel_tools.py` 是 root 交互 CLI，命令串只由 `INIT_CMD` 常量与面板自身目录拼接，`yf_input` 仅作分支选择 |
| B507 paramiko `AutoAddPolicy` | 3 | **豁免**：沿用历史信任策略（改严格 known_hosts 属行为变更，见「残留风险」） |
| B324 `hashlib.md5` | 2 | **豁免 + 真修**：`md5()` 保留给缓存键/指纹/历史哈希比对；basic_auth 与旧密码校验改 bcrypt |
| B413 `Crypto.Cipher.AES` | 1 | **真修**：删除死代码 `aesEncrypt_Crypto` / `aesDecrypt_Crypto` |
| B202 `tarfile.extractall` | 1 | **真修**：改 `filter='data'`（tarfile 官方安全解压入口） |
| B103 `chmodR(path, 755)` | 1 | **真修（误报）**：`chmodR` 按八进制解析，改传字符串 `'755'`；bandit 此前把十进制 755 误判为 0o1363 |

### MD5 → bcrypt 的具体收口

- `web/core/yf.py` 新增 `isLegacyPwdHash()` / `checkPwdCompat()`：**bcrypt 优先，历史 MD5/SHA256 仅作一次性比对**（`hmac.compare_digest` 常量时间），`admin/__init__.py` 的 basic_auth 校验与 `setting.py` 的原密码校验统一走它。
- `setting.py::set_basic_auth` 改为 `yf.hasPwd()`（bcrypt）落库；老安装的 MD5 存量值仍可登录，下次改密即自动升级。
- `login.py::_password_matches` 收敛到兼容层，命中遗留弱哈希后仍即时回写 bcrypt。

- [x] `bandit ... -lll` 本地复跑：**No issues identified**，`High: 0`，30 处豁免全部带理由
- [x] 语法与静态门禁：`py_compile` 全通过；`run_all.py --static` 4 项全绿

## 三、验证记录

| 项目 | 命令 | 结果 |
|------|------|------|
| 依赖漏洞 | `pip-audit -r requirements.txt --strict` | 无漏洞（21 条全消） |
| 安全静态 | `bandit -r web scripts panel_task.py panel_tools.py -x testsuite,test,node_modules,.git -lll` | 退出码 0，High 0 |
| 密码兼容层 | `test/_pwd_compat_probe.py`（20 断言，跑完已删） | 全通过（bcrypt / MD5 / SHA256 / 空值 / 非法哈希 / basic_auth 新旧值） |
| 全量门禁 | `PYTHONUTF8=1 python testsuite/run_all.py` | **173 模块 / 1276 用例 / 0 隔离 / 4 静态门禁 全绿** |
| 回归守卫 | `testsuite/test_supply_chain_guards.py` 新增 `test_16/17/18` | 锁死依赖分档、nosec 必须带理由、basic_auth 不得再用 MD5 |

> 说明：`test_db_migration_selfheal` / `test_edition_layering` 的两条失败是 **Windows 子进程中文编码**
> 既有问题（`PYTHONUTF8=1` 下全绿，Linux CI 不复现），与本次改动无关。

## 四、已知残留风险（明确记录，不粉饰）

1. **Python<3.9 的系统仍带 CVE**：Flask 2.x / Werkzeug 2.x / cryptography 46.x 在其支持范围内上游已无修复版。分档只保证「新系统真修复 + 老系统不被拖死」，不等于老系统安全。
2. **SSH 主机密钥不校验**（B507 ×3）：`ssh_local.py` / `ssh_terminal.py` 连接用户配置的**非本机**目标时仍沿用 `AutoAddPolicy`，存在中间人风险。改严格校验会中断既有用户流程，**待专门评估**（本轮未动）。
3. **MD5 仍存在于非口令场景**：缓存键、文件名指纹、校验和、以及 `yf.md5()` 派生的 Fernet key 未动（后者改动会破坏存量加密数据），以带理由的 nosec 显式豁免。
4. **`security/audit-ignore.txt` 未启用**：本轮全部靠「真修复 + 分档」解决，不需要豁免文件兜底。

### 顺带结清的既有测试期望

| 文件 | 原因 |
|------|------|
| `testsuite/test_p2_deep_optimization.py` | 原断言写死了 `yf.md5(old_password)`（旧实现），改为校验 `yf.checkPwdCompat(...)` |
| `testsuite/test_login_urlguard_safepath.py` | 原断言要求 `_password_matches` 内含 `legacy_md5` 局部变量，改为校验兼容层调用 |



# 第 5 层「会话可撤销 + 登录限流双维度」—— B1 / B2（本轮）

> 来源：`参考/20260928优化.md` §2 B 类 P1（B1 会话不可撤销、B2 限流只按 IP）。
> 门禁基线：**174 模块 / 1294 用例 / 0 隔离 / 4 项静态门禁 全绿**
> （本轮起点：173 模块 / 1276 用例 / 0 隔离 / 4 静态门禁）
> 本轮**不碰** C1 ORM 异常语义（用户拍板：高风险项单独立项）。

## 一、交付内容

| 组 | 项 | 关键实现 | 状态 |
|---|---|---|---|
| B1 | 服务端会话存储 | 新增 `web/core/panel_session.py` + `panel_session` 表；登录态有服务端副本（`session_id/uid/ip/ua/created_at/last_seen/expires_at/revoked`） | ✅ |
| B1 | 可撤销 / 可强制下线 | `touch()` 每请求校验；改密码 `revoke_user_sessions()` 踢掉所有设备；二步验证变更同样撤销（保留当前会话） | ✅ |
| B1 | 会话列表 UI + 接口 | `/setting/get_sessions`、`/setting/revoke_session` + 设置页「登录会话」入口（layer 弹窗：IP/设备/登录时间/最后活跃/下线） | ✅ |
| B1 | 生命周期统一 | `session['overdue']` 由 7 天改为 1 天，与 `PERMANENT_SESSION_LIFETIME`、`panel_session.SESSION_TTL` 三者一致 | ✅ |
| B1 | 降级（fail-open） | 会话表不可用 / 查询异常时 `touch()` 放行，退回纯签名 Cookie；`create()` 未落库则返回空串（不制造查不到的服务端会话） | ✅ |
| B2 | 双维度限流 | 新增 `web/core/login_guard.py` + `panel_login_failure` 表；IP 与**账号**各记一份，任一超限即封禁 | ✅ |
| B2 | 计数落库 | 计数 / 封禁窗口落库（多 worker、重启口径一致）；表不可用时自动退回进程内存计数 | ✅ |
| B2 | 封禁审计 + 解封 | 触发封禁写 `panel_audit`（`login.banned`）；新增 `/setting/unlock_login` 供管理员解封（防账号维度误伤） | ✅ |
| — | 表自愈 | 两张新表 + 索引登记进 `core/migrations/schema.py`，老库升级自动补齐 | ✅ |
| — | i18n | 9 个新词条 × 6 语言；已跑 `export_lang_carriers.py --apply` 重派载体 | ✅ |

## 二、关键设计决策（含取舍）

1. **fail-open 与 fail-closed 的边界**：
   * 「表不可用 / 查询异常」→ **放行**（fail-open），绝不把所有人锁在门外；
   * 「表可用，但明确查不到 / 已撤销 / 已过期」→ **拒绝**（fail-closed）。
   为区分二者，`panel_session.touch()` 用 `query()` 的**错误串**判定 DB 异常，
   而不是复用 `find()` —— 后者把「读失败」和「查无结果」都返回 `None`，会误判。
2. **登录缓存与撤销时效**：撤销后主动 `invalidate_login_cache()`，
   因此 20s 缓存不会拖延「下一次请求即被登出」。多 worker 下其他进程仍有 ≤20s 延迟
   （面板默认 `workers=1`，已在 `invalidate_login_cache` docstring 写明）。
3. **旧 Cookie 一次性采纳**：升级前已登录的浏览器没有 `session_id`，
   首次请求时由 `isLogined()` 登记为服务端会话，纳入可撤销管理，用户无感。
4. **不改 C1**：`orm.py::return ex` 的语义未动，本轮只在新增模块里用 `query()` + 错误串判定。

## 三、验证记录

| 项目 | 命令 | 结果 |
|---|---|---|
| 新增用例 | `PYTHONUTF8=1 python testsuite/test_session_revocable.py` | **18/18**（表自愈 / 创建·撤销·过期·列表 / fail-open / IP·账号双维度 / 内存降级 / 调用点静态守卫） |
| 全量门禁 | `PYTHONUTF8=1 python testsuite/run_all.py` | **174 模块 / 1294 用例 / 0 隔离 / 4 静态门禁 全绿** |
| i18n | `python scripts/verify_i18n.py` | 11 项全绿 |
| 代码质量棘轮 | `python scripts/verify_code_quality.py` | bare 172 / silent 517 / print 45（只减不增） |
| JS 语法 | `node --check web/static/app/config.js` | 通过 |

## 四、已知边界（明确记录）

1. **多 worker 撤销延迟**：`_login_cache` 是进程内字典，多 worker 下其他进程最长 20s 才感知撤销。
   彻底解决需外置缓存（与 D6「单 worker 硬约束」同一议题），本轮不动。
2. **账号维度可被恶意锁定**：攻击者用同一用户名失败 N 次可触发 1 小时封禁（自 DoS）。
   已提供 `/setting/unlock_login` 解封入口，且封禁 1 小时后自动失效；如需更强（只对已存在账号计数、
   或对账号维度用更长窗口）属产品策略，待评估。
3. **`session_id` 随 Cookie 一起丢失**：清理 Cookie 即登出，符合预期。
4. **会话清理**：`prune()` 只删「过期或已撤销且超过 7 天」的行，登录时节流触发，不另起定时器。

---

# 后续排期（第 5 层未做项，按 `参考/20260928优化.md` 对照）

| 优先级 | 内容 | 说明 |
|---|---|---|
| P1 | B7 代理池单一真源 | 4 份安装/更新脚本 + 3 处运行时统一到 `scripts/proxies.list` |
| P2 | D1 审计流水 UI | 后端 `/logs/get_audit_trail` 已就绪，缺展示入口 |
| P2 | B5 `os.system` 47 处 / C3 `print` 45 处 | 机械但量大 |
| P2 | B4 去掉 Flask monkey patch / C4 `requirements.lock` | 需版本确认 / 需联网 |
| P0（需真机/CI） | A1 翻转签名开关 / A2 首个签名 Release | 依赖外部环境 |
| 立项（高风险/产品决策） | C1 ORM 异常语义 / C5 巨型文件拆分 / D3~D6 | 单独立项 |



# 第 6 层「可本地存量清理（批次 1）」—— B7 / B8 / C3 / B4

> 来源：`参考/20260928优化.md` §2（B7/B8/B4/C3）。
> 用户拍板（2026-09-29）：可本地存量清理分 4 批，**本轮只做批次 1**
> （代理单一真源 + 日志/补丁卫生），节奏为「先清单后改，逐批验证」。
> 门禁基线：**174 模块 / 1295 用例 / 0 隔离 / 4 项静态门禁 全绿**
> （本轮起点：174 模块 / 1294 用例 / 0 隔离 / 4 静态门禁）

## 一、交付内容

| 项 | 内容 | 验证 |
|---|---|---|
| **B7** 代理单一真源 | 新增 `scripts/proxies.list`（13 条：`键名\|URL\|作用域`）。5 个消费者全部改为读取：`scripts/github_download.sh`、`web/core/yf.py`、`scripts/{install,install_dev,update,update_dev}.sh`；`deploy.sh` 引导期因仓库未落地无法读文件，保留内嵌副本。 | `test_deploy_bootstrap::test_04` |
| **B8** 键名与域名对齐 | `ghproxy_net=gh-proxy.org` 错配消失（文件里键名统一为 `gh-proxy.org`）；`test_04` 新增「键名必须包含在 URL 中」断言。 | `test_04` |
| **C3** `print` → 日志 | `web/` 下 45 → **0**；36 处异常/诊断改用 `yf.writeFileLog` / `logging`；7 处 CLI 输出（`echoStart/echoEnd/echoInfo`）与 2 处 `site_reflect.py` 修复工具输出用 `# print-ok:` 豁免（内嵌 `__main__` 块自动豁免）。 | `verify_code_quality.py` |
| **B4** 删 Flask monkey patch | `web/admin/__init__.py` 删除 `RequestContext.session` property 补丁；`flask-socketio` 下界 `>=5.3.0` → **`>=5.3.6`**（首个兼容 Flask 3.x 的版本）。 | `test_login_urlguard_safepath::test_no_request_context_monkey_patch` |

## 二、关键设计（含取舍）

### B7：为什么 `deploy.sh` 仍需内嵌副本

`deploy.sh` 的引导期在仓库/发布包落地**之前**运行，此时磁盘上没有 `scripts/proxies.list`，
所以它必须内嵌 `YF_BOOTSTRAP_PROXY_LIST`。这不是漏网，而是固有约束——
由 `test_04` 把「内嵌副本 == 文件 rt 子集」钉死。

### B7：读不到文件的降级

`github_download.sh` / `yf.py` / 4 个脚本均做了 fail-soft：文件缺失时退化为

- 运行时列表：`[""]`（仅官方直连）；
- 交互菜单：只剩 `source`（官方直连），并打印警告。

**绝不因清单缺失而卡死安装**——与「大陆可用性优先」的既定口径一致。

### B7：作用域而不是硬编码子集

文件用 `rt` / `ui` / `both` 表达「运行时回退顺序」与「安装期菜单/测速」两个不同用途，
避免了「强行合并会改变安装体验」。新增代理只改 `scripts/proxies.list` 一行。

### C3：豁免标记而非一刀切

`panel_tools.py` 的 `echoInfo(...)` 是 **CLI 面向终端**的输出，改成日志后运维就看不到结果了。
所以计数器新增两类豁免：
1. 结构性：`if __name__ == '__main__':` 块内的 `print`（不依赖人工标记）；
2. 行内标记：`# print-ok: 理由`（用于跨模块的 CLI 输出）。

## 三、验证记录

| 项目 | 命令 | 结果 |
|---|---|---|
| 全量门禁 | `PYTHONUTF8=1 python testsuite/run_all.py` | **174 模块 / 1295 用例 / 0 隔离 / 4 静态门禁 全绿** |
| 代理单一真源 | `-k deploy_bootstrap` | 11/11 |
| 代码质量 | `scripts/verify_code_quality.py` | bare 172 / silent 517 / **print 0**（基线已同步下调） |
| 检测器自证 | `verify_code_quality.py --self-test` | 通过（含两类 print 豁免夹具） |
| B4 守卫 | `test_login_urlguard_safepath` | 18/18 |
| Shell 语法 | `bash -n`（5 个脚本） | 全部通过 |
| 代理派生实测 | 读取 `proxies.list` 后打印 | 运行时 6 项与 `deploy.sh` 内嵌副本逐项一致；交互菜单 9 项 |

## 四、已知边界（不粉饰）

1. **B4 未经运行时验证**：本机无 Flask/flask-socketio，webssh 握手无法本地跑。
   补丁删除依赖 `python-app-*.yml`（`workflow_dispatch`，真启 gunicorn）或真机确认。
   已在 `requirements.txt` 与测试注释写明原因。
2. **C3 仍有合理 print**：`web/` 之外（`plugins/`、`panel_tools.py`）未在计数器范围内，
   `panel_tools.py` 本身大量使用 `yf.echoInfo` 输出，保留不动。
3. **`print-ok` 标记可能被滥用**：它是人工豁免，没有强制校验；
   但基数已是 0，任何新增都要显式写理由，比静默增长强。

## 五、批次 2~4（未做，待下轮）

| 批次 | 内容 | 状态 |
|---|---|---|
| 2 | C2 异常存量清理（`web/core` + `web/admin` 约 40 处，分轮降基线） | 未开始 |
| 3 | B5 `os.system` 47 处（先出「变量来源可控性」清单） | 未开始 |
| 4 | C1 ORM 异常语义（高风险，595 调用点） | 未开始 |



# 第 7 层「P1-1：B5 `os.system` 存量收口」

> 来源：`参考/20260928优化.md` §B5（H4.4）。
> 用户拍板（2026-09-29）：全部改造（含 `plugins/*/t/` 测试目录与 `plugins/待审核/`），
> 管道类用 `shlex.quote` 逐段引用，新增 `os_system_count` 棘轮指标。
> 门禁基线：**174 模块 / 1295 用例 / 0 隔离 / 4 项静态门禁 全绿**（本轮起点同）

## 一、交付内容

| 项 | 结果 |
|---|---|
| 总量 | 实测 **47 行命中 = 44 处生效 + 3 行注释**；另发现 `panel_tools.py`（扫描器含它但文档口径只有 `web/`+`plugins/`）另有 **32 处** → **全量 76 处** |
| 真注入（用户可控） | 15 处：`rsyncd:args['path']`×6、`pureftp:path`×2、`{mysql,mariadb}/scripts/tools.py:password`×2、`mysql:import_sql/name`×2、`mysql:sync_args_*`×2、`待审核/acme:domain/email`×1 |
| 服务端路径/常量 | 29 处：`rm -rf SSH_PRIVATE_KEY/bak_file`、`mkdir/chown/chmod`、`expect`、sphinx、task_manager、`t/` 测试目录 |
| `panel_tools.py` | 32 处：15 处 `INIT_CMD` 常量列表化、12 处路径/管道列表化、**5 处必须用 shell 的如实保留并计入基线** |
| 新增指标 | `scripts/verify_code_quality.py` 新增第 4 指标 `os_system_count`（ast 级，注释行天然不计），基线 **5** |
| 顺带修 bug | `plugins/task_manager/process_network_total.py` 缺 `import yf`（必 NameError），已补 `sys.path` + `import core.yf as yf` |

## 二、关键决策（含取舍）

1. **否决「换成 `yf.execShell` 就交差」**。读了 `yf.py:106` 的 `sanitizeCmdScripts`，它只修脚本 CRLF，
   **不做注入消毒**，`execShell` 同样 `shell=True`。所以每处要么列表化、要么 `shlexQuote`，
   不能换原语糊弄（那是指标作弊）。
2. **管道类（`pv | mysql`）用 `shlexQuote` 逐段引用**（用户选定）——管道无法列表化，
   最小改动保持行为；`pwd/sock/bak_file/sync_db` 均为拼接进 shell 的变量，全部引用。
3. **撤回 `# os-system-ok` 豁免机制**。初版给 5 处加豁免标记→计数变 0，与用户拍板的
   「基线锁 ≈5」不一致，且这 5 处会**从计数里消失不可见**。改为如实计入基线=5，
   行内注释说明「为何必须保留」。
4. **`rm -rf` 一律改 `yf.removeDir`**（已有 `invalidPathReason` 拒绝非法路径），
   `mkdir/chown/chmod` 改 `os.makedirs` + `yf.safeExecShell` 列表参数；
   `pureftp` 的 `chown` 改 `shutil.chown`（顺带消除 macOS/BSD 的 `www.www` vs `www:www` 分支）。
5. ** `acme` 待审核插件**：`getDnsapiExportVar` 初版 `"="+值` 遇值内含 `"`/`$()` 即可注入，
   改为变量名正则校验 + `shlexQuote`。

## 三、验证记录

| 项目 | 命令 | 结果 |
|---|---|---|
| 全量门禁 | `PYTHONUTF8=1 python testsuite/run_all.py` | **174 模块 / 1295 用例 / 0 隔离 / 4 静态门禁 全绿** |
| os.system 实测 | `verify_code_quality.py` | 76 → **5**（全部为「必须经 shell」且无变量进入） |
| 检测器自证 | `--self-test` | 通过（四类均命中，注释行不计） |
| 语法 | `py_compile`（15 个改动 py） | 全部 OK |
| Shell | `bash -n`（`scripts/*.sh` + `scripts/install/*.sh` + `deploy.sh`） | 0 失败 |
| 棘轮基线 | `--update` | bare 172 / silent 516 / print 0 / **os_system_count 5** |
| 守卫用例 | `test_supply_chain_guards::test_16` | nosec 下限 `25 → 7`（B5 删了 23 处 `# nosec B605`，属用例自述的「确实是修好了某条」） |

## 四、发现与边界（不粉饰）

1. **`process_network_total.py` 另外还有一处隐患（未修，已确认非 bug）**：它被
   `task_manager_index.py:536` 用 `yf.getServerDir() + '/mdserver-web'` 拼路径拉起。
   实测 `deploy.sh:1539/1664/1969` 会创建 `/www/server/mdserver-web -> yufeng_panel` 软链接，
   故该路径**能工作**（与 mysql/mariadb 里的同类路径一致），不是缺陷。
2. **5 处保留的 `os.system`** —— 精确口径（前一份记录写得不准，此处更正）：
   - **3 处纯字面量、确实无任何变量进入 shell**：多级管道杀进程（`panel_tools.py:187`）、
     `bash <(curl -sSL https://linuxmirrors.cn/main.sh)`（`:322`，URL 常量）、
     `curl -Lso- bench.sh | bash`（`:326`，命令全字面量）；
   - **2 处拼接了服务端常量路径**（`:633` / `:685`）：
     `"cd " + yf.getPanelDir() + " && source bin/activate && python plugins/mysql/index.py ..."`。
     该值是面板自身安装目录（来自 `__file__` 推导），**不是用户输入**，因此不构成注入面；
     但「无变量进入 shell」这句话对这两处**不成立**，特此更正（审计指出）。
     若要彻底清零，需要改成 `yf.safeExecShell([...], cwd=...)` + 直接调 venv 解释器，
     但这会引入「venv 内 python 路径探测」的新不确定性，故本轮保留。
   它们不是命令注入面，但仍是供应链面（下载即执行），已登记（见 B6 同类问题）。
3. **服务端路径类（如 `bak_file`/`SSH_PRIVATE_KEY`）本次未做白名单校验**，只做了引用。
   若将来这些值变成外部输入，需再评估。



# 第 8 层「P1-2：C2 静默 `except: pass` 存量清理（web/core + web/admin）」

> 来源：`参考/20260928优化.md` §C2（H3.1）。
> 用户拍板（2026-09-29）：本轮清 `web/core` + `web/admin`；日志级别「按站点判断」
> （真异常→`yf.writeFileLog`，预期内→`logging.debug`）。
> 门禁基线：**174 模块 / 1295 用例 / 0 隔离 / 4 项静态门禁 全绿**

## 一、实测修正与交付

| 项 | 结果 |
|---|---|
| 文档口径偏差 | 文档说「裸 except 172 / 静默 518」，但**实测 `web/` 里裸 except = 0**；172 处裸 except 全在 `panel_task.py`(19) + `panel_tools.py`(4) + `plugins/`(149) |
| 本轮范围 | `web/core` 71 + `web/admin` 38 = **109 处 silent_except**，清零 |
| 基线变化 | `silent_except` **516 → 407**（−109，单调下调）；`bare_except` 172 不变（web/ 本就没有） |
| 新增 logger | `yf.admin` / `yf.plugin` / `yf.dashboard` / `yf.files` / `yf.system` / `yf.i18n` / `yf.resources` / `yf.core`；`yf.migrations` 补 `import logging`；`yf.orm` 复用已有 `log` |

## 二、关键设计（含取舍）

1. **「按站点判断」而非一刀切**：
   - 真异常（DB/IO/子进程/备份还原/审计落库失败）→ `yf.writeFileLog`，线上可查；
   - 预期内（探测/回退/清收/权限不足/第三方接口）→ `logging.debug`，不刷 `logs/debug.log`。
2. **判定型接口不改日志，而是重构去掉 `pass`**：`yf.isNumber` / `yf.isVaildIp` 里的
   `except ...: pass` 是**正常分支而非错误**，加日志会产生高频噪音。改为嵌套 `return False`，
   语义逐输入比对无差异（含 `½`/`٣`/`１２`/`fe80::1%eth0` 等边界，全部 OK）。
3. **`del RUN_CACHE[k]` + `except KeyError: pass` → `RUN_CACHE.pop(k, None)`**：
   行为等价、代码更短，顺带消掉 2 处静默 except。
4. **日志本体失败不得递归**：`userSafeError` / 500 处理里的「写日志」自身抛异常时退回模块 logger。

## 三、验证记录

| 项目 | 命令 | 结果 |
|---|---|---|
| 全量门禁 | `PYTHONUTF8=1 python testsuite/run_all.py` | **174 模块 / 1295 用例 / 0 隔离 / 4 静态门禁 全绿** |
| 语法 | `py_compile`（21 个改动 py） | 全部 OK |
| 计数 | `verify_code_quality.py` | silent 516→**407**；web/core+web/admin 残留 **0** |
| 棘轮基线 | `--update` | bare 172 / silent 407 / print 0 / os.system 5 |
| 等价性自检 | `isNumber`/`isVaildIp` 新老实现逐输入对比 | 全部 OK（无行为差异） |

## 四、边界（不粉饰）

本轮只动了 `web/core` + `web/admin`。剩余 silent_except 仍在：
`web/utils` 104 · `plugins/` 约 290 · `panel_task.py` 8；裸 except（172）全在
`panel_task.py`/`panel_tools.py`/`plugins/`，属后续批次。



# 第 9 层「P1-3：C7 静态资源去重 + N1 /metrics 探针 + 跨系统静态守卫」

> 来源：`参考/20260928优化.md` §C7；以及 `task.md` 第 3 层 H5.3 的 `/metrics` 预留。
> 用户拍板（2026-09-29）：`/metrics` 用 `thisdb.getOption('metrics_open', default='no')` 开关，
> 未开启返回 **404**（不暴露端点存在）；只暴露健康类指标。
> 门禁基线：**176 模块 / 1310 用例 / 0 隔离 / 4 项静态门禁 全绿**

## 一、交付内容

| 项 | 结果 |
|---|---|
| **C7** 删 `bootstrap-3.3.5` | `git rm -r web/static/bootstrap-3.3.5`（10 个文件 372K）。全仓引用扫描：`web/`+`plugins/` **0 命中**；`文档/jq升级3.7/jq升级3.7.md:175` 证实它是 3.4.1 迁移后的遗留目录 |
| **N1** `/metrics` | `web/admin/__init__.py` 新增路由：默认关闭（`metrics_open` 默认 `'no'`）→ `abort(404)`；开启后不需登录（同 `/healthz` 口径）；只出 `yf_up` / `yf_db_ok` / `yf_data_writable`，`text/plain; version=0.0.4`，`Cache-Control: no-store`；不回显版本/路径指纹 |
| 豁免接线 | 关站/安全入口豁免行改为 `request.path == '/healthz' or request.path == '/metrics'`（**保留 healthz 字面量**，不破既有 `test_25` 断言） |
| 新增守卫 | `testsuite/test_p1_misc_cleanup.py`（10 项：C7 目录/引用/动态拼接/单版本 + N1 路由/默认 404/豁免/Prometheus 格式/无指纹/只读） |
| 新增守卫 | `testsuite/test_cross_platform_guard.py`（5 项：索引无 CRLF / 全源文件声明 `eol=lf` / `.gitattributes` 根规则 / 无 UTF-8 BOM / 15 类安装脚本齐备且带 shebang） |

## 二、关键设计（含取舍）

1. **`/metrics` 未开启返回 404 而不是 403**：403 等于告诉扫描器「这里有个端点」，
   默认关闭的探针应该连存在性都不暴露。
2. **探针无鉴权但默认关闭**：与 `/healthz` 同理（抓取方常是独立监控进程），
   正因为无鉴权才必须默认关闭 + 显式开启，并在注释里写明需自建网络隔离。
3. **跨平台守卫查「索引 + 属性」而非工作区**：Windows 上 `w/crlf` 是正常现象
   （实测 4 个 `plugins/php/versions/*/install.sh`），只要 `i/lf` 且 `attr eol=lf`，
   Linux 检出就一定是 LF——这才是决定生产行为的证据（实测 1349/1349 源文件均 `eol=lf`）。
4. **刻意不做的两项跨平台检查**（写进用例 docstring 备案）：
   - 「硬编码反斜杠路径」扫描：实测 25 命中 **全为误报**（都是 SQL 转义单引号 `'\\''`）；
   - 「源文件必须可 UTF-8 解码」：实测 2 个历史文件不满足，不塞进门禁卡住所有人。

## 三、验证记录

| 项目 | 命令 | 结果 |
|---|---|---|
| 全量门禁 | `PYTHONUTF8=1 python testsuite/run_all.py` | **176 模块 / 1310 用例 / 0 隔离 / 4 静态门禁 全绿** |
| C7+N1 守卫 | `testsuite/test_p1_misc_cleanup.py` | 10/10 |
| 跨平台守卫 | `testsuite/test_cross_platform_guard.py` | 5/5 |
| 删除范围确认 | `git ls-files web/static/bootstrap-3.3.5`（删前） | 10 个文件，精确路径无通配符 |
| 语法 | `py_compile`（`web/admin/__init__.py` + 2 个新用例） | OK |

## 四、发现与边界（不粉饰）

1. **根目录 `fonts.css` 是 UTF-16LE**（BOM `FF FE` + NUL 字节），且在仓库根而非 `web/static/`。
   属仓库卫生问题（疑似误提交），**本次未动**（需你先定“删还是转码”）。
2. **`web/static/codemirror/addon/search/search_backup.js` 含非法 UTF-8 字节**，
   从命名看是 `search.js` 的备份副本（同一目录下 `search.js` 才是被引用的那个）。
   同上，**本次未动**，仅登记。
3. **`/metrics` 未做 UI 开关**：只支持 `thisdb.setOption('metrics_open','yes')`；
   若需要图形开关，属后续小改动（会牵涉 i18n 6 语言）。



# 第 10 层：P1 批次收尾验证（本轮终态）

> 用户2026-09-29 圈定本轮只做 **P1（安全与质量收口）**；本层为逐项复核与归档。

## 一、任务闭环

| Task | 内容 | 状态 |
|---|---|---|
| task-1 | 存量盘点 + 范围圈定（用户拍板 P1） | ✅ |
| task-2 | P1-1 B5 `os.system` 收口（76 处 → 5） | ✅ |
| task-3 | P1-2 C2 静默 except 清理（web/core + web/admin 109 处） | ✅ |
| task-4 | P1-3 C7 删 `bootstrap-3.3.5` + N1 `/metrics` + 跨平台守卫 | ✅ |
| task-5 | 收尾验证 + task.md + 记忆归档 | ✅ |

## 二、最终验证证据（逐项实测）

| 证据项 | 命令 | 结果 |
|---|---|---|
| 全量门禁 | `PYTHONUTF8=1 python testsuite/run_all.py` | **176 模块 / 1310 用例 / 0 活跃隔离 / 4 静态门禁 全绿**（48s） |
| 代理单一真源 | `python testsuite/run_all.py -k deploy_bootstrap` | 11/11（含 `test_04` 代理一致 + 内嵌副本漂移 + `test_11` 测速表派生） |
| 15 类系统安装脚本 | `bash -n scripts/install/*.sh` | 15/15 通过，0 失败 |
| 全部 `.sh` 语法 | `testsuite/test_shell_syntax.py`（已挂门禁） | 全库 `.sh` 均过 `bash -n` |
| 代码质量棘轮 | `python scripts/verify_code_quality.py` | bare 172 / silent 407 / print **0** / os.system **5**，均未恶化 |
| 新增守卫 | `test_p1_misc_cleanup.py`(10) + `test_cross_platform_guard.py`(5) | 15/15 |
| i18n 静态门禁 | `run_all.py --static` | 11 项全绿 |

## 三、三条硬约束的逐项交代

### 1）适配全部 15 类受支持系统
- 本轮所有改动均为跨平台写法：新增/改写均用 `yf.safeExecShell([...])` 列表参数、
  `os.makedirs`、`shutil.chown`、`yf.shlexQuote`，**未新增任何平台特定分支**；
- 新增 `test_cross_platform_guard.py`：索引无 CRLF、1349 个源文件均带 `eol=lf` 属性、
  `.gitattributes` 根规则存在、无 UTF-8 BOM、15 类安装脚本齐备且带 shebang；
- `pureftp` 的 chown 从「`www.www` / `www.staff` 手写分支」改为 `shutil.chown`，
  顺带消除了平台分支。
- **未做真机逐发行版实跑**（已与你约定以静态守卫 + `bash -n` + testsuite 为证据）。

### 2）SQLite 自愈升级（复用 `schema_version`）
- **本轮没有新增/修改任何表结构**（B5/C2/C7/N1 均不碰 DB）；
- 已有 `panel_session` / `panel_login_failure` / `panel_audit` 等新表仍走原自愈路径：
  结构对齐每次启动幂等跑，数据迁移按 `schema_version` 只跑一次；
- 回归：`run_all.py -k db_migration_selfheal`（16 项，含升级路径 heredoc 真跑）全绿。

### 3）中国地区代理可用
- 未新增任何硬编码代理；`scripts/proxies.list` 仍是唯一真源，
  `test_04` 锁死「文件 rt 子集 == `deploy.sh` 内嵌副本」；
- 本轮改动的 shell 部分不涉及代理（`install/*.sh` 的 loader 未动）；
- 本地测速/代理回退逻辑（`_load_github_proxy_list` / `_GH_PROXY_LIST`）未动。

## 四、本轮结束后仍存在（已登记，不在 P1 范围）

| 项 | 实测 |
|---|---|
| C2 余额 | silent_except 407（`web/utils` 104 / `plugins/` ~290 / `panel_task.py` 8）；bare_except 172（全在 `panel_task.py`/`panel_tools.py`/`plugins/`） |
| B5 余额 | 5 处 `os.system`：3 处纯字面量；2 处拼服务端常量路径 `yf.getPanelDir()`（非用户输入，无注入面，已注释理由并计入基线 5） |
| C1 | `web/core/orm.py` 仍 `return ex`（595 调用点，高风险，单独立项） |
| D1/D2 | 审计流水 UI / 远端转发未接（后端已就绪） |
| 外部依赖项 | A1/A2/B6/C4/C6/D6/E1/E2/E3（需真机/CI/联网/产品决策） |
| 新发现 | 根目录 `fonts.css`(UTF-16LE)、`search_backup.js`(非法 UTF-8) 仓库卫生问题 |

**设计一致性结论**：本轮所有改动都满足「向上不新增硬编码代理、不新增平台分支、
不改表结构（因此不涉及自愈路径变更）、不降低任何门禁强度」四条约束。



# 第 11 层「C2 批次 2：web/utils + web/thisdb」

> 审计驳回指出目标要求「所有可本地自动化验证的已知问题」，P1 只是第一批；
> 用户授权「全量推进到底」。本层为批次 2。
> 门禁基线：**176 模块 / 1310 用例 / 0 隔离 / 4 静态门禁 全绿**

## 一、交付

| 项 | 结果 |
|---|---|
| 范围 | `web/utils` 104 + `web/thisdb` 5 = **109 处** silent_except，全部清零 |
| 基线变化 | `silent_except` **407 → 298**（−109，单调下调）；`bare_except` 172 不变（这两目录本无裸 except） |
| 新增 logger | `yf.thisdb.crontab` / `yf.thisdb.firewall` / `yf.task` / `yf.firewall` / `yf.system` / `yf.system.update` / `yf.system.stats` / `yf.ssh` / `yf.ssh_terminal` / `yf.page` / `yf.urlguard` / `yf.fcgi` / `yf.crontab` / `yf.file` / `yf.plugin` / `yf.site` |
| 重点文件 | `site.py` 25 / `file.py` 21 / `plugin.py` 21 / `crontab.py` 15 / `task.py` 5 / 其余 12 文件 |

## 二、分级口径（沿用第 8 层）

- **真异常**（站点配置 rename/symlink/删除失败、PID 文件写入失败、任务启动失败、
  插件安装/版本文件写入失败、acme.sh 安装失败、user.ini 清理失败）→ `yf.writeFileLog`；
- **预期内**（psutil 进程已退出、pid 文件缺失、`chattr` 权限不足、缓存读写、
  `os.chmod/chown` 非 root、目录扫描、自适应分页上限探测、ffi 日志写入）→ `logging.debug`。

## 三、验证

| 项目 | 结果 |
|---|---|
| `py_compile`（16 个改动文件） | 全部 OK |
| `verify_code_quality.py` | silent 407→**298**；`web/` 与 `web/thisdb` 残留 **0** |
| 全量门禁 | **176 模块 / 1310 用例 / 0 隔离 / 4 静态门禁 全绿** |
| 基线 | `--update` 已落：bare 172 / silent 298 / print 0 / os.system 5 |

## 四、发现（已登记，未修）

1. **`web/utils/setting.py:194` 与 `web/utils/site.py:2981` 的 acme.sh 安装命令写错了**：
   `yf.execShell("curl -sS curl https://get.acme.sh | sh")` —— 多了一个 `curl` 参数，
   curl 会把 `curl` 当成 URL 去请求，**安装实际不会成功**（且属「下载即执行」供应链面）。
   本轮只把静默 `pass` 改成 `writeFileLog`（让失败可见），**命令本身未改**（涉及安装流程，单独评估）。
2. `web/utils/crontab.py` 顶部有 **重复导入** `from utils.urlguard import validate_url`（同一行出现两次）。



# 第 12 层「C2 批次 3 + 4：panel_*.py 与 plugins/ 全量归零」

> 用户授权「全量推进到底」。其中 plugins/ 已从 436 处机械清理。
> 终态门禁：**176 模块 / 1310 用例 / 0 隔离 / 4 静态门禁 全绿**

## 一、交付（C2 全部完成）

| 批次 | 范围 | silent | bare |
|---|---|---|---|
| 批次 1 | `web/core` + `web/admin` | 516→407 | 172（不变） |
| 批次 2 | `web/utils` + `web/thisdb` | 407→298 | — |
| 批次 3 | `panel_task.py` + `panel_tools.py` | 298→287 | 172→149 |
| 批次 4 | `plugins/`（47 个文件） | 287→**0** | 149→**0** |

**终态：`bare_except = 0`、`silent_except = 0`、`print_in_web = 0`、`os_system_count = 5`**

改动规模：97 个文件；新增模块 logger 约 60 个（`yf.<plugin>` 命名）。

## 二、关键工程方法（值得回看）

一次性手改 436 处不现实，因此写了临时工具 `test/qfix.py`（收尾时删除）自动生成
「唯一 oldText + newText」编辑对，再由 `edit` 工具落地。工具踩过 3 个坑：

1. **相邻嵌套 except 会产出重叠编辑** → 改为「按变更行聚类 + 唯一性扩展 + 强制不重叠」；
2. **裸 `except:` 的 body 若是 `return`/赋值，不能被日志覆盖**（否则吞掉控制流）→ 仅 `pass` body
   才替换，否则**在 body 前插日志**；
3. **`except ValueError: pass` 不能直接用 `_e`**（未绑定）→ 正则补 `as _e`；已有 `as X` 的沿用 X。

另一个真实事故：`plugins/clean/clean_executor.py` 的 `import core.yf as yf` 在 `try:` **内部**，
用无锚点旧文本插入 logger 导致缩进错位 → 语法错（已修）。教训：
**header 锚点必须限定顶格（`^import core.yf as yf`）**，事后逐个 `py_compile` 才抳得住。

## 三、验证

| 项目 | 结果 |
|---|---|
| `py_compile`（94 个改动 py） | 0 失败 |
| `verify_code_quality.py` | **bare 0 / silent 0** / print 0 / os.system 5 |
| 全量门禁 | **176 模块 / 1310 用例 / 0 隔离 / 4 静态门禁 全绿** |

## 四、边界（不粉饰）

1. **机制是「加日志」，不是「修正业务逻辑」**：本次只把静默 `pass` 改成具名异常 + `debug` 日志，
   并保留原有控制流；插件里真正「吞异常后继续用错误返回值」的**语义缺陷仍需逐个排查**，
   不在本次机械清理范围内（文档 §C2 也只要求先清静态存量）。
2. **日志级别以 `debug` 为主**（插件探测/解析/回退均属预期内），默认不会输出；
   排查时需临时调高 `yf.*` 日志级别。



# 第 13 层「C1：ORM/DB 异常语义（方案 B 兼容层，核心层）」

> 用户拍板：采用 **方案 B（兼容层 + 新 Strict 接口）**；本轮只做 **核心层 + 守卫**，
> 8 个调用点文件按 `yf.py → gitea → sphinx → postgresql → data_query → mariadb → mysql`
> 顺序**分次**迁移（不在本轮）。
> 门禁：**177 模块 / 1321 用例 / 0 隔离 / 4 静态门禁 全绿**

## 一、调用点依赖矩阵（实测）

| 层 | 实现 | 失败时旧返回 | 文件数 | 调用点 | 其中丢弃返回值 |
|---|---|---|---|---|---|
| A 外部库 | `web/core/orm.py::ORM` | **异常对象**（truthy） | 8 | 470（`execute` 161 / `query` 192 / `find` 约 100+） | **180** |
| B 面板 SQLite | `web/core/db.py::Sql` | `"error: ..."` 字符串 | 29 | 125 | 53 |

A 层 8 个文件：`plugins/mysql/index.py`（189）、`plugins/mariadb/index.py`（180）、
`plugins/data_query/sql_mysql.py`（41）、`plugins/postgresql/index.py`（29）、
`web/core/yf.py`（15）、`plugins/sphinx/class/sphinx_make.py`（11）、
`plugins/gitea/index.py`（3）、`plugins/mariadb/scripts/test.py`（2）。

三条旧故障语义：① 连接失败 → 错误字符串；② SQL 错 → **异常对象**（`if orm.execute(...)` 恒真）；
③ 正常 → 结果。额外缺陷：`find()` 会在异常对象上 `len()` → **TypeError**。

## 二、本层交付

| 项 | 内容 |
|---|---|
| `ORMError` | 带 `sql` / `params` / `orig` 字段；**继承 Exception**（关键：已有 5 处 `isinstance(res, Exception)` 判断，继承后 100% 兼容） |
| A 层旧 API | `execute/query` 保留旧返回形状，但失败时 **ERROR 日志 + 返回 `ORMError`**（不再静默）；`find()` 遇错误对象直接返回它（不再 `len()` 崩） |
| A 层新 API | `executeStrict` / `queryStrict` / `findStrict`：连接失败与 SQL 错**一律抛 `ORMError`** |
| `SqlError` | B 层新异常；`Sql.executeStrict` / `queryStrict` / `findStrict` 失败即抛 |
| B 层旧 API | **完全不改**（仍返回 `"error: ..."`）——调用面 29 文件/125 处，一次改语义不可审查 |
| 守卫用例 | `testsuite/test_orm_error_semantics.py`（11 项）：三路径 × 旧/新 API + `ORMError` 继承红线 + `find()` 回归 + 静态守卫（不得再有无日志的 `return ex`） |

## 三、验证

| 项目 | 结果 |
|---|---|
| 新用例 | `test_orm_error_semantics.py` **11/11**（本机无 pymysql，注入假模块真跑，非 skip） |
| 全量门禁 | **177 模块 / 1321 用例 / 0 隔离 / 4 静态门禁 全绿** |
| `py_compile` | `orm.py` / `db.py` / 新用例 均 OK |

## 四、遗留（已登记，按用户「调用点分次」决定）

**180 处丢弃返回值的调用点仍是「truthy 陷阱」**：现在失败会打 ERROR 日志、不再静默，
但调用方若只做真值判断，依旧会把 `ORMError` 当成功。彻底消除需要逐文件改用
`*Strict` + 显式 `try/except`，集中在 `mysql/index.py`（105+75）、`mariadb/index.py`（78）——
这两个文件正是同步/备份主线，**无真机可测**，故按用户决定不在本轮动。

# 第 14 层「task-10：其余本地可验证项（H4.1 / I2 / I4 / 库卫生）」

| 项 | 结论 | 证据 |
|---|---|---|
| **H4.1 `requirements.lock`** | **需联网**（本机离线无法 `pip-compile --generate-hashes`）→ 改为 **CI 生成** | `.github/workflows/security-scan.yml` 新增 `lock` job；产物 `requirements-lock` artifact；新增守卫 `testsuite/test_dependency_lock_and_hygiene.py` 锁死「**锁文件不得取代 `requirements.txt`**」（真正安装入口是 `scripts/lib.sh::install_requirements`，带 PIPSRC 镜像回退） |
| **I2 发布模板** | **已本地闭环**（实测已完成） | `RELEASE_TEMPLATE.md` 含「变更类型 / 升级说明 / 回滚方法 / 发布前自检」；`release.yml:143` `body_path` 引用；既有守卫 `test_edition_layering.py` 已覆盖 |
| **I4 商业版分层** | **已本地闭环**（实测已完成） | `web/core/edition.py` + `web/pro/`；`test_edition_layering.py` 12 项全绿 |
| **库卫生** | **可本地验证 → 已修** | 根目录 `fonts.css`（UTF-16LE，位置也异常）与 `web/static/codemirror/addon/search/search_backup.js`（`search.js` 旧备份）实测**全仓零引用**，已 `git rm`；守卫断言两者不存在且无新引用 |

验证：新守卫 5/5；全量门禁 **178 模块 / 1326 用例 / 0 隔离 / 4 静态门禁 全绿**。



# 第 15 层：本轮终态与遗留（收尾）

## 一、终态指标

| 指标 | 起点 | 终点 |
|---|---|---|
| `bare_except` | 172 | **0** |
| `silent_except` | 518 | **0** |
| `print_in_web` | 45 | **0** |
| `os_system_count` | 76（实测） | **5**（均注释理由） |
| 门禁用例 | 176 模块 / 1310 用例 | **178 模块 / 1326 用例 / 0 活跃隔离 / 4 静态门禁** |

## 二、三条硬约束的最终证据

| 约束 | 证据 |
|---|---|
| 适配 15 类系统 | `test_cross_platform_guard.py` 5/5（索引无 CRLF、1349+ 源文件带 `eol=lf`、`.gitattributes` 根规则、无 BOM、15 类安装脚本齐备且带 shebang）；`test_shell_syntax.py` 全库 `.sh` 过 `bash -n` |
| SQLite 自愈升级 | `test_db_migration_selfheal.py` 16/16（含升级路径 heredoc 真跑）；本轮**未改任何表结构**，自愈路径未动 |
| 中国地区代理 | `test_deploy_bootstrap.py` 11/11（`test_04` 代理单一真源 + 内嵌副本一致；`test_11` 测速表由列表派生） |

## 三、遗留（本轮未做，已逐项登记）

| 项 | 原因 |
|---|---|
| **C1 调用点迁移（180 处丢弃返回值）** | 用户拍板「调用点分次」；现失败已打 ERROR 日志不再静默，但仍保留 truthy 语义。集中在 `mysql/mariadb` 同步备份主线，无真机可测 |
| A1 签名强制开关翻转为 1 | 需首个签名 Release + 真机验证 |
| A2 首个签名 Release | 需推 tag / CI 实跑 |
| B6 curl\|bash 信任根 | 需 A2 配套；改文档只能做一半 |
| C4 `requirements.lock` 入库 | 需联网生成（已由 CI `lock` job 代劳，待维护者取产物提交） |
| C6 `--coverage` / C7 前端构建 | 需 `coverage` / esbuild（本机无） |
| D1/D2 审计 UI / 远端转发 | 后端已就绪，前端与「日志离开本机」属新功能 |
| D3 授权/激活/计费；D4 RBAC；D5 插件签名；D6 多 worker | 产品决策 / 压测基线 |
| E1 `.i18n.bak`；E2 zabbix sql.gz；E3 `.git` 体积 | 刻意保留 / 待用户确认 / 禁止改写历史 |

---

# 第 16 层「小 bug 修复（用户点名 4 项 + 同族 10 处同步链路）」

## 一、用户点名 4 项的实测结论

| 点名项 | 实测结论 | 处理 |
|---|---|---|
| acme.sh 安装命令多一个 `curl` | **真 bug**（`curl -sS curl <url>` 会把 `curl` 当第一个 URL） | ✅ 修为 `curl -fsSL https://get.acme.sh \| sh`（`setting.py` / `site.py`），顺带把 `site.py` 的 `--set-default-ca` 由 `execShell(拼接串)` 改为 `safeExecShell([...])` |
| `web/utils/crontab.py` 重复导入 | **误报**：两处 `from utils.urlguard import validate_url` 分属 `_is_private_url()` 与 `_validate_to_url()` **两个不同函数**的局部导入（避开循环导入的保守写法），**不是同一作用域重复** | 不改代码，仅更正记录 |
| `plugins/php/versions/{53,54,55,56}/install.sh` CRLF | **无需处理**：git 索引为 `i/lf` 且属性 `eol=lf`，Linux 检出必为 LF；仅本机工作区 CRLF | 不改 |
| `task_manager` 网络统计启动路径 | **真脆弱**：`yf.getServerDir() + '/mdserver-web'` 依赖 deploy.sh 建的兼容软链，自定义安装目录时不存在 | ✅ 改用 `yf.getPanelDir()`；另修 `pid` 读取（`readFile` 失败返 `False` 时 `'/proc/' + False` 会 TypeError）+ 启动命令路径 `shlexQuote` |

## 二、顺带发现：JS 式拼接写进了 Python 字符串字面量（同族 10 处）

**根因**：把 JS 的 `" + x + "` 拼接写法直接写进了 Python 单引号字符串里。
`getSPluginDir()` 甚至直接把字面量当返回值：

```python
def getSPluginDir():
    return '" + yf.getPanelDir() + "/plugins/' + getPluginName()
```

于是发出去的命令成了 `cd " + yf.getPanelDir() + " && ...`：`cd` 必然失败、`&&` 短路 →
**主从同步链路成片不可用**（命令要么走 `ssh.exec_command` 到远端，要么回给前端执行）。

| 文件 | 处数 | 说明 |
|---|---|---|
| `plugins/mysql/index.py` | 5 | `getSPluginDir()` 定义 + `get_master_rep_slave_user_cmd`×2 + `dump_mysql_data` + `sync_database_repair` + `do_full_sync` |
| `plugins/mariadb/index.py` | 3 | `get_master_rep_slave_user_cmd_ssh` + `get_master_rep_slave_user_cmd` + `do_full_sync` |
| `plugins/postgresql/index.py` | 2 | `slaveSyncCmd`（回给前端）+ `get_master_rep_slave_user_cmd`（远端） |
| `plugins/mongodb/index.py` | 3 | 仅在 **docstring 示例**里，只影响文档 |
| `plugins/task_manager/task_manager_index.py` | 1 | `exe_keys` 字典键，字面量永远不命中 → 面板插件进程漏标 |

**同时修掉的连带缺陷**：
- `plugins/mysql/index.py:1890` `importDbBackupProgress` 的面板根仍是 `getServerDir()+'/mdserver-web'` → 改 `getPanelDir()`。
- `plugins/mariadb/index.py::getArgs()` **没有 JSON 分支**（mysql 有）：负载加上正确引号后反而会解析失败（`args['sign']` → KeyError）。已按 mysql 对齐补上 JSON 分支，并把旧分支的 `t[1]` 直取改为长度校验（无 `:` 时不再 IndexError）。

**修复后的命令形式**（演示）：

```
cd /www/server/yufeng_panel && source bin/activate && python3 /www/server/yufeng_panel/plugins/mysql/index.py do_full_sync '{"db": "demo1", "sign": "abc"}'
```

三处（`cd` 目标 / 脚本路径 / JSON 负载）均经 `yf.shlexQuote`，负载作为**单个 argv** 到达，
接收端 `json.loads` 能正常解析；同时消除了 mariadb `fullSyncCmd` 原先的**命令注入面**（db/sign 未校验）。

## 三、死文件仅登记不删（用户拍板）

`plugins/mysql/index_mysql.py` 与 `plugins/mariadb/index_mariadb.py` 含同样的 `getSPluginDir()` 坏定义，
但经全仓扫描（`web/`+`plugins/`+`testsuite/`）**零引用**。按用户拍板**只登记不删**，已写入守卫例外清单并由 `test_03` 持续验证「仍为零引用」。

## 四、新增守卫：`testsuite/test_panel_cmd_path_guard.py`（17 项）

| 组 | 项 | 内容 |
|---|---|---|
| JS 拼接 | 1~3 | 字面量里不得出现 `" + 函数调用(`；例外清单不得长大；两个死文件仍零引用 |
| acme | 4 | 安装命令恰 1 个 URL、带 `-f`、不得把 `curl` 当参数 |
| 面板根 | 5 | 不得出现 `+ '/mdserver-web'` 拼接（进程匹配类如 `.find('mdserver-web/plugins')` 不误伤） |
| 脚本/负载引用 | 6~8 | 同步命令串的脚本路径与负载必须 `shlexQuote`；`getSPluginDir()` 必须返回真实路径 |
| mariadb 行为 | 9~11 | **真跑** `getArgs()`：JSON 负载解析、旧写法不崩、无 `:` 不 IndexError |
| task_manager | 12~15 | 启动路径用 `getPanelDir()`；pid 读取容错；路径引用；`exe_keys` 运行时计算 |
| shell 往返 | 16~17 | 用 `shlex.split` 模拟 POSIX shell：负载作为单 argv 到达；注入字符不被拆成独立命令 |

**变异自证 4/4 全部命中**（回退 JS 字面量 / 回退 `curl -sS curl` / 回退 `mdserver-web` 拼接 / 去掉 mariadb JSON 分支 → 守卫均 FAIL；字节级快照还原，无残留）。

## 五、验证与边界

- 全量门禁：**179 模块 / 1343 用例 / 0 隔离 / 4 静态门禁 全绿**；代码质量棘轮未动（bare 0 / silent 0 / print 0 / os.system 5）。
- `py_compile` 8 个改动文件 OK；所有改动文件保持 **LF**（无 CRLF 污染）。
- **不能替代的验证**：主从同步真实链路（需 MySQL/PostgreSQL/MongoDB + 远端主机）。本轮只保证「命令串构造正确 + 参数解析正确」，已在用例 docstring 与守卫文件头明确声明。
- **保留未改（需真机确认）**：`task_manager`/`postgresql`/`sphinx`/`varnish` 里的 `cmdline.find('mdserver-web')` 与 `ps -ef | grep -v mdserver-web` 仍是**字符串匹配**：面板改名为 `yufeng_panel` 后，这些匹配可能不再命中（轻则分类显示不准，重则过滤失效）。**不能靠静态判断，需真机看进程表**，留作下一轮。
- **临时脚本事故记录**：变异自证首次用 `read_text()`/`write_text()` 改写插件文件，未加 `finally` 还原 + Windows 下静默把全文转成 CRLF。已修为「字节快照 + `finally` 还原 + `newline='\n'`」。教训：**擅自改写业务文件的验证脚本必须有恢复保障**。

---

# 第 17 层「C5 巨型文件：安全 / 可靠性 / 性能优化（用户拍板范围）」

## 零、侦察结论（先纠正前提）

| 文件 | 行数 | 顶层定义 | 真实性质 |
|---|---|---|---|
| `plugins/mysql/index.py` | 5288 | 163 函数 | CLI **脚本入口**（`__main__` 196 分支分发） |
| `plugins/mariadb/index.py` | 4398 | 141 函数 | 与 mysql **136 同名函数，其中 95 已漂移** |
| `web/utils/site.py` | 3199 | 1 个 `sites` 类（119 方法）+ 2 模块函数 | 被 13 处 `from utils.site import sites` 使用 |
| `web/core/yf.py` | 3206 | 197 函数 | **198 符号 / 7682 处 `yf.X` 调用点**，80 函数内部互调 |

**结论：按行数切分本身几乎不产生安全/可靠/性能收益（只省几 ms 导入解析）。真收益在切分过程中暴露的结构问题。**

## 一、用户拍定范围

| 维度 | 拍定 | 内容 |
|---|---|---|
| 安全+可靠性 | 都修 | 对齐 `mariadb::delDb` 到 mysql 版（pymysql 直连 + 超时 + 1008 容错 + `find` 空值保护）；`mysql::setDbBackup` 补库名白名单；不再丢弃返回值 |
| 性能 | 两项都做 | my.cnf 读取加 mtime 失效缓存；`delDb` 的 N 次 `DROP USER` 合并为单条 |
| 结构 | 只拆 yf.py | `web/core/yf/` 包 + `__init__.py` 完整重导出，7682 调用点零改动 |

## 二、实施清单

- [x] A1 `mariadb::delDb` 对齐 mysql（含 `find` 空值保护 + 友好报错）
- [x] A2 `mariadb::getSocketFile` 修无守卫导致的 `TypeError`/`AttributeError`
- [x] A3 `mariadb::getDbPort` 补守卫（同上）—— 另发现 mysql 侧 `getShowLogFile/getMyDbPos/getMyPort/getAuthPolicy` 同样无守卫，一并收口
- [x] A4 `mysql::setDbBackup` 补库名白名单
- [x] A5 `mariadb::setDbBackup` 不再丢弃 backup 输出（原无条件返回成功）
- [x] A6 两插件 `delDb`：单条 `DROP USER` 合并 + 用户名/Host 白名单
- [x] B1 两插件 my.cnf 读取缓存（mtime+size+读取实现 三重 key）
- [x] C1 `web/core/yf.py` → `web/core/yf/` 包（保留猴补丁语义）
- [x] T1 新增守卫用例（加固对齐 + 猴补丁语义 + 符号等价）
- [x] V  全量门禁 + 三约束证据 + `task.md` 收尾

## 三、实施结果

### 3.1 A/B：安全 + 可靠性 + 性能（两个数据库插件）

| 项 | 改前 | 改后 |
|---|---|---|
| `mariadb::delDb` | 30 行：ORM + 字符串拼 SQL + **丢弃 `execute()` 返回值** + `find['accept']` 直接下标 | 105 行：pymysql 直连 + DictCursor + `connect_timeout=5`/`read_timeout` + `1008` 容错 + `if not find` 友好报错 + 超时重启重试 |
| `mysql::delDb` | 本地 1 条 + 每 Host 1 条 `DROP USER`（N 次往返）；用户名/Host 直拼字面量 | 单条 `DROP USER 'u'@'h1','u'@'h2'`（不用 `IF EXISTS`，兼容 5.5/5.6）；`_dropUserTargets()` 白名单化 |
| `mysql::setDbBackup` | 无库名校验 | 补 `^[\w\.-]+$` 白名单（与 mariadb 对齐） |
| `mariadb::setDbBackup` | `p.communicate()` 丢弃 + **无条件返回成功** | 检查 `returncode` 与「备份失败」字样，失败必报错 |
| my.cnf 读取 | 每个 getter 各自 `yf.readFile(getConf())` + 裸 `re.search`（mysql 29/5/12 次、mariadb 27/3/10 次） | 统一 `_readCnf()`（**路径+mtime_ns+size+`yf.readFile` 实现** 四元组作 key）+ `_cnfValue()`；文件一改立刻失效，绝不返回旧值 |
| mariadb 10 个 my.cnf getter | `re.search(rep, content)` + `tmp.groups()` 无守卫 → my.cnf 缺失抛 `TypeError`、无该项抛 `AttributeError` | 全部走 `_cnfValue(pattern, default)`，永不抛异常 |

**新增守卫** `testsuite/test_db_plugin_hardening.py` **18 项**：AST 扫「my.cnf 读后未判空即 re.search」（两插件 0 残留）、缓存命中/失效/stat 失败语义、`_dropUserTargets` 注入拦截、两插件 `delDb` 加固口径逐项比对、真跑 `mariadb::setDbBackup` 失败路径。**变异自证 4/4 命中**。

**过程中抓到的自造 bug**：`mysql::setDbBackup` 内部有局部 `import re`，导致我新加的 `re.match` 触发 `UnboundLocalError`（`re` 被视为局部名）—— 已删掉那个冗余的局部导入。

### 3.2 C：`web/core/yf.py` → `web/core/yf/` 包

**形态**：`__init__.py` 3206 → **1078 行**（门面：模块级状态 + 44 个必须留驻的函数），外迁 **153 个函数 / 约 2333 行**到 10 个子模块（138~492 行）。

```
web/core/yf/
  __init__.py  1078 行   模块级状态 + 被补丁符号 + 枢纽函数 + 重导出
  panel.py      492 行   面板任务 / 网站操作 / 通知
  net.py        430 行   HTTP 池 / 证书 / IP / SSH
  system.py     380 行   os / 信息 / 页面 / json 工具
  fileio.py     286 行   文件读写 / 备份 / 大小
  shell.py      278 行   命令执行 / 权限 / 进程
  security.py   245 行   口令 / 加解密 / RSA
  textutil.py   236 行   时间 / 字符串 / 数字
  log.py        219 行   日志 / 审计 / CLI 输出
  paths.py      163 行   目录 / 端口 / 路径
  github.py     138 行   代理列表 / 下载 / 测速
```

**猴补丁语义怎么保住的**（拆包最大的静默风险）：

* 实测有 **21 个符号**被测试补丁过，两类机制都要算：`yf.X = ...` **和** `patch.object(yf, 'X')` / `patch('core.yf.X')`（第一版只扫了前者，全量门禁直接红 40 项）。
* 这 21 个符号**定义一律留在 `__init__.py`**（这样 `yf.X` 才是被替换的那个对象）；
* 子模块里对它们的调用一律走**运行时经包解析的 shim**（`_pkg().X(...)`），而不是 `from . import X`（静态导入会让补丁失效，产生「设了补丁却没测到」的假绿）；
* 子模块之间**不互相 import**，统一 `from . import <name>` 经包命名空间取，导入顺序由 codemod 按拓扑序生成，从根上排除循环导入。

**其他必须留驻 `__init__.py` 的三类函数**（codemod 自动识别并打印理由）：

1. 被补丁的 21 个符号；
2. 有 `global X` 重绑定语句的 7 个（`fixCrlf`/`getGithubProxyInfo`/`getLanguage`/`getAesKey`/`_get_http_pool`/`opWeb`/`notifyMessageTry`）—— 外迁后重绑定的是子模块的名字，与包内读数分叉；
3. 模块级语句在导入期直接调用的（`_load_github_proxy_list`/`_proxy_display_name`，用于 `_GITHUB_PROXY_LIST` 顶层求值）；
4. 读取被补丁**模块级状态** `_PANEL_ROOT_DIR` 的函数（`getRunDir`/`getRootDir`/`getFatherDir`）；
5. 被其它模块引用、且处于循环依赖环里的**枢纽**函数（`readFile`/`writeFileLog`/`writeLog`/`M`/`checkPid` 等）—— 提升到门面即打破环，比「把整个环的模块合并」好得多（试过后者：一次环就把 10 个模块并成 1 个，拆包直接退化）。

**搬迁工具** `scripts/tools/split_yf_module.py`（保留供审阅，带 `--dry-run` / `--restore`）：只按 AST 行号切片，**不改写任何函数体**；写盘前打印完整计划，写盘后做三重自检（`py_compile` + **未解析全局名静态扫描** + **符号等价对比**）。

### 3.3 顺带修掉的 3 个原文件潜伏 bug（静态自检抓出）

`split_yf_module.py` 的「未解析全局名」检查（symtable）在搬迁后报出 3 个 `NameError` —— 复核备份确认**都是原 `web/core/yf.py` 里就存在的**，不是搬迁造成：

| 位置 | 问题 | 处理 |
|---|---|---|
| `requestFcgiPHP` | 调用了不存在的 `url_encode` → `pdata` 为 dict 时必 500 | ✅ 改 `urllib.parse.urlencode`（`load_url_public` 内部用 `StringIO`，故不 `.encode()`） |
| `tgbotNotifyObject` | 引用未定义的 `app_token` → 必 500 | ✅ 改 `t['app_token']`（与 `tgbotNotifyChatID` 的 `t['chat_id']`、`notify_tgbot.py` 同源） |
| `getFpmAddress` | 引用未定义的 `bind` → `NameError` 被外层 `except` 吞掉，于是「php-fpm 监听 TCP」时静默返回 unix socket 路径（连不上） | ✅ 补回丢失的参数 `bind=False`（保持原 if/else 结构）。**已核实** `fcgi_client.FCGIApp::_getConnection` 对 tuple 走 `socket.create_connection`，即返回元组是有意设计 |

### 3.4 新增/迁移的守卫

| 用例 | 项数 | 内容 |
|---|---|---|
| `testsuite/test_db_plugin_hardening.py` | 18 | A/B 的加固口径与缓存语义 |
| `testsuite/test_yf_package_contract.py` | 13 | 包形态、`_PANEL_ROOT_DIR`、重导出可解析、符号数下限、**补丁语义端到端**（补 `yf.getPanelDir` → `net.getLocalIp` 读到被补目录；补 `isAppleSystem`+`execShell` → `paths.getAcmeDir` 走 macOS 分支）、子模块不得静态导入被补符号、shim 不得进重导出清单、**补丁集新鲜度**（testsuite 里新出现的补丁目标未登记即红灯） |
| `testsuite/_yf_pkg.py`（新助手） | — | 兼容「单文件 / 拆包」两形态的源码读取；已登记进 `test_repo_contract` 白名单 |
| 6 个按路径读 `web/core/yf.py` 的守卫 | — | 改为经 `_yf_pkg.resolve_text()` 读**包内源码拼接**，保证拆包后仍覆盖同一批代码：`test_deploy_bootstrap` / `test_p3_ssrf_and_transport` / `test_path_guard` / `test_plugin_status_detection` / `test_site_delete_fix` / `test_supply_chain_guards` |
| `plugins/mariadb/lang/*.json`（6 语言） | 2 键 | A5/A1 新增的两条用户可见消息补进语言包（复用 mysql 译文，六语言键集保持一致） |

### 3.5 验证

* 全量门禁：**181 模块 / 1374 用例 / 0 隔离 / 4 静态门禁 全绿**（约 52s）。
* i18n 11 项静态门禁全绿；代码质量棘轮未动（bare 0 / silent 0 / print 0 / os.system 5）。
* 包内 11 个文件全部 **LF / 无 BOM**。
* `web/core/yf.py` 已删除；原文件备份在 `test/tmp_yf_split/yf.py`（收尾删除）。

### 3.6 本轮未做 / 需真机确认

* **`web/utils/site.py`（3199 行 / 119 方法）与两个数据库插件的主体未拆**：用户拍板本轮只拆 `yf.py`。
* **mysql/mariadb 仍是两份副本**（136 同名 / 95 漂移）：本轮只对齐了安全相关函数，未抽共享模块（用户拍板）。
* **需真机验证**：`delDb` 的「超时→重启数据库→重试」分支、`getFpmAddress` 的 TCP 分支（tuple）在真实 php-fpm 配置下的连通性、主从同步真实链路。
* `plugins/*/scripts/{tools,test}.py` 依赖不存在的 `class/core` 且全库零引用（死脚本），本轮只登记未处理。


---

## 第 18 层：真机验证与 P0 修复（goal `mumdpftx-pja0w7`）

真机：`root@172.17.60.248`，Debian 12（kernel 6.1.0-47）+ MySQL 5.7.44 + PHP-FPM，面板跑 gunicorn。

### 18.1 调试通道与安全基线（task-1）

- 新增 `test/ssh_run.sh`（plink/pscp 包装，密码只从 `YF_SSH_PASS` 取，不落盘）——按收尾约束**已于本轮结束时删除**（`test/` 本身被 `.gitignore` 覆盖）；通道可用性由下一条的 md5 往返一致性直接佐证。
- plink 免交互执行 ✅、pscp 上传/下载往返 md5 一致 ✅；20 个改动文件与服务器 **md5 逐一一致** ✅。
- 备份目录 `/root/yf_debug_backup_20260929_155436`（记录于 `/root/.yf_debug_last_backup`）。
- 重启方式与影响面：`/etc/init.d/yf restart`（→ `cd web && gunicorn -c setting.py app:app`，pid `logs/panel.pid`，UI 中断 2~5s）；MySQL = `systemctl restart mysql`。

### 18.2 清理被包遮蔽的旧 `web/core/yf.py`（task-2）

- 服务器曾**同时存在** `web/core/yf/` 与 `web/core/yf.py`（后者被包遮蔽）。已删 `web/core/yf.py`（103729 字节，备份 `<备份目录>/web_core_yf.py.pre_split`）+ 陈旧 `yf.cpython-311.pyc` + 包内 `__pycache__`。
- 验证：`import core.yf` → `/www/server/yufeng_panel/web/core/yf/__init__.py`，公开符号 **216**（口径：`dir()` 非下划线；其中函数 189 / 类 1 / 模块 26；包内 `def` 定义过的函数名 204）；重启后 pid 2048846、监听 `0.0.0.0:60374`、`HTTP / → 200`、无 ImportError。

### 18.3 task-3 验证结论：`delDb` 重启-重试分支有 **P0 缺陷**

**触发方式**（真实锁等待，不改代码造超时）：造专属探针库 `yfdel_probe` + `LOCK TABLES ... SELECT SLEEP(240)` 持住 MDL → `DROP DATABASE` 真实阻塞 → 走面板 CLI 真实代码路径 `del_db`。

**修复前实测**（16:48:37 → 16:49:15，elapsed 38s，rc=0）：

```
{"status": false, "msg": "删除失败!重启后尝试删除数据库依然失败:
  (2003, \"Can't connect to MySQL server on 'localhost' ([Errno 111] Connection refused)\")"}
```

- 38s ≥ 30s → **超时分支确实触发**（`read_timeout=30` 生效）；`journalctl` 显示 16:49:11 `Stopped/Started mysql.service` → **重启确实执行**。
- **但 MySQL 起不来，服务被留在 `failed`**（MainPID=0），库删不掉，需人工介入约 3 分钟。
- `error.log` 根因：`Can't create/write to file '/www/server/mysql/data/mysql.pid' (Errcode: 13 - Permission denied)`；`Can't start server: can't create PID file`。

**根因链**：面板以 **root** 运行，`mysql::status()` 的「PID 自愈」把存活 PID **写进 mysqld 的 datadir**（`pid-file = /www/server/mysql/data/mysql.pid`，目录 `750 mysql:mysql`）；写盘是原子替换 → 属主变成 `root:root`；而 mysqld 由 systemd 以 `User=mysql` 启动 → **无法创建自己的 pid 文件** → 启动失败。

**连带缺陷**：① `restart()`/`start()` 只看轮询结果、服务 failed 也返回 `'ok'`（上层误判）；② `delDb` 重试失败直接抛错，**不把服务拉回可用状态**。

证据固化于服务器 `/root/yf_task3_evidence.txt`（51 行）。

### 18.4 修复内容（本地）

| 文件 | 改动 |
|---|---|
| `web/core/yf/__init__.py` | 新增 **`syncPidFile(pid_file, pid)`**：只在「目录属主 = 当前用户」且「文件不存在或属主 = 当前用户」时才写；目录缺失不写（不在状态检查里造目录）；内容已是目标值不重写；无 `os.geteuid` 的平台直接跳过 |
| `plugins/mysql/index.py` | 2 处 pid 自愈写回 → `yf.syncPidFile`；`start()`/`restart()` 未就绪时返回 `error:` 串；`delDb` 检查 `restart()` 返回值并兜底 `start()`，重试失败时先把服务拉回可用状态并把状态写进报错 |
| `plugins/mariadb/index.py` | 同上（3 处写回；`start()`/`restart()` 原来**连就绪轮询都没有**，补上 8 秒轮询 + 如实报错；`delDb` 同样兜底） |
| `plugins/redis/index.py` | pid 自愈写回 → `yf.syncPidFile` |
| `plugins/php/index.py` | pid 自愈写回 → `yf.syncPidFile` |

新增守卫 `testsuite/test_pid_file_ownership_guard.py`（**15 项**）：助手行为 8 项（含「属主不匹配绝不写」）+ 家族收口 3 项 + 服务失败如实上报 4 项（`delDb` 兜底用 **AST 结构断言**，字符串存在性检查会被 `if False:` 蒙混）。

同步修正 3 个断言了**旧危险行为**的既有用例（`test_mysql/redis_upgrade_self_healing`、`test_upgrade_and_mariadb_self_healing`）：把 `geteuid` 对齐到临时目录属主，使写回断言在任意平台成立，并**新增「属主不匹配则绝不写盘」场景**。

**变异自证 4/4**（工具 `test/mutate_pid_guard.py`，字节快照 + `finally` 还原）：去掉属主判据 / `restart` 退回 `return res` / 丢弃 `restart` 返回值 / 重试失败不兜底 —— 四处改坏都被守卫抓红。**第一次跑时 D 项未被抓**（假绿），据此把该断言改成 AST 结构检查。

### 18.5 真机复验证据（修复后）

**A. 属主受控对照实验**：

| 场景 | 结果 |
|---|---|
| `yf.syncPidFile('/www/server/mysql/data/mysql.pid', pid)`（datadir 属主 uid 1002，euid 0） | **False**（拒绝写入） |
| 删掉 pid 文件后再调 `index.py status` | 返回 `start`（判定仍正确），**pid 文件未被创建**（旧代码会以 root 重建 = P0） |
| 负对照：同一助手写 root 自有目录 `/root/yf_pid_probe/daemon.pid` | **True**，内容 `12345` → 拒绝写入源于属主规则，非功能失效 |

**B. 原故障场景完整复跑**（17:32:30 → 17:33:08，elapsed 38s）：

```
{"status": true, "msg": "删除成功!"}
```

| 项 | 修复前 | 修复后 |
|---|---|---|
| 超时分支 | elapsed 38s | elapsed 38s |
| CLI 输出 | `status:false ... Connection refused` | **`status:true 删除成功!`** |
| MySQL 终态 | **failed / MainPID=0** | **active/running**（2080855 → 2104380，证明重启发生） |
| 探针库 / 用户 | 残留 | 0 / 0 |
| 面板记录 | 残留 | 已删（回到 3 行） |
| `error.log` PID 权限错误 | 有 | **0** |
| 业务库 | — | `test1` / `cc2` / `dianbiao` 完好 |

### 18.6 验证

* 本地全量门禁：**182 模块 / 1389 用例 / 0 隔离 / 4 静态门禁 全绿**（约 51s）。
* 部署：5 个文件 pscp 上服务器后 **md5 逐一双向一致**；备份 `/root/yf_p0_fix_backup_20260929_172412`（回滚命令已记录）。
* 服务器无遗留探针对象（库/用户/面板记录均已清）。

### 18.7 task-4：`getFpmAddress` 的 TCP 分支（真机实测通过）

真机 php 装了 80/81/83（均监听 unix socket），仅 1 个站点且未绑定 83 → 选 83 做实验。

| 步骤 | 实测 |
|---|---|
| 基线 | `listen = /tmp/php-cgi-83.sock`；`getFpmAddress('83')` → `'/tmp/php-cgi-83.sock'` |
| 改 `www.conf` 为 `listen = 127.0.0.1:9083` + `systemctl restart php83` | `ss -lntp` → `php-fpm` 监听 `127.0.0.1:9083`（pid 2106400） |
| 断言 | `getFpmAddress('83')` → **`('127.0.0.1', 9083)`**（元组）；`bind=True` 同 |
| **fcgi 真实连通** | `requestFcgiPHP(('127.0.0.1',9083), '/index.php', document_root='/tmp/fcgi_probe')` → 响应 `FCGI_PROBE_OK` |
| 回滚 | 恢复 `www.conf` + 重启 → `getFpmAddress('83')` 回到 sock 路径、sock 恢复、服务 active、fcgi 仍连通 |

结论：TCP 分支（元组）在真实 php-fpm 配置下**返回值正确且可真实建立 FCGI 连接**（`FCGIApp` 对 tuple 走 `socket.create_connection`）。备份 `/root/yf_task4_backup/www.conf.orig`。

### 18.8 task-5：进程匹配 `mdserver-web` 的失效范围（真机结论表）

**事实基线**：`/www/server/mdserver-web` 是软链 → `/www/server/yufeng_panel`；面板实际以 `/www/server/yufeng_panel/bin/python3 ...` 启动；**cmdline 含 `mdserver-web` 的进程数 = 0**（含 `yufeng_panel` = 2）。面板启动插件的真实形式（`web/utils/plugin.py:1609`）为 `[sys.executable, 绝对插件路径, func]`，即：

```
/www/server/yufeng_panel/bin/python /www/server/yufeng_panel/plugins/sphinx/index.py status
```

**逐处结论**：

| 位置 | 匹配式 | 真机命中 | 后果 |
|---|---|---|---|
| `plugins/sphinx/index.py:122` | `ps -ef\|grep sphinx \|grep -v grep \|grep -v mdserver-web` | **插件自己命中**（同一瞬间 `ps` 只匹配到 `plugins/sphinx/index.py status` 自身） | **功能缺陷**：`status()` 返回 **`start`**，而 sphinx **根本未安装** |
| `plugins/postgresql/index.py:345` | `...\|grep -v python\|grep -v mdserver-web` | `grep -v python` 把插件自己滤掉 → 判定正确；`mdserver-web` 过滤 **0** 个进程 | 当前无故障（未安装时提前返回 stop），但**冗余守卫完全失效**；若插件 CLI 将来非 python 启动，即退化为同类假阳性 |
| `plugins/varnish/index.py:84` | 同 postgresql | 同上；真机实测 `status()` → **`stop`**（正确） | 同上 |
| `plugins/task_manager/task_manager_index.py:352` | `cmdline.find('mdserver-web/plugins')` | 面板真实 cmdline 用 **绝对路径** → `False`（连软链相对形式也 `False`） | **分类不准**：面板插件进程不被标为「面板插件进程」 |
| `plugins/task_manager/task_manager_index.py:385` | `cmdline.find('mdserver-web') and find('gunicorn -c setting.py app:app')` | 真实 cmdline 含 `yufeng_panel` → **`False`** | **分类不准**：面板本体不被标为「御风面板」 |

**对照实验（同一台机、同样未安装）**：

| 插件 | 是否有 `grep -v python` | 实测 status | 期望 |
|---|---|---|---|
| sphinx | ❌ 无 | **start** | stop ❌ |
| varnish | ✅ 有 | **stop** | stop ✅ |

→ 二者代码仅差一个 `grep -v python`，直接坐实：**`mdserver-web` 守卫已失效，真正起作用的是 `grep -v python`**。

**运行时目录判据实测**（修复方向）：对插件进程 cmdline，`find(yf.getPanelDir() + '/plugins/')` = **True**；对面板 gunicorn，`find(yf.getPanelDir())` = **True**；而 `mdserver-web` 两个判据均为 **False**。

### 18.9 task-6：主从同步真实链路 —— 单机可验部分已验，双机链路标记「阻塞」

**链路方向（读码结论，`plugins/mysql/index.py::doFullSyncSSH`）**：`doFullSyncSSH` 跑在**从库**，它：读从库 `slave_id_rsa` 表拿主库 IP/端口/私钥 → paramiko SSH 登录**主库** root → 在主库执行 `dump_mysql_data` 产出 `/tmp/dump.sql.gz` → SFTP 拉回 → 再在主库执行 `get_master_rep_slave_user_cmd` 取 `CHANGE MASTER TO` SQL → 本地 `stop slave` + 把 `MASTER_HOST/SOURCE_HOST` 重写为真实主库 IP + 执行 → 解压导入 dump。**两端都必须装面板**（从库要跑本插件代码；主库要被 SSH 执行插件命令）。

**已在本机（主库角色）验证**：

| 项 | 实测结果 |
|---|---|
| 主库前置条件 | `log_bin=1`、`server_id=1789553551`、`binlog_format=MIXED`、`gtid_mode=OFF`、`read_only=0`；`SHOW MASTER STATUS` → `mysql-bin.000010 : 1382` |
| 本机从库角色 | `SHOW SLAVE STATUS` 为空 = 未配置从库 ✓ |
| 主从三张配置表 | `master_replication_user` / `slave_sync_user` / `slave_id_rsa` **均 0 行** = 从未配对过 |
| **主库侧 dump（从库会 SSH 执行的那一步）** | `dump_mysql_data '{"db":"test1"}'` → **`ok`**，产出 `/tmp/dump.sql.gz` **4181757 字节**，`gzip -dc` 含 1 个 `CREATE TABLE`，头部 `-- MySQL dump 10.13 Distrib 5.7.44`；**随后已删除**（不留数据副本） |
| 从库会执行的两条命令（原样复刻） | ① `cd <面板目录> && source bin/activate && python3 <面板目录>/plugins/mysql/index.py dump_mysql_data '{"db":…}'`；② 同形式 `get_master_rep_slave_user_cmd '{"username":…,"db":""}'`；③ SFTP `get("/tmp/dump.sql.gz", "/tmp/dump.sql.gz")` |

**顺带发现并修复的缺陷（单侧漂移，已归 task-7）**：主库侧 `get_master_rep_slave_user_cmd` 在「username 非空但查无该同步账户」时 `clist` 为空列表 → `clist[0]` 抛**未捕获 IndexError**（真机 stdout 输出 traceback），从库侧 `json.loads(result)` 随之失败、整条链路报错难查。mariadb 侧两个同名函数一直有 `if len(clist) == 0` 守卫，mysql 侧缺失。

**阻塞项：双机真实复制链路**

阻塞原因（客观）：链路两端都需装面板，而本机网段内**未发现第二台面板机**（探测到的 60374 端口均为回环 `127.0.0.0/8` 与 docker 网桥 `172.18/19/20.0.1`）；**用同一台机自配主从会产生复制回环 + 数据重复导入**，属破坏性操作，按约束不做。

所需环境清单（第二台面板机）：

| 项 | 要求 |
|---|---|
| 系统 | Debian 12 / Ubuntu 22.04+，能访问主库 22 端口 |
| 面板 | 与本机**同版本**面板（含 `plugins/mysql`）；venv 内需有 **paramiko**（从库侧 `doFullSyncSSH` 依赖） |
| MySQL | 从库版本 ≥ 主库（5.7.44）；`server_id` 与主库不同；若要级联则 `log_slave_updates=1` |
| SSH | 从库 root 持有主库私钥；主库 `authorized_keys` 含该公钥；主库 sshd 允许 root 登录 |
| 网络 | 从库 → 主库：`22`（SSH）+ 主库 MySQL 端口（复制连接） |

验收步骤与每步预期证据：

1. **主库加同步账户**：主库面板 → MySQL 插件 → 添加同步账户（CLI `add_master_rep_slave_user`）
   → 证据：主库 `master_replication_user` 出现 1 行；`SELECT user,host FROM mysql.user WHERE user='<账户>'` 有记录。
2. **从库登记主库 SSH**：从库面板 → 添加从库 SSH 信息（CLI `add_slave_ssh`，主库 IP/端口/私钥）
   → 证据：从库 `slave_id_rsa` 出现 1 行；从库能 `ssh -i <key> root@<主库>` 免密登录。
3. **触发全量同步**：从库执行 `do_full_sync` / `full_sync`（先 `full_sync_cmd` 预览）
   → 证据：从库 `/tmp/dump.sql.gz` 存在；`db_sync_status` 进度走到 100；从库 `SHOW SLAVE STATUS` 的 `Slave_IO_Running=Yes` 且 `Slave_SQL_Running=Yes`。
4. **数据一致性**：主库 `SHOW MASTER STATUS` 的 File/Position 与从库 `SHOW SLAVE STATUS` 的 `Master_Log_File`/`Read_Master_Log_Pos` 对齐；任选 1 个业务库对两侧 `mysqldump` 做校验和对比一致。
5. **增量验证**：主库建表/插行 → 从库 1~2 秒内可见，`Seconds_Behind_Master` 回落 0。

> 另：`doFullSyncSSH` 会把私钥写到 `/tmp/mysql_sync_id_rsa.txt`（`chmod 600`）且 `paramiko.util.log_to_file('paramiko.log')` 会在当前工作目录落一个 `paramiko.log`；双机验证时注意清理，且不要让它进仓库。

### 18.10 task-7：修复项三段证据汇总

| # | 缺陷 | 本地改动 | 服务器复验 | 本地门禁 |
|---|---|---|---|---|
| 1 | **P0**：面板 `status()` 把 pid 写进 mysqld datadir → 属主变 root → mysqld 下次启动失败（`delDb` 重启分支把 MySQL 留在 failed） | `web/core/yf/__init__.py` 新增 `syncPidFile`（+48 行）；`mysql`/`mariadb`/`redis`/`php` 共 7 处写回改走它；`mysql`/`mariadb` 的 `start()`/`restart()` 未就绪时如实返回 `error:`；`delDb` 检查 `restart()` 返回值 + 重试失败时先把服务拉回并把状态写进报错（`mysql` +52/−? 、`mariadb` +60） | 见 §18.5：`syncPidFile` → False（拒绝）；删掉 pid 后 `status` 仍 `start` 且**不再以 root 重建**；负对照 → True；原故障场景复跑 → `status:true 删除成功!` + MySQL **active/running** + error.log PID 错误 **0** | 全绿 |
| 2 | **P1**：`sphinx::status` 假阳性（未安装也报 start）；`mdserver-web` 路径判据全库失效（`sphinx`/`postgresql`/`varnish` + `task_manager` 四处） | `sphinx` 补 `grep -v python` + 运行时面板目录；`postgresql`/`varnish` 换运行时面板目录；`task_manager` 新增 `_panel_dir_marks`/`_is_panel_process`/`_is_panel_plugin_process` 三个助手并替掉 4 处失效判据（+44 行） | 见 §18.8 末：`sphinx → stop`（修复前 start）、`varnish`/`postgresql` 仍 stop；生成的命令串含 `grep -v python` + `grep -v /www/server/yufeng_panel`；`get_process_ps` 端到端：gunicorn → **御风面板**、现场拉起的插件进程 → **面板插件进程**、varnishd → 均 False；面板 HTTP 200 | 全绿 |
| 3 | **P2**：`mysql::getMasterRepSlaveUserCmd` 缺空结果守卫 → 未捕获 `IndexError`（mariadb 侧两个同名函数都有守卫 = 单侧漂移） | `plugins/mysql/index.py` 补 `if len(clist) == 0` 守卫（与 mariadb 对齐）+ `plugins/mysql/lang/*.json` 六语言补 `错误同步账户!` 键 | 真机对照：修复前（备份旧文件）`IndexError: list index out of range` → 修复后 `{"status": false, "msg": "错误同步账户!"}`；空用户名仍返回 `请添加同步账户!`；面板 HTTP 200 | 全绿 |

**新增/修正的守卫用例（共 31 个 test 方法）**：

* `testsuite/test_pid_file_ownership_guard.py`（**15**，新）：`syncPidFile` 行为 8 + 家族收口 3 + 服务失败如实上报 4（`delDb` 兜底用 AST 结构断言）
* `testsuite/test_process_match_panel_dir.py`（**10**，新）：失效判据清零 + 三插件命令串（去注释源码断言）+ `sphinx` 行为 + `task_manager` 分类（用真机真实 cmdline 样本）
* `testsuite/test_db_plugin_hardening.py`（**+3**）：同步账户守卫的行为 + 静态兵
* 同步修正 3 个断言了**旧危险行为**的既有用例（`test_mysql/redis_upgrade_self_healing`、`test_upgrade_and_mariadb_self_healing`）：`geteuid` 对齐临时目录属主，使写回断言在任意平台成立，并新增「属主不匹配则绝不写盘」场景

**变异自证**：P0 批 **4/4**（`test/mutate_pid_guard.py`）、进程匹配批 **4/4**（`test/mutate_process_match.py`）、同步守卫批 2/2（内联）。自证过程中**三次抓到自己的假绿断言**，已逐个修正：

1. `delDb` 兜底只用字符串存在性检查 → 改成 AST 结构断言（把判断改成 `if False:` 也能过）
2. 进程匹配用例直接对**带注释源码**断言 `grep -v python`，而注释里恰好有这串字 → 改用 `ast.unparse` 去注释后再断言
3. 同步守卫的静态兵被注释里的 `clist[0]` 绊倒（守卫被判在 `clist[0]` 之后）→ 同样去注释
4. 另修一处**测试自身错误**：`assertIn('错误同步账户', raw)` —— `returnJson` 会把中文转义为 `\uXXXX`，必须断言解析后的 `msg`

**终态**：本地全量门禁 **183 模块 / 1402 用例 / 0 隔离 / 4 静态门禁 全绿**（目标基线为 181/1374；本轮新增 2 个用例模块与 28 个 test 方法，是**超集**而非降强）。棘轮未动：`bare_except 0 / silent_except 0 / print_in_web 0 / os_system_count 5`。

**部署与回滚**（服务器，均已 md5 双向校验）：`/root/yf_p0_fix_backup_20260929_172412`（5 文件）、`/root/yf_task5_fix_backup_20260929_174359`（4 文件）、`/root/yf_task6_fix_backup_20260930_074452`（1 代码 + 6 语言包）。

### 18.11 C 类可执行清单（需 CI / 产品决策 / 外部环境）

> 完整版（含与本文一致的表格 + 细节说明）在 `参考/20260928优化.md` §10.3；本节为同内容的可执行摘要。每项格式：**改动点** → **验收步骤** → **所需外部条件**。

**① 需 CI / 联网 / 发布流程**

| # | 项 | 改动点 | 验收步骤 | 所需外部条件 |
|---|---|---|---|---|
| A1 | 翻转 `YF_REQUIRE_SIGNATURE=1` | `scripts/install.sh`/`update.sh` 默认值与验签入口 | ① 未签名 tarball 必须**拒绝**；② 签名 tarball 必须通过；③ 无残留硬编码 | A2 + 干净 Linux 机 |
| A2 | 首个签名 Release | 推 tag → CI 出签名 tarball + 公钥分发 | ① `git tag && push --tags`；② CI 绿；③ `yf_release_verify.py` 验签通过 | CI 可联网 + 签名私钥 |
| B6 | 安装脚本信任根（`curl \| bash`） | `install.sh` 文档 + 校验步骤 | ① 先下 tarball → 验签 → 再执行；② 文档给出 sha256 与验签命令 | A2 |
| C4 | `requirements.lock` 入库 | CI `lock` job 已就绪 | ① 取 artifact；② 提交入库；③ 「锁不得取代 `requirements.txt`」守卫仍绿 | CI |
| C6 | `run_all.py --coverage` | 加 `--coverage` | ① `pip install coverage`；② 出报告；③ 先只出基线不设门禁 | 联网装包 |
| C7 | 最小前端构建（esbuild） | `web/static` 构建管线 + 依赖锁 | ① 引入 esbuild；② 产物与现网 diff 空；③ CI 加构建步骤 | 联网装包 |
| E1 | `.i18n.bak`（33 文件） | 依赖 A2 的 tarball 形态自然剔除 | ① 确认 tarball 内无 `.i18n.bak`；② **禁止手工删除** | A2 |
| E2 | `zabbix` 8.4MB `*.sql.gz` | 待确认是否属交付内容 | ① 属交付 → 保留登记；② 不属 → 移出仓库（**需用户确认**） | 产品决策 |
| E3 | `.git` 约 98MB | **禁止改写历史** | — | 既有决策 |

**② 需产品决策**

| # | 项 | 改动点 | 验收步骤 | 所需外部条件 |
|---|---|---|---|---|
| D1 | 审计流水 UI（**性价比最高**） | 前端页 + 6 语言 i18n（后端已就绪） | ① 筛选可用；② 「校验哈希链」显示 `verify_chain()`；③ 6 语言键齐全；④ i18n 门禁绿 | UI 形态确认 |
| D2 | 审计远端转发 | 转发出口 + 失败重试 | ① 条目到达 syslog；② 断网不阻塞主流程 | 合规口径 |
| D3 | 授权/激活/计费 | `edition.py` + `web/pro/` 已分层 | ① 社区版仍整目录剔除 `web/pro/`；② 失败降级不炸面板 | 商业模型 |
| D4 | RBAC 多用户 | 权限模型 + 中间件 | ① 角色→权限矩阵可配；② 越权 403 且进审计 | 权限模型 |
| D5 | 插件签名与权限声明 | 插件清单 + 签名校验 | ① 未签名插件拒绝加载（可开关）；② 声明与运行时校验一致 | 权限清单 |
| D6 | 多 worker | 外置进程态（Redis/FileSystemCache） | ① 起 2+ worker；② 会话/限流仍生效（已走 DB）；③ 压测对比 | 外置缓存 + 压测环境 |

**③ 本地可做但需排期**

| # | 项 | 改动点 | 验收步骤 | 所需外部条件 |
|---|---|---|---|---|
| C1 | ORM 调用点迁移 **180 处** | 逐文件改 `*Strict` + 显式 `try/except`（顺序：`yf.py`→`gitea`→`sphinx`→`postgresql`→`data_query`→`mariadb`→`mysql`） | ① 每文件单独可回退；② 门禁全绿；③ 真机同步/备份回归 | 真机回归 |
| C5 | 巨型文件拆分（剩余） | `web/utils/site.py` 3199 行、两插件 5288/4398 行 | ① 同款 codemod（三重自检）；② 插件 CLI 入口签名不变；③ 门禁全绿 | 一次一个文件 |
| C5b | 抽 mysql/mariadb 共享核心 | 抽公共模块（136 同名 / 95 漂移） | ① 漂移归零；② 双插件门禁全绿；③ 真机跑删库/备份/同步 | 真机回归 |

**④ 需第二台真机（本轮已阻塞）**

| # | 项 | 改动点 | 验收步骤 | 所需外部条件 |
|---|---|---|---|---|
| R1 | 主从同步真实链路 | 无（验证项） | 见 §18.9 五步 | 第二台面板机（同版本面板 + paramiko + MySQL ≥5.7.44 + 独立 `server_id`） |

**⑤ 本轮新增「不做」记录**

| 项 | 决定 |
|---|---|
| `plugins/webssh/index.py` 的 `'mdserver-web'` | **不动**：那是 `deDoubleCrypt/enDoubleCrypt` 的**加解密盐值**，改它会破坏既有密文兼容 |
| `test/tmp_i18n/`、`test/tmp_plugin_i18n_audit/` 等上轮快照目录 | 在 `.gitignore` 覆盖的 `test/` 区，不参与交付；非本轮产物，不删 |
| 用同一台机自配 MySQL 主从 | **不做**：会产生复制回环 + 数据重复导入，属破坏性操作 |
| `plugins/*/scripts/{tools,test}.py` | 依赖不存在的 `class/core` 且全库零引用（死脚本），只登记不删 |

### 18.12 审计复核后的补正（2026-09-30）

独立审计以只读方式复核后，给出 `<approved/>` 并附 4 处瑕疵；已逐条处理：

| # | 审计意见 | 处理 |
|---|---|---|
| 1 | 本机默认控制台编码下 `test_db_migration_selfheal.py` / `test_edition_layering.py` 各 1 项失败（子进程中文 stdout 被按 UTF-8 解码产生 mojibake） | **已根治**：根因是**子进程**按控制台 cp936 输出、而用例按 UTF-8 解码。两处用例改为给子进程带 `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8`；并在 `testsuite/run_all.py::child_env()` 统一钉死（原先只是继承 `os.environ`）→ **不带 `PYTHONUTF8` 跑全量门禁也全绿**（183/1402/0/4） |
| 2 | `§18.2` 称公开符号 243，实测 `dir()` 非下划线为 216 | **已修正**为 216 并写明口径（函数 189 / 类 1 / 模块 26；包内 `def` 函数名 204） |
| 3 | `§18.1` 称新增 `test/ssh_run.sh`，但该文件本地不存在 | **已改措辞**：说明它按收尾约束已删除（`test/` 被 `.gitignore` 覆盖），通道可用性由 md5 往返一致性佐证 |
| 4 | `/tmp` 尚存 `yf_restart.log` | **非本轮产物**：那是 `/etc/init.d/yf restart`（面板自身重启脚本）写的日志，属面板正常行为；本轮创建的探针/凭据文件（含 `/tmp/.yf_probe_pw`）确已清除 |













