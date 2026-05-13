#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

VERSION=$2

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

Install_App()
{
	echo '正在安装脚本文件...'
	mkdir -p $serverPath/task_manager

	if [ -f /usr/bin/apt ]; then
		apt install libpcap-dev -y
	fi

	if [ -f /usr/bin/yum ]; then
		yum install libpcap-devel -y
	fi

	if [ -f /usr/bin/dnf ]; then
		dnf install libpcap-devel -y
	fi

	pip3 install pypcap

	echo "$VERSION" > $serverPath/task_manager/version.pl
	echo "安装任务管理器成功"
}

Uninstall_App()
{	
	rm -rf $serverPath/task_manager
	echo "卸载任务管理器成功"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_App
else
	Uninstall_App
fi
