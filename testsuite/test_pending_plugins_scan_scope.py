# coding: utf-8
"""待审核插件「参考件化」守卫（2026-10-23 政策变更，取代 P2-11 的扫描范围守卫）。

## 政策变更

`文档/待审核插件/` 下的 34 个未转正插件一度被纳入安全扫描（P2-11）：
`scripts/verify_code_quality.py` 的 `PENDING_SCAN_DIR` + 5 个 `pending_*` 基线，
以及 `security-scan.yml` 的 `paths` 与 bandit 的 `-r` 目标。

2026-10-23 决定：**那批代码后续不会再被使用**，整目录打包成
`文档/待审核插件.7z`，仅作为后续开发的参考件（要复用时手工解包看，不会原样搬进
`plugins/`）。于是 P2-11 的扫描段失去了对象 —— 留着它只会变成「扫空目录恒绿」的
假守卫，还挂着 5 个 `pending_*` 基线，误导后人以为有东西正在被门禁保护。

## 本文件锁死的东西（新口径）

1. **活代码树已下线**：`文档/待审核插件/` 不得存在（防有人解包回去当活代码）；
   参考件 `文档/待审核插件.7z` 必须存在且非空；
2. **棘轮里不得再有待审核段**：`scripts/verify_code_quality.py` 的**代码标识符**里
   不许出现 `PENDING_SCAN_DIR` / `PENDING_METRICS` / `ALL_METRICS` /
   `_iter_pending_py_files`、也不许出现任何 `pending_*` 指标名；
   `scripts/code_quality_baseline.json` 不许有 `pending_*` 键；
3. **真跑一次 `run_scan()`**：扫到的文件必须全部落在 `web/`、`plugins/`、
   `panel_task.py`、`panel_tools.py` 之下 —— 防有人把 `文档/` 又塞回扫描范围；
4. **security-scan.yml 不再是待审核插件的触发器**：`paths`（push / pull_request）
   与两条 bandit 命令里都不许再出现该目录；同时两条 bandit 命令必须还在、
   `paths` 不许被清空、也不许出现全通配 `**`（否则上面几条断言会失去意义）；
5. **转正出口还在**：`文档/插件转正检查单.md` 必须存在，并写明新口径
   （从 `待审核插件.7z` 取参考 → 落到 `plugins/` → 走正式门禁）。

## 断言策略

* 标识符用 **AST** 取（`ast.Name` / `ast.Attribute` / 函数名 / 形参），不靠文本匹配
  —— 注释里解释「为什么删掉 `pending_*`」不能算违规；
* 行为用**真跑 `run_scan()`** 证明，而不是只看常量值；
* workflow 用 `yaml.safe_load` 解析后断言（GitHub 读的是解析后的 `paths:`，
  注释里出现的路径字符串不算数）；无 PyYAML 时退回 `test_ci_workflows_hardening.py`
  的受控行解析器（它自己的 `test_02` 会与 PyYAML 逐文件交叉比对）。

变异自证（手工执行，均实测变红 → 还原后绿）：
①删 `文档/待审核插件.7z` → 用例 01/02 红；②在 `verify_code_quality.py` 里加回
`PENDING_SCAN_DIR` 常量 → 用例 10 红；③把 `文档` 塞进 `SCAN_DIRS` → 用例 13 红
（这类「扩了范围但恰好空扫」只有常量级断言抓得住，见该用例说明）；
④把 `文档/待审核插件/**` 加回 `security-scan.yml` 的 paths → 用例 20 红；
⑤把它加回 bandit 目标 → 用例 21 红。
"""
import ast
import importlib.util
import io
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

QUALITY_SCRIPT = os.path.join(ROOT, 'scripts', 'verify_code_quality.py')
BASELINE_FILE = os.path.join(ROOT, 'scripts', 'code_quality_baseline.json')
SECURITY_WORKFLOW = os.path.join(ROOT, '.github', 'workflows', 'security-scan.yml')
CHECKLIST = os.path.join(ROOT, '文档', '插件转正检查单.md')

#: 参考件（源码树下线后**唯一**的载体）。
ARCHIVE = os.path.join(ROOT, '文档', '待审核插件.7z')
#: 已下线的活代码目录（必须不存在）。
PENDING_DIR = os.path.join(ROOT, '文档', '待审核插件')
#: 任何位置都不许再出现的目录名（paths / bandit 目标 / 扫描范围）。
PENDING_TOKEN = '文档/待审核插件'

#: 允许被扫描的根：正式代码（含插件）+ 根级脚本。
PRODUCTION_ROOTS = ('web/', 'plugins/')
PRODUCTION_FILES = ('panel_task.py', 'panel_tools.py')

#: 棘轮里不许再出现的标识符（P2-11 扫描段的组成部分）。
FORBIDDEN_IDENTIFIERS = ('PENDING_SCAN_DIR', 'PENDING_METRICS', 'ALL_METRICS',
                         '_iter_pending_py_files')
#: 指标名前缀：`pending_*` 这套基线只属于已撤销的待审核段。
FORBIDDEN_PREFIX = 'pending_'


def _read(path):
    with io.open(path, encoding='utf-8', errors='replace') as fh:
        return fh.read().replace('\r\n', '\n')


def _load_module_by_path(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _quality_detector():
    """加载 `scripts/verify_code_quality.py`（纯标准库），复用同一份检测器。"""
    if 'yf_pending_quality_detector' not in __import__('sys').modules:
        mod = _load_module_by_path(QUALITY_SCRIPT, 'yf_pending_quality_detector')
        __import__('sys').modules['yf_pending_quality_detector'] = mod
    return __import__('sys').modules['yf_pending_quality_detector']


def _identifiers(path):
    """AST 取模块里**真正用到的标识符**（名字、属性名、函数名、形参名）。

    刻意不读注释与字符串：文件头需要写清楚「为什么删掉 `pending_*`」，
    正文注释也可能提到旧常量名 —— 那些都不算「代码里还有它」。
    """
    tree = ast.parse(_read(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
    return names


def _load_trigger():
    """解析 `security-scan.yml` 的触发块 → `{事件: {子键: [值...]}}`（非文本匹配）。"""
    text = _read(SECURITY_WORKFLOW)
    try:
        import yaml
    except ImportError:
        parser = _load_module_by_path(
            os.path.join(HERE, 'test_ci_workflows_hardening.py'), 'yf_pending_trigger_parser')
        return parser.parse_trigger_regex(text)
    data = yaml.safe_load(text)
    trig = data.get('on', data.get(True, {})) or {}
    out = {}
    for event, cfg in trig.items():
        sub = {}
        if isinstance(cfg, dict):
            for key, val in cfg.items():
                if isinstance(val, list):
                    sub[str(key)] = [str(v) for v in val]
        out[str(event)] = sub
    return out


def _bandit_commands():
    """所有 `bandit -r ...` 命令（阻断档 + 报告档）。"""
    text = _read(SECURITY_WORKFLOW)
    try:
        import yaml
    except ImportError:
        return [line.strip() for line in text.split('\n')
                if line.strip().startswith('bandit -r')]
    cmds = []
    for job in (yaml.safe_load(text).get('jobs') or {}).values():
        for step in (job or {}).get('steps') or []:
            for line in (step.get('run') or '').split('\n'):
                if line.strip().startswith('bandit -r'):
                    cmds.append(line.strip())
    return cmds


class TestReferenceArchiveOnly(unittest.TestCase):
    """1：活代码树已下线，参考件（7z）还在。"""

    def test_01_live_tree_is_gone(self):
        self.assertFalse(
            os.path.isdir(PENDING_DIR),
            '`文档/待审核插件/` 又出现了：2026-10-23 起该目录已整目录打包成 '
            '`文档/待审核插件.7z`，源码树不再入库。要复用请解包到仓库外的目录看，'
            '不要解回仓库（否则它会被误当成活代码，也会重新进扫描/棘轮的口径争议）。')

    def test_02_archive_exists(self):
        self.assertTrue(os.path.isfile(ARCHIVE),
                        '缺少参考件 `文档/待审核插件.7z` —— 它是那批插件代码的唯一载体，'
                        '删掉就等于永久丢弃后续开发的参考')
        size = os.path.getsize(ARCHIVE)
        self.assertGreater(size, 64 * 1024,
                           '参考件只有 %d 字节，疑似空包/截断（原包约 470KB）' % size)


class TestRatchetHasNoPendingSegment(unittest.TestCase):
    """2 + 3：棘轮里没有待审核段，且扫描结果只覆盖正式代码。"""

    def test_10_quality_script_has_no_pending_identifiers(self):
        names = _identifiers(QUALITY_SCRIPT)
        hit = sorted(n for n in names
                     if n in FORBIDDEN_IDENTIFIERS or n.startswith(FORBIDDEN_PREFIX))
        self.assertEqual(
            hit, [],
            'verify_code_quality.py 里又出现了待审核扫描段的标识符 %r。'
            '该段已随「待审核插件打包成参考件」撤销：目录都不存在，扫它只会'
            '「扫空目录恒绿」，是假守卫。要上线的新插件落进 `plugins/` 就会被扫。' % hit)

    def test_11_baseline_has_no_pending_keys(self):
        with io.open(BASELINE_FILE, encoding='utf-8') as fh:
            baseline = json.load(fh)
        stale = sorted(k for k in baseline if k.startswith(FORBIDDEN_PREFIX))
        self.assertEqual(stale, [],
                         'scripts/code_quality_baseline.json 还留着待审核段的基线键 %r'
                         '（对应的扫描代码已删除，这些键永远不会有读数）' % stale)

    def test_12_run_scan_only_covers_production_code(self):
        """真跑一次检测器：任何落到 `文档/`（或其它非正式代码）的命中都算红。"""
        detector = _quality_detector()
        result = detector.run_scan()
        scanned = set()
        for metric in detector.METRICS:
            for path, _line, _snippet in result[metric]:
                scanned.add(path.replace('\\', '/'))
        self.assertTrue(scanned, 'run_scan() 一个文件都没扫到，检测器已经空转')
        bad = sorted(p for p in scanned
                     if not (p.startswith(PRODUCTION_ROOTS) or p in PRODUCTION_FILES))
        self.assertEqual(
            bad, [],
            '扫描结果里出现了正式代码之外的路径 %r —— 有人把 `文档/`（或别的参考件目录）'
            '重新塞进了扫描范围。参考件不进生产，也不该进棘轮' % bad[:5])


    def test_13_scan_scope_is_exactly_production(self):
        """扫描范围常量必须**逐字**等于正式代码。

        只靠 `test_12`（真跑一遍、看命中路径）不够：如果有人把 `文档/` 塞回
        `SCAN_DIRS`，而那儿恰好没有任何 `*.py`（参考件已打包成 7z 就是这样），
        一次空扫照样全绿 —— 那正是本仓库最忌讳的「假守卫」。所以这里把常量本身
        钉死：扩范围必须显式改用例并说明理由。
        """
        consts = {}
        for node in ast.parse(_read(QUALITY_SCRIPT)).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1                     and isinstance(node.targets[0], ast.Name):
                try:
                    consts[node.targets[0].id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    continue
        self.assertEqual(consts.get('SCAN_DIRS'), ['web', 'plugins'],
                         'SCAN_DIRS 变了：%r —— 参考件（文档/）不属于扫描范围，'
                         '要上线的插件落进 plugins/ 就会被扫' % (consts.get('SCAN_DIRS'),))
        self.assertEqual(consts.get('SCAN_ROOT_PY'), ['panel_task.py', 'panel_tools.py'],
                         'SCAN_ROOT_PY 变了：%r' % (consts.get('SCAN_ROOT_PY'),))


class TestSecurityScanWorkflowScope(unittest.TestCase):
    """4：security-scan.yml 不再是待审核插件目录的触发器。"""

    @classmethod
    def setUpClass(cls):
        cls.trigger = _load_trigger()
        cls.cmds = _bandit_commands()

    def test_20_paths_do_not_reference_pending_dir(self):
        for event in ('push', 'pull_request'):
            paths = (self.trigger.get(event) or {}).get('paths', [])
            hit = [p for p in paths if PENDING_TOKEN in p]
            self.assertEqual(
                hit, [],
                'security-scan.yml 的 %s paths 仍有 %r：该目录已是参考件（7z 里没有可执行'
                '代码），改它触发全量扫描既扫不到代码、又白占 CI 配额。'
                '要上线的插件落进 `plugins/` 那条路径本来就被扫' % (event, hit))

    def test_21_bandit_targets_do_not_reference_pending_dir(self):
        self.assertGreaterEqual(len(self.cmds), 2,
                                'bandit 的扫描命令少于 2 条（阻断 + 报告两条都要留）')
        bad = [c for c in self.cmds if PENDING_TOKEN in c]
        self.assertEqual(
            bad, [],
            '这些 bandit 命令还带着已下线的参考件目录：%r。'
            'bandit 扫不存在的目录 = 「看起来扫了」的假覆盖' % bad)

    def test_22_scan_scope_still_covers_production(self):
        """反向：撤掉参考件不许把正式代码的覆盖也一起撤掉。"""
        for event in ('push', 'pull_request'):
            paths = (self.trigger.get(event) or {}).get('paths', [])
            self.assertTrue(paths, '%s 的 paths 被清空了' % event)
            self.assertNotIn('**', paths, '%s 的 paths 出现全通配 **' % event)
            for required in ('plugins/**/*.py', 'web/**.py', 'scripts/**.py'):
                self.assertIn(required, paths,
                              '%s 的 paths 缺少 %s —— 正式代码的触发范围被缩小了'
                              % (event, required))
        joined = ' '.join(self.cmds)
        for target in ('web', 'scripts', 'panel_task.py', 'panel_tools.py'):
            self.assertIn(target, joined, 'bandit 目标里少了 %s' % target)


class TestChecklistDoc(unittest.TestCase):
    """5：转正出口还在，且写明新口径。"""

    @classmethod
    def setUpClass(cls):
        cls.text = _read(CHECKLIST) if os.path.isfile(CHECKLIST) else ''

    def test_30_checklist_file_exists(self):
        self.assertTrue(os.path.isfile(CHECKLIST),
                        '缺少 文档/插件转正检查单.md —— 没有检查单，「转正必须过审计」'
                        '就没有载体（参考件唯一的出口就是这张单子）')

    def test_31_checklist_covers_key_items(self):
        """关键条目逐词命中：任一被删掉，都意味着某类风险从检查单里消失了。"""
        required = {
            '待审核插件.7z': '参考件载体与取用口径（不再是活代码目录）',
            'plugins/': '落地位置：转正 = 搬进 plugins/，随后自动进正式门禁',
            'os.system': '命令注入面（execShell / os.system / eval / 裸拼命令）',
            'bandit': 'bandit 无 HIGH 的机械门禁',
            'i18n': '六语言键齐全 + 死键清零',
            '严格模式': '安装/卸载脚本的 set -euo pipefail',
            'writefile': '棘轮指标里的 writefile_bare_success',
            'ERR trap': '安装脚本失败可定位',
            'lib_install_report': 'P1-8 规范库落账',
            'requirements.txt': '依赖与锁口径',
            '组件生命周期与安全响应政策': '危险版本下架口径对齐',
            '36': '36 插件契约计数同步',
            '审计人': '审计记录表格模板',
        }
        missing = [('%s（%s）' % (word, why)) for word, why in required.items()
                   if word not in self.text]
        self.assertEqual(missing, [], '转正检查单缺少这些条目：%s' % missing)

    def test_32_checklist_has_checkboxes(self):
        """必须是「可勾选清单」，不是散文。"""
        ticks = self.text.count('- [ ]')
        self.assertGreaterEqual(ticks, 15, '可勾选项只有 %d 条，检查单退化成散文了' % ticks)


if __name__ == '__main__':
    unittest.main(verbosity=2)
