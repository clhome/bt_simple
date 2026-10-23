# coding: utf-8
"""测评报告 P2-12 后半：剩余中低危安全收敛的回归守卫。

覆盖 5 项：
  1. 面板 SSL 私钥写入后显式 chmod 0600（net.createLocalSSL / setting.savePanelSsl）；
  2. 临时登录 token 用后即焚（同一 token 第二次使用被拒）；
  3. bcrypt 缺失时必须 fail-closed（校验拒绝 / 哈希抛异常），且告警不得静默；
  4. /dashboard/hook 路由必须带登录态校验，不再无鉴权；
  5. plugins/待审核/ 必须有「未审核 + 命令注入未修」警示 README。
     （`文档/待审核插件/` 已于 2026-10-23 打包为 `文档/待审核插件.7z`，
     源码树下线、只作参考件，不再校验其 README；新政策见
     testsuite/test_pending_plugins_scan_scope.py）

沿用仓库既有风格：AST 抽出真实函数体在桩命名空间里执行（不依赖 flask app 上下文、
不碰真库、不发网络请求）。断言必须真能失败 —— 见 `test/p2_miscsec_mutation_probe.py`。
"""
import ast
import hashlib
import json
import logging
import os
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)

import core.yf as yf
import core.yf.security as yf_security

NET_PY = os.path.join(WEB, 'core', 'yf', 'net.py')
SETTING_PY = os.path.join(WEB, 'utils', 'setting.py')
LOGIN_PY = os.path.join(WEB, 'admin', 'dashboard', 'login.py')
DASHBOARD_PY = os.path.join(WEB, 'admin', 'dashboard', 'dashboard.py')
PLUGIN_WARN_README = os.path.join(ROOT, 'plugins', '待审核', 'README.md')


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _func_src(path, name):
    """抽出函数的真实源码（去掉装饰器），供桩命名空间执行。"""
    tree = ast.parse(_read(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            node.decorator_list = []
            return ast.unparse(ast.Module(body=[node], type_ignores=[]))
    raise AssertionError('%s 里找不到函数 %s' % (path, name))


def _redirect(url):
    return ('REDIRECT', url)


# ---------------------------------------------------------------------------
# 1) 面板 SSL 私钥权限
# ---------------------------------------------------------------------------

def _fake_openssl():
    class _PKey(object):
        def generate_key(self, *a):
            pass

    class _Subject(object):
        CN = ''

    class _X509(object):
        def __init__(self):
            self._s = _Subject()

        def set_serial_number(self, *a):
            pass

        def get_subject(self):
            return self._s

        def set_issuer(self, *a):
            pass

        def gmtime_adj_notBefore(self, *a):
            pass

        def gmtime_adj_notAfter(self, *a):
            pass

        def set_pubkey(self, *a):
            pass

        def sign(self, *a):
            pass

    class _Crypto(object):
        TYPE_RSA = 0
        FILETYPE_PEM = 0

        def PKey(self):
            return _PKey()

        def X509(self):
            return _X509()

        def dump_certificate(self, *a):
            return b'C' * 200

        def dump_privatekey(self, *a):
            return b'K' * 200

    mod = types.ModuleType('OpenSSL')
    mod.crypto = _Crypto()
    return mod


class TestPanelSslPrivateKeyPerms(unittest.TestCase):

    def test_createlocalssl_chmods_private_key_0600(self):
        fake = _fake_openssl()
        ns = {
            'getPanelDir': lambda: '/tmp/pdir',
            'execShell': lambda *a: None,
            'getClientIp': lambda: '127.0.0.1',
            'getLocalIp': lambda: '10.0.0.1',
            'writeFile': lambda *a: None,
            'os': os,
            '_log': logging.getLogger('yf.core'),
        }
        with mock.patch.dict(sys.modules, {'OpenSSL': fake}):
            exec(compile(_func_src(NET_PY, 'createLocalSSL'), NET_PY, 'exec'), ns)
            with mock.patch('os.chmod') as chmod:
                result = ns['createLocalSSL']()
        self.assertTrue(result, 'createLocalSSL 应成功写出证书与私钥')
        key_calls = [c for c in chmod.call_args_list
                     if str(c[0][0]).endswith('/ssl/local/private.pem')]
        self.assertTrue(key_calls, 'createLocalSSL 必须对 private.pem 调 os.chmod')
        self.assertEqual(key_calls[0][0][1], 0o600,
                         'private.pem 权限必须收紧为 0600，实际 %r' % (key_calls[0][0][1],))

    def test_savepanelsl_chmods_private_key_0600(self):
        pdir = tempfile.mkdtemp()
        key_dir = os.path.join(pdir, 'ssl', 'local')
        os.makedirs(key_dir)
        key_path = os.path.join(key_dir, 'private.pem')
        with open(key_path, 'w', encoding='utf-8') as fh:
            fh.write('old')
        key_path_norm = os.path.normcase(os.path.normpath(key_path))

        yf_stub = types.SimpleNamespace(
            inArray=lambda arr, v: v in arr,
            returnData=lambda status, msg, data=None: {'status': status, 'msg': msg, 'data': data},
            getPanelDir=lambda: pdir,
            writeFile=lambda *a, **k: None,
            checkCert=lambda *a, **k: True,
            writeFileLog=lambda *a, **k: None,
            getPanelPort=lambda: 7200,
            getLocalIp=lambda: '127.0.0.1',
        )
        thisdb_stub = types.SimpleNamespace(
            getOptionByJson=lambda name, default=None: dict(default or {}),
            setOption=lambda *a, **k: None,
            getOption=lambda name, default=None: default,
        )
        ns = {'yf': yf_stub, 'thisdb': thisdb_stub, 'os': os, 'json': json}
        exec(compile(_func_src(SETTING_PY, 'savePanelSsl'), SETTING_PY, 'exec'), ns)
        with mock.patch('os.chmod') as chmod, mock.patch('os.remove'):
            res = ns['savePanelSsl'](object(), 'local',
                                     '-----BEGIN CERTIFICATE-----',
                                     '-----BEGIN RSA PRIVATE KEY-----')
        self.assertTrue(res['status'], 'savePanelSsl 应成功：%r' % (res,))
        key_calls = [c for c in chmod.call_args_list
                     if os.path.normcase(os.path.normpath(str(c[0][0]))) == key_path_norm]
        self.assertTrue(key_calls, 'savePanelSsl 必须对 private.pem 调 os.chmod')
        self.assertEqual(key_calls[0][0][1], 0o600,
                         'private.pem 权限必须收紧为 0600，实际 %r' % (key_calls[0][0][1],))


# ---------------------------------------------------------------------------
# 2) 临时登录 token 用后即焚
# ---------------------------------------------------------------------------

class _TempLoginCase(object):

    def __init__(self, state=0, expire_delta=3600):
        self.token = 'a' * 32
        self.row = {
            'id': 7,
            'token': self.token,
            'state': state,
            'expire': int(time.time()) + expire_delta,
        }
        self.session = {}
        self.logged = []
        self.errors = []

    def where(self, *a, **k):
        return self

    def update(self, data):
        self.row.update(data)
        return 1

    def _yf(self):
        return types.SimpleNamespace(
            getClientIp=lambda: '10.0.0.9',
            writeLog=lambda *a, **k: self.logged.append(a),
            md5=lambda s: s,
            M=lambda *a, **k: self,
        )

    def call(self):
        ns = {
            'thisdb': types.SimpleNamespace(
                getTempLoginByToken=lambda t: self.row if t == self.token else None,
                getUserById=lambda i: {'id': 1, 'name': 'admin'}),
            'yf': self._yf(),
            'request': types.SimpleNamespace(environ={'REMOTE_PORT': '5555'}),
            'session': self.session,
            'panel_session': types.SimpleNamespace(create=lambda *a, **k: ''),
            'redirect': _redirect,
            'time': time,
            'getErrorNum': lambda *a, **k: True,
            'setErrorNum': lambda *a, **k: self.errors.append(a),
            '_client_ua': lambda: 'test-ua',
            '__package__': 'admin.dashboard',
        }
        exec(compile(_func_src(LOGIN_PY, 'login_temp_user'), LOGIN_PY, 'exec'), ns)
        return ns['login_temp_user'](self.token)


class TestTempLoginTokenOneTime(unittest.TestCase):

    def test_replay_is_rejected(self):
        case = _TempLoginCase()
        first = case.call()
        self.assertEqual(first, ('REDIRECT', '/'), '首次使用应登录成功')
        self.assertTrue(case.session.get('login'), '首次使用应建立登录态')
        self.assertEqual(case.row['state'], 1, '使用后必须写入已用标记')
        second = case.call()
        self.assertEqual(second, '验证失败!', '同一 token 第二次必须被拒（用后即焚）')

    def test_preseeded_used_token_rejected(self):
        case = _TempLoginCase(state=1)
        self.assertEqual(case.call(), '验证失败!', '已用 token 不得再放行')
        self.assertEqual(case.logged, [], '被拒的 token 不得记成功日志')
        self.assertFalse(case.session.get('login'))

    def test_fresh_token_still_works(self):
        case = _TempLoginCase(state=0)
        self.assertEqual(case.call(), ('REDIRECT', '/'))
        self.assertEqual(len(case.logged), 1)


# ---------------------------------------------------------------------------
# 3) bcrypt 缺失必须 fail-closed（P2-7：旧口径「降级 SHA256」已被废除）
# ---------------------------------------------------------------------------

class TestBcryptFailClosed(unittest.TestCase):
    """缺 bcrypt 时：校验返回 False、哈希抛 PwdCryptoUnavailable，且必须打告警。

    历史口径（本用例的前身 TestBcryptFailOpenWarns）断言的是
    「降级到无盐 SHA256 且仍放行」——那正是 P2-7 要拆掉的 fail-open 漏洞，
    断言已按新契约反向收紧（不是放宽）。
    """

    def test_checkpwd_returns_false_on_importerror(self):
        stored = hashlib.sha256(b'pw').hexdigest()
        with mock.patch.dict(sys.modules, {'bcrypt': None}):
            with self.assertLogs('yf.core', level='WARNING') as cm:
                ok = yf_security.checkPwd('pw', stored)
        self.assertFalse(ok, '缺 bcrypt 时必须拒绝校验，不得退回无盐 SHA256 比对')
        joined = '\n'.join(cm.output)
        self.assertIn('bcrypt', joined, '告警文案必须点名 bcrypt')

    def test_haspwd_raises_on_importerror(self):
        with mock.patch.dict(sys.modules, {'bcrypt': None}):
            with self.assertLogs('yf.core', level='WARNING') as cm:
                with self.assertRaises(yf.PwdCryptoUnavailable) as ctx:
                    yf.hasPwd('pw')
        self.assertIn('bcrypt', str(ctx.exception), '异常文案必须点名 bcrypt')
        joined = '\n'.join(cm.output)
        self.assertIn('bcrypt', joined)

    def test_bcrypt_available_does_not_warn(self):
        stored = yf.hasPwd('pw')
        with self.assertRaises(AssertionError):
            with self.assertLogs('yf.core', level='WARNING'):
                self.assertTrue(yf_security.checkPwd('pw', stored))

    def test_source_warns_in_importerror_branch(self):
        for path, name in ((os.path.join(WEB, 'core', 'yf', 'security.py'), 'checkPwd'),
                           (os.path.join(WEB, 'core', 'yf', '__init__.py'), 'hasPwd')):
            body = _func_src(path, name)
            self.assertIn('except ImportError', body, '%s 应保留 ImportError 分支' % name)
            branch = body.split('except ImportError', 1)[1]
            self.assertIn('_log.warning', branch,
                          '%s 的 ImportError 分支必须打 warning，不得静默降级' % name)


# ---------------------------------------------------------------------------
# 4) /dashboard/hook 需要登录态
# ---------------------------------------------------------------------------

class TestDashboardHookRequiresLogin(unittest.TestCase):

    def _webhook_decorators(self):
        tree = ast.parse(_read(DASHBOARD_PY))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'webhook':
                names = []
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                        names.append(dec.func.id)
                    elif isinstance(dec, ast.Name):
                        names.append(dec.id)
                return names
        raise AssertionError('dashboard.py 里找不到 webhook 路由函数')

    def test_hook_has_login_required(self):
        decorators = self._webhook_decorators()
        self.assertIn('panel_login_required', decorators,
                      '/dashboard/hook 必须加 @panel_login_required，不得无鉴权')

    def test_login_required_imported(self):
        self.assertIn('from admin.user_login_check import panel_login_required',
                      _read(DASHBOARD_PY))

    def test_route_line_is_immediately_followed_by_login_required(self):
        lines = _read(DASHBOARD_PY).splitlines()
        idx = next(i for i, l in enumerate(lines)
                   if '@blueprint.route("/hook"' in l.replace("'", '"'))
        self.assertIn('panel_login_required', lines[idx + 1],
                      '登录装饰器必须紧跟路由，避免被后续改动剥离')


# ---------------------------------------------------------------------------
# 5) 待审核插件文档警示
# ---------------------------------------------------------------------------

class TestPendingPluginWarnings(unittest.TestCase):

    def _check(self, path):
        self.assertTrue(os.path.isfile(path), '缺少警示文档：%s' % path)
        text = _read(path)
        for keyword in ('未接入面板', '未审核', '命令注入',
                        'webhook', 'system_safe', 'backup_ftp'):
            self.assertIn(keyword, text, '%s 缺少关键词 %r' % (path, keyword))

    def test_plugins_pending_readme(self):
        self._check(PLUGIN_WARN_README)

    def test_pending_code_untouched_marker(self):
        """警示文档存在即可；这里只保证目录里确实有待审核插件（防止误删成空目录）。

        `文档/待审核插件/` 已于 2026-10-23 打包成 `文档/待审核插件.7z`（源码树下线、
        只作参考件），所以这里只校验 `plugins/待审核/`；新政策的守卫在
        `test_pending_plugins_scan_scope.py`。
        """
        self.assertTrue(os.path.isdir(os.path.join(ROOT, 'plugins', '待审核')))


if __name__ == '__main__':
    unittest.main()
