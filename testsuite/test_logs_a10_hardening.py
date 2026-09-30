# coding:utf-8
"""A10 logs 模块回归守卫（第二轮：面板日志归档 / 分页容错 / 前端转义与遮罩）。

覆盖本轮新修的 4 类问题（每条都能被 test/a10_mutation_probe.py 回退打红）：

1. ``/logs/get_log_list`` 用表单原文调 ``yf.getPage`` → ``int('abc')`` 抛
   ValueError，接口 **HTTP 500**（列表本身已容错，分页没跟上）；
2. ``thisdb.archiveLogs`` 忽略 ``yf.writeFile`` 的返回值 → 归档没落盘也照样
   ``clearLog()``，**面板日志不可逆丢失**（实测复现）；
3. 归档文件名只精确到秒 → 同一秒内二次归档把上一份（唯一证据）覆盖掉；
4. ``logs.js``：``getLogs`` 无 ``.fail()``（500 时 loading 遮罩永久卡死）且
   日志内容直接拼 HTML（存储型 XSS，库中已存在真实载荷）。
"""
import ast
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'web'))

import thisdb.logs as logs_db  # noqa: E402
import utils.adult_log as adult_log  # noqa: E402

ADULT_LOG = os.path.join(ROOT, 'web', 'utils', 'adult_log.py')

THISDB_LOGS = os.path.join(ROOT, 'web', 'thisdb', 'logs.py')
LOGS_ROUTE = os.path.join(ROOT, 'web', 'admin', 'logs', '__init__.py')
LOGS_JS = os.path.join(ROOT, 'web', 'static', 'app', 'logs.js')


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


class _FakeTable(object):
    """最小 SQL 表替身：只实现 logs 相关链路用到的方法。"""

    def __init__(self, state):
        self.state = state

    def field(self, *a):
        return self

    def order(self, *a):
        return self

    def limit(self, *a):
        return self

    def where(self, *a):
        return self

    def select(self):
        return [dict(r) for r in self.state['rows']]

    def count(self):
        return len(self.state['rows'])

    def delete(self):
        n = len(self.state['rows'])
        self.state['rows'] = []
        self.state['cleared'] = True
        self.state['delete_calls'] += 1
        return n

    def execute(self, *a, **k):
        return 1


class _ArchiveCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_a10_')
        self.state = {'rows': [{'id': i, 'type': 't', 'log': 'l%d' % i,
                                'uid': 1, 'ip': '', 'add_time': 'x'}
                               for i in range(1, 4)],
                      'cleared': False, 'delete_calls': 0}
        self._patches = [
            mock.patch.object(logs_db.yf, 'M',
                              lambda table='': _FakeTable(self.state)),
            mock.patch.object(logs_db.yf, 'getPanelDataDir', lambda: self.tmp),
            mock.patch.object(logs_db.yf, 'formatDate',
                              lambda *a, **k: '2026-09-30 16:00:00'),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def _expect(self):
        return os.path.normpath(os.path.join(self.tmp, 'log_archive',
                                             'panel_logs_20260930_160000.json'))

    def _norm(self, path):
        return os.path.normpath(path)


class TestArchiveLogs(_ArchiveCase):
    def test_normal_archives_then_clears(self):
        path, count = logs_db.archiveLogs()
        self.assertEqual(count, 3)
        self.assertEqual(self._norm(path), self._expect())
        self.assertTrue(os.path.exists(path))
        with open(path, encoding='utf-8') as fh:
            body = json.load(fh)
        self.assertEqual(body['count'], 3)
        self.assertEqual(len(body['rows']), 3)
        self.assertTrue(self.state['cleared'])
        self.assertEqual(self.state['rows'], [])

    def test_write_failure_must_not_clear(self):
        """P0 数据丢失：归档写失败时**绝不能**清空（旧实现照清）。"""
        with mock.patch.object(logs_db.yf, 'writeFile', lambda *a, **k: False):
            with self.assertRaises(Exception):
                logs_db.archiveLogs()
        self.assertFalse(self.state['cleared'], '归档失败却清空了日志')
        self.assertEqual(len(self.state['rows']), 3)

    def test_dir_failure_must_not_clear(self):
        # writeFile 用真实实现（它会自己建目录）：这样只有「先检查 makeDirs」
        # 才能拦住清空，去掉该检查就会写出归档并清空 -> 用例变红。
        with mock.patch.object(logs_db.yf, 'makeDirs', lambda *a, **k: False):
            with self.assertRaises(Exception):
                logs_db.archiveLogs()
        self.assertFalse(self.state['cleared'])
        self.assertEqual(len(self.state['rows']), 3)

    def test_empty_archive_file_must_not_clear(self):
        with mock.patch.object(logs_db.yf, 'writeFile', lambda *a, **k: True):
            with self.assertRaises(Exception):
                logs_db.archiveLogs()
        self.assertFalse(self.state['cleared'])
        self.assertEqual(len(self.state['rows']), 3)

    def test_same_second_must_not_overwrite(self):
        """同一秒内二次归档必须另起文件名，否则旧归档凭空消失。"""
        os.makedirs(os.path.dirname(self._expect()), exist_ok=True)
        with open(self._expect(), 'w', encoding='utf-8') as fh:
            fh.write('{"count": 999, "rows": []}')
        path, count = logs_db.archiveLogs()
        self.assertNotEqual(self._norm(path), self._expect())
        self.assertTrue(os.path.exists(path))
        with open(self._expect(), encoding='utf-8') as fh:
            self.assertEqual(json.load(fh)['count'], 999, '旧归档被覆盖')
        self.assertTrue(self.state['cleared'])


class TestGetLogsListNormalized(unittest.TestCase):
    """分页参数必须在 thisdb 层规范化后回传（路由的分页组件依赖它）。"""

    def setUp(self):
        self.state = {'rows': [], 'cleared': False, 'delete_calls': 0}
        self.p = mock.patch.object(logs_db.yf, 'M',
                                   lambda table='': _FakeTable(self.state))
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_bad_page_size_fall_back(self):
        r = logs_db.getLogsList(page='abc', size='abc')
        self.assertEqual(r['page'], 1)
        self.assertEqual(r['size'], 10)

    def test_bounds(self):
        r = logs_db.getLogsList(page='-5', size='99999')
        self.assertEqual(r['page'], 1)
        self.assertEqual(r['size'], 200)
        r2 = logs_db.getLogsList(page='2', size='0')
        self.assertEqual(r2['page'], 2)
        self.assertEqual(r2['size'], 1)

    def test_returned_values_are_int(self):
        r = logs_db.getLogsList(page='3', size='25')
        self.assertIsInstance(r['page'], int)
        self.assertIsInstance(r['size'], int)

    def test_search_is_parameterized(self):
        """注入串只能当字面量匹配，不能改变语义（参数化查询）。"""
        src = ast.unparse(ast.parse(_read(THISDB_LOGS)))
        self.assertIn('type like ? or log like ?', src)
        self.assertNotIn("like '%", src)


class TestSarFailureIsHonest(unittest.TestCase):
    """sa/sa* 读取：sar 未安装或文件缺失必须如实报错，不能回空串冒充成功。"""

    def test_missing_sar_reports_failure(self):
        with mock.patch.object(adult_log.yf, 'execShellRc',
                               lambda *a, **k: (127, '', 'sar: command not found')), \
             mock.patch.object(adult_log.yf, 'writeFileLog', lambda *a, **k: True):
            res = adult_log.getAuditLogsName('sa/sa01')
        self.assertIsInstance(res, dict)
        self.assertFalse(res['status'])

    def test_empty_output_reports_failure(self):
        with mock.patch.object(adult_log.yf, 'execShellRc',
                               lambda *a, **k: (0, '  \n ', '')), \
             mock.patch.object(adult_log.yf, 'writeFileLog', lambda *a, **k: True):
            res = adult_log.getAuditLogsName('sa/sa01')
        self.assertFalse(res['status'])

    def test_ok_output_is_escaped(self):
        with mock.patch.object(adult_log.yf, 'execShellRc',
                               lambda *a, **k: (0, '<b>x</b> 12:00', '')):
            res = adult_log.getAuditLogsName('sa/sa01')
        self.assertEqual(res, '&lt;b&gt;x&lt;/b&gt; 12:00')

    def test_source_uses_rc(self):
        src = ast.unparse(ast.parse(_read(ADULT_LOG)))
        self.assertIn('execShellRc', src)
        self.assertIn('shlex.quote', src)


class TestRouteSourceGuards(unittest.TestCase):
    """路由层守卫：用 AST 断言，注释 / 字符串蒙混无效。"""

    def _fn(self, name):
        tree = ast.parse(_read(LOGS_ROUTE))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail('路由 %s 不存在' % name)

    def test_get_log_list_uses_normalized_paging(self):
        src = ast.unparse(self._fn('get_log_list'))
        self.assertIn("info['page']", src)
        self.assertIn("info['size']", src)
        # 旧写法：把表单原文（p / size）直接喂给 yf.getPage -> int('abc') 抛错
        self.assertNotIn("'p': p", src.replace('"', "'"))
        self.assertNotIn("'row': size", src.replace('"', "'"))

    def test_del_panel_logs_failure_is_honest(self):
        fn = self._fn('del_panel_logs')
        handlers = [h for n in ast.walk(fn) if isinstance(n, ast.Try)
                    for h in n.handlers]
        self.assertTrue(handlers, 'del_panel_logs 必须捕获归档异常')
        fail_src = ' '.join(ast.unparse(h) for h in handlers)
        self.assertIn('returnData(False', fail_src)
        # 复用成功文案会变成「失败但提示已清空」的假成功
        self.assertNotIn('logs.py_msg_8d2a5b', fail_src)


def _mask_js(src):
    """把 JS 注释/字符串/正则字面量的**内容**换成空格，长度与原文一一对应。

    这样既能在「只剩代码结构」的掩码上做结构断言（注释/字符串无法蒙混），
    又能用同一下标回到原文取真实内容做断言。
    """
    buf = list(src)
    i, n = 0, len(src)
    quote = None

    def _blank(a, b):
        for k in range(a, min(b, n)):
            if buf[k] != '\n':
                buf[k] = ' '

    def _prev_code_ch():
        for k in range(i - 1, -1, -1):
            if src[k] in ' \t\r\n':
                continue
            return src[k]
        return ''

    while i < n:
        ch = src[i]
        if quote:
            if ch == '\\':
                _blank(i, i + 2)
                i += 2
                continue
            if ch == quote:
                quote = None
                _blank(i, i + 1)
                i += 1
                continue
            _blank(i, i + 1)
            i += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            _blank(i, i + 1)
            i += 1
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '/':
            start = i
            while i < n and src[i] != '\n':
                i += 1
            _blank(start, i)
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '*':
            start = i
            i += 2
            while i + 1 < n and not (src[i] == '*' and src[i + 1] == '/'):
                i += 1
            i += 2
            _blank(start, i)
            continue
        if ch == '/' and _prev_code_ch() in '(,=:[!&|?{};':
            # 正则字面量（如 /&/g、/"/g）：剥到未转义的结束斜杠与标志位
            start = i
            i += 1
            while i < n:
                if src[i] == '\\':
                    i += 2
                    continue
                if src[i] == '/':
                    i += 1
                    break
                i += 1
            while i < n and src[i].isalpha():
                i += 1
            _blank(start, i)
            continue
        i += 1
    return ''.join(buf)


def _js_function(src, name):
    """返回 (掩码后的函数体, 原文的函数体)；取不到返回 ('', '')。"""
    masked = _mask_js(src)
    at = masked.find('function ' + name + '(')
    if at < 0:
        return '', ''
    brace = masked.find('{', at)
    if brace < 0:
        return '', ''
    depth = 0
    for i in range(brace, len(masked)):
        if masked[i] == '{':
            depth += 1
        elif masked[i] == '}':
            depth -= 1
            if depth == 0:
                return masked[brace:i + 1], src[brace:i + 1]
    return '', ''


class TestFrontendGuards(unittest.TestCase):
    def test_get_logs_has_fail_handler(self):
        body, _raw = _js_function(_read(LOGS_JS), 'getLogs')
        self.assertTrue(body, 'getLogs 函数缺失')
        self.assertIn('$.post(', body)
        self.assertIn('.fail(', body)
        self.assertGreater(body.index('.fail('), body.index('$.post('),
                           '.fail() 必须挂在 $.post 请求链上')

    def test_del_logs_has_fail_handler(self):
        body, _raw = _js_function(_read(LOGS_JS), 'delLogs')
        self.assertTrue(body, 'delLogs 函数缺失')
        self.assertIn('$.post(', body)
        self.assertIn('.fail(', body)

    def test_all_requests_have_fail(self):
        src = _mask_js(_read(LOGS_JS))
        self.assertGreaterEqual(src.count('.fail('), 4)
        self.assertEqual(src.count('$.post('), src.count('.fail('),
                         '每个 $.post 请求都必须配 .fail()')

    def test_panel_log_rows_are_escaped(self):
        body, _raw = _js_function(_read(LOGS_JS), 'getLogs')
        for field in ('id', 'type', 'log', 'add_time'):
            self.assertIn('logsEsc(rows[i].%s)' % field, body,
                          '面板日志 %s 未转义（存储型 XSS）' % field)
            self.assertNotIn('+ rows[i].%s +' % field, body)

    def test_esc_helper_escapes_amp_first(self):
        src = _read(LOGS_JS)
        self.assertIn('function logsEsc(', src)
        body, raw = _js_function(src, 'logsEsc')
        # 结构：5 次 replace（& < > " '）——掩码上数，注释蒙混无效
        self.assertEqual(body.count('.replace('), 5)
        # 内容：& 必须最先转义（否则 &lt; 会被二次转义/绕过）
        self.assertIn('&amp;', raw)
        self.assertLess(raw.index('&amp;'), raw.index('&lt;'))

    def test_no_undefined_str_call(self):
        self.assertNotIn('str(e)', _read(LOGS_JS))


if __name__ == '__main__':
    unittest.main()
