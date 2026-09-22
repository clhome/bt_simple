# coding:utf-8
import sys
import os
import unittest
import json
import sqlite3
import tempfile

# 设置项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
web_dir = os.path.join(project_root, 'web')
plugins_dir = os.path.join(project_root, 'plugins')
data_query_dir = os.path.join(plugins_dir, 'data_query')

for p in [web_dir, plugins_dir, data_query_dir, project_root]:
    if p not in sys.path:
        sys.path.insert(0, p)

import core.yf as yf

# 进程级隔离：把面板 SQLite / 服务目录重定向到系统临时区。
# 本机 `F:` 盘上 sqlite3 不只是 connect 慢，**close() 单次也要 30~60s**。
# `web/core/db.py` 在 atexit 里注册了 `_close_all_connections`，而本用例会开出
# 6 个连接（1 个面板库 + 5 个 `<serverDir>/*.db`）—— 光是进程退出就要 ~270s。
# 实测：用例本体 `Ran 7 tests in 0.508s`，进程却要 184~296s，99.8% 在解释器退出。
# 见 testsuite.md §5.7 / §5.9。
from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('pg_driver_mysql')

import common_db  # noqa: E402


class TestPgDriverAndMysqlDbs(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 隔离已在模块级完成（见上方注释）。这里留个断言防止有人删掉那行。
        assert _PANEL_TMP and _SERVER_TMP, '模块级隔离未生效'

    def test_01_pg_driver_interfaces(self):
        """测试 PostgreSQL 驱动检查与日志接口"""
        import sql_postgresql
        # 1. check_driver
        res = sql_postgresql.check_driver()
        self.assertTrue(isinstance(res, dict))
        self.assertTrue(res.get('status', False))
        self.assertIn('installed', res.get('data', {}))

        # 2. get_install_driver_log
        res_log = sql_postgresql.get_install_driver_log()
        self.assertTrue(isinstance(res_log, dict))
        self.assertTrue(res_log.get('status', False))
        self.assertIn('log', res_log.get('data', {}))

        # 3. 类实例上的挂载方法测试
        ctr = sql_postgresql.nosqlPostgreSQLCtr()
        self.assertTrue(hasattr(ctr, 'check_driver'))
        self.assertTrue(hasattr(ctr, 'install_pg_driver'))
        self.assertTrue(hasattr(ctr, 'get_install_driver_log'))
        self.assertTrue(ctr.check_driver().get('status', False))

    def test_02_pg_get_db_list_driver_missing_flag(self):
        """测试 PostgreSQL 驱动未安装时的友好错误和 driver_missing 标志"""
        import sql_postgresql
        res = sql_postgresql.get_db_list({'sid': 'pgsql'})
        self.assertTrue(isinstance(res, dict))
        # 若驱动未安装，必须有 driver_missing 标志或 psycopg2 提示
        if not res.get('status'):
            msg = res.get('msg', '')
            data = res.get('data', {}) or {}
            is_driver_err = 'psycopg2' in msg or data.get('driver_missing') is True
            self.assertTrue(is_driver_err or '未连接' in msg or '无法连接' in msg)

    def test_03_mysql_server_list_always_available(self):
        """测试 MySQL 服务列表免物理依赖、始终提供 127.0.0.1"""
        import sql_mysql
        res = sql_mysql.get_server_list()
        self.assertTrue(res.get('status', False))
        servers = res.get('data', [])
        self.assertTrue(len(servers) > 0)
        self.assertEqual(servers[0].get('group'), 'local')
        self.assertTrue('127.0.0.1' in servers[0].get('name', '') or servers[0].get('val') == 'mysql')

    def test_04_mysql_fallback_databases_not_empty(self):
        """测试 MySQL 数据库离线探测：无论是否有数据库均返回非空列表（包含 mysql 兜底）"""
        import sql_mysql
        mysql_obj = sql_mysql.nosqlMySQL()
        dbs = mysql_obj._get_fallback_databases('mysql')
        self.assertTrue(isinstance(dbs, list))
        self.assertTrue(len(dbs) > 0)
        self.assertIn('mysql', dbs)

    def test_05_mysql_get_db_list_offline_fallback(self):
        """测试 MySQL 未直连服务时，依然返回 status: True 并在 list 中展示全部可用库供自选"""
        import sql_mysql
        res = sql_mysql.get_db_list({'sid': 'mysql'})
        self.assertTrue(res.get('status', False))
        data = res.get('data', {})
        self.assertIn('list', data)
        self.assertTrue(len(data['list']) > 0)
        self.assertIn('is_connected', data)

    def test_06_mysql_get_table_list_error_message(self):
        """测试 MySQL 在未连接或错误库名时友好返回错误信息"""
        import sql_mysql
        # 1. 非法表名防注入
        res_inj = sql_mysql.get_table_list({'sid': 'mysql', 'db': "test' OR '1'='1"})
        self.assertFalse(res_inj.get('status'))
        self.assertIn('非法', res_inj.get('msg'))

        # 2. 正常库名但服务未连接时的友好提示
        res_conn = sql_mysql.get_table_list({'sid': 'mysql', 'db': 'mysql'})
        self.assertTrue(isinstance(res_conn, dict))

    def test_07_app_js_syntax_and_declarations(self):
        """测试 app.js 核心方法与翻译兜底声明"""
        app_js_path = os.path.join(data_query_dir, 'static', 'js', 'app.js')
        self.assertTrue(os.path.exists(app_js_path))
        with open(app_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 1. 检查 pt 函数声明提升
        self.assertIn('function pt(str)', content)
        self.assertIn('window.pt = pt;', content)

        # 2. 检查 PostgreSQL 一键安装与日志弹窗函数
        self.assertIn('function showInstallPgDriverDialog()', content)
        self.assertIn('btn_install_pg_driver', content)
        self.assertIn('get_install_driver_log', content)

        # 3. 检查 MySQL 离线数据库下拉保留与自选连接交互
        self.assertIn('未连接到 MySQL 服务，已列出可用数据库，请自主选择连接', content)
        self.assertIn('mysqlGetTableList(1);', content)


if __name__ == '__main__':
    unittest.main()
