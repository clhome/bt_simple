#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH


curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

# 「卸载前彻底停进程」共享库（scripts/lib_service_stop.sh，纯函数，可安全 source）。
# 只 systemctl stop 是不够的：进程若不是该 unit 起的（上次卸载删了 unit／手工启动），
# 就会带着已删除的 datadir/程序文件继续占着端口 —— 见 2026-10-27 MySQL 现场。
for _yf_svc_lib in "${rootPath}/scripts/lib_service_stop.sh" \
                   "${serverPath}/yufeng_panel/scripts/lib_service_stop.sh"; do
	if [ -f "${_yf_svc_lib}" ]; then
		. "${_yf_svc_lib}"
		break
	fi
done
unset _yf_svc_lib


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
	# 必须非 0：面板按退出码判定安装结果，`exit 0` 会让「版本脚本都不存在」
	# 也显示成「安装成功」（假成功家族，2026-10-28 统一收紧）
	echo '缺少安装脚本版本...'
	exit 1
fi 

if [ "${action}" == "uninstall" ];then
	# 卸载前置：停 unit + 按「可执行文件在本插件目录下」杀残留（含程序文件已删的僵尸）
	yf_svc_force_stop "${serverPath}/openresty" openresty || echo "[WARN] openresty 仍有进程残留（见上方日志），卸载继续但端口可能被占" >&2
	if [ -f /usr/lib/systemd/system/openresty.service ] || [ -f /lib/systemd/system/openresty.service ];then
		systemctl stop openresty
		rm -f /usr/lib/systemd/system/openresty.service
		rm -f /lib/systemd/system/openresty.service
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
