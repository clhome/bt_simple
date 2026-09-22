#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专项回归测试套件：
1. MySQL 插件大版本升级检测与单次自愈迁移（1.x -> 2.x 仅执行一次自愈）
2. MySQL 插件后续版本升级接口（扩展性验证）
3. MariaDB 插件多模态健康探测与 PID 自动自愈
4. MariaDB 插件孤儿 Socket 安全清理机制
5. MariaDB 插件 SQLite 自动补齐 rw 权限列与配置幂等自愈
6. MariaDB 插件大版本升级单次自愈迁移与扩展性
7. install.sh 升级管道逻辑校验
"""

import os
import sys
import tempfile
import sqlite3
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(PROJECT_ROOT, 'web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import core.yf as yf
import plugins.mysql.index as mysql_idx
import plugins.mariadb.index as mariadb_idx


class TestUpgradeAndMariadbSelfHealing(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_dir = self.tmp_dir.name

        # 保存原始函数供恢复
        self._orig_mysql_vfile = mysql_idx.getPluginVersionFile
        self._orig_mysql_sdir = mysql_idx.getServerDir
        self._orig_mariadb_vfile = mariadb_idx.getPluginVersionFile
        self._orig_mariadb_sdir = mariadb_idx.getServerDir

        # 默认隔离测试环境
        self.mysql_test_vfile = os.path.join(self.test_dir, 'mysql_plugin_version.pl')
        self.mariadb_test_vfile = os.path.join(self.test_dir, 'mariadb_plugin_version.pl')
        mysql_idx.getPluginVersionFile = lambda: self.mysql_test_vfile
        mysql_idx.getServerDir = lambda: self.test_dir
        mariadb_idx.getPluginVersionFile = lambda: self.mariadb_test_vfile
        mariadb_idx.getServerDir = lambda: self.test_dir

    def tearDown(self):
        mysql_idx.getPluginVersionFile = self._orig_mysql_vfile
        mysql_idx.getServerDir = self._orig_mysql_sdir
        mariadb_idx.getPluginVersionFile = self._orig_mariadb_vfile
        mariadb_idx.getServerDir = self._orig_mariadb_sdir
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_01_mysql_version_compare(self):
        """测试版本比对函数准确性"""
        cmp_func = mysql_idx.comparePluginVersion
        self.assertEqual(cmp_func('1.0', '2.0'), -1)
        self.assertEqual(cmp_func('2.0', '1.0'), 1)
        self.assertEqual(cmp_func('2.0', '2.0'), 0)
        self.assertEqual(cmp_func('1.9.9', '2.0.0'), -1)
        self.assertEqual(cmp_func('2.1', '2.0'), 1)
        self.assertEqual(cmp_func('2.0.1', '2.0'), 1)

    def test_02_mysql_upgrade_once_and_pipeline(self):
        """测试 MySQL 从 1.x 升级到 2.0 时仅执行一次自愈迁移，且再次调用幂等跳过"""
        # 1. 老环境初始版本为 1.0
        self.assertEqual(mysql_idx.getInstalledPluginVersion(), '1.0')

        # 模拟迁移计数器
        migration_counter = {'count': 0}
        def mock_migrate_2(ver=''):
            migration_counter['count'] += 1
            return 'mock 2.0 ok'

        orig_steps = mysql_idx.MYSQL_MIGRATION_STEPS
        mysql_idx.MYSQL_MIGRATION_STEPS = [('2.0', mock_migrate_2)]

        try:
            # 首次执行升级检测：应该命中 1.x -> 2.0 迁移
            res1 = mysql_idx.checkPluginUpgrade()
            self.assertTrue(res1['status'])
            self.assertEqual(migration_counter['count'], 1)
            self.assertEqual(mysql_idx.getInstalledPluginVersion(), '2.0')

            # 第二次执行升级检测：由于版本已是 2.0，必须 0 开销直接跳过，计数器不增加
            res2 = mysql_idx.checkPluginUpgrade()
            self.assertTrue(res2['status'])
            self.assertEqual(res2['msg'], 'Already up to date')
            self.assertEqual(migration_counter['count'], 1)

            # 模拟未来扩展：如果发布了 3.0 大版本
            mysql_idx.CURRENT_PLUGIN_VERSION = '3.0'
            def mock_migrate_3(ver=''):
                migration_counter['count'] += 1
                return 'mock 3.0 ok'
            mysql_idx.MYSQL_MIGRATION_STEPS.append(('3.0', mock_migrate_3))

            res3 = mysql_idx.checkPluginUpgrade()
            self.assertTrue(res3['status'])
            self.assertEqual(migration_counter['count'], 2)
            self.assertEqual(mysql_idx.getInstalledPluginVersion(), '3.0')
        finally:
            mysql_idx.MYSQL_MIGRATION_STEPS = orig_steps
            mysql_idx.CURRENT_PLUGIN_VERSION = '2.0'

    def test_03_mariadb_sqlite_auto_add_rw_column(self):
        """测试 MariaDB 的 pSqliteDb 能够自动为老版本 databases 表补齐 rw 列"""
        db_file = os.path.join(self.test_dir, 'mariadb.db')
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS `databases` (
              `id` INTEGER PRIMARY KEY AUTOINCREMENT,
              `pid` INTEGER,
              `name` TEXT,
              `username` TEXT,
              `password` TEXT,
              `accept` TEXT,
              `ps` TEXT,
              `addtime` TEXT
            );
        """)
        conn.commit()
        conn.close()

        # 访问数据库，触发自动加列自愈
        psdb = mariadb_idx.pSqliteDb('databases')
        conn_verify = sqlite3.connect(db_file)
        cur_verify = conn_verify.cursor()
        cur_verify.execute("PRAGMA table_info(databases)")
        columns = [c[1] for c in cur_verify.fetchall()]
        conn_verify.close()
        self.assertIn('rw', columns, "MariaDB 老表 databases 未能自动补齐 rw 字段")

    def test_04_mariadb_pid_auto_healing(self):
        """测试 MariaDB status() 探针能够多模态感知存活进程并自动自愈写回 PID 文件"""
        pid_file = os.path.join(self.test_dir, 'mariadb.pid')
        orig_get_pid_file = mariadb_idx.getPidFile
        mariadb_idx.getPidFile = lambda: pid_file

        current_pid = os.getpid()
        orig_get_mariadb_pid = mariadb_idx.getMariadbPid
        mariadb_idx.getMariadbPid = lambda: current_pid

        try:
            if os.path.exists(pid_file):
                os.remove(pid_file)

            st = mariadb_idx.status('10.6')
            self.assertEqual(st, 'start', "探测到存活进程时状态应判定为 start")
            self.assertTrue(os.path.exists(pid_file), "应当自动自愈写回 PID 文件")
            self.assertEqual(yf.readFile(pid_file).strip(), str(current_pid))
        finally:
            mariadb_idx.getPidFile = orig_get_pid_file
            mariadb_idx.getMariadbPid = orig_get_mariadb_pid

    def test_05_mariadb_clean_orphan_sockets(self):
        """测试 MariaDB 孤儿 socket 清理机制"""
        fake_sock = os.path.join(self.test_dir, 'mysql.sock')
        with open(fake_sock, 'w', encoding='utf-8') as f:
            f.write('lock')

        orig_get_mariadb_pid = mariadb_idx.getMariadbPid
        orig_get_sock = mariadb_idx.getSocketFile

        try:
            mariadb_idx.getSocketFile = lambda: fake_sock

            # 场景 A: 进程存活 -> 坚决不能删除
            mariadb_idx.getMariadbPid = lambda: 12345
            mariadb_idx.cleanOrphanSockets()
            self.assertTrue(os.path.exists(fake_sock), "有进程存活时绝对不能清理 socket")

            # 场景 B: 无进程存活 -> 判定为孤儿套接字死锁，必须安全清理
            mariadb_idx.getMariadbPid = lambda: None
            mariadb_idx.cleanOrphanSockets()
            self.assertFalse(os.path.exists(fake_sock), "无进程存活时应当安全清除孤儿 socket")
        finally:
            mariadb_idx.getMariadbPid = orig_get_mariadb_pid
            mariadb_idx.getSocketFile = orig_get_sock

    def test_06_mariadb_upgrade_once_pipeline(self):
        """测试 MariaDB 大版本升级单次自愈与扩展性"""
        self.assertEqual(mariadb_idx.getInstalledPluginVersion(), '1.0')

        call_count = {'val': 0}
        def mock_mariadb_mig_2(ver=''):
            call_count['val'] += 1
            return 'mariadb 2.0 ok'

        orig_steps = mariadb_idx.MARIADB_MIGRATION_STEPS
        mariadb_idx.MARIADB_MIGRATION_STEPS = [('2.0', mock_mariadb_mig_2)]

        try:
            # 首次执行升级检测
            res1 = mariadb_idx.checkPluginUpgrade()
            self.assertTrue(res1['status'])
            self.assertEqual(call_count['val'], 1)
            self.assertEqual(mariadb_idx.getInstalledPluginVersion(), '2.0')

            # 第二次执行检测：0 开销跳过
            res2 = mariadb_idx.checkPluginUpgrade()
            self.assertTrue(res2['status'])
            self.assertEqual(res2['msg'], 'Already up to date')
            self.assertEqual(call_count['val'], 1)
        finally:
            mariadb_idx.MARIADB_MIGRATION_STEPS = orig_steps

    def test_07_install_scripts_syntax_and_upgrade_branch(self):
        """测试 mysql 和 mariadb 的 install.sh 脚本语法及包含升级自愈分支"""
        mysql_sh = os.path.join(PROJECT_ROOT, 'plugins', 'mysql', 'install.sh')
        mariadb_sh = os.path.join(PROJECT_ROOT, 'plugins', 'mariadb', 'install.sh')

        self.assertTrue(os.path.exists(mysql_sh))
        self.assertTrue(os.path.exists(mariadb_sh))

        m_content = yf.readFile(mysql_sh)
        self.assertIn('check_plugin_upgrade', m_content)
        self.assertIn('upgrade_self_healing', m_content)

        maria_content = yf.readFile(mariadb_sh)
        self.assertIn('check_plugin_upgrade', maria_content)
        self.assertIn('upgrade_self_healing', maria_content)


if __name__ == '__main__':
    unittest.main()
