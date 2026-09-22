# coding:utf-8
import os
import sys
import shutil
import unittest
import tempfile

# 将项目根目录加入 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
WEB_DIR = os.path.join(BASE_DIR, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

from web.utils.site import sites


class TestSiteCreateDefaultPage(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='test_site_root_')
        # 防御性检测与自愈：防止批量测试执行中其他未隔离测试 mock 了 core.yf 或 site.py 内部绑定的 yf
        import core.yf as yf_mod
        import web.utils.site as site_module
        if not hasattr(site_module.yf.writeFile, '__code__'):
            import importlib
            importlib.reload(yf_mod)
            importlib.reload(site_module)
        self.site_obj = site_module.sites()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_root_dir_new_site(self):
        """测试新建站点时自动生成美化后的默认首页并复制 favicon.ico"""
        target_site_dir = os.path.join(self.temp_dir, 'www.example.com')
        self.assertFalse(os.path.exists(target_site_dir))

        # 执行 createRootDir
        self.site_obj.createRootDir(target_site_dir)

        # 断言目录已创建
        self.assertTrue(os.path.isdir(target_site_dir))

        # 断言 index.html 存在
        index_html_path = os.path.join(target_site_dir, 'index.html')
        self.assertTrue(os.path.isfile(index_html_path))

        # 断言 favicon.ico 存在（源文件存在时必定成功复制）
        favicon_path = os.path.join(target_site_dir, 'favicon.ico')
        src_favicon = os.path.join(BASE_DIR, 'web', 'static', 'favicon.ico')
        if os.path.exists(src_favicon):
            self.assertTrue(os.path.isfile(favicon_path))
            self.assertEqual(os.path.getsize(favicon_path), os.path.getsize(src_favicon))

        # 读取 index.html 内容并校验
        with open(index_html_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 校验页面结构与核心视觉元素
        self.assertIn('<!DOCTYPE html>', content)
        self.assertIn('<html lang="zh-CN">', content)
        self.assertIn('<title>网站搭建成功 | Setup Successful</title>', content)
        self.assertIn('href="./favicon.ico"', content)
        self.assertIn('src="./favicon.ico"', content)
        self.assertIn('<h1>网站搭建成功</h1>', content)
        self.assertIn('Website Setup Successful', content)
        self.assertIn('#10b981', content)
        self.assertIn('您的专属网络空间已准备就绪', content)
        self.assertIn('Your exclusive web space is ready and online', content)
        self.assertIn('衢州御风科技有限公司出品', content)
        self.assertIn('Produced by Quzhou Yufeng Technology Co., Ltd', content)
        self.assertIn('fadeUp', content)
        self.assertIn('@media (max-width: 768px)', content)
        self.assertIn('onerror="this.parentElement.style.display=\'none\'"', content)

    def test_create_root_dir_existing_site_no_overwrite(self):
        """测试目录已存在时（非 autoInit）不覆写已有文件"""
        target_site_dir = os.path.join(self.temp_dir, 'existing.com')
        os.makedirs(target_site_dir)

        custom_index = os.path.join(target_site_dir, 'index.html')
        with open(custom_index, 'w', encoding='utf-8') as f:
            f.write('<h1>My Custom Site</h1>')

        # 执行 createRootDir
        self.site_obj.createRootDir(target_site_dir)

        with open(custom_index, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertEqual(content, '<h1>My Custom Site</h1>')

    def test_encoding_and_line_endings(self):
        """测试 site.py 以及生成的 HTML 严格遵循 UTF-8 (无 BOM) 和 LF 换行规范"""
        site_py_path = os.path.join(BASE_DIR, 'web', 'utils', 'site.py')
        with open(site_py_path, 'rb') as f:
            raw = f.read()

        # 检查无 BOM
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), "site.py 不应包含 UTF-8 BOM")

        # 检查 LF 换行（不包含 CRLF）
        self.assertNotIn(b'\r\n', raw, "site.py 必须严格使用 LF 换行符，不允许 CRLF")


if __name__ == '__main__':
    unittest.main()
