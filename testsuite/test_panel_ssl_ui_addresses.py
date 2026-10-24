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
SYSTEM_PY = os.path.join(WEB, 'core', 'yf', 'system.py')
INDEX_HTML = os.path.join(WEB, 'templates', 'default', 'index.html')
SETTING_HTML = os.path.join(WEB, 'templates', 'default', 'setting.html')
LANG_DIR = os.path.join(WEB, 'static', 'language')

LANGS = ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it')
UI_KEYS = ('ssl_access_lan', 'ssl_access_wan', 'ssl_access_domain', 'ssl_access_local',
           'ssl_first_visit_title', 'ssl_step_open_any', 'ssl_step_cert_warning',
           'ssl_step_click_advanced', 'ssl_step_click_continue',
           'ssl_closed_relogin_tip', 'ssl_closed_goto')


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


class TestCloseSslKeepsUserInside(unittest.TestCase):
    """关闭 SSL 后必须把用户送到「带安全入口的 http 地址」，而不是死页面。

    现场（2026-10-24）：关闭 SSL 后浏览器被带回 `http://ip:port/`（无安全入口），
    面板渲染「请使用正确的入口登录面板」，用户以为面板坏了。真实原因是两层叠加：

    1. 关掉 SSL 后，浏览器里那个带 `Secure` 标记的会话 Cookie 在明文 HTTP 下**不会
       被回传** → 等于掉登录态；
    2. 前端原来只是把当前 URL 的 `https` 换成 `http`（此时当前页是 `/`，没有入口），
       而后端 `close_panel_ssl` 又没告诉前端该去哪。

    所以：后端必须返回 http + admin_path 的地址清单，前端必须用它跳登录入口页。
    """

    def _close_ns(self, admin_path='q69dnrwy'):
        pdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, pdir, True)
        options = {}
        ns = {
            'yf': types.SimpleNamespace(
                getPanelPort=lambda: 60374,
                getLanIp=lambda: '172.17.60.248',
                getLocalIp=lambda: '202.107.245.93',
                writeFileLog=lambda *a, **k: None,
                restartPanel=lambda: None,
                returnData=lambda status, msg, data=None: {
                    'status': status, 'msg': msg, 'data': data},
            ),
            'thisdb': types.SimpleNamespace(
                getOptionByJson=lambda name, default=None: {'open': True, 'choose': 'local'},
                setOption=lambda name, value: options.setdefault(name, value),
                getOption=lambda name, default=None: {
                    'admin_path': admin_path, 'panel_domain': '',
                }.get(name, default),
            ),
            'os': os,
            'json': json,
        }
        for fn in ('buildPanelAccessUrls', 'closePanelSsl'):
            exec(compile(_func_src(UTILS_SETTING, fn), UTILS_SETTING, 'exec'), ns)
        Stub = type('Stub', (object,), {
            'buildPanelAccessUrls': ns['buildPanelAccessUrls'],
            'closePanelSsl': ns['closePanelSsl'],
        })
        return Stub(), options

    def test_returns_http_urls_with_admin_path(self):
        stub, options = self._close_ns()
        res = stub.closePanelSsl()
        self.assertTrue(res['status'], res)
        data = res['data']
        self.assertIsInstance(data, dict, '关闭 SSL 必须返回 {url, urls} 供前端跳转')
        for item in data['urls']:
            self.assertTrue(item['url'].startswith('http://'), item['url'])
            self.assertTrue(item['url'].endswith('/q69dnrwy'),
                            '落点必须带安全入口，否则只会看到「请使用正确的入口登录面板」: %s'
                            % item['url'])
        self.assertFalse(any('https://' in u['url'] for u in data['urls']),
                         '已关闭 SSL，不能再给 https 地址')
        self.assertIn('panel_ssl', options, '关闭时必须落库')
        self.assertIn('"open": false', options['panel_ssl'].replace('False', 'false'),
                      '落库的面板 SSL 状态必须是关闭')

    def test_empty_admin_path_keeps_root(self):
        stub, _ = self._close_ns(admin_path='')
        res = stub.closePanelSsl()
        self.assertEqual('http://172.17.60.248:60374', res['data']['url'])

    def test_frontend_uses_backend_url_not_naive_scheme_swap(self):
        src = _read(CONFIG_JS)
        # 旧的「把 https 字样换成 http」在 `当前页是 /` 时会落到无入口地址
        self.assertNotIn("var to_http = window.location.href.replace('https', 'http')", src,
                         '关闭 SSL 不能再用「当前 URL 去 s」的裸跳转（会落到无安全入口的 /）')
        self.assertIn('showSslClosedWindow(', src, '关闭 SSL 后要有落地提示（含 http 地址 + 重新登录）')
        self.assertIn('YfPanelSsl.pickTarget(', src, '跳转目标应取后端返回的地址清单')

    def test_redirect_helper_keeps_admin_path(self):
        """`checkDomainPanel` 的 302 同样必须带安全入口。"""
        src = _read(SYSTEM_PY)
        start = src.index('def checkDomainPanel(')
        end = src.index('\ndef ', start + 1)
        body = src[start:end]
        self.assertIn('admin_path', body, '302 跳转丢了安全入口 → 用户会被丢到「入口错误」页')
        self.assertIn('+ admin_path', body)


class TestAdminPathStableAcrossSslToggle(unittest.TestCase):
    """开启/关闭面板 SSL 不得改动安全入口（`admin_path`），前后缀必须一致。

    用户可见的后果：入口一变，手里那条 `https://ip:port/q69dnrwy` 立刻失效，
    而面板又把入口藏起来（`path.html` 不告诉你怎么找），看起来就是「开关 SSL 把
    面板弄坏了」。所以这里把「入口只由安装初始化 / 用户手动修改写入」钉成契约：
    SSL 相关流程**一个字都不许写** `admin_path`，且返回的地址后缀必须与库里一致。
    """

    ADMIN = 'q69dnrwy'

    def _stub(self, pdir):
        """构造一个带真实 buildPanelAccessUrls 的桩实例，记录所有 setOption。"""
        written = []
        ns = {
            'yf': types.SimpleNamespace(
                getPanelDir=lambda: pdir,
                getPanelPort=lambda: 60374,
                getLanIp=lambda: '172.17.60.248',
                getLocalIp=lambda: '202.107.245.93',
                writeFileLog=lambda *a, **k: None,
                restartPanel=lambda: None,
                createLocalSSL=lambda: True,
                returnData=lambda status, msg, data=None: {
                    'status': status, 'msg': msg, 'data': data},
            ),
            'thisdb': types.SimpleNamespace(
                getOptionByJson=lambda name, default=None: {
                    'panel_ssl': {'open': False, 'choose': 'local'},
                }.get(name, dict(default or {})),
                setOption=lambda name, value, **k: written.append((name, value)),
                getOption=lambda name, default=None: {
                    'admin_path': self.ADMIN, 'panel_domain': '',
                }.get(name, default),
            ),
            'os': os,
            'json': json,
        }
        for fn in ('buildPanelAccessUrls', 'setPanelLocalSsl', 'closePanelSsl'):
            exec(compile(_func_src(UTILS_SETTING, fn), UTILS_SETTING, 'exec'), ns)
        Stub = type('Stub', (object,), {k: ns[k] for k in
                                        ('buildPanelAccessUrls', 'setPanelLocalSsl', 'closePanelSsl')})
        return Stub(), written

    def _suffixes(self, data):
        self.assertIsInstance(data, dict, data)
        return sorted(u['url'].rsplit(':', 1)[-1].split('/', 1)[-1] for u in data['urls'])

    def test_open_and_close_keep_same_suffix(self):
        pdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, pdir, True)
        os.makedirs(os.path.join(pdir, 'ssl', 'local'))
        for name in ('cert.pem', 'private.pem'):
            with open(os.path.join(pdir, 'ssl', 'local', name), 'w', encoding='utf-8') as fh:
                fh.write('x')

        stub, written = self._stub(pdir)
        opened = stub.setPanelLocalSsl('1')
        closed = stub.closePanelSsl()

        self.assertEqual([self.ADMIN, self.ADMIN], self._suffixes(opened['data']),
                         '开启 SSL 后地址后缀必须还是原安全入口: %r' % (opened['data'],))
        self.assertEqual([self.ADMIN, self.ADMIN], self._suffixes(closed['data']),
                         '关闭 SSL 后地址后缀必须还是原安全入口: %r' % (closed['data'],))
        names = [n for n, _v in written]
        self.assertNotIn('admin_path', names,
                         'SSL 开关不得写 admin_path（会让用户手里的入口地址失效）')

    def test_ssl_module_never_writes_admin_path(self):
        src = _read(UTILS_SETTING)
        self.assertNotIn("setOption('admin_path'", src,
                         'web/utils/setting.py 不得写 admin_path（入口只由安装初始化 / 用户手动修改）')
        self.assertNotIn('setOption("admin_path"', src)

    def test_all_ssl_entry_points_share_admin_path(self):
        """四个入口（自签开启 / 自贴证书 / ACME / 关闭）都走同一个地址构造器。"""
        src = _read(UTILS_SETTING)
        for name in ('savePanelSsl', 'createPanelAcme', 'setPanelLocalSsl', 'closePanelSsl'):
            start = src.index('def %s(' % name)
            nxt = src.find('\n    def ', start + 1)
            body = src[start:nxt if nxt != -1 else len(src)]
            self.assertIn('buildPanelAccessUrls(', body,
                          '%s 必须用 buildPanelAccessUrls 生成地址（否则后缀口径会分叉）' % name)


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
