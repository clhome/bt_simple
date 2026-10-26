#!/bin/bash
# ---------------------------------------------------------------------------------
# 源码包获取器 —— 「下载了没 + 下全了没」一次判清（《问题报告》次要-3 / 通用原则 2）
#
# 为什么需要：各版本脚本的下载写法长期是
#
#     if [ ! -f ${dir}/pkg.tar.gz ];then
#         wget -nv --no-check-certificate -O ${dir}/pkg.tar.gz --tries=3 <url>
#     fi
#     if [ ! -d ${dir}/pkg-1.0 ];then
#         cd ${dir} && tar -zxf ${dir}/pkg.tar.gz     # 0 字节时必死，且重跑必死
#     fi
#
# 三个坑：
#   1. `wget` 的退出码没人看；源 404 / CDN 返回 HTML 时留下 0 字节或错误页；
#   2. 守卫只判「文件存在」⇒ 毒化：下次重跑跳过下载、直接 tar 失败；
#   3. 没有备用通道：`wget` 在部分网络下 `No data received`，而 `curl` 同一条 URL
#      是通的（真机实测 dev.mysql.com 就是这样）。
#
# 本文件的口径：**文件非空 + 能 `tar -t` 通过 + 包内顶层目录符合预期**才算下载成功；
# 失败立刻删包（绝不留下毒化文件）并返回非 0，由调用方 `|| exit 1`。
#
# 用法：
#   source "${rootPath}/scripts/lib_src_fetch.sh"
#   yf_src_fetch "${mysqlDir}/mysql-boost-8.0.46.tar.gz" "<url>" "mysql-8.0.46" || exit 1
# ---------------------------------------------------------------------------------

# yf_src_fetch <目标文件> <URL> [期望包内顶层目录名]
#   环境变量：
#     YF_FETCH_TIMEOUT  单次下载超时秒数（默认 900）
#   返回：0 = 包已就绪且校验通过；非 0 = 失败（已打印原因，文件已删除）
yf_src_fetch() {
	local _dst=${1:-}
	local _url=${2:-}
	local _want_top=${3:-}
	local _timeout=${YF_FETCH_TIMEOUT:-900}

	if [ -z "${_dst}" ] || [ -z "${_url}" ]; then
		echo "[ERROR] yf_src_fetch: 缺少参数（目标=${_dst} URL=${_url}）" >&2
		return 1
	fi

	# ① 已存在且校验通过 ⇒ 幂等返回（重跑不重下）
	if _yf_src_fetch_verify "${_dst}" "${_want_top}"; then
		echo "[src_fetch] 已存在且校验通过，跳过下载: ${_dst}"
		return 0
	fi
	# ② 存在但不合格 ⇒ 删掉（这是「毒化重跑」的源头），重新下
	if [ -f "${_dst}" ]; then
		echo "[src_fetch][WARN] 本地文件为空或已损坏，删除后重新下载: ${_dst}"
		rm -f "${_dst}"
	fi

	mkdir -p "$(dirname "${_dst}")" 2>/dev/null || true
	echo "[src_fetch] 下载: ${_url}"

	# ③ curl 优先（wget 在部分 CDN 上会 No data received），wget 兜底
	if command -v curl >/dev/null 2>&1; then
		curl -fSL --connect-timeout 20 --max-time "${_timeout}" -o "${_dst}" "${_url}" || rm -f "${_dst}"
	fi
	if [ ! -s "${_dst}" ] && command -v wget >/dev/null 2>&1; then
		wget -nv --no-check-certificate -T 120 -t 3 -O "${_dst}" "${_url}" || rm -f "${_dst}"
	fi

	if ! _yf_src_fetch_verify "${_dst}" "${_want_top}"; then
		rm -f "${_dst}"
		echo "[ERROR] 源码包下载失败或损坏: ${_url}" >&2
		echo "[ERROR] 已删除残留文件（避免下次重跑被 0 字节毒化），请检查网络/镜像后重试" >&2
		return 1
	fi
	echo "[src_fetch] 校验通过: ${_dst}"
	return 0
}

# 内部：文件非空 + 能被 tar 列出 + （可选）顶层目录匹配
_yf_src_fetch_verify() {
	local _f=${1:-}
	local _want=${2:-}
	[ -s "${_f}" ] || return 1
	# gzip 先过一遍（HTML 错误页/截断包在这里被拦住）
	if ! gzip -t "${_f}" >/dev/null 2>&1; then
		return 1
	fi
	local _top
	_top=$(tar -tzf "${_f}" 2>/dev/null | head -n 1 | cut -d/ -f1)
	[ -n "${_top}" ] || return 1
	if [ -n "${_want}" ]; then
		case "${_top}" in
			"${_want}" | "${_want}/"*) : ;;
			*) return 1 ;;
		esac
	fi
	return 0
}
