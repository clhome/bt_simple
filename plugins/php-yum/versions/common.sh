#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

version=$1
action=$2
extName=$3

# 参数白名单（与 index.py 的 isPhpVersion / 扩展名正则同口径）：
# version 会被拼进 yum 包名与文件路径，extName 同理，任一非法即拒绝，杜绝命令注入。
if ! printf '%s' "$version" | grep -Eq '^[0-9]{1,3}$'; then
	echo "ERROR: invalid version: ${version}" >&2
	exit 1
fi
if ! printf '%s' "$extName" | grep -Eq '^[a-zA-Z0-9_-]+$'; then
	echo "ERROR: invalid extension name: ${extName}" >&2
	exit 1
fi

# 过滤 PHP 内核内置扩展（已在 php-common 中内置）
if [ "$extName" == "iconv" ] || [ "$extName" == "exif" ] || [ "$extName" == "openssl" ] || [ "$extName" == "gettext" ]; then
	echo "Extension ${extName} is built-in to PHP core common package."
	exit 0
fi

FILE=${curPath}/${version}/${extName}.sh
FILE_COMMON=${curPath}/common/${extName}.sh

if [ "$action" == 'install' ];then
	if [ -f "$FILE" ];then
		bash "${curPath}/${version}/${extName}.sh" install
	elif [ -f "$FILE_COMMON" ];then
		bash "${FILE_COMMON}" install "${version}"
	else
		# 智能精确安装，避免盲目双重调用
		if [ "$extName" == "redis" ]; then
			yum install -y php${version}-php-pecl-redis5 2>/dev/null || yum install -y php${version}-php-pecl-redis
		elif [ "$extName" == "memcached" ] || [ "$extName" == "mongodb" ] || [ "$extName" == "zip" ] || [ "$extName" == "mcrypt" ]; then
			yum install -y php${version}-php-pecl-${extName} 2>/dev/null || yum install -y php${version}-php-${extName}
		else
			yum install -y php${version}-php-${extName} 2>/dev/null || yum install -y php${version}-php-pecl-${extName}
		fi
	fi
fi

if [ "$action" == 'uninstall' ];then
	if [ -f "$FILE" ];then
		bash "${curPath}/${version}/${extName}.sh" uninstall
	elif [ -f "$FILE_COMMON" ];then
		bash "${FILE_COMMON}" uninstall "${version}"
	else
		yum remove -y php${version}-php-${extName} php${version}-php-pecl-${extName} php${version}-php-pecl-redis5 2>/dev/null || true
	fi
fi

if [ "$PHP_EXT_NO_RESTART" != "1" ]; then
	php_status=`systemctl status php${version}-php-fpm 2>/dev/null | grep -E "inactive|failed"`
	if [ "$php_status" == "" ];then
		systemctl reset-failed php${version}-php-fpm 2>/dev/null || true
		systemctl restart php${version}-php-fpm 2>/dev/null || service php${version}-php-fpm restart 2>/dev/null || true
	fi
fi


