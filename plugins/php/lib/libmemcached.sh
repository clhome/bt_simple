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

#----------------------------- libmemcached start -------------------------#
if [ ! -d ${SERVER_ROOT}/libmemcached ];then
    cd ${SOURCE_ROOT}
    if [ ! -f ${SOURCE_ROOT}/libmemcached-1.0.18.tar.gz ];then
        github_download ${SOURCE_ROOT}/libmemcached-1.0.18.tar.gz https://github.com/clhome/bt_simple/releases/download/init/libmemcached-1.0.18.tar.gz
    fi 
    tar -zxf libmemcached-1.0.18.tar.gz
    cd libmemcached-1.0.18

    # sed -i '_bak' "41,52s#ulong#zend_ulong#g" ${SERVER_ROOT}/libmemcached-1.0.18/clients/memflush.cc
    sed -i "s#opt_servers == false#\!opt_servers#g" ${SERVER_ROOT}/libmemcached-1.0.18/clients/memflush.cc
    # sed -i "s#opt_servers == false#\!opt_servers#g" /www/server/source/lib/libmemcached-1.0.18/clients/memflush.cc
    ./configure --prefix=${SERVER_ROOT}/libmemcached -with-memcached && make -j${cpuCore:-1} && make install

    cd $SOURCE_ROOT && rm -rf $SOURCE_ROOT/libmemcached-1.0.18
    
fi
#----------------------------- libmemcached end -------------------------#