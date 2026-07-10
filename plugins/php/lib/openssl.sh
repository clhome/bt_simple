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

opensslVersion="3.5.2"
# echo $rootPath

SERVER_ROOT=$rootPath/lib
SOURCE_ROOT=$rootPath/source/lib
mkdir -p $SOURCE_ROOT

if [ ! -d ${SERVER_ROOT}/openssl ];then
    cd ${SOURCE_ROOT}
    if [ ! -f ${SOURCE_ROOT}/openssl-${opensslVersion}.tar.gz ];then
        github_download ${SOURCE_ROOT}/openssl-${opensslVersion}.tar.gz https://github.com/openssl/openssl/releases/download/openssl-${opensslVersion}/openssl-${opensslVersion}.tar.gz
    fi 
    tar -zxf openssl-${opensslVersion}.tar.gz
    cd openssl-${opensslVersion}
    ./config --prefix=${SERVER_ROOT}/openssl zlib-dynamic shared
    make -j${cpuCore:-1} && make install

    cd $SOURCE_ROOT && rm -rf $SOURCE_ROOT/openssl-${opensslVersion}
fi

