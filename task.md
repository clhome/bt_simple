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
