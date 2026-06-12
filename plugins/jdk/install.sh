#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

Install_jdk()
{
	mkdir -p $curPath
	mkdir -p $serverPath/jdk
	echo '安装完成' > $install_tmp
	echo Successify
}

Uninstall_jdk()
{
	rm -rf $curPath
	echo '卸载完成' > $install_tmp
}

action=$1
if [ "${1}" == 'install' ];then
	Install_jdk
else
	Uninstall_jdk
fi
