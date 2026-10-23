# coding: utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 作者: midoks & yufeng tec
# ---------------------------------------------------------------------------------
# 代码质量棘轮门禁
# ---------------------------------------------------------------------------------
"""
统计四类「静默失败 / 不可诊断 / 命令注入」的写法，并做**棘轮**约束：只减不增。

为什么是棘轮而不是「一把清零」：
    本仓现存 170+ 处裸 `except:`、近 200 处 `except Exception: pass`、几十处 `print`。
    一次性全改会把改动面铺到几十个模块、几十个插件上，回归风险远大于收益，
    而且其中一部分（如插件脚本的 print）是**合理**的。
    棘轮的价值是「阻止继续恶化」+ 给出可量化的下降目标，
    每轮顺手清一批、把基线调低即可，永远不会反弹。

扫描范围（两段，各自一套基线）：
    正式段  SCAN_DIRS = ['web', 'plugins'] + SCAN_ROOT_PY
    待审核段 PENDING_SCAN_DIR = '文档/待审核插件'

    为什么待审核段单独成常量、指标单独记 `pending_*`（P2-11）：
        `文档/待审核插件/` 里放着 34 个还没转正的插件。它们**当前不可达**
        （`web/utils/plugin.py` 的插件列表把 `待审核` 显式排除），但「转正」
        就是把这些文件搬进 `plugins/`，一搬就直接进生产 —— 所以它们必须在
        同一道棘轮之下，否则转正那一刻才第一次被扫，等于没扫。
        但又不许把它们混进 SCAN_DIRS：①SCAN_DIRS 的语义是「已发布的正式代码」，
        转正前它们不是；②正式段已经清零的指标（bare/silent/print 全 0）一旦
        混入待审核目录的存量（本轮只纳入扫描、不修插件代码），会立刻把整套
        门禁打红，而「清零」这个既有成果也就再也不可读了。
        于是：**同一套检测器、同一套判据、分开的基线**，各自只减不增。
        待审核段的 print 口径与正式插件一致（`print_in_web` 只统计 `web/`，
        插件代码要打印就走 `yf.writeFileLog`/`logging`），所以 `pending_print_in_web`
        基准恒为 0 —— 这不是豁免，而是与正式插件**同一条**尺子。

三个指标：
    bare_except           裸 `except:` —— 会吞掉 KeyboardInterrupt / SystemExit
    silent_except         `except Exception:` 紧接 `pass` —— 静默失败，线上无法诊断
    print_in_web          `web/` 下的 `print(` —— 生产代码应走 logging
    os_system_count       `os.system(...)` —— 字符串拼接进 shell，命令注入风险
    writefile_bare_success 裸 `yf.writeFile(...)` 后 6 行内直接 `returnJson(True)`

    writefile_bare_success 是什么：
        `yf.writeFile` 默认「失败只返回 False，永不抛异常」，所以凭返回值不看的
        裸调用写完就 `returnJson(True)`，等于「写盘失败 = 界面显示成功」。
        判据（ast 级）：调用是裸表达式语句（结果被丢弃）+ 未传必须抛异常的
        `must=True` + 其后 6 行内出现 `returnJson(True, ...)`。
        正确的写法天然不计入：`if not yf.writeFile(...)` / `bool(yf.writeFile(...))` /
        `yf.writeFile(..., must=True)`。
        基线 = 2026 P1-7 整改后的实测值，只减不增（每改一处就把基线调低）。

    为什么 os_system_count 不是 0：
        剩下 3 处是「必须经 shell 才能完成」的**纯字面量**调用（多级管道杀进程 / 进程替换 curl /
        管道 bench.sh），已确认**无变量进入 shell**（bandit 亦判为 LOW）。它们如实计入基线
        （=3）而不是用豁免标记抹掉，这样数字真实反映存量，日后任何新增 os.system 都会直接变红。
        原先还有 2 处 `cd && source bin/activate && python ...`（拼接了面板目录常量），
        已改为 `yf.safeExecShell([...], cwd=...)` + 直接调 venv 解释器，基线 5 → 3。

print 的两类**豁免**（必须是真·CLI 输出，不是偷懒）：
    1. 位于 `if __name__ == '__main__':` 块内（直接跑脚本的入口，输出就该走 stdout）；
    2. 行内带 `# print-ok: 理由` 标记（如 `panel_tools.py` 依赖的 terminal 输出）。
    其余一律用 `yf.writeFileLog(...)` / `logging`，让面板进程的诊断信息有处可查。

用法：
    python scripts/verify_code_quality.py              # 校验（超出基线即失败）
    python scripts/verify_code_quality.py --verbose    # 列出具体位置
    python scripts/verify_code_quality.py --update     # 把当前值写成新基线（只允许下降）
    python scripts/verify_code_quality.py --self-test  # 检测器自证（夹具断言）
    python scripts/verify_code_quality.py --allow-increase --update   # 明确允许上调（需理由）
"""

import argparse
import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_FILE = os.path.join(ROOT, 'scripts', 'code_quality_baseline.json')

# 扫描范围：业务代码 + 插件。刻意排除测试、参考料与依赖目录
SCAN_DIRS = ['web', 'plugins']
SCAN_ROOT_PY = ['panel_task.py', 'panel_tools.py']
EXCLUDE_DIRS = {'__pycache__', 'node_modules', 'test', 'testsuite', '参考', '文档',
                'cl_tasks', '.git', 'data', 'logs', 'tmp', '.workbuddy-ai'}

#: 待审核插件目录（P2-11）：转正即进生产，必须与正式插件同一套棘轮。
#: 单独成常量而不是塞进 SCAN_DIRS —— 见文件头「扫描范围」一节的说明。
PENDING_SCAN_DIR = '文档/待审核插件'

RE_BARE_EXCEPT = re.compile(r'^\s*except\s*:\s*(#.*)?$')
RE_EXCEPT = re.compile(r'^\s*except\b')
RE_PRINT = re.compile(r'(?<![\w.])print\s*\(')
RE_OS_SYSTEM = re.compile(r'(?<![\w.])os\.system\s*\(')
METRICS = ('bare_except', 'silent_except', 'print_in_web', 'os_system_count',
           'writefile_bare_success')
#: 待审核段的指标族：与正式段一一对应，只是键名加 `pending_` 前缀、单列基线。
PENDING_METRICS = tuple('pending_' + m for m in METRICS)
ALL_METRICS = METRICS + PENDING_METRICS

#: 裸 writeFile 之后「写后直接报成功」的判定窗口（行）
WRITEFILE_SUCCESS_WINDOW = 6


def _iter_py_files():
    for base in SCAN_DIRS:
        abs_base = os.path.join(ROOT, base)
        if not os.path.isdir(abs_base):
            continue
        for root, dirs, files in os.walk(abs_base):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fn in files:
                if fn.endswith('.py'):
                    yield os.path.join(root, fn)
    for fn in SCAN_ROOT_PY:
        path = os.path.join(ROOT, fn)
        if os.path.isfile(path):
            yield path


def _iter_pending_py_files():
    """待审核插件目录下的 `*.py`（P2-11 纳入扫描范围）。

    刻意与 `_iter_py_files()` **分开**：那个函数是「正式代码」的单一入口，
    被 `testsuite/test_writefile_must_and_ratchet.py` 的棘轮直接复用，
    混入待审核目录会让正式基线与待审核存量互相污染。
    """
    abs_base = os.path.join(ROOT, PENDING_SCAN_DIR.replace('/', os.sep))
    if not os.path.isdir(abs_base):
        return
    for root, dirs, files in os.walk(abs_base):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fn in files:
            if fn.endswith('.py'):
                yield os.path.join(root, fn)


def _rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, '/')


def _is_main_guard(test):
    """判断 `if __name__ == '__main__':` 的条件表达式。"""
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq) and len(test.comparators) == 1):
        return False

    def literal(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Constant):
            return node.value
        return None

    return {literal(test.left), literal(test.comparators[0])} == {'__name__', '__main__'}


def _collect_web_prints(tree, lines):
    """收集需要整改的 `print(`：排除 CLI 入口块与带 `# print-ok` 标记的行。"""
    out = []

    def visit(node, in_main):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'print'):
            if not in_main:
                src = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ''
                if 'print-ok' not in src:
                    out.append((node.lineno, src.strip()))
        for child in ast.iter_child_nodes(node):
            child_main = in_main
            if isinstance(child, ast.If) and _is_main_guard(child.test):
                child_main = True
            visit(child, child_main)

    visit(tree, False)
    out.sort()
    return out


def _collect_writefile_bare_success(tree):
    """收集「裸 yf.writeFile(...) 之后 6 行内直接 returnJson(True)」的位置。

    只认裸表达式语句：只要调用结果被用到（`if not ...` / 赋值 / `bool(...)`），
    或者显式传了 `must=True`（写失败会抛），都不算 —— 那些写法失败时
    会如实回失败，不再是「写盘失败 = 界面显示成功」。
    """

    def _is_writefile_call(node):
        if not isinstance(node, ast.Call):
            return False
        f = node.func
        return (isinstance(f, ast.Attribute) and f.attr == 'writeFile'
                and isinstance(f.value, ast.Name) and f.value.id == 'yf')

    def _is_returnjson_true(node):
        if not isinstance(node, ast.Call):
            return False
        f = node.func
        if not (isinstance(f, ast.Attribute) and f.attr == 'returnJson'):
            return False
        return bool(node.args) and isinstance(node.args[0], ast.Constant) \
            and node.args[0].value is True

    success_lines = sorted(
        n.lineno for n in ast.walk(tree)
        if _is_returnjson_true(n))

    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        call = node.value
        if not _is_writefile_call(call):
            continue
        if any(kw.arg == 'must' for kw in call.keywords):
            continue   # must=True：写失败会抛异常，不算静默
        base = getattr(call, 'end_lineno', None) or call.lineno
        for line in success_lines:
            if 0 < line - base <= WRITEFILE_SUCCESS_WINDOW:
                out.append((node.lineno,
                            'yf.writeFile(...) 后 %d 行内直接 returnJson(True)，未校验写盘结果'
                            % (line - base)))
                break
    out.sort()
    return out


def scan_text(text, path, in_web):
    """扫描单份源码，返回 {metric: [(行号, 片段)]}。

    用 `ast` 而不是正则：正则无法区分「真的裸 except」与「字符串/注释里的 except」，
    也数不准字符串里的 `print(`。这类计数器一旦误报，就会被人当成噪音忽略，
    整道门禁也就废了。只有语法解析失败时才退回正则。
    """
    found = {m: [] for m in METRICS}
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _scan_text_regex(text, in_web)

    lines = text.split('\n')

    def snippet(lineno):
        return lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ''

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                found['bare_except'].append((node.lineno, snippet(node.lineno)))
            elif len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                found['silent_except'].append((node.lineno, snippet(node.lineno)))
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == 'system'
              and isinstance(node.func.value, ast.Name) and node.func.value.id == 'os'):
            found['os_system_count'].append((node.lineno, snippet(node.lineno)))

    if in_web:
        found['print_in_web'] = _collect_web_prints(tree, lines)

    found['writefile_bare_success'] = _collect_writefile_bare_success(tree)

    for metric in found:
        found[metric].sort()
    return found


def _scan_text_regex(text, in_web):
    """语法解析失败时的降级扫描（会误报字符串内容，仅作兑底）。"""
    found = {m: [] for m in METRICS}
    lines = text.split('\n')
    for idx, line in enumerate(lines, 1):
        if RE_BARE_EXCEPT.match(line):
            found['bare_except'].append((idx, line.strip()))
            continue
        if RE_EXCEPT.match(line):
            for j in range(idx, min(idx + 4, len(lines))):
                nxt = lines[j].strip()
                if not nxt or nxt.startswith('#'):
                    continue
                if nxt == 'pass':
                    found['silent_except'].append((idx, line.strip()))
                break
        if in_web and RE_PRINT.search(line) and 'print-ok' not in line:
            found['print_in_web'].append((idx, line.strip()))
        if RE_OS_SYSTEM.search(line) and not line.strip().startswith('#'):
            found['os_system_count'].append((idx, line.strip()))
    return found


def _scan_files(paths, metrics, result, in_web_of=None):
    """把一批文件扫进 `result`，键名前缀由 `metrics` 决定（正式段 / 待审核段共用）。"""
    for path in paths:
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                text = fh.read().replace('\r\n', '\n')
        except OSError:
            continue
        in_web = in_web_of(path) if in_web_of else _rel(path).startswith('web/')
        hits_by_metric = scan_text(text, path, in_web)
        for metric, key in metrics.items():
            for line_no, snippet in hits_by_metric[metric]:
                result[key].append((_rel(path), line_no, snippet))


def run_scan():
    """两段扫描：正式代码 → `METRICS`，待审核插件 → `PENDING_METRICS`。"""
    result = {m: [] for m in ALL_METRICS}
    _scan_files(_iter_py_files(), dict(zip(METRICS, METRICS)), result)
    # 待审核段与正式插件同口径：`in_web=False`（`print_in_web` 只针对 web/ 生产代码）
    _scan_files(_iter_pending_py_files(),
                dict(zip(METRICS, PENDING_METRICS)), result,
                in_web_of=lambda path: False)
    return result


def load_baseline():
    if not os.path.isfile(BASELINE_FILE):
        return {}
    with open(BASELINE_FILE, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def counts_of(result):
    return {m: len(result[m]) for m in ALL_METRICS}


def self_test():
    """检测器自证：用夹具确认四类都能被识别，且合法写法不被误报。"""
    fixture = (
        "def a():\n"
        "    try:\n"
        "        pass\n"
        "    except:\n"          # 1 裸 except
        "        pass\n"
        "    try:\n"
        "        pass\n"
        "    except Exception:\n"  # 1 静默 except
        "        pass\n"
        "    print('debug')\n"     # 1 print
        "    try:\n"
        "        pass\n"
        "    except ValueError as e:\n"   # 不算静默（有日志）
        "        logging.warning(e)\n"
        "    if __name__ == '__main__':\n"
        "        print('cli')\n"          # 豁免：CLI 入口
        "    print('x')  # print-ok: 夹具\n"  # 豁免：显式标记
        "    d = {'except': 1}\n"          # 字符串里的 except 不得误报
        "    x = 'print('\n"               # 字符串里的 print 不得误报
        "    os.system('ls ' + a)\n"       # 1 处 os.system
        "    os.system('id')\n"           # 1 处 os.system
        "    # os.system('x')\n"          # 注释行不计
        "    yf.writeFile(p, 'x')\n"     # 1 处裸写盘+报成功
        "    return yf.returnJson(True, 'ok')\n"
        "    if not yf.writeFile(p, 'x'):\n"       # 校验过，不计
        "        return yf.returnJson(False, 'fail')\n"
        "    yf.writeFile(p, 'x', must=True)\n"    # must=True，不计
        "    return yf.returnJson(True, 'ok')\n"
        "    yf.writeFile(p, 'x')\n"     # 隔了 >6 行，不计
        "    a1 = 1\n    a2 = 2\n    a3 = 3\n    a4 = 4\n    a5 = 5\n    a6 = 6\n"
        "    return yf.returnJson(True, 'ok')\n"
        "    return d, x\n"
    )
    got = scan_text(fixture, '<fixture>', in_web=True)
    counts = {m: len(got[m]) for m in METRICS}
    expected = {'bare_except': 1, 'silent_except': 1, 'print_in_web': 1,
                'os_system_count': 2, 'writefile_bare_success': 1}
    if counts != expected:
        print('[FAIL] 自证失败：期望 %r，实际 %r' % (expected, counts))
        return 1
    print('[OK] 检测器自证通过（五类均命中，合法写法零误报，两类 print 豁免生效）')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='代码质量棘轮门禁')
    parser.add_argument('--verbose', action='store_true', help='列出具体位置')
    parser.add_argument('--update', action='store_true', help='把当前值写成新基线')
    parser.add_argument('--allow-increase', action='store_true',
                        help='允许基线上调（默认只允许下降）')
    parser.add_argument('--self-test', action='store_true', help='检测器自证')
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    result = run_scan()
    counts = counts_of(result)
    baseline = load_baseline()

    if args.verbose:
        for metric in ALL_METRICS:
            print('--- %s (%d) ---' % (metric, counts[metric]))
            for path, line_no, snippet in result[metric][:40]:
                print('  %s:%d  %s' % (path, line_no, snippet[:100]))
            if counts[metric] > 40:
                print('  ... 其余 %d 处省略' % (counts[metric] - 40))

    if args.update:
        new_baseline = dict(baseline)
        increased = []
        for metric, value in counts.items():
            old = baseline.get(metric)
            if old is not None and value > old and not args.allow_increase:
                increased.append('%s: %d -> %d' % (metric, old, value))
            new_baseline[metric] = value
        if increased:
            print('[FAIL] 基线只允许下降，以下指标上调被拒绝：')
            for item in increased:
                print('  %s' % item)
            print('若确实必要，请显式加 --allow-increase 并在提交信息里写明理由。')
            return 1
        with open(BASELINE_FILE, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(new_baseline, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write('\n')
        print('[OK] 基线已更新：%s' % _rel(BASELINE_FILE))
        for metric in ALL_METRICS:
            print('  %-16s %s' % (metric, new_baseline.get(metric)))
        return 0

    if not baseline:
        print('[FAIL] 缺少基线文件 %s；先执行 --update 生成。' % _rel(BASELINE_FILE))
        return 1

    problems = []
    # 列宽按最长指标名算：待审核段加入后 `pending_writefile_bare_success` 比原来宽一倍（P2-11）
    name_width = max(len(m) for m in ALL_METRICS) + 2
    for metric in ALL_METRICS:
        old = baseline.get(metric)
        new = counts[metric]
        mark = 'OK ' if (old is not None and new <= old) else 'BAD'
        print('  [%s] %-*s 当前 %4d  基线 %4d' % (
            mark, name_width, metric, new, old if old is not None else -1))
        if old is None:
            problems.append('%s 缺基线' % metric)
        elif new > old:
            problems.append('%s 由 %d 增到 %d' % (metric, old, new))

    if problems:
        print('\n[FAIL] 代码质量棘轮被突破：')
        for item in problems:
            print('  - %s' % item)
        print('请消除新增问题；若确属合理（如插件脚本新增 print），'
              '用 --update --allow-increase 并说明理由。')
        return 1

    print('\n[OK] 代码质量棘轮通过（各指标均未恶化）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
