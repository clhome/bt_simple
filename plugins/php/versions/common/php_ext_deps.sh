#!/bin/bash
# PHP 扩展编译期「开发包依赖」探测 / 自动补齐（可安全 source 纯函数库）
#
# 背景（《问题报告》P1-新：php 扩展构建依赖不自带）
#   php84 两次安装失败的两个姿势：
#     #23 主构建完成，但 curl 扩展找不到 libcurl（pkg-config 无 libcurl>=7.61）；
#     #24 libcurl 有了，readline 又倒在 libedit（下载波动，见 lib/libedit.sh）。
#   脚本本身不装 libcurl-dev 之类的开发包，能否编出来完全取决于机器既有环境
#   （#21/#22 恰好有 libcurl-dev 就过了）。这属于「安装结果取决于运气」。
#
# 这里提供两件事：
#   yf_pkgconfig_has <模块> [最低版本]                 纯探测，不装东西
#   yf_ext_ensure_pkgconfig <模块> <apt包> <rpm包>     缺失时尝试自动装，仍缺则返回 1
#
# 约定：调用方在返回 1 时必须给出**可照抄的命令**再失败，不许继续 configure。
# 只做探测/装包，不改动任何 PHP 产物。

# $1=模块名（pkg-config 名，如 libcurl）；$2=最低版本（可空）
yf_pkgconfig_has() {
	local _mod="${1:-}"
	local _min="${2:-}"
	[ -n "${_mod}" ] || return 1
	command -v pkg-config >/dev/null 2>&1 || return 1
	if [ -n "${_min}" ]; then
		pkg-config --atleast-version="${_min}" "${_mod}" >/dev/null 2>&1
	else
		pkg-config --exists "${_mod}" >/dev/null 2>&1
	fi
}

# 判断包管理器（apt / dnf / yum），输出其一；都没有则输出空
yf_ext_pkg_mgr() {
	if command -v apt-get >/dev/null 2>&1; then
		echo apt
	elif command -v dnf >/dev/null 2>&1; then
		echo dnf
	elif command -v yum >/dev/null 2>&1; then
		echo yum
	else
		echo ''
	fi
}

# $1=模块名 $2=apt 包名 $3=rpm 包名 [$4=最低版本]
# 已满足 → 0；缺失但自动装成功后满足 → 0；否则 1（并打印可照抄的修复命令）
yf_ext_ensure_pkgconfig() {
	local _mod="${1:-}"
	local _apt_pkg="${2:-}"
	local _rpm_pkg="${3:-}"
	local _min="${4:-}"
	local _mgr=""

	if yf_pkgconfig_has "${_mod}" "${_min}"; then
		return 0
	fi

	echo "[deps] 未检测到 ${_mod}${_min:+>=${_min}}，尝试安装开发包（${_apt_pkg:-?} / ${_rpm_pkg:-?}）..." >&2
	_mgr="$(yf_ext_pkg_mgr)"
	case "${_mgr}" in
		apt)
			[ -n "${_apt_pkg}" ] || return 1
			DEBIAN_FRONTEND=noninteractive apt-get install -y ${_apt_pkg} >/dev/null 2>&1 || true
			;;
		dnf|yum)
			[ -n "${_rpm_pkg}" ] || return 1
			"${_mgr}" install -y ${_rpm_pkg} >/dev/null 2>&1 || true
			;;
		*)
			echo "[deps][ERROR] 未识别的包管理器，无法自动安装 ${_mod} 开发包" >&2
			return 1
			;;
	esac

	if yf_pkgconfig_has "${_mod}" "${_min}"; then
		echo "[deps] ${_mod} 已就绪" >&2
		return 0
	fi

	echo "[deps][ERROR] 缺少 ${_mod}${_min:+>=${_min}} 开发包，扩展无法编译。请手动安装后重试：" >&2
	if [ -n "${_apt_pkg}" ]; then
		echo "    Debian/Ubuntu:  apt-get install -y ${_apt_pkg}" >&2
	fi
	if [ -n "${_rpm_pkg}" ]; then
		echo "    RHEL/CentOS:    yum install -y ${_rpm_pkg}" >&2
	fi
	return 1
}
