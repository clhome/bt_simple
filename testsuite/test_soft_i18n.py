# -*- coding: utf-8 -*-
"""
自动化测试软件管理模块多语言、菜单及操作按钮
"""

import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "web"))

from core.i18n import t as backend_t

# 进程级隔离：本模块的 test_plugin_py_type_keys 会 `from utils.plugin import plugin`，
# 而 utils.plugin 在**导入期**就会打开 <panelDir>/data/panel.db。
# F: 盘上 sqlite3 的 close() 单次要 30~60s，退出时 atexit 逐个关连接。
# 见 testsuite.md §5.7 / §5.9。
from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('soft_i18n')

class TestSoftI18n(unittest.TestCase):
    def test_left_menu_software_all_languages(self):
        """测试 6 国语言包中左侧菜单及 soft 相关翻译简短不折行"""
        expected = {
            "zh-CN": "软件",
            "zh-TW": "軟體",
            "en": "Software",
            "fr": "Logiciels",
            "de": "Software",
            "it": "Software"
        }
        for lang, exp in expected.items():
            self.assertEqual(backend_t("menu.memuAsoft", lang=lang), exp)
            self.assertEqual(backend_t("menu.M9", lang=lang), exp)
            self.assertEqual(backend_t("menu.soft", lang=lang), exp)

    def test_action_buttons_all_languages(self):
        """测试 6 国语言包中 install, uninstall, set, update 按钮纯净无 quotes"""
        langs = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]
        keys = ["public.install", "public.uninstall", "public.set", "public.update"]
        for lang in langs:
            for k in keys:
                val = backend_t(k, lang=lang)
                self.assertIsNotNone(val)
                self.assertNotIn('"', val)
                self.assertNotIn("'", val)
                self.assertNotIn(">", val)
                self.assertNotIn("<", val)
                self.assertNotEqual(val, k)

    def test_english_and_traditional_action_values(self):
        """测试英文与繁体中文关键操作词"""
        self.assertEqual(backend_t("public.install", lang="en"), "Install")
        self.assertEqual(backend_t("public.uninstall", lang="en"), "Uninstall")
        self.assertEqual(backend_t("public.set", lang="en"), "Settings")
        self.assertEqual(backend_t("public.update", lang="en"), "Update")

        self.assertEqual(backend_t("public.install", lang="zh-TW"), "安裝")
        self.assertEqual(backend_t("public.uninstall", lang="zh-TW"), "解除安裝")
        self.assertEqual(backend_t("public.set", lang="zh-TW"), "設定")

    def test_soft_category_types_all_languages(self):
        """测试 6 国语言包中软件分类标签全部正确适配"""
        expected_types = {
            "zh-CN": {
                "soft.type_all": "全部",
                "soft.type_installed": "已安装",
                "soft.type_runtime": "运行环境",
                "soft.type_database": "数据库",
                "soft.type_system_tools": "系统工具",
                "soft.type_other_plugins": "其他插件",
                "soft.type_php": "PHP"
            },
            "zh-TW": {
                "soft.type_all": "全部",
                "soft.type_installed": "已安裝",
                "soft.type_runtime": "運行環境",
                "soft.type_database": "資料庫",
                "soft.type_system_tools": "系統工具",
                "soft.type_other_plugins": "其他外掛",
                "soft.type_php": "PHP"
            },
            "en": {
                "soft.type_all": "All",
                "soft.type_installed": "Installed",
                "soft.type_runtime": "Runtime",
                "soft.type_database": "Database",
                "soft.type_system_tools": "System Tools",
                "soft.type_other_plugins": "Other Plugins",
                "soft.type_php": "PHP"
            },
            "fr": {
                "soft.type_all": "Tout",
                "soft.type_installed": "Installé",
                "soft.type_runtime": "Environnement d'exécution",
                "soft.type_database": "Base de données",
                "soft.type_system_tools": "Outils système",
                "soft.type_other_plugins": "Autres plugins",
                "soft.type_php": "PHP"
            },
            "de": {
                "soft.type_all": "Alle",
                "soft.type_installed": "Installiert",
                "soft.type_runtime": "Laufzeitumgebung",
                "soft.type_database": "Datenbank",
                "soft.type_system_tools": "Systemwerkzeuge",
                "soft.type_other_plugins": "Andere Plugins",
                "soft.type_php": "PHP"
            },
            "it": {
                "soft.type_all": "Tutti",
                "soft.type_installed": "Installato",
                "soft.type_runtime": "Ambiente di runtime",
                "soft.type_database": "Database",
                "soft.type_system_tools": "Strumenti di sistema",
                "soft.type_other_plugins": "Altri plugin",
                "soft.type_php": "PHP"
            }
        }
        for lang, key_map in expected_types.items():
            for key, exp_val in key_map.items():
                val = backend_t(key, lang=lang)
                self.assertEqual(val, exp_val, f"Failed for {lang} - {key}: expected {exp_val}, got {val}")

    def test_plugin_py_type_keys(self):
        """测试 plugin.py 中 def_plugin_type 的 key 配置与多语言转换"""
        from utils.plugin import plugin
        types = plugin.def_plugin_type
        self.assertGreater(len(types), 0)
        for item in types:
            self.assertIn("key", item)
            self.assertTrue(item["key"].startswith("soft.type_"))
            # 测试中英翻译均不为空
            cn_val = backend_t(item["key"], lang="zh-CN")
            en_val = backend_t(item["key"], lang="en")
            self.assertNotEqual(cn_val, item["key"])
            self.assertNotEqual(en_val, item["key"])

    def test_page_py_i18n(self):
        """测试 page.py 分页支持多语言"""
        from utils.page import Page
        page_info = {
            'count': 15,
            'row': 10,
            'p': 1,
            'return_js': 'getSList',
            'uri': ''
        }
        # 英文测试
        from core.i18n import _LANG_DIR
        try:
            from flask import g, Flask
            app = Flask(__name__)
            with app.test_request_context():
                g.lang = 'en'
                p_en = Page()
                html_en = p_en.GetPage(page_info)
                self.assertIn("Total", html_en)
                self.assertIn("records", html_en)
                self.assertIn("Next Page", html_en)
                self.assertNotIn("共", html_en)
                self.assertNotIn("条数据", html_en)

                g.lang = 'zh-CN'
                p_cn = Page()
                html_cn = p_cn.GetPage(page_info)
                self.assertIn("共", html_cn)
                self.assertIn("条数据", html_cn)
                self.assertIn("下一页", html_cn)
        except ImportError:
            pass

if __name__ == "__main__":
    unittest.main()
