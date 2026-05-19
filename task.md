# Task: 增加 bs 指令并替换提示信息

## 项目描述
BtSimple (原 mdserver-web) 是一个 Linux 面板。目前主要通过 `mw` 命令进行命令行操作。

## 开发规范
- 统一使用 UTF-8 (无 BOM) 格式。
- 遵循原有代码风格。
- 增加 `bs` 命令作为 `mw` 的别名。
- 保持 `mw` 命令兼容。
- 将所有面向用户的提示信息中的 `mw` 替换为 `bs`。

## Task List
- [x] 调研并确认 `mw` 命令的所有定义和使用位置 @done(2026-05-14 16:22)
- [x] 修改 `scripts/init.d/mw.tpl` 中的提示信息，将 `mw` 替换为 `bs` @done(2026-05-14 16:25)
- [x] 修改 `panel_tools.py` 中的提示信息 @done(2026-05-14 16:26)
- [x] 修改 `cli.sh` 中的提示信息 @done(2026-05-14 16:27)
- [x] 修改安装/更新脚本，确保同时创建 `mw` 和 `bs` 的软链接 @done(2026-05-14 16:35)
    - [x] `scripts/install.sh`
    - [x] `scripts/install_dev.sh`
    - [x] `scripts/update.sh`
    - [x] `scripts/update_dev.sh`
    - [x] `deploy.sh`
- [x] 在 `web/admin/setup/init_cmd.py` 中增加 `bs` 指令的自动创建逻辑 @done(2026-05-14 16:38)
- [x] 检查其他文档或代码中的提示（如 `README.md`, `cmd.md`, `config.js` 等） @done(2026-05-14 16:40)
- [x] 修复 `bs uninstall` 卸载失败的问题 @done(2026-05-14 17:48)
    - [x] 在 `scripts/init.d/mw.tpl` 中增加 `uninstall` 处理逻辑 @done(2026-05-14 17:45)
    - [x] 优化 `panel_tools.py` 对未知命令的处理逻辑 @done(2026-05-14 17:47)
- [x] 优化 `scripts/uninstall.sh` 脚本 @done(2026-05-14 17:53)
    - [x] 动态检测已安装的 PHP 版本并卸载 @done(2026-05-14 17:52)
    - [x] 优化其他组件（MySQL/Redis等）的检测与卸载逻辑 @done(2026-05-14 17:53)

# Task: 优化宝塔面板迁移逻辑，实现软件扫描、自动安装与数据无缝接管

## 项目描述
宝塔面板安装软件与当前开发面板安装路径、管理机制存在差异。迁移宝塔面板时直接保留软件目录会因判定为“已安装”而导致其无法运行。本次改动旨在分析原本的宝塔软件和版本，在新面板中自动异步重装，并将旧的数据无缝迁入接管。

## 开发规范
- 统一使用 UTF-8 (无 BOM) 格式。
- 保证数据备份的绝对安全，不丢失任何用户原本的建站和数据库数据。
- 逻辑代码模块化，保持高内聚低耦合。

## Task List
- [x] 方案构思：设计宝塔面板迁移时的软件扫描、目录隔离与数据接管方案 @done(2026-05-18 13:30)
- [x] 修改 `deploy.sh` 中的 `migrate_from_bt`：@done(2026-05-18 13:35)
    - [x] 编写宝塔软件扫描函数 `scan_bt_installed_software()`，获取 MySQL, Redis, OpenResty, PHP, PostgreSQL 的版本 @done(2026-05-18 13:35)
    - [x] 导出扫描结果为 `/tmp/bt_migrated_software.json`，并在代码部署后写入 `${PANEL_DIR}/data/bt_migrated_software.json` @done(2026-05-18 13:35)
    - [x] 对存在冲突的原宝塔软件目录（mysql, redis, php, postgresql 等）及原数据目录进行重命名备份隔离（如 `mysql_bt_bak`），避免判定冲突 @done(2026-05-18 13:35)
- [x] 编写 Python 后端初始化迁移逻辑 `web/admin/setup/bt_migration.py`：@done(2026-05-18 13:40)
    - [x] 编写检测 `bt_migrated_software.json` 的逻辑 @done(2026-05-18 13:40)
    - [x] 实现智能版本匹配：自动比对插件所支持的版本，生成对应安装任务 @done(2026-05-18 13:40)
    - [x] 调用插件安装接口将这些软件放入面板任务队列中自动安装 @done(2026-05-18 13:40)
    - [x] 在 `web/admin/setup/__init__.py` 中调用此逻辑 @done(2026-05-18 13:41)
- [x] 编写数据恢复的一键导入指令 `restore_bt_data` (可在 `panel_tools.py` 或单独脚本中定义)：@done(2026-05-18 13:50)
    - [x] 能够一键恢复 MySQL 的数据库文件，修改权限并安全接管 @done(2026-05-18 13:50)
    - [x] 能够一键恢复 Redis 等缓存的配置与快照数据 @done(2026-05-18 13:50)
- [x] 验证整体迁移方案并提供详尽的操作说明 @done(2026-05-18 13:58)

# Task: 解决从 mdserver-web 迁移/升级时说明文档无法覆盖的问题

## 项目描述
在执行从 mdserver-web 迁移升级至 bt_simple 时，部署脚本通过 `deploy_code` 重构和部署代码，但其 `CODE_ITEMS` 白名单中缺少了 `README.md` 与 `RELEASE_TEMPLATE.md`，导致迁移后原本遗留在目录下的旧说明文档无法得到覆盖更新。

## 开发规范
- 统一使用 UTF-8 (无 BOM) 格式。

## Task List
- [x] 在 `deploy.sh` 脚本的 `deploy_code()` 部署白名单中加入 `README.md` 和 `RELEASE_TEMPLATE.md` @done(2026-05-19 08:55)

# Task: 解决迁移后版本号始终显示为 1.0.6 且需二次在 Web 端升级的问题

## 项目描述
在任何迁移或部署场景下，版本号容易因为网络（GitHub API 被强墙、无外网等）获取失败导致 `.version` 文件为空或未生成。一旦没有 `.version` 文件，系统会强行兜底显示为硬编码版本 `1.0.6`，使得用户不得不再次在前端手动点击一次升级。

## 开发规范
- 统一使用 UTF-8 (无 BOM) 格式。

## Task List
- [x] 在 `deploy.sh` 中增加 `set_panel_version` 统一版本自解析函数，支持无网/弱网下优先解析本地 `web/version.py` 版本写入 `.version` 机制 @done(2026-05-19 08:56)
- [x] 替换三处重复且易受网络波动影响的 `curl` 版本写入代码为 `set_panel_version` @done(2026-05-19 08:56)
- [x] 将 `web/version.py` 硬编码的兜底默认版本由 `1.0.6` 升级为 `1.0.7` 以对齐最新特性 @done(2026-05-19 08:57)


# Task: 优化 PostgreSQL 管理器备份与导入功能

## 项目描述
优化 PostgreSQL 管理器的备份与导入交互。主要优化点：
1. 将数据库列表中 “未备份” 状态文字更改为 “备份/导入”（保留点击显示备份详情弹窗的功能）。
2. 在数据库备份详情弹窗中，增加 “同步”（扫描服务器备份目录中后缀名为 `.gz` 的备份，使其支持导入）和 “本地上传” 功能。

## 开发规范
- 统一使用 UTF-8 (无 BOM) 格式。
- 遵循原有代码风格。
- 保证中英文多语言一致性。
- 代码改动应最小化，保持高内聚低耦合。

## Task List
- [x] 调研 PostgreSQL 管理器原有的前端和后端备份逻辑与代码位置 @done(2026-05-19 09:06)
- [x] 备份/导入文字与链接优化：将数据库列表中的 “未备份” 或备份状态字段修改为 “备份/导入” @done(2026-05-19 09:06)
- [x] 编写或优化后端备份同步接口：扫描指定备份目录下所有 `.gz` 文件，并提供支持导入的列表 @done(2026-05-19 09:06)
- [x] 编写或优化后端本地上传接口：支持在备份详情中上传备份文件并保存到指定备份目录 @done(2026-05-19 09:06)
- [x] 编写前端备份详情页面交互：增加 “同步” 和 “本地上传” 按钮，实现对应的前端交互与文件上传逻辑 @done(2026-05-19 09:06)
- [x] 整合验证：测试备份、同步、上传、导入、删除全流程，确保没有 Bug @done(2026-05-19 09:06)
- [x] 列表排序优化：确保备份详情列表中的备份文件按备份时间从新到旧降序排列 @done(2026-05-19 09:10)

# Task: 修复 PostgreSQL 管理器备份、同步、上传与显示 Bug

## 项目描述
在 PostgreSQL 管理器使用中，修复以下问题：
1. 文件上传在 Windows 开发调试环境下（以及某些权限受限环境）因 `os.chown` 方法缺失/无权限导致“上传错误”的 bug。
2. 后端 `getArgs()` 在接收前端传来的多参数 JSON 字符串时分割逻辑损坏，导致同步点击失效等诸多 bug。
3. 之前备份的以及用户上传的备份文件，因为不满足严格的 `db_dbname_` 前缀规则，在非同步状态下无法显示出来的 bug。

## 开发规范
- 统一使用 UTF-8 (无 BOM) 格式。
- 遵循原有代码风格。
- 保证中英文多语言一致性。
- 代码改动应最小化，保持高内聚低耦合。

## Task List
- [x] 在 `task.md` 中创建此修复 Task 与 Task List @done(2026-05-19 09:25)
- [x] 修复 `web/admin/files/files.py` 中 `os.chown` 在 Windows 等环境下的缺失/报错问题 @done(2026-05-19 09:27)
- [x] 优化 `plugins/postgresql/index.py` 中 `getArgs` 的参数解析，使其完美支持多参数的 JSON 解析 @done(2026-05-19 09:28)
- [x] 优化 `plugins/postgresql/index.py` 中 `getDbBackupListFunc` 过滤逻辑，兼容 `dbname_` 及 `db_dbname_` 前缀备份文件，使其不点同步也能正确显示 @done(2026-05-19 09:29)
- [x] 整合验证备份、同步、上传以及列表显示功能 @done(2026-05-19 09:30)
- [x] 彻底重构并修复 `plugins/postgresql/index.py` 中 `pgBack` 备份函数，替换硬编码路径并增加 Windows 兼容及执行成功校验 @done(2026-05-19 09:31)
- [x] 彻底重构并修复 `plugins/postgresql/index.py` 中 `pgBackList` 获取备份列表函数，解除 `i.split("_")[0]` 造成的前缀匹配屏蔽，调用通用的 `getDbBackupListFunc` 过滤逻辑 @done(2026-05-19 09:31)
- [x] 彻底重构并修复 `plugins/postgresql/index.py` 中 `importDbBackup` 数据库还原函数，纠正错配参数并修复硬编码指令和用户权限崩溃 @done(2026-05-19 09:31)

# Task: 优化 PostgreSQL 备份文件命名规则以体现版本号

## 项目描述
优化 PostgreSQL 面板的备份命名机制，让生成的备份文件名称中包含当前安装的 PostgreSQL 对应版本号（如 `pg_backup_v18.3_dbname_时间.gz`），并升级备份过滤匹配逻辑以完美兼容新老两种命名的文件展示。

## 开发规范
- 统一使用 UTF-8 (无 BOM) 格式。

## Task List
- [x] 在 `task.md` 中登记新任务 @done(2026-05-19 09:33)
- [x] 增加通用版本号获取方法 `getPgVersion()` @done(2026-05-19 09:34)
- [x] 重构 `pgBack()` 备份数据库的文件命名为 `pg_backup_v{version}_{dbname}_{cur_time}.gz` @done(2026-05-19 09:34)
- [x] 重构 `setDbBackup()` 面板主备份函数的文件命名，与弹窗的命名格式统一 @done(2026-05-19 09:34)
- [x] 升级 `getDbBackupListFunc()` 过滤匹配逻辑，兼容体现版本号的最新备份格式，确保完美展示 @done(2026-05-19 09:34)
- [x] 整合验证备份文件产生与完美列表展现 @done(2026-05-19 09:34)

# Task: 在MySQL管理器中显示数据库创建时间并按创建时间降序排列

## 项目描述
在数据库管理列表中显示每一个数据库的“创建时间”。无论使用的是哪一个MySQL/MariaDB版本（MySQL、MySQL-Community、MariaDB），列表都必须支持显示“创建时间”这一列，并且数据库列表必须按“创建时间”（`addtime`）降序排列。

## 开发规范
- 统一使用 UTF-8 (无 BOM) 格式。
- 遵循原有代码风格。
- 保证所有 MySQL/MariaDB 版本插件的功能同步性与一致性。
- 代码改动应最小化，保持高内聚低耦合。

## Task List
- [x] 在 `task.md` 中登记此任务 @done(2026-05-19 09:44)
- [x] 修改 MySQL 插件的后端排序逻辑（`plugins/mysql/index.py`）： @done(2026-05-19 09:47)
    - [x] 修改 `getDbList` 的排序为 `addtime desc, id desc` @done(2026-05-19 09:47)
    - [x] 修改 `getMasterDbList` 的排序为 `addtime desc, id desc` @done(2026-05-19 09:47)
- [x] 修改 MySQL 社区版插件的后端排序逻辑（`plugins/mysql-community/index.py`）： @done(2026-05-19 09:47)
    - [x] 修改 `getDbList` 的排序为 `addtime desc, id desc` @done(2026-05-19 09:47)
    - [x] 修改 `getMasterDbList` 的排序为 `addtime desc, id desc` @done(2026-05-19 09:47)
- [x] 修改 MariaDB 插件的后端排序逻辑（`plugins/mariadb/index.py`）： @done(2026-05-19 09:47)
    - [x] 修改 `getDbList` 的排序为 `addtime desc, id desc` @done(2026-05-19 09:47)
    - [x] 修改 `getMasterDbList` 的排序为 `addtime desc, id desc` @done(2026-05-19 09:47)
- [x] 修改 MySQL 插件的前端渲染逻辑（`plugins/mysql/js/mysql.js`）： @done(2026-05-19 09:50)
    - [x] 在 `dbList` 数据库列表表头 `thead` 增加 `创建时间` 列 @done(2026-05-19 09:50)
    - [x] 在 `dbList` 数据库列表行 `tbody` 中渲染 `addtime` 字段数据 @done(2026-05-19 09:50)
- [x] 修改 MySQL 社区版插件的前端渲染逻辑（`plugins/mysql-community/js/mysql-community.js`）： @done(2026-05-19 09:50)
    - [x] 在 `dbList` 数据库列表表头 `thead` 增加 `创建时间` 列 @done(2026-05-19 09:50)
    - [x] 在 `dbList` 数据库列表行 `tbody` 中渲染 `addtime` 字段数据 @done(2026-05-19 09:50)
- [x] 修改 MariaDB 插件的前端渲染逻辑（`plugins/mariadb/js/mariadb.js`）： @done(2026-05-19 09:50)
    - [x] 在 `dbList` 数据库列表表头 `thead` 增加 `创建时间` 列 @done(2026-05-19 09:50)
    - [x] 在 `dbList` 数据库列表行 `tbody` 中渲染 `addtime` 字段数据 @done(2026-05-19 09:50)
- [x] 整合验证所有三个插件的功能，确保界面显示正常、排序正确且无中文乱码。 @done(2026-05-19 09:51)


# Task: 优化数据库备份文件命名，以数据库版本号作为命名前缀

## 项目描述
为了更好地识别数据库备份所属的数据库版本，需要将备份文件的前缀由原本硬编码的 `db_` 改为包含对应版本号的动态前缀（如 `mysql57_`, `mysql80_`, `mariadb104_` 等），其中版本号需根据当前安装的数据库版本动态解析（例如：5.7.x 解析为 57，10.4.x 解析为 104），同时保证过滤检索机制向下兼容旧版 `db_` 前缀的备份，确保用户原有备份资产完全可用。

## 开发规范
- 统一使用 UTF-8 (无 BOM) 格式。
- 遵循原有代码风格。
- 保证历史旧版前缀 `db_` 的备份文件完美向下兼容，对用户不可丢失、完全可读。

## Task List
- [x] 在 `task.md` 中登记此任务 @done(2026-05-19 10:05)
- [x] 优化 MySQL 插件的备份生成及检索过滤： @done(2026-05-19 10:06)
    - [x] 重构 `scripts/backup.py` 中 `backupDatabase` 生成的备份文件前缀为动态版本号（如 `mysql57_`） @done(2026-05-19 10:06)
    - [x] 重构 `plugins/mysql/index.py` 中 `getDbBackupListFunc`，使其同时完美检索出新前缀与历史旧版 `db_` 前缀的备份文件 @done(2026-05-19 10:06)
- [x] 优化 MySQL 社区版插件的备份生成及检索过滤： @done(2026-05-19 10:09)
    - [x] 重构 `plugins/mysql-community/scripts/backup.py` 中 `backupDatabase` 生成的备份文件前缀为动态版本号（如 `mysql80_`） @done(2026-05-19 10:09)
    - [x] 重构 `plugins/mysql-community/index.py` 中 `getDbBackupListFunc`，使其同时完美检索出新前缀与历史旧版 `db_` 前缀的备份文件 @done(2026-05-19 10:09)
- [x] 优化 MariaDB 插件的备份生成及检索过滤： @done(2026-05-19 10:13)
    - [x] 重构 `plugins/mariadb/scripts/backup.py` 中 `backupDatabase` 生成的备份文件前缀为动态版本号（如 `mariadb104_`） @done(2026-05-19 10:13)
    - [x] 重构 `plugins/mariadb/index.py` 中 `getDbBackupListFunc`，使其同时完美检索出新前缀与历史旧版 `db_` 前缀的备份文件 @done(2026-05-19 10:13)
- [x] 整合验证所有三个插件的备份生成与显示功能，确保历史旧版备份与新版本前缀备份完美共存。 @done(2026-05-19 10:14)


# Task: 优化 PostgreSQL 插件备份文件命名，以数据库版本号作为命名前缀

## 项目描述
为了与 MySQL/MariaDB 保持统一，需要将 PostgreSQL 备份文件的前缀由原本的 `pg_backup_v{version}_` 改为包含对应版本号的动态前缀（如 `postgre183_`，其中 183 代表 PostgreSQL 版本 18.3），版本号需要根据当前安装的版本动态解析。同时，检索机制必须向下兼容旧版 `pg_backup_v{version}_` 以及历史更早的 `db_` 前缀备份。

## 开发规范
- 统一使用 UTF-8 (无 BOM) 格式。
- 遵循原有代码风格。
- 保证所有历史格式备份文件完美向下兼容，不可丢失。

## Task List
- [x] 在 `task.md` 中登记此任务 @done(2026-05-19 10:15)
- [x] 优化 PostgreSQL 插件的备份生成及检索过滤： @done(2026-05-19 10:17)
    - [x] 重构 `plugins/postgresql/index.py` 中 `setDbBackup` 与 `pgBack` 生成的备份文件前缀为动态版本号（如 `postgre183_`） @done(2026-05-19 10:17)
    - [x] 重构 `plugins/postgresql/index.py` 中 `getDbBackupListFunc`，使其同时完美检索出新前缀、历史 `pg_backup_v{version}_` 前缀以及更早的旧前缀备份文件 @done(2026-05-19 10:17)
- [x] 整合验证 PostgreSQL 插件的备份生成与显示功能，确保新旧备份完美共存。 @done(2026-05-19 10:17)


# Task: 优化 PostgreSQL 插件界面、排序与模态框尺寸

## 项目描述
为了给用户更好的视觉和交互体验，在 PostgreSQL 插件管理器中增加“创建时间”字段展示，并使数据库列表按照创建时间降序排列。同时拉大模态框的长度和宽度，调整内容展示高度，避免默认弹出框产生多余的滚动条。

## Task List
- [x] 在 `task.md` 中登记此任务 @done(2026-05-19 10:20)
- [x] 优化 PostgreSQL 数据库列表排序及字段展示：
    - [x] 修改 `plugins/postgresql/index.py` 中 `getDbList` 查询排序，使其按 `addtime desc, id desc` 降序排列 @done(2026-05-19 10:20)
    - [x] 修改 `plugins/postgresql/js/postgresql.js` 中的 `dbList` 渲染逻辑，在表格中增加“创建时间”这一列并正确展示 `addtime` 字段 @done(2026-05-19 10:20)
- [x] 优化模态框尺寸与布局以避免滚动条：
    - [x] 修改 `plugins/postgresql/index.html` 中的 `resetPluginWinWidth` 宽度至 `950px` @done(2026-05-19 10:20)
    - [x] 在 `plugins/postgresql/index.html` 中新增调用 `resetPluginWinHeight(650)` 以拉大高度 @done(2026-05-19 10:20)
    - [x] 将 `.soft-man-con` 容器高度增大为 `570px`，实现完美填充且无外层滚动条 @done(2026-05-19 10:20)



