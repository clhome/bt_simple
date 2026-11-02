# coding:utf-8

import os
import sys
import unittest
import tempfile
import shutil
import sqlite3
import json

test_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(test_dir)
web_dir = os.path.join(project_dir, 'web')
plugins_dir = os.path.join(project_dir, 'plugins')
redis_dir = os.path.join(plugins_dir, 'redis')
data_query_dir = os.path.join(plugins_dir, 'data_query')

for p in [project_dir, web_dir, redis_dir, data_query_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

import core.yf as yf
import plugins.data_query.common_db as common_db
import plugins.data_query.nosql_redis as nosql_redis


class TestDataQueryRedisAuthFix(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix='test_dq_redis_')
        self.sandbox_server = os.path.join(self.tmp_dir, 'server', 'redis')
        os.makedirs(self.sandbox_server, exist_ok=True)

        common_db.getDataQueryDir = lambda: self.tmp_dir
        common_db.getSqliteConn().close()

        nosql_redis.common_db = common_db
        sys.modules['common_db'] = common_db

        common_db.yf.getServerDir = lambda: os.path.join(self.tmp_dir, 'server')
        nosql_redis.yf.getServerDir = lambda: os.path.join(self.tmp_dir, 'server')

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_detect_local_redis_conf_parsing(self):
        """测试复杂密码（双引号含空格与特殊符号、单引号、普通注释）的精准解析"""
        ins = nosql_redis.nosqlRedisCtr().getInstanceBySid(0)

        # 1. 双引号密码含空格和特殊字符
        conf_path = os.path.join(self.sandbox_server, 'redis.conf')
        yf.writeFile(conf_path, 'port 6388\nrequirepass "Complex Pass 2026!#@"\n')
        c1 = ins._detect_local_redis_conf()
        self.assertEqual(c1.get('port'), 6388)
        self.assertEqual(c1.get('requirepass'), 'Complex Pass 2026!#@')

        # 2. 单引号密码
        yf.writeFile(conf_path, "port 6389\nrequirepass 'Single_Pass_99'\n")
        c2 = ins._detect_local_redis_conf()
        self.assertEqual(c2.get('port'), 6389)
        self.assertEqual(c2.get('requirepass'), 'Single_Pass_99')

        # 3. 未加引号带注释
        yf.writeFile(conf_path, "port 6390\nrequirepass PlainPass123 # 这是一条注释\n")
        c3 = ins._detect_local_redis_conf()
        self.assertEqual(c3.get('port'), 6390)
        self.assertEqual(c3.get('requirepass'), 'PlainPass123')

        # 4. 未设置密码 (注释掉)
        yf.writeFile(conf_path, "port 6379\n# requirepass foobared\n")
        c4 = ins._detect_local_redis_conf()
        self.assertEqual(c4.get('port'), 6379)
        self.assertEqual(c4.get('requirepass'), '')

    def test_02_redis_conn_self_healing_from_old_wrong_password(self):
        """测试当 SQLite 中记录的密码失效（报错 invalid username-password）时，自动自愈为权威密码并回写 SQLite"""
        real_pass = 'Authoritative_Pass_2026'
        conf_path = os.path.join(self.sandbox_server, 'redis.conf')
        yf.writeFile(conf_path, f'port 6379\nrequirepass "{real_pass}"\n')

        wrong_old_pass = 'OldWrongPass888'
        common_db._upsert_auto_connection(
            name='本机配置',
            db_type='redis',
            host='127.0.0.1',
            port=6379,
            username='',
            password=common_db.encodePassword(wrong_old_pass),
            auth_db='',
            notes='__auto_local__'
        )

        c_list = common_db.getConnectionList({'db_type': 'redis'}).get('data', [])
        self.assertEqual(len(c_list), 1)
        conn_id = c_list[0]['id']

        raw_c = common_db.getConnection({'id': conn_id}, raw_password=True).get('data')
        self.assertEqual(raw_c.get('password'), wrong_old_pass)

        import types
        mock_redis_mod = types.ModuleType('redis')

        class MockRedisClient:
            def __init__(self, connection_pool=None, **kwargs):
                self.pool = connection_pool
                self.pwd = connection_pool.connection_kwargs.get('password') if connection_pool else kwargs.get('password')

            def ping(self):
                if self.pwd == real_pass:
                    return True
                raise Exception("AuthenticationError: WRONGPASS invalid username-password pair or user is disabled.")

            def close(self):
                pass

        class MockConnectionPool:
            def __init__(self, host='127.0.0.1', port=6379, password=None, **kwargs):
                self.connection_kwargs = {'password': password, 'host': host, 'port': port}

            def disconnect(self):
                pass

        mock_redis_mod.ConnectionPool = MockConnectionPool
        mock_redis_mod.Redis = MockRedisClient
        old_redis_module = sys.modules.get('redis')
        sys.modules['redis'] = mock_redis_mod

        try:
            ins = nosql_redis.nosqlRedisCtr().getInstanceBySid(f"conn_{conn_id}")
            self.assertEqual(ins._nosqlRedis__DB_PASS, wrong_old_pass)

            conn = ins.redis_conn(0)
            self.assertIsNotNone(conn, "自愈后应成功返回连接对象")
            self.assertIsNone(ins.getLastError(), "自愈后不应保留错误")
            self.assertEqual(ins._nosqlRedis__DB_PASS, real_pass, "实例密码应自愈为真实权威密码")

            updated_raw = common_db.getConnection({'id': conn_id}, raw_password=True).get('data')
            self.assertEqual(updated_raw.get('password'), real_pass, "自愈机制必须将正确密码自动持久化至 SQLite db_connections")

        finally:
            if old_redis_module:
                sys.modules['redis'] = old_redis_module
            else:
                sys.modules.pop('redis', None)

    def test_03_redis_conn_self_healing_to_empty_password(self):
        """测试当 Redis 清空为无密码状态而 SQLite 残留旧密码时，自愈为空密码并清除 SQLite 旧密码"""
        conf_path = os.path.join(self.sandbox_server, 'redis.conf')
        yf.writeFile(conf_path, 'port 6379\n# requirepass foobared\n')

        old_pass = 'OldObsoletePass'
        common_db._upsert_auto_connection(
            name='本机配置',
            db_type='redis',
            host='127.0.0.1',
            port=6379,
            password=common_db.encodePassword(old_pass),
            notes='__auto_local__'
        )
        c_list = common_db.getConnectionList({'db_type': 'redis'}).get('data', [])
        conn_id = c_list[0]['id']

        import types
        mock_redis_mod = types.ModuleType('redis')

        class MockRedisClientEmpty:
            def __init__(self, connection_pool=None, **kwargs):
                self.pool = connection_pool
                self.pwd = connection_pool.connection_kwargs.get('password') if connection_pool else kwargs.get('password')

            def ping(self):
                if not self.pwd:
                    return True
                raise Exception("AuthenticationError: WRONGPASS invalid username-password pair or user is disabled.")

            def close(self):
                pass

        class MockConnectionPoolEmpty:
            def __init__(self, host='127.0.0.1', port=6379, password=None, **kwargs):
                self.connection_kwargs = {'password': password, 'host': host, 'port': port}

            def disconnect(self):
                pass

        mock_redis_mod.ConnectionPool = MockConnectionPoolEmpty
        mock_redis_mod.Redis = MockRedisClientEmpty
        old_redis_module = sys.modules.get('redis')
        sys.modules['redis'] = mock_redis_mod

        try:
            ins = nosql_redis.nosqlRedisCtr().getInstanceBySid(f"conn_{conn_id}")
            conn = ins.redis_conn(0)
            self.assertIsNotNone(conn)
            self.assertEqual(ins._nosqlRedis__DB_PASS, '')

            updated_raw = common_db.getConnection({'id': conn_id}, raw_password=True).get('data')
            self.assertEqual(updated_raw.get('password'), '', "SQLite 中的旧密码应被清除为空")
        finally:
            if old_redis_module:
                sys.modules['redis'] = old_redis_module
            else:
                sys.modules.pop('redis', None)

    def test_04_preview_and_apply_sync_with_empty_password(self):
        """测试服务侧同步功能在探测到无密码时能够正常更新置空，不再受错误保护机制阻塞"""
        conf_path = os.path.join(self.sandbox_server, 'redis.conf')
        yf.writeFile(conf_path, 'port 6379\n# requirepass foobared\n')

        common_db._upsert_auto_connection(
            name='本机配置',
            db_type='redis',
            host='127.0.0.1',
            port=6379,
            password=common_db.encodePassword('ExistingOldPass'),
            notes='__auto_local__'
        )

        diff_res = common_db.previewLocalSyncDiff({'db_type': 'redis'})
        self.assertTrue(diff_res.get('status'))
        all_items = diff_res.get('data', {}).get('items', [])
        items = [it for it in all_items if it.get('db_type') == 'redis']
        self.assertEqual(len(items), 1)
        r_item = items[0]
        self.assertEqual(r_item['status'], 'modified')
        self.assertIn("密码: 已清空(未设密码)", r_item['diff_details'])

        apply_res = common_db.applyLocalSync({'sync_items': items})
        self.assertTrue(apply_res.get('status'))

        c_list = common_db.getConnectionList({'db_type': 'redis'}).get('data', [])
        conn_id = c_list[0]['id']
        raw_c = common_db.getConnection({'id': conn_id}, raw_password=True).get('data')
        self.assertEqual(raw_c.get('password'), '', "应用同步后密码应成功置空")


if __name__ == '__main__':
    unittest.main()
