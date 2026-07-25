#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
install_tmp='/tmp/bt_install.pl'
pluginPath=/www/server/panel/plugin/pg_docker

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

scriptDir=$(cd "$(dirname "$0")" && pwd)
pluginsDir=$(dirname "$scriptDir")

Check_And_Install_Docker()
{
    echo '正在检查 御风Docker管理器 依赖...'
    
    # 查找 docker 插件的 install.sh 脚本
    dockerInstallScript=""
    if [ -f "$pluginsDir/docker/install.sh" ]; then
        dockerInstallScript="$pluginsDir/docker/install.sh"
    elif [ -f "$scriptDir/../docker/install.sh" ]; then
        dockerInstallScript="$scriptDir/../docker/install.sh"
    elif [ -f "/www/server/panel/plugins/docker/install.sh" ]; then
        dockerInstallScript="/www/server/panel/plugins/docker/install.sh"
    elif [ -f "/www/server/panel/plugin/docker/install.sh" ]; then
        dockerInstallScript="/www/server/panel/plugin/docker/install.sh"
    fi

    # 检查是否已安装 docker 插件 (通过 version.pl 标记判断)
    if [ -f "$serverPath/docker/version.pl" ] || [ -f "/www/server/docker/version.pl" ]; then
        echo '检测到已安装 御风Docker管理器 插件，跳过其重复安装。'
    else
        echo '未检测到 御风Docker管理器 插件，即将优先自动安装 御风Docker管理器 插件...'
        if [ -n "$dockerInstallScript" ] && [ -f "$dockerInstallScript" ]; then
            bash "$dockerInstallScript" install "1.0"
            echo '御风Docker管理器 插件已优先安装完成！'
        else
            echo '警告: 未找到 docker 插件安装脚本，尝试直接检测系统底层 Docker 环境...'
            if ! which docker &> /dev/null; then
                echo '错误: 系统未安装 Docker 且找不到 docker 插件安装脚本，无法继续！'
                exit 1
            fi
        fi
    fi
}

Install_pg_docker()
{
    echo '正在安装 pg_docker 插件...'
    Check_And_Install_Docker
    mkdir -p $pluginPath
    echo 'pg_docker 插件安装完成！'
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
elif [ "${1}" == 'uninstall' ];then
    Uninstall_pg_docker
else
    echo 'Error!';
fi
