#!/bin/bash
# ---------------------------------------------------------------------------------
# OpenResty 构建配方（**唯一真源**）—— 供 versions/<版本>/install.sh 薄封装调用
#
# 为什么要有这个文件：
#   历史上每个 versions/<ver>/install.sh 都是一份 300 行的完整拷贝，只有 VERSION
#   与 `1.31.1` 那个硬编码分支不同。上游每发一版就要复制一份 → 修一处配置（安全
#   相关）必须记得同步到 7 份拷贝里，实测已经漏过。把配方收敛到这里后：
#     * versions/1.31.1/install.sh 与 versions/1.31.9.1/install.sh 只剩版本号两行；
#     * 「御风软件版本在线同步」（scripts/version_sync.py + web/core/
#       openresty_release_index.py）可以按同一模板**自动生成**新版本的薄封装，
#       上游发版后不必等面板重新发版就能装/升到最新。
#
# 调用约定（由薄封装在 source 前设置）：
#   YF_OPENRESTY_VERSION  完整上游版本号，如 1.31.9.1（源码包 openresty-1.31.9.1.tar.gz）
#   YF_OPENRESTY_SERIES   中间件目录名（versions/<dir>），一般等于 VERSION；
#                         历史目录 1.31.1 的 VERSION 是 1.31.1.1，SERIES 才是 1.31.1
#
# 退出码：任何一步失败都 exit 非 0（面板按退出码判定安装结果，见 2026-10-28 假成功收紧）
# ---------------------------------------------------------------------------------

if [ -z "${BASH_VERSION:-}" ]; then
	# 被 `sh -x` 调用时（Debian 的 /bin/sh 是 dash，不认 [[ ]] 与 source）切回 bash 自己
	exec bash "$0" "$@"
fi

YF_OPENRESTY_VERSION="${YF_OPENRESTY_VERSION:-}"
YF_OPENRESTY_SERIES="${YF_OPENRESTY_SERIES:-${YF_OPENRESTY_VERSION}}"
if [ -z "${YF_OPENRESTY_VERSION}" ]; then
	echo "[ERROR] openresty_build.sh: 未设置 YF_OPENRESTY_VERSION（应由 versions/<ver>/install.sh 提供）" >&2
	exit 1
fi

PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

# 路径一律按**脚本自身位置**解析，不依赖 `pwd`：面板以 `cd <插件目录> && bash install.sh`
# 调用，但运维手工 `bash versions/1.31.9.1/install.sh install` 时 cwd 是随机的。
#
# 目录层级必须与面板一致（`yf.getServerDir()` 是面板根目录的**上一级**）：
#   <serverPath>/openresty           ← 面板识别的安装根（version.pl / nginx/sbin/nginx）
#   <serverPath>/source/openresty    ← 源码/依赖缓存
#   <YF_PANEL_DIR>/scripts/…         ← 面板自带的下载/编译辅助库
# 注：2026-11-27 曾在这里少算一层（把面板根当成 serverPath），导致二进制装到
# `<面板根>/openresty` 而面板仍去看 `<serverPath>/openresty` —— 升级后「显示已升级、
# 实际还是旧二进制」，且启动用的是旧二进制。已修正，并加了下方的冒充检查。
_build_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)      # .../versions/common
_versions_dir=$(dirname "${_build_dir}")                      # .../versions
_plugin_dir=$(dirname "${_versions_dir}")                      # .../openresty
_plugins_dir=$(dirname "${_plugin_dir}")                        # .../plugins
YF_PANEL_DIR=$(dirname "${_plugins_dir}")                      # 面板根目录（.../yufeng_panel）
rootPath=${YF_PANEL_DIR}                                       # 与原版本脚本同名
serverPath=$(dirname "${YF_PANEL_DIR}")                        # 面板的 server 根（/www/server）
curPath=${_plugin_dir}

# make 并发自适应（1C512M 机器 -j1），与面板其它插件同一套
for _yf_jobs_lib in "${YF_PANEL_DIR}/scripts/lib_make_jobs.sh" \
                    "/www/server/yufeng_panel/scripts/lib_make_jobs.sh"; do
	if [ -f "${_yf_jobs_lib}" ]; then
		. "${_yf_jobs_lib}"
		break
	fi
done

# 统一的 GitHub 下载函数库（镜像节点 / 重试 / 校验）
for _gh_lib in "${YF_PANEL_DIR}/scripts/github_download.sh" \
               "/www/server/yufeng_panel/scripts/github_download.sh"; do
	if [ -f "${_gh_lib}" ]; then
		. "${_gh_lib}"
		break
	fi
done

# 附加模块获取器（下载 → gzip 完整性 → 解压 → 标记文件校验，失败清理重试）
if [ ! -f "${_build_dir}/nginx_addon_fetch.sh" ]; then
	echo "[ERROR] 缺少附加模块获取器 nginx_addon_fetch.sh，停止安装（避免残缺模块进 configure）" >&2
	exit 1
fi
. "${_build_dir}/nginx_addon_fetch.sh"
if ! command -v yf_nginx_addon_fetch >/dev/null 2>&1; then
	echo "[ERROR] nginx_addon_fetch.sh 未提供 yf_nginx_addon_fetch，停止安装" >&2
	exit 1
fi

# 核心源码包获取器
if [ ! -f "${_build_dir}/openresty_src_fetch.sh" ]; then
	echo "[ERROR] 缺少源码获取器 openresty_src_fetch.sh，停止安装" >&2
	exit 1
fi
. "${_build_dir}/openresty_src_fetch.sh"
if ! command -v yf_openresty_src_fetch >/dev/null 2>&1; then
	echo "[ERROR] openresty_src_fetch.sh 未提供 yf_openresty_src_fetch，停止安装" >&2
	exit 1
fi

sysName=$(uname)
action=${1:-}
type=${2:-}
VERSION=${YF_OPENRESTY_VERSION}
SERIES=${YF_OPENRESTY_SERIES}

openrestyDir=${serverPath}/source/openresty

# 版本号数值比较：_yf_ver_ge <a> <b> → a >= b ? 0 : 1
_yf_ver_ge() {
	local _a=$1 _b=$2
	local _i _x _y
	for _i in 1 2 3 4 5; do
		_x=$(echo "${_a}" | cut -d. -f${_i})
		_y=$(echo "${_b}" | cut -d. -f${_i})
		[ -z "${_x}" ] && _x=0
		[ -z "${_y}" ] && _y=0
		_x=$((10#${_x}))
		_y=$((10#${_y}))
		if [ "${_x}" -gt "${_y}" ]; then
			return 0
		fi
		if [ "${_x}" -lt "${_y}" ]; then
			return 1
		fi
	done
	return 0
}

# 校验「已装二进制」是否真的对应当前目标版本。
# 防的是这类历史事故：version.pl 被写成 1.31.9.1，但 nginx/sbin/nginx 还是旧的
# 1.31.1（例如上次装错目录 / 编译失败却写了版本号）——只看 version.pl 会误判“已安装”
# 并直接 exit 0，导致面板永远修不好。`nginx -v` 形如 `nginx version: openresty/1.31.9.1`。
_yf_openresty_bin_matches() {
	local _bin="${serverPath}/openresty/nginx/sbin/nginx"
	[ -x "${_bin}" ] || return 1
	local _out
	_out=$("${_bin}" -v 2>&1)
	case "${_out}" in
		*"${VERSION}"*) return 0 ;;
	esac
	case "${_out}" in
		*"${SERIES}"*) return 0 ;;
	esac
	return 1
}

Install_openresty()
{
	# 历史误装警告：曾把安装根算成面板根（<面板>/openresty），那份目录面板不会使用。
	if [ "${YF_PANEL_DIR}" != "${serverPath}" ] && [ -d "${YF_PANEL_DIR}/openresty/nginx/sbin" ]; then
		echo "[WARN] 检测到历史误装的 OpenResty 目录（面板不会使用）: ${YF_PANEL_DIR}/openresty" >&2
		echo "[WARN] 确认本次安装正常后，可手工删除该目录释放空间" >&2
	fi

	if [ "${action}" == "install" ]; then
		if [ -d "$serverPath/openresty" ] && [ -f "$serverPath/openresty/version.pl" ]; then
			CURRENT_VERSION=$(cat "$serverPath/openresty/version.pl" 2>/dev/null)
			# 已是同一版本（完整号，或历史版本脚本只写了三段号）→ 还要复核二进制
			if [ "${CURRENT_VERSION}" == "${VERSION}" ] || [ "${CURRENT_VERSION}" == "${SERIES}" ]; then
				if _yf_openresty_bin_matches; then
					echo "OpenResty ${VERSION} is already installed."
					exit 0
				fi
				echo "[WARN] version.pl 记录 ${CURRENT_VERSION}，但 nginx 二进制版本不匹配，重新编译安装" >&2
			fi
		fi
	fi

	# ----- cpu start ------
	if [ -z "${cpuCore}" ]; then
		cpuCore="1"
	fi

	if [ -f /proc/cpuinfo ]; then
		cpuCore=$(grep "processor" /proc/cpuinfo | wc -l)
	fi

	MEM_INFO=$(LC_ALL=C free -m | grep Mem | awk '{printf("%.f",($2)/1024)}')
	if [ "${cpuCore}" != "1" ] && [ "${MEM_INFO}" != "0" ]; then
		limitCore=$((MEM_INFO * 2))
		if [ "${limitCore}" -lt "1" ]; then
			limitCore="1"
		fi
		if [ "${cpuCore}" -gt "${limitCore}" ]; then
			cpuCore="${limitCore}"
		fi
	else
		cpuCore="1"
	fi

	if [ "${cpuCore}" -lt "1" ]; then
		cpuCore="1"
	fi
	# ----- cpu end ------

	# --- yf adaptive clamp (1C512M -> -j1) ---
	if command -v yf_make_jobs >/dev/null 2>&1; then
		_yf_jobs=$(yf_make_jobs 2>/dev/null || echo "")
		if [ -n "${_yf_jobs}" ] && [ "${_yf_jobs}" -ge 1 ] 2>/dev/null; then
			cpuCore="${_yf_jobs}"
		fi
	fi

	# 强力停止并清退所有旧的 nginx/openresty 进程，杜绝 80 端口占用或 Text file busy 故障
	if [ -f /usr/lib/systemd/system/openresty.service ] || [ -f /lib/systemd/system/openresty.service ]; then
		systemctl stop openresty
	fi
	if [ -f "$serverPath/openresty/init.d/openresty" ]; then
		"$serverPath/openresty/init.d/openresty" stop
	fi
	killall -9 nginx 2>/dev/null
	killall -9 openresty 2>/dev/null
	pkill -9 nginx 2>/dev/null
	pkill -9 openresty 2>/dev/null

	mkdir -p "${openrestyDir}"
	echo '正在安装脚本文件...'

	if ! yf_openresty_src_fetch "${openrestyDir}" "${VERSION}"; then
		echo "[ERROR] OpenResty 核心源码包获取或校验失败，停止安装" >&2
		exit 1
	fi

	OPTIONS=''

	opensslVersion="3.5.5"
	pcreVersion='8.45'
	if [ "$sysName" == "Darwin" ]; then
		if [ ! -f "${openrestyDir}/pcre-${pcreVersion}.tar.gz" ]; then
			wget -nv --no-check-certificate -O "${openrestyDir}/pcre-${pcreVersion}.tar.gz" https://netix.dl.sourceforge.net/project/pcre/pcre/${pcreVersion}/pcre-${pcreVersion}.tar.gz
		fi

		if [ ! -d "${openrestyDir}/pcre-${pcreVersion}" ]; then
			cd "${openrestyDir}" && tar -zxf "pcre-${pcreVersion}.tar.gz"
		fi
		OPTIONS="${OPTIONS} --with-pcre=${openrestyDir}/pcre-${pcreVersion}"

		if [ ! -f "${openrestyDir}/openssl-${opensslVersion}.tar.gz" ]; then
			github_download "${openrestyDir}/openssl-${opensslVersion}.tar.gz" "https://github.com/openssl/openssl/releases/download/openssl-${opensslVersion}/openssl-${opensslVersion}.tar.gz"
		fi

		if [ ! -d "${openrestyDir}/openssl-${opensslVersion}" ]; then
			cd "${openrestyDir}" && tar -zxf "openssl-${opensslVersion}.tar.gz"
		fi
		OPTIONS="${OPTIONS} --with-openssl=${openrestyDir}/openssl-${opensslVersion}"
	else
		if [ ! -f "${openrestyDir}/openssl-${opensslVersion}.tar.gz" ]; then
			github_download "${openrestyDir}/openssl-${opensslVersion}.tar.gz" "https://github.com/openssl/openssl/releases/download/openssl-${opensslVersion}/openssl-${opensslVersion}.tar.gz"
		fi

		if [ ! -d "${openrestyDir}/openssl-${opensslVersion}" ]; then
			cd "${openrestyDir}" && tar -zxf "openssl-${opensslVersion}.tar.gz"
		fi
		OPTIONS="${OPTIONS} --with-openssl=${openrestyDir}/openssl-${opensslVersion}"
	fi

	# HTTP/3 从 1.31.1 起提供：按数值比较判定，新版本（1.31.9.1 / 1.32.x …）自动继承，
	# 不再像旧脚本那样把 "1.31.1" 硬编码进 [[ =~ ]]（新版本会漏掉这个模块）。
	if _yf_ver_ge "${VERSION}" "1.31.1"; then
		OPTIONS="${OPTIONS} --with-http_v3_module"
	fi

	# jemalloc
	jemallocVersion="5.3.0"
	ARM_CHECK=$(uname -a | grep -E 'aarch64|arm|ARM')
	if [ -z "${ARM_CHECK}" ] && [ "$sysName" != "Darwin" ]; then
		if [ ! -f '/usr/local/lib/libjemalloc.so' ] && [ ! -f '/usr/lib/libjemalloc.so' ] && [ ! -f '/usr/lib64/libjemalloc.so' ]; then
			if [ ! -f "${openrestyDir}/jemalloc-${jemallocVersion}.tar.bz2" ]; then
				github_download "${openrestyDir}/jemalloc-${jemallocVersion}.tar.bz2" "https://github.com/jemalloc/jemalloc/releases/download/${jemallocVersion}/jemalloc-${jemallocVersion}.tar.bz2"
			fi
			if [ ! -d "${openrestyDir}/jemalloc-${jemallocVersion}" ]; then
				cd "${openrestyDir}" && tar -xvf "jemalloc-${jemallocVersion}.tar.bz2"
				cd "jemalloc-${jemallocVersion}"
				./configure
				CMD_MAKE=$(which gmake)
				if [ "$?" == "0" ]; then
					gmake -j"${cpuCore}" && gmake install
				else
					make -j"${cpuCore}" && make install
				fi
				ldconfig
			fi
		fi
		if [ -f '/usr/local/lib/libjemalloc.so' ] || [ -f '/usr/lib/libjemalloc.so' ] || [ -f '/usr/lib64/libjemalloc.so' ]; then
			OPTIONS="${OPTIONS} --with-ld-opt=-ljemalloc"
		fi
	fi

	# ngx_cache_purge：下载/解压/标记文件三段校验，失败清理重试
	if ! yf_nginx_addon_fetch "${openrestyDir}" ngx_cache_purge-master \
		"https://github.com/nginx-modules/ngx_cache_purge/archive/refs/heads/master.tar.gz" config \
		"https://github.com/nginx-modules/ngx_cache_purge.git"; then
		exit 1
	fi
	OPTIONS="${OPTIONS} --add-module=${openrestyDir}/ngx_cache_purge-master"

	# nginx-http-concat
	if ! yf_nginx_addon_fetch "${openrestyDir}" nginx-http-concat-master \
		"https://github.com/alibaba/nginx-http-concat/archive/refs/heads/master.tar.gz" config \
		"https://github.com/alibaba/nginx-http-concat.git"; then
		exit 1
	fi
	OPTIONS="${OPTIONS} --add-module=${openrestyDir}/nginx-http-concat-master"

	# ngx_http_substitutions_filter_module
	if ! yf_nginx_addon_fetch "${openrestyDir}" ngx_http_substitutions_filter_module-master \
		"https://github.com/yaoweibin/ngx_http_substitutions_filter_module/archive/refs/heads/master.tar.gz" config \
		"https://github.com/yaoweibin/ngx_http_substitutions_filter_module.git"; then
		exit 1
	fi
	OPTIONS="${OPTIONS} --add-module=${openrestyDir}/ngx_http_substitutions_filter_module-master"

	# br
	if [ ! -d "${openrestyDir}/ngx_brotli/deps/brotli/c" ]; then
		rm -rf "${openrestyDir}/ngx_brotli"
		github_clone "${openrestyDir}/ngx_brotli" https://github.com/wxx9248/ngx_brotli.git

		mkdir -p "${openrestyDir}/ngx_brotli/deps/brotli"
		github_download "${openrestyDir}/ngx_brotli/deps/brotli.tar.gz" https://github.com/google/brotli/archive/refs/tags/v1.1.0.tar.gz
		if [ "$?" == "0" ]; then
			cd "${openrestyDir}/ngx_brotli/deps" && tar -zxf brotli.tar.gz -C brotli --strip-components=1
			rm -f brotli.tar.gz
		else
			cd "${openrestyDir}/ngx_brotli" && github_clone deps/brotli https://github.com/google/brotli.git
		fi
	fi

	if [ ! -d "${openrestyDir}/ngx_brotli/deps/brotli/c" ]; then
		echo "Error: Brotli library is missing from the ngx_brotli/deps/brotli/c directory!" >&2
		exit 1
	fi
	OPTIONS="${OPTIONS} --add-module=${openrestyDir}/ngx_brotli"

	OPTIONS="${OPTIONS} --with-threads"
	OPTIONS="${OPTIONS} --with-file-aio"
	OPTIONS="${OPTIONS} --with-pcre-jit"
	OPTIONS="${OPTIONS} --with-http_gzip_static_module"

	# zstd
	if [ ! -d "${openrestyDir}/zstd-nginx-module-master" ]; then
		github_download "${openrestyDir}/zstd-nginx-module.tar.gz" https://github.com/tokers/zstd-nginx-module/archive/refs/heads/master.tar.gz
		cd "${openrestyDir}" && tar -zxf zstd-nginx-module.tar.gz
	fi

	pkg-config --exists --print-errors libzstd
	if [ "$?" == "0" ]; then
		OPTIONS="${OPTIONS} --add-module=${openrestyDir}/zstd-nginx-module-master"
	fi

	cd "${openrestyDir}/openresty-${VERSION}" && ./configure \
	--prefix="$serverPath/openresty" \
	$OPTIONS \
	--with-stream \
	--with-http_v2_module \
	--with-http_ssl_module  \
	--with-http_slice_module \
	--with-http_stub_status_module \
	--with-http_sub_module \
	--with-http_realip_module

	if [ "$?" != "0" ]; then
		echo "Configure failed!" >&2
		exit 1
	fi

	# 修复 OpenSSL 3.x 编译兼容问题：
	# OpenResty 生成的 objs/Makefile 会对 OpenSSL 源码执行 "gmake clean"，
	# 但 OpenSSL 3.x 的 clean 目标会删除 util/perl/OpenSSL/fallback.pm，
	# 导致后续 ./config 因找不到该 Perl 模块而失败。
	# 解决方案：将 Makefile 中针对 OpenSSL 的 "gmake clean" 替换为无操作(true)。
	OBJS_MAKEFILE="${openrestyDir}/openresty-${VERSION}/build/nginx-*/objs/Makefile"
	for _mf in ${OBJS_MAKEFILE}; do
		if [ -f "$_mf" ]; then
			sed -i 's/\&\& if \[ -f Makefile \]; then $(MAKE) clean; fi \\/\&\& if [ -f Makefile ]; then true; fi \\/g' "$_mf"
		fi
	done

	# 避免正在运行的二进制导致 Text file busy 无法覆盖
	if [ -f "$serverPath/openresty/nginx/sbin/nginx" ]; then
		mv -f "$serverPath/openresty/nginx/sbin/nginx" "$serverPath/openresty/nginx/sbin/nginx.bak"
	fi
	if [ -f "$serverPath/openresty/bin/openresty" ]; then
		mv -f "$serverPath/openresty/bin/openresty" "$serverPath/openresty/bin/openresty.bak"
	fi

	# 清理临时构建目录（正常完成或中途失败/爆盘中断均自动触发，避免数 GB 源码残留）
	_yf_cleanup_build_dirs() {
		local _d
		for _d in \
			"${openrestyDir}/pcre-${pcreVersion}" \
			"${openrestyDir}/openssl-${opensslVersion}" \
			"${openrestyDir}/jemalloc-${jemallocVersion}" \
			"${openrestyDir}/ngx_cache_purge-master" \
			"${openrestyDir}/nginx-http-concat-master" \
			"${openrestyDir}/ngx_http_substitutions_filter_module-master" \
			"${openrestyDir}/openresty-${VERSION}" \
			"${openrestyDir}/zstd-nginx-module-master"; do
			if [ -n "${_d}" ] && [ -d "${_d}" ]; then
				rm -rf "${_d}" 2>/dev/null
			fi
		done
	}
	trap _yf_cleanup_build_dirs EXIT

	CMD_MAKE=$(which gmake)
	if [ "$?" == "0" ]; then
		gmake -j"${cpuCore}" && gmake install && gmake clean
	else
		make -j"${cpuCore}" && make install && make clean
	fi
	if [ "$?" != "0" ]; then
		echo "Build failed!" >&2
		exit 1
	fi

	_yf_cleanup_build_dirs
	trap - EXIT

	# 写完整上游版本号（1.31.9.1）。外层 install.sh 看到它以 SERIES 开头就不会覆盖成
	# 目录名 —— 否则 1.31.1.1 与 1.31.1.2 会同样落成 "1.31.1"，面板永远看不出补丁差。
	mkdir -p "$serverPath/openresty"
	echo "${VERSION}" > "$serverPath/openresty/version.pl"

	echo 'Installation of Openresty completed'
}

Uninstall_openresty()
{
	echo 'Uninstalling Openresty completed'
}

if [ "${action}" == "install" ]; then
	Install_openresty
elif [ "${action}" == "upgrade" ]; then
	Install_openresty
else
	Uninstall_openresty
fi
