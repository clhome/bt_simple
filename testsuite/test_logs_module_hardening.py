# coding:utf-8
"""日志模块硬化回归。

覆盖本轮修复的六类问题：

1. ``lastlog`` 在本地化（中文等）环境下解析越界导致接口 500；
2. ``last``（wtmp/btmp/utmp）同类越界；
3. 日志审计 ``log_name`` 未校验 → ``/var/log`` 之外的任意文件读取 + 命令注入；
4. ``last``/``lastlog`` 日志内容未转义 → 日志审计页存储型 XSS；
5. 面板操作日志 ``getLogsList`` 的 ``search`` 拼接 SQL（注入）与无上限分页；
6. 前端日志页缺少 ``.fail()`` 处理，后端 500 时 loading 遮罩永久卡死。
"""
import ast
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'web'))

import utils.adult_log as adult_log  # noqa: E402

ADULT_LOG = os.path.join(ROOT, 'web', 'utils', 'adult_log.py')
THISDB_LOGS = os.path.join(ROOT, 'web', 'thisdb', 'logs.py')
LOGS_ROUTE = os.path.join(ROOT, 'web', 'admin', 'logs', '__init__.py')
LOGS_JS = os.path.join(ROOT, 'web', 'static', 'app', 'logs.js')


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def _unparse(path):
    return ast.unparse(ast.parse(_read(path)))


def _fake_exec(out):
    def _fn(*args, **kwargs):
        return (out, '')
    return _fn


class TestLastlogParsing(unittest.TestCase):
    """P0：lastlog 本地化/异常行不得崩溃。"""

    def _run(self, out):
        with mock.patch.object(adult_log.yf, 'execShell', _fake_exec(out)), \
             mock.patch.object(adult_log.yf, 'writeFileLog', lambda *a, **k: True):
            return adult_log.getAuditLastLog()

    def test_english_output(self):
        out = ('root             pts/0    172.17.11.248    Wed Sep 30 08:01:31 +0800 2026\n'
               'daemon                                      **Never logged in**\n')
        res = self._run(out)
        self.assertTrue(res['status'])
        self.assertEqual(res['data'][0]['最后登录时间'], '2026-09-30 08:01:31')
        self.assertEqual(res['data'][1]['最后登录时间'], '从未登录过')

    def test_localized_never_logged_in_does_not_crash(self):
        """旧实现在此抛 IndexError -> /logs/get_audit_file 返回 500。"""
        out = ('root             pts/0    172.17.11.248    Wed Sep 30 08:01:31 +0800 2026\n'
               'daemon                                      **从未登录过**\n'
               'bin                                         **从未登录过**\n')
        res = self._run(out)
        self.assertTrue(res['status'])
        self.assertEqual(len(res['data']), 3)
        self.assertEqual(res['data'][1]['最后登录时间'], '从未登录过')

    def test_blank_and_short_lines(self):
        res = self._run('   \n\ndaemon\nbroken words\n')
        self.assertTrue(res['status'])
        for row in res['data']:
            self.assertEqual(row['最后登录时间'], '从未登录过')

    def test_locale_forced_in_command(self):
        captured = {}

        def _cap(cmd, timeout=None):
            captured['cmd'] = cmd
            captured['timeout'] = timeout
            return ('', '')

        with mock.patch.object(adult_log.yf, 'execShell', _cap), \
             mock.patch.object(adult_log.yf, 'writeFileLog', lambda *a, **k: True):
            adult_log.getAuditLastLog()
        self.assertIn('LC_ALL=C', captured['cmd'])
        self.assertIn('LANGUAGE=C', captured['cmd'])
        self.assertIsNotNone(captured['timeout'])


class TestLastParsing(unittest.TestCase):
    """wtmp/btmp/utmp（last）解析：正常行可用、异常行不崩。"""

    def _run(self, out):
        with mock.patch.object(adult_log.yf, 'execShell', _fake_exec(out)), \
             mock.patch.object(adult_log.yf, 'writeFileLog', lambda *a, **k: True):
            return adult_log.getAuditLast('/var/log/wtmp')

    def test_wtmp_rows(self):
        out = ('root     pts/0        172.17.11.248    Wed Sep 30 08:01   still logged in\n'
               'runlevel (to lvl 5)   6.1.0-47-amd64   Mon Sep 22 12:46 - 12:46  (00:00)\n'
               'reboot   system boot  6.1.0-47-amd64   Mon Sep 22 12:41   still running\n')
        res = self._run(out)
        self.assertTrue(res['status'])
        self.assertEqual(len(res['data']), 3)
        self.assertEqual(res['data'][0]['端口'], 'pts/0')
        self.assertEqual(res['data'][0]['来源'], '172.17.11.248')

    def test_short_lines_do_not_crash(self):
        res = self._run('x\n\nlone\n')
        self.assertTrue(res['status'])


class TestSafeLogPath(unittest.TestCase):
    """P0 安全：日志名白名单 + realpath 包含校验。"""

    def test_accepts_normal_names(self):
        for name in ('wtmp', 'lastlog', 'sa/sa01', 'nginx/access.log', 'auth.log'):
            self.assertIsNotNone(adult_log._safeLogPath(name), name)

    def test_rejects_traversal_and_injection(self):
        bad = ('../../etc/shadow', '/etc/passwd', 'wtmp; id', 'a b',
               '....//etc/passwd', 'foo|bar', '$(id)', '`id`', 'a\nb', '', None)
        for name in bad:
            self.assertIsNone(adult_log._safeLogPath(name), name)

    def test_rejects_symlink_escape(self):
        """realpath 后的目标必须仍在 /var/log 内（挡住软链逃逸）。"""
        def _fake_realpath(p):
            return adult_log._LOG_DIR if p == adult_log._LOG_DIR else '/etc/passwd'
        with mock.patch.object(adult_log.os.path, 'realpath', side_effect=_fake_realpath):
            self.assertIsNone(adult_log._safeLogPath('foo'))

    def test_get_audit_name_rejects_bad(self):
        with mock.patch.object(adult_log.yf, 'execShell', _fake_exec('')):
            for name in ('../../etc/shadow', 'wtmp; id', '/etc/passwd', 'nope.log'):
                res = adult_log.getAuditLogsName(name)
                self.assertFalse(res['status'], name)


class TestXssEscaping(unittest.TestCase):
    """P1 安全：日志内容进入前端 HTML 前必须转义。"""

    def test_lastlog_values_escaped(self):
        out = 'root             pts/0    <b>evil</b>    Wed Sep 30 08:01:31 +0800 2026\n'
        with mock.patch.object(adult_log.yf, 'execShell', _fake_exec(out)), \
             mock.patch.object(adult_log.yf, 'writeFileLog', lambda *a, **k: True):
            res = adult_log.getAuditLastLog()
        joined = ' '.join(str(v) for v in res['data'][0].values())
        self.assertNotIn('<b>', joined)
        self.assertIn('&lt;b&gt;', joined)


class TestSourceGuards(unittest.TestCase):
    """源码级守卫：防止修复被回退（用 AST，避免被注释/字符串骗过）。"""

    def test_no_unquoted_shell_concat_in_audit(self):
        src = _unparse(ADULT_LOG)
        self.assertNotIn('sar -f /var/log/{}', src)
        self.assertIn('shlex.quote', src)
        self.assertIn('_safeLogPath', src)

    def test_getlogslist_is_parameterized(self):
        src = _unparse(THISDB_LOGS)
        self.assertIn('type like ? or log like ?', src)
        # 旧实现： " type like '%" + search + "%' or ..."（把用户输入拼进 SQL）
        self.assertNotIn("like '%", src)

    def test_getlogslist_bounds_page_size(self):
        src = _unparse(THISDB_LOGS)
        self.assertIn('min(200, int(size))', src)

    def test_route_get_audit_file_has_try(self):
        tree = ast.parse(_read(LOGS_ROUTE))
        fn = next((n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == 'get_audit_file'), None)
        self.assertIsNotNone(fn)
        self.assertTrue(any(isinstance(n, ast.Try) for n in ast.walk(fn)))


class TestFrontendGuards(unittest.TestCase):
    def test_js_has_fail_handlers(self):
        src = _read(LOGS_JS)
        # 两个日志审计请求都必须有 .fail()，否则后端 500 时遮罩会永久卡住
        self.assertGreaterEqual(src.count('.fail(function'), 2)

    def test_js_no_undefined_str_call(self):
        src = _read(LOGS_JS)
        self.assertNotIn('str(e)', src)


if __name__ == '__main__':
    unittest.main()
