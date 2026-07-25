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
if [ -z "$VERSION" ]; then
    VERSION="1.0"
fi

Check_And_Install_Docker()
{
    echo '正在检查 御风Docker管理器 依赖...'
    
    # 获取插件根目录
    pluginsDir=$(dirname "$curPath")
    dockerInstallScript="$pluginsDir/docker/install.sh"

    # 检查是否已安装 docker 插件 (通过 version.pl 标记判断)
    if [ -f "$serverPath/docker/version.pl" ]; then
        echo '检测到已安装 御风Docker管理器 插件，跳过其重复安装。'
    else
        echo '未检测到 御风Docker管理器 插件，即将优先自动安装 御风Docker管理器 插件...'
        if [ -f "$dockerInstallScript" ]; then
            # 切换到 plugins 目录执行，确保 docker 的 install.sh (依赖 pwd) 也能获取正确的路径
            (cd "$pluginsDir" && bash docker/install.sh install "1.0")
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
    mkdir -p $serverPath/pg_docker
    echo "${VERSION}" > $serverPath/pg_docker/version.pl
    echo 'pg_docker 插件安装完成！'
}

Uninstall_pg_docker()
{
    echo '正在卸载 pg_docker 插件...'
    rm -rf $serverPath/pg_docker
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
