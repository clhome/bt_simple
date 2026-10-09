# coding: utf-8
r"""D05 supervisor 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/supervisor/`（真机 Debian 12 上 **未安装**：无 `/www/server/supervisor`、
无 systemd unit、`systemctl is-active supervisor` = inactive；注意面板 venv 里虽有
`bin/supervisord`/`bin/supervisorctl`（pip 脚本），但面板按 info.json 的 `checks/path`
（`server/supervisor`）判定为「未安装」——这正是假成功的温床）。

真机实测（修复前 HEAD，证据见 `test/_d05_probe_before*.sh` 输出）：
  * **`status()` 假阳性**：`ps -ef|grep supervisor|grep -v grep|grep -v index.py` 把
    命令行里含 supervisor 字样的**无关 python 进程**（探针
    `/tmp/yf_probe_D05/supervisor_watchdog.py`）当成 supervisord → 未安装也回 `start`。
  * **未安装路径伪造产物 / 假成功**：`/www/server/supervisor` 存在时 `start` 会写出
    `conf.d/` + `supervisor.conf` + `/lib/systemd/system/supervisor.service`
    （ExecStart 指向未安装的 supervisord），随后 `systemctl start` 失败但结果被吞；
    目录不存在时 `start/stop/restart/reload` 直接 `FileNotFoundError` traceback；
    `initd_install` 无条件回 `ok`（真机 `systemctl enable` 实际失败）→ `initd_status` 回 `ok`。
  * **配置注入**：`add_job numprocs='1\nuser=nobody'` 真的写出第二行 `user=nobody`
    （`command` 里的 `\n` 同理），`update_job` 亦可注入。
  * **崩溃**：未安装时 `config_tpl`/`confd_list` 直接 FileNotFoundError；
    `confd_list_trace_log` 在 `readFile` 回 False 时 TypeError；
    `read_config_log_tpl` 缺 `line` 参数 KeyError；`line='abc'` ValueError。
  * **`update_job` 命令截断**：`split('=')[1]` 把带 `=` 的 command 截断（改一次配置就丢命令）。
  * **前端**：6 个裸 `$.post` 全无 `.fail()`（失败时 time:0 遮罩永久卡死）；
    动态值（进程名/命令/用户/配置路径）直接拼 HTML 与行内 `onclick`。

断言策略：不装 supervisor（禁止新增依赖），全部在**临时目录夹具**上真跑插件函数；
「已安装」路径用夹具 + 伪 `findSupBin`（等价于 venv 里有 pip 脚本的真实场景）。
结构类断言用 `ast`（抗「注释 / `if False:` 蒙混」），前端断言先去注释。
"""
import ast
import contextlib
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
PLUGIN_SRC = os.environ.get('YF_D05_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'supervisor')
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)

IDX = os.path.join(PLUGIN_SRC, 'index.py')
JS = os.path.join(PLUGIN_SRC, 'js', 'supervisor.js')
LANGDIR = os.path.join(PLUGIN_SRC, 'lang')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']

NOT_INSTALLED_MSG = 'supervisor 未安装!'
NEW_MSG_KEYS = [
    'supervisor 未安装!', 'supervisor 操作失败!', '写入配置失败!', '参数格式错误!',
    '启动用户不存在!', '日志路径不合法!', '进程数量不合法!', '配置文件不存在!',
    '配置内容不合法!', '优先级参数不合法!', '请求失败',
]
CJK_RE = re.compile(r'[\u4e00-\u9fff]')
POSIX = os.path.exists('/proc/self/comm')


def _read_src(path):
    with open(path, 'r', encoding='utf-8') as fp:
        return fp.read()


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


class _Fixture(object):
    """把插件目录/服务目录/systemd 目录全指到临时目录，真跑插件函数（不碰 /www、不装依赖）。"""

    def __init__(self, installed=True, server_exists=None):
        self.root = tempfile.mkdtemp(prefix='d05_fx_')
        self.server = os.path.join(self.root, 'server', 'supervisor')
        self.plugin = os.path.join(self.root, 'plugin')
        self.systemd = os.path.join(self.root, 'systemd')
        self.shells = []
        self.installed = installed
        self._build()
        if server_exists is None:
            server_exists = installed
        if server_exists:
            os.makedirs(os.path.join(self.server, 'conf.d'), exist_ok=True)
            for sub in ('log', 'run'):
                os.makedirs(os.path.join(self.server, sub), exist_ok=True)
        # 只读资源（conf 模板 / init.d unit 模板）
        for rel in ('conf', 'init.d', 'lang'):
            src = os.path.join(PLUGIN_SRC, rel)
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(self.plugin, rel))
        self.mod = self._load()

    def _build(self):
        os.makedirs(self.plugin, exist_ok=True)
        os.makedirs(self.systemd, exist_ok=True)

    def _load(self):
        import core.yf  # noqa: F401
        cwd = os.getcwd()
        spec = importlib.util.spec_from_file_location('d05_supervisor_mod', IDX)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        finally:
            os.chdir(cwd)
        self.yf = sys.modules['core.yf']
        # 模块自有的路径函数（不是 yf.*）必须逐个替换
        mod.getServerDir = lambda *a, **k: self.server
        mod.getPluginDir = lambda *a, **k: self.plugin
        mod.getUserListData = lambda *a, **k: ['root', 'www']
        mod.findSupBin = self._find_bin
        self._patch(self.yf, 'getServerDir', lambda *a, **k: os.path.dirname(self.server))
        self._patch(self.yf, 'getPanelDir', lambda *a, **k: os.path.join(self.root, 'panel'))
        self._patch(self.yf, 'getPluginDir', lambda *a, **k: self.plugin)
        self._patch(self.yf, 'systemdCfgDir', lambda *a, **k: self.systemd)
        self._patch(self.yf, 'isAppleSystem', lambda *a, **k: False)
        self._patch(self.yf, 'shlexQuote', lambda s: '"%s"' % s)
        self._patch(self.yf, 'writeLog', lambda *a, **k: None)
        self._patch(self.yf, 'execShell', self._shell)
        self._patch(self.yf, 'execShellRc', self._shell_rc)
        return mod

    def _patch(self, obj, name, value):
        old = getattr(obj, name, None)
        setattr(obj, name, value)
        self.patched = getattr(self, 'patched', [])
        self.patched.append((obj, name, old))

    def _find_bin(self, name):
        return '/fixture/bin/' + name if self.installed else ''

    def _shell(self, cmd, **kw):
        self.shells.append((cmd, kw))
        return ('', '')

    def _shell_rc(self, cmd, **kw):
        self.shells.append((cmd, kw))
        return (0, '', '')

    def close(self):
        for obj, name, old in getattr(self, 'patched', []):
            setattr(obj, name, old)
        self.patched = []
        shutil.rmtree(self.root, ignore_errors=True)

    # -- 夹具辅助
    def pid_file(self):
        return os.path.join(self.server, 'run', 'supervisor.pid')

    def write_pidfile(self, content):
        os.makedirs(os.path.dirname(self.pid_file()), exist_ok=True)
        with open(self.pid_file(), 'w', encoding='utf-8') as fp:
            fp.write(content)

    def write_conf(self, name, body):
        os.makedirs(os.path.join(self.server, 'conf.d'), exist_ok=True)
        path = os.path.join(self.server, 'conf.d', name)
        with open(path, 'w', encoding='utf-8') as fp:
            fp.write(body)
        return path

    def conf_path(self, name):
        return os.path.join(self.server, 'conf.d', name)

    def server_snapshot(self):
        found = []
        for base, dirs, files in os.walk(self.root):
            if os.path.abspath(base) == os.path.abspath(self.plugin):
                dirs[:] = []
                continue
            for f in files:
                found.append(os.path.relpath(os.path.join(base, f), self.root))
        return sorted(found)


def _json(out):
    return json.loads(out)


class TestD05Backend(unittest.TestCase):

    def setUp(self):
        self.fx = _Fixture(installed=True)
        self.addCleanup(self.fx.close)

    @contextlib.contextmanager
    def _stderr(self):
        """插件失败原因必须写 stderr（面板 /plugins/run 以 stderr 判定失败）。"""
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            yield buf

    # ---------------------------------------------------------------- 未安装路径
    def test_01_not_installed_status_never_reports_start(self):
        fx = _Fixture(installed=False, server_exists=False)
        self.addCleanup(fx.close)
        self.assertEqual(fx.mod.status(), 'stop')
        # status() 必须零 shell 调用（旧实现每次轮询 fork 3 个 ps/grep/awk 进程）
        self.assertEqual(fx.shells, [])

    def test_02_not_installed_ops_report_error_and_write_nothing(self):
        fx = _Fixture(installed=False, server_exists=False)
        self.addCleanup(fx.close)
        before = fx.server_snapshot()
        with self._stderr() as err:
            for func in ('start', 'stop', 'restart', 'reload'):
                self.assertEqual(getattr(fx.mod, func)(), 'fail', func)
            for func in ('initdInstall', 'initdUinstall', 'initdStatus'):
                self.assertEqual(getattr(fx.mod, func)(), 'fail', func)
        # 失败原因写 stderr：面板 /plugins/run 只以 stderr 判定插件失败
        self.assertIn('supervisor 未安装!', err.getvalue())
        # 零 systemctl 调用 = 未安装时不假装启停/假装设置开机启动
        self.assertEqual([c for c, _ in fx.shells if 'systemctl' in str(c)], [])
        # 零产物：不建 conf.d / 主配置 / systemd unit
        self.assertFalse(os.path.exists(os.path.join(fx.server, 'supervisor.conf')))
        self.assertEqual(fx.server_snapshot(), before)
        self.assertEqual(os.listdir(fx.systemd), [])

    def test_03_not_installed_install_path_creates_no_artifacts(self):
        """`server/supervisor` 缺失（真机现状）+ venv 里恰好有 pip 脚本时仍算未安装。"""
        fx = _Fixture(installed=True, server_exists=False)  # findSupBin 找得到，但安装目录缺失
        self.addCleanup(fx.close)
        self.assertEqual(fx.mod.status(), 'stop')
        with self._stderr() as err:
            self.assertEqual(fx.mod.start(), 'fail')
        self.assertIn('supervisor 未安装!', err.getvalue())
        self.assertFalse(fx.mod.isInstalled())
        self.assertFalse(os.path.exists(os.path.join(fx.server, 'supervisor.conf')))
        self.assertEqual(os.listdir(fx.systemd), [])

    def test_04_not_installed_mutating_entrypoints_refuse(self):
        fx = _Fixture(installed=False, server_exists=False)
        self.addCleanup(fx.close)
        cases = [
            ('addJob', '{"name":"a","user":"root","path":"/tmp","command":"/bin/sleep 1","numprocs":"1"}'),
            ('startJob', '{"name":"a","status":"start"}'),
            ('restartJob', '{"name":"a","status":"stop"}'),
            ('delJob', '{"name":"a"}'),
            ('updateJob', '{"name":"a","user":"root","numprocs":"1","priority":"999"}'),
        ]
        for func, args in cases:
            fx.mod.sys.argv = ['index.py', func, args]
            try:
                out = _json(getattr(fx.mod, func)())
            finally:
                keep = fx.mod.sys.argv
            self.assertFalse(out['status'], func)
            self.assertIn('未安装', out['msg'], func)
            fx.mod.sys.argv = keep
        self.assertEqual(fx.server_snapshot(), [])

    def test_05_status_uses_pidfile_not_ps_grep(self):
        tree = ast.parse(_read_src(IDX))
        fn = _func(tree, 'status')
        self.assertIsNotNone(fn)
        calls = _calls(fn)
        self.assertNotIn('execShell', calls)
        self.assertNotIn('execShellRc', calls)
        self.assertIn('getSupervisordPid', calls)
        # 全模块不得再把 ps|grep supervisor 当判据（按字符串字面量判定，注释/文档不算）
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                        and isinstance(first.value.value, str):
                    docstrings.add(id(first.value))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in docstrings:
                self.assertNotIn('ps -ef', node.value, node.value)
                self.assertNotIn('grep -v index.py', node.value, node.value)

    def test_06_stale_or_foreign_pid_is_not_start(self):
        # pid 文件指向任意存活进程（含命令行带 supervisor 字样的探针）时必须 stop
        self.fx.write_pidfile(str(os.getpid()))
        self.assertEqual(self.fx.mod.status(), 'stop')
        # pid 文件内容非数字
        self.fx.write_pidfile('not-a-pid')
        self.assertEqual(self.fx.mod.status(), 'stop')
        # pid 文件不存在
        os.remove(self.fx.pid_file())
        self.assertEqual(self.fx.mod.status(), 'stop')
        # 只有「pid 文件 + /proc 确认是 supervisord」才 start
        self.fx.mod._pidIsSupervisord = lambda pid: True
        self.fx.write_pidfile('4242')
        self.assertEqual(self.fx.mod.status(), 'start')

    @unittest.skipUnless(POSIX, '需要 /proc')
    def test_07_pid_is_supervisord_precise(self):
        """真进程验证：名字不是 supervisord 的 python 进程不算；脚本名恰为 supervisord 才算。"""
        script_dir = os.path.join(self.fx.root, 'bin')
        os.makedirs(script_dir, exist_ok=True)
        sv = os.path.join(script_dir, 'supervisord')
        with open(sv, 'w', encoding='utf-8') as fp:
            fp.write('import time\ntime.sleep(60)\n')
        decoy = os.path.join(script_dir, 'supervisor_watchdog.py')
        with open(decoy, 'w', encoding='utf-8') as fp:
            fp.write('import time\ntime.sleep(60)\n')
        procs = [subprocess.Popen([sys.executable, p]) for p in (sv, decoy)]
        self.addCleanup(lambda: [p.kill() for p in procs])
        import time as _t
        _t.sleep(1.5)
        self.assertTrue(self.fx.mod._pidIsSupervisord(procs[0].pid))
        self.assertFalse(self.fx.mod._pidIsSupervisord(procs[1].pid))
        self.assertFalse(self.fx.mod._pidIsSupervisord('999999'))

    # ---------------------------------------------------------------- 配置注入
    def _add_job(self, payload):
        self.fx.mod.sys.argv = ['index.py', 'add_job', json.dumps(payload)]
        return _json(self.fx.mod.addJob())

    def test_08_add_job_rejects_newline_injection(self):
        base = {'name': 'job1', 'user': 'root', 'path': '/tmp', 'command': '/bin/sleep 1',
                'numprocs': '1'}
        bad = [
            (dict(base, name='a\n[program:evil]'), '进程名称'),
            (dict(base, command='x\nautostart=true'), '配置内容不合法!'),
            (dict(base, path='/tmp\ndirectory=/etc'), '配置内容不合法!'),
            (dict(base, user='root\nuser=daemon'), '配置内容不合法!'),
            (dict(base, numprocs='1\nuser=nobody'), '进程数量不合法!'),
            (dict(base, numprocs='0'), '进程数量不合法!'),
            (dict(base, numprocs='abc'), '进程数量不合法!'),
            (dict(base, user='nosuchuser_x'), '启动用户不存在!'),
        ]
        for payload, expect in bad:
            out = self._add_job(payload)
            self.assertFalse(out['status'], payload)
            self.assertIn(expect, out['msg'], payload)
            self.assertFalse(os.path.exists(self.fx.conf_path('job1.ini')), payload)
        self.assertEqual(os.listdir(os.path.join(self.fx.server, 'conf.d')), [])

    def test_09_add_job_ok_and_idempotent(self):
        payload = {'name': 'job1', 'user': 'root', 'path': '/tmp',
                   'command': 'env A=1 /bin/sleep 1', 'numprocs': '2'}
        out = self._add_job(payload)
        self.assertTrue(out['status'], out)
        body = _read_src(self.fx.conf_path('job1.ini'))
        self.assertEqual(body.count('[program:job1]'), 1)
        self.assertIn('command=env A=1 /bin/sleep 1\n', body)
        self.assertIn('numprocs=2\n', body)
        self._add_job(payload)
        self.assertEqual(_read_src(self.fx.conf_path('job1.ini')), body)

    def test_10_update_job_keeps_command_with_equals_and_validates(self):
        self.fx.write_conf('job1.ini',
                        '[program:job1]\ncommand=env A=1 /bin/sleep 1\ndirectory=/tmp\n'
                        'user=root\npriority=999\nnumprocs=1\n')
        self.fx.mod.sys.argv = ['index.py', 'update_job',
                                json.dumps({'name': 'job1', 'user': 'root',
                                            'numprocs': '3', 'priority': '100'})]
        out = _json(self.fx.mod.updateJob())
        self.assertTrue(out['status'], out)
        body = _read_src(self.fx.conf_path('job1.ini'))
        self.assertIn('command=env A=1 /bin/sleep 1\n', body)
        self.assertIn('numprocs=3\n', body)
        self.assertIn('priority=100\n', body)

        for field, value, expect in (
                ('numprocs', '1\nuser=nobody', '进程数量不合法!'),
                ('priority', '999\nuser=nobody', '优先级参数不合法!'),
                ('priority', 'abc', '优先级参数不合法!'),
                ('user', 'root\nuser=daemon', '配置内容不合法!'),
        ):
            payload = {'name': 'job1', 'user': 'root', 'numprocs': '1', 'priority': '999'}
            payload[field] = value
            self.fx.mod.sys.argv = ['index.py', 'update_job', json.dumps(payload)]
            out = _json(self.fx.mod.updateJob())
            self.assertFalse(out['status'], (field, value))
            self.assertIn(expect, out['msg'], (field, value))

    # ---------------------------------------------------------------- 参数与崩溃
    def test_11_get_args_non_dict_payload(self):
        self.fx.mod.sys.argv = ['index.py', 'read_config_log_tpl', '[]']
        self.assertEqual(self.fx.mod.getArgs(), {})
        self.fx.mod.sys.argv = ['index.py', 'read_config_log_tpl', '123']
        self.assertEqual(self.fx.mod.getArgs(), {})
        self.fx.mod.sys.argv = ['index.py', 'add_job', 'name:a']
        self.assertEqual(self.fx.mod.getArgs(), {'name': 'a'})
        self.fx.mod.sys.argv = ['index.py', 'add_job', 'command:/bin/sh -c a:b']
        self.assertEqual(self.fx.mod.getArgs(), {'command': '/bin/sh -c a:b'})

    def test_12_missing_and_invalid_params_return_envelope(self):
        conf = self.fx.write_conf('job1.ini',
                               '[program:job1]\ncommand=/bin/sleep 1\ndirectory=/tmp\n')
        # 缺 line 参数 → 缺少必要参数（不是 KeyError）
        self.fx.mod.sys.argv = ['index.py', 'read_config_log_tpl', json.dumps({'file': conf})]
        out = _json(self.fx.mod.readConfigLogTpl())
        self.assertFalse(out['status'])
        self.assertIn('缺少必要参数', out['msg'])
        # line 非数字 → 参数格式错误（不是 ValueError 500）
        self.fx.mod.sys.argv = ['index.py', 'read_config_log_tpl',
                                json.dumps({'file': conf, 'line': 'abc'})]
        out = _json(self.fx.mod.readConfigLogTpl())
        self.assertFalse(out['status'])
        self.assertIn('参数格式错误!', out['msg'])
        # 不存在的配置文件 → 业务错误（不是 FileNotFoundError）
        missing = os.path.join(self.fx.server, 'conf.d', 'nope.ini')
        self.fx.mod.sys.argv = ['index.py', 'read_config_log_error_tpl',
                                json.dumps({'file': missing, 'line': '10'})]
        out = _json(self.fx.mod.readConfigLogErrorTpl())
        self.assertFalse(out['status'])
        self.assertIn('配置文件不存在!', out['msg'])

    def test_13_missing_files_do_not_raise(self):
        # 未安装（目录不存在）时的只读入口
        fx = _Fixture(installed=False, server_exists=False)
        self.addCleanup(fx.close)
        self.assertEqual(_json(fx.mod.configTpl()), [])
        self.assertEqual(_json(fx.mod.confDList())['data'], [])
        fx.mod.sys.argv = ['index.py', 'confd_list_trace_log', '{"name":"nope.ini"}']
        self.assertEqual(fx.mod.confDlistTraceLog(), '')
        fx.mod.sys.argv = ['index.py', 'confd_list_error_log', '{"name":"nope.ini"}']
        self.assertEqual(fx.mod.confDlistErrorLog(), '')
        # 已安装但目标文件不存在
        self.fx.mod.sys.argv = ['index.py', 'confd_list_trace_log', '{"name":"nope.ini"}']
        self.assertEqual(self.fx.mod.confDlistTraceLog(), '')
        self.fx.mod.sys.argv = ['index.py', 'read_config_tpl',
                                json.dumps({'file': self.fx.conf_path('nope.ini')})]
        out = _json(self.fx.mod.readConfigTpl())
        self.assertFalse(out['status'])
        self.assertIn('配置文件不存在!', out['msg'])
        self.fx.mod.sys.argv = ['index.py', 'get_job_info', '{"name":"nope"}']
        out = _json(self.fx.mod.getJobInfo())
        self.assertFalse(out['status'])
        self.assertIn('配置文件不存在!', out['msg'])

    def test_14_get_job_info_defaults_and_values(self):
        self.fx.write_conf('job1.ini',
                        '[program:job1]\ncommand=/bin/sleep 1\ndirectory=/tmp\n'
                        'user=root\nnumprocs=2\npriority=99\n')
        self.fx.mod.sys.argv = ['index.py', 'get_job_info', '{"name":"job1"}']
        out = _json(self.fx.mod.getJobInfo())
        self.assertEqual(out['daemoninfo']['user'], 'root')
        self.assertEqual(out['daemoninfo']['numprocs'], '2')
        self.assertEqual(out['daemoninfo']['priority'], '99')
        # 缺键时给默认值（前端弹窗直接回填，undefined 会显示成字符串）
        self.fx.write_conf('job2.ini', '[program:job2]\ncommand=/bin/sleep 1\ndirectory=/tmp\n')
        self.fx.mod.sys.argv = ['index.py', 'get_job_info', '{"name":"job2"}']
        out = _json(self.fx.mod.getJobInfo())
        self.assertEqual(out['daemoninfo']['numprocs'], '1')
        self.assertEqual(out['daemoninfo']['priority'], '999')

    # ---------------------------------------------------------------- 文件与删除
    def test_15_clear_log_sandbox(self):
        outside = os.path.join(self.fx.root, 'shadow')
        with open(outside, 'w', encoding='utf-8') as fp:
            fp.write('secret-data')
        conf = self.fx.write_conf('job1.ini',
                               '[program:job1]\ncommand=/bin/sleep 1\nstdout_logfile=' +
                               outside + '\n')
        self.fx.mod.sys.argv = ['index.py', 'sup_clear_log', json.dumps({'file': conf})]
        out = _json(self.fx.mod.supClearLog())
        self.assertFalse(out['status'])
        self.assertIn('日志路径不合法!', out['msg'])
        self.assertEqual(_read_src(outside), 'secret-data')

        inside = os.path.join(self.fx.server, 'log', 'job1.out.log')
        os.makedirs(os.path.dirname(inside), exist_ok=True)
        with open(inside, 'w', encoding='utf-8') as fp:
            fp.write('log-line\n')
        conf = self.fx.write_conf('job2.ini',
                               '[program:job2]\ncommand=/bin/sleep 1\nstdout_logfile=' +
                               inside + '\n')
        self.fx.mod.sys.argv = ['index.py', 'sup_clear_log', json.dumps({'file': conf})]
        out = _json(self.fx.mod.supClearLog())
        self.assertTrue(out['status'], out)
        self.assertEqual(_read_src(inside), '')

    def test_16_conf_paths_and_names_whitelist(self):
        fx = self.fx
        # 目录穿越 / 越界路径
        for bad in ('/etc/shadow', '/www/server/supervisor/conf.d/../../etc/passwd',
                    os.path.join(fx.root, 'x.ini')):
            self.assertFalse(fx.mod.checkSafeFile(bad), bad)
            self.assertFalse(fx.mod.checkSafeName('a\n[program:evil]'))
        self.assertTrue(fx.mod.checkSafeFile(fx.conf_path('a.ini')))

    # ---------------------------------------------------------------- 可靠性
    def test_17_supervisorctl_calls_have_timeout_and_quote(self):
        self.fx.write_conf('job1.ini',
                        '[program:job1]\ncommand=/bin/sleep 1\ndirectory=/tmp\n')
        self.fx.mod.sys.argv = ['index.py', 'start_job', '{"name":"job1","status":"stop"}']
        out = _json(self.fx.mod.startJob())
        self.assertTrue(out['status'], out)
        ctl = [c for c, kw in self.fx.shells if 'supervisorctl' in str(c)]
        self.assertTrue(ctl, self.fx.shells)
        for c, kw in self.fx.shells:
            if 'supervisorctl' in str(c):
                self.assertIn('timeout', kw, c)
                self.assertEqual(kw['timeout'], self.fx.mod.SUP_CTL_TIMEOUT)
                self.assertIn('"', str(c))  # 路径/进程名经 shlexQuote

    def test_18_supervisorctl_error_is_not_fake_success(self):
        self.fx.write_conf('job1.ini',
                        '[program:job1]\ncommand=/bin/sleep 1\ndirectory=/tmp\n')
        self.fx.mod.yf.execShellRc = lambda cmd, **kw: (
            0, 'job1: ERROR (no such process)', '')
        self.fx.mod.sys.argv = ['index.py', 'start_job', '{"name":"job1","status":"start"}']
        out = _json(self.fx.mod.startJob())
        self.assertFalse(out['status'], out)
        self.fx.mod.sys.argv = ['index.py', 'restart_job', '{"name":"job1","status":"start"}']
        out = _json(self.fx.mod.restartJob())
        self.assertFalse(out['status'], out)

    def test_19_write_failure_is_not_fake_success(self):
        self.fx.mod.yf.writeFile = lambda *a, **k: False
        out = self._add_job({'name': 'job1', 'user': 'root', 'path': '/tmp',
                             'command': '/bin/sleep 1', 'numprocs': '1'})
        self.assertFalse(out['status'], out)
        self.assertIn('写入配置失败!', out['msg'])

    def test_20_get_sup_list_no_shell_when_not_installed(self):
        fx = _Fixture(installed=False, server_exists=False)
        self.addCleanup(fx.close)
        self.assertEqual(_json(fx.mod.getSupList())['data'], [])
        self.assertEqual(fx.shells, [])
        self.assertEqual(fx.mod.status(), 'stop')

    def test_20b_get_sup_list_uses_timeout(self):
        self.assertEqual(_json(self.fx.mod.getSupList())['data'], [])
        self.assertTrue(self.fx.shells)
        for c, kw in self.fx.shells:
            self.assertIn('timeout', kw, c)


class TestD05Frontend(unittest.TestCase):

    def setUp(self):
        self.src = _strip_js_comments(_read_src(JS))

    def test_21_every_raw_post_has_fail_handler(self):
        posts = re.findall(r'\$\.post\(', self.src)
        fails = re.findall(r'\.fail\(', self.src)
        self.assertGreaterEqual(len(posts), 6, 'expected the 6 raw $.post calls')
        self.assertGreaterEqual(len(fails), len(posts),
                                '每个裸 $.post 都要有 .fail()（否则 time:0 遮罩永久卡死）')
        # 遮罩变量必须在 fail 里被关闭
        self.assertIn('layer.close(loadT);', self.src)

    def test_22_dynamic_values_are_escaped(self):
        self.assertIn('function supEsc(', self.src)
        self.assertIn('function supJsArg(', self.src)
        self.assertNotIn("onclick=\"startOrStop(\\''", self.src)
        self.assertNotIn("onclick=\"delJob(\\''", self.src)
        self.assertNotIn("onclick=\"updateJob(\\''", self.src)
        self.assertIn('supJsArg(rdata.data[i][\'program\'])', self.src)
        self.assertIn('supEsc(rdata.data[i][\'command\'])', self.src)
        self.assertIn('supEsc(rdata.data[i][\'name\'])', self.src)
        self.assertIn('supJsArg(rdata.data[i][\'name\'])', self.src)

    def test_23_lang_files_aligned_and_new_keys_present(self):
        keys = None
        for lg in LANGS:
            data = json.loads(_read_src(os.path.join(LANGDIR, lg + '.json')))
            self.assertEqual(set(data), set(keys) if keys else set(data), lg)
            keys = set(data)
            for k in NEW_MSG_KEYS:
                self.assertIn(k, data, '%s missing %s' % (lg, k))
                self.assertTrue(str(data[k]).strip(), '%s: empty translation for %s' % (lg, k))
            if lg in ('de', 'fr', 'it', 'en'):
                for k in NEW_MSG_KEYS:
                    self.assertFalse(CJK_RE.search(data[k]),
                                     '%s should not contain Chinese: %s' % (lg, k))


if __name__ == '__main__':
    unittest.main()
