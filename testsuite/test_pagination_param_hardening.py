# coding: utf-8
"""分页参数容错回归守卫(本轮父 agent 复核 A03 时发现并修复)。

缺陷:分页参数的 int() 收口有两处**未容错**,任何页面传非数字分页参数即 500:

1. `web/core/yf/system.py::getPageObject` 直接 `int(args['p'])` / `int(args['row'])`
   / `int(args['count'])`。它是**全仓 15 处分页调用的唯一咽喉**(dashboard/files/
   logs/setting/site/crontab/firewall/plugin/task 全走 `yf.getPage` → 这里),
   所以一处不安全 = 所有分页端点都对 `p=abc` 500;而且它在 `page.Page` 的越界夹取
   **之前**执行(先崩,夹取根本没机会生效)。
2. `web/admin/files/files.py::get_dir` 的 `int(page)` / `int(row)`(表单原值)。
   真机实测 `POST /files/get_dir` 带 `p=abc` → ValueError → 500。

修复口径:在咽喉处统一容错 + 夹下界(row=0 会让 `__GetCountPage` 除零),
页码上界仍由 `page.Page` 夹到 [1, 总页数]。

断言策略:直接调真实的 `getPageObject`,覆盖非法/越界/合法三类输入,并从分页 HTML
的 `Pnumber` 片段解析出「当前页/总页数」(Page 的页码属性是名字改写私有,不可直接读;
row 是公开的 `ROW`)。路由层用 AST 断言 `int(page)`/`int(row)` 一定在 try 内(而不是
禁止出现 —— 修好后的正确写法仍是 `max(1, int(page))`,只是被 try 包住)。
"""
import ast
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('page_param')

import core.yf as yf  # noqa: E402

_PNUMBER = re.compile(r"Pnumber'>(\d+)/(\d+)<")


def _pages(html):
    """从分页 HTML 解析 (当前页, 总页数)。"""
    m = _PNUMBER.search(html)
    assert m, '分页 HTML 未见 Pnumber 片段: %r' % html[:200]
    return int(m.group(1)), int(m.group(2))


class PageParamToleranceTest(unittest.TestCase):
    """咽喉处:非法分页参数不得抛异常,且要归一为可用值。"""

    def _obj(self, args):
        return yf.getPageObject(args, '1,2,3,4,5,6,7,8')

    def test_01_non_numeric_p_falls_back_to_first(self):
        html, pg = self._obj({'count': 100, 'p': 'abc', 'row': 10, 'tojs': 'getFiles'})
        cur, total = _pages(html)
        self.assertEqual(cur, 1)
        self.assertEqual(total, 10)

    def test_02_non_numeric_row_falls_back_to_default(self):
        html, pg = self._obj({'count': 100, 'p': 1, 'row': 'abc', 'tojs': 'getFiles'})
        self.assertEqual(pg.ROW, 10)
        _pages(html)

    def test_03_non_numeric_count_does_not_raise(self):
        html, pg = self._obj({'count': 'abc', 'p': 1, 'row': 10, 'tojs': 'getFiles'})
        cur, total = _pages(html)
        self.assertEqual(cur, 1)
        self.assertGreaterEqual(total, 0)

    def test_04_row_zero_does_not_divide_by_zero(self):
        # row=0 会让 __GetCountPage 做 ceil(count/0.0) -> ZeroDivisionError
        html, pg = self._obj({'count': 100, 'p': 1, 'row': 0, 'tojs': 'getFiles'})
        self.assertGreaterEqual(pg.ROW, 1)
        _pages(html)

    def test_05_negative_row_clamped(self):
        html, pg = self._obj({'count': 100, 'p': 1, 'row': -5, 'tojs': 'getFiles'})
        self.assertGreaterEqual(pg.ROW, 1)
        _pages(html)

    def test_06_negative_count_clamped(self):
        html, pg = self._obj({'count': -3, 'p': 1, 'row': 10, 'tojs': 'getFiles'})
        cur, total = _pages(html)
        self.assertEqual(cur, 1)
        self.assertGreaterEqual(total, 0)

    def test_07_huge_page_clamped_to_last_and_html_bounded(self):
        html, pg = self._obj({'count': 100, 'p': 99999, 'row': 10, 'tojs': 'getFiles'})
        cur, total = _pages(html)
        self.assertEqual(cur, total, '越界页码必须夹到最后一页而不是离开范围')
        # 分页 HTML 不得随 p 放大(O(p) 放大是 A11 修过的同类问题)
        self.assertLess(len(html), 20000)

    def test_08_legit_values_unchanged(self):
        html, pg = self._obj({'count': 100, 'p': 3, 'row': 10, 'tojs': 'getFiles'})
        cur, total = _pages(html)
        self.assertEqual(cur, 3)
        self.assertEqual(total, 10)
        self.assertEqual(pg.ROW, 10)

    def test_09_float_string_not_truncated(self):
        # '1.5' 若被 int() 直接吃会 ValueError;归一为第 1 页而不是猜测截断
        html, pg = self._obj({'count': 100, 'p': '1.5', 'row': 10, 'tojs': 'getFiles'})
        cur, _ = _pages(html)
        self.assertEqual(cur, 1)

    def test_10_getpage_wrapper_still_returns_html(self):
        html = yf.getPage({'count': 100, 'p': 'abc', 'row': 'abc', 'tojs': 'getFiles'})
        self.assertIsInstance(html, str)
        self.assertGreater(len(html), 0)

    def test_11_missing_keys_use_defaults(self):
        # 只给 count 也要能出分页(历史上缺 row/p 会 KeyError/TypeError)
        html, pg = self._obj({'count': 50})
        cur, total = _pages(html)
        self.assertEqual(cur, 1)
        self.assertEqual(total, 5)


class GetDirRouteTest(unittest.TestCase):
    """路由层:get_dir 对表单分页值的 int() 必须在 try 内。"""

    def _route_source(self):
        with open(os.path.join(WEB, 'admin', 'files', 'files.py'), encoding='utf-8') as fh:
            return fh.read()

    def _get_dir_fn(self):
        tree = ast.parse(self._route_source())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'get_dir':
                return node
        return None

    def test_12_get_dir_int_calls_are_guarded(self):
        fn = self._get_dir_fn()
        self.assertIsNotNone(fn, 'get_dir 路由不存在')

        # 收集被 try 包住的 int() 调用行号
        guarded_lines = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Try):
                for stmt in node.body:
                    for sub in ast.walk(stmt):
                        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                                and sub.func.id == 'int'):
                            guarded_lines.add(sub.lineno)

        unguarded = []
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'int' and node.args):
                arg = ast.unparse(node.args[0])
                if arg in ('page', 'row') and node.lineno not in guarded_lines:
                    unguarded.append((node.lineno, arg))
        self.assertEqual(unguarded, [],
                         'get_dir 仍有未包 try 的 int(表单值): %s' % unguarded)

    def test_13_get_dir_clamps_after_parsing(self):
        src = self._route_source()
        fn_src = src.split('def get_dir():', 1)[1].split('\ndef ', 1)[0]
        self.assertIn('max(1, int(page))', fn_src)
        self.assertIn('max(1, int(row))', fn_src)


# ---------------------------------------------------------------------------
# P1-6：插件层（mysql / mariadb / postgresql）的分页参数 / tojs / type 容错
#
# 缺陷：postgresql 早有 `_parsePageArgs` 容错范式与 `args.get('tojs', 默认)` 兜底，
# mysql / mariadb 未跟进——`page=abc` → int() ValueError、负页码 → SQL 报错、
# 缺 tojs → KeyError、缺/非法 type → KeyError/ValueError，插件直接抛 traceback，
# 前端拿到非 JSON（等效 500）。
#
# 怎么测（为什么不用 import index.py）：`plugins/*/index.py` 顶层会 `os.chdir()`
# 到 `web/` 并拉起面板运行时（`core.yf` 等），直接 import 既慢又脏。所以这里用
# `ast` 把被测函数**原样抽出来 exec**（顶层不执行），既测的是真代码，又零副作用；
# 另用 AST 断言源码里已无裸 `int(args[...])` / 裸 `args['tojs']`。
#
# `_parsePageArgs` 为什么仍是三个插件各留一份（而不是抽到 plugins/lib/ 共用）：
# `plugins/<name>/` 下的每个目录都会被 `test_repo_contract.py::plugin_names()` 当成
# 一个插件（`EXPECTED_PLUGIN_COUNT == 36`），新增 `plugins/lib/` 会让那条既有契约
# 断言变红，而红线要求不放宽既有断言；抽到 `web/` 则是改运行时代码结构。因此按
# 「与 postgresql 同名同签名同语义」各自落一份，并由本用例锁死三份 AST 完全一致
# （任何单侧重写/漂移都会红），效果等同共用组件。
# ---------------------------------------------------------------------------

PLUGIN_INDEX = {
    'mysql': os.path.join(ROOT, 'plugins', 'mysql', 'index.py'),
    'mariadb': os.path.join(ROOT, 'plugins', 'mariadb', 'index.py'),
    'postgresql': os.path.join(ROOT, 'plugins', 'postgresql', 'index.py'),
}
PLUGIN_JS = {
    'mysql': os.path.join(ROOT, 'plugins', 'mysql', 'js', 'mysql.js'),
    'mariadb': os.path.join(ROOT, 'plugins', 'mariadb', 'js', 'mariadb.js'),
    'postgresql': os.path.join(ROOT, 'plugins', 'postgresql', 'js', 'postgresql.js'),
}

#: 三插件必须给出**相同**兜底结果的一组非法入参：(说明, args, 额外调参, 期望 (page, size))
PLUGIN_PAGE_CASES = [
    ('非数字 page/page_size', {'page': 'abc', 'page_size': 'xyz'}, {}, (1, 10)),
    ('负页码 / 负每页条数', {'page': '-5', 'page_size': '-1'}, {}, (1, 10)),
    ('超大 page / page_size', {'page': '999999999', 'page_size': '999999999'}, {},
     (999999999, 100)),
    ('缺参（完全没有 page/page_size/tojs）', {}, {}, (1, 10)),
    ('空串 page / page_size', {'page': '', 'page_size': ''}, {}, (1, 10)),
    ('None 值', {'page': None, 'page_size': None}, {}, (1, 10)),
    ('空白串 page_size', {'page': ' 2 ', 'page_size': '   '}, {}, (2, 10)),
    ('浮点串（不猜截断，回默认）', {'page': '1.5', 'page_size': '2.5'}, {}, (1, 10)),
    ('def_size=5 时非法值', {'page': 'abc', 'page_size': 'xyz'}, {'def_size': 5}, (1, 5)),
    ('def_size=5 时缺参', {}, {'def_size': 5}, (1, 5)),
    ('合法值不受影响', {'page': '3', 'page_size': '5'}, {}, (3, 5)),
    ('max_size 按调用处封顶', {'page': '1', 'page_size': '500'}, {'max_size': 20}, (1, 20)),
]

#: 每处 tojs 的上下文默认值（必须按函数各自的前端回调取，不能统一写死一个）
PLUGIN_TOJS_DEFAULTS = {
    'mysql': [
        ('binLogList', 'myBinLogsRender'),
        ('getSlaveSSHList', 'getSlaveSSHPage'),
        ('getSlaveSyncUserList', 'getSlaveSyncUserPage'),
    ],
    'mariadb': [
        ('binLogList', 'myBinLogsRender'),
        ('getSlaveSSHList', 'getSlaveSSHPage'),
        ('getSlaveSyncUserList', 'getSlaveSyncUserPage'),
    ],
    'postgresql': [
        ('getSlaveSSHList', 'getSlaveSSHPage'),
    ],
}


def _plugin_src(plugin):
    with open(PLUGIN_INDEX[plugin], 'r', encoding='utf-8') as fh:
        return fh.read()


def _plugin_fn(plugin, name):
    """取插件 index.py 的顶层函数节点（不 import 插件：它顶层就 chdir + 拉运行时）。"""
    for node in ast.parse(_plugin_src(plugin)).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError('%s/index.py 里找不到 %s()，守卫需同步' % (plugin, name))


def _exec_fn(plugin, name, ns):
    """把插件里的某个函数原样编译进给定的命名空间（等价于只执行这一个 def）。"""
    node = _plugin_fn(plugin, name)
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 PLUGIN_INDEX[plugin], 'exec'), ns)
    return ns[name]


def _parse_page_args_of(plugin):
    return _exec_fn(plugin, '_parsePageArgs', {})


def _fn_body_dump(func_node):
    """函数 AST 的规范化指纹：跳过文档串（它随插件名/上下文而变），余下必须一致。"""
    body = list(func_node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    node = ast.FunctionDef(name=func_node.name, args=func_node.args, body=body,
                           decorator_list=func_node.decorator_list, returns=None,
                           type_comment=None)
    return ast.dump(ast.fix_missing_locations(node))


def _tojs_default(func_node):
    """函数体里 `xxx.get('tojs', <默认>)` 的默认值；没有则返回 None。"""
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (isinstance(f, ast.Attribute) and f.attr == 'get'):
            continue
        if len(node.args) < 2:
            continue
        key = node.args[0]
        val = node.args[1]
        if isinstance(key, ast.Constant) and key.value == 'tojs' \
                and isinstance(val, ast.Constant):
            return val.value
    return None


class _FakeDb(object):
    """极简连接替身：只记录调用链，返回空结果集（不连真库）。"""

    def __init__(self, calls):
        self.calls = calls

    def execute(self, sql, *rest):
        self.calls.append(('execute', sql))
        return 'ok'

    def field(self, *cols):
        self.calls.append(('field', cols))
        return self

    def where(self, cond, params):
        self.calls.append(('where', cond, params))
        return self

    def select(self):
        self.calls.append(('select',))
        return []

    def find(self):
        self.calls.append(('find',))
        return {}

    def limit(self, value):
        self.calls.append(('limit', value))
        return self

    def order(self, *cols):
        self.calls.append(('order', cols))
        return self

    def count(self):
        self.calls.append(('count',))
        return 0

    def getField(self, name):
        self.calls.append(('getField', name))
        return ''


class _FakeYf(object):
    """只替换「会碰 I/O」的入口；returnJson / getJson 用真实现，好断言真实返回形状。"""

    returnJson = staticmethod(yf.returnJson)
    getJson = staticmethod(yf.getJson)

    def __init__(self):
        #: 每次 getPage() 收到的分页参数（用来断言 tojs 到底落成了什么）
        self.page_args = []

    @staticmethod
    def getInfo(msg, args=()):
        return msg

    def getPage(self, page_args):
        # 只需要“有个字符串”：分页 HTML 本体不是本用例的关注点
        self.page_args.append(dict(page_args))
        return 'page:%s/%s' % (page_args.get('p'), page_args.get('row'))


def _run_get_db_list(plugin, args):
    """跑真 `getDbList()`（三插件同结构）：DB/运行时全用替身。

    返回 (JSON 字符串, 真正拼给 SQL 的 LIMIT 值)。getDbList 是「裸 int() 时代
    page=abc 直接 ValueError」的典型现场，而且拼出的 LIMIT 会原样进 SQL。
    """
    calls = []
    ns = {
        'yf': _FakeYf(),
        'getArgs': (lambda: dict(args)),
        'pSqliteDb': (lambda *a: _FakeDb(calls)),
        'getDbBackupListFunc': (lambda *a: []),
        'getDbPort': (lambda: '3306'),
    }
    _exec_fn(plugin, '_parsePageArgs', ns)
    fn = _exec_fn(plugin, 'getDbList', ns)
    out = fn()
    limits = [c[1] for c in calls if c[0] == 'limit']
    return out, (limits[0] if limits else None)


def _run_list_fn(plugin, name, args):
    """跑真的列表接口（getSlaveSSHList / getSlaveSyncUserList）：DB/运行时全用替身。

    返回 (JSON 字符串, 交给 yf.getPage 的分页参数列表) —— 后者能直接看出
    缺 tojs 时到底回退到了哪个前端回调。
    """
    calls = []
    fake = _FakeYf()
    ns = {
        'yf': fake,
        'getArgs': (lambda: dict(args)),
        'pSqliteDb': (lambda *a: _FakeDb(calls)),
    }
    _exec_fn(plugin, '_parsePageArgs', ns)
    _exec_fn(plugin, 'checkArgs', ns)
    fn = _exec_fn(plugin, name, ns)
    return fn(), fake.page_args


def _run_sync_to_databases(plugin, args):
    """跑真 `syncToDatabases()`：只把 DB/运行时替身注入命名空间，函数体一行不改。"""
    calls = []
    ns = {
        'yf': _FakeYf(),
        'json': json,
        'getArgs': (lambda: dict(args)),
        'pMysqlDb': (lambda *a: _FakeDb(calls)),
        'pSqliteDb': (lambda *a: _FakeDb(calls)),
        'isSqlError': (lambda r: None),
        'toDbBase': (lambda *a: 1),
    }
    _exec_fn(plugin, 'checkArgs', ns)
    fn = _exec_fn(plugin, 'syncToDatabases', ns)
    return fn(), calls


class DbPluginPageArgsTest(unittest.TestCase):
    """三插件：同一组非法分页参数 → 同一份兜底结果，且不抛异常。"""

    def test_14_same_fallback_across_three_plugins(self):
        fns = dict((p, _parse_page_args_of(p)) for p in PLUGIN_INDEX)
        for title, args, kwargs, expect in PLUGIN_PAGE_CASES:
            got = {}
            for plugin, fn in fns.items():
                try:
                    got[plugin] = fn(dict(args), **kwargs)
                except Exception as ex:  # 兜底函数本身绝不允许抛异常
                    self.fail('%s 对「%s」抛了 %s: %s' % (plugin, title, type(ex).__name__, ex))
            self.assertEqual(len(set(got.values())), 1,
                             '三插件对「%s」的兜底结果不一致：%s' % (title, got))
            self.assertEqual(got['mysql'], expect, '「%s」兜底结果不符：%s' % (title, got['mysql']))

    def test_15_falls_back_to_default_size_not_zero(self):
        # 负/零 page_size 若原样进 SQL 会 LIMIT 0 或报错；必须回默认值（不是 1，也不是 0）
        for plugin in PLUGIN_INDEX:
            fn = _parse_page_args_of(plugin)
            self.assertEqual(fn({'page': '1', 'page_size': '0'}), (1, 10),
                             '%s：page_size=0 必须回默认值' % plugin)
            self.assertEqual(fn({'page': '0', 'page_size': '5'}), (1, 5),
                             '%s：page=0 必须夹到 1' % plugin)

    def test_16_parse_page_args_identical_across_plugins(self):
        # 三份实现必须同签名同语义：函数体 AST 完全一致（任一单侧重写/漂移立即红）；
        # 文档串不参与比较（它写着各自插件的上下文），签名与穿迫方式参与。
        dumps = dict((p, _fn_body_dump(_plugin_fn(p, '_parsePageArgs'))) for p in PLUGIN_INDEX)
        self.assertEqual(dumps['mysql'], dumps['postgresql'],
                         'mysql 的 _parsePageArgs 与 postgresql 范式已漂移')
        self.assertEqual(dumps['mariadb'], dumps['postgresql'],
                         'mariadb 的 _parsePageArgs 与 postgresql 范式已漂移')

    def test_17_no_bare_int_on_args_left(self):
        # 静态断言：mysql / mariadb 里 `int(args[` 出现次数必须为 0
        for plugin in ('mysql', 'mariadb'):
            self.assertEqual(_plugin_src(plugin).count('int(args['), 0,
                             '%s/index.py 仍有裸 int(args[...])' % plugin)
        # postgresql 保留原样：AST 层面同样不得有 int(args[...]) 调用（源码里那 2 处
        # 只是注释/文档串在描述历史缺陷，不是代码）
        for plugin in PLUGIN_INDEX:
            tree = ast.parse(_plugin_src(plugin))
            bad = []
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == 'int' and node.args):
                    arg = node.args[0]
                    if (isinstance(arg, ast.Subscript) and isinstance(arg.value, ast.Name)
                            and arg.value.id == 'args'):
                        bad.append(node.lineno)
            self.assertEqual(bad, [], '%s/index.py 仍有 int(args[...])：行 %s' % (plugin, bad))

    def test_18_def_size_matches_postgresql_counterpart(self):
        # getSlaveSSHList 在三个插件里是同一个前端接口，兜底每页条数必须一致（5）
        for plugin in PLUGIN_INDEX:
            fn = _plugin_fn(plugin, 'getSlaveSSHList')
            src = ast.get_source_segment(_plugin_src(plugin), fn)
            self.assertIn('def_size=5', src,
                          '%s：getSlaveSSHList 的 _parsePageArgs 应传 def_size=5' % plugin)

    def test_19_tojs_defaults_per_call_site(self):
        for plugin, expects in PLUGIN_TOJS_DEFAULTS.items():
            defaults = []
            for fname, default in expects:
                got = _tojs_default(_plugin_fn(plugin, fname))
                self.assertEqual(got, default,
                                 '%s::%s 的 tojs 默认值应为 %r，实际 %r' % (plugin, fname, default, got))
                defaults.append(got)
            # 不能统一写死一个：同一插件内 3 处必须各按上下文取（互不相同）
            if len(defaults) > 1:
                self.assertEqual(len(set(defaults)), len(defaults),
                                 '%s 的多处 tojs 默认值被写成了同一个：%s' % (plugin, defaults))

    def test_20_tojs_default_value_exists_in_frontend_js(self):
        # 默认值不能是凭空的字符串：它必须是该插件 JS 里真实存在的回调函数名
        for plugin, expects in PLUGIN_TOJS_DEFAULTS.items():
            with open(PLUGIN_JS[plugin], 'r', encoding='utf-8') as fh:
                js = fh.read()
            for fname, default in expects:
                self.assertIn('function %s(' % default, js,
                              '%s::%s 的 tojs 默认值 %r 在 js 里不存在'
                              % (plugin, fname, default))

    def test_21_no_bare_tojs_subscript(self):
        # 源码里不得再有裸 args['tojs']（缺参即 KeyError）
        for plugin in PLUGIN_INDEX:
            bad = [n.lineno for n in ast.walk(ast.parse(_plugin_src(plugin)))
                   if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
                   and n.value.id == 'args' and isinstance(n.slice, ast.Constant)
                   and n.slice.value == 'tojs']
            self.assertEqual(bad, [], '%s/index.py 仍有裸 args[\'tojs\']：行 %s' % (plugin, bad))

    def test_22_type_invalid_returns_json_error_not_traceback(self):
        for plugin in ('mysql', 'mariadb'):
            for bad in ('abc', '', '1.5', None):
                args = {'type': bad, 'ids': '[]'}
                try:
                    out, _calls = _run_sync_to_databases(plugin, args)
                except Exception as ex:
                    self.fail('%s::syncToDatabases(type=%r) 抛了 %s: %s（前端会拿到非 JSON）'
                              % (plugin, bad, type(ex).__name__, ex))
                obj = json.loads(out)
                self.assertIs(obj['status'], False,
                              '%s::syncToDatabases(type=%r) 应回 JSON 错误：%s' % (plugin, bad, out))
                self.assertIn('type', obj['msg'],
                              '%s::syncToDatabases(type=%r) 的错误文案应点名 type：%s'
                              % (plugin, bad, out))

    def test_23_type_missing_returns_json_error(self):
        for plugin in ('mysql', 'mariadb'):
            out, _calls = _run_sync_to_databases(plugin, {'ids': '[]'})
            obj = json.loads(out)
            self.assertIs(obj['status'], False, '%s：缺 type 应回 JSON 错误：%s' % (plugin, out))
            self.assertIn('type', obj['msg'], '%s：缺 type 的错误文案应点名 type：%s' % (plugin, out))

    def test_24_type_legit_values_unchanged(self):
        # 合法取值语义不变：0 = 同步全部数据库（走 select 全量）；非 0 = 按 ids 同步
        for plugin in ('mysql', 'mariadb'):
            out0, calls0 = _run_sync_to_databases(plugin, {'type': '0', 'ids': '[]'})
            self.assertIs(json.loads(out0)['status'], True, '%s：type=0 应成功：%s' % (plugin, out0))
            self.assertIn(('select',), calls0, '%s：type=0 应走「查询全部数据库」分支' % plugin)
            self.assertNotIn('find', [c[0] for c in calls0],
                             '%s：type=0 不该走按 id 查询分支' % plugin)

            out1, calls1 = _run_sync_to_databases(plugin, {'type': '1', 'ids': '[1,2]'})
            self.assertIs(json.loads(out1)['status'], True, '%s：type=1 应成功：%s' % (plugin, out1))
            self.assertNotIn(('select',), calls1, '%s：type=1 不该走全量查询分支' % plugin)
            self.assertEqual([c[0] for c in calls1].count('find'), 2,
                             '%s：type=1 应按 ids 逐个 find：%s' % (plugin, calls1))

    def test_25_get_db_list_survives_bad_page_args(self):
        """真跑三个插件的 `getDbList()`：非法分页参数不得抛异常，且 LIMIT 三插件一致。"""
        for title, args, kwargs, expect in PLUGIN_PAGE_CASES:
            if kwargs:
                # 带 def_size/max_size 的几条测的是「其它接口按调用处传参」的口径，
                # getDbList 不传这两个参数，故不适用
                continue
            limits = {}
            for plugin in PLUGIN_INDEX:
                try:
                    out, limit = _run_get_db_list(plugin, args)
                except Exception as ex:
                    self.fail('%s::getDbList 对「%s」抛了 %s: %s'
                              % (plugin, title, type(ex).__name__, ex))
                obj = json.loads(out)
                self.assertIn('data', obj, '%s::getDbList 返回结构变了：%s' % (plugin, out))
                page, size = expect
                self.assertEqual(limit, '%d,%d' % ((page - 1) * size, size),
                                 '%s::getDbList 对「%s」拼出的 LIMIT 不对：%s'
                                 % (plugin, title, limit))
                limits[plugin] = limit
            self.assertEqual(len(set(limits.values())), 1,
                             '三插件对「%s」的 LIMIT 不一致：%s' % (title, limits))

    def test_26_list_endpoints_tolerate_missing_tojs(self):
        # 缺 tojs 不得 KeyError：要回退到本接口自己的前端回调（每处上下文不同）
        cases = [('getSlaveSSHList', 'getSlaveSSHPage'),
                 ('getSlaveSyncUserList', 'getSlaveSyncUserPage')]
        for plugin in ('mysql', 'mariadb'):
            for fname, default in cases:
                for args in ({'page': '1', 'page_size': '5'},
                             {'page': 'abc', 'page_size': 'xyz'}):
                    try:
                        out, page_args = _run_list_fn(plugin, fname, args)
                    except Exception as ex:
                        self.fail('%s::%s 在 tojs 缺参时抛了 %s: %s'
                                  % (plugin, fname, type(ex).__name__, ex))
                    self.assertEqual(len(page_args), 1,
                                     '%s::%s 没有走到 yf.getPage' % (plugin, fname))
                    self.assertEqual(page_args[0].get('tojs'), default,
                                     '%s::%s 的 tojs 回退值应为 %r，实际 %r'
                                     % (plugin, fname, default, page_args[0].get('tojs')))
                    # 同一请求里的非法 page/page_size 也要一并兜住
                    self.assertEqual((page_args[0].get('p'), page_args[0].get('row')), (1, 5),
                                     '%s::%s 非法分页参数未兜底：%s'
                                     % (plugin, fname, page_args[0]))
                    self.assertIn('data', json.loads(out))


if __name__ == '__main__':
    unittest.main()