#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)

rootPath=$(cd "$curPath/../../../.."; pwd)
serverPath=$(dirname "$rootPath")
sourcePath=${serverPath}/source/php

LIBNAME=memcache
LIBV=2.2.7
sysName=`uname`
actionType=$1
version=$2


# 扩展目录以 php-config 为准：全新分支在第一次编译共享扩展之前，
# `extensions/no-debug-non-zts-*` 还不存在（正是这次 make install 创建的），
# 靠 `ls | grep` 会猜到空串 → extFile 成为 `extensions//xxx.so`，编译成功也判缺失。
extDir=`$serverPath/php/${version}/bin/php-config --extension-dir 2>/dev/null`
if [ -z "${extDir}" ]; then
	NON_ZTS_FILENAME=`ls $serverPath/php/${version}/lib/php/extensions 2>/dev/null | grep no-debug-non-zts | head -1`
	extDir=$serverPath/php/${version}/lib/php/extensions/${NON_ZTS_FILENAME}
fi
extFile=${extDir}/${LIBNAME}.so

if [ "$sysName" == "Darwin" ];then
	BAK='_bak'
else
	BAK=''
fi

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
		php_lib=$sourcePath/php_lib
		mkdir -p $php_lib

		wget -O $php_lib/${LIBNAME}-${LIBV}.tgz https://pecl.php.net/get/${LIBNAME}-${LIBV}.tgz

		cd $php_lib && tar xvf ${LIBNAME}-${LIBV}.tgz
		cd ${LIBNAME}-${LIBV}
		$serverPath/php/$version/bin/phpize
		./configure --with-php-config=$serverPath/php/$version/bin/php-config --enable-memcache --with-zlib-dir
		make -j${cpuCore:-1} && make install && make clean

	fi
	
	# 这个目录可能就是刚才 `make install` 才创建的：判存前重新解析一次
	extDirNow=`$serverPath/php/${version}/bin/php-config --extension-dir 2>/dev/null`
	if [ -n "${extDirNow}" ]; then
		extFile=${extDirNow}/$(basename "$extFile")
	fi

	if [ ! -f "$extFile" ];then
		echo "ERROR!"
		return
	fi
	echo "" >> $serverPath/php/$version/etc/php.ini
	echo "[${LIBNAME}]" >> $serverPath/php/$version/etc/php.ini
	echo "extension=${LIBNAME}.so" >> $serverPath/php/$version/etc/php.ini
	

	bash ${rootPath}/plugins/php/versions/lib.sh $version restart
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
		echo "php-$version not install memcache, Plese select other version!"
		return
	fi
	
	sed -i $BAK "/${LIBNAME}.so/d" $serverPath/php/$version/etc/php.ini
	sed -i $BAK "/${LIBNAME}/d" $serverPath/php/$version/etc/php.ini
		
	rm -f $extFile
	bash ${rootPath}/plugins/php/versions/lib.sh $version restart
	echo '==============================================='
	echo 'successful!'
}


if [ "$actionType" == 'install' ];then
	Install_lib
elif [ "$actionType" == 'uninstall' ];then
	Uninstall_lib
fi