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

偿还计划（P2-12）：基线只是「不许变坏」，本文件另配 `REDUCTION_PLAN` —— 一张写死
上限的年度下降表（快照档 → 70% → 40% → 清零），由
`testsuite/test_shell_debt_reduction_plan.py` 按日期判定当前档并断言实际违规数不超标。

扫描范围（两侧各一份基线，由 `SCAN_SCOPES` 驱动，守卫同时覆盖）：
  * web 侧：`web/` + `panel_tools.py` + `panel_task.py` -> `scripts/shell_concat_baseline.txt`
  * plugins 侧：`plugins/`（跳过 `plugins/待审核/` 与 `文档/待审核插件/`，
    那批判定当前不可达，由 p2-miscsec 统一加文档警示）
    -> `scripts/shell_concat_baseline_plugins.txt`
刻意**排除** `testsuite/`、`test/`，否则守卫自己的夹具会被自己命中。
"""
import ast
import datetime
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
MYSQL_PY = os.path.join(project_dir, 'plugins', 'mysql', 'index.py')
MARIADB_PY = os.path.join(project_dir, 'plugins', 'mariadb', 'index.py')
#: 棘轮基线放在 `scripts/`，与 `scripts/code_quality_baseline.json` 保持一致。
#: 两侧各一份（web 侧 / plugins 侧），由 `SCAN_SCOPES` 分别驱动。
BASELINE_FILE = os.path.join(project_dir, 'scripts', 'shell_concat_baseline.txt')
PLUGINS_BASELINE_FILE = os.path.join(project_dir, 'scripts',
                                     'shell_concat_baseline_plugins.txt')

SCAN_DIRS = ['web']
SCAN_ROOT_FILES = ['panel_tools.py', 'panel_task.py']
EXCLUDE_DIRS = {'__pycache__', 'node_modules', 'test', 'testsuite', '参考', '文档',
                'cl_tasks', '.git', 'data', 'logs', 'tmp', '.workbuddy-ai'}
#: `plugins/待审核/` 与 `文档/待审核插件/` 判定当前不可达（未安装），本轮不扫描、不登记。
PLUGINS_EXCLUDE_DIRS = EXCLUDE_DIRS | {'待审核'}

#: 扫描范围 = (名称, 扫描目录, 根文件, 额外排除目录, 基线文件)。
SCAN_SCOPES = (
    {'name': 'web', 'dirs': SCAN_DIRS, 'root_files': SCAN_ROOT_FILES,
     'exclude': EXCLUDE_DIRS, 'baseline': BASELINE_FILE},
    {'name': 'plugins', 'dirs': ['plugins'], 'root_files': [],
     'exclude': PLUGINS_EXCLUDE_DIRS, 'baseline': PLUGINS_BASELINE_FILE},
)


# ---------------------------------------------------------------------------
# 技术债偿还计划（P2-12）：基线只「防增」，这里补上「什么时候必须还清」
# ---------------------------------------------------------------------------
# 为什么要有这张表：只防增的棘轮有个致命的使用方式 —— 基线一旦不再缩小，
# 「存量裸拼」就变成了永久豁免。所以除了「新指纹不得新增」（test_10，机制不动），
# 再加一条**带日期的下降曲线**：到了某个日期，实际违规数必须已经降下来。
#
#: 每档 = (截止日期 'YYYY-MM-DD', web 段允许上限, 插件段允许上限)。
#:
#: **上限值一律是写死的整数，不在断言里现算**——现算（如 `int(baseline * 0.7)`）
#: 会永远跟着基线走，等于没有约束；改这张表必须是一次显式的人工提交。
#:
#: 数值口径（2026-10-22 实测；用 `--print-baseline web` / `--print-baseline plugins`
#: 跑本文件可复现）：
#:   * 第一档 = **今天实测的违规数** = 两份基线文件的条目数（web 81 / 插件 316）；
#:     两者必须一致，由 `test_shell_debt_reduction_plan.py` 用例 3 双向校验；
#:   * 第二档 ≈ 第一档的 70%（81×0.7=56.7→57；316×0.7=221.2→221）；
#:   * 第三档 ≈ 第一档的 40%（81×0.4=32.4→32；316×0.4=126.4→126）；
#:   * 第四档必须为 0（终点：存量清零，此后基线文件只允许剩注释）。
REDUCTION_PLAN = (
    ('2026-10-22', 81, 316),    # 基线快照日（实测 81 / 316）
    ('2027-06-30', 57, 221),    # ≈ 基线的 70%
    ('2027-12-31', 32, 126),    # ≈ 基线的 40%
    ('2028-06-30', 0, 0),       # 终点：清零
)

#: 计划表里各扫描段占的那一列（与 `REDUCTION_PLAN` 元组下标一一对应）。
PLAN_LIMIT_INDEX = {'web': 1, 'plugins': 2}


def _parse_plan_date(text):
    """`'YYYY-MM-DD'` -> `datetime.date`（格式错直接抛，要求计划表可读）。"""
    year, month, day = (int(x) for x in str(text).split('-'))
    return datetime.date(year, month, day)


def plan_tier_for(today=None):
    """返回「今天适用的那一档」`(截止日期, web 上限, 插件上限)`。

    判定口径（规则写死在这里，**不在断言里现算**）：
      1. 取**最后一个「截止日期 <= 今天」的档** —— 即「已经到期、到今天就该达到的那一档」；
         到期日**当天**就按该档约束，并且一直按它继续约束到下一个到期日；
      2. 今天早于第一档（计划尚未生效）时取第一档：第一档就是基线快照档，
         只有更严、不会更松；
      3. 「截止日期」保持字面含义（到此日必须达标），所以到期日**之前**仍适用上一档 ——
         否则会出现「计划生效第二天就要求跳到 70% 档」的时间炸弹，那不是还款计划而是断头台。
    """
    day = datetime.date.today() if today is None else today
    if isinstance(day, str):
        day = _parse_plan_date(day)
    tier = REDUCTION_PLAN[0]
    for cand in REDUCTION_PLAN:
        if _parse_plan_date(cand[0]) <= day:
            tier = cand
    return tier


def plan_limit_for(scope_name, today=None):
    """该扫描段在「今天适用的那一档」里的允许上限（整数）。"""
    return plan_tier_for(today)[PLAN_LIMIT_INDEX[scope_name]]


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


def _iter_py_files(dirs=None, root_files=None, exclude=None):
    dirs = SCAN_DIRS if dirs is None else dirs
    root_files = SCAN_ROOT_FILES if root_files is None else root_files
    exclude = EXCLUDE_DIRS if exclude is None else exclude
    for base in dirs:
        abs_base = os.path.join(ROOT, base)
        if not os.path.isdir(abs_base):
            continue
        for root, subdirs, files in os.walk(abs_base):
            subdirs[:] = [d for d in subdirs if d not in exclude]
            for fn in sorted(files):
                if fn.endswith('.py'):
                    yield os.path.join(root, fn)
    for fn in root_files:
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


def collect_violations(dirs=None, root_files=None, exclude=None):
    all_v = {}
    for path in _iter_py_files(dirs, root_files, exclude):
        rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
        try:
            all_v.update(analyze_source(rel, _read(path)))
        except SyntaxError as e:
            raise AssertionError('%s 语法错误，棘轮无法分析：%s' % (rel, e))
    return all_v


def _scope_violations(scope):
    return collect_violations(scope['dirs'], scope['root_files'], scope['exclude'])


def load_baseline(path=None):
    """读取基线指纹集合（纯文本，一行一个；`#` 开头为注释）。

    刻意不用 JSON：指纹里会原样出现引号/反斜杠，纯文本省掉一层转义，
    人工复核与 diff 都更直观。
    """
    path = BASELINE_FILE if path is None else path
    out = set()
    with open(path, encoding='utf-8') as fh:
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
        for scope in SCAN_SCOPES:
            known = load_baseline(scope['baseline'])
            current = _scope_violations(scope)
            new = sorted(set(current) - known)
            self.assertEqual([], new, '[%s] 发现 %d 处**新增** shell 裸拼（棘轮只减不增）：%s'
                             % (scope['name'], len(new), new))

    def test_11_dnsapi_export_rule_baseline_empty(self):
        """`export k="v"` 形态必须零残留（dnsapi 注入的根因）。"""
        for scope in SCAN_SCOPES:
            current = _scope_violations(scope)
            hits = {k: v for k, v in current.items() if v['rule'] == 'export_doublequote'}
            self.assertEqual({}, hits, '[%s] 仍有 export 双引号插值：%s' % (scope['name'], hits))
            self.assertEqual([], [k for k in load_baseline(scope['baseline'])
                                  if '::export_doublequote::' in k],
                             '[%s] 基线里不允许登记 export_doublequote' % scope['name'])

    def test_12_scan_scope_covered(self):
        """防止「扫描器坏了所以永远绿」：必须真的扫到已知文件与已知点。"""
        must = {
            'web': ('web/utils/site.py', 'web/utils/file.py', 'panel_tools.py'),
            'plugins': ('plugins/mysql/index.py', 'plugins/mariadb/index.py',
                        'plugins/redis/index.py'),
        }
        for scope in SCAN_SCOPES:
            current = _scope_violations(scope)
            self.assertGreater(len(current), 30, '[%s] 扫到的违规数异常偏少，疑似扫描失效：%d'
                               % (scope['name'], len(current)))
            files = {k.split('::')[0] for k in current}
            for f in must[scope['name']]:
                self.assertIn(f, files, '[%s] 扫描范围漏了 %s' % (scope['name'], f))

    def test_13_baseline_matches_current_rule_set(self):
        for scope in SCAN_SCOPES:
            for key in load_baseline(scope['baseline']):
                rule = key.split('::')[2]
                self.assertIn(rule, ('inline_bare_concat', 'bare_variable'),
                              '[%s] 基线含未知规则：%s' % (scope['name'], key))


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


# ---------------------------------------------------------------------------
# 定点守卫（plugins 侧）：`drop user ...@'<hostname>'` 回退即红
# ---------------------------------------------------------------------------
def _find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


class TestPluginsHostnameQuoteFix(unittest.TestCase):
    """mysql/mariadb 的 `drop user ...@'<hostname>'` 必须过 shell 引用 + SQL 转义。

    hostname 来自 `hostname` 命令输出，旧实现裸拼进 `-e "drop user ''@'<hostname>'"`：
    双引号内 `"`/`$()`/反引号仍会展开 → root 命令注入。这里只做 AST 定点断言
    （棘轮只看 shell 调用首参，看不到 `drop_hostname` 内部的构造过程，所以必须另设守卫）。
    """
    #: (文件, 含 drop user 拼接的函数)
    TARGETS = (
        (MYSQL_PY, ('initMysqlPwd', 'initMysql8Pwd')),
        (MARIADB_PY, ('initMariaDbPwd',)),
    )

    def test_40_hostname_not_bare_in_string_expr(self):
        offenders = []
        for path, _funcs in self.TARGETS:
            tree = ast.parse(_read(path))
            for node in _outermost_string_exprs(tree):
                if not any(isinstance(n, ast.Name) and n.id == 'hostname'
                           for n in ast.walk(node)):
                    continue
                quoted = _quote_wrapped_ids(node)
                if any(isinstance(n, ast.Name) and n.id == 'hostname'
                       and id(n) not in quoted for n in ast.walk(node)):
                    offenders.append('%s:%d' % (os.path.relpath(path, ROOT), node.lineno))
        self.assertEqual([], offenders,
                         'hostname 又裸拼进字符串表达式（应 shlexQuote/SQL 转义）：%s' % offenders)

    def test_41_drop_user_cmd_is_shell_quoted(self):
        """`drop_hostname`/`drop_root_hostname` 的构造必须含 yf.shlexQuote。"""
        bad = []
        for path, funcs in self.TARGETS:
            tree = ast.parse(_read(path))
            rel = os.path.relpath(path, ROOT)
            for fname in funcs:
                func = _find_func(tree, fname)
                self.assertIsNotNone(func, '%s 结构变了：缺 %s' % (rel, fname))
                for n in ast.walk(func):
                    if not isinstance(n, ast.Assign):
                        continue
                    tgt = [t.id for t in n.targets if isinstance(t, ast.Name)]
                    if not any(t in ('drop_hostname', 'drop_root_hostname') for t in tgt):
                        continue
                    if not _expr_has_quote(n.value):
                        bad.append('%s::%s:%d' % (rel, fname, n.lineno))
        self.assertEqual([], bad, 'drop user 命令未过 yf.shlexQuote：%s' % bad)

    def test_42_no_outer_doublequote_sql_arg(self):
        """旧形态特征：`-e "drop user ...` —— 不允许再把 SQL 塞进双引号参数（注释行不计）。"""
        needle = '-e ' + _DQUOTE + 'drop user '
        offenders = []
        for p, _f in self.TARGETS:
            code = '\n'.join(line for line in _read(p).splitlines()
                             if not line.lstrip().startswith('#'))
            if needle in code:
                offenders.append(os.path.relpath(p, ROOT))
        self.assertEqual([], offenders,
                         '仍有双引号包裹的 drop user 参数（hostname 可逃逸）：%s' % offenders)

    def test_43_hostname_sql_escaped(self):
        """hostname 进 SQL 前必须 `replace("'", "''")`（否则单引号可破 SQL）。"""
        bad = []
        for path, funcs in self.TARGETS:
            tree = ast.parse(_read(path))
            rel = os.path.relpath(path, ROOT)
            for fname in funcs:
                func = _find_func(tree, fname)
                self.assertIsNotNone(func, '%s 结构变了：缺 %s' % (rel, fname))
                ok = False
                for n in ast.walk(func):
                    if not (isinstance(n, ast.Assign) and any(
                            isinstance(t, ast.Name) and t.id == 'sql_hostname'
                            for t in n.targets)):
                        continue
                    v = n.value
                    if (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute)
                            and v.func.attr == 'replace' and len(v.args) == 2
                            and all(isinstance(x, ast.Constant) for x in v.args)
                            and v.args[0].value == "'" and v.args[1].value == "''"):
                        ok = True
                if not ok:
                    bad.append('%s::%s' % (rel, fname))
        self.assertEqual([], bad, 'hostname 未做 SQL 层单引号转义：%s' % bad)


if __name__ == '__main__':
    # 生成/刷新基线：`python testsuite/test_shell_concat_ratchet.py --print-baseline [web|plugins]`
    if '--print-baseline' in sys.argv or '--write-baseline' in sys.argv:
        flag = '--print-baseline' if '--print-baseline' in sys.argv else '--write-baseline'
        idx = sys.argv.index(flag)
        rest = [a for a in sys.argv[idx + 1:] if not a.startswith('-')]
        scope_name = rest[0] if rest else 'web'
        scope = {s['name']: s for s in SCAN_SCOPES}[scope_name]
        lines = [
            '# P0-1（%s 侧）shell 裸拼棘轮基线：只减不增。' % scope_name,
            '# 由 testsuite/test_shell_concat_ratchet.py %s %s 生成。' % (flag, scope_name),
            '# 格式：<相对路径>::<函数名>::<规则>::<表达式>',
        ]
        lines.extend(sorted(_scope_violations(scope)))
        if flag == '--write-baseline':
            with open(scope['baseline'], 'w', encoding='utf-8', newline='\n') as fh:
                fh.write('\n'.join(lines) + '\n')
            print('wrote %d lines -> %s' % (len(lines), scope['baseline']))
        else:
            print('\n'.join(lines))
        sys.exit(0)
    unittest.main()
