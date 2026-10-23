# coding: utf-8
"""P2-10 修复守卫：插件 zip 包导入的「解压前成员校验」（Zip Slip / 软链逃逸）。

修复前 `web/utils/plugin.py`：

- `updateZip()`：`request_zip.save()` 之后**直接** `yf.safeExecShell(['unzip', ...])`，
  成员名从不校验 —— 只靠 `unzip` 自带的消毒，再加一道**事后**的 `_has_symlink()`
  （文件已经落到临时目录/临时目录之外了，事后再删也补不回「已写出去」的字节）；
- `inputZipApi()`：同样只有事后的软链检查（它是 `/plugins/input_zip` 的独立入口，
  直接调用可以完全绕过 `updateZip`）。

修复后（同一套判据，不另写）：

1. `updateZip()` 先调 `_safeExtractPluginZip()` → 内部 `utils.file.safeArchiveCheck(pkg, dest, 'zip')`
   （与 P0-3 的 `unzip`、P1-4 的 `plugins/mysql/import_archive.py` 同一份判据）；
2. 被拒 / 校验函数取不到 / 校验抛异常 → 一律 **fail-closed**：删掉临时 zip、
   清空解压目录、返回中文拒绝原因（含被拒 code），**一个文件都不落地**；
3. 校验通过才 `unzip`，且**保留**解压后的 `_has_symlink()` 作为第二道（纵深防御）。

断言策略（本文件是**零外部依赖**、可独立跑）：

- 真实 zip 夹具（`tempfile` + `zipfile` 现场造）：`../evil.txt`、绝对路径成员、
  软链逃逸成员（zip 的软链只是 external_attr 元数据，**造它不需要 root/POSIX**，
  故本机（Windows）不 skip）；
- 真跑 `updateZip()` / `inputZipApi()`（面板目录用 `yf.getPanelDir` 指到临时区，
  绝不碰真实 `plugins/`）；解压命令用记录型替身（有 `unzip` 就发真命令，
  没有就用标准库落盘），既能断言「校验失败一次解压都没发出去」，
  又能断言合法包确实解压成功；
- 静态面：`updateZip` 的校验调用早于解压、`inputZipApi` 也有自校验、
  事后 `_has_symlink` 未被删、`plugin.py` 里只有一条解压路径（`'unzip'` 字面量 1 处）。
"""
import ast
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('YF_P2_10_ROOT') or os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.yf as yf  # noqa: E402
from testsuite._isolation import isolate  # noqa: E402

# 进程级隔离：必须早于 import thisdb / utils.plugin（它们在导入期就会打开面板库）
_PANEL_TMP, _SERVER_TMP = isolate('p2_10_zipslip')

import utils.file as file_utils  # noqa: E402
import utils.plugin as plugin_util  # noqa: E402
from utils.plugin import plugin as PluginCls  # noqa: E402

PLUGIN_PY = os.path.join(WEB, 'utils', 'plugin.py')

#: 解压命令的原实现（打桩前抓在手里，便于「有 unzip 就跑真命令」）
_REAL_SAFE_EXEC_SHELL = yf.safeExecShell


# ---------------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------------
def _read_plugin_py():
    with open(PLUGIN_PY, encoding='utf-8') as fh:
        return fh.read()


def _func_node(name):
    tree = ast.parse(_read_plugin_py())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError('plugin.py 里找不到函数 %s' % name)


def _func_src(name):
    """函数源码（含缩进与注释，按行切片 —— 行号相关断言要用它）。"""
    src = _read_plugin_py()
    node = _func_node(name)
    return '\n'.join(src.splitlines()[node.lineno - 1:node.end_lineno])


def _make_zip(path, entries):
    """按 [(成员名, 内容)] 造 zip；成员名原样写入（不做任何消毒）。"""
    with zipfile.ZipFile(path, 'w') as zf:
        for name, data in entries:
            # ZipInfo 保留原始成员名（含 '/' 开头与 '..'），writestr 不会净化
            zf.writestr(zipfile.ZipInfo(name), data)
    return path


def _make_symlink_zip(path, link_name, target):
    """造一个「软链成员」zip：软链只是 zip 的 external_attr 元数据 + 内容=目标路径。

    因此不需要 POSIX 特权（Windows 上也能造），断言 `safeArchiveCheck` 会据此拒绝。
    """
    info = zipfile.ZipInfo(link_name)
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr(info, target)
    return path


def _make_clean_zip(path, plugin_name='p2pkg'):
    """合法插件包：info.json + 一个 .py。"""
    info = {
        'name': plugin_name,
        'title': 'P2-10 clean',
        'versions': '1.0',
        'author': 'case',
        'ps': 'clean package',
    }
    return _make_zip(path, [
        ('info.json', json.dumps(info)),
        ('main.py', 'print("ok")\n'),
    ])


class _FakeUpload(object):
    """werkzeug `FileStorage` 的最小替身：只有 `filename` 与 `save()`。"""

    def __init__(self, src_path, filename='plugin.zip'):
        self._src = src_path
        self.filename = filename

    def save(self, dst_path):
        shutil.copyfile(self._src, dst_path)


class _ExtractRecorder(object):
    """记录「解压命令」的替身：有 unzip 就发真命令，没有就用标准库落盘。

    它只替换子进程调用这一层，**被测代码照旧发 `['unzip', ...]`**：
    校验失败时这里必须一次都没被调用（这才是「解压前校验」的运行时证据）。
    """

    def __init__(self):
        self.calls = []
        self.unzip_bin = shutil.which('unzip')

    def __call__(self, cmd_list, *args, **kwargs):
        self.calls.append(list(cmd_list))
        if not cmd_list or cmd_list[0] != 'unzip':
            return ('', '')
        if self.unzip_bin:
            return _REAL_SAFE_EXEC_SHELL(cmd_list, *args, **kwargs)
        # 本机无 unzip：用标准库完成同样的落盘（纯测试替身，不参与判定）
        zip_path = cmd_list[3]
        dest_dir = cmd_list[cmd_list.index('-d') + 1]
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest_dir)
        return ('', '')


def _snapshot(base, skip_top=('data', 'logs')):
    """目录树快照（相对路径集合）；只跳过面板自身的库与日志目录。"""
    out = set()
    for root, dirs, files in os.walk(base):
        rel = os.path.relpath(root, base)
        top = rel.split(os.sep)[0]
        if top in skip_top:
            dirs[:] = []
            continue
        for name in files:
            out.add(os.path.normpath(os.path.join(rel, name)))
    return out


class _WithoutAttr(object):
    """临时把某个属性「摘掉」（模拟校验函数缺失），退出时还原。"""

    def __init__(self, obj, name):
        self.obj = obj
        self.name = name
        self._had = hasattr(obj, name)
        self._val = getattr(obj, name, None)

    def __enter__(self):
        if self._had:
            delattr(self.obj, self.name)
        return self

    def __exit__(self, *exc):
        if self._had:
            setattr(self.obj, self.name, self._val)
        else:
            try:
                delattr(self.obj, self.name)
            except AttributeError:
                pass
        return False


# ---------------------------------------------------------------------------------
# 行为：updateZip（解压前校验 → 零落地 / 合法包放行）
# ---------------------------------------------------------------------------------
class PluginZipUpdateSlipTest(unittest.TestCase):
    def setUp(self):
        self.panel = tempfile.mkdtemp(prefix='yf_p2_10_panel_')
        self.work = tempfile.mkdtemp(prefix='yf_p2_10_work_')
        # 面板目录整体指到临时区：绝不碰真实 plugins/ 与真实 temp/
        self._orig_panel = yf.getPanelDir
        yf.getPanelDir = lambda: self.panel
        self.rec = _ExtractRecorder()
        self._exec_patch = mock.patch.object(yf, 'safeExecShell', self.rec)
        self._exec_patch.start()
        self.inst = PluginCls()

    def tearDown(self):
        self._exec_patch.stop()
        yf.getPanelDir = self._orig_panel
        shutil.rmtree(self.panel, ignore_errors=True)
        shutil.rmtree(self.work, ignore_errors=True)

    # ---------------- 公共断言 ----------------
    def _assert_rejected_cleanly(self, rdata, code, before):
        """被拒 + 临时 zip 已删 + 面板目录里外零新增文件 + 一次解压都没发出去。"""
        self.assertIs(rdata.get('status'), False, '恶意插件包必须被拒: %r' % (rdata,))
        msg = str(rdata.get('msg') or '')
        self.assertIn('已拒绝解压', msg, '拒绝原因要说清「已拒绝解压」: %r' % msg)
        self.assertIn(code, msg, '拒绝原因里要带被拒 code（%s）: %r' % (code, msg))
        self.assertEqual(self.rec.calls, [], '校验失败时不得发出任何解压命令: %r' % (self.rec.calls,))
        # 临时 zip 必须删掉
        self.assertFalse(
            os.path.exists(os.path.join(self.panel, 'temp', 'plugin_tmp.zip')),
            '被拒后临时 zip 必须删除')
        # 解压目录被清空（updateZip 建出来的 temp 目录整个被清）
        temp_dir = os.path.join(self.panel, 'temp')
        self.assertFalse(os.path.exists(temp_dir) and os.listdir(temp_dir),
                         '被拒后解压目录必须是空的/不存在')
        # 面板目录里外零新增
        self.assertEqual(_snapshot(self.panel), before, '被拒后不得有任何新文件落地')
        for leak in (os.path.join(self.panel, 'evil.txt'),
                     os.path.join(self.panel, 'temp', 'evil.txt'),
                     os.path.join(self.panel, 'evil_abs.txt'),
                     os.path.join(self.panel, 'pkg', 'evil_link')):
            self.assertFalse(os.path.exists(leak), '越界成员落盘了: %s' % leak)

    # ---------------- 用例 ----------------
    def test_01_parent_ref_member_rejected_and_nothing_lands(self):
        """`../evil.txt` 成员（经典 Zip Slip）→ 解压前被拒，零新增文件。"""
        zpath = _make_zip(os.path.join(self.work, 'slip.zip'),
                          [('info.json', '{"name": "p2pkg"}'),
                           ('../evil.txt', 'pwned')])
        before = _snapshot(self.panel)
        rdata = self.inst.updateZip(_FakeUpload(zpath))
        self._assert_rejected_cleanly(rdata, 'parent_ref', before)

    def test_02_absolute_path_member_rejected_and_nothing_lands(self):
        """绝对路径成员（`/etc/evil.txt`）→ 解压前被拒，零新增文件。"""
        zpath = _make_zip(os.path.join(self.work, 'abs.zip'),
                          [('info.json', '{"name": "p2pkg"}'),
                           ('/evil_abs.txt', 'pwned')])
        before = _snapshot(self.panel)
        rdata = self.inst.updateZip(_FakeUpload(zpath))
        self._assert_rejected_cleanly(rdata, 'absolute_path', before)

    def test_03_symlink_escape_member_rejected_and_nothing_lands(self):
        """软链逃逸成员（`pkg/evil_link -> ../../etc/passwd`）→ 解压前被拒。

        软链在 zip 里只是 external_attr 元数据，造夹具不需要 root/POSIX，故不 skip。
        另加一条 POSIX 才有的真软链静态面：事后 `_has_symlink` 仍在（见 test_06）。
        """
        zpath = _make_symlink_zip(os.path.join(self.work, 'link.zip'),
                                  'pkg/evil_link', '../../etc/passwd')
        # 先确认夹具真的带上软链元数据（否则本用例会变成「假绿」）
        with zipfile.ZipFile(zpath) as zf:
            infos = zf.infolist()
        self.assertTrue(any(stat.S_ISLNK((i.external_attr >> 16) & 0xFFFF) for i in infos),
                        '夹具没有软链成员，用例无效')
        before = _snapshot(self.panel)
        rdata = self.inst.updateZip(_FakeUpload(zpath))
        self._assert_rejected_cleanly(rdata, 'symlink_escape', before)

    def test_04_validator_missing_or_raising_is_fail_closed(self):
        """校验函数取不到 / 抛异常 → fail-closed 拒绝（不许「无法校验就当通过」）。"""
        zpath = _make_clean_zip(os.path.join(self.work, 'clean_for_failclosed.zip'))

        # (a) 校验函数被摘掉（属性不存在）
        before = _snapshot(self.panel)
        with _WithoutAttr(file_utils, 'safeArchiveCheck'):
            rdata = self.inst.updateZip(_FakeUpload(zpath))
        self.assertIs(rdata.get('status'), False, rdata)
        self.assertIn('fail-closed', str(rdata.get('msg') or ''))
        self.assertEqual(self.rec.calls, [], '取不到校验函数时不得解压')
        self.assertEqual(_snapshot(self.panel), before)
        self.assertFalse(os.path.exists(os.path.join(self.panel, 'temp', 'plugin_tmp.zip')))

        # (b) 校验函数存在但抛异常
        before = _snapshot(self.panel)
        with mock.patch.object(file_utils, 'safeArchiveCheck',
                               side_effect=RuntimeError('校验器异常')):
            rdata = self.inst.updateZip(_FakeUpload(zpath))
        self.assertIs(rdata.get('status'), False, rdata)
        self.assertIn('fail-closed', str(rdata.get('msg') or ''))
        self.assertEqual(self.rec.calls, [], '校验抛异常时不得解压')
        self.assertEqual(_snapshot(self.panel), before)
        self.assertFalse(os.path.exists(os.path.join(self.panel, 'temp', 'plugin_tmp.zip')))

    def test_05_clean_package_still_imports(self):
        """合法包（info.json + main.py）→ 校验通过、正常解压（回归，防过度拦截）。"""
        zpath = _make_clean_zip(os.path.join(self.work, 'clean.zip'))
        rdata = self.inst.updateZip(_FakeUpload(zpath))
        self.assertEqual(rdata.get('name'), 'p2pkg', '合法包必须照旧可用: %r' % (rdata,))
        self.assertEqual(os.path.realpath(rdata.get('tmp_path')),
                         os.path.realpath(os.path.join(self.panel, 'temp')))
        self.assertEqual(len(self.rec.calls), 1, '合法包必须且只解压一次: %r' % (self.rec.calls,))
        self.assertEqual(self.rec.calls[0][0], 'unzip')
        self.assertTrue(os.path.isfile(os.path.join(self.panel, 'temp', 'info.json')))
        self.assertTrue(os.path.isfile(os.path.join(self.panel, 'temp', 'main.py')))
        # 临时 zip 解压完照旧删掉
        self.assertFalse(os.path.exists(os.path.join(self.panel, 'temp', 'plugin_tmp.zip')))

    def test_07_input_zip_entry_self_check(self):
        """`inputZipApi` 是独立入口：源目录含软链必须自校验拒绝（防绕过 updateZip）。"""
        pkg = os.path.join(self.panel, 'temp', 'p2pkg')
        os.makedirs(pkg)
        with open(os.path.join(pkg, 'info.json'), 'w', encoding='utf-8') as fh:
            json.dump({'name': 'p2pkg', 'title': 't', 'versions': '1.0'}, fh)
        link_file = os.path.join(pkg, 'main.py')
        with open(link_file, 'w', encoding='utf-8') as fh:
            fh.write('print(1)\n')

        real_islink = os.path.islink

        def fake_islink(path):
            return os.path.normpath(str(path)) == os.path.normpath(link_file) \
                or real_islink(path)

        with mock.patch('os.path.islink', side_effect=fake_islink):
            rdata = self.inst.inputZipApi('p2pkg', pkg)
        self.assertIs(rdata.get('status'), False, '含软链的插件源目录必须拒收: %r' % (rdata,))
        self.assertFalse(os.path.exists(os.path.join(self.panel, 'plugins', 'p2pkg')),
                         '拒收后不得留下半成品插件目录')

    def test_08_input_zip_accepts_clean_dir(self):
        """干净源目录照旧能导入（回归）。"""
        pkg = os.path.join(self.panel, 'temp', 'p2clean')
        os.makedirs(pkg)
        with open(os.path.join(pkg, 'info.json'), 'w', encoding='utf-8') as fh:
            json.dump({'name': 'p2clean', 'title': 't', 'versions': '1.0'}, fh)
        rdata = self.inst.inputZipApi('p2clean', pkg)
        self.assertIs(rdata.get('status'), True, rdata)
        self.assertTrue(os.path.isfile(
            os.path.join(self.panel, 'plugins', 'p2clean', 'info.json')))


# ---------------------------------------------------------------------------------
# 静态面：顺序、入口覆盖、纵深防御未被删
# ---------------------------------------------------------------------------------
class PluginZipStaticGuardTest(unittest.TestCase):
    def test_06_static_order_and_depth_defense(self):
        src = _read_plugin_py()

        # ① updateZip 里没有任何「裸解压」，解压与校验都收在同一个模块级函数里
        update_src = _func_src('updateZip')
        self.assertIn('_safeExtractPluginZip(', update_src, 'updateZip 必须走校验+解压的统一入口')
        self.assertNotIn("'unzip'", update_src, 'updateZip 里不得再出现裸 unzip 调用')

        # ② 抽出来的函数：校验在解压之前，且带 fail-closed 分支
        helper_src = _func_src('_safeExtractPluginZip')
        self.assertIn('_pluginArchiveCheck(', helper_src)
        self.assertIn("'unzip'", helper_src)
        self.assertLess(helper_src.index('_pluginArchiveCheck('),
                        helper_src.index("'unzip'"),
                        '校验调用必须早于解压调用')
        self.assertIn('fail-closed', helper_src, '取不到/校验抛异常必须 fail-closed')

        # ③ 判据确实来自面板统一函数（不另写一套）
        check_src = _func_src('_pluginArchiveCheck')
        self.assertIn('utils.file', check_src)
        self.assertIn('safeArchiveCheck(', check_src)

        # ④ 行号口径：校验函数定义在解压字符串之前（同一文件内）
        check_line = src.count('\n', 0, src.index('def _pluginArchiveCheck('))
        unzip_line = src.count('\n', 0, src.index("'unzip'"))
        self.assertLess(check_line, unzip_line)

        # ⑤ plugin.py 里只有一条解压路径（'unzip' 字面量恰好 1 处，且在这个函数内）
        self.assertEqual(src.count("'unzip'"), 1,
                         "plugin.py 的解压路径应只有 _safeExtractPluginZip 一处")

        # ⑥ inputZipApi 也自带入口校验，且在 copytree 之前
        input_src = _func_src('inputZipApi')
        self.assertIn('_checkPluginSourceDir(', input_src, 'inputZipApi 必须自校验')
        self.assertLess(input_src.index('_checkPluginSourceDir('),
                        input_src.index('copytree('),
                        'inputZipApi 的校验必须早于 copytree')

        # ⑦ 事后 _has_symlink 仍保留（纵深防御未被删）：updateZip 里它在解压之后
        self.assertIn('_has_symlink(', update_src, '事后的 _has_symlink 检查不得删除')
        self.assertLess(update_src.index('_safeExtractPluginZip('),
                        update_src.index('_has_symlink('),
                        '_has_symlink 必须在解压之后（第二道防线）')
        # 目录形态的入口判据仍然是那份现成的软链检测
        self.assertIn('_has_symlink(', _func_src('_checkPluginSourceDir'))
        # 检测函数本体仍在
        self.assertIn('def _has_symlink(', src)


if __name__ == '__main__':
    unittest.main()
