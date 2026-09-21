# coding:utf-8

import os
import sys
import json
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OP_WAF_DIR = os.path.join(ROOT_DIR, 'plugins', 'op_waf')

class TestOpWafUi(unittest.TestCase):

    def test_no_ow_post_in_index_html(self):
        index_html_path = os.path.join(OP_WAF_DIR, 'index.html')
        self.assertTrue(os.path.exists(index_html_path), "index.html must exist")
        with open(index_html_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Ensure no owPost remains
        self.assertNotIn('owPost', content, "index.html should not contain deprecated owPost")

        # Ensure renderWafAdditionalContent uses wafApi.postSilent
        self.assertIn('wafApi.postSilent', content, "index.html should use wafApi.postSilent")
        self.assertIn("rule_name: r", content, "index.html should request rule_name")

    def test_rule_json_files_exist_and_valid(self):
        rules = ['args', 'post', 'cookie', 'url', 'user_agent']
        rule_dir = os.path.join(OP_WAF_DIR, 'waf', 'rule')
        for r in rules:
            rule_path = os.path.join(rule_dir, f"{r}.json")
            if os.path.exists(rule_path):
                with open(rule_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.assertIsInstance(data, list, f"Rule file {r}.json should be a JSON list")

    def test_cards_single_line_layout(self):
        index_html_path = os.path.join(OP_WAF_DIR, 'index.html')
        with open(index_html_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查是否采用单行 flex 布局并消除了 flex-wrap: wrap
        self.assertIn("display: flex; gap: 10px; align-items: stretch;", content)
        self.assertNotIn("flex-wrap: wrap", content)
        # 检查 5 个卡片都采用了 flex: 1; min-width: 0;
        self.assertEqual(content.count("flex: 1; min-width: 0;"), 5)

    def test_sidebar_style_and_adaptive_height(self):
        index_html_path = os.path.join(OP_WAF_DIR, 'index.html')
        with open(index_html_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 左侧菜单栏灰色底纹背景设置
        self.assertIn("background-color: #f8fafc !important;", content)

        # 选中项白色卡片样式
        self.assertIn(".bt-w-menu p.bgw", content)
        self.assertIn("background-color: #ffffff !important;", content)

        # 右侧内容区容器：纵向滚动唯一由 .bt-w-con 承担
        self.assertIn(".bt-w-con", content)
        self.assertIn("overflow-y: auto !important;", content)

    def test_popup_height_is_adaptive_not_pixel_locked(self):
        """
        弹窗高度契约（随用户反馈「高度显示不够适配」固化）：

        1. 初始高度按视口自适应，而不是写死 620 —— 非中文文案长度约为中文的 1.5~2 倍；
        2. 内容渲染完成后再按真实内容高度二次收敛，短页面不留大片空白；
        3. .bt-w-main 只能是 100%，绝不能像素锁死。

        第 3 条是这次的真实故障根因：resetPluginWinHeight() 用 jQuery 写的是**行内**高度，
        而行内样式优先级低于 !important，所以 `.bt-w-main { height: 578px !important }`
        会让它在 620~860 的弹窗里恒定停在 578px，底部留出一条空白死区。
        """
        index_html_path = os.path.join(OP_WAF_DIR, 'index.html')
        with open(index_html_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 1. 视口自适应（下限 620 不小于原尺寸，上限 860 避免超大屏过度拉伸）
        self.assertRegex(
            content,
            r"resetPluginWinHeight\(h\)",
            "应调用 resetPluginWinHeight(h) 传入计算后的自适应高度")
        self.assertRegex(
            content,
            r"Math\.max\(\s*620\s*,\s*Math\.min\(\s*860\s*,\s*vh\s*-\s*90\s*\)\s*\)",
            "初始高度应为视口自适应公式 Math.max(620, Math.min(860, vh - 90))")

        # 2. 内容二次收敛：MutationObserver + 防抖 + 阈值
        self.assertIn("MutationObserver", content, "应监听内容变化以二次收敛高度")
        self.assertRegex(content, r"setTimeout\(\s*fit\s*,\s*\d+\s*\)", "应有防抖后再测量")
        self.assertRegex(content, r"THRESHOLD\s*=\s*\d+", "应有调整阈值避免高度震荡")

        # 3. 关键红线：.bt-w-main 不得像素锁死
        self.assertNotRegex(
            content,
            r"\.bt-w-main\s*\{[^}]*height:\s*\d+px",
            ".bt-w-main 不能写死像素高度（行内样式会输给 !important，导致底部死区）")
        self.assertRegex(
            content,
            r"\.bt-w-main\s*\{[^}]*height:\s*100%\s*!important",
            ".bt-w-main 应为 height: 100% !important，实际高度由 JS 统一注入")

if __name__ == '__main__':
    unittest.main()


