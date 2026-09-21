# -*- coding: utf-8 -*-
"""
测试用例：验证面板设置中语言配置的精简（方案B）
- 确保 setting.html 移除了冗余的语言表单项
- 确保 config.js 移除了 savePanelLanguage 死代码
- 确保 layout.html 和 login.html 中的全局快捷语言切换保留且完好
"""

import unittest
import os
import re

class TestSettingLanguageRemoval(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    def test_setting_html_no_language_dropdown(self):
        """验证 setting.html 中已移除 panelLanguageSelect 及相关保存项"""
        setting_file = os.path.join(self.base_dir, 'web/templates/default/setting.html')
        with open(setting_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertNotIn('panelLanguageSelect', content, "setting.html 中不应再包含 panelLanguageSelect 下拉框")
        self.assertNotIn('savePanelLanguage()', content, "setting.html 中不应再包含 savePanelLanguage() 按钮")

    def test_config_js_no_save_panel_language(self):
        """验证 config.js 中已清理 savePanelLanguage 函数"""
        config_js_file = os.path.join(self.base_dir, 'web/static/app/config.js')
        with open(config_js_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertNotIn('function savePanelLanguage', content, "config.js 中不应再包含 savePanelLanguage 函数定义")

    def test_global_language_switchers_retained(self):
        """验证 layout.html 与 login.html 中的全局快捷语言切换保留且正常"""
        layout_file = os.path.join(self.base_dir, 'web/templates/default/layout.html')
        login_file = os.path.join(self.base_dir, 'web/templates/default/login.html')

        with open(layout_file, 'r', encoding='utf-8') as f:
            layout_content = f.read()
        with open(login_file, 'r', encoding='utf-8') as f:
            login_content = f.read()

        self.assertIn('YfI18n.setLanguage', layout_content, "layout.html 必须保留 YfI18n.setLanguage 快捷切换")
        self.assertIn('panel-lang-switcher', layout_content, "layout.html 必须保留 panel-lang-switcher 侧边栏结构")
        self.assertIn('YfI18n.setLanguage', login_content, "login.html 必须保留 YfI18n.setLanguage 快捷切换")

if __name__ == '__main__':
    unittest.main()
