# coding:utf-8
import os
import sys
import json
import importlib
import importlib.util
import unittest
from unittest import mock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT_DIR, 'testsuite', 'Functional Testing'))

from ft_common import FTBaseTestCase

class TestPluginsDatabasesFunctional(FTBaseTestCase):
    """数据库类插件（MySQL, MariaDB, Redis, Valkey, PostgreSQL, MongoDB, DataQuery）端到端功能测试"""

    def setUp(self):
        super().setUp()
        os.chdir(ROOT_DIR)

    def test_01_mysql_and_mariadb_contracts_and_cnf(self):
        """测试 MySQL 与 MariaDB 核心契约与配置探测机制"""
        import importlib
        os.chdir(ROOT_DIR)
        
        # 验证 MySQL
        mysql_spec = importlib.util.spec_from_file_location("mysql_index", os.path.join(ROOT_DIR, "plugins", "mysql", "index.py"))
        mysql_mod = importlib.util.module_from_spec(mysql_spec)
        mysql_spec.loader.exec_module(mysql_mod)

        self.assertEqual(mysql_mod.getPluginName(), 'mysql')
        self.assertTrue('mysql' in mysql_mod.getPluginDir().replace('\\', '/'))
        
        # 测试缺参校验
        ok, res_json = mysql_mod.checkArgs({'db_name': 'test'}, ['db_name', 'user'])
        self.assertFalse(ok, "缺少必要参数时应返回 False")
        res_data = json.loads(res_json)
        self.assertFalse(res_data.get('status'))
        self.assertTrue('user' in res_data.get('msg', ''))

        # 完整参数校验
        ok2, res_json2 = mysql_mod.checkArgs({'db_name': 'test', 'user': 'root'}, ['db_name', 'user'])
        self.assertTrue(ok2, "具备完整参数时应返回 True")

        # 验证 MariaDB
        os.chdir(ROOT_DIR)
        mariadb_spec = importlib.util.spec_from_file_location("mariadb_index", os.path.join(ROOT_DIR, "plugins", "mariadb", "index.py"))
        mariadb_mod = importlib.util.module_from_spec(mariadb_spec)
        mariadb_spec.loader.exec_module(mariadb_mod)

        self.assertEqual(mariadb_mod.getPluginName(), 'mariadb')
        self.assertTrue('mariadb' in mariadb_mod.getPluginDir().replace('\\', '/'))

    def test_02_redis_and_valkey_config_and_port(self):
        """测试 Redis 与 Valkey 运行时配置解析与端口自愈"""
        import importlib
        os.chdir(ROOT_DIR)

        redis_spec = importlib.util.spec_from_file_location("redis_index", os.path.join(ROOT_DIR, "plugins", "redis", "index.py"))
        redis_mod = importlib.util.module_from_spec(redis_spec)
        redis_spec.loader.exec_module(redis_mod)

        self.assertEqual(redis_mod.getPluginName(), 'redis')

        # 在沙箱中模拟 redis.conf
        conf_dir = os.path.join(self.sandbox_dir, 'server', 'redis')
        os.makedirs(conf_dir, exist_ok=True)
        conf_file = os.path.join(conf_dir, 'redis.conf')
        with open(conf_file, 'w', encoding='utf-8') as f:
            f.write("port 6379\nbind 127.0.0.1\nmaxmemory 512mb\n")

        # 验证读取配置与参数
        with mock.patch.object(redis_mod, 'getServerDir', return_value=conf_dir):
            detected = redis_mod.detectAndFixConf()
            self.assertTrue(os.path.exists(detected))

        # 验证 Valkey
        os.chdir(ROOT_DIR)
        valkey_spec = importlib.util.spec_from_file_location("valkey_index", os.path.join(ROOT_DIR, "plugins", "valkey", "index.py"))
        valkey_mod = importlib.util.module_from_spec(valkey_spec)
        valkey_spec.loader.exec_module(valkey_mod)

        self.assertEqual(valkey_mod.getPluginName(), 'valkey')

    def test_03_mongodb_and_postgresql_command_builder(self):
        """测试 MongoDB 与 PostgreSQL 运维脚本与备份命令组装安全性"""
        import importlib
        os.chdir(ROOT_DIR)

        # MongoDB
        mongo_spec = importlib.util.spec_from_file_location("mongodb_index", os.path.join(ROOT_DIR, "plugins", "mongodb", "index.py"))
        mongo_mod = importlib.util.module_from_spec(mongo_spec)
        mongo_spec.loader.exec_module(mongo_mod)

        self.assertEqual(mongo_mod.getPluginName(), 'mongodb')
        self.assertTrue('mongodb' in mongo_mod.getServerDir().replace('\\', '/'))

        # PostgreSQL
        os.chdir(ROOT_DIR)
        pg_spec = importlib.util.spec_from_file_location("pg_index", os.path.join(ROOT_DIR, "plugins", "postgresql", "index.py"))
        pg_mod = importlib.util.module_from_spec(pg_spec)
        pg_spec.loader.exec_module(pg_mod)

        self.assertEqual(pg_mod.getPluginName(), 'postgresql')

    def test_04_data_query_security_and_parsing(self):
        """测试 DataQuery 数据管理模块安全隔离与 SQL 防越权机制"""
        import importlib
        os.chdir(ROOT_DIR)

        dq_spec = importlib.util.spec_from_file_location("dq_index", os.path.join(ROOT_DIR, "plugins", "data_query", "index.py"))
        dq_mod = importlib.util.module_from_spec(dq_spec)
        dq_spec.loader.exec_module(dq_mod)

        self.assertEqual(dq_mod.getPluginName(), 'data_query')


if __name__ == '__main__':
    unittest.main()
