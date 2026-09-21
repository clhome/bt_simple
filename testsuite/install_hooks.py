#!/usr/bin/env python3
# coding: utf-8
"""把提交门禁装成 git 的 pre-commit 钩子，让「不通过就不许提交」真正生效。

    python testsuite/install_hooks.py            # 安装（完整门禁）
    python testsuite/install_hooks.py --static   # 安装（只跑静态门禁，秒级）
    python testsuite/install_hooks.py --status   # 查看当前安装状态
    python testsuite/install_hooks.py --uninstall

注意：`.git/hooks/` 不随仓库分发，**每个克隆都要各自装一次**（或用
`git config core.hooksPath testsuite/hooks` 指向仓库内的目录，但那样钩子本身也会被提交）。
钩子可用 `git commit --no-verify` 临时绕过——这是 git 的标准逃生门，不做拦截。
"""
import argparse
import os
import stat
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOOK_PATH = os.path.join(ROOT, '.git', 'hooks', 'pre-commit')
MARKER = '# >>> yufeng testsuite pre-commit >>>'

HOOK_TEMPLATE = """#!/bin/sh
{marker}
# 御风面板（bt_simple）提交门禁 —— 由 testsuite/install_hooks.py 生成
# 卸载：python testsuite/install_hooks.py --uninstall
# 临时绕过：git commit --no-verify
if [ -n "$YUFENG_SKIP_TESTS" ]; then
    echo "[testsuite] YUFENG_SKIP_TESTS 已设置，跳过提交门禁"
    exit 0
fi
echo "[testsuite] 正在运行提交门禁…（绕过：git commit --no-verify）"
exec {python} testsuite/run_all.py {extra}
# <<< yufeng testsuite pre-commit <<<
"""


def quote(path):
    return '"%s"' % path if ' ' in path else path


def build_hook(python, static):
    return HOOK_TEMPLATE.format(
        marker=MARKER,
        python=quote(python),
        extra='--static' if static else '',
    ).rstrip() + '\n'


def read_existing():
    if not os.path.isfile(HOOK_PATH):
        return None
    with open(HOOK_PATH, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read()


def install(python, static, force):
    existing = read_existing()
    if existing is not None and MARKER not in existing and not force:
        print(f'❌ 已存在一个非本工具生成的 pre-commit 钩子：{HOOK_PATH}')
        print('   为避免破坏你的钩子，这里不覆盖。请二选一：')
        print('     1) 先备份/合并它，再用 --force 覆盖')
        print('     2) 手动把下面这行加进你的钩子：')
        print(f'        {quote(python)} testsuite/run_all.py')
        return 1

    os.makedirs(os.path.dirname(HOOK_PATH), exist_ok=True)
    with open(HOOK_PATH, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(build_hook(python, static))
    mode = os.stat(HOOK_PATH).st_mode
    os.chmod(HOOK_PATH, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f'✅ 已安装 pre-commit 钩子：{HOOK_PATH}')
    print(f'   解释器：{python}')
    print(f'   模式：{"只跑静态门禁（秒级）" if static else "完整门禁"}')
    print('   绕过：git commit --no-verify  或  设置环境变量 YUFENG_SKIP_TESTS=1')
    return 0


def status():
    existing = read_existing()
    if existing is None:
        print(f'未安装（{HOOK_PATH} 不存在）')
        return 0
    if MARKER in existing:
        mode = '只跑静态门禁' if '--static' in existing else '完整门禁'
        print(f'已安装（{HOOK_PATH}，模式：{mode}）')
    else:
        print(f'存在一个非本工具生成的 pre-commit 钩子：{HOOK_PATH}')
    return 0


def uninstall():
    existing = read_existing()
    if existing is None:
        print('未安装，无需卸载')
        return 0
    if MARKER not in existing:
        print(f'❌ {HOOK_PATH} 不是本工具生成的，拒绝删除')
        return 1
    os.remove(HOOK_PATH)
    print(f'✅ 已卸载 {HOOK_PATH}')
    return 0


def main():
    ap = argparse.ArgumentParser(description='安装/卸载 testsuite 提交门禁钩子')
    ap.add_argument('--static', action='store_true', help='钩子只跑静态门禁')
    ap.add_argument('--force', action='store_true', help='覆盖已存在的其它 pre-commit 钩子')
    ap.add_argument('--status', action='store_true', help='查看安装状态')
    ap.add_argument('--uninstall', action='store_true', help='卸载钩子')
    args = ap.parse_args()

    if not os.path.isdir(os.path.join(ROOT, '.git')):
        print(f'❌ {ROOT} 不是 git 仓库（找不到 .git）')
        return 1
    if args.status:
        return status()
    if args.uninstall:
        return uninstall()
    return install(sys.executable, args.static, args.force)


if __name__ == '__main__':
    sys.exit(main())
