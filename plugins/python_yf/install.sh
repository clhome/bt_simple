#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

# 安装目录和标记文件
serverPath=/www/server
install_path=${serverPath}/python_yf

Install_python_yf()
{
	echo "开始安装 御风Python管理器..."
	mkdir -p ${install_path}
	
	# 检查uv是否已安装
	if [ ! -f "$HOME/.local/bin/uv" ]; then
		echo "正在安装 uv 核心组件..."
		curl -LsSf https://astral.sh/uv/install.sh | sh
		if [ $? -ne 0 ]; then
			echo "uv 安装失败，请检查网络！"
			rm -rf ${install_path}
			exit 1
		fi
	else
		echo "uv 核心组件已存在。"
	fi

	echo "安装完成。"
}

Uninstall_python_yf()
{
	echo "正在卸载 御风Python管理器..."
	# 我们只删除插件标志目录，保留 uv 本身以防止影响其他用户或环境，用户可手动删除 uv
	rm -rf ${install_path}
	echo "卸载完成。"
}

action=$1
if [ "${action}" == "install" ]; then
	Install_python_yf
elif [ "${action}" == "uninstall" ]; then
	Uninstall_python_yf
fi
