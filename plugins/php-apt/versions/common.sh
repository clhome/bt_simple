#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
export DEBIAN_FRONTEND=noninteractive

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

version=$1
action=$2
extName=$3

if ! command -v bc >/dev/null 2>&1; then
	apt-get install -y bc 2>/dev/null || true
fi

# 过滤 PHP 内核已内置扩展（避免 apt 报错 Unable to locate package）
if [ "$extName" == "iconv" ] || [ "$extName" == "exif" ]; then
	echo "Extension ${extName} is built-in to PHP core (no separate deb package required)."
	exit 0
fi

FILE=${curPath}/${version}/${extName}.sh
FILE_COMMON=${curPath}/common/${extName}.sh

if [ "$action" == 'install' ];then
	if [ -f $FILE ];then
		bash ${curPath}/${version}/${extName}.sh install $version
	elif [ -f $FILE_COMMON ];then
		bash ${FILE_COMMON} install ${version}
	else
		apt-get install -y php${version}-${extName}
	fi
fi

if [ "$action" == 'uninstall' ];then
	if [ -f $FILE ];then
		bash ${curPath}/${version}/${extName}.sh uninstall $version
	elif [ -f $FILE_COMMON ];then
		bash ${FILE_COMMON} uninstall ${version}
	else
		apt-get remove -y php${version}-${extName}
	fi
fi

if [ "$PHP_EXT_NO_RESTART" != "1" ]; then
	php_status=`systemctl status php${version}-fpm 2>/dev/null | grep -E "inactive|failed"`
	if [ "$php_status" == "" ];then
		systemctl reset-failed php${version}-fpm 2>/dev/null || true
		systemctl restart php${version}-fpm 2>/dev/null || service php${version}-fpm restart 2>/dev/null || true
	fi
fi