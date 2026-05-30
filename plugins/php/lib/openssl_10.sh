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

opensslVersion="1.0.2u"
# echo $rootPath

SERVER_ROOT=$rootPath/lib
SOURCE_ROOT=$rootPath/source/lib

if [ ! -d ${SERVER_ROOT}/openssl10 ];then
    cd ${SOURCE_ROOT}

    if [ ! -f ${SOURCE_ROOT}/openssl-${opensslVersion}.tar.gz ];then
        github_download ${SOURCE_ROOT}/openssl-${opensslVersion}.tar.gz https://github.com/clhome/bt_simple/releases/download/init/openssl-${opensslVersion}.tar.gz
    fi

    tar -zxf openssl-${opensslVersion}.tar.gz
    cd openssl-${opensslVersion}
    ./config --openssldir=${SERVER_ROOT}/openssl10 zlib-dynamic shared
    make && make install

    # export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/www/server/lib/openssl10/lib
    if [ -d /etc/ld.so.conf.d ];then
        echo "/www/server/lib/openssl10/lib" > /etc/ld.so.conf.d/openssl10.conf
    elif [ -f /etc/ld.so.conf ]; then
        echo "/www/server/lib/openssl10/lib" >> /etc/ld.so.conf
    fi

    ldconfig
    # ldconfig -p  | grep openssl

    cd $SOURCE_ROOT && rm -rf $SOURCE_ROOT/openssl-${opensslVersion}
fi


