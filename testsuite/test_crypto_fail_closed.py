# coding: utf-8
"""P2-7：加密组件缺失时必须 **fail-closed**（绝不放行、绝不写弱哈希、绝不落明文）。

被守住的三条 fail-open（整改前都是「静默降级继续跑」）：

  1. `security.py::checkPwd()` 缺 bcrypt → 退回**无盐 SHA256** 比对（等于放行登录）；
  2. `yf/__init__.py::hasPwd()` 缺 bcrypt → 退回**无盐 SHA256** 哈希（等于写弱哈希）；
  3. `security.py::enDoubleCrypt()` 缺 cryptography → `return strings`（等于**明文落盘**）。

用例口径（零外部依赖，不装/不卸任何包）：
  * 「缺库」用 `mock.patch.dict(sys.modules, {'bcrypt': None})` 模拟 ——
    运行时的 `import bcrypt` / `import cryptography` 直接抛 ImportError，
    与真机未装依赖的表现一致；
  * 端到端用例（第 3 组）不走真实系统命令 / 真实数据库：用 AST 抽出**真实函数体**
    在桩命名空间里执行，把「写盘函数」换成记录器 —— 断言**一次写入都没发生**；
  * 静态用例（第 5 组）走 AST，不用正则猜：即使有人把 `return strings` 写成
    `return (strings)` 或多行拼接也照样抓得到。

断言必须真能失败：变异自证见本次 P2-7 报告（把 `raise` 改回 `return strings`
或把 `return False` 改回 SHA256 比对，本文件必须变红）。
"""
import ast
import hashlib
import json
import logging
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)

import core.yf as yf
import core.yf.security as yf_security
import core.db_pwd as db_pwd

SECURITY_PY = os.path.join(WEB, 'core', 'yf', 'security.py')
YF_INIT_PY = os.path.join(WEB, 'core', 'yf', '__init__.py')
PUREFTP_PY = os.path.join(ROOT, 'plugins', 'pureftp', 'index.py')
NOTIFY_EMAIL_PY = os.path.join(WEB, 'admin', 'setting', 'notify_email.py')

#: 模拟「没装 bcrypt」：sys.modules 里置 None 后 import 直接抛 ImportError
MISSING_BCRYPT = {'bcrypt': None}
#: 模拟「没装 cryptography」（含子模块，避免 `from cryptography.fernet import ...` 走缓存）
MISSING_CRYPTO = {'cryptography': None, 'cryptography.fernet': None}

_PLAIN = 'Secr3t-Plaintext-P2-7'


# ---------------------------------------------------------------------------
# 工具：读源码 / AST 抽函数 / 在桩命名空间里执行真实函数体
# ---------------------------------------------------------------------------
def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _func_node(path, name):
    tree = ast.parse(_read(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError('%s 里找不到函数 %s' % (path, name))


def _func_src(path, name):
    node = _func_node(path, name)
    node.decorator_list = []
    return ast.unparse(ast.Module(body=[node], type_ignores=[]))


def _load_func(path, name, ns):
    """把真实函数体放进桩命名空间执行，返回可调用对象。"""
    exec(compile(_func_src(path, name), path, 'exec'), ns)
    return ns[name]


def _import_handlers(node):
    """函数体内所有 `except ImportError` 处理器（递归，含嵌套 try）。"""
    out = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.ExceptHandler):
            continue
        t = sub.type
        if isinstance(t, ast.Name) and t.id == 'ImportError':
            out.append(sub)
        elif isinstance(t, ast.Tuple):
            for elt in t.elts:
                if isinstance(elt, ast.Name) and elt.id == 'ImportError':
                    out.append(sub)
                    break
    return out


def _uses_hashlib_sha256(node):
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Attribute) and sub.attr in ('sha256', 'sha1', 'sha512', 'md5')
                and isinstance(sub.value, ast.Name) and sub.value.id == 'hashlib'):
            return True
    return False


def _returns_name(node, name):
    for sub in ast.walk(node):
        if isinstance(sub, ast.Return) and sub.value is not None:
            v = sub.value
            if isinstance(v, ast.Name) and v.id == name:
                return True
            if (isinstance(v, ast.Call) and isinstance(v.func, ast.Name)
                    and v.func.id == name and not v.args):
                return True
    return False


def _raises(node, exc_name):
    for sub in ast.walk(node):
        if isinstance(sub, ast.Raise) and isinstance(sub.exc, ast.Call):
            fn = sub.exc.func
            if isinstance(fn, ast.Name) and fn.id == exc_name:
                return True
        if isinstance(sub, ast.Raise) and isinstance(sub.exc, ast.Name) and sub.exc.id == exc_name:
            return True
    return False


class _Recorder(object):
    """记录「有没有发生写入」的替身。"""

    def __init__(self):
        self.calls = []

    def __call__(self, *a, **k):
        self.calls.append((a, k))


class _FakeLog(object):
    def __init__(self):
        self.errors = []
        self.debugs = []

    def error(self, *a, **k):
        self.errors.append(a)

    def warning(self, *a, **k):
        self.errors.append(a)

    def debug(self, *a, **k):
        self.debugs.append(a)

    def info(self, *a, **k):
        self.debugs.append(a)


# ---------------------------------------------------------------------------
# 1) 缺 bcrypt：校验拒绝、哈希抛异常、历史哈希路径不受影响
# ---------------------------------------------------------------------------
class TestMissingBcryptFailClosed(unittest.TestCase):

    def test_exceptions_are_exported_from_package(self):
        """`yf.PwdCryptoUnavailable` / `yf.DataCryptUnavailable` 必须能从包门面取到。"""
        self.assertIs(yf.PwdCryptoUnavailable, yf_security.PwdCryptoUnavailable)
        self.assertIs(yf.DataCryptUnavailable, yf_security.DataCryptUnavailable)
        self.assertTrue(issubclass(yf.PwdCryptoUnavailable, RuntimeError))
        self.assertTrue(issubclass(yf.DataCryptUnavailable, RuntimeError))

    def test_hasPwd_raises_when_bcrypt_missing(self):
        with mock.patch.dict(sys.modules, MISSING_BCRYPT):
            with self.assertRaises(yf.PwdCryptoUnavailable) as ctx:
                yf.hasPwd('pw')
        msg = str(ctx.exception)
        self.assertIn('bcrypt', msg, '异常文案必须点名 bcrypt，运维才知道装什么')
        self.assertIn('安装', msg, '异常文案必须给出补救提示')

    def test_checkPwd_returns_false_when_bcrypt_missing(self):
        stored = hashlib.sha256(b'pw').hexdigest()
        with mock.patch.dict(sys.modules, MISSING_BCRYPT):
            with self.assertLogs('yf.core', level='WARNING'):
                got = yf_security.checkPwd('pw', stored)
        self.assertFalse(got, '缺 bcrypt 时必须拒绝校验，不得退回无盐 SHA256 比对')

    def test_checkPwdCompat_still_accepts_legacy_md5(self):
        """历史 MD5 存量口令的兼容比对不受影响（老安装升级路径）。"""
        legacy_md5 = yf_security.md5('pw')
        with mock.patch.dict(sys.modules, MISSING_BCRYPT):
            with self.assertLogs('yf.core', level='WARNING'):
                self.assertTrue(yf_security.checkPwdCompat('pw', legacy_md5),
                                '历史 MD5 哈希路径必须仍然可用')
                self.assertFalse(yf_security.checkPwdCompat('bad', legacy_md5))

    def test_checkPwdCompat_still_accepts_legacy_sha256(self):
        legacy_sha = hashlib.sha256('pw'.encode('utf-8')).hexdigest()
        with mock.patch.dict(sys.modules, MISSING_BCRYPT):
            with self.assertLogs('yf.core', level='WARNING'):
                self.assertTrue(yf_security.checkPwdCompat('pw', legacy_sha))

    def test_bcrypt_present_still_works(self):
        """装了 bcrypt 时行为不变（防止把正常路径也搞坏）。"""
        digest = yf.hasPwd('pw')
        self.assertTrue(digest.startswith('$2'), 'bcrypt 在场时必须仍产出 bcrypt 哈希')
        self.assertTrue(yf_security.checkPwd('pw', digest))
        self.assertFalse(yf_security.checkPwd('bad', digest))


# ---------------------------------------------------------------------------
# 2) 缺 cryptography：enDoubleCrypt 抛异常，绝不返回明文
# ---------------------------------------------------------------------------
class TestMissingCryptographyFailClosed(unittest.TestCase):

    def test_enDoubleCrypt_raises_instead_of_returning_plaintext(self):
        ret = None
        with mock.patch.dict(sys.modules, MISSING_CRYPTO):
            with self.assertRaises(yf.DataCryptUnavailable) as ctx:
                ret = yf.enDoubleCrypt('k', _PLAIN)
        # 这条直接守住「不明文落盘」：异常路径下返回值绝不能是明文
        self.assertNotEqual(_PLAIN, ret, 'enDoubleCrypt 失败时不得把入参原样返回（明文落盘）')
        self.assertIsNone(ret)
        msg = str(ctx.exception)
        self.assertIn('cryptography', msg, '异常文案必须点名 cryptography')
        self.assertIn('安装', msg, '异常文案必须给出补救提示')
        self.assertIn('明文', msg, '异常文案必须说明不会以明文保存')

    def test_enDoubleCrypt_still_encrypts_when_available(self):
        token = yf.enDoubleCrypt('k', _PLAIN)
        self.assertNotEqual(_PLAIN, token)
        self.assertNotIn(_PLAIN, token)

    def test_deDoubleCrypt_roundtrip_unaffected(self):
        token = yf.enDoubleCrypt('k', _PLAIN)
        self.assertEqual(_PLAIN, yf.deDoubleCrypt('k', token))


# ---------------------------------------------------------------------------
# 3) 端到端：缺库时代表性调用点「一次写入都不发生」
# ---------------------------------------------------------------------------
class TestNoPlaintextWriteEndToEnd(unittest.TestCase):

    def setUp(self):
        # enDoubleCrypt 内部失败时会写面板日志；换成记录器，不污染真实日志文件
        self.logged = _Recorder()
        patcher = mock.patch.object(yf_security, 'writeFileLog', self.logged)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _pureftp_ns(self):
        """pureftp.addFtp 的桩命名空间：记录所有写库/建用户动作。"""
        writes = []

        class _FakeConn(object):
            def __init__(self):
                self.rows = []

            def where(self, *a, **k):
                return self

            def count(self):
                return 0

            def add(self, fields, values):
                writes.append(('ftps.add', fields, values))
                self.rows.append(values)

        def _pftpDB():
            return _FakeConn()

        def _pftpAdd(user, pwd, path):
            writes.append(('pftpAdd', user, pwd, path))
            return (True, '')

        def _reloadPwDb():
            writes.append(('reloadPwDb',))

        ns = {
            'yf': yf,
            'time': __import__('time'),
            '_PWD_CRYPT_KEY': 'pureftp',
            '_log': _FakeLog(),
            'getArgs': lambda: {'ftp_username': 'yftest_p27',
                                'ftp_password': _PLAIN,
                                'path': '/www/wwwroot/yftest_p27',
                                'ps': 'p2-7'},
            'checkArgs': lambda args, names: (True, None),
            'validUsername': lambda u: True,
            'invalidHomePathReason': lambda p: None,
            'validPassword': lambda p: True,
            'pftpDB': _pftpDB,
            'pftpAdd': _pftpAdd,
            '_reloadPwDb': _reloadPwDb,
        }
        return ns, writes

    def test_pureftp_addFtp_writes_nothing_without_cryptography(self):
        ns, writes = self._pureftp_ns()
        func = _load_func(PUREFTP_PY, 'addFtp', ns)
        with mock.patch.dict(sys.modules, MISSING_CRYPTO):
            res = func()

        self.assertEqual([], writes,
                         '缺 cryptography 时不得建 FTP 用户、不得写库、不得落明文：%r' % (writes,))
        data = json.loads(res)
        self.assertFalse(data['status'], '必须回失败，不能假成功：%r' % (res,))
        self.assertIn('cryptography', data['msg'], '错误文案必须点名缺失的依赖')
        self.assertNotIn(_PLAIN, res, '返回体里不得出现明文口令')

    def test_pureftp_addFtp_writes_ciphertext_when_available(self):
        """对照（正常路径）：装齐依赖时必须真的写一条密文。"""
        ns, writes = self._pureftp_ns()
        func = _load_func(PUREFTP_PY, 'addFtp', ns)
        res = func()
        self.assertEqual('ok', res)
        added = [w for w in writes if w[0] == 'ftps.add']
        self.assertEqual(1, len(added), '正常路径应当写一条 ftps 记录：%r' % (writes,))
        values = added[0][2]
        self.assertNotIn(_PLAIN, values, '落库口令不得是明文')
        self.assertTrue(str(values[2]).startswith('gAAAA'), '落库口令必须是 Fernet 密文')

    def _notify_email_ns(self):
        stores = []
        db = mock.Mock()
        db.getOptionByJson.return_value = {'open': False}

        def _setOption(name, value, type=None):
            stores.append((name, value))

        db.setOption.side_effect = _setOption

        class _Form(object):
            def get(self, key, default=''):
                payload = {'tag': 'email',
                           'data': json.dumps({'smtp_host': 'smtp.example.com',
                                               'username': 'u',
                                               'password': _PLAIN})}
                return payload.get(key, default)

        ns = {
            'yf': yf,
            'json': json,
            'request': type('R', (), {'form': _Form()}),
            'thisdb': db,
        }
        return ns, stores, db

    def test_notify_email_save_writes_nothing_without_cryptography(self):
        ns, stores, db = self._notify_email_ns()
        func = _load_func(NOTIFY_EMAIL_PY, 'set_notify_email', ns)
        with mock.patch.dict(sys.modules, MISSING_CRYPTO):
            res = func()

        self.assertEqual([], stores, '缺 cryptography 时不得写库（更不得落明文）：%r' % (stores,))
        self.assertEqual([], db.setOption.call_args_list)
        self.assertFalse(res.get('status'), '必须回失败，不能假成功：%r' % (res,))
        self.assertIn('cryptography', res.get('msg', ''))
        self.assertNotIn(_PLAIN, json.dumps(res, ensure_ascii=False))

    def test_notify_email_save_writes_ciphertext_when_available(self):
        ns, stores, db = self._notify_email_ns()
        func = _load_func(NOTIFY_EMAIL_PY, 'set_notify_email', ns)
        res = func()
        self.assertTrue(res.get('status'))
        self.assertEqual(1, len(stores), '正常路径应写一次 notify_email')
        written = stores[0][1]
        self.assertNotIn(_PLAIN, written, '通知口令不得明文落库')
        self.assertIn('cfg', json.loads(written))


# ---------------------------------------------------------------------------
# 4) db_pwd.encrypt_pwd：缺库时向上抛，不返回「带 MARKER 的明文」
# ---------------------------------------------------------------------------
class TestDbPwdWriteSideFailClosed(unittest.TestCase):

    def setUp(self):
        self.logs = []
        db_pwd.set_log_writer(self.logs.append)
        self.addCleanup(db_pwd.set_log_writer, None)

    def test_encrypt_pwd_raises_without_cryptography(self):
        ret = None
        with mock.patch.dict(sys.modules, MISSING_CRYPTO):
            with self.assertRaises(yf.DataCryptUnavailable):
                ret = db_pwd.encrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, _PLAIN)
        self.assertIsNone(ret)
        # 无论是裸明文还是 yfenc: 前缀的明文都不允许出现
        self.assertNotEqual(_PLAIN, ret)
        self.assertNotEqual(db_pwd.MARKER + _PLAIN, ret)
        self.assertTrue(any('encrypt_pwd' in str(m) for m in self.logs),
                        '拒绝写入必须留日志：%r' % (self.logs,))

    def test_encrypt_pwd_returns_marker_ciphertext_when_available(self):
        enc = db_pwd.encrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, _PLAIN)
        self.assertTrue(db_pwd.is_encrypted(enc), '正常路径必须带 MARKER')
        self.assertNotIn(_PLAIN, enc)
        self.assertEqual(_PLAIN, db_pwd.decrypt_pwd(db_pwd.SCOPE_MYSQL_ROOT, enc))


# ---------------------------------------------------------------------------
# 5) 静态断言：except 分支里不许再有退化实现
# ---------------------------------------------------------------------------
class TestStaticNoFailOpenBranch(unittest.TestCase):

    def test_enDoubleCrypt_never_returns_input_on_error(self):
        node = _func_node(SECURITY_PY, 'enDoubleCrypt')
        handlers = [n for n in ast.walk(node) if isinstance(n, ast.ExceptHandler)]
        self.assertTrue(handlers, 'enDoubleCrypt 必须保留异常分支')
        for h in handlers:
            self.assertFalse(
                _returns_name(h, 'strings'),
                'enDoubleCrypt 的 except 分支不得 `return strings`（明文落盘）：第 %d 行'
                % getattr(h, 'lineno', -1))
        self.assertTrue(any(_raises(h, 'DataCryptUnavailable') for h in handlers),
                        'enDoubleCrypt 的 except 分支必须抛 DataCryptUnavailable')

    def test_hasPwd_importerror_branch_has_no_sha256_fallback(self):
        node = _func_node(YF_INIT_PY, 'hasPwd')
        handlers = _import_handlers(node)
        self.assertTrue(handlers, 'hasPwd 必须保留 except ImportError 分支')
        for h in handlers:
            self.assertFalse(_uses_hashlib_sha256(h),
                             'hasPwd 的 ImportError 分支不得退回 SHA256 哈希')
            self.assertTrue(_raises(h, 'PwdCryptoUnavailable'),
                            'hasPwd 的 ImportError 分支必须抛 PwdCryptoUnavailable')

    def test_checkPwd_importerror_branch_has_no_sha256_fallback(self):
        node = _func_node(SECURITY_PY, 'checkPwd')
        handlers = _import_handlers(node)
        self.assertTrue(handlers, 'checkPwd 必须保留 except ImportError 分支')
        for h in handlers:
            self.assertFalse(_uses_hashlib_sha256(h),
                             'checkPwd 的 ImportError 分支不得退回 SHA256 比对')
            self.assertTrue(
                any(isinstance(s, ast.Return) and isinstance(s.value, ast.Constant)
                    and s.value.value is False for s in ast.walk(h)),
                'checkPwd 的 ImportError 分支必须 return False（拒绝校验）')

    def test_enDoubleCrypt_algorithm_untouched(self):
        """红线：只改异常分支，算法本体（key 派生 + Fernet.encrypt）不得动。"""
        body = _func_src(SECURITY_PY, 'enDoubleCrypt')
        self.assertIn('Fernet', body)
        self.assertIn('urlsafe_b64encode', body)
        self.assertIn('f.encrypt(strings)', body)

    def test_legacy_hash_branch_of_checkPwdCompat_kept(self):
        """checkPwdCompat 的历史 MD5/SHA256 分支必须保留（老安装升级路径）。"""
        body = _func_src(SECURITY_PY, 'checkPwdCompat')
        self.assertIn('isLegacyPwdHash', body)
        self.assertIn('hmac.compare_digest', body)


if __name__ == '__main__':
    unittest.main(verbosity=2)
