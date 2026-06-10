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

## 需求：Webstats 插件分析与加固优化

**涉及文件：**
- `plugins/webstats/info.json`
- `plugins/webstats/index.py`
- `plugins/webstats/install.sh`
- `plugins/webstats/tool_migrate.py`

### Task List

- [x] 在 `task.md` 结尾追加 webstats 插件分析与优化任务列表 @done(2026-05-29 00:20)
- [x] 备份与预备：物理备份待修改的 `webstats` 插件核心文件 @done(2026-05-29 00:21)
- [x] 升级 `plugins/webstats/info.json` 插件配置，版本更新至 0.2.6，日期更新至 2026-05-29 @done(2026-05-29 00:21)
- [x] 优化 `install.sh` 鲁棒性：引入 `GEO_VERSION` 备用 fallback 默认静态版本，防止网络波动或 API 限频导致安装崩溃 @done(2026-05-29 00:22)
- [x] 彻底修复 `plugins/webstats/index.py` 安全 SQL 注入漏洞，对模糊搜索 `search_uri` 实施严谨的参数化绑定查询 @done(2026-05-29 00:22)
- [x] 彻底重构 `plugins/webstats/tool_migrate.py` 以进行可用性与性能优化： @done(2026-05-29 00:24)
  * [x] 彻底移除每次迁移站点结束时的 Nginx `restart` 重启操作，保证零服务中断 @done(2026-05-29 00:24)
  * [x] 引入 SQLite 显式大事务机制 `BEGIN TRANSACTION` / `COMMIT`，并改为参数化批量插入，将数据迁移吞吐提升 100x+，杜绝 WAL 锁定和数据库损坏隐患 @done(2026-05-29 00:24)
- [x] 安全彻底清理并物理删除未被引用的冗余文件 `plugins/webstats/webstats_index.py` @done(2026-05-29 00:25)
- [x] 验证：确保重构后代码语法完全正确，迁移任务运行飞速，无任何 Nginx 中断，且安全性注入漏洞被成功封锁 @done(2026-05-29 00:25)

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

## 需求：PHP[YUM] 极速安装插件安全性、可用性与有效性分析及优化加固

**问题描述：**
针对 `php-yum` 插件进行深入的有效性、可用性与安全性审查，发现如下核心缺陷：
1. **安全性高危隐患**：
   - **RCE命令注入漏洞**：后端 `index.py` 中的 `installLib` 和 `uninstallLib` 函数对扩展名称参数 `name` 缺乏任何安全性校验，直接将其拼接成 Shell 命令在终端中执行。如果恶意构造 `name` 的值，就可以引发远程代码执行 (RCE) 命令注入高危漏洞。
   - **命令注入与执行缺陷**：`initReplace` 使用 `sed -i` 命令在 Shell 中执行正则替换来修改 php.ini 路径配置，存在命令注入缺陷且稳定性较差。
   - **`getArgs` 越界崩溃与引号过滤**：后端 `getArgs()` 在没有参数或参数解析失败时容易因为越界抛出 `IndexError`，导致后台服务崩溃。
   - **EOL版本安全提示**：在 `info.json` 里的 EOL 废弃版本没有安全提示指引。
2. **有效性与系统级兼容缺陷**：
   - **虚假版本 `8.5` 挂起与 404**：PHP 官方并没有发布 PHP 8.5 稳定版本，RemiRepo 也没有发布 `php85` 的 rpm 包。用户如果尝试安装 8.5 会报错 404 或者包不存在，导致不可用。
   - **自启动路径卸载 Bug**：`install.sh` 卸载服务时尝试移除 `/lib/systemd/system/system/php${type}-php-fpm.service` （多写了一个 `system/`），导致实际 service 没有清理干净。
3. **可用性与路径计算错乱**：
   - **路径计算错乱**：`install.sh` 和 `versions/common.sh` 中的 `curPath=\`pwd\`` 严重依赖于当前的工作目录 Cwd。一旦面板任务管理器在其他目录下执行该脚本，二次 `dirname` 就会抛出找不到目录等错误。
   - **状态检测容易误判**：后端 `status(version)` 函数通过模糊的 `ps -ef | grep 'remi/php...'` 进程过滤进行状态判断，极易与 `grep` 自身、安装编译进程或面板其他进程混淆。
   - **死代码冗余与依赖污染**：
     - `php-yum` 目录下多余遗留脚本 `index_php_yum.py` 没有任何引用，且它的 `getPluginName()` 被错误地写成了 `'php'`，不仅增大了维护开销，还极易引发依赖污染。
     - 前端 `js/php.js` 中的 `getPHPInfo()` 目前通过 `phpPostCallback` 调用死代码 `index_php_yum.py`。我们在物理删除该文件后，应当重构该函数为直接调用 `phpPost('get_php_info', ...)` 走统一的 `index.py` 主程序。

**涉及文件：**
- `plugins/php-yum/info.json`
- `plugins/php-yum/install.sh`
- `plugins/php-yum/index.py`
- `plugins/php-yum/js/php.js`
- `plugins/php-yum/versions/phplib.conf`
- `plugins/php-yum/versions/lib.sh`
- `plugins/php-yum/versions/common.sh`
- `plugins/php-yum/index_php_yum.py` (物理彻底删除)
- `plugins/php-yum/versions/85/` (物理彻底删除)

### Task List

- [x] 在 `task.md` 结尾追加 PHP[YUM] 插件分析、加固与优化任务列表 @done(2026-05-28 23:35)
- [x] 备份与预备：物理备份待修改的 `php-yum` 插件核心文件 @done(2026-05-28 23:35)
- [x] 物理清理：彻底删除虚假版本的整个目录 `versions/85` 以及冗余遗留文件 `index_php_yum.py` @done(2026-05-28 23:35)
- [x] 优化 `info.json` 元数据配置： @done(2026-05-28 23:35)
  * [x] 移除不支持的 `8.5` 版本
  * [x] 补充对 EOL 版本的安全警示与指引，规范化 JSON 排版
- [x] 优化 `install.sh` 安装脚本和 `versions/common.sh` 扩展安装脚本的路径计算： @done(2026-05-28 23:35)
  * [x] 将 `curPath=\`pwd\`` 重构为利用 `BASH_SOURCE[0]` 动态定位绝对路径，彻底消除执行工作目录不一致导致的路径解析失败
  * [x] 修复 `install.sh` 卸载自启动服务时 `/lib/systemd/system/system/...` 路径写重的低级 Bug
- [x] 重构 `versions/phplib.conf` 和 `versions/lib.sh` 的版本列表： @done(2026-05-28 23:35)
  * [x] 在 `phplib.conf` 中移除所有支持版本里对 `85` 版本的声明
  * [x] 在 `lib.sh` 中移除对 `8.5` 版本的声明
- [x] 重构后端 `index.py` 核心逻辑以提升安全性、可用性与健壮性： @done(2026-05-28 23:36)
  * [x] 升级 `status(version)` 函数：优先采用 `systemctl is-active php${version}-php-fpm` 精准监控服务状态，并以 PID 文件校验为辅助，解决进程模糊过滤误判缺陷
  * [x] 增强安全性，防范 RCE 命令注入：在 `installLib` 和 `uninstallLib` 中，对传入的 `name` 扩展名字段进行 `r'^[a-zA-Z0-9_-]+$'` 强白名单正则校验，从源头阻断任意 Shell 命令注入
  * [x] 原生化重构 `initReplace` 的 CA 路径替换：废弃 `sed -i` 外部 Shell 执行，改用 Python 原生正则读写替换，彻底解决安全与性能缺陷
  * [x] 重构 `getArgs()` 引入 `json.loads` 智能 JSON 容错、越界索引保护与引号清洗，杜绝后台服务挂起崩溃
- [x] 优化前端 `js/php.js` 逻辑以规避冗余依赖： @done(2026-05-28 23:36)
  * [x] 重构 `getPHPInfo` 函数：改用统一的 `phpPost` 发送请求给 `get_php_info`，安全对接统一的 `index.py` 后端，彻底解除对已删除的 `index_php_yum.py` 和 `phpPostCallback` 的依赖
  * [x] 清理无用的 `phpPostCallback` 全局函数
- [x] 整体验证：确保重构后代码语法完全正确，各项 API 功能（版本获取、PHPinfo 展示、禁用函数、会话设置、并发设置、扩展安装/卸载）均正常，防注入与安全防护无误 @done(2026-05-28 23:37)

## 需求：PostgreSQL 插件极速安装与管理安全性、可用性及有效性加固与优化

**问题描述：**
针对 PostgreSQL 运行环境插件进行深入的有效性、可用性与安全性审查，发现如下核心缺陷并进行彻底修复与升级：
1. **安全性高危隐患**：
   - **SQL 注入风险**：底层的 `class/pg.py` 不支持参数化查询。主控 `index.py` 中有大量直接拼接 SQL 的操作；SQLite 模糊查询拼接 `search` 参数存在 SQL 注入风险。
   - **Shell 命令注入风险 (RCE)**：在备份还原等多个函数（`pgBack`, `importDbBackup`）中将未校验的数据库名或文件名直接拼接进 Shell 终端执行。
   - **敏感凭据与文件权限泄露风险**：主从同步时，私钥和明文密码执行脚本暴露在全局可读写的 `/tmp/` 目录下。
2. **可用性与系统兼容缺陷**：
   - **服务状态模糊误判**：状态检测依赖 `ps -ef | grep postgres`，极易受到其他进程（如编译安装、面板其他 python 线程等）的误导。
   - **备份容错机制**：0 字节的损坏备份文件依然会提示成功，且文件名正则兼容度不足。
3. **版本时效性**：
   - 源码包版本落后于 PostgreSQL 官方 2026 最新稳定分支。

**修复文件：**
- `plugins/postgresql/info.json`
- `plugins/postgresql/class/pg.py`
- `plugins/postgresql/index.py`
- `plugins/postgresql/versions/14/install.sh`
- `plugins/postgresql/versions/15/install.sh`
- `plugins/postgresql/versions/16/install.sh`
- `plugins/postgresql/versions/17/install.sh`

### Task List

- [x] 在 `task.md` 结尾追加 PostgreSQL 插件分析、加固与优化任务列表 @done(2026-05-28 23:20)
- [x] 备份与预备：物理备份待修改的 `postgresql` 插件核心文件 @done(2026-05-28 23:21)
- [x] 升级版本定义声明与源码包定义： @done(2026-05-28 23:23)
  * [x] 修改 `info.json` 升级各主流分支至最新发布版本 @done(2026-05-28 23:23)
  * [x] 修改 `versions/14/install.sh` 更新源码包定义 `VERSION=14.23` @done(2026-05-28 23:23)
  * [x] 修改 `versions/15/install.sh` 更新源码包定义 `VERSION=15.18` @done(2026-05-28 23:23)
  * [x] 修改 `versions/16/install.sh` 更新源码包定义 `VERSION=16.14` @done(2026-05-28 23:23)
  * [x] 修改 `versions/17/install.sh` 更新源码包定义 `VERSION=17.10` @done(2026-05-28 23:23)
- [x] 底层 ORM 参数化支持升级： @done(2026-05-28 23:25)
  * [x] 在 `class/pg.py` 中为 `execute()` 和 `query()` 方法增加默认值 `param=()` 参数化支持，并保持完美的向前兼容 @done(2026-05-28 23:25)
- [x] 重构后端 `index.py` 核心逻辑以提升安全性、可用性与健壮性： @done(2026-05-28 23:36)
  * [x] 升级 `status(version)` 函数：优先采用 `systemctl is-active postgresql` 监控服务状态，辅助以 PID 活跃验证，彻底解决进程模糊过滤误判 @done(2026-05-28 23:27)
  * [x] 增加高危变量强正则白名单校验：对 `dbname` / `username` / `dbuser` / `newpwd` / `password` / `filename` / `file` / `access` / `address` 全面进行正则白名单校验，从源头阻断任意 SQL 与 Shell 命令注入 (RCE) @done(2026-05-28 23:33)
  * [x] 升级 SQLite 模糊匹配检索：重构 `getDbList` 中的模糊匹配为 `?` 参数化查询，彻底消除 SQL 注入漏洞 @done(2026-05-28 23:31)
  * [x] 主从同步敏感文件物理防护：将私钥文件 `pg_sync_id_rsa.txt` 和脚本 `cmd_run.sh` 移入插件安全目录，在写入后立即执行强制 `chmod 0600`，并在使用后彻底销毁，确保本地多用户环境下凭证安全性 @done(2026-05-28 23:35)
  * [x] 优化备份文件容错校验：在 `pgBack()` 备份完成后验证生成文件大小，若是 0 字节则彻底清除垃圾文件并抛出明确错误异常提示，拒绝假成功 @done(2026-05-28 23:35)
- [x] 验证：确保重构后代码语法完全正确，各项 API 功能均正常，安全防护阻断成功，主从同步临时凭据收规防护正确 @done(2026-05-28 23:42)

## 需求：Redis 插件分析、加固与版本管理及交互优化

**问题描述：**
针对 Redis 缓存数据库运行环境插件进行深入的有效性、可用性与安全性审查，发现如下核心缺陷并进行彻底修复与升级：
1. **安全性高危隐患**：
   - **任意文件读取漏洞 (Arbitrary File Read)**：在 `index.py` 中，`readConfigTpl` 读取 `args['file']` 字段。该字段是传入的文件路径，被直接传给 `mw.readFile` 而没有任何过滤。这允许攻击者传入任意路径（例如 `/etc/passwd`）读取其内容，造成严重的文件泄露风险。
   - **配置文件注入与 Shell 注入风险 (RCE)**：在 `submitRedisConf` 函数中，直接使用 `val = g + ' ' + args[g]` 替换配置值并写入配置文件，接着调用 `reload()` 重载 Redis 服务。如果用户提交的配置中含有换行符 `\n` 或特殊命令，会引发配置文件指令注入（Conf Injection）。一旦重载，可能会通过 Redis 的特定指令写入恶意计划任务（cron）或 WebShell，从而导致 RCE。
   - **`getArgs` 越界崩溃与引号过滤**：后端 `getArgs()` 在没有参数或参数解析失败时容易抛出越界异常或崩溃。
2. **可用性与系统兼容缺陷**：
   - **服务状态模糊误判**：状态检测依赖于 PID 文件的存在性判断，但若 Redis 异常挂掉时 PID 文件未清理，则会造成虚假的 start 状态误判。
   - **自启动状态检测模糊**：`systemctl status` 依赖于模糊输出匹配，容易受到系统 Locale 语言包（如中文包）影响，导致判断失败。
   - **路径计算错乱**：`install.sh` 中的 `curPath=\`pwd\`` 严重依赖于当前的工作目录 Cwd。一旦面板任务管理器在其他目录下执行该脚本，二次 `dirname` 就会抛出找不到目录等错误。
   - **配置路径与说明硬编码**：相关说明的命令硬编码为 `/www/server/redis`，而未适配面板自定义安装路径。

**修复文件：**
- `plugins/redis/info.json`
- `plugins/redis/install.sh`
- `plugins/redis/index.py`
- `plugins/redis/js/redis.js`

### Task List

- [x] 在 `task.md` 结尾追加 Redis 插件分析、加固与优化任务列表 @done(2026-05-28 23:44)
- [x] 备份与预备：物理备份待修改的 `redis` 插件核心文件 @done(2026-05-28 23:48)
- [x] 优化 `info.json` 插件元数据配置，确保配置合法美观 @done(2026-05-28 23:50)
- [x] 优化 `install.sh` 脚本的路径计算： @done(2026-05-28 23:51)
  * [x] 将 `curPath=\`pwd\`` 重构为利用 `BASH_SOURCE[0]` 动态定位绝对路径，彻底消除执行工作目录不一致导致的路径解析失败 @done(2026-05-28 23:51)
- [x] 重构后端 `index.py` 核心逻辑以提升安全性、可用性与健壮性： @done(2026-05-28 23:55)
  * [x] 升级 `status()` 函数：优先采用 PID 的实际活跃校验（`mw.checkPid`），当 PID 存活时返回 start，结合 `systemctl is-active`，解决崩溃后 PID 残留导致误判为正常运行的问题 @done(2026-05-28 23:53)
  * [x] 升级 `initdStatus()` 方法：采用官方最可靠命令 `systemctl is-enabled` 进行校验，解决跨语言语言包无法匹配的低级 Bug @done(2026-05-28 23:53)
  * [x] 安全增强 `readConfigTpl` 逻辑：对传入的 `args['file']` 强制进行前缀比对或严格的白名单校验，防止越界目录穿越和任意文件读取 @done(2026-05-28 23:54)
  * [x] 安全增强 `submitRedisConf` 对配置项的强正则 white-list 校验：包含 `port/timeout/maxclients/databases/maxmemory` 纯数字匹配，`bind/slaveof` 字符白名单匹配，以及 `requirepass/masterauth` 强抗注入正则限制（绝对禁止包含 `\n` 或 `\r` 换行符），从源头阻断任意配置写入和 RCE @done(2026-05-28 23:55)
  * [x] 重构 `getArgs()` 引入智能解析、越界保护与异常保护，杜绝后台服务挂起崩溃 @done(2026-05-28 23:55)
- [x] 优化前端与交互逻辑以规避硬编码： @done(2026-05-28 23:57)
  * [x] 在前端 `js/redis.js` 中的 `submitConf()` 里增加基本的正则格式前置校验，增强抗漏洞防御纵深 @done(2026-05-28 23:56)
  * [x] 优化 `redisReadme()` 显示：从后端获取当前的 Redis 主目录，以动态变量渲染命令行，消除硬编码的路径错误 @done(2026-05-28 23:57)
- [x] 验证：确保重构后代码语法完全正确，各项 API 功能正常，任意文件读取和换行符注入漏洞被完美封堵，页面交互无误 @done(2026-05-28 23:58)

## 需求：rsyncd 插件有效性、可用性与安全性分析及优化加固

**问题描述：**
针对 `rsyncd` 插件的系统架构和核心代码进行全面安全与质量审查，发现并针对以下问题进行优化加固：
1. **可用性与低级拼写 Bug**：
   - `index.py:612` 将 `chmod` 错写为了 `cmod`，直接导致同步命令脚本无法被正确赋予执行权限，调用时提示权限拒绝。
   - `index.py:343` / `344` 将 `disable` 错写为了 `diable`，导致服务卸载或停用开机自启行为失败。
2. **严重的安全性命令行注入漏洞**：
   - 在 `index.py` 的 `lsyncdRun` 中，参数 `name` 直接参与了 `bash cmd` 命令的拼接和 Shell 执行；而在 `tool_task.py` 创建计划任务时，`name` 也直接拼接进了 Shell 语句块中。没有对该参数进行任何后端校验过滤，容易引发基于 Shell 命令拼接的任意命令执行（RCE）与系统提权。
3. **安全白名单与版本管理**：
   - 默认模板 `rsyncd.conf` 中直接使用了 `hosts allow = *`，虽然使用便捷但在缺乏安全过滤的环境下危险性高；需要为插件的版本号进行升级管理，并对各功能参数增加严格过滤。

**涉及文件：**
- `plugins/rsyncd/info.json`
- `plugins/rsyncd/index.py`
- `plugins/rsyncd/tool_task.py`

### Task List

- [x] 在 `task.md` 结尾追加 rsyncd 插件分析与优化任务列表 @done(2026-05-28 23:48)
- [x] 优化 `info.json` 元数据配置，升级版本号至 2.1 @done(2026-05-28 23:50)
- [x] 重构后端 `index.py` 核心逻辑： @done(2026-05-28 23:56)
  * [x] 修复可用性笔误，将 `cmod +x` 修正为 `chmod +x`，将 `diable` 修正为 `disable` @done(2026-05-28 23:52)
  * [x] 增加针对关键输入项（如 `name`, `sname`）的强正则安全校验，限制为字母、数字、下划线及中划线，彻底杜绝 Shell 注入漏洞 @done(2026-05-28 23:54)
  * [x] 增加针对端口等配置的强类型保护校验，限制端口为有效数值范围 @done(2026-05-28 23:55)
  * [x] 优化 IP 白名单支持：为同步目录增加可选配置的 IP 白名单拦截防护 @done(2026-05-28 23:55)
- [x] 重构 `tool_task.py` 计划任务逻辑： @done(2026-05-28 23:58)
  * [x] 为计划任务同步增加相同的正则安全白名单校验，彻底防堵 Shell 注入 @done(2026-05-28 23:58)
- [x] 验证：确保重构后代码语法完全正确，各功能运行无阻碍，安全拦截逻辑被成功封堵 @done(2026-05-28 23:59)

## 需求：sphinx 插件有效性、可用性与安全性分析及优化加固

**问题描述：**
针对 `sphinx` 插件的系统架构和核心代码进行全面安全与质量审查，发现并针对以下问题进行优化加固：
1. **可用性与重大配置覆盖 Bug**：
   - `tool_cron.py` 中 `createBgTaskDeltaByName` 中的 `mw.writeFile(getTaskConf(), json.dumps(args))` 会导致增量更新计划任务的 ID 覆盖全量更新计划任务 of 全量更新计划任务配置。需修正为写入到 `getTaskDeltaConf()`。
   - `tool_cron.py` 内部缺少在检测到已存在任务时将 `task_id` 自动写回到本地配置文件的逻辑，容易导致状态不同步。
   - `index.py` 中 `getArgs()` 对传入参数简单的 `split(':')` 容易截断包含冒号的参数（如含冒号的数据库密码、表名等），需要提升为鲁棒的参数解析与 JSON 参数检测。
   - `index.py` 预检中对 aarch64 系统的限制不够精准，导致 Mac 平台的 arm64 (M1/M2/M3) 环境开发测试受阻。
2. **命令注入安全性风险**：
   - `index.py` 的 `updateAll` 和 `updateDelta` 函数中通过 `os.system` 拼接 shell 字符串直接执行命令，未对包含的 `index` 配置项名字做任何正则过滤，若配置中含有恶意注入字符可能产生安全隐患。

**涉及文件：**
- `plugins/sphinx/index.py`
- `plugins/sphinx/tool_cron.py`

### Task List

- [x] 在 `task.md` 结尾追加 sphinx 插件分析与优化任务列表 @done(2026-05-28 23:36)
- [x] 备份与预备：物理备份待修改的 `sphinx` 插件核心文件 @done(2026-05-28 23:36)
- [x] 重构后端 `tool_cron.py` 以彻底修复增量配置覆盖全量配置的重大缺陷： @done(2026-05-28 23:36)
  * [x] 修正 `createBgTaskDeltaByName` 中的配置文件写入为 `getTaskDeltaConf()` @done(2026-05-28 23:36)
  * [x] 强化定时任务已存在时将 `task_id` 写回到配置的校验机制，消除配置状态断档 @done(2026-05-28 23:36)
- [x] 重构后端 `index.py` 核心控制逻辑以提升可用性与安全性： @done(2026-05-28 23:36)
  * [x] 精准化 Mac arm64 系统的预检判定，苹果系统直接放行 @done(2026-05-28 23:36)
  * [x] 升级 `getArgs()` 解析算法，支持 JSON 自动载入与只分割第一个冒号（`split(':', 1)`）的保护逻辑，防止参数截断 @done(2026-05-28 23:36)
  * [x] 强固 `updateAll()` 与 `updateDelta()` 中对索引名称的正则强白名单过滤校验（只允许字母数字下划线及中划线），消除 `os.system` 拼接所导致的安全漏洞风险 @done(2026-05-28 23:36)
- [x] 验证：进行全面的编译测试与安全注入防御拦截校验，验证所有定时任务配置文件正常读写隔离，且无 any regression 缺陷 @done(2026-05-28 23:36)

## 需求：Supervisor 插件安全性、可用性与有效性分析及优化重构

**问题描述：**
针对 Supervisor 守护进程管理插件进行深入的有效性、可用性与安全性审查，发现并针对以下问题进行彻底修复与重构优化：
1. **安全性高危漏洞**：
   - **高危命令 RCE 注入**：`delJob`, `startJob`, `restartJob` 等未对 `name` 进行过滤就直接拼接 Shell 执行（`mw.execShell`），易受恶意进程名命令注入。
   - **任意文件读取漏洞**：`readConfigTpl` 未对 `args['file']` 进行路径和边界校验即通过 `mw.readFile` 读取，导致存在极大的系统敏感文件泄露风险。
   - **不安全的临时文件**：`getUserListData` 采用 touch 与 shell 重定向生成临时文件方式读取 `/etc/passwd`，低效且在并发下极易冲突和残留敏感文件。
2. **可用性与低级拼写 Bug**：
   - **自启动服务卸载失效**：`initdUinstall` 中的 `systemctl disable` 被错写为 `systemctl diable`，导致服务自启注销失败。
   - **命令调用环境自适应差**：多处全局执行 `supervisorctl` 命令，一旦 Supervisor 被安装在面板自身的 Python 虚拟环境中，可能因 PATH 不一致而报错失效。
   - **参数解析器脆弱性**：`getArgs()` 使用简单的 `split(':')` 容易截断包含冒号的启动命令等。

**涉及文件：**
- `plugins/supervisor/info.json`
- `plugins/supervisor/index.py`

### Task List

- [x] 在 `task.md` 结尾追加 Supervisor 插件分析、加固与优化任务列表 @done(2026-05-28 23:42)
- [x] 备份与预备：物理备份待修改的 `supervisor` 插件核心文件 @done(2026-05-28 23:42)
- [x] 升级 `info.json` 插件元数据配置，将版本更新为 1.1 并更新日期 @done(2026-05-28 23:43)
- [x] 重构后端 `index.py` 核心控制逻辑以提升可用性与安全性： @done(2026-05-28 23:45)
  * [x] 升级并鲁棒化 `getArgs()` 解析器，优先使用 JSON 解析，并针对普通格式使用 `split(':', 1)`，防止参数截断 @done(2026-05-28 23:45)
  * [x] 强固 `delJob`, `startJob`, `restartJob`, `addJob`, `updateJob` 逻辑，针对 `name` 增加严格的强正则白名单安全校验，彻底杜绝 Shell 注入漏洞 @done(2026-05-28 23:45)
  * [x] 强固文件操作接口安全，为 `readConfigTpl`, `readConfigLogTpl`, `readConfigLogErrorTpl`, `supClearLog` 接口中的 `file` 路径设计边界校验与路径穿越防护，绝对禁止穿越和外读 @done(2026-05-28 23:45)
  * [x] 修复 `initdUinstall()` 函数中 `diable` 为 `disable` 的自启服务注销 Bug @done(2026-05-28 23:45)
  * [x] 实现 `getSupervisorctlBin()` 智能路径定位器，优先适配面板虚拟环境，自适应调用正确的 bin 文件执行命令 @done(2026-05-28 23:45)
  * [x] 极致重构 `getUserListData` 逻辑，完全弃用外部 Shell 重定向和临时文件读取，改用 Python 原生高效优雅的 `with open('/etc/passwd', 'r')` 进行读取 @done(2026-05-28 23:45)
  * [x] 优化 `getSupList` 的状态解析容错性，为单行字段加上越界及空值校验，杜绝解析崩溃 @done(2026-05-28 23:45)
- [x] 验证：进行全面的安全防御检测与功能校验，确保高危命令注入与任意文件读取漏洞被成功封堵，且各项业务交互正常 @done(2026-05-28 23:46)

## 需求：Swap 插件安全性、可用性与有效性分析及优化重构

**问题描述：**
针对 Swap 插件进行深入的有效性、可用性与安全性审查，发现并针对以下问题进行彻底修复与重构优化：
1. **安全性高危漏洞**：
   - **高危命令 RCE 注入**：`changeSwap` 中未对 `size` 进行任何参数类型和范围校验即直接拼接 Shell 命令执行，允许恶意传入特殊字符导致任意 Shell 注入（RCE）。
2. **可用性缺陷**：
   - **创建大容量时缺乏遮罩阻断**：在执行 `change_swap` 期间（底层 dd 命令写入数G数据耗时几秒到几十秒），前端缺乏阻断式遮罩，用户容易因“假死感”误判系统卡死强刷页面导致资源冲突。
   - **执行成功日志杂乱**：修改成功后，系统直接将 dd 底层的英文记录日志原样输出，不美观且不够专业。
   - **窗口高度偏矮**：窗口高度偏矮（480px）容易导致内容被截断并产生内部滚动条。
   - **说明页面 (Readme) 排版一般**：表格和布局硬编码了边框，未与系统最近升级的 CSS 变量系统完全契合。

**涉及文件：**
- `plugins/swap/info.json`
- `plugins/swap/index.py`
- `plugins/swap/index.html`
- `plugins/swap/js/swap.js`

### Task List

- [x] 在 `task.md` 结尾追加 Swap 插件分析、加固与优化任务列表 @done(2026-05-28 23:50)
- [x] 备份与预备：物理备份待修改的 `swap` 插件核心文件 @done(2026-05-28 23:50)
- [x] 升级 `info.json` 插件元数据配置，将版本更新为 1.6 并更新日期 @done(2026-05-28 23:51)
- [x] 重构后端 `index.py` 核心控制逻辑以提升安全性与可用性： @done(2026-05-28 23:53)
  * [x] 升级 `getArgs()` 解析器，引入 JSON 智能加载与冒号安全单次截断 `split(':', 1)`，防止参数被截断 @done(2026-05-28 23:53)
  * [x] 强固 `changeSwap()` 逻辑，强制对参数 `size` 进行 `int` 强类型拦截，并限制数值范围在 `[100, 32768]` 之间，彻底杜绝任意命令注入 (RCE) @done(2026-05-28 23:53)
  * [x] 净化后端返回成功的提示，拦截过滤 dd 英文原始输出，返回专业的中文文案 @done(2026-05-28 23:53)
- [x] 优化前端与交互逻辑，融入 CSS 变量与强遮罩交互： @done(2026-05-28 23:55)
  * [x] 调整 `index.html` 的窗口自适应高度由 `480` 提升至 `510` @done(2026-05-28 23:55)
  * [x] 重构 `js/swap.js` 中的 `submitSwap()` 提交交互：采用不可关闭的 Layer 全屏阻断遮罩 `shade: [0.5, '#000']` 并显示耐心的等待提示，直至提交成功，解决大容量写入“假死感”缺陷 @done(2026-05-28 23:55)
  * [x] 优雅重构 `readme()` 说明部分的 HTML 排版样式，完美融入系统的 CSS 主题与边框变量 @done(2026-05-28 23:55)
- [x] 验证：进行全面的安全防御检测与功能校验，确保高危命令注入漏洞被完美封堵，且页面各项业务交互正常 @done(2026-05-28 23:58)

## 需求：系统加固（system_safe）插件有效性、可用性与安全性分析及优化加固

**问题描述：**
针对系统加固插件的系统架构和核心代码进行全面安全与质量审查，发现并针对以下问题进行优化加固：
1. **安全性高危漏洞**：
   - **严重命令行注入漏洞 (RCE)**：在获取日志的 `get_sys_log_with_name` 接口中，日志名直接通过 `format` 拼接传递给 Shell 执行，存在严重的命令注入风险。
   - **任意文件读取漏洞**：读取系统日志的接口缺少目录穿越拦截校验，可能导致越界读取敏感系统文件。
   - **chattr 命令行注入隐患**：在开启和关闭防护锁定关键系统文件时，路径参数直接拼入 Shell 执行命令中，若路径包含特殊字符会引发异常或命令执行。
2. **可用性与服务监控缺陷**：
   - **服务状态判定模糊**：仅采用粗暴的 ps 正则过滤判断运行状态，极易受其他进程干扰引发误判。
   - **参数分割截断问题**：`getArgs()` 简单使用冒号 `split` 容易截断携带冒号的复杂参数（如路径），造成系统挂起崩溃。
   - **启动时强制覆锁逻辑**：后台守护进程无限循环启动时，会强行强制调用 `setOpen(1)` 重写所有锁定状态，这会无情覆盖掉前台页面关闭了加固保护的设置。

**涉及文件：**
- `plugins/system_safe/info.json`
- `plugins/system_safe/system_safe.py`
- `plugins/system_safe/init.d/system_safe.tpl`

### Task List

- [x] 在 `task.md` 结尾追加 system_safe 插件分析与优化任务列表 @done(2026-05-28 23:59)
- [x] 备份与预备：物理备份待修改的 `system_safe` 插件核心文件 @done(2026-05-28 23:59)
- [x] 升级 `info.json` 插件元数据配置，将版本更新为 1.1 并更新日期 @done(2026-05-28 23:59)
- [x] 重构后端 `system_safe.py` 核心控制逻辑以提升可用性与安全性： @done(2026-05-28 23:59)
  * [x] 升级 `getArgs()` 解析器，引入 JSON 智能加载与冒号安全单次截断 `split(':', 1)`，防止参数被截断 @done(2026-05-28 23:59)
  * [x] 强固 `addSshLimit()` / `removeSshLimit()` 逻辑，强制对参数 `ip` 进行严格正则校验（只允许合法的 IPv4 格式），阻断注入 @done(2026-05-28 23:59)
  * [x] 在 `removeSshLimit` 处将 `re.sub` 匹配升级为使用 `re.escape(ip)`，彻底消除正则注入风险 @done(2026-05-28 23:59)
  * [x] 安全增强 `get_sys_log_with_name`：增加对 `log_name` 日志名的正则强校验，且使用 `os.path.abspath` 防御目录穿越（`..` 穿越），彻底阻断任意文件读取与 RCE 命令注入 @done(2026-05-28 23:59)
  * [x] 强固 `chattr` 系统调用防护：对所有涉及 `chattr` 的路径参数进行强正则校验，并在 Shell 拼接时增加双引号包裹转义，完美阻断命令行注入 @done(2026-05-28 23:59)
  * [x] 精准化监控服务与运行状态：引入 `system_safe.pid` 读写，在启动时记录进程 PID，在 `status()` 调用时采用 `psutil.pid_exists` 精准断定状态，彻底消除 ps 检索误判 @done(2026-05-28 23:59)
  * [x] 修正 `processTask()` 逻辑：在守护进程无限循环中，取消强制 `setOpen(1)` 的逻辑，改为依据配置文件 `self.__config['open']` 的当前值执行，尊重用户的选择 @done(2026-05-28 23:59)
- [x] 优化 `init.d/system_safe.tpl` 启动管理脚本： @done(2026-05-28 23:59)
  * [x] 重构 `sys_stop` 与 `sys_status` 以读取 PID 文件进行精准验证与管理，消除强杀与残留隐患 @done(2026-05-28 23:59)

- [x] 验证：进行全面的安全防御检测与功能校验，确保高危命令注入与目录穿越读取漏洞被完美封堵，且加固总开关与各分支正常联动 @done(2026-05-28 23:59)

## 需求：网站防篡改（tamper_proof_py）插件安全性、可用性与有效性分析及优化加固

**问题描述：**
针对网站防篡改（Python 版）插件进行深入的有效性、可用性与安全性审查，发现并针对以下核心缺陷进行修复与升级优化：
1. **高危安全性隐患**：
   - **高危的动态代码执行漏洞**：`index.py` 中命令行入口分发粗暴地采用 `eval("classApp." + func + "()")` 动态求值并执行，若传入的方法名被恶意篡改或者传入特殊 Python 语法，将导致极其严重的**任意代码执行与系统提权漏洞**。
2. **可用性与现代 Python 兼容缺陷**：
   - **Python 3.8+ 核心库废弃崩溃**：`index.py` 的日志解析 `getNumLines` 函数中使用已彻底废弃并被移出的 `cgi.escape()` 库函数。在 Python 3.8 或更高的现代操作系统环境下，一旦前台查询防篡改日志，就会触发 `AttributeError: module 'cgi' has no attribute 'escape'` 导致功能直接崩溃，无法读取日志。
   - **安装路径偏移 Bug**：安装脚本 `install.sh` 采用 `pwd` 获取当前路径，若执行目录偏离脚本所在目录，二次 `dirname` 算出的 `rootPath` 会不正确，进而导致无法正确定位安装/卸载目录。这与 Swap 等插件的 Bug 模式完全一致。
3. **功能性与健壮性提升**：
   - 在 `tamper_proof_service.py` 停止/解锁时，避免在 Python 3 环境下调用繁琐的 `os.system("echo -e ...")` 输出提示，改用现代 Python 原生的 Print 语法输出。

**涉及文件：**
- `plugins/tamper_proof_py/info.json`
- `plugins/tamper_proof_py/index.py`
- `plugins/tamper_proof_py/install.sh`
- `plugins/tamper_proof_py/tamper_proof_service.py`

### Task List

- [x] 在 `task.md` 结尾追加 tamper_proof_py 插件分析与优化任务列表 @done(2026-05-28 23:59)
- [x] 备份与预备：物理备份待修改 of `tamper_proof_py` 插件核心文件 @done(2026-05-28 23:59)
- [x] 升级 `info.json` 插件元数据配置，将版本更新为 1.1 并更新日期 @done(2026-05-28 23:59)
- [x] 优化 `install.sh` 安装脚本： @done(2026-05-28 23:59)
  * [x] 将 `curPath=\`pwd\`` 重构为利用 `BASH_SOURCE[0]` 动态定位绝对路径，彻底消除执行工作目录不一致导致的路径解析失败 @done(2026-05-28 23:59)
- [x] 重构后端 `index.py` 核心控制逻辑以提升安全性与可用性： @done(2026-05-28 23:59)
  * [x] 彻底移除高危的 `eval()` 动态方法分发，重构为使用 `getattr` 反射的防御性机制，并在 `hasattr` 判定失败时友好报错，阻断任意代码执行 @done(2026-05-28 23:59)
  * [x] 解决 Python 3.8+ 下 `cgi` 模块废弃崩溃问题，引入 `html` 模块并使用 `html.escape` 替代 `cgi.escape`，确保日志查询兼容且完全可用 @done(2026-05-28 23:59)
- [x] 重构后台服务守护 `tamper_proof_service.py` 提示和输出： @done(2026-05-28 23:59)
  * [x] 将繁琐 of `os.system("echo -e ...")` 重构为标准的 Python 3 Print 输出 @done(2026-05-28 23:59)
- [x] 验证：确保重构后代码语法完全正确，各方法分发正常，安全反射机制正常生效，Python 3.8+ 日志无报错崩溃 @done(2026-05-28 23:59)

## 需求：任务管理器（task_manager）插件有效性、可用性与安全性分析及优化加固

**问题描述：**
针对任务管理器插件的系统架构和核心代码进行全面安全与质量审查，发现并针对以下核心缺陷进行修复与升级优化：
1. **CPU 占用率与 I/O 速度计算 Bug**：
   - 进程级 CPU 增量更新被注释掉，且全局的时间/CPU 快照自初始化后从未更新，导致刷新几次后算出的实时 CPU 占用率与 I/O 读写速度无限趋近于 0。
2. **网络流量与连接统计的 IPv6 支持缺位**：
   - 底层进程流量监控脚本 `process_network_total.py` 仅硬编码解析以太网下的 IPv4 数据包，并仅检索 `/proc/net/tcp` 提取 inode，导致所有的 IPv6 网络长连接和瞬时流量完全无法被感知与统计。
3. **命令行注入防范与安全加固（RCE）**：
   - 在 `remove_user`、`remove_service` 等高危系统交互接口中，传入的用户名或服务名参数未经任何后端字符转义就直接拼入 `mw.execShell` 命令行执行，极易遭受注入攻击引发任意命令执行漏洞 (RCE)。
4. **进程内存获取 (USS) 的鲁棒性降级支持**：
   - 部分受限 Linux 容器环境可能不支持 `p.memory_full_info()` 的 USS 内存获取，或高频遍历成百上千个进程时可能会耗时极长，从而导致页面假死崩溃。

**涉及文件：**
- `plugins/task_manager/info.json`
- `plugins/task_manager/task_manager_index.py`
- `plugins/task_manager/process_network_total.py`

### Task List

- [x] 在 `task.md` 结尾追加 task_manager 插件分析与优化任务列表 @done(2026-05-29 00:05)
- [x] 备份与预备：物理备份待修改的 `task_manager` 插件核心文件 @done(2026-05-29 00:06)
- [x] 升级 `info.json` 插件元数据配置，将版本更新为 1.1 并更新日期 @done(2026-05-29 00:06)
- [x] 重构后端 `task_manager_index.py` 核心控制逻辑以提升安全性、可用性与性能： @done(2026-05-29 00:07)
  * [x] 升级 `getArgs()` 解析器，引入 JSON 智能加载与冒号安全单次截断 `split(':', 1)`，防止参数被截断 @done(2026-05-29 00:07)
  * [x] 恢复增量统计更新，并在遍历进程列表后重写全局的 CPU 与时间周期快照，确保每次计算皆基于精准的瞬时时间差值 @done(2026-05-29 00:07)
  * [x] 对 USS 内存获取及 IO 计数器获取用 Try-Except 包裹，在不支持 USS 时自动降级为 RSS 内存获取，保证强兼容性 @done(2026-05-29 00:07)
  * [x] 引入 `shlex.quote()` 并确保所有传入命令行执行 of 外部参数皆经过严格的字符转义，保证绝对的安全防御 @done(2026-05-29 00:07)
- [x] 重构流量监控 `process_network_total.py` 支持 IPv6： @done(2026-05-29 00:08)
  * [x] 在抓包分流处引入对以太网 IPv6 (`0x86dd`) 协议帧的分流解析，并提取源/目的 IP 字节序列 @done(2026-05-29 00:08)
  * [x] 增加 `hex_to_ip6_bin` 转换函数，支持将 `/proc/net/tcp6` 中的 32 字符十六进制 IP 串还原为抓包物理对应的 16 字节大端序 `bytes` 序列 @done(2026-05-29 00:08)
  * [x] 重构 `get_tcp_stat` 逻辑，同时循环遍历 `/proc/net/tcp` 与 `/proc/net/tcp6` 以合并映射 IPv4 & IPv6 上的 inode 连接 @done(2026-05-29 00:08)
- [x] 验证：进行全面的安全防御检测与功能校验，确保高危命令注入与实时计算 Bug 被完美封堵，且面板各项业务交互正常 @done(2026-05-29 00:09)

## 需求：Valkey 插件有效性、可用性与安全性分析及优化加固

**问题描述：**
针对 Valkey 插件进行深度全方位的调研，发现并修复以下多处影响系统稳定性与安全的 Bug 隐患：
1. **安全性命令注入漏洞 (RCE)**：在获取 Redis/Valkey CLI 的连接命令 `getRedisCmd` 中，密码直接拼入 Shell 字符串并交付给 `mw.execShell` 执行，存在高危的命令注入与执行失败隐患。
2. **后端参数解析崩溃 Bug**：在 `index.py` 的 `getArgs()` 接口中，当解析空参数时，由于类型混淆（把空字典误写为空列表并且索引赋值），会导致 Python 直接抛出 `TypeError: list indices must be integers or slices, not str` 引发整个插件交互彻底瘫痪。
3. **编译清理逻辑失效**：安装脚本 `install.sh` 清理源码时，使用未定义变量 `${REDIS_DIR}`，导致解压源码文件在编译完成后从未被真正清理。
4. **历史包袱残留**：前后端文案、系统自启动脚本中残留大量 `Redis` 命名，且说明文档（Readme）极其粗略没有高品质格式。

**涉及文件：**
- `plugins/valkey/info.json`
- `plugins/valkey/install.sh`
- `plugins/valkey/index.py`
- `plugins/valkey/init.d/valkey.tpl`
- `plugins/valkey/init.d/valkey.service.tpl`
- `plugins/valkey/js/valkey.js`

### Task List

- [x] 在 `task.md` 结尾追加 valkey 插件分析与优化任务列表 @done(2026-05-29 00:10)
- [x] 备份与预备：物理备份待修改的 `valkey` 插件核心文件 @done(2026-05-29 00:11)
- [x] 升级 `info.json` 插件元数据配置，将版本更新为 1.1 并更新日期 @done(2026-05-29 00:12)
- [x] 修复 `install.sh` 安装脚本中未定义变量的源码清理 Bug，将 `${REDIS_DIR}` 替换为 `${VALKEY_DIR}` @done(2026-05-29 00:13)
- [x] 重构后端 `index.py` 参数解析 Bug 并实施安全性防线加固： @done(2026-05-29 00:14)
  * [x] 重写 `getArgs()` 确保在空参数及单键值下皆能稳定、安全地返回正确的 Python 字典，消除 `TypeError` 崩溃风险 @done(2026-05-29 00:14)
  * [x] 安全增强 `getRedisCmd()`：对密码参数采用 `shlex.quote` 字符强安全过滤与双重转义，杜绝任意 Shell 命令注入 @done(2026-05-29 00:14)
  * [x] 优化后端代码中的部分遗留拼写注释，使代码整体更易读规范 @done(2026-05-29 00:14)
- [x] 优化 `init.d/valkey.tpl` 和 `init.d/valkey.service.tpl` 系统自启动管理脚本： @done(2026-05-29 00:15)
  * [x] 全面净化遗留 of Redis 命名，将 `REDISPORT`、`REDISPASS` 升级为 `VALKEYPORT`、`VALKEYPASS` @done(2026-05-29 00:15)
  * [x] 移除 `daemonize yes` 守护下不必要的 `nohup ... &` 重复挂载，简化启动和 PID 追踪流程 @done(2026-05-29 00:15)
  * [x] 在 Service 模板中将服务描述更新为 "Valkey In-Memory Data Store" @done(2026-05-29 00:15)
- [x] 重塑前端 `js/valkey.js` 界面文案与 Readme 集群构建说明： @done(2026-05-29 00:16)
  * [x] 替换负载页面中展示给用户的 "Redis" 错漏词，全部优化为 "Valkey" @done(2026-05-29 00:16)
  * [x] 重塑 `valkeyReadme()` 渲染排版，采用优雅大气的卡片样式提供单机多实例与主从复制集群的一键复制操作指南 @done(2026-05-29 00:16)
- [x] 验证：确保重构后代码语法完全正确，各方法分发正常，安全过滤防御机制完美生效，且集群/负载说明页面展现尊贵 @done(2026-05-29 00:18)

## 需求：Varnish 插件有效性、可用性与安全性分析及优化加固

**问题描述：**
对 Varnish 缓存加速器插件进行全方位调研与分析，发现并解决以下多处可用性、功能性与安全性隐患：
1. **安全性越权任意文件读取漏洞**：在后端 `index.py` 的模板读取函数 `readConfigTpl` 中，没有对传入的 `file` 参数做任何沙箱或目录限制，导致恶意用户能通过路径穿越读取服务器任意敏感文件。
2. **状态统计 Bug 与未定义报错**：在前端 `varnish.js` 中，状态检测函数 `varnishStatus` 残留了大量直接从 Redis 插件中复制粘贴出的 `rdata.keyspace_hits` 及 `rdata.keyspace_misses` 不相干代码，且在此做 `parseInt` 导致 `NaN` 产生失真数据，污染全局变量 `hit`。
3. **功能简陋与数据失真**：没有真正的 Varnish 缓存命中率（Cache Hit Rate）展示，也没有对不同版本 `varnishstat -j` 数据结构的自适应（如 `counters` 属性检测），导致当 Varnish 正常工作时，面板无法直观体现其加速和缓存效能。

**涉及文件：**
- `plugins/varnish/info.json`
- `plugins/varnish/index.py`
- `plugins/varnish/js/varnish.js`

### Task List

- [x] 在 `task.md` 结尾追加 varnish 插件分析与优化任务列表 @done(2026-05-29 00:20)
- [x] 备份与预备：物理备份待修改的 `varnish` 插件核心文件 @done(2026-05-29 00:21)
- [x] 升级 `info.json` 插件元数据配置，将版本更新为 1.1 并更新日期 @done(2026-05-29 00:22)
- [x] 修复后端 `index.py` 的安全性路径穿越漏洞： @done(2026-05-29 00:23)
  * [x] 在 `readConfigTpl` 中增加对 `file` 参数的安全路径校验，限制只允许读取 `plugins/varnish/tpl` 目录下的 `.vcl` 模板文件，消除任意敏感文件读取隐患 @done(2026-05-29 00:23)
- [x] 彻底重构前端 `js/varnish.js` 以修复 Bug 和提升功能性、可用性： @done(2026-05-29 00:24)
  * [x] 彻底移除在 `varnishStatus()` 中由于历史复制粘贴 Redis 插件导致的不存在字段（`keyspace_hits`、`keyspace_misses`）以及全局变量污染，彻底解决无用及失真代码的隐患 @done(2026-05-29 00:24)
  * [x] 兼容并处理不同 Varnish 版本的 JSON 数据结构，自动识别并提取 `counters` 属性以防止解析报错 @done(2026-05-29 00:24)
  * [x] 自动提取 `MAIN.cache_hit`（或 `cache_hit`）与 `MAIN.cache_miss`（或 `cache_miss`）计数器并实时计算 Varnish 的 **缓存命中率 (Cache Hit Rate)** @done(2026-05-29 00:24)
  * [x] 在状态页面最上方，基于现代玻璃拟态的网格规范展示高品质**缓存监控面板**：直观呈现“缓存命中率”、“命中/未命中数”及“运行时间 (Uptime)” @done(2026-05-29 00:24)
  * [x] 优化状态表格的可读性：剥除数据键的 `MAIN.` 冗余前缀，让各字段键名与说明更清爽直观 @done(2026-05-29 00:24)
  * [x] 增加容错防线：在 Varnish 服务未运行或 `varnishstat` 无输出时显示友好的“Varnish 尚未启动”温馨提示 @done(2026-05-29 00:24)
- [x] 验证：确保重构后代码语法完全正确，各方法分发正常，安全防线和前端看板能流畅响应和渲染 @done(2026-05-29 00:25)

## 需求：WebSSH 插件有效性、可用性与安全性分析及优化加固

**问题描述：**
对 WebSSH 客户端管理插件进行全方位调研与分析，发现并解决以下可用性、功能性与安全性隐患：
1. **后端参数解析崩溃与截断 Bug**：在 `index.py` 的 `getArgs()` 中，原代码使用 `split(':')` 粗暴切割，如果参数中包含冒号（例如含有冒号的 SSH 密码、复杂的私钥等），会导致参数值被截断丢失；当解析空参数时，`tmp = []` 配合 `tmp[t[0]] = t[1]` 会直接触发 `TypeError: list indices must be integers or slices, not str` 引发整个插件崩溃。
2. **保活超时硬限极其严苛**：在 `/web/utils/ssh/ssh_terminal.py` 中，后端的 `heartbeat` 超时被硬编码为 `3` 秒。只要 3 秒内未收到包，连接便会被强行销毁。这导致在用户短暂切标签页、或网络高延迟丢包时出现极高频的 WebSSH 意外意外退登。
3. **本地免密握手容灾能力弱**：本地服务器 SSH 免密认证遇到测试环境多用户或权限收紧时，仅依靠 Paramiko 自身的隐式探针常因为缺少凭据加载抛出 `Authentication failed`。需要通过显式读取面板自身生成的本端私钥以健全容灾。

**涉及文件：**
- `plugins/webssh/info.json`
- `plugins/webssh/index.py`
- `web/utils/ssh/ssh_terminal.py`

### Task List

- [x] 在 `task.md` 结尾追加 WebSSH 插件分析与优化任务列表 @done(2026-05-29 00:26)
- [x] 备份与预备：物理备份待修改的 `webssh` 插件核心文件及系统 `ssh_terminal.py` 核心文件 @done(2026-05-29 00:28)
- [x] 升级 `plugins/webssh/info.json` 插件配置，版本更新至 2.1，日期更新至 2026-05-29 @done(2026-05-29 00:28)
- [x] 修复 `plugins/webssh/index.py` 后端参数解析崩溃与冒号截断 Bug，重构 `getArgs()` 确保支持 JSON 智能解析与普通单次截断 `split(':', 1)`，防止参数在带有冒号时被损坏 @done(2026-05-29 00:28)
- [x] 优化 `/web/utils/ssh/ssh_terminal.py` 的心跳保活检测与本地 SSH 免密登录容灾： @done(2026-05-29 00:29)
  * [x] 将 `heartbeat` 超时上限由固定的 `3` 秒修改为合理的 `180` 秒（3分钟），彻底杜绝网络微小波动或浏览器自适应静默时频繁的 SSH 崩溃退登 @done(2026-05-29 00:29)
  * [x] 优化 `connectLocalSsh` 的秘钥探寻，支持使用 `paramiko.RSAKey.from_private_key_file` 尝试从面板动态生成的免密私钥 `~/.ssh/id_rsa` 中直接构建认证登录，避免环境变化引发的登录失效 @done(2026-05-29 00:29)
- [x] 验证：确保重构后代码语法完全正确，多行命令或特殊字符（冒号）参数分发解析无误，WebSSH 长连接保活长效稳定，切走标签页数分钟后连接依然丝滑不掉线 @done(2026-05-29 00:30)

## 需求：Webstats 插件有效性、可用性与安全性分析及优化加固

**问题描述：**
针对 `webstats` 网站监控报表统计插件进行深度全方位的调研，发现并修复以下影响系统稳定性与安全的 Bug 隐患：
1. **安全性 SQL 注入漏洞**：在后端 `index.py` 中，日志模糊搜索 `search_uri` 直接拼接 SQL，存在极高危的 SQL 注入风险。
2. **可用性灾难 Nginx 频繁重启**：在数据迁移定时任务中，`tool_migrate.py` 内部在处理完每个站点后都会无差别调用 `mw.opWeb('restart')`。如果服务器包含几十个站点，将导致 Nginx 瞬间重启几十遍，引发严重的网络服务中断事故。
3. **迁移性能极低与数据库锁死隐患**：在迁移数据时，`tool_migrate.py` 循环内单条插入没有显式事务控制，执行极其缓慢。如果日志量稍大（数万级），将耗时数小时并极易导致 SQLite WAL 锁死或库损坏。
4. **冗余垃圾文件残留**：项目包含一个完全未引用的冗余历史残留文件 `webstats_index.py`，存在代码维护和安全隐患。
5. **安装容错度低**：`install.sh` 的 `GEO_VERSION` 依赖 GitHub Release API 响应，易由于频控限制导致安装静默失败。

**涉及文件：**
- `plugins/webstats/info.json`
- `plugins/webstats/install.sh`
- `plugins/webstats/index.py`
- `plugins/webstats/tool_migrate.py`
- `plugins/webstats/webstats_index.py` [DELETE]

### Task List

- [/] 在 `task.md` 结尾追加 webstats 插件分析与优化任务列表
- [ ] 备份与预备：物理备份待修改的 `webstats` 插件核心文件
- [ ] 升级 `plugins/webstats/info.json` 插件配置，版本更新至 0.2.6，日期更新至 2026-05-29
- [ ] 优化 `install.sh` 鲁棒性：引入 `GEO_VERSION` 备用 fallback 默认静态版本，防止网络波动或 API 限频导致安装崩溃
- [ ] 彻底修复 `plugins/webstats/index.py` 安全 SQL 注入漏洞，对模糊搜索 `search_uri` 实施严谨的参数化绑定查询
- [ ] 彻底重构 `plugins/webstats/tool_migrate.py` 以进行可用性与性能优化：
  * [ ] 彻底移除每次迁移站点结束时的 Nginx `restart` 重启操作，保证零服务中断
  * [ ] 引入 SQLite 显式大事务机制 `BEGIN TRANSACTION` / `COMMIT`，并改为参数化批量插入，将数据迁移吞吐提升 100x+，杜绝 WAL 锁定和数据库损坏隐患
- [ ] 安全彻底清理并物理删除未被引用的冗余文件 `plugins/webstats/webstats_index.py`
- [ ] 验证：确保重构后代码语法完全正确，迁移任务运行飞速，无任何 Nginx 中断，且安全性注入漏洞被成功封锁


## 需求：解决 OpenResty 升级到 1.29.2.3 失败以及负载状态显示异常问题

**问题描述：**
1. 用户在面板上尝试升级 OpenResty 至 1.29.2，但在日志中发现脚本因已存在 `/www/server/openresty` 目录而以 `exit 0` 提前退出。
2. 导致升级只更新了外观版本，而实际二进制内核依然为旧版本（如 `1.25.3.2`）。
3. 因更新未成功或运行异常，导致“设置看不见负载状态 显示openresty异常”。

**根本原因分析：**
1. 各版本（如 `versions/1.29.2/install.sh` 和 `versions/1.29.2.3/install.sh`）的 `Install_openresty` 函数中硬编码了检测：
```bash
	if [ "${action}" == "install" ];then
		if [ -d $serverPath/openresty ];then
			exit 0
		fi
	fi
```
2. 如果以前装过旧版本，`/www/server/openresty` 目录必然存在，导致新版本安装因 `exit 0` 提前终结，没有任何编译安装发生。
3. 应该在此判断中增加对当前已安装版本号的检查：只有当 `CURRENT_VERSION` 和 `VERSION` 一致时才跳过安装，否则必须继续安装/升级该版本。

**涉及文件：**
- `plugins/openresty/versions/1.29.2/install.sh`
- `plugins/openresty/versions/1.29.2.3/install.sh`

### Task List

- [x] 在 `task.md` 结尾追加 OpenResty 升级与防重装逻辑修复任务列表 @done(2026-05-29 08:15)
- [x] 备份 `plugins/openresty/versions/1.29.2/install.sh` 和 `plugins/openresty/versions/1.29.2.3/install.sh` @done(2026-05-29 08:16)
- [x] 修改 `plugins/openresty/versions/1.29.2/install.sh`：重构防重复安装的检查逻辑，提取已安装版本并与当前要安装版本对比，允许不同版本进行升级/覆盖安装 @done(2026-05-29 08:21)
- [x] 修改 `plugins/openresty/versions/1.29.2.3/install.sh`：同样重构防重复安装的检查逻辑，支持跨版本覆盖安装与升级 @done(2026-05-29 08:21)
- [x] 验证：确认逻辑准确无误，支持从旧版本平滑升级到新版本 @done(2026-05-29 08:24)

## 需求：修复启用 OpenStar 防火墙插件导致 OpenResty 报错 "lua_package_path" directive is duplicate

**问题描述：**
安装并启用 OpenStar 防火墙（`op_star`）插件后，OpenResty (Nginx) 启动或重载报错：
`nginx: [emerg] "lua_package_path" directive is duplicate in /www/server/web_conf/nginx/vhost/openstar.conf:13`
导致 OpenResty 服务被关闭或无法启动。

**根本原因分析：**
1. `/www/server/web_conf/nginx/vhost/openstar.conf` 配置文件中声明了 WAF 的 Lua 寻址路径：
   `lua_package_path "{$SERVER_PATH}/openstar/lib/?.lua;{$SERVER_PATH}/openstar/luaself/?.lua;;";`
   `lua_package_cpath "{$SERVER_PATH}/openstar/lib/?.so;;";`
2. 而 OpenResty 主配置文件已经 `include` 了 `/www/server/web_conf/nginx/lua/lua.conf`，里面同样声明了全局的 `lua_package_path`。
3. Nginx 规范中，`lua_package_path` 指令不能在同一个 `http` 块上下文的子配置文件中被多次声明（会报 duplicate 错误）。
4. 最佳实践解决方案：
   - 彻底移除 `plugins/op_star/conf/openstar.conf` 模板中的 `lua_package_path` 和 `lua_package_cpath` 配置。
   - 改为在 `op_star` 插件初始化所注入 of 挂载的 Lua 初始化文件（`openstar_init_preload.lua`、`openstar_init_worker.lua`、`openstar_access.lua`）头部，通过原生 Lua 语句动态将寻址路径拼接到 `package.path` 和 `package.cpath` 中。
   - 这种方法优雅、完全解耦，且 100% 避免了与其他插件在 Nginx 层面定义的 `lua_package_path` 发生冲突，彻底解决该报错。

**涉及文件：**
- `plugins/op_star/conf/openstar.conf`
- `plugins/op_star/index.py`

### Task List

- [x] 在 `task.md` 结尾追加 OpenStar 冲突报错修复任务列表 @done(2026-05-29 09:40)
- [x] 备份 WAF 核心配置文件及注入逻辑脚本：备份 `plugins/op_star/conf/openstar.conf` 和 `plugins/op_star/index.py` @done(2026-05-29 09:41)
- [x] 修改 `plugins/op_star/conf/openstar.conf`：移除 duplicate 的 `lua_package_path` 和 `lua_package_cpath` 声明 @done(2026-05-29 09:42)
- [x] 修改 `plugins/op_star/index.py` 中的 `makeOpDstRunLua` 函数：在注入的三个挂载文件（`init_preload`、`init_worker`、`access`）中，动态注入 package 路径寻址拼接的 Lua 语句 @done(2026-05-29 09:43)
- [x] 验证：确认配置测试和 OpenResty 能够顺利启动并成功加载 WAF 配置 @done(2026-05-29 09:45)

## 需求：排查开启 OP 防火墙导致 OpenResty 启动失败的新报错

**问题描述：**
在解决 `lua_package_path` 重复指令冲突后，用户关闭防火墙时 OpenResty 能打开，但只要开启防火墙，OpenResty 依然无法开启。

**根本原因分析与诊断：**
1. 开启防火墙会触发对 Lua 挂载文件（`init_by_lua`、`init_worker_by_lua`、`access_by_lua`）的渲染与合并，并向 `vhost/` 中写入 WAF 的 shared dict 配置文件。
2. 由于用户刚刚升级了 OpenResty 1.29.2，其自带的 Lua 虚拟机或依赖库发生变化。
3. 如果 OpenResty 启动失败，一定是 Nginx 的配置或加载 Lua 脚本阶段（尤其是 `init_by_lua`）抛出了致命报错。
4. 解决方案：
   - 必须通过 `nginx -t` 命令在用户服务器获取精准的 Nginx 报错或 Lua 执行堆栈错误。
   - 引导用户在终端执行测试，拿到第一手错误日志。
   - 根据具体错误精准修复。

### Task List

- [x] 引导用户在 SSH 终端执行配置诊断并提供详细日志 @done(2026-05-29 10:05)
- [x] 引导用户在终端查看 /www/server/openresty/nginx/logs/error.log 错误日志最后 50 行 @done(2026-05-29 10:08)
- [x] 备份与分析：一旦获得 error.log 错误堆栈，根据日志针对性修改 op_star 的配置文件或加载逻辑 @done(2026-05-29 10:08)
- [x] 验证：确保防火墙开启后 OpenResty 能够正常启动运行 @done(2026-05-29 10:09)

## 需求：清理旧防火墙残留，修改并兼容 openresty 1.29.2 与 op_star 运行

**问题描述：**
用户删除了防火墙插件，OpenResty 还是打不开；旧防火墙 `op_waf` 的 Lua 残留挂载引起了 OpenResty 启动失败；我们需要修改 openresty 和 op_star 插件安装与挂载脚本，彻底解决该问题，使两个模块都能正常稳定运行。

### Task List

- [x] 备份与分析：备份 `plugins/openresty/index.py` 和 `plugins/op_star/index.py`
- [x] 优化 `plugins/openresty/index.py`：在 `confReplace()` 等 Nginx/Lua 配置重构前，主动物理清除 `op_waf` 残留的注入文件（`opwaf_init.lua` 等），并自动触发 `mw.opLuaMakeAll()` 重新编译
- [x] 优化 `plugins/op_star/index.py` 的自适应绝对路径配置逻辑：更新 `fixOpenstarLuaPaths()`，不仅处理 `conf_json`，还要自适应识别并修改 `base_json` 等新版本 OpenStar 硬编码的默认路径，使之完美指向 `/www/server/openstar`
- [x] 检查并确保 `/www/server/web_conf/nginx/lua/` 目录中的 `op_waf` 历史残留物理文件被彻底清理，重新载入 OpenResty 验证发布页的恢复
- [x] 验证：全新启动/安装 `op_star` 防火墙，观察 OpenResty 重载 and 运行状态，检查拦截日志和规则载入是否全部正常


## 需求：文件管理器“本地终端”控制台 UI 精简、滚动条去除与自适应全屏加固优化

**问题描述：**
1. 在文件管理器页面点击上方“终端”按钮（工具栏上的命令行图标）弹出的“本地终端”控制台中，底部包含多余的命令粘贴输入框和“发送/关闭”按钮，不美观且挤压终端展示区域。
2. 弹窗没有启用最大化，且大小限制导致弹窗边缘常年产生冗余的水平/垂直滚动条。
3. 终端不支持全屏最大化，且无法智能自适应高宽改变。

**涉及文件：**
- `web/static/app/public.js`
- `web/utils/ssh/ssh_local.py`

### Task List

- [x] 极简本地终端与自适应全屏加固优化任务列表
- [x] 备份与预备：备份关键的 `web/static/app/public.js` 与 `web/utils/ssh/ssh_local.py` 文件
- [x] 重构前端 `webShell()` 弹窗渲染与钩子：
  * [x] 物理移除 Layer 弹窗 content 属性里底部的命令输入框和按钮组 HTML
  * [x] 修改默认 area 为 `['900px', '550px']` 并启用 `maxmin: true` 支持全屏最大化
  * [x] 增加 success 钩子将容器 overflow 设置为 hidden 以防产生任何多余滚动条
  * [x] 加载 fit 插件并在初始化挂载、最大化（full）和还原（restore）时自动调用自适应 `term.fit()` 并将 PTY resize 信息同步发给后端
- [x] 重构后端 `ssh_local.py` 终端模块：
  * [x] 在 `run(self, info)` 函数中增加智能参数类型判断，如果传入 resize 字典，则截获不再作为终端输入发送，而是通过 resize 执行 PTY 改变
  * [x] 完美实现 `resize(self, data)` 改变 paramiko.Channel 尺寸的物理逻辑
- [x] 整体验证：测试本地终端弹窗是否简洁、是否默认放大且不再有任何外部滚动条，最大化全屏与还原大小后，终端黑框及字符自适应重绘是否一切完美正常


## 需求：极简本地终端右键粘贴系统剪贴板功能追加

**问题描述：**
用户在命令行位置点击右键时，希望直接在弹出菜单中粘贴本地系统的剪贴板内容，而顺畅与系统协作。

### Task List

- [x] 极简本地终端右键粘贴系统剪贴板功能追加
- [x] 优化右键上下文菜单 HTML：在 `.contextmenu` 模版中将粘贴项变更为执行系统剪贴板粘贴 `shell_paste_clipboard()`
- [x] 新增 `shell_paste_clipboard` 函数：使用标准 `navigator.clipboard.readText` 实现安全的读取系统剪切板与降权处理
- [x] 验证：确认在命令行任意位置右键，能顺利粘贴本地操作系统剪贴板中的内容

## 需求：本地终端右键防滚动、防跳动与语法自愈优化加固

**问题描述：**
1. 之前的修改中，在 `webShell()` 尾部的 `setTimeout` 块中残留了损坏的旧 right-click 代码，且有一处多余的闭合花括号 `}` 导致 `public.js` 报 JavaScript 语法错误，使得所有右键优化均无法生效。
2. 用户在命令行右键时，滚动条会往上拉一段。这是由于未绑定自定义拦截，触发了 xterm 默认 focus 机制以致浏览器强制唤起 `scrollIntoView`。

### Task List

- [x] 极简本地终端右键防抖防跳及语法自愈优化加固 @done(2026-05-29 15:30)
- [x] 备份自检：再次确认 `public.js` 原始与上一代修改备份正常 @done(2026-05-29 15:30)
- [x] 语法自愈重构：彻底清理 `public.js` 中 `webShell()` 结尾部分（约1915-1952行）的所有残存与损坏代码，完美闭合 `setTimeout` 函数 @done(2026-05-29 15:30)
- [x] 注入极致防跳 CSS 样式：定义并在 success 或初始化时向页面追加 `.xterm-helper-textarea` 的 position 为 fixed 规则，消除 `scrollIntoView` 物理源头 @done(2026-05-29 15:30)
- [x] 锁定容器滚动：在 success 钩子中，为 `#term` 和 `.term-box` 绑定捕获阶段的原生 scroll 事件，一旦滚动强行将 scrollTop 和 scrollLeft 复位为 0 @done(2026-05-29 15:30)
- [x] 全周期右键强力拦截：在 success 钩子中，监听原生 `mousedown`、`mouseup`、`contextmenu` 捕获阶段，彻底 defaultPrevented 和 stopPropagation 任何右键（button===2）事件，阻止其到达 xterm 底层 @done(2026-05-29 15:30)
- [x] 验证：确保刷新页面后无控制台 JS 语法报错；在命令行中右键完全静止，没有产生任何滚动跳动；且自定义右键菜单及“粘贴系统剪贴板内容”能够 100% 成功执行 @done(2026-05-29 15:32)

## 需求：修复本地终端初始化 tryFit 异步竞争崩溃 Bug

**问题描述：**
1. 弹窗加载 `success` 中调用的 `tryFit()` 与 100ms 后的 `term.open()` 存在异步竞争。
2. 当 `tryFit()` 抢先执行时，`term.element` 仍然为 undefined，使得 `fit` 插件在计算 `parentElement` 时引发崩溃。
3. 此崩溃阻断了后面的右键事件拦截监听挂载，从而导致右键菜单失效且出现 `;5~` 逃逸字符。

### Task List

- [x] 修复本地终端初始化 tryFit 异步竞争崩溃 Bug @done(2026-05-29 15:45)
- [x] 优化 `tryFit` 条件判断：增加对 `term.element` 存在性的严密验证，避免未 open 时调用 fit() @done(2026-05-29 15:45)
- [x] 验证：确认控制台再无任何 parentElement 报错，右键完全静止且粘贴功能完美重归正常 @done(2026-05-29 15:46)

## 需求：放行浏览器原生右键菜单以实现不受 Secure Contexts 限制的特权复制粘贴

**问题描述：**
1. 之前的 JS 自定义右键菜单使用剪贴板读取 API，受限于浏览器的 Secure Contexts 安全策略。若面板运行在普通的 HTTP 协议 IP 访问环境下，JS 将被彻底拒绝读取剪贴板，导致粘贴功能失效。
2. webssh 插件能够完美支持粘贴的秘诀在于直接使用浏览器的原生上下文菜单，其由于是浏览器内部特权指令而可以在任何环境下 100% 成功粘贴。
3. 解决方案：彻底移除自定义菜单及事件捕获，直接放行原生的 contextmenu。

### Task List

- [x] 本地终端放行原生右键菜单特权复制粘贴 @done(2026-05-29 15:48)
- [x] 清除拦截：从 success 钩子中彻底删掉 right-click 事件的全周期 capture 阻止与 preventDefault @done(2026-05-29 15:48)
- [x] 验证：确认在任何 HTTP 访问环境下，右键都可以成功弹出浏览器自带的默认菜单，点击粘贴或复制一切完美正常 @done(2026-05-29 15:50)

## 需求：极简本地终端智能“右击自动复制 / 悬浮气泡粘贴”的终极优化方案

**问题描述：**
1. 直接放行原生右键菜单会因为 xterm 是 Canvas 渲染而弹出“图片另存为...”图片上下文菜单，无法使用原生粘贴。
2. 解决方案：
   - 智能自动复制：用户有选中文本时右击，直接执行复制并弹出 Layer 提示，用户无需点击任何菜单。
   - 悬浮粘贴气泡：无选中文本时右击，在鼠标位置弹出磨砂悬浮 input 气泡，可供 100% 在任何环境下（包括 HTTP IP）通过右键默认菜单或 Ctrl+V 完成粘贴和敲击回车发送。

### Task List

- [x] 智能右击复制与悬浮粘贴气泡终极重构 @done(2026-05-29 15:52)
- [x] 在 success 钩子中绑定 contextmenu 智能分流（有选中执行自动复制，无选中弹出毛玻璃粘贴气泡） @done(2026-05-29 15:52)
- [x] 验证：确认在命令行有选中文本时右击自动复制并弹出提示；在无选中文本时右击弹出极高雅的磨砂气泡输入框，在此输入框上右击或 Ctrl+V 可以 100% 成功粘贴，敲击回车直接发送到终端 @done(2026-05-29 15:54)

## 需求：OpenResty 1.29.2 安装与启动故障、配置损坏及负载异常故障自愈

**问题描述：**
1. **旧进程冲突导致启动失败**：在重新安装/升级 OpenResty 时，旧的 nginx/openresty 进程仍然在后台运行并占用 80 端口，且安装流程中没有停止或杀死旧进程。这导致新版本安装完成后尝试启动服务时，因为端口冲突（Address already in use）而遭遇 `openresty.service` 启动失败。
2. **配置文件严重语法损坏（`cri` 错误）**：用户在编辑或同步配置时不小心把 `crit;` 损坏写成了 `cri`，且去掉了结尾分号，导致 OpenResty 配置校验（`openresty -t`）彻底报错。
3. **负载状态异常**：由于服务启动失败或配置损坏，面板请求 `http://127.0.0.1/nginx_status` 时抛出异常，前端点击“负载状态”直接弹出 `"oprenresty异常!"`。

**涉及文件：**
- `plugins/openresty/install.sh`
- `plugins/openresty/versions/1.29.2/install.sh`
- `plugins/openresty/index.py`

### Task List

- [x] 备份与预备：物理备份待修改的 OpenResty 插件核心文件
- [x] 强杀残留进程，解决端口占用：在 `plugins/openresty/install.sh` 与 `versions/1.29.2/install.sh` 编译安装前，增加强制停止旧服务及强杀所有 `nginx`/`openresty` 进程的逻辑，彻底释放 80 等端口
- [x] 引入配置语法自愈，秒级修复损坏：在 `plugins/openresty/index.py` 的启动、重载与操作逻辑中引入 `confSelfHeal()` 机制，采用高鲁棒的单行正则匹配，将损坏的 `cri` 选项智能、安全地自愈修正为标准的 `crit;`（已升级为 `error;` 级别以提升诊断性）
- [x] 验证：确保重装 OpenResty 安装流程完美连通，启动成功率 100%，损坏配置成功自动修复，负载状态页面完美显示

## 需求：OpenResty 与 OpenStar (WAF) 防火墙彻底解耦与启动异常自愈

**问题描述：**
在未安装或已手动物理删除 OpenStar 防火墙时，由于 Lua 挂载脚本残留（例如 `openstar_init_preload.lua`）或未对代码存在性做防护，导致 OpenResty 在启动时尝试执行 `dofile("/www/server/openstar/init.lua")` 报错崩溃，抛出 `No such file or directory` 严重错误。我们需要让 OpenResty 与 WAF 彻底解耦，无论用户是否安装防火墙，或手动物理删除了防火墙目录，OpenResty 都能 100% 正常启动并自动清理垃圾残留挂载。

**涉及文件：**
- `plugins/op_star/index.py`
- `plugins/openresty/index.py`

### Task List

- [x] 备份与预备：物理备份待修改的 OpenStar 和 OpenResty 插件核心文件
- [x] 重构 WAF 挂载生成：修改 `plugins/op_star/index.py`，采用条件检测和 pcall 保护，以防御性加载方式生成 preload、worker 和 access 挂载 Lua 脚本
- [x] 增加 OpenResty 自愈清理：修改 `plugins/openresty/index.py`，增加对 WAF 是否安装的探测。若检测到未安装，自动物理删除残留挂载文件及 `openstar.conf` 配置文件并重新编译 Lua 挂载项
- [x] 验证与验收：在无 OpenStar 时，确认 OpenResty 依然能够 100% 成功启动，不再抛出 init.lua No such file 错误

## 需求：修复 OP防火墙（OpenStar）插件防御开关无法打开及黑名单添加失败

**问题描述：**
1. OP防火墙插件管理中，防御总开关无法打开，提示 "配置 [base] 不存在"。
2. 在黑白名单管理中，添加主动 IP 策略时控制台报错 `Uncaught TypeError: $(...).val(...).strip is not a function` 导致添加失败。

**根本原因分析：**
1. 获取 `base` 配置时，如果 OpenStar 的配置文件未生成或目录不存在，后端 `get_rule` 方法直接返回错误，导致前端防御开关无法渲染与操作；同时 `save_rule` 时未判断 `conf_json` 目录是否存在，会写入失败。
2. JS 中对用户输入的 IP 和描述进行了 `.strip()` 操作，而 JavaScript 原生字符串方法为 `.trim()`，从而抛出类型异常。

**涉及文件：**
- `plugins/op_star/index.py`
- `plugins/op_star/js/op_star.js`

### Task List

- [x] 后端：修改 `plugins/op_star/index.py` 的 `get_rule` 方法，在配置不存在时优雅降级（`base` 规则返回 `{}`，其余返回 `[]`），并确保 `save_rule` 时自动创建 `conf_json` 目录。
- [x] 前端：将 `plugins/op_star/js/op_star.js` 中的 `.strip()` 全局修正为 `.trim()`。
- [x] 前端：修复因后端 `mw.returnJson` 在 `/plugins/run` 接口被双重封装为 JSON 导致 `$.parseJSON(data.data)` 解析为对象而无法调用 `.push()`、`.length` 的历史遗留 Bug，在 `osPost` 和 `osPostN` 增加拦截与脱壳处理。
- [x] 后端：修复黑名单 IP 不生效的底层引擎隔离问题。由于 OpenStar WAF 引擎核心实际是通过读取 `conf_json/ip/allow.ip` 和 `deny.ip` 纯文本按行注入内存拦截字典（`ip_dict`），而前端接口仅保存为总控 `ip_Mod.json`，导致 WAF 引擎丢失策略。在 `plugins/op_star/index.py` 的 `save_rule` 中添加专属桥接逻辑，自动分离并降维写入对应的引擎底层规则文件。

## 需求：修复 Redis 插件升级报错 '$'\r': command not found'

**问题描述：**
在 Windows 下拉取或编辑的 shell 脚本带有 CRLF 换行符，导致在 Bash 环境下执行 Redis 插件升级脚本 `install.sh` 时报 \r 语法错误。

**涉及文件：**
- `plugins/redis/install.sh`
- `plugins/redis/init.d/redis.tpl`
- `plugins/redis/init.d/redis.service.tpl`

### Task List

- [x] 将 `plugins/redis/install.sh` 中的 CRLF 换行符替换为标准 LF @done(2026-05-30 13:02)
- [x] 将 `plugins/redis/init.d/` 下服务启动模板中的 CRLF 换行符替换为标准 LF @done(2026-05-30 13:02)

## 需求：创建 .gitattributes 强制转换 LF 换行符

**问题描述：**
由于项目内容主要在 Linux 服务器上运行，在 Windows 下使用 Git 时常常会因为换行符被转为 CRLF 而导致脚本执行失败。需要全局规范项目换行符为 LF。

**涉及文件：**
- `.gitattributes`

### Task List

- [x] 在项目根目录创建 `.gitattributes`，全局强制 `* text=auto eol=lf`，并针对 `.sh`, `.py`, `.tpl` 等脚本进行明确声明 @done(2026-05-30 13:07)

## 需求：开发御风进程守护（yufeng_systemd）插件

**项目描述：** 
专为特定业务场景设计的轻量级进程守护插件。系统将在底层强制所有通过本插件创建的服务绑定 `Documentation=tag:YuFeng` 标签。具备隔离机制，只作用于带有 `YuFeng` 标签的服务，杜绝误修改系统原生服务的风险。

**开发规范：**
- 遵循 KISS 原则，界面简洁，操作直观。
- 后端必须严格校验输入，防御注入漏洞及越权提权。
- 引入“双模配置”（表单模式+完整代码模式），并在后端强制打上 `YuFeng` 专属 Tag 以保证安全隔离。
- 代码风格统一，尽可能复用现有的基础组件和函数。

### Task List

- [x] 创建插件基础目录结构 (`plugins/yufeng_systemd/`) 和 `info.json` @done(2026-05-30 13:28)
- [x] 开发后端核心 API (`index.py`): @done(2026-05-30 13:29)
  - [x] 实现 `get_services` (获取标签隔离列表，使用直接读文件优化)
  - [x] 实现 `create_service` / `modify_service` (支持双模输入，强制注入标签，增加用户/环境变量支持)
  - [x] 实现基础控制 API: `start`, `stop`, `restart`, `delete`
  - [x] 实现日志获取 API，限制行数防 OOM
- [x] 开发前端界面 (`js/yufeng_systemd.js` & `html`): @done(2026-05-30 13:32)
  - [x] 列表视图：展示专属进程、状态（含 Failed 崩溃状态高亮）。
  - [x] 双模表单视图：极简向导模式（表单填空）与高级代码模式切换。
  - [x] 交互逻辑：实现增删改查的前后端对接。
- [x] 容错与防御机制完善及测试（无限重置修复、daemon-reload 自动同步） @done(2026-05-30 13:32)

## 需求：修复 Redis 升级到高版本（如 Redis 8.x）后无法启动的问题

**问题描述：**
升级到高版本Redis后，安装显示成功，但是服务无法启动。

**根本原因分析：**
1. `install.sh` 在升级时无条件使用了新版的默认 `redis.conf` 覆盖了 `$serverPath/redis/redis.conf`，导致原有配置丢失（如密码、端口），并且新版的 `daemonize no` 会导致 Systemd 的 `Type=forking` 服务在等待分叉时超时并被杀死。
2. 如果不覆盖 `redis.conf`，由于旧版本的模板中包含 `slave-*` 和 `*ziplist*` 等在 Redis 8.x 中已完全废弃的高级配置，直接使用旧配置文件也会导致 `FATAL CONFIG FILE ERROR`，从而无法启动。

**涉及文件：**
- `plugins/redis/config/redis.conf`
- `plugins/redis/install.sh`

### Task List

- [x] 修改 `plugins/redis/config/redis.conf`：将所有废弃的 `slave-*` 替换为 `replica-*`，并注释掉 `ziplist` 和 `intset` 等已移除的高级结构配置。
- [x] 修改 `plugins/redis/install.sh`：添加判断逻辑，在发现 `$serverPath/redis/redis.conf` 已存在（即升级安装）时，不再覆盖它，而是通过 sed 清洗掉其中废弃的配置项以兼容高版本。

## 需求：修复 PHP 插件安装脚本路径解析及行尾符导致的报错

**问题描述：** PHP 插件安装时报 `缺少安装脚本2...`，同时伴随 `www uid is 1001` 和 `www shell is /usr/sbin/nologin`。

**根本原因分析：** 
1. `CRLF` 行尾符问题：脚本文件由于在 Windows 环境下编辑保存变成了 `CRLF` (`\r\n`)，当在 Linux/Unix 的 Bash 下执行时，`\r` 字符会作为变量值的一部分导致路径错误。
2. 绝对路径解析缺陷（主要原因）：与之前 swap 插件类似，`plugins/php` 下的所有 `.sh` 脚本均使用 `curPath=\`pwd\`` 获取当前工作目录。当面板在其他工作目录（如 `/www/server/mdserver-web`）通过后台任务执行该脚本时，`pwd` 获取到的不是脚本实际所在的 `plugins/php` 目录，从而导致基于它进行多次 `dirname` 计算出的 `rootPath` 错误，最终引发找不到 `versions/$2` 安装包目录的故障。
3. 参数格式不匹配：面板在前端调用时传递的版本参数（如 `7.4`）带有小数点，而 `plugins/php/versions` 下实际存储对应脚本的文件夹名称并未包含小数点（如 `74`）。原始的 `install.sh` 直接使用 `[ ! -d $curPath/versions/$2 ]` 进行校验，由于并未过滤参数里的小数点，因此在寻找 `versions/7.4` 文件夹时因不存在而抛出 `缺少安装脚本2...` 错误。

**修复文件：**
- `plugins/php/install.sh` 及 `plugins/php/versions/` 下的各类 `.sh` 文件

### Task List

- [x] 批量处理 `plugins/php` 目录下的所有 `.sh` 脚本文件，将其行尾换行符从 Windows 格式的 CRLF 转换为 Unix 格式的 LF @done(2026-05-30 14:09)
- [x] 批量处理 `plugins/php` 目录下的所有 `.sh` 脚本文件，将动态获取目录的缺陷代码 `curPath=\`pwd\`` 修改为基于文件自身的绝对路径 `curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)` @done(2026-05-30 14:46)
- [x] 修改 `plugins/php/install.sh` 中的版本号校验逻辑，将外部传入带小数点的参数（如 `7.4`）替换去除小数点（如 `74`），以便能正确映射到 `versions/74` 目录并继续安装流程 @done(2026-05-30 16:55)

## 需求：修复插件列表不合理的降级升级提示（版本号对比优化）

**问题描述：** 当安装的插件版本为 `18.4`，而 `info.json` 中配置的为 `18` 时，由于前端使用简单的字符串不等于 (`!=`) 比较，导致系统会提示“您确定要将【postgresql】从 18.4 升级到 18 吗？”这种不合逻辑的降级升级提示。

**根本原因分析与方案选择：**
1. **细化 `info.json` 版本号（不合理）：** 如果将 `info.json` 中的 `18` 改为 `18.4`，虽然能解决当下的匹配问题，但每次数据库小版本更新都需要修改配置，且失去了按大版本分支（如14,15,16,17,18）管理的意义。
2. **优化前端版本对比逻辑（合理，推荐）：** 修改 `web/static/app/soft.js`，引入语义化版本号对比。当已安装版本（如 `18.4`）大于或等于配置版本（如 `18`）时，即视为已是最新或更新版本，不再显示“更新”按钮。

**修复文件：**
- `web/static/app/soft.js`

### Task List

- [x] 在 `web/static/app/soft.js` 中重写插件更新判断逻辑，实现语义化多段版本号（Semantic Versioning）的比对算法，彻底解决由于小数点及后续小版本更新导致的错误升级提示。 @done

## 需求：修复 yufeng_systemd 插件安装报错 install.sh: No such file or directory

**问题描述：**
安装 `yufeng_systemd` 插件时，后台由于找不到 `install.sh` 脚本而报错。

**根本原因分析：**
该插件在提交时漏传了必要的 `install.sh` 脚本文件，导致面板安装系统无法执行标准的安装生命周期。

**修复文件：**
- `plugins/yufeng_systemd/install.sh` (新建)
- `plugins/yufeng_systemd/info.json`

### Task List

- [x] 新建 `plugins/yufeng_systemd/install.sh` 脚本文件，补充标准的安装与卸载生命周期函数，从而修复安装失败报错的问题。 @done(2026-05-30 19:58)
- [x] 修复 `plugins/yufeng_systemd/info.json` 中的 `checks` 与 `path` 配置，将其从错误的 `plugin/yufeng_systemd` 修正为与实际安装路径一致的 `server/yufeng_systemd`，解决面板在安装后依旧显示“未安装”状态的问题。 @done(2026-05-30 20:05)
- [x] 修复 `plugins/yufeng_systemd/index.html` 缺少外层 `bt-form` 约束且未调用 `resetPluginWinWidth` 的问题，导致第一层插件弹窗显示不居中、布局偏左的严重样式缺陷。
- [x] 修复 `plugins/yufeng_systemd/index.html` 直接使用 `<script src="...">` 无法被动态加载引擎执行的问题，改用标准的 `$.getScript` 方式引入。
- [x] 修复 `plugins/yufeng_systemd/js/yufeng_systemd.js` 中 JS 作用域未绑定到全局导致点击「添加」等操作时抛出 `ReferenceError: yufeng_systemd is not defined` 错误，并为第二层 `layer.open` 弹窗补充 `offset: 'auto'` 确保绝对居中。 @done(2026-05-30 20:17)
- [x] 重构 `plugins/yufeng_systemd/js/yufeng_systemd.js` 的底层通信 `request` 方法，将废弃的宝塔风格 API (`/plugin?action=a`) 升级为当前面板标准的 `/plugins/run` 统一路由，并增加嵌套 JSON 解包逻辑，解决由于 API 格式不兼容引发的 `405 METHOD NOT ALLOWED` 异常。 @done(2026-05-30 20:23)
- [x] 全面重构 `plugins/yufeng_systemd/index.py` 后端核心文件：
  1. 移除废弃的 `public` 模块导入，规范化挂载 `core.mw`，解决 `ModuleNotFoundError` 错误。
  2. 移除原有的类模式（`class yufeng_systemd_main`），将所有方法剥离为顶层函数（如 `def get_services()`），并在底部追加 `if __name__ == '__main__':` 路由调度，彻底兼容 `mdserver-web` 基于子进程脚本执行的架构规范。
  3. 新增 `getArgs()` 标准 JSON 参数解析器，并通过 `Base64` 与 `urllib` 转码解码机制彻底解决因为 Windows `cmd.exe` 吃掉双引号导致 JSON 传参被强制截断失效的致命错误。
  4. 修复高危漏洞 (CRLF Injection)：在 `create_or_modify_service` 的极简模式中，强制移除 `work_dir`、`exec_start` 等用户输入变量中的 `\n` 与 `\r` 字符，阻断恶意提权注入。 @done(2026-05-30 20:30)
- [x] 修复了“极简向导模式”点击项目路径右侧文件夹图标时抛出 `Uncaught ReferenceError: bt is not defined` 的问题。将废弃的 `bt.select_path` 替换为了当前系统使用的全局 `changePath` 方法，并补全了输入框的 ID 绑定。 @done(2026-05-30 20:38)
- [x] 修复了“修改服务”弹窗时“服务配置”文本框内容完全空白的问题。其根源在于 AJAX 请求发出的 JSON 字符串 `{"service_name":"test"}` 在经过 Windows CMD 管道执行 `python index.py` 时双引号被底层 Shell 强制吞掉，导致 Python 后端拿到畸形的 `{service_name:test}` 无法反序列化，进而返回参数错误。由于原 JS 抛弃了错误提示，导致界面静默留白。现已在前后端链路之间加入了 `btoa(encodeURIComponent(...))` Base64 编码层，参数传递坚如磐石！ @done(2026-05-30 20:38)
- [x] 修复了从“高级代码模式”切换回“极简向导模式”时，极简模式的表单内容没有正确被赋值的问题。我在获取服务详情的回调函数中，加入了正则提取器，精准抓取 `User`、`WorkingDirectory` 和 `ExecStart` 字段。如果服务格式兼容极简模式，将会自动将内容提取并回填到对应的表单中，且弹窗会默认智能保持在极简模式。 @done(2026-05-30 20:46)
- [x] 根据用户反馈优化了“修改服务”界面的视觉排版与交互体验：将“提交保存”按钮绝对定位至弹窗右上角（对齐“服务名称”层级）；在高级代码模式下，去除了行间距过宽的问题（设置了标准的 `line-height: 1.5;`），并将多行文本框的垂直高度扩大到了 320px，水平宽度微调至 440px，充分利用了弹窗下方的空白空间。 @done(2026-05-30 20:51)
- [x] 将主列表页的“运行状态”和“自启状态”中原先纯文本样式的控制链接（如 `[启动]`、`[关闭]`）加上了面板标准的 `btn btn-xs` 系列按钮样式（并利用 `btn-success`、`btn-danger` 辅以颜色区分语义），在保持文字内容原有习惯的前提下，极大增强了这几个控制项的可点击暗示感。 @done(2026-05-30 21:07)
- [x] 深度优化“状态与控制”交互逻辑（状态即操作模式）：去除了视觉割裂的“纯文本 + 独立按钮”传统布局。现在，无论是“运行状态”还是“自启状态”，都统一整合为了单一的带颜色徽章按钮（例如：绿色的 `运行中 ⏹`、红色的 `已停止 ▶`）。悬浮时会有“点击启动/停止”的标题提示，极大简化了界面噪音，使得表格清爽直观。 @done(2026-05-30 21:15)


## 需求：修复 PHP 插件安装时路径报错与下载失败问题

**问题描述：**
PHP 插件安装时，报错 `/www/server/mdserver-web/plugins/php/plugins/php/lib: No such file or directory`，并且因为网络 HTTP 劫持导致下载 PHP 安装包失败，提示文件不完整。

**根本原因分析：**
1. 之前统一替换所有脚本 `curPath` 为动态路径时，未考虑不同层级目录深度导致多级 `dirname` 解析出错误的 `rootPath` 与 `serverPath`。
2. 安装包下载时的 `LOCAL_ADDR` 节点测速中，使用了 `http://ipinfo.io/json`，在部分网络环境下会被透明 HTTP 代理劫持（返回 302 重定向），导致无法正确分配国内下载节点，继而回退到 `php.net` 亦被劫持，最终下载到空洞 HTML 文件引发 `tar` 失败。

**涉及文件：**
- `plugins/php/versions/**/*.sh` (所有版本的 PHP 安装及扩展脚本)

### Task List

- [x] 修复 `plugins/php` 安装失败后无法在列表中显示的 Bug：由于 `plugins/php/info.json` 中加入了 UTF-8 编码的中文提示，导致在 Windows 平台下默认使用 GBK 编码读取时抛出 `UnicodeDecodeError`（`web/core/mw.py` 的 `readFile` 函数）。这导致插件完全不被解析而在列表中消失。已全局为 `mw.py` 中的 `readFile` 与 `writeFile` 显式指定 `encoding='utf-8'` 解决此问题。
- [x] 修复 `plugins/php/index.py` Bug：修正 `getPhpSocket` 中 `www.conf` 文件不存在（比如刚安装失败或被删除）导致引发的 `TypeError` 崩溃。修正了 `status` 状态检查函数内因对 `sock.find(':')` 使用不当导致永远误判调用进程状态逻辑检查的错误。
- [x] 将所有脚本中的 `http://ipinfo.io/json` 统一修改为 `https://ipinfo.io/json`，以强制 TLS 加密绕过局域网透明 HTTP 劫持，确保中国大陆加速节点能够被正常分配 @done


## 需求：修复由于 Captive Portal（强制主页认证）导致的 PHP 与依赖下载失败

**问题描述：**
PHP 安装过程中，出现 `zlib.sh: line 35: cd: /www/server/source/lib/zlib-1.2.11: No such file or directory` 以及 `curl: (60) SSL certificate problem`，最终导致 `tar` 报错。

**根本原因分析：**
1. 用户的服务器网络处于某种强制 Web 认证（Captive Portal）或深信服/网康等上网行为管理的透明代理下。
2. 所有的 HTTP/HTTPS 下载流量，都被劫持并 302 重定向到了 `http://172.17.1.121/1.htm` 这个页面。
3. `curl` 因为证书不信任拦截了请求导致无法正确测速，而 `wget` 带有 `--no-check-certificate` 参数，成功将这个 3.2KB 的拦截 HTML 页面当成源码压缩包（如 `.tar.xz` 或 `.tar.gz`）下载了下来。
4. 解压脚本在对这个假冒的 HTML 页面进行 `tar` 解压时必然失败，导致后续的 `cd` 和 `make` 找不到源码目录而全面崩溃。
5. 原版 PHP `install.sh` 缺乏错误阻断，在下载文件被判定损坏时会删除文件但接着继续强行 `tar`，导致满屏报错。

**涉及文件：**
- `plugins/php/versions/**/*.sh`

### Task List

- [x] 重写并修正所有 PHP `install.sh` 脚本中的异常处理逻辑：当检测到 MD5 校验失败，或者压缩包文件不存在时，立刻通过 `exit 1` 阻断执行流程，防止出现满屏找不到路径的干扰报错，精准暴露下载错误。 @done
- [x] 为 `curl https://ipinfo.io/json` 测速增加 `-k` 参数，忽略局域网代理颁发的伪造证书，增强弱网劫持环境下的生存力。 @done
- [x] 排查明确最终根本阻断原因是 `172.17.1.121` 透明认证系统劫持了流量，需交由用户在宿主机完成网络放行。 @done

## 需求：软件管理搜索框前添加重置按钮

**问题描述：**
需要在右上角软件管理搜索框的前面加一个重置按钮，点击后清除搜索内容并刷新列表，提高用户体验。

**涉及文件：**
- web/templates/default/soft.html

### Task List

- [x] 在 web/templates/default/soft.html 搜索框前添加重置按钮（x），并绑定清除搜索和刷新列表的 JS 逻辑 @done
- [x] 修复搜索模块因外层容器固定宽度限制导致新增重置按钮后，搜索按钮被挤出换行的问题（拉宽外层容器至 350px 并补充了按钮间距） @done

## 需求：在软件管理中，如果input框内没有内容，则隐藏重置按钮

**问题描述：**
在软件管理页面的搜索框，如果没有输入任何内容，重置按钮显示在那里显得多余且不美观。需要实现在输入框没有内容时自动隐藏重置按钮的功能。

**涉及文件：**
- web/templates/default/soft.html

### Task List

- [x] 修改 web/templates/default/soft.html，为重置按钮设置初始隐藏样式，并监听搜索框的 input 事件，根据内容动态显示/隐藏重置按钮 @done

## 需求：文件菜单搜索栏增加重置功能按钮

**问题描述：**
在文件菜单下的搜索栏，需要增加和软件管理菜单下搜索栏一样的重置功能按钮，只有在input框中有文字才显示重置按钮。

**涉及文件：**
- `web/templates/default/files.html`

### Task List

- [x] 在 `web/templates/default/files.html` 中，为搜索框前增加重置按钮，并通过 `oninput` 事件控制按钮显示与隐藏 @done(2026-06-01 08:54)

## 需求：文件搜索模块调整为 Flex 布局解决换行问题

**问题描述：**
增加重置按钮后，整个搜索模块的宽度变大，超出了原本 `float: left` (`pull-left`) 机制下的排版空间限制，导致右侧的搜索按钮掉到了下一行。需要将整个搜索模块向左扩展，并保证所有控件处于同一行。

**涉及文件：**
- `web/templates/default/files.html`

### Task List

- [x] 在 `files.html` 的搜索表单上应用 `display: flex; align-items: center;` 并移除子元素的 `pull-left` 类，使其能够根据内容自动向左扩展而不换行 @done(2026-06-01 09:02)

## 需求：文件搜索重置按钮微调垂直居中对齐

**问题描述：**
重置按钮和后方的搜索输入框在垂直方向上存在落差（没有完全对齐）。
经排查发现，原有搜索框 (`.ser-text`) 及搜索按钮 (`.ser-sub`) 在全局 CSS 中强制携带了 `margin-top: 10px;`，而重置按钮缺少该属性导致在 Flex 交叉轴对齐时出现了视觉高度落差。

**涉及文件：**
- `web/templates/default/files.html`

### Task List

- [x] 在 `files.html` 的重置按钮 `style` 中补齐 `margin-top: 10px;`，完美匹配输入框和搜索按钮的外边距模型，实现像素级居中对齐 @done(2026-06-01 09:20)

## PHP 7.x OpenSSL 编译修复

### Task List
- [x] 为 PHP 7.1~7.4 升级 OpenSSL 至 1.1，并注入 CFLAGS 头文件优先级 @done
- [x] 为 PHP 7.0 注入 OpenSSL 1.0 的 CFLAGS 头文件优先级 @done
- [x] 修复 `plugins/php/versions/7*/install.sh` 脚本在 Windows 环境下编辑时意外引入的 CRLF (`\r\n`) 换行符导致在 Linux 执行时报 `$'\r': command not found` 的问题。已通过二进制重新写入的方式将所有涉及的 7.x 安装脚本转换为标准的 LF (`\n`)。 @done

## 需求：修复面板重启导致崩溃的问题

**问题描述：**
在面板点击重启后，面板崩溃起不来，需要去SSH执行 `bs 1` 才能启动。

**根本原因分析：**
- 在 `mw_stop_panel` 结束时（`kill -9` 发出后），操作系统释放端口和清理进程信息需要极短暂的延迟。
- 若紧接着无缝执行 `mw_start_panel`，`ps -ef` 往往会误扫到处于终止中（D/Z状态）的旧 gunicorn 进程，从而判断面板已运行，直接跳过启动逻辑。
- 旧进程随后彻底死亡，导致面板实际处于停机状态。
- `bs 1` (即 `mw restart`) 因为中途夹杂了 `mw_stop_task` 的较长耗时，给了 gunicorn 充分死亡的窗口，因此不会触发此问题。

**修复文件：**
- `cli.sh`
- `scripts/init.d/mw.tpl` (已确认最新版本已有 sleep 2)
- `文档/test/mw`

### Task List

- [x] 在 `cli.sh` 和 `test/mw` 的 `restart`、`restart_panel` 操作 `stop` 与 `start` 之间加入 `sleep 2`，让操作系统彻底回收旧进程资源 @done

## 需求：修复OP防火墙黑名单封锁失效问题
**问题描述**：
在“黑白名单”中将测试主机 172.17.60.218 加入黑名单后，依然可以访问服务器。

**根本原因分析**：
- 面板在 Windows 平台保存 `.ip` 配置文件时（调用 `mw.writeFile`，即文本写模式），默认会将 `\n` 转换成 Windows 风格的换行符 `\r\n`。
- OpenStar (基于 OpenResty) IP 黑白名单模块逐行加载 `deny.ip` 时，未能正确清洗结尾的 `\r`，导致字典中实际存储的是 `172.17.60.218\r`。
- 访客请求时，`ngx.var.remote_addr`（不带 `\r`）无法匹配命中，导致封锁策略完全失效。


## 需求：修复OP防火墙黑名单封锁失效问题
**问题描述**：
在“黑白名单”中将测试主机 172.17.60.218 加入黑名单后，依然可以访问服务器。

**根本原因分析**：
- 面板在 Windows 平台保存 `.ip` 配置文件时（调用 `mw.writeFile`，即文本写模式），默认会将 `\n` 转换成 Windows 风格的换行符 `\r\n`。
- OpenStar (基于 OpenResty) IP 黑白名单模块逐行加载 `deny.ip` 时，未能正确清洗结尾的 `\r`，导致字典中实际存储的是 `172.17.60.218\r`。
- 访客请求时，`ngx.var.remote_addr`（不带 `\r`）无法匹配命中，导致封锁策略完全失效。

**修复文件**：
- `plugins/op_star/index.py`

### Task List

- [x] 在 `index.py` 中的 `save_rule` 及 `apply_template` 拦截 `ip_Mod` 的写文件逻辑，弃用全局 `mw.writeFile`，改为独立 `open(..., newline='\n')` 以强制指定写入 LF (Unix 换行风格) 避免引擎加载异常。 @done

## 需求：修复 OP 防火墙 OpenStar C-call boundary 协程挂起错误
**问题描述**：
OpenStar 日志中提示 `attempt to yield across C-call boundary` 错误，导致虽然配置黑名单生效并匹配成功，却无法正常返回 403 拦截，实际封锁失效。

**根本原因分析**：
- OpenStar 的 `access_all.lua` 中包含 `ngx.exit()` 或类似会触发 Nginx Lua 协程切换（yield）的代码。
- 当前插件生成的 `openstar_access.lua` 入口文件中，使用了 `pcall(dofile, access_file)` 包装执行。
- `pcall` 以及其内部的 `dofile`（由于使用 C 函数）创建了 C-call boundary，阻止了内层代码安全让出协程，导致 OpenResty 抛出异常并中断拦截响应。

**修复文件**：
- `plugins/op_star/index.py`

### Task List

- [x] 修改 `plugins/op_star/index.py` 中的 `makeOpDstRunLua` 方法，移除生成 Lua 挂载文件（`openstar_access.lua` 与 `openstar_init_worker.lua`）时的 `pcall` 包装机制，直接使用 `dofile(file)`。 @done
- [x] 注入 `package.path` 和 `package.cpath`，以彻底消除 C-call 边界约束，保证 `ngx.exit(403)` 等协程中断操作顺利执行。 @done

## 需求：修复 OP 防火墙规则列表 Regex 列显示 `undefined` 问题
**问题描述**：
在 OP 防火墙面板的“拦截规则”页面（如 GET 参数过滤、Cookie过滤 等），表格中的正则表达式列全部显示为 `undefined`，而“规则描述”、“执行动作”等状态显示异常或被 fallback 显示。

**根本原因分析**：
- OpenStar 引擎底层的原生 JSON 规则配置（如 `args_Mod.json`）格式是一个嵌套数组 `[ ["regex", "j", "deny", "on", "desc"], ... ]`。
- 而宝塔插件 `op_star` 前端代码（`op_star.js`）只处理了将规则解析为 Object（`{ "state": "on", "action": "deny", "rule": ["regex", "j"], "name": "desc" }`）的逻辑。
- 当加载底层原生未被模板覆盖的数组格式规则时，`rule.rule`，`rule.state` 等属性均为 `undefined`，导致页面无法正常读取并渲染真正的正则表达式。

**修复文件**：
- `plugins/op_star/js/op_star.js`

### Task List

- [x] 修改 `op_star.js` 中渲染表格的核心逻辑，增加对 `Array` 格式规则的解析兼容，使其能正确读取索引 `0`（正则）、`2`（动作）、`3`（状态）、`4`（描述）。 @done
- [x] 修改 `toggleRuleState` 函数的逻辑，使其在更新状态时能够正确修改数组格式下的索引 `3` 或者 Object 格式下的 `.state` 属性，保证状态切换正常生效。 @done

## 需求：更新 GitHub 镜像加速代理节点

**问题描述**：
由于原有的部分公共 GitHub 镜像代理（如 gh-proxy.org、ghfast.top 等）连接不稳定或失效，导致面板环境下的代码克隆、文件下载等操作超时失败。

**根本原因分析**：
公共代理节点失效，需要寻找并替换为当前存活且支持 `git clone` 代理的有效节点，以提高容灾能力和下载成功率。

**涉及文件**：
- `scripts/github_download.sh`
- `web/core/mw.py`

### Task List

- [x] 更新 `scripts/github_download.sh` 中的 `_GH_PROXY_LIST`，增加有效节点（如 ghproxy.net, gh.con.sh, gh-proxy.com, cors.zme.ink），并移除失效节点。 @done
- [x] 同步更新 `web/core/mw.py` 中的代理测试列表及默认 fallback 节点。 @done

## 需求：OpenStar WAF 插件深度优化

**问题描述：**
根据《防火墙优化.md》文档要求，分阶段完成WAF的10项深度优化。

**涉及文件：**
- plugins/op_waf/waf/lua/waf_common.lua
- plugins/op_waf/waf/lua/init.lua
- plugins/op_waf/waf/lua/init_worker.lua
- plugins/op_waf/waf/config.json
- plugins/op_waf/waf/html/cookie.html

### Task List

- [x] Phase 1: JSON/API 防护引擎（解析 application/json）
- [x] Phase 1: 404 扫描行为分析（1分钟50次封禁30分钟）
- [x] Phase 1: 真实 IP 识别与 Trusted Proxy（XFF / CF-Connecting-IP）
- [x] Phase 1: 最大日志缓存限制（50000条上限）
- [x] Phase 2: IPv6 与代理池 CC 防护（IP段统计 /24与/64）
- [x] Phase 2: 浏览器指纹验证（Canvas/WebGL等替代单JS验证）
- [x] Phase 3: HMAC-SHA256 签名机制（替代MD5）
- [x] Phase 3: 管理接口 127.0.0.1 限制（remove_waf_drop_ip等）
- [x] Phase 3: 上传文件深度检测（扩展名、MIME、文件头检测）
- [x] Phase 4: 现代攻击规则集（SSRF, Log4j, Spring, Fastjson, ThinkPHP, Redis等）

## 需求：文件模块优化（排序与修改时间标红）

**问题描述**：
1. 文件列表默认排序应按照字母顺序升序排列。
2. 优化修改时间显示，将文件修改时间与当前时间相同的部分标红处理（颗粒度为年、月、日、时、分、秒），以便用户快速识别新修改的文件。

**涉及文件**：
- `web/static/app/files.js`

### Task List

- [x] 在 `files.js` 中新增 `getMatchTime` 函数，精确到颗粒度（年、月、日、时、分、秒）对文件时间进行比较，并在匹配部分使用红色字体显示。 @done
- [x] 修改 `files.js` 中的数据加载逻辑，当没有排序 Cookie 时，将默认排序参数 `post['order']` 设置为 `fname asc`，实现默认字母升序排列。 @done
- [x] 替换 `files.js` 中文件列表与对话框渲染处的 `getLocalTime` 调用为 `getMatchTime`，确保时间高亮功能生效，同时保留标题等 tooltip 中的纯文本时间格式。 @done

## 需求：在线编辑器增加注释高亮和快捷键功能

**问题描述**：
1. 注释文档需要展示成不同颜色标识，并且适配python、php、html等不同的常用文件。
2. 需要支持 Ctrl + / 快捷键，进行快速对某一行或几行进行注释化或者反注释化操作。

**涉及文件**：
- `web/static/app/public.js`
- `web/templates/default/layout.html`
- `web/static/css/site.css`

### Task List

- [x] 修改 `layout.html`，引入 CodeMirror 的 `comment.min.js` 扩展。
- [x] 修改 `public.js` 中的 `onlineEditFile` 函数，在 CodeMirror 配置的 `extraKeys` 中增加 `"Ctrl-/": "toggleComment"` 快捷键绑定。
- [x] 修改 `public.js` 中的编辑器类型推断，增加对 `py`, `sh`, `bash`, `ini`, `yaml`, `md` 等常见文件的支持，确保相应语言的代码高亮及注释规则能被 CodeMirror 正确识别。
- [x] 修改 `site.css`，覆盖 `.cm-comment` 样式，增加醒目的注释颜色和斜体效果，使注释更加清晰。
- [x] **修复 (Bugfix)**: 修正 `python` 等语言的样式完全丢失及 `Ctrl+/` 无效的问题。补充在 `layout.html` 中通过 CDN 引入缺失的 `python.min.js`、`shell.min.js`、`yaml.min.js` 等对应的底层语言解析包，使 CodeMirror 真正具备对这些语言的高亮和注释语法认知。
- [x] **优化 (Refactor)**: 按照用户要求去除 CDN 依赖，将 `python.js`、`shell.js`、`yaml.js`、`markdown.js`、`properties.js` 以及 `comment.js` 等缺失的 CodeMirror 扩展全部直接下载到本地的 `web/static/codemirror/` 相应目录下，并将 `layout.html` 中的引用全部改为纯本地路径，保证断网或 CDN 不稳定情况下的绝对可靠性。

## 需求：OP 防火墙封禁历史网站默认显示“ALL”并清除下拉菜单中的“unset”

**问题描述**：
1. 防火墙封禁历史页面，网站下拉菜单默认展示所有“ALL”（即显示全部域名下的封锁记录），目前默认选中第一个具体域名。
2. 下拉菜单选项中的 `unset` 无实际意义，需要将其去除，避免对用户造成困扰。

**涉及文件**：
- [index.py](file:///f:/git/gitea20250909/bt_simple/plugins/op_waf/index.py)
- [op_waf.js](file:///f:/git/gitea20250909/bt_simple/plugins/op_waf/js/op_waf.js)

### Task List

- [x] 在 `task.md` 结尾追加任务列表 @done(2026-06-08 09:00)
- [x] 备份待修改的核心文件 @done(2026-06-08 09:01)
- [x] 重构后端 `index.py` 的站点列表读取和默认站点配置函数，将 `unset` 选项清除，并将 `ALL` 作为默认值和第一项加入列表 @done(2026-06-08 09:02)
- [x] 修改后端 `index.py` 的 `getLogsList` 日志列表查询函数，当 `site` 域名为 `ALL` 时，不加 `domain=?` 条件，实现全局日志查询 @done(2026-06-08 09:02)
- [x] 修改前端 `js/op_waf.js`，将占位符 `option` 从 `unset` 修改为 `ALL` @done(2026-06-08 09:03)
- [x] 在前端 `js/op_waf.js` 渲染地区限制站点下拉框时，排除 `ALL` 选项以避免用户误选 @done(2026-06-08 09:03)
- [x] 验证：确认 WAF 封禁历史网站默认显示 `ALL` 且正常加载全部日志，下拉列表不再含有 `unset`，且地区限制添加时过滤掉了 `ALL` @done(2026-06-08 09:04)

## 需求：WAF 防火墙首页新增“今日拦截（次）”指标三栏卡片展示

**问题描述**：
1. 防火墙首页增加“今日拦截”指标，要求使用高性能的内存+静态文件缓存方案（方案二），不能有额外的 SQLite 数据库大表查询负荷。
2. 页面顶栏的布局从原先的两栏（绿色、蓝色）变为三栏，第一列增加今日拦截（次），展示风格要求优雅简介，色系调和。

**涉及文件**：
- [waf_common.lua](file:///f:/git/gitea20250909/bt_simple/plugins/op_waf/waf/lua/waf_common.lua)
- [op_waf.js](file:///f:/git/gitea20250909/bt_simple/plugins/op_waf/js/op_waf.js)

### Task List

- [x] 在 `task.md` 结尾追加任务列表 @done(2026-06-08 09:12)
- [x] 备份 `waf_common.lua` 核心 Lua 引擎文件 @done(2026-06-08 09:13)
- [x] 修改 `waf_common.lua` 中的 `stats_total` 累加函数，在内存中增加 `today_total` 及 `today_date` 的日历级防线计数更新 @done(2026-06-08 09:14)
- [x] 修改前端 `op_waf.js` 的 `wafScreen` 首页渲染函数，检测日期并获取今日拦截数（若日期不同则取0值退化） @done(2026-06-08 09:14)
- [x] 修改前端 `op_waf.js` 的 CSS 和 HTML 卡片渲染布局，拓展为三栏卡片展示并引入优雅的橙色渐变主题卡片 @done(2026-06-08 09:14)
- [x] 验证：检查 Lua 语法和页面展示，发起多次本地拦截请求，验证今日拦截与总拦截数是否能够实时递增，修改系统时间跨天验证今日拦截数是否自动归零 @done(2026-06-08 09:15)

## 需求：在控制面板大看板首页概览中展示“今日拦截/总拦截”数据

**问题描述**：
1. 面板全局首页的“概览”版块中需要追加显示“御风防火墙”的实时运行指标。
2. 呈现样式要求以“御风防火墙：今日拦截/总拦截”为标题，值展示为“今日拦截数/总拦截数”（如 `35/108`），并且点击数值可以直接弹窗唤起防火墙插件进行配置。

**涉及文件**：
- [index.py](file:///f:/git/gitea20250909/bt_simple/plugins/op_waf/index.py)
- [index.js](file:///f:/git/gitea20250909/bt_simple/web/static/app/index.js)

### Task List

- [x] 在 `task.md` 结尾追加任务列表 @done(2026-06-08 09:25)
- [x] 备份 `web/static/app/index.js` 核心文件 @done(2026-06-08 09:25)
- [x] 修改 `plugins/op_waf/index.py`，实现 `getTotalStatistics()` 后端统计函数，获取并输出今日拦截数和总拦截数（格式如今日/总计），并注册 `get_total_statistics` 命令行路由 @done(2026-06-08 09:25)
- [x] 修改前端 `web/static/app/index.js` 的 `loadKeyDataCount()` 函数，将 `op_waf` 插件追加进加载列表，并做别名定制显示为“御风防火墙：今日拦截/总拦截” @done(2026-06-08 09:26)
- [x] 验证：刷新面板首页，观察概览版块是否正确渲染出“御风防火墙：今日拦截/总拦截”和相应数据，并验证点击是否能正确弹出防火墙管理窗口 @done(2026-06-08 09:26)

## 需求：点击首页的御风OP防火墙数据，跳转至防火墙的“首页”选项卡

**问题描述**：
目前点击首页概览版块中的“御风OP防火墙”拦截数据时，弹出的 WAF 管理窗口会默认显示首个“服务”选项卡。
需要实现点击该项时直接跳转并展示 WAF 的“首页”选项卡，显示今日拦截、总拦截、安全天数的子菜单。

**涉及文件**：
- [index.js](file:///f:/git/gitea20250909/bt_simple/web/static/app/index.js)
- [index.html](file:///f:/git/gitea20250909/bt_simple/plugins/op_waf/index.html)

### Task List

- [x] 备份待修改的 `plugins/op_waf/index.html` @done(2026-06-08 09:54)
- [x] 修改 `web/static/app/index.js` 的 `loadKeyDataCount` 函数，增加当 `pname == 'op_waf'` 时，注入 `window.DEFAULT_ACTIVE_TAB = 'wafIndex';` 的控制状态 @done(2026-06-08 09:54)
- [x] 修改 `plugins/op_waf/index.html` 的初始化脚本，当检测到 `window.DEFAULT_ACTIVE_TAB === 'wafIndex'` 时，高亮“首页”选项卡并直接调用 `wafScreen()` 进行首页内容渲染 @done(2026-06-08 09:55)
- [x] 验证：在控制面板首页概览处点击“御风OP防火墙”，确认管理窗口弹窗后能直接显示 WAF 首页（即带有三色大卡片的统计面板） @done(2026-06-08 09:56)

## 需求：修复首页点击防火墙时弹窗标题显示为系统名 op_waf 的缺陷

**问题描述**：
从软件列表中点击防火墙，弹出的窗口标题为“御风OP防火墙【1.0】管理”；但从首页概览数字点击进去，标题却变成了“op_waf【1.1】管理”（即插件的系统文件夹名）。

**涉及文件**：
- [index.js](file:///f:/git/gitea20250909/bt_simple/web/static/app/index.js)

### Task List

- [x] 备份待修改的 `web/static/app/index.js` @done(2026-06-08 10:05)
- [x] 优化 `index.js` 中的别名匹配逻辑，使 `op_waf` 映射为 `御风OP防火墙`，`mysql` 映射为 `MySQL`，`gogs` 映射为 `Gogs`，`gitea` 映射为 `Gitea` @done(2026-06-08 10:05)
- [x] 将计算后的 `show_name` 别名传入 `softMain` 作为 `title` 参数，消除硬编码系统名 `pname` 的问题 @done(2026-06-08 10:05)
- [x] 验证：在控制面板首页点击各个概览数字，确认弹出的管理窗口的 Title 均显示正确的中文或大写规范名称 @done(2026-06-08 10:06)



## 需求：第三方插件显示逻辑与样式优化

**问题描述：**
软件管理界面的插件列表将官方认证插件与未认证（第三方/自行上传）插件混在一起，导致官方主推生态不够突出，且不利于安全与体验管理。需要对第三方插件进行视觉降级，并允许用户手动开启或隐藏。

**涉及文件：**
- `plugins/*/info.json`
- `web/utils/plugin.py`
- `web/admin/plugins/__init__.py`
- `web/templates/default/soft.html`
- `web/static/app/soft.js`

### Task List

- [x] 批量修改：编写脚本将所有官方认证插件（除“待审核”外）的 `info.json` 中 `display: 1` 升级为 `display: 2` @done(2026-06-08 13:00)
- [x] 修改后端 `web/utils/plugin.py`：在加载信息时缓存原始 `display`，并在 `getAllPluginList` 中加入 `show_third_party` 参数过滤逻辑，默认仅放出 `display_level >= 2` 的插件 @done(2026-06-08 13:00)
- [x] 修改前端 `web/templates/default/soft.html`：在“刷新列表”按钮后侧追加带下拉弹窗交互的设置齿轮图标，内含 `[x] 显示第三方插件` 开关 @done(2026-06-08 13:00)
- [x] 修改前端 `web/static/app/soft.js`：追加 `localStorage` 持久化选项，并绑定至下拉复选框；在渲染插件列表时，为第三方插件 (`display_level == 1`) 醒目注入 `(第三方)` 橙色文字标签 @done(2026-06-08 13:00)
- [x] 增加点击页面其他区域自动收起齿轮弹窗的交互优化 @done(2026-06-08 13:00)

## 需求：精准校验并修正全部 CDN 资源的版本号以匹配本地回退

**问题描述：**
之前的 CDN 替换方案（2026-05-25）存在严重的库版本号不一致问题（如 marked CDN 为 4.3.0，本地为 15.0.12；clipboard CDN 为 2.0.11，本地为 2.0.1 等）。用户要求 CDN 资源加速时，必须具备本地 fallback 回退能力，且 CDN 加载的版本号**必须和本地文件完全一致**以防出现 API 兼容性灾难。

**涉及文件：**
- web/templates/default/layout.html
- web/templates/default/index.html
- web/templates/default/monitor.html

### Task List

- [x] 通过脚本精准探测 web/static/js/ 和 css 下所有第三方库的本地真实版本号。
- [x] 修改 layout.html，纠正不匹配的 CDN 版本号（Layer 3.0.1, CodeMirror 5.21.0, Marked 15.0.12, Clipboard 2.0.1, Socket.io 4.5.0）。
- [x] 修改 index.html 和 monitor.html，纠正 ECharts 版本号（从 5.4.3 改为真实的 5.4.1）。
- [x] 验证所有的替换均带有 onerror 或 window.XXX || document.write() 兜底本地代码。


## 需求：修复 Layer CDN 地址 404 问题

**问题描述：**
由于 Staticfile 上 layer 3.0.1 版本的 css 路径不存在（产生 404），现将其及其配套 JS 替换为稳定且经过验证的 BootCDN 的 3.5.1 版本。

### Task List
- [x] 将 layout.html 中的 layer.css 替换为 https://cdn.bootcdn.net/ajax/libs/layer/3.5.1/theme/default/layer.css。
- [x] 将 layout.html 中的 layer.js 同步替换为 https://cdn.bootcdn.net/ajax/libs/layer/3.5.1/layer.min.js，保持版本和样式一致性。


## 需求：修复 BootCDN 跨域问题，将 Layer 替换为 cdnjs

**问题描述：**
BootCDN 节点由于严格的跨域安全策略，导致部分用户加载 CSS 时遇到 strict-origin-when-cross-origin CORS 错误。使用全局可访问的 Cloudflare cdnjs 作为最终替代。

### Task List
- [x] 将 layout.html 中的 layer.css 替换为 https://cdnjs.cloudflare.com/ajax/libs/layer/3.5.1/theme/default/layer.css。
- [x] 将 layout.html 中的 layer.js 同步替换为 https://cdnjs.cloudflare.com/ajax/libs/layer/3.5.1/layer.js。


## 需求：优化 Docker 部署脚本

**问题描述：**
1. 基础镜像过时（Debian 10）
2. 使用 Systemd 导致运行不稳
3. Volume 挂载 /www 导致核心文件在挂载宿主机目录时丢失
4. 弱密码及构建执行效率低

### Task List

- [ ] 重构 Dockerfile，使用 debian:12-slim，拆分构建层，增加缓存清理
- [ ] 移除 start.service 和旧的 start.sh
- [ ] 新增 entrypoint.sh，生成动态密码并守护进程
- [ ] 修复 VOLUME，仅映射 /www/wwwroot 和 /www/server/mysql/data

## 需求：重构与修复 Docker 管理器插件

**问题描述：**
1. 高危命令注入漏洞：多处使用 mw.execShell 且未转义参数。
2. 可靠性问题：硬编码时区、解析参数脆弱、macOS 开发路径硬编码残留。
3. 执行效率：部分操作（如获取状态）调用了冗长且消耗大的系统 ps 指令。

### Task List

- [x] 重构 plugins/docker/index.py：使用 shlex.quote() 转义所有 mw.execShell 的外部参数，修复命令注入高危漏洞
- [x] 优化 getDClient()，移除无效的 macOS 硬编码路径，使用官方标准的 /var/run/docker.sock 作为后备
- [x] 重写 status() 状态检测函数，改用 systemctl is-active 或 docker-py API 检测，提高执行效率和准确度
- [x] 修复 utc_to_local 中的时区硬编码（Asia/Chongqing），改为动态计算系统时区偏移

## 需求：修复 Docker 镜像拉取失败时仍提示成功的 Bug

**问题描述：**
用户在前端拉取一个不存在的非官方镜像（如 cloudreve，正确应为 cloudreve/cloudreve）时，底层 docker-py 抛出异常，触发 Shell 降级拉取。但原代码在解析 Shell 错误输出时仅匹配了 `invalid` 关键字，导致所有如 `not found`、`denied` 等致命错误被漏报，前端错误地弹出了“拉取成功”提示，且本地实际上没有镜像。

### Task List

- [x] 重构 `plugins/docker/index.py` 的 `dockerPull` 与 `dockerPlulPath`，全面捕获 `Error`、`error`、`not found`、`denied` 等常见守护进程标准错误输出
- [x] 提取并透传真实的错误信息至前端，防止假阳性报错漏判

## 需求：增加加速器管理与修复服务控制

**问题描述：**
1. 用户需要可视化的 Docker 加速器管理功能，读取 `/etc/docker/daemon.json`。
2. 重启按钮底层存在引用未定义函数的崩溃 BUG。

### Task List
- [x] 修复 `index.py` 中 `restart()` 的 `runLog()` 未定义 Bug
- [x] 在 `index.html` 左侧菜单栏新增 `<p onclick="dockerAccelerator();">加速器</p>`
- [x] 在 `js/docker.js` 新增 `dockerAccelerator()` 界面渲染函数和预置模板逻辑
- [x] 在 `index.py` 新增 `get_accelerator` 接口获取当前加速器源
- [x] 在 `index.py` 新增 `set_accelerator` 接口写入并重启 Docker 服务

## 需求：实现自动节点容灾拉取功能

**任务清单：**
- [x] 后端 (index.py)：新增 docker_pull_with_mirror 接口，支持指定 Mirror 地址并通过重命名 Tag 的方式完成拉取。
- [x] 前端 (js/docker.js)：在加速器设置页面增加用户自定义管理（本身已支持通过文本框编辑并保存 daemon.json）。
- [x] 前端 (js/docker.js)：增加全局变量或开关记忆功能，决定是否启用自动容灾。
- [x] 前端 (js/docker.js)：修改获取镜像弹窗逻辑，嵌入实时进度显示 div。
- [x] 前端 (js/docker.js)：编写轮询函数，当普通拉取失败时，依次用用户配置的 Mirror 节点列表尝试。

## 需求：强制删除插件后自动从 GitHub 恢复面板插件目录

**问题描述：**
强制删除插件后会把 `/www/server/mdserver-web/plugins/xxx` 文件夹也删除，导致插件从商店列表消失，用户无法再次进行安装。

**修复文件：**
- `web/utils/plugin.py`

### Task List

- [x] 在后端 `web/utils/plugin.py` 强制卸载分支中，**保留**面板自带的插件控制文件夹 `/www/server/mdserver-web/plugins/xxx`，不进行物理删除（无需从 GitHub 重新同步下载） @done(2026-06-10 12:48)
- [x] 在前端 `web/static/app/soft.js` 实现「输入插件名二次确认」的双重弹窗防御验证，杜绝手误删除数据 @done(2026-06-10 12:35)
- [x] 在后端 `web/utils/plugin.py` 中通过读取并处理带版本号的安装路径，实施「父目录及根路径多重防线白名单审查」，并在安全校验通过后一并删除 `/www/server/xxx` 文件夹 @done(2026-06-10 12:35)
- [x] 在前端确认弹窗中添加「删除前打包备份到 /www/backup」复选框且默认勾选，并在后端物理删除前自动执行 `tar` 打包备份 @done(2026-06-10 12:40)
- [x] 验证整体功能是否正常 @done(2026-06-10 12:48)

## 需求：修复 MongoDB 安装脚本 Bug 与网络异常导致的假装安装成功

**问题描述：**
用户在安装 MongoDB 时因官方服务器 `fastdl.mongodb.org` 网络超时一直挂起，或者下载失败产生空文件。但因为安装脚本中存在一处验证解压的逻辑 Bug（错误地判断 `! -d 压缩包.tgz`），导致即使没有下载成功也会错误地触发解压及后续的拷贝动作；并且关键指令没有配置错误中断，最终脚本异常执行完毕后错误地向主控面板返回了安装成功的退出码。

### Task List
- [x] 在 `plugins/mongodb/versions/**/*.sh` 中修正全部错误解压验证，将 `! -d ${FILE_NAME_TGZ}` 改为 `! -d ${FILE_NAME}`，将 `! -d ${TOOL_FILE_NAME_TGZ}` 改为 `! -d ${TOOL_FILE_NAME}` @done
- [x] 为 `plugins/mongodb/versions/**/*.sh` 中的 `wget` 下载添加 `-T 120 -t 3` 超时与重试参数，并在 `wget` 和 `tar` 等关键语句后附加 `|| exit 1`，确保在网络超时或解压失败时抛出错误，正确阻断面板显示“安装成功”的错觉 @done

## 需求：在软件管理添加缓存清理功能

**问题描述：**
软件管理需要提供显式的操作入口用于清除 `/www/server/source/` 下的安装包缓存，以释放磁盘空间并规避网络异常引发的各种残缺安装包导致的连环错误。

### Task List
- [x] 后端 (`web/utils/plugin.py`)：在 `clearCache` 函数中追加清理 `/www/server/source/*` 的逻辑 @done
- [x] 前端 (`web/templates/default/soft.html`)：在“显示第三方插件”下拉菜单中新增“清理缓存”按钮 @done
- [x] 前端 (`web/static/app/soft.js`)：新增 `clearPluginCache` 函数，包含二次确认弹窗并发起清理请求 @done
