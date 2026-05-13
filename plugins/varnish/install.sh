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

VERSION=$2

Install_varnish()
{
	echo '正在安装脚本文件...'
	mkdir -p $serverPath/source

	if [ "${sysName}" == "Darwin" ]; then
		brew install varnish
	elif which apt &> /dev/null; then
		apt install varnish -y
	elif which yum &> /dev/null; then
		yum install varnish -y
	elif which pacman &> /dev/null; then
		pacman -Sy --noconfirm varnish
	elif which zypper &> /dev/null; then
		zypper install -y varnish
	else
		echo "Unsupported OS for Varnish"
		exit 1
	fi

	mkdir -p $serverPath/varnish
	echo "1.0" > $serverPath/varnish/version.pl
	echo '安装完成'

	cd ${rootPath} && python3 ${rootPath}/plugins/varnish/index.py start
	cd ${rootPath} && python3 ${rootPath}/plugins/varnish/index.py initd_install
}

Uninstall_varnish()
{
	cd ${rootPath} && python3 ${rootPath}/plugins/varnish/index.py stop
	cd ${rootPath} && python3 ${rootPath}/plugins/varnish/index.py initd_uninstall

	if [ "${sysName}" == "Darwin" ]; then
		brew uninstall varnish
	elif which apt &> /dev/null; then
		apt remove varnish -y
	elif which yum &> /dev/null; then
		yum remove varnish -y
	elif which pacman &> /dev/null; then
		pacman -Rv --noconfirm varnish
	elif which zypper &> /dev/null; then
		zypper remove -y varnish
	fi
	rm -rf $serverPath/varnish
	echo "uninstall varnish"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_varnish
else
	Uninstall_varnish
fi
