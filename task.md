## 需求：修复 MySQL[Tar] 5.7 创建数据库时报"数据库密码错误"

**问题描述：** MySQL 5.7 插件安装后，MySQL 服务正常运行，但点击「添加数据库」时弹出"数据库密码错误,在管理列表-点击【修复】！"错误。

**根本原因分析：**
- SQLite 中记录的 `mysql_root` 密码与 MySQL 实际 root 密码不一致
- 原因1（安装阶段）：`initMysqlPwd('5.7')` 使用了 `PASSWORD()` 函数，该函数在 MySQL 5.7.6+ 中已废弃，在 `--initialize-insecure` 后的免密首次连接中执行失败，导致密码从未真正设置成功，但 SQLite 已写入新密码
- 原因2（修复阶段）：`resetDbRootPwd` 对 MySQL 5.7 也使用了同样废弃的 `PASSWORD()` 方式，导致点击【修复】后依然无法真正重置密码
- 正确方式应与 8.x 相同：先 `flush privileges` 再 `ALTER USER`

**修复文件：** `plugins/mysql/index.py`

### Task List

- [x] 修复 `initMysqlPwd` 函数（**安装阶段根源修复**）：MySQL 5.7 改用 `flush privileges + ALTER USER` 方式初始化 root 密码，从根源上消除重装后仍报错的问题 @done(2026-05-21 08:49)
- [x] 修复 `resetDbRootPwd` 函数：MySQL 5.7 改用 `flush privileges + ALTER USER` 方式（与 8.x 一致），不再使用废弃的 `PASSWORD()` 函数 @done(2026-05-21 08:42)
- [x] 修复 `fixDbAccess` 函数：增加停服/启服后的等待时间（stop后+2s，skip-grant-tables模式启动后+5s，关闭后启动+3s），确保 MySQL 完全就绪再执行密码重置 @done(2026-05-21 08:42)
- [x] 改善错误提示：`fixDbAccess` 异常时返回具体错误信息，便于调试 @done(2026-05-21 08:42)

## 需求：修复 swap 插件安装路径多出 "plugins" 报错

**问题描述：** 安装 swap 插件时，报 `python3: can't open file '/www/server/mdserver-web/plugins/plugins/swap/index.py': [Errno 2] No such file or directory` 错误。

**根本原因分析：** `install.sh` 脚本通过 `pwd` 获取当前工作目录，当执行该脚本的 Cwd 与实际脚本所在目录不一致时，二次 `dirname` 会计算出多带 `/plugins` 的 `rootPath`。

**修复文件：** `plugins/swap/install.sh`

### Task List

- [x] 修改 `plugins/swap/install.sh`：将 `curPath=\`pwd\`` 改为动态根据 `BASH_SOURCE[0]` 获取绝对路径方式 @done(2026-05-22 17:28)
- [x] 修改 `scripts/lib.sh`：将 `curPath=\`pwd\`` 改为动态根据 `BASH_SOURCE[0]` 获取绝对路径，解决被 source 时覆写全局 rootPath 变量导致 getos.sh 报错的严重缺陷 @done(2026-05-22 17:35)
- [x] 验证路径解析及公共库引入正确性 @done(2026-05-22 17:35)

## 需求：消息盒子执行日志添加时间戳

**问题描述：** 消息盒子中的执行日志里，需要加上时间，最好把显示给用户的日志都能加上时间，方便用户查看。时间样式 `[260522 14:22]`。

**根本原因分析：** 
- 面板后台运行的任务（如软件安装、插件编译等）的执行日志，是由 `panel_task.py` 中的 `execShell` 直接将子进程 stdout/stderr 重定向到 `g_log_file`（`mw.getPanelTaskExecLog()`）中。
- 由于重定向是由操作系统直接处理的，输出的内容并没有被注入时间。
- 为了让日志具有实时的、精确的时间戳，需要由 `panel_task.py` 中的 `execShell` 用 Python 自行捕获子进程的输出，在每一行前面实时拼接 `[yymmdd HH:MM]` 样式的时间前缀，然后再写入日志文件。

**修复文件：** `panel_task.py`

### Task List

- [x] 在 `panel_task.py` 中重构 `execShell` 函数，捕获子进程的标准输出与标准错误流 @done(2026-05-22 17:43)
- [x] 每一行实时增加 `[yymmdd HH:MM]` 样式的时间戳前缀并写入 `g_log_file` @done(2026-05-22 17:43)
- [x] 验证执行日志输出的时间戳格式符合 `[260522 14:22]` 样式，且进程退出和异常捕获逻辑正常 @done(2026-05-22 17:43)

## 需求：消息盒子安装日志窗口放大

**问题描述：** 消息盒子里安装过程的日志窗口偏矮（只有 200px），导致显示内容有限，不方便阅读。需要放大该窗口，展示更多日志内容。

**根本原因分析：**
- 控制消息盒子任务列表中安装日志展示窗口（`.cmd` 样式类）的 CSS 属性在 `site.css` 和 `ensite.css` 中均被硬编码为了 `height: 200px;`。
- 将此高度调整为 `400px;` 可以大大提高可见日志的行数，使其高度与“执行日志”页面更匹配，提升交互阅读体验。

**修复文件：** 
- `web/static/css/site.css`
- `web/static/css/ensite.css`

- [x] 修改 `web/static/css/site.css`：将 `.cmdlist li .cmd` 和 `.tab-con ul.cmdlist li .cmd` 中的 `height: 200px` 调整为 `height: 400px` @done(2026-05-22 17:53)
- [x] 修改 `web/static/css/ensite.css`：将 `.cmdlist li .cmd` 和 `.tab-con ul.cmdlist li .cmd` 中的 `height: 200px` 调整为 `height: 400px` @done(2026-05-22 17:53)
- [ ] 用户进行浏览器强制刷新验证（Ctrl + F5），检查调整后的日志展示高度

## 需求：修复 swap 插件状态检测与配置修改不生效问题

**问题描述：**
1. 后端检测系统 Swap 状态受 Locale 语言环境（如中文“交换”）干扰。
2. 启动脚本中多 Swap 挂载冲突，导致系统本身存在 Swap 时插件无法挂载自己的 swapfile。
3. 前端修改后页面没有重新拉取最新系统状态，用户无法判断是否生效。

**修复文件：**
- `plugins/swap/index.py`
- `plugins/swap/init.d/swap.tpl`
- `plugins/swap/js/swap.js`

### Task List

- [x] 修复 `plugins/swap/index.py` 后端状态检测：读取 `/proc/swaps` 进行插件 swapfile 挂载判定，并解析 `/proc/meminfo` 的 `SwapTotal` 获取系统真实 Swap 容量 @done(2026-05-22 18:05)
- [x] 修复 `plugins/swap/init.d/swap.tpl` 启动脚本模板：修改 `app_start` 和 `app_status` 使用 `/proc/swaps` 独立检测，不再因为系统有其他 Swap 而跳过挂载 @done(2026-05-22 18:07)
- [x] 修复 `plugins/swap/js/swap.js` 前端页面渲染与交互：在修改成功后自动调用 `swapStatus()` 重新拉取状态进行显示刷新，并同时显示系统总 Swap 与插件专属 Swap 容量 @done(2026-05-22 18:10)
- [x] 验证整体功能：在系统已有 Swap 情况下，测试修改是否能够成功使 swapfile 挂载，且前端页面正确自动刷新并能准确反映最新 Swap 容量 @done(2026-05-22 18:12)

## 需求：完善 swap 插件“说明”内容，增加不同内存配置建议与使用指引

**问题描述：**
目前插件说明极其简陋，只有两句命令行，用户无法得知不同物理内存情况下应该如何合理配置 Swap 大小，也缺乏相关注意事项说明。

**修复文件：**
- `plugins/swap/js/swap.js`

### Task List

- [x] 在 `plugins/swap/js/swap.js` 的 `readme()` 函数中，设计并渲染排版美观的 HTML “说明”界面，详细列出不同内存情况下的配置建议表格、SSD/HDD 使用注意事项、以及与系统级 Swap 叠加运行的机制 @done(2026-05-22 18:15)
- [x] 验证前台“说明”标签页的实际渲染结果与可读性 @done(2026-05-22 18:15)

## 需求：重构 Swap 插件交互界面，实现直观的当前状态、配置表单和智能配置推荐

**问题描述：**
目前的 Swap 设置界面字段堆叠，含义不明确，“最大使用交换分区”下拉框、“系统当前总 Swap”与“插件专属 Swap”、“修改大小”框并存且缺乏指引，导致用户无法理解各自的作用和如何配置。

**修复文件：**
- `plugins/swap/index.py`
- `plugins/swap/js/swap.js`

### Task List

- [x] 优化后端 `plugins/swap/index.py` 的 `swapStatus()`：在返回结果中新增物理内存总量 `mem_total` (MB) 的精准获取 @done(2026-05-22 18:22)
- [x] 重构前端 `plugins/swap/js/swap.js` 的 `swapStatus()` 渲染界面：将界面划分为清晰的“当前状态”卡片和“调整配置”表单，并根据物理内存自动生成“💡 智能配置推荐”，极大地提升交互友好度与专业感 @done(2026-05-22 18:25)
- [x] 验证优化后的界面排版与交互正常 @done(2026-05-22 18:25)

