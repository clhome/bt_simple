# coding: utf-8
"""P2-8「登录限流降级可见化」的守卫：status() / 缓存 / 路由 / 模板 / i18n / 语义未改。

## 背景

`web/core/login_guard.py` 的计数落库在 `panel_login_failure` 表不可用时 **fail-open**：
自动退回**进程内内存计数**。这个取舍本身是对的（表坏了不能把登录全部打死，那是
可用性事故），但代价是「多 worker 下每个进程各算各的」—— 也就是爆破限流与
「改密码踢下线」会**静默失效**，而面板上看不到任何迹象。

本项只做**可见化**：新增 `login_guard.status()` + `/get_login_guard_status` +
首页告警 + 文档明示取舍。**限流语义一行未改**（第 7 组用例专门守这一点）。

## 用例分组

1. `StatusBackendTest`         —— db / memory 两态判定与 reason 非空
2. `StatusRobustnessTest`      —— `_query` / `_execute` 抛异常时 `status()` 不抛上层
3. `StatusCacheTest`           —— 短时缓存：连调两次只探一次表，`_reset_status_cache()` 后可再探
4. `RouteWiringTest`           —— 路由存在 + `@panel_login_required` + 首页确实用上了判定结果
5. `TemplateWarningTest`       —— 首页告警块受 `login_guard` 状态控制、含「限流/降级」、两态可区分
6. `I18nAndDocTest`            —— 六语言键齐全（zh-TW 无简体残留）+ SECURITY.md 口径词
7. `CoreSemanticsUnchangedTest` —— `is_banned()` 的 fail-open 分支仍在（没被改成 fail-closed）

## 零外部依赖

`login_guard` 模块级只 import `logging/threading/time`，数据库访问全在函数内延迟
import（`import core.yf as yf`）。因此本用例**按文件路径加载模块**即可，不建 Flask app、
不开面板库、不需要 node/opencc。
"""

import ast
import importlib.util
import io
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')

GUARD_PY = os.path.join(WEB, 'core', 'login_guard.py')
DASHBOARD_PY = os.path.join(WEB, 'admin', 'dashboard', 'dashboard.py')
INDEX_TMPL = os.path.join(WEB, 'templates', 'default', 'index.html')
SECURITY_MD = os.path.join(ROOT, 'SECURITY.md')
LANG_DIR = os.path.join(WEB, 'static', 'language')

LANGS = ('zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it')

KEY_TITLE = 'login_guard_degraded_title'
KEY_DESC = 'login_guard_degraded_desc'

#: 模板里判定「是否降级」的标志变量名（由 dashboard.index() 传入）
FLAG = 'login_guard_degraded'

#: zh-TW 里出现即说明混进了简体（OpenCC 反向转换能抓到的就是这些字）
SIMPLIFIED_ONLY = '录级为进计数败无写库护码线请检后页'


def _read(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


def load_guard():
    """按文件路径加载 `login_guard`（不 import admin / 不建库）。"""
    spec = importlib.util.spec_from_file_location('yf_login_guard_visibility', GUARD_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _guarded_region(src, flag):
    """取出 `{% if <flag> %} ... {% endif %}` 之间的模板片段（取最长的一段）。

    这样能区分「告警块受状态控制」与「告警块写在条件外面」——后者在 db 态下
    也会显示，等于天天误报，用户很快就会无视它。
    """
    pat = re.compile(r'\{%-?\s*if\s+' + re.escape(flag) +
                     r'\s*-?%\}(.*?)\{%-?\s*endif\s*-?%\}', re.S)
    blocks = pat.findall(src)
    if not blocks:
        return None
    return max(blocks, key=len)


def _func_node(src, name):
    """按函数名取 AST 节点（用于断言「某个分支还在」）。"""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _func_source(src, name):
    """按函数名取源码文本（保留原始排版，便于字符串断言）。"""
    lines = src.split('\n')
    node = _func_node(src, name)
    if node is None:
        return None
    return '\n'.join(lines[node.lineno - 1:node.end_lineno])


def _calls(node, func_name):
    """节点内是否调用了名为 func_name 的函数。"""
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) \
                and child.func.id == func_name:
            return True
    return False


def _rows_none_branch(node):
    """取出 `if rows is None:` 分支的语句列表（找不到返回 None）。

    这是 fail-open 的**唯一「降级入口」**：查询失败（`_query` 返回 None）时走到这里。
    """
    for child in ast.walk(node):
        if not isinstance(child, ast.If):
            continue
        t = child.test
        if isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) \
                and t.left.id == 'rows' and len(t.ops) == 1 \
                and isinstance(t.ops[0], ast.Is) \
                and isinstance(t.comparators[0], ast.Constant) \
                and t.comparators[0].value is None:
            return child.body
    return None


def _stats_calls(stmts, func_name):
    """语句列表里是否有对 func_name 的调用（只看本层，不递归）。"""
    for s in stmts:
        for child in ast.walk(s):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) \
                    and child.func.id == func_name:
                return True
    return False


def _returns_true(stmts):
    """语句列表里本层是否有 `return True`（不递归进嵌套 if）。

    只看本层是故意的：`is_banned` 里「内存计数命中 -> return True」是**正确**写法，
    要抓的是「查询失败就直接 return True」这种 fail-closed 改写。
    """
    for s in stmts:
        if isinstance(s, ast.Return) and isinstance(s.value, ast.Constant) \
                and s.value.value is True:
            return True
    return False


class _GuardCase(unittest.TestCase):
    """共用的模块加载 + 替身复原（替身不许漏到别的用例里）。"""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_guard()

    def setUp(self):
        self._orig = {
            '_table_ready': self.mod._table_ready,
            '_query': self.mod._query,
            '_execute': self.mod._execute,
        }
        self.mod.reset_cache()

    def tearDown(self):
        for name, fn in self._orig.items():
            setattr(self.mod, name, fn)
        self.mod.reset_cache()

    def _force_backend(self, ready, query=None):
        """用替身把后端固定到指定状态（不碰真库）。"""
        self.mod._table_ready = lambda: ready
        if query is not None:
            self.mod._query = query
        self.mod._reset_status_cache()


# --------------------------------------------------------------------------
# 1) 两态判定
# --------------------------------------------------------------------------
class StatusBackendTest(_GuardCase):
    """`status()` 必须如实暴露 db / memory 两态（否则告警永远不会出现）。"""

    def test_10_db_when_table_ready(self):
        self._force_backend(True, query=lambda *a, **k: [])
        st = self.mod.status()
        self.assertTrue(st['table_ready'], '表就绪时必须报 table_ready=True')
        self.assertEqual('db', st['backend'], '表就绪时 backend 必须是 db')
        for key in ('table_ready', 'backend', 'reason', 'checked_at'):
            self.assertIn(key, st, 'status() 缺少键 %r' % key)
        self.assertIsInstance(st['checked_at'], str)
        self.assertTrue(st['checked_at'], 'checked_at 不能为空（用于「什么时候判的」）')

    def test_11_memory_when_table_not_ready(self):
        self._force_backend(False)
        st = self.mod.status()
        self.assertFalse(st['table_ready'])
        self.assertEqual('memory', st['backend'], '表不可用时必须暴露为 memory 态')
        self.assertTrue(st['reason'], '降级必须给出理由（面板要写清为什么降级）')

    def test_12_memory_reason_mentions_cause(self):
        """真探测路径下 reason 要能说明原因（表不存在 / 查询失败 / 未初始化）。"""
        self.mod._READY_REASON[0] = 'panel_login_failure 表不存在（未初始化或迁移未执行）'
        self.mod._table_ready = lambda: False
        self.mod._reset_status_cache()
        st = self.mod.status()
        self.assertEqual('memory', st['backend'])
        self.assertIn('panel_login_failure', st['reason'])

    def test_13_memory_reason_never_empty_even_if_probe_stubbed(self):
        """替身把探测绕过时，reason 也要有兜底文案（不能返回空串）。"""
        self.mod._READY_REASON[0] = ''
        self.mod._table_ready = lambda: False
        self.mod._reset_status_cache()
        self.assertTrue(self.mod.status()['reason'].strip())


# --------------------------------------------------------------------------
# 2) 健壮性：可见化功能本身不许把首页/登录拖崩
# --------------------------------------------------------------------------
class StatusRobustnessTest(_GuardCase):
    """`_query` / `_execute` 抛异常时 `status()` 必须仍能返回，且报 memory 态。"""

    def test_20_query_raises_still_returns(self):
        def boom(*a, **k):
            raise RuntimeError('数据库不可用')

        self._force_backend(True, query=boom)
        st = self.mod.status()          # 不许抛
        self.assertEqual('memory', st['backend'], '查询抛异常时必须报 memory 态')
        self.assertIn('数据库不可用', st['reason'])

    def test_21_execute_raises_does_not_break_status(self):
        def boom(*a, **k):
            raise RuntimeError('写库不可用')

        self._force_backend(True, query=lambda *a, **k: [])
        self.mod._execute = boom
        st = self.mod.status()
        self.assertIn(st['backend'], ('db', 'memory'))
        self.assertIn('reason', st)

    def test_22_table_ready_raises_still_returns(self):
        def boom():
            raise RuntimeError('探测炸了')

        self.mod._table_ready = boom
        self.mod._reset_status_cache()
        st = self.mod.status()
        self.assertFalse(st['table_ready'])
        self.assertEqual('memory', st['backend'])
        self.assertIn('探测炸了', st['reason'])

    def test_23_query_none_counts_as_memory(self):
        """表在但读不到（锁表 / 库损坏）同样算降级 —— 此时限流已经在走内存计数。"""
        self._force_backend(True, query=lambda *a, **k: None)
        self.assertEqual('memory', self.mod.status()['backend'])


# --------------------------------------------------------------------------
# 3) 短时缓存
# --------------------------------------------------------------------------
class StatusCacheTest(_GuardCase):
    """首页每次刷新都会问一次状态：不缓存就是每次请求都探表。"""

    def test_30_two_calls_probe_once(self):
        calls = []

        def fake_ready():
            calls.append(1)
            return False

        self.mod._table_ready = fake_ready
        self.mod._reset_status_cache()
        self.mod.status()
        self.mod.status()
        self.assertEqual(1, len(calls),
                         '连续两次 status() 只允许探表一次（短时缓存失效了？）')

    def test_31_reset_cache_allows_new_probe(self):
        calls = []

        def fake_ready():
            calls.append(1)
            return False

        self.mod._table_ready = fake_ready
        self.mod._reset_status_cache()
        self.mod.status()
        self.assertEqual(1, len(calls))
        self.mod._reset_status_cache()
        self.mod.status()
        self.assertEqual(2, len(calls), '_reset_status_cache() 后必须重新探表')

    def test_32_ttl_in_expected_range(self):
        ttl = getattr(self.mod, 'STATUS_CACHE_TTL', None)
        self.assertIsNotNone(ttl, '缺少 STATUS_CACHE_TTL')
        self.assertTrue(1 <= ttl <= 60, 'status 缓存 TTL 应在 1~60s（实测 %r）' % ttl)

    def test_33_cached_result_is_isolated(self):
        """返回的是副本：调用方改了返回值不能污染缓存。"""
        self._force_backend(False)
        first = self.mod.status()
        first['backend'] = 'db'
        self.assertEqual('memory', self.mod.status()['backend'])


# --------------------------------------------------------------------------
# 4) 路由接线
# --------------------------------------------------------------------------
class RouteWiringTest(unittest.TestCase):
    """接口存在 + 登录可见 + 首页真的用上了判定结果（防「写了模块没人用」）。"""

    def test_40_route_with_login_required(self):
        src = _read(DASHBOARD_PY)
        self.assertIn('/get_login_guard_status', src, '缺少 /get_login_guard_status 路由')
        m = re.search(r"@blueprint\.route\('/get_login_guard_status'.*?"
                      r"\ndef get_login_guard_status\(\):", src, re.S)
        self.assertIsNotNone(m, '找不到 /get_login_guard_status 视图')
        self.assertIn('@panel_login_required', m.group(0),
                      '限流状态接口必须登录可见（不能匿名暴露面板内部状态）')

    def test_41_route_returns_status_dict(self):
        src = _read(DASHBOARD_PY)
        body = _func_source(src, 'get_login_guard_status')
        self.assertIsNotNone(body, '找不到 get_login_guard_status 函数体')
        self.assertIn('login_guard', body)
        self.assertIn('status()', body, '路由必须调用 login_guard.status()')
        self.assertIn('returnData', body, '与同文件其它接口一致：走 yf.returnData 包装')

    def test_42_index_passes_flag_into_template(self):
        src = _read(DASHBOARD_PY)
        self.assertIn('login_guard_degraded=', src,
                      '首页没有把降级标志传进模板 → 告警永远不会出现')
        self.assertIn('login_guard_status=', src)
        body = _func_source(src, 'index')
        self.assertIsNotNone(body)
        self.assertIn('_login_guard_status()', body,
                      'index() 必须真的去取状态，而不是传常量')

    def test_43_index_short_circuit_is_visible(self):
        """取状态失败也按 memory 报（宁可告警，不许静默）。"""
        src = _read(DASHBOARD_PY)
        body = _func_source(src, '_login_guard_status')
        self.assertIsNotNone(body)
        self.assertIn('memory', body, '状态读取失败时应当按降级上报，不能静默当 db')
        self.assertIn('_log.warning', body, '异常必须留日志（不许静默 except）')


# --------------------------------------------------------------------------
# 5) 首页告警块
# --------------------------------------------------------------------------
class TemplateWarningTest(unittest.TestCase):
    """告警必须受 login_guard 状态控制，且文案能说清「限流降级」。"""

    def setUp(self):
        self.html = _read(INDEX_TMPL)

    def test_50_warning_block_guarded_by_state(self):
        block = _guarded_region(self.html, FLAG)
        self.assertIsNotNone(block, '首页缺少受 ' + FLAG + ' 状态控制的告警块')
        self.assertIn('role="alert"', block, '告警块必须带 role="alert"（无障碍 + 可被用例定位）')

    def test_51_warning_text_mentions_limit_degrade(self):
        block = _guarded_region(self.html, FLAG)
        self.assertIsNotNone(block)
        self.assertTrue('限流' in block or '降级' in block,
                        '告警文案必须含「限流」或「降级」')
        self.assertIn(KEY_TITLE, block)
        self.assertIn(KEY_DESC, block)

    def test_52_two_states_distinguishable(self):
        """memory 才告警；块内带 backend 标记，db/memory 两态可区分。"""
        block = _guarded_region(self.html, FLAG)
        self.assertIsNotNone(block)
        self.assertIn("login_guard_status['backend']", block,
                      '告警块要能标出当前 backend（区分 db / memory 两态）')

    def test_53_warning_is_after_plain_http_block(self):
        """只追加：P2-2 的明文 HTTP 告警块必须原样还在。"""
        self.assertIn('id="plainHttpWarning"', self.html, 'P2-2 的告警块被动了')
        self.assertIn('plain_http_warning_title', self.html)
        self.assertLess(self.html.index('plainHttpWarning'),
                        self.html.index('loginGuardWarning'),
                        'P2-8 告警应追加在 P2-2 之后，不改变既有顺序')


# --------------------------------------------------------------------------
# 6) i18n + 交付文档
# --------------------------------------------------------------------------
class I18nAndDocTest(unittest.TestCase):
    """六语言文案齐全（zh-TW 无简体残留），文档写明取舍。"""

    def _value(self, lang, key):
        src = _read(os.path.join(LANG_DIR, lang, 'lan.js'))
        m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % re.escape(key), src)
        self.assertIsNotNone(m, '%s 的 lan.js 缺少 %s' % (lang, key))
        return m.group(1)

    def test_60_all_six_languages_have_keys(self):
        for lang in LANGS:
            for key in (KEY_TITLE, KEY_DESC):
                self.assertTrue(self._value(lang, key).strip(),
                                '%s 的 %s 是空值（界面会空白/回落中文）' % (lang, key))

    def test_61_zh_tw_has_no_simplified_residue(self):
        for key in (KEY_TITLE, KEY_DESC):
            val = self._value('zh-TW', key)
            bad = [ch for ch in SIMPLIFIED_ONLY if ch in val]
            self.assertEqual([], bad, 'zh-TW 的 %s 混进简体字：%r（%r）' % (key, bad, val))

    def test_62_carriers_derived_from_lan_js(self):
        """载体（template.json / public.json / template.setting.json）已随之派生。"""
        import json
        for lang in LANGS:
            for name in ('public.json', 'template.json', 'template.setting.json'):
                path = os.path.join(LANG_DIR, lang, name)
                with io.open(path, 'r', encoding='utf-8') as fh:
                    text = fh.read()
                self.assertIn(KEY_TITLE, text, '%s/%s 缺少 %s' % (lang, name, KEY_TITLE))
                self.assertIn(KEY_DESC, text, '%s/%s 缺少 %s' % (lang, name, KEY_DESC))
                json.loads(text)     # 载体必须是合法 JSON

    def test_63_security_md_states_the_tradeoff(self):
        doc = _read(SECURITY_MD)
        self.assertIn('## 已知取舍', doc, 'SECURITY.md 缺少「## 已知取舍」小节')
        idx = doc.index('## 已知取舍')
        section = doc[idx:] if '## ' not in doc[idx + 3:] else doc
        for word in ('fail-open', '多 worker', '告警'):
            self.assertIn(word, doc, 'SECURITY.md 未写明 %r 口径' % word)
        self.assertIn('登录', section)
        self.assertIn('进程', section)


# --------------------------------------------------------------------------
# 7) 限流语义未改（本项只做可见化）
# --------------------------------------------------------------------------
class CoreSemanticsUnchangedTest(unittest.TestCase):
    """fail-open 取舍必须原样保留 —— 谁把它改成 fail-closed 这里就要红。"""

    @classmethod
    def setUpClass(cls):
        cls.src = _read(GUARD_PY)

    def test_70_is_banned_keeps_fail_open_branch(self):
        """`if rows is None:` 分支必须仍是「查内存 + continue」，而不是直接封禁。"""
        node = _func_node(self.src, 'is_banned')
        self.assertIsNotNone(node, '找不到 is_banned()')
        self.assertTrue(_calls(node, '_query'), 'is_banned 必须仍走 _query')
        branch = _rows_none_branch(node)
        self.assertIsNotNone(
            branch, 'is_banned 里找不到「查询失败（rows is None）」分支：fail-open 被改了？')
        self.assertTrue(_stats_calls(branch, '_mem_banned'),
                        '查询失败时应改查内存计数（fail-open），当前分支里没有 _mem_banned')
        self.assertTrue(any(isinstance(s, ast.Continue) for s in branch),
                        '查询失败后必须继续看下一个维度（continue），不能就此收手')
        self.assertFalse(_returns_true(branch),
                         '「查询失败 -> return True」= fail-closed：库坏时会把所有人锁在门外')

    def test_71_bump_falls_back_to_memory(self):
        node = _func_node(self.src, '_bump')
        self.assertIsNotNone(node, '找不到 _bump()')
        branch = _rows_none_branch(node)
        self.assertIsNotNone(branch, '_bump 里找不到「查询失败（rows is None）」分支')
        self.assertTrue(_stats_calls(branch, '_mem_bump'),
                        '_bump 的降级分支被删了：内存兜底计数必须保留')

    def test_72_is_banned_still_consults_memory_on_failure(self):
        body = _func_source(self.src, 'is_banned')
        self.assertIn('_mem_banned(kind, value, now)', body,
                      'is_banned 的「查询失败 -> 查内存」分支必须保留（fail-open）')

    def test_73_status_is_read_only(self):
        """status() / _probe_status() 不得写库（只读探测）。"""
        for name in ('status', '_probe_status'):
            node = _func_node(self.src, name)
            self.assertIsNotNone(node, '找不到 %s()' % name)
            self.assertFalse(_calls(node, '_execute'), '%s 不许写库' % name)
            self.assertFalse(_calls(node, '_bump'), '%s 不许计数' % name)
            self.assertFalse(_calls(node, 'register_failure'), '%s 不许改计数' % name)

    def test_74_no_new_dependency(self):
        """零新依赖：只用标准库。"""
        tree = ast.parse(self.src)
        allowed = {'logging', 'threading', 'time'}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imported.add(a.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split('.')[0])
        extra = imported - allowed - {'core'}
        self.assertEqual(set(), extra, 'login_guard 引入了新依赖：%r' % sorted(extra))


if __name__ == '__main__':
    unittest.main()
