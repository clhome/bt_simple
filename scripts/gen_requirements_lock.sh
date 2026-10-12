#!/bin/bash
# ---------------------------------------------------------------------------
# 生成 requirements.lock（带哈希，可复现安装）
#
# 对应测评报告 P0-5「无 lockfile → 构建不可重现 / 供应链漂移不可审计」的修复入口。
#
# 前提（缺一不可）：
#   1. 需要**联网**访问 PyPI（或已配置可用的镜像，如 PIP_INDEX_URL）；
#   2. 需要 Python 3.9+ —— requirements.txt 里 flask / Werkzeug / pyOpenSSL /
#      cryptography 按 python_version 分档，不同解释器解析出的锁文件不同。
#      与 .github/workflows/security-scan.yml 的 `lock` job（Python 3.11）保持一致；
#   3. 需要 pip-tools：pip install "pip-tools>=7.4.0"。
#
# 用法：
#   bash scripts/gen_requirements_lock.sh              # 生成 <仓库根>/requirements.lock
#   bash scripts/gen_requirements_lock.sh out.lock     # 指定输出文件
#
# 口径（勿改）：
#   * 锁文件只用于**审计与可复现安装**，绝不作为唯一安装路径 ——
#     安装脚本（scripts/lib.sh / deploy.sh）仍以 requirements.txt 为准，
#     保证大陆网络 / 离线环境装得上（守卫见 testsuite/test_dependency_lock_and_hygiene.py）；
#   * 本脚本与 security-scan.yml 的 `lock` job 使用同一条 pip-compile 命令，
#     两者产物应当一致。
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-${ROOT}/requirements.lock}"

if ! command -v pip-compile >/dev/null 2>&1; then
    echo "缺少 pip-compile，请先执行：pip install 'pip-tools>=7.4.0'" >&2
    exit 1
fi

cd "${ROOT}"
echo "生成 ${OUT}（pip-compile --generate-hashes，需联网）..."
pip-compile --generate-hashes --resolver=backtracking \
    --output-file "${OUT}" requirements.txt
echo "完成：${OUT}"
