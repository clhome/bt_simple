# coding: utf-8
r"""C05 varnish 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/varnish/`。真机 Debian12 上 varnish **未安装**（`which varnishd varnishadm`
无输出、`/www/server/varnish` 与 `/etc/varnish` 不存在、`systemctl is-enabled varnish` =
`No such file or directory`），openresty 是生产 web 服务器（888 + 站点 80）→ 口径 =
**夹具真跑 + 真机 HTTP 面核对**（与 C01/C04 同款，不改动任何生产服务）。

真机对照（详见 task.md 的 C05 行）：
  * 里程碑契约「未安装 → status 必须回 stop；运行中 → status 必须回 start」：
    夹具三态 —— 未安装 / 装了未运行 → `stop`；真存活进程（`/bin/sleep` 复制成 `varnishd`，
    comm 精确为 varnishd）+ 真 pid 文件 `/run/varnishd.pid` → `start`；陈旧 pid 文件 → `stop`。
  * 历史误报根因（`ps -ef|grep varnish` 缺 `grep -v python`）：真机自身匹配探针实测
    V1(`grep -v grep` 之后无 python 过滤) → `start pids=<探针自身 python 进程>`；加 python
    过滤 → `stop`。
  * HEAD 版仍存在的误报：`tail -f /var/log/varnish/varnish.log` 这类**无关进程**同样被
    `grep varnish` 命中 → 真机实测 HEAD 版 `status()` 回 `start`（此时根本没装 varnish）。
  * 真机 HTTP 面（`/plugins/run` + App 凭据，用后即删）：修复前 `status`→`start`、
    `initd_install`→`ok`（而 `systemctl is-enabled varnish` = No such file or directory）、
    `read_config_tpl`(JSON argv)→「缺少必要参数: file」、`read_config_tpl`(缺文件)→整段
    `AttributeError` traceback；修复后 `stop` / 业务错误信封 / VCL 正文 / 「配置文件不存在
    或无法读取!」，且 unit 文件与安装目录零新增。

夹具：`yf.getServerDir()` 指到临时目录（= 面板安装标记），`yf.getPluginDir()` 指到夹具
插件目录（tpl 真文件 + 软链逃逸用例），`yf.execShell`/`yf.execShellRc` 换成**记录型进程表
桩**——模拟真机实测的进程表（面板自身 python 子进程、软链路径下的 python 子进程、命令行
提到 varnish 的无关进程、真 varnishd 进程），并按命令文本里的 `grep -v …` 过滤规则回放，
于是 ps|grep 与 pgrep 两条判据都能在夹具里真跑、可被逐条回退验证。

断言策略：能真跑的一律真跑；结构类断言用 `ast`（抗「Python 注释 / if False: 蒙混」），
前端用去注释后的源码断言（抗「JS 注释蒙混」）。
"""
import ast
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, 'plugins', 'varnish')

#: 变异探针可覆盖：指向临时副本后重跑本文件，对应用例必须变红
IDX = os.environ.get('YF_C05_INDEX') or os.path.join(PLUGIN, 'index.py')
JS = os.environ.get('YF_C05_JS') or os.path.join(PLUGIN, 'js', 'varnish.js')
INSTALL_SH = os.environ.get('YF_C05_INSTALL') or os.path.join(PLUGIN, 'install.sh')
LANGDIR = os.environ.get('YF_C05_LANGDIR') or os.path.join(PLUGIN, 'lang')

LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
#: 本轮新增的后端消息键（六语言必须齐备且一致）
NEW_MSG_KEYS = ['varnish 未安装!', 'Varnish 状态获取失败,请检查服务是否已启动!',
                '配置文件不存在或无法读取!', 'varnish 日志文件不存在!', '开机启动设置失败!']
#: 本轮新增的前端提示键
NEW_JS_KEYS = ['状态获取请求失败,请刷新后重试!', '配置文件路径获取失败!', '文件内容获取失败!']
CJK_RE = re.compile(r'[\u3400-\u9fff]')


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _write(path, text):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


def _str_lit(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if node.__class__.__name__ == 'Str':  # pragma: no cover - 老版本兼容
        return node.s
    return None


def _tree(path=None):
    return ast.parse(_read(path or IDX))


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


def _calls(node):
    return [_call_name(n) for n in ast.walk(node) if isinstance(n, ast.Call)]


def _str_literals(node):
    out = []
    for n in ast.walk(node):
        lit = _str_lit(n)
        if lit is not None:
            out.append(lit)
    return out


def _strip_js_comments(src):
    """抹掉 JS 注释（保留字符串/正则字面量），避免把旧写法写在注释里骗过断言。

    必须识别正则字面量：`/\"/g` 这类正则里的引号会把「引号配对」状态机带偏，
    一旦带偏，后面的 `//` 注释就剥不掉 → 注释蒙混探针会漏判（真机实测过）。
    """
    out = []
    i, n = 0, len(src)
    quote = None
    prev = ''
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
            prev = ch
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
        if ch == '/' and prev in ('', '(', ',', '=', ':', '[', '!', '&', '|', '?', '{', '}', ';'):
            out.append(ch)
            i += 1
            in_class = False
            while i < n:
                c = src[i]
                if c == '\\' and i + 1 < n:
                    out.append(c)
                    out.append(src[i + 1])
                    i += 2
                    continue
                if c == '[':
                    in_class = True
                elif c == ']':
                    in_class = False
                elif c == '/' and not in_class:
                    out.append(c)
                    i += 1
                    break
                elif c == '\n':
                    break
                out.append(c)
                i += 1
            prev = '/'
            continue
        out.append(ch)
        if not ch.isspace():
            prev = ch
        i += 1
    return ''.join(out)


def _js_function(src, name):
    """取 JS 顶层函数体（花括号配对），返回不含注释的源码；找不到返回 None。"""
    m = re.search(r'\nfunction\s+' + re.escape(name) + r'\s*\(', src)
    if not m:
        return None
    i = src.index('{', m.end() - 1)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return _strip_js_comments(src[m.start():j + 1])
    return None


# ---------------------------------------------------------------------------
# 记录型进程表桩（回放真机实测的进程表 + 命令文本里的 grep 过滤规则）
# ---------------------------------------------------------------------------

class _ProcTable(object):
    running = False          # comm 精确为 varnishd 的真进程
    decoy = False            # 无关进程（cmdline 提到 varnish，如 tail -f /var/log/varnish/varnish.log）
    self_python = True       # 面板以 python 调用本插件（cmdline 同时含 varnish 与 python）
    self_python_alt = False  # 软链/改名后的面板目录：argv 含 python 但不含 getPanelDir()
    unit_state = 'missing'   # enabled / enabled-runtime / disabled / missing
    sysctl = {}              # action -> (rc, out, err)
    varnishstat = (0, '{"counters": {"MAIN.cache_hit": {"value": 3, "description": "hit"}}}', '')
    calls = []


def _ps_lines():
    panel = _Fixture.panel_dir
    lines = []
    if _ProcTable.self_python:
        lines.append('root 4242 4241 0 00:00 ? 00:00:00 %s/bin/python3 '
                     '%s/plugins/varnish/index.py status' % (panel, panel))
    if _ProcTable.self_python_alt:
        # 真机历史：面板目录改名/软链时 argv 里的路径与 getPanelDir() 不同，
        # 只有 `grep -v python` 能挡住这一行（缺它就是里程碑说的误报根因）
        lines.append('root 4243 4241 0 00:00 ? 00:00:00 /usr/bin/python3 '
                     '/www/server/mdserver-web/plugins/varnish/index.py status')
    if _ProcTable.decoy:
        lines.append('root 4244 1 0 00:00 ? 00:00:00 tail -f /var/log/varnish/varnish.log')
    if _ProcTable.running:
        lines.append('root 4245 1 0 00:00 ? 00:00:00 /usr/sbin/varnishd -a :6081 '
                     '-f /etc/varnish/default.vcl')
    return lines


def _filter_lines(cmd_text, lines):
    if 'grep -v grep' in cmd_text:
        lines = [ln for ln in lines if 'grep' not in ln]
    if 'grep -v python' in cmd_text:
        lines = [ln for ln in lines if 'python' not in ln]
    for tok in re.findall(r'grep -v\s+(\S+)', cmd_text):
        tok = tok.strip('\'"')
        if tok in ('grep', 'python'):
            continue
        lines = [ln for ln in lines if tok not in ln]
    return lines


def _sysctl_out(text):
    """execShell 形态（旧实现）的系统调用回放：(stdout, stderr)。"""
    parts = text.split()
    if 'status' in parts:
        if _ProcTable.unit_state in ('enabled', 'enabled-runtime'):
            return ('   Loaded: loaded (/lib/systemd/system/varnish.service; %s; preset: enabled)'
                    % _ProcTable.unit_state, '')
        return ('', '')
    for action in ('daemon-reload', 'enable', 'disable', 'start', 'stop', 'restart', 'reload'):
        if action in parts:
            rc, out, err = _ProcTable.sysctl.get(action, (0, '', ''))
            return (out, err)
    return ('', '')


def fake_execShell(cmd, cwd=None, timeout=None, shell=True):
    text = cmd if isinstance(cmd, str) else ' '.join(str(x) for x in cmd)
    _ProcTable.calls.append(text)
    if 'ps -ef' in text and 'varnish' in text:
        return ('\n'.join(_filter_lines(text, _ps_lines())), '')
    if 'systemctl' in text:
        return _sysctl_out(text)
    return ('', '')


def fake_execShellRc(cmd, cwd=None, timeout=None, shell=True):
    argv = list(cmd) if isinstance(cmd, (list, tuple)) else shlex.split(cmd)
    _ProcTable.calls.append(argv)
    prog = argv[0] if argv else ''
    if prog == 'pgrep':
        if _ProcTable.running:
            return (0, '4245\n', '')
        return (1, '', '')
    if prog == 'systemctl':
        action = argv[1] if len(argv) > 1 else ''
        if action == 'is-enabled':
            state = _ProcTable.unit_state
            if state == 'missing':
                return (1, '', 'Failed to get unit file state for varnish.service: '
                               'No such file or directory')
            return (0 if state.startswith('enabled') else 1, state + '\n', '')
        rc, out, err = _ProcTable.sysctl.get(action, (0, '', ''))
        return (rc, out, err)
    if prog == 'varnishstat':
        return _ProcTable.varnishstat
    return (0, '', '')


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

class _Fixture(unittest.TestCase):
    server = ''
    panel_dir = ''
    mod = None
    yf = None

    @classmethod
    def setUpClass(cls):
        cls._cwd = os.getcwd()
        cls.root = tempfile.mkdtemp(prefix='c05_varnish_')
        cls.server = os.path.join(cls.root, 'server')
        cls.plugroot = os.path.join(cls.root, 'plugins')
        cls.tpldir = os.path.join(cls.plugroot, 'varnish', 'tpl')
        os.makedirs(cls.tpldir, exist_ok=True)
        cls.logdir = os.path.join(cls.root, 'log')
        os.makedirs(cls.logdir, exist_ok=True)
        cls.outside = os.path.join(cls.root, 'outside.vcl')
        _write(cls.outside, 'OUTSIDE-SECRET\n')
        _write(os.path.join(cls.tpldir, 'default.vcl'),
               'vcl 4.0;\n# fixture\nacl purge { "127.0.0.1"; }\n')
        _write(os.path.join(cls.tpldir, 'notes.txt'), 'not a vcl\n')

        sys.path.insert(0, os.path.join(ROOT, 'web'))
        import core.yf as yf
        cls.yf = yf
        cls.panel_dir = yf.getPanelDir()
        cls._orig = dict((k, getattr(yf, k, None))
                         for k in ('getServerDir', 'getPluginDir',
                                   'execShell', 'execShellRc'))
        yf.getServerDir = lambda *a, **k: cls.server
        yf.getPluginDir = lambda *a, **k: cls.plugroot
        yf.execShell = fake_execShell
        yf.execShellRc = fake_execShellRc

        os.chdir(ROOT)
        spec = importlib.util.spec_from_file_location('c05_varnish_idx', IDX)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        os.chdir(cls._cwd)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._cwd)
        for k, v in cls._orig.items():
            if v is not None:
                setattr(cls.yf, k, v)
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        _ProcTable.running = False
        _ProcTable.decoy = False
        _ProcTable.self_python = True
        _ProcTable.self_python_alt = False
        _ProcTable.unit_state = 'missing'
        _ProcTable.sysctl = {}
        _ProcTable.varnishstat = (0, '{"counters": {"MAIN.cache_hit": {"value": 3, '
                                     '"description": "hit"}}}', '')
        _ProcTable.calls[:] = []
        shutil.rmtree(os.path.join(self.server, 'varnish'), ignore_errors=True)
        self.mod.VARNISH_LOG_CANDIDATES = ('/var/log/varnish/varnish.log',
                                           '/var/log/varnish/varnishncsa.log')
        self._symlink = None

    def tearDown(self):
        if self._symlink and os.path.islink(self._symlink):
            os.remove(self._symlink)

    # ---- 夹具控制 ----
    def install(self, on=True):
        marker = os.path.join(self.server, 'varnish')
        if on:
            os.makedirs(marker, exist_ok=True)
            _write(os.path.join(marker, 'version.pl'), '1.1\n')
        else:
            shutil.rmtree(marker, ignore_errors=True)

    def set_unit(self, state):
        _ProcTable.unit_state = state

    def argv_call(self, func, *argv):
        old = list(sys.argv)
        sys.argv = ['index.py', func] + list(argv)
        try:
            return ('OK', getattr(self.mod, func)())
        except Exception as e:
            return ('RAISED', '%s: %s' % (type(e).__name__, e))
        finally:
            sys.argv = old

    def json_of(self, raw):
        if isinstance(raw, dict):
            return raw
        return json.loads(raw)

    def systemctl_calls(self):
        out = []
        for c in _ProcTable.calls:
            argv = c if isinstance(c, list) else shlex.split(c)
            if argv and argv[0] == 'systemctl':
                out.append(' '.join(argv))
        return out


# ---------------------------------------------------------------------------
# 1. 里程碑契约：status() 的三态真判据
# ---------------------------------------------------------------------------

class TestStatus(_Fixture):

    def test_01_not_installed_is_stop(self):
        """未安装 → stop。"""
        self.install(False)
        self.assertEqual(self.mod.status(), 'stop')

    def test_02_panel_python_selfmatch_is_stop(self):
        """面板以 python 调用本插件（cmdline 含 varnish）时不得把自己算成运行中。"""
        self.install(False)
        self.assertTrue(_ProcTable.self_python)
        self.assertEqual(self.mod.status(), 'stop')

    def test_03_renamed_panel_dir_python_is_stop(self):
        """面板目录改名/软链时（argv 里的路径 ≠ getPanelDir()）同样不得误报。"""
        self.install(False)
        _ProcTable.self_python_alt = True
        self.assertEqual(self.mod.status(), 'stop')

    def test_04_unrelated_process_mentioning_varnish_is_stop(self):
        """无关进程（tail -f /var/log/varnish/varnish.log）不得算成 varnish 在运行。"""
        self.install(False)
        _ProcTable.decoy = True
        self.assertEqual(self.mod.status(), 'stop')

    def test_05_installed_but_stopped_is_stop(self):
        """装了但没进程 → stop（不得只看安装目录/pid 文件存在性）。"""
        self.install(True)
        self.assertEqual(self.mod.status(), 'stop')

    def test_06_running_is_start(self):
        """真存活进程（comm 精确 varnishd）+ 真 pid 文件 → start。"""
        self.install(True)
        _ProcTable.running = True
        pidfile = os.path.join(self.root, 'run', 'varnishd.pid')
        os.makedirs(os.path.dirname(pidfile), exist_ok=True)
        _write(pidfile, '4245\n')
        self.assertEqual(self.mod.status(), 'start')

    def test_07_running_with_decoy_is_start(self):
        self.install(True)
        _ProcTable.running = True
        _ProcTable.decoy = True
        self.assertEqual(self.mod.status(), 'start')

    def test_08_stale_pid_file_is_not_start(self):
        """陈旧 pid 文件不得造成假阳性。"""
        self.install(False)
        pidfile = os.path.join(self.root, 'run', 'varnishd.pid')
        os.makedirs(os.path.dirname(pidfile), exist_ok=True)
        _write(pidfile, '999999\n')
        self.assertEqual(self.mod.status(), 'stop')
        fn = _func(_tree(), 'status')
        lits = ' '.join(_str_literals(fn))
        self.assertNotIn('pid', lits.lower(), 'status() 不得以 pid 文件存在性为判据')
        self.assertNotIn('os.path.exists', _calls(fn), 'status() 不得以文件存在性为判据')

    def test_09_status_uses_exact_process_name(self):
        """结构：必须用 `pgrep -x varnishd` 精确匹配，不得回退 `ps -ef|grep varnish`。"""
        fn = _func(_tree(), 'status')
        self.assertIsNotNone(fn)
        self.assertEqual(self.mod.VARNISH_PROCESS, 'varnishd')
        lits = ' '.join(_str_literals(fn))
        self.assertIn('pgrep', lits)
        self.assertNotIn('ps -ef', lits)
        self.assertNotIn('grep varnish', lits)
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
        rc_calls = [n for n in calls if _call_name(n).endswith('execShellRc')]
        self.assertTrue(rc_calls, 'status() 必须用 execShellRc（要看退出码）')
        self.assertNotIn('yf.execShell', _calls(fn), 'status() 不得再用 execShell 字符串判据')
        kwargs = dict((k.arg, k) for n in rc_calls for k in n.keywords)
        self.assertIn('timeout', kwargs, '进程探测必须带超时')
        self.assertIsInstance(kwargs['timeout'].value, ast.Constant)
        # 真跑一遍：记录的 argv 必须是精确进程名匹配
        self.install(False)
        _ProcTable.calls[:] = []
        self.mod.status()
        self.assertIn(['pgrep', '-x', 'varnishd'], _ProcTable.calls)

    def test_10_status_never_shells_out_via_string(self):
        """结构：模块内所有 execShellRc 调用必须是 list argv（无字符串拼 shell）。"""
        for n in ast.walk(_tree()):
            if isinstance(n, ast.Call) and _call_name(n).endswith('execShellRc'):
                self.assertTrue(n.args and isinstance(n.args[0], (ast.List, ast.Tuple)),
                                'execShellRc 只允许 list argv 形态')


# ---------------------------------------------------------------------------
# 2. argv 层：getArgs / checkArgs
# ---------------------------------------------------------------------------

class TestArgsLayer(_Fixture):

    def test_11_getArgs_json_single_argv(self):
        """前端真实形态：一个 JSON argv 必须解析成 dict（旧实现切成 '"file"' 键）。"""
        old = list(sys.argv)
        sys.argv = ['index.py', 'read_config_tpl',
                    json.dumps({'file': self.tpldir + '/default.vcl'})]
        try:
            self.assertEqual(self.mod.getArgs(),
                             {'file': self.tpldir + '/default.vcl'})
        finally:
            sys.argv = old

    def test_12_getArgs_malformed_returns_empty(self):
        """畸形 argv（空对象/裸值/数组/无参）必须回 {}，不得 IndexError。"""
        for argv in (['{}'], ['foo'], ['[1,2]'], ['1.1'], []):
            old = list(sys.argv)
            sys.argv = ['index.py', 'getArgs'] + argv
            try:
                self.assertEqual(self.mod.getArgs(), {}, 'argv=%r' % argv)
            finally:
                sys.argv = old

    def test_13_getArgs_kv_fallback(self):
        old = list(sys.argv)
        sys.argv = ['index.py', 'f', 'file:/a.vcl', 'x:1']
        try:
            self.assertEqual(self.mod.getArgs(), {'file': '/a.vcl', 'x': '1'})
        finally:
            sys.argv = old

    def test_14_checkArgs_non_dict(self):
        ok, payload = self.mod.checkArgs(None, ['file'])
        self.assertFalse(ok)
        self.assertIn('缺少必要参数', self.json_of(payload)['msg'])


# ---------------------------------------------------------------------------
# 3. readConfigTpl / configTpl
# ---------------------------------------------------------------------------

class TestConfigTpl(_Fixture):

    def test_15_read_config_tpl_json_argv_returns_content(self):
        """真 UI 形态（JSON argv）必须真的读到模板正文（旧实现回「缺少必要参数」）。"""
        kind, raw = self.argv_call('readConfigTpl',
                                   json.dumps({'file': self.tpldir + '/default.vcl'}))
        self.assertEqual(kind, 'OK')
        payload = self.json_of(raw)
        self.assertTrue(payload['status'])
        self.assertIn('acl purge', payload['data'])

    def test_16_read_config_tpl_kv_argv_returns_content(self):
        kind, raw = self.argv_call('readConfigTpl', 'file:' + self.tpldir + '/default.vcl')
        self.assertEqual(kind, 'OK')
        self.assertIn('acl purge', self.json_of(raw)['data'])

    def test_17_read_config_tpl_traversal_blocked(self):
        for argv in (json.dumps({'file': '/etc/passwd'}),
                     'file:/etc/passwd',
                     json.dumps({'file': '/etc/passwd.vcl'}),
                     json.dumps({'file': self.outside})):
            kind, raw = self.argv_call('readConfigTpl', argv)
            self.assertEqual(kind, 'OK', argv)
            payload = self.json_of(raw)
            self.assertFalse(payload['status'], argv)
            self.assertIn('越权访问拦截', payload['msg'], argv)

    def test_18_read_config_tpl_missing_file_is_business_error(self):
        """readFile 返回 False 时必须是业务错误，不得 AttributeError traceback。"""
        for argv in (json.dumps({'file': self.tpldir + '/nope.vcl'}),
                     'file:' + self.tpldir + '/nope.vcl'):
            kind, raw = self.argv_call('readConfigTpl', argv)
            self.assertEqual(kind, 'OK', argv)
            payload = self.json_of(raw)
            self.assertFalse(payload['status'], argv)
            self.assertEqual(payload['msg'], '配置文件不存在或无法读取!')

    def test_19_read_config_tpl_symlink_escape_blocked(self):
        link = os.path.join(self.tpldir, 'evil.vcl')
        try:
            os.symlink(self.outside, link)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest('当前环境不支持创建软链')
        self._symlink = link
        kind, raw = self.argv_call('readConfigTpl', json.dumps({'file': link}))
        self.assertEqual(kind, 'OK')
        payload = self.json_of(raw)
        self.assertFalse(payload['status'])
        self.assertNotIn('OUTSIDE-SECRET', json.dumps(payload))

    def test_20_read_config_tpl_bad_file_arg(self):
        """非字符串/裸值/数组/无参一律回业务错误，不得抛异常。"""
        for argv in (json.dumps({'file': 123}), json.dumps({'file': None}),
                     'foo', '[1,2]', ''):
            kind, raw = self.argv_call('readConfigTpl', argv)
            self.assertEqual(kind, 'OK', argv)
            self.assertFalse(self.json_of(raw)['status'], argv)

    def test_21_config_tpl_lists_only_vcl(self):
        raw = self.mod.configTpl()
        files = json.loads(raw)
        self.assertEqual([os.path.basename(f) for f in files], ['default.vcl'])
        bak = self.tpldir + '.bak'
        os.rename(self.tpldir, bak)
        try:
            self.assertEqual(json.loads(self.mod.configTpl()), [])
        finally:
            os.rename(bak, self.tpldir)


# ---------------------------------------------------------------------------
# 4. runInfo / runLog
# ---------------------------------------------------------------------------

class TestInfoAndLog(_Fixture):

    def test_22_run_info_not_installed_is_business_error(self):
        """未安装不得回空串（面板会把它当成功）。"""
        self.install(False)
        payload = self.json_of(self.mod.runInfo())
        self.assertFalse(payload['status'])
        self.assertEqual(payload['msg'], 'varnish 未安装!')

    def test_23_run_info_passthrough_json(self):
        self.install(True)
        raw = self.mod.runInfo()
        self.assertTrue(raw.strip().startswith('{'))
        self.assertIn('MAIN.cache_hit', json.loads(raw)['counters'])

    def test_24_run_info_failure_is_business_error(self):
        self.install(True)
        # 退出码非 0 但 stdout 有残留：只看 stdout 空不空的旧契约会把残留当成功
        _ProcTable.varnishstat = (1, '{"counters": {}}', 'Cannot connect to varnishd')
        payload = self.json_of(self.mod.runInfo())
        self.assertFalse(payload['status'])
        self.assertEqual(payload['msg'], 'Varnish 状态获取失败,请检查服务是否已启动!')

    def test_25_run_log_missing_is_business_error(self):
        payload = self.json_of(self.mod.runLog())
        self.assertFalse(payload['status'])
        self.assertEqual(payload['msg'], 'varnish 日志文件不存在!')

    def test_26_run_log_returns_existing_path(self):
        log = os.path.join(self.logdir, 'varnish.log')
        _write(log, 'x\n')
        self.mod.VARNISH_LOG_CANDIDATES = (log, '/var/log/varnish/varnishncsa.log')
        self.assertEqual(self.mod.runLog(), log)


# ---------------------------------------------------------------------------
# 5. initdStatus / initdInstall / vaOp
# ---------------------------------------------------------------------------

class TestServiceOps(_Fixture):

    def test_27_initd_status_states(self):
        for state, want in (('enabled', 'ok'), ('enabled-runtime', 'ok'),
                            ('disabled', 'fail'), ('missing', 'fail')):
            self.set_unit(state)
            self.assertEqual(self.mod.initdStatus(), want, state)

    def test_28_initd_status_uses_is_enabled(self):
        fn = _func(_tree(), 'initdStatus')
        lits = ' '.join(_str_literals(fn))
        self.assertIn('is-enabled', lits)
        self.assertNotIn('grep loaded', lits)
        self.assertNotIn('systemctl status', lits)
        self.assertIn('yf.execShellRc', _calls(fn))

    def test_29_initd_install_not_installed_is_fail(self):
        """未安装不得回 'ok'（面板会显示「开机启动 已开启」）。"""
        self.install(False)
        for fn in (self.mod.initdInstall, self.mod.initdUinstall):
            self.assertEqual(fn(), 'fail')
        self.assertEqual([c for c in self.systemctl_calls() if 'enable' in c
                          or 'disable' in c], [], '未安装不得调 systemctl enable/disable')

    def test_30_initd_install_rc_failure_is_not_ok(self):
        self.install(True)
        _ProcTable.sysctl = {'enable': (1, '', 'Failed to enable unit'),
                             'disable': (1, '', 'Failed to disable unit')}
        self.assertEqual(self.mod.initdInstall(), 'fail')
        self.assertEqual(self.mod.initdUinstall(), 'fail')

    def test_31_initd_install_success_is_ok(self):
        self.install(True)
        _ProcTable.sysctl = {'enable': (0, '', ''), 'disable': (0, '', '')}
        self.assertEqual(self.mod.initdInstall(), 'ok')
        self.assertEqual(self.mod.initdUinstall(), 'ok')

    def test_32_ops_error_when_not_installed(self):
        self.install(False)
        for name in ('start', 'stop', 'restart', 'reload'):
            self.assertEqual(getattr(self.mod, name)(), 'ERROR: varnish 未安装', name)
        self.assertEqual([c for c in self.systemctl_calls()
                          if c.split()[-1] == 'varnish'], [],
                         '未安装不得对 systemctl 发起启停')
        self.assertFalse(os.path.exists(os.path.join(self.server, 'varnish')))

    def test_33_ops_use_exit_code(self):
        """退出码非 0（即使 stderr 为空）必须回 fail，不得假成功。"""
        self.install(True)
        _ProcTable.sysctl = {'start': (1, '', ''), 'stop': (1, '', ''),
                             'restart': (1, '', ''), 'reload': (1, '', ''),
                             'daemon-reload': (0, '', '')}
        for name in ('start', 'stop', 'restart', 'reload'):
            self.assertEqual(getattr(self.mod, name)(), 'fail', name)
        _ProcTable.sysctl = dict((k, (0, '', '')) for k in
                                 ('start', 'stop', 'restart', 'reload', 'daemon-reload'))
        for name in ('start', 'stop', 'restart', 'reload'):
            self.assertEqual(getattr(self.mod, name)(), 'ok', name)

    def test_34_ops_use_list_argv_and_exit_code(self):
        fn = _func(_tree(), 'vaOp')
        self.assertIn('yf.execShellRc', _calls(fn))
        self.assertNotIn('yf.execShell', _calls(fn))


# ---------------------------------------------------------------------------
# 6. 结构：不得凭空造产物 / 不得拼 shell
# ---------------------------------------------------------------------------

class TestStructure(_Fixture):

    def test_35_no_artifact_fabrication(self):
        """模块不得写任何文件/建目录（旧缺陷是「未安装也伪造 unit/安装目录」）。"""
        calls = _calls(_tree())
        for bad in ('yf.writeFile', 'yf.makeDirs', 'os.makedirs', 'shutil.copyfile',
                    'shutil.copy', 'os.mkdir'):
            self.assertNotIn(bad, calls, '模块不得凭空造产物: ' + bad)

    def test_36_no_hardcoded_mdserver_web(self):
        src = _read(IDX)
        code = '\n'.join(ln for ln in src.splitlines() if not ln.strip().startswith('#'))
        self.assertNotIn('mdserver-web', code)


# ---------------------------------------------------------------------------
# 7. 前端
# ---------------------------------------------------------------------------

class TestFrontend(_Fixture):

    def test_37_ajax_calls_have_fail_handler(self):
        js = _strip_js_comments(_read(JS))
        self.assertIn('function vhEscape(', js)
        for name in ('varnishStatus', 'varnishPluginConfig'):
            body = _js_function(js, name)
            self.assertIsNotNone(body, name)
            self.assertIn('.fail(', body, name + ' 缺 .fail()（500/超时会让遮罩卡死）')
        self.assertEqual(js.count('.fail('), 3, '三处 ajax 都必须有 .fail()')

    def test_38_inner_status_guard(self):
        js = _strip_js_comments(_read(JS))
        status_body = _js_function(js, 'varnishStatus')
        self.assertIn('rdata.status === false', status_body,
                      'run_info 的业务错误信封必须显式提示')
        cfg_body = _js_function(js, 'varnishPluginConfig')
        self.assertIn('!data.status', cfg_body, '配置文件路径接口必须判内层/外层 status')
        self.assertIn("typeof data.data !== 'string'", cfg_body)

    def test_39_dynamic_values_escaped(self):
        js = _strip_js_comments(_read(JS))
        status_body = _js_function(js, 'varnishStatus')
        for expr in ('vhEscape(keyName)', 'vhEscape(val)', 'vhEscape(desc)',
                     'vhEscape(timestamp)', 'vhEscape(data.msg)', 'vhEscape(rdata.msg)'):
            self.assertIn(expr, status_body, expr)


# ---------------------------------------------------------------------------
# 8. 语言包 / 安装脚本
# ---------------------------------------------------------------------------

class TestLangAndInstall(_Fixture):

    def test_40_lang_keys_complete_and_aligned(self):
        packs = {}
        for lang in LANGS:
            p = os.path.join(LANGDIR, lang + '.json')
            self.assertTrue(os.path.isfile(p), p)
            packs[lang] = json.loads(_read(p))
        base = set(packs['zh-CN'])
        for lang in LANGS:
            self.assertEqual(set(packs[lang]), base, '语言包键集合不一致: ' + lang)
        for key in NEW_MSG_KEYS + NEW_JS_KEYS:
            for lang in LANGS:
                self.assertTrue(packs[lang].get(key), '%s 缺键/空译文: %s' % (lang, key))
                if lang not in ('zh-CN', 'zh-TW'):
                    self.assertFalse(CJK_RE.search(packs[lang][key]),
                                     '%s 译文仍是中文: %s' % (lang, key))

    def test_41_backend_messages_resolvable(self):
        """index.py 里 returnJson/stderr 的中文消息必须能在 zh-CN 查到键。"""
        keys = set(json.loads(_read(os.path.join(LANGDIR, 'zh-CN.json'))))
        src = _read(IDX)
        bad = []
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else ''
            idx = 1 if name == 'returnJson' else (0 if name == 'write' else None)
            if idx is None or len(node.args) <= idx:
                continue
            lit = _str_lit(node.args[idx])
            if not lit or not CJK_RE.search(lit):
                continue
            key = lit.strip()
            if key in keys:
                continue
            ci = key.find(':')
            if 0 < ci <= 40 and (key[:ci + 1] in keys or (key[:ci + 1] + ' ') in keys):
                continue
            bad.append(lit)
        self.assertEqual(bad, [], '语言包查不到键: %r' % (bad,))

    def test_42_install_sh_checks_results(self):
        sh = _read(INSTALL_SH)
        self.assertIn('/usr/sbin/varnishd', sh)
        self.assertIn('未找到 varnishd', sh)
        self.assertIn("!= 'ok'", sh)
        self.assertIn('exit 1', sh)


if __name__ == '__main__':
    unittest.main(verbosity=2)
