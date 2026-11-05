# -*- coding: utf-8 -*-
"""
右上角检查更新弹窗与按钮安全自动化测试
"""

import os
import re
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class TestCheckUpdateDialog(unittest.TestCase):
    def test_index_js_check_update_no_undefined_button(self):
        """测试 checkUpdate() 中不存在 lan.public.know 导致的无效 undefined 按钮"""
        index_js_path = os.path.join(ROOT_DIR, "web", "static", "app", "index.js")
        with open(index_js_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. 绝不能出现已废弃或未定义的 lan.public.know 以及未收录的 update_get
        self.assertNotIn("lan.public.know", content, "index.js 不应出现未定义的 lan.public.know")
        self.assertNotIn("update_get", content, "index.js 不应出现六语言包未收录的 update_get 键")

        # 2. 提取 checkUpdate 函数定义
        match = re.search(r"function\s+checkUpdate\s*\(\)\s*\{([\s\S]*?)\n\}", content)
        self.assertTrue(match, "未能匹配到 checkUpdate 函数定义")
        func_body = match.group(1)

        # 校验 loading 提示使用正规六语言键
        self.assertIn("retrieving_updates_please_wait", func_body)

        # 3. 校验 status === false 时的弹窗配置：应为单按钮（关闭）且不再传双按钮
        self.assertNotIn("btn: [lan.public.know, lan.public.close]", func_body)
        self.assertIn("btn: [closeText]", func_body, "checkUpdate 应只提供单一关闭按钮")
        self.assertIn("layer.alert(", func_body, "无更新提示应使用 layer.alert 规范呈现")

    def test_public_js_localize_buttons_filters_invalid_items(self):
        """测试 public.js 中 localizeButtons 具备防御性过滤 undefined/null 能力"""
        public_js_path = os.path.join(ROOT_DIR, "web", "static", "app", "public.js")
        with open(public_js_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 确保 localizeButtons 函数包含过滤无效项目的逻辑
        self.assertIn("validButtons = btnArr.filter(", content)
        self.assertIn("item !== undefined && item !== null", content)


if __name__ == "__main__":
    unittest.main()

