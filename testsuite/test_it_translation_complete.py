# -*- coding: utf-8 -*-
"""
专项自动化测试套件: 验证 web/static/language/it 意大利语翻译完整性与语法有效性
1. 验证全部 13 个文件 0 中文字符残留；
2. 验证 Node.js 解析 it/lan.js 零语法错误且核心属性完备；
3. 验证全部 12 个 .json 文件均为合法合规的标准 JSON；
4. 验证全部 13 个文件均为 UTF-8 无 BOM 且 LF 换行。
"""

import os
import sys
import json
import re
import subprocess
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IT_DIR = os.path.join(ROOT_DIR, "web", "static", "language", "it")

EXPECTED_FILES = [
    "lan.js",
    "log.json",
    "public.json",
    "template.crontab.json",
    "template.files.json",
    "template.index.json",
    "template.json",
    "template.logs.json",
    "template.monitor.json",
    "template.security.json",
    "template.setting.json",
    "template.site.json",
    "template.soft.json"
]

ZH_PATTERN = re.compile(r'[\u4e00-\u9fa5]')

class TestItalianTranslationComplete(unittest.TestCase):

    def test_01_all_expected_files_exist(self):
        """验证全部 13 个语言包文件均存在"""
        for fname in EXPECTED_FILES:
            fpath = os.path.join(IT_DIR, fname)
            self.assertTrue(os.path.isfile(fpath), f"缺少文件: {fname}")
            self.assertGreater(os.path.getsize(fpath), 0, f"文件为空: {fname}")

    def test_02_zero_chinese_characters(self):
        """验证全部 13 个文件中文字符严格为 0"""
        for fname in EXPECTED_FILES:
            fpath = os.path.join(IT_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            matches = ZH_PATTERN.findall(content)
            self.assertEqual(len(matches), 0, f"文件 {fname} 仍包含 {len(matches)} 个中文字符，示例: {matches[:10]}")

    def test_03_json_files_syntax_and_validity(self):
        """验证所有 12 个 .json 文件均为有效 JSON 且顶层包含键"""
        json_files = [f for f in EXPECTED_FILES if f.endswith(".json")]
        self.assertEqual(len(json_files), 12)
        for fname in json_files:
            fpath = os.path.join(IT_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIsInstance(data, dict, f"{fname} 顶层不是字典")
            self.assertGreater(len(data), 0, f"{fname} 顶层键为空")

    def test_04_lan_js_syntax_via_nodejs(self):
        """通过 Node.js 验证 it/lan.js 语法完全正确且 lan 对象各模块完备"""
        lan_path = os.path.join(IT_DIR, "lan.js").replace("\\", "/")
        check_script = (
            "const fs = require('fs');\n"
            + f"let code = fs.readFileSync('{lan_path}', 'utf-8');\n"
            + "let lan = new Function(code + '; return lan;')();\n"
            + "if (typeof lan === 'undefined') { throw new Error('lan is not defined'); }\n"
            + "if (typeof lan.get !== 'function') { throw new Error('lan.get is not a function'); }\n"
            + "var requiredSections = ['index', 'site', 'ftp', 'database', 'config', 'files', 'soft', 'public'];\n"
            + "for (var i = 0; i < requiredSections.length; i++) {\n"
            + "    if (!lan[requiredSections[i]] || typeof lan[requiredSections[i]] !== 'object') {\n"
            + "        throw new Error('Missing section: ' + requiredSections[i]);\n"
            + "    }\n"
            + "}\n"
            + "console.log('SUCCESS_NODE_VALID');\n"
        )

        res = subprocess.run(["node", "-e", check_script], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0, f"Node.js 解析 lan.js 失败: {res.stderr}")
        self.assertIn("SUCCESS_NODE_VALID", res.stdout)

    def test_05_utf8_no_bom_and_lf_endings(self):
        """验证全部 13 个文件编码为 UTF-8 无 BOM，且换行符统一为 LF"""
        for fname in EXPECTED_FILES:
            fpath = os.path.join(IT_DIR, fname)
            with open(fpath, "rb") as f:
                raw_bytes = f.read()
            # 校验无 UTF-8 BOM (0xEF, 0xBB, 0xBF)
            self.assertFalse(raw_bytes.startswith(b'\xef\xbb\xbf'), f"文件包含 BOM 头: {fname}")
            # 校验无 Windows CRLF (\r\n) 换行符
            self.assertNotIn(b'\r\n', raw_bytes, f"文件包含 CRLF 换行符: {fname}")

if __name__ == "__main__":
    unittest.main(verbosity=2)
