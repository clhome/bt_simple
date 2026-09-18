#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(cd "$curPath/../../../.."; pwd)
serverPath=$(dirname "$rootPath")
sourcePath=${serverPath}/source
sysName=`uname`

version=8.0.x
PHP_VER=80


Install_php()
{
#------------------------ install start ------------------------------------#


yum install -y php80 php80-php-fpm 
if [ "$?" == "0" ];then
	mkdir -p $serverPath/php-yum/${PHP_VER}
fi

#------------------------ install end ------------------------------------#
}

Uninstall_php()
{
	# $serverPath/php-ya/init.d/php${PHP_VER} stop
	rm -rf $serverPath/php-yum/${PHP_VER}
	echo "卸载php-${version}..."
}

action=${1}
if [ "${1}" == 'install' ];then
	Install_php
else
	Uninstall_php
fi
