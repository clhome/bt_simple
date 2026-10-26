#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)

rootPath=$(cd "$curPath/../../../.."; pwd)
serverPath=$(dirname "$rootPath")
sourcePath=${serverPath}/source/php

actionType=$1
version=$2

LIBNAME=gd
LIBV=0

# 扩展目录以 php-config 为准：全新分支在第一次编译共享扩展之前，
# `extensions/no-debug-non-zts-*` 还不存在（正是这次 make install 创建的），
# 靠 `ls | grep` 会猜到空串 → extFile 成为 `extensions//xxx.so`，编译成功也判缺失。
extDir=`$serverPath/php/${version}/bin/php-config --extension-dir 2>/dev/null`
if [ -z "${extDir}" ]; then
	NON_ZTS_FILENAME=`ls $serverPath/php/${version}/lib/php/extensions 2>/dev/null | grep no-debug-non-zts | head -1`
	extDir=$serverPath/php/${version}/lib/php/extensions/${NON_ZTS_FILENAME}
fi
extFile=${extDir}/${LIBNAME}.so

sysName=`uname`
if [ "$sysName" == "Darwin" ];then
	BAK='_bak'
else
	BAK=''
fi


sysName=`uname`
echo "use system: ${sysName}"

if [ ${sysName} == "Darwin" ]; then
	OSNAME='macos'
elif grep -Eqi "CentOS" /etc/issue || grep -Eq "CentOS" /etc/*-release; then
	OSNAME='centos'
elif grep -Eqi "Fedora" /etc/issue || grep -Eq "Fedora" /etc/*-release; then
	OSNAME='fedora'
elif grep -Eqi "Debian" /etc/issue || grep -Eq "Debian" /etc/*-release; then
	OSNAME='debian'
elif grep -Eqi "Ubuntu" /etc/issue || grep -Eq "Ubuntu" /etc/*-release; then
	OSNAME='ubuntu'
elif grep -Eqi "Raspbian" /etc/issue || grep -Eq "Raspbian" /etc/*-release; then
	OSNAME='raspbian'
else
	OSNAME='unknow'
fi

Install_lib()
{

	isInstall=`cat $serverPath/php/$version/etc/php.ini|grep "${LIBNAME}.so"`
	if [ "${isInstall}" != "" ];then
		echo "php-$version 已安装${LIBNAME},请选择其它版本!"
		return
	fi


	# cp -frp /usr/lib64/libldap* /usr/lib/

	# ln -s /usr/lib64/libjpeg.so /usr/lib/libjpeg.so
	# ln -s /usr/lib64/libpng.so /usr/lib/libpng.so

	if [ ! -f /usr/lib/libjpeg.so ];then
		ln -s /usr/lib64/libjpeg.so /usr/lib/libjpeg.so
	fi

	if [ ! -f /usr/lib/libpng.so ];then
		ln -s /usr/lib64/libpng.so /usr/lib/libpng.so
	fi
	
	
	# 这个目录可能就是刚才 `make install` 才创建的：判存前重新解析一次
	extDirNow=`$serverPath/php/${version}/bin/php-config --extension-dir 2>/dev/null`
	if [ -n "${extDirNow}" ]; then
		extFile=${extDirNow}/$(basename "$extFile")
	fi

	if [ ! -f "$extFile" ];then

		if [ ! -d $sourcePath/php${version}/ext ];then
			cd ${rootPath}/plugins/php && /bin/bash install.sh install ${version}
		fi
		
		cd $sourcePath/php${version}/ext/${LIBNAME}
		
		$serverPath/php/$version/bin/phpize
		./configure --with-php-config=$serverPath/php/$version/bin/php-config \
		--with-gd \
		--with-jpeg-dir=/usr/lib \
		--with-freetype-dir=${serverPath}/lib/freetype_old \
		--enable-gd-native-ttf

		make clean && make -j${cpuCore:-1} && make install && make clean
		
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
		return
	fi
	
	echo $serverPath/php/$version/etc/php.ini
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