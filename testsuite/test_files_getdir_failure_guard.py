# coding: utf-8
"""回归守卫：面包屑点上层路径时 get_dir 被拒导致的前端 TypeError。

真机现象（用户报告，v1.9.56）：
    文件管理里处于 `/www/server/yufeng_panel`，点面包屑上层的 `www` / `server`，
    控制台抛
        Uncaught TypeError: Cannot read properties of undefined (reading 'length')
        at Object.success (files.js:629:41)

根因（两层）：
1. 后端是**按设计**拒绝的：`safePath` 的 `_SENSITIVE_EXACT` 里明确列了 `/www`、
   `/www/server`（只放行 `/` 这个特例，见 files.py get_dir 的注释与
   test_files_safepath_gaps_hardening 的 test_11b/11c），所以 get_dir 回的是
   `{status:false, msg:'FILE_DANGER'}` —— 没有 dir / files / page。
2. 前端 success 回调**不看 status 也不兜底**：`if (rdata.dir)` /
   `if (rdata.files)` 只是把写入 `window.currentFiles` 的两段循环挡住，紧接着的渲染用
   `for (var i = 0; i < rdata.files.length; ...)`（第 629 行，列 41 正是 `.length`）
   在 `rdata.files` 为 undefined 时直接抛错 —— 第 629 行能对上报告里的 629:41。

修法：回调开头先判 `!rdata || rdata.status === false` 早退 + `layer.msg` 提示
（服务端 msg 经 `yfMsgEscape` 转义再进提示，避免 layer.msg 当 HTML 渲染），
并把缺失的 dir / files 规整成空数组。

断言分两层：
- **行为**（testsuite/js/files_getdir_failure_probe.js）：把 files.js 里那段 ajax
  success 回调整段抠出来在 node vm 里真跑，喂失败 payload / 残缺 payload /
  正常空目录 / 正常列表，断言「不抛异常、失败要给提示、提示要转义、正常不受影响」。
  去掉守卫即复现报告里那句 TypeError（探针已做变异验证）。
- **结构**：源码里确实存在早退守卫，且 `layer.msg` 前面过了转义 —— 防止「守卫写在
  注释里」或「提示直接塞服务端 msg」被绕过。
"""
import os
import re
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FILES_JS = os.path.join(ROOT, 'web', 'static', 'app', 'files.js')
PROBE = os.path.join(HERE, 'js', 'files_getdir_failure_probe.js')

NODE = shutil.which('node')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _strip_comments(code):
    """去掉 // 与 /* */ 注释（引号感知），避免注释里的代码片段骗过结构断言。"""
    out = []
    i, n, quote = 0, len(code), None
    while i < n:
        ch = code[i]
        nxt = code[i + 1] if i + 1 < n else ''
        if quote:
            out.append(ch)
            if ch == '\\' and i + 1 < n:
                out.append(nxt)
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch == '/' and nxt == '/':
            nl = code.find('\n', i)
            i = n if nl == -1 else nl
            continue
        if ch == '/' and nxt == '*':
            end = code.find('*/', i + 2)
            i = n if end == -1 else end + 2
            continue
        if ch in '"\'`':
            quote = ch
        out.append(ch)
        i += 1
    return ''.join(out)


def _get_files_callback(src):
    """取 getFiles 里 `$.post('/files/get_dir', ...)` 的 success 回调源码（花括号配对）。"""
    marker = "$.post('/files/get_dir', post, function(rdata) {"
    start = src.find(marker)
    if start == -1:
        raise AssertionError('files.js 里找不到 get_dir 请求，函数被重写了？')
    i = src.index('{', start + len(marker) - 1)
    begin = i
    depth, quote = 0, None
    while i < len(src):
        ch = src[i]
        nxt = src[i + 1] if i + 1 < len(src) else ''
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch == '/' and nxt == '/':
            nl = src.find('\n', i)
            i = len(src) if nl == -1 else nl
        elif ch == '/' and nxt == '*':
            end = src.find('*/', i + 2)
            i = len(src) if end == -1 else end + 1
        elif ch in '"\'':
            quote = ch
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return src[begin + 1:i]
        i += 1
    raise AssertionError('get_dir success 回调花括号不配对')


class TestFilesGetDirFailureGuard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _read(FILES_JS)
        cls.callback = _get_files_callback(cls.src)
        # 结构断言只看代码，不看注释
        cls.code = _strip_comments(cls.callback)

    # ---- 结构层 ----

    def test_01_callback_guards_failed_payload_before_render(self):
        """失败 payload 必须在任何渲染/取值之前早退，且不许再裸读 dir/files。"""
        code = self.code
        guard_pos = code.find('rdata.status === false')
        self.assertNotEqual(guard_pos, -1,
                            'get_dir 回调缺少 status === false 守卫：后端拒绝时仍会走到对 undefined 取 length')
        # 守卫必须在第一次读 dir/files 之前
        first_use = min([p for p in (code.find('rdata.dir'), code.find('rdata.files')) if p != -1])
        self.assertLess(guard_pos, first_use, '守卫位置在取用 dir/files 之后，等于没守')
        guard_block = code[guard_pos:guard_pos + 800]
        self.assertIn('return', guard_block, '守卫分支没有 return，后面照样会炸')
        self.assertIn('layer.msg(', guard_block, '守卫分支要给出提示，不能静默失败')

    def test_02_failure_message_is_escaped(self):
        """提示走 layer.msg（按 HTML 渲染），服务端 msg 必须先转义。"""
        guard_block = self.code[self.code.find('rdata.status === false'):][:800]
        self.assertRegex(guard_block, r'layer\.msg\(\s*yfMsgEscape\(',
                         '服务端 msg 未转义就进了 layer.msg，可被文件名/路径注入 HTML')

    def test_03_dir_and_files_normalized_before_render(self):
        """缺失的 dir / files 要规整成空数组，后面所有 .length 才安全。"""
        for field in ('dir', 'files'):
            self.assertRegex(
                self.code,
                r'if\s*\(\s*rdata\.%s\s*==\s*null\s*\)\s*\{\s*rdata\.%s\s*=\s*\[\]\s*;' % (field, field),
                'rdata.%s 没有 null -> [] 的归一化' % field)

    def test_04_no_unguarded_length_on_response(self):
        """回调里对响应字段取 .length 必须发生在归一化之后。"""
        uses = list(re.finditer(r'rdata\.(?:dir|files)\.length', self.code))
        self.assertTrue(uses, '回调里已经没有 dir/files 循环了？用例可能已失效')
        norm_pos = min(self.code.find('rdata.dir = []'), self.code.find('rdata.files = []'))
        self.assertNotEqual(norm_pos, -1, '找不到归一化代码')
        for m in uses:
            self.assertGreater(m.start(), norm_pos,
                               '存在归一化之前就取 .length 的代码路径：%s' % self.code[max(0, m.start() - 80):m.start() + 20])

    # ---- 行为层 ----

    @unittest.skipUnless(NODE, '未安装 node，跳过前端行为夹具')
    def test_10_probe_reruns_callback_with_failure_payloads(self):
        """真跑回调：安全拒绝 / 含 HTML 的 msg / 残缺 payload / 正常空目录 / 正常列表。"""
        proc = subprocess.run([NODE, PROBE], cwd=ROOT, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=180)
        out = proc.stdout.decode('utf-8', 'replace').strip()
        err = proc.stderr.decode('utf-8', 'replace').strip()
        self.assertEqual(proc.returncode, 0,
                         'get_dir 回调在失败 payload 上仍抛异常或提示不对：%s %s' % (out, err[-2000:]))
        self.assertEqual(out.splitlines()[-1], 'OK', out)

    def test_11_probe_actually_reproduces_the_reported_error(self):
        """守卫被删掉时，探针必须复现报告里那句 TypeError（防止用例变成永绿）。

        只在内存里做变异：把本次新增的守卫 + 归一化整段摘掉（即回到修复前的回调），
        写回 files.js 跑探针，最后无论成败都把原文件还原。
        """
        if not NODE:
            self.skipTest('未安装 node，跳过变异验证')
        start_marker = "if (!rdata || typeof rdata !== 'object' || rdata.status === false) {"
        end_marker = '// 路径与条目名都来自用户可控目录'
        start = self.callback.find(start_marker)
        end = self.callback.find(end_marker)
        self.assertNotEqual(start, -1)
        self.assertNotEqual(end, -1)
        self.assertLess(start, end)
        mutant_cb = self.callback[:start] + self.callback[end:]
        mutated = self.src.replace(self.callback, mutant_cb, 1)
        self.assertNotEqual(mutated, self.src, '变异未生效')
        backup = FILES_JS + '.mutant_bak'
        try:
            shutil.copyfile(FILES_JS, backup)
            with open(FILES_JS, 'w', encoding='utf-8') as f:
                f.write(mutated)
            proc = subprocess.run([NODE, PROBE], cwd=ROOT, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=180)
            out = proc.stdout.decode('utf-8', 'replace')
            self.assertNotEqual(proc.returncode, 0, '删掉守卫后探针仍然通过 —— 用例已失去守护能力')
            self.assertIn("reading 'length'", out,
                          '变异后没复现报告里的 reading length：%s' % out[-500:])
        finally:
            shutil.move(backup, FILES_JS)


if __name__ == '__main__':
    unittest.main()
