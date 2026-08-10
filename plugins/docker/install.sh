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

	# 0. 安装基础依赖工具 rsync（用于保障 Docker 目录安全迁移功能）
	if ! which rsync &> /dev/null; then
		echo '正在补充安装基础依赖工具 rsync...'
		if [ -f /usr/bin/yum ]; then
			yum install -y rsync
		elif [ -f /usr/bin/apt-get ]; then
			apt-get update -y && apt-get install -y rsync
		fi
	fi

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
	install_python_deps() {
		local pip_cmd=$1
		local LOCAL_ADDR=$(get_local_addr)
		if [ "$LOCAL_ADDR" == "cn" ]; then
			# 依次尝试清华源、阿里云源和官方源
			$pip_cmd install docker pytz -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
			if [ $? -ne 0 ]; then
				echo "清华源安装失败，尝试使用阿里云源..."
				$pip_cmd install docker pytz -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
				if [ $? -ne 0 ]; then
					echo "阿里云源安装失败，尝试使用官方源..."
					$pip_cmd install docker pytz
				fi
			fi
		else
			$pip_cmd install docker pytz
		fi
	}

	if [ -f ${rootPath}/bin/pip3 ];then
		install_python_deps "${rootPath}/bin/pip3"
	else
		install_python_deps "pip3"
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
