#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH=$PATH:/opt/homebrew/bin

function version_gt() { test "$(echo "$@" | tr " " "\n" | sort -V | head -n 1)" != "$1"; }
function version_le() { test "$(echo "$@" | tr " " "\n" | sort -V | head -n 1)" == "$1"; }
function version_lt() { test "$(echo "$@" | tr " " "\n" | sort -rV | head -n 1)" != "$1"; }
function version_ge() { test "$(echo "$@" | tr " " "\n" | sort -rV | head -n 1)" == "$1"; }

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
appPath=$(dirname "$curPath")

rootPath=$(cd "$curPath/../../../.."; pwd)
serverPath=$(dirname "$rootPath")
sourcePath=${serverPath}/source/php

actionType=$1
version=$2

LIBNAME=zip
LIBV=0

LIB_PATH_NAME=lib/php
if [ -d $serverPath/php/${version}/lib64 ];then
	LIB_PATH_NAME=lib64
fi

# 扩展目录**不能**靠 `ls extensions | grep no-debug-non-zts` 猜：全新分支在第一次
# 编译共享扩展之前，该子目录还不存在（正是本次 `make install` 才创建的）→ 猜出空串，
# extFile 变成 `extensions//xxx.so`，于是「编译成功却报产物缺失」（真机 PHP8.5/curl）。
# 以 php-config 为准；取不到才退回目录探测（只取第一行，目录不存在时不报错）。
NON_ZTS_FILENAME=`ls $serverPath/php/${version}/${LIB_PATH_NAME}/extensions 2>/dev/null | grep no-debug-non-zts | head -1`
extDir=`$serverPath/php/${version}/bin/php-config --extension-dir 2>/dev/null`
if [ -z "${extDir}" ]; then
	extDir=$serverPath/php/${version}/${LIB_PATH_NAME}/extensions/${NON_ZTS_FILENAME}
fi
extFile=${extDir}/${LIBNAME}.so

sysName=`uname`
if [ "$sysName" == "Darwin" ];then
	BAK='_bak'
else
	BAK=''
fi

if [ ! -d $serverPath/lib/libzip ];then
	cd ${rootPath}/plugins/php/lib && /bin/bash libzip.sh
fi

export PKG_CONFIG_PATH=${serverPath}/lib/libzip/lib/pkgconfig

# ZIP_OPTION='--with-zip'
# libzip_version=`pkg-config libzip --modversion`
# if version_lt "$libzip_version" "0.11.0" ;then
# 	cd ${rootPath}/plugins/php/lib && /bin/bash libzip.sh
# 	export PKG_CONFIG_PATH=$serverPath/lib/libzip/lib/pkgconfig
# 	ZIP_OPTION="--with-zip=$serverPath/lib/libzip"
# fi

Install_lib()
{

	isInstall=`cat $serverPath/php/$version/etc/php.ini|grep "${LIBNAME}.so"`
	if [ "${isInstall}" != "" ];then
		echo "php-$version 已安装${LIBNAME},请选择其它版本!"
		return
	fi
	
	
	# 这个目录可能就是刚才 `make install` 才创建的：判存前重新解析一次
	extDirNow=`$serverPath/php/${version}/bin/php-config --extension-dir 2>/dev/null`
	if [ -n "${extDirNow}" ]; then
		extFile=${extDirNow}/$(basename "$extFile")
	fi

	if [ ! -f "$extFile" ];then

		if [ ! -d $sourcePath/php${version}/ext ];then
			cd ${rootPath}/plugins/php && /bin/bash ${rootPath}/plugins/php/versions/${version}/install.sh install 
		fi

		cd $sourcePath/php${version}/ext/${LIBNAME}
		
		$serverPath/php/$version/bin/phpize
		./configure --with-php-config=$serverPath/php/$version/bin/php-config --with-zip

		make clean && make -j${cpuCore:-1} && make install && make clean

		# if [ -d $sourcePath/php${version} ];then
		# cd ${sourcePath} && rm -rf $sourcePath/php${version}
		# fi
		
	fi

	# 这个目录可能就是刚才 `make install` 才创建的：判存前重新解析一次
	extDirNow=`$serverPath/php/${version}/bin/php-config --extension-dir 2>/dev/null`
	if [ -n "${extDirNow}" ]; then
		extFile=${extDirNow}/$(basename "$extFile")
	fi

	if [ ! -f "$extFile" ];then
		echo "ERROR: ${LIBNAME} 扩展产物缺失: $extFile（编译或安装失败）" >&2
		return 1
	fi

    echo "" >> $serverPath/php/$version/etc/php.ini
	echo "[${LIBNAME}]" >> $serverPath/php/$version/etc/php.ini
	echo "extension=${LIBNAME}.so" >> $serverPath/php/$version/etc/php.ini
	
	cd  ${curPath} && bash ${rootPath}/plugins/php/versions/lib.sh $version restart
	echo '==========================================================='
	echo 'successful!'
}


Uninstall_lib()
{
	if [ ! -f "$serverPath/php/$version/bin/php-config" ];then
		echo "php-$version 未安装,请选择其它版本!"
		return
	fi
	
	# 这个目录可能就是刚才 `make install` 才创建的：判存前重新解析一次
	extDirNow=`$serverPath/php/${version}/bin/php-config --extension-dir 2>/dev/null`
	if [ -n "${extDirNow}" ]; then
		extFile=${extDirNow}/$(basename "$extFile")
	fi

	if [ ! -f "$extFile" ];then
		echo "php-$version 未安装${LIBNAME},请选择其它版本!"
		return
	fi
	
	echo $serverPath/php/$version/etc/php.ini
	sed -i $BAK "/${LIBNAME}.so/d" $serverPath/php/$version/etc/php.ini
	sed -i $BAK "/${LIBNAME}/d" $serverPath/php/$version/etc/php.ini
		
	rm -f $extFile
	cd  ${curPath} && bash ${rootPath}/plugins/php/versions/lib.sh $version restart
	echo '==============================================='
	echo 'successful!'
}



if [ "$actionType" == 'install' ];then
	Install_lib
elif [ "$actionType" == 'uninstall' ];then
	Uninstall_lib
fi