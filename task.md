# 项目描述
BtSimple (mdserver-web) 是一个简单的 Linux 面板，旨在提供高效、简洁的服务器管理体验。

# 开发规范
- 简洁至上 (KISS 原则)
- 统一使用 UTF-8 (无 BOM)
- 优先使用内置函数和已有工具
- 严格遵循构思、审核、拆解、执行流程

# 任务清单
- [x] 修复页面更新报错：服务器数据或网络有问题!
    - [x] 在 `versionDiff` 中支持忽略 `v` 前缀
    - [x] 在 `updateServer` 中改用 `tag_name` 替代 `name`
    - [x] 优化 `getServerInfo` 的超时和代理处理，确保 API 调用稳定
