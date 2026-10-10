#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

# serverPath 由脚本自身位置推导，异常时（如脚本被放到根目录）拒绝执行任何 mkdir/rm
if [ -z "${serverPath}" ] || [ "${serverPath}" = "/" ];then
	echo "invalid serverPath: ${serverPath}"
	exit 1
fi

Install_jdk()
{
	mkdir -p "$curPath"
	mkdir -p "$serverPath/jdk"
	echo '安装完成'
	echo Successify
}

Uninstall_jdk()
{
	# 只删除本插件目录（curPath 由 BASH_SOURCE 推导），并回读确认，避免假成功
	rm -rf "$curPath"
	if [ -d "$curPath" ];then
		echo "uninstall failed: $curPath still exists"
		exit 1
	fi
	echo '卸载完成'
}

action=$1
if [ "${action}" == 'install' ];then
	Install_jdk
elif [ "${action}" == 'uninstall' ];then
	Uninstall_jdk
else
	# 旧实现 else 兜底：无参/拼错参数也会走卸载并 rm -rf 插件目录
	echo "usage: $0 {install|uninstall}"
	exit 1
fi
