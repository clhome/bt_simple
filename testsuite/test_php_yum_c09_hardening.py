# coding: utf-8
r"""C09 php-yum 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/php-yum/`（index.py + js/php.js + versions/common.sh + lang/）。真机是
Debian 12，**无 yum/dnf/rpm、无 /etc/opt/remi** → 严禁真实 install/remove；本模块全部在
**临时目录夹具**上真跑插件函数（不碰 /etc/opt/remi、不碰生产 php80/81/83）。

真机探针（`test/_c09_probe.py`，安全载荷只写 /tmp）暴露的缺陷与 C07/C08 同族：
  * **版本号是唯一用户可控「路径/命令片段」入口，且 `formatVersion()` 只是去点、零校验**：
    HEAD 版 `status` / `get_lib_conf` / `initd_status` 三处把 `83; echo PWNED; #` 拼进 shell
    **真的执行**（探针 `INJECTED_*: YES`）；`conf` 对未安装版本仍 `makedirs + 写 php.ini`
    （凭空造产物）。
    → new：`^\d{1,3}$` 白名单 + `isPhpVersion/versionOrError/versionOrFail`，CLI 统一收口
    + 各 sink 二次校验；新增 `isPhpInstalled`，未安装一律拒绝 与 不造产物。
  * **`getArgs` 只认 dict 前的 json.loads 结果**：`args='[]'` → list → 后续 `.keys()`/
    `args['ip']` 抛 AttributeError/KeyError；`set_session_conf '{}'` 真机 traceback。
    → new：非 dict 一律回 {} / `参数格式错误!`。
  * **`set_max_time time='abc'` / `set_max_size max='x'`** 真机 traceback（int() ValueError）
    → new 回业务错误信封。
  * **php.ini / pool / session 指令注入**：`submit_php_conf date.timezone='PRC\nX=1'`、
    `set_disable_func 'exec\nX'`、`set_fpm_conf max_children='30\nX'`、
    `set_session_conf save_handler='evil'` / `ip='1.2.3.4\nX'`（旧 IP 校验是非锚定
    `re.search`）全部可注入 → new 全部白名单/锚定拒绝。
  * **陈旧 pid 文件假阳性**：`status` 用 `os.kill(pid, 0)`，指向任意存活进程即报 start
    → new `_pidIsPhpFpmMaster`（`/proc/<pid>/comm=='php-fpm'` + 本版本目录）精确判定。
  * **`find | grep sess_ | xargs rm -f` 拼接**：无 `-print0`/`-r`、路径未引用（C07 已修 php）
    → new `-maxdepth 2 -type f -name 'sess_*' -print0 | xargs -0 -r` + `shlexQuote`。
  * **`install_lib`/`uninstall_lib`** 的 version/name 拼进 common.sh 调用 → new 白名单 +
    `yf.shlexQuote`，并在 `versions/common.sh` 侧再加同口径正则兜底。
  * **readFile 返回 False 未判**：`getLibConf` 的 `json.loads(readFile(phplib))`、
    `makeOpenrestyConf` 的 `json.loads(readFile(info.json))` → False 时 TypeError
    → new 判空回业务错误。
  * **前端未转义**：`disableFunc` 把 php.ini 的 `disable_functions`、`phpLibConfig` 把扩展
    清单字段原样拼进 innerHTML/`javascript:`（存储型 XSS）→ new `phpEsc`；`getPHPInfo` 缺
    `status` 守卫（错误时 `data.data.replace` 抛异常）→ new 补守卫。

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
PLUGIN_SRC = os.environ.get('YF_C09_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'php-yum')
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

VERSION = '83'
#: 未安装版本：生命周期/启停类断言用（保持夹具里不存在该版本目录）
NOT_INSTALLED = '99'
#: 未安装版本：只用于 getConf 自愈断言（自愈会建出该版本目录，不能与上面的混用）
NOT_INSTALLED_CONF = '97'
BAD_VERSION = '83; echo PWNED > /tmp/yf_c09_pwn; #'

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
session.save_path = "/tmp"
disable_functions = passthru,exec
"""

FPMCONF = """[global]
pid = /var/opt/remi/php83/run/php-fpm/php-fpm.pid
include=/etc/opt/remi/php83/php-fpm.d/*.conf
"""

YFCONF = """[www]
user = www
group = www
listen = /var/opt/remi/php83/run/php-fpm/php83-fpm.sock
pm = dynamic
pm.max_children = 30
pm.start_servers = 5
pm.min_spare_servers = 5
pm.max_spare_servers = 20
request_terminate_timeout = 30
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
    """返回函数体 AST 转储（不含 docstring）——避免把注释/文档里的旧写法当成缺陷。"""
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
        self.root = tempfile.mkdtemp(prefix='c09_fx_')
        self.server = os.path.join(self.root, 'remi')
        self.plugin = os.path.join(self.root, 'php-yum')
        self.wwwserver = os.path.join(self.root, 'wwwserver')
        self.father = os.path.join(self.root, 'father')
        self.shells = []
        self.shellrcs = []
        self.tasks = []
        self.d_so = ''
        self._build()
        self.mod = self._load()

    def _build(self):
        _write(os.path.join(self.server, 'php' + VERSION, 'php.ini'), PHPINI)
        _write(os.path.join(self.server, 'php' + VERSION, 'php-fpm.conf'), FPMCONF)
        _write(os.path.join(self.server, 'php' + VERSION, 'php-fpm.d', 'yf.conf'), YFCONF)
        os.makedirs(self.wwwserver, exist_ok=True)
        os.makedirs(self.father, exist_ok=True)
        for rel in ('conf', 'versions'):
            src = os.path.join(PLUGIN_SRC, rel)
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(self.plugin, rel))
        shutil.copyfile(os.path.join(PLUGIN_SRC, 'info.json'),
                        os.path.join(self.plugin, 'info.json'))

    def _load(self):
        import core.yf  # noqa: F401
        cwd = os.getcwd()
        spec = importlib.util.spec_from_file_location('c09_php_yum_mod', IDX)
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
        # 夹具不真建 /var/opt/remi、/var/run/php-fpm（真机系统路径，测试机不能碰）
        mod.ensureRuntimeDirs = lambda *a, **k: None
        self._patch(self.yf, 'getServerDir', lambda *a, **k: self.wwwserver)
        self._patch(self.yf, 'getPluginDir', lambda *a, **k: self.root)
        self._patch(self.yf, 'getFatherDir', lambda *a, **k: self.father)
        self._patch(self.yf, 'getLocalIp', lambda *a, **k: '127.0.0.1')
        self._patch(self.yf, 'getSslCrt', lambda *a, **k: '')
        self._patch(self.yf, 'makeDirs', self._make_dirs)
        self._patch(self.yf, 'writeLog', lambda *a, **k: None)
        self._patch(self.yf, 'triggerTask', lambda *a, **k: None)
        self._patch(self.yf, 'requestFcgiPHP', lambda *a, **k: None)
        self._patch(self.yf, 'M', self._m)
        self._patch(self.yf, 'execShell', self._exec_shell)
        self._patch(self.yf, 'execShellRc', self._exec_shell_rc)
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

    @staticmethod
    def _m(_table=''):
        class _Q(object):
            def where(self, *a, **k):
                return self

            def field(self, *a, **k):
                return self

            def select(self):
                return []

        return _Q()

    def _exec_shell(self, cmd, cwd=None, timeout=None, shell=True):
        self.shells.append(cmd)
        if 'php.d' in cmd:
            return (self.d_so, '')
        return ('', '')

    def _exec_shell_rc(self, cmd, cwd=None, timeout=None, shell=True):
        self.shellrcs.append(cmd)
        return (0, 'enabled', '')

    def _make_dirs(self, path):
        # 只允许在夹具临时目录内建目录，避免测试机被写出 C:\var\remi 之类的系统路径
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
        self.fx.shellrcs[:] = []
        self.fx.tasks[:] = []
        self.fx.d_so = ''

    def assertRejected(self, raw):
        data = self.fx.envelope(raw)
        self.assertFalse(data['status'])
        return data


# ---------------------------------------------------------------------------
# 版本白名单 + 路径穿越 / 注入 / 未安装不造产物
# ---------------------------------------------------------------------------

class TestVersionGuards(_FixtureCase):

    def test_01_version_whitelist(self):
        m = self.fx.mod
        for good in ('83', '74', '8', ' 83 ', '83\n'):
            self.assertTrue(m.isPhpVersion(good), good)
        for bad in ('', '8.3', None, '../../etc', '83;id', 'a83', 'x', '83 4',
                    '8383', '-83', '../83'):
            self.assertFalse(m.isPhpVersion(bad), bad)
        # formatVersion 只做去点归一化，不能当校验用
        self.assertEqual(m.formatVersion('8.3'), '83')
        self.assertFalse(m.isPhpVersion('8.3'))

    def test_02_version_or_error_envelope(self):
        m = self.fx.mod
        err, ver = m.versionOrError('83')
        self.assertIsNone(err)
        self.assertEqual(ver, '83')
        err, ver = m.versionOrError('../../etc')
        self.assertIsNotNone(err)
        self.assertIsNone(ver)
        self.assertIn('PHP版本参数不合法!', json.loads(err)['msg'])

    def test_03_status_rejects_injection(self):
        self.assertEqual(self.fx.mod.status(BAD_VERSION), 'ERROR: PHP版本参数不合法')
        self.assertEqual(self.fx.shells, [])

    def test_04_conf_whitelist_only(self):
        m = self.fx.mod
        # 非法版本：不得拼路径、不得建目录（旧实现 `conf '../../etc'` 以 root 建树）
        self.assertEqual(m.getConf('../../etc'), '')
        # 合法版本：getConf 的「自愈生成 php.ini」是既有契约，但只能落在版本目录内
        vdir = os.path.join(self.fx.server, 'php' + NOT_INSTALLED_CONF)
        self.assertEqual(os.path.normpath(m.getConf(NOT_INSTALLED_CONF)),
                         os.path.normpath(os.path.join(vdir, 'php.ini')))
        self.assertTrue(os.path.exists(os.path.join(vdir, 'php.ini')))
        # 只有版本目录内的 bootstrap ini，不得出现任何生命周期产物
        self.assertEqual(['php.ini'], sorted(os.listdir(vdir)))

    def test_05_conf_requires_server_root(self):
        # 服务根目录（/etc/opt/remi）不存在 = 本机从未装过 → 不得自愈造产物
        m = self.fx.mod
        orig = m.getServerDir
        m.getServerDir = lambda *a, **k: os.path.join(self.fx.root, 'no_such_server')
        try:
            self.assertEqual(m.getConf(VERSION), '')
            self.assertFalse(m.isPhpInstalled(VERSION))
        finally:
            m.getServerDir = orig
        self.assertFalse(os.path.exists(os.path.join(self.fx.root, 'no_such_server')))

    def test_05_get_lib_conf_rejects(self):
        self.assertRejected(self.fx.mod.getLibConf(BAD_VERSION))
        self.assertEqual(self.fx.shells, [])

    def test_06_initd_guards(self):
        m = self.fx.mod
        for fn in ('initdStatus', 'initdInstall', 'initdUinstall'):
            self.assertEqual(getattr(m, fn)(BAD_VERSION), 'ERROR: PHP版本参数不合法', fn)
        self.assertEqual(self.fx.shells, [])
        self.assertEqual(self.fx.shellrcs, [])
        # 未安装的合法版本：一律 fail（旧实现无条件 'ok'）
        for fn in ('initdStatus', 'initdInstall', 'initdUinstall'):
            self.assertEqual(getattr(m, fn)(NOT_INSTALLED), 'fail', fn)

    def test_07_install_uninstall_lib_rejects(self):
        m = self.fx.mod
        self.fx.set_args(BAD_VERSION, {'name': 'redis'})
        self.assertRejected(m.installLib(BAD_VERSION))
        self.assertRejected(m.uninstallLib(BAD_VERSION))
        self.fx.set_args(VERSION, {'name': 'redis; id'})
        self.assertRejected(m.installLib(VERSION))
        self.assertRejected(m.uninstallLib(VERSION))
        self.assertEqual(self.fx.tasks, [])
        self.assertEqual(self.fx.shells, [])

    def test_08_json_entrypoints_reject_bad_version(self):
        m = self.fx.mod
        self.fx.set_args(BAD_VERSION, {'time': '60'})
        for fn in ('setMaxTime', 'setMaxSize', 'setFpmConfig', 'submitPhpConf',
                   'resetPhpConf', 'setDisableFunc', 'resetDisableFunc', 'getDisableFunc',
                   'getFpmConfig', 'getFpmStatus', 'getPhpConf', 'getLimitConf',
                   'getSessionConf', 'getSessionCount', 'cleanSessionOld', 'tunePhpConfig'):
            data = self.assertRejected(getattr(m, fn)(BAD_VERSION))
            self.assertIn('PHP版本参数不合法!', data['msg'], fn)
        self.assertEqual(self.fx.shells, [])

    def test_09_phpinfo_rejects(self):
        self.assertEqual(self.fx.mod.getPhpinfo(BAD_VERSION), 'ERROR: PHP版本参数不合法')
        self.assertEqual(self.fx.mod.getPhpinfo(NOT_INSTALLED), 'PHP[99]未安装,不可访问!')

    def test_10_upgrade_and_check_reject(self):
        m = self.fx.mod
        self.assertRejected(m.upgradeSelfHealing(BAD_VERSION))
        self.assertRejected(m.checkPluginUpgrade(BAD_VERSION))
        self.assertRejected(m.upgradeSelfHealing(NOT_INSTALLED))

    def test_11_pid_master_check(self):
        m = self.fx.mod
        # 当前进程 comm 不是 php-fpm → 必须 False（防陈旧 pid 指向无关存活进程误报 start）
        self.assertFalse(m._pidIsPhpFpmMaster(os.getpid(), VERSION))

    def test_12_uninstalled_never_fabricates(self):
        m = self.fx.mod
        self.assertEqual(m.phpOp(NOT_INSTALLED, 'start'), 'ERROR: PHP-99 未安装')
        self.assertEqual(m.start(NOT_INSTALLED), 'ERROR: PHP-99 未安装')
        self.assertEqual(m.restart(NOT_INSTALLED), 'ERROR: PHP-99 未安装')
        self.assertFalse(m.initReplace(NOT_INSTALLED))
        self.assertFalse(m.phpFpmWwwReplace(NOT_INSTALLED))
        self.assertFalse(m.makeOpenrestyConf('%%%'))
        # 生命周期产物一个都不允许出现（旧实现造出 php-fpm.d/yf.conf + install.ok + web_conf 三件套）
        self.assertFalse(os.path.exists(os.path.join(
            self.fx.server, 'php' + NOT_INSTALLED, 'php-fpm.d', 'yf.conf')))
        self.assertFalse(os.path.exists(os.path.join(
            self.fx.server, 'php' + NOT_INSTALLED, 'php-fpm.conf')))
        self.assertFalse(os.path.exists(os.path.join(
            self.fx.root, 'wwwserver', 'php-yum', NOT_INSTALLED, 'install.ok')))
        self.assertFalse(os.path.exists(os.path.join(
            self.fx.wwwserver, 'web_conf', 'php', 'conf', 'enable-php-yum99.conf')))
        self.assertFalse(os.path.exists(os.path.join(self.fx.server, 'php' + NOT_INSTALLED)))

    def test_13_status_uninstalled_is_stop(self):
        # 未安装且 systemctl 非 active → stop（而不是假阳性 start）
        self.assertEqual(self.fx.mod.status(NOT_INSTALLED), 'stop')


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
        data = self.assertRejected(self.fx.mod.setMaxTime(VERSION))
        self.assertIn('时间参数不合法!', data['msg'])

    def test_25_set_max_size_non_numeric(self):
        self.fx.set_args(VERSION, {'max': 'x'})
        data = self.assertRejected(self.fx.mod.setMaxSize(VERSION))
        self.assertIn('上传大小参数不合法!', data['msg'])

    def test_26_set_session_conf_missing_args(self):
        self.fx.set_args(VERSION, {})
        self.assertRejected(self.fx.mod.setSessionConf(VERSION))


# ---------------------------------------------------------------------------
# 配置注入（php.ini / pool / session）
# ---------------------------------------------------------------------------

class TestConfigInjection(_FixtureCase):

    def ini(self):
        return self.fx.read(os.path.join('php' + VERSION, 'php.ini'))

    def yfconf(self):
        return self.fx.read(os.path.join('php' + VERSION, 'php-fpm.d', 'yf.conf'))

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
        # 被注释的同名行必须归一化为生效行（旧实现写回去仍是注释 → 用户改了不生效）
        self.assertNotIn(';date.timezone = Asia/Shanghai', self.ini())

    def test_32_set_disable_func_newline_rejected(self):
        self.fx.set_args(VERSION, {'disable_functions': 'exec\nINVALID_DIRECTIVE = 1'})
        data = self.assertRejected(self.fx.mod.setDisableFunc(VERSION))
        self.assertIn('禁用函数格式不合法!', data['msg'])
        self.assertNotIn('INVALID_DIRECTIVE', self.ini())

    def test_33_set_disable_func_valid_applied(self):
        self.fx.set_args(VERSION, {'disable_functions': 'exec,passthru'})
        data = self.fx.envelope(self.fx.mod.setDisableFunc(VERSION))
        self.assertTrue(data['status'])
        self.assertIn('disable_functions = exec,passthru', self.ini())

    def test_34_set_session_handler_whitelist(self):
        self.fx.set_args(VERSION, {'ip': '1.2.3.4', 'port': '6379', 'passwd': '',
                                   'save_handler': 'evil'})
        data = self.assertRejected(self.fx.mod.setSessionConf(VERSION))
        self.assertIn('Session存储方式不合法!', data['msg'])

    def test_35_set_session_ip_anchored(self):
        self.fx.set_args(VERSION, {'ip': '1.2.3.4\nINVALID_DIRECTIVE = 1', 'port': '6379',
                                   'passwd': '', 'save_handler': 'redis'})
        data = self.assertRejected(self.fx.mod.setSessionConf(VERSION))
        self.assertIn('请输入正确的IP地址', data['msg'])
        self.assertNotIn('INVALID_DIRECTIVE', self.ini())

    def test_36_set_session_passwd_quote_newline_rejected(self):
        for bad in ('a"b', 'a\nINVALID_DIRECTIVE = 1', 'a\\b'):
            self.fx.set_args(VERSION, {'ip': '1.2.3.4', 'port': '6379',
                                       'passwd': bad, 'save_handler': 'redis'})
            self.assertRejected(self.fx.mod.setSessionConf(VERSION))
        self.assertNotIn('INVALID_DIRECTIVE', self.ini())

    def test_37_set_session_redis_valid(self):
        self.fx.d_so = 'redis.so\n'
        self.fx.set_args(VERSION, {'ip': '1.2.3.4', 'port': '6379',
                                   'passwd': 's3cret', 'save_handler': 'redis'})
        data = self.fx.envelope(self.fx.mod.setSessionConf(VERSION))
        self.assertTrue(data['status'])
        ini = self.ini()
        self.assertIn('session.save_handler = redis', ini)
        self.assertIn('session.save_path = "tcp://1.2.3.4:6379?auth=s3cret"', ini)

    def test_38_set_fpm_numeric_rejected(self):
        self.fx.set_args(VERSION, {'max_children': '30\npm.max_children = 999',
                                   'start_servers': '5', 'min_spare_servers': '5',
                                   'max_spare_servers': '20', 'pm': 'dynamic'})
        data = self.assertRejected(self.fx.mod.setFpmConfig(VERSION))
        self.assertIn('并发参数不合法!', data['msg'])
        self.assertNotIn('pm.max_children = 999', self.yfconf())

    def test_39_set_fpm_pm_whitelist(self):
        self.fx.set_args(VERSION, {'max_children': '30', 'start_servers': '5',
                                   'min_spare_servers': '5', 'max_spare_servers': '20',
                                   'pm': 'evil'})
        data = self.assertRejected(self.fx.mod.setFpmConfig(VERSION))
        self.assertIn('运行模式不合法!', data['msg'])

    def test_40_set_fpm_valid_applied(self):
        self.fx.set_args(VERSION, {'max_children': '42', 'start_servers': '5',
                                   'min_spare_servers': '5', 'max_spare_servers': '20',
                                   'pm': 'ondemand'})
        data = self.fx.envelope(self.fx.mod.setFpmConfig(VERSION))
        self.assertTrue(data['status'])
        conf = self.yfconf()
        self.assertIn('pm.max_children = 42', conf)
        self.assertIn('pm = ondemand', conf)

    def test_41_set_max_time_valid_applied(self):
        self.fx.set_args(VERSION, {'time': '120'})
        data = self.fx.envelope(self.fx.mod.setMaxTime(VERSION))
        self.assertTrue(data['status'])
        self.assertIn('max_execution_time = 120', self.ini())
        self.assertIn('request_terminate_timeout = 120', self.yfconf())

    def test_42_set_max_size_valid_applied(self):
        self.fx.set_args(VERSION, {'max': '64'})
        data = self.fx.envelope(self.fx.mod.setMaxSize(VERSION))
        self.assertTrue(data['status'])
        ini = self.ini()
        self.assertIn('upload_max_filesize = 64M', ini)
        self.assertIn('post_max_size = 64M', ini)

    def test_43_get_lib_conf_readfile_guards(self):
        os.remove(os.path.join(self.fx.plugin, 'versions', 'phplib.conf'))
        data = self.assertRejected(self.fx.mod.getLibConf(VERSION))
        self.assertIn('扩展列表配置文件不存在!', data['msg'])
        _write(os.path.join(self.fx.plugin, 'versions', 'phplib.conf'), '{not json')
        data = self.assertRejected(self.fx.mod.getLibConf(VERSION))
        self.assertIn('扩展列表配置文件格式错误!', data['msg'])

    def test_44_get_fpm_status_fcgi_false(self):
        self.fx.set_args(VERSION, {})
        orig = self.fx.mod.status
        self.fx.mod.status = lambda v: 'start'
        try:
            data = self.assertRejected(self.fx.mod.getFpmStatus(VERSION))
        finally:
            self.fx.mod.status = orig
        self.assertIn('获取状态失败', data['msg'])

    def test_45_get_phpinfo_fcgi_false(self):
        # 旧实现 str(False, encoding='utf-8') → TypeError traceback
        orig = self.fx.mod.status
        self.fx.mod.status = lambda v: 'start'
        try:
            out = self.fx.mod.getPhpinfo(VERSION)
        finally:
            self.fx.mod.status = orig
        self.assertIn('未启动', out)


# ---------------------------------------------------------------------------
# shell 拼接（shlexQuote / xargs -0 -r / execShellRc）
# ---------------------------------------------------------------------------

class TestShellHardening(_FixtureCase):

    def test_50_clean_session_old_uses_print0(self):
        data = self.fx.envelope(self.fx.mod.cleanSessionOld(VERSION))
        self.assertTrue(data['status'])
        rm_cmds = [c for c in self.fx.shells if 'rm -f' in c]
        self.assertEqual(len(rm_cmds), 2)
        for cmd in rm_cmds:
            self.assertIn('-print0', cmd)
            self.assertIn('xargs -0 -r', cmd)
            self.assertNotIn("'sess_'|xargs rm", cmd)
            self.assertIn('-maxdepth 2', cmd)

    def test_51_session_count_uses_shlexquote(self):
        seen = []
        orig = self.fx.yf.shlexQuote
        self.fx.yf.shlexQuote = lambda s: (seen.append(str(s)), orig(s))[1]
        try:
            data = self.fx.envelope(self.fx.mod.getSessionCount(VERSION))
        finally:
            self.fx.yf.shlexQuote = orig
        self.assertTrue(data['status'])
        self.assertIn('/tmp', seen)

    def test_52_install_lib_cmd_quoted(self):
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
        self.assertIn('common.sh', self.fx.tasks[0]['cmd'])
        self.assertIn(VERSION, seen)
        self.assertIn('redis', seen)

    def test_53_uninstall_lib_cmd_quoted(self):
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

    def test_54_www_conf_backup_quoted(self):
        conf = os.path.join(self.fx.server, 'php' + VERSION, 'php-fpm.d', 'www.conf')
        _write(conf, '[www]\nlisten = /tmp/www.sock\n')
        self.fx.mod.phpFpmWwwReplace(VERSION)
        mv = [c for c in self.fx.shells if c.startswith('mv ')]
        self.assertTrue(mv)
        self.assertIn("'", mv[0])


# ---------------------------------------------------------------------------
# 结构断言（ast，抗注释蒙混）
# ---------------------------------------------------------------------------

class TestStructure(unittest.TestCase):

    def setUp(self):
        self.tree = _tree(IDX)
        self.src = _read(IDX)

    def test_60_guards_exist(self):
        for name in ('isPhpVersion', 'versionOrError', 'versionOrFail', 'isPhpInstalled',
                     'getVersionDir', 'validateIniValue', 'setIniKey', '_pidIsPhpFpmMaster'):
            self.assertIsNotNone(_func(self.tree, name), name)

    def test_61_dispatch_validates_version(self):
        self.assertIn('if func not in', self.src)
        self.assertIn('and not isPhpVersion(version):', self.src)
        self.assertIn("print('ERROR: PHP版本参数不合法')", self.src)

    def test_62_entrypoints_have_version_guard(self):
        for name in ('status', 'getConf', 'phpOp', 'initReplace', 'getLibConf', 'setSessionConf',
                     'getPhpinfo', 'initdStatus', 'initdInstall', 'initdUinstall', 'installLib',
                     'uninstallLib', 'setMaxTime', 'setMaxSize', 'setFpmConfig', 'submitPhpConf',
                     'resetPhpConf', 'setDisableFunc', 'resetDisableFunc', 'getDisableFunc',
                     'getPhpConf', 'getLimitConf', 'getSessionConf', 'getSessionCount',
                     'cleanSessionOld', 'getFpmConfig', 'getFpmStatus', 'tunePhpConfig',
                     'upgradeSelfHealing', 'checkPluginUpgrade', 'makeOpenrestyConf',
                     'phpFpmWwwReplace', 'phpFpmReplace', 'phpPrependFile'):
            node = _func(self.tree, name)
            self.assertIsNotNone(node, name)
            self.assertTrue(_calls_any(node, ['versionOrError', 'versionOrFail', 'isPhpVersion',
                                              'isPhpInstalled', '_isInstalledVersionOrError']),
                            name)

    def test_63_status_has_no_os_kill(self):
        node = _func(self.tree, 'status')
        code = _code_only(node)
        self.assertNotIn("'kill'", code)
        self.assertTrue(_calls_any(node, ['_pidIsPhpFpmMaster']))

    def test_64_ini_writes_go_through_setinikey(self):
        for name in ('submitPhpConf', 'resetPhpConf', 'setDisableFunc', 'resetDisableFunc',
                     'setMaxSize', 'setMaxTime', 'setFpmConfig', 'tunePhpConfig'):
            self.assertTrue(_calls_any(_func(self.tree, name), ['setIniKey']), name)

    def test_65_initreplace_guards_installed(self):
        for name in ('initReplace', 'phpOp', 'upgradeSelfHealing', 'phpFpmWwwReplace',
                     'phpFpmReplace', 'getLibConf'):
            self.assertTrue(_calls_any(_func(self.tree, name),
                                       ['isPhpInstalled', '_isInstalledVersionOrError']), name)
        # getConf 只做版本白名单（自愈生成 php.ini 是既有契约）
        self.assertFalse(_calls_any(_func(self.tree, 'getConf'), ['isPhpInstalled']))
        self.assertTrue(_calls_any(_func(self.tree, 'getConf'), ['isPhpVersion']))

    def test_66_readfile_guards(self):
        lib = _code_only(_func(self.tree, 'getLibConf'))
        self.assertNotIn('json.loads', lib.replace('json.loads(phplib_raw)', ''))
        self.assertTrue(_calls_any(_func(self.tree, 'getLibConf'), ['readFile']))
        mk = _func(self.tree, 'makeOpenrestyConf')
        self.assertTrue(_calls_any(mk, ['readFile']))

    def test_67_initd_uses_rc(self):
        for name in ('initdStatus', 'initdInstall', 'initdUinstall'):
            self.assertTrue(_calls_any(_func(self.tree, name), ['execShellRc']), name)

    def test_68_common_sh_has_whitelist(self):
        sh = _read(COMMON_SH)
        self.assertIn('invalid version', sh)
        self.assertIn('invalid extension name', sh)
        self.assertIn("^[0-9]{1,3}$", sh)


# ---------------------------------------------------------------------------
# 前端断言（去注释后的源码）
# ---------------------------------------------------------------------------

class TestFrontend(unittest.TestCase):

    def setUp(self):
        self.src = _strip_js_comments(_read(JS))

    def test_70_php_esc_defined(self):
        self.assertIn('function phpEsc(', self.src)

    def test_71_dynamic_values_escaped(self):
        for marker in ('phpEsc(disable_functions[i])', 'phpEsc(rdata.disable_functions)',
                       'phpEsc(libs[i].name)', 'phpEsc(libs[i].title)', 'phpEsc(libs[i].msg)',
                       'phpEsc(version)'):
            self.assertIn(marker, self.src, marker)

    def test_72_phpinfo_status_guard(self):
        i = self.src.index('function getPHPInfo(')
        seg = self.src[i:i + 400]
        self.assertIn('if (!data.status)', seg)

    def test_73_uses_safe_api_wrapper(self):
        self.assertIn("YfPlugin.createApi('php-yum')", self.src)
        self.assertNotIn('$.post(', self.src)


# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

class TestI18n(unittest.TestCase):

    def test_80_new_keys_in_all_langs(self):
        key_sets = {}
        for lang in LANGS:
            data = json.loads(_read(os.path.join(LANGDIR, lang + '.json')))
            key_sets[lang] = set(data.keys())
            for k in NEW_MSG_KEYS:
                self.assertIn(k, data, '%s missing %s' % (lang, k))
        base = key_sets['zh-CN']
        for lang in LANGS:
            self.assertEqual(base, key_sets[lang], 'key parity: %s' % lang)

    def test_81_backend_msgs_reachable(self):
        src = _read(IDX)
        for msg in NEW_MSG_KEYS:
            self.assertIn(msg, src, msg)


if __name__ == '__main__':
    unittest.main()
