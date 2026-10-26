#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)

rootPath=$(cd "$curPath/../../../.."; pwd)
serverPath=$(dirname "$rootPath")
sourcePath=${serverPath}/source/php

LIBNAME=ZendGuardLoader

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
extFile=$serverPath/php/${version}/lib/php/extensions/${NON_ZTS_FILENAME}/ZendOptimizer.so


if [ "$sysName" == "Darwin" ];then
	BAK='_bak'
else
	BAK=''
fi

Install_lib()
{
	

	isInstall=`cat $serverPath/php/$version/etc/php.ini|grep "ZendOptimizer.so"`
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

		if [ $sysName == 'Darwin' ]; then
			wget -O $php_lib/zend-loader-php5.3.tar.gz http://downloads.zend.com/guard/5.5.0/ZendGuardLoader-php-5.3-darwin-i386.tar.gz
		else
			wget -O $php_lib/ZendOptimizer-3.3.3-linux-glibc23-x86_64.tar.gz http://downloads.zend.com/optimizer/3.3.3/ZendOptimizer-3.3.3-linux-glibc23-x86_64.tar.gz
		fi 

		cd $php_lib && tar zxvf ZendOptimizer-3.3.3-linux-glibc23-x86_64.tar.gz
		cd $php_lib/ZendOptimizer-3.3.3-linux-glibc23-x86_64
		cp $php_lib/ZendOptimizer-3.3.3-linux-glibc23-x86_64/data/5_2_x_comp/ZendOptimizer.so $serverPath/php/$version/lib/php/extensions/no-debug-non-zts-20060613/

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

	echo  "" >> $serverPath/php/$version/etc/php.ini
	echo  "[Zend ZendGuard Loader]" >> $serverPath/php/$version/etc/php.ini
	echo  "zend_extension=$serverPath/php/$version/lib/php/extensions/no-debug-non-zts-20060613/ZendOptimizer.so" >> $serverPath/php/$version/etc/php.ini
	echo  "zend_loader.enable=1" >> $serverPath/php/$version/etc/php.ini
	echo  "zend_loader.disable_licensing=0" >> $serverPath/php/$version/etc/php.ini
	echo  "zend_loader.obfuscation_level_support=3" >> $serverPath/php/$version/etc/php.ini
	echo  "zend_loader.license_path=" >> $serverPath/php/$version/etc/php.ini
	
	bash ${rootPath}/plugins/php/versions/lib.sh $version restart
	echo '==========================================================='
	echo 'successful!'
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
		echo "php-$version 未安装${LIBNAME},请选择其它版本!"
		return
	fi
	
	sed -i $BAK "/ZendOptimizer.so/d"  $serverPath/php/$version/etc/php.ini
	sed -i $BAK "/zend_loader/d"  $serverPath/php/$version/etc/php.ini
	sed -i $BAK "/\[Zend ZendGuard Loader\]/d"  $serverPath/php/$version/etc/php.ini
		
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