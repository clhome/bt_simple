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

opensslVersion="1.0.2u"
# echo $rootPath

SERVER_ROOT=$rootPath/lib
SOURCE_ROOT=$rootPath/source/lib

# 判存不能只看目录在不在：旧版本用 `--openssldir` 而没有 `--prefix`，
# 结果 openssl 被装进 /usr/local，${SERVER_ROOT}/openssl10 下没有 include/lib，
# 但目录确实存在 → 之后再也不会重装，依赖它的编译（MySQL 5.5/5.6、PHP 7.0）
# 会一直报「Wrong option or path for WITH_SSL=.../openssl10」。
_yf_ossl_ready() {
    [ -f "${SERVER_ROOT}/openssl10/include/openssl/ssl.h" ] || return 1
    if [ -f "${SERVER_ROOT}/openssl10/lib/libssl.so" ] ||        [ -f "${SERVER_ROOT}/openssl10/lib/libssl.a" ] ||        [ -f "${SERVER_ROOT}/openssl10/lib64/libssl.so" ] ||        [ -f "${SERVER_ROOT}/openssl10/lib64/libssl.a" ]; then
        return 0
    fi
    return 1
}

if ! _yf_ossl_ready; then
    # 残留的不完整目录先清掉（否则 configure/install 会混用旧文件）
    if [ -d "${SERVER_ROOT}/openssl10" ]; then
        echo "[openssl10][WARN] ${SERVER_ROOT}/openssl10 存在但缺 include/lib（旧版 --openssldir 写法留下的），重新编译安装"
        rm -rf "${SERVER_ROOT}/openssl10"
    fi
    mkdir -p ${SOURCE_ROOT}
    cd ${SOURCE_ROOT} || { echo "[openssl10][ERROR] 无法进入 ${SOURCE_ROOT}" >&2; exit 1; }

    if [ ! -f ${SOURCE_ROOT}/openssl-${opensslVersion}.tar.gz ];then
        github_download ${SOURCE_ROOT}/openssl-${opensslVersion}.tar.gz https://github.com/clhome/bt_simple/releases/download/init/openssl-${opensslVersion}.tar.gz
    fi
    if [ ! -s ${SOURCE_ROOT}/openssl-${opensslVersion}.tar.gz ]; then
        echo "[openssl10][ERROR] 下载 openssl-${opensslVersion}.tar.gz 失败" >&2
        exit 1
    fi

    tar -zxf openssl-${opensslVersion}.tar.gz || { echo "[openssl10][ERROR] 解压失败" >&2; exit 1; }
    cd openssl-${opensslVersion} || { echo "[openssl10][ERROR] 源码目录不存在" >&2; exit 1; }
    # 关键：--prefix 才是安装目的地；--openssldir 只是配置目录（旧写法把它当 prefix 用了）
    # `-fcommon`：OpenSSL 1.0.2 有多个 tentatively-defined 全局变量，gcc>=10
    # 默认 -fno-common 会直接链接失败（Debian 12 / Ubuntu 22.04 上必踩）。
    # 传递方式很关键：OpenSSL **1.0.2 的 Configure 不读 CFLAGS 环境变量**
    # （只读 CC/RANLIB/AR/PERL/MAKE），它把任何 `-*` 命令行参数原样并进 cflags
    # （Configure 里 `$flags.=$_` → `$cflags="$flags$cflags"`，已核对 1.0.2u 源码）。
    # 所以 -fcommon **必须作为 ./config 的参数**；只 export CFLAGS 在 1.0.2 上是空操作。
    export CFLAGS="-fcommon ${CFLAGS:-}"
    ./config -fcommon --prefix=${SERVER_ROOT}/openssl10 \
             --openssldir=${SERVER_ROOT}/openssl10/ssl \
             zlib-dynamic shared || { echo "[openssl10][ERROR] ./config 失败" >&2; exit 1; }
    if ! make -j${cpuCore:-1}; then
        echo "[openssl10][ERROR] make 失败" >&2
        exit 1
    fi
    if ! make install; then
        echo "[openssl10][ERROR] make install 失败" >&2
        exit 1
    fi

    # export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:${SERVER_ROOT}/openssl10/lib
    if [ -d /etc/ld.so.conf.d ];then
        echo "${SERVER_ROOT}/openssl10/lib" > /etc/ld.so.conf.d/openssl10.conf
    elif [ -f /etc/ld.so.conf ]; then
        echo "${SERVER_ROOT}/openssl10/lib" >> /etc/ld.so.conf
    fi

    ldconfig
    # ldconfig -p  | grep openssl

    cd $SOURCE_ROOT && rm -rf $SOURCE_ROOT/openssl-${opensslVersion}
fi

if [ ! -d ${SERVER_ROOT}/openssl10/lib64 ] && [ -d ${SERVER_ROOT}/openssl10/lib ]; then
    ln -sf ${SERVER_ROOT}/openssl10/lib ${SERVER_ROOT}/openssl10/lib64
elif [ ! -d ${SERVER_ROOT}/openssl10/lib ] && [ -d ${SERVER_ROOT}/openssl10/lib64 ]; then
    ln -sf ${SERVER_ROOT}/openssl10/lib64 ${SERVER_ROOT}/openssl10/lib
fi

# 装完回读：没有 ssl.h / libssl 就明确失败（让调用方拿得到非 0 退出码，
# 而不是等到 cmake/configure 阶段报一句看不懂的「Wrong option or path」）
if ! _yf_ossl_ready; then
    echo "[openssl10][ERROR] ${SERVER_ROOT}/openssl10 安装后仍缺 include/openssl/ssl.h 或 libssl，无法供编译使用" >&2
    exit 1
fi
echo "[openssl10] OK: ${SERVER_ROOT}/openssl10（$( ${SERVER_ROOT}/openssl10/bin/openssl version 2>/dev/null || echo 'version unknown' )）"
