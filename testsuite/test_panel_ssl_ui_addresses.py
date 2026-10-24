# coding: utf-8
"""面板 SSL「访问地址 + 首次访问指引」的回归守卫。

## 需求（2026-10-24）

开启自签证书后的成功弹窗必须做到两件事：

1. **同时给出内网地址和外网地址**，并且**点哪一条都能复制那一条**；
   以前只显示后端算出来的单个地址（多为公网 IP）：内网用户被支去公网绕一圈
   （NAT 回环还可能直接不通），外网用户拿到内网地址则完全打不开。
2. **明确告知首次访问自签证书地址的浏览器操作**：点【高级】→
   点【继续前往 xx.xx.xx.xx（不安全）】。原来只写了「点击高级或详情 /
   继续访问」，与 Chrome 的实际文案对不上，用户照做找不到按钮。

## 断言分层

1. **后端地址清单**：`web/utils/setting.py::buildPanelAccessUrls` 必须给出
   domain / lan / wan 三类条目（去重、过滤回环、带安全入口与端口）。
2. **接口形状**：`setPanelLocalSsl` 的 `data` 必须是 `{url, urls:[...]}`，
   且 `url == urls[0].url`（前端拿哪个都不会空）。
3. **前端渲染**：`panel_ssl_urls.js` 真跑一遍（node + vm），断言两条地址都渲染出来、
   每行带自己的 `data-url`，且点击第二行时复制的是**第二行**的地址。
4. **文案**：六语言都有这组键（内网/外网/域名/首访四步），不允许只有中文。
"""

import ast
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)

UTILS_SETTING = os.path.join(WEB, 'utils', 'setting.py')
URLS_JS = os.path.join(WEB, 'static', 'app', 'panel_ssl_urls.js')
INDEX_JS = os.path.join(WEB, 'static', 'app', 'index.js')
CONFIG_JS = os.path.join(WEB, 'static', 'app', 'config.js')
INDEX_HTML = os.path.join(WEB, 'templates', 'default', 'index.html')
SETTING_HTML = os.path.join(WEB, 'templates', 'default', 'setting.html')
LANG_DIR = os.path.join(WEB, 'static', 'language')

LANGS = ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it')
UI_KEYS = ('ssl_access_lan', 'ssl_access_wan', 'ssl_access_domain', 'ssl_access_local',
           'ssl_first_visit_title', 'ssl_step_open_any', 'ssl_step_cert_warning',
           'ssl_step_click_advanced', 'ssl_step_click_continue')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


def _func_src(path, name):
    tree = ast.parse(_read(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            node.decorator_list = []
            return ast.unparse(ast.Module(body=[node], type_ignores=[]))
    raise AssertionError('%s 里找不到 %s' % (path, name))


def _build_urls_ns(lan='', wan='', domain='', port='60374', admin_path=''):
    """构造 buildPanelAccessUrls 的桩命名空间（不碰真库/真网络）。"""
    log = []
    ns = {
        'yf': types.SimpleNamespace(
            getPanelPort=lambda: port,
            getLanIp=lambda: lan,
            getLocalIp=lambda: wan,
            writeFileLog=lambda msg: log.append(msg),
        ),
        'thisdb': types.SimpleNamespace(
            getOption=lambda name, default=None: {
                'panel_domain': domain,
                'admin_path': admin_path,
            }.get(name, default),
        ),
        'os': os,
    }
    exec(compile(_func_src(UTILS_SETTING, 'buildPanelAccessUrls'),
                 UTILS_SETTING, 'exec'), ns)
    return ns, log


def _call_build(**kwargs):
    ns, _log = _build_urls_ns(**kwargs)
    return ns['buildPanelAccessUrls'](object())


class TestPanelAccessUrls(unittest.TestCase):

    def test_lan_and_wan_both_listed(self):
        res = _call_build(lan='172.17.60.248', wan='202.107.245.93', admin_path='/q69dnrwy')
        self.assertEqual(['lan', 'wan'], [u['type'] for u in res['urls']],
                         '内网 + 外网 必须都给出（顺序：内网在前，方便同一台机器直接点）')
        self.assertIn('https://172.17.60.248:60374/q69dnrwy',
                      [u['url'] for u in res['urls']])
        self.assertIn('https://202.107.245.93:60374/q69dnrwy',
                      [u['url'] for u in res['urls']])

    def test_primary_url_is_first_item(self):
        res = _call_build(lan='10.0.0.5', wan='1.2.3.4')
        self.assertEqual(res['urls'][0]['url'], res['url'],
                         'url 必须等于 urls[0].url，前端拿哪个都不会空')

    def test_domain_listed_first_when_bound(self):
        res = _call_build(domain='panel.example.com', lan='10.0.0.5', wan='1.2.3.4')
        self.assertEqual(['domain', 'lan', 'wan'], [u['type'] for u in res['urls']])
        self.assertTrue(res['url'].startswith('https://panel.example.com:60374'))

    def test_duplicate_hosts_deduped(self):
        # 公网 IP 直接绑在网卡上时 lan == wan，只保留一条，别重复两行一样的地址
        res = _call_build(lan='1.2.3.4', wan='1.2.3.4')
        self.assertEqual(1, len(res['urls']), res['urls'])

    def test_loopback_never_shown_as_wan(self):
        res = _call_build(lan='', wan='127.0.0.1')
        types_ = [u['type'] for u in res['urls']]
        self.assertNotIn('wan', types_,
                         '拿不到公网 IP 时不能把 127.0.0.1 当成「外网地址」')
        self.assertEqual('local', types_[0])

    def test_admin_path_without_slash_normalized(self):
        res = _call_build(lan='10.0.0.5', admin_path='q69dnrwy')
        self.assertIn('https://10.0.0.5:60374/q69dnrwy', res['url'])

    def test_empty_admin_path_kept_clean(self):
        res = _call_build(lan='10.0.0.5', admin_path='')
        self.assertEqual('https://10.0.0.5:60374', res['url'])

    def test_lan_probe_failure_does_not_raise(self):
        ns, log = _build_urls_ns(lan='', wan='1.2.3.4')

        def _boom():
            raise OSError('no route')
        ns['yf'].getLanIp = _boom
        res = ns['buildPanelAccessUrls'](object())
        self.assertEqual(['wan'], [u['type'] for u in res['urls']])
        self.assertTrue(log, '内网探测失败必须留日志，不能静默少一条地址')


class TestSetPanelLocalSslReturnsUrlList(unittest.TestCase):

    def test_returns_dict_with_urls(self):
        pdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, pdir, True)
        os.makedirs(os.path.join(pdir, 'ssl', 'local'))
        for name in ('cert.pem', 'private.pem'):
            with open(os.path.join(pdir, 'ssl', 'local', name), 'w', encoding='utf-8') as fh:
                fh.write('x')

        set_option = []
        ns = {
            'yf': types.SimpleNamespace(
                getPanelDir=lambda: pdir,
                createLocalSSL=lambda: True,
                returnData=lambda status, msg, data=None: {
                    'status': status, 'msg': msg, 'data': data},
                writeFileLog=lambda *a, **k: None,
                getPanelPort=lambda: 60374,
                getLanIp=lambda: '172.17.60.248',
                getLocalIp=lambda: '202.107.245.93',
            ),
            'thisdb': types.SimpleNamespace(
                getOptionByJson=lambda name, default=None: dict(default or {}),
                setOption=lambda name, value: set_option.append((name, value)),
                getOption=lambda name, default=None: {
                    'admin_path': 'q69dnrwy', 'panel_domain': '',
                }.get(name, default),
            ),
            'os': os,
            'json': json,
        }
        exec(compile(_func_src(UTILS_SETTING, 'buildPanelAccessUrls'),
                     UTILS_SETTING, 'exec'), ns)
        exec(compile(_func_src(UTILS_SETTING, 'setPanelLocalSsl'),
                     UTILS_SETTING, 'exec'), ns)
        # 两个方法合成一个桩实例：setPanelLocalSsl 内部要调 self.buildPanelAccessUrls()
        # （用真类，函数描述符才会绑定 self）
        Stub = type('Stub', (object,), {
            'buildPanelAccessUrls': ns['buildPanelAccessUrls'],
            'setPanelLocalSsl': ns['setPanelLocalSsl'],
        })
        res = Stub().setPanelLocalSsl('0')
        self.assertTrue(res['status'], res)
        data = res['data']
        self.assertIsInstance(data, dict, 'data 必须是 {url, urls}（前端要逐条渲染）')
        self.assertEqual(['lan', 'wan'], [u['type'] for u in data['urls']])
        self.assertEqual('https://172.17.60.248:60374/q69dnrwy', data['url'])
        self.assertTrue(set_option, '成功时仍要落库面板 SSL 状态')


class TestFrontendRendersBothAddresses(unittest.TestCase):
    """用 node + vm 真跑一遍组件：两条地址都渲染、点谁复制谁。"""

    def _run_node(self, script):
        node = shutil.which('node')
        if not node:
            self.skipTest('未安装 node，跳过前端行为用例')
        res = subprocess.run([node, '-e', script], cwd=ROOT,
                             capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(res.returncode, 0, 'node 用例失败: %s\n%s' % (res.stderr, res.stdout))
        return res.stdout

    def test_two_rows_and_click_copies_the_clicked_one(self):
        script = """
        const fs = require('fs');
        const vm = require('vm');

        const copied = [];
        const handlers = {};
        function makeEl(url) { return { __row: true, url: url }; }
        function $(arg) {
          if (arg && arg.__row) {
            return { attr: function (n) { return n === 'data-url' ? arg.url : ''; },
                     css: function () { return this; } };
          }
          return {
            off: function (ev) { delete handlers[ev]; return this; },
            on: function (ev, sel, fn) { handlers[ev] = fn; return this; },
            css: function () { return this; }
          };
        }
        const sandbox = {
          console: console,
          jQuery: $,
          navigator: { clipboard: { writeText: function (t) {
              copied.push(t);
              return { then: function (ok) { ok(); return { catch: function () {} }; } };
          } } },
          document: { createElement: function () { return {}; }, body: { appendChild: function () {}, removeChild: function () {} } },
          location: { hostname: '172.17.60.248' },
          layer: { msg: function () {} }
        };
        sandbox.window = sandbox;
        vm.createContext(sandbox);
        vm.runInContext(fs.readFileSync('web/static/app/panel_ssl_urls.js', 'utf8'), sandbox);

        const data = {
          url: 'https://172.17.60.248:60374/q69dnrwy',
          urls: [
            { type: 'lan', host: '172.17.60.248', url: 'https://172.17.60.248:60374/q69dnrwy' },
            { type: 'wan', host: '202.107.245.93', url: 'https://202.107.245.93:60374/q69dnrwy' }
          ]
        };
        const api = sandbox.YfPanelSsl;
        const html = api.urlsHtml(data);
        if (html.indexOf('172.17.60.248') === -1 || html.indexOf('202.107.245.93') === -1) {
          console.error('两条地址没有都渲染出来: ' + html); process.exit(2);
        }
        if ((html.match(/yf-ssl-url-row/g) || []).length !== 2) {
          console.error('地址行数不为 2'); process.exit(3);
        }
        if (html.indexOf('data-url="https://202.107.245.93:60374/q69dnrwy"') === -1) {
          console.error('缺少第二行的 data-url'); process.exit(4);
        }
        if (html.indexOf('LAN') === -1 && html.indexOf('内网') === -1) {
          console.error('缺少「内网地址」标签'); process.exit(5);
        }
        const steps = api.stepsHtml();
        ['高级', 'xx.xx.xx.xx', '不安全'].forEach(function (needle) {
          if (steps.indexOf(needle) === -1) {
            console.error('首次访问指引缺少关键文案: ' + needle); process.exit(6);
          }
        });

        api.bindCopy('#box');
        const clickHandler = handlers['click.yfssl'];
        if (typeof clickHandler !== 'function') { console.error('未挂点击复制'); process.exit(7); }
        clickHandler.call(makeEl('https://202.107.245.93:60374/q69dnrwy'));
        if (copied.length !== 1 || copied[0] !== 'https://202.107.245.93:60374/q69dnrwy') {
          console.error('点击第二行复制的不是第二行地址: ' + JSON.stringify(copied)); process.exit(8);
        }

        // 同主机优先：内网访问时重启后要留在内网地址
        if (api.pickTarget(data) !== 'https://172.17.60.248:60374/q69dnrwy') {
          console.error('pickTarget 未优先当前主机'); process.exit(9);
        }
        // 兼容旧版纯字符串返回值
        if (api.normalize('https://1.2.3.4:7200').url !== 'https://1.2.3.4:7200') {
          console.error('旧字符串返回值兼容失败'); process.exit(10);
        }
        console.log('PANEL_SSL_URL_TESTS_PASSED');
        """
        out = self._run_node(script)
        self.assertIn('PANEL_SSL_URL_TESTS_PASSED', out)


class TestFrontendWiring(unittest.TestCase):

    def test_component_exposes_api(self):
        src = _read(URLS_JS)
        for name in ('urlsHtml', 'stepsHtml', 'bindCopy', 'pickTarget', 'normalize'):
            self.assertIn('%s: %s' % (name, name), src, '组件缺少 %s' % name)
        self.assertIn('window.YfPanelSsl', src)

    def test_index_js_uses_component(self):
        src = _read(INDEX_JS)
        self.assertIn('YfPanelSsl.urlsHtml(', src, '首页弹窗未渲染多地址列表')
        self.assertIn('YfPanelSsl.bindCopy(', src, '首页弹窗未绑定逐行点击复制')
        self.assertIn('YfPanelSsl.pickTarget(', src, '重启后跳转未按当前主机挑选地址')

    def test_config_js_uses_component(self):
        src = _read(CONFIG_JS)
        self.assertIn('YfPanelSsl.urlsHtml(', src, '面板设置弹窗未渲染多地址列表')
        self.assertIn('YfPanelSsl.bindCopy(', src, '面板设置弹窗未绑定逐行点击复制')

    def test_templates_load_component(self):
        for path in (INDEX_HTML, SETTING_HTML):
            self.assertIn("asset_v('app/panel_ssl_urls.js')", _read(path),
                          '%s 未引入 panel_ssl_urls.js（或缺少缓存指纹）' % os.path.basename(path))


class TestSslUiI18nComplete(unittest.TestCase):

    def test_six_languages_have_ui_keys(self):
        for lang in LANGS:
            carrier = json.loads(_read(os.path.join(LANG_DIR, lang, 'template.setting.json')))
            config = carrier.get('config') or {}
            missing = [k for k in UI_KEYS if not config.get(k)]
            self.assertEqual([], missing, '%s 缺少面板 SSL 提示文案: %r' % (lang, missing))

    def test_no_cjk_leak_in_latin_languages(self):
        cjk = re.compile(u'[\u4e00-\u9fff]')
        for lang in ('en', 'de', 'fr', 'it'):
            carrier = json.loads(_read(os.path.join(LANG_DIR, lang, 'template.setting.json')))
            config = carrier.get('config') or {}
            bad = [k for k in UI_KEYS if cjk.search(str(config.get(k, '')))]
            self.assertEqual([], bad, '%s 的面板 SSL 文案里混进了中文: %r' % (lang, bad))

    def test_steps_match_browser_wording(self):
        """步骤必须与 Chrome 实际按钮文案对得上（高级 / 继续前往 xx.xx.xx.xx（不安全））。"""
        config = json.loads(_read(os.path.join(LANG_DIR, 'zh-CN', 'template.setting.json')))['config']
        self.assertIn('高级', config['ssl_step_click_advanced'])
        self.assertIn('xx.xx.xx.xx', config['ssl_step_click_continue'])
        self.assertIn('不安全', config['ssl_step_click_continue'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
