# coding: utf-8
r"""C07 php 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/php/`。真机 Debian12 上 php80/81/83 均 active+enabled（unix socket），
php80 被生产站点引用（phpmyadmin + 172.17.60.248），php81/php83 无 vhost 引用 →
口径 = **夹具真跑 + 真机 HTTP 面 + 一次可回滚写 + 全程 md5 对照**。

真机对照（详见 task.md 的 C07 行；同一份夹具探针 old/new 逐条对照 62 场景，49 条不同）：
  * **版本号是全模块唯一的用户可控「路径/命令片段」**：old `status('../../etc')` 会把
    穿越值拼进 shell；`getConf('../../../tmp/x')` 会以 root 真建出 `<任意目录>/etc/php.ini`
    （夹具 `file_created=True`）；new 一律「PHP版本参数不合法」且零落盘。
  * **pool 穿越 = 任意文件写**：old `get_fpm_conf {"pool":"../../../evil"}` 真机实测建出
    `/www/server/php/evil.conf`；`set_fpm_conf` 更会连带造出 init.d 脚本、systemd unit 与
    整套 `web_conf/php/*` 模板 → new 回「FPM池名不合法!」且零落盘。
  * **php.ini 指令注入**：old `submit_php_conf date.timezone='PRC\nINVALID_DIRECTIVE = 1'`、
    `set_disable_func 'exec\nINVALID...'`、`set_session_conf ip='1.2.3.4\nINVALID...'`
    （IP 校验用非锚定 re.search）全部回「设置成功」并把注入行真写进 php.ini → new 全部拒绝。
  * **注释键静默失效**：old `submit_php_conf` 的替换正则不含 `^\s*;?`，`;date.timezone = UTC`
    写回去仍是注释行（用户改了却不生效，界面还回成功）→ new 归一化为未注释的 `date.timezone = UTC`。
  * **未安装也造产物 + 假成功**：old `start('99')` 建出 `etc/php.ini`、`init.d/php99`、
    `systemd/php99.service` 等 6 个产物并真跑 `systemctl start`；`upgrade_self_healing('99')`
    同样凭空造树；`initd_install/uninstall` 无条件回 `ok`（真机实测 unit 不存在也回 ok）→
    new 一律 `ERROR: PHP-99 未安装` / `skipped=['99']`，零产物。
  * **status 假阳性两处**：① old `ps aux|grep 'php-fpm: master process'|grep '/php/<v>/'`
    命中**命令行带这些字样的无关 python 进程**（夹具 `stop`→实测 `start`）；② 陈旧 pid 文件
    指向任意存活进程时 `os.kill(pid,0)` 成功即报 `start` → new 按 `/proc/<pid>/comm == php-fpm`
    + 本版本目录精确判定，两处都回 `stop`，真 master 仍回 `start`。
  * **`getFpmAddress` 的 `bind` NameError**：old 在「监听 TCP」与「自定义 socket 路径」两种
    配置下都静默回退成默认 `/tmp/php-cgi-<v>.sock`（fcgi 必连不上）→ new 回 `('127.0.0.1',9000)`
    与配置里的真实 socket 路径。
  * **readFile 失败返回 False 未判**：old `getFpmStatus`/`getPhpinfo` 连接失败时
    `str(False, encoding='utf-8')` → `TypeError`；`getSessionCount_Origin` 用 `int()` 直接吃
    shell 输出 → 空输出 `ValueError` → new 全部回业务错误信封 / 0。
  * **扩展名命令注入（root RCE）**：old `install_lib name='x; touch /tmp/pwn'` 把注入命令
    **写进后台任务队列**（真机实测 task id=72 落库并执行）、`uninstall_lib` 当场 `execShell`
    执行（真机实测建出 `/tmp/yf_c07_pwn`）→ new 按 `versions/phplib.conf` 白名单拒绝。
  * **`kill_all_php` 跨插件误杀**：old `pkill -9 -f php-fpm` 把系统包安装的
    php-fpm7.4/8.3/8.4 一并 SIGKILL（真机实测 php80 因 unit 无 Restart 留在 failed）→
    new 收窄为 `pkill -9 -x php-fpm`（只杀源码编译版）。

断言策略：能真跑的一律真跑（夹具真跑 + 记录型 shell）；结构类断言用 `ast`（抗「Python 注释 /
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
PLUGIN_SRC = os.environ.get('YF_C07_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'php')

#: 插件 index.py 里 `import core.yf` 依赖面板 web/ 目录在 sys.path 上（真机由面板进程提供）
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)

IDX = os.path.join(PLUGIN_SRC, 'index.py')
IDX_PHP = os.path.join(PLUGIN_SRC, 'index_php.py')
JS = os.path.join(PLUGIN_SRC, 'js', 'php.js')
LANGDIR = os.path.join(PLUGIN_SRC, 'lang')

LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
#: 本轮新增的后端消息键（六语言必须齐备且一致）
NEW_MSG_KEYS = ['PHP版本参数不合法!', 'PHP版本未安装!', '参数格式错误!', '参数值不合法!',
                '没有需要保存的配置项!', '配置文件写入失败!', 'FPM池名不合法!',
                '并发参数不合法!', '运行模式不合法!', '读取 PHP-FPM 配置文件失败!',
                'FPM配置校验失败,已回滚!', '当前PHP-FPM配置不支持该参数!',
                '上传大小限制过大!', 'Session存储方式不合法!', '禁用函数格式不合法!',
                '扩展列表配置文件不存在!', '扩展列表配置文件格式错误!',
                '扩展名称不合法!', '未找到该扩展的卸载脚本!']
CJK_RE = re.compile(r'[\u3400-\u9fff]')

VERSION = '85'          # 夹具里「已安装」的版本（真机无此版本，避免与生产 php80/81/83 混淆）
NOT_INSTALLED = '99'    # 夹具里「未安装」的版本

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
session.save_path = "/www/server/php/tmp/session"
disable_functions = passthru,exec
extension = "redis.so"
extension = "memcached.so"
"""

WWWCONF = """[www]
user = www
group = www
listen = /tmp/php-cgi-85.sock
pm = dynamic
pm.max_children = 30
pm.start_servers = 5
pm.min_spare_servers = 5
pm.max_spare_servers = 20
pm.status_path = /phpfpm_status_85
request_terminate_timeout = 30
"""

STUB = """#!/bin/bash
cfg=""
while [ $# -gt 0 ]; do
  if [ "$1" = "-y" ]; then shift; cfg="$1"; fi
  shift
done
if [ -n "$cfg" ] && grep -rq 'INVALID_DIRECTIVE' "$(dirname "$cfg")" 2>/dev/null; then
  echo "ERROR: syntax error" >&2
  exit 1
fi
exit 0
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
    """调用名是否命中 names 之一（容忍 `yf.` / `os.path.` 前缀）。"""
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
    """抹掉 JS 注释（保留字符串/正则字面量），避免把旧写法写在注释里骗过断言。"""
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
        # 正则字面量：`/\"/g`、`/'/g` 这类正则里的引号会把引号配对状态机带偏，
        # 一旦带偏，后面的注释就剥不掉 → 注释蒙混探针会漏判（C05 已踩过）。
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


# ---------------------------------------------------------------------------
# 夹具：临时 server 根 + 记录型 shell + 进程表桩
# ---------------------------------------------------------------------------

class _Fixture(object):
    """把 `yf.getServerDir()` 指到临时目录，真跑插件函数（不碰生产）。"""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix='c07_fx_')
        self.server = os.path.join(self.root, 'server')
        self.systemd = os.path.join(self.root, 'systemd')
        self.father = os.path.join(self.root, 'father')
        self.shells = []
        self.shellrc = []
        self.tasks = []
        self.procs = []
        self.fcgi_ok = False
        self.rc = (0, '', '')
        self._build()
        self.mod = self._load()

    # ---- 夹具文件 ----
    def _build(self):
        ver = os.path.join(self.server, 'php', VERSION)
        _write(os.path.join(ver, 'etc', 'php.ini'), PHPINI)
        _write(os.path.join(ver, 'etc', 'php-fpm.conf'),
               '[global]\npid = run/php-fpm.pid\ninclude = %s/php/%s/etc/php-fpm.d/*.conf\n'
               % (self.server.replace('\\', '/'), VERSION))
        _write(os.path.join(ver, 'etc', 'php-fpm.d', 'www.conf'), WWWCONF)
        _write(os.path.join(ver, 'etc', 'php-fpm.d', 'tcp.conf'),
               '[tcp]\nlisten = 127.0.0.1:9000\n')
        _write(os.path.join(ver, 'etc', 'php-fpm.d', 'custom.conf'),
               '[custom]\nlisten = /run/php-fpm-85-custom.sock\n')
        _write(os.path.join(ver, 'sbin', 'php-fpm'), STUB, 0o755)
        for sub in ('var/run', 'var/log'):
            os.makedirs(os.path.join(ver, *sub.split('/')), exist_ok=True)
        os.makedirs(os.path.join(self.server, 'php', NOT_INSTALLED), exist_ok=True)
        os.makedirs(os.path.join(self.server, 'tmp', 'session'), exist_ok=True)
        os.makedirs(self.systemd, exist_ok=True)
        os.makedirs(self.father, exist_ok=True)

    def _load(self):
        import core.yf  # noqa: F401
        cwd = os.getcwd()
        spec = importlib.util.spec_from_file_location('c07_php_mod', IDX)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        finally:
            os.chdir(cwd)
        self.yf = sys.modules['core.yf']
        self._saved = {}
        self._patch(self.yf, 'getServerDir', lambda *a, **k: self.server)
        self._patch(self.yf, 'systemdCfgDir', lambda *a, **k: self.systemd)
        self._patch(self.yf, 'getFatherDir', lambda *a, **k: self.father)
        self._patch(self.yf, 'writeLog', lambda *a, **k: None)
        # getInfo 不接管：它是纯函数，真跑才能拓到「格式化参数必须是 str」这类回归
        self._patch(self.yf, 'triggerTask', lambda *a, **k: None)
        self._patch(self.yf, 'syncPidFile', lambda *a, **k: True)
        self._patch(self.yf, 'execShell', self._exec_shell)
        self._patch(self.yf, 'execShellRc', self._exec_rc)
        self._patch(self.yf, 'requestFcgiPHP', self._fcgi)
        mod.getPluginVersionFile = lambda: os.path.join(self.root, 'plugin_version.pl')
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

    def _exec_rc(self, cmd, cwd=None, timeout=None, shell=True):
        self.shellrc.append(cmd)
        if isinstance(cmd, (list, tuple)):
            # php-fpm -t 语法校验：按真机行为模拟（递归检查 include 目录里的 INVALID_DIRECTIVE）。
            # 不真跑进程：Windows 上无法执行 bash 存根，而真机已经逐条对照过真 `php-fpm -t`。
            conf = ''
            for i, item in enumerate(cmd):
                if item == '-y' and i + 1 < len(cmd):
                    conf = cmd[i + 1]
            bad = False
            if conf and os.path.isdir(os.path.dirname(conf)):
                for root, dirs, files in os.walk(os.path.dirname(conf)):
                    for name in files:
                        try:
                            if 'INVALID_DIRECTIVE' in _read(os.path.join(root, name)):
                                bad = True
                        except Exception:
                            pass
            if bad:
                return (1, '', 'ERROR: syntax error')
            return (0, 'configuration file %s test is successful' % conf, '')
        return self.rc

    def _fcgi(self, *a, **k):
        return b'{"pool":"www","process manager":"dynamic","start time":1759128995}' \
            if self.fcgi_ok else False

    # ---- 工具 ----
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

    def set_argv(self, *argv):
        sys.argv = [IDX, 'func'] + list(argv)

    def set_args(self, obj):
        self.set_argv(VERSION, json.dumps(obj))

    def call(self, fn, *a, **k):
        return getattr(self.mod, fn)(*a, **k)

    def envelope(self, raw):
        data = json.loads(raw)
        self.assertIsInstance(data, dict)
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
        self.fx.shellrc[:] = []
        self.fx.tasks[:] = []
        self.fx.fcgi_ok = False
        self.fx.rc = (0, '', '')
        self.fx.procs = []

    # ---- 进程表桩（跨平台：直接替掉 _iterProcesses 这个唯一进程来源）----
    def stub_procs(self, rows):
        self.fx.mod._iterProcesses = lambda: iter(rows)

    def restore_procs(self):
        del self.fx.mod._iterProcesses

    def stub_proc_info(self, comm, args):
        self.fx.mod._procInfo = lambda pid: (comm, args)

    def restore_proc_info(self):
        del self.fx.mod._procInfo


class TestPhpVersionAndPoolGuards(_FixtureCase):

    def test_01_version_whitelist(self):
        m = self.fx.mod
        for good in ('85', ' 83 ', '80\n', '8', '999'):
            self.assertTrue(m.isPhpVersion(good), good)
        for bad in ('../../etc', '', None, '80;id', 'a80', '8 0', '../80', 'x', '8.0', '80-1'):
            self.assertFalse(m.isPhpVersion(bad), bad)

    def test_02_version_or_error_envelope(self):
        m = self.fx.mod
        err, ver = m.versionOrError('85')
        self.assertIsNone(err)
        self.assertEqual(ver, '85')
        err, ver = m.versionOrError('../../etc')
        self.assertIsNotNone(err)
        self.assertIsNone(ver)
        self.assertFalse(json.loads(err)['status'])
        self.assertIn('PHP版本参数不合法!', json.loads(err)['msg'])

    def test_03_pool_whitelist(self):
        m = self.fx.mod
        self.assertTrue(m.isPhpPool('www'))
        self.assertTrue(m.isPhpPool('backup'))
        for bad in ('../../evil', 'a/b', '', None, 'www.conf', 'a b', 'x' * 33):
            self.assertFalse(m.isPhpPool(bad), bad)

    def test_04_status_rejects_traversal_version(self):
        self.assertEqual(self.fx.mod.status('../../etc'), 'ERROR: PHP版本参数不合法')
        self.assertEqual(self.fx.shells, [])
        self.assertEqual(self.fx.shellrc, [])

    def test_05_conf_traversal_creates_nothing(self):
        target = os.path.join(self.fx.root, 'tmp', 'evil')
        ver = os.path.relpath(target, os.path.join(self.fx.server, 'php'))
        self.fx.mod.getConf(ver)
        self.assertFalse(os.path.exists(os.path.join(target, 'etc', 'php.ini')))

    def test_06_conf_path_returns_for_installed(self):
        self.assertEqual(os.path.normpath(self.fx.mod.getConf(VERSION)),
                         os.path.normpath(os.path.join(self.fx.server, 'php', VERSION,
                                                       'etc', 'php.ini')))

    def test_07_fpm_conf_pool_traversal_no_write(self):
        m = self.fx.mod
        orig = m.getArgs
        m.getArgs = lambda: {'pool': '../../../evil'}
        try:
            out = m.getFpmConfig(VERSION)
        finally:
            m.getArgs = orig
        self.assertFalse(json.loads(out)['status'])
        self.assertIn('FPM池名不合法!', json.loads(out)['msg'])
        self.assertFalse(os.path.exists(os.path.join(self.fx.server, 'php', 'evil.conf')))

    def test_08_set_fpm_conf_pool_traversal_no_write(self):
        self.fx.set_args({'version': VERSION, 'pool': '../../evil', 'max_children': '30',
                          'start_servers': '5', 'min_spare_servers': '5',
                          'max_spare_servers': '20', 'pm': 'dynamic'})
        out = json.loads(self.fx.call('setFpmConfig', VERSION))
        self.assertFalse(out['status'])
        self.assertFalse(os.path.exists(os.path.join(self.fx.server, 'php', 'evil.conf')))
        self.assertFalse(os.path.exists(
            os.path.join(self.fx.server, 'php', VERSION, 'evil.conf')))


class TestPhpIniWrites(_FixtureCase):

    def ini(self):
        return self.fx.read(os.path.join('php', VERSION, 'etc', 'php.ini'))

    def test_10_submit_injection_rejected(self):
        self.fx.set_args({'date.timezone': 'PRC\nINVALID_DIRECTIVE = 1'})
        out = json.loads(self.fx.call('submitPhpConf', VERSION))
        self.assertFalse(out['status'])
        self.assertIn('参数值不合法!', out['msg'])
        self.assertNotIn('INVALID_DIRECTIVE', self.ini())

    def test_11_submit_backslash_value_rejected(self):
        self.fx.set_args({'error_reporting': 'E_ALL \\1'})
        out = json.loads(self.fx.call('submitPhpConf', VERSION))
        self.assertFalse(out['status'])

    def test_12_submit_commented_key_becomes_effective(self):
        self.fx.set_args({'date.timezone': 'UTC'})
        out = json.loads(self.fx.call('submitPhpConf', VERSION))
        self.assertTrue(out['status'])
        self.assertIn('\ndate.timezone = UTC', '\n' + self.ini())
        self.assertNotIn(';date.timezone = UTC', self.ini())

    def test_13_submit_valid_values(self):
        self.fx.set_args({'memory_limit': '256M', 'display_errors': 'On'})
        out = json.loads(self.fx.call('submitPhpConf', VERSION))
        self.assertTrue(out['status'])
        self.assertIn('memory_limit = 256M', self.ini())
        self.assertIn('display_errors = On', self.ini())
        self.assertTrue(any('systemctl reload php%s' % VERSION in str(s)
                            for s in self.fx.shells))

    def test_14_submit_empty_args_rejected(self):
        self.fx.set_args({})
        out = json.loads(self.fx.call('submitPhpConf', VERSION))
        self.assertFalse(out['status'])
        self.assertIn('没有需要保存的配置项!', out['msg'])

    def test_15_submit_readfile_false_guard(self):
        """php.ini 读不到时必须如实报错，而不是把整份配置覆写成空"""
        m = self.fx.mod
        ini_path = os.path.join(self.fx.server, 'php', VERSION, 'etc', 'php.ini')
        saved = self.fx.yf.readFile
        self.fx.yf.readFile = lambda p: False
        try:
            self.fx.set_args({'memory_limit': '256M'})
            out = json.loads(m.submitPhpConf(VERSION))
        finally:
            self.fx.yf.readFile = saved
        self.assertFalse(out['status'])
        self.assertIn('读取 PHP 配置文件失败', out['msg'])
        self.assertTrue(os.path.getsize(ini_path) > 100)

    def test_16_disable_func_injection_rejected(self):
        self.fx.set_args({'disable_functions': 'exec\nINVALID_DIRECTIVE = 1'})
        out = json.loads(self.fx.call('setDisableFunc', VERSION))
        self.assertFalse(out['status'])
        self.assertIn('禁用函数格式不合法!', out['msg'])
        self.assertNotIn('INVALID_DIRECTIVE', self.ini())

    def test_17_disable_func_valid(self):
        self.fx.set_args({'disable_functions': 'exec,system,passthru'})
        out = json.loads(self.fx.call('setDisableFunc', VERSION))
        self.assertTrue(out['status'])
        self.assertIn('disable_functions = exec,system,passthru', self.ini())

    def test_18_disable_func_readfile_false_no_data_loss(self):
        m = self.fx.mod
        ini_path = os.path.join(self.fx.server, 'php', VERSION, 'etc', 'php.ini')
        size = os.path.getsize(ini_path)
        saved = self.fx.yf.readFile
        self.fx.yf.readFile = lambda p: False
        try:
            self.fx.set_args({'disable_functions': 'exec'})
            out = json.loads(m.setDisableFunc(VERSION))
        finally:
            self.fx.yf.readFile = saved
        self.assertFalse(out['status'])
        self.assertEqual(os.path.getsize(ini_path), size)

    def test_19_session_missing_args_envelope(self):
        self.fx.set_args({})
        out = json.loads(self.fx.call('setSessionConf', VERSION))
        self.assertFalse(out['status'])
        self.assertIn('缺少必要参数: ip', out['msg'])

    def test_20_session_handler_whitelist(self):
        self.fx.set_args({'ip': '127.0.0.1', 'port': '6379', 'passwd': '',
                          'save_handler': 'evil_handler'})
        out = json.loads(self.fx.call('setSessionConf', VERSION))
        self.assertFalse(out['status'])
        self.assertIn('Session存储方式不合法!', out['msg'])
        self.assertNotIn('evil_handler', self.ini())

    def test_21_session_ip_anchored_validation(self):
        for ip in ('1.2.3.4evil', '1.2.3.4\nINVALID_DIRECTIVE = 1', '1.2.3', '1.2.3.4.5',
                   '999.1.1.1'):
            self.fx.set_args({'ip': ip, 'port': '6379', 'passwd': '',
                              'save_handler': 'redis'})
            out = json.loads(self.fx.call('setSessionConf', VERSION))
            self.assertFalse(out['status'], ip)
            self.assertNotIn('INVALID_DIRECTIVE', self.ini())

    def test_22_session_files_valid(self):
        self.fx.set_args({'ip': '', 'port': '', 'passwd': '', 'save_handler': 'files'})
        out = json.loads(self.fx.call('setSessionConf', VERSION))
        self.assertTrue(out['status'])
        self.assertIn('session.save_handler = files', self.ini())

    def test_23_validate_ini_value_rules(self):
        m = self.fx.mod
        for key, val in (('memory_limit', '256M'), ('display_errors', 'On'),
                         ('max_execution_time', '300'), ('date.timezone', 'Asia/Shanghai'),
                         ('error_reporting', 'E_ALL & ~E_NOTICE')):
            err, out = m.validateIniValue(key, val)
            self.assertEqual(err, '', '%s=%s' % (key, val))
            self.assertEqual(out, val)
        for key, val in (('memory_limit', '50M\nINVALID_DIRECTIVE = 1'),
                         ('display_errors', 'On;evil'), ('max_execution_time', 'abc'),
                         ('date.timezone', 'PRC"'), ('post_max_size', '50M\nINVALID = 1')):
            err, out = m.validateIniValue(key, val)
            self.assertEqual(err, '参数值不合法!', '%s=%s' % (key, val))
            self.assertIsNone(out)
        # 尾随空白被 strip 后合法（不构成注入面）
        err, out = m.validateIniValue('post_max_size', '50M\n')
        self.assertEqual((err, out), ('', '50M'))


class TestFpmConfAndRollback(_FixtureCase):

    def www(self):
        return self.fx.read(os.path.join('php', VERSION, 'etc', 'php-fpm.d', 'www.conf'))

    def test_30_set_fpm_bad_numbers_rejected(self):
        for bad in ('abc', '0', '-5', '99999999', ''):
            self.fx.set_args({'version': VERSION, 'pool': 'www', 'max_children': bad,
                              'start_servers': '5', 'min_spare_servers': '5',
                              'max_spare_servers': '20', 'pm': 'dynamic'})
            out = json.loads(self.fx.call('setFpmConfig', VERSION))
            self.assertFalse(out['status'], bad)

    def test_31_set_fpm_pm_injection_rejected(self):
        self.fx.set_args({'version': VERSION, 'pool': 'www', 'max_children': '30',
                          'start_servers': '5', 'min_spare_servers': '5',
                          'max_spare_servers': '20',
                          'pm': 'dynamic\nINVALID_DIRECTIVE = 1'})
        out = json.loads(self.fx.call('setFpmConfig', VERSION))
        self.assertFalse(out['status'])
        self.assertIn('运行模式不合法!', out['msg'])
        self.assertNotIn('INVALID_DIRECTIVE', self.www())

    def test_32_set_fpm_cross_field_constraints(self):
        self.fx.set_args({'version': VERSION, 'pool': 'www', 'max_children': '5',
                          'start_servers': '30', 'min_spare_servers': '5',
                          'max_spare_servers': '20', 'pm': 'dynamic'})
        out = json.loads(self.fx.call('setFpmConfig', VERSION))
        self.assertFalse(out['status'])

    def test_33_set_fpm_valid_runs_syntax_check(self):
        self.fx.set_args({'version': VERSION, 'pool': 'www', 'max_children': '60',
                          'start_servers': '6', 'min_spare_servers': '6',
                          'max_spare_servers': '30', 'pm': 'dynamic'})
        out = json.loads(self.fx.call('setFpmConfig', VERSION))
        self.assertTrue(out['status'])
        self.assertIn('pm.max_children = 60', self.www())
        self.assertTrue(any(isinstance(c, (list, tuple)) and '-t' in c
                            for c in self.fx.shellrc))

    def test_33b_success_path_formats_log_message(self):
        """真机实测踩过：yf.getInfo 的格式化参数必须是 str，传 int 会在写盘后抛 TypeError
        （用户看到失败、但配置已经改了）。这里用真实 getInfo 跑成功路径。"""
        self.fx.set_args({'version': VERSION, 'pool': 'www', 'max_children': '50',
                          'start_servers': '10', 'min_spare_servers': '10',
                          'max_spare_servers': '30', 'pm': 'dynamic'})
        out = json.loads(self.fx.call('setFpmConfig', VERSION))
        self.assertTrue(out['status'])
        self.fx.set_args({'max': '64'})
        out = json.loads(self.fx.call('setMaxSize', VERSION))
        self.assertTrue(out['status'])
        self.fx.set_args({'time': '120'})
        out = json.loads(self.fx.call('setMaxTime', VERSION))
        self.assertTrue(out['status'])

    def test_34_syntax_check_failure_rolls_back(self):
        m = self.fx.mod
        path = os.path.join(self.fx.server, 'php', VERSION, 'etc', 'php-fpm.d', 'www.conf')
        origin = _read(path)
        ok = m._applyFpmConf(VERSION, path, origin + '\nINVALID_DIRECTIVE = 1\n')
        self.assertFalse(ok)
        self.assertEqual(_read(path), origin)

    def test_35_php_fpm_t_check_helper(self):
        m = self.fx.mod
        path = os.path.join(self.fx.server, 'php', VERSION, 'etc', 'php-fpm.d', 'www.conf')
        origin = _read(path)
        _write(path, origin + '\nINVALID_DIRECTIVE = 1\n')
        ok, msg = m.checkFpmConf(VERSION)
        self.assertFalse(ok)
        self.assertIn('syntax error', msg)
        _write(path, origin)
        ok, msg = m.checkFpmConf(VERSION)
        self.assertTrue(ok)

    def test_36_set_max_time_bad_input(self):
        for bad in ('abc', '10', '0', '-1', '999999'):
            self.fx.set_args({'time': bad})
            out = json.loads(self.fx.call('setMaxTime', VERSION))
            self.assertFalse(out['status'], bad)
        self.fx.set_args({})
        out = json.loads(self.fx.call('setMaxTime', VERSION))
        self.assertFalse(out['status'])

    def test_37_set_max_time_valid_applies_and_reloads(self):
        self.fx.set_args({'time': '45'})
        out = json.loads(self.fx.call('setMaxTime', VERSION))
        self.assertTrue(out['status'])
        self.assertIn('request_terminate_timeout = 45', self.www())
        self.assertIn('max_execution_time = 45',
                      self.fx.read(os.path.join('php', VERSION, 'etc', 'php.ini')))
        self.assertTrue(any('systemctl reload php%s' % VERSION in str(s)
                            for s in self.fx.shells))

    def test_38_set_max_size_bad_input(self):
        for bad in ('abc', '1', '0', '99999999', '-3'):
            self.fx.set_args({'max': bad})
            out = json.loads(self.fx.call('setMaxSize', VERSION))
            self.assertFalse(out['status'], bad)

    def test_39_set_max_size_valid(self):
        self.fx.set_args({'max': '60'})
        out = json.loads(self.fx.call('setMaxSize', VERSION))
        self.assertTrue(out['status'])
        ini = self.fx.read(os.path.join('php', VERSION, 'etc', 'php.ini'))
        self.assertIn('upload_max_filesize = 60M', ini)
        self.assertIn('post_max_size = 60M', ini)

class TestFpmAddressAndStatus(_FixtureCase):

    def test_40_get_fpm_address_tcp(self):
        m = self.fx.mod
        orig = m.getArgs
        m.getArgs = lambda: {'pool': 'tcp'}
        try:
            self.assertEqual(m.getFpmAddress(VERSION), ('127.0.0.1', 9000))
        finally:
            m.getArgs = orig

    def test_41_get_fpm_address_custom_socket(self):
        m = self.fx.mod
        orig = m.getArgs
        m.getArgs = lambda: {'pool': 'custom'}
        try:
            self.assertEqual(m.getFpmAddress(VERSION), '/run/php-fpm-85-custom.sock')
        finally:
            m.getArgs = orig

    def test_42_get_fpm_address_default_socket(self):
        m = self.fx.mod
        orig = m.getArgs
        m.getArgs = lambda: {}
        try:
            self.assertEqual(m.getFpmAddress(VERSION), '/tmp/php-cgi-85.sock')
        finally:
            m.getArgs = orig

    def test_43_find_master_ignores_decoy_python(self):
        self.stub_procs([('111', 'python3',
                          'php-fpm: master process (%s/php/%s/etc/php-fpm.conf)'
                          % (self.fx.server, VERSION))])
        try:
            self.assertEqual(self.fx.mod.status(VERSION), 'stop')
        finally:
            self.restore_procs()

    def test_44_find_master_detects_real_process(self):
        self.stub_procs([('222', 'php-fpm',
                          'php-fpm: master process (%s/php/%s/etc/php-fpm.conf)'
                          % (self.fx.server, VERSION))])
        try:
            self.assertEqual(self.fx.mod.status(VERSION), 'start')
        finally:
            self.restore_procs()

    def test_45_find_master_ignores_other_distro_version(self):
        """系统包安装的 php-fpm8.3（comm 带版本）不得被算成本插件的 83"""
        self.stub_procs([('333', 'php-fpm8.3',
                          'php-fpm: master process (/etc/php/8.3/fpm/php-fpm.conf)')])
        try:
            self.assertEqual(self.fx.mod.status('83'), 'stop')
        finally:
            self.restore_procs()

    def test_46_stale_pid_not_start(self):
        pid_file = os.path.join(self.fx.server, 'php', VERSION, 'var', 'run',
                                'php-fpm.pid')
        _write(pid_file, '1\n')
        self.stub_procs([])
        self.stub_proc_info('systemd', '/sbin/init')
        saved = self.fx.yf.checkPid
        self.fx.yf.checkPid = lambda pid: True
        try:
            self.assertEqual(self.fx.mod.status(VERSION), 'stop')
        finally:
            self.fx.yf.checkPid = saved
            self.restore_procs()
            self.restore_proc_info()

    def test_47_fpm_status_conn_failure_envelope(self):
        self.fx.fcgi_ok = False
        self.stub_procs([('222', 'php-fpm',
                          'php-fpm: master process (%s/php/%s/etc/php-fpm.conf)'
                          % (self.fx.server, VERSION))])
        try:
            out = json.loads(self.fx.call('getFpmStatus', VERSION))
        finally:
            self.restore_procs()
        self.assertFalse(out['status'])
        self.assertIn('获取状态失败, 返回内容异常', out['msg'])

    def test_48_fpm_status_ok(self):
        self.fx.fcgi_ok = True
        self.stub_procs([('222', 'php-fpm',
                          'php-fpm: master process (%s/php/%s/etc/php-fpm.conf)'
                          % (self.fx.server, VERSION))])
        try:
            out = json.loads(self.fx.call('getFpmStatus', VERSION))
        finally:
            self.restore_procs()
        self.assertTrue(out['status'])
        self.assertIn('start time', out['data'])

    def test_49_phpinfo_conn_failure_no_traceback(self):
        self.fx.fcgi_ok = False
        self.stub_procs([('222', 'php-fpm',
                          'php-fpm: master process (%s/php/%s/etc/php-fpm.conf)'
                          % (self.fx.server, VERSION))])
        try:
            out = self.fx.call('getPhpinfo', VERSION)
        finally:
            self.restore_procs()
        self.assertIsInstance(out, str)
        self.assertIn('phpinfo 获取失败', out)

    def test_50_get_phpinfo_validates_version(self):
        out = json.loads(self.fx.call('getPhpinfo', '../../etc'))
        self.assertFalse(out['status'])
        self.assertIn('PHP版本参数不合法!', out['msg'])


class TestNotInstalledNoArtifacts(_FixtureCase):

    def artifacts(self):
        return [
            os.path.join(self.fx.server, 'php', NOT_INSTALLED, 'etc', 'php.ini'),
            os.path.join(self.fx.server, 'php', NOT_INSTALLED, 'etc', 'php-fpm.conf'),
            os.path.join(self.fx.server, 'php', 'init.d', 'php' + NOT_INSTALLED),
            os.path.join(self.fx.systemd, 'php%s.service' % NOT_INSTALLED),
        ]

    def test_60_start_uninstalled_refused(self):
        out = self.fx.call('start', NOT_INSTALLED)
        self.assertIn('未安装', out)
        for path in self.artifacts():
            self.assertFalse(os.path.exists(path), path)

    def test_61_restart_reload_stop_uninstalled_refused(self):
        for fn in ('restart', 'reload', 'stop'):
            out = getattr(self.fx.mod, fn)(NOT_INSTALLED)
            self.assertIn('未安装', out, fn)
        for path in self.artifacts():
            self.assertFalse(os.path.exists(path), path)

    def test_62_self_healing_skips_uninstalled(self):
        out = json.loads(self.fx.call('upgradeSelfHealing', NOT_INSTALLED))
        self.assertFalse(out['status'])
        self.assertEqual(out['data']['skipped'], [NOT_INSTALLED])
        self.assertFalse(os.path.exists(self.artifacts()[0]))
        self.assertTrue(any('未安装，跳过环境自愈' in ln for ln in out['msg'].split('\n')))

    def test_63_self_healing_rejects_bad_version(self):
        out = json.loads(self.fx.call('upgradeSelfHealing', '../../etc'))
        self.assertFalse(out['status'])

    def test_64_initd_install_uninstall_honest(self):
        for fn in ('initdInstall', 'initdUinstall'):
            out = getattr(self.fx.mod, fn)(NOT_INSTALLED)
            self.assertIn('未安装', out, fn)
        self.assertFalse(any('systemctl enable' in str(s) for s in self.fx.shellrc))
        self.assertFalse(any('systemctl disable' in str(s) for s in self.fx.shellrc))

    def test_65_initd_status_uses_is_enabled(self):
        self.fx.rc = (0, 'enabled\n', '')
        self.assertEqual(self.fx.mod.initdStatus(VERSION), 'ok')
        self.assertTrue(any('is-enabled' in str(c) for c in self.fx.shellrc))
        self.fx.rc = (1, '', 'Failed to get unit file state')
        self.assertEqual(self.fx.mod.initdStatus(VERSION), 'fail')

    def test_66_kill_all_php_exact_comm_only(self):
        self.fx.call('killAllPhp', VERSION)
        joined = ' '.join(str(s) for s in self.fx.shellrc)
        self.assertIn('pkill -9 -x php-fpm', joined)
        self.assertNotIn('pkill -9 -f php-fpm', joined)


class TestLibAndSessionMisc(_FixtureCase):

    def test_70_install_lib_injection_rejected(self):
        for bad in ('x; touch /tmp/yf_c07_pwn', 'notalib', '../../evil', 'x y'):
            self.fx.set_args({'name': bad})
            out = json.loads(self.fx.call('installLib', VERSION))
            self.assertFalse(out['status'], bad)
            self.assertIn('扩展名称不合法!', out['msg'])
            self.assertEqual(self.fx.tasks, [], bad)

    def test_71_uninstall_lib_injection_rejected(self):
        for bad in ('x; touch /tmp/yf_c07_pwn', 'notalib'):
            self.fx.set_args({'name': bad})
            out = json.loads(self.fx.call('uninstallLib', VERSION))
            self.assertFalse(out['status'], bad)
            self.assertEqual(self.fx.shellrc, [], bad)
            self.assertEqual(self.fx.shells, [], bad)

    def test_72_install_lib_valid_task_quoted(self):
        self.fx.set_args({'name': 'sg11'})
        out = json.loads(self.fx.call('installLib', VERSION))
        self.assertTrue(out['status'])
        self.assertEqual(len(self.fx.tasks), 1)
        self.assertIn('install sg11', self.fx.tasks[0]['cmd'])
        self.assertIn("'", self.fx.tasks[0]['cmd'])   # 路径已 shlexQuote

    def test_73_uninstall_lib_no_such_extension_not_success(self):
        self.fx.rc = (0, 'no such extension\n', '')
        self.fx.set_args({'name': 'sg11'})
        out = json.loads(self.fx.call('uninstallLib', VERSION))
        self.assertFalse(out['status'])

    def test_74_lib_conf_uninstalled_envelope(self):
        out = json.loads(self.fx.call('get_lib_conf', {'version': NOT_INSTALLED}))
        self.assertFalse(out['status'])
        self.assertIsInstance(out['msg'], str)

    def test_75_session_count_shell_output_guard(self):
        self.fx.yf.execShell = lambda cmd, cwd=None, timeout=None, shell=True: ('', '')
        try:
            data = self.fx.mod.getSessionCount_Origin(VERSION)
        finally:
            self.fx.yf.execShell = self.fx._exec_shell
        self.assertEqual(data, {'total': 0, 'oldfile': 0})

    def test_76_session_find_narrowed(self):
        self.fx.mod.getSessionCount_Origin(VERSION)
        tmp_cmds = [str(s) for s in self.fx.shells if 'find /tmp' in str(s)]
        self.assertTrue(tmp_cmds)
        for cmd in tmp_cmds:
            self.assertIn('-maxdepth 2', cmd)
            self.assertIn("-name 'sess_*'", cmd)
        self.fx.shells[:] = []
        self.fx.mod.cleanSessionOld(VERSION)
        clean_cmds = [str(s) for s in self.fx.shells if 'rm -f' in str(s)]
        self.assertTrue(clean_cmds)
        for cmd in clean_cmds:
            self.assertIn('-maxdepth 2', cmd)
            self.assertIn("-name 'sess_*'", cmd)
            self.assertIn('xargs -0 -r rm -f', cmd)

    def test_77_clean_session_old_reports_failure(self):
        self.fx.yf.execShell = lambda cmd, cwd=None, timeout=None, shell=True: ('1\n', '')
        saved = self.fx.mod.getSessionCount_Origin
        self.fx.mod.getSessionCount_Origin = lambda v: {'total': 1, 'oldfile': 1}
        try:
            out = json.loads(self.fx.mod.cleanSessionOld(VERSION))
        finally:
            self.fx.mod.getSessionCount_Origin = saved
            self.fx.yf.execShell = self.fx._exec_shell
        self.assertFalse(out['status'])
        self.assertIn('清理失败', out['msg'])

    def test_78_get_args_never_raises(self):
        m = self.fx.mod
        for argv in ([VERSION, 'foo'], [VERSION, '[1,2]'], [VERSION, ''],
                     [VERSION, '{"a":"1"}'], [VERSION, 'a:b'],
                     [VERSION, 'a:b', 'c:d', 'noColon']):
            sys.argv = [IDX, 'func'] + argv
            out = m.getArgs()
            self.assertIsInstance(out, dict, argv)
        sys.argv = [IDX, 'func', VERSION, '{"a":"1"}']
        self.assertEqual(m.getArgs(), {'a': '1'})
        sys.argv = [IDX, 'func', VERSION, 'a:b']
        self.assertEqual(m.getArgs(), {'a': 'b'})

    def test_79_check_args_non_dict(self):
        out = json.loads(self.fx.mod.checkArgs(['x'], ['name'])[1])
        self.assertFalse(out['status'])
        self.assertIn('参数格式错误!', out['msg'])

    def test_80_upgrade_version_file_garbage_and_latest(self):
        m = self.fx.mod
        vf = os.path.join(self.fx.root, 'plugin_version.pl')
        _write(vf, '2.0')
        self.assertIn('已是最新版本', json.loads(m.checkPluginUpgrade(VERSION))['msg'])
        _write(vf, '1.0')
        out = json.loads(m.checkPluginUpgrade(VERSION))
        self.assertTrue(out['status'])
        self.assertEqual(_read(vf), '2.0')
        os.remove(vf)
        out = json.loads(m.checkPluginUpgrade(VERSION))
        self.assertTrue(out['status'])
        self.assertEqual(_read(vf), '2.0')


# ---------------------------------------------------------------------------
# 结构断言（AST，抗注释 / if False 蒙混）
# ---------------------------------------------------------------------------

class TestPhpStructure(unittest.TestCase):

    def setUp(self):
        self.tree = _tree(IDX)

    def test_90_guards_exist(self):
        for name in ('isPhpVersion', 'isPhpPool', 'isIpv4', 'versionOrError', 'versionOrFail',
                     'getVersionDir', 'isInstalled', 'validateIniValue', 'setIniKey',
                     'checkFpmConf', '_applyFpmConf', '_iterProcesses', '_findFpmMaster',
                     '_pidIsFpmMaster', '_intShell', 'getLibNames', 'isLibName'):
            self.assertIsNotNone(_func(self.tree, name), name)

    def test_91_status_has_no_shell_process_match(self):
        node = _func(self.tree, 'status')
        code = _code_only(node)
        self.assertNotIn('ps aux', code)
        self.assertNotIn('grep', code)
        self.assertTrue(_calls_any(node, ['_findFpmMaster']))

    def test_92_find_master_uses_proc_comm(self):
        node = _func(self.tree, '_findFpmMaster')
        self.assertIn("comm != 'php-fpm'", _read(IDX))
        self.assertTrue(_calls_any(node, ['_iterProcesses']))

    def test_93_make_php_ini_refuses_uninstalled(self):
        self.assertTrue(_calls_any(_func(self.tree, 'makePhpIni'), ['isInstalled']))

    def test_94_php_op_refuses_uninstalled(self):
        self.assertTrue(_calls_any(_func(self.tree, 'phpOp'), ['isInstalled']))

    def test_95_initd_uses_rc(self):
        for name in ('initdInstall', 'initdUinstall', 'initdStatus'):
            self.assertTrue(_calls_any(_func(self.tree, name), ['execShellRc']), name)
        self.assertIn('is-enabled', _read(IDX))

    def test_96_fpm_address_no_undefined_bind(self):
        node = _func(self.tree, 'getFpmAddress')
        code = _code_only(node)
        self.assertNotIn("'bind'", code)
        self.assertNotIn('if bind:', code)
        self.assertNotIn('bind', {n.id for n in ast.walk(node) if isinstance(n, ast.Name)})

    def test_97_no_raw_shell_concat_of_user_values(self):
        """install_lib/uninstall_lib 的命令必须走 shlexQuote，且扩展名先过白名单"""
        src = _read(IDX)
        for name in ('installLib', 'uninstallLib'):
            node = _func(self.tree, name)
            self.assertTrue(_calls_any(node, ['shlexQuote']), name)
            self.assertTrue(_calls_any(node, ['isLibName']), name)
        self.assertIn("yf.shlexQuote(getPluginDir() + \"/versions\")", src)

    def test_98_ini_writes_go_through_setIniKey(self):
        for name in ('submitPhpConf', 'resetPhpConf', 'setDisableFunc', 'setSessionConf',
                     'setMaxSize', 'setMaxTime'):
            self.assertTrue(_calls_any(_func(self.tree, name), ['setIniKey']), name)

    def test_99_fpm_writes_go_through_apply(self):
        for name in ('setFpmConfig', 'setMaxTime'):
            self.assertTrue(_calls_any(_func(self.tree, name), ['_applyFpmConf']), name)

    def test_100_kill_all_php_exact(self):
        node = _func(self.tree, 'killAllPhp')
        code = _code_only(node)
        self.assertIn('pkill -9 -x php-fpm', code)
        self.assertNotIn('pkill -9 -f php-fpm', code)

    def test_101_version_guard_on_json_entrypoints(self):
        for name in ('setFpmConfig', 'setMaxTime', 'setMaxSize', 'setSessionConf',
                     'submitPhpConf', 'resetPhpConf', 'setDisableFunc', 'getDisableFunc',
                     'getPhpinfo', 'installLib', 'uninstallLib', 'getFpmStatus',
                     'tunePhpConfig', 'getFpmConfig'):
            self.assertTrue(_calls_any(_func(self.tree, name),
                                       ['versionOrError', 'isPhpVersion']), name)

    def test_102_index_php_guards(self):
        tree = _tree(IDX_PHP)
        node = _func(tree, 'libConfCommon')
        self.assertTrue(_calls_any(node, ['isdir']))
        src = _read(IDX_PHP)
        self.assertIn("if not phpini or isinstance(phpini, bool):", src)
        self.assertIn('requestFcgiPHP', src)
        self.assertIn("isinstance(sock_data, (bytes, bytearray))", src)


# ---------------------------------------------------------------------------
# 前端断言（去注释后的源码）
# ---------------------------------------------------------------------------

class TestPhpFrontend(unittest.TestCase):

    def setUp(self):
        self.src = _strip_js_comments(_read(JS))

    def test_110_all_ajax_have_fail(self):
        ajax = len(re.findall(r'\$\.post\(', self.src))
        fail = len(re.findall(r'\.fail\(', self.src))
        self.assertGreaterEqual(ajax, 3)
        self.assertEqual(ajax, fail, 'ajax=%d fail=%d' % (ajax, fail))

    def test_111_esc_helpers_defined(self):
        self.assertIn('function phpEsc(', self.src)
        self.assertIn('function phpInner(', self.src)

    def test_112_no_raw_json_parse_of_plugin_data(self):
        self.assertNotIn('JSON.parse(ret_data.data)', self.src)
        self.assertNotIn('JSON.parse(rdata.data)', self.src)
        # 只允许两处：phpInner 封装自身 + phpFpmConfigFile 的 try/catch 兼容分支
        self.assertLessEqual(self.src.count('JSON.parse(data.data)'), 2)
        self.assertIn('return JSON.parse(data.data);', self.src)

    def test_113_phpinfo_uses_data_msg(self):
        self.assertNotIn('layer.msg(rdata.msg, { icon: 2 })', self.src)

    def test_114_dynamic_values_escaped(self):
        for marker in ('phpEsc(rdata[i].value)', 'phpEsc(rdata[i].name)',
                       'phpEsc(rdata.pool)', 'phpEsc(rdata.passwd)',
                       'phpEsc(disable_functions[i])', 'phpEsc(libs[i].name)'):
            self.assertIn(marker, self.src, marker)

    def test_115_inner_status_guards(self):
        self.assertGreaterEqual(self.src.count('phpInner('), 12)


# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

class TestPhpI18n(unittest.TestCase):

    def test_120_new_keys_in_all_langs(self):
        key_sets = {}
        for lang in LANGS:
            path = os.path.join(LANGDIR, '%s.json' % lang)
            with io.open(path, encoding='utf-8') as fh:
                data = json.load(fh)
            key_sets[lang] = set(data)
            for key in NEW_MSG_KEYS:
                self.assertIn(key, data, '%s 缺键 %r' % (lang, key))
                self.assertTrue(data[key].strip(), '%s 键 %r 译文为空' % (lang, key))
        base = key_sets[LANGS[0]]
        for lang in LANGS[1:]:
            self.assertEqual(key_sets[lang], base, '%s 键集与 zh-CN 不一致' % lang)

    def test_121_foreign_langs_have_no_cjk(self):
        for lang in ('en', 'de', 'fr', 'it'):
            with io.open(os.path.join(LANGDIR, '%s.json' % lang),
                         encoding='utf-8') as fh:
                data = json.load(fh)
            for key in NEW_MSG_KEYS:
                self.assertIsNone(CJK_RE.search(data[key]),
                                  '%s 的 %r 译文含中文: %r' % (lang, key, data[key]))

    def test_122_backend_messages_resolve_to_keys(self):
        """index.py 里 returnJson 的中文字面量必须能在语言包里查到（含冒号前缀契约）"""
        src = _read(IDX)
        with io.open(os.path.join(LANGDIR, 'zh-CN.json'), encoding='utf-8') as fh:
            keys = set(json.load(fh))

        def resolves(lit):
            if lit in keys:
                return True
            for sep in (':', '：'):
                idx = lit.find(sep)
                if 0 < idx <= 40 and lit[:idx + 1] in keys:
                    return True
            return False

        for lit in re.findall(r"returnJson\(\s*(?:False|True)\s*,\s*'([^']*[\u4e00-\u9fff][^']*)'",
                              src):
            self.assertTrue(resolves(lit), '语言包缺键: %r' % lit)


if __name__ == '__main__':
    unittest.main()
