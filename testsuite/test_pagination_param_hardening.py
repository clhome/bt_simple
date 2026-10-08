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


if __name__ == '__main__':
    unittest.main()