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
mariadb_dir = os.path.join(base_dir, 'plugins', 'mariadb')

if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if mariadb_dir not in sys.path:
    sys.path.insert(0, mariadb_dir)

import core.yf as yf
import index as mariadb_index


class TestMariaDbSetDbAccess(unittest.TestCase):

    def test_01_js_frontend_syntax_and_val_logic(self):
        """测试前端 mariadb.js 中无字面量泄漏，不再存在失效的 .attr('selected', true)，且正确使用 .val()"""
        js_file = os.path.join(mariadb_dir, 'js', 'mariadb.js')
        with open(js_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证双引号内单引号字面量泄漏已彻底消除
        self.assertNotIn("'+ pt(", content)
        self.assertNotIn("'+pt(", content)
        self.assertNotIn("pt(') + '", content)

        # 验证 setDbAccess 函数中不再包含对 dataAccess 的 attr("selected", true)
        self.assertNotIn('$(\'select[name="dataAccess"]\').find("option[value=\'127.0.0.1\']").attr("selected",true)', content)
        self.assertNotIn('$(\'select[name="dataAccess"]\').find(\'option[value="%\"]\').attr("selected",true)', content)
        self.assertNotIn('$(\'select[name="dataAccess"]\').find(\'option[value="ip"]\').attr("selected",true)', content)

        # 验证已换成 val() 回显
        self.assertIn("$sel.val('127.0.0.1')", content)
        self.assertIn("$sel.val('%')", content)
        self.assertIn("$sel.val('ip')", content)

        # 验证提交逻辑精准匹配
        self.assertIn("dataObj['dataAccess'] === 'ip'", content)
        self.assertIn("dataObj['access'] = addr;", content)

    def test_02_check_sql_exec(self):
        """测试 checkSqlExec 辅助函数的错误识别与拦截能力"""
        self.assertIsNone(mariadb_index.checkSqlExec(1))
        self.assertIsNone(mariadb_index.checkSqlExec(0))
        self.assertIsNone(mariadb_index.checkSqlExec(None))

        # 包含 SQL 语法错误
        err_res = mariadb_index.checkSqlExec("ERROR 1064: You have an error in your SQL syntax near '-test.*'")
        self.assertIsNotNone(err_res)
        data = json.loads(err_res)
        self.assertFalse(data['status'])

        # 包含 Exception 对象
        ex = Exception("Access denied for user 'root'@'localhost'")
        err_res2 = mariadb_index.checkSqlExec(ex)
        self.assertIsNotNone(err_res2)
        data2 = json.loads(err_res2)
        self.assertFalse(data2['status'])
        self.assertIn("SQL执行失败", data2['msg'])

    @patch('index.pMysqlDb')
    def test_03_create_user_quotes_and_safe_pwd(self, mock_pMysqlDb):
        """测试 __createUser 对中划线库名的反引号包裹、密码转义与 IF NOT EXISTS"""
        mock_pdb = MagicMock()
        mock_pdb.execute.return_value = 0
        mock_pMysqlDb.return_value = mock_pdb

        create_user_fn = getattr(mariadb_index, '__createUser')
        create_user_fn('my-app-db', 'app-user', 'Pass\'Word\\123', '192.168.1.50')

        executed_sqls = [call[0][0] for call in mock_pdb.execute.call_args_list]

        # 必须包裹反引号 `my-app-db`.*
        self.assertTrue(any("`my-app-db`.*" in sql for sql in executed_sqls), "未找到反引号包裹的库名授权语句")
        # 必须转义密码
        self.assertTrue(any("Pass\\'Word\\\\123" in sql for sql in executed_sqls), "密码未正确转义")
        # 必须使用 CREATE USER IF NOT EXISTS
        self.assertTrue(any("CREATE USER IF NOT EXISTS `app-user`@`localhost`" in sql for sql in executed_sqls))
        self.assertTrue(any("CREATE USER IF NOT EXISTS `app-user`@`192.168.1.50`" in sql for sql in executed_sqls))

    @patch('index.pSqliteDb')
    @patch('index.pMysqlDb')
    @patch('index.getArgs')
    def test_04_set_db_access_root_to_all(self, mock_getArgs, mock_pMysqlDb, mock_pSqliteDb):
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
        mock_pdb.query.return_value = [{'Host': '127.0.0.1'}]
        mock_pdb.execute.return_value = 0
        mock_pMysqlDb.return_value = mock_pdb

        res = mariadb_index.setDbAccess()
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
    def test_05_set_db_access_normal_user_hyphen_dbname(self, mock_getArgs, mock_pMysqlDb, mock_pSqliteDb):
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

        res = mariadb_index.setDbAccess()
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
    def test_06_set_db_access_sql_error_propagation(self, mock_getArgs, mock_pMysqlDb, mock_pSqliteDb):
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

        res1 = mariadb_index.setDbAccess()
        data1 = json.loads(res1)
        self.assertFalse(data1['status'], "底层执行失败时不应返回 status=True")
        self.assertIn("SQL执行失败", data1['msg'])

        # 场景 2：底层抛出运行时异常
        mock_pdb.execute.side_effect = RuntimeError("Connection lost")
        res2 = mariadb_index.setDbAccess()
        data2 = json.loads(res2)
        self.assertFalse(data2['status'])
        self.assertIn("设置数据库权限异常", data2['msg'])

    @patch('index.pSqliteDb')
    @patch('index.pMysqlDb')
    @patch('index.getArgs')
    def test_07_set_db_master_access(self, mock_getArgs, mock_pMysqlDb, mock_pSqliteDb):
        """测试主从复制用户权限设置与加固"""
        mock_getArgs.return_value = {
            'username': 'repl_user',
            'access': '192.168.1.188'
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

        res = mariadb_index.setDbMasterAccess()
        data = json.loads(res)
        self.assertTrue(data['status'])
        self.assertEqual(data['msg'], '设置成功!')

        executed_sqls = [call[0][0] for call in mock_pdb.execute.call_args_list]
        self.assertTrue(any("drop user 'repl_user'@'127.0.0.1'" in sql for sql in executed_sqls))
        self.assertTrue(any("grant all privileges on *.* to `repl_user`@`192.168.1.188` with grant option" in sql for sql in executed_sqls))

    def test_08_dblist_access_icon_rendering(self):
        """测试前端 mariadb.js 中 dbList 正确渲染多人绿色权限图标"""
        js_file = os.path.join(mariadb_dir, 'js', 'mariadb.js')
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
        """测试 MariaDB 菜单顺序（服务后面紧跟管理列表且无独立端口菜单）以及管理列表右上方端口配置"""
        # 1. 验证 index.html 菜单结构
        html_file = os.path.join(mariadb_dir, 'index.html')
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # 不再存在独立端口菜单项
        self.assertNotIn('<p onclick="myPort();">端口</p>', html_content)

        # 管理列表上移到服务正下方
        pos_service = html_content.find("pluginService")
        pos_dblist = html_content.find('onclick="dbList()"')
        pos_config = html_content.find('pluginConfig')

        self.assertNotEqual(pos_service, -1)
        self.assertNotEqual(pos_dblist, -1)
        self.assertNotEqual(pos_config, -1)
        self.assertTrue(pos_service < pos_dblist < pos_config, "管理列表菜单必须置于服务菜单正下方且在配置文件上方")

        # 2. 验证 mariadb.js 包含端口配置控件与 changeDbPort 处理函数
        js_file = os.path.join(mariadb_dir, 'js', 'mariadb.js')
        with open(js_file, 'r', encoding='utf-8') as f:
            js_content = f.read()

        self.assertIn('id="db_port_val"', js_content)
        self.assertIn('id="btn_save_db_port"', js_content)
        self.assertIn('changeDbPort()', js_content)
        self.assertIn('function changeDbPort()', js_content)
        self.assertIn("set_my_port", js_content)
        self.assertIn("db_port_val", js_content)

        # 3. 验证 index.py getDbList 返回 info['port']
        py_file = os.path.join(mariadb_dir, 'index.py')
        with open(py_file, 'r', encoding='utf-8') as f:
            py_content = f.read()
        self.assertIn("info['port'] = getDbPort()", py_content)


if __name__ == '__main__':
    unittest.main()
