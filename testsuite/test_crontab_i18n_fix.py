# -*- coding: utf-8 -*-
"""
计划任务周期渲染与 Day Restriction 国际化专项测试套件
"""
import os
import sys
import json
import re
import unittest
import subprocess
import py_compile

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LANG_DIR = os.path.join(ROOT_DIR, "web", "static", "language")

class TestCrontabI18nFix(unittest.TestCase):

    def contains_chinese(self, text):
        if not isinstance(text, str):
            return False
        return bool(re.search(r'[\u4e00-\u9fff]', text))

    def test_01_language_dictionary_completeness(self):
        """测试 6 种语言包中 crontab 日期限制与周期词条的完整性与纯净度"""
        langs = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]
        required_keys = ["day_limit", "day_none", "day_stock", "day_workday", "day_holiday"]
        week_keys = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

        for lang in langs:
            # 1. 验证 template.json
            tmpl_path = os.path.join(LANG_DIR, lang, "template.json")
            self.assertTrue(os.path.exists(tmpl_path), f"Missing {lang}/template.json")
            with open(tmpl_path, "r", encoding="utf-8") as f:
                tmpl_data = json.load(f)
            
            crontab_tmpl = tmpl_data.get("crontab", {})
            for key in required_keys:
                self.assertIn(key, crontab_tmpl, f"{lang}/template.json missing crontab.{key}")
                val = crontab_tmpl[key]
                self.assertTrue(len(val.strip()) > 0, f"{lang}/template.json crontab.{key} is empty")
                if lang in ["en", "fr", "de", "it"]:
                    self.assertFalse(self.contains_chinese(val), f"{lang}/template.json crontab.{key} contains Chinese: {val}")

            for key in week_keys:
                self.assertIn(key, crontab_tmpl, f"{lang}/template.json missing crontab.{key}")
                val = crontab_tmpl[key]
                if lang in ["en", "fr", "de", "it"]:
                    self.assertFalse(self.contains_chinese(val), f"{lang}/template.json crontab.{key} contains Chinese: {val}")

            # 2. 验证 lan.js
            lan_path = os.path.join(LANG_DIR, lang, "lan.js")
            self.assertTrue(os.path.exists(lan_path), f"Missing {lang}/lan.js")
            with open(lan_path, "r", encoding="utf-8") as f:
                lan_text = f.read()

            for key in required_keys:
                self.assertIn(f'"{key}"', lan_text, f"{lang}/lan.js missing key {key}")

    def test_02_javascript_dom_generation_and_balance(self):
        """测试在 Node 环境中运行 crontab.js 周期渲染与标签平衡闭合"""
        test_script = os.path.join(ROOT_DIR, "testsuite", "simulate_crontab.js")
        self.assertTrue(os.path.exists(test_script))

        res = subprocess.run(["node", test_script], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0, f"simulate_crontab.js execution failed: {res.stderr}")
        output = res.stdout

        # 检查是否包含英文字段
        self.assertIn("Monday", output)
        self.assertIn("Hours", output)
        self.assertIn("Minutes", output)
        self.assertIn("Start time", output)
        self.assertIn("End time", output)
        self.assertIn('"Stock Trading Day"', output)
        self.assertIn('"Workday"', output)
        self.assertIn('"Holiday"', output)

        # 检查是否无中文字段（在 EN 渲染段中）
        self.assertNotIn("周一", output)
        self.assertNotIn("小时", output)
        self.assertNotIn("分钟", output)
        self.assertNotIn("开始时间", output)
        self.assertNotIn("结束时间", output)

        # 检查 HTML 标签是否平衡闭合
        for tag in ["div", "button", "b", "span", "ul", "li", "label"]:
            open_count = len(re.findall(rf'<{tag}[\s>]', output))
            close_count = len(re.findall(rf'</{tag}>', output))
            self.assertEqual(open_count, close_count, f"Unbalanced tag <{tag}>: {open_count} open vs {close_count} close")

    def test_03_python_files_cleanliness(self):
        """测试 Python 文件语法有效性且无截断死代码"""
        target_py = os.path.join(ROOT_DIR, "web", "admin", "crontab", "__init__.py")
        try:
            py_compile.compile(target_py, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"Python compile error in {target_py}: {e}")

        with open(target_py, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 确保只包含一个 "# coding:utf-8"
        self.assertEqual(content.count("# coding:utf-8"), 1, "Duplicate header or truncated code still exists in __init__.py")
        # 确保 add 函数只定义了一次
        self.assertEqual(content.count("def add():"), 1, "Duplicate add() function in __init__.py")

if __name__ == '__main__':
    unittest.main()
