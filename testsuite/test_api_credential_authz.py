# -*- coding: utf-8 -*-
"""P1-5：面板 API 凭据鉴权的授权回归（`panel_login_required` 的 API 分支）。

被锁死的历史缺陷（`web/admin/user_login_check.py` 原实现）：

1. **只看密钥**：`status` 从不检查 —— 界面上「停用」了凭据，凭 `app_secret`
   仍能拿到管理员等价权限，「停用成功」是假象；
2. `white_list` 从不校验 —— IP 白名单形同虚设；
3. `panel_api` 选项缺失时默认 `open: True`，与初始化写入的 `{'open': False}` 口径相反。

本用例的判定口径（顺序即实现顺序）：
    面板 API 开关 → 凭据存在 → status 启用 → 来源 IP 命中白名单 → 密钥比对

**零外部依赖**：本机没装 flask，用例用最小的 `flask` 替身（只提供
`request` / `Response` / `render_template`）；`admin`、`thisdb` 同样用替身，
被测算的是 `user_login_check.py` 的真实代码 + 真实的 `core.yf.getClientIp()`
与真实的 `core.audit.write_audit` 调用点（后者被 monkeypatch 记录参数）。

替身只在 `setUpClass` 里通过 `patch.dict(sys.modules, ...)` 装上、`tearDownClass`
卸掉；门禁本身每个模块独立子进程，不会串味。
"""
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

from testsuite._isolation import isolate              # noqa: E402

# 必须在会打开面板库的模块之前重定向目录（见 testsuite/_isolation.py）
_PANEL_TMP, _SERVER_TMP = isolate('api_credential_authz')

import core.yf as yf                                  # noqa: E402  真实的 getClientIp
import core.audit as audit_mod                        # noqa: E402  真实的 write_audit 定义处

#: 用例里到处用的密钥明文；末尾会断言它绝不出现在审计/日志参数里
SECRET = 'S3cr3t-For-Testing-Do-Not-Log'
APP_ID = 'app-1'

#: 一个不含内网/回环的 IP，保证 yf.getClientIp() 不会去读转发头
PUBLIC_IP = '81.2.69.160'
#: 另一个公网 IP，用于「白名单外」
OTHER_IP = '78.46.12.34'


# ---------------------------------------------------------------------------
# 最小 flask 替身
# ---------------------------------------------------------------------------
class _FakeHeaders(object):
    """大小写不敏感的头（`request.headers.get` 的真实语义）。"""

    def __init__(self, data=None):
        self._data = {}
        for key, val in (data or {}).items():
            self._data[key.lower()] = val

    def get(self, key, default=''):
        return self._data.get(key.lower(), default)


class _FakeRequest(object):
    """可反复复位的假请求对象：真实 `yf.getClientIp()` 会读它。"""

    def __init__(self):
        self.headers = _FakeHeaders()
        self.remote_addr = '127.0.0.1'

    def reset(self, headers=None, remote_addr='127.0.0.1'):
        self.headers = _FakeHeaders(headers)
        self.remote_addr = remote_addr


class _FakeResponse(object):
    """`flask.Response(status=...)` 的最小替身。"""

    def __init__(self, body=None, status=200, **kwargs):
        self.body = body
        self.status_code = status
        self.kwargs = kwargs


REQUEST = _FakeRequest()


def _fake_flask_module():
    mod = types.ModuleType('flask')
    mod.request = REQUEST
    mod.Response = _FakeResponse
    mod.render_template = lambda name, **kwargs: _FakeResponse('template:%s' % name)
    return mod


def _fake_admin_modules():
    """`admin` / `admin.common` 替身：把导入期依赖挡在外面。"""
    admin = types.ModuleType('admin')
    admin.session = {}
    common = types.ModuleType('admin.common')
    common.isLogined = lambda: False
    admin.common = common
    return admin, common


def _load_under_test():
    """按真实文件路径加载被测模块（模块名刻意起名唯一，避免与真身撞车）。"""
    path = os.path.join(_WEB, 'admin', 'user_login_check.py')
    spec = importlib.util.spec_from_file_location('p15_user_login_check_under_test', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ApiCredentialAuthzTest(unittest.TestCase):
    """API 凭据鉴权的 8 条硬口径。"""

    @classmethod
    def setUpClass(cls):
        cls.admin_stub, cls.common_stub = _fake_admin_modules()
        cls.thisdb_stub = types.ModuleType('thisdb')
        cls.patcher = mock.patch.dict(sys.modules, {
            'flask': _fake_flask_module(),
            'admin': cls.admin_stub,
            'admin.common': cls.common_stub,
            'thisdb': cls.thisdb_stub,
        })
        cls.patcher.start()
        cls.mod = _load_under_test()

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()

    # -- 夹具 ---------------------------------------------------------------
    def setUp(self):
        REQUEST.reset()
        self.audits = []
        self.option_defaults = []
        self._audit_patcher = mock.patch.object(audit_mod, 'write_audit', self._record_audit)
        self._audit_patcher.start()
        self.addCleanup(self._audit_patcher.stop)
        self.addCleanup(REQUEST.reset)

        # 基线：API 开启、凭据启用、白名单为空、密钥正确
        self.app_record = {
            'app_id': APP_ID,
            'app_secret': SECRET,
            'white_list': '',
            'status': 1,
        }
        self.stub_thisdb(option={'open': True}, app=self.app_record)

    def _record_audit(self, action, target='', result='ok', detail='', **kwargs):
        self.audits.append({
            'action': action, 'target': target, 'result': result,
            'detail': detail, 'kwargs': kwargs,
        })
        return True

    def stub_thisdb(self, option=None, app=None, option_missing=False):
        """装 thisdb 替身。

        :param option:         `getOptionByJson` 命中选项时返回的值
        :param app:            `getAppByAppId` 命中时返回的凭据记录（None = 不存在）
        :param option_missing: 模拟 option 表里根本没有 `panel_api` 这一项，
                               此时**忠实**按真实实现返回调用方给的 `default`
        """
        def getOptionByJson(name, type='common', default=None):
            self.option_defaults.append(default)
            if option_missing:
                return default
            return option

        def getAppByAppId(app_id):
            if app and app.get('app_id') == app_id:
                return dict(app)
            return None

        self.thisdb_stub.getOptionByJson = getOptionByJson
        self.thisdb_stub.getAppByAppId = getAppByAppId
        self.thisdb_stub.getOption = lambda name, default=None, **kw: default

    def call_view(self, headers=None, remote_addr=PUBLIC_IP):
        """用给定请求头/IP 走一遍被装饰的视图，返回响应对象。"""
        REQUEST.reset(headers=headers, remote_addr=remote_addr)

        @self.mod.panel_login_required
        def view():
            return _FakeResponse('view-body')

        return view()

    def api_headers(self, secret=SECRET, app_id=APP_ID):
        return {'App-Id': app_id, 'App-Secret': secret}

    def last_audit(self):
        self.assertTrue(self.audits, '鉴权分支必须留下审计记录，实际一条都没写')
        return self.audits[-1]

    # -- 用例 1 ------------------------------------------------------------
    def test_disabled_credential_rejected(self):
        """停用凭据（status=0）+ 正确 secret → 拒；不能因为密钥对就放行。"""
        self.app_record['status'] = 0
        resp = self.call_view(self.api_headers())

        self.assertEqual(403, resp.status_code, '停用的 API 凭据必须被拒绝')
        audit = self.last_audit()
        self.assertEqual('denied', audit['result'])
        self.assertIn('status_disabled', audit['detail'])

    # -- 用例 2 ------------------------------------------------------------
    def test_ip_outside_white_list_rejected(self):
        """启用凭据 + 白名单外 IP → 拒。"""
        self.app_record['white_list'] = '81.2.69.160\n10.1.2.3'
        resp = self.call_view(self.api_headers(), remote_addr=OTHER_IP)

        self.assertEqual(403, resp.status_code, '不在 IP 白名单内的来源必须被拒绝')
        audit = self.last_audit()
        self.assertEqual('denied', audit['result'])
        self.assertIn('ip_not_allowed:%s' % OTHER_IP, audit['detail'])

    # -- 用例 3 ------------------------------------------------------------
    def test_ip_inside_white_list_and_secret_ok_allowed(self):
        """启用凭据 + 白名单内 IP + 正确 secret → 通过。"""
        self.app_record['white_list'] = '81.2.69.160\n10.1.2.3\n'
        resp = self.call_view(self.api_headers(), remote_addr=PUBLIC_IP)

        self.assertEqual(200, resp.status_code, '白名单内 + 密钥正确必须放行')
        self.assertEqual('view-body', resp.body)
        audit = self.last_audit()
        self.assertEqual('ok', audit['result'])
        self.assertEqual('api.auth', audit['action'])

    # -- 用例 4 ------------------------------------------------------------
    def test_empty_white_list_allowed_backward_compatible(self):
        """白名单为空 → 不限制（向后兼容旧数据），审计里要标明 white_list=empty。"""
        self.app_record['white_list'] = ''
        resp = self.call_view(self.api_headers(), remote_addr=OTHER_IP)

        self.assertEqual(200, resp.status_code, '空白名单必须保持不限制（向后兼容）')
        audit = self.last_audit()
        self.assertEqual('ok', audit['result'])
        self.assertIn('white_list=empty', audit['detail'])

        # 只有空白 / 换行 / 逗号的「看起来有内容」的名单，同样视为空
        self.audits = []
        self.app_record['white_list'] = '  \n , \r\n '
        resp = self.call_view(self.api_headers(), remote_addr=OTHER_IP)
        self.assertEqual(200, resp.status_code)
        self.assertIn('white_list=empty', self.last_audit()['detail'])

    # -- 用例 5 ------------------------------------------------------------
    def test_wrong_secret_rejected(self):
        """启用凭据 + 白名单内 IP + 错误 secret → 拒（secret 比对不能被绕过）。"""
        self.app_record['white_list'] = PUBLIC_IP
        resp = self.call_view(self.api_headers(secret='wrong-secret'), remote_addr=PUBLIC_IP)

        self.assertEqual(403, resp.status_code, '密钥错误必须被拒绝')
        audit = self.last_audit()
        self.assertEqual('denied', audit['result'])
        self.assertIn('bad_secret', audit['detail'])

    # -- 用例 6 ------------------------------------------------------------
    def test_panel_api_option_missing_defaults_to_closed(self):
        """`panel_api` 选项缺失 → 默认 open=False → 拒（不再是「默认放行」）。"""
        self.stub_thisdb(option=None, app=self.app_record, option_missing=True)
        resp = self.call_view(self.api_headers())

        self.assertEqual(403, resp.status_code, '选项缺失必须默认关闭 API')
        self.assertEqual({'open': False}, self.option_defaults[-1],
                         'panel_api 的 default 必须与初始化写入的 {"open": False} 一致')
        audit = self.last_audit()
        self.assertEqual('denied', audit['result'])
        self.assertIn('api_closed', audit['detail'])

    # -- 用例 7 ------------------------------------------------------------
    def test_denied_writes_audit_with_expected_args(self):
        """拒绝时必须真的调用 write_audit，且 result='denied'、target=app_id。"""
        self.app_record['status'] = 0
        self.call_view(self.api_headers())

        self.assertEqual(1, len(self.audits), '一次拒绝应当只写一条审计')
        audit = self.audits[0]
        self.assertEqual('api.auth', audit['action'])
        self.assertEqual(APP_ID, audit['target'])
        self.assertEqual('denied', audit['result'])
        self.assertIn(PUBLIC_IP, audit['detail'])

        # 凭据不存在时：审计记的是「请求声称的 app_id」并给出 404（方便追查扫库行为）
        self.audits = []
        self.app_record['app_id'] = 'another-app'
        resp = self.call_view(self.api_headers())
        self.assertEqual(404, resp.status_code, '凭据不存在维持原实现的 404')
        self.assertEqual(APP_ID, self.audits[0]['target'])
        self.assertEqual('denied', self.audits[0]['result'])
        self.assertIn('app_not_found', self.audits[0]['detail'])

    # -- 用例 8 ------------------------------------------------------------
    def test_secret_never_leaks_into_audit(self):
        """审计 detail / 任何参数里都不许出现 secret 明文。"""
        cases = [
            # (记录, 请求头, 来源 IP) —— 覆盖 ok / status_disabled / bad_secret / ip_not_allowed
            ({'status': 1, 'white_list': ''}, self.api_headers(), PUBLIC_IP),
            ({'status': 0, 'white_list': ''}, self.api_headers(), PUBLIC_IP),
            ({'status': 1, 'white_list': PUBLIC_IP}, self.api_headers(secret='wrong-secret'), PUBLIC_IP),
            ({'status': 1, 'white_list': OTHER_IP}, self.api_headers(), PUBLIC_IP),
            ({'status': 1, 'white_list': ''}, self.api_headers(secret=SECRET + '-x'), PUBLIC_IP),
        ]
        for record, headers, ip in cases:
            self.app_record.update(record)
            self.call_view(headers, remote_addr=ip)

        self.assertEqual(len(cases), len(self.audits))
        for audit in self.audits:
            blob = repr(audit)
            self.assertNotIn(SECRET, blob, '审计内容里出现了 app_secret 明文')
            self.assertNotIn('wrong-secret', blob, '审计内容里出现了请求里的密钥明文')
            self.assertNotIn(SECRET + '-x', blob)
            self.assertNotIn('app_secret', audit['detail'])

    # -- 附加：空凭据仍走登录态分支 ------------------------------------------
    def test_no_credentials_falls_through_to_login_branch(self):
        """`App-Id`/`App-Secret` 为空时保持原行为：走登录态判断，不进 API 鉴权。"""
        self.stub_thisdb(option={'open': True}, app=self.app_record)
        resp = self.call_view({}, remote_addr=PUBLIC_IP)
        self.assertEqual(200, resp.status_code)
        self.assertEqual('template:default/path.html', resp.body, '未登录应渲染跳转页')
        self.assertEqual([], self.audits, '登录态分支不应写 api.auth 审计')
        self.assertEqual([], self.option_defaults, '空凭据不应查 panel_api 选项')

        # 已登录 → 直接放行
        with mock.patch.object(self.mod, 'isLogined', lambda: True):
            resp = self.call_view({'App-Id': '', 'App-Secret': ''}, remote_addr=PUBLIC_IP)
        self.assertEqual('view-body', resp.body)

    # -- 附加：白名单格式（与 add_app 写入的「每行1个」口径一致） --------------
    def test_white_list_format_variants(self):
        """换行 / 逗号 / 分号 / 多余空格 / ::ffff: 前缀 / CIDR，都按同一口径解析。"""
        variants = [
            '81.2.69.160',
            '81.2.69.160\n',
            '10.0.0.1\n81.2.69.160',
            '10.0.0.1, 81.2.69.160',
            '10.0.0.1;81.2.69.160',
            '  81.2.69.160  \r\n10.0.0.1',
            '::ffff:81.2.69.160',
            '81.2.0.0/16',
            '10.0.0.0/8\n81.2.0.0/16',
        ]
        for raw in variants:
            self.app_record['white_list'] = raw
            resp = self.call_view(self.api_headers(), remote_addr=PUBLIC_IP)
            self.assertEqual(200, resp.status_code, '白名单 %r 应命中 %s' % (raw, PUBLIC_IP))

        # 脏条目不能把整份名单弄失效
        self.app_record['white_list'] = 'not-an-ip\n\n81.2.69.160'
        self.assertEqual(200, self.call_view(self.api_headers()).status_code)

        # 取不到来源 IP 时 fail closed
        self.app_record['white_list'] = '81.2.69.160'
        resp = self.call_view(self.api_headers(), remote_addr='')
        self.assertEqual(403, resp.status_code, '来源 IP 不可解析时必须拒绝')


class ApiCredentialPureFunctionTest(unittest.TestCase):
    """判定逻辑是纯函数：可直接喂参数断言，不必造请求。"""

    @classmethod
    def setUpClass(cls):
        cls.admin_stub, cls.common_stub = _fake_admin_modules()
        cls.thisdb_stub = types.ModuleType('thisdb')
        cls.patcher = mock.patch.dict(sys.modules, {
            'flask': _fake_flask_module(),
            'admin': cls.admin_stub,
            'admin.common': cls.common_stub,
            'thisdb': cls.thisdb_stub,
        })
        cls.patcher.start()
        cls.mod = _load_under_test()

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()

    def decide(self, **kwargs):
        params = {
            'app_id': APP_ID,
            'app_secret': SECRET,
            'info': {'app_id': APP_ID, 'app_secret': SECRET, 'white_list': '', 'status': 1},
            'client_ip': PUBLIC_IP,
            'open_flag': True,
        }
        params.update(kwargs)
        return self.mod._api_credential_decision(**params)

    def test_uses_real_getclientip(self):
        """取来源 IP 必须走 core.yf.getClientIp（已处理 ::ffff: 与转发头），而不是裸 remote_addr。"""
        self.assertIs(yf, self.mod.yf)
        self.assertIs(yf.getClientIp, self.mod.yf.getClientIp)

    def test_decision_reasons(self):
        cases = [
            ({'open_flag': False}, (False, 'api_closed')),
            ({'info': None}, (False, 'app_not_found')),
            ({'info': {'app_secret': SECRET, 'white_list': '', 'status': 0}}, (False, 'status_disabled')),
            ({'info': {'app_secret': SECRET, 'white_list': '', 'status': None}}, (False, 'status_disabled')),
            ({'info': {'app_secret': SECRET, 'white_list': '', 'status': '1'}}, (True, 'ok:white_list=empty')),
            ({'info': {'app_secret': SECRET, 'white_list': OTHER_IP, 'status': 1}},
             (False, 'ip_not_allowed:%s' % PUBLIC_IP)),
            ({'app_secret': 'nope', 'info': {'app_secret': SECRET, 'white_list': '', 'status': 1}},
             (False, 'bad_secret')),
            ({}, (True, 'ok:white_list=empty')),
        ]
        for kwargs, expected in cases:
            self.assertEqual(expected, self.decide(**kwargs), '参数 %r' % (kwargs,))

    def test_status_accepts_only_one(self):
        """`status` 只有 1 算启用；0 / None / 脏数据全部按停用（默认关门）。"""
        for status in (0, '0', None, '', 'disabled'):
            self.assertFalse(self.mod._status_enabled(status), 'status=%r 不应算启用' % (status,))
        for status in (1, '1'):
            self.assertTrue(self.mod._status_enabled(status), 'status=%r 应算启用' % (status,))

    def test_ip_parsing_helpers(self):
        self.assertEqual([], self.mod._parse_white_list(''))
        self.assertEqual([], self.mod._parse_white_list(' \r\n , '))
        self.assertEqual([], self.mod._parse_white_list(None))
        self.assertEqual(['1.2.3.4', '5.6.7.8'],
                         self.mod._parse_white_list('1.2.3.4\n 5.6.7.8\r\n'))
        self.assertEqual(['1.2.3.4', '5.6.7.8'], self.mod._parse_white_list('1.2.3.4,5.6.7.8'))
        self.assertTrue(self.mod._ip_in_white_list('1.2.3.4', '1.2.3.4'))
        self.assertTrue(self.mod._ip_in_white_list('1.2.3.4', '::ffff:1.2.3.4'))
        self.assertTrue(self.mod._ip_in_white_list('1.2.3.4', '1.2.0.0/16'))
        self.assertTrue(self.mod._ip_in_white_list('2001:db8::1', '2001:db8::/32'))
        self.assertFalse(self.mod._ip_in_white_list('1.2.3.4', '5.6.7.8'))
        self.assertFalse(self.mod._ip_in_white_list('', '1.2.3.4'))
        self.assertFalse(self.mod._ip_in_white_list('1.2.3.4', 'garbage'))


if __name__ == '__main__':
    unittest.main()
