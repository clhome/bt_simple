# BT Simple 站点管理优化

## 项目整体描述

BT Simple 是一个轻量级的服务器运维面板。本项目旨在对其进行精简、优化和定制，以满足便捷高效的日常运维管理需求。

## 开发规范描述

1. 简洁至上：恪守 KISS 原则，强调可维护性，避免过度设计。
2. 编码规范：统一使用 UTF-8 (无 BOM) 格式，换行符强制使用 LF。避免使用 PowerShell 直接修改包含中文的文件。
3. 渐进式推进：本着事实优先和第一性原理，小步快跑，逐步明确和验证需求。

## Task List

- [x] 检查并修改 `web/static/app/site.js` 的 `webEdit` 页面跳转逻辑，支持配置文件的 defaultTab。
- [x] 将网站列表中“设置”按钮的点击事件绑定修改为跳转到配置文件（传入 'config' 作为 defaultTab）。
- [x] 验证点击“设置”能够跳转到“配置文件”页面，且点击域名能够跳转到默认的“域名管理”页面。
- [x] 修改 `yufeng_systemd` 插件 of `index.html`，添加左侧菜单栏并美化使用说明页面。
- [x] 修改 `yufeng_systemd` 插件的 `js/yufeng_systemd.js`，实现 Tab 切换逻辑。
- [x] 验证界面切换和配置/使用说明的功能和样式是否优雅美观。
- [x] 修复添加服务时服务名含中文及选择器冲突导致提交保存无响应的 Bug
- [x] 在添加/修改弹窗的“服务名称”右侧增加“请勿使用中文名称”的红色提醒描述。
- [x] 修复“提交保存”按钮被 info-r 遮挡的问题，改用 layui-layer 规范的原生底部按钮。
- [x] 优化服务列表中的运行状态和自启状态图标，使其准确反映当前状态（而不是下一步动作），且调整“已关闭”按钮为更柔和的灰色。
- [x] 修复 systemd 日志中 "Invalid URL, ignoring: tag:YuFeng" 的警告，将 Documentation 字段改用规范 of URL 格式 (https://yufeng.tag) 且保证老服务向前兼容。
- [x] 在运行日志弹窗中增加“清空日志”按钮，利用 systemd journalctl --since 机制实现单服务的日志独立虚拟清空，并在删除服务时清理时间记录文件。
- [x] 拓宽弹窗中“项目路径”和“启动命令”的输入框宽度，并在下方添加可一键复制的 Python 虚拟环境启动命令优雅示例。
- [x] 优化启动命令下方的 Python 虚拟环境启动示例为圆角矩形警示框，整体下移且仅作直接展示。
- [x] 实现宝塔站点导入至御风面板数据库的功能
  - [x] 在 `panel_tools.py` 中新增 `import_bt_sites` 函数以支持解析宝塔 SQLite 数据库 `sites` 表（提取 `name`, `path`, `status`, `ps`, `addtime` 字段），并调用 `MwSites.instance().add()` 创建站点、更新时间以及状态同步
  - [x] 在 `panel_tools.py` 的 `main` 入口中注册 `import_bt_sites` 命令接口
  - [x] 在 `deploy.sh` 部署脚本中，在 `migrate_from_bt` 方法的末尾添加检测和询问交互（y/n）以及调用导入指令 the 逻辑
  - [x] 进行测试和验证（使用 `参考/site.db` 进行模拟测试，验证导入的有效性）
- [x] 优化 `deploy.sh` 站点导入交互逻辑，以完美兼容非交互的静默模式（SILENT_MODE）及无 Tty 终端环境
- [x] deploy.sh 健壮性审计修复
  - [x] #1 严重：移除缺失的 `uninstall_panel` 函数替换为 `log_warn` 提示用户手动执行卸载命令（L1265）
  - [x] #2 严重：修复 `-cn` 参数与子命令互斥问题（L1268）
  - [x] #3 严重：修复 `mv` 目标目录已存在时行为错误（L638, L1005）
  - [x] #4 中等：`confirm()` 增加 Tty Fallback（L141）
  - [x] #5 中等：`_bt_bak` 备份目录重复执行时 `mv` 嵌套（L965-988）
  - [x] #6 中等：宝塔迁移补充 `setup_china_git_config` 调用
  - [x] #7 中等：宝塔迁移补充 acme.sh 安装
  - [x] #8 中等：主入口菜单 `read` 补充 Tty Fallback（L1283等）
