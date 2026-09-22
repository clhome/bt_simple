# -*- coding: utf-8 -*-
"""
自动化测试监控模块（Monitor）模板渲染与国际化
"""

import os
import sys
import unittest
import json

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "web"))

import jinja2

class TestMonitorI18n(unittest.TestCase):
    def setUp(self):
        self.template_dir = [
            os.path.join(ROOT_DIR, "web", "templates", "default"),
            os.path.join(ROOT_DIR, "web", "templates")
        ]
        self.env = jinja2.Environment(loader=jinja2.FileSystemLoader(self.template_dir))

    def test_monitor_template_syntax(self):
        """测试 monitor.html 模板语法是否合法且无异常"""
        def fake_t(key, default=''):
            return default or key

        class MockG:
            is_pjax = False
            lang = 'zh-CN'

        self.env.globals['t'] = fake_t
        try:
            tpl = self.env.get_template("monitor.html")
            rendered = tpl.render(
                g=MockG(),
                session={"login": True, "username": "admin"},
                data={"use_cdn": "no", "ip": "127.0.0.1"},
                config={"version": "1.0.0", "title": "御风面板", "ip": "127.0.0.1"},
                t=fake_t,
                current_lang="zh-CN",
                menu=[]
            )
            self.assertIn("compute_view", rendered)
            self.assertIn("getload_average_view", rendered)
            self.assertIn("enlargeChart", rendered)
            self.assertIn("control.js", rendered)
        except Exception as e:
            self.fail(f"Template rendering failed with exception: {e}")

    def test_control_keys_in_languages(self):
        """测试所有 6 国语言包中 control 核心词条是否存在"""
        langs = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]
        required_keys = [
            "enlarge_chart", "the_chart_has_not", "enlarge", "loading_please_wait",
            "open_jk", "save_days", "stat_wan_only", "clear_records",
            "resource_usage", "average_load", "cpu_usage", "mem_usage", "disk_io", "net_io",
            "pre"
        ]
        for lang in langs:
            json_path = os.path.join(ROOT_DIR, "web", "static", "language", lang, "template.json")
            self.assertTrue(os.path.exists(json_path), f"Missing template.json for {lang}")
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            control_dict = data.get("control", {})
            for key in required_keys:
                self.assertIn(key, control_dict, f"Missing control.{key} in {lang}")

    def test_public_pre_in_languages(self):
        """测试 6 国语言 public.json 与 lan.js 中 pre 词条有效性"""
        langs = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]
        expected_pre = {
            "zh-CN": "百分比(%)",
            "zh-TW": "百分比(%)",
            "en": "Percentage(%)",
            "fr": "Pourcentage (%)",
            "de": "Prozentsatz (%)",
            "it": "Percentuale (%)"
        }
        for lang in langs:
            # 1. 验证 public.json
            p_path = os.path.join(ROOT_DIR, "web", "static", "language", lang, "public.json")
            self.assertTrue(os.path.exists(p_path))
            with open(p_path, "r", encoding="utf-8") as f:
                p_data = json.load(f)
            self.assertEqual(p_data.get("pre"), expected_pre[lang], f"[{lang}] public.json pre 翻译不匹配")

            # 2. 验证 lan.js
            l_path = os.path.join(ROOT_DIR, "web", "static", "language", lang, "lan.js")
            self.assertTrue(os.path.exists(l_path))
            with open(l_path, "r", encoding="utf-8") as f:
                l_content = f.read()
            self.assertIn('"pre":', l_content, f"[{lang}] lan.js 缺失 pre 键")

    def test_control_js_validity(self):
        """测试 control.js 是否存在并包含关键优化结构与百分比国际化"""
        js_path = os.path.join(ROOT_DIR, "web", "static", "app", "control.js")
        self.assertTrue(os.path.exists(js_path))
        with open(js_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("lan && lan.control && t(", content, "control.js should not have raw buggy t() invocation")
        self.assertIn("enlargeChart", content)
        self.assertIn("chartInstances", content)
        self.assertIn("percentLabel", content)
        self.assertIn("public.pre", content)

    def test_runtime_percent_translations(self):
        """测试 6 国语言在运行时真实输出对应语言的百分比标签"""
        import subprocess
        i18n_path = os.path.join(ROOT_DIR, "web", "static", "app", "i18n.js").replace("\\", "/")
        lang_dir = os.path.join(ROOT_DIR, "web", "static", "language").replace("\\", "/")

        node_script = """
        const fs = require('fs');
        const path = require('path');
        const vm = require('vm');

        const langDir = '__LANG_DIR__';
        const i18nJs = fs.readFileSync('__I18N_PATH__', 'utf8');

        const expected = {
            'zh-CN': '百分比(%)',
            'zh-TW': '百分比(%)',
            'en': 'Percentage(%)',
            'fr': 'Pourcentage (%)',
            'de': 'Prozentsatz (%)',
            'it': 'Percentuale (%)'
        };

        for (const [lang, exp] of Object.entries(expected)) {
            const lanJs = fs.readFileSync(path.join(langDir, lang, 'lan.js'), 'utf8');
            const sandbox = {
                window: {},
                document: { cookie: 'yf_lang=' + lang, querySelectorAll: () => [], readyState: 'complete' },
                navigator: { languages: [lang] },
                location: { search: '' },
                localStorage: { getItem: () => lang, setItem: () => {} },
                _SERVER_LANG: lang
            };
            sandbox.window = sandbox;
            const ctx = vm.createContext(sandbox);
            vm.runInContext(lanJs, ctx);
            vm.runInContext(i18nJs, ctx);

            const res = vm.runInContext("t('public.pre')", ctx);
            if (res !== exp) {
                throw new Error(`[${lang}] t('public.pre') got '${res}', expected '${exp}'`);
            }
        }
        console.log('ALL PERCENTAGE RUNTIME TRANSLATIONS PASS');
        """.replace('__LANG_DIR__', lang_dir).replace('__I18N_PATH__', i18n_path)

        cmd = ["node", "-e", node_script]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=ROOT_DIR)
        self.assertEqual(p.returncode, 0, f"运行时翻译失败:\n{p.stderr}\n{p.stdout}")

if __name__ == "__main__":
    unittest.main()

