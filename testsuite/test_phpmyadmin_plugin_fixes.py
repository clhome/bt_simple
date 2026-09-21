# -*- coding: utf-8 -*-
"""
自动化测试 phpmyadmin 插件脚本语法与 public.js 基础服务状态面板渲染
"""

import os
import re
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

class TestPhpMyAdminPluginFixes(unittest.TestCase):
    def test_phpmyadmin_js_no_dangling_async(self):
        """测试 phpmyadmin.js 中不包含孤立的 async 关键字"""
        pma_js_path = os.path.join(ROOT_DIR, "plugins", "phpmyadmin", "js", "phpmyadmin.js")
        self.assertTrue(os.path.exists(pma_js_path))
        with open(pma_js_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 确保没有整行为 async 的孤立语句
        lines = [line.strip() for line in content.split("\n")]
        self.assertNotIn("async", lines, "phpmyadmin.js should not contain dangling 'async' statement")

    def test_public_js_plugin_set_service_no_nested_duplication(self):
        """测试 public.js 中 pluginSetService 无重复嵌套且严格按插件类型区分"""
        public_js_path = os.path.join(ROOT_DIR, "web", "static", "app", "public.js")
        self.assertTrue(os.path.exists(public_js_path))
        with open(public_js_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # 提取 pluginSetService 函数体
        match = re.search(r'function pluginSetService\(_name.*?\n\}', content, re.DOTALL)
        self.assertIsNotNone(match, "pluginSetService should exist in public.js")
        func_body = match.group(0)

        # 检查是否包含重复的 '<p class="status">' 嵌套
        self.assertNotIn("'<p class=\"status\">' + ('<p class=\"status\">'", func_body)
        
    def test_phpmyadmin_js_methods_exist(self):
        """测试 phpmyadmin.js 包含 homePage 和 phpVer 函数定义"""
        pma_js_path = os.path.join(ROOT_DIR, "plugins", "phpmyadmin", "js", "phpmyadmin.js")
        with open(pma_js_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("function homePage()", content)
        self.assertIn("function phpVer(", content)

    def test_language_clean_buttons(self):
        """测试 6 国语言包中 restart_1 与 reload_configuration 不包含奇怪符号"""
        langs = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]
        for lang in langs:
            lan_js = os.path.join(ROOT_DIR, "web", "static", "language", lang, "lan.js")
            with open(lan_js, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn("')\">", content)
            self.assertNotIn("')\\\">", content)

    def test_phpmyadmin_index_html_no_homepage_menu(self):
        """测试 phpmyadmin/index.html 中已移除多余的主页菜单项"""
        pma_html_path = os.path.join(ROOT_DIR, "plugins", "phpmyadmin", "index.html")
        with open(pma_html_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("homePage()", content)

    def test_phpmyadmin_service_has_kill_all_php(self):
        """测试 phpmyadmin 服务面板包含 kill_all_php 强杀按钮"""
        pma_js_path = os.path.join(ROOT_DIR, "plugins", "phpmyadmin", "js", "phpmyadmin.js")
        with open(pma_js_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("kill_all_php", content)
        self.assertIn("pma-kill-section", content)

    def test_plugin_config_no_duplicate_textarea(self):
        """测试 public.js 中 pluginConfig 不包含双重 textarea 或重复 HTML 嵌套"""
        public_js_path = os.path.join(ROOT_DIR, "web", "static", "app", "public.js")
        with open(public_js_path, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r'function pluginConfig\(_name.*?\n\}', content, re.DOTALL)
        self.assertIsNotNone(match)
        func_body = match.group(0)
        # 统计 textarea 出现次数，应该只有 1 次
        self.assertEqual(func_body.count('id="textBody"'), 1)

    def test_css_sticky_modal_menu(self):
        """测试 CSS 中包含弹窗菜单固定与独立滚动规则"""
        for css_file in ["site.css", "ensite.css"]:
            css_path = os.path.join(ROOT_DIR, "web", "static", "css", css_file)
            with open(css_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn(".layui-layer-page .bt-w-menu", content)
            self.assertIn(".layui-layer-page .bt-w-con", content)

    def test_get_pma_path_no_double_slash(self):
        """测试 phpmyadmin/index.py 生成的访问地址包含随机保护目录且不出现双斜杠"""
        index_py_path = os.path.join(ROOT_DIR, "plugins", "phpmyadmin", "index.py")
        with open(index_py_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("':' + port + '/' + rand_path + '/index.php'", content)
        self.assertIn("getConfInc()", content)

if __name__ == "__main__":
    unittest.main()








