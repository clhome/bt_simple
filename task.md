# 20261102 手测缺陷修复与体验优化任务

## 项目概况与规范

根据 `参考/20261102手测.md` 反馈的 6 大缺陷问题进行针对性核对与彻底修复，同时对排查发现的同族/共性问题一并根治治理：

1. **御风 Python 多版本**：修复安装包含预发布标识（如 `cpython-3.15.0b4-linux-x86_64-gnu`、`3.15.0b4`）时因正则限制报错「版本标识不合法，已拒绝」的缺陷；
2. **御风 Docker 管理器**：优化容器日志模块，增加刷新、清空日志功能及 5 秒自动刷新勾选框（日志自动置底滚动）；
3. **御风网站防火墙**：修复服务面板「开机启动」点击报错问题，补齐 `initdStatus` / `initdInstall` / `initdUninstall` 接口，并排查治理 `op_load_balance` 与 `webstats` 插件的共性缺失；
4. **phpMyAdmin 无法访问 (502 Bad Gateway)**：排查修复 phpMyAdmin 关联 PHP-FPM 服务未运行或 socket 不匹配导致的 502 错误，增加 PHP 服务运行检测与自愈拉起机制；
5. **任务管理器样式美化**：消除硬编码 `597px` 超高导致的底部文字被裁切截断问题，重构自适应弹性布局与底部优雅留白；
6. **御风服务管理器**：
   - 6.1 统一更名为「御风进程管理器」；
   - 6.2 日志模块优化：增加 5 秒自动刷新勾选框（默认勾选），更新时保持最新日志显示在当前页底部，旧日志不断上移。

### 开发规范

- **编码与格式**：所有文件统一采用 UTF-8 (无 BOM) 编码，换行符强制使用 LF (`\n`)。
- **跨平台兼容**：严禁硬编码反斜杠路径，保证 Windows 本地开发与 Linux 生产环境兼容。
- **目录洁净**：测试脚本统一归入根目录 `test/`，执行完成后主动清理临时排查文件。

---

## 任务拆解与进度 (Task List)

- [x] **任务 1：御风 Python 多版本预发布标识放行与安全加固 (`plugins/python_yf`)**
  - [x] 1.1 扩展 `plugins/python_yf/index.py` 中 `TARGET_RE` 正则表达式，支持 PEP 440 预发布版本（如 `3.15.0b4`、`cpython-3.15.0b4-linux-x86_64-gnu`、`rc`、`t` 变体），同时严格防止注入
  - [x] 1.2 在 `testsuite/test_python_yf_d08_hardening.py` 中扩充测试用例与验证

- [x] **任务 2：御风 Docker 管理器日志模块优化 (`plugins/docker`)**
  - [x] 2.1 后端 `plugins/docker/index.py` 实现 `docker_clear_con_log` 容器日志清空接口
  - [x] 2.2 前端 `plugins/docker/js/docker.js` 优化 `logsCon` 弹窗，新增刷新按钮、清除日志按钮与 5 秒自动刷新勾选框
  - [x] 2.3 实现日志自动滚至底部（保持最新日志在底部）、弹窗关闭时自动注销定时器

- [x] **任务 3：御风网站防火墙开机启动与共性插件治理 (`plugins/op_waf`, `op_load_balance`, `webstats`)**
  - [x] 3.1 在 `plugins/op_waf/index.py` 中实现并路由 `initdStatus`、`initdInstall`、`initdUninstall`
  - [x] 3.2 治理共性问题：为同样使用 `pluginService` 但缺少 initd 接口的 `op_load_balance` 和 `webstats` 补齐对应接口与路由

- [x] **任务 4：phpMyAdmin 无法访问 (502 Bad Gateway) 深度排查与修复 (`plugins/phpmyadmin`)**
  - [x] 4.1 健全 `plugins/phpmyadmin/index.py` 中 PHP 版本探测与自愈逻辑，避免失效版本残留
  - [x] 4.2 在 phpMyAdmin 启动或访问时检测所绑定 PHP 服务的运行状态，未运行时自动尝试拉起，根治 502 错误
  - [x] 4.3 优化服务页展示当前 PHP 绑定版本与运行状态（带状态指示灯），提升容错与可视化

- [x] **任务 5：任务管理器底部显示样式美化 (`plugins/task_manager`)**
  - [x] 5.1 消除 `plugins/task_manager/js/task_manager.js` 中多处超高的硬编码 `597px`，改为容器自适应高度
  - [x] 5.2 优化 `plugins/task_manager/index.html` 布局与底部内边距，确保最后一行和表格底边完整显示不被裁剪

- [x] **任务 6：御风进程管理器更名与日志 5 秒自动刷新 (`plugins/yufeng_systemd`)**
  - [x] 6.1 将插件名称从「御风服务管理器」/「御风进程守护」统一更名为「御风进程管理器」，同步更新 `info.json`、多语言包和页面文案
  - [x] 6.2 优化 `plugins/yufeng_systemd/js/yufeng_systemd.js` 的 `get_logs` 弹窗，底部左侧增加「5秒自动刷新」复选框（默认勾选），更新时自动置底滚动，弹窗关闭清理定时器

- [x] **任务 8：修复后台任务守护进程单例锁与服务重启僵尸锁死锁问题**
  - [x] 8.1 在 `web/core/yf/paths.py` 中补充 `getPanelTaskLockFile()` 并在 `web/core/yf/__init__.py` 中导出暴露
  - [x] 8.2 加固 `panel_task.py` 中的 `acquirePanelTaskSingletonLock()`，增加兜底容错，防止属性缺失导致闪退，并在 `runPanelTask()` 增强异常隔离与锁释放保护
  - [x] 8.3 优化 `scripts/init.d/yf.tpl` 的 `yf_stop_task()`，当 `panel_task.lock` 存在时增加进程存活探测，自动清理死亡进程的僵尸锁，避免 `yf 1` 重启卡死
  - [x] 8.4 扩展/完善单元测试用例，端到端验证 `getPanelTaskLockFile` 与单例锁调用，运行测试套件确保全部绿灯

- [x] **任务 10：修复 Redis 升级到最新补丁版后右侧仍提示「升级到」的逻辑缺陷**
  - [x] 10.1 后端 `_seriesApplyVersionHint` 与提示缓存清理：当 `kind != 'update'` 或目标版本不高于当前版本时，彻底清理 `series_update` 等残留字段；治理 `_giteaApplyVersionHint` 共性逻辑
  - [x] 10.2 前端 `web/static/app/soft.js` 健全版本防御逻辑：最新目标与已安装版本相同时严禁渲染「升级到」超链接，并在 `softUpdate` 与徽标判断处增强校验
  - [x] 10.3 补充单测用例覆盖版本升级后旧提示消除场景，运行全量测试套件验证
  - [x] 10.4 治理升级或重启后后台服务存活巡检快照残留导致的「服务异常」红标假阳性误报（当前服务在线 `status: true` 时严禁挂异常红标，点击刷新列表主动失效旧快照）
  - [ ] 7.1 **Gitea**: 修复 `plugins/gitea/install.html` 中 `<strong>3000</strong>` 导致的文本节点被切割问题，使其整句匹配 `"Gitea 默认服务端口为 3000。"` 语言包键
  - [ ] 7.2 **Docker**: 移除已废弃死键 `"Docker日志"`，补充 `docker.js` 中新引用的 `"获取日志失败"` 及其六国语言包映射
  - [ ] 7.3 **phpMyAdmin**: 为 `phpmyadmin.js` 中新增的 `pt('启动成功')` 和 `pt('启动失败')` 补充六国语言包映射
  - [ ] 7.4 **御风进程管理器**: 将六国语言包中的旧键 `"【御风进程守护】提示："`、`"在御风进程守护中进行配置"` 更新为 `"【御风进程管理器】提示："`、`"在御风进程管理器中进行配置"`，并移除已无引用的死键 `"御风进程守护"`

- [ ] **任务 8：自动化测试验证与全量回归**
  - [ ] 8.1 运行 `testsuite/test_plugins_i18n_upgrade.py` 确保 100% 通过
  - [ ] 8.2 运行 `python testsuite/run_all.py` 执行全量门禁回归测试
  - [ ] 8.3 清理临时测试文件，更新任务完成状态

- [x] **任务 12：修复 CI 门禁失败（i18n 字面量、代码质量棘轮 silent_except 与 shell 拼接棘轮）**
  - [x] 12.1 将 `plugins/data_query/static/js/app.js` 中的 `pt('服务侧同步')` 修正为统一规范键 `pt('服务器同步')`
  - [x] 12.2 修复 `plugins/data_query/common_db.py` 及 `nosql_redis.py` 中 3 处 `silent_except`（添加调试日志），满足代码质量棘轮要求
  - [x] 12.3 修复 `plugins/phpmyadmin/index.py` 中 4 处 shell 裸拼违规（使用 `yf.shlexQuote` 并移除脆弱的 grep 探活），满足 shell 拼接棘轮要求
  - [x] 12.4 运行 `test_shell_concat_ratchet.py`、`test_plugins_i18n_upgrade.py`、`scripts/verify_code_quality.py` 等门禁确保全部通过

- [x] **任务 10：修复 MySQL 5.7 / MariaDB 创建数据库 1396 报错与假失败缺陷 (`plugins/mysql`, `plugins/mariadb`)**
  - [x] 10.1 根因定位与排查：彻底分析 `addDb` 盲目 `drop user` 导致 MySQL 1396 报错及引发子进程 stderr 误判机制
  - [x] 10.2 重构 `plugins/mysql/index.py` 的 `addDb`，改造为「先查后删（`SELECT Host` + `_dropUserTargets`）」防御机制，消除盲目 DROP
  - [x] 10.3 同步重构孪生插件 `plugins/mariadb/index.py` 的 `addDb` 及关联的 `delMasterRepSlaveUser` / `updateMasterRepSlaveUser`
  - [x] 10.4 编写针对性单元测试与安全门禁验证，确保全量测试套件通过

- [x] **任务 11：数据管理插件本地 Redis 连接失败缺陷修复与自愈增强 (`plugins/data_query`)**
  - [x] 11.1 **根因治理与密码探测强化 (`common_db.py`)**：在 `scanCurrentLocalConfigs` 中优先复用 `plugins.redis.index` 的成熟配置解析体系，完善单双引号及注释截断；修复空密码保护机制逻辑，允许清空/重置密码正常同步，杜绝脏旧密码死锁
  - [x] 11.2 **多级智能自愈与连接容灾 (`nosql_redis.py`)**：重构本地连接异常自愈链路，当遇到 `invalid username-password` / `NOAUTH` 时，依序执行「权威配置文件密码 ➔ 空密码 ➔ 在线真实运行时密码」多级自愈；自愈成功后自动回写持久化至 SQLite `db_connections`
  - [x] 11.3 **前端体验与错误引导优化 (`app.js`, `index.html`)**：优化本地连接密码错误时的诊断提示，提供更明确的引导信息，支持无缝重试
  - [x] 11.4 **测试套件扩充与全量回归**：编写 `testsuite/test_data_query_redis_auth_fix.py` 覆盖各种密码格式、旧密码脱节自愈与空密码同步场景，确保门禁全部通过

- [x] **任务 13：修复 PHP-FPM 多版本 backup pool 监听 Socket 冲突与自愈缺陷 (`plugins/php`, `panel_task.py`)**
  - [x] 13.1 **核心修复 (`plugins/php/index.py`)**：在 `phpFpmPoolReplace` 中根据 `pool` 参数动态计算 `listen_path`（`www` 为 `/tmp/php-cgi-{version}.sock`，其它非 `www` 池如 `backup` 为 `/tmp/php-cgi-{version}.{pool}.sock`），修正极限兜底模板中的 socket 路径
  - [x] 13.2 **后台巡检自愈覆盖 (`panel_task.py`)**：在 `phpPoolHeal_step` 中增加对编译版各版本 `backup.conf` 的巡检与自愈，确保所有存量版本的被改坏的备用池配置能被自动校准为 `.backup.sock`
  - [x] 13.3 **自动化回归测试与门禁验证**：在 `testsuite/test_php_fpm_pool_socket.py` 与 `testsuite/test_php_pool_healing_and_ui_quotes.py` 中扩充测试用例，覆盖多版本 `backup.conf` 自愈、防冲突断言，运行全量回归测试确保 100% 通过

- [x] **任务 14：御风网站统计插件样式全面美化与排版重构 (`plugins/webstats`)**
  - [x] 14.1 **重构概览页（Overview）指标与卡片布局**：根治趋势指标中 `访客量(UV)` 换行导致的单选框悬空错位 Bug；将指标单选器改造为现代 Flex 药丸/单选组并优化秒数输入；重构概览 7 大统计卡片为现代 Dashboard 卡片网格（微浅底色/柔和边框/数字层级分明）
  - [x] 14.2 **重构日志页（SitesLog & SitesErrorLog）筛选工具栏**：消除请求类型、状态码、来源、蜘蛛过滤、IP、耗时、大小、URL过滤等杂乱硬编码行；打造统一高度（32px）、对齐规范、圆角微光晕的现代筛选组件（Flex 流式排布与一体化搜索框）
  - [x] 14.3 **优化通用控制栏与其它模块页面（SitesList, SpiderStat, ClientStat, IpStat, UriStat, GlobalSetting）**：统一顶部网站/时间快速切换组、时段与刷新按钮的现代视觉风格；优化蜘蛛统计侧边卡片与图表容器排版；规范表格与全局设置表单样式
  - [x] 14.4 **样式与交互兼容性验证**：确保所有原业务选择器、事件绑定及 i18n 多语言翻译完整兼容；验证各分辨率及语言下布局无溢出、无换行错位
  - [x] 14.5 **优化客户端统计（ClientStat）图表空间排版**：圆环图容器锁定紧凑宽度并靠左对齐，彻底消除左侧空白；右侧柱状图弹性占满所有剩余空间，优化柱状图图例与网格边距，避免图例重叠与柱状挤压

- [x] **任务 15：文件管理器压缩默认命名重构与重名递增防冲突 (`web/static/app/files.js`)**
  - [x] 15.1 在 `web/static/app/files.js` 中新增时间戳生成、扩展名获取与递增候选名称计算工具函数
  - [x] 15.2 重构 `zip(dirName, submits)`：移除随机字符串，集成当前时间戳命名与本地优先防重名计算
  - [x] 15.3 完善服务端 `/files/check_exists_files` 异步校验与自动递增校准机制，联动压缩格式与目录切换
  - [x] 15.4 编写专门的单元测试用例，覆盖时间格式、防重名序号递增（无后缀 -> -01 -> -02）、扩展名联动及边缘场景
  - [x] 15.5 运行自动化测试验证，确保全部通过，更新任务完成状态

- [x] **任务 16：御风OP防火墙与御风F2B防火墙版本升级及新漏洞蜜罐规则安全增量同步 (`op_waf`, `fail2ban`)**
  - [x] 16.1 规则模板增强：在 `op_waf/waf/config.json`、`waf/rule/vuln.json`、`waf/rule/url.json` 中补充针对 Java/Spring Boot (CVE-2026-40972/41843) 及相关高危漏洞的蜜罐诱饵与防御特征
  - [x] 16.2 平滑升级机制实现：在 `op_waf/index.py` 中实现 `upgradeRules()`，在服务启动、重启、配置重载时智能执行安全增量合并；更新 `op_waf/install.sh` 支持 `install/update/upgrade` 动作
  - [x] 16.3 前端与版本元数据同步：更新 `op_waf/js/op_waf.js` 蜜罐还原默认路径，升级 `op_waf/info.json` 版本至 1.6
  - [x] 16.4 `fail2ban` 协同与版本升级：升级 `fail2ban/info.json` 与 `install.sh` 版本至 1.3.0，规范安装脚本动作分发，优化 `op-waf` 蜜罐联动拦截原因展示
  - [x] 16.5 测试套件与全量回归：编写单元测试验证老用户升级增量合并、自定义规则绝不覆盖、蜜罐诱饵与拦截特征有效性，确保全量测试通过

- [x] **任务 17：文件管理器双击打开体验优化与二进制安全探测 (`web/static/app/files.js`, `web/utils/file.py`, 多语言包)**
  - [x] 17.1 **后端安全探测增强 (`web/utils/file.py`)**：在 `getFileBody` 中增加 NUL 空字节 (`\x00`) 二进制嗅探拦截，防止二进制文件误以文本解码并被破坏，规范多语言错误键为 `file.py_msg_binary` 及 `file.py_msg_f48da9`
  - [x] 17.2 **多语言字典补充 (`template.files.json`)**：在 6 种语言包中补充 `py_msg_binary`、`binary_preview_unsupported`、`file_too_large` 等键值
  - [x] 17.3 **前端双击分流与属性绑定 (`web/static/app/files.js`)**：
    - 列表/图标渲染时绑定 `data-size` 属性；
    - 重构 `openFilename(obj)`：支持图片（预览）、SVG（预览）、压缩包（调起解压）、二进制扩展名拦截提示、>2MB 文件提示，以及对无后缀（如 `config`, `HEAD`, `Dockerfile`）或未知后缀小文本文件放行并调用 `onlineEditFile`
  - [x] 17.4 **自动化测试用例与全量验证**：编写测试脚本验证 `getFileBody` 对普通文本读取、空字节二进制文件拦截、超过 2MB 文件拦截及多语言映射，运行回归测试确保零破坏

- [x] **任务 18：全局弹窗提示（layer.msg / alert / confirm）自适应宽度与长文本截断治理 (`site.css`, `ensite.css`, `public.js`, `files.js`)**
  - [x] 18.1 **样式层彻底修复 (`site.css`, `ensite.css`)**：
    - 移除 `.layui-layer-msg .layui-layer-content` 粗暴的 `white-space: nowrap !important`，放开 `.layui-layer-msg` 最大宽度为 `min(650px, 90vw)`，支持内容单行伸展自适应并可在超长时安全折行；
    - 对 loading 类型单独设置 `white-space: nowrap` 维持无滚动条特性；
    - 增强 `.layui-layer-dialog` (alert/confirm) 最大宽度自适应到 600px，支持长消息自动折行；
  - [x] 18.2 **JS 拦截层全局保底增强 (`web/static/app/public.js`)**：在 `layer.msg`、`layer.alert`、`layer.confirm` 劫持逻辑中将 `maxWidth` 默认值提升（msg 提升为 650，alert/confirm 提升为 600），覆盖 layer.js 默认 360px 内联限制；
  - [x] 18.3 **业务层双重防御 (`web/static/app/files.js`)**：在 `openFilename` 调用的 `layer.msg` 明确附带 `maxWidth: 650`；
  - [x] 18.4 **全量弹窗排查与回归验证**：排查 tips、prompt、页面层弹窗，运行回归测试确保样式与逻辑稳定。

- [x] **任务 19：缺陷修复（P1-1、P2-1、P2-2、P2-3、P2-4）**
  - [x] 19.1 **P1-1 修复**：`testsuite/test_gitea_wedged_live.py` 单元文件 `$$` 转义 bug（改为 `$$$$` 并增加 systemd MainPID 校验）
  - [x] 19.2 **P2-1 修复**：`testsuite/test_recent_logins.py` flaky 治理（剥离外网网络请求、用例完全自包含与数据清理）
  - [x] 19.3 **P2-2 补充**：`plugins/op_waf` 老用户增量合并 live 验证用例补齐（含自定义规则、禁用规则与自建蜜罐路径升级验证）
  - [x] 19.4 **P2-3 修复**：`plugins/docker/index.py` 容器清日志 glob 贪婪前缀匹配漏洞（改用 `conFind.id` 64 位精准定位）
  - [x] 19.5 **P2-4 修复**：`plugins/op_waf/index.py` 中 `upgradeRules` 与 `upgradeRulesCli` 成功契约规范化（失败显式回退，拒绝假成功）
  - [x] 19.6 **全量回归与测试验证**：运行相关单元测试及门禁确保全部通过

- [x] **任务 20：左侧导航栏软件菜单升级提示角标（.softnum）定位修正与自适应布局优化 (`site.css`, `ensite.css`)**
  - [x] 20.1 **核心修复与自适应增强 (`web/static/css/site.css`)**：将 `.softnum` 定位重构为 `right: 12px; left: auto; top: 12px;`，整体左移进入菜单项胶囊背景内；增加 `min-width: 20px; width: auto; padding: 0 4px; box-sizing: border-box;` 支持多位数自适应；
  - [x] 20.2 **多样式文件同步与折叠模式优化 (`web/static/css/site.css`, `web/static/css/ensite.css`)**：同步 `ensite.css` 中 `.softnum` 样式；优化 mini 折叠侧边栏下 `body.sidebar-mini .softnum` 的定位为 `left: auto; right: 0;`，确保折叠与展开状态下角标与外框皆完整呈现；
  - [x] 20.3 **样式回归验证与测试**：验证中/英多语言下文字与角标布局、单双位数字显示效果及响应式切换，确保无溢出截断、无视觉破坏。

- [x] **任务 21：GitHub 下载链路性能优化与死链挂起根治 (`scripts/github_download.sh`, `op_waf`, `webstats`)**
  - [x] 21.1 **修复插件 GeoLite 下载逻辑与文件守卫 (`plugins/op_waf/install.sh`, `plugins/webstats/install.sh`)**：使用 GitHub 原生 Releases latest download 路径（`.../releases/latest/download/GeoLite2-*.mmdb`），解除对限流易超时的 GitHub API 依赖；预留安全 fallback（`latest`），防止空变量产生 `download//`；增加下载目标文件存在性检查（`[ -f ... ]`），避免未下载成功时 `cp` 报找不到文件
  - [x] 21.2 **核心基础库 `github_download.sh` 鲁棒性与性能重构 (`scripts/github_download.sh`)**：非法 URL 前置拦截（防 `//` 畸变与空资源）；为 `_gh_try_download` 引入 `timeout "$timeout"` 命令级硬超时与 `--dns-timeout=10 --connect-timeout=10`，彻底根治 Slowloris/代理慢速挂死数分钟的问题；实现 HTTP 404 资源不存在快速失败（Fast-Fail）熔断机制，不再盲目轮询 8 个代理；智能过滤在测速中已判明不可用的死节点，将备选单节点超时压缩至 15 秒内
  - [x] 21.3 **自动化回归测试与门禁验证**：扩充/编写专门的测试用例验证 404 快速失败、非法 URL 拦截、超时控制及原生 latest download，运行相关测试套件确保无破坏，清理临时排查文件

- [x] **任务 22：御风进程管理器操作报错修复与上下文作用域加固 (`plugins/yufeng_systemd/js/yufeng_systemd.js`)**
  - [x] 22.1 **根因修复与作用域解耦**：将 `control` 函数中 `layer.confirm` 回调内的 `this.request` 修正为 `yufeng_systemd.request`，并对 confirm 弹窗提示中的服务名称增加 `ysEsc` XSS 转义防护
  - [x] 22.2 **全局防错加固**：全面排查 `yufeng_systemd.js`，将内部所有方法（`init`, `get_list`, `save_service`, `request` 等）中不安全的 `this.` 引用统一显式绑定为 `yufeng_systemd.`，防止第三方库回调、事件冒泡或异步解构导致 `this` 丢失
  - [x] 22.3 **前端测试与回归验证**：在 `testsuite/js/systemd_d06_frontend_probe.js` 中增加针对 `control` 方法在 layer 回调上下文中执行的模拟测试用例，运行 `testsuite/test_systemd_d06_hardening.py` 验证 100% 通过

- [x] **任务 23：首页「PHP 安全基线」点击自动触发安全检测优化**
  - [x] 23.1 改造 `web/static/app/index.js` 的 `btSecurityCenter.showPhpSecModal`，支持立即弹窗并每次自动调用 `getPhpSecurityStatus(true)`
  - [x] 23.2 优化 `getPhpSecurityStatus` 与 `buildPhpModalHtml`，增加检测中（Scanning）按钮动画与防抖防并发机制，请求完成后自动刷新弹窗与首页角标
  - [x] 23.3 在 `testsuite/test_php_rescan_and_shop_policy.py` 中扩充自动化测试用例，覆盖点开自动触发检测与按钮状态逻辑
  - [x] 23.4 运行全量 PHP 安全基线与首页相关测试套件，确保 100% 通过
  - [x] 23.5 更新任务完成状态并清理临时测试文件

- [x] **任务 24：明文 HTTP 检测告警重构、按钮样式与位置对调、说明文件补充**
  - [x] 24.1 **弹窗内容与视觉重构 (`web/static/app/index.js`, 多语言包)**：重构明文 HTTP 安全风险弹窗，强化“标准 SSL 证书（域名 + CA 签发）”作为官方首选推荐方案；明确将自签证书定性为“应急过渡方案（无奈之举）”，指出其虽具基础防嗅探作用，但存在缺乏 CA 信任（浏览器报红拦截）、无法防范中间人攻击（MITM）等严重局限性；优化自签证书步骤说明
  - [x] 24.2 **弹窗按钮样式与布局对调 (`web/static/app/index.js`)**：
    - 将【前往面板设置】设为推荐主按钮，赋予原【一键启用自签证书】的绿色高亮样式（`#20a53a`），排在底部右侧；
    - 将【一键启用自签证书】作为次要/应急选项，样式对调为次要普通/灰色按钮，位置调整至底部左侧（`float: left; margin-left: 0;`）；
    - 保留【关闭】按钮排在底部右侧（普通取消样式），确保 `yes`/`btn2`/`btn3` 回调精确对应
  - [x] 24.3 **说明文件补充 (`文档/御风面板说明书/说明书.md`)**：
    - 在说明书全局系统设置安全章节新增「面板 SSL 证书安全配置指南」；
    - 详述明文 HTTP 传输风险、标准 SSL 证书完整配置与访问方法（域名解析、面板域名绑定、Let's Encrypt / ACME 免费申请与自动续期、自定义商用证书导入）；
    - 深刻阐述自签证书的作用（防明文窃听）与局限性（浏览器拦截警告、无法杜绝中间人攻击、易使管理员产生安全麻痹等），明确其权宜之计属性与应急访问步骤；
    - 提供从自签证书平滑切换为标准 SSL 证书的操作指引
  - [x] 24.4 **自动化测试、门禁回归与代码质量验证**：编写测试脚本验证弹窗逻辑、DOM 结构、按钮回调与样式规则，确保跨平台与多语言一致性，全量回归测试无破坏
  - [x] 24.5 **标准 SSL 证书操作步骤结构化细化 (`web/static/app/index.js`, 多语言包, `说明书.md`)**：
    - 弹窗推荐卡片消除大段纯文本，增补 4 大结构化标准操作步骤（域名解析 -> 绑定域名 -> 申请/部署 -> 加密访问），与下方自签步骤形成工整对照；
    - 补齐六国语言包对应文案并同步至 `template.index.json`、`template.json` 与 `lan.js`；
    - 深度细化《御风面板说明书》标准 SSL 证书配置章节，补充 80 端口放行、ACME 自动签发桥接验证及自定义证书导入等实操细节；
    - 扩充测试用例与全量回归验证。

- [x] **任务 25：版本号单一定义源改造 (`APP_VERSION`) 与组件变量自动拆解**
  - [x] 25.1 重构 `web/version.py`：以单一 `APP_VERSION` 作为定义入口，自动拆解出 `APP_RELEASE`、`APP_REVISION`、`APP_SMALL_VERSION`、`APP_SUFFIX` 并导出，保障模块层兼容
  - [x] 25.2 改造 `deploy.sh`：将版本更新与检测从 3~4 个独立变量 sed/grep 统一简化为操作 `APP_VERSION`
  - [x] 25.3 改造 `.github/workflows/release.yml`：CI 发布流校验直接比对 `APP_VERSION` 与 Release Tag
  - [x] 25.4 改造 `scripts/tools/build_edition.py`：版本读取改为提取 `APP_VERSION`
  - [x] 25.5 改造 `testsuite/test_supply_chain_guards.py`，新增 `testsuite/test_version_parsing.py` 覆盖拆解逻辑与兼容性
  - [x] **任务 26：修复拆包契约门禁失败 (`test_yf_package_contract.py`)**
  - [x] 26.1 定位 `test_11_every_shim_is_documented_and_alone` 失败根因：`panel.py` 中冗余引入了 `makeDirs` 的 shim，且该符号已在 `__init__.py` 中由 `shell.py` 重导出，触发防自我覆盖死循环保护契约断言
  - [x] 26.2 移除 `web/core/yf/panel.py` 中违规定义的 `makeDirs` shim，在 `makePhpConfStub` 内部改用标准 `os.makedirs(conf_dir, exist_ok=True)`
  - [x] 26.3 验证 `test_yf_package_contract.py` 与 `test_site_php_version_switch.py` 确保 100% 通过

- [x] **任务 27：御风面板 PHP 安装与升级功能鲁棒性优化与并发冲突根治**
  - [x] 27.1 **构建脚本 configure 退出码防御**：在各 PHP 编译安装脚本（`versions/80`~`85` 等）中检查 `./configure` 执行状态，失败时立即中止退出并清理 swap，根治因配置失败未中止引发的 `#error "Unknown SIZEOF_SIZE_T"` 虚假次生错误
  - [x] 27.2 **OS/源码级排他构建锁 (Build Lock)**：在各 PHP 版本的 `install.sh` 中增加基于文件锁的构建排他互斥机制，若同版本已有构建正在进行则立即报错退出，彻底消除源码目录并发竞态破坏
  - [x] 27.3 **面板任务队列并发防重与升级互斥**：在 `plugins/php/index.py` 中增强 `submitBaselineUpgrade` 与 `upgradeToBaseline`，检测同版本已在排队或执行中的安装/升级任务并拦截，在执行层增加双重锁保护；同步加固 `web/utils/plugin.py` 安装判定
  - [x] 27.4 **后台任务守护进程 (panel_task.py) 单例锁加固**：在 `panel_task.py` 启动阶段引入独占文件锁，杜绝双实例同时启动、并发分发任务或日志流穿插打乱
  - [x] 27.5 **自动化测试与全量回归验证**：编写测试用例覆盖 configure 防御、并发任务去重、构建锁互斥与单例守卫，确保全量测试套件 100% 通过

- [x] **任务 28：编译版 PHP 安装/升级构建锁父子进程自死锁治理 (`plugins/php`, `php_ver_guard.sh`)**
  - [x] 28.1 **构建锁可重入与继承机制**：在 `plugins/php/versions/common/php_ver_guard.sh` 中实现纯 POSIX 兼容的祖先进程判定函数 `_yf_php_is_ancestor_pid`，加锁时登记并导出当前 PID 环境变量
  - [x] 28.2 **嵌套调用与继承保护**：支持同进程内加锁深度计数，当子进程（或同一调用链）检测到锁已由祖先进程持有时判定为继承，跳过重复 flock 并标记继承状态；子进程释放锁时跳过释放底层物理锁，交由外层持有者统一释放
  - [x] 28.3 **测试套件扩充与全量回归**：在 `testsuite/test_php_install_upgrade_robustness.py` 补充父子进程继承、递归重入、子进程退出不破锁与跨进程真实互斥的自动化用例，运行全量测试验证 100% 通过

- [x] **任务 29：修复右上角检查更新弹窗中的无效 undefined 按钮 (`web/static/app/index.js`, `public.js`)**
  - [x] 29.1 修复 `web/static/app/index.js` 中 `checkUpdate()` 无更新提示弹窗：移除未定义的 `lan.public.know`，弹窗优化为仅保留一个「关闭」按钮的单按钮告知弹窗
  - [x] 29.2 加固 `web/static/app/public.js` 中 `localizeButtons` 对 `undefined`/`null` 等无效按钮的容错过滤
  - [x] 29.3 编写测试用例 `testsuite/test_check_update_dialog.py`，验证按钮合法性与无更新弹窗行为
  - [x] 29.4 修复 `checkUpdate()` 中 loading 提示的 i18n 键：由不存在的 `index.update_get` 对齐为全局六语言包正规键 `index.retrieving_updates_please_wait`，解决 CI 静态门禁 `user-visible-damage` UNKNOWN 报错

- [x] **任务 30：面板自升级可靠性与假成功根治 (`web/utils/system/update.py`, `index.js`)**
  - [x] 30.1 校验升级步骤、目标源码包结构和版本声明，拒绝不完整或错误的升级目录
  - [x] 30.2 严格检查解压回退、版本号落盘及依赖安装结果；失败如实报错并保留重试能力
  - [x] 30.3 修复安装请求异常被前端误判为成功，补齐服务端与前端回归测试
  - [x] 30.4 运行升级专项、静态门禁与全量回归，清理临时排查文件

- [x] **任务 31：网站列表 SSL 状态显示修复与 ACME 自动续签加固**
  - [x] 31.1 重构 `yf.getCertName` 证书解析引擎 (`web/core/yf/system.py`)：优先使用 `cryptography.x509` 解析，增强 pyOpenSSL 兜底容错
  - [x] 31.2 修复网站列表 SSL 状态与证书路径提取 (`web/admin/site/site.py`)：从 vhost 配置动态提取 `ssl_certificate` 路径，完善状态降级
  - [x] 31.3 修复 ACME 自动续签定时任务与历史自愈机制 (`web/admin/setup/init_cron.py`)：移除 `--standalone` 与 `--force`，实现存量任务自动校准
  - [x] 31.4 编写专门测试用例并执行全量门禁回归验证

- [x] **任务 32：计划任务系统核心任务防误删与展示加固**
  - [x] 32.1 后端防误删硬拦截 (`web/admin/crontab/__init__.py`, `web/utils/crontab.py`)：对系统内置核心任务（以 `[勿删]` 开头）在删除与修改接口中增加安全拦截，防止误删或改乱
  - [x] 32.2 前端安全展示与操作受控 (`web/static/app/crontab.js`)：对系统内置任务禁用复选框、移除「编辑」和「删除」按钮，仅保留「执行」与「日志」
  - [x] 32.3 徽章视觉优化 (`crontab.js`)：任务名称优雅替换 `[勿删]` 为「系统任务」绿色徽章
  - [x] 32.4 编写专门测试用例并执行全量门禁回归验证

- [x] **任务 33：计划任务自动创建与系统内置任务多语言国际化显示优化**
  - [x] 33.1 多语言词条扩充与对齐：在 6 种语言包（`zh-CN`, `zh-TW`, `en`, `de`, `fr`, `it`）的 `template.crontab.json` 和 `lan.js` 中补充内置任务及检查任务的多语言映射
  - [x] 33.2 前端任务名称智能翻译引擎 (`web/static/app/crontab.js`)：实现 `translateTaskName(name)`，精准解析系统内置任务、备份任务（数据库/网站/目录）、日志切割、释放内存、网站监控等
  - [x] 33.3 后端 `getCrontabHuman` 同步支持 (`web/utils/crontab.py`)：补充 `name_display` 国际化计算，保持前后端契约完整与兼容
  - [x] 33.4 自动化测试与全量回归验证：编写测试用例验证多语言环境下任务名称正确翻译，确保 i18n 与代码质量门禁 100% 通过

- [x] **任务 34：门禁测试未通过修复与回归治理**
  - [x] 34.1 修复 `test_upgrade_transaction.py` 中 `_build_env_update_script` 的 PATH 设置与 bash 检测，确保依赖更新脚本退出码正确传递且 Windows 环境兼容；移除冗余 `export PATH` 避免误触 `export_doublequote` 棘轮门禁规则
  - [x] 34.2 修复 `test_crontab_sync_status.py` 中 `test_04d_frontend_marks_rejected_tasks` 任务名渲染断言，兼容 `display_name`
  - [x] 34.3 运行 `python scripts/tools/export_lang_carriers.py --apply` 同步多语言载体，消除 `test_lang_carrier_derivation.py` 漂移
  - [x] 34.4 优化 `testsuite/test_crontab_manual_run_force.py` 中 `_run` 的 `current_hm` 逻辑，杜绝环境残留污染
  - [x] 34.5 运行全量门禁回归，确保 100% 通过

- [x] **任务 35：面板升级可靠性加固与竞态自愈优化 (`web/utils/system/update.py`, `panel.py`, `github.py`)**
  - [x] 35.1 **源码目录清理时序重构**：将 `step == 'install'` 中的临时包删除移至全部校验与依赖更新成功之后；失败时保留包体，杜绝重试时「更新源码包未找到」误报；若目录缺失但 zip 仍在时自动解压自愈
  - [x] 35.2 **依赖更新 pip 内存优化**：在 `_build_env_update_script` 中为 `pip3 install` 强制增加 `--no-cache-dir`，降低低配服务器内存峰值
  - [x] 35.3 **优雅延迟重启消除 HTTP 竞态断连**：加固 `yf.restartPanel()` 支持异步延迟 1 秒重启，保证 Gunicorn 完整下发 HTTP JSON 响应，杜绝工作进程提前被 kill 造成假失败
  - [x] 35.4 **GitHub 下载链路双通道与重试加固**：`wget` 增加 `--tries=2 --waitretry=1 -c` 断点续传重试；Tag 动态源码包下载异常时自动回退至 Release 静态构建附件 `yf.zip`
  - [x] 35.5 **编写自动化回归测试与验证**：编写 `testsuite/test_upgrade_reliability_hardening.py`，覆盖清理时序、pip 参数、延迟重启、双通道下载 fallback 等，测试 100% 通过

- [x] **任务 36：门禁拦截修复与代码质量棘轮归零 (`panel_task.py`, `test_system_a08_hardening.py`)**
  - [x] 36.1 **消除 `silent_except` 违规 (`panel_task.py`)**：将第 538 行 `except Exception: pass` 改造为异常警告日志记录，彻底消除静默吞异常，使 `silent_except` 计数归零（恢复至基线 0）
  - [x] 36.2 **兼容双通道下载反证断言 (`testsuite/test_system_a08_hardening.py`)**：在 `test_04_mutation_positive_control` 中将 `len(urls) == 1` 断言兼容为 `len(urls) >= 1` 并断言所有调用 URL 均命中注入特征，适配双通道降级下载机制
  - [x] 36.3 **单元测试与代码质量门禁验证**：单独验证 `test_system_a08_hardening.py`、`test_request_security_hardening.py` 及 `scripts/verify_code_quality.py`
  - [x] 36.4 **全量门禁回归验证**：运行 `python testsuite/run_all.py`，确保所有测试用例与静态门禁 100% 通过，收尾更新任务状态

- [x] **任务 37：服务存活巡检单元匹配加固与误报消除 (`web/core/service_patrol.py`)**
  - [x] 37.1 **精确同名单元最高优先级**：在 `pick_unit_for_plugin(plugin, units)` 中，当同名单元 `<plugin>.service`（如 `mysql.service`）命中时，赋予其绝对最高优先级直接返回，彻底消除带 `-`（如 `mysql-apt.service`）的失效历史服务因 ASCII 字典序抢占导致的误报
  - [x] 37.2 **严密路径边界防误判**：加固插件工作目录与二进制路径匹配，增加词边界校验，避免 `/server/mysql-apt`、`/server/mysql-community` 误作为 `/server/mysql` 前缀被匹配
  - [x] 37.3 **自动化单测与防回归验证**：在 `testsuite/test_install_fake_success_guards.py` 中增加同名服务优先与前缀隔离测试用例，运行相关单测确保 100% 通过

- [x] **任务 38：门禁未通过修复（多语言 soft.already_latest 补齐与插件缓存清理 silent_except 治理）**
  - [x] 38.1 **消除插件缓存清理处 `silent_except` 违规 (`web/admin/plugins/__init__.py`)**：在 `clear_cache` 异常处理中将 `pass` 替换为 `_log.debug`，使代码质量棘轮 `silent_except` 归零恢复基线
  - [x] 38.2 **补齐六国语言包 `soft.already_latest` 映射 (`web/static/language/*/lan.js`)**：在 zh-CN、zh-TW、en、de、fr、it 六语言的 `lan.js` 中新增 `soft.already_latest` 键值
  - [x] 38.3 **派生同步 `.json` 语言包载体**：运行 `python scripts/tools/export_lang_carriers.py --apply`，同步生成 `template.soft.json` 等载体，确保单源派生一致
  - [x] 38.4 **静态门禁与单元测试验证**：运行 `python testsuite/run_all.py --static`、`test_i18n_web_backend_scope.py`、`test_request_security_hardening.py`，确保静态检查和相关用例 100% 通过

- [x] **任务 39：御风面板 SSH 管理全面升级（ED25519 升级、后台生效修复与开关交互治理）**
  - [x] 39.1 **全面升级现代 ED25519 并修复后台密钥生效与权限缺陷 (`web/utils/firewall.py`)**：清理重复定义的 `resetRootSshKey`；生成标准高强度 ED25519 密钥对；生成后将公钥严格写入 `/root/.ssh/authorized_keys` 并纠正权限（目录 700、authorized_keys 与私钥 600、公钥 644）；健全 `checkRootSshKey` 与写盘错误检测
  - [x] 39.2 **修复前端开关文案颠倒、取消回滚错乱与状态同步缺陷 (`web/static/app/firewall.js`)**：修正 `setSshPubkeyStatus`、`setSshRootStatus`、`setSshPassStatus`、`setMstscStatus` 的文案三元判断逻辑（开启提示开启、关闭提示禁止）；优化原生事件交互防止取消乱跳；确认执行后精准同步状态；关闭密码登录前增加防自锁警告
  - [x] 39.3 **自动化回归测试与门禁验证**：扩充 `testsuite/test_firewall_a04_hardening.py`，覆盖 ED25519 密钥生成、authorized_keys 同步写入与权限断言；运行全量测试与代码质量门禁确保 100% 通过
