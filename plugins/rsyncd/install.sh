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

sysName=`uname`


#获取信息和版本
# bash /www/server/yufeng_panel/scripts/getos.sh
bash ${rootPath}/scripts/getos.sh
OSNAME=`cat ${rootPath}/data/osname.pl`


if [ -f ${rootPath}/bin/activate ];then
	source ${rootPath}/bin/activate
fi

if id www &> /dev/null ;then 
    echo "www uid is `id -u www`"
    echo "www shell is `grep "^www:" /etc/passwd |cut -d':' -f7 `"
else
    groupadd www
	useradd -g www -s /bin/bash www
fi

# echo $OSNAME

Install_rsyncd()
{
	echo '正在安装脚本文件...'
	

	if [ "$OSNAME" == "debian" ] || [ "$OSNAME" == "ubuntu" ];then
		apt install -y rsync
		apt install -y lsyncd
	elif [[ "$OSNAME" == "arch" ]]; then
		echo y | pacman -Sy rsync
		echo y | pacman -Sy lsyncd
	elif [[ "$OSNAME" == "macos" ]]; then
		# brew install rsync
		# brew install lsyncd
		echo "ok"
	else
		yum install -y rsync
		yum install -y lsyncd
	fi

	mkdir -p $serverPath/rsyncd
	mkdir -p $serverPath/rsyncd/receive
	mkdir -p $serverPath/rsyncd/send
	
	echo '2.0' > $serverPath/rsyncd/version.pl
	echo '安装完成'
	cd ${rootPath} && python3 ${rootPath}/plugins/rsyncd/index.py start
	cd ${rootPath} && python3 ${rootPath}/plugins/rsyncd/index.py initd_install
}

Uninstall_rsyncd()
{
	# 卸载前置：停 unit + 按「可执行文件在本插件目录下」杀残留（含程序文件已删的僵尸）
	yf_svc_force_stop "${serverPath}/rsyncd" rsyncd lsyncd || echo "[WARN] rsyncd 仍有进程残留（见上方日志），卸载继续但端口可能被占" >&2
	if [ -f /usr/lib/systemd/system/rsyncd.service ] || [ -f /lib/systemd/system/rsyncd.service ];then
		systemctl stop rsyncd
		systemctl disable rsyncd
		rm -rf /usr/lib/systemd/system/rsyncd.service
		rm -rf /lib/systemd/system/rsyncd.service
		systemctl daemon-reload
	fi

	if [ -f /usr/lib/systemd/system/lsyncd.service ] || [ -f /lib/systemd/system/lsyncd.service ];then
		systemctl stop lsyncd
		systemctl disable lsyncd
		rm -rf /usr/lib/systemd/system/lsyncd.service
		rm -rf /lib/systemd/system/lsyncd.service
		systemctl daemon-reload
	fi

	if [ -f $serverPath/rsyncd/initd/rsyncd ];then
		$serverPath/rsyncd/initd/rsyncd stop
	fi
	
	rm -rf $serverPath/rsyncd
	echo "卸载完成"
}

action=$1
if [ "${action}" == 'install' ];then
	Install_rsyncd
elif [ "${action}" == 'uninstall' ];then
	# 旧版是 else 兜底：任何非法/缺失参数（含无参）都会执行卸载，
	# 直接 rm -rf 安装目录。面板只会传 install / uninstall，这里显式分支。
	Uninstall_rsyncd
else
	echo "Usage: $0 {install|uninstall}"
	exit 1
fi
