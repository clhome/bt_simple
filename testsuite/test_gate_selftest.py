# coding: utf-8
"""门禁自身的自证：验证 `run_all.py` 的关键护栏真的会「响」。

## 为什么要有这个文件

本仓库历史上栽过**假门禁**：`python -m unittest` 在**收集不到任何用例**时，
照样打印 `Ran 0 tests ... OK` 并返回 0。如果门禁不校验「收集到的用例数 > 0」，
就会得到一套「永远全绿」的门禁 —— 比没有门禁更危险，因为它给人虚假的安全感。

所以**护栏本身必须有测试**：哪天有人把 `script_style_tests()` 的 `assert` 条件
删了、或把 `ran == 0` 那条分支改成放行，这里必须立刻变红。
（同一个思路见 `scripts/verify_i18n.py --self-test`。）

本模块**不依赖**被 gitignore 的 `test/`，也**不依赖**网络。
"""
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import run_all as gate  # noqa: E402

# 本文件自带的「模块级 assert」判定，**故意不复用** `gate.TOP_ASSERT_RE`：
# 用被守护对象当判定基准是循环论证，护栏会退化成真空通过。详见对应用例的注释。
_TOP_LEVEL_ASSERT = re.compile(r'^assert\b', re.M)


class TestScriptStyleDetection(unittest.TestCase):
    """`script_style_tests()` 决定「哪些模块要改跑 `python testsuite/xxx.py`」。

    判定必须**同时**满足「有 `__main__` 入口」与「全文真的出现过 `assert`」。
    少任何一条，当脚本跑都等于什么都没做 —— 那还是假绿。
    """

    def _write(self, src):
        fd, path = tempfile.mkstemp(suffix='.py', prefix='gate_selftest_')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(src)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_script_style_module_detected(self):
        p = self._write('def test_a():\n    assert 1 == 1\n\n'
                        'if __name__ == "__main__":\n    test_a()\n')
        self.assertEqual(gate.script_style_tests(p), ['test_a'])

    def test_run_tests_entry_detected(self):
        p = self._write('def run_tests():\n    assert True\n\n'
                        'if __name__ == "__main__":\n    run_tests()\n')
        self.assertEqual(gate.script_style_tests(p), ['run_tests'])

    def test_unittest_module_is_not_script_style(self):
        """有 `TestCase` 的模块走 `-m unittest`，不算脚本式。"""
        p = self._write('import unittest\n\n'
                        'class T(unittest.TestCase):\n'
                        '    def test_a(self):\n        assert 1\n')
        self.assertEqual(gate.script_style_tests(p), [])

    def test_main_without_assert_is_not_accepted(self):
        """有 `__main__` 但**没有断言** → 不算（否则当脚本跑等于没验证）。"""
        p = self._write('def test_a():\n    print("hello")\n\n'
                        'if __name__ == "__main__":\n    test_a()\n')
        self.assertEqual(gate.script_style_tests(p), [])

    def test_assert_without_main_is_not_accepted(self):
        """有断言但没有入口 → 不算（`-m unittest` 也收不到它）。"""
        p = self._write('def test_a():\n    assert 1 == 1\n')
        self.assertEqual(gate.script_style_tests(p), [])

    def test_top_level_script_is_detected(self):
        """**顶层直线脚本**：0 个函数、没有 `__main__`，靠模块级 `assert` 断言。

        这种模块当脚本跑是真的会执行断言的，必须识别出来 —— 否则门禁永远
        执行不了它，隔离区的「意外转绿」反向检查对它彻底失明。
        （真实案例：`test_op_waf_full_i18n.py` / `_v2.py`。）
        """
        p = self._write('assert 1 == 1\nprint("ok")\nassert 2 == 2\n')
        self.assertEqual(gate.script_style_tests(p), [gate.TOP_SCRIPT_MARKER])

    def test_top_level_script_without_assert_is_not_accepted(self):
        """顶层脚本但一句 `assert` 都没有 → 还是假绿，不算。"""
        p = self._write('print("什么都没验证")\n')
        self.assertEqual(gate.script_style_tests(p), [])

    def test_indented_assert_is_not_top_level(self):
        """函数**内部**的 `assert` 不算模块级断言，否则「没有入口」的模块会被误放行。"""
        p = self._write('def helper():\n    assert 1 == 1\n')
        self.assertEqual(gate.script_style_tests(p), [])

    def test_no_module_with_top_level_assert_is_missed(self):
        """回归护栏：仓库里凡是「有模块级 `assert`」的模块，都必须被识别为脚本式。

        漏识别 = 门禁不执行它 = 它在隔离区里永远不会被判定为「意外转绿」。

        注意：这里**故意用本文件自己定义的正则**，而不是 `gate.TOP_ASSERT_RE`。
        用被守护对象本身当判定基准是循环论证 —— 一旦那个正则被改坏（或被人
        在变异测试里打桩），扫描集合会一起变空，护栏就变成「真空通过」。
        """
        missed = []
        for m in gate.discover_modules():
            with open(os.path.join(HERE, m), encoding='utf-8') as fp:
                src = fp.read()
            if 'unittest.TestCase' in src:
                continue
            if _TOP_LEVEL_ASSERT.search(src) and not gate.script_style_tests(os.path.join(HERE, m)):
                missed.append(m)
        self.assertEqual(missed, [],
                         '这些模块有模块级 assert 却没被识别为脚本式，门禁不会执行它们：%s' % missed)


class TestFakeGreenGuards(unittest.TestCase):
    """「假绿」防护：`Ran 0 tests ... OK` 绝不能被当成通过。"""

    def test_ran_re_matches_zero(self):
        m = gate.RAN_RE.search('Ran 0 tests in 0.001s\n\nOK\n')
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 0)

    def test_ran_re_matches_singular(self):
        m = gate.RAN_RE.search('Ran 1 test in 0.001s')
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 1)

    def test_ran_re_absent_when_no_tests_reported(self):
        self.assertIsNone(gate.RAN_RE.search('所有测试用例 100% 顺利通过！'))


class TestOverheadDiagnostic(unittest.TestCase):
    """`⚑` 开销诊断：解析「用例本体耗时」，并与进程总耗时对比。

    关键约束：解析不到本体耗时（脚本式用例）时**不参与**告警，
    否则会把本来就不打印这个数字的模块误报成开销异常。
    """

    def test_body_seconds_parsed(self):
        self.assertAlmostEqual(gate.body_seconds('Ran 7 tests in 0.508s'), 0.508)

    def test_body_seconds_takes_max_when_repeated(self):
        """脚本式用例会把两段输出拼在一起，取最大者。"""
        text = 'Ran 3 tests in 0.100s\n...\nRan 5 tests in 2.500s'
        self.assertAlmostEqual(gate.body_seconds(text), 2.5)

    def test_body_seconds_zero_when_unparsable(self):
        self.assertEqual(gate.body_seconds('所有测试用例 100% 顺利通过！'), 0.0)

    def test_overhead_ignores_unparsable_body(self):
        r = {'kind': 'case', 'body': 0.0, 'secs': 300.0, 'name': 'x'}
        self.assertEqual(gate.overhead(r), 0.0)

    def test_overhead_computed(self):
        r = {'kind': 'case', 'body': 0.5, 'secs': 60.5, 'name': 'x'}
        self.assertAlmostEqual(gate.overhead(r), 60.0)

    def test_overhead_zero_for_static_gates(self):
        r = {'kind': 'static', 'secs': 300.0, 'name': 'x'}
        self.assertEqual(gate.overhead(r), 0.0)

    def test_threshold_is_sane(self):
        """阈值太小会天天误报，太大就抓不到 —— 钉在合理区间。"""
        self.assertGreaterEqual(gate.OVERHEAD_WARN_SECONDS, 5.0)
        self.assertLessEqual(gate.OVERHEAD_WARN_SECONDS, 120.0)


class TestDiscoveryAndQuarantine(unittest.TestCase):
    """模块发现与隔离区解析。"""

    def test_discover_only_test_py(self):
        mods = gate.discover_modules()
        self.assertTrue(mods, '一个用例都没发现，说明发现逻辑坏了')
        for m in mods:
            self.assertTrue(m.startswith('test_') and m.endswith('.py'), m)

    def test_isolation_helper_is_not_discovered(self):
        """`_isolation.py` 是共享助手，不能被当成用例模块去跑。"""
        self.assertNotIn('_isolation.py', gate.discover_modules())

    def test_quarantine_parsed_with_reasons(self):
        q = gate.load_quarantine()
        self.assertTrue(q, '隔离区解析为空，说明解析逻辑坏了')
        for mod, reason in q.items():
            self.assertTrue(mod.endswith('.py'), mod)
            self.assertTrue(reason.strip(), '%s 缺少原因' % mod)


class TestStaleQuarantineReason(unittest.TestCase):
    """隔离名单的**另一半**腐烂方式：模块还是红的，但红的原因已经变了。

    「意外转绿」门禁能自动发现；「原因文字对不上实际失败」没人会发现，
    名单就会变成误导后人的假线索 —— 本仓库真出现过：两条写着
    「未收集到用例（导入失败）」的条目，实际原因一个是引用了已删除的
    `plugins/caddy/...`，一个是插件白名单拒绝 `%TEMP%` 路径。

    `stale_reason()` 是**弱校验**：只认「原因里写了异常类型、而该类型在实际
    输出里一个字都找不到」。宁可漏报，不可误报 —— 误报会让这条提示被无视。
    """

    def test_matching_reason_is_not_stale(self):
        self.assertFalse(gate.stale_reason(
            'AssertionError: 4 != 0 : 语言包 [en] 缺失核心词条',
            'Traceback ...\nAssertionError: 4 != 0 : 语言包 [en] 缺失核心词条\n'))

    def test_mismatched_reason_is_stale(self):
        """记录的是 NameError，实际却挂在 FileNotFoundError → 原因过期。"""
        self.assertTrue(gate.stale_reason(
            "NameError: name 'PROJECT_ROOT' is not defined",
            "FileNotFoundError: [Errno 2] No such file or directory: 'caddy.js'"))

    def test_reason_without_exception_type_is_never_stale(self):
        """纯中文描述无法校验 → 一律不判过期（宁可漏报）。"""
        self.assertFalse(gate.stale_reason('未收集到用例（导入失败）', '随便什么输出'))

    def test_empty_reason_is_not_stale(self):
        self.assertFalse(gate.stale_reason('', 'AssertionError: boom'))

    def test_first_exception_type_wins(self):
        """原因里写了多个异常类型时，取第一个；第一个找不到就算过期。"""
        reason = "ModuleNotFoundError: No module named 'x'；AssertionError: y"
        self.assertTrue(gate.stale_reason(reason, 'AssertionError: y'))
        self.assertFalse(gate.stale_reason(reason, 'ModuleNotFoundError: No module named x'))

    def test_empty_output_is_stale_when_reason_names_type(self):
        """输出为空（例如超时）但原因写了异常类型 → 说明原因已不适用。"""
        self.assertTrue(gate.stale_reason('AssertionError: boom', ''))

    def test_real_quarantine_reasons_are_checkable(self):
        """真实名单里的原因至少得能解析出「结论」，不能全是无法校验的模糊话术。

        允许纯中文原因（如「脚本式用例；引用已移除的 caddy」），但要求
        带异常类型的原因占多数 —— 否则 `stale_reason()` 等于形同虚设。
        """
        q = gate.load_quarantine()
        typed = [m for m, r in q.items() if gate.EXC_IN_REASON_RE.search(r)]
        self.assertGreater(len(typed), len(q) // 2,
                           '超过一半的隔离原因没有写异常类型，名单太模糊，无法校验')


class TestModuleWithoutTestsIsRejected(unittest.TestCase):
    """端到端：一个「收集不到用例」的模块，`run_module()` 必须判红。

    这是门禁**最重要**的一条护栏 —— 它要是坏了，整套门禁退化成「永远全绿」。
    探针模块写进 `testsuite/`（`test_*.py` 被契约用例放行），跑完立即删除；
    万一残留，门禁也会因为它「收集不到用例」而变红 —— 是「响」而不是「静默」。
    """

    PROBE = 'test_zz_gate_selftest_probe.py'

    def test_empty_module_is_red(self):
        path = os.path.join(HERE, self.PROBE)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('# coding:utf-8\n'
                    '# 本文件由 test_gate_selftest.py 临时生成，用于验证门禁护栏；'
                    '正常情况下不该出现在仓库里。\n\n\n'
                    'def helper():\n    return 1\n')
        try:
            r = gate.run_module(self.PROBE)
        finally:
            if os.path.exists(path):
                os.remove(path)

        self.assertFalse(r['ok'], '收集不到用例的模块必须判红，否则门禁是假绿')
        self.assertEqual(r['ran'], 0)
        self.assertIn('未收集到任何用例', r['reason'])


if __name__ == '__main__':
    unittest.main()
