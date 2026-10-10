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

# 版本号由面板传入（`bash install.sh install <version>`），会拼进下载 URL、
# tar 文件名与 `cd` 目标路径：只允许数字与点，阻断路径/命令注入。
VER=$2
case "${VER}" in
	*[!0-9.]*|'') echo "invalid version: ${VER}"; exit 1;;
esac

Install_pureftp()
{
	# serverPath 由 pwd 推导：从错误目录执行时会退化成 / 甚至空串，
	# 后面的 rm -rf 与 --prefix 就会指向未限定的目标。
	if [ -z "${serverPath}" ] || [ "${serverPath}" == '/' ];then
		echo "invalid server path: ${serverPath}"
		exit 1
	fi

	if id ftp &> /dev/null ;then 
	    echo "ftp UID is `id -u ftp`"
	    echo "ftp Shell is `grep "^ftp:" /etc/passwd |cut -d':' -f7 `"
	else
	    groupadd ftp
		useradd -g ftp -s /sbin/nologin ftp
	fi

	mkdir -p ${serverPath}/source/pureftp

	FILE_PATH=$serverPath/source/pureftp/pure-ftpd-${VER}.tar.gz
	DOWNLOAD_URL=https://download.pureftpd.org/pub/pure-ftpd/releases/pure-ftpd-${VER}.tar.gz

	yf_download $FILE_PATH $DOWNLOAD_URL

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
	
	if [ ! -f "${serverPath}/pureftp/bin/pure-pw" ];then
		echo "ERROR: pure-ftpd installation failed."
		rm -rf ${serverPath}/pureftp
		exit 1
	fi

	echo "${VER}" > ${serverPath}/pureftp/version.pl
	echo '安装完成'

	cd ${rootPath} && python3 ${rootPath}/plugins/pureftp/index.py start
	cd ${rootPath} && python3 ${rootPath}/plugins/pureftp/index.py initd_install

	echo "Configuring TLS for pure-ftpd..."
	mkdir -p /etc/ssl/private
	if [ ! -f '/etc/ssl/private/pure-ftpd-dhparams.pem' ]; then
		openssl dhparam -out /etc/ssl/private/pure-ftpd-dhparams.pem 512
	fi
	
	if [ ! -f '/etc/ssl/private/pure-ftpd.pem' ]; then
		openssl req -x509 -nodes -days 3650 -newkey rsa:2048 -sha256 -keyout /etc/ssl/private/pure-ftpd.pem -out /etc/ssl/private/pure-ftpd.pem -subj "/CN=pureftpd/O=pureftpd/C=CN"
	fi
	
	if [ -f '/etc/ssl/private/pure-ftpd.pem' ];then
		chmod 600 /etc/ssl/private/*.pem
		sed -i "s/# TLS/TLS/g" ${serverPath}/pureftp/etc/pure-ftpd.conf
		cd ${rootPath} && python3 ${rootPath}/plugins/pureftp/index.py restart
	fi
}

Uninstall_pureftp()
{
	# serverPath 由 pwd 推导：从错误目录执行时它会退化成 / 甚至空串，
	# 后面的 rm -rf 就会指向未限定的目标。
	if [ -z "${serverPath}" ] || [ "${serverPath}" == '/' ];then
		echo "invalid server path: ${serverPath}"
		exit 1
	fi

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
	if [ -d ${serverPath}/pureftp ];then
		echo "uninstall failed: ${serverPath}/pureftp still exists"
		exit 1
	fi
	userdel ftp
	groupdel ftp
	echo '卸载完成'
}

action=$1
if [ "${action}" == 'install' ];then
	Install_pureftp $2
elif [ "${action}" == 'uninstall' ];then
	# 旧版是 else 兜底：任何非法/缺失参数（含无参）都会执行卸载，
	# 直接 rm -rf 安装目录并 userdel ftp。面板只会传 install / uninstall，这里显式分支。
	Uninstall_pureftp
else
	echo "usage: $0 {install|uninstall} [version]"
	exit 1
fi
