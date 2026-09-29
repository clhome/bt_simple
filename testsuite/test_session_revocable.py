# coding: utf-8
"""
会话可撤销 + 登录失败双维度限流（B1 / B2）

对应 `参考/20260928优化.md` 的两个 P1 遗留项：

B1 服务端会话（`panel_session` 表）
    * 登录态有服务端副本，因此可以「列举设备 / 强制下线 / 改密码踢人」；
    * 不再只有「签名 Cookie」这一条无法吊销的链路；
    * 表不可用时**降级为旧行为**（fail-open），绝不把所有人锁在门外。

B2 登录失败限流（`panel_login_failure` 表）
    * IP 与账号**双维度**计数，任一超限即封禁（旧实现只有 IP 维度）；
    * 计数落库，多 worker / 重启口径一致；
    * 验收口径：同一账号从 6 个不同 IP 各失败 1 次，第 6 次被拒。

另附静态守卫：确认关键调用点真的接上了（否则「写了模块但没人用」会假绿）。
"""
import os
import sys
import time
import unittest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(project_root, 'web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import core.yf as yf                                    # noqa: E402
from testsuite._isolation import isolate                # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('session_revocable')

import core.panel_session as panel_session              # noqa: E402
import core.login_guard as login_guard                  # noqa: E402
from core.migrations import runner, ensure_schema       # noqa: E402
from core.migrations import schema as mig_schema        # noqa: E402


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
    return set(r[0] for r in _q("SELECT name FROM sqlite_master WHERE type='table'"))


def _columns(table):
    return set(r[1] for r in _q('PRAGMA table_info(%s)' % table))


def _read(rel):
    with open(os.path.join(project_root, rel), 'r', encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


def _reset_panel_conn():
    """让迁移引擎能拿到写锁。

    面板自己的线程本地连接（core.db）是长驻的，在 WAL 下会挡住
    `ensure_schema()` 的 `BEGIN IMMEDIATE`（实测等满 30s busy_timeout 后失败）。
    先关掉共享连接并清空缓存表，迁移完成后再用时自然重连。

    这只是一个测试辅助 —— 生产路径里迁移发生在 thisdb 导入之前，不存在这个问题。
    """
    try:
        import core.db as cdb
        cdb._close_all_connections()
        conns = getattr(cdb._local, 'connections', None)
        if isinstance(conns, dict):
            conns.clear()
    except Exception:
        pass


def _heal_schema():
    _reset_panel_conn()
    runner.reset_cache()
    report = ensure_schema()
    _reset_panel_conn()
    return report


class SchemaSelfHealTest(unittest.TestCase):
    """升级后的老库必须自动出现两张新表（与 H1 自愈框架衔接）。"""

    def setUp(self):
        runner.reset_cache()
        panel_session.reset_cache()
        login_guard.reset_cache()

    def test_01_required_tables_declared(self):
        self.assertIn('panel_session', mig_schema.REQUIRED_TABLES)
        self.assertIn('panel_login_failure', mig_schema.REQUIRED_TABLES)
        names = [i[0] for i in mig_schema.REQUIRED_INDEXES]
        self.assertIn('panel_session_uid_idx', names)
        self.assertIn('panel_login_failure_kv_idx', names)

    def test_02_old_db_gets_both_tables(self):
        _x('DROP TABLE IF EXISTS panel_session')
        _x('DROP TABLE IF EXISTS panel_login_failure')
        self.assertNotIn('panel_session', _tables())

        report = _heal_schema()
        self.assertEqual(report.get('errors'), [], report.get('errors'))
        tables = _tables()
        self.assertIn('panel_session', tables)
        self.assertIn('panel_login_failure', tables)

        self.assertTrue({'session_id', 'uid', 'username', 'ip', 'ua',
                         'created_at', 'last_seen', 'expires_at', 'revoked'}
                        <= _columns('panel_session'))
        self.assertTrue({'kind', 'value', 'fail_count', 'first_at',
                         'last_at', 'banned_until'} <= _columns('panel_login_failure'))


class PanelSessionTest(unittest.TestCase):

    def setUp(self):
        panel_session.reset_cache()
        self.uid = 9001

    def _clean(self):
        _x('DELETE FROM panel_session WHERE uid=?', (self.uid,))

    def test_10_create_and_touch(self):
        self._clean()
        sid = panel_session.create(self.uid, 'alice', '1.2.3.4', 'UA/1.0')
        self.assertTrue(sid)
        valid, reason = panel_session.touch(sid)
        self.assertTrue(valid)
        self.assertEqual(reason, 'ok')

    def test_11_revoke_blocks_touch(self):
        self._clean()
        sid = panel_session.create(self.uid, 'alice', '1.2.3.4', 'UA/1.0')
        self.assertEqual(panel_session.revoke(sid), 1)
        valid, reason = panel_session.touch(sid)
        self.assertFalse(valid)
        self.assertEqual(reason, 'revoked')

    def test_12_revoke_user_sessions_keeps_current(self):
        self._clean()
        a = panel_session.create(self.uid, 'alice', '1.1.1.1', 'A')
        b = panel_session.create(self.uid, 'alice', '2.2.2.2', 'B')
        panel_session.revoke_user_sessions(self.uid, keep_session_id=a)
        self.assertTrue(panel_session.touch(a)[0], '当前会话必须保留')
        self.assertFalse(panel_session.touch(b)[0], '其它会话必须被撤销')

    def test_13_expired_session_rejected(self):
        self._clean()
        sid = panel_session.create(self.uid, 'alice', '1.1.1.1', 'A',
                                   expires_at=int(time.time()) - 1)
        valid, reason = panel_session.touch(sid)
        self.assertFalse(valid)
        self.assertEqual(reason, 'expired')

    def test_14_list_sessions_hides_revoked(self):
        self._clean()
        a = panel_session.create(self.uid, 'alice', '1.1.1.1', 'A')
        b = panel_session.create(self.uid, 'alice', '2.2.2.2', 'B')
        panel_session.revoke(b)
        rows = panel_session.list_sessions(self.uid)
        ids = [r['session_id'] for r in rows]
        self.assertIn(a, ids)
        self.assertNotIn(b, ids)
        row = [r for r in rows if r['session_id'] == a][0]
        self.assertEqual(row['ip'], '1.1.1.1')
        self.assertEqual(row['ua'], 'A')

    def test_15_fail_open_when_table_missing(self):
        """会话表不可用时必须放行（fail-open），否则会把所有人锁在门外。"""
        _x('DROP TABLE IF EXISTS panel_session')
        panel_session.reset_cache()
        valid, reason = panel_session.touch('whatever')
        self.assertTrue(valid)
        self.assertEqual(reason, 'unknown')
        # create() 也必须诚实：没落库就返回空串，不做「查不到的服务端会话」
        self.assertEqual(panel_session.create(self.uid, 'alice'), '')
        # 复原，避免影响后续用例
        _heal_schema()


class LoginGuardTest(unittest.TestCase):
    """B2 验收：IP 单维 + 账号跨 IP 双维度都必须能封禁。"""

    def setUp(self):
        login_guard.reset_cache()
        self.limit = login_guard.LOGIN_FAIL_LIMIT

    def test_20_ip_dimension_ban(self):
        ip = '198.51.100.10'
        login_guard.reset(ip, 'user-a')
        blocked = False
        for _ in range(self.limit):
            blocked, remain = login_guard.register_failure(ip, 'user-a')
        self.assertTrue(blocked, '同一 IP 连续失败达上限必须封禁')
        self.assertTrue(login_guard.is_banned(ip, 'user-a'))
        self.assertEqual(remain, 0)
        login_guard.reset(ip, 'user-a')
        self.assertFalse(login_guard.is_banned(ip, 'user-a'))

    def test_21_account_dimension_across_ips(self):
        """验收标准：同一账号从 6 个不同 IP 各失败 1 次后，第 6 次被拒。"""
        username = 'victim-account'
        login_guard.reset(None, username)
        blocked = False
        for i in range(self.limit):
            ip = '203.0.113.%d' % (100 + i)
            login_guard.reset(ip, None)
            blocked, _remain = login_guard.register_failure(ip, username)
        self.assertTrue(blocked, '账号维度跨 IP 累计失败达上限必须封禁')
        # 换一个全新 IP，仅凭账号维度也必须被拦
        fresh_ip = '203.0.113.250'
        login_guard.reset(fresh_ip, None)
        self.assertTrue(login_guard.is_banned(fresh_ip, username))
        login_guard.reset(None, username)
        self.assertFalse(login_guard.is_banned(fresh_ip, username))

    def test_22_failure_count_and_reset(self):
        ip = '198.51.100.22'
        login_guard.reset(ip, 'user-c')
        self.assertEqual(login_guard.failure_count(ip, 'user-c'), 0)
        login_guard.register_failure(ip, 'user-c')
        login_guard.register_failure(ip, 'user-c')
        self.assertEqual(login_guard.failure_count(ip, 'user-c'), 2)
        login_guard.reset(ip, 'user-c')
        self.assertEqual(login_guard.failure_count(ip, 'user-c'), 0)

    def test_23_memory_fallback_when_table_missing(self):
        """表不可用时退回进程内存计数，限流不能凭空消失。"""
        _x('DROP TABLE IF EXISTS panel_login_failure')
        login_guard.reset_cache()
        ip = '198.51.100.33'
        login_guard.reset(ip, None)
        blocked = False
        for _ in range(self.limit):
            blocked, _remain = login_guard.register_failure(ip, None)
        self.assertTrue(blocked)
        self.assertTrue(login_guard.is_banned(ip, None))
        login_guard.reset(ip, None)
        # 复原
        _heal_schema()
        login_guard.reset_cache()


class CallSiteGuardTest(unittest.TestCase):
    """静态守卫：确认关键调用点真的接上了（防「写了模块没人用」）。"""

    def test_30_islogined_checks_server_session(self):
        src = _read('web/admin/common.py')
        self.assertIn('panel_session.touch(', src)
        self.assertIn('def invalidate_login_cache(', src)
        self.assertIn('panel_session.create(', src)
        # 撤销后必须清缓存，否则 20s 内仍算已登录
        self.assertIn('invalidate_login_cache', src)

    def test_31_login_success_registers_session(self):
        src = _read('web/admin/dashboard/login.py')
        body = src.split('def _login_success')[1].split('def login_temp_user')[0]
        self.assertIn('panel_session.create(', body)
        self.assertIn("session['session_id']", body)
        # 生命周期统一为 1 天（不再与 Cookie 寿命冲突）
        self.assertNotIn('7 * 24 * 60 * 60', body)
        self.assertIn('panel_session.SESSION_TTL', body)

    def test_32_password_change_revokes_sessions(self):
        src = _read('web/admin/setting/setting.py')
        body = src.split('def set_password')[1].split('# 设置面板端口')[0]
        self.assertIn('revoke_user_sessions(', body)
        self.assertIn('invalidate_login_cache(', body)

    def test_33_2fa_change_revokes_sessions(self):
        src = _read('web/admin/setting/secondary_verifiy.py')
        self.assertIn('_revoke_other_sessions', src)
        self.assertIn('revoke_user_sessions(', src)

    def test_34_login_uses_dual_dimension_guard(self):
        src = _read('web/admin/dashboard/login.py')
        self.assertIn('core.login_guard', src)
        # 密码失败必须带上 username，账号维度才生效
        self.assertIn('_register_login_failure(client_ip, username)', src)
        self.assertIn('_reset_login_failure(client_ip, username)', src)

    def test_35_endpoints_exposed(self):
        src = _read('web/admin/setting/setting.py')
        for ep in ("'/get_sessions'", "'/revoke_session'", "'/unlock_login'"):
            self.assertIn(ep, src)
        ui = _read('web/templates/default/setting.html')
        self.assertIn('sessionManage()', ui)
        js = _read('web/static/app/config.js')
        self.assertIn('function sessionManage(', js)
        self.assertIn("'/setting/get_sessions'", js)
        self.assertIn("'/setting/revoke_session'", js)


if __name__ == '__main__':
    unittest.main()
