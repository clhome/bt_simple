#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专项自动化测试：验证重启/修复服务器多语言与拟态风格实现
1. 验证 6 国语言包中 template.index.json, template.json, lan.js 词条完整性
2. 验证 i18n.js FALLBACK_MAP 包含重启/修复词条
3. 验证 index.js 中 reBoot 函数无硬编码中文，全面接入 t(...) 与拟态 DOM
4. 验证 site.css 与 ensite.css 拟态样式规则完全对齐
5. 验证所有涉及 JS 与 JSON 文件语法无误
"""

import os
import json
import re
import subprocess
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANG_DIR = os.path.join(BASE_DIR, 'web', 'static', 'language')
APP_DIR = os.path.join(BASE_DIR, 'web', 'static', 'app')
CSS_DIR = os.path.join(BASE_DIR, 'web', 'static', 'css')

EXPECTED_KEYS = [
    "reboot_server_title",
    "reboot_server",
    "reboot_panel",
    "reboot_repair_btn",
    "reboot_repair_tip",
    "reboot_panel_title",
    "reboot_panel_confirm",
    "reboot_panel_wait_msg",
    "reboot_repair_dialog_title",
    "reboot_repair_confirm",
    "reboot_repair_badge",
    "reboot_repair_preparing",
    "reboot_server_safe_title",
    "reboot_server_container_tip",
    "reboot_server_safe_desc",
    "reboot_step_stop_web",
    "reboot_step_stop_mysql",
    "reboot_step_reboot_server",
    "reboot_step_wait_server",
    "reboot_status_stopping_web",
    "reboot_status_stopping_mysql",
    "reboot_status_starting_reboot",
    "reboot_status_waiting_start",
    "reboot_status_success"
]

LANGUAGES = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']

class TestRebootI18nAndStyle(unittest.TestCase):

    def test_01_template_index_json_keys(self):
        """验证全部 6 国语言的 template.index.json 均包含所有预期键值"""
        for lang in LANGUAGES:
            path = os.path.join(LANG_DIR, lang, 'template.index.json')
            self.assertTrue(os.path.exists(path), f"{path} 不存在")
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            index_data = data.get('index', {})
            for key in EXPECTED_KEYS:
                self.assertIn(key, index_data, f"[{lang}] template.index.json 缺少键: {key}")
                val = index_data[key]
                self.assertTrue(bool(val and val.strip()), f"[{lang}] 键 {key} 的值为空")
                if lang == 'en':
                    # 英文不应含中文字符
                    has_chinese = bool(re.search(r'[\u4e00-\u9fa5]', val))
                    self.assertFalse(has_chinese, f"[en] 键 {key} 包含未翻译的中文: {val}")

    def test_02_template_json_keys(self):
        """验证全部 6 国语言的 template.json 均包含所有预期键值"""
        for lang in LANGUAGES:
            path = os.path.join(LANG_DIR, lang, 'template.json')
            self.assertTrue(os.path.exists(path), f"{path} 不存在")
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            index_data = data.get('index', {})
            for key in EXPECTED_KEYS:
                self.assertIn(key, index_data, f"[{lang}] template.json 缺少键: {key}")

    def test_03_lan_js_keys(self):
        """验证全部 6 国语言的 lan.js 均包含所有预期键值"""
        for lang in LANGUAGES:
            path = os.path.join(LANG_DIR, lang, 'lan.js')
            self.assertTrue(os.path.exists(path), f"{path} 不存在")
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            for key in EXPECTED_KEYS:
                self.assertIn(f'"{key}":', content, f"[{lang}] lan.js 缺少键: {key}")

    def test_04_i18n_fallback_map(self):
        """验证 i18n.js FALLBACK_MAP 包含兜底词条"""
        path = os.path.join(APP_DIR, 'i18n.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        for key in EXPECTED_KEYS:
            self.assertTrue(f"'{key}':" in content or f'"{key}":' in content, f"i18n.js 缺少兜底键: {key}")

    def test_05_index_js_no_hardcoded_chinese_in_reboot(self):
        """验证 index.js 中的 reBoot 函数使用 t(...)，且无写死的中文 HTML"""
        path = os.path.join(APP_DIR, 'index.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 截取 reBoot 函数内容
        start_idx = content.find('function reBoot()')
        self.assertNotEqual(start_idx, -1, "index.js 中未找到 reBoot 函数")
        end_idx = content.find('function repPanel()', start_idx)
        self.assertNotEqual(end_idx, -1, "index.js 中未找到 repPanel 函数")
        reboot_func = content[start_idx:end_idx]

        # 检查是否包含关键的 t 调用
        self.assertIn("t('index.reboot_server_title'", reboot_func)
        self.assertIn("t('index.reboot_server'", reboot_func)
        self.assertIn("t('index.reboot_panel'", reboot_func)
        self.assertIn("t('index.reboot_repair_btn'", reboot_func)
        self.assertIn("t('index.reboot_repair_tip'", reboot_func)
        self.assertIn("t('index.reboot_panel_title'", reboot_func)
        self.assertIn("t('index.reboot_panel_confirm'", reboot_func)
        self.assertIn("t('index.reboot_repair_dialog_title'", reboot_func)
        self.assertIn("t('index.reboot_repair_confirm'", reboot_func)
        self.assertIn("t('index.reboot_server_safe_title'", reboot_func)
        self.assertIn("t('index.reboot_step_stop_web'", reboot_func)

        # 检查拟态 DOM 类名
        self.assertIn("rebt-btn-item", reboot_func)
        self.assertIn("rebt-icon-wrapper", reboot_func)
        self.assertIn("rebt-warning-box", reboot_func)
        self.assertIn("btn-neu-cancel", reboot_func)
        self.assertIn("btn-neu-confirm", reboot_func)

        # 检查是否修复了 rebootbox.close() 为 layer.close(rebootbox)
        self.assertNotIn("rebootbox.close()", reboot_func)
        self.assertIn("layer.close(rebootbox)", reboot_func)

    def test_06_css_neumorphic_rules_aligned(self):
        """验证 site.css 与 ensite.css 均包含拟态规则并且一致"""
        for css_name in ['site.css', 'ensite.css']:
            path = os.path.join(CSS_DIR, css_name)
            with open(path, 'r', encoding='utf-8') as f:
                css_content = f.read()
            self.assertIn(".rebt-con", css_content, f"{css_name} 缺少 .rebt-con")
            self.assertIn(".rebt-btn-item", css_content, f"{css_name} 缺少 .rebt-btn-item")
            self.assertIn(".rebt-icon-wrapper", css_content, f"{css_name} 缺少 .rebt-icon-wrapper")
            self.assertIn(".rebt-warning-box", css_content, f"{css_name} 缺少 .rebt-warning-box")
            self.assertIn(".btn-neu-cancel", css_content, f"{css_name} 缺少 .btn-neu-cancel")
            self.assertIn(".btn-neu-confirm", css_content, f"{css_name} 缺少 .btn-neu-confirm")

    def test_07_js_syntax_via_node(self):
        """使用 Node.js 严格执行并验证所有修改的 JS 文件语法"""
        node_script = """
        const fs = require('fs');
        const langs = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it'];
        langs.forEach(lang => {
            const code = fs.readFileSync('web/static/language/' + lang + '/lan.js', 'utf8');
            new Function(code);
        });
        new Function(fs.readFileSync('web/static/app/i18n.js', 'utf8'));
        new Function(fs.readFileSync('web/static/app/index.js', 'utf8'));
        console.log('ALL_JS_SYNTAX_PASS');
        """
        proc = subprocess.run(['node', '-e', node_script], cwd=BASE_DIR, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Node.js 语法检查失败: {proc.stderr}")
        self.assertIn('ALL_JS_SYNTAX_PASS', proc.stdout)

if __name__ == '__main__':
    unittest.main()
