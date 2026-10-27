#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
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


VERSION=$2

# /www/server/yufeng_panel/bin/supervisorctl  -c /www/server/supervisor/supervisor.conf
# cmd | status

bash ${rootPath}/scripts/getos.sh
OSNAME=`cat ${rootPath}/data/osname.pl`
OSNAME_ID=`cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}' | awk -F "\"" '{print $2}'`


if [ -f ${rootPath}/bin/activate ];then
	source ${rootPath}/bin/activate
fi

Install_app()
{
	echo '正在安装[supervisor]...'
	mkdir -p $serverPath/source
	mkdir -p $serverPath/supervisor
	mkdir -p $serverPath/supervisor/log
	mkdir -p $serverPath/supervisor/run

	echo 'supervisor install...'

	SYS_PIP_OPT=""
	if pip install --help 2>/dev/null | grep -q "break-system-packages"; then
		SYS_PIP_OPT="--break-system-packages"
	fi
	if [ "centos" == "$OSNAME" ] || [ "fedora" == "$OSNAME" ];then
    	pip install $SYS_PIP_OPT supervisor
    elif [ "ubuntu" == "$OSNAME" ] || [ "debian" == "$OSNAME" ] ;then
    	pip install $SYS_PIP_OPT supervisor
	else
		pip install $SYS_PIP_OPT supervisor
    	# brew install supervisor
	fi

	echo "${VERSION}" > $serverPath/supervisor/version.pl

	cd ${rootPath} && python3 plugins/supervisor/index.py start
	cd ${rootPath} && python3 plugins/supervisor/index.py initd_install
	
	echo '安装完成[supervisor]'
}

Uninstall_app()
{
	# 卸载前置：停 unit + 按「可执行文件在本插件目录下」杀残留（含程序文件已删的僵尸）
	yf_svc_force_stop "${serverPath}/supervisor" supervisor || echo "[WARN] supervisor 仍有进程残留（见上方日志），卸载继续但端口可能被占" >&2

	if [ -f /usr/lib/systemd/system/supervisor.service ] || [ -f /lib/systemd/system/supervisor.service ];then
		systemctl stop supervisor
		systemctl disable supervisor
		rm -rf /usr/lib/systemd/system/supervisor.service
		rm -rf /lib/systemd/system/supervisor.service
		systemctl daemon-reload
	fi

	pip uninstall supervisor -y

	rm -rf $serverPath/supervisor

	echo "卸载完成[supervisor]"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_app
else
	Uninstall_app
fi
