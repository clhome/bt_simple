# coding: utf-8
"""A01 dashboard（首页概览）真机测试中修复的两处缺陷的回归守卫。

1. ``/get_recent_logins`` 的 ``limit`` 只有上界（>50 → 50），没有下界。
   SQLite 把**负数 LIMIT 当成「不限制」**，于是 ``limit=-1`` 一次拉出全表
   （真机实测：64 条登录日志全量返回；``limit=50`` 返回 50 条）；
   另外 ``limit=0`` 会让本页为空、触发「兜底展示当前用户」分支，
   凭空造出一条记录并把 count 改写为 1（假数据）。
2. ``tojs``（分页回调名）被 ``utils/page.py`` 原样拼进
   ``onclick='<tojs>(n)'``，含引号即可闭合属性注入标签：
   真机 ``POST /get_recent_logins`` 带
   ``tojs=x'><img src=x onerror=alert(1)>`` 时响应的分页 HTML 里
   出现了可执行的 ``<img src=x onerror=alert(1)>``，而前端用
   ``$('#allLoginLogsPage').html(data.page)`` 渲染 → 反射型 XSS。

两处断言都跑**真实源码**：第 1 项用 ``ast`` 抽出 ``get_recent_logins``
函数体在桩命名空间里执行，第 2 项直接调用 ``core.yf.getPageObject``
（离线可跑，不依赖 flask / 面板库 / 网络）。
"""
import ast
import os
import re
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)

DASHBOARD_PY = os.path.join(WEB, 'admin', 'dashboard', 'dashboard.py')
SYSTEM_PY = os.path.join(WEB, 'core', 'yf', 'system.py')
INDEX_JS = os.path.join(WEB, 'static', 'app', 'index.js')

#: 真机上确认能打穿 onclick 属性的两个载荷
XSS_TAG_PAYLOAD = "x'><img src=x onerror=alert(1)>"
XSS_JS_PAYLOAD = "x');alert(document.cookie);//"


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


# --------------------------------------------------------------------------
# 1) /get_recent_logins 的 limit 夹取
# --------------------------------------------------------------------------

class _FakeRequest(object):
    def __init__(self, values):
        self.values = values


class _FakeQuery(object):
    """最小化的 ``yf.M(...)`` 查询链：只记录 limit() 的实参。"""

    def __init__(self, sink):
        self._sink = sink

    def where(self, *args, **kwargs):
        return self

    def field(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, value):
        self._sink['limit'] = value
        return self

    def select(self):
        return []

    def count(self):
        return 0


def _load_get_recent_logins(sink):
    """抽出真实的 ``get_recent_logins`` 源码（去装饰器）后在桩命名空间执行。"""
    tree = ast.parse(_read(DASHBOARD_PY))
    fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'get_recent_logins':
            fn = node
            break
    if fn is None:
        raise AssertionError('dashboard.py 里找不到 get_recent_logins')
    fn.decorator_list = []
    src = ast.unparse(ast.Module(body=[fn], type_ignores=[]))

    yf = types.SimpleNamespace(
        getClientIp=lambda: '10.0.0.9',
        M=lambda *a, **k: _FakeQuery(sink),
        writeFileLog=lambda *a, **k: None,
        getPage=lambda args: sink.setdefault('page_args', args),
        returnData=lambda status, msg, data=None, *a: {
            'status': status, 'msg': msg, 'data': data},
        formatDate=lambda *a, **k: '2026-01-01 00:00:00',
    )
    ns = {
        'yf': yf,
        'request': _FakeRequest({}),
        'thisdb': types.SimpleNamespace(getUserById=lambda _id: {
            'login_time': '2026-01-01 00:00:00', 'login_ip': '10.0.0.9'}),
        '_log': types.SimpleNamespace(debug=lambda *a, **k: None),
        'parse_ip_type_info': lambda ip: ('lan', '局域网内网'),
        'webhook_index': None,
    }
    exec(compile(src, DASHBOARD_PY, 'exec'), ns)
    return ns['get_recent_logins'], ns


class TestRecentLoginsLimitClamp(unittest.TestCase):
    """负数 / 0 / 非法 limit 都不能变成「不限量」或空页兜底。"""

    def _limit_arg(self, given):
        sink = {}
        fn, ns = _load_get_recent_logins(sink)
        ns['request'].values = {'limit': given, 'p': '1'}
        fn()
        return sink['limit'], sink['page_args']

    def test_negative_limit_is_clamped(self):
        for given in ('-1', '-50', '-100000'):
            limit_str, _page_args = self._limit_arg(given)
            start, row = limit_str.split(',')
            self.assertGreaterEqual(int(row), 1, 'limit=%s 未夹取下界' % given)
            self.assertEqual(int(start), 0, 'limit=%s 起始行应为 0' % given)

    def test_zero_and_invalid_limit(self):
        for given in ('0', 'abc', '', ' ', '2.9', None):
            limit_str, _page_args = self._limit_arg(given)
            _start, row = limit_str.split(',')
            self.assertGreaterEqual(int(row), 1, 'limit=%r 未夹取下界' % given)

    def test_upper_bound_kept(self):
        limit_str, page_args = self._limit_arg('999999')
        self.assertEqual(limit_str.split(',')[1], '50')
        self.assertEqual(int(page_args['row']), 50)

    def test_normal_limit_preserved(self):
        limit_str, page_args = self._limit_arg('3')
        self.assertEqual(limit_str, '0,3')
        self.assertEqual(int(page_args['row']), 3)

    def test_source_clamps_lower_bound(self):
        """结构断言：limit 解析后必须同时出现下界夹取（防止有人只留上界）。"""
        tree = ast.parse(_read(DASHBOARD_PY))
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == 'get_recent_logins')
        lowered = 0
        for node in ast.walk(fn):
            if isinstance(node, ast.If) and isinstance(node.test, ast.Compare) \
                    and isinstance(node.test.ops[0], (ast.Lt, ast.LtE)):
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign) \
                            and isinstance(stmt.targets[0], ast.Name) \
                            and stmt.targets[0].id == 'limit':
                        lowered += 1
        self.assertEqual(lowered, 1, 'get_recent_logins 缺少 limit 下界夹取')


# --------------------------------------------------------------------------
# 2) 分页回调名 tojs 的白名单校验
# --------------------------------------------------------------------------

class TestTojsWhitelist(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import core.yf as yf
        cls.yf = yf

    def _page_html(self, tojs):
        out = self.yf.getPageObject(
            {'count': 30, 'row': 10, 'p': 1, 'tojs': tojs})[0]
        self.assertIsInstance(out, str)
        return out

    def test_legit_callback_still_rendered(self):
        html = self._page_html('getAllLoginLogs')
        self.assertIn("onclick='getAllLoginLogs(2)'", html)
        self.assertNotIn('href=', html)

    def test_dotted_callback_still_rendered(self):
        html = self._page_html('page.next')
        self.assertIn("onclick='page.next(2)'", html)

    def test_html_tag_payload_not_reflected(self):
        html = self._page_html(XSS_TAG_PAYLOAD)
        self.assertNotIn('<img', html, '载荷被原样拼进了分页 HTML')
        self.assertNotIn('onerror', html)
        self.assertNotIn("x'", html)
        self.assertNotIn('onclick', html, '非法回调名必须退回 href 分页模式')

    def test_js_payload_not_reflected(self):
        html = self._page_html(XSS_JS_PAYLOAD)
        self.assertNotIn('alert(', html)
        self.assertNotIn("x'", html)

    def test_non_string_tojs_does_not_crash(self):
        for given in (123, None, 1.5, '', '   '):
            html = self._page_html(given)
            self.assertNotIn('onclick', html)

    def test_system_py_validates_tojs(self):
        """结构断言：白名单校验必须在 getPageObject 里（唯一入口）。"""
        tree = ast.parse(_read(SYSTEM_PY))
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == 'getPageObject')
        src = ast.unparse(fn)
        self.assertIn('return_js', src)
        self.assertIn('re.match', src)
        self.assertIn('[A-Za-z_$]', src)


# --------------------------------------------------------------------------
# 3) 首页最近登录 / IP 归属地请求都必须有失败分支（遮罩/表格不卡死）
# --------------------------------------------------------------------------

class TestDashboardJsFailureHandling(unittest.TestCase):

    def test_dashboard_ajax_calls_have_fail_handler(self):
        js = _read(INDEX_JS)
        for call in ("$.post('/get_recent_logins'", "$.post('/get_ip_location'"):
            starts = [m.start() for m in re.finditer(re.escape(call), js)]
            self.assertTrue(starts, call)
            for pos in starts:
                # 请求链所在的整个函数体（到下一个顶层 function 为止）
                nxt = js.find('\nfunction ', pos)
                body = js[pos:nxt if nxt > 0 else len(js)]
                self.assertIn('.fail(', body,
                              '%s 调用链缺少 .fail() 失败分支' % call)


if __name__ == '__main__':
    unittest.main()
