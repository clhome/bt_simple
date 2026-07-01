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
- [x] 优化删除逻辑：如果删除数据库执行超过 30 秒超时，则在 Python 中捕获异常，自动调用重启 MySQL 的操作并重新执行删除，防止因元数据锁阻塞导致面板卡死。
- [x] 分析最近 15 天 Git 提交记录并更新文档
  - [x] 制定更新文档实施计划
  - [x] 更新 README.md，补充近期核心优化与新特性
  - [x] 更新 RELEASE_TEMPLATE.md，补充最近 15 天版本的重大变更日志
  - [x] 更新 说明书.md，补充宝塔迁移新逻辑、Fail2ban 监狱管理、JDK 等插件的运维指引
- [x] 增强 MySQL/MariaDB 数据库删除安全校验
  - [x] 在 `web/static/language/Simplified_Chinese/lan.js` 添加相关多语言翻译项
  - [x] 修改 `web/static/app/public.js` 的 `safeMessage` 弹窗方法，支持双重校验
  - [x] 修改 `plugins/mysql/js/mysql.js` 传递 `checkName`
  - [x] 修改 `plugins/mariadb/js/mariadb.js` 传递 `checkName`
  - [x] 测试双重验证是否生效
- [x] 整合服务器测速脚本到面板中
  - [x] 编写 `scripts/speed.sh` 服务器测速脚本
  - [x] 在 `web/admin/system/system.py` 中新增 `/system/speed_test` API 路由
  - [x] 在 `web/templates/default/index.html` 顶部增加带有 RJ45 图标的“测速”入口
  - [x] 在 `web/static/app/index.js` 添加 `runSpeedTest` 触发测速弹窗
- [x] 优化服务器测速弹窗为优雅的 Web 仪表盘样式
  - [x] 在 `web/static/app/index.js` 实现日志文本实时解析器
  - [x] 设计精美的 HTML 卡片和网络测速节点列表 UI 结构
  - [x] 通过轮询渲染实时进度条、旋转加载动画与成功/失败状态标志
- [x] 解决测速点跳过与弹窗尺寸文字换行优化
  - [x] 优化 `scripts/speed.sh` 测速输出缓存机制
  - [x] 调整 `web/static/app/index.js` 弹窗宽高与第一列标签宽度，杜绝换行和滚动条
  - [x] 本地验证并完成所有功能
- [x] 修复 html.escape 转义导致的测速状态不更新漏洞
  - [x] 在 `web/static/app/index.js` 中兼容匹配 `-&gt;` 与 `->` 节点行
  - [x] 验证各大云节点的实时测速状态点亮功能
- [x] 调整测速节点并增加境内外网络分割线
  - [x] 修改 `scripts/speed.sh` 移除失效 163 并添加美国、英国、德国、日本官方测试点
  - [x] 修改 `web/admin/system/system.py` Windows 模拟日志适配新节点
  - [x] 调整 `web/static/app/index.js` 添加分割线 UI 结构、海外节点，并拓高弹窗到 680px
  - [x] 验证界面样式和语法编译
- [x] 服务器测速界面深度打磨与文案优化
  - [x] 在 `web/static/app/index.js` 中将 CPU 显示重构为双行且支持解构
  - [x] 在 `web/static/app/index.js` 下载标题处加入测速原理灰色小字说明
  - [x] 将弹窗区域拉高至 730px 杜绝滚动条
  - [x] 验证界面样式和编译校验
- [x] 网络比特率测速与公司出品标识优化
  - [x] 修改 `scripts/speed.sh` 将网速计算换算为 bits 每秒（输出 Mbps）
  - [x] 修改 `web/admin/system/system.py` 中的模拟数据为 Mbps
  - [x] 修改 `web/static/app/index.js` 添加右下角“衢州御风科技有限公司出品”的优雅声明
  - [x] 验证界面样式和编译校验
- [/] 本地缓存恢复与“再次测试”工作流优化
  - [/] 在 `web/static/app/index.js` 中新增 localStorage 的检测和数据渲染还原逻辑
  - [ ] 改造 `runSpeedTest` 并新增 `startNewSpeedTest` 再次测试触发流
  - [ ] 在 HTML 中加入“再次测试”按钮并在测速彻底结束时更新本地缓存
  - [ ] 验证界面样式和编译校验
- [x] 新增命令行选项 31（恢复宝塔网站列表数据）的入口
  - [x] 在 `panel_tools.py` 的菜单中新增菜单项 `(31)   恢复宝塔网站列表数据`
  - [x] 在 `panel_tools.py` 的 `nums` 列表中允许 31
  - [x] 在 `panel_tools.py` 的 `mwcli` 内部处理 31 输入，实现 `find_bt_site_db()` 函数以自动或手动定位 `site.db` 路径
  - [x] 成功调用已有的 `import_bt_sites(db_path)` 完成站点恢复
- [x] 优化 `safe_js.html` 页面样式
  - [x] 设计新版 HTML 结构与 CSS 变量（参考 `user_agent.html`）
  - [x] 替换原有的样式和 DOM 结构，保持 JS 与关键 ID 的兼容性
  - [x] 验证倒计时交互与视觉效果
- [x] 修复 `deploy.sh` 脚本在非交互或 piped 模式下的 `confirm` 交互提示缺失问题
- [x] 优化 `deploy.sh` 中 `acme.sh` 的安装逻辑，优先使用统一网络库 `github_download` 进行离线包下载与本地安装，杜绝 GitHub 直连下载卡死问题
- [x] 优化 `bs 11` 命令修改密码逻辑，调整为自动生成 8-12 位随机安全密码并直接输出给用户，避免弱密码安全风险
- [x] 优化 `panel_tools.py` 中的 `restore_bt_data` 恢复确认交互逻辑，自动检测 `sys.stdin` 状态和 TTY 环境，若处于非交互式 Web 面板环境下则自动确认，解决迁移恢复时面板卡死的问题
- [x] 解决数据库迁移时面板日志显示延迟（黑屏很久）的问题，在后台启动 Python 命令时添加 `-u` 参数以开启无缓冲输出，实现迁移日志在 Web 面板的实时动态展示
- [x] 在“面板设置”页面中，于“数据库迁移”下方新增“网站列表迁移”行与按钮，支持自动扫描备份的 `site.db` 路径或手动输入路径，并实现后台异步读取及 Web 进度日志回显（对应 `bs 31` 功能）
- [x] jQuery 升级 - 阶段 1：静态扫描与自动修复
  - [x] 编写静态扫描与自动修复脚本 `scripts/jq_migrate_scan.py`
  - [x] 执行静态扫描 `--report` 生成待修改报告
  - [x] 执行 `--fix` 自动修复自定义业务代码中的废弃 API
  - [x] 手动修复 `layout.html` 中的 `$.globalEval` 异步执行问题
  - [x] 确认自动修改并清理生成的临时备份文件
- [x] jQuery 升级 - 阶段 2：引入 jQuery 3.7.1 + Migrate 插件 & 升级 Bootstrap 3.4.1
  - [x] 编写并执行脚本 `scripts/download_assets.py` 下载所需 JS、CSS 与字体文件
  - [x] 修改 `layout.html` 中的引用，将其替换为 3.7.1 + Migrate + 3.4.1 的资源
  - [x] 修改 `login.html` 中的引用为新版
  - [x] 手动冒烟测试确认登录与主要页面的可用性，并记录控制台中的 JQMIGRATE 黄色警告
- [x] jQuery 升级 - 阶段 3：自动化回归测试与警告修复
  - [x] 安装必要的依赖包 `paramiko` 和 `playwright` 并安装 Chromium
  - [x] 编写并运行 `scripts/sync_to_test.py` 同步最新代码至远程测试服务器并重启面板
  - [x] 编写并运行 `scripts/jq_migrate_test.py` 进行页面回归测试，收集控制台警告
  - [x] 根据测试报告修复所有发现的兼容黄色警告，直至警告数为 0


