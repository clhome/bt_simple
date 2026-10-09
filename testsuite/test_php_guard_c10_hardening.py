# coding: utf-8
r"""C10 php-guard 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/php-guard/`（index.py + index.html + lang/）。真机是 Debian 12，php80/81/83
是**生产** PHP-FPM（php80 被站点引用）→ 本模块全部在**临时目录夹具**上真跑插件函数，
只碰夹具里的 php 目录，不启停任何生产服务。

真机探针（`test/_c10_probe.py`，安全载荷只写 /tmp 与夹具）暴露的缺陷（与 C07/C08/C09 同族）：
  * **版本号是唯一用户可控「命令/路径片段」入口**：HEAD 版 `repair_version()` 直接
    `"systemctl restart php" + version`、`"ps -ef | grep php/" + version + " | … | xargs kill -9"`，
    真机实测 `80; touch /tmp/…/PWN; #` **真的执行**（`A_INJ_PWN_CREATED=True`，root RCE）；
    `init.d` 路径同理由版本号拼成（穿越探测/任意可执行文件执行）。
    → new：`^\d{1,3}$` 白名单 + `isPhpVersion/versionOrError/isPhpInstalled`，非法版本零 shell 调用。
  * **旧前端形态 `args="'80'"`（字面引号）**：面板 `json.loads` 失败后把 `'80'` 当版本号 →
    `systemd`/`init.d` 路径全不命中 → 走到兜底分支 `grep php/'80'`（shell 去引号 = `php/80`）
    **把该版本全部 FPM 真杀一遍**（真机 `B_QUOTED_MATCH_PROD_PROCS=1`），然后报「未找到启动服务」
    —— 「杀掉正在服务的 PHP 且不重启」。
    → new：白名单拦下 + 前端改发 `JSON.stringify(String(version))`。
  * **假成功**：`restart` 命令成败完全不看（真机 `C_SYSTEMD_FAIL_RESULT` 在
    `Unit php999.service not found` 时仍回 `status:true`；夹具 init.d rc=1 同样回成功）。
    → new：`yf.execShellRc` 按退出码判成败。
  * **get_status 三处可靠性缺陷**：① `getFpmAddress` 对 TCP 监听版本回元组 → 循环里
    `sock.startswith('/')` 抛 AttributeError 逃出 → **只要有一个版本监听 TCP，整个状态接口失败**
    （真机夹具 `F1_STATUS_TCP` 报 `'tuple' object has no attribute 'startswith'`）；
    ② fcgi 空响应被判 `running`（假阳性，旧实现 `F2` 五个版本全 running）；
    ③ 只按 `isdigit()` 列目录 → php-apt 自愈出的空目录被当成已安装版本展示（假版本 `99`）。
    → new：元组拆成 `host:port` + `port_type`、空响应/非 bytes 判 stopped、与守护同判据
    （存在 `sbin/php-fpm`）。
  * **前端**：3 个 ajax 全无 `.fail()`（500/超时遮罩永久卡死）；`item.log`/`item.type`/
    `php.sock` 原样拼进 innerHTML（存储型 XSS）；`repair_version` 的业务失败被外层成功信封
    掩盖（`layer.msg(res.data)` 收到对象 → 显示 `[object Object]`，失败当成功）。
    → new：`pgEsc` + 3 处 `.fail()` + 内层 `status === false` 守卫 + 合法 JSON args。

断言策略：能真跑的一律在夹具里真跑（含真实 subprocess 执行夹具脚本验退出码）；结构类断言用
`ast`（抗「注释 / `if False:`」蒙混），前端用**去注释**后的源码断言（抗 JS 注释蒙混）。
"""
import ast
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_SRC = os.environ.get('YF_C10_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'php-guard')
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)

IDX = os.path.join(PLUGIN_SRC, 'index.py')
HTML = os.path.join(PLUGIN_SRC, 'index.html')
LANGDIR = os.path.join(PLUGIN_SRC, 'lang')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']

VERSION = '80'
TCP_VERSION = '83'
NOT_INSTALLED = '99'
BAD_VERSION = '80; touch /tmp/yf_c10_pwn; #'

NEW_FRONT_KEYS = ['状态获取请求失败,请刷新后重试!', '自愈日志获取失败,请刷新后重试!',
                  '手动诊断请求失败,请刷新后重试!']

WWWCONF = """[www]
user = www
group = www
listen = /tmp/php-cgi-%s.sock
pm.status_path = /phpfpm_status_%s
"""

TCPCONF = """[www]
user = www
group = www
listen = 127.0.0.1:9083
pm.status_path = /phpfpm_status_83
"""


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _write(path, text, mode=0o644):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    try:
        os.chmod(path, mode)
    except Exception:
        pass


def _tree(path):
    return ast.parse(_read(path))


def _func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _call_name(call):
    f = call.func
    parts = []
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        parts.append(f.id)
    return '.'.join(reversed(parts))


def _code_only(node):
    """函数体源码（由 `ast.unparse` 反生成，**不含注释**）——抗「注释里写旧写法蒙混」。"""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return '\n'.join(ast.unparse(b) for b in body)


def _strip_js_comments(src):
    out = []
    i, n = 0, len(src)
    quote = None
    while i < n:
        ch = src[i]
        if quote:
            out.append(ch)
            if ch == '\\' and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '/':
            while i < n and src[i] != '\n':
                i += 1
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '*':
            i += 2
            while i + 1 < n and not (src[i] == '*' and src[i + 1] == '/'):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def front_src():
    """index.html 的内联 JS，已去注释（抗「JS 注释蒙混」）。"""
    html = _read(HTML)
    blocks = re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)
    return _strip_js_comments('\n'.join(blocks))


class _Fixture(object):
    """把 `yf.getServerDir()` 等指到临时目录，真跑插件函数（不碰真机 /www/server/php）。"""

    def __init__(self, fcgi=b'{"pool":"www"}', systemd_rc=0, script_rc=0, real_scripts=False):
        self.root = tempfile.mkdtemp(prefix='c10_fx_')
        self.server = os.path.join(self.root, 'server')
        self.panel = os.path.join(self.root, 'panel')
        self.systemd = os.path.join(self.root, 'systemd')
        self.shells = []
        self.shellrcs = []
        self.fcgi = fcgi
        self.systemd_rc = systemd_rc
        self.script_rc = script_rc
        self.real_scripts = real_scripts
        self._build()
        self.mod = self._load()

    def _build(self):
        php = os.path.join(self.server, 'php')
        # 80：正常版本（有 sbin/php-fpm + init.d 脚本，退出码 0）
        # 81：init.d 脚本存在但退出码 1
        # 83：监听 TCP（触发 getFpmAddress 元组分支）
        # 999：有 unit 夹具（系统里并不存在该 unit）
        # 99：只有空目录（php-apt 自愈产物形态）
        for ver in (VERSION, '81', TCP_VERSION, '999'):
            _write(os.path.join(php, ver, 'sbin', 'php-fpm'), '#!/bin/sh\nexit 0\n', 0o755)
        os.makedirs(os.path.join(php, NOT_INSTALLED))
        _write(os.path.join(php, VERSION, 'etc', 'php-fpm.d', 'www.conf'), WWWCONF % (VERSION, VERSION))
        _write(os.path.join(php, '81', 'etc', 'php-fpm.d', 'www.conf'), WWWCONF % ('81', '81'))
        _write(os.path.join(php, TCP_VERSION, 'etc', 'php-fpm.d', 'www.conf'), TCPCONF)
        for ver, rc in ((VERSION, 0), ('81', 1)):
            _write(os.path.join(php, 'init.d', 'php' + ver), '#!/bin/sh\nexit %d\n' % rc, 0o755)
        _write(os.path.join(self.systemd, 'php999.service'), '[Unit]\nDescription=fixture\n')
        _write(os.path.join(self.panel, 'data', '502Task.pl'), 'True\n')

    def _load(self):
        import core.yf  # noqa: F401
        cwd = os.getcwd()
        spec = importlib.util.spec_from_file_location('c10_php_guard_mod', IDX)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        finally:
            os.chdir(cwd)
        self.yf = sys.modules['core.yf']
        self._saved = {}
        self._patch(self.yf, 'getServerDir', lambda *a, **k: self.server)
        self._patch(self.yf, 'getPanelDir', lambda *a, **k: self.panel)
        self._patch(self.yf, 'getPluginDir', lambda *a, **k: self.root)
        self._patch(self.yf, 'systemdCfgDir', lambda *a, **k: self.systemd)
        self._patch(self.yf, 'execShell', self._exec_shell)
        self._patch(self.yf, 'execShellRc', self._exec_shell_rc)
        self._patch(self.yf, 'requestFcgiPHP', self._fcgi)
        self._patch(self.yf, 'M', self._m)
        return mod

    def _patch(self, obj, name, value):
        if name not in self._saved:
            self._saved[name] = getattr(obj, name)
        setattr(obj, name, value)

    def _fcgi(self, sock, uri, *a, **k):
        if isinstance(self.fcgi, Exception):
            raise self.fcgi
        return self.fcgi

    @staticmethod
    def _m(_table=''):
        class _Q(object):
            def where(self, *a, **k):
                return self

            def field(self, *a, **k):
                return self

            def order(self, *a, **k):
                return self

            def limit(self, *a, **k):
                return self

            def select(self):
                return []
        return _Q()

    def _exec_shell(self, cmd, cwd=None, timeout=None, shell=True):
        self.shells.append(str(cmd))
        return ('', '')

    def _exec_shell_rc(self, cmd, cwd=None, timeout=None, shell=True):
        self.shellrcs.append(str(cmd))
        if not shell and isinstance(cmd, (list, tuple)):
            argv = [str(x) for x in cmd]
            # 只真跑夹具内的脚本（POSIX），systemctl 之类一律用受控返回值
            if self.real_scripts and os.name != 'nt' and argv and argv[0].startswith(self.root):
                p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = p.communicate()
                return (p.returncode, out.decode('utf-8', 'replace'), err.decode('utf-8', 'replace'))
            if argv and argv[0] == 'systemctl':
                return (self.systemd_rc, '', '' if self.systemd_rc == 0 else 'fixture failure')
            return (self.script_rc, '', '' if self.script_rc == 0 else 'fixture rc=%s' % self.script_rc)
        return (self.systemd_rc, '', '')

    @property
    def all_shell_calls(self):
        return list(self.shells) + list(self.shellrcs)

    def close(self):
        for name, value in self._saved.items():
            setattr(self.yf, name, value)
        shutil.rmtree(self.root, ignore_errors=True)


class _Base(unittest.TestCase):
    fcgi = b'{"pool":"www"}'
    systemd_rc = 0

    def setUp(self):
        self.fx = _Fixture(fcgi=self.fcgi, systemd_rc=self.systemd_rc)

    def tearDown(self):
        self.fx.close()


# ---------------------------------------------------------------- 版本白名单
class TestVersionWhitelist(_Base):

    def test_01_injection_version_rejected_without_shell(self):
        r = self.fx.mod.repair_version(BAD_VERSION)
        self.assertFalse(r['status'])
        self.assertEqual('PHP版本参数不合法!', r['msg'])
        self.assertEqual([], self.fx.all_shell_calls,
                         '非法版本不得产生任何 shell 调用，实际: %r' % self.fx.all_shell_calls)

    def test_02_legacy_quoted_version_rejected(self):
        """旧前端形态 args="'80'"（字面引号）：HEAD 版会 grep php/'80' 真杀进程。"""
        r = self.fx.mod.repair_version("'80'")
        self.assertFalse(r['status'])
        self.assertEqual('PHP版本参数不合法!', r['msg'])
        self.assertEqual([], self.fx.all_shell_calls)

    def test_03_path_traversal_version_rejected(self):
        for bad in ('../../../../tmp/x', '/etc/passwd', '80/../../etc', '..', './80'):
            with self.subTest(bad=bad):
                fx = _Fixture()
                try:
                    r = fx.mod.repair_version(bad)
                    self.assertFalse(r['status'], bad)
                    self.assertEqual([], fx.all_shell_calls, bad)
                finally:
                    fx.close()

    def test_04_non_string_and_empty_rejected(self):
        for bad in (None, '', {}, [], 0.5):
            with self.subTest(bad=bad):
                fx = _Fixture()
                try:
                    r = fx.mod.repair_version(bad)
                    self.assertFalse(r['status'], bad)
                    self.assertEqual([], fx.all_shell_calls, bad)
                finally:
                    fx.close()

    def test_05_uninstalled_version_no_kill_pipeline(self):
        """未安装版本（只有空目录）不得「先强杀再报失败」。"""
        r = self.fx.mod.repair_version(NOT_INSTALLED)
        self.assertFalse(r['status'])
        self.assertTrue(r['msg'].startswith('PHP-99 未安装'), r['msg'])
        self.assertEqual([], self.fx.all_shell_calls)

    def test_06_is_php_version_shape(self):
        m = self.fx.mod
        for ok in ('80', '8', '123'):
            self.assertTrue(m.isPhpVersion(ok), ok)
        for bad in ('', '8.0', '80;x', 'abcd', '1234', None, '-80', '80 81'):
            self.assertFalse(m.isPhpVersion(bad), bad)
        self.assertTrue(m.isPhpVersion(' 80 '), '两侧空白应被 strip 后视为合法')

    def test_07_is_php_installed_uses_binary_not_plain_dir(self):
        m = self.fx.mod
        self.assertTrue(m.isPhpInstalled(VERSION))
        self.assertFalse(m.isPhpInstalled(NOT_INSTALLED),
                         '只有空目录的版本不算已安装（与 panel_task.check502 同判据）')


# ---------------------------------------------------------------- 如实报成败
class TestHonestResult(_Base):

    def test_10_systemd_failure_reports_false(self):
        fx = _Fixture(systemd_rc=1)
        try:
            r = fx.mod.repair_version('999')
            self.assertFalse(r['status'], 'restart 退出码非 0 不得报成功: %r' % r)
            self.assertIn('systemd', r['msg'])
        finally:
            fx.close()

    def test_11_systemd_success_reports_true(self):
        r = self.fx.mod.repair_version('999')
        self.assertTrue(r['status'], r)
        self.assertIn('systemd', r['msg'])

    def test_12_initd_failure_reports_false(self):
        fx = _Fixture(script_rc=1)
        try:
            r = fx.mod.repair_version('81')
            self.assertFalse(r['status'], 'init.d 退出码非 0 不得报成功: %r' % r)
            self.assertIn('init.d', r['msg'])
            self.assertTrue(fx.shellrcs, '必须真的去调 init.d 脚本')
        finally:
            fx.close()

    def test_13_initd_success_reports_true(self):
        fx = _Fixture(script_rc=0)
        try:
            r = fx.mod.repair_version(VERSION)
            self.assertTrue(r['status'], r)
            self.assertIn('init.d', r['msg'])
        finally:
            fx.close()

    @unittest.skipIf(os.name == 'nt', 'POSIX 才能直接 exec 夹具脚本')
    def test_13b_initd_real_script_rc_propagates(self):
        """夹具脚本真跑（真实 subprocess）：rc=1 → 失败，rc=0 → 成功。"""
        fx = _Fixture(real_scripts=True)
        try:
            self.assertFalse(fx.mod.repair_version('81')['status'])
        finally:
            fx.close()
        fx = _Fixture(real_scripts=True)
        try:
            self.assertTrue(fx.mod.repair_version(VERSION)['status'])
        finally:
            fx.close()

    def test_14_repair_uses_rc_check_and_no_shell_string(self):
        """ast 结构断言：repair_version 必须按 rc 判成败、不得再拼 shell 字符串。"""
        tree = _tree(IDX)
        fn = _func(tree, 'repair_version')
        self.assertIsNotNone(fn)
        calls = [_call_name(n) for n in ast.walk(fn) if isinstance(n, ast.Call)]
        self.assertTrue(any(c.endswith('execShellRc') for c in calls),
                        'repair_version 必须用 execShellRc 取退出码')
        self.assertFalse(any(c.endswith('execShell') for c in calls),
                         'repair_version 不得再用无法判成败的 execShell')
        src = _code_only(fn)
        self.assertGreaterEqual(src.count('rc != 0'), 2, '两个分支都必须判 rc')
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and _call_name(node).endswith('execShell'):
                for arg in node.args:
                    self.assertNotIsInstance(arg, ast.BinOp, 'execShell 的参数不得是字符串拼接')

    def test_15_kill_pipeline_removed(self):
        """`ps -ef | grep php/<v> | … | xargs kill -9` 必须整条消失（避免杀完不重启）。

        用 ast 只在**字符串字面量**里找（抗注释蒙混：注释里提旧写法不算缺陷）。
        """
        lits = []
        for node in ast.walk(_tree(IDX)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                lits.append(node.value)
        blob = '\n'.join(lits)
        for token in ('ps -ef', 'xargs', 'kill -9', 'grep php/'):
            self.assertNotIn(token, blob, '模块里仍存在会拼接 shell 的字面量: %s' % token)

    def test_16_no_unconditional_success_return(self):
        """成功的 return 必须整体位于「rc == 0 分支」内，不能被无条件送出。"""
        tree = _tree(IDX)
        fn = _func(tree, 'repair_version')
        self.assertIsNotNone(fn)
        guarded = 0
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue
            dumped = ast.dump(node.test)
            if 'rc' not in dumped:
                continue
            guarded += 1
            self.assertTrue(any(isinstance(s, ast.Return) for s in ast.walk(node)),
                            'rc 分支里必须有 return（按退出码判成败）')
        self.assertGreaterEqual(guarded, 2, 'systemd / init.d 两个分支都要判 rc')
        # try 体里不得存在「顶层」成功 return（即不在任何 If 内）
        for node in fn.body:
            if isinstance(node, ast.Try):
                for stmt in node.body:
                    if isinstance(stmt, ast.Return):
                        val = ast.dump(stmt)
                        self.assertNotIn('True', val, 'try 体顶层不得直接回成功')
        src = _code_only(fn)
        for lit in ('已通过 systemd 重启', '已通过 init.d 重启'):
            pos = src.find(lit)
            self.assertGreater(pos, 0, lit)
            self.assertIn('rc != 0', src[:pos], '%s 之前必须先判 rc' % lit)


# ---------------------------------------------------------------- get_status
class TestGetStatus(_Base):
    fcgi = b'{"pool":"www"}'

    def _versions(self, r):
        self.assertTrue(r.get('status'), r)
        return [x['version'] for x in r['data']['php_status']]

    def test_20_tcp_listen_version_does_not_break_api(self):
        r = self.fx.mod.get_status()
        self.assertTrue(r['status'], r)
        row = [x for x in r['data']['php_status'] if x['version'] == TCP_VERSION][0]
        self.assertEqual('tcp', row['port_type'])
        self.assertEqual('127.0.0.1:9083', row['sock'])
        self.assertEqual('running', row['status'])

    def test_21_empty_fcgi_response_is_stopped(self):
        """空响应（连接异常）不得判 running。"""
        fx = _Fixture(fcgi=b'')
        try:
            r = fx.mod.get_status()
            self.assertTrue(r['status'], r)
            self.assertEqual(['stopped'] * len(r['data']['php_status']),
                             [x['status'] for x in r['data']['php_status']])
        finally:
            fx.close()

    def test_22_bad_gateway_markers_are_stopped(self):
        for marker in (b'Bad Gateway', b'HTTP Error 404: Not Found', b'Connection refused'):
            with self.subTest(marker=marker):
                fx = _Fixture(fcgi=marker)
                try:
                    r = fx.mod.get_status()
                    self.assertTrue(r['status'])
                    self.assertNotIn('running', [x['status'] for x in r['data']['php_status']])
                finally:
                    fx.close()

    def test_23_fcgi_exception_is_stopped_not_crash(self):
        fx = _Fixture(fcgi=FileNotFoundError('socket gone'))
        try:
            r = fx.mod.get_status()
            self.assertTrue(r['status'], r)
            self.assertNotIn('running', [x['status'] for x in r['data']['php_status']])
        finally:
            fx.close()

    def test_24_phantom_dir_not_listed(self):
        vers = self._versions(self.fx.mod.get_status())
        self.assertNotIn(NOT_INSTALLED, vers, '只有空目录的版本不得列出（假版本）')
        self.assertIn(VERSION, vers)
        self.assertIn(TCP_VERSION, vers)

    def test_25_daemon_flag_reflects_marker_file(self):
        self.assertTrue(self.fx.mod.get_status()['data']['daemon_enabled'])
        os.remove(os.path.join(self.fx.panel, 'data', '502Task.pl'))
        self.assertFalse(self.fx.mod.get_status()['data']['daemon_enabled'])

    def test_26_result_is_json_serializable(self):
        json.dumps(self.fx.mod.get_status())

    def test_27_undecodable_bytes_do_not_raise(self):
        fx = _Fixture(fcgi=b'\xff\xfe\x00garbage')
        try:
            r = fx.mod.get_status()
            self.assertTrue(r['status'], r)
        finally:
            fx.close()

    def test_28_status_has_no_os_kill(self):
        """status 语义是「真连通性」，不得退化为进程/pid 存在性判断。"""
        src = _code_only(_func(_tree(IDX), 'get_status'))
        self.assertNotIn('os.kill', src)
        self.assertNotIn('ps -ef', src)


# ---------------------------------------------------------------- 前端
class TestFrontend(unittest.TestCase):

    def setUp(self):
        self.src = front_src()

    def test_30_escape_helper_defined_and_used(self):
        self.assertIn('function pgEsc(', self.src)
        for field in ('pgEsc(item.log)', 'pgEsc(item.type)', 'pgEsc(item.add_time)',
                      'pgEsc(php.sock)', 'pgEsc(php.version)'):
            self.assertIn(field, self.src, field)

    def test_31_no_raw_backend_field_in_html(self):
        for raw in ("+ item.log +", "+ item.type +", "+ item.add_time +", "+ php.sock +"):
            self.assertNotIn(raw, self.src, raw)

    def test_32_all_ajax_have_fail(self):
        self.assertEqual(3, self.src.count('$.post('))
        self.assertEqual(3, self.src.count('.fail('), '三个 ajax 都必须有 .fail()')

    def test_33_repair_args_is_valid_json(self):
        self.assertIn('JSON.stringify(String(version))', self.src)
        self.assertNotIn("args: \"'\" + version", self.src)

    def test_34_inner_status_guards_present(self):
        self.assertGreaterEqual(self.src.count('status === false'), 3,
                                '三个回调都要有内层业务失败守卫')

    def test_35_repair_success_shows_business_message(self):
        """业务失败不得走成功分支（HEAD 把对象塞给 layer.msg）。"""
        self.assertIn('body.status === false', self.src)
        self.assertNotIn("layer.msg(res.data ||", self.src)


# ---------------------------------------------------------------- 语言包
class TestLang(unittest.TestCase):

    def _lang(self, name):
        return json.loads(_read(os.path.join(LANGDIR, name + '.json')))

    def test_40_six_languages_key_parity(self):
        sets = {n: set(self._lang(n)) for n in LANGS}
        base = sets['zh-CN']
        for n in LANGS:
            self.assertEqual(base, sets[n], '%s 键集与其他语言不一致' % n)

    def test_41_new_backend_and_frontend_keys_present(self):
        zh = self._lang('zh-CN')
        for k in NEW_FRONT_KEYS:
            self.assertIn(k, zh, k)

    def test_42_frontend_fail_keys_are_used(self):
        """新增键必须真被 pt() 用到（否则是死键）。"""
        for k in NEW_FRONT_KEYS:
            self.assertIn("pt('%s')" % k, self.src if hasattr(self, 'src') else front_src(), k)

    def test_43_lang_files_are_lf_utf8(self):
        for n in LANGS:
            with io.open(os.path.join(LANGDIR, n + '.json'), 'rb') as fh:
                raw = fh.read()
            self.assertNotIn(b'\r\n', raw, n)
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), n)
            json.loads(raw.decode('utf-8'))

    def test_44_new_keys_are_not_dirty(self):
        """新键不得是拼接/HTML/转义残留（verify_i18n 的脏键规则同口径）。"""
        for n in LANGS:
            data = self._lang(n)
            for k in NEW_FRONT_KEYS:
                self.assertNotIn('<', k)
                self.assertNotIn('+', k)
                self.assertEqual(k.strip(), k)


# ---------------------------------------------------------------- 源码/编码
class TestSourceHygiene(unittest.TestCase):

    def test_50_index_py_lf_no_bom(self):
        with io.open(IDX, 'rb') as fh:
            raw = fh.read()
        self.assertNotIn(b'\r\n', raw)
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))

    def test_51_no_hardcoded_mdserver_web(self):
        self.assertNotIn('mdserver-web', _read(IDX))

    def test_52_cli_status_contract(self):
        """CLI 契约：status → start（面板 checkStatusReal 只看这一行）。"""
        p = subprocess.Popen([sys.executable, IDX, 'status'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             cwd=os.path.join(WEB_DIR, '..'))
        out, _ = p.communicate(timeout=60)
        self.assertEqual('start', out.decode('utf-8', 'replace').strip())


if __name__ == '__main__':
    unittest.main()
