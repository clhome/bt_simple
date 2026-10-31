# 御风 JDK 管理器插件显示修复、版本升级与安全加固 (CVE-2026-91403/114820)

## 项目概况与目标

针对 `plugins/jdk` 插件进行全方位缺陷修复、版本升级与针对 2026年10月重大安全漏洞的加固治理：

1. **界面显示修复**：修复 `plugins/jdk/index.html` 中第 115 行 `.textpt` 致命语法错误，恢复管理界面右侧内容区正常渲染；
2. **插件版本升级**：将插件元数据版本号由 `1.0` 升级为 `1.1`（更新日期为 `2026-10-31`），同步安装脚本与初始化 `version.pl`；
3. **软件菜单提示升级与老版本一键更新**：
   - 在软件管理列表标题旁增加可更新徽章提示，操作列提供【更新】入口；
   - 动态更新左侧菜单 `.softnum` 角标提示有软件待升级；
   - 完善 `plugins/jdk/install.sh` 的更新升级处理分支，老版本点击“更新”时平滑升级 `version.pl` 至 1.1，并自动对已有 JDK 进行安全加固；
4. **在线 JDK 版本矩阵升级与数字排序优化**：
   - 解决清华镜像站老版本 404 导致离线 fallback 失败的问题，将默认硬编码源更新为当前镜像真实存在的文件（8u504, 11.0.32.1, 17.0.21, 21.0.13），并增加 `jdk-25`；
   - 自适应 CPU 架构（x86_64 与 aarch64）；
   - 将动态版本解析从 ASCII 字典序改进为版本号数值元组排序，杜绝大小版本比较倒挂；
5. **CVE-2026-91403 / CVE-2026-114820 (CVSS 9.1) 信任库加固治理**：
   - 在新安装/更新 JDK 时，使用 `keytool` 自动从 `cacerts` 中剔除 4 张弱密钥 CA 根证书（`emsignrootcag1 [jdk]`, `emsignrootcag2 [jdk]`, `emsigneccrootcag3 [jdk]`, `comodoaaaca [jdk]`）；
   - 在后端 `plugins/jdk/index.py` 中提供 `check_ca_security` 与 `fix_ca_security` 接口；
   - 在插件前端界面为已安装 JDK 呈现安全状态与一键加固入口；
6. **多语言与规范**：补齐多语言词条（zh-CN, zh-TW, en, de, fr, it），编写回归测试并保证跨平台兼容。

## 规范与原则

- **简洁至上**：恪守 KISS 原则，注重代码可维护性，严禁过度工程化与冗余抽象。
- **第一性原理**：从核心问题出发拆解实现路径，杜绝盲目臆测。
- **事实优先**：严谨客观，发现既有代码问题、需求冲突或盲点请直接指出。
- **编码与格式**：所有文件统一采用 UTF-8 (无 BOM) 编码，换行符强制使用 LF (`\n`)。
- **跨平台兼容**：保证在 Windows 11 本地开发与 Linux 服务器部署的双向跨平台兼容性，严禁硬编码反斜杠路径。
- **目录洁净**：测试脚本统一归入根目录 `test/`，严禁污染生产代码目录，执行完成后主动清理临时排查文件。

## 任务拆解与进度 (Task List)

- [x] **任务 1：修复前端白屏缺陷 ([plugins/jdk/index.html](file:///d:/git/gitea/bt_simple/plugins/jdk/index.html))**
  - [x] 1.1 修复 `$("#jdk_menu_manage").textpt(...)` 为 `$("#jdk_menu_manage").text(pt(...))`
  - [x] 1.2 检查并确保弹窗初始化、事件绑定与表格初次加载流程正常
- [x] **任务 2：JDK 在线版本源、排序算法与架构适配 ([plugins/jdk/index.py](file:///d:/git/gitea/bt_simple/plugins/jdk/index.py))**
  - [x] 2.1 更新兜底 `default_jdks` 矩阵，替换失效的 404 URL，加入 `jdk-25`
  - [x] 2.2 增加 CPU 架构（x86_64 / aarch64）自适应探测
  - [x] 2.3 优化 `get_online_jdks` 版本号多段数字解析排序算法
- [x] **任务 3：实现 CVE-2026-91403 / CVE-2026-114820 信任库加固与治理**
  - [x] 3.1 在 `plugins/jdk/install.sh` 及 `index.py` 安装脚本中增加安装后自动 `keytool -delete` 4 个高危 CA 证书
  - [x] 3.2 在 `index.py` 中增加 `check_ca_security` 与 `fix_ca_security` 接口，支持扫描与一键加固
  - [x] 3.3 在 `plugins/jdk/index.html` 前端表格中展示证书安全状态与一键加固按钮
- [x] **任务 4：插件版本升级、软件管理更新支持与菜单升级提示**
  - [x] 4.1 升级 `plugins/jdk/info.json` 版本至 `1.1`，更新日期 `2026-10-31`
  - [x] 4.2 优化 `plugins/jdk/install.sh`：支持传递版本参数，老版本更新时平滑升级 `version.pl` 至 1.1 并触发 CA 加固
  - [x] 4.3 在 `web/static/app/soft.js` 中优化通用插件更新提示徽章，并在左侧菜单 `.softnum` 联动展示可更新数量
- [x] **任务 5：多语言词条补全与全量回归测试**
  - [x] 5.1 在 `plugins/jdk/lang/` 各语言包补充新增词条
  - [x] 5.2 编写 `test/test_jdk_plugin.py` 自动化测试脚本，全面验证接口、版本解析、安装升级脚本、加固逻辑与语法规范
  - [x] 5.3 运行验证全绿后，清理临时测试脚本，完成收尾
