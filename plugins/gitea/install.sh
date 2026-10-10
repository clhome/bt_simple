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

# 版本号由面板传入（`bash install.sh install <version>`）。旧实现直接写死 1.26.1，
# 于是在面板里选 1.17.2/1.18.5/1.22.1/1.24.3 实际都会装成 1.26.1（版本参数被静默忽略）。
VERSION=$2
if [ -z "${VERSION}" ];then
	VERSION=1.26.1
fi
# 版本号会拼进下载 URL 与文件名：只允许数字与点，阻断路径/命令注入
case "${VERSION}" in
	*[!0-9.]*|'') echo "invalid version: ${VERSION}"; exit 1;;
esac
URL_DOWNLOAD=https://github.com/go-gitea/gitea/releases/download

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
	URL="${URL_DOWNLOAD}/v${VERSION}/${file_xz}"
	
	# 改用 GitHub Releases 下载，以便 yf_download 能够自动启用国内的 Github 代理加速
	yf_download $serverPath/source/gitea/$file_xz $URL

	cd $serverPath/source/gitea && xz -k -d $file_xz
	if [ ! -f $file ];then
		echo "download failed: $file"
		exit 1
	fi
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

	# 旧实现无条件 echo 'install success'：下载/解压失败时也报成功（假成功）
	if [ ! -x $serverPath/gitea/gitea ];then
		echo "install failed: $serverPath/gitea/gitea missing"
		exit 1
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
	if [ -d $serverPath/gitea ];then
		echo "uninstall failed: $serverPath/gitea still exists"
		exit 1
	fi
	echo 'uninstall success'
}

action=$1
if [ "${action}" == 'install' ];then
	Install_App
elif [ "${action}" == 'uninstall' ];then
	Uninstall_App
else
	# 旧实现 else 兜底：无参/拼错参数也会执行卸载并 rm -rf 安装目录
	echo "usage: $0 {install|uninstall} [version]"
	exit 1
fi
