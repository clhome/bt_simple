# -*- coding: utf-8 -*-
"""safeMessage 的 HTML 转义 / 净化回归测试。

被测生产代码：
  - web/static/app/public.js 的 yfMsgEscape / yfMsgSanitize，以及 safeMessage
    的 title / content 注入点
  - web/static/app/files.js 的 renderFileOverwriteHtml（文件名同时落在
    title 属性位与文本位）

为什么用 Node 而不是在 Python 里复刻：净化器是前端 JS，用 Python 再写一份
等价实现来测，测的是「替身」而不是生产代码 —— 两边一旦漂移，测试照样全绿。
tools/test_safemessage_sanitize.js 直接从 public.js 抽取真实代码块求值。

本文件额外固化「变异自证」：把净化器改成恒等函数后，行为测试必须转为失败。
缺了这一步，一个写错的测试会永远全绿，看起来像有保护其实没有。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PUBLIC_JS = os.path.join(ROOT, 'web', 'static', 'app', 'public.js')
FILES_JS = os.path.join(ROOT, 'web', 'static', 'app', 'files.js')
HARNESS = os.path.join(HERE, 'i18n_scripts', 'tools', 'test_safemessage_sanitize.js')

NODE_CANDIDATES = [
    'node',
    r'C:/Users/wzucc/.workbuddy-ai/binaries/node/versions/22.22.2-2/node.exe',
]


def find_node():
    for c in NODE_CANDIDATES:
        p = shutil.which(c) or (c if os.path.isfile(c) else None)
        if not p:
            continue
        try:
            r = subprocess.run([p, '--version'], capture_output=True, text=True, timeout=30)
        except Exception:
            continue
        if r.returncode == 0:
            return p
    return None


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


CHROME_CANDIDATES = [
    r'C:/Program Files/Google/Chrome/Application/chrome.exe',
    r'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'google-chrome',
    'chromium',
]


def find_chrome():
    for c in CHROME_CANDIDATES:
        p = c if os.path.isfile(c) else shutil.which(c)
        if p:
            return p
    return None


NODE = find_node()


class TestSafeMessageEscape(unittest.TestCase):

    def setUp(self):
        if NODE is None:
            self.skipTest('未找到可用的 node')
        if not os.path.isfile(HARNESS):
            self.skipTest('缺少夹具 tools/test_safemessage_sanitize.js')

    # ---------- 行为测试（真实代码） ----------

    def test_01_harness_passes_on_real_code(self):
        """净化层行为测试：XSS 向量必须被拦，既有 UI 必须保留。"""
        r = subprocess.run([NODE, HARNESS], cwd=ROOT, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=120)
        self.assertEqual(0, r.returncode,
                         '净化层行为测试未通过：\n' + (r.stdout or '') + (r.stderr or ''))

    def test_02_mutation_self_proof(self):
        """变异自证：净化器退化为恒等函数后，行为测试必须失败。

        若这一步仍然通过，说明断言恒真、测试形同虚设。
        """
        src = read(PUBLIC_JS)
        needle = 'function yfMsgSanitize(html, extended) {'
        self.assertEqual(1, src.count(needle), '未能唯一定位 yfMsgSanitize 定义')
        mutant = src.replace(
            needle,
            needle + " return String(html == null ? '' : html);")
        tmpdir = tempfile.mkdtemp(prefix='yf_sanitize_mut_')
        try:
            mp = os.path.join(tmpdir, 'public_mutated.js')
            with open(mp, 'w', encoding='utf-8', newline='') as f:
                f.write(mutant)
            env = dict(os.environ)
            env['YF_PUBLIC_JS'] = mp
            r = subprocess.run([NODE, HARNESS], cwd=ROOT, capture_output=True,
                               text=True, encoding='utf-8', errors='replace',
                               timeout=120, env=env)
            self.assertNotEqual(0, r.returncode,
                                '变异体（净化器=恒等函数）竟然通过了测试 → 断言恒真')
            out = (r.stdout or '') + (r.stderr or '')
            # 至少要有 XSS 段（A）的失败，证明拦截类断言真的在起作用
            self.assertIn('[FAIL] A', out, '变异体上没有任何 A 段（XSS）失败：\n' + out)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ---------- 静态检查：注入点确实接了净化 ----------

    def test_03_safe_message_injection_points(self):
        """safeMessage 的 title / 正文 / 附加 HTML 三处都必须过净化。"""
        src = read(PUBLIC_JS)
        self.assertIn('yfMsgSanitize(h)', src, '正文 h 未接入净化')
        self.assertIn('yfMsgSanitize(f, true)', src, '附加 HTML f 未接入净化')
        self.assertIn('title: safeTitle', src, 'title 未接入净化')
        # 旧的裸拼接必须消失（否则净化形同虚设）
        self.assertNotIn('"<p>" + h + "</p>"', src, '正文仍是裸拼接')
        self.assertNotIn('"</p>" + f + "<div', src, '附加 HTML 仍是裸拼接')
        self.assertNotIn('title: j,', src, 'title 仍是裸赋值')

    def test_04_files_overwrite_escapes_filename(self):
        """renderFileOverwriteHtml：文件名（含 title 属性位）必须转义。"""
        src = read(FILES_JS)
        self.assertIn('yfMsgEscape(item.filename)', src, '文件名未转义')
        self.assertIn('safeFileName', src)
        self.assertNotIn('\'title="\' + item.filename', src, 'title 属性位仍是裸拼接')
        self.assertNotIn('>\' + item.filename + \'</td>', src, '单元格文本仍是裸拼接')

    def test_05_line_endings_and_bom_preserved(self):
        """编辑不得改变换行符与 BOM（本仓库存在历史 CRLF 文件）。"""
        for p in (PUBLIC_JS, FILES_JS):
            with open(p, 'rb') as f:
                b = f.read()
            self.assertNotIn(b'\r\n', b, '%s 被写成了 CRLF' % os.path.basename(p))
            self.assertFalse(b.startswith(b'\xef\xbb\xbf'),
                             '%s 被写入了 BOM' % os.path.basename(p))

    def test_06_js_syntax(self):
        """两个文件必须通过 Node 语法校验。"""
        for p in (PUBLIC_JS, FILES_JS):
            r = subprocess.run([NODE, '--check', p], capture_output=True,
                               text=True, encoding='utf-8', errors='replace', timeout=60)
            self.assertEqual(0, r.returncode,
                             '%s 语法错误：%s' % (os.path.basename(p), r.stderr))

    # ---------- 浏览器级验证（最强证据，无 Chrome 时跳过） ----------

    def test_07_browser_does_not_execute_sanitized_payloads(self):
        """headless Chrome 实测：净化后的载荷不得执行；对照组必须能执行。

        字符串断言只能证明「危险子串不在了」，浏览器验证才能证明
        「即便有漏网，浏览器也不执行」。对照组是必须的 —— 若探针本身
        抓不到执行，「净化后未置位」的结论毫无意义。
        """
        chrome = find_chrome()
        if chrome is None:
            self.skipTest('未找到 Chrome，跳过浏览器级验证')
        gen = os.path.join(HERE, 'i18n_scripts', 'tools', 'gen_xss_browser_probe.js')
        if not os.path.isfile(gen):
            self.skipTest('缺少生成器 gen_xss_browser_probe.js')

        tmpdir = tempfile.mkdtemp(prefix='yf_xss_probe_')
        try:
            env = dict(os.environ)
            env['YF_PROBE_OUT'] = tmpdir
            r = subprocess.run([NODE, gen], cwd=ROOT, capture_output=True,
                               text=True, encoding='utf-8', errors='replace',
                               timeout=60, env=env)
            self.assertEqual(0, r.returncode, '生成验证页失败：' + (r.stderr or ''))

            def title_of(name):
                url = 'file:///' + os.path.join(tmpdir, name).replace('\\', '/')
                rr = subprocess.run(
                    [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
                     '--virtual-time-budget=3000', '--dump-dom', url],
                    capture_output=True, text=True, encoding='utf-8',
                    errors='replace', timeout=120)
                m = re.search(r'<title>([^<]*)</title>', rr.stdout or '')
                return m.group(1) if m else None

            raw = title_of('xss_browser_probe_raw.html')
            self.assertIsNotNone(raw, '对照组标题未取到')
            self.assertNotEqual('pending', raw, '对照组脚本未执行，探针无效')
            self.assertGreater(json.loads(raw)['pwned'], 0,
                               '对照组未发生脚本执行 → 探针抓不到执行，结论无意义')

            san = title_of('xss_browser_probe.html')
            self.assertIsNotNone(san, '净化页标题未取到')
            self.assertNotEqual('pending', san, '净化页脚本未执行')
            data = json.loads(san)
            self.assertEqual(0, data['pwned'],
                             '净化后的载荷在浏览器中执行了：' + san)
            # 同时确认既有 UI 元素确实被渲染出来（不是把内容全转义成文本）
            self.assertGreater(data['strictTags'], 15, '严格档渲染出的元素过少：' + san)
            self.assertGreater(data['extTags'], 15, '宽松档渲染出的元素过少：' + san)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
