# coding: utf-8
"""`scripts/bench` 性能基准脚本的守卫。

背景：README 里的性能数字此前只有一句「作者自测、环境相关」，没有任何可复现的基准
（报告 P1 第三部分 6.1/6.3/6.4 与附录 A）。P1-8 在 README 里补了指向
`scripts/bench/README.md` 的引用，本守卫负责守住那套基准**真的存在、真的能跑、
README 里的命令与脚本支持的 case 一致、脚本保持零第三方依赖**。

断言都用「行为 + 结构」两种口径，注释 / `if False:` 蒙混写法抓不到：

* 文件存在 + `py_compile` 通过；
* `--help` 退出码为 0；
* `--quick` 真跑一个最轻的 case，校验输出 JSON 的必需字段；
* README 里的 `--case <名字>` 与脚本 `CASES` 双向一致；
* AST 扫描脚本的所有 import，只允许标准库。
"""
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH_DIR = os.path.join(ROOT, 'scripts', 'bench')
BENCH_PY = os.path.join(BENCH_DIR, 'bench.py')
BENCH_README = os.path.join(BENCH_DIR, 'README.md')

# 跑 case 时退出码 3 = 依赖缺失、全部跳过（脚本约定，见 scripts/bench/README.md）。
EXIT_SKIPPED = 3
# 最轻、且只需标准库的 case 兜底：cpu_info 需要 psutil，缺了就退到它。
FALLBACK_CASE = 'plugins_list'


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _child_env():
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


def _run_bench(args):
    return subprocess.run([sys.executable, BENCH_PY] + list(args),
                          cwd=ROOT, capture_output=True, env=_child_env())


def _load_bench_module():
    spec = importlib.util.spec_from_file_location('yf_bench_guard', BENCH_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestBenchScriptsHardening(unittest.TestCase):

    def test_01_bench_files_exist_and_compile(self):
        self.assertTrue(os.path.isfile(BENCH_PY), 'scripts/bench/bench.py 不存在')
        self.assertTrue(os.path.isfile(BENCH_README), 'scripts/bench/README.md 不存在')
        proc = subprocess.run([sys.executable, '-m', 'py_compile', BENCH_PY],
                              cwd=ROOT, capture_output=True, env=_child_env())
        self.assertEqual(proc.returncode, 0,
                         'py_compile 失败：%s' % proc.stderr.decode('utf-8', 'replace'))

    def test_02_help_returns_zero(self):
        proc = _run_bench(['--help'])
        self.assertEqual(proc.returncode, 0,
                         '--help 退出码非 0：%s' % proc.stderr.decode('utf-8', 'replace'))
        out = proc.stdout.decode('utf-8', 'replace')
        self.assertIn('--case', out)
        self.assertIn('--quick', out)

    def test_03_quick_run_emits_required_json_fields(self):
        tmpdir = tempfile.mkdtemp(prefix='yf_bench_guard_')
        out_json = os.path.join(tmpdir, 'bench.json')

        proc = _run_bench(['--quick', '--case', 'cpu_info', '--json', out_json])
        if proc.returncode == EXIT_SKIPPED:
            # cpu_info 需要 psutil，开发机 / 轻量 CI 上没有 → 退到最轻的标准库 case。
            proc = _run_bench(['--quick', '--case', FALLBACK_CASE, '--json', out_json])

        self.assertEqual(
            proc.returncode, 0,
            '--quick 跑 case 失败（rc=%s）：%s' % (proc.returncode,
                                                  proc.stderr.decode('utf-8', 'replace')))
        self.assertTrue(os.path.isfile(out_json), '未写出 JSON：%s' % out_json)

        with open(out_json, encoding='utf-8') as fh:
            data = json.load(fh)

        # 顶层必需字段
        self.assertTrue(data.get('timestamp'), 'JSON 缺 timestamp')
        self.assertTrue(data.get('env'), 'JSON 缺 env')
        env = data['env']
        for key in ('python', 'os', 'platform', 'cpu_count_logical'):
            self.assertIn(key, env, 'env 缺字段 %s' % key)

        # result 必需字段
        ok_results = [r for r in data.get('results', []) if r.get('status') == 'ok']
        self.assertTrue(ok_results, '没有成功的 case 结果：%s' % data.get('results'))
        result = ok_results[0]
        self.assertTrue(result.get('case'), 'result 缺 case')
        self.assertIsNotNone(result.get('median'), 'result 缺 median')
        self.assertIsNotNone(result.get('p95'), 'result 缺 p95')
        self.assertGreaterEqual(result.get('samples', 0), 1, 'result 缺 samples')

    def test_04_readme_commands_match_supported_cases(self):
        bench = _load_bench_module()
        supported = set(bench.CASES)
        readme = _read(BENCH_README)
        named = set(re.findall(r'--case\s+([A-Za-z_][A-Za-z0-9_]*)', readme))
        # README 里出现的 case 名（除 all 外）必须都是脚本支持的
        unknown = named - supported - {'all'}
        self.assertFalse(unknown, 'README 引用了脚本不支持的 case：%s' % sorted(unknown))
        # 每个支持的 case 都要在 README 里有对应命令
        missing = supported - named
        self.assertFalse(missing, 'README 未给出这些 case 的运行命令：%s' % sorted(missing))
        # README 至少要给出 all 的组合命令
        self.assertIn('all', named, 'README 未给出 --case all 的组合命令')

    def test_05_script_imports_only_stdlib(self):
        tree = ast.parse(_read(BENCH_PY))
        allowed = set(sys.stdlib_module_names)
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split('.')[0]
                    if root not in allowed:
                        offenders.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # 相对导入：内部模块，放行
                    continue
                root = (node.module or '').split('.')[0]
                if root and root not in allowed:
                    offenders.append(node.module)
        self.assertFalse(offenders, 'bench.py 引入了非标准库 import：%s' % offenders)


if __name__ == '__main__':
    unittest.main(verbosity=2)
