#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

# 引入共享编译环境 (cpuCore)
_env_lib=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common_env.sh
if [ -f "$_env_lib" ]; then source "$_env_lib"; fi

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")

igmVersion="7.1.1-15"
# echo $rootPath

SERVER_ROOT=$rootPath/lib
SOURCE_ROOT=$rootPath/source/lib

if [ ! -d ${SERVER_ROOT}/ImageMagick ];then
    cd ${SOURCE_ROOT}
    if [ ! -f ${SOURCE_ROOT}/ImageMagick-${igmVersion}.tar.gz ];then
        wget --no-check-certificate -O ImageMagick-${igmVersion}.tar.gz  https://imagemagick.org/archive/ImageMagick-${igmVersion}.tar.gz -T 20
    fi

    tar -zxf ImageMagick-${igmVersion}.tar.gz
    cd ImageMagick-${igmVersion}
    ./configure --prefix=${SERVER_ROOT}/ImageMagick --disable-openmp
    make -j${cpuCore:-1} && make install

    if [ -d /etc/ld.so.conf.d ];then
        echo "/www/server/lib/ImageMagick/lib" > /etc/ld.so.conf.d/ImageMagick.conf
    elif [ -f /etc/ld.so.conf ]; then
        echo "/www/server/lib/ImageMagick/lib" >> /etc/ld.so.conf
    fi

    ldconfig

    cd $SOURCE_ROOT && rm -rf $SOURCE_ROOT/ImageMagick-${igmVersion}
fi


