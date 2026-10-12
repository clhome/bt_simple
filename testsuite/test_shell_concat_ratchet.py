# coding: utf-8
"""P0-1（web 侧）棘轮守卫：shell 拼接点不得**新增**「未引用变量直进 shell」形态。

背景与动机
----------
`web/` 下存在大量历史写法 `yf.execShell('...' + var + '...')`。一次性全改既改不完、
也不安全（改动面铺到几十个模块），而「修一半」恰恰是本仓已经栽过的坑：同族点里
改了一个、漏了另一个，漏洞照旧（如 MariaDB 端整文件漏修、dnsapi 的键值仍裸拼）。

棘轮（ratchet）的用法：把**现存违规登记为基线**（`scripts/shell_concat_baseline.txt`，
随测试入库），只减不增：
  * 出现基线之外的新违规 -> 红；
  * 某个已修点被改回裸拼 -> 它不在基线里 -> 红；
  * 基线里的旧违规被修掉 -> 绿（可顺手把基线调小）。

规则（AST，不用正则 —— 正则分不清字符串字面量里的加号/引号）
----------------------------------------------------------
  inline_bare_concat   首个实参是字符串拼接/格式化表达式（加号 / 百分号 / f-string /
                       `.format()` / `.join()`），且其中有**未被引用**的变量。
                       已引用 = 表达式内被 `shlexQuote(...)` 直接包裹，或该变量在同一
                       函数里被赋值为含 `shlexQuote` 的表达式（含 `.append(shlexQuote)`）。
  bare_variable        首个实参就是一个裸变量名（`execShell(cmd)`）——静态看不到构造
                       过程，一律登记为基线，但禁止**新增**（新增即需人工复核）。
  export_doublequote   出现 `export <key>="<value>"` 形态的插值：双引号内 `$()` 与
                       反引号**仍会展开**。这是 dnsapi 注入的根因（`getDnsapiExportVar`），
                       基线必须为空 —— 任何一次回退都会变红。

扫描范围：`web/` + `panel_tools.py` + `panel_task.py`（与 P0-1 收口范围一致；
`plugins/` 另开一轮，避免跨模块返工）。刻意**排除** `testsuite/`、`test/`，
否则守卫自己的夹具会被自己命中。
"""
import ast
import os
import re
import sys
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
WEB_DIR = os.path.join(project_dir, 'web')
for _p in (WEB_DIR, project_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.yf as real_yf  # noqa: E402

ROOT = project_dir
SITE_PY = os.path.join(WEB_DIR, 'utils', 'site.py')
FILE_PY = os.path.join(WEB_DIR, 'utils', 'file.py')
#: 棘轮基线放在 `scripts/`，与 `scripts/code_quality_baseline.json` 保持一致
BASELINE_FILE = os.path.join(project_dir, 'scripts', 'shell_concat_baseline.txt')

SCAN_DIRS = ['web']
SCAN_ROOT_FILES = ['panel_tools.py', 'panel_task.py']
EXCLUDE_DIRS = {'__pycache__', 'node_modules', 'test', 'testsuite', '参考', '文档',
                'cl_tasks', '.git', 'data', 'logs', 'tmp', '.workbuddy-ai'}

SHELL_ATTRS = {'execShell', 'execShellRc', 'safeExecShell'}
SUBPROCESS_ATTRS = {'Popen', 'run', 'call', 'check_output', 'check_call'}
QUOTE_FUNCS = {'shlexQuote', 'shlex_quote', 'quote'}

#: `export k="v"` 形态的字面量特征
_EXPORT_LITERAL = 'export '
_DOUBLEQUOTE_LITERAL = '"'

#: 单引号引用之外的 shell 元字符（分号截断、`$()`/反引号命令替换、`${IFS}` 空白绕过）。
#: 用 chr() 拼出来，避免本文件里出现需要二次转义的裸反斜杠。
_SHELL_METACHARS = ';|&<>$' + chr(96) + chr(92) + chr(10)

_BACKSLASH = chr(92)
_DQUOTE = chr(34)
_SQUOTE = chr(39)


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read().replace(chr(13) + chr(10), chr(10))


def _iter_py_files():
    for base in SCAN_DIRS:
        abs_base = os.path.join(ROOT, base)
        if not os.path.isdir(abs_base):
            continue
        for root, dirs, files in os.walk(abs_base):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fn in sorted(files):
                if fn.endswith('.py'):
                    yield os.path.join(root, fn)
    for fn in SCAN_ROOT_FILES:
        p = os.path.join(ROOT, fn)
        if os.path.isfile(p):
            yield p


# ---------------------------------------------------------------------------
# AST 规则引擎（纯函数，便于用内嵌夹具自证）
# ---------------------------------------------------------------------------
def _is_quote_call(func):
    """`yf.shlexQuote` / `shlex.quote` / `shlex_quote`。"""
    if isinstance(func, ast.Attribute) and func.attr in QUOTE_FUNCS:
        return True
    if isinstance(func, ast.Name) and func.id in QUOTE_FUNCS:
        return True
    return False


def _expr_has_quote(expr):
    return any(isinstance(n, ast.Call) and _is_quote_call(n.func) for n in ast.walk(expr))


def _quote_wrapped_ids(expr):
    """表达式内被 `shlexQuote(...)` 直接包裹的变量名节点 id。"""
    out = set()
    for n in ast.walk(expr):
        if isinstance(n, ast.Call) and _is_quote_call(n.func):
            for inner in ast.walk(n):
                if isinstance(inner, ast.Name):
                    out.add(id(inner))
    return out


def _value_names(expr):
    """表达式里作为**数据值**出现的 Name 节点（排除 `yf.xxx` 的接收者与 `foo()` 的函数名）。"""
    receivers = set()
    for n in ast.walk(expr):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            receivers.add(id(n.value))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            receivers.add(id(n.func))
    return [n for n in ast.walk(expr) if isinstance(n, ast.Name) and id(n) not in receivers]


def _func_quoted_names(func):
    """函数内被「赋值为含 shlexQuote 的表达式」的变量名（含 `.append(shlexQuote)`）。

    例：`q_path = yf.shlexQuote(path)`、`sfiles.append(yf.shlexQuote(rel))`、
    `sfiles_str = ' '.join(sfiles)`（传递闭包）。修掉赋值层的引用同样会让棘轮变红。
    """
    if func is None:
        return set()
    quoted = set()
    changed = True
    while changed:
        changed = False
        for n in ast.walk(func):
            if isinstance(n, ast.Assign):
                val = n.value
                if _expr_has_quote(val) or any(
                        isinstance(x, ast.Name) and x.id in quoted for x in ast.walk(val)):
                    for t in n.targets:
                        if isinstance(t, ast.Name) and t.id not in quoted:
                            quoted.add(t.id)
                            changed = True
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == 'append' and isinstance(n.func.value, ast.Name)):
                if _expr_has_quote(n) or any(
                        isinstance(x, ast.Name) and x.id in quoted for x in ast.walk(n)):
                    if n.func.value.id not in quoted:
                        quoted.add(n.func.value.id)
                        changed = True
    return quoted


def _enclosing_func(tree, node):
    best = None
    for parent in ast.walk(tree):
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if parent.lineno <= node.lineno <= (parent.end_lineno or parent.lineno):
                if best is None or parent.lineno > best.lineno:
                    best = parent
    return best


def _shell_call_kind(node):
    f = node.func
    if isinstance(f, ast.Attribute):
        if f.attr in SHELL_ATTRS:
            return f.attr
        if f.attr == 'system' and isinstance(f.value, ast.Name) and f.value.id == 'os':
            return 'os.system'
        if f.attr in SUBPROCESS_ATTRS and isinstance(f.value, ast.Name) \
                and f.value.id == 'subprocess':
            return 'subprocess.' + f.attr
    if isinstance(f, ast.Name) and f.id in SHELL_ATTRS:
        return f.id
    return None


def _is_string_expr(arg):
    """是不是「在代码里现拼/现格式化」的字符串表达式。"""
    if isinstance(arg, (ast.BinOp, ast.JoinedStr)):
        return True
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) \
            and arg.func.attr in ('format', 'join'):
        return True
    return False


def _outermost_string_exprs(tree):
    """所有字符串拼接/格式化表达式，且去掉被其他候选嵌套的内层节点。

    `'a' + k + '="' + v` 的 AST 是左嵌套的 BinOp 树，逐个 walk 会把同一条语句
    拆成多个指纹；只保留最外层，保证「一条语句 = 一个指纹」。
    """
    cands = [n for n in ast.walk(tree) if isinstance(n, ast.expr) and _is_string_expr(n)]
    ids = {id(n) for n in cands}
    nested = set()
    for n in cands:
        for sub in ast.walk(n):
            if sub is not n and id(sub) in ids:
                nested.add(id(sub))
    return [n for n in cands if id(n) not in nested]


def _norm_expr(src, node):
    seg = ast.get_source_segment(src, node) or ''
    return ' '.join(seg.split())[:120]


def analyze_source(rel, src):
    """返回该源码的违规 {fingerprint: {'rule', 'detail'}}。"""
    out = {}
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kind = _shell_call_kind(node)
        if not kind or not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, (ast.Starred, ast.List, ast.Tuple, ast.Constant)):
            continue
        func = _enclosing_func(tree, node)
        fname = func.name if func else '<module>'

        if isinstance(arg, ast.Name):
            fp = '%s::%s::bare_variable::%s' % (rel, fname, arg.id)
            out[fp] = {'rule': 'bare_variable',
                       'detail': 'shell 首参是裸变量 %s（%s:%d）' % (arg.id, rel, node.lineno)}
            continue

        if not _is_string_expr(arg):
            continue

        quoted_ids = _quote_wrapped_ids(arg)
        func_quoted = _func_quoted_names(func)
        bare = sorted({n.id for n in _value_names(arg)
                       if id(n) not in quoted_ids and n.id not in func_quoted})
        if not bare:
            continue
        expr = _norm_expr(src, arg)
        fp = '%s::%s::inline_bare_concat::%s' % (rel, fname, expr)
        out[fp] = {'rule': 'inline_bare_concat',
                   'detail': '%s 里 %s 未引用就拼进 %s（%s:%d）'
                             % (fname, ','.join(bare), kind, rel, node.lineno)}

    # 规则三：`export <key>="<value>"` 形态（与 shell 调用点无关，扫全文件）
    for node in _outermost_string_exprs(tree):
        if not any(isinstance(n, ast.Name) for n in ast.walk(node)):
            continue
        lits = [n.value for n in ast.walk(node)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        if any(_EXPORT_LITERAL in s for s in lits) \
                and any(_DOUBLEQUOTE_LITERAL in s for s in lits):
            func = _enclosing_func(tree, node)
            fname = func.name if func else '<module>'
            fp = '%s::%s::export_doublequote::%s' % (rel, fname, _norm_expr(src, node))
            out[fp] = {'rule': 'export_doublequote',
                       'detail': '%s 用 `export k="v"` 拼 shell（双引号内 $()/反引号仍展开）'
                                 % fname}
    return out


def collect_violations():
    all_v = {}
    for path in _iter_py_files():
        rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
        try:
            all_v.update(analyze_source(rel, _read(path)))
        except SyntaxError as e:
            raise AssertionError('%s 语法错误，棘轮无法分析：%s' % (rel, e))
    return all_v


def load_baseline():
    """读取基线指纹集合（纯文本，一行一个；`#` 开头为注释）。

    刻意不用 JSON：指纹里会原样出现引号/反斜杠，纯文本省掉一层转义，
    人工复核与 diff 都更直观。
    """
    out = set()
    with open(BASELINE_FILE, encoding='utf-8') as fh:
        for line in fh:
            line = line.rstrip('\n')
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            out.add(line)
    return out


def _unquoted_shell_metachars(cmd):
    """返回命令串里**未被单/双引号包裹**的 shell 元字符（双引号内的 `$`/反引号也算）。"""
    bad = []
    quote = None
    i = 0
    while i < len(cmd):
        ch = cmd[i]
        if quote == _SQUOTE:
            if ch == _SQUOTE:
                quote = None
            i += 1
            continue
        if quote == _DQUOTE:
            if ch == _BACKSLASH:
                i += 2
                continue
            if ch == _DQUOTE:
                quote = None
                i += 1
                continue
            if ch in '$' + chr(96):  # 双引号内仍会展开
                bad.append(ch)
            i += 1
            continue
        if ch in _SQUOTE + _DQUOTE:
            quote = ch
            i += 1
            continue
        if ch == _BACKSLASH:
            i += 2
            continue
        if ch in _SHELL_METACHARS:
            bad.append(ch)
        i += 1
    return bad


# ---------------------------------------------------------------------------
# 规则引擎自证夹具（守卫自身也要「真能失败」）
# ---------------------------------------------------------------------------
_GOOD_FIXTURE = '''
def ok(path):
    q = yf.shlexQuote(path)
    yf.execShell("cd " + q + " && ls")
    yf.execShell("lsof " + yf.shlexQuote(path) + " 2>/dev/null")
    yf.safeExecShell(['chattr', '-i', path])
    yf.execShell("ls -l /tmp")
'''

_BAD_FIXTURE = '''
def bad(path, name):
    yf.execShell("chattr -i " + path)
    yf.execShell("lsof '%s' 2>/dev/null" % path)
    yf.execShell(f"chown -R www:www {path}")
    yf.execShell("echo {}".format(name))
    yf.execShell(cmd)
    os.system("kill " + name)
'''

_EXPORT_BAD_FIXTURE = '''
def leak(data):
    out = ''
    for k in data:
        out += 'export ' + k + '="' + data[k] + '"' + chr(10)
    return out
'''


class TestRuleEngineSelfTest(unittest.TestCase):
    """内嵌夹具：正确写法不得误伤，坏写法必须被抓到。"""

    def test_01_good_forms_not_flagged(self):
        v = analyze_source('web/fixture_good.py', _GOOD_FIXTURE)
        self.assertEqual({}, v, '正确写法被误判为违规：%s' % v)

    def test_02_bad_forms_flagged(self):
        v = analyze_source('web/fixture_bad.py', _BAD_FIXTURE)
        rules = sorted(item['rule'] for item in v.values())
        self.assertEqual(5, rules.count('inline_bare_concat'),
                         '五个现拼表达式都该被抓到：%s' % v)
        self.assertEqual(1, rules.count('bare_variable'), '裸变量该被抓到：%s' % v)

    def test_03_export_doublequote_flagged(self):
        v = analyze_source('web/fixture_export.py', _EXPORT_BAD_FIXTURE)
        self.assertTrue(any(i['rule'] == 'export_doublequote' for i in v.values()),
                        '`export k="v"` 未被抓到：%s' % v)


# ---------------------------------------------------------------------------
# 棘轮本体
# ---------------------------------------------------------------------------
class TestShellConcatRatchet(unittest.TestCase):

    def test_10_no_new_violations(self):
        known = load_baseline()
        current = collect_violations()
        new = sorted(set(current) - known)
        self.assertEqual([], new, '发现 %d 处**新增** shell 裸拼（棘轮只减不增）：%s'
                         % (len(new), new))

    def test_11_dnsapi_export_rule_baseline_empty(self):
        """`export k="v"` 形态必须零残留（dnsapi 注入的根因）。"""
        current = collect_violations()
        hits = {k: v for k, v in current.items() if v['rule'] == 'export_doublequote'}
        self.assertEqual({}, hits, '仍有 export 双引号插值：%s' % hits)
        self.assertEqual([], [k for k in load_baseline()
                              if '::export_doublequote::' in k],
                         '基线里不允许登记 export_doublequote')

    def test_12_scan_scope_covered(self):
        """防止「扫描器坏了所以永远绿」：必须真的扫到已知文件与已知点。"""
        current = collect_violations()
        self.assertGreater(len(current), 30, '扫到的违规数异常偏少，疑似扫描失效：%d'
                           % len(current))
        files = {k.split('::')[0] for k in current}
        for must in ('web/utils/site.py', 'web/utils/file.py', 'panel_tools.py'):
            self.assertIn(must, files, '扫描范围漏了 %s' % must)

    def test_13_baseline_matches_current_rule_set(self):
        for key in load_baseline():
            rule = key.split('::')[2]
            self.assertIn(rule, ('inline_bare_concat', 'bare_variable'),
                          '基线含未知规则：%s' % key)


# ---------------------------------------------------------------------------
# 定点守卫：本轮已修的点，回退即红
# ---------------------------------------------------------------------------
def _load_dnsapi_export_var():
    """按 AST 抽出 `getDnsapiExportVar` 与其依赖的 `_DNSAPI_KEY_RE` 单独编译。"""
    tree = ast.parse(_read(SITE_PY))
    keep = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, 'id', '') == '_DNSAPI_KEY_RE' for t in node.targets):
            keep.append(node)
    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'getDnsapiExportVar':
            method = node
            break
    if method is None or not keep:
        raise AssertionError('site.py 结构变了，守卫需同步：缺 getDnsapiExportVar/_DNSAPI_KEY_RE')
    keep.append(method)

    class _FakeYf:
        shlexQuote = staticmethod(real_yf.shlexQuote)

    ns = {'re': re, 'yf': _FakeYf()}
    exec(compile(ast.Module(body=keep, type_ignores=[]), SITE_PY, 'exec'), ns)
    return ns['getDnsapiExportVar']


def _call_dnsapi(data):
    return _load_dnsapi_export_var()(None, data)


class TestDnsapiExportFix(unittest.TestCase):
    """`/site/set_dnsapi` 写入的键值不得成为 root 命令注入。"""

    MALICIOUS = {
        'CF_Token': '"; touch /tmp/yf_pwned; echo "',
        'CF_Key': '$(touch /tmp/yf_pwned)',
        'CF_Email': '`touch /tmp/yf_pwned`',
        'CF_Zone_ID': 'a b',
        'CF_Account_ID': "it's a token",
    }

    def test_20_values_are_shell_quoted(self):
        out = _call_dnsapi(dict(self.MALICIOUS))
        self.assertTrue(out, '应至少导出一个变量')
        for line in out.rstrip('\n').split('\n'):
            m = re.match(r'^export ([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
            self.assertIsNotNone(m, '导出行不是合法标识符/键值：%r' % line)
            val = m.group(2)
            self.assertTrue(val.startswith("'") and val.endswith("'"),
                            '值未经单引号引用（双引号内 $()/反引号仍展开）：%r' % line)
            self.assertEqual([], _unquoted_shell_metachars(val),
                             '值里仍有未引用的 shell 元字符：%r' % line)

    def test_24_newline_value_stays_quoted(self):
        out = _call_dnsapi({'CF_Zone_ID': 'a\nb'})
        self.assertEqual("export CF_Zone_ID='a\nb'\n", out,
                         '含换行的值必须仍被单引号包住：%r' % out)
        val = out[len('export CF_Zone_ID='):].rstrip('\n')
        self.assertTrue(val.startswith("'") and val.endswith("'"),
                        '换行值逃出了引用：%r' % out)

    def test_21_malicious_keys_dropped(self):
        out = _call_dnsapi({'x;touch /tmp/yf_pwned': 'v', 'CF_Token': 'v'})
        self.assertNotIn('x;touch', out)
        self.assertIn('export CF_Token=', out)

    def test_22_roundtrip_through_real_shell(self):
        """把生成的串丢进真 shell：恶意载荷不得执行（POSIX；Windows 跳过）。"""
        if os.name == 'nt':
            self.skipTest('真机 shell 语义仅 POSIX')
        import subprocess
        import tempfile
        marker = os.path.join(tempfile.mkdtemp(prefix='yf_dnsapi_'), 'pwned')
        data = {'CF_Token': '$(touch %s)' % marker, 'CF_Key': '`touch %s`' % marker}
        script = _call_dnsapi(data) + ':\n'
        subprocess.run(['bash', '-c', script], capture_output=True, timeout=30)
        self.assertFalse(os.path.exists(marker), 'dnsapi 载荷在真 shell 里被执行了')

    def test_23_createacmedns_quotes_dnspai(self):
        tree = ast.parse(_read(SITE_PY))
        target = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'createAcmeDns':
                target = node
                break
        self.assertIsNotNone(target, 'site.py 结构变了：缺 createAcmeDns')
        src = _read(SITE_PY)
        bad = []
        for n in ast.walk(target):
            if not (isinstance(n, ast.Name) and n.id == 'dnspai'):
                continue
            inside_quote = any(
                isinstance(p, ast.Call) and _is_quote_call(p.func)
                and any(x is n for x in ast.walk(p))
                for p in ast.walk(target))
            inside_concat = any(
                isinstance(p, (ast.BinOp, ast.JoinedStr))
                and any(x is n for x in ast.walk(p))
                for p in ast.walk(target))
            if inside_concat and not inside_quote:
                bad.append(n.lineno)
        self.assertEqual([], bad, 'createAcmeDns 里 dnspai 未过 shlexQuote：行 %s' % bad)


class TestManualQuoteConvergence(unittest.TestCase):
    """手工 `path.replace("'", "'\\''")` 统一收敛到 `yf.shlexQuote`。"""

    def test_30_no_manual_quote_idiom(self):
        # 手工写法是 `path.replace(` + 双引号 + 单引号 + 双引号 + 逗号
        idiom = '.replace(' + _DQUOTE + _SQUOTE + _DQUOTE + ','
        offenders = []
        for path in _iter_py_files():
            rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
            if idiom in _read(path):
                offenders.append(rel)
        self.assertEqual([], offenders,
                         '仍有手工单引号转义，应改用 yf.shlexQuote：%s' % offenders)

    def test_31_get_occupying_process_has_no_bare_concat(self):
        tree = ast.parse(_read(FILE_PY))
        func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'getOccupyingProcess':
                func = node
                break
        self.assertIsNotNone(func, 'file.py 结构变了：缺 getOccupyingProcess')
        rel = 'web/utils/file.py'
        v = analyze_source(rel, _read(FILE_PY))
        hits = [k for k in v if '::getOccupyingProcess::inline_bare_concat::' in k]
        self.assertEqual([], hits, 'getOccupyingProcess 又出现裸拼：%s' % hits)


if __name__ == '__main__':
    # 生成/刷新基线：`python testsuite/test_shell_concat_ratchet.py --print-baseline`
    if '--print-baseline' in sys.argv:
        print('# P0-1（web 侧）shell 裸拼棘轮基线：只减不增。')
        print('# 由 testsuite/test_shell_concat_ratchet.py --print-baseline 生成。')
        print('# 格式：<相对路径>::<函数名>::<规则>::<表达式>')
        print('# 扫描范围：web/**/*.py + panel_tools.py + panel_task.py')
        for fp in sorted(collect_violations()):
            print(fp)
        sys.exit(0)
    unittest.main()
