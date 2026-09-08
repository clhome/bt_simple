# 面板前端UI/UX现代化优化任务

> 项目整体描述：优化御风面板前端界面，使用现代设计规范（卡片化、圆角、弥散阴影等），基于纯CSS和现有jQuery实现，不新增插件。
> 开发规范描述：KISS原则，优先复用项目中已有的函数和模块。无BOM UTF-8格式，LF换行符。不允许使用>或>>重定向。所有测试程序与阶段性临时排查/批处理工具统一放置在根目录test文件夹中，保持生产目录整洁。
> 注意：开发过程需要考虑多国语言的适配。

## Task List

- [x] 1. 扩充 6 国语言词典（zh-CN, zh-TW, en, fr, de, it）与映射表：在 `template.json`、`lan.js` 与 `scripts/tools/phrases_full.py` 中录入软件分类（全部、已安装、运行环境、数据库、系统工具、其他插件、PHP等）词条。
- [x] 2. 优化后端分类定义与接口（`web/utils/plugin.py`）：为 `def_plugin_type` 分类项增加标准 `key` 属性，并在 `getList` 返回时通过 `core.i18n.t` 支持多语言。
- [x] 3. 优化前端软件分类标签渲染（`web/static/app/soft.js`）：通过 `t(i18nKey, fallback)` 动态翻译并注入 `data-i18n` 属性。
- [x] 4. 优化分页多语言支持（`web/utils/page.py`）：启用 `PAGE` 国际化字典读取，修复分页文本（首页/上一页/共X条数据等）英文适配。
- [x] 5. 编写并运行自动化测试（`test/test_soft_i18n.py`），验证 6 国语言分类及分页渲染正确性。
- [x] 6. 补全 6 国语言词库中的公共弹窗词条（`confirm`、`cancel`、`close`、`info`、`do_you_want_to`），并在 `lan.js` 与 `i18n.js` 中确立 `public` 命名空间可用性。
- [x] 7. 修复 `#signout` 点击事件：使用标准的 `t('public.do_you_want_to')`，彻底修复内容空字符串与滚动条异常。
- [x] 8. 实现全局 Layer 弹窗多语言自动拦截与适配引擎（`confirm`、`alert`、`prompt`、`open`）：全站弹窗标题和按钮自动接入多语言，修复历史硬编码中文。
- [x] 9. 编写自动化测试套件（`test/test_layer_dialog_i18n.py`）并回归全量测试，确保 100% 验证通过。
- [x] 10. 清洗并修复 `web/static/app/public.js` 中的关于弹窗渲染逻辑：消除标题、公司、荣誉出品与版权的双层嵌套，彻底删除多余的一行“荣誉出品”，消除内存图标的双重拼接。
- [x] 11. 补全并修正 `scripts/tools/phrases_full.py`、`lan.js`、`template.json` 中的关于页面及搜索栏多语言词条（涵盖 zh-CN, zh-TW, en, fr, de, it 6 国语言），彻底解决中英文混合与翻译缺失问题。
- [x] 12. 运行构建脚本重新生成全套 6 国语言包（`lan.js`、`public.json` 与 `template.json`），确保语言字典与前端调用完全对齐。
- [x] 13. 编写自动化测试套件（`test/test_about_i18n.py`），验证 6 国语言下关于页面翻译正确性、无冗余“荣誉出品”及无多余内存图标。
- [x] 15. 排查并定位英文状态下页面仍显示中文问题：确认 lan.js 结尾缺少逗号导致的 SyntaxError 崩溃以及双重 public 覆盖。
- [x] 16. 规范化合并 6 国语言 lan.js：将末尾关于弹窗与搜索栏词条正确合并进主 public 字典，彻底删除末尾多余且损坏语法的重复 public 块。
- [x] 17. 运行 Node.js 真实语法解析校验与自动化测试：确保全部 6 国语言 lan.js 零语法错误，且在英文状态下 t('public.yufeng_panel_current_server') 正常输出英文。
- [x] 18. 清理临时排查脚本并验收完成度。
- [x] 19. 重构 `web/static/app/soft.js` 中 `runUninstallVersion` 弹窗结构：规范化完整闭合 HTML，恢复备份复选框 `#normal_uninstall_backup_chk` 与关闭按钮正常右上角定位。
- [x] 20. 补全并同步 6 国语言词条：在 `lan.js`、`template.json` 和 `phrases_full.py` 的 `soft` 模块录入 `uninstall_confirm_prefix`、`uninstall_confirm_suffix`、`uninstall_backup_tip` 纯文本翻译。
- [x] 21. 编写自动化测试套件（`test/test_uninstall_modal_i18n.py`），验证 HTML 结构自闭合、复选框有效性与 6 国语言纯正翻译。
- [x] 22. 运行全量测试套件回归验证，确保 100% 通过并清理临时文件。
- [x] 23. 彻底修复卸载弹窗内容多国语言国际化：将 6 国语言 `lan.js` 中的词条从误插入位置精准归位至真实 `soft` 模块末尾，解决多语言状态下内容回退显示中文的问题。
- [x] 24. 修复监控页面计算资源图表“百分比(%)”多语言未翻译问题：在 6 国语言 `public.json`、`lan.js`（`public` 模块）与 `template.json` 中补齐 `pre` 词条，并在 `control.js` 与 `i18n.js` 中做好兜底与自动化测试验证。
- [x] 25. 优化 6 国语言词典（`phrases_full.py`、`lan.js`、`template.json`）：精简 `files` 命名空间中 `include_sub`、`total_of_directory_and`、`get`、`path_root`、`site_root`、`panel_root` 等词条为紧凑易读短语。
- [x] 26. 重新构建 6 国语言包并强制 LF 换行，确保全套语言包语法正确且词条生效。
- [x] 27. 优化 `files.html` 与 `site.css`：重构搜索框内部 `.file_search` 为 Flex 弹性对齐与防折行布局，保证多语言文字与复选框自然贴合并消除遮挡。
- [x] 28. 优化 `files.js` 路径面包屑与统计栏自适应算法：动态计算可用宽度，避免深层路径与多语言统计文字撞击右侧搜索框。
- [x] 29. 编写并运行自动化测试套件（`test/test_files_i18n_layout.py`）验证多语言词条、布局完整性与语法无误，验收完成后清理临时文件。
- [x] 30. 调整 `files.js` 中 `calcPathWidth` 算法：设定更合理的预留宽度（增加留白缓冲与统计区最小宽度），缩短地址栏，使统计栏中的“获取”完整清晰展示，绝不被搜索框覆盖。
- [x] 31. 重构 `files.html` 与 `site.css` 搜索框组件样式：采用一体化复合输入框组（`.search-input-box`），去除 `.file_search` 绝对定位白底覆盖，消除浮空绿线与不对齐缺陷，完美对齐放大镜按钮。
- [x] 32. 更新并执行自动化测试套件（`test/test_files_i18n_layout.py` 与 `test/run_all_tests.py`），验证布局与样式无损并验收。
- [x] 33. 分析容量计算异常与“Calc”按键业务逻辑：排查前端累加（9.76 KB）与后端 du -sh（24k）统计口径冲突的底层根因，输出完整对比与方案分析供用户确认。
- [x] 34. 重构 `files.js` 中 `calcPathWidth` 算法与 `files.html` 搜索框右对齐：去除 `max 350px` 限制，精确计算容器宽度，让地址栏尽量占满空间；搜索框紧密右对齐，消除中间无意义留白。
- [x] 35. 根据用户对“Calc”按键的决策实施优化（智能按需显示：无子目录时隐藏 Calc；有子目录时才显示；统一后端口径为真实文件大小），并通过全量 139 项自动化测试回归验证。
- [x] 36. 修复直接打开页面时显示不完整（统计信息被搜索框覆盖）问题：统一 tipTools 宽度基准，增加 dirInfo 与搜索框保底宽度及安全留白，并在表格渲染后与 DOM 就绪后多阶段校准 calcPathWidth。
- [x] 37. 优化搜索框与回收站/切换按钮组右侧边距：将搜索框与切换按钮组/回收站向左缩进对齐，使第一行搜索框右边缘、第二行切换按钮组右边缘与下方框体（表格最右边框线）严格垂直对齐，整体呈现专业对称排版。
- [x] 38. 排查并修复 `web/static/app/site.js` 中 `getWeb` 函数的 HTML 结构拼接：消除丢失的双引号与闭合标签，将文案与 HTML 结构完全解耦，确保 12 列严格对齐。
- [x] 39. 全面扫描并修复 `site.js` 中所有因机械式 i18n 替换遗留的语法残损与未闭合标签（覆盖弹窗、设置、删除、备份操作等共 14 个受损函数）。
- [x] 40. 编写自动化测试套件（`test/test_site_table_i18n.py`），验证数据行 12 列结构完整性、各操作事件闭合性与 6 国语言切换文案。
- [x] 42. 优化 `web/static/app/site.js` 中网站目录（`shortpath`）显示逻辑：移除 30 字符机械截断，充分利用 26% 列宽空间展示完整路径。
- [x] 43. 为网站目录链接添加 CSS 智能文本防溢出样式（`display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: middle;`），兼顾自适应完整展示与极端超长保护。
- [x] 44. 更新并运行测试套件（`test/test_site_table_i18n.py` 与 `test/run_all_tests.py`），验证长路径（>30字符）完整渲染与全量回归通过。
- [x] 45. 优化网站列表页面排版与列宽防护（`web/templates/default/site.html`）：为 `#webBodyHeader th` 与 `#webBody td` 统一添加 `white-space: nowrap; vertical-align: middle;`，微调关键列宽（备份放宽至 65px、到期放宽至 90px 等），彻底杜绝表头与数据行断行。
- [x] 46. 启用 6 国语言精炼专业简写（`template.json`、`lan.js`、`phrases_full.py`）：将表头字段（Created、Traffic、SSL、Expires、Path）与数据状态（None/Yes、Settings、None）优化为紧凑标准的专业用语。
- [x] 47. 修复分类下拉框多语言缺失与选项异常（`web/static/app/site.js`）：修正 `getClassType` 中误用的 `are_you_sure_you_3` 为 `全部分类`，并为 `默认分类` 增加国际化动态翻译。
- [x] 48. 优化通用分页组件西文空格粘连问题（`web/utils/page.py`）：对西文语种自动智能补全数字两侧空格，解决 `Total2records` 粘连。
- [x] 49. 编写专项自动化测试套件（`test/test_site_i18n_concise.py`），验证 6 国语言简写文案、CSS nowrap 样式、分类下拉与分页排版。
- [x] 57. 实施弹窗关闭按钮 (X) 双重修复：在 `site.css` 与 `ensite.css` 中重置 `.layui-layer-setwin .layui-layer-close2` 样式（消除 `-28px` 负边距并修复裁剪），并在 `i18n.js` / `public.js` 全局弹窗拦截器中自动归一化 `closeBtn: 2` 为内嵌式 `closeBtn: 1`。
- [x] 58. 优化多语言词典（`phrases_full.py`、`lan.js`、`template.json`）：将 6 国语言文件操作列词条（`copy_path`、`permissions`、`compress`、`preview`、`download`、`delete` 等）精炼优化为国际通行简写。
- [x] 59. 重新构建 6 国语言包并强制 LF 换行，确保全套语言包语法正确且简写词条生效。
- [x] 60. 重构 `files.js` 表格列宽配置与操作列样式：为大小、权限、所有者设置合理保底列宽，操作列适配弹性空间，并为 `.editmenu` 与 `span` 增加 `white-space: nowrap !important;` 彻底杜绝换行。
- [x] 61. 编写专项自动化测试套件（`test/test_modal_close_btn_and_files_ops.py`），验证 6 国语言简写、关闭按钮样式与操作列防折行规则。
- [x] 62. 运行全量自动化测试套件回归验证，确保 100% 通过并清理临时排查脚本。
- [x] 63. 补全 6 国语言词典（`scripts/tools/phrases_full.py` 与语言包）：新增 `running_prefix`、`ip_type_lan`、`ip_type_loopback`、`ip_type_public` 以及 `login_details_*` 系列词条。
- [x] 64. 优化系统运行时间多语言支持（`web/utils/system/main.py`、`web/admin/system/system.py` 与 `web/static/app/index.js`）：使用 `core.i18n.t` 消除硬编码“已运行:”，前端与后端双重保障多语言动态格式化。
- [x] 65. 优化 Recent Logins 与 Logs 弹窗表格渲染（`web/admin/dashboard/dashboard.py` 与 `web/static/app/index.js`）：为归属地与登录详情增加语义化 Key，前端消除硬编码中文表头与标签，弹窗 LOCATION 与 DETAILS 接入多语言格式化。
- [x] 66. 重新构建 6 国语言包并强制 LF 换行，确保全套语言包语法正确且词条生效。
- [x] 67. 编写专项自动化测试套件（`test/test_index_i18n_fix.py`），验证 3 处多语言、数据接口语义化 Key、前端无硬编码中文及 6 国语言完整性。
- [x] 68. 运行自动化测试套件验证，确保 100% 通过并保持开发目录整洁。

## 插件多国语言翻译审查与完整补全

- [x] 69. 恢复工作区被误修改的插件语言文件（`git restore plugins/`），找回历史完整翻译数据。
- [x] 70. 编写并运行纯净词条并集提取脚本（`test/extract_clean_plugin_keys.py`）：扫描 38 个插件所有现有语言文件，彻底过滤 JS/HTML/CSS 代码污染，合并生成每个插件权威完整的中文词条库（并集）并更新 `zh-CN.json`。
- [x] 71. 构建全局优质翻译词典（`test/build_global_plugin_dict.py`）：从现有 38 个插件与系统词库中收割所有成熟纯正的外语词条。
- [x] 72. 编写批量高质量翻译补全脚本（`test/rebuild_all_plugin_langs.py`）：对 38 个插件 × 5 种外语（zh-TW, en, de, fr, it）的缺失词条进行专业运维标准补全，确保各语言文件 key 100% 对齐且无未翻译中文。
- [x] 73. 编写严密的自动化校验测试套件（`test/validate_plugin_lang.py`）：自动验证 JSON 语法、Key 完全一致、无代码污染、无未翻译中文，并完成回归测试。
- [x] 74. 验收完成度并清理开发临时排查脚本。

## 插件弹窗多语言动态渲染引擎与翻译缺失彻底解决

- [x] 79. 补全 38 个插件 `lang/*.json` 词库中的静态菜单项（服务、自启动、配置修改、容器列表、仓库等）与出品版权词条，确保所有语言包 100% 覆盖。
- [x] 80. 升级前端框架核心 `i18n.js` 与 `soft.js`：实现插件弹窗 DOM 自动国际化引擎，自动拦截并翻译 `.bt-w-menu` 左侧菜单及底部版权，并在插件语言包就绪时自动双向绑定。
- [x] 81. 补全 `public.js` 服务控制条多语言词条：在 6 种语言的 `public.json` 与 `lan.js`（`public` 模块）补齐 `current_status`、`open`、`restart_1`、`reload_configuration` 等词条，并在 `i18n.js` 中建立保底机制，消除英文下回退中文。
- [x] 82. 规范化重构 `docker.js` 中的产品说明模块：使用 `pt(...)` 动态包装产品说明文案（核心定位、极速拉取、便捷配置、资源管控、批量运维等），并在 Docker 语言包中精准对齐翻译。
- [x] 83. 编写并运行自动化测试套件（`test/test_plugin_runtime_i18n.py`）：验证 38 个插件菜单覆盖率、Docker 弹窗渲染多语言准确性、服务控制条在 6 国语言下 0 中文残留。
- [x] 84. 全量回归测试、清理临时文件并向用户交付成果。

## 插件多国语言版本响应速度专项性能优化

- [x] 85. 消除 `soft.js` 软件管理列表渲染时的串行网络风暴：移除循环内针对 38 个插件同步请求语言包的代码，优先复用已有的全局 `plugins.xxx` 词典，使软件列表渲染耗时由 ~1500ms 骤降至 <5ms。
- [x] 86. 重构 `i18n.js` 插件语言包加载机制：引入本地二级缓存（内存 Memory + localStorage），命中缓存 0ms 直出；优化为极速异步预加载/按需加载，彻底废弃主线程同步 XHR 阻塞。
- [x] 87. 重构 `i18n.js` 中 `translatePluginDOM` 渲染引擎：彻底废除 `$con.find('div, span, p')` 暴力全量扫描与递归 text 读取，改用精确定向选择器（仅针对 `.bt-w-menu p` 与底部版权元素），消除强制同步重排（Reflow），使弹窗国际化耗时缩短至 <1ms。
- [x] 88. 优化 `plugin_api.js` 请求体验：解决 `api.post` 与业务函数双重 loading 遮罩重叠冲突，消除界面闪烁与卡顿。
- [x] 89. 优化后端 `yf.py` 中 `execShell` 与 `sanitizeCmdScripts`：为已检查过的脚本文件增加内存缓存，避免只读命令重复进行磁盘 I/O 检查。
- [x] 90. 编写专项性能基准测试与自动化回归测试套件（`test/test_plugin_performance.py`），验证优化前后各链路耗时及多语言渲染 100% 正确性。
- [x] 91. 全量回归测试验证、清理临时工具并向用户汇报。

## 插件后端打开性能深度优化与 Loading 异常修复

- [x] 92. 修复各插件服务页面 loading 文字空白与右侧上下滚动条箭头异常：
  - 完善 6 国语言公共字典（`public.json` 与 `lan.js`）中的 `loading_1`、`loading` 词条；
  - 优化 `public.js` 中的 `pluginService`，传入明确默认文本 `t('public.loading_1', '正在获取服务状态...')`，彻底杜绝空字符串；
  - 增强 `public.js` 中全局 `initLayerI18n` 拦截器支持 `layer.msg`，遇空内容自动保底注入多语言 Loading，并自动翻译常见中文加载文案；
  - 在 `site.css` 与 `ensite.css` 中为 `.layui-layer-msg .layui-layer-content` 设置 `overflow: hidden !important;`，彻底杜绝上下滚动条箭头。
- [x] 93. 实施打开插件后端杀手级优化 —— 服务端直出 HTML 内联注入插件语言包：
  - 在 `web/admin/plugins/__init__.py` 的 `/setting` 接口中，返回 `index.html` 时直接内联注入当前语言的 `_pluginDicts` 字典；
  - 前端拿到 HTML 时语言包已 100% 内存就绪，彻底免除前端向后端二次请求语言包的网络耗时（网络请求次数直接归零）。
- [x] 94. 实施打开插件后端内存级模板与静态文件缓存优化：
  - 为 `index.html` 与插件静态文件添加 Python 进程级缓存，避免每次打开弹窗都产生磁盘文件读取。
- [x] 95. 实施打开插件后端状态查询短时防抖缓存：
  - 在 `web/admin/plugins/__init__.py` 的 `/run` 接口中，针对只读状态查询 `status` 提供 2 秒轻量防抖缓存，避免弹窗初始化与默认菜单点击连续触发两次 Python 进程启动；写操作立即失效缓存。
- [x] 96. 编写并运行自动化回归测试套件（`test/test_loading_modal_and_backend_opt.py`），验证 loading 弹窗无滚动条无空白，以及后端内联注入与缓存的正确性。
- [x] 98. 排查并修复 `lan.js` 语法报错（`Unexpected identifier 'loading'`）：
  - 准确定位并修复因键名误替换导致的 6 处异常键名（`"down"loading"` 恢复为 `"downloading"`，`"up"loading"` 恢复为 `"uploading"`，`"start_up"loading"` 恢复为 `"start_uploading"`）；
  - 在全量 6 国语言的 `lan.js` 的 `public` 模块中规范注入 `loading` 与 `loading_1` 词条；
  - 运行 `node test/check_lan_syntax.js`，全部 6 种语言 `lan.js` 100% 通过 Node.js V8 语法编译与执行解析；
  - 全量自动化测试回归通过，清理临时排查脚本。

## 插件后端 run 响应性能全面优化（从 600ms 降至与 master 一致）

- [x] 99. 消除子进程中的大型 JSON 磁盘 I/O 放大：
  - 在 `web/core/yf.py` 的 `returnData` 和 `returnJson` 中加入快速短路机制（若无有效待翻译字符串，0ms 极速穿透）；
  - 在非 Flask 上下文（子进程环境）中，避免子进程读取并解析近 400KB 的巨型语言包，使子进程恢复为 master 分支的轻量纯内存极速退出。
- [x] 100. 优化 `web/core/yf.py` 中 `sanitizeCmdScripts` 快速路径：
  - 使用字符串预检快速跳过无脚本命令，消除无谓正则匹配与文件属性探测。
- [x] 101. 优化 `web/admin/plugins/__init__.py` 的 `/run` 路由：
  - 对空消息直接返回，杜绝主进程对空字符串发起多语言盲搜。
- [x] 102. 编写专项基准性能与对比测试套件（`test/test_plugin_run_speed.py`）：
  - 验证子进程与主进程单次 `/plugins/run` 响应耗时大幅缩短至 ~270ms（与 master 分支一致）。
- [x] 103. 全量回归测试、清理临时工具并向用户汇报。

## 插件自启动菜单清理与服务页面一体化集成

- [x] 104. 扩充 6 国语言词典（`public.json`、`lan.js` 与 `phrases_full.py`）：录入 `boot_start`、`boot_start_enabled`、`boot_start_disabled`、`setting_boot_start` 等开机启动相关词条，并验证多语言语法无误。
- [x] 105. 在公共框架中封装开机自启动组件（`web/static/app/public.js`）：
  - 实现 `pluginInitDSwitchHtml` 统一生成现代规范的开关组件；
  - 实现 `pluginInitDSwitchRender` 异步获取 `initd_status` 并更新状态；
  - 实现 `pluginToggleInitD` 支持开关切换、调用 `initd_install` / `initd_uninstall` 并处理响应反馈与异常回滚；
  - 在公共服务渲染函数 `pluginSetService` 的操作按钮下方自动嵌入该自启动组件。
- [x] 106. 为自定义服务页面的插件（`apache`, `caddy`, `openresty`, `pureftp`）统一挂载开机自启动组件：
  - 更新 `plugins/apache/js/httpd.js` 的 `orPluginSetService`；
  - 更新 `plugins/caddy/js/caddy.js` 的 `orPluginSetService`；
  - 更新 `plugins/openresty/js/openresty.js` 的 `orPluginSetService`；
  - 更新 `plugins/pureftp/js/ftp.js` 的 `pureftpService`。
- [x] 107. 批量清理 22 个插件左侧菜单中的“自启动”菜单项：
  - 从各插件 `index.html` 中彻底移除 `<p onclick="pluginInitD(...)">自启动</p>`。
- [x] 108. 编写专项自动化测试套件（`test/test_plugin_initd_integration.py`）：
  - 验证 22 个插件 `index.html` 无遗留自启动菜单；
  - 验证公共与定制服务页面完整嵌入开机启动组件；
  - 验证 6 国语言完整性与 Node.js 语法校验。
- [x] 109. 全量回归测试、清理临时排查工具并验收交付。

## Docker 插件容器与镜像列表 Loading 过场动画优化

- [x] 110. 在 `plugins/docker/index.html` 的 `<style>` 中扩展现代 Loading Spinner 与微动画 CSS（`.docker-spinner`, `.docker-loading-box`, `.docker-loading-text`, `.docker-table-fadein`, `.glyphicon-spin`）。
- [x] 111. 在 `plugins/docker/js/docker.js` 中封装通用表格 Loading 占位与空状态生成器（`dockerTableLoadingHtml`, `dockerTableEmptyHtml`）。
- [x] 112. 重构容器列表模块（`dockerConList`, `dockerConListRender`）：独立表格 ID `#docker_con_table`，初始载入与刷新按钮添加 Loading 过场动画、防连击禁用反馈、空状态及请求序列号防竞态保护。
- [x] 113. 重构镜像列表模块（`dockerImageList`, `dockerImageListRender`）：独立表格 ID `#docker_image_table`，初始载入与刷新按钮添加 Loading 过场动画、防连击禁用反馈、空状态及请求序列号防竞态保护。
- [x] 114. 补齐 6 国语言包（`plugins/docker/lang/{zh-CN,zh-TW,en,de,fr,it}.json`）中的容器与镜像加载及空状态提示词条。
- [x] 115. 编写专项自动化测试套件（`test/test_docker_loading_animation.py`），验证 CSS 样式定义、JS 渲染逻辑、防竞态锁及多语言 JSON 语法规范。
- [x] 116. 运行自动化测试回归验证，确保 100% 通过并清理临时文件。

## 系统加固第一阶段：P0 级高危安全与语法缺陷修复

- [x] 117. 修复插件静态文件读取接口越界漏洞（`web/admin/plugins/__init__.py`）：在 `/file` 增加 `commonpath` 严格白名单与目录逃逸防御（遇到越界直接返回 403）。
- [x] 118. 彻底废除 `plugin.callback` 中的危险 `eval()`（`web/utils/plugin.py`）：对脚本与方法名实施正则白名单校验，改用标准 Python 反射安全调用 `getattr`。
- [x] 119. 清洗 `site.py` 中 6 处历史遗留 `makeDirs(... && chmod ...)` 语法缺陷（`web/utils/site.py`）：严格拆分原生目录创建与权限分配，杜绝畸变目录名。
- [x] 120. 收紧 WebSSH SocketIO 的跨域通配符来源（`web/admin/__init__.py`）：收回 `cors_allowed_origins="*"`，防御跨站 WebSocket 劫持（CSWSH）。
- [x] 121. 修复全局语言设置越权篡改（`web/admin/setting/setting.py`）：未登录访客切换语言仅下发客户端 Cookie，登录管理员才允许持久化写入 `data/language.pl`。
- [x] 122. 编写专项自动化测试套件（`test/test_p0_security_fixes.py`），验证路径穿越防御、安全反射、目录创建规范及语言配置隔离。
- [x] 123. 运行全量测试套件回归验证，确保 100% 通过并保持开发目录整洁。

## 系统加固第二阶段：P1 级核心可靠性与性能重构

- [x] 124. 重构 `panel_task.py` 守护进程双通道架构：分离秒级高频看门狗调度线程与重型长耗时任务队列线程，彻底消除编译长任务卡死调度循环缺陷。
- [x] 125. 优化 `panel_task.py` 任务状态与异常退出码捕获：检查子进程 returncode，失败标记为 status=2 并记录错误日志，增加死循环重试熔断控制。
- [x] 126. 消除 `web/utils/system/monitor.py` 监控采集 1 秒同步挂起阻塞：优化为非阻塞时间窗口计算，单次采集耗时缩短至 <1ms。
- [x] 127. 优化 `web/utils/system/monitor.py` 历史数据清理逻辑：从每 15 秒全表 DELETE 降频为每小时批处理一次，减少 99% 的数据库写放大与锁竞争。
- [x] 128. 增强 `web/utils/system/update.py` 升级机制：一键升级流程前置强制生成核心快照，并提供一键灾备回滚自愈机制。
- [x] 129. 编写专项自动化测试套件（`test/test_p1_reliability_and_perf.py`），验证双通道解耦、退出码捕获、监控零阻塞与升级回滚功能。
- [x] 130. 运行全量测试套件回归验证，确保 100% 通过并保持开发目录整洁。

## 系统加固第三阶段：P2 级深度调优与供应链加固

- [x] 131. 加固登录验证码机制（`web/admin/dashboard/login.py`）：防范跳过 `/code` 直接登录，并在单次校验后立即注销销毁验证码，杜绝重放攻击。
- [x] 132. 强化修改密码安全体系（`web/admin/setting/setting.py` 与 `web/static/app/config.js`）：前端弹窗增加原密码字段，后端强制校验原密码有效性、提升密码复杂度（长度>=8且含字母和数字），修改后注销旧会话。
- [x] 133. 优化插件运行状态探测与并发控制（`web/utils/plugin.py`）：修复异步刷新命中旧缓存缺陷，限制多线程最大并发数为 4，常用核心插件引入轻量 PID 文件快速探测。
- [x] 134. 升级包完整性与 SHA-256 供应链安全校验（`web/utils/system/update.py`）：解压前执行 `zipfile` 完整性检测与 SHA-256 校验和验证，拦截中间人篡改包。
- [x] 135. 模板关键静态资源版本指纹补齐（`web/templates/default/*.html`）：为尚未注入 `?v={{config.version}}` 的核心脚本与样式补充版本指纹，避免浏览器旧缓存错乱。
- [x] 136. 编写专项自动化测试套件（`test/test_p2_deep_optimization.py`），验证验证码防绕过与防重放、密码原密码与复杂度校验、插件探测并发与轻量探测、升级包校验等功能。
- [x] 137. 运行全量测试套件回归验证，确保 100% 通过并保持开发目录整洁。

## 系统二次深度加固与性能跃升（安全/可靠/性能）

### 第一阶段：P0 级高危安全漏洞加固
- [x] 138. 修复分片上传接口（`upload_segment`）路径穿越与任意文件覆盖漏洞（`web/admin/files/files.py`、`web/utils/file.py`）：对文件名增加严格过滤与根路径白名单限制。
- [x] 139. 修复压缩与解压命令裸字符串拼接注入隐患（`web/utils/file.py`）：对 `uncompress`、`unzip`、`zip` 中涉及的 `sfile`、`dfile`、`path` 全面引入 `shlex.quote` 转义。
- [x] 140. 修复宝塔站点导入与数据库迁移接口的参数命令注入漏洞（`web/admin/setting/setting.py`）：对 `db_path` 与 `dbs` 参数实行合法性校验与安全转义。
- [x] 141. 编写专项自动化测试套件（`test/test_p0_deep_security.py`），验证分片上传防穿越、压缩解压安全转义与迁移命令注入防御。
- [x] 142. 运行自动化测试验证，确保 100% 通过并保持开发目录整洁。

### 第二阶段：P1 级核心可靠性与关键性能重构
- [x] 143. 推行全局 `writeFile` 原子写入机制（`web/core/yf.py`）：采用“临时文件写入 + 刷盘 + `os.replace` 原子替换”，杜绝断电/OOM/磁盘满时的零字节损坏。
- [x] 144. 重构任务取消机制（`web/utils/task.py`）：引入进程组（Process Group）精准清理孤儿编译子进程，杜绝 `kill -9` 误杀守护进程。
- [x] 145. 重构 `getDirList` 与 `sortFileList`（`web/utils/file.py`、`web/core/yf.py`）：改用 `os.scandir` 实现大目录秒级加载与单次系统调用。
- [x] 146. 加固远程下载接口（`panel_task.py`、`web/admin/files/files.py`）：限制 URL 协议为 http/https，拦截 `file://` 等非安全协议，校验目标文件名防越界。
- [x] 147. 编写专项自动化测试套件（`test/test_p1_deep_reliability_perf.py`），验证原子写入、进程组精准清理、os.scandir 高效遍历与协议校验。
- [x] 148. 运行自动化测试验证，确保 100% 通过并保持开发目录整洁。

### 第三阶段：P2 级深度调优与工程规范清洗
- [x] 149. 根目录与数据目录路径锚定物理文件绝对路径（`web/core/db.py`、`web/core/yf.py`）：彻底杜绝 `os.getcwd()` 漂移脱轨。
- [x] 150. 优化反代环境下真实 IP 识别与防误封（`web/core/yf.py`）：安全识别 X-Forwarded-For 与 X-Real-IP。
- [x] 151. 优化大文件日志逆序读取（`web/core/yf.py`）：修复 UTF-8 中文边界截断与多余 strip 破坏缩进问题。
- [x] 152. 清理 `web/utils/site.py` 遗留的外部 `mkdir -p` / `rm -rf` 子进程，替换为 Python 标准库原生实现。
- [x] 153. 编写专项自动化测试套件（`test/test_p2_deep_refine.py`），验证路径锚定、反代 IP 识别、日志逆序读取与原生文件操作。
- [x] 154. 全量回归测试验证，确保 100% 通过并清理临时文件。

## 修复推荐安装重复弹出缺陷

- [x] 155. 修复 `web/core/yf.py` 中 `getFatherDir()` 目录层级错误：恢复为物理绝对路径向上两级（`os.path.dirname(os.path.dirname(_PANEL_ROOT_DIR))`），确保 `getServerDir()` 精确指向 `/www/server`，彻底恢复插件目录探测机制。
- [x] 156. 强化推荐安装弹窗防重弹机制（`web/utils/plugin.py`、`web/static/app/index.js`）：后端增加持久化防重弹标记支持，前端在展示/关闭时增加客户端状态记录，确保推荐安装只在面板初次打开展示一次，杜绝后续重复弹出。
- [x] 157. 编写专项自动化回归测试（`test/test_recommend_install_bug.py`），验证 `getFatherDir()`、`getServerDir()` 路径计算正确性以及推荐安装仅初次弹出的防重逻辑。
- [x] 158. 运行全量测试套件回归验证，清理临时文件。

## 修复网站修改弹窗错位与按钮文字污染缺陷

- [x] 159. 修复 `web/static/app/site.js` 中的 `webEdit` 弹窗结构与样式：恢复标准双栏布局 `.bt-w-menu pull-left` 与 `.bt-w-con webedit-con pd15`，恢复窗口标准尺寸 `['950px','780px']`，补全 `defaultTab` 高亮切换与 `success` 初始化。
- [x] 160. 净化全量 6 国语言包中 `site.add` 词条：将 `web/static/language/*/{lan.js,template.json}` 中被污染的 `',1)">添加` 修正为标准的纯文本（中文“添加”、英文“Add”、繁体“新增”、德文“Hinzufügen”、法文“Ajouter”、意文“Aggiungi”）。
- [x] 161. 编写专项自动化回归测试（`test/test_webedit_layout_and_add_btn.py`），验证 `site.js` 中 `webEdit` DOM 结构类名与全语种 `site.add` 词条的纯净性。
- [x] 162. 运行全量测试套件回归验证，清理临时排查文件。

## 修复网站修改子目录绑定报错及各Tab功能深度排查

- [x] 163. 修复 `web/static/app/site.js` 中 `dirBinding` 数据解包缺陷（解包 `data.data` 并增加 `dirs`/`binding` 空保底），修正删除绑定函数名为 `delDirBind`。
- [x] 164. 重构修复 `web/static/app/site.js` 中 `phpVersion` 与 `setPHPVersion` 的 HTML 残损拼接（补全 `<select id='phpVersion'>`、去除乱码片段、规范化 `layer.msg` 提示文案）。
- [x] 165. 修复 `web/static/app/site.js` 中 `configFile` 未闭合标签 `</textarea>` 并恢复保存配置按钮 `#SaveConfigFileBtn` 与说明列表。
- [x] 166. 强化 `site.js` 中 `toProxy`、`to301`、`rewrite`、`webPathEdit` 等关键 Tab 函数的空值防御，彻底杜绝 `reading 'length'` 类崩溃。
- [x] 167. 编写专项回归测试套件（`test/test_webedit_tabs_integrity.py`）并全量回归验证。

## 对齐历史版本彻底修复伪静态（rewrite）CodeMirror报错

- [x] 168. 对齐 Git 历史版本重构 `web/static/app/site.js` 中的 `rewrite` 伪静态模块：恢复嵌套调用 `/site/get_rewrite_conf` 获取真实配置路径，消除写死路径与 `editor.setValue(undefined)` 导致的 CodeMirror `reading 'split'` 崩溃，修正另存为模板弹窗标题与逻辑。
- [x] 169. 编写专项自动化回归测试并进行全量回归验证。

## 修复网站修改弹窗（webEdit）右侧大片白屏缺陷（CSS Flex弹性盒脱节）

- [x] 170. 修复 `web/static/app/site.js` 中 `webEdit` 弹窗 HTML 结构：补全 `<div class='bt-w-main'>` 弹性布局容器包裹，使左侧侧边栏 `.bt-w-menu` 与右侧主视图 `#webedit-con.bt-w-con` 纳入 Flex 上下文，彻底解决因 `float: none !important` 导致的纵向掉落、被裁切白屏问题。
- [x] 171. 在 `web/static/css/site.css` 和 `web/static/css/ensite.css` 中增强兼容兜底：为包含 `.bt-w-menu` 的父级增加 flex 弹性布局兜底，双重保障弹窗左右分栏永不错位。
- [x] 172. 更新并扩展自动化回归测试（`test/test_webedit_layout_and_add_btn.py`），验证 `bt-w-main` 弹性容器存在与 CSS 规则规范性，运行全量测试验证无回归。

## 修复网站修改中流量限制文字丢失与重定向接口302报错缺陷

- [x] 173. 补全全语种语言包中缺失的 `site.limit_net_1` ~ `15` 词条，并在 `web/static/app/site.js` 的 `limitNet` 函数中加入中文兜底保底，彻底解决复选框与冒号前文字丢失、圆点无内容问题。
- [x] 174. 修复后端路由与前端接口调用（`web/admin/site/redirect.py`、`web/static/app/site.js`）：后端增加 `/site/get_redirect_list` 路由别名，前端将 `to301` 列表请求修正为 `/site/get_redirect`，彻底解决 302 重定向卡在“正在获取数据...”的死锁。
- [x] 175. 重构对齐 `web/static/app/site.js` 中 `to301` 的完整功能：恢复多重定向列表渲染（`r_from`、`r_type`、`keep_path`）、创建重定向弹窗、删除重定向与 CodeMirror 配置文件在线编辑保存功能。
- [x] 176. 编写专项回归测试套件（`test/test_limitnet_and_redirect_fix.py`），验证语言包词条、路由端点及前端语法逻辑，执行全量回归。

## 优化网站修改中子目录绑定与流量限制排版及间距样式

- [x] 177. 重构 `web/static/app/site.js` 中 `dirBinding` 表单与表格排版：采用现代弹性盒布局（Flex），扩大各输入控件与标签间距（域名输入框与“子目录”标签间增加独立呼吸空间，彻底消除拥挤紧贴），增强表格空状态提示。
- [x] 178. 重构 `web/static/app/site.js` 中 `limitNet` 流量限制表单排版并更新 CSS（`web/static/css/site.css`、`web/static/css/ensite.css`）：彻底解决标签因 64px 狭窄宽度导致的折行断行问题，规范标签宽度为 110px、禁止换行、输入框统一对齐、按钮左边距对齐，增强层次分隔。
- [x] 179. 编写专项回归测试套件（`test/test_webedit_styling_and_layout_opt.py`），验证子目录绑定间距样式、流量限制标签不折行与排版规范，运行全量测试验证无回归。

## 排查插件外部与内部状态不一致缺陷（OpenResty外部显示停止/内部显示开启）

- [x] 180. 深入排查并定位外部卡片与内部弹窗状态不一致的根因：确认 `web/core/yf.py` 缺失 `checkPid` 方法引发 `AttributeError` 被静默捕获、`checkStatusQuick` 返回 `False` 阻断兜底降级链路等核心诱因。
- [x] 181. 在 `web/core/yf.py` 中实现标准且健壮的跨平台进程检测函数 `checkPid(pid)`（支持 Linux `os.kill(pid, 0)`、`errno.EPERM`、`/proc/{pid}` 双重判定，以及 Windows `psutil` 兼容）。
- [x] 182. 重构 `web/utils/plugin.py` 中的快速探测逻辑（`checkStatusQuick` 与 `checkStatusReal`）：修复调用 `yf.checkPid`，在无法确认存活时返回 `None` 触发官方 `status()` 动态兜底，确保 OpenResty、MySQL、Redis、Pure-FTPd、PHP 内外状态 100% 对齐。
- [x] 183. 检查并对齐 `plugins/redis/index.py` 中调用 `yf.checkPid` 的逻辑，确保其与 `yf.py` 完美兼容。
- [x] 184. 编写专项自动化回归测试套件（`test/test_plugin_status_detection.py`），验证 `yf.checkPid` 在存活/失效/异常 PID 下的表现，以及 5 大核心服务在 PID 存在/缺失/非标路径下的状态探测与兜底降级。

## 修复插件服务操作500报错与确认弹窗空白缺失缺陷

- [x] 186. 补全 6 国语言包（`zh-CN`, `zh-TW`, `en`, `de`, `fr`, `it`）中 `public` 命名空间缺失的服务操作词条（`stop_1`, `start_1`, `restart_2`, `overload`, `force_stop_kill`, `are_you_sure_you`, `serving_please_wait_moment`, `service_has`, `service_failed`），确保多语言统一对齐。
- [x] 187. 优化修复 `web/static/app/public.js` 中 `pluginOpService`：增加中文保底文案（fallback），优化确认弹窗内容排版与防滚动条样式，彻底解决确认框空白及垂直滚动箭头问题。
- [x] 188. 加固 `web/utils/plugin.py` 中 `runByCache` 与 `run` 方法：对配置数据增加 `dict` 类型安全校验与全局异常兜底，增强执行脚本异常捕获与友好返回。
- [x] 189. 加固 `web/admin/plugins/__init__.py` 中 `/run` 路由：修复视图函数 `def list():` 遮蔽 Python 内置 `list` 导致的致命 `TypeError`，添加全局 `try...except` 保护与日志记录，对非致命 stderr 输出进行智能判定（若成功输出 `ok` 则判定为成功），保证 API 永远返回标准 JSON 结构，彻底杜绝 500 Internal Server Error。
- [x] 190. 编写专项自动化回归测试套件（`test/test_plugin_service_ops_and_modal.py`），验证全语种词条完整性、前端确认框回退机制、缓存操作容错与路由安全降级。
- [x] 191. 运行全量测试套件回归验证，清理开发过程中的临时文件。


## 彻底修复服务状态修改后外部状态自动刷新与防颠簸问题

- [x] 195. 彻底清除静态文件浏览器强缓存障碍（`web/admin/plugins/__init__.py`、`plugins/openresty/index.html` 等）：对 `/plugins/file` 路由中的 `.js` 与 `.css` 移除 30 天强缓存，改为 `no-cache, must-revalidate`；在各插件 `index.html` 脚本加载路径中注入动态时间戳。
- [x] 196. 重构后端状态写操作即时对齐与延迟校准机制（`web/utils/plugin.py`、`web/admin/plugins/__init__.py`）：在执行 `stop`、`start`、`restart` 等状态操作成功后，精确将目标状态写入缓存，杜绝立即并发探测因进程退出/拉起物理耗时而误判（例如 stop 后进程未彻底退出被误判为 True 并回写缓存）；2 秒后启动异步最终物理校验。
- [x] 197. 前端强化 DOM 属性绑定与乐观状态保护（`web/static/app/soft.js`、`web/static/app/public.js`）：在表格行及状态列明确注入 `data-name` 与 `data-plugin` 属性，`window.refreshExternalPluginStatus` 采用高优先级属性选择器秒级翻转图标，并设立短时间本地状态保护锁防止异步早到包数据颠簸。
- [x] 198. 编写自动化回归测试套件并运行全量测试验证，清理测试临时文件。

## 软件菜单分类切换延迟与插件状态探测性能优化

- [x] 199. 修复 `web/utils/plugin.py` 中异步刷新缓存覆写缺陷：改暴力覆盖为增量字典合并（`cached_data.update(fresh_data)`），彻底解决分类切换时全局缓存被冲刷踩踏的问题。
- [x] 200. 在 `checkStatusMThreadsByCache` 中过滤无需展示状态的插件（`display_status is False`）：直接跳过探测队列并赋默认状态，杜绝工具类插件产生无意义的外部子进程调用。
- [x] 201. 扩展 `checkStatusQuick` 轻量快速探针：补充 Docker、OP_WAF 防火墙、Fail2Ban 防火墙、Swap 虚拟内存等服务的极速状态检测，使冷启动耗时从百毫秒级降至毫秒级。
- [x] 202. 编写专项自动化回归测试套件（`test/test_plugin_list_perf_opt.py`），验证缓存增量合并、`display_status` 过滤机制与快速探针准确性。
- [x] 203. 运行全量自动化测试套件回归验证，确保 100% 通过并清理临时文件。

## 首页提醒修改即时刷新与全局配置缓存优化

- [x] 204. 在 `web/utils/config.py` 中实现标准全局变量缓存主动失效函数 `clearGlobalVarCache()`，保持原有 30 秒 TTL 缓存机制提升系统性能的同时提供即时刷新机制。
- [x] 205. 在 `web/admin/setting/setting.py` 中接入即时失效机制：在 `set_home_notice` 保存后立即触发 `clearGlobalVarCache()`，并对齐重构 `set_webname`、`set_ip`、`set_backup_dir`、`set_www_dir`、`set_status_code`、`set_cdn_status`、`set_gpu_detect`、`save_menu_config` 的缓存即时刷新。
- [x] 206. 编写专项自动化回归测试套件（`test/test_home_notice_cache.py`），验证 30 秒性能读缓存、写时主动失效、`set_home_notice` 修改后即时生效与日常访问命中缓存。
- [x] 207. 运行自动化测试套件进行全面回归验证，确保 100% 通过并清理临时测试文件。

## 文件管理页面刷新按钮现代化样式升级

- [x] 208. 优化 `web/templates/default/files.html`：将路径栏右侧旧版灰色刷新按钮重构为统一现代化绿色刷新组件（`.btn-refresh-icon.refreshBtn`），嵌入矢量 SVG 旋转图标，尺寸适配为 28px 高度，接入 `yfRefreshBtn` 顺滑旋转动效与 6 国语言国际化属性。
- [x] 209. 优化 `web/static/css/site.css` 与 `web/static/css/ensite.css`：为 `.refreshBtn.btn-refresh-icon` 补全专用规则（高度 28px、`margin-left: 6px` 呼吸留白、垂直居中对齐、Hover 浮起与 Active 按压动效）。
- [x] 210. 优化 `web/static/app/files.js`：为第二行工具栏刷新按钮绑定 `yfRefreshBtn` 旋转动效，并确保 `calcPathWidth` 动态宽度算法与新刷新按钮完美契合。
- [x] 211. 编写专项自动化测试套件（`test/test_files_refresh_btn.py`）：验证刷新按钮结构、SVG 矢量图标、多语言属性、CSS 样式规则与宽度自适应算法。
- [x] 212. 运行自动化测试套件回归验证，确保 100% 通过并清理临时排查文件。

## 文件管理复制/剪切后红框位置粘贴按钮修复与单次粘贴控制

- [x] 213. 补全 6 国语言词典（`template.json`、`lan.js`）：在 6 国语言（zh-CN, zh-TW, en, de, fr, it）的 `files` 命名空间中录入 `paste` 词条，并修正完善 `paste_all`，确保语法正确与多语言无硬编码。
- [x] 214. 重构 `web/static/app/files.js` 中粘贴按钮渲染与显示逻辑：
  - 彻底移除左侧 `BarTools` 中错误追加的单文件粘贴按钮；
  - 重构 `showSeclect()`，统一管理红框位置（`#Batch`）的渲染：当无多选时检测单文件或批量剪贴板，智能展示高亮绿色粘贴按钮（`.btn.btn-success.btn-sm`）；
  - 动态计算 `#Batch` 偏移，精准自适应贴合在回收站左侧，彻底解决历史遗留的冲刷清空缺陷与多语言重叠隐患。
- [x] 215. 重构 `copyFile`、`cutFile`、`pasteFile` 与 `batchPaste` 交互状态流转：
  - 点击“复制”或“剪切”时立即写入状态并即时刷新红框粘贴按钮（0ms 即现），接入多语言提示；
  - 点击“粘贴”时立即消费并清除剪贴板状态，即刻隐藏红框粘贴按钮，确保一次复制或剪切仅能粘贴一次。
- [x] 216. 编写专项自动化测试套件（`test/test_files_paste_button.py`）：
  - 验证 6 国语言词条完整性与 `lan.js` 语法无误；
  - 验证 `files.js` 中单文件与批量复制/剪切的状态互斥、即时显示、单次点击消费后隐藏逻辑；
  - 验证 `BarTools` 无多余残留与 `#Batch` 自适应布局。
- [x] 217. 运行全量自动化测试回归验证，确保 100% 通过并清理临时排查文件。

## 粘贴覆盖新旧文件大小比对与按钮间距美化优化

- [x] 218. 后端扩展 `check_exists_files` 接口（`web/admin/files/files.py`）：
  - 支持接收单文件来源路径 `sfile` 与读取批量来源路径；
  - 同时提取并返回目标旧文件大小（`size`）与来源新文件大小（`new_size`），以及对应修改时间。
- [x] 219. 前端重构覆盖确认弹窗与新旧大小比对（`web/static/app/files.js`）：
  - 向 `/files/check_exists_files` 传入 `sfile` 来源路径；
  - 封装现代化覆盖比对表格组件，展示 `旧大小 <= 新大小`（如 `200KB <= 501KB`），加入警示提示横幅与卡片式表格，弹窗适度拓宽至 540px，全面提升视觉美观度；
  - 适配 6 国语言词条（表头比对提示等）。
- [x] 220. 增大粘贴按钮与回收站间距（`web/static/app/files.js`）：
  - 将粘贴按钮与回收站的呼吸间隔从 10px 提升至宽裕的 20px（`rightPos = trashRight + trashWidth + 20`）；
  - 增强回收站元素宽度获取健壮性，确保视觉上保持明显间距，彻底消除拥挤粘连。
- [x] 221. 编写专项自动化测试套件（`test/test_paste_overwrite_compare.py`）并全量回归验证，确保 100% 通过。

## 消除底部横向滚动条与粘贴/回收站间距拉开优化

- [x] 222. 消除页面底部横向滚动条缺陷（`web/static/css/site.css`, `web/static/css/ensite.css`, `web/static/app/files.js`）：
  - 为 `#tipTools` 增加 `box-sizing: border-box !important; width: 100% !important; left: 0; right: 0;`；
  - 移除 `files.js` 中将 `$("#tipTools").width($(".file-box").width())` 导致 padding 溢出 30px 的旧逻辑，规范为安全自适应；
  - 在全局 CSS（`html, body`, `.main-content`, `.file-box`）设置 `overflow-x: hidden`，彻底绝除横向滚动条。
- [x] 223. 拉开粘贴按钮与回收站间距（`web/templates/default/files.html`, `web/static/app/files.js`）：
  - 计入回收站自带的 `margin-right: 20px` 与实际边框位置，在 `showSeclect()` 中设置真实安全间隔（`rightPos >= 205px`）；
  - 更新 `files.html` 中 `#Batch` 初始行内定位为 `right: 205px`，确保初次呈现与状态切换时均具备显著可见的呼吸间隙。
- [x] 224. 编写并运行自动化回归测试套件（`test/test_paste_spacing_and_scrollbar.py`），确保全绿通过并清理临时文件。

## 修复回收站与右侧视图切换按钮间距（三者等宽呼吸间距）

- [x] 225. 修复回收站与右侧视图切换按钮粘连缺陷（`web/static/app/files.js`, `web/templates/default/files.html`）：
  - 将 `#recycle_bin` 的绝对定位设为 `right: 107px; margin-right: 0;`，与右侧视图切换按钮保持标准 20px 呼吸间距；
  - 同步调整 `#Batch` 初始定位与 `showSeclect()` 计算基准为 `right: 216px`（`rightPos >= 216px`），保持粘贴按钮与回收站之间对称维持 >=20px 宽裕间距。
- [x] 226. 完善自动化回归测试（`test/test_paste_spacing_and_scrollbar.py`），验证三者间距均严格保持在 20px 以上，全绿通过并清理临时文件。



