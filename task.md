# 任务清单：御风面板全模块功能性测试套件构建与执行

> **目标**：在 `testsuite/Functional Testing/` 目录下构建覆盖项目全部层级与模块的功能性测试套件（Functional Testing），全面验证每个模块的业务设计要求，执行并输出完整测试报告。

## 任务拆解与进度

- [ ] **Task 1: 测试套件基础设施与仿真支持 (`ft_common.py`)**
  - [ ] 封装跨平台沙箱运行环境（隔离数据目录、虚拟面板 DB、临时 serverDir）。
  - [ ] 提供底层系统命令与 I/O 调用的可控仿真桩（捕获入参、模拟返回、验证业务流）。
- [ ] **Task 2: 独立系统守护与 CLI 核心功能测试 (`ft_daemons_and_cli.py`)**
  - [ ] `panel_task.py`：测试任务队列出入队、任务执行状态流转、并发锁抢占与取消处理。
  - [ ] `panel_tools.py`：测试命令行重置密码、修改访问端口、查看/修改安全入口、急救自检。
- [ ] **Task 3: Web Admin 核心控制台 13 大模块功能测试 (`ft_admin_web_core.py`)**
  - [ ] 网站管理 (`site`)：站点生命周期、虚拟主机配置生成与解析、伪静态、反代规则。
  - [ ] 文件管理 (`files`)：文件读写、权限修改模型、解压缩、回收站机制。
  - [ ] 设置与菜单 (`setting/config`)：菜单容灾与合法性校验、安全入口、端口变更。
  - [ ] 计划任务 (`crontab`)：Cron 周期解析、任务脚本组装与更新。
  - [ ] 防火墙 (`firewall`)：端口与 IP 放行/拦截规则组装。
  - [ ] 监控与仪表盘 (`monitor/dashboard`)：性能采样计算、时间范围聚合、系统资源读取。
  - [ ] 软件商店、系统管理、日志、任务、安装、插件路由完整业务逻辑。
- [ ] **Task 4: 36 大生态插件业务功能测试套件**
  - [ ] 数据库插件 (`ft_plugins_databases.py`)：覆盖 MySQL, MariaDB, Redis, Valkey, PostgreSQL, MongoDB, DataQuery 等配置生成、管理命令、备份恢复逻辑。
  - [ ] Web与运行环境插件 (`ft_plugins_web_runtime.py`)：覆盖 OpenResty, Apache, PHP, PHP-FPM, OP-WAF, OP-LoadBalance, Varnish 等服务控制与规则装配。
  - [ ] 系统运维与容器插件 (`ft_plugins_system_ops.py`)：覆盖 Docker, Clean, Fail2ban, Supervisor, Systemd, TaskManager, Swap, LinuxSysOpt 等任务编排。
- [ ] **Task 5: 功能测试统一执行器与执行报告生成**
  - [ ] 编写统一测试驱动器 `run_all_ft.py`，支持多套件执行、结果统计与明细捕获。
  - [ ] 批量执行所有功能测试，分析执行结果与断言。
  - [ ] 输出最终完整执行报告到 `testsuite/Functional Testing/20261010_ft_execution_report.md`。
