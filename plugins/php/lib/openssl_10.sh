#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")

opensslVersion="1.0.2u"
# echo $rootPath

SERVER_ROOT=$rootPath/lib
SOURCE_ROOT=$rootPath/source/lib

HTTP_PREFIX="https://"
LOCAL_ADDR=common
cn=$(curl -fsSL -m 10 http://ipinfo.io/json | grep "\"country\": \"CN\"")
if [ ! -z "$cn" ] || [ "$?" == "0" ] ;then
    LOCAL_ADDR=cn
    HTTP_PREFIX="https://mirror.ghproxy.com/"
fi

GH_PREFIX="https://github.com"
if [ "$LOCAL_ADDR" == "cn" ]; then
    GH_PREFIX="https://mirror.ghproxy.com/https://github.com"
fi

if [ ! -d ${SERVER_ROOT}/openssl10 ];then
    cd ${SOURCE_ROOT}

    if [ ! -f ${SOURCE_ROOT}/openssl-${opensslVersion}.tar.gz ];then
        wget --no-check-certificate -O openssl-${opensslVersion}.tar.gz ${GH_PREFIX}/clhome/bt_simple/releases/download/init/openssl-${opensslVersion}.tar.gz -T 20
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


