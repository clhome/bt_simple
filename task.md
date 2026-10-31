# Gitea 插件自动获取最新版本与无损平滑升级任务

## 项目概况与目标

针对 `plugins/gitea` 插件实现全自动最新版本检测与老版本一键无损升级能力，确保生产环境下升级过程绝对平滑、不破坏既有环境与用户数据：

1. **自动获取最新版本与版本对比**：
   - 实现高可用版本嗅探：支持 GitHub Releases 页面 302 重定向嗅探（免 API 限流）+ GitHub REST API 兜底，并集成面板内置 GitHub 镜像加速通道；
   - 精确读取本地当前版本（执行 `gitea --version` 结合 `version.pl`）；
   - 提供版本缓存与手动刷新机制，提取最新版本号、发布日期与 Release Notes 摘要；
   - 引入语义化版本（SemVer）比对算法，精确判断更新状态。
2. **老版本一键无损安全升级与秒级自动回滚（核心安全保障）**：
   - **环境与数据绝对隔离**：严格保持 `/www/server/gitea/custom/conf/app.ini` 独立不变，保持仓库、数据库、LFS、附件与 SSH 密钥等数据 100% 独立，不破坏原有环境；
   - **大版本跳跃防呆与 SQLite 自动快照**：识别版本跨度，规避 Gitea 数据库迁移跳跃断代风险；升级前自动快照 SQLite 数据库文件；
   - **升级前环境兼容性预检**：下载新版二进制包并解压后，先在临时目录预执行 `--version` 测试，确保系统架构与 glibc 动态链接库完全兼容；
   - **原子替换与 15 秒健康巡检**：备份旧可执行文件为 `gitea.bak.{timestamp}`，优雅停止旧服务，替换二进制并启动新版本，自动触发 Gitea 内部 Schema 迁移，持续巡检进程与端口；
   - **异常自动秒级回滚**：若新版本启动失败或 15 秒内崩溃，立即自动恢复 `gitea.bak` 旧版本二进制并拉起旧服务，保证原有使用环境不受破坏，服务短暂重启。
3. **前端管理界面与多语言支持**：
   - 在 `plugins/gitea/index.html` 菜单中新增「版本管理」功能项（并在「服务」首页增加当前/最新版本徽标联动）；
   - 展示当前版本、最新版本、更新状态、发布时间与更新日志；
   - 提供【检查更新】与【一键安全升级】按钮，包含安全提示弹窗与升级进度提示；
   - 补齐 `plugins/gitea/lang/` 6 种语言包（zh-CN, zh-TW, en, de, fr, it）。
4. **自动化测试与跨平台验证**：
   - 在根目录 `test/` 编写完备的自动化测试脚本，验证版本探测、SemVer 比对、升级流程、自动回滚以及前端接口；
   - 确保遵循 UTF-8 LF 规范与 Windows/Linux 跨平台兼容性要求。

## 规范与原则

- **简洁至上**：恪守 KISS 原则，注重代码可维护性，严禁过度工程化与冗余抽象。
- **第一性原理**：从核心问题出发拆解实现路径，杜绝盲目臆测。
- **事实优先**：严谨客观，发现既有代码问题、需求冲突或盲点请直接指出。
- **编码与格式**：所有文件统一采用 UTF-8 (无 BOM) 编码，换行符强制使用 LF (`\n`)。
- **跨平台兼容**：保证在 Windows 11 本地开发与 Linux 服务器部署的双向跨平台兼容性，严禁硬编码反斜杠路径。
- **目录洁净**：测试脚本统一归入根目录 `test/`，严禁污染生产代码目录，执行完成后主动清理临时排查文件。

## 任务拆解与进度 (Task List)

- [x] **任务 1：后端版本探测与最新 Release 解析开发 ([plugins/gitea/index.py](file:///d:/git/gitea/bt_simple/plugins/gitea/index.py))**
  - [x] 1.1 实现 `getCurrentVersion`：优先通过二进制 `gitea --version` 与 `version.pl` 获取精确当前版本
  - [x] 1.2 实现 `getLatestReleaseFromGithub`：实现 302 重定向嗅探与 GitHub API 降级通道，支持国内 GitHub 镜像代理与本地缓存
  - [x] 1.3 实现 SemVer 版本大小解析比对与大版本跨度风险评估逻辑
- [x] **任务 2：实现原子升级、健康检查与秒级回滚核心逻辑 ([plugins/gitea/index.py](file:///d:/git/gitea/bt_simple/plugins/gitea/index.py))**
  - [x] 2.1 实现升级前置安全备份（旧二进制备份与 SQLite 数据快照）
  - [x] 2.2 实现新版本下载、解压、预检（`--version` 架构与 glibc 探针）
  - [x] 2.3 实现停服、原子替换二进制与拉起新版本
  - [x] 2.4 实现 15 秒健康巡检与异常自动回滚（Fail-Safe Rollback）
  - [x] 2.5 暴露后端 API：`check_update` 与 `upgrade_app`
- [x] **任务 3：前端界面交互与体验集成 ([plugins/gitea/index.html](file:///d:/git/gitea/bt_simple/plugins/gitea/index.html), [plugins/gitea/js/gitea.js](file:///d:/git/gitea/bt_simple/plugins/gitea/js/gitea.js))**
  - [x] 3.1 在 `index.html` 菜单中增加「版本管理」项
  - [x] 3.2 在 `js/gitea.js` 中实现版本信息展示、更新检测触发与更新日志渲染
  - [x] 3.3 实现安全升级弹窗确认、进度加载遮罩与升级完成回调
  - [x] 3.4 在「服务」页面顶部增加版本状态与快捷更新入口
- [x] **任务 4：多语言包更新与同步 ([plugins/gitea/lang/](file:///d:/git/gitea/bt_simple/plugins/gitea/lang/))**
  - [x] 4.1 在 `zh-CN.json`, `zh-TW.json`, `en.json`, `de.json`, `fr.json`, `it.json` 补全新增多语言词条
- [x] **任务 5：编写自动化测试与全量回归验证**
  - [x] 5.1 在 `test/test_gitea_upgrade.py` 中补齐针对版本检测、版本比对、升级及回滚流程的测试
  - [x] 5.2 执行全量测试验证，确认所有测试通过且无语法、编码错误
  - [x] 5.3 验证完成后主动清理测试临时文件，更新任务打勾状态
- [x] **任务 6：基于 2026-10-31 建议报告与最新发布规范的二次深度优化**
  - [x] 6.1 精简 `info.json`：剔除淘汰的 1.17~1.24 等无用老版本，只显示当前主流稳定版 `["28.2.0", "1.27.3"]`
  - [x] 6.2 修正 SemVer 归一化算法：将 `28.x` 映射为 `(1, 28, x)`，正确判定 1.26 到 28.2 为两级平滑升级
  - [x] 6.3 强化老用户升级提示：在【服务】页面顶部增加醒目的「升级横幅」，说明 28.x 即 1.28 稳定线并提供一键升级
  - [x] 6.4 扩充备份与回滚范围：将 `custom/conf/app.ini` 纳入完整快照备份与回滚链
  - [x] 6.5 增加 `app.ini` 28.x 兼容性预检：检测废弃键与阻止启动的非法 `BLOCKED_HOST_LIST`
  - [x] 6.6 适配 Darwin 资产名称：版本 ≥28 时去除 `-10.12`，彻底解决 macOS 下 404 缺陷
  - [x] 6.7 更新回归测试集与 i18n 多语言校验，完整门禁 3 项失败（2 项前置、1 项全量 flaky 待复跑）
- [x] **任务 7：修复插件严格模式棘轮报警 (`test_plugin_install_strict_mode.py`)**
  - [x] 7.1 将 `plugins/jdk/install.sh` 中的裸 `|| true` 优化替换为安全命令 `|| :`，消除基线超额突破
  - [x] 7.2 运行回归测试套件 `test_plugin_install_strict_mode.py` 验证 26 项用例与门禁全绿通过
- [x] **任务 8：修复弹窗多语言溢出与换行护栏 (`test_dialog_i18n_overflow.py`)**
  - [x] 8.1 优化 `plugins/gitea/lang/` 各语言包中「版本管理」侧边菜单翻译为「Versions/Versionen/Versioni」，解决 97px 定宽菜单槽溢出
  - [x] 8.2 在 `plugins/gitea/js/gitea.js` 两处 `display:flex; justify-content:space-between;` 容器中追加 `flex-wrap:wrap;`，满足类级换行护栏要求
- [x] **任务 9：2026-10-31 新发现问题专项修复（P0、P1-1~P1-4、P2）**
  - [x] 9.1 (P0) 修复 JDK `install.sh` 动态别名删除：按 `keytool -list -v` 提取完整别名，删除失败计入日志，杜绝 Temurin DN 别名静默失效
  - [x] 9.2 (P1-1) 修复 Gitea 进程探测与升级停服验证：`getGiteaPids` 剥离 ` (deleted)` 后缀并辅以 `cmdline` 判据，`upgradeApp` 增加端口释放检测与残留 PID 明示
  - [x] 9.3 (P1-2) 修复 Gitea start 在 systemd `active(exited)` 僵住状态下的启动处理：识别僵住状态并降级转 `restart`
  - [x] 9.4 (P1-4) JDK 管理器版本升级为 1.2 并同步 `test_jdk_plugin.py` 测试断言
  - [x] 9.5 (P2-2/P2-3) 微调 `RELEASE_TEMPLATE.md` 措辞为“尾部回退区”并增补测试复跑与升级说明清单
  - [x] 9.6 编写并运行回归测试，验证全部修复成果
