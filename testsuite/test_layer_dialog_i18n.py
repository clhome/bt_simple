# -*- coding: utf-8 -*-
"""
全局 Layer 弹窗及退出登录弹窗多语言自动化测试
"""

import os
import sys
import json
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "web"))

from core.i18n import t as backend_t

class TestLayerDialogI18n(unittest.TestCase):
    def test_dialog_keys_in_all_languages(self):
        """测试 6 国语言包中公共弹窗核心词汇齐备且准确"""
        expected = {
            "zh-CN": {
                "public.confirm": "确定",
                "public.cancel": "取消",
                "public.close": "关闭",
                "public.info": "信息",
                "public.do_you_want_to": "是否要退出御风面板?"
            },
            "zh-TW": {
                "public.confirm": "確定",
                "public.cancel": "取消",
                "public.close": "關閉",
                "public.info": "資訊",
                "public.do_you_want_to": "是否要退出御風面板?"
            },
            "en": {
                "public.confirm": "Confirm",
                "public.cancel": "Cancel",
                "public.close": "Close",
                "public.info": "Info",
                "public.do_you_want_to": "Do you want to exit the Yufeng panel?"
            },
            "fr": {
                "public.confirm": "Confirmer",
                "public.cancel": "Annuler",
                "public.close": "Fermer",
                "public.info": "Information",
                "public.do_you_want_to": "Voulez-vous quitter le panneau Yufeng ?"
            },
            "de": {
                "public.confirm": "Bestätigen",
                "public.cancel": "Abbrechen",
                "public.close": "Schließen",
                "public.info": "Information",
                "public.do_you_want_to": "Möchten Sie das Yufeng-Panel verlassen?"
            },
            "it": {
                "public.confirm": "Conferma",
                "public.cancel": "Annulla",
                "public.close": "Chiudi",
                "public.info": "Informazioni",
                "public.do_you_want_to": "Vuoi uscire dal pannello Yufeng?"
            }
        }
        for lang, items in expected.items():
            for key, exp_val in items.items():
                val = backend_t(key, lang=lang)
                self.assertEqual(val, exp_val, f"Failed for {lang} - {key}: expected '{exp_val}', got '{val}'")

    def test_public_js_signout_robustness(self):
        """测试 public.js 中 #signout 退出逻辑健壮且无空字符串短路隐患"""
        pub_path = os.path.join(ROOT_DIR, "web", "static", "app", "public.js")
        with open(pub_path, "r", encoding="utf-8") as f:
            code = f.read()
        
        # 确保不存在会导致短路为 "" 的旧语法
        self.assertNotIn("lan && lan.public && t('public.do_you_want_to') || \"\"", code)
        
        # 确保使用 t('public.do_you_want_to')
        self.assertIn("t('public.do_you_want_to'", code)
        self.assertIn("title: infoTitle", code)
        self.assertIn("btn: [confirmBtn, cancelBtn]", code)

    def test_public_js_layer_interceptor_exists(self):
        """测试 public.js 中全局 Layer 拦截多语言增强函数存在且完整"""
        pub_path = os.path.join(ROOT_DIR, "web", "static", "app", "public.js")
        with open(pub_path, "r", encoding="utf-8") as f:
            code = f.read()
        
        self.assertIn("function initLayerI18n()", code)
        self.assertIn("origConfirm.call(this", code)
        self.assertIn("origAlert.call(this", code)
        self.assertIn("origOpen.call(this", code)
        self.assertIn("initLayerI18n();", code)

    def test_i18n_js_fallback_and_namespace_safety(self):
        """测试 i18n.js 中包含弹窗回退词典与 lan.public 安全声明"""
        i18n_path = os.path.join(ROOT_DIR, "web", "static", "app", "i18n.js")
        with open(i18n_path, "r", encoding="utf-8") as f:
            code = f.read()
        
        self.assertIn("'confirm': '确定'", code)
        self.assertIn("'cancel': '取消'", code)
        self.assertIn("'info': '信息'", code)
        self.assertIn("'do_you_want_to': '是否要退出御风面板?'", code)
        self.assertIn("window.lan.public = window.lan.public || {};", code)

if __name__ == "__main__":
    unittest.main()
