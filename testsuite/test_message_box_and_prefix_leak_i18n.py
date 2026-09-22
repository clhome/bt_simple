# -*- coding: utf-8 -*-
"""
自动化测试：消息盒子多语言、系统监控与全局前缀泄露防范
验证 6 国语言包完整性、i18n.js 优雅降级以及 public.js 消息盒子调用规范
"""

import os
import sys
import unittest
import json
import re
import subprocess

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LANG_DIR = os.path.join(ROOT_DIR, "web", "static", "language")
APP_DIR = os.path.join(ROOT_DIR, "web", "static", "app")

LANG_CODES = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]

REQUIRED_MSG_BOX_KEYS = [
    "message_box", "task_list", "message_list", "execution_log",
    "memory_1", "uplink", "downstream", "if_task_has_not",
    "there_are_currently_no", "retrieving_logs", "completed", "done",
    "time_taken", "processing_1", "waiting_1", "installing_1", "installing_2",
    "scanning", "downloading", "scan", "close", "del",
    "task_name", "task_time", "task_tip_read", "task_tip_all"
]

class TestMessageBoxAndPrefixLeakI18n(unittest.TestCase):

    def test_01_language_packs_contain_all_message_box_keys(self):
        """测试 6 国语言包的 public.json 和 lan.js 中必须完整包含所有消息盒子与系统监控词条"""
        for code in LANG_CODES:
            pub_path = os.path.join(LANG_DIR, code, "public.json")
            lan_path = os.path.join(LANG_DIR, code, "lan.js")
            
            self.assertTrue(os.path.exists(pub_path), f"Missing public.json for {code}")
            self.assertTrue(os.path.exists(lan_path), f"Missing lan.js for {code}")
            
            with open(pub_path, "r", encoding="utf-8") as f:
                pub_data = json.load(f)
            with open(lan_path, "r", encoding="utf-8") as f:
                lan_content = f.read()
                
            self.assertIn('"public":', lan_content, f"Missing 'public' section in {code}/lan.js")
            
            for k in REQUIRED_MSG_BOX_KEYS:
                self.assertIn(k, pub_data, f"Key '{k}' missing in {code}/public.json")
                self.assertTrue(bool(pub_data[k]), f"Key '{k}' is empty in {code}/public.json")
                self.assertNotIn("public.", pub_data[k], f"Value for '{k}' in {code}/public.json contains leaked prefix")
                self.assertIn(f'"{k}"', lan_content, f"Key '{k}' missing in {code}/lan.js")

    def test_02_specific_language_translations_accuracy(self):
        """测试特定语言下（中文、英文、繁体）消息盒子词条翻译准确性"""
        with open(os.path.join(LANG_DIR, "zh-CN", "public.json"), "r", encoding="utf-8") as f:
            zh_pub = json.load(f)
        self.assertEqual(zh_pub["message_box"], "消息盒子")
        self.assertEqual(zh_pub["task_list"], "任务列表")
        self.assertEqual(zh_pub["message_list"], "消息列表")
        self.assertEqual(zh_pub["memory_1"], "内存:")
        self.assertEqual(zh_pub["uplink"], "上行:")
        self.assertEqual(zh_pub["downstream"], "下行:")

        with open(os.path.join(LANG_DIR, "en", "public.json"), "r", encoding="utf-8") as f:
            en_pub = json.load(f)
        self.assertEqual(en_pub["message_box"], "Message Box")
        self.assertEqual(en_pub["task_list"], "Task List")
        self.assertEqual(en_pub["message_list"], "Message List")
        self.assertEqual(en_pub["memory_1"], "Memory:")
        self.assertEqual(en_pub["uplink"], "Up:")
        self.assertEqual(en_pub["downstream"], "Down:")
        self.assertEqual(en_pub["there_are_currently_no"], "There are currently no tasks!")

        with open(os.path.join(LANG_DIR, "zh-TW", "public.json"), "r", encoding="utf-8") as f:
            tw_pub = json.load(f)
        self.assertEqual(tw_pub["task_list"], "任務列表")
        self.assertEqual(tw_pub["memory_1"], "記憶體:")

    def test_03_i18n_js_fallback_prevents_prefix_leak(self):
        """测试 i18n.js 在 key 不存在时绝不泄露带点号的前缀代码（支持 || 语法短路回退）"""
        i18n_path = os.path.join(APP_DIR, "i18n.js")
        with open(i18n_path, "r", encoding="utf-8") as f:
            i18n_code = f.read()

        js_runner = f"""
        global.window = {{ location: {{ search: '' }}, navigator: {{ languages: ['zh-CN'] }} }};
        global.document = {{ cookie: '', readyState: 'complete', querySelectorAll: function(){{ return []; }}, addEventListener: function(){{}} }};
        global.navigator = global.window.navigator;
        global.window.lan = {{ public: {{ message_box: '消息盒子', memory_1: '内存:' }} }};
        var window = global.window;
        var document = global.document;
        var navigator = global.navigator;
        var lan = global.window.lan;
        {i18n_code}
        var t = window.t;
        
        var results = {{
            val1: t('public.message_box'),
            val2: t('public.memory_1'),
            non_existent: t('public.non_existent_metric'),
            short_circuit: t('public.non_existent_metric') || '默认文本',
            fallback_param: t('public.non_existent_metric', '参数默认文本')
        }};
        console.log(JSON.stringify(results));
        """
        
        res = subprocess.run(["node", "-e", js_runner], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0, f"Node.js error: {res.stderr}")
        data = json.loads(res.stdout.strip())
        
        # 1. 存在对应 key 时正常返回
        self.assertEqual(data["val1"], "消息盒子")
        self.assertEqual(data["val2"], "内存:")

        # 2. 不存在对应 key 时，绝不能返回 "public.non_existent_xxx"，必须返回空字符串以支持 ||
        self.assertNotIn("public.", data["non_existent"])
        self.assertEqual(data["non_existent"], "")

        # 3. 测试短路语法
        self.assertEqual(data["short_circuit"], "默认文本")

        # 4. 测试传参 fallback 语法
        self.assertEqual(data["fallback_param"], "参数默认文本")


    def test_04_public_js_syntax_and_no_bt_prefix(self):
        """测试 public.js 中已移除所有未翻译的 bt.* 前缀，并保持语法合法"""
        public_js_path = os.path.join(APP_DIR, "public.js")
        with open(public_js_path, "r", encoding="utf-8") as f:
            public_js_content = f.read()

        # 验证不再包含 t('bt.xxx')
        bt_matches = re.findall(r"""t\(['"]bt\.[^'"]+['"]\)""", public_js_content)
        self.assertEqual(len(bt_matches), 0, f"Found legacy bt.* calls in public.js: {bt_matches}")

        # 验证 messageBox 标题与组件调用正常
        self.assertIn("t('public.message_box'", public_js_content)
        self.assertIn("t('public.task_list'", public_js_content)
        self.assertIn("t('public.message_list'", public_js_content)
        self.assertIn("t('public.execution_log'", public_js_content)
        self.assertIn("t('public.memory_1'", public_js_content)
        self.assertIn("t('public.uplink'", public_js_content)
        self.assertIn("t('public.downstream'", public_js_content)

if __name__ == "__main__":
    unittest.main()
