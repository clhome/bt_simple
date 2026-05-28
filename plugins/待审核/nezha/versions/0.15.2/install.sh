#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

VERSION=0.15.2

# bash install.sh install 0.15.2
# cd /www/server/mdserver-web/plugins/nezha && bash install.sh install 0.15.2
# cd /Users/midoks/Desktop/mwdev/server/mdserver-web/plugins/nezha && bash install.sh install 0.15.2

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

load_vars() {
	OS=$(uname | tr '[:upper:]' '[:lower:]')
	TARGET_DIR="$serverPath/nezha/dashboard"

	# 检测是否为中国大陆网络环境（通过快速测试 github.com 连接度判定）
	if [[ -z "${CN}" ]]; then
		if ! curl -I -s --connect-timeout 3 https://github.com > /dev/null; then
			CN=true
		fi
	fi
}

# 高可用下载与多镜像源自动 fallback 重试引擎
download_file_with_fallback() {
	local raw_url="${1}"
	local destination="${2}"

	# 提取 github.com 之后的相对路径
	local github_path=$(echo "${raw_url}" | sed 's|https://github.com/||')

	# 定义高可用镜像列表
	local proxies=(
		"https://ghproxy.net/https://github.com/"
		"https://mirror.ghproxy.com/https://github.com/"
		"https://gh-proxy.com/https://github.com/"
		"https://github.com/"
	)

	if [[ "${CN}" != "true" ]]; then
		# 海外直接拉取，如果超时则回退到代理镜像
		proxies=(
			"https://github.com/"
			"https://gh-proxy.com/https://github.com/"
		)
	fi

	local success=false
	for proxy in "${proxies[@]}"; do
		local download_url="${proxy}${github_path}"
		printf "Fetching %s\n" "${download_url}"

		if test -x "$(command -v curl)"; then
			code=$(curl --connect-timeout 10 -sL -w '%{http_code}' "${download_url}" -o "${destination}")
		elif test -x "$(command -v wget)"; then
			code=$(wget -q -t2 -T10 -O "${destination}" --server-response "${download_url}" 2>&1 | awk '/^  HTTP/{print $2}' | tail -1)
		else
			printf "\e[1;31mNeither curl nor wget was available to perform requests.\e[0m\n"
			exit 1
		fi

		if [ "${code}" == "200" ]; then
			printf "\n\e[1;32mDownload succeeded via %s\e[0m\n" "${proxy}"
			success=true
			break
		else
			printf "\e[1;31mDownload failed with code %s via %s, trying next source...\e[0m\n" "${code}" "${proxy}"
			rm -f "${destination}"
		fi
	done

	if [ "${success}" != "true" ]; then
		printf "\e[1;31mAll download mirror sources failed!\e[0m\n"
		exit 1
	fi
}


Install_dashborad(){
	echo '正在安装哪吒监控...'
	mkdir -p $serverPath/source

	if [ ! -f $TARGET_DIR/nezha ];then
		DOWNLOAD_URL="https://github.com/midoks/nezha/releases/download/v${VERSION}/nezha-${OS}-${ARCH}.zip"
		DOWNLOAD_FILE="$(mktemp).zip"
		
		download_file_with_fallback "${DOWNLOAD_URL}" "${DOWNLOAD_FILE}"

		if [ ! -f "${DOWNLOAD_FILE}" ]; then
			echo "下载失败，压缩包文件不存在！"
			exit 1
		fi

		# 验证压缩包有效性，防止空文件残留破坏后续安装
		unzip -t "${DOWNLOAD_FILE}" &>/dev/null
		if [ "$?" != "0" ]; then
			echo "下载的压缩包已损坏，自动清理残留..."
			rm -f "${DOWNLOAD_FILE}"
			exit 1
		fi

		if [ ! -d $TARGET_DIR ]; then
			mkdir -p $TARGET_DIR
		fi

		unzip "${DOWNLOAD_FILE}" -d $TARGET_DIR
		rm -rf "${DOWNLOAD_FILE}"
	fi
}

Install_agent(){
	echo -e "正在下载监控端"
	mkdir -p $serverPath/source

	version=v0.15.1
	AGENT_TARGET_DIR="$serverPath/nezha/agent"

	if [ ! -f $AGENT_TARGET_DIR/nezha-agent ];then
		DOWNLOAD_URL="https://github.com/nezhahq/agent/releases/download/${version}/nezha-agent_${OS}_${ARCH}.zip"
		DOWNLOAD_FILE="$(mktemp).zip"

		download_file_with_fallback "${DOWNLOAD_URL}" "${DOWNLOAD_FILE}"

		if [ ! -f "${DOWNLOAD_FILE}" ]; then
			echo "Agent下载失败，文件不存在！"
			exit 1
		fi

		# 验证压缩包有效性
		unzip -t "${DOWNLOAD_FILE}" &>/dev/null
		if [ "$?" != "0" ]; then
			echo "Agent压缩包已损坏，自动清理..."
			rm -f "${DOWNLOAD_FILE}"
			exit 1
		fi

		if [ ! -d $AGENT_TARGET_DIR ]; then
			mkdir -p $AGENT_TARGET_DIR
		fi
	
		unzip "${DOWNLOAD_FILE}" -d $AGENT_TARGET_DIR
		rm -rf "${DOWNLOAD_FILE}"
	fi
}

Install_App()
{
	load_vars
	get_arch

	Install_dashborad
	Install_agent

	if [ -d $serverPath/nezha ];then
		echo "$VERSION" > $serverPath/nezha/version.pl
		cd ${rootPath} && python3 ${rootPath}/plugins/nezha/index.py init_cfg
	fi
	echo 'install successful'
}

Uninstall_App()
{
	cd ${rootPath} && python3 ${rootPath}/plugins/nezha/index.py initd_uninstall
	cd ${rootPath} && python3 ${rootPath}/plugins/nezha/index.py initd_uninstall_agent
	cd ${rootPath} && python3 ${rootPath}/plugins/nezha/index.py stop
	cd ${rootPath} && python3 ${rootPath}/plugins/nezha/index.py stop_agent
	rm -rf $serverPath/nezha
	echo "install fail"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_App
else
	Uninstall_App
fi
