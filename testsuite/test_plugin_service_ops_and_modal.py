# -*- coding: utf-8 -*-
import unittest
import os
import sys
import json
import re

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, 'web')
sys.path.insert(0, WEB_DIR)
sys.path.insert(0, ROOT_DIR)

from unittest.mock import MagicMock
for mod in ['flask_compress', 'flask_socketio', 'flask_caching', 'flask_session', 'psutil']:
    sys.modules.setdefault(mod, MagicMock())

user_check_mock = MagicMock()
user_check_mock.panel_login_required = lambda f: f
sys.modules['admin.user_login_check'] = user_check_mock

import core.yf as yf
import thisdb
from utils.plugin import plugin as YfPlugin


class TestPluginServiceOpsAndModal(unittest.TestCase):

    def setUp(self):
        self.langs = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
        self.keys = [
            'stop_1', 'start_1', 'restart_2', 'overload', 'force_stop_kill',
            'are_you_sure_you', 'serving_please_wait_moment', 'service_has', 'service_failed'
        ]

    def test_01_all_languages_contain_service_keys(self):
        """测试 6 国语言包中 public 命名空间下均包含全部 9 个服务操作词条"""
        for lang in self.langs:
            lan_file = os.path.join(WEB_DIR, 'static', 'language', lang, 'lan.js')
            tpl_file = os.path.join(WEB_DIR, 'static', 'language', lang, 'template.json')

            self.assertTrue(os.path.exists(lan_file), f"{lan_file} must exist")
            self.assertTrue(os.path.exists(tpl_file), f"{tpl_file} must exist")

            # 验证 template.json
            with open(tpl_file, 'r', encoding='utf-8') as f:
                tpl_data = json.load(f)
            self.assertIn('public', tpl_data, f"{lang} template.json must have 'public' block")
            for k in self.keys:
                self.assertIn(k, tpl_data['public'], f"{lang} template.json public missing {k}")
                self.assertTrue(len(tpl_data['public'][k]) > 0, f"{lang} template.json public[{k}] cannot be empty")

            # 验证 lan.js
            with open(lan_file, 'r', encoding='utf-8') as f:
                lan_content = f.read()
            self.assertIn('"public": {', lan_content, f"{lang} lan.js must have 'public' object")
            pub_idx = lan_content.find('"public": {')
            pub_block = lan_content[pub_idx:]
            for k in self.keys:
                self.assertIn(f'"{k}"', pub_block, f"{lang} lan.js public missing key \"{k}\"")

    def test_02_public_js_plugin_op_service_fallback_and_layout(self):
        """测试 web/static/app/public.js 中 pluginOpService 的健壮性与排版防溢出"""
        pub_js = os.path.join(WEB_DIR, 'static', 'app', 'public.js')
        with open(pub_js, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查是否包含 opNameMap 及中文保底
        self.assertIn("opNameMap", content)
        self.assertIn("t('public.stop_1', '停止')", content)
        self.assertIn("t('public.start_1', '启动')", content)
        self.assertIn("t('public.restart_2', '重启')", content)
        self.assertIn("t('public.overload', '重载')", content)
        self.assertIn("t('public.force_stop_kill', '强制停止(kill)')", content)

        # 检查确认弹窗中文保底与自适应防滚动条容器
        self.assertIn("t('public.are_you_sure_you', '您真的要{1}{2}{3}服务吗？')", content)
        self.assertIn("area: '420px'", content)
        self.assertIn("confirmHtml", content)

        # 检查失败分支 icon: 2
        self.assertIn("t('public.operation_error', '操作异常!')", content)
        self.assertIn("icon: 2", content)

    def test_03_run_by_cache_robustness_against_none_or_malformed_data(self):
        """测试 runByCache 在配置缓存为 None、字符串、损坏 JSON 等极端情况下的容错能力"""
        pg = YfPlugin.instance()

        # 测试数据类型为 None、非字典时不会抛出 TypeError
        cache_key = pg._plugin__plugin_status_cachekey

        test_cases = [None, "", "not-a-json", [], 123, {"op_waf": "start"}]
        for bad_val in test_cases:
            try:
                # 手动覆盖 option 缓存
                if bad_val is None or bad_val == "":
                    thisdb.setOption(cache_key, "null")
                elif isinstance(bad_val, str):
                    thisdb.setOption(cache_key, bad_val)
                else:
                    thisdb.setOption(cache_key, json.dumps(bad_val))

                # 执行 runByCache 绝不可崩溃
                pg.runByCache('op_waf', 'stop', '1.5')
                pg.runByCache('openresty', 'restart', '1.21')
            except Exception as e:
                self.fail(f"runByCache crashed with input {bad_val}: {e}")

    def test_04_pg_run_robustness(self):
        """测试 pg.run 面对异常插件与脚本时的安全返回"""
        pg = YfPlugin.instance()

        # 测试不存在的插件脚本
        res = pg.run('non_existent_plugin_xyz', 'stop')
        self.assertIsInstance(res, tuple)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0], '')
        self.assertIn('不存在', res[1])

    def test_05_route_run_response_structure_and_error_handling(self):
        """测试 plugins/__init__.py 的 /run 路由逻辑健壮性与返回结构"""
        import importlib.util
        from flask import Flask, request

        plugin_init_path = os.path.join(WEB_DIR, 'admin', 'plugins', '__init__.py')
        spec = importlib.util.spec_from_file_location("plugins_blueprint_test", plugin_init_path)
        plugins_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugins_mod)
        run_view_func = plugins_mod.run

        app = Flask(__name__)
        app.secret_key = 'test-secret'

        with app.test_request_context('/plugins/run', method='POST', data={'name': 'non_existent_xyz', 'func': 'stop'}):
            try:
                # 模拟登录态
                from flask import session
                session['login'] = True
                res = run_view_func()
                self.assertIsInstance(res, dict)
                self.assertIn('status', res)
                self.assertIn('msg', res)
                self.assertIn('data', res)
                self.assertFalse(res['status'])
            except Exception as e:
                self.fail(f"/plugins/run view raised unhandled exception: {e}")

    def test_06_route_run_stderr_warning_with_ok_and_exception_handling(self):
        """测试 /run 路由在底层有警告但返回 ok 时判定成功，以及全局捕获异常永不 500"""
        import importlib.util
        from flask import Flask, session
        from unittest.mock import patch

        plugin_init_path = os.path.join(WEB_DIR, 'admin', 'plugins', '__init__.py')
        spec = importlib.util.spec_from_file_location("plugins_blueprint_test2", plugin_init_path)
        plugins_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugins_mod)
        run_view_func = plugins_mod.run

        app = Flask(__name__)
        app.secret_key = 'test-secret'

        # 1. 模拟底层有警告但输出 'ok'
        with app.test_request_context('/plugins/run', method='POST', data={'name': 'op_waf', 'func': 'stop'}):
            session['login'] = True
            with patch.object(YfPlugin, 'run', return_value=('ok', 'DeprecationWarning: something')):
                res = run_view_func()
                self.assertTrue(res['status'])
                self.assertEqual(res['data'], 'ok')

        # 2. 模拟底层抛出严重异常
        with app.test_request_context('/plugins/run', method='POST', data={'name': 'op_waf', 'func': 'restart'}):
            session['login'] = True
            with patch.object(YfPlugin, 'run', side_effect=RuntimeError("Subprocess failed unexpectedly")):
                res = run_view_func()
                self.assertIsInstance(res, dict)
                self.assertFalse(res['status'])
                self.assertIn('Subprocess failed unexpectedly', res['msg'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
