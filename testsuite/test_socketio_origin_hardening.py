# coding: utf-8
"""Socket.IO 跨域/同源来源校验（CSWSH 防护与脱离请求上下文兼容）测试。

被测目标：
  * 后端 `web/core/security.py:check_socketio_origin_allowed` 与 `web/admin/__init__.py:check_socketio_origin`
  * 前端 `web/static/app/public.js` 本地终端事件与生命周期管理

背景：
  用户在面板文件管理中点击命令行图标打开终端时，控制台报错：
    1. Permissions policy violation: unload is not allowed in this document
    2. POST .../socket.io/?... 400 (BAD REQUEST)
    3. WebSocket connection to ws://... failed
  根本原因是 Engine.IO WSGI 回调在 Flask 请求上下文外执行，解引用 request.host 触发
  RuntimeError 被吞并导致返回 False，同时前端使用过时的 unload 监听器。
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

from core.security import check_socketio_origin_allowed


class SocketIOOriginSecurityTests(unittest.TestCase):
    def test_01_empty_origin_allowed(self):
        """无 Origin 请求头（同源标准 GET 等）必须直接放行。"""
        self.assertTrue(check_socketio_origin_allowed(None))
        self.assertTrue(check_socketio_origin_allowed(''))

    def test_02_loopback_origins_allowed(self):
        """本地回环地址（127.0.0.1 / localhost / ::1）无论是否有 context 均放行。"""
        self.assertTrue(check_socketio_origin_allowed('http://127.0.0.1:60374'))
        self.assertTrue(check_socketio_origin_allowed('http://localhost:60374'))
        self.assertTrue(check_socketio_origin_allowed('http://[::1]:60374'))

    def test_03_outside_request_context_does_not_raise(self):
        """在 Flask request context 之外调用绝对不能抛出 RuntimeError，必须优雅处理。"""
        # 模拟没有 Flask 上下文，纯 WSGI environ
        env = {'HTTP_HOST': '172.17.60.248:60374'}
        self.assertTrue(check_socketio_origin_allowed('http://172.17.60.248:60374', environ=env),
                        '同源 Host 必须放行')

        # 传 WSGI environ 反代 X-Forwarded-Host
        env_fwd = {'HTTP_X_FORWARDED_HOST': 'panel.example.com:443', 'HTTP_HOST': '127.0.0.1:60374'}
        self.assertTrue(check_socketio_origin_allowed('https://panel.example.com', environ=env_fwd),
                        '反向代理 X-Forwarded-Host 必须放行')

    def test_04_cross_site_cswsh_rejected(self):
        """恶意第三方跨站来源（CSWSH 劫持）必须被坚决拦截拒绝。"""
        env = {'HTTP_HOST': '172.17.60.248:60374'}
        evil_origins = [
            'http://evil.com',
            'https://hacker.site:60374',
            'http://172.17.60.249:60374',
            'http://fake-domain.com',
        ]
        for evil in evil_origins:
            self.assertFalse(check_socketio_origin_allowed(evil, environ=env),
                             f'必须拦截恶意跨站来源: {evil}')

    def test_05_ipv6_host_parsing(self):
        """IPv6 格式的主机名和端口必须正确解析，不能因 split(':') 误截断。"""
        env_v6 = {'HTTP_HOST': '[2001:db8::1]:60374'}
        self.assertTrue(check_socketio_origin_allowed('http://[2001:db8::1]:60374', environ=env_v6),
                        '合法的同源 IPv6 地址必须放行')
        self.assertFalse(check_socketio_origin_allowed('http://[2001:db8::2]:60374', environ=env_v6),
                         '非同源 IPv6 地址必须拦截')

    def test_06_configured_panel_domain_and_server_ips(self):
        """配置了 panel_domain 或已知服务器 IP 时，Origin 必须放行。"""
        env = {'HTTP_HOST': '127.0.0.1:60374'}
        self.assertTrue(check_socketio_origin_allowed('https://my-safe-panel.com',
                                                      environ=env,
                                                      panel_domain='my-safe-panel.com'))
        self.assertTrue(check_socketio_origin_allowed('http://202.107.245.93:60374',
                                                      environ=env,
                                                      server_ips={'202.107.245.93', '172.17.60.248'}))


class FrontendTerminalHygieneTests(unittest.TestCase):
    def test_07_no_unload_listener_in_public_js(self):
        """前端 public.js 严禁使用 unload 监听器（杜绝 Permissions policy violation）。"""
        js_path = os.path.join(WEB_DIR, 'static', 'app', 'public.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertNotIn("$(window).on('unload'", content,
                         "严禁在 public.js 中绑定 $(window).on('unload'，请使用 beforeunload / pagehide")
        self.assertNotIn('.on("unload"', content)

        # 确认已使用现代生命周期事件
        self.assertIn('beforeunload.webshell', content)
        self.assertIn('pagehide.webshell', content)

    def test_08_terminal_layer_has_end_cleanup_hook(self):
        """本地终端弹窗必须配置 end 回调，确保各种方式关闭弹窗均能彻底清理资源。"""
        js_path = os.path.join(WEB_DIR, 'static', 'app', 'public.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('cleanUpWebShell', content, '必须定义 cleanUpWebShell 清理函数')
        self.assertIn('end: function ()', content, 'layer.open 必须定义 end 回调销毁定时器与终端')


class EngineIOIntegrationTests(unittest.TestCase):
    def test_09_engineio_server_cors_flow(self):
        """若环境安装了 engineio / flask_socketio，真跑 Engine.IO Server 的 _cors_allowed_origins 流程。"""
        try:
            from engineio import Server
        except ImportError:
            self.skipTest('当前环境未安装 engineio 库，跳过端到端驱动测试')

        server = Server(cors_allowed_origins=check_socketio_origin_allowed)
        environ = {
            'HTTP_ORIGIN': 'http://172.17.60.248:60374',
            'HTTP_HOST': '172.17.60.248:60374',
            'wsgi.url_scheme': 'http'
        }
        allowed = server._cors_allowed_origins(environ)
        self.assertEqual(allowed, ['http://172.17.60.248:60374'], '同源请求必须被 Engine.IO 正确放行')

        # 跨站恶意来源被拦截
        bad_environ = {
            'HTTP_ORIGIN': 'http://evil.com',
            'HTTP_HOST': '172.17.60.248:60374',
            'wsgi.url_scheme': 'http'
        }
        bad_allowed = server._cors_allowed_origins(bad_environ)
        self.assertEqual(bad_allowed, [], '恶意跨站必须返回空列表，Engine.IO 将拒绝并返回 400')


if __name__ == '__main__':
    unittest.main()
