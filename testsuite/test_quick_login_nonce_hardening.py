# coding: utf-8
"""测评报告 P0-2 回归守卫：安全入口快捷登录（一次性 nonce + 强制 2FA）。

旧机制 `GET /<安全入口>?login=base64(json{username,password,time})`：

  * 明文口令经 base64 进 URL → 落访问日志 / 浏览器历史 / Referer；
  * 该分支只校验口令，**不校验二步验证**，是 2FA 旁路。

新机制：源面板现签 `{url: <目标>/quick_login, fields: {nonce,username,password,time}}`，
前端把 fields 装进隐藏表单 **POST** 给目标面板；目标面板 `dashboard.py::quick_login`
把 nonce 记为一次性、短时效（用后即焚），并复用 login.py 的限流/口令校验/二步验证流程。

沿用仓库既有风格：AST 抽出真实函数体，在桩命名空间里执行（不依赖 flask app 上下文、
不发起网络请求、不碰真库）。断言必须真能失败 —— 见 `test/p0_quick_login_mutation_probe.py`。
"""
import ast
import base64
import json
import os
import re
import sys
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)

import core.quick_login_nonce as quick_login_nonce

DASHBOARD_PY = os.path.join(WEB, 'admin', 'dashboard', 'dashboard.py')
BOOKMARK_PY = os.path.join(WEB, 'admin', 'setting', 'panel_bookmark.py')
PUBLIC_JS = os.path.join(WEB, 'static', 'app', 'public.js')

SECRET = 'S3cret!Pass-测试口令'
SECRET_B64 = base64.b64encode(SECRET.encode('utf-8')).decode('utf-8')


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _func_src(path, name):
    """抽出函数的真实源码（去掉 blueprint 装饰器），供桩命名空间执行。"""
    tree = ast.parse(_read(path))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            node.decorator_list = []
            return ast.unparse(ast.Module(body=[node], type_ignores=[]))
    raise AssertionError('%s 里找不到函数 %s' % (path, name))


def _assign_src(path, name):
    """抽出模块级赋值的真实源码（如 _PB_URL_RE / QUICK_LOGIN_TTL_MS）。"""
    tree = ast.parse(_read(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.unparse(node)
    raise AssertionError('%s 里找不到模块级赋值 %s' % (path, name))


def _const_value(path, name):
    tree = ast.parse(_read(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    # 常量可能是 `60 * 1000` 这类表达式，literal_eval 不支持，故用受限 eval
                    return eval(ast.unparse(node.value), {'__builtins__': {}}, {})
    raise AssertionError('%s 里找不到常量 %s' % (path, name))


def _redirect(url):
    return ('REDIRECT', url)


class _Recorder(object):
    def __init__(self, result=None):
        self.calls = []
        self.result = result

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


class _FakeRequest(object):
    def __init__(self, form=None, args=None):
        self.form = form or {}
        self.args = args or {}


class _FakeYf(object):
    def __init__(self, client_ip='10.0.0.9'):
        self.client_ip = client_ip
        self.logs = []

    def getClientIp(self):
        return self.client_ip

    def writeLog(self, *args, **kwargs):
        self.logs.append((args, kwargs))

    def writeFileLog(self, *args, **kwargs):
        pass


# ---------------------------------------------------------------------------
# 执行 quick_login 的桩：相对导入 `from .login import ...` 需要一个假包
# ---------------------------------------------------------------------------

class _FakePackage(object):
    """临时注册 `admin.dashboard.login` 假模块，让被抽出的函数能 import 到桩。"""

    def __init__(self, login_mod):
        self._login_mod = login_mod
        self._saved = {}

    def __enter__(self):
        for name in ('admin', 'admin.dashboard', 'admin.dashboard.login'):
            self._saved[name] = sys.modules.get(name)
        if sys.modules.get('admin') is None:
            sys.modules['admin'] = types.ModuleType('admin')
        pkg = types.ModuleType('admin.dashboard')
        pkg.__path__ = []
        sys.modules['admin.dashboard'] = pkg
        sys.modules['admin.dashboard.login'] = self._login_mod
        return self

    def __exit__(self, *exc):
        for name, mod in self._saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod
        return False


class _QuickLoginCase(object):
    """构造并执行 dashboard.py::quick_login 的真实函数体。"""

    def __init__(self, two_step_open=False, info=None, banned=False,
                 password_ok=True, db_path='secret', client_ip='10.0.0.9'):
        self.yf = _FakeYf(client_ip)
        self.request = _FakeRequest()
        self.is_banned = _Recorder(banned)
        self.register_failure = _Recorder((False, 4))
        self.reset_failure = _Recorder(None)
        self.password_matches = _Recorder(password_ok)
        self.login_success = _Recorder(None)
        self._two_step_open = two_step_open
        self._info = info if info is not None else {'id': 1, 'name': 'admin', 'password': 'x'}

        self.thisdb = types.SimpleNamespace(
            getOption=lambda name, default=None: db_path if name == 'admin_path' else default,
            getOptionByJson=lambda name, default=None: (
                {'open': self._two_step_open} if name == 'two_step_verification' else default),
            getUserByName=lambda name: self._info if name == 'admin' else None,
        )
        login_mod = types.ModuleType('admin.dashboard.login')
        login_mod._is_banned = self.is_banned
        login_mod._register_login_failure = self.register_failure
        login_mod._reset_login_failure = self.reset_failure
        login_mod._password_matches = self.password_matches
        login_mod._login_success = self.login_success
        self._login_mod = login_mod

    def call(self, path='secret', form=None):
        self.request.form = form if form is not None else {}
        ns = {
            'thisdb': self.thisdb,
            'yf': self.yf,
            'redirect': _redirect,
            'request': self.request,
            'time': time,
            'quick_login_nonce': quick_login_nonce,
            'QUICK_LOGIN_TTL_MS': _const_value(DASHBOARD_PY, 'QUICK_LOGIN_TTL_MS'),
            '__package__': 'admin.dashboard',
        }
        exec(compile(_func_src(DASHBOARD_PY, 'quick_login'), DASHBOARD_PY, 'exec'), ns)
        with _FakePackage(self._login_mod):
            return ns['quick_login'](path)

    def fresh_form(self, nonce='n1', stamp=None, password=SECRET, username='admin'):
        return {
            'nonce': nonce,
            'username': username,
            'password': password,
            'time': str(int(time.time() * 1000) if stamp is None else stamp),
        }


# ---------------------------------------------------------------------------
# 1) 源面板：口令不进 URL
# ---------------------------------------------------------------------------

class _BookmarkCase(object):
    def __init__(self, url='http://192.168.0.9:8888/secret'):
        self.row = {'id': 1, 'url': url, 'username': 'admin', 'password': SECRET}

        yf = types.SimpleNamespace(
            M=lambda *a, **k: self,
            getRandomString=lambda n: 'N' * n,
            deDoubleCrypt=lambda key, value: value,
            returnData=lambda status, msg, data=None, *a: {'status': status, 'msg': msg, 'data': data},
        )
        self._ns = {
            'yf': yf,
            'request': _FakeRequest({'id': '1'}),
            'time': time,
            're': re,
            '__package__': 'admin.setting.panel_bookmark',
        }
        src = '\n'.join([
            _assign_src(BOOKMARK_PY, '_PB_URL_RE'),
            _func_src(BOOKMARK_PY, '_valid_panel_url'),
            _func_src(BOOKMARK_PY, '_dec_pwd'),
            _func_src(BOOKMARK_PY, '_quick_login_url'),
            _func_src(BOOKMARK_PY, 'get_panel_login'),
        ])
        exec(compile(src, BOOKMARK_PY, 'exec'), self._ns)

    # 模拟 yf.M('panel').where(...).find() 查询链
    def where(self, *args, **kwargs):
        return self

    def find(self):
        return self.row

    def call(self):
        return self._ns['get_panel_login']()


class TestPanelBookmarkNoCredentialInUrl(unittest.TestCase):

    def setUp(self):
        self.case = _BookmarkCase()

    def test_url_carries_no_credential(self):
        res = self.case.call()
        self.assertTrue(res['status'])
        url = res['data']['url']
        self.assertNotIn(SECRET, url, '明文口令不得出现在快捷登录 URL 里')
        self.assertNotIn(SECRET_B64, url, 'base64 口令不得出现在快捷登录 URL 里')
        self.assertNotIn('login=', url, '旧的 ?login= 机制必须废弃')
        self.assertTrue(url.endswith('/quick_login'), '目标应为快捷登录 POST 端点：%s' % url)

    def test_old_base64_payload_absent_from_url(self):
        """旧机制把整个 json{rand,username,password,time} 做 base64 拼进 URL。"""
        res = self.case.call()
        url = res['data']['url']
        blob = base64.b64encode(json.dumps({
            'rand': 'N' * 8, 'username': 'admin', 'password': SECRET,
            'time': int(time.time() * 1000)}).encode('utf-8')).decode('utf-8')
        self.assertNotIn(blob, url)
        self.assertNotIn('eyJ', url, 'URL 里不应出现 base64(json) 前缀 eyJ')

    def test_post_fields_carry_the_secret(self):
        """口令只能走 POST body（前端隐藏表单），故必须由 fields 携带。"""
        res = self.case.call()
        fields = res['data']['fields']
        self.assertEqual(fields['password'], SECRET)
        self.assertEqual(fields['username'], 'admin')
        self.assertTrue(fields['nonce'], '必须现签一次性 nonce')
        self.assertGreaterEqual(len(fields['nonce']), 16, 'nonce 长度不足以防猜测')
        self.assertGreater(int(fields['time']), 0)

    def test_source_has_no_base64_login_url(self):
        body = _func_src(BOOKMARK_PY, 'get_panel_login')
        self.assertNotIn('login=', body)
        self.assertNotIn('b64encode', body)
        self.assertNotIn('base64', body)
        self.assertIn('fields', body)

    def test_list_return_has_no_password(self):
        body = _func_src(BOOKMARK_PY, 'get_panel_list')
        self.assertNotIn('password', body, '列表接口不得回传口令')

    def test_query_and_trailing_slash_url_normalized(self):
        for raw in ('http://h:8888/secret', 'http://h:8888/secret/',
                    'http://h:8888/secret?x=1', 'http://h:8888/secret#f'):
            url = _BookmarkCase(raw).call()['data']['url']
            self.assertEqual(url, 'http://h:8888/secret/quick_login', raw)


# ---------------------------------------------------------------------------
# 2) GET ?login= 分支已废弃
# ---------------------------------------------------------------------------

def _legacy_login_payload():
    return base64.b64encode(json.dumps({
        'rand': 'N' * 8, 'username': 'admin', 'password': SECRET,
        'time': int(time.time() * 1000)}).encode('utf-8')).decode('utf-8')


class TestGetLoginDeprecated(unittest.TestCase):

    def _run(self, path, args):
        session = {}
        rendered = []
        ns = {
            'thisdb': types.SimpleNamespace(
                getOption=lambda name, default=None: {
                    'admin_path': 'secret', 'template': 'default',
                    'unauthorized_status': '0'}.get(name, default),
                getUserByName=lambda name: {'id': 1, 'name': 'admin', 'password': 'x'},
                updateUserLoginTime=lambda ip: None),
            'isLogined': lambda: False,
            'redirect': _redirect,
            'render_template': lambda tpl: rendered.append(tpl) or ('RENDER', tpl),
            'Response': lambda *a, **k: ('RESPONSE', k.get('status')),
            'request': _FakeRequest(args=args),
            'session': session,
            'yf': types.SimpleNamespace(getClientIp=lambda: '10.0.0.9', writeLog=lambda *a: None,
                                        writeFileLog=lambda *a: None),
            'base64': base64,
            'json': json,
            'time': time,
            '__package__': 'admin.dashboard',
        }
        # 即使旧分支被复活，也要让它的相对导入解析成功（否则会 NameError 掩盖问题）
        login_mod = types.ModuleType('admin.dashboard.login')
        login_mod._is_banned = _Recorder(False)
        login_mod._register_login_failure = _Recorder((False, 5))
        login_mod._reset_login_failure = _Recorder(None)
        login_mod._password_matches = _Recorder(True)  # 故意放行，逼出「是否真的建立了登录态」
        exec(compile(_func_src(DASHBOARD_PY, 'admin_safe_path'), DASHBOARD_PY, 'exec'), ns)
        with _FakePackage(login_mod):
            resp = ns['admin_safe_path'](path)
        return session, rendered, resp

    def test_legacy_login_arg_does_not_log_in(self):
        session, rendered, resp = self._run('secret', {'login': _legacy_login_payload()})
        self.assertNotIn('login', session, '?login= 旧机制必须已废弃，不得建立登录态')
        self.assertNotIn('username', session)
        self.assertEqual(resp, ('RENDER', 'default/login.html'),
                         '带 login= 的安全入口应只回登录页')

    def test_legacy_login_arg_never_verifies_password(self):
        """真正废弃的标准：源码里不再出现解码/校验口令的痕迹。"""
        body = _func_src(DASHBOARD_PY, 'admin_safe_path')
        for banned in ('base64', 'json.loads', '_password_matches', 'time_diff',
                       "session['login']", 'b64decode'):
            self.assertNotIn(banned, body, 'admin_safe_path 仍残留旧快捷登录分支：%s' % banned)

    def test_route_is_get_only(self):
        src = _read(DASHBOARD_PY)
        rule_line = next(l for l in src.splitlines() if "endpoint='admin_safe_path'" in l)
        self.assertIn("methods=['GET']", rule_line, '安全入口只应接受 GET')


# ---------------------------------------------------------------------------
# 3) quick_login：nonce 一次性 + 时效
# ---------------------------------------------------------------------------

class TestQuickLoginNonce(unittest.TestCase):

    def setUp(self):
        quick_login_nonce.reset()

    def tearDown(self):
        quick_login_nonce.reset()

    def test_first_use_logs_in(self):
        case = _QuickLoginCase()
        resp = case.call(form=case.fresh_form())
        self.assertEqual(len(case.login_success.calls), 1, '首次使用应登录成功')
        self.assertEqual(resp, ('REDIRECT', '/'))
        self.assertEqual(len(case.yf.logs), 1)

    def test_replay_is_rejected(self):
        case = _QuickLoginCase()
        form = case.fresh_form(nonce='replay-me')
        case.call(form=form)
        self.assertEqual(len(case.login_success.calls), 1, '首次应成功')
        case.call(form=form)  # 同一 nonce 再放一次
        self.assertEqual(len(case.login_success.calls), 1, 'nonce 重放必须被拒（用后即焚）')

    def test_stale_timestamp_is_rejected(self):
        case = _QuickLoginCase()
        stale = int((time.time() - 600) * 1000)  # 10 分钟前，远超 60s 窗口
        case.call(form=case.fresh_form(nonce='stale', stamp=stale))
        self.assertEqual(case.login_success.calls, [], '过期签发的快捷登录必须被拒')

    def test_future_timestamp_is_rejected(self):
        case = _QuickLoginCase()
        future = int((time.time() + 600) * 1000)
        case.call(form=case.fresh_form(nonce='future', stamp=future))
        self.assertEqual(case.login_success.calls, [], '未来时间戳必须被拒（防时钟回拨绕过）')

    def test_missing_or_empty_nonce_is_rejected(self):
        for nonce in ('', '   '):
            case = _QuickLoginCase()
            case.call(form=case.fresh_form(nonce=nonce))
            self.assertEqual(case.login_success.calls, [], 'nonce=%r 不得放行' % nonce)

    def test_bad_timestamp_is_rejected(self):
        for raw in ('', 'abc', '0', 'None'):
            case = _QuickLoginCase()
            case.call(form=case.fresh_form(stamp=raw))
            self.assertEqual(case.login_success.calls, [], 'time=%r 不得放行' % raw)

    def test_wrong_entrance_path_is_rejected(self):
        case = _QuickLoginCase()
        case.call(path='not-secret', form=case.fresh_form())
        self.assertEqual(case.login_success.calls, [], '路径不匹配不得登录')
        self.assertEqual(case.password_matches.calls, [], '路径不匹配时不应触碰口令校验')

    def test_ttl_is_short(self):
        ttl = _const_value(DASHBOARD_PY, 'QUICK_LOGIN_TTL_MS')
        self.assertTrue(0 < ttl <= 60000, '签发时间窗口必须 ≤60s，实际 %r' % ttl)
        self.assertTrue(0 < quick_login_nonce.NONCE_TTL <= 60,
                        'nonce 有效期必须 ≤60s，实际 %r' % quick_login_nonce.NONCE_TTL)


class TestNonceStore(unittest.TestCase):

    def setUp(self):
        quick_login_nonce.reset()

    def tearDown(self):
        quick_login_nonce.reset()

    def test_burn_is_one_shot(self):
        self.assertTrue(quick_login_nonce.burn('abc'))
        self.assertFalse(quick_login_nonce.burn('abc'), '同一 nonce 第二次必须为 False')

    def test_empty_nonce_rejected(self):
        for value in ('', None):
            self.assertFalse(quick_login_nonce.burn(value))

    def test_expired_entry_can_be_reused_but_is_purged(self):
        self.assertTrue(quick_login_nonce.burn('ttl', ttl=-1))  # 立即过期
        self.assertTrue(quick_login_nonce.burn('ttl'), '过期条目不应再占用 nonce')
        self.assertFalse(quick_login_nonce.burn('ttl'))


# ---------------------------------------------------------------------------
# 4) 强制 2FA
# ---------------------------------------------------------------------------

class TestQuickLoginTwoStep(unittest.TestCase):

    def setUp(self):
        quick_login_nonce.reset()

    def tearDown(self):
        quick_login_nonce.reset()

    def test_2fa_does_not_log_in(self):
        case = _QuickLoginCase(two_step_open=True)
        resp = case.call(form=case.fresh_form())
        self.assertEqual(case.login_success.calls, [],
                         '开启 2FA 时快捷登录绝不能直接建立登录态')
        self.assertEqual(resp, ('REDIRECT', '/secret'),
                         '开启 2FA 时应回到安全入口登录页走 TOTP 第二步')

    def test_2fa_check_precedes_login(self):
        body = _func_src(DASHBOARD_PY, 'quick_login')
        self.assertIn('two_step_verification', body)
        self.assertIn("two_step_verification.get('open')", body)
        self.assertLess(body.index('two_step_verification'), body.index('_login_success(info'),
                        '2FA 判断必须早于 _login_success')

    def test_2fa_password_still_checked(self):
        case = _QuickLoginCase(two_step_open=True, password_ok=False)
        case.call(form=case.fresh_form(password='wrong'))
        self.assertEqual(len(case.register_failure.calls), 1,
                         '2FA 开启时口令错误同样要计入失败')


# ---------------------------------------------------------------------------
# 5) 与正常登录同口径：限流 + 失败计数
# ---------------------------------------------------------------------------

class TestQuickLoginSharesLoginGuard(unittest.TestCase):

    def setUp(self):
        quick_login_nonce.reset()

    def tearDown(self):
        quick_login_nonce.reset()

    def test_imports_same_helpers_as_do_login(self):
        body = _func_src(DASHBOARD_PY, 'quick_login')
        for helper in ('_is_banned', '_register_login_failure',
                       '_reset_login_failure', '_password_matches', '_login_success'):
            self.assertIn(helper, body, '快捷登录必须复用 login.py 的 %s' % helper)
        self.assertIn('from .login import', body)

    def test_wrong_password_counts_failure(self):
        case = _QuickLoginCase(password_ok=False)
        case.call(form=case.fresh_form(password='wrong'))
        self.assertEqual(len(case.register_failure.calls), 1, '口令错误必须计入统一失败计数')
        self.assertEqual(case.login_success.calls, [])
        self.assertEqual(case.reset_failure.calls, [], '失败不得清空计数')

    def test_unknown_user_counts_failure(self):
        case = _QuickLoginCase(info=None)
        case.call(form=case.fresh_form(username='nobody'))
        self.assertEqual(len(case.register_failure.calls), 1)

    def test_success_resets_failure(self):
        case = _QuickLoginCase()
        case.call(form=case.fresh_form())
        self.assertEqual(len(case.reset_failure.calls), 1, '成功必须清空失败计数')
        self.assertEqual(len(case.register_failure.calls), 0)

    def test_banned_client_short_circuits(self):
        case = _QuickLoginCase(banned=True)
        case.call(form=case.fresh_form())
        self.assertEqual(case.password_matches.calls, [], '封禁中不应再校验口令')
        self.assertEqual(case.login_success.calls, [])

    def test_ban_check_uses_ip_and_account(self):
        case = _QuickLoginCase()
        case.call(form=case.fresh_form(username='admin'))
        self.assertTrue(case.is_banned.calls)
        args = case.is_banned.calls[0][0]
        self.assertIn('10.0.0.9', args)
        self.assertIn('admin', args, '封禁需同时按 IP 与账号判定')


# ---------------------------------------------------------------------------
# 6) 前端：口令只进 POST body
# ---------------------------------------------------------------------------

class TestFrontendPostsForm(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.js = _read(PUBLIC_JS)

    def test_no_window_open_of_login_url(self):
        self.assertNotIn('window.open(res.data.url)', self.js,
                         '不得再把带 login= 的 URL 直接 window.open')

    def test_submits_hidden_form_with_fields(self):
        self.assertIn('res.data.fields', self.js, '前端必须消费服务端现签的 POST 字段')
        self.assertIn("form.method = 'POST'", self.js)
        self.assertIn("input.type = 'hidden'", self.js)

    def test_no_login_query_param(self):
        self.assertNotIn("login='", self.js)
        self.assertNotIn('?login=', self.js)


# ---------------------------------------------------------------------------
# 7) 跨源 POST 与 CSRF 豁免的一致性（豁免由 core/security.py 提供）
# ---------------------------------------------------------------------------

class TestQuickLoginCsrfExemption(unittest.TestCase):

    def test_route_suffix_matches_csrf_exempt_suffix(self):
        from core.security import CSRF_EXEMPT_POST_SUFFIX
        rule = next(l for l in _read(DASHBOARD_PY).splitlines()
                    if "endpoint='quick_login'" in l)
        self.assertIn("'/<path>" + CSRF_EXEMPT_POST_SUFFIX + "'", rule.replace(' ', ''),
                      '路由后缀必须与 CSRF 豁免后缀一致，否则跨源 POST 会被 403')

    def test_cross_origin_post_passes_csrf(self):
        from core.security import csrf_decision
        allowed, reason = csrf_decision(
            method='POST', path='/secret/quick_login', host='target.example:7200',
            referer='http://source.example:8888/', origin='http://source.example:8888',
            token_expected='tok', token_supplied='', has_app_id=False)
        self.assertTrue(allowed, '源→目标的跨源快捷登录 POST 必须通过 CSRF')
        self.assertEqual(reason, 'exempt-path')


if __name__ == '__main__':
    unittest.main()
