#!/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin
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

Install_pureftp()
{
	if id ftp &> /dev/null ;then 
	    echo "ftp UID is `id -u ftp`"
	    echo "ftp Shell is `grep "^ftp:" /etc/passwd |cut -d':' -f7 `"
	else
	    groupadd ftp
		useradd -g ftp -s /sbin/nologin ftp
	fi

	mkdir -p ${serverPath}/source/pureftp

	VER=$1
	FILE_PATH=$serverPath/source/pureftp/pure-ftpd-${VER}.tar.gz
	DOWNLOAD_URL=https://github.com/jedisct1/pure-ftpd/releases/download/${VER}/pure-ftpd-${VER}.tar.gz

	mw_download $FILE_PATH $DOWNLOAD_URL

	# Last Download Method Fallback
	if [ ! -f $FILE_PATH ];then
		wget --no-check-certificate -O $FILE_PATH https://mirror.ghproxy.com/${DOWNLOAD_URL} -T 10
	fi

	if [ ! -d $serverPath/source/pureftp/pure-ftpd-${VER} ];then
		cd $serverPath/source/pureftp  && tar zxvf pure-ftpd-${VER}.tar.gz
	fi

	cd $serverPath/source/pureftp/pure-ftpd-${VER} &&  ./configure --prefix=${serverPath}/pureftp \
 	CFLAGS=-O2 \
		--with-puredb \
		--with-quotas \
		--with-cookie \
		--with-virtualhosts \
		--with-diraliases \
		--with-sysquotas \
		--with-ratios \
		--with-altlog \
		--with-paranoidmsg \
		--with-shadow \
		--with-welcomemsg \
		--with-throttling \
		--with-uploadscript \
		--with-language=english \
		--with-rfc2640 \
		--with-ftpwho \
		--with-tls && make && make install && make clean
	
	if [ -d ${serverPath}/pureftp ];then 
		echo "${1}" > ${serverPath}/pureftp/version.pl
		echo '安装完成'

		cd ${rootPath} && python3 ${rootPath}/plugins/pureftp/index.py start
		cd ${rootPath} && python3 ${rootPath}/plugins/pureftp/index.py initd_install
	else
		echo '安装失败'
	fi
}

Uninstall_pureftp()
{
	if [ -f /usr/lib/systemd/system/pureftp.service ];then
		systemctl stop pureftp
		systemctl disable pureftp
		rm -rf /usr/lib/systemd/system/pureftp.service
		systemctl daemon-reload
	fi

	if [ -f $serverPath/pureftp/initd/pureftp ];then
		$serverPath/pureftp/initd/pureftp stop
	fi

	rm -rf ${serverPath}/pureftp
	userdel ftp
	groupdel ftp
	echo '卸载完成'
}

action=$1
if [ "${1}" == 'install' ];then
	Install_pureftp $2
else
	Uninstall_pureftp $2
fi
