# coding: utf-8
"""
请求安全与错误面加固回归（G3 / G5 / H3）

覆盖三件事：

G3  CSRF 与「用 GET 改状态」
    * 判定逻辑的真值表（token × referer × 豁免 × API 头）
    * 状态变更端点必须 POST-only，且不得从 request.args 取参
    * GET 注销已移除

G5  错误面收口
    * 异常原文不得回前端（只给追踪号）
    * 存在 500 / 未捕获异常兜底，且不回显堆栈

H3  代码质量棘轮
    * 棘轮脚本自证通过、基线存在、门禁已挂进 run_all.py
"""
import os
import subprocess
import sys
import unittest
from unittest import mock

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(project_root, 'web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.security import csrf_decision, extract_supplied_token  # noqa: E402


def _read(rel):
    with open(os.path.join(project_root, rel), 'r', encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


class CsrfDecisionTest(unittest.TestCase):
    """CSRF 判定真值表（纯函数，不起 Flask）。"""

    HOST = 'panel.example.com:7200'

    def _decide(self, **kw):
        args = dict(method='POST', path='/plugins/run', host=self.HOST,
                    referer='', origin='', token_expected='tok', token_supplied='')
        args.update(kw)
        return csrf_decision(**args)

    def test_01_safe_methods_always_pass(self):
        for method in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            allowed, reason = self._decide(method=method)
            self.assertTrue(allowed, method)
            self.assertEqual(reason, 'safe-method')

    def test_02_valid_token_passes_even_without_referer(self):
        """带合法 token 但无 Referer（隐私插件剥头）必须放行 —— 这正是本次要修好的场景。"""
        allowed, reason = self._decide(token_supplied='tok')
        self.assertTrue(allowed)
        self.assertEqual(reason, 'token-only')

    def test_03_referer_alone_still_passes(self):
        """零回归保证：今天能过的（Referer 正确）明天还能过。"""
        allowed, reason = self._decide(
            referer='https://%s/files' % self.HOST)
        self.assertTrue(allowed)
        self.assertEqual(reason, 'referer-only')

    def test_04_origin_alone_still_passes(self):
        allowed, _ = self._decide(origin='https://%s' % self.HOST)
        self.assertTrue(allowed)

    def test_05_no_proof_is_rejected(self):
        allowed, reason = self._decide()
        self.assertFalse(allowed)
        self.assertEqual(reason, 'no-proof')

    def test_06_wrong_token_and_wrong_referer_rejected(self):
        allowed, _ = self._decide(token_supplied='bad',
                                  referer='https://evil.example.com/x')
        self.assertFalse(allowed)

    def test_07_wrong_token_but_good_referer_still_passes(self):
        """OR 语义：token 错不影响 Referer 这条通路（保守、零回归）。"""
        allowed, reason = self._decide(
            token_supplied='bad', referer='https://%s/a' % self.HOST)
        self.assertTrue(allowed)
        self.assertEqual(reason, 'referer-only')

    def test_08_api_header_auth_exempt(self):
        allowed, reason = self._decide(has_app_id=True)
        self.assertTrue(allowed)
        self.assertEqual(reason, 'api-header-auth')

    def test_09_hook_and_acme_exempt(self):
        for path in ('/hook', '/.well-known/acme-challenge/x'):
            allowed, reason = self._decide(path=path)
            self.assertTrue(allowed, path)
            self.assertEqual(reason, 'exempt-path')

    def test_10_token_compare_is_constant_time_and_strict(self):
        """必须是全等比较：前缀/大小写不同都不能放过。"""
        for bad in ('to', 'tok ', 'TOK', 'tokx', ''):
            allowed, _ = self._decide(token_supplied=bad)
            self.assertFalse(allowed, '不该放行 %r' % bad)

    def test_11_extract_supplied_token_prefers_header(self):
        class H(dict):
            def get(self, k, d=''):
                return dict.get(self, k, d)
        self.assertEqual(extract_supplied_token(H({'X-CSRF-Token': 'a'}), {'csrf_token': 'b'}), 'a')
        self.assertEqual(extract_supplied_token(H(), {'csrf_token': 'b'}), 'b')
        self.assertEqual(extract_supplied_token(H(), {}), '')


class StateChangingRoutesTest(unittest.TestCase):

    def test_12_plugin_endpoints_are_post_only(self):
        text = _read('web/admin/plugins/__init__.py')
        for route in ("'/run', endpoint='run', methods=['POST']",
                      "'/callback', endpoint='callback', methods=['POST']",
                      "'/clear_cache', endpoint='clear_cache', methods=['POST']"):
            self.assertIn(route, text, '缺少 POST-only 路由：%s' % route)
        for bad in ("'/run', endpoint='run', methods=['GET','POST']",
                    "'/callback', endpoint='callback', methods=['GET','POST']",
                    "'/clear_cache', endpoint='clear_cache', methods=['POST', 'GET']"):
            self.assertNotIn(bad, text, '仍在开放 GET 改状态：%s' % bad)

    def test_13_no_args_based_state_change(self):
        """可改状态的端点不得从 query string 取参（否则 GET 即可触发）。"""
        text = _read('web/admin/plugins/__init__.py')
        for fn in ('def run():', 'def callback():'):
            start = text.index(fn)
            head = text[start:start + 700]
            self.assertNotIn("request.args.get('name'", head, '%s 仍从 args 取 name' % fn)
            self.assertNotIn("request.args.get('func'", head, '%s 仍从 args 取 func' % fn)
            self.assertNotIn("request.args.get('script'", head, '%s 仍从 args 取 script' % fn)

    def test_14_ssl_and_bookmark_state_routes_are_post_only(self):
        ssl_text = _read('web/admin/site/ssl.py')
        for ep in ('set_dnsapi', 'set_cert_to_site', 'remove_cert',
                   'http_to_https', 'close_to_https'):
            self.assertRegex(
                ssl_text,
                r"@blueprint\.route\('/%s',[^)]*methods=\['POST'\]\)" % ep,
                '%s 应为 POST-only' % ep)
        bookmark = _read('web/admin/setting/panel_bookmark.py')
        self.assertIn("endpoint='del_panel_info', methods=['POST']", bookmark)

    def test_15_login_get_signout_removed(self):
        text = _read('web/admin/dashboard/login.py')
        self.assertNotIn("request.args.get('signout'", text,
                         'GET 注销仍在（可被 CSRF 强制踢下线）')
        self.assertIn("'/do_signout'", text)
        # 前端也必须改成 POST
        js = _read('web/static/app/config.js')
        self.assertNotIn("/login?signout=True", js)
        self.assertIn("/do_signout", js)

    def test_16_csrf_wired_into_app(self):
        text = _read('web/admin/__init__.py')
        self.assertIn('from core.security import csrf_decision', text)
        self.assertIn("g.csrf_token", text)
        self.assertIn("session['csrf_token']", text)
        # 模板上下文要能拿到 token
        self.assertIn('csrf_token=getattr(g, \'csrf_token\', \'\')', text)

    def test_17_templates_carry_csrf_token(self):
        for tpl in ('web/templates/default/layout.html',
                    'web/templates/default/login.html'):
            text = _read(tpl)
            self.assertIn('name="csrf-token"', text, '%s 缺少 meta csrf-token' % tpl)
            self.assertIn('X-CSRF-Token', text, '%s 未注入 ajaxSetup' % tpl)


class ErrorSurfaceTest(unittest.TestCase):

    def test_18_user_safe_error_does_not_leak_internals(self):
        import core.yf as yf
        secret = '/www/server/yufeng_panel/data/panel.db'
        exc = RuntimeError('sqlite3.OperationalError: no such table: x at %s' % secret)
        with mock.patch.object(yf, 'writeFileLog', lambda *a, **k: None):
            msg = yf.userSafeError(exc)
        self.assertNotIn(secret, msg, '脱敏后仍泄露了内部路径')
        self.assertNotIn('sqlite3', msg, '脱敏后仍泄露了内部组件信息')
        self.assertIn('追踪号', msg, '应给出追踪号便于对账')

    def test_19_plugin_errors_are_sanitized(self):
        text = _read('web/admin/plugins/__init__.py')
        self.assertIn('yf.userSafeError(e)', text)
        self.assertNotIn('操作执行异常: {str(e)}', text)

    def test_20_500_handler_present_and_quiet(self):
        text = _read('web/admin/__init__.py')
        self.assertIn('@app.errorhandler(500)', text)
        self.assertIn('@app.errorhandler(Exception)', text)

        start = text.index('def internal_server_error')
        end = text.index('def unhandled_exception')
        body = text[start:end]
        # 真正的泄露途径是「把异常/堆栈插进响应体」，而不是注释里提到 traceback
        self.assertNotIn('traceback.format_exc', body, '兜底页不得回显堆栈')
        self.assertNotIn('format_exc()', body)
        html_start = body.index('html = (')
        html_literal = body[html_start:]
        for leak in ('% error', '% (error', 'error)', '{error', 'str(error)'):
            self.assertNotIn(leak, html_literal,
                             '兜底页插值了异常内容（%s）' % leak)
        self.assertIn('返回首页', html_literal)


class ObservabilityTest(unittest.TestCase):
    """H5：请求级追踪号与 /healthz 探针。"""

    def test_24_request_id_generated_and_echoed(self):
        text = _read('web/admin/__init__.py')
        self.assertIn("g.request_id = (request.headers.get('X-Request-Id', '')", text)
        self.assertIn("response.headers['X-Request-Id'] = getattr(g, 'request_id', '')", text)

    def test_25_healthz_exempt_from_close_redirect(self):
        """探针不能被「关站/安全入口」重定向，否则监控永远看不到真实状态。"""
        text = _read('web/admin/__init__.py')
        self.assertIn("request.path == '/healthz'", text)
        self.assertIn("@app.route('/healthz')", text)
        # 不健康要返回 503，便于负载均衡自动摘除
        self.assertIn('503', text)
        # 不得回显版本号/路径等指纹信息
        start = text.index("def healthz():")
        body = text[start:text.index('@app.errorhandler(404)')]
        self.assertNotIn('APP_VERSION', body)
        self.assertNotIn("'db_path'", body)
        self.assertIn("'database'", body)
        self.assertIn("'data_writable'", body)

    def test_26_user_safe_error_reuses_request_id(self):
        """用户报的追踪号必须与日志里的请求 ID 是同一个，否则串不起链路。

        本机可能没装 flask；用假模块注入 sys.modules，
        这样无论环境如何都能**真跑**这段逻辑，而不是 skip 掉当通过。
        """
        import types
        import core.yf as yf

        fake_flask = types.ModuleType('flask')
        fake_flask.g = types.SimpleNamespace(request_id='reqid-abc123')
        with mock.patch.dict(sys.modules, {'flask': fake_flask}):
            with mock.patch.object(yf, 'writeFileLog', lambda *a, **k: None):
                msg = yf.userSafeError(RuntimeError('boom'))
        self.assertIn('reqid-abc123', msg)

    def test_27_user_safe_error_falls_back_without_request_id(self):
        """没有请求上下文时（如计划任务进程）也不能崩，应自生成追踪号。"""
        import types
        import core.yf as yf

        fake_flask = types.ModuleType('flask')
        fake_flask.g = types.SimpleNamespace()          # 没有 request_id
        with mock.patch.dict(sys.modules, {'flask': fake_flask}):
            with mock.patch.object(yf, 'writeFileLog', lambda *a, **k: None):
                msg = yf.userSafeError(RuntimeError('boom'))
        self.assertIn('追踪号', msg)
        self.assertNotIn('None', msg)


class CodeQualityRatchetTest(unittest.TestCase):

    def test_21_ratchet_script_self_test(self):
        proc = subprocess.run(
            [sys.executable, 'scripts/verify_code_quality.py', '--self-test'],
            cwd=project_root, capture_output=True)
        self.assertEqual(proc.returncode, 0,
                         proc.stdout.decode('utf-8', 'replace') +
                         proc.stderr.decode('utf-8', 'replace'))

    def test_22_ratchet_passes_and_baseline_exists(self):
        self.assertTrue(os.path.isfile(
            os.path.join(project_root, 'scripts', 'code_quality_baseline.json')))
        proc = subprocess.run(
            [sys.executable, 'scripts/verify_code_quality.py'],
            cwd=project_root, capture_output=True)
        self.assertEqual(proc.returncode, 0,
                         proc.stdout.decode('utf-8', 'replace'))

    def test_23_ratchet_wired_into_gate(self):
        text = _read('testsuite/run_all.py')
        self.assertIn('verify_code_quality.py', text,
                      '棘轮未挂进静态门禁')
        self.assertIn("'--self-test'", text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
