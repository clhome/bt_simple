#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
install_tmp='/tmp/bt_install.pl'
pluginPath=/www/server/panel/plugin/pg_docker

Install_pg_docker()
{
    echo '正在安装 pg_docker 插件...'
    mkdir -p $pluginPath
    echo '安装完成'
}

Uninstall_pg_docker()
{
    echo '正在卸载 pg_docker 插件...'
    rm -rf $pluginPath
    echo '卸载完成'
}

action=$1
if [ "${1}" == 'install' ];then
    Install_pg_docker
elif  [ "${1}" == 'uninstall' ];then
    Uninstall_pg_docker
else
    echo 'Error!';
fi
