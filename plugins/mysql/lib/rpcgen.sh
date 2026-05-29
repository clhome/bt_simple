#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

# 引入统一的 GitHub 下载函数库
_gh_lib=$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd ../../../scripts 2>/dev/null && pwd)/github_download.sh
if [ -f "$_gh_lib" ]; then
    source "$_gh_lib"
fi

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")

# echo $rootPath

SERVER_ROOT=$rootPath/lib
SOURCE_ROOT=$rootPath/source/lib

which rpcgen
if [ "$?" != "0" ];then
	
	if [ ! -f ${SOURCE_ROOT}/rpcsvc-proto-1.4.tar.gz ];then
		github_download ${SOURCE_ROOT}/rpcsvc-proto-1.4.tar.gz https://github.com/thkukuk/rpcsvc-proto/releases/download/v1.4/rpcsvc-proto-1.4.tar.gz
	fi

	if [ ! -d ${SERVER_ROOT}/rpcsvc-proto-1.4 ];then
		cd ${SOURCE_ROOT} && tar -zxvf rpcsvc-proto-1.4.tar.gz
		cd ${SOURCE_ROOT}/rpcsvc-proto-1.4
		./configure && make  && make install
	fi	

fi