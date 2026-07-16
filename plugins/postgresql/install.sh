#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

# cd /www/server/yufeng_panel/plugins/postgresql && bash install.sh install 16

action="$1"
type="$2"

if ! [[ "$type" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    # Type should be numbers, like 16 or 9.6
    echo '参数格式错误...'
    exit 0
fi

VERSION=(${type//./ })

# 动态检测当前系统的 pip 是否支持 --break-system-packages 参数（兼容新老版本Linux）
PIP_OPT=""
if pip install --help | grep -q "break-system-packages"; then
    PIP_OPT="--break-system-packages"
fi

pip install $PIP_OPT psycopg2-binary

if [ -f "${rootPath}/bin/activate" ];then
	source "${rootPath}/bin/activate"
	pip install psycopg2-binary
fi


if [ -z "${type}" ];then
	echo '缺少安装脚本...'
	exit 0
fi 

if [ ! -d "$curPath/versions/$VERSION" ];then
	echo '缺少安装脚本2...'
	exit 0
fi

if [ "${action}" == "uninstall" ];then
	if [ -f /usr/lib/systemd/system/postgresql.service ] || [ -f /lib/systemd/system/postgresql.service ];then
		systemctl stop postgresql
		systemctl disable postgresql
		rm -rf /usr/lib/systemd/system/postgresql.service
		rm -rf /lib/systemd/system/postgresql.service
		systemctl daemon-reload
	fi
fi

sh -x "$curPath/versions/$VERSION/install.sh" "$action"

if [ "${action}" == "install" ] && [ -d "$serverPath/postgresql" ];then
	#初始化 
	cd "${rootPath}" && python3 "${rootPath}/plugins/postgresql/index.py" start "${type}"
	cd "${rootPath}" && python3 "${rootPath}/plugins/postgresql/index.py" initd_install "${type}"
fi
