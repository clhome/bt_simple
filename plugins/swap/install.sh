#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

SYSOS=`uname`
VERSION=$2

Install_swap()
{
	if [ -d $serverPath/swap ];then
		exit 0
	fi

	echo '正在安装脚本文件...'
	mkdir -p $serverPath/source
	mkdir -p $serverPath/swap
	echo "${VERSION}" > $serverPath/swap/version.pl

	if [ "$sysName" == "Darwin" ];then
		echo "macOS not support swap"
	else
		# 检查是否已有 swapfile
		if [ ! -f $serverPath/swap/swapfile ];then
			dd if=/dev/zero of=$serverPath/swap/swapfile bs=1M count=1024
			chmod 600 $serverPath/swap/swapfile
			mkswap $serverPath/swap/swapfile
			swapon $serverPath/swap/swapfile
		fi
	fi 

	echo '安装完成'

	cd ${rootPath} && python3 ${rootPath}/plugins/swap/index.py start
	cd ${rootPath} && python3 ${rootPath}/plugins/swap/index.py initd_install
}

Uninstall_swap()
{
	if [ -f $serverPath/swap/swapfile ];then
		swapoff $serverPath/swap/swapfile
	fi

	if [ -f /usr/lib/systemd/system/swap.service ] || [ -f /lib/systemd/system/swap.service ];then
		systemctl stop swap
		systemctl disable swap
		rm -rf /usr/lib/systemd/system/swap.service
		rm -rf /lib/systemd/system/swap.service
		systemctl daemon-reload
	fi

	if [ -f $serverPath/swap/initd/swap ];then
		$serverPath/swap/initd/swap stop
	fi

	rm -rf $serverPath/swap
	
	echo "Uninstall_swap"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_swap
else
	Uninstall_swap
fi
