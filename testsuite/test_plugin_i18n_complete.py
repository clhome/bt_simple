# -*- coding: utf-8 -*-
"""
插件多语言翻译完整性与质量专项自动化测试套件 (test_plugin_i18n_complete.py)
"""

import unittest
import os
import json
import re

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PLUGINS_DIR = os.path.join(ROOT_DIR, "plugins")
LANGS = ["zh-CN", "zh-TW", "en", "de", "fr", "it"]

class TestPluginI18nComplete(unittest.TestCase):

    def setUp(self):
        self.plugins = sorted([
            d for d in os.listdir(PLUGINS_DIR)
            if os.path.isdir(os.path.join(PLUGINS_DIR, d))
            and os.path.isdir(os.path.join(PLUGINS_DIR, d, "lang"))
        ])

    def test_plugins_count(self):
        """验证全部 38 个插件存在且拥有 lang 目录"""
        self.assertEqual(len(self.plugins), 38, f"预期 38 个插件，实际发现 {len(self.plugins)} 个")

    def test_all_languages_files_exist_and_valid_json(self):
        """验证 38 个插件 × 6 种语言共 228 个文件全部存在且能正确解析为合法 JSON"""
        for p in self.plugins:
            lang_dir = os.path.join(PLUGINS_DIR, p, "lang")
            for lang in LANGS:
                fpath = os.path.join(lang_dir, f"{lang}.json")
                self.assertTrue(os.path.exists(fpath), f"插件 {p} 缺少语言文件: {lang}.json")
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.assertIsInstance(data, dict, f"{fpath} 根结构必须是字典")
                    self.assertGreater(len(data), 0, f"{fpath} 词条不能为空")

    def test_key_consistency_across_all_languages(self):
        """验证每个插件的 6 种语言文件的 Key 集合 100% 对齐"""
        for p in self.plugins:
            lang_dir = os.path.join(PLUGINS_DIR, p, "lang")
            with open(os.path.join(lang_dir, "zh-CN.json"), "r", encoding="utf-8") as f:
                base_keys = set(json.load(f).keys())
            
            for lang in ["zh-TW", "en", "de", "fr", "it"]:
                with open(os.path.join(lang_dir, f"{lang}.json"), "r", encoding="utf-8") as f:
                    target_keys = set(json.load(f).keys())
                self.assertEqual(base_keys, target_keys, f"插件 {p} 在 {lang}.json 中的 key 集合与 zh-CN.json 不一致")

    def test_no_code_pollution_in_keys_and_values(self):
        """验证词条中无 JavaScript 函数体代码污染与样式块污染"""
        code_regex = re.compile(r'function\s+\w+\s*\(|\$\.(post|get|ajax)\s*\(|pluginService\s*\(|layer\.(msg|open)\s*\(')
        for p in self.plugins:
            lang_dir = os.path.join(PLUGINS_DIR, p, "lang")
            for lang in LANGS:
                with open(os.path.join(lang_dir, f"{lang}.json"), "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    self.assertFalse(code_regex.search(k), f"[{p}/{lang}.json] key 包含代码污染: {k[:50]}")
                    self.assertFalse(code_regex.search(v), f"[{p}/{lang}.json] value 包含代码污染: {v[:50]}")

    def test_foreign_languages_have_no_chinese_residuals(self):
        """验证外语 (en, de, fr, it) 文件中没有残留的未翻译中文"""
        cn_regex = re.compile(r'[\u4e00-\u9fa5]')
        for p in self.plugins:
            lang_dir = os.path.join(PLUGINS_DIR, p, "lang")
            for lang in ["en", "de", "fr", "it"]:
                with open(os.path.join(lang_dir, f"{lang}.json"), "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    if cn_regex.search(k):
                        self.assertFalse(cn_regex.search(v), f"[{p}/{lang}.json] 词条未翻译完全 (key={k}): {v}")

    def test_clean_plugin_specific_translations(self):
        """专项验证用户关注的 clean 插件多语言翻译完整性"""
        clean_dir = os.path.join(PLUGINS_DIR, "clean", "lang")
        with open(os.path.join(clean_dir, "zh-CN.json"), "r", encoding="utf-8") as f:
            zh_cn = json.load(f)
        with open(os.path.join(clean_dir, "zh-TW.json"), "r", encoding="utf-8") as f:
            zh_tw = json.load(f)
        with open(os.path.join(clean_dir, "en.json"), "r", encoding="utf-8") as f:
            en = json.load(f)

        # 确保 clean 插件拥有全部 11 个界面纯净词条，绝不仅剩 1 条
        self.assertGreaterEqual(len(zh_cn), 11)
        self.assertEqual(len(zh_cn), len(zh_tw))
        self.assertEqual(len(zh_cn), len(en))
        
        # 验证繁体与英文翻译准确性
        self.assertEqual(zh_tw["日志清理"], "日誌清理")
        self.assertEqual(zh_tw["手动执行"], "手動執行")
        self.assertEqual(zh_tw["运行日志"], "執行日誌")
        self.assertEqual(en["服务"], "Service")
        self.assertEqual(en["日志清理"], "Log Cleanup")
        self.assertEqual(en["手动执行"], "Manual Run")
        self.assertEqual(en["运行日志"], "Runtime Logs")

if __name__ == "__main__":
    unittest.main()
