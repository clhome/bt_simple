#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

VERSION=0.9.15
URL_DOWNLOAD=https://github.com/DNSCrypt/doh-server/releases/download

sysName=`uname`
sysArch=`arch`

Install_App()
{
	mkdir -p $serverPath/source/doh
	echo '正在安装脚本文件...'

	if [ "$sysName" == "Darwin" ];then
		echo "macOS not support doh-proxy binary"
		exit 1
	fi

	if [ "$sysArch" == "aarch64" ] || [ "$sysArch" == "arm64" ];then
		file=doh-proxy_${VERSION}_linux-aarch64
	else
		file=doh-proxy_${VERSION}_linux-x86_64
	fi

	file_xz="${file}.tar.bz2"
	URL="${URL_DOWNLOAD}/${VERSION}/${file_xz}"
	
	mw_download $serverPath/source/doh/$file_xz $URL

	if [ -f $serverPath/source/doh/$file_xz ];then
		cd $serverPath/source/doh && tar -xjf $file_xz
	fi
		
	if [ -f $serverPath/source/doh/doh-proxy ];then
		mkdir -p $serverPath/doh
		mv $serverPath/source/doh/doh-proxy $serverPath/doh
	fi

	if [ -d $serverPath/doh ];then
		echo $VERSION > $serverPath/doh/version.pl
		cd ${rootPath} && python3 plugins/doh/index.py start
		cd ${rootPath} && python3 plugins/doh/index.py initd_install
	fi

	echo 'install doh success'
}

Uninstall_App()
{
	if [ -f /usr/lib/systemd/system/doh.service ];then
		systemctl stop doh
		systemctl disable doh
		rm -rf /usr/lib/systemd/system/doh.service
		systemctl daemon-reload
	fi

	rm -rf $serverPath/doh
	echo 'uninstall doh success'
}


action=$1
if [ "${1}" == 'install' ];then
	Install_App
else
	Uninstall_App
fi
