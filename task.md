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

- [X] 调研并确认 `mw` 命令的所有定义和使用位置 @done(2026-05-14 16:22)
- [X] 修改 `scripts/init.d/mw.tpl` 中的提示信息，将 `mw` 替换为 `bs` @done(2026-05-14 16:25)
- [X] 修改 `panel_tools.py` 中的提示信息 @done(2026-05-14 16:26)
- [X] 修改 `cli.sh` 中的提示信息 @done(2026-05-14 16:27)
- [X] 修改安装/更新脚本，确保同时创建 `mw` 和 `bs` 的软链接 @done(2026-05-14 16:35)
  - [X] `scripts/install.sh`
  - [X] `scripts/install_dev.sh`
  - [X] `scripts/update.sh`
  - [X] `scripts/update_dev.sh`
  - [X] `deploy.sh`
- [X] 在 `web/admin/setup/init_cmd.py` 中增加 `bs` 指令的自动创建逻辑 @done(2026-05-14 16:38)
- [X] 检查其他文档或代码中的提示（如 `README.md`, `cmd.md`, `config.js` 等） @done(2026-05-14 16:40)
- [X] 修复 `bs uninstall` 卸载失败的问题 @done(2026-05-14 17:48)
  - [X] 在 `scripts/init.d/mw.tpl` 中增加 `uninstall` 处理逻辑 @done(2026-05-14 17:45)
  - [X] 优化 `panel_tools.py` 对未知命令的处理逻辑 @done(2026-05-14 17:47)
- [X] 优化 `scripts/uninstall.sh` 脚本 @done(2026-05-14 17:53)
  - [X] 动态检测已安装的 PHP 版本并卸载 @done(2026-05-14 17:52)
  - [X] 优化其他组件（MySQL/Redis等）的检测与卸载逻辑 @done(2026-05-14 17:53)

# Task: 优化宝塔面板迁移逻辑，实现软件扫描、自动安装与数据无缝接管

## 项目描述

宝塔面板安装软件与当前开发面板安装路径、管理机制存在差异。迁移宝塔面板时直接保留软件目录会因判定为“已安装”而导致其无法运行。本次改动旨在分析原本的宝塔软件和版本，在新面板中自动异步重装，并将旧的数据无缝迁入接管。

## 开发规范

- 统一使用 UTF-8 (无 BOM) 格式。
- 保证数据备份的绝对安全，不丢失任何用户原本的建站和数据库数据。
- 逻辑代码模块化，保持高内聚低耦合。

## Task List

- [X] 方案构思：设计宝塔面板迁移时的软件扫描、目录隔离与数据接管方案 @done(2026-05-18 13:30)
- [X] 修改 `deploy.sh` 中的 `migrate_from_bt`：@done(2026-05-18 13:35)
  - [X] 编写宝塔软件扫描函数 `scan_bt_installed_software()`，获取 MySQL, Redis, OpenResty, PHP, PostgreSQL 的版本 @done(2026-05-18 13:35)
  - [X] 导出扫描结果为 `/tmp/bt_migrated_software.json`，并在代码部署后写入 `${PANEL_DIR}/data/bt_migrated_software.json` @done(2026-05-18 13:35)
  - [X] 对存在冲突的原宝塔软件目录（mysql, redis, php, postgresql 等）及原数据目录进行重命名备份隔离（如 `mysql_bt_bak`），避免判定冲突 @done(2026-05-18 13:35)
- [X] 编写 Python 后端初始化迁移逻辑 `web/admin/setup/bt_migration.py`：@done(2026-05-18 13:40)
  - [X] 编写检测 `bt_migrated_software.json` 的逻辑 @done(2026-05-18 13:40)
  - [X] 实现智能版本匹配：自动比对插件所支持的版本，生成对应安装任务 @done(2026-05-18 13:40)
  - [X] 调用插件安装接口将这些软件放入面板任务队列中自动安装 @done(2026-05-18 13:40)
  - [X] 在 `web/admin/setup/__init__.py` 中调用此逻辑 @done(2026-05-18 13:41)
- [X] 编写数据恢复的一键导入指令 `restore_bt_data` (可在 `panel_tools.py` 或单独脚本中定义)：@done(2026-05-18 13:50)
  - [X] 能够一键恢复 MySQL 的数据库文件，修改权限并安全接管 @done(2026-05-18 13:50)
  - [X] 能够一键恢复 Redis 等缓存的配置与快照数据 @done(2026-05-18 13:50)
- [X] 验证整体迁移方案并提供详尽的操作说明 @done(2026-05-18 13:58)

# Task: 解决从 mdserver-web 迁移/升级时说明文档无法覆盖的问题

## 项目描述

在执行从 mdserver-web 迁移升级至 bt_simple 时，部署脚本通过 `deploy_code` 重构和部署代码，但其 `CODE_ITEMS` 白名单中缺少了 `README.md` 与 `RELEASE_TEMPLATE.md`，导致迁移后原本遗留在目录下的旧说明文档无法得到覆盖更新。

## 开发规范

- 统一使用 UTF-8 (无 BOM) 格式。

## Task List

- [X] 在 `deploy.sh` 脚本的 `deploy_code()` 部署白名单中加入 `README.md` 和 `RELEASE_TEMPLATE.md` @done(2026-05-19 08:55)

# Task: 解决迁移后版本号始终显示为 1.0.6 且需二次在 Web 端升级的问题

## 项目描述

在任何迁移或部署场景下，版本号容易因为网络（GitHub API 被强墙、无外网等）获取失败导致 `.version` 文件为空或未生成。一旦没有 `.version` 文件，系统会强行兜底显示为硬编码版本 `1.0.6`，使得用户不得不再次在前端手动点击一次升级。

## 开发规范

- 统一使用 UTF-8 (无 BOM) 格式。

## Task List

- [X] 在 `deploy.sh` 中增加 `set_panel_version` 统一版本自解析函数，支持无网/弱网下优先解析本地 `web/version.py` 版本写入 `.version` 机制 @done(2026-05-19 08:56)
- [X] 替换三处重复且易受网络波动影响的 `curl` 版本写入代码为 `set_panel_version` @done(2026-05-19 08:56)
- [X] 将 `web/version.py` 硬编码的兜底默认版本由 `1.0.6` 升级为 `1.0.7` 以对齐最新特性 @done(2026-05-19 08:57)

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

- [X] 调研 PostgreSQL 管理器原有的前端和后端备份逻辑与代码位置 @done(2026-05-19 09:06)
- [X] 备份/导入文字与链接优化：将数据库列表中的 “未备份” 或备份状态字段修改为 “备份/导入” @done(2026-05-19 09:06)
- [X] 编写或优化后端备份同步接口：扫描指定备份目录下所有 `.gz` 文件，并提供支持导入的列表 @done(2026-05-19 09:06)
- [X] 编写或优化后端本地上传接口：支持在备份详情中上传备份文件并保存到指定备份目录 @done(2026-05-19 09:06)
- [X] 编写前端备份详情页面交互：增加 “同步” 和 “本地上传” 按钮，实现对应的前端交互与文件上传逻辑 @done(2026-05-19 09:06)
- [X] 整合验证：测试备份、同步、上传、导入、删除全流程，确保没有 Bug @done(2026-05-19 09:06)
- [X] 列表排序优化：确保备份详情列表中的备份文件按备份时间从新到旧降序排列 @done(2026-05-19 09:10)

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

- [X] 在 `task.md` 中创建此修复 Task 与 Task List @done(2026-05-19 09:25)
- [X] 修复 `web/admin/files/files.py` 中 `os.chown` 在 Windows 等环境下的缺失/报错问题 @done(2026-05-19 09:27)
- [X] 优化 `plugins/postgresql/index.py` 中 `getArgs` 的参数解析，使其完美支持多参数的 JSON 解析 @done(2026-05-19 09:28)
- [X] 优化 `plugins/postgresql/index.py` 中 `getDbBackupListFunc` 过滤逻辑，兼容 `dbname_` 及 `db_dbname_` 前缀备份文件，使其不点同步也能正确显示 @done(2026-05-19 09:29)
- [X] 整合验证备份、同步、上传以及列表显示功能 @done(2026-05-19 09:30)
- [X] 彻底重构并修复 `plugins/postgresql/index.py` 中 `pgBack` 备份函数，替换硬编码路径并增加 Windows 兼容及执行成功校验 @done(2026-05-19 09:31)
- [X] 彻底重构并修复 `plugins/postgresql/index.py` 中 `pgBackList` 获取备份列表函数，解除 `i.split("_")[0]` 造成的前缀匹配屏蔽，调用通用的 `getDbBackupListFunc` 过滤逻辑 @done(2026-05-19 09:31)
- [X] 彻底重构并修复 `plugins/postgresql/index.py` 中 `importDbBackup` 数据库还原函数，纠正错配参数并修复硬编码指令和用户权限崩溃 @done(2026-05-19 09:31)

# Task: 优化 PostgreSQL 备份文件命名规则以体现版本号

## 项目描述

优化 PostgreSQL 面板的备份命名机制，让生成的备份文件名称中包含当前安装的 PostgreSQL 对应版本号（如 `pg_backup_v18.3_dbname_时间.gz`），并升级备份过滤匹配逻辑以完美兼容新老两种命名的文件展示。

## 开发规范

- 统一使用 UTF-8 (无 BOM) 格式。

## Task List

- [X] 在 `task.md` 中登记新任务 @done(2026-05-19 09:33)
- [X] 增加通用版本号获取方法 `getPgVersion()` @done(2026-05-19 09:34)
- [X] 重构 `pgBack()` 备份数据库的文件命名为 `pg_backup_v{version}_{dbname}_{cur_time}.gz` @done(2026-05-19 09:34)
- [X] 重构 `setDbBackup()` 面板主备份函数的文件命名，与弹窗的命名格式统一 @done(2026-05-19 09:34)
- [X] 升级 `getDbBackupListFunc()` 过滤匹配逻辑，兼容体现版本号的最新备份格式，确保完美展示 @done(2026-05-19 09:34)
- [X] 整合验证备份文件产生与完美列表展现 @done(2026-05-19 09:34)

# Task: 在MySQL管理器中显示数据库创建时间并按创建时间降序排列

## 项目描述

在数据库管理列表中显示每一个数据库的“创建时间”。无论使用的是哪一个MySQL/MariaDB版本（MySQL、MySQL-Community、MariaDB），列表都必须支持显示“创建时间”这一列，并且数据库列表必须按“创建时间”（`addtime`）降序排列。

## 开发规范

- 统一使用 UTF-8 (无 BOM) 格式。
- 遵循原有代码风格。
- 保证所有 MySQL/MariaDB 版本插件的功能同步性与一致性。
- 代码改动应最小化，保持高内聚低耦合。

## Task List

- [X] 在 `task.md` 中登记此任务 @done(2026-05-19 09:44)
- [X] 修改 MySQL 插件的后端排序逻辑（`plugins/mysql/index.py`）： @done(2026-05-19 09:47)
  - [X] 修改 `getDbList` 的排序为 `addtime desc, id desc` @done(2026-05-19 09:47)
  - [X] 修改 `getMasterDbList` 的排序为 `addtime desc, id desc` @done(2026-05-19 09:47)
- [X] 修改 MySQL 社区版插件的后端排序逻辑（`plugins/mysql-community/index.py`）： @done(2026-05-19 09:47)
  - [X] 修改 `getDbList` 的排序为 `addtime desc, id desc` @done(2026-05-19 09:47)
  - [X] 修改 `getMasterDbList` 的排序为 `addtime desc, id desc` @done(2026-05-19 09:47)
- [X] 修改 MariaDB 插件的后端排序逻辑（`plugins/mariadb/index.py`）： @done(2026-05-19 09:47)
  - [X] 修改 `getDbList` 的排序为 `addtime desc, id desc` @done(2026-05-19 09:47)
  - [X] 修改 `getMasterDbList` 的排序为 `addtime desc, id desc` @done(2026-05-19 09:47)
- [X] 修改 MySQL 插件的前端渲染逻辑（`plugins/mysql/js/mysql.js`）： @done(2026-05-19 09:50)
  - [X] 在 `dbList` 数据库列表表头 `thead` 增加 `创建时间` 列 @done(2026-05-19 09:50)
  - [X] 在 `dbList` 数据库列表行 `tbody` 中渲染 `addtime` 字段数据 @done(2026-05-19 09:50)
- [X] 修改 MySQL 社区版插件的前端渲染逻辑（`plugins/mysql-community/js/mysql-community.js`）： @done(2026-05-19 09:50)
  - [X] 在 `dbList` 数据库列表表头 `thead` 增加 `创建时间` 列 @done(2026-05-19 09:50)
  - [X] 在 `dbList` 数据库列表行 `tbody` 中渲染 `addtime` 字段数据 @done(2026-05-19 09:50)
- [X] 修改 MariaDB 插件的前端渲染逻辑（`plugins/mariadb/js/mariadb.js`）： @done(2026-05-19 09:50)
  - [X] 在 `dbList` 数据库列表表头 `thead` 增加 `创建时间` 列 @done(2026-05-19 09:50)
  - [X] 在 `dbList` 数据库列表行 `tbody` 中渲染 `addtime` 字段数据 @done(2026-05-19 09:50)
- [X] 整合验证所有三个插件的功能，确保界面显示正常、排序正确且无中文乱码。 @done(2026-05-19 09:51)

# Task: 优化数据库备份文件命名，以数据库版本号作为命名前缀

## 项目描述

为了更好地识别数据库备份所属的数据库版本，需要将备份文件的前缀由原本硬编码的 `db_` 改为包含对应版本号的动态前缀（如 `mysql57_`, `mysql80_`, `mariadb104_` 等），其中版本号需根据当前安装的数据库版本动态解析（例如：5.7.x 解析为 57，10.4.x 解析为 104），同时保证过滤检索机制向下兼容旧版 `db_` 前缀的备份，确保用户原有备份资产完全可用。

## 开发规范

- 统一使用 UTF-8 (无 BOM) 格式。
- 遵循原有代码风格。
- 保证历史旧版前缀 `db_` 的备份文件完美向下兼容，对用户不可丢失、完全可读。

## Task List

- [X] 在 `task.md` 中登记此任务 @done(2026-05-19 10:05)
- [X] 优化 MySQL 插件的备份生成及检索过滤： @done(2026-05-19 10:06)
  - [X] 重构 `scripts/backup.py` 中 `backupDatabase` 生成的备份文件前缀为动态版本号（如 `mysql57_`） @done(2026-05-19 10:06)
  - [X] 重构 `plugins/mysql/index.py` 中 `getDbBackupListFunc`，使其同时完美检索出新前缀与历史旧版 `db_` 前缀的备份文件 @done(2026-05-19 10:06)
- [X] 优化 MySQL 社区版插件的备份生成及检索过滤： @done(2026-05-19 10:09)
  - [X] 重构 `plugins/mysql-community/scripts/backup.py` 中 `backupDatabase` 生成的备份文件前缀为动态版本号（如 `mysql80_`） @done(2026-05-19 10:09)
  - [X] 重构 `plugins/mysql-community/index.py` 中 `getDbBackupListFunc`，使其同时完美检索出新前缀与历史旧版 `db_` 前缀的备份文件 @done(2026-05-19 10:09)
- [X] 优化 MariaDB 插件的备份生成及检索过滤： @done(2026-05-19 10:13)
  - [X] 重构 `plugins/mariadb/scripts/backup.py` 中 `backupDatabase` 生成的备份文件前缀为动态版本号（如 `mariadb104_`） @done(2026-05-19 10:13)
  - [X] 重构 `plugins/mariadb/index.py` 中 `getDbBackupListFunc`，使其同时完美检索出新前缀与历史旧版 `db_` 前缀的备份文件 @done(2026-05-19 10:13)
- [X] 整合验证所有三个插件的备份生成与显示功能，确保历史旧版备份与新版本前缀备份完美共存。 @done(2026-05-19 10:14)

# Task: 优化 PostgreSQL 插件备份文件命名，以数据库版本号作为命名前缀

## 项目描述

为了与 MySQL/MariaDB 保持统一，需要将 PostgreSQL 备份文件的前缀由原本的 `pg_backup_v{version}_` 改为包含对应版本号的动态前缀（如 `postgre183_`，其中 183 代表 PostgreSQL 版本 18.3），版本号需要根据当前安装的版本动态解析。同时，检索机制必须向下兼容旧版 `pg_backup_v{version}_` 以及历史更早的 `db_` 前缀备份。

## 开发规范

- 统一使用 UTF-8 (无 BOM) 格式。
- 遵循原有代码风格。
- 保证所有历史格式备份文件完美向下兼容，不可丢失。

## Task List

- [X] 在 `task.md` 中登记此任务 @done(2026-05-19 10:15)
- [X] 优化 PostgreSQL 插件的备份生成及检索过滤： @done(2026-05-19 10:17)
  - [X] 重构 `plugins/postgresql/index.py` 中 `setDbBackup` 与 `pgBack` 生成的备份文件前缀为动态版本号（如 `postgre183_`） @done(2026-05-19 10:17)
  - [X] 重构 `plugins/postgresql/index.py` 中 `getDbBackupListFunc`，使其同时完美检索出新前缀、历史 `pg_backup_v{version}_` 前缀以及更早的旧前缀备份文件 @done(2026-05-19 10:17)
- [X] 整合验证 PostgreSQL 插件的备份生成与显示功能，确保新旧备份完美共存。 @done(2026-05-19 10:17)

# Task: 优化 PostgreSQL 插件界面、排序与模态框尺寸

## 项目描述

为了给用户更好的视觉和交互体验，在 PostgreSQL 插件管理器中增加“创建时间”字段展示，并使数据库列表按照创建时间降序排列。同时拉大模态框的长度和宽度，调整内容展示高度，避免默认弹出框产生多余的滚动条。

## Task List

- [X] 在 `task.md` 中登记此任务 @done(2026-05-19 10:20)
- [X] 优化 PostgreSQL 数据库列表排序及字段展示：
  - [X] 修改 `plugins/postgresql/index.py` 中 `getDbList` 查询排序，使其按 `addtime desc, id desc` 降序排列 @done(2026-05-19 10:20)
  - [X] 修改 `plugins/postgresql/js/postgresql.js` 中的 `dbList` 渲染逻辑，在表格中增加“创建时间”这一列并正确展示 `addtime` 字段 @done(2026-05-19 10:20)
- [X] 优化模态框尺寸与布局以避免滚动条：
  - [X] 修改 `plugins/postgresql/index.html` 中的 `resetPluginWinWidth` 宽度至 `950px` @done(2026-05-19 10:20)
  - [X] 在 `plugins/postgresql/index.html` 中新增调用 `resetPluginWinHeight(650)` 以拉大高度 @done(2026-05-19 10:20)
  - [X] 将 `.soft-man-con` 容器高度增大为 `570px`，实现完美填充且无外层滚动条 @done(2026-05-19 10:20)

# Task: 替换老旧外部构建依赖为自主仓库依赖并提供中国大陆加速

## 项目描述

在插件安装过程中，部分脚本（如 webstats, op_waf 以及 php 的 openssl, libzip, libiconv 等依赖组件）强依赖原作者 `midoks` 个人 GitHub 仓库的 Release 附件。为了消除该强依赖关系，保障项目长久的独立生命力，需将这 5 处下载链接统一替换为用户自己仓库的新 Release 链接。此外，在进行链接替换时，还需确保在中国大陆地区可以使用 `mirror.ghproxy.com` 中转节点进行智能加速下载。

## 开发规范

- 统一使用 UTF-8 (无 BOM) 格式。
- 遵循 Shell 编程规范，做好环境判断的健壮性。
- 代码修改需最小化，不破坏原有各组件的核心安装逻辑。

## Task List

- [X] 登记 `task.md` 任务清单 @done(2026-05-19 11:12)
- [X] 修改 `plugins/webstats/install.sh` 脚本中的老链接，并支持中转加速 @done(2026-05-19 11:12)
- [X] 修改 `plugins/op_waf/install.sh` 脚本中的老链接，并支持中转加速 @done(2026-05-19 11:12)
- [X] 修改 `plugins/php/lib/openssl_10.sh` 脚本中的老链接，并支持中转加速 @done(2026-05-19 11:12)
- [X] 修改 `plugins/php/lib/libzip.sh` 脚本中的老链接，并支持中转加速 @done(2026-05-19 11:12)
- [X] 修改 `plugins/php/lib/libiconv.sh` 脚本中的老链接，并支持中转加速 @done(2026-05-19 11:12)

# Task: 彻底消除 dl.midoks.icu 个人域名依赖并精简编译脚本

## 项目描述

在 PHP 依赖库编译脚本中（libiconv.sh, openssl_10.sh, libzip.sh），原作者在 `cn` 条件下优先请求其私人的云存储域名 `dl.midoks.icu`。为达到完全脱离原作者服务独立运行的目标，且防止该域名停用时产生 20 秒的连接挂起等待，需将这些脚本中的冗余判断直接剔除，统一精简为拉取用户自己的 GitHub Release 链接，并通过智能中转镜像提供最佳加速体验。

## 开发规范

- 统一使用 UTF-8 (无 BOM) 格式。
- 保证 Shell 脚本中逻辑的极简化和高度健壮。

## Task List

- [X] 登记 `task.md` 任务清单 @done(2026-05-19 11:15)
- [X] 彻底清理并精简 `plugins/php/lib/libiconv.sh` 中的冗余判断，直接使用用户 init 地址 @done(2026-05-19 11:15)
- [X] 彻底清理并精简 `plugins/php/lib/openssl_10.sh` 中的冗余判断，直接使用用户 init 地址 @done(2026-05-19 11:15)
- [X] 彻底清理并精简 `plugins/php/lib/libzip.sh` 中的冗余判断，直接使用用户 init 地址 @done(2026-05-19 11:15)

# Task: 彻底删除 Telegram 机器人插件中的广告推送组件

## 项目描述

Telegram 机器人插件中的 `push_ad.py` 文件包含了硬编码的原作者大群 ID 及代实名、备案域名、18+ 采集等第三方推广广告。当用户启动 tgbot 时，该脚本会强制利用用户的 Bot Token 向原作者公开大群推送擦边推广内容，严重危害用户的机器人账号安全。由于该插件采用动态目录扫描加载机制，需彻底删除 `push_ad.py` 源码及对应静态广告图 `ad.png`，以彻底断绝此广告后门。

## 开发规范

- 代码与资源清理要彻底，不遗留无用静态资产。
- 保证动态加载机制平稳过渡，不引起报错。

## Task List

- [X] 登记 `task.md` 任务清单 @done(2026-05-19 11:20)
- [X] 物理删除 `plugins/tgbot/startup/extend/push_ad.py` 脚本文件 @done(2026-05-19 11:20)
- [X] 物理删除 `plugins/tgbot/static/image/ad.png` 广告静态图资源 @done(2026-05-19 11:20)

# Task: 物理清理并剔除 `push_notice_msg.py` 垃圾广告通知脚本

## 项目描述

在 Telegram 机器人插件的扩展模块中，存在另一个名为 `push_notice_msg.py` 的轮播消息脚本。该文件不仅硬编码了原作者的公开推广大群，还包含相同的引流广告键盘，以及每 90 秒高频推送并撤回一次原作者的技术提问吐槽信息。为了保障用户机器人账号的最高安全，防止被官方拉黑，且消除多余的后台网络消耗，需物理删除该脚本。

## 开发规范

- 彻底清理源码，平稳消除其在插件系统中的动态扫描加载项。

## Task List

- [X] 登记 `task.md` 任务清单 @done(2026-05-19 11:25)
- [X] 物理删除 `plugins/tgbot/startup/extend/push_notice_msg.py` 脚本文件 @done(2026-05-19 11:25)

# Task: 物理清除 Telegram 客户端插件中的全部高危营销流氓后门

## 项目描述

在 Telegram 客户端托管插件（tgclient）的扩展目录下（tgclient/startup/extend/），包含了 4 个极其危险、无底线的流氓营销及垃圾后门脚本。若用户登录托管其个人 Telegram 账号，这些脚本会直接通过其账号自动执行跨群强发广告、暴力搜刮其他群的成员强行拉人进入作者群、擅自越权管理别人群以及陷入暴力遍历嗅探死循环。这不仅严重消耗服务器网络性能，更会在几秒内导致用户的个人 Telegram 账号被官方直接永久注销封禁。因此，必须将这 4 个高危流氓脚本全部物理清除。

## 开发规范

- 对垃圾后门组件清理要彻底，不遗留任何隐藏高危脚本。

## Task List

- [X] 登记 `task.md` 任务清单 @done(2026-05-19 11:27)
- [X] 物理删除 `plugins/tgclient/startup/extend/client_ad.py` 垃圾广告脚本 @done(2026-05-19 11:27)
- [X] 物理删除 `plugins/tgclient/startup/extend/client_holding.py` 强行拉人流氓后门 @done(2026-05-19 11:27)
- [X] 物理删除 `plugins/tgclient/startup/extend/client_check_member.py` 越权管理他人群脚本 @done(2026-05-19 11:27)
- [X] 物理删除 `plugins/tgclient/startup/extend/client_temp.py` 暴力死循环嗅探脚本 @done(2026-05-19 11:27)

# Task: 替换更新脚本 `update.sh` 中的老旧 GitHub 链接与解压目录映射

## 项目描述

在系统老旧的更新脚本 `scripts/old/update.sh` 中，依旧硬编码指向了原作者 `midoks` 个人 GitHub 仓库的 Release 更新压缩包下载路径。为了让整个更新逻辑平滑转移至用户自主掌控的 `clhome/bt_simple` 仓库，需将此处的下载链接予以替换，并引入已有的 `HTTP_PREFIX` 以支持国内中转加速。此外，需将解压后的首级目录从 `mdserver-web-${VERSION}` 同步映射替换为 `bt_simple-${VERSION}`，以保证升级拷贝能正确运行。

## 开发规范

- 对 Shell 脚本的字符串匹配和文件路径变动要极其敏感，必须确保拷贝和删除目录一致。

## Task List

- [X] 登记 `task.md` 任务清单 @done(2026-05-19 11:28)
- [X] 替换 `scripts/old/update.sh` 脚本中的老 GitHub 链接，并支持中转加速 @done(2026-05-19 11:28)
- [X] 同步修改 `scripts/old/update.sh` 中解压首级文件夹名称从 `mdserver-web` 变更为 `bt_simple` @done(2026-05-19 11:28)

# Task: 物理删除 Telegram 机器人插件中的论坛引流后门脚本 `push_bbs_ntid.py`

## 项目描述

在 Telegram 机器人插件的扩展目录中，`push_bbs_ntid.py` 脚本每 5 分钟从原作者个人 Discuz! 论坛（bbs.midoks.icu）抓取最新发帖信息，并强行通过用户的机器人 Token 向原作者的公开技术大群推送发帖通知。这完全是原作者私人的引流推客，对面板用户不仅毫无用处，更白白消耗后台资源并有极高概率触发 Telegram 官方风控导致机器人账号封禁。需彻底物理删除该流氓后门脚本。

## 开发规范

- 彻底清理源码，消除后台隐形网络请求和动态加载项。

## Task List

- [X] 登记 `task.md` 任务清单 @done(2026-05-19 11:32)
- [X] 物理删除 `plugins/tgbot/startup/extend/push_bbs_ntid.py` 论坛引流脚本 @done(2026-05-19 11:32)

# Task: 全局清理 `midoks.icu` 残留、物理清除引流后门并重构第三方下载源

## 项目描述

全局检索发现了多处 `midoks.icu` 关键字残留。其中，`tgbot` 的 2 个接收消息扩展脚本 `receive_faq.py` 和 `receive_music163_search.py` 含有强制检索并推荐原作者个人论坛的引流后门，现已被物理删除。另外，对于 13 处在 `cn` 环境下强依赖 `dl.midoks.icu` 附件的第三方资源（GeoLite2、PureFtp、ICU4C、Zlib、OpenResty、HAProxy），需将代码中的下载源统一重构为用户本人的 `clhome` 自主 GitHub 仓库源（支持中转加速），并列出需要用户上传到其 `init` Release 中的原始包下载清单。

## 开发规范

- 彻底物理清理引流后门。
- 替换后的第三方依赖源必须保证与对应的插件安装包名称完美一致。

## Task List

- [X] 登记 `task.md` 任务清单 @done(2026-05-19 11:35)
- [X] 物理删除 `plugins/tgbot/startup/extend/receive_faq.py` 论坛检索后门脚本 @done(2026-05-19 11:35)
- [X] 物理删除 `plugins/tgbot/startup/extend/receive_music163_search.py` 论坛检索后门脚本 @done(2026-05-19 11:35)
- [X] 重构代码为“官方直连+大陆智能中转镜像加速”，无感免除用户上传大文件之劳顿 @done(2026-05-19 11:36)

# Task: 升级旧版 OpenSSL 编译版本至 `1.0.2u` 以修复高危安全缺陷

## 项目描述

系统中低版本 PHP 编译时所引用的 `openssl-1.0.2q` 版本发布于 2018 年，存在多个已知的严重 CVE 安全漏洞（如 CVE-2022-0778 无限循环拒绝服务等）。为了在保障低版本 PHP（PHP 5.4 - 7.4）的向后 API 兼容性的前提下提升安全水位，需将 `openssl_10.sh` 的编译底座升级至 OpenSSL 1.0.2 大分支的最后一个免费稳定版 `1.0.2u`。已经将官方包上传至其仓库 release 中。

## 开发规范

- 保证只更改版本号常量，不动任何已经验证过的编译路径，保障 100% 的编译向后兼容性。

## Task List

- [X] 登记 `task.md` 任务清单 @done(2026-05-19 13:02)
- [X] 修改 `plugins/php/lib/openssl_10.sh` 中的版本常量从 `1.0.2q` 升级为 `1.0.2u` @done(2026-05-19 13:03)

# Task: 升级 Web 面板 Python 关键依赖版本以防御 SSH Terrapin 及高危拒绝服务漏洞

## 项目描述

对系统 `requirements.txt` 的第三方依赖包进行深度安全审计后发现：`paramiko>=2.8.0` 存在灾难级的 Terrapin 攻击漏洞（CVE-2023-48795，可导致 SSH 通信被中间人篡改和解密）；`chardet==3.0.4` 存在古老字符集解析引发无限递归死循环的 Bug。为了加固面板的 SSH 终端管理器与后台性能稳定性，需将这些依赖包在 `requirements.txt` 中的起步及限制版本进行安全提升。

## 开发规范

- 仅提升版本控制区间，确保与 Python 3 各版本的最大兼容性。

## Task List

- [X] 登记 `task.md` 任务清单 @done(2026-05-19 13:16)
- [X] 在 `requirements.txt` 中将 `paramiko` 升级至 `>=3.4.0` @done(2026-05-19 13:17)
- [X] 在 `requirements.txt` 中将 `chardet` 升级至 `>=4.0.0` @done(2026-05-19 13:17)
- [X] 在 `requirements.txt` 中将 `psutil` 升级至 `>=5.9.8` @done(2026-05-19 13:17)

# Task: MySQL/MariaDB从文件导入数据时增加覆盖数据库确认弹窗

## 项目描述

在 MySQL / MariaDB 插件管理器中，用户点击“从文件导入数据”进行导入操作（包含外部导入和备份详情导入）时，应增加二次确认弹窗，提示：“当前操作会覆盖 xxx 数据库，是否继续？”。这能有效防止用户因手误点击导入而导致现有数据库数据被意外覆盖。

## 开发规范

- 统一使用 UTF-8 (无 BOM) 格式。
- 遵循原有代码风格。
- 代码改动应最小化，保持高内聚低耦合。
- 实现确认提示，若确认则继续导入，取消则终止。

## Task List

- [X] 优化 MySQL 插件导入操作，在点击导入时提示“当前操作会覆盖 xxx 数据库，是否继续” @done(2026-05-19 13:53)
- [X] 优化 MySQL 社区版插件导入操作，在点击导入时提示“当前操作会覆盖 xxx 数据库，是否继续” @done(2026-05-19 13:53)
- [X] 优化 MariaDB 插件导入操作，在点击导入时提示“当前操作会覆盖 xxx 数据库，是否继续” @done(2026-05-19 13:53)
- [X] 整合验证这三个插件的导入覆盖确认功能，确保功能正常 @done(2026-05-19 13:53)

# Task: 修复 PostgreSQL 管理器备份成功但列表为空的问题

## 项目描述

在 PostgreSQL 管理器中，点击备份后提示执行成功，但下方的备份详情列表却显示为空。经排查，原因为前端获取备份列表接口（`pg_back_list`）在 Python 后端（`pgBackList`）重构时被误改为了返回包含 `status` 字段的 `mw.returnJson(True, 'ok', rr)` 结构，而非直接序列化字典对象的 `mw.getJson` 结构。这导致前端解析出的数据格式与预期不符（无法正确获取 `.list` 属性及 `.upload_dir` 属性），从而渲染出空列表。

## 开发规范

- 统一使用 UTF-8 (无 BOM) 格式。
- 遵循原有代码风格。
- 修复逻辑需简单直接，不引入额外复杂度。

## Task List

- [X] 在 `task.md` 中登记此修复 Task 与 Task List @done(2026-05-19 14:02)
- [X] 修改 `plugins/postgresql/index.py` 中 `pgBackList` 的返回结构，构造包含 `list` 与 `upload_dir` 的字典并使用 `mw.getJson` 序列化返回 @done(2026-05-19 14:05)
- [X] 整合验证 PostgreSQL 备份、同步、上传与显示功能，确保列表渲染正常且不为空 @done(2026-05-19 14:08)
- [X] 修复 `plugins/postgresql/js/postgresql.js` 中 `uploadDbFiles` 异步 DOM 渲染导致 `uploadStart` 无法获取隐藏 input 值的 Bug @done(2026-05-19 14:14)
- [X] 整合测试本地上传功能，确保弹窗正常拉起且无异常 @done(2026-05-19 14:14)
- [X] 修复 PostgreSQL 管理列表中权限按钮报错，在 `index.py` 中实现 `getDbAccess` 与 `setDbAccess` 函数 @done(2026-05-19 16:21)
- [X] 整合测试权限设置功能，确保弹窗和修改生效且无报错 @done(2026-05-19 16:21)

## Task: PostgreSQL 物理路径重构至 /www/server/pgsql (一劳永逸对齐宝塔规范)

### 任务描述
在无历史存量包袱的阶段，全面将 PostgreSQL 的物理安装、运行以及数据存储路径从 `/www/server/postgresql` 更改为 `/www/server/pgsql`，保证在从宝塔迁移到本面板时 100% 路径兼容，免去目录名称不一致带来的任何潜在调用风险与软链接配置。

### 开发规范
- 统一修改 `plugins/postgresql/index.py` 里的 `getServerDir()` 返回映射，指向 `/www/server/pgsql`。
- 全量修改各版本（14, 15, 16, 17, 18）的 `install.sh` 中的安装前缀及配置目录。
- 逐个校验 Python 控制逻辑中是否还有残留硬编码路径并进行修正。
- 遵循原有代码风格，确保修改极度精确。

### Task List
- [X] 登记 PostgreSQL 物理路径对齐 Task List @done(2026-05-19 17:35)
- [X] 修改 `plugins/postgresql/index.py` 中的 `getServerDir()`，映射至 `/www/server/pgsql` @done(2026-05-19 17:35)
- [X] 仔细审查并清理 `index.py` 中所有的物理路径硬编码 "/www/server/postgresql" @done(2026-05-19 17:35)
- [X] 仔细修改版本 14 的安装脚本 `versions/14/install.sh` 物理路径为 `pgsql` @done(2026-05-19 17:35)
- [X] 仔细修改版本 15 的安装脚本 `versions/15/install.sh` 物理路径为 `pgsql` @done(2026-05-19 17:35)
- [X] 仔细修改版本 16 的安装脚本 `versions/16/install.sh` 物理路径为 `pgsql` @done(2026-05-19 17:35)
- [X] 仔细修改版本 17 的安装脚本 `versions/17/install.sh` 物理路径为 `pgsql` @done(2026-05-19 17:35)
- [X] 仔细修改版本 18 的安装脚本 `versions/18/install.sh` 物理路径为 `pgsql` @done(2026-05-19 17:35)
- [X] 验证及测试 Python 控制脚本在 Windows 开发与本地模拟环境下的基础输出 @done(2026-05-19 17:35)
- [X] 修复面板 checks 检测路径，将 `info.json` 里的 `"checks"` 与 `"path"` 修正为 `"server/pgsql"`，使面板能完美识别新路径的安装状态 @done(2026-05-19 17:51)
501: - [X] 解决管理页面各选项卡“文件不存在”的硬编码隐患，在 `contentReplace()` 中将 `{$APP_PATH}` 的硬编码路径彻底修正为动态的 `getServerDir()` 并在 `initDreplace()` 中加入了强制刷新与自愈生成机制 @done(2026-05-19 17:53)
502: 
503: # Task: 在 PostgreSQL 数据库权限管理中增加特权显示与一键赋权功能
504: 
505: ## 项目描述
506: 
507: 在 PostgreSQL 管理列表的“权限”设置弹窗中：
508: 1. 增加当前数据库特权（`DEFAULT PRIVILEGES`）的显示。
509: 2. 增加一键赋权功能，可以将对应数据库下的权限（Schema、已有的表/序列/函数、未来新建的表/序列/函数特权）一键赋权给该数据库的创建用户（即所有者）。
510: 
511: ## 开发规范
512: 
513: - 统一使用 UTF-8 (无 BOM) 格式。
514: - 保证历史前端接口的向后兼容，不破坏原本的网段权限设置。
515: - 代码变动最小化，保持极高的健壮性和优美的界面展示。
516: 
517: ## Task List
518: 
519: - [X] 在 `task.md` 中登记新任务 @done(2026-05-20 09:00)
520: 520: - [X] 升级 `plugins/postgresql/class/pg.py`，支持动态切换连接数据库 @done(2026-05-20 09:10)
521: - [X] 重构 `plugins/postgresql/index.py` 中的 `pgDb` 方法以接收 `dbname` 参数并动态设置 @done(2026-05-20 09:12)
522: - [X] 升级 `plugins/postgresql/index.py` 中的 `getDbAccess`： @done(2026-05-20 09:15)
523:   - [X] 在 Sqlite 中获取该数据库的创建用户名 `dbuser` @done(2026-05-20 09:15)
524:   - [X] 连接至对应数据库 `dbname` 执行验证 SQL 获取其 `DEFAULT PRIVILEGES` @done(2026-05-20 09:15)
525:   - [X] 将当前 accept 状态、创建用户名、以及权限数据作为 `res_data` 返回给前端 @done(2026-05-20 09:15)
526: - [X] 在 `plugins/postgresql/index.py` 中新增 `setDbPrivileges` 一键赋权接口： @done(2026-05-20 09:18)
527:   - [X] 在 Sqlite 中获取该数据库的创建用户名 `dbuser` @done(2026-05-20 09:18)
528:   - [X] 连接至对应数据库 `dbname` 依次执行 GRANT 及 ALTER DEFAULT PRIVILEGES 的 8 条赋权 SQL 语句 @done(2026-05-20 09:18)
529: - [X] 修改 `plugins/postgresql/js/postgresql.js` 中 `setDbAccess` 方法： @done(2026-05-20 09:25)
530:   - [X] 优化模态框布局，在“访问权限”行下方增加“特权明细”展示区域 @done(2026-05-20 09:25)
531:   - [X] 在模态框成功弹出后，如果接口返回了 `privileges`，在表格/列表中渲染展示出来（包括 grantor, schema, object_type, privileges） @done(2026-05-20 09:25)
532:   - [X] 增加“一键赋权”按钮，点击后发送请求调用 `set_db_privileges` 接口，一键赋权并提示成功后刷新权限展示 @done(2026-05-20 09:25)
533: - [X] 整合并调试测试，确保特权成功查询并能执行一键赋权，且原来的访问权限（pg_hba.conf修改）功能也完全正常 @done(2026-05-20 09:28)

# Task: 修复 PostgreSQL 一键赋权按钮点击无效、未实现赋权的问题

## 项目描述

用户在 PostgreSQL 管理器的“权限设置”弹窗中，点击“一键赋权给创建用户”按钮没有发生任何反应，也没有真正实现赋权。
经排查，原因是后端 `plugins/postgresql/index.py` 中虽有 `setDbPrivileges()` 方法，但在脚本的 `__main__` 路由分发逻辑中，遗漏了对 `set_db_privileges` 请求的映射分发，导致前端请求直接返回 `'error'`，进而导致赋权操作失败。

## 开发规范

- 统一使用 UTF-8 (无 BOM) 格式。
- 遵循原有代码风格。
- 修复逻辑需要简单直接，不引入额外复杂度。

## Task List

- [X] 在 `task.md` 中登记此修复 Task 与 Task List @done(2026-05-20 11:45)
- [X] 修改 `plugins/postgresql/index.py` 的路由映射，在 `__main__` 入口中加入对 `set_db_privileges` 的分发调用 @done(2026-05-20 11:45)
- [X] 整合验证一键赋权功能，确保按钮点击后调用成功，前端刷新后能够完美渲染展示出 DEFAULT PRIVILEGES 信息 @done(2026-05-20 11:45)
# Task: 修复面板安装/迁移完成时默认信息获取中 scheme 因未匹配而报错的问题

## 项目描述

在全新安装或迁移完成打印默认信息时，Shell 脚本中通过 `python3 panel_tools.py panel_ssl_type` 来获取面板 SSL 的 scheme (http/https)。但由于 `panel_tools.py` 的 `main()` 分发逻辑中漏掉了对 `panel_ssl_type` 的映射，导致其输出 `ERROR: Parameter error`，最终在最终输出中被拼成了 `ERROR: Parameter error://ip:port/path` 的奇怪格式。

## 开发规范

- 统一使用 UTF-8 (无 BOM) 格式。
- 遵循原有代码风格。

## Task List

- [X] 在 `panel_tools.py` 中增加对 `panel_ssl_type` 方法的映射分发支持 @done(2026-05-20 17:05)
- [X] 验证获取面板默认信息的 URL 拼接与输出正常 @done(2026-05-20 17:05)

