#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

# 引入统一的 GitHub 下载函数库
curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
_gh_lib=$(cd "$curPath" && cd ../../../../scripts 2>/dev/null && pwd)/github_download.sh
if [ -f "$_gh_lib" ]; then
    source "$_gh_lib"
fi

# cd /Users/midoks/Desktop/mwdev/server/mdserver-web/plugins/openresty && bash install.sh install 1.31.1
# cd /www/server/mdserver-web/plugins/openresty && bash install.sh install 1.31.1

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

sysName=`uname`
action=$1
type=$2

VERSION=1.31.1.1

openrestyDir=${serverPath}/source/openresty

Install_openresty()
{
	if [ "${action}" == "install" ];then
		if [ -d $serverPath/openresty ];then
			if [ -f $serverPath/openresty/version.pl ];then
				CURRENT_VERSION=$(cat $serverPath/openresty/version.pl)
				if [ "${CURRENT_VERSION}" == "${VERSION}" ];then
					echo "OpenResty ${VERSION} is already installed."
					exit 0
				fi
			fi
		fi
	fi
	
	# ----- cpu start ------
	if [ -z "${cpuCore}" ]; then
    	cpuCore="1"
	fi

	if [ -f /proc/cpuinfo ];then
		cpuCore=`cat /proc/cpuinfo | grep "processor" | wc -l`
	fi

	MEM_INFO=$(free -m|grep Mem|awk '{printf("%.f",($2)/1024)}')
	if [ "${cpuCore}" != "1" ] && [ "${MEM_INFO}" != "0" ];then
	    limitCore=$((MEM_INFO * 2))
	    if [ "${limitCore}" -lt "1" ]; then
	        limitCore="1"
	    fi
	    if [ "${cpuCore}" -gt "${limitCore}" ];then
	        cpuCore="${limitCore}"
	    fi
	else
	    cpuCore="1"
	fi

	if [ "${cpuCore}" -lt "1" ]; then
		cpuCore="1"
	fi
	# ----- cpu end ------

	# 强力停止并清退所有旧的 nginx/openresty 进程，杜绝 80 端口占用或 Text file busy 故障
	if [ -f /usr/lib/systemd/system/openresty.service ] || [ -f /lib/systemd/system/openresty.service ];then
		systemctl stop openresty
	fi
	if [ -f $serverPath/openresty/init.d/openresty ];then
		$serverPath/openresty/init.d/openresty stop
	fi
	killall -9 nginx 2>/dev/null
	killall -9 openresty 2>/dev/null
	pkill -9 nginx 2>/dev/null
	pkill -9 openresty 2>/dev/null

	mkdir -p ${openrestyDir}
	echo '正在安装脚本文件...'

	# wget -O openresty-1.21.4.1.tar.gz https://openresty.org/download/openresty-1.21.4.1.tar.gz
	if [ ! -f ${openrestyDir}/openresty-${VERSION}.tar.gz ];then
		wget --no-check-certificate -O ${openrestyDir}/openresty-${VERSION}.tar.gz https://openresty.org/download/openresty-${VERSION}.tar.gz -T 3
	fi

	DOWNLOAD_SIZE=`wc -c ${openrestyDir}/openresty-${VERSION}.tar.gz | awk '{print $1}'`
	if [ "$DOWNLOAD_SIZE" == "0" ];then
		echo 'download failed, download again'
		rm -rf ${openrestyDir}/openresty-${VERSION}.tar.gz
	fi

	# Last Download Method (USTC Mirror)
	if [ ! -f ${openrestyDir}/openresty-${VERSION}.tar.gz ];then
		wget --no-check-certificate -O ${openrestyDir}/openresty-${VERSION}.tar.gz https://mirrors.ustc.edu.cn/openresty/download/openresty-${VERSION}.tar.gz -T 10
	fi

	cd ${openrestyDir} && tar -zxvf openresty-${VERSION}.tar.gz

	OPTIONS=''

	opensslVersion="3.5.5"
	libresslVersion="3.9.1"
	pcreVersion='8.45'
	if [ "$sysName" == "Darwin" ];then

		if [ ! -f ${openrestyDir}/pcre-${pcreVersion}.tar.gz ];then
			wget --no-check-certificate -O ${openrestyDir}/pcre-${pcreVersion}.tar.gz https://netix.dl.sourceforge.net/project/pcre/pcre/${pcreVersion}/pcre-${pcreVersion}.tar.gz
		fi

		if [ ! -d ${openrestyDir}/pcre-${pcreVersion} ];then
			cd ${openrestyDir} &&  tar -zxvf pcre-${pcreVersion}.tar.gz
		fi
		OPTIONS="${OPTIONS} --with-pcre=${openrestyDir}/pcre-${pcreVersion}"


		if [ ! -f ${openrestyDir}/openssl-${opensslVersion}.tar.gz ];then
	        github_download ${openrestyDir}/openssl-${opensslVersion}.tar.gz https://github.com/openssl/openssl/releases/download/openssl-${opensslVersion}/openssl-${opensslVersion}.tar.gz
	    fi

	    if [ ! -d ${openrestyDir}/openssl-${opensslVersion} ];then
			cd ${openrestyDir} &&  tar -zxvf openssl-${opensslVersion}.tar.gz
		fi
	    OPTIONS="${OPTIONS} --with-openssl=${openrestyDir}/openssl-${opensslVersion}"

		# BREW_DIR=`which brew`
		# BREW_DIR=${BREW_DIR/\/bin\/brew/}

		# brew info openssl@1.1 | grep /opt/homebrew/Cellar/openssl@1.1 | cut -d \  -f 1 | awk 'END {print}'
		# OPENSSL_LIB_DEPEND_DIR=`brew info openssl@1.1 | grep ${BREW_DIR}/Cellar/openssl@1.1 | cut -d \  -f 1 | awk 'END {print}'`
		# OPTIONS="${OPTIONS} --with-openssl=${OPENSSL_LIB_DEPEND_DIR}"
	else
		if [ ! -f ${openrestyDir}/openssl-${opensslVersion}.tar.gz ];then
	        github_download ${openrestyDir}/openssl-${opensslVersion}.tar.gz https://github.com/openssl/openssl/releases/download/openssl-${opensslVersion}/openssl-${opensslVersion}.tar.gz
	    fi

	    if [ ! -d ${openrestyDir}/openssl-${opensslVersion} ];then
			cd ${openrestyDir} &&  tar -zxvf openssl-${opensslVersion}.tar.gz
		fi
		OPTIONS="${OPTIONS} --with-openssl=${openrestyDir}/openssl-${opensslVersion}"

	fi

	if [[ "$VERSION" =~ "1.31.1" ]];then
		OPTIONS="${OPTIONS} --with-http_v3_module"

		# if [ ! -f ${openrestyDir}/libressl-${libresslVersion}.tar.gz ];then
	    #     wget --no-check-certificate -O ${openrestyDir}/libressl-${libresslVersion}.tar.gz https://ftp.openbsd.org/pub/OpenBSD/LibreSSL/libressl-${libresslVersion}.tar.gz
	    # fi

	    # if [ ! -d ${openrestyDir}/libressl-${libresslVersion} ];then
		# 	cd ${openrestyDir} &&  tar -zxvf libressl-${libresslVersion}.tar.gz
		# fi
	    
	    # OPTIONS="${OPTIONS} --with-cc-opt=-I${openrestyDir}/libressl-${libresslVersion}/libressl/build/include"
	    # OPTIONS="${OPTIONS} --with-cc-opt=-I${openrestyDir}/libressl-${libresslVersion}/libressl/build/lib"
	fi

	# jemalloc
	jemallocVersion="5.3.0"
	ARM_CHECK=$(uname -a | grep -E 'aarch64|arm|ARM')
	if [ -z "${ARM_CHECK}" ] && [ "$sysName" != "Darwin" ];then
		if [ ! -f '/usr/local/lib/libjemalloc.so' ] && [ ! -f '/usr/lib/libjemalloc.so' ] && [ ! -f '/usr/lib64/libjemalloc.so' ]; then
			if [ ! -f ${openrestyDir}/jemalloc-${jemallocVersion}.tar.bz2 ];then
				github_download ${openrestyDir}/jemalloc-${jemallocVersion}.tar.bz2 https://github.com/jemalloc/jemalloc/releases/download/${jemallocVersion}/jemalloc-${jemallocVersion}.tar.bz2
			fi
			if [ ! -d ${openrestyDir}/jemalloc-${jemallocVersion} ];then
				cd ${openrestyDir} && tar -xvf jemalloc-${jemallocVersion}.tar.bz2
				cd jemalloc-${jemallocVersion}
				./configure
				CMD_MAKE=`which gmake`
				if [ "$?" == "0" ];then
					gmake -j${cpuCore} && gmake install
				else
					make -j${cpuCore} && make install
				fi
				ldconfig
			fi
		fi
		if [ -f '/usr/local/lib/libjemalloc.so' ] || [ -f '/usr/lib/libjemalloc.so' ] || [ -f '/usr/lib64/libjemalloc.so' ]; then
			OPTIONS="${OPTIONS} --with-ld-opt=-ljemalloc"
		fi
	fi

	# ngx_cache_purge
	if [ ! -d ${openrestyDir}/ngx_cache_purge-master ];then
		github_download ${openrestyDir}/ngx_cache_purge.tar.gz https://github.com/nginx-modules/ngx_cache_purge/archive/refs/heads/master.tar.gz
		cd ${openrestyDir} && tar -zxvf ngx_cache_purge.tar.gz
	fi
	OPTIONS="${OPTIONS} --add-module=${openrestyDir}/ngx_cache_purge-master"

	# nginx-http-concat
	if [ ! -d ${openrestyDir}/nginx-http-concat-master ];then
		github_download ${openrestyDir}/nginx-http-concat.tar.gz https://github.com/alibaba/nginx-http-concat/archive/refs/heads/master.tar.gz
		cd ${openrestyDir} && tar -zxvf nginx-http-concat.tar.gz
	fi
	OPTIONS="${OPTIONS} --add-module=${openrestyDir}/nginx-http-concat-master"

	# ngx_http_substitutions_filter_module
	if [ ! -d ${openrestyDir}/ngx_http_substitutions_filter_module-master ];then
		github_download ${openrestyDir}/ngx_http_substitutions_filter_module.tar.gz https://github.com/yaoweibin/ngx_http_substitutions_filter_module/archive/refs/heads/master.tar.gz
		cd ${openrestyDir} && tar -zxvf ngx_http_substitutions_filter_module.tar.gz
	fi
	OPTIONS="${OPTIONS} --add-module=${openrestyDir}/ngx_http_substitutions_filter_module-master"

	# br
	if [ ! -d ${openrestyDir}/ngx_brotli/deps/brotli/c ];then
		rm -rf ${openrestyDir}/ngx_brotli
		github_clone ${openrestyDir}/ngx_brotli https://github.com/wxx9248/ngx_brotli.git
		cd ${openrestyDir}/ngx_brotli && github_clone deps/brotli https://github.com/google/brotli.git
	fi
	OPTIONS="${OPTIONS} --add-module=${openrestyDir}/ngx_brotli"

	OPTIONS="${OPTIONS} --with-threads"
	OPTIONS="${OPTIONS} --with-file-aio"
	OPTIONS="${OPTIONS} --with-pcre-jit"
	OPTIONS="${OPTIONS} --with-http_gzip_static_module"

	#zstd
	if [ ! -d ${openrestyDir}/zstd-nginx-module-master ];then
		github_download $openrestyDir/zstd-nginx-module.tar.gz https://github.com/tokers/zstd-nginx-module/archive/refs/heads/master.tar.gz
		cd ${openrestyDir} && tar -zxvf zstd-nginx-module.tar.gz
	fi

	pkg-config --exists --print-errors libzstd
	if [ "$?" == "0" ];then
		OPTIONS="${OPTIONS} --add-module=${openrestyDir}/zstd-nginx-module-master"
	fi
	
	

	cd ${openrestyDir}/openresty-${VERSION} && ./configure \
	--prefix=$serverPath/openresty \
	$OPTIONS \
	--with-stream \
	--with-http_v2_module \
	--with-http_ssl_module  \
	--with-http_slice_module \
	--with-http_stub_status_module \
	--with-http_sub_module \
	--with-http_realip_module

	if [ "$?" != "0" ];then
		echo "Configure failed!"
		exit 1
	fi
	# --without-luajit-gc64
	# --with-debug
	# 用于调式

	# 避免正在运行的二进制导致 Text file busy 无法覆盖
	if [ -f $serverPath/openresty/nginx/sbin/nginx ];then
		mv -f $serverPath/openresty/nginx/sbin/nginx $serverPath/openresty/nginx/sbin/nginx.bak
	fi
	if [ -f $serverPath/openresty/bin/openresty ];then
		mv -f $serverPath/openresty/bin/openresty $serverPath/openresty/bin/openresty.bak
	fi

	CMD_MAKE=`which gmake`
	if [ "$?" == "0" ];then
		gmake -j${cpuCore} && gmake install && gmake clean
	else
		make -j${cpuCore} && make install && make clean
	fi


    if [ -d ${openrestyDir}/pcre-${pcreVersion} ];then
    	rm -rf ${openrestyDir}/pcre-${pcreVersion}
    fi

    if [ -d ${openrestyDir}/openssl-${opensslVersion} ];then
    	rm -rf ${openrestyDir}/openssl-${opensslVersion}
    fi

    if [ -d ${openrestyDir}/libressl-${libresslVersion} ];then
    	rm -rf ${openrestyDir}/libressl-${libresslVersion}
    fi

    if [ -d ${openrestyDir}/jemalloc-${jemallocVersion} ];then
    	rm -rf ${openrestyDir}/jemalloc-${jemallocVersion}
    fi

    if [ -d ${openrestyDir}/ngx_cache_purge-master ];then
    	rm -rf ${openrestyDir}/ngx_cache_purge-master
    fi

    if [ -d ${openrestyDir}/nginx-http-concat-master ];then
    	rm -rf ${openrestyDir}/nginx-http-concat-master
    fi

    if [ -d ${openrestyDir}/ngx_http_substitutions_filter_module-master ];then
    	rm -rf ${openrestyDir}/ngx_http_substitutions_filter_module-master
    fi

    if [ -d $openrestyDir/openresty-${VERSION} ];then
		rm -rf $openrestyDir/openresty-${VERSION}
	fi

	if [ -d $openrestyDir/zstd-nginx-module-master ];then
		rm -rf $openrestyDir/zstd-nginx-module-master
	fi

	# if [ -d $openrestyDir/ngx_brotli ];then
	# 	rm -rf $openrestyDir/ngx_brotli
	# fi
	echo 'Installation of Openresty completed'
}

Uninstall_openresty()
{
	echo 'Uninstalling Openresty completed'
}

action=$1
if [ "${1}" == "install" ];then
	Install_openresty
elif [ "${1}" == "upgrade" ];then
	Install_openresty
else
	Uninstall_openresty
fi
