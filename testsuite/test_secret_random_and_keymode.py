# coding: utf-8
"""
P2-3：安全材料的随机源 + AES 密钥文件落盘权限

两个独立但同源的缺陷：

1. `web/core/yf/textutil.py` 的 `getRandomString()` 用 Mersenne Twister（`Random()`），
   却被用来生产 AES key/iv、面板安全入口（admin_path）、初始管理员账号/口令、
   临时登录 token/盐、数据库口令等安全材料。MT 的输出可由少量输出反推，
   不满足不可预测性。修复方式：**保留函数名/签名/字符集/返回类型**，
   内部改用 `secrets.choice`（CSPRNG），因此 20+ 个调用点零改动。
2. `aes.json`（明文 AES key/vi，面板加密存储的根密钥）落盘时没有收紧权限，
   默认受 umask 影响通常是 0644。修复：写入/读到之后 `os.chmod(..., 0o600)`，
   Windows 上 `os.chmod` 只影响只读位（属已知降级），失败只告警不影响功能。

本用例零外部依赖（只用标准库），并且：

* 用例 3 只是「没有明显退化」的守卫 —— MT 也能通过，**不能**用它证明密码学强度；
* 用例 5 的权限位断言在 Windows 上跳过（`os.chmod` 语义不同），但
  文件仍必须被成功创建且可读；另外用一条**静态断言**（`getAesKey` 函数体内
  必须存在 `os.chmod(aes_file, 0o600)`）保证「删掉 chmod」的变异在任何平台都能被发现。
"""
import ast
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(project_root, 'web')
for _p in (web_dir, project_root):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.yf as yf                                    # noqa: E402
from core.yf import getRandomString                      # noqa: E402

#: 改前的字符集，逐字符抄写（**故意不引用源码常量**，否则字符集被改也测不出来）。
CHARS = set('AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz0123456789')

TEXTUTIL_PATH = os.path.join(web_dir, 'core', 'yf', 'textutil.py')
YF_INIT_PATH = os.path.join(web_dir, 'core', 'yf', '__init__.py')

POSIX = os.name != 'nt'


def _read_src(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


def _source_of_func(path, name):
    """取模块内指定顶层函数的源码文本（按 AST 行号切片，空格/换行原样）。"""
    src = _read_src(path)
    tree = ast.parse(src)
    lines = src.split('\n')
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError('%s 里找不到函数 %s' % (path, name))


class TestGetRandomStringContract(unittest.TestCase):
    """用例 1：字符集与长度契约（对外行为与改前完全一致）"""

    def test_length_and_charset(self):
        for n in (1, 8, 16, 32, 48):
            s = getRandomString(n)
            self.assertIsInstance(s, str)
            self.assertEqual(len(s), n, '长度必须严格等于 %d，实际 %r' % (n, s))
            bad = set(s) - CHARS
            self.assertEqual(bad, set(), '出现了字符集外的字符：%r（值=%r）' % (bad, s))

    def test_zero_and_negative_keep_old_behavior(self):
        # 改前实现是 for i in range(length) 空循环 ⇒ 返回 ''（str 类型）
        self.assertEqual(getRandomString(0), '')
        self.assertIsInstance(getRandomString(0), str)
        self.assertEqual(getRandomString(-1), '')
        self.assertEqual(getRandomString(-99), '')

    def test_non_integer_still_type_error(self):
        # 改前 range(16.0) / range('16') 抛 TypeError —— 契约保持
        with self.assertRaises(TypeError):
            getRandomString(16.0)
        with self.assertRaises(TypeError):
            getRandomString('16')


class TestNoMersenneTwister(unittest.TestCase):
    """用例 2：`getRandomString` 函数体内不得再出现 MT / random 模块调用"""

    def setUp(self):
        self.src = _read_src(TEXTUTIL_PATH)
        self.body = _source_of_func(TEXTUTIL_PATH, 'getRandomString')

    def test_no_random_call_in_body(self):
        # 文本层（保守，先挡最直接的回退写法）
        self.assertNotIn('Random()', self.body, 'getRandomString 内又出现了 Random()')
        self.assertNotIn('random.', self.body, 'getRandomString 内又调用了 random 模块')
        # AST 层：任何 random.* 的属性调用、任何 Random 名字都算违规
        tree = ast.parse(self.body)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertNotEqual(getattr(node.value, 'id', None), 'random',
                                    'getRandomString 内仍调用 random 模块：%s' % node.attr)
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name):
                    self.assertNotIn(fn.id, ('Random', 'SystemRandom'),
                                     'getRandomString 内仍构造 %s()' % fn.id)

    def test_uses_csprng(self):
        # 正向保证（AST 级，不含注释）：确实换成了 CSPRNG —— 函数体里必须有
        # secrets.* 调用（或 os.urandom）。只看代码节点，不会被注释/文档字符串骗过。
        tree = ast.parse(_source_of_func(TEXTUTIL_PATH, 'getRandomString'))
        csprng_calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if isinstance(fn, ast.Attribute):
                if isinstance(fn.value, ast.Name) and fn.value.id in ('secrets', 'os'):
                    csprng_calls.append('%s.%s' % (fn.value.id, fn.attr))
        self.assertTrue(any(c.startswith('secrets.') or c == 'os.urandom' for c in csprng_calls),
                        'getRandomString 未使用 secrets / os.urandom，实际调用：%r' % (csprng_calls,))

    def test_no_mt_import(self):
        # `from random import Random` 已删除（textutil 里没有别的函数用它，
        # 全仓 grep 已确认：Random() 只在原 getRandomString 里出现过）
        self.assertNotIn('from random import Random', self.src)
        self.assertNotIn('import random', self.src)


class TestNotObviouslyDegraded(unittest.TestCase):
    """用例 3/4：弱统计守卫 —— 只能证明「没明显退化」，不能证明密码学强度"""

    def test_200_unique_of_length_16(self):
        # 注：MT 也能过这条，它只是守卫（例如别退化成常量/计数器）。
        vals = [getRandomString(16) for _ in range(200)]
        self.assertEqual(len(set(vals)), 200, '200 次长度 16 生成出现重复，疑似退化为常量/低熵')

    def test_single_char_distribution_not_constant(self):
        chars = set(getRandomString(1) for _ in range(1000))
        self.assertGreaterEqual(len(chars), 50,
                                '1000 次单字符生成只出现 %d 种字符（字符集 62 种），疑似退化' % len(chars))
        self.assertEqual(chars - CHARS, set())


class TestAesJsonMode(unittest.TestCase):
    """用例 5/6：aes.json 落盘 0600，且权限收紧不破坏既有读取逻辑"""

    def setUp(self):
        self._old_cache = yf._aes_key_cache
        yf._aes_key_cache = None            # 清掉进程内缓存，保证每次真跑落盘逻辑
        self._tmp = tempfile.mkdtemp(prefix='yf_aes_')
        self.aes_file = os.path.join(self._tmp, 'aes.json')
        self._patch = mock.patch.object(yf, 'getPanelDataDir', lambda: self._tmp)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        yf._aes_key_cache = self._old_cache

    def _run_getaeskey_recording_chmod(self):
        """调一次 getAesKey()，并记录它对 os.chmod 的全部调用。"""
        calls = []
        real_chmod = os.chmod

        def _rec(path, mode, *a, **kw):
            calls.append((os.path.abspath(str(path)), mode))
            return real_chmod(path, mode, *a, **kw)

        with mock.patch.object(os, 'chmod', _rec):
            got = yf.getAesKey()
        return got, calls

    def test_generated_aes_json_created_and_chmod_called(self):
        got, calls = self._run_getaeskey_recording_chmod()

        # 1) 文件确实被创建（任何平台都必须成立）
        self.assertTrue(os.path.exists(self.aes_file), 'aes.json 没有被创建')

        # 2) 内容可读且合法 —— 证明 chmod 没把文件写成不可读
        with open(self.aes_file, 'r', encoding='utf-8') as fh:
            on_disk = json.load(fh)
        self.assertEqual(set(on_disk), {'key', 'vi'})
        self.assertEqual(on_disk, got)
        for name in ('key', 'vi'):
            self.assertEqual(len(on_disk[name]), 16)
            self.assertEqual(set(on_disk[name]) - CHARS, set())

        # 3) 行为断言（跨平台）：必须真的对 aes.json 调过 os.chmod(..., 0o600)。
        #    这一条让「删掉 chmod」在 Windows 上也能被动态发现（不依赖权限位断言）。
        target = os.path.abspath(self.aes_file)
        self.assertIn((target, 0o600), calls,
                      'getAesKey() 没有对 aes.json 调用 os.chmod(..., 0o600)，实际调用：%r' % (calls,))

    @unittest.skipUnless(POSIX, 'Windows 的 os.chmod 只影响只读位，不做权限位断言（降级已文档化）')
    def test_aes_json_mode_is_0600(self):
        yf.getAesKey()
        mode = stat.S_IMODE(os.stat(self.aes_file).st_mode)
        self.assertEqual(mode, 0o600, 'aes.json 权限应为 0600，实际 %o' % mode)
        msg = 'chmod 之后文件仍可被属主读写（权限 %o）' % mode
        self.assertTrue(os.access(self.aes_file, os.R_OK) and os.access(self.aes_file, os.W_OK), msg)

    def test_existing_aes_json_is_not_broken(self):
        # 预置一对已知 key/vi（模拟老版本 MT 生成并已落盘的 aes.json）
        known = {'key': 'AaBbCcDdEeFfGgHh', 'vi': '0123456789ZzYyXx'}
        with open(self.aes_file, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(known))
        yf._aes_key_cache = None

        got, calls = self._run_getaeskey_recording_chmod()
        self.assertEqual(got, known, '既有 aes.json 的读取逻辑被 chmod 改坏了')
        # 读路径也要顺手收紧（老部署升级后不会重写文件，否则 0644 永远留着）
        target = os.path.abspath(self.aes_file)
        self.assertIn((target, 0o600), calls,
                      '读到既有 aes.json 后没有收紧权限，实际调用：%r' % (calls,))
        # 读路径的顺手收紧也不能破坏内容
        with open(self.aes_file, 'r', encoding='utf-8') as fh:
            self.assertEqual(json.load(fh), known)

    def test_getaeskey_source_has_chmod_0600(self):
        """静态守卫：`getAesKey` 函数体内必须有 `os.chmod(aes_file, 0o600)`。

        为什么需要它：Windows 上上面的权限位断言会 skip，若只靠动态断言，
        「把 chmod 删掉」的变异在 Windows 上不会被发现。AST 断言跨平台有效。
        """
        body = _source_of_func(YF_INIT_PATH, 'getAesKey')
        tree = ast.parse(body)
        hits = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr == 'chmod'):
                continue
            if not (isinstance(fn.value, ast.Name) and fn.value.id == 'os'):
                continue
            args = node.args
            if len(args) < 2:
                continue
            target_ok = isinstance(args[0], ast.Name) and args[0].id == 'aes_file'
            mode_ok = isinstance(args[1], ast.Constant) and args[1].value == 0o600
            if target_ok and mode_ok:
                hits.append(node.lineno)
        self.assertTrue(hits, 'getAesKey() 里找不到 os.chmod(aes_file, 0o600)')
        # 写路径 + 读路径（老文件顺手收紧）各一处
        self.assertGreaterEqual(len(hits), 2,
                                'chmod 覆盖不足，只有 %d 处：%r' % (len(hits), hits))


if __name__ == '__main__':
    unittest.main()
