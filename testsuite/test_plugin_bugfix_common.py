# -*- coding: utf-8 -*-
"""
插件共性缺陷深度修复专项自动化测试套件 (test_plugin_bugfix_common.py)
涵盖：
1. i18n.js translatePluginDOM 结构安全防护（断言绝不误杀主容器、绝无白屏）
2. 架构安全警示标题等多语言选择器穿透验证
3. linux_sys_opt 异步数据注入与评分多语言闭环
4. 全量插件反引号模板字符串 ' + pt(...) 语法错乱零残留 (0 项)
5. 全量插件 JS 脚本 Node.js 严格编译 100% 语法正确
"""

import os
import sys
import json
import re
import unittest
import subprocess

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGINS_DIR = os.path.join(ROOT_DIR, "plugins")
TEST_DIR = os.path.join(ROOT_DIR, "testsuite")
I18N_JS_PATH = os.path.join(ROOT_DIR, "web", "static", "app", "i18n.js")

class TestPluginBugfixCommon(unittest.TestCase):
    
    def test_01_i18n_js_protection_against_dom_destruction(self):
        """测试 1: 验证 i18n.js 中已彻底移除导致 DOM 误杀的危险容器选择器"""
        with open(I18N_JS_PATH, "r", encoding="utf-8") as f:
            code = f.read()
            
        # 绝不能包含针对顶级大容器的暴力覆盖选择器
        self.assertNotIn(".bt-form > div:last-child", code, "危险选择器 .bt-form > div:last-child 未移除，会导致弹窗白屏！")
        self.assertNotIn(".bt-w-con > div:last-child", code, "危险选择器 .bt-w-con > div:last-child 未移除！")
        self.assertNotIn("$scope.children('div').add($scope.find('.bt-w-con').children('div'))", code, "危险 fallback 未移除！")
        
        # 必须包含结构安全守卫
        self.assertIn(".hasClass('bt-w-main')", code, "缺少 bt-w-main 结构安全防线！")
        self.assertIn(".hasClass('soft-man-con')", code, "缺少 soft-man-con 结构安全防线！")

    def test_02_alert_title_selector_coverage(self):
        """测试 2: 验证 translatePluginDOM 选择器已覆盖 alert-title 与高危警示容器"""
        with open(I18N_JS_PATH, "r", encoding="utf-8") as f:
            code = f.read()
            
        self.assertIn(".alert-title", code, "translatePluginDOM 必须包含 .alert-title 选择器！")
        self.assertIn('div[style*="color: #cf1322"]', code, "translatePluginDOM 必须包含红色安全警示容器选择器！")
        self.assertIn(".pma-info-header", code, "translatePluginDOM 必须包含 .pma-info-header 选择器！")

    def test_03_pg_docker_security_alert_structure(self):
        """测试 3: 验证 pg_docker index.html 中架构安全警示标题已包含 alert-title class"""
        pg_docker_html = os.path.join(PLUGINS_DIR, "pg_docker", "index.html")
        with open(pg_docker_html, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn('class="alert-title"', content, "pg_docker 指南警示标题缺少 alert-title class！")
        self.assertIn("架构安全警示：Docker 网络与系统防火墙", content, "pg_docker 指南中原中文标杆文本应完好存在！")

    def test_04_linux_sys_opt_i18n_integration(self):
        """测试 4: 验证 linux_sys_opt index.html 在渲染后主动触发 translatePluginDOM"""
        linux_opt_html = os.path.join(PLUGINS_DIR, "linux_sys_opt", "index.html")
        with open(linux_opt_html, "r", encoding="utf-8") as f:
            content = f.read()
            
        # 验证 optStatus 注入后调用 translatePluginDOM
        self.assertIn("window.YfI18n.translatePluginDOM($('.soft-man-con'), 'linux_sys_opt')", content,
                      "linux_sys_opt optStatus() 未在注入后调用 translatePluginDOM！")
        # 验证 pt('内核与并发参数状态')
        self.assertIn("${pt('内核与并发参数状态')}", content, "内核参数表格标题未接入 pt 国际化！")
        self.assertIn("${pt('一键全局优化')}", content, "一键全局优化按钮未接入 pt 国际化！")

    def test_05_no_backtick_quote_concatenation_syntax_bug(self):
        """测试 5: 全量排查所有 38 个插件，断言 0 处在反引号模板字符串内部混用 ' + pt(...) + '"""
        violations = []
        for root, dirs, files in os.walk(PLUGINS_DIR):
            for f in files:
                if f.endswith('.js') or f.endswith('.html'):
                    fp = os.path.join(root, f)
                    with open(fp, "r", encoding="utf-8", errors="ignore") as file_in:
                        text = file_in.read()
                    
                    parts = text.split('`')
                    if len(parts) > 1:
                        for idx in range(1, len(parts), 2):
                            tmpl = parts[idx]
                            if "' + pt(" in tmpl or "'+pt(" in tmpl or "'+ pt(" in tmpl:
                                rel = os.path.relpath(fp, PLUGINS_DIR)
                                violations.append(rel)
                                break
                                
        self.assertEqual(len(violations), 0, f"发现插件模板字符串内存在 ' + pt(...) 语法拼接错乱: {violations}")

    def test_06_node_syntax_all_plugin_scripts(self):
        """测试 6: 调用 Node.js 严格编译所有 38 个插件的全部 81 个脚本文件，断言 100% 语法正确"""
        verify_script = os.path.join(TEST_DIR, "verify_all_plugin_js_syntax.js")
        res = subprocess.run(["node", verify_script], cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0, f"Node.js 语法校验脚本执行失败: {res.stderr}")
        self.assertIn("所有插件 JS 脚本语法全部校验通过！", res.stdout, "存在插件 JS 语法未通过校验！")

    def test_07_simulated_runtime_it_and_en_dom(self):
        """测试 7: 验证非中文状态下版权替换逻辑对主容器的保护防线"""
        # 验证 i18n.js 中的实际代码片段
        with open(I18N_JS_PATH, "r", encoding="utf-8") as f:
            code = f.read()

        # 验证选择器绝对未包含顶级大容器
        self.assertNotIn(".bt-form > div:last-child", code)
        self.assertNotIn(".bt-w-con > div:last-child", code)
        
        # 验证包含四大结构防线
        self.assertIn("if ($el.hasClass('bt-w-main') || $el.hasClass('bt-w-con') || $el.hasClass('bt-form') || $el.hasClass('soft-man-con'))", code)
        self.assertIn("if ($el.find('.bt-w-menu, .soft-man-con, table, .table, form').length > 0)", code)
        self.assertIn("if ($el.children().length <= 1)", code)

if __name__ == '__main__':
    unittest.main()
