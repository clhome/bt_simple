import unittest
import os
import re
import base64
import zlib
import struct
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def parse_png_dim(png_bytes):
    assert png_bytes[:8] == b'\x89PNG\r\n\x1a\n'
    w, h, depth, ctype = struct.unpack('>IIBB', png_bytes[16:26])
    return w, h, depth, ctype

class TestMdIconAndEditorFix(unittest.TestCase):

    def test_site_css_md_icon(self):
        site_css_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'css', 'site.css')
        with open(site_css_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查列表视图 32x32 md 图标
        m32 = re.search(r'\.list-list\s+\.ico-md[^{]*\{\s*background-image:\s*url\("data:image/png;base64,([^"]+)"\)', content)
        self.assertIsNotNone(m32, "site.css 中未找到 .list-list .ico-md 规则")
        bytes32 = base64.b64decode(m32.group(1))
        w, h, _, _ = parse_png_dim(bytes32)
        self.assertEqual((w, h), (32, 32), f"列表视图图标尺寸应为 32x32，当前为 {w}x{h}")

        # 检查大图标视图 80x80 md 图标
        m80 = re.search(r'\.fileList\s+\.ico-md[^{]*\{\s*background-image:\s*url\("data:image/png;base64,([^"]+)"\)', content)
        self.assertIsNotNone(m80, "site.css 中未找到 .fileList .ico-md 规则")
        bytes80 = base64.b64decode(m80.group(1))
        w, h, _, _ = parse_png_dim(bytes80)
        self.assertEqual((w, h), (80, 80), f"大图标视图图标尺寸应为 80x80，当前为 {w}x{h}")

    def test_ensite_css_md_icon(self):
        ensite_css_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'css', 'ensite.css')
        with open(ensite_css_path, 'r', encoding='utf-8') as f:
            content = f.read()

        m32 = re.search(r'\.list-list\s+\.ico-md[^{]*\{\s*background-image:\s*url\("data:image/png;base64,([^"]+)"\)', content)
        self.assertIsNotNone(m32, "ensite.css 中未找到 .list-list .ico-md 规则")
        bytes32 = base64.b64decode(m32.group(1))
        w, h, _, _ = parse_png_dim(bytes32)
        self.assertEqual((w, h), (32, 32))

        m80 = re.search(r'\.fileList\s+\.ico-md[^{]*\{\s*background-image:\s*url\("data:image/png;base64,([^"]+)"\)', content)
        self.assertIsNotNone(m80, "ensite.css 中未找到 .fileList .ico-md 规则")
        bytes80 = base64.b64decode(m80.group(1))
        w, h, _, _ = parse_png_dim(bytes80)
        self.assertEqual((w, h), (80, 80))

    def test_files_js_get_ext_name(self):
        files_js_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'files.js')
        with open(files_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查 getExtName 定义中包含 md
        match = re.search(r'function getExtName\(fileName\)\s*\{([\s\S]*?)\n\}', content)
        self.assertIsNotNone(match, "未找到 getExtName 函数定义")
        func_body = match.group(1)
        self.assertIn("'md'", func_body, "getExtName 中缺少 'md' 扩展名支持")

        # 使用 node 执行验证实际函数返回
        node_script = """
        """ + match.group(0) + """
        console.log(JSON.stringify({
            md: getExtName("3.md"),
            MD: getExtName("README.MD"),
            txt: getExtName("1.txt"),
            other: getExtName("unknown.xyz")
        }));
        """
        res = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, check=True)
        import json
        out = json.loads(res.stdout.strip())
        self.assertEqual(out["md"], "md", "3.md 应该返回 md")
        self.assertIn(out["MD"], ["md", "MD"], "README.MD 应该识别为 md 或 MD")
        self.assertEqual(out["txt"], "txt", "1.txt 应该返回 txt")
        self.assertEqual(out["other"], "file", "未知文件应该返回 file")

    def test_public_js_online_edit_file_cleanliness(self):
        public_js_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'public.js')
        with open(public_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        match = re.search(r'function onlineEditFile\([^)]*\)\s*\{([\s\S]*?)\n\}', content)
        self.assertIsNotNone(match, "未找到 onlineEditFile 函数")
        func_body = match.group(1)

        # 1. 验证 btn 数组无二次嵌套
        self.assertNotIn("glyphicon-floppy-disk</span> ' + ('<span class=\"glyphicon glyphicon-floppy-disk", func_body)
        self.assertNotIn("glyphicon-refresh</span> ' + ('<span class=\"glyphicon glyphicon-refresh", func_body)

        # 2. 验证 toggleHtml 无二次嵌套
        toggle_matches = re.findall(r'auto-refresh-toggle', func_body)
        # toggleHtml 中定义 1 次 class="auto-refresh-toggle"，layero.find 中查找使用 1 次
        self.assertEqual(len(toggle_matches), 2, f"auto-refresh-toggle 出现次数异常: {len(toggle_matches)}")

        # 3. 验证 content 表单只包含单个 form 与单个 textarea
        # content 现在优先走模板 YF_TPL.onlineEdit（web/static/app/tpl/i18n_tpl.js），
        # 内联的 '<form ...>' 只剩兜底分支，所以不能再要求 content: 后面紧跟 '<form'。
        # 改为直接数函数体里的元素个数，并确认模板分支存在。
        self.assertIn("YF_TPL.onlineEdit", func_body,
                      "content 未优先使用 YF_TPL.onlineEdit 模板")
        self.assertEqual(func_body.count("<form"), 1, "content 中不应出现多个 <form")
        self.assertEqual(func_body.count("</form>"), 1, "content 中不应出现多个 </form>")
        self.assertEqual(func_body.count('id="textBody"'), 1, "content 中不应出现多个 #textBody")
        self.assertEqual(func_body.count('name="encoding"'), 1, "content 中不应出现多个 encoding 下拉框")

        # 4. 验证 title 无残留孤立 "]"
        self.assertNotIn('f + "]"', func_body, "title 中不应残留孤立的 + \"]\"")

        # 5. 验证 cancel.btn 无二次嵌套
        self.assertNotIn("glyphicon-remove</span> ' + ('<span class=\"glyphicon glyphicon-remove", func_body)

    def test_js_syntax(self):
        # 验证 public.js 与 files.js 的 Node.js 语法合法性
        for js_file in ['public.js', 'files.js']:
            js_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', js_file)
            res = subprocess.run(["node", "-c", js_path], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"{js_file} 语法检测失败: {res.stderr}")

if __name__ == '__main__':
    unittest.main()
