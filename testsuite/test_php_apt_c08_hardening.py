# coding: utf-8
r"""C08 php-apt 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/php-apt/`（65 函数 + `versions/` + `plugin_version.pl`）。真机是 Debian 12，
apt 是真实包管理器 → **严禁** `apt install/remove` 生产 php 包；本模块全部在**临时目录夹具**
上真跑插件函数（不碰 /etc/php、不碰生产 php80/81/83）。

真机实测（探针 `test/_c08_probe_inject.sh`，安全载荷只写 /tmp）暴露的缺陷：
  * **版本号是唯一用户可控「路径/命令片段」入口，且 `formatVersion()` 是「假规范化」**：
    `formatVersion('8.3; echo PWNED; #')` 因含 `.` 原样返回 → 真机 `status` / `get_lib_conf` /
    `initd_status` 三处都把注入值拼进 shell 并**真的执行**（探针 `INJECTED_*: YES`）；
    `conf`（getConf）更以 root 真建出 `/tmp/yf_probe_c08_trav/fpm/php.ini`（`TRAVERSAL: FILE_CREATED`）。
    → new：新增 `^\d+\.\d+$` 白名单（与磁盘目录过滤同口径）+ `isPhpVersion/versionOrError/
    versionOrFail`，在 CLI 统一收口 + 各 path/shell sink 二次校验。
  * **`getArgs` 只认 dict 前的 json.loads 结果**：`args='[]'`（合法 JSON 非对象）会得到 list →
    `args['version']` TypeError；`set_session_conf '{}'` → `args['ip']` KeyError 真机 traceback。
    → new：非 dict 一律回 {} / `参数格式错误!`。
  * **`set_max_time time='abc'`** 真机 traceback（`int('abc')` ValueError）→ new 回业务错误信封。
  * **php.ini 指令注入**：`submit_php_conf date.timezone='PRC\nINVALID_DIRECTIVE=1'`、
    `set_disable_func 'exec\nINVALID'`、`set_fpm_conf max_children='30\n...'`、`set_session_conf
    save_handler='evil'` 全部可注入任意配置行 → new 全部白名单拒绝。
  * **陈旧 pid 文件假阳性**：`os.kill(pid,0)` 指向任意存活进程即报 start → new 用
    `/proc/<pid>/comm == php-fpm` + 本版本目录精确判定（C07 同族）。
  * **`rm`/`find` 拼接**：`rm -f {sock_file}` 未引用、`find /tmp |grep sess_|xargs rm -f`
    无 `-print0`/`-r`（C07 已修 php，php-apt 漏改）→ new 走 `yf.shlexQuote` + `xargs -0 -r`。
  * **`install_lib`/`uninstall_lib`** 的 `version` 未校验即拼进 `common.sh` 调用
    （uninstall 当场 execShell、install 入队后台任务）→ new 版本白名单 + `yf.shlexQuote`，
    并在 `versions/common.sh` 侧再加同口径正则兜底。

断言策略：能真跑的一律真跑（临时目录夹具 + 记录型 shell）；结构类断言用 `ast`（抗「注释 /
`if False:` 蒙混」），前端用去注释后的源码断言（抗「JS 注释蒙混」）。
"""
import ast
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_SRC = os.environ.get('YF_C08_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'php-apt')
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)

IDX = os.path.join(PLUGIN_SRC, 'index.py')
JS = os.path.join(PLUGIN_SRC, 'js', 'php.js')
COMMON_SH = os.path.join(PLUGIN_SRC, 'versions', 'common.sh')
LANGDIR = os.path.join(PLUGIN_SRC, 'lang')

LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
NEW_MSG_KEYS = ['PHP版本参数不合法!', '参数格式错误!', '参数值不合法!',
                'Session存储方式不合法!', '禁用函数格式不合法!', '并发参数不合法!',
                '运行模式不合法!', '时间参数不合法!', '上传大小参数不合法!',
                '扩展列表配置文件不存在!', '扩展列表配置文件格式错误!']
CJK_RE = re.compile(r'[\u3400-\u9fff]')

VERSION = '8.3'
NOT_INSTALLED = '9.9'
BAD_VERSION = '8.3; echo PWNED > /tmp/yf_c08_pwn; #'

PHPINI = """[PHP]
engine = On
short_open_tag = On
asp_tags = Off
max_execution_time = 300
max_input_time = 60
max_input_vars = 1000
memory_limit = 128M
post_max_size = 50M
file_uploads = On
upload_max_filesize = 50M
max_file_uploads = 20
default_socket_timeout = 60
error_reporting = E_ALL & ~E_NOTICE
display_errors = Off
cgi.fix_pathinfo = 1
;date.timezone = PRC
session.save_handler = files
session.save_path = "/var/lib/php/sessions"
disable_functions = passthru,exec
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


def _calls(node):
    return [_call_name(n) for n in ast.walk(node) if isinstance(n, ast.Call)]


def _calls_any(node, names):
    calls = _calls(node)
    for name in names:
        for c in calls:
            if c == name or c.endswith('.' + name):
                return True
    return False


def _code_only(node):
    """返回函数体源码（不含 docstring）——避免把注释/文档里的旧写法当成缺陷。"""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return '\n'.join(ast.dump(b) for b in body)


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
    """把 `getServerDir()` / `getPluginDir()` 指到临时目录，真跑插件函数（不碰生产）。"""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix='c08_fx_')
        self.server = os.path.join(self.root, 'etc_php')
        self.plugin = os.path.join(self.root, 'php-apt')
        self.father = os.path.join(self.root, 'father')
        self.shells = []
        self.tasks = []
        self._build()
        self.mod = self._load()

    def _build(self):
        _write(os.path.join(self.server, VERSION, 'fpm', 'php.ini'), PHPINI)
        _write(os.path.join(self.server, VERSION, 'fpm', 'php-fpm.conf'),
               '[global]\npid = /run/php/php%s-fpm.pid\ninclude=/etc/php/%s/fpm/pool.d/*.conf\n'
               % (VERSION, VERSION))
        _write(os.path.join(self.server, VERSION, 'fpm', 'pool.d', 'yf.conf'),
               '[yf]\nlisten = /run/php/php%s-fpm.sock\npm = dynamic\npm.max_children = 30\n'
               'pm.start_servers = 5\npm.min_spare_servers = 5\npm.max_spare_servers = 20\n'
               'request_terminate_timeout = 30\n' % VERSION)
        os.makedirs(os.path.join(self.server, NOT_INSTALLED), exist_ok=True)
        os.makedirs(self.father, exist_ok=True)
        # 插件只读资源（conf 模板 / 扩展清单 / info.json）
        for rel in ('conf', 'versions'):
            src = os.path.join(PLUGIN_SRC, rel)
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(self.plugin, rel))
        shutil.copyfile(os.path.join(PLUGIN_SRC, 'info.json'),
                        os.path.join(self.plugin, 'info.json'))

    def _load(self):
        import core.yf  # noqa: F401
        cwd = os.getcwd()
        spec = importlib.util.spec_from_file_location('c08_php_apt_mod', IDX)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        finally:
            os.chdir(cwd)
        self.yf = sys.modules['core.yf']
        self._saved = {}
        # 模块内 getServerDir/getPluginDir 是自有的（非 yf.*），必须直接替换
        mod.getServerDir = lambda *a, **k: self.server
        mod.getPluginDir = lambda *a, **k: self.plugin
        mod.getPluginVersionFile = lambda *a, **k: os.path.join(self.root, 'plugin_version.pl')
        mod.ensureSystemdOverride = lambda *a, **k: None
        self._patch(self.yf, 'getServerDir', lambda *a, **k: self.server)
        self._patch(self.yf, 'getPluginDir', lambda *a, **k: self.root)
        self._patch(self.yf, 'getFatherDir', lambda *a, **k: self.father)
        self._patch(self.yf, 'getLocalIp', lambda *a, **k: '127.0.0.1')
        self._patch(self.yf, 'getSslCrt', lambda *a, **k: '')
        self._patch(self.yf, 'makeDirs', self._make_dirs)
        self._patch(self.yf, 'writeLog', lambda *a, **k: None)
        self._patch(self.yf, 'triggerTask', lambda *a, **k: None)
        self._patch(self.yf, 'execShell', self._exec_shell)
        self._patch_thisdb()
        return mod

    def _patch(self, obj, name, value):
        if name not in self._saved:
            self._saved[name] = getattr(obj, name)
        setattr(obj, name, value)

    def _patch_thisdb(self):
        class _Tasks(object):
            @staticmethod
            def addTask(name=None, cmd=None, type='execshell', status=0):
                self.tasks.append({'name': name, 'cmd': cmd})
                return True

        self._saved_thisdb = sys.modules.get('thisdb')
        sys.modules['thisdb'] = _Tasks

    def _exec_shell(self, cmd, cwd=None, timeout=None, shell=True):
        self.shells.append(cmd)
        return ('', '')

    def _make_dirs(self, path):
        # 只允许在夹具临时目录内建目录，避免测试机被写出 C:\run\php 之类的系统路径
        try:
            if str(path).startswith(self.root):
                os.makedirs(path, exist_ok=True)
        except Exception:
            pass
        return True

    def close(self):
        for name, value in self._saved.items():
            setattr(self.yf, name, value)
        if self._saved_thisdb is None:
            sys.modules.pop('thisdb', None)
        else:
            sys.modules['thisdb'] = self._saved_thisdb
        shutil.rmtree(self.root, ignore_errors=True)

    def read(self, rel):
        path = os.path.join(self.server, rel)
        return _read(path) if os.path.exists(path) else ''

    def set_args(self, version, obj):
        sys.argv = [IDX, 'func', version, json.dumps(obj)]

    def envelope(self, raw):
        data = json.loads(raw)
        assert isinstance(data, dict)
        return data


class _FixtureCase(unittest.TestCase):
    fixture = None

    @classmethod
    def setUpClass(cls):
        cls.fixture = _Fixture()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.close()

    def setUp(self):
        self.fx = self.fixture
        self.fx.shells[:] = []
        self.fx.tasks[:] = []

    def assertRejected(self, raw):
        data = self.fx.envelope(raw)
        self.assertFalse(data['status'])
        return data


# ---------------------------------------------------------------------------
# 版本白名单 + 路径穿越 / 注入
# ---------------------------------------------------------------------------

class TestVersionGuards(_FixtureCase):

    def test_01_version_whitelist(self):
        m = self.fx.mod
        for good in ('8.3', '7.4', '5.6', ' 8.3 ', '8.3\n'):
            self.assertTrue(m.isPhpVersion(good), good)
        for bad in ('', '8', '80', None, '../../etc', '8.3;id', 'a8.3',
                    '8.3.1', 'x', '8.3 4', '8..3'):
            self.assertFalse(m.isPhpVersion(bad), bad)

    def test_02_version_or_error_envelope(self):
        m = self.fx.mod
        err, ver = m.versionOrError('8.3')
        self.assertIsNone(err)
        self.assertEqual(ver, '8.3')
        err, ver = m.versionOrError('../../etc')
        self.assertIsNotNone(err)
        self.assertIsNone(ver)
        self.assertFalse(json.loads(err)['status'])
        self.assertIn('PHP版本参数不合法!', json.loads(err)['msg'])

    def test_03_status_rejects_injection(self):
        self.assertEqual(self.fx.mod.status(BAD_VERSION), 'ERROR: PHP版本参数不合法')
        self.assertEqual(self.fx.shells, [])

    def test_04_conf_traversal_creates_nothing(self):
        target = os.path.join(self.fx.root, 'evil')
        ver = os.path.relpath(target, self.fx.server)
        self.assertEqual(self.fx.mod.getConf(ver), '')
        self.assertFalse(os.path.exists(os.path.join(target, 'fpm', 'php.ini')))

    def test_05_get_lib_conf_rejects(self):
        self.assertRejected(self.fx.mod.getLibConf(BAD_VERSION))
        self.assertEqual(self.fx.shells, [])

    def test_06_initd_rejects(self):
        m = self.fx.mod
        for fn in ('initdStatus', 'initdInstall', 'initdUinstall'):
            out = getattr(m, fn)(BAD_VERSION)
            self.assertEqual(out, 'ERROR: PHP版本参数不合法', fn)
        self.assertEqual(self.fx.shells, [])

    def test_07_install_uninstall_lib_rejects(self):
        m = self.fx.mod
        self.fx.set_args(BAD_VERSION, {'name': 'redis'})
        self.assertRejected(m.installLib(BAD_VERSION))
        self.assertRejected(m.uninstallLib(BAD_VERSION))
        self.assertEqual(self.fx.tasks, [])
        self.assertEqual(self.fx.shells, [])

    def test_08_json_entrypoints_reject_bad_version(self):
        m = self.fx.mod
        self.fx.set_args(BAD_VERSION, {'time': '60'})
        for fn, args in (
            ('setMaxTime', (BAD_VERSION,)),
            ('setMaxSize', (BAD_VERSION,)),
            ('setFpmConfig', (BAD_VERSION,)),
            ('submitPhpConf', (BAD_VERSION,)),
            ('resetPhpConf', (BAD_VERSION,)),
            ('setDisableFunc', (BAD_VERSION,)),
            ('getDisableFunc', (BAD_VERSION,)),
            ('getFpmConfig', (BAD_VERSION,)),
            ('getFpmStatus', (BAD_VERSION,)),
            ('getPhpConf', (BAD_VERSION,)),
            ('getLimitConf', (BAD_VERSION,)),
            ('getSessionConf', (BAD_VERSION,)),
            ('getSessionCount', (BAD_VERSION,)),
            ('cleanSessionOld', (BAD_VERSION,)),
            ('tunePhpConfig', (BAD_VERSION,)),
        ):
            data = self.assertRejected(getattr(m, fn)(*args))
            self.assertIn('PHP版本参数不合法!', data['msg'], fn)
        self.assertEqual(self.fx.shells, [])

    def test_09_phpinfo_rejects(self):
        self.assertEqual(self.fx.mod.getPhpinfo(BAD_VERSION), 'ERROR: PHP版本参数不合法')

    def test_10_upgrade_and_check_reject(self):
        m = self.fx.mod
        self.assertRejected(m.upgradeSelfHealing(BAD_VERSION))
        self.assertRejected(m.checkPluginUpgrade(BAD_VERSION))

    def test_11_pid_master_check(self):
        m = self.fx.mod
        # 当前进程 comm 不是 php-fpm → 必须 False（防陈旧 pid 指向无关存活进程误报 start）
        self.assertFalse(m._pidIsPhpFpmMaster(os.getpid(), VERSION))


# ---------------------------------------------------------------------------
# getArgs / checkArgs 健壮性
# ---------------------------------------------------------------------------

class TestArgsRobustness(_FixtureCase):

    def _args(self, *argv):
        sys.argv = [IDX, 'func', 'V'] + list(argv)
        return self.fx.mod.getArgs()

    def test_20_non_dict_json_returns_empty(self):
        self.assertEqual(self._args('[]'), {})
        self.assertEqual(self._args('123'), {})
        self.assertEqual(self._args('"abc"'), {})

    def test_21_dict_json_and_kv(self):
        self.assertEqual(self._args('{"x": "1", "y": "2"}'), {'x': '1', 'y': '2'})
        self.assertEqual(self._args('x:1'), {'x': '1'})
        self.assertEqual(self._args('x:1', 'y:2'), {'x': '1', 'y': '2'})

    def test_22_malformed_returns_empty(self):
        self.assertEqual(self._args('{'), {})
        self.assertEqual(self._args(''), {})

    def test_23_check_args_non_dict(self):
        ok, msg = self.fx.mod.checkArgs([], ['time'])
        self.assertFalse(ok)
        self.assertIn('参数格式错误!', json.loads(msg)['msg'])

    def test_24_set_max_time_non_numeric(self):
        self.fx.set_args(VERSION, {'time': 'abc'})
        self.assertRejected(self.fx.mod.setMaxTime(VERSION))

    def test_25_set_session_conf_missing_args(self):
        self.fx.set_args(VERSION, {})
        self.assertRejected(self.fx.mod.setSessionConf(VERSION))


# ---------------------------------------------------------------------------
# 配置注入（php.ini / pool / session）
# ---------------------------------------------------------------------------

class TestConfigInjection(_FixtureCase):

    def ini(self):
        return self.fx.read(os.path.join(VERSION, 'fpm', 'php.ini'))

    def test_30_submit_php_conf_newline_rejected(self):
        self.fx.set_args(VERSION, {'date.timezone': 'PRC\nINVALID_DIRECTIVE = 1'})
        data = self.assertRejected(self.fx.mod.submitPhpConf(VERSION))
        self.assertIn('参数值不合法!', data['msg'])
        self.assertNotIn('INVALID_DIRECTIVE', self.ini())

    def test_31_submit_php_conf_valid_applied(self):
        self.fx.set_args(VERSION, {'date.timezone': 'Asia/Shanghai'})
        data = self.fx.envelope(self.fx.mod.submitPhpConf(VERSION))
        self.assertTrue(data['status'])
        self.assertIn('date.timezone = Asia/Shanghai', self.ini())
        # 被注释的同名行必须归一化为生效行
        self.assertNotIn(';date.timezone = Asia/Shanghai', self.ini())

    def test_32_set_disable_func_newline_rejected(self):
        self.fx.set_args(VERSION, {'disable_functions': 'exec\nINVALID_DIRECTIVE = 1'})
        self.assertRejected(self.fx.mod.setDisableFunc(VERSION))
        self.assertNotIn('INVALID_DIRECTIVE', self.ini())

    def test_33_set_session_handler_whitelist(self):
        self.fx.set_args(VERSION, {'ip': '1.2.3.4', 'port': '6379', 'passwd': '',
                                   'save_handler': 'evil'})
        data = self.assertRejected(self.fx.mod.setSessionConf(VERSION))
        self.assertIn('Session存储方式不合法!', data['msg'])

    def test_34_set_session_passwd_quote_rejected(self):
        self.fx.set_args(VERSION, {'ip': '1.2.3.4', 'port': '6379',
                                   'passwd': 'a"b', 'save_handler': 'redis'})
        self.assertRejected(self.fx.mod.setSessionConf(VERSION))

    def test_35_set_fpm_numeric_rejected(self):
        self.fx.set_args(VERSION, {'max_children': '30\npm.max_children = 999',
                                   'start_servers': '5', 'min_spare_servers': '5',
                                   'max_spare_servers': '20', 'pm': 'dynamic'})
        data = self.assertRejected(self.fx.mod.setFpmConfig(VERSION))
        self.assertIn('并发参数不合法!', data['msg'])

    def test_36_set_fpm_pm_whitelist(self):
        self.fx.set_args(VERSION, {'max_children': '30', 'start_servers': '5',
                                   'min_spare_servers': '5', 'max_spare_servers': '20',
                                   'pm': 'evil'})
        data = self.assertRejected(self.fx.mod.setFpmConfig(VERSION))
        self.assertIn('运行模式不合法!', data['msg'])

    def test_37_set_fpm_valid_applied(self):
        self.fx.set_args(VERSION, {'max_children': '42', 'start_servers': '5',
                                   'min_spare_servers': '5', 'max_spare_servers': '20',
                                   'pm': 'dynamic'})
        data = self.fx.envelope(self.fx.mod.setFpmConfig(VERSION))
        self.assertTrue(data['status'])
        pool = self.fx.read(os.path.join(VERSION, 'fpm', 'pool.d', 'yf.conf'))
        self.assertIn('pm.max_children = 42', pool)

    def test_38_set_max_size_non_numeric(self):
        self.fx.set_args(VERSION, {'max': 'x'})
        self.assertRejected(self.fx.mod.setMaxSize(VERSION))


# ---------------------------------------------------------------------------
# shell 拼接（shlexQuote / xargs -0 -r）
# ---------------------------------------------------------------------------

class TestShellHardening(_FixtureCase):

    def test_40_clean_session_old_uses_print0(self):
        self.fx.mod.getSessionCount_Origin = lambda v: {'total': 0, 'oldfile': 0}
        data = self.fx.envelope(self.fx.mod.cleanSessionOld(VERSION))
        self.assertTrue(data['status'])
        self.assertTrue(self.fx.shells)
        for cmd in self.fx.shells:
            self.assertIn('-print0', cmd)
            self.assertIn('xargs -0 -r', cmd)
            self.assertNotIn("'sess_'|xargs rm", cmd)

    def test_41_install_lib_cmd_quoted(self):
        seen = []
        orig = self.fx.yf.shlexQuote
        self.fx.yf.shlexQuote = lambda s: (seen.append(str(s)), orig(s))[1]
        try:
            self.fx.set_args(VERSION, {'name': 'redis'})
            data = self.fx.envelope(self.fx.mod.installLib(VERSION))
        finally:
            self.fx.yf.shlexQuote = orig
        self.assertTrue(data['status'])
        self.assertEqual(len(self.fx.tasks), 1)
        cmd = self.fx.tasks[0]['cmd']
        self.assertIn('common.sh', cmd)
        # 版本与扩展名必须经 shlexQuote（防御性引用），用哨兵记录调用入参
        self.assertIn(VERSION, seen)
        self.assertIn('redis', seen)

    def test_42_uninstall_lib_cmd_quoted(self):
        seen = []
        orig = self.fx.yf.shlexQuote
        self.fx.yf.shlexQuote = lambda s: (seen.append(str(s)), orig(s))[1]
        try:
            self.fx.set_args(VERSION, {'name': 'redis'})
            self.fx.mod.uninstallLib(VERSION)
        finally:
            self.fx.yf.shlexQuote = orig
        self.assertTrue(self.fx.shells)
        self.assertIn(VERSION, seen)
        self.assertIn('redis', seen)


# ---------------------------------------------------------------------------
# 结构断言（ast，抗注释蒙混）
# ---------------------------------------------------------------------------

class TestStructure(unittest.TestCase):

    def setUp(self):
        self.tree = _tree(IDX)
        self.src = _read(IDX)

    def test_50_guards_exist(self):
        for name in ('isPhpVersion', 'versionOrError', 'versionOrFail', 'validateIniValue',
                     'setIniKey', '_pidIsPhpFpmMaster', '_intShell'):
            self.assertIsNotNone(_func(self.tree, name), name)

    def test_51_dispatch_validates_version(self):
        self.assertIn('if not isPhpVersion(version):', self.src)
        self.assertIn("print('ERROR: PHP版本参数不合法')", self.src)

    def test_52_entrypoints_have_version_guard(self):
        for name in ('status', 'getConf', 'phpOp', 'getLibConf', 'setSessionConf', 'getPhpinfo',
                     'initdStatus', 'initdInstall', 'initdUinstall', 'installLib', 'uninstallLib',
                     'setMaxTime', 'setMaxSize', 'setFpmConfig', 'submitPhpConf', 'resetPhpConf',
                     'setDisableFunc', 'resetDisableFunc', 'getDisableFunc', 'getPhpConf',
                     'getLimitConf', 'getSessionConf', 'getSessionCount', 'cleanSessionOld',
                     'getFpmConfig', 'getFpmStatus', 'tunePhpConfig', 'upgradeSelfHealing',
                     'checkPluginUpgrade'):
            node = _func(self.tree, name)
            self.assertIsNotNone(node, name)
            self.assertTrue(_calls_any(node, ['versionOrError', 'versionOrFail', 'isPhpVersion']),
                            name)

    def test_53_rm_commands_quoted(self):
        src = _read(IDX)
        # phpOp 与 upgradeSelfHealing 各有一处孤儿 socket 清理，两处都必须走 shlexQuote
        self.assertGreaterEqual(src.count("yf.execShell(f'rm -f {yf.shlexQuote(sock_file)}')"), 2)
        self.assertGreaterEqual(src.count("yf.execShell(f'rm -f {yf.shlexQuote(pid_file)}')"), 1)
        for name in ('phpOp', 'upgradeSelfHealing'):
            self.assertTrue(_calls_any(_func(self.tree, name), ['shlexQuote']), name)

    def test_54_install_uninstall_quote(self):
        for name in ('installLib', 'uninstallLib'):
            self.assertTrue(_calls_any(_func(self.tree, name), ['shlexQuote']), name)

    def test_55_status_uses_proc_comm_not_os_kill(self):
        node = _func(self.tree, 'status')
        code = _code_only(node)
        self.assertNotIn('kill', code)
        self.assertTrue(_calls_any(node, ['_pidIsPhpFpmMaster']))

    def test_56_ini_writes_go_through_setIniKey(self):
        for name in ('submitPhpConf', 'resetPhpConf', 'setDisableFunc', 'resetDisableFunc',
                     'setMaxSize', 'setMaxTime'):
            self.assertTrue(_calls_any(_func(self.tree, name), ['setIniKey']), name)

    def test_57_make_op_conf_guards_readfile(self):
        node = _func(self.tree, 'makeOpConf')
        code = _code_only(node)
        self.assertNotIn('json.loads(content)', code)
        self.assertTrue(_calls_any(node, ['readFile']))

    def test_58_common_sh_has_whitelist(self):
        sh = _read(COMMON_SH)
        self.assertIn("invalid version", sh)
        self.assertIn("invalid extension name", sh)
        self.assertIn('apt-get install -y "php${version}-${extName}"', sh)


# ---------------------------------------------------------------------------
# 前端断言（去注释后的源码）
# ---------------------------------------------------------------------------

class TestFrontend(unittest.TestCase):

    def setUp(self):
        self.src = _strip_js_comments(_read(JS))

    def test_60_php_esc_defined(self):
        self.assertIn('function phpEsc(', self.src)

    def test_61_dynamic_values_escaped(self):
        for marker in ('phpEsc(disable_functions[i])', 'phpEsc(rdata.disable_functions)',
                       'phpEsc(libs[i].name)', 'phpEsc(libs[i].title)', 'phpEsc(libs[i].msg)'):
            self.assertIn(marker, self.src, marker)

    def test_62_uses_safe_api_wrapper(self):
        self.assertIn("YfPlugin.createApi('php-apt')", self.src)
        self.assertNotIn('$.post(', self.src)


# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

class TestI18n(unittest.TestCase):

    def test_70_new_keys_in_all_langs(self):
        key_sets = {}
        for lang in LANGS:
            data = json.loads(_read(os.path.join(LANGDIR, lang + '.json')))
            key_sets[lang] = set(data.keys())
            for k in NEW_MSG_KEYS:
                self.assertIn(k, data, '%s missing %s' % (lang, k))
        base = key_sets['zh-CN']
        for lang in LANGS:
            self.assertEqual(base, key_sets[lang], 'key parity: %s' % lang)

    def test_71_backend_msgs_reachable(self):
        src = _read(IDX)
        for msg in NEW_MSG_KEYS:
            self.assertIn(msg, src, msg)


if __name__ == '__main__':
    unittest.main()
