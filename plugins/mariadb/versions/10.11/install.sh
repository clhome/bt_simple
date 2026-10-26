#!/bin/bash
# yf_verify_archive（按内容魔数校验压缩包）定义在 scripts/github_download.sh，
# 那是可安全 source 的纯函数库（scripts/lib.sh 是部署脚本，被 source 会 pip install/exit）
for _yf_gh in "$(dirname "$0")/../../../../scripts/github_download.sh" \
              "$(dirname "$0")/../../../scripts/github_download.sh" \
              "/www/server/yufeng_panel/scripts/github_download.sh"; do
	if [ -f "$_yf_gh" ]; then
		. "$_yf_gh" >/dev/null 2>&1
		break
	fi
done
unset _yf_gh

if [ -f $(dirname $0)/../../scripts/lib_make_jobs.sh ]; then source $(dirname $0)/../../scripts/lib_make_jobs.sh; elif [ -f /www/server/yufeng_panel/scripts/lib_make_jobs.sh ]; then source /www/server/yufeng_panel/scripts/lib_make_jobs.sh; fi
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

#https://dev.mysql.com/downloads/mysql/5.5.html#downloads
#https://dev.mysql.com/downloads/file/?id=480541

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")
sysName=`uname`

mariadbDir=${serverPath}/source/mariadb

MY_VER=10.11.11

Install_app()
{
	mkdir -p ${mariadbDir}
	echo '正在安装脚本文件...'

	if [ "$sysName" != "Darwin" ];then
		mkdir -p /var/log/mariadb
		touch /var/log/mariadb/mariadb.log
	fi

	# ----- cpu start ------
	if [ -z "${cpuCore}" ]; then
    	cpuCore="1"
	fi

	if [ -f /proc/cpuinfo ];then
		cpuCore=`cat /proc/cpuinfo | grep "processor" | wc -l`
	fi

	MEM_INFO=$(LC_ALL=C free -m|grep Mem|awk '{printf("%.f",($2)/1024)}')
	if [ "${cpuCore}" != "1" ] && [ "${MEM_INFO}" != "0" ];then
	    if [ "${cpuCore}" -gt "${MEM_INFO}" ];then
	        cpuCore="${MEM_INFO}"
	    fi
	else
	    cpuCore="1"
	fi

	if [ "$cpuCore" -gt "2" ];then
		cpuCore=`echo "$cpuCore" | awk '{printf("%.f",($1)*0.8)}'`
	else
		cpuCore="1"
	fi
	# ----- cpu end ------
# --- yf adaptive clamp (1C512M -> -j1) ---
if command -v yf_make_jobs >/dev/null 2>&1; then _yf_jobs=$(yf_make_jobs 2>/dev/null || echo ""); if [ -n "$_yf_jobs" ] && [ "$_yf_jobs" -ge 1 ] 2>/dev/null; then cpuCore="$_yf_jobs"; fi; fi

	# if [ ! -f ${mariadbDir}/mariadb-${MY_VER}.tar.gz ];then
	# 	wget --no-check-certificate -O ${mariadbDir}/mariadb-${MY_VER}.tar.gz --tries=3 https://mirrors.aliyun.com/mariadb/mariadb-${MY_VER}/source/mariadb-${MY_VER}.tar.gz
	# fi

	# https://downloads.mariadb.org/interstitial/mariadb-10.9.1/source/mariadb-10.9.1.tar.gz
	if [ ! -f ${mariadbDir}/mariadb-${MY_VER}.tar.gz ];then
		wget -nv --no-check-certificate -O ${mariadbDir}/mariadb-${MY_VER}.tar.gz --tries=3 https://archive.mariadb.org/mariadb-${MY_VER}/source/mariadb-${MY_VER}.tar.gz
		# 下载后按**内容**验一次（HTML 错误页/截断包在这里拦住，而不是等到编译阶段报一堆无关错误）
		if command -v yf_verify_archive >/dev/null 2>&1 && ! yf_verify_archive "${mariadbDir}/mariadb-${MY_VER}.tar.gz"; then
			echo "[ERROR] 下载内容无效（不是有效压缩包），请检查网络/镜像: ${mariadbDir}/mariadb-${MY_VER}.tar.gz" >&2
			rm -f "${mariadbDir}/mariadb-${MY_VER}.tar.gz"
			exit 1
		fi
	fi

	if [ ! -d ${mariadbDir}/mariadb-${MY_VER} ];then
		 ( cd ${mariadbDir} && tar -zxf ${mariadbDir}/mariadb-${MY_VER}.tar.gz ) || { echo "[ERROR] 解压失败（包损坏），请重试: ${mariadbDir}/mariadb-${MY_VER}.tar.gz" >&2; exit 1; }
	fi

	INSTALL_CMD=cmake
	# check cmake version
	CMAKE_VERSION=`cmake -version | grep version | awk '{print $3}' | awk -F '.' '{print $1}'`
	if [ "$CMAKE_VERSION" -eq "2" ];then
		mkdir -p /var/log/mariadb
		touch /var/log/mariadb/mariadb.log
		INSTALL_CMD=cmake3
	fi
	

	if [ -d $serverPath/mariadb ] && [ ! -f $serverPath/mariadb/bin/mysql ]; then
		echo "检测到残留的不完整 MariaDB 编译安装目录，正在清理..."
		rm -rf $serverPath/mariadb
	fi

	if [ ! -d $serverPath/mariadb ];then
		cd ${mariadbDir}/mariadb-${MY_VER} && ${INSTALL_CMD} \
		-DCMAKE_INSTALL_PREFIX=$serverPath/mariadb \
		-DMYSQL_DATADIR=$serverPath/mariadb/data/ \
		-DMYSQL_USER=mysql \
		-DMYSQL_UNIX_ADDR=$serverPath/mariadb/mysql.sock \
		-DWITH_MYISAM_STORAGE_ENGINE=1 \
		-DWITH_INNOBASE_STORAGE_ENGINE=1 \
		-DWITH_MEMORY_STORAGE_ENGINE=1 \
		-DENABLED_LOCAL_INFILE=1 \
		-DWITH_PARTITION_STORAGE_ENGINE=1 \
		-DEXTRA_CHARSETS=all \
		-DDEFAULT_CHARSET=utf8mb4 \
		-DDEFAULT_COLLATION=utf8mb4_general_ci \
		-DCMAKE_C_COMPILER=/usr/bin/gcc \
		-DCMAKE_CXX_COMPILER=/usr/bin/g++ && \
		make -j${cpuCore} && make install && make clean || {
			echo "[ERROR] cmake / make 失败：mariadb 编译安装未完成（见上方 cmake 日志）" >&2
			exit 1
		}


		if [ -d $serverPath/mariadb ];then
			echo '10.11' > $serverPath/mariadb/version.pl
			echo '安装完成'
		else
			echo '安装失败'
			echo 'install fail'>&2
			exit 1
		fi
	fi

	if [ -d ${mariadbDir}/mariadb-${MY_VER} ];then
		rm -rf ${mariadbDir}/mariadb-${MY_VER}
	fi
}

Uninstall_app()
{
	rm -rf $serverPath/mariadb
	echo '卸载完成'
}

action=$1
if [ "${1}" == 'install' ];then
	Install_app
else
	Uninstall_app
fi