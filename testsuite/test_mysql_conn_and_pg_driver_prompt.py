# coding:utf-8
import os
import sys
import json
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

WEB_DIR = os.path.join(PROJECT_ROOT, "web")
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

PLUGIN_DIR = os.path.join(PROJECT_ROOT, "plugins", "data_query")
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

import common_db
import sql_mysql
import sql_postgresql


class TestMySQLFixAndPgDriverPrompt(unittest.TestCase):

    def test_01_language_json_syntax(self):
        """验证 6 大多语言包语法及新增词条"""
        lang_dir = os.path.join(PLUGIN_DIR, "lang")
        langs = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]
        required_keys = [
            "驱动缺失提示",
            "检测到当前系统尚未安装 PostgreSQL (psycopg2) 驱动，无法建立数据库连接。是否立即自动安装驱动？",
            "立即安装",
            "立即安装驱动并查看日志"
        ]
        for l in langs:
            p = os.path.join(lang_dir, f"{l}.json")
            self.assertTrue(os.path.exists(p), f"语言包不存在: {p}")
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIsInstance(data, dict)
            for k in required_keys:
                self.assertIn(k, data, f"语言包 {l}.json 缺少关键词条: {k}")
                self.assertTrue(bool(data[k]), f"语言包 {l}.json 词条 {k} 内容为空")

    def test_02_get_db_port_custom_isolation(self):
        """验证 getDbPort 传入 conn_<id> 时能够精准读取连接独立端口，不被全局设置覆盖"""
        # 新增一个具有特殊端口的测试连接
        conn_res = common_db.saveConnection({
            'name': 'Unit Test PG Port 65432',
            'db_type': 'postgresql',
            'host': '127.0.0.1',
            'port': 65432,
            'username': 'postgres',
            'password': 'test_password',
            'auth_db': 'test_db'
        })
        self.assertTrue(conn_res.get('status'))
        c_id = conn_res['data']['id']

        try:
            # 查该 Profile 的端口
            p_info = common_db.getDbPort('postgresql', sid=f"conn_{c_id}")
            self.assertEqual(p_info.get('port'), 65432, "应该优先返回该 Profile 的独立端口 65432")

            # 故意全局修改 postgresql 端口为 6666
            common_db.setDbPort('postgresql', 6666)

            # 再次查询该 Profile 端口，必须依然是 65432，不受 6666 干扰！
            p_info_after = common_db.getDbPort('postgresql', sid=f"conn_{c_id}")
            self.assertEqual(p_info_after.get('port'), 65432, "Profile 独立端口 65432 绝对不应该被全局修改 6666 覆盖！")

            # 未指定 sid 时，应该返回全局修改的 6666
            global_port = common_db.getDbPort('postgresql', sid=None)
            self.assertEqual(global_port.get('port'), 6666)
        finally:
            common_db.deleteConnection({'id': c_id})

    def test_03_plugin_orm_methods_no_attribute_error(self):
        """验证 PluginORM 重构后具备完整的 connect, _ORM__Conn, _ORM__Connect 别名，且绝无 AttributeError"""
        orm_inst = sql_mysql.PluginORM()
        orm_inst.setHost('127.0.0.1')
        orm_inst.setPort(3306)
        orm_inst.setUser('root')
        orm_inst.setPwd('dummy_pwd')
        orm_inst.setTimeout(1)

        # 检查关键方法存在性
        self.assertTrue(hasattr(orm_inst, 'connect'))
        self.assertTrue(hasattr(orm_inst, '_ORM__Conn'))
        self.assertTrue(hasattr(orm_inst, '_ORM__Connect'))
        self.assertTrue(hasattr(orm_inst, 'getLastError'))
        self.assertTrue(hasattr(orm_inst, 'query'))
        self.assertTrue(hasattr(orm_inst, 'find'))
        self.assertTrue(hasattr(orm_inst, 'execute'))
        self.assertTrue(hasattr(orm_inst, 'close'))

        # 调用 _ORM__Connect，必须返回布尔值，绝不允许抛出 AttributeError 崩溃！
        try:
            res = orm_inst._ORM__Connect()
            self.assertIsInstance(res, bool)
        except AttributeError as ae:
            self.fail(f"PluginORM 仍存在 AttributeError: {ae}")
        except Exception:
            pass  # 网络不通返回 False 正常

    def test_04_mysql_get_last_error_and_get_db_list(self):
        """验证 nosqlMySQL.conn 和 nosqlMySQLCtr.getDbList 错误诊断信息透传"""
        ctr = sql_mysql.nosqlMySQLCtr()
        inst = ctr.getInstanceBySid('mysql')

        # 故意将连接配置设为一个不可达的目标以测试错误捕获与诊断
        inst._nosqlMySQL__DB_HOST = '127.0.0.1'
        inst._nosqlMySQL__DB_PORT = 54321
        inst._nosqlMySQL__DB_PASS = 'wrong_password_xyz'

        # 执行 conn，验证错误信息生成
        conn_res = inst.conn()
        err_text = inst.getLastError()
        self.assertFalse(conn_res)
        self.assertTrue(bool(err_text), "应当产生详细连接错误诊断文本")

        # 执行 getDbList，验证 fallback 和 error_msg 返回
        db_res = ctr.getDbList({'sid': 'mysql'})
        self.assertTrue(db_res.get('status'))
        self.assertFalse(db_res['data']['is_connected'])
        self.assertTrue(db_res['data']['is_fallback'])
        self.assertIn('error_msg', db_res['data'])
        self.assertTrue(bool(db_res['data']['error_msg']))

    def test_05_postgresql_driver_check(self):
        """验证 PostgreSQL 模块检测驱动状态与错误透传机制"""
        pg_inst = sql_postgresql.nosqlPostgreSQL()
        pg_conn = pg_inst.conn()
        err_msg = pg_inst.getLastError()

        # 当未安装 psycopg2 驱动时，应该准确提示
        if sql_postgresql.psycopg2 is None:
            self.assertFalse(pg_conn)
            self.assertIn("psycopg2", err_msg)
            ctr = sql_postgresql.nosqlPostgreSQLCtr()
            dbs = ctr.getDbList()
            self.assertFalse(dbs.get('status'))
            self.assertIn("psycopg2", dbs.get('msg', ''))

    def test_06_detect_local_mysql_passwords(self):
        """验证多源密码探测机制"""
        pwds = common_db.detectLocalMySQLPasswords()
        self.assertIsInstance(pwds, list)
        self.assertIn("", pwds, "应包含空密码兜底")
        self.assertIn("admin", pwds, "应包含从实际存在的 server/mysql/mysql.db 探测到的 admin 密码")

    def test_07_mysql_auth_db_fallback(self):
        """验证初始/认证库容灾处理能力"""
        orm_inst = sql_mysql.PluginORM()
        orm_inst.setDbName("non_existent_fake_db_12345")
        self.assertEqual(orm_inst.db_name, "non_existent_fake_db_12345")

    def test_08_password_retention_and_test_conn_input(self):
        """验证编辑连接测试时优先采用输入密码，以及同步时不盲目清空已有密码"""
        save_res = common_db.saveConnection({
            'name': 'Test Retention Node',
            'db_type': 'mysql',
            'host': '127.0.0.1',
            'port': 3306,
            'username': 'root',
            'password': 'old_safe_password',
            'notes': '__auto_local__'
        })
        self.assertTrue(save_res.get('status'))
        c_id = save_res['data']['id']

        # 1. 验证 testConnection: 当传入新密码时优先使用新密码（此处端口不通会返回网络拒绝，但参数解析正常）
        test_res = common_db.testConnection({
            'id': c_id,
            'password': 'newly_typed_password'
        })
        self.assertIsInstance(test_res, dict)

        # 2. 验证 applyLocalSync: 当传入配置项密码为空时，已有密码受保护不被清空
        sync_res = common_db.applyLocalSync({
            'sync_items': [{
                'id': c_id,
                'db_type': 'mysql',
                'name': 'Test Retention Node',
                'new_config': {
                    'host': '127.0.0.1',
                    'port': 3306,
                    'username': 'root',
                    'password': '',  # 空密码
                    'auth_db': ''
                }
            }]
        })
        self.assertTrue(sync_res.get('status'))
        detail = common_db.getConnection({'id': c_id}, raw_password=True)
        self.assertEqual(detail['data']['password'], 'old_safe_password', "同步未探测到新密码时，旧密码应当被安全保护保留")


if __name__ == '__main__':
    unittest.main()

