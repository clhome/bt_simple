# coding: utf-8
"""文件路径策略守卫：**放开**口径（2026-10-28 用户裁定）+ 结构接线。

## 政策

用户明确要求：「不要拦截，所有目录都允许用户访问」。因此 `file.safePath()` 不再按
目录黑名单拒绝 —— 面包屑点 `/www`、`/www/server`、`/etc` 或面板自身目录都必须能进。
`safePath` 只保留**输入本身非法**的拦截（空 / 非字符串 / NUL / 无法词法规范化），
那几条是防崩溃（拼 shell 与文件 API 会抛异常），不是权限。

本文件原来断言的是「越界路径必须被拒」（P0-3 之二那轮的加固）。政策反转后，
那些断言按**新口径**逐条翻转为「必须放行」，继续作为回归守卫存在：
想重新收紧，把 `web/utils/file.py::ALLOW_ALL_PATHS` 置 False，并把本文件的
`TestPathPolicyAllowsEverything` 改回拒绝断言。

## 断言分三层

1. **直测** `safePath`：敏感文件 / 系统根 / 面板自身资产 / 数据库目录，读写两种模式一律放行；
   非法输入（空 / None / NUL / bytes）仍拒。
2. **行为**：AST 抽出路由函数真调用，`/etc`、`/etc/shadow` 这类路径不得再返回
   `FILE_DANGER` / `FILE_SENSITIVE_DIR`。破坏性路由（删/下载）只用**不存在的路径**，
   保证用例不会真删/真写测试机上的文件。
3. **结构**：各入口仍调用 `safePath`（保留单一收口点），且 `ALLOW_ALL_PATHS` 开关与
   黑名单判定代码都在（可回溯收紧）。
"""
import ast
import logging
import os
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

FILE_PY = os.path.join(ROOT, 'web', 'utils', 'file.py')
FILES_PY = os.path.join(ROOT, 'web', 'admin', 'files', 'files.py')

PANEL_DIR = '/www/server/yufeng_panel'


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _keep_nodes(path, assigns=(), funcs=()):
    """按 AST 抽出指定的模块级赋值与函数定义（不执行整个模块，避免拉起重依赖）。"""
    src = _read(path)
    tree = ast.parse(src)
    keep = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, 'id', '') in assigns for t in node.targets):
            keep.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in funcs:
            # 路由函数带装饰器（@blueprint.route / @panel_login_required）：摘掉再执行
            node.decorator_list = []
            keep.append(node)
    return keep


class _FakeYf:
    """safePath / fileDelete / dirDelete 依赖的 yf 最小面。"""

    panel_dir = PANEL_DIR

    @classmethod
    def getPanelDir(cls):
        return cls.panel_dir

    @classmethod
    def returnData(cls, status, msg, data=None, *args):
        return {'status': status, 'msg': msg, 'data': data}

    @staticmethod
    def getInfo(tpl, args=()):
        return tpl

    @staticmethod
    def writeLog(*a, **k):
        return True

    @staticmethod
    def removeDir(path):
        return True

    @staticmethod
    def getFatherDir():
        return '/www/server'


class _FakeThisdb:
    @staticmethod
    def getOption(*a, **k):
        return ''

    @staticmethod
    def addTaskByDownload(**k):
        return True


def _load_utils_file():
    """执行 file.py 的 safePath / fileDelete / dirDelete（+ 黑名单常量）。"""
    nodes = _keep_nodes(
        FILE_PY,
        assigns=('ALLOW_ALL_PATHS', '_SENSITIVE_PATHS', '_SENSITIVE_EXACT',
                 '_SENSITIVE_DATA_PREFIXES', '_PANEL_SENSITIVE_REL'),
        funcs=('_posix_norm', 'safePath', 'fileDelete', 'dirDelete'),
    )
    ns = {
        'os': os,
        'yf': _FakeYf,
        'thisdb': _FakeThisdb,
        '_log': logging.getLogger('files-safepath-test'),
        'mvRecycleBin': lambda p: False,
        'getOccupyingProcess': lambda p: '',
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), FILE_PY, 'exec'), ns)
    return ns


class _FileShim:
    """路由里 `import utils.file as file` 的最小替身：safePath 用真实现。"""

    def __init__(self, ns):
        self.safePath = ns['safePath']
        self.fileDelete = ns['fileDelete']
        self.dirDelete = ns['dirDelete']

    def getAccess(self, filename):
        return {'chmod': '755', 'chown': 'www'}

    def getSysUserList(self):
        return ['www', 'root']

    def getAllDirList(self, path, page, size, order, search):
        return {'count': 0, 'dir': [], 'files': [], 'path': path}

    def getDirList(self, path, page, size, order, search):
        return {'count': 0, 'dir': [], 'files': [], 'path': path}

    def getDirSizeByBash(self, path):
        return '0 B'


class _Req:
    def __init__(self, form=None, args=None):
        self.form = dict(form or {})
        self.args = dict(args or {})


def _load_route(name, file_shim, req, yf=None, os_shim=None):
    """抽出 files.py 的单个路由函数并执行，返回可调用的函数对象。"""
    nodes = _keep_nodes(FILES_PY, funcs=(name,))
    if not nodes:
        raise AssertionError('未找到路由函数 %s' % name)
    ns = {
        'os': os_shim if os_shim is not None else os,
        'json': __import__('json'),
        'file': file_shim,
        'yf': yf if yf is not None else _RouteYf,
        'request': req,
        'session': types.SimpleNamespace(get=lambda *a, **k: {}),
        'thisdb': _FakeThisdb,
        'logging': logging,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), FILES_PY, 'exec'), ns)
    return ns[name]


class _RouteYf:
    @staticmethod
    def returnData(status, msg, data=None, *args):
        return {'status': status, 'msg': msg, 'data': data}

    @staticmethod
    def getFatherDir():
        return '/www/server'

    @staticmethod
    def getPage(*a, **k):
        return ''

    @staticmethod
    def fileNameCheck(name):
        return True

    @staticmethod
    def triggerTask():
        return True


def _calls_in_func(name, callee_text):
    """路由函数源码里是否出现某个调用（文本匹配，含关键字形式）。"""
    src = _read(FILES_PY)
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return callee_text in '\n'.join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError('未找到函数 %s' % name)


# 原来写模式要拒绝的关键数据目录（现在是「必须放行」的正向清单）
_DATA_PREFIXES = (
    '/www/server/data', '/www/server/mysql', '/www/server/mariadb',
    '/www/server/redis', '/www/server/valkey', '/www/server/pgsql',
    '/www/server/postgresql', '/www/server/panel', '/www/server/yufeng_panel',
)

# 原黑名单里的敏感系统路径（现在是正向清单）
_SENSITIVE_FILES = (
    '/etc/passwd', '/etc/shadow', '/etc/gshadow', '/etc/sudoers', '/etc/sudoers.d',
    '/etc/ssh/sshd_config', '/root/.ssh/authorized_keys', '/etc/ld.so.preload',
    '/etc/cron.d/evil', '/var/spool/cron/root',
)


class TestPathPolicyAllowsEverything(unittest.TestCase):
    """直测 safePath：**所有目录都放行**（政策口径），只拒非法输入。"""

    @classmethod
    def setUpClass(cls):
        cls.ns = _load_utils_file()
        cls.safePath = staticmethod(cls.ns['safePath'])

    def test_01_allows_sensitive_system_files(self):
        for p in _SENSITIVE_FILES:
            for write in (False, True):
                ok, reason = self.safePath(p, write=write)
                self.assertTrue(ok, 'write=%s 时 %s 被拦: %s（政策要求全放行）'
                                % (write, p, reason))

    def test_02_allows_system_roots(self):
        for p in ('/', '/etc', '/www', '/www/server', '/root', '/usr', '/var'):
            for write in (False, True):
                ok, reason = self.safePath(p, write=write)
                self.assertTrue(ok, 'write=%s 时 %s 被拦: %s' % (write, p, reason))

    def test_03_allows_data_prefixes_read_and_write(self):
        for p in _DATA_PREFIXES:
            for write in (False, True):
                ok, reason = self.safePath(p, write=write)
                self.assertTrue(ok, 'write=%s 时 %s 被拦: %s' % (write, p, reason))

    def test_04_allows_data_prefix_subpaths(self):
        for p in ('/www/server/mysql/data/ibdata1',
                  '/www/server/data/panel.db',
                  '/www/server/mariadb/mysql/ib_logfile0',
                  '/www/server/mysql/'):
            ok, reason = self.safePath(p, write=True)
            self.assertTrue(ok, '%s 被拦: %s' % (p, reason))

    def test_05_allows_root_dotdot_normalized(self):
        """`/etc/passwd/..` 词法上是 `/etc`：放行（不再有目录黑名单）。"""
        ok, reason = self.safePath('/etc/passwd/..')
        self.assertTrue(ok, reason)

    def test_06_allows_wwwroot_and_env_dirs(self):
        for p in ('/www/wwwroot/site/a.txt', '/www/server/php/72/bin/php',
                  '/www/server/nginx/conf/nginx.conf', '/www/server/mysql_conf/x.cnf'):
            for write in (False, True):
                ok, reason = self.safePath(p, write=write)
                self.assertTrue(ok, '%s 被拦: %s' % (p, reason))

    def test_07_still_rejects_malformed_input(self):
        """非法输入仍拒：这些会在拼 shell / 文件 API 时抛异常或截断，不是权限问题。"""
        for bad in ('', None, '/tmp/a\x00b', b'/tmp/x', 123):
            ok, reason = self.safePath(bad)
            self.assertFalse(ok, '%r 应被拒' % (bad,))
            self.assertEqual(reason, 'FILE_DANGER')


class TestRouteDoesNotBlockAnyDir(unittest.TestCase):
    """行为层：AST 抽出路由函数真调用，任何目录都不得被 safePath 拦下。"""

    @classmethod
    def setUpClass(cls):
        cls.ns = _load_utils_file()
        cls.file = _FileShim(cls.ns)

        # download_file 走 `from utils.urlguard import validate_url`：替身固定放行，
        # 这样断言才能落到 safePath 这一层（不被 URL 校验失败掩盖）。
        fake_mod = types.ModuleType('utils.urlguard')
        fake_mod.validate_url = lambda url, resolve=False: (True, 'ok', {})
        cls._saved = sys.modules.get('utils.urlguard')
        sys.modules['utils.urlguard'] = fake_mod

    @classmethod
    def tearDownClass(cls):
        if cls._saved is None:
            sys.modules.pop('utils.urlguard', None)
        else:
            sys.modules['utils.urlguard'] = cls._saved

    def _assert_not_blocked(self, r, label):
        """断言没有被 safePath 拦（其它失败原因不影响本断言）。"""
        msg = str(r.get('msg') if isinstance(r, dict) else r)
        self.assertNotIn('FILE_DANGER', msg, '%s 仍被 safePath 拦: %r' % (label, r))
        self.assertNotIn('FILE_SENSITIVE_DIR', msg, '%s 仍被写模式拦: %r' % (label, r))

    # ---- 读入口 ----

    def test_10_get_dir_etc(self):
        os_shim = types.SimpleNamespace(
            path=types.SimpleNamespace(exists=lambda p: True))
        fn = _load_route('get_dir', self.file, _Req({'path': '/etc'}), os_shim=os_shim)
        r = fn()
        self._assert_not_blocked(r, 'get_dir(/etc)')
        self.assertIn('count', r, 'get_dir(/etc) 应返回目录列表: %r' % (r,))

    def test_11_get_dir_www_and_server(self):
        """用户点名的两条面包屑：/www 与 /www/server 必须能打开。"""
        os_shim = types.SimpleNamespace(
            path=types.SimpleNamespace(exists=lambda p: True))
        for p in ('/www', '/www/server', '/'):
            fn = _load_route('get_dir', self.file, _Req({'path': p}), os_shim=os_shim)
            r = fn()
            self._assert_not_blocked(r, 'get_dir(%s)' % p)
            self.assertIn('count', r, 'get_dir(%s) 应返回目录列表: %r' % (p, r))

    def test_12_get_dir_real_wwwroot(self):
        d = tempfile.mkdtemp(prefix='yf_pathpolicy_')
        self.addCleanup(__import__('shutil').rmtree, d, True)
        fn = _load_route('get_dir', self.file, _Req({'path': d}))
        r = fn()
        self.assertIsNot(r.get('status'), False, '正常目录被误拒: %r' % (r,))
        self.assertIn('count', r)

    def test_13_check_exists_etc(self):
        fn = _load_route('check_exists_files', self.file, _Req({'dfile': '/etc'}))
        self._assert_not_blocked(fn(), 'check_exists_files(/etc)')

    def test_14_get_dir_size_and_file_access(self):
        fn = _load_route('get_dir_size', self.file, _Req({'path': '/etc'}))
        self._assert_not_blocked(fn(), 'get_dir_size(/etc)')
        fn2 = _load_route('file_access', self.file, _Req({'filename': '/etc/shadow'}))
        self._assert_not_blocked(fn2(), 'file_access(/etc/shadow)')

    # ---- 写/删/下载：只用不存在的路径，绝不真删真写 ----

    def test_15_file_delete_and_dir_delete_not_blocked(self):
        for p in ('/www/server/mysql/yf_policy_probe_absent.cnf',
                  '/www/server/data/yf_policy_probe_absent'):
            self._assert_not_blocked(self.file.fileDelete(p), 'fileDelete(%s)' % p)
            self._assert_not_blocked(self.file.dirDelete(p), 'dirDelete(%s)' % p)

    def test_16_download_file_not_blocked(self):
        fn = _load_route('download_file', self.file, _Req({
            'url': 'http://ok.example/x', 'path': '/www/server/mysql',
            'filename': 'x.txt'}))
        self._assert_not_blocked(fn(), 'download_file -> /www/server/mysql')


class TestStructuralWiring(unittest.TestCase):
    """结构层：各入口仍调 safePath（单一收口点）+ 放宽是可逆开关。"""

    def test_30_read_entries_call_safepath(self):
        for fn in ('check_exists_files', 'get_dir', 'get_dir_size', 'file_access'):
            self.assertTrue(_calls_in_func(fn, 'file.safePath('),
                            '%s 未走 safePath（收口点丢了）' % fn)

    def test_31_write_entry_calls_safepath_write(self):
        self.assertTrue(_calls_in_func('download_file', 'file.safePath(path, write=True)'),
                        'download_file 未以写模式过 safePath')

    def test_32_policy_switch_is_reversible(self):
        """`ALLOW_ALL_PATHS` 开关 + 黑名单判定代码必须都在，方便日后重新收紧。"""
        src = _read(FILE_PY)
        self.assertIn('ALLOW_ALL_PATHS = True', src, '政策开关常量不存在')
        self.assertIn('_SENSITIVE_DATA_PREFIXES', src, '关键数据目录黑名单被删了')
        self.assertIn('_PANEL_SENSITIVE_REL', src, '面板自身资产黑名单被删了')
        tree = ast.parse(src)
        body = ''
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'safePath':
                lines = src.splitlines()
                body = chr(10).join(lines[node.lineno - 1:node.end_lineno])
        self.assertIn('if write:', body, 'safePath 的写模式判定被整段删了')
        self.assertIn('_SENSITIVE_DATA_PREFIXES', body, '写模式判定没保留')


if __name__ == '__main__':
    unittest.main()
