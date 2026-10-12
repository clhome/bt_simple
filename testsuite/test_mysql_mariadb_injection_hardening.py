# coding: utf-8
"""P0-1②③④ 修复守卫：MySQL / MariaDB 命令注入（root RCE）。

测评报告点名的三处（②datadir、③fullSync db/sign、④主从同步账号存储型注入）
历史上都是「修了一半」——mysql 侧有 `safe_check_args`、mariadb 整文件 0 处；本用例
把「两端同口径」这件事钉死，并把每处注入点的恶意载荷都跑一遍。

锁死的内容：

1. **公共实现唯一**：`web/core/yf/validate.py` 是唯一白名单来源，两端 `safe_check_args`
   都只是 `yf.dbSafeCheckArgs` 的薄委托（改回各自的正则即红）。
2. **写入侧入口**：`addSlaveSyncUser` 两端都过 `safeSyncIp/safeSyncPort/safeSyncUser/
   safeSyncPass`；`setMyDbPos` 两端都过 `safeDatadir` 且非法即 return。
3. **拼接侧双保险**：`setMyDbPos`/`fullSync`/`doFullSyncUser` 的 `execShell` 参数里
   必须出现 `yf.shlexQuote`，且 `-p'<pass>'` 这种可被单引号突破的写法不得复活。
4. **对称**：同一组载荷在两端得到完全相同的结果；两端 `safe_check_args` 调用点数量相等。
5. **行为**：恶意载荷（`;`、`$()`、反引号、`|`、`&&`、换行、单引号突破）被拒，
   合法值（IPv4/IPv6、正常路径/账号）仍放行。

每条断言都要求「真能失败」，由 `test/p0_db_injection_mutation_probe.py` 逐处回退自证。
"""
import ast
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.yf as yf  # noqa: E402

MYSQL_SRC = os.path.join(ROOT, 'plugins', 'mysql', 'index.py')
MARIADB_SRC = os.path.join(ROOT, 'plugins', 'mariadb', 'index.py')
VALIDATE_SRC = os.path.join(WEB, 'core', 'yf', 'validate.py')

#: 两端必须完全一致的校验入口数量（mysql 加固前就有 7 处，mariadb 本轮补齐到 7 处）
SAFE_CHECK_CALLS = 7

#: 通用 shell 元字符载荷（不含空白，靠「拒空白」的旧白名单拦不住）
SHELL_PAYLOADS = [
    'x;id', 'x|id', 'x&&id', 'x$(id)', 'x`id`', 'x\nid', "x'id", 'x"id', 'x id', 'x>id', 'x<id',
]

DATADIR_BAD = [
    '/tmp/x;id', '/tmp/x$(id)', '/tmp/x`id`', '/tmp/x|id', '/tmp/x&&id', '/tmp/x\nid',
    '/tmp/x y', '/a/../b', 'relative/dir', '', '/', '/tmp/' + 'a' * 200,
]
DATADIR_OK = ['/www/server/mysql/data', '/data/mysql-8.0', '/tmp/a_b.c']

IP_BAD = ['127.0.0.1;id', '127.0.0.1$(id)', '127.0.0.1`id`', 'localhost', '1.2.3.4 5',
          '', '999.1.1.1', '1.2.3.4|id']
IP_OK = ['127.0.0.1', '::1', '2001:db8::1']

PORT_BAD = ['0', '65536', '-1', '3306;id', 'abc', '', 'None', '3306|x']
PORT_OK = ['3306', 3306, '1', '65535']

USER_BAD = ['u;id', 'u$(id)', 'u`id`', 'u|id', 'u x', "u'x", 'u"x', 'u\nx', '']
USER_OK = ['syncuser', 'repl_user-1', 'repl@host']

PASS_BAD = ["p'w", 'p$(id)', 'p`id`', 'p|x', 'p&&x', 'p\nx', 'p x', '']
PASS_OK = ['p@ss-W0rd', 'Abc123', 'a.b-c+d%:,']


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


def _find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _calls(node, name):
    """函数体内所有 `name(...)`（裸名）或 `.name(...)`（属性）调用节点。"""
    out = []
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name) and f.id == name:
            out.append(n)
        elif isinstance(f, ast.Attribute) and f.attr == name:
            out.append(n)
    return out


def _attr_call_names(node):
    """函数体内所有 `xxx.attr(...)` 的 attr 名。"""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            out.append(n.func.attr)
    return out


def _string_consts(node):
    return [n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _load_safe_check_args(path):
    """把插件里的 `safe_check_args` 函数体单独编译出来，供行为对称测试真调用。"""
    tree = ast.parse(_read(path))
    fn = _find_func(tree, 'safe_check_args')
    assert fn is not None, '%s 缺少 safe_check_args' % path
    module = ast.Module(body=[fn], type_ignores=[])
    ns = {'yf': yf, 're': re}
    exec(compile(module, path, 'exec'), ns)
    return ns['safe_check_args']


class SharedValidatorTest(unittest.TestCase):
    """一、公共白名单实现本身的行为（两端共用，故一处通过即两端通过）。"""

    def test_01_datadir_rejects_shell_metachars(self):
        for payload in DATADIR_BAD:
            self.assertEqual('', yf.safeDatadir(payload), 'datadir 未拦：%r' % payload)

    def test_02_datadir_accepts_legit_absolute_paths(self):
        for value in DATADIR_OK:
            self.assertEqual(value, yf.safeDatadir(value), 'datadir 误伤：%r' % value)

    def test_03_db_sign_username_whitelist(self):
        for payload in SHELL_PAYLOADS:
            self.assertFalse(yf.dbSafeCheckArgs(db_name=payload), 'db_name 未拦：%r' % payload)
            self.assertFalse(yf.dbSafeCheckArgs(sign_val=payload), 'sign 未拦：%r' % payload)
            self.assertFalse(yf.dbSafeCheckArgs(username=payload), 'username 未拦：%r' % payload)
        self.assertTrue(yf.dbSafeCheckArgs(db_name='demo1', sign_val='a.b:c-d', username='root'))

    def test_04_ip_ipv4_ipv6(self):
        for payload in IP_BAD:
            self.assertEqual('', yf.safeSyncIp(payload), 'ip 未拦：%r' % payload)
        for value in IP_OK:
            self.assertNotEqual('', yf.safeSyncIp(value), 'ip 误伤：%r' % value)

    def test_05_port_range(self):
        for payload in PORT_BAD:
            self.assertIsNone(yf.safeSyncPort(payload), 'port 未拦：%r' % payload)
        for value in PORT_OK:
            self.assertIsNotNone(yf.safeSyncPort(value), 'port 误伤：%r' % value)
        self.assertEqual(3306, yf.safeSyncPort('3306'))

    def test_06_user_pass_charset(self):
        for payload in USER_BAD:
            self.assertEqual('', yf.safeSyncUser(payload), 'user 未拦：%r' % payload)
        for payload in PASS_BAD:
            self.assertEqual('', yf.safeSyncPass(payload), 'pass 未拦：%r' % payload)
        for value in USER_OK:
            self.assertNotEqual('', yf.safeSyncUser(value), 'user 误伤：%r' % value)
        for value in PASS_OK:
            self.assertNotEqual('', yf.safeSyncPass(value), 'pass 误伤：%r' % value)

    def test_07_single_quote_breakout_is_rejected(self):
        # 报告原文：`-p'<pass>'` 的单引号可被 pass 内的 `'` 突破
        self.assertEqual('', yf.safeSyncPass("x' -oProxyCommand=id #"))
        self.assertEqual('', yf.safeSyncPass("';id;'"))


class PluginSymmetryTest(unittest.TestCase):
    """二、两端同口径（防止再次「修了一半」）。"""

    @classmethod
    def setUpClass(cls):
        cls.mysql_src = _read(MYSQL_SRC)
        cls.mariadb_src = _read(MARIADB_SRC)
        cls.mysql = ast.parse(cls.mysql_src)
        cls.mariadb = ast.parse(cls.mariadb_src)

    def _fn(self, tree, name):
        fn = _find_func(tree, name)
        self.assertIsNotNone(fn, '函数缺失：%s' % name)
        return fn

    def test_10_both_delegate_to_shared_validator(self):
        for label, tree in (('mysql', self.mysql), ('mariadb', self.mariadb)):
            fn = self._fn(tree, 'safe_check_args')
            calls = _calls(fn, 'dbSafeCheckArgs')
            self.assertEqual(1, len(calls), '%s.safe_check_args 未委托给 yf.dbSafeCheckArgs' % label)

    def test_11_safe_check_args_call_sites_are_symmetric(self):
        counts = {}
        for label, src in (('mysql', self.mysql_src), ('mariadb', self.mariadb_src)):
            counts[label] = len(_calls(ast.parse(src), 'safe_check_args'))
        self.assertEqual(counts['mysql'], counts['mariadb'],
                         '两端 safe_check_args 调用点不对称：%r' % counts)
        self.assertEqual(SAFE_CHECK_CALLS, counts['mysql'], '调用点数量变化：%r' % counts)

    def test_12_add_slave_sync_user_validates_write_side(self):
        for label, tree in (('mysql', self.mysql), ('mariadb', self.mariadb)):
            names = _attr_call_names(self._fn(tree, 'addSlaveSyncUser'))
            for needed in ('safeSyncIp', 'safeSyncPort', 'safeSyncUser', 'safeSyncPass'):
                self.assertIn(needed, names, '%s.addSlaveSyncUser 缺写入侧校验 %s' % (label, needed))

    def test_13_set_my_db_pos_validates_and_quotes(self):
        for label, tree in (('mysql', self.mysql), ('mariadb', self.mariadb)):
            fn = self._fn(tree, 'setMyDbPos')
            names = _attr_call_names(fn)
            self.assertIn('safeDatadir', names, '%s.setMyDbPos 未过 safeDatadir' % label)
            self.assertIn('shlexQuote', names, '%s.setMyDbPos 拼接侧未 shlexQuote' % label)
            # shlexQuote 结果落到的变量名（q_*）
            safe_names = set()
            for n in ast.walk(fn):
                if (isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                        and isinstance(n.value.func, ast.Attribute)
                        and n.value.func.attr == 'shlexQuote'):
                    for t in n.targets:
                        if isinstance(t, ast.Name):
                            safe_names.add(t.id)
            # execShell 参数里不得再裸拼 datadir（只能是常量或已 quote 的变量）
            for call in _calls(fn, 'execShell'):
                loaded = {n.id for a in call.args for n in ast.walk(a)
                          if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
                self.assertEqual(set(), loaded & {'s_datadir', 't_datadir'},
                                 '%s.setMyDbPos 裸拼 datadir：%r' % (label, loaded))
                self.assertTrue(loaded <= safe_names,
                                '%s.setMyDbPos execShell 用到未转义变量：%r' % (label, loaded - safe_names))

    def test_14_full_sync_validates_and_quotes(self):
        for label, tree in (('mysql', self.mysql), ('mariadb', self.mariadb)):
            fn = self._fn(tree, 'fullSync')
            self.assertTrue(_calls(fn, 'safe_check_args'),
                            '%s.fullSync 缺 safe_check_args' % label)
            self.assertIn('shlexQuote', _attr_call_names(fn),
                          '%s.fullSync 拼接侧未 shlexQuote' % label)

    def test_15_dump_uses_shlex_quote_not_single_quote_wrapping(self):
        for label, tree in (('mysql', self.mysql), ('mariadb', self.mariadb)):
            fn = self._fn(tree, 'doFullSyncUser')
            names = _attr_call_names(fn)
            for needed in ('safeSyncIp', 'safeSyncPort', 'safeSyncUser', 'safeSyncPass'):
                self.assertIn(needed, names, '%s.doFullSyncUser 缺触发侧校验 %s' % (label, needed))
            self.assertIn('shlexQuote', names, '%s.doFullSyncUser 拼接侧未 shlexQuote' % label)
            for text in _string_consts(fn):
                self.assertNotIn("-p'", text,
                                 '%s.doFullSyncUser 仍用单引号包裹口令：%r' % (label, text))

    def test_16_payloads_agree_on_both_sides(self):
        mysql_check = _load_safe_check_args(MYSQL_SRC)
        mariadb_check = _load_safe_check_args(MARIADB_SRC)
        payloads = SHELL_PAYLOADS + ['', 'demo1', 'a.b:c-d', 'valid_user']
        for payload in payloads:
            for kw in ('db_name', 'sign_val', 'username'):
                self.assertEqual(
                    mysql_check(**{kw: payload}), mariadb_check(**{kw: payload}),
                    '两端结果不一致：%s=%r' % (kw, payload))
                self.assertEqual(
                    yf.dbSafeCheckArgs(**{kw: payload}), mysql_check(**{kw: payload}),
                    'mysql 结果与公共实现不一致：%s=%r' % (kw, payload))


class SharedModuleIsSingleSourceTest(unittest.TestCase):
    """三、白名单只此一份，插件里不得再各写一套正则。"""

    def test_20_validate_module_exists(self):
        self.assertTrue(os.path.isfile(VALIDATE_SRC), '缺少公共校验模块 %s' % VALIDATE_SRC)
        for name in ('dbSafeCheckArgs', 'safeDatadir', 'safeSyncIp', 'safeSyncPort',
                     'safeSyncUser', 'safeSyncPass'):
            self.assertTrue(hasattr(yf, name), 'yf 未导出 %s' % name)

    def test_21_plugins_do_not_redefine_whitelist_regexes(self):
        for label, path in (('mysql', MYSQL_SRC), ('mariadb', MARIADB_SRC)):
            tree = ast.parse(_read(path))
            fn = _find_func(tree, 'safe_check_args')
            self.assertEqual([], _calls(fn, 'match'),
                             '%s.safe_check_args 又出现了本地正则' % label)


if __name__ == '__main__':
    unittest.main(verbosity=2)
