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
	FILE=phpMyAdmin-${VER}-all-languages.tar.gz
	URL="https://files.phpmyadmin.net/phpMyAdmin/${VER}/$FILE"
	
	mw_download $serverPath/source/phpmyadmin/$FILE $URL

	if [ ! -d $serverPath/source/phpmyadmin/$FDIR ];then
		cd $serverPath/source/phpmyadmin  && tar zxvf $FILE
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
