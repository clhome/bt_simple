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

- [x] 修改 `plugins/swap/install.sh`：将 `curPath=\`pwd\`` 改为动态根据 `BASH_SOURCE[0]` 获取的绝对路径方式 @done(2026-05-22 17:28)
- [x] 验证路径解析正确性 @done(2026-05-22 17:28)
