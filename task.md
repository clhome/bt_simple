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



