# -*- coding: utf-8 -*-
"""
测试 JDK 管理器与 Python YF 插件修复、参数解析鲁棒化及多语言国际化
"""

import os
import sys
import json
import unittest

# 将项目目录加入 sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR = os.path.join(BASE_DIR, "web")
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import core.yf as yf
from core.i18n import t, SUPPORTED_CODES

class TestJdkAndHashFixI18n(unittest.TestCase):

    def setUp(self):
        # 确保语言环境初始化
        pass

    def test_jdk_get_args_robustness(self):
        """测试 JDK 插件 getArgs 对各种引号和格式的兼容性"""
        import plugins.jdk.index as jdk_mod

        # Case 1: 标准 JSON 字符串 (包含外层单引号)
        test_json = json.dumps({"version": "jdk-8", "download_url": "https://example.com/jdk8.tar.gz"})
        sys.argv = ['index.py', 'install_jdk', f"'{test_json}'"]
        parsed = jdk_mod.getArgs()
        self.assertEqual(parsed.get('version'), 'jdk-8')
        self.assertEqual(parsed.get('download_url'), 'https://example.com/jdk8.tar.gz')

        # Case 2: 标准 JSON 字符串 (包含外层双引号)
        sys.argv = ['index.py', 'install_jdk', f'"{test_json}"']
        parsed = jdk_mod.getArgs()
        self.assertEqual(parsed.get('version'), 'jdk-8')

        # Case 3: 标准 JSON 字符串 (无外层引号)
        sys.argv = ['index.py', 'install_jdk', test_json]
        parsed = jdk_mod.getArgs()
        self.assertEqual(parsed.get('version'), 'jdk-8')

        # Case 4: 空参数
        sys.argv = ['index.py', 'get_jdk_list']
        parsed = jdk_mod.getArgs()
        self.assertEqual(parsed, {})

        # Case 5: 多个参数片段拼接（含引号）
        sys.argv = ['index.py', 'install_jdk', "'{\"version\":", "\"jdk-17\",", "\"download_url\":", "\"https://test.com\"}'"]
        parsed = jdk_mod.getArgs()
        self.assertEqual(parsed.get('version'), 'jdk-17')

    def test_python_yf_get_args_robustness(self):
        """测试 Python YF 插件 getArgs 对各种引号和格式的兼容性"""
        import plugins.python_yf.index as py_mod

        # Case 1: 带单引号的 JSON
        test_json = json.dumps({"version": "3.12.0", "path": "/www/wwwroot/myproject"})
        sys.argv = ['index.py', 'create_venv', f"'{test_json}'"]
        parsed = py_mod.getArgs()
        self.assertEqual(parsed.get('version'), '3.12.0')
        self.assertEqual(parsed.get('path'), '/www/wwwroot/myproject')

        # Case 2: 无外层引号的 JSON
        sys.argv = ['index.py', 'create_venv', test_json]
        parsed = py_mod.getArgs()
        self.assertEqual(parsed.get('version'), '3.12.0')

        # Case 3: 空参数
        sys.argv = ['index.py', 'get_python_list']
        parsed = py_mod.getArgs()
        self.assertEqual(parsed, {})

    def test_jdk_i18n_messages_all_languages(self):
        """验证 JDK 模块的所有消息在 6 种语言下均能正确翻译，且不包含 k_ 哈希码"""
        keys_to_test = [
            "jdk.manage",
            "jdk.invalid_path",
            "jdk.path_not_exists",
            "jdk.verify_failed",
            "jdk.already_exists",
            "jdk.add_success",
            "jdk.param_error",
            "jdk.already_installed",
            "jdk.task_added",
            "jdk.in_use_error",
            "jdk.uninstall_success",
            "jdk.set_default_success",
            "jdk.type_panel",
            "jdk.type_custom",
            "jdk.type_sys",
            "jdk.sys_default",
            "jdk.is_default",
            "jdk.set_as_default",
            "jdk.installing",
            "jdk.sys_built_in",
            "jdk.remove_record",
            "jdk.add_custom",
            "jdk.th_version",
            "jdk.th_path"
        ]

        for lang in SUPPORTED_CODES:
            for k in keys_to_test:
                translated = t(k, lang=lang)
                self.assertIsNotNone(translated, f"Key {k} should have translation in {lang}")
                self.assertNotEqual(translated, k, f"Key {k} should not fallback to key name in {lang}")
                self.assertFalse(translated.startswith("k_"), f"Translation '{translated}' should not be a hash code")

    def test_python_yf_i18n_messages_all_languages(self):
        """验证 Python YF 模块的所有消息在 6 种语言下均能正确翻译"""
        keys_to_test = [
            "python_yf.uv_not_found",
            "python_yf.specify_install_ver",
            "python_yf.install_task_added",
            "python_yf.specify_uninstall_ver",
            "python_yf.uninstall_success",
            "python_yf.specify_ver_path",
            "python_yf.venv_create_success",
            "python_yf.param_error",
            "python_yf.del_success",
            "python_yf.venv_not_exists"
        ]

        for lang in SUPPORTED_CODES:
            for k in keys_to_test:
                translated = t(k, lang=lang)
                self.assertIsNotNone(translated, f"Key {k} should have translation in {lang}")
                self.assertNotEqual(translated, k, f"Key {k} should not fallback to key name in {lang}")
                self.assertFalse(translated.startswith("k_"), f"Translation '{translated}' should not be a hash code")

    def test_jdk_plugin_returns_no_hash_codes(self):
        """验证 JDK 插件执行方法的返回值中绝对不含 k_ 哈希码"""
        import plugins.jdk.index as jdk_mod
        main = jdk_mod.jdk_main()

        # 测试缺少参数时返回
        res_json = main.install_jdk({})
        res = json.loads(res_json)
        self.assertFalse(res['status'])
        self.assertNotIn("k_bff0e837", res['msg'])
        self.assertIn("参数", res['msg'])

        # 测试添加自定义非法路径
        res_json = main.add_custom_jdk({"path": "/invalid/path/java"})
        res = json.loads(res_json)
        self.assertFalse(res['status'])
        self.assertNotIn("k_8130fc6a", res['msg'])

        # 测试设置不存在的路径为默认
        res_json = main.set_default_jdk({"path": "/nonexistent/bin/java"})
        res = json.loads(res_json)
        self.assertFalse(res['status'])
        self.assertNotIn("k_a5d10c9a", res['msg'])

    def test_frontend_index_html_args_fix(self):
        """验证前端 index.html 中的传参格式无单引号嵌套"""
        html_path = os.path.join(BASE_DIR, "plugins", "jdk", "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 确保不存在 args: "'" + JSON.stringify
        self.assertNotIn("args: \"'\" + JSON.stringify", content)
        self.assertNotIn("args: '\\'' + JSON.stringify", content)
        # 确保使用了多语言函数
        self.assertIn("jdk.manage", content)
        self.assertIn("jdk.set_as_default", content)

if __name__ == "__main__":
    unittest.main()
