# coding: utf-8
"""README「宣称与实现对齐」守卫（测评报告 P1-8）。

锁死四类修复，任何一条被改回去都必须让门禁变红：

1. README 不再出现被证伪的绝对化表述（零网络依赖 / chardet / 强制 TLS 1.2+ /
   「严密的」CSRF / 默认自动备份核心数据 / 首创极其严密），并新增
   「功能性外联清单」小节如实列出对外访问目标；
2. 性能数字附「作者自测、环境相关」免责说明并引用 `scripts/bench/README.md`
   （脚本本身由另一个任务创建，本用例只引用、不创建）；
3. 面板 HTTPS 显式约束最低 TLS 1.2：`yf.createPanelSslContext()` 的
   `minimum_version` 必须为 `ssl.TLSVersion.TLSv1_2`，且 `web/setting.py`
   经 gunicorn `ssl_context` 下发；
4. 面板 SSL 开启时 `after_request` 下发 HSTS；卸载弹窗的「卸载前备份」勾选框
   真实存在且默认勾选，并接到后端 `uninstall(..., backup=...)`。

**双语文档（2026-10 起）**：`README.md` 是英文主文档、`README_cn.md` 是中文文档，
两份都对外发布。第 1、2 条对**两份都校验**，且各用自己语言的词表 —— 只把中文
词表套在英文文档上等于什么都没校验（英文里把「强制 TLS 1.2+」写回去不会红），
反过来也一样；只钉一份则另一份整段约束静默失效。本用例就栽过这个跟头：
README.md 改成英文后 test_02 / test_03 变红，但错的是断言不是文档。

变异自证见 `test/p1_honesty_mutation_probe.py`（把上述修复逐条回退，守卫须全红）。
"""
import ast
import os
import ssl
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

README = os.path.join(ROOT, 'README.md')
README_CN = os.path.join(ROOT, 'README_cn.md')
SETTING_PY = os.path.join(WEB, 'setting.py')
ADMIN_INIT = os.path.join(WEB, 'admin', '__init__.py')
SOFT_JS = os.path.join(WEB, 'static', 'app', 'soft.js')
PLUGIN_ROUTE = os.path.join(WEB, 'admin', 'plugins', '__init__.py')

#: 双语文档对：(文件名, 路径, 语言)。所有 README 断言都遍历这一对。
README_PAIR = (
    ('README.md', README, 'en'),
    ('README_cn.md', README_CN, 'zh'),
)

#: 被证伪、不得再出现的绝对化表述（逐条对应修复前的原文），按语言分组。
#: 英文条目是中文条目的英文等价写法 —— 换语言不能成为把夸大表述写回去的后门。
DISPROVEN_CLAIMS = {
    'zh': [
        '100% 独立解耦',
        '后门物理清洗',
        '全局清除了已发现的所有后门及网络依赖',
        'chardet>=4.0.0',
        '强制支持 TLS 1.2+',
        '严密的 CSRF 防护',
        '默认自动打包备份核心数据',
        '首创极其严密的',
        '彻底杜绝手误删库',
    ],
    'en': [
        '100% independent decoupling',
        'physically cleansed',
        'all discovered backdoors and network dependencies have been globally removed',
        'chardet>=4.0.0',
        'forced tls 1.2+',
        'enforces tls 1.2+',
        'strict csrf protection',
        'rigorous csrf protection',
        'defaults to automatically backing up core data',
        'first-ever extremely rigorous',
        'completely eliminates the risk of manual database deletion',
    ],
}

#: 「功能性外联清单」小节标题（唯一与语言有关的部分；外联目标域名本身与语言无关）。
EXTERNAL_SECTION = {
    'zh': '### 功能性外联清单',
    'en': '### Functional Outbound Network Request List',
}

#: 外联清单必须提示的风险场景用词（内网 / 离线），每组命中任意一个即可。
ISOLATION_HINTS = {
    'zh': [('内网',), ('离线',)],
    'en': [('intranet',), ('air-gapped', 'offline')],
}

#: 性能数字免责声明：必须引用基准脚本说明，并写明「作者自测 / 环境相关」两个口径。
BENCH_README_REF = 'scripts/bench/README.md'
PERF_DISCLAIMER = {
    'zh': [('作者自测',), ('环境相关',)],
    'en': [('author benchmark', 'author local test'),
           ('environment-dependent', 'varies by hardware')],
}

#: 「并非零网络依赖」必须写明的口径（P1-8 的核心修法，两份文档都要有）。
NOT_ZERO_NET = {
    'zh': '并非零网络依赖',
    'en': 'not zero network dependency',
}

#: 功能性外联清单必须点名的外部目标（recon 已核实真实存在）
EXTERNAL_TARGETS = [
    'timor.tech',
    'ip-api.com',
    'whois.pconline.com.cn',
    'ipinfo.io',
    'yftec.top',
    'gh-proxy.org',
    'Staticfile',
]


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _func_slice(source, start_marker, end_marker):
    start = source.find(start_marker)
    assert start != -1, '找不到 %s' % start_marker
    end = source.find(end_marker, start)
    assert end != -1, '找不到 %s（在 %s 之后）' % (end_marker, start_marker)
    return source[start:end]


class _FakeRequest(object):
    start_time = 0.0
    path = '/'


class _FakeG(object):
    request_id = 'test-rid'

    def __init__(self, hsts_clear=False):
        self.hsts_clear = hsts_clear


class _FakeResponse(object):
    def __init__(self):
        self.headers = {}


class _FakeThisdb(object):
    """可切换面板 SSL 开关的 thisdb 桩。"""

    def __init__(self, ssl_open):
        self._ssl_open = ssl_open

    def getOptionByJson(self, name, type='common', default=None):
        if name == 'panel_ssl':
            return {'open': self._ssl_open}
        return default


class _FakeYf(object):
    """yf 桩：HSTS 的判定现在统一走 `yf.panelSslState()['ready']`。

    `open` 与 `ready` 分开传入，才能断言「配置开了但证书不可用」（半开状态）
    不被打上 HSTS —— 那种状态下根本没 HTTPS，打 HSTS 等于把浏览器锁在打不开的地址。
    """

    def __init__(self, ssl_open, ssl_ready=None, choose='nginx'):
        self._open = ssl_open
        self._ready = ssl_open if ssl_ready is None else ssl_ready
        self._choose = choose

    def panelSslState(self, *a, **k):
        return {
            'open': self._open,
            'ready': self._ready,
            'degraded': bool(self._open) and not self._ready,
            'choose': self._choose,
            'certfile': '/tmp/ssl/%s/cert.pem' % self._choose,
            'keyfile': '/tmp/ssl/%s/private.pem' % self._choose,
        }


def _load_request_after():
    """从 `web/admin/__init__.py` 里抽出 `requestAfter` 并在桩环境里执行。

    只编译这一个函数体（去掉 `@app.after_request` 装饰器），因此不需要拉起整个
    Flask app / 数据库，也能真调用它、断言响应头。
    """
    tree = ast.parse(_read(ADMIN_INIT))
    fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'requestAfter':
            fn = node
            break
    assert fn is not None, 'web/admin/__init__.py 找不到 requestAfter'
    fn.decorator_list = []
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    return fn, compile(module, ADMIN_INIT, 'exec')


def _call_request_after(ssl_open, ssl_ready=None, choose='nginx', hsts_clear=False):
    fn, code = _load_request_after()
    ns = {
        'time': time,
        'request': _FakeRequest(),
        'g': _FakeG(hsts_clear),
        'thisdb': _FakeThisdb(ssl_open),
        'yf': _FakeYf(ssl_open, ssl_ready, choose),
    }
    exec(code, ns)
    response = _FakeResponse()
    ns['requestAfter'](response)
    return response.headers


class ReadmeClaimsHonestyTest(unittest.TestCase):

    # ----------------------------- README -----------------------------

    @staticmethod
    def _readme_texts():
        """返回 [(文件名, 语言, 全文)]；缺文件直接失败（别让断言在空气里通过）。"""
        out = []
        for name, path, lang in README_PAIR:
            if not os.path.isfile(path):
                raise AssertionError('缺少文档 %s（中英双语文档必须成对存在）' % name)
            out.append((name, lang, _read(path)))
        return out

    def test_01_readme_drops_disproven_claims(self):
        """两份 README 都不得再出现被证伪的绝对化表述（各按自己语言的词表）。"""
        for name, lang, text in self._readme_texts():
            low = text.lower()
            hit = [c for c in DISPROVEN_CLAIMS[lang] if c.lower() in low]
            self.assertEqual([], hit,
                             '%s 仍含被证伪的绝对化表述：%s' % (name, hit))

    def test_02_readme_has_external_services_section(self):
        """两份 README 都必须有「功能性外联清单」小节并点名真实外联目标。"""
        for name, lang, text in self._readme_texts():
            low = text.lower()
            self.assertIn(EXTERNAL_SECTION[lang], text,
                          '%s 缺少「功能性外联清单」小节标题（期望：%s）'
                          % (name, EXTERNAL_SECTION[lang]))
            missing = [t for t in EXTERNAL_TARGETS if t.lower() not in low]
            self.assertEqual([], missing,
                             '%s 外联清单缺少目标：%s' % (name, missing))
            for group in ISOLATION_HINTS[lang]:
                self.assertTrue(any(p.lower() in low for p in group),
                                '%s 外联清单应提示「%s」环境注意事项'
                                % (name, ' / '.join(group)))

    def test_03_readme_perf_numbers_disclaimed(self):
        """性能数字必须注明「作者自测、环境相关」并引用基准脚本说明（两份都要）。"""
        for name, lang, text in self._readme_texts():
            low = text.lower()
            self.assertIn(BENCH_README_REF, text,
                          '%s 性能数字未引用 %s' % (name, BENCH_README_REF))
            for group in PERF_DISCLAIMER[lang]:
                self.assertTrue(any(p.lower() in low for p in group),
                                '%s 性能数字缺少「%s」免责说明'
                                % (name, ' / '.join(group)))

    def test_03b_readmes_are_a_linked_pair(self):
        """中英两份文档必须互相链接，且都写明「并非零网络依赖」。

        互链是「双语文档成对维护」的最小证据：只留一份、或翻译漏掉另一份，
        上面 01~03 的断言就会因为少扫一份文档而变松。
        """
        for name, lang, text in self._readme_texts():
            other = 'README_cn.md' if lang == 'en' else 'README.md'
            self.assertIn(other, text, '%s 未链接对侧文档 %s' % (name, other))
            self.assertIn(NOT_ZERO_NET[lang].lower(), text.lower(),
                          '%s 未写明「%s」' % (name, NOT_ZERO_NET[lang]))

    # ------------------------------- TLS ------------------------------

    def test_04_tls_minimum_version_is_1_2(self):
        """面板 SSLContext 的最低版本必须**显式**写为 TLS 1.2。

        运行期断言不够：Python 3.10+ 的 SSLContext 默认 minimum_version 已是
        TLS 1.2，删掉显式赋值运行值不变。因此还要钉住源码里的显式赋值。
        """
        net_src = _read(os.path.join(WEB, 'core', 'yf', 'net.py'))
        self.assertIn('context.minimum_version = ssl.TLSVersion.TLSv1_2', net_src,
                      'net.py 未显式设置 minimum_version = TLSv1_2')
        import core.yf as yf  # noqa: E402  —— 延迟导入，避免影响其它用例
        self.assertTrue(hasattr(yf, 'createPanelSslContext'),
                        'core.yf 缺少 createPanelSslContext')
        ctx = yf.createPanelSslContext()
        self.assertIsInstance(ctx, ssl.SSLContext)
        self.assertEqual(ssl.TLSVersion.TLSv1_2, ctx.minimum_version,
                         '面板 SSLContext 未锁定最低 TLS 1.2')

    def test_05_setting_wires_ssl_context(self):
        """setting.py 必须把受约束的 SSLContext 交给 gunicorn（ssl_context）。

        gunicorn>=22 的 `ssl_context` 只能是**可调用对象**（签名 (conf, factory)）：
        直接给 SSLContext 实例会被 `validate_callable(2)` 拒掉，而 gunicorn 只打一行
        stderr 告警就跳过该项 —— 面板起得来但根本没有 TLS。所以这里钉住「传的是工厂」。
        """
        text = _read(SETTING_PY)
        self.assertIn('ssl_context = yf.panelSslContextFactory(', text,
                      'setting.py 未通过 ssl_context 工厂下发 TLS 约束')
        self.assertNotIn('ssl_context = yf.createPanelSslContext(', text,
                         '直接传 SSLContext 实例会被 gunicorn 拒掉（Value is not callable）')
        self.assertNotIn('# ssl_version = 5', text,
                         'setting.py 不应保留被注释的旧 ssl_version 写法')

    def test_05b_ssl_context_factory_is_gunicorn_compatible(self):
        """工厂必须真能被 gunicorn 那样调用（arity=2）并返回 TLS1.2 起步的 context。"""
        import core.yf as yf  # noqa: E402
        factory = yf.panelSslContextFactory('/c.pem', '/k.pem', 'DEFAULT')
        self.assertTrue(callable(factory), 'ssl_context 必须是 callable')
        arity = len([p for p in __import__('inspect').signature(factory).parameters.values()
                     if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])
        self.assertEqual(2, arity, 'gunicorn 的 validate_callable(2) 要求两个位置参数')

        default_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx = factory(None, lambda: default_ctx)
        self.assertIs(ctx, default_ctx, '应复用 gunicorn 默认工厂造出来的 context')
        self.assertEqual(ssl.TLSVersion.TLSv1_2, ctx.minimum_version)
        # 默认工厂报错时不能把面板拖下水：退回自建 context（不加载证书，避免测试读文件）
        def _boom():
            raise ValueError('cafile missing')
        ctx2 = yf.panelSslContextFactory()(None, _boom)
        self.assertIsInstance(ctx2, ssl.SSLContext)
        self.assertEqual(ssl.TLSVersion.TLSv1_2, ctx2.minimum_version)

    # ------------------------------ HSTS ------------------------------

    def test_06_hsts_only_when_panel_ssl_on(self):
        """HSTS 只发给「真证书」；自签 / 关闭 / 半开状态一律不发（否则浏览器被锁死）。"""
        self.assertIn('Strict-Transport-Security', _read(ADMIN_INIT),
                      'after_request 未下发 HSTS 头')
        on = _call_request_after(ssl_open=True, choose='nginx')
        self.assertIn('Strict-Transport-Security', on, '真证书 HTTPS 时应下发 HSTS')
        self.assertIn('max-age=', on['Strict-Transport-Security'], 'HSTS 缺少 max-age')
        off = _call_request_after(ssl_open=False)
        self.assertNotIn('Strict-Transport-Security', off,
                         '面板 SSL 关闭时不应下发 HSTS')
        # 自签证书绝不能发 HSTS：HSTS 会让证书告警变成「不可绕过」，
        # 而自签恰恰需要用户点「继续前往」，两者天生冲突。
        self_signed = _call_request_after(ssl_open=True, choose='local')
        self.assertNotIn('Strict-Transport-Security', self_signed,
                         '自签证书不得下发 HSTS（会让浏览器永久拒绝访问该主机）')
        # 关 SSL 的那个响应要把它清掉
        cleared = _call_request_after(ssl_open=False, hsts_clear=True)
        self.assertEqual('max-age=0', cleared.get('Strict-Transport-Security'),
                         '关闭 SSL 时必须下发 max-age=0 清除 HSTS')
        # 半开状态（配置 open、证书不可用）：实际仍是明文 HTTP，不能打 HSTS
        half = _call_request_after(ssl_open=True, ssl_ready=False)
        self.assertNotIn('Strict-Transport-Security', half,
                         '证书不可用时不得下发 HSTS（会把浏览器锁在打不开的 https 上）')

    # ------------------------ 卸载备份默认勾选 -------------------------

    def test_07_uninstall_backup_checkbox_default_checked(self):
        """强制卸载与普通卸载弹窗都要有「卸载前备份」勾选框且默认勾选。"""
        source = _read(SOFT_JS)

        force = _func_slice(source, 'function forceUninstallPlugin', 'function uninstallPreInspection')
        self.assertIn("id='force_uninstall_backup_chk'", force,
                      '强制卸载弹窗缺少备份勾选框（DOM 不存在，读到的永远是 0）')
        self.assertIn("id='force_uninstall_backup_chk' checked='checked'", force,
                      '强制卸载弹窗的备份勾选框未默认勾选')

        normal = _func_slice(source, 'function runUninstallVersion', 'function uninstallVersion')
        self.assertIn("id='normal_uninstall_backup_chk'", normal,
                      '普通卸载弹窗缺少备份勾选框')
        self.assertIn("id='normal_uninstall_backup_chk' checked='checked'", normal,
                      '普通卸载弹窗的备份勾选框未默认勾选')

    def test_08_uninstall_backup_wired_to_backend(self):
        """两个卸载路径都要把 backup 传给后端，后端要把它接到 uninstall()。"""
        source = _read(SOFT_JS)
        force = _func_slice(source, 'function forceUninstallPlugin', 'function uninstallPreInspection')
        self.assertIn('backup: isBackup', force, '强制卸载未把 backup 传给后端')
        normal = _func_slice(source, 'function runUninstallVersion', 'function uninstallVersion')
        self.assertIn("'&backup=' + isBackup", normal, '普通卸载未把 backup 传给后端')

        route = _read(PLUGIN_ROUTE)
        self.assertIn("backup = request.form.get('backup'", route,
                      '/plugins/uninstall 未读取 backup 参数')
        self.assertIn('pg.uninstall(name, version, force=force, backup=backup)', route,
                      '/plugins/uninstall 未把 backup 传给 uninstall()')


if __name__ == '__main__':
    unittest.main()
