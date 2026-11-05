#!/usr/bin/env bash
# ---------------------------------------------------------------------------------
# bt_simple 自动化发布脚本 (Linux/Unix 入口)
# ---------------------------------------------------------------------------------
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
    python3 "$DIR/scripts/release.py" "$@"
elif command -v python >/dev/null 2>&1; then
    python "$DIR/scripts/release.py" "$@"
else
    echo "[ERROR] 未检测到 python/python3 环境，请先安装 Python！"
    exit 1
fi

