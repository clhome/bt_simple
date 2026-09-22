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

## 容器化部署 PostgreSQL 探测与多实例同步差异比对 Bug 根治

- [x] 50. 重构容器化 PostgreSQL 探测逻辑：对齐 `pg_docker` 有效容器过滤标准，增强 Docker 环境变量密码/注释清洗 (`common_db.py`)
- [x] 51. 彻底修复多容器同步差异比对算法：禁止跨容器混淆匹配、增加已匹配排重集合、为多容器生成实例级唯一标识 (`common_db.py`)
- [x] 52. 优化前端同步差异对话框名称呈现逻辑 (`plugins/data_query/static/js/app.js`)
- [x] 53. 编写与执行自动化回归测试套件 (`test/test_pg_docker_sync_fix.py`) 验证多容器比对零重合、密码零污染，完成 UTF-8/LF 校验与收尾

## 容器化 PostgreSQL 默认选中修复、认证库支持与多路由穿透连接自愈

- [x] 54. 修复数据源列表生成逻辑 (`common_db.py`)：消除已存在容器配置时被虚假「本地 PostgreSQL」霸占默认项缺陷，优先默认选中第一个有效本地/容器配置
- [x] 55. 增强 PostgreSQL 实例解析与认证库配置 (`sql_postgresql.py`)：在物理服务未安装时将 `sid=pgsql` 智能自愈对齐到容器，连接优先使用 `auth_db`
- [x] 56. 实现 Docker 容器多路由网络自愈与 IP 直连容灾 (`sql_postgresql.py`)：解决 127.0.0.1 回环被拒导致端口不通问题，支持 localhost/网关/容器IP 智能穿透
- [x] 57. 编写与执行自动化回归测试套件 (`test/test_pg_connection_and_routing.py`)，验证默认选择、认证库连接与网络容灾，完成编码检查与收尾

## 数据管理插件全量多国语言适配与界面死角彻底本地化

- [x] 58. 重构前端翻译核心与本地字典加速机制 (`static/js/app.js` 中的 `pt` 函数)，优先调用插件专属字典并实现 0ms 本地字典缓存
- [x] 59. 增强前端 `translateDataQueryDOM` 与服务下拉框动态前缀多语言适配 (`app.js`)：全面覆盖搜索按钮、底部选项卡、表头与下拉框 `容器:`/`本机配置`/`远程:`
- [x] 60. 全量补齐 6 大语言包中的界面、按钮、选项卡与表头词条 (`plugins/data_query/lang/*.json`)
- [x] 61. 编写与运行自动化回归测试套件 (`test/test_data_query_i18n.py`) 验证 6 大语言完整覆盖并校验编码与清理收尾

## 标签页未安装遮罩霸屏与 Tab 状态隔离 Bug 彻底修复

- [x] 62. 根除全屏未安装遮罩霸屏缺陷：彻底废除 `showInstallLayer`，移除 Redis/MongoDB/Memcached/MySQL 连接失败或无服务器时触发全局遮罩的代码 (`plugins/data_query/static/js/app.js`)
- [x] 63. 加固 Tab 切换隔离与遮罩重置机制 (`selectTab`)，并在 `index.html` 中永久隐藏旧残留遮罩 (`index.html`, `app.js`)
- [x] 64. 编写与运行自动化回归测试套件 (`test/test_no_install_mask_bug.py`) 验证修复有效性与全数据库状态独立性，清理收尾与编码校验

## MySQL 插件升级故障根治、平滑无损升级与自动自愈任务清单

- [x] 65. 重构状态探针 `status(version)`：结合进程树（`Process`）、网络端口（`Port`）、套接字（`Socket`）多模态探活，进程存活时自动自愈补齐 PID 文件 (`plugins/mysql/index.py`)
- [x] 66. 安全启动与“零触碰”防御机制：废除破坏性 `pkill -9`，增加残留套接字死锁清理，日常启动严格禁止重命名备份数据目录 (`plugins/mysql/index.py`)
- [x] 67. SQLite 数据库结构与服务配置幂等自愈：启动/检查时自动为老库 `databases` 补齐 `rw` 字段，校准 `mysql.service` 与 systemd 重载 (`plugins/mysql/index.py`)
- [x] 68. 改造 `plugins/mysql/install.sh`：检测到已有实例时平滑进入无损升级/自愈流程，不再机械 `exit 0`，完成服务更新与权限同步 (`plugins/mysql/install.sh`)
- [x] 69. 强化 `plugins/data_query` 与 MySQL 的自愈互通：加固对已升级/正在启动中实例的连接重试与密码快照双向校准 (`plugins/data_query/common_db.py`, `plugins/data_query/sql_mysql.py`)
- [x] 70. 编写自动化回归测试套件 (`test/test_mysql_upgrade_self_healing.py`)，验证老环境升级、PID自愈、无损启动与 `data_query` 自动同步 100% 通过
- [x] 71. 成果全量回归、UTF-8(LF)编码检查与临时文件清理收尾

## 大版本升级检测框架与 MariaDB 插件自愈任务清单

- [x] 72. 为 MySQL 插件实现大版本升级检测与单次自愈迁移框架（支持 1.x->2.x 升级自动自愈一次，并保留未来升级接口） (`plugins/mysql/index.py`)
- [x] 73. 对齐改造 MariaDB 插件自愈功能：多模态健康探针、孤儿 Socket 清理与数据零触碰防御 (`plugins/mariadb/index.py`)
- [x] 74. 对齐改造 MariaDB 插件元数据自愈与版本升级迁移框架：SQLite `rw` 字段自动补齐、`mariadb.sql` 幂等与 `checkPluginUpgrade` (`plugins/mariadb/index.py`, `conf/mariadb.sql`)
- [x] 75. 改造 MariaDB 安装升级脚本衔接无损自愈 (`plugins/mariadb/install.sh`)
- [x] 76. 编写自动化回归测试套件 (`test/test_upgrade_and_mariadb_self_healing.py`)，验证 MySQL 与 MariaDB 单次升级自愈、版本跳跃与扩展接口
- [x] 77. 全量测试回归、UTF-8(LF)校验与清理收尾

## Docker 管理器离线镜像导出/导入功能 Bug 修复与优化任务清单

- [x] 78. 重构后端离线镜像列表与过滤排序 (`plugins/docker/index.py` 中的 `dockerImagePickList`)
- [x] 79. 修复后端多镜像打包参数拼接与真实 Shell 错误捕获 (`plugins/docker/index.py` 中的 `dockerImagePickSave`)
- [x] 80. 加固后端镜像导入校验、路径安全防护与假成功根除 (`plugins/docker/index.py` 中的 `dockerImagePickLoad`)
- [x] 81. 修复前端打包弹窗未选镜像校验、增加上传格式限制、空状态与 loading 交互 (`plugins/docker/js/docker.js`)
- [x] 82. 编写与运行自动化回归测试套件 (`test/test_docker_image_pick.py`)，验证过滤、排序、多镜像打包命令构造与导入校验
- [x] 83. 成果全量回归、UTF-8(LF)编码校验与清理收尾
- [x] 84. 修复「上传镜像」点击报 `dPostOrgin is not defined` 缺陷，对齐统一 `api.post('image_pick_dir')` (`plugins/docker/js/docker.js`)
- [x] 85. 彻底修复 Docker 插件 3 处多语言缺失与匹配缺陷（默认路径裸文、加速器前导空格、出品方署名绑定与 6 大语言包全量补齐） (`docker.js`, `index.html`, `lang/*.json`)

## MySQL 插件多选数据库批量独立备份与打包下载任务清单

- [x] 86. 重构前端按钮与交互逻辑：移除「删除选中」，替换为「备份并下载选中」，实现多选精准提取、串行独立备份与实时进度弹窗 (`plugins/mysql/js/mysql.js`)
- [x] 87. 增强后端备份与新增打包接口：优化 `setDbBackup` 返回最新备份文件路径，实现 `packageDbBackups` 高效 ZIP 归档与清理 (`plugins/mysql/index.py`)
- [x] 88. 补齐 6 大国际化语言包词条：备份并下载选中、多库进度与状态提示 (`plugins/mysql/lang/*.json`)
- [x] 89. 编写与运行自动化测试套件 (`test/test_mysql_batch_backup.py`) 验证打包、路径提取、ZIP 结构与容错机制
- [x] 90. 成果全量回归、UTF-8(LF)编码校验与清理收尾
- [x] 91. 精简非中文多语言文案（英文改为 `Backup & Download`，德/法/意同步精简）并拓宽管理弹窗尺寸至 1180px，彻底消除多语言下操作栏按钮折行缺陷 (`lang/*.json`, `plugins/mysql/index.html`)
- [x] 92. 彻底根除 `setDbBackup` 使用 `os.system` 导致子进程控制台日志泄露污染 API JSON 返回缺陷，并在前端实现鲁棒的自愈提取解析与全流程错误阻断 (`plugins/mysql/index.py`, `plugins/mysql/js/mysql.js`)

## Redis 插件启动故障根治与平滑无损升级自愈任务清单

- [x] 93. 重构 Redis systemd 服务模板 (`plugins/redis/init.d/redis.service.tpl`)：添加标准 `PIDFile`，废除暴力强杀 `pkill -9`，配置启动超时与重启策略
- [x] 94. 重构状态探针 `status()` 与多模态探活自愈 (`plugins/redis/index.py`)：整合 PID 文件、进程树探针 (`pgrep`)、端口监听与 systemd 状态，存活时自动写回真实 PID，彻底消除假死误判
- [x] 95. 生产配置与密码“零触碰”防御与初始化加固 (`plugins/redis/index.py` 中的 `initDreplace`)：已有 `redis.conf` 绝对禁止覆盖重置，保留密码与端口，补齐 `init.pl` 与运行目录自愈
- [x] 96. 启动闭环校验与假成功彻底拦截 (`plugins/redis/index.py` 中的 `start` / `redisOp`)：拉起后同步探活，未成功拉起时提取真实日志报错返回，避免假阳性
- [x] 97. 实现大版本升级检测与单次自愈流水线 (`plugins/redis/index.py` 中的 `checkPluginUpgrade` 与 `upgradeSelfHealing`)：支持 1.x->2.0 自动单次自愈，清理 apt 冲突服务、重置 systemd 失败状态、对齐版本标记
- [x] 98. 改造安装升级脚本 (`plugins/redis/install.sh`)：检测到已有实例时平滑进入无损升级自愈，不再重复编译
- [x] 99. 更新 `README.md` 中的自愈命令文档，添加 Redis 插件的 `check_plugin_upgrade` 与 `upgrade_self_healing` 使用说明
- [x] 100. 编写自动化回归测试套件 (`test/test_redis_upgrade_self_healing.py`)，验证多模态探针、PID 自愈、配置保护、升级检测与单次执行特性 100% 通过
- [x] 101. 成果全量回归、UTF-8(LF)编码检查与临时文件清理收尾

## Redis 插件版本丢失、配置为空与传参缺陷自愈任务清单

- [x] 102. 彻底修复 `getArgs()` 参数解析与偏移缺陷 (`plugins/redis/index.py`)：智能支持无版本传参 (`sys.argv[2]`) 与多版本传参 (`sys.argv[3]`)，根除 `参数:(file)没有!`
- [x] 103. 实现配置多源智能探测与自愈同步 (`plugins/redis/index.py` 中的 `getConf` / `detectAndFixConf`)：支持从运行进程参数、`/etc/redis/redis.conf`、`/etc/redis.conf` 自愈，保证 `redis.conf` 绝不为空
- [x] 104. 重构性能调整配置正则提取与保存逻辑 (`plugins/redis/index.py` 中的 `getRedisConfInfo` / `submitRedisConf`)：支持特殊字符密码、IPv6、引号包裹与行尾注释，杜绝配置读出为空
- [x] 105. 实现 Redis 二进制版本自愈与面板版本探测增强 (`plugins/redis/index.py`, `web/utils/plugin.py`)：通过 `redis-server -v` 自动探测并写回 `version.pl`
- [x] 106. 优化前端弹窗标题格式化逻辑 (`web/static/app/soft.js`)：彻底消除 `Redis [] Manage` 空白方括号
- [x] 107. 编写与运行自动化回归测试套件 (`test/test_redis_config_and_version_fix.py`) 验证版本探测、参数解析与正则匹配 100% 通过
- [x] 108. 成果全量回归、UTF-8(LF)编码检查与收尾

## Redis 弹窗细节美化、状态值修复、双滚动条消除与 Data Manager 连接自愈任务清单

- [x] 109. 优化性能调整 input 宽度与 Flex 对齐排版 (`plugins/redis/js/redis.js`)：IP 与密码扩至 260px，去除生硬逗号，优化布局结构
- [x] 110. 补齐性能调整说明文字多语言字典与翻译调用 (`plugins/redis/js/redis.js`, `plugins/redis/lang/*.json`)：支持中英法德意繁全面多语言
- [x] 111. 修复负载状态（load status）全部 undefined 根因 (`plugins/redis/index.py` 中的 `getRedisCmd` / `runInfo`)：精准识别密码与端口，避免未认证返回空
- [x] 112. 优化弹窗布局样式与消除双滚动条 (`plugins/redis/index.html`, `web/static/app/soft.js`)：消除重复标题版本，解决滚动条重叠与高度不足
- [x] 113. 优化运行日志获取逻辑与空日志自愈 (`plugins/redis/index.py` 中的 `runLog`)：动态解析配置文件中的真实 `logfile` 路径
- [x] 114. 修复 Data Manager 连接 Redis 失败根因 (`plugins/data_query/nosql_redis.py`)：智能解析带 IPv6 的 bind 与双引号密码，提供详尽异常诊断
- [x] 115. 编写自动化回归测试套件 (`test/test_redis_ui_and_datamanager_fix.py`) 验证状态读取、参数提取、密码处理与 Data Manager 连接 100% 通过

## Redis 性能配置宽屏自适应、内存密码热同步与负载状态全自动自愈任务清单

- [x] 116. 性能调整表单 CSS 隔离与宽屏舒展 (`plugins/redis/js/redis.js`, `plugins/redis/index.html`)：废除受污染的 `.conf_p span` 样式，说明文字单行完整舒展铺开，彻底消除换行
- [x] 117. 配置提交真实生效机制修复 (`plugins/redis/index.py` 中的 `submitRedisConf`)：将无效的 `reload()` 替换为平滑安全的 `restart()`，确保配置与内存 100% 同步生效
- [x] 118. Data Manager 本地 Redis 连接在线热同步与自愈重连 (`plugins/data_query/nosql_redis.py`)：检测到 `invalid username-password` 时尝试在线 CONFIG SET 或自动平滑自愈重连
- [x] 119. 负载状态读取失败自动自愈与精准诊断 (`plugins/redis/index.py` 中的 `runInfo` 与 `getRedisCmd`)：对齐命令转义，当密码分歧时自动触发自愈并重试提取，杜绝“未能读取到有效状态数据”
- [x] 120. 编写与运行自动化回归测试套件 (`test/test_redis_hot_sync_and_full_width.py`) 验证宽屏排版、热同步自愈与状态提取 100% 通过
- [x] 121. 成果全量回归、UTF-8(LF)编码校验、临时文件清理与打勾收尾

## Redis 性能配置 input 统一等宽与原生 RESP/Socket 零依赖状态读取自愈清单

- [x] 122. 性能调整所有配置项 input 框宽度统一为 200px (`plugins/redis/js/redis.js`)
- [x] 123. 重构 Redis 状态获取机制：实现三级执行器（Python redis 模块 -> 原生 Socket RESP 零依赖直连 -> redis-cli 回退） (`plugins/redis/index.py`)
- [x] 124. 同步升级 `infoReplication`、`clusterInfo`、`clusterNodes` 为三级可靠执行器 (`plugins/redis/index.py`)
- [x] 125. 编写与运行自动化回归测试套件 (`test/test_redis_resp_socket_and_uniform_inputs.py`)
- [x] 126. 成果全量回归、UTF-8(LF)编码校验、临时文件清理与打勾收尾

## Redis 运行日志空白彻底根除、专属现代化日志视图与业务说明自愈清单

- [x] 127. 彻底移除 `restart()` 中粗暴清空日志文件缺陷，改为安全追加重启活跃记录 (`plugins/redis/index.py`)
- [x] 128. 增强后端日志接口：实现 `getRunLog()` 与 `clearRunLog()`，支持多模态日志自愈（物理文件 -> systemd journalctl 提取 -> 格式化健康诊断），并动态确保 `redis.conf` 具备有效绝对路径 `logfile` (`plugins/redis/index.py`)
- [x] 129. 前端构建专属现代化日志视图 `redisRunLog()` (`plugins/redis/js/redis.js`, `plugins/redis/index.html`)：
  - 路径与状态实时展示；
  - 提供【刷新日志】与【清空日志】便捷控制；
  - 增加醒目的绿色多语言业务提示条：明确说明“Redis 为内存数据库，默认仅记录生命周期、快照与告警事件，常规键值读写记录不写入运行日志”；
  - 等宽代码字体、暗色终端高对比配色、高度自适应，彻底杜绝黑屏空白。
- [x] 130. 补充 6 国国际化多语言词条 (`plugins/redis/lang/*.json`)：日志文件、刷新日志、清空日志、说明等全面适配
- [x] 131. 编写与运行自动化回归测试套件 (`test/test_redis_run_log_fix.py`) 6 项测试全部通过
- [x] 132. 成果全量回归、UTF-8(LF)编码校验、临时文件清理与打勾收尾

## Redis 状态数据解析字典格式兼容与误报根治清单

- [x] 133. 修复 Python `redis` 客户端返回 dict 字典导致 `runInfo()`、`infoReplication()` 与 `clusterInfo()` 解析失败并误判触发重启的缺陷 (`plugins/redis/index.py`)
- [x] 134. 在 `execRedisCommand` 增加 `format_redis_res` 将 Python 字典转为标准多行键值字符串，保持协议一致性 (`plugins/redis/index.py`)
- [x] 135. 在 `runInfo()`、`infoReplication()`、`clusterInfo()` 中构建三重容灾提取（标准换行 -> `ast.literal_eval` -> 正则匹配），彻底杜绝“未能读取到有效的 Redis 状态数据” (`plugins/redis/index.py`)
- [x] 136. 更新自动化测试套件 (`test/test_redis_resp_socket_and_uniform_inputs.py`) 加入用户真实数据字典解析测试，4 项测试全部通过
- [x] 137. 成果全量回归、UTF-8(LF)编码校验、临时文件清理与打勾收尾

## Redis 主从/集群状态多语言补全、配置修改提示本地化与菜单防截断清单

- [x] 138. 优化公共配置模板多语言机制与回退链条 (`web/static/app/public.js` 中的 `pluginConfigTpl`)
- [x] 139. 补全 6 国公共语言包配置修改提示词条 (`web/static/language/*/public.json`)：`tip_use_ctrl_to_2`, `this_is_2`, `main_configuration_file_if_1`, `retrieving_configuration_template`
- [x] 140. 优化 Redis 左侧菜单栏宽度 (140px) 与精炼 6 国语言导航词条 (`plugins/redis/index.html`, `plugins/redis/lang/*.json`)，彻底根除英文截断 (Configurat..., Performan..., master-)
- [x] 141. 注入与校准 6 国语言包中 21 个主从状态与 13 个集群状态说明词条 (`plugins/redis/lang/*.json`)，采用 Redis 官方权威术语
- [x] 142. 编写自动化回归测试套件 (`test/test_redis_i18n_completion.py`) 验证 6 国语言包词条 100% 覆盖、JSON 合法性与 `pluginConfigTpl` 渲染
- [x] 143. 全量测试回归、UTF-8(LF)编码校验、临时文件清理与打勾收尾

## PHP 插件三剑客（php、php-apt、php-yum）大版本升级自愈与全链路健壮性重构任务清单

- [x] 144. 批量清理 `plugins/php/versions/*/install.sh` 中的 `------` 语法事故尾缀 (14 个版本)
- [x] 145. 加固 `plugins/php/init.d/php.service.tpl` 与 `php.service.52.tpl`：注入完整高可用动态库 `LD_LIBRARY_PATH` 并规范守护参数
- [x] 146. 重构 `plugins/php/index.py`：实现大版本单次自愈流水线 (`checkPluginUpgrade`, `upgradeSelfHealing`)、三级容灾拉起 (Systemd/SysVInit/直接执行) 与双模态精准探活
- [x] 147. 修复 `plugins/php/index_php.py` 中的 `sock.find(':')` 逻辑判断 Bug 并替换不安全 `os.system` 为安全目录清理
- [x] 148. 对齐重构 `plugins/php-apt/index.py`：实现大版本单次自愈、`/run/php` 运行目录自愈补全、重置 failed 与安全命令加固
- [x] 149. 对齐重构 `plugins/php-yum/index.py`：实现大版本单次自愈、Remi 运行目录自愈补全、重置 failed 与安全命令加固
- [x] 150. 前端服务管理界面升级：为 `php`、`php-apt`、`php-yum` 增设【自愈修复】功能与详细自愈报告弹窗 (`index.html`, `js/php.js`)
- [x] 151. 全面补齐 6 国语言包词条 (`zh-CN`, `zh-TW`, `en`, `de`, `fr`, `it`) 覆盖自愈与错误诊断
- [x] 152. 更新 `README.md` 与 `plugins/plugins_check.md` 中的自愈命令与插件完成状态
- [x] 153. 编写与运行自动化回归测试套件 (`test/test_php_plugins_self_healing.py`) 验证版本跃迁、单次自愈、三级拉起与精准探活 100% 通过
- [x] 154. 成果全量回归、UTF-8(LF)编码检查与临时测试文件清理收尾

## PHP 插件配置正则提取崩溃、FPM 语法错误根治与前端界面整体修复清单

- [x] 155. 根治全局正则提取致命崩溃 (`AttributeError: 'NoneType' object has no attribute 'groups'`)：重构 `getDisableFunc`、`getFpmConfig`、`getLimitConf`、`getPhpConf`、`getSessionConf`，建立全量判空防御与智能默认值兜底 (`plugins/php/index.py`, `plugins/php-apt/index.py`, `plugins/php-yum/index.py`)
- [x] 156. 根治 PHP-FPM 配置语法错误：清理 `php-fpm.conf` 中非法的 `php_value[auto_prepend_file]`（PHP-FPM global 段禁止包含 php_value），并在自愈迁移与池配置中安全收口
- [x] 157. 修复 `plugins/php/index.py` 中 `phpOp` 的目录混淆笔误：修正 `server_dir = yf.getServerDir()` 为 `getServerDir()`，彻底消除 `/www/server/80` 错误路径
- [x] 158. 实现配置文件自动健全与缺失自愈：当 `php.ini` 或池配置不存在时，自动从模板生成，彻底解决配置修改空白与编辑文件为空
- [x] 159. 优化左侧菜单宽度与英文截断：将 `plugins/php*/index.html` 的 `.bt-w-menu` 宽度从 125px 调整至 140px，窗口宽度调至 880px，精炼 6 国语言菜单文案
- [x] 160. 修复性能调整等界面的中英混杂文案与多语言模板插值 (`plugins/php*/js/php.js`, `plugins/php*/lang/*.json`)
- [x] 161. 编写与运行自动化回归测试套件 (`test/test_php_config_robustness_and_startup.py`) 验证正则判空防御、FPM 语法自愈、路径校准与界面数据加载 100% 通过
- [x] 162. 成果全量回归、UTF-8(LF)编码检查与临时测试文件清理收尾

## PHP 插件 No pool defined 启动失败根治与前端多页面翻译代码裸露修复清单

- [x] 163. 重构 `phpFpmReplace` 与 `phpFpmPoolReplace`：实现 `include` 指令绝对路径自愈、去除注释，以及 `www.conf` 核心工作池缺损自愈，彻底根治 `No pool defined` (`plugins/php/index.py`, `plugins/php-apt/index.py`, `plugins/php-yum/index.py`)
- [x] 164. 加固启动预检与自愈流水线 (`phpOp`, `upgradeSelfHealing`)：启动前强制预检工作池与主配置健全性，并在升级自愈中建立池自愈闭环 (`plugins/php*/index.py`)
- [x] 165. 彻底修复前端 `js/php.js` 模板引号混淆与代码裸露 (`plugins/php/js/php.js`, `plugins/php-apt/js/php.js`, `plugins/php-yum/js/php.js`)：全面校准双引号模板内部插值 `" + pt(...) + "`，消除 `' + pt(...) + '` 裸露
- [x] 166. 精炼 6 国语言包中“常用功能”文案（`Common Tools` -> `Common`），彻底消除 140px 菜单截断 (`plugins/php*/lang/*.json`)
- [x] 167. 编写与运行自动化回归测试套件 (`test/test_php_pool_healing_and_ui_quotes.py`)，验证池自愈与前端引号 100% 通过，UTF-8(LF)编码检查与收尾

## PHP 插件配置文件与禁用函数空白自愈、性能排版与会话表格多语言适配清单

- [x] 168. 修复 `plugins/php/index.py` 中 `makePhpIni` 与 `getConf` 的相互递归调用缺陷，建立缺损/0字节损坏物理文件自愈生成机制，彻底解决配置文件为空与禁用函数列表为空
- [x] 169. 对齐加固 `plugins/php-apt` 与 `plugins/php-yum` 的 `getConf` 与 `getDisableFunc` 缺损自愈
- [x] 170. 重构性能调整（Performance）表单排版：隔离并拓宽 `.bingfa .line .span_tit` 弹性适配（165px~180px）、拓宽并发方案下拉框（150px），杜绝多语言截断与挤压 (`plugins/php*/index.html`, `plugins/php*/js/php.js`)
- [x] 171. 重构会话管理（Session）清理文件表格 `.session_clear_list`：使用 Flex 自适应弹性布局替代写死 270px 宽度与固定高度，彻底杜绝多语言换行重叠与按钮拥挤 (`plugins/php*/index.html`)
- [x] 172. 补齐 6 国公共语言包（`web/static/language/*/public.json`）中配置文件编辑界面的提示词条（`tip_use_ctrl_to_1`, `this_is_1`, `main_configuration_file_if`, `save_4`），消除中文裸露
- [x] 173. 编写与运行自动化回归测试套件 (`test/test_php_ini_self_healing_and_i18n_layout.py`) 验证配置自愈、禁用函数加载、表单排版与公共词条 100% 通过，UTF-8(LF)编码校验与收尾

## PHP 插件配置修改多语言说明补齐、宽屏舒展排版与还原默认值全链路落地清单

- [x] 174. 彻底修复配置修改说明文字中文裸露与生硬逗号，并将下拉框与输入项宽度拓宽至 100px 消除 `Turn o` 截断 (`plugins/php*/js/php.js`, `plugins/php*/index.html`)
- [x] 175. 左侧菜单栏宽度由 140px 拓宽至 155px，精炼 6 国语言菜单词条，彻底杜绝 `Configurati...` 截断 (`plugins/php*/index.html`, `plugins/php*/lang/*.json`)
- [x] 176. 后端实现 `reset_php_conf(version)` 接口与命令行派发：支持将 15 项核心配置重置为官方安全优化默认基准值并自动 reload 重载生效 (`plugins/php/index.py`, `plugins/php-apt/index.py`, `plugins/php-yum/index.py`)
- [x] 177. 前端在【配置修改】与【禁用函数】页面增设【还原默认值】按钮与二次确认交互弹窗 (`plugins/php*/js/php.js`)
- [x] 178. 补全 6 国语言包中“还原默认值”、“确定要将 PHP 配置还原为推荐的默认值吗？”等国际化词条 (`plugins/php*/lang/*.json`)
- [x] 179. 编写与运行自动化回归测试套件 (`test/test_php_reset_defaults_and_full_i18n.py`) 验证多语言翻译、排版布局、还原默认值接口与前端交互 100% 通过，收尾验证

## PHP-APT 扩展安装死锁触发器防频降级与 PHP 源码版解压编译容灾加固清单

- [x] 180. 解决 `php-apt` 安装失败：在扩展安装时抑制高频 restart（设置 `PHP_EXT_NO_RESTART=1`），并在启动/重启前执行 `systemctl reset-failed` 彻底根除 `start-limit-hit` 崩溃 (`plugins/php-apt/install.sh`, `plugins/php-apt/versions/common.sh`, `plugins/php-apt/index.py`)
- [x] 181. 修复 PHP 源码版安装全版本 `MEM_INFO` 内存探测缺陷，兼容非英文环境，杜绝 `[: : 需要整数表达式` 语法崩溃 (`plugins/php/versions/*/install.sh`)
- [x] 182. 根治 PHP 源码版解压异常 EOF 与源码嵌套缺陷：自动检测补全 `xz-utils`/`xz` 依赖，改用 `--strip-components=1 -C` 原地解压根除 `mv` 目录嵌套，引入 `xz -dc` 管道与 `.tar.gz` 容灾回退，增加 `main/php_version.h` 完整性校验 (`plugins/php/versions/*/install.sh`)
- [x] 183. 编写与运行自动化回归测试套件 (`test/test_php_install_fixes.py`) 验证解压容灾、内存探测、APT 频控保护与全版本语法 100% 通过
- [x] 184. 成果全量回归、UTF-8(LF)编码校验、临时文件清理与打勾收尾

## PHP-YUM 扩展安装死锁触发器防频降级与 Remi 源大版本适配清单

- [x] 185. 解决 `php-yum` 批量安装扩展高频重启：在扩展循环安装前后导出 `PHP_EXT_NO_RESTART=1` / `unset PHP_EXT_NO_RESTART`，并在 `common.sh` 中跳过重启，末尾统一执行 `systemctl reset-failed` + `systemctl restart` (`plugins/php-yum/install.sh`, `plugins/php-yum/versions/common.sh`)
- [x] 186. 优化 `plugins/php-yum/install.sh` 中 Remi 源安装：增加 `${VERSION_ID%%.*}` 大版本截取与已安装判断，防止次版本号 (如 8.5/9.4) 请求 404；Composer 下载增加国内/官方容灾双回退
- [x] 187. 在 `plugins/php-yum/versions/common.sh` 单扩展独立安装重启逻辑中加入 `systemctl reset-failed` 恢复保障
- [x] 188. 编写与运行自动化回归测试套件 (`test/test_php_yum_install_fixes.py`) 验证频控抑制、版本截取、reset-failed 与脚本健壮性 100% 通过
- [x] 189. 成果全量回归、UTF-8(LF)编码校验、临时文件清理与打勾收尾

## PHP 插件三剑客（php、php-apt、php-yum）安装脚本全链路优化（中美双轨、速度爆发与安全加固）清单

- [x] 190. 优化 `plugins/php-apt/install.sh`：实现 `curPath` 跨路径安全解析、dpkg 锁等待、中美双轨选源、GPG 原子下载与批量扩展合并安装
- [x] 191. 优化 `plugins/php-apt/versions/common.sh` 与 `versions/*/install.sh`：修复路径与过滤内置无包扩展
- [x] 192. 优化 `plugins/php-yum/install.sh`：补全 `epel-release`、拓宽主流发行版识别、中美双轨选源、消除管道高危代码与批量扩展合并安装
- [x] 193. 优化 `plugins/php-yum/versions/lib.sh`、`common.sh` 与 `versions/*/install.sh`：清理代码混乱与修复路径
- [x] 194. 优化 `plugins/php/install.sh` 与各扩展脚本（`versions/common/*.sh`）：根除误删主源码死循环、引入频控重启抑制、HTTPS 升级
- [x] 195. 编写与运行自动化回归测试套件 (`test/test_php_install_optimization.py`) 验证语法、双轨选源、批量安装与防回退机制 100% 通过
- [x] 196. 成果全量回归、UTF-8(LF)编码校验、临时文件清理与打勾收尾
- [x] 197. 彻底根治 `plugins/php` 源码版空目录阻断解压缺陷：将 15 个子版本判断从 `[ ! -d ... ]` 改为 `[ ! -f .../main/php_version.h ]`，杜绝 `cannot find sources` 致命中断
- [x] 198. 彻底根治 `plugins/php-apt` 与 `plugins/php-yum` 子版本路径浅层计算缺陷：校准 `rootPath=$(cd "$curPath/../../../.."; pwd)` 深度至 4 级，根除错建目录与外层误判跳出
- [x] 199. 增加子版本路径深度与头文件存在性回归测试（`test_09`、`test_10`），全量回归 100% 通过与收尾

## PHP 插件三剑客安装脚本深度审计、BUG修复与安全加固清单

- [x] 200. 修复 `php-apt` 与 `php-yum` 的 `opcache.sh` 黑名单路径重复拼接 `${serverPath}/server/...` 致命 Bug (`plugins/php-apt/versions/common/opcache.sh`, `plugins/php-yum/versions/common/opcache.sh`)
- [x] 201. 修复三个 PHP 插件 opcache JIT 语法与 PHP 8.4+ 字符串模式兼容（`opcache.jit=tracing`），并增强 `opcache.enable` 幂等检测防止多次安装重复追加配置 (`plugins/php*/versions/common/opcache.sh`)
- [x] 202. 补充 `php-apt` 与 `php-yum` 的 `index.py` 路由派发：新增 `get_php_info` 分支与前端 JS 命名对齐，彻底解决点击查看 phpinfo 返回 fail (`plugins/php-apt/index.py`, `plugins/php-yum/index.py`)
- [x] 203. 加固 `php-apt` 5 个 PECL 扩展脚本（`swoole.sh`, `brotli.sh`, `seaslog.sh`, `yaf.sh`, `yar.sh`）：全面升级为 HTTPS 下载链接、增加 `--no-check-certificate` 与压缩包本地存在性缓存检测，防止网络重下与中间人风险
- [x] 204. 编写与运行自动化回归测试套件 (`test/test_php_installer_security_and_bugs.py`)，验证路由派发、路径拼接、JIT 语法、幂等性与 HTTPS 校验 100% 通过
- [x] 205. 全量测试回归、UTF-8(LF)编码校验与清理收尾

## PHP-APT 服务异常停止与 Systemd Type=notify 假死全链路修复与启动优化清单

- [x] 211. 补全 `plugins/php-apt/conf/php-fpm.conf` 全局健康与控制参数：增加 `systemd_interval = 10`、`process_control_timeout = 10s`、`emergency_restart_threshold = 10`、`emergency_restart_interval = 1m`
- [x] 212. 优化 `plugins/php-apt/conf/www.conf`：优化动态进程管理配置，降低小内存 VPS 空载进程数与突发 OOM 风险
- [x] 213. 重构 `plugins/php-apt/index.py`：注入 systemd override 容灾配置（解除 `StartLimitBurst`，配置 `Restart=always`、`TimeoutStartSec=60s`），修复 `status` 中 `ps aux` 降级正则与 `activating` 过渡态误判
- [x] 214. 重构 `plugins/php-apt/install.sh`：彻底消除安装过程中的 5 次密集启动风暴，实现单次平滑拉起与 10 秒过渡缓冲
- [x] 215. 加固 `web/utils/plugin.py` 中 `checkStatusQuick`：增加对 `php-apt` 真实 PID 路径（`/run/php/php{version}-fpm.pid`）的轻量快速探测，杜绝内外状态不一致
- [x] 216. 编写与运行自动化回归测试套件 (`test/test_php_apt_fpm_fix.py`)：覆盖配置参数完整性、systemd override 逻辑、状态匹配正则与平滑重启流程
- [x] 217. 全量测试回归、UTF-8(LF)编码校验、即时更新 task.md 并清理临时测试文件

## 系统升级自动清除废弃插件 system_safe 任务清单

- [x] 218. 编写系统级废弃插件自动清除与防御模块 (`web/admin/setup/cleanup.py`)：实现对 `system_safe` 的检测、解除 chattr 锁定、停止服务、杀灭进程、禁止自启、移除 service/init.d 脚本与文件清理
- [x] 219. 集成到面板启动初始化流程 (`web/admin/setup/__init__.py`)：在 `setup.init()` 中调用清理逻辑，确保升级或重启时幂等自愈
- [x] 220. 集成到 Web 端系统升级流程 (`web/utils/system/update.py`)：在 `updateServer` 代码覆盖与环境更新后即时触发清理
- [x] 221. 集成到 CLI 升级脚本 (`scripts/update.sh` 和 `scripts/update_dev.sh`)：在覆盖代码后、重启服务前检测并彻底清理 `system_safe`
- [x] 222. 编写与运行自动化回归测试套件 (`test/test_cleanup_system_safe.py`)：验证检测算法、清理步骤的安全性与幂等性
- [x] 223. 在测试服务器上执行清理验证与 status 确认，确保 `php8.4-fpm` 长期正常运行
- [x] 224. 成果全量回归、UTF-8(LF)编码校验、即时更新 task.md 并清理临时测试文件

## 御风F2B防火墙（fail2ban）插件可靠性/安全性/多语言/性能四维审计与全链路优化清单

### 阶段一：四维审计（产出报告）

- [x] 225. 输出 fail2ban 插件四维审计报告 (`test/tmp_f2b/fail2ban_optimization_report.md`)：逐项给出 P0/P1/P2 优先级、行号证据、代码片段与验证方法
- [x] 226. 编写可复用 i18n 一致性检查器 (`test/tmp_f2b/check.py`)：统计 `pt()` 字面量与 zh-CN 键差异、定位 `pt()` 外中文、HTML 注入译文检测、zh-TW 简体字泄漏、死键扫描

### 阶段二：安全加固（P0）

- [x] 227. 修复命令注入：新增 `safe_ip()` / `safe_port()` / `safe_int()` / `safe_bool()` 与 `ALLOWED_MODES` 白名单，`f2b_client()` 统一经 `shlex.quote` 转义全部参数 (`plugins/fail2ban/index.py`)
- [x] 228. 修复 `get_ip_logs()` 内部参数泄漏（`args dump` 明文回显），并改用词边界正则 `(?<![\d.])ip(?![\d.])` 精确匹配 IP

### 阶段三：可靠性根治（P0）

- [x] 229. 重写 `setBlackIp()`：修复遍历 dict 键导致 `fail2ban-client set server banip` 打到不存在 jail 的致命 Bug，改为 `yf-manual` 专用永久封禁 jail（`bantime = -1` + 永不匹配 filter）
- [x] 230. 移除 `get_active_bans()` 中伪造 `bantime = -1` 的假永久封禁逻辑，改为真实 `manual` 标记
- [x] 231. 修复 `[DEFAULT] backend = systemd` 污染 mysql/redis 等 jail 导致静默失效：`backend` 下沉至各 jail，新增 `resolve_backend()` / `pick_logpath()` / `ensure_filter()` 按模式解析真实日志路径

### 阶段四：可靠性加固（P1）

- [x] 232. 修复 `checkEnv()` 误删运行中 socket：仅在服务 `inactive/failed/unknown` 或（非 systemd 系统）PID 已死时清理
- [x] 233. 新增 `wait_service_up()` 指数退避（0.4→2.0s，10s 预算），消除固定 `sleep(0.8)` 在慢机器上的启动假失败；失败诊断仅保留末尾 5 行 / 1200 字符
- [x] 234. 修复 `initDreplace()` 只 `return` 不落盘的 Bug，真正写入 SysV 初始化脚本并 `chmod 0755`
- [x] 235. 重写 `f2bOp()`：支持 systemd / SysV 双通道，darwin / freebsd 明确返回不支持；启动成功后自动 `apply_black_list()` 恢复黑名单
- [x] 236. 重写 `initdStatus()` / `initdInstall()` / `initdUinstall()`，兼容 systemd 与 SysV（`update-rc.d` / `chkconfig`）
- [x] 237. 修复 `get_total_statistics` 返回 `versions` 数组导致首页插件卡片 `onclick` HTML 属性被破坏的 Bug（取 `raw_ver[-1]`）

### 阶段五：性能优化（P2）

- [x] 238. 新增 `open_bans_db()`（`mode=ro` URI 只读 + `PRAGMA busy_timeout=5000`）与 `_DBFILE_CACHE` 路径缓存（300s TTL），消除直连 SQLite 写竞争
- [x] 239. 新增 `read_tail_lines()`（`collections.deque` 环形缓冲）替换 `tail` 子进程，日志读取改为纯 Python 零进程开销
- [x] 240. `get_active_bans()` 下推 SQL 过滤（`WHERE bantime < 0 OR timeofban + bantime > ?`）并在内存合并黑名单，避免全表扫描
- [x] 241. `get_logs_list()` 增加 `MAX_PAGE_SIZE` 上限与 `parse_ban_line()` 结构化解析；`log_candidates()` 支持轮转日志（`.log.1/.2/.3`）

### 阶段六：数据准确性与一致性（P2）

- [x] 242. 修复指标失真：`dbpurgeage` 由 `1d` 迁移为 `30d`（`ensure_db_retention()`），新增 `protect_start.pl` 记录防护起始日，`get_protect_days()` 返回真实防护天数
- [x] 243. 移除 `_delete_db_ban()` 直写数据库逻辑，解封统一走 `fail2ban-client`，彻底消除与 `fail2ban-server` 的写冲突

### 阶段七：多国语言适配（P1）

- [x] 244. 前端 `js/fail2ban.js` 补全 30+ 处未翻译文案（`小时`/`分钟`/`未知`/`次`/`秒`/`暂无日志数据`/`局域网/保留地址`/网站防护深度解析长文案等）
- [x] 245. 修复 `f2bService()` 就绪检测使用中文字面量 `'当前状态'` 导致非中文面板下严格模式开关与用户指引不渲染的问题，改为语言无关的 DOM 选择器判定
- [x] 246. 新增 `f2bMsg()` / `f2bReasonText()` / `f2bJailLabel()` 前端辅助函数；后端 `parse_ban_line()` 返回 `reason_code` / `restore`，修复 ajax 重渲染后封禁原因无法翻译的问题
- [x] 247. 修复解封确认弹窗碎片化翻译导致的拼接错乱，改为单一完整翻译键 `确定要解封 IP ({1}) 吗？`
- [x] 248. 六语言包（zh-CN/zh-TW/en/de/fr/it）重写：清理 11 个死键、补齐 11 个新键，六语种 155 键完全对齐、键集一致
- [x] 249. 修正机翻残留（`次 /`→"Second-rate"、`防爆破`→"Explosionsschutz"/"antidéflagrant"/"a prova di esplosione"、`自启动`→"Seit dem Start"、`参数:(` 跨语言串味）与 zh-TW 简体字泄漏

### 阶段八：安装脚本与工程收尾（P2）

- [x] 250. 加固 `plugins/fail2ban/install.sh`：新增 `die()` / `warn()` 与 `set -o pipefail`，安装后 `verify_install()` 校验 `fail2ban-client`，安装失败不再误报"安装完成"并继续启动
- [x] 251. `install.sh` 补齐 `iptables` / `ipset` / `python3-systemd` 依赖安装（含降级回退），移除 `yum purge` 死代码，新增 `dnf` 分支
- [x] 252. `install.sh` 卸载改为「先备份 `/etc/fail2ban` 到 `${serverPath}/backup/fail2ban/etc_fail2ban_<ts>.tar.gz`，再仅清理包管理器自带文件」，保留用户自定义 `filter.d` / `jail.d` / `fail2ban.local`
- [x] 253. `install.sh` 卸载补齐残留清理（`/var/lib/fail2ban`、`/run/fail2ban`、`/var/log/fail2ban.log*`、`fail2ban-manual.log`）与 `systemd` unit 清理，action 派发改为 `case` 白名单
- [x] 254. 清理插件内 `__pycache__/` 构建残留；经核查确认 `js/*.i18n.bak` 为项目级 i18n 回滚快照（全插件统一、已被 git 跟踪），予以保留
- [x] 255. 编写 fail2ban 插件自动化回归测试套件 (`test/test_fail2ban_plugin.py`)：54 项测试覆盖安全校验、黑名单生效链路、backend 解析、日志解析、i18n 覆盖率、UTF-8(LF) 编码规范、install.sh 加固与 info.json 清单，全部通过
- [x] 256. 更新 `test/test_fail2ban_stability.py`：新增「无 mysql 日志的 Linux 主机降级 systemd 后端」用例，并断言 `[DEFAULT]` 段不得出现 `backend`
- [x] 257. 修复 `sync_jail_local()` 中 `ensure_service_log()` / `ensure_filter()` 位于 `resolve_backend()` 之后的顺序 Bug（占位日志未创建即被判无日志而整段跳过）
- [x] 258. 沉淀可复用工具 `test/i18n_scripts/i18n_plugin_check.py`：通用插件 i18n 一致性检查器（pt() 覆盖、HTML 违规、键集一致性、zh-TW 简体泄漏、脏键、死键），硬性失败 0 项
- [x] 259. 审计报告归档至 `文档/防火墙/防火墙优化6.md`（沿用既有 `防火墙优化N.md` 编号约定），并更正两处初判结论：`js/*.i18n.bak` 系项目级 i18n 回滚快照应予保留、`__pycache__` 会被 `plugin_compress.sh` 打进插件包
- [x] 260. 全量回归：`test_fail2ban_plugin.py`(54) + `test_fail2ban_stability.py`(6) + `test_all_python_syntax.py` + `test_all_plugins_js_syntax.py` + `test_plugin_runtime_i18n.py`(1314 菜单项 100% 覆盖) 全部通过
- [x] 261. 清理临时文件（`test/tmp_f2b/` 及 `plugins/fail2ban/__pycache__/`），确认插件内文本文件 UTF-8 无 BOM + LF，并即时更新 task.md 收尾

## 御风F2B防火墙弹窗非中文界面双滚动条与高度不足修复清单

- [x] 262. 定位根因：`.soft-man-con` 内联 `height:520px`，而 `.bt-w-con` 内容盒仅 `578 - 60(内边距) = 518px`，恒溢出 2px 触发外层滚动条；英/德/法/意文案更长时又撑破 520px 触发内层滚动条 → 非中文界面同时出现内外两条滚动条
- [x] 263. 移除 `.soft-man-con` 内联固定高度，新增 `.bt-w-con > .soft-man-con { height: auto; overflow-x: auto }` 规则：纵向滚动统一由外层 `.bt-w-con` 唯一承担，彻底消除双层滚动条；保留横向滚动以容纳宽表格
- [x] 264. 弹窗高度由硬编码 `620` 改为视口自适应（`Math.max(620, Math.min(860, innerHeight - 90))`）：下限 620 保证不小于原尺寸，上限 860 避免超大屏过度拉伸，四周留出边距
- [x] 265. 新增 5 项弹窗布局回归测试 (`TestPopupLayout`)：内容区无内联高度、`height:auto` 覆盖规则存在、外层为唯一滚动容器、高度自适应且下限 ≥ 620、内联脚本通过 `node --check`
- [x] 266. 用 Chrome headless 实测验证（`test/tmp_f2b_layout/` 对比工装）：旧实现 1100×760 下 `totalScrollbars: 2`（内层 547>520、外层 520>518）；新实现同尺寸仅 1 条，1100×1000 下 0 条，与修复目标一致
- [x] 267. 全量回归（`test_fail2ban_plugin.py` 59 项、`test_fail2ban_stability.py` 6 项、`test_all_plugins_js_syntax.py` 5 项）全部通过，`index.html` UTF-8 无 BOM + LF

## 御风F2B防火墙 × 御风OP防火墙 功能重合治理与单向联动开发清单

分析结论见 `文档/防火墙/fail2ban与op_waf功能重合分析与联动方案.md`。总体路线：**不合并插件**，改为「职责边界划分 + 单向联动（op_waf 负责发现，fail2ban 负责持久封禁）+ 单点解封」。

前置约束（贯穿全部阶段，逐条验收）：
- **A. 独立运行**：只安装其中一个插件时，对端缺失不得导致任何报错、阻塞或功能退化
- **B. 性能**：实时防火墙，攻击强度不可预估。请求路径必须零同步阻塞，联动通道异步削峰；两侧性能均不得因联动而退化
- **C. 国际化**：zh-CN / zh-TW / en / de / fr / it 六语言翻译完整、键集一致、译文无 HTML

> 落地验收：联动专项测试 `test/test_f2b_op_waf_link.py` **70 项全部通过**；fail2ban 既有回归 59 + 6 项、op_waf 既有回归 4 套件、全库 Python/JS 语法、插件运行时 i18n 全部通过。量化性能说明见 `文档/防火墙/fail2ban与op_waf功能重合分析与联动方案.md` 第八节。

### 阶段一：P0 职责边界划分（消除 Web 层重复接管）

- [x] 268. fail2ban 新增 op_waf 探测层（`op_waf_installed()` / `op_waf_spool_path()` / `op_waf_link_state()` / `op_waf_spool_exists()` / `op_waf_link_enabled()`）：以「插件目录 + 情报 spool 文件」判定，**不读对方任何配置文件**（弱耦合）；spool 存在性探测加进程内 30s TTL 缓存，缓存命中时 0 次 stat（测试已断言）
- [x] 269. fail2ban `get_anti_info()` 初始化默认值时：检测到 op_waf 已安装 → `site` 默认规则 `act` 置 false（默认不重复接管 Web 层）；**已有配置一律不动**，绝不静默改写用户设置（新增 `_site_default_act()`，测试已覆盖「已有配置不被改写」）
- [x] 270. fail2ban「网站防护」页新增职责边界提示条（仅检测到 op_waf 时显示）与「一键停用重复的网站防护」按钮，把选择权交给用户；后端新增 `disable_site_anti` CLI（只置 `act=false`，不删规则，sshd 不受影响）
- [x] 271. op_waf「全局配置」页补充职责边界说明：Web 层（CC / 扫描 / 注入 / 地区）由本插件负责，内核层全端口封禁交给 F2B，避免用户重复配置（联动开关行 + 帮助信息条目）

### 阶段二：P1 单向联动通道 —— fail2ban 接收侧

- [x] 272. fail2ban 新增 `OP_WAF_JAIL = 'op-waf'` 与专用 filter `filter.d/op-waf.conf`：`failregex` **精确匹配 op_waf 主动写入的情报行**（`^.*op_waf\[ban\]\s+WARNING\s+Ban\s+<HOST>...$`，不含任何 HTTP 状态码），从机制上切断「op_waf 拦截 → fail2ban 二次升级封禁」的意外级联；已用真实样本回归：444/403/500 访问日志行全部不匹配、情报行全部匹配
- [x] 273. `sync_jail_local()` 末尾按需下发 `[op-waf]` jail：`backend = polling` + `pollinterval = 2` + `maxretry = 1` + `bantime` 取本插件配置（`op_waf_link.bantime`，默认 86400）+ 固定 `banaction = %(banaction_allports)s`（联动封禁一律全端口）；**spool 不存在则完全不下发并清掉历史 filter**（对端未安装时零残留）
- [x] 274. 新增 CLI 动作 `sync_op_waf_jail`（供 op_waf 开关切换时调用）与 `op_waf_link_status`（供 UI 展示情报源状态）、`set_op_waf_link`（调整封禁时长）；`sync_op_waf_jail` 幂等：内容不变不重写、**不触发 reload**（测试断言未变化时 `fail2ban-client` 调用次数为 0）
- [x] 275. spool 路径白名单校验（`abspath(spool).startswith(abspath(<serverDir>/op_waf) + sep)`），杜绝路径注入导致 fail2ban 读取任意文件；测试用 `../../evil.log` 逃逸样本验证被拒绝

### 阶段三：P1 单向联动通道 —— op_waf 生产侧

- [x] 276. op_waf `waf/config.json` 新增 `ban_sync` 段（`open` 开关，含说明文案）；Python 侧新增 `get_ban_sync` / `set_ban_sync` 接口，并复用 `autoMakeLuaImportSingle('config', True)` 只重编 `waf_config.lua` 让 Lua 侧平滑拿到新配置
- [x] 277. Lua `waf_common.lua` 新增 `push_ban_sync()`：仅「真实封禁事件」入队（非每请求），IP 形态快速校验（`is_ip_like`）+ 队列上限保护（`BAN_SYNC_MAX = 5000`，超出计数丢弃）；开关关闭时首行即返回（**零开销**，仅 1 次 table 取值）
- [x] 278. 在 3 处真实封禁发生点接入 `push_ban_sync()`：`write_log()` 阈值升级、`add_reputation_penalty()` 信誉归零（100 分）、`waf_cc()` CC 超限（传单 IP 而非 `block_target` 网段 —— `<HOST>` 无法吸收 CIDR，已加注释与测试断言）
- [x] 279. Lua 新增 `flush_ban_sync()`：批量出队（单次最多 `BAN_SYNC_BATCH = 200`）→ 同批按 IP 去重 → append-only 追加写 spool + 4MB 上限截断保护；写失败时按原序 `lpush` 回队列，**绝不丢情报**
- [x] 280. `init_worker.lua` 挂载 `ngx.timer.every(2, waf_flush_ban_sync)`（仅 `ngx.worker.id() == 0`，`pcall` 包裹）：全部文件 IO 落在 light thread，**请求路径零阻塞**；与既有 timer 相互独立，互不拖累
- [x] 281. op_waf 开关打开时校验 fail2ban 已安装（`f2bInstalled()` 同时校验 server 目录与插件入口）并回调其 `sync_op_waf_jail`；未安装则**拒绝开启并明确提示**（优雅降级）；开关关闭时同步删除 spool 撤销对端 jail；spool 创建失败自动回滚开关，保持两侧状态一致

### 阶段四：P1 单点解封与状态互认

- [x] 282. op_waf `removeDropIp()`：联动开启时同步调用 `unban_op_waf_ip` 解除 fail2ban `[op-waf]` jail 的封禁；带 `silent` 参数防止与 283 形成双向递归（测试断言 silent 模式下不产生任何对端调用）
- [x] 283. fail2ban `unban_active_ip()`：对 `op-waf` jail 解封时同步调用 op_waf 的 `remove_waf_drop_ip?silent=1`；带 `silent` 参数防止递归；对端未联动时静默成功，绝不让调用方报错
- [x] 284. 两侧 UI 解封确认弹窗明确提示「将同时解除内核层 / 应用层封禁」，根治「在 op_waf 解封了却仍访问不了」的困惑

### 阶段五：性能加固

- [x] 285. Lua 侧：联动队列 `waf_ban_sync` 与日志队列**分离**（日志队列降级丢弃时不拖累封禁情报）；队列上限 5000 + `ban_sync_drop` 计数抑制爆发期膨胀；同批出队时按 IP 去重，减少 fail2ban 侧无谓解析
- [x] 286. Python 侧：`sync_op_waf_jail` 幂等（内容不变不重写、不 reload）；spool 探测 TTL 缓存；联动未开启时不产生任何额外子进程调用；`op_waf_link_status` 在配置就绪时为纯只读（三条均已由测试断言）
- [x] 287. 性能验证：量化说明见 `文档/防火墙/fail2ban与op_waf功能重合分析与联动方案.md` 第八节（8.3 请求路径开销表 + 8.4 验收结果）；可断言部分已固化为 `TestPerformanceInvariants`（缓存命中 0 次 stat、未变化 0 次 reload、未联动 0 次跨插件子进程、状态查询 0 次写盘），确认攻击路径上不存在同步阻塞

### 阶段六：国际化补全与回归收尾

- [x] 288. op_waf 修复 6 处译文含 HTML（`后续如需解除封禁，请前往面板的 <b>` 等碎片）—— 违反 `web/core/i18n.py` 硬约束；改为单一完整键 `后续如需解除封禁，请前往面板的「{1}」进行手动删除解封。` + `{1}` 位置插值
- [x] 289. op_waf 清理 7 个脏键（`)没有!`、`参数:(`、`后续如需解除封禁，请前往面板的`、`进行手动删除解封。`，以及 `\\uFEFF...` 与真实 BOM 两种形式的导出表头）
- [x] 290. op_waf + fail2ban zh-TW 简体残留转换（opencc s2twp，仅处理「值 == 简体原文」的条目，已有译文不动）：共转换 11 条；复检剩余 0 条可转换项（余下同形字属正常）
- [x] 291. 修正 op_waf 归属地查询硬编码 `lang=zh-CN`，改为跟随面板语言（新增 `IP_API_LANG_MAP` + `normalize_ip_api_lang()`，对齐 fail2ban 实现；`getIpLocationBatch` / `getIpLocation` 均已支持 `lang` 参数）
- [x] 292. 两侧本次新增文案六语言补齐：fail2ban 155→172 键、op_waf 709→720 键；键集与 zh-CN 基线**完全一致**，0 缺失 / 0 多余 / 0 空值 / 0 译文含 HTML / 0 死键脏键
- [x] 293. op_waf 弹窗高度改为视口自适应（`Math.max(620, Math.min(860, vh - 90))`，对齐 fail2ban 的双滚动条修复方案），并补 `.bt-w-con > .soft-man-con { height: auto; overflow-x: auto; }`，消除非中文界面高度不足
- [x] 294. 新增联动专项测试 `test/test_f2b_op_waf_link.py`（**70 项**）：跨插件契约对齐（常量/绝对路径/Lua 行格式↔failregex）、对端缺失时不报错（含 silent 解封、状态查询）、spool 路径白名单、jail 生成与撤销、幂等性与真实变更检测、Lua 语法（luaparser AST，缺失时退化为去噪后配平校验）与性能结构、六语言键集与 HTML 红线、前端 `pt()` 文案覆盖率、性能不变量
- [x] 295. 全量回归：`test_fail2ban_plugin.py` 59 项、`test_fail2ban_stability.py` 6 项、`test_all_python_syntax.py` 2 项、`test_all_plugins_js_syntax.py` 5 项、`test_plugin_runtime_i18n.py` 3 项（1314 条菜单项 100% 覆盖）、op_waf 既有 4 套件（P0 安全 / P1 可靠性性能 / P2 优化 / spider）**全部通过**；编码规范核查通过（全部改动文件 UTF-8 无 BOM + LF，语言包缩进保持原状 fail2ban=4 / op_waf=1）；临时脚本统一归档在 `test/i18n_scripts/`，工作区无残留垃圾文件


### 明确不做（附理由，避免后续反复讨论）

- **不合并为一个插件**：Python+iptables 守护进程 ↔ OpenResty Lua，技术栈/依赖/故障域/生命周期均不可合并；且与说明书既有的「网络层-内核层-应用层」纵深防御定位直接冲突
- **不让 op_waf 直接操作 iptables**：会绕过 fail2ban 的封禁数据库，状态更割裂；统一由 fail2ban 作为唯一封禁执行者
- **不让 fail2ban 依赖 OpenResty**：会让「只想防 SSH 爆破」的用户被迫安装整套 OpenResty
- **两侧黑名单不盲目自动同步**：语义不对等（op_waf 封禁地址 = 仅 Web 层，fail2ban 黑名单 = 全端口），自动同步会把「只挡网站」放大成「断其所有服务」

---

## 御风F2B防火墙「网站防护已托管」提示与后端动态消息国际化清单

需求来源：用户反馈「已经点击了一键停用之后，提示内容就应该改成『网站防护已自动托管至御风OP防火墙』，或者用更加严谨的文字进行表述，需要适配多语言」。

前置约束同上：**A. 独立运行**（未装 op_waf 时提示条不出现，行为与改动前一致）、**B. 性能**（纯前端渲染，无新增请求/子进程）、**C. 国际化**（六语言键集一致、译文无 HTML、无脏键死键）。

- [x] 296. 职责边界提示改为**三态**：`已装 op_waf 且仍在重复接管` → 黄色警告条 +「一键停用」按钮（保持原样）；`已装 op_waf 且不再接管` → **绿色「已托管」提示条**（本次新增，取代原先只是撤掉警告、留一行小字的做法）；`未装 op_waf` → 完全不展示。文案比用户原话更严谨：明确「Web 层由 OP 防火墙在应用层拦截、本插件不再重复接管、避免双重封禁与解封后仍无法访问」，并给出回退入口「如需恢复，可在上方表格中重新启用」
- [x] 297. 绿色提示条追加**第三段动态说明**（攻击 IP 的归宿）：情报联动已开启 → 「仍会在本插件内核层以 iptables 全端口持久封禁，Nginx 重启也不失效」；未开启 → 提示到下方开启「御风OP防火墙情报联动」。解决用户看到「已托管」后必然产生的疑问「那攻击者谁挡？」
- [x] 298. fail2ban「一键停用」后端成功提示由 `已停用重复的网站防护` 改为 `网站防护已托管至御风OP防火墙`，与提示条标题共用同一语言键（toast 与页面文案一致）
- [x] 299. **修复 op_waf `wafMsg()` 的自递归缺陷（P0）**：兜底分支误写为 `return wafMsg(msg)`，未命中模式时无限递归 → `RangeError: Maximum call stack size exceeded`，导致 op_waf 全部走 `wafMsg()` 的提示（约 36 处）在运行时都不显示。已改为 `return pt(msg)`，并加回归测试锁死该写法
- [x] 300. 建立「后端动态消息」国际化机制并补齐缺口：后端为保留调试信息返回「可翻译前缀 + 动态参数」（如 `删除失败: <异常>`、`同步成功，当前共 12 条…!`），新增 `F2B_MSG_PATTERNS` / `WAF_MSG_PATTERNS` 模式表把参数拆出来，再用带 `{1}` 的完整键查表；共补 15 个键（fail2ban 12 个含 6 个后端消息、op_waf 3 个），并修正 `IP格式错误` 裸消息被误匹配成空参数的渲染问题
- [x] 301. 新增**真实渲染验证**：`test/tools/render_f2b_site_anti.js` 用最小 jQuery / layer / api / pt 替身在 Node 里真正执行 `f2bSiteAnti()`，Python 侧断言 4 种状态 × 6 语言的配色、标题、联动分支差异、以及非中文语言下提示条区域**零中文残留**
- [x] 302. 全量回归：`test_f2b_op_waf_link.py` **85 项**（新增 5 项渲染 + 4 项后端消息/i18n 守卫）、`test_fail2ban_plugin.py` 59 项、`test_fail2ban_stability.py` 6 项、全库 Python/JS 语法、插件运行时 i18n、op_waf 4 套件**全部通过**；六语言键集一致（fail2ban 183 / op_waf 723）；编码核查通过（UTF-8 无 BOM + LF，语言包缩进保持原状）
- [x] 303. 按用户截图的**精确状态**（已装 op_waf + 两条规则均「已停用」+ 情报联动未接入）做端到端渲染复现：确认真实执行 `f2bSiteAnti()` 后输出绿色「已托管」条、黄色警告条不再出现，六语言逐一核对无误。新增 `test/tools/build_f2b_banner_preview.py` 一键生成前后对比预览页（提示条 HTML 直接取自渲染工装，非手工绘制），产物在 `test/tmp_banner_preview/preview_delegated.{html,png}`（`test/` 已 gitignore）

---

## 御风F2B防火墙 × 御风OP防火墙「联动开关可用性」与「弹窗高度适配」清单

需求来源：用户二次反馈两个问题 ——
1. 提示条让用户「在下方开启『御风OP防火墙情报联动』」，但下方面板只有「封禁时长 + 保存」，状态显示「未接入」，**没有任何可点击的开启入口**；
2. op_waf 弹窗高度不适配，**下方留出大片空白**，整体不协调，希望两个防火墙插件都更专业、美观。

前置约束同上：**A. 独立运行**（未装对端时不得报错、不得产生副作用）、**B. 性能**（新增逻辑不得进入请求热路径）、**C. 国际化**（六语言键集一致、译文无 HTML）、**D. 逐步记录**。

- [x] 304. **定位并修复根因（P0）**：op_waf 自己的联动开关挂在 `<label for=... onclick="setBanSync()">` 上。浏览器对 label 的处理顺序是「先派发 label 自身的 click（处理器同步执行）→ 再执行默认动作把点击转发给 checkbox 去翻转」，因此在 label onclick 里读 `$('#close_ban_sync').is(':checked')` 拿到的**永远是翻转前的旧值**，提交的也永远是旧状态 —— 开关视觉上拨动了、状态却怎么点都不变，重渲染后又弹回。用真实浏览器 + 真实 jQuery 复现并固化为证据（`label-onclick=false` / `input-onchange=true`）。同一缺陷还波及 `setWafAreaLimitSwitch()`（地区限制开关），一并修复。全库 28 处开关中其余 26 处走「后端翻转」语义（前端不读状态），不受影响
- [x] 305. 在 fail2ban「御风OP防火墙情报联动」面板新增**「联动开关」行**（`btswitch` 开关 + 已开启/已关闭标注 + 一行效果说明），使用户在原提示条指引的位置真正能开启联动。开关挂在 `input` 的 `onchange` 上（不是 label onclick），并在取消 / 失败时自动把开关拨回，杜绝「视觉已切换、实际未生效」
- [x] 306. 新增 fail2ban 后端 `set_op_waf_link_open()`：本插件**不自行造状态**，而是通过面板既有的跨插件约定（`python3 <panelDir>/plugins/op_waf/index.py set_ban_sync <json>`）把用户意图转发给 op_waf，再回读 spool 确认 —— 从机制上杜绝「本插件显示已开启、对端其实没在写」的两侧状态分叉。成功后强制刷新 spool 探测缓存（否则 30s TTL 内会按旧状态下发错误的 jail）再 `sync_op_waf_jail()`
- [x] 307. **约束 A 落地**：对端未安装或处于「只有 server 目录、没有插件入口」的半残状态时明确拒绝且**不发起任何子进程调用**（用目录树快照断言零文件增删）；对端返回非 JSON / 空响应时优雅降级
- [x] 308. **i18n 洁净性**：对端失败原因（中文原文）**只写面板日志**，返回给前端的始终是本插件自己的可翻译键（`未检测到御风OP防火墙` / `情报联动设置失败，请检查御风OP防火墙运行状态` / `情报联动已开启` / `情报联动已关闭`），避免非中文面板漏出中文。新增 11 键 × 6 语言（fail2ban 183 → 194），同步器 `test/i18n_scripts/sync_op_waf_link_switch_i18n.py`
- [x] 309. **修复 op_waf 弹窗底部死区**：根因是 `plugins/op_waf/index.html` 的 `.bt-w-main` 写死 `height:578px !important`。`resetPluginWinHeight()` 是用 jQuery 写**行内**高度的，而行内样式优先级低于 `!important`，于是弹窗高度在 620~860 之间变化时 `.bt-w-main` 恒定停在 578px，下方留出一条死区（表现为弹窗底部大片空白、左右两栏提前结束）。改为 `height:100%`，与 fail2ban 侧早已采用的写法对齐
- [x] 310. 为**两个插件**都加上「弹窗高度按当前页内容自适应」：用 `MutationObserver` 监听内容区（无需改动每一个 render 函数），防抖 80ms 等渲染稳定后测量，把弹窗收敛到刚好容纳内容并夹在 `[560, 视口高-90]`；与当前高度差小于 16px 则不动，避免高度震荡。效果：短页面（如 op_waf「服务」）窗口紧凑，长页面（全局配置 / 封锁历史 / 网站防护）自动变高
- [x] 311. 新增回归守卫（`test_f2b_op_waf_link.py` 85 → **106 项**）：`TestOpWafLinkSwitch`（跨插件调用契约、参数形态、成功/失败消息、缓存刷新时序、前端 onchange 契约、取消回滚）、`TestSwitchDomContract`（**通用守卫**：任何读取 checkbox 状态的处理函数都不得挂在 `<label onclick>` 上，并现场用真实浏览器固化事件顺序依据）、`TestPopupHeightAdaptation`（`.bt-w-main` 不得写死像素、fit 常量必须与 `soft.js` 的 42 与 `.bt-w-con` 的实际内边距一致）、`TestLinkSwitchI18n`（六语言覆盖 + 非中文不得照抄中文）
- [x] 312. 全量回归通过：`test_f2b_op_waf_link` **106** / `test_fail2ban_plugin` 59 / `test_fail2ban_stability` 6 / `test_all_python_syntax` 2 / `test_all_plugins_js_syntax` 5 / `test_plugin_runtime_i18n`（1314 菜单项 100% 覆盖）/ op_waf P0·P1·P2·spider 4 套件；六语言键集一致（fail2ban 194 / op_waf 723，0 空值 0 HTML）；编码核查通过（UTF-8 无 BOM + LF，缩进 fail2ban=4 / op_waf=1 保持原状）；`i18n_plugin_check.py` 硬性失败项 0
- [x] 313. 新增 `test/tools/build_f2b_link_panel_preview.py`：把渲染工装扩展为可指定 JS 路径，从而能从 `git show HEAD:plugins/fail2ban/js/fail2ban.js` 渲染出**真实的「修改前」面板**（而非手工拼装假 HTML）做前后对比；产物在 `test/tmp_banner_preview/preview_link_panel.{html,png}`

---

## 御风F2B防火墙 × 御风OP防火墙「跨插件调用静默失败」修复清单

需求来源：用户开启上一步新增的「联动开关」时报错 ——

```
联动开关失败：{"data": "{\"status\": false, \"msg\": \"情报联动设置失败，请检查御风OP防火墙运行状态\"}", "msg": "OK", "status": true}
```

报错信封里是 **fail2ban 自己的兜底文案**（说明 fail2ban 已发出请求、被对端拒绝），指向跨插件调用本身。

前置约束同上：**A. 独立运行**、**B. 性能**、**C. 国际化**、**D. 逐步记录**。

- [x] 314. **定位根因（P0）**：跨插件调用被写成 `yf.execShell('python3 ' + entry + ' set_ban_sync ' + json.dumps({'open':'1'}))`。这是**拼 shell 字符串**，有三个叠加缺陷，且**每一个都只会静默失败、不抛异常**：(1) 面板跑插件统一用 `sys.executable`（可能来自 venv，PATH 里未必有 `python3`）；(2) shell 按空格分词，把 `{"open": "1"}` 拆成 `{open:` 和 `1}` 两段，对端 `getArgs()` 组装不出字典、只能走兜底分支拿到空值，于是报「缺少必要参数」；(3) 缺 `cwd`，插件 import 期若有相对路径依赖会错位。已用真实 `sh -c` 复现分词结果：`['python3', '/tmp/plugins/op_waf/index.py', 'set_ban_sync', '{open:', '1}']`
- [x] 315. 对齐面板权威调用方式：阅读 `web/utils/plugin.py` 的 `plugin.run()` 与 `yf.safeExecShell()`，确认面板自身用的是 `[sys.executable, path, func, ...]` **参数列表** + `cwd=yf.getPanelDir()`（`subprocess.Popen(shell=False)`，天然免疫分词与注入）。跨插件调用改为同一形态：`yf.safeExecShell([sys.executable or 'python3', entry, func, json.dumps(args)], cwd=yf.getPanelDir(), timeout=...)`
- [x] 316. 在 fail2ban 侧新增可复用的 `call_plugin_cli(plugin_name, func, args, timeout)`（统一处理入口不存在 / 空响应 / 非 JSON / 超时，全部降级为 `(False, 原因)` 而不抛异常），`call_op_waf_ban_sync()` 改为调用它；docstring 明确写出「不要拼 shell 字符串」及其三个坑
- [x] 317. 在 op_waf 侧新增对称的 `callF2bCli(func, args, timeout)`，并修复**另外两处同样的缺陷调用**：`callFail2banSync()`（同步 jail）与 `removeDropIp()` 单点解封分支的 `unban_op_waf_ip`。即本次共修 3 处跨插件调用
- [x] 318. **约束 A 落地**：入口文件不存在时直接返回 `(False, 'not_installed')`，**不发起任何子进程**；对端未安装 / 半残状态下开关操作明确失败且无副作用
- [x] 319. 新增 `TestCrossPluginInvocation` 回归守卫（`test_f2b_op_waf_link.py` 106 → **112 项**）：(1) 用正则 + `_code_only()`（先剥掉 docstring 与 `#` 注释，避免守卫匹配到自己的说明文字）全库禁止 `'python3 ' +` 形式的跨插件 shell 拼接；(2) 断言两侧都使用 `yf.safeExecShell(cmd, cwd=yf.getPanelDir())`；(3) 断言命令首元素为 `sys.executable or 'python3'`；(4) `test_shell_would_have_split_the_json` 用真实 shell 证明旧写法确实会拆坏 JSON；(5) `test_end_to_end_real_subprocess_delivers_json` **真起一个子进程 stub 插件**，再用对端真实的 `getArgs()` 解析，端到端证明参数完整送达；(6) 断言 op_waf 侧两处调用也已修复
- [x] 320. 同步修正因调用方式变更而失效的既有测试：`LinkTestCase.stub_safe_exec()` 抽为共享工装，把断言从「shell 字符串内容」改为「**参数列表**」（`cmd[0] == sys.executable or 'python3'`、`cmd[1].endswith('plugins/fail2ban/index.py')`、`cmd[2] == 'sync_op_waf_jail'`、`json.loads(cmd[3]) == {...}`）；`test_unlinked_unban_spawns_no_subprocess` 同时 stub `execShell` 与 `safeExecShell`
- [x] 321. 更新因「弹窗高度适配」而**语义过时**的测试 `test_op_waf_ui.py::test_sidebar_style_and_fixed_height`（原断言写死 `resetPluginWinHeight(620);`，与本次需求直接冲突）。拆为两项：保留侧边栏样式断言，新增 `test_popup_height_is_adaptive_not_pixel_locked` 固化**新契约** —— 初始高度为视口自适应公式、内容二次收敛（`MutationObserver` + 防抖 + 阈值）、且 `.bt-w-main` **禁止**像素锁死（用 `assertNotRegex` 断言 `height: <数字>px` 不出现）
- [x] 322. 全量回归通过：`test_f2b_op_waf_link` **112** / `test_fail2ban_plugin` 59 / `test_fail2ban_stability` 6 / `test_all_python_syntax` 2 / `test_all_plugins_js_syntax` 5 / `test_op_waf_ui` 5（合计 **189 项 OK**）+ op_waf P0·P1·P2·spider 4 套件全部通过；`i18n_plugin_check.py` 两插件硬性失败项均为 **0**
- [x] 323. 新增**可复现的修复证据报告** `test/tools/build_cross_plugin_fix_report.py` → `test/tmp_link_fix_report/fix_report.html`（含 PNG 截图）。报告里每条证据都**现场跑出来**而非手写：shell 分词证据真调 `shlex.split()`、调用点证据真扫源码（剥 docstring/注释后再匹配）、测试计数真跑 unittest —— 这样报告过期时会自己变红，而不是继续骗人。并**按性质分类**顺带排查结果，避免误报：A 类「跨进程调用且参数含 JSON」5 处（`mariadb:3584`、`mysql:1397`、`mysql:1881`、`plugin.py:1240-1241`，与本次同源，建议后续单独修复）；B 类 `crontab.py:740-750` 7 处**不算缺陷**（cron 本来就交给 shell 执行、必须是字符串，且参数是文件名/数字不含 JSON）

## 本地工作区全量换行符规范化（CRLF -> LF）与 Git 状态对齐

- [x] 324. 编写本地工作区 CRLF 扫描与安全转换工具 (`test/convert_crlf_to_lf.py`)
- [x] 325. 批量执行转换，将工作区中所有非标准换行符（CRLF / mixed）文件转为纯 LF
- [x] 326. 更新 Git 索引缓存（`git add`），确保 `git status` 洁净（working tree clean）
- [x] 327. 全量验证 `git ls-files --eol`，确保所有文件 `w/lf` 且无遗留 CRLF，清理 `test/` 临时脚本并完成打勾

## 换行符归一复核：推翻原判断 + 修正校验用例口径

> 起因：进度文档里遗留的待办写着「剩余 90 个 CRLF 文件，`git cat-file` 证实 HEAD 里就是 CRLF，
> 建议单独一次提交」。复核后确认**该前提是错的**，第 324~327 项其实已经把问题解决完了。

- [x] 328. 复核确认**仓库内容本来就是 LF**：3560 个受跟踪文件 `git ls-files --eol` 全为 `i/lf` + `w/lf`，`w/crlf` / `i/crlf` / `w/mixed` 均为 **0**；`git cat-file blob <sha>` 原始字节 CR 计数 **0** → **不需要任何「换行符归一」提交**（第 326 项的 `git add` 后 `git status` 对这些文件零差异，恰好反证索引本就是 LF）
- [x] 329. 定位并记录原判断的**测量方法缺陷**（两个都是假信号）：① `git cat-file -p HEAD:<path>` 会套用 smudge 过滤器（系统级 `core.autocrlf=true`，来自 PortableGit 的 `etc/gitconfig`），把索引里本是 LF 的内容显示成 CRLF；`-p <blob-sha>` 同样过滤，**只有 `git cat-file blob <sha>` 是原始字节**。② Git Bash 下 `grep -c $'\r'` 恒等于**文件行数**（127 行的 `install.sh` 返回 128）→ 可靠写法 `grep -cP '\r'` 或 `tr -cd '\r' | wc -c`
- [x] 330. 更正三处错误记录：`plugins/plugins_check.md` §5.3、`plugins/i18n_遗留问题升级方案.md` §10.2 / §10.4 / §10.5、`.workbuddy-ai/memory/MEMORY.md`
- [x] 331. 重写 `test/test_crlf_and_sh_syntax.py::test_01`：改为只校验**受版本控制的 blob**（`git ls-files -s -z` 取 sha 并按 blob 去重 → `git cat-file --batch` 读原始内容），不再把 `.gitignore` 忽略的 `test/`(13)、`参考/`(7) 本地草稿算作「仓库文件」—— 那才是它长期转不绿的真正原因
- [x] 332. 补两道防「假门禁」护栏：① **扫描面下限**（匹配文件数 < 1000 即判失败，实测受跟踪文本文件 2870 个）；② **检测器自证** `test_01b`：在临时仓库里把 CRLF 真正 `git commit`（须先 `git config core.autocrlf false`，否则 add 阶段就被转换掉），断言检测器必须报出来
- [x] 333. 新增变异自证 harness `test/crlf_detector_selftest.py`：把 `_repo_text_blobs` 变异为「只返回路径、内容为空」→ `test_01` 仍 PASS（它本就检测不到），`test_01b` **FAIL** ✓ —— 证明新护栏有牙，不是永远全绿的假门禁
- [x] 334. 全量验证无回归：`test_crlf_and_sh_syntax` **5/5 OK**；`scripts/verify_i18n.py` **9/9 PASS**；所有改动文件均为 LF 无 BOM



## 提交门禁 `testsuite/` 补全与提效

> 用户要求：`testsuite/` 存放标准测试用例，**只有完全通过才可提交**；
> 从 `test/` 筛出有效代码迁入，不够全面则补全；并在 `testsuite/testsuite.md` 写清用法与注意事项。

- [x] 335. 盘点 `test/`：AST 分类 125 个 TestCase 模块 / 833 个方法，逐个隔离运行（`test/tmp_run_all_probe.py`）得到 **104 绿 / 40 红**
- [x] 336. 迁移 104 个绿色用例到 `testsuite/`，并把 40 个红色用例**一并复制**进来 —— 否则 `quarantine.txt` 的反向检查（「隔离项必须仍为红」）是死代码
- [x] 337. 生成 `testsuite/quarantine.txt`（39 条，格式 `模块名  # 原因`，原因取真实异常首行）
- [x] 338. 落地门禁入口 `testsuite/run_all.py`：每模块独立子进程 + 超时、**必须校验 `Ran N tests` 的 N>0**（防「永远全绿」假门禁）、隔离区反向检查、静态门禁分离
- [x] 339. 落地 `testsuite/install_hooks.py`：装成 `pre-commit`（拒绝覆盖外来钩子，`--force` 才覆盖；`git commit --no-verify` / `YUFENG_SKIP_TESTS=1` 可绕过）
- [x] 340. 新增 `testsuite/test_repo_contract.py`（14 项，纯静态毫秒级）：插件数契约 36、必需文件、6 语言包、`info.json` schema、`plugin_version.pl` 格式、`.gitattributes`、无垃圾文件、**不得引用被忽略的 `test/`**、命名必须 `test_*.py`、隔离条目必须存在且有原因、`testsuite/` 根目录不得出现生成物、`.scratch` 必须被 gitignore
- [x] 341. 新增 `testsuite/test_shell_syntax.py`：批量 `bash -n` 全仓 353 个 `.sh`（16 路分块 + 循环内**不做命令替换**，53s → 5.5s）—— **当场抓出 42 个 `plugins/*/versions/**/install.sh` 被追加 ` ------`（commit `4d4051205`）导致 bash 无法解析**，已修复
- [x] 342. 修复 146 个用例模块里指向被忽略 `test/` 的路径引用（`os.path.join` 与裸字符串两种形态），迁移 6 个夹具文件进 `testsuite/`
- [x] 343. 修 17 个「`-m unittest` 收集不到用例」的模块：识别为**脚本式用例**（模块级 `def test_*()` / `run_tests()` + `__main__` + 裸 `assert`），门禁自动改跑 `python testsuite/xxx.py` 并以退出码判定；判定条件同时要求「有 `__main__` **且**全文有 `assert`」（否则当脚本跑等于没验证，仍是假绿）
- [x] 344. 排查 156 项「引用了不存在的文件」告警 → 精确复核后确认**真实缺失夹具 0 个**（全是运行时生成物、临时目录内文件名、或故意的负例名如 `non_existent.log`）；另扫「条件式断言」（`if os.path.exists(): assert`）假绿风险，命中 **0 处**
- [x] 345. 修 **SQLite 并行争用**：`test_auto_detect_and_i18n` / `test_data_query_remotedb` / `test_mysql_conn_and_pg_driver_prompt` / `test_sync_and_speed` 都会经 `common_db.saveConnection()` 写同一份真实面板 SQLite，并行跑必然 `database is locked`（2 模块假红）并静默污染断言（`'conn_26' != 'pgsql'`）。修法：`common_db.getSqliteFile` 重定向到本进程专属 `tempfile.mkdtemp()`
- [x] 346. 修 **沙箱批量删除守卫误伤 `tearDown`**：单次工具调用内删除超阈值（默认 50）即抛 `SystemExit(1)`，一次跑上百模块必然触发（9 模块假红 + 残留目录级联污染断言，如 `test_p1` 的 `24 != 23`）。修法：`run_all.py:child_env()` 给每个子进程唯一 `CODEBUDDY_TOOL_CALL_ID` + 抬高阈值。**反例**：`CODEBUDDY_SAFE_DELETE_ENABLED=0` 会被宿主直接 `SIGTERM`，不可用
- [x] 347. 修 **临时产物落点**：全部改用 `tempfile.mkdtemp()`（系统临时区）。实测仓库所在 `F:` 盘**单次删除固定 5.15s**（与文件数无关），`%TEMP%` 仅 0.01s —— **差 500 倍**，门禁里累计二十几次删除即浪费一两分钟
- [x] 348. 删除被误提交的运行时生成物 `testsuite/run_node_runtime_test.js`（`c987f0df4`），并加守卫防复发
- [x] 349. 重写 `testsuite/testsuite.md`（330+ 行，8 节）：快速开始 / 目录结构 / 四条硬约束 / 隔离区约定 / 注意事项 5.1–5.9 / 运行环境 / 失败排查 / 新增用例
- [x] 350. **模拟干净克隆验证**：把 `test/` 改名隐藏后跑完整门禁 → **`gate_rc=0`，全部门禁通过**（108 个用例参与、38 个隔离、702 个 test 方法、耗时 180.6s）
- [x] 351. 揪出并修掉门禁**最大的时间黑洞**：`F:` 盘上 sqlite3 不只是 `connect` 慢（30s），**`close()` 单次也要 30~60s**；`web/core/db.py:56` 在导入期就注册了 `atexit` → `_close_all_connections()`，逐个关连接。`test_pg_driver_and_mysql_dbs` 分阶段打点实测 `IMPORT=0.05 / TESTS=0.61 / PRE_EXIT=0.67 / ATEXIT_ELAPSED=296.90` —— **99.8% 的时间花在解释器退出**。逐连接计时：面板库 30.60s、`<serverDir>/mysql.db` 60.01s、`mariadb/*.db` 各 60s，6 个连接 ≈ 270s
- [x] 352. 新增共享助手 `testsuite/_isolation.py` 的 `isolate(prefix)`：一次性把面板 SQLite 落点 + `<serverDir>` 挪到 `tempfile.mkdtemp()`，并造一份假 `mysql/mysql.db`（`config(mysql_root)`）当自动探测的确定输入；预建 `data/`、`mysql/`、`mariadb/` 避免 sqlite 抛 `unable to open database file` 脏 stderr
- [x] 353. 确定**正确接缝是 `core.db.getPanelDir`，不是 `yf.getPanelDir`**：后者被 `yf.getPluginDir()` 依赖，插件靠它定位自己的文件（`plugins/op_waf/index.py:74` `sys.path.append(getPluginDir()+"/class")` → `from luamaker import luamaker`）。改 `yf.getPanelDir()` 实测报 `ModuleNotFoundError: No module named 'luamaker'`。面板 SQLite 落点只在 `web/core/db.py:82/:150`，改那个函数最精准
- [x] 354. 确定**补丁必须早于「会打开面板库的模块」被导入**：实测 `import utils.plugin` 在**导入期**就打开 `<panelDir>/data/panel.db`（导入前 `core.db._local.connections` 为空，导入后立刻多一条真实路径）
- [x] 355. 用 `isolate()` 改造 6 个模块，实测收益：`test_data_query_fix` 53.3s→**1s**、`test_pg_driver_and_mysql_dbs` 184~296s→**1s**、`test_concurrent_callbacks` 55.1s→**1s**、`test_f2b_op_waf_link` 108.7s→**38s**、`test_site_create_default_page` 85.8s→**1s**（隔离中，失败原因不变）、`test_external_status_sync` 47.2s→**2s**（隔离中，失败原因不变）
- [x] 356. `run_all.py` 内置**开销识别**：解析输出里的 `Ran N tests in X.XXXs`（用例本体耗时）与进程总耗时对比，差值 ≥ `OVERHEAD_WARN_SECONDS`（20s）即在该行打 `⚑` 并在汇总单列一节「本体很快、进程很慢」+ 修法指引；解析不到本体耗时的脚本式用例自动跳过，不误报。实测当轮抓出 5 个模块
- [x] 357. `test_repo_contract.py` 白名单登记 `_isolation.py`；`testsuite.md` §5.7 补「close() 30~60s + atexit」实测数据、§5.9 改为围绕 `isolate()` 重写并说明「为什么改 `core.db.getPanelDir` 而不是 `yf.getPanelDir`」；`SKILL.md` 同步补第三层坑与三条硬知识
- [x] 358. **门禁整体提速**：总耗时 295.7s → **180.6s**（模块耗时之和 1004.9s → 约 740s），全程 `gate_rc=0`
- [x] 359. 新增诊断立刻抓出**第二批** 6 个同类模块并逐个修掉（同用 `isolate()`）：`test_mysql_conn_and_pg_driver_prompt` 77.2s→**3s**、`test_p0_deep_security` 56.3s→**1s**、`test_p1_deep_reliability_perf` 61.9s→**7s**、`test_plugin_callback_fix` 42.4s→**1s**、`test_soft_i18n`（隔离中）75.3s→**1s**、`test_files_i18n_layout`（隔离中）31.7s→**2s**
- [x] 360. 复核两个隔离模块**失败原因与隔离区记录逐字一致**（`test_soft_i18n`: `'執行環境' != '運行環境'`；`test_files_i18n_layout`: `'right: 87px;' not found in ...`），未发生「意外转绿」
- [x] 361. 顺带修 `test_files_i18n_layout.py` 缺模块级 `import sys`（原来只在测试函数里 import，模块级用它加 `sys.path` 会 `NameError`）
- [x] 362. 清理 `MEMORY.md`（16.7KB → **7.1KB**）：按主题合并去重，把详细手册指向仓库内 `testsuite/testsuite.md` 与 `yufeng-plugin-dev` 技能，只保留「跨任务必须记住、且不写在仓库里」的约定
- [x] 363. 第三批（诊断再次点名）7 个模块：`test_plugin_performance` 112.9s→**2s**、`test_recent_logins` 49.5s→**2s**、`test_home_notice_cache` 37.8s→**2s**、`test_plugin_service_ops_and_modal`（隔离中）51.9s→**2s**；**主动回退 3 个不该隔离的**：`test_p2_deep_refine`、`test_recommend_install_bug`（路径契约用例，重定向后必然失败）、`test_mysql_manage_open_phpmyadmin`（起子进程，隔离后子进程吃满 `F:` 盘 30s 超时、挤掉原记录的失败原因）
- [x] 364. 把这两条「不能隔离」的教训写进 `testsuite.md` §5.9 与 `SKILL.md` 速查表：**只给 `⚑` 点名的模块做隔离，不要凭「它 import 了 utils.plugin」就批量加**
- [x] 365. **门禁最终态：`python testsuite/run_all.py` → `gate_rc=0`，108 个用例参与 / 38 个隔离 / 702 个 test 方法 / 总耗时 75.0s，`⚑` 点名 0 个**（起点 295.7s，**快 3.9 倍**）
- [x] 366. 新增 `testsuite/test_gate_selftest.py`（19 项，约 1.2s）：**给门禁自己的护栏写测试**。覆盖 `script_style_tests()` 五种输入形态、`RAN_RE` 对 `Ran 0 tests ... OK` 的识别（假门禁防护）、`body_seconds()`/`overhead()` 解析与「解析不到就不告警」、`discover_modules()` 只收 `test_*.py` 且不会把 `_isolation.py` 当用例，以及**端到端**验证「收集不到用例的模块必须判红」
- [x] 367. 对自证做**变异自证**：① 删掉 `script_style_tests()` 的 `assert` 判定 → 自证变红；② 把「未收集到任何用例」分支改成放行 → 自证变红（`收集不到用例的模块必须判红，否则门禁是假绿`）。两次变异后均已恢复，`git diff testsuite/run_all.py` 为空
- [x] 368. 干净克隆复核：隐藏 `test/` 后 8 个代表模块行为一致、`test_repo_contract` 14/14 通过 ⇒ 新增的 `testsuite/_isolation.py` 在无 `test/` 的克隆上可用；`⚑` 盲区（脚本式用例）已核实无害（16 个脚本式用例最慢 14.8s）
- [x] 369. 最终态复核：`gate_rc=0`，**109 个用例参与 / 38 个隔离 / 721 个 test 方法 / 75.4s**，`⚑` 0 个
