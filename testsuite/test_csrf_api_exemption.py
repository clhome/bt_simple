# -*- coding: utf-8 -*-
"""P2-1：CSRF 豁免前置 —— 「带 `App-Id` 头就豁免」改为「必须真的通过凭据鉴权」。

被锁死的历史缺陷（`web/core/security.py:csrf_decision` 原实现）::

    if has_app_id:
        return True, 'api-header-auth'

请求头是客户端随便填的，不是凭据。攻击者页面只要在跨站请求里带上 `App-Id` 头，
就整块绕过 CSRF 防护（`web/admin/__init__.py` 当时只判「头存不存在」）。

本轮修复口径（**只做豁免前置**，token / Referer 的 OR 模型一个字没动）：

* 豁免条件从「头存在」换成 `api_verified=True`——由 `web/admin/__init__.py` 用
  P1-5 已实现的纯函数 `_api_credential_decision` 真验凭据之后才置真，
  reason 改名 `api-authenticated`（便于审计区分「真鉴权」与历史上的「带头」）；
* `panel_api.open=False` / 凭据不存在 / `status=0` / 白名单外 IP / secret 错
  → 一律不豁免；
* 鉴权链路任何异常（模块导入失败 / 查库失败 / 取 IP 失败）都 **fail-closed**：
  不豁免、只记 warning、不把异常抛到上层；
* 没带 `App-Id`/`App-Secret` 的浏览器请求行为**完全不变**。

零外部依赖：只 import 标准库与纯函数 `core.security`。`web/admin/__init__.py` 里的
两个判定函数用 AST 从**真实源码**抠出来执行（替身只提供 thisdb / yf / app.logger），
所以测的就是仓库里的那段代码，不会出现「用例里复制一份口径，实现退化了用例照样绿」。
"""
import ast
import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WEB = os.path.join(_ROOT, 'web')
for _p in (_WEB, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.security import csrf_decision, extract_supplied_token  # noqa: E402

ADMIN_INIT = 'web/admin/__init__.py'
SECURITY_PY = 'web/core/security.py'

HOST = 'panel.example.com:7200'
APP_ID = 'app-1'
SECRET = 'S3cr3t-For-Testing-Do-Not-Log'
PUBLIC_IP = '81.2.69.160'
OTHER_IP = '78.46.12.34'


def _read(rel):
    with open(os.path.join(_ROOT, rel), 'r', encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


# ---------------------------------------------------------------------------
# 最小的请求 / thisdb / yf / app.logger 替身
# ---------------------------------------------------------------------------
class _Headers(dict):
    """大小写不敏感的头（与 werkzeug 的 `request.headers.get` 语义一致）。"""

    def __init__(self, data=None):
        dict.__init__(self)
        for key, val in (data or {}).items():
            dict.__setitem__(self, key.lower(), val)

    def get(self, key, default=''):
        return dict.get(self, (key or '').lower(), default)


class _Req(object):
    """够用的假请求：`_csrf_request_decision` 只用到这五个成员。"""

    def __init__(self, method='POST', path='/api/run', host=HOST,
                 headers=None, form=None):
        self.method = method
        self.path = path
        self.host = host
        self.headers = _Headers(headers)
        self.form = dict(form or {})


class _Logger(object):
    def __init__(self):
        self.warnings = []
        self.debugs = []

    def warning(self, fmt, *args):
        self.warnings.append(fmt % args if args else str(fmt))

    def debug(self, fmt, *args):
        self.debugs.append(fmt % args if args else str(fmt))


class _App(object):
    def __init__(self):
        self.logger = _Logger()


class _ThisDb(object):
    """thisdb 替身：可注入「API 开关 / 凭据记录 / 抛异常」。"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.panel_api = {'open': True}
        self.record = {
            'app_id': APP_ID,
            'app_secret': SECRET,
            'white_list': '',
            'status': 1,
        }
        self.calls = []
        self.raise_option = None
        self.raise_app = None

    def getOptionByJson(self, name, type='common', default=None):
        self.calls.append(('option', name, default))
        if self.raise_option is not None:
            raise self.raise_option
        return dict(self.panel_api) if isinstance(self.panel_api, dict) else self.panel_api

    def getAppByAppId(self, app_id):
        self.calls.append(('app', app_id))
        if self.raise_app is not None:
            raise self.raise_app
        if self.record and self.record.get('app_id') == app_id:
            return dict(self.record)
        return None


class _Yf(object):
    """`core.yf` 替身：只提供被用到且最容易出错的 `getClientIp`。"""

    def __init__(self):
        self.ip = PUBLIC_IP
        self.raise_ip = None

    def getClientIp(self):
        if self.raise_ip is not None:
            raise self.raise_ip
        return self.ip


# ---------------------------------------------------------------------------
# 把 web/admin/__init__.py 里的判定函数按 AST 抠出来执行
# ---------------------------------------------------------------------------
_ADMIN_FUNCS = ('_api_headers_authenticated', '_csrf_request_decision')


def _load_admin_functions(extra_globals):
    tree = ast.parse(_read(ADMIN_INIT))
    found = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _ADMIN_FUNCS:
            found[node.name] = node
    missing = [name for name in _ADMIN_FUNCS if name not in found]
    if missing:
        raise AssertionError('%s 里找不到函数：%s' % (ADMIN_INIT, ', '.join(missing)))

    namespace = dict(extra_globals)
    namespace.setdefault('csrf_decision', csrf_decision)
    namespace.setdefault('extract_supplied_token', extract_supplied_token)
    module = ast.Module(body=[found[name] for name in _ADMIN_FUNCS], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, ADMIN_INIT, 'exec'), namespace)
    return namespace


def _fake_admin_modules():
    """`admin` / `admin.common` 替身：挡掉 `user_login_check` 的导入期依赖。"""
    admin = types.ModuleType('admin')
    admin.session = {}
    common = types.ModuleType('admin.common')
    common.isLogined = lambda: False
    admin.common = common
    return admin, common


def _fake_flask_module():
    mod = types.ModuleType('flask')
    mod.render_template = lambda name, **kwargs: None
    mod.Response = object
    mod.request = types.SimpleNamespace(headers=_Headers(), form={})
    return mod


def _load_user_login_check():
    """按真实文件路径加载 P1-5 的判定模块（被测的是它的真实实现）。"""
    path = os.path.join(_WEB, 'admin', 'user_login_check.py')
    spec = importlib.util.spec_from_file_location('p21_user_login_check_under_test', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Harness(unittest.TestCase):
    """装上真实 `_api_credential_decision`，并拿到 admin 里的两个判定函数。"""

    @classmethod
    def setUpClass(cls):
        admin_stub, common_stub = _fake_admin_modules()
        cls.thisdb_stub = types.ModuleType('thisdb')
        cls._patcher = mock.patch.dict(sys.modules, {
            'flask': _fake_flask_module(),
            'admin': admin_stub,
            'admin.common': common_stub,
            'thisdb': cls.thisdb_stub,
        })
        cls._patcher.start()
        cls.user_login_check = _load_user_login_check()
        # 让 admin/__init__.py 里的 `from admin.user_login_check import ...` 命中真实模块
        sys.modules['admin.user_login_check'] = cls.user_login_check

        cls.db = _ThisDb()
        cls.yf = _Yf()
        cls.app = _App()
        cls.ns = _load_admin_functions({'thisdb': cls.db, 'yf': cls.yf, 'app': cls.app})

    @classmethod
    def tearDownClass(cls):
        cls._patcher.stop()

    def setUp(self):
        self.db.reset()
        self.yf.ip = PUBLIC_IP
        self.yf.raise_ip = None
        self.app.logger = _Logger()
        self.api_authenticated = self.ns['_api_headers_authenticated']
        self.decide = self.ns['_csrf_request_decision']

    def api_headers(self, app_id=APP_ID, secret=SECRET):
        return {'App-Id': app_id, 'App-Secret': secret}


# ---------------------------------------------------------------------------
# 1) 纯函数真值表
# ---------------------------------------------------------------------------
class CsrfDecisionTableTest(unittest.TestCase):
    """`csrf_decision` 真值表：豁免只认 `api_verified`，OR 四态原样保持。"""

    def decide(self, **kwargs):
        args = dict(method='POST', path='/plugins/run', host=HOST,
                    referer='', origin='', token_expected='tok', token_supplied='')
        args.update(kwargs)
        return csrf_decision(**args)

    def test_01_forged_header_alone_is_rejected(self):
        """只带 `App-Id` 头（未鉴权）→ 拒绝，理由不得是任何豁免。"""
        for extra in ({'has_app_id': True}, {'has_app_id': False}, {}):
            allowed, reason = self.decide(**extra)
            self.assertFalse(allowed, '仅凭请求头存在不得豁免 CSRF：%r' % (extra,))
            self.assertEqual(reason, 'no-proof', extra)

    def test_02_api_verified_is_the_header_exemption(self):
        allowed, reason = self.decide(api_verified=True)
        self.assertTrue(allowed)
        self.assertEqual(reason, 'api-authenticated')

        # `has_app_id` 只是信息位：带不带头不影响结论
        self.assertEqual((allowed, reason), self.decide(api_verified=True, has_app_id=True))

    def test_03_safe_methods_always_pass(self):
        for method in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            for extra in ({'has_app_id': True}, {'api_verified': True}, {}):
                allowed, reason = self.decide(method=method, **extra)
                self.assertTrue(allowed, (method, extra))
                self.assertEqual(reason, 'safe-method', (method, extra))

    def test_04_exempt_paths_still_pass(self):
        for path in ('/hook', '/.well-known/acme-challenge/x',
                     '/secret/quick_login', '/panel-7200/quick_login'):
            allowed, reason = self.decide(path=path)
            self.assertTrue(allowed, path)
            self.assertEqual(reason, 'exempt-path', path)

    def test_05_or_model_four_states_unchanged(self):
        """token-only / referer-only / token+referer / no-proof 必须与改前完全一致。"""
        good_ref = 'https://%s/files' % HOST
        cases = [
            ({'token_supplied': 'tok'}, (True, 'token-only')),
            ({'referer': good_ref}, (True, 'referer-only')),
            ({'origin': 'https://%s' % HOST}, (True, 'referer-only')),
            ({'token_supplied': 'tok', 'referer': good_ref}, (True, 'token+referer')),
            ({'token_supplied': 'bad', 'referer': good_ref}, (True, 'referer-only')),
            ({'token_supplied': 'bad'}, (False, 'no-proof')),
            ({'referer': 'https://evil.example.com/x'}, (False, 'no-proof')),
            ({}, (False, 'no-proof')),
        ]
        for kwargs, expected in cases:
            self.assertEqual(expected, self.decide(**kwargs), kwargs)
            # 带 `App-Id` 头不得改变上面任何一态（它不参与判定）
            self.assertEqual(expected, self.decide(has_app_id=True, **kwargs),
                             '带头后结果变了：%r' % (kwargs,))


# ---------------------------------------------------------------------------
# 2) 跨站伪造头
# ---------------------------------------------------------------------------
class ForgedAppIdHeaderCrossSiteTest(_Harness):
    """攻击者页面发起的 POST：带伪造 `App-Id` 头、Issuer 非同源、无 token → 必须 403。"""

    def forged_request(self, headers=None, **kwargs):
        base = {
            'App-Id': APP_ID,
            'Origin': 'https://evil.example.com',
            'Referer': 'https://evil.example.com/csrf.html',
        }
        base.update(headers or {})
        return self.decide(_Req(headers=base, **kwargs), 'tok')

    def test_01_forged_header_without_secret_denied(self):
        allowed, reason = self.forged_request()
        self.assertFalse(allowed, '伪造 App-Id 头就能过 CSRF = 修复没生效')
        self.assertEqual(reason, 'no-proof')

    def test_02_forged_header_with_guessed_secret_denied(self):
        allowed, reason = self.forged_request(headers={'App-Secret': 'guessed-secret'})
        self.assertFalse(allowed, '猜的 secret 必须被拒')
        self.assertEqual(reason, 'no-proof')

    def test_03_forged_header_with_same_origin_but_no_token_denied(self):
        """头+同源 Referer 但未鉴权：只能按 referer-only 走（旧行为），不是「头豁免」。"""
        allowed, reason = self.forged_request(
            headers={'App-Secret': 'guessed-secret',
                     'Referer': 'https://%s/files' % HOST})
        self.assertTrue(allowed, 'Referer 同源本来就允许通过（OR 模型未改）')
        self.assertEqual(reason, 'referer-only', '不得再出现「带头即豁免」的理由')

    def test_04_denial_maps_to_403_in_before_request(self):
        """`before_request` 在 `not allowed` 时返回 403 —— 上面断言的正是同一份判定代码。"""
        allowed, _ = self.forged_request(headers={'App-Secret': 'guessed-secret'})
        self.assertFalse(allowed)
        self.assertIn("return Response('Forbidden', status=403)", _read(ADMIN_INIT))


# ---------------------------------------------------------------------------
# 3) 鉴权通过才豁免
# ---------------------------------------------------------------------------
class CsrfExemptionRequiresRealAuthTest(_Harness):
    """只有「API 已开启 + 凭据存在 + status 启用 + 白名单内 + secret 正确」才豁免。"""

    def test_01_api_closed_never_exempts(self):
        """`panel_api.open=False`：凭据鉴权本身未开启，带正确 App-Id/Secret 也不豁免。"""
        self.db.panel_api = {'open': False}
        allowed, reason = self.decide(_Req(headers=self.api_headers()), 'tok')
        self.assertFalse(allowed, 'API 未开启时不得豁免 CSRF')
        self.assertEqual(reason, 'no-proof')

    def test_02_verified_credential_exempted(self):
        allowed, reason = self.decide(_Req(headers=self.api_headers()), 'tok')
        self.assertTrue(allowed)
        self.assertEqual(reason, 'api-authenticated')
        # 真验过库：选项 + 凭据都查过（证明不是「头存在即真」）
        kinds = [call[0] for call in self.db.calls]
        self.assertIn('option', kinds)
        self.assertIn('app', kinds)

    def test_03_disabled_credential_not_exempted(self):
        self.db.record['status'] = 0
        allowed, reason = self.decide(_Req(headers=self.api_headers()), 'tok')
        self.assertFalse(allowed, '停用的凭据不得豁免（status=0）')
        self.assertEqual(reason, 'no-proof')

    def test_04_ip_outside_white_list_not_exempted(self):
        self.db.record['white_list'] = PUBLIC_IP
        self.yf.ip = OTHER_IP
        allowed, reason = self.decide(_Req(headers=self.api_headers()), 'tok')
        self.assertFalse(allowed, '白名单外 IP 不得豁免')
        self.assertEqual(reason, 'no-proof')

    def test_05_ip_inside_white_list_exempted(self):
        self.db.record['white_list'] = '10.0.0.1\n%s' % PUBLIC_IP
        allowed, reason = self.decide(_Req(headers=self.api_headers()), 'tok')
        self.assertTrue(allowed)
        self.assertEqual(reason, 'api-authenticated')

    def test_06_wrong_secret_not_exempted(self):
        allowed, reason = self.decide(
            _Req(headers=self.api_headers(secret='wrong-secret')), 'tok')
        self.assertFalse(allowed, 'secret 不对不得豁免')
        self.assertEqual(reason, 'no-proof')

    def test_07_unknown_app_id_not_exempted(self):
        allowed, reason = self.decide(
            _Req(headers=self.api_headers(app_id='nobody')), 'tok')
        self.assertFalse(allowed, '凭据不存在不得豁免')
        self.assertEqual(reason, 'no-proof')

    def test_08_browser_requests_without_api_headers_unchanged(self):
        """没带 App-Id/App-Secret 的浏览器请求：不查库、不进鉴权，行为完全不变。"""
        allowed, reason = self.decide(
            _Req(headers={'Referer': 'https://%s/files' % HOST}), 'tok')
        self.assertTrue(allowed)
        self.assertEqual(reason, 'referer-only')
        self.assertEqual([], self.db.calls, '无 App 头不应触碰 API 选项/凭据查询')

        self.assertEqual((True, 'token-only'),
                         self.decide(_Req(form={'csrf_token': 'tok'}), 'tok'))
        self.assertEqual((False, 'no-proof'), self.decide(_Req(), 'tok'))

    def test_09_only_one_header_present_falls_back(self):
        """只带 App-Id 或只带 App-Secret：不尝试鉴权，走原 token/referer 分支。"""
        for headers in ({'App-Id': APP_ID}, {'App-Secret': SECRET}):
            self.db.reset()
            allowed, reason = self.decide(_Req(headers=headers), 'tok')
            self.assertFalse(allowed, headers)
            self.assertEqual('no-proof', reason)
            self.assertEqual([], self.db.calls, '缺一个头时不应查库：%r' % (headers,))


# ---------------------------------------------------------------------------
# 4) 异常 fail-closed
# ---------------------------------------------------------------------------
class ApiAuthFailClosedTest(_Harness):
    """鉴权链路任何异常：不豁免、只记 warning、不把异常抛到上层。"""

    def assert_denied_with_warning(self):
        allowed, reason = self.decide(_Req(headers=self.api_headers()), 'tok')
        self.assertFalse(allowed, '异常时必须 fail-closed，不得豁免 CSRF')
        self.assertEqual('no-proof', reason)
        self.assertTrue(self.app.logger.warnings,
                        '异常必须留下 warning 日志，不能静默失败')

    def test_01_option_query_raises(self):
        self.db.raise_option = RuntimeError('database is locked')
        self.assert_denied_with_warning()

    def test_02_credential_query_raises(self):
        self.db.raise_app = RuntimeError('no such table: app')
        self.assert_denied_with_warning()

    def test_03_client_ip_raises(self):
        self.yf.raise_ip = RuntimeError('working outside request context')
        self.assert_denied_with_warning()

    def test_04_import_failure_of_decision_module(self):
        """P1-5 的模块导入失败（升级窗口期文件缺失）也必须 fail-closed。"""
        with mock.patch.dict(sys.modules, {'admin.user_login_check': None}):
            self.assert_denied_with_warning()

    def test_05_helper_returns_false_instead_of_raising(self):
        for attr, value in (('raise_option', RuntimeError('boom')),
                            ('raise_app', RuntimeError('boom'))):
            self.db.reset()
            setattr(self.db, attr, value)
            self.assertFalse(self.api_authenticated(APP_ID, SECRET), attr)
            self.assertTrue(self.app.logger.warnings, attr)

        self.db.reset()
        self.yf.raise_ip = RuntimeError('boom')
        self.assertFalse(self.api_authenticated(APP_ID, SECRET))
        self.assertTrue(self.app.logger.warnings)


# ---------------------------------------------------------------------------
# 5) + 6) 静态断言：实现里不许再有「头存在即放行」以及退回
# ---------------------------------------------------------------------------
class SourceGuardTest(unittest.TestCase):
    """把修复钉在源码上：捷径删掉、接线必须传鉴权结果。"""

    @staticmethod
    def _func_node(tree, name):
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        return None

    @staticmethod
    def _returns_true(stmt):
        return (isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Tuple)
                and len(stmt.value.elts) == 2
                and isinstance(stmt.value.elts[0], ast.Constant)
                and stmt.value.elts[0].value is True)

    def test_01_csrf_decision_has_no_header_shortcut(self):
        src = _read(SECURITY_PY)
        func = self._func_node(ast.parse(src), 'csrf_decision')
        self.assertIsNotNone(func, 'security.py 里找不到 csrf_decision')

        args = [a.arg for a in func.args.args] + [a.arg for a in func.args.kwonlyargs]
        self.assertIn('api_verified', args, '必须新增 api_verified 参数')

        # 任何「return True, <reason>」的分支，其条件里都不许出现 has_app_id
        allow_branches = [node for node in ast.walk(func)
                          if isinstance(node, ast.If)
                          and any(self._returns_true(stmt) for stmt in node.body)]
        self.assertTrue(allow_branches, '没找到任何放行分支')
        for node in allow_branches:
            cond = ast.unparse(node.test)
            self.assertNotIn('has_app_id', cond,
                             '放行分支仍依赖「头存在」：%s' % cond)

        # 凭据豁免分支必须且只能靠 api_verified，reason 必须是新口径
        api_branch = [node for node in allow_branches
                      if 'api_verified' in ast.unparse(node.test)]
        self.assertEqual(1, len(api_branch), '凭据豁免分支必须且只能看 api_verified')
        reason = api_branch[0].body[0].value.elts[1].value
        self.assertEqual('api-authenticated', reason)

        # 旧 reason 必须消失（否则审计无法区分「头存在」与「真鉴权」）
        self.assertNotIn('api-header-auth', src, '旧的 api-header-auth 口径必须删掉')
        self.assertIn("'api-authenticated'", src)

    def test_02_admin_wiring_passes_auth_result(self):
        src = _read(ADMIN_INIT)
        tree = ast.parse(src)
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == 'csrf_decision']
        self.assertEqual(1, len(calls), 'admin/__init__.py 应只有一处 csrf_decision 调用')

        keywords = {kw.arg: kw.value for kw in calls[0].keywords}
        self.assertIn('api_verified', keywords, '调 csrf_decision 必须传鉴权结果')
        value = keywords['api_verified']
        self.assertIsInstance(value, ast.Call,
                              'api_verified 必须是算出来的，不能是常量/头存在')
        self.assertEqual('_api_headers_authenticated', getattr(value.func, 'id', None),
                         'api_verified 必须来自鉴权函数，不能退回「头存在即真」')

    def test_03_auth_helper_is_fail_closed_and_reuses_p15(self):
        src = _read(ADMIN_INIT)
        node = self._func_node(ast.parse(src), '_api_headers_authenticated')
        self.assertIsNotNone(node, '缺 _api_headers_authenticated')
        body = ast.get_source_segment(src, node)

        # 复用 P1-5 的纯判定函数，不另写一套口径
        self.assertIn('from admin.user_login_check import _api_credential_decision', body)
        self.assertIn('_api_credential_decision(', body)
        # 取值方式与 panel_login_required 一致
        self.assertIn("getOptionByJson('panel_api'", body)
        self.assertIn('getAppByAppId(', body)
        self.assertIn('getClientIp()', body)
        # fail-closed：异常要有可见日志，且不许 except: pass
        self.assertIn('app.logger.warning', body, '异常必须记 warning')
        self.assertNotIn('except:', body, '不得裸 except')
        self.assertIn('except Exception as exc', body)
        self.assertNotIn('pass', body.split('except Exception as exc:')[-1],
                         'except 分支不得只 pass')
        # 未通过鉴权时返回 False（豁免必须显式为真）
        self.assertIn('return False', body)

    def test_04_before_request_still_denies_with_403(self):
        src = _read(ADMIN_INIT)
        self.assertIn("return Response('Forbidden', status=403)", src)
        self.assertIn('_csrf_request_decision(request', src,
                      'before_request 必须走这份判定入口')


if __name__ == '__main__':
    unittest.main(verbosity=2)
