# coding: utf-8
"""P2-11 守卫：待审核插件目录必须留在安全扫描范围之内。

## 故障现场（改前的真实形状）

`文档/待审核插件/` 里有 **34** 个还没转正的插件，它们原本**完全在门禁之外**：

* `scripts/verify_code_quality.py` 的 `SCAN_DIRS = ['web', 'plugins']` 不含它，
  连 `EXCLUDE_DIRS` 都把整个 `文档` 排除了 —— 代码质量棘轮对它彻底失明；
* `.github/workflows/security-scan.yml` 的 `paths:`（push 与 pull_request 两处）
  与 bandit 的 `-r web scripts panel_task.py panel_tools.py` 都没有它；
* `web/utils/plugin.py` 的插件列表还把 `待审核` 显式排除。

后果不是「现在有洞」，而是「**转正那一刻才第一次被扫**」：转正的动作就是把这些文件
原样搬进 `plugins/` 直接进生产 —— 存量里已经写着 `os.system` / 裸 `except` /
`except Exception: pass` / 裸 `yf.writeFile` 后直接报成功。

## 修复口径（本文件锁死的东西）

1. 扫描范围：`scripts/verify_code_quality.py` 新增 `PENDING_SCAN_DIR = '文档/待审核插件'`，
   **单独成常量**（不塞进 `SCAN_DIRS`），指标键加 `pending_` 前缀单独记基线；
2. 基线是**实测现值 + 只减不增**（`scripts/code_quality_baseline.json` 的 `pending_*`），
   既不设 0（会让 34 个插件的存量立刻把门禁打红），也不把它排除在外（那就是原来的洞）；
3. 触发范围：`security-scan.yml` 的 push / pull_request 两处 `paths:` 与 bandit 两处
   `-r` 目录都含该目录；
4. 转正资格：`文档/插件转正检查单.md`（本文件只校验它存在且关键条目在位）。

## 断言策略

* 扫描范围用 **AST 取常量值** + **真跑 `run_scan()`**：只断言「源码里出现了这个字符串」
  太弱（注释里写一句就能骗过），所以额外证明「这个常量真的把文件喂进了扫描器」——
  删掉常量、或把 `_iter_pending_py_files()` 从 `run_scan()` 里摘掉，都会红。
* baseline 的 `pending_*` 值与**本文件写死的常量双向一致**：只改基线不改用例、或只改用例
  不改基线，都会红（防止「悄悄放宽基线」这种最省事的作弊）。
* workflow 用 `yaml.safe_load` 解析后断言（不用文本匹配）：文本匹配会把注释里出现的
  `文档/待审核插件/**` 也算成通过，而 GitHub 读的是解析后的 `paths:`。
  PyYAML 缺失时退回 `test_ci_workflows_hardening.py` 的受控行解析器（那个解析器由
  它自己的 `test_02` 与 PyYAML 逐文件交叉比对过），因此本文件对 PyYAML 不是硬依赖。
* 目录本身仍然存在且非空：防止有人「删掉待审核目录」来让上面几条轻松变绿。

变异自证（手工执行，输出见整改报告）：把 `PENDING_SCAN_DIR` 从扫描范围里去掉 → 用例 1/2 红；
把 `文档/待审核插件/**` 从 push 的 `paths:` 删掉 → 用例 3 红；改回即绿。
"""
import ast
import importlib.util
import io
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

QUALITY_SCRIPT = os.path.join(ROOT, 'scripts', 'verify_code_quality.py')
BASELINE_FILE = os.path.join(ROOT, 'scripts', 'code_quality_baseline.json')
SECURITY_WORKFLOW = os.path.join(ROOT, '.github', 'workflows', 'security-scan.yml')
CHECKLIST = os.path.join(ROOT, '文档', '插件转正检查单.md')
PENDING_DIR = os.path.join(ROOT, '文档', '待审核插件')

#: 待审核目录在扫描范围里的**唯一事实来源**（verify_code_quality.py 的常量值）。
PENDING_SCAN_DIR = '文档/待审核插件'
#: GitHub `paths` 过滤使用的模式（`**` 跨层级，覆盖目录下一切文件）。
PENDING_PATH_GLOB = '文档/待审核插件/**'

#: 待审核段基线 = **2026-10-22 实测现值**（P2-11 落地时跑 `verify_code_quality.py` 得到）。
#: 只减不增：每清掉一处，这里和 scripts/code_quality_baseline.json 都要跟着降。
#:
#: 实测来源（34 个条目 / 44 个 *.py，其中 15 个文件有命中）：
#:   bare_except 32（裸 except）    silent_except 9（except + 紧跟 pass）
#:   print_in_web 0（与正式插件同口径：该项只统计 web/）  os_system_count 13
#:   writefile_bare_success 23（裸 yf.writeFile 后 6 行内 returnJson(True)）
PENDING_BASELINE = {
    'pending_bare_except': 32,
    'pending_silent_except': 9,
    'pending_print_in_web': 0,
    'pending_os_system_count': 13,
    'pending_writefile_bare_success': 23,
}


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
    return _load_module_by_path(QUALITY_SCRIPT, 'p211_quality_detector')


def _module_constants(path):
    """用 AST 取模块级 `NAME = <字面量>` 的赋值（不执行、不依赖注释文本）。"""
    out = {}
    for node in ast.parse(_read(path)).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    out[target.id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    continue
    return out


def _load_trigger():
    """解析 `security-scan.yml` 的触发块 → `{事件: {子键: [值...]}}`。

    优先 PyYAML（`requirements.txt` 已含，CI 必有）；本机没有时退回
    `testsuite/test_ci_workflows_hardening.py` 的受控行解析器 —— 它自己的
    `test_02` 会在 PyYAML 可用时把两者逐文件比对，所以这条退路不是「换个更松的判据」。
    两条路径都**不是文本匹配**：注释里出现的模式串不会进结果。
    """
    text = _read(SECURITY_WORKFLOW)
    try:
        import yaml
    except ImportError:
        parser = _load_module_by_path(
            os.path.join(HERE, 'test_ci_workflows_hardening.py'), 'p211_trigger_parser')
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


class TestPendingDirInScanScope(unittest.TestCase):
    """1 + 2：待审核目录在代码质量棘轮的扫描范围里，且有独立基线兜住存量。"""

    @classmethod
    def setUpClass(cls):
        cls.vcq = _quality_detector()

    def test_01_pending_dir_is_a_scan_constant(self):
        """扫描范围常量必须**真的存在且等于** `文档/待审核插件`（AST 取值，不看注释）。"""
        consts = _module_constants(QUALITY_SCRIPT)
        self.assertIn('PENDING_SCAN_DIR', consts,
                      'scripts/verify_code_quality.py 里没有 PENDING_SCAN_DIR 常量 —— '
                      '待审核目录又回到扫描范围之外了（P2-11 回退）')
        self.assertEqual(consts['PENDING_SCAN_DIR'], PENDING_SCAN_DIR,
                         'PENDING_SCAN_DIR 的值被改成了别的东西：%r' % (consts['PENDING_SCAN_DIR'],))
        # 刻意不塞进 SCAN_DIRS：那是「已发布的正式代码」的语义，
        # 混进去会让待审核存量直接污染正式基线（正式段 bare/silent/print 现在是 0）。
        self.assertNotIn(PENDING_SCAN_DIR, consts.get('SCAN_DIRS', []),
                         '待审核目录被塞进了 SCAN_DIRS：正式段基线会被存量稀释，'
                         '请用 PENDING_SCAN_DIR + pending_* 指标族')

    def test_02_pending_files_really_reach_the_scanner(self):
        """光有常量不算数：必须证明它真把待审核目录的 *.py 喂进了扫描器。"""
        files = list(self.vcq._iter_pending_py_files())
        self.assertTrue(files, 'PENDING_SCAN_DIR 没扫到任何文件（路径写错了？目录被删了？）')
        bad = [f for f in files
               if not os.path.relpath(f, ROOT).replace(os.sep, '/')
               .startswith(PENDING_SCAN_DIR + '/')]
        self.assertEqual(bad, [], '扫描到了待审核目录之外的文件：%s' % bad[:5])

    def test_03_run_scan_has_pending_metrics(self):
        """`run_scan()` 必须产出 pending_* 指标，且确实数到了存量（不是空转的 0）。"""
        counts = self.vcq.counts_of(self.vcq.run_scan())
        for key in PENDING_BASELINE:
            self.assertIn(key, counts, 'run_scan() 没有产出 %s' % key)
        self.assertGreater(counts['pending_bare_except'], 0,
                           '待审核段的裸 except 统计为 0：要么存量被清了（请下调基线），'
                           '要么这个目录根本没被扫（那就是 P2-11 的老问题）')

    def test_04_baseline_keys_present_and_measured(self):
        """基线文件里必须有全部 pending_* 键，且当前实测值 ≤ 基线（真跑棘轮）。"""
        baseline = self.vcq.load_baseline()
        missing = [k for k in PENDING_BASELINE if k not in baseline]
        self.assertEqual(missing, [],
                         'scripts/code_quality_baseline.json 缺少待审核段基线键：%s'
                         '（用 `python scripts/verify_code_quality.py --update` 按实测值生成，'
                         '不许手工写大）' % missing)
        counts = self.vcq.counts_of(self.vcq.run_scan())
        over = {k: (counts[k], baseline[k]) for k in PENDING_BASELINE
                if counts[k] > baseline[k]}
        self.assertEqual(over, {},
                         '待审核段指标超过了基线（当前, 基线）：%r。'
                         '要么清掉新增的违规，要么在报告里说明后**下调**基线；'
                         '不许把基线改大' % over)

    def test_05_static_gate_exit_code_zero(self):
        """子进程真跑一次棘轮：退出码必须是 0（`--static` 里的那一条就是它）。"""
        proc = subprocess.run([sys.executable, 'scripts/verify_code_quality.py'],
                              cwd=ROOT, capture_output=True, timeout=280)
        out = (proc.stdout + proc.stderr).decode('utf-8', 'replace')
        self.assertEqual(proc.returncode, 0,
                         'scripts/verify_code_quality.py 退出码非 0：\n%s' % out)

    def test_06_pending_baseline_not_silently_loosened(self):
        """基线不可悄悄放宽：文件里的 pending_* 值必须等于本用例写死的常量（双向）。"""
        baseline = self.vcq.load_baseline()
        in_file = {k: v for k, v in baseline.items() if k.startswith('pending_')}
        self.assertEqual(sorted(in_file), sorted(PENDING_BASELINE),
                         '基线文件里的 pending_* 键集合与本用例不一致：文件 %r / 用例 %r。'
                         '新增或删除指标时两处必须同步' % (sorted(in_file), sorted(PENDING_BASELINE)))
        drifted = {k: (in_file[k], PENDING_BASELINE[k]) for k in PENDING_BASELINE
                   if in_file.get(k) != PENDING_BASELINE[k]}
        self.assertEqual(drifted, {},
                         'pending_* 基线被单方面改过（文件值, 用例值）：%r。'
                         '放宽基线必须同时改用例并在报告里写明理由与实测证据' % drifted)


class TestSecurityScanWorkflowScope(unittest.TestCase):
    """3：`security-scan.yml` 的 push / pull_request 触发范围与 bandit 目录都覆盖待审核目录。"""

    @classmethod
    def setUpClass(cls):
        cls.trigger = _load_trigger()
        cls.text = _read(SECURITY_WORKFLOW)

    def test_10_push_paths_include_pending_dir(self):
        paths = (self.trigger.get('push') or {}).get('paths', [])
        self.assertIn(PENDING_PATH_GLOB, paths,
                      'security-scan.yml 的 push paths 不含 %s —— 改动待审核插件不会触发扫描'
                      '（现有 paths：%r）' % (PENDING_PATH_GLOB, paths))

    def test_11_pull_request_paths_include_pending_dir(self):
        paths = (self.trigger.get('pull_request') or {}).get('paths', [])
        self.assertIn(PENDING_PATH_GLOB, paths,
                      'security-scan.yml 的 pull_request paths 不含 %s（现有 paths：%r）'
                      % (PENDING_PATH_GLOB, paths))

    def test_12_bandit_scan_dirs_include_pending_dir(self):
        """bandit 是**显式列目录**的，所以命令里也得有它（两个步骤都要）。"""
        try:
            import yaml
        except ImportError:  # 无 PyYAML 时退化为「逐行找 bandit -r」的受控解析
            cmds = [line for line in self.text.split('\n')
                    if line.strip().startswith('bandit -r')]
        else:
            cmds = []
            for job in (yaml.safe_load(self.text).get('jobs') or {}).values():
                for step in (job or {}).get('steps') or []:
                    run = step.get('run') or ''
                    cmds.extend(line for line in run.split('\n')
                                if line.strip().startswith('bandit -r'))
        self.assertGreaterEqual(len(cmds), 2, 'bandit 的扫描命令少于 2 条（阻断 + 报告）')
        bad = [c.strip() for c in cmds if PENDING_SCAN_DIR not in c]
        self.assertEqual(bad, [],
                         '这些 bandit 命令没扫待审核目录：%r' % bad)

    def test_13_trigger_still_has_no_regression(self):
        """顺带确认没把整个 paths 改成通配（那等于「每次都扫」，也会让上面的断言失去意义）。"""
        for event in ('push', 'pull_request'):
            paths = (self.trigger.get(event) or {}).get('paths', [])
            self.assertTrue(paths, '%s 的 paths 被清空了' % event)
            self.assertNotIn('**', paths, '%s 的 paths 出现全通配 **' % event)


class TestChecklistDoc(unittest.TestCase):
    """4：转正检查单存在，且关键条目在位（否则「纳入扫描」只是半道门禁）。"""

    @classmethod
    def setUpClass(cls):
        cls.text = _read(CHECKLIST) if os.path.isfile(CHECKLIST) else ''

    def test_20_checklist_file_exists(self):
        self.assertTrue(os.path.isfile(CHECKLIST),
                        '缺少 文档/插件转正检查单.md —— 没有检查单，「转正必须过审计」就没有载体')

    def test_21_checklist_covers_key_items(self):
        """关键条目逐词命中：任一被删掉，都意味着某类风险从检查单里消失了。"""
        # 词 -> 它代表的那条要求（报红时能直接看出丢了什么）
        required = {
            'os.system': '命令注入面（execShell / os.system / eval / 裸拼命令）',
            'bandit': 'bandit 无 HIGH 的机械门禁',
            'i18n': '六语言键齐全 + 死键清零',
            '严格模式': '安装/卸载脚本的 set -euo pipefail',
            'writefile': '棘轮 5 项指标里的 writefile_bare_success',
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

    def test_22_checklist_has_checkboxes(self):
        """必须是「可勾选清单」，不是散文。"""
        ticks = self.text.count('- [ ]')
        self.assertGreaterEqual(ticks, 15, '可勾选项只有 %d 条，检查单退化成散文了' % ticks)


class TestPendingDirStillExists(unittest.TestCase):
    """6：顺带守卫 —— 待审核目录仍存在且非空（防「删目录让检查变绿」）。"""

    def test_30_pending_dir_exists_and_not_empty(self):
        self.assertTrue(os.path.isdir(PENDING_DIR),
                        '文档/待审核插件/ 不见了：P2-11 只做「纳入扫描 + 检查单」，'
                        '不是「删掉待审核目录」。真要清空必须先逐个走完转正检查单')
        entries = [n for n in os.listdir(PENDING_DIR) if not n.startswith('.')]
        self.assertGreater(len(entries), 0,
                           '文档/待审核插件/ 空了 —— 是转正搬走了，还是被人删了？'
                           '转正必须同步 36 插件契约计数并更新本用例')


if __name__ == '__main__':
    unittest.main(verbosity=2)
