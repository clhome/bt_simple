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

Install_Docker()
{
	echo '正在安装脚本文件...'
	mkdir -p $serverPath/source

	if [ ! -d  $serverPath/docker ];then
		LOCAL_ADDR=$(get_local_addr)
		if [ "$LOCAL_ADDR" == "cn" ];then
			curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
		else
			curl -fsSL https://get.docker.com | bash
		fi
		mkdir -p $serverPath/docker
	fi

	# 安装 Python 库以支持面板管理
	if [ -f ${rootPath}/bin/pip3 ];then
		${rootPath}/bin/pip3 install docker pytz
	else
		pip3 install docker pytz
	fi
	
	if [ -d $serverPath/docker ];then
		echo "${VERSION}" > $serverPath/docker/version.pl
		echo '安装Docker完成'

		cd ${rootPath} && python3 ${rootPath}/plugins/docker/index.py start
		cd ${rootPath} && python3 ${rootPath}/plugins/docker/index.py initd_install
	fi
}

Uninstall_Docker()
{
	CMD=yum
	which apt &> /dev/null && CMD=apt

	if [ -f /usr/lib/systemd/system/docker.service ];then
		systemctl stop docker
		systemctl disable docker
		rm -rf /usr/lib/systemd/system/docker.service
		systemctl daemon-reload
	fi

	$CMD remove -y docker docker-ce-cli containerd.io

	rm -rf $serverPath/docker
	echo "卸载Docker完成"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_Docker
else
	Uninstall_Docker
fi
