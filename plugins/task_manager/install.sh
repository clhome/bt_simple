#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

# 路径校准
rootPath=/www/server/mdserver-web
serverPath=/www/server

VERSION=$2

# 获取镜像源
PIPSRC="https://pypi.org/simple"
if [ -f ${rootPath}/data/is_china.pl ];then
    PIPSRC="https://pypi.tuna.tsinghua.edu.cn/simple"
fi

Install_App()
{
	echo '正在安装脚本文件...'
	mkdir -p $serverPath/task_manager

	# 安装依赖库
	if [ -f /usr/bin/apt ]; then
		apt install libpcap-dev build-essential -y
	fi

	if [ -f /usr/bin/yum ]; then
		yum install libpcap-devel gcc -y
	fi

	if [ -f /usr/bin/dnf ]; then
		dnf install libpcap-devel gcc -y
	fi

	# 使用面板专属 Python 环境进行安装
	# 显式指定 pip3 路径，避免环境变量干扰
	PANEL_PIP=${rootPath}/bin/pip3
	if [ ! -f $PANEL_PIP ];then
		PANEL_PIP=pip3
	fi

	echo "使用镜像源: $PIPSRC"
	$PANEL_PIP install pypcap -i $PIPSRC

	# 检查是否安装成功
	${rootPath}/bin/python3 -c "import pcap" 2>/dev/null
	if [ $? != 0 ];then
		echo "pypcap 安装失败，尝试直接安装..."
		$PANEL_PIP install pypcap
	fi

	# 安全加固：防止命令注入 (虽然安装脚本由面板调用，但也应保持规范)
	# 此处无需 shlex，因为是 shell 脚本内部变量

	echo "$VERSION" > $serverPath/task_manager/version.pl
	echo "安装任务管理器成功"
}

Uninstall_App()
{
	rm -rf $serverPath/task_manager
	echo "卸载成功"
}

action=$1
if [ "${action}" == 'install' ];then
	Install_App
elif [ "${action}" == 'uninstall' ];then
	Uninstall_App
fi
