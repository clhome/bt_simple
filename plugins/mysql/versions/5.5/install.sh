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
sysArch=`arch`

mysqlDir=${serverPath}/source/mysql

VERSION=5.5.62

_os=`uname`
echo "use system: ${_os}"
if [ ${_os} == "Darwin" ]; then
	OSNAME='macos'
elif grep -Eq "openSUSE" /etc/*-release; then
	OSNAME='opensuse'
	zypper refresh
elif grep -Eq "FreeBSD" /etc/*-release; then
	OSNAME='freebsd'
	pkg install -y wget unzip
elif grep -Eqi "Arch" /etc/issue || grep -Eq "Arch" /etc/*-release; then
	OSNAME='arch'
	echo y | pacman -Sy unzip
elif grep -Eqi "CentOS" /etc/issue || grep -Eq "CentOS" /etc/*-release; then
	OSNAME='centos'
	yum install -y wget zip unzip
elif grep -Eqi "Fedora" /etc/issue || grep -Eq "Fedora" /etc/*-release; then
	OSNAME='fedora'
	yum install -y wget zip unzip
elif grep -Eqi "Rocky" /etc/issue || grep -Eq "Rocky" /etc/*-release; then
	OSNAME='rocky'
	yum install -y wget zip unzip
elif grep -Eqi "AlmaLinux" /etc/issue || grep -Eq "AlmaLinux" /etc/*-release; then
	OSNAME='alma'
	yum install -y wget zip unzip
elif grep -Eqi "Debian" /etc/issue || grep -Eq "Debian" /etc/*-release; then
	OSNAME='debian'
	apt update -y
	apt install -y devscripts
	apt install -y wget zip unzip
elif grep -Eqi "Ubuntu" /etc/issue || grep -Eq "Ubuntu" /etc/*-release; then
	OSNAME='ubuntu'
	apt install -y wget zip unzip
else
	OSNAME='unknow'
fi

VERSION_ID=`cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}' | awk -F "\"" '{print $2}'`


Install_common(){
	apt install -y libudev-dev
	apt install -y libtirpc-dev
	apt install -y libssl-dev
	apt install -y libgssglue-dev
	apt install -y software-properties-common

	apt install -y build-essential
	apt install -y cmake 
	apt install -y pkg-config 
	apt install -y libncurses5-dev
	apt install -y libsystemd-dev 
	apt install -y libsasl2-dev 
	apt install -y libldap2-dev 
}

# 安装依赖
Install_dep(){
	Install_common
	add-apt-repository -y ppa:ubuntu-toolchain-r/test

	export PKG_CONFIG_PATH=/usr/lib/pkgconfig
	apt install -y gcc-10 g++-10
	WHERE_DIR_GCC=/usr/bin/gcc-10
	WHERE_DIR_GPP=/usr/bin/g++-10
}

Install_dep_debain13(){
	Install_common
	# add-apt-repository -y ppa:ubuntu-toolchain-r/test
	export PKG_CONFIG_PATH=/usr/lib/pkgconfig
	apt install -y gcc-12 g++-12
	WHERE_DIR_GCC=/usr/bin/gcc-12
	WHERE_DIR_GPP=/usr/bin/g++-12
}

Install_mysql()
{
	mkdir -p ${mysqlDir}
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

	if [ ! -f ${mysqlDir}/mysql-${VERSION}.tar.gz ];then
		wget -nv --no-check-certificate -O ${mysqlDir}/mysql-${VERSION}.tar.gz --tries=3 https://dev.mysql.com/get/Downloads/MySQL-5.5/mysql-${VERSION}.tar.gz
		# 下载后按**内容**验一次（HTML 错误页/截断包在这里拦住，而不是等到编译阶段报一堆无关错误）
		if command -v yf_verify_archive >/dev/null 2>&1 && ! yf_verify_archive "${mysqlDir}/mysql-${VERSION}.tar.gz"; then
			echo "[ERROR] 下载内容无效（不是有效压缩包），请检查网络/镜像: ${mysqlDir}/mysql-${VERSION}.tar.gz" >&2
			rm -f "${mysqlDir}/mysql-${VERSION}.tar.gz"
			exit 1
		fi
	fi

	if [ ! -d ${mysqlDir}/mysql-${VERSION} ];then
		 ( cd ${mysqlDir} && tar -zxf ${mysqlDir}/mysql-${VERSION}.tar.gz ) || { echo "[ERROR] 解压失败（包损坏），请重试: ${mysqlDir}/mysql-${VERSION}.tar.gz" >&2; exit 1; }
	fi
	
	WHERE_DIR_GCC=/usr/bin/gcc
	WHERE_DIR_GPP=/usr/bin/g++
	if [ ! -f $WHERE_DIR_GCC ];then
		WHERE_DIR_GCC=`which gcc`
	fi

	if [ ! -f $WHERE_DIR_GPP ];then
		WHERE_DIR_GPP=`which g++`
	fi

	# https://blog.whsir.com/post-7748.html
	# arm架构编译MySQL5.5报错
	if [[ "$sysArch" =~  "aarch" ]];then
		# wget --no-check-certificate -O ${mysqlDir}/mysql-5.5-fix-arm-client_plugin.patch https://down.whsir.com/downloads/mysql-5.5-fix-arm-client_plugin.patch
		cd ${mysqlDir}/mysql-5.5.62 && patch -p1 < ${rootPath}/plugins/mysql/patch/mysql-5.5-fix-arm-client_plugin.patch
	fi

	if [ "$OSNAME" == "ubuntu" ];then
		Install_dep
	fi

	# 与 5.6 同一个坑：CMake 默认 `WITH_SSL=system`，OpenSSL 3.x 的发行版上会报
	# 「Cannot find appropriate system libraries for WITH_SSL=system」；
	# 而 5.5 只支持 OpenSSL 1.0.x（1.1/3.x 的结构体不兼容）。
	# 因此默认自建 OpenSSL 1.0.2 并显式指向它（openssl_10.sh 内有判存，已装过就跳过）。
	OPTIONS=''
	cd ${rootPath}/plugins/php/lib && /bin/bash openssl_10.sh || {
		echo "[ERROR] 自建 OpenSSL 1.0.2 失败，MySQL ${VERSION} 无法编译（见上方 openssl10 日志）" >&2
		exit 1
	}
	_ossl_dir="${serverPath}/lib/openssl10"
	if [ ! -f "${_ossl_dir}/include/openssl/ssl.h" ]; then
		echo "[ERROR] 未找到可用的 OpenSSL 1.0.2：${_ossl_dir}/include/openssl/ssl.h 不存在" >&2
		exit 1
	fi
	export PKG_CONFIG_PATH=${_ossl_dir}/lib/pkgconfig:${_ossl_dir}/lib64/pkgconfig:${PKG_CONFIG_PATH}
	OPTIONS="-DWITH_SSL=${_ossl_dir}"

	if [ "$OSNAME" == "debian" ] && [ "$VERSION_ID" == "13" ];then
		# 实测在 Debian 13（glibc 2.41 / OpenSSL 3.x）上 MySQL 5.5 编不过。
		# 旧代码在这里 `exit 0` —— 面板会显示「安装成功」，而机器上什么都没有
		# （假成功）。必须非 0 退出并指明替代版本。
		# 也不要先白编一遍 OpenSSL 1.0.2（约 3 分钟）再宣布不支持。
		echo "[ERROR] Debian 13 无法编译 MySQL 5.5（glibc/OpenSSL 过新），请改用 MySQL 5.7+ 或 MariaDB 10.6+" >&2
		exit 1
	fi

	if [ -d $serverPath/mysql ] && [ ! -f $serverPath/mysql/bin/mysql ]; then
		echo "检测到残留的不完整 MySQL 编译安装目录，正在清理..."
		rm -rf $serverPath/mysql
	fi

	if [ ! -d $serverPath/mysql ];then
		cd ${mysqlDir}/mysql-5.5.62 && cmake \
		-DCMAKE_INSTALL_PREFIX=$serverPath/mysql \
		-DMYSQL_USER=mysql \
		-DMYSQL_TCP_PORT=3306 \
		-DMYSQL_UNIX_ADDR=/var/tmp/mysql.sock \
		-DWITH_MYISAM_STORAGE_ENGINE=1 \
		-DWITH_INNOBASE_STORAGE_ENGINE=1 \
		-DWITH_MEMORY_STORAGE_ENGINE=1 \
		-DENABLED_LOCAL_INFILE=1 \
		-DWITH_PARTITION_STORAGE_ENGINE=1 \
		$OPTIONS \
		-DEXTRA_CHARSETS=all \
		-DDEFAULT_CHARSET=utf8mb4 \
		-DDEFAULT_COLLATION=utf8mb4_general_ci \
		-DCMAKE_C_COMPILER=$WHERE_DIR_GCC \
		-DCMAKE_CXX_COMPILER=$WHERE_DIR_GPP && \
		make -j${cpuCore} && make install && make clean || {
			echo "[ERROR] cmake / make 失败：mysql 编译安装未完成（见上方 cmake 日志）" >&2
			exit 1
		}


		if [ -d $serverPath/mysql ];then
			rm -rf ${mysqlDir}/mysql-${VERSION}
			echo '5.5' > $serverPath/mysql/version.pl
			echo "${VERSION}安装完成"
		else
			# rm -rf ${mysqlDir}/mysql-5.5.62
			echo "${VERSION}安装失败"
			exit 1
		fi
	fi
}

Uninstall_mysql()
{
	# 先停进程再删目录（2026-10-27）：只 rm -rf 会让 mysqld 带着已删除的
	# datadir/socket 继续占着 3306，重装后表现为「数据库密码错误」。
	# stop_and_kill 只杀 exe 属于本插件的进程，不动系统里别的 MySQL/MariaDB。
	if [ -f "${serverPath}/yufeng_panel/plugins/mysql/index.py" ]; then
		(cd "${serverPath}/yufeng_panel" && python3 "${serverPath}/yufeng_panel/plugins/mysql/index.py" stop_and_kill 2>/dev/null) || true
	fi
	if command -v pgrep >/dev/null 2>&1; then
		for _pid in $(pgrep -f "^${serverPath}/mysql/bin/mysqld" 2>/dev/null); do
			kill "$_pid" 2>/dev/null || true
		done
		sleep 1
		for _pid in $(pgrep -f "^${serverPath}/mysql/bin/mysqld" 2>/dev/null); do
			kill -9 "$_pid" 2>/dev/null || true
		done
	fi
	rm -rf $serverPath/mysql
	echo '卸载完成'
}

action=$1
if [ "${1}" == "install" ];then
	Install_mysql
else
	Uninstall_mysql
fi