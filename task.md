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

