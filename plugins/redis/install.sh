#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

# https://www.cnblogs.com/zlonger/p/16177595.html
# https://www.cnblogs.com/BNTang/articles/15841688.html

# ps -ef|grep redis |grep -v grep | awk '{print $2}' | xargs kill

# cd /Users/midoks/Desktop/mwdev/server/mdserver-web/plugins/redis && bash install.sh install 7.2.2

# cmd查看| info replication
# /Users/midoks/Desktop/mwdev/server/redis/bin/redis-cli -h 127.0.0.1 -p 6399
# /www/server/redis/bin/redis-cli -h 127.0.0.1 -p 6399

VERSION=$2

Install_App()
{
	echo '正在安装脚本文件...'
	mkdir -p $serverPath/source
	mkdir -p $serverPath/source/redis

	FILE_TGZ=redis-${VERSION}.tar.gz
	REDIS_DIR=$serverPath/source/redis

	if [ ! -f $REDIS_DIR/${FILE_TGZ} ];then
		wget -nv --no-check-certificate -O $REDIS_DIR/${FILE_TGZ} https://download.redis.io/releases/${FILE_TGZ}
	fi
	
	cd $REDIS_DIR && tar -zxf ${FILE_TGZ}

	# 获取CPU核心数用于多核并行编译加速
	cpuCore=$(nproc 2>/dev/null)
	if [ -z "$cpuCore" ]; then
		cpuCore="1"
	fi

	CMD_MAKE=`which gmake`
	if [ "$?" == "0" ];then
		cd redis-${VERSION} && gmake BUILD_TLS=yes -j ${cpuCore} PREFIX=$serverPath/redis install
	else
		cd redis-${VERSION} && make BUILD_TLS=yes -j ${cpuCore} PREFIX=$serverPath/redis install
	fi

	if [ -d $serverPath/redis ];then
		mkdir -p $serverPath/redis/data
		if [ ! -f $serverPath/redis/redis.conf ];then
			sed '/^ *#/d' redis.conf > $serverPath/redis/redis.conf
		else
			sed -i 's/slave-serve-stale-data/replica-serve-stale-data/g' $serverPath/redis/redis.conf
			sed -i 's/slave-read-only/replica-read-only/g' $serverPath/redis/redis.conf
			sed -i 's/slave-priority/replica-priority/g' $serverPath/redis/redis.conf
			sed -i 's/client-output-buffer-limit slave/client-output-buffer-limit replica/g' $serverPath/redis/redis.conf
			sed -i '/ziplist/d' $serverPath/redis/redis.conf
			sed -i '/intset/d' $serverPath/redis/redis.conf
		fi

		# 系统内核参数自动优化 (消除 Redis 经典警告)
		VM_OVERCOMMIT_MEMORY=$(cat /etc/sysctl.conf | grep vm.overcommit_memory)
		NET_CORE_SOMAXCONN=$(cat /etc/sysctl.conf | grep net.core.somaxconn)
		if [ -z "${VM_OVERCOMMIT_MEMORY}" ] && [ -z "${NET_CORE_SOMAXCONN}" ];then
			echo "vm.overcommit_memory = 1" >> /etc/sysctl.conf
			echo "net.core.somaxconn = 1024" >> /etc/sysctl.conf
			sysctl -p
		fi

		# ARM架构兼容优化
		ARM_CHECK=$(uname -a | grep aarch64)
		if [ "${ARM_CHECK}" ];then
			echo "ignore-warnings ARM64-COW-BUG" >> $serverPath/redis/redis.conf
		fi

		echo "${VERSION}" > $serverPath/redis/version.pl
		echo '安装完成'

		cd ${rootPath} && python3 ${rootPath}/plugins/redis/index.py start
		cd ${rootPath} && python3 ${rootPath}/plugins/redis/index.py initd_install
		
	else
		echo '安装失败!'
	fi

	if [ -d ${REDIS_DIR}/redis-${VERSION} ];then
		rm -rf ${REDIS_DIR}/redis-${VERSION}
	fi
}

Uninstall_App()
{
	if [ -f /usr/lib/systemd/system/redis.service ];then
		systemctl stop redis
		systemctl disable redis
		rm -rf /usr/lib/systemd/system/redis.service
		systemctl daemon-reload
	fi

	if [ -f /lib/systemd/system/redis.service ];then
		systemctl stop redis
		systemctl disable redis
		rm -rf /lib/systemd/system/redis.service
		systemctl daemon-reload
	fi

	if [ -f $serverPath/redis/initd/redis ];then
		$serverPath/redis/initd/redis stop
	fi

	if [ -d $serverPath/redis ];then
		rm -rf $serverPath/redis
	fi
	
	echo "卸载redis成功"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_App
else
	Uninstall_App
fi
