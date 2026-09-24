# coding: utf-8
"""新增安全加固的回归门禁：
  * Item2 S2/S3 —— verify_login 限流、统一文案、遗留弱哈希即时升级
  * Item3 R2     —— requirements 依赖约束修正 / simple-websocket
  * Item4 S4/S5  —— 文件路径 safePath 统一校验、SSRF DNS 解析校验
  * Item5        —— 登录缓存淘汰

全部为离线静态/AST 断言，不依赖 flask、不发起网络请求。
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


class TestUrlGuard(unittest.TestCase):
    """urlguard 仅依赖标准库，可直接导入并做纯离线断言。"""

    @classmethod
    def setUpClass(cls):
        from utils import urlguard
        cls.ug = urlguard

    def test_public_ip_classification(self):
        ug = self.ug
        self.assertTrue(ug.is_public_ip('8.8.8.8'))
        self.assertTrue(ug.is_public_ip('1.1.1.1'))
        for bad in ('127.0.0.1', '10.0.0.5', '192.168.1.10', '172.16.3.4',
                    '169.254.169.254', '::1', 'fc00::1', '0.0.0.0'):
            self.assertFalse(ug.is_public_ip(bad), bad)

    def test_parse_url_rejects_dangerous_forms(self):
        ug = self.ug
        for bad in ('file:///etc/passwd', 'gopher://x/', 'http://user:pass@example.com/',
                    'http://localhost/', 'http://metadata.google.internal/', '',
                    'not-a-url', 'http:///nohost'):
            meta, err = ug.parse_url(bad)
            self.assertIsNone(meta, bad)

    def test_validate_url_ip_literal(self):
        ug = self.ug
        ok, _err, _meta = ug.validate_url('http://127.0.0.1:7200/admin', resolve=False)
        self.assertFalse(ok)
        ok, _err, meta = ug.validate_url('http://8.8.8.8/x', resolve=False)
        self.assertTrue(ok)
        self.assertTrue(meta['host_is_ip'])

    def test_validate_url_domain_no_dns(self):
        ug = self.ug
        ok, _err, meta = ug.validate_url('https://example.com/path', resolve=False)
        self.assertTrue(ok)
        self.assertFalse(meta['host_is_ip'])
        self.assertEqual(meta['port'], 443)

    def test_resolve_arg_from_meta(self):
        ug = self.ug
        meta = {'host': 'example.com', 'port': 443, 'host_is_ip': False,
                'ips': ['203.0.113.10']}
        self.assertEqual(ug.resolve_arg_from_meta(meta), 'example.com:443:203.0.113.10')
        v6 = {'host': 'example.com', 'port': 8443, 'host_is_ip': False,
              'ips': ['2001:4860:4860::8888']}
        self.assertEqual(ug.resolve_arg_from_meta(v6),
                         'example.com:8443:[2001:4860:4860::8888]')
        self.assertEqual(ug.resolve_arg_from_meta(
            {'host': '8.8.8.8', 'port': 80, 'host_is_ip': True, 'ips': []}), '')


class TestSafePath(unittest.TestCase):
    """从 utils/file.py 抽取 safePath 纯函数执行（避免导入 flask/thisdb）。"""

    @classmethod
    def setUpClass(cls):
        src = _read('web/utils/file.py')
        tree = ast.parse(src)
        want_assign = {'_SENSITIVE_PATHS', '_SENSITIVE_EXACT', '_PANEL_SENSITIVE_REL'}
        want_func = {'safePath', '_posix_norm'}
        keep = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    getattr(t, 'id', '') in want_assign for t in node.targets):
                keep.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name in want_func:
                keep.append(node)
        ns = {'os': os}

        class _FakeYf:
            @staticmethod
            def getPanelDir():
                return '/www/server/yufeng_panel'

        ns['yf'] = _FakeYf()
        exec(compile(ast.Module(body=keep, type_ignores=[]), 'file_safePath', 'exec'), ns)
        cls.safePath = staticmethod(ns['safePath'])

    def test_allows_normal_ops_paths(self):
        for p in ('/www/wwwroot/a.php', '/www/server/openresty/conf/nginx.conf',
                  '/var/log/nginx/access.log', '/etc/nginx/conf.d/a.conf', '/tmp/x.php',
                  '/www/server/yufeng_panel/web/utils/file.py'):
            ok, _reason = self.safePath(p)
            self.assertTrue(ok, p)

    def test_blocks_sensitive_system_paths(self):
        for p in ('/etc/passwd', '/etc/shadow', '/etc/ssh/sshd_config',
                  '/root/.ssh/authorized_keys', '/etc/cron.d/evil',
                  '/var/spool/cron/root', '/etc/passwd/..'):
            ok, reason = self.safePath(p)
            self.assertFalse(ok, p)
            self.assertEqual(reason, 'FILE_DANGER')

    def test_blocks_system_roots(self):
        for p in ('/', '/etc', '/www', '/www/server', '/root', '/usr'):
            ok, _reason = self.safePath(p)
            self.assertFalse(ok, p)

    def test_blocks_panel_own_assets(self):
        for p in ('/www/server/yufeng_panel/data/panel.db',
                  '/www/server/yufeng_panel/ssl/private.pem',
                  '/www/server/yufeng_panel/web/admin/__init__.py'):
            ok, reason = self.safePath(p)
            self.assertFalse(ok, p)
            self.assertEqual(reason, 'FILE_DANGER')

    def test_rejects_empty_and_nul(self):
        for p in ('', None, '/tmp/a\x00b'):
            ok, _reason = self.safePath(p)
            self.assertFalse(ok, repr(p))


class TestStaticHardening(unittest.TestCase):

    def test_requirements_constraints(self):
        req = _read('requirements.txt')
        # 只检查真实依赖行（忽略注释/空行）
        lines = [l.strip() for l in req.splitlines()
                 if l.strip() and not l.strip().startswith('#')]
        self.assertFalse(any(l.startswith('requests>=2.34.2') for l in lines))
        self.assertFalse(any(l.startswith('flask-session') for l in lines))
        self.assertTrue(any(l.startswith('simple-websocket') for l in lines))
        self.assertTrue(any(l.startswith('flask-socketio>=5.3.0') for l in lines))
        self.assertTrue(any(l.startswith('python-engineio>=4.6.0') for l in lines))

    def test_login_shared_rate_limit(self):
        src = _read('web/admin/dashboard/login.py')
        for token in ('_register_login_failure', '_is_banned', '_reset_login_failure',
                      '_password_matches', '_login_success'):
            self.assertIn('def ' + token, src)
        verify = src.split('def verifyLogin')[1].split('def do_login')[0]
        # 2FA 第二步必须复用限流，不能成为旁路
        self.assertIn('_register_login_failure', verify)
        self.assertIn('_is_banned', verify)
        # 未开启二步验证时不得登录
        self.assertIn("two_step_verification.get('open')", verify)

    def test_login_weak_hash_upgrade(self):
        src = _read('web/admin/dashboard/login.py')
        body = src.split('def _password_matches')[1].split('def _login_success')[0]
        self.assertIn('_upgrade_password', body)
        self.assertIn('legacy_md5', body)

    def test_crontab_delegates_to_urlguard(self):
        src = _read('web/utils/crontab.py')
        self.assertIn('from utils.urlguard import validate_url', src)
        self.assertNotIn('import ipaddress', src)
        # 运行时二次解析 + curl --resolve 锁 IP
        self.assertIn('urlguard.py', src)
        self.assertIn('--resolve', src)

    def test_download_task_ssrf_guard(self):
        src = _read('panel_task.py')
        body = src.split('def downloadFile')[1].split('def runPanelTask')[0]
        self.assertIn('validate_url', body)

    def test_login_cache_pruning(self):
        src = _read('web/admin/common.py')
        self.assertIn('_prune_login_cache', src)
        self.assertIn('_LOGIN_CACHE_MAX', src)

    def test_file_manager_calls_safepath(self):
        src = _read('web/utils/file.py')
        for fn in ('getFileBody', 'saveBody', 'fileDelete', 'dirDelete',
                   'copyFile', 'createFile', 'createDir', 'setFileAccess'):
            body = src.split('def ' + fn + '(')[1].split('\ndef ')[0]
            self.assertIn('safePath(', body, fn)


if __name__ == '__main__':
    unittest.main()
