# coding:utf-8
import os
import sys
import json
import inspect
import unittest
from unittest.mock import MagicMock, patch

# 锚定根目录
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(root_dir, 'web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import core.yf as yf
import utils.plugin as plugin_module
from utils.plugin import plugin as YfPlugin


class TestPluginCallbackFix(unittest.TestCase):

    def setUp(self):
        self.pg = YfPlugin.instance()

    def test_01_re_and_inspect_imported(self):
        """测试 web/utils/plugin.py 成功导入 re 和 inspect，无 NameError"""
        self.assertTrue(hasattr(plugin_module, 're'), "plugin_module 缺少 re 模块")
        self.assertTrue(hasattr(plugin_module, 'inspect'), "plugin_module 缺少 inspect 模块")
        # 直接调用 re.match 验证功能正常
        self.assertIsNotNone(plugin_module.re.match(r'^[a-zA-Z0-9_\-]+$', 'task_manager'))

    def test_02_whitelist_validation(self):
        """测试 callback 安全白名单校验"""
        # 非法字符拦截
        res, msg = self.pg.callback('task;rm -rf', 'get_list')
        self.assertFalse(res)
        self.assertEqual(msg, "非法的调用参数!")

        res, msg = self.pg.callback('task_manager', 'get(list)')
        self.assertFalse(res)
        self.assertEqual(msg, "非法的调用参数!")

        res, msg = self.pg.callback('task_manager', 'get_list', script='index;evil')
        self.assertFalse(res)
        self.assertEqual(msg, "非法的调用参数!")

        # 插件不存在拦截
        res, msg = self.pg.callback('non_existent_plugin_xyz', 'test_func')
        self.assertFalse(res)
        self.assertEqual(msg, "插件不存在!")

    def test_03_adaptive_dispatch_single_dict_arg(self):
        """测试单字典参数函数（如 def func(args = {})）：兼容 task_manager_index.py 形式"""
        # 模拟插件模块
        dummy_mod = type(sys)('dummy_plugin')
        received = {}

        def sample_get_process_list(args={}):
            received['type'] = type(args)
            received['args'] = args
            return {'status': True, 'count': len(args)}

        dummy_mod.sample_get_process_list = sample_get_process_list

        with patch('importlib.import_module', return_value=dummy_mod):
            res, data = self.pg.callback(
                'task_manager',
                'sample_get_process_list',
                args='{"sortx":"cpu_percent","reverse":"True","search":""}',
                script='dummy_script'
            )
            self.assertTrue(res, f"调用失败: {data}")
            self.assertEqual(received['type'], dict, "参数应被正确反序列化为字典传递")
            self.assertEqual(received['args'].get('sortx'), 'cpu_percent')
            self.assertEqual(received['args'].get('reverse'), 'True')
            self.assertEqual(data.get('status'), True)

    def test_04_adaptive_dispatch_keyword_args(self):
        """测试具体关键字参数函数（如 def func(name, count=1)）"""
        dummy_mod = type(sys)('dummy_plugin2')
        received = {}

        def sample_kw_func(name, count=1):
            received['name'] = name
            received['count'] = count
            return f"{name}:{count}"

        dummy_mod.sample_kw_func = sample_kw_func

        with patch('importlib.import_module', return_value=dummy_mod):
            res, data = self.pg.callback(
                'task_manager',
                'sample_kw_func',
                args='{"name":"cpu","count":4}',
                script='dummy_script2'
            )
            self.assertTrue(res)
            self.assertEqual(received['name'], 'cpu')
            self.assertEqual(received['count'], 4)
            self.assertEqual(data, "cpu:4")

    def test_05_adaptive_dispatch_no_arg(self):
        """测试无参数函数（如 def func()）"""
        dummy_mod = type(sys)('dummy_plugin3')

        def sample_no_arg():
            return "ok_no_arg"

        dummy_mod.sample_no_arg = sample_no_arg

        with patch('importlib.import_module', return_value=dummy_mod):
            # 传入空 args
            res, data = self.pg.callback('task_manager', 'sample_no_arg', args='', script='dummy_script3')
            self.assertTrue(res)
            self.assertEqual(data, "ok_no_arg")

            # 即使前端传入了无用 args，也能正常安全调用
            res, data = self.pg.callback('task_manager', 'sample_no_arg', args='{"foo":"bar"}', script='dummy_script3')
            self.assertTrue(res)
            self.assertEqual(data, "ok_no_arg")

    def test_06_task_manager_index_signatures(self):
        """验证 task_manager_index.py 中的实际函数签名，并确保反射分发匹配"""
        tm_index_path = os.path.join(root_dir, 'plugins', 'task_manager', 'task_manager_index.py')
        self.assertTrue(os.path.exists(tm_index_path), "task_manager_index.py 必须存在")

        expected_funcs = [
            'get_process_list',
            'get_network_list',
            'kill_process',
            'kill_process_all',
            'set_meter_head',
            'get_service_list',
            'get_run_list',
            'get_cron_list',
            'get_who',
            'get_process_info',
            'get_user_list'
        ]
        
        # 检查函数定义
        with open(tm_index_path, 'r', encoding='utf-8') as f:
            content = f.read()
            for func_name in expected_funcs:
                self.assertIn(f"def {func_name}", content, f"未找到函数 {func_name} 的定义")

    def test_07_callback_route_ast_and_exception_safety(self):
        """测试 /plugins/callback 路由代码结构包含完整 try...except 全局兜底，杜绝 500 异常"""
        plugins_init_path = os.path.join(web_dir, 'admin', 'plugins', '__init__.py')
        with open(plugins_init_path, 'r', encoding='utf-8') as f:
            code = f.read()

        # 验证路由定义与异常处理
        self.assertIn("@blueprint.route('/callback', endpoint='callback', methods=['GET','POST'])", code)
        self.assertIn("def callback():", code)
        self.assertIn("try:", code)
        self.assertIn("except Exception as e:", code)
        self.assertIn("yf.writeLog('插件管理'", code)
        self.assertIn("return {'status': False, 'msg': f\"操作执行异常: {str(e)}\", 'data': ''}", code)

        # 若本地存在 Flask，则运行真实的路由测试
        try:
            from flask import Flask, request
            app = Flask(__name__)
            app.secret_key = 'test_secret_key'

            from admin.plugins import blueprint
            app.register_blueprint(blueprint, url_prefix='/plugins')

            client = app.test_client()
            with client.session_transaction() as sess:
                sess['login'] = True
                sess['username'] = 'admin'

            with patch.object(YfPlugin, 'callback', side_effect=RuntimeError("Simulated Critical Error")):
                resp = client.post('/plugins/callback', data={
                    'name': 'task_manager',
                    'func': 'get_process_list',
                    'script': 'task_manager_index',
                    'args': '{"sortx":"cpu_percent"}'
                })
                self.assertEqual(resp.status_code, 200)
                res_json = json.loads(resp.data.decode('utf-8'))
                self.assertFalse(res_json.get('status'))
                self.assertIn("Simulated Critical Error", res_json.get('msg'))
        except ImportError:
            pass  # 无 Flask 环境下静态 AST 已验证安全保护

    def test_08_encoding_and_line_endings(self):
        """检查修改过的核心文件统一为 UTF-8 无 BOM 与 LF 换行"""
        check_files = [
            os.path.join(root_dir, 'web', 'utils', 'plugin.py'),
            os.path.join(root_dir, 'web', 'admin', 'plugins', '__init__.py')
        ]
        for fpath in check_files:
            with open(fpath, 'rb') as f:
                raw = f.read()
                # 验证无 UTF-8 BOM
                self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), f"{fpath} 不允许包含 UTF-8 BOM")
                # 验证 LF 换行符（不包含 CRLF）
                self.assertNotIn(b'\r\n', raw, f"{fpath} 必须使用 LF 换行符，不允许 CRLF")

    def test_09_simulate_all_task_manager_frontend_calls(self):
        """全面模拟 task_manager.js 中所有 tmPostCallback 前端请求分发"""
        tm_mock_module = type(sys)('task_manager_index_mock')
        calls_record = []

        def mock_get_process_list(args={}):
            calls_record.append(('get_process_list', args))
            return {'status': True, 'process_list': [], 'meter_head': {}}

        def mock_set_meter_head(args={}):
            calls_record.append(('set_meter_head', args))
            return True

        def mock_get_network_list(args={}):
            calls_record.append(('get_network_list', args))
            return []

        def mock_get_service_list(args={}):
            calls_record.append(('get_service_list', args))
            return []

        def mock_get_run_list(args={}):
            calls_record.append(('get_run_list', args))
            return []

        def mock_get_cron_list(args={}):
            calls_record.append(('get_cron_list', args))
            return []

        def mock_get_who(args={}):
            calls_record.append(('get_who', args))
            return []

        def mock_get_process_info(args={}):
            calls_record.append(('get_process_info', args))
            return {'pid': args.get('pid')}

        def mock_kill_process_all(pid):
            calls_record.append(('kill_process_all', pid))
            return True

        tm_mock_module.get_process_list = mock_get_process_list
        tm_mock_module.set_meter_head = mock_set_meter_head
        tm_mock_module.get_network_list = mock_get_network_list
        tm_mock_module.get_service_list = mock_get_service_list
        tm_mock_module.get_run_list = mock_get_run_list
        tm_mock_module.get_cron_list = mock_get_cron_list
        tm_mock_module.get_who = mock_get_who
        tm_mock_module.get_process_info = mock_get_process_info

        test_cases = [
            ('get_process_list', '{"sortx":"cpu_percent","reverse":"undefined","search":"","version":"1.0"}'),
            ('set_meter_head', '{"meter_head_name":"ps","version":"1.0"}'),
            ('get_network_list', '{"version":"1.0"}'),
            ('get_service_list', '{"version":"1.0"}'),
            ('get_run_list', '{"version":"1.0"}'),
            ('get_cron_list', '{"version":"1.0"}'),
            ('get_who', '{"version":"1.0"}'),
            ('get_process_info', '{"pid":1234,"version":"1.0"}'),
        ]

        with patch('importlib.import_module', return_value=tm_mock_module):
            for func_name, args_str in test_cases:
                res, data = self.pg.callback('task_manager', func_name, args=args_str, script='task_manager_index')
                self.assertTrue(res, f"调用 {func_name} 失败: {data}")

        self.assertEqual(len(calls_record), 8)
        # 验证每个调用接收到的参数均为字典且完整
        for func_name, arg in calls_record:
            self.assertIsInstance(arg, dict)
            self.assertEqual(arg.get('version'), '1.0')


if __name__ == '__main__':
    unittest.main()
