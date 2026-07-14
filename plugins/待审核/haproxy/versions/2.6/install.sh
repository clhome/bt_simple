#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")
sysName=`uname`

bash ${rootPath}/scripts/getos.sh
OSNAME=`cat ${rootPath}/data/osname.pl`
OSNAME_ID=`cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}' | awk -F "\"" '{print $2}'`


VERSION=2.6.4
MIN_VERSION=2.6
Install_App()
{
	echo '正在安装Haproxy软件...'
	
	# 安装编译依赖
	if [ -f /usr/bin/yum ]; then
		yum install -y gcc make openssl-devel pcre2-devel
	elif [ -f /usr/bin/apt-get ]; then
		apt-get update -y
		apt-get install -y gcc make libssl-dev libpcre2-dev
	fi

	mkdir -p $serverPath/haproxy

	APP_DIR=${serverPath}/source/haproxy
	mkdir -p $APP_DIR
	echo $MIN_VERSION > $serverPath/haproxy/version.pl

	LOCAL_ADDR=common
    cn=$(curl -fsSL -m 10 -s http://ipinfo.io/json | grep "\"country\": \"CN\"")
    if [ ! -z "$cn" ] || [ "$?" == "0" ] ;then
        LOCAL_ADDR=cn
    fi


    if [ "${LOCAL_ADDR}" == "cn" ];then
    	if [ ! -f ${APP_DIR}/haproxy-${VERSION}.tar.gz ];then
			wget -nv -O ${APP_DIR}/haproxy-${VERSION}.tar.gz https://ghp.ci/https://www.haproxy.org/download/${MIN_VERSION}/src/haproxy-${VERSION}.tar.gz
		fi
    	if [ ! -f ${APP_DIR}/haproxy-${VERSION}.tar.gz ];then
			wget -nv -O ${APP_DIR}/haproxy-${VERSION}.tar.gz https://mirror.ghproxy.com/https://www.haproxy.org/download/${MIN_VERSION}/src/haproxy-${VERSION}.tar.gz
		fi
    fi

	
	if [ ! -f ${APP_DIR}/haproxy-${VERSION}.tar.gz ];then
		if [ $sysName == 'Darwin' ]; then
			wget -nv --no-check-certificate -O ${APP_DIR}/haproxy-${VERSION}.tar.gz https://www.haproxy.org/download/${MIN_VERSION}/src/haproxy-${VERSION}.tar.gz
		else
			curl -sSLo ${APP_DIR}/haproxy-${VERSION}.tar.gz https://www.haproxy.org/download/${MIN_VERSION}/src/haproxy-${VERSION}.tar.gz
		fi
	fi

	if [ ! -f ${APP_DIR}/haproxy-${VERSION}.tar.gz ];then
		curl -sSLo ${APP_DIR}/haproxy-${VERSION}.tar.gz https://www.haproxy.org/download/${MIN_VERSION}/src/haproxy-${VERSION}.tar.gz
	fi


	cd ${APP_DIR} && tar -zxf haproxy-${VERSION}.tar.gz

	if [ "$OSNAME" == "macos" ];then
		cd ${APP_DIR}/haproxy-${VERSION} && (make TARGET=osx USE_OPENSSL=1 USE_PCRE2=1 || make TARGET=osx) && make install PREFIX=$serverPath/haproxy
	else
		cd ${APP_DIR}/haproxy-${VERSION} && (make TARGET=linux-glibc USE_OPENSSL=1 USE_PCRE2=1 || make TARGET=linux-glibc) && make install PREFIX=$serverPath/haproxy
	fi

	echo '安装Haproxy成功'

	#Haproxy日志配置
	if [ -f /etc/rsyslog.conf ];then
		find_ha=`cat /etc/rsyslog.conf | grep haproxy`
		if [ "$find_ha" != "" ];then
			echo $find_ha
		else
			echo "---------------------------------------------"
			echo "" > ${serverPath}/haproxy/haproxy.log
			echo "local0.*  ${serverPath}/haproxy/haproxy.log" >> /etc/rsyslog.conf
			systemctl restart syslog
			echo "syslog默认的haproxy配置"
			echo "local0.*  ${serverPath}/haproxy/haproxy.log >> /etc/rsyslog.conf"
			echo "---------------------------------------------"
		fi
	fi

	#删除解压源码
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
