# 御风面板回归问题深度修复与共性整改

## 项目背景与目标

根据真机回归测试报告（`御风面板_bt_simple_聚焦真机回归结论_9d30461_2026-10-29.md`），重点攻坚并彻底修复报告中暴露出的 4 项关键缺陷（N8、N9、N10、N11），并对全仓存在的同类共性问题（坏代理污染、弱文件校验、扩展依赖冲突、大包下载超时与死链）进行同口径整改与测试固化，确保所有插件在真机与 CI 环境下均具备极高的稳定性和自愈能力。

## 规范与原则

- **编码标准**：统一采用 UTF-8 (无 BOM) 编码，换行符强制使用 LF (`\n`)。
- **环境兼容**：保证在 Windows 11 本地开发与 Linux 服务器部署的双向跨平台兼容性，严禁硬编码反斜杠路径。
- **事实与防假**：严格依据实际校验结果（魔数、完整性检查、解压探活、真实退出码），严禁任何口头或表面假成功。
- **目录洁净**：测试脚本与排查验证工具统一置于 `test/` 目录或既有 `testsuite/`，保持生产目录洁净。

## 任务拆解与进度 (Task List)

- [x] **任务 1：N8 修复与代理/校验共性强化（P1）**
  - [x] 1.1 从 `scripts/proxies.list` 与 `deploy.sh` 中移除已停用失效节点 `gh.con.sh`，保证单一真源与引导副本同步
  - [x] 1.2 重构强化 `scripts/github_download.sh` 中的 `_gh_verify_file` 与 `yf_verify_archive`：对压缩包后缀严格校验魔数与解压完整性，严禁放行错误文本；拦截代理停用与报错文本；下载成功日志附带真实字节数与校验状态
  - [x] 1.3 修复 `plugins/phpmyadmin/install.sh`：GitHub 源下载后严密校验包有效性，损坏时自动清除并无缝回落至官方源；官方源同样完成有效性闭环校验；解压前严密防御
- [x] **任务 2：N9 修复与 php 扩展依赖助手互斥包隔离（P1）**
  - [x] 2.1 修复 `plugins/php/versions/common/curl.sh`：将 apt 包名参数由互斥双包改为首选 `libcurl4-openssl-dev`
  - [x] 2.2 增强 `plugins/php/versions/common/php_ext_deps.sh` 中的 `yf_ext_ensure_pkgconfig`：支持候选包逐个依次尝试安装，彻底杜绝把互斥包同时传给 apt 导致崩溃；输出真实安装错误信息避免全吞；照抄命令输出单包
- [x] **任务 3：N10 修复与 php 主构建核心依赖前置确保（P2）**
  - [x] 3.1 在 `plugins/php/versions/common/php_ext_deps.sh` 中新增 `yf_php_ensure_core_build_deps` 函数，前置探测并自动补齐 `pkg-config`、`libxml2-dev`、`libsqlite3-dev` 等主构建核心依赖
  - [x] 3.2 在 `plugins/php/install.sh` 中接入核心依赖前置确保，缺失且无法安装时提供明确友好的提示与照抄命令并诚实退出
- [x] **任务 4：N11 修复与 mysql-fast 下载 URL/大包超时整改（P1）**
  - [x] 4.1 修复 `plugins/mysql/install.sh` 下载超时：显式设置长超时（1800s），防止 850MB+ 大包在默认 30s 下被截断
  - [x] 4.2 完善 MySQL 预编译包官方分发体系与镜像列表：纳入官方 CDN（`cdn.mysql.com`）、重定向分发（`dev.mysql.com/get/...`）与 Archives 归档库，剔除已失效的空镜像；修正 8.4 等版本的可用发布配置
- [x] **任务 5：自动化测试覆盖与全量验证**
  - [x] 5.1 编写/更新针对代理节点、下载坏文件拦截、curl 依赖助手单包安装、php 核心依赖探测及 mysql 下载 URL 的测试用例
  - [x] 5.2 运行测试套件验证修复成果，清理测试临时文件，确保全绿
