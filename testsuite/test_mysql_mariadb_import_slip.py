# coding: utf-8
"""P1-4 修复守卫：MySQL / MariaDB「导入外部 SQL 包」的 Zip Slip（任意文件写）。

修复前：`plugins/mysql/index.py::importDbExternal()` 与
`plugins/mariadb/index.py::importDbExternal()` 的 zip / tar 分支直接
`zf.extractall(import_dir)` / `tf.extractall(import_dir)`，**从不校验成员名**。
成员名写成 `../evil.txt`、绝对路径或软链逃逸时，解压即写到 import 目录之外
（面板以 root 运行 = 任意文件写）。触发场景：管理员导入他人提供的备份包。

修复后：两个插件的「校验 + 解压」都走同一个小组件
`plugins/mysql/import_archive.py::safeExtractImportArchive()` ——
先 `web/utils/file.py::safeArchiveCheck()` 校验成员名（判据复用，不另写一套），
通过后才 extract / extractall；校验不过或校验函数抛异常一律 fail closed
（不解压、不落任何文件、并删掉被拒的包）。

本用例锁死四件事：

1. 三类恶意归档（`../` 成员 / 绝对路径成员 / 软链逃逸成员）×（zip、tar.gz）
   全部被拒，且**目录外零落盘、目录内无残留**；
2. 合法备份包（只含 `dump.sql`）仍能正常解压，没有 `.sql` 成员时仍走
   `extractall`（防过度拦截、防改坏既有行为）；
3. 校验函数抛异常时同样拒绝（fail closed）；
4. 写法：两个插件的 `importDbExternal()` 里不得再出现裸 `extract` / `extractall`，
   且组件里 `safeArchiveCheck` 的调用必须早于任何解压调用（防「修了一半」）。

为什么选「新建小组件模块」这条路：`plugins/*/index.py` 顶层会 `os.chdir()` 到
`web/`、`sys.path.append` 并拉起面板运行时（`core.yf` 等），用例直接 import 它
既慢又脏；用 `ast` 把函数抽出来 exec 又要自己维护一份依赖环境（见
`test_archive_slip_hardening.py` 里为 file.py 搭的那套）。把「校验 + 解压」收进
`plugins/mysql/import_archive.py` 后，用例按文件路径 import 它即可（零外部依赖、
不动运行时代码结构），两个插件也都调用同一份实现。

本用例**不**改动 `test_archive_slip_hardening.py` 的任何断言；判据冲突以它为准。
"""
import ast
import importlib.util
import io
import os
import shutil
import stat
import sys
import tarfile
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB_DIR = os.path.join(ROOT, 'web')
for _p in (WEB_DIR, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

COMPONENT_PY = os.path.join(ROOT, 'plugins', 'mysql', 'import_archive.py')
IDX_MYSQL = os.path.join(ROOT, 'plugins', 'mysql', 'index.py')
IDX_MARIA = os.path.join(ROOT, 'plugins', 'mariadb', 'index.py')


def _load_component():
    """按文件路径加载被测组件（不 import 插件 index.py：它顶层就 chdir + 拉运行时）。"""
    spec = importlib.util.spec_from_file_location('bt_import_archive_under_test', COMPONENT_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ia = _load_component()


def _read(path):
    with open(path, 'r', encoding='utf-8') as fp:
        return fp.read()


def _walk_files(base):
    """base 下所有文件的相对路径集合（用于「有没有新落文件」的断言）。"""
    out = set()
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            out.add(os.path.relpath(os.path.join(dirpath, name), base))
    return out


# ---------------------------------------------------------------------------
# 归档构造：三类恶意包 + 合法包（zip / tar.gz 各一套）
# ---------------------------------------------------------------------------
def _zip_file(path, member, data):
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr(member, data)


def _zip_symlink(path, member, target):
    with zipfile.ZipFile(path, 'w') as zf:
        info = zipfile.ZipInfo(member)
        info.create_system = 3                     # Unix：外部属性位才带文件类型
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, target)


def _tar_file(path, member, data):
    with tarfile.open(path, 'w:gz') as tf:
        info = tarfile.TarInfo(member)
        raw = data if isinstance(data, bytes) else data.encode('utf-8')
        info.size = len(raw)
        tf.addfile(info, io.BytesIO(raw))


def _tar_symlink(path, member, target):
    with tarfile.open(path, 'w:gz') as tf:
        info = tarfile.TarInfo(member)
        info.type = tarfile.SYMTYPE
        info.linkname = target
        tf.addfile(info)


#: (kind, 形态) -> 构造函数
_BUILDERS = {
    ('zip', 'file'): _zip_file,
    ('zip', 'symlink'): _zip_symlink,
    ('tar', 'file'): _tar_file,
    ('tar', 'symlink'): _tar_symlink,
}

#: 归档扩展名（对应插件里 zip / tar 两条分支）
_SUFFIX = {'zip': '.zip', 'tar': '.tar.gz'}

_KINDS = ('zip', 'tar')


class _SlipCase(unittest.TestCase):
    """公共夹具：每个用例一份临时根目录，解压目标固定为 `<root>/import`。"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='bt_import_slip_')
        self.import_dir = os.path.join(self.root, 'import')
        os.makedirs(self.import_dir)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _fresh(self):
        """subTest 里换一套干净的临时目录（避免上一个 kind 的残留影响断言）。"""
        self.tearDown()
        self.setUp()

    def _make(self, kind, form, member, data):
        path = os.path.join(self.import_dir, 'backup' + _SUFFIX[kind])
        _BUILDERS[(kind, form)](path, member, data)
        return path

    # -- 断言助手 ---------------------------------------------------------
    def _assert_rejected(self, kind, form, member, data, code, outside):
        """恶意包必须被拒：目录外零落盘、目录内无残留（被拒的包本身也被清掉）。"""
        path = self._make(kind, form, member, data)
        before = _walk_files(self.root)
        ok, import_sql, msg = ia.safeExtractImportArchive(
            path, self.import_dir, kind, 'dump.sql')
        self.assertFalse(ok, '%s/%s 恶意包未被拒绝: msg=%r' % (kind, form, msg))
        self.assertEqual('', import_sql, '被拒的包不得给出待导入的 SQL 路径')
        self.assertIn(code, msg, '失败原因里必须带被拒的拒绝码 %s: %r' % (code, msg))
        new_files = _walk_files(self.root) - before
        self.assertEqual(set(), new_files, '%s/%s 恶意包新落了文件: %s'
                         % (kind, form, sorted(new_files)))
        self.assertEqual([], os.listdir(self.import_dir),
                         '导入目录内必须无残留，实际: %s' % sorted(os.listdir(self.import_dir)))
        for p in outside:
            self.assertFalse(os.path.exists(p), '目录外出现被写入的文件: %s' % p)

    # 1) 含 `../evil.txt` 成员的包 -----------------------------------------
    def test_parent_ref_member_rejected(self):
        for kind in _KINDS:
            with self.subTest(kind=kind):
                self._fresh()
                self._assert_rejected(kind, 'file', '../evil.txt', 'pwned',
                                      'parent_ref',
                                      [os.path.join(self.root, 'evil.txt')])

    # 2) 含绝对路径成员的包 -------------------------------------------------
    def test_absolute_path_member_rejected(self):
        for kind in _KINDS:
            with self.subTest(kind=kind):
                self._fresh()
                # 成员名写成「临时根目录下 evil_abs.txt」的绝对路径：一旦放行解压，
                # 这个文件就正好落在我们断言的位置
                target = os.path.join(self.root, 'evil_abs.txt')
                member = target.replace(os.sep, '/')
                self._assert_rejected(kind, 'file', member, 'pwned',
                                      'absolute_path', [target])

    # 3) 含软链逃逸成员的包 -------------------------------------------------
    def test_symlink_escape_member_rejected(self):
        for kind in _KINDS:
            with self.subTest(kind=kind):
                self._fresh()
                self._assert_rejected(kind, 'symlink', 'link', '../evil_link.txt',
                                      'symlink_escape',
                                      [os.path.join(self.root, 'evil_link.txt')])

    # 4) 回归：合法备份包仍能正常解压 ---------------------------------------
    def test_legit_archive_still_extracts(self):
        for kind in _KINDS:
            with self.subTest(kind=kind):
                self._fresh()
                path = self._make(kind, 'file', 'dump.sql', 'SELECT 1;')
                ok, import_sql, msg = ia.safeExtractImportArchive(
                    path, self.import_dir, kind, 'dump.sql')
                self.assertTrue(ok, '合法备份包被误拒: %r' % msg)
                self.assertEqual(os.path.join(self.import_dir, 'dump.sql'), import_sql)
                with open(import_sql, 'r', encoding='utf-8') as fp:
                    self.assertEqual('SELECT 1;', fp.read())
                # 导入目录内：解出来的 dump.sql + 原始包本身（合法包按既有行为保留）
                self.assertEqual({'dump.sql', 'backup' + _SUFFIX[kind]},
                                 _walk_files(self.import_dir),
                                 '解压产物只能出现在导入目录内')
                self.assertEqual({'import'}, set(os.listdir(self.root)),
                                 '解压不得在导入目录之外落任何文件')

    # 5) 回归：没有 .sql 成员时仍走 extractall（既有行为不变）---------------
    def test_no_sql_member_still_extractall(self):
        for kind in _KINDS:
            with self.subTest(kind=kind):
                self._fresh()
                path = self._make(kind, 'file', 'notes.txt', 'hello')
                ok, import_sql, msg = ia.safeExtractImportArchive(
                    path, self.import_dir, kind, 'dump.sql')
                self.assertTrue(ok, '合法包（无 .sql 成员）被误拒: %r' % msg)
                self.assertEqual('', import_sql)
                self.assertEqual({'notes.txt', 'backup' + _SUFFIX[kind]},
                                 _walk_files(self.import_dir),
                                 'extractall 分支应把成员解到导入目录内')

    # 6) fail closed：校验函数抛异常也必须拒绝 -------------------------------
    def test_checker_exception_is_fail_closed(self):
        path = self._make('zip', 'file', 'dump.sql', 'SELECT 1;')
        before = _walk_files(self.root)
        origin = ia._safeArchiveCheck

        def _boom(*_args, **_kwargs):
            raise RuntimeError('校验器挂了')

        ia._safeArchiveCheck = _boom
        try:
            ok, import_sql, msg = ia.safeExtractImportArchive(
                path, self.import_dir, 'zip', 'dump.sql')
        finally:
            ia._safeArchiveCheck = origin
        self.assertFalse(ok, '校验函数抛异常时必须按失败处理（fail closed）')
        self.assertEqual('', import_sql)
        self.assertIn('fail-closed', msg)
        self.assertEqual(set(), _walk_files(self.root) - before, '异常路径也不得落文件')
        self.assertEqual([], os.listdir(self.import_dir))


# ---------------------------------------------------------------------------
# 写法守卫：两个插件必须走同一组件，且组件里校验早于解压
# ---------------------------------------------------------------------------
def _find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _call_names(node, wanted):
    """收集 node 子树里对 wanted 集合内名字（Name 或 .attr）的调用节点。"""
    out = []
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name):
            name = f.id
        elif isinstance(f, ast.Attribute):
            name = f.attr
        else:
            name = ''
        if name in wanted:
            out.append(n)
    return out


class WiringGuard(unittest.TestCase):
    """「两个插件都调组件」与「组件里先校验后解压」的静态守卫。"""

    def test_plugins_have_no_raw_extract(self):
        for path in (IDX_MYSQL, IDX_MARIA):
            with self.subTest(plugin=os.path.basename(os.path.dirname(path))):
                fn = _find_func(ast.parse(_read(path)), 'importDbExternal')
                self.assertIsNotNone(fn, '%s 找不到 importDbExternal' % path)
                raw = _call_names(fn, {'extract', 'extractall'})
                self.assertEqual([], [n.lineno for n in raw],
                                 '%s 的 importDbExternal 里不得再有裸 extract/extractall' % path)

    def test_plugins_call_component_for_zip_and_tar(self):
        for path in (IDX_MYSQL, IDX_MARIA):
            with self.subTest(plugin=os.path.basename(os.path.dirname(path))):
                fn = _find_func(ast.parse(_read(path)), 'importDbExternal')
                kinds = set()
                for call in _call_names(fn, {'_safeExtractImportArchive'}):
                    for arg in call.args:
                        if isinstance(arg, ast.Constant) and arg.value in _KINDS:
                            kinds.add(arg.value)
                self.assertEqual({'zip', 'tar'}, kinds,
                                 '%s 的 zip / tar 两个分支都必须过组件校验' % path)

    def test_component_checks_before_extract(self):
        fn = _find_func(ast.parse(_read(COMPONENT_PY)), 'safeExtractImportArchive')
        self.assertIsNotNone(fn, '组件里找不到 safeExtractImportArchive')
        checks = _call_names(fn, {'_safeArchiveCheck'})
        extracts = _call_names(fn, {'_extractZip', '_extractTar'})
        self.assertTrue(checks, '组件必须先调 safeArchiveCheck 校验成员名')
        self.assertEqual(2, len(extracts), '组件必须同时覆盖 zip 与 tar 两个解压分支')
        self.assertLess(min(c.lineno for c in checks), min(c.lineno for c in extracts),
                        'safeArchiveCheck 必须早于任何解压调用')


if __name__ == '__main__':
    unittest.main(verbosity=2)
