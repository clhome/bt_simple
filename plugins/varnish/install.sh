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

	# 包管理器失败时旧实现照样写安装标记 + 调 start（回 fail 也当成功）= 假成功
	if [ ! -x /usr/sbin/varnishd ] && [ ! -x /usr/bin/varnishd ] && [ ! -x /usr/local/sbin/varnishd ]; then
		echo 'Varnish 安装失败: 未找到 varnishd'
		exit 1
	fi

	out=$(cd ${rootPath} && python3 ${rootPath}/plugins/varnish/index.py start 2>&1)
	if [ "$out" != 'ok' ]; then
		echo "Varnish 启动失败: ${out}"
		exit 1
	fi
	cd ${rootPath} && python3 ${rootPath}/plugins/varnish/index.py initd_install
	echo '安装完成'
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
