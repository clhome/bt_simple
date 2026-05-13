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

VERSION=1.26.1
URL_DOWNLOAD=https://dl.gitea.com

sysName=`uname`
sysArch=`arch`

Install_Rsync(){
	# 检查 rsync
	if ! command -v rsync &> /dev/null; then
		if which apt &> /dev/null; then
			apt install -y rsync
		elif which yum &> /dev/null; then
			yum install -y rsync
		elif which pacman &> /dev/null; then
			pacman -Sy --noconfirm rsync
		fi
	fi
}

Install_App()
{
	Install_Rsync

	mkdir -p $serverPath/source/gitea

	if ! id www &> /dev/null; then
	    groupadd www
		useradd -g www www
	fi

	if [ "$sysName" != "Darwin" ];then
		if [ ! -d /home/www ];then
			mkdir -p /home/www
			chown -R www:www /home/www
		fi
	fi

	echo '正在安装脚本文件...'
	
	if [ "$sysName" == "Darwin" ];then
		file=gitea-${VERSION}-darwin-10.12-amd64
	else
		if [ "$sysArch" == "aarch64" ] || [ "$sysArch" == "arm64" ];then
			file=gitea-${VERSION}-linux-arm64
		else
			file=gitea-${VERSION}-linux-amd64
		fi
	fi

	file_xz="${file}.xz"
	URL="${URL_DOWNLOAD}/gitea/${VERSION}/${file_xz}"
	
	# Gitea 官方下载点在国内可能较慢，mw_download 会处理 GitHub 但这里是 dl.gitea.com
	# 我们可以尝试使用 ghp.ci 代理如果需要，但 gitea.com 主要是二进制
	mw_download $serverPath/source/gitea/$file_xz $URL

	cd $serverPath/source/gitea && xz -k -d $file_xz
	if [ -f $file ];then
		mkdir -p $serverPath/gitea
		mv $serverPath/source/gitea/$file $serverPath/gitea/gitea
		chmod +x $serverPath/gitea/gitea
		chown -R www:www $serverPath/gitea
	fi

	if [ -d $serverPath/gitea ];then
		echo $VERSION > $serverPath/gitea/version.pl
		cd ${rootPath} && python3 plugins/gitea/index.py start
		cd ${rootPath} && python3 plugins/gitea/index.py initd_install
	fi

	echo 'install success'
}

Uninstall_App()
{
	if [ -f /usr/lib/systemd/system/gitea.service ];then
		systemctl stop gitea
		systemctl disable gitea
		rm -rf /usr/lib/systemd/system/gitea.service
		systemctl daemon-reload
	fi

	if [ -f $serverPath/gitea/initd/gitea ];then
		$serverPath/gitea/initd/gitea stop
	fi

	rm -rf $serverPath/gitea
	echo 'uninstall success'
}

action=$1
if [ "${1}" == 'install' ];then
	Install_App
else
	Uninstall_App
fi
