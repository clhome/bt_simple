# coding: utf-8
"""CI 触发自动化守卫（测评报告 P1 第 9 条）。

## 为什么要有这个文件

测评报告 P1 第 9 条的结论是「CI 自动化程度低」：`.github/workflows/` 里 9 个
workflow，push 时自动跑的只有 `i18n-check.yml` 与 `security-scan.yml`，而
`python-app-mysql{55,56,57,80}.yml` / `python-app-op.yml` / `python-app-php.yml`
全是 `workflow_dispatch`（手动），即 240+ 测试文件与集成测试**不在每次提交时
自动运行**，门禁实际靠本地自觉执行 `run_all.py`。

修法有两半，本文件把两半都钉死：

1. 新增 `core-regression.yml`：push / PR 自动跑**仓库唯一门禁**
   `python testsuite/run_all.py`（含 4 项静态门禁）；
2. 6 个重型 workflow 由「只能手动」改成「手动 + push/PR，但用 `paths` 收窄到
   **本插件目录 + 本 workflow 文件**」—— 它们要 `sudo bash scripts/install_dev.sh`
   装整套面板再真装 MySQL / PHP / OpenResty，每次提交都跑既慢又没必要。

护栏（每条都能真失败，见 `test/p1_ci_mutation_probe.py` 的 7 处回退自证）：

* `core-regression.yml` 必须存在，且**同时**含 `push` 与 `pull_request`，
  并真的执行 `testsuite/run_all.py`；
* 6 个重型 workflow 必须含 `push`（带 `paths`）与 `pull_request`（带 `paths`），
  且**仍保留** `workflow_dispatch`（手动跑重型集成冒烟的能力不能被改掉）；
* `paths` 必须**逐字**等于「本插件目录 + 本 workflow 文件」—— 放宽（如加上
  `web/**`）会让「避免每次提交都跑重装」的意图失效，必须报红；
* `release.yml` / `i18n-check.yml` / `security-scan.yml` 的**触发键与范围**
  与基线逐字一致（基线写在本文件里，改动必须显式改基线并说明理由）；
* 不许用 `|| true` / `continue-on-error` 掩盖门禁失败。

## 解析方式

优先 PyYAML（`requirements.txt` 已含 pyyaml，CI 必有）；本机没有 PyYAML 时退化为
`parse_trigger_regex()` 的受控行解析。两条路径都产出**同一种归一化结构**
`{事件: {子键: [值...]}}`，并由 `test_02` 在 PyYAML 可用时逐文件比对两者结果
—— 回退解析器本身也被证明过，不会因为「本机碰巧有 PyYAML」而悄悄腐烂。

（注意 YAML 1.1 把裸 `on` 解析成布尔 `True`：PyYAML 里顶层键是 `True` 而不是
`'on'`，取值时必须两个都试，否则所有触发断言都会在「找不到 on」上假红。）
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORKFLOW_DIR = os.path.join(ROOT, '.github', 'workflows')

CORE_WORKFLOW = 'core-regression.yml'

# 重型集成冒烟 workflow → 它实际安装的插件目录。
# 这层映射不是装饰：test_24 会交叉核对文件里确实调用 `<插件目录>/install.sh`，
# 防止「paths 写了一个和 workflow 无关的目录」这种假收窄。
HEAVY_WORKFLOWS = {
    'python-app-mysql55.yml': 'plugins/mysql/',
    'python-app-mysql56.yml': 'plugins/mysql/',
    'python-app-mysql57.yml': 'plugins/mysql/',
    'python-app-mysql80.yml': 'plugins/mysql/',
    'python-app-op.yml': 'plugins/openresty/',
    'python-app-php.yml': 'plugins/php/',
}

# i18n-check.yml 的 paths（基线，逐字抄写；顺序为归一化后的排序结果）
# `web/**/*.py`：P2-14 —— web 后端（returnData/returnJson/returnMsg）的中文消息
# 已进入 `verify_i18n.py` 的 backend-msg-key 检查（web 段走棘轮基线），触发范围
# 必须跟上。这是**收紧**（多一条触发路径 = 更多提交会跑这个门禁），不是放宽。
_I18N_PATHS = [
    '.github/workflows/i18n-check.yml',
    'plugins/**/*.js',
    'plugins/**/index.html',
    'plugins/**/index.py',
    'plugins/**/lang/**',
    'scripts/verify_i18n.py',
    'web/**/*.py',
    'web/static/app/i18n.js',
    'web/static/app/public.js',
    'web/static/language/**',
]

# security-scan.yml 的 paths（基线，逐字抄写；顺序为归一化后的排序结果）
# `scripts/**.py`：bandit 本来就扫 scripts，触发范围必须跟上，否则漏扫
# （2026-10-13：`scripts/tools/build_edition.py` 的 B202 HIGH 就是这么躲过好几次提交的）。
# `文档/待审核插件/**`：P2-11 新增 —— 待审核插件转正就是搬进 `plugins/` 直接进生产，
# 所以它的改动也必须触发扫描（bandit 的 `-r` 目录也同步加了这个目录）；
# 代码质量棘轮那侧的对应基线是 `scripts/code_quality_baseline.json` 的 `pending_*` 键。
_SCAN_PATHS = [
    '.github/workflows/security-scan.yml',
    'panel_task.py',
    'panel_tools.py',
    'plugins/**/*.py',
    'requirements*.txt',
    'scripts/**.py',
    'web/**.py',
    '文档/待审核插件/**',
]

# 不许动触发条件的三个 workflow（基线 = 2026-10-12 改动前的实际触发，逐字抄写）。
FROZEN_BASELINE = {
    'release.yml': {
        'push': {'tags': ['v*']},
        'workflow_dispatch': {'inputs': ['tag']},
    },
    'i18n-check.yml': {
        'workflow_dispatch': {},
        'push': {'paths': _I18N_PATHS},
        'pull_request': {'paths': _I18N_PATHS},
    },
    'security-scan.yml': {
        'push': {
            'branches': ['i18n', 'main', 'master'],
            'paths': _SCAN_PATHS,
        },
        'pull_request': {'paths': _SCAN_PATHS},
        'schedule': {'cron': ['0 3 * * 1']},
        'workflow_dispatch': {},
    },
}

# `core-regression.yml` 的 paths-ignore 只允许排除这些「与门禁无关」的纯文档/笔记。
# 下面 `CODE_SAMPLES` 里的路径**一个都不许**被它们匹配到。
DOC_IGNORE_BASELINE = [
    'README.md',
    'RELEASE_TEMPLATE.md',
    'cl_tasks/**',
    'cmd.md',
    'compatibility.md',
    'task.md',
    '文档/**',
]
CODE_SAMPLES = [
    'testsuite/run_all.py',
    'testsuite/test_ci_workflows_hardening.py',
    'web/admin/setting/__init__.py',
    'plugins/mysql/index.py',
    'scripts/verify_i18n.py',
    'requirements.txt',
    '.github/workflows/core-regression.yml',
]
DOC_SAMPLES = ['README.md', '文档/插件统一开发规范.md', 'cl_tasks/20261012_1000task.md']


def _read(rel):
    with open(os.path.join(ROOT, rel), 'r', encoding='utf-8') as fp:
        return fp.read()


def _workflow_files():
    """`.github/workflows/` 下所有 workflow 文件名（`.yml` 与 `.yaml` 都要发现）。"""
    return sorted(n for n in os.listdir(WORKFLOW_DIR)
                  if n.endswith(('.yml', '.yaml')))


# --------------------------------------------------------------------------
# 触发解析：PyYAML 优先，正则回退（两者产出同一结构）
# --------------------------------------------------------------------------
def _norm_cfg(cfg):
    """把某个事件的配置归一化成 `{子键: [值...]}`（列表排序，便于逐字比对）。"""
    if isinstance(cfg, list):
        # 事件的值直接是列表（`schedule: - cron: '...'`），没有外层子键
        out = {}
        for item in cfg:
            if isinstance(item, dict):
                for k, v in item.items():
                    out.setdefault(str(k), []).append(str(v))
        return {k: sorted(v) for k, v in out.items()}
    if not isinstance(cfg, dict):
        return {}
    out = {}
    for key, val in cfg.items():
        key = str(key)
        if isinstance(val, list):
            vals = []
            for item in val:
                if isinstance(item, dict):
                    vals.extend(str(v) for v in item.values())
                else:
                    vals.append(str(item))
            out[key] = sorted(vals)
        elif isinstance(val, dict):
            # 如 `workflow_dispatch.inputs.tag`：记下输入名（tag 被删掉要报红）
            out[key] = sorted(str(k) for k in val)
        else:
            out[key] = [] if val is None else [str(val)]
    return out


def parse_trigger(text):
    """解析 workflow 的触发块 → `{事件: {子键: [值...]}}`。

    PyYAML 可用时用它；否则走 `parse_trigger_regex()`。两者结构一致。
    """
    try:
        import yaml
    except ImportError:
        return parse_trigger_regex(text)
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return {}
    # YAML 1.1：裸 `on` 会被解析成布尔 True
    if 'on' in data:
        trig = data['on']
    elif True in data:
        trig = data[True]
    else:
        trig = {}
    if not isinstance(trig, dict):
        return {}
    return {str(ev): _norm_cfg(cfg) for ev, cfg in trig.items()}


_ON_LINE_RE = re.compile(r'^on:\s*$')
_EVENT_RE = re.compile(r'^([\w\-]+):\s*(.*)$')


def parse_trigger_regex(text):
    """无 PyYAML 时的受控行解析（只认缩进，不认完整 YAML 语义）。

    覆盖本仓库 workflow 用到的全部形态：
      * 事件键在缩进 2（`  push:`）；
      * 事件的子键在缩进 4（`    paths:`），值可为流式列表
        （`    branches: [master, main, i18n]`）；
      * 块式列表项在缩进 6（`      - 'plugins/mysql/**'`）**或缩进 4**
        （`schedule:` 的 `    - cron: '0 3 * * 1'`，YAML 允许序列与键同缩进）；
      * 缩进 6 的映射键（`      tag:`，即 workflow_dispatch 的输入名）记成值；
      * 更深的行（缩进 ≥ 8，如 `required: true`）不属于触发范围，忽略；
      * 缩进 0 表示离开 `on:` 块，停止。
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if _ON_LINE_RE.match(line):
            start = i
            break
    if start is None:
        return {}

    def append_item(cfg, key, item):
        """把一个列表项（`- x` / `- cron: x` / `tag:`）归入 cfg[key]。

        `key=None` 表示「事件的值直接是列表」（如 `schedule:`），此时从
        `- cron: '...'` 里取键名；`val` 为空且 key 已知时，把键名本身当值
        （workflow_dispatch 的输入名 `tag:`，其值在更深的缩进里）。
        """
        item = item[2:].strip() if item.startswith('- ') else item
        m = _EVENT_RE.match(item)
        if m:
            name, val = m.group(1), m.group(2).strip().strip('\'"')
            if key is None:
                key = name
            elif not val:
                val = name
        else:
            val = item.strip('\'"')
            if key is None:
                return
        if val:
            cfg.setdefault(key, []).append(val)

    events = {}
    cur_event = None
    cur_key = None
    for line in lines[start + 1:]:
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        indent = len(line) - len(line.lstrip(' '))
        if indent == 0:
            break
        stripped = line.strip()
        if indent == 2:
            m = _EVENT_RE.match(stripped)
            if m:
                cur_event, cur_key = m.group(1), None
                events[cur_event] = {}
            continue
        if cur_event is None:
            continue
        cfg = events[cur_event]
        if indent == 4:
            if stripped.startswith('- ') and (cur_key is not None or not cfg):
                append_item(cfg, cur_key, stripped)
                continue
            m = _EVENT_RE.match(stripped)
            if m:
                cur_key = m.group(1)
                vals = cfg.setdefault(cur_key, [])
                inline = m.group(2).strip()
                # 流式列表：`branches: [master, main, i18n]`（security-scan.yml 用）
                if inline.startswith('[') and inline.endswith(']'):
                    for part in inline[1:-1].split(','):
                        part = part.strip().strip('\'"')
                        if part:
                            vals.append(part)
            continue
        if indent == 6 and cur_key is not None:
            append_item(cfg, cur_key, stripped)

    return {ev: {k: sorted(v) for k, v in cfg.items()}
            for ev, cfg in events.items()}


# --------------------------------------------------------------------------
# GitHub paths 过滤的近似匹配（`*` 不跨 `/`，`**` 跨层级）
# --------------------------------------------------------------------------
def github_match(pattern, path):
    rx, i = '', 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern[i:i + 2] == '**':
            rx += '.*'
            i += 2
        elif ch == '*':
            rx += '[^/]*'
            i += 1
        elif ch == '?':
            rx += '[^/]'
            i += 1
        else:
            rx += re.escape(ch)
            i += 1
    return re.match('^' + rx + '$', path) is not None


def is_ignored(patterns, path):
    return any(github_match(p, path) for p in patterns)


def _paths_of(trigger, event):
    return (trigger.get(event) or {}).get('paths', [])


def _effective_lines(text):
    """去掉整行注释与空行后的「会真正执行/生效」的行。

    注释里出现 `|| true` / `continue-on-error` 是在**解释为什么不能用它**，
    不是掩盖失败 —— 一律按注释剔除，只查会进 YAML 结构的行。
    """
    return [line for line in text.split('\n')
            if line.strip() and not line.lstrip().startswith('#')]


def _masking_offenders(text):
    return [line.strip() for line in _effective_lines(text)
            if '|| true' in line or '|| :' in line or 'continue-on-error' in line]


def _assert_no_masking(test, name, text):
    """门禁类 workflow 不得用 `|| true` / `continue-on-error` 掩盖失败。"""
    test.assertEqual(_masking_offenders(text), [],
                     '%s 用 `|| true` / `continue-on-error` 掩盖失败；'
                     'CI 缺依赖就在 workflow 里补装依赖' % name)


class TestWorkflowsParsable(unittest.TestCase):
    """所有 workflow 必须可解析、无 Tab 缩进、至少有一个触发事件。"""

    def test_01_all_workflows_parse(self):
        files = _workflow_files()
        self.assertTrue(files, '一个 workflow 都没发现，路径写错了？')
        for name in files:
            text = _read(os.path.join('.github', 'workflows', name))
            for i, line in enumerate(text.split('\n'), 1):
                self.assertNotRegex(line, r'^\t', '%s 第 %d 行用了 Tab 缩进' % (name, i))
            self.assertTrue(parse_trigger(text),
                            '%s 解析不出任何触发事件（YAML 结构被改坏了？）' % name)

    def test_02_regex_fallback_agrees_with_pyyaml(self):
        """回退解析器必须与 PyYAML 结论一致 —— 否则「本机有 PyYAML」会掩盖它的腐烂。"""
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest('本机无 PyYAML，无法交叉比对（CI 有 requirements.txt 提供）')
        for name in _workflow_files():
            text = _read(os.path.join('.github', 'workflows', name))
            self.assertEqual(parse_trigger_regex(text), parse_trigger(text),
                             '%s：正则回退解析与 PyYAML 结论不一致' % name)


class TestCoreRegressionWorkflow(unittest.TestCase):
    """`core-regression.yml`：每次 push / PR 跑仓库唯一门禁。"""

    def setUp(self):
        self.path = os.path.join('.github', 'workflows', CORE_WORKFLOW)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, self.path)),
                        '缺少 %s —— 报告 P1 第 9 条要求 push/PR 自动跑核心回归' % CORE_WORKFLOW)
        self.text = _read(self.path)
        self.trigger = parse_trigger(self.text)

    def test_10_triggers_on_push_and_pull_request(self):
        self.assertIn('push', self.trigger,
                      'core-regression.yml 没有 push 触发 = 每次提交不会自动跑')
        self.assertIn('pull_request', self.trigger,
                      'core-regression.yml 没有 pull_request 触发')

    def test_11_runs_repo_gate(self):
        """必须走唯一门禁入口 `testsuite/run_all.py`（自己 discover 会绕过防假绿护栏）。"""
        self.assertIn('testsuite/run_all.py', self.text,
                      '未执行仓库门禁 testsuite/run_all.py')
        self.assertRegex(self.text, r'run:\s*python\s+testsuite/run_all\.py',
                         'run 步骤不是 `python testsuite/run_all.py`')

    def test_12_installs_dependencies_and_python(self):
        self.assertIn('actions/checkout@', self.text, '缺少检出步骤')
        self.assertRegex(self.text, r"python-version:\s*['\"]?3\.1[12]",
                         '未设置 Python 3.11 / 3.12')
        self.assertRegex(self.text, r'pip install[^\n]*-r requirements\.txt',
                         '未按 requirements.txt 安装依赖')

    def test_13_paths_ignore_does_not_exclude_code(self):
        """paths-ignore 只许排除纯文档 —— testsuite/、web/、plugins/ 必须在触发范围内。"""
        for event in ('push', 'pull_request'):
            ignored = (self.trigger.get(event) or {}).get('paths-ignore', [])
            self.assertEqual(sorted(ignored), sorted(DOC_IGNORE_BASELINE),
                             '%s 的 paths-ignore 与基线不一致（放宽会把代码改动也排除）' % event)
            for sample in CODE_SAMPLES:
                self.assertFalse(is_ignored(ignored, sample),
                                 '%s 的 paths-ignore 把代码路径 %s 也排除了' % (event, sample))

    def test_14_paths_ignore_still_covers_pure_docs(self):
        """反向：paths-ignore 不能是空摆设 —— 纯文档改动确实被排除。"""
        ignored = (self.trigger.get('push') or {}).get('paths-ignore', [])
        self.assertTrue(ignored, 'paths-ignore 为空，纯文档改动也会跑全量门禁')
        for sample in DOC_SAMPLES:
            self.assertTrue(is_ignored(ignored, sample),
                            '纯文档路径 %s 未被排除，paths-ignore 形同虚设' % sample)

    def test_15_glob_matcher_selftest(self):
        """`github_match()` 的语义自证（`*` 不跨 `/`，`**` 跨层级）。"""
        self.assertTrue(github_match('plugins/**', 'plugins/a/b.py'))
        self.assertTrue(github_match('plugins/**/lang/**', 'plugins/x/lang/en.json'))
        self.assertTrue(github_match('requirements*.txt', 'requirements.txt'))
        self.assertFalse(github_match('*.md', 'testsuite/testsuite.md'),
                         '`*` 不应跨 `/`，否则 `*.md` 会误伤子目录')
        self.assertTrue(github_match('*.md', 'README.md'))
        self.assertFalse(github_match('文档/**', 'testsuite/run_all.py'))

    def test_16_no_masking(self):
        _assert_no_masking(self, CORE_WORKFLOW, self.text)

    def test_17_runner_os_is_pinned_to_a_verified_version(self):
        """门禁自己也不许跑在 `ubuntu-latest` 上。

        2026-10-23 的核心回归红（#10~#12）到现在都无法从仓库状态复现：本地 Windows、
        干净 venv（只装 requirements.txt）、以及 Linux/Python 3.11 全量复跑都是全绿。
        唯一剩下的变量就是 runner 平台 —— `ubuntu-latest` 已迁到 README 列为
        「待适配 / 未验证」的 26.04。平台一漂移，红就不再等于「代码回归」，
        告警信号直接失效。所以把它钉到 compatibility.md 已验证的两个 LTS。
        """
        _assert_runner_pinned(self, CORE_WORKFLOW, self.text)


class TestHeavyWorkflowTriggers(unittest.TestCase):
    """6 个重型集成冒烟：手动 + push/PR，但 paths 收窄到本插件目录 + 本文件。"""

    def test_20_each_heavy_triggers_on_push_with_paths(self):
        for name, plugin in sorted(HEAVY_WORKFLOWS.items()):
            trig = parse_trigger(_read(os.path.join('.github', 'workflows', name)))
            self.assertIn('push', trig, '%s 没有 push 触发' % name)
            paths = _paths_of(trig, 'push')
            self.assertTrue(paths, '%s 的 push 没有 paths 过滤 = 每次提交都跑重装' % name)
            self.assertEqual(sorted(paths), sorted([plugin + '**', '.github/workflows/' + name]),
                             '%s 的 push paths 必须逐字等于「本插件目录 + 本 workflow 文件」' % name)

    def test_21_each_heavy_triggers_on_pull_request_with_paths(self):
        for name, plugin in sorted(HEAVY_WORKFLOWS.items()):
            trig = parse_trigger(_read(os.path.join('.github', 'workflows', name)))
            self.assertIn('pull_request', trig, '%s 没有 pull_request 触发' % name)
            paths = _paths_of(trig, 'pull_request')
            self.assertTrue(paths, '%s 的 pull_request 没有 paths 过滤' % name)
            self.assertEqual(sorted(paths), sorted([plugin + '**', '.github/workflows/' + name]),
                             '%s 的 pull_request paths 必须逐字等于「本插件目录 + 本 workflow 文件」' % name)

    def test_22_each_heavy_keeps_workflow_dispatch(self):
        """手动触发必须保留：重型冒烟要能在需要时随时手动跑一遍。"""
        for name in sorted(HEAVY_WORKFLOWS):
            trig = parse_trigger(_read(os.path.join('.github', 'workflows', name)))
            self.assertIn('workflow_dispatch', trig, '%s 丢了 workflow_dispatch' % name)

    def test_23_heavy_paths_do_not_leak_other_dirs(self):
        """收窄要真收窄：不许出现 `web/**`、`**`、`*` 这类「等于没过滤」的模式。"""
        for name in sorted(HEAVY_WORKFLOWS):
            trig = parse_trigger(_read(os.path.join('.github', 'workflows', name)))
            for event in ('push', 'pull_request'):
                for pattern in _paths_of(trig, event):
                    self.assertNotIn(pattern, ('*', '**', '*/**', 'web/**', 'plugins/**'),
                                     '%s 的 %s paths 含过宽模式 %s' % (name, event, pattern))

    def test_24_plugin_dir_matches_the_install_step(self):
        """交叉核对：映射里的插件目录确实是该 workflow 安装的东西（防假收窄）。"""
        for name, plugin in sorted(HEAVY_WORKFLOWS.items()):
            text = _read(os.path.join('.github', 'workflows', name))
            self.assertIn(plugin + 'install.sh', text,
                          '%s 的 paths 指向 %s，但文件里并没有安装它' % (name, plugin))
            self.assertIn('scripts/install_dev.sh', text,
                          '%s 不再安装面板本体？触发策略的前提变了' % name)

    def test_25_no_masking(self):
        for name in sorted(HEAVY_WORKFLOWS):
            _assert_no_masking(self, name, _read(os.path.join('.github', 'workflows', name)))


class TestFrozenWorkflowTriggers(unittest.TestCase):
    """`release.yml` / `i18n-check.yml` / `security-scan.yml` 的触发不许被顺手改掉。"""

    def _check(self, name):
        actual = parse_trigger(_read(os.path.join('.github', 'workflows', name)))
        self.assertEqual(actual, FROZEN_BASELINE[name],
                         '%s 的触发条件与基线不一致（若确需变更，请显式更新基线并说明理由）' % name)

    def test_30_release_trigger_unchanged(self):
        self._check('release.yml')

    def test_31_i18n_check_trigger_unchanged(self):
        self._check('i18n-check.yml')

    def test_32_security_scan_trigger_unchanged(self):
        self._check('security-scan.yml')

    def test_33_no_masking(self):
        for name in ('release.yml', 'i18n-check.yml'):
            _assert_no_masking(self, name, _read(os.path.join('.github', 'workflows', name)))


# 门禁 / 冒烟类 workflow 允许钉的 runner 版本（= `compatibility.md` 已验证矩阵里的
# Ubuntu）。加新版本的前提：先在 compatibility.md 里验证通过，再来这里放行
# —— 顺序不能反。
VERIFIED_RUNNER_OS = ('ubuntu-22.04', 'ubuntu-24.04')


def _assert_runner_pinned(test, name, text):
    """矩阵里的 `os` 必须是**已验证的具体版本**，不许 `ubuntu-latest`。

    2026-10-23 的教训：`ubuntu-latest` 自 2026-10-19 起迁到 Ubuntu 26.04，而
    26.04 在本仓库还是「待适配 / 未验证」。平台一漂移，workflow 变红就分不清
    「平台没适配」还是「代码真回归」（重型冒烟真装 PHP/MySQL 时更致命）。
    """
    m = re.search(r'^\s*os:\s*\[(.*?)\]\s*$', text, re.M)
    test.assertIsNotNone(m, '%s 找不到 `os: [...]` 矩阵' % name)
    values = [v.strip().strip('\'"') for v in m.group(1).split(',') if v.strip()]
    test.assertTrue(values, '%s 的 os 矩阵为空' % name)
    for value in values:
        test.assertNotIn('latest', value,
                         '%s 用了 %s：`ubuntu-latest` 会随平台漂移，'
                         '门禁/冒烟类 workflow 一律钉已验证的具体版本' % (name, value))
        test.assertIn(value, VERIFIED_RUNNER_OS,
                      '%s 钉了未验证的 runner %s（先让它在 compatibility.md '
                      '里验证通过，再加进 VERIFIED_RUNNER_OS）' % (name, value))


class TestHeavyWorkflowRunnability(unittest.TestCase):
    """重型冒烟必须「跑得起来 + 判得出真假」—— 2026-10-23 的两次翻车都栽在这里。

    背景（`bt_simple Actions 报错整理（Commit 1ec4a4c）` 问题二 / 问题三）：

    1. **MySQL55/56/57/80 的 `Start DEBUG` 退出码 127**：那段是从 mdserver 时代
       抄来的

           cd web && gunicorn -c setting.py app:app
           python3 panel_task.py &

       两个点都能独立致命：`cd web` 是相对路径（runner 的 cwd 是 checkout 目录，
       不是面板目录），裸 `gunicorn` 不在 PATH 上（面板的 Python 环境在
       `/www/server/yufeng_panel/bin` 这个 venv 里，setup-python 的解释器没有它）。
    2. **PHP / OpenResty 用 `ubuntu-latest`**：GitHub 已公告该标签自 2026-10-19 起
       迁移到 Ubuntu 26.04，而 README「待适配 / 未验证」写明 26.04 的工具链分支、
       t64 库名、ondrej/sury 源都没验证 —— 源码编译 PHP / OpenResty 在那里必然失败。
       重型 workflow 是「真装一遍」，必须钉已验证的具体版本。

    还有一个更隐蔽的问题：`web/setting.py` 里 `daemon=True`，所以「启动了」这件事
    本身**不可判**（double-fork 后父进程立刻回 0，端口被占之类的失败发生在子进程）。
    因此冒烟步骤必须断言**外部可观测状态**（`/healthz` 回 200），不能只敲启动命令。
    """

    def _text(self, name):
        return _read(os.path.join('.github', 'workflows', name))

    def test_50_runner_os_is_pinned_to_a_verified_version(self):
        """矩阵里不许出现 `ubuntu-latest`：平台漂移会让「真装」类 workflow 无声变红。"""
        for name in sorted(HEAVY_WORKFLOWS):
            _assert_runner_pinned(self, name, self._text(name))

    def test_51_no_bare_gunicorn_or_relative_panel_dir(self):
        """不许出现「裸 gunicorn」与「相对面板目录」—— 这两条各自都能给出退出码 127。"""
        # 注释行里提到旧写法是在解释为什么不能用，不算违规（_effective_lines 已剔除）
        bare_gunicorn = re.compile(r'^\s*(?:sudo\s+)?gunicorn\b')
        bare_task = re.compile(r'^\s*(?:sudo\s+)?python3\s+panel_task\.py')
        rel_web = re.compile(r'^\s*cd\s+web\b')
        for name in sorted(HEAVY_WORKFLOWS):
            for line in _effective_lines(self._text(name)):
                self.assertIsNone(bare_gunicorn.match(line),
                                  '%s：裸 `gunicorn` 不在 PATH 上（面板 venv 在 ' \
                                  '/www/server/yufeng_panel/bin），请用绝对路径：%s'
                                  % (name, line.strip()))
                self.assertIsNone(bare_task.match(line),
                                  '%s：裸 `python3` 不是面板的解释器，请用 ' \
                                  './bin/python3：%s' % (name, line.strip()))
                self.assertIsNone(rel_web.match(line),
                                  '%s：`cd web` 依赖 runner 的 cwd（那是 checkout ' \
                                  '目录），请用绝对路径：%s' % (name, line.strip()))

    def test_52_smoke_step_asserts_the_panel_answers(self):
        """冒烟必须断言「面板真的应答了」，不能只敲启动命令（daemon=True 下那是假绿）。"""
        for name in sorted(HEAVY_WORKFLOWS):
            text = self._text(name)
            self.assertIn('/healthz', text,
                          '%s 没有调用 /healthz：只敲启动命令的话，gunicorn ' \
                          'double-fork 后立刻返回 0，端口没起来也会判绿' % name)
            self.assertIn('/www/server/yufeng_panel', text,
                          '%s 没有用面板的绝对路径' % name)
            self.assertIn('exit 1', text,
                          '%s 的冒烟步骤没有失败出口（只会一路绿下去）' % name)

    def test_53_actions_are_on_current_majors(self):
        """`actions/*` 不许停在 v3（Node.js 20 已弃用，会被强制跑在新 runtime 上）。"""
        floors = {'actions/checkout': 4, 'actions/setup-python': 5}
        for name in _workflow_files():
            text = self._text(name)
            for action, floor in floors.items():
                for m in re.finditer(re.escape(action) + r'@v(\d+)', text):
                    version = int(m.group(1))
                    self.assertGreaterEqual(
                        version, floor,
                        '%s 用了 %s@v%d（已弃用），请升到 v%d+'
                        % (name, action, version, floor))


class TestNoMaskedGateFailures(unittest.TestCase):
    """不许用 `|| true` / `continue-on-error` 把门禁失败吞掉。

    唯一的例外是 `security-scan.yml` 里那条**明确不阻断**的 bandit JSON 报告步骤
    （`-f json -o bandit-report.json || true`，与它同 job 的 `-lll` 阻断步骤并存）。
    一刀切禁掉会逼人删掉这条有用的报告 —— 所以这里把例外写死成「只允许这一行」，
    并反向断言真正的阻断步骤里没有它。
    """

    def test_40_security_scan_exception_is_only_the_report_line(self):
        text = _read(os.path.join('.github', 'workflows', 'security-scan.yml'))
        offenders = _masking_offenders(text)
        self.assertTrue(offenders, 'security-scan.yml 的非阻断报告步骤不应被删掉')
        for line in offenders:
            self.assertIn('bandit-report.json', line,
                          'security-scan.yml 只有非阻断报告步骤可用 `|| true`，这里是：%s' % line)
        # 阻断型步骤（pip-audit --strict / bandit -lll）必须原样保留且无掩盖
        self.assertIn('pip-audit -r requirements.txt --strict', text)
        self.assertIn('-lll', text)
        self.assertEqual([line.strip() for line in _effective_lines(text)
                          if 'continue-on-error' in line], [],
                         '阻断型 job 不得改成 continue-on-error')

    def test_41_all_workflows_checked(self):
        """覆盖全部 workflow：门禁类文件由各自的用例断言，这里保证「没有漏检的文件」。"""
        gate_files = {CORE_WORKFLOW} | set(HEAVY_WORKFLOWS)
        checked = gate_files | {'release.yml', 'i18n-check.yml', 'security-scan.yml'}
        self.assertEqual(set(_workflow_files()), checked,
                         '新增/删除了 workflow，请同步更新本守卫的检查清单')


if __name__ == '__main__':
    unittest.main()
