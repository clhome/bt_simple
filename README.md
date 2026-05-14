<p align="center">
  <img src="https://raw.githubusercontent.com/clhome/bt_simple/master/web/static/img/logo.png" width="120" />
  <h3 align="center">BtSimple (bt_simple)</h3>
  <p align="center">一款基于 Python 的轻量级、安全增强型 Linux 服务器管理面板</p>
  <p align="center">
    <img src="https://img.shields.io/badge/License-MIT-green.svg" />
    <img src="https://img.shields.io/badge/Python-3.7+-blue.svg" />
    <img src="https://img.shields.io/badge/OS-Linux-orange.svg" />
  </p>
</p>

---

## 🚀 软件介绍

**BtSimple** 是一款轻量级的 Linux 面板，源自 [mdserver-web](https://github.com/midoks/mdserver-web) 项目。它秉持 **KISS (Keep It Simple, Stupid)** 原则，去除了冗余功能，专注于核心的网站管理、数据库运维和系统安全加固。

本项目在原版基础上进行了深度的安全性审计与性能优化，旨在为用户提供一个既强大又透明的服务器管理工具。

### 核心特性

- **轻量高效**：相比于传统面板，BtSimple 占用资源极低，非常适合小内存 VPS。
- **安全加固**：
  - 密码存储全面升级为 `bcrypt` 算法。
  - 强制支持 TLS 1.2+ 高安全通信协议。
  - 具备智能 IP 封禁机制，防范暴力破解。
  - 严密的 CSRF 防护与文件路径遍历检测。
- **计划任务深度重构**：
  - **模态化管理**：任务添加移至模态框，界面更清爽。
  - **导入/导出**：支持任务配置的 JSON 备份与跨平台迁移。
  - **智能策略**：支持股票开盘日、工作日、节假日等云端日期限制执行。
  - **日志优化**：支持日志框高度动态扩展、5秒自动刷新、执行任务后自动弹出日志及空日志友好展示。
  - **高效运维**：支持模糊搜索与多字段动态排序，实时持久化任务执行时间。
- **文件管理体验优化**：
  - **多标签页**：支持浏览器风格的多目录同时操作与本地状态持久化。
  - **全屏拖拽**：深度支持文件/文件夹递归拖入上传，自动解析并保留目录层级。
  - **预上传清单**：上传前展示详细统计清单与项目详情，确保操作准确无误。
- **全能管理**：集成 OpenResty、MySQL、PHP、Redis、MongoDB 等常用环境。
- **插件化架构**：功能高度解耦，按需安装，支持自定义插件开发。
- **极致兼容**：完美支持一键从 **mdserver-web** 或 **宝塔面板 (BT.CN)** 平滑迁移。

---

## 🛠️ 使用方法

### 1. 一键安装 / 迁移

我们提供了一个智能部署脚本，可以自动检测您的环境。无论是全新安装，还是从现有面板迁移，均可一键完成。

```bash
curl --insecure -fsSL https://raw.githubusercontent.com/clhome/bt_simple/refs/heads/master/deploy.sh | bash
```

#### 🇨🇳 中国境内服务器加速

针对中国境内服务器访问 GitHub 不稳定的问题，部署脚本内置了**自动加速功能**。它会自动检测服务器位置，并切换至国内镜像源（如 ghproxy 和清华 Pip 源）以确保安装成功。

如果您需要强制开启中国区加速模式，请使用以下命令：

```bash
curl --insecure -fsSL https://gh-proxy.org/https://raw.githubusercontent.com/clhome/bt_simple/refs/heads/master/deploy.sh | bash -s -- -cn
```

### 2. 备份与回滚

安全性是 BtSimple 的核心。在执行重大更新或迁移前，建议您手动备份关键数据。

#### 手动备份 (建议)

```bash
# 备份面板数据库与配置文件
tar -czf /www/backup/bt_simple_data_$(date +%Y%m%d).tar.gz /www/server/mdserver-web/data
```

#### 一键回滚 (通过部署脚本)

如果您在迁移后遇到兼容性问题，可以使用部署脚本快速回滚到原有的面板状态：

```bash
# 回滚到迁移前的 mdserver-web 状态
bash deploy.sh rollback_mw

# 回滚到迁移前的宝塔面板状态
bash deploy.sh rollback_bt
```

#### 一键卸载

如果您不再需要面板，可以执行以下命令进行清理（保留网站数据）：

```bash
# 方式 1：通过部署脚本卸载
bash deploy.sh uninstall

# 方式 2：通过系统命令卸载
mw uninstall
```

### 3. 命令行工具

面板内置了强大的 `mw` 命令行工具，方便在 SSH 环境下快速运维：

- `mw default`：查看面板默认登录信息。
- `mw stop/start/restart`：面板服务控制。
- `mw update`：检查并升级面板版本。

---

## 👨‍💻 开发方法

BtSimple 欢迎开发者参与贡献。代码结构清晰，易于上手。

### 目录结构

- `web/`：面板前端与后端逻辑 (Flask 实现)。
- `plugins/`：所有插件的存放目录，每个插件包含独立的 shell 脚本与 UI 配置。
- `scripts/`：安装、卸载与维护脚本。

### 插件开发步骤

1. 参考 `plugins/simple-plugin` 创建新插件目录。
2. 编写 `info.json` 定义插件元数据。
3. 编写 `install.sh` 实现自动化安装逻辑。
4. 编写 `index.py` 处理插件的后端业务逻辑。

### 编码原则

- 保持简单：避免过度工程化。
- 事实优先：在提交 PR 前请确保经过充分测试。
- 安全第一：使用内置的 `mw.shlex_quote` 处理系统命令。

---

## 📝 优缺点总结

### 优点

- **透明度高**：开源且代码逻辑清晰，用户可完全掌握服务器运行细节。
- **性能卓越**：采用原生 Python 开发，去除了不必要的后台轮询任务，响应极快。
- **迁移友好**：目前市面上对旧版 mdserver-web 和宝塔面板支持最友好的迁移方案。
- **安全性强**：经过系统性的漏洞审计与修复，具备企业级的安全防护基准。

### 缺点

- **生态规模**：插件数量相较于宝塔等商业面板较少，但已覆盖 90% 以上的常用需求。
- **文档完善度**：部分高级功能的开发文档仍在补充中。

---

## 🌟 未来方向

1. **缓存策略优化**：引入更高效的持久化缓存机制，进一步提升高并发下的 UI 响应速度。
2. **深度监控增强**：提供更细粒度的服务器资源监控报表与异常预警功能。
3. **插件市场扩展**：增加对 Node.js、Go、Docker 管理等现代开发环境的深度支持。
4. **自动化审计**：引入更严格的静态代码分析，确保持续的安全性。

---

**BtSimple** 致力于成为 Linux 面板界的一股清流，感谢所有贡献者和用户！

[GitHub 仓库](https://github.com/clhome/bt_simple) | [WIKI 文档](https://github.com/clhome/bt_simple/wiki)
