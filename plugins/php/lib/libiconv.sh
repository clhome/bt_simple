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

# cd /www/server/mdserver-web/plugins/php/lib && bash libiconv.sh

# echo $rootPath

SERVER_ROOT=$rootPath/lib
SOURCE_ROOT=$rootPath/source/lib

if [ ! -d ${SERVER_ROOT}/libiconv ];then
    cd $SOURCE_ROOT

    if [ ! -f ${SOURCE_ROOT}/libiconv-1.15.tar.gz ];then
        github_download ${SOURCE_ROOT}/libiconv-1.15.tar.gz https://github.com/clhome/bt_simple/releases/download/init/libiconv-1.15.tar.gz
    fi

    if [ ! -d ${SOURCE_ROOT}/libiconv-1.15 ];then
        cd $SOURCE_ROOT && tar -zxf libiconv-1.15.tar.gz
    fi

    cd ${SOURCE_ROOT}/libiconv-1.15

    ./configure --prefix=${SERVER_ROOT}/libiconv --enable-static && make -j${cpuCore:-1} && make install

    if [ -d $SOURCE_ROOT/libiconv-1.15 ];then 
        cd $SOURCE_ROOT && rm -rf $SOURCE_ROOT/libiconv-1.15
    fi
fi