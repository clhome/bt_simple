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

# $1=模块名 $2=apt 包名(可多个候选，空格分隔，依次尝试) $3=rpm 包名 [$4=最低版本]
# 已满足 → 0；缺失但自动装成功后满足 → 0；否则 1（并打印可照抄的修复命令）
yf_ext_ensure_pkgconfig() {
	local _mod="${1:-}"
	local _apt_pkg="${2:-}"
	local _rpm_pkg="${3:-}"
	local _min="${4:-}"
	local _mgr=""
	local _last_err=""

	if yf_pkgconfig_has "${_mod}" "${_min}"; then
		return 0
	fi

	echo "[deps] 未检测到 ${_mod}${_min:+>=${_min}}，尝试自动补齐开发包..." >&2
	_mgr="$(yf_ext_pkg_mgr)"
	local _cand_err=""
	case "${_mgr}" in
		apt)
			[ -n "${_apt_pkg}" ] || return 1
			local _cand=""
			for _cand in ${_apt_pkg}; do
				echo "[deps] 正在尝试通过 apt 安装 ${_cand}..." >&2
				if command -v timeout >/dev/null 2>&1; then
					_cand_err=$(DEBIAN_FRONTEND=noninteractive timeout 300 apt-get install -y "${_cand}" 2>&1) || true
				else
					_cand_err=$(DEBIAN_FRONTEND=noninteractive apt-get install -y "${_cand}" 2>&1) || true
				fi
				if [ -n "${_last_err}" ]; then
					_last_err="${_last_err}"$'\n'"--- ${_cand} ---"$'\n'"${_cand_err}"
				else
					_last_err="${_cand_err}"
				fi
				if yf_pkgconfig_has "${_mod}" "${_min}"; then
					break
				fi
			done
			;;
		dnf|yum)
			[ -n "${_rpm_pkg}" ] || return 1
			local _cand=""
			for _cand in ${_rpm_pkg}; do
				echo "[deps] 正在尝试通过 ${_mgr} 安装 ${_cand}..." >&2
				if command -v timeout >/dev/null 2>&1; then
					_cand_err=$(timeout 300 "${_mgr}" install -y "${_cand}" 2>&1) || true
				else
					_cand_err=$("${_mgr}" install -y "${_cand}" 2>&1) || true
				fi
				if [ -n "${_last_err}" ]; then
					_last_err="${_last_err}"$'\n'"--- ${_cand} ---"$'\n'"${_cand_err}"
				else
					_last_err="${_cand_err}"
				fi
				if yf_pkgconfig_has "${_mod}" "${_min}"; then
					break
				fi
			done
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

	if [ -n "${_last_err}" ]; then
		echo "[deps][WARN] 包管理器执行输出摘要：" >&2
		printf '%s\n' "${_last_err}" | tail -n 8 | sed 's/^/    /' >&2
	fi

	local _pref_apt=$(echo "${_apt_pkg}" | awk '{print $1}')
	local _pref_rpm=$(echo "${_rpm_pkg}" | awk '{print $1}')
	echo "[deps][ERROR] 缺少 ${_mod}${_min:+>=${_min}} 开发包，扩展无法编译。请手动安装后重试：" >&2
	if [ -n "${_pref_apt}" ]; then
		echo "    Debian/Ubuntu:  apt-get install -y ${_pref_apt}" >&2
	fi
	if [ -n "${_pref_rpm}" ]; then
		echo "    RHEL/CentOS:    yum install -y ${_pref_rpm}" >&2
	fi
	return 1
}

# 确保 PHP 本体编译所需的核心底层开发依赖（报告 N10：防止新机时序窗口缺少 libxml2 等包导致 configure 失败）
# 返回：0=核心依赖已全部满足；1=依赖缺失且自动补齐失败（已输出可照抄的手工安装指令）
yf_php_ensure_core_build_deps() {
	local _mgr="$(yf_ext_pkg_mgr)"
	local _missing=()

	if ! command -v pkg-config >/dev/null 2>&1; then
		_missing+=("pkg-config")
	fi

	if ! yf_pkgconfig_has "libxml-2.0" "2.9.4"; then
		_missing+=("libxml2")
	fi

	if ! yf_pkgconfig_has "sqlite3"; then
		_missing+=("sqlite3")
	fi

	if [ "${#_missing[@]}" -eq 0 ]; then
		return 0
	fi

	echo "[deps] 检测到 PHP 主构建核心依赖未就绪: ${_missing[*]}，正在尝试自动安装..." >&2

	local _apt_pkgs="pkg-config libxml2-dev libsqlite3-dev zlib1g-dev libssl-dev"
	local _rpm_pkgs="pkgconfig libxml2-devel sqlite-devel zlib-devel openssl-devel"

	local _install_log=""
	case "${_mgr}" in
		apt)
			# 新机或缓存过期时预先更新索引，避免因缓存导致依赖安装失败（P1-2）
			_cand_out=$(DEBIAN_FRONTEND=noninteractive apt-get update -y -o Acquire::Languages=none 2>&1) || true
			if [ -n "${_cand_out}" ]; then
				if [ -n "${_install_log}" ]; then _install_log="${_install_log}"$'\n'"${_cand_out}"; else _install_log="${_cand_out}"; fi
			fi
			for _p in ${_apt_pkgs}; do
				_cand_out=$(DEBIAN_FRONTEND=noninteractive apt-get install -y "${_p}" 2>&1) || true
				if [ -n "${_cand_out}" ]; then
					if [ -n "${_install_log}" ]; then _install_log="${_install_log}"$'\n'"${_cand_out}"; else _install_log="${_cand_out}"; fi
				fi
			done
			;;
		dnf|yum)
			for _p in ${_rpm_pkgs}; do
				_cand_out=$("${_mgr}" install -y "${_p}" 2>&1) || true
				if [ -n "${_cand_out}" ]; then
					if [ -n "${_install_log}" ]; then _install_log="${_install_log}"$'\n'"${_cand_out}"; else _install_log="${_cand_out}"; fi
				fi
			done
			;;
		*)
			;;
	esac

	local _still_missing=()
	if ! command -v pkg-config >/dev/null 2>&1; then
		_still_missing+=("pkg-config")
	fi
	if ! yf_pkgconfig_has "libxml-2.0" "2.9.4"; then
		_still_missing+=("libxml2-dev(libxml-2.0>=2.9.4)")
	fi
	if ! yf_pkgconfig_has "sqlite3"; then
		_still_missing+=("libsqlite3-dev(sqlite3)")
	fi
	if ! yf_pkgconfig_has "zlib"; then
		_still_missing+=("zlib1g-dev(zlib)")
	fi
	if ! yf_pkgconfig_has "openssl"; then
		_still_missing+=("libssl-dev(openssl)")
	fi

	if [ "${#_still_missing[@]}" -eq 0 ]; then
		echo "[deps] PHP 主构建核心依赖已就绪" >&2
		return 0
	fi

	if [ -n "${_install_log}" ]; then
		echo "[deps][WARN] 包管理器输出摘要：" >&2
		printf '%s\n' "${_install_log}" | tail -n 10 | sed 's/^/    /' >&2
	fi

	echo "[deps][ERROR] PHP 主构建核心开发依赖缺失: ${_still_missing[*]}，构建前中止。" >&2
	echo "请先手动安装所需依赖后重试：" >&2
	case "${_mgr}" in
		apt)
			echo "    Debian/Ubuntu:  apt-get update && apt-get install -y ${_apt_pkgs}" >&2
			;;
		dnf|yum)
			echo "    RHEL/CentOS:    ${_mgr} install -y ${_rpm_pkgs}" >&2
			;;
		*)
			echo "    Debian/Ubuntu:  apt-get update && apt-get install -y ${_apt_pkgs}" >&2
			echo "    RHEL/CentOS:    yum install -y ${_rpm_pkgs}" >&2
			;;
	esac
	return 1
}
