#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH=$PATH:/opt/homebrew/bin

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)

rootPath=$(cd "$curPath/../../../.."; pwd)
serverPath=$(dirname "$rootPath")
sourcePath=${serverPath}/source/php

# support 55-74

LIBNAME=ioncube
LIBV=0
sysName=`uname`
actionType=$1
version=$2
IC_VERSION=${version:0:1}.${version:1:2}
ARCH=`uname -m`

if [ "$version" -gt "82" ];then
	echo "not need"
	exit 1
fi

DEFAULT_ARCH='x86-64'
if [ "$ARCH" == "aarch64" ];then
	DEFAULT_ARCH='aarch64'
fi

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
		if [ ! -f $php_lib/ioncube_loaders_lin.tar.gz ];then
			wget -O $php_lib/ioncube_loaders_lin.tar.gz https://downloads.ioncube.com/loader_downloads/ioncube_loaders_lin_${DEFAULT_ARCH}.tar.gz
			cd $php_lib && tar -zxf ioncube_loaders_lin.tar.gz
		fi 

		if [ ! -d $php_lib/ioncube ];then
			cd $php_lib && tar -zxf ioncube_loaders_lin.tar.gz
		fi
		cd $php_lib/ioncube
		
		cp -rf $php_lib/ioncube/ioncube_loader_lin_${IC_VERSION}.so $extFile
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

	sed -i $BAK "1i\[${LIBNAME}]" $serverPath/php/$version/etc/php.ini
	sed -i $BAK "2i\zend_extension=${LIBNAME}.so" $serverPath/php/$version/etc/php.ini
	# echo "[${LIBNAME}]" >> $serverPath/php/$version/etc/php.ini
	# echo "zend_extension=${LIBNAME}.so" >> $serverPath/php/$version/etc/php.ini

	cd  ${curPath} && bash ${rootPath}/plugins/php/versions/lib.sh $version restart
	echo '==========================================================='
	echo 'successful!'

	if [ -d $php_lib/ioncube ];then
		rm -rf $php_lib/ioncube
	fi
}


Uninstall_lib()
{
	if [ ! -f "$serverPath/php/$version/bin/php-config" ];then
		echo "php$version 未安装,请选择其它版本!"
		return
	fi
	
	# 这个目录可能就是刚才 `make install` 才创建的：判存前重新解析一次
	extDirNow=`$serverPath/php/${version}/bin/php-config --extension-dir 2>/dev/null`
	if [ -n "${extDirNow}" ]; then
		extFile=${extDirNow}/$(basename "$extFile")
	fi

	if [ ! -f "$extFile" ];then
		echo "php$version 未安装${LIBNAME},请选择其它版本!"
		echo "php-$vphp not install ${LIBNAME}, Plese select other version!"
		return
	fi
	
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