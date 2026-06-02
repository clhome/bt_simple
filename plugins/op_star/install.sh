#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

# cd /www/server/mdserver-web/plugins/op_star && bash install.sh install 1.0
# cd /www/server/mdserver-web && python3 plugins/op_star/index.py start
# cd /www/server/mdserver-web && python3 plugins/op_star/index.py stop

# 引入统一的 GitHub 下载函数库
_gh_lib=$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd ../../scripts 2>/dev/null && pwd)/github_download.sh
if [ -f "$_gh_lib" ]; then
    source "$_gh_lib"
fi

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

action=$1
version=$2
sys_os=`uname`

if [ -f ${rootPath}/bin/activate ];then
	source ${rootPath}/bin/activate
fi

Install_App(){
	echo '正在准备安装 OP 高性能防火墙 (OpenStar)...'
	mkdir -p $serverPath/source/op_star
	mkdir -p $serverPath/openstar

	# 检查是否已安装 git，未安装则进行安装
	if ! command -v git &> /dev/null; then
		echo "正在安装 git 客户端以获取防火墙内核..."
		if [ -f /usr/bin/yum ]; then
			yum install -y git
		elif [ -f /usr/bin/apt-get ]; then
			apt-get update && apt-get install -y git
		fi
	fi

	# 克隆 starjun/openstar 仓库
	if [ ! -d $serverPath/openstar/.git ]; then
		echo "正在克隆 OpenStar 核心代码库..."
		rm -rf $serverPath/openstar
		
		github_clone "$serverPath/openstar" "https://github.com/clhome/openstar.git"
		if [ "$?" != "0" ]; then
			echo "克隆 OpenStar 失败！"
			exit 1
		fi
	fi

	# 确保 logs 目录存在且有权限
	mkdir -p $serverPath/openstar/logs
	chmod -R 755 $serverPath/openstar

	echo "${version}" > $serverPath/openstar/version.pl
	echo 'OpenStar 核心代码部署成功！'

	# 启动服务
	cd ${rootPath} && python3 ${rootPath}/plugins/op_star/index.py start
	sleep 2
	cd ${rootPath} && python3 ${rootPath}/plugins/op_star/index.py reload
}

Uninstall_App(){
	echo '正在停止并卸载 OP 高性能防火墙...'
	cd ${rootPath} && python3 ${rootPath}/plugins/op_star/index.py stop
	rm -rf $serverPath/openstar
	echo '卸载成功！'
}

action=$1
if [ "${1}" == 'install' ];then
	Install_App
else
	Uninstall_App
fi
