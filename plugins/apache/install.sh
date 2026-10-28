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
	# 必须非 0：面板按退出码判定安装结果，`exit 0` 会让「版本脚本都不存在」
	# 也显示成「安装成功」（假成功家族，2026-10-28 统一收紧）
	echo '缺少安装脚本版本...'
	exit 1
fi 

if [ "${action}" == "uninstall" ];then
	# 卸载前置：停 unit + 按「可执行文件在本插件目录下」杀残留（含程序文件已删的僵尸）
	yf_svc_force_stop "${serverPath}/apache" httpd || echo "[WARN] apache 仍有进程残留（见上方日志），卸载继续但端口可能被占" >&2
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
