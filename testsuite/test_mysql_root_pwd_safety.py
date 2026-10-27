# coding: utf-8
"""P2-5：MySQL root 口令安全（不再拼进 shell 字符串、不再进 argv）。

## 覆盖的问题

`plugins/mysql/index.py` 的 `setRootPwdForce()` / `adjust_password_policy()` 曾把
用户提交的口令拼进**一行 shell 命令**（`yf.execShell()` 默认 `shell=True`）：

    serverdir + f"/bin/mysql -u root -e \\"ALTER USER ... IDENTIFIED BY '{new_password}';\\""
    serverdir + f"/bin/mysql -u root -p'{new_password}' -e 'SHOW DATABASES;'"

口令里出现 `'`、`$()`、反引号即可截断引号或触发命令替换（**以 root 身份执行**）；
验证那一步还把口令拼成 `-p'...'` 直接进 argv，`ps -ef` 全员可见。

## 本用例钉住五件事

1. **SQL 字面量转义**：`_mysqlSqlLiteral()` 按 MySQL 语义逐字符转义，塞进 `'...'`
   之后用 MySQL 语义反解必须等于原文，且不能提前闭合字面量；
2. **option 文件**：`_mysqlClientDefaultsFile()` 落盘 0600、内容可反解、用完能删；
3. **静态（AST）**：两个函数体内不再有「现拼字符串进 execShell」，不再有 `-p'`，
   mysql 调用一律 `execShellRc([[...]], shell=False)`；
4. **行为**：替身跑 `setRootPwdForce("p' OR 1=1 -- ", "8.0")` —— 每条 argv 都是 list、
   口令不出现在任何 argv 元素里（验证步走 defaults-file）、SQL 里是转义后的形态、
   返回 `True` 当且仅当验证步 rc==0、临时 defaults 文件函数返回后被删除；
5. **日志**：失败时 `writeFileLog` 的内容不含口令。

零外部依赖：不连真库、不起真进程（`subprocess.Popen` / `time.sleep` / `start()` 全部替身）。
"""
import ast
import os
import re
import stat
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
IDX = os.path.join(ROOT, 'plugins', 'mysql', 'index.py')

for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 进程级隔离必须早于「会打开面板库的模块」导入
from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('mysql_root_pwd_safety')

import importlib.util  # noqa: E402


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


_MOD = None


def _mysql_module():
    """按路径加载 `plugins/mysql/index.py`（模块级会 chdir 到 web/，这里恢复 cwd）。"""
    global _MOD
    if _MOD is not None:
        return _MOD
    name = 'p25_mysql_index_under_test'
    spec = importlib.util.spec_from_file_location(name, IDX)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    cwd = os.getcwd()
    try:
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
    _MOD = mod
    return mod


# ---------------------------------------------------------------------------
# 反解器：按两种规则的**真实语义**把转义结果还原，用来证明「转义是可逆的」
# ---------------------------------------------------------------------------
#: MySQL 字符串字面量的转义序列（未开启 NO_BACKSLASH_ESCAPES）
_SQL_ESC = {
    '0': '\x00', "'": "'", '"': '"', 'b': '\b', 'n': '\n', 'r': '\r',
    't': '\t', 'Z': '\x1a', '\\': '\\',
}


def _sqlUnescape(inner):
    """把「单引号字面量内部的内容」按 MySQL 语义反解回原文。"""
    out = []
    i = 0
    n = len(inner)
    while i < n:
        ch = inner[i]
        if ch == '\\' and i + 1 < n:
            nxt = inner[i + 1]
            if nxt in _SQL_ESC:
                out.append(_SQL_ESC[nxt])
                i += 2
                continue
            if nxt in '%_':  # MySQL 里 \% \_ 不是转义序列，反斜杠保留
                out.append('\\')
                out.append(nxt)
                i += 2
                continue
            out.append(nxt)  # 其余 `\x` 等价于 `x`
            i += 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def _unescaped_positions(inner, ch="'"):
    """返回 `inner` 里**未被反斜杠转义**的 `ch` 位置（字面量提前闭合的证据）。"""
    pos = []
    i = 0
    n = len(inner)
    while i < n:
        if inner[i] == '\\':
            i += 2
            continue
        if inner[i] == ch:
            pos.append(i)
        i += 1
    return pos


#: mysql option 文件的转义序列（值用双引号包）
_OPT_ESC = {
    'b': '\b', 't': '\t', 'n': '\n', 'r': '\r', '\\': '\\', 's': ' ',
    '"': '"', "'": "'",
}


def _optionUnescape(inner):
    """把 option 文件双引号值内部的内容按 option-file 语义反解回原文。"""
    out = []
    i = 0
    n = len(inner)
    while i < n:
        ch = inner[i]
        if ch == '\\' and i + 1 < n:
            nxt = inner[i + 1]
            if nxt in _OPT_ESC:
                out.append(_OPT_ESC[nxt])
            else:
                out.append(nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


#: 表驱动用例：口令里能出现的「危险字符」全覆盖 + 组合串
_LITERAL_CASES = [
    'plain123',
    "it's",                       # 单引号（原来直接截断 shell 单引号）
    'back\\slash',                # 反斜杠
    '$(id)',                      # 命令替换
    '`id`',                       # 反引号命令替换
    'double"quote',               # 双引号
    'line1\nline2',               # 换行
    'cr\rx',                      # 回车
    'nul\x00x',                   # NUL
    'ctrlz\x1ax',                 # 0x1a
    "p@ss'\";$(id)`",             # 组合串
    "'; DROP TABLE mysql.user; -- ",   # 经典闭合注入
    "\\' OR 1=1 -- ",             # 反斜杠 + 引号组合
    "trail\\",                    # 末尾反斜杠（最容易二次转义的坑）
    '中文口令$()',                 # 非 ASCII
]


class TestMysqlSqlLiteral(unittest.TestCase):
    """`_mysqlSqlLiteral`：MySQL 字符串字面量转义，逐字符验证。"""

    def setUp(self):
        self.lit = _mysql_module()._mysqlSqlLiteral

    def test_01_table_driven_roundtrip(self):
        for raw in _LITERAL_CASES:
            with self.subTest(raw=raw):
                inner = self.lit(raw)
                # 1) 不能提前闭合字面量：内部不得出现未转义的单引号
                self.assertEqual([], _unescaped_positions(inner, "'"),
                                 '转义结果里有未转义的单引号，能提前闭合字面量: %r' % inner)
                # 2) 塞进 '...' 后按 MySQL 语义反解，必须逐字符等于原文
                self.assertEqual(raw, _sqlUnescape(inner),
                                 '转义不可逆，反解结果与原文不符: %r -> %r' % (raw, inner))

    def test_02_expected_escapes(self):
        """关键字符的转义形态逐条钉死（防「悄悄改成别的规则」）。"""
        self.assertEqual(r"a\'b", self.lit("a'b"))
        self.assertEqual('a\\\\b', self.lit('a\\b'))
        self.assertEqual(r'a\"b', self.lit('a"b'))
        self.assertEqual(r'a\0b', self.lit('a\x00b'))
        self.assertEqual(r'a\nb', self.lit('a\nb'))
        self.assertEqual(r'a\rb', self.lit('a\rb'))
        self.assertEqual(r'a\Zb', self.lit('a\x1ab'))
        # 不带 shell 语义的字符一律原样（多转义反而会改口令）
        self.assertEqual('$(id)', self.lit('$(id)'))
        self.assertEqual('a`b', self.lit('a`b'))
        self.assertEqual('a;b', self.lit('a;b'))

    def test_03_backslash_before_quote(self):
        """`\\'` 这类组合不能变成「转义反斜杠 + 裸引号」。"""
        raw = "\\'"
        inner = self.lit(raw)
        self.assertEqual('\\\\\\\'', inner)
        self.assertEqual([], _unescaped_positions(inner, "'"))
        self.assertEqual(raw, _sqlUnescape(inner))

    def test_04_sql_built_from_literal_is_parseable(self):
        """拼进真实 SQL 语句后，口令整体仍在同一个字面量里。"""
        pwd = "p@ss'\";$(id)`"
        sql = "ALTER USER 'root'@'localhost' IDENTIFIED BY '" + self.lit(pwd) + "';"
        body = sql.split("IDENTIFIED BY '", 1)[1]
        # 找第一个「未转义的单引号」= 字面量真正的结束位置
        end = _unescaped_positions(body, "'")[0]
        self.assertEqual("';", body[end:], '口令没被完整包在一个字面量里: %r' % sql)
        self.assertEqual(pwd, _sqlUnescape(body[:end]))

    def test_05_none_and_non_str(self):
        self.assertEqual('', self.lit(None))
        self.assertEqual('123', self.lit(123))


class TestMysqlClientDefaultsFile(unittest.TestCase):
    """`_mysqlClientDefaultsFile`：0600 临时 option 文件。"""

    def setUp(self):
        self.mod = _mysql_module()

    def test_01_content_mode_and_roundtrip(self):
        pwd = 'p@ss"w\\o\'rd\n$()`'
        path = self.mod._mysqlClientDefaultsFile(pwd)
        try:
            self.assertTrue(os.path.isfile(path), '没有落盘: %s' % path)
            with open(path, 'r', encoding='utf-8') as fh:
                content = fh.read()
            self.assertIn('[client]', content)
            self.assertIn('user=root', content)
            self.assertRegex(content, r'(?m)^password="')
            # 值必须按 option-file 规则转义得可反解
            m = re.search(r'(?m)^password="(.*)"$', content)
            self.assertIsNotNone(m, 'option 文件里没找到 password= 行: %r' % content)
            self.assertEqual(pwd, _optionUnescape(m.group(1)),
                             'option 文件里的口令反解不出来: %r' % m.group(1))
            # 单引号在 option 文件里必须原样（照 SQL 规则写 \' 会改口令）
            self.assertNotIn("\\'", m.group(1))
            if os.name == 'posix':
                mode = stat.S_IMODE(os.stat(path).st_mode)
                self.assertEqual(0o600, mode, '权限不是 0600: %s' % oct(mode))
        finally:
            os.remove(path)
        self.assertFalse(os.path.exists(path), '文件没删掉: %s' % path)

    def test_02_two_calls_use_different_paths(self):
        p1 = self.mod._mysqlClientDefaultsFile('a')
        p2 = self.mod._mysqlClientDefaultsFile('a')
        try:
            self.assertNotEqual(p1, p2, '两次调用复用了同一个临时文件路径')
        finally:
            for p in (p1, p2):
                os.remove(p)


# ---------------------------------------------------------------------------
# 静态断言（AST）
# ---------------------------------------------------------------------------
_SHELL_FUNCS = ('execShell', 'execShellRc', 'safeExecShell')
_GUARDED = ('adjust_password_policy', 'setRootPwdForce')


def _module_funcs(tree):
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _call_name(node):
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ''


def _shell_calls(fn):
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and n.args and _call_name(n) in _SHELL_FUNCS:
            out.append(n)
    return out


class TestStaticNoShellConcat(unittest.TestCase):

    def setUp(self):
        self.src = _read(IDX)
        self.tree = ast.parse(self.src)
        self.funcs = _module_funcs(self.tree)

    def test_01_helpers_exist_at_module_level(self):
        for name in ('_mysqlSqlLiteral', '_mysqlClientDefaultsFile'):
            self.assertIn(name, self.funcs, '缺少模块级纯函数 %s' % name)
        self.assertLess(self.funcs['_mysqlSqlLiteral'].lineno,
                        self.funcs['setRootPwdForce'].lineno,
                        '_mysqlSqlLiteral 必须定义在 setRootPwdForce 之前')
        self.assertLess(self.funcs['_mysqlClientDefaultsFile'].lineno,
                        self.funcs['setRootPwdForce'].lineno,
                        '_mysqlClientDefaultsFile 必须定义在 setRootPwdForce 之前')

    def test_02_no_inline_string_into_shell(self):
        """不许再出现「现拼/现格式化字符串」当 shell 首参（含 f-string + new_password）。"""
        for fname in _GUARDED:
            for call in _shell_calls(self.funcs[fname]):
                arg = call.args[0]
                self.assertIsInstance(
                    arg, (ast.Constant, ast.List),
                    '%s 里 %s 的首参是现拼字符串（%s:%d）——口令会进 shell'
                    % (fname, _call_name(call), os.path.basename(IDX), call.lineno))
                if isinstance(arg, ast.JoinedStr):
                    self.fail('%s 里仍有 f-string 进 shell（第 %d 行）' % (fname, call.lineno))

    def test_03_no_fstring_password_anywhere_in_module(self):
        """全模块：任何 shell 调用的 f-string/拼接里都不许引用口令变量。"""
        bad = []
        for n in ast.walk(self.tree):
            if not isinstance(n, ast.Call) or not n.args:
                continue
            if _call_name(n) not in _SHELL_FUNCS:
                continue
            arg = n.args[0]
            if not isinstance(arg, (ast.JoinedStr, ast.BinOp)):
                continue
            names = {x.id for x in ast.walk(arg) if isinstance(x, ast.Name)}
            if names & {'new_password', 'pwd', 'password'}:
                bad.append('%d:%s' % (n.lineno, ','.join(sorted(names))))
        self.assertEqual([], bad, '有 shell 调用把口令变量拼进命令串：%s' % bad)

    def test_04_no_dash_p_password(self):
        """不许再把口令拼成 `-p'...'`（argv/shell 都算）。"""
        for fname in _GUARDED:
            seg = ast.get_source_segment(self.src, self.funcs[fname]) or ''
            self.assertNotIn("-p'", seg, '%s 里仍有 -p\'口令\' 写法' % fname)
            self.assertNotIn('-p"', seg, '%s 里仍有 -p"口令" 写法' % fname)
            self.assertIsNone(re.search(r'-p\s*[\'"]', seg),
                              '%s 里仍有 -p<引号> 写法' % fname)
            self.assertEqual(
                [], [n for n in ast.walk(self.funcs[fname])
                     if isinstance(n, ast.Constant) and n.value == '-p'],
                '%s 里仍有 -p 元素' % fname)

    def test_05_mysql_calls_are_execshellrc_list(self):
        """两个函数里的 mysql 调用一律 `execShellRc([字面量列表], shell=False)`。"""
        for fname in _GUARDED:
            for call in _shell_calls(self.funcs[fname]):
                name = _call_name(call)
                if name == 'execShell':
                    # 唯一允许保留的是 ps|kill pipeline：纯字面量、无外部输入
                    arg = call.args[0]
                    self.assertIsInstance(arg, ast.Constant,
                                          '%s 里的 execShell 只允许字面量 pipeline' % fname)
                    self.assertIn('ps -ef', arg.value)
                    continue
                self.assertEqual('execShellRc', name,
                                 '%s 里出现意外的 shell 封装 %s' % (fname, name))
                self.assertIsInstance(call.args[0], ast.List,
                                      '%s:%d 的 mysql 调用首参必须是列表字面量（棘轮 bare_variable 规则）'
                                      % (fname, call.lineno))
                kw = {k.arg: k.value for k in call.keywords}
                self.assertIn('shell', kw, '%s:%d 缺 shell=False' % (fname, call.lineno))
                self.assertIsInstance(kw['shell'], ast.Constant)
                self.assertFalse(kw['shell'].value,
                                 '%s:%d 仍是 shell=True' % (fname, call.lineno))
                self.assertIn('timeout', kw, '%s:%d 缺 timeout' % (fname, call.lineno))

    def test_06_password_only_via_db_root(self):
        """口令 SQL 只由 `db_root.build_set_root_sql()` 生成，模块内不再手拼口令。"""
        fn = self.funcs['setRootPwdForce']
        used = [n for n in ast.walk(fn)
                if isinstance(n, ast.Call) and _call_name(n) == 'run_sql']
        self.assertGreaterEqual(len(used), 1,
                               'setRootPwdForce 应通过 db_root.run_sql 执行口令 SQL')
        builders = [n for n in ast.walk(fn)
                    if isinstance(n, ast.Call) and _call_name(n) == 'build_set_root_sql']
        self.assertEqual(1, len(builders), '口令 SQL 必须由 db_root.build_set_root_sql 生成')
        # 口令变量不得直接进字符串拼接/格式化（转义只允许在 db_root 里做一次）
        for n in ast.walk(fn):
            if not isinstance(n, (ast.BinOp, ast.JoinedStr)):
                continue
            names = {x.id for x in ast.walk(n) if isinstance(x, ast.Name)}
            if 'new_password' in names:
                self.fail('setRootPwdForce:%d 把口令直接拼进字符串' % n.lineno)
        # 全模块：不许再出现「IDENTIFIED BY '…' + 口令变量」的手写拼法
        for n in ast.walk(self.tree):
            if not isinstance(n, ast.BinOp) or not isinstance(n.op, ast.Add):
                continue
            seg = ast.get_source_segment(self.src, n) or ''
            names = {x.id for x in ast.walk(n) if isinstance(x, ast.Name)}
            if names & {'new_password', 'password', 'pwd'} and 'IDENTIFIED' in seg.upper():
                self.fail('第 %d 行仍在手拼 IDENTIFIED BY 口令' % n.lineno)

    def test_07_defaults_file_used_for_verify(self):
        """验证步必须用 --defaults-extra-file，且必须 try/finally 删除。"""
        fn = self.funcs['setRootPwdForce']
        seg = ast.get_source_segment(self.src, fn) or ''
        self.assertIn('--defaults-extra-file=', seg)
        self.assertIn('_mysqlClientDefaultsFile', seg)
        self.assertRegex(seg, r'try:\s*\n(?:.*\n)*?.*finally:', '缺 try/finally 清理')
        self.assertIn('os.remove(', seg)


# ---------------------------------------------------------------------------
# 行为用例（替身驱动，不碰真进程/真库）
# ---------------------------------------------------------------------------
class _StubYf(object):
    def __init__(self, rc_seq=None, err=''):
        self.calls = []
        self.shell_calls = []
        self.logs = []
        self._rc_seq = list(rc_seq or [])
        self._err = err

    def getServerDir(self):
        return _SERVER_TMP

    @staticmethod
    def _fakeStderr(argv):
        """模拟 mysql 的语法错误回显：会把查询片段带上（含转义后的口令）。

        真 mysql 对「字面量 SQL」不会打印口令，所以这里按**本次实际传入的 SQL**
        构造回显：常量 SQL 里没有口令，口令 SQL 里是转义形态——正好验证打码。
        """
        sql = ''
        if isinstance(argv, (list, tuple)) and argv:
            sql = str(argv[-1]) if len(argv) > 2 else ''
        return ("ERROR 1064 (42000): You have an error in your SQL syntax; "
                "check the manual near '%s' at line 1" % sql[-120:])

    def execShellRc(self, cmdstring, cwd=None, timeout=None, shell=True):
        record = {'argv': cmdstring, 'shell': shell, 'timeout': timeout}
        # 验证步：在调用当下就检查临时 defaults 文件的状态
        if isinstance(cmdstring, (list, tuple)):
            for a in cmdstring:
                if isinstance(a, str) and a.startswith('--defaults-extra-file='):
                    path = a.split('=', 1)[1]
                    record['cnf'] = path
                    record['cnf_exists'] = os.path.exists(path)
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as fh:
                            record['cnf_content'] = fh.read()
                        if os.name == 'posix':
                            record['cnf_mode'] = stat.S_IMODE(os.stat(path).st_mode)
        self.calls.append(record)
        rc = self._rc_seq.pop(0) if self._rc_seq else 0
        err = '' if rc == 0 else (self._err or self._fakeStderr(cmdstring))
        record['rc'] = rc
        record['raw_err'] = err
        return (rc, '', err)

    def execShell(self, cmdstring, cwd=None, timeout=None, shell=True):
        self.shell_calls.append(cmdstring)
        return ('', '')

    def writeFileLog(self, msg, path=None, **kwargs):
        self.logs.append(str(msg))


class _StubPopen(object):
    PIPE = -1

    def __init__(self, *a, **kw):
        self.args = a
        self.kw = kw


class _StubSubprocess(object):
    """替代模块级 `subprocess`：`Popen` 与 `PIPE` 都要有，且不得真起进程。"""

    PIPE = -1

    def __init__(self):
        self.popens = []

    def Popen(self, *a, **kw):
        self.popens.append({'argv': a[0] if a else None, 'kw': kw})
        return _StubPopen(*a, **kw)


class _StubTime(object):
    def __init__(self):
        self.slept = []

    def sleep(self, sec):
        self.slept.append(sec)


class _StubDbRootRun(object):
    """替代 `db_root._default_run`：记录 argv/环境，可按需返回 rc。

    `setRootPwdForce` 已经把「写口令」搬到 `web/core/db_root.py`（mysql / mariadb
    共用），所以这里断言的是**真正传给 mysql 客户端的 argv**，而不是执行封装。
    """

    def __init__(self, rc=0, err=''):
        self.calls = []
        self.rc = rc
        self.err = err

    def __call__(self, argv, timeout=None):
        rec = {'argv': list(argv), 'timeout': timeout}
        self.calls.append(rec)
        if self.rc == 0:
            return 0, '', ''
        return self.rc, '', self.err or ('ERROR 1064 (42000): near %r at line 1' % str(argv[-1])[-120:])


class TestSetRootPwdForceBehavior(unittest.TestCase):

    PWD = "p' OR 1=1 -- "

    def _run(self, verify_rc_seq=None, db_root_rc=0, db_root_err=''):
        mod = _mysql_module()
        stub = _StubYf(rc_seq=verify_rc_seq, err=db_root_err)
        stub_time = _StubTime()
        adjust_calls = []
        db_root_run = _StubDbRootRun(rc=db_root_rc, err=db_root_err)

        def _fake_adjust(version):
            adjust_calls.append(version)

        self._orig = (mod.yf, mod.time, mod.subprocess, mod.start,
                      mod.adjust_password_policy, mod.db_root._default_run)
        mod.yf = stub
        mod.time = stub_time
        mod.subprocess = _StubSubprocess()
        mod.start = lambda version='': 'ok'
        mod.adjust_password_policy = _fake_adjust
        mod.db_root._default_run = db_root_run
        try:
            ok = mod.setRootPwdForce(self.PWD, '8.0')
        finally:
            (mod.yf, mod.time, mod.subprocess, mod.start,
             mod.adjust_password_policy, mod.db_root._default_run) = self._orig
        return ok, stub, adjust_calls, db_root_run

    def test_01_argv_are_lists_and_never_carry_password(self):
        ok, stub, adjust_calls, db_root_run = self._run(verify_rc_seq=[0])
        self.assertTrue(ok)
        self.assertEqual(['8.0'], adjust_calls, '8.x 必须仍然调整密码策略')
        self.assertEqual(1, len(db_root_run.calls),
                         '写口令应只经 db_root 一次往返（覆盖 localhost/127.0.0.1/::1）')
        for rec in db_root_run.calls:
            self.assertIsInstance(rec['argv'], list, 'argv 不是 list: %r' % (rec['argv'],))
            for a in rec['argv']:
                self.assertIsInstance(a, str)
                self.assertNotIn(self.PWD, a, '口令原文进了 argv: %r' % (rec['argv'],))
        # 验证步仍是 execShellRc 列表 + 临时 defaults 文件
        self.assertEqual(1, len(stub.calls), '验证步应只有 1 次 execShellRc')
        self.assertIsInstance(stub.calls[0]['argv'], list)
        self.assertFalse(stub.calls[0]['shell'], '仍是 shell=True')
        self.assertIsNotNone(stub.calls[0]['timeout'], '缺 timeout')
        self.assertNotIn(self.PWD, ''.join(str(a) for a in stub.calls[0]['argv']),
                         '口令原文进了 argv')
        # ps|kill pipeline 保留原样，且不含口令
        self.assertEqual(2, len(stub.shell_calls))
        for c in stub.shell_calls:
            self.assertNotIn(self.PWD, c)

    def test_02_sql_carries_escaped_password(self):
        escaped = _mysql_module()._mysqlSqlLiteral(self.PWD)
        self.assertNotEqual(self.PWD, escaped, '转义结果与原文相同，转义没生效')
        _ok, _stub, _adj, db_root_run = self._run(verify_rc_seq=[0])
        sqls = [a for rec in db_root_run.calls for a in rec['argv']
                if isinstance(a, str) and 'IDENTIFIED BY' in a]
        self.assertEqual(1, len(sqls), '没找到写口令的 SQL')
        sql = sqls[0]
        self.assertIn(escaped, sql, 'SQL 里不是转义后的形态: %r' % sql)
        self.assertNotIn(self.PWD, sql, 'SQL 里出现了未转义的口令')
        # 三个本地 host 都必须被覆盖（只改 localhost 就是「安装完就密码错误」的根因）
        for host in ('localhost', '127.0.0.1', '::1'):
            self.assertIn("'root'@'%s'" % host, sql, 'SQL 没有覆盖 root@%s' % host)

    def test_03_verify_uses_defaults_file_and_cleans_up(self):
        _ok, stub, _adj, _run = self._run(verify_rc_seq=[0])
        verify = [r for r in stub.calls if 'cnf' in r]
        self.assertEqual(1, len(verify), '验证步没有走 --defaults-extra-file')
        rec = verify[0]
        self.assertTrue(rec['cnf_exists'], '验证时临时 defaults 文件不存在')
        self.assertRegex(rec['cnf_content'], r'(?m)^password=".*"$')
        value = re.search(r'(?m)^password="(.*)"$', rec['cnf_content']).group(1)
        # 口令只能以 option-file 转义形态出现，且必须能原样反解回来
        self.assertEqual(self.PWD, _optionUnescape(value),
                         'defaults 文件里的口令反解不出原文: %r' % value)
        if os.name == 'posix':
            self.assertEqual(0o600, rec.get('cnf_mode'))
        self.assertFalse(os.path.exists(rec['cnf']),
                         '函数返回后临时 defaults 文件没删掉: %s' % rec['cnf'])

    def test_04_return_true_iff_verify_rc_zero(self):
        ok, _stub, _adj, _run = self._run(verify_rc_seq=[0])
        self.assertTrue(ok, '验证步 rc=0 却返回 False')
        ok, _stub, _adj, _run = self._run(verify_rc_seq=[1])
        self.assertFalse(ok, '验证步 rc=1 却返回 True')

    def test_05_failure_log_has_no_password(self):
        """失败日志不得带口令（mysql 的语法错误回显会带查询片段）。"""
        escaped = _mysql_module()._mysqlSqlLiteral(self.PWD)
        self.assertNotEqual(self.PWD, escaped)
        ok, stub, _adj, _run = self._run(verify_rc_seq=[1], db_root_rc=1)
        self.assertFalse(ok)
        self.assertTrue(stub.logs, '失败时没有任何日志')
        for msg in stub.logs:
            self.assertNotIn(self.PWD, msg, '日志里出现了口令原文: %r' % msg)
            self.assertNotIn(escaped, msg, '日志里出现了口令的 SQL 转义形态: %r' % msg)
            self.assertNotIn('OR 1=1', msg, '日志里出现了口令片段: %r' % msg)
        # 打码要真发生（要么替换成 ***，要么整段丢弃只剩 ERROR 码），
        # 且日志仍能看出是哪一步失败（不是空日志蒙混）
        self.assertTrue(any(('***' in m) or ('ERROR 1064' in m) for m in stub.logs),
                        '失败细节既没打码也没保留错误码: %r' % stub.logs)
        self.assertTrue(any('rc=1' in m for m in stub.logs))

    def test_06_5_6_branch_also_uses_argv(self):
        mod = _mysql_module()
        stub = _StubYf(rc_seq=[0])
        db_root_run = _StubDbRootRun(rc=0)
        orig = (mod.yf, mod.time, mod.subprocess, mod.start, mod.db_root._default_run)
        mod.yf = stub
        mod.time = _StubTime()
        mod.subprocess = _StubSubprocess()
        mod.start = lambda version='': 'ok'
        mod.db_root._default_run = db_root_run
        try:
            ok = mod.setRootPwdForce(self.PWD, '5.6')
        finally:
            (mod.yf, mod.time, mod.subprocess, mod.start,
             mod.db_root._default_run) = orig
        self.assertTrue(ok)
        self.assertEqual(1, len(db_root_run.calls), '5.6 路径也应只经 db_root 一次')
        for rec in db_root_run.calls:
            self.assertIsInstance(rec['argv'], list)
            for a in rec['argv']:
                self.assertNotIn(self.PWD, a)
        sql = db_root_run.calls[0]['argv'][-1]
        self.assertIn(mod._mysqlSqlLiteral(self.PWD), sql)
        # 5.5/5.6 走旧语法 GRANT ... IDENTIFIED BY，同样必须覆盖三个 host
        self.assertIn('GRANT ALL PRIVILEGES', sql)
        for host in ('localhost', '127.0.0.1', '::1'):
            self.assertIn("'root'@'%s'" % host, sql)


if __name__ == '__main__':
    unittest.main()
