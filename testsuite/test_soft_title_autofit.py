# coding: utf-8
import os
import sys
import subprocess
import unittest

# 确保路径可导入
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

class TestSoftTitleAutoFit(unittest.TestCase):

    def setUp(self):
        self.root = project_root

    def test_01_soft_title_no_version(self):
        """1. 验证 soft.js 首页软件卡片去除版本号显示，保留 data-id 与点击参数"""
        soft_js = os.path.join(self.root, 'web', 'static', 'app', 'soft.js')
        with open(soft_js, 'r', encoding='utf-8') as f:
            js_code = f.read()

        # 不再包含首页名称拼接版本号
        self.assertNotIn("var name = raw_title + ' ' + plugin.setup_version", js_code, "首页软件名称中依然残留版本号拼接")
        self.assertIn("var name = raw_title;", js_code, "未找到首页纯净标题赋值")
        
        # 验证 data-id 与 softMain 依然传递 setup_version 保持正常功能
        self.assertIn("data-id=\"' + data_id + '\"", js_code, "data-id 必须保留")
        self.assertIn("plugin.setup_version", js_code, "softMain 参数中必须保留版本号")
        print("  [OK] 软件名称去除版本号、data-id 与交互参数保持完整")

    def test_02_css_sname_centering_and_scaling(self):
        """2. 验证 site.css 与 ensite.css 中 .sname 居中与动态字号支持"""
        for rel_css in ['web/static/css/site.css', 'web/static/css/ensite.css']:
            css_path = os.path.join(self.root, rel_css)
            with open(css_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 验证不允许有 font-size: 12px !important，必须允许内联动态缩放
            sname_block = content.split('.soft-man .sname {')[-1].split('}')[0]
            self.assertNotIn("font-size: 12px !important;", sname_block,
                             f"{rel_css} .sname 中仍有 font-size 强约束 !important，阻碍动态缩小")
            
            # 验证 display: block 与 text-align: center 杜绝 Flex 两端截断
            self.assertIn("display: block", sname_block, f"{rel_css} 必须使用 display: block")
            self.assertIn("text-align: center", sname_block, f"{rel_css} 必须使用 text-align: center")
            self.assertNotIn("display: inline-flex", sname_block, f"{rel_css} 不得使用会导致双向溢出裁切的 inline-flex")
            print(f"  [OK] {rel_css} 居中排版与字号动态缩放样式校验通过")

    def test_03_autofit_logic_and_events(self):
        """3. 验证 soft.js 中自适应字号测量与初始梯级预估"""
        soft_js = os.path.join(self.root, 'web', 'static', 'app', 'soft.js')
        with open(soft_js, 'r', encoding='utf-8') as f:
            js_code = f.read()

        self.assertIn("function autoFitSoftName()", js_code, "未找到 autoFitSoftName 函数")
        self.assertIn("scrollWidth > el.clientWidth", js_code, "未找到 DOM 尺寸溢出动态判定")
        self.assertIn("resize.softName", js_code, "未找到 resize 响应式监听")
        self.assertIn("title=\"' + raw_title + '\"", js_code, "卡片名称必须包含完整标题 title 提示")
        print("  [OK] 动态测量 autoFitSoftName 与 resize 适配逻辑校验通过")

    def test_04_js_syntax_and_line_ending(self):
        """4. Node.js V8 语法校验与 UTF-8 LF 规范"""
        soft_js = os.path.join(self.root, 'web', 'static', 'app', 'soft.js')
        res = subprocess.run(['node', '-c', soft_js], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"soft.js 语法错误: {res.stderr}")
        print("  [OK] soft.js Node.js V8 语法检测 100% 通过")

        for rel_path in [
            'web/static/app/soft.js',
            'web/static/css/site.css',
            'web/static/css/ensite.css'
        ]:
            full_path = os.path.join(self.root, rel_path)
            with open(full_path, 'rb') as f:
                raw = f.read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), f"{rel_path} 不能有 UTF-8 BOM")
            self.assertNotIn(b'\r\n', raw, f"{rel_path} 必须强制使用 LF 换行符")
        print("  [OK] 编码格式 UTF-8 (无 BOM) 与 LF 换行符检测全部通过")


if __name__ == '__main__':
    print("=" * 50)
    print(" 开始执行首页软件名称精简与字号自适应测试")
    print("=" * 50)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSoftTitleAutoFit)
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("=" * 50)
        print(" [SUCCESS] 软件名称精简与字号自适应 100% 验证通过！")
        print("=" * 50)
        sys.exit(0)
    else:
        sys.exit(1)
