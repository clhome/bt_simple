#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""御风面板本地快速门禁（提交前必跑，~25秒内拦截所有 CI 报错点）。

包含：
1. 静态门禁 4 项（i18n 12项、i18n自证、代码质量棘轮、代码质量自证）
2. 核心代码安全棘轮：
   - test_shell_concat_ratchet.py（shell 裸拼注入棘轮）
   - test_writefile_must_and_ratchet.py（文件原子写入安全棘轮）
   - test_download_tls_ratchet.py（下载 TLS 安全棘轮）
   - test_download_verify_ratchet.py（下载完整性校验棘轮）
"""

import os
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


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)

    print("=" * 70)
    print("御风面板 本地提交前快速门禁（Quick Gate）")
    print("=" * 70)

    py = sys.executable

    steps = [
        ("静态门禁 4 项 (verify_i18n + verify_code_quality)", [py, "testsuite/run_all.py", "--static"]),
        ("Shell 裸拼防注入棘轮 (test_shell_concat_ratchet)", [py, "-m", "unittest", "testsuite/test_shell_concat_ratchet.py"]),
        ("文件写入与下载安全棘轮 (writefile + tls + verify)", [
            py, "-m", "unittest",
            "testsuite/test_writefile_must_and_ratchet.py",
            "testsuite/test_download_tls_ratchet.py",
            "testsuite/test_download_verify_ratchet.py"
        ]),
    ]

    for title, cmd in steps:
        if not run_step(title, cmd):
            print("\n[FAIL] 快速门禁未通过，请根据上方日志修复后再提交。")
            sys.exit(1)

    print("\n" + "=" * 70)
    print("[OK] 恭喜！所有静态门禁与核心安全棘轮全部通过，可放心推送到 GitHub。")
    print("=" * 70)


if __name__ == '__main__':
    main()

