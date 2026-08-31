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

### 插件 i18n 与安全升级改造（第一阶段试点）
- `[x]` `op_waf` (功能复杂度最高)
  - `[x]` 更新 info.json 规范化 type
  - `[x]` 提取及生成 lang/zh-CN.json 与 lang/en.json
  - `[x]` 前端 js/op_waf.js 接入 YfPlugin.createApi，替换硬编码中文为 pt()
  - `[x]` 前端 index.html 增加 data-i18n 属性
  - `[x]` 后端 index.py 使用 yf.safeExecShell 杜绝注入，规范 yf.returnJson 消息
  - `[x]` 完成升级与测试
- `[x]` `mysql` (使用频率最高)
  - `[x]` 修正 info.json 的 type
  - `[x]` 提取 lang/zh-CN.json 词汇
  - `[x]` 前端 js/mysql.js 更换为 api.post / api.postSilent / api.postAsync 等标准接口
  - `[x]` 完成语法结构测试
- `[x]` `openresty` (底层基石)
- `[x]` 其他所有 38 个存量插件的自动化提取与标准化重构（已使用 `batch_upgrade.py` 一键完成）

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



## 第三阶段：插件国际化深度优化与架构重构 (完成)

- [x] 1. 回滚被污染的后端 Python 源码
- [x] 2. 编写高精度的自然语言提取引擎
- [x] 3. 自动化改造前端调用 (JS & HTML)
- [x] 4. 对所有 41 个存量插件进行终极清洗与测试。
## 第五阶段：首页状态图表与国际化显示 Bug 修复 (完成)

- [x] 1. 深度分析与定位 `web/static/app/index.js` 中负载状态与磁盘 Inode 状态显示的根本原因（自动国际化替换导致的语法与结构污染）。
- [x] 2. 补齐与同步 6 国语言包（zh-CN, zh-TW, en, fr, de, it）中缺失的首页状态词条（`inode_info`, `total`, `used`, `available`, `inode_usage`, `inode_usage_exceed`, `clean_up_trash`, `partition`, `when_the_usage_reaches`, `mem_warning`, `cpu_logical`）。
- [x] 3. 重构并修复 `web/static/app/index.js`：彻底纠正 `getLoad`（负载状态）、`getDiskInfo`（磁盘与 Inode 提示）、`showCpuTips`（CPU 提示）、`setMemImg`（内存状态）、`getInfo`（核心数显示）、`getGpuInfo`（GPU 提示）、`netImg`（网络 IO 图表）等模块。
- [x] 4. 编写全自动回归测试脚本 `test/test_index_status_i18n.py`，验证数据渲染、DOM 结构与 6 种语言下的文案完整性与正确性。
- [x] 5. 最终验证与清理临时脚本。


## 第七阶段：系统监控模块（Monitor）500 错误排查与前端国际化修复 (完成)

- [x] 1. 定位并修复 `web/templates/default/monitor.html` 中因双引号转义 `\"` 导致 Jinja2 模板编译抛出 `TemplateSyntaxError: unexpected char '\\'` 引发 500 Internal Server Error 的语法错误。
- [x] 2. 补齐并规范 6 国语言包中 `control` 命名空间缺失的词条（如 `enlarge_chart`, `the_chart_has_not`, `enlarge`, `loading_please_wait`, `processing_please_wait`, `did_you_really_delete`, `clear_history`, `unit_kb`, `unit_kb_1`, `number_of_bytes_read`, `number_of_bytes_written`, `load_details`, `minute`, `minutes` 等），重新编译生成标准的 `lan.js` 与 `template.json`。
- [x] 3. 重构并优化 `web/static/app/control.js`：将所有的 `lan && lan.control && t(...)` 调用规范化为 `(window.lan && lan.control && lan.control.key) || t('control.key', '默认值')`，防止未定义变量报错并保证多语言平滑回退。
- [x] 4. 编写全自动回归测试脚本 `test/test_monitor_i18n.py`，覆盖模板 Jinja2 编译、路由渲染、JS 语法及多语言词条校验。
- [x] 5. 验证并完成交付。

## 第八阶段：页面底部（Footer）多语言翻译与品牌规范统一 (完成)

- [x] 1. 完善后端 `web/core/i18n.py` 与前端 `web/static/app/i18n.js` 的默认文本回退与防裸键泄露机制，彻底杜绝未命中词条时界面显示 `brand_panel` / `brand_company` / `tools_box` 等键名。
- [x] 2. 规范 6 国语言包中品牌与页脚词条（御风统一对齐为 `Yufeng`，御风科技有限公司对齐为 `Yufeng Technology Co., Ltd.`）：
  - `common.brand_panel`: 御风面板 / 御風面板 / Yufeng Panel / Panneau Yufeng / Yufeng-Panel / Pannello Yufeng
  - `public.brand_company`: 御风科技 / 御風科技 / Yufeng Technology / Technologie Yufeng / Yufeng-Technologie / Tecnologia Yufeng
  - `public.ip_privacy_check`: IP隐私安全检测 / IP隱私安全檢測 / IP Privacy & Security Check / Test de confidentialité et sécurité IP / IP-Datenschutz- und Sicherheitsprüfung / Controllo privacy e sicurezza IP
  - `public.tools_box`: 御风工具箱 / 御風工具箱 / Yufeng Toolbox / Boîte à outils Yufeng / Yufeng-Toolbox / Strumenti Yufeng
  - `public.company_signature`: 衢州御风科技有限公司出品 / 衢州御風科技有限公司出品 / Produced by Quzhou Yufeng Technology Co., Ltd. / Produit par Quzhou Yufeng Technology Co., Ltd. / Präsentiert von Quzhou Yufeng Technology Co., Ltd. / Prodotto da Quzhou Yufeng Technology Co., Ltd.
  - `public.source_code`: 源码 / 源碼 / Source Code / Code source / Quellcode / Codice sorgente
- [x] 3. 运行编译器生成标准合法语法的 6 国 `lan.js` 与 `template.json`。
- [x] 4. 编写全自动回归测试脚本 `test/test_footer_i18n.py` 并运行完整测试套件验证。

## 第九阶段：首页系统详情与服务器性能/带宽测速全量多语言适配 (完成)

- [x] 1. 整理并同步 6 国语言包（zh-CN, zh-TW, en, fr, de, it）中系统详情（`showSystemDetails`）全量词条（操作系统、发行版、内核、架构、虚拟化、处理器、型号、核心线程、指令集、网络节点、TCP拥塞算法、负载平均、物理内存、Swap、磁盘容量等及其详细 Tooltip 说明）。
- [x] 2. 整理并同步 6 国语言包中服务器性能与带宽测速（`runSpeedTest` / `renderSpeedTestModal`）全量词条（系统基本信息、磁盘 I/O 读写性能、读写速度、多区域节点下载测速、基准说明、境外节点分割线、再次测试、环境初始化/排队/测试中/超时/已跳过状态等）。
- [x] 3. 重构 `web/static/app/index.js` 中的 `showSystemDetails`、`renderSpeedTestModal`、`triggerSpeedReTest`、`startRealNewTest` 及 `runLogPolling`，全部采用 `t('index.xxx', '中文默认')` 统一国际化驱动，彻底消除硬编码中文。
- [x] 4. 重新编译 6 种语言包生成合法合规的 `lan.js` 和 `template.json`。
- [x] 5. 编写自动化回归测试脚本 `test/test_system_details_speedtest_i18n.py` 并运行全量测试套件验证。

## 第十一阶段：测速弹窗「物理内存未知」与「磁盘空间描述」国际化修复 (完成)

- [x] 1. 优化 `scripts/speed.sh` 中内存获取逻辑，从 `/proc/meminfo` 的 `MemTotal` 直接计算 MB / GB，避免因不同系统 Locale 导致 `free -m` 匹配失败返回“未知”。
- [x] 2. 优化 `web/static/app/index.js`，增加 `formatMemString` 国际化格式化，使“未知”动态渲染为对应语言（如 English: `Unknown`, Français: `Inconnu` 等）。
- [x] 3. 增加 `formatDiskSizeString` 智能格式化函数，将“根分区共 38G, 已用 11G, 剩余 25G”通过 `index.disk_size_format` 动态翻译为对应语言（如 English: `Root 38G, Used 11G, Free 25G`，Français: `Racine 38G, Utilisé 11G, Libre 25G` 等）。
- [x] 4. 在 6 国语言包中同步更新 `index.disk_size_format` 与 `public.unknown`，重新编译生成 `lan.js` 与 `template.json`。
- [x] 5. 编写自动化测试 `test/test_mem_disk_i18n.py` 并通过全量回归测试套件验证。

## 第十二阶段：ESXi 虚拟机及全虚拟化环境物理内存高兼容性识别增强 (完成)

- [x] 1. 分析 ESXi / KVM / 容器 / 极简 Linux 环境下 `free` 命令缺失或输出异常原因。
- [x] 2. 改造 `scripts/speed.sh`：实现 `/proc/meminfo`、`free` 第二行第二列、`vmstat`、环境变量 `TOTAL_MEM_MB` 四级级联容灾识别，彻底杜绝“未知”。
- [x] 3. 改造 `web/admin/system/system.py`：在启动测速进程时将 Python `psutil` 精确物理内存通过环境变量 `TOTAL_MEM_MB` 注入子进程。
- [x] 4. 优化 `web/static/app/index.js`：当历史缓存或日志因旧版原因记录了“未知”时，自动联动当前会话已探明的真实内存数据进行智能自愈展示。
- [x] 5. 编写自动化测试脚本 `test/test_memory_compatibility.py` 并运行验证。

## 第十三阶段：软件管理页面菜单缩写、安装翻译与操作列多语言优化 (完成)

- [x] 1. 统一 6 国语言包中左侧菜单及相关词条（`menu.memuAsoft`、`menu.M9`、`menu.soft`）为精简词（en: `Software`，zh-CN: `软件`，zh-TW: `軟體`，fr: `Logiciels`，de: `Software`，it: `Software`），防止菜单折行。
- [x] 2. 规范 6 国语言包中 `public.install`、`public.uninstall`、`public.set`、`public.update`、`soft.install` 等核心按钮词条，清除带有引号转义的陈旧 hack 字符串。
- [x] 3. 重构 `web/static/app/soft.js` 中操作列（`handle`）生成逻辑，消除多余双引号符号 `"` 并使用标准的 `t()` 翻译驱动。
- [x] 4. 优化 `web/templates/default/soft.html` 表格操作列宽度（拓宽至 `150`），确保多语言下如 `Paramètres | Désinstaller` 或 `Settings | Uninstall` 单行优雅呈现。
- [x] 5. 重新编译 6 国语言包生成标准 `lan.js` 与 `template.json`。
- [x] 6. 编写自动化测试 `test/test_soft_i18n.py` 并全量回归验证。

## 第十四阶段：全部插件（Plugins）软件名称与介绍 6 国语言全量多语言适配 (完成)

- [x] 1. 扫描 `plugins/` 目录下全部 38 个有效插件（排除 `待审核` 目录），整理 `title` 与 `ps` 描述。
- [x] 2. 统一品牌词：所有“御风”统一规范翻译为 **`YuFeng`**。
- [x] 3. 为 6 种语言（zh-CN, zh-TW, en, fr, de, it）编写并录入全部 38 个插件的 `title` 和 `ps` 多语言词典至 `plugins` 命名空间。
- [x] 4. 重新编译 6 国语言包生成标准合规的 `lan.js` 与 `template.json`。
- [x] 5. 重构 `web/static/app/soft.js` 及首页软件展示模块，使用 `t('plugins.' + plugin.name + '.title', plugin.title)` 与 `t('plugins.' + plugin.name + '.ps', plugin.ps)` 实现无缝多语言渲染。
- [x] 6. 编写全覆盖自动化测试 `test/test_plugins_i18n.py` 并运行全量回归验证。

## 第十五阶段：修复多语言环境下 PHP 等多版本共存插件版本号丢失 Bug (完成)

- [x] 1. 深入分析多版本共存插件（`coexist: true`，如 `php`、`php-apt`、`php-yum`）与单实例插件（`coexist: false`）在多语言标题渲染时的版本拼接逻辑。
- [x] 2. 修复 `web/static/app/soft.js`：对 `coexist: true` 的插件动态拼接 `'-' + plugin.versions`（如 `PHP-5.6`、`PHP-8.1`），对单实例已安装插件保留 `plugin.setup_version`。
- [x] 3. 同步修复软件管理操作弹窗（`addVersion`、`softMain`、`uninstallVersion`）与首页快捷卡片（`softIndexList`）中的多语言版本标题传递。
- [x] 4. 编写自动化测试 `test/test_coexist_versions_i18n.py` 验证各语言下版本号完整呈现。

## 第十六阶段：左侧菜单栏多语言下拉框 UI 样式三项精细化优化 (完成)

- [x] 1. 调整高度：将多语言下拉框的高度由 30px 拓高至 42px，圆角 10px，与上方菜单项（44px）保持一致的视觉高度与比例。
- [x] 2. 缩短宽度与修复溢出：设置固定宽度 156px（在 180px 侧边栏内左右各留 12px 边距），彻底消除右侧超出边际的问题。
- [x] 3. 增大上下边距：增加上下外边距（`margin: 24px 12px 20px 12px`），与上方的“退出”菜单项及下方的快捷添加按钮拉开舒适的呼吸间距。
- [x] 4. 在 `site.css`、`ensite.css` 与 `layout.html` 中同步应用并进行全量自动化测试回归。
- [x] 5. 修复 `ensite.css` 中的 2 处语法错误（冒号写错分号）与 5 处属性/前缀告警，确保 IDE 诊断 0 报错。

## 第十七阶段：修复 phpMyAdmin 插件完整功能与多语言残留符号清理 (完成)

- [x] 1. 修复 `plugins/phpmyadmin/js/phpmyadmin.js` 中孤立的 `async` 语法错误，彻底解决 `ReferenceError: async is not defined`。
- [x] 2. 补全 `phpmyadmin.js` 中缺失的 `homePage()` 与 `phpVer(version)` 函数定义，彻底解决点击“主页”和“PHP版本”时报 `homePage is not defined`、`phpVer is not defined` 的问题。
- [x] 3. 全量清理 6 国语言包中历史旧版宝塔残留的 `')">` 等脏符号，彻底恢复“重启”、“重载配置”等按钮文字的纯净展示。
- [x] 4. 为 phpMyAdmin 定制专属操作指引说明卡片（重载配置与重启服务说明）与访问认证卡片（内网/外网地址、用户名密码），单层结构优雅整洁呈现，彻底杜绝重复嵌套。
## 第十八阶段：phpMyAdmin 强杀功能补充、弹窗菜单固定与配置输入框重复修复 (完成)

- [x] 1. 在 `phpmyadmin.js` 中，将特殊情况下“kill所有php进程”强杀按钮及红色运维警示卡片补充到【服务】面板“访问与认证信息”卡片下方。
- [x] 2. 重构 `site.css`、`ensite.css` 与 `soft.js` 中的弹窗布局：设置外层内容容器 `overflow: hidden`，左侧 `.bt-w-menu` 固定不随滚动条漂移，右侧 `.bt-w-con` 独立滚动。
- [x] 3. 彻底修复 `public.js` 中 `pluginConfig`、`pluginConfigTpl`、`pluginConfigListTpl` 函数因历史字符串拼接错误导致多出一个 `<textarea id="textBody">` 空白输入框的问题。
- [x] 4. 编写全量自动化测试套件 `test/test_phpmyadmin_plugin_fixes.py`，全量 12 个测试套件 38 个用例 100% 绿灯回归通过。
- [x] 5. 修复 `plugins/phpmyadmin/index.py` 中因 `path` 配置为空字符串导致访问 URL 出现 `//index.php` 遗漏安全子目录的问题，实现 `getPmaPath()` 自动感知与自愈探测。
- [x] 6. 深度优化 `plugins/phpmyadmin/index.py` 中 `config.inc.php` 配置文件与启动状态检测：当未设置子目录或直接位于根目录时，精准自愈定位 `/www/server/phpmyadmin/config.inc.php`，彻底解决启动报错“服务启动失败”及配置读取失败的问题。
- [x] 7. 对齐 master 分支安全机制，在 `getCfg()` 中引入随机保护子目录（`phpmyadmin_xxxxxx`）的主动感知与自动探测自愈机制，确保访问地址包含随机保护字符串并能正常访问网页。

## 第十九阶段：修复 CRLF 换行符导致的安装脚本语法错误与全量自愈防护 (完成)

- [x] 1. 全量扫描并清洗代码仓库中所有文本文件（Shell、Python、HTML、JS、CSS、Conf、JSON、TPL、MD、Lua等），统一将 CRLF 换行符转换为标准 LF（无 BOM UTF-8）。
- [x] 2. 完善 `.gitattributes` 配置，严格指定所有源码、脚本与资源文件在 Git 检出与提交时强制使用 `eol=lf`。
- [x] 3. 增强 `scripts/lib.sh` 与 `scripts/getos.sh` 等公共基础脚本，在执行系统识别前主动做 `\r` 字符过滤与自愈处理，防止意外由 Windows 传输引起的脚本语法异常。
- [x] 4. 优化 `panel_task.py` 后台任务执行引擎：在执行 Shell 任务时，支持自动检测并自愈目标脚本中的 Windows 回车符（`\r`），彻底杜绝 `$'\r': 未找到命令` 错误。
- [x] 5. 编写自动化回归测试脚本 `test/test_crlf_and_sh_syntax.py`，全量验证代码库换行符、Bash 脚本语法与自愈机制。

## 第二十阶段：修复消息盒子样式与DOM结构错误 (完成)

- [x] 1. 重构 `web/static/app/public.js`：清洗 `messageBox`、`tasklist`、`execLog`、`remind` 及 `getReloads` 中双重嵌套与错乱的 HTML 字符串，建立标准优雅的 DOM 结构与语义化多语言支持。
- [x] 2. 优化 `site.css` 与 `ensite.css`：为消息盒子增加专属的纵向 Flex 布局样式（`.msg-box-form`、`#msg_box_sys_info`），保证弹窗固定尺寸（680px*600px）下左侧固定、右侧独立滚动、底部状态栏自适应停靠。
- [x] 3. 清洗并更新国际化词典（`phrases_full.py`）及 6 种语言包，彻底清除 `public_auto_str_39` 等冗余脏数据并确保消息盒子词条完整无误。
- [x] 4. 编写全自动回归测试脚本 `test/test_message_box.py`，全量验证消息盒子 JS 语法、HTML 结构、Tab 切换逻辑及多语言词条。

## 第二十一阶段：修复 Docker 及全量插件前端 JS 语法错误与 API 签名多态兼容 (完成)

- [x] 1. 深度分析 Docker 插件前端报错根因：`function api.post(...)` 非法点号函数声明导致脚本解析失败（SyntaxError），进而导致 `dockerService` 未定义（ReferenceError）。
- [x] 2. 扫描并修复所有插件中遗留的非法点号函数声明语法错误（`docker.js`、`gitea.js`、`pgadmin.js`、`pureftp/ftp.js`、`sphinx.js`）。
- [x] 3. 增强 `web/static/app/plugin_api.js` 中 `YfPlugin.createApi` 请求方法，实现对多种参数签名（`(method, callback)`、`(method, args, callback)`、`(method, version, args, callback)`）的智能多态参数归一化处理。
- [x] 4. 编写全量插件与前端 JS 语法、函数定义及 API 兼容性自动化测试脚本 `test/test_all_plugins_js_syntax.py`。
- [x] 5. 运行全量测试套件确保 100% 绿灯回归通过。

## 第二十二阶段：排查并修复全仓库 Python 语法错误与 AST 编译校验 (完成)

- [x] 1. 全量扫描整个代码仓库中所有 248 个 Python 源码文件（包括 `plugins/`、`web/`、`scripts/` 等），进行 AST 语法树解析与字节码编译校验。
- [x] 2. 修复 `plugins/docker/index.py` 中 `checkDockerMigrateSpace` 遗留的字典语法错误（`{'required': '未知', 'available': '未知'}` 结构修复）。
- [x] 3. 优化 `plugins/mariadb/index_mariadb.py` 正则表达式字符串为 Raw String，消除 Python 3.12+ 的 SyntaxWarning。
- [x] 4. 编写全量 Python 语法与 AST 结构自动化回归测试 `test/test_all_python_syntax.py`，全量 63 个测试用例 100% 绿灯通过。






## 第二十一阶段：后台任务引擎 (panel_task.py) I/O 读写放大与性能优化

- [x] 1. 优化 xecShell，实现按时间差进行刷盘 (flush)，防止因高频按行刷盘引发的 I/O 风暴与安装任务阻塞。
- [x] 2. 优化 downloadFile 中的 downloadHook，引入基于进度差值或时间间隔的节流机制，防止产生每 8KB 数据即进行文件打开/关闭的灾难级性能消耗。

## 第二十二阶段：面板插件首页高频 I/O 消除

- [x] 1. 优化 web/utils/plugin.py 的 getIndexList，避免每次首页请求都进行 info.json 的重复磁盘 I/O 解析，改为使用内存级 getStaticPluginList 缓存加速查询。

## 第二十三阶段：首页 UI 细节优化

- [x] 1. 优化 `web/templates/default/index.html`，在软件列表标题右侧增加绿色的刷新小图标，实现点击立即刷新重载面板首页的软件状态。
- [x] 2. 精细化重构首页软件刷新按钮样式：使用 Flex 容器实现与“软件”标题绝对水平对齐，图标定制为现代主题翠绿风格，支持 Hover 浅绿微光悬浮态与 Active 物理按压下沉（下降）动画反馈，并加入平滑旋转动效。

## 第二十四阶段：全系统通用绿色刷新组件模块化提取与多页面复用

- [x] 1. 抽象并建立全局通用的现代化绿色刷新组件 CSS（`.btn-refresh-icon` 纯图标小按钮、`.yf-refresh-btn` 带文字图标按钮），支持浅绿微光 Hover 态、物理按压下沉（下降）Active 态与平滑 360° 旋转动效。
- [x] 2. 在全局公共库 `web/static/app/public.js` 中封装通用方法 `yfRefreshBtn(el, callback)` 并注册全页面自动事件委托。
- [x] 3. 在“网站管理”页面（`web/templates/default/site.html`）接入通用纯图标刷新按钮组件。
- [x] 4. 在“软件管理”页面（`web/templates/default/soft.html`）接入通用带文字图标刷新按钮组件。
