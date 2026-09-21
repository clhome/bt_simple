# -*- coding: utf-8 -*-
"""
多语言（除简体中文与繁体中文外的所有语言 en, fr, de, it）全量完整度与质量自动化测试套件
验证项目：
1. 语言包文件完整性与键值数量严格对齐 (public.json: 521, log.json: 120, template.json: 30 sections)
2. 外语包中文字符残留数量严格为 0 (0 Chinese characters)
3. 杜绝膨胀：lan.js 体积健康恢复 (< 500KB，杜绝 72MB 膨胀)
4. lan.js JavaScript 语法有效性
5. 换行符规范为 LF，编码为 UTF-8 无 BOM
"""

import unittest
import os
import json
import re
import subprocess

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANG_DIR = os.path.join(ROOT_DIR, "web", "static", "language")
FOREIGN_LANGS = ["en", "fr", "de", "it"]
ALL_LANGS = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]
ZH_REGEX = re.compile(r'[\u4e00-\u9fa5]')

class TestAllForeignLanguagesComplete(unittest.TestCase):

    def test_file_existence_and_encoding(self):
        """测试各语言目录及核心语言文件存在性与 LF 格式"""
        for lang in FOREIGN_LANGS:
            lang_dir = os.path.join(LANG_DIR, lang)
            self.assertTrue(os.path.isdir(lang_dir), f"语言目录缺失: {lang}")
            for fn in ["public.json", "template.json", "log.json", "lan.js"]:
                fp = os.path.join(lang_dir, fn)
                self.assertTrue(os.path.isfile(fp), f"文件缺失: {fp}")
                with open(fp, "rb") as f:
                    content = f.read()
                    self.assertFalse(content.startswith(b'\xef\xbb\xbf'), f"文件包含 BOM 头: {fp}")
                    # 检查没有孤立的 CR
                    self.assertNotIn(b'\r\n', content, f"文件换行符应为 LF，不应包含 CRLF: {fp}")

    def test_zero_chinese_in_foreign_languages(self):
        """断言除简体/繁体中文之外的所有外语包，中文字符残留数 100% 为 0"""
        for lang in FOREIGN_LANGS:
            lang_dir = os.path.join(LANG_DIR, lang)
            
            # 1. public.json
            with open(os.path.join(lang_dir, "public.json"), "r", encoding="utf-8") as f:
                pub = json.load(f)
            zh_in_pub = [f"{k}: {v}" for k, v in pub.items() if isinstance(v, str) and ZH_REGEX.search(v)]
            self.assertEqual(len(zh_in_pub), 0, f"[{lang}] public.json 仍包含中文: {zh_in_pub[:3]}")

            # 2. template.json
            with open(os.path.join(lang_dir, "template.json"), "r", encoding="utf-8") as f:
                tmpl = json.load(f)
            zh_in_tmpl = []
            for sec, items in tmpl.items():
                if isinstance(items, dict):
                    for k, v in items.items():
                        if isinstance(v, str) and ZH_REGEX.search(v):
                            zh_in_tmpl.append(f"{sec}.{k}: {v}")
            self.assertEqual(len(zh_in_tmpl), 0, f"[{lang}] template.json 仍包含中文: {zh_in_tmpl[:3]}")

            # 3. log.json
            with open(os.path.join(lang_dir, "log.json"), "r", encoding="utf-8") as f:
                log_data = json.load(f)
            zh_in_log = [f"{k}: {v}" for k, v in log_data.items() if isinstance(v, str) and ZH_REGEX.search(v)]
            self.assertEqual(len(zh_in_log), 0, f"[{lang}] log.json 仍包含中文: {zh_in_log[:3]}")

            # 4. lan.js
            with open(os.path.join(lang_dir, "lan.js"), "r", encoding="utf-8") as f:
                lan_text = f.read()
            self.assertFalse(ZH_REGEX.search(lan_text), f"[{lang}] lan.js 仍包含中文内容")

    def test_key_counts_alignment(self):
        """断言外语包键值数量与中文源 100% 对齐"""
        with open(os.path.join(LANG_DIR, "zh-CN", "public.json"), "r", encoding="utf-8") as f:
            zh_pub = json.load(f)
        with open(os.path.join(LANG_DIR, "zh-CN", "template.json"), "r", encoding="utf-8") as f:
            zh_tmpl = json.load(f)
        with open(os.path.join(LANG_DIR, "zh-CN", "log.json"), "r", encoding="utf-8") as f:
            zh_log = json.load(f)

        for lang in FOREIGN_LANGS:
            lang_dir = os.path.join(LANG_DIR, lang)
            with open(os.path.join(lang_dir, "public.json"), "r", encoding="utf-8") as f:
                pub = json.load(f)
            self.assertEqual(len(pub), len(zh_pub), f"[{lang}] public.json 键数不匹配")

            with open(os.path.join(lang_dir, "template.json"), "r", encoding="utf-8") as f:
                tmpl = json.load(f)
            self.assertEqual(len(tmpl), len(zh_tmpl), f"[{lang}] template.json section 数不匹配")

            with open(os.path.join(lang_dir, "log.json"), "r", encoding="utf-8") as f:
                log_data = json.load(f)
            self.assertEqual(len(log_data), len(zh_log), f"[{lang}] log.json 键数不匹配")

    def test_lan_js_health_and_syntax(self):
        """断言所有语言包 lan.js 杜绝膨胀（恢复正常体积 < 500KB）且通过 JS 语法解析"""
        for lang in ALL_LANGS:
            lan_file = os.path.join(LANG_DIR, lang, "lan.js")
            file_size = os.path.getsize(lan_file)
            self.assertLess(file_size, 500 * 1024, f"[{lang}] lan.js 存在异常膨胀: {file_size} 字节")
            self.assertGreater(file_size, 50 * 1024, f"[{lang}] lan.js 体积过小可能内容不全: {file_size} 字节")

            # 使用 Node.js 测试语法有效性
            cmd = ["node", "-e", f"const fs = require('fs'); const code = fs.readFileSync({json.dumps(lan_file)}, 'utf-8'); const fn = new Function(code + '; return lan;'); const obj = fn(); if (!obj || typeof obj !== 'object') process.exit(1);"]
            p = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, f"[{lang}] lan.js JavaScript 语法解析失败: {p.stderr}")

    def test_public_auto_str_translated(self):
        """专门断言 public.json 中 public_auto_str 前缀全部翻译且无中文"""
        for lang in FOREIGN_LANGS:
            pub_file = os.path.join(LANG_DIR, lang, "public.json")
            with open(pub_file, "r", encoding="utf-8") as f:
                pub = json.load(f)
            auto_keys = [k for k in pub if k.startswith("public_auto_str_")]
            self.assertGreater(len(auto_keys), 100, f"[{lang}] public_auto_str 系列键数量不足")
            for k in auto_keys:
                v = pub[k]
                if isinstance(v, str):
                    self.assertFalse(ZH_REGEX.search(v), f"[{lang}] {k} 包含中文残留: {v}")
                elif isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        if isinstance(sub_v, str):
                            self.assertFalse(ZH_REGEX.search(sub_v), f"[{lang}] {k}.{sub_k} 包含中文残留: {sub_v}")


if __name__ == "__main__":
    unittest.main()
