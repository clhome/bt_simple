#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）自动化发版与 Tag 提交入口
# ---------------------------------------------------------------------------------
import importlib.util
import os
import sys

_core_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "release.py")
spec = importlib.util.spec_from_file_location("release_core", _core_script)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

# 导出核心函数
for _attr in dir(core):
    if not _attr.startswith("__"):
        globals()[_attr] = getattr(core, _attr)

if __name__ == "__main__":
    try:
        sys.exit(core.main())
    except KeyboardInterrupt:
        print("\n[INFO] 用户中断操作。")
        sys.exit(130)
