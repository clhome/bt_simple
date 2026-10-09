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
# sysName 并非 lib.sh 提供的变量（旧版用它判 Darwin，恒为空 → macOS 也走 Linux 分支），
# 统一用上面 uname 的结果判断
VERSION=$2

Install_swap()
{
	echo '正在安装脚本文件...'

	# 清理旧版本可能在 mdserver-web (rootPath) 目录下创建的巨大残留文件夹
	if [ -d "${rootPath}/swap" ]; then
		echo "发现旧版本遗留的 ${rootPath}/swap 目录，正在清理..."
		if [ -f "${rootPath}/swap/swapfile" ]; then
			swapoff "${rootPath}/swap/swapfile" 2>/dev/null
		fi
		rm -rf "${rootPath}/swap"
	fi

	mkdir -p $serverPath/source
	mkdir -p $serverPath/swap
	echo "${VERSION}" > $serverPath/swap/version.pl

	if [ "${SYSOS}" == "Darwin" ];then
		echo "macOS not support swap"
	else
		# 检查是否已有 swapfile；每一步判退出码，dd/mkswap/swapon 失败即中止，
		# 不半途留下半个文件还报「安装完成」
		if [ ! -f ${serverPath}/swap/swapfile ];then
			if ! dd if=/dev/zero of=${serverPath}/swap/swapfile bs=1M count=1024; then
				echo "创建 swapfile 失败，请检查磁盘空间"
				exit 1
			fi
			chmod 600 ${serverPath}/swap/swapfile || exit 1
			if ! mkswap ${serverPath}/swap/swapfile; then
				echo "格式化 swapfile 失败"
				exit 1
			fi
			if ! swapon ${serverPath}/swap/swapfile; then
				echo "启用 swapfile 失败"
				exit 1
			fi
		fi
	fi 

	echo '安装完成'

	cd ${rootPath} && python3 ${rootPath}/plugins/swap/index.py start
	cd ${rootPath} && python3 ${rootPath}/plugins/swap/index.py initd_install
}

Uninstall_swap()
{
	if [ -f ${serverPath}/swap/swapfile ];then
		swapoff ${serverPath}/swap/swapfile
	fi

	if [ -f /usr/lib/systemd/system/swap.service ] || [ -f /lib/systemd/system/swap.service ];then
		systemctl stop swap
		systemctl disable swap
		rm -rf /usr/lib/systemd/system/swap.service
		rm -rf /lib/systemd/system/swap.service
		systemctl daemon-reload
	fi

	if [ -f ${serverPath}/swap/initd/swap ];then
		${serverPath}/swap/initd/swap stop
	fi

	rm -rf ${serverPath}/swap
	
	echo "Uninstall_swap"
}

action=$1
# 显式分支：旧版把 else 当卸载兑底，`bash install.sh`（无参）或任意手误参数
# 都会 swapoff + systemctl disable + rm -rf 插件目录。
case "${action}" in
	'install')
		Install_swap
		;;
	'uninstall')
		Uninstall_swap
		;;
	*)
		echo "usage: $0 install|uninstall"
		exit 1
		;;
esac
