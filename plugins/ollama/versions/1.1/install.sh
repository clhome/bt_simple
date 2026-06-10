#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

VERSION=1.1
sysName=`uname`

# bash install.sh install 1.0
# cd /www/server/mdserver-web/plugins/ollama && bash install.sh install 1.0
# cd /Users/midoks/Desktop/mwdev/server/mdserver-web/plugins/ollama && bash install.sh install 1.0

bash ${rootPath}/scripts/getos.sh



OSNAME=`cat ${rootPath}/data/osname.pl`
OSNAME_ID=`cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}' | awk -F "\"" '{print $2}'`


ARCH="amd64"

get_arch() {
	TMP_ARCH=`arch`
	if [ "$TMP_ARCH" == "x86_64" ];then
		ARCH="amd64"
	elif [ "$TMP_ARCH" == "aarch64" ];then
		ARCH="arm64"
	else
		echo $ARCH
	fi
}

Install_App()
{
	echo "正在下载并安装 Ollama (使用镜像加速下载)..."
	
	# 统一调用系统自带的 GitHub 下载辅助库，获取 _GH_PROXY_LIST 代理列表
	source ${rootPath}/scripts/github_download.sh

	OLLAMA_INSTALL_SCRIPT=$(mktemp)
	curl -fsSL https://ollama.com/install.sh -o $OLLAMA_INSTALL_SCRIPT
	
	if [ ! -f "$OLLAMA_INSTALL_SCRIPT" ] || [ ! -s "$OLLAMA_INSTALL_SCRIPT" ]; then
		echo "下载 Ollama 安装脚本失败!"
		exit 1
	fi

	local success=false
	for proxy in "${_GH_PROXY_LIST[@]}"; do
		echo "尝试使用加速节点: $proxy"
		cat $OLLAMA_INSTALL_SCRIPT | sed "s#https://ollama.com/download#${proxy}https://github.com/ollama/ollama/releases/latest/download#g" | sh
		if [ $? -eq 0 ] && [ -f /usr/local/bin/ollama ]; then
			success=true
			break
		else
			echo "加速节点 $proxy 安装失败，尝试下一个..."
		fi
	done

	rm -f $OLLAMA_INSTALL_SCRIPT

	if [ "$success" != "true" ]; then
		echo "所有节点均失败，安装失败!"
		exit 1
	fi

	mkdir -p $serverPath/ollama
	echo "$VERSION" > $serverPath/ollama/version.pl

	cd ${rootPath} && python3 ${rootPath}/plugins/ollama/index.py start
	echo 'install successful'
}

Uninstall_App()
{
	cd ${rootPath} && python3 ${rootPath}/plugins/ollama/index.py stop

	systemctl stop ollama.service
	systemctl disable ollama.service
	rm -rf /etc/systemd/system/ollama.service
	systemctl daemon-reload
	rm -rf $(which ollama)
	rm -rf /usr/share/ollama
	rm -rf ~/.ollama

	userdel ollama
	groupdel ollama

	if command -v apt &> /dev/null; then
		apt remove -y ollama
	fi

	rm -rf $serverPath/ollama
	echo "uninstall successful"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_App
else
	Uninstall_App
fi
