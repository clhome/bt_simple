#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

function version_gt() { test "$(echo "$@" | tr " " "\n" | sort -V | head -n 1)" != "$1"; }
function version_le() { test "$(echo "$@" | tr " " "\n" | sort -V | head -n 1)" == "$1"; }
function version_lt() { test "$(echo "$@" | tr " " "\n" | sort -rV | head -n 1)" != "$1"; }
function version_ge() { test "$(echo "$@" | tr " " "\n" | sort -rV | head -n 1)" == "$1"; }

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

P_VER=`python3 -V | awk '{print $2}'`
echo "python:$P_VER"

sysName=`uname`
echo "use system: ${sysName}"

Install_pgadmin()
{
	if version_lt "$P_VER" "3.8.0" ;then
		echo 'Python版本太低, 无法安装'
		exit 1
	fi
	PG_DIR=${serverPath}/pgadmin/run
	PG_DATA_DIR=${serverPath}/pgadmin/data
	mkdir -p $PG_DIR
	mkdir -p $PG_DATA_DIR
	
	VERSION=9.15
	echo "${VERSION}" > ${serverPath}/pgadmin/version.pl

	if [ ! -f $PG_DIR/bin/activate ];then
	    python3 -m venv $PG_DIR
	fi

	if [ -f ${PG_DIR}/bin/activate ];then
		source ${PG_DIR}/bin/activate
	fi

	# 使用国内镜像加速 pip 安装
	LOCAL_ADDR=$(get_local_addr)
	PIP_OPT=""
	if [ "$LOCAL_ADDR" == "cn" ];then
		PIP_OPT="-i https://pypi.tuna.tsinghua.edu.cn/simple"
	fi

	pip install $PIP_OPT gunicorn pgadmin4

	cd ${rootPath} && python3 ${rootPath}/plugins/pgadmin/index.py start
	echo '安装完成'
}

Uninstall_pgadmin()
{
	cd ${rootPath} && python3 ${rootPath}/plugins/pgadmin/index.py stop

	if [ -f /usr/lib/systemd/system/pgadmin.service ];then
		systemctl stop pgadmin
		systemctl disable pgadmin
		rm -rf /usr/lib/systemd/system/pgadmin.service
		systemctl daemon-reload
	fi

	rm -rf ${serverPath}/pgadmin
	echo '卸载完成'
}

action=$1
if [ "${1}" == 'install' ];then
	Install_pgadmin
else
	Uninstall_pgadmin
fi
