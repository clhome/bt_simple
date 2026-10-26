#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH



curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

# 版本脚本退出码必须透传（《问题报告》P1-5 机制 C）：见 scripts/lib_version_step.sh
_yf_step_lib="${rootPath}/scripts/lib_version_step.sh"
if [ -f "${_yf_step_lib}" ]; then
	source "${_yf_step_lib}"
fi

sysName=`uname`
action=$1
type=$2

VERSION=$2
openrestyDir=${serverPath}/source/apache

if id www &> /dev/null ;then 
    echo "www uid is `id -u www`"
    echo "www shell is `grep "^www:" /etc/passwd |cut -d':' -f7 `"
else
    groupadd www
	useradd -g www -s /bin/bash www
fi

if [ "${action}" == "upgrade" ];then
	yf_version_step "${action}" "${VERSION}" "$curPath/versions/$2/install.sh" || exit $?
	
	echo "${VERSION}" > $serverPath/apache/version.pl

	mkdir -p $serverPath/web_conf/php/conf
	echo 'set $PHP_ENV 0;' > $serverPath/web_conf/php/conf/enable-php-00.conf

	#初始化 
	cd ${rootPath} && python3 ${rootPath}/plugins/apache/index.py start
	cd ${rootPath} && python3 ${rootPath}/plugins/apache/index.py initd_install
	exit 0
fi


if [ "${2}" == "" ];then
	echo '缺少安装脚本版本...'
	exit 0
fi 

if [ "${action}" == "uninstall" ];then
	if [ -f /usr/lib/systemd/system/httpd.service ] || [ -f /lib/systemd/system/httpd.service ];then
		systemctl stop httpd
		rm -f /usr/lib/systemd/system/httpd.service
		rm -f /lib/systemd/system/httpd.service
		systemctl daemon-reload
	fi

	if [ -f $serverPath/apache/init.d/httpd ];then
		$serverPath/apache/init.d/httpd stop
	fi

	rm -rf $serverPath/apache
fi

yf_version_step "${action}" "${VERSION}" "$curPath/versions/$2/install.sh" || exit $?

if [ "${action}" == "install" ] && [ -d $serverPath/apache ];then
	echo "${VERSION}" > $serverPath/apache/version.pl

	mkdir -p $serverPath/web_conf/php/conf
	echo 'set $PHP_ENV 0;' > $serverPath/web_conf/php/conf/enable-php-00.conf

	#初始化 
	cd ${rootPath} && python3 ${rootPath}/plugins/apache/index.py start
	cd ${rootPath} && python3 ${rootPath}/plugins/apache/index.py initd_install
fi
