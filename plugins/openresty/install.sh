#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH


curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

sysName=`uname`
action=$1
type=$2

lockFile="/var/run/yf_openresty_install.lock"
if [ -f "${lockFile}" ];then
    pid=$(cat "${lockFile}")
    if ps -p $pid > /dev/null 2>&1; then
        echo "Another OpenResty installation is already running (PID: $pid). Exiting."
        exit 1
    fi
fi
echo $$ > "${lockFile}"
trap "rm -f ${lockFile}" EXIT

VERSION=$2
openrestyDir=${serverPath}/source/openresty

if id www &> /dev/null ;then 
    echo "www uid is `id -u www`"
    echo "www shell is `grep "^www:" /etc/passwd |cut -d':' -f7 `"
else
    groupadd www
	useradd -g www -s /bin/bash www
fi

if [ "${action}" == "upgrade" ];then
	sh -x $curPath/versions/$2/install.sh $1
	if [ "$?" != "0" ];then
		echo "Sub-script install.sh failed!"
		exit 1
	fi
	
	echo "${VERSION}" > $serverPath/openresty/version.pl

	mkdir -p $serverPath/web_conf/php/conf
	echo 'set $PHP_ENV 0;' > $serverPath/web_conf/php/conf/enable-php-00.conf

	#初始化 
	cd ${rootPath} && python3 ${rootPath}/plugins/openresty/index.py start
	cd ${rootPath} && python3 ${rootPath}/plugins/openresty/index.py initd_install
	exit 0
fi


if [ "${2}" == "" ];then
	echo '缺少安装脚本版本...'
	exit 0
fi 

if [ "${action}" == "uninstall" ];then
	if [ -f /usr/lib/systemd/system/openresty.service ] || [ -f /lib/systemd/system/openresty.service ];then
		systemctl stop openresty
		rm -rf /usr/systemd/system/openresty.service
		rm -rf /lib/systemd/system/openresty.service
		systemctl daemon-reload
	fi

	if [ -f $serverPath/openresty/init.d/openresty ];then
		$serverPath/openresty/init.d/openresty stop
	fi

	rm -rf $serverPath/openresty
fi

# 编译安装或升级前，强力停止并清退所有旧的 nginx/openresty 进程，杜绝 80 端口冲突或 Text file busy 故障
if [ "${action}" == "install" ] || [ "${action}" == "upgrade" ];then
	if [ -f /usr/lib/systemd/system/openresty.service ] || [ -f /lib/systemd/system/openresty.service ];then
		systemctl stop openresty
	fi
	if [ -f $serverPath/openresty/init.d/openresty ];then
		$serverPath/openresty/init.d/openresty stop
	fi
	killall -9 nginx 2>/dev/null
	killall -9 openresty 2>/dev/null
	pkill -9 nginx 2>/dev/null
	pkill -9 openresty 2>/dev/null
fi

sh -x $curPath/versions/$2/install.sh $1
if [ "$?" != "0" ];then
	echo "Sub-script install.sh failed!"
	exit 1
fi

if [ "${action}" == "install" ] && [ -d $serverPath/openresty ];then
	echo "${VERSION}" > $serverPath/openresty/version.pl

	mkdir -p $serverPath/web_conf/php/conf
	echo 'set $PHP_ENV 0;' > $serverPath/web_conf/php/conf/enable-php-00.conf

	#初始化 
	cd ${rootPath} && python3 ${rootPath}/plugins/openresty/index.py start
	cd ${rootPath} && python3 ${rootPath}/plugins/openresty/index.py initd_install
fi
