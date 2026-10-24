#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin

function version_gt() { test "$(echo "$@" | tr " " "\n" | sort -V | head -n 1)" != "$1"; }
function version_le() { test "$(echo "$@" | tr " " "\n" | sort -V | head -n 1)" == "$1"; }
function version_lt() { test "$(echo "$@" | tr " " "\n" | sort -rV | head -n 1)" != "$1"; }
function version_ge() { test "$(echo "$@" | tr " " "\n" | sort -rV | head -n 1)" == "$1"; }

P_VER=`python3 -V | awk '{print $2}'`
echo "python:$P_VER"
sleep 1

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(dirname "$curPath")
serverPath=$(dirname "$rootPath")
sourcePath=$serverPath/source/lib
libPath=$serverPath/lib

mkdir -p $sourcePath
mkdir -p $libPath
rm -rf ${libPath}/lib.pl


# 自动检测并清洗脚本中的 Windows CRLF 换行符
function fix_crlf() {
    local target_file=$1
    if [ -f "$target_file" ]; then
        if grep -q $'\r' "$target_file" 2>/dev/null; then
            sed -i 's/\r$//' "$target_file" 2>/dev/null
        fi
    fi
}

fix_crlf "${rootPath}/scripts/getos.sh"
bash ${rootPath}/scripts/getos.sh
OSNAME=`cat ${rootPath}/data/osname.pl 2>/dev/null`
VERSION_ID=`cat /etc/*-release 2>/dev/null | grep VERSION_ID | awk -F = '{print $2}' | awk -F "\"" '{print $2}'`

# system judge
if [ "$OSNAME" == "macos" ]; then
    brew install libmemcached
    brew install curl
    brew install zlib
    brew install freetype
    brew install openssl
    brew install libzip
elif [ "$OSNAME" == "opensuse" ];then
    echo "opensuse lib"
elif [ "$OSNAME" == "arch" ];then
    echo "arch lib"
elif [ "$OSNAME" == "freebsd" ];then
    echo "freebsd lib"
elif [ "$OSNAME" == "centos" ];then
    echo "centos lib"
elif [ "$OSNAME" == "rocky" ]; then
    echo "rocky lib"
elif [ "$OSNAME" == "fedora" ];then
    echo "fedora lib"
elif [ "$OSNAME" == "alma" ];then
    echo "alma lib"
elif [ "$OSNAME" == "ubuntu" ];then
    echo "ubuntu lib"
elif [ "$OSNAME" == "debian" ]; then
    echo "debian lib"
else
    echo "OK"
fi
echo "system:${OSNAME}:${VERSION_ID}"


# --- Common Helpers Start ---

# 引入统一的 GitHub 下载函数库
_gh_download_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)/github_download.sh"
if [ -f "$_gh_download_lib" ]; then
    fix_crlf "$_gh_download_lib"
    source "$_gh_download_lib"
fi

function get_local_addr() {
    if [ ! -z "$LOCAL_ADDR" ]; then
        echo $LOCAL_ADDR
        return
    fi
    local cn=$(curl -fsSL -m 5 -s http://ipinfo.io/json | grep "\"country\": \"CN\"")
    if [ ! -z "$cn" ]; then
        echo "cn"
    elif [ -f ${rootPath}/data/is_china.pl ]; then
        local is_cn=$(cat ${rootPath}/data/is_china.pl)
        if [ "$is_cn" == "True" ]; then
            echo "cn"
        else
            echo "common"
        fi
    else
        echo "common"
    fi
}

function get_cpu_cores() {
    local cores="1"
    if [ -f /proc/cpuinfo ]; then
        cores=$(cat /proc/cpuinfo | grep "processor" | wc -l)
    fi

    if [ -x "$(command -v free)" ]; then
        local mem=$(LC_ALL=C free -m | grep Mem | awk '{printf("%.f",($2)/1024)}')
        if [ "$cores" -gt "$mem" ] && [ "$mem" -gt 0 ]; then
            cores=$mem
        fi
    fi

    if [ "$cores" -gt "2" ]; then
        cores=$(echo "$cores" | awk '{printf("%.f",($1)*0.8)}')
    else
        cores="1"
    fi
    echo $cores
}

# Usage: yf_download <file_path> <url> [timeout]
#
# TLS 口径（报告 P1-3）：默认**开启证书校验**。只有显式设置环境变量
# `YF_INSECURE_DOWNLOAD=1` 时才放宽，且由 github_download.sh 里的
# `yf_wget_tls_extra_args` 统一追加参数并向 stderr 打 `[WARN]` 告警。
# 本函数**没有**「校验失败后自动降级重试」的兜底。
function yf_download() {
    local file=$1
    local url=$2
    local timeout=${3:-30}

    if [ -f "$file" ]; then
        # 验证文件有效性（判断是否被劫持为 HTML 或 0 字节，若是则删除重下）
        if type _gh_verify_file >/dev/null 2>&1; then
            if _gh_verify_file "$file"; then
                return 0
            else
                echo "检测到无效的缓存文件（如网络劫持的 HTML 页面或损坏文件），准备清理并重新下载: $file"
                rm -f "$file" 2>/dev/null
            fi
        else
            local existing_size=$(wc -c < "$file" 2>/dev/null | tr -d ' ')
            if [ "$existing_size" -gt 0 ] 2>/dev/null; then
                if head -c 100 "$file" 2>/dev/null | grep -qiE '^\s*(<html|<!DOCTYPE html)'; then
                    echo "检测到缓存文件为 HTML 报错/认证页面，准备清理并重新下载: $file"
                    rm -f "$file" 2>/dev/null
                else
                    return 0
                fi
            fi
        fi
    fi

    # GitHub URL 委托给统一函数处理
    if [[ $url == https://github.com* ]] || [[ $url == https://api.github.com* ]] || [[ $url == https://raw.githubusercontent.com* ]]; then
        if ! type github_download >/dev/null 2>&1; then
            local _gh_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)/github_download.sh"
            if [ -f "$_gh_lib" ]; then
                source "$_gh_lib"
            fi
        fi
        if type github_download >/dev/null 2>&1; then
            github_download "$file" "$url" "$timeout"
            return $?
        fi
    fi

    # 非 GitHub URL（如 OpenResty 官方镜像等）
    local addr=$(get_local_addr)
    if [ "$addr" == "cn" ]; then
        # OpenResty Mirror
        if [[ $url == https://openresty.org/download/* ]]; then
            local filename=$(basename $url)
            local proxy_url="https://mirrors.ustc.edu.cn/openresty/download/$filename"
            echo "Downloading from mirror: $proxy_url"
            wget $(yf_wget_tls_extra_args "$proxy_url") -O $file --tries=3 --timeout=$timeout $proxy_url
        fi
    fi

    if [ ! -f $file ]; then
        echo "Downloading from original: $url"
        wget $(yf_wget_tls_extra_args "$url") -O $file --tries=3 --timeout=$timeout $url
    fi
}

# --------------------------------------------------------------------------- #
# 下载后完整性校验（报告 P1-3）
#
# 背景：以前所有 shell 侧下载都是「下完就用」，只有文件大小 / 是否为 HTML 报错页
# 这类弱校验（见 github_download.sh::_gh_verify_file）。这类检查挡不住精心构造的
# 中间人替换包。这里提供一个**可复用**的 sha256 入口，由调用方传入期望值。
#
# 为什么只提供机制、不给每个组件预置哈希：哈希必须来自可信发布方（官方 release
# 页 / 仓库里已有的常量）；凭空编一个值比不校验更糟（会让安装永远失败或让人去
# 删掉校验）。所以这里只做「你给期望值，我负责 fail-closed」。
# --------------------------------------------------------------------------- #

# 计算文件 sha256（优先 sha256sum，退化 shasum / openssl，覆盖精简系统与 macOS）
# 用法: yf_sha256_of_file <file>
# 返回: 0 并打印 64 位小写十六进制；文件不存在或三种工具都算不出来 → 1
function yf_sha256_of_file() {
    local _f=$1
    local _h=""
    if [ ! -f "$_f" ]; then
        return 1
    fi
    if command -v sha256sum >/dev/null 2>&1; then
        _h=$(sha256sum "$_f" 2>/dev/null | awk '{print $1}')
    elif command -v shasum >/dev/null 2>&1; then
        _h=$(shasum -a 256 "$_f" 2>/dev/null | awk '{print $1}')
    elif command -v openssl >/dev/null 2>&1; then
        _h=$(openssl dgst -sha256 "$_f" 2>/dev/null | awk '{print $NF}')
    fi
    if [ -z "$_h" ]; then
        return 1
    fi
    echo "$_h"
}

# 用法: yf_download_sha256 <file> <url> <expected_sha256> [timeout]
#
# 语义（fail-closed）：下载 → 算 sha256 → 与期望值逐字符比对。
#   * 期望值为空  -> 直接拒绝下载并返回 1（防「传空串等于跳过校验」的漏网）；
#   * 文件下不下来、或算不出哈希 -> 删包并返回 1；
#   * 不匹配       -> 删包并返回 1。
# 调用方**必须**检查返回值，不要用 `|| true` 吞掉。
# 镜像/代理/GitHub 加速仍由 yf_download 负责，本函数只管完整性。
function yf_download_sha256() {
    local file=$1
    local url=$2
    local expected=$3
    local timeout=${4:-60}
    local actual=""

    if [ -z "$expected" ]; then
        echo "[ERROR] yf_download_sha256: 期望 sha256 为空，拒绝下载（fail-closed）: $url" >&2
        return 1
    fi

    if ! yf_download "$file" "$url" "$timeout"; then
        echo "[ERROR] 下载失败: $url" >&2
        rm -f "$file" 2>/dev/null
        return 1
    fi

    actual=$(yf_sha256_of_file "$file") || actual=""
    if [ -z "$actual" ]; then
        echo "[ERROR] sha256 无法计算（缺少 sha256sum/shasum/openssl 或文件不存在），已删包并拒绝使用: $file" >&2
        rm -f "$file" 2>/dev/null
        return 1
    fi
    if [ "$actual" != "$expected" ]; then
        echo "[ERROR] sha256 校验不匹配，已删包并拒绝使用: $file" >&2
        echo "[ERROR]   期望: $expected" >&2
        echo "[ERROR]   实际: $actual" >&2
        rm -f "$file" 2>/dev/null
        return 1
    fi
    echo "[OK] sha256 校验通过: $file"
    return 0
}

# --- Common Helpers End ---


HTTP_PREFIX="https://"
LOCAL_ADDR=$(get_local_addr)

PIPSRC="https://pypi.python.org/simple"
if [ "$LOCAL_ADDR" != "common" ];then
    PIPSRC="https://pypi.tuna.tsinghua.edu.cn/simple"
fi

echo "local:${LOCAL_ADDR}"
echo "pypi source:$PIPSRC"

# 移除全局安装 pip3 的逻辑（遵循 PEP 668，避免破坏宿主机环境）

if [ ! -f /www/server/yufeng_panel/bin/activate ];then
    echo "正在创建独立的 Python 虚拟环境..."
    cd /www/server/yufeng_panel || exit 1
    
    # 尝试标准创建 (自带 pip)
    if ! python3 -m venv .; then
        echo "标准 venv 创建失败(可能缺少 ensurepip)，尝试 --without-pip 回退模式..."
        python3 -m venv --without-pip .
        
        # 激活没有 pip 的虚拟环境
        source /www/server/yufeng_panel/bin/activate
        
        echo "正在为虚拟环境独立下载安装 pip..."
        curl -fsSL -m 15 -o get-pip.py https://bootstrap.pypa.io/get-pip.py || wget -qO get-pip.py --timeout=15 https://bootstrap.pypa.io/get-pip.py
        python3 get-pip.py -i $PIPSRC
        rm -f get-pip.py
    fi
fi

# 确保虚拟环境被正确激活
if [ -f /www/server/yufeng_panel/bin/activate ]; then
    source /www/server/yufeng_panel/bin/activate
else
    echo "Error: 虚拟环境激活脚本不存在，环境初始化失败！"
    exit 1
fi

pip3 install --upgrade pip -i $PIPSRC
pip3 install --upgrade setuptools wheel -i $PIPSRC


# 安装 requirements.txt 中的依赖项
#
# 两个源都失败时必须 exit 1（报告 P1-6）：本脚本刻意不开 `set -e`（中间有大量
# 「允许失败」的探测命令，如 `cat /etc/*-release`、`bash getos.sh`、brew 安装），
# 但依赖装不上就必须让退出码非 0，否则调用方（scripts/install/*.sh）会把
# 「依赖缺失、面板起不来」当成安装成功。
if [ "$LOCAL_ADDR" != "common" ]; then
    echo "正在使用国内加速源安装 Python 依赖..."
    if ! cd /www/server/yufeng_panel || ! pip3 install -r /www/server/yufeng_panel/requirements.txt -i $PIPSRC; then
        echo "警告: 加速源安装失败，正在尝试使用官方源..."
        if ! pip3 install -r /www/server/yufeng_panel/requirements.txt; then
            echo "错误: Python 依赖安装失败（加速源与官方源均失败），中止安装！"
            exit 1
        fi
    fi
else
    echo "正在使用官方源安装 Python 依赖..."
    if ! cd /www/server/yufeng_panel || ! pip3 install -r /www/server/yufeng_panel/requirements.txt; then
        echo "警告: 官方源安装失败，正在尝试使用国内加速源..."
        if ! pip3 install -r /www/server/yufeng_panel/requirements.txt -i $PIPSRC; then
            echo "错误: Python 依赖安装失败（官方源与加速源均失败），中止安装！"
            exit 1
        fi
    fi
fi

# 强制升级 requests 库以自动修复可能由 urllib3/charset-normalizer 升级引起的版本冲突警告
pip3 install --upgrade requests -i $PIPSRC


# Different versions use different python lib
P_VER_D=`echo "$P_VER"|awk -F '.' '{print $1}'`
P_VER_M=`echo "$P_VER"|awk -F '.' '{print $2}'`
NEW_P_VER=${P_VER_D}.${P_VER_M}

if [ -f /www/server/yufeng_panel/version/r${NEW_P_VER}.txt ];then
    echo "cd /www/server/yufeng_panel && pip3 install -r /www/server/yufeng_panel/version/r${NEW_P_VER}.txt"
    # 版本专属依赖（老 Python 的锁版本）装不上同样必须中止，理由同上
    if ! cd /www/server/yufeng_panel || ! pip3 install -r /www/server/yufeng_panel/version/r${NEW_P_VER}.txt -i $PIPSRC; then
        echo "错误: 版本专属依赖 (version/r${NEW_P_VER}.txt) 安装失败，中止安装！"
        exit 1
    fi
fi

echo "lib ok!"
# 保留旧版命名，向下兼容第三方或未更新的旧脚本
function mw_download() {
    yf_download "$@"
}
