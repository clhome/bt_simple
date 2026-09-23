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

	SYS_PIP_OPT=""
	if pip install --help 2>/dev/null | grep -q "break-system-packages"; then
		SYS_PIP_OPT="--break-system-packages"
	fi

	pip install $SYS_PIP_OPT $PIP_OPT gunicorn pgadmin4

	# version.pl 记录**实际装上的版本**，而不是写死的常量。
	# 面板显示的版本号必须可核查：pgAdmin 各版本的配置项与 setup.py 语义会变
	# （例如 v8 起 `setup.py setup-db` 不再创建初始管理员），
	# 版本号写错会让后续排障完全跑偏。
	INSTALLED_VER=`pip show pgadmin4 2>/dev/null | awk '/^Version:/{print $2}'`
	if [ -z "${INSTALLED_VER}" ];then
		echo 'pgadmin4 安装失败'
		exit 1
	fi
	echo "${INSTALLED_VER}" > ${serverPath}/pgadmin/version.pl
	echo "pgadmin4: ${INSTALLED_VER}"

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
