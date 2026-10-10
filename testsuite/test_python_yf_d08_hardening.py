# coding: utf-8
r"""D08 python_yf 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/python_yf/`（`index.py`、`index.html`、`install.sh`、`lang/*.json`）。
里程碑契约 = **只动 uv 自己管理的解释器与用户明确创建的项目目录，任何越界/失败都必须如实报错**。

真机实测（Debian 12，`uv 0.12.0`，面板 gunicorn gthread 2 worker/4 threads）与本文件
夹具真跑共同暴露的缺陷：

  * **命令注入（P0，root RCE）**：`version` / `path` 直接 f-string 拼进 `yf.execShell`：
    `install_python version='3.9.25; touch /tmp/PWN1; #'`、`uninstall_python` 同款、
    `create_venv version='cpython-3.14.6-linux-x86_64-gnu; touch /tmp/PWN3; #'`
    三次真机实测都在面板 root 下造出了文件（PWN1/PWN2/PWN3）。
    → new：`TARGET_RE` 白名单 + `_run_uv()` 逐参 `yf.shlexQuote`。
  * **-- 选项注入**：`uninstall_python version='--help'` 让 uv 当成参数解析并回「卸载成功」
    → new：白名单先于任何调用。
  * **假成功（P0）**：`install/uninstall/create/remove` 只判输出里有没有 "error"：
    uv 缺失（`~/.local/bin/uv` 不存在）时 install 回「安装任务已提交」、uninstall 回
    「卸载成功」（真机实测）；`remove_venv` 在目录没被删掉时照样回「删除成功」。
    → new：`execShellRc` 判退出码 + 回读列表/目录二次确认。
  * **无超时**：所有 uv 调用 `timeout=None`，下载悬挂会永久占用 gthread 线程。
    → new：显式 120s / 900s。
  * **任意目录写（越界）**：`create_venv path='/www/server/yufeng_panel'`（面板安装目录本身）
    与 `path='/www/server/python_yf'` 真机实测都成功落盘 `.venv`，且 `path='..'` 未归一化
    （落点与登记值不一致）→ new：`_safe_dir()` 绝对路径 + 无 `..` + 面板/系统目录黑名单 + 目录存在。
    另：根目录判据 `realpath(sep).rstrip('/\\')` 在 Linux/Windows 上都恒假（死代码），
    `path='/'` 会落到 `/.venv` —— 变异测试（屏蔽平台判据后）实测发现，已修为显式比根。
  * **venvs.json 读侧崩溃**：被写成 `[]` 时 `get_venvs().get()` 抛 AttributeError，真机
    `/plugins/run` 直接把 traceback 当 msg 返回；值为字符串时前端拿到 `"notalist".length`。
    → new：`_normalize_venvs()` 归一（非法结构丢弃）。
  * **并发丢登记**：4 个并发 `create_venv` 真机实测只登记了 1 个（读-改-写非原子），
    另外 3 个虚拟环境变成界面永远删不掉的孤儿 → new：`_venv_file_lock()`（flock 目
    录 + 进程内锁）包裹读改写。
  * **系统解释器可被卸载**：`uninstall_python` 没有任何归属判断，`/usr/bin/python3.11`
    这类系统解释器只要有版本号就能落到 `uv python uninstall` → new：只允许卸载
    落在 `~/.local/share/uv/python` 下的解释器，其余一律拒绝。
  * **状态判据脆弱**：`get_python_list` 用文本表格「最后一列是否以 / 开头」判已安装
    （uv 在 TTY 下会把路径缩写成 `~/.local/...`）→ new：改读
    `uv python list --output-format json`，`managed` 由 realpath 与 uv 目录比对得出。
  * **前端**：`request()` 无 `.fail()`（HTTP 500 时 loading 遮罩永久卡死）；venv 路径/
    版本标识未转义直接拼进 innerHTML 与行内 `onclick`（路径来自用户输入并落进
    venvs.json，构成存储型 XSS）→ new：`pyEsc`/`pyJsArg` 覆盖全部回显点 + `.fail()`。
  * **install.sh**：只看 `-f` 存在，uv 存在但不可执行时面板会当成「已安装」→ 加 `-x` 复核。

断言策略：全部真跑 —— 把被测源码以**桩 `core.yf`** exec 进命名空间（记录型 `execShellRc`），
再用 AST 断言「修复必须存在于源码里」（注释与 `if False:` 蒙混不过去）。

变异自证：`test/_d08_mutation.py`（逐条回退修复 → 本文件必须变红）。
"""
import ast
import json
import os
import re
import shlex
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_SRC = os.environ.get('YF_D08_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'python_yf')

IDX = os.path.join(PLUGIN_SRC, 'index.py')
HTML = os.path.join(PLUGIN_SRC, 'index.html')
SH = os.path.join(PLUGIN_SRC, 'install.sh')
LANG_DIR = os.path.join(PLUGIN_SRC, 'lang')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']

PANEL_DIR = '/www/server/yufeng_panel'

#: 白名单必须放行的真实取值
GOOD_TARGETS = ['3.13', '3.13.14', 'cpython-3.13.14-linux-x86_64-gnu']
#: 必须拒绝的注入 / 选项注入 / 穿越取值
BAD_TARGETS = ['3.9.25; touch /tmp/PWN', '--all', '--help', '-i', '../../etc',
               'cpython-3.13.14;id', '$(id)', '`id`', 'a b', '', ' ', '3.13\nid',
               'cpython-3.14.6-linux-x86_64-gnu|id', '..']

NEW_I18N_KEYS = [
    '请求失败，请稍后重试',
    '版本标识不合法，已拒绝',
    '目录路径不合法，已拒绝',
    '该 Python 为系统或外部环境，禁止卸载',
    '该路径不是虚拟环境目录，未删除',
    '该版本未安装，无法卸载',
    '该版本下有关联的虚拟环境({1}个)，为了安全禁止卸载',
    '获取 Python 列表失败: ',
    '操作超时，请稍后重试',
    '未能确认安装结果: ',
    '未能确认卸载结果: ',
    '删除失败: ',
]


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _func_src(path, name):
    src = _read(path)
    lines = src.splitlines()
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError('%s 中找不到顶层函数 %s' % (path, name))


def _call_names(src):
    """收集调用点的完整点号路径（`yf.shlexQuote` → 'yf.shlexQuote'）。"""
    names = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call):
            f = n.func
            parts = []
            while isinstance(f, ast.Attribute):
                parts.append(f.attr)
                f = f.value
            if isinstance(f, ast.Name):
                parts.append(f.id)
                names.append('.'.join(reversed(parts)))
    return names


def _js_code(path):
    """去掉 JS 注释后的源码（防止在注释里写 pyEsc/.fail 蒙混）。"""
    src = _read(path)
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    out = []
    for line in src.splitlines():
        i = line.find('//')
        if i != -1:
            line = line[:i]
        out.append(line)
    return '\n'.join(out)


class FakeYf(object):
    """记录型 core.yf 桩：所有 shell 调用都被记下来（真跑装配，不 mock 被测逻辑）。"""

    def __init__(self):
        self.cmds = []
        self.files = {}
        self.rc = 0
        self.out = ''
        self.err = ''
        self.rm_impl = None

    def shlexQuote(self, s):
        return shlex.quote(str(s))

    def execShellRc(self, cmdstring, cwd=None, timeout=None, shell=True):
        self.cmds.append({'cmd': cmdstring, 'timeout': timeout})
        if self.rm_impl is not None and cmdstring.startswith('rm -rf '):
            return self.rm_impl(cmdstring)
        return (self.rc, self.out, self.err)

    def returnJson(self, status, msg, data=None, *args):
        return {'status': status, 'msg': msg, 'data': data}

    def getPanelDir(self):
        return PANEL_DIR

    def readFile(self, filename):
        if filename in self.files:
            return self.files[filename]
        try:
            with open(filename, encoding='utf-8') as fh:
                return fh.read()
        except Exception:
            return False

    def writeFile(self, filename, content, mode='w+'):
        self.files[filename] = content
        return True


def _load_module(fake_yf):
    """把 index.py 以桩 core.yf 注入后 exec，返回其命名空间（真源码、真行为）。"""
    src = _read(IDX)
    ns = {'__name__': 'python_yf_under_test', '__file__': IDX}
    cwd = os.getcwd()
    core_pkg = types.ModuleType('core')
    core_pkg.__path__ = []
    core_pkg.yf = fake_yf
    saved_core = sys.modules.get('core')
    saved_yf = sys.modules.get('core.yf')
    sys.modules['core'] = core_pkg
    sys.modules['core.yf'] = fake_yf
    try:
        exec(compile(src, IDX, 'exec'), ns)
    finally:
        os.chdir(cwd)
        if saved_core is None:
            sys.modules.pop('core', None)
        else:
            sys.modules['core'] = saved_core
        if saved_yf is None:
            sys.modules.pop('core.yf', None)
        else:
            sys.modules['core.yf'] = saved_yf
    return ns


def _tail(names):
    """调用点路径的末段（`yf.shlexQuote` → 'shlexQuote'）。"""
    return set(n.split('.')[-1] for n in names)


class D08Base(unittest.TestCase):
    def setUp(self):
        self.fake = FakeYf()
        self.ns = _load_module(self.fake)
        self.tmp = tempfile.mkdtemp(prefix='yf_d08_guard_')
        self.venv_file = os.path.join(self.tmp, 'venvs.json')
        self.ns['VENV_FILE'] = self.venv_file
        self.ns['_VENV_DIR'] = self.tmp
        # uv 可执行文件用占位文件代替：被测逻辑只做存在性判断（真机调用不在本文件里做）
        self.uv = os.path.join(self.tmp, 'uv')
        with open(self.uv, 'w', encoding='utf-8') as fh:
            fh.write('')
        self.ns['UV_BIN'] = self.uv
        self.ns['UV_PYTHON_DIR'] = '/root/.local/share/uv/python'
        self._saved_argv = list(sys.argv)

    def tearDown(self):
        sys.argv = self._saved_argv
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def set_registry(self, data):
        """写 venvs.json：既放到桩内存（被测代码读得到），也真落盘（get_venvs 会先看文件存在）。"""
        text = data if isinstance(data, str) else json.dumps(data)
        self.fake.files[self.venv_file] = text
        with open(self.venv_file, 'w', encoding='utf-8') as fh:
            fh.write(text)
        return text

    def call(self, func, payload):
        """以插件真实入口形式调用：sys.argv = [index.py, func, json]（cwd 无关）。"""
        sys.argv = ['index.py', func, json.dumps(payload)]
        return self.ns[func]()


class TestTargetWhitelist(D08Base):
    def test_01_whitelist_accepts_real_values(self):
        for v in GOOD_TARGETS:
            self.assertTrue(self.ns['_valid_target'](v), '应放行: %r' % v)

    def test_02_whitelist_rejects_injection(self):
        for v in BAD_TARGETS:
            self.assertFalse(self.ns['_valid_target'](v), '必须拒绝: %r' % v)

    def test_03_whitelist_rejects_non_string(self):
        for v in (None, 313, ['3.13'], {'a': 1}, True):
            self.assertFalse(self.ns['_valid_target'](v), '必须拒绝: %r' % (v,))


class TestSafeDir(D08Base):
    def test_10_accepts_normal_project_dir(self):
        base = tempfile.mkdtemp(prefix='yf_d08_proj_')
        self.addCleanup(lambda: __import__('shutil').rmtree(base, ignore_errors=True))
        self.assertEqual(self.ns['_safe_dir'](base), os.path.normpath(base))

    def test_11_rejects_panel_and_system_dirs(self):
        # 关键：这些 POSIX 绝对路径在开发机（Windows）既不存在、`isabs()` 也回 False，
        # 不屏蔽这两个判据的话，黑名单被删掉也照样返回 None（变异测试实测会漏判）。
        with mock.patch('os.path.isdir', return_value=True), \
                mock.patch('os.path.isabs', return_value=True):
            for p in ('/', '/etc', '/etc/nginx', '/usr', '/usr/lib', '/bin', '/boot',
                      '/www/server', '/www/server/yufeng_panel', '/www/server/python_yf',
                      '/root/.local/share/uv', '/var/lib/mysql'):
                self.assertIsNone(self.ns['_safe_dir'](p), '必须拒绝: %r' % p)

    def test_12_rejects_traversal_relative_and_junk(self):
        base = tempfile.mkdtemp(prefix='yf_d08_proj_')
        self.addCleanup(lambda: __import__('shutil').rmtree(base, ignore_errors=True))
        for p in ('project', None, '', '   ', base + '\x00', 123, ['/tmp']):
            self.assertIsNone(self.ns['_safe_dir'](p), '必须拒绝: %r' % (p,))
        # `..` 判据必须独立生效（不能被「目录不存在 / 平台 isabs」代劳）
        with mock.patch('os.path.isdir', return_value=True), \
                mock.patch('os.path.isabs', return_value=True):
            for p in ('../etc', base + '/../../etc', base + '/\nid'):
                self.assertIsNone(self.ns['_safe_dir'](p), '必须拒绝: %r' % (p,))

    def test_13_rejects_missing_dir(self):
        self.assertIsNone(self.ns['_safe_dir'](os.path.join(self.tmp, 'not_created_yet')))


class TestInjectionNeverReachesShell(D08Base):
    def test_20_install_injection_rejected_without_uv_call(self):
        for bad in ('3.9.25; touch /tmp/PWN', '--all', '../../etc'):
            res = self.call('install_python', {'version': bad})
            self.assertFalse(res['status'], '注入必须被拒绝: %r' % bad)
            self.assertIn('不合法', res['msg'])
            self.assertEqual([], self.fake.cmds, '任何 uv 调用都不允许发生: %r' % self.fake.cmds)

    def test_21_uninstall_option_injection_rejected(self):
        for bad in ('--help', '--all'):
            res = self.call('uninstall_python', {'version': bad})
            self.assertFalse(res['status'])
            self.assertIn('不合法', res['msg'])
            self.assertEqual([], self.fake.cmds)

    def test_22_create_venv_injection_rejected(self):
        base = tempfile.mkdtemp(prefix='yf_d08_proj_')
        self.addCleanup(lambda: __import__('shutil').rmtree(base, ignore_errors=True))
        res = self.call('create_venv', {'version': 'cpython-3.13.14-linux-x86_64-gnu; touch /tmp/PWN',
                                        'path': base})
        self.assertFalse(res['status'])
        res = self.call('create_venv', {'version': '3.13', 'path': base + '; touch /tmp/PWN'})
        self.assertFalse(res['status'])
        res = self.call('create_venv', {'version': '3.13', 'path': 'x; id'})
        self.assertFalse(res['status'])
        self.assertEqual([], self.fake.cmds, '任何 uv 调用都不允许发生: %r' % self.fake.cmds)

    def test_23_non_dict_args_do_not_crash(self):
        for raw in ('[]', '"x"', 'null', '3', '[1,2]', '{"version": 313}', '{"version": null}'):
            sys.argv = ['index.py', 'install_python', raw]
            res = self.ns['install_python']()
            self.assertFalse(res['status'], 'raw=%r 不应成功' % raw)
        sys.argv = ['index.py', 'create_venv', 'version:3.13,path:/etc']
        res = self.ns['create_venv']()
        self.assertFalse(res['status'])
        self.assertEqual([], self.fake.cmds)


class TestUninstallOwnership(D08Base):
    def test_30_system_python_refused(self):
        self.ns['_python_list'] = lambda: ([{
            'name': 'cpython-3.11.2-linux-x86_64-gnu', 'version': '3.11.2',
            'path': '/usr/bin/python3.11', 'managed': False}], '')
        res = self.call('uninstall_python', {'version': 'cpython-3.11.2-linux-x86_64-gnu'})
        self.assertFalse(res['status'])
        self.assertIn('系统或外部环境', res['msg'])
        self.assertEqual([], self.fake.cmds, '系统解释器绝不允许落到 uv 命令上')

    def test_31_unknown_version_refused(self):
        self.ns['_python_list'] = lambda: ([], '')
        res = self.call('uninstall_python', {'version': '3.9.25'})
        self.assertFalse(res['status'])
        self.assertEqual([], self.fake.cmds)

    def test_32_managed_python_with_venvs_refused(self):
        self.ns['_python_list'] = lambda: ([{
            'name': 'cpython-3.13.14-linux-x86_64-gnu', 'version': '3.13.14',
            'path': '/root/.local/share/uv/python/cpython-3.13.14-linux-x86_64-gnu/bin/python3.13',
            'managed': True}], '')
        self.ns['get_venvs'] = lambda: {'cpython-3.13.14-linux-x86_64-gnu': ['/tmp/a/.venv']}
        res = self.call('uninstall_python', {'version': 'cpython-3.13.14-linux-x86_64-gnu'})
        self.assertFalse(res['status'])
        self.assertIn('禁止卸载', res['msg'])
        self.assertEqual([], self.fake.cmds)


class TestNoFalseSuccess(D08Base):
    def test_40_install_rc0_but_not_installed_is_failure(self):
        self.ns['_python_list'] = lambda: ([], '')
        res = self.call('install_python', {'version': '3.13.14'})
        self.assertFalse(res['status'], '回读不到就绝不能报成功')
        self.assertIn('未能确认安装结果', res['msg'])

    def test_41_uv_missing_install_is_failure(self):
        self.ns['UV_BIN'] = os.path.join(self.tmp, 'no_such_uv')
        res = self.call('install_python', {'version': '3.13.14'})
        self.assertFalse(res['status'])
        self.assertIn('uv_not_found', res['msg'])
        self.assertEqual([], self.fake.cmds)

    def test_42_timeout_is_reported(self):
        self.fake.rc = -1
        self.fake.err = 'Timeout：uv'
        res = self.call('install_python', {'version': '3.13.14'})
        self.assertFalse(res['status'])
        self.assertIn('超时', res['msg'])

    def test_43_remove_venv_verifies_real_deletion(self):
        base = tempfile.mkdtemp(prefix='yf_d08_del_')
        self.addCleanup(lambda: __import__('shutil').rmtree(base, ignore_errors=True))
        path = os.path.join(base, '.venv')
        os.makedirs(os.path.join(path, 'bin'))
        with open(os.path.join(path, 'bin', 'python'), 'w', encoding='utf-8') as fh:
            fh.write('')
        self.set_registry({'3.13': [path]})

        # rm 返回 0 但目录还在（假成功场景）→ 必须如实报失败，且登记保留
        self.fake.rc = 0
        res = self.call('remove_venv', {'version': '3.13', 'path': path})
        self.assertFalse(res['status'], '删不掉就不能报删除成功')
        self.assertIn('删除失败', res['msg'])
        self.assertIn(path, json.loads(self.fake.files[self.venv_file])['3.13'])

        # rm 真删 → 成功且登记清空
        def _rm(_cmd):
            import shutil as _sh
            _sh.rmtree(path, ignore_errors=True)
            return (0, '', '')

        self.fake.rm_impl = _rm
        res = self.call('remove_venv', {'version': '3.13', 'path': path})
        self.assertTrue(res['status'], res)
        self.assertFalse(os.path.exists(path))
        self.assertNotIn(path, json.loads(self.fake.files[self.venv_file]).get('3.13', []))

    def test_44_remove_venv_refuses_non_venv_dir(self):
        base = tempfile.mkdtemp(prefix='yf_d08_del2_')
        self.addCleanup(lambda: __import__('shutil').rmtree(base, ignore_errors=True))
        path = os.path.join(base, '.venv')
        os.makedirs(path)
        self.set_registry({'3.13': [path]})
        res = self.call('remove_venv', {'version': '3.13', 'path': path})
        self.assertFalse(res['status'])
        self.assertIn('不是虚拟环境目录', res['msg'])
        self.assertTrue(os.path.isdir(path), '拒绝时不得删除任何东西')

    def test_45_remove_venv_refuses_unregistered_path(self):
        base = tempfile.mkdtemp(prefix='yf_d08_del3_')
        self.addCleanup(lambda: __import__('shutil').rmtree(base, ignore_errors=True))
        path = os.path.join(base, '.venv')
        os.makedirs(os.path.join(path, 'bin'))
        self.set_registry({})
        res = self.call('remove_venv', {'version': '3.13', 'path': path})
        self.assertFalse(res['status'])
        self.assertTrue(os.path.isdir(path))
        self.assertEqual([], [c for c in self.fake.cmds if 'rm -rf' in c['cmd']])

    def test_46_uninstall_rc0_but_still_installed_is_failure(self):
        """uv 卸载退出码 0 但解释器仍在（真机实测的假成功）→ 必须回读确认后报失败。"""
        item = {'name': 'cpython-3.13.14-linux-x86_64-gnu', 'version': '3.13.14',
                'path': '/root/.local/share/uv/python/cpython-3.13.14-linux-x86_64-gnu/bin/python3.13',
                'managed': True}
        self.ns['_python_list'] = lambda: ([dict(item)], '')
        res = self.call('uninstall_python', {'version': 'cpython-3.13.14-linux-x86_64-gnu'})
        self.assertFalse(res['status'], '解释器还在就绝不能报卸载成功')
        self.assertIn('未能确认卸载结果', res['msg'])
        self.assertEqual(1, len(self.fake.cmds), '应真的调用过一次 uv uninstall')
        self.assertIn('uninstall', self.fake.cmds[0]['cmd'])


class TestVenvRegistry(D08Base):
    def test_50_normalize_drops_poison(self):
        norm = self.ns['_normalize_venvs']
        self.assertEqual({}, norm([]))
        self.assertEqual({}, norm('x'))
        self.assertEqual({}, norm(None))
        self.assertEqual({}, norm({'a': 'notalist'}))
        self.assertEqual({}, norm({'a': []}))
        self.assertEqual({}, norm({1: ['/tmp/a']}))
        self.assertEqual({'a': ['/tmp/a']}, norm({'a': ['/tmp/a', 1, None, '']}))

    def test_51_poisoned_registry_does_not_break_list(self):
        self.ns['_python_list'] = lambda: ([{
            'name': 'cpython-3.13.14-linux-x86_64-gnu', 'version': '3.13.14',
            'path': '/root/.local/share/uv/python/cpython-3.13.14-linux-x86_64-gnu/bin/python3.13',
            'managed': True}], '')
        for poison in ('[]', '{"cpython-3.13.14-linux-x86_64-gnu": "notalist"}', 'null', '{oops'):
            self.set_registry(poison)
            res = self.ns['get_python_list']()
            self.assertTrue(res['status'], 'poison=%r 不应让接口失败' % poison)
            self.assertEqual([], res['data']['installed'][0]['venvs'])

    def test_52_list_classifies_by_json_path_not_text(self):
        payload = json.dumps([
            {'key': 'cpython-3.14.6-linux-x86_64-gnu', 'version': '3.14.6',
             'path': '/root/.local/bin/python3.14',
             'symlink': '/root/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu/bin/python3.14',
             'implementation': 'cpython', 'variant': 'default'},
            {'key': 'cpython-3.15.0b4-linux-x86_64-gnu', 'version': '3.15.0b4',
             'path': None, 'symlink': None,
             'implementation': 'cpython', 'variant': 'default'},
            {'key': 'cpython-3.11.2-linux-x86_64-gnu', 'version': '3.11.2',
             'path': '/usr/bin/python3.11', 'symlink': None,
             'implementation': 'cpython', 'variant': 'default'},
            {'key': 'cpython-3.14.6+freethreaded-linux-x86_64-gnu', 'version': '3.14.6',
             'path': '/root/.local/bin/python3.14t', 'symlink': None,
             'implementation': 'cpython', 'variant': 'freethreaded'},
            {'key': 'pypy-3.11.15-linux-x86_64-gnu', 'version': '3.11.15',
             'path': None, 'symlink': None, 'implementation': 'pypy', 'variant': 'default'},
        ])
        self.fake.out = payload
        res = self.ns['get_python_list']()
        self.assertTrue(res['status'])
        installed = res['data']['installed']
        self.assertEqual(['cpython-3.14.6-linux-x86_64-gnu', 'cpython-3.11.2-linux-x86_64-gnu'],
                         [i['name'] for i in installed])
        self.assertTrue(installed[0]['managed'], 'uv 目录下的解释器必须是 managed')
        self.assertFalse(installed[1]['managed'], '系统解释器不得算 managed')
        self.assertEqual(['cpython-3.15.0b4-linux-x86_64-gnu'],
                         [i['name'] for i in res['data']['available']])
        names = [i['name'] for i in res['data']['all_versions']]
        self.assertNotIn('pypy-3.11.15-linux-x86_64-gnu', names)
        self.assertNotIn('cpython-3.14.6+freethreaded-linux-x86_64-gnu', names)

    def test_53_concurrent_read_modify_write_keeps_every_entry(self):
        import threading
        ns = self.ns
        ns['get_venvs'] = lambda: ns['_normalize_venvs'](
            json.loads(self.fake.files[self.venv_file])) if self.venv_file in self.fake.files else {}

        def _worker(i):
            with ns['_venv_file_lock']():
                data = ns['get_venvs']()
                data.setdefault('3.13', []).append('/tmp/r%d/.venv' % i)
                ns['save_venvs'](data)

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        saved = json.loads(self.fake.files[self.venv_file])
        self.assertEqual(8, len(saved['3.13']), '并发读-改-写不得丢登记')

    def test_54_file_lock_holds_thread_lock(self):
        """跨进程 flock 在无 fcntl 的平台会退化为空 —— 进程内锁必须独立存在。"""
        body = _func_src(IDX, '_venv_file_lock')
        self.assertIn('_VENV_LOCK', body, '读-改-写必须持进程内锁（变异回退成 nullcontext 即失守）')
        self.assertRegex(body, r'with\s+_VENV_LOCK\s*:')
        self.assertIn('threading.Lock()', _read(IDX))


class TestCreateVenvRealPath(D08Base):
    def test_60_create_venv_quotes_every_argument(self):
        base = tempfile.mkdtemp(prefix='yf d08 proj ')
        self.addCleanup(lambda: __import__('shutil').rmtree(base, ignore_errors=True))
        path = os.path.join(base, '.venv')
        os.makedirs(os.path.join(path, 'bin'))
        with open(os.path.join(path, 'bin', 'python'), 'w', encoding='utf-8') as fh:
            fh.write('')
        res = self.call('create_venv', {'version': 'cpython-3.13.14-linux-x86_64-gnu', 'path': base})
        self.assertTrue(res['status'], res)
        self.assertEqual(1, len(self.fake.cmds))
        cmd = self.fake.cmds[0]['cmd']
        self.assertIn(shlex.quote(path), cmd, '带空格的路径必须被整体转义')
        self.assertIn('--prompt', cmd)
        self.assertNotIn('; ', cmd)
        self.assertIsNotNone(self.fake.cmds[0]['timeout'], 'uv 调用必须有超时')
        saved = json.loads(self.fake.files[self.venv_file])
        self.assertEqual([path], saved['cpython-3.13.14-linux-x86_64-gnu'])

    def test_61_prompt_is_sanitized(self):
        base = tempfile.mkdtemp(prefix='yf_d08_proj_')
        self.addCleanup(lambda: __import__('shutil').rmtree(base, ignore_errors=True))
        weird = os.path.join(base, 'a;b`id`c')
        os.makedirs(weird)
        path = os.path.join(weird, '.venv')
        os.makedirs(os.path.join(path, 'bin'))
        with open(os.path.join(path, 'bin', 'python'), 'w', encoding='utf-8') as fh:
            fh.write('')
        res = self.call('create_venv', {'version': '3.13', 'path': weird})
        self.assertTrue(res['status'], res)
        cmd = self.fake.cmds[0]['cmd']
        self.assertIn(shlex.quote(path), cmd)
        self.assertNotIn(';', cmd.replace(shlex.quote(path), ''))


class TestSourceStructure(unittest.TestCase):
    """AST 结构断言：修复必须真的写在源码里（不受注释/死代码影响）。"""

    def test_70_uv_calls_go_through_quoted_helper(self):
        src = _func_src(IDX, '_run_uv')
        calls = _tail(_call_names(src))
        self.assertIn('shlexQuote', calls, '_run_uv 必须逐参转义')
        self.assertIn('execShellRc', calls, '必须用带退出码的执行原语')
        for fname in ('install_python', 'uninstall_python', 'create_venv'):
            body = _func_src(IDX, fname)
            self.assertNotIn('execShell(', body.replace('execShellRc(', ''),
                             '%s 不得直接用 execShell 拼字符串' % fname)
            self.assertNotIn('JoinedStr', [type(n).__name__ for n in ast.walk(ast.parse(body))
                                           if isinstance(n, ast.JoinedStr) and 'uv' in ast.unparse(n)],
                             '%s 不得把 uv 命令写成 f-string' % fname)
            self.assertIn('_valid_target', _tail(_call_names(body)), '%s 必须过版本白名单' % fname)

    def test_71_create_venv_checks_dir_and_timeout(self):
        body = _func_src(IDX, 'create_venv')
        self.assertIn('_safe_dir', _tail(_call_names(body)))
        self.assertIn('_venv_file_lock', [n.id for n in ast.walk(ast.parse(body))
                                          if isinstance(n, ast.Name)])
        self.assertIn('_CMD_TIMEOUT', body)

    def test_72_remove_venv_verifies_after_delete(self):
        body = _func_src(IDX, 'remove_venv')
        calls = _tail(_call_names(body))
        self.assertIn('shlexQuote', calls, 'rm 的路径必须转义')
        self.assertIn('execShellRc', calls)
        self.assertIn('exists', calls, '删除后必须回读确认')
        self.assertIn('_safe_dir', calls, '必须过目录黑名单')
        self.assertIn('save_venvs', calls)
        self.assertLess(body.index('execShellRc'), body.rindex('save_venvs'),
                        '必须先真删成功再改登记表')

    def test_73_uninstall_only_touches_managed(self):
        body = _func_src(IDX, 'uninstall_python')
        self.assertIn("'managed'", body)
        self.assertIn('_python_list', _tail(_call_names(body)))

    def test_74_timeouts_are_explicit(self):
        src = _read(IDX)
        self.assertRegex(src, r'_CMD_TIMEOUT\s*=\s*\d+')
        self.assertRegex(src, r'_INSTALL_TIMEOUT\s*=\s*\d+')
        self.assertNotIn('timeout=None', src)


class TestFrontend(unittest.TestCase):
    def setUp(self):
        self.js = _js_code(HTML)

    def test_80_request_has_fail_handler(self):
        self.assertIn('.fail(', self.js, 'HTTP 失败必须关遮罩，否则 loading 永久卡死')
        self.assertIn('layer.close(loadT)', self.js)

    def test_81_escaping_helpers_exist_and_used(self):
        self.assertIn('function pyEsc(', self.js)
        self.assertIn('function pyJsArg(', self.js)
        for value in ('item.name', 'item.path', 'item.version', 'v_path', 'res.msg', 'version_name'):
            self.assertRegex(self.js, r'pyEsc\(\s*%s\s*\)' % re.escape(value),
                             '%s 回显必须转义' % value)
        # 行内 onclick 不得再出现「裸串拼接」写法（\'' + <值>）或裸值拼接
        self.assertNotIn("\\'' +", self.js, '行内 onclick 不得直接拼接未转义值')
        for raw_concat in ('+ item.name +', '+ item.path +', '+ v_path +', '+ item.version +'):
            self.assertNotIn(raw_concat, self.js, '回显值不得裸拼: %s' % raw_concat)

    def test_82_uninstall_button_uses_managed_flag(self):
        self.assertIn('item.managed', self.js)
        self.assertNotIn("item.path.indexOf('/uv/python')", self.js)

    def test_83_all_masks_closed_on_both_branches(self):
        self.assertIn('mask', self.js)
        self.assertIn(', loadT);', self.js, '调用方自己的遮罩必须交给 request 统一关闭')


class TestInstallSh(unittest.TestCase):
    def test_90_install_sh_verifies_uv_executable(self):
        sh = _read(SH)
        self.assertIn('-x "$HOME/.local/bin/uv"', sh, 'uv 存在但不可执行必须判为安装失败')
        # 只在别处出现不算：curl 安装分支内必须复核可执行位（旧实现只看 -f）
        branch = re.search(r'curl[^\n]*\n(.*?)\n\s*fi\n', sh, re.S)
        self.assertIsNotNone(branch, 'install.sh 必须保留 curl 安装分支')
        self.assertIn('-x "$HOME/.local/bin/uv"', branch.group(1),
                      'curl 安装后必须复核 uv 可执行（只看 -f 会假成功）')
        self.assertNotRegex(sh, r'Install_python_yf\(\)\s*\{\s*rm -rf /')

    def test_91_install_sh_syntax_is_sane(self):
        sh = _read(SH)
        self.assertIn('Uninstall_python_yf', sh)
        self.assertIn('${install_path}', sh)


class TestI18n(unittest.TestCase):
    def test_95_six_lang_files_aligned(self):
        sets = {}
        for lang in LANGS:
            with open(os.path.join(LANG_DIR, lang + '.json'), encoding='utf-8') as fh:
                sets[lang] = json.load(fh)
        ref = set(sets['en'])
        for lang, data in sets.items():
            self.assertEqual(ref, set(data), '%s 与 en 的键集合不一致' % lang)

    def test_96_new_message_keys_present_in_all_langs(self):
        for lang in LANGS:
            with open(os.path.join(LANG_DIR, lang + '.json'), encoding='utf-8') as fh:
                data = json.load(fh)
            for key in NEW_I18N_KEYS:
                self.assertIn(key, data, '%s 缺键: %s' % (lang, key))
                self.assertTrue(data[key].strip(), '%s 的 %s 译文为空' % (lang, key))

    def test_97_no_dead_len_placeholder_key(self):
        for lang in LANGS:
            with open(os.path.join(LANG_DIR, lang + '.json'), encoding='utf-8') as fh:
                data = json.load(fh)
            self.assertNotIn('该版本下有关联的虚拟环境({len(venvs)}个)，为了安全禁止卸载', data)
            self.assertNotIn('该版本下有关联的虚拟环境({0}个)，为了安全禁止卸载', data,
                             'i18n 静态门禁禁止 {0} 占位符（msgTpl 从 {1} 起替换）')


if __name__ == '__main__':
    unittest.main()
