#!/bin/bash
if [ -f $(dirname $0)/../../scripts/lib_make_jobs.sh ]; then source $(dirname $0)/../../scripts/lib_make_jobs.sh; elif [ -f /www/server/yufeng_panel/scripts/lib_make_jobs.sh ]; then source /www/server/yufeng_panel/scripts/lib_make_jobs.sh; fi
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH=$PATH:/opt/homebrew/bin

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(cd "$curPath/../../../.."; pwd)
serverPath=$(dirname "$rootPath")
sourcePath=${serverPath}/source
sysName=`uname`
SYS_ARCH=`arch`

OSID=$(grep -E "^ID=" /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')
OSVER=$(grep -E "^VERSION_ID=" /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')
# Debian 13 (trixie) 上 PHP 5.x 依赖的老 OpenSSL/编译器组合未验证且基本无法编译，明确标记不支持
if [ "$OSID" == "debian" ] && [ "$OSVER" == "13" ];then
    echo "PHP 5.3 不支持在 Debian 13 (trixie) 上安装（依赖的老版本 OpenSSL/工具链已不可用），请选择 PHP 7.2+"
    exit 1
fi

version=5.3.29
PHP_VER=53
md5_file_ok=dcff9c881fe436708c141cfc56358075
Install_php()
{
#------------------------ install start ------------------------------------#
echo "安装php-5.3.29 ..."
mkdir -p $sourcePath/php
mkdir -p $serverPath/php

cd ${rootPath}/plugins/php/lib && /bin/bash zlib.sh

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
		wget -nv --no-check-certificate -O $sourcePath/php/php-${version}.tar.xz https://museum.php.net/php5/php-${version}.tar.xz
	fi

	#检测文件是否损坏.
	if [ -f $sourcePath/php/php-${version}.tar.xz ];then
		md5_file=`md5sum $sourcePath/php/php-${version}.tar.xz  | awk '{print $1}'`
		if [ "${md5_file}" != "${md5_file_ok}" ]; then
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


if [ -f $serverPath/php/53/bin/php ];then
	return
fi

# OPTIONS="${OPTIONS} --with-freetype-dir=${serverPath}/lib/freetype_old"
# OPTIONS="${OPTIONS} --with-gd --enable-gd-native-ttf"
# OPTIONS="${OPTIONS} --with-jpeg --with-jpeg-dir=/usr/lib"
OPTIONS='--without-iconv'

if [ $sysName == 'Darwin' ]; then
	OPTIONS="${OPTIONS} --with-freetype-dir=${serverPath}/lib/freetype"
fi

IS_64BIT=`getconf LONG_BIT`
if [ "$IS_64BIT" == "64" ];then
	OPTIONS="${OPTIONS} --with-libdir=lib64"
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
# --- yf adaptive clamp (1C512M -> -j1) ---
if command -v yf_make_jobs >/dev/null 2>&1; then _yf_jobs=$(yf_make_jobs 2>/dev/null || echo ""); if [ -n "$_yf_jobs" ] && [ "$_yf_jobs" -ge 1 ] 2>/dev/null; then cpuCore="$_yf_jobs"; fi; fi

if [ "${SYS_ARCH}" == "aarch64" ];then
	OPTIONS="$OPTIONS --build=aarch64-unknown-linux-gnu --host=aarch64-unknown-linux-gnu"
fi

if [ ! -d $serverPath/php/${PHP_VER}/bin ];then
	cd $sourcePath/php/php${PHP_VER} && ./configure \
	--prefix=$serverPath/php/${PHP_VER} \
	--exec-prefix=$serverPath/php/${PHP_VER} \
	--with-config-file-path=$serverPath/php/${PHP_VER}/etc \
	--enable-mysqlnd \
	--with-mysql=mysqlnd \
	--with-pdo-mysql=mysqlnd \
	--with-mysqli=mysqlnd \
	--enable-mbstring \
	--enable-exif \
	--enable-hash \
	--enable-libxml \
	--enable-simplexml \
	--enable-dom \
	--enable-filter \
	--enable-xml \
	--enable-ftp \
	--enable-soap \
	--enable-posix \
	--enable-sockets \
	--enable-mbstring \
	--enable-sysvmsg \
	--enable-sysvsem \
	--enable-sysvshm \
	--disable-fileinfo \
	$OPTIONS \
	--enable-fpm
	make clean && make -j${cpuCore} && make install && make clean

	# rm -rf $sourcePath/php/php${PHP_VER}
	echo "安装php-${version}成功"
fi


if [  -f $serverPath/php/53/bin/php.dSYM ];then
	mv $serverPath/php/53/bin/php.dSYM $serverPath/php/53/bin/php
fi

if [  -f $serverPath/php/53/sbin/php-fpm.dSYM ];then
	mv $serverPath/php/53/sbin/php-fpm.dSYM $serverPath/php/53/sbin/php-fpm
fi


if [ -d $serverPath/php/53 ] && [ ! -d $serverPath/php/53/lib/php/extensions/no-debug-non-zts-20090626 ]; then
	mkdir -p $serverPath/php/53/lib/php/extensions/no-debug-non-zts-20090626
fi

#------------------------ install end ------------------------------------#
}



Uninstall_php()
{
	$serverPath/php/init.d/php53 stop
	rm -rf $serverPath/php/53
	echo "uninstall php-5.3.29 ..."
}

action=${1}
if [ "${1}" == 'install' ];then
	Install_php
else
	Uninstall_php
fi