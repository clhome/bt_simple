#!/bin/bash
# ---------------------------------------------------------------------------------
# OpenResty 核心源码包高可用获取器
#
# 解决原脚本痛点：
#   1. 原 `wget -T 3` 短超时导致跨国连接/弱网下极易握手失败，留下 0 字节损坏包；
#   2. 备用中科大镜像已全线 404，导致回退死路；
#   3. 解压失败不熔断，导致随后 git clone 自动建出空的父目录，最终在
#      `./configure` 时报 "No such file or directory"；
#   4. 缺少大小与 gzip 完整性强校验，导致 HTML 错误页直接进入解压流程。
# ---------------------------------------------------------------------------------

yf_openresty_src_fetch() {
	local _dir=$1
	local _ver=$2
	local _target_dir="${_dir}/openresty-${_ver}"
	local _tarball="${_dir}/openresty-${_ver}.tar.gz"

	# 1. 幂等检查：若完整目录已存在且包含 ./configure，直接就绪返回
	if [ -f "${_target_dir}/configure" ]; then
		return 0
	fi

	# 2. 坏目录防毒化：目录存在但缺少 configure（上次失败遗留或被子模块 git clone 建出的假目录）
	if [ -d "${_target_dir}" ]; then
		echo "[openresty][WARN] 检测到残缺源码目录（缺少 configure），清理重建: ${_target_dir}"
		rm -rf "${_target_dir}"
	fi

	mkdir -p "${_dir}"

	# 3. 压缩包有效性判定函数（非空 + 体积 > 1MB + gzip 测试通过）
	_is_valid_tarball() {
		local _f=$1
		if [ ! -s "${_f}" ]; then
			return 1
		fi
		# 正常 openresty 源码包体积在 4MB~6MB，< 1MB 多为 HTML 404/错误页
		local _size
		if command -v stat >/dev/null 2>&1; then
			_size=$(stat -c%s "${_f}" 2>/dev/null || stat -f%z "${_f}" 2>/dev/null || echo 0)
		else
			_size=$(wc -c < "${_f}" 2>/dev/null || echo 0)
		fi
		if [ "${_size:-0}" -lt 1000000 ]; then
			return 1
		fi
		gzip -t "${_f}" 2>/dev/null
	}

	# 4. 若已有压缩包损坏，彻底清理
	if [ -f "${_tarball}" ] && ! _is_valid_tarball "${_tarball}"; then
		echo "[openresty][WARN] 现存压缩包损坏或为错误页，删除重新获取: ${_tarball}"
		rm -f "${_tarball}"
	fi

	# 5. 若无有效包，执行双通道高可用下载（官方源 + GitHub 官方 Release）
	if [ ! -f "${_tarball}" ]; then
		local _urls=(
			"https://openresty.org/download/openresty-${_ver}.tar.gz"
			"https://github.com/openresty/openresty/releases/download/v${_ver}/openresty-${_ver}.tar.gz"
		)
		local _downloaded=0

		for _u in "${_urls[@]}"; do
			echo "[openresty] 正在尝试下载源码包: ${_u}"
			rm -f "${_tarball}" 2>/dev/null

			# 优先支持 github_download（若为 GitHub 链接可利用镜像节点加速）
			if [[ "$_u" == https://github.com* ]] && command -v github_download >/dev/null 2>&1; then
				github_download "${_tarball}" "${_u}" 60
			elif command -v curl >/dev/null 2>&1; then
				curl -fsSL --connect-timeout 20 --max-time 300 --retry 2 -o "${_tarball}" "${_u}" || rm -f "${_tarball}"
			fi

			if [ ! -s "${_tarball}" ] && command -v wget >/dev/null 2>&1; then
				wget -nv --no-check-certificate --timeout=30 --tries=2 -O "${_tarball}" "${_u}" || rm -f "${_tarball}"
			fi

			if _is_valid_tarball "${_tarball}"; then
				echo "[openresty][OK] 源码包下载成功并通过完整性校验: ${_tarball}"
				_downloaded=1
				break
			else
				echo "[openresty][WARN] 该源下载失败或包损坏: ${_u}"
				rm -f "${_tarball}" 2>/dev/null
			fi
		done

		if [ "$_downloaded" -ne 1 ]; then
			echo "[openresty][ERROR] 所有下载通道均未获取到可用的 openresty-${_ver}.tar.gz" >&2
			return 1
		fi
	fi

	# 6. 解压并校验
	echo "[openresty] 正在解压源码包: ${_tarball} -> ${_dir}"
	rm -rf "${_target_dir}" 2>/dev/null
	tar -zxf "${_tarball}" -C "${_dir}"
	if [ "$?" -ne 0 ] || [ ! -f "${_target_dir}/configure" ]; then
		echo "[openresty][ERROR] 解压失败或源码目录缺失 configure: ${_target_dir}" >&2
		rm -rf "${_target_dir}" 2>/dev/null
		rm -f "${_tarball}" 2>/dev/null
		return 1
	fi

	echo "[openresty][OK] 源码就绪: ${_target_dir}"
	return 0
}

