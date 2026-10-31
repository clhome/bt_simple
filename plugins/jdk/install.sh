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

# 从镜像目录清单里取该特性版本最新的 linux tar.gz 文件名（镜像内容会随上游滚动，
# 写死 `OpenJDK17U-jdk_x64_linux_hotspot_17.0.19_10.tar.gz` 这种全量文件名必然 404 ——
# 真机实测 index.py 里那三条默认 URL 现在全是 404）。
_jdk_pick_remote() {
	local _v=$1
	local _arch=$2
	local _base="https://mirrors.tuna.tsinghua.edu.cn/Adoptium/${_v}/jdk/${_arch}/linux/"
	local _html=''
	if command -v curl >/dev/null 2>&1; then
		_html=$(curl -fsSL --connect-timeout 15 --max-time 60 "${_base}" 2>/dev/null) || _html=''
	elif command -v wget >/dev/null 2>&1; then
		_html=$(wget -q -T 60 -t 1 -O - "${_base}" 2>/dev/null) || _html=''
	fi
	[ -n "${_html}" ] || return 1
	local _file
	_file=$(printf '%s' "${_html}" | grep -o "OpenJDK${_v}U-jdk_${_arch}_linux_hotspot_[^\"]*\.tar\.gz" | sort -u | tail -1)
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
			_line=$(curl -fsSL --connect-timeout 10 --max-time 30 "${_url}" 2>/dev/null) || _line=''
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
	#   ② 从镜像清单现取最新包（不写死文件名），下载 → 校验 → 解压
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
	echo "开始安装 JDK${_feature}（${_arch}）: ${_url}"

	# 0 字节 / 错误页毒化：先删再下，下完立刻验
	rm -f "${_tarball}"
	if command -v curl >/dev/null 2>&1; then
		curl -fSL --connect-timeout 20 --max-time 1800 -o "${_tarball}" "${_url}" || rm -f "${_tarball}"
	fi
	if [ ! -s "${_tarball}" ] && command -v wget >/dev/null 2>&1; then
		wget -nv -T 300 -t 2 -O "${_tarball}" "${_url}" || rm -f "${_tarball}"
	fi
	if [ ! -s "${_tarball}" ] || ! tar -tzf "${_tarball}" >/dev/null 2>&1; then
		rm -f "${_tarball}"
		echo "JDK 安装包下载失败或已损坏: ${_url}" >&2
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
