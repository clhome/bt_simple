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
