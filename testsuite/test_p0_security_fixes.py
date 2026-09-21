# -*- coding: utf-8 -*-
"""
御风面板（BtSimple）P0 级安全加固与语法缺陷修复专项自动化测试套件
"""
import unittest
import os
import re
import ast

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, "web")
ADMIN_PLUGINS_INIT = os.path.join(WEB_DIR, "admin", "plugins", "__init__.py")
UTILS_PLUGIN_PY = os.path.join(WEB_DIR, "utils", "plugin.py")
UTILS_SITE_PY = os.path.join(WEB_DIR, "utils", "site.py")
ADMIN_INIT_PY = os.path.join(WEB_DIR, "admin", "__init__.py")
SETTING_SETTING_PY = os.path.join(WEB_DIR, "admin", "setting", "setting.py")

class TestP0SecurityFixes(unittest.TestCase):

    def test_01_encoding_and_line_endings(self):
        """测试 1: 验证所有修改的关键文件均为 UTF-8 无 BOM 且使用 LF 换行"""
        files_to_check = [
            ADMIN_PLUGINS_INIT,
            UTILS_PLUGIN_PY,
            UTILS_SITE_PY,
            ADMIN_INIT_PY,
            SETTING_SETTING_PY,
        ]
        for fpath in files_to_check:
            self.assertTrue(os.path.exists(fpath), f"File {fpath} not found")
            with open(fpath, "rb") as f:
                content = f.read()
            self.assertFalse(content.startswith(b"\xef\xbb\xbf"), f"File {fpath} has UTF-8 BOM")
            self.assertNotIn(b"\r\n", content, f"File {fpath} has CRLF line endings, must be LF")

    def test_02_plugins_file_path_traversal_defense(self):
        """测试 2: 验证 /plugins/file 具备严格的目录穿越防护（403拦截）"""
        with open(ADMIN_PLUGINS_INIT, "r", encoding="utf-8") as f:
            code = f.read()

        # 验证提取并校验了 name 与 f
        self.assertIn("def file():", code)
        self.assertIn("if not name or '/' in name or '\\\\' in name or '..' in name:", code)
        self.assertIn("target_file = os.path.abspath(os.path.join(plugin_dir, f))", code)
        self.assertIn("if not target_file.startswith(plugin_dir + os.sep) and target_file != plugin_dir:", code)
        self.assertIn("return Response('Forbidden', status=403)", code)

        # 逻辑模拟测试路径遍历校验算法
        plugin_base = os.path.abspath(os.path.join(ROOT_DIR, "plugins", "docker"))
        
        # 正常路径
        normal_file = os.path.abspath(os.path.join(plugin_base, "js/docker.js"))
        self.assertTrue(normal_file.startswith(plugin_base + os.sep))

        # 非法越界路径
        escaped_file1 = os.path.abspath(os.path.join(plugin_base, "../../../../etc/passwd"))
        self.assertFalse(escaped_file1.startswith(plugin_base + os.sep))

        escaped_file2 = os.path.abspath(os.path.join(plugin_base, "..\\..\\config.py"))
        self.assertFalse(escaped_file2.startswith(plugin_base + os.sep))

    def test_03_plugin_callback_eval_abolished(self):
        """测试 3: 验证 plugin.callback 彻底废除 eval()，改用安全反射"""
        with open(UTILS_PLUGIN_PY, "r", encoding="utf-8") as f:
            code = f.read()

        # 语法树解析确保 plugin.py 内部无语法错误
        tree = ast.parse(code)
        
        # 校验 callback 函数定义
        self.assertIn("def callback(self, name, func,", code)
        
        # 确保整个 plugin.py 中不再存在 eval( 字符串
        self.assertNotIn("eval(", code, "plugin.py 中仍残留 eval() 调用，必须彻底废除！")

        # 确保包含安全标识符正则校验与 getattr 反射调用
        self.assertIn("re.match(r'^[a-zA-Z0-9_\\-]+$', name)", code)
        self.assertIn("re.match(r'^[a-zA-Z0-9_]+$', func)", code)
        self.assertIn("target_func = getattr(mod, func)", code)

    def test_04_site_py_makedirs_chmod_cleaned(self):
        """测试 4: 验证 site.py 中已彻底清除 ' && chmod ' 语法缺陷"""
        with open(UTILS_SITE_PY, "r", encoding="utf-8") as f:
            code = f.read()

        # 校验不含任何 && chmod 字符串
        self.assertNotIn(" && chmod ", code, "site.py 中仍存在 ' && chmod ' 畸变拼接！")
        self.assertNotIn("&& chmod", code, "site.py 中仍存在 '&& chmod' 畸变拼接！")

        # 校验原生 setMode 调用存在
        self.assertIn("yf.makeDirs(vhost)", code)
        self.assertIn("yf.setMode(vhost, '755')", code)
        self.assertIn("yf.makeDirs(self.sslLetsDir)", code)
        self.assertIn("yf.setMode(self.sslLetsDir, '755')", code)

    def test_05_socketio_cors_hardened(self):
        """测试 5: 验证 WebSSH SocketIO 跨域通配符已收紧，防止 CSWSH"""
        with open(ADMIN_INIT_PY, "r", encoding="utf-8") as f:
            code = f.read()

        # 确保不在 SocketIO 中直接配置通配符 "*"
        self.assertNotIn('cors_allowed_origins="*"', code)
        self.assertNotIn("cors_allowed_origins='*'", code)

        # 确保存在来源验证函数 check_socketio_origin
        self.assertIn("def check_socketio_origin(origin):", code)
        self.assertIn("cors_allowed_origins=check_socketio_origin", code)

        # 逻辑模拟 origin 校验算法
        from urllib.parse import urlparse
        def mock_check_origin(origin, req_host, domain=""):
            if not origin:
                return True
            try:
                orig_netloc = urlparse(origin).netloc.split(':')[0]
                host = req_host.split(':')[0]
                if orig_netloc == host or orig_netloc in ('127.0.0.1', 'localhost'):
                    return True
                if domain and orig_netloc == domain:
                    return True
                return False
            except Exception:
                return False

        # 同源与本地通过
        self.assertTrue(mock_check_origin("http://127.0.0.1:7200", "127.0.0.1:7200"))
        self.assertTrue(mock_check_origin("http://localhost:7200", "127.0.0.1:7200"))
        self.assertTrue(mock_check_origin("https://panel.example.com", "panel.example.com", "panel.example.com"))
        self.assertTrue(mock_check_origin("", "127.0.0.1:7200"))

        # 跨站恶意源拒绝
        self.assertFalse(mock_check_origin("http://attacker-evil.com", "127.0.0.1:7200"))
        self.assertFalse(mock_check_origin("https://phishing.site", "panel.example.com", "panel.example.com"))

    def test_06_set_language_permission_isolation(self):
        """测试 6: 验证 /set_language 增加 isLogined() 校验，未登录禁止修改服务端全局配置"""
        with open(SETTING_SETTING_PY, "r", encoding="utf-8") as f:
            code = f.read()

        self.assertIn("def set_language():", code)
        self.assertIn("from admin.common import isLogined", code)
        self.assertIn("if isLogined():", code)
        self.assertIn("lang_file = os.path.join(panel_dir, 'data/language.pl')", code)
        self.assertIn("response.set_cookie('yf_lang', norm_lang", code)

if __name__ == "__main__":
    unittest.main()
