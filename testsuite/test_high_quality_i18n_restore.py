# -*- coding: utf-8 -*-
"""
自动化测试：高质量母语国际化恢复验证
验证全套语言包（en, zh-TW, fr, de, it, zh-CN）恢复纯正母语、彻底消除中英夹杂怪胎，且新增词条完整保留
"""

import os
import sys
import unittest
import json
import re

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LANG_DIR = os.path.join(ROOT_DIR, "web", "static", "language")

ALL_LANGS = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]

class TestHighQualityI18nRestore(unittest.TestCase):

    def test_01_english_public_json_is_pure_and_accurate(self):
        """测试 en/public.json 恢复纯正英语，绝无中英夹杂"""
        en_pub_path = os.path.join(LANG_DIR, "en", "public.json")
        self.assertTrue(os.path.exists(en_pub_path), "Missing en/public.json")
        
        with open(en_pub_path, "r", encoding="utf-8") as f:
            en_pub = json.load(f)

        # 1. 验证用户指出的关键错误提示恢复纯正英语
        self.assertEqual(en_pub.get("NAME"), "Linux Control Panel")
        self.assertEqual(en_pub.get("PAGE_ERR_TITLE"), "Access Denied")
        self.assertEqual(en_pub.get("PAGE_ERR_DOMAIN_H1"), "Sorry, you do not have access.")
        self.assertEqual(en_pub.get("PAGE_ERR_DOMAIN_P1"), "Please use the correct domain name to access the site!")
        self.assertEqual(en_pub.get("PAGE_ERR_DOMAIN_P2"), "View authorized domains: cat /www/server/panel/data/domain.conf")
        self.assertEqual(en_pub.get("PAGE_ERR_DOMAIN_P3"), "Disable access restrictions: rm -f /www/server/panel/data/domain.conf")
        self.assertEqual(en_pub.get("PAGE_ERR_IP_H1"), "Sorry, your IP address is not authorized.")
        self.assertEqual(en_pub.get("PAGE_ERR_IP_P1"), "Your current IP address is [{1}]. Please use the correct IP address to access the site!")
        self.assertEqual(en_pub.get("PAGE_ERR_404_TITLE"), "404 Not Found")
        self.assertEqual(en_pub.get("PAGE_ERR_404_H1"), "Sorry, the page does not exist.")
        self.assertEqual(en_pub.get("PAGE_ERR_500_TITLE"), "500 Internal Server Error")
        self.assertEqual(en_pub.get("PAGE_ERR_500_H1"), "Sorry, a program error occurred.")
        self.assertEqual(en_pub.get("PAGE_ERR_HELP"), "Request for Help")
        self.assertEqual(en_pub.get("LOGIN_USER_EMPTY"), "The username or password cannot be blank!")
        self.assertEqual(en_pub.get("ERROR"), "Operation Failed")
        self.assertEqual(en_pub.get("SUCCESS"), "Operation Successful")
        self.assertEqual(en_pub.get("START"), "Start")
        self.assertEqual(en_pub.get("STOP"), "Stop")
        self.assertEqual(en_pub.get("OPEN"), "Open")
        self.assertEqual(en_pub.get("CLOSE"), "Close")

        # 2. 验证新增的消息盒子与监控指标词条无损
        self.assertEqual(en_pub.get("message_box"), "Message Box")
        self.assertEqual(en_pub.get("task_list"), "Task List")
        self.assertEqual(en_pub.get("message_list"), "Message List")
        self.assertEqual(en_pub.get("execution_log"), "Execution Log")
        self.assertEqual(en_pub.get("memory_1"), "Memory:")
        self.assertEqual(en_pub.get("uplink"), "Up:")
        self.assertEqual(en_pub.get("downstream"), "Down:")
        self.assertEqual(en_pub.get("task_name"), "Task Name")

        # 3. 验证关键错误字段绝对不含中文字符
        forbidden_chinese_keys = [
            "PAGE_ERR_TITLE", "PAGE_ERR_DOMAIN_H1", "PAGE_ERR_DOMAIN_P1",
            "PAGE_ERR_DOMAIN_P2", "PAGE_ERR_DOMAIN_P3", "PAGE_ERR_IP_H1",
            "PAGE_ERR_IP_P2", "PAGE_ERR_IP_P3", "PAGE_ERR_404_H1",
            "PAGE_ERR_404_P1", "PAGE_ERR_500_H1", "PAGE_ERR_500_P1",
            "PAGE_ERR_HELP", "ARGS_ERR", "CODE_BOOM", "LOGIN_USER_EMPTY",
            "LOGIN_ERR_LIMIT", "LOGIN_SUCCESS", "OPEN", "CLOSE"
        ]
        for k in forbidden_chinese_keys:
            val = en_pub.get(k, "")
            self.assertFalse(bool(re.search(r'[\u4e00-\u9fa5]', val)), f"Key '{k}' contains Chinese in en/public.json: {val}")

    def test_02_other_languages_authenticity(self):
        """测试法、德、意、繁体在 public.json 中的纯正母语"""
        # 法语
        with open(os.path.join(LANG_DIR, "fr", "public.json"), "r", encoding="utf-8") as f:
            fr_pub = json.load(f)
        self.assertEqual(fr_pub.get("PAGE_ERR_TITLE"), "Accès refusé")
        self.assertEqual(fr_pub.get("message_box"), "Boîte de messages")

        # 德语
        with open(os.path.join(LANG_DIR, "de", "public.json"), "r", encoding="utf-8") as f:
            de_pub = json.load(f)
        self.assertEqual(de_pub.get("PAGE_ERR_TITLE"), "Zugriff verweigert")
        self.assertEqual(de_pub.get("message_box"), "Nachrichtenbox")

        # 意大利语
        with open(os.path.join(LANG_DIR, "it", "public.json"), "r", encoding="utf-8") as f:
            it_pub = json.load(f)
        self.assertEqual(it_pub.get("PAGE_ERR_TITLE"), "Accesso negato")
        self.assertEqual(it_pub.get("message_box"), "Casella messaggi")

        # 繁体中文
        with open(os.path.join(LANG_DIR, "zh-TW", "public.json"), "r", encoding="utf-8") as f:
            tw_pub = json.load(f)
        self.assertIn(tw_pub.get("PAGE_ERR_TITLE"), ["拒絕訪問", "訪問被拒絕", "拒絕存取"])
        self.assertEqual(tw_pub.get("memory_1"), "記憶體:")

    def test_03_all_language_files_lf_and_valid_json_js(self):
        """测试 6 国语言目录下所有 .json 与 .js 文件均使用 LF 换行符且格式合法"""
        for code in ALL_LANGS:
            lang_dir = os.path.join(LANG_DIR, code)
            for fn in ["public.json", "template.json", "log.json", "lan.js"]:
                fp = os.path.join(lang_dir, fn)
                self.assertTrue(os.path.exists(fp), f"Missing {code}/{fn}")
                
                with open(fp, "rb") as f:
                    raw_bytes = f.read()
                self.assertNotIn(b"\r\n", raw_bytes, f"File {code}/{fn} contains CRLF line endings!")
                
                if fn.endswith(".json"):
                    with open(fp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.assertIsInstance(data, dict, f"{code}/{fn} is not a valid JSON dict")

if __name__ == "__main__":
    unittest.main()
