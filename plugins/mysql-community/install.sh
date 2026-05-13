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

action=$1
type=$2

if id mysql &> /dev/null ;then 
    echo "mysql UID is `id -u mysql`"
else
    groupadd mysql
	useradd -g mysql -s /usr/sbin/nologin mysql
fi


_os=`uname`
echo "use system: ${_os}"
if [ ${_os} == "Darwin" ]; then
	OSNAME='macos'
elif grep -Eq "openSUSE" /etc/*-release; then
	OSNAME='opensuse'
elif grep -Eq "FreeBSD" /etc/*-release; then
	OSNAME='freebsd'
elif grep -Eqi "Arch" /etc/issue || grep -Eq "Arch" /etc/*-release; then
	OSNAME='arch'
elif grep -Eqi "CentOS" /etc/issue || grep -Eq "CentOS" /etc/*-release; then
	OSNAME='centos'
elif grep -Eqi "Fedora" /etc/issue || grep -Eq "Fedora" /etc/*-release; then
	OSNAME='fedora'
elif grep -Eqi "Rocky" /etc/issue || grep -Eq "Rocky" /etc/*-release; then
	OSNAME='rocky'
elif grep -Eqi "AlmaLinux" /etc/issue || grep -Eq "AlmaLinux" /etc/*-release; then
	OSNAME='alma'
elif grep -Eqi "Debian" /etc/issue || grep -Eq "Debian" /etc/*-release; then
	OSNAME='debian'
elif grep -Eqi "Ubuntu" /etc/issue || grep -Eq "Ubuntu" /etc/*-release; then
	OSNAME='ubuntu'
else
	OSNAME='unknow'
fi

VERSION_ID=`cat /etc/*-release | grep 'VERSION_ID' | awk -F = '{print $2}' | awk -F "\"" '{print $2}'`

# 针对 Ubuntu 24.04 和 Debian 13 的兼容性优化
if [[ "$OSNAME" == "ubuntu" ]] && [[ "$VERSION_ID" =~ "24" ]]; then
	cur_dir=`pwd`
	cd /usr/lib/x86_64-linux-gnu
	[ ! -f libaio.so.1 ] && [ -f libaio.so.1t64.0.2 ] && ln -s libaio.so.1t64.0.2 libaio.so.1
	[ ! -f libncurses.so.6 ] && [ -f libncursesw.so.6.4 ] && ln -s libncursesw.so.6.4 libncurses.so.6
	cd $cur_dir
fi

if [[ "$OSNAME" == "debian" ]] && [[ "$VERSION_ID" =~ "13" ]]; then
	cur_dir=`pwd`
	cd /usr/lib/x86_64-linux-gnu
	[ ! -f libaio.so.1 ] && [ -f libaio.so.1t64.0.2 ] && ln -s libaio.so.1t64.0.2 libaio.so.1
	cd $cur_dir
fi

if [ "${type}" == "" ];then
	echo '缺少安装版本参数...'
	exit 1
fi 

if [ ! -d $curPath/versions/$type ];then
	echo "未找到版本 $type 的安装脚本..."
	exit 1
fi

if [ "${action}" == "uninstall" ];then
	cd ${rootPath} && python3 ${rootPath}/plugins/mysql-community/index.py stop ${type}
	cd ${rootPath} && python3 ${rootPath}/plugins/mysql-community/index.py initd_uninstall ${type}
	cd $curPath

	if [ -f /usr/lib/systemd/system/mysql-community.service ] || [ -f /lib/systemd/system/mysql-community.service ];then
		systemctl stop mysql-community
		systemctl disable mysql-community
		rm -rf /usr/lib/systemd/system/mysql-community.service
		rm -rf /lib/systemd/system/mysql-community.service
		systemctl daemon-reload
	fi
fi

# 执行具体版本的安装脚本
/bin/bash $curPath/versions/$type/install_generic.sh $action

if [ "${action}" == "install" ];then
	if [ "$?" == "0" ];then
		cd ${rootPath} && python3 ${rootPath}/plugins/mysql-community/index.py start ${type}
		cd ${rootPath} && python3 ${rootPath}/plugins/mysql-community/index.py initd_install ${type}
	else
		echo "MySQL $type 安装失败！"
		exit 1
	fi
fi
