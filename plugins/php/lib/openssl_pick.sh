#!/bin/bash
# MySQL 编译期 OpenSSL 选择器（可安全 source 的纯函数库）
#
# ## 为什么需要
# 2026-10-27 的 CI 三轮红（5.6 的 `WITH_SSL=/www/server/lib/openssl11` →
# `WITH_SSL=bundled` → `WITH_SSL=system` 全失败）暴露的是「从来没实测过版本矩阵」。
# 实测（Debian 12 + OpenSSL 3.0.22，各版本源码真跑 cmake）：
#
#   * MySQL **5.5 / 5.6**：只认 OpenSSL **1.0.x**；5.6.51 已移除 `extra/yassl`，
#     `cmake/ssl.cmake` 只接受 system/yes/<path> → 只能自建 1.0.2 后 `-DWITH_SSL=<path>`；
#   * MySQL **5.7.44**：`cmake/ssl.cmake` 明确 `(OPENSSL_MAJOR_VERSION STREQUAL "1" OR "3")`
#     都算找到了 → **系统 OpenSSL 3.x 可直接用**（实测 3.0.22 通过 SSL 检查）；
#   * MySQL **8.0+**：`MIN_OPENSSL_VERSION_REQUIRED = "1.0.0"` → 系统 3.x 更没问题。
#
# 所以 5.7 及以后**不必自建 OpenSSL**：以前「系统 >=3 就自建」的做法每次安装都要多编
# 3~15 分钟，还多一个「openssl release 下载失败」的失败面。这里统一成：
#   **系统库能用就用（-DWITH_SSL=system），确实不能才自建。**
#
# ## 口径
#   yf_openssl_system_version           输出系统 openssl 版本（取不到则空）
#   yf_openssl_version_ge <have> <need> have >= need 时返回 0
#   yf_openssl_system_usable <min>      头文件存在且版本 >= min 时返回 0
#   yf_openssl_build_dir <1.1|3>        自建对应大版本，成功时输出安装目录；失败 exit 1

yf_openssl_system_version() {
	openssl version 2>/dev/null | awk '{print $2}'
}

# 把 `1.0.2u` 这类带字母后缀的版本归一化成 `1.0.2`（OpenSSL 1.0.2 系列的习惯写法）。
# 不归一化会被下面的字符检查判成「非版本号」→ 误判「系统库不可用」→ 白编一次 OpenSSL。
_yf_openssl_norm() {
	printf '%s' "${1:-}" | sed -n 's/^\([0-9][0-9.]*\).*/\1/p'
}

yf_openssl_version_ge() {
	local have=""
	local need="${2:-0.0.0}"
	have=$(_yf_openssl_norm "${1:-}")
	[ -n "${have}" ] || return 1
	case "${have}" in
		*[!0-9.]*) return 1 ;;   # LibreSSL 等非 OpenSSL：不认为「够用」
	esac
	awk -v a="${have}" -v b="${need}" 'BEGIN{
		split(a, x, "."); split(b, y, ".");
		for (i = 1; i <= 3; i++) {
			ai = (i in x) ? x[i] + 0 : 0;
			bi = (i in y) ? y[i] + 0 : 0;
			if (ai > bi) exit 0;
			if (ai < bi) exit 1;
		}
		exit 0;
	}'
}

# $1 = 最低可用版本（如 1.0.2 / 1.0.0）
yf_openssl_system_usable() {
	local min="${1:-1.0.0}"
	[ -f /usr/include/openssl/ssl.h ] || return 1
	yf_openssl_version_ge "$(yf_openssl_system_version)" "${min}"
}

# $1 = 大版本系列：1.1 或 3
# 成功时把「自建安装目录」打到 stdout；任何一步失败都 exit 1（调用方是安装脚本）。
yf_openssl_build_dir() {
	local series="${1:-}"
	local root="${rootPath:-}"
	local script=""
	local sub=""
	local label=""

	case "${series}" in
		1.1) script="openssl_11.sh"; sub="openssl11"; label="OpenSSL 1.1" ;;
		3) script="openssl.sh"; sub="openssl"; label="OpenSSL 3.x" ;;
		*) echo "[ERROR] yf_openssl_build_dir: 不支持的大版本 '${series}'（只支持 1.1 / 3）" >&2; exit 1 ;;
	esac

	if [ -z "${root}" ]; then
		echo "[ERROR] yf_openssl_build_dir: 缺少 rootPath（请在 install.sh 里 source 本库）" >&2
		exit 1
	fi

	if ! ( cd "${root}/plugins/php/lib" && /bin/bash "${script}" ); then
		echo "[ERROR] 自建 ${label} 失败（见上方 ${sub} 日志）" >&2
		exit 1
	fi

	local dir="${serverPath}/lib/${sub}"
	if [ ! -f "${dir}/include/openssl/ssl.h" ]; then
		echo "[ERROR] 自建 ${label} 后找不到 ${dir}/include/openssl/ssl.h" >&2
		exit 1
	fi
	printf '%s' "${dir}"
}
