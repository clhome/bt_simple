#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(cd "$curPath/../../../.."; pwd)
serverPath=$(dirname "$rootPath")
sourcePath=${serverPath}/source
sysName=`uname`

version=8.5.x
PHP_VER=85
# php85 系 Remi modular 分支包名（remi-release 由 plugins/php-yum/install.sh 统一注入），
# 8.5 分支的 CVE-2026-109618/109619 修复由 Remi 回移补丁承担。


Install_php()
{
#------------------------ install start ------------------------------------#
yum install -y php85 php85-php-fpm
if [ "$?" == "0" ];then
	mkdir -p $serverPath/php-yum/${PHP_VER}
fi

#------------------------ install end ------------------------------------#
}

Uninstall_php()
{
	yum remove -y php85 php85-php-fpm php85-*
	rm -rf $serverPath/php-yum/${PHP_VER}
	echo "卸载php-${version}..."
}

action=${1}
if [ "${1}" == 'install' ];then
	Install_php
else
	Uninstall_php
fi
