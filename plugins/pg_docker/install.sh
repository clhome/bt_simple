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

Install_pg_docker()
{
    echo '正在安装 pg_docker 插件...'
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
