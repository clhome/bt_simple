# 御风面板 Debian 13 深度适配与审计缺陷全面整改

## 项目概况与目标

针对 2026-10-30 审计发现的问题（P1-1 至 P1-10、P2-1 至 P2-9），进行事实核查与彻底根治，同时全面深化 Debian 13 (trixie) 环境适配，消除所有假成功、死循环、未校验放行、双语代码漂移及测试空心问题。

## 规范与原则

- **简洁至上**：恪守 KISS 原则，注重代码可维护性，严禁过度工程化与冗余抽象。
- **第一性原理**：从核心问题出发拆解实现路径，杜绝盲目臆测。
- **事实优先**：严谨客观，严格依据真实退出码与完整性校验，杜绝任何假成功。
- **编码与格式**：所有文件统一采用 UTF-8 (无 BOM) 编码，换行符强制使用 LF (`\n`)。
- **跨平台兼容**：保证在 Windows 11 本地开发与 Linux 服务器部署的双向跨平台兼容性，严禁硬编码反斜杠路径。
- **目录洁净**：测试脚本与排查验证工具统一归入根目录 `test/` 或既有 `testsuite/`，严禁污染生产代码目录。

## 任务拆解与进度 (Task List)

- [x] **任务 1：Debian 13 (trixie) 深度适配与系统兼容强化**
  - [x] 1.1 `deploy.sh` APT 换源适配 deb822 格式（`/etc/apt/sources.list.d/debian.sources` 与 `ubuntu.sources`），支持阿里云镜像加速及更新失败自动回滚
  - [x] 1.2 `scripts/install/debian.sh` 跨架构软链加固：适配 aarch64 与 x86_64 下 `libaio.so.1t64` 到 `libaio.so.1` 软链接
  - [x] 1.3 `plugins/php-apt/install.sh` 系统代号探测升级：优先从 `/etc/os-release` 获取 `VERSION_CODENAME`，精准识别 Debian 13 为 `trixie`
  - [x] 1.4 `web/utils/system/update.py` 版本比较兜底：在 Python 3.12+ / 3.13 缺少 packaging 且无 distutils 时提供轻量元组比对兜底
- [x] **任务 2：PHP 主构建与扩展依赖检查缺陷修复（P1-1, P1-2, P1-3, P2-2）**
  - [x] 2.1 修复 `plugins/php/versions/common/php_ext_deps.sh` 复查漏查问题：在 `yf_php_ensure_core_build_deps` 复查段补齐 `sqlite3`、`zlib`、`openssl` 校验，杜绝假就绪（P1-1）
  - [x] 2.2 修复自动安装路径前置缺失 `apt-get update`：安装前执行非破坏性更新，避免新机或缓存过期导致失败（P1-2）
  - [x] 2.3 修复 `plugins/php/install.sh` 守卫静默跳过：当依赖助手库不可用或函数未定义时显式报错退出，严禁静默跳过（P1-3）
  - [x] 2.4 强化 `yf_ext_ensure_pkgconfig`：累积记录多候选包失败摘要，增加单包安装超时保护（P2-2）
- [x] **任务 3：MariaDB 卸载调用链、安全防护与退出码加固（P1-4, P1-5, P1-6）**
  - [x] 3.1 修复 `plugins/mariadb/index.py` 的 `uninstallPreInspection`：服务停止失败或进程残留时拒绝返回 ok，阻止假卸载（P1-4）
  - [x] 3.2 修复 `plugins/mariadb/install.sh` 卸载退出码：`stop_and_kill` 自检发现残留时由 WARN 升级为非 0 失败退出（P1-4）
  - [x] 3.3 加固 `version.pl` 回读与兜底删除：增加严格格式白名单校验，兜底 `rm -rf` 增加 `serverPath` 安全校验（P1-5）
  - [x] 3.4 梳理并注释规范 MariaDB 卸载调用链契约（P1-6）
- [x] **任务 4：MySQL 大包下载、镜像顺序与断点续传整改（P1-7, P2-3）**
  - [x] 4.1 纠正 `plugins/mysql/install.sh` 官方 URL 顺序断言与下载逻辑：保留网络中断后的续传能力，仅损坏时清理（P1-7）
  - [x] 4.2 抽取尺寸门校验常量 `MYSQL_TAR_MIN_BYTES` 并规范注释说明（P2-3）
- [x] **任务 5：代理管理、测速脚本与真源保护（P1-8, P1-9, P2-8）**
  - [x] 5.1 排查死节点 `cors.zme.ink`，保持 `scripts/proxies.list` 与 `deploy.sh` 引导序列严格同步（P1-8）
  - [x] 5.2 改造 `scripts/proxy_tester.py`：默认不写回原文件（新增显式 `--save` 控制），写回时完整保留行间注释（P1-9）
  - [x] 5.3 纠正 `README_cn.md` 表格中的代理说明，标注为示例并指向单一真源 `scripts/proxies.list`（P2-8）
- [x] **任务 6：面板初始密码展示、CLI 双语与命令友好提示（P1-10, P2-4, P2-9）**
  - [x] 6.1 根治初始密码无法展示顽疾：在 `panel_tools.py` 的 `show_panel_pwd()` 中改用 `yf.checkPwdCompat` 校验 bcrypt/MD5，恢复初始密码明文展示（P1-10）
  - [x] 6.2 重构 `scripts/init.d/yf.tpl` 的 `yf_default`：抽取地址组装公共逻辑，消除双语分支代码复制与漂移风险（P2-4）
  - [x] 6.3 优化 `yfcli` 命令分发：针对 `100/101` 提供已废弃专属提示，发布说明增加 `yf 0` 与 `100/101` 变动说明（P2-9）
- [x] **任务 7：压缩包与脚本校验边界收紧（P2-1）**
  - [x] 7.1 `scripts/github_download.sh`：解压校验工具缺失时明确失败（不放行），扩大错误页关键字扫描窗口至 2048 字节（P2-1）
  - [x] 7.2 `plugins/phpmyadmin/install.sh`：校验函数库不可用时显式报错中止，严禁放行未校验文件（P2-1）
- [x] **任务 8：自动化测试套件补齐、修正与全量验证（P2-5, P2-7）**
  - [x] 8.1 修复 `testsuite/test_download_multi.py`：测试桩兼容 `python3` 与 `sys.executable`（P2-5）
  - [x] 8.2 重构 `testsuite/test_yf_cli_and_i18n.py` 的 `test_05`：真实调用 `set_panel_username` 验证边界校验，补齐 `100/101` 与双语等用例（P2-5）
  - [x] 8.3 增强 `testsuite/test_report_9d30461_fixes.py`：补齐 N10 sqlite3 复查断言与 N11 官方源 URL 顺序断言（P2-5）
  - [x] 8.4 运行所有相关自动化测试套件验证修复成果，保持测试全绿（P2-7）
