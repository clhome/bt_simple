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
# 单一真源：scripts/proxies.list（取作用域 rt / both，保持文件中的顺序）。
# 首位为空串表示官方直连，使直连也能参与测速并默认优先。
# 清单文件由发布包/仓库提供；万一缺失则退化为「仅官方直连」——
# 绝不因为读不到清单而卡死安装（testsuite/test_deploy_bootstrap.py::test_04 有守卫）。
_GH_PROXY_LIST=()
_yf_proxy_list_file="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/proxies.list"
if [ -f "$_yf_proxy_list_file" ]; then
    while IFS='|' read -r _yf_p_name _yf_p_url _yf_p_scope; do
        case "$_yf_p_name" in
            ''|'#'*) continue ;;
        esac
        case "$_yf_p_scope" in
            rt|both) _GH_PROXY_LIST+=("$_yf_p_url") ;;
        esac
    done < "$_yf_proxy_list_file"
fi
if [ "${#_GH_PROXY_LIST[@]}" -eq 0 ]; then
    _GH_PROXY_LIST=("")
fi

# ---------- 内部辅助函数 ----------

# 探针单例全局缓存 (供所有子脚本共享加速)
if [ -z "$_GH_BEST_PROXY" ]; then
    export _GH_BEST_PROXY=""
fi

# 全局缓存 GitHub 直连状态: "ok" (通畅), "fail" (阻断), "" (未测)
if [ -z "$_GH_DIRECT_STATE" ]; then
    export _GH_DIRECT_STATE=""
fi

# 全局缓存测速中确认存活与失败的节点列表
_GH_ALIVE_PROXIES=()
_GH_FAILED_PROXIES=()

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

# ---------- 测速探针（2026-11-27 改造） ----------
#
# 历史写法：探针直接用面板仓库的整仓归档
#   https://github.com/<panel>/archive/refs/heads/master.tar.gz  +  curl -m 5
# 三个问题（真机实测）：
#   1. 每个节点都会白下最多 5 秒的数据。1.6MB/s 的机器 ≈ 8MB/节点，9 个节点 ≈ 70MB，
#      全部丢弃（-o /dev/null），运维在日志里会误以为「在下载面板包」；
#   2. 该 URL 由 GitHub **现场打包**（codeload 动态生成 tar.gz），既慢又计入归档限流，
#      测出来的"最快节点"与真正下载的 release 资产不是同一条链路；
#   3. 结果只活在进程环境变量里，每个安装任务都要重测一遍。
#
# 现在改为：
#   * 探针 = 面板 release 下的**固定资产** + HTTP Range 只取前 512KB（≤512KB/节点，
#     且完全不再让 GitHub 现场打包）；
#   * 官方直连先单独测，达到阈值就直接用（不再扫代理）；
#   * 结果落盘缓存 30 分钟（跨安装任务复用）；
#   * 其余代理**并行**探测（各写临时文件，再按列表顺序汇总，tie-break 与旧实现一致）。
#
# 全部参数可用 YF_GH_* 环境变量覆盖（内网镜像 / 排障时用）。
_GH_SPEED_TEST_URL="${YF_GH_SPEED_TEST_URL:-https://github.com/clhome/bt_simple/releases/download/v2.1.4/yf-panel-2.1.4.tar.gz}"
_GH_SPEED_TEST_RANGE="${YF_GH_SPEED_TEST_RANGE:-0-524287}"
_GH_SPEED_TIMEOUT="${YF_GH_SPEED_TIMEOUT:-4}"
_GH_SPEED_CACHE_FILE="${YF_GH_SPEED_CACHE:-${TMPDIR:-/tmp}/.yf_gh_proxy_speed}"
_GH_SPEED_CACHE_TTL="${YF_GH_SPEED_CACHE_TTL:-1800}"
_GH_SPEED_FAST_LIMIT="${YF_GH_SPEED_FAST_LIMIT:-3145728}"

# 探测单个节点：输出 "<http状态>|<速度字节/秒>|<实际字节数>"（不落盘）
_gh_speed_probe() {
    local prefix=$1
    local url
    url=$(_gh_proxy_url "$prefix" "$_GH_SPEED_TEST_URL")
    local out
    out=$(LC_ALL=C curl -s -L -o /dev/null \
        -w '%{http_code}|%{speed_download}|%{size_download}' \
        -r "$_GH_SPEED_TEST_RANGE" -m "$_GH_SPEED_TIMEOUT" "$url" 2>/dev/null)
    [ -n "$out" ] || out="000|0|0"
    echo "$out"
}

# 读磁盘缓存：TTL 内命中则输出节点前缀（"direct" 或代理 URL），未命中返回 1
_gh_speed_cache_load() {
    [ -f "$_GH_SPEED_CACHE_FILE" ] || return 1
    local ts=""
    local best=""
    local now=""
    IFS='|' read -r ts best < "$_GH_SPEED_CACHE_FILE" 2>/dev/null || return 1
    case "$ts" in ''|*[!0-9]*) return 1 ;; esac
    [ -n "$best" ] || return 1
    now=$(date +%s 2>/dev/null)
    case "$now" in ''|*[!0-9]*) return 1 ;; esac
    local age=$((now - ts))
    [ "$age" -ge 0 ] 2>/dev/null || return 1
    [ "$age" -le "$_GH_SPEED_CACHE_TTL" ] || return 1
    echo "$best"
}

# 写磁盘缓存（失败静默：缓存只是加速手段，绝不能影响安装）
_gh_speed_cache_save() {
    local now
    now=$(date +%s 2>/dev/null)
    case "$now" in ''|*[!0-9]*) return 0 ;; esac
    printf '%s|%s\n' "$now" "$1" > "$_GH_SPEED_CACHE_FILE" 2>/dev/null || true
}

# 记录一个节点的测速结果：打印 + 维护存活/失败表 + 选最优（结果存在全局变量里，
# 因为并行子 shell 收不到父进程的数组改动，汇总必须在父进程按顺序重放一遍）。
# 用法: _gh_speed_apply <proxy> <"status|speed|size">
_gh_speed_apply() {
    local proxy=$1
    local result=$2
    local show_name=$proxy
    if [ -z "$show_name" ]; then
        show_name="官方直连"
    fi
    local status=${result%%|*}
    local rest=${result#*|}
    local speed=${rest%%|*}
    case "$status" in ''|*[!0-9]*) status="000" ;; esac
    case "$speed" in ''|*[!0-9.]*) speed="0" ;; esac

    if [ "$status" = "200" ] || [ "$status" = "206" ]; then
        _GH_ALIVE_PROXIES+=("$proxy")
        local speed_mbps
        speed_mbps=$(awk -v s="$speed" 'BEGIN{printf "%.2f", s/1024/1024}')
        echo -e "  - 测速节点: ${show_name} ... \033[32m[存活, 速度: ${speed_mbps} MB/s]\033[0m" >&2
        if awk -v s1="$speed" -v s2="$_GH_MAX_SPEED" 'BEGIN{if(s1>s2) exit 0; else exit 1}'; then
            _GH_MAX_SPEED=$speed
            if [ -z "$proxy" ]; then
                _GH_BEST_CANDIDATE="direct"
            else
                _GH_BEST_CANDIDATE=$proxy
            fi
        fi
    else
        _GH_FAILED_PROXIES+=("$proxy")
        echo -e "  - 测速节点: ${show_name} ... \033[31m[不可用或响应错]\033[0m" >&2
    fi
}

# 获取最佳代理节点（测速后取带宽最大的节点；直连达标则提前结束）
_gh_get_best_proxy() {
    if [ -n "$_GH_BEST_PROXY" ]; then
        echo "$_GH_BEST_PROXY"
        return 0
    fi

    # 1) 磁盘缓存：30 分钟内测过就直接复用（避免每个安装任务都重测一遍）
    local cached
    cached=$(_gh_speed_cache_load 2>/dev/null)
    if [ -n "$cached" ]; then
        export _GH_BEST_PROXY="$cached"
        echo -e "  - 复用 30 分钟内的测速结果: ${cached}" >&2
        echo "$_GH_BEST_PROXY"
        return 0
    fi

    echo -e "正在测速寻找最快的 GitHub 节点（单节点最长 ${_GH_SPEED_TIMEOUT}s，每节点最多 512KB）..." >&2
    _GH_MAX_SPEED=0
    _GH_BEST_CANDIDATE=""
    _GH_ALIVE_PROXIES=()
    _GH_FAILED_PROXIES=()

    # 2) 官方直连先单独测：快就直接收工，不扫代理
    if _gh_check_direct; then
        _gh_speed_apply "" "$(_gh_speed_probe "")"
        if awk -v s="$_GH_MAX_SPEED" -v limit="$_GH_SPEED_FAST_LIMIT" 'BEGIN{if(s>=limit) exit 0; else exit 1}'; then
            export _GH_BEST_PROXY="direct"
            _gh_speed_cache_save "direct"
            echo -e "  -> 官方直连已达 $(awk -v s="$_GH_MAX_SPEED" 'BEGIN{printf "%.2f", s/1024/1024}') MB/s，跳过代理轮询。" >&2
            echo "$_GH_BEST_PROXY"
            return 0
        fi
    else
        _GH_FAILED_PROXIES+=("")
        echo -e "  - 测速节点: 官方直连 ... \033[31m[不可达]\033[0m" >&2
    fi

    # 3) 其余代理并行探测
    local -a _plist=()
    local _p
    for _p in "${_GH_PROXY_LIST[@]}"; do
        [ -z "$_p" ] && continue
        _plist+=("$_p")
    done

    if [ "${#_plist[@]}" -gt 0 ]; then
        local _tmpdir=""
        _tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/.yf_gh_speed.XXXXXX" 2>/dev/null)
        if [ -n "$_tmpdir" ]; then
            local -a _pids=()
            local _i=0
            for _p in "${_plist[@]}"; do
                ( _gh_speed_probe "$_p" > "$_tmpdir/$_i" 2>/dev/null ) &
                _pids+=("$!")
                _i=$((_i + 1))
            done
            local _pid
            for _pid in "${_pids[@]}"; do
                wait "$_pid" 2>/dev/null
            done
            _i=0
            for _p in "${_plist[@]}"; do
                local _r="000|0|0"
                [ -f "$_tmpdir/$_i" ] && _r=$(cat "$_tmpdir/$_i" 2>/dev/null)
                [ -n "$_r" ] || _r="000|0|0"
                _gh_speed_apply "$_p" "$_r"
                _i=$((_i + 1))
            done
            rm -rf "$_tmpdir" 2>/dev/null
        else
            # 没有 mktemp 的极端环境：退回串行（探针已限流，成本仍远低于旧版）
            for _p in "${_plist[@]}"; do
                _gh_speed_apply "$_p" "$(_gh_speed_probe "$_p")"
            done
        fi
    fi

    if [ -n "$_GH_BEST_CANDIDATE" ]; then
        export _GH_BEST_PROXY="$_GH_BEST_CANDIDATE"
        _gh_speed_cache_save "$_GH_BEST_PROXY"
        local final_speed_mbps
        final_speed_mbps=$(awk -v s="$_GH_MAX_SPEED" 'BEGIN{printf "%.2f", s/1024/1024}')
        local show_best=$_GH_BEST_PROXY
        if [ "$show_best" = "direct" ]; then
            show_best="官方直连"
        fi
        echo -e "选用下载最快的 GitHub 节点: \033[32m$show_best\033[0m (速度: ${final_speed_mbps} MB/s)" >&2
        echo "$_GH_BEST_PROXY"
        return 0
    fi

    echo -e "✗ 所有 GitHub 节点均探测失败，本次将使用 GitHub 官方直连" >&2
    export _GH_BEST_PROXY="direct"
    echo "$_GH_BEST_PROXY"
    return 1
}

# 用法: yf_verify_archive <file>
#
# 判一个「刚下下来的压缩包」是不是**真的**压缩包 —— 按内容魔数，不看文件名后缀。
#
# 为什么必须有它（真机 2026-10-26，PHP 8.2/8.5 安装失败）：
#   * 下载校验曾经按文件名后缀决定要不要校验，而调用方常先下到 `xxx.tar.gz.part`
#     再改名 → 整个校验被跳过 → 代理返回的几十字节错误文本被当成「下载成功」；
#   * 插件脚本里大量 `wget -O x.tar.gz URL && tar -zxf x.tar.gz` 也不看退出码，
#     拿到 HTML 错误页后照样往下编译，最后报一堆与网络无关的错误。
# 口径：认识 gzip / zip / xz / bz2 / zstd / 7z 的魔数；认识就做一次真校验；
#       不认识且不像 HTML/错误文本时按「未知格式」放行（避免误伤 .tar 等无魔数包）。
function yf_verify_archive() {
    local _f=$1
    [ -f "$_f" ] || return 1
    local _size
    _size=$(wc -c < "$_f" 2>/dev/null | tr -d ' ')
    [ -n "$_size" ] && [ "$_size" -gt 0 ] 2>/dev/null || return 1

    local _clean="$(basename "$_f")"
    _clean="${_clean%.part}"
    _clean="${_clean%.tmp}"
    _clean="${_clean%.download}"

    local _magic
    _magic=$(head -c 6 "$_f" 2>/dev/null | od -An -tx1 2>/dev/null | tr -d ' \n')

    # 1. 已知魔数：必须通过对应压缩工具的真实完整性测试（工具缺失坚决不放行，P2-1）
    case "$_magic" in
        1f8b*)
            gzip -t "$_f" >/dev/null 2>&1 && return 0 || return 1
            ;;
        504b*)
            if command -v unzip >/dev/null 2>&1; then
                unzip -t "$_f" >/dev/null 2>&1 && return 0 || return 1
            fi
            echo "[verify][ERROR] 缺少 unzip 工具，拒绝放行未经验证的 zip 文件: $_f" >&2
            return 1
            ;;
        fd377a585a00*|fd377a58*)
            if command -v xz >/dev/null 2>&1; then
                xz -t "$_f" >/dev/null 2>&1 && return 0 || return 1
            fi
            echo "[verify][ERROR] 缺少 xz 工具，拒绝放行未经验证的 xz 文件: $_f" >&2
            return 1
            ;;
        425a68*)        # bz2
            if command -v bzip2 >/dev/null 2>&1; then
                bzip2 -t "$_f" >/dev/null 2>&1 && return 0 || return 1
            fi
            echo "[verify][ERROR] 缺少 bzip2 工具，拒绝放行未经验证的 bz2 文件: $_f" >&2
            return 1
            ;;
        28b52ffd*)      # zstd
            if command -v zstd >/dev/null 2>&1; then
                zstd -t "$_f" >/dev/null 2>&1 && return 0 || return 1
            fi
            echo "[verify][ERROR] 缺少 zstd 工具，拒绝放行未经验证的 zstd 文件: $_f" >&2
            return 1
            ;;
    esac

    # 2. 若文件名明确带有已知压缩扩展名，但魔数完全不匹配，绝不放行（防御伪装文本包）
    case "$_clean" in
        *.tar.gz|*.tgz|*.gz|*.tar.xz|*.xz|*.zip|*.tar.bz2|*.bz2|*.tar.zst|*.zst)
            return 1
            ;;
        *.tar)
            if command -v tar >/dev/null 2>&1; then
                tar -tf "$_f" >/dev/null 2>&1 && return 0 || return 1
            fi
            echo "[verify][ERROR] 缺少 tar 工具，拒绝放行未经验证的 tar 归档: $_f" >&2
            return 1
            ;;
    esac

    # 3. 没有已知魔数：绝对拒绝 HTML 错误页/认证页
    if head -c 1024 "$_f" 2>/dev/null | grep -qiE '^[[:space:]]*(<html|<!DOCTYPE html|<head|<body|<xml)'; then
        return 1
    fi

    # 4. 拒绝代理错误/停用提示/常见网关报错文本（放宽至 2048 字节全文扫描，防御长报错页，P2-1）
    if [ "$_size" -lt 65536 ] && head -c 2048 "$_f" 2>/dev/null | grep -qiE 'error|invalid|denied|blocked|forbidden|not found|abuse|suspend|suspent|report|rate limit|captcha|security|gateway|unavailable|bad request|timeout|请|错误|拦截|未找到|停止'; then
        return 1
    fi

    # 5. 小于 512 字节且非脚本魔数的纯 ASCII 文本，一律当代理异常文本拦截
    if [ "$_size" -lt 512 ]; then
        local _f2=$(head -c 2 "$_f" 2>/dev/null)
        if [ "$_f2" != "#!" ]; then
            if LC_ALL=C grep -qE '^[[:print:][:space:]]+$' "$_f" 2>/dev/null; then
                return 1
            fi
        fi
    fi

    return 0
}

# 用法: yf_fetch_archive <file> <url> [timeout]
#
# 下载 + 内容校验一体：校验不过就删掉并返回非 0（调用方负责 exit）。
# 与 `yf_download`（scripts/lib.sh）的区别：那个函数在部署脚本里，插件不能 source；
# 这里只依赖 `_gh_try_download`，自包含，插件可以直接 source 本文件使用。
function yf_fetch_archive() {
    local _f=$1
    local _url=$2
    local _to=${3:-300}
    if [ -f "$_f" ] && yf_verify_archive "$_f"; then
        return 0
    fi
    if [ -f "$_f" ]; then
        echo "[WARN] 本地已有文件无效（HTML 错误页/截断包），删除重下: $_f" >&2
        rm -f "$_f"
    fi
    if ! _gh_try_download "$_f" "$_url" "$_to"; then
        return 1
    fi
    if ! yf_verify_archive "$_f"; then
        rm -f "$_f"
        return 1
    fi
    return 0
}

# 该 URL 是否属于 GitHub（只有它们能被 GitHub 加速节点代理）
# 用法: _gh_is_github_url <url>
_gh_is_github_url() {
    case "$1" in
        https://github.com/*|https://objects.githubusercontent.com/*|        https://codeload.github.com/*|https://raw.githubusercontent.com/*|        https://gist.githubusercontent.com/*|https://release-assets.githubusercontent.com/*)
            return 0
            ;;
    esac
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

    # 如果是直连或者为空
    if [ "$prefix" = "direct" ] || [ -z "$prefix" ]; then
        echo "$url"
        return
    fi

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

    local magic=$(head -c 8 "$file" 2>/dev/null | od -An -tx1 2>/dev/null | tr -d ' \n')

    # 提取拟定文件名（去除 .part / .tmp / .download 等中间态后缀）
    local clean_name="$(basename "$file")"
    clean_name="${clean_name%.part}"
    clean_name="${clean_name%.tmp}"
    clean_name="${clean_name%.download}"

    # 1. 若目标文件名属于已知压缩包格式，必须符合对应格式且通过完整性检验，绝不放行伪装文件
    case "$clean_name" in
        *.tar.gz|*.tgz|*.gz)
            case "$magic" in
                1f8b*) gzip -t "$file" >/dev/null 2>&1 && return 0 || return 1 ;;
                *) return 1 ;;
            esac
            ;;
        *.tar.xz|*.xz)
            case "$magic" in
                fd377a58*)
                    if command -v xz >/dev/null 2>&1; then
                        xz -t "$file" >/dev/null 2>&1 && return 0 || return 1
                    fi
                    echo "[_gh_verify_file][ERROR] 缺少 xz 工具，拒绝放行未经验证的 xz 文件: $file" >&2
                    return 1
                    ;;
                *) return 1 ;;
            esac
            ;;
        *.zip)
            case "$magic" in
                504b0304*|504b0506*|504b0708*)
                    if command -v unzip >/dev/null 2>&1; then
                        unzip -t "$file" >/dev/null 2>&1 && return 0 || return 1
                    fi
                    echo "[_gh_verify_file][ERROR] 缺少 unzip 工具，拒绝放行未经验证的 zip 文件: $file" >&2
                    return 1
                    ;;
                *) return 1 ;;
            esac
            ;;
        *.tar.bz2|*.bz2)
            case "$magic" in
                425a68*)
                    if command -v bzip2 >/dev/null 2>&1; then
                        bzip2 -t "$file" >/dev/null 2>&1 && return 0 || return 1
                    fi
                    echo "[_gh_verify_file][ERROR] 缺少 bzip2 工具，拒绝放行未经验证的 bz2 文件: $file" >&2
                    return 1
                    ;;
                *) return 1 ;;
            esac
            ;;
        *.tar.zst|*.zst)
            case "$magic" in
                28b52ffd*)
                    if command -v zstd >/dev/null 2>&1; then
                        zstd -t "$file" >/dev/null 2>&1 && return 0 || return 1
                    fi
                    echo "[_gh_verify_file][ERROR] 缺少 zstd 工具，拒绝放行未经验证的 zstd 文件: $file" >&2
                    return 1
                    ;;
                *) return 1 ;;
            esac
            ;;
        *.tar)
            if command -v tar >/dev/null 2>&1; then
                tar -tf "$file" >/dev/null 2>&1 && return 0 || return 1
            fi
            echo "[_gh_verify_file][ERROR] 缺少 tar 工具，拒绝放行未经验证的 tar 归档: $file" >&2
            return 1
            ;;
    esac

    # 2. 对其他文件，若命中已知压缩包魔数，亦执行格式完整性检查（工具缺失拒绝放行）
    case "$magic" in
        1f8b*)
            gzip -t "$file" >/dev/null 2>&1 && return 0 || return 1
            ;;
        504b0304*|504b0506*|504b0708*)
            if command -v unzip >/dev/null 2>&1; then
                unzip -t "$file" >/dev/null 2>&1 && return 0 || return 1
            fi
            echo "[_gh_verify_file][ERROR] 缺少 unzip 工具，拒绝放行未经验证的 zip 文件: $file" >&2
            return 1
            ;;
        fd377a58*)
            if command -v xz >/dev/null 2>&1; then
                xz -t "$file" >/dev/null 2>&1 && return 0 || return 1
            fi
            echo "[_gh_verify_file][ERROR] 缺少 xz 工具，拒绝放行未经验证的 xz 文件: $file" >&2
            return 1
            ;;
        425a68*)
            if command -v bzip2 >/dev/null 2>&1; then
                bzip2 -t "$file" >/dev/null 2>&1 && return 0 || return 1
            fi
            echo "[_gh_verify_file][ERROR] 缺少 bzip2 工具，拒绝放行未经验证的 bz2 文件: $file" >&2
            return 1
            ;;
        28b52ffd*)
            if command -v zstd >/dev/null 2>&1; then
                zstd -t "$file" >/dev/null 2>&1 && return 0 || return 1
            fi
            echo "[_gh_verify_file][ERROR] 缺少 zstd 工具，拒绝放行未经验证的 zstd 文件: $file" >&2
            return 1
            ;;
    esac

    # 3. 普通文件（.sh / 二进制）：严禁 HTML 错误页/登录页（扩大至 1024 字节扫描，与 yf_verify_archive 对齐，P2-1）
    if head -c 1024 "$file" 2>/dev/null | grep -qiE '^[[:space:]]*(<html|<!DOCTYPE html|<head|<body|<xml)'; then
        return 1
    fi

    # 4. 纯文本代理错误提示/停用页（扫描放宽至 65536 字节文件前 2048 字节，与 yf_verify_archive 对齐，P2-1）
    if [ "$size" -lt 65536 ] && head -c 2048 "$file" 2>/dev/null | grep -qiE 'error|invalid|denied|blocked|forbidden|not found|abuse|suspend|suspent|report|rate limit|captcha|security|gateway|unavailable|bad request|timeout|请|错误|拦截|未找到|停止'; then
        return 1
    fi

    # 5. 小于 512 字节且首字符不是脚本魔数（#!）的 ASCII 文本文件，一律当做非预期错误输出拒收
    if [ "$size" -lt 512 ]; then
        local first_two=$(head -c 2 "$file" 2>/dev/null)
        if [ "$first_two" != "#!" ]; then
            if LC_ALL=C grep -qE '^[[:print:][:space:]]+$' "$file" 2>/dev/null; then
                return 1
            fi
        fi
    fi

    return 0
}

# ---------- 传输层 TLS 校验：默认开启，放宽必须显式 opt-in（报告 P1-3） ----------
#
# 口径：**默认一律做 TLS 证书校验**。只有显式设置 `YF_INSECURE_DOWNLOAD=1` 时才放宽
# （老系统 CA 根证书缺失 / 自建内网镜像等极端场景），且必须打醒目告警，便于事后追查。
#
# 刻意**不提供**「校验失败后自动降级重试」的兜底：一次失败就是失败，不会偷偷改用
# 跳证书再试一遍 —— 那种兜底等于把默认安全的开关又拧回去了。需要放宽请人工设置
# 环境变量，并在安装记录里留下痕迹（[WARN] 日志就是痕迹）。
#
# 本函数是仓库里唯一产出「放宽 TLS 参数」的地方（单一真源），
# `scripts/lib.sh::yf_download` 与 `_gh_try_download` 都走它。
YF_INSECURE_DOWNLOAD="${YF_INSECURE_DOWNLOAD:-}"

# 是否已显式开启「关闭 TLS 校验」：只认字符串 1，其它值（含空、0、yes）一律视为未开启。
yf_insecure_download_enabled() {
    [ "${YF_INSECURE_DOWNLOAD}" = "1" ]
}

# 用法: yf_wget_tls_extra_args <url>
# 输出: 要追加给 wget 的 TLS 参数（默认无输出 = 保持证书校验）；
#       仅当 YF_INSECURE_DOWNLOAD=1 时输出放宽参数，并向 stderr 打 [WARN] 告警。
# 注意: 调用方必须**不加引号**地使用命令替换（空值要能展开成「没有参数」）。
yf_wget_tls_extra_args() {
    if yf_insecure_download_enabled; then
        echo "[WARN] TLS 校验已被 YF_INSECURE_DOWNLOAD=1 关闭: $1" >&2
        echo "--no-check-certificate"
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

    # 默认做 TLS 校验；放宽参数只能由 yf_wget_tls_extra_args 在显式 opt-in 时给出
    # 补充 --dns-timeout=10 --connect-timeout=10 避免底层握手死等；
    # 且若系统存在 timeout 命令，增加进程级硬超时强杀，杜绝假死节点长期阻塞
    local _tls_extra
    _tls_extra=$(yf_wget_tls_extra_args "$url")
    if command -v timeout >/dev/null 2>&1; then
        timeout "$timeout" wget $_tls_extra -O "$file" --dns-timeout=10 --connect-timeout=10 --timeout="$timeout" --tries=1 -q "$url" 2>/dev/null
    else
        wget $_tls_extra -O "$file" --dns-timeout=10 --connect-timeout=10 --timeout="$timeout" --tries=1 -q "$url" 2>/dev/null
    fi

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

    # 检查 URL 格式合法性：防止空 tag 导致产生形如 releases/download//xxx 的死链接
    if [[ "$url" =~ (releases/download//|archive/refs/tags//) ]] || [[ "$url" =~ [^:]//[^/]+$ ]]; then
        echo "[github_download] 错误: URL 包含非法空路径段或双斜杠: $url" >&2
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

    # **非 GitHub 的地址一律直连**：GitHub 加速节点只能代理 github.com 系的 URL，
    # 把 https://thrysoee.dk/... 塞进 https://gh.con.sh/ 只换来一段几十字节的错误文本
    # （真机 PHP8.2 安装就卡在这里：libedit 两个源都被判「包损坏」）。
    if ! _gh_is_github_url "$url"; then
        echo "[github_download] 非 GitHub 地址，直连下载 (${timeout}s)..."
        if _gh_try_download "$file" "$url" "$timeout"; then
            local _sz=$(wc -c < "$file" 2>/dev/null | tr -d ' ')
            echo "[github_download] ✓ 直连下载成功 (大小: ${_sz} 字节，校验通过)"
            return 0
        fi
        echo "[github_download] ✗ 直连下载失败: $url"
        return 1
    fi

    # 获取最佳节点（缓存读取或极速测速）
    _gh_get_best_proxy >/dev/null
    local best_proxy="$_GH_BEST_PROXY"
    
    if [ -n "$best_proxy" ]; then
        local proxy_url=$(_gh_proxy_url "$best_proxy" "$url")
        local show_best=$best_proxy
        if [ "$show_best" = "direct" ]; then
            show_best="官方直连"
        fi
        echo "[github_download] 命中最佳节点: ${show_best}"
        echo "[github_download] 正在尝试下载 (${timeout}s)..."
        if _gh_try_download "$file" "$proxy_url" "$timeout"; then
            local _sz=$(wc -c < "$file" 2>/dev/null | tr -d ' ')
            echo "[github_download] ✓ 下载成功 (大小: ${_sz} 字节，校验通过)"
            return 0
        else
            echo "[github_download] ✗ 最佳节点下载失败，正在探测响应状态..."
            # 测速缓存里的"最佳节点"已实际失败（节点挂了/被限流）：立刻作废缓存，
            # 否则接下来 30 分钟内的每个安装任务都会先撞一次同一个节点。
            rm -f "$_GH_SPEED_CACHE_FILE" 2>/dev/null
            local probe_code=$(LC_ALL=C curl -sL -m 5 -o/dev/null -w "%{http_code}" "$proxy_url" 2>/dev/null)
            if [ "$probe_code" = "404" ] || [ "$probe_code" = "410" ]; then
                echo "[github_download] ✗ 目标资源不存在 (HTTP $probe_code Not Found)，终止所有代理轮询！" >&2
                echo "[github_download] 提示: 上游 GitHub 资源不存在，请检查地址或 tag 是否正确: $url" >&2
                return 1
            fi
            echo "[github_download] 状态码为 ${probe_code:-000}，非 404 错误，准备进入降级备选节点轮询"
        fi
    fi

    # 降级轮询机制
    echo "[github_download] === 进入最终降级轮询机制 ==="
    # 备选节点单次超时压缩至最多 15 秒（避免无效等待数分钟）
    local fallback_timeout=$timeout
    if [ "$fallback_timeout" -gt 15 ]; then
        fallback_timeout=15
    fi

    for proxy in "${_GH_PROXY_LIST[@]}"; do
        local is_tested=false
        if [ "$best_proxy" = "direct" ] && [ -z "$proxy" ]; then
            is_tested=true
        elif [ "$best_proxy" = "$proxy" ]; then
            is_tested=true
        fi
        if [ "$is_tested" = "true" ]; then
            continue
        fi

        # 智能过滤：跳过在测速中已明确确认失败的死节点
        local is_failed=false
        for failed_p in "${_GH_FAILED_PROXIES[@]}"; do
            if [ "$failed_p" = "$proxy" ]; then
                is_failed=true
                break
            fi
        done
        if [ "$is_failed" = "true" ]; then
            continue
        fi

        # 智能过滤：跳过在测速中已明确确认失败的死节点
        local is_failed=false
        for failed_p in "${_GH_FAILED_PROXIES[@]}"; do
            if [ "$failed_p" = "$proxy" ]; then
                is_failed=true
                break
            fi
        done
        if [ "$is_failed" = "true" ]; then
            continue
        fi

        local proxy_url=$(_gh_proxy_url "$proxy" "$url")
        local show_name=$proxy
        if [ -z "$show_name" ]; then
            show_name="官方直连"
        fi
        echo "[github_download] 尝试备选节点: ${show_name} (${fallback_timeout}s)..."
        if _gh_try_download "$file" "$proxy_url" "$fallback_timeout"; then
            local _sz=$(wc -c < "$file" 2>/dev/null | tr -d ' ')
            echo "[github_download] ✓ 降级轮询下载成功 (大小: ${_sz} 字节，校验通过)"
            return 0
        else
            # 若备选节点返回 404，也直接终止轮询（避免浪费时间）
            local probe_code=$(LC_ALL=C curl -sL -m 5 -o/dev/null -w "%{http_code}" "$proxy_url" 2>/dev/null)
            if [ "$probe_code" = "404" ] || [ "$probe_code" = "410" ]; then
                echo "[github_download] ✗ 备选节点确认目标资源不存在 (HTTP $probe_code Not Found)，终止所有代理轮询！" >&2
                echo "[github_download] URL: $url" >&2
                return 1
            fi
        fi
    done

    # 全部失败
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

    # 获取最佳节点
    _gh_get_best_proxy >/dev/null
    local best_proxy="$_GH_BEST_PROXY"
    
    if [ -n "$best_proxy" ]; then
        local proxy_repo_url=$(_gh_proxy_url "$best_proxy" "$repo_url")
        local show_best=$best_proxy
        if [ "$show_best" = "direct" ]; then
            show_best="官方直连"
        fi
        echo "[github_clone] 命中最佳节点: ${show_best}"
        echo "[github_clone] 正在尝试克隆 (${timeout}s)..."
        if _gh_try_clone "$target_dir" "$proxy_repo_url" "$branch" "$timeout"; then
            echo "[github_clone] ✓ 克隆成功"
            return 0
        fi
        echo "[github_clone] ✗ 最佳节点克隆失败，准备尝试备选节点..."
    fi

    # 降级轮询机制
    echo "[github_clone] === 进入最终降级轮询机制 ==="
    for proxy in "${_GH_PROXY_LIST[@]}"; do
        local is_tested=false
        if [ "$best_proxy" = "direct" ] && [ -z "$proxy" ]; then
            is_tested=true
        elif [ "$best_proxy" = "$proxy" ]; then
            is_tested=true
        fi
        if [ "$is_tested" = "true" ]; then
            continue
        fi

        # 智能过滤：跳过在测速中已明确确认失败的死节点
        local is_failed=false
        for failed_p in "${_GH_FAILED_PROXIES[@]}"; do
            if [ "$failed_p" = "$proxy" ]; then
                is_failed=true
                break
            fi
        done
        if [ "$is_failed" = "true" ]; then
            continue
        fi

        local proxy_repo_url=$(_gh_proxy_url "$proxy" "$repo_url")
        local show_name=$proxy
        if [ -z "$show_name" ]; then
            show_name="官方直连"
        fi
        echo "[github_clone] 尝试备选节点: ${show_name} (${timeout}s)..."
        if _gh_try_clone "$target_dir" "$proxy_repo_url" "$branch" "$timeout"; then
            echo "[github_clone] ✓ 降级轮询克隆成功"
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

    # 获取最佳节点
    _gh_get_best_proxy >/dev/null
    local best_proxy="$_GH_BEST_PROXY"
    
    local result
    if [ -n "$best_proxy" ]; then
        local proxy_url=$(_gh_proxy_url "$best_proxy" "$url")
        result=$(curl -s -m "$timeout" "$proxy_url" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$result" ]; then
            echo "$result"
            return 0
        fi
    fi

    # 降级轮询
    for proxy in "${_GH_PROXY_LIST[@]}"; do
        local is_tested=false
        if [ "$best_proxy" = "direct" ] && [ -z "$proxy" ]; then
            is_tested=true
        elif [ "$best_proxy" = "$proxy" ]; then
            is_tested=true
        fi
        if [ "$is_tested" = "true" ]; then
            continue
        fi

        # 智能过滤：跳过在测速中已明确确认失败的死节点
        local is_failed=false
        for failed_p in "${_GH_FAILED_PROXIES[@]}"; do
            if [ "$failed_p" = "$proxy" ]; then
                is_failed=true
                break
            fi
        done
        if [ "$is_failed" = "true" ]; then
            continue
        fi

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

# ---------------------------------------------------------------------------
# yf_multi_download <url> <outfile> [conns] [sha256|-] [timeout]
#
# 多连接分段下载 + 续传 + 强校验。为一个具体问题而写（2026-10-28）：
#   MariaDB 官方 bintar 只在大陆**不可用**的 archive.mariadb.org 上，
#   单连接实测 13~24 KB/s（340MB 要 4 小时），但同一主机 8 连接聚合 ~150 KB/s。
#   所以「能不能装」在代码之外还取决于下载器并发度。
#
# 行为：
#   1. 已有文件且 sha256（若给了）/内容 都对 → 直接复用，不重下；
#   2. 有 aria2c → 用它（自带多连接 + 续传）；
#   3. 否则 HEAD 取 content-length，按连接数切段并行 curl，逐段核对后拼接；
#      拿不到长度 / 不支持 Range / 文件太小 → 退回单线程 `curl -C -`（续传）重试 3 次；
#   4. 最后校验 sha256（给了才校验）+ 内容魔数（yf_verify_archive）。
# 返回：0 = 成功且校验通过；非 0 = 失败（并删除半成品，避免下次拿坏包当缓存）
# ---------------------------------------------------------------------------
function yf_multi_download() {
    local url=$1
    local out=$2
    local conns=${3:-8}
    local want_sha=${4:--}
    local to=${5:-3600}

    if [ -z "$url" ] || [ -z "$out" ]; then
        echo "[yf_multi_download] 用法: yf_multi_download <url> <outfile> [conns] [sha256|-] [timeout]" >&2
        return 1
    fi
    case "$conns" in ''|*[!0-9]*) conns=8 ;; esac
    [ "$conns" -ge 1 ] 2>/dev/null || conns=8
    [ "$conns" -gt 16 ] && conns=16

    # 1) 复用已有文件
    if [ -f "$out" ]; then
        local _have=0
        if [ "$want_sha" != "-" ] && [ -n "$want_sha" ] && command -v sha256sum >/dev/null 2>&1; then
            [ "$(sha256sum "$out" | awk '{print $1}')" = "$want_sha" ] && _have=1
        elif yf_verify_archive "$out" 2>/dev/null; then
            _have=1
        fi
        if [ "$_have" = "1" ]; then
            return 0
        fi
        echo "[yf_multi_download] 已有文件不完整或校验不符，删除重下: $out" >&2
        rm -f "$out"
    fi
    mkdir -p "$(dirname "$out")" 2>/dev/null

    local _got=0
    # 2) aria2c
    if command -v aria2c >/dev/null 2>&1; then
        if aria2c -x"$conns" -s"$conns" --continue=true --allow-overwrite=true \
                  --auto-file-renaming=false --console-log-level=warn \
                  --summary-interval=0 --timeout=30 --max-tries=3 \
                  -d "$(dirname "$out")" -o "$(basename "$out")" "$url" >/dev/null 2>&1; then
            _got=1
        else
            echo "[yf_multi_download] aria2c 失败，改用 curl 分段下载" >&2
            rm -f "$out"
        fi
    fi

    # 3) 并行分段 curl
    if [ "$_got" != "1" ]; then
        _yf_multi_curl "$url" "$out" "$conns" "$to" || _got=0
        [ -f "$out" ] && _got=1
    fi
    if [ "$_got" != "1" ]; then
        echo "[yf_multi_download] 下载失败: $url" >&2
        rm -f "$out"
        return 1
    fi

    # 4) 强校验
    if [ "$want_sha" != "-" ] && [ -n "$want_sha" ] && command -v sha256sum >/dev/null 2>&1; then
        local _sha
        _sha=$(sha256sum "$out" | awk '{print $1}')
        if [ "$_sha" != "$want_sha" ]; then
            echo "[yf_multi_download] sha256 不匹配（期望 ${want_sha} 实际 ${_sha}），删除: $out" >&2
            rm -f "$out"
            return 1
        fi
    fi
    if ! yf_verify_archive "$out" 2>/dev/null; then
        # 没有已知魔数的普通文件不拦（yf_verify_archive 只拦 HTML 错误页/无效压缩包）
        echo "[yf_multi_download] 内容校验未通过（可能是错误页/截断），删除: $out" >&2
        rm -f "$out"
        return 1
    fi
    return 0
}

# 分段并行下载的内部实现（不对外承诺稳定；失败会删半成品）。
#
# 分块策略（2026-10-28 实测教训）：**不要把一个文件平均切成 N 大块**。
# 第一次实现按 349MB/8 ≈ 43MB 切，8 条连接跑 40 分钟后有两条断流，
# 整批作废（"期望 349220601 实际 242864858"），40 分钟白等。
# 现在改成「固定 4MB 小块 + 有限轮次补缺」：断流只损失 4MB，下一轮只重下缺块，
# 且越到后面并发越集中在慢块上（尾延迟不再被单条慢连接支配）。
function _yf_multi_curl() {
    local url=$1 out=$2 conns=$3 to=$4
    local size="" hdr=""
    hdr=$(curl -sIL -m 20 "$url" 2>/dev/null)
    size=$(printf '%s' "$hdr" | awk 'tolower($1)=="content-length:" {v=$2} END{print v}' | tr -d '
')
    case "$size" in ''|*[!0-9]*) size="" ;; esac

    # 小于 8MB 或拿不到长度：单线程 + 续传重试
    if [ -z "$size" ] || [ "$size" -lt 8388608 ] || [ "$conns" -le 1 ]; then
        local n=0 got=""
        while [ "$n" -lt 3 ]; do
            if curl -sL -C - --retry 3 --retry-delay 2 --max-time "$to" -o "$out" "$url" 2>/dev/null                     && [ -s "$out" ]; then
                if [ -n "$size" ]; then
                    got=$(wc -c < "$out" 2>/dev/null | tr -d ' ')
                    if [ "$got" = "$size" ] && yf_verify_archive "$out" 2>/dev/null; then
                        return 0
                    fi
                elif yf_verify_archive "$out" 2>/dev/null; then
                    return 0
                fi
            fi
            n=$(( n + 1 ))
            sleep 2
        done
        rm -f "$out"
        return 1
    fi

    local part_dir="${out}.parts"
    rm -rf "$part_dir"
    mkdir -p "$part_dir" || return 1

    local chunk=4194304                     # 4MB/块：断流损失小、补缺便宜
    local total=$(( (size + chunk - 1) / chunk ))
    local round=0 missing=1 idx st en exp f got running
    while [ "$missing" = "1" ] && [ "$round" -lt 4 ]; do
        round=$(( round + 1 ))
        missing=0
        running=0
        idx=0
        while [ "$idx" -lt "$total" ]; do
            st=$(( idx * chunk ))
            en=$(( st + chunk - 1 ))
            [ "$en" -ge "$size" ] && en=$(( size - 1 ))
            exp=$(( en - st + 1 ))
            f="${part_dir}/p_${idx}"
            got=""
            [ -f "$f" ] && got=$(wc -c < "$f" 2>/dev/null | tr -d ' ')
            if [ "$got" = "$exp" ]; then
                idx=$(( idx + 1 ))
                continue
            fi
            missing=1
            rm -f "$f"
            ( curl -sL --retry 3 --retry-delay 2 --max-time "$to" -r "${st}-${en}" -o "$f" "$url" 2>/dev/null ) &
            running=$(( running + 1 ))
            if [ "$running" -ge "$conns" ]; then
                wait
                running=0
            fi
            idx=$(( idx + 1 ))
        done
        [ "$running" -gt 0 ] && wait
        if [ "$round" -gt 1 ]; then
            echo "[yf_multi_download] 第 ${round} 轮补下缺失分块..." >&2
        fi
    done

    # 逐块核对后按序拼接
    : > "$out"
    idx=0
    while [ "$idx" -lt "$total" ]; do
        f="${part_dir}/p_${idx}"
        if [ ! -f "$f" ]; then
            echo "[yf_multi_download] 缺少分块 ${idx}，放弃" >&2
            rm -rf "$part_dir" "$out"
            return 1
        fi
        cat "$f" >> "$out" 2>/dev/null || { rm -rf "$part_dir" "$out"; return 1; }
        idx=$(( idx + 1 ))
    done
    rm -rf "$part_dir"

    got=$(wc -c < "$out" 2>/dev/null | tr -d ' ')
    if [ "$got" != "$size" ]; then
        echo "[yf_multi_download] 分段下载不完整（期望 ${size} 实际 ${got:-0} 字节），放弃" >&2
        rm -f "$out"
        return 1
    fi
    # 拼完立刻验内容（错误页/截断包在这里拦下，别等调用方）
    if ! yf_verify_archive "$out" 2>/dev/null; then
        echo "[yf_multi_download] 分段拼接后内容校验未通过，放弃: $out" >&2
        rm -f "$out"
        return 1
    fi
    return 0
}
