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
    "https://gh-proxy.com/"
    "https://cors.zme.ink/"
    "https://gh.ddlc.top/"
    "https://ghproxy.net/"
)

# ---------- 内部辅助函数 ----------

# 探针单例全局缓存 (供所有子脚本共享加速)
if [ -z "$_GH_BEST_PROXY" ]; then
    export _GH_BEST_PROXY=""
fi

# 全局缓存 GitHub 直连状态: "ok" (通畅), "fail" (阻断), "" (未测)
if [ -z "$_GH_DIRECT_STATE" ]; then
    export _GH_DIRECT_STATE=""
fi

# 快速检测 GitHub 直连连通性 (5秒超时)
_gh_check_direct() {
    if [ "$_GH_DIRECT_STATE" == "ok" ]; then return 0; fi
    if [ "$_GH_DIRECT_STATE" == "fail" ]; then return 1; fi
    
    # 快速探测 GitHub 主站，限制 5 秒超时
    if LC_ALL=C curl -s -m 5 -o /dev/null "https://github.com" 2>/dev/null; then
        export _GH_DIRECT_STATE="ok"
        return 0
    else
        export _GH_DIRECT_STATE="fail"
        return 1
    fi
}

# 获取最佳代理节点 (测速后取带宽最大的节点)
_gh_get_best_proxy() {
    if [ -n "$_GH_BEST_PROXY" ]; then
        echo "$_GH_BEST_PROXY"
        return 0
    fi
    
    echo -e "正在测速寻找带宽最大的 GitHub 加速节点..." >&2
    local best_proxy=""
    local max_speed=0
    
    for proxy in "${_GH_PROXY_LIST[@]}"; do
        echo -n "  - 正在测速节点: $proxy ... " >&2
        # 使用真实的 release 压缩包进行测速
        local test_url="${proxy}https://github.com/clhome/bt_simple/archive/refs/heads/master.tar.gz"
        
        # 增加 -L (跟随重定向) 和 %{speed_download} (提取速度字节/秒)，严格限制 5 秒超时，不落盘。
        # 设定 LC_ALL=C 避免某些语种环境小数点变成逗号导致截断报错
        local result=$(LC_ALL=C curl -s -L -o /dev/null -w "%{http_code}:%{speed_download}" -m 5 "$test_url" 2>/dev/null)
        
        local status=$(echo "$result" | cut -d: -f1)
        local speed=$(echo "$result" | cut -d: -f2)
        
        if [ -z "$status" ]; then status="000"; fi
        if [ -z "$speed" ]; then speed="0"; fi
        
        # 重定向后一般是 200 状态码
        if [[ "$status" == "200" || "$status" == "206" ]]; then
            # 把速度转为 MB/s，保留两位小数
            local speed_mbps=$(awk -v s="$speed" 'BEGIN{printf "%.2f", s/1024/1024}')
            echo -e "\033[32m[存活, 速度: ${speed_mbps} MB/s]\033[0m" >&2
            
            # 利用 awk 比较，选出速度最大(max_speed)的节点
            if awk -v s1="$speed" -v s2="$max_speed" 'BEGIN{if(s1>s2) exit 0; else exit 1}'; then
                max_speed=$speed
                best_proxy=$proxy
            fi
        else
            echo -e "\033[31m[不可用或响应错]\033[0m" >&2
        fi
    done
    
    if [ -n "$best_proxy" ]; then
        export _GH_BEST_PROXY="$best_proxy"
        local final_speed_mbps=$(awk -v s="$max_speed" 'BEGIN{printf "%.2f", s/1024/1024}')
        echo -e "选用下载最快的 GitHub 代理: \033[32m$best_proxy\033[0m (速度: ${final_speed_mbps} MB/s)" >&2
        echo "$_GH_BEST_PROXY"
        return 0
    fi
    
    echo -e "✗ 所有 GitHub 代理节点均探测失败，本次将使用 GitHub 官方直连" >&2
    return 1
}

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

    local ret=0
    # 使用 timeout 命令包裹 git clone
    if command -v timeout >/dev/null 2>&1; then
        timeout "$timeout" git clone --depth 1 ${branch:+-b "$branch"} "$repo_url" "$target_dir" >/dev/null 2>&1
        ret=$?
    else
        # 没有 timeout 命令时，使用 git 自带的 http.lowSpeedLimit 机制
        git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime="$timeout" clone --depth 1 ${branch:+-b "$branch"} "$repo_url" "$target_dir" >/dev/null 2>&1
        ret=$?
    fi

    # 恢复信号捕获
    trap - INT TERM HUP

    # 严密验证：退出码必须是 0 并且目录完整
    if [ $ret -eq 0 ] && [ -d "$target_dir" ] && [ -d "$target_dir/.git" ]; then
        return 0
    fi

    # 强制清理被强杀或断流遗留的“半成品脏目录”
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
    if _gh_check_direct; then
        echo "[github_download] 尝试直连 GitHub (${timeout}s)..."
        if _gh_try_download "$file" "$url" "$timeout"; then
            echo "[github_download] ✓ 直连成功"
            return 0
        fi
        echo "[github_download] ✗ 直连失败，标记直连不可用，准备使用代理加速节点..."
        export _GH_DIRECT_STATE="fail"
    else
        echo "[github_download] ⚠ GitHub 直连不通，跳过直连死等，直接使用代理加速..."
    fi

    # 步骤2: 极速探测获取缓存节点，避免盲目轮询
    _gh_get_best_proxy >/dev/null
    local best_proxy="$_GH_BEST_PROXY"
    if [ -n "$best_proxy" ]; then
        local proxy_url=$(_gh_proxy_url "$best_proxy" "$url")
        echo "[github_download] 命中最佳加速代理: ${best_proxy}"
        echo "[github_download] 正在尝试通过代理下载 (${timeout}s)..."
        if _gh_try_download "$file" "$proxy_url" "$timeout"; then
            echo "[github_download] ✓ 代理下载成功: $best_proxy"
            return 0
        else
            echo "[github_download] ✗ 代理连接成功但下载失败，可能是资源不存在或网络抖动"
        fi
    else
        echo "[github_download] ✗ 代理探针测速失败，所有备选代理均无快速响应！"
    fi

    # 步骤3: 如果极速代理方案也失败了，走最终的备选降级轮询机制
    echo "[github_download] === 进入最终降级轮询机制 ==="
    for proxy in "${_GH_PROXY_LIST[@]}"; do
        if [ "$proxy" == "$best_proxy" ]; then continue; fi
        local proxy_url=$(_gh_proxy_url "$proxy" "$url")
        echo "[github_download] 尝试备选代理: ${proxy} (${timeout}s)..."
        if _gh_try_download "$file" "$proxy_url" "$timeout"; then
            echo "[github_download] ✓ 降级轮询代理下载成功: $proxy"
            return 0
        fi
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
    local timeout=${4:-90}

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
    if _gh_check_direct; then
        echo "[github_clone] 尝试直连 GitHub (${timeout}s)..."
        if _gh_try_clone "$target_dir" "$repo_url" "$branch" "$timeout"; then
            echo "[github_clone] ✓ 直连克隆成功"
            return 0
        fi
        echo "[github_clone] ✗ 直连失败，标记直连不可用，准备使用代理加速节点..."
        export _GH_DIRECT_STATE="fail"
    else
        echo "[github_clone] ⚠ GitHub 直连不通，跳过直连死等，直接使用代理加速..."
    fi

    # 步骤2: 极速获取缓存最佳代理
    _gh_get_best_proxy >/dev/null
    local best_proxy="$_GH_BEST_PROXY"
    if [ -n "$best_proxy" ]; then
        local proxy_repo_url=$(_gh_proxy_url "$best_proxy" "$repo_url")
        echo "[github_clone] 命中最佳加速代理: ${best_proxy}"
        echo "[github_clone] 正在尝试通过代理克隆 (${timeout}s)..."
        if _gh_try_clone "$target_dir" "$proxy_repo_url" "$branch" "$timeout"; then
            echo "[github_clone] ✓ 代理克隆成功: $best_proxy"
            return 0
        fi
    fi

    # 步骤3: 如果最佳节点下载失败，再走最终轮询降级
    echo "[github_clone] === 进入最终降级轮询机制 ==="
    for proxy in "${_GH_PROXY_LIST[@]}"; do
        if [ "$proxy" == "$best_proxy" ]; then continue; fi
        local proxy_repo_url=$(_gh_proxy_url "$proxy" "$repo_url")
        echo "[github_clone] 尝试备选代理: ${proxy} (${timeout}s)..."
        if _gh_try_clone "$target_dir" "$proxy_repo_url" "$branch" "$timeout"; then
            echo "[github_clone] ✓ 降级轮询克隆成功: $proxy"
            return 0
        fi
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
    if _gh_check_direct; then
        result=$(curl -s -m "$timeout" "$url" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$result" ]; then
            echo "$result"
            return 0
        fi
        export _GH_DIRECT_STATE="fail"
    fi

    # 步骤2: 读取最佳缓存节点
    _gh_get_best_proxy >/dev/null
    local best_proxy="$_GH_BEST_PROXY"
    if [ -n "$best_proxy" ]; then
        local proxy_url=$(_gh_proxy_url "$best_proxy" "$url")
        result=$(curl -s -m "$timeout" "$proxy_url" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$result" ]; then
            echo "$result"
            return 0
        fi
    fi

    # 步骤3: 降级轮询
    for proxy in "${_GH_PROXY_LIST[@]}"; do
        if [ "$proxy" == "$best_proxy" ]; then continue; fi
        local proxy_url=$(_gh_proxy_url "$proxy" "$url")
        result=$(curl -s -m "$timeout" "$proxy_url" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$result" ]; then
            echo "$result"
            return 0
        fi
    done

    echo "[github_api_get] ✗ 所有 API 请求方式均失败: $url" >&2
    return 1
}
