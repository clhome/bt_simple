#!/bin/bash
if [ -f $(dirname $0)/../../scripts/lib_make_jobs.sh ]; then source $(dirname $0)/../../scripts/lib_make_jobs.sh; elif [ -f /www/server/yufeng_panel/scripts/lib_make_jobs.sh ]; then source /www/server/yufeng_panel/scripts/lib_make_jobs.sh; fi
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH=$PATH:/opt/homebrew/bin

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(cd "$curPath/../../../.."; pwd)
serverPath=$(dirname "$rootPath")

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

if [ -f ${rootPath}/scripts/github_download.sh ];then
	source ${rootPath}/scripts/github_download.sh
fi

sourcePath=${serverPath}/source
sysName=`uname`
SYS_ARCH=`arch`

version=5.2.17
PHP_VER=52
Install_php()
{
#------------------------ install start ------------------------------------#
echo "安装php-${version} ..."
mkdir -p $sourcePath/php
mkdir -p $serverPath/php

cd ${rootPath}/plugins/php/lib && /bin/bash zlib.sh

if [ ! -d $sourcePath/php/php${PHP_VER} ];then
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

	if [ ! -f $sourcePath/php/php-${version}.tar.gz ];then
		wget -nv --no-check-certificate -O $sourcePath/php/php-${version}.tar.gz https://museum.php.net/php5/php-${version}.tar.gz
	fi
	
	if [ ! -f $sourcePath/php/php-5.2.17-fpm-0.5.14.diff.gz ]; then
		wget -nv --no-check-certificate -O $sourcePath/php/php-5.2.17-fpm-0.5.14.diff.gz http://php-fpm.org/downloads/php-5.2.17-fpm-0.5.14.diff.gz
	fi


	if [ ! -f $sourcePath/php/php-5.2.17-max-input-vars.patch ]; then
		github_download $sourcePath/php/php-5.2.17-max-input-vars.patch https://raw.githubusercontent.com/laruence/laruence.github.com/master/php-5.2-max-input-vars/php-5.2.17-max-input-vars.patch
	fi

	if [ ! -f $sourcePath/php/php-5.x.x.patch ]; then
		wget -nv --no-check-certificate -O $sourcePath/php/php-5.x.x.patch https://mail.gnome.org/archives/xml/2012-August/txtbgxGXAvz4N.txt
	fi


	if [ ! -f $sourcePath/php/php-${version}.tar.gz ] && [ ! -f $sourcePath/php/php-${version}.tar.xz ]; then
		echo "PHP source file missing!"
		exit 1
	fi
	rm -rf $sourcePath/php/php${PHP_VER}
	mkdir -p $sourcePath/php/php${PHP_VER}
	if [ -f $sourcePath/php/php-${version}.tar.gz ]; then
		tar -zxf $sourcePath/php/php-${version}.tar.gz -C $sourcePath/php/php${PHP_VER} --strip-components=1 2>/dev/null
	elif [ -f $sourcePath/php/php-${version}.tar.xz ]; then
		tar -xf $sourcePath/php/php-${version}.tar.xz -C $sourcePath/php/php${PHP_VER} --strip-components=1 2>/dev/null
	fi
	if [ ! -f "$sourcePath/php/php${PHP_VER}/main/php_version.h" ]; then
		echo "Error: PHP source extraction failed, main/php_version.h not found!"
		rm -rf $sourcePath/php/php${PHP_VER}
		exit 1
	fi


	cd $sourcePath/php
	gzip -cd php-5.2.17-fpm-0.5.14.diff.gz | patch -d php${PHP_VER} -p1
	cd $sourcePath/php/php${PHP_VER}
	patch -p1 < ../php-5.2.17-max-input-vars.patch
	patch -p0 -b < ../php-5.x.x.patch 
	sed -i "s/\!png_check_sig (sig, 8)/png_sig_cmp (sig, 0, 8)/" ext/gd/libgd/gd_png.c
fi


if [  -f $serverPath/php/${PHP_VER}/bin/php.dSYM ];then
	mv $serverPath/php/${PHP_VER}/bin/php.dSYM $serverPath/php/${PHP_VER}/bin/php
fi

if [  -f $serverPath/php/${PHP_VER}/sbin/php-fpm.dSYM ];then
	mv $serverPath/php/${PHP_VER}/sbin/php-fpm.dSYM $serverPath/php/${PHP_VER}/sbin/php-fpm
fi


if [ -f $serverPath/php/${PHP_VER}/bin/php ];then
	return
fi

OPTIONS='--without-iconv'
if [ $sysName == 'Darwin' ]; then
	OPTIONS="${OPTIONS} --with-freetype-dir=${serverPath}/lib/freetype"
fi

IS_64BIT=`getconf LONG_BIT`
if [ "$IS_64BIT" == "64" ];then
	OPTIONS="${OPTIONS} --with-libdir=lib64"
fi

if [ "${SYS_ARCH}" == "aarch64" ];then
	OPTIONS="$OPTIONS --build=aarch64-unknown-linux-gnu --host=aarch64-unknown-linux-gnu"
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

if [ ! -d $serverPath/php/${PHP_VER} ];then

	export MYSQL_LIB_DIR=/usr/lib64/mysql
	
	cd $sourcePath/php/php${PHP_VER} && ./configure \
	--prefix=$serverPath/php/${PHP_VER} \
	--exec-prefix=$serverPath/php/${PHP_VER} \
	--with-config-file-path=$serverPath/php/${PHP_VER}/etc \
	--enable-xml \
	--enable-shared \
	--with-mysql=mysqlnd \
	--enable-embedded-mysqli=shared \
	--enable-sysvmsg \
	--enable-sysvsem \
	--enable-sysvshm \
	$OPTIONS \
	--enable-fastcgi \
	--enable-fpm
	# ZEND_EXTRA_LIBS='-liconv'
	make -j${cpuCore:-1} && make install && make clean
fi

if [ "$?" != "0" ];then
	echo "install fail!!"
	rm -rf $sourcePath/php/php${PHP_VER}
	exit 2
fi


if [  -f $serverPath/php/${PHP_VER}/bin/php.dSYM ];then
	mv $serverPath/php/${PHP_VER}/bin/php.dSYM $serverPath/php/${PHP_VER}/bin/php
fi

if [  -f $serverPath/php/${PHP_VER}/sbin/php-fpm.dSYM ];then
	mv $serverPath/php/${PHP_VER}/sbin/php-fpm.dSYM $serverPath/php/${PHP_VER}/sbin/php-fpm
fi

if [ ! -d $serverPath/php/${PHP_VER}/lib/php/extensions/no-debug-non-zts-20060613 ]; then
	mkdir -p $serverPath/php/${PHP_VER}/lib/php/extensions/no-debug-non-zts-20060613
fi

# ps -ef|grep php/52 |grep -v grep |awk '{print $2}'|xargs kill
# /www/server/php/init.d/php52 start
# /www/server/php/52/sbin/php-fpm start
mkdir -p $serverPath/php/${PHP_VER}/var/log
mkdir -p $serverPath/php/${PHP_VER}/var/run

#------------------------ install end ------------------------------------#
}



Uninstall_php()
{
	$serverPath/php/init.d/php${PHP_VER} stop
	rm -rf $serverPath/php/${PHP_VER}
	echo "uninstall php-${version} ..."
}

action=${1}
if [ "${1}" == 'install' ];then
	Install_php
else
	Uninstall_php
fi
# --- yf adaptive clamp (1C512M -> -j1) ---
if command -v yf_make_jobs >/dev/null 2>&1; then _yf_jobs=$(yf_make_jobs 2>/dev/null || echo ""); if [ -n "$_yf_jobs" ] && [ "$_yf_jobs" -ge 1 ] 2>/dev/null; then cpuCore="$_yf_jobs"; fi; fi
