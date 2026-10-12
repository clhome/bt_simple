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
SETTING_PY = os.path.join(WEB, 'setting.py')
ADMIN_INIT = os.path.join(WEB, 'admin', '__init__.py')
SOFT_JS = os.path.join(WEB, 'static', 'app', 'soft.js')
PLUGIN_ROUTE = os.path.join(WEB, 'admin', 'plugins', '__init__.py')

#: 被证伪、不得再出现的绝对化表述（逐条对应修复前的原文）
DISPROVEN_CLAIMS = [
    '100% 独立解耦',
    '后门物理清洗',
    '全局清除了已发现的所有后门及网络依赖',
    'chardet>=4.0.0',
    '强制支持 TLS 1.2+',
    '严密的 CSRF 防护',
    '默认自动打包备份核心数据',
    '首创极其严密的',
    '彻底杜绝手误删库',
]

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


def _call_request_after(ssl_open):
    fn, code = _load_request_after()
    ns = {
        'time': time,
        'request': _FakeRequest(),
        'g': _FakeG(),
        'thisdb': _FakeThisdb(ssl_open),
    }
    exec(code, ns)
    response = _FakeResponse()
    ns['requestAfter'](response)
    return response.headers


class ReadmeClaimsHonestyTest(unittest.TestCase):

    # ----------------------------- README -----------------------------

    def test_01_readme_drops_disproven_claims(self):
        """README 不得再出现被证伪的绝对化表述。"""
        text = _read(README)
        hit = [c for c in DISPROVEN_CLAIMS if c in text]
        self.assertEqual([], hit, 'README 仍含被证伪的绝对化表述：%s' % hit)

    def test_02_readme_has_external_services_section(self):
        """README 必须新增「功能性外联清单」小节并点名真实外联目标。"""
        text = _read(README)
        self.assertIn('### 功能性外联清单', text, 'README 缺少「功能性外联清单」小节标题')
        missing = [t for t in EXTERNAL_TARGETS if t not in text]
        self.assertEqual([], missing, '外联清单缺少目标：%s' % missing)
        self.assertIn('内网', text, '外联清单应提示内网/敏感环境注意事项')
        self.assertIn('离线', text, '外联清单应提示离线环境注意事项')

    def test_03_readme_perf_numbers_disclaimed(self):
        """性能数字必须注明「作者自测、环境相关」并引用基准脚本说明。"""
        text = _read(README)
        self.assertIn('scripts/bench/README.md', text, '性能数字未引用 scripts/bench/README.md')
        self.assertIn('作者自测', text, '性能数字缺少「作者自测」免责说明')
        self.assertIn('环境相关', text, '性能数字缺少「环境相关」免责说明')

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
        """setting.py 必须把受约束的 SSLContext 交给 gunicorn（ssl_context）。"""
        text = _read(SETTING_PY)
        self.assertIn('ssl_context = yf.createPanelSslContext(', text,
                      'setting.py 未通过 ssl_context 下发 TLS 约束')
        self.assertNotIn('# ssl_version = 5', text,
                         'setting.py 不应保留被注释的旧 ssl_version 写法')

    # ------------------------------ HSTS ------------------------------

    def test_06_hsts_only_when_panel_ssl_on(self):
        """面板 SSL 开启时下发 HSTS，关闭时不发（避免锁死 HTTP 访问）。"""
        self.assertIn('Strict-Transport-Security', _read(ADMIN_INIT),
                      'after_request 未下发 HSTS 头')
        on = _call_request_after(ssl_open=True)
        self.assertIn('Strict-Transport-Security', on, '面板 SSL 开启时未下发 HSTS')
        self.assertIn('max-age=', on['Strict-Transport-Security'], 'HSTS 缺少 max-age')
        off = _call_request_after(ssl_open=False)
        self.assertNotIn('Strict-Transport-Security', off,
                         '面板 SSL 关闭时不应下发 HSTS')

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
