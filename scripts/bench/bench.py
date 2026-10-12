#!/usr/bin/env python3
# coding: utf-8
# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）性能基准脚本
# ---------------------------------------------------------------------------------
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
"""可复现的性能基准：把 README 里「作者自测、环境相关」的性能数字变成可跑的命令。

    python scripts/bench/bench.py --case cpu_info
    python scripts/bench/bench.py --case plugins_list
    python scripts/bench/bench.py --case run_batch
    python scripts/bench/bench.py --case all
    python scripts/bench/bench.py --quick --case all
    python scripts/bench/bench.py --case plugins_list --json /tmp/bench.json

设计约束（改动前请先读懂）：

1. **只依赖标准库**。业务模块（`web/...`）一律在 case 内部用
   `importlib.import_module` 动态加载，本文件里不出现任何非标准库的 `import`
   语句 —— `testsuite/test_bench_scripts_hardening.py` 会用 AST 扫描强制这一点。
2. **缺依赖就跳过，不崩**。任何 case 在 import 阶段抛 `ImportError`
   （如开发机上没有 psutil / flask）都会变成 `status=skipped` + 明确的
   `skip_reason`，退出码用约定的 `EXIT_SKIPPED(3)`，而不是堆栈回溯。
3. **不修改业务代码**。bench 只调用现有函数 / 路由逻辑，测的是它们本来的行为。
"""
import argparse
import datetime
import importlib
import importlib.util
import json
import math
import os
import platform
import statistics
import sys
import time

# Windows 中文控制台默认 GBK，直接 print 中文会乱码 / 抛 UnicodeEncodeError。
# 统一把 stdout/stderr 钉成 UTF-8（与 testsuite/run_all.py 同口径）。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
WEB_DIR = os.path.join(ROOT, 'web')
RESULTS_DIR = os.path.join(HERE, 'results')

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_SKIPPED = 3

DEFAULT_SAMPLES = 20
QUICK_SAMPLES = 3

# README 里出现的 case 名必须与这里完全一致（守卫测试会交叉核对）。
CASES = ('cpu_info', 'plugins_list', 'run_batch')

# run_batch 基准默认批量调用的插件（func=status，只读、不改变系统状态）。
# 即使插件未安装，`plugin.run()` 也会快速返回错误串，仍然覆盖并行调度路径。
RUN_BATCH_PLUGINS = ('php-apt', 'clean', 'swap', 'webstats', 'pureftp', 'supervisor')


class SkipCase(Exception):
    """环境不满足（缺依赖 / 缺运行条件），该 case 跳过。"""


def _ensure_web_path():
    """把 web/ 与仓库根插入 sys.path，使 `core.yf` / `utils.*` / `admin.*` 可导入。"""
    for path in (WEB_DIR, ROOT):
        if path not in sys.path:
            sys.path.insert(0, path)


def _load(name):
    """动态加载业务模块（非标准库 import 语句不出现在本文件里）。"""
    _ensure_web_path()
    return importlib.import_module(name)


def collect_env():
    """采集环境信息，供「环境相关」免责与跨机对比使用。"""
    env = {
        'python': sys.version.split()[0],
        'python_full': sys.version.replace('\n', ' '),
        'python_executable': sys.executable,
        'os': platform.system(),
        'platform': platform.platform(),
        'machine': platform.machine(),
        'processor': platform.processor() or None,
        'cpu_count_logical': os.cpu_count(),
        'cpu_count_physical': None,
    }
    # psutil 可选：装了才补物理核数，没装不影响其它 case。
    try:
        psutil = importlib.import_module('psutil')
        env['cpu_count_physical'] = psutil.cpu_count(logical=False)
    except Exception:
        pass
    return env


def percentile(sorted_values, pct):
    """线性插值分位数（与 numpy.percentile 默认口径一致，避免引入 numpy）。"""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return sorted_values[int(k)]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


# --------------------------------------------------------------------------
# case 实现：每个 `_case_<name>_once()` 只做一次采样（返回耗时毫秒由外层统一计）。
# --------------------------------------------------------------------------
def _case_cpu_info_once():
    """测 `web/utils/system/main.py::getCpuInfo(interval=None)` 的非阻塞返回。"""
    main = _load('utils.system.main')
    main.getCpuInfo(interval=None)


def _case_plugins_list_once():
    """测 `/plugins/list` 的后端聚合路径（`utils.plugin.plugin.getList`）。"""
    up = _load('utils.plugin')
    pg = up.plugin.instance()
    pg.getList('0', '', 1, 10, 0)


def _case_run_batch_once():
    """测 `/plugins/run_batch` 的并行执行路径（`admin.plugins.run_batch`）。

    `run_batch` 是 Flask 视图，需要请求上下文才能取 `request.form`。这里用
    `app.test_request_context` 造一个最小上下文，并走 `__wrapped__` 绕过登录装饰器
    （`panel_login_required` 用 `functools.wraps` 包了原函数）。缺 flask 即跳过。
    """
    if importlib.util.find_spec('flask') is None:
        raise SkipCase('flask 未安装：无法构造请求上下文调用 run_batch 视图')
    admin_plugins = _load('admin.plugins')
    flask = importlib.import_module('flask')
    tasks = [{'name': name, 'func': 'status', 'version': '', 'args': '', 'script': 'index'}
             for name in RUN_BATCH_PLUGINS]
    payload = json.dumps(tasks)
    app = flask.Flask('bench')
    with app.test_request_context('/plugins/run_batch', method='POST',
                                  data={'list': payload}):
        admin_plugins.run_batch.__wrapped__()


_CASE_FUNCS = {
    'cpu_info': _case_cpu_info_once,
    'plugins_list': _case_plugins_list_once,
    'run_batch': _case_run_batch_once,
}


def _skipped(case, reason):
    return {'case': case, 'status': 'skipped', 'samples': 0, 'samples_ms': [],
            'median': None, 'p95': None, 'mean': None, 'min': None, 'max': None,
            'unit': 'ms', 'skip_reason': reason}


def run_case(case, samples):
    """跑一个 case：预热 1 次 + 采样 N 次，返回结果字典。

    缺依赖 / 采样期间报错都返回 `status=skipped` + 明确原因，不抛异常（“不崩”）。
    """
    func = _CASE_FUNCS[case]
    # 预热：把首次导入 / 首次调用的固定开销排除在采样之外。
    try:
        func()
    except SkipCase as exc:
        return _skipped(case, str(exc))
    except ImportError as exc:
        return _skipped(case, '导入业务模块失败：%s' % exc)
    except Exception as exc:
        return _skipped(case, '预热失败：%s' % exc)

    samples_ms = []
    try:
        for _ in range(samples):
            start = time.perf_counter()
            func()
            samples_ms.append(round((time.perf_counter() - start) * 1000.0, 4))
    except Exception as exc:
        return _skipped(case, '采样失败：%s' % exc)

    ordered = sorted(samples_ms)
    return {
        'case': case,
        'status': 'ok',
        'samples': len(samples_ms),
        'samples_ms': samples_ms,
        'median': round(statistics.median(samples_ms), 4),
        'p95': round(percentile(ordered, 95), 4),
        'mean': round(statistics.fmean(samples_ms), 4),
        'min': min(samples_ms),
        'max': max(samples_ms),
        'unit': 'ms',
        'skip_reason': None,
    }


def build_report(case, samples, quick):
    return {
        'tool': 'scripts/bench/bench.py',
        'schema': 1,
        'timestamp': datetime.datetime.now().astimezone().isoformat(),
        'quick': quick,
        'case_arg': case,
        'requested_samples': samples,
        'env': collect_env(),
        'results': [run_case(c, samples) for c in resolve_cases(case)],
    }


def resolve_cases(case):
    if case == 'all':
        return list(CASES)
    return [case]


def print_report(report):
    print('=' * 72)
    print('御风面板性能基准  %s' % report['timestamp'])
    env = report['env']
    print('环境: Python %s | OS %s | 逻辑核 %s | %s'
          % (env['python'], env['os'], env['cpu_count_logical'], env['platform']))
    print('-' * 72)
    for result in report['results']:
        if result['status'] != 'ok':
            print('%-14s SKIP   %s' % (result['case'], result['skip_reason']))
            continue
        print('%-14s median=%-9s p95=%-9s mean=%-9s min=%-9s max=%-9s (%d 次, %s)'
              % (result['case'], result['median'], result['p95'], result['mean'],
                 result['min'], result['max'], result['samples'], result['unit']))
    print('=' * 72)


def default_json_path():
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join(RESULTS_DIR, 'bench_%s.json' % stamp)


def write_report(report, path):
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write('\n')


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog='bench.py',
        description='御风面板性能基准（仅标准库；缺依赖的 case 会跳过并说明原因）')
    parser.add_argument('--case', default='all',
                        help='要跑的 case：%s 或 all（默认 all）' % ' | '.join(CASES))
    parser.add_argument('--samples', type=int, default=None,
                        help='采样次数（默认 %d；--quick 时为 %d）'
                             % (DEFAULT_SAMPLES, QUICK_SAMPLES))
    parser.add_argument('--quick', action='store_true',
                        help='少量采样（%d 次），供测试 / CI 用' % QUICK_SAMPLES)
    parser.add_argument('--json', dest='json_path', default=None,
                        help='结果 JSON 输出路径（默认写到 scripts/bench/results/）')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)

    cases = resolve_cases(args.case)
    for case in cases:
        if case not in CASES:
            print('未知 case：%s（可选：%s 或 all）' % (case, ' | '.join(CASES)),
                  file=sys.stderr)
            return EXIT_ERROR

    if args.samples is not None:
        samples = args.samples
    else:
        samples = QUICK_SAMPLES if args.quick else DEFAULT_SAMPLES
    if samples < 1:
        print('--samples 必须 >= 1', file=sys.stderr)
        return EXIT_ERROR

    report = build_report(args.case, samples, args.quick)
    print_report(report)

    json_path = args.json_path or default_json_path()
    try:
        write_report(report, json_path)
    except OSError as exc:
        print('写 JSON 失败：%s' % exc, file=sys.stderr)
        return EXIT_ERROR
    print('结果 JSON: %s' % json_path)

    if any(r['status'] == 'ok' for r in report['results']):
        return EXIT_OK
    return EXIT_SKIPPED


if __name__ == '__main__':
    sys.exit(main())
