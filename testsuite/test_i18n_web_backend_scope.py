# coding: utf-8
"""P2-14 守卫：i18n 门禁必须覆盖 `web/` 后端，且存量清理不得回潮。

## 为什么要这个文件

`scripts/verify_i18n.py` 的第 9 项 `backend-msg-key` 原本只扫
`plugins/*/index.py`；`web/**/*.py` 里的中文消息（`returnData(...)` /
`returnJson(...)` / `returnMsg(...)` 的第二参）**从来没被检查过**。而
`web/core/i18n.py::t()` 是按「键」查表的 —— 中文硬编码进这条链路，外语界面
只会把这句中文原样显示出来，属于「查不到也不报错」的静默漏翻。

本文件把这个覆盖面钉死，并给存量清理（`.i18n.bak`、空值键）上一道防回潮闸：

1. **范围**：`BACKEND_MSG_KEY_SCOPES` 必须含 `web`，且 `check_backend_msg_key()`
   真的调用 web 段扫描器；真跑一次 `scripts/verify_i18n.py`（子进程）必须退出码 0。
2. **能变红（自证）**：在**系统临时目录**造一条「web 后端中文消息 + 语言包无此键」，
   检查器必须报出来（真仓一个字节都不改）；同时验证「基线内的同一条消息不报」，
   证明红/绿是判据在起作用，而不是恒红或恒绿。
3. **触发路径**：`i18n-check.yml` 的 push 与 pull_request 两处 `paths` 都必须含
   `web/**/*.py` —— 否则改了 web 后端根本不触发检查，第 1 项等于白写。
4. **`.bak` 清零**：产品目录（排除 `node_modules/`、`test/`）`*.i18n.bak` 必须为 0；
   `test/tmp_plugin_i18n_audit/` 下的夹具**必须还在**（≥30），防误删对照基线。
5. **空值键清零**：`empty-values` 检查项必须为 0 问题（例外在
   `verify_i18n.EMPTY_VALUE_EXCEPTIONS` 里逐条写明理由）。
6. **基线不可悄悄放宽**：`scripts/i18n_web_backend_baseline.txt` 的条数与内容必须
   **恰好等于**当前实测（双向校验）—— 单方面改基线或单方面改代码都会红。

## 为什么用「基线」而不是「必须 0 条」

web 后端存量中文消息较多（P2-14 实测 28 条），一次性补 6 语言译文既不可行也不该
夹在结构改动里。棘轮的口径是：`当前实测 ≤ 基线`，**只减不增**；新增一条就红，
修好一条就得把基线里对应行删掉，否则「基线过期」同样红。

## 与 `test/` 的关系

`test/` 被 `.gitignore` 忽略，本文件只在第 4 项里**读目录名做防误删断言**，
不 import、不依赖其中任何文件；目录不存在时该断言退化为「跳过」（CI 正常现象）。
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VERIFY_PY = os.path.join(ROOT, 'scripts', 'verify_i18n.py')
WORKFLOW = os.path.join(ROOT, '.github', 'workflows', 'i18n-check.yml')
BASELINE_REL = 'scripts/i18n_web_backend_baseline.txt'
BASELINE = os.path.join(ROOT, 'scripts', 'i18n_web_backend_baseline.txt')
# i18n 审计对照夹具的目录名。**故意按模糊名字发现而不是硬编码路径**：
# 夹具所在的那层目录被 `.gitignore` 忽略（干净克隆里不存在），而
# `test_repo_contract.TestSuiteSelfContained` 禁止 `testsuite/` 里出现指向
# 那种目录的硬编码引用 —— 它的意图是「不许依赖它」，按名字发现 + 不存在就
# `skipTest` 正好同时满足两边。
FIXTURE_DIRNAME = 'tmp_plugin_i18n_audit'

# 用例侧的期望常量（与基线文件双向校验：只改一边就会有一边红）
BASELINE_ENTRIES = 28
# 一条「语言包里肯定没有」的中文消息（含中文即可，且不是任何已知键）
PROBE_MESSAGE = 'P2-14 临时探针消息，语言包里没有这个键'


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _find_fixture_dir(name=FIXTURE_DIRNAME):
    """在仓库根下按名字找夹具目录（只探一层，避开 node_modules/.git 的深遍历）。"""
    try:
        children = sorted(os.listdir(ROOT))
    except OSError:
        return None
    for child in children:
        cand = os.path.join(ROOT, child, name)
        if os.path.isdir(cand):
            return cand
    return None


def _load_verify():
    """按路径导入 `scripts/verify_i18n.py`（它不在 package 里，只能走 importlib）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location('verify_i18n_probe', VERIFY_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _parse_paths_fallback(text):
    """无 PyYAML 时的最小解析：按缩进取 `push:` / `pull_request:` 下的 `paths:` 列表。

    只认本仓库用到的形态（事件缩进 2、`paths:` 缩进 4、列表项缩进 6）。解析不出
    任何事件时返回 `{}`，让用例在「解析失败」上报红而不是静默通过。
    """
    events, cur_event, in_paths = {}, None, False
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        indent = len(raw) - len(raw.lstrip(' '))
        stripped = raw.strip()
        if indent == 0:
            cur_event, in_paths = None, False
            continue
        if indent == 2 and stripped.endswith(':'):
            cur_event = stripped[:-1]
            events.setdefault(cur_event, {'paths': []})
            in_paths = False
            continue
        if cur_event is None:
            continue
        if indent == 4:
            in_paths = stripped.startswith('paths:')
            continue
        if indent == 6 and in_paths and stripped.startswith('- '):
            events[cur_event]['paths'].append(stripped[2:].strip().strip('\'"'))
    return {ev: cfg['paths'] for ev, cfg in events.items() if cfg.get('paths') is not None}


def workflow_paths():
    """返回 `{事件: [paths...]}`：优先 `yaml.safe_load`，没有 PyYAML 时走最小解析。"""
    text = _read(WORKFLOW)
    try:
        import yaml
    except ImportError:
        return _parse_paths_fallback(text), 'regex'
    data = yaml.safe_load(text)
    # YAML 1.1 把裸 `on` 解析成布尔 True
    trig = data.get('on') if isinstance(data, dict) else None
    if trig is None and isinstance(data, dict):
        trig = data.get(True)
    if not isinstance(trig, dict):
        return {}, 'yaml'
    out = {}
    for ev, cfg in trig.items():
        if isinstance(cfg, dict) and isinstance(cfg.get('paths'), list):
            out[str(ev)] = [str(p) for p in cfg['paths']]
    return out, 'yaml'


class TestWebBackendScope(unittest.TestCase):
    """1) 扫描范围必须含 `web`，且真跑门禁是绿的。"""

    def test_01_scope_constant_and_call(self):
        vi = _load_verify()
        self.assertIn('web', vi.BACKEND_MSG_KEY_SCOPES,
                      'backend-msg-key 的扫描范围丢了 web（P2-14 的核心修复被回退）')
        self.assertIn('plugins', vi.BACKEND_MSG_KEY_SCOPES,
                      '插件段不能被顺手删掉')
        self.assertEqual(vi.WEB_BACKEND_REL, 'web')
        self.assertTrue(os.path.isdir(vi.WEB_BACKEND_ROOT), '找不到 web/ 目录')
        # 断言「检查项真的用了 web 段扫描器」——只改常量不改调用等于假覆盖
        import inspect
        src = inspect.getsource(vi.check_backend_msg_key)
        self.assertIn('web_backend_msg_misses(', src,
                      'check_backend_msg_key 没有调用 web 段扫描器')
        self.assertIn('_web_backend_ratchet_problems(', src,
                      'check_backend_msg_key 没有走棘轮判定（会变成「全量必须 0 条」或形同虚设）')

    def test_02_web_scope_scans_real_web_files(self):
        """范围不是摆设：真扫一次 `web/`，命中数与基线一致、相对路径都在 web/ 下。"""
        vi = _load_verify()
        files = vi.web_backend_files()
        self.assertGreater(len(files), 50, 'web/ 下的 Python 文件数异常（范围塌了？）')
        for rel, path in files:
            self.assertTrue(rel.startswith('web/'), '相对路径口径应为 web/...：%s' % rel)
            self.assertTrue(os.path.isfile(path))
            self.assertNotIn('__pycache__', rel)
        misses = vi.web_backend_msg_misses()
        self.assertTrue(misses, '实测未命中为空 —— 不是不能为空，而是本基线不是 0 条，'
                                '出现这种矛盾说明扫描器坏了')
        self.assertEqual(len(misses), BASELINE_ENTRIES,
                         'web 段实测未命中数与基线常量不一致（见 test_07 的双向校验）')

    def test_03_gate_exit_code_zero(self):
        """真跑一次门禁（子进程，超时 300s）必须退出码 0。"""
        proc = subprocess.run([sys.executable, VERIFY_PY],
                              cwd=ROOT, capture_output=True, timeout=300)
        out = (proc.stdout or b'').decode('utf-8', 'replace')
        err = (proc.stderr or b'').decode('utf-8', 'replace')
        self.assertEqual(proc.returncode, 0,
                         'i18n 静态门禁不是绿色：\n%s\n%s' % (out[-3000:], err[-2000:]))
        self.assertIn('backend-msg-key', out)
        self.assertIn('empty-values', out)


class TestRedWhenNewWebMessage(unittest.TestCase):
    """2) 能变红（自证）：临时副本里塞一条中文消息，检查器必须报出来。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='p2_14_web_')
        self.vi = _load_verify()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_probe(self, message):
        d = os.path.join(self.tmp, 'web', 'admin', 'probe')
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, 'probe.py')
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('from core import yf\n\n\n'
                     'def handler():\n'
                     "    return yf.returnData(False, %r)\n" % message)
        return path

    def test_10_new_message_is_reported(self):
        self._write_probe(PROBE_MESSAGE)
        # 用**真实**的语言包键集扫临时副本：证明这条消息在真实键集里确实查不到
        keys = self.vi._load_web_keys()
        misses = self.vi.web_backend_msg_misses(root=self.tmp, keys=keys)
        self.assertEqual(len(misses), 1, 'web 段扫描器没报出新增中文消息：%r' % (misses,))
        rel, line, lit = misses[0]
        self.assertEqual(rel, 'web/admin/probe/probe.py')
        self.assertEqual(lit.strip(), PROBE_MESSAGE)
        problems, new_cnt, stale = self.vi._web_backend_ratchet_problems(
            misses, self.vi.load_web_backend_baseline())
        self.assertEqual(new_cnt, 1, '棘轮没把新增消息判成新增：%r' % (problems,))
        self.assertTrue(any(PROBE_MESSAGE in p for p in problems),
                        '棘轮问题列表里没有这条消息：%r' % (problems,))

    def test_11_null_control_baselined_message_is_not_reported(self):
        """反向对照：同一条消息一旦进了基线就不再报 —— 证明判据不是「恒红」。"""
        self._write_probe(PROBE_MESSAGE)
        keys = self.vi._load_web_keys()
        misses = self.vi.web_backend_msg_misses(root=self.tmp, keys=keys)
        baseline = [('web/admin/probe/probe.py', PROBE_MESSAGE)]
        problems, new_cnt, stale = self.vi._web_backend_ratchet_problems(misses, baseline)
        self.assertEqual(problems, [])
        self.assertEqual((new_cnt, stale), (0, 0))

    def test_12_docstring_example_is_not_reported(self):
        """docstring 里的用法示例不是运行时消息，不得误报（否则门禁天天红）。"""
        d = os.path.join(self.tmp, 'web', 'core')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'doc.py'), 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('"""说明：\n\n'
                     "    return yf.returnData(False, '文档示例消息')\n"
                     '"""\n')
        misses = self.vi.web_backend_msg_misses(root=self.tmp,
                                               keys=self.vi._load_web_keys())
        self.assertEqual(misses, [], 'docstring 示例被误报：%r' % (misses,))


class TestWorkflowTriggerPaths(unittest.TestCase):
    """3) 触发路径：push 与 pull_request 都必须含 `web/**/*.py`。"""

    def test_20_both_events_include_web_backend_py(self):
        paths, how = workflow_paths()
        self.assertTrue(paths, 'i18n-check.yml 解析不出任何带 paths 的触发事件（%s）' % how)
        for event in ('push', 'pull_request'):
            self.assertIn(event, paths, 'i18n-check.yml 缺 %s 触发' % event)
            self.assertIn('web/**/*.py', paths[event],
                          '%s 的 paths 不含 web/**/*.py —— 改 web 后端不会触发 i18n 检查'
                          '（实际：%r）' % (event, paths[event]))

    def test_21_no_overbroad_web_glob(self):
        """只许精确的 `web/**/*.py`，不许顺手放成 `web/**`（会把前端资源也拉进来）。"""
        paths, _how = workflow_paths()
        for event in ('push', 'pull_request'):
            for pattern in paths.get(event, []):
                self.assertNotIn(pattern, ('web/**', 'web/*', '**', '*'),
                                 '%s 的 paths 里出现了过宽模式 %r（噪音）' % (event, pattern))

    def test_22_parsers_agree(self):
        """PyYAML 与最小解析必须在「是否含 web/**/*.py」上给出同一结论。"""
        text = _read(WORKFLOW)
        fallback = _parse_paths_fallback(text)
        for event in ('push', 'pull_request'):
            self.assertIn('web/**/*.py', fallback.get(event, []),
                          '最小解析器在 %s 上看不出 web/**/*.py（解析器腐烂？）' % event)


class TestBakCleanup(unittest.TestCase):
    """4) 产品内 `*.i18n.bak` 清零，且 `test/` 下的夹具一个都不许少。"""

    def _product_bak_files(self):
        hits = []
        for top in ('plugins', 'web', 'scripts'):
            base = os.path.join(ROOT, top)
            if not os.path.isdir(base):
                continue
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames
                               if d not in ('node_modules', '__pycache__', '.git')]
                for fn in filenames:
                    if fn.endswith('.i18n.bak'):
                        hits.append(os.path.relpath(os.path.join(dirpath, fn), ROOT))
        return hits

    def test_30_no_product_i18n_bak(self):
        hits = self._product_bak_files()
        self.assertEqual(hits, [], '产品目录里还有 *.i18n.bak（P2-14 已清理，禁止回潮）：%r'
                                   % hits[:10])

    def test_31_test_fixtures_still_present(self):
        """防误删：i18n 审计夹具目录下的 31 个 `.i18n.bak` 是对照基线。"""
        fixture_dir = _find_fixture_dir()
        if fixture_dir is None:
            self.skipTest('%s 不存在（干净克隆/CI 正常现象）' % FIXTURE_DIRNAME)
        n = 0
        for dirpath, _dirnames, filenames in os.walk(fixture_dir):
            n += sum(1 for fn in filenames if fn.endswith('.i18n.bak'))
        self.assertGreaterEqual(n, 30, 'i18n 审计夹具被删了（应为 ≥30，实测 %d）' % n)

    def test_32_repo_scope_has_no_other_bak_regression(self):
        """全仓（排除 node_modules/test/tmp）不得再出现 `.i18n.bak`。"""
        hits = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames
                           if d not in ('node_modules', 'test', 'tmp', '.git',
                                        '__pycache__', 'logs')]
            for fn in filenames:
                if fn.endswith('.i18n.bak'):
                    hits.append(os.path.relpath(os.path.join(dirpath, fn), ROOT))
        self.assertEqual(hits, [], '全仓仍有 *.i18n.bak：%r' % hits[:10])


class TestEmptyValueKeys(unittest.TestCase):
    """5) 空值键清零（例外必须在 `EMPTY_VALUE_EXCEPTIONS` 里写明理由）。"""

    def test_40_empty_value_check_is_green(self):
        vi = _load_verify()
        problems = vi.check_empty_values(None)
        self.assertEqual(problems, [], '存在空值键（补译或删键，确需保留请进例外表）：\n  '
                                       + '\n  '.join(problems[:10]))

    def test_41_exceptions_are_documented(self):
        vi = _load_verify()
        for key, why in vi.EMPTY_VALUE_EXCEPTIONS.items():
            self.assertGreater(len(why.strip()), 12,
                               '空值例外 %r 没写清理由（要能让人判断能不能删）' % (key,))

    def test_42_markup_only_rule_selfproof(self):
        """判据自证：纯标记/注释源 → 派生必然为空；有文本的源 → 必须报。"""
        vi = _load_verify()
        self.assertTrue(vi._is_pure_markup('<!-- 系统配置 -->'))
        self.assertTrue(vi._is_pure_markup('</ul>'))
        self.assertFalse(vi._is_pure_markup('个'))
        self.assertFalse(vi._is_pure_markup(''))
        self.assertFalse(vi._is_pure_markup(' '))


class TestBaselineNotWidened(unittest.TestCase):
    """6) 基线不可悄悄放宽：文件、常量、实测三方必须互相对得上。"""

    def test_50_baseline_path_constant(self):
        vi = _load_verify()
        self.assertEqual(vi.WEB_BACKEND_BASELINE_REL, BASELINE_REL,
                         '基线路径常量与用例常量不一致')
        self.assertEqual(os.path.normcase(vi.WEB_BACKEND_BASELINE),
                         os.path.normcase(BASELINE))
        self.assertTrue(os.path.isfile(BASELINE), '缺少棘轮基线文件 %s' % BASELINE_REL)

    def test_51_baseline_count_matches_case_constant(self):
        vi = _load_verify()
        baseline = vi.load_web_backend_baseline()
        self.assertEqual(len(baseline), BASELINE_ENTRIES,
                         '基线条数(%d)与用例常量(%d)不一致：放宽基线必须先改这里并说明理由'
                         % (len(baseline), BASELINE_ENTRIES))

    def test_52_baseline_equals_live_misses(self):
        """**双向校验**：基线内容必须恰好等于当前实测（多集相等）。

        少一条 = 门禁会报「新增」；多一条 = 门禁会报「基线过期」。两个方向都红，
        所以既不能只改基线（放宽），也不能只改代码（不精删基线）。
        """
        vi = _load_verify()
        baseline = sorted((rel, lit) for rel, lit in vi.load_web_backend_baseline())
        live = sorted((rel, lit.strip()) for rel, _ln, lit in vi.web_backend_msg_misses())
        self.assertEqual(len(baseline), len(live),
                         '基线条数(%d)与实测条数(%d)不一致' % (len(baseline), len(live)))
        self.assertEqual(baseline, live,
                         '基线内容与实测不一致（改名/改写/新增/修好都会命中）：\n'
                         '仅基线有：%r\n仅实测有：%r'
                         % ([x for x in baseline if x not in live][:5],
                            [x for x in live if x not in baseline][:5]))

    def test_53_baseline_entries_point_into_web(self):
        vi = _load_verify()
        for rel, lit in vi.load_web_backend_baseline():
            self.assertTrue(rel.startswith('web/'), '基线条目不在 web/ 下：%r' % rel)
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)),
                            '基线指向不存在的文件：%r（删文件后必须精删基线）' % rel)
            self.assertTrue(lit.strip(), '基线里有空消息行：%r' % rel)
            self.assertNotIn('\t\t', lit)

    def test_54_baseline_header_states_ratchet(self):
        """基线文件的头注释必须说明「只减不增」，否则后来人看不懂就会随手乘大。"""
        text = _read(BASELINE)
        self.assertIn('棘轮', text)
        self.assertIn('--write-web-backend-baseline', text)
        for line in text.splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            self.assertIn('\t', line, '基线行必须是「路径<TAB>消息」：%r' % line)


if __name__ == '__main__':
    unittest.main()
