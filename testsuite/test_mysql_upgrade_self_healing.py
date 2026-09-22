# coding: utf-8
import os
import sys
import unittest
import shutil
import tempfile
import sqlite3
from unittest.mock import patch, MagicMock

# 确保 web 目录加入 sys.path 以加载核心组件
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(WORKSPACE_DIR, 'web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

plugins_mysql_dir = os.path.join(WORKSPACE_DIR, 'plugins', 'mysql')
if plugins_mysql_dir not in sys.path:
    sys.path.insert(0, plugins_mysql_dir)

import core.yf as yf
import plugins.mysql.index as mysql_index
import plugins.data_query.common_db as common_db
import plugins.data_query.sql_mysql as data_query_mysql

class TestMySQLUpgradeSelfHealing(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='mysql_test_healing_')

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_status_pid_self_healing(self):
        """测试 1: 验证 status() 在 PID 文件丢失或失效时，能通过真实进程探测自动自愈写回 PID"""
        test_pid_file = os.path.join(self.test_dir, 'mysql.pid')
        fake_live_pid = 99881

        with patch.object(mysql_index, 'getPidFile', return_value=test_pid_file), \
             patch.object(mysql_index, 'getMysqldPid', return_value=fake_live_pid), \
             patch.object(yf, 'checkPid', side_effect=lambda pid: pid == fake_live_pid):

            # 场景 A: pid_file 缺失，但后台有真实进程存活
            self.assertFalse(os.path.exists(test_pid_file))
            st = mysql_index.status('5.7')
            self.assertEqual(st, 'start', "真实进程存活时，status 必须返回 start")
            self.assertTrue(os.path.exists(test_pid_file), "status 必须自愈重建 pid 文件")
            self.assertEqual(yf.readFile(test_pid_file).strip(), str(fake_live_pid), "自愈写回的 PID 必须与真实进程一致")

            # 场景 B: pid_file 存在且有效，直接返回 start
            st2 = mysql_index.status('5.7')
            self.assertEqual(st2, 'start')

            # 场景 C: pid_file 里是死进程 (7777)，但系统有真实进程 fake_live_pid (99881)
            yf.writeFile(test_pid_file, '7777')
            st3 = mysql_index.status('5.7')
            self.assertEqual(st3, 'start')
            self.assertEqual(yf.readFile(test_pid_file).strip(), str(fake_live_pid), "死 PID 必须被自动校准替换为真实存活 PID")

    def test_02_status_stops_when_no_process(self):
        """测试 2: 当无 PID 且无任何 mysqld 进程存活时，准确返回 stop"""
        test_pid_file = os.path.join(self.test_dir, 'non_existent.pid')
        with patch.object(mysql_index, 'getPidFile', return_value=test_pid_file), \
             patch.object(mysql_index, 'getMysqldPid', return_value=None), \
             patch.object(mysql_index, 'getSocketFile', return_value='/tmp/non_existent_test.sock'), \
             patch.object(yf, 'isSupportSystemctl', return_value=False):
            st = mysql_index.status('5.7')
            self.assertEqual(st, 'stop', "没有任何存活进程时必须返回 stop")

    def test_03_data_directory_zero_touch_protection(self):
        """测试 3: 验证已有数据目录零触碰防御机制，绝对不改名、不备份、不二次初始化"""
        fake_datadir = os.path.join(self.test_dir, 'data')
        os.makedirs(fake_datadir, exist_ok=True)
        # 模拟已有数据库目录与用户表
        mysql_sys_dir = os.path.join(fake_datadir, 'mysql')
        os.makedirs(mysql_sys_dir, exist_ok=True)
        user_db_dir = os.path.join(fake_datadir, 'my_blog_db')
        os.makedirs(user_db_dir, exist_ok=True)

        # 1. 验证 isMysqlDataInited 检测
        self.assertTrue(mysql_index.isMysqlDataInited(fake_datadir), "包含 mysql 或业务库的数据目录必须识别为已初始化")

        # 2. 模拟启动时调用 initMysql57Data
        with patch.object(mysql_index, 'getDataDir', return_value=fake_datadir), \
             patch.object(yf, 'execShell') as mock_exec:
            res = mysql_index.initMysql57Data()
            self.assertTrue(res, "已有数据目录必须直接返回 True")
            mock_exec.assert_not_called()

            # 验证数据目录完好无损，未被重命名为 _backup_
            self.assertTrue(os.path.exists(user_db_dir), "用户业务数据库必须完整保留，绝不被移动")
            backup_dirs = [d for d in os.listdir(self.test_dir) if '_backup_' in d]
            self.assertEqual(len(backup_dirs), 0, "严禁生成任何破坏性的 backup 目录")

    def test_04_sqlite_schema_rw_column_idempotent_migration(self):
        """测试 4: 验证老版本 SQLite 数据库 (缺少 rw 字段) 在 pSqliteDb 中平滑无损自动补齐"""
        fake_server_dir = os.path.join(self.test_dir, 'server_mysql')
        os.makedirs(fake_server_dir, exist_ok=True)
        db_file = os.path.join(fake_server_dir, 'mysql.db')

        # 创建老版本结构的 databases 表（不含 rw 字段）
        raw_conn = sqlite3.connect(db_file)
        raw_conn.execute("""
            CREATE TABLE `databases` (
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
        # 插入一条已有业务数据库记录
        raw_conn.execute("""
            INSERT INTO `databases` (pid, name, username, password, accept, ps, addtime)
            VALUES (0, 'shop_prod', 'shop_user', 'SecPass123', '127.0.0.1', '生产商城库', '2026-08-01 10:00:00')
        """)
        raw_conn.commit()
        raw_conn.close()

        # 验证初始状态确实无 rw 字段
        chk_conn = sqlite3.connect(db_file)
        cols_before = [c[1] for c in chk_conn.execute("PRAGMA table_info('databases')").fetchall()]
        chk_conn.close()
        self.assertNotIn('rw', cols_before, "老表初始状态不应包含 rw 字段")

        # 通过 pSqliteDb 读取，触发自愈
        with patch.object(mysql_index, 'getServerDir', return_value=fake_server_dir):
            conn = mysql_index.pSqliteDb('databases')
            # 校验自愈后字段结构
            cols_after = [c.get('name') if isinstance(c, dict) else c[1] for c in conn.query("PRAGMA table_info('databases')")]
            self.assertIn('rw', cols_after, "自愈后必须自动补齐 rw 字段")

            # 校验老数据依然完好无损，且 rw 默认补齐为 'all'
            row = conn.where("name=?", ('shop_prod',)).find()
            self.assertIsNotNone(row)
            self.assertEqual(row.get('name'), 'shop_prod')
            self.assertEqual(row.get('username'), 'shop_user')
            self.assertEqual(row.get('rw'), 'all', "老数据 rw 字段必须平滑填充默认值 all")

    def test_05_safe_start_does_not_kill_running_mysql(self):
        """测试 5: 验证 start() 在 MySQL 已经运行时坚决不执行 pkill -9，直接返回 ok"""
        with patch.object(mysql_index, 'status', return_value='start'), \
             patch.object(yf, 'execShell') as mock_exec, \
             patch.object(mysql_index, 'appCMD') as mock_app_cmd:
            res = mysql_index.start('5.7')
            self.assertEqual(res, 'ok')
            mock_exec.assert_not_called()
            mock_app_cmd.assert_not_called()

    def test_06_upgrade_self_healing_end_to_end(self):
        """测试 6: 验证 upgrade_self_healing 端到端执行与自愈汇报"""
        fake_server_dir = os.path.join(self.test_dir, 'server_mysql')
        os.makedirs(fake_server_dir, exist_ok=True)

        with patch.object(mysql_index, 'getServerDir', return_value=fake_server_dir), \
             patch.object(mysql_index, 'initDreplace') as mock_initd, \
             patch.object(mysql_index, 'status', return_value='start'):

            # 模拟在 config 表中存有 root 密码
            test_db = os.path.join(fake_server_dir, 'mysql.db')
            sq_conn = sqlite3.connect(test_db)
            sq_conn.execute("CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY, mysql_root TEXT);")
            sq_conn.execute("INSERT OR REPLACE INTO config (id, mysql_root) VALUES (1, 'root_pass_666');")
            sq_conn.commit()
            sq_conn.close()

            res_json = mysql_index.upgradeSelfHealing('5.7')
            import json
            res = json.loads(res_json)
            self.assertTrue(res.get('status'), "升级自愈必须返回成功状态")
            mock_initd.assert_called_once()

            # 验证快照文件已自动自愈同步生成
            self.assertTrue(os.path.exists(os.path.join(fake_server_dir, 'mysql_root.pl')))
            self.assertEqual(yf.readFile(os.path.join(fake_server_dir, 'mysql_root.pl')).strip(), 'root_pass_666')
            self.assertTrue(os.path.exists(os.path.join(fake_server_dir, 'default.pl')))
            self.assertEqual(yf.readFile(os.path.join(fake_server_dir, 'default.pl')).strip(), 'root_pass_666')

    def test_07_data_query_detects_healed_credentials(self):
        """测试 7: 验证 data_query 的 detectLocalMySQLPasswords 能够准确探测到自愈后的密码"""
        mysql_dir = os.path.join(self.test_dir, 'mysql')
        os.makedirs(mysql_dir, exist_ok=True)
        # 写入自愈生成的 default.pl 快照
        pl_file = os.path.join(mysql_dir, 'default.pl')
        yf.writeFile(pl_file, 'test_root_pwd_888')

        with patch.object(yf, 'getServerDir', return_value=self.test_dir):
            pwds = common_db.detectLocalMySQLPasswords()
            # 验证是否成功探测到了候选密码
            found = ('test_root_pwd_888' in pwds)
            self.assertTrue(found, "detectLocalMySQLPasswords 必须能探测到自愈快照中的 root 密码")


if __name__ == '__main__':
    unittest.main()
