#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
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

mkdir -p  $SOURCE_ROOT

if [ ! -d ${SERVER_ROOT}/zlib ];then

    cd $SOURCE_ROOT

    if [ ! -f ${SOURCE_ROOT}/zlib-1.2.11.tar.gz ];then
        github_download ${SOURCE_ROOT}/zlib-1.2.11.tar.gz https://github.com/madler/zlib/archive/v1.2.11.tar.gz
    fi

    if [ ! -d ${SOURCE_ROOT}/zlib-1.2.11 ];then
        cd $SOURCE_ROOT && tar -zxvf zlib-1.2.11.tar.gz
    fi
    cd ${SOURCE_ROOT}/zlib-1.2.11

    ./configure --prefix=${SERVER_ROOT}/zlib && make && make install

    cd $SOURCE_ROOT && rm -rf $SOURCE_ROOT/zlib-1.2.11
    #rm -rf zlib-1.2.11
    #rm -rf zlib-1.2.11.tar.gz
fi