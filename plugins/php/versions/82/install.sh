#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH=$PATH:/opt/homebrew/bin

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(cd "$curPath/../../../.."; pwd)
serverPath=$(dirname "$rootPath")
sourcePath=${serverPath}/source
sysName=`uname`

if [ -f "${rootPath}/scripts/lib_make_jobs.sh" ]; then
	source "${rootPath}/scripts/lib_make_jobs.sh"
elif [ -f /www/server/yufeng_panel/scripts/lib_make_jobs.sh ]; then
	source /www/server/yufeng_panel/scripts/lib_make_jobs.sh
fi

# P0-2 判存守卫：读完整版本号再判（本文件两道判存都依赖它）。
# 加载不到就直接停止 —— 没有判定函数就等于回到「目录存在即跳过」的假成功。
for _yf_guard in "${rootPath}/plugins/php/versions/common/php_ver_guard.sh" \
	"/www/server/yufeng_panel/plugins/php/versions/common/php_ver_guard.sh"; do
	if [ -f "$_yf_guard" ]; then
		. "$_yf_guard"
		break
	fi
done
if ! command -v yf_php_install_needs_build >/dev/null 2>&1; then
	echo "[ERROR] 缺少判存守卫 php_ver_guard.sh，无法校验已装版本，停止安装以避免假成功。"
	exit 1
fi

# 源码包获取器（多镜像 / 劫持检测 / sha256 强校验 / 离线包）：与判存守卫同一个 common 目录。
for _yf_src_lib in "${rootPath}/plugins/php/versions/common/php_src_fetch.sh" \
	"/www/server/yufeng_panel/plugins/php/versions/common/php_src_fetch.sh"; do
	if [ -f "$_yf_src_lib" ]; then
		. "$_yf_src_lib"
		break
	fi
done
if ! command -v yf_php_fetch_source >/dev/null 2>&1; then
	echo "[ERROR] 缺少源码包获取器 php_src_fetch.sh，无法安全下载源码，停止安装。"
	exit 1
fi

# CVE-2026-109618/109619（php2shell）修复基线：8.2 分支不得低于 8.2.35
# 哈希口径是官方 php-<version>.tar.xz 的 sha256（不是 md5），取值来源
# https://www.php.net/releases/index.php?json&version=<分支>&max=1 （2026-10-22 取，<分支>=8.2；禁止凭记忆或第三方镜像抄值）
version=8.2.35
PHP_VER=82
sha256_file_ok=5737b98601fe5ab1b8c5db0c82ed3158acb9283ed3081ffe2faffb9ac81455e6

# ---------------------------------------------------------------------------------
# 目标版本覆盖（面板「自动获取最新版本」下发）
#
# 面板会定期抓 php.net 官方发布索引，某分支出了新补丁版时，升级任务需要装**新版**
# 而不是本文件里写死的发布时版本。下发的两个值都做严格校验：
#   * 版本必须是 x.y.z 且属于本分支（`83` 只接受 8.3.x）；
#   * 必须同时给出 64 位十六进制的官方 sha256 —— 只给版本不给哈希等于关掉完整性校验。
# 任一不合法就**忽略覆盖**并用文件内的固定值（宁可装旧版，也不装来路不明的包）。
# 也可由运维手工写入本目录下的 version.auto（同样格式，供下次安装/重装沿用）。
# ---------------------------------------------------------------------------------
_yf_pin_version="${version}"
_yf_pin_sha256="${sha256_file_ok}"
if [ -f "${curPath}/version.auto" ]; then
	# shellcheck disable=SC1090
	. "${curPath}/version.auto" >/dev/null 2>&1
fi
_yf_target_version="${YF_PHP_TARGET_VERSION:-${version}}"
_yf_target_sha256="${YF_PHP_TARGET_SHA256:-${sha256_file_ok}}"
_yf_target_sha256=$(echo "${_yf_target_sha256}" | tr 'A-Z' 'a-z')
_yf_target_series="${PHP_VER:0:1}.${PHP_VER:1:1}"
if echo "${_yf_target_version}" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' \
	&& echo "${_yf_target_version}" | grep -Eq "^${_yf_target_series}\." \
	&& echo "${_yf_target_sha256}" | grep -Eq '^[0-9a-f]{64}$'; then
	version="${_yf_target_version}"
	sha256_file_ok="${_yf_target_sha256}"
else
	echo "[WARN] 下发的目标版本/哈希不合法（version='${_yf_target_version}' sha256='${_yf_target_sha256}'），改用内置版本 ${_yf_pin_version}"
fi
if [ "${version}" != "${_yf_pin_version}" ]; then
	echo "[INFO] 本次安装目标版本: ${version}（内置版本 ${_yf_pin_version}）"
fi
# P0-2（已完成）：下面两道判存都改成「比对完整版本号」，所以只改 version= 也能对
# 存量机器生效：
#   ① 源码层比对 main/php_version.h 里的 PHP_VERSION，不一致就清目录重新下载解压；
#   ② 安装层比对 bin/php -v / sbin/php-fpm -v，低于目标版本必须重装，不再「目录存在即跳过」。
# 判定逻辑在 plugins/php/versions/common/php_ver_guard.sh，可独立调用做幂等测试。
Install_php()
{
#------------------------ install start ------------------------------------#
echo "安装php-${version} ..."
if command -v yf_ensure_swap >/dev/null 2>&1; then yf_ensure_swap; fi
trap 'if command -v yf_cleanup_swap >/dev/null 2>&1; then yf_cleanup_swap; fi' EXIT
mkdir -p $sourcePath/php
mkdir -p $serverPath/php

cd ${rootPath}/plugins/php/lib && /bin/bash freetype_new.sh
cd ${rootPath}/plugins/php/lib && /bin/bash zlib.sh

# redat ge 8
which yum
if [ "$?" == "0" ];then
	cd ${rootPath}/plugins/php/lib && /bin/bash oniguruma.sh
fi

# P0-2①：源码层判存 —— 不再只看 php_version.h 是否存在，而是比对里面的完整版本号。
# 版本不一致 / 读不出（含旧源码残留）都必须重新下载解压，否则会拿旧源码编译。
yf_php_src_needs_fetch "$sourcePath/php/php${PHP_VER}" "${version}"
_yf_src_need_fetch=$?
if [ "$_yf_src_need_fetch" = "2" ]; then
	echo "[ERROR] 目标版本 '${version}' 非法，无法判定源码版本，停止安装。"
	exit 1
fi
if [ "$_yf_src_need_fetch" = "0" ]; then
	if [ -d "$sourcePath/php/php${PHP_VER}" ]; then
		echo "已解压源码的版本与目标 ${version} 不一致（或无法读取），清理旧源码后重新下载解压..."
	fi
	if ! command -v xz >/dev/null 2>&1; then
		which apt-get >/dev/null 2>&1 && apt-get update && apt-get install -y xz-utils
		which yum >/dev/null 2>&1 && yum install -y xz
	fi


	# 源码包获取：多镜像轮询 + HTML 劫持识别 + sha256 强校验 + 离线包复用。
	# 失败时 helper 会打印每个镜像的失败原因与四种自救方式（含离线放置目录）。
	mkdir -p "$sourcePath/php"
	if ! yf_php_fetch_source "${version}" "${sha256_file_ok}" "$sourcePath/php/php-${version}.tar.xz"; then
		echo "[ERROR] PHP ${version} 源码包获取失败，安装中止（未改动现有安装）。"
		exit 1
	fi

	rm -rf $sourcePath/php/php${PHP_VER}
	mkdir -p $sourcePath/php/php${PHP_VER}
	tar -xf $sourcePath/php/php-${version}.tar.xz -C $sourcePath/php/php${PHP_VER} --strip-components=1 2>/dev/null
	if [ ! -f "$sourcePath/php/php${PHP_VER}/main/php_version.h" ]; then
		echo "Direct tar extraction failed, trying xz pipeline..."
		xz -dc $sourcePath/php/php-${version}.tar.xz | tar -xf - -C $sourcePath/php/php${PHP_VER} --strip-components=1 2>/dev/null
	fi
	if [ ! -f "$sourcePath/php/php${PHP_VER}/main/php_version.h" ]; then
		echo "Trying fallback to tar.gz format..."
		wget -nv --no-check-certificate -O $sourcePath/php/php-${version}.tar.gz https://mirrors.nju.edu.cn/php/php-${version}.tar.gz 2>/dev/null
		if [ -f "$sourcePath/php/php-${version}.tar.gz" ]; then
			tar -zxf $sourcePath/php/php-${version}.tar.gz -C $sourcePath/php/php${PHP_VER} --strip-components=1 2>/dev/null
		fi
	fi
	if [ ! -f "$sourcePath/php/php${PHP_VER}/main/php_version.h" ]; then
		echo "Error: PHP source extraction failed, main/php_version.h not found!"
		rm -rf $sourcePath/php/php${PHP_VER}
		exit 1
	fi

	# P0-2①：解压完再回读一次，源码版本必须等于目标版本 —— 宁可失败，也不用错源码编译。
	_yf_src_ver=`yf_php_ver_from_header "$sourcePath/php/php${PHP_VER}"`
	if [ "$_yf_src_ver" != "${version}" ]; then
		echo "[ERROR] 解压后的源码版本 '${_yf_src_ver:-未知}' 与目标 ${version} 不一致，停止安装。"
		rm -rf $sourcePath/php/php${PHP_VER}
		exit 1
	fi
fi

cd $sourcePath/php/php${PHP_VER}

OPTIONS='--without-iconv'

IS_64BIT=`getconf LONG_BIT`
if [ "$IS_64BIT" == "64" ];then
	OPTIONS="${OPTIONS} --with-libdir=lib64"
fi

argon_version=`pkg-config libargon2 --modversion`
if [ "$?" == "0" ];then
	OPTIONS="${OPTIONS} --with-password-argon2"
fi

# ----- cpu start ------
if [ -z "${cpuCore}" ]; then
	cpuCore="1"
fi

if [ -f /proc/cpuinfo ];then
	cpuCore=`cat /proc/cpuinfo | grep "processor" | wc -l`
fi

MEM_INFO=$(which free > /dev/null 2>&1 && LC_ALL=C free -m | awk '/Mem|内存/{printf("%.f",($2)/1024)}' || echo "0")
if [ -z "${MEM_INFO}" ] || [ "${MEM_INFO}" == "0" ]; then
    MEM_INFO="1"
fi
if [ "${cpuCore}" != "1" ] && [ "${MEM_INFO}" != "0" ];then
    if [ "${cpuCore}" -gt "${MEM_INFO}" ];then
        cpuCore="${MEM_INFO}"
    fi
else
    cpuCore="1"
fi

if [ "$cpuCore" -gt "2" ];then
	cpuCore=`echo "$cpuCore" | awk '{printf("%.f",($1)*0.8)}'`
else
	cpuCore="1"
fi
# ----- cpu end ------
	# --- yf adaptive clamp ---
	if command -v yf_make_jobs >/dev/null 2>&1; then
		_yf_jobs=$(yf_make_jobs 82 2>/dev/null || echo "")
		if [ -n "$_yf_jobs" ] && [ "$_yf_jobs" -ge 1 ] 2>/dev/null; then
			cpuCore="$_yf_jobs"
		fi
	fi

	if [ "$sysName" == "Darwin" ];then
		BREW_DIR=`which brew`
		BREW_DIR=${BREW_DIR/\/bin\/brew/}

		LIB_DEPEND_DIR=`brew info openssl | grep ${BREW_DIR}/Cellar/openssl | cut -d \  -f 1 | awk 'END {print}'`
		OPTIONS="$OPTIONS --with-openssl=$(brew --prefix openssl)"
		export PKG_CONFIG_PATH=$LIB_DEPEND_DIR/lib/pkgconfig
		export OPENSSL_CFLAGS="-I${LIB_DEPEND_DIR}/include"
		export OPENSSL_LIBS="-L/${LIB_DEPEND_DIR}/lib -lssl -lcrypto -lz"
	else
		cd ${rootPath}/plugins/php/lib && /bin/bash openssl_11.sh
		export PKG_CONFIG_PATH=$serverPath/lib/openssl11/lib/pkgconfig:$PKG_CONFIG_PATH
		OPTIONS="$OPTIONS --with-openssl=$serverPath/lib/openssl11"
	fi

	# echo "$sourcePath/php/php${PHP_VER}"
	# P0-2②：安装层判存 —— 不再「目录存在就整段跳过 configure/make/install」，
	# 改为比对已装二进制的完整版本；低于目标版本（或读不出）必须重装。
	yf_php_install_needs_build "$serverPath/php/${PHP_VER}" "${version}"
	_yf_inst_need_build=$?
	if [ "$_yf_inst_need_build" = "2" ]; then
		echo "[ERROR] 无法判定已装 PHP 版本（目标 '${version}'），停止安装以避免假成功。"
		exit 1
	fi
	if [ "$_yf_inst_need_build" = "0" ]; then
		echo "开始编译安装 PHP${version}（前缀 $serverPath/php/${PHP_VER}）..."
		cd $sourcePath/php/php${PHP_VER}
		./configure \
		--prefix=$serverPath/php/${PHP_VER} \
		--exec-prefix=$serverPath/php/${PHP_VER} \
		--with-config-file-path=$serverPath/php/${PHP_VER}/etc \
		--enable-mysqlnd \
		--with-mysqli=mysqlnd \
		--with-pdo-mysql=mysqlnd \
		--enable-mbstring \
		--enable-ftp \
		--enable-sockets \
		--enable-simplexml \
		--enable-soap \
		--enable-posix \
		--enable-sysvmsg \
		--enable-sysvsem \
		--enable-sysvshm \
		--disable-intl \
		--disable-fileinfo \
		$OPTIONS \
		--enable-fpm

		make clean || true
		if command -v yf_php_build >/dev/null 2>&1; then
			if ! yf_php_build "${cpuCore}"; then
				echo "[ERROR] PHP${PHP_VER} build failed, stop install to avoid false success."
				if command -v yf_cleanup_swap >/dev/null 2>&1; then yf_cleanup_swap; fi
				exit 1
			fi
		else
			if ! make -j${cpuCore}; then
				echo "[WARN] Parallel build failed (code $?, possibly OOM), cleaning stale JIT artifacts and retrying with -j1..."
				rm -f ext/opcache/jit/ir/ir_fold_hash.h ext/opcache/jit/ir/gen_ir_fold_hash 2>/dev/null || true
				rm -f ext/opcache/jit/ir/*.dep 2>/dev/null || true
				if ! make -j1; then
					echo "[ERROR] PHP${PHP_VER} build failed."
					exit 1
				fi
			fi
		fi
		if ! make install; then
			echo "[ERROR] PHP${PHP_VER} make install failed."
			if command -v yf_cleanup_swap >/dev/null 2>&1; then yf_cleanup_swap; fi
			exit 1
		fi
		make clean || true
		if command -v yf_cleanup_swap >/dev/null 2>&1; then yf_cleanup_swap; fi

		# rm -rf $sourcePath/php/php${PHP_VER}
	else
		echo "已装 PHP 版本不低于目标 ${version}，跳过编译。"
	fi

	# P0-2②：装完回读一次（只提示不中断：缺失动态库时 `php -v` 可能失败，
	# 硬失败会误伤正常新装；升级流程里的硬断言与回退由面板侧统一兜底）。
	if [ "$_yf_inst_need_build" = "0" ]; then
		_yf_inst_ver=`yf_php_ver_from_binary "$serverPath/php/${PHP_VER}"`
		if [ "$_yf_inst_ver" = "${version}" ]; then
			echo "PHP${version} 安装完成，回读校验通过（${_yf_inst_ver}）。"
		else
			echo "[WARN] 安装后回读版本 '${_yf_inst_ver:-未知}' 与目标 ${version} 不一致，请检查编译日志。"
		fi
	fi
	#------------------------ install end ------------------------------------#
}

Uninstall_php()
{
	$serverPath/php/init.d/php${PHP_VER} stop
	rm -rf $serverPath/php/${PHP_VER}
	echo "卸载php-${version}..."
}

action=${1}
if [ "${1}" == 'install' ];then
	Install_php
else
	Uninstall_php
fi