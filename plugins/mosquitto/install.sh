#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

sysName=`uname`
echo "use system: ${sysName}"

VERSION=2.1.2
mosquittoDir=${serverPath}/source/mosquitto

Install_App()
{
	if id mosquitto &> /dev/null ;then 
	    echo "mosquitto UID is `id -u mosquitto`"
	    echo "mosquitto Shell is `grep "^mosquitto:" /etc/passwd |cut -d':' -f7 `"
	else
	    groupadd mosquitto
		useradd -g mosquitto mosquitto
	fi

	echo '正在安装脚本文件...'
	mkdir -p ${mosquittoDir}

	URL="https://mosquitto.org/files/source/mosquitto-${VERSION}.tar.gz"
	mw_download ${mosquittoDir}/mosquitto-${VERSION}.tar.gz ${URL}
	
	if [ ! -d ${mosquittoDir}/mosquitto-${VERSION} ];then
		cd ${mosquittoDir} && tar -zxvf mosquitto-${VERSION}.tar.gz
	fi


	INSTALL_CMD=cmake
	# check cmake version
	CMAKE_VERSION=`cmake -version | grep version | awk '{print $3}' | awk -F '.' '{print $1}'`
	if [ "$CMAKE_VERSION" -eq "2" ];then
		INSTALL_CMD=cmake3
	fi

	mkdir -p $serverPath/mosquitto
	if  [ ! -d $serverPath/mosquitto/bin ];then
		cd ${mosquittoDir}/mosquitto-${VERSION} && ${INSTALL_CMD} . -DCMAKE_INSTALL_PREFIX=$serverPath/mosquitto && make -j$(get_cpu_cores) && make install
	fi
	
	if [ -d $serverPath/mosquitto ];then
		echo "${VERSION}" > $serverPath/mosquitto/version.pl
		echo '安装mosquitto完成'

		cd ${rootPath} && python3 ${rootPath}/plugins/mosquitto/index.py start
		cd ${rootPath} && python3 ${rootPath}/plugins/mosquitto/index.py initd_install
	fi
}

Uninstall_App()
{
	if [ -f /usr/lib/systemd/system/mosquitto.service ];then
		systemctl stop mosquitto
		systemctl disable mosquitto
		rm -rf /usr/lib/systemd/system/mosquitto.service
		systemctl daemon-reload
	fi

	if [ -f $serverPath/mosquitto/initd/mosquitto ];then
		$serverPath/mosquitto/initd/mosquitto stop
	fi

	rm -rf $serverPath/mosquitto
	echo "卸载mosquitto成功"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_App
else
	Uninstall_App
fi
