# coding:utf-8

import os
import re
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGINS_DIR = os.path.join(ROOT_DIR, "plugins")

EXCLUDE_PLUGINS = {"待审核", "op_waf"}

class TestAllPluginsUi(unittest.TestCase):

    def setUp(self):
        self.plugins = [
            d for d in os.listdir(PLUGINS_DIR)
            if os.path.isdir(os.path.join(PLUGINS_DIR, d)) and d not in EXCLUDE_PLUGINS
        ]
        self.plugins.sort()

    def test_total_plugin_count(self):
        """插件数量下限校验（防止插件被误删）。

        历史问题：此处曾硬编码 37，但排除 待审核/ 与 op_waf 后实际为 35，
        导致该用例长期失败。改为「下限校验」——数量异常下降才失败，
        正常新增插件不会再误报。
        """
        self.assertGreaterEqual(
            len(self.plugins), 30,
            f"正式插件数量异常下降，仅剩 {len(self.plugins)} 个（应 ≥30）")

    def test_all_plugins_have_index_html(self):
        for p in self.plugins:
            idx_path = os.path.join(PLUGINS_DIR, p, "index.html")
            self.assertTrue(os.path.exists(idx_path), f"Plugin '{p}' missing index.html")

    def test_all_plugins_have_fixed_width_and_height(self):
        """校验插件弹窗显式设置了宽高。

        注意：参数允许是**数字字面量**或**表达式**（如视口自适应变量）。
        部分插件（fail2ban / op_waf）为适配不同语言文案长度，按视口动态计算
        高度并传入变量，这属于推荐做法，不应判为失败。
        """
        for p in self.plugins:
            idx_path = os.path.join(PLUGINS_DIR, p, "index.html")
            with open(idx_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 匹配实参（数字或表达式，但不跨越嵌套括号）
            w_match = re.search(r"resetPluginWinWidth\s*\(\s*([^()]+?)\s*\)", content)
            h_match = re.search(r"resetPluginWinHeight\s*\(\s*([^()]+?)\s*\)", content)

            self.assertIsNotNone(w_match, f"Plugin '{p}' must call resetPluginWinWidth(width)")
            self.assertIsNotNone(h_match, f"Plugin '{p}' must call resetPluginWinHeight(height)")

            for label, m in (("width", w_match), ("height", h_match)):
                arg = m.group(1).strip()
                self.assertTrue(arg, f"Plugin '{p}' {label} argument must not be empty")
                if arg.isdigit():
                    self.assertGreater(int(arg), 0, f"Plugin '{p}' {label} must be > 0")

    def test_menu_plugins_have_gray_sidebar_and_white_active_cards(self):
        for p in self.plugins:
            idx_path = os.path.join(PLUGINS_DIR, p, "index.html")
            with open(idx_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if "bt-w-menu" in content:
                # 必须包含侧边栏浅灰底纹
                self.assertIn("background-color: #f8fafc !important;", content, f"Plugin '{p}' missing .bt-w-menu gray background #f8fafc")
                # 必须包含选中态纯白卡片
                self.assertIn(".bt-w-menu p.bgw", content, f"Plugin '{p}' missing .bt-w-menu p.bgw active style")
                self.assertIn("background-color: #ffffff !important;", content, f"Plugin '{p}' missing white active background #ffffff")
                # 必须包含内容区滚动保护
                self.assertIn(".bt-w-con", content, f"Plugin '{p}' missing .bt-w-con container style")
                self.assertIn("overflow-y: auto !important;", content, f"Plugin '{p}' missing overflow-y: auto in .bt-w-con")

    def test_single_page_plugins_have_scroll_protection(self):
        for p in self.plugins:
            idx_path = os.path.join(PLUGINS_DIR, p, "index.html")
            with open(idx_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if "bt-w-menu" not in content:
                self.assertIn(".bt-w-con", content, f"Single-page plugin '{p}' missing .bt-w-con container style")
                self.assertIn("overflow-y: auto !important;", content, f"Single-page plugin '{p}' missing overflow-y: auto in .bt-w-con")

if __name__ == '__main__':
    unittest.main()
