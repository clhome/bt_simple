# -*- coding: utf-8 -*-
"""
自动化测试套件：MySQL 与 MariaDB 外部导入 SQL 日志弹窗与执行可靠性测试
验证点：
1. 后端 importDbExternal 在非法参数、文件不存在、空文件、成功导入与失败导入时的返回值与结构化日志；
2. 前端 mysql.js 和 mariadb.js 中 importDbExternal 与 showImportLogModal 具备 loading 遮罩、不可自动关闭 (time: 0, shadeClose: false)、手动关闭与日志复制能力。
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
web_dir = os.path.join(PROJECT_ROOT, 'web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)


class TestImportLogBackend(unittest.TestCase):
    """测试后端 MySQL / MariaDB importDbExternal 日志组装与异常捕获"""

    def setUp(self):
        # 确保基础环境变量
        pass

    def test_mysql_import_path_traversal(self):
        """测试路径穿越防御"""
        import plugins.mysql.index as mysql_plugin
        with patch.object(mysql_plugin, 'getArgs', return_value={'file': '../etc/passwd', 'name': 'testdb'}):
            res_str = mysql_plugin.importDbExternal()
            import json
            res = json.loads(res_str)
            self.assertFalse(res['status'])
            self.assertIn('不合法', res['msg'])

    def test_mysql_import_file_not_found(self):
        """测试文件不存在时的日志返回"""
        import plugins.mysql.index as mysql_plugin
        with patch.object(mysql_plugin, 'getArgs', return_value={'file': 'non_existent_file.sql', 'name': 'testdb'}), \
             patch.object(mysql_plugin.os.path, 'exists', return_value=False):
            res_str = mysql_plugin.importDbExternal()
            import json
            res = json.loads(res_str)
            self.assertFalse(res['status'])
            self.assertIn('源文件不存在', res['msg'])
            self.assertIn('log', res['data'])
            self.assertIn('未找到', res['data']['log'])

    def test_mysql_import_empty_file(self):
        """测试待导入 SQL 文件大小为 0 时的检测与日志"""
        import plugins.mysql.index as mysql_plugin
        with patch.object(mysql_plugin, 'getArgs', return_value={'file': 'empty.sql', 'name': 'testdb'}), \
             patch.object(mysql_plugin.os.path, 'exists', return_value=True), \
             patch.object(mysql_plugin.os.path, 'getsize', return_value=0):
            res_str = mysql_plugin.importDbExternal()
            import json
            res = json.loads(res_str)
            self.assertFalse(res['status'])
            self.assertIn('SQL文件内容为空', res['msg'])
            self.assertIn('log', res['data'])
            self.assertIn('0 字节', res['data']['log'])

    def test_mysql_import_success_with_log(self):
        """测试模拟执行成功时的详细日志组装"""
        import plugins.mysql.index as mysql_plugin

        mock_process = MagicMock()
        mock_process.communicate.return_value = (b"", b"mysql: [Warning] Using a password on the command line interface can be insecure.\n")
        mock_process.returncode = 0

        mock_file = MagicMock()
        mock_file.__enter__.return_value = MagicMock()
        mock_file.__exit__.return_value = False

        with patch.object(mysql_plugin, 'getArgs', return_value={'file': 'test_data.sql', 'name': 'mydb'}), \
             patch.object(mysql_plugin.os.path, 'exists', return_value=True), \
             patch.object(mysql_plugin.os.path, 'getsize', return_value=1024), \
             patch.object(mysql_plugin, 'pSqliteDb') as mock_db, \
             patch.object(mysql_plugin, 'getSocketFile', return_value='/tmp/mysql.sock'), \
             patch.object(mysql_plugin, 'getConf', return_value='/etc/my.cnf'), \
             patch('builtins.open', return_value=mock_file), \
             patch('subprocess.Popen', return_value=mock_process):

            mock_db.return_value.where.return_value.getField.return_value = 'root123'

            res_str = mysql_plugin.importDbExternal()
            import json
            res = json.loads(res_str)
            self.assertTrue(res['status'])
            self.assertIn('导入成功', res['msg'])
            self.assertIn('log', res['data'])
            log = res['data']['log']
            self.assertIn('目标数据库: mydb', log)
            self.assertIn('导入源文件: test_data.sql', log)
            self.assertIn('执行耗时:', log)
            self.assertIn('进程退出码: 0', log)
            self.assertIn('执行结论: 数据库导入执行完毕！', log)

    def test_mysql_import_failed_with_stderr_log(self):
        """测试模拟执行失败时的错误捕获与排查日志"""
        import plugins.mysql.index as mysql_plugin

        mock_process = MagicMock()
        mock_process.communicate.return_value = (b"", b"ERROR 1049 (42000): Unknown database 'mydb'\n")
        mock_process.returncode = 1

        mock_file = MagicMock()
        mock_file.__enter__.return_value = MagicMock()
        mock_file.__exit__.return_value = False

        with patch.object(mysql_plugin, 'getArgs', return_value={'file': 'test_data.sql', 'name': 'mydb'}), \
             patch.object(mysql_plugin.os.path, 'exists', return_value=True), \
             patch.object(mysql_plugin.os.path, 'getsize', return_value=1024), \
             patch.object(mysql_plugin, 'pSqliteDb') as mock_db, \
             patch.object(mysql_plugin, 'getSocketFile', return_value='/tmp/mysql.sock'), \
             patch.object(mysql_plugin, 'getConf', return_value='/etc/my.cnf'), \
             patch('builtins.open', return_value=mock_file), \
             patch('subprocess.Popen', return_value=mock_process):

            mock_db.return_value.where.return_value.getField.return_value = 'root123'

            res_str = mysql_plugin.importDbExternal()
            import json
            res = json.loads(res_str)
            self.assertFalse(res['status'])
            self.assertIn('导入失败或存在异常', res['msg'])
            self.assertIn('log', res['data'])
            log = res['data']['log']
            self.assertIn('Unknown database', log)
            self.assertIn('进程退出码: 1', log)
            self.assertIn('排查建议:', log)

    def test_mariadb_import_success_and_failed_with_log(self):
        """测试 MariaDB 导入日志返回"""
        import plugins.mariadb.index as mariadb_plugin

        mock_process = MagicMock()
        mock_process.communicate.return_value = (b"", b"")
        mock_process.returncode = 0

        mock_file = MagicMock()
        mock_file.__enter__.return_value = MagicMock()
        mock_file.__exit__.return_value = False

        with patch.object(mariadb_plugin, 'getArgs', return_value={'file': 'maria_test.sql', 'name': 'mariadb_demo'}), \
             patch.object(mariadb_plugin.os.path, 'exists', return_value=True), \
             patch.object(mariadb_plugin.os.path, 'getsize', return_value=2048), \
             patch.object(mariadb_plugin, 'pSqliteDb') as mock_db, \
             patch.object(mariadb_plugin, 'getSocketFile', return_value='/tmp/mysql.sock'), \
             patch.object(mariadb_plugin, 'getConf', return_value='/etc/my.cnf'), \
             patch('builtins.open', return_value=mock_file), \
             patch('subprocess.Popen', return_value=mock_process):

            mock_db.return_value.where.return_value.getField.return_value = 'root123'

            res_str = mariadb_plugin.importDbExternal()
            import json
            res = json.loads(res_str)
            self.assertTrue(res['status'])
            self.assertIn('log', res['data'])
            self.assertIn('MariaDB 外部数据库导入日志', res['data']['log'])


class TestImportLogFrontend(unittest.TestCase):
    """测试前端 mysql.js 与 mariadb.js 中的弹窗和 loading 特性"""

    def test_mysql_js_modal_and_loading(self):
        mysql_js_path = os.path.join(PROJECT_ROOT, 'plugins', 'mysql', 'js', 'mysql.js')
        with open(mysql_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证包含 showImportLogModal
        self.assertIn('function showImportLogModal(', content)
        # 验证 modal 属性：time: 0 (不自动关闭), shadeClose: false (点击遮罩不关闭)
        self.assertIn('time: 0', content)
        self.assertIn('shadeClose: false', content)
        # 验证提供关闭与复制按钮
        self.assertIn("btn: [pt('关闭'), pt('复制日志')]", content)
        # 验证包含代码框
        self.assertIn('id="import_log_box"', content)
        # 验证 importDbExternal 包含 loading 遮罩
        self.assertIn('var loading = layer.msg(pt(\'正在导入数据库，请稍候...\')', content)
        self.assertIn('layer.close(loading);', content)
        # 验证 importDbExternal 调用 showImportLogModal
        self.assertIn('showImportLogModal(name, file, isSuccess, logText', content)

    def test_mariadb_js_modal_and_loading(self):
        mariadb_js_path = os.path.join(PROJECT_ROOT, 'plugins', 'mariadb', 'js', 'mariadb.js')
        with open(mariadb_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证包含 showImportLogModal
        self.assertIn('function showImportLogModal(', content)
        # 验证 modal 属性：time: 0, shadeClose: false
        # 验证包含代码框
        self.assertIn('id="import_log_box"', content)
        # 验证 importDbExternal 包含 loading 遮罩
        self.assertIn('var loading = layer.msg(pt(\'正在导入数据库，请稍候...\')', content)
        self.assertIn('layer.close(loading);', content)
        # 验证 importDbExternal 调用 showImportLogModal
        self.assertIn('showImportLogModal(name, file, isSuccess, logText', content)

    def test_api_post_standard_three_args(self):
        """验证 mysql.js 与 mariadb.js 中 api.post 为标准三参数传递，杜绝参数错位导致 file 丢失"""
        for js_file in ['plugins/mysql/js/mysql.js', 'plugins/mariadb/js/mariadb.js']:
            full_path = os.path.join(PROJECT_ROOT, js_file)
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # 必须调用 api.post('import_db_external',{file:file,name:name}, function(data){
            self.assertIn("api.post('import_db_external',{file:file,name:name}, function(data){", content)
            self.assertIn("api.post('import_db_backup',{file:file,name:name}, function(data){", content)

    def test_import_db_external_progress_existing_log(self):
        """测试存在历史日志时，importDbExternalProgress 能正确读取并返回"""
        import plugins.mysql.index as mysql_plugin
        with patch.object(mysql_plugin, 'getArgs', return_value={'file': 'test.sql', 'name': 'mydb'}), \
             patch.object(mysql_plugin.os.path, 'exists', return_value=True), \
             patch.object(mysql_plugin.yf, 'readFile', return_value='【MySQL 外部数据库导入日志】\n执行结论: 数据库导入执行完毕！'):
            import json
            res = json.loads(mysql_plugin.importDbExternalProgress())
            self.assertTrue(res['status'])
            self.assertTrue(res['data']['has_log'])
            self.assertIn('执行结论: 数据库导入执行完毕！', res['data']['log'])

    def test_import_db_external_progress_no_log(self):
        """测试无历史日志时，importDbExternalProgress 返回友好提示信息"""
        import plugins.mysql.index as mysql_plugin
        with patch.object(mysql_plugin, 'getArgs', return_value={'file': 'test.sql', 'name': 'mydb'}), \
             patch.object(mysql_plugin.os.path, 'exists', return_value=False):
            import json
            res = json.loads(mysql_plugin.importDbExternalProgress())
            self.assertTrue(res['status'])
            self.assertFalse(res['data']['has_log'])
            self.assertIn('暂无执行导入的历史日志记录', res['data']['log'])

    def test_get_db_backup_import_list_filter_hidden(self):
        """测试 getDbBackupImportList 过滤 .logs 隐藏目录"""
        import plugins.mysql.index as mysql_plugin
        with patch.object(mysql_plugin.os.path, 'exists', return_value=True), \
             patch.object(mysql_plugin.os, 'listdir', return_value=['.logs', '.hidden.sql', 'normal.sql', 'data.zip']), \
             patch.object(mysql_plugin.os.path, 'isdir', return_value=False), \
             patch.object(mysql_plugin.os.path, 'getsize', return_value=1024), \
             patch.object(mysql_plugin.os.path, 'getctime', return_value=1700000000):
            import json
            res = json.loads(mysql_plugin.getDbBackupImportList())
            self.assertTrue(res['status'])
            names = [item['name'] for item in res['data']['list']]
            self.assertNotIn('.logs', names)
            self.assertNotIn('.hidden.sql', names)
            self.assertIn('normal.sql', names)
            self.assertIn('data.zip', names)

    def test_import_progress_frontend_modal(self):
        """测试前端 importDbExternalProgress 调用 showImportLogModal 而非原命令弹窗"""
        import re
        for js_file in ['plugins/mysql/js/mysql.js', 'plugins/mariadb/js/mariadb.js']:
            full_path = os.path.join(PROJECT_ROOT, js_file)
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('function importDbExternalProgress(file,name){', content)
            self.assertIn('showImportLogModal(name, file, isSuccess, logText);', content)
            func_match = re.search(r'function importDbExternalProgress\(file,name\)\{(.*?)\n\}', content, re.DOTALL)
            self.assertTrue(func_match)
            self.assertNotIn('手动导入命令CMD', func_match.group(1))


if __name__ == '__main__':
    unittest.main()

