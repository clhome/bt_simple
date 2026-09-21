#!/usr/bin/env python3
# coding: utf-8
"""御风面板（bt_simple）提交门禁 —— 唯一入口。

    python testsuite/run_all.py             # 完整门禁（默认）
    python testsuite/run_all.py --static    # 只跑静态检查（秒级，迭代时用）
    python testsuite/run_all.py -k i18n     # 只跑名字含 i18n 的模块
    python testsuite/run_all.py --list      # 列出全部用例与隔离原因
    python testsuite/run_all.py --jobs 8    # 并行度（默认 min(8, CPU)）
    python testsuite/run_all.py -v          # 失败时打印完整输出

退出码：0 = 全部通过，可以提交；1 = 有失败，禁止提交。

设计要点（都是踩过坑才加的，改动前请先读懂）：

1. **每个模块独立子进程 + 超时**：一个模块死循环 / 段错误不会带走整套门禁。
2. **必须校验「收集到的用例数 > 0」**：`python -m unittest` 在没收集到用例时
   也会打印 `Ran 0 tests ... OK` 并返回 0。不校验就会得到「永远全绿」的假门禁
   —— 这正是本仓库历史上栽过的跟头。
3. **隔离区（quarantine.txt）**：已知的、与本次改动无关的红色用例。它们不影响
   门禁结果，但门禁会**反向检查它们是否意外转绿**，转绿即报错，强制有人去清理名单，
   避免隔离区变成垃圾场。
4. **静态门禁与用例分开**：静态检查（i18n 9 项、检测器自证）是纯标准库、
   无副作用的，`--static` 可以秒级跑完，适合编辑过程中反复跑。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable

MODULE_TIMEOUT = 600          # 单模块超时（秒）
STATIC_TIMEOUT = 300
RAN_RE = re.compile(r'^Ran (\d+) tests? in ', re.M)

# 静态门禁：不依赖 testsuite/ 下的用例，直接调用仓库里的独立工具
STATIC_GATES = [
    ('i18n 静态门禁（9 项）', [PY, 'scripts/verify_i18n.py']),
    ('i18n 检测器自证', [PY, 'scripts/verify_i18n.py', '--self-test']),
]


# --------------------------------------------------------------------------
# 隔离区
# --------------------------------------------------------------------------
def load_quarantine():
    """读 quarantine.txt：`模块名  # 原因`，返回 {模块名: 原因}。"""
    path = os.path.join(HERE, 'quarantine.txt')
    out = {}
    if not os.path.isfile(path):
        return out
    with open(path, 'r', encoding='utf-8') as fp:
        for line in fp:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            mod, _, reason = line.partition('#')
            mod = mod.strip()
            if mod:
                out[mod] = reason.strip() or '（未填写原因）'
    return out


# --------------------------------------------------------------------------
# 发现用例
# --------------------------------------------------------------------------
def discover_modules():
    mods = []
    for name in sorted(os.listdir(HERE)):
        if name.startswith('test_') and name.endswith('.py'):
            if os.path.isfile(os.path.join(HERE, name)):
                mods.append(name)
    return mods


def run_cmd(cmd, timeout):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=timeout)
        return p.returncode, (p.stdout + b'\n' + p.stderr).decode('utf-8', 'replace'), time.time() - t0
    except subprocess.TimeoutExpired:
        return 124, f'超时 >{timeout}s', time.time() - t0
    except OSError as e:
        return 125, f'无法启动：{e}', time.time() - t0


def run_static(name, cmd):
    rc, text, secs = run_cmd(cmd, STATIC_TIMEOUT)
    ok = rc == 0
    reason = '' if ok else f'退出码 {rc}'
    return {'kind': 'static', 'name': name, 'ok': ok, 'reason': reason,
            'ran': 0, 'secs': secs, 'text': text, 'cmd': ' '.join(cmd)}


def run_module(name):
    cmd = [PY, '-m', 'unittest', 'testsuite.' + name[:-3], '-v']
    rc, text, secs = run_cmd(cmd, MODULE_TIMEOUT)
    m = RAN_RE.search(text)
    ran = int(m.group(1)) if m else 0
    if rc == 124:
        ok, reason = False, '超时'
    elif ran == 0:
        # 关键护栏：收集不到用例不能算通过
        ok, reason = False, '未收集到任何用例（疑似假门禁）'
    else:
        ok = (rc == 0)
        reason = '' if ok else f'退出码 {rc}，{len(re.findall(r"^(FAIL|ERROR): ", text, re.M))} 个失败'
    return {'kind': 'case', 'name': name, 'ok': ok, 'reason': reason,
            'ran': ran, 'secs': secs, 'text': text, 'cmd': ' '.join(cmd)}


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description='御风面板提交门禁')
    ap.add_argument('--static', action='store_true', help='只跑静态门禁（秒级）')
    ap.add_argument('-k', '--filter', help='只跑名字包含该子串的用例')
    ap.add_argument('--list', action='store_true', help='列出用例与隔离原因')
    ap.add_argument('--jobs', type=int, default=min(8, (os.cpu_count() or 4)),
                    help='并行度（默认 min(8, CPU)）')
    ap.add_argument('-v', '--verbose', action='store_true', help='失败时打印完整输出')
    args = ap.parse_args()

    quarantine = load_quarantine()
    modules = discover_modules()
    if args.filter:
        modules = [m for m in modules if args.filter in m]

    if args.list:
        print(f'静态门禁（{len(STATIC_GATES)} 项）：')
        for name, _ in STATIC_GATES:
            print(f'  [静态] {name}')
        print(f'\n用例模块（{len(modules)} 个）：')
        for m in modules:
            tag = ' [隔离]' if m in quarantine else ''
            print(f'  {m}{tag}')
            if m in quarantine:
                print(f'        └─ {quarantine[m]}')
        return 0

    t0 = time.time()
    print('=' * 78)
    print('御风面板提交门禁（bt_simple / testsuite）')
    print('=' * 78)

    results = []

    if not args.static:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for r in pool.map(lambda m: run_module(m), modules):
                results.append(r)
                print(format_line(r, quarantine), flush=True)
    else:
        print('（--static：只跑静态门禁）')

    for name, cmd in STATIC_GATES:
        r = run_static(name, cmd)
        results.append(r)
        print(format_line(r, quarantine), flush=True)

    # 汇总
    cases = [r for r in results if r['kind'] == 'case']
    statics = [r for r in results if r['kind'] == 'static']
    quarantined = [r for r in cases if r['name'] in quarantine]
    active = [r for r in cases if r['name'] not in quarantine]

    failed = [r for r in active if not r['ok']] + [r for r in statics if not r['ok']]
    unexpected_green = [r for r in quarantined if r['ok']]

    print('-' * 78)
    print(f"用例：{len(active)} 个参与门禁，{len(quarantined)} 个隔离；"
          f"静态门禁 {len(statics)} 项；总耗时 {round(time.time() - t0, 1)}s")
    print(f"参与门禁的用例共 {sum(r['ran'] for r in active)} 个 test 方法")

    if unexpected_green:
        print()
        print('⚠ 以下隔离用例「意外转绿」，请从 quarantine.txt 移除（否则隔离区会烂掉）：')
        for r in unexpected_green:
            print(f'    {r["name"]}  —— 原隔离原因：{quarantine[r["name"]]}')

    if failed:
        print()
        print(f'❌ 门禁未通过：{len(failed)} 项失败')
        for r in failed:
            print(f'    [{r["kind"]}] {r["name"]}  ({r["reason"]})')
            if args.verbose and r.get('text'):
                print('    ' + '-' * 70)
                for line in r['text'].strip().splitlines()[-60:]:
                    print('    | ' + line)
        print()
        print('禁止提交。修复后重跑：python testsuite/run_all.py')
        return 1

    if unexpected_green:
        return 1

    print()
    print('✅ 全部门禁通过，可以提交。')
    return 0


def format_line(r, quarantine):
    tag = 'QUAR' if (r['kind'] == 'case' and r['name'] in quarantine) else ('PASS' if r['ok'] else 'FAIL')
    extra = f"{r['ran']:>3}项" if r['kind'] == 'case' else '  — '
    line = f"[{tag}] {extra} {r['secs']:>6.1f}s  {r['name']}"
    if r['kind'] == 'case' and r['name'] in quarantine:
        line += f"   ← 隔离：{quarantine[r['name']]}"
    elif not r['ok']:
        line += f"   ← {r['reason']}"
    return line


if __name__ == '__main__':
    sys.exit(main())
