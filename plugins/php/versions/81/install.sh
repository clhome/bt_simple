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

version=8.1.33
PHP_VER=81
sha256_file_ok=9db83bf4590375562bc1a10b353cccbcf9fcfc56c58b7c8fb814e6865bb928d1
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

if [ ! -f "$sourcePath/php/php${PHP_VER}/main/php_version.h" ];then
	if ! command -v xz >/dev/null 2>&1; then
		which apt-get >/dev/null 2>&1 && apt-get update && apt-get install -y xz-utils
		which yum >/dev/null 2>&1 && yum install -y xz
	fi


	# ----------------------------------------------------------------------- #
	# 中国优化安装
	cn=$(curl -fsSL -k -m 10 -s https://ipinfo.io/json | grep "\"country\": \"CN\"")
	LOCAL_ADDR=common
	if [ ! -z "$cn" ] || [ "$?" == "0" ] ;then
		LOCAL_ADDR=cn
	fi

	if [ "$LOCAL_ADDR" == "cn" ];then
		if [ ! -f $sourcePath/php/php-${version}.tar.xz ];then
			wget -nv --no-check-certificate -O $sourcePath/php/php-${version}.tar.xz https://mirrors.nju.edu.cn/php/php-${version}.tar.xz
		fi
	fi
	# ----------------------------------------------------------------------- #

	if [ ! -f $sourcePath/php/php-${version}.tar.xz ];then
		wget -nv --no-check-certificate -O $sourcePath/php/php-${version}.tar.xz https://www.php.net/distributions/php-${version}.tar.xz
	fi
		
	#检测文件是否损坏.
	if [ -f $sourcePath/php/php-${version}.tar.xz ];then
		sha256_file=`sha256sum $sourcePath/php/php-${version}.tar.xz  | awk '{print $1}'`
		if [ "${sha256_file}" != "${sha256_file_ok}" ]; then
			echo "PHP${version} 下载文件不完整,重新安装"
			rm -rf $sourcePath/php/php-${version}.tar.xz
			exit 1
		fi
	fi

	if [ ! -f $sourcePath/php/php-${version}.tar.xz ]; then
		echo "PHP source file missing!"
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
fi

cd $sourcePath/php/php${PHP_VER}

OPTIONS='--without-iconv'
# if [ $sysName == 'Darwin' ]; then
# 	OPTIONS="${OPTIONS} --with-curl"
# fi

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
		_yf_jobs=$(yf_make_jobs 81 2>/dev/null || echo "")
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
		# 自建失败必须中止（2026-10-27，与 MySQL 5.6 事故同族）：否则会拿空目录去
		# configure，最终只留一句含糊的 "Package requirements (openssl) were not met"。
		cd ${rootPath}/plugins/php/lib && /bin/bash openssl_11.sh || {
			echo "[ERROR] 自建 OpenSSL 1.1 失败，PHP ${version} 无法编译（见上方 openssl11 日志）" >&2
			exit 1
		}
		_ossl_dir="${serverPath}/lib/openssl11"
		if [ ! -f "${_ossl_dir}/include/openssl/ssl.h" ]; then
			echo "[ERROR] 未找到可用的 OpenSSL 1.1：${_ossl_dir}/include/openssl/ssl.h 不存在" >&2
			exit 1
		fi
		export PKG_CONFIG_PATH=${_ossl_dir}/lib/pkgconfig:$PKG_CONFIG_PATH
		OPTIONS="$OPTIONS --with-openssl=${_ossl_dir}"
	fi

	if [ ! -d $serverPath/php/${PHP_VER} ];then
		cd $sourcePath/php/php${PHP_VER}
		./configure \
		--prefix=$serverPath/php/${PHP_VER} \
		--exec-prefix=$serverPath/php/${PHP_VER} \
		--with-config-file-path=$serverPath/php/${PHP_VER}/etc \
		--enable-mysqlnd \
		--with-mysqli=mysqlnd \
		--with-pdo-mysql=mysqlnd \
		--enable-ftp \
		--enable-mbstring \
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
	fi 
	#------------------------ install end ------------------------------------#
}

Uninstall_php()
{
	# 先彻底停 php-fpm（init.d stop 失败也能按「可执行文件在本版本目录下」杀掉），
	# 否则 php-fpm 会带着已删除的二进制继续占着 fpm socket（同 MySQL 现场）。
	for _yf_svc_lib in "${rootPath}/scripts/lib_service_stop.sh" \
	                   "${serverPath}/yufeng_panel/scripts/lib_service_stop.sh"; do
		[ -f "${_yf_svc_lib}" ] && . "${_yf_svc_lib}" && break
	done
	if command -v yf_svc_force_stop >/dev/null 2>&1; then
		yf_svc_force_stop "${serverPath}/php/${PHP_VER}" "php${PHP_VER}" || \
			echo "[WARN] php-fpm(${PHP_VER}) 仍有进程残留，卸载继续但端口/socket 可能被占" >&2
	fi
	$serverPath/php/init.d/php${PHP_VER} stop 2>/dev/null
	rm -rf $serverPath/php/${PHP_VER}
	echo "卸载php-${version}..."
}

action=${1}
if [ "${1}" == 'install' ];then
	Install_php
else
	Uninstall_php
fi