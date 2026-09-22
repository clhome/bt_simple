# -*- coding: utf-8 -*-
"""
自动化测试套件：任务管理器（task_manager）网络标签页表头、静态代码健康度与全量多语言国际化验证
覆盖：
1. 网络表头无 undefined 测试
2. 网络表头 6 国语言正确渲染测试
3. 弹窗标题符号规范与多语种测试
4. 顶部 Tab、设置项及占位符翻译覆盖测试
5. 外语包（en, de, fr, it）0 中文残留测试
6. 6 国语言包键名 100% 对齐测试
7. index.html 内嵌 CSS 语法合法性与空规则集检查（防止 th: { / tr: { 等语法错误及空 ruleset）
8. index.html DOM 结构与多语言属性完整性检查
9. 前端 JavaScript 脚本语法 Node.js V8 引擎编译检查
"""
import os
import json
import re
import subprocess
import unittest

BASE_DIR = r"f:\git\gitea20250909\bt_simple"
TM_JS = os.path.join(BASE_DIR, "plugins", "task_manager", "js", "task_manager.js")
TM_HTML = os.path.join(BASE_DIR, "plugins", "task_manager", "index.html")
SOFT_JS = os.path.join(BASE_DIR, "web", "static", "app", "soft.js")
I18N_JS = os.path.join(BASE_DIR, "web", "static", "app", "i18n.js")
LANG_DIR = os.path.join(BASE_DIR, "plugins", "task_manager", "lang")
LANGS = ["zh-CN", "zh-TW", "en", "de", "fr", "it"]

class TestTaskManagerI18n(unittest.TestCase):

    def setUp(self):
        self.lang_dicts = {}
        for l in LANGS:
            fpath = os.path.join(LANG_DIR, f"{l}.json")
            self.assertTrue(os.path.exists(fpath), f"Language file not found: {fpath}")
            with open(fpath, "r", encoding="utf-8") as f:
                self.lang_dicts[l] = json.load(f)

    def test_01_no_lan_index_undefined_in_js(self):
        """测试 1: task_manager.js 中不得存在未定义的 lan.index 引用"""
        with open(TM_JS, "r", encoding="utf-8") as f:
            content = f.read()
        
        matches = re.findall(r'lan\.index\.[a-zA-Z0-9_]+', content)
        self.assertEqual(len(matches), 0, f"Found undefined lan.index calls: {matches}")
        
        # 确保包含 pt('协议' 等关键表头定义
        for h in ["协议", "本地地址", "外部地址", "状态", "进程", "PID"]:
            pattern = f"pt('{h}'"
            self.assertIn(pattern, content, f"Header '{h}' is not wrapped with pt() in task_manager.js")

    def test_02_network_headers_translation_in_all_langs(self):
        """测试 2: 验证网络表头各字段在 6 国语言下的翻译绝不为 None 或空，且外语无中文"""
        headers = ["协议", "本地地址", "外部地址", "状态", "进程", "PID", "屏蔽此IP"]
        zh_pattern = re.compile(r'[\u4e00-\u9fa5]')

        for l in LANGS:
            d = self.lang_dicts[l]
            for h in headers:
                self.assertIn(h, d, f"Header key '{h}' missing in {l}.json")
                trans = d[h]
                self.assertTrue(bool(trans), f"Translation for '{h}' in {l} is empty")
                self.assertNotIn("undefined", trans.lower(), f"Translation contains undefined in {l}")

                if l in ["en", "de", "fr", "it"]:
                    self.assertFalse(zh_pattern.search(trans), f"Foreign lang {l} contains Chinese in '{h}': {trans}")

        # 针对英文的具体值断言
        en = self.lang_dicts["en"]
        self.assertEqual(en["协议"], "Protocol")
        self.assertEqual(en["本地地址"], "Local Address")
        self.assertEqual(en["外部地址"], "Foreign Address")
        self.assertEqual(en["状态"], "Status")
        self.assertEqual(en["进程"], "Process")
        self.assertEqual(en["PID"], "PID")
        self.assertEqual(en["屏蔽此IP"], "Block IP")

    def test_03_soft_js_dialog_title_formatting(self):
        """测试 3: 验证 soft.js 中的标题格式化逻辑规整性"""
        with open(SOFT_JS, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 不应存在以前恶性的写死中文全角与英文半角拼接: '【' + version + ...
        self.assertNotIn("_title + '【' + version + (lan && lan.soft", content)
        
        # 应包含当前语种区分与 winTitle 规范拼接
        self.assertIn("isZh", content)
        self.assertIn("winTitle", content)

    def test_04_i18n_js_translate_plugin_dom_support(self):
        """测试 4: 验证 i18n.js 中的 translatePluginDOM 已支持水平Tab与设置表头项"""
        with open(I18N_JS, "r", encoding="utf-8") as f:
            content = f.read()
        
        self.assertIn(".man-menu-sub span", content, "translatePluginDOM should support .man-menu-sub span")
        self.assertIn(".setting_ul .setting_ul_li span", content, "translatePluginDOM should support setting dropdown items")
        self.assertIn("input[placeholder]", content, "translatePluginDOM should support input placeholder")

    def test_05_all_tabs_and_columns_have_translations(self):
        """测试 5: 验证 task_manager 所有 Tab 标签和表头设置项均拥有 6 国语言翻译"""
        required_keys = [
            "进程", "启动项", "服务", "网络", "用户", "计划任务", "会话",
            "支持名称、字段模糊搜索", "设置表头",
            "应用名称", "PID", "线程", "用户", "CPU", "内存", "io读", "io写", "上行", "下行", "连接", "状态", "操作"
        ]
        for l in LANGS:
            d = self.lang_dicts[l]
            for rk in required_keys:
                self.assertIn(rk, d, f"Key '{rk}' missing in {l}.json")
                self.assertTrue(bool(d[rk]), f"Value for '{rk}' is empty in {l}.json")

    def test_06_no_chinese_in_foreign_languages(self):
        """测试 6: 严格检验外语语言包 (en, de, fr, it) 中 100% 零中文字符残留"""
        zh_pattern = re.compile(r'[\u4e00-\u9fa5]')
        for l in ["en", "de", "fr", "it"]:
            d = self.lang_dicts[l]
            for k, v in d.items():
                self.assertFalse(zh_pattern.search(v), f"Foreign language {l}.json key '{k}' has Chinese in value: '{v}'")

    def test_07_language_keys_fully_aligned(self):
        """测试 7: 验证 6 个语言包的键名集合严格 100% 一致"""
        ref_keys = set(self.lang_dicts["zh-CN"].keys())
        for l in ["zh-TW", "en", "de", "fr", "it"]:
            curr_keys = set(self.lang_dicts[l].keys())
            diff = ref_keys ^ curr_keys
            self.assertEqual(len(diff), 0, f"Keys not aligned between zh-CN and {l}: {diff}")

    def test_08_index_html_css_syntax_and_cleanliness(self):
        """测试 8: 静态代码健康度 - 严格检测 index.html 中的 CSS 语法错误与警告规则"""
        with open(TM_HTML, "r", encoding="utf-8") as f:
            html_content = f.read()

        style_match = re.search(r'<style>(.*?)</style>', html_content, re.DOTALL)
        self.assertTrue(style_match, "No <style> block found in index.html")
        css_content = style_match.group(1)

        # 1. 检查选择器后误写冒号的致命语法错误（如 #TaskManagement th: { 或 tr: {）
        colon_errors = re.findall(r'(\b[a-zA-Z0-9_\-\.#]+\s*:\s*\{)', css_content)
        # 过滤合法的伪类（如 :hover { 等）
        invalid_colons = []
        for match in colon_errors:
            # 合法的伪类列表
            valid_pseudo = [':hover', ':focus', ':active', ':disabled', ':checked', ':first-child', ':last-child', ':nth-of-type', '::after', '::before']
            if not any(vp in match for vp in valid_pseudo):
                invalid_colons.append(match)
        self.assertEqual(len(invalid_colons), 0, f"Invalid CSS selectors with illegal colon before brace: {invalid_colons}")

        # 2. 括号对称性校验
        open_braces = css_content.count('{')
        close_braces = css_content.count('}')
        self.assertEqual(open_braces, close_braces, f"CSS brace mismatch: {open_braces} open vs {close_braces} close")

        # 3. 检查空规则集（去除注释后）
        css_clean = re.sub(r'/\*.*?\*/', '', css_content, flags=re.DOTALL)
        empty_rules = re.findall(r'([^{}]+)\{\s*\}', css_clean)
        clean_empty_rules = [r.strip() for r in empty_rules if r.strip()]
        self.assertEqual(len(clean_empty_rules), 0, f"Empty CSS rulesets found: {clean_empty_rules}")

        # 4. 检查 display: inline-block 与 float: right 同时声明的冲突警告
        rule_blocks = re.findall(r'\{([^{}]+)\}', css_clean)
        for block in rule_blocks:
            has_inline_block = bool(re.search(r'display\s*:\s*inline-block', block))
            has_float = bool(re.search(r'float\s*:\s*(left|right)', block))
            self.assertFalse(has_inline_block and has_float, f"CSS property conflict (inline-block ignored due to float): {block}")

    def test_09_index_html_dom_and_i18n_attributes(self):
        """测试 9: 静态代码健康度 - 验证 index.html DOM 结构完整性与 i18n 属性"""
        with open(TM_HTML, "r", encoding="utf-8") as f:
            html = f.read()

        # 核心容器节点验证
        self.assertIn('class="t-mana TaskManView"', html)
        self.assertIn('id="TaskManagement"', html)
        self.assertIn('id="load_average"', html)
        self.assertIn('class="resource-panel pd15"', html)
        self.assertIn('class="plug_menu set_list_fid_dropdown"', html)

        # 验证 7 个 Tab 标签均已具备 data-i18n 属性
        tab_classes = ["p_list", "p_run", "p_service", "p_network", "p_user", "p_cron", "p_session"]
        for cls in tab_classes:
            self.assertTrue(re.search(rf'class="[^"]*\b{cls}\b[^"]*"[^>]*data-i18n=', html),
                            f"Tab class {cls} is missing data-i18n attribute")

        # 验证搜索框和设置按钮具备国际化属性
        self.assertIn('data-i18n="[placeholder]task_manager.search_placeholder"', html)
        self.assertIn('data-i18n="[title]task_manager.config_table_header"', html)

    def test_10_javascript_syntax_via_node(self):
        """测试 10: 前端 JavaScript 语法 - 使用 Node.js V8 引擎严格编译校验 task_manager.js"""
        cmd = ["node", "-c", TM_JS]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"JavaScript syntax error in task_manager.js:\n{res.stderr}")

if __name__ == "__main__":
    unittest.main(verbosity=2)
