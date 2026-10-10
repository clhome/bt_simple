# coding:utf-8
import os
import sys
import time
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FT_DIR = os.path.join(ROOT_DIR, 'testsuite', 'Functional Testing')

def main():
    print("=" * 80)
    print(" 御风面板（bt_simple）全模块端到端功能性测试运行器 (FT Suite Runner)")
    print("=" * 80)

    test_modules = [
        ('守护进程与系统 CLI (Daemons & CLI)', 'ft_daemons_and_cli.py'),
        ('Web Admin 控制台 13 大核心模块 (Web Admin Core)', 'ft_admin_web_core.py'),
        ('数据库插件生态 (Databases Plugins)', 'ft_plugins_databases.py'),
        ('Web 网关与运行环境插件 (Web & Runtime)', 'ft_plugins_web_runtime.py'),
        ('系统与运维管理插件 (System & Ops)', 'ft_plugins_system_ops.py'),
    ]

    total_tests = 0
    total_failures = 0
    total_errors = 0
    start_total_time = time.time()
    results_summary = []

    for name, filename in test_modules:
        file_path = os.path.join(FT_DIR, filename)
        if not os.path.exists(file_path):
            print(f"[MISSING] {filename}")
            continue

        os.chdir(ROOT_DIR)
        t_start = time.time()
        loader = unittest.TestLoader()
        suite = loader.discover(start_dir=FT_DIR, pattern=filename)
        
        runner = unittest.TextTestRunner(verbosity=0)
        result = runner.run(suite)
        t_elapsed = time.time() - t_start

        test_count = result.testsRun
        fails = len(result.failures)
        errs = len(result.errors)
        total_tests += test_count
        total_failures += fails
        total_errors += errs

        status = "PASS" if (fails == 0 and errs == 0) else "FAIL"
        results_summary.append({
            'name': name,
            'file': filename,
            'tests': test_count,
            'status': status,
            'time': t_elapsed
        })

        color_flag = "[OK]" if status == "PASS" else "[FAIL]"
        print(f"[{status:^6}] {color_flag} {name:<45} | 用例: {test_count:2d} | 耗时: {t_elapsed:.3f}s")
        if fails > 0 or errs > 0:
            for f in result.failures:
                print(f"       Failure: {f[0]}: {f[1]}")
            for e in result.errors:
                print(f"       Error: {e[0]}: {e[1]}")

    total_time = time.time() - start_total_time
    print("-" * 80)
    print(f"总计模块: {len(test_modules)} 个 | 总执行用例: {total_tests} 项 | 总耗时: {total_time:.3f}s")
    if total_failures == 0 and total_errors == 0:
        print(">>> 综合判定: 全部通过 (100% PASS) - 满足全模块功能性设计与交付标准 <<<")
        print("=" * 80)
        return 0
    else:
        print(f">>> 综合判定: 存在失败 (Failures: {total_failures}, Errors: {total_errors}) <<<")
        print("=" * 80)
        return 1

if __name__ == '__main__':
    sys.exit(main())
