# coding: utf-8
import os
import sys
import stat
import shutil
import unittest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_DIR, 'web'))

class TestSiteDeleteFix(unittest.TestCase):
    def test_public_js_safemessage_execution_order(self):
        """验证 public.js 中 safeMessage 确定按钮在关闭弹窗前先执行业务回调 g()"""
        public_js_path = os.path.join(PROJECT_DIR, 'web', 'static', 'app', 'public.js')
        with open(public_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('function safeMessage(', content)
        # 确保 g() 在 layer.close(mess) 之前执行
        submit_idx = content.find('$("#toSubmit").on(\'click\'')
        self.assertNotEqual(submit_idx, -1)
        block = content[submit_idx:submit_idx + 1000]

        g_call_idx = block.find('g();')
        close_idx = block.find('layer.close(mess);')
        self.assertNotEqual(g_call_idx, -1, "回调 g() 必须被调用")
        self.assertNotEqual(close_idx, -1, "弹窗 layer.close(mess) 必须被调用")
        self.assertLess(g_call_idx, close_idx, "回调 g() 必须在 layer.close(mess) 之前执行，防止 DOM 提前销毁")

    def test_site_js_webdelete_and_alldelete_logic(self):
        """验证 site.js 中 webDelete 与 allDeleteSite 防丢失监听与 showMsg 提示规范"""
        site_js_path = os.path.join(PROJECT_DIR, 'web', 'static', 'app', 'site.js')
        with open(site_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证 webDelete
        self.assertIn('function webDelete(wid, wname)', content)
        webdel_idx = content.find('function webDelete(wid, wname)')
        webdel_block = content[webdel_idx:webdel_idx + 1800]

        self.assertIn('change.delpath', webdel_block, "必须有 delpath change 事件监听")
        self.assertIn('&path=1', webdel_block, "必须构造 &path=1 参数")
        self.assertIn('showMsg(', webdel_block, "必须使用 showMsg 展示删除成功/失败结果")
        self.assertIn('getWeb(', webdel_block, "必须在 showMsg 回调中执行 getWeb 刷新")
        self.assertIn('.fail(', webdel_block, "必须包含 .fail() 错误容错处理")

        # 验证 allDeleteSite
        self.assertIn('function allDeleteSite()', content)
        alldel_idx = content.find('function allDeleteSite()')
        alldel_block = content[alldel_idx:alldel_idx + 1200]
        self.assertIn('change.delpath_all', alldel_block, "批量删除必须有 delpath change 监听")
        self.assertIn('&path=1', alldel_block, "批量删除必须正确读取并拼接 &path=1")

    def test_site_py_delete_method(self):
        """验证 site.py 中 delete 方法支持真实路径清理、delUserInI 调用与安全防御"""
        site_py_path = os.path.join(PROJECT_DIR, 'web', 'utils', 'site.py')
        with open(site_py_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('def delete(self, site_id, path):', content)
        delete_idx = content.find('def delete(self, site_id, path):')
        delete_block = content[delete_idx:delete_idx + 1500]

        # 检查判空防御
        self.assertIn("if not info:", delete_block, "必须对不存在的站点进行判空防御")
        # 检查真实路径获取
        self.assertIn("info.get('path'", delete_block, "必须支持获取站点实际物理路径 info['path']")
        # 检查 delUserInI
        self.assertIn("self.delUserInI(", delete_block, "删除目录前必须调用 delUserInI 解锁 .user.ini")
        # 检查 yf.removeDir
        self.assertIn("yf.removeDir(", delete_block, "必须调用 yf.removeDir 清除物理目录")

    def test_yf_removedir_handles_readonly_files(self):
        """验证 yf.removeDir 可以顺利删除包含只读文件和子目录的文件夹"""
        from core import yf

        test_dir = os.path.join(PROJECT_DIR, 'testsuite', '.scratch', 'temp_site_delete_test_dir')
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir, ignore_errors=True)

        os.makedirs(os.path.join(test_dir, 'subdir', 'nested'), exist_ok=True)
        normal_file = os.path.join(test_dir, 'index.html')
        with open(normal_file, 'w', encoding='utf-8') as f:
            f.write("hello")

        readonly_file = os.path.join(test_dir, 'subdir', 'readonly.txt')
        with open(readonly_file, 'w', encoding='utf-8') as f:
            f.write("readonly content")
        # 设为只读
        os.chmod(readonly_file, stat.S_IREAD)

        # 验证文件确实是只读
        self.assertTrue(os.path.exists(readonly_file))

        # 执行 yf.removeDir
        result = yf.removeDir(test_dir)
        self.assertTrue(result, "yf.removeDir 应该返回 True")
        self.assertFalse(os.path.exists(test_dir), "测试目录应当已被彻底删除")

    def test_file_encodings_and_line_endings(self):
        """验证所有涉及修改的文件均为 UTF-8 (无 BOM) 且使用 LF 换行符"""
        target_files = [
            os.path.join(PROJECT_DIR, 'web', 'static', 'app', 'public.js'),
            os.path.join(PROJECT_DIR, 'web', 'static', 'app', 'site.js'),
            os.path.join(PROJECT_DIR, 'web', 'utils', 'site.py'),
            os.path.join(PROJECT_DIR, 'web', 'core', 'yf.py'),
            os.path.join(PROJECT_DIR, 'task.md'),
        ]

        for file_path in target_files:
            with open(file_path, 'rb') as f:
                raw = f.read()

            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), f"{file_path} 不能包含 UTF-8 BOM 头")
            self.assertNotIn(b'\r\n', raw, f"{file_path} 必须强制使用 LF 换行符，不允许 CRLF")

if __name__ == '__main__':
    unittest.main()
