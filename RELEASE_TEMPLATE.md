### 🚀 BtSimple v1.0.1 - 安全加固与仓库迁移正式版

本项目是从 `mdserver-web` 深度 Fork 并重构的轻量级 Linux 面板。本次发布标志着系统已完成全面的安全性审计与性能优化，建议所有用户更新。

#### 🔒 安全增强 (Security Hardening)

- **密码算法升级** ：全面迁移至 `bcrypt` 加希算法，且支持从旧版 MD5 无缝平滑迁移。
- **通信协议锁定** ：强制限制 TLS 1.2+ 协议及高强度加密套件，禁用不安全的旧版 SSL。
- **智能防御机制** ：
- 引入基于 IP 的登录锁定机制，防范暴力破解。
- 强化 CSRF 防护，校验请求来源（Referer/Origin）。
- **注入防护** ：对所有 Shell 命令执行路径进行了 shlex 转义加固，防止命令拼接注入。
- **路径安全** ：增强了文件上传与管理的路径过滤，防止目录遍历攻击。

#### ⚡ 性能与可靠性优化 (Performance & Reliability)

- **数据库连接优化** ：重新配置 SQLite 连接池（10/20 比例），降低资源占用。
- **后台任务重构** ：将高风险的递归重试逻辑改为稳健的循环机制，彻底杜绝 `RecursionError`。
- **响应速度提升** ：移除大量不必要的 `os.system` 调用，改用原生 Python 内置函数处理文件权限，操作延迟显著降低。
- **轮询负载优化** ：优化了后台监控的采样频率，降低闲置时的 CPU 和 I/O 开销。

#### 🌐 仓库迁移说明

- 项目官方地址已正式迁移至：`https://github.com/clhome/bt_simple`
- 更新检查逻辑、部署脚本及 UI 链接已全部同步适配新地址。

#### 🛠️ 安装与迁移方法

全新安装或从旧版迁移：

```bash
curl --insecure -fsSL https://raw.githubusercontent.com/clhome/bt_simple/refs/heads/master/deploy.sh | bash
```

++利用Github action 进行自动发布
