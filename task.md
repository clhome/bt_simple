# 日志清理插件重构为「日志管理与磁盘瘦身」任务进度

> 项目整体描述：将 plugins/clean 重构为专业、安全、高可靠的「日志管理与磁盘瘦身」插件，彻底消除命令注入隐患与 Inode 锁死，保护 Linux 等保安全审计合规，增加日志占用体检、Top 10 大文件榜单、精准保留天数与现代化 UI。
> 开发规范描述：KISS 原则，严禁命令拼接注入，采用 Python 原生安全文件操作；UTF-8 无 BOM，LF 换行符；跨平台兼容；测试代码统归根目录 test/。

## Task List

- [x] 1. 编写安全沙箱与合规防护模块 (`plugins/clean/clean_security.py`)
- [x] 2. 编写日志占用体检与分类扫描模块 (`plugins/clean/clean_scanner.py`)
- [x] 3. 编写精准清理执行器与战报审计模块 (`plugins/clean/clean_executor.py`)
- [x] 4. 重构插件主入口与 API 路由 (`plugins/clean/index.py`)
- [x] 5. 重构计划任务策略联动模块 (`plugins/clean/tool_task.py`)
- [x] 6. 现代化前端交互界面重构 (`plugins/clean/index.html`)
- [x] 7. 完善插件元数据、安装脚本与多语言 (`info.json`, `install.sh`, `lang/`)
- [x] 8. 编写测试用例并在 `test/` 运行验证，完成收尾清理
- [x] 9. 修复“清理战报”与“服务状态”容器选择器冲突及界面重复问题，实现专属服务状态与运行日志看板
- [x] 10. 修复运行日志中的 HTML 实体转义乱码；统一插件名称为「磁盘清理」；彻底修复非日志数据文件误截断并按容量降序重构战报明细展示
- [x] 11. 全面多国语言适配（补充分类描述、策略提示、战报列名、服务周期、合规说明等中英文及多语种）、弹框高度增高至 720px 保证 Disk Check 一屏完整展示、非中文菜单按钮缩写与防折行优化
