# coding: utf-8
import os
import sys
import unittest
import re

class TestPgDockerUI(unittest.TestCase):
    def setUp(self):
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.html_path = os.path.join(self.root_dir, 'plugins', 'pg_docker', 'index.html')

    def test_file_exists_and_encoding(self):
        self.assertTrue(os.path.exists(self.html_path), "plugins/pg_docker/index.html 应该存在")
        with open(self.html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertNotIn('\r\n', content, "文件应统一使用 LF 换行符")
        self.assertGreater(len(content), 1000, "文件内容不应为空")

    def test_backup_modal_scrollbar_and_size(self):
        with open(self.html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 验证备份管理弹窗是否配置了 overflow-y: auto 和 height: 100%
        self.assertIn('overflow-y: auto', content, "弹窗内容容器必须包含 overflow-y: auto")
        self.assertIn('box-sizing: border-box', content, "弹窗内容容器应包含 box-sizing: border-box")
        self.assertIn("['820px', '600px']", content, "备份管理弹窗尺寸应拓宽为 820px 以防内容挤压")
        
        # 验证备份管理表格列宽与防折行
        self.assertIn('white-space: nowrap;', content, "备份管理表格操作列需包含 white-space: nowrap;")

    def test_main_modal_width_and_action_column(self):
        with open(self.html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 验证主弹窗宽度设置
        self.assertIn('targetWidth = 1100', content, "主弹窗宽度应设为 1100px")
        
        # 验证操作列包含 white-space: nowrap
        self.assertIn('min-width: 210px; white-space: nowrap;', content, "主表头操作列应设置 min-width 和 nowrap")
        self.assertIn("'<td style=\"text-align: right; white-space: nowrap;\">' +", content, "实例列表操作单元格应防止折行")

if __name__ == '__main__':
    unittest.main()
