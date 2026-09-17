# 数据管理插件（data_query）报错彻底修复、反射调用优化与 PostgreSQL 免安装支持

> 项目概况：解决 POST /plugins/callback 报 500 Internal Server Error 问题；修复所有数据库报 get_list() got an unexpected keyword argument 'sid' 问题；实现 PostgreSQL 免安装判断并无缝兼容 plugins/pg_docker 容器实例。
> 开发规范：严格遵循 KISS 原则，所有文件使用 UTF-8 无 BOM 与 LF 换行符；跨平台兼容 Windows 开发与 Linux 部署；所有测试文件归入 test/；任务完成后主动验证并清理临时文件。

## Task List

- [x] 1. 修复底层反射调用模块签名与参数分发机制 (`web/utils/plugin.py`)
- [x] 2. 全面加固各数据库后端导出函数签名容错性 (`nosql_redis.py`, `nosql_mongodb.py`, `nosql_memcached.py`)
- [x] 3. 彻底根除 MySQL 模块 500 报错与异常对象返回序列化崩溃缺陷 (`plugins/data_query/sql_mysql.py`)
- [x] 4. 改造 PostgreSQL 模块为免安装并自动识别 `pg_docker` 容器实例 (`plugins/data_query/sql_postgresql.py`)
- [x] 5. 调整前端交互逻辑 (`plugins/data_query/static/js/app.js`)：移除 PostgreSQL 未安装拦截遮罩
- [x] 6. 加固 Flask 蓝图层 `callback` 路由防止任何未捕获异常泄漏 500 HTML (`web/admin/plugins/__init__.py`, `web/core/yf.py`)
- [x] 7. 编写与运行自动化回归测试套件 (`test/test_data_query_fix.py`, `test/test_plugin_callback_fix.py`) 验证各项修复 100% 通过
- [x] 8. 验收与编码格式校验（UTF-8 无 BOM、LF 换行符）与临时文件清理
- [x] 9. 彻底修复多线程并发调用插件导致 `KeyError` 弹窗（显示脚本模块名）缺陷 (`web/utils/plugin.py`)
- [x] 10. 优化各数据库切换时端口获取与服务列表加载时序，防止并发轰炸与状态不同步 (`plugins/data_query/static/js/app.js`)
- [x] 11. 增强 PostgreSQL 连接错误透传与诊断信息（驱动、认证、网络状态友好提示） (`plugins/data_query/sql_postgresql.py`)
- [x] 12. 编写多线程高并发压力回归测试 (`test/test_concurrent_callbacks.py`) 验证并发调用 100% 零报错
- [x] 13. 修复前端 `pt is not defined` 报错并加固国际化翻译函数兜底机制 (`plugins/data_query/static/js/app.js`)
- [x] 14. 实现 PostgreSQL 驱动检测、一键安装后端执行接口与实时滚动日志框 (`plugins/data_query/sql_postgresql.py`, `plugins/data_query/static/js/app.js`)
- [x] 15. 改造 MySQL 数据库获取与服务列表：支持免物理目录检测、兼容 MariaDB/Docker，连接受限时回退面板数据库元数据并在下拉框呈现全部可用库 (`plugins/data_query/sql_mysql.py`, `plugins/data_query/static/js/app.js`)
- [x] 16. 编写与运行自动化测试套件 (`test/test_pg_driver_and_mysql_dbs.py`)，验证驱动安装接口与 MySQL 库回退机制 100% 正常

## 重构任务清单 (多国语言、按需连接、Navicat式连接管理、UI排布优化)

- [x] 17. 扩展 SQLite 存储与统一连接管理器 (`plugins/data_query/common_db.py`)
- [x] 18. 改造五大数据库驱动适配层以支持远程连接与网络超时 (`sql_mysql.py`, `sql_postgresql.py`, `nosql_redis.py`, `nosql_mongodb.py`, `nosql_memcached.py`)
- [x] 19. 编写与执行后端连接与驱动回归测试 (`test/test_data_query_remotedb.py`)
- [x] 20. 优化前端 HTML 结构与 Flex 响应式排布 (`plugins/data_query/static/html/index.html` & `static/css/data.css`)
- [x] 21. 重构前端交互逻辑、按需连接状态机与 Navicat 连接管理弹窗 (`plugins/data_query/static/js/app.js`)
- [x] 22. 全面补充与完善 6 大国际化多语言包 (`plugins/data_query/lang/*.json`)
- [x] 23. 端到端功能回归验证、UTF-8(LF)编码检查与测试文件清理

## 本地配置自动读取、PostgreSQL多模式探测与全量国际化任务清单

- [x] 24. 实现后端本机数据库配置探测与「本机配置」自动持久化（MySQL, Redis, MongoDB, Memcached）(`plugins/data_query/common_db.py`)
- [x] 25. 实现 PostgreSQL 直接安装与 `pg_docker` 多容器实例探测与自动命名（如 `local_test1`）(`plugins/data_query/common_db.py`)
- [x] 26. 修复 `getUnifiedServerList` 参数反射签名与前端数据源聚合排序 (`common_db.py`, `app.js`)
- [x] 27. 优化前端初始化时默认选中「本机配置」、回填端口与空状态展示 (`static/js/app.js`, `static/html/index.html`)
- [x] 28. 全面打通面板左侧菜单多语言渲染 (`web/templates/default/layout.html` & `web/static/language/*/lan.js`)
- [x] 29. 全量补齐 6 大语言包中带冒号标签、空状态文案与动态提示 (`plugins/data_query/lang/*.json`)
- [x] 30. 编写自动化验证测试套件并执行端到端验证，收尾清理与编码校验

## 服务器按需同步、差异对比选择与加载性能优化任务清单

- [x] 31. 重构后端日常读取逻辑（SQLite命中零延迟）并实现扫描与差异比对分析接口（`previewLocalSyncDiff` & `applyLocalSync`）(`plugins/data_query/common_db.py`)
- [x] 32. 优化前端 HTML 与 CSS：在 `#cutTab` 右上角增加「服务器同步」按钮与对比弹窗样式 (`index.html` & `data.css`)
- [x] 33. 实现前端同步弹窗交互、新旧配置差异呈现、用户勾选确认与批量覆盖逻辑 (`static/js/app.js`)
- [x] 34. 补齐 6 大语言包中关于同步、差异对比、冲突状态与操作按钮的全部词条 (`plugins/data_query/lang/*.json`)
- [x] 35. 编写自动化测试套件 (`test/test_sync_and_speed.py`) 验证毫秒级响应、比对精度与选择性覆盖
- [x] 36. 成果全量回归、UTF-8(LF)编码校验、临时文件清理与打勾收尾

## 提示截断修复、MySQL连接Bug根治与PostgreSQL驱动自动弹窗安装任务清单

- [x] 37. 修复前端 Layer 提示框溢出截断缺陷，增加自适应宽度与自动换行 (`plugins/data_query/static/css/data.css`)
- [x] 38. 彻底重构 MySQL 连接适配层 (`sql_mysql.py`)，移除导致 AttributeError 的 `_ORM__Connect` 缺陷，支持 TCP/Socket 容灾与详细错误诊断
- [x] 39. 修复自定义连接端口读取机制 (`common_db.py`)，防止下拉选中实例后端口被全局覆盖
- [x] 40. 实现 PostgreSQL 驱动缺失自动弹窗询问（`layer.confirm`）与一键展示实时安装日志窗口 (`plugins/data_query/static/js/app.js`)
- [x] 41. 补齐 6 大语言包驱动询问弹窗词条，编写自动化测试 (`test/test_mysql_conn_and_pg_driver_prompt.py`) 并验收收尾
- [x] 42. 全方位深挖本机与官方 MySQL 密码探测源（覆盖 `default.pl`、`mysql_root.pl`、`debian.cnf`、`my.cnf`、官方 `yf.M` ORM 结构与多种字段），加固同步时不盲目清空已有密码机制 (`plugins/data_query/common_db.py`)
- [x] 43. 修复编辑连接弹窗中测试连接优先采用输入明文密码（避免读取已有密码覆盖），优化报错细节展示（透明化展示认证主体与是否包含密码） (`common_db.py`, `sql_mysql.py`)
- [x] 44. 加强本地连接智能自愈（`host=127.0.0.1` 失败时自动对齐 `localhost` / Socket 双向容灾探测），编写自动化回归测试并 100% 通过验证 (`test/test_mysql_conn_and_pg_driver_prompt.py`)
- [x] 45. 修复官方 MySQL 插件打开管理弹窗时因 `my.cnf` 缺失 `datadir` 配置触发 `AttributeError: 'NoneType' object has no attribute 'groups'` 缺陷 (`plugins/mysql/index.py`)

## MySQL 常用功能弹窗显示修复（滚动条与命令长文本自动换行）

- [x] 46. 增加与完善弹窗弹性布局、自适应独立滚动包装层与长命令强制换行样式 (`plugins/data_query/static/css/data.css`)
- [x] 47. 重构 MySQL 常用功能系列弹窗结构 (`plugins/data_query/static/js/app.js`)：为最频繁前 N 条 SQL 等弹窗增加滚动容器与 SQL 折行展示，补齐 i18n 标题
- [x] 48. 规范常用功能其他弹窗（网络指标、冗余索引、表空间统计、连接统计、锁阻塞 SQL 等）的防截断与自动换行处理 (`static/js/app.js`)
- [x] 49. 编写与运行前端样式与结构静态分析/回归验证脚本，检查 UTF-8 无 BOM、LF 换行符，清理临时测试文件
