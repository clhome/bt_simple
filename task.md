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
