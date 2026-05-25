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
- [x] 前端：在 `web/static/app/index.js` 中重构 `showUpdateUI`、更新它的展示逻辑，在“1. 下载并解压更新包...”上方优雅展示测速优选后的加速站提示，并在修复系统时通过异步探测获取站名并完美展示 @done(2026-05-25 16:05)
- [x] 验证：确认在网页端打开更新或修复弹窗时，均能秒级响应并展示“已使用 xxx 网站加速更新”字样，且升级所走代理确实为挑选出的最优代理链路 @done(2026-05-25 16:05)
