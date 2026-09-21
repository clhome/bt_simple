# coding: utf-8
import os
import sys
import subprocess
import unittest

# 确保路径可导入
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

class TestSoftCardUniformSize(unittest.TestCase):

    def setUp(self):
        self.root = project_root

    def test_01_css_uniform_size_rules(self):
        """1. 验证 site.css 与 ensite.css 中框体尺寸 100% 固化，确保所有框体完全一样大"""
        for rel_css in ['web/static/css/site.css', 'web/static/css/ensite.css']:
            css_path = os.path.join(self.root, rel_css)
            with open(css_path, 'r', encoding='utf-8') as f:
                content = f.read()

            self.assertIn('.soft-man [class*="col-"] .soft-card-box', content, f"{rel_css} 缺少 .soft-card-box 选择器")
            
            # 查找尺寸锁定块
            target_block = None
            chunks = content.split('.soft-man [class*="col-"] .soft-card-box')
            for chunk in chunks[1:]:
                block = chunk.split('{')[1].split('}')[0]
                if 'width: 100% !important;' in block:
                    target_block = block
                    break
            
            self.assertIsNotNone(target_block, f"{rel_css} 未找到包含 width: 100% !important 的 .soft-card-box 固化规则块")
            self.assertIn('height: 100% !important;', target_block, f"{rel_css} 必须包含 height: 100% !important;")
            self.assertIn('min-width: 100% !important;', target_block, f"{rel_css} 必须包含 min-width: 100% !important;")
            self.assertIn('max-width: 100% !important;', target_block, f"{rel_css} 必须包含 max-width: 100% !important;")
            print(f"  [OK] {rel_css} 卡片框体 100% 强制尺寸锁定规则校验通过")

    def test_02_cache_key_upgrade_and_invalidation(self):
        """2. 验证前端缓存 Key 升级为 index_soft_cache_html_v3 及强刷逻辑"""
        soft_js = os.path.join(self.root, 'web', 'static', 'app', 'soft.js')
        with open(soft_js, 'r', encoding='utf-8') as f:
            soft_content = f.read()

        self.assertIn("SOFT_CACHE_KEY = 'index_soft_cache_html_v3'", soft_content, "soft.js 必须升级为 index_soft_cache_html_v3")
        self.assertIn("removeItem('index_soft_cache_html')", soft_content, "soft.js 必须清理旧版本缓存")

        index_html = os.path.join(self.root, 'web', 'templates', 'default', 'index.html')
        with open(index_html, 'r', encoding='utf-8') as f:
            html_content = f.read()
        self.assertIn("soft.js?v=", html_content, "index.html 必须包含 soft.js 引用")
        self.assertIn("&t=", html_content, "index.html 必须包含版本时间戳参数")

        public_js = os.path.join(self.root, 'web', 'static', 'app', 'public.js')
        with open(public_js, 'r', encoding='utf-8') as f:
            pub_content = f.read()
        self.assertIn("removeItem('index_soft_cache_html_v3')", pub_content, "public.js 必须支持清理 index_soft_cache_html_v3")

        index_js = os.path.join(self.root, 'web', 'static', 'app', 'index.js')
        with open(index_js, 'r', encoding='utf-8') as f:
            idx_content = f.read()
        self.assertIn("removeItem('index_soft_cache_html_v3')", idx_content, "index.js 必须支持清理 index_soft_cache_html_v3")

        print("  [OK] 缓存 Key 升级、过期清理与时间戳穿透校验通过")

    def test_03_js_syntax_and_line_endings(self):
        """3. Node.js V8 语法校验与 LF / UTF-8 无 BOM 规范"""
        for rel_js in ['web/static/app/soft.js', 'web/static/app/public.js', 'web/static/app/index.js']:
            js_path = os.path.join(self.root, rel_js)
            res = subprocess.run(['node', '-c', js_path], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"{rel_js} 语法错误: {res.stderr}")
            print(f"  [OK] {rel_js} Node.js 语法检测通过")

        for rel_path in [
            'web/static/app/soft.js',
            'web/static/app/public.js',
            'web/static/app/index.js',
            'web/static/css/site.css',
            'web/static/css/ensite.css',
            'web/templates/default/index.html'
        ]:
            full_path = os.path.join(self.root, rel_path)
            with open(full_path, 'rb') as f:
                raw = f.read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), f"{rel_path} 不能有 UTF-8 BOM")
            self.assertNotIn(b'\r\n', raw, f"{rel_path} 必须强制使用 LF 换行符")
        print("  [OK] 编码格式 UTF-8 (无 BOM) 与 LF 换行符检测全部通过")


if __name__ == '__main__':
    print("=" * 50)
    print(" 开始执行首页软件框体尺寸严格统一专项测试")
    print("=" * 50)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSoftCardUniformSize)
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("=" * 50)
        print(" [SUCCESS] 所有框体完全一样大与缓存强刷机制 100% 验证通过！")
        print("=" * 50)
        sys.exit(0)
    else:
        sys.exit(1)
