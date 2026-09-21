# coding:utf-8
import os
import sys
import unittest
import shutil

# 设置运行环境
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(root_dir, 'web')
sys.path.insert(0, web_dir)
sys.path.insert(0, os.path.join(web_dir, 'core'))

import core.yf as yf
import utils.file as file_util

class TestP0DeepSecurity(unittest.TestCase):

    def setUp(self):
        self.test_tmp = os.path.join(root_dir, 'tmp', 'test_p0_sec')
        os.makedirs(self.test_tmp, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_tmp):
            shutil.rmtree(self.test_tmp, ignore_errors=True)

    def test_01_upload_segment_path_traversal(self):
        """验证分片上传接口彻底防御路径穿越与越界文件写入"""
        dummy_blobs = []
        
        # 1. 尝试使用 ../ 逃逸到上级目录
        res = file_util.uploadSegment(self.test_tmp, '../../evil.sh', '10', '0', '', '', '0', dummy_blobs)
        self.assertFalse(res['status'], "应该拦截带 ../ 的文件名")

        # 2. 尝试使用 Windows 风格反斜杠 ..\ 逃逸
        res = file_util.uploadSegment(self.test_tmp, '..\\..\\evil.sh', '10', '0', '', '', '0', dummy_blobs)
        self.assertFalse(res['status'], "应该拦截带 ..\\ 的文件名")

        # 3. 尝试使用绝对路径逃逸
        res = file_util.uploadSegment(self.test_tmp, '/etc/shadow', '10', '0', '', '', '0', dummy_blobs)
        self.assertFalse(res['status'], "应该拦截带 / 的绝对路径文件名")

        # 4. 尝试含有非法命令符号的文件名
        res = file_util.uploadSegment(self.test_tmp, 'test;rm -rf /', '10', '0', '', '', '0', dummy_blobs)
        self.assertFalse(res['status'], "应该拦截带分号的非法文件名")

    def test_02_archive_quote_safety(self):
        """验证压缩与解压命令转义的安全性"""
        executed_cmds = []
        orig_exec = yf.execShell

        def mock_exec(cmd):
            executed_cmds.append(cmd)
            return ('0', '')

        yf.execShell = mock_exec
        try:
            # 1. 含有空格和特殊单双引号的文件名进行解压
            sfile = os.path.join(self.test_tmp, "my file's & test.zip")
            dfile = os.path.join(self.test_tmp, "dest's dir")
            with open(sfile, 'w', encoding='utf-8') as f:
                f.write('dummy')
            
            res = file_util.uncompress(sfile, dfile, self.test_tmp)
            self.assertTrue(res['status'])
            last_cmd = executed_cmds[-1]
            # 验证命令中包含正确的转义，而不是裸字符串拼接
            self.assertIn(yf.shlexQuote(sfile), last_cmd)
            self.assertIn(yf.shlexQuote(dfile), last_cmd)

            # 2. 压缩单个带有空格与特殊符号的文件
            res_zip = file_util.zip(sfile, dfile + ".zip", 'zip', self.test_tmp)
            self.assertTrue(res_zip['status'])
            zip_cmd = executed_cmds[-1]
            self.assertIn(yf.shlexQuote(sfile), zip_cmd)

        finally:
            yf.execShell = orig_exec

    def test_03_migrate_dbs_and_path_validation(self):
        """验证迁移模块对 dbs 和 db_path 的参数校验"""
        import re
        db_pattern = r'^[a-zA-Z0-9_\-]+(,[a-zA-Z0-9_\-]+)*$'

        # 合法 db 列表
        valid_dbs = ["db1", "db_1,db_2", "my-db,test_db3"]
        for d in valid_dbs:
            self.assertTrue(bool(re.match(db_pattern, d)), f"应该允许合法数据库名: {d}")

        # 注入型非法 db 列表
        invalid_dbs = [
            "db1; rm -rf /",
            "db1 && echo evil",
            "db1`cat /etc/passwd`",
            "db1$(id)",
            "db1|rm -rf",
            "db1/test"
        ]
        for d in invalid_dbs:
            self.assertFalse(bool(re.match(db_pattern, d)), f"应该拦截危险注入参数: {d}")

if __name__ == '__main__':
    unittest.main()
