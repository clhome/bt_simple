# -*- coding: utf-8 -*-
"""
验证软件卸载弹窗备份复选框及多语言适配自动化测试套件
"""
import os
import sys
import json
import re
import unittest
import subprocess

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = r"f:\git\gitea20250909\bt_simple"
LANG_DIR = os.path.join(BASE_DIR, "web", "static", "language")
SOFT_JS = os.path.join(BASE_DIR, "web", "static", "app", "soft.js")

LANGS = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]
REQUIRED_KEYS = [
    "uninstall_confirm_prefix",
    "uninstall_confirm_suffix",
    "uninstall_backup_tip",
    "software_uninstallation_confirmation",
    "confirm_uninstall"
]

ZH_PATTERN = re.compile(r'[\u4e00-\u9fff]')

class TestUninstallModalI18n(unittest.TestCase):
    def test_01_soft_js_modal_html_structure(self):
        """测试 soft.js 中 runUninstallVersion 弹窗 HTML 标签完整闭合与复选框存在"""
        with open(SOFT_JS, "r", encoding="utf-8") as f:
            content = f.read()

        func_idx = content.find("function runUninstallVersion")
        self.assertNotEqual(func_idx, -1, "soft.js 未找到 runUninstallVersion 函数")

        func_body = content[func_idx:func_idx + 1500]

        # 1. 验证备份复选框存在
        self.assertIn("id='normal_uninstall_backup_chk'", func_body, "runUninstallVersion 缺少备份复选框 id")

        # 2. 提取 contentHtml
        m = re.search(r'var contentHtml\s*=\s*"([\s\S]*?)";', func_body)
        self.assertTrue(m, "未能提取 contentHtml 字符串定义")
        html_template = m.group(1)

        # 验证 div 标签平衡
        div_open = html_template.count("<div")
        div_close = html_template.count("</div>")
        self.assertEqual(div_open, div_close, f"div 标签不平衡: open={div_open}, close={div_close}")

        # 验证 span 标签平衡
        span_open = html_template.count("<span")
        span_close = html_template.count("</span>")
        self.assertEqual(span_open, span_close, f"span 标签不平衡: open={span_open}, close={span_close}")

        # 验证 label 标签平衡
        label_open = html_template.count("<label")
        label_close = html_template.count("</label>")
        self.assertEqual(label_open, label_close, f"label 标签不平衡: open={label_open}, close={label_close}")

        # 验证弹窗配置
        self.assertIn("closeBtn: 1", func_body, "runUninstallVersion 应显式开启 closeBtn: 1")

    def test_02_template_json_keys(self):
        """测试 6 国语言 template.json 中 soft 模块词条完整且无污染"""
        for lang in LANGS:
            tmpl_path = os.path.join(LANG_DIR, lang, "template.json")
            self.assertTrue(os.path.exists(tmpl_path), f"缺失 {lang}/template.json")
            with open(tmpl_path, "r", encoding="utf-8") as f:
                d = json.load(f)

            soft_dict = d.get("soft", {})
            for k in REQUIRED_KEYS:
                self.assertIn(k, soft_dict, f"[{lang}] template.json soft 模块缺失键: {k}")
                val = soft_dict[k]
                self.assertTrue(val, f"[{lang}] template.json soft.{k} 为空")
                if lang in ['en', 'fr', 'de', 'it']:
                    self.assertFalse(ZH_PATTERN.search(val), f"[{lang}] template.json soft.{k} 包含中文字符: {val}")

    def test_03_lan_js_keys(self):
        """测试 6 国语言 lan.js 中 soft 模块词条完整且无污染"""
        for lang in LANGS:
            lan_path = os.path.join(LANG_DIR, lang, "lan.js")
            self.assertTrue(os.path.exists(lan_path), f"缺失 {lang}/lan.js")
            with open(lan_path, "r", encoding="utf-8") as f:
                content = f.read()

            for k in REQUIRED_KEYS:
                self.assertIn(f'"{k}":', content, f"[{lang}] lan.js 缺失键: {k}")

    def test_04_js_syntax(self):
        """测试各语言 lan.js 零语法报错"""
        for lang in LANGS:
            lan_path = os.path.join(LANG_DIR, lang, "lan.js").replace("\\", "/")
            cmd = ["node", "-e", f'const vm = require("vm"); const fs = require("fs"); vm.runInThisContext(fs.readFileSync("{lan_path}", "utf8"));']
            p = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, f"[{lang}] lan.js 语法错误: {p.stderr}")

    def test_05_runtime_translation(self):
        """测试各语言在浏览器环境下的运行时实际翻译值

        这里断言的是**不变量**，不是冻结的文案 —— 原来把六种语言的
        prefix/suffix/backup 逐字写死，文案一改（例如英文从
        "Are you sure you want to uninstall 【" 变成
        "Do you really want to uninstall ["）用例就假红，
        而真正的缺陷反而可能被忽略。现在检查：
          · 三个键都能解析出非空值，且不残留 `soft.` 前缀（键泄漏）；
          · prefix 含开括号、suffix 含闭括号（确认框是 prefix+库名+suffix 拼的）；
          · 西欧语言（en/de/fr/it）的值里不得出现中日韩字符或全角标点；
          · 备份提示必须提到 /www/backup。
        """
        i18n_path = os.path.join(BASE_DIR, "web", "static", "app", "i18n.js").replace("\\", "/")
        lang_dir_path = LANG_DIR.replace("\\", "/")

        node_script = """
        const fs = require('fs');
        const path = require('path');
        const vm = require('vm');

        const langDir = '__LANG_DIR__';
        const i18nJs = fs.readFileSync('__I18N_PATH__', 'utf8');

        // 中日韩汉字 + 全角标点（】、？、【 等都落在这里）
        const CJK = /[\\u3000-\\u303f\\u3040-\\u30ff\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff\\uff00-\\uffef]/;
        const WESTERN = ['en', 'de', 'fr', 'it'];

        for (const lang of ['en', 'de', 'fr', 'it', 'zh-TW', 'zh-CN']) {
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

            const pref = vm.runInContext("t('soft.uninstall_confirm_prefix')", ctx);
            const suff = vm.runInContext("t('soft.uninstall_confirm_suffix')", ctx);
            const bkp = vm.runInContext("t('soft.uninstall_backup_tip')", ctx);

            const problems = [];
            const vals = [['prefix', pref], ['suffix', suff], ['backup', bkp]];
            for (const [name, v] of vals) {
                if (!v) { problems.push(name + ' 为空或未解析'); continue; }
                if (String(v).indexOf('soft.') === 0) { problems.push(name + ' 键泄漏: ' + v); }
            }
            if (pref && !/[\\[【]/.test(pref)) problems.push('prefix 缺开括号: ' + pref);
            if (suff && !/[\\]】]/.test(suff)) problems.push('suffix 缺闭括号: ' + suff);
            if (bkp && bkp.indexOf('/www/backup') < 0) problems.push('backup 未提到 /www/backup: ' + bkp);
            if (WESTERN.indexOf(lang) >= 0) {
                for (const [name, v] of vals) {
                    if (v && CJK.test(v)) problems.push(name + ' 混入中日韩字符/全角标点: ' + v);
                }
            }
            if (problems.length) throw new Error('[' + lang + '] ' + problems.join(' | '));
        }
        console.log('ALL RUNTIME TRANSLATIONS PASS');
        """.replace('__LANG_DIR__', lang_dir_path).replace('__I18N_PATH__', i18n_path)

        cmd = ["node", "-e", node_script]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', cwd=BASE_DIR)
        self.assertEqual(p.returncode, 0, f"Node.js 运行时翻译测试失败:\n{p.stderr}\n{p.stdout}")

if __name__ == '__main__':
    unittest.main()
