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
   **口令是唯一例外**：用户裁定（P0-1④ follow-up）放宽为「可打印字符 + 强制引用」，
   写入侧只挡控制字符，安全性完全由拼接侧的单引号包裹承担 —— 故 `test_17` 会把
   恶意口令真拼进 dump 命令，用 `shlex.split` 断言它仍只是一个 `-p<pass>` 词元。
4. **对称**：同一组载荷在两端得到完全相同的结果；两端 `safe_check_args` 调用点数量相等。
5. **行为**：库名/同步标识/用户名/ip/端口/datadir 的恶意载荷（`;`、`$()`、反引号、`|`、
   `&&`、换行、单引号突破）被拒；口令只拒控制字符（NUL/换行/回车/制表符/DEL）与空串/
   超长，含引号/`$`/反引号/空白的口令被**接受**但必须被单引号正确包裹。
6. **SQL 汇点**（P0-1④ 延伸）：口令不再被白名单保证「无引号」，`doFullSyncUser` 里
   `stop/start ... user='{}' password='{}'`（含主库回传的 `uinfo` 凭据）的 SQL 字面量
   必须改走 ORM 参数化（`db.query(sql, params)`），由 pymysql 按 SQL 语义转义
   （`test_30`/`test_31`）。

每条断言都要求「真能失败」，由 `test/p0_db_injection_mutation_probe.py` 逐处回退自证。
"""
import ast
import os
import re
import shlex
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

#: 口令口径（用户裁定 P0-1④ follow-up）：只拒控制字符与空/超长；引号/`$`/反引号/
#: 空白/shell 元字符一律放行 —— 安全性由拼接侧 `yf.shlexQuote` 承担。
PASS_BAD = ['p\nx', 'p\rx', 'p\tx', 'p\x00x', 'p\x7fx', 'p\x1bx', 'a' * 129, '']
PASS_OK = ["p'w", 'p$(id)', 'p`id`', 'p|x', 'p&&x', 'p x', 'p;id', 'p$!#*()', 'p"w',
           'p\\w', 'p>id', 'p<id', 'p@ss-W0rd', 'Abc123', 'a.b-c+d%:,', 'a' * 128]

#: 拼进 mysqldump/mariadb-dump 命令行的恶意口令（单引号突破 + 命令注入）
HOSTILE_PASS = ["p'w", "'; touch /tmp/pwned; #", 'p$(id)', 'p`id`', 'p|x', 'p&&x',
                'p x', 'p$!#*()', 'p"w', 'p\\w']


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


def _dump_command(path, pass_value):
    """取出插件 `doFullSyncUser` 里 `dump_sql_data = ...` 的拼接表达式，用给定口令求值。

    直接求值而不是只做 AST 检查：只有真把恶意口令拼进命令行，才能用 `shlex.split`
    看出「shell 会不会把口令拆成额外词元」。
    """
    tree = ast.parse(_read(path))
    fn = _find_func(tree, 'doFullSyncUser')
    assert fn is not None, '%s 缺少 doFullSyncUser' % path
    assign = None
    for node in ast.walk(fn):
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'dump_sql_data'
                        for t in node.targets)):
            assign = node
    assert assign is not None, '%s.doFullSyncUser 缺少 dump_sql_data 拼接' % path
    ns = {
        'yf': yf,
        'getServerDir': lambda: '/www/server/mysql',
        'dmp_option': '--opt',
        'ssl_mode': '--ssl-mode=DISABLED',
        'sync_db': 'demo1',
        'bak_file': '/tmp/bak.sql',
        'ip': '10.0.0.2',
        'port': '3306',
        'user': 'repl_user',
        'apass': pass_value,
    }
    expr = ast.Expression(body=assign.value)
    return eval(compile(ast.fix_missing_locations(expr), path, 'eval'), ns)


def _credential_query_calls(path):
    """把同步账号凭据（`apass` / `uinfo`）送进 SQL 的 `db.query(...)` 调用点。

    `uinfo` 是主库 SSH 回传的 `{'username','password'}`，与 `apass` 同一数据流。
    """
    tree = ast.parse(_read(path))
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'query'):
            continue
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        if names & {'apass', 'uinfo'}:
            out.append(node)
    return out


def _params_expr(call):
    """`db.query(sql, params)` 的 params 表达式（位置参或关键字参）。"""
    if len(call.args) > 1:
        return call.args[1]
    for kw in call.keywords:
        if kw.arg == 'params':
            return kw.value
    return None


class _QueryRecorder(object):
    """记录 `db.query(sql, params)` 的桩，替掉真 ORM（本机不装 pymysql）。"""

    def __init__(self):
        self.calls = []

    def query(self, sql, params=None):
        self.calls.append((sql, params))
        return []


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

    def test_06_user_strict_pass_control_chars_only(self):
        # 用户名口径**不放宽**：仍拒引号/空白/shell 元字符
        for payload in USER_BAD:
            self.assertEqual('', yf.safeSyncUser(payload), 'user 未拦：%r' % payload)
        for value in USER_OK:
            self.assertNotEqual('', yf.safeSyncUser(value), 'user 误伤：%r' % value)
        # 口令只拒控制字符/空/超长（用户裁定 P0-1④ follow-up）
        for payload in PASS_BAD:
            self.assertEqual('', yf.safeSyncPass(payload), 'pass 未拦：%r' % payload)
        for value in PASS_OK:
            self.assertEqual(value, yf.safeSyncPass(value), 'pass 误伤：%r' % value)

    def test_07_quote_and_metachar_passwords_are_accepted(self):
        # 报告原文里的载荷：`-p'<pass>'` 的突破靠拼接侧 shlexQuote，不再靠拒字符
        for value in ("x' -oProxyCommand=id #", "';id;'", "p'w", 'p$(id)', 'p`id`',
                      'p;id', 'p|x', 'p&&x', 'p x', 'p$!#'):
            self.assertEqual(value, yf.safeSyncPass(value), '口令被误拒：%r' % value)

    def test_08_pass_rejects_control_chars_and_length_overflow(self):
        # 防 `$` 锚定漏网：结尾换行/回车/NUL/制表符/DEL 必须仍被拒
        for payload in PASS_BAD:
            self.assertEqual('', yf.safeSyncPass(payload), '口令未拦：%r' % payload)
        self.assertEqual('', yf.safeSyncPass('abc\n'), '结尾换行漏网（`$` 锚定写法）')
        self.assertEqual('', yf.safeSyncPass('abc\r\n'))
        self.assertEqual('', yf.safeSyncPass('abc\x00'))
        self.assertEqual('a' * 128, yf.safeSyncPass('a' * 128))
        self.assertEqual('', yf.safeSyncPass('a' * 129))

    def test_09_pass_regex_is_fullmatch_not_dollar(self):
        """口令正则不得改用 `$` 锚定（`$` 会在结尾换行前匹配）。"""
        tree = ast.parse(_read(VALIDATE_SRC))
        pattern = None
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == '_SYNC_PASS_RE'
                            for t in node.targets)):
                pattern = node.value.args[0].value
        self.assertIsNotNone(pattern, '未找到 _SYNC_PASS_RE')
        self.assertNotIn('$', pattern, '口令正则不得用 `$` 锚定：%r' % pattern)
        fn = _find_func(tree, 'safeSyncPass')
        self.assertTrue(_calls(fn, 'fullmatch'),
                        'safeSyncPass 必须用 fullmatch 锚定整串：%s' % VALIDATE_SRC)


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

    def test_17_dump_command_quotes_hostile_passwords(self):
        """口令口径放宽后，安全性全靠拼接侧单引号包裹 —— 真拼一遍验证。

        对每条恶意口令取出 `dump_sql_data` 的拼接结果，用 `shlex.split` 看 shell
        分词：必须仍然只有一个 `-p<pass>` 词元、总词元数与普通口令一致。
        """
        for label, path in (('mysql', MYSQL_SRC), ('mariadb', MARIADB_SRC)):
            baseline = shlex.split(_dump_command(path, 'plainpw'))
            for payload in HOSTILE_PASS:
                cmd = _dump_command(path, payload)
                try:
                    tokens = shlex.split(cmd)
                except ValueError as exc:
                    self.fail('%s 恶意口令破坏了引号配对（%s）：%r → %r'
                              % (label, exc, payload, cmd))
                self.assertIn(yf.shlexQuote(payload), cmd,
                              '%s 拼接侧未走 shlexQuote：%r' % (label, payload))
                self.assertIn('-p' + payload, tokens,
                              '%s 口令未被单引号包裹：%r → %r' % (label, payload, cmd))
                self.assertEqual(len(baseline), len(tokens),
                                 '%s 恶意口令改变了命令词元数（注入成功）：%r → %r'
                                 % (label, payload, tokens))
                self.assertNotIn('touch', tokens,
                                 '%s 恶意口令突破了引号：%r → %r' % (label, payload, tokens))


class SyncAccountSqlLiteralTest(unittest.TestCase):
    """四、P0-1④ 延伸：口令口径放宽后，mysql 的 STOP/START SLAVE SQL 字面量不得再拼字符串。

    `doFullSyncUser` 里 `stop/start ... user='{}' password='{}'` 过去靠「口令不含引号」
    的白名单兜底；口径放宽后必须改成 ORM 参数化（`web/core/orm.py::query(sql, params)`
    → `cursor.execute(sql, params)`，由 pymysql 按 SQL 语义转义，不手写 `\\'`）。
    同一数据流的 `uinfo`（主库回传的同步账号凭据）同样不得拼进 SQL 文本。
    """

    def test_30_credentials_reach_sql_as_params_not_sql_text(self):
        calls = _credential_query_calls(MYSQL_SRC)
        self.assertEqual(3, len(calls),
                         '把同步账号凭据送进 SQL 的 db.query 调用点应恰为 3 处（stop/start/uinfo）')
        for call in calls:
            sql_names = {n.id for n in ast.walk(call.args[0]) if isinstance(n, ast.Name)}
            self.assertEqual(set(), sql_names & {'apass', 'uinfo'},
                             'mysql/index.py:%d 仍把凭据拼进 SQL 文本' % call.lineno)
            params = _params_expr(call)
            self.assertIsNotNone(params, 'mysql/index.py:%d 缺参数化 params' % call.lineno)
            params_names = {n.id for n in ast.walk(params) if isinstance(n, ast.Name)}
            self.assertTrue(params_names & {'apass', 'uinfo'},
                            'mysql/index.py:%d 的 params 未携带凭据' % call.lineno)

    def test_31_hostile_pass_never_lands_in_sql_text(self):
        calls = _credential_query_calls(MYSQL_SRC)
        payloads = HOSTILE_PASS + ['p\\w', 'p%p_p', "a'b", 'p_%s%', 'p"; DROP TABLE x; --']
        for payload in payloads:
            for call in calls:
                recorder = _QueryRecorder()
                ns = {'db': recorder, 'slave_name': 'replica', 'user': 'repl_user',
                      'apass': payload,
                      'uinfo': {'username': 'repl_user', 'password': payload}}
                eval(compile(ast.fix_missing_locations(ast.Expression(body=call)),
                             MYSQL_SRC, 'eval'), ns)
                self.assertEqual(1, len(recorder.calls),
                                 'mysql/index.py:%d 未调用 db.query' % call.lineno)
                sql, params = recorder.calls[0]
                self.assertNotIn(payload, sql, '口令被拼进 SQL 文本：%r' % sql)
                self.assertNotIn('repl_user', sql, '用户名被拼进 SQL 文本：%r' % sql)
                self.assertIn(payload, tuple(params), '口令未按参数传递：%r' % (params,))
                self.assertEqual(2, sql.count('%s'),
                                 'SQL 占位符数量与参数不符（pymysql mogrify 会报错）：%r' % sql)


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
