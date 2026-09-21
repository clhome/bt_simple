# -*- coding: utf-8 -*-
"""
自动化测试套件：验证全库插件 k_ 哈希提示清零、Python 语法正确性与 6 国语言包完整适配
"""

import os
import sys
import re
import json
import unittest
import py_compile

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PLUGINS_DIR = os.path.join(BASE_DIR, "plugins")

LANGS = ["zh-CN", "zh-TW", "en", "de", "fr", "it"]

class TestPluginHashReversionAndI18n(unittest.TestCase):

    def test_01_zero_hash_codes_in_plugins(self):
        """测试 1: 断言全量插件 Python 文件中绝对无 k_ 哈希提示码残留"""
        pattern = re.compile(r'["\'](k_[0-9a-fA-F]{6,10})["\']')
        found_matches = []
        
        for root, dirs, files in os.walk(PLUGINS_DIR):
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    rel_path = os.path.relpath(fpath, BASE_DIR).replace("\\", "/")
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fp:
                        for idx, line in enumerate(fp, 1):
                            if pattern.search(line):
                                found_matches.append((rel_path, idx, line.strip()))
                                
        self.assertEqual(
            len(found_matches), 0,
            f"Expected 0 k_ hash codes in plugins, but found {len(found_matches)}: {found_matches[:5]}"
        )

    def test_02_all_plugin_python_syntax(self):
        """测试 2: 断言所有插件 Python 文件均能成功编译，零语法错误"""
        compile_errors = []
        
        for root, dirs, files in os.walk(PLUGINS_DIR):
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    rel_path = os.path.relpath(fpath, BASE_DIR).replace("\\", "/")
                    try:
                        py_compile.compile(fpath, doraise=True)
                    except Exception as e:
                        compile_errors.append((rel_path, str(e)))
                        
        self.assertEqual(
            len(compile_errors), 0,
            f"Expected 0 Python compile errors, but found {len(compile_errors)}: {compile_errors[:5]}"
        )

    def test_03_plugin_lang_files_alignment(self):
        """测试 3: 断言所有 38 个插件的 6 种语言包 Key 集合严格 100% 对齐"""
        plugins = [d for d in os.listdir(PLUGINS_DIR) if os.path.isdir(os.path.join(PLUGINS_DIR, d))]
        self.assertGreaterEqual(len(plugins), 34, "Plugins count should be >= 34")
        
        misaligned = []
        
        for p in plugins:
            lang_dir = os.path.join(PLUGINS_DIR, p, "lang")
            if not os.path.exists(lang_dir):
                continue
                
            zh_cn_path = os.path.join(lang_dir, "zh-CN.json")
            if not os.path.exists(zh_cn_path):
                misaligned.append(f"{p}: missing zh-CN.json")
                continue
                
            with open(zh_cn_path, "r", encoding="utf-8") as f:
                cn_keys = set(json.load(f).keys())
                
            for lg in ["zh-TW", "en", "de", "fr", "it"]:
                lpath = os.path.join(lang_dir, f"{lg}.json")
                if not os.path.exists(lpath):
                    misaligned.append(f"{p}: missing {lg}.json")
                    continue
                with open(lpath, "r", encoding="utf-8") as f:
                    other_keys = set(json.load(f).keys())
                diff = cn_keys.symmetric_difference(other_keys)
                if diff:
                    misaligned.append(f"{p}: {lg}.json not aligned with zh-CN.json (diff: {len(diff)} keys)")
                    
        self.assertEqual(len(misaligned), 0, f"Language misalignment detected: {misaligned[:5]}")

    def test_04_core_plugin_returned_phrases_translation(self):
        """测试 4: 模拟前端 pt 翻译，验证核心插件返回文案在 6 种语言下均能正确翻译"""
        # 测试用例：(插件名, 中文短语, 预期非中文翻译关键词)
        test_cases = [
            ("linux_sys_opt", "全平台内核优化配置已成功生效！", "kernel"),
            ("docker", "导入镜像文件成功!", "image"),
            ("mysql", "存储目录迁移成功!", "migrat"),
            ("postgresql", "切换成功!", "switch"),
            ("redis", "设置成功", "success"),
            ("yufeng_systemd", "操作成功", "success")
        ]
        
        for plugin, phrase, en_keyword in test_cases:
            lang_dir = os.path.join(PLUGINS_DIR, plugin, "lang")
            
            for lg in LANGS:
                lpath = os.path.join(lang_dir, f"{lg}.json")
                self.assertTrue(os.path.exists(lpath), f"{lpath} must exist")
                with open(lpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                self.assertIn(phrase, data, f"Phrase '{phrase}' must be present in {plugin} {lg}.json")
                translated = data[phrase]
                self.assertTrue(bool(translated), f"Translation for '{phrase}' in {lg} must not be empty")
                
                if lg == "en":
                    self.assertIn(en_keyword.lower(), translated.lower(), f"English translation '{translated}' should contain '{en_keyword}'")
                elif lg in ["de", "fr", "it"]:
                    # 确保外语不含未翻译的中文
                    has_zh = bool(re.search(r'[\u4e00-\u9fa5]', translated))
                    self.assertFalse(has_zh, f"Translation in {lg} should not contain Chinese: '{translated}'")

    def test_05_frontend_index_html_layer_msg_pt_wrapper(self):
        """测试 5: 验证 linux_sys_opt/index.html 中弹窗已全面接入 pt(...) 国际化"""
        html_path = os.path.join(PLUGINS_DIR, "linux_sys_opt", "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # 确保不存在未包裹的 layer.msg(rdata.msg) 或 layer.msg(resp.msg)
        self.assertNotIn("layer.msg(rdata.msg", content)
        self.assertNotIn("layer.msg(resp.msg", content)
        # 确保正确使用 pt
        self.assertIn("layer.msg(pt(rdata.msg)", content)
        self.assertIn("layer.msg(pt(resp.msg)", content)

if __name__ == "__main__":
    unittest.main()
