# coding: utf-8
"""P2-12：shell 拼接技术债的「年度下降目标 + 判定口径」与「新代码 argv 检查点」。

为什么要这个文件（补的是哪块洞）
------------------------------
`web/core/yf/__init__.py` 的 `execShell` / `execShellRc` 默认 `shell=True`，历史裸拼
形成了技术债基线（`scripts/shell_concat_baseline.txt` 81 条 +
`scripts/shell_concat_baseline_plugins.txt` 316 条）。既有棘轮
（`testsuite/test_shell_concat_ratchet.py` 的 `test_10_no_new_violations`）只是
**只减不增**：它证明「没有变坏」，但证明不了「会变好」—— 基线一旦不再缩小，
存量裸拼就变成了永久豁免。所以补两件事：

1. **年度下降目标（带日期、带上限数字）**：`REDUCTION_PLAN` 四档 ——
   快照档（2026-10-22）→ ≈70%（2027-06-30）→ ≈40%（2027-12-31）→ 0（2028-06-30）。
   上限是**写死的整数**，断言里不许现算（现算会永远跟着基线走，等于没约束）。
2. **新代码检查点**：`git ls-files --others --exclude-standard`（未跟踪新文件）+
   `git diff --name-only HEAD`（本次改动文件）里落在棘轮扫描范围内的 `.py`，
   不得出现**基线之外**的 shell 裸拼（对全新文件等价于 `analysis == {}`）。
   这样「约定」不只是 docstring 里的一句话，而有可执行判据。

判定口径（当前档怎么选）
-----------------------
`plan_tier_for(today)` 取**最后一个「截止日期 <= 今天」的档**：到期日当天起必须
≤ 该档上限，并一直按该档约束到下一个到期日；今天早于第一档时取第一档。
「截止日期」保持字面含义（到此日必须达标），因此不会出现「计划生效第二天就要求
跳到 70% 档」的时间炸弹；而到了 2028-06-30 那一天，上限就是 0，闸门必然收紧。

零外部依赖：只用标准库 + 复用棘轮模块的 `analyze_source()` / `_scope_violations()`。
"""
import ast
import datetime
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (HERE, os.path.join(ROOT, 'web'), ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import test_shell_concat_ratchet as ratchet  # noqa: E402

YF_PY = os.path.join(ROOT, 'web', 'core', 'yf', '__init__.py')
LIFECYCLE_DOC = os.path.join(ROOT, '文档', '组件生命周期与安全响应政策.md')

#: 「新代码」的两路来源：未跟踪的新文件 + 相对 HEAD 的改动文件。
#: 拆成两路而不是只取其一：新文件常是 `git add` 前就进 CI 的，改动文件则已入库。
GIT_NEW_CODE_CMDS = (
    ('未跟踪的新文件', ['ls-files', '--others', '--exclude-standard']),
    ('相对 HEAD 的改动文件', ['diff', '--name-only', 'HEAD']),
)


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


# 扫描代价不低（两侧合计 ~40s），同一进程里只扫一次。
_VIOLATION_CACHE = {}


def _violations(scope):
    if scope['name'] not in _VIOLATION_CACHE:
        _VIOLATION_CACHE[scope['name']] = ratchet._scope_violations(scope)
    return _VIOLATION_CACHE[scope['name']]


def _scanned_rel_files():
    """棘轮真正会扫的相对路径集合（直接复用它的迭代器，避免两边口径打架）。"""
    out = set()
    for scope in ratchet.SCAN_SCOPES:
        for path in ratchet._iter_py_files(scope['dirs'], scope['root_files'], scope['exclude']):
            out.add(os.path.relpath(path, ROOT).replace(os.sep, '/'))
    return out


def _git_lines(args):
    """跑一次 git，返回 `(行列表, 不可用原因)`；git 不可用 / 非仓库 / 无 HEAD 时给原因。"""
    try:
        proc = subprocess.run(['git'] + args, cwd=ROOT, capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, 'git 不可用：%s' % exc
    if proc.returncode != 0:
        detail = (proc.stderr or b'').decode('utf-8', 'replace').strip().replace('\n', ' ')[:200]
        return None, 'git %s 返回 %d：%s' % (' '.join(args), proc.returncode, detail)
    return [line.strip() for line in (proc.stdout or b'').decode('utf-8', 'replace').splitlines()
            if line.strip()], ''


def new_code_files():
    """返回 `(相对路径列表, 跳过原因)`。

    跳过（不算红）的情形：git 不可用 / 不是 git 仓库 / 没有 HEAD / 取不到任何改动。
    这是刻意的 —— 本用例要防的是「新代码又写裸拼」，而不是考勤环境的 git 状态。
    """
    cands, reasons = [], []
    for _label, args in GIT_NEW_CODE_CMDS:
        lines, why = _git_lines(args)
        if lines is None:
            reasons.append(why)
            continue
        cands.extend(lines)
    if not cands and reasons:
        return [], '；'.join(reasons)
    scanned = _scanned_rel_files()
    files = []
    for rel in dict.fromkeys(cands):  # 去重且保序
        rel = rel.replace(os.sep, '/')
        if rel in scanned and rel.endswith('.py'):
            files.append(rel)
    if not files:
        return [], ('git 可用但「新代码」集合里没有任何落在扫描范围内的 .py'
                    '（未跟踪 %d 个候选、跳过原因：%s）' % (len(cands), '；'.join(reasons) or '无'))
    return files, ''


class TestReductionPlanShape(unittest.TestCase):
    """用例 1：计划表本身必须是一张「有终点、不反弹」的表。"""

    def test_01_plan_defined_sorted_monotonic_and_ends_at_zero(self):
        plan = ratchet.REDUCTION_PLAN
        self.assertIsInstance(plan, tuple, 'REDUCTION_PLAN 必须是不可变元组（防运行期被改）')
        self.assertGreaterEqual(len(plan), 2, '至少要有一档目标 + 一档终点：%r' % (plan,))

        # 结构：每档 = (日期字符串, web 上限, 插件上限)，上限是非负整数（不许写算式/浮点）
        for tier in plan:
            self.assertEqual(3, len(tier), '每档必须是 (截止日期, web 上限, 插件上限)：%r' % (tier,))
            date_text, web_limit, plugins_limit = tier
            self.assertRegex(str(date_text), r'^\d{4}-\d{2}-\d{2}$',
                             '截止日期必须是 YYYY-MM-DD：%r' % (date_text,))
            for name, limit in (('web', web_limit), ('plugins', plugins_limit)):
                self.assertIsInstance(limit, int,
                                      '[%s] 上限必须是写死的整数（不许现算/浮点）：%r' % (name, limit))
                self.assertGreaterEqual(limit, 0, '[%s] 上限不得为负：%r' % (name, limit))

        # 日期升序（同时证明日期可解析 —— 解析不了在这里就红，而不是在判定口径里静默取错）
        dates = [ratchet._parse_plan_date(t[0]) for t in plan]
        self.assertEqual(sorted(dates), dates, 'REDUCTION_PLAN 的截止日期必须升序：%r' % (dates,))
        self.assertEqual(len(set(dates)), len(dates), '截止日期不得重复：%r' % (dates,))

        # 单调不增：后一档的上限必须 <= 前一档（否则「下降目标」会反弹）
        for idx in range(1, len(plan)):
            prev, cur = plan[idx - 1], plan[idx]
            for name, col in ratchet.PLAN_LIMIT_INDEX.items():
                self.assertLessEqual(
                    cur[col], prev[col],
                    '[%s] 第 %d 档上限 %d 大于第 %d 档 %d（%s → %s）：下降目标不许反弹'
                    % (name, idx + 1, cur[col], idx, prev[col], prev[0], cur[0]))

        # 终点：最后一档必须全 0，否则「什么时候必须还清」就没有答案
        last = plan[-1]
        self.assertEqual((0, 0), (last[1], last[2]),
                         '最后一档（%s）必须全 0（存量清零），实际 %r' % (last[0], last))


class TestCurrentTierEnforced(unittest.TestCase):
    """用例 2：今天落在哪一档，实际违规数就必须 <= 那一档的上限。"""

    def test_02_actual_violations_within_current_tier(self):
        today = datetime.date.today()
        tier = ratchet.plan_tier_for(today)
        for scope in ratchet.SCAN_SCOPES:
            name = scope['name']
            actual = len(_violations(scope))
            limit = tier[ratchet.PLAN_LIMIT_INDEX[name]]
            self.assertLessEqual(
                actual, limit,
                '[%s] 今天（%s）适用的档位是 %s（上限 %d），实测 %d 处 shell 裸拼 —— '
                '超 %d 处。要么按计划还债，要么走显式评审下调 REDUCTION_PLAN 的数值'
                '（只允许往下调）。' % (name, today, tier[0], limit, actual, actual - limit))

    def test_04_plan_rule_is_deadline_based(self):
        """口径自证：档位是「最后一个已到期的档」，早于第一档取第一档，晚于最后一档取 0 档。"""
        plan = ratchet.REDUCTION_PLAN
        first_date = plan[0][0]
        last_date = plan[-1][0]
        self.assertEqual(plan[0], ratchet.plan_tier_for('2000-01-01'),
                         '早于第一档时应取第一档（快照档）')
        self.assertEqual(plan[0], ratchet.plan_tier_for(first_date),
                         '到期日当天必须按该档约束')
        # 第一档到第二档之间：仍按第一档（截止日期 = 到此日必须达标）
        between = ratchet._parse_plan_date(plan[1][0]) - datetime.timedelta(days=1)
        self.assertEqual(plan[0], ratchet.plan_tier_for(between),
                         '第二档到期之前仍适用第一档（不是时间炸弹）')
        self.assertEqual(plan[1], ratchet.plan_tier_for(plan[1][0]),
                         '第二档到期当天必须切到第二档')
        after_last = ratchet._parse_plan_date(last_date) + datetime.timedelta(days=1)
        self.assertEqual(plan[-1], ratchet.plan_tier_for(after_last),
                         '最后一档到期之后仍按最后一档（上限 0）约束')
        self.assertEqual(0, ratchet.plan_limit_for('web', after_last))
        self.assertEqual(0, ratchet.plan_limit_for('plugins', after_last))

    def test_03_baseline_entries_match_first_tier(self):
        """防两套数打架：基线文件的条目数必须等于计划表第一档（快照档）的上限。"""
        snapshot = ratchet.REDUCTION_PLAN[0]
        for scope in ratchet.SCAN_SCOPES:
            name = scope['name']
            entries = ratchet.load_baseline(scope['baseline'])
            expected = snapshot[ratchet.PLAN_LIMIT_INDEX[name]]
            self.assertEqual(
                expected, len(entries),
                '[%s] 基线文件 %s 有 %d 条，REDUCTION_PLAN 第一档（%s）写的是 %d —— '
                '两套数打架：还债时请**同时**把基线剪小并把计划表往下调。'
                % (name, os.path.relpath(scope['baseline'], ROOT), len(entries),
                   snapshot[0], expected))


class TestNewCodeCheckpoint(unittest.TestCase):
    """用例 5：新增/改动代码默认 argv —— 可执行的检查点（git 不可用则 skip）。"""

    def test_10_new_code_has_no_bare_shell_concat(self):
        files, why = new_code_files()
        if not files:
            self.skipTest(why or '没有可检查的新代码（git 不可用或无改动）')

        known = set()
        for scope in ratchet.SCAN_SCOPES:
            known |= ratchet.load_baseline(scope['baseline'])

        leaked = {}
        for rel in files:
            path = os.path.join(ROOT, rel.replace('/', os.sep))
            if not os.path.isfile(path):
                continue  # 改动集合里的已删除文件
            analysis = ratchet.analyze_source(rel, _read(path))
            fresh = {fp: info for fp, info in analysis.items() if fp not in known}
            if fresh:
                leaked[rel] = fresh

        self.assertEqual(
            {}, leaked,
            '新代码里出现了 %d 处**基线之外**的 shell 裸拼（新代码默认必须 argv 列表 + '
            'shell=False；确需 shell=True 的，参数不得含外部输入且必须就地注释理由）：%s'
            % (len(leaked), sorted(leaked)))

    def test_11_checkpoint_detector_is_alive(self):
        """防「检查点永远绿」：同一套分析函数必须能把坏夹具抓出来。"""
        analysis = ratchet.analyze_source('web/core/yf/new_module_tmp.py', ratchet._BAD_FIXTURE)
        self.assertNotEqual({}, analysis, '分析方法对坏写法零命中，检查点形同虚设')
        good = ratchet.analyze_source('web/core/yf/new_module_tmp.py', ratchet._GOOD_FIXTURE)
        self.assertEqual({}, good, '正确写法被误判，检查点会误伤新代码：%s' % good)


class TestConventionDocumented(unittest.TestCase):
    """用例 5（文档面）：约定与计划必须真的落在文档/docstring 里，而不是只活在口头。"""

    def test_20_lifecycle_doc_has_debt_plan_section(self):
        self.assertTrue(os.path.isfile(LIFECYCLE_DOC), '缺少《组件生命周期与安全响应政策》')
        text = _read(LIFECYCLE_DOC)
        self.assertIn('## 9. 技术债偿还计划', text,
                      '生命周期政策缺「## 9. 技术债偿还计划（shell 拼接）」小节')
        self.assertIn('shell', text.split('## 9. 技术债偿还计划', 1)[1][:2000].lower(),
                      '第 9 节必须写明 shell 拼接技术债')
        self.assertRegex(text, r'2027-\d{2}-\d{2}',
                         '第 9 节必须写明带具体日期的下降档位（至少一个 2027 日期）')
        # 计划表里的四个到期日都要留档，避免文档与代码漂移
        for tier in ratchet.REDUCTION_PLAN:
            self.assertIn(tier[0], text, '文档缺档位日期 %s（REDUCTION_PLAN 与文档漂移）' % tier[0])

    def test_21_execshell_docstring_states_argv_contract(self):
        tree = ast.parse(_read(YF_PY))
        found = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name in ('execShell', 'execShellRc'):
                found[node.name] = ast.get_docstring(node) or ''
        for name in ('execShell', 'execShellRc'):
            self.assertIn(name, found, 'web/core/yf/__init__.py 结构变了：缺 %s' % name)
            doc = found[name]
            self.assertIn('argv', doc, '[%s] docstring 必须写明「新代码默认用 argv 列表」' % name)
            self.assertIn('shell=False', doc, '[%s] docstring 必须写明 shell=False 默认口径' % name)
            self.assertIn('外部输入', doc, '[%s] docstring 必须写明 shell=True 的例外条件' % name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
