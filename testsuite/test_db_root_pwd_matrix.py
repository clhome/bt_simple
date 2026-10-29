# coding: utf-8
"""MySQL / MariaDB root 口令矩阵守卫（「安装完就提示数据库密码错误」）。

## 现场症状

MySQL 5.7 装完，点「性能优化」/「当前状态」直接报：

    [orm] query 连接失败: (1045, "Access denied for user 'root'@'127.0.0.1' (using password: YES)")
    sql=show global status
    → 「数据库密码错误，在管理列表-点击【修复】!」，点了也修不好

## 根因（已在真 MariaDB 实例上复现，见 test/probe_root_hosts.sh 与 test/verify_db_root_pwd.sh）

面板（mysql 与 mariadb **两个插件**）在初始化 / 修复 / 改密码时只写
`root@localhost` 一条口令，而真实的账户矩阵是：

    root@localhost   ← 面板改了
    root@127.0.0.1   ← mariadb-install-db / 旧 mysql_install_db 建的，口令仍是空的
    root@::1         ← 同上

插件模板 my*.cnf 全都带 `skip_name_resolve=1`，此时 `127.0.0.1` **不会**反解成
`localhost`，必须匹配独立的 `root@127.0.0.1` 账户；而面板 ORM
（`web/core/orm.py`）在 socket 文件不存在时会静默退回 TCP。
三者相遇，就用「空口令账户」去认证 → 1045。

第二个硬伤：这些写入步骤**从不检查执行结果**，失败也直接 `_saveRootPwd(pwd)`，
于是面板记下了新口令、数据库里还是旧口令（或空口令），从此每次连接都是 1045，
点「修复」走的又是同一套「只改 localhost」逻辑，所以修不好。

## 修法

`web/core/db_root.py` 收敛成一处：

1. `build_set_root_sql()` 幂等覆盖 localhost / 127.0.0.1 / ::1
   （5.5/5.6 用 `GRANT ... IDENTIFIED BY`，5.7+/MariaDB 用
   `CREATE USER IF NOT EXISTS` + `ALTER USER` + `GRANT`）；
2. `apply_root_pwd()` 执行后**真的连一次库验证**，验证不过就不许保存口令；
3. mysql / mariadb 的初始化 / 修复 / 改密码入口全部改走它。

本测试锁死上面三点（真库验证脚本见 `test/verify_db_root_pwd.sh`）。
"""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
MYSQL_IDX = os.path.join(ROOT, 'plugins', 'mysql', 'index.py')
MARIADB_IDX = os.path.join(ROOT, 'plugins', 'mariadb', 'index.py')

if WEB not in sys.path:
    sys.path.insert(0, WEB)

from testsuite._isolation import isolate  # noqa: E402

isolate('db_root_pwd_matrix')

import core.db_root as db_root  # noqa: E402


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def _func_map(path):
    tree = ast.parse(_read(path))
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


_UNESCAPE = {'0': '\x00', 'n': '\n', 'r': '\r', 'Z': '\x1a',
             '\\': '\\', "'": "'", '"': '"'}


def _sql_unescape(text):
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '\\' and i + 1 < len(text) and text[i + 1] in _UNESCAPE:
            out.append(_UNESCAPE[text[i + 1]])
            i += 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


# ---------------------------------------------------------------------------
# 1. SQL 构造
# ---------------------------------------------------------------------------
class TestRootSqlMatrix(unittest.TestCase):

    def test_01_covers_all_local_hosts(self):
        """三个本地 host 都必须被设置口令（只改 localhost 就是 1045 的根因）。"""
        sql = db_root.build_set_root_sql('5.7', 'pwd123')
        for host in db_root.ROOT_HOSTS:
            self.assertIn("'root'@'%s'" % host, sql, '缺少 root@%s' % host)
        self.assertEqual(('localhost', '127.0.0.1', '::1'), db_root.ROOT_HOSTS,
                         '本地 host 矩阵被改动，先确认 orm 的连接方式')

    def test_02_modern_syntax_is_idempotent(self):
        """5.7+/8.x/MariaDB：必须 CREATE IF NOT EXISTS + ALTER，重复执行不报错。"""
        sql = db_root.build_set_root_sql('8.0', 'pwd')
        self.assertIn('CREATE USER IF NOT EXISTS', sql)
        self.assertIn('ALTER USER', sql)
        self.assertIn('GRANT ALL PRIVILEGES', sql)
        # 先 FLUSH：skip-grant-tables 下 CREATE/ALTER USER 会被拒（ERROR 1290）
        self.assertTrue(sql.strip().startswith('FLUSH PRIVILEGES;'),
                        'SQL 必须以 FLUSH PRIVILEGES 开头（skip-grant-tables 场景需要）')
        self.assertIn('FLUSH PRIVILEGES;', sql.split('\n')[-1])
        for host in db_root.ROOT_HOSTS:
            self.assertEqual(1, sql.count("ALTER USER 'root'@'%s'" % host))
            self.assertEqual(1, sql.count("CREATE USER IF NOT EXISTS 'root'@'%s'" % host))

    def test_03_legacy_syntax_for_5_5_5_6(self):
        """5.5/5.6 没有 ALTER USER：必须用 GRANT ... IDENTIFIED BY（同时建/改/授权）。"""
        for ver in ('5.5', '5.6', '5.6.51'):
            sql = db_root.build_set_root_sql(ver, 'pwd')
            self.assertNotIn('ALTER USER', sql, '5.5/5.6 不该出现 ALTER USER')
            self.assertNotIn('CREATE USER', sql)
            for host in db_root.ROOT_HOSTS:
                self.assertIn("'root'@'%s' IDENTIFIED BY 'pwd'" % host, sql)

    def test_04_password_is_escaped(self):
        pwd = "p'a\\b\"c;d`e$f"
        sql = db_root.build_set_root_sql('5.7', pwd)
        self.assertIn(db_root.sql_literal(pwd), sql)
        self.assertNotIn("BY '%s'" % pwd, sql, '口令原样出现在 SQL 里（没转义）')

    def test_05_sql_literal_is_reversible(self):
        """转义必须可逆（否则写进去的口令和面板记的不一样）。"""
        cases = ["p'q", 'a\\b', 'a"b', 'a\nb', 'a\rb', 'a\x1ab', 'a\x00b',
                 '$(id)', 'a`b', 'a;b', "a'b\\", '\\\'', '中文口令']
        for raw in cases:
            lit = db_root.sql_literal(raw)
            self.assertEqual(raw, _sql_unescape(lit), '转义不可逆: %r -> %r' % (raw, lit))
            # 不允许出现「未转义的单引号」把字面量提前闭合
            i = 0
            while i < len(lit):
                if lit[i] == '\\':
                    i += 2
                    continue
                self.assertNotEqual("'", lit[i],
                                    '字面量里出现未转义单引号: %r' % lit)
                i += 1

    def test_06_option_escape_differs_from_sql(self):
        """option 文件的单引号必须原样（照 SQL 规则写 \\' 会把口令改掉）。"""
        self.assertEqual("a'b", db_root.option_escape("a'b"))
        self.assertEqual('a\\"b', db_root.option_escape('a"b'))
        self.assertEqual('a\\\\b', db_root.option_escape('a\\b'))
        self.assertEqual('a\\tb', db_root.option_escape('a\tb'))
        self.assertEqual('a\\bb', db_root.option_escape('a\bb'))

    def test_07_legacy_version_detection(self):
        self.assertTrue(db_root.is_legacy_auth_version('5.5.62'))
        self.assertTrue(db_root.is_legacy_auth_version('5.6'))
        for ver in ('5.7.44', '8.0', '8.4', '9.7', '10.11', ''):
            self.assertFalse(db_root.is_legacy_auth_version(ver), ver)


# ---------------------------------------------------------------------------
# 2. 应用 + 验证的判定矩阵（注入 runner，不碰真库）
# ---------------------------------------------------------------------------
class _Runner(object):
    """按 SQL / 验证步骤分别返回 rc 的假 runner，并记录 argv。"""

    def __init__(self, fail_sql=False, fail_socket=False, fail_tcp=False):
        self.calls = []
        self.fail_sql = fail_sql
        self.fail_socket = fail_socket
        self.fail_tcp = fail_tcp

    def __call__(self, argv, timeout=None):
        rec = {'argv': list(argv), 'timeout': timeout}
        self.calls.append(rec)
        sql = argv[-1]
        if sql.strip() == 'SELECT 1;':
            # TCP 那次验证的临时 option 文件里有 host=127.0.0.1；socket 那次没有
            if self._tcp_style(argv):
                return (1, '', 'ERROR 1045 (28000): Access denied') if self.fail_tcp else (0, '', '')
            return (1, '', 'ERROR 1045 (28000): Access denied') if self.fail_socket else (0, '', '')
        if 'FLUSH PRIVILEGES' in sql:
            return (1, '', 'ERROR 1290 (HY000): skip-grant-tables') if self.fail_sql else (0, '', '')
        return 0, '', ''

    @staticmethod
    def _tcp_style(argv):
        """验证 TCP 的那一次 argv 会带 host=127.0.0.1（临时 option 文件里的行）。"""
        for a in argv:
            if a.startswith(('--defaults-file=', '--defaults-extra-file=')):
                path = a.split('=', 1)[1]
                try:
                    with open(path, encoding='utf-8') as fh:
                        return 'host=127.0.0.1' in fh.read()
                except OSError:
                    return False
        return False


class TestApplyRootPwd(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp(prefix='db_root_matrix_')
        self.sock = os.path.join(self.tmpdir, 'mysql.sock')
        with open(self.sock, 'w') as fh:
            fh.write('')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_01_all_green(self):
        run = _Runner()
        res = db_root.apply_root_pwd('/bin/mysql', '5.7', 'pwd',
                                     socket_file=self.sock, port=3306, run=run)
        self.assertTrue(res.ok, res)
        self.assertTrue(res.sql_ok)
        self.assertTrue(res.socket_ok)
        self.assertTrue(res.tcp_ok)
        # 至少一次写口令 + socket 验证 + TCP 验证
        self.assertGreaterEqual(len(run.calls), 3)

    def test_02_sql_failure_blocks_save(self):
        run = _Runner(fail_sql=True)
        res = db_root.apply_root_pwd('/bin/mysql', '5.7', 'pwd',
                                     socket_file=self.sock, port=3306, run=run)
        self.assertFalse(res.ok, '写入口令失败却判成功（会把错口令记进面板库）')
        self.assertFalse(res.sql_ok)
        self.assertIn('写入口令失败', res.detail)

    def test_03_socket_missing_falls_back_to_tcp(self):
        """socket 文件不存在（现场形态）时，靠 TCP 验证通过就算成功。"""
        run = _Runner()
        res = db_root.apply_root_pwd('/bin/mysql', '5.7', 'pwd',
                                     socket_file=os.path.join(self.tmpdir, 'nope.sock'),
                                     port=3306, run=run)
        self.assertIsNone(res.socket_ok, 'socket 不存在时不该判 socket 验证')
        self.assertTrue(res.tcp_ok)
        self.assertTrue(res.ok, res)

    def test_04_both_transports_fail(self):
        run = _Runner(fail_socket=True, fail_tcp=True)
        res = db_root.apply_root_pwd('/bin/mysql', '5.7', 'pwd',
                                     socket_file=self.sock, port=3306, run=run)
        self.assertFalse(res.ok, '两种连接都失败却判成功')
        self.assertIn('验证失败', res.detail)

    def test_05_tcp_failure_alone_does_not_block(self):
        """用户自己配了 skip-networking 时只走 socket：不能因为 TCP 不通就拒绝保存。"""
        run = _Runner(fail_tcp=True)
        res = db_root.apply_root_pwd('/bin/mysql', '5.7', 'pwd',
                                     socket_file=self.sock, port=3306, run=run)
        self.assertTrue(res.ok, res)
        self.assertTrue(res.socket_ok)
        self.assertFalse(res.tcp_ok)

    def test_06_password_never_in_argv(self):
        run = _Runner()
        pwd = "S3cret'pwd"
        db_root.apply_root_pwd('/bin/mysql', '5.7', pwd,
                               socket_file=self.sock, port=3306, run=run)
        for rec in run.calls:
            for a in rec['argv']:
                self.assertNotIn(pwd, a, '口令原文进了 argv: %r' % (rec['argv'],))

    def test_07_failure_detail_has_no_password(self):
        run = _Runner(fail_sql=True)
        pwd = "S3cret'pwd"
        res = db_root.apply_root_pwd('/bin/mysql', '5.7', pwd,
                                     socket_file=self.sock, port=3306, run=run)
        self.assertNotIn(pwd, res.detail, '失败详情里带了口令: %r' % res.detail)


# ---------------------------------------------------------------------------
# 3. 插件侧静态断言：四个入口都走 db_root，不再手写单 host SQL
# ---------------------------------------------------------------------------
class TestPluginsUseSharedRootPwd(unittest.TestCase):

    def _assert_plugin(self, path, helper_line, entry_funcs):
        src = _read(path)
        funcs = _func_map(path)
        self.assertIn('import core.db_root as db_root', src,
                      '%s 没引入共享实现' % os.path.basename(path))
        self.assertIn('def _applyRootPwd(', src, '%s 缺少统一写入口' % os.path.basename(path))
        for fn in entry_funcs:
            self.assertIn(fn, funcs, '缺少函数 %s' % fn)
            seg = ast.get_source_segment(src, funcs[fn]) or ''
            # 常规入口走 _applyRootPwd（内部已含 build_set_root_sql + 验证）；
            # setRootPwdForce 是 skip-grant 全流程，自己调 db_root.run_sql + build_set_root_sql。
            if '_applyRootPwd(' in seg:
                continue
            self.assertIn('db_root.run_sql(', seg,
                          '%s::%s 没有走共享实现（单 host 写入会再次引发 1045）' % (
                              os.path.basename(path), fn))
            self.assertIn('build_set_root_sql(', seg,
                          '%s::%s 的口令 SQL 必须由 db_root 生成' % (os.path.basename(path), fn))
        # 全文件：不许再出现「只写 localhost 的 ALTER USER」手拼。
        # 注：不用 ast.get_source_segment（它内部会重新分词整个文件，对大文件里的
        # 每个 BinOp 调用一次就是 O(n²)，实测把本用例拖到 50s）—— 按行号取文本即可。
        lines = src.splitlines()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.BinOp):
                continue
            start = (node.lineno or 1) - 1
            end = node.end_lineno or node.lineno or 1
            seg = '\n'.join(lines[start:end])
            if 'IDENTIFIED' in seg.upper() and 'LOCALHOST' in seg:
                self.fail('%s 第 %d 行仍在手拼只改 localhost 的口令 SQL'
                          % (os.path.basename(path), node.lineno))

    def test_01_mysql_entries(self):
        self._assert_plugin(
            MYSQL_IDX, '_applyRootPwd',
            ('initMysqlPwd', 'initMysql8Pwd', 'resetDbRootPwd', 'setRootPwd', 'setRootPwdForce'))

    def test_02_mariadb_entries(self):
        self._assert_plugin(
            MARIADB_IDX, '_applyRootPwd',
            ('initMariaDbPwd', 'resetDbRootPwd', 'setRootPwd'))

    def test_03_save_only_after_verify(self):
        """`_saveRootPwd` 只能在验证通过的分支里调用（否则面板记错口令）。"""
        for path in (MYSQL_IDX, MARIADB_IDX):
            src = _read(path)
            funcs = _func_map(path)
            fn = funcs['_applyRootPwd']
            saved_under_guard = False
            saved_elsewhere = []
            for stmt in fn.body:
                if isinstance(stmt, ast.If):
                    cond = ast.get_source_segment(src, stmt.test) or ''
                    for node in ast.walk(stmt):
                        if (isinstance(node, ast.Call) and
                                getattr(node.func, 'id', '') == '_saveRootPwd'):
                            if 'res.ok' in cond:
                                saved_under_guard = True
                            else:
                                saved_elsewhere.append(node.lineno)
            # 任何不在 `if res.ok` 分支里的 _saveRootPwd 都算错
            if not saved_under_guard:
                in_guard = set()
            else:
                in_guard = None
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == '_saveRootPwd':
                    if in_guard is not None:
                        saved_elsewhere.append(node.lineno)
            self.assertTrue(saved_under_guard,
                            '%s::_applyRootPwd 没有在 `if res.ok` 里保存口令' % os.path.basename(path))
            self.assertEqual([], sorted(set(saved_elsewhere)),
                             '%s::_applyRootPwd 在验证分支之外也在保存口令'
                             % os.path.basename(path))

    def test_04_fix_db_access_reports_failure(self):
        """【修复】不能无条件回「修复成功」。"""
        for path in (MYSQL_IDX, MARIADB_IDX):
            src = _read(path)
            funcs = _func_map(path)
            seg = ast.get_source_segment(src, funcs['fixDbAccess']) or ''
            self.assertIn('reset_ok', seg,
                          '%s::fixDbAccess 没检查 resetDbRootPwd 的返回值' % os.path.basename(path))
            self.assertIn('修复失败', seg,
                          '%s::fixDbAccess 失败时没有明确失败提示' % os.path.basename(path))


if __name__ == '__main__':
    unittest.main()
