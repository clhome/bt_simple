# bt_simple 项目开发任务清单

## 项目整体描述

御风面板（bt_simple）是一个 Linux 服务器管理面板。提供包括服务器状态监控、计划任务管理、网站与数据库管理等各种常规服务器管理操作。

## 开发规范描述

- 遵循 KISS 原则，保持代码简单。
- 多轮对话逐步明确需求。
- 修改文件使用 UTF-8 (无 BOM) 格式。
- 每次开发必须及时更新维护本任务列表。

---

## 需求：修复计划任务从服务器同步无效的问题

- [x] 分析前端 `crontab.js` 中“从服务器同步”功能所调用的后端接口 (`/crontab/sync_sys_cron`)。
- [x] 分析 `init_cron.py` 中的同步逻辑，发现原 `init_cron()` 对系统原生计划任务存在漏解析，且主动过滤了面板产生的任务，导致未在面板数据库注册的任务无法同步。
- [x] 重构 `cron_todb` 逻辑，使其能支持正确的 cron 表达式（包含 `day-n`, `hour-n`, `minute-n` 等）。
- [x] 重写 `init_cron()` 核心逻辑，解析并遍历系统的 crontab 文件。
- [x] 对于未在数据库里的面板任务（`/www/server/cron/xxx`），通过比对哈希并读取源脚本将其导入面板数据库；对系统原生任务也直接添加为 `toShell` 类型。
- [x] 在 `sync_all_tasks()` 中添加并合并 `init_cron()` 的同步统计结果，完成整个流程修复。

- [x] 调整恢复任务的命名逻辑：从提取哈希前8位修改为提取后8位，例如 `[恢复任务] 56c7b212`。

------

[20260618 16:26]Code committed

## 需求：优化更新脚本，增加版本判断避免资源浪费

- [x] 在 `deploy.sh` 中新增 `check_version_and_update` 函数。
- [x] 解析本地 `.version` 与 Github Releases 的 `tag_name` 进行 `sort -V` 大小对比。
- [x] 将 `deploy.sh` 中 `update` 参数的行为从强制执行 `migrate_from_mw` 改为调用校验逻辑。
- [x] 额外增加 `force_update` 参数用于特殊情况下的强制覆盖安装。

------

[20260618 17:36] 更新脚本增加版本比对功能完成

## 需求：优化版本检测失败时的降级策略

- [x] 在 `deploy.sh` 中修改 `check_version_and_update` 逻辑：当无法访问 GitHub API 获取远端版本号时，直接降级执行强制覆盖升级 `migrate_from_mw`，以保证网络受限情况下的更新可用性。

------

[20260618 17:41] 网络受限时强制覆盖更新逻辑修复完成

------

[20260618 17:44]Code committed

## 需求：修复 deploy.sh 在 Linux 下因 CRLF 换行符报错的问题

- [x] 将 `deploy.sh` 文件的换行符从 CRLF 转换为 LF。
- [x] 确保 `deploy.sh` 的编码为 UTF-8 (无 BOM)。
- [x] 排查 `scripts/` 目录下的其他 `*.sh` 脚本并统一转换修复了 CRLF 与 BOM。

------

[20260618 18:26]Code committed

