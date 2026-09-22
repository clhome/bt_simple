# coding:utf-8
import os
import sys
import json
import time
import sqlite3
import unittest
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
web_dir = os.path.join(PROJECT_ROOT, "web")
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)

import core.yf as yf
from plugins.data_query import common_db

class TestSyncAndSpeed(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 隔离真实面板 SQLite：这些用例会通过 common_db 写
        # <serverDir>/data_query/data_query.db。门禁是**并行**跑模块的，
        # 多个模块同时写同一个 sqlite 文件会 `sqlite3.OperationalError:
        # database is locked`（实测让 2 个模块假红）。
        # 把 sqlite 文件重定向到本进程专属临时目录即可彻底隔离。
        cls._db_tmp = tempfile.mkdtemp(prefix='yufeng_dq_db_')
        common_db.getSqliteFile = lambda: os.path.join(cls._db_tmp, 'data_query.db')
        # 再把 serverDir 指向本进程专属临时区，并在里面**造一份假的「已装 MySQL」**：
        # ① 性能：本机仓库所在的 F: 盘上普通文件读写是 0.00s，但 sqlite 每次连接要
        #    **30s**（Windows 的字节范围文件锁在该盘上忙等到超时）。
        #    common_db.detectLocalMySQLPasswords() 会扫 <serverDir>/*/*.db，
        #    单次 _get_sqlite_field 就 30~60s，足以把整个模块拖到超时。
        # ② 确定性：自动探测有了确定的输入，用例不再依赖本机是否真装了 MySQL。
        cls._server_tmp = tempfile.mkdtemp(prefix='yufeng_server_')
        os.makedirs(os.path.join(cls._server_tmp, 'mysql'), exist_ok=True)
        _seed = sqlite3.connect(os.path.join(cls._server_tmp, 'mysql', 'mysql.db'))
        _seed.execute('CREATE TABLE IF NOT EXISTS config (mysql_root TEXT)')
        _seed.execute('INSERT INTO config (mysql_root) VALUES (?)', ('unit_test_root_pwd',))
        _seed.commit()
        _seed.close()
        yf.getServerDir = staticmethod(lambda: cls._server_tmp)

    def setUp(self):
        self.conn = common_db.getSqliteConn()

    def tearDown(self):
        if hasattr(self, 'conn') and self.conn:
            try:
                self.conn.close()
            except Exception:
                pass

    def test_01_sqlite_cache_hit_speed_optimization(self):
        """测试已存在本地数据库配置时，getUnifiedServerList 实现毫秒级快速返回"""
        common_db._upsert_auto_connection(
            name='本机配置',
            db_type='mysql',
            host='127.0.0.1',
            port=3306,
            username='root',
            password=common_db.encodePassword('root_pass'),
            auth_db='mysql',
            notes='__auto_local__'
        )

        t0 = time.time()
        res = common_db.getUnifiedServerList('mysql')
        cost_ms = (time.time() - t0) * 1000

        self.assertTrue(res.get('status'))
        items = res.get('data', [])
        self.assertTrue(len(items) > 0)
        has_local = any(x.get('group') == 'local' for x in items)
        self.assertTrue(has_local, "应当包含本地配置组")
        self.assertLess(cost_ms, 150.0, f"SQLite 缓存命中响应耗时过长: {cost_ms:.2f}ms")

    def test_02_scan_current_local_configs_independent(self):
        """测试纯扫描函数独立工作，返回合规的配置数据结构"""
        scanned = common_db.scanCurrentLocalConfigs()
        self.assertTrue(isinstance(scanned, list))
        for item in scanned:
            self.assertIn('db_type', item)
            self.assertIn('name', item)
            self.assertIn('host', item)
            self.assertIn('port', item)
            self.assertIn('notes', item)
            self.assertIn('instance_type', item)

    def test_03_preview_local_sync_diff_structure(self):
        """测试 previewLocalSyncDiff 准确生成差异结构并标识状态"""
        res = common_db.previewLocalSyncDiff()
        self.assertTrue(res.get('status'))
        data = res.get('data', {})
        self.assertIn('items', data)
        self.assertIn('has_diff', data)
        self.assertIn('total', data)
        items = data.get('items', [])
        for it in items:
            self.assertIn(it.get('status'), ('new', 'modified', 'identical'))
            self.assertIn('new_config', it)

    def test_04_apply_local_sync_selective_overwrite(self):
        """测试用户勾选选择性覆盖机制：仅覆盖勾选项，未勾选项保持原状"""
        common_db._upsert_auto_connection(
            name='本机配置',
            db_type='redis',
            host='127.0.0.1',
            port=6379,
            username='',
            password=common_db.encodePassword('orig_redis_pwd'),
            auth_db='',
            notes='__auto_local__'
        )
        common_db._upsert_auto_connection(
            name='本机配置',
            db_type='memcached',
            host='127.0.0.1',
            port=11211,
            username='',
            password='',
            auth_db='',
            notes='__auto_local__'
        )

        c = self.conn.cursor()
        c.execute("SELECT id, password FROM db_connections WHERE db_type='redis' AND notes='__auto_local__'")
        r_row = c.fetchone()
        redis_id = r_row['id']
        orig_redis_pwd = r_row['password']

        c.execute("SELECT id, port FROM db_connections WHERE db_type='memcached' AND notes='__auto_local__'")
        m_row = c.fetchone()
        mem_id = m_row['id']
        orig_mem_port = m_row['port']

        # 模拟用户仅勾选覆盖 Memcached 的端口为 11212，而未勾选 Redis
        sync_items = [
            {
                'id': mem_id,
                'db_type': 'memcached',
                'target_name': '本机配置',
                'instance_type': 'local',
                'new_config': {
                    'host': '127.0.0.1',
                    'port': 11212,
                    'username': '',
                    'password': '',
                    'auth_db': ''
                }
            }
        ]

        apply_res = common_db.applyLocalSync({'sync_items': sync_items})
        self.assertTrue(apply_res.get('status'))

        # 验证 Memcached 端口被成功覆盖更新
        c.execute("SELECT port FROM db_connections WHERE id = ?", (mem_id,))
        new_mem_row = c.fetchone()
        self.assertEqual(new_mem_row['port'], 11212, "勾选的 Memcached 端口应当被覆盖为 11212")

        # 验证未勾选的 Redis 完全保留原样（密码不变）
        c.execute("SELECT password FROM db_connections WHERE id = ?", (redis_id,))
        new_r_row = c.fetchone()
        self.assertEqual(new_r_row['password'], orig_redis_pwd, "未勾选的 Redis 配置应当保持完全不变")

    def test_05_file_encoding_and_lf(self):
        """测试所有涉及文件均为 UTF-8 无 BOM 且使用 LF 换行符"""
        checked_files = [
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'common_db.py'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'static', 'html', 'index.html'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'static', 'css', 'data.css'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'static', 'js', 'app.js'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'lang', 'zh-CN.json'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'lang', 'en.json'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'lang', 'zh-TW.json'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'lang', 'de.json'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'lang', 'fr.json'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'lang', 'it.json'),
        ]
        for fp in checked_files:
            self.assertTrue(os.path.exists(fp), f"文件不存在: {fp}")
            with open(fp, 'rb') as f:
                raw = f.read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), f"文件包含 UTF-8 BOM: {fp}")
            self.assertNotIn(b'\r\n', raw, f"文件包含 CRLF 换行符: {fp}")


if __name__ == '__main__':
    unittest.main()
