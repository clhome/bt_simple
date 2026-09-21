# -*- coding: utf-8 -*-
import os
import sys
import json
import re
import types
import tempfile
import unittest
import subprocess
from unittest.mock import MagicMock

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(BASE_DIR, 'web'))

_orig_modules = {
    'flask': sys.modules.get('flask'),
    'werkzeug': sys.modules.get('werkzeug'),
    'werkzeug.utils': sys.modules.get('werkzeug.utils'),
    'admin': sys.modules.get('admin'),
    'admin.user_login_check': sys.modules.get('admin.user_login_check'),
    'core': sys.modules.get('core'),
    'core.yf': sys.modules.get('core.yf'),
    'utils': sys.modules.get('utils'),
    'utils.file': sys.modules.get('utils.file'),
    'thisdb': sys.modules.get('thisdb'),
}

# 为后端 files.py 注入标准库轻量 mock 环境（解耦宿主环境对第三方库的依赖）
class MockModule(types.ModuleType):
    def __getattr__(self, name):
        return MagicMock()

def mock_route(*args, **kwargs):
    def decorator(f):
        return f
    return decorator

mock_blueprint = MagicMock()
mock_blueprint.route = mock_route
mock_flask = MockModule('flask')
mock_flask.Blueprint = MagicMock(return_value=mock_blueprint)
mock_flask.request = MagicMock()
mock_flask.session = {}
sys.modules['flask'] = mock_flask

mock_werkzeug = MockModule('werkzeug')
mock_werkzeug_utils = MockModule('werkzeug.utils')
mock_werkzeug_utils.secure_filename = lambda x: x
sys.modules['werkzeug'] = mock_werkzeug
sys.modules['werkzeug.utils'] = mock_werkzeug_utils

mock_admin = MockModule('admin')
mock_admin.session = {}
mock_user_check = MockModule('admin.user_login_check')
mock_user_check.panel_login_required = lambda f: f
sys.modules['admin'] = mock_admin
sys.modules['admin.user_login_check'] = mock_user_check

mock_core = MockModule('core')
mock_core_yf = MockModule('core.yf')
mock_core_yf.returnData = lambda status, msg, data=None: {'status': status, 'msg': msg, 'data': data}
mock_core_yf.isAppleSystem = lambda: False
mock_core.yf = mock_core_yf
sys.modules['core'] = mock_core
sys.modules['core.yf'] = mock_core_yf

mock_utils = types.ModuleType('utils')
mock_utils_file = types.ModuleType('utils.file')
sys.modules['utils'] = mock_utils
sys.modules['utils.file'] = mock_utils_file
mock_thisdb = types.ModuleType('thisdb')
sys.modules['thisdb'] = mock_thisdb

import importlib.util
files_path = os.path.join(BASE_DIR, 'web/admin/files/files.py')
spec = importlib.util.spec_from_file_location("files_route", files_path)
files_route = importlib.util.module_from_spec(spec)
sys.modules['admin.files.files'] = files_route
spec.loader.exec_module(files_route)

class TestPasteOverwriteCompare(unittest.TestCase):
    """粘贴覆盖新旧大小比对与按钮间距美化优化专项测试套件"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='test_paste_compare_')
        self.src_dir = os.path.join(self.test_dir, 'src')
        self.dst_dir = os.path.join(self.test_dir, 'dst')
        os.makedirs(self.src_dir, exist_ok=True)
        os.makedirs(self.dst_dir, exist_ok=True)

        # 创建目标旧文件 (200KB) 与来源新文件 (501KB)
        self.old_file = os.path.join(self.dst_dir, '1.txt')
        self.new_file = os.path.join(self.src_dir, '1.txt')
        with open(self.old_file, 'wb') as f:
            f.write(b'A' * (200 * 1024))
        with open(self.new_file, 'wb') as f:
            f.write(b'B' * (501 * 1024))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_backend_check_exists_files_single(self):
        """验证后端 check_exists_files 在单文件模式下返回 size 与 new_size 真实业务逻辑"""
        form_data = {
            'dfile': self.dst_dir,
            'filename': '1.txt',
            'sfile': self.new_file
        }
        files_route.request.form.get = lambda k, d='': form_data.get(k, d)

        res = files_route.check_exists_files()
        self.assertTrue(res.get('status'))
        data = res.get('data', [])
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['filename'], '1.txt')
        self.assertEqual(data[0]['size'], 200 * 1024)
        self.assertEqual(data[0]['new_size'], 501 * 1024)
        self.assertTrue(len(data[0].get('mtime', '')) > 0)
        self.assertTrue(len(data[0].get('new_mtime', '')) > 0)

    def test_02_backend_check_exists_files_batch(self):
        """验证后端 check_exists_files 在批量模式下从 session 读取并返回 new_size 真实业务逻辑"""
        files_route.session = {
            'selected': {
                'path': self.src_dir,
                'data': json.dumps(['1.txt'])
            }
        }
        form_data = {
            'dfile': self.dst_dir,
            'filename': '',
            'sfile': ''
        }
        files_route.request.form.get = lambda k, d='': form_data.get(k, d)

        res = files_route.check_exists_files()
        self.assertTrue(res.get('status'))
        data = res.get('data', [])
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['filename'], '1.txt')
        self.assertEqual(data[0]['size'], 200 * 1024)
        self.assertEqual(data[0]['new_size'], 501 * 1024)

    def test_03_frontend_render_overwrite_html_logic(self):
        """验证前端 renderFileOverwriteHtml 产生的新旧大小对比结构与样式"""
        files_js_path = os.path.join(BASE_DIR, 'web/static/app/files.js')
        with open(files_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('function renderFileOverwriteHtml(result)', content)
        self.assertIn('&lt;=', content)
        self.assertIn('old_file_size', content)
        self.assertIn('new_file_size', content)
        self.assertIn('size_compare', content)
        self.assertIn('glyphicon-exclamation-sign', content)
        self.assertIn('Math.min(540', content)

    def test_04_node_runtime_overwrite_html_output(self):
        """使用 Node.js 运行 renderFileOverwriteHtml，断言输出符合 200KB <= 501KB 比对语义"""
        chk_script = os.path.join(BASE_DIR, 'test/check_overwrite_render.js')
        res = subprocess.run(['node', chk_script], capture_output=True, text=True, cwd=BASE_DIR)
        self.assertEqual(res.returncode, 0, f"Node.js render test failed:\n{res.stderr}\n{res.stdout}")
        self.assertIn("PASS", res.stdout)

    def test_05_paste_btn_spacing_with_recycle_bin(self):
        """验证粘贴按钮与回收站间距已扩展为 >=20px"""
        files_js_path = os.path.join(BASE_DIR, 'web/static/app/files.js')
        with open(files_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        match = re.search(r'var gap = (\d+);', content)
        self.assertIsNotNone(match, "gap definition not found in showSeclect")
        gap_val = int(match.group(1))
        self.assertGreaterEqual(gap_val, 20, f"Gap should be >= 20px, got {gap_val}")

    def test_06_overwrite_i18n_all_languages(self):
        """验证 6 国语言包完整包含 overwrite_title、overwrite_tip、size_compare 等词条"""
        lang_dir = os.path.join(BASE_DIR, 'web/static/language')
        langs = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
        required_keys = ['overwrite_title', 'overwrite_tip', 'size_compare', 'old_file_size', 'new_file_size']

        for lang in langs:
            tpl_path = os.path.join(lang_dir, lang, 'template.json')
            with open(tpl_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            files_dict = data.get('files', {})
            for rk in required_keys:
                self.assertIn(rk, files_dict, f"[{lang}] template.json missing files.{rk}")

            lan_path = os.path.join(lang_dir, lang, 'lan.js')
            with open(lan_path, 'r', encoding='utf-8') as f:
                c = f.read()
            for rk in required_keys:
                self.assertIn(f'"{rk}":', c, f"[{lang}] lan.js missing '{rk}'")

def tearDownModule():
    for k, v in _orig_modules.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v

if __name__ == '__main__':
    unittest.main()
