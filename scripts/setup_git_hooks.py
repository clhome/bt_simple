#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键安装本地 Git 提交前门禁钩子 (pre-commit)。

本工具将把轻量静态门禁挂载到本地 .git/hooks/pre-commit。
在每次执行 git commit 时，自动运行 `python testsuite/run_all.py --static`（耗时约 3 秒），
彻底杜绝「本地以为通过、推送 GitHub Actions 却因 i18n 缺键或代码质量棘轮红掉」的问题。
"""

import os
import stat
import sys

HOOK_CONTENT = """#!/bin/sh
# 提交前本地门禁校验钩子（防止本地绿提交红）
# 只跑静态门禁（耗时约 3 秒），检查 i18n 多语言一致性/缺键与代码质量棘轮（silent_except、bare_except 等）

echo "[pre-commit] 正在运行本地静态门禁校验 (python testsuite/run_all.py --static)..."

if command -v python >/dev/null 2>&1; then
    PY_CMD="python"
elif command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
else
    echo "[pre-commit] 错误：未找到 Python 命令，请确认 Python 已添加到系统 PATH"
    exit 1
fi

$PY_CMD testsuite/run_all.py --static
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "❌ [pre-commit] 本地静态门禁未通过，禁止提交！"
    echo "请根据上方报错修复后重试，或执行: $PY_CMD testsuite/run_all.py --static"
    exit $EXIT_CODE
fi

echo "✅ [pre-commit] 本地静态门禁校验通过。"
exit 0
"""


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    git_dir = os.path.join(root, '.git')
    if not os.path.exists(git_dir):
        print(f"错误: 未找到 .git 目录 ({git_dir})，无法安装 hook。")
        sys.exit(1)

    hooks_dir = os.path.join(git_dir, 'hooks')
    os.makedirs(hooks_dir, exist_ok=True)
    target = os.path.join(hooks_dir, 'pre-commit')

    with open(target, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(HOOK_CONTENT)

    # 赋予执行权限 (POSIX)
    try:
        current_stat = os.stat(target)
        os.chmod(target, current_stat.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass

    print(f"[OK] 成功安装 pre-commit 钩子: {target}")
    print("以后每次 git commit 均会自动执行秒级静态门禁校验，彻底杜绝 CI 失败。")


if __name__ == '__main__':
    main()
