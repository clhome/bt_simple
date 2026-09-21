#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestSoftSearchStyle(unittest.TestCase):
    """验证软件页面搜索按钮样式、间距与对齐优化"""

    def setUp(self):
        self.site_css_path = os.path.join(BASE_DIR, "web", "static", "css", "site.css")
        self.ensite_css_path = os.path.join(BASE_DIR, "web", "static", "css", "ensite.css")
        self.soft_html_path = os.path.join(BASE_DIR, "web", "templates", "default", "soft.html")
        self.files_html_path = os.path.join(BASE_DIR, "web", "templates", "default", "files.html")

    def test_01_file_encoding_and_lf(self):
        """测试 1: 确保所有修改文件均为 UTF-8 (无 BOM) 且使用 LF 换行符"""
        for file_path in [self.site_css_path, self.ensite_css_path, self.soft_html_path]:
            with open(file_path, "rb") as f:
                content = f.read()
                self.assertFalse(content.startswith(b"\xef\xbb\xbf"), f"{file_path} 含有 UTF-8 BOM 头！")
                self.assertNotIn(b"\r\n", content, f"{file_path} 含有 CRLF 换行符，必须为 LF！")

    def test_02_global_style_pollution_resolved(self):
        """测试 2: 验证 site.css 中的文件管理按钮样式已精确限定在 search-input-box，杜绝全局污染"""
        with open(self.site_css_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 确保不存在孤立且带有 !important 的全局选择器 ".search form button.ser-sub {"
        # 允许的是 ".search-input-box + button.ser-sub" 或 ".search form .search-input-box + button.ser-sub"
        pattern = r"\.search\s+form\s+button\.ser-sub\s*\{"
        self.assertIsNone(
            re.search(pattern, content),
            "site.css 中仍存在直接污染全局所有 search 表单按钮的宽泛选择器 .search form button.ser-sub {",
        )

        # 确保文件管理专属选择器依然存在
        self.assertIn(".search-input-box + button.ser-sub", content)

    def test_03_soft_html_structure(self):
        """测试 3: 验证 soft.html 中已应用 soft-search-box，且彻底清除了浮动与写死的内联 margin-top"""
        with open(self.soft_html_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证包含 soft-search-box 类
        self.assertIn("soft-search-box", content)

        # 验证输入框与按钮不再使用容易造成错位的内联 margin-top: 10px 与 pull-left
        self.assertNotIn('<input type="text" id="SearchValue" class="ser-text pull-left"', content)
        self.assertNotIn('<button type="button" class="ser-sub pull-left"', content)
        self.assertNotIn('style="margin-top: 10px;" onclick=\'getSList(1)\'', content)

    def test_04_soft_search_box_css_rules(self):
        """测试 4: 验证 site.css 和 ensite.css 均包含软件页面现代 Flex 居中、8px 间距、32px 等高与完整圆角样式"""
        for css_path in [self.site_css_path, self.ensite_css_path]:
            with open(css_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn(".soft-search-box form", content)
            self.assertIn("display: flex;", content)
            self.assertIn("align-items: center;", content)
            self.assertIn("gap: 8px;", content)

            # 验证输入框规则：32px 高度、圆角与过度
            self.assertIn(".soft-search-box .ser-text", content)
            self.assertIn("height: 32px", content)
            self.assertIn("border-radius: var(--radius-sm, 4px)", content)

            # 验证按钮规则：32px 高度、独立全圆角与 hover 效果
            self.assertIn(".soft-search-box button.ser-sub", content)
            self.assertIn("width: 36px", content)
            self.assertIn("cursor: pointer;", content)
            self.assertIn(".soft-search-box button.ser-sub:hover", content)
            self.assertIn("transform: translateY(-1px);", content)

            # 验证重置搜索按钮样式
            self.assertIn(".soft-search-box #resetSearchBtn", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
