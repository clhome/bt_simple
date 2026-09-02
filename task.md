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
