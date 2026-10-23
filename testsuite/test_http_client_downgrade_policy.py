# coding: utf-8
"""P2-6 守卫：HTTP 客户端「用途分级」降级策略（不许静默降级）。

背景
----
`web/core/yf/net.py` 的出站客户端原本在 TLS 校验失败时**静默降级为不校验证书**
（`_pool_request` 的 `for insecure in (False, True)` 吞掉所有异常再换不验证的池，
`HttpGet`/`HttpGet2`/`HttpPost` 失败后还会无条件再落一次 `_insecure_ssl_context()`），
全程没有一行告警。凭据类请求（path 里带 bot token）与代码类下载一旦被中间人诱导
降级就是直接失守；而本机探测类请求在缺 CA 束的老系统上又确实需要降级。

因此按用途分级：`low` 允许降级但**必须留痕**；`code` / `credential` 禁止降级，
校验失败即放弃并写明确原因。日志里的 URL 必须脱敏（去 query string 与 userinfo）。

本用例锁死的六件事
------------------
1. `code` / `credential`：验证池抛 `ssl.SSLError` 时**不得**用不验证池，返回
   `None`/错误串，且写日志；
2. `low`：同样替身下**必须**降级、拿到数据，且日志含「降级」与脱敏 URL；
3. 无静默路径：遍历三种 purpose，只要发生过降级，就一定有一条日志；
4. 脱敏：日志里不得出现 `pass` / `SECRET` / `token=`，但要有 host 与 path；
5. 默认值兼容：不传 purpose 按 `low`（既有调用点不因签名变化报错），
   `HttpGet`/`HttpGet2`/`HttpPost` 以及包级 `yf.httpGet`/`yf.httpPost` 都验；
6. 静态断言：`_insecure_ssl_context()` 的**使用点**必须落在「purpose 为 low 的
   分支」内（AST 祖先 `if` 判定），不能出现在无条件路径上。

零外部依赖：只用标准库，不联网（池与 urlopen 全部替身化）。
"""
import ast
import os
import ssl
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
for _p in (ROOT, WEB):
    if _p not in sys.path:
        sys.path.insert(0, _p)

NET_PY = os.path.join(WEB, 'core', 'yf', 'net.py')

#: 脱敏用例用的 URL：userinfo + query string 都夹带凭据
SECRET_URL = 'https://user:pass@example.com/a/b?token=SECRET&x=1'
#: 脱敏后应当保留的部分
URL_HOST_PART = 'example.com'
URL_PATH_PART = '/a/b'
#: 日志里绝不允许出现的内容（凭据）
URL_SECRET_PARTS = ('pass', 'SECRET', 'token=')

#: 不验证池成功时返回的固定内容（用来断言「真的走了降级通道并拿到数据」）
INSECURE_BODY = 'DATA-FROM-INSECURE-POOL'


def _read_net():
    with open(NET_PY, encoding='utf-8') as fh:
        return fh.read()


class _FakeResp(object):
    def __init__(self, data):
        self.data = data


class _FakePool(object):
    """连接池替身：`verify` 池固定抛 SSLError，`insecure` 池按配置成功或失败。"""

    def __init__(self, mode, harness):
        self.mode = mode
        self.harness = harness

    def request(self, method, url, **kwargs):
        self.harness.events.append((self.mode, method))
        if self.mode == 'verify':
            raise ssl.SSLError('certificate verify failed')
        if self.harness.insecure_error is not None:
            raise self.harness.insecure_error
        return _FakeResp(INSECURE_BODY.encode('utf-8'))


class _Harness(object):
    """一组替身：验证池必失败、不验证池可配；记录调用顺序与全部日志。"""

    def __init__(self, tc, insecure_error=None):
        self.tc = tc
        self.insecure_error = insecure_error
        self.events = []          # [('verify'|'insecure', method)]
        self.pool_requests = []   # 每次 _get_http_pool(insecure=?) 的入参
        self.urlopen_calls = []   # 每次 urllib.request.urlopen 的入参
        self.logs = []            # writeFileLog 收到的全部内容

        self.net = tc.net
        # 1) 连接池替身
        p1 = mock.patch.object(self.net, '_get_http_pool', self._get_pool)
        p1.start()
        tc.addCleanup(p1.stop)
        # 2) 日志替身（捕获而不落盘）
        p2 = mock.patch.object(self.net, 'writeFileLog', self._log)
        p2.start()
        tc.addCleanup(p2.stop)
        # 3) urlopen 替身：只要被调到就记一笔（禁止降级时必须一次都不调）
        p3 = mock.patch('urllib.request.urlopen', self._urlopen)
        p3.start()
        tc.addCleanup(p3.stop)

    def _get_pool(self, insecure=False):
        self.pool_requests.append(bool(insecure))
        return _FakePool('insecure' if insecure else 'verify', self)

    def _urlopen(self, url, *args, **kwargs):
        # 兜底通道是否「不校验」由调用方是否传了 context 判断
        self.urlopen_calls.append({'url': url,
                                   'insecure_ctx': kwargs.get('context') is not None})
        self.events.append(('urlopen',))
        raise ssl.SSLError('certificate verify failed for ' + str(url))

    def _log(self, msg, *args, **kwargs):
        self.logs.append(str(msg))
        return True

    # ---- 断言辅助 ----
    @property
    def downgraded(self):
        """是否真的降级过（要过不验证池，或走了 urlopen 兜底）。

        注意 `pool_requests` 存的是布尔量（True=要了不验证池），不是字符串，
        写成 `'insecure' in pool_requests` 会恒为 False，整个「无静默路径」
        断言就变成假绿（本轮变异自证真的绕过一次）。
        """
        return (True in self.pool_requests) or bool(self.urlopen_calls)

    def log_text(self):
        return '\n'.join(self.logs)


class HttpDowngradePolicyTest(unittest.TestCase):

    def setUp(self):
        import core.yf as yf          # noqa: F401  （确认包可导入）
        self.yf = yf
        self.net = yf.net

    # ------------------------------------------------------------------ 1
    def test_code_and_credential_never_downgrade(self):
        """code / credential：验证池失败后不许碰不验证池，返回 None/错误串，且有日志。"""
        cases = (
            ('HttpGet', 'GET', lambda: self.net.HttpGet(SECRET_URL, 3, purpose=purpose)),
            ('HttpGet2', 'GET', lambda: self.net.HttpGet2(SECRET_URL, 3, purpose=purpose)),
            ('HttpPost', 'POST', lambda: self.net.HttpPost(SECRET_URL, {'a': 'b'}, 3,
                                                          purpose=purpose)),
        )
        for purpose in (self.net.PURPOSE_CODE, self.net.PURPOSE_CREDENTIAL):
            for name, method, call in cases:
                with self.subTest(purpose=purpose, fn=name):
                    h = _Harness(self)
                    result = call()
                    # 不验证池一次都不许要、一次都不许用
                    self.assertEqual(h.pool_requests, [False],
                                     '禁止降级的 purpose 不许请求不校验证书的连接池')
                    self.assertEqual(h.events, [('verify', method)])
                    self.assertEqual(h.urlopen_calls, [],
                                     '禁止降级的 purpose 不许走 urlopen 不校验兜底')
                    # 返回值：None 或错误串（与既有失败形态一致），绝不能是数据
                    self.assertTrue(result is None or isinstance(result, str))
                    self.assertNotEqual(result, INSECURE_BODY)
                    self.assertNotIn(INSECURE_BODY, str(result))
                    if isinstance(result, str):
                        self.assertIn('禁止降级', result,
                                      '错误串必须说清「禁止降级」，不能只回一个看不懂的错误')
                    # 必须留痕，且原因里带 purpose + 脱敏 url
                    self.assertTrue(h.logs, '禁止降级也必须写日志')
                    text = h.log_text()
                    self.assertIn('purpose=%s' % purpose, text)
                    self.assertIn(URL_HOST_PART, text)
                    self.assertIn(URL_PATH_PART, text)

    # ------------------------------------------------------------------ 1b
    def test_pool_request_returns_none_for_code(self):
        """底层 `_pool_request` 在 code/credential 下直接返回 None（不降级）。"""
        for purpose in (self.net.PURPOSE_CODE, self.net.PURPOSE_CREDENTIAL):
            with self.subTest(purpose=purpose):
                h = _Harness(self)
                out = self.net._pool_request('GET', SECRET_URL, 3, purpose=purpose)
                self.assertIsNone(out)
                self.assertEqual(h.pool_requests, [False])
                self.assertTrue(h.logs)

    # ------------------------------------------------------------------ 2
    def test_low_downgrades_with_log(self):
        """low：允许降级（老系统缺 CA 仍要能用），但每次降级都要有日志。"""
        h = _Harness(self)
        data = self.net.HttpGet(SECRET_URL, 3, purpose=self.net.PURPOSE_LOW)
        self.assertEqual(data, INSECURE_BODY, 'low 必须仍能在验证失败后降级取到数据')
        self.assertEqual(h.pool_requests, [False, True],
                         'low 应当先验证、失败后尝试不验证池')
        self.assertIn('purpose=%s' % self.net.PURPOSE_LOW, h.log_text())
        self.assertTrue(any('降级' in line for line in h.logs),
                        'low 的降级必须写日志，不许静默')
        self.assertTrue(any(URL_HOST_PART in line and URL_PATH_PART in line
                            for line in h.logs),
                        '降级日志必须带脱敏 url（host + path）')

    # ------------------------------------------------------------------ 2b
    def test_low_urlopen_fallback_also_logs(self):
        """low 的 urllib 兜底同样是降级：必须留痕（这是第二个容易漏的静默点）。"""
        h = _Harness(self, insecure_error=ssl.SSLError('unverified pool broken'))
        data = self.net.HttpGet('http://127.0.0.1:8080/status', 3)
        self.assertTrue(h.urlopen_calls, 'low 在两个池都失败后仍应保留 urllib 兜底')
        self.assertTrue(h.urlopen_calls[0]['insecure_ctx'],
                        '兜底必须带不校验证书的 context（既有行为）')
        self.assertTrue(any('降级' in line for line in h.logs),
                        'urllib 兜底降级也必须写日志')
        self.assertIsInstance(data, str)   # 兜底也失败 → 错误串

    # ------------------------------------------------------------------ 3
    def test_no_silent_downgrade_path(self):
        """遍历三种 purpose + 两种替身：只要发生过降级，就一定有一条日志。"""
        for purpose in (self.net.PURPOSE_LOW, self.net.PURPOSE_CODE,
                        self.net.PURPOSE_CREDENTIAL):
            for insecure_error in (None, ssl.SSLError('unverified pool broken')):
                with self.subTest(purpose=purpose, insecure_broken=insecure_error is not None):
                    h = _Harness(self, insecure_error=insecure_error)
                    probes = (
                        ('HttpGet', lambda: self.net.HttpGet(SECRET_URL, 3, purpose=purpose)),
                        ('HttpGet2', lambda: self.net.HttpGet2(SECRET_URL, 3, purpose=purpose)),
                        ('HttpPost', lambda: self.net.HttpPost(SECRET_URL, {'a': 'b'}, 3,
                                                             purpose=purpose)),
                        ('_pool_request', lambda: self.net._pool_request('GET', SECRET_URL, 3,
                                                                        purpose=purpose)),
                    )
                    for name, call in probes:
                        h.events[:] = []
                        h.pool_requests[:] = []
                        h.urlopen_calls[:] = []
                        h.logs[:] = []
                        call()
                        if h.downgraded:
                            self.assertTrue(
                                any('降级' in line for line in h.logs),
                                'purpose=%s 走 %s 发生了降级（%r/%r）却没有任何日志'
                                % (purpose, name, h.pool_requests, h.urlopen_calls))
                        if purpose != self.net.PURPOSE_LOW:
                            self.assertFalse(h.downgraded,
                                             'code/credential 绝对不许降级')

    # ------------------------------------------------------------------ 4
    def test_url_is_masked_in_logs(self):
        """脱敏：日志里不许出现 userinfo / query string 里的凭据。"""
        # 两种降级形态都覆盖：low 池成功（降级日志）与 low 兜底也失败（错误细节）
        for insecure_error in (None, ssl.SSLError('pool broken for ' + SECRET_URL)):
            with self.subTest(insecure_broken=insecure_error is not None):
                h = _Harness(self, insecure_error=insecure_error)
                self.net.HttpGet(SECRET_URL, 3, purpose=self.net.PURPOSE_LOW)
                text = h.log_text()
                self.assertTrue(text.strip(), '必须有日志')
                for bad in URL_SECRET_PARTS:
                    self.assertNotIn(bad, text,
                                     '日志泄漏了 URL 里的凭据片段 %r：%s' % (bad, text))
                self.assertIn(URL_HOST_PART, text, '脱敏后仍要能定位主机')
                self.assertIn(URL_PATH_PART, text, '脱敏后仍要能定位接口路径')

    def test_mask_helper_contract(self):
        """脱敏函数本身的契约：scheme://host/path，去 userinfo 与 query。"""
        self.assertEqual(self.net._maskUrl(SECRET_URL),
                         'https://example.com/a/b')
        self.assertEqual(self.net._maskUrl('http://127.0.0.1/clean_waf_drop_ip'),
                         'http://127.0.0.1/clean_waf_drop_ip')
        # telegram 的 bot token 藏在 path 里，也必须擦掉
        masked_tg = self.net._maskUrl('https://api.telegram.org/bot123456:AAH-secret/sendMessage')
        self.assertNotIn('AAH-secret', masked_tg)
        self.assertIn('api.telegram.org', masked_tg)

    # ------------------------------------------------------------------ 5
    def test_default_purpose_is_low_backward_compatible(self):
        """不传 purpose 时按 low 处理：签名兼容 + 仍能降级 + 仍写日志。"""
        cases = (
            ('HttpGet', lambda: self.net.HttpGet(SECRET_URL, 3), 'GET'),
            ('HttpGet2', lambda: self.net.HttpGet2(SECRET_URL, 3), 'GET'),
            ('HttpPost', lambda: self.net.HttpPost(SECRET_URL, {'a': 'b'}, 3), 'POST'),
        )
        for name, call, method in cases:
            with self.subTest(fn=name):
                h = _Harness(self)
                data = call()
                self.assertEqual(data, INSECURE_BODY,
                                 '%s 默认分级必须是 low（可降级，保持既有行为）' % name)
                self.assertEqual(h.pool_requests, [False, True])
                self.assertTrue(any('降级' in line for line in h.logs),
                                '%s 默认分级的降级也必须写日志' % name)
                self.assertIn(('insecure', method), h.events)

        # 包级转发（既有两个入口）也必须能用旧签名调用、行为等同 low
        for name, call in (('yf.httpGet', lambda: self.yf.httpGet(SECRET_URL, 3)),
                           ('yf.httpGet(timeout=)', lambda: self.yf.httpGet(SECRET_URL, timeout=3)),
                           ('yf.httpPost', lambda: self.yf.httpPost(SECRET_URL, {'a': 'b'}, 3))):
            with self.subTest(fn=name):
                h = _Harness(self)
                data = call()
                self.assertEqual(data, INSECURE_BODY, '%s 默认分级必须是 low' % name)
                self.assertTrue(any('降级' in line for line in h.logs))

    def test_package_forward_passes_purpose(self):
        """包级转发层不许吃掉 purpose（否则 credential 会被悄悄降级成 low）。"""
        h = _Harness(self)
        self.yf.httpPost('https://api.telegram.org/bot123456:AAH-secret/sendMessage',
                         {'chat_id': '1', 'text': 'hi'}, 3,
                         purpose=self.yf.PURPOSE_CREDENTIAL)
        self.assertEqual(h.pool_requests, [False], 'credential 经转发层也必须禁止降级')
        self.assertFalse(h.urlopen_calls)
        self.assertTrue(h.logs)
        self.assertNotIn('AAH-secret', h.log_text())

    def test_purpose_constants_exported(self):
        """分级常量必须能从 yf 包直接取到（调用点用 yf.PURPOSE_* 显式标注）。"""
        self.assertEqual(self.yf.PURPOSE_LOW, 'low')
        self.assertEqual(self.yf.PURPOSE_CODE, 'code')
        self.assertEqual(self.yf.PURPOSE_CREDENTIAL, 'credential')
        self.assertEqual(self.net._PURPOSE_DOWNGRADE_ALLOWED,
                         {'low': True, 'code': False, 'credential': False})

    def test_unknown_purpose_fails_closed(self):
        """分级名拼错时按「禁止降级」处理（fail-closed），且留痕。"""
        h = _Harness(self)
        result = self.net.HttpGet(SECRET_URL, 3, purpose='loww')
        self.assertNotEqual(result, INSECURE_BODY)
        self.assertEqual(h.pool_requests, [False])
        self.assertFalse(h.urlopen_calls)
        self.assertIn('loww', h.log_text())

    # ------------------------------------------------------------------ 6
    def test_insecure_context_only_on_low_branch(self):
        """静态断言：`_insecure_ssl_context()` 的使用点只能在 low 分支内。"""
        src = _read_net()
        tree = ast.parse(src)

        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node

        usage = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, 'id', None) or getattr(func, 'attr', None)
            if name == '_insecure_ssl_context':
                usage.append(node)

        self.assertTrue(usage, 'net.py 里应当仍保留不校验证书的 context 使用点（low 兜底）')

        for call in usage:
            node = call
            guarded = False
            while node in parents:
                node = parents[node]
                if isinstance(node, ast.If):
                    test_src = ast.get_source_segment(src, node.test) or ''
                    if '_purposeAllowsDowngrade' in test_src:
                        guarded = True
                        break
                if isinstance(node, ast.FunctionDef):
                    break
            self.assertTrue(
                guarded,
                'net.py:%d 的 _insecure_ssl_context() 不在「purpose 允许降级」的分支里，'
                '等于又出现了无条件降级' % call.lineno)

        # 连接池那条降级路径同样必须过 purpose 门禁
        body = src.split('def _pool_request(')[1].split('\ndef ')[0]
        self.assertIn('allow_downgrade = _purposeAllowsDowngrade(purpose)', body)
        self.assertIn('if not allow_downgrade', body)
        self.assertLess(body.index('if not allow_downgrade'),
                        body.index('_get_http_pool(insecure=insecure)'),
                        '门禁必须在不验证池被取用之前生效')
        # 先验证后降级的既有顺序不变（P3 的 C2 用例依赖这行字面量）
        self.assertIn('for insecure in (False, True)', body)

        # 三个入口的签名都保留 purpose 且默认 low
        for fn in ('HttpGet', 'HttpGet2', 'HttpPost'):
            sig = src.split('def ' + fn + '(')[1].split(')')[0]
            self.assertIn('purpose=PURPOSE_LOW', sig, fn)


if __name__ == '__main__':
    unittest.main()
