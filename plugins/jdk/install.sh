#!/bin/bash
PATH=/www/server/panel/pyenv/bin:/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

pluginPath=/www/server/panel/plugin/jdk

Install_jdk()
{
	mkdir -p $pluginPath
	mkdir -p /www/server/jdk
	echo '安装完成' > $install_tmp
	echo Successify
}

Uninstall_jdk()
{
	rm -rf $pluginPath
	echo '卸载完成' > $install_tmp
}

action=$1
if [ "${1}" == 'install' ];then
	Install_jdk
else
	Uninstall_jdk
fi
