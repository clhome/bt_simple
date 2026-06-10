#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

# 引入统一的 GitHub 下载函数库
_gh_lib=$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd ../../scripts 2>/dev/null && pwd)/github_download.sh
if [ -f "$_gh_lib" ]; then
    source "$_gh_lib"
fi

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

# https://www.cnblogs.com/zlonger/p/16177595.html
# https://www.cnblogs.com/BNTang/articles/15841688.html

# ps -ef|grep valkey |grep -v grep | awk '{print $2}' | xargs kill

# cd /Users/midoks/Desktop/mwdev/server/mdserver-web/plugins/valkey && bash install.sh install 7.2.2

# cmd查看| info replication
# /Users/midoks/Desktop/mwdev/server/valkey/bin/valkey-cli -h 127.0.0.1 -p 6399
# /www/server/valkey/bin/valkey-cli -h 127.0.0.1 -p 6399

VERSION=$2

Install_App()
{
	echo '正在安装脚本文件...'
	mkdir -p $serverPath/source
	mkdir -p $serverPath/source/valkey

	FILE_TGZ=${VERSION}.tar.gz
	VALKEY_DIR=$serverPath/source/valkey

	if [ -f $VALKEY_DIR/${FILE_TGZ} ]; then
		if ! gzip -t $VALKEY_DIR/${FILE_TGZ} 2>/dev/null; then
			echo "检测到 ${FILE_TGZ} 文件已损坏，正在删除以准备重新下载..."
			rm -f $VALKEY_DIR/${FILE_TGZ}
		fi
	fi

	if [ ! -f $VALKEY_DIR/${FILE_TGZ} ];then
		github_download $VALKEY_DIR/${FILE_TGZ} https://github.com/valkey-io/valkey/archive/refs/tags/${FILE_TGZ}
	fi
	
	cd $VALKEY_DIR && tar -zxvf ${FILE_TGZ}
	if [ "$?" != "0" ];then
		echo "解压 ${FILE_TGZ} 失败，文件可能已损坏。已清理损坏文件，请重试安装。"
		rm -f ${FILE_TGZ}
		exit 1
	fi

	CMD_MAKE=`which gmake`
	if [ "$?" == "0" ];then
		cd valkey-${VERSION} && gmake PREFIX=$serverPath/valkey install
	else
		cd valkey-${VERSION} && make PREFIX=$serverPath/valkey install
	fi

	if [ -d $serverPath/valkey ];then
		mkdir -p $serverPath/valkey/data
		sed '/^ *#/d' valkey.conf > $serverPath/valkey/valkey.conf

		echo "${VERSION}" > $serverPath/valkey/version.pl
		echo '安装完成'

		cd ${rootPath} && python3 plugins/valkey/index.py start
		cd ${rootPath} && python3 plugins/valkey/index.py initd_install
		
	else
		echo '安装失败!'
	fi

	if [ -d ${VALKEY_DIR}/valkey-${VERSION} ];then
		rm -rf ${VALKEY_DIR}/valkey-${VERSION}
	fi
}

Uninstall_App()
{
	if [ -f /usr/lib/systemd/system/valkey.service ];then
		systemctl stop valkey
		systemctl disable valkey
		rm -rf /usr/lib/systemd/system/valkey.service
		systemctl daemon-reload
	fi

	if [ -f /lib/systemd/system/valkey.service ];then
		systemctl stop valkey
		systemctl disable valkey
		rm -rf /lib/systemd/system/valkey.service
		systemctl daemon-reload
	fi

	if [ -f $serverPath/valkey/initd/valkey ];then
		$serverPath/valkey/initd/valkey stop
	fi

	if [ -d $serverPath/valkey ];then
		rm -rf $serverPath/valkey
	fi
	
	echo "卸载valkey成功"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_App
else
	Uninstall_App
fi
