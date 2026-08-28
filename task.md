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

- `[x]` 46. 优化 `web/core/yf.py`：重构 `deleteFile` 函数，增加对 `os.path.islink` 的死软链接兼容并用 `try-except` 捕获异常，彻底消除 Gunicorn 与后台任务并发初始化的竞态 FileNotFoundError。
- `[x]` 47. 运行本地语法与编译校验，确保修改后的 `yf.py` 没有任何异常。

- `[x]` 48. 优化文件管理页面 (files.js)：修改复选框及其所在第一列单元格的点击逻辑，实现单击第一列单元格的任意空白区域即可勾选选中，且阻止事件冒泡以防触发行的排他性框选事件。

- `[x]` 49. 优化路径页样式 (`web/templates/default/path.html`)，要求专业性强，现代简约风格，并在右下角显示出品方：衢州御风科技有限公司。

- `[x]` 50. 修复本地终端 `ssh_local.py` 中 `connectSsh()` 的死锁问题与 `try-except` 异常重试逻辑，增加 `try...finally` 块释放锁。
- `[x]` 51. 修复本地终端 `ssh_local.py` 在连接本地 SSH 时，主动加载本地私钥以作凭证，并统一 `invoke_shell` 的本地化环境变量参数，解决特定服务器黑屏与连接失败问题。
- `[x]` 52. 对重构后的本地终端连接 and 读取逻辑进行验证测试。

- `[x]` 53. 优化 `ssh_local.py` 中 `connectSsh()` 连接目标顺序，优先请求自定义端口，将 22 端口移至兜底。
- `[x]` 54. 实现 `connectSsh()` 每次尝试连接独立实例化 `paramiko.SSHClient`，确保连接失败时其内部状态能够被干净关闭与清理，避免状态污染导致后续尝试失效。
- `[x]` 55. 再次在 Mock 脚本中验证多备用连接目标抛出 banner 异常时的状态清理和继续尝试流程。

- `[x]` 56. 重构 `ssh_local.py` 的 `connectSsh()` 支持输出详细连接节点、加载状态、连接目标和异常报错等调试日志至 Web 终端。
- `[x]` 57. 重构 `ssh_local.py` 的 `run(info)` 方法增加重试冷却（10s）与输入唤醒（有按键数据时立即重试）逻辑，避免报错刷屏。
- `[x]` 58. 通过编写的 Mock 测试用例验证 10s 冷却限频和即时唤醒的功能性。

- `[x]` 59. 在 `ssh_local.py` 的 `connectSsh()` 中引入本地 `authorized_keys` 授权公钥的精准第二列加密字符指纹比对与缺失自动追加写入。
- `[x]` 60. 在 `connectSsh()` 中引入对 `/root/.ssh`（700）及 `authorized_keys`（600）目录和文件的安全权限加固。
- `[x]` 61. 在 `ssh_local.py` 中 `ssh.connect()` 各个分支调用处显式指定 `username='root'`。
- `[x]` 62. 在 Mock 测试脚本中验证权限设定逻辑与参数传递是否正常。

- `[x]` 63. 在 `ssh_local.py` 的 `run(info)` 数据读取异常捕获中，通过 `exit_status_ready()` 对通道是否已经死亡进行精确判定，只在通道真死时重置 `self.__ssh = None`，保护正常的非阻塞读取超时。
- `[x]` 64. 对修改后的连接状态和读取进行最终测试与打包。

- `[x]` 65. 修改前端 `public.js`，重构 `server_response` 消息接收监听，过滤后端自定义调试前缀并在 Shell 真正就绪的时刻才安全地触发 `cd` 指令。
- `[x]` 66. 修改前端 `public.js`，在终端 Layer 弹窗的 `cancel` 回调事件中，通过 socket 主动向后端发送 `exit\r` 以注销并清理 SSH 会话进程。
- `[x]` 67. 在 Web 终端中验证首次及后续打开时自动 `cd` 目录功能。

- `[x]` 68. 修改 `web/admin/__init__.py`，在最顶部引入 RequestContext.session 兼容补丁以解决高版本 Flask 与老版本 flask_socketio 的 setter 写入异常。
- `[x]` 69. 编写 Mock 校验脚本测试 Monkey Patch 作用于 RequestContext.session 的可行性与读写正确性。

- `[x]` 70. 分析 `deploy.sh` 安装脚本的潜在错误与优化点，并提出修改建议。
- `[x]` 71. 分析面板在新装、迁移等场景下是否会获取当前用户位数，并排查不显示的原因。
- `[x]` 72. 实施 `deploy.sh` 脚本在用户位数、开发预览版判断、临时文件安全和 PostgreSQL 备份等 4 个维度的代码优化。
- `[x]` 73. 对 `deploy.sh` 脚本执行 shell 语法校验和本地模拟验证。
- `[x]` 74. 在 `index.py` 中重构数据初始化 (`initSiteInfo`)，将新站点 `allow_curl` 改为 `curl_protection` 默认开启，并支持老配置平滑迁移。
- `[x]` 75. 在 `index.py` 中重构 `getSiteConfig` 和 `getSiteConfigByName` 的配置获取与字段迁移写回。
- `[x]` 76. 在 `init.lua` 中重构 `waf_curl` 拦截方法，使其适配并依赖新字段 `curl_protection`，同时实现关闭时的完美放行。
- `[x]` 77. 在 `js/op_waf.js` 中重构站点详细配置 `siteWafConfig`，将 `curl` 开关移至顶部的防火墙开关旁，并删除底部原表格对应行。
- `[x]` 78. 运行本地验证流程，检查 Python 端和 Lua 端逻辑，以及配置迁移。
- `[x]` 79. 配合用户需求，将 `curl` 保护开关与列加回到站点配置主列表中，并顺带修复历史统计数据对齐的 Bug。
- `[x]` 80. 重构日志管理跳转逻辑：使站点配置中点击特定站点日志时能精准跳转、自动高亮侧栏，且下拉框默认选中该站点。

- `[x]` 81. 修改 `web/utils/plugin.py` 中 `init` 函数的默认推荐版本：OpenResty 1.31.1, PHP 80, phpMyAdmin 5.2.1。
- `[x]` 82. 修改 `web/static/app/index.js` 中的一键安装弹窗，配置 `skin: 'layui-layer-modern'` 并调整弹窗大小为 `["380px", "460px"]` 消除滚动条。
- `[x]` 83. 修改 `web/static/css/site.css` 和 `web/static/css/ensite.css`，重构推荐安装 UI 样式，包括警告框、卡片、列表项、下拉框、复选框和按钮，使其变成现代简约的设计，并彻底消除溢出滚动条。
- `[x]` 84. 验证推荐版本加载和弹窗样式表现是否符合预期。

- `[x]` 85. 优化 `web/static/app/index.js`，将一键安装弹窗的高度设为 `auto` 自适应以避免按钮被截断，同时将 `closeBtn` 从 `2` 改为 `1`，使关闭按钮置于标题栏右侧，布局更规整。
- `[x]` 86. 微调 `site.css` 和 `ensite.css` 中的样式，确保在自适应高度下，关闭按钮样式与新皮肤完美适配，且底部有充足的安全留白。
- `[x]` 87. 验证修改后的弹窗样式 and 高度是否在所有语言下都完全符合预期。

- `[x]` 88. 优化 `web/utils/plugin.py`，实现新服务器部署后系统已预装 fail2ban 防火墙的自动识别和自动接管逻辑（补齐面板所需的 `/www/server/fail2ban` 及 `version.pl` 等标识），解决已安装软件列表为空的体验问题。

- `[x]` 89. 优化安全管理中 SSH 允许 root 登录状态检测逻辑：只有当 PermitRootLogin 明确为 yes 时才显示为开启，其它未配置或非 yes 值一律显示为关闭。
- `[x]` 90. 运行本地 Python 语法编译校验，确保修改后的 firewall.py 没有任何异常。
- `[x]` 91. 优化 `plugins/php/lib/common_env.sh`：重构 `MEM_INFO` 获取逻辑，处理中文/英文环境下的 `free` 提取，并防范空值保护，避免“需要整数表达式”错误。
- `[x]` 92. 优化 `plugins/php/versions/80/install.sh`：重构 `MEM_INFO` 获取逻辑，防范空值，解决 PHP8.0 编译安装阶段的“需要整数表达式”警告。
- `[x]` 93. 优化 `plugins/php/install.sh`：配置 Composer 前，临时将当前安装的 PHP bin 目录加入到 `PATH` 中，解决 `composer` 报错 `/usr/bin/env: php: 没有那个文件或目录` 的问题。
- `[x]` 94. 优化 OpenResty 所有版本的安装脚本（1.17.8 - 1.31.1 以及 rtmp）：优化 Brotli 依赖克隆逻辑，改为优先使用 github_download 下载 tar.gz 并解压缩剥离首层，解压失败再回退到原 github_clone，同时优化错误判断，避免在依赖缺失时盲目继续编译。

- `[x]` 95. 优化系统安装脚本 `scripts/install/debian.sh`：引入 `smart_apt_install` 以实现系统依赖包的批量与智能降级安装，并前置 `apt update` 以防 404。
- `[x]` 96. 优化系统安装脚本 `scripts/install/ubuntu.sh`：引入 `smart_apt_install` 以实现系统依赖包的批量与智能降级安装，并前置 `apt update` 以防 404。
- `[x]` 97. 优化 Python 环境依赖安装脚本 `scripts/lib.sh`：修正国内环境下优先使用加速源，且在失败时支持降级使用官方源。
- `[x]` 98. 优化桌面概览中御风F2B底层防火墙的显示逻辑：在 `plugins/fail2ban/index.py` 的 `get_total_statistics` 方法中增加对 `/www/server/fail2ban` 目录是否存在的校验，确保仅在防火墙实际安装成功时才在前端首页显示概览卡片。

- `[x]` 99. 优化 WAF 插件 `index.py`，使读取 `default.pl`、`domains.json` 时进行 `.strip()` 过滤和 `try-except` 异常保护。
- `[x]` 100. 优化 WAF 插件前端 `op_waf.js`，在渲染时进行站点名称的 `trim()` 去空白，并在日志请求时为站点名参数提供默认 `'ALL'` 回退。

- `[x]` 101. 修复 Web 更新检查 `getServerInfo()` 在中国境内服务器始终失败及内容为空的 bug：GitHub 代理站不支持代理 `api.github.com`（返回 403），重构为通过代理利用 `releases/latest` 的 302 重定向获取最新 tag，并通过代理获取 `raw.githubusercontent.com` 上的 `RELEASE_TEMPLATE.md` 作为更新内容展示。若依然失败则提供包含 GitHub Release 链接的 Markdown 友好提示。
- `[x]` 102. 优化 Web 端的 Python 下载代理节点选优机制 (`yf.py/test_speed_bg`)：将原来的小文件延迟测速（Ping 测试）重构为利用 `master.tar.gz` 进行真实带宽测速（`speed_download`），并与 Bash 脚本对齐增加大于 3MB/s 提前退出的机制，解决默认获取到高延迟低带宽节点导致更新下载极慢的问题。
- `[x]` 103. 优化 `yf.githubDownload` 逻辑：下载大文件时强制阻塞等待（最多 10 秒）后台测速线程完成，确保完全命中测出的最优带宽节点后再进行下载，解决因“秒点”更新导致错过最优节点的问题。

- `[x]` 104. 优化 `plugins/pg_docker/index.html`：在实例列表操作列新增“修改配置”按钮，实现弹出 Layer 修改密码与宿主机端口的 UI 交互，并在成功后自动刷新列表。
- `[x]` 105. 优化 `plugins/pg_docker/index.py`：新增 `modify_config` 接口，支持通过 `docker exec psql` 安全修改容器内数据库密码，并同步修改 `docker-compose.yml` 中的环境变量和 `ports` 并通过 `docker compose up -d` 自动重启生效。
- `[x]` 106. 优化 `plugins/pg_docker/index.py`：在 `modify_config` 和 `create_instance` 中引入基于原生 `socket` 的宿主机端口占用检测，防止因端口冲突导致的容器启动失败。
- `[x]` 107. 优化 `plugins/pg_docker`：通过 `docker stats` 获取每个实例容器的 CPU 和内存资源占用，并在前端实例列表中追加徽章显示。

- `[x]` 108. 开发 `plugins/python_yf` 插件：创建基础目录、配置 `info.json` 元数据和 `install.sh` 安装卸载脚本，引入 `uv` 一键安装支持。
- `[x]` 109. 开发 `plugins/python_yf` 后端：编写 `index.py`，实现解析 `uv python list` 输出获取可用与已安装版本的方法，及触发安装/卸载后台任务。
- `[x]` 110. 开发 `plugins/python_yf` 前端：基于现有的卡片化设计规范编写 `index.html`，实现两个 Tab 分别展示可用版本和已安装版本并对接对应的操作接口。
- `[x]` 111. 开发联调与验证：在面板中进行实际安装、下载版本、卸载版本等功能的端到端测试，确保对面板主环境 0 影响。
- `[x]` 112. 优化 `plugins/python_yf/index.py`：引入 `venvs.json`，在 `get_python_list` 中返回虚拟环境的创建记录，并新增 `create_venv` 接口。
- `[x]` 113. 优化 `plugins/python_yf/index.html`：在前端“已安装版本”中添加“创建虚拟环境”按钮及弹窗，并展示该版本下的虚拟环境数量记录。
- `[x]` 114. 开发联调与测试虚拟环境的创建和 UI 展示。

- `[x]` 115. 优化 plugins/php/install.sh 中 Composer 安装逻辑：导出临时环境变量并优先从国内镜像直连下载压缩包，并增加文件生成校验保护防止出现系统级报错。
- `[x]` 116. 优化 plugins/php-apt/install.sh 中 Composer 安装逻辑（同 115）。
- `[x]` 117. 优化文件管理页面 (files.js)：调换“新建目录”与“新建空白文件”的位置，使“新建目录”排在首位。

### 解决 Gitea Docker 被 op_waf 防火墙拦截的问题
- `[x]` 分析拦截原因：url.json 规则拦截 .git 以及 POST 内容检测
  - `[x]` `#577` - add_host中需要验证网站目录是否包含了".." 等越权路径名
- `[x]` 开发统一的《插件统一开发规范》
  - `[x]` 定义多语言 i18n 规范和迁移策略
  - `[x]` 定义安全、稳定、性能要求
  - `[x]` 优化并确定插件统一 i18n 的核心辅助函数 `createPluginTranslator`，减少重复代码
  - `[x]` 新增前端统一请求封装 `YfPlugin.createApi()`，统一 loading、错误处理与参数格式化
  - `[x]` 新增后端防注入安全执行函数 `yf.safeExecShell()`
- `[x]` 撤销全局 url_white.json 对 .git 的放行，避免其他正常站点的源码泄露风险。
- `[x]` 确认 WAF 中影响 Git 的分类为 **GET**（URL规则限制 .git）和 **POST**（拦截 push 时的二进制 packfile）。
- `[x]` 建议用户在面板中对特定站点（git.yangmaok.*）进行独立配置。


### 解决 Git OAuth 登录被拦截的问题
- [x] 提出修复方案：建议将 OAuth 认证路径加入白名单，或直接针对 Git 站点关闭 GET 参数过滤。

### 解答用户关于计划任务日志中“空格变冒号”的疑问
- [x] 分析日志输出格式与 Bash `cd` 报错机制
- [x] 结论解答：并非空格被替换为冒号，而是 Bash 的标准错误输出格式 `cd: <目录>: No such file or directory`。实际原因是目标路径不存在。

### OpenResty Gzip 传输优化与通用性支持
- [x] 1. 分析 OpenResty Gzip 优化配置的通用性、原理及针对反向代理/预压缩文件生效的关键机制
- [x] 2. 更新 `plugins/openresty/conf/nginx.conf` 默认配置模板，将 `gzip_proxied any;` 与 `gzip_static on;` 纳入新安装默认配置
- [x] 3. 增强 `plugins/openresty/index.py` 中的 `confSelfHeal` 和 `setCfg`，支持自动自愈升级已有配置并在开启 gzip 时补全优化指令
- [x] 4. 编写自动化测试脚本并在 `test/` 目录下进行针对性测试验证
- [x] 5. 将 `plugins/openresty/conf/nginx.conf` 模板中的 `brotli` 默认改为 `on`，实现安装完成时默认自动开启 Brotli 与 Gzip 双压缩
- [x] 6. 更新 `plugins/openresty/index.py` 中的 `getCfg` 默认值及 `confReplace` 安全兼容逻辑
- [x] 7. 运行自动化测试用例验证新装与自愈流程

### 首页右下角增加“最近登录记录”模块
- [x] 1. 优化登录日志记录：在 `web/admin/dashboard/login.py` 中补充登录成功（常规登录、两步验证、安全路径）的日志写入。
- [x] 2. 增加后端数据接口：在 `web/admin/dashboard/dashboard.py` 中新增 `/get_recent_logins` 接口，解析并返回最近登录记录结构化数据。
- [x] 3. 扩展前端模板结构：在 `web/templates/default/index.html` 右侧流量图表下方添加“最近登录”卡片 DOM 结构。
- [x] 4. 编写前端动态渲染与交互：在 `web/static/app/index.js` 中新增 `getRecentLogins()` 函数，并接入流水线错峰加载。
- [x] 5. 补充与优化精致视觉样式：在 `web/static/css/site.css` 或样式定义中添加微表格、胶囊徽章与状态圆点样式。
- [x] 6. 编写自动化测试与全面验证：在 `test/` 目录下创建测试脚本并验证功能、数据格式及边界条件。
- [x] 7. 高度独立控制与无滚动条优化：卡片紧凑排版，标题栏与行高轻量化，避免首页出现纵向滚动条。
- [x] 8. 呈现最新的 5 次记录（支持 Web 和 SSH 方式）。
- [x] 9. 将表格“账号”列替换为“登录方式”（Web/SSH）专业徽章。
- [x] 10. 公网 IP 归属地解析（参考 op_waf pconline 接口）与浏览器 localStorage 本地缓存机制。
- [x] 11. 编写自动化测试用例并完成端到端验证。
- [x] 12. 首页卡片限制显示 3 行记录，高度独立控制（缩小至 ~115px），彻底消除首页垂直滚动条。
- [x] 13. 标题栏“更多日志 →”右对齐对齐优化。
- [x] 14. 点击“更多日志 →”弹出精致模态弹窗（Layer），支持完整记录展示、每页 10 条分页功能。
- [x] 15. 弹窗内支持状态（成功/失败）与方式（Web/SSH）多维条件组合筛选与快速刷新。
- [x] 16. 后端 `/get_recent_logins` 接口升级支持 `p`、`limit`、`status`、`method` 筛选及 `yf.getPage` 分页数据生成。
- [x] 17. 自动化测试脚本更新并进行端到端验证。
- [x] 18. 登录时间客户端时区自适应：后端返回 Unix 时间戳，前端根据浏览器本地时区动态转换为本地时间展示，并在 title 提示服务器原时间。
- [x] 19. 优化后端 IP 归属地获取：参考 `op_waf` 引入 `ip-api.com` 作为首选高可用解析方案，并将现有 `pconline` 作为后备方案（Fallback）。
- [x] 20. 优化前端 `index.js` 中的 IP 归属地本地缓存机制：增加未知结果的防污染和自愈逻辑。
- [x] 21. 编写自动化测试用例，全面验证国内外 IP 解析、降级逻辑及接口返回格式。
- [x] 22. 优化前端 `web/static/app/index.js`：引入基于 `sessionStorage` 的 SWR 会话级缓存与 60s 智能冷却机制，实现来回切换左侧菜单时 0ms 瞬间秒开且无闪烁。
- [x] 23. 优化登录与登出逻辑（`login.html` & `public.js`）：在用户新登录及退出登录时自动清除最近登录会话缓存，保证新登录后即时获取最新本地 IP 与最新日志。
- [x] 24. 验证菜单切换流畅度、冷却控制与新登录缓存自愈流程。

### op_waf 防火墙降低负载与稳定性性能优化
- [x] 25. 优化后台定时器频率（`init_worker.lua` & `waf_common.lua`）：调整过期日志清理为每小时、统计持久化为每30秒、日志异步入库为每3秒、CPU采样为每15秒，降低 80%+ 磁盘 I/O 争用。
- [x] 26. 优化防 CC 指纹计算（`init.lua`）：利用原生 C 级 `ngx.md5` 替代纯 Lua 循环 `hmac_sha256` 生成请求特征 key，大幅降低 CPU 计算消耗。
- [x] 27. 修复 GeoIP / MaxMindDB FFI 二级指针内存调用缺陷（`waf_maxminddb.lua`），彻底消除 Worker 崩溃闪退（Segfault）引起的系统负载波动。
- [x] 28. 优化蜜罐路径检测效率（`init.lua`），提升高频常规访问下的过滤吞吐。
- [x] 29. 编写端到端自动化测试脚本，全面验证 Lua 语法、安全规则拦截率、防 CC 频控、日志记录与稳定性。

### 御风面板多国语言版本（i18n）全套国际化升级（6 种语言）
- [x] 30. 创建 `lang.json` 与更新 `list.json`，定义 6 种支持语言（zh-CN, zh-TW, en, fr, de, it）元数据与名称映射。
- [x] 31. 提取并规范化主语言包（`zh-CN/`），制作并校验 `zh-TW/`（繁体中文）、`en/`（英文）、`fr/`（法文）、`de/`（德文）、`it/`（意大利文）全套多语言词库（含 `lan.js`、`public.json`、`template.json`、`log.json`）。
- [x] 32. 删除 `Simplified_Chinese/` 冗余目录，全面统一使用 `zh-CN`。
- [x] 33. 开发前端 i18n 核心模块 `web/static/app/i18n.js`，实现浏览器语言自动探测、Cookie/localStorage/URL 优先级解析、响应式语言切换与 `lan` 兼容代理。
- [x] 34. 开发后端 i18n 模块 `web/core/i18n.py` 与改造 `web/core/yf.py`，实现 `Accept-Language` 请求头智能解析、多语言 JSON 字典加载与 `returnMsg`/`returnData` 动态国际化支持。
- [x] 35. 改造 `web/admin/__init__.py`，注册 i18n 请求前置钩子及 Jinja2 全局变量注入（`t`, `current_lang`, `supported_languages`）。
- [x] 36. 改造 `web/admin/setting/setting.py`，增加 `/setting/set_language` 与 `/setting/get_languages` API 接口。
- [x] 37. 改造 `web/templates/default/layout.html` 与 `web/templates/default/login.html`，实现按当前语言动态引入 `lan.js`，并在顶部导航栏和登录页添加多语言快速切换器。
- [x] 38. 改造 `web/templates/default/setting.html` 与 `web/static/app/config.js`，在面板设置中增加“面板语言”选项。
- [x] 39. 编写全套自动化测试脚本 `test/test_i18n.py`，全面验证 6 语言字典完整性、键值对齐、浏览器语言探测与接口多语言返回。

### 前端 HTML 与 JS 文本全量国际化迁移（第二阶段 - 深度修补）
- [x] 40. 【HTML】全量双轨国际化（首页与概览、网站管理、文件与安全、监控、计划任务、软件等 HTML模板）。
- [x] 41. 【JS - 批次一】深度提取与重构 `web/static/app/index.js` 的中文硬编码，包括垃圾清理、测速及弹窗。
- [x] 42. 【JS - 批次一】深度提取与重构 `web/static/app/site.js` 的中文硬编码，包括网站设置各类复杂弹窗与防盗链向导。
- [x] 43. 【JS - 批次二】深度提取与重构 `web/static/app/public.js`、`web/static/app/config.js` 与 `web/static/app/crontab.js`。
- [x] 44. 【JS - 批次三】深度提取与重构 `web/static/app/files.js` 与 `web/static/app/firewall.js`。
- [x] 45. 【JS - 批次四】深度提取与重构 `web/static/app/control.js`、`web/static/app/soft.js`、`web/static/app/logs.js`、`web/static/app/upload.js`。
- [x] 46. 随批次同步扩充 `scripts/tools/phrases_full.py` 字典，并持续运行 `build_all_languages.py` 同步多语言包。
- [x] 47. 运行 `test/test_i18n.py` 及全自动化本地代码校验确保零异常。

### 后端 Python 消息全量国际化迁移（第三阶段）
- [x] 48. 【核心基础设施】增强 `web/core/yf.py` 与 `web/core/i18n.py`，支持 `returnData`、`returnMsg`、`returnJson` 传递动态格式化参数。
- [x] 49. 【后端 - 批次一】设置与仪表盘模块国际化（`web/admin/setting/*.py`, `web/admin/dashboard/*.py`）。
- [x] 50. 【后端 - 批次二】网站管理模块国际化（`web/utils/site.py`, `web/admin/site/*.py`）。
- [x] 51. 【后端 - 批次三】文件系统、防火墙与 SSH 模块国际化（`web/utils/file.py`, `web/utils/firewall.py`, `web/utils/ssh/*.py`, `web/admin/files/*.py`, `web/admin/firewall/*.py`）。
- [x] 52. 【后端 - 批次四】计划任务、插件、系统管理与日志审计国际化（`web/utils/crontab.py`, `web/utils/plugin.py`, `web/utils/system/*.py`, `web/admin/system/*.py`, `web/admin/crontab/*.py`, `web/admin/task/*.py`, `web/admin/logs/*.py`）。
- [x] 53. 【词典与构建】自动化工具提取新增后端 key 并同步更新 `phrases_full.py`，重新生成 6 语言包。
- [x] 54. 【测试与验证】运行 `test/test_i18n.py` 单元测试与 Python 语法检查，确保后端 API 返回 100% 正常。


