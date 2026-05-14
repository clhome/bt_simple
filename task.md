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
