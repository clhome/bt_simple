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

	# 1. 智能检测系统是否已存在 Docker 引擎（防止覆盖破坏原本正在运行的第三方容器引擎）
	if which docker &> /dev/null; then
		echo '系统已检测到已安装 Docker 引擎，跳过底层引擎安装，直接进行面板对接配置...'
	else
		echo '系统未检测到 Docker 引擎，开始为您安全部署标准 Docker 环境...'
		LOCAL_ADDR=$(get_local_addr)
		if [ "$LOCAL_ADDR" == "cn" ];then
			# 大陆环境通过阿里云加速脚本下载并安装 Docker
			curl -fsSL https://gitee.com/tech-shrimp/docker_installer/releases/download/latest/linux.sh | bash -s docker --mirror Aliyun
		else
			# 海外环境直接通过官方一键脚本下载并安装
			curl -fsSL https://get.docker.com | bash
		fi
		
		# 强制启动并开机自启 Docker 引擎
		systemctl start docker
		systemctl enable docker
	fi

	# 2. 强行创建面板的管理专属目录
	if [ ! -d  $serverPath/docker ];then
		mkdir -p $serverPath/docker
	fi

	# 3. 安装 Python SDK 支持库（注入国内清华加速源以防大陆网络超时卡死）
	echo '正在安装面板配套的 Python 管理库依赖...'
	LOCAL_ADDR=$(get_local_addr)
	if [ "$LOCAL_ADDR" == "cn" ];then
		# 大陆环境采用清华源极速安装
		if [ -f ${rootPath}/bin/pip3 ];then
			${rootPath}/bin/pip3 install docker pytz -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
		else
			pip3 install docker pytz -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
		fi
	else
		# 海外环境采用官方常规源安装
		if [ -f ${rootPath}/bin/pip3 ];then
			${rootPath}/bin/pip3 install docker pytz
		else
			pip3 install docker pytz
		fi
	fi
	
	# 4. 写入面板安装状态和版本标识并启动面板配套后台服务
	if [ -d $serverPath/docker ];then
		echo "${VERSION}" > $serverPath/docker/version.pl
		echo '安装Docker插件成功！'

		cd ${rootPath} && python3 ${rootPath}/plugins/docker/index.py start
		cd ${rootPath} && python3 ${rootPath}/plugins/docker/index.py initd_install
	fi
}

Uninstall_Docker()
{
	# 温和、零破坏性卸载：仅移除面板管理端配置与插件状态，安全保留宿主机底层的公共 Docker 引擎服务和所有容器业务数据！
	rm -rf $serverPath/docker
	echo "卸载Docker插件完成（系统底层Docker引擎服务及您的业务容器已安全保留）"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_Docker
else
	Uninstall_Docker
fi
