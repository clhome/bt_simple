# coding: utf-8
"""SSRF / 传输安全回归（task.md 第 1 层 C1/C2）。

  C1 计划任务下载：初始 URL 与每次 302 跳转都要做 SSRF 校验；不得用全局 socket 超时
  C2 出口 HTTPS：验证优先，失败再降级（不再无条件 CERT_NONE）
"""
import ast
import os
import sys
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
WEB_DIR = os.path.join(project_dir, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)


def _read(rel):
    with open(os.path.join(project_dir, rel), encoding='utf-8') as f:
        return f.read()


class TestDownloadSsrf(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._cwd = os.getcwd()
        sys.path.insert(0, WEB_DIR)
        cls.src = _read('panel_task.py')

    def test_redirect_handler_present(self):
        self.assertIn('_make_safe_redirect_handler', self.src)
        body = self.src.split('def _make_safe_redirect_handler')[1].split('\ndef downloadFile')[0]
        self.assertIn('_validate(newurl', body,
                      '重定向每一跳都必须重新做 SSRF 校验')

    def test_no_global_socket_timeout(self):
        self.assertNotIn('socket.setdefaulttimeout', self.src,
                         '全局 socket 默认超时会污染整个进程')
        self.assertNotIn('urlretrieve', self.src,
                         'urlretrieve 无法校验重定向，已改为自建 opener 流式下载')

    def test_runtime_redirect_to_private_blocked(self):
        import urllib.request
        import urllib.error
        import panel_task
        try:
            handler = panel_task._make_safe_redirect_handler()
            req = urllib.request.Request('http://example.com/')
            with self.assertRaises(urllib.error.HTTPError):
                handler.redirect_request(
                    req, None, 302, 'Found', {},
                    'http://169.254.169.254/latest/meta-data/')
            with self.assertRaises(urllib.error.HTTPError):
                handler.redirect_request(
                    req, None, 302, 'Found', {},
                    'http://127.0.0.1:7200/admin')
        finally:
            os.chdir(self._cwd)


class TestOutboundTls(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _read('web/core/yf.py')

    def test_pool_defaults_to_verify(self):
        body = self.src.split('def _get_http_pool')[1].split('\ndef _pool_request')[0]
        self.assertIn("cert_reqs='CERT_REQUIRED'", body,
                      '默认连接池必须校验证书')
        self.assertIn('insecure', body)

    def test_pool_request_falls_back(self):
        body = self.src.split('def _pool_request')[1].split('\ndef HttpGet')[0]
        self.assertIn('for insecure in (False, True)', body,
                      '必须先验证、失败再降级')

    def test_http_methods_use_pool_request(self):
        for fn in ('HttpGet', 'HttpGet2', 'HttpPost'):
            body = self.src.split('def ' + fn + '(')[1].split('\ndef ')[0]
            self.assertIn('_pool_request(', body, fn)


if __name__ == '__main__':
    unittest.main()
