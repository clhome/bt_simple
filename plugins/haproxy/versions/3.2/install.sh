#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")
sysName=`uname`

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

VERSION=3.2.19
MIN_VERSION=3.2
Install_App()
{
	echo '正在安装Haproxy软件...'
	mkdir -p $serverPath/haproxy

	APP_DIR=${serverPath}/source/haproxy
	mkdir -p $APP_DIR
	echo $MIN_VERSION > $serverPath/haproxy/version.pl

	URL="https://www.haproxy.org/download/${MIN_VERSION}/src/haproxy-${VERSION}.tar.gz"
	mw_download ${APP_DIR}/haproxy-${VERSION}.tar.gz ${URL}
	
	if [ ! -d ${APP_DIR}/haproxy-${VERSION} ];then
		cd ${APP_DIR} && tar -zxvf haproxy-${VERSION}.tar.gz
	fi

	CPU_CORES=$(get_cpu_cores)

	if [ "$sysName" == "Darwin" ];then
		cd ${APP_DIR}/haproxy-${VERSION} && make -j${CPU_CORES} TARGET=osx && make install PREFIX=$serverPath/haproxy
	else
		cd ${APP_DIR}/haproxy-${VERSION} && make -j${CPU_CORES} TARGET=linux-glibc && make install PREFIX=$serverPath/haproxy
	fi

	echo '安装Haproxy成功'

	# Haproxy日志配置
	if [ -f /etc/rsyslog.conf ];then
		find_ha=`cat /etc/rsyslog.conf | grep haproxy`
		if [ "$find_ha" == "" ];then
			echo "local0.*  ${serverPath}/haproxy/haproxy.log" >> /etc/rsyslog.conf
			if [ -f /usr/bin/systemctl ]; then
				systemctl restart rsyslog
			fi
		fi
	fi

	# 删除解压源码
	if [ -d ${APP_DIR}/haproxy-${VERSION} ];then
		rm -rf ${APP_DIR}/haproxy-${VERSION}
	fi
}

Uninstall_App()
{
	if [ -f $serverPath/haproxy/initd/haproxy ];then
		$serverPath/haproxy/initd/haproxy stop
	fi

	rm -rf $serverPath/haproxy
	echo "卸载Haproxy成功"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_App
else
	Uninstall_App
fi
