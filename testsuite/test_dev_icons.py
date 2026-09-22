import unittest
import os
import re
import base64
import struct
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def parse_png_dim(png_bytes):
    assert png_bytes[:8] == b'\x89PNG\r\n\x1a\n', "PNG 头部魔数校验失败"
    w, h, depth, ctype = struct.unpack('>IIBB', png_bytes[16:26])
    return w, h, depth, ctype

class TestDevIcons(unittest.TestCase):

    def check_css_icons(self, css_rel_path):
        css_path = os.path.join(PROJECT_ROOT, css_rel_path)
        with open(css_path, 'r', encoding='utf-8') as f:
            content = f.read()

        icons = ['py', 'json', 'sh']
        for ext in icons:
            # 检查 32x32 列表视图
            pattern_32 = rf'\.list-list\s+\.ico-{ext}[^{{]*\{{\s*background-image:\s*url\("data:image/png;base64,([^"]+)"\)'
            m32 = re.search(pattern_32, content, re.IGNORECASE)
            self.assertIsNotNone(m32, f"{css_rel_path} 中未找到 .list-list .ico-{ext} 规则")
            bytes32 = base64.b64decode(m32.group(1))
            w, h, _, ctype = parse_png_dim(bytes32)
            self.assertEqual((w, h), (32, 32), f"{ext} 列表视图图标尺寸应为 32x32，当前为 {w}x{h}")
            self.assertEqual(ctype, 6, f"{ext} 列表视图应为 RGBA (ctype=6)")

            # 检查 80x80 网格大图标视图
            pattern_80 = rf'\.fileList\s+\.ico-{ext}[^{{]*\{{\s*background-image:\s*url\("data:image/png;base64,([^"]+)"\)'
            m80 = re.search(pattern_80, content, re.IGNORECASE)
            self.assertIsNotNone(m80, f"{css_rel_path} 中未找到 .fileList .ico-{ext} 规则")
            bytes80 = base64.b64decode(m80.group(1))
            w, h, _, ctype = parse_png_dim(bytes80)
            self.assertEqual((w, h), (80, 80), f"{ext} 大图标视图图标尺寸应为 80x80，当前为 {w}x{h}")
            self.assertEqual(ctype, 6, f"{ext} 大图标视图应为 RGBA (ctype=6)")

    def test_site_css_dev_icons(self):
        self.check_css_icons(os.path.join('web', 'static', 'css', 'site.css'))

    def test_ensite_css_dev_icons(self):
        self.check_css_icons(os.path.join('web', 'static', 'css', 'ensite.css'))

    def test_files_js_get_ext_name_dev_icons(self):
        files_js_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'files.js')
        with open(files_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        match = re.search(r'function getExtName\(fileName\)\s*\{([\s\S]*?)\n\}', content)
        self.assertIsNotNone(match, "未找到 getExtName 函数定义")
        func_code = match.group(0)

        # 检查白名单中是否包含各类扩展名
        for ext in ["'py'", "'PY'", "'json'", "'JSON'", "'sh'", "'SH'"]:
            self.assertIn(ext, match.group(1), f"getExtName 中缺少扩展名支持: {ext}")

        # 使用 node 执行真实解析判断
        node_script = f"""
        {func_code}
        const results = {{
            py: getExtName("server.py"),
            PY: getExtName("MAIN.PY"),
            json: getExtName("config.json"),
            JSON: getExtName("DATA.JSON"),
            sh: getExtName("install.sh"),
            SH: getExtName("RUN.SH"),
            md: getExtName("readme.md"),
            MD: getExtName("DOC.MD"),
            txt: getExtName("log.txt"),
            other: getExtName("unknown.xyz")
        }};
        console.log(JSON.stringify(results));
        """
        res = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, check=True)
        import json
        out = json.loads(res.stdout.strip())
        self.assertEqual(out["py"], "py")
        self.assertEqual(out["PY"], "PY")
        self.assertEqual(out["json"], "json")
        self.assertEqual(out["JSON"], "JSON")
        self.assertEqual(out["sh"], "sh")
        self.assertEqual(out["SH"], "SH")
        self.assertEqual(out["md"], "md")
        self.assertEqual(out["MD"], "MD")
        self.assertEqual(out["txt"], "txt")
        self.assertEqual(out["other"], "file")

    def test_files_js_syntax(self):
        files_js_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'files.js')
        res = subprocess.run(["node", "-c", files_js_path], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"files.js 语法检查失败: {res.stderr}")

    def test_utf8_and_lf_encoding(self):
        target_files = [
            os.path.join(PROJECT_ROOT, 'web', 'static', 'css', 'site.css'),
            os.path.join(PROJECT_ROOT, 'web', 'static', 'css', 'ensite.css'),
            os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'files.js'),
            os.path.join(PROJECT_ROOT, 'task.md'),
            os.path.join(PROJECT_ROOT, 'testsuite', 'test_dev_icons.py'),
        ]
        for fpath in target_files:
            with open(fpath, 'rb') as f:
                content = f.read()
            self.assertFalse(content.startswith(b'\xef\xbb\xbf'), f"{fpath} 不得包含 UTF-8 BOM")
            self.assertNotIn(b'\r\n', content, f"{fpath} 强制要求使用 LF 换行符，检测到 CRLF")

if __name__ == '__main__':
    unittest.main()

