# -*- coding: utf-8 -*-
#!/bin/bash

PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
export DEBIAN_FRONTEND=noninteractive

# https://downloads.mysql.com/archives/community/

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.."; pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")
sysName=`uname`

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

myDir=${serverPath}/source/mysql-community

OS_ARCH=`arch`
MYSQL_VER=8.4.9
SUFFIX_NAME=${MYSQL_VER}-linux-glibc2.28-${OS_ARCH}

COMMUNITY_INSTALL()
{
    mkdir -p $myDir
    mkdir -p $serverPath/mysql-community

    # Linux - Generic
    URL="https://cdn.mysql.com/Downloads/MySQL-8.4/mysql-${SUFFIX_NAME}.tar.xz"
    mw_download ${myDir}/mysql-${SUFFIX_NAME}.tar.xz ${URL}

    if [ -f ${myDir}/mysql-${SUFFIX_NAME}.tar.xz ];then
        cd ${myDir} && tar -Jxf ${myDir}/mysql-${SUFFIX_NAME}.tar.xz
        cp -rf ${myDir}/mysql-${SUFFIX_NAME}/* $serverPath/mysql-community
        rm -rf $myDir/mysql-${SUFFIX_NAME}
    else
        return 1
    fi
}

COMMUNITY_UNINSTALL()
{
    rm -rf $myDir/mysql-${SUFFIX_NAME}
}

Install_mysql()
{
	echo '正在安装脚本文件...'
	COMMUNITY_INSTALL
	if [ "$?" == "0" ];then
		mkdir -p $serverPath/mysql-community
		echo '8.4' > $serverPath/mysql-community/version.pl
		echo '安装完成'
	else
		echo '8.4' > $serverPath/mysql-community/version.pl
		echo "暂时不支持该系统或下载失败"
        exit 1
	fi
}

Uninstall_mysql()
{
	COMMUNITY_UNINSTALL
	rm -rf $serverPath/mysql-community
	echo '卸载完成'
}

action=$1
if [ "${1}" == 'install' ];then
	Install_mysql
else
	Uninstall_mysql
fi
