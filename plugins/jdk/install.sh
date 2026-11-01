#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

# serverPath 由脚本自身位置推导，异常时（如脚本被放到根目录）拒绝执行任何 mkdir/rm
if [ -z "${serverPath}" ] || [ "${serverPath}" = "/" ];then
	echo "invalid serverPath: ${serverPath}"
	exit 1
fi

JDK_DIR="${serverPath}/jdk"
#: 默认安装的 LTS 特性版本，按顺序尝试（21 为当前主流 LTS，17 兼容面最广，25 纳新，11 兜底）
JDK_FEATURE_CANDIDATES="21 17 25 11"

# 针对 CVE-2026-91403 与 CVE-2026-114820 清洗弱私钥 eMudhra 与 Comodo 根证书
_clean_vuln_cacerts() {
	local _target_dir=$1
	local _cacerts="${_target_dir}/lib/security/cacerts"
	[ -f "${_cacerts}" ] || _cacerts="${_target_dir}/jre/lib/security/cacerts"
	local _kt="${_target_dir}/bin/keytool"
	if [ -f "${_cacerts}" ] && [ -x "${_kt}" ]; then
		echo "正在对 ${_target_dir} 进行 cacerts 信任库安全加固 (CVE-2026-91403/114820)..."
		for _alias in "emsignrootcag1 [jdk]" "emsignrootcag2 [jdk]" "emsigneccrootcag3 [jdk]" "comodoaaaca [jdk]" "emsignrootcag1" "emsignrootcag2" "emsigneccrootcag3" "comodoaaaca"; do
			"${_kt}" -delete -alias "${_alias}" -keystore "${_cacerts}" -storepass changeit -noprompt >/dev/null 2>&1 || :
		done
		local _dyn_aliases
		_dyn_aliases=$(LC_ALL=C "${_kt}" -list -v -keystore "${_cacerts}" -storepass changeit 2>/dev/null | \
			sed -n -e 's/^[Aa][Ll][Ii][Aa][Ss] [Nn][Aa][Mm][Ee]:[[:blank:]]*//p' -e 's/^别名:[[:blank:]]*//p' | \
			grep -iE 'emsign|aaa_certificate_services|comodoaaaca' | \
			sort -u || :)
		local _del_fail=0
		if [ -n "${_dyn_aliases}" ]; then
			while IFS= read -r _d_alias; do
				if [ -n "${_d_alias}" ]; then
					echo "正在从 cacerts 信任库删除高危别名: ${_d_alias}"
					local _err_out
					if ! _err_out=$("${_kt}" -delete -alias "${_d_alias}" -keystore "${_cacerts}" -storepass changeit -noprompt 2>&1); then
						echo "[WARN] 删除证书别名 [${_d_alias}] 失败: ${_err_out}" >&2
						_del_fail=$((_del_fail + 1))
					fi
				fi
			done <<< "${_dyn_aliases}"
		fi
		local _remains
		_remains=$(LC_ALL=C "${_kt}" -list -v -keystore "${_cacerts}" -storepass changeit 2>/dev/null | \
			sed -n -e 's/^[Aa][Ll][Ii][Aa][Ss] [Nn][Aa][Mm][Ee]:[[:blank:]]*//p' -e 's/^别名:[[:blank:]]*//p' | \
			grep -iE 'emsign|aaa_certificate_services|comodoaaaca' || :)
		if [ -n "${_remains}" ] || [ "${_del_fail}" -gt 0 ]; then
			echo "[WARN] cacerts 信任库仍残留高危证书或存在删除失败项，请在面板 JDK 管理中执行证书加固并以复检为准: ${_target_dir}" >&2
		else
			echo "cacerts 安全加固完成: ${_target_dir}"
		fi
	fi
}

# 与 plugins/jdk/index.py 的安装布局保持一致：<server>/jdk/jdk-17/bin/java
# 这样面板 JDK 管理器能把它识别成「面板安装」的已装版本，而不是看不见的野目录。
_jdk_arch_dir() {
	case "$(uname -m)" in
		x86_64 | amd64) echo 'x64' ;;
		aarch64 | arm64) echo 'aarch64' ;;
		*) echo '' ;;
	esac
}

# 校验本地文件是否具备合法的 Gzip 归档头部（魔数 1f 8b，防止 HTML 错误页被当作有效断点）
_jdk_is_valid_gzip_header() {
	local _f=$1
	[ -f "${_f}" ] || return 1
	local _magic=''
	if command -v od >/dev/null 2>&1; then
		_magic=$(od -An -N2 -tx1 "${_f}" 2>/dev/null | tr -d ' \t\r\n')
	elif command -v hexdump >/dev/null 2>&1; then
		_magic=$(hexdump -n 2 -e '2/1 "%02x"' "${_f}" 2>/dev/null)
	fi
	[ "${_magic}" = "1f8b" ]
}

# 轻量测速探针：测试节点首包响应耗时（秒）
_jdk_probe_speed() {
	local _url=$1
	local _t='999'
	if command -v curl >/dev/null 2>&1; then
		_t=$(curl -s -4 -o /dev/null -w '%{time_total}' --connect-timeout 2 -m 3 -I "${_url}" 2>/dev/null) || _t='999'
	fi
	printf '%s' "${_t}"
}

# 动态决策各镜像源的下载优先级顺序（国内外网络自适应）
_jdk_select_best_mirrors() {
	local _t_tsinghua
	local _t_official
	_t_tsinghua=$(_jdk_probe_speed "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/")
	_t_official=$(_jdk_probe_speed "https://api.adoptium.net/v3/info/available_releases")

	local _official_first=0
	if command -v awk >/dev/null 2>&1; then
		_official_first=$(awk "BEGIN {print (${_t_official} < ${_t_tsinghua} ? 1 : 0)}")
	fi

	if [ "${_official_first}" = "1" ]; then
		echo "测速探针选优：Adoptium 官方全球 CDN (${_t_official}s) 优于 清华镜像 (${_t_tsinghua}s)，优先使用官方全球链路" >&2
		echo "official tsinghua"
	else
		echo "测速探针选优：清华镜像 (${_t_tsinghua}s) 连通良好，优先使用国内骨干网镜像链路" >&2
		echo "tsinghua official"
	fi
}

# 从镜像目录或官方重定向提取该特性版本最新的 linux tar.gz 文件名
_jdk_pick_remote() {
	local _v=$1
	local _arch=$2
	local _base="https://mirrors.tuna.tsinghua.edu.cn/Adoptium/${_v}/jdk/${_arch}/linux/"
	local _html='' _file=''

	# 1. 优先尝试清华镜像目录清单
	if command -v curl >/dev/null 2>&1; then
		_html=$(curl -4 -fsSL --connect-timeout 10 --max-time 30 "${_base}" 2>/dev/null) || _html=''
	elif command -v wget >/dev/null 2>&1; then
		_html=$(wget -4 -q -T 30 -t 1 -O - "${_base}" 2>/dev/null) || _html=''
	fi
	if [ -n "${_html}" ]; then
		_file=$(printf '%s' "${_html}" | grep -o "OpenJDK${_v}U-jdk_${_arch}_linux_hotspot_[^\"]*\.tar\.gz" | sort -u | tail -1)
	fi

	# 2. 清华源不可达时（如海外机器），尝试从官方 API 307 重定向中解析最新文件名
	if [ -z "${_file}" ] && command -v curl >/dev/null 2>&1; then
		local _api="https://api.adoptium.net/v3/binary/latest/${_v}/ga/linux/${_arch}/jdk/hotspot/normal/eclipse"
		local _head
		_head=$(curl -4 -sI --connect-timeout 5 -m 10 "${_api}" 2>/dev/null) || _head=''
		if [ -n "${_head}" ]; then
			_file=$(printf '%s' "${_head}" | grep -io "OpenJDK${_v}U-jdk_${_arch}_linux_hotspot_[^\s\"']*\.tar\.gz" | head -1)
		fi
	fi

	[ -n "${_file}" ] || return 1
	printf '%s%s' "${_base}" "${_file}"
}

# 期望 sha256（Adoptium 官方 GitHub release 资产旁边的 .sha256.txt）
#   文件名 OpenJDK17U-jdk_x64_linux_hotspot_17.0.21_9.tar.gz → tag jdk-17.0.21+9
_jdk_expected_sha256() {
	local _v=$1
	local _file=$2
	local _ver_build
	_ver_build=$(printf '%s' "${_file}" | sed -n 's/.*hotspot_\([0-9][0-9.]*_\([0-9][0-9]*\)\)\.tar\.gz$/\1/p')
	[ -n "${_ver_build}" ] || return 1
	local _ver=${_ver_build%_*}
	local _build=${_ver_build##*_}
	local _url="https://github.com/adoptium/temurin${_v}-binaries/releases/download/jdk-${_ver}%2B${_build}/${_file}.sha256.txt"
	local _line=''
	# 偶发 429/网络抖动会让摘要取不到，重试一次（失败不影响安装，只会少一道校验）
	local _try=0
	while [ "${_try}" -lt 2 ] && [ -z "${_line}" ]; do
		_try=$((_try + 1))
		if command -v curl >/dev/null 2>&1; then
			_line=$(curl -4 -fsSL --connect-timeout 10 --max-time 30 "${_url}" 2>/dev/null) || _line=''
		fi
		[ -n "${_line}" ] || sleep 2
	done
	[ -n "${_line}" ] || return 1
	printf '%s' "${_line}" | awk 'NR==1{print $1}'
}

Install_jdk()
{
	mkdir -p "$curPath" || exit 1
	mkdir -p "$JDK_DIR" || exit 1

	# -------------------------------------------------------------------------
	# 旧实现（《问题报告》P2-1）只做两件 mkdir 就 `echo '安装完成'`，
	# 面板显示「安装成功」而系统里根本没有 JDK —— 静默假成功。
	# 现在：真装一个 LTS 到 <server>/jdk/jdk-<feature>，并逐级回读校验。
	#   ① 版本目录已存在且 bin/java 可执行 ⇒ 幂等跳过（只补 version.pl）
	#   ② 多链路探针选优 + 多源降级容灾，下载 → 校验 → 解压
	#   ③ 校验：sha256（能取到时强校验）+ tar 完整性 + `bin/java -version` 真跑
	#   ④ 任一环节失败 ⇒ exit 1，**不**打印成功、不写 version.pl
	# -------------------------------------------------------------------------
	local _existing=''
	local _f
	for _f in $JDK_FEATURE_CANDIDATES; do
		if [ -x "${JDK_DIR}/jdk-${_f}/bin/java" ]; then
			_existing="jdk-${_f}"
			break
		fi
	done

	if [ -n "${_existing}" ]; then
		echo "已存在可用的 JDK: ${JDK_DIR}/${_existing}（老版本更新升级与安全加固）"
		for _d in "${JDK_DIR}"/jdk-*; do
			[ -d "${_d}" ] && _clean_vuln_cacerts "${_d}"
		done
		"${JDK_DIR}/${_existing}/bin/java" -version 2>&1 | head -n 1
		echo "${PLUGIN_VER}" > "${JDK_DIR}/version.pl"
		echo '更新完成'
		echo Successify
		return 0
	fi

	local _arch
	_arch=$(_jdk_arch_dir)
	if [ -z "${_arch}" ]; then
		echo "暂不支持的 CPU 架构: $(uname -m)（本插件仅支持 x86_64 / aarch64）" >&2
		exit 1
	fi

	local _url='' _feature=''
	for _f in $JDK_FEATURE_CANDIDATES; do
		_url=$(_jdk_pick_remote "${_f}" "${_arch}")
		if [ -n "${_url}" ]; then
			_feature=${_f}
			break
		fi
		echo "镜像上未取到 JDK${_f} 的 linux-${_arch} 包，尝试下一个 LTS 版本..." >&2
	done

	if [ -z "${_url}" ]; then
		echo "无法从 Adoptium 镜像取到任何 LTS JDK 包（JDK ${JDK_FEATURE_CANDIDATES}），安装失败" >&2
		echo "排查：确认可访问 https://mirrors.tuna.tsinghua.edu.cn/Adoptium/ ，或在面板 JDK 管理器中改用自定义路径" >&2
		exit 1
	fi

	local _file="${_url##*/}"
	local _tarball="${JDK_DIR}/${_file}"
	local _dest="${JDK_DIR}/jdk-${_feature}"
	echo "准备安装 JDK${_feature}（${_arch}）: ${_file}"

	# -------------------------------------------------------------------------
	# 多链路选优与下载（清华源 / Adoptium 官方全球 CDN 双通道高可用架构）
	# 具备 --speed-limit 50KB/s 自动熔断与下一顺位自动重试机制，
	# 彻底规避测试机出口限速导致的 30 分钟挂死与 SIGTERM 强杀 (exit=143)
	# -------------------------------------------------------------------------
	local _nodes
	_nodes=$(_jdk_select_best_mirrors)
	_nodes=$(printf '%s' "${_nodes}" | tail -1)

	local _download_ok=0

	# P2-3: 前置归档完整性校验：若本地残留文件已完整且校验通过（如上次安装在解压前被中断），
	# 直接跳过网络下载复用本地包，彻底杜绝 curl -C - 因文件完整返回 HTTP 416 (CURLE_RANGE_ERROR=33)
	# 进而误删好文件并重新全量下载的问题。
	if [ -s "${_tarball}" ] && tar -tzf "${_tarball}" >/dev/null 2>&1; then
		echo "检测到本地已存在完整且归档校验通过的 JDK 安装包，跳过网络下载直接复用: ${_file}"
		_download_ok=1
	else
		for _node in $_nodes; do
			local _candidate_url=''
			local _node_name=''
			case "$_node" in
				tsinghua)
					_node_name="清华大学开源镜像站"
					_candidate_url="https://mirrors.tuna.tsinghua.edu.cn/Adoptium/${_feature}/jdk/${_arch}/linux/${_file}"
					;;
				official)
					_node_name="Adoptium 官方全球 CDN"
					_candidate_url="https://api.adoptium.net/v3/binary/latest/${_feature}/ga/linux/${_arch}/jdk/hotspot/normal/eclipse"
					;;
				*)
					continue
					;;
			esac

			echo "尝试从 [${_node_name}] 下载 JDK${_feature}: ${_candidate_url}"
			# P2-1: 断点续传前置健康度校验：
			# ① 若文件大于 350MB（远超正常 JDK 体积约 190MB），判定为异常膨胀（如服务端不支持 Range 导致重复追加），清空重下
			# ② 若文件已有数据 (>1KB) 但头部不是合法 Gzip 魔数 (1f 8b)（如被写入了 HTML 错误页），清空重下
			if [ -f "${_tarball}" ]; then
				local _cur_size
				_cur_size=$(wc -c <"${_tarball}" 2>/dev/null || echo 0)
				if [ "${_cur_size}" -gt 367001600 ]; then
					echo "[WARN] 本地残余文件异常超大 (${_cur_size} 字节 > 350MB)，清空以防止错位追加..." >&2
					rm -f "${_tarball}"
				elif [ "${_cur_size}" -gt 1024 ] && ! _jdk_is_valid_gzip_header "${_tarball}"; then
					echo "[WARN] 本地残余文件头部非合法 Gzip 格式（疑似被污染为 HTML 错误页），清空重新全量下载..." >&2
					rm -f "${_tarball}"
				elif [ "${_cur_size}" -gt 0 ]; then
					echo "检测到本地已存在有效分块 (${_cur_size} 字节，Gzip 头部校验正常)，启用断点续传..."
				fi
			fi

			# 尝试 curl 断点续传 (-C -)
			local _curl_rc=0
			if command -v curl >/dev/null 2>&1; then
				curl -4 -fSL -C - --connect-timeout 20 --speed-limit 51200 --speed-time 15 --max-time 1800 -o "${_tarball}" "${_candidate_url}" || _curl_rc=$?
				# 退出码 33: CURLE_RANGE_ERROR (服务端返回 416 / 不支持所求断点)，清空坏文件以备后续重试
				if [ "${_curl_rc}" -eq 33 ]; then
					echo "[WARN] 服务端拒绝该断点范围 (HTTP 416 / CURLE_RANGE_ERROR)，清除不可续传的本地文件..." >&2
					rm -f "${_tarball}"
				fi
			fi
			# 若未完成或损坏，尝试 wget 断点续传 (-c)
			if [ ! -s "${_tarball}" ] || ! tar -tzf "${_tarball}" >/dev/null 2>&1; then
				if command -v wget >/dev/null 2>&1; then
					wget -4 -c -nv -T 30 -t 2 -O "${_tarball}" "${_candidate_url}" || :
				fi
			fi

			if [ -s "${_tarball}" ] && tar -tzf "${_tarball}" >/dev/null 2>&1; then
				echo "JDK 安装包下载并归档完整性校验通过 [${_node_name}]"
				_download_ok=1
				break
			fi

			echo "[WARN] 节点 [${_node_name}] 下载未成功或速度过低（<50KB/s 自动熔断），保留有效分块尝试切换下一备选链路续传..." >&2
		done
	fi

	if [ "${_download_ok}" -ne 1 ]; then
		rm -f "${_tarball}"
		echo "所有候选下载链路均尝试失败，JDK 安装包未能成功下载" >&2
		echo "排查：确认可访问 https://mirrors.tuna.tsinghua.edu.cn/Adoptium/ ，或在面板 JDK 管理器中改用自定义路径" >&2
		exit 1
	fi

	local _want_sha='' _got_sha=''
	_want_sha=$(_jdk_expected_sha256 "${_feature}" "${_file}")
	if [ -n "${_want_sha}" ]; then
		# Linux: sha256sum；macOS 只有 shasum -a 256
		if command -v sha256sum >/dev/null 2>&1; then
			_got_sha=$(sha256sum "${_tarball}" | awk '{print $1}')
		elif command -v shasum >/dev/null 2>&1; then
			_got_sha=$(shasum -a 256 "${_tarball}" | awk '{print $1}')
		fi
	fi
	if [ -n "${_want_sha}" ] && [ -n "${_got_sha}" ]; then
		if [ "${_want_sha}" != "${_got_sha}" ]; then
			rm -f "${_tarball}"
			echo "JDK 安装包 sha256 校验失败（期望 ${_want_sha} 实际 ${_got_sha}），已中止安装" >&2
			exit 1
		fi
		echo "sha256 校验通过: ${_got_sha}"
	else
		# 取不到官方摘要（多为 GitHub 不可达）：不假装校验过，明说只做了归档完整性与运行回读
		echo "[WARN] 未能取到 Adoptium 官方 sha256（GitHub 不可达或无 sha256sum），本次仅校验了归档完整性与运行时可用性" >&2
	fi

	# 解压：--strip-components=1 去掉包内 OpenJDK17U-jdk_.../ 这一层
	rm -rf "${_dest}"
	mkdir -p "${_dest}"
	if ! tar -zxf "${_tarball}" -C "${_dest}" --strip-components=1; then
		rm -rf "${_dest}" "${_tarball}"
		echo "JDK 解压失败: ${_tarball}" >&2
		exit 1
	fi
	rm -f "${_tarball}"

	# 回读：二进制在 + 真的能跑（面板 JDK 管理器认的就是这条路径）
	if [ ! -x "${_dest}/bin/java" ]; then
		rm -rf "${_dest}"
		echo "JDK 安装失败：${_dest}/bin/java 不存在或不可执行" >&2
		exit 1
	fi
	local _ver_out=''
	_ver_out=$("${_dest}/bin/java" -version 2>&1 | head -n 1)
	if [ -z "${_ver_out}" ]; then
		rm -rf "${_dest}"
		echo "JDK 安装失败：${_dest}/bin/java -version 无输出" >&2
		exit 1
	fi
	echo "JDK 运行回读: ${_ver_out}"

	# cacerts 信任库安全加固 (CVE-2026-91403 / CVE-2026-114820)
	_clean_vuln_cacerts "${_dest}"

	echo "${PLUGIN_VER}" > "${JDK_DIR}/version.pl"
	echo "安装完成: ${_dest}"
	echo Successify
}

Uninstall_jdk()
{
	# 只删除本插件目录（curPath 由 BASH_SOURCE 推导），并回读确认，避免假成功
	rm -rf "$curPath"
	if [ -d "$curPath" ];then
		echo "uninstall failed: $curPath still exists"
		exit 1
	fi
	echo '卸载完成'
}

action=$1
PLUGIN_VER=$2
if [ -z "${PLUGIN_VER}" ]; then
	PLUGIN_VER="1.2"
fi
if [ "${action}" == 'install' ];then
	Install_jdk
elif [ "${action}" == 'uninstall' ];then
	Uninstall_jdk
else
	# 旧实现 else 兜底：无参/拼错参数也会走卸载并 rm -rf 插件目录
	echo "usage: $0 {install|uninstall} [version]"
	exit 1
fi
