# coding: utf-8
"""B10 data_query 模块加固守卫（SQL 注入 / 危险语句 / 命令注入 / 超时 / 分页 / XSS）。

真机实测（Debian12，生产库 test1/cc2/dianbiao 全程只读，行数+SHOW CREATE md5 前后零变化）：

1. `sql_postgresql` 驱动 `conn()` 把 `docker_instance` 原样拼进
   `docker inspect --format '...' <name>` shell 字符串；而 `docker_instance`
   来自**用户可写的连接备注/名称**（`get_options` 的 `conn_` 分支：
   `notes='__auto_docker_pg_x;touch /tmp/pwn'` → `x;touch /tmp/pwn`）。
   真机 `saveConnection` + `get_db_list(sid=conn_<id>)`（含 HTTP `/plugins/callback`
   用户路径）以 root 建出 marker → 命令注入 / RCE。修复：白名单收敛容器名 +
   `yf.execShellRc(argv, shell=False)`。
2. `PluginORM` 只设 `connect_timeout`，不设 `read_timeout` → 一条慢 SQL 把面板
   worker 挂到插件 op_timeout(600s)。真机 `SELECT SLEEP(8)` 实跑 8.00s 无中断；
   修复后 `SELECT SLEEP(30)` 在 10.01s 被切断（SLEEP(8) 仍正常返回，无假阳性）。
3. `getDataList` 的 `size` 客户端可控且不封顶：真机 `size=50000` 一次返回 50000 行；
   修复后封顶 1000 行。
4. `redundantIndexesCmd` 直接 `data[int(args['index'])]`：负索引静默丢掉**另一条**
   冗余索引（真机 index=-1 回「执行成功!」），越界/非数字抛未捕获
   IndexError/ValueError。修复：类型 + 边界校验。
5. 前端数据浏览把库/表/字段名与单元格值（来自任意被浏览库）原样拼 `.html()`；
   redis 键名还拼进行内 onclick → 存储型 XSS；多个带 `time:0` 遮罩的 `$.post`
   缺 `.fail()` → 500 时遮罩永久卡死。

断言口径：真跑行为为主（stub 掉 pymysql/驱动连接，真调 `getDataList`/
`redundantIndexesCmd`/`connect`），辅以 AST 与前端源码结构断言。
"""
import ast
import io
import json
import os
import re
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
APPJS = os.path.join(ROOT, 'plugins', 'data_query', 'static', 'js', 'app.js')
PG = os.path.join(ROOT, 'plugins', 'data_query', 'sql_postgresql.py')
MYSQL = os.path.join(ROOT, 'plugins', 'data_query', 'sql_mysql.py')

if WEB not in sys.path:
    sys.path.insert(0, WEB)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
PLUGIN_DIR = os.path.join(ROOT, 'plugins', 'data_query')
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

# 进程级隔离必须早于会打开面板库的模块导入（同 test_data_query_fix.py）
from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('data_query_b10')

import importlib.util  # noqa: E402


def _load_mysql(path=MYSQL):
    """从文件路径加载 sql_mysql（供变异自证重定向到被回退的副本）。"""
    spec = importlib.util.spec_from_file_location('dq_b10_mysql_under_test', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['dq_b10_mysql_under_test'] = mod
    spec.loader.exec_module(mod)
    return mod


sql_mysql = _load_mysql()


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _parse(res):
    if isinstance(res, str):
        try:
            return json.loads(res)
        except Exception:
            return res
    return res


def _live_nodes(node):
    """产出「可达」AST 节点，跳过 `if False:` / `while False:` 等静态死分支（防蒙混）。"""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        if isinstance(n, ast.If):
            if not (isinstance(n.test, ast.Constant) and not n.test.value):
                stack.append(n.test)
                stack.extend(n.body)
            stack.extend(n.orelse)
            continue
        if isinstance(n, ast.While) and isinstance(n.test, ast.Constant) and not n.test.value:
            continue
        stack.extend(ast.iter_child_nodes(n))


def _strip_js_comments(js):
    """去掉 JS 注释，防止把修复代码写进注释/死代码就蒙混过关。"""
    js = re.sub(r'/\*.*?\*/', '', js, flags=re.S)
    js = re.sub(r'(?<!:)//[^\n]*', '', js)
    return js


class _FakeCursor(object):
    def close(self):
        pass


class _FakeConn(object):
    def cursor(self):
        return _FakeCursor()

    def close(self):
        pass


class _RecDB(object):
    """记录被执行的 SQL 的假连接。"""

    def __init__(self, perf=True, redundant_rows=None):
        self.sqls = []
        self.executed = []
        self._perf = perf
        self._rows = redundant_rows if redundant_rows is not None else []

    def setDbName(self, db):
        self.db = db

    def find(self, sql):
        self.sqls.append(sql)
        return {'@@performance_schema': 1 if self._perf else 0}

    def query(self, sql):
        self.sqls.append(sql)
        if 'count(*)' in sql:
            return [{'num': 5000}]
        if 'schema_redundant_indexes' in sql:
            return self._rows
        return [{'id': '1', 'name': 'x'}]

    def execute(self, sql, params=None):
        self.executed.append(sql)
        return 1


class _FakeInst(object):
    def __init__(self, db):
        self._db = db

    def conn(self):
        return self._db


class TestDataQueryB10Hardening(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        assert _PANEL_TMP and _SERVER_TMP, '模块级隔离未生效'

    # ---------- 1. postgresql docker inspect 命令注入 ----------

    def test_01_pg_no_shell_concat_of_docker_instance(self):
        src = _read(PG)
        tree = ast.parse(src)
        # 旧实现：yf.execShell(f"docker inspect ... {c_name}")
        bad = []
        for node in _live_nodes(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == 'execShell':
                bad.append(node.lineno)
        self.assertEqual(bad, [], 'sql_postgresql 不得再用 yf.execShell(字符串) 执行 docker inspect: %s' % bad)

        # 必须用 argv 列表 + shell=False
        found = False
        for node in _live_nodes(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == 'execShellRc':
                arg0 = node.args[0] if node.args else None
                kw = {k.arg: k.value for k in node.keywords}
                shell = kw.get('shell')
                if isinstance(arg0, (ast.List, ast.Tuple)) and isinstance(shell, ast.Constant) and shell.value is False:
                    found = True
        self.assertTrue(found, 'docker inspect 必须走 execShellRc(argv 列表, shell=False)')

    def test_02_pg_docker_instance_whitelist(self):
        # 用 AST 而非源码正则：把白名单写进注释/`if False:` 不算数
        tree = ast.parse(_read(PG))
        guard_ok = False
        nulled = False
        for node in _live_nodes(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == 'match' and isinstance(node.func.value, ast.Name) \
                    and node.func.value.id == 're' and node.args:
                pat = node.args[0]
                if isinstance(pat, ast.Constant) and isinstance(pat.value, str) \
                        and '[A-Za-z0-9_]' in pat.value and 'docker_inst' in ast.dump(node):
                    guard_ok = True
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                    and node.value.value is None \
                    and any(isinstance(t, ast.Name) and t.id == 'docker_inst' for t in node.targets):
                nulled = True
        self.assertTrue(guard_ok, 'docker_instance 必须过容器名白名单 re.match(..., docker_inst)')
        self.assertTrue(nulled, '白名单不匹配时必须把 docker_instance 置空（丢弃网络穿透回退）')

    # ---------- 2. 语句超时 ----------

    def test_03_plugin_orm_sets_read_timeout(self):
        m = _load_mysql(MYSQL)
        captured = {}

        def fake_connect(**kw):
            captured.update(kw)
            return _FakeConn()

        fake_pymysql = types.SimpleNamespace(
            connect=fake_connect,
            cursors=types.SimpleNamespace(DictCursor=object),
        )
        orig = m.pymysql
        m.pymysql = fake_pymysql
        try:
            o = m.PluginORM()
            o.setHost('127.0.0.1')
            o.setPort(3306)
            o.setUser('u')
            o.setPwd('p')
            o.setTimeout(5)
            self.assertTrue(o.connect())
        finally:
            m.pymysql = orig
        self.assertIn('read_timeout', captured, '必须设置 read_timeout（否则慢 SQL 挂死面板线程）')
        self.assertIn('write_timeout', captured)
        self.assertEqual(captured['read_timeout'], o.query_timeout)
        self.assertTrue(0 < o.query_timeout <= 30, '语句超时必须是有界值: %r' % o.query_timeout)

    # ---------- 3. 分页上限 ----------

    def test_04_get_data_list_size_capped(self):
        m = _load_mysql(MYSQL)
        db = _RecDB()
        ctr = m.nosqlMySQLCtr()
        orig = ctr.getInstanceBySid
        ctr.getInstanceBySid = lambda sid: _FakeInst(db)
        try:
            res = _parse(m.get_data_list({'sid': 'mysql', 'db': 'd', 'table': 't1', 'p': 1, 'size': 100000000}))
        finally:
            ctr.getInstanceBySid = orig
        self.assertTrue(res.get('status'))
        select_sqls = [s for s in db.sqls if s.startswith('select * from')]
        self.assertTrue(select_sqls, '应生成数据查询 SQL: %s' % db.sqls)
        m_lim = re.search(r'limit\s+(\d+)\s*,\s*(\d+)', select_sqls[0])
        self.assertIsNotNone(m_lim, 'limit 缺失: %s' % select_sqls[0])
        self.assertLessEqual(int(m_lim.group(2)), 1000, 'size 必须封顶 <=1000: %s' % select_sqls[0])

    # ---------- 4. 冗余索引 DROP 的 index 校验 ----------

    def test_05_redundant_index_bounds(self):
        m = _load_mysql(MYSQL)
        rows = [
            {'sql_drop_index': 'ALTER TABLE `d`.`t1` DROP INDEX `a`'},
            {'sql_drop_index': 'ALTER TABLE `d`.`t1` DROP INDEX `b`'},
        ]
        ctr = m.nosqlMySQLCtr()

        for bad in (-1, -2, 999, 'abc', '0;DROP', None):
            db = _RecDB(redundant_rows=rows)
            orig = ctr.getInstanceBySid
            ctr.getInstanceBySid = lambda sid, _db=db: _FakeInst(_db)
            try:
                res = _parse(m.redundant_indexes_cmd({'sid': 'mysql', 'index': bad}))
            finally:
                ctr.getInstanceBySid = orig
            self.assertFalse(res.get('status'), 'index=%r 必须被拒: %s' % (bad, res))
            self.assertEqual(db.executed, [], 'index=%r 不得执行任何 DDL: %s' % (bad, db.executed))

        # 合法索引仍可执行（只 DROP 指定那一条）
        db = _RecDB(redundant_rows=rows)
        orig = ctr.getInstanceBySid
        ctr.getInstanceBySid = lambda sid: _FakeInst(db)
        try:
            res = _parse(m.redundant_indexes_cmd({'sid': 'mysql', 'index': 1}))
        finally:
            ctr.getInstanceBySid = orig
        self.assertTrue(res.get('status'))
        self.assertEqual(db.executed, ['ALTER TABLE `d`.`t1` DROP INDEX `b`'])

    # ---------- 5. 前端 XSS / 遮罩 ----------

    def test_06_frontend_helpers_defined(self):
        js = _strip_js_comments(_read(APPJS))
        self.assertIn('function dqEscapeHtml(', js)
        self.assertIn('function dqJsStr(', js)

    def test_07_frontend_data_cells_escaped(self):
        js = _strip_js_comments(_read(APPJS))
        # 数据单元格 / 表头字段名必须转义（旧实现：'<td title="'+dlist[i][f]+'">'）
        self.assertNotIn("'<td title=\"'+dlist[i][f]+'\">'+dlist[i][f]", js)
        self.assertNotIn("'<td>'+data[i].name+'</td>'", js)
        self.assertIn('dqEscapeHtml(dlist[i][f])', js)
        self.assertIn('dqEscapeHtml(fields[i])', js)
        # redis 键名进 onclick 必须走 JS 字符串转义
        self.assertNotIn("redisDeleteKey(\\''+data[i].name", js)
        self.assertIn('dqJsStr(data[i].name)', js)

    def test_08_frontend_mask_ajax_has_fail(self):
        js = _strip_js_comments(_read(APPJS))
        # 逐个带 time:0 遮罩的请求：其 $.post 语句必须以 .fail(...) 收尾，
        # 否则面板 500 时遮罩永久卡死（旧实现 20 个 ajax 只有 2 个 .fail）。
        bad = []
        for m in re.finditer(r'time:\s*0\s*,\s*shade', js):
            post = js.find('$.post(', m.end())
            if post == -1:
                bad.append(('mask without $.post', m.start()))
                continue
            end = js.find("'json')", post)
            if end == -1:
                bad.append(('post without json', post))
                continue
            end += len("'json')")
            tail = js[end:end + 40].lstrip()
            if not tail.startswith('.fail('):
                bad.append((post, tail[:40]))
        self.assertEqual(bad, [], '带 time:0 遮罩的请求必须都有 .fail(): %s' % bad)


if __name__ == '__main__':
    unittest.main()
