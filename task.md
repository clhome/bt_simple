# 任务清单：御风面板全模块功能性测试套件构建与执行

> **目标**：在 `testsuite/Functional Testing/` 目录下构建覆盖项目全部层级与模块的功能性测试套件（Functional Testing），全面验证每个模块的业务设计要求，执行并输出完整测试报告。

## 任务拆解与进度

- [x] **Task 1: 测试套件基础设施与仿真支持 (`ft_common.py`)**
  - [x] 封装跨平台沙箱运行环境（隔离数据目录、虚拟面板 DB、临时 serverDir）。
  - [x] 提供底层系统命令与 I/O 调用的可控仿真桩（捕获入参、模拟返回、验证业务流）。
  - [x] 自动执行完整 `default.sql` 与动态补齐 `crontab` 迁移列，建立自洽的数据库环境。
- [x] **Task 2: 独立系统守护与 CLI 核心功能测试 (`ft_daemons_and_cli.py`)**
  - [x] `panel_task.py`：测试任务队列唤醒逻辑、PID 锁管理与信号仿真。
  - [x] `panel_tools.py`：测试命令行面板访问控制、端口/安全入口设置、BasicAuth/2FA 开关、用户名修改与 bcrypt 密码重置。
- [x] **Task 3: Web Admin 核心控制台 13 大模块功能测试 (`ft_admin_web_core.py`)**
  - [x] 网站管理 (`site`)：站点入库生命周期、虚拟主机域名绑定、站点启停与删除。
  - [x] 文件管理 (`files`)：文件读写、目录创建、回收站软删除隔离与安全彻底删除。
  - [x] 设置与菜单 (`setting/config`)：菜单数据自愈机制、默认菜单注入、XSS 防御与配置读取。
  - [x] 计划任务 (`crontab`)：Crontab 表达式解析、任务入库与脚本生命周期。
  - [x] 防火墙 (`firewall`)：端口放行、规则持久化、面板关键端口保护与删除拦截。
  - [x] 监控与采样 (`monitor`)：系统硬件采样入库、跨时间段指标查询。
  - [x] 仪表盘与系统信息 (`dashboard/system`)：基础硬件指标采集与多核 CPU 解析。
- [x] **Task 4: 36 大生态插件业务功能测试套件**
  - [x] 数据库插件 (`ft_plugins_databases.py`)：覆盖 MySQL, MariaDB, Redis, Valkey, PostgreSQL, MongoDB, DataQuery 的契约、配置探测与参数防御。
  - [x] Web与运行环境插件 (`ft_plugins_web_runtime.py`)：覆盖 OpenResty, Apache, PHP, OP-WAF, OP-LoadBalance 的服务控制、入参多态解码、域名注入防范与 Upstream 校验。
  - [x] 系统运维与容器插件 (`ft_plugins_system_ops.py`)：覆盖 Clean, Fail2ban, Docker, YufengSystemd, Supervisor 的垃圾防误删、容器名白名单、高危挂载阻断与服务单元管理。
- [x] **Task 5: 功能测试统一执行器与执行报告生成**
  - [x] 编写统一测试驱动器 `run_all_ft.py`，支持多套件执行、结果统计与明细捕获。
  - [x] 批量执行所有功能测试，分析执行结果与断言（23 个端到端测试全部通过，100% PASS）。
  - [x] 输出完整详尽功能性测试审计与执行报告到 `testsuite/Functional Testing/20261010ft.md`。
