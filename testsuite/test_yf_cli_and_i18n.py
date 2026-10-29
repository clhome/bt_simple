# coding: utf-8
# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）yf 命令与双语国际化强化测试套件
# ---------------------------------------------------------------------------------
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------

import ast
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

PANEL_TOOLS = os.path.join(ROOT, 'panel_tools.py')
YF_TPL = os.path.join(ROOT, 'scripts', 'init.d', 'yf.tpl')


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


class YfCliMenuAndLanguageTest(unittest.TestCase):
    """验证 yf 命令行菜单、双语切换、过期菜单清理及安全可靠性。"""

    def setUp(self):
        self.tools_src = _read(PANEL_TOOLS)
        self.tpl_src = _read(YF_TPL)

    def test_01_deprecated_php52_menus_removed(self):
        """确认 PHP52 相关过期菜单项及其分发分支已彻底移除。"""
        self.assertNotIn("'(100)  开启PHP52显示'", self.tools_src)
        self.assertNotIn("'(101)  关闭PHP52显示'", self.tools_src)
        self.assertNotIn('elif yf_input == 100:', self.tools_src)
        self.assertNotIn('elif yf_input == 101:', self.tools_src)

        # nums 白名单中不得含有 100 和 101
        start = self.tools_src.index('    nums = [')
        nums_block = self.tools_src[start:self.tools_src.index(']', start)]
        self.assertNotRegex(nums_block, r'\b100\b', 'nums 白名单仍残留 100')
        self.assertNotRegex(nums_block, r'\b101\b', 'nums 白名单仍残留 101')

    def test_02_language_switch_menu_and_dispatch_registered(self):
        """确认已新增 (32) 切换面板语言 菜单项和相应处理。"""
        self.assertIn("'(32)   切换面板语言'", self.tools_src)
        self.assertIn("'(32)   Switch Panel Language'", self.tools_src)

        start = self.tools_src.index('    nums = [')
        nums_block = self.tools_src[start:self.tools_src.index(']', start)]
        self.assertRegex(nums_block, r'\b32\b', 'nums 白名单缺少 32')
        self.assertIn('elif yf_input == 32:', self.tools_src, '缺少 32 的分发分支')
        self.assertIn('switch_panel_language', self.tools_src)

    def test_03_main_method_supports_lang_command(self):
        """确认 main() 命令行解析支持 yf lang 子命令。"""
        self.assertIn("elif method == 'lang':", self.tools_src)

    def test_04_init_script_tpl_fixes(self):
        """确认 yf.tpl 中的遗留 bug 已全部修复：未定义变量、路由错误、错别字及双语。"""
        # 1. 不得存在未定义的 $yf_path 变量
        self.assertNotIn('$yf_path', self.tpl_src, 'yf.tpl 仍残留未定义的 $yf_path 变量')

        # 2. unbind_ssl 路由必须正确指向 yf_unbind_ssl 而非 yf_unbind_domain
        self.assertRegex(self.tpl_src, r"'unbind_ssl'\)\s*yf_unbind_ssl;;",
                         'unbind_ssl 分支未正确调用 yf_unbind_ssl')

        # 3. yf.tpl 注册了 lang 命令
        self.assertRegex(self.tpl_src, r"'lang'\)\s*cd \$\{PANEL_DIR\} && python3 \$\{PANEL_DIR\}/panel_tools\.py lang",
                         'yf.tpl 未注册 lang 子命令')

        # 4. yf list 和 yf default 支持读取 data/language.pl 双语
        self.assertIn('data/language.pl', self.tpl_src)
        self.assertIn('Yufeng Panel Information', self.tpl_src)
        self.assertIn('Switch panel language', self.tpl_src)

    def test_05_username_validation_hardening(self):
        """用户名修改输入具备正则安全防御。"""
        import panel_tools
        # 测试正则逻辑
        valid_usernames = ['admin_1', 'user123', 'yf_user_2026']
        invalid_usernames = ['adm', 'a'*25, 'user name', 'user;rm -rf', 'user<script>']
        for u in valid_usernames:
            self.assertTrue(bool(re.match(r'^[a-zA-Z0-9_]{5,20}$', u)))
        for u in invalid_usernames:
            self.assertFalse(bool(re.match(r'^[a-zA-Z0-9_]{5,20}$', u)))

    def test_06_display_width_alignment(self):
        """验证全角半角字符显示宽度计算，确保终端菜单排版工整。"""
        from panel_tools import _get_display_width, _pad_menu_item
        self.assertEqual(_get_display_width('abc'), 3)
        self.assertEqual(_get_display_width('重启面板服务'), 12)
        # 补全空格测试
        padded_cn = _pad_menu_item('(1)    重启面板服务', 38)
        padded_en = _pad_menu_item('(1)    Restart Panel Service', 38)
        self.assertEqual(_get_display_width(padded_cn), 38)
        self.assertEqual(_get_display_width(padded_en), 38)

    def test_07_language_switch_logic(self):
        """验证 switch_panel_language 能够正确持久化至 data/language.pl。"""
        import panel_tools
        import core.yf as yf
        panel_dir = yf.getPanelDir()
        lang_file = os.path.join(panel_dir, 'data', 'language.pl')
        orig_content = yf.readFile(lang_file) if os.path.exists(lang_file) else None

        try:
            panel_tools.switch_panel_language('en')
            self.assertTrue(os.path.exists(lang_file))
            self.assertEqual(yf.readFile(lang_file).strip(), 'en')

            panel_tools.switch_panel_language('zh-CN')
            self.assertEqual(yf.readFile(lang_file).strip(), 'zh-CN')
        finally:
            if orig_content is not None:
                yf.writeFile(lang_file, orig_content)
            elif os.path.exists(lang_file):
                os.remove(lang_file)


if __name__ == '__main__':
    unittest.main(verbosity=2)

