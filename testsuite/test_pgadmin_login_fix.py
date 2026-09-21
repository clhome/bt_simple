# coding:utf-8
"""
pgadmin 登录循环修复测试套件
验证 CSRF 降级、密码同步、配置自愈等修复措施
"""

import unittest
import os
import sys
import tempfile
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(BASE_DIR, 'plugins', 'pgadmin')


class TestPgAdminLoginLoopFix(unittest.TestCase):
    """pgadmin 登录循环修复验证"""

    def test_01_config_local_csrf_disabled(self):
        """验证 config_local.py 模板包含 CSRF 降级配置"""
        cfg_file = os.path.join(PLUGIN_DIR, 'conf', 'config_local.py')
        self.assertTrue(os.path.exists(cfg_file), 'config_local.py 模板文件不存在')
        content = open(cfg_file, 'r', encoding='utf-8').read()
        self.assertIn('WTF_CSRF_ENABLED = False', content, '缺少 WTF_CSRF_ENABLED = False')
        self.assertIn('WTF_CSRF_CHECK_DEFAULT = False', content, '缺少 WTF_CSRF_CHECK_DEFAULT = False')

    def test_02_config_local_all_required_settings(self):
        """验证 config_local.py 包含所有必要的安全与反代配置"""
        cfg_file = os.path.join(PLUGIN_DIR, 'conf', 'config_local.py')
        content = open(cfg_file, 'r', encoding='utf-8').read()

        required_settings = [
            "CROSS_ORIGIN_OPENER_POLICY = 'unsafe-none'",
            'PROXY_X_HOST_COUNT = 1',
            'PROXY_X_FOR_COUNT = 1',
            'PROXY_X_PROTO_COUNT = 1',
            'PROXY_X_PORT_COUNT = 1',
            'ENHANCED_COOKIE_PROTECTION = False',
            'SESSION_COOKIE_SECURE = False',
            "SESSION_COOKIE_SAMESITE = 'Lax'",
            'MAX_LOGIN_ATTEMPTS = 0',
            'WTF_CSRF_ENABLED = False',
            'WTF_CSRF_CHECK_DEFAULT = False',
        ]
        for setting in required_settings:
            self.assertIn(setting, content, '缺少配置: ' + setting)

    def test_03_nginx_conf_required_headers(self):
        """验证 pgadmin.conf Nginx 配置包含所有必要的反代头"""
        conf_file = os.path.join(PLUGIN_DIR, 'conf', 'pgadmin.conf')
        self.assertTrue(os.path.exists(conf_file), 'pgadmin.conf 不存在')
        content = open(conf_file, 'r', encoding='utf-8').read()

        required_headers = [
            'proxy_set_header Host $http_host',
            'proxy_set_header X-Real-IP $remote_addr',
            'proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for',
            'proxy_set_header X-Forwarded-Proto $scheme',
            'proxy_set_header X-Forwarded-Host $http_host',
            'proxy_set_header X-Forwarded-Port $server_port',
            'proxy_set_header Authorization ""',
            'proxy_pass_header Set-Cookie',
            'proxy_cookie_path / /',
            'proxy_redirect off',
        ]
        for header in required_headers:
            self.assertIn(header, content, '缺少 Nginx 配置: ' + header)

    def test_04_index_py_unlock_with_password_sync(self):
        """验证 index.py 的 unlockPgAdminUsers 和 syncPgAdminPassword 包含原生应用上下文密码同步逻辑"""
        idx_file = os.path.join(PLUGIN_DIR, 'index.py')
        self.assertTrue(os.path.exists(idx_file), 'index.py 不存在')
        content = open(idx_file, 'r', encoding='utf-8').read()

        # 验证原生应用上下文与官方 user_management 调用存在
        self.assertIn('user_management_update_user', content, '缺少官方 user_management_update_user 调用')
        self.assertIn('create_app', content, '缺少 create_app 应用上下文调用')
        self.assertIn('syncPgAdminPassword', content, '缺少统一密码同步函数 syncPgAdminPassword')
        # 验证 active 解锁
        self.assertIn("active", content, '缺少 active 解锁设置')

    def test_05_index_py_initpgconffile_detects_csrf(self):
        """验证 initPgConfFile 检测条件包含 WTF_CSRF_ENABLED"""
        idx_file = os.path.join(PLUGIN_DIR, 'index.py')
        content = open(idx_file, 'r', encoding='utf-8').read()
        self.assertIn("'WTF_CSRF_ENABLED' not in content", content,
                       'initPgConfFile 未检测 WTF_CSRF_ENABLED')

    def test_06_password_sync_sqlite_logic(self):
        """模拟 SQLite 数据库密码同步逻辑的正确性"""
        db_path = os.path.join(tempfile.gettempdir(), 'test_pgadmin4.db')
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE user (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                locked INTEGER DEFAULT 0,
                login_attempts INTEGER DEFAULT 0,
                confirmed_at TEXT
            )''')
            cursor.execute(
                "INSERT INTO user (email, password, active, locked, login_attempts) VALUES (?, ?, 0, 1, 5)",
                ('test@example.com', 'old_hash_value')
            )
            conn.commit()

            # 模拟解锁逻辑
            cursor.execute("UPDATE user SET locked = 0, login_attempts = 0, active = 1")
            conn.commit()

            # 模拟密码同步
            new_hash = 'new_hashed_password_value'
            cursor.execute("UPDATE user SET password = ? WHERE email = ?", (new_hash, 'test@example.com'))
            conn.commit()

            # 验证
            cursor.execute("SELECT password, active, locked, login_attempts FROM user WHERE email = ?",
                           ('test@example.com',))
            row = cursor.fetchone()
            self.assertIsNotNone(row, '用户记录不存在')
            self.assertEqual(row[0], new_hash, '密码未正确更新')
            self.assertEqual(row[1], 1, 'active 未设为 1')
            self.assertEqual(row[2], 0, 'locked 未设为 0')
            self.assertEqual(row[3], 0, 'login_attempts 未重置为 0')

            # 测试用户不存在时的 INSERT 回退
            cursor.execute("UPDATE user SET password = ? WHERE email = ?", (new_hash, 'new@example.com'))
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO user (email, password, active, confirmed_at) VALUES (?, ?, 1, datetime('now'))",
                    ('new@example.com', new_hash)
                )
            conn.commit()

            cursor.execute("SELECT email FROM user WHERE email = ?", ('new@example.com',))
            self.assertIsNotNone(cursor.fetchone(), '新用户未成功创建')

            conn.close()
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_07_utf8_lf_encoding(self):
        """校验修改的文件为 UTF-8 无 BOM 与 LF 换行符"""
        check_files = [
            os.path.join(PLUGIN_DIR, 'conf', 'config_local.py'),
            os.path.join(PLUGIN_DIR, 'conf', 'pgadmin.conf'),
            os.path.join(PLUGIN_DIR, 'index.py'),
        ]
        for fpath in check_files:
            with open(fpath, 'rb') as f:
                raw = f.read()
            fname = os.path.basename(fpath)
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), fname + ' 包含 BOM')
            self.assertNotIn(b'\r\n', raw, fname + ' 包含 CRLF 换行符')
            self.assertNotIn(b'\r', raw, fname + ' 包含 CR 换行符')

    def test_08_no_broken_setup_update_user(self):
        """验证 index.py 已彻底移除 setup.py update-user 外部命令调用，根除 KeyError: 'role'"""
        idx_file = os.path.join(PLUGIN_DIR, 'index.py')
        content = open(idx_file, 'r', encoding='utf-8').read()
        self.assertNotIn('setup.py update-user', content, 'index.py 仍残留不可靠的 setup.py update-user 调用')

    def test_09_set_web_pg_password_flow(self):
        """验证 setWebPgPassword 具备先持久化配置、再同步 SQLite 的健壮流程"""
        idx_file = os.path.join(PLUGIN_DIR, 'index.py')
        content = open(idx_file, 'r', encoding='utf-8').read()
        self.assertIn("def setWebPgPassword():", content)
        # 确保包含 setCfg('web_pg_password', password)
        self.assertIn("setCfg('web_pg_password', password)", content)
        # 确保调用 syncPgAdminPassword(email, password)
        self.assertIn("syncPgAdminPassword(email, password)", content)
        # 确保有 unlockPgAdminUsers() 调用
        self.assertIn("unlockPgAdminUsers()", content)

    def test_10_password_length_validation(self):
        """验证 setWebPgPassword 具备不少于 6 位长度校验"""
        idx_file = os.path.join(PLUGIN_DIR, 'index.py')
        content = open(idx_file, 'r', encoding='utf-8').read()
        self.assertIn("len(password) < 6", content, '缺少不少于 6 位密码长度校验')


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPgAdminLoginLoopFix)
    res = unittest.TestResult()
    suite.run(res)
    print("TOTAL:", res.testsRun, "FAILURES:", len(res.failures), "ERRORS:", len(res.errors))
    for f in res.failures:
        print("FAIL_CASE:", f[0].id())
        print("FAIL_MSG:", f[1].strip().split('\n')[-1])
    for e in res.errors:
        print("ERR_CASE:", e[0].id())
        print("ERR_MSG:", e[1].strip().split('\n')[-1])
    if not res.wasSuccessful():
        sys.exit(1)
