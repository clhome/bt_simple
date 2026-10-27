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
# -*- coding: utf-8 -*-
#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

#https://dev.mysql.com/downloads/mysql/5.6.html
#https://dev.mysql.com/downloads/file/?id=489600

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")
sysName=`uname`
sysArch=`arch`

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


mysqlDir=${serverPath}/source/mysql

VERSION=5.6.51
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
		wget -nv --no-check-certificate -O ${mysqlDir}/mysql-${VERSION}.tar.gz --tries=3 https://cdn.mysql.com/Downloads/MySQL-5.6/mysql-${VERSION}.tar.gz
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

	if [ "$OSNAME" == "ubuntu" ];then
		apt install -y libudev-dev
		apt install -y libtirpc-dev
		apt install -y libssl-dev
		apt install -y libgssglue-dev
		apt install -y software-properties-common
		add-apt-repository -y ppa:ubuntu-toolchain-r/test

		export PKG_CONFIG_PATH=/usr/lib/pkgconfig
		apt install -y gcc-11 g++-11
		WHERE_DIR_GCC=/usr/bin/gcc-11
		WHERE_DIR_GPP=/usr/bin/g++-11
	fi

	OPTIONS=''
	# MySQL 5.6 在 OpenSSL 3.x 的发行版上只有一条可行路径：自建 OpenSSL 1.0.x。
	# 三条都实测过（2026-10-27，下载 mysql-5.6.51 源码逐条核对）：
	#   ① 不指定 WITH_SSL → CMake 默认 `WITH_SSL=system` →
	#      「Cannot find appropriate system libraries for WITH_SSL=system」（CI 第二次红）；
	#   ② `-DWITH_SSL=bundled` → **5.6.51 已移除 extra/yassl**，ssl.cmake 只认
	#      system/yes/<path>，bundled 会直接报「Wrong option or path」；
	#   ③ `-DWITH_SSL=<自建 1.0.2 路径>` → 唯一能编过的（5.6 只支持 1.0.x）。
	# 自建脚本内有判存：已经装过 OpenSSL 1.0.2 的机器会直接跳过，不会重复编译。
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

	if [ -d $serverPath/mysql ] && [ ! -f $serverPath/mysql/bin/mysql ]; then
		echo "检测到残留的不完整 MySQL 编译安装目录，正在清理..."
		rm -rf $serverPath/mysql
	fi

	if [ ! -d $serverPath/mysql ];then
		cd ${mysqlDir}/mysql-${VERSION} && cmake \
		-DCMAKE_INSTALL_PREFIX=$serverPath/mysql \
		-DMYSQL_USER=mysql \
		-DMYSQL_TCP_PORT=3306 \
		-DMYSQL_UNIX_ADDR=/var/tmp/mysql.sock \
		-DWITH_MYISAM_STORAGE_ENGINE=1 \
		-DWITH_INNOBASE_STORAGE_ENGINE=1 \
		-DWITH_MEMORY_STORAGE_ENGINE=1 \
		-DENABLED_LOCAL_INFILE=1 \
		-DWITH_PARTITION_STORAGE_ENGINE=1 \
		-DENABLE_DOWNLOADS=1 \
		-DEXTRA_CHARSETS=all \
		-DDEFAULT_CHARSET=utf8mb4 \
		-DDEFAULT_COLLATION=utf8mb4_general_ci \
		$OPTIONS \
		-DCMAKE_C_COMPILER=$WHERE_DIR_GCC \
		-DCMAKE_CXX_COMPILER=$WHERE_DIR_GPP \
		-DCMAKE_CXX_STANDARD=11 && \
		make -j${cpuCore} && make install && make clean || {
			echo "[ERROR] cmake / make 失败：mysql 编译安装未完成（见上方 cmake 日志）" >&2
			exit 1
		}



		if [ -d $serverPath/mysql ];then
			rm -rf ${mysqlDir}/mysql-${VERSION}
			echo '5.6' > $serverPath/mysql/version.pl
			echo "${VERSION}安装完成"
		else
			# rm -rf ${mysqlDir}/mysql-5.6.*
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