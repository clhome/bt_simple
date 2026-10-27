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
opensslVersion="1.1.1w"
# echo $rootPath

SERVER_ROOT=$rootPath/lib
SOURCE_ROOT=$rootPath/source/lib
mkdir -p $SOURCE_ROOT

# 判存不能只看目录在不在：中断过的安装会留下空目录，之后再也不会重装，
# 依赖它的编译只会报「Wrong option or path」这种看不懂的错。
_yf_ossl_ready() {
    [ -f "${SERVER_ROOT}/openssl11/include/openssl/ssl.h" ] || return 1
    for _d in "${SERVER_ROOT}/openssl11/lib" "${SERVER_ROOT}/openssl11/lib64"; do
        if [ -f "${_d}/libssl.so" ] || [ -f "${_d}/libssl.a" ]; then
            return 0
        fi
    done
    return 1
}

if ! _yf_ossl_ready; then
    if [ -d "${SERVER_ROOT}/openssl11" ]; then
        echo "[openssl11][WARN] ${SERVER_ROOT}/openssl11 存在但缺 include/lib，重新编译安装"
        rm -rf "${SERVER_ROOT}/openssl11"
    fi
    cd ${SOURCE_ROOT}
    if [ ! -f ${SOURCE_ROOT}/openssl-${opensslVersion}.tar.gz ];then
        github_download ${SOURCE_ROOT}/openssl-${opensslVersion}.tar.gz https://github.com/openssl/openssl/releases/download/OpenSSL_${opensslVersion//./_}/openssl-${opensslVersion}.tar.gz
    fi 
    tar -zxf openssl-${opensslVersion}.tar.gz
    cd openssl-${opensslVersion}
    ./config --prefix=${SERVER_ROOT}/openssl11 zlib-dynamic shared
    make -j${cpuCore:-1} || { echo "[openssl11][ERROR] make 失败" >&2; exit 1; }
    make install || { echo "[openssl11][ERROR] make install 失败" >&2; exit 1; }

    # export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:${SERVER_ROOT}/openssl11/lib
    if [ -d /etc/ld.so.conf.d ];then
        echo "${SERVER_ROOT}/openssl11/lib" > /etc/ld.so.conf.d/openssl11.conf
    elif [ -f /etc/ld.so.conf ]; then
        echo "${SERVER_ROOT}/openssl11/lib" >> /etc/ld.so.conf
    fi

    ldconfig
    # ldconfig -p  | grep openssl

    cd $SOURCE_ROOT && rm -rf $SOURCE_ROOT/openssl-${opensslVersion}
fi

if [ ! -d ${SERVER_ROOT}/openssl11/lib64 ] && [ -d ${SERVER_ROOT}/openssl11/lib ]; then
    ln -sf ${SERVER_ROOT}/openssl11/lib ${SERVER_ROOT}/openssl11/lib64
elif [ ! -d ${SERVER_ROOT}/openssl11/lib ] && [ -d ${SERVER_ROOT}/openssl11/lib64 ]; then
    ln -sf ${SERVER_ROOT}/openssl11/lib64 ${SERVER_ROOT}/openssl11/lib
fi

# 装完回读：缺 ssl.h/libssl 就明确失败（让调用方拿到非 0，而不是后续 cmake/configure 报怪错）
if ! _yf_ossl_ready; then
    echo "[openssl11][ERROR] ${SERVER_ROOT}/openssl11 安装后仍缺 include/openssl/ssl.h 或 libssl" >&2
    exit 1
fi
