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

# cd /www/server/yufeng_panel/plugins/php/lib && bash libedit.sh

# echo $rootPath

SERVER_ROOT=$rootPath/lib
SOURCE_ROOT=$rootPath/source/lib

# ---------------------------------------------------------------------------
# libedit —— readline 扩展的唯一外部依赖（《问题报告》P1-6）
#
# 历史实现有四处「静默失败」，合起来的表现是「php82/83/84/85 装完都没有 readline」，
# 而安装报告里 missing 却是空数组：
#   1. 唯一的下载地址是 GitHub release 资产
#      https://github.com/clhome/bt_simple/releases/download/init/libedit-20230828-3.1.tar.gz
#      —— 实测 **404**（资产已随 release 重建失效）；
#   2. 不看下载返回值、不校验包完整性：404 留下的 HTML 错误页直接进 tar；
#   3. `cd` 到不存在的源码目录失败后继续在当前目录 ./configure（报错也无人看）；
#   4. 全部步骤都没有 `|| exit`，脚本最后一句是真/假都不影响退出码。
# 结果：readline 的 `./configure` 报 "Package requirements (libedit) were not met"，
# 扩展脚本走失败路径 exit 0（机制 B），外层记成功。
#
# 现在的口径：
#   * 官方源优先（thrysoee.dk，实测 200/534KB），GitHub release 作为备用源；
#   * 下载后 `tar -tzf` 验完整性 + 必须能看到 `libedit-<ver>/configure`，否则换源重试；
#   * configure && make && make install 用 `&&` 链住，任一步失败即 exit 1；
#   * 装完回读 `include/histedit.h` + `lib/pkgconfig/libedit.pc`，缺一个就 exit 1。
# ---------------------------------------------------------------------------
VERSION="20230828-3.1"
LIBEDIT_TGZ="libedit-${VERSION}.tar.gz"
LIBEDIT_PREFIX="${SERVER_ROOT}/libedit"

# 源列表：官方源在前；GitHub release 保留为备用（将来补上资产就能用）
LIBEDIT_SOURCES="
https://thrysoee.dk/editline/${LIBEDIT_TGZ}
https://github.com/clhome/bt_simple/releases/download/init/${LIBEDIT_TGZ}
"

# 下载到 $1，成功（文件非空且是含 configure 的合法 tar.gz）返回 0
_yf_libedit_fetch() {
    local dst=$1
    local src
    local tmp="${dst}.part"
    for src in ${LIBEDIT_SOURCES}; do
        [ -n "${src}" ] || continue
        echo "[libedit] 尝试下载: ${src}"
        rm -f "${tmp}"
        if command -v github_download >/dev/null 2>&1; then
            github_download "${tmp}" "${src}" || true
        fi
        if [ ! -s "${tmp}" ]; then
            if command -v curl >/dev/null 2>&1; then
                curl -fsSL --connect-timeout 15 --max-time 180 -o "${tmp}" "${src}" || true
            elif command -v wget >/dev/null 2>&1; then
                wget -nv -T 60 -t 2 -O "${tmp}" "${src}" || true
            fi
        fi
        if [ -s "${tmp}" ] && tar -tzf "${tmp}" 2>/dev/null | grep -q "^libedit-${VERSION}/configure$"; then
            mv -f "${tmp}" "${dst}"
            echo "[libedit] 下载成功: ${dst}"
            return 0
        fi
        echo "[libedit][WARN] 该源不可用或包损坏: ${src}"
        rm -f "${tmp}"
    done
    return 1
}

if [ ! -d "${LIBEDIT_PREFIX}" ]; then
    # source/lib 目录不一定存在：旧实现直接 cd，失败后所有相对路径都错位
    mkdir -p "${SOURCE_ROOT}" || { echo "[libedit][ERROR] 无法创建 ${SOURCE_ROOT}" >&2; exit 1; }
    cd "${SOURCE_ROOT}" || { echo "[libedit][ERROR] 无法进入 ${SOURCE_ROOT}" >&2; exit 1; }

    if [ ! -f "${SOURCE_ROOT}/${LIBEDIT_TGZ}" ]; then
        _yf_libedit_fetch "${SOURCE_ROOT}/${LIBEDIT_TGZ}" || {
            echo "[libedit][ERROR] 所有下载源均失败，libedit 无法安装（readline 扩展将不可用）" >&2
            exit 1
        }
    else
        # 已有的包也要验：0 字节 / HTML 错误页会毒化重跑
        if ! tar -tzf "${SOURCE_ROOT}/${LIBEDIT_TGZ}" 2>/dev/null | grep -q "^libedit-${VERSION}/configure$"; then
            echo "[libedit][WARN] 本地已有的包损坏，删除后重新下载"
            rm -f "${SOURCE_ROOT}/${LIBEDIT_TGZ}"
            _yf_libedit_fetch "${SOURCE_ROOT}/${LIBEDIT_TGZ}" || {
                echo "[libedit][ERROR] 所有下载源均失败，libedit 无法安装（readline 扩展将不可用）" >&2
                exit 1
            }
        fi
    fi

    if [ ! -d "${SOURCE_ROOT}/libedit-${VERSION}" ]; then
        tar -zxf "${LIBEDIT_TGZ}" -C "${SOURCE_ROOT}" || {
            echo "[libedit][ERROR] 解压失败: ${SOURCE_ROOT}/${LIBEDIT_TGZ}" >&2
            exit 1
        }
    fi

    cd "${SOURCE_ROOT}/libedit-${VERSION}" || {
        echo "[libedit][ERROR] 源码目录不存在: ${SOURCE_ROOT}/libedit-${VERSION}" >&2
        exit 1
    }

    ./configure --prefix="${LIBEDIT_PREFIX}" && make -j"${cpuCore:-1}" && make install || {
        echo "[libedit][ERROR] libedit 编译/安装失败（prefix=${LIBEDIT_PREFIX}）" >&2
        exit 1
    }

    # 回读：扩展编译真正需要的是头文件与 pkg-config 文件，缺一个就等于没装
    if [ ! -f "${LIBEDIT_PREFIX}/include/histedit.h" ] || [ ! -f "${LIBEDIT_PREFIX}/lib/pkgconfig/libedit.pc" ]; then
        echo "[libedit][ERROR] 安装后回读失败：${LIBEDIT_PREFIX} 下缺少 histedit.h 或 lib/pkgconfig/libedit.pc" >&2
        exit 1
    fi
    echo "[libedit] 安装完成: ${LIBEDIT_PREFIX}"

    if [ -d "${SOURCE_ROOT}/libedit-${VERSION}" ]; then
        cd "${SOURCE_ROOT}" && rm -rf "${SOURCE_ROOT}/libedit-${VERSION}"
    fi
fi
