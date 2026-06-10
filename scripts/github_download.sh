#!/bin/bash
# =========================================================================
# GitHub 统一下载函数库
# =========================================================================
# 提供 github_download 和 github_clone 两个函数，统一处理：
#   1. 直连 GitHub（等待 10 秒）
#   2. 若失败，轮询代理站列表（每个 10 秒）
#   3. 若全部失败，等待 10 秒后再次完整轮询（最多 2 次）
#   4. 若仍失败，返回错误码 1
#
# 用法（在其他脚本中 source 本文件后调用）:
#   source /path/to/github_download.sh
#   github_download <保存路径> <GitHub原始URL> [单次超时秒数]
#   github_clone   <目标目录> <GitHub仓库URL> [分支]
# =========================================================================

# ---------- 代理站列表 ----------
# 与 scripts/install.sh 和 web/core/mw.py 保持一致
_GH_PROXY_LIST=(
    "https://ghproxy.net/"
    "https://gh.con.sh/"
    "https://gh-proxy.com/"
    "https://cors.zme.ink/"
)

# ---------- 内部辅助函数 ----------

# 将原始 GitHub URL 加上代理前缀
# 用法: _gh_proxy_url <proxy_prefix> <original_url>
# 例如: _gh_proxy_url "https://ghfast.top/" "https://github.com/foo/bar.tar.gz"
#   => "https://ghfast.top/https://github.com/foo/bar.tar.gz"
# 注意: 部分代理前缀自带 "https://"（如 ghp.ci），需要去重
_gh_proxy_url() {
    local prefix=$1
    local url=$2

    # 如果代理前缀已经以 "https://" 结尾，原始 URL 需要去掉 "https://"
    if [[ "$prefix" == *"https://" ]]; then
        echo "${prefix}${url#https://}"
    else
        echo "${prefix}${url}"
    fi
}

# 验证下载的文件是否有效（防代理返回HTML错误页）
# 用法: _gh_verify_file <文件路径>
# 返回: 0=有效 1=无效
_gh_verify_file() {
    local file=$1
    if [ ! -f "$file" ]; then return 1; fi
    local size=$(wc -c < "$file" 2>/dev/null | tr -d ' ')
    if [ "$size" -eq 0 ] 2>/dev/null; then return 1; fi

    # 如果是 gzip 压缩包
    if [[ "$file" == *.tar.gz ]] || [[ "$file" == *.tgz ]] || [[ "$file" == *.gz ]]; then
        if gzip -t "$file" 2>/dev/null; then return 0; else return 1; fi
    fi
    # 如果是 zip 压缩包
    if [[ "$file" == *.zip ]]; then
        if unzip -t "$file" >/dev/null 2>&1; then return 0; else return 1; fi
    fi
    
    # 针对普通文件（如 .sh 或二进制），检测是否被代理篡改为 HTML 错误页
    # 简单检查文件头部是否为明显的 HTML 标签
    if head -c 100 "$file" 2>/dev/null | grep -qiE '^\s*(<html|<!DOCTYPE html)'; then
        return 1
    fi

    return 0
}

# 尝试使用 wget 下载文件
# 用法: _gh_try_download <保存路径> <完整URL> <超时秒数>
# 返回: 0=成功 1=失败
_gh_try_download() {
    local file=$1
    local url=$2
    local timeout=$3

    # 先删除可能存在的空文件/残留文件
    rm -f "$file" 2>/dev/null

    wget --no-check-certificate -O "$file" --timeout="$timeout" --tries=1 -q "$url" 2>/dev/null

    # 校验: 文件必须有效
    if _gh_verify_file "$file"; then
        return 0
    fi

    rm -f "$file" 2>/dev/null
    return 1
}

# 尝试使用 git clone
# 用法: _gh_try_clone <目标目录> <仓库URL> <分支> <超时秒数>
# 返回: 0=成功 1=失败
_gh_try_clone() {
    local target_dir=$1
    local repo_url=$2
    local branch=$3
    local timeout=$4

    rm -rf "$target_dir" 2>/dev/null

    # 捕获用户中断信号，确保中断时删除下载了一半的目录
    trap 'rm -rf "$target_dir" 2>/dev/null; exit 1' INT TERM HUP

    # 使用 timeout 命令包裹 git clone
    if command -v timeout >/dev/null 2>&1; then
        timeout "$timeout" git clone --depth 1 ${branch:+-b "$branch"} "$repo_url" "$target_dir" >/dev/null 2>&1
    else
        # 没有 timeout 命令时，使用 git 自带的 http.lowSpeedLimit 机制
        git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime="$timeout" clone --depth 1 ${branch:+-b "$branch"} "$repo_url" "$target_dir" >/dev/null 2>&1
    fi

    # 恢复信号捕获
    trap - INT TERM HUP

    if [ -d "$target_dir" ] && [ -d "$target_dir/.git" ]; then
        return 0
    fi

    rm -rf "$target_dir" 2>/dev/null
    return 1
}


# ---------- 公开函数 ----------

# github_download - 统一的 GitHub 文件下载函数
#
# 用法: github_download <保存路径> <GitHub原始URL> [单次超时秒数=10]
# 返回: 0=成功 1=全部失败
#
# 流程:
#   1. 直连 GitHub（等待 timeout 秒）
#   2. 失败则轮询代理站列表（每个 timeout 秒）
#   3. 全部失败则等待 10 秒后再次完整代理轮询（最多 2 次）
#   4. 仍失败则返回 1
github_download() {
    local file=$1
    local url=$2
    local timeout=${3:-60}

    if [ -z "$file" ] || [ -z "$url" ]; then
        echo "[github_download] 错误: 缺少参数。用法: github_download <保存路径> <URL> [超时秒数]"
        return 1
    fi

    # 如果文件已存在，校验其有效性；若无效则删除
    if [ -f "$file" ]; then
        if _gh_verify_file "$file"; then
            echo "[github_download] 文件已存在且完整，跳过: $file"
            return 0
        else
            echo "[github_download] 文件已存在但可能已损坏，正在清理以重新下载: $file"
            rm -f "$file" 2>/dev/null
        fi
    fi

    echo "[github_download] 开始下载: $url"
    echo "[github_download] 保存路径: $file"

    # 步骤1: 直连 GitHub
    echo "[github_download] 尝试直连 GitHub (${timeout}s)..."
    if _gh_try_download "$file" "$url" "$timeout"; then
        echo "[github_download] ✓ 直连成功"
        return 0
    fi
    echo "[github_download] ✗ 直连失败，开始代理轮询..."

    # 步骤2+3: 代理轮询，最多 2 轮
    local round
    for round in 1 2; do
        if [ "$round" -gt 1 ]; then
            echo "[github_download] 等待 10 秒后进行第 ${round} 轮代理轮询..."
            sleep 10
        fi

        echo "[github_download] === 第 ${round} 轮代理轮询 ==="

        local proxy
        for proxy in "${_GH_PROXY_LIST[@]}"; do
            local proxy_url=$(_gh_proxy_url "$proxy" "$url")
            echo "[github_download] 尝试代理: ${proxy} (${timeout}s)..."

            if _gh_try_download "$file" "$proxy_url" "$timeout"; then
                echo "[github_download] ✓ 代理下载成功: $proxy"
                return 0
            fi
            echo "[github_download] ✗ 代理失败: $proxy"
        done
    done

    # 步骤4: 全部失败
    echo "[github_download] ✗✗✗ 错误: 所有下载方式均失败！"
    echo "[github_download] URL: $url"
    echo "[github_download] 请检查网络连接或手动下载文件到: $file"
    return 1
}


# github_clone - 统一的 GitHub 仓库克隆函数
#
# 用法: github_clone <目标目录> <GitHub仓库URL> [分支]
# 返回: 0=成功 1=全部失败
#
# 流程与 github_download 相同：直连 → 代理轮询 → 重试
github_clone() {
    local target_dir=$1
    local repo_url=$2
    local branch=${3:-""}
    local timeout=30

    if [ -z "$target_dir" ] || [ -z "$repo_url" ]; then
        echo "[github_clone] 错误: 缺少参数。用法: github_clone <目标目录> <仓库URL> [分支]"
        return 1
    fi

    # 如果目标目录已存在且包含 .git，跳过
    if [ -d "$target_dir" ] && [ -d "$target_dir/.git" ]; then
        echo "[github_clone] 仓库已存在，跳过: $target_dir"
        return 0
    fi

    echo "[github_clone] 开始克隆: $repo_url"
    echo "[github_clone] 目标目录: $target_dir"

    # 步骤1: 直连
    echo "[github_clone] 尝试直连 GitHub (${timeout}s)..."
    if _gh_try_clone "$target_dir" "$repo_url" "$branch" "$timeout"; then
        echo "[github_clone] ✓ 直连克隆成功"
        return 0
    fi
    echo "[github_clone] ✗ 直连失败，开始代理轮询..."

    # 步骤2+3: 代理轮询，最多 2 轮
    local round
    for round in 1 2; do
        if [ "$round" -gt 1 ]; then
            echo "[github_clone] 等待 10 秒后进行第 ${round} 轮代理轮询..."
            sleep 10
        fi

        echo "[github_clone] === 第 ${round} 轮代理轮询 ==="

        local proxy
        for proxy in "${_GH_PROXY_LIST[@]}"; do
            local proxy_repo_url=$(_gh_proxy_url "$proxy" "$repo_url")
            echo "[github_clone] 尝试代理: ${proxy} (${timeout}s)..."

            if _gh_try_clone "$target_dir" "$proxy_repo_url" "$branch" "$timeout"; then
                echo "[github_clone] ✓ 代理克隆成功: $proxy"
                return 0
            fi
            echo "[github_clone] ✗ 代理失败: $proxy"
        done
    done

    # 全部失败
    echo "[github_clone] ✗✗✗ 错误: 所有克隆方式均失败！"
    echo "[github_clone] URL: $repo_url"
    echo "[github_clone] 请检查网络连接或手动克隆仓库到: $target_dir"
    return 1
}


# github_api_get - 统一的 GitHub API GET 请求函数
#
# 用法: github_api_get <API URL>
# 输出: API 响应内容（stdout）
# 返回: 0=成功 1=全部失败
#
# 例如: github_api_get "https://api.github.com/repos/P3TERX/GeoLite.mmdb/releases/latest"
github_api_get() {
    local url=$1
    local timeout=10

    if [ -z "$url" ]; then
        echo "[github_api_get] 错误: 缺少参数" >&2
        return 1
    fi

    # 步骤1: 直连
    local result
    result=$(curl -s -m "$timeout" "$url" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$result" ]; then
        echo "$result"
        return 0
    fi

    # 步骤2+3: 代理轮询（API 请求也可以通过代理）
    local round
    for round in 1 2; do
        if [ "$round" -gt 1 ]; then
            sleep 10
        fi

        local proxy
        for proxy in "${_GH_PROXY_LIST[@]}"; do
            local proxy_url=$(_gh_proxy_url "$proxy" "$url")
            result=$(curl -s -m "$timeout" "$proxy_url" 2>/dev/null)
            if [ $? -eq 0 ] && [ -n "$result" ]; then
                echo "$result"
                return 0
            fi
        done
    done

    echo "[github_api_get] ✗ 所有 API 请求方式均失败: $url" >&2
    return 1
}
