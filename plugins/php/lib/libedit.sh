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

# cd /www/server/yufeng_panel/plugins/php/lib && bash libedit.sh

# echo $rootPath

SERVER_ROOT=$rootPath/lib
SOURCE_ROOT=$rootPath/source/lib

if [ ! -d ${SERVER_ROOT}/libedit ];then
    cd $SOURCE_ROOT

    VERSION="20230828-3.1"

    if [ ! -f ${SOURCE_ROOT}/libedit-${VERSION}.tar.gz ];then
       github_download ${SOURCE_ROOT}/libedit-${VERSION}.tar.gz https://github.com/clhome/bt_simple/releases/download/init/libedit-${VERSION}.tar.gz
    fi

    if [ ! -d ${SOURCE_ROOT}/libedit-${VERSION} ];then
        cd $SOURCE_ROOT && tar -zxf libedit-${VERSION}.tar.gz
    fi

    cd ${SOURCE_ROOT}/libedit-${VERSION}

    ./configure --prefix=${SERVER_ROOT}/libedit && make -j${cpuCore:-1} && make install

    if [ -d $SOURCE_ROOT/libedit-${VERSION} ];then 
        cd $SOURCE_ROOT && rm -rf $SOURCE_ROOT/libedit-${VERSION}
    fi
fi