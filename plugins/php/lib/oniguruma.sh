#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

# 引入统一的 GitHub 下载函数库
_gh_lib=$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd ../../../scripts 2>/dev/null && pwd)/github_download.sh
if [ -f "$_gh_lib" ]; then
    source "$_gh_lib"
fi

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")

# echo $rootPath

SERVER_ROOT=$rootPath/lib
SOURCE_ROOT=$rootPath/source/lib

which onig-config
if [ "$?" != "0" ];then
    cd ${SOURCE_ROOT}
    if [ ! -f ${SOURCE_ROOT}/oniguruma-6.9.4.tar.gz ];then
        github_download ${SOURCE_ROOT}/oniguruma-6.9.4.tar.gz https://github.com/kkos/oniguruma/archive/v6.9.4.tar.gz
    fi

    if [ ! -d  cd ${SOURCE_ROOT}/oniguruma-6.9.4 ];then
        cd ${SOURCE_ROOT} && tar -zxvf oniguruma-6.9.4.tar.gz
    fi
    
    cd ${SOURCE_ROOT}/oniguruma-6.9.4 && ./autogen.sh && ./configure --prefix=/usr && make && make install
    cd $SOURCE_ROOT && rm -rf $SOURCE_ROOT/oniguruma-6.9.4
fi

