# coding: utf-8
"""P0-3① 修复守卫：解压成员名校验（Zip Slip 任意文件写）。

修复前（`web/utils/file.py::unzip` / `uncompress`）：压缩包交给
`unzip` / `tar` / `unrar` / `7z` 解压，参数虽已 `shlexQuote`（命令注入那一半历史已堵），
但**压缩包成员名从不校验** —— 成员名写成 `../x` 或 `/etc/x`，解压即写到目标目录之外
（面板以 root 运行 → root 任意文件写）。

修复后：解压前先读成员名走 `safeArchiveMembers()` 校验（zip/tar 用标准库
`zipfile` / `tarfile` 读，rar/7z 用 `unrar lb` / `7z l -slt` 列表解析；读不出来
一律拒绝 = fail closed），校验通过才发解压命令。

本用例锁死四件事（都要求**真能失败**，由 `test/p0_zipslip_mutation_probe.py`
逐个回退修复点自证）：

1. 规则：`safeArchiveMembers()` 逐个拒绝恶意成员名（绝对路径 / `..` / 盘符 / UNC /
   NUL 与控制字符 / 软链逃逸 / realpath 越界），正常成员名放行；
2. 真实压缩包：现场用 `zipfile` / `tarfile` 造出带 `../` 成员与越界软链成员的
   zip / tar.gz，走真实校验路径（`safeArchiveCheck`）断言被拒，且目标目录内外
   都没有新文件落盘；
3. 行为：AST 抽出 `unzip` / `uncompress` 真调用（yf 全 mock，shell 只记账），
   恶意压缩包必须被拒且**一次解压命令都没发出去**；干净压缩包必须仍能解压
   （防过度拦截）；
4. 写法：AST 断言 `unzip` / `uncompress` 的**每个**解压分支都调用了校验函数，
   且校验调用在 shell 调用之前（防「修了一半」）。

注：Python 3.12+ 自带的 `zipfile` / `tarfile` 解压器自身会拦 `../`，但面板**不是**
用它们解压的（走外部 `unzip` / `tar` / `unrar` / `7z`），故守卫按「面板自己的
校验函数」断言，不依赖外部二进制的行为。
"""
import ast
import io
import os
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import unittest
import zipfile
from unittest import mock

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
WEB_DIR = os.path.join(project_dir, 'web')
for _p in (WEB_DIR, project_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.yf as real_yf  # noqa: E402

FILE_PY = os.path.join(WEB_DIR, 'utils', 'file.py')

#: 解压前必须调用的校验函数（分支守卫按名字找）
VALIDATOR_CALLS = {'safeArchiveCheck'}
#: 真正发出去的解压命令（校验必须发生在它之前）
SHELL_CALLS = {'execShell', 'safeExecShell', 'execShellRc'}

#: (成员名, 期望拒绝码) —— 全部必须被拒
MALICIOUS_MEMBERS = [
    ('../evil.txt', 'parent_ref'),                # 经典 Zip Slip
    ('../../etc/passwd', 'parent_ref'),
    ('a/../../b.txt', 'parent_ref'),
    ('a/../b.txt', 'parent_ref'),                 # realpath 后仍在 dest 内，仍须词法拒绝
    ('..', 'parent_ref'),
    ('dir/..', 'parent_ref'),
    ('/etc/passwd', 'absolute_path'),
    ('//server/share/evil.txt', 'absolute_path'),
    ('\\\\server\\share\\evil.txt', 'absolute_path'),   # UNC
    ('\\evil.txt', 'absolute_path'),                    # 根相对（反斜杠归一后是 /evil）
    ('C:evil.txt', 'absolute_path'),                    # 盘符相对
    ('C:\\Windows\\evil.txt', 'absolute_path'),
    ('dir/evil\x00.txt', 'control_char'),               # NUL
    ('dir/evil\ntxt', 'control_char'),
    ('', 'bad_name'),
]

#: 正常成员名（不得误伤）
CLEAN_MEMBERS = [
    'a.txt',
    'dir/b.txt',
    'dir/sub/c.txt',
    'dir/./e.txt',
    'a b.txt',
    'a-b_c.d.txt',
]

#: `7z l -slt` 输出的最小真实形态（首条记录是压缩包自身，在首个分隔线之前）
SEVENZ_SLT_CLEAN = """Listing archive: ok.7z

--
Path = ok.7z
Type = 7z
Physical Size = 132
Headers Size = 122

----------
Path = ok.txt
Size = 5

----------
Path = dir/sub.txt
Size = 7
"""

SEVENZ_SLT_EVIL = SEVENZ_SLT_CLEAN + """
----------
Path = ../pwned_7z.txt
Size = 7
"""


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


def _func_node(name):
    tree = ast.parse(_read(FILE_PY))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError('未找到 %s（file.py 结构变了，守卫需同步）' % name)


def _call_name(call):
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ''


# ---------------------------------------------------------------------------
# 被测代码装载：AST 抽出校验函数 + unzip/uncompress，yf 全 mock（不起 Flask、不连库）
# ---------------------------------------------------------------------------
_KEEP_ASSIGN = {
    'ALLOW_ALL_PATHS', '_SENSITIVE_PATHS', '_SENSITIVE_EXACT', '_SENSITIVE_DATA_PREFIXES',
    '_PANEL_SENSITIVE_REL',
    '_ARCHIVE_CTRL_RE', '_ARCHIVE_DRIVE_RE', '_SEVENZ_RECORD_SEP_RE',
    '_ARCHIVE_REJECT_MSG',
}
_KEEP_CLASS = {'_ArchiveListError'}
_KEEP_FUNC = {
    '_posix_norm', 'safePath',
    '_archiveRejectMsg', '_archiveMemberReason', '_archiveJoin', '_archivePathInside',
    'safeArchiveMembers', 'parseUnrarBareListing', 'parse7zSltListing',
    '_zipArchiveEntries', '_tarArchiveEntries', '_rarArchiveEntries',
    '_7zArchiveEntries', '_gzOutputEntries', 'safeArchiveCheck',
    'unzip', 'uncompress',
}


class _Recorder:
    def __init__(self):
        self.exec_shell = []
        self.exec_shell_rc = []
        self.logs = []


class _FakeYf:
    """只覆盖 shell / 返回值相关的 yf 函数，其余透传真实实现。

    刻意**不**mock `shlexQuote` / `getPanelDir` 的真实语义（前者透传真实实现，
    后者只改根目录），守卫要跟着产品口径走。
    """

    def __init__(self, rec, panel_dir, bins=(), listing=('', 0, '')):
        self.rec = rec
        self.panel_dir = panel_dir
        self.bins = set(bins)
        self.listing = listing          # execShellRc 的返回值 (rc, out, err)

    def __getattr__(self, name):
        return getattr(real_yf, name)

    def getPanelDir(self):
        return self.panel_dir

    def checkBinExist(self, name):
        return name in self.bins

    def execShell(self, cmdstring, *a, **k):
        self.rec.exec_shell.append(cmdstring)
        return ('', '')

    def execShellRc(self, cmdstring, *a, **k):
        self.rec.exec_shell_rc.append(cmdstring)
        rc, out, err = self.listing
        return (rc, out, err)

    @staticmethod
    def returnData(status, msg, data=None, *a, **k):
        return {'status': status, 'msg': msg, 'data': data}

    @staticmethod
    def writeLog(*a, **k):
        return True


class _FakeLog:
    def __init__(self, rec):
        self.rec = rec

    def warning(self, *a, **k):
        self.rec.logs.append(a)

    def debug(self, *a, **k):
        pass


def _load_file_ns(fake_yf, rec):
    """按 AST 抽取节点并编译（不起 Flask、不连库）。"""
    tree = ast.parse(_read(FILE_PY))
    keep = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, 'id', '') in _KEEP_ASSIGN for t in node.targets):
            keep.append(node)
        elif isinstance(node, ast.ClassDef) and node.name in _KEEP_CLASS:
            keep.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in _KEEP_FUNC:
            keep.append(node)
    got_funcs = {n.name for n in keep if isinstance(n, ast.FunctionDef)}
    missing = _KEEP_FUNC - got_funcs
    if missing:
        raise AssertionError('file.py 结构变了，守卫需同步：缺 %s' % sorted(missing))
    ns = {
        'os': os,
        're': re,
        'stat': stat,
        'zipfile': zipfile,
        'tarfile': tarfile,
        'yf': fake_yf,
        '_log': _FakeLog(rec),
        'setMode': lambda *a, **k: None,
        'setFileAccept': lambda *a, **k: None,
    }
    exec(compile(ast.Module(body=keep, type_ignores=[]), FILE_PY, 'exec'), ns)
    return ns


def _snapshot(root):
    """root 下的相对路径集合（用于断言「没有新文件落盘」）。"""
    out = set()
    for base, dirs, files in os.walk(root):
        for name in dirs + files:
            out.add(os.path.relpath(os.path.join(base, name), root))
    return out


def _make_evil_zip(path):
    """带 `../` 成员的 zip（成员名写进归档后确实是 `../`，payload 是真的）。"""
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('ok.txt', 'ok')
        zf.writestr('../pwned_zip.txt', 'pwned')


def _make_evil_tar(path, mode='w:gz'):
    with tarfile.open(path, mode) as tf:
        data = b'ok'
        info = tarfile.TarInfo('ok.txt')
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
        data = b'pwned'
        info = tarfile.TarInfo('../pwned_tar.txt')
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))


#: 走 `tar` 校验的三个压缩分支（tar.gz / tar.xz / tar.bz2）
TAR_MODES = (('w:gz', '.tar.gz'), ('w:xz', '.tar.xz'), ('w:bz2', '.tar.bz2'))


class TestSafeArchiveMembersRules(unittest.TestCase):
    """规则层：纯函数 `safeArchiveMembers` 的判定。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='yf_zipslip_rules_')
        cls.dest = os.path.join(cls.tmp, 'dest')
        os.makedirs(cls.dest)
        rec = _Recorder()
        cls.ns = _load_file_ns(_FakeYf(rec, os.path.join(cls.tmp, 'panel')), rec)
        cls.check = staticmethod(cls.ns['safeArchiveMembers'])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def test_01_clean_members_allowed(self):
        ok, code = self.check(CLEAN_MEMBERS, self.dest)
        self.assertTrue(ok, '正常成员名被误伤：%r（%s）' % (CLEAN_MEMBERS, code))
        self.assertEqual(code, 'OK')

    def test_02_malicious_members_rejected(self):
        for member, expect in MALICIOUS_MEMBERS:
            ok, code = self.check([member], self.dest)
            self.assertFalse(ok, '恶意成员名未被拒绝：%r' % (member,))
            self.assertEqual(code, expect, '成员 %r 的拒绝码不对：%s' % (member, code))

    def test_03_one_bad_member_rejects_whole_archive(self):
        """整包拒绝：坏成员在最后也要拦下（不能只看第一个）。"""
        ok, code = self.check(['a.txt', 'dir/b.txt', '../evil.txt'], self.dest)
        self.assertFalse(ok)
        self.assertEqual(code, 'parent_ref')

    def test_04_symlink_targets_judged_by_resolution(self):
        dest = self.dest
        # 绝对目标 -> 拒绝
        ok, code = self.check(['link'], dest, {'link': '/etc/passwd'})
        self.assertFalse(ok)
        self.assertEqual(code, 'symlink_absolute')
        # 相对但解算后越界 -> 拒绝
        ok, code = self.check(['link'], dest, {'link': '../../etc/passwd'})
        self.assertFalse(ok)
        self.assertEqual(code, 'symlink_escape')
        # Windows 盘符目标 -> 拒绝
        ok, code = self.check(['link'], dest, {'link': 'C:\\Windows\\system32'})
        self.assertFalse(ok)
        self.assertEqual(code, 'symlink_absolute')
        # 目标取不到（读不出软链内容）-> 拒绝
        ok, code = self.check(['link'], dest, {'link': None})
        self.assertFalse(ok)
        self.assertEqual(code, 'symlink_unknown')
        # 指向 dest 内的兄弟文件 -> 放行
        ok, code = self.check(['dir/link'], dest, {'dir/link': '../a.txt'})
        self.assertTrue(ok, '指向 dest 内的软链被误伤：%s' % code)

    def test_05_realpath_boundary_rejects_escape(self):
        """realpath 解算后落到 dest 之外必须被拒（软链逃逸的判据）。

        真实软链在 Windows 上要管理员/开发者模式才能建，故这里用受控的 realpath
        替身把「解算后越界」这一情形固定下来；POSIX 上另有真软链用例（test_06）。
        """
        dest = self.dest
        outside = os.path.join(self.tmp, 'outside', 'evil.txt')
        real_realpath = os.path.realpath

        def fake_realpath(path):
            if os.path.basename(str(path)) == 'evil.txt':
                return outside
            return real_realpath(path)

        with mock.patch.object(os.path, 'realpath', fake_realpath):
            ok, code = self.check(['dir/evil.txt'], dest)
        self.assertFalse(ok, 'realpath 越界的成员未被拒绝')
        self.assertEqual(code, 'outside_dest')

    @unittest.skipIf(os.name == 'nt', 'Windows 建真软链需要管理员/开发者模式')
    def test_06_real_symlink_in_dest_escape_rejected(self):
        dest = os.path.join(self.tmp, 'dest_link')
        outside = os.path.join(self.tmp, 'outside_link')
        os.makedirs(outside)
        os.makedirs(dest)
        os.symlink(outside, os.path.join(dest, 'inside'))
        ok, code = self.check(['inside/evil.txt'], dest)
        self.assertFalse(ok, 'dest 内的软链逃逸未被拒绝')
        self.assertEqual(code, 'outside_dest')

    def test_07_every_reject_code_covered(self):
        """每个拒绝码都要有恶意用例覆盖（防「顺手删掉用例、规则也就没人测了」）。"""
        codes = set()
        for member, _expect in MALICIOUS_MEMBERS:
            codes.add(self.check([member], self.dest)[1])
        codes.add(self.check(['link'], self.dest, {'link': '/etc/passwd'})[1])
        codes.add(self.check(['link'], self.dest, {'link': '../..'})[1])
        codes.add(self.check(['link'], self.dest, {'link': None})[1])
        outside = os.path.join(self.tmp, 'outside', 'evil.txt')
        real_realpath = os.path.realpath

        def fake_realpath(path):
            if os.path.basename(str(path)) == 'evil.txt':
                return outside
            return real_realpath(path)

        with mock.patch.object(os.path, 'realpath', fake_realpath):
            codes.add(self.check(['dir/evil.txt'], self.dest)[1])
        self.assertEqual(codes, {
            'bad_name', 'control_char', 'absolute_path', 'parent_ref',
            'outside_dest', 'symlink_absolute', 'symlink_escape', 'symlink_unknown',
        }, '拒绝码覆盖不全：规则或恶意用例被删了')


class TestSafeArchiveCheckRealArchives(unittest.TestCase):
    """真实压缩包：现场造恶意 zip / tar.gz / 越界软链，走真实校验路径。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_zipslip_arch_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dest = os.path.join(self.tmp, 'dest')
        os.makedirs(self.dest)
        rec = _Recorder()
        self.ns = _load_file_ns(_FakeYf(rec, os.path.join(self.tmp, 'panel')), rec)
        self.check = self.ns['safeArchiveCheck']

    def _assert_nothing_written(self, before, label):
        self.assertEqual(_snapshot(self.tmp), before, '%s：有文件被写到了目标目录之外' % label)

    def test_10_evil_zip_rejected(self):
        zip_path = os.path.join(self.tmp, 'evil.zip')
        _make_evil_zip(zip_path)
        # 夹具自证：`../` 成员确实写进了归档（不是空夹具）
        with zipfile.ZipFile(zip_path) as zf:
            self.assertIn('../pwned_zip.txt', zf.namelist())
        before = _snapshot(self.tmp)
        ok, code = self.check(zip_path, self.dest, 'zip')
        self.assertFalse(ok, '带 `../` 成员的 zip 未被拒绝')
        self.assertEqual(code, 'parent_ref')
        self._assert_nothing_written(before, '恶意 zip')
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'pwned_zip.txt')))

    def test_11_evil_tar_archives_rejected(self):
        """tar.gz / tar.xz / tar.bz2 三个分支都走 tar 成员校验，都要拦下。"""
        for mode, ext in TAR_MODES:
            tar_path = os.path.join(self.tmp, 'evil' + ext)
            _make_evil_tar(tar_path, mode)
            with tarfile.open(tar_path) as tf:
                self.assertIn('../pwned_tar.txt', tf.getnames())
            before = _snapshot(self.tmp)
            ok, code = self.check(tar_path, self.dest, 'tar')
            self.assertFalse(ok, '带 `../` 成员的 %s 未被拒绝' % ext)
            self.assertEqual(code, 'parent_ref')
            self._assert_nothing_written(before, '恶意 %s' % ext)
            self.assertFalse(os.path.exists(os.path.join(self.tmp, 'pwned_tar.txt')))

    def test_12_zip_symlink_member_rejected(self):
        zip_path = os.path.join(self.tmp, 'link.zip')
        with zipfile.ZipFile(zip_path, 'w') as zf:
            info = zipfile.ZipInfo('link')
            info.external_attr = (0o120777 << 16) | 0o777   # S_IFLNK | 0777
            zf.writestr(info, '/etc/passwd')
            zf.writestr('link/evil.txt', 'pwned')           # 两段式：经软链写出去
        ok, code = self.check(zip_path, self.dest, 'zip')
        self.assertFalse(ok, 'zip 里的绝对软链成员未被拒绝')
        self.assertEqual(code, 'symlink_absolute')

    def test_13_tar_symlink_member_rejected(self):
        for linkname, expect in (('/etc/passwd', 'symlink_absolute'),
                                 ('../../etc/passwd', 'symlink_escape')):
            tar_path = os.path.join(self.tmp, 'link.tar.gz')
            with tarfile.open(tar_path, 'w:gz') as tf:
                info = tarfile.TarInfo('link')
                info.type = tarfile.SYMTYPE
                info.linkname = linkname
                tf.addfile(info)
            ok, code = self.check(tar_path, self.dest, 'tar')
            self.assertFalse(ok, 'tar 软链成员 %r 未被拒绝' % (linkname,))
            self.assertEqual(code, expect)

    def test_14_clean_archives_still_pass(self):
        """干净压缩包必须放行（防过度拦截把正常运维堵死）。"""
        zip_path = os.path.join(self.tmp, 'ok.zip')
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('ok.txt', 'ok')
            zf.writestr('dir/sub.txt', 'ok')
        ok, code = self.check(zip_path, self.dest, 'zip')
        self.assertTrue(ok, '正常 zip 被误伤：%s' % code)

        for mode, ext in TAR_MODES:
            tar_path = os.path.join(self.tmp, 'ok' + ext)
            with tarfile.open(tar_path, mode) as tf:
                data = b'ok'
                info = tarfile.TarInfo('dir/sub.txt')
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
            ok, code = self.check(tar_path, self.dest, 'tar')
            self.assertTrue(ok, '正常 %s 被误伤：%s' % (ext, code))

    def test_15_unreadable_archive_fails_closed(self):
        """读不出成员列表（不是 zip / 不是 tar）必须拒绝，不能放行。"""
        bogus = os.path.join(self.tmp, 'bogus.zip')
        with open(bogus, 'wb') as fh:
            fh.write(b'not a zip at all')
        ok, code = self.check(bogus, self.dest, 'zip')
        self.assertFalse(ok, '损坏/伪造的 zip 未被拒绝（fail closed 失效）')
        self.assertEqual(code, 'list_failed')

    def test_16_listing_parsers(self):
        ns = self.ns
        self.assertEqual(ns['parseUnrarBareListing']('ok.txt\n../pwned.txt\n'),
                         ['ok.txt', '../pwned.txt'])
        # `7z l -slt`：压缩包自身那条记录（首个分隔线之前）不算成员
        self.assertEqual(ns['parse7zSltListing'](SEVENZ_SLT_CLEAN),
                         ['ok.txt', 'dir/sub.txt'])
        self.assertIn('../pwned_7z.txt', ns['parse7zSltListing'](SEVENZ_SLT_EVIL))
        # 看不到记录分隔线 = 输出格式不认识 -> 抛错（由 safeArchiveCheck 转成拒绝）
        with self.assertRaises(ns['_ArchiveListError']):
            ns['parse7zSltListing']('Path = ok.txt\nSize = 5\n')
        # gz 单文件：落盘名固定为去掉 .gz 的 basename
        self.assertEqual(ns['_gzOutputEntries']('/tmp/x/ok.txt.gz')[0], ['ok.txt'])
        with self.assertRaises(ns['_ArchiveListError']):
            ns['_gzOutputEntries']('/tmp/x/ok.zip')


class TestUncompressBehavior(unittest.TestCase):
    """行为层：AST 抽出 unzip/uncompress 真调用，shell 只记账。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_zipslip_beh_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dest = os.path.join(self.tmp, 'dest')
        os.makedirs(self.dest)
        self.rec = _Recorder()
        self.bins = ('rar', 'unrar', '7z')
        self.listing = ('', 0, '')

    def _ns(self):
        fake = _FakeYf(self.rec, os.path.join(self.tmp, 'panel'),
                       bins=self.bins, listing=self.listing)
        return _load_file_ns(fake, self.rec)

    def _run(self, name, *args):
        before = _snapshot(self.tmp)
        result = self._ns()[name](*args)
        self.assertEqual(_snapshot(self.tmp), before,
                         '%s(%s)：拒绝时仍写盘了'
                         % (name, os.path.basename(str(args[0]))))
        return result

    def test_20_uncompress_rejects_evil_zip(self):
        zip_path = os.path.join(self.tmp, 'evil.zip')
        _make_evil_zip(zip_path)
        result = self._run('uncompress', zip_path, self.dest, self.tmp)
        self.assertFalse(result['status'], '恶意 zip 未被拒绝：%r' % (result,))
        self.assertEqual(self.rec.exec_shell, [], '被拒的 zip 仍发出了解压命令')
        self.assertTrue(self.rec.logs, '拒绝原因没有落日志（排查会瞎）')

    def test_21_uncompress_rejects_evil_tar_archives(self):
        """tar.gz / tar.xz / tar.bz2 三个解压分支都要先校验再拼命令。"""
        for mode, ext in TAR_MODES:
            self.rec.exec_shell[:] = []
            tar_path = os.path.join(self.tmp, 'evil' + ext)
            _make_evil_tar(tar_path, mode)
            result = self._run('uncompress', tar_path, self.dest, self.tmp)
            self.assertFalse(result['status'], '恶意 %s 未被拒绝：%r' % (ext, result))
            self.assertEqual(self.rec.exec_shell, [], '被拒的 %s 仍发出了解压命令' % ext)

    def test_22_uncompress_rejects_evil_rar(self):
        rar_path = os.path.join(self.tmp, 'evil.rar')
        with open(rar_path, 'wb') as fh:
            fh.write(b'Rar!\x1a\x07\x00')          # 内容无关：列表由 mock 给
        self.listing = (0, 'ok.txt\n../pwned_rar.txt\n', '')
        result = self._run('uncompress', rar_path, self.dest, self.tmp)
        self.assertFalse(result['status'], '恶意 rar 未被拒绝：%r' % (result,))
        self.assertEqual(self.rec.exec_shell, [], '被拒的 rar 仍发出了解压命令')
        self.assertTrue(any('unrar' in str(c[0]) for c in self.rec.exec_shell_rc if c),
                        '未先走 unrar 列表命令：%r' % (self.rec.exec_shell_rc,))

    def test_23_uncompress_rejects_evil_7z(self):
        seven_path = os.path.join(self.tmp, 'evil.7z')
        with open(seven_path, 'wb') as fh:
            fh.write(b'7z\xbc\xaf\x27\x1c')
        self.listing = (0, SEVENZ_SLT_EVIL, '')
        result = self._run('uncompress', seven_path, self.dest, self.tmp)
        self.assertFalse(result['status'], '恶意 7z 未被拒绝：%r' % (result,))
        self.assertEqual(self.rec.exec_shell, [], '被拒的 7z 仍发出了解压命令')

    def test_24_rar_7z_listing_failure_fails_closed(self):
        """列表命令失败 / 输出不认识 / 工具缺失，一律拒绝（fail closed）。"""
        rar_path = os.path.join(self.tmp, 'broken.rar')
        with open(rar_path, 'wb') as fh:
            fh.write(b'Rar!\x1a\x07\x00')
        # ① unrar 返回非 0
        self.listing = (2, '', 'unrar: cannot open archive')
        result = self._run('uncompress', rar_path, self.dest, self.tmp)
        self.assertFalse(result['status'], 'unrar 列表失败仍放行：%r' % (result,))
        # ② 7z 输出没有记录分隔线（格式不认识）
        seven_path = os.path.join(self.tmp, 'broken.7z')
        with open(seven_path, 'wb') as fh:
            fh.write(b'7z\xbc\xaf\x27\x1c')
        self.listing = (0, 'Path = ok.txt\nSize = 5\n', '')
        result = self._run('uncompress', seven_path, self.dest, self.tmp)
        self.assertFalse(result['status'], '7z 列表解析不了仍放行：%r' % (result,))
        # ③ unrar 不在 PATH
        self.bins = ('rar', '7z')
        self.listing = (0, 'ok.txt\n', '')
        result = self._run('uncompress', rar_path, self.dest, self.tmp)
        self.assertFalse(result['status'], 'unrar 缺失仍放行：%r' % (result,))
        self.assertEqual(self.rec.exec_shell, [], '校验失败的归档仍发出了解压命令')

    def test_25_uncompress_still_extracts_clean_archives(self):
        """正对照：干净归档必须照旧解压（一条命令，内容不变）。"""
        zip_path = os.path.join(self.tmp, 'ok.zip')
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('ok.txt', 'ok')
        result = self._ns()['uncompress'](zip_path, self.dest, self.tmp)
        self.assertTrue(result['status'], '正常 zip 解压被拒：%r' % (result,))
        self.assertEqual(len(self.rec.exec_shell), 1, self.rec.exec_shell)
        self.assertIn('unzip -o -d', self.rec.exec_shell[0])

        self.rec.exec_shell[:] = []
        self.listing = (0, SEVENZ_SLT_CLEAN, '')
        seven_path = os.path.join(self.tmp, 'ok.7z')
        with open(seven_path, 'wb') as fh:
            fh.write(b'7z\xbc\xaf\x27\x1c')
        result = self._ns()['uncompress'](seven_path, self.dest, self.tmp)
        self.assertTrue(result['status'], '正常 7z 解压被拒：%r' % (result,))
        self.assertEqual(len(self.rec.exec_shell), 1, self.rec.exec_shell)
        self.assertIn('7z x', self.rec.exec_shell[0])

    def test_26_unzip_rejects_evil_archives(self):
        zip_path = os.path.join(self.tmp, 'evil.zip')
        _make_evil_zip(zip_path)
        result = self._run('unzip', zip_path, self.dest, 'zip', self.tmp)
        self.assertFalse(result['status'], 'unzip 路由未拦恶意 zip：%r' % (result,))
        self.assertEqual(self.rec.exec_shell, [], '被拒的 zip 仍发出了解压命令')

        self.rec.exec_shell[:] = []
        tar_path = os.path.join(self.tmp, 'evil.tar.gz')
        _make_evil_tar(tar_path)
        result = self._run('unzip', tar_path, self.dest, 'tar', self.tmp)
        self.assertFalse(result['status'], 'unzip 路由未拦恶意 tar.gz：%r' % (result,))
        self.assertEqual(self.rec.exec_shell, [], '被拒的 tar.gz 仍发出了解压命令')


class TestBranchCoverageAst(unittest.TestCase):
    """写法层：每个解压分支都必须先校验成员名，再发解压命令。"""

    @staticmethod
    def _branches(func_name, subject):
        """解压分派链上的分支体：`<subject> == '...'` 的 if/elif 体，外加 else 体。"""
        branches = []
        for node in ast.walk(_func_node(func_name)):
            if not isinstance(node, ast.If):
                continue
            test = node.test
            if not (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
                    and test.left.id == subject and len(test.ops) == 1
                    and isinstance(test.ops[0], ast.Eq)
                    and isinstance(test.comparators[0], ast.Constant)):
                continue
            branches.append((test.comparators[0].value, node.body, node.lineno))
            if node.orelse and not isinstance(node.orelse[0], ast.If):
                branches.append(('else', node.orelse, node.lineno))
        return branches

    def _assert_branch_validates(self, func_name, subject, expect_count):
        branches = self._branches(func_name, subject)
        self.assertEqual(len(branches), expect_count,
                         '%s 的解压分支数变了（%s），守卫需同步：%r'
                         % (func_name, expect_count, [b[0] for b in branches]))
        for label, body, lineno in branches:
            calls = [c for stmt in body for c in ast.walk(stmt)
                     if isinstance(c, ast.Call)]
            validators = [c.lineno for c in calls if _call_name(c) in VALIDATOR_CALLS]
            shells = [c.lineno for c in calls if _call_name(c) in SHELL_CALLS]
            self.assertTrue(validators,
                            '%s 的 %r 分支没有调用成员名校验（Zip Slip 漏了一半）'
                            % (func_name, label))
            self.assertTrue(shells,
                            '%s 的 %r 分支没有发解压命令（解压被删了？）' % (func_name, label))
            self.assertLess(min(validators), min(shells),
                            '%s 的 %r 分支先解压后校验（等于没校验）' % (func_name, label))

    def test_30_uncompress_every_branch_validates(self):
        self._assert_branch_validates('uncompress', 'extension', 7)

    def test_31_unzip_every_branch_validates(self):
        self._assert_branch_validates('unzip', 'stype', 2)


if __name__ == '__main__':
    unittest.main()
