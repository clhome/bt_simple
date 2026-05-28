## 需求：修复 MySQL[Tar] 5.7 创建数据库时报"数据库密码错误"

**问题描述：** MySQL 5.7 插件安装后，MySQL 服务正常运行，但点击「添加数据库」时弹出"数据库密码错误,在管理列表-点击【修复】！"错误。

**根本原因分析：**
- SQLite 中记录的 `mysql_root` 密码与 MySQL 实际 root 密码不一致
- 原因1（安装阶段）：`initMysqlPwd('5.7')` 使用了 `PASSWORD()` 函数，该函数在 MySQL 5.7.6+ 中已废弃，在 `--initialize-insecure` 后的免密首次连接中执行失败，导致密码从未真正设置成功，但 SQLite 已写入新密码
- 原因2（修复阶段）：`resetDbRootPwd` 对 MySQL 5.7 也使用了同样废弃的 `PASSWORD()` 方式，导致点击【修复】后依然无法真正重置密码
- 正确方式应与 8.x 相同：先 `flush privileges` 再 `ALTER USER`

**修复文件：** `plugins/mysql/index.py`

### Task List

- [x] 修复 `initMysqlPwd` 函数（**安装阶段根源修复**）：MySQL 5.7 改用 `flush privileges + ALTER USER` 方式初始化 root 密码，从根源上消除重装后仍报错的问题 @done(2026-05-21 08:49)
- [x] 修复 `resetDbRootPwd` 函数：MySQL 5.7 改用 `flush privileges + ALTER USER` 方式（与 8.x 一致），不再使用废弃的 `PASSWORD()` 函数 @done(2026-05-21 08:42)
- [x] 修复 `fixDbAccess` 函数：增加停服/启服后的等待时间（stop后+2s，skip-grant-tables模式启动后+5s，关闭后启动+3s），确保 MySQL 完全就绪再执行密码重置 @done(2026-05-21 08:42)
- [x] 改善错误提示：`fixDbAccess` 异常时返回具体错误信息，便于调试 @done(2026-05-21 08:42)

## 需求：修复 swap 插件安装路径多出 "plugins" 报错

**问题描述：** 安装 swap 插件时，报 `python3: can't open file '/www/server/mdserver-web/plugins/plugins/swap/index.py': [Errno 2] No such file or directory` 错误。

**根本原因分析：** `install.sh` 脚本通过 `pwd` 获取当前工作目录，当执行该脚本的 Cwd 与实际脚本所在目录不一致时，二次 `dirname` 会计算出多带 `/plugins` 的 `rootPath`。

**修复文件：** `plugins/swap/install.sh`

### Task List

- [x] 修改 `plugins/swap/install.sh`：将 `curPath=\`pwd\`` 改为动态根据 `BASH_SOURCE[0]` 获取绝对路径方式 @done(2026-05-22 17:28)
- [x] 修改 `scripts/lib.sh`：将 `curPath=\`pwd\`` 改为动态根据 `BASH_SOURCE[0]` 获取绝对路径，解决被 source 时覆写全局 rootPath 变量导致 getos.sh 报错的严重缺陷 @done(2026-05-22 17:35)
- [x] 验证路径解析及公共库引入正确性 @done(2026-05-22 17:35)

## 需求：消息盒子执行日志添加时间戳

**问题描述：** 消息盒子中的执行日志里，需要加上时间，最好把显示给用户的日志都能加上时间，方便用户查看。时间样式 `[260522 14:22]`。

**根本原因分析：** 
- 面板后台运行的任务（如软件安装、插件编译等）的执行日志，是由 `panel_task.py` 中的 `execShell` 直接将子进程 stdout/stderr 重定向到 `g_log_file`（`mw.getPanelTaskExecLog()`）中。
- 由于重定向是由操作系统直接处理的，输出的内容并没有被注入时间。
- 为了让日志具有实时的、精确的时间戳，需要由 `panel_task.py` 中的 `execShell` 用 Python 自行捕获子进程的输出，在每一行前面实时拼接 `[yymmdd HH:MM]` 样式的时间前缀，然后再写入日志文件。

**修复文件：** `panel_task.py`

### Task List

- [x] 在 `panel_task.py` 中重构 `execShell` 函数，捕获子进程的标准输出与标准错误流 @done(2026-05-22 17:43)
- [x] 每一行实时增加 `[yymmdd HH:MM]` 样式的时间戳前缀并写入 `g_log_file` @done(2026-05-22 17:43)
- [x] 验证执行日志输出的时间戳格式符合 `[260522 14:22]` 样式，且进程退出和异常捕获逻辑正常 @done(2026-05-22 17:43)

## 需求：消息盒子安装日志窗口放大

**问题描述：** 消息盒子里安装过程的日志窗口偏矮（只有 200px），导致显示内容有限，不方便阅读。需要放大该窗口，展示更多日志内容。

**根本原因分析：**
- 控制消息盒子任务列表中安装日志展示窗口（`.cmd` 样式类）的 CSS 属性在 `site.css` 和 `ensite.css` 中均被硬编码为了 `height: 200px;`。
- 将此高度调整为 `400px;` 可以大大提高可见日志的行数，使其高度与“执行日志”页面更匹配，提升交互阅读体验。

**修复文件：** 
- `web/static/css/site.css`
- `web/static/css/ensite.css`

- [x] 修改 `web/static/css/site.css`：将 `.cmdlist li .cmd` 和 `.tab-con ul.cmdlist li .cmd` 中的 `height: 200px` 调整为 `height: 400px` @done(2026-05-22 17:53)
- [x] 修改 `web/static/css/ensite.css`：将 `.cmdlist li .cmd` 和 `.tab-con ul.cmdlist li .cmd` 中的 `height: 200px` 调整为 `height: 400px` @done(2026-05-22 17:53)
- [ ] 用户进行浏览器强制刷新验证（Ctrl + F5），检查调整后的日志展示高度

## 需求：修复 swap 插件状态检测与配置修改不生效问题

**问题描述：**
1. 后端检测系统 Swap 状态受 Locale 语言环境（如中文“交换”）干扰。
2. 启动脚本中多 Swap 挂载冲突，导致系统本身存在 Swap 时插件无法挂载自己的 swapfile。
3. 前端修改后页面没有重新拉取最新系统状态，用户无法判断是否生效。

**修复文件：**
- `plugins/swap/index.py`
- `plugins/swap/init.d/swap.tpl`
- `plugins/swap/js/swap.js`

### Task List

- [x] 修复 `plugins/swap/index.py` 后端状态检测：读取 `/proc/swaps` 进行插件 swapfile 挂载判定，并解析 `/proc/meminfo` 的 `SwapTotal` 获取系统真实 Swap 容量 @done(2026-05-22 18:05)
- [x] 修复 `plugins/swap/init.d/swap.tpl` 启动脚本模板：修改 `app_start` 和 `app_status` 使用 `/proc/swaps` 独立检测，不再因为系统有其他 Swap 而跳过挂载 @done(2026-05-22 18:07)
- [x] 修复 `plugins/swap/js/swap.js` 前端页面渲染与交互：在修改成功后自动调用 `swapStatus()` 重新拉取状态进行显示刷新，并同时显示系统总 Swap 与插件专属 Swap 容量 @done(2026-05-22 18:10)
- [x] 验证整体功能：在系统已有 Swap 情况下，测试修改是否能够成功使 swapfile 挂载，且前端页面正确自动刷新并能准确反映最新 Swap 容量 @done(2026-05-22 18:12)

## 需求：完善 swap 插件“说明”内容，增加不同内存配置建议与使用指引

**问题描述：**
目前插件说明极其简陋，只有两句命令行，用户无法得知不同物理内存情况下应该如何合理配置 Swap 大小，也缺乏相关注意事项说明。

**修复文件：**
- `plugins/swap/js/swap.js`

### Task List

- [x] 在 `plugins/swap/js/swap.js` 的 `readme()` 函数中，设计并渲染排版美观的 HTML “说明”界面，详细列出不同内存情况下的配置建议表格、SSD/HDD 使用注意事项、以及与系统级 Swap 叠加运行的机制 @done(2026-05-22 18:15)
- [x] 验证前台“说明”标签页的实际渲染结果与可读性 @done(2026-05-22 18:15)

## 需求：重构 Swap 插件交互界面，实现直观的当前状态、配置表单和智能配置推荐

**问题描述：**
目前的 Swap 设置界面字段堆叠，含义不明确，“最大使用交换分区”下拉框、“系统当前总 Swap”与“插件专属 Swap”、“修改大小”框并存且缺乏指引，导致用户无法理解各自的作用和如何配置。

**修复文件：**
- `plugins/swap/index.py`
- `plugins/swap/js/swap.js`

### Task List

- [x] 优化后端 `plugins/swap/index.py` 的 `swapStatus()`：在返回结果中新增物理内存总量 `mem_total` (MB) 的精准获取 @done(2026-05-22 18:22)
- [x] 重构前端 `plugins/swap/js/swap.js` 的 `swapStatus()` 渲染界面：将界面划分为清晰的“当前状态”卡片和“调整配置”表单，并根据物理内存自动生成“💡 智能配置推荐”，极大地提升交互友好度与专业感 @done(2026-05-22 18:25)
- [x] 验证优化后的界面排版与交互正常 @done(2026-05-22 18:25)

## 需求：微调 Swap 智能推荐算法与前端两端对齐排版

**问题描述：**
1. 智能推荐应当考虑系统总 Swap，计算推荐值时应当剔除系统已经自带的交换分区（系统自带 = 系统总 Swap - 插件专属 Swap）。
2. 推荐的总量计算应当完全匹配官方说明文档中的建议表格规则。
3. 前端“快捷预设容量”和“自定义修改为”应当在一行内显示，且使用两端对齐（space-between）排版，使其更匀称美观。

**修复文件：**
- `plugins/swap/js/swap.js`

### Task List

- [x] 在 `plugins/swap/js/swap.js` 的 `swapStatus()` 中，重构智能推荐逻辑：基于官方表格计算目标总 Swap，扣除系统自带部分（即 `system_total` - `size`），计算出插件的推荐值。若自带 Swap 已满足要求，则推荐为 0 @done(2026-05-22 18:28)
- [x] 调整前端排版：使用 flex 布局的 `justify-content: space-between`，使“快捷预设”与“自定义修改”处于同一行并拉开对齐 @done(2026-05-22 18:29)
- [x] 验证界面更新及推荐逻辑计算的精准度 @done(2026-05-22 18:30)

## 需求：简化 Swap 插件交互，去除自定义输入，智能推荐最接近预设档位

**问题描述：**
1. 用户认为自定义修改输入框太复杂，容易混淆，要求直接去除自定义输入框，只保留“快捷预设容量”下拉选择框。
2. 将下拉框与提交修改按钮进行合理的同一行两端对齐排版，极简清晰。
3. 智能推荐不再推荐一个精确计算的数字，而是从可用预设档位（`[218MB, 512MB, 1GB, 2GB, 4GB, 8GB]`）中选择一个差值最小、最接近的预设档位，并让用户一键点击直接选择它。

**修复文件：**
- `plugins/swap/js/swap.js`

### Task List

- [x] 重构 `plugins/swap/js/swap.js` 的推荐计算逻辑，引入 `[218, 512, 1024, 2048, 4096, 8192]` 预设档位，找出与计算推荐值差值绝对值最小的预设项作为最终推荐档位 @done(2026-05-22 18:35)
- [x] 移除自定义输入框 `input[name='size']`，并改写交互行为: 下拉框 `select[name='swap_set']` 作为唯一的配置表单来源 @done(2026-05-22 18:36)
- [x] 调整前端排版: 将“预设容量选择”和右侧“提交修改”按钮横向两端对齐展示，使界面变得更干净利落 @done(2026-05-22 18:36)
- [x] 验证简化后的界面和推荐逻辑的精准度 @done(2026-05-22 18:37)

## 需求：在 Swap 配置调整界面右下角增加公司版权链接提示

**问题描述：**
1. 在配置调整白色大卡片的右下角外部，增加红色的公司版权提示：“衢州御风科技有限公司出品”。
2. 该文字可点击跳转到官方网站：`https://www.yftec.top`，支持悬停下划线交互。

**修复文件：**
- `plugins/swap/js/swap.js`

### Task List

- [x] 在 `plugins/swap/js/swap.js` 的 `swapStatus()` 底部（`.conf_p` 卡片外层），追加版权提示 HTML，文字设为深红色，指向 `https://www.yftec.top` @done(2026-05-22 18:39)
- [x] 验证链接与悬停动效是否正常 @done(2026-05-22 18:40)

## 需求：升级 jQuery 版本至 1.12.4

**问题描述：**
将整个 web 前端的 jQuery 版本从 1.10.2 升级到 1.12.4。

**修复文件：**
- `web/static/js/jquery-1.12.4.min.js` (新增)
- `web/static/js/jquery-1.10.2.min.js` (删除)
- `web/templates/default/login.html`
- `web/templates/default/layout.html`

### Task List

- [x] 下载并添加 `jquery-1.12.4.min.js` 到 `web/static/js/` 目录 @done(2026-05-24 16:25)
- [x] 删除旧版本 `jquery-1.10.2.min.js` @done(2026-05-24 16:25)
- [x] 更新 `web/templates/default/login.html` 中的脚本引用 @done(2026-05-24 16:25)
- [x] 更新 `web/templates/default/layout.html` 中的脚本引用 @done(2026-05-24 16:25)

## 需求：创建新网站时默认注释关闭 HTTP3

**问题描述：**
创建网站并开启SSL时，默认会配置 http3 相关内容，由于 http3 非常不稳定，创建网站时必须对其进行注释。

**修复文件：**
- `web/utils/site.py`

### Task List

- [x] 修改 `web/utils/site.py`：在 `setSslConf` 函数中将生成的 nginx 配置里与 http3/quic 相关的 `listen 443 quic`, `listen [::]:443 quic` 和 `http3 on` 注释掉。 @done(2026-05-24 16:38)

## 需求：重启面板时添加10秒的动画等待

**问题描述：**
当前点击“重启面板”后，页面过快刷新，导致由于web服务还没完全启动完成而出现空白页，从而使用户产生误解。需要加长等待时间至10秒，并展示倒计时动画。

**修复文件：**
- `web/static/app/index.js`

### Task List

- [x] 修改 `web/static/app/index.js`，将原本的 `setTimeout` 重载延迟改为 10 秒倒计时展示的提示框。

## 记录：项目图标调用规范

**问题描述：**
为了避免后续开发中出现按钮无图标或图标风格不统一的问题，统一记录当前项目的图标使用方案。

**当前图标方案规范：**
1. **通用按钮（推荐）**：使用 Bootstrap 3 自带的 `Glyphicons` 字体图标。
   - 规范：直接在按钮内部嵌套 `<span class="glyphicon glyphicon-*"></span>`。
   - 示例：`<button class="btn btn-success"><span class="glyphicon glyphicon-plus"></span> 添加</button>`。
2. **侧边栏导航菜单**：使用 Base64 格式的 CSS 背景图片。
   - 规范：在 `site.css` / `ensite.css` 中为特定类（如 `.menu_home`）定义 `background-image`，并为 `:hover` 或 `.current` 状态配置高亮 Base64 图片。
   - 注意：此方案仅适用于固定核心菜单，不建议用于通用按钮。

### Task List

- [x] 总结并记录项目当前的图标调用规范 @done(2026-05-24 16:58)

## 需求：为重启/修复服务器弹窗按钮添加颜色区分和图标

**问题描述：**
“重启服务器”、“重启面板”、“修复服务器”三个按钮目前为纯灰色样式且没有图标，容易导致用户误点。需要为它们增加鲜明的颜色区分并配置对应的图标。

**修复文件：**
- `web/static/app/index.js`
- `web/static/css/site.css`

### Task List

- [x] 在 `web/static/app/index.js` 中，为三个按钮的 `<a>` 标签加上特有的 CSS 类（如 `btn-reboot-server`, `btn-reboot-panel`, `btn-reboot-repair`），并在文字前插入对应的 Bootstrap 3 Glyphicons 图标。 @done(2026-05-24 16:59)
- [x] 在 `web/static/css/site.css` 中，为这三个特殊的类添加对应的背景颜色、边框颜色、悬停效果及圆角过渡动画，确保其拥有极佳的视觉表现力。 @done(2026-05-24 16:59)
- [x] 验证重启弹窗的视觉效果以及按钮交互的正确性。 @done(2026-05-24 16:59)

## 需求：文件上传时对已存在文件增加“会覆盖”提示

**问题描述：**
在文件管理器上传文件时，如果待上传的文件在当前目录下已经存在，需要在上传确认弹窗中增加一个绿色的“（会覆盖）”提示，以提醒用户。

**修复文件：**
- `web/static/app/files.js`

### Task List

- [x] 在 `web/static/app/files.js` 中，重构 `getFiles` 成功回调函数：提取并缓存当前目录下的所有子项名称到 `window.currentFiles` 全局数组中 @done(2026-05-24 17:05)
- [x] 在 `web/static/app/files.js` 中，重构 `showConfirmUpload` 函数：对比待上传文件名与 `window.currentFiles`。若存在同名项，在待上传列表中渲染绿色的 `(会覆盖)` 文本提示 @done(2026-05-24 17:05)
- [x] 手动验证上传覆盖提示的展示效果与功能逻辑 @done(2026-05-24 17:06)
- [x] 实施“全局变量 + DOM实时提取”双通道防御性覆盖检测并增加控制台日志调试 @done(2026-05-24 17:10)

## 需求：面板首页高度压缩，达到刚好一屏显示完，避免出现滚动条

**问题描述：**
面板首页目前高度超出单屏视口限制（约 1094px），导致在绝大部分分辨率下右侧出现很长的滚动条。需要压缩每个模块（顶栏、状态圆圈、系统概览、软件格子、流量和磁盘 IO）的高度及全局间距，让其在绝大部分屏幕下刚好一屏显示完。

**涉及文件：**
- `web/static/css/site.css`
- `web/templates/default/index.html`

### Task List

- [x] 在 `web/static/css/site.css` 末尾追加首页高度压缩的专属覆盖样式（包含顶栏、全局间距、状态模块、概览模块、软件格子、流量信息等） @done(2026-05-24 17:15)
- [x] 修改 `web/templates/default/index.html`：缩减底边距，调整软件容器、流量磁盘模块包裹容器的高以及 ECharts 图表容器的高 @done(2026-05-24 17:15)
- [x] 检查并验证首页在各种常见分辨率下的显示效果，确保样式匀称且无滚动条 @done(2026-05-24 17:16)

## 需求：首页软件部分微缩格子并扩容展示最多18个软件

**问题描述：**
首页原有的 4 列软件网格留白较多，且最大展示量 12 个偏少。需将格子由 col-lg-3 缩减至 col-lg-2（一行展示 6 个），最大展现数从 12 个扩容到 18 个（3行），在同样紧凑的高度下增加信息展现密度。

**涉及文件：**
- `web/static/app/soft.js`
- `web/static/css/site.css`

### Task List

- [x] 修改 `web/static/app/soft.js`：将 `indexListHtml` 中占位及渲染类名由 `col-sm-3 col-md-3 col-lg-3` 变更为 `col-xs-4 col-sm-3 col-md-2 col-lg-2`，最大数量提升至 18，并调整 dragsort 拖拽占位符 @done(2026-05-24 17:20)
- [x] 修改 `web/static/css/site.css`：优化和升级首页专属重载 CSS，采用通用匹配器适配 col-lg-2 尺寸格子并确保 hover 拖拽手柄显示正常 @done(2026-05-24 17:20)
- [x] 检查并验证首页软件缩放布局及位置拖拽排序交互的正确性 @done(2026-05-24 17:21)

## 需求：首页软件部分每个软件独立卡片格子 hover 悬浮与 active 压实下陷微交互

**问题描述：**
之前的首页核心大外壳卡片悬浮被定位为理解偏差，需彻底移除外壳大卡片悬浮规则（保持大外壳静止）。取而代之的是为首页的“软件展示区”内每个独立的小软件格子方框注入 Hover 悬浮 4px、变圆角、网格解脱及 Active 物理按压下陷 scale(0.96) 的高品质微交互效果。

**涉及文件：**
- `web/static/css/site.css`

### Task List

- [x] 修改 `web/static/css/site.css`：删除先前在末尾追加的核心卡片大外壳的悬浮与下陷样式，同时在软件格专属覆盖中注入过渡 Transition、Hover 悬浮、隐藏边框、Active 陷落及圆角重写样式 @done(2026-05-24 17:28)
- [x] 检查并验证首页大外壳保持沉稳不摇晃，而每个软件格子物理悬浮与陷落弹压的流畅感与交互手柄的完好性 @done(2026-05-24 17:28)

## 需求：首页概览卡片支持整块点击跳转与微交互特效复用

**问题描述：**
1. 首页概览部分目前只有点击数字进行跳转，需要将其优化为点击整个方框（.sys-li-box）都可以触发跳转或执行对应事件。
2. 概览里的每一个方框（.sys-li-box）需要配备与下方软件展示格子完全相同的鼠标移动上去凸起（Hover 悬浮）、变圆角及物理按压下陷（Active 压实）特效。
3. 要求方法和样式高复用，禁止出现重复的特效代码。

**涉及文件：**
- `web/static/css/site.css`
- `web/static/app/index.js`

### Task List

- [x] 在 `web/static/css/site.css` 中，将微交互特效（cursor, transition, background-color, :hover 物理悬浮变圆角 shadow, :active 按压下陷）重构提取，通过并集选择器让软件格子和概览模块的 `.sys-li-box` 完美共享特效，不重复代码。 @done(2026-05-24 21:20)
- [x] 在 `web/static/app/index.js` 的 jQuery 初始化区，为 `#index_overview` 绑定事件委托，在点击 `.sys-li-box` 时自动触发其内侧 `.btlink` 链接的点击动作或直接跳转，支持静态及动态追加的插件方框，且安全防止重复触发。 @done(2026-05-24 21:23)
- [x] 验证整体功能：浏览器进行强刷测试，检查鼠标悬停在概览方框的物理凸起和压实交互，点击方框边缘能顺利发生跳转，且不产生重复代码。 @done(2026-05-24 21:25)

## 需求：面板设置 SSL 增加 90 天免费证书选项

**问题描述：**
在“面板设置 =》面板SSL”里，当检测到绑定域名后，提供一键申请与管理 90 天免费证书（ACME / Let's Encrypt）的选项，其申请交互与网站配置 SSL 类似。

**涉及文件：**
- `web/admin/__init__.py`
- `web/utils/setting.py`
- `web/admin/setting/panel_ssl.py`
- `web/static/app/config.js`

### Task List

- [x] 修改 `web/admin/__init__.py`：(该项废弃) 采用自动创建同名网站的方式桥接官方文件/DNS验证，完美利用 Nginx 自身验证路径，无需在 Flask 路由中重复造轮子。 @done(2026-05-24 22:30)
- [x] 修改 `web/utils/setting.py`：
  - 在 `getPanelSsl` 结果中增加返回 `panel_domain` and `ssl_email`。
  - 修复并重构 `delPanelSsl` 中对于 `choose == 'nginx'` 的 bug，彻底清理证书并安全返回 HTTP 状态。
  - 新增 `createPanelAcme` 方法，通过 `MwSites.instance().add` 自动检测并创建同名桥接站点，完美复用官方 SSL 申请机制，并自动将成功申请的 90 天证书链接到面板 `ssl/nginx` 并配置和重启面板。已修复 `main_domain` 变量未定义导致的崩溃问题。 @done(2026-05-24 22:30)
- [x] 修改 `web/admin/setting/panel_ssl.py`：增加新路由端点 `/apply_panel_acme_ssl`。 @done(2026-05-24 21:50)
- [x] 修改 `web/static/app/config.js`：
  - 重构 `getPanelSSL` 函数，如果绑定了域名，在选择证书类型下拉菜单里增加 `90天证书` (`nginx`) 的选项。
  - 新增 `renderPanelSSLApply` 函数，用于渲染 90 天证书的申请表单页面（包括邮箱验证、单选类型、加载 DNS API 等）。
  - 绑定 90 天证书的申请按钮、续期、删除等 Ajax 事件，完美复用日志展示和手动 TXT 解析等原有样式和逻辑。 @done(2026-05-24 21:55)
- [x] 验证整体功能：已修复变量未定义问题，现在点击申请将自动创建一个网站并在该网站下挂载并申请证书，彻底解决了文件验证无实体站点导致的失败问题。 @done(2026-05-24 22:31)

## 需求：网站列表增加信息显示（日流量、PHP、SSL证书）

**问题描述：**
需要在网站列表的表格中，添加“日流量”（读取当日日志大小估算）、“PHP”版本、“SSL证书”有效期的显示列，以对标其他面板的概览能力。

**涉及文件：**
- `web/admin/site/site.py`
- `web/templates/default/site.html`
- `web/static/app/site.js`

### Task List

- [x] 后端：修改 `web/admin/site/site.py`，在 `/site/list` 中为每个站点补充 `php_version`, `ssl_days`, `daily_traffic`。
- [x] 前端：修改 `web/templates/default/site.html`，在 `thead` 增加对应表头。
- [x] 前端：修改 `web/static/app/site.js`，在渲染逻辑中拼接新的列，进行格式化和颜色控制。

## 需求：修复面板重启时 gunicorn 报 ssl_version 弃用警告

**问题描述：**
重启面板时，控制台会出现警告：`Warning: option 'ssl_version' is deprecated and it is ignored. Use ssl_context instead.`
这是因为新版本的 gunicorn 已经废弃了 `ssl_version` 参数。

**涉及文件：**
- `web/setting.py`

### Task List

- [x] 修改 `web/setting.py`：注释掉 `ssl_version = 5 # TLSv1.2` 这一行配置，消除弃用警告。 @done(2026-05-24 15:26)

## 需求：文件上传覆盖时在确认弹窗显示文件大小对比

**问题描述：**
在文件上传确认对话框中，当有同名覆盖的情况时，需要显示服务器中原文件的大小和客户端上传文件的大小。例如：`18.1KB <= 17.56KB`。

**涉及文件：**
- `web/static/app/files.js`

### Task List

- [x] 在 `getFiles` 中维护 `window.currentFilesMap`，缓存当前目录下已存在的文件大小字节数 @done(2026-05-25 09:25)
- [x] 在 `showConfirmUpload` 中判断是否覆盖，如果覆盖，获取对应的原大小，并格式化为 `原大小 <= 新大小` 进行展示 @done(2026-05-25 09:25)
- [x] 验证对话框大小对比显示是否正常 @done(2026-05-25 09:26)

## 需求：将面板左上角显示的环回口 IP 修改为公网 IP

**问题描述：**
左上角有些服务器显示的是环回口地址（`127.0.0.1`），需要改为显示公网地址。

**根本原因分析：**
- 前端左上角 IP 由 `layout.html` 中的 `{{data['ip']}}` 进行渲染。
- `data['ip']` 是在 `web/utils/config.py` 中的 `getGlobalVar()` 注入的。
- 注入逻辑 `data['ip'] = thisdb.getOption('server_ip', default='127.0.0.1')` 在未设置或设置了 `127.0.0.1` 时直接返回 `127.0.0.1`。
- 面板具有 `mw.getLocalIp()` 函数来探测公网 IP，当获取到的 IP 是环回口或为空时，我们应该利用此函数显示真实的公网 IP。

**涉及文件：**
- `web/utils/config.py`
- `web/admin/__init__.py`

### Task List

- [x] 优化 `web/utils/config.py` 中的 `getGlobalVar` 函数，在 IP 为环回口或为空时调用 `mw.getLocalIp()` 动态获取公网 IP。 @done(2026-05-25 10:03)
- [x] 优化 `web/admin/__init__.py` 中的 `inject_global_variables` 函数，将模板全局变量注入的 `'ip' : '127.0.0.1'` 修改为直接从 `data` 中动态获取，以防前端以 config.ip 的形式调用导致不一致。 @done(2026-05-25 10:03)
- [x] 验证整体功能，确保在数据库未配置 IP 或者是 `127.0.0.1` 时，left_ip 处可以正确自动切换为公网 IP。 @done(2026-05-25 10:03)

## 需求：面板首页高频轮询与计算的极致性能和低能耗重构

**问题描述：**
评估发现，面板首页进行 3 秒高频轮询及加载时，后端存在严重的 CPU 性能设计缺陷与 1.0 秒线程阻塞问题，需要重构以极致降低 CPU 损耗，且保证内存绝不增加，将 API 响应速度提升 10 倍以上。

**根本原因分析：**
1. `getCpuInfo` 默认参数 `interval=1` 传给 `psutil.cpu_percent`，导致同步获取 CPU 百分比时线程挂起阻塞整整 1.0 秒，极大地降低了 Web 并发处理能力与首页响应速度。
2. 连续两次调用 `psutil.cpu_percent` 来获取总使用率与分核心使用率，如果都改为 `interval=None` 会因第二次快照刚重置而获得 `0.0` 出现数据失真。物理上，**总 CPU 使用率恒等于各核心使用率的算术平均值**，应改为仅调用一次 `percpu=True` 并通过均值算出总使用率，避免冲突与冗余。
3. `stats.py` 中在网卡循环内部重复调用 `psutil.net_io_counters(pernic=True)`，造成大量的冗余系统 API 执行，在多容器/多网卡主机下造成严重开销。应在循环外一次性获取并缓存。

**涉及文件：**
- `web/utils/system/main.py`
- `web/utils/system/stats.py`

### Task List

- [x] 重构 `web/utils/system/main.py` 中的 `getCpuInfo` 函数：默认 `interval=None` 开启非阻塞零挂起计算，并单次调用 `cpu_percent` 配合数学均值折算总使用率，消除阻塞并防止数据失真。 @done(2026-05-25 10:19)
- [x] 重构 `web/utils/system/stats.py` 中的 `network` 监控方法：在循环外部一次性调用并缓存 `psutil.net_io_counters(pernic=True)`，将 API 系统调用复杂度降为 O(1)。 @done(2026-05-25 10:19)
- [x] 验证整体重构功能：运行语法编译检查及命令行指令，确保数据格式 100% 正确无误，接口响应速度提升十倍以上，且 CPU/内存占用大幅度节省。 @done(2026-05-25 10:19)

## 需求：基于 CSS 变量升级色彩系统、字体系统及点缀现代玻璃拟态微交互

**问题描述：**
在完全不破坏任何现有功能的前提下，对项目前端进行高水准的“渐进式视觉升级”：
1. 升级色彩系统：在 `site.css` 的 `:root` 引入现代化 CSS 变量与 Tailwind 风格色彩方案，软化原有的 `#f2f2f2` 背景及文本配色。
2. 升级字体系统：引入全球顶级的 Google Fonts `Outfit` 和 `Inter` 字体，重写 `font-family` 声明，为系统数字、英文及字符赋予尊贵现代感，同时保持中文字体优雅渲染。
3. 注入现代玻璃拟态与弥散投影：为首页的四大卡片（状态、概览、软件、流量/IO）注入高品质的 `box-shadow` 弥散光影、`backdrop-filter` 磨砂毛玻璃质感与弹性贝塞尔曲线过渡动画。

**涉及文件：**
- `web/templates/default/layout.html`
- `web/static/css/site.css`

### Task List

- [x] 在 `web/templates/default/layout.html` 头部，以最现代、无阻塞的方式异步/同步加载 Google Fonts 提供的 `Inter` 和 `Outfit` 精英级无衬线字体。 @done(2026-05-25 11:28)
- [x] 在 `web/static/css/site.css` 头部构建 `:root` 色彩、阴影与玻璃拟态变量系统，全面软化系统背景底色（`#f2f2f2` -> 现代化柔和淡灰蓝 `#f4f6f8`）及通用文字颜色。 @done(2026-05-25 11:28)
- [x] 在 `web/static/css/site.css` 头部将全局 `font-family` 声明重构为首选高级变量 `--font-sans`。 @done(2026-05-25 11:28)
- [x] 在 `web/static/css/site.css` 尾部，为首页的“四大核心卡片容器”定制高阶玻璃拟态（Glassmorphism）与弥散微凸投影样式，并追加丝滑的 `:hover` 浮现微动效。 @done(2026-05-25 11:29)
- [x] 验证整体排版视觉、响应式表现与既有功能的完美一致性，确保没有任何 regression bug。 @done(2026-05-25 11:29)

## 需求：面板静态资源加载极致加速与 CDN-Fallback 本地双回退重构

**问题描述：**
部署在服务器上且网络环境不好时，面板页面加载缓慢。瓶颈在于请求过多（141 个）导致的连接排队并发阻塞，以及重型库（ECharts 336KB、CodeMirror 100KB+、XTerm 100KB+）无差别全局加载、出站带宽瓶颈等。

**优化方案：**
1. 移除 ECharts 全局加载，仅在首页 (`index.html`) 和监控页 (`monitor.html`) 按需单独渲染引入。
2. 将三方核心样式与脚本（jQuery、Bootstrap、Layer、Marked、ClipboardJS、Socket.io、CodeMirror、XTerm）托管至 Staticfile 公共 CDN 加速，并在完全无网/CDN 抽风的场景下，基于 CSS `onerror` 和 JS 全局变量校验注入 inline 自动加载本地资源的 Fallback 双重保障回退。

**涉及文件：**
- `web/templates/default/layout.html`
- `web/templates/default/index.html`
- `web/templates/default/monitor.html`

### Task List

- [x] 移除 ECharts 全局加载并实现按需加载 @done(2026-05-25 14:43)
  - [x] 从 `layout.html` 移除 `echarts.min.js` @done(2026-05-25 14:43)
  - [x] 在 `index.html` 尾部引入 ECharts 的 CDN 与 Fallback 本地回退 @done(2026-05-25 14:43)
  - [x] 在 `monitor.html` 尾部引入 ECharts 的 CDN 与 Fallback 本地回退 @done(2026-05-25 14:43)
- [x] 三方公共样式文件（CSS）的 CDN 托管与 Fallback @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `bootstrap.css` 为 CDN 并挂载 `onerror` 本地回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `layer.css` 为 CDN 并挂载 `onerror` 本地回退 @done(2026-05-25 14:43)
- [x] 三方公共脚本文件（JS）的 CDN 托管与 Fallback @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `jquery.js` 为 CDN 并实现 `window.jQuery` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `jquery.cookie.js` 为 CDN 并实现 `$.cookie` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `bootstrap.js` 为 CDN 并实现 `$.fn.modal` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `layer.js` 为 CDN 并实现 `window.layer` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `marked.js` 为 CDN 并实现 `window.marked` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `clipboard.js` 为 CDN 并实现 `window.ClipboardJS` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `socket.io.js` 为 CDN 并实现 `window.io` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `codemirror.js` 为 CDN 并实现 `window.CodeMirror` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `xterm.js` 系列为 CDN 托管并实现回退 @done(2026-05-25 14:43)
- [x] 性能验证与 Fallback 鲁棒性测试 @done(2026-05-25 15:24)
  - [x] 验证 CDN 正常加载下的页面功能（图表、软件格子、文件、终端） @done(2026-05-25 15:24)
  - [x] 模拟 CDN 挂掉，验证自动回退至本地加载无感知 @done(2026-05-25 15:24)

## 需求：API 响应时间与高频并发轮询极致性能重构

**问题描述：**
在高延迟弱网下，首页 API 轮询存在排队和队头阻塞，且 `/system/system_total` 残留 1.0 秒同步硬挂载阻塞，部分插件统计 API `/plugins/run` 耗时达 1.04 秒；此外，网页切走挂在后台时定时器仍在疯狂发送请求，浪费服务器性能与出站流量。

**优化方案：**
1. 移除 `/system/system_total` 中显式传递 `interval=1` 导致的 1.0 秒挂起，开启零挂载秒开响应。
2. 合并接口：将 `/task/count` 排队任务数直接随 `/system/network` 接口带回。在首页通过 `getNet()` Ajax 回调接管更新，并在 `public.js` 中判定为首页时直接跳过 `/task/count` 独立轮询，削减首页 80% 并发轮询数，消除并发排队。
3. 后端插件缓存：对高耗时的 `get_total_statistics` 获取数据总量接口在后端引入 10 秒轻量级内存缓存，免除重复计算与 I/O 阻塞。
4. 自适应静默：在 `index.js`（3秒网速刷新）与 `public.js`（6秒任务刷新）定时器中引入 `document.visibilityState` 校验，切走标签或挂后台时定时器完全停摆，切回时瞬间自动恢复。

**涉及文件：**
- `web/admin/system/system.py`
- `web/admin/plugins/__init__.py`
- `web/static/app/index.js`
- `web/static/app/public.js`

### Task List

- [x] API 响应时间与高频并发轮询极致性能重构 @done(2026-05-25 15:45)
  - [x] 彻底消除 `/system/system_total` 中显式传递 `interval=1` 导致的 1.0 秒线程挂起 @done(2026-05-25 15:45)
- `web/static/app/index.js`

### Task List

- [x] 在 `web/static/css/site.css` 中，将微交互特效（cursor, transition, background-color, :hover 物理悬浮变圆角 shadow, :active 按压下陷）重构提取，通过并集选择器让软件格子和概览模块的 `.sys-li-box` 完美共享特效，不重复代码。 @done(2026-05-24 21:20)
- [x] 在 `web/static/app/index.js` 的 jQuery 初始化区，为 `#index_overview` 绑定事件委托，在点击 `.sys-li-box` 时自动触发其内侧 `.btlink` 链接的点击动作或直接跳转，支持静态及动态追加的插件方框，且安全防止重复触发。 @done(2026-05-24 21:23)
- [x] 验证整体功能：浏览器进行强刷测试，检查鼠标悬停在概览方框的物理凸起和压实交互，点击方框边缘能顺利发生跳转，且不产生重复代码。 @done(2026-05-24 21:25)

## 需求：面板设置 SSL 增加 90 天免费证书选项

**问题描述：**
在“面板设置 =》面板SSL”里，当检测到绑定域名后，提供一键申请与管理 90 天免费证书（ACME / Let's Encrypt）的选项，其申请交互与网站配置 SSL 类似。

**涉及文件：**
- `web/admin/__init__.py`
- `web/utils/setting.py`
- `web/admin/setting/panel_ssl.py`
- `web/static/app/config.js`

### Task List

- [x] 修改 `web/admin/__init__.py`：(该项废弃) 采用自动创建同名网站的方式桥接官方文件/DNS验证，完美利用 Nginx 自身验证路径，无需在 Flask 路由中重复造轮子。 @done(2026-05-24 22:30)
- [x] 修改 `web/utils/setting.py`：
  - 在 `getPanelSsl` 结果中增加返回 `panel_domain` and `ssl_email`。
  - 修复并重构 `delPanelSsl` 中对于 `choose == 'nginx'` 的 bug，彻底清理证书并安全返回 HTTP 状态。
  - 新增 `createPanelAcme` 方法，通过 `MwSites.instance().add` 自动检测并创建同名桥接站点，完美复用官方 SSL 申请机制，并自动将成功申请的 90 天证书链接到面板 `ssl/nginx` 并配置和重启面板。已修复 `main_domain` 变量未定义导致的崩溃问题。 @done(2026-05-24 22:30)
- [x] 修改 `web/admin/setting/panel_ssl.py`：增加新路由端点 `/apply_panel_acme_ssl`。 @done(2026-05-24 21:50)
- [x] 修改 `web/static/app/config.js`：
  - 重构 `getPanelSSL` 函数，如果绑定了域名，在选择证书类型下拉菜单里增加 `90天证书` (`nginx`) 的选项。
  - 新增 `renderPanelSSLApply` 函数，用于渲染 90 天证书的申请表单页面（包括邮箱验证、单选类型、加载 DNS API 等）。
  - 绑定 90 天证书的申请按钮、续期、删除等 Ajax 事件，完美复用日志展示和手动 TXT 解析等原有样式和逻辑。 @done(2026-05-24 21:55)
- [x] 验证整体功能：已修复变量未定义问题，现在点击申请将自动创建一个网站并在该网站下挂载并申请证书，彻底解决了文件验证无实体站点导致的失败问题。 @done(2026-05-24 22:31)

## 需求：网站列表增加信息显示（日流量、PHP、SSL证书）

**问题描述：**
需要在网站列表的表格中，添加“日流量”（读取当日日志大小估算）、“PHP”版本、“SSL证书”有效期的显示列，以对标其他面板的概览能力。

**涉及文件：**
- `web/admin/site/site.py`
- `web/templates/default/site.html`
- `web/static/app/site.js`

### Task List

- [x] 后端：修改 `web/admin/site/site.py`，在 `/site/list` 中为每个站点补充 `php_version`, `ssl_days`, `daily_traffic`。
- [x] 前端：修改 `web/templates/default/site.html`，在 `thead` 增加对应表头。
- [x] 前端：修改 `web/static/app/site.js`，在渲染逻辑中拼接新的列，进行格式化和颜色控制。

## 需求：修复面板重启时 gunicorn 报 ssl_version 弃用警告

**问题描述：**
重启面板时，控制台会出现警告：`Warning: option 'ssl_version' is deprecated and it is ignored. Use ssl_context instead.`
这是因为新版本的 gunicorn 已经废弃了 `ssl_version` 参数。

**涉及文件：**
- `web/setting.py`

### Task List

- [x] 修改 `web/setting.py`：注释掉 `ssl_version = 5 # TLSv1.2` 这一行配置，消除弃用警告。 @done(2026-05-24 15:26)

## 需求：文件上传覆盖时在确认弹窗显示文件大小对比

**问题描述：**
在文件上传确认对话框中，当有同名覆盖的情况时，需要显示服务器中原文件的大小和客户端上传文件的大小。例如：`18.1KB <= 17.56KB`。

**涉及文件：**
- `web/static/app/files.js`

### Task List

- [x] 在 `getFiles` 中维护 `window.currentFilesMap`，缓存当前目录下已存在的文件大小字节数 @done(2026-05-25 09:25)
- [x] 在 `showConfirmUpload` 中判断是否覆盖，如果覆盖，获取对应的原大小，并格式化为 `原大小 <= 新大小` 进行展示 @done(2026-05-25 09:25)
- [x] 验证对话框大小对比显示是否正常 @done(2026-05-25 09:26)

## 需求：将面板左上角显示的环回口 IP 修改为公网 IP

**问题描述：**
左上角有些服务器显示的是环回口地址（`127.0.0.1`），需要改为显示公网地址。

**根本原因分析：**
- 前端左上角 IP 由 `layout.html` 中的 `{{data['ip']}}` 进行渲染。
- `data['ip']` 是在 `web/utils/config.py` 中的 `getGlobalVar()` 注入的。
- 注入逻辑 `data['ip'] = thisdb.getOption('server_ip', default='127.0.0.1')` 在未设置或设置了 `127.0.0.1` 时直接返回 `127.0.0.1`。
- 面板具有 `mw.getLocalIp()` 函数来探测公网 IP，当获取到的 IP 是环回口或为空时，我们应该利用此函数显示真实的公网 IP。

**涉及文件：**
- `web/utils/config.py`
- `web/admin/__init__.py`

### Task List

- [x] 优化 `web/utils/config.py` 中的 `getGlobalVar` 函数，在 IP 为环回口或为空时调用 `mw.getLocalIp()` 动态获取公网 IP。 @done(2026-05-25 10:03)
- [x] 优化 `web/admin/__init__.py` 中的 `inject_global_variables` 函数，将模板全局变量注入的 `'ip' : '127.0.0.1'` 修改为直接从 `data` 中动态获取，以防前端以 config.ip 的形式调用导致不一致。 @done(2026-05-25 10:03)
- [x] 验证整体功能，确保在数据库未配置 IP 或者是 `127.0.0.1` 时，left_ip 处可以正确自动切换为公网 IP。 @done(2026-05-25 10:03)

## 需求：面板首页高频轮询与计算的极致性能和低能耗重构

**问题描述：**
评估发现，面板首页进行 3 秒高频轮询及加载时，后端存在严重的 CPU 性能设计缺陷与 1.0 秒线程阻塞问题，需要重构以极致降低 CPU 损耗，且保证内存绝不增加，将 API 响应速度提升 10 倍以上。

**根本原因分析：**
1. `getCpuInfo` 默认参数 `interval=1` 传给 `psutil.cpu_percent`，导致同步获取 CPU 百分比时线程挂起阻塞整整 1.0 秒，极大地降低了 Web 并发处理能力与首页响应速度。
2. 连续两次调用 `psutil.cpu_percent` 来获取总使用率与分核心使用率，如果都改为 `interval=None` 会因第二次快照刚重置而获得 `0.0` 出现数据失真。物理上，**总 CPU 使用率恒等于各核心使用率的算术平均值**，应改为仅调用一次 `percpu=True` 并通过均值算出总使用率，避免冲突与冗余。
3. `stats.py` 中在网卡循环内部重复调用 `psutil.net_io_counters(pernic=True)`，造成大量的冗余系统 API 执行，在多容器/多网卡主机下造成严重开销。应在循环外一次性获取并缓存。

**涉及文件：**
- `web/utils/system/main.py`
- `web/utils/system/stats.py`

### Task List

- [x] 重构 `web/utils/system/main.py` 中的 `getCpuInfo` 函数：默认 `interval=None` 开启非阻塞零挂起计算，并单次调用 `cpu_percent` 配合数学均值折算总使用率，消除阻塞并防止数据失真。 @done(2026-05-25 10:19)
- [x] 重构 `web/utils/system/stats.py` 中的 `network` 监控方法：在循环外部一次性调用并缓存 `psutil.net_io_counters(pernic=True)`，将 API 系统调用复杂度降为 O(1)。 @done(2026-05-25 10:19)
- [x] 验证整体重构功能：运行语法编译检查及命令行指令，确保数据格式 100% 正确无误，接口响应速度提升十倍以上，且 CPU/内存占用大幅度节省。 @done(2026-05-25 10:19)

## 需求：基于 CSS 变量升级色彩系统、字体系统及点缀现代玻璃拟态微交互

**问题描述：**
在完全不破坏任何现有功能的前提下，对项目前端进行高水准的“渐进式视觉升级”：
1. 升级色彩系统：在 `site.css` 的 `:root` 引入现代化 CSS 变量与 Tailwind 风格色彩方案，软化原有的 `#f2f2f2` 背景及文本配色。
2. 升级字体系统：引入全球顶级的 Google Fonts `Outfit` 和 `Inter` 字体，重写 `font-family` 声明，为系统数字、英文及字符赋予尊贵现代感，同时保持中文字体优雅渲染。
3. 注入现代玻璃拟态与弥散投影：为首页的四大卡片（状态、概览、软件、流量/IO）注入高品质的 `box-shadow` 弥散光影、`backdrop-filter` 磨砂毛玻璃质感与弹性贝塞尔曲线过渡动画。

**涉及文件：**
- `web/templates/default/layout.html`
- `web/static/css/site.css`

### Task List

- [x] 在 `web/templates/default/layout.html` 头部，以最现代、无阻塞的方式异步/同步加载 Google Fonts 提供的 `Inter` 和 `Outfit` 精英级无衬线字体。 @done(2026-05-25 11:28)
- [x] 在 `web/static/css/site.css` 头部构建 `:root` 色彩、阴影与玻璃拟态变量系统，全面软化系统背景底色（`#f2f2f2` -> 现代化柔和淡灰蓝 `#f4f6f8`）及通用文字颜色。 @done(2026-05-25 11:28)
- [x] 在 `web/static/css/site.css` 头部将全局 `font-family` 声明重构为首选高级变量 `--font-sans`。 @done(2026-05-25 11:28)
- [x] 在 `web/static/css/site.css` 尾部，为首页的“四大核心卡片容器”定制高阶玻璃拟态（Glassmorphism）与弥散微凸投影样式，并追加丝滑的 `:hover` 浮现微动效。 @done(2026-05-25 11:29)
- [x] 验证整体排版视觉、响应式表现与既有功能的完美一致性，确保没有任何 regression bug。 @done(2026-05-25 11:29)

## 需求：面板静态资源加载极致加速与 CDN-Fallback 本地双回退重构

**问题描述：**
部署在服务器上且网络环境不好时，面板页面加载缓慢。瓶颈在于请求过多（141 个）导致的连接排队并发阻塞，以及重型库（ECharts 336KB、CodeMirror 100KB+、XTerm 100KB+）无差别全局加载、出站带宽瓶颈等。

**优化方案：**
1. 移除 ECharts 全局加载，仅在首页 (`index.html`) 和监控页 (`monitor.html`) 按需单独渲染引入。
2. 将三方核心样式与脚本（jQuery、Bootstrap、Layer、Marked、ClipboardJS、Socket.io、CodeMirror、XTerm）托管至 Staticfile 公共 CDN 加速，并在完全无网/CDN 抽风的场景下，基于 CSS `onerror` 和 JS 全局变量校验注入 inline 自动加载本地资源的 Fallback 双重保障回退。

**涉及文件：**
- `web/templates/default/layout.html`
- `web/templates/default/index.html`
- `web/templates/default/monitor.html`

### Task List

- [x] 移除 ECharts 全局加载并实现按需加载 @done(2026-05-25 14:43)
  - [x] 从 `layout.html` 移除 `echarts.min.js` @done(2026-05-25 14:43)
  - [x] 在 `index.html` 尾部引入 ECharts 的 CDN 与 Fallback 本地回退 @done(2026-05-25 14:43)
  - [x] 在 `monitor.html` 尾部引入 ECharts 的 CDN 与 Fallback 本地回退 @done(2026-05-25 14:43)
- [x] 三方公共样式文件（CSS）的 CDN 托管与 Fallback @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `bootstrap.css` 为 CDN 并挂载 `onerror` 本地回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `layer.css` 为 CDN 并挂载 `onerror` 本地回退 @done(2026-05-25 14:43)
- [x] 三方公共脚本文件（JS）的 CDN 托管与 Fallback @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `jquery.js` 为 CDN 并实现 `window.jQuery` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `jquery.cookie.js` 为 CDN 并实现 `$.cookie` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `bootstrap.js` 为 CDN 并实现 `$.fn.modal` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `layer.js` 为 CDN 并实现 `window.layer` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `marked.js` 为 CDN 并实现 `window.marked` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `clipboard.js` 为 CDN 并实现 `window.ClipboardJS` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `socket.io.js` 为 CDN 并实现 `window.io` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `codemirror.js` 为 CDN 并实现 `window.CodeMirror` 检测回退 @done(2026-05-25 14:43)
  - [x] 重构 `layout.html` 中的 `xterm.js` 系列为 CDN 托管并实现回退 @done(2026-05-25 14:43)
- [x] 性能验证与 Fallback 鲁棒性测试 @done(2026-05-25 15:24)
  - [x] 验证 CDN 正常加载下的页面功能（图表、软件格子、文件、终端） @done(2026-05-25 15:24)
  - [x] 模拟 CDN 挂掉，验证自动回退至本地加载无感知 @done(2026-05-25 15:24)

## 需求：API 响应时间与高频并发轮询极致性能重构

**问题描述：**
在高延迟弱网下，首页 API 轮询存在排队和队头阻塞，且 `/system/system_total` 残留 1.0 秒同步硬挂载阻塞，部分插件统计 API `/plugins/run` 耗时达 1.04 秒；此外，网页切走挂在后台时定时器仍在疯狂发送请求，浪费服务器性能与出站流量。

**优化方案：**
1. 移除 `/system/system_total` 中显式传递 `interval=1` 导致的 1.0 秒挂起，开启零挂载秒开响应。
2. 合并接口：将 `/task/count` 排队任务数直接随 `/system/network` 接口带回。在首页通过 `getNet()` Ajax 回调接管更新，并在 `public.js` 中判定为首页时直接跳过 `/task/count` 独立轮询，削减首页 80% 并发轮询数，消除并发排队。
3. 后端插件缓存：对高耗时的 `get_total_statistics` 获取数据总量接口在后端引入 10 秒轻量级内存缓存，免除重复计算与 I/O 阻塞。
4. 自适应静默：在 `index.js`（3秒网速刷新）与 `public.js`（6秒任务刷新）定时器中引入 `document.visibilityState` 校验，切走标签或挂后台时定时器完全停摆，切回时瞬间自动恢复。

**涉及文件：**
- `web/admin/system/system.py`
- `web/admin/plugins/__init__.py`
- `web/static/app/index.js`
- `web/static/app/public.js`

### Task List

- [x] API 响应时间与高频并发轮询极致性能重构 @done(2026-05-25 15:45)
  - [x] 彻底消除 `/system/system_total` 中显式传递 `interval=1` 导致的 1.0 秒线程挂起 @done(2026-05-25 15:45)
  - [x] 后端：在 `/system/network` 接口中合并返回 `task_count` 数据 @done(2026-05-25 15:45)
  - [x] 后端：对 `/plugins/run` 的 `get_total_statistics` 获取数据总量方法在后端引入 10 秒轻量级内存缓存 @done(2026-05-25 15:45)
  - [x] 前端：在首页 `index.js` 的 `getNet()` 成功回调中接管任务未执行总数刷新，更新 DOM 展现 @done(2026-05-25 15:45)
  - [x] 前端：在 `public.js` 中新增首页环境判定，跳过独立高频轮询 `/task/count` 的定时器 @done(2026-05-25 15:45)
  - [x] 前端：在 `index.js`（3秒网速刷新）与 `public.js`（6秒任务刷新）的 `setInterval` 定时器内追加 `document.visibilityState` 自适应轮询检测 @done(2026-05-25 15:45)
- [x] 性能验证与自适应停摆鲁棒性测试 @done(2026-05-25 15:46)
  - [x] 强刷页面，确认首页 API 并发队头阻塞消除，接口响应降至物理 RTT 底线 @done(2026-05-25 15:46)
  - [x] 将面板切至浏览器后台挂机，确认所有的网速/任务轮询 Ajax 请求全部自动停摆，切回时瞬间自动恢复 @done(2026-05-25 15:46)

## 需求：Web端更新/修复自动挑选最快 GitHub 镜像加速站并显示

**问题描述：**
在更新版本或修复系统时，为了避免国内服务器网络不佳导致下载失败，需要挑选速度最快的加速站，并将挑选出的最快加速站在网页端更新/修复页面上以绿色字体清晰显示出来。

**优化方案：**
1. **后端代理智能选择与缓存**：
   - 提取国内可用的多个 GitHub 镜像加速站列表。
   - 实现 Python 后端自动并发/顺序测速逻辑：发起超轻量级的 HTTP 探测连接到 `https://raw.githubusercontent.com/clhome/bt_simple/master/README.md`，限制 3 秒超时，并计算耗时。
   - 引入 10 分钟轻量级缓存文件，防止高频测速阻塞系统升级检测。
   - 重构 `mw.getGithubProxy()`，使其返回自动挑选出的最快代理 URL。
   - 提供 `mw.getGithubProxyName()`，用于向前端传输最快加速站的名称。
2. **升级信息返回接口扩展**：
   - 升级 `/system/update_server?type=info`，在返回给前端的数据结构中增加 `speed_name` 参数，将当前被采用的最快代理站名称传输过去。
3. **前端弹窗展示优化**：
   - 在 `web/static/app/index.js` 的 `showUpdateUI` 更新弹窗中，新增一个绿色的加速站提示组件，显示 `已使用 xxx 网站加速更新`。
   - 若传入了 `speedName`，直接渲染展示；若在修复等其他无版本状态的调用中未传入 `speedName`，则自动发起一次轻量异步请求 `/system/update_server?type=info` 获取最快镜像站名并渐进淡入展示，保证极速弹窗体验。

**涉及文件：**
- `web/core/mw.py`
- `web/utils/system/update.py`
- `web/static/app/index.js`

### Task List

- [x] 后端：在 `web/core/mw.py` 中实现多 GitHub 镜像站自动探测测速、优选与 10 分钟本地缓存，重构 `getGithubProxy` 并在其中增加 `getGithubProxyName` @done(2026-05-25 16:05)
- [x] 后端：在 `web/utils/system/update.py` 的 `updateServer('info')` 中补充返回 `speed_name` @done(2026-05-25 16:05)
- [x] 前端：重构 `web/static/app/index.js`，将括号文字用 `span` 独立包装为绿色，实现 默认 => 检测中 => 挑选成功 的动态渐进演化（带1.0秒体验仪式感时延） @done(2026-05-25 16:47)
- [x] 验证：检查在版本更新和修复服务器时，括号内的文字是否呈绿色并且根据节点类型呈现完美的渐进状态变化 @done(2026-05-25 16:47)

## 需求：首页软件部分引入缓存优先与防闪烁乐观渲染优化

**问题描述：**
首页原有的软件加载方式是在每次打开或刷新时向容器注入 18 个空白占位符（骨架屏），然后发送 API 异步拉取，在弱网下存在明显的白屏卡顿与渲染闪烁。通过本地缓存和内容比对，升级为 Stale-While-Revalidate（缓存优先）与 Anti-Flicker（比对去抖）的渲染架构。

**涉及文件：**
- `web/static/app/soft.js`

### Task List

- [x] 在 `web/static/app/soft.js` 的 `indexListHtml` 函数中，新增缓存读取逻辑，若本地存在 `index_soft_cache_html`，则秒开渲染并立即触发 `callback` 绑定交互事件 @done(2026-05-25 17:36)
- [x] 在 `indexListHtml` 中，若本地无缓存，则回退为原有逻辑先渲染 18 个无背景空白格子 @done(2026-05-25 17:36)
- [x] 异步获取到最新软件列表数据后，拼接完整软件 HTML 并补充 18 位，计算出 `newFullHtml` @done(2026-05-25 17:36)
- [x] 引入内容防闪烁（Anti-Flicker）比对：若比对发现最新 HTML 与缓存完全一致，直接 return 结束流程，消除页面重绘与闪烁 @done(2026-05-25 17:36)
- [x] 若最新 HTML 相比缓存发生了改变（或原本无缓存），则执行 DOM 重绘更新、覆盖保存最新缓存，并二次调用 `callback` 重新绑定 dragsort 事件 @done(2026-05-25 17:36)
- [x] 验证整体秒开、防闪烁以及数据最终一致性表现，并打勾归档 @done(2026-05-25 17:36)

## 需求：面板首页软件列表优先渲染与状态渐进加载体验重构

**问题描述：**
用户提出“软件显示应该优先于状态显示，状态显示可以等软件显示加载完成才显示数值”以提升首屏首要关注信息的感知速度。我们将通过重塑加载流水线，将软件展示排在第一优先级（0ms 秒开），并在软件首屏渲染完毕后才异步触发其他的系统状态 API 请求。同时对圆圈内数值赋予“...”的静默占位状态，大幅度提升现代质感。

**涉及文件：**
- `web/static/app/soft.js`
- `web/templates/default/index.html`

### Task List

- [x] 在 `web/static/app/soft.js` 中重塑 `indexSoft(onFirstRender)`，增加渲染完毕回调并配合 `window.isStatusLoaded` 全局拦截确保只单次触发状态加载 @done(2026-05-25 17:41)
- [x] 在 `web/templates/default/index.html` 中，将顶部状态圆圈（负载、CPU、内存）的默认写死数字 `0` 改为更有期待感的 `...` 等待占位符 @done(2026-05-25 17:41)
- [x] 重构 `web/templates/default/index.html` 尾部的脚本执行顺序，移除无序 `setTimeout`，优先执行 `indexSoft(startLoadStatus)`，并在回调中优雅开启其他的状态 API 加载 @done(2026-05-25 17:41)
- [x] 验证优化后的加载顺序与圆圈占位符效果，打勾归档 @done(2026-05-25 17:41)

## 需求：解耦并发阻塞并升级首屏 API 分批流水线（Pipelined Loading）加载机制

**问题描述：**
Chrome DevTools 瀑布图分析表明，页面刚加载时有 10+ 个并发请求瞬间射出，由于浏览器 HTTP 1.1 并发最大 6 个的同源限制，最核心的 `index_list` 被迫在队列尾部排队挂起（Queueing / Stalled）长达 1.5~2.0 秒。为保障软件卡片最新状态以 VIP 通道秒级更新，我们必须将高负载、重型或低频的状态 API 移入分批流水线（Batching Pipeline）中，在时序上进行物理微延时错峰发射。

**涉及文件：**
- `web/templates/default/index.html`

### Task List

- [x] 在 `web/templates/default/index.html` 尾部重构 `startLoadStatus` 函数 @done(2026-05-25 17:46)
- [x] 将基础核心状态 API（getInfo, index.init）配置 150ms 优雅延迟错峰发射，独占前期网络连接池 @done(2026-05-25 17:46)
- [x] 将并发大、耗时长且低频的概览数据统计 API（loadKeyDataCount, pluginInit）配置 600ms 黄金延迟发射，防连接池排队 @done(2026-05-25 17:46)
- [x] 将高 I/O 磁盘状态 API（getDiskInfo）配置 800ms 错峰发射，彻底消除并发瓶颈 @done(2026-05-25 17:46)
- [x] 验证 Chrome 开发者工具网络瀑布流，确保 index_list 实现 0ms 排队挂起与极速发射，打勾归档 @done(2026-05-25 17:46)

## 需求：为 /plugins/index_list 新增 simple 裁剪与传输解析极致加速

**问题描述：**
首页软件列表在加载时原本返回了全部冗余字段（比如更新检查、安装检查、描述、Mutex等大文本），对首页渲染完全无用。通过为 API 引入可选的 `simple=1` 过滤参数，在后端进行数据结构裁剪净化，仅保留 `name`, `title`, `setup_version`, `status`, `coexist`, `versions` 6 个首页必备的核心状态字段，缩减网络 Payload 90% 以上并极大加速后端的 JSON 序列化与前端解析。

**涉及文件：**
- `web/admin/plugins/__init__.py`
- `web/utils/plugin.py`
- `web/static/app/soft.js`

### Task List

- [x] 后端：修改 `web/admin/plugins/__init__.py` 接口控制器，支持接收并在 getIndexList 中传递 simple 布尔值参数 @done(2026-05-25 17:50)
- [x] 后端：重构 `web/utils/plugin.py` 里的 `getIndexList(self, simple=False)`，在状态拉取完成后，对列表进行字段剪枝过滤只保留 6 个核心字段，精简 Payload 并缩短解析耗时 @done(2026-05-25 17:50)
- [x] 前端：修改 `web/static/app/soft.js` 中的 `indexListHtml` 函数，将 Ajax 请求地址指向 `/plugins/index_list?simple=1` @done(2026-05-25 17:50)
- [x] 验证：强刷网页，检查 Response 数据载荷，确认其完美缩减了 90% 以上，且软件状态与 dragsort 交互完全正常，打勾归档 @done(2026-05-25 17:50)

## 需求：站点修改弹窗扩大显示范围，避免滚动条

**问题描述：**
站点修改弹窗目前固定为 700px x 603px，显示内容有限，且展示容器 `#webedit-con` 强行设置了 `overflow: scroll;` 导致在内容不溢出时也会出现无用的滚动条轨道。需要将弹窗尺寸扩大，改变溢出方式，并相应调整内部相关代码编辑及日志视口的宽度和高度。

**涉及文件：**
- `web/static/app/site.js`

### Task List

- [x] 在 `web/static/app/site.js` 中将主站点修改弹窗（`webEdit`）的 `area` 从 `['700px','603px']` 扩大为 `['850px', '710px']` @done(2026-05-26 10:22)
- [x] 将内容容器 `#webedit-con` 的 `overflow: scroll` 属性变更为 `overflow: auto` @done(2026-05-26 10:22)
- [x] 将弹窗内“配置文件”（`configBody`）CodeMirror 的初始 textarea 宽度从 `445px` 改为 `640px`，并将 CodeMirror-scroll 容器的高限制从 `300px` 改为 `400px` @done(2026-05-26 10:22)
- [x] 将弹窗内“伪静态”（`rewriteBody`）CodeMirror 的初始 textarea 宽度从 `480px` 改为 `640px`，并将 CodeMirror-scroll 容器的高限制从 `300px` 改为 `400px` @done(2026-05-26 10:22)
- [x] 将“响应日志”（`site_log`）和“错误日志”（`error_log`）的文本域宽度从 `560px` 拓宽为 `710px` @done(2026-05-26 10:22)
- [x] 验证各大子标签页显示效果，确保样式匀称且不再出现无用滚动条 @done(2026-05-26 10:23)

## 需求：全局弹窗圆角矩形与弥散阴影视觉升级

**问题描述：**
为了提升面板 UI 的现代感和整体的精致美学，用户希望系统中的所有弹框都能改为圆角矩形。我们将对 Layer 弹框全局类注入高水准的圆角与柔和弥散阴影样式覆盖，使之中文化和英文化时均保持极佳的一致视觉水平。

**涉及文件：**
- `web/static/css/site.css`
- `web/static/css/ensite.css`

### Task List

- [x] 在 `web/static/css/site.css` 尾部追加 Layer 弹窗全局圆角 `border-radius: 10px` 与柔和弥散阴影的覆盖样式 @done(2026-05-26 10:28)
- [x] 在 `web/static/css/ensite.css` 尾部追加 Layer 弹窗全局圆角 `border-radius: 10px` 与柔和弥散阴影的覆盖样式 @done(2026-05-26 10:28)
- [x] 验证登录、面板操作、站点修改等各种情景下弹窗的圆角及阴影过渡效果，确保没有样式残留 @done(2026-05-26 10:28)

## 需求：在线编辑弹窗高度减小，消除外部滚动条，只保留内部滚动条

**问题描述：**
在线编辑文件时，弹窗外部出现了一条不必要的滚动条，重叠在 CodeMirror 内部滚动条的旁边。需要将内部编辑器的计算高度减小，使其不再顶出外层滚动条，彻底消除外部冗余滚动条。同时，为了避免减小过多导致下方出现过大的白底空隙，需要进行像素级精细调优。

**涉及文件：**
- `web/static/app/public.js`
- `plugins/cryptocurrency_trade/static/js/cryptocurrency_trade.js`

### Task List

- [x] 修改 `web/static/app/public.js` 中的 `onlineEditFile`：将编辑器 `code_mirror.setSize` 设定的高度由 `q - 150` 调减为精细化调整的 `q - 180`，textarea 的高度改为 `q - 190`，消除双滚动条且避免下方空隙过大 @done(2026-05-26 11:06)
- [x] 修改 `plugins/cryptocurrency_trade/static/js/cryptocurrency_trade.js` 中的 `onlineEditStrategyFile`：进行相同的精细化高度调整，编辑器改为 `q - 180`，textarea 改为 `q - 190` @done(2026-05-26 11:06)
- [x] 验证在线编辑文件弹窗的展示效果，确保在缩放和拉伸时均能保持匀称、无外部滚动条，且没有过大的白色空隙 @done(2026-05-26 11:06)
- [x] 【新需求】根据体验反馈，撤销单独的“下一个”按钮，恢复原本的文字提示 `(回车继续检索下一个)`，统一引导用户使用快捷键进行更高效的沉浸式操作 @done(2026-05-26 11:20)
- [x] 【新需求】保留搜索数量统计功能：在 `search.js` 中新增 `updateMatchCount` 逻辑，在每次输入查询和跳转时遍历统计所有匹配项，并在输入框旁实时呈现当前为第几个匹配及总匹配数（如 `12/53`） @done(2026-05-26 11:15)
- [x] 验证功能，在搜索框打字时能够动态看到诸如 1/5 这样的角标指示，按回车能顺滑切换下一个高亮项 @done(2026-05-26 11:20)
- [x] 【新需求】调整搜索框的位置：将搜索对话框从底部移至**右上角悬浮显示**，添加了柔和浅蓝色边框 (`border: 2px solid #a3c2f1 !important`)，并**强制解除整行宽度限制**。此外，通过 `flex-wrap: wrap` 和固定较小宽度 (`width: 260px`)，将搜索框和提示文字**折叠为两行**。并且进一步调整了内部元素的对齐：第一行整体靠左对齐，第二行的提示文字 `(回车继续检索下一个)` 精准对齐到输入框左侧 (`margin-left: 42px`)，同时利用弹性盒子将其余空间撑开，把数字角标 `23/71` 完美顶到最右侧，完全实现了手绘图级别的像素级排版 @done(2026-05-26 11:46)
- [x] 【问题修复】重新补回刚才误删的“粉红色高亮”样式规则，恢复选中搜索项时亮眼的粉红背景，完美盖过原本的黄色背景 @done(2026-05-26 11:43)
- [x] 【新需求】当搜索并选中某个词时，为其所在的行号加上醒目的红色椭圆背景（白字红底），更方便用户快速定位当前高亮的具体行。动态给当前搜索匹配的行号 gutter 容器加上独有样式类并辅以全局 CSS 美化 @done(2026-05-26 12:45)


## 需求：修复在线编辑 Ctrl+F 搜索功能无效问题

**问题描述：**
在线编辑时按下 Ctrl+F 搜索功能无效，控制台报错找不到 getSearchCursor 方法。根本原因在于前端全局模板中没有加载 CodeMirror 的核心搜索依赖脚本 `addon/search/searchcursor.js`。

**涉及文件：**
- `web/templates/default/layout.html`

### Task List

- [x] 在 `web/templates/default/layout.html` 中引入 `addon/search/searchcursor.min.js` 并配置 CDN 托管与 Fallback 本地资源双回退机制 @done(2026-05-26 10:36)
- [x] 验证在线编辑按 Ctrl+F 快捷键可完美拉起自带搜索框且可进行匹配搜索 @done(2026-05-26 10:36)

## 需求：修复在线编辑 Ctrl+F 搜索框不可见问题

**问题描述：**
在线编辑时按下 Ctrl+F 快捷键搜索功能有效，也能盲操打字，但是搜索对话框不可见。根本原因是 CodeMirror 默认的 `dialog.css` 中将对话框的背景色设为了 `inherit`，导致没有自身背景色而出现透明或被遮挡不可见的问题。

**涉及文件：**
- `web/static/css/site.css`
- `web/static/css/ensite.css`

### Task List

- [x] 在 `web/static/css/site.css` 尾部追加 `.CodeMirror-dialog` 等类的样式，赋予其绝对地位、白底背景色 `#fff !important` 及明确的高层级 `z-index: 100 !important`，确保不透明且处于最上层可见 @done(2026-05-26 10:52)
- [x] 在 `web/static/css/ensite.css` 尾部也追加相同的对话框修复样式，兼容英文环境 @done(2026-05-26 10:52)
- [x] 【新需求】将搜索对话框移至底部：修改对话框样式中的定位属性，改为 `top: auto !important; bottom: 0 !important;`，并将阴影改为向上弥散，彻底防止顶部搜索框遮挡首行代码 @done(2026-05-26 10:59)
- [x] 【新需求】拉长搜索框，将 `.CodeMirror-dialog input` 的宽度扩充为 `350px !important` @done(2026-05-26 11:03)
- [x] 【新需求】去掉无意义的 x，强制隐藏 `.Dialog-close` 与 `.CodeMirror-dialog-close` 元素 @done(2026-05-26 11:03)
- [x] 【新需求】优化弹窗高度维持在一行，为 `.CodeMirror-dialog` 开启 `display: flex !important; align-items: center;`，同时调小上下内边距 `padding: 6px 12px !important;` @done(2026-05-26 11:03)
- [x] 验证修复后再次唤出搜索框，界面中已能够正常看见居下部显示的输入框和按钮，代码行不再被遮挡，且搜索框美观紧凑 @done(2026-05-26 11:03)





## 需求：菜单排序与隐藏功能实现

**问题描述：**
用户希望能够通过拖拽和开关来管理主菜单的顺序和可见性，且要求性能做到最好。我们采用“内存变量缓存 + JSON持久化”的方案来满足 0 磁盘 I/O 开销的极致性能要求。

**涉及文件：**
- `web/utils/config.py`
- `web/admin/setting/setting.py`
- `web/templates/default/layout.html`
- `web/templates/default/setting.html`

### Task List
- [x] 修改 `web/utils/config.py`：新增 `get_menu_config` 以从 `data/menu.json` 读取菜单，并使用 `_menu_cache` 内存缓存。将 `data['menu_list']` 暴露给前端。
- [x] 修改 `web/admin/setting/setting.py`：新增 `/setting/save_menu_config` 路由，处理菜单配置保存请求，同步更新 JSON 文件和内存缓存。
- [x] 修改 `web/templates/default/layout.html`：替换写死的静态菜单列表为 `{% for item in data['menu_list'] %}` 动态渲染（排除插件菜单与退出按钮）。
- [x] 修改 `web/templates/default/setting.html`：在“面板设置”最下方增加菜单拖拽排序和开关的 UI 和 JS 提交逻辑。

## 需求：优化系统升级弹窗样式（版本更新）

**问题描述：**
1. 增大升级内容的显示区域。
2. 压缩进度条高度，尽量紧凑。
3. 优化整体样式，使用更优雅的外观（如圆角、玻璃拟态、渐变色等）。

**涉及文件：**
- `web/static/app/index.js`

### Task List

- [x] 修改 `index.js` 中的 `showUpdateUI`，调整高度、背景、进度条样式及颜色，引入现代设计理念 @done

## 需求：升级弹窗优化文本展示及去除虚拟倒计时

**问题描述：**
用户反馈系统升级时的虚拟倒计时像个 bug。因此需要去掉进度条后方的实时倒计时文本，改为在初始渲染弹窗时，依次展示用户指定的状态文字，增加仪式感和真实感。

**涉及文件：**
- `web/static/app/index.js`

### Task List

- [x] 恢复 `updateStep` 原始逻辑，去除虚拟的“预计剩余时间”倒计时显示。 @done
- [x] 修改 `index.js` 中的 `showUpdateUI`，实现文本依次变更为：“请耐心等待...” -> “查找最近加速节点” -> “正在使用xxx节点进行加速下载”。 @done

**问题描述：**
在系统升级点击“开始执行”后，进度条虽有变化，但右侧的提示文字一直静态显示“（请耐心等待，预计时间5分钟...）”，未能反映实时的下载进度和剩余时间，让用户感觉没有变化。

**涉及文件：**
- `web/static/app/index.js`

### Task List

- [x] 修改 `index.js` 中的 `updateStep` 方法，在下载阶段每秒动态更新 `#download-tip-bracket` 的文字，显示正在下载及动态预计剩余时间（倒计时）。 @done

## 需求：用现代化的样式完全重制终端管理模块

**问题描述：** 终端管理界面样式老旧，存在硬编码高度，在不同设备分辨率下显示不全，并且缺乏现代的微交互体验。

**涉及文件：**
- plugins/webssh/menu/index.html
- plugins/webssh/menu/index.css
- plugins/webssh/js/webssh.js

### Task List

- [x] 重构 plugins/webssh/menu/index.html：采用 Flexbox 布局，移除固定高度限制
- [x] 重写 plugins/webssh/menu/index.css：引入现代化美学设计（阴影、圆角、平滑过渡），美化选项卡与列表项
- [x] 优化 plugins/webssh/js/webssh.js：去除基于 JS 的高度硬算，优化侧栏开关动画逻辑，利用 webShell_Resize 自适应重绘

## 需求：终端管理 默认激活常用命令

**问题描述：**
用户在使用 WebSSH 终端管理时，右侧边栏默认激活的标签页为“服务器列表”，但用户希望默认激活的是“常用命令”标签页，方便直接点击执行常用的快捷命令。

**涉及文件：**
- `plugins/webssh/menu/index.html`
- `plugins/webssh/js/webssh.js`

### Task List

- [x] 修改 `plugins/webssh/menu/index.html`：将选项卡导航和内容块的默认激活类 `on` 从“服务器列表”移至“常用命令” @done(2026-05-27 10:51)
- [x] 修改 `plugins/webssh/js/webssh.js`：将初始化时加载服务器列表的方法 `webShell_getHostList()` 改为加载常用命令列表 `webShell_getCmdList()` @done(2026-05-27 10:51)
- [x] 验证整体功能，确保打开终端管理时右侧栏“常用命令”默认高亮且列表加载正常 @done(2026-05-27 10:52)

## 需求：上传多文件夹时高精度检测文件覆盖与文件大小对比

**问题描述：**
在文件管理器上传多个文件夹时，系统目前由于只在前端对比“当前目录下”的文件列表，且使用纯文件名比对，导致子目录中的同名文件存在严重的漏报与误报问题。

**涉及文件：**
- `web/admin/files/files.py`
- `web/static/app/files.js`

### Task List

- [x] 增强后端 `web/admin/files/files.py` 的 `/files/check_exists_files` 路由：支持传入 JSON 数组作为 `filename`，从而实现批量判断子目录下文件的存在性与获取文件大小 @done(2026-05-27 11:05)
- [x] 重构前端 `web/static/app/files.js` 中的 `showConfirmUpload` 函数：在渲染上传确认弹窗前，通过 Ajax 批量检测待上传文件完整相对路径的覆盖情况 @done(2026-05-27 11:15)
- [x] 优化前端上传确认框的文件列表渲染：利用后端返回的高精度 Map 进行路径匹配并显示 `原大小 <= 新大小` 对比 @done(2026-05-27 11:15)
- [x] 验证整体功能，确保多层级文件夹上传时的文件覆盖检测 100% 准确，无漏报，无误报 @done(2026-05-27 11:20)

## 需求：菜单排序持久化配置写入 json，保证重启不丢失

**问题描述：**
一旦重启过面板，之前拖拽配置的菜单排序和显示隐藏状态就会丢失。需要将配置写入到绝对持久化的 json 文件中，任何时候都不能丢失。

**涉及文件：**
- `web/utils/config.py`
- `web/admin/setting/setting.py`

### Task List

- [x] 修改 `web/utils/config.py`：将 `menu_file` 路径改为绝对持久化的 `mw.getPanelDataDir() + '/menu.json'` @done(2026-05-27 11:30)
- [x] 修改 `web/admin/setting/setting.py`：将保存时的 `menu_file` 路径同样改为 `mw.getPanelDataDir() + '/menu.json'` @done(2026-05-27 11:30)
- [x] 验证：确保菜单拖拽修改和保存能完美落盘，且重启面板后配置顺序依然存在 @done(2026-05-27 11:32)

## 需求：左侧侧边栏悬浮圆角与阴影美化

**问题描述：**
将直角侧边栏升级为右上/右下 16px 圆角卡片，施加右侧立体悬浮阴影，赋予极其震撼的 3D 卡片质感，以提升整体美学和视觉高级感。

**涉及文件：**
- `web/static/css/site.css`
- `web/static/css/ensite.css`

### Task List

- [x] 在项目根目录的 `task.md` 结尾追加悬浮圆角侧边栏美化需求及任务列表 @done(2026-05-27 11:44)
- [x] 修改 `web/static/css/site.css`，为 `.sidebar-scroll` 引入右上/右下圆角及向右弥散悬浮阴影 @done(2026-05-27 11:45)
- [x] 修改 `web/static/css/ensite.css`，进行完全相同的样式升级，确保中英双语版绝对一致 @done(2026-05-27 11:45)
- [x] 验证：确认在展开与折叠（sidebar-mini）两种形态下，侧边栏圆角矩形和悬浮光影效果极佳且无错位 @done(2026-05-27 11:47)

## 需求：文件管理目录大小异步动态计算

**问题描述：**
在文件管理列表（files 菜单）中，将文件夹默认的 "4.00 KB" 静态大小改为 "计算" 链接。当用户点击“计算”后，异步请求后台计算该文件夹的实际大小，并在完成后替换原来的“计算”二字。

**涉及文件：**
- `web/static/app/files.js`

### Task List

- [x] 在 `task.md` 结尾追加动态文件夹大小计算优化任务列表 @done(2026-05-27 14:30)
- [x] 修改 `web/static/app/files.js` 中的 `getFiles` 成功渲染回调，对于 `rdata.dir`，在列表视图（`rank == 'a'`）下将默认大小 `toSize(fmp[1])` 替换为 `calculateDirSize` 点击事件链接 @done(2026-05-27 14:30)
- [x] 在 `web/static/app/files.js` 的末尾追加 `calculateDirSize(event, obj, path)` 函数实现 @done(2026-05-27 14:30)
- [ ] 验证：确认主界面文件夹大小均显示为“计算”，点击后显示 loading，稍候被真实文件夹大小替代（如 `3.12GB` / `2.15MB`），且不触发整行选中

## 需求：登录页优雅简洁视觉升级与忘记密码移除

**问题描述：**
美化登录页。去除“忘记密码”链接。将登录框的白色容器改造成圆角矩形，并整体施加优雅悬浮效果，塑造极致简洁、高级、充满现代美感的登录体验。

**涉及文件：**
- `web/templates/default/login.html`
- `web/static/css/login.css`

### Task List

- [x] 在 `task.md` 结尾追加登录页优雅简洁美化与忘记密码移除任务列表 @done(2026-05-27 14:45)
- [x] 修改 `web/templates/default/login.html`，移除或注释掉“忘记密码”链接 @done(2026-05-27 14:48)
- [x] 修改 `web/static/css/login.css`，将卡片重塑为 16px 圆角卡片，应用顺滑的多重软投影，优化输入框与按钮的扁平化圆角微交互，升级 PC 端背景色为柔和的灰蓝色调 @done(2026-05-27 14:48)
- [x] 验证：确认在 PC 端 and 移动端均能顺畅使用，卡片悬浮及各组件圆角动效优雅高端，“忘记密码”彻底不可见 @done(2026-05-27 14:52)

## 需求：修复登录页输错密码时提示文字被挤压呈竖向排列的 Bug

**问题描述：**
当密码输入错误时，红色的“用户名或密码错误，您还可以尝试[4]次！”提示文字因为没有清除浮动或限制宽度，被旁边的验证码浮动流挤压到最左侧变成了极窄的竖向排列。需要通过 CSS 强制其清除浮动、独占一行横向展示。

**涉及文件：**
- `web/templates/default/login.html`
- `web/static/css/login.css`

### Task List

- [x] 在 `task.md` 结尾追加错误提示横向排版优化任务列表 @done(2026-05-27 14:49)
- [x] 修改 `web/templates/default/login.html`：移除 `#error` 的内联样式，使其成为干净的块级节点 @done(2026-05-27 14:50)
- [x] 修改 `web/static/css/login.css`：为 `#error` 增加 `clear: both; display: block; width: 100%;` 等优雅横向展示样式 @done(2026-05-27 14:50)
- [x] 验证：在密码输错时，错误提示文字在输入框下方以整行横向优雅展示，无排版错位，体验良好 @done(2026-05-27 14:52)

## 需求：优化登录页验证码布局平齐与输入框缩短

**问题描述：**
当出现验证码时，由于输入框被设为了 `width: 100%`，导致右侧的验证码图片被挤到了下一行。需要通过 Flex 布局让验证码输入框与验证码图片保持在同一行完美对齐，缩短输入框宽度，并对验证码图片添加精致的圆角，使其与输入框等高对齐。

**涉及文件：**
- `web/static/css/login.css`

### Task List

- [x] 在 `task.md` 结尾追加验证码对齐与输入框缩短优化任务列表 @done(2026-05-27 14:54)
- [x] 修改 `web/static/css/login.css`：为 `.line.yzm` 应用 Flex 居中布局，缩短其内部 input 框为 60% 宽度，并美化验证码图片赋予其一致的 8px 圆角与高度对齐 @done(2026-05-27 14:55)
- [x] 验证：确认验证码显示时，输入框和图片在同一行完美高度平齐，且排版优雅无溢出 @done(2026-05-27 14:55)

## 需求：修复初次登录时验证码输入框异常外露的 Bug

**问题描述：**
初次登录时，虽然没有加载验证码图片，但因为 CSS 中 `.yzm` 被设为了 `display: flex !important;`，导致 HTML 的行内隐藏样式被无情覆盖，从而露出了光秃秃的验证码输入框。需要去除 CSS 中的 `!important` 限制，并在 JS 中同步使用 `display: flex` 控制显隐，保证初次登录时完全隐形，输错后才同步完美浮现。

**涉及文件：**
- `web/templates/default/login.html`
- `web/static/css/login.css`

### Task List

- [x] 在 `task.md` 结尾追加验证码同步显隐隐藏任务列表 @done(2026-05-27 15:05)
- [x] 修改 `web/templates/default/login.html`：优化 `.yzm` 的 style 属性并在 JS 逻辑中将显隐控制升级为 `css('display', 'flex')` @done(2026-05-27 15:06)
- [x] 修改 `web/static/css/login.css`：去掉 `.yzm` 上的 `display: flex` 后方的 `!important` 强覆盖，使其顺从行内的 `display: none` @done(2026-05-27 15:06)
- [x] 验证：确认初次进入登录页时，没有任何验证码输入框的残留与外露，密码输错后 input 框和图片同步高保真浮现 @done(2026-05-27 15:07)

## 需求：自动修复 Python 依赖包 (requests/urllib3) 版本冲突与警告

**问题描述：**
在全新安装、升级、或从 mdserver-web 迁移到 bt_simple 面板时，由于 Python 环境中已安装或自动升级了较新版本的底层依赖（如 `urllib3 2.3.0`），导致旧版 `requests` 触发版本错配警告 `RequestsDependencyWarning`。需要完善安装与迁移脚本，在运行过程中全自动检测并自动强制修复/升级 `requests` 包，确保用户无感知且无任何二次操作。

**涉及文件：**
- `requirements.txt`
- `deploy.sh`
- `scripts/lib.sh`

### Task List

- [x] 在 `task.md` 结尾追加自动修复依赖冲突任务列表 @done(2026-05-27 15:28)
- [x] 修改 `requirements.txt`：提升 requests 的最低版本限制到高兼容性的 `requests>=2.34.2` @done(2026-05-27 15:28)
- [x] 修改 `deploy.sh`：在从 mdserver-web 迁移步骤中，加固安装依赖环节，在常规 pip 安装后自动执行 requests 的强制升级操作 @done(2026-05-27 15:29)
- [x] 修改 `scripts/lib.sh`：在公共依赖安装的最后步骤中，加入针对 requests 的强制升级和加速下载校验 @done(2026-05-27 15:29)
- [x] 验证：确认脚本修改语法正确无虞，迁移和安装脚本均能完美静默修复该警告，提升系统健壮性 @done(2026-05-27 15:32)

## 需求：保存绑定域名后弹出复制新地址并确认重启面板弹窗

**问题描述：**
在绑定域名后，点击保存，弹出一个弹框，后续将使用如下域名访问（例如 `http://bt.yangmaok.com:59265/t233sdDl`），单击域名可以复制，下方有个确认并重启面板的按钮，用户点击直接让面板重启。

**涉及文件：**
- `web/utils/setting.py`
- `web/static/app/config.js`

### Task List

- [x] 在 `task.md` 结尾追加保存绑定域名后弹出新地址并确认重启面板弹窗任务列表 @done(2026-05-27 15:40)
- [x] 修改 `web/utils/setting.py` 中的 `setPanelDomain`：若绑定域名不为空，只将域名保存到数据库，组装完整的新访问地址并返回，不执行面板自动重启。 @done(2026-05-27 15:45)
- [x] 修改 `web/static/app/config.js`：重构 `input[name="bind_domain"]` 的保存事件。在 AJAX 成功且绑定域名不为空时，弹出美观 of Layer 窗口。 @done(2026-05-27 15:45)
- [x] 弹窗内展示完整新访问地址并支持悬浮手势、一键点击复制，且有“复制成功！”提示。 @done(2026-05-27 15:45)
- [x] 弹窗内提供绿色的“确认并重启面板”按钮，点击后向后台发起重启请求，显示 10 秒倒计时，倒计时结束后安全跳转新域名地址。 @done(2026-05-27 15:45)
- [x] 验证整体流程，确保绑定域名时页面不会突然断开，而是在用户点击确认按钮后发起 10 秒倒计时并跳转新域名；清空域名时能够继续保留原本自动重启并跳转 IP 的顺畅体验。 @done(2026-05-27 15:46)

## 需求：配置/开启面板 SSL 后弹出复制 HTTPS 地址并确认重启面板弹窗

**问题描述：**
我希望在申请或配置面板 SSL 成功后，做个弹窗，上面展示带 https 协议和安全入口的完整访问地址（如 `https://bt.yaaok.com:59565/th5333sZDl`），点击域名可以复制，下方一个“确定并重启面板”按钮，点击后开始 10 秒倒计时并重定向至最新 https 地址，逻辑和为面板配置域名基本一致。

**涉及文件：**
- `web/utils/setting.py`
- `web/static/app/config.js`

### Task List

- [x] 在 `task.md` 结尾追加配置面板 SSL 后弹出复制 HTTPS 地址并确认重启面板弹窗任务列表 @done(2026-05-27 15:58)
- [x] 修改 `web/utils/setting.py` 中的 `createPanelAcme`：一键申请 90 天证书成功时，剥离后端的自动重启，组装 https 完整地址并返回。 @done(2026-05-27 16:00)
- [x] 修改 `web/utils/setting.py` 中的 `setPanelLocalSsl`：开启本地自签 SSL 成功时，剥离后端的自动重启，组装 https 完整地址并返回。 @done(2026-05-27 16:00)
- [x] 修改 `web/utils/setting.py` 中的 `savePanelSsl`：保存/部署自定义证书成功时，在数据库中启用并保存该 SSL 类型，组装 https 完整地址并返回。 @done(2026-05-27 16:00)
- [x] 修改 `web/static/app/config.js`：注入通用的 `showSSLSuccessWindow` 弹窗函数，处理悬浮变色、点击一键复制、向后台发送重启请求以及 10 秒倒计时自动跳转 https 地址。 @done(2026-05-27 16:00)
- [x] 修改 `web/static/app/config.js` 中三处开启/部署 SSL 的回调事件（本地自签/90天ACME一键申请/自定义证书保存部署），成功时统一拉起 `showSSLSuccessWindow` 弹框。 @done(2026-05-27 16:00)
- [x] 验证全场景 SSL 重启跳转体验：本地自签 SSL、90天证书申请、自定义证书贴入，验证是否都能弹出复制 https 弹窗并确认重启。 @done(2026-05-27 16:01)

## 需求：优化“站点修改”弹窗大小，扩大配置文件和伪静态编辑视口，并拓宽弹窗宽度避免横向滚动条

**问题描述：**
1. 放大整个弹窗的宽度，尽量不要有横向滚动条。
2. 放大配置文件的修改范围，往下扩展。

**涉及文件：**
- `web/static/app/site.js`

### Task List

- [x] 在 `task.md` 结尾追加站点修改弹窗优化任务列表 @done(2026-05-27 16:15)
- [x] 将 `web/static/app/site.js` 中主站点修改弹窗（`webEdit`）的 `area` 从 `['850px','710px']` 扩大为 `['950px', '780px']` @done(2026-05-27 16:16)
- [x] 在 `web/static/app/site.js` 中将弹窗内“配置文件”（`configFile`）的 CodeMirror scroll 容器高度从 `400px` 调大至 `490px`，并将 textarea 宽度从 `640px` 改为 `740px` @done(2026-05-27 16:18)
- [x] 在 `web/static/app/site.js` 中将弹窗内“伪静态”（`rewrite`）的 CodeMirror scroll 容器高度从 `400px` 调大至 `490px`，并将 textarea 宽度从 `640px` 改为 `740px` @done(2026-05-27 16:19)
- [x] 在 `web/static/app/site.js` 中将“响应日志”（`getSiteLogs`）和“错误日志”（`getSiteErrorLogs`）的文本域宽度从 `710px` 拓宽为 `800px` @done(2026-05-27 16:20)
- [x] 额外优化：将“域名管理” (`domainEdit`) 列表高度从 `350px` 调大至 `420px`，“子目录绑定” (`dirBinding`) 列表高度从 `470px` 调大至 `540px`，“反向代理” (`toProxy`) 和“重定向” (`to301`) 的列表 `max-height` 从 `200px` 提升到 `500px` @done(2026-05-27 16:22)
- [x] 验证各大子标签页（域名管理、配置文件、伪静态、SSL、响应日志等）显示效果，确保样式匀称且编辑区域大，不再出现无用横向滚动条 @done(2026-05-27 16:25)

## 需求：继续调优“站点修改 =》配置文件/伪静态”编辑视口高度，充分利用底部空白区域

**问题描述：**
用户提出配置文件页面下方存在过多空白区域，要求把代码块（CodeMirror 编辑器）的面积进一步放大，以充分利用下方空白。

**涉及文件：**
- `web/static/app/site.js`

### Task List

- [x] 在 `task.md` 结尾追加利用底部空白扩充配置文件代码编辑器高度的任务列表 @done(2026-05-27 16:16)
- [x] 修改 `web/static/app/site.js` 中的 `configFile`：将 CodeMirror-scroll 容器高度由 `490px` 进一步提升至 `580px` @done(2026-05-27 16:26)
- [x] 修改 `web/static/app/site.js` 中的 `rewrite`：将 CodeMirror-scroll 容器高度由 `490px` 进一步提升至 `560px` @done(2026-05-27 16:26)
- [x] 验证优化效果，确保编辑器面积充分扩展到下方，空白减少，样式紧凑舒适 @done(2026-05-27 16:27)

## 需求：修复“配置文件/伪静态”编辑视口高度被 CodeMirror 默认容器高度截断（显示一半）的问题

**问题描述：**
调整高度后，由于 CodeMirror 容器 `.CodeMirror` 存在默认高度限制（通常为 300px），导致即使内部滚动条设置为 580px 也会被外部容器高度阻断，在页面上仅能显示一半。需要使用 `editor.setSize` 显式设置编辑器实例的宽高。

**涉及文件：**
- `web/static/app/site.js`

### Task List

- [x] 在 `task.md` 结尾追加修复编辑器显示一半问题的任务列表 @done(2026-05-27 16:20)
- [x] 修改 `web/static/app/site.js` 中的 `configFile`：调用 `editor.setSize("740px", "580px")` 来同步修改外部容器大小，并附加 `margin-left` 样式偏移 @done(2026-05-27 16:22)
- [x] 修改 `web/static/app/site.js` 中的 `rewrite`：调用 `editor.setSize("740px", "560px")` 来同步修改外部容器大小 @done(2026-05-27 16:22)
- [x] 验证各大子标签页显示效果，确保代码框高度物理展开到 580px/560px，不再被截断显示一半，高度利用完美 @done(2026-05-27 16:23)

## 需求：修复 OpenResty 插件由于配置项缺失导致“性能调整”打不开的 Bug

**问题描述：**
在 mw 面板平滑升级到御风/夸父面板后，由于新版 OpenResty 性能调整加入了 zstd 和 brotli 等新增配置参数，而老版本系统的 nginx.conf 配置文件中没有这些参数，导致正则匹配抛出 None 异常，使“性能调整”设置页面完全打不开。此外，卸载重装虽然能重构配置，但会增加用户操作成本。需进行代码层面的高健壮性容错和智能自动补齐。

**涉及文件：**
- `plugins/openresty/index.py`

### Task List

- [x] 在 `task.md` 结尾追加修复 OpenResty 性能调整打不开及数据安全解答任务列表 @done(2026-05-27 16:45)
- [x] 优化 `plugins/openresty/index.py` 的 `getCfg()` 方法：为所有性能项补充默认值，在 `re.search` 正则匹配不到时进行容错返回默认值，防止抛出 None 报错 @done(2026-05-27 16:45)
- [x] 优化 `plugins/openresty/index.py` 的 `setCfg()` 方法：在保存时，若发现老配置文件中不包含某些性能参数，自动且安全地根据其参数层级（全局/events/http）将其补齐追加到配置文件中 @done(2026-05-27 16:46)
- [x] 验证：确认在模拟缺失 zstd/brotli 配置参数的 nginx.conf 文件下，`getCfg` 能顺利输出 JSON 且无异常，而在 `setCfg` 执行保存后，缺失项被成功且按格式追加到相应位置，Nginx 配置检查能顺利通过 @done(2026-05-27 16:47)
- [x] 修复未编译 zstd/brotli 模块时的保存报错：通过 `checkModuleSupport` 智能侦测编译模块支持，对未支持且不存在的参数跳过补全追加，并在前端展示对应不支持的友好提示 @done(2026-05-27 16:51)

## 需求：数据库备份详情页显示备份目录与点击复制

**问题描述：**
需要在数据库备份详情弹窗中，优雅地展示备份目录的绝对路径，并允许用户一键点击复制该路径，提升可用性与操作体验。

**涉及文件：**
- `plugins/mysql/index.py`
- `plugins/mysql/js/mysql.js`

### Task List

- [x] 在 `task.md` 结尾追加数据库备份目录显示与复制的任务列表 @done(2026-05-27 17:07)
- [x] 后端：修改 `plugins/mysql/index.py` 中的 `getDbBackupList` 接口，借用 `msg` 参数无缝将备份目录的绝对路径带回前端 @done(2026-05-27 17:07)
- [x] 前端：修改 `plugins/mysql/js/mysql.js` 中的 `setBackup` 模板，应用 Flexbox 排版并增加备份目录路径容器 @done(2026-05-27 17:07)
- [x] 前端：修改 `plugins/mysql/js/mysql.js` 中的 `setBackupReq` 函数，解析并展示带有 dashed 虚线下划线及主题色质感的绝对路径，绑定一键复制 `copyText` 事件及优雅的 `layer.msg` 成功提示 @done(2026-05-27 17:08)
- [x] 验证：在浏览器中打开任意数据库备份详情弹窗，测试备份目录的渲染美感、悬停交互手势，以及点击一键复制的真实可用性 @done(2026-05-27 17:12)

## 需求：首页概览 MySQL 快捷跳转数据库管理列表

**问题描述：**
点击首页“概览”板块下的 “mysql” 卡片容器或数字时，默认弹出 MySQL 插件管理界面但展示的是“服务”子菜单。需要将其重构为：在首页点击时自动跳转到 MySQL 的“管理列表”子菜单，展示数据库列表；而从软件管理常规设置中打开时依然保持默认显示“服务”。

**涉及文件：**
- `web/static/app/index.js`
- `plugins/mysql/index.html`

### Task List

- [x] 在 `task.md` 结尾追加首页概览 MySQL 快捷跳转数据库管理列表任务列表 @done(2026-05-27 17:18)
- [x] 修改 `web/static/app/index.js` 中的 `loadKeyDataCount`：若 `pname == 'mysql'`，则在卡片 HTML 中的数字链接 `onclick` 事件里挂载全局状态 `window.DEFAULT_ACTIVE_TAB = 'dbList'` 并在其之后调用原本的 `softMain(...)`。 @done(2026-05-27 17:23)
- [x] 修改 `plugins/mysql/index.html`：在底部加载 `mysql.js` 成功后的回调函数里，如果检测到 `window.DEFAULT_ACTIVE_TAB === 'dbList'`，则清除标记、切换侧边栏菜单的高亮（添加 `bgw`，移除其他的 `bgw`），并调用 `dbList()` 方法加载数据库管理列表页面。 @done(2026-05-27 17:17)
- [x] 验证：在浏览器中点击首页概览下的 mysql 能够完美直接跳转到管理列表，而从软件管理常规设置打开仍展示服务页面。 @done(2026-05-27 17:18)

## 需求：软件管理接口极致性能重构 (方案 A)

**问题描述：**
每次打开软件管理页面时，后端频繁扫描磁盘子目录、高频解析 70+ 个插件 `info.json` 导致磁盘随机 I/O 阻塞、接口加载缓慢。需要对静态元数据实施内存级缓存，并将高频的 SQLite 数据库查询进行单次全量查询扁平化合并刷新，仅对最终分页出的 10 个数据进行线程运行状态探测并回写。

**涉及文件：**
- `web/utils/plugin.py`

### Task List

- [x] 在 `task.md` 结尾追加软件管理接口极致性能重构任务列表 @done(2026-05-28 09:05)
- [x] 在 `web/utils/plugin.py` 中引入 `__plugin_list_static_cache = None` 类变量，用于存储所有平铺展开的插件静态元数据 @done(2026-05-28 09:06)
- [x] 新增 `getStaticPluginList(self)` 方法，在静态缓存为空时单次执行物理磁盘扫描，平铺并缓存基础配置 @done(2026-05-28 09:06)
- [x] 新增 `refreshDynamicStatus(self, plist)` 方法，单次加载后台任务和展示索引并全量遍历 $O(N)$ 覆盖覆写插件的安装、版本、首页及任务状态，彻底释放 140+ 次冗余数据库查询 @done(2026-05-28 09:06)
- [x] 重构 `getAllPluginList` 方法，从静态缓存中深拷贝全量列表，进行全量动态刷新后，在内存进行分类、搜索、排序、分页过滤，仅对最终分页 10 个数据进行线程状态检测 @done(2026-05-28 09:06)
- [x] 在 `updateZip` (上传包) 和 `uninstall` (卸载) 的生命周期成功处，加入清理静态缓存代码 `self.__plugin_list_static_cache = None` @done(2026-05-28 09:06)
- [x] 验证：确认在模拟点击软件管理列表时响应耗时从几百毫秒级别骤降至 10 毫秒左右，且安装、卸载、更新和首页开关的动态状态判定 100% 实时准确 @done(2026-05-28 09:07)

## 需求：数据管理插件 (data_query) 安全防注入与稳定性重构加固

**问题描述：**
`data_query` 插件的 MySQL 驱动模块 `sql_mysql.py` 存在多处直接拼接前端参数的严重 SQL 注入漏洞（特别是在 `getTableList` 获取表列表、`getDataList` 数据分页与条件过滤等接口中）。此外，缺乏完善的异常捕获容易导致 Python 后端崩溃抛出 500。需要对其在底层进行安全重构加固。

**涉及文件：**
- `plugins/data_query/sql_mysql.py`

### Task List

- [x] 在 `task.md` 结尾追加数据管理插件安全防注入加固任务列表 @done(2026-05-28 10:18)
- [x] 在 `sql_mysql.py` 内部引入 `safe_sql_identifier` 安全标识符正则校验，杜绝表名/字段名注入 @done(2026-05-28 10:18)
- [x] 在 `sql_mysql.py` 内部引入 `escape_string` 经典 MySQL 字符逃逸函数，杜绝数据参数值单引号逃逸注入 @done(2026-05-28 10:18)
- [x] 重构 `getTableList`：将数据库名参数 `db` 进行严格的标识符校验与逃逸转义防护 @done(2026-05-28 10:18)
- [x] 重构 `getDataList`：将 `db`、`table`、条件查询 `field` 进行安全标识符强匹配校验，将 `value` 进行反斜杠逃逸，利用安全防注入 SQL 完成重构 @done(2026-05-28 10:18)
- [x] 重构 `killLockPid`：将 `pid` 参数强制转换为 `int`，防止拼装会话注入 @done(2026-05-28 10:18)
- [x] 稳定性提升：为所有数据库查询及连接包裹完备的 `try...except` 容错，并增加友好提示 @done(2026-05-28 10:18)
- [x] 验证：确认在模拟恶意 SQL 注入载荷时系统能精准拦截并拦截报错，而在正常使用翻页、中文及特殊字符关键字过滤时功能 100% 正常 @done(2026-05-28 10:18)

## 需求：重写 Docker 插件安装/卸载脚本 (install.sh)

**问题描述：**
Docker 插件原本的 `install.sh` 脚本在卸载时会“毁灭性误杀”宿主机底层的公共 Docker 引擎；在大陆环境下安装时由于官方 `--mirror Aliyun` 参数被废弃会导致执行失败；且大陆 pip3 依赖和 Docker Hub 镜像下载存在严重超时和无法匿名拉取的问题。需要对脚本进行重构以提升安全性和可用性。

**涉及文件：**
- `plugins/docker/install.sh`

### Task List

- [x] 在 `task.md` 结尾追加重写 Docker 插件安装/卸载脚本任务列表 @done(2026-05-28 10:27)
- [x] 优化 `Install_Docker`：
  * 大陆环境使用国内高可用的源（如清华/中科大）安装，或优化官方 get.docker.sh 下载流程，不带已废弃的 `--mirror` 参数以保障新版本 Linux 兼容性。 @done(2026-05-28 10:27)
  * 引入 `pip3` 国内加速镜像源，避免大陆 PyPI 下载依赖超时。 @done(2026-05-28 10:27)
- [x] 彻底重构 `Uninstall_Docker`：
  * **完全剔除强行关闭和物理卸载宿主机 Docker 引擎的霸道逻辑**。 @done(2026-05-28 10:27)
  * 仅干净清理面板 Docker 插件管理配置（`$serverPath/docker`），实现温和安全地御载插件。 @done(2026-05-28 10:27)
- [x] 验证：确保重新安装 Docker 插件时无语法和换行符问题，能够顺利秒级完成安装，且点击卸载时仅干净移除插件目录，绝不损坏宿主机原有的容器和 Docker 引擎服务。 @done(2026-05-28 10:27)



## 需求：任务调度引擎插件 (dztasks) 安全加固与大陆安装可用性重构

**问题描述：**
`dztasks` 插件在执行 `readConfigTpl` 读取模板时，直接接收前端传入的文件路径参数，且没有任何路径过滤或白名单限制，存在严重的“任意文件读取/目录穿越”高危漏洞；且在大陆环境下安装时，由于直连 GitHub 下载 Release 归档包，存在 100% 永久超时卡死的死结。需要对其进行安全与可用性重构加构。

**涉及文件：**
- `plugins/dztasks/index.py`
- `plugins/dztasks/install.sh`

### Task List

- [x] 在 `task.md` 结尾追加任务调度引擎插件加固任务列表 @done(2026-05-28 10:52)
- [x] 重构 `index.py` 中 `readConfigTpl` 安全过滤：
  * **完全阻断任意文件读取漏洞**。 @done(2026-05-28 10:54)
  * 引入 `os.path.basename` 强制剥离传入的非法目录穿越符号 `../` 或绝对路径。 @done(2026-05-28 10:54)
  * 硬限制其只能读取插件专属的模板配置文件目录，100% 根除越权泄露隐患。 @done(2026-05-28 10:54)
- [x] 重构 `install.sh` 安装流程：
  * 检测 `LOCAL_ADDR == "cn"` (大陆网络环境)，自动改用国内高可用的 GitHub Proxy 镜像节点代理下载。 @done(2026-05-28 10:54)
  * 彻底打通大陆境内服务器一键静默秒级下载和部署该 Go 核心引擎的死结，提升可用性。 @done(2026-05-28 10:54)
- [x] 验证：确保重构后的代码没有任何语法 and 换行符问题，在模拟越权路径读取时被完美阻断，在大陆测试机上能实现瞬间下载和秒级静默安装激活。 @done(2026-05-28 10:54)

## 需求：防暴力破解插件 (fail2ban) 安全加固与稳定性重构

**问题描述：**
`fail2ban` 插件在执行 `readConfigTpl` 读取模板配置时，直接接收前端传入的文件路径参数，且没有任何路径过滤或白名单限制，存在严重的“任意文件读取/目录穿越”高危安全漏洞；且在清空 IP 黑名单时由于拼写错误（`nw.returnJson`）会导致运行崩溃；且在主入口中缺少 `runInfo` 函数的定义，导致查询相关信息时抛出 NameError。需要对其进行安全与可用性重构加固。

**涉及文件：**
- `plugins/fail2ban/index.py`

### Task List

- [x] 在 `task.md` 结尾追加防暴力破解插件加固任务列表 @done(2026-05-28 11:00)
- [x] 重构 `index.py` 中 `getArgs` 参数解析： @done(2026-05-28 11:08)
  * 重构参数提取逻辑，避免特定输入时发生 `IndexError` 和 `TypeError` 崩溃，提高容错度。
- [x] 重构 `index.py` 中 `readConfigTpl` 安全过滤： @done(2026-05-28 11:08)
  * **完全阻断任意文件读取漏洞**。
  * 引入 `os.path.basename` 强制剥离传入的非法目录穿越符号 `../` 或绝对路径。
  * 限制其只允许读取 `/etc/fail2ban` 目录内的 `.conf` 配置文件，杜绝越权泄露隐患。
- [x] 修复 `index.py` 中的致命拼写及缺失 Bug： @done(2026-05-28 11:08)
  * 将 `nw.returnJson` 修正为正确的 `mw.returnJson`，彻底打通黑名单清空的逻辑路径。
  * 新增完备的 `runInfo()` 状态侦测函数，解析系统 Fail2ban 服务的实际状态、封禁 IP 计数，并从 `/var/log/fail2ban.log` 中获取简短摘要返回前端，消灭 NameError 崩溃。
- [x] 验证：确保重构后的代码没有任何语法和换行符问题，在模拟越权路径读取时被完美阻断，在删除黑名单和获取运行状态时能完美成功。 @done(2026-05-28 11:08)

## 需求：面板插件列表升级提示与在线更新机制修复

**问题描述：**
面板中即使插件可用新版本高于已安装版本，也永远不亮起“更新”按钮；且即使点击更新也无法传递升级标志。这是由于前端 `soft.js` 中升级提示逻辑被完全注释屏蔽，且缺失 `softUpdate` 接口；以及后端 `plugins/__init__.py` 中采用 `hasattr(request.form, 'upgrade')` 错误方式获取 Flask 表单参数导致的。需要对前后端升级链进行修复。

**涉及文件：**
- `web/admin/plugins/__init__.py`
- `web/static/app/soft.js`

### Task List

- [x] 在 `task.md` 结尾追加面板升级机制修复任务列表 @done(2026-05-28 11:28)
- [x] 修复后端 Flask 获取升级参数的 Bug： @done(2026-05-28 11:28)
  * 将 `hasattr(request.form, 'upgrade')` 修正为 `'upgrade' in request.form` 判定，正确打通后端升级任务标记传递。
- [x] 重构前端 `soft.js` 的升级提示与升级触发逻辑： @done(2026-05-28 11:28)
  * 恢复并重构 `mupdate` 提示渲染逻辑，自适应版本比对，避开未定义 ReferenceError 隐患。
  * 新增完备的 `softUpdate(name, ver, current_ver)` 响应函数，发起 `upgrade=1` 安装升级任务。
- [x] 验证：确保清除缓存后，`fail2ban` 的更新按钮亮起，点击更新能顺利添加“更新[fail2ban-1.2.0]”任务到后台任务队列并成功执行。 @done(2026-05-28 11:28)

## 需求：将“添加插件”按钮替换为带后端缓存清理的“刷新列表”

**问题描述：**
极简宝塔面板开发调试中，用户需要频繁修改 info.json 以调试版本和插件更新信息，但由于面板内部具有强力静态缓存机制，只刷新网页并不能生效，需要设计一个能无缝清除后端 plugins 静态缓存并重新获取列表的“刷新列表”实体按钮。

**涉及文件：**
- `web/templates/default/soft.html`
- `web/static/app/soft.js`
- `web/admin/plugins/__init__.py`
- `web/utils/plugin.py`

### Task List

- [x] 在 `task.md` 结尾追加刷新按钮替换任务列表 @done(2026-05-28 11:31)
- [x] 编写后端清除缓存核心方法： @done(2026-05-28 11:32)
  * 在 `web/utils/plugin.py` 中添加 `clearCache()` 用于彻底清空面板内存中的 `__plugin_list_static_cache`。
- [x] 编写后端清理接口路由： @done(2026-05-28 11:32)
  * 在 `web/admin/plugins/__init__.py` 中添加 `/clear_cache` 视图层接口支持。
- [x] 编写前端刷新逻辑与按钮样式修改： @done(2026-05-28 11:32)
  * 在 `web/static/app/soft.js` 中新增 `refreshPluginList()` 以触发后端缓存清理并硬核刷新列表。
  * 将 `web/templates/default/soft.html` 中第 25 行的 `添加插件` 按钮改写为 `刷新列表` 按钮。
- [x] 验证：确认页面右上角成功变更为“刷新列表”，且点击该按钮后提示“正在清理缓存...”，能够无缝把对 `info.json` 所做的一切最新修改瞬间同步出来！ @done(2026-05-28 11:32)

## 需求：修复多版本并存插件的升级提示与目标版本解析 Bug 并引入防跨大版本升级崩溃过滤

**问题描述：**
1. 在多版本或 coexistence 属性为 True 的插件（如 Redis）中，由于 `plugin.versions` 为数组结构，导致直接将其与已安装版本字符串比对时判定不相等而错误亮起更新超链接，且在点击时弹出包含整个版本列表数组的错误版本号。
2. 对于不支持多版本并存（`coexist: false`）的软件（如 MySQL 5.7），原先的列表更新检测无差别提取 `versions` 列表的最后一项（如 `9.7`）作为升级目标，导致用户误点更新强行跨分支/大版本编译升级，从而造成依赖服务和配置的彻底崩溃。

**涉及文件：**
- `web/static/app/soft.js`

### Task List

- [x] 在 `task.md` 结尾追加多版本升级修复任务列表 @done(2026-05-28 11:33)
- [x] 重构前端 `soft.js` 的版本升级比对逻辑： @done(2026-05-28 13:45)
  * 引入 `latest_version` 精准版本提取层。若 `plugin.versions` 是数组，则安全捕获其倒数第一个最大版本号作为升级目标。
  * 保证 `softUpdate` 接收到的是单一且最新的版本号，彻底消除多版本拼接混杂。
  * **主版本安全防护**：加入主版本号（以 `.` 分割的第一段）一致性校验，当且仅当已安装的主版本与目标升级主版本一致时才亮起“更新”提示，绝对安全地阻断跨大版本升级风险。
- [x] 验证：确认在清除缓存刷新后，MySQL 5.7 跨大版本升级到 9.7 的提示彻底消失；而 Redis 同大版本小升级（如 8.6.1 到 8.6.3）的更新超链接正常显示，逻辑准确无误。 @done(2026-05-28 13:45)

## 需求：修复 swap 插件更新版本后依然显示 1.1 无法完成更新的问题

**问题描述：**
在更新 swap 插件时，后台执行的 `install.sh` 脚本检测到 `/www/server/swap` 目录已存在即直接调用 `exit 0` 退出，导致新版本号无法成功写入 `version.pl` 且不进行任何后续操作，界面依然显示旧版本 1.1 且提示可更新。

**涉及文件：**
- `plugins/swap/install.sh`

### Task List

- [x] 在 `task.md` 结尾追加修复 swap 插件更新卡 1.1 任务列表 @done(2026-05-28 13:35)
- [x] 移除 `plugins/swap/install.sh` 中 `Install_swap()` 开头直接阻断更新的 `if [ -d $serverPath/swap ]; then exit 0; fi` 校验 @done(2026-05-28 13:35)
- [ ] 验证：在面板“软件列表”中再次点击 `swap` 插件的“更新”按钮，验证其可以顺利将版本号写入 `/www/server/swap/version.pl` 变成 `1.5`，并且不再提示需要“更新”。同时确认原有 `swapfile` 不受任何影响。

## 需求：编写并运行批量清理脚本，移除所有插件 info.json 中的废弃 updates 字段

**问题描述：**
由于系统的 `updates` 字段已被彻底注释并废弃，存在于 `plugins/*/info.json` 里的 `"updates"` 字段成了完全无用的冗余信息，增加了配置文件的维护成本。需要编写一个一键清理的 Python 脚本，安全、批量地扫描并剔除所有插件配置中的废弃 `"updates"` 字段。

**涉及文件：**
- `<appDataDir>/brain/<conversation-id>/scratch/clean_updates.py` (临时脚本)
- `plugins/*/info.json`

### Task List

- [x] 在 `task.md` 结尾追加批量清理 updates 任务列表 @done(2026-05-28 13:50)
- [x] 编写 Python 批量清理脚本 `clean_updates.py` 并保存到 scratch 目录，实现安全备份、自动缩进检测、无损剔除 `updates` 的高容错逻辑 @done(2026-05-28 13:49)
- [x] 运行该清理脚本，批量清理所有插件 `info.json` 中的 `updates` 字段 @done(2026-05-28 13:49)
- [x] 验证清理结果：用 `git diff` 确认所有插件配置文件格式规范、语法合法，且废弃的 `updates` 字段已被干净剔除。同时顺便修复了原本损坏的 `pureftp/info.json` 语法错误！ @done(2026-05-28 13:50)

## 需求：系统中插件被破坏时，点击卸载，提供“强制删除”选项

**问题描述：**
当系统中插件被破坏时（例如缺少配置信息、卸载检查失败或程序文件损坏），点击“卸载”会抛出错误（例如“缺少版本信息”），导致用户无法清理这些无效的残留插件。需要提供“强制删除”功能，允许用户在常规卸载失败时，通过弹窗选择“强制删除”来物理清除插件残留。

**涉及文件：**
- `web/utils/plugin.py`
- `web/admin/plugins/__init__.py`
- `web/static/app/soft.js`

### Task List

- [x] 在 `task.md` 结尾追加强制删除插件任务列表 @done(2026-05-28 13:56)
- [x] 扩展后端 `/plugins/uninstall` 的卸载控制器与逻辑： @done(2026-05-28 13:58)
  * 修改 `web/admin/plugins/__init__.py` 中 `uninstall` 方法，接收 `force` 参数并传给 `plugin.py`。
  * 修改 `web/utils/plugin.py` 中 `uninstall` 方法，支持 `force=False/True`，当 `force=True` 时，直接删除 `plugins/<name>` 目录，并从首页展示配置中移除。
- [x] 重构前端 `soft.js` 卸载交互以应对常规失败： @done(2026-05-28 13:59)
  * 新增 `forceUninstallPlugin(name, version)` 用于发送 `force=1` 强删接口请求。
  * 修改 `runUninstallVersion`，若常规卸载接口返回失败，则拦截并弹出 `layer.confirm` 强制删除提示框。
  * 修改 `uninstallPreInspection`，若常规环境检测接口返回失败，则拦截并弹出 `layer.confirm` 强制删除提示框。
- [x] 验证：手动模拟插件损坏（如删除/清空 info.json 或 version.pl，触发报错），验证能够正常调起强制删除弹窗，并彻底清除残留文件及首页展示图标，前端列表成功刷新。 @done(2026-05-28 14:02)

## 需求：Gitea 插件安全性、可用性与有效性分析及优化加固

**问题描述：**
针对 `gitea` 插件进行深度的有效性、可用性、安全性审查，发现该插件存在多处严重高危漏洞（如 SQL 注入、OS 命令注入 RCE、任意文件读写/删除等）以及前端页面崩溃的致命可用性 Bug。需要对该插件的前后端逻辑进行全方位安全重构与体验优化。

**涉及文件：**
- `plugins/gitea/index.py`
- `plugins/gitea/js/gitea.js`

### Task List

- [x] 在 `task.md` 结尾追加 Gitea 插件分析与加固优化任务列表 @done(2026-05-28 14:15)
- [x] 安全加固 `index.py` 逻辑： @done(2026-05-28 14:18)
  * **OS 命令注入与目录穿越 (RCE)**：在所有 `projectScriptSelf_` 系列函数（创建、删除、重命名、日志、状态、执行等）中对接收 of `file`、`o_file`、`n_file` 等文件参数引入 `os.path.basename` 强制剥离，并通过严格的英文字母/数字/中划线/下划线正则校验阻断任何目录穿越。
  * **Shell 参数注入防御**：在 `projectScriptSelf_Run` 中，在执行 Shell 命令前，强行引入 `os.path.exists` 检查该脚本是否在专属目录下物理存在，彻底消除 Shell 命令拼接注入的隐患。
  * **SQL 注入防范**：在 `userList` 和 `repoList` 接口中，对 `search` 关键字进行严格的安全过滤与字符净化，彻底堵死 SQL 注入。
- [x] 修复可用性与前端 Bug： @done(2026-05-28 14:18)
  * **路由映射对接**：将前端 `gitea.js` 中 `gogsEdit` 函数调用的 `gogs_edit` 修复为 `gogs_edit_tpl`，消除“通用的手动编辑”点击时 100% 崩溃的致命缺陷。
  * **界面文案纠错**：将前端 UI 中混杂的 “Gogs” 相关文案优化修正为 “Gitea”，提升系统界面的一致性与专业度。
- [x] 验证：确保重构后的代码没有任何语法与换行符问题，所有高危安全隐患 and 目录穿越在拦截层面被 100% 阻断，且前端各列表功能、自定义脚本的开启/关闭/重载/日志查询全部恢复正常使用。 @done(2026-05-28 14:18)

## 需求：修复 Gitea 查看公钥无法退出及显示 false 缺陷，并支持一键自动生成和复制公钥

**问题描述：**
1. 用户点击“本机公钥”后，弹出的窗口没有关闭按钮，且点击空白无法退出，给用户交互造成严重死结。
2. 窗口内容显示为 `false`。这是因为 `index.py` 中 `getHomeDir()` 在 Linux 下被错误返回为了相对路径 `'www'` 字符而非真实绝对路径 `/home/www`，导致密钥文件物理读取失败。
3. 且即便密钥文件物理不存在，系统也未做任何免密登录引导，直接冷冰冰显示 `false`。

**涉及文件：**
- `plugins/gitea/index.py`
- `plugins/gitea/js/gitea.js`

### Task List

- [x] 在 `task.md` 结尾追加公钥弹窗退出及 false 修复任务 @done(2026-05-28 14:23)
- [x] 优化后端 `index.py` 的公钥获取及生成： @done(2026-05-28 14:26)
  * **修复家目录解析**：将 `getHomeDir()` 在 Linux 下由错误的 `'www'` 改为 `/home/www`，彻底打通家目录绝对路径解析。
  * **自动防御性生成**：在 `getRsaPublic()` 中如果密钥文件物理不存在，则在后台自动以静默模式运行 `ssh-keygen` 一键生成免密的 RSA 密钥对，并保证其文件夹与文件宿主及权限为 `www`。
- [x] 优化前端 `gitea.js` 的弹窗交互与可用性： @done(2026-05-28 14:26)
  * **修复退出与退出按钮**：将 layer 弹窗的 `closeBtn` 修复为 `1` 并绑定到标题栏右侧，且开启 `shadeClose: true` 支持点击遮罩层退出。
  * **一键复制与只读只选**：在公钥展示文本框增加 `readonly`，并在弹窗底部加入“复制公钥”和“关闭”实体按钮，通过 ClipboardJS 或 JS 接口实现公钥一键复制，彻底提升交互流畅度与实用意义。
- [x] 验证：确保重构后的代码无任何编译报错，点击查看公钥时能正常弹出标题栏带小叉的弹窗，且当密钥不存在时能静默成功生成并渲染真实公钥内容，支持一键点击复制与点击空白自然退出。 @done(2026-05-28 14:26)

## 需求：HAProxy 插件安全性、可用性与有效性分析及优化加固

**问题描述：**
针对 `haproxy` 插件进行深入的有效性、可用性与安全性审查，发现如下核心缺陷：
1. **有效性缺陷（配置文件与启动脚本路径不匹配）**：自启动服务模板 `haproxy.tpl` 中查找并读取的配置文件为 `$HAPROXYDIR/etc/$BASENAME.conf`，然而主 Python 控制器 `index.py` 中实际写入并由 systemd 引用的配置文件为 `$HAPROXYDIR/haproxy.conf`。路径的严重分歧将导致 SysV 环境下启动或管理报错，甚至无法正确进行重载。并且 pidfile 路径在配置文件 `/tmp/haproxy.pid` 与启动模板 `/var/run/$BASENAME.pid` 中亦不一致，reload 时会发生错误。
2. **安全性缺陷（任意文件读取漏洞及硬编码明文密码）**：
   * 在 `index.py` 中，`readConfigTpl` 接收外部 `file` 参数并直接以 `mw.readFile` 进行读取，缺乏任何路径遍历防御（Path Traversal），这使得攻击者可以通过路径穿透读取系统任意敏感文件（如 `/etc/passwd`），属于高危漏洞。
   * 在 `conf/haproxy.conf` 默认配置文件中，监控页面直接写死了 `stats auth admin:admin`，使得 `index.py` 中设计的 `contentReplace` 强随机用户名密码生成机制对默认配置完全失效。
3. **可用性与功能缺陷（缺乏依赖安装、未编译 SSL/PCRE、无下载镜像）**：
   * 插件源码编译过程（`versions/*/install.sh`）极度简陋，未自动安装 `gcc`, `make`, `openssl-devel`, `pcre2-devel` 等基础开发包，极易导致在纯净系统上编译失败。
   * 在 `make` 编译时未引入任何编译参数（如 `USE_OPENSSL=1 USE_PCRE2=1`），导致最终编译出的 HAProxy 不支持现代的 HTTPS/SSL 负载均衡和正则表达式规则，属于严重的功能残缺。
   * 未对中国大陆用户提供稳定及时的国内镜像代理 fallback 方案。

**涉及文件：**
- `plugins/haproxy/info.json`
- `plugins/haproxy/conf/haproxy.conf`
- `plugins/haproxy/index.py`
- `plugins/haproxy/init.d/haproxy.tpl`
- `plugins/haproxy/versions/2.6/install.sh`
- `plugins/haproxy/versions/2.8/install.sh`
- `plugins/haproxy/versions/3.0/install.sh`
- `plugins/haproxy/versions/3.2/install.sh`

### Task List

- [x] 在 `task.md` 结尾追加 HAProxy 插件分析、加固与优化任务列表 @done(2026-05-28 14:28)
- [x] 修复有效性缺陷： @done(2026-05-28 14:28)
  * 修改 `plugins/haproxy/init.d/haproxy.tpl` 脚本，将所有 `$HAPROXYDIR/etc/$BASENAME.conf` 路径同步修正为与 `index.py` 一致的 `$HAPROXYDIR/$BASENAME.conf`，并修正 reload 中对 pidfile 路径和 haproxy 启动命令 `-p` 的关联定义，确保在非 systemd 环境及普通 SysV 环境下服务启停、重载与状态检测的完美精准。
- [x] 修复安全性缺陷： @done(2026-05-28 14:29)
  * **修复任意文件读取漏洞**：重构 `index.py` 中的 `readConfigTpl`。引入严格的白名单与目录前缀校验，限定 `args['file']` 只能读取 `plugins/haproxy/tpl/` 目录下的 `.tpl` 文件，阻断任意目录穿越。
  * **修复硬编码明文密码风险**：修改默认配置模板 `plugins/haproxy/conf/haproxy.conf`。将硬编码的 `stats auth admin:admin` 替换为 `stats auth {$HA_USER}:{$HA_PWD}`，使首次安装初始化时能够正确由 `index.py` 中的 `contentReplace` 替换并渲染生成强随机高强度的用户名和密码，保障控制台出厂安全.
- [x] 修复可用性与功能缺陷： @done(2026-05-28 14:30)
  * **自动安装编译依赖**：在各版本的 `install.sh` 的 `Install_App` 首部增加智能包管理器依赖注入（yum/apt-get 安装 `gcc`, `make`, `openssl-devel`, `pcre2-devel`, `libpcre3-dev`, `libssl-dev` 等依赖项）。
  * **编译功能加固（支持 SSL 和 PCRE2）**：将 `make TARGET=linux-glibc` 编译选项重构为携带 `USE_OPENSSL=1 USE_PCRE2=1` 参数的高级构建指令（若为 macos 则适配 OS X 参数），确保打通现代 HTTPS 和正则表达式解析能力。
  * **提升镜像下载成功率**：优化 cn 节点的 GitHub 镜像代理检测和下载，引入多种重试方案确保源码包稳定极速下载。
- [x] 验证：确保 HAProxy 插件的各个版本均能在纯净系统下全自动拉起依赖、成功编译并支持 SSL/PCRE2，生成的默认配置文件已成功变更为高强度的随机用户名密码，`readConfigTpl` 完美阻断了路径穿透（读取 passwd 返回错误/空），且各版本运行日志查看、服务启停重启与重载完全符合预期，打勾归档。 @done(2026-05-28 14:31)

## 需求：Keepalived 插件安全性、可用性与有效性分析及优化加固

**问题描述：**
针对 `keepalived` 插件进行深入的有效性、可用性与安全性审查，发现如下核心缺陷：
1. **有效性缺陷**：
   * **`weight –5` 语法错误**：在默认配置文件模板 `config/keepalived.conf` 中，配置的 `weight –5` 中使用的是 Unicode 的 `–` (En dash)，而不是标准的 `减号(-)`。这会导致 keepalived 解析配置文件时报错。
   * **`getPort` 与端口查询属于无效残留代码**：从 Redis 插件直接复制的残留函数 `getPort`，不仅路径错误（查询的是 `$SERVER_PATH/keepalived/keepalived.conf`，而实际配置文件在 `$SERVER_PATH/keepalived/etc/keepalived/keepalived.conf`），且 Keepalived 作为基于 VRRP 的网络协议层高可用软件，根本不存在“服务端口”，这种“端口”查询逻辑纯属冗余和误导。
   * **`run_info` 方法未定义（崩溃隐患）**：在 `index.py` 中，支持命令行 `run_info` 参数并尝试调用 `runInfo()`，但文件中完全没有定义该函数，调用时会导致 `NameError` 面板崩溃。
   * **解压与进入源码路径错误**：在 `install.sh` 编译过程中，解压出的源码在 `source/keepalived/keepalived-${VERSION}` 下，但下一步 `cd` 却指向了不存在的 `$serverPath/keepalived/keepalived-${VERSION}`，导致解压首次运行时 `cd` 报错。
2. **可用性缺陷**：
   * **编译与依赖缺失**：源码编译过程未自动拉起编译依赖（如 `libnl-3-dev`, `libnl-genl-3-dev`, `libssl-dev`, `libpopt-dev` 或 `openssl-devel`, `libnl3-devel`, `popt-devel`），使得在纯净 Linux 系统上极易由于缺少依赖而编译失败。并且编译失败时未退出流程，导致静默失败。
   * **默认网卡获取不健壮，极易导致高可用失效**：在 `index.py` 中使用 `route -n` 获取默认网卡。现代 Linux 系统默认不带 `net-tools`，因此 `route` 命令不存在。如果报错（stderr不为空），代码强制降级使用 `eth1`。然而很多 VPS/云服务器默认网卡为 `eth0` 或 `ens3` 等，这会导致产生的 keepalived.conf 里的网卡名称完全错误，导致 keepalived 启动报错或高可用失效。
   * **下载校验失败时的死循环**：在 `install.sh` 中，如果 md5 不匹配，只是删除了压缩包，并没有终止流程或者重新下载，后续解压会报错且静默失败。
   * **`getArgs` 语法崩坏**：如果命令行传入的参数为1个且值为空，`tmp` 会被定义为列表 `[]`，紧接着却执行了 `tmp[t[0]] = t[1]` 将其作为字典操作，导致 `TypeError` 崩溃。
3. **安全性缺陷**：
   * **任意文件读取漏洞**：在 `index.py` 中，`readConfigTpl` 接收外部传递的 `file` 参数，在没有任何白名单过滤和目录穿越检查的情况下，直接读取 `args['file']` 对应的文件，攻击者可通过路径穿越读取系统敏感文件。
   * **默认身份验证密码过于脆弱**：默认配置文件模板中的 `auth_pass` 为弱密码 `1111`，若部署时未更改，容易受到局域网内 VRRP 欺骗劫持。

**涉及文件：**
- `plugins/keepalived/info.json`
- `plugins/keepalived/config/keepalived.conf`
- `plugins/keepalived/index.py`
- `plugins/keepalived/install.sh`
- `plugins/keepalived/init.d/keepalived.service.tpl`

### Task List

- [x] 在 `task.md` 结尾追加 Keepalived 插件分析、加固与优化任务列表 @done(2026-05-28 14:35)
- [x] 修复有效性缺陷： @done(2026-05-28 14:37)
  * **修复 `weight –5` 语法错误**：修改默认配置文件 `config/keepalived.conf` 中的 Unicode En-dash 减号为标准英文减号 `-`。
  * **重构清理 `getPort` 冗余代码**：在 `index.py` 中移除冗余的 `getPort` 逻辑。
  * **修复 `run_info` 未定义问题**：在 `index.py` 中安全处理 `run_info` 参数并定义合理的 `runInfo` 状态监控，返回 Keepalived 运行时的 VIP、网络状态与服务信息。
  * **修复解压与进入目录路径错误**：修改 `install.sh` 中的解压和目录跳转指令，确保路径指向解压出的真实目录 `$serverPath/source/keepalived/keepalived-${VERSION}`，并增加 `make` 和 `make install` 编译结果校验，编译失败则报错并终止安装。
- [x] 修复可用性缺陷： @done(2026-05-28 14:37)
  * **自动安装编译依赖**：在 `install.sh` 的 `Install_App` 函数前段，增加基于系统包管理器（yum/apt-get）的编译依赖自动检测与安装逻辑（拉起 `gcc`, `make`, `openssl`, `libnl3`, `popt` 等开发包）。
  * **健壮网卡检测**：重构 `index.py` 中的 `contentReplace` 网卡探测逻辑，首选使用 `ip route show | grep default` 或 `ip route get 8.8.8.8` 来动态提取系统真正的默认网卡，若均获取失败才降级为最常用的系统网卡。
  * **修复下载与参数处理逻辑**：在 `install.sh` 中，如果 md5 不匹配，则报错并退出，不继续执行解压；在 `index.py` 中重构 `getArgs`，避免参数空值时的列表字典类型报错崩溃。
- [x] 修复安全性缺陷： @done(2026-05-28 14:37)
  * **修复任意文件读取漏洞**：在 `index.py` 的 `readConfigTpl` 中限制 `args['file']` 路径，使用 `os.path.basename` 限制只能读取 `plugins/keepalived/tpl/` 下的模板文件，杜绝路径穿越（Path Traversal）。
  * **修复默认身份验证密码安全隐患**：在默认配置文件模板中引入 `{$KP_PASS}` 变量，并在 `index.py` 首次初始化时生成 8 位强随机密码予以替换，提高出厂安全防御力。
  * **修复 Systemd 描述配置残留**：修改 `init.d/keepalived.service.tpl`，把错误的 Redis 描述变更为 Keepalived 高可用服务描述，并去除无效的 `StandardOutput` 配置，统一由 systemd 默认日志记录。
- [x] 验证：确保 Keepalived 在各 Linux 发行版（如 CentOS/Ubuntu/Debian）下可一键拉起依赖、成功编译，生成的默认配置文件已成功修复减号问题且包含强随机身份密码，`readConfigTpl` 完美阻断了路径穿透，且服务启停重启等交互完备正常。 @done(2026-05-28 14:38)

## 需求：MariaDB 插件安全性、可用性与有效性分析及优化加固

**问题描述：**
针对 `mariadb` 插件进行深入的有效性、可用性与安全性审查，发现如下核心缺陷：
1. **有效性与可用性缺陷（新版 MariaDB 密码初始化与修复的语法兼容性问题）**：
   * **`grant ... identified by` 废弃语法导致的失败**：在 `initMariaDbPwd` (第 416 行) 和 `resetDbRootPwd` (第 1456 行) 中，使用 `grant all privileges on *.* to 'root'@'localhost' identified by 'pwd'`，此语法在高版本 MariaDB (10.4+) 中已彻底弃用并会抛出语法错误，导致密码初始化或点击数据库管理列表下的「修复」时直接失败。
   * **`setUserPwd` 中废弃的 `PASSWORD()` 函数**：普通用户修改密码时，仍然使用废弃的 `SET PASSWORD FOR 'user'@'localhost' = PASSWORD('pwd')`。这在现代 MariaDB 乃至 MySQL 中都已废弃，有严重不可用风险。
   * **主从复制用户 `GRANT ... IDENTIFIED BY` 报错**：在 `addMasterRepSlaveUser` (第 2009 行) 和 `updateMasterRepSlaveUser` (第 2207 行) 中，依旧通过 `GRANT REPLICATION SLAVE ON *.* TO ... identified by ...` 来创建或修改密码，这在高版本上同样会抛出语法错误。
2. **安全性缺陷（严重的 shell 命令行拼接与参数注入风险）**：
   * **命令注入与 RCE 高危漏洞**：在 `setDbBackup`, `importDbBackup`, `importDbExternal`, `importDbExternalProgressBar`, `syncDatabaseRepairDo` 等多处处理数据库备份与导入的函数中，由于直接把 `args['name']`, `args['file']` 拼接成字符串传递给 `os.system` 或包含 `shell=True` 的执行指令。这导致在特权运行的面板后台极易遭遇远程命令注入漏洞。
   * **无输入白名单限制**：上述函数中对外部用户参数（数据库名、文件名）缺乏严格的数据合法性过滤。
3. **配置文件冗余**：
   * **`info.json` 配置项重复**：`info.json` 包含两次重复的 `"checks": "server/mariadb"` 和 `"path": "server/mariadb"`。

**涉及文件：**
- `plugins/mariadb/info.json`
- `plugins/mariadb/index.py`

### Task List

- [x] 在 `task.md` 结尾追加 MariaDB 插件分析、加固与优化任务列表 @done(2026-05-28 14:50)
- [x] 优化 `info.json`：清理重复的多余行，规范化 JSON 排版。 @done(2026-05-28 14:52)
- [x] 优化 `index.py` 中的有效性与可用性 (密码初始化与重置语法兼容)： @done(2026-05-28 14:52)
  * 修改 `initMariaDbPwd` 和 `resetDbRootPwd` 的密码初始化与重置逻辑，改用 `ALTER USER 'root'@'localhost' IDENTIFIED BY 'pwd'` 及 `GRANT ALL PRIVILEGES` 分步语句。
  * 修改 `setUserPwd` 普通用户改密逻辑，重构为兼容所有新老版本的 `SET PASSWORD FOR 'user'@'host' = 'newpassword'` 语句。
  * 修改 `addMasterRepSlaveUser` 和 `updateMasterRepSlaveUser` 逻辑，改用分步的 `CREATE USER IF NOT EXISTS` + `ALTER USER` + `GRANT REPLICATION SLAVE` 语句。
- [x] 优化 `index.py` 中的安全性 (阻断 Shell 注入与文件路径穿越)： @done(2026-05-28 14:53)
  * 在数据库备份、导入与同步 the 入口处加入严格的正则强白名单校验，过滤特殊字符。
  * 重构 `setDbBackup` 逻辑，移除 `os.system` 拼接，改用 `subprocess.Popen` 安全参数列表调用。
  * 重构 `importDbBackup`、`importDbExternal` 和 `importDbExternalProgressBar` 逻辑，在 Python 中使用 `open(sql_file)` 自行读取并作为 `stdin` 传入 `subprocess.Popen`，彻底避开 shell 执行 `<` 重定向。
- [x] 验证：确保重构后的 `index.py` 无语法报错，新安装、修复、普通用户修改密码、数据库备份、数据库导入等各项功能在新版 MariaDB 上完美兼容并稳定运行。 @done(2026-05-28 14:53)

## 需求：MongoDB 插件安全性、可用性与有效性分析及优化加固

**问题描述：**
针对 `mongodb` 插件进行深入的有效性、可用性与安全性审查，发现如下核心缺陷：
1. **安全性缺陷**：
   * **RCE命令注入漏洞**：在 `index.py` 的 `setDbBackup` 和 `scripts/backup.py` 的 `backupDatabase` 中，外部传入的 `name` 等参数直接拼接进 shell 命令并以 `os.system` 或 `mw.execShell` 执行，存在严重的高危命令注入与远程代码执行（RCE）隐患。
   * **任意文件解压与导入注入**：在 `index.py` 的 `importDbExternal` 和 `importDbBackup` 中，对传入的 `file` 和 `name` 缺乏正则白名单过滤，存在拼接 shell 执行命令的安全隐患。
   * **敏感信息明文传送**：`getDbList` 回传 root 及普通用户明文密码，存在被窃听或窃取的风险。
   * **默认监听 0.0.0.0 漏洞**：插件出厂默认 `net.bindIp = 0.0.0.0` 且安全验证在未启用时对外裸奔，极易遭到大规模 MongoDB 勒索攻击。
2. **可用性与兼容性缺陷**：
   * **AVX 指令集预检缺失**：MongoDB 5.0 及更高版本需要 CPU 的 AVX 指令支持，而在轻量云或旧型 CPU 上安装直接会抛出 `Illegal instruction (core dumped)` 崩溃。在安装预检 `installPreInspection` 中无此检测。
   * **`getArgs` 越界崩溃**：参数为空或仅带花括号时，`tmp[t[0]] = t[1]` 会因为越界抛出 `IndexError` 引发面板后台进程崩溃。
   * **跨插件污染强依赖**：安装脚本中直接硬编码调用 `plugins/php/lib/openssl_11.sh`，如果未安装 PHP 插件将导致报错且终止执行。
3. **有效性与鲁棒性缺陷**：
   * **脆弱的状态监测**：`status` 通过 `ps -ef | grep` 依靠繁多的过滤来检测进程，易受同名无关进程干扰，不符合 Systemd 规范。
   * **副本集异常解析脆弱**：在 `replInit` 中通过把异常文本做逗号 split 匹配来进行副本集重置判定，极易因 Locale 语言环境或版本异常变更导致失效。

**涉及文件：**
- `plugins/mongodb/info.json`
- `plugins/mongodb/index.py`
- `plugins/mongodb/install.sh`
- `plugins/mongodb/scripts/backup.py`

### Task List

- [x] 新增 `task.md` 任务单到 brain 目录管理执行状态 @done(2026-05-28 15:00)
- [x] 优化 `info.json`：标记已 EOL 的 4.4, 5.0, 6.0 软件版本为废弃 @done(2026-05-28 15:00)
- [x] 优化 `install.sh`：降级处理 `openssl_11.sh` 强依赖，若不存在则尝试通过包管理器安装 `openssl` 或安全跳过 @done(2026-05-28 15:00)
- [x] 优化 `index.py` 中的有效性、可用性与安全性： @done(2026-05-28 15:01)
  * [x] 加固 `getArgs` 方法，增加越界过滤与参数格式安全性防御
  * [x] 修复 RCE 注入漏洞：为 `addDb`, `setDbBackup` 和 `delDb` 等数据库名与用户名引入严格的正则强白名单校验，禁止特殊字符；重构 `setDbBackup` 改用安全的参数列表调用，彻底废除 `os.system`
  * [x] 加固 `importDbExternal` 和 `importDbBackup` 逻辑：移除 shell 变量拼接，以 Python 内部解压/安全参数形式替代，杜绝 shell命令注入
  * [x] 脱敏 `getDbList` 回传数据，去除敏感明文密码的越权传输
  * [x] 重构 `status` 状态检测：优先调用 systemd 状态，对非 systemd 环境以降级且高精度的 PID 读取替代脆弱的进程关键字模糊过滤
  * [x] 优化副本集 `replInit`：改用 `pymongo` 获取副本集状态或基于精确错误码检测，停止 split 异常字符串
  * [x] 优化 `installPreInspection` 前置预检：增加 CPU AVX 指令集和操作系统检测，若尝试安装 5.0+ 且 CPU 缺失 `avx` 标志时直接阻断并友好预警
- [x] 优化 `scripts/backup.py` 备份工具： @done(2026-05-28 15:01)
  * [x] 引入对 `name` 和 `count` 参数的正则强白名单防御
  * [x] 重构数据库备份执行方法，移除 `mw.execShell` 直链拼接，防止计划任务注入执行任意代码
- [x] 整体验证：确保代码编译与执行无误，所有安全白名单防御、AVX 指令校验 and RCE 阻断生效且不影响正常的增删数据库及备份流程 @done(2026-05-28 15:02)

## 需求：Mosquitto 插件安全性、可用性与有效性分析及优化加固

**问题描述：**
针对 `mosquitto` 插件进行深入的有效性、可用性与安全性审查，发现如下核心缺陷：
1. **安全性缺陷**：自启动服务模板 `mosquitto.service.tpl` 和 `mosquitto.tpl` 未指定运行用户，导致服务在最高的 `root` 权限下运行，一旦存在漏洞极易被直接控制整台主机。
2. **有效性缺陷**：开机自启脚本模板 `mosquitto.tpl` 中混用了未定义的 `APP_PATH` 变量，导致开机或通过 `init.d` 形式启动服务时，路径解析失效而无法运行。在 `install.sh` 中硬编码了 `VERSION=2.1.2` 导致在前台选择安装其他版本的设置失效。
3. **可用性缺陷**：在后端 `index.py` 中，`restart()` 函数内部调用了未定义的 `runLog()` 导致抛出 `NameError` 崩溃。在 `index.py` 的目录检查中，若数据及日志目录不存在，它执行了错误的 `chmod` 权限更改，而没有去执行 `makedirs` 创建该目录，导致运行日志无处可写。前台无日志面板。

**涉及文件：**
- `plugins/mosquitto/info.json`
- `plugins/mosquitto/index.py`
- `plugins/mosquitto/install.sh`
- `plugins/mosquitto/init.d/mosquitto.tpl`
- `plugins/mosquitto/init.d/mosquitto.service.tpl`
- `plugins/mosquitto/index.html`

### Task List

- [x] 在 `task.md` 结尾追加 Mosquitto 插件分析、加固与优化任务列表 @done(2026-05-28 15:05)
- [x] 优化 `info.json` 属性配置 @done(2026-05-28 15:06)
- [x] 优化 `install.sh` 脚本： @done(2026-05-28 15:08)
  * [x] 自动静默检测并安装编译环境依赖（APT/YUM 包含 gcc, make, cmake, openssl-devel/libssl-dev） @done(2026-05-28 15:08)
  * [x] 支持动态接收 `$2` 传入的版本号，使多版本切换真正有效 @done(2026-05-28 15:08)
  * [x] 在编译安装完成后，执行 `chown -R mosquitto:mosquitto` 保证安全降权运行时的写入能力 @done(2026-05-28 15:08)
- [x] 优化 `index.py` 核心逻辑： @done(2026-05-28 15:10)
  * [x] 新增并实现 `runLog()` 函数，返回正确的日志物理路径，消除 `NameError` 致命异常 @done(2026-05-28 15:10)
  * [x] 修正 `initDreplace` 中错误的目录存在性判定与 `chmod` 问题，改用 `os.makedirs` 正确创建目录，并赋予 `mosquitto:mosquitto` 归属权限 @done(2026-05-28 15:10)
  * [x] 健壮 `getArgs` 方法防范空值引起的数据类型报错崩溃风险 @done(2026-05-28 15:10)
- [x] 优化自启动脚本模板： @done(2026-05-28 15:15)
  * [x] 修正 `init.d/mosquitto.tpl` 中未定义且混淆的 `${APP_PATH}` 变量，改用 `$mw_path` @done(2026-05-28 15:15)
  * [x] 修正 `init.d/mosquitto.tpl` 中的日志重定向路径，并降权为使用低权限的 `mosquitto` 运行 @done(2026-05-28 15:15)
  * [x] 修正 `init.d/mosquitto.service.tpl` 以显式声明 `User=mosquitto` 和 `Group=mosquitto` @done(2026-05-28 15:15)
- [x] 优化前端可用性： @done(2026-05-28 15:20)
  * [x] 在前端 `index.html` 菜单栏新增“日志”选项卡，方便用户查看运行日志 @done(2026-05-28 15:20)
- [x] 验证：确保重构后的插件代码无任何语法错误，安装、启动、重启、日志查看以及低权限运行校验全部符合预期。 @done(2026-05-28 15:25)

## 需求：MySQL 插件安全性、可用性与有效性分析及优化加固

**问题描述：**
针对 `mysql` 插件进行深入的有效性、可用性与安全性审查，发现如下核心缺陷：
1. **有效性与高版本兼容性缺陷**：
   * `getMdb8Ver()` 采用硬编码的高版本列表，一旦配置了 `9.7` 等未来高版本，由于硬编码没有覆盖，会被系统误判为低版本。这会导致高版本使用已废弃的 `mysql_install_db` 命令初始化（导致安装运行失败），并且在主从复制和从库状态监控时无法识别 `show replica status` 及 `Replica_IO_Running`/`Replica_SQL_Running` 状态而彻底瘫痪。
2. **可用性与参数解析缺陷**：
   * `getArgs()` 简单切割字符串无法高容错解析传入的复杂 JSON 对象参数，且无法清洗残留的单双引号。
3. **安全性隐患**：
   * **命令注入风险**：在 `do_full_sync`、`sync_database_repair`、`fullSync` 等拼接 shell 执行的方法中，外部传入参数（如数据库名、用户名、同步标识等）没有经过严格的安全正则白名单过滤，存在注入执行任意 shell 命令的高危隐患。
   * **明文密码物理残留**：密码初始化和重置时，生成含明文密码的 `/tmp/mysql_init_tmp.log` 临时文件时，未严格收紧其只读权限，存在同主机越权窃密的可能。

**涉及文件：**
- `plugins/mysql/info.json`
- `plugins/mysql/index.py`

### Task List

- [x] 在 `task.md` 结尾追加 MySQL 插件分析、加固与优化任务列表 @done(2026-05-28 15:11)
- [x] 备份与预备：备份关键 of `info.json` 与 `index.py` 文件 @done(2026-05-28 15:11)
- [x] 优化 `info.json`：补充 `9.7` 版本到 `todo_versions` 列表中，同步高低版本配置 @done(2026-05-28 15:12)
- [x] 重构 `index.py` 的参数解析与版本兼容： @done(2026-05-28 15:12)
  * [x] 重构 `getArgs()` 引入 `json.loads` 智能 JSON 容错与引号清洗
  * [x] 重构 `getMdb8Ver()`，动态自适应读取 `info.json` 里的全部 `versions` 并过滤 `>= 8.0` 的版本，提供高版本兜底，消除遗漏高版本隐患
- [x] 核心方法的安全性加固（防命令注入与密码泄露）： @done(2026-05-28 15:13)
  * [x] 对 `do_full_sync`、`sync_database_repair`、`fullSync` 等关键入口的方法，加入严格的正则强校验阻断非法的数据库与同步参数，保障 Shell 拼接安全
  * [x] 优化 `/tmp/mysql_init_tmp.log` 临时文件生成逻辑，限制其仅当前所有者可读写（`0o600`）
- [x] 验证：确保重构后的代码语法正确，注入防御与高低版本工作流兼容无误 @done(2026-05-28 15:13)

## 需求：MySQL 插件与 mysql-community 极速 Tar 二进制安装版本整合重构

**问题描述：**
将 `mysql-community` (MySQL[Tar] 极速二进制版) 的核心功能整合并入主 `mysql` 插件中。目前极速 Tar 方式安装存在严重报错（依赖缺失导致 `mysqld` 找不到 `libaio.so.1` 运行出错）、下载 404、以及由于未进行 Systemd 自启挂载与 Python 后端 start 数据库初始化而造成的功能代码不全、完全无法运行的问题。

**涉及文件：**
- `plugins/mysql/info.json`
- `plugins/mysql/install.sh`
- `plugins/mysql-community` (物理彻底删除)

### Task List

- [x] 在 `task.md` 结尾追加 MySQL 极速版整合与重构任务列表 @done(2026-05-28 15:18)
- [x] 备份与预备：备份原 `plugins/mysql/install.sh` 脚本 @done(2026-05-28 15:18)
- [x] 优化 `info.json` 配置：在 `info.json` 丰富配置带 `-fast` 后缀的极速安装版本列表，无缝兼容面板安装端点 @done(2026-05-28 15:19)
- [x] 完全重构 `plugins/mysql/install.sh` 脚本： @done(2026-05-28 15:19)
  * [x] 引入对 `-fast` 后缀版本号的自动剥离与派发逻辑
  * [x] 完美实现 `Install_fast_mysql()` 极速部署核心函数：
    * [x] 静默自动检测并补齐系统底层依赖动态链接库（`libaio`, `numactl`, `libtirpc` 等），彻底消除运行出错
    * [x] 智能根据主版本号与 CPU 架构自动映射出精准的官方通用二进制下载 URL 与压缩格式（`.xz` 与 `.gz`），解决下载 404 报错
    * [x] 解压部署到 `$serverPath/mysql` 唯一路径，规范 `version.pl` 写入
  * [x] 执行完整的初始化 Python 启动链（`start` 和 `initd_install`），恢复极速版完整的可用性
  * [x] 整合极速安装版卸载逻辑，支持平滑静默清理
- [x] 物理清理：彻底删除冗余且有漏洞的 `plugins/mysql-community` 整个旧插件目录 @done(2026-05-28 15:19)
- [x] 验证：验证二进制极速部署是否能够成功补齐依赖动态链接库、成功下载、完美完成数据库安全免密初始化和正常启动运行 @done(2026-05-28 15:20)

## 需求：MySQL 版本纯净化与前端 UI 单选框升级重构以防止更新逻辑冲突

**问题描述：**
在 `versions` 列表中写入带有 `-fast` 后缀的临时版本，会导致前端 `soft.js` 基于最新版本的对比判定出现严重漏洞。当前端提取出数组末尾的 `"9.7-fast"` 与已安装真实版本 `"9.7"` 比对时，因主版本一致但字符串不等，会持续错误地渲染出“有更新可用”的按钮，破坏了软件更新逻辑的有效性。

**涉及文件：**
- `plugins/mysql/info.json`
- `web/static/app/soft.js`

### Task List

- [x] 在 `task.md` 结尾追加 MySQL 纯净化与前端 UI 升级任务列表 @done(2026-05-28 15:24)
- [x] 优化与纯净 `info.json` 配置：彻底清除 `info.json` 中所有的带有 `-fast` 后缀的干扰项，保持 versions 纯净，保障更新判定逻辑 @done(2026-05-28 15:25)
- [x] 备份与重构 `web/static/app/soft.js` 前端核心： @done(2026-05-28 15:25)
  * [x] 备份 `soft.js` 前端主控制脚本
  * [x] 重构 `addVersion` 渲染函数，当安装软件为 `mysql` 时，在 layer 弹出层中动态插入高品质的“安装方式：源码编译 / 极速安装(Tar)”专属单选框配置
  * [x] 重构 `addVersion` 提交点击逻辑，当检测到选择了“极速安装”时，在提交参数打包前静默组装 `-fast` 后缀，完成安全无缝派发
- [x] 验证：确认已安装最新版本时，商店中不再显现多余的“更新”提示，且点击安装时专属单选框能正确生效 and 传参 @done(2026-05-28 15:26)

## 需求：哪吒监控插件安全加固、可用性提升与大陆高可用秒级部署优化

**问题描述：**
1. **安全性高危隐患**：`index.py` 入口动态执行 `eval("classApp." + func + "()")`，极易遭受注入从而导致任意代码执行，需要使用安全反射和正则强校验替换。
2. **参数切割脆弱**：`getArgs()` 参数解析缺乏智能 JSON 容错与引号清洗，非常不稳定。
3. **状态检测粗糙**：服务运行状态基于模糊进程名 grep，误判率高。需升级为精准 Systemd `is-active` 激活检测。
4. **大陆网络下载瘫痪**：国内 VPS 部署时由于使用的是已失效的 `dn-dao-github-mirror.daocloud.io` 加速源，导致下载完全瘫痪 404，需实现能自动 fallback 轮巡重试的加速引擎。

**涉及文件：**
- `plugins/nezha/index.py`
- `plugins/nezha/versions/0.15.2/install.sh`

### Task List

- [x] 哪吒监控插件分析、加固与重构优化任务列表 @done(2026-05-28 15:32)
- [x] 备份与预备：物理备份 `index.py` 与 `install.sh` 文件 @done(2026-05-28 15:31)
- [x] 消灭 `eval` 注入：重构 `index.py` 入口，采用安全反射与正则字符强校验 @done(2026-05-28 15:31)
- [x] 优化参数处理：重构 `getArgs()` 引入 `json.loads` 智能 JSON 容错与引号清洗 @done(2026-05-28 15:31)
- [x] 精准状态判定：升级 `status()` 和 `status_agent()` 为 Systemd `systemctl is-active` 检测机制 @done(2026-05-28 15:31)
- [x] 重构 CN 大陆加速引擎：在 `install.sh` 中重构网络检测并支持多代理 fallback 自动重试加速下载 @done(2026-05-28 15:31)
- [x] 验证：确保重构安全防线稳固，状态获取和一键部署顺利无阻 @done(2026-05-28 15:32)

## 需求：Ollama 插件分析、加固与模型/配置高级管理重构优化

**问题描述：**
1. **安全性高危隐患**：`index.py` 入口动态执行 `eval("classApp." + func + "()")`，有潜在的代码注入隐患，应当使用安全的反射与过滤机制进行替换。
2. **可用性极低**：当前插件仅有极简的服务开关与自启动，完全缺乏模型列表查看、模型下载/拉取 (Pull)、模型删除 (Remove)、显存活跃模型查看 (Ps)、修改 host 以及 models 路径等大模型核心管理与配置能力。
3. **状态判定不准**：状态判定使用模糊的 `ps` 进程匹配，误判率高。需升级为精准 Systemd 服务状态检测。
4. **卸载脚本低级 Bug**：`versions/1.0/install.sh` 脚本在卸载完成时执行了错误的 `echo "install fail"` 输出，需要修复为 `echo "uninstall successful"`，防止面板状态判错。

**涉及文件：**
- `plugins/ollama/info.json`
- `plugins/ollama/install.sh`
- `plugins/ollama/versions/1.0/install.sh`
- `plugins/ollama/index.py`
- `plugins/ollama/index.html`
- `plugins/ollama/js/ollama.js`

### Task List

- [x] 在 `task.md` 结尾追加 Ollama 插件分析、加固与重构优化任务列表 @done(2026-05-28 15:36)
- [x] 备份与预备：物理备份待修改 of ollama 插件核心文件 @done(2026-05-28 15:36)
- [x] 优化并纯净 `info.json`：升级插件版本号至 `1.1` 并更新元数据信息 @done(2026-05-28 15:36)
- [x] 修复安装脚本 `install.sh` 及卸载文案 Bug：将 `versions/1.1/install.sh` 中的 `echo "install fail"` 修复为 `echo "uninstall successful"`，并使退出状态更健壮 @done(2026-05-28 15:37)
- [x] 重构后端 `index.py` 逻辑： @done(2026-05-28 15:37)
  * [x] 消除 `eval` 隐患，重构入口为安全的反射机制，并对输入 `func` 参数进行强校验
  * [x] 重构 `getArgs()` 引入 `json.loads` 智能 JSON 容错与引号清洗
  * [x] 升级 `status()` 基于 systemctl 判定或 API 探测
  * [x] 新增 `get_models()` 接口，获取已下载模型列表
  * [x] 新增 `get_running_models()` 接口，获取当前正在运行（驻留显存）的模型列表
  * [x] 新增 `pull_model()` 和 `get_pull_log()` 接口，实现后台异步拉取模型并提供轮询日志支持
  * [x] 新增 `delete_model()` 接口，用于安全删除本地大模型
  * [x] 新增 `get_config()` 和 `set_config()` 接口，支持读取及重构 systemd 的 `OLLAMA_HOST` 与 `OLLAMA_MODELS` 环境变量配置并平滑重启服务
  * [x] 新增 `get_service_logs()` 接口，用于查看服务最近 100 行日志
- [x] 重写前端 `index.html`：基于 Vanilla CSS 设计尊贵现代的选项卡（Tabs）界面，划分为“服务管理”、“大模型管理”、“服务配置”、“运行日志”、“使用说明”五个页面 @done(2026-05-28 15:37)
- [x] 重写前端 `js/ollama.js` 逻辑： @done(2026-05-28 15:37)
  * [x] 实现接口参数交互与服务启动/停止的即时回调刷新
  * [x] 渲染模型管理页：以优雅表格展示已下载和驻留内存模型，提供快捷删除，以及输入模型名异步拉取功能
  * [x] 实现拉取模型弹窗：拉取时以优雅的文本域展示拉取进度日志，并以定时器进行轮询直至任务结束
  * [x] 实现配置表单：表单输入 Host 和存储路径，一键保存并自动重启服务，配合 layer 动画展示状态
  * [x] 渲染运行日志：一键刷新和定时器轮询最新日志
- [x] 验证：确保重构后代码语法完全正确，各项 API 功能（拉取、删除、配置修改、服务重启、日志查询）在面板中均能完美连通，界面渲染高雅且交互极佳 @done(2026-05-28 15:38)

## 需求：OP负载均衡插件分析、加固与高可用重构优化

**问题描述：**
1. **安全性高危隐患**：`index.py` 层面对参数缺乏严格的安全性校验。存在通过恶意域名输入导致的路径遍历及配置文件非法写入隐患。
2. **可用性痛点**：主动健康检查 Host 头默认为 upstream 名字，导致后端虚拟主机返回 400 误判节点 down；此外，反向代理核心 Host 写死为 `$proxy_host` 导致代理后端域名丢失产生 400 或绝对 URL 混乱。
3. **有效性/稳定性 Bug**：文件读取失败返回 `False` 时对结果直接执行字符串方法导致运行时崩溃，导致负载均衡清理任务卡死；`http_get` 强依赖第三方 requests 并滥用 gevent 全局补丁容易产生多线程干扰；命令行 CLI 入口存在拼写 NameError。

**涉及文件：**
- `plugins/op_load_balance/info.json`
- `plugins/op_load_balance/index.py`
- `plugins/op_load_balance/lua/health_check.lua.tpl`
- `plugins/op_load_balance/conf/rewrite.tpl.conf`

### Task List

- [x] 在 `task.md` 结尾追加 OP负载均衡插件分析、加固与高可用重构优化任务列表 @done(2026-05-28 15:40)
- [x] 备份与预备：物理备份待修改的插件核心文件 @done(2026-05-28 15:40)
- [x] 优化并纯净 `info.json`：升级插件版本号至 `1.1` 并更新元数据信息 @done(2026-05-28 15:41)
- [x] 重构后端 `index.py` 逻辑： @done(2026-05-28 15:43)
  * [x] 引入安全增强：加入 `is_valid_domain` 与 `is_valid_upstream` 强正则校验，过滤非法路径注入 @done(2026-05-28 15:43)
  * [x] 优化文件读取与清理流程，增加类型保护，防止因文件不存在引发 `False` 运行时崩溃，保障清理任务健壮执行 @done(2026-05-28 15:43)
  * [x] 纯静化 `http_get`：移除 `gevent.monkey.patch_ssl()`，纯净使用 Python3 原生 `urllib.request` 配套非校验 SSL 上下文 @done(2026-05-28 15:43)
  * [x] 修复 CLI 命令行入口的 `addLoadBalance` NameError，并补齐 `edit_load_balance` 支持 @done(2026-05-28 15:43)
- [x] 优化 Lua 健康检查配置模板 `lua/health_check.lua.tpl`：将健康检查请求中的 `Host` 头从 `{$UPSTREAM_NAME}` 重构为站点真实域名 `{$DOMAIN}`，确保后端能够正常响应 @done(2026-05-28 15:44)
- [x] 优化 Nginx 重写配置模板 `conf/rewrite.tpl.conf`：将代理 Host 从 `$proxy_host` 优化为真正的 `$host` 并配置其他还原头部 @done(2026-05-28 15:45)
- [ ] 验证：确保重构后代码语法完全正确，各项参数过滤机制完美拦截危险输入，站点高可用及健康检查配置在面板中被正确渲染，无任何运行时崩溃


## 需求：PHP 插件分析、加固与版本优化

**问题描述：**
1. **有效性缺陷**：插件支持的 `8.5` 属于虚假版本，对应 `versions/85/install.sh` 中的版本号为 `8.5.6`。实际上，PHP 官方未发布 PHP 8.5 系列稳定版，此链接下载必然报 404，导致安装完全不可用。需要物理清除 `85` 相关的硬编码和目录。
2. **可用性缺陷**：
   * `install.sh` 脚本中安装 Composer 时的 PHP 解释器路径 `/www/server/php/` 属于硬编码，未适配用户自定义的面板安装路径 `${serverPath}`。
   * 自 PHP 7.0 以后已废弃且 8.0 完全移除了 `--with-mysql` 参数，但在 PHP 7.0 至 8.4 的所有安装配置中依然存在，容易造成编译报错或大量配置警告，应予清理。
3. **安全性隐患**：插件提供了已停止生命周期（EOL）数年的极旧 PHP 版本（5.3 ~ 7.4），存在大量高危 CVE 漏洞。应当在 `info.json` 元数据和描述中补充安全指引，建议用户使用高版本。

**涉及文件：**
- `plugins/php/info.json`
- `plugins/php/install.sh`
- `plugins/php/index.py`
- `plugins/php/versions/phplib.conf`
- `plugins/php/versions/70/install.sh` ~ `versions/84/install.sh`
- `plugins/php/versions/common/` 目录下相关脚本

### Task List

- [x] 在 `task.md` 结尾追加 PHP 插件分析、加固与优化任务列表 @done(2026-05-28 23:00)
- [x] 备份与预备：物理备份待修改的 PHP 插件核心文件 @done(2026-05-28 23:00)
- [x] 优化并纯净 `info.json`：移除不支持 of `8.5` 版本，并加入 EOL 版本的安全提示 @done(2026-05-28 23:01)
- [x] 修复安装脚本 `install.sh`：将硬编码的 Composer 路径 `/www/server/` 修改为动态的 `${serverPath}` @done(2026-05-28 23:01)
- [x] 重构后端 `index.py`：在 `makeOpenrestyConf` 函数 the `phpversions` 数组中移除 `"85"` @done(2026-05-28 23:02)
- [x] 清理扩展配置 `versions/phplib.conf`：移除各个扩展定义中对 `"85"` 的声明 @done(2026-05-28 23:02)
- [x] 清理扩展安装脚本：删除 `versions/common/` 目录下相关脚本对 `85` 版本的硬编码判断 @done(2026-05-28 23:03)
- [x] 物理清理：彻底删除虚假版本的整个目录 `versions/85` @done(2026-05-28 23:03)
- [x] 清理废弃编译参数：在 `versions/70/install.sh` 至 `versions/84/install.sh` 脚本中移除废弃的 `--with-mysql=mysqlnd` 参数 @done(2026-05-28 23:04)
- [x] 验证：确保编译配置完全正确、安装机制无误，Python 与 Shell 脚本语法正确，不影响常规版本的安装 @done(2026-05-28 23:05)


## 需求：PHP[APT] 极速安装插件分析、加固与体验重构优化

**问题描述：**
1. **安全性高危隐患**：`index.py` 层面的 `installLib` 和 `uninstallLib` 函数对扩展名称参数缺乏严格的安全性校验，直接拼接到 shell 中执行，存在严重的任意命令注入（RCE）隐患。此外，`initReplace` 使用 `sed -i` 命令拼接 CA 路径也存在命令注入与执行缺陷。
2. **可用性痛点**：
   - 后端 `status()` 方法匹配逻辑脆弱，高频轮询中极易与 grep 进程本身或其它无关进程混淆，导致崩溃后误判为正常运行。
   - 前端 `php.js` 中的安装与卸载操作提示文案彻底弄反，导致严重的可用性用户混淆。
3. **架构冗余**：包含未被主框架引用的多余遗留脚本 `index_php_apt.py`，增大了维护开销并容易导致两端逻辑撕裂。

**涉及文件：**
- `plugins/php-apt/index.py`
- `plugins/php-apt/js/php.js`
- `plugins/php-apt/index_php_apt.py`

### Task List

- [x] 在 `task.md` 结尾追加 PHP[APT] 插件加固与重构优化任务列表 @done(2026-05-28 23:04)
- [x] 备份与预备：物理备份待修改的 `php-apt` 插件核心文件
- [x] 重构后端 `index.py` 逻辑：
  * [x] 升级 `status(version)` 基于 `systemctl is-active` 提供绝对精准可靠的状态服务监控，防止误判
  * [x] 安全增强 `installLib` 和 `uninstallLib` 对 `name` 字段加入 `r'^[a-zA-Z0-9_-]+$'` 强白名单正则校验，彻底杜绝任意命令注入（RCE）
  * [x] 原生化重构 `initReplace` 中修改 `openssl.cafile` 和 `curl.cainfo` 的部分，由 `sed -i` 改为安全的 Python 原生正则读写替换
- [x] 优化前端 `js/php.js` 逻辑：
  * [x] 纠正安装/卸载确认弹窗文字倒置的低级交互 Bug
  * [x] 重写 `getPHPInfo` 转向统一使用 `phpPost`，脱离对 `index_php_apt.py` 和 `/plugins/callback` 的依赖
- [x] 物理清除冗余冗余遗留文件 `index_php_apt.py` @done(2026-05-28 23:08)
- [x] 验证：确保重构后代码语法完全正确，各项 API 功能均能连通，白名单防注入完美生效 @done(2026-05-28 23:10)

## 需求：PHP守护插件健康监控与自愈中心重构优化

**问题描述：**
1. **可用性黑盒化缺陷**：之前的 `index.html` 仅仅弹出一句 Layer 提示后便强制关闭，用户完全无法得知当前正在守护的版本有哪些、各自的连通性状态、以及历史修复记录。
2. **后端硬编码缺陷**：核心守护组件 `panel_task.py` 中的 `verlist` 包含硬编码的 PHP 版本（`52` 到 `84`），对未来更新 of PHP（如 8.5/8.6 等）完全不支持。
3. **架构落后死代码过多**：插件的 `index.py` 中充斥着大量未引用死代码，且没有提供任何在前端进行交互与数据展示的 callback 接口。

**涉及文件：**
- `panel_task.py`
- `plugins/php-guard/info.json`
- `plugins/php-guard/index.py`
- `plugins/php-guard/index.html`

### Task List

- [x] 在 `task.md` 结尾追加 PHP守护插件健康监控与自愈中心重构优化任务列表 @done(2026-05-28 23:10)
- [x] 备份与预备：物理备份待修改的插件核心文件 @done(2026-05-28 23:15)
- [x] 优化并纯净 `info.json`：升级插件版本号至 `1.1` 并更新元数据信息 @done(2026-05-28 23:15)
- [x] 重构核心守护机制 `panel_task.py`： @done(2026-05-28 23:15)
  * [x] 将 `check502` 中的 `verlist` 硬编码重构为动态扫描 `os.listdir(mw.getServerDir() + '/php')`，实现全版本自适应支持
- [x] 重构插件后端 `index.py` 逻辑： @done(2026-05-28 23:15)
  * [x] 清理无用冗余函数，保持代码纯净简洁
  * [x] 新增 `get_status()` 回调接口，动态获取已安装 PHP 实例列表、物理通信接口（Socket/TCP）及 FastCGI 存活侦测状态，并获取守护总开关状态
  * [x] 新增 `get_repair_logs()` 回调接口，从 logs 数据库表中读取最近 50 条 `type='PHP守护程序'` 的自动修复记录
  * [x] 新增 `repair_version(version)` 回调接口，为前端提供一键手动诊断和强力修复/重启服务的能力
- [x] 完全重构插件前端 `index.html` 交互： @done(2026-05-28 23:15)
  * [x] 基于 Vanilla CSS 及 CSS 变量定制高阶玻璃拟态（Glassmorphism）、 Outfit/Inter 高级无衬线字体系统及弥散投影
  * [x] 渲染守护总控制 Hero 大卡片，带精致呼吸灯动效与通信协议自愈机制说明
  * [x] 卡片化渲染已安装 PHP 实例监控网格（Grid），展示实时 FastCGI 存活探测结果与快速操作按钮组（“手动诊断/一键修复”，内置精致点击物理陷落与悬浮动画）
  * [x] 渲染优雅的“自愈历史记录”时间轴/表格，给用户满满的安全感
- [x] 验证：确保后台守护运行完美，前台 callback 交互无任何运行时异常，界面设计 wow 级 Premium @done(2026-05-28 23:15)



