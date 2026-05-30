#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

VERSION=$2
APP_NAME=yufeng_systemd

Install_App()
{
	echo '正在安装脚本文件...'
	mkdir -p $serverPath/$APP_NAME
	echo "$VERSION" > $serverPath/$APP_NAME/version.pl
	echo 'install complete'
}

Uninstall_App()
{
	rm -rf $serverPath/$APP_NAME
	echo "uninstall completed"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_App
else
	Uninstall_App
fi
