#!/usr/bin/env python
# coding=utf-8

import sys
import os
import unittest
import json
from unittest.mock import MagicMock, patch

# 确保路径
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(base_dir, 'web')
mysql_dir = os.path.join(base_dir, 'plugins', 'mysql')

if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if mysql_dir not in sys.path:
    sys.path.insert(0, mysql_dir)

import core.yf as yf
import index as mysql_index


class TestMysqlSetDbAccess(unittest.TestCase):

    def test_01_js_frontend_syntax_and_val_logic(self):
        """测试前端 mysql.js 中不再存在失效的 .attr('selected', true)，且正确使用 .val()"""
        js_file = os.path.join(mysql_dir, 'js', 'mysql.js')
        with open(js_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证 setDbAccess 函数中不再包含对 dataAccess 的 attr("selected", true)
        self.assertNotIn('$(\'select[name="dataAccess"]\').find("option[value=\'127.0.0.1\']").attr("selected",true)', content)
        self.assertNotIn('$(\'select[name="dataAccess"]\').find(\'option[value="%\"]\').attr("selected",true)', content)
        self.assertNotIn('$(\'select[name="dataAccess"]\').find(\'option[value="ip"]\').attr("selected",true)', content)

        # 验证已换成 val()
        self.assertIn("$sel.val('127.0.0.1')", content)
        self.assertIn("$sel.val('%')", content)
        self.assertIn("$sel.val('ip')", content)

        # 验证提交逻辑精准匹配
        self.assertIn("dataObj['dataAccess'] === 'ip'", content)
        self.assertIn("dataObj['access'] = addr;", content)

    def test_02_check_sql_exec(self):
        """测试 checkSqlExec 辅助函数的错误识别与拦截能力"""
        self.assertIsNone(mysql_index.checkSqlExec(1))
        self.assertIsNone(mysql_index.checkSqlExec(0))
        self.assertIsNone(mysql_index.checkSqlExec(None))

        # 包含 SQL 语法错误
        err_res = mysql_index.checkSqlExec("ERROR 1064: You have an error in your SQL syntax near '-test.*'")
        self.assertIsNotNone(err_res)
        data = json.loads(err_res)
        self.assertFalse(data['status'])

        # 包含 Exception 对象
        ex = Exception("Access denied for user 'root'@'localhost'")
        err_res2 = mysql_index.checkSqlExec(ex)
        self.assertIsNotNone(err_res2)
        data2 = json.loads(err_res2)
        self.assertFalse(data2['status'])
        self.assertIn("SQL执行失败", data2['msg'])

    @patch('index.pSqliteDb')
    @patch('index.pMysqlDb')
    @patch('index.getArgs')
    def test_03_set_db_access_root_to_all(self, mock_getArgs, mock_pMysqlDb, mock_pSqliteDb):
        """测试 ROOT 用户将权限修改为所有人（%）"""
        mock_getArgs.return_value = {
            'username': 'root',
            'access': '%'
        }

        # 模拟 sqlite config 返回 root 密码
        mock_config_table = MagicMock()
        mock_config_table.where.return_value.getField.return_value = 'Root@Secret_123'

        def sqlite_router(table):
            if table == 'config':
                return mock_config_table
            return MagicMock()

        mock_pSqliteDb.side_effect = sqlite_router

        # 模拟 mysql orm
        mock_pdb = MagicMock()
        # 原先有 127.0.0.1
        mock_pdb.query.return_value = [{'Host': '127.0.0.1'}]
        mock_pdb.execute.return_value = 0
        mock_pMysqlDb.return_value = mock_pdb

        res = mysql_index.setDbAccess()
        data = json.loads(res)
        self.assertTrue(data['status'])
        self.assertEqual(data['msg'], '设置成功!')

        executed_sqls = [call[0][0] for call in mock_pdb.execute.call_args_list]

        # 应该删除了旧的非 localhost 用户
        self.assertTrue(any("drop user 'root'@'127.0.0.1'" in sql for sql in executed_sqls))

        # 应该针对 % 创建了用户并授予了 *.* WITH GRANT OPTION
        self.assertTrue(any("CREATE USER IF NOT EXISTS `root`@`%`" in sql for sql in executed_sqls))
        self.assertTrue(any("GRANT ALL PRIVILEGES ON *.* TO `root`@`%` WITH GRANT OPTION" in sql for sql in executed_sqls))

    @patch('index.pSqliteDb')
    @patch('index.pMysqlDb')
    @patch('index.getArgs')
    def test_04_set_db_access_normal_user_hyphen_dbname(self, mock_getArgs, mock_pMysqlDb, mock_pSqliteDb):
        """测试包含中划线数据库名的普通用户权限修改，验证反引号包裹与只读属性保护"""
        mock_getArgs.return_value = {
            'username': 'app-user',
            'access': '192.168.1.100,192.168.1.200'
        }

        mock_databases_table = MagicMock()
        # 原数据库读写状态为只读 'r'
        mock_databases_table.where.return_value.field.return_value.find.return_value = {
            'name': 'my-cool-db',
            'username': 'app-user',
            'password': 'Pass\'Word\\123',
            'accept': '127.0.0.1',
            'rw': 'r'
        }

        mock_pSqliteDb.return_value = mock_databases_table

        mock_pdb = MagicMock()
        mock_pdb.query.return_value = [{'Host': '127.0.0.1'}]
        mock_pdb.execute.return_value = 0
        mock_pMysqlDb.return_value = mock_pdb

        res = mysql_index.setDbAccess()
        data = json.loads(res)
        self.assertTrue(data['status'])

        executed_sqls = [call[0][0] for call in mock_pdb.execute.call_args_list]

        # 验证数据库名必须使用反引号包裹 `my-cool-db`.*
        self.assertTrue(any("`my-cool-db`.*" in sql for sql in executed_sqls), "未找到反引号包裹的数据库名授权语句")

        # 验证只读模式使用 GRANT SELECT
        self.assertTrue(any("GRANT SELECT ON `my-cool-db`.* TO `app-user`@`192.168.1.100`" in sql for sql in executed_sqls))
        self.assertTrue(any("GRANT SELECT ON `my-cool-db`.* TO `app-user`@`192.168.1.200`" in sql for sql in executed_sqls))

        # 验证保留 localhost 用户权限
        self.assertTrue(any("GRANT SELECT ON `my-cool-db`.* TO `app-user`@`localhost`" in sql for sql in executed_sqls))

        # 验证 sqlite 更新 accept 字段和 rw 字段
        mock_databases_table.where.return_value.setField.assert_any_call('accept', '192.168.1.100,192.168.1.200')
        mock_databases_table.where.return_value.setField.assert_any_call('rw', 'r')

    @patch('index.pSqliteDb')
    @patch('index.pMysqlDb')
    @patch('index.getArgs')
    def test_05_set_db_access_sql_error_propagation(self, mock_getArgs, mock_pMysqlDb, mock_pSqliteDb):
        """测试当底层 SQL 报错时（返回异常对象或抛出异常），不会假装设置成功，而是正确向用户报错"""
        mock_getArgs.return_value = {
            'username': 'test_user',
            'access': '%'
        }

        mock_databases_table = MagicMock()
        mock_databases_table.where.return_value.field.return_value.find.return_value = {
            'name': 'test_db',
            'username': 'test_user',
            'password': '123',
            'accept': '127.0.0.1',
            'rw': 'rw'
        }
        mock_pSqliteDb.return_value = mock_databases_table

        # 场景 1：底层 execute 返回异常对象（真实的 ORM 行为）
        mock_pdb = MagicMock()
        mock_pdb.query.return_value = []
        mock_pdb.execute.return_value = Exception("Access denied for user 'root'@'localhost' to database 'test_db'")
        mock_pMysqlDb.return_value = mock_pdb

        res1 = mysql_index.setDbAccess()
        data1 = json.loads(res1)
        self.assertFalse(data1['status'], "底层执行失败时不应返回 status=True")
        self.assertIn("SQL执行失败", data1['msg'])

        # 场景 2：底层抛出运行时异常
        mock_pdb.execute.side_effect = RuntimeError("Connection lost")
        res2 = mysql_index.setDbAccess()
        data2 = json.loads(res2)
        self.assertFalse(data2['status'])
        self.assertIn("设置数据库权限异常", data2['msg'])

    def test_06_orm_execute_and_query_with_percent_symbol(self):
        """测试 web.core.orm.ORM 在 SQL 含有 % 通配符时不会因空参数抛出 not enough arguments for format string"""
        try:
            import core.orm as orm_module
            from pymysql.cursors import Cursor
        except ImportError:
            return

        # 1. 验证真实 PyMySQL Cursor 行为：空元组 () 会导致 % 字符串格式化崩溃，而 args=None 则安全通过
        mock_conn = MagicMock()
        mock_conn.encoding = 'utf-8'
        real_cursor = Cursor(mock_conn)
        sql_with_percent = "GRANT ALL PRIVILEGES ON `test`.* TO `test`@`%`"

        # args=None 安全通过
        formatted_sql = real_cursor.mogrify(sql_with_percent, None)
        self.assertEqual(formatted_sql, sql_with_percent)

        # args=() 会触发 TypeError，验证缺陷原型的重现
        with self.assertRaises(TypeError):
            real_cursor.mogrify(sql_with_percent, ())

        # 2. 验证修复后的 ORM.execute 与 ORM.query 对参数的正确处理
        o = orm_module.ORM()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{'Host': '%'}]
        mock_conn2 = MagicMock()

        o._ORM__DB_CONN = mock_conn2
        o._ORM__DB_CUR = mock_cursor

        with patch.object(o, '_ORM__Conn', return_value=True), \
             patch.object(o, '_ORM__Close', return_value=None):

            # (1) 默认 params=None 时，调用 mock_cursor.execute(sql)，不带第二个参数
            o.execute(sql_with_percent)
            mock_cursor.execute.assert_called_once_with(sql_with_percent)

            # (2) 显式 params=() 时，也不传第二个参数
            mock_cursor.execute.reset_mock()
            o.execute(sql_with_percent, ())
            mock_cursor.execute.assert_called_once_with(sql_with_percent)

            # (3) 显式 params=[] 时，同样不传第二个参数
            mock_cursor.execute.reset_mock()
            o.execute(sql_with_percent, [])
            mock_cursor.execute.assert_called_once_with(sql_with_percent)

            # (4) query 含有 % 也绝不传空参数
            mock_cursor.execute.reset_mock()
            res = o.query("SELECT * FROM mysql.user WHERE Host='%'")
            mock_cursor.execute.assert_called_once_with("SELECT * FROM mysql.user WHERE Host='%'")
            self.assertEqual(res, [{'Host': '%'}])

            # (5) 当传入非空有效参数时，正常传递给游标进行参数化
            mock_cursor.execute.reset_mock()
            o.execute("SELECT * FROM mysql.user WHERE User=%s", ('test',))
            mock_cursor.execute.assert_called_once_with("SELECT * FROM mysql.user WHERE User=%s", ('test',))

    @patch('index.pSqliteDb')
    @patch('index.pMysqlDb')
    @patch('index.getArgs')
    def test_07_set_db_master_access(self, mock_getArgs, mock_pMysqlDb, mock_pSqliteDb):
        """测试主从复制用户权限设置与加固"""
        mock_getArgs.return_value = {
            'username': 'repl_user',
            'access': '%'
        }

        mock_master_table = MagicMock()
        mock_master_table.where.return_value.find.return_value = {
            'username': 'repl_user',
            'password': 'ReplPassword123!',
            'accept': '127.0.0.1'
        }
        mock_pSqliteDb.return_value = mock_master_table

        mock_pdb = MagicMock()
        mock_pdb.query.return_value = [{'Host': '127.0.0.1'}]
        mock_pdb.execute.return_value = 0
        mock_pMysqlDb.return_value = mock_pdb

        res = mysql_index.setDbMasterAccess()
        data = json.loads(res)
        self.assertTrue(data['status'])
        self.assertEqual(data['msg'], '设置成功!')

        executed_sqls = [call[0][0] for call in mock_pdb.execute.call_args_list]
        self.assertTrue(any("drop user 'repl_user'@'127.0.0.1'" in sql for sql in executed_sqls))
        self.assertTrue(any("grant all privileges on *.* to `repl_user`@`%` with grant option" in sql for sql in executed_sqls))

    def test_08_dblist_access_icon_rendering(self):
        """测试前端 mysql.js 中 dbList 正确渲染多人绿色权限图标"""
        js_file = os.path.join(mysql_dir, 'js', 'mysql.js')
        with open(js_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证包含 accept 检查条件
        self.assertIn("accept !== '127.0.0.1' && accept !== 'localhost'", content)

        # 验证包含双 glyphicon-user 错落层叠组合
        self.assertIn('<span class="glyphicon glyphicon-user" style="font-size:11px; opacity:0.8; margin-right:-6px;"></span>', content)
        self.assertIn('<span class="glyphicon glyphicon-user" style="font-size:12px;"></span>', content)

        # 验证包含绿色配色与交互属性
        self.assertIn("color:#20a53a", content)
        self.assertIn("setDbAccess", content)
        self.assertIn("pt('访问权限')", content)
        self.assertIn("pt('所有人')", content)

    def test_09_menu_and_manage_port_config(self):
        """测试 MySQL 菜单顺序（服务后面紧跟管理列表且无独立端口菜单）以及管理列表右上方端口配置"""
        # 1. 验证 index.html 菜单结构
        html_file = os.path.join(mysql_dir, 'index.html')
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # 不再存在独立端口菜单项
        self.assertNotIn('<p onclick="myPort();">端口</p>', html_content)

        # 管理列表上移到服务正下方
        pos_service = html_content.find("mySqlServiceWrapper")
        pos_dblist = html_content.find('onclick="dbList()"')
        pos_config = html_content.find('pluginConfig')

        self.assertNotEqual(pos_service, -1)
        self.assertNotEqual(pos_dblist, -1)
        self.assertNotEqual(pos_config, -1)
        self.assertTrue(pos_service < pos_dblist < pos_config, "管理列表菜单必须置于服务菜单正下方且在配置文件上方")

        # 2. 验证 mysql.js 包含端口配置控件与 changeDbPort 处理函数
        js_file = os.path.join(mysql_dir, 'js', 'mysql.js')
        with open(js_file, 'r', encoding='utf-8') as f:
            js_content = f.read()

        self.assertIn('id="db_port_val"', js_content)
        self.assertIn('id="btn_save_db_port"', js_content)
        self.assertIn('changeDbPort()', js_content)
        self.assertIn('function changeDbPort()', js_content)
        self.assertIn("set_my_port", js_content)
        self.assertIn("db_port_val", js_content)

        # 3. 验证 index.py getDbList 返回 info['port']
        py_file = os.path.join(mysql_dir, 'index.py')
        with open(py_file, 'r', encoding='utf-8') as f:
            py_content = f.read()
        self.assertIn("info['port'] = getDbPort()", py_content)


if __name__ == '__main__':
    unittest.main()

