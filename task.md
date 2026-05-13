# 项目描述
BtSimple 是一个简洁的 Linux 面板，旨在提供基础的服务器管理功能。

# 开发规范描述
1. 简洁至上：保持代码简单易懂，避免过度工程。
2. 统一风格：参考现有代码风格进行开发。
3. UTF-8 编码：所有文件使用无 BOM 的 UTF-8 编码。
4. 结构化：遵循「构思方案 → 审核确认 → 任务拆解 → 实施执行」流程。

# 任务列表
- [x] 为防火墙增加 enable 开关
    - [x] 数据库迁移：增加 `status` 字段到 `firewall` 表
    - [x] 后端：更新 `web/thisdb/firewall.py` 处理 `status` 字段
    - [x] 后端：更新 `web/utils/firewall.py` 增加状态切换逻辑
    - [x] 后端：在 `web/admin/firewall/__init__.py` 增加状态切换接口
    - [x] 前端：更新 `web/static/app/firewall.js` 渲染切换开关并调用接口
    - [x] 验证：确保开关能正确控制防火墙规则的生效和失效
