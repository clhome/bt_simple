# -*- coding: utf-8 -*-
"""
文件管理页面多语言词条精简与防重叠弹性布局自动化测试套件
验证范围：
1. 6 国语言词典（zh-CN, zh-TW, en, fr, de, it）中 files 模块精简词条正确性；
2. site.css 中 .file_search 弹性排版、居中对齐与防折行特性；
3. files.html 中搜索框 padding-right 与结构合理性；
4. files.js 中动态可用宽度计算与回收站多语言接入。
"""

import json
import os
import re
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, "web")
LANG_DIR = os.path.join(WEB_DIR, "static", "language")
SITE_CSS_PATH = os.path.join(WEB_DIR, "static", "css", "site.css")
FILES_HTML_PATH = os.path.join(WEB_DIR, "templates", "default", "files.html")
FILES_JS_PATH = os.path.join(WEB_DIR, "static", "app", "files.js")

SUPPORTED_LANGUAGES = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]

EXPECTED_TRANSLATIONS = {
    "include_sub": {
        "zh-CN": "包含子目录",
        "zh-TW": "包含子目錄",
        "en": "Subdirs",
        "fr": "Sous-dossiers",
        "de": "Unterverz.",
        "it": "Sottocartelle"
    },
    "total_of_directory_and": {
        "zh-CN": "共 {1} 个目录，{2} 个文件，",
        "zh-TW": "共 {1} 個目錄，{2} 個檔案，",
        "en": "Dirs: {1}, Files: {2}, Size: ",
        "fr": "Rép : {1}, Fich : {2}, Taille : ",
        "de": "Verz: {1}, Date: {2}, Größe: ",
        "it": "Dir: {1}, File: {2}, Dim: "
    },
    "get": {
        "zh-CN": "获取",
        "zh-TW": "取得",
        "en": "Calc",
        "fr": "Calc",
        "de": "Berech.",
        "it": "Calc"
    },
    "path_root": {
        "zh-CN": "根目录",
        "zh-TW": "根目錄",
        "en": "Root",
        "fr": "Root",
        "de": "Root",
        "it": "Root"
    },
    "site_root": {
        "zh-CN": "网站总目录",
        "zh-TW": "網站總目錄",
        "en": "Websites",
        "fr": "Sites",
        "de": "Websites",
        "it": "Siti web"
    },
    "panel_root": {
        "zh-CN": "御风面板",
        "zh-TW": "御風面板",
        "en": "Panel",
        "fr": "Panneau",
        "de": "Panel",
        "it": "Pannello"
    },
    "recycle_bin": {
        "zh-CN": "回收站",
        "zh-TW": "資源回收筒",
        "en": "Recycle Bin",
        "fr": "Corbeille",
        "de": "Papierkorb",
        "it": "Cestino"
    }
}


class TestFilesI18nLayout(unittest.TestCase):

    def test_compact_translations_in_all_languages(self):
        """验证 6 国语言词典中精简词汇 100% 准确写入 template.json 与 lan.js"""
        for lang in SUPPORTED_LANGUAGES:
            tpl_path = os.path.join(LANG_DIR, lang, "template.json")
            lan_path = os.path.join(LANG_DIR, lang, "lan.js")

            self.assertTrue(os.path.exists(tpl_path), f"{lang}/template.json 不存在")
            self.assertTrue(os.path.exists(lan_path), f"{lang}/lan.js 不存在")

            with open(tpl_path, "r", encoding="utf-8") as f:
                tpl_data = json.load(f)
            files_tpl = tpl_data.get("files", {})

            with open(lan_path, "r", encoding="utf-8") as f:
                lan_content = f.read()

            for key, expected_by_lang in EXPECTED_TRANSLATIONS.items():
                expected_val = expected_by_lang[lang]
                actual_tpl_val = files_tpl.get(key)
                self.assertEqual(
                    actual_tpl_val, expected_val,
                    f"[{lang}] template.json 中 files.{key} 期望 '{expected_val}', 实际为 '{actual_tpl_val}'"
                )
                escaped_expected = json.dumps(expected_val, ensure_ascii=False)
                self.assertIn(
                    f'"{key}": {escaped_expected}', lan_content,
                    f"[{lang}] lan.js 中未找到有效键值 \"{key}\": {escaped_expected}"
                )

    def test_site_css_file_search_styles(self):
        """验证 site.css 中 .search-input-box 与 .file_search 使用 Flex 布局且无固定 width: 85px"""
        with open(SITE_CSS_PATH, "r", encoding="utf-8") as f:
            css_content = f.read()

        self.assertIn(".search-input-box {", css_content, "site.css 应包含 .search-input-box 样式定义")
        self.assertNotIn("width: 85px", css_content, "site.css 中不应再包含硬编码 width: 85px")
        self.assertIn("display: inline-flex", css_content, ".search-input-box 应采用 inline-flex 布局")
        self.assertIn("white-space: nowrap", css_content, "应声明 white-space: nowrap 防止文字换行错位")

    def test_files_html_search_box_layout(self):
        """验证 files.html 复合搜索框结构、输入框与复选框合理性及与下方框体严格垂直对齐"""
        with open(FILES_HTML_PATH, "r", encoding="utf-8") as f:
            html_content = f.read()

        self.assertIn('class="search-input-box"', html_content, "未找到搜索外层复合容器 .search-input-box")
        self.assertIn('id="search_file"', html_content, "未找到搜索框 id search_file")
        self.assertIn('class="file_search"', html_content, "未找到 .file_search 容器")
        self.assertIn('id="search_all"', html_content, "未找到复选框 id search_all")
        self.assertIn('white-space: nowrap;', html_content, "统计栏外层容器应添加 white-space: nowrap 防止折行遮挡")
        self.assertIn('right: 30px;', html_content, "搜索框应设置 right: 30px 与下方框体最右边框垂直对齐")
        self.assertIn('margin-right: 15px;', html_content, "切换按钮组应设置 margin-right: 15px 与下方框体最右边框垂直对齐")

    def test_files_js_dynamic_width_and_i18n(self):
        """验证 files.js 中 calcPathWidth 动态占满算法、防遮挡安全留白与智能按需展示 Calc 按钮"""
        with open(FILES_JS_PATH, "r", encoding="utf-8") as f:
            js_content = f.read()

        self.assertIn("function calcPathWidth()", js_content, "files.js 应包含动态计算可用宽度的 calcPathWidth 函数")
        self.assertNotIn('width($(".file-box").width()-700)', js_content, "不应再出现写死的 -700 减量")
        self.assertNotIn("available > 350", js_content, "应去除 350px 硬编码上限以使地址栏尽量占满")
        self.assertIn("safeGap = 45", js_content, "应预留至少 45px 舒适安全缓冲杜绝遮挡")
        self.assertIn("right: 87px;", js_content, "回收站按钮应向左平移至 right: 87px 与切换按钮组保持整齐间隙")
        self.assertIn("calcPathWidth();", js_content, "窗口 resize 与数据渲染后应触发 calcPathWidth()")

        # 智能按需显示 Calc 按钮：仅在有子目录时显示
        self.assertIn("rdata.dir && rdata.dir.length > 0", js_content, "应仅在存在子目录时渲染 Calc 按键")

        # 验证 getDisk 中的回收站多语言接入
        self.assertNotIn('title="回收站"', js_content, "getDisk 中不应再硬编码 title=\"回收站\"")
        self.assertNotIn('&nbsp;回收站</span>', js_content, "getDisk 中不应再硬编码 &nbsp;回收站</span>")
        self.assertIn("trashText", js_content, "getDisk 中应使用 trashText 动态多语言变量")

    def test_dir_size_calculation_and_formatting(self):
        """验证后端容量格式化 formatFileSize 与实际文件字节数统计一致性"""
        import sys
        sys.path.insert(0, WEB_DIR)
        from utils import file as file_util

        self.assertEqual(file_util.formatFileSize(0), "0 B")
        self.assertEqual(file_util.formatFileSize(796), "796 B")
        self.assertEqual(file_util.formatFileSize(10003), "9.77 KB")
        self.assertEqual(file_util.formatFileSize(1048576), "1.00 MB")
        self.assertEqual(file_util.formatFileSize(1073741824), "1.00 GB")

        # 验证非存在路径
        self.assertEqual(file_util.getDirSizeByBash("/path_not_exists_test_12345"), "0 B")


if __name__ == "__main__":
    unittest.main()
