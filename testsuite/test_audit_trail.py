# coding: utf-8
"""
审计流水回归（G4）

商业版合规的三个硬门槛，本用例逐条锁死：

1. **有身份**：操作日志必须记下「谁、从哪」。
   历史实现把 uid 硬编码为 0（取 session 的代码被注释掉了），
   且 `addLog()` 根本没写 uid 字段 —— 界面上那一列永远是默认值 1。
2. **不可抹除**：`del_panel_logs` 原为「一键物理清空」，管理员或拿到会话的
   攻击者可以借此消灭证据。现改为先归档再清空，且归档动作本身进审计。
3. **篡改可发现**：`panel_audit` 带哈希链，改一行或删一行都会让后续校验断开。

另外验证与「SQLite 自愈」的衔接：**老库升级后 `panel_audit` 表与 `logs.ip`
列必须自动出现**，不需要用户做任何操作。
"""
import os
import sqlite3
import sys
import types
import unittest
from unittest import mock

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(project_root, 'web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import core.yf as yf                                    # noqa: E402
from testsuite._isolation import isolate                # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('audit_trail')

import core.audit as audit                              # noqa: E402
from core.migrations import runner, ensure_schema       # noqa: E402
import thisdb                                           # noqa: E402


def _db_path():
    return os.path.join(_PANEL_TMP, 'data', 'panel.db')


# 刻意复用面板自己的连接（yf.M()），而不是另开 sqlite3 连接：
#   1. 另开连接会与 core/db.py 的线程本地连接互锁（WAL 下也会 busy_timeout 卡 30s）；
#   2. 复用同一连接，测的就是面板真实走的链路。
def _q(sql, params=()):
    cur = yf.M().query(sql, params)
    if isinstance(cur, str):
        raise AssertionError('SQL 查询失败：%s' % cur)
    return [tuple(r) for r in cur.fetchall()]


def _x(sql, params=()):
    r = yf.M().execute(sql, params)
    if isinstance(r, str):
        raise AssertionError('SQL 执行失败：%s' % r)
    return r


def _tables():
    return set(r[0] for r in _q(
        "SELECT name FROM sqlite_master WHERE type='table'"))


def _columns(table):
    return set(r[1] for r in _q('PRAGMA table_info(%s)' % table))


def _raw(sql, params=()):
    """兼容入口：SELECT/PRAGMA 走查询，其余走执行。"""
    if sql.strip().lower().startswith(('select', 'pragma')):
        return _q(sql, params)
    return _x(sql, params)


class _FakeHeaders(dict):
    def get(self, k, d=''):
        return dict.get(self, k, d)


class _FakeRequest(object):
    remote_addr = '203.0.113.9'
    method = 'POST'
    path = '/plugins/run'
    headers = _FakeHeaders({'User-Agent': 'pytest-agent/1.0'})


def _fake_flask(session_data, request_id='rid-test'):
    mod = types.ModuleType('flask')
    mod.request = _FakeRequest()
    mod.session = dict(session_data)
    mod.g = types.SimpleNamespace(request_id=request_id)
    return mod


class AuditSchemaSelfHealTest(unittest.TestCase):
    """升级后审计表/列必须自动出现（与 H1 自愈框架的衔接）。"""

    def setUp(self):
        runner.reset_cache()

    def test_01_old_db_gets_audit_table_and_logs_ip(self):
        # 模拟「老库」：把新加的东西都去掉
        _x('DROP TABLE IF EXISTS panel_audit')
        _x('ALTER TABLE logs RENAME TO logs_old')
        _x('CREATE TABLE logs (id INTEGER PRIMARY KEY AUTOINCREMENT,'
           ' type TEXT, log TEXT, uid INTEGER DEFAULT 1, add_time TEXT)')
        _x('DROP TABLE logs_old')
        self.assertNotIn('panel_audit', _tables())
        self.assertNotIn('ip', _columns('logs'))

        report = ensure_schema(_db_path(), force=True)

        self.assertIn('panel_audit', _tables(),
                      '老库升级后未自动创建审计表')
        self.assertIn('panel_audit', report['created_tables'])
        self.assertIn('ip', _columns('logs'),
                      '老库升级后 logs 表未补上 ip 列')
        self.assertIn('logs.ip', report['added_columns'])
        self.assertEqual(report['errors'], [])

    def test_02_audit_table_survives_clear_log(self):
        """清空操作日志不得波及审计流水。"""
        thisdb.addLog('测试', 'x', 1, ip='1.1.1.1')
        audit.write_audit('test.action', target='t')
        before = _q('SELECT COUNT(*) FROM panel_audit')[0][0]
        self.assertGreaterEqual(before, 1)

        thisdb.clearLog()

        after = _q('SELECT COUNT(*) FROM panel_audit')[0][0]
        self.assertEqual(after, before, 'clearLog 竟然动了审计流水')


class AuditIdentityTest(unittest.TestCase):

    def setUp(self):
        runner.reset_cache()
        ensure_schema(_db_path(), force=True)
        _raw('DELETE FROM logs')
        _raw('DELETE FROM panel_audit')

    def test_03_write_log_records_uid_and_ip(self):
        """操作日志必须记下操作者与来源 IP（此前 uid 恒为 0、ip 根本没写）。"""
        fake = _fake_flask({'login': True, 'uid': 7, 'username': 'alice'})
        with mock.patch.dict(sys.modules, {'flask': fake}):
            yf.writeLog('测试类型', '执行了某个操作')

        rows = _raw('SELECT uid, ip, log FROM logs ORDER BY id DESC LIMIT 1')
        self.assertEqual(len(rows), 1)
        uid, ip, _log = rows[0]
        self.assertEqual(int(uid), 7, '未记录真实操作者 uid')
        self.assertTrue(ip, '未记录来源 IP')

    def test_04_write_log_dual_writes_audit(self):
        fake = _fake_flask({'login': True, 'uid': 7, 'username': 'alice'})
        with mock.patch.dict(sys.modules, {'flask': fake}):
            yf.writeLog('插件管理', '启动 mysql')

        rows = _raw('SELECT uid, username, ip, action, detail FROM panel_audit '
                    'ORDER BY id DESC LIMIT 1')
        self.assertEqual(len(rows), 1, 'writeLog 未同步落审计流水')
        uid, username, ip, action, detail = rows[0]
        self.assertEqual(int(uid), 7)
        self.assertEqual(username, 'alice')
        self.assertTrue(ip)
        self.assertEqual(action, '插件管理')
        self.assertIn('mysql', detail)

    def test_05_no_request_context_degrades_gracefully(self):
        """计划任务/CLI 场景没有请求上下文，不能崩，只是身份为空。"""
        self.assertTrue(audit.write_audit('cron.run', target='backup'))
        rows = _raw('SELECT uid, ip FROM panel_audit ORDER BY id DESC LIMIT 1')
        self.assertEqual(int(rows[0][0]), 0)
        self.assertEqual(rows[0][1] or '', '')


class AuditChainTest(unittest.TestCase):

    def setUp(self):
        runner.reset_cache()
        ensure_schema(_db_path(), force=True)
        _raw('DELETE FROM panel_audit')

    def test_06_chain_valid_after_writes(self):
        for i in range(5):
            audit.write_audit('act.%d' % i, target='t%d' % i)
        ok, problems, checked = audit.verify_chain()
        self.assertEqual(checked, 5)
        self.assertTrue(ok, '哈希链校验失败：%r' % problems)

    def test_07_tamper_is_detected(self):
        for i in range(4):
            audit.write_audit('act.%d' % i, target='t%d' % i)
        mid = _raw('SELECT id FROM panel_audit ORDER BY id ASC LIMIT 1 OFFSET 1')[0][0]
        _raw("UPDATE panel_audit SET detail='被改过了' WHERE id=?", (mid,))

        ok, problems, _ = audit.verify_chain()
        self.assertFalse(ok, '内容被改动却没被发现')
        self.assertTrue(any('row_hash' in p for p in problems), problems)

    def test_08_deletion_is_detected(self):
        for i in range(4):
            audit.write_audit('act.%d' % i, target='t%d' % i)
        mid = _raw('SELECT id FROM panel_audit ORDER BY id ASC LIMIT 1 OFFSET 1')[0][0]
        _raw('DELETE FROM panel_audit WHERE id=?', (mid,))

        ok, problems, _ = audit.verify_chain()
        self.assertFalse(ok, '删掉中间一行却没被发现')
        self.assertTrue(any('prev_hash' in p for p in problems), problems)

    def test_09_write_audit_never_raises_on_broken_db(self):
        with mock.patch.object(yf, 'M', side_effect=RuntimeError('db down')):
            self.assertFalse(audit.write_audit('x.y', target='z'))


class LogArchiveTest(unittest.TestCase):

    def setUp(self):
        runner.reset_cache()
        ensure_schema(_db_path(), force=True)
        _raw('DELETE FROM logs')
        _raw('DELETE FROM panel_audit')

    def test_10_archive_exports_then_clears(self):
        for i in range(3):
            thisdb.addLog('测试', '日志 %d' % i, 1, ip='10.0.0.%d' % i)

        path, count = thisdb.archiveLogs()

        self.assertEqual(count, 3)
        self.assertTrue(os.path.isfile(path), '归档文件未生成')
        with open(path, 'r', encoding='utf-8') as fh:
            import json
            data = json.load(fh)
        self.assertEqual(data['count'], 3)
        self.assertEqual(len(data['rows']), 3)
        self.assertEqual(_raw('SELECT COUNT(*) FROM logs')[0][0], 0,
                         '归档后应清空界面日志')

    def test_11_archive_action_is_audited(self):
        """归档（原「一键清空」）这个动作本身必须留痕。"""
        thisdb.addLog('测试', 'x', 1, ip='1.1.1.1')
        fake = _fake_flask({'login': True, 'uid': 1, 'username': 'admin'})
        with mock.patch.dict(sys.modules, {'flask': fake}):
            thisdb.archiveLogs()
            yf.writeLog('面板设置', '面板操作日志已归档(1 条)并清空!')

        rows = _raw("SELECT action, detail FROM panel_audit WHERE detail LIKE '%归档%'")
        self.assertTrue(rows, '归档动作未进审计流水')

    def test_12_del_panel_logs_uses_archive_not_clear(self):
        with open(os.path.join(web_dir, 'admin', 'logs', '__init__.py'),
                  encoding='utf-8') as fh:
            text = fh.read()
        start = text.index('def del_panel_logs():')
        body = text[start:text.index('@blueprint.route', start + 10)]
        self.assertIn('archiveLogs', body, 'del_panel_logs 未改为归档')
        self.assertNotIn('clearLog()', body, 'del_panel_logs 仍在直接物理清空')

    def test_13_audit_query_and_verify_endpoints_exist(self):
        with open(os.path.join(web_dir, 'admin', 'logs', '__init__.py'),
                  encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn("'/get_audit_trail'", text)
        self.assertIn("'/verify_audit_chain'", text)
        self.assertIn('@panel_login_required', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
