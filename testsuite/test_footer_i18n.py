# -*- coding: utf-8 -*-
"""
自动化测试页面底部 Footer 品牌与多语言渲染测试
"""

import os
import sys
import unittest
import json

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "web"))

import jinja2
from core.i18n import t as backend_t

class TestFooterI18n(unittest.TestCase):
    def setUp(self):
        self.template_dir = [
            os.path.join(ROOT_DIR, "web", "templates", "default"),
            os.path.join(ROOT_DIR, "web", "templates")
        ]
        self.env = jinja2.Environment(loader=jinja2.FileSystemLoader(self.template_dir))

    def test_backend_t_fallback(self):
        """测试后端 t 函数遇到不存在的 key 时能正确使用默认参数回退，而不是返回 key 名"""
        res = backend_t("non_existing_key_xyz", "默认回退文本")
        self.assertEqual(res, "默认回退文本")

    def test_footer_translations_all_languages(self):
        """测试所有 6 国语言包中 Footer 与 Yufeng 品牌词条完全合规"""
        langs = {
            "zh-CN": {
                "common.brand_panel": "御风面板",
                "public.brand_company": "御风科技",
                "public.ip_privacy_check": "IP隐私安全检测",
                "public.tools_box": "御风工具箱",
                "public.company_signature": "衢州御风科技有限公司出品",
                "public.source_code": "源码"
            },
            "zh-TW": {
                "common.brand_panel": "御風面板",
                "public.brand_company": "御風科技",
                "public.ip_privacy_check": "IP隱私安全檢測",
                "public.tools_box": "御風工具箱",
                "public.company_signature": "衢州御風科技有限公司出品",
                "public.source_code": "源碼"
            },
            "en": {
                "common.brand_panel": "Yufeng Panel",
                "public.brand_company": "Yufeng Technology",
                "public.ip_privacy_check": "IP Privacy & Security Check",
                "public.tools_box": "Yufeng Toolbox",
                "public.company_signature": "Produced by Quzhou Yufeng Technology Co., Ltd.",
                "public.source_code": "Source Code"
            },
            "fr": {
                "common.brand_panel": "Panneau Yufeng",
                "public.brand_company": "Technologie Yufeng",
                "public.ip_privacy_check": "Test de confidentialité et sécurité IP",
                "public.tools_box": "Boîte à outils Yufeng",
                "public.company_signature": "Produit par Quzhou Yufeng Technology Co., Ltd.",
                "public.source_code": "Code source"
            },
            "de": {
                "common.brand_panel": "Yufeng-Panel",
                "public.brand_company": "Yufeng-Technologie",
                "public.ip_privacy_check": "IP-Datenschutz- und Sicherheitsprüfung",
                "public.tools_box": "Yufeng-Toolbox",
                "public.company_signature": "Präsentiert von Quzhou Yufeng Technology Co., Ltd.",
                "public.source_code": "Quellcode"
            },
            "it": {
                "common.brand_panel": "Pannello Yufeng",
                "public.brand_company": "Tecnologia Yufeng",
                "public.ip_privacy_check": "Controllo privacy e sicurezza IP",
                "public.tools_box": "Strumenti Yufeng",
                "public.company_signature": "Prodotto da Quzhou Yufeng Technology Co., Ltd.",
                "public.source_code": "Codice sorgente"
            }
        }

        for lang, expected in langs.items():
            for key, expected_val in expected.items():
                actual_val = backend_t(key, lang=lang)
                self.assertEqual(actual_val, expected_val, f"Mismatch for {key} in {lang}: got {actual_val}, expected {expected_val}")

    def test_layout_footer_rendering(self):
        """测试 layout.html 底部渲染输出的内容"""
        class MockG:
            is_pjax = False
            lang = 'zh-CN'

        self.env.globals['t'] = backend_t
        tpl = self.env.get_template("layout.html")
        rendered = tpl.render(
            g=MockG(),
            session={"login": True, "username": "admin"},
            data={"use_cdn": "no", "ip": "127.0.0.1"},
            config={"version": "1.0.0", "title": "御风面板", "ip": "127.0.0.1"},
            current_lang="zh-CN",
            menu=[]
        )
        self.assertIn("御风面板", rendered)
        self.assertIn("御风科技", rendered)
        self.assertIn("IP隐私安全检测", rendered)
        self.assertIn("御风工具箱", rendered)
        self.assertIn("衢州御风科技有限公司出品", rendered)
        self.assertNotIn(">brand_panel<", rendered)
        self.assertNotIn(">brand_company<", rendered)
        self.assertNotIn(">tools_box<", rendered)
        self.assertNotIn(">ip_privacy_check<", rendered)
        self.assertNotIn(">company_signature<", rendered)

if __name__ == "__main__":
    unittest.main()
