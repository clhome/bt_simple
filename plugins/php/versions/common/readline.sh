#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH=$PATH:/opt/homebrew/bin

# cd /www/server/yufeng_panel/plugins/php/versions/common && bash readline.sh install 81

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)

appPath=$(dirname "$curPath")

rootPath=$(cd "$curPath/../../../.."; pwd)
serverPath=$(dirname "$rootPath")
sourcePath=${serverPath}/source/php
SYS_ARCH=`arch`
actionType=$1
version=$2

LIBNAME=readline
LIBV=0

if [ "$version" -lt "74" ];then
	echo "not need"
	exit 0
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

sysName=`uname`
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

		if [ ! -d $sourcePath/php${version}/ext ];then
			cd ${rootPath}/plugins/php && /bin/bash ${rootPath}/plugins/php/versions/${version}/install.sh install 
		fi

		cd $sourcePath/php${version}/ext/${LIBNAME}
		if [ ! -f "config.m4" ];then
			mv config0.m4 config.m4
		fi

		OPTIONS=""
		if [ "${SYS_ARCH}" == "aarch64" ] && [ "$version" -lt "56" ];then
			OPTIONS="$OPTIONS --build=aarch64-unknown-linux-gnu --host=aarch64-unknown-linux-gnu"
		fi

		# libedit 是 readline 的唯一外部依赖：它的脚本现在失败即 exit 1，
		# 这里必须把失败接住（否则会在没有 libedit 的情况下继续 configure，
		# 最后只留一条含糊的 "Package requirements (libedit) were not met"）
		cd ${rootPath}/plugins/php/lib && /bin/bash libedit.sh || {
			echo "ERROR: libedit 安装失败，readline 扩展无法编译（详见上文）" >&2
			return 1
		}
		export PKG_CONFIG_PATH=$PKG_CONFIG_PATH:${serverPath}/lib/libedit/lib/pkgconfig
		# libedit.sh 退出 0 也要回读一次 pkg-config：否则 configure 只留一句含糊的
		# "Package requirements (libedit) were not met"，看不出是依赖没装成。
		if ! pkg-config --exists libedit 2>/dev/null; then
			echo "ERROR: libedit 已安装但 pkg-config 找不到 libedit.pc（PKG_CONFIG_PATH=${PKG_CONFIG_PATH}）" >&2
			echo "       请检查 ${serverPath}/lib/libedit/lib/pkgconfig/libedit.pc 是否存在" >&2
			return 1
		fi
		OPTIONS="$OPTIONS --with-libedit=${serverPath}/lib/libedit"

		cd $sourcePath/php${version}/ext/${LIBNAME}
		$serverPath/php/$version/bin/phpize
		if ! ./configure --with-php-config=$serverPath/php/$version/bin/php-config $OPTIONS; then
			echo "ERROR: ${LIBNAME} 扩展 configure 失败（见上方输出）" >&2
			return 1
		fi
		if ! ( make clean && make -j${cpuCore:-1} && make install ); then
			echo "ERROR: ${LIBNAME} 扩展编译/安装失败，已中止" >&2
			return 1
		fi
		make clean || true
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