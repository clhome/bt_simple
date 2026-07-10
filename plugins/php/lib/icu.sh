#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

# 引入统一的 GitHub 下载函数库
_gh_lib=$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd ../../../scripts 2>/dev/null && pwd)/github_download.sh
if [ -f "$_gh_lib" ]; then
    source "$_gh_lib"
fi

# 引入共享编译环境 (cpuCore)
_env_lib=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common_env.sh
if [ -f "$_env_lib" ]; then source "$_env_lib"; fi

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")

# echo $rootPath

SERVER_ROOT=$rootPath/lib
SOURCE_ROOT=$rootPath/source/lib

if [ ! -d ${SERVER_ROOT}/icu ];then
	
	cd ${SOURCE_ROOT}

	if [ ! -f ${SOURCE_ROOT}/icu4c-52_2-src.tgz ];then
		github_download ${SOURCE_ROOT}/icu4c-52_2-src.tgz https://github.com/unicode-org/icu/releases/download/release-52-2/icu4c-52_2-src.tgz
	fi

	if [ ! -d ${SERVER_ROOT}/lib/icu/lib ];then
		cd ${SOURCE_ROOT} && tar -zxf icu4c-52_2-src.tgz

		cd ${SOURCE_ROOT}/icu/source
		./runConfigureICU Linux --prefix=${SERVER_ROOT}/icu && make -j${cpuCore:-1} CXXFLAGS="-g -O2 -std=c++11" && make install

		# export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/www/server/lib/icu/lib
		if [ -d /etc/ld.so.conf.d ];then
			echo "/www/server/lib/icu/lib" > /etc/ld.so.conf.d/mw-icu.conf
		elif [ -f /etc/ld.so.conf ]; then
			echo "/www/server/lib/icu/lib" >> /etc/ld.so.conf
		fi

		ldconfig

		cd $SOURCE_ROOT && rm -rf ${SOURCE_ROOT}/icu
	fi

fi