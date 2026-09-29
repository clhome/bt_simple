# coding: utf-8
"""C1 异常语义回归：`core.orm.ORM`（A 层）与 `core.db.Sql`（B 层）

契约要求「连接失败 / SQL 错 / 正常」三条路径都要有断言覆盖，本文件按此组织。

采用 **方案 B（兼容层）**，因此断言点是「兼容 + 可诊断 + 新接口可抛」：

A 层（`core.orm.ORM`，外部 MySQL/MariaDB/PostgreSQL）
  * 失败**不改变旧返回形状**：连接失败 → 错误文本；SQL 错 → `ORMError`（truthy）；
  * 但两者都必须 **打 ERROR 日志**（旧实现是完全静默的，这才是真正的故障源）；
  * `ORMError` 必须 **继承 Exception** —— 已有 5 处 `isinstance(res, Exception)` 依赖它；
  * `executeStrict/queryStrict/findStrict` 失败一律 **抛** `ORMError`；
  * 回归：`find()` 旧实现会在异常对象上做 `len()` 直接抛 `TypeError`，现在返回错误对象。

B 层（`core.db.Sql`，面板 SQLite）
  * 旧 API 继续返回 `"error: ..."` 字符串（调用面太大，保持兼容）；
  * `executeStrict/queryStrict/findStrict` 失败抛 `SqlError`。

本机没有 pymysql（面板只在服务器安装），因此注入假模块后**真跑** orm.py 的逻辑，
而不是把用例 skip 掉当通过。
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)


def _install_fake_pymysql():
    if 'pymysql' in sys.modules:
        return
    pkg = types.ModuleType('pymysql')
    cursors = types.ModuleType('pymysql.cursors')
    cursors.DictCursor = object
    pkg.cursors = cursors
    pkg.connect = lambda **kw: None
    sys.modules['pymysql'] = pkg
    sys.modules['pymysql.cursors'] = cursors


_install_fake_pymysql()


class _FakeCursor:
    def __init__(self, rows=None, raises=None):
        self._rows = rows if rows is not None else []
        self._raises = raises

    def execute(self, sql, params=None):
        if self._raises:
            raise self._raises
        return 1

    def fetchall(self):
        return self._rows

    def close(self):
        return None


class _FakeConn:
    def __init__(self, raises=None):
        self._raises = raises

    def commit(self):
        if self._raises:
            raise self._raises

    def close(self):
        return None


class _FakeSqlConn:
    def commit(self):
        return None

    def close(self):
        return None

    def execute(self, sql, params=()):
        return None

    def executescript(self, script):
        return None


class OrmErrorSemanticsTest(unittest.TestCase):
    """A 层：`core.orm.ORM` 三路径 + 兼容红线。"""

    def _orm(self):
        import core.orm as orm_mod
        return orm_mod, orm_mod.ORM()

    # ---------- 兼容红线 ----------
    def test_01_ormerror_is_exception(self):
        orm_mod, _ = self._orm()
        self.assertTrue(issubclass(orm_mod.ORMError, Exception),
                        'ORMError 必须继承 Exception，否则会破坏既有 isinstance 判断')
        self.assertFalse(issubclass(orm_mod.ORMError, (BaseException,)) and not issubclass(orm_mod.ORMError, Exception))

    def test_02_no_bare_return_ex_without_log(self):
        """静态守卫：`return ex` 不得再以「无日志」形式出现。"""
        with open(os.path.join(WEB, 'core', 'orm.py'), encoding='utf-8') as fh:
            src = fh.read().replace('\r\n', '\n')
        self.assertNotIn('            return ex\n        finally:', src,
                         'execute/query 又出现无日志的裸 `return ex`')
        self.assertIn('class ORMError', src)
        for name in ('def executeStrict', 'def queryStrict', 'def findStrict'):
            self.assertIn(name, src, '缺少 Strict 接口 %s' % name)

    # ---------- 路径 1：连接失败 ----------
    def test_03_connect_failure_legacy_returns_err_and_logs(self):
        orm_mod, obj = self._orm()
        obj._ORM__Conn = lambda: False
        obj._ORM__DB_ERR = 'connect refused'
        with self.assertLogs('yf.orm', level='ERROR') as cm:
            r = obj.execute('select 1')
        self.assertEqual(r, 'connect refused')
        self.assertTrue(any('连接失败' in m for m in cm.output),
                        '连接失败必须打 ERROR 日志：%r' % cm.output)

    def test_04_connect_failure_strict_raises(self):
        orm_mod, obj = self._orm()
        obj._ORM__Conn = lambda: False
        obj._ORM__DB_ERR = 'connect refused'
        with self.assertRaises(orm_mod.ORMError) as ctx:
            obj.queryStrict('select 1')
        self.assertIn('sql=select 1', str(ctx.exception))

    # ---------- 路径 2：SQL 执行错 ----------
    def test_05_sql_error_legacy_returns_ormerror_and_logs(self):
        orm_mod, obj = self._orm()
        obj._ORM__Conn = lambda: True
        obj._ORM__DB_CONN = _FakeConn()
        obj._ORM__DB_CUR = _FakeCursor(raises=RuntimeError('bad sql'))
        with self.assertLogs('yf.orm', level='ERROR') as cm:
            r = obj.execute('broken')
        self.assertIsInstance(r, orm_mod.ORMError)
        self.assertIsInstance(r, Exception)          # 兼容旧 isinstance 判断
        self.assertIn('bad sql', str(r))
        self.assertEqual(r.sql, 'broken')
        self.assertTrue(any('执行失败' in m for m in cm.output))

    def test_06_sql_error_strict_raises(self):
        orm_mod, obj = self._orm()
        obj._ORM__Conn = lambda: True
        obj._ORM__DB_CONN = _FakeConn()
        obj._ORM__DB_CUR = _FakeCursor(raises=RuntimeError('bad sql'))
        with self.assertRaises(orm_mod.ORMError) as ctx:
            obj.executeStrict('broken')
        self.assertIsInstance(ctx.exception.orig, RuntimeError)

    # ---------- 路径 3：正常 ----------
    def test_07_normal_path_returns_rows(self):
        orm_mod, obj = self._orm()
        obj._ORM__Conn = lambda: True
        obj._ORM__DB_CONN = _FakeConn()
        obj._ORM__DB_CUR = _FakeCursor(rows=[{'a': 1}])
        self.assertEqual(obj.queryStrict('select a from t'), [{'a': 1}])
        obj._ORM__DB_CUR = _FakeCursor(rows=[{'a': 1}])
        self.assertEqual(obj.findStrict('select a from t'), {'a': 1})

    def test_08_find_no_longer_crashes_on_error(self):
        """回归：旧 find() 在错误对象上做 len() → TypeError。"""
        orm_mod, obj = self._orm()
        obj.query = lambda sql, params=None: orm_mod.ORMError('boom', sql=sql)
        r = obj.find('select 1')
        self.assertIsInstance(r, orm_mod.ORMError)


class SqlStrictLayerTest(unittest.TestCase):
    """B 层：`core.db.Sql` 兼容语义 + Strict 抛错。"""

    def _sql(self):
        import core.db as db_mod
        return db_mod, db_mod.Sql()

    def _fake_fail(self, db_mod, obj):
        obj._Sql__getConn = lambda: None
        obj._Sql__DB_CONN = _FakeSqlConn()
        return db_mod

    def test_10_dberror_classes_and_strict_exist(self):
        db_mod, _ = self._sql()
        self.assertTrue(issubclass(db_mod.SqlError, Exception))
        with open(os.path.join(WEB, 'core', 'db.py'), encoding='utf-8') as fh:
            src = fh.read().replace('\r\n', '\n')
        for name in ('class SqlError', 'def executeStrict', 'def queryStrict', 'def findStrict'):
            self.assertIn(name, src, 'db.py 缺少 %s' % name)
        # 旧语义必须保持：仍然返回 "error: " 字符串
        self.assertIn('return "error: " + str(ex)', src)

    def test_11_legacy_returns_error_string_strict_raises(self):
        db_mod, obj = self._sql()
        self._fake_fail(db_mod, obj)
        orig = db_mod._execute_with_retry

        def boom(*a, **k):
            raise RuntimeError('disk I/O error')

        db_mod._execute_with_retry = boom
        try:
            legacy = obj.execute('update t set a=1')
            self.assertIsInstance(legacy, str)
            self.assertTrue(legacy.startswith('error: '))
            with self.assertRaises(db_mod.SqlError) as ctx:
                obj.executeStrict('update t set a=1')
            self.assertIn('disk I/O error', str(ctx.exception))
            with self.assertRaises(db_mod.SqlError):
                obj.queryStrict('select 1')
        finally:
            db_mod._execute_with_retry = orig

    def test_12_strict_normal_path_passes_through(self):
        db_mod, obj = self._sql()
        self._fake_fail(db_mod, obj)
        orig = db_mod._execute_with_retry

        class _Res:
            rowcount = 7

            def fetchall(self):
                return [{'a': 1}]

        db_mod._execute_with_retry = lambda *a, **k: _Res()
        try:
            self.assertEqual(obj.executeStrict('update t set a=1'), 7)
            # query 旧语义就是「返回游标对象」，Strict 只做错误检查，必须是直通
            self.assertIsInstance(obj.queryStrict('select 1'), _Res)
        finally:
            db_mod._execute_with_retry = orig


if __name__ == '__main__':
    unittest.main(verbosity=2)
