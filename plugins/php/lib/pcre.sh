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

SERVER_ROOT=$rootPath/lib
SOURCE_ROOT=$rootPath/source/lib
mkdir -p $SOURCE_ROOT

pcreVersion='8.38'

if [ ! -d ${SERVER_ROOT}/pcre ];then
    cd ${SOURCE_ROOT}

    if [ ! -f ${SOURCE_ROOT}/pcre-${pcreVersion}.tar.gz ];then
        github_download ${SOURCE_ROOT}/pcre-${pcreVersion}.tar.gz https://github.com/clhome/bt_simple/releases/download/init/pcre-${pcreVersion}.tar.gz
    fi
    

    if [ ! -d ${SOURCE_ROOT}/pcre-${pcreVersion} ];then
        cd ${SOURCE_ROOT} && tar -zxf pcre-${pcreVersion}.tar.gz
        
    fi

    cd ${SOURCE_ROOT}/pcre-${pcreVersion}
    ./configure --prefix=${SERVER_ROOT}/pcre
    make -j${cpuCore:-1} && make install

    cd $SOURCE_ROOT && rm -rf ${SOURCE_ROOT}/pcre-${pcreVersion}
fi

