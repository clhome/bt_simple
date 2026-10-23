# coding: utf-8
"""P2-13 门禁用例的**别名模块**（只为让 `run_all.py -k php_session_perm` 能选到）。

门禁的 `-k` 是按**模块文件名子串**过滤的（`testsuite/run_all.py:322`：
`modules = [m for m in modules if args.filter in m]`），而本项用例的正式文件名是
`testsuite/test_php_session_dir_perm.py`（任务书指定名），其中不含连续子串
`php_session_perm`（中间隔着 `_dir`）—— 于是 `-k php_session_perm` 会选出 **0 个模块**，
而「0 个模块但退出码 0」正是本仓库反复强调要避免的**假绿**。

所以这里起一个 3 行别名把正式模块重新导出：断言全部写在
`testsuite/test_php_session_dir_perm.py` 里，本文件**不含任何断言**。
"""
import os
import sys

try:                                                        # `python -m unittest testsuite.xxx`
    from .test_php_session_dir_perm import *  # noqa: F401,F403
except ImportError:                                        # 直接 `python testsuite/xxx.py`
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_php_session_dir_perm import *  # noqa: F401,F403
