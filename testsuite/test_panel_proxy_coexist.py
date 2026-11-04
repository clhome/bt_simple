# coding: utf-8
"""守卫：`yf 33` 单端口(80/443)面板共存（`web/utils/panel_proxy.py`）。

## 本文件守什么

方案为什么必须是「server 级 if + 418 命名路由」，而不是 v1/v2 文档里的
「站点里注入 `location /` + 418」——这三条都是拿真 nginx 复现过的坑，
退化回去就等于让用户改一次站点配置整站发布失败：

1. **不得注入 `location /`**：伪静态模板（`web/misc/nginx/rewrite/*.conf`）普遍自带
   `location /`，再注入一个会直接 `[emerg] duplicate location "/"`；
2. **不得写 `conf.d/websocket_map.conf`**：`plugins/openresty/conf/nginx.conf` 只 include
   `vhost/*.conf`，写 `conf.d/` 等于没配；
3. **注入点必须在 `server_name` 之后、站点自己的 server 级 rewrite 之前**，
   否则站点开了「强制 HTTPS」会把面板入口 301 掉。

另外守：注入/摘除幂等、`$http_host` 透传（面板 CSRF 的 Referer netloc 比对）、
`yf 33` 菜单与 `yf proxy` 子命令真的接上了、`nginx -t` 失败必须回滚。
"""

import io
import os
import re
import shutil
import sys
import tempfile
import unittest
import contextlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
PANEL_TOOLS = os.path.join(ROOT, 'panel_tools.py')
YF_TPL = os.path.join(ROOT, 'scripts', 'init.d', 'yf.tpl')
PANEL_PROXY = os.path.join(WEB, 'utils', 'panel_proxy.py')
REWRITE_DIR = os.path.join(WEB, 'misc', 'nginx', 'rewrite')
TPL = os.path.join(WEB, 'misc', 'nginx', 'tpl', 'nginx.conf')

#: 面板真实生成的站点 vhost（web/misc/nginx/tpl/nginx.conf 渲染后 + wordpress 伪静态）
SAMPLE_VHOST = """server
{
    listen 80;
    listen [::]:80;
    server_name www.xx.com;
    index index.php index.html index.htm default.php default.htm default.html;
    root /www/wwwroot/www.xx.com;

    #SSL-START
    #error_page 404/404.html;
    #SSL-END

    #PHP-INFO-START
    include /www/server/web_conf/php/conf/enable-php-74.conf;
    #PHP-INFO-END

    #REWRITE-START
    include /www/server/web_conf/nginx/rewrite/www.xx.com.conf;
    #REWRITE-END

    location ~ ^/(\\.user.ini|\\.htaccess|\\.git|\\.svn|\\.project|LICENSE|README.md)
    {
        return 404;
    }

    location ~ .*\\.(gif|jpg|jpeg|png|bmp|swf|js|css|ttf|woff2)$
    {
        expires      30d;
        access_log /dev/null;
        if ($invalid_referer){
           return 404;
        }
    }

    access_log  /www/wwwlogs/www.xx.com.log main;
    error_log   /www/wwwlogs/www.xx.com.error.log;
}
"""

INCLUDE_PATH = '/www/server/web_conf/nginx/enable-yf-proxy.conf'


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read().replace('\r\n', '\n')


def _load_panel_proxy():
    """把 web/ 加进 sys.path 后导入被测模块（导入期不碰数据库）。"""
    if WEB not in sys.path:
        sys.path.insert(0, WEB)
    import utils.panel_proxy as mod
    return mod


class PanelProxyPureFuncTest(unittest.TestCase):
    """纯函数：渲染 / 注入 / 摘除（不读磁盘、不连库）。"""

    @classmethod
    def setUpClass(cls):
        cls.pp = _load_panel_proxy()

    # ---- 片段渲染 ----

    def test_fragment_reads_cookie_var_with_cookie_prefix(self):
        # nginx 读 Cookie 的变量是 `$cookie_<name>`；写成 `$yf_panel_mode` 编译得过去
        # （未定义变量会报错，这里恰好会报错）但一旦改成 map/set 就会静默失效。
        frag = self.pp.render_fragment('/q69dnrwy', '/yf_exit_panel', 7200)
        self.assertIn('if ($cookie_yf_panel_mode = "1")', frag)
        self.assertNotRegex(frag, r'if \(\$(?!cookie_|uri|scheme|server_|http_|yf_)',
                            '出现了来源不明的 nginx 变量')
        # 下发标记 Cookie 时用的是裸名
        self.assertIn('Set-Cookie "yf_panel_mode=1;', frag)
        self.assertIn('Set-Cookie "yf_panel_mode=0;', frag)

    def test_fragment_renders_entry_exit_and_upstream(self):
        frag = self.pp.render_fragment('/q69dnrwy', self.pp.EXIT_PATH,
                                       '60347', 'http', '/www/wwwlogs')
        self.assertIn('if ($uri = /q69dnrwy) { set $yf_panel_route 1; }', frag)
        self.assertIn('if ($uri = /yf_exit_panel) { set $yf_panel_route 2; }', frag)
        self.assertIn('proxy_pass http://127.0.0.1:60347;', frag)
        self.assertIn('access_log /www/wwwlogs/panel-proxy.log;', frag)
        # 两侧花括号必须配平（format 转义写错的典型症状）
        self.assertEqual(frag.count('{'), frag.count('}'))

    def test_fragment_never_touches_site_locations(self):
        frag = self.pp.render_fragment('/q69dnrwy', self.pp.EXIT_PATH, 7200)
        # 只允许出现命名 location；绝不出现 location / 或 location ^~ / 或 PHP/静态正则
        self.assertNotRegex(frag, r'(?m)^\s*location\s+[\^~=]?\s*/\s*\{')
        self.assertNotRegex(frag, r'location\s+~\s')
        self.assertIn('location @yf_panel_backend {', frag)
        self.assertIn('location @yf_panel_exit {', frag)

    def test_fragment_uses_http_host_for_csrf_referer(self):
        # core/security.py 用 netloc_of(referer) == request.host 判定 CSRF；
        # $host 会丢端口 → 必须用 $http_host
        frag = self.pp.render_fragment('/q69dnrwy', '/yf_exit_panel', 7200)
        self.assertIn('proxy_set_header Host $http_host;', frag)
        self.assertNotIn('proxy_set_header Host $host;', frag)

    def test_fragment_keeps_websocket_and_big_upload_capability(self):
        frag = self.pp.render_fragment('/q69dnrwy', '/yf_exit_panel', 7200)
        self.assertIn('proxy_set_header Upgrade $http_upgrade;', frag)
        self.assertIn('proxy_set_header Connection $connection_upgrade;', frag)
        self.assertIn('proxy_buffering off;', frag)
        self.assertIn('client_max_body_size 4096m;', frag)
        self.assertIn('proxy_read_timeout 3600s;', frag)

    def test_fragment_does_not_hijack_acme_challenge(self):
        # 站点证书走 acme.sh webroot，抢 /.well-known/ 会让续签全部失败
        frag = self.pp.render_fragment('/q69dnrwy', '/yf_exit_panel', 7200)
        self.assertNotIn('acme-challenge', frag)

    def test_fragment_upstream_scheme_switches_with_panel_ssl(self):
        frag = self.pp.render_fragment('/q69dnrwy', '/yf_exit_panel', 7200, 'https')
        self.assertIn('proxy_pass https://127.0.0.1:7200;', frag)

    def test_force_https_block_is_site_scoped(self):
        # 默认必须「不跳转」，由站点级 set $yf_panel_https_port 打开；
        # 否则纯 80 站点的入口会被 301 到不存在的 https（实机踩过的坑）
        frag = self.pp.render_fragment('/q69dnrwy', '/yf_exit_panel', 7200)
        self.assertIn('if ($yf_panel_https_port = "") { set $yf_panel_https_port 0; }', frag)
        self.assertIn('if ($yf_panel_https_port = 0) { set $yf_panel_need_https 0; }', frag)
        self.assertIn('if ($scheme = https)          { set $yf_panel_need_https 0; }', frag)

    # ---- 注入 ----

    def test_inject_puts_block_after_server_name(self):
        new_conf, changed, reason = self.pp.inject_marker(
            SAMPLE_VHOST, INCLUDE_PATH, ports=(80,), https_port=0)
        self.assertEqual(reason, '')
        self.assertTrue(changed)
        self.assertIn(INCLUDE_PATH, new_conf)
        self.assertIn('set $yf_panel_https_port 0;', new_conf)
        # 注入点必须在 server_name 之后（server 级 rewrite 按出现顺序执行）
        self.assertLess(new_conf.index('server_name www.xx.com;'),
                        new_conf.index(self.pp.MARK_BEGIN))
        # 且必须早于站点模板里的 PHP/伪静态 include
        self.assertLess(new_conf.index(self.pp.MARK_BEGIN),
                        new_conf.index('enable-php-74.conf'))

    def test_inject_https_flag_when_site_has_443(self):
        conf = SAMPLE_VHOST.replace('listen 80;', 'listen 80;\n    listen 443 ssl http2;')
        new_conf, changed, reason = self.pp.inject_marker(
            conf, INCLUDE_PATH, ports=(80, 443), https_port=443)
        self.assertEqual(reason, '')
        self.assertTrue(changed)
        self.assertIn('set $yf_panel_https_port 443;', new_conf)

    def test_inject_is_idempotent_and_refreshes_flag(self):
        once, _c1, _r1 = self.pp.inject_marker(SAMPLE_VHOST, INCLUDE_PATH, ports=(80,), https_port=0)
        twice, changed, reason = self.pp.inject_marker(once, INCLUDE_PATH, ports=(80,), https_port=443)
        self.assertEqual(reason, '')
        self.assertTrue(changed)
        self.assertEqual(twice.count(self.pp.MARK_BEGIN), 1)
        self.assertEqual(twice.count(INCLUDE_PATH), 1)
        self.assertIn('set $yf_panel_https_port 443;', twice)

    def test_inject_noop_when_nothing_changed(self):
        once, _c, _r = self.pp.inject_marker(SAMPLE_VHOST, INCLUDE_PATH, ports=(80,), https_port=0)
        twice, changed, reason = self.pp.inject_marker(once, INCLUDE_PATH, ports=(80,), https_port=0)
        self.assertEqual(reason, '')
        self.assertFalse(changed)
        self.assertEqual(once, twice)

    def test_inject_reports_missing_ports(self):
        _c, changed, reason = self.pp.inject_marker(SAMPLE_VHOST, INCLUDE_PATH, ports=(8080,))
        self.assertFalse(changed)
        self.assertEqual(reason, 'port_not_found')

    # ---- 摘除 ----

    def test_strip_restores_original_bytes(self):
        once, _c, _r = self.pp.inject_marker(SAMPLE_VHOST, INCLUDE_PATH, ports=(80,), https_port=443)
        back, changed = self.pp.strip_marker(once)
        self.assertTrue(changed)
        self.assertNotIn(self.pp.MARK_BEGIN, back)
        self.assertNotIn(INCLUDE_PATH, back)
        self.assertEqual(back, SAMPLE_VHOST)

    def test_strip_keeps_users_own_blank_lines(self):
        # 摘除只删标记块本身：用户/模板自己的连续空行不能被我们「顺手美化」，
        # 否则 `yf proxy off` 之后 vhost 就不再是逐字节还原。
        src = SAMPLE_VHOST.replace('    #SSL-START', '\n\n\n    #SSL-START')
        once, _c, _r = self.pp.inject_marker(src, INCLUDE_PATH, ports=(80,), https_port=0)
        self.assertIn('\n\n\n', once)
        back, changed = self.pp.strip_marker(once)
        self.assertTrue(changed)
        self.assertEqual(back, src)

    def test_strip_is_idempotent(self):
        back, changed = self.pp.strip_marker(SAMPLE_VHOST)
        self.assertFalse(changed)
        self.assertEqual(back, SAMPLE_VHOST)

    # ---- 解析 ----

    def test_listen_ports(self):
        conf = ('listen 80 default_server;\nlisten [::]:80;\n'
                'listen 443 ssl http2;\nlisten [::]:443 ssl;\n')
        http_ports, https_ports = self.pp.listen_ports(conf)
        self.assertEqual(http_ports, [80])
        self.assertEqual(https_ports, [443])

    def test_server_blocks_ignores_nested_content(self):
        conf = 'server {\n  location / { if ($a = "1") { return 403; } }\n}\n'
        blocks = self.pp.server_blocks(conf)
        self.assertEqual(len(blocks), 1)
        start, end = blocks[0]
        self.assertTrue(conf[start:end].endswith('}'))
        self.assertEqual(conf[start:end].count('{'), conf[start:end].count('}'))

    def test_normalize_entry(self):
        pp = self.pp
        self.assertEqual(pp.normalize_entry('q69dnrwy'), '/q69dnrwy')
        self.assertEqual(pp.normalize_entry('/q69dnrwy'), '/q69dnrwy')
        self.assertEqual(pp.normalize_entry(''), '')
        self.assertEqual(pp.normalize_entry(None), '')


class PanelProxyIoTest(unittest.TestCase):
    """I/O 层：真实文件系统上的注入 → 校验失败 → 回滚。"""

    @classmethod
    def setUpClass(cls):
        cls.pp = _load_panel_proxy()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_panel_proxy_')
        self.saved = {}
        # 只替换路径函数与外部副作用，其余逻辑走真实实现
        pp = self.pp
        self.saved = {
            'conf_dir': pp.conf_dir,
            'vhost_dir': pp.vhost_dir,
            'fragment_path': pp.fragment_path,
            'state_path': pp.state_path,
            'logs_dir': pp.logs_dir,
            'websocket_map_path': pp.websocket_map_path,
            'web_server_kind': pp.web_server_kind,
            'checkWebConfig': pp.yf.checkWebConfig,
            'restartWeb': pp.yf.restartWeb,
            'writeLog': pp.yf.writeLog,
        }
        os.makedirs(os.path.join(self.tmp, 'vhost'), exist_ok=True)
        pp.conf_dir = lambda: self.tmp
        pp.vhost_dir = lambda: os.path.join(self.tmp, 'vhost')
        pp.fragment_path = lambda: os.path.join(self.tmp, pp.FRAGMENT_NAME)
        pp.state_path = lambda: os.path.join(self.tmp, 'state.json')
        pp.logs_dir = lambda: self.tmp
        pp.websocket_map_path = lambda: os.path.join(self.tmp, 'vhost', pp.WS_MAP_NAME)
        pp.web_server_kind = lambda: 'openresty'
        pp.yf.writeLog = lambda *a, **k: None
        self.vhost = os.path.join(self.tmp, 'vhost', 'www.xx.com.conf')
        with io.open(self.vhost, 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(SAMPLE_VHOST)

    def tearDown(self):
        pp = self.pp
        pp.conf_dir = self.saved['conf_dir']
        pp.vhost_dir = self.saved['vhost_dir']
        pp.fragment_path = self.saved['fragment_path']
        pp.state_path = self.saved['state_path']
        pp.logs_dir = self.saved['logs_dir']
        pp.websocket_map_path = self.saved['websocket_map_path']
        pp.web_server_kind = self.saved['web_server_kind']
        pp.yf.checkWebConfig = self.saved['checkWebConfig']
        pp.yf.restartWeb = self.saved['restartWeb']
        pp.yf.writeLog = self.saved['writeLog']
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_ws_map(self):
        with io.open(self.pp.websocket_map_path(), 'w', encoding='utf-8', newline='\n') as fp:
            fp.write("map $http_upgrade $connection_upgrade {\n    default upgrade;\n    '' close;\n}\n")

    def test_apply_then_disable_round_trip(self):
        pp = self.pp
        self._write_ws_map()
        pp.yf.checkWebConfig = lambda: True
        pp.yf.restartWeb = lambda: True
        targets = [{'site': 'www.xx.com', 'vhost': self.vhost, 'https_port': 0,
                    'http_ports': [80]}]
        res = pp.apply(targets, entry_path='/q69dnrwy', restart=False)
        self.assertTrue(res['ok'], res)
        self.assertTrue(os.path.exists(pp.fragment_path()))
        self.assertIn(pp.MARK_BEGIN, _read(self.vhost))
        self.assertTrue(pp.is_enabled())

        res2 = pp.disable(restart=False)
        self.assertTrue(res2['ok'], res2)
        self.assertEqual(_read(self.vhost), SAMPLE_VHOST)
        self.assertFalse(os.path.exists(pp.fragment_path()))
        self.assertFalse(pp.is_enabled())

    def test_apply_rolls_back_when_nginx_test_fails(self):
        pp = self.pp
        self._write_ws_map()
        pp.yf.checkWebConfig = lambda: '[emerg] duplicate location "/"'
        pp.yf.restartWeb = lambda: True
        targets = [{'site': 'www.xx.com', 'vhost': self.vhost, 'https_port': 0,
                    'http_ports': [80]}]
        res = pp.apply(targets, entry_path='/q69dnrwy', restart=False)
        self.assertFalse(res['ok'])
        self.assertIn('nginx_config_test_failed', res['errors'])
        self.assertIn('duplicate location', res['nginx_error'])
        # 回滚：vhost 回到注入前，片段文件删除，状态不落盘
        self.assertEqual(_read(self.vhost), SAMPLE_VHOST)
        self.assertFalse(os.path.exists(pp.fragment_path()))
        self.assertFalse(pp.is_enabled())

    def test_disable_sweeps_stray_marker_without_state(self):
        pp = self.pp
        self._write_ws_map()
        self._write_ws_map()
        conf, _c, _r = pp.inject_marker(SAMPLE_VHOST, INCLUDE_PATH, ports=(80,), https_port=0)
        with io.open(self.vhost, 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(conf)
        pp.yf.checkWebConfig = lambda: True
        pp.yf.restartWeb = lambda: True
        res = pp.disable(restart=False)
        self.assertTrue(res['ok'], res)
        self.assertEqual(_read(self.vhost), SAMPLE_VHOST)

    def test_sync_never_raises(self):
        pp = self.pp
        # 未启用时直接返回，且不抛
        self.assertFalse(pp.sync())
        # 状态里写着启用但文件全丢：可以返回 False，但绝不能抛
        pp.save_state({'enable': True, 'targets': [{'vhost': '/nonexistent/x.conf'}],
                       'entry_path': '/q69dnrwy', 'panel_port': '7200'})
        try:
            pp.sync()
        except Exception as exc:  # noqa: BLE001
            self.fail('sync() 不允许抛异常: %s' % exc)


class TestWizardPrerequisites(unittest.TestCase):
    """守卫：`yf 33` 的两个前置条件必须自己引导，不许把用户堵在「未发现站点」上。

    现场（2026-11-04）：新机器直接跑 `yf 33`，只得到一句
    「未发现监听 80 端口的站点配置」就没下文了 —— 用户得自己猜要先装 OpenResty、
    先建站。本用例锁死这两条引导路径都真的能走下去。
    """

    @classmethod
    def setUpClass(cls):
        cls._cwd = os.getcwd()
        os.chdir(ROOT)
        if WEB not in sys.path:
            sys.path.insert(0, WEB)
        import panel_tools as pt
        cls.pt = pt
        cls.pp = _load_panel_proxy()

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._cwd)

    def setUp(self):
        self.pt = self.__class__.pt
        self.pp = self.__class__.pp
        self.saved = {}
        for mod, name in ((self.pp, 'web_server_kind'), (self.pp, 'list_targets'),
                          (self.pp, 'is_enabled'), (self.pp, 'apply'),
                          (self.pp, 'get_admin_path'), (self.pp, 'panel_port'),
                          (self.pp, 'upstream_scheme'),
                          (self.pt, '_sp_install_openresty'),
                          (self.pt, '_sp_detect_addresses')):
            self.saved[(id(mod), name)] = getattr(mod, name)
        self.answers = []
        self.saved_input = self.pt.yf_input_cmd
        self.pt.yf_input_cmd = lambda msg='': (self.answers.pop(0) if self.answers else '')
        # 避开数据库：这几个取值在向导里都只为展示
        self.pp.get_admin_path = lambda: 'q69dnrwy'
        self.pp.panel_port = lambda: '60347'
        self.pp.upstream_scheme = lambda: 'http'
        self.pp.is_enabled = lambda: False

    def tearDown(self):
        for (mid, name), val in self.saved.items():
            if mid == id(self.pp):
                setattr(self.pp, name, val)
            else:
                setattr(self.pt, name, val)
        self.pt.yf_input_cmd = self.saved_input

    def _run(self, answers):
        self.answers = list(answers)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = self.pt._single_port_proxy(None, None)
        return rc, out.getvalue()

    # ---- ① 未装 OpenResty ----

    def test_missing_openresty_offers_cli_install(self):
        self.pp.web_server_kind = lambda: ''
        called = []
        self.pt._sp_install_openresty = lambda pp: (called.append(1), False)[1]
        rc, out = self._run(['y'])           # 同意安装 -> 进入安装函数（这里桩为失败）
        self.assertEqual(rc, 1)
        self.assertTrue(called, '同意后必须真的去调用安装，而不是让用户去软件商店')
        self.assertIn('OpenResty', out)

    def test_missing_openresty_declined_still_mentions_app_store(self):
        self.pp.web_server_kind = lambda: ''
        self.pt._sp_install_openresty = lambda pp: False
        rc, out = self._run(['n'])
        self.assertEqual(rc, 1)
        self.assertIn('yf 33', out, '取消后要告诉用户装完怎么继续')

    def test_openresty_install_uses_store_command_shape(self):
        """安装必须走与软件商店完全同一条命令：`bash install.sh install <ver>`，
        且 cwd 必须是插件目录（install.sh 靠 pwd 推 serverPath）。"""
        plugin_dir, script, _info, versions = self.pt._sp_plugin_paths()
        if not script:
            self.skipTest('当前检出不带 openresty 插件包')
        self.assertTrue(versions, 'info.json 应解析出版本列表')
        src = _read(PANEL_TOOLS)
        self.assertIn("'install', version", src)
        self.assertIn('cwd=plugin_dir', src)

    # ---- ② 没有站点 ----

    def test_no_site_offers_to_create_one(self):
        self.pp.web_server_kind = lambda: 'openresty'
        created = []
        self.pp.list_targets = lambda port=80: created[-1] if created else []
        self.pt._sp_create_site = lambda pp: (created.append(True), True)[1]
        # 建站后进入选站点：回车=默认站点；再确认写入
        self.pp.apply = lambda *a, **k: {'ok': True, 'errors': [], 'entry_path': '/q69dnrwy',
                                         'panel_port': '60347',
                                         'targets': [{'site': '172.17.60.248', 'vhost': '/x.conf',
                                                      'https_port': 0}]}
        fake_target = {'site': '172.17.60.248', 'vhost': '/x.conf', 'http_ports': [80],
                       'https_port': 0, 'names': ['172.17.60.248'], 'is_default': False,
                       'injected': False}
        self.pp.list_targets = lambda port=80: ([fake_target] if created else [])
        rc, out = self._run(['y', '', ''])   # 建站 -> 选默认站点 -> 确认写入
        self.assertEqual(rc, 0, out)
        self.assertTrue(created, '没站点时必须真的去创站建站')

    def test_no_site_declined_shows_port_hint(self):
        self.pp.web_server_kind = lambda: 'openresty'
        self.pp.list_targets = lambda port=80: []
        rc, out = self._run(['n'])
        self.assertEqual(rc, 1)
        self.assertIn('菜单 6', out, '不建站时应保留「直接把面板端口改成 80」的提示')

    def test_create_site_asks_lan_or_wan(self):
        self.pp.web_server_kind = lambda: 'openresty'
        self.pp.list_targets = lambda port=80: []
        self.pt._sp_detect_addresses = lambda: ('172.17.60.248', '203.0.113.9')
        recorded = {}
        self.pt._sp_create_site_with = (
            lambda pp, primary, extras: (recorded.update(primary=primary, extras=extras), True)[1])
        # 建站 -> 建完仍无站点（模拟失败）→ 提前返回，但已能验证选择结果
        rc, out = self._run(['y', '2'])       # 选「外网地址」
        self.assertIn('172.17.60.248', out, '必须把内网/外网两个地址都摆出来给用户选')
        self.assertIn('203.0.113.9', out)
        self.assertEqual(recorded.get('primary'), '203.0.113.9')

    def test_create_site_both_addresses_by_default(self):
        self.pp.web_server_kind = lambda: 'openresty'
        self.pp.list_targets = lambda port=80: []
        self.pt._sp_detect_addresses = lambda: ('172.17.60.248', '203.0.113.9')
        recorded = {}
        self.pt._sp_create_site_with = (
            lambda pp, primary, extras: (recorded.update(primary=primary, extras=extras), True)[1])
        self._run(['y', ''])                  # 回车 = 默认项（两个都绑）
        self.assertEqual(recorded.get('primary'), '203.0.113.9')
        self.assertIn('172.17.60.248', recorded.get('extras') or [],
                      '默认应同时绑定内网与外网，避免 NAT 下 Host 不匹配掉进 403')


class PanelProxySourceGuardTest(unittest.TestCase):
    """源码级守卫：防止方案被"优化"回会炸的写法。"""

    def test_module_never_writes_conf_d(self):
        src = _read(PANEL_PROXY)
        # websocket_map.conf 必须落在 vhost/0.websocket.conf（nginx.conf 只 include
        # vhost/*.conf）；文中说明性的 `conf.d/` 不算，只禁止真拿它拼路径。
        self.assertNotRegex(src, r'[\'\"]/?conf\.d/',
                            'websocket_map.conf 必须落在 vhost/0.websocket.conf',
                            )

    def test_module_never_uses_duplicate_prone_location(self):
        src = _read(PANEL_PROXY)
        self.assertNotRegex(src, r'location\s+\^?~\s*/', '不得注入 location / 或 ^~ /')
        # 碎片文本里出现 location / 也视为回归（CONF 模板就写在模块里）
        self.assertNotRegex(src, r'\\n\s*location\s+/\s*\{')

    def test_config_writes_must_be_visible_on_failure(self):
        """配置类写入必须 must=True：`writeFile` 默认失败只返回 False 且永不抛，
        静默失败 = 面板入口没生效却回「成功」（本仓库专门有这条棘轮规则）。"""
        src = _read(PANEL_PROXY)
        self.assertIn('must=True', src)
        body = src[src.index('def _write_with_backup'):]
        body = body[:body.index('\n\n\n')]
        self.assertIn('must=True', body)

    def test_module_uses_safe_exec_only(self):
        src = _read(PANEL_PROXY)
        self.assertNotIn('os.system', src)
        self.assertNotIn('shell=True', src)

    def test_menu_and_command_wired(self):
        tools = _read(PANEL_TOOLS)
        self.assertRegex(tools, r'\(33\)\s+\S*单端口', '菜单缺 (33) 单端口项')
        self.assertRegex(tools, r'\(33\)\s+\S*[Pp]ort', '菜单缺英文文案')
        self.assertIn('yf_input == 33', tools)
        self.assertRegex(tools, r'\b33,\s*$|\b33\b[,\s]*\n',
                         'nums 列表必须认 33，否则菜单项点了报"未知命令"')
        self.assertIn("method == 'proxy'", tools, 'main() 缺 proxy 子命令')

        tpl = _read(YF_TPL)
        self.assertIn("'proxy')", tpl, 'yf.tpl 缺 proxy 分支')

    def test_hooks_are_installed(self):
        """改端口/改入口/开关 SSL 必须回调 panel_proxy.sync()，否则用户改完就失联。"""
        adm_setting = _read(os.path.join(WEB, 'admin', 'setting', 'setting.py'))
        self.assertIn('panel_proxy', adm_setting)
        utils_setting = _read(os.path.join(WEB, 'utils', 'setting.py'))
        self.assertIn('panel_proxy', utils_setting)
        site = _read(os.path.join(WEB, 'utils', 'site.py'))
        self.assertIn('panel_proxy', site)


class RewriteTemplatesConflictTest(unittest.TestCase):
    """证据用例：为什么不能用 `location /` 方案（伪静态模板普遍自带 `location /`）。"""

    def test_most_rewrite_templates_define_location_root(self):
        offenders = []
        for fn in sorted(os.listdir(REWRITE_DIR)):
            if not fn.endswith('.conf'):
                continue
            try:
                text = _read(os.path.join(REWRITE_DIR, fn))
            except Exception:
                continue
            if re.search(r'(?m)^\s*location\s+/\s*\{', text):
                offenders.append(fn)
        self.assertTrue(
            len(offenders) >= 10,
            '本仓库大量伪静态模板自带 location /（实测 %d 个），'
            '所以注入 location / 必然 duplicate location:%s' % (len(offenders), offenders))

    def test_site_template_puts_php_and_rewrite_includes_after_root(self):
        tpl = _read(TPL)
        self.assertIn('enable-php-', tpl)
        self.assertIn('#REWRITE-START', tpl)
        # 站点自己在 #error_page 标记处插入「强制 HTTPS」的 server 级 rewrite，
        # 因此面板片段必须插在 server_name 之后（更靠前）才不会被抢走
        self.assertLess(tpl.index('server_name'), tpl.index('#error_page 404/404.html;'))


if __name__ == '__main__':
    unittest.main()
