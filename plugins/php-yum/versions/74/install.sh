#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(cd "$curPath/../../../.."; pwd)
serverPath=$(dirname "$rootPath")
sourcePath=${serverPath}/source
sysName=`uname`

version=7.4.x
PHP_VER=74


Install_php()
{
#------------------------ install start ------------------------------------#
# P1-新：yum 失败必须中止。
#   历史写法是 `yum install -y ...` 后只判 `$?` 去 mkdir，失败也就「不建目录」，
#   函数返回 0 → 外层当成安装成功；在 Debian/Ubuntu 上 `yum` 直接 127，
#   面板任务却是 exit 0（虚假成功）。这里失败即非 0 退出，并把原因说清楚。
if ! command -v yum >/dev/null 2>&1; then
	echo "[ERROR] 当前系统没有 yum，PHP[YUM] 渠道只支持 RHEL 系（CentOS/Rocky/Alma/RHEL/openEuler 等）；Debian/Ubuntu 请用 PHP[APT] 渠道" >&2
	exit 1
fi

if ! yum install -y php74 php74-php-fpm; then
	echo "[ERROR] yum 安装 php74 / php74-php-fpm 失败（见上方 yum 输出）" >&2
	exit 1
fi

mkdir -p "$serverPath/php-yum/${PHP_VER}"
#------------------------ install end ------------------------------------#
}

Uninstall_php()
{
	yum remove -y php74 php74-php-fpm php74-*
	rm -rf $serverPath/php-yum/${PHP_VER}
	echo "卸载php-${version}..."
}

action=${1}
if [ "${1}" == 'install' ];then
	Install_php
else
	Uninstall_php
fi
