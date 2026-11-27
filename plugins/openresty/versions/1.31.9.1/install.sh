#!/bin/bash
# ---------------------------------------------------------------------------
# OpenResty 1.31.9.1 安装/升级入口（薄封装）
#
# 构建配方统一在 versions/common/openresty_build.sh（唯一真源）。
# 本文件由「御风软件版本在线同步」按同一模板生成，手工改动会在下次同步被覆盖；
# 要调整编译参数请改 common/openresty_build.sh。
#
# 上游说明（2026-11-23）：nginx core 1.31.8 → 1.31.9，含 10 项安全修复
# （HTTP/2/3 内存破坏与 UAF、resolver/mail proxy UAF、try_files+alias 溢出等）。
# ---------------------------------------------------------------------------
YF_OPENRESTY_VERSION="1.31.9.1"
YF_OPENRESTY_SERIES="1.31.9.1"

# 兼容被 `sh -x` 调用（Debian 的 /bin/sh 是 dash）
if [ -z "${BASH_VERSION:-}" ]; then
	exec bash "$0" "$@"
fi

_build_sh="$(cd "$(dirname "$0")" && pwd)/../common/openresty_build.sh"
if [ ! -f "${_build_sh}" ]; then
	echo "[ERROR] 缺少构建配方: ${_build_sh}" >&2
	exit 1
fi
. "${_build_sh}"
