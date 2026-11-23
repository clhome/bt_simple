#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""御风面板本地提交前智能增量快速门禁（Quick Gate）。

设计原则：
1. 【静态门禁必查】：i18n 12项、代码质量棘轮等静态指标（~8秒）
2. 【核心通用护栏必查】：
   - test_shell_concat_ratchet.py（shell 裸拼防注入棘轮）
   - test_dialog_i18n_overflow.py（弹窗溢出与多语言换行护栏）
   - test_writefile_must_and_ratchet.py（原子写文件安全）
3. 【智能增量定向检测】：根据 git status 变动文件，仅自动触发受影响模块的测试用例（如改动 plugins/jdk 则仅跑 -k jdk 用例），秒级搞定。
"""

import os
import re
import subprocess
import sys
import time


def run_step(title, cmd):
    print(f"--> [正在运行] {title}...")
    t0 = time.time()
    p = subprocess.run(cmd, shell=False)
    cost = round(time.time() - t0, 1)
    if p.returncode != 0:
        print(f"[FAIL] {title} 未通过 (退出码 {p.returncode})，耗时 {cost}s")
        return False
    print(f"[PASS] {title} 通过，耗时 {cost}s")
    return True


def get_git_changed_files():
    """获取工作区与暂存区的所有变更文件列表。"""
    try:
        p = subprocess.run(['git', 'status', '--porcelain'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        files = []
        for line in p.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # porcelain 格式: XY filename 或 R  orig -> new
            parts = line.split(maxsplit=1)
            if len(parts) >= 2:
                fpath = parts[1]
                if '->' in fpath:
                    fpath = fpath.split('->')[-1].strip()
                files.append(fpath.replace('\\', '/'))
        return files
    except Exception:
        return []


def detect_impacted_modules(files):
    """根据变更文件推断受影响的插件与模块关键词。"""
    keywords = set()
    ignored_exts = {'.md', '.txt', '.png', '.jpg', '.jpeg', '.svg', '.ico', '.gitignore'}

    for f in files:
        _, ext = os.path.splitext(f)
        if ext.lower() in ignored_exts:
            continue

        # 匹配 plugins/<name>/
        m = re.match(r'^plugins/([^/]+)/', f)
        if m:
            keywords.add(m.group(1))
            continue

        # 匹配 testsuite/test_<name>*.py
        m_test = re.match(r'^testsuite/test_([a-zA-Z0-9]+)', f)
        if m_test:
            keywords.add(m_test.group(1))
            continue

        # 匹配 web/admin/<name>/
        m_web = re.match(r'^web/admin/([^/]+)/', f)
        if m_web:
            keywords.add(m_web.group(1))
            continue

    return sorted(keywords)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)

    print("=" * 70)
    print("御风面板 本地提交前智能快速门禁（Quick Gate - 方案 B 增量模式）")
    print("=" * 70)

    py = sys.executable

    # 1. 必跑核心门禁
    steps = [
        ("静态门禁 4 项 (verify_i18n + verify_code_quality)", [py, "testsuite/run_all.py", "--static"]),
        ("代码安全与布局护栏 (shell_concat + dialog_i18n_overflow + writefile)", [
            py, "-m", "unittest",
            "testsuite/test_shell_concat_ratchet.py",
            "testsuite/test_dialog_i18n_overflow.py",
            "testsuite/test_writefile_must_and_ratchet.py"
        ]),
    ]

    for title, cmd in steps:
        if not run_step(title, cmd):
            print("\n[FAIL] 核心门禁未通过，请根据上方日志修复后再提交。")
            sys.exit(1)

    # 2. 智能增量检测：受影响模块定向用例
    changed_files = get_git_changed_files()
    impacted_modules = detect_impacted_modules(changed_files)

    if impacted_modules:
        print(f"\n--> 检测到本次变更涉及模块: {', '.join(impacted_modules)}")
        for mod in impacted_modules:
            # 检查是否有匹配的测试用例文件
            test_files = [fn for fn in os.listdir("testsuite") if fn.startswith("test_") and mod in fn and fn.endswith(".py")]
            if test_files:
                title = f"模块增量用例回归 (-k {mod}，共 {len(test_files)} 个关联测试模块)"
                cmd = [py, "testsuite/run_all.py", "-k", mod]
                if not run_step(title, cmd):
                    print(f"\n[FAIL] 模块 [{mod}] 增量测试未通过，请修复后再提交。")
                    sys.exit(1)
            else:
                print(f"--> 模块 [{mod}] 无单独 test_{mod}*.py 用例，跳过专属回归。")
    else:
        print("\n--> 未检测到受影响的核心逻辑模块变更（或仅为文档/静态资源变更），跳过增量用例。")

    print("\n" + "=" * 70)
    print("[OK] 恭喜！智能快速门禁全部通过，代码质量与安全达标，可放心提交与推送。")
    print("=" * 70)


if __name__ == '__main__':
    main()
