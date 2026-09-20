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
