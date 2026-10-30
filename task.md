# 御风面板 487d1f4 + 134ac78 遗留缺陷与衍生问题深度闭环

## 项目概况与目标

针对 2026-10-30 审计报告中未闭合的问题（P1-1 至 P1-10、P2-1 至 P2-5）及关联同类衍生问题进行彻底根治：
1. 彻底解决 MariaDB 与 MySQL 卸载过程中的假成功、未受控放行、serverPath 越界与幂等性缺失；
2. 彻底根治 MySQL 在 Debian 13 及各版本下的 libtirpc-dev 依赖确实问题，纠正镜像下载与续传描述；
3. 为所有大源码构建（MariaDB / MySQL 各版本）建立前置秒级磁盘容量硬预检；
4. 根治纯净系统下全新安装无法显示初始明文密码问题（虚拟环境 Python 解释器调用链修复）；
5. 按照方案 A 闭合死节点队尾降级，同步收紧 `_gh_verify_file` 主下载路径校验窄口；
6. 完善双语帮助、发布说明，全面补齐并纠正测试套件滞后断言，保持全量测试全绿。

## 规范与原则

- **简洁至上**：恪守 KISS 原则，注重代码可维护性，严禁过度工程化与冗余抽象。
- **第一性原理**：从核心问题出发拆解实现路径，杜绝盲目臆测。
- **事实优先**：严谨客观，严格依据真实退出码与完整性校验，杜绝任何假成功。
- **编码与格式**：所有文件统一采用 UTF-8 (无 BOM) 编码，换行符强制使用 LF (`\n`)。
- **跨平台兼容**：保证在 Windows 11 本地开发与 Linux 服务器部署的双向跨平台兼容性，严禁硬编码反斜杠路径。
- **目录洁净**：测试脚本与排查验证工具统一归入根目录 `test/` 或既有 `testsuite/`，严禁污染生产代码目录。

## 任务拆解与进度 (Task List)

- [x] **任务 1：MariaDB & MySQL 卸载调用链、安全断言与幂等性彻底闭环（P1-1, P1-2, P1-3, P1-4 及 MySQL 类似问题）**
  - [x] 1.1 修复 `plugins/mariadb/index.py` 的 `uninstallPreInspection`：服务停止失败或进程残留时拒绝返回 ok、拒绝清理图标、带回残留信息，并同步修复 `plugins/mysql/index.py`（P1-1）
  - [x] 1.2 修复 `plugins/mariadb/install.sh` 兜底删除：增加严格的 `/www/server` 前缀断言与防穿透保护（P1-2）
  - [x] 1.3 修复 `plugins/mariadb/install.sh` 卸载幂等性：已卸载干净且无残留进程时正常退出，不误报错误（P1-3）
  - [x] 1.4 规范并在代码/注释中固定 MariaDB / MySQL 卸载调用链与状态同步机制（P1-4）
- [x] **任务 2：MySQL Debian 依赖与全版本类似缺陷修复及下载客观说明（P1-5, P1-6, P1-7）**
  - [x] 2.1 修复 `plugins/mysql/versions/8.0/install.sh` 及 8.2~9.7 各版本构建脚本的 `libtirpc-dev` 等依赖安装 Debian/Ubuntu 通用适配（P1-7）
  - [x] 2.2 纠正 `task.md` 中关于 MySQL 下载跨镜像续传的超前表述，客观记录实测镜像可达性结果（P1-5, P1-6）
- [x] **任务 3：大源码构建磁盘容量前置智能预检（P1-8 及全量版本适配）**
  - [x] 3.1 为 MariaDB (11.4, 10.6) 增加构建前 $\ge$ 8GB 磁盘空闲空间预检（P1-8）
  - [x] 3.2 为 MySQL (8.0, 5.7, 8.2~9.7) 增加构建前 $\ge$ 10GB 磁盘空闲空间预检，空间不足秒级报错并显示缺额（P1-8）
- [x] **任务 4：初始密码真实展示链与虚拟环境 Python 彻底根治（P1-9）**
  - [x] 4.1 修复 `deploy.sh` 与 `scripts/init.d/yf.tpl` 的 Python 执行器：优先使用面板虚拟环境 Python，确保 `bcrypt` 模块正常加载（P1-9）
  - [x] 4.2 优化 `yf.tpl` 中安装完成文案，确保初始密码直观展示，兜底指引清晰（P1-9）
- [x] **任务 5：代理节点队尾降级结项与校验窄口同步收紧（P1-10, P2-1, P2-2, P2-3）**
  - [x] 5.1 结项 P1-10：确认死节点（`cors.zme.ink`、`gh.ddlc.top`）按方案 A 保持队尾降级并更新说明（P1-10）
  - [x] 5.2 修复 `scripts/github_download.sh`：将 `_gh_verify_file` 校验口径同步收紧（工具缺失报错、HTML 1024 字节、长文本报错 2048 字节）（P2-1）
  - [x] 5.3 优化 `scripts/init.d/yf.tpl` 中的 `yf_list`：规范双语结构并增加同步修改说明（P2-2）
  - [x] 5.4 补全 `RELEASE_TEMPLATE.md` 中关于 `yf 0` 与 `100/101` 变动说明（P2-3）
- [x] **任务 6：测试套件补齐、旧断言纠正与全量门禁验证（P2-5）**
  - [x] 6.1 `testsuite/test_proxy_tester.py`：补充未指定 `--save` 保护与显式 `--save` 写回用例（P2-5）
  - [x] 6.2 `testsuite/test_yf_cli_and_i18n.py::test_09`：无 bcrypt 环境时优雅跳过而非红脸（P2-5）
  - [x] 6.3 `testsuite/test_mariadb_uninstall.py`：更新过时的恒为 ok 断言，补齐 stop 失败拦截、自检 exit 1 与 serverPath 安全断言测试（P2-5）
  - [x] 6.4 运行所有测试套件保持全绿通过
