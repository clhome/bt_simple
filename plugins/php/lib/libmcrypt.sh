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


ISFIND="0"
SYS_DIR=(/usr/local /usr)
for S_DIR in ${SYS_DIR[@]}; do
    if [ -f $S_DIR/include/mcrypt.h ];then
        ISFIND="1"
    fi
done

if [ $ISFIND == "0" ];then
    cd $SOURCE_ROOT
    if [ ! -f ${SOURCE_ROOT}/libmcrypt-2.5.8.tar.gz ];then
        github_download ${SOURCE_ROOT}/libmcrypt-2.5.8.tar.gz https://github.com/clhome/bt_simple/releases/download/init/libmcrypt-2.5.8.tar.gz
    fi

    tar -zxf libmcrypt-2.5.8.tar.gz
    cd libmcrypt-2.5.8
    ./configure && make -j${cpuCore:-1} && make install && make clean

    cd $SOURCE_ROOT && rm -rf $SOURCE_ROOT/libmcrypt-2.5.8
fi