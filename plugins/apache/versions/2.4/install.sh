#!/bin/bash
if [ -f $(dirname $0)/../../scripts/lib_make_jobs.sh ]; then source $(dirname $0)/../../scripts/lib_make_jobs.sh; elif [ -f /www/server/yufeng_panel/scripts/lib_make_jobs.sh ]; then source /www/server/yufeng_panel/scripts/lib_make_jobs.sh; fi
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH



curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

sysName=`uname`
action=$1
type=$2

VERSION=2.4.66
apacheDir=${serverPath}/source/apache

Install_App()
{
	if [ "${action}" == "install" ];then
		# 幂等秒退的前提是「真的装好了」（《问题报告》P1-4 坑 4）：
		# 旧写法 `[ -d $serverPath/apache ]` 只看目录存在 —— 上一次安装失败留下的
		# 空/残缺目录会让重跑秒退 exit 0，永久卡在「面板显示已装、机器上没有 httpd」。
		if [ -x ${serverPath}/apache/httpd/bin/httpd ];then
			echo 'apache 已安装（httpd 二进制存在），跳过'
			exit 0
		fi
		if [ -d ${serverPath}/apache ];then
			echo '检测到残留的不完整 apache 目录，清理后重装'
			rm -rf ${serverPath}/apache
		fi
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

	mkdir -p ${apacheDir}
	echo 'install script ...'
	OPTIONS=''

	# 安装 APR 和 APR-util
	APR_VERSION=1.7.6
	APR_UTIL_VERSION=1.6.3

	# --------------------------------------------------------------------------
	# 源码包获取（《问题报告》P1-4）：
	#   ① 下架：`downloads.apache.org` 只保留**当前版本**，apr-util 1.6.3 与
		#      httpd 2.4.66 实测 404（apr 1.7.6 尚在，但同一批依赖不能混着两个源用，
		#      否则下次 apr 也下架时又是一模一样的假成功）；archive.apache.org 保留全部
		#      历史版本，实测三个包均 200。
	#   ② 0 字节毒化：旧代码 `wget -T 3` 不看退出码、不校验包，404 留下的空文件/
		#      HTML 错误页会让守卫 `[ ! -f ... ]` 下次直接跳过 → tar 必死、重跑必死。
	# 所以下载统一走 yf_apache_fetch：curl → wget 回退，cURL 失败即时删包，
	# 并以 `tar -tjf` 验证 bzip2 完整性与可解压性，任一步失败立即 exit 1。
	# --------------------------------------------------------------------------
	yf_apache_fetch() {
		local _file=$1
		local _url=$2
		# 已存在且能解压 ⇒ 直接用（幂等重跑不重下）
		if [ -s "${_file}" ] && tar -tjf "${_file}" >/dev/null 2>&1; then
			return 0
		fi
		# 存在但坏（0 字节/HTML 页/截断）⇒ 删掉重下，绝不留毒
		if [ -f "${_file}" ]; then
			echo "[apache][WARN] 源码包损坏，删除重下: ${_file}"
			rm -f "${_file}"
		fi
		echo "[apache] 下载: ${_url}"
		if command -v curl >/dev/null 2>&1; then
			curl -fsSL --connect-timeout 15 --max-time 900 -o "${_file}" "${_url}" || rm -f "${_file}"
		fi
		if [ ! -s "${_file}" ] && command -v wget >/dev/null 2>&1; then
			wget -nv --no-check-certificate -T 120 -t 2 -O "${_file}" "${_url}" || rm -f "${_file}"
		fi
		if [ ! -s "${_file}" ] || ! tar -tjf "${_file}" >/dev/null 2>&1; then
			rm -f "${_file}"
			echo "[apache][ERROR] 下载失败或源码包损坏: ${_url}" >&2
			return 1
		fi
		return 0
	}

	yf_apache_fetch ${apacheDir}/apr-${APR_VERSION}.tar.bz2 "https://archive.apache.org/dist/apr/apr-${APR_VERSION}.tar.bz2" || exit 1
	yf_apache_fetch ${apacheDir}/apr-util-${APR_UTIL_VERSION}.tar.bz2 "https://archive.apache.org/dist/apr/apr-util-${APR_UTIL_VERSION}.tar.bz2" || exit 1
	yf_apache_fetch ${apacheDir}/httpd-${VERSION}.tar.bz2 "https://archive.apache.org/dist/httpd/httpd-${VERSION}.tar.bz2" || exit 1

	# 安装 APR
	#   configure 与 make 必须同一条 `&&` 链（《问题报告》P1-5 机制 A）：
	#   旧写法 configure 一行、`make -j` 另一行且无条件执行，configure 失败
	#   （缺编译器/缺依赖）时 make 照跑，最后只留一句含糊的 "APR configure failed"
	#   甚至直接落到下一段。
	if [ ! -d ${serverPath}/apache/apr ];then
		cd ${apacheDir} && tar -jxf apr-${APR_VERSION}.tar.bz2 || { echo "[apache][ERROR] 解压失败: apr-${APR_VERSION}" >&2; exit 1; }
		cd ${apacheDir}/apr-${APR_VERSION} && ./configure --prefix=${serverPath}/apache/apr && make -j${cpuCore} && make install || {
			echo "[apache][ERROR] APR 编译安装失败（configure 或 make 非 0）" >&2
			exit 1
		}
		# 检查 APR 配置文件
		APR_CONFIG=$(find ${serverPath}/apache/apr -name "apr-*config" | head -1)
		if [ -z "$APR_CONFIG" ];then
			echo "[apache][ERROR] APR installation failed: apr-config not found" >&2
			exit 1
		fi
		echo "APR installed successfully: $APR_CONFIG"
	fi

	# 安装 APR-util
	if [ ! -d ${serverPath}/apache/apr-util ];then
		cd ${apacheDir} && tar -jxf apr-util-${APR_UTIL_VERSION}.tar.bz2 || { echo "[apache][ERROR] 解压失败: apr-util-${APR_UTIL_VERSION}" >&2; exit 1; }
		cd ${apacheDir}/apr-util-${APR_UTIL_VERSION} && ./configure --prefix=${serverPath}/apache/apr-util --with-apr=${serverPath}/apache/apr && make -j${cpuCore} && make install || {
			echo "[apache][ERROR] APR-util 编译安装失败（configure 或 make 非 0）" >&2
			exit 1
		}
		# 检查 APR-util 配置文件
		APU_CONFIG=$(find ${serverPath}/apache/apr-util -name "apu-*config" | head -1)
		if [ -z "$APU_CONFIG" ];then
			echo "[apache][ERROR] APR-util installation failed: apu-config not found" >&2
			exit 1
		fi
		echo "APR-util installed successfully: $APU_CONFIG"
	fi

	if [ ! -d ${apacheDir}/httpd-${VERSION} ];then
		cd ${apacheDir} && tar -jxf ${apacheDir}/httpd-${VERSION}.tar.bz2 || { echo "[apache][ERROR] 解压失败: httpd-${VERSION}" >&2; exit 1; }
	fi
	

	# 检查 APR 和 APR-util 可执行文件
	APR_CONFIG=$(find ${serverPath}/apache/apr -name "apr-*config" | head -1)
	APU_CONFIG=$(find ${serverPath}/apache/apr-util -name "apu-*config" | head -1)

	if [ -z "$APR_CONFIG" ];then
		echo "[apache][ERROR] APR config not found" >&2
		exit 1
	fi

	if [ -z "$APU_CONFIG" ];then
		echo "[apache][ERROR] APR-util config not found" >&2
		exit 1
	fi

	OPTIONS="${OPTIONS} --with-apr=$APR_CONFIG"
	OPTIONS="${OPTIONS} --with-apr-util=$APU_CONFIG"

	# if [ "$sysName" != "Darwin" ];then
	# 	OPTIONS="${OPTIONS} --enable-systemd"
	# fi
	# 同机制 A：configure 与 make 同一条链，失败即 exit 1，绝不打印 completed
	cd ${apacheDir}/httpd-${VERSION} && ./configure \
	--prefix=$serverPath/apache/httpd \
	$OPTIONS && make -j${cpuCore} && make install && make clean || {
		echo "[apache][ERROR] httpd 编译安装失败（configure 或 make 非 0）" >&2
		exit 1
	}

	if [ -d ${apacheDir}/apr-${APR_VERSION} ];then
    	rm -rf ${apacheDir}/apr-${APR_VERSION}
    fi

    if [ -d ${apacheDir}/apr-util-${APR_UTIL_VERSION} ];then
    	rm -rf ${apacheDir}/apr-util-${APR_UTIL_VERSION}
    fi

    # 旧写法删的是 `httpd-${APR_UTIL_VERSION}`（= httpd-1.6.3，永不存在的目录），
    # 于是 httpd-2.4.66 源码树永远留在磁盘上（几百 MB）。
    if [ -d ${apacheDir}/httpd-${VERSION} ];then
    	rm -rf ${apacheDir}/httpd-${VERSION}
    fi

	# 装后回读：没有二进制就是没装上，不许打印 completed（《问题报告》P1-4）
	if [ ! -x ${serverPath}/apache/httpd/bin/httpd ];then
		echo "[apache][ERROR] installation of apache failed: ${serverPath}/apache/httpd/bin/httpd 不存在或不可执行" >&2
		exit 1
	fi
	echo 'installation of apache completed'
}

Uninstall_App()
{
	echo 'uninstalling apache completed'
}

action=$1
if [ "${1}" == "install" ];then
	Install_App
elif [ "${1}" == "upgrade" ];then
	Install_App
else
	Uninstall_App
fi