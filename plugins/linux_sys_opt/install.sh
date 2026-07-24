#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

VERSION=$2

Install_linux_sys_opt()
{
	echo '正在安装御风Linux系统优化插件...'
	mkdir -p $serverPath/linux_sys_opt
	echo "${VERSION}" > $serverPath/linux_sys_opt/version.pl
	echo '安装完成'
}

Uninstall_linux_sys_opt()
{
	echo '正在卸载内核优化插件并恢复默认...'
    if [ -f /etc/sysctl.d/99-yufeng-server.conf ];then
        rm -f /etc/sysctl.d/99-yufeng-server.conf
        sysctl --system > /dev/null 2>&1
    fi
    if [ -f /etc/systemd/system/disable-thp.service ];then
        systemctl stop disable-thp.service
        systemctl disable disable-thp.service
        rm -f /etc/systemd/system/disable-thp.service
        systemctl daemon-reload
    fi
    if command -v tuned-adm &> /dev/null; then
        tuned-adm profile virtual-guest > /dev/null 2>&1 || true
    fi

	rm -rf $serverPath/linux_sys_opt
	echo "Uninstall_linux_sys_opt"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_linux_sys_opt
else
	Uninstall_linux_sys_opt
fi
