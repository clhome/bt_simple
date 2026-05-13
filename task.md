# BtSimple 项目优化整改任务书

## 项目整体描述
BtSimple 是一个基于 mdserver-web fork 的服务器管理面板，旨在提供简洁、高效、安全的服务器管理体验。本项目目前处于安全加固和可靠性提升阶段，需要根据《优化整改.md》进行系统性的整改。

## 开发规范描述
1. **简洁至上**：遵循 KISS 原则，代码逻辑清晰，易于维护。
2. **安全优先**：处理 Web 请求时必须考虑 CSRF、XSS、Session 安全等因素。
3. **兼容性**：在不改变现有功能的前提下进行加固，确保插件 and 数据完全兼容。
4. **日志记录**：关键业务逻辑增加必要的错误日志记录。
5. **标注完成**：每完成一项整改，需在《优化整改.md》中对应的条目后标注“（已修复）”。
6. **通用逻辑复用**：插件开发与维护应优先引用 `scripts/lib.sh` 中的公共函数（如 `get_local_addr`, `get_cpu_cores`, `mw_download`），严禁重复造轮子，确保全局安装逻辑一致性。

## Task List

- [x] S-01 Flask SECRET_KEY 加固 (web/admin/__init__.py)
- [x] S-02 Cookie 安全标记 (web/admin/__init__.py)
- [x] S-03 CSRF 防护 (web/admin/__init__.py)
- [x] S-04 安全响应头 (web/admin/__init__.py)
- [x] S-07 登录锁定改为 IP 封禁 (web/admin/dashboard/login.py)
- [x] R-01 递归重试改循环 (panel_task.py)
- [x] S-05 WebSocket CORS 配置 (web/admin/__init__.py)
- [x] S-08 API 认证加固 (web/admin/user_login_check.py)
- [x] S-09 文件上传安全处理 (web/admin/files/files.py)
- [x] R-03 会话过期逻辑优化 (web/admin/common.py)
- [x] R-04 panel_tools.py 运行时 Bug 修复
- [x] R-05 文件管理逻辑修复 (web/utils/file.py)
- [x] S-06 密码迁移至 bcrypt (web/admin/dashboard/login.py, web/thisdb/user.py)
- [x] S-10 Shell 命令转义加固 (web/core/mw.py)
- [x] S-11 移除敏感响应头 (web/admin/__init__.py)
- [x] R-06 TLS 版本限制 (web/setting.py)
- [x] P-01 高频文件轮询频率降低 (panel_task.py)
- [x] P-02 os.system 替换为原生 Python 操作 (web/utils/file.py)
- [x] P-04 数据库连接池配置优化 (web/config.py)
- [ ] O-01 中国区服务器安装优化 (deploy.sh, scripts/lib.sh, update.py)
- [x] O-02 插件版本更新与安装脚本核查 (plugins/*) (已完成核心插件优化)
