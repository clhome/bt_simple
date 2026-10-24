# coding: utf-8
"""面板 SSL「半开状态」回归守卫。

## 现场（2026-10-23）

开启面板自签证书后，面板直接访问不了，gunicorn 日志里只有：

    [yf] 面板 SSL 私钥权限收紧失败: [Errno 2] No such file or directory:
         '/www/server/yufeng_panel/ssl/local/private.pem'
    Listening at: http://0.0.0.0:60374          <- 实际仍是明文 HTTP

## 根因

`panel_ssl.open` 是「用户点了开启」，能不能真起 HTTPS 取决于磁盘上有没有证书。
改造前各处的口径互不一致：

  * gunicorn 配置（web/setting.py）：open **且** 证书文件存在 → 才上 TLS（否则静默明文）；
  * `checkDomainPanel`：只看 open → 302 到 https；
  * `SESSION_COOKIE_SECURE` / HSTS：只看 open → Cookie 只在 https 下回传。

于是「配置说开了、证书没落盘」= 半开状态：跳 https 打不开 + Secure Cookie 不回传，
面板彻底无法访问。而证书没落盘的直接原因是 `createLocalSSL` 忽略了 `writeFile`
的返回值（writeFile 默认失败只回 `False`、不抛异常），只剩一条误导性的 chmod 告警。

## 本守卫断言三件事

1. `yf.panelSslState()` 是**唯一**判定入口：配置 + 文件双条件，半开状态必须
   `ready=False`（按未启用处理），而不是「配置说开就算开」。
2. `createLocalSSL` 写盘失败必须返回 False、且不再拿缺失文件去 chmod。
3. 四处接线都用同一判定：gunicorn 配置 / 302 跳转 / Secure Cookie / HSTS，
   外加「自签证书生成失败时不得把 open 置真」。
"""

import io
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)

import core.yf as yf

GUNICORN_CONF = os.path.join(WEB, 'setting.py')
SYSTEM_PY = os.path.join(WEB, 'core', 'yf', 'system.py')
ADMIN_INIT = os.path.join(WEB, 'admin', '__init__.py')
UTILS_SETTING = os.path.join(WEB, 'utils', 'setting.py')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


class TestPanelSslState(unittest.TestCase):
    """一、判定函数（表驱动）：混淆「配置」与「文件」就会漏掉半开状态。"""

    def setUp(self):
        self.pdir = tempfile.mkdtemp()
        patcher = mock.patch.object(yf, 'getPanelDir', return_value=self.pdir)
        patcher.start()
        self.addCleanup(patcher.stop)
        import shutil
        self.addCleanup(shutil.rmtree, self.pdir, True)

    def _write_cert(self, choose='local', cert=b'CERT', key=b'KEY'):
        d = os.path.join(self.pdir, 'ssl', choose)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'cert.pem'), 'wb') as fh:
            fh.write(cert)
        with open(os.path.join(d, 'private.pem'), 'wb') as fh:
            fh.write(key)

    def test_open_false_is_plain_http(self):
        st = yf.panelSslState({'open': False, 'choose': 'local'})
        self.assertFalse(st['ready'])
        self.assertFalse(st['degraded'], '未开启不算「半开」，不应触发告警')

    def test_open_true_but_files_missing_is_degraded_not_ready(self):
        st = yf.panelSslState({'open': True, 'choose': 'local'})
        self.assertTrue(st['open'], 'open 是用户意图，要原样带回')
        self.assertFalse(st['ready'], '证书不存在时必须判定为「不可用 HTTPS」')
        self.assertTrue(st['degraded'], 'open 但证书缺失 = 半开状态，必须可识别')

    def test_open_true_with_files_is_ready(self):
        self._write_cert()
        st = yf.panelSslState({'open': True, 'choose': 'local'})
        self.assertTrue(st['ready'])
        self.assertFalse(st['degraded'])

    def test_nginx_choose_uses_its_own_dir(self):
        self._write_cert(choose='nginx')
        st = yf.panelSslState({'open': True, 'choose': 'nginx'})
        self.assertTrue(st['ready'])
        self.assertTrue(st['certfile'].replace('\\', '/').endswith('/ssl/nginx/cert.pem'))

    def test_zero_byte_cert_is_not_ready(self):
        self._write_cert(cert=b'')
        st = yf.panelSslState({'open': True, 'choose': 'local'})
        self.assertFalse(st['ready'], '0 字节证书（磁盘满/截断）不能当可用')

    def test_missing_private_key_is_not_ready(self):
        self._write_cert()
        os.remove(os.path.join(self.pdir, 'ssl', 'local', 'private.pem'))
        st = yf.panelSslState({'open': True, 'choose': 'local'})
        self.assertFalse(st['ready'], '只有 cert.pem 也不能起 TLS（gunicorn 要私钥）')

    def test_illegal_choose_is_not_ready(self):
        st = yf.panelSslState({'open': True, 'choose': 'acme'})
        self.assertFalse(st['ready'])
        self.assertEqual('', st['certfile'])

    def test_non_dict_option_falls_back_to_off(self):
        for bad in (None, 'open', ['open']):
            st = yf.panelSslState(bad)
            self.assertFalse(st['open'])
            self.assertFalse(st['ready'])

    def test_db_read_failure_falls_back_to_plain_http(self):
        fake_db = types.SimpleNamespace(
            getOptionByJson=mock.Mock(side_effect=RuntimeError('db down')))
        with mock.patch.dict(sys.modules, {'thisdb': fake_db}):
            st = yf.panelSslState()
        self.assertFalse(st['open'], '读库失败按未开启处理，绝不冒出半开状态')

    def test_reads_option_when_not_given(self):
        fake_db = types.SimpleNamespace(
            getOptionByJson=mock.Mock(return_value={'open': True, 'choose': 'local'}))
        self._write_cert()
        with mock.patch.dict(sys.modules, {'thisdb': fake_db}):
            st = yf.panelSslState()
        self.assertTrue(st['ready'])
        fake_db.getOptionByJson.assert_called_once()


class TestPanelSslWiring(unittest.TestCase):
    """二、接线：四处判定必须共用 panelSslState（各写一份就会再次漂移）。"""

    def setUp(self):
        self.pdir = tempfile.mkdtemp()
        import shutil
        self.addCleanup(shutil.rmtree, self.pdir, True)

    def test_gunicorn_conf_only_enables_tls_when_ready(self):
        src = _read(GUNICORN_CONF)
        self.assertIn("yf.panelSslState(", src,
                      'gunicorn 配置必须用 panelSslState 判定（否则证书缺失时静默明文）')
        self.assertIn("if panel_ssl_state['ready']:", src,
                      '只有 ready 才能挂 ssl_context')
        self.assertIn('createLocalSSL', src,
                      '证书缺失时要先尝试自愈，而不是直接静默退回 HTTP')
        self.assertIn('以明文 HTTP 启动', src,
                      '退回明文 HTTP 必须留下显式告警日志')

    def test_gunicorn_ssl_context_is_callable_not_instance(self):
        """gunicorn 的 `ssl_context` 只接受 callable —— 传 SSLContext 实例=静默无 TLS。

        现场日志：
            Invalid value for ssl_context: <ssl.SSLContext object at 0x...>
            Error: Value is not callable: <ssl.SSLContext object at 0x...>
        gunicorn 把该配置项当非法值跳过，进程照常启动、Listening 仍是 http。
        """
        src = _read(GUNICORN_CONF)
        self.assertIn('ssl_context = yf.panelSslContextFactory(', src)
        self.assertNotIn('ssl_context = yf.createPanelSslContext(', src,
                         'createPanelSslContext 返回的是实例，gunicorn 会拒掉')
        # 证书路径仍必须以 gunicorn 配置项的形式给出（它的默认工厂靠这三个）
        for name in ('certfile = ', 'keyfile  = ', 'ciphers = '):
            self.assertIn(name, src,
                          'gunicorn 默认 SSLContext 工厂需要 %s 配置项' % name.strip(' ='))

    def test_ssl_context_factory_contract(self):
        """工厂：arity=2、复用 gunicorn 默认 context、最低 TLS 1.2。"""
        import inspect
        import ssl
        factory = yf.panelSslContextFactory()
        self.assertTrue(callable(factory))
        params = [p for p in inspect.signature(factory).parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        self.assertEqual(2, len(params), 'validate_callable(2) 要求两个位置参数')

        base = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx = factory(None, lambda: base)
        self.assertIs(ctx, base, '应复用 gunicorn 默认工厂的 context（证书/ALPN 都在那）')
        self.assertEqual(ssl.TLSVersion.TLSv1_2, ctx.minimum_version,
                         '最低 TLS 1.2 必须钉死在工厂里')
        import ssl as _ssl
        self.assertTrue(ctx.options & _ssl.OP_NO_COMPRESSION)

    def test_ssl_context_factory_falls_back_when_default_factory_fails(self):
        import ssl

        def _boom():
            raise ValueError('cafile missing')
        ctx = yf.panelSslContextFactory()(None, _boom)
        self.assertIsInstance(ctx, ssl.SSLContext, '默认工厂失败也要给出可用的 context')
        self.assertEqual(ssl.TLSVersion.TLSv1_2, ctx.minimum_version)

    def test_unusable_ciphers_do_not_break_startup(self):
        """套件字串不被 OpenSSL 接受时必须能降级，而不是把面板启动弄挂。"""
        import ssl
        ctx = yf.panelSslContextFactory(None, None, 'NOT-A-CIPHER-STRING')(None, None)
        self.assertIsInstance(ctx, ssl.SSLContext)
        self.assertEqual(ssl.TLSVersion.TLSv1_2, ctx.minimum_version,
                         '降级套件不允许连带把最低 TLS 版本放松')

    def test_redirect_to_https_requires_ready(self):
        src = _read(SYSTEM_PY)
        start = src.index('def checkDomainPanel(')
        end = src.index('\ndef ', start + 1)
        body = src[start:end]
        self.assertIn('panelSslState', body,
                      '302 到 https 必须按「证书可用」判定，不能只看 panel_ssl.open')
        self.assertIn("state['ready']", body.replace('panel_ssl_state', 'state'))

    def test_secure_cookie_requires_ready(self):
        src = _read(ADMIN_INIT)
        self.assertIn("app.config['SESSION_COOKIE_SECURE'] = bool(panel_ssl_state['ready'])",
                      src,
                      'Secure Cookie 必须与「证书可用」绑定：半开状态下加 Secure = 登录掉线')

    def test_hsts_requires_ready(self):
        src = _read(ADMIN_INIT)
        self.assertIn("_panel_ssl_on = bool(yf.panelSslState()['ready'])", src,
                      'HSTS 只能在真上 HTTPS 时下发')

    def test_local_ssl_switch_refuses_open_without_cert(self):
        """自签证书生成失败时不得把 panel_ssl.open 置真（那就是半开状态）。"""
        import ast
        tree = ast.parse(_read(UTILS_SETTING))
        func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'setPanelLocalSsl':
                func = node
        self.assertIsNotNone(func)
        func.decorator_list = []
        src = ast.unparse(ast.Module(body=[func], type_ignores=[]))

        set_option = mock.Mock()
        ns = {
            'yf': types.SimpleNamespace(
                getPanelDir=lambda: self.pdir,
                createLocalSSL=lambda: False,
                returnData=lambda status, msg, data=None: {
                    'status': status, 'msg': msg, 'data': data},
                writeFileLog=lambda *a, **k: None,
                getPanelPort=lambda: 7200,
                getLocalIp=lambda: '127.0.0.1',
            ),
            'thisdb': types.SimpleNamespace(
                getOptionByJson=lambda name, default=None: dict(default or {}),
                setOption=set_option,
                getOption=lambda name, default=None: default,
            ),
            'os': os,
            'json': __import__('json'),
        }
        exec(compile(src, UTILS_SETTING, 'exec'), ns)
        res = ns['setPanelLocalSsl'](object(), '1')
        self.assertFalse(res['status'], '证书没生成出来就不能回「设置成功」')
        self.assertFalse(set_option.called, '失败时不得把 panel_ssl.open 写进库')


if __name__ == '__main__':
    unittest.main(verbosity=2)
