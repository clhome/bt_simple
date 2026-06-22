# 项目整体描述
bt_simple 是一个简洁的 Linux 面板（轻量版服务器管理面板），使用 Python 3 和 Flask 框架构建，支持管理常用的 Web 服务与数据库（如 OpenResty, PHP, MySQL, Redis, MongoDB, Memcached 等）。

# 开发规范描述
1. **简洁至上**：恪守 KISS 原则，强调可维护性，避免过度工程化。
2. **事实优先**：以事实为准则，有错直指。
3. **编码规范**：统一使用 UTF-8 (无 BOM) 格式，换行符强制使用 LF。避免使用 PowerShell 直接修改包含中文的文件。
4. **运行环境**：简体中文 Windows 11 平台。命令行强制使用 `C:\Program Files\PowerShell\7\pwsh.exe`。
5. **开发工作流**：在设计与编码前先进行充分调研与澄清。新建 `task.md` 进行任务拆解与跟踪。
6. **修改控制**：在进行非简单修改前，需编写 `implementation_plan.md` 提交用户审核通过后方可执行。

# 任务清单

- [x] 检查并完成依赖项延迟加载（Lazy Import）优化
    - [x] 1. 完成非核心依赖项在 `plugins/data_query` 目录下的延迟加载分析与设计
    - [x] 2. 编写并提交 `implementation_plan.md` 供用户审核
    - [x] 3. 修改 `plugins/data_query/sql_mysql.py` 移除无用的全局 `pymongo` 导入
    - [x] 4. 修改 `plugins/data_query/nosql_mongodb.py` 将全局的 `pymongo` 与 `bson` 导入改为方法内局部按需导入
    - [x] 5. 修改 `plugins/data_query/nosql_redis.py` 将全局的 `redis` 导入改为方法内局部按需导入
    - [x] 6. 修改 `plugins/data_query/nosql_memcached.py` 将全局的 `pymemcache` 导入改为方法内局部按需导入
    - [x] 7. 运行本地语法或逻辑检查，并编写 `walkthrough.md` 汇总优化情况

- [x] 优化数据管理插件的说明描述
    - [x] 1. 修改 `plugins/data_query/info.json` 中的 `ps` 描述，增加 Ctrl+F5 刷新和侧边菜单操作的提示说明

- [x] 在服务管理弹窗中展示优雅的操作指引步骤
    - [x] 1. 修改 `plugins/data_query/index.html`，重载 `pluginSetService` 方法以动态载入可视化“使用指引”

- [x] 取消数据管理插件的重启、关闭服务功能并优化界面
    - [x] 1. 修改 `plugins/data_query/index.html`，移除原有的服务操作按钮，改成静态展示的免服务“使用指引”说明

- [x] 移除弹窗中的状态栏显示并调整弹窗大小
    - [x] 1. 修改 `plugins/data_query/index.html` 移除服务状态行，增大宽度到 460px，高度调为 280px 以适应静态指引内容

- [x] 在指引页面中增加“打开管理页”的跳转按钮
    - [x] 1. 修改 `plugins/data_query/index.html`，在标题右侧增加绿色“打开管理页”按钮，支持快速跳转与弹窗关闭

------

20260622 13:11Code committed
- [x] 修复 MySQL 服务重启导致数据清空的严重 BUG
    - [x] 1. 将 `plugins/mysql/index.py` 中的 `removeDir(datadir)` 改为改名备份备份机制

- [ ] 增加 MySQL 异常备份目录检测与提示
    - [x] 1. 修改 `plugins/mysql/index.py` 增加 `check_anomaly_backup` 接口
    - [x] 2. 修改 `plugins/mysql/js/mysql.js` 增加 `mySqlServiceWrapper` 检测逻辑与弹窗渲染
    - [x] 3. 修改 `plugins/mysql/index.html` 替换点击与初始化服务入口

------

20260622 14:19Code committed
