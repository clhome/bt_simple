#!/bin/bash
# =========================================================================
# ==御风面板== 一键部署脚本
# 支持: 全新安装 / 从 mdserver-web 迁移 / 从宝塔面板迁移
# =========================================================================
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
export LANG=en_US.UTF-8

# 引入统一的 GitHub 下载函数库
_gh_deploy_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)/scripts/github_download.sh"
if [ -f "$_gh_deploy_lib" ]; then
    source "$_gh_deploy_lib"
else
    _gh_deploy_lib="/tmp/github_download.sh"
    _gh_dl_url="https://raw.githubusercontent.com/clhome/bt_simple/master/scripts/github_download.sh"
    # 本地不存在时尝试网络拉取（兼容单脚本一键安装场景），使用 -f 参数避免下载到 502 HTML 错误页
    if curl -sSLf --connect-timeout 2 "$_gh_dl_url" -o "$_gh_deploy_lib" 2>/dev/null || \
       curl -sSLf "https://gh-proxy.com/$_gh_dl_url" -o "$_gh_deploy_lib" 2>/dev/null || \
       curl -sSLf "https://ghproxy.net/$_gh_dl_url" -o "$_gh_deploy_lib" 2>/dev/null; then
        source "$_gh_deploy_lib"
    fi
fi

# ---------- 颜色定义 ----------
RED='\033[31m'
GREEN='\033[32m'
YELLOW='\033[33m'
BLUE='\033[34m'
PLAIN='\033[0m'
BOLD='\033[1m'

# ---------- 全局变量 ----------
PANEL_DIR=/www/server/yufeng_panel
LEGACY_PANEL_DIR=/www/server/mdserver-web
BT_DIR=/www/server/panel
BACKUP_DIR=/www/backup
TIMESTAMP=$(date +%Y%m%d%H%M%S)
LOG_FILE=/var/log/bt_simple_deploy.log
SILENT_MODE=false

# fork 仓库地址（⚠️ 请根据实际修改为你的 GitHub 仓库地址）
GIT_REPO_BASE="https://github.com/clhome/bt_simple.git"
GIT_REPO="${BT_SIMPLE_REPO:-$GIT_REPO_BASE}"
GIT_BRANCH="${BT_SIMPLE_BRANCH:-master}"
FORCE_CN=false
_IS_CHINA=""

# ---------- 中国区加速 ----------
check_china() {
    if [ "$FORCE_CN" = "true" ]; then
        return 0
    fi
    if [ -n "$_IS_CHINA" ]; then
        [ "$_IS_CHINA" = "true" ] && return 0 || return 1
    fi
    # 通过 IP 地理位置判断是否在中国境内
    local status=$(curl -s -m 2 http://www.baidu.com > /dev/null && echo "ok" || echo "fail")
    if [ "$status" = "ok" ]; then
        # 优先使用 myip.ipip.net，它在国内非常快速且直接返回中文归属地
        local ipip_cn=$(curl -s -m 2 http://myip.ipip.net 2>/dev/null)
        if [[ "$ipip_cn" == *"中国"* ]]; then
            _IS_CHINA="true"
            return 0
        fi
        
        # 降级：若 ipip.net 接口由于网络抖动不可达，则降级使用 ipapi.co
        local cn=$(curl -s -m 2 https://ipapi.co/country/ 2>/dev/null)
        if [ "$cn" = "CN" ]; then
            _IS_CHINA="true"
            return 0
        fi
    fi
    _IS_CHINA="false"
    return 1
}

get_github_url() {
    local original_url=$1
    if check_china; then
        if [[ $original_url == *"github.com"* ]]; then
            local best_proxy=""
            if type _gh_get_best_proxy >/dev/null 2>&1; then
                _gh_get_best_proxy >/dev/null
                best_proxy="$_GH_BEST_PROXY"
            fi
            local use_proxy="${best_proxy:-https://gh-proxy.com/}"
            
            if type _gh_proxy_url >/dev/null 2>&1; then
                _gh_proxy_url "$use_proxy" "$original_url"
            else
                echo "${use_proxy}${original_url}"
            fi
            return
        fi
    fi
    echo "$original_url"
}

setup_china_git_config() {
    if check_china; then
        log_info "配置 Git 全局代理加速 (GitHub -> ghproxy)..."
        
        local best_proxy=""
        if type _gh_get_best_proxy >/dev/null 2>&1; then
            _gh_get_best_proxy >/dev/null
            best_proxy="$_GH_BEST_PROXY"
        fi
        
        if [ -z "$best_proxy" ]; then
            best_proxy="https://gh-proxy.com/"
        fi
        
        # 定义备用代理列表 (与 github_download.sh 保持一致，用于清理旧规则)
        local proxies=(
            "https://gh-proxy.com/"
            "https://cors.zme.ink/"
            "https://gh.ddlc.top/"
            "https://ghproxy.net/"
        )
        
        # 先清理以前可能设置过的所有代理规则，防止堆积
        for proxy in "${proxies[@]}"; do
            git config --global --remove-section url."${proxy}https://github.com/" 2>/dev/null || true
        done
        git config --global --remove-section url."https://gh-proxy.com/https://github.com/" 2>/dev/null || true
        
        if [ -n "$best_proxy" ]; then
            log_info "选用存活的 GitHub 代理: $best_proxy"
            git config --global url."${best_proxy}https://github.com/".insteadOf "https://github.com/"
        else
            log_warn "所有 GitHub 代理节点均探测失败，本次将使用 GitHub 官方直连"
        fi
        
        git config --global http.version HTTP/1.1
    fi
}

# ---------- 工具函数 ----------
log_info()  { echo -e "${GREEN}[INFO]${PLAIN} $1" | tee -a $LOG_FILE; }
log_warn()  { echo -e "${YELLOW}[WARN]${PLAIN} $1" | tee -a $LOG_FILE; }
log_error() { echo -e "${RED}[ERROR]${PLAIN} $1" | tee -a $LOG_FILE; }

confirm() {
    if [ "$SILENT_MODE" = "true" ]; then
        return 0
    fi
    local msg="$1"
    local response="no"
    echo -e "\n${BOLD}${YELLOW}$msg${PLAIN}"
    if [ -t 0 ]; then
        read -p "请输入 [yes/no]: " response
    else
        printf "请输入 [yes/no]: "
        read response < /dev/tty 2>/dev/null || response="no"
    fi
    [ "$response" = "yes" ]
}

install_acme() {
    if [ -d /root/.acme.sh ]; then
        return 0
    fi
    log_info "安装 acme.sh ..."
    local acme_downloaded=false
    if type github_download >/dev/null 2>&1; then
        log_info "正在使用统一网络库下载 acme.sh ..."
        if github_download "/tmp/acme.sh.tar.gz" "https://github.com/acmesh-official/acme.sh/archive/master.tar.gz" 30; then
            mkdir -p /tmp/acme-src
            tar -zxf /tmp/acme.sh.tar.gz -C /tmp/acme-src --strip-components=1
            cd /tmp/acme-src && ./acme.sh --install -m my@example.com 2>/dev/null
            cd - >/dev/null
            rm -rf /tmp/acme-src /tmp/acme.sh.tar.gz
            acme_downloaded=true
        fi
    fi

    if [ "$acme_downloaded" = "false" ]; then
        if check_china; then
            local best_proxy=""
            if type _gh_get_best_proxy >/dev/null 2>&1; then
                _gh_get_best_proxy >/dev/null
                best_proxy="$_GH_BEST_PROXY"
            fi
            local acme_proxy="${best_proxy:-https://gh-proxy.com/}"
            curl "${acme_proxy}https://raw.githubusercontent.com/acmesh-official/acme.sh/master/acme.sh" | sh -s -- --install-online -m my@example.com 2>/dev/null
        else
            curl -fsSL https://get.acme.sh | bash 2>/dev/null
        fi
    fi

    if [ -d /root/.acme.sh ]; then
        /root/.acme.sh/acme.sh --set-default-ca --server letsencrypt
    fi
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "请以 root 身份运行此脚本!"
        exit 1
    fi
}

detect_os() {
    _os=$(uname)
    if [ "$_os" = "Darwin" ]; then
        OSNAME='macos'
    elif grep -Eqi "openSUSE" /etc/*-release 2>/dev/null; then OSNAME='opensuse'
    elif grep -Eqi "FreeBSD" /etc/*-release 2>/dev/null; then OSNAME='freebsd'
    elif grep -Eqi "EulerOS|openEuler" /etc/*-release 2>/dev/null; then OSNAME='euler'
    elif grep -Eqi "CentOS" /etc/*-release 2>/dev/null; then OSNAME='rhel'
    elif grep -Eqi "Rocky" /etc/*-release 2>/dev/null; then OSNAME='rhel'
    elif grep -Eqi "AlmaLinux" /etc/*-release 2>/dev/null; then OSNAME='rhel'
    elif grep -Eqi "Fedora" /etc/*-release 2>/dev/null; then OSNAME='rhel'
    elif grep -Eqi "Red Hat" /etc/*-release 2>/dev/null; then OSNAME='rhel'
    elif grep -Eqi "Amazon Linux" /etc/*-release 2>/dev/null; then OSNAME='amazon'
    elif grep -Eqi "Debian" /etc/*-release 2>/dev/null; then OSNAME='debian'
    elif grep -Eqi "Ubuntu" /etc/*-release 2>/dev/null; then OSNAME='ubuntu'
    elif grep -Eqi "Alpine" /etc/*-release 2>/dev/null; then OSNAME='alpine'
    else OSNAME='unknow'
    fi
    log_info "检测到操作系统: ${OSNAME}"
}

check_architecture() {
    log_info "检测系统架构..."
    local is64bit=$(getconf LONG_BIT)
    if [ "${is64bit}" != '64' ]; then
        log_error "抱歉，当前面板不支持32位系统，请使用64位系统！"
        exit 1
    fi
}

check_system_resources() {
    log_info "检测系统资源..."
    local mem_total=$(free -m | grep Mem | awk '{print $2}')
    if [ "${mem_total}" -lt "450" ]; then
        log_error "当前服务器内存为: ${mem_total}MB"
        log_error "检测到当前服务器内存小于450MB，无法继续安装面板！"
        log_error "建议更换内存大于等于512MB的服务器。"
        exit 1
    fi

    local root_disk_space=$(df -m | grep '/$' | awk '{print $4}')
    if [ -n "${root_disk_space}" ] && [ "${root_disk_space}" -le 400 ]; then
        log_error "系统盘(/)剩余空间不足400M，无法继续安装！"
        exit 1
    fi

    local www_disk_space=$(df -m | grep '/www$' | awk '{print $4}')
    if [ -n "${www_disk_space}" ] && [ "${www_disk_space}" -le 400 ]; then
        log_error "/www盘剩余空间不足400M，无法继续安装！"
        exit 1
    fi
}

check_os_version() {
    log_info "检查系统版本支持情况..."
    if [ -f /etc/redhat-release ]; then
        if grep -qE ' 6\.' /etc/redhat-release; then
            log_error "CentOS 6 官方已停止支持，不支持安装面板，请更换 CentOS 7/8/9 或其它系统。"
            exit 1
        fi
    fi

    if grep -qi "Ubuntu" /etc/issue 2>/dev/null; then
        local ubuntu_ver=$(cat /etc/issue | grep -i Ubuntu | awk '{print $2}' | cut -f 1 -d '.')
        if [ -n "${ubuntu_ver}" ] && [ "${ubuntu_ver}" -lt "16" ]; then
            log_error "Ubuntu ${ubuntu_ver} 官方已停止支持，不支持安装面板，建议更换 Ubuntu 20/22/24。"
            exit 1
        fi
    fi
    
    if grep -qi "Debian" /etc/issue 2>/dev/null; then
        local debian_ver=$(cat /etc/issue | grep -i Debian | awk '{print $3}')
        if [ -n "${debian_ver}" ] && [ "${debian_ver}" -lt "10" ]; then
            log_error "Debian ${debian_ver} 官方已停止支持，不支持安装面板，建议更换 Debian 11/12。"
            exit 1
        fi
    fi
}

fix_apt_lock() {
    if ! command -v apt-get >/dev/null 2>&1; then
        return 0
    fi
    
    log_info "检查 apt/dpkg 锁状态..."
    local wait=0
    while fuser /var/lib/dpkg/lock >/dev/null 2>&1 || \
          fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || \
          fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || \
          fuser /var/cache/apt/archives/lock >/dev/null 2>&1; do
        
        if [ ${wait} -eq 0 ]; then
            log_warn "检测到 apt/dpkg 正在使用中，等待完成..."
        fi
        
        [ ${wait} -ge 60 ] && break
        sleep 3
        wait=$((wait + 3))
    done
    
    if fuser /var/lib/dpkg/lock >/dev/null 2>&1 || \
       fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || \
       fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || \
       fuser /var/cache/apt/archives/lock >/dev/null 2>&1; then
        
        log_warn "强制清理 apt/dpkg 锁..."
        pkill -9 unattended-upgr 2>/dev/null
        pkill -9 apt-get 2>/dev/null
        pkill -9 apt 2>/dev/null
        pkill -9 dpkg 2>/dev/null
        sleep 1
        
        rm -f /var/lib/dpkg/lock-frontend
        rm -f /var/lib/dpkg/lock
        rm -f /var/lib/apt/lists/lock
        rm -f /var/cache/apt/archives/lock
        
        log_info "修复 dpkg 状态..."
        dpkg --configure -a 2>/dev/null || true
        apt-get install -f -y 2>/dev/null || true
    fi
    return 0
}

setup_domestic_mirrors() {
    if ! check_china; then
        return 0
    fi

    log_info "检测到中国大陆网络，配置全局加速镜像源..."

    # 配置 pip 国内镜像 (全局加速后续的 Python 依赖安装)
    mkdir -p ~/.pip
    if [ ! -f ~/.pip/pip.conf ] || ! grep -q "aliyun" ~/.pip/pip.conf 2>/dev/null; then
        cat > ~/.pip/pip.conf <<EOF
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
[install]
trusted-host = mirrors.aliyun.com
EOF
        log_info "已配置 pip 阿里云加速源"
    fi

    # 配置系统 APT 源加速 (Ubuntu/Debian)
    if command -v apt-get >/dev/null 2>&1 && [ -f "/etc/apt/sources.list" ]; then
        local current_source=$(grep ^deb /etc/apt/sources.list | head -n 1 | sed -E 's|^[^ ]+ https?://([^/]+).*|\1|')
        
        # 如果当前源属于慢速官方源，尝试替换为阿里云源
        if [[ "$current_source" == *"archive.ubuntu.com"* || "$current_source" == *"security.ubuntu.com"* || "$current_source" == *"deb.debian.org"* || "$current_source" == *"security.debian.org"* ]]; then
            log_info "当前 APT 源 ($current_source) 在国内较慢，正在切换至阿里云镜像..."
            \cp -rpa /etc/apt/sources.list /etc/apt/sources.list.btbackup
            sed -i "s/$current_source/mirrors.aliyun.com/g" /etc/apt/sources.list
            sed -i "s/archive.ubuntu.com/mirrors.aliyun.com/g" /etc/apt/sources.list
            sed -i "s/security.ubuntu.com/mirrors.aliyun.com/g" /etc/apt/sources.list
            sed -i "s/deb.debian.org/mirrors.aliyun.com/g" /etc/apt/sources.list
            sed -i "s/security.debian.org/mirrors.aliyun.com/g" /etc/apt/sources.list
            
            apt-get update -y -o Acquire::Languages=none >/dev/null 2>&1
            if [ $? -eq 0 ]; then
                log_info "APT 加速源配置完成"
            else
                log_warn "APT 源更新遇到问题，已回滚源配置..."
                \cp -rpa /etc/apt/sources.list.btbackup /etc/apt/sources.list
                apt-get update -y -o Acquire::Languages=none >/dev/null 2>&1
            fi
        fi
    fi
}

install_basic_deps() {
    setup_domestic_mirrors
    fix_apt_lock
    log_info "安装基础依赖..."
    if command -v apt >/dev/null 2>&1; then
        apt install -y wget curl zip unzip tar git cron >/dev/null 2>&1
    elif command -v yum >/dev/null 2>&1; then
        yum install -y wget curl zip unzip tar git crontabs >/dev/null 2>&1
    elif command -v apk >/dev/null 2>&1; then
        apk add wget curl zip unzip tar git >/dev/null 2>&1
    fi
    
    # 二次验证依赖是否安装成功
    local missing_tools=""
    for tool in wget curl zip unzip tar git; do
        if ! command -v $tool >/dev/null 2>&1; then
            missing_tools="$missing_tools $tool"
        fi
    done
    if [ -n "$missing_tools" ]; then
        log_error "基础依赖安装失败，缺少工具:$missing_tools"
        log_error "这通常是因为系统源不可用或网络问题。请尝试手动修复系统源后重试。"
        exit 1
    fi
}

set_panel_version() {
    log_info "设置面板版本号..."
    local final_ver=""
    
    # 0. 如果是执行远端最新版本升级，优先使用该版本，并同步修改本地文件
    if [ "$IS_UPDATING_TO_LATEST" = "true" ] && [ -n "$LATEST_REMOTE_VER" ]; then
        final_ver="$LATEST_REMOTE_VER"
        # 尝试同步修改 version.py 的硬编码，以防下一次读取错误
        if [ -f ${PANEL_DIR}/web/version.py ]; then
            local new_rel=$(echo "$final_ver" | awk -F. '{print $1}')
            local new_rev=$(echo "$final_ver" | awk -F. '{print $2}')
            local new_smv=$(echo "$final_ver" | awk -F. '{print $3}' | awk -F- '{print $1}')
            if [ -n "$new_rel" ] && [ -n "$new_rev" ] && [ -n "$new_smv" ]; then
                sed -i "s/^[[:space:]]*APP_RELEASE[[:space:]]*=.*/APP_RELEASE = $new_rel/" ${PANEL_DIR}/web/version.py
                sed -i "s/^[[:space:]]*APP_REVISION[[:space:]]*=.*/APP_REVISION = $new_rev/" ${PANEL_DIR}/web/version.py
                sed -i "s/^[[:space:]]*APP_SMALL_VERSION[[:space:]]*=.*/APP_SMALL_VERSION = $new_smv/" ${PANEL_DIR}/web/version.py
            fi
        fi
    fi
    
    # 1. 优先尝试从本地已下载覆盖的 web/version.py 中解析硬编码版本（最稳健的离线方案）
    if [ -z "$final_ver" ] && [ -f ${PANEL_DIR}/web/version.py ]; then
        local app_rel=$(grep -E '^[[:space:]]*APP_RELEASE[[:space:]]*=[[:space:]]*' ${PANEL_DIR}/web/version.py | awk -F '=' '{print $2}' | tr -d '[:space:]"')
        local app_rev=$(grep -E '^[[:space:]]*APP_REVISION[[:space:]]*=[[:space:]]*' ${PANEL_DIR}/web/version.py | awk -F '=' '{print $2}' | tr -d '[:space:]"')
        local app_smv=$(grep -E '^[[:space:]]*APP_SMALL_VERSION[[:space:]]*=[[:space:]]*' ${PANEL_DIR}/web/version.py | awk -F '=' '{print $2}' | tr -d '[:space:]"')
        local app_suf=$(grep -E '^[[:space:]]*APP_SUFFIX[[:space:]]*=[[:space:]]*' ${PANEL_DIR}/web/version.py | awk -F '=' '{print $2}' | tr -d "[:space:]'\"")
        
        if [ -n "$app_rel" ] && [ -n "$app_rev" ] && [ -n "$app_smv" ]; then
            if [ -n "$app_suf" ]; then
                final_ver="${app_rel}.${app_rev}.${app_smv}-${app_suf}"
            else
                final_ver="${app_rel}.${app_rev}.${app_smv}"
            fi
        fi
    fi
    
    # 2. 如果本地解析失败，且网络畅通，则尝试从 GitHub 接口获取 latest release 作为兜底
    if [ -z "$final_ver" ]; then
        local latest_ver
        if type github_api_get >/dev/null 2>&1; then
            latest_ver=$(github_api_get "https://api.github.com/repos/clhome/bt_simple/releases/latest" 2>/dev/null | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
        else
            latest_ver=$(curl -s -m 5 "https://api.github.com/repos/clhome/bt_simple/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
        fi
        if [ -n "$latest_ver" ]; then
            final_ver="$latest_ver"
        fi
    fi
    
    # 3. 最终写入 .version 文件
    if [ -n "$final_ver" ]; then
        # 确保去掉可能包含的 v 前缀
        final_ver=$(echo "$final_ver" | sed 's/^v//')
        echo "$final_ver" > ${PANEL_DIR}/.version
        log_info "当前已写入 .version 版本号: ${final_ver}"
    else
        log_warn "未能成功获取到版本号，使用默认硬编码显示"
    fi
}

# ---------- 环境检测 ----------
detect_environment() {
    HAS_YF=false
    HAS_MW=false
    HAS_BT=false

    if [ -d "$PANEL_DIR" ] && [ -f "$PANEL_DIR/cli.sh" ]; then
        HAS_YF=true
    fi
    if [ -d "$LEGACY_PANEL_DIR" ] && [ -f "$LEGACY_PANEL_DIR/cli.sh" ] && [ ! -L "$LEGACY_PANEL_DIR" ]; then
        HAS_MW=true
    fi
    if [ -d "$BT_DIR" ] && { [ -f "$BT_DIR/BT-Panel" ] || [ -f "$BT_DIR/main.py" ]; }; then
        HAS_BT=true
    fi
}

show_banner() {
    clear
    echo -e '+---------------------------------------------------+'
    echo -e '|                                                   |'
    echo -e '|   =============================================   |'
    echo -e '|                                                   |'
    echo -e '|          御风面板 bt_simple一键部署工具             |'
    echo -e '|                                                   |'
    echo -e '|   =============================================   |'
    echo -e '|                                                   |'
    echo -e '+---------------------------------------------------+'
    echo ""
    echo -e "  系统时间: ${BLUE}$(date '+%Y-%m-%d %H:%M:%S')${PLAIN}"
    echo -e "  操作系统: ${BLUE}${OSNAME}${PLAIN}"
    echo ""
}

# =====================================================================
# 备份功能
# =====================================================================
backup_mdserver_web() {
    mkdir -p $BACKUP_DIR
    if $HAS_YF; then
        log_info "备份 yufeng_panel 面板..."
        tar -czf ${BACKUP_DIR}/yufeng_panel-${TIMESTAMP}.tar.gz \
            --exclude='yufeng_panel/bin' \
            --exclude='yufeng_panel/lib' \
            --exclude='yufeng_panel/lib64' \
            --exclude='yufeng_panel/include' \
            -C /www/server yufeng_panel 2>/dev/null
        log_info "备份完成: ${BACKUP_DIR}/yufeng_panel-${TIMESTAMP}.tar.gz"
    else
        log_info "备份 mdserver-web 面板..."
        tar -czf ${BACKUP_DIR}/mdserver-web-${TIMESTAMP}.tar.gz \
            --exclude='mdserver-web/bin' \
            --exclude='mdserver-web/lib' \
            --exclude='mdserver-web/lib64' \
            --exclude='mdserver-web/include' \
            -C /www/server mdserver-web 2>/dev/null
        log_info "备份完成: ${BACKUP_DIR}/mdserver-web-${TIMESTAMP}.tar.gz"
    fi

    if [ -f ${PANEL_DIR}/data/system.db ]; then
        cp ${PANEL_DIR}/data/system.db ${BACKUP_DIR}/system.db.${TIMESTAMP}.bak
    fi
}

backup_bt_panel() {
    log_info "备份宝塔面板..."
    mkdir -p $BACKUP_DIR

    tar -czf ${BACKUP_DIR}/bt-panel-${TIMESTAMP}.tar.gz \
        -C /www/server panel 2>/dev/null

    if [ -f ${BT_DIR}/data/default.db ]; then
        cp ${BT_DIR}/data/default.db ${BACKUP_DIR}/bt_default.db.${TIMESTAMP}.bak
    fi
    log_info "备份完成: ${BACKUP_DIR}/bt-panel-${TIMESTAMP}.tar.gz"
}

# =====================================================================
# 回滚功能
# =====================================================================
rollback_mdserver_web() {
    local backup_file=$(ls -t ${BACKUP_DIR}/yufeng_panel-*.tar.gz 2>/dev/null | head -1)
    if [ -z "$backup_file" ]; then
        backup_file=$(ls -t ${BACKUP_DIR}/mdserver-web-*.tar.gz 2>/dev/null | head -1)
    fi
    if [ -z "$backup_file" ]; then
        log_error "未找到面板备份文件!"
        return 1
    fi
    log_info "从备份恢复: $backup_file"
    stop_panel
    rm -rf ${PANEL_DIR}/web ${PANEL_DIR}/panel_task.py ${PANEL_DIR}/panel_tools.py
    tar -xzf "$backup_file" -C /www/server
    local db_bak=$(ls -t ${BACKUP_DIR}/system.db.*.bak 2>/dev/null | head -1)
    if [ -n "$db_bak" ]; then
        cp "$db_bak" ${PANEL_DIR}/data/system.db
    fi
    start_panel
    log_info "回滚完成!"
}

rollback_bt_panel() {
    local backup_file=$(ls -t ${BACKUP_DIR}/bt-panel-*.tar.gz 2>/dev/null | head -1)
    if [ -z "$backup_file" ]; then
        log_error "未找到宝塔面板备份文件!"
        return 1
    fi
    log_info "从备份恢复宝塔面板: $backup_file"

    # 停止 bt_simple
    stop_panel

    # 清理 bt_simple 安装（如果存在）
    if [ -d ${PANEL_DIR} ]; then
        rm -rf ${PANEL_DIR}
    fi

    # 恢复宝塔目录（从 .bak 目录恢复）
    local bak_dir=$(ls -td ${BT_DIR}.bak.* 2>/dev/null | head -1)
    if [ -n "$bak_dir" ] && [ -d "$bak_dir" ]; then
        mv "$bak_dir" ${BT_DIR}
        log_info "已恢复宝塔面板目录: $bak_dir -> ${BT_DIR}"
    else
        # 从 tar 包恢复
        tar -xzf "$backup_file" -C /www/server
    fi

    # 恢复宝塔自启并启动
    if command -v systemctl >/dev/null 2>&1; then
        systemctl enable bt 2>/dev/null
    fi
    if [ -f /etc/init.d/bt ]; then
        /etc/init.d/bt start
    fi

    # 移除 mw/bs 命令链接
    rm -f /usr/bin/mw 2>/dev/null
    rm -f /usr/bin/bs 2>/dev/null

    log_info "宝塔面板回滚完成!"
}

# =====================================================================
# 服务控制
# =====================================================================
stop_panel() {
    # 停止 yufeng_panel 或 mdserver-web
    if [ -f /usr/bin/yf ]; then
        yf stop 2>/dev/null
    elif [ -f /usr/bin/mw ]; then
        mw 2 2>/dev/null
    fi

    if [ -f /etc/init.d/yf ]; then
        /etc/init.d/yf stop 2>/dev/null
    elif [ -f /etc/init.d/mw ]; then
        /etc/init.d/mw stop 2>/dev/null
    fi
    # 停止宝塔
    if [ -f /etc/init.d/bt ]; then
        /etc/init.d/bt stop 2>/dev/null
    fi
    # 强杀残留
    ps aux | grep -E 'gunicorn.*app:app|panel_task\.py' | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null
    sleep 1
}

start_panel() {
    if [ -f /usr/bin/yf ]; then
        yf start
    elif [ -f /usr/bin/mw ]; then
        mw 3
    elif [ -f /etc/init.d/yf ]; then
        /etc/init.d/yf start
    elif [ -f /etc/init.d/mw ]; then
        /etc/init.d/mw start
    elif [ -f ${PANEL_DIR}/cli.sh ]; then
        cd ${PANEL_DIR} && bash cli.sh start
    fi
}

# =====================================================================
# 代码下载
# =====================================================================
download_code() {
    log_info "下载 bt_simple 代码..."
    rm -rf /tmp/bt_simple_deploy

    # 如果用户没有显式指定分支，并且当前是默认的 master，则尝试自动获取最新 release
    if [ "$GIT_BRANCH" = "master" ] && [ -z "${BT_SIMPLE_BRANCH:-}" ]; then
        log_info "尝试获取最新正式版 (Release) Tag..."
        local latest_tag=""
        if type github_api_get >/dev/null 2>&1; then
            latest_tag=$(github_api_get "https://api.github.com/repos/clhome/bt_simple/releases/latest" 2>/dev/null | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
        else
            latest_tag=$(curl -s -m 5 "https://api.github.com/repos/clhome/bt_simple/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
        fi
        
        if [ -n "$latest_tag" ]; then
            export GIT_BRANCH="$latest_tag"
            log_info "获取成功，本次将从正式版 Release (${GIT_BRANCH}) 下载代码"
        else
            log_warn "获取最新 Release 失败，将回退使用 master 分支"
        fi
    fi

    local download_url=$(get_github_url ${GIT_REPO})
    local clone_ret=0

    if type github_clone >/dev/null 2>&1; then
        log_info "正在使用统一克隆库从 ${GIT_REPO} 拉取代码..."
        github_clone "/tmp/bt_simple_deploy" "${GIT_REPO}" "${GIT_BRANCH}"
        clone_ret=$?
    else
        if command -v git >/dev/null 2>&1; then
            log_info "正在从 ${download_url} 拉取代码..."
            git -c advice.detachedHead=false -c http.version=HTTP/1.1 clone --depth 1 -b ${GIT_BRANCH} ${download_url} /tmp/bt_simple_deploy 2>&1 | tee -a $LOG_FILE
            clone_ret=$?
        else
            log_error "git 未安装，请先安装 git"
            exit 1
        fi
    fi

    # 双重安全锁：校验退出码，以及核心业务文件夹 'web' 是否被 Git 成功签出
    if [ $clone_ret -ne 0 ] || [ ! -d /tmp/bt_simple_deploy/web ]; then
        log_error "代码下载失败或中途断流，请检查网络或仓库地址: ${GIT_REPO}"
        rm -rf /tmp/bt_simple_deploy 2>/dev/null
        exit 1
    fi

    # 如果用户明确指定了 master 分支（尝鲜预览版），则主动为版本号同步最新 Release 编号并打上 dev 后缀标签
    if [ "$BT_SIMPLE_BRANCH" = "master" ] && [ -f /tmp/bt_simple_deploy/web/version.py ]; then
        log_info "正在为开发预览版注入 -dev 版本标识..."
        
        # 尝试获取远端最新正式版的版本号，让开发版基于最新正式版号 + dev
        local latest_tag=""
        if type github_api_get >/dev/null 2>&1; then
            latest_tag=$(github_api_get "https://api.github.com/repos/clhome/bt_simple/releases/latest" 2>/dev/null | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
        else
            latest_tag=$(curl -s -m 5 "https://api.github.com/repos/clhome/bt_simple/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
        fi
        
        if [ -n "$latest_tag" ]; then
            local clean_ver=$(echo "$latest_tag" | sed 's/^v//')
            local new_rel=$(echo "$clean_ver" | awk -F. '{print $1}')
            local new_rev=$(echo "$clean_ver" | awk -F. '{print $2}')
            local new_smv=$(echo "$clean_ver" | awk -F. '{print $3}' | awk -F- '{print $1}')
            if [ -n "$new_rel" ] && [ -n "$new_rev" ] && [ -n "$new_smv" ]; then
                sed -i "s/^[[:space:]]*APP_RELEASE[[:space:]]*=.*/APP_RELEASE = $new_rel/" /tmp/bt_simple_deploy/web/version.py
                sed -i "s/^[[:space:]]*APP_REVISION[[:space:]]*=.*/APP_REVISION = $new_rev/" /tmp/bt_simple_deploy/web/version.py
                sed -i "s/^[[:space:]]*APP_SMALL_VERSION[[:space:]]*=.*/APP_SMALL_VERSION = $new_smv/" /tmp/bt_simple_deploy/web/version.py
            fi
        fi
        sed -i "s/^[[:space:]]*APP_SUFFIX[[:space:]]*=.*/APP_SUFFIX = 'dev'/" /tmp/bt_simple_deploy/web/version.py
    fi

    log_info "代码下载完成"
}

# 将代码部署到面板目录
deploy_code() {
    local src="/tmp/bt_simple_deploy"
    log_info "部署代码到 ${PANEL_DIR} ..."

    # 核心代码目录及文档
    local CODE_ITEMS="web panel_task.py panel_tools.py cli.sh scripts route version.py branding.py requirements.txt README.md RELEASE_TEMPLATE.md"
    for item in $CODE_ITEMS; do
        if [ -e ${src}/${item} ]; then
            rm -rf ${PANEL_DIR}/${item}
            cp -rf ${src}/${item} ${PANEL_DIR}/
        fi
    done

    # 安全地同步更新插件管理器
    if [ -d "${src}/plugins" ]; then
        log_info "安全地更新插件管理器..."
        # 逐个循环仓库中的插件，仅覆盖同步存在的插件，防止删掉用户自定义的其他插件
        for plugin_path in ${src}/plugins/*; do
            if [ -d "$plugin_path" ]; then
                local plugin_name=$(basename "$plugin_path")
                mkdir -p ${PANEL_DIR}/plugins/${plugin_name}
                cp -rf ${plugin_path}/* ${PANEL_DIR}/plugins/${plugin_name}/
            fi
        done
        log_info "插件管理器更新完成"
    fi

    # 确保目录权限
    chmod 755 ${PANEL_DIR}/data 2>/dev/null
    chmod 755 ${PANEL_DIR}/cli.sh 2>/dev/null

    rm -rf /tmp/bt_simple_deploy
    log_info "代码部署完成"
}

# =====================================================================
# 场景1: 全新安装
# =====================================================================
fresh_install() {
    log_info "===== 开始全新安装 bt_simple ====="

    # 如果检测到旧版的真正 mdserver-web 目录存在，且它不是一个软链接
    if [ -d "/www/server/mdserver-web" ] && [ ! -L "/www/server/mdserver-web" ]; then
        log_warn "检测到旧版 mdserver-web 面板安装目录！"
        log_info "正在自动将其重命名为 yufeng_panel 保证安装正常..."

        # 停止旧面板服务
        if [ -f "/etc/init.d/mw" ]; then
            /etc/init.d/mw stop >/dev/null 2>&1
        elif [ -f "/etc/init.d/yf" ]; then
            /etc/init.d/yf stop >/dev/null 2>&1
        fi

        # 安全重命名物理目录
        if [ -d "/www/server/yufeng_panel" ]; then
            cp -af /www/server/mdserver-web/* /www/server/yufeng_panel/
            rm -rf /www/server/mdserver-web
        else
            mv /www/server/mdserver-web /www/server/yufeng_panel
        fi

        if [ -d "/www/server/yufeng_panel" ]; then
            log_info "物理目录迁移成功: mdserver-web -> yufeng_panel"
            # 创建向下兼容的软链接
            ln -sf /www/server/yufeng_panel /www/server/mdserver-web
            log_info "已创建兼容性软链接: mdserver-web -> yufeng_panel"

            # ⚠️ 关键防御保护：若在全新安装过程中检测到并迁移了旧数据，
            # 必须直接重定向调用 migrate_from_mw 函数，以防后续的 fresh_install 流程执行 rm -rf 清空该目录！
            log_info "检测到老版本数据已自动重命名，全新安装程序将自动切换为【迁移升级模式】..."
            migrate_from_mw
            exit 0
        else
            log_error "目录迁移失败，请检查权限！"
            exit 1
        fi
    fi

    # 创建目录结构
    if id www >/dev/null 2>&1; then
        log_info "www 用户已存在"
    else
        groupadd www
        useradd -g www -s /usr/sbin/nologin www
    fi

    mkdir -p /www/server
    mkdir -p /www/wwwroot
    mkdir -p /www/wwwlogs
    mkdir -p /www/backup/database
    mkdir -p /www/backup/site

    # 下载代码
    download_code
    if [ -d "${PANEL_DIR}" ]; then
        rm -rf "${PANEL_DIR}"
    fi
    mv /tmp/bt_simple_deploy ${PANEL_DIR}
    
    if [ ! -L "$LEGACY_PANEL_DIR" ]; then
        ln -sf ${PANEL_DIR} ${LEGACY_PANEL_DIR}
    fi
    
    mkdir -p ${PANEL_DIR}/logs
    mkdir -p ${PANEL_DIR}/data

    # 安装 acme.sh
    install_acme

    # 安装系统依赖
    log_info "安装系统依赖（可能需要几分钟）..."
    setup_china_git_config
    cd ${PANEL_DIR} && bash scripts/install/${OSNAME}.sh 2>&1 | tee -a $LOG_FILE

    # 启动服务
    cd ${PANEL_DIR} && bash cli.sh start
    sleep 3

    # 等待 init 脚本生成
    local n=0
    while [ ! -f /etc/rc.d/init.d/yf ] && [ $n -lt 30 ]; do
        sleep 1
        let n+=1
    done

    # 配置系统服务
    if [ -f /etc/rc.d/init.d/yf ]; then
        bash /etc/rc.d/init.d/yf stop
        bash /etc/rc.d/init.d/yf start
    fi

    # 创建 mw/bs 命令
    if [ ! -e /usr/bin/yf ] && [ -f /etc/rc.d/init.d/yf ]; then
        ln -sf /etc/rc.d/init.d/yf /usr/bin/yf
    fi
    if [ ! -e /usr/bin/mw ] && [ -f /etc/rc.d/init.d/yf ]; then
        ln -sf /etc/rc.d/init.d/yf /usr/bin/mw
    fi
    if [ ! -e /usr/bin/bs ] && [ -f /etc/rc.d/init.d/yf ]; then
        ln -sf /etc/rc.d/init.d/yf /usr/bin/bs
    fi

    # 开放面板端口
    open_panel_port

    # 生成 12 位随机密码并设置
    local rand_pass=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 12 | head -n 1)
    if [ -f ${PANEL_DIR}/panel_tools.py ]; then
        cd ${PANEL_DIR} && python3 panel_tools.py panel "$rand_pass" > /dev/null 2>&1
        echo "$rand_pass" > ${PANEL_DIR}/data/default.pl
    fi

    # 设置面板版本号
    set_panel_version

    disable_upstream_update
    show_panel_info "$rand_pass"
    log_info "===== 全新安装完成 ====="
}

# =====================================================================
# 场景2: 从 mdserver-web 迁移
# =====================================================================
migrate_from_mw() {
    if $HAS_YF; then
        log_info "===== 升级 yufeng_panel 面板 ====="
        echo -e "${YELLOW}准备升级 yufeng_panel 面板${PLAIN}"
        echo -e "当前面板信息:"
        yf 10 2>/dev/null || bs 10 2>/dev/null || mw 10 2>/dev/null
        echo ""
    else
        log_info "===== 从 mdserver-web 迁移到 bt_simple ====="
        echo -e "${YELLOW}检测到已安装 mdserver-web 面板${PLAIN}"
        echo -e "当前面板信息:"
        mw 10 2>/dev/null
        echo ""

        echo -e "${RED}注意事项:${PLAIN}"
        echo "  1. 迁移仅替换面板 Python 代码，不影响已部署的网站和数据库"
        echo "  2. data/ plugins/ ssl/ 等数据目录将完整保留"
        echo "  3. 如迁移失败可一键回滚到原版"
        echo ""

        if ! confirm "是否确认【升级】或者从 mdserver-web 迁移到 bt_simple?"; then
            log_info "用户取消迁移"
            return
        fi
    fi

    # 备份
    backup_mdserver_web

    # 停止服务
    log_info "停止面板服务..."
    stop_panel

    # PostgreSQL 路径兼容: md面板使用 postgresql，bt_simple 期望 pgsql
    if [ -d "/www/server/postgresql" ] && [ ! -d "/www/server/pgsql" ]; then
        log_info "检测到 /www/server/postgresql 目录，需重命名为 pgsql 以兼容新面板..."
        # 先停止 PostgreSQL 进程，否则重命名会失败
        if systemctl is-active postgresql >/dev/null 2>&1; then
            log_info "正在停止 PostgreSQL 服务..."
            systemctl stop postgresql
            sleep 2
        fi
        # 兜底: 确保所有 postgres 进程已终止
        if pgrep -x postgres >/dev/null 2>&1; then
            log_warn "仍有残留 postgres 进程，强制终止..."
            pkill -9 postgres 2>/dev/null
            sleep 1
        fi
        # 重命名目录
        mv /www/server/postgresql /www/server/pgsql
        if [ -d "/www/server/pgsql" ]; then
            log_info "目录重命名成功: postgresql -> pgsql"
            # 创建软链接兜底，防止其他配置或脚本硬编码了旧路径
            ln -sf /www/server/pgsql /www/server/postgresql
            log_info "已创建兼容软链接: postgresql -> pgsql"
        else
            log_error "目录重命名失败，请手动处理: mv /www/server/postgresql /www/server/pgsql"
        fi
    fi

    if [ -d "$LEGACY_PANEL_DIR" ] && [ ! -L "$LEGACY_PANEL_DIR" ]; then
        log_info "迁移物理目录 ${LEGACY_PANEL_DIR} -> ${PANEL_DIR}..."
        mv ${LEGACY_PANEL_DIR} ${PANEL_DIR}
        ln -sf ${PANEL_DIR} ${LEGACY_PANEL_DIR}
        log_info "已创建向下兼容的软链接: ${LEGACY_PANEL_DIR} -> ${PANEL_DIR}"
    fi

    # 下载并部署
    download_code
    deploy_code

    # 更新数据库存储路径 (Section 7.1 step 8)
    if [ -f ${PANEL_DIR}/data/panel.db ]; then
        log_info "更新 SQLite 数据库中的路径参数..."
        python3 -c "
import sqlite3
db_path = '${PANEL_DIR}/data/panel.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute(\"UPDATE option SET value = REPLACE(value, '/www/server/mdserver-web', '/www/server/yufeng_panel') WHERE value LIKE '%mdserver-web%'\")
cursor.execute(\"UPDATE crontab SET echo = REPLACE(echo, '/www/server/mdserver-web', '/www/server/yufeng_panel') WHERE echo LIKE '%mdserver-web%'\")
cursor.execute(\"UPDATE crontab SET sBody = REPLACE(sBody, '/www/server/mdserver-web', '/www/server/yufeng_panel') WHERE sBody LIKE '%mdserver-web%'\")
conn.commit()
conn.close()
" 2>&1 | tee -a $LOG_FILE
    fi

    # 递归替换 Nginx / OpenResty 的配置项 (Section 7.1 step 9)
    log_info "更新 Web 服务配置文件路径..."
    if [ -d "/www/server/nginx/conf/" ]; then
        find /www/server/nginx/conf/ -type f -name "*.conf" -exec sed -i 's|/www/server/mdserver-web|/www/server/yufeng_panel|g' {} + 2>/dev/null
    fi
    if [ -d "/www/server/openresty/" ]; then
        find /www/server/openresty/ -type f -name "*.conf" -exec sed -i 's|/www/server/mdserver-web|/www/server/yufeng_panel|g' {} + 2>/dev/null
    fi

    # 更新 cron 任务中可能残留的废弃模块调用
    log_info "更新系统计划任务脚本中的废弃 Python 调用..."
    if [ -d "/www/server/cron/" ]; then
        find /www/server/cron/ -type f -exec sed -i 's/import core.mw as mw/import core.yf as yf/g' {} + 2>/dev/null
        find /www/server/cron/ -type f -exec sed -i 's/mw.formatDate()/yf.formatDate()/g' {} + 2>/dev/null
    fi

    # 检查依赖
    log_info "检查 Python 依赖..."
    if [ -f ${PANEL_DIR}/bin/activate ]; then
        cd ${PANEL_DIR} && source bin/activate
        pip3 install --disable-pip-version-check --no-warn-script-location -r requirements.txt 2>&1 | grep -v 'already satisfied' | tee -a $LOG_FILE
        # 强制升级 requests 库以消除可能的 RequestsDependencyWarning 版本冲突警告
        pip3 install --disable-pip-version-check --no-warn-script-location --upgrade requests 2>&1 | tee -a $LOG_FILE
    fi

    # 启动
    start_panel
    sleep 2
    disable_upstream_update

    # 验证
    log_info "验证面板状态..."
    sleep 3
    if ps aux | grep 'gunicorn.*app:app' | grep -v grep >/dev/null 2>&1; then
        log_info "面板服务已正常启动"
    else
        log_warn "面板可能未正常启动，请检查日志: tail -50 ${PANEL_DIR}/logs/panel_error.log"
        echo ""
        if confirm "是否回滚到原版 mdserver-web?"; then
            rollback_mdserver_web
            return
        fi
    fi

    # 如果缺少 default.pl（例如之前升级失败丢失），则重新生成密码
    local rand_pass=""
    if [ ! -f ${PANEL_DIR}/data/default.pl ]; then
        rand_pass=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 12 | head -n 1)
        if [ -f ${PANEL_DIR}/panel_tools.py ]; then
            cd ${PANEL_DIR} && python3 panel_tools.py panel "$rand_pass" > /dev/null 2>&1
            echo "$rand_pass" > ${PANEL_DIR}/data/default.pl
        fi
        log_info "检测到缺少默认密码文件，已重新生成面板密码"
    fi

    # 设置面板版本号
    set_panel_version

    show_panel_info "$rand_pass"
    echo ""
    log_info "===== mdserver-web 迁移完成 ====="
    echo -e "${YELLOW}提示: 如需回滚请执行: bash $0 rollback_mw${PLAIN}"
}

# =====================================================================
# 场景3辅助: 扫描宝塔安装的软件及版本
# =====================================================================
scan_bt_installed_software() {
    log_info "正在分析原宝塔面板已安装软件..."
    
    local mysql_ver=""
    local redis_ver=""
    local postgres_ver=""
    local nginx_ver=""
    local php_vers=""

    # 1. 检测 MySQL
    if [ -d "/www/server/mysql" ]; then
        if [ -f "/www/server/mysql/version.pl" ]; then
            mysql_ver=$(cat /www/server/mysql/version.pl | tr -d '\r\n ')
        else
            mysql_ver="5.7"
        fi
        log_info "检测到宝塔 MySQL 版本: ${mysql_ver}"
    fi

    # 2. 检测 Redis
    if [ -d "/www/server/redis" ]; then
        if [ -f "/www/server/redis/version.pl" ]; then
            redis_ver=$(cat /www/server/redis/version.pl | tr -d '\r\n ')
        else
            redis_ver="7.2.2"
        fi
        log_info "检测到宝塔 Redis 版本: ${redis_ver}"
    fi

    # 3. 检测 PostgreSQL
    if [ -d "/www/server/postgresql" ]; then
        if [ -f "/www/server/postgresql/version.pl" ]; then
            postgres_ver=$(cat /www/server/postgresql/version.pl | tr -d '\r\n ')
        else
            postgres_ver="16"
        fi
        log_info "检测到宝塔 PostgreSQL 版本: ${postgres_ver}"
    fi

    # 4. 检测 Nginx / OpenResty
    if [ -d "/www/server/nginx" ]; then
        if [ -f "/www/server/nginx/version.pl" ]; then
            nginx_ver=$(cat /www/server/nginx/version.pl | tr -d '\r\n ')
        else
            nginx_ver="1.22.1"
        fi
        log_info "检测到宝塔 Nginx/OpenResty 版本: ${nginx_ver}"
    fi

    # 5. 检测 PHP
    if [ -d "/www/server/php" ]; then
        for php_dir in /www/server/php/*; do
            if [ -d "$php_dir" ]; then
                local php_v=$(basename "$php_dir")
                if [[ "$php_v" =~ ^[0-9]+$ ]]; then
                    if [ -z "$php_vers" ]; then
                        php_vers="\"${php_v}\""
                    else
                        php_vers="${php_vers}, \"${php_v}\""
                    fi
                fi
            fi
        done
        log_info "检测到宝塔 PHP 版本: ${php_vers}"
    fi

    # 拼装为 JSON 文件
    mkdir -p /tmp
    cat > /tmp/bt_migrated_software.json <<EOF
{
  "mysql": "${mysql_ver}",
  "redis": "${redis_ver}",
  "postgresql": "${postgres_ver}",
  "openresty": "${nginx_ver}",
  "php": [${php_vers}]
}
EOF
    log_info "已保存宝塔软件分析结果到 /tmp/bt_migrated_software.json"
}

# =====================================================================
# 场景3: 从宝塔面板迁移
# =====================================================================
migrate_from_bt() {
    log_info "===== 从宝塔面板迁移到 bt_simple ====="

    echo -e "${YELLOW}检测到已安装宝塔面板${PLAIN}"
    echo -e "${RED}重要提醒:${PLAIN}"
    echo "  1. 宝塔面板与 bt_simple 是不同架构，数据库/配置不通用"
    echo "  2. 迁移后原宝塔面板将被停止（不删除），bt_simple 全新安装"
    echo "  3. 已通过宝塔安装的软件将被隔离备份，并在迁移后自动重新安装相同版本"
    echo "  4. 迁移完成后您可以进入web管理页后在【面板设置->数据库迁移】中操作，也可以通过 'bs migrate_restore'命令行操作恢复原有的数据库数据"
    echo "  5. /www/wwwroot 下的网站文件完整保留"
    echo ""
    echo -e "${YELLOW}迁移后将保留的内容:${PLAIN}"
    echo "  ✅ /www/wwwroot/     - 网站文件"
    echo "  ✅ /www/backup/       - 备份文件"
    echo ""
    echo -e "${YELLOW}重构与恢复的内容:${PLAIN}"
    echo "  ⚠️  面板软件环境（会后台自动拉起重新安装，并在完成后通过指令还原数据）"
    echo "  ⚠️  计划任务"
    echo "  ⚠️  面板账号密码（新面板会生成新的）"
    echo ""

    if ! confirm "是否确认从宝塔面板迁移到 bt_simple? (宝塔面板将被停止但保留)"; then
        log_info "用户取消迁移"
        return
    fi

    # 备份宝塔面板
    backup_bt_panel

    # 分析宝塔已安装软件
    scan_bt_installed_software

    # 停止宝塔
    log_info "停止宝塔面板服务..."
    if [ -f /etc/init.d/bt ]; then
        /etc/init.d/bt stop
    fi
    # 禁用宝塔自启
    if command -v systemctl >/dev/null 2>&1; then
        systemctl disable bt 2>/dev/null
    fi

    # 重命名宝塔目录（保留但不占用路径）
    if [ -d ${BT_DIR} ]; then
        mv ${BT_DIR} ${BT_DIR}.bak.${TIMESTAMP}
        log_info "宝塔面板已移至: ${BT_DIR}.bak.${TIMESTAMP}"
    fi

    # 安全关闭数据服务以确保进行干净的离线备份（Clean Shutdown）
    log_info "正在安全停止各数据服务以确保数据完整无脏页残留..."
    if [ -f /etc/init.d/mysqld ]; then
        /etc/init.d/mysqld stop
        sleep 2
    fi
    if [ -f /etc/init.d/redis ]; then
        /etc/init.d/redis stop
        sleep 1
    fi
    if [ -f /etc/init.d/pgsql ]; then
        /etc/init.d/pgsql stop
        sleep 1
    fi

    # 备份隔离原本宝塔软件安装目录，避免判定冲突
    log_info "正在隔离备份原本的宝塔软件目录以避免环境冲突..."
    if [ -d "/www/server/mysql" ]; then
        [ -d "/www/server/mysql_bt_bak" ] && rm -rf /www/server/mysql_bt_bak
        mv /www/server/mysql /www/server/mysql_bt_bak
        log_info "已备份 MySQL 目录: /www/server/mysql -> /www/server/mysql_bt_bak"
    fi
    if [ -d "/www/server/data" ]; then
        [ -d "/www/server/data_bt_bak" ] && rm -rf /www/server/data_bt_bak
        mv /www/server/data /www/server/data_bt_bak
        log_info "已备份 MySQL 数据目录: /www/server/data -> /www/server/data_bt_bak"
    fi
    if [ -d "/www/server/redis" ]; then
        [ -d "/www/server/redis_bt_bak" ] && rm -rf /www/server/redis_bt_bak
        mv /www/server/redis /www/server/redis_bt_bak
        log_info "已备份 Redis 目录: /www/server/redis -> /www/server/redis_bt_bak"
    fi
    if [ -d "/www/server/postgresql" ]; then
        [ -d "/www/server/postgresql_bt_bak" ] && rm -rf /www/server/postgresql_bt_bak
        mv /www/server/postgresql /www/server/postgresql_bt_bak
        log_info "已备份 PostgreSQL 目录: /www/server/postgresql -> /www/server/postgresql_bt_bak"
    fi
    if [ -d "/www/server/php" ]; then
        [ -d "/www/server/php_bt_bak" ] && rm -rf /www/server/php_bt_bak
        mv /www/server/php /www/server/php_bt_bak
        log_info "已备份 PHP 目录: /www/server/php -> /www/server/php_bt_bak"
    fi
    if [ -d "/www/server/nginx" ]; then
        [ -d "/www/server/nginx_bt_bak" ] && rm -rf /www/server/nginx_bt_bak
        mv /www/server/nginx /www/server/nginx_bt_bak
        log_info "已备份 Nginx/OpenResty 目录: /www/server/nginx -> /www/server/nginx_bt_bak"
    fi

    # 保留 /www 基础目录结构（宝塔已创建）
    mkdir -p /www/server
    mkdir -p /www/wwwroot
    mkdir -p /www/wwwlogs
    mkdir -p /www/backup/database
    mkdir -p /www/backup/site

    # 创建 www 用户（宝塔通常已创建）
    if ! id www >/dev/null 2>&1; then
        groupadd www
        useradd -g www -s /usr/sbin/nologin www
    fi

    # 全新安装 bt_simple
    setup_china_git_config
    download_code
    if [ -d "${PANEL_DIR}" ]; then
        rm -rf "${PANEL_DIR}"
    fi
    mv /tmp/bt_simple_deploy ${PANEL_DIR}
    
    if [ ! -L "$LEGACY_PANEL_DIR" ]; then
        ln -sf ${PANEL_DIR} ${LEGACY_PANEL_DIR}
    fi
    
    mkdir -p ${PANEL_DIR}/logs
    mkdir -p ${PANEL_DIR}/data

    # 写入迁移软件标记文件
    if [ -f "/tmp/bt_migrated_software.json" ]; then
        cp /tmp/bt_migrated_software.json ${PANEL_DIR}/data/bt_migrated_software.json
        rm -f /tmp/bt_migrated_software.json
        log_info "已保存软件迁移数据至 ${PANEL_DIR}/data/bt_migrated_software.json"
    fi

    # 安装 acme.sh
    install_acme

    # 安装依赖
    log_info "安装系统依赖..."

    cd ${PANEL_DIR} && bash scripts/install/${OSNAME}.sh 2>&1 | tee -a $LOG_FILE

    # 启动
    cd ${PANEL_DIR} && bash cli.sh start
    sleep 3

    local n=0
    while [ ! -f /etc/rc.d/init.d/yf ] && [ $n -lt 30 ]; do
        sleep 1
        let n+=1
    done

    if [ -f /etc/rc.d/init.d/yf ]; then
        bash /etc/rc.d/init.d/yf stop
        bash /etc/rc.d/init.d/yf start
    fi

    if [ ! -e /usr/bin/yf ] && [ -f /etc/rc.d/init.d/yf ]; then
        ln -sf /etc/rc.d/init.d/yf /usr/bin/yf
    fi
    if [ ! -e /usr/bin/mw ] && [ -f /etc/rc.d/init.d/yf ]; then
        ln -sf /etc/rc.d/init.d/yf /usr/bin/mw
    fi
    if [ ! -e /usr/bin/bs ] && [ -f /etc/rc.d/init.d/yf ]; then
        ln -sf /etc/rc.d/init.d/yf /usr/bin/bs
    fi

    # 开放面板端口
    open_panel_port

    # 生成 12 位随机密码并设置
    local rand_pass=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 12 | head -n 1)
    if [ -f ${PANEL_DIR}/panel_tools.py ]; then
        cd ${PANEL_DIR} && python3 panel_tools.py panel "$rand_pass" > /dev/null 2>&1
        echo "$rand_pass" > ${PANEL_DIR}/data/default.pl
    fi

    # 设置面板版本号
    set_panel_version

    disable_upstream_update

    # 尝试导入宝塔站点
    local bt_db_bak_path="${BT_DIR}.bak.${TIMESTAMP}/data/db/site.db"
    if [ -f "${bt_db_bak_path}" ]; then
        if [ "$SILENT_MODE" = "true" ]; then
            log_info "静默模式，已自动跳过宝塔站点导入。"
        else
            echo -e "\n${BOLD}${YELLOW}是否需要导入宝塔面板站点到御风面板数据库 (y/n)?${PLAIN}"
            local import_choice="n"
            if [ -t 0 ]; then
                read -p "请输入 [y/n]: " import_choice
            else
                read -p "请输入 [y/n]: " import_choice < /dev/tty 2>/dev/null || import_choice="n"
            fi

            if [ "$import_choice" = "y" ] || [ "$import_choice" = "Y" ]; then
                log_info "正在导入宝塔站点到御风面板数据库..."
                cd ${PANEL_DIR} && python3 panel_tools.py import_bt_sites "${bt_db_bak_path}"
            else
                log_info "已跳过宝塔站点导入。"
            fi
        fi
    fi

    show_panel_info "$rand_pass"

    echo ""
    log_info "===== 宝塔面板迁移完成 ====="
    echo -e "${YELLOW}提示:${PLAIN}"
    echo "  1. 原宝塔面板备份在: ${BT_DIR}.bak.${TIMESTAMP}"
    echo "  2. 如需回滚请执行: bash $0 rollback_bt"
    echo "  3. 第一次使用御风面板请使用【bs 11】命令初始化密码"
}


# =====================================================================
# 检测并更新版本
# =====================================================================
check_version_and_update() {
    local local_ver="0.0.0"
    if [ -f ${PANEL_DIR}/.version ]; then
        local_ver=$(cat ${PANEL_DIR}/.version | sed 's/^v//' | tr -d '\r\n ')
    fi

    log_info "正在检查远端最新版本..."
    local exact_tag=""
    if type github_api_get >/dev/null 2>&1; then
        exact_tag=$(github_api_get "https://api.github.com/repos/clhome/bt_simple/releases/latest" 2>/dev/null | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
    else
        exact_tag=$(curl -s -m 5 "https://api.github.com/repos/clhome/bt_simple/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
    fi

    if [ -z "$exact_tag" ]; then
        log_warn "获取远端版本号失败（可能受限于国内网络），将直接执行强行覆盖升级..."
        migrate_from_mw
        return 0
    fi

    local remote_ver=$(echo "$exact_tag" | sed 's/^v//')
    log_info "当前本地版本: ${local_ver} | 远端最新版本: ${remote_ver}"

    if [ "$local_ver" = "$remote_ver" ]; then
        log_info "已经是最新版本，无需升级。"
        return 0
    fi

    # 比较版本号
    local winner=$(echo -e "${local_ver}\n${remote_ver}" | sort -V | tail -n 1)
    if [ "$winner" = "$remote_ver" ] && [ "$local_ver" != "$remote_ver" ]; then
        log_info "检测到新版本，开始静默升级..."
        export GIT_BRANCH="$exact_tag"
        export IS_UPDATING_TO_LATEST="true"
        export LATEST_REMOTE_VER="${remote_ver}"
        migrate_from_mw
    else
        log_info "本地版本已等于或高于远端版本，跳过升级。"
    fi
}

# =====================================================================
# 禁用上游自动更新

# =====================================================================
disable_upstream_update() {
    local yf_script="/etc/rc.d/init.d/yf"
    if [ -f "$yf_script" ]; then
        # 检查是否已禁用
        if grep -q "自动更新已禁用" "$yf_script" 2>/dev/null; then
            return
        fi
        # 在 mw_update 函数中插入禁用逻辑
        sed -i '/^yf_update()/,/^}/{
            /^yf_update()/!{
                /^{/a\    echo "自动更新已禁用(bt_simple fork)，请手动从仓库拉取更新"; return 0
            }
        }' "$yf_script" 2>/dev/null
        log_info "已禁用上游自动更新"
    fi
}

# =====================================================================
# 防火墙开放面板端口
# =====================================================================
open_panel_port() {
    local port=7200
    if [ -f ${PANEL_DIR}/data/port.pl ]; then
        port=$(cat ${PANEL_DIR}/data/port.pl)
    fi
    log_info "开放面板端口: ${port}"

    if command -v ufw >/dev/null 2>&1; then
        ufw allow ${port}/tcp >/dev/null 2>&1
    elif command -v firewall-cmd >/dev/null 2>&1; then
        firewall-cmd --permanent --zone=public --add-port=${port}/tcp >/dev/null 2>&1
        firewall-cmd --reload >/dev/null 2>&1
    fi
}

# =====================================================================
# 显示面板信息
# =====================================================================
show_panel_info() {
    local force_pass="$1"
    local version=""
    if [ -f ${PANEL_DIR}/.version ]; then
        version="【$(cat ${PANEL_DIR}/.version | sed 's/^v//')】"
    fi
    echo ""
    echo -e "=================================================================="
    echo -e "${GREEN}${BOLD}${version} 御风面板安装/迁移完成!${PLAIN}"
    echo -e "=================================================================="
    
    if [ -f /usr/bin/mw ] || [ -f /usr/bin/bs ]; then
        # 获取默认信息
        local info=""
        if [ -f /usr/bin/bs ]; then
            info=$(bs 10 2>/dev/null)
        else
            info=$(mw 10 2>/dev/null)
        fi

        if [ -n "$force_pass" ]; then
            # 如果传入了强制显示的密码，则替换掉 mask 后的密码输出
            echo "$info" | sed "s/\*-password.*/|-password: $force_pass/"
        else
            echo "$info"
        fi
    elif [ -f ${PANEL_DIR}/data/port.pl ]; then
        local port=$(cat ${PANEL_DIR}/data/port.pl 2>/dev/null)
        echo -e "面板端口: ${port:-7200}"
        if [ -f ${PANEL_DIR}/data/default.pl ]; then
            echo -e "默认密码: $(cat ${PANEL_DIR}/data/default.pl)"
        fi
    fi
    echo -e "=================================================================="
    echo -e "日志文件: ${LOG_FILE}"
    echo -e "=================================================================="

    
    local report_res=$(curl -s -m 10 --location --request GET 'https://www.yftec.top/index.php/api/deploy/report' 2>/dev/null)
    if [ -n "$report_res" ]; then
        local user_number=$(echo "$report_res" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('data', {}).get('user_number', ''))" 2>/dev/null)
        if [ -n "$user_number" ]; then
            echo -e "${GREEN}您是御风面板第${user_number}位用户，衢州御风科技与您智领未来，共筑匠心${PLAIN}"
            echo -e "=================================================================="
        fi
    fi
}

# =====================================================================
# 主入口
# =====================================================================
main() {
    check_root
    check_architecture
    check_system_resources
    check_os_version
    detect_os
    install_basic_deps
    detect_environment

    mkdir -p $BACKUP_DIR
    echo "===== bt_simple deploy $(date) =====" >> $LOG_FILE

    # 处理 flag 参数（如 -cn），使其不与子命令互斥
    while [[ "${1:-}" == -* ]]; do
        case "$1" in
            -cn) FORCE_CN=true; shift ;;
            *) break ;;
        esac
    done

    # 命令行参数处理
    case "${1:-}" in
        update)
            SILENT_MODE=true
            check_version_and_update
            exit 0
            ;;
        force_update)
            SILENT_MODE=true
            migrate_from_mw
            exit 0
            ;;
        install)
            SILENT_MODE=true
            fresh_install
            exit 0
            ;;
        rollback_mw)
            rollback_mdserver_web
            exit 0
            ;;
        rollback_bt)
            rollback_bt_panel
            exit 0
            ;;
        uninstall)
            log_warn "卸载功能暂未实现，请手动执行: bash /etc/rc.d/init.d/yf uninstall"
            exit 0
            ;;
    esac

    show_banner

    if $HAS_YF; then
        echo -e "${YELLOW}检测到已安装 yufeng_panel 面板${PLAIN}"
        echo ""
        echo "=================================================================="
        echo -e " ${YELLOW}运维提示：版本降级与环境修复指引${PLAIN}"
        echo " ----------------------------------------------------------------"
        echo " 若当前面板正运行 [开发预览版 (-dev)]，或核心代码出现损坏缺失，"
        echo " 且需要强制切回并锁定至最新的官方稳定发行版 (Stable Release)，"
        echo " 请务必选择下方【 2) 强制覆盖升级 】以重置整个代码仓库。"
        echo "=================================================================="
        echo ""
        echo "  1) 检查并升级 (自动比对稳定版版本)"
        echo "  2) 强制覆盖升级 (不比对版本，适用于环境修复或回退正式版)"
        echo "  3) 强制升级至开发预览版 (拉取 master 最新提交，存在不稳定风险)"
        echo "  4) 取消"
        echo ""
        if [ -t 0 ]; then read -p "请选择 [1-4]: " choice; else read -p "请选择 [1-4]: " choice < /dev/tty 2>/dev/null || choice="4"; fi
        case "$choice" in
            1) check_version_and_update ;;
            2) migrate_from_mw ;;
            3) 
                export BT_SIMPLE_BRANCH="master"
                migrate_from_mw
                ;;
            *) echo "已取消"; exit 0 ;;
        esac
    elif $HAS_BT && $HAS_MW; then
        echo -e "${YELLOW}检测到同时存在宝塔面板和 mdserver-web${PLAIN}"
        echo ""
        echo "  1) 从 mdserver-web 迁移"
        echo "  2) 从宝塔面板迁移"
        echo "  3) 取消"
        echo ""
        if [ -t 0 ]; then read -p "请选择 [1-3]: " choice; else read -p "请选择 [1-3]: " choice < /dev/tty 2>/dev/null || choice="3"; fi
        case "$choice" in
            1) migrate_from_mw ;;
            2) migrate_from_bt ;;
            *) echo "已取消"; exit 0 ;;
        esac
    elif $HAS_MW; then
        echo -e "${YELLOW}检测到已安装 mdserver-web 面板${PLAIN}"
        echo ""
        echo "  1) 确认【升级】或者从 mdserver-web 迁移到 bt_simple"
        echo "  2) 取消"
        echo ""
        if [ -t 0 ]; then read -p "请选择 [1-2]: " choice; else read -p "请选择 [1-2]: " choice < /dev/tty 2>/dev/null || choice="2"; fi
        case "$choice" in
            1) migrate_from_mw ;;
            *) echo "已取消"; exit 0 ;;
        esac
    elif $HAS_BT; then
        echo -e "${YELLOW}检测到已安装宝塔面板${PLAIN}"
        echo ""
        echo "  1) 从宝塔面板迁移到 bt_simple"
        echo "  2) 取消"
        echo ""
        if [ -t 0 ]; then read -p "请选择 [1-2]: " choice; else read -p "请选择 [1-2]: " choice < /dev/tty 2>/dev/null || choice="2"; fi
        case "$choice" in
            1) migrate_from_bt ;;
            *) echo "已取消"; exit 0 ;;
        esac
    else
        echo -e "${GREEN}未检测到已安装面板，将执行全新安装${PLAIN}"
        echo ""
        if confirm "是否开始全新安装 bt_simple 面板?"; then
            fresh_install
        else
            echo "已取消"
            exit 0
        fi
    fi
}

main "$@"
