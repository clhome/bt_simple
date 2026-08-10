#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

sysName=`uname`
echo "use system: ${sysName}"

Install_phpmyadmin()
{
	if [ -d $serverPath/phpmyadmin ];then
		exit 0
	fi

	mkdir -p ${serverPath}/source/phpmyadmin
	
	VER=5.2.3
	FDIR=phpMyAdmin-${VER}-all-languages
	FILE=phpMyAdmin-${VER}-all-languages.tar.xz
	FILEPATH=$serverPath/source/phpmyadmin/$FILE

	# 优先从项目 GitHub Release 下载（自带国内代理加速）
	GH_URL="https://github.com/clhome/bt_simple/releases/download/init/$FILE"
	github_download $FILEPATH $GH_URL

	# 回退：尝试官方源
	if [ ! -f $FILEPATH ] || ! xz -t $FILEPATH 2>/dev/null; then
		rm -f $FILEPATH 2>/dev/null
		echo "GitHub 源下载失败，尝试官方源..."
		OFFICIAL_URL="https://files.phpmyadmin.net/phpMyAdmin/${VER}/$FILE"
		curl -k -L --connect-timeout 15 --max-time 120 -o $FILEPATH $OFFICIAL_URL
	fi

	# 解压
	if [ -f $FILEPATH ] && xz -t $FILEPATH 2>/dev/null; then
		if [ ! -d $serverPath/source/phpmyadmin/$FDIR ]; then
			cd $serverPath/source/phpmyadmin && tar xJvf $FILE
		fi
	fi

	if [ ! -d $serverPath/source/phpmyadmin/$FDIR ]; then
		echo "下载失败或文件损坏，请检查网络连通性"
		rm -f $FILEPATH 2>/dev/null
		exit 1
	fi
	
	mkdir -p ${serverPath}/phpmyadmin
	cp -r $serverPath/source/phpmyadmin/$FDIR $serverPath/phpmyadmin/
	cd $serverPath/phpmyadmin/ && mv $FDIR phpmyadmin
	rm -rf $serverPath/source/phpmyadmin/$FDIR

	echo "${VER}" > ${serverPath}/phpmyadmin/version.pl
	cd ${rootPath} && python3 ${rootPath}/plugins/phpmyadmin/index.py start
	
	echo '安装完成'
}

Uninstall_phpmyadmin()
{
	cd ${rootPath} && python3 ${rootPath}/plugins/phpmyadmin/index.py stop
	
	rm -rf ${serverPath}/phpmyadmin
	echo '卸载完成'
}

action=$1
if [ "${1}" == 'install' ];then
	Install_phpmyadmin
else
	Uninstall_phpmyadmin
fi
