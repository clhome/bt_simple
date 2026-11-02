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
- [ ] **任务 7：插件 i18n 升级门禁修复与规范对齐 (`test_plugins_i18n_upgrade.py`)**
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

