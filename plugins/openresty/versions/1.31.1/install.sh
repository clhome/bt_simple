#!/bin/bash
# ---------------------------------------------------------------------------
# OpenResty 1.31.1（上游 1.31.1.1）安装/升级入口（薄封装）
#
# 构建配方统一在 versions/common/openresty_build.sh（唯一真源）。
# 历史版本目录名沿用三段「1.31.1」（面板已装用户的 version.pl 可能就是它），
# 真实上游版本号是 1.31.1.1。
# ---------------------------------------------------------------------------
YF_OPENRESTY_VERSION="1.31.1.1"
YF_OPENRESTY_SERIES="1.31.1"

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
