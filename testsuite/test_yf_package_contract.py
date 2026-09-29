# -*- coding: utf-8 -*-
"""`web/core/yf` 拆包契约守卫（2026-09-29）。

背景：`web/core/yf.py`（3206 行 / 197 个顶层函数）被拆成 `web/core/yf/` 包
（10 个子模块 + 门面 `__init__.py`），搬迁由 `scripts/tools/split_yf_module.py`
机械完成。拆包**唯一容易静默出事的地方**是「猴子补丁语义」：

* testsuite 有 21 个符号被 `yf.X = ...` 或 `patch.object(yf, 'X')` 替换过；
* 这些符号被 yf 内部函数调用了大量次数（execShell 23 处、getPanelDir 18 处……）；
* 单文件时代，内部裸名调用天然看到补丁；拆包后如果子模块用
  `from . import execShell` **静态导入**，补丁就失效了 —— 表现为
  「补丁设了、内部调用仍走真实实现」的**假绿**（测试通过但没测到东西）。

因此设计上：这些符号**定义留在 `__init__.py`**，子模块里对它们的调用一律走
`_pkg()` 运行时解析的 shim。本用例把这条不变量、符号完整性、以及
「补丁集是否已过期」全部钉住。
"""

import ast
import os
import re
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.join(ROOT, 'web') not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, 'web'))

from testsuite._yf_pkg import module_files, is_packaged  # noqa: E402

CODEMOD = os.path.join(ROOT, 'scripts', 'tools', 'split_yf_module.py')


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


def _codemod_set(name):
    """从 codemod 里取出 `NAME = {...}` 的字符串集合（保持单一真源）。"""
    tree = ast.parse(_read(CODEMOD))
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id == name:
            return {e.value for e in node.value.elts}
    raise AssertionError('codemod 里找不到 %s' % name)


def _scan_patched_in_testsuite():
    """扫描 testsuite，返回被补丁的 yf 符号集（两种机制都要算）。

    用 AST 而不是正则：正则会把**文档字符串/注释里举例的**
    `patch.object(yf, 'X')` 也当成真实补丁（本用例自己的 docstring 就踩过）。
    """
    found = set()
    for name in sorted(os.listdir(HERE)):
        if not name.endswith('.py'):
            continue
        tree = ast.parse(_read(os.path.join(HERE, name)))
        for node in ast.walk(tree):
            # A) yf.X = ...
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) \
                            and tgt.value.id == 'yf':
                        found.add(tgt.attr)
            # B) patch.object(yf, 'X') / patch('core.yf.X')
            if not isinstance(node, ast.Call):
                continue
            args = node.args
            func = node.func
            is_patch = (isinstance(func, ast.Name) and func.id == 'patch') or \
                       (isinstance(func, ast.Attribute) and func.attr == 'object')
            if not is_patch or not args:
                continue
            first = args[0]
            if isinstance(first, ast.Name) and first.id == 'yf' and len(args) > 1 \
                    and isinstance(args[1], ast.Constant) and isinstance(args[1].value, str):
                found.add(args[1].value)
            elif isinstance(first, ast.Constant) and isinstance(first.value, str) \
                    and first.value.startswith('core.yf.'):
                found.add(first.value.split('.', 2)[2])
    return found


@unittest.skipUnless(is_packaged(), '当前为单文件形态，拆包契约用例不适用')
class TestYfPackageShape(unittest.TestCase):
    """一、包形态与符号完整性"""

    @classmethod
    def setUpClass(cls):
        import core.yf as yf
        cls.yf = yf

    def test_01_package_layout(self):
        """包内必须有门面 + 子模块，且没有遗留的 web/core/yf.py"""
        self.assertFalse(os.path.exists(os.path.join(ROOT, 'web', 'core', 'yf.py')),
                         '拆包后不得再残留单文件（会与包同名遮蔽）')
        files = module_files()
        self.assertGreaterEqual(len(files), 5, '子模块数量异常：%r' % files)
        self.assertIn('__init__.py', [os.path.basename(f) for f in files])

    def test_02_panel_root_dir_points_to_panel_root(self):
        """_PANEL_ROOT_DIR 必须仍指向面板根（包内多了一层目录，易算错）"""
        expected = os.path.join(ROOT, 'web')
        self.assertEqual(self.yf._PANEL_ROOT_DIR, os.path.dirname(expected))
        self.assertEqual(self.yf.getPanelDir(), self.yf._PANEL_ROOT_DIR)

    def test_03_reexport_block_resolves(self):
        """门面里 `from .x import ...` 列的每个名字都必须真的能取到"""
        init_src = _read(os.path.join(ROOT, 'web', 'core', 'yf', '__init__.py'))
        names = set()
        for line in init_src.splitlines():
            if line.startswith('from .') and ' import ' in line:
                names |= {x.strip() for x in line.split(' import ', 1)[1].split(',')}
        self.assertGreater(len(names), 150, '重导出清单过短，疑似搬迁漏项')
        missing = sorted(n for n in names if not hasattr(self.yf, n))
        self.assertEqual([], missing, '门面重导出的名字取不到：%r' % missing)

    def test_04_symbol_floor(self):
        """公开符号数不得少于拆包前（拆包只能搬家，不能丢东西）"""
        public = [n for n in dir(self.yf) if not n.startswith('__')]
        self.assertGreaterEqual(len(public), 233,
                                '符号数少于拆包前的 233，疑似丢函数：%d' % len(public))

    def test_05_key_api_surface_alive(self):
        """跨模块抽样：搬迁后 API 面必须仍然可用"""
        for name in ('execShell', 'safeExecShell', 'getPanelDir', 'getServerDir', 'readFile',
                     'writeFile', 'writeFileLog', 'M', 'checkPid', 'removeDir', 'getOs',
                     'getLocalIp', 'getAcmeDir', 'returnJson', 'invalidPathReason',
                     'getGithubProxyInfo', '_load_github_proxy_list', 'aesEncrypt', 'md5',
                     'getDate', 'getOsName', 'opWeb', 'httpGet'):
            self.assertTrue(hasattr(self.yf, name), '缺少 API：%s' % name)


@unittest.skipUnless(is_packaged(), '当前为单文件形态，拆包契约用例不适用')
class TestMonkeyPatchSemantics(unittest.TestCase):
    """二、猴子补丁语义（拆包最大的静默风险）"""

    @classmethod
    def setUpClass(cls):
        import core.yf as yf
        import core.yf.shell as shell_mod
        cls.yf = yf
        cls.shell = shell_mod

    def test_06_patched_symbol_is_real_definition_not_shim(self):
        """`yf.X` 必须是真实定义（补丁替换的就是它），而不是子模块里的 shim"""
        for name in ('execShell', 'safeExecShell', 'readFile', 'writeFile', 'writeFileLog',
                     'getPanelDir', 'getServerDir', 'getPluginDir', 'getOs', 'checkPid',
                     'removeDir', 'isSupportSystemctl', 'getPanelDataDir', 'systemdCfgDir',
                     'M', 'writeLog', 'opWeb', 'httpGet', 'hasPwd', 'returnData',
                     'isAppleSystem'):
            self.assertEqual('core.yf', getattr(self.yf, name).__module__,
                             '%s 被 shim 覆盖了，补丁会打空' % name)

    def test_07_shim_resolves_through_package_at_call_time(self):
        """子模块里的 shim 必须运行时经包解析——补丁设上就必须被 shim 看到"""
        with mock.patch.object(self.yf, 'execShell', return_value=('PATCHED', '')):
            self.assertEqual(('PATCHED', ''), self.shell.execShell('anything'))
        self.assertNotEqual(('PATCHED', ''), self.shell.execShell('anything'))

    def test_08_internal_caller_sees_getpanelDir_patch(self):
        """端到端：补 yf.getPanelDir → net.getLocalIp 必须读被补目录下的 iplist"""
        with mock.patch.object(self.yf, 'getPanelDir', return_value='/tmp/__yf_patch_probe__'), \
             mock.patch.object(self.yf, 'readFile', return_value='10.9.8.7'):
            self.assertEqual('10.9.8.7', self.yf.getLocalIp())

    def test_09_internal_caller_sees_isapplesystem_and_execshell_patch(self):
        """端到端：补 yf.isAppleSystem + yf.execShell → paths.getAcmeDir 走 macOS 分支"""
        with mock.patch.object(self.yf, 'isAppleSystem', return_value=True), \
             mock.patch.object(self.yf, 'execShell', return_value=('alice', '')):
            self.assertEqual('/Users/alice/.acme.sh', self.yf.getAcmeDir())

    def test_10_no_static_import_of_patched_names(self):
        """子模块不得静态 `from . import <被补丁符号>`（那会让补丁失效）"""
        patched = _codemod_set('PATCHED_FUNCS')
        offenders = []
        for path in module_files():
            if os.path.basename(path) == '__init__.py':
                continue
            for line in _read(path).splitlines():
                if not (line.startswith('from .') and ' import ' in line):
                    continue
                imported = {x.strip() for x in line.split(' import ', 1)[1].split(',')}
                for name in sorted(imported & patched):
                    offenders.append('%s: %s' % (os.path.basename(path), name))
        self.assertEqual([], offenders, '这些被补丁符号被静态导入了：%r' % offenders)

    def test_11_every_shim_is_documented_and_alone(self):
        """有 shim 的子模块必须带 `_pkg` 定义（shim 依赖它），且 shim 名不出现在重导出清单"""
        init_src = _read(os.path.join(ROOT, 'web', 'core', 'yf', '__init__.py'))
        reexported = set()
        for line in init_src.splitlines():
            if line.startswith('from .') and ' import ' in line:
                reexported |= {x.strip() for x in line.split(' import ', 1)[1].split(',')}
        for path in module_files():
            src = _read(path)
            base = os.path.basename(path)
            if base == '__init__.py' or '_pkg()' not in src:
                continue
            self.assertIn('def _pkg():', src, '%s 用了 shim 却没有 _pkg 定义' % base)
            for name in re.findall(r'^def (\w+)\(\*args, \*\*kwargs\):\n    return _pkg\(\)',
                                   src, re.M):
                self.assertNotIn(name, reexported,
                                 '%s 的 shim %s 进了重导出清单（会自我覆盖成死循环）' % (base, name))


@unittest.skipUnless(is_packaged(), '当前为单文件形态，拆包契约用例不适用')
class TestPatchedSetFreshness(unittest.TestCase):
    """三、补丁集新鲜度（新增补丁目标时必须回来更新 codemod）"""

    def test_12_codemod_covers_all_patched_symbols(self):
        """testsuite 里实际补丁过的 yf 符号，必须都在 codemod 的补丁集里

        否则新加一处 `patch.object(yf, 'X')` 时，X 若被搬到子模块且用静态导入，
        补丁会静默失效——本用例就是为了让这种「悄悄失效」变成红灯。
        """
        declared = _codemod_set('PATCHED_FUNCS') | _codemod_set('PATCHED_STATE')
        found = _scan_patched_in_testsuite()
        missing = sorted(found - declared)
        self.assertEqual([], missing,
                         '这些符号被测试补丁过但 codemod 未登记（请更新 PATCHED_FUNCS/'
                         'PATCHED_STATE 并重跑 scripts/tools/split_yf_module.py）：%r' % missing)

    def test_13_codemod_declares_scan_derived_set(self):
        """补丁集必须保持「扫描派生」的规模（防止有人手工删条目）"""
        declared = _codemod_set('PATCHED_FUNCS')
        self.assertGreaterEqual(len(declared), 20,
                                'PATCHED_FUNCS 条目过少，疑似被手工删减：%d' % len(declared))


if __name__ == '__main__':
    unittest.main(verbosity=2)
