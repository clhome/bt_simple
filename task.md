# 面板前端UI/UX现代化优化任务

> 项目整体描述：优化御风面板前端界面，使用现代设计规范（卡片化、圆角、弥散阴影等），基于纯CSS和现有jQuery实现，不新增插件。
> 开发规范描述：KISS原则，优先复用项目中已有的函数和模块。无BOM UTF-8格式，LF换行符。不允许使用>或>>重定向。

## Task List

- `[x]` 1. 修改 `site.css`，引入现代化 CSS 变量（色彩、阴影、圆角），重置部分全局组件样式（按钮、输入框、滚动条等）。
- `[x]` 2. 改造 `layout.html` 全局框架，优化侧边栏样式及 hover 效果。
- `[x]` 3. 改造 `site.html`，实现真正的卡片化展示，重置表格无边框风格，增加按钮悬浮动画。
- `[x]` 4. 统一界面细节，优化部分内联样式并验证实际显示效果。
- `[x]` 5. 优化系统监控页面(`monitor.html` 和 `control.js`)，使其拆分为 6 个独立的图表（3列 x 2行），并消除滚动条。
- `[x]` 6. 为监控图表添加“放大”功能，通过模态弹窗(layer)单独展示选中的图表。
- `[x]` 7. 使用 jQuery 3.7.1 风格重构部分图表事件绑定，提升渲染和响应性能。
- `[x]` 8. 优化 `plugins` 目录下所有 `install.sh` 中的 `wget` 命令，添加 `-nv` (non-verbose) 参数以减少日志大小和 I/O 负担。
- `[x]` 9. 重命名 Python 核心公共库 `web/core/mw.py` 到 `yf.py`，并创建兼容桥接文件 `mw.py`。
- `[x]` 10. 重命名及重构部分零散的 Python 和 API 调试示例文件。
- `[x]` 11. 重构 Python 核心函数及别名（如 `mw_async`->`yf_async` 等），修改系统服务注册处的服务名称引用。
- `[x]` 12. 重构系统服务模板（`scripts/init.d/*.tpl`）：重命名文件并修改内部环境变量及进程匹配逻辑。
- `[x]` 13. 调整 `cli.sh` 终端输出，修改所有 Python 业务文件中的 `import mw` 和相关方法。
- `[x]` 14. 改造 `deploy.sh` 与安装升级脚本：实现环境监测、目录平滑迁移、兼容软链接创建等逻辑。
- `[x]` 15. 修复 `panel_tools.py` 中的 `INIT_CMD` 硬编码路径。
- `[x]` 16. 修复 `web/core/yf.py` 中 `restartTask` 和 `panelCmd` 的 `mw` 路径硬编码问题。
- `[x]` 17. 修复 `deploy.sh` 中更新数据库配置时的 `config` 表名拼写错误（改为 `option`）。
- `[x]` 18. 修复 Systemd 服务模板中的 `ExecStart` 路径以符合 Systemd 绝对路径规范并使用虚拟环境 Python。
- `[x]` 19. 优化 `deploy.sh` 中的 `start_panel` 与 `stop_panel` 逻辑，优先调用新服务。
- `[x]` 20. 清理 `web/branding.py` 中的 `APP_NAME` 为 `'yufeng_panel'`，并更新 `web/utils/php/fcgi_client.py` 中的日志路径。
- `[x]` 21. 编写代码清理脚本，全局统一 `import core.yf as mw` 和 `import mw` 的别名为 `yf`，并替换相关代码中的 `mw.` 调用。
- `[x]` 22. 清理 `panel_tools.py` 及其它地方硬编码的 `mw_xxx = yf_xxx` 等向下兼容别名。
- `[x]` 23. 全局执行替换脚本并进行校验，确保 0 报错，消除 `DeprecatedProxy` 的性能损耗。
- `[x]` 24. 性能优化：替换 `yf.py` 中的原生系统调用（`execShell("cp/rm")` 改为 `shutil`/`os`）
- `[x]` 25. 性能优化：解决 `site.py` 递归文件遍历中的耗时查询（提前获取 `uid`/`gid`）
- `[x]` 26. 性能优化：在 `db.py` 中引入内存缓存以优化 SQLite 表结构查询 (`PRAGMA table_info`)
- `[x]` 27. 性能优化：实现服务重载（Nginx）去抖动机制，避免频繁阻塞
- `[x]` 28. 性能优化：在 `yf.py` 中增加大文件尾部读取函数 `readFileEnd`
- `[x]` 29. 优化 `deploy.sh`：引入 `get_latest_release_tag` 辅助函数，优先通过 API + 代理获取最新正式版 tag，并以 `git ls-remote` 作为兜底，解决开发预览版注入时由于网络问题导致的 `-dev` 版本号抓取错误。
- `[x]` 30. 优化 `deploy.sh` 的测速效率：在 `download_code` 和 `check_version_and_update` 函数开头在父 Shell 中提前执行测速以缓存 `_GH_BEST_PROXY`，避免子 Shell 运行导致重复测速。
- `[x]` 31. 优化 `deploy.sh` 迁移回滚逻辑与统一命名：在部署时将 `deploy.sh` 写入面板目录，将回滚命令提示改为以固定的绝对路径指向新部署 of `/www/server/yufeng_panel/deploy.sh`，且函数名及参数统一重命名为 `yufeng_panel` / `rollback_yf`。
- `[x]` 32. 安全优化：改进 `web/admin/__init__.py` 中的 CSRF 拦截逻辑，通过准确提取 Host 校验 Referer/Origin，阻断空 Referer 与子串欺骗绕过。
- `[x]` 33. 安全优化：修复 `web/thisdb/temp_login.py` 中的 `(now_time)` 非元组传参，并为 `web/core/db.py` 里的 `where` 方法添加对非元组/列表入参的安全兼容包装。
- `[x]` 34. 安全优化：修改 `deploy.sh` 中对 `_gh_deploy_lib` 的写入路径，使用 `mktemp -d` 专属目录防范 `/tmp` 软链接本地竞争提权风险。
- `[x]` 35. 性能优化：为 `web/thisdb/option.py` 引入内存级的 Option 全局配置项缓存，减少高频 SQLite 读盘操作。
- `[x]` 36. 性能优化：清除 `panel_task.py` 中的原生系统调用（替换 `touch`、`rm` 及部分外部进程杀死命令为 Python 原生原生调用或 `shell=False` 的 `subprocess` 调用）。

- `[x]` 37. 优化 `deploy.sh`：引入全局 `INIT_D_SCRIPT` 变量，实现 `/etc/rc.d/init.d/yf` 与 `/etc/init.d/yf` 的动态识别，消除非 CentOS 系统上的启动报错。
- `[x]` 38. 优化 `deploy.sh` 迁移回滚函数 `rollback_yufeng_panel`：移除兼容软链接并物理重命名恢复 `/www/server/mdserver-web` 目录物理路径，实现完美的物理回滚。
- `[x]` 39. 优化 `deploy.sh` 迁移回滚函数 `rollback_yufeng_panel`：在解压老版代码后，动态使用 `sed` 补丁老版 `monitor.py` 中 `int(None)` 引起的崩溃 bug，并确保能正确使用原服务的 init 脚本启动。
- `[x]` 40. 优化 `panel_tools.py`：动态判断 `INIT_DIR` 目录是否存在，使各种维护指令在 Ubuntu 等系统上能正常调用正确的系统服务脚本。
- `[x]` 41. 优化 `deploy.sh` 中的 `start_panel` 启动函数与软链接重建，使其优先使用正确绝对路径启动，并使用 rm -f && ln -sf 强力覆盖并创建新链接，防止旧死链接阻碍。

- `[x]` 42. 优化 `scripts/github_download.sh`：将直连加入测速首位，增加大于 3MB/s 提前退出，改写下载和 API 获取逻辑以消除盲目超时等待。
- `[x]` 43. 优化 `deploy.sh` 脚本：适配测速返回为 `"direct"` 的情况，处理 `get_github_url`、`setup_china_git_config` 以及 `install_acme` 的调用逻辑。
- `[x]` 44. 优化 `web/core/yf.py` 脚本：调整 Python 端代理列表及测速模块，使其支持直连测速并消除盲目直连等待。
- `[x]` 45. 对修改后的 Shell 脚本与 Python 逻辑进行测试验证。
