# -*- coding: utf-8 -*-
"""
验证关于页面与公共词典的多语言适配及UI修复正确性测试套件
"""
import os
import sys
import json
import re
import unittest

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = r"f:\git\gitea20250909\bt_simple"
TOOLS_DIR = os.path.join(BASE_DIR, "scripts", "tools")
LANG_DIR = os.path.join(BASE_DIR, "web", "static", "language")
PUBLIC_JS = os.path.join(BASE_DIR, "web", "static", "app", "public.js")

REQUIRED_PUBLIC_KEYS = [
    "yufeng_panel_btsimple",
    "quzhou_yufeng_technology_co",
    "proudly_presented_by",
    "retrieving_panel_resource_usage",
    "yufeng_panel_current_server",
    "memory",
    "failed_to_retrieve_resources",
    "quzhou_yufeng_technology_yftec",
    "all_rights_reserved_admin",
    "loading_instructions",
    "search_content",
    "previous",
    "next",
    "replace_with",
    "replace_current",
    "replace_all",
    "replace",
    "all_1"
]

REQUIRED_AUTO_KEYS = [
    "public_auto_str_127",
    "public_auto_str_128",
    "public_auto_str_129",
    "public_auto_str_130",
    "public_auto_str_131",
    "public_auto_str_132",
    "public_auto_str_133",
    "public_auto_str_134",
    "public_auto_str_135",
    "public_auto_str_136",
    "public_auto_str_137",
    "public_auto_str_138",
    "public_auto_str_140",
    "public_auto_str_141",
    "public_auto_str_142",
    "public_auto_str_143"
]

chinese_char_pattern = re.compile(r'[\u4e00-\u9fff]')

class TestAboutI18n(unittest.TestCase):
    def test_01_phrases_full(self):
        """测试 phrases_full.py 中的词典"""
        sys.path.insert(0, TOOLS_DIR)
        import phrases_full
        dict_full = phrases_full.FULL_I18N_DICTIONARY
        public_dict = dict_full.get("public", {})

        for k in REQUIRED_PUBLIC_KEYS:
            self.assertIn(k, public_dict, f"phrases_full.py public section 缺失键: {k}")
            item = public_dict[k]
            for lang in ['en', 'fr', 'de', 'it']:
                val = item.get(lang, '')
                self.assertFalse(chinese_char_pattern.search(val), f"phrases_full.py [{k}] 在 {lang} 中含有中文: {val}")

        for k in REQUIRED_AUTO_KEYS:
            self.assertIn(k, public_dict, f"phrases_full.py public section 缺失自动键: {k}")
            item = public_dict[k]
            for lang in ['en', 'fr', 'de', 'it']:
                val = item.get(lang, '')
                self.assertFalse(chinese_char_pattern.search(val), f"phrases_full.py [{k}] 在 {lang} 中含有中文: {val}")

    def test_02_languages_json_and_lan_js(self):
        """测试 6 国语言包 (zh-CN, zh-TW, en, fr, de, it) 的 public.json, template.json 和 lan.js"""
        LANGS = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]
        for lang in LANGS:
            lang_dir = os.path.join(LANG_DIR, lang)

            # 1. public.json
            pub_path = os.path.join(lang_dir, "public.json")
            self.assertTrue(os.path.exists(pub_path), f"{lang}/public.json 不存在")
            with open(pub_path, "r", encoding="utf-8") as f:
                pub_data = json.load(f)
            for k in REQUIRED_PUBLIC_KEYS:
                self.assertIn(k, pub_data, f"{lang}/public.json 缺失键: {k}")
                if lang in ['en', 'fr', 'de', 'it']:
                    self.assertFalse(chinese_char_pattern.search(pub_data[k]), f"{lang}/public.json [{k}] 含有中文字符: {pub_data[k]}")

            # 2. template.json
            tmpl_path = os.path.join(lang_dir, "template.json")
            self.assertTrue(os.path.exists(tmpl_path), f"{lang}/template.json 不存在")
            with open(tmpl_path, "r", encoding="utf-8") as f:
                tmpl_data = json.load(f)
            for k in REQUIRED_PUBLIC_KEYS:
                self.assertIn(k, tmpl_data, f"{lang}/template.json 缺失键: {k}")

            # 3. lan.js
            lan_path = os.path.join(lang_dir, "lan.js")
            self.assertTrue(os.path.exists(lan_path), f"{lang}/lan.js 不存在")
            with open(lan_path, "r", encoding="utf-8") as f:
                lan_content = f.read()
            for k in REQUIRED_PUBLIC_KEYS:
                self.assertIn(f'"{k}":', lan_content, f"{lang}/lan.js 缺失键: {k}")

    def test_03_public_js_rendering_structure(self):
        """测试 web/static/app/public.js 中的渲染结构与调用"""
        with open(PUBLIC_JS, "r", encoding="utf-8") as f:
            js_content = f.read()

        about_part = js_content[js_content.find("var showRelease"):js_content.find("var showRelease") + 4000]

        # 检查是否有多层嵌套
        if "('<h2" in js_content and "('<h2" in js_content[js_content.find("('<h2") + 5:]:
            self.assertNotIn("('<h2", about_part, "public.js showRelease 仍存在 ('<h2 嵌套")

        # 检查内存图标数量
        hdd_icon_count = about_part.count("glyphicon-hdd")
        self.assertEqual(hdd_icon_count, 1, f"public.js showRelease 中的 glyphicon-hdd 图标数量异常: {hdd_icon_count}")

        # 检查是否有多余的荣誉出品标签嵌套
        self.assertNotIn("荣誉出品</p></a>", about_part)
        self.assertNotIn("</a> 荣誉出品</p>", about_part)

        # 检查调用
        self.assertIn("t('public.yufeng_panel_btsimple'", about_part)
        self.assertIn("t('public.quzhou_yufeng_technology_co'", about_part)
        self.assertIn("t('public.proudly_presented_by'", about_part)
        self.assertIn("t('public.yufeng_panel_current_server'", about_part)
        self.assertIn("t('public.memory'", about_part)
        self.assertIn("t('public.failed_to_retrieve_resources'", about_part)

if __name__ == '__main__':
    unittest.main()
