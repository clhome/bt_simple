#!/bin/bash
# =========================================================================
# bt_simple 一键部署脚本
# 支持: 全新安装 / 从 mdserver-web 迁移 / 从宝塔面板迁移
# =========================================================================
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
export LANG=en_US.UTF-8

# ---------- 颜色定义 ----------
RED='\033[31m'
GREEN='\033[32m'
YELLOW='\033[33m'
BLUE='\033[34m'
PLAIN='\033[0m'
BOLD='\033[1m'

# ---------- 全局变量 ----------
PANEL_DIR=/www/server/mdserver-web
BT_DIR=/www/server/panel
BACKUP_DIR=/www/backup
TIMESTAMP=$(date +%Y%m%d%H%M%S)
LOG_FILE=/var/log/bt_simple_deploy.log

# fork 仓库地址（⚠️ 请根据实际修改为你的 GitHub 仓库地址）
GIT_REPO_BASE="https://github.com/clhome/bt_simple.git"
GIT_REPO="${BT_SIMPLE_REPO:-$GIT_REPO_BASE}"
GIT_BRANCH="${BT_SIMPLE_BRANCH:-master}"
FORCE_CN=false

# ---------- 中国区加速 ----------
check_china() {
    if [ "$FORCE_CN" = "true" ]; then
        return 0
    fi
    # 通过 IP 地理位置判断是否在中国境内
    local status=$(curl -s -m 2 http://www.baidu.com > /dev/null && echo "ok" || echo "fail")
    if [ "$status" = "ok" ]; then
        local cn=$(curl -s -m 2 https://ipapi.co/country/ 2>/dev/null)
        if [ "$cn" = "CN" ]; then
            return 0
        fi
    fi
    return 1
}

get_github_url() {
    local original_url=$1
    if check_china; then
        if [[ $original_url == *"github.com"* ]]; then
            echo "https://gh-proxy.org/$original_url"
            return
        fi
    fi
    echo "$original_url"
}

setup_china_git_config() {
    if check_china; then
        log_info "配置 Git 全局代理加速 (GitHub -> ghproxy)..."
        git config --global url."https://gh-proxy.org/https://github.com/".insteadOf "https://github.com/"
        git config --global http.version HTTP/1.1
    fi
}

# ---------- 工具函数 ----------
log_info()  { echo -e "${GREEN}[INFO]${PLAIN} $1" | tee -a $LOG_FILE; }
log_warn()  { echo -e "${YELLOW}[WARN]${PLAIN} $1" | tee -a $LOG_FILE; }
log_error() { echo -e "${RED}[ERROR]${PLAIN} $1" | tee -a $LOG_FILE; }

confirm() {
    local msg="$1"
    local response
    echo -e "\n${BOLD}${YELLOW}$msg${PLAIN}"
    read -p "请输入 [yes/no]: " response < /dev/tty
    [ "$response" = "yes" ]
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

install_basic_deps() {
    log_info "安装基础依赖..."
    if command -v apt >/dev/null 2>&1; then
        apt install -y wget curl zip unzip tar git cron >/dev/null 2>&1
    elif command -v yum >/dev/null 2>&1; then
        yum install -y wget curl zip unzip tar git crontabs >/dev/null 2>&1
    elif command -v apk >/dev/null 2>&1; then
        apk add wget curl zip unzip tar git >/dev/null 2>&1
    fi
}

# ---------- 环境检测 ----------
detect_environment() {
    HAS_MW=false
    HAS_BT=false

    if [ -d "$PANEL_DIR" ] && [ -f "$PANEL_DIR/cli.sh" ]; then
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
    echo -e '|          bt_simple 面板一键部署工具               |'
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
    log_info "备份 mdserver-web 面板..."
    mkdir -p $BACKUP_DIR

    tar -czf ${BACKUP_DIR}/mdserver-web-${TIMESTAMP}.tar.gz \
        --exclude='mdserver-web/bin' \
        --exclude='mdserver-web/lib' \
        --exclude='mdserver-web/lib64' \
        --exclude='mdserver-web/include' \
        -C /www/server mdserver-web 2>/dev/null

    if [ -f ${PANEL_DIR}/data/system.db ]; then
        cp ${PANEL_DIR}/data/system.db ${BACKUP_DIR}/system.db.${TIMESTAMP}.bak
    fi
    log_info "备份完成: ${BACKUP_DIR}/mdserver-web-${TIMESTAMP}.tar.gz"
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
    local backup_file=$(ls -t ${BACKUP_DIR}/mdserver-web-*.tar.gz 2>/dev/null | head -1)
    if [ -z "$backup_file" ]; then
        log_error "未找到 mdserver-web 备份文件!"
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

    # 移除 mw 命令链接
    rm -f /usr/bin/mw 2>/dev/null

    log_info "宝塔面板回滚完成!"
}

# =====================================================================
# 服务控制
# =====================================================================
stop_panel() {
    # 停止 mdserver-web
    if [ -f /usr/bin/mw ]; then
        mw 2 2>/dev/null
    fi
    if [ -f /etc/init.d/mw ]; then
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
    if [ -f /usr/bin/mw ]; then
        mw 3
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

    local download_url=$(get_github_url ${GIT_REPO})
    if command -v git >/dev/null 2>&1; then
        log_info "正在从 ${download_url} 拉取代码..."
        git -c http.version=HTTP/1.1 clone --depth 1 -b ${GIT_BRANCH} ${download_url} /tmp/bt_simple_deploy 2>&1 | tee -a $LOG_FILE
    else
        log_error "git 未安装，请先安装 git"
        exit 1
    fi

    if [ ! -d /tmp/bt_simple_deploy/web ]; then
        log_error "代码下载失败，请检查仓库地址: ${GIT_REPO}"
        exit 1
    fi
    log_info "代码下载完成"
}

# 将代码部署到面板目录
deploy_code() {
    local src="/tmp/bt_simple_deploy"
    log_info "部署代码到 ${PANEL_DIR} ..."

    # 核心代码目录
    local CODE_ITEMS="web panel_task.py panel_tools.py cli.sh scripts route version.py branding.py requirements.txt"
    for item in $CODE_ITEMS; do
        if [ -e ${src}/${item} ]; then
            rm -rf ${PANEL_DIR}/${item}
            cp -rf ${src}/${item} ${PANEL_DIR}/
        fi
    done

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
    mv /tmp/bt_simple_deploy ${PANEL_DIR}
    mkdir -p ${PANEL_DIR}/logs
    mkdir -p ${PANEL_DIR}/data

    # 安装 acme.sh
    if [ ! -d /root/.acme.sh ]; then
        log_info "安装 acme.sh ..."
        if check_china; then
            curl https://gh-proxy.org/https://raw.githubusercontent.com/acmesh-official/acme.sh/master/acme.sh | sh -s -- --install-online -m my@example.com 2>/dev/null
        else
            curl -fsSL https://get.acme.sh | bash 2>/dev/null
        fi
    fi

    # 安装系统依赖
    log_info "安装系统依赖（可能需要几分钟）..."
    setup_china_git_config
    cd ${PANEL_DIR} && bash scripts/install/${OSNAME}.sh 2>&1 | tee -a $LOG_FILE

    # 启动服务
    cd ${PANEL_DIR} && bash cli.sh start
    sleep 3

    # 等待 init 脚本生成
    local n=0
    while [ ! -f /etc/rc.d/init.d/mw ] && [ $n -lt 30 ]; do
        sleep 1
        let n+=1
    done

    # 配置系统服务
    if [ -f /etc/rc.d/init.d/mw ]; then
        bash /etc/rc.d/init.d/mw stop
        bash /etc/rc.d/init.d/mw start
    fi

    # 创建 mw 命令
    if [ ! -e /usr/bin/mw ] && [ -f /etc/rc.d/init.d/mw ]; then
        ln -sf /etc/rc.d/init.d/mw /usr/bin/mw
    fi

    # 开放面板端口
    open_panel_port

    # 生成 12 位随机密码并设置
    local rand_pass=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 12 | head -n 1)
    if [ -f /usr/bin/mw ]; then
        mw 11 $rand_pass > /dev/null
        echo "$rand_pass" > ${PANEL_DIR}/data/default.pl
    fi

    # 自动获取并设置版本号
    log_info "获取最新版本号..."
    local latest_ver=$(curl -s "https://api.github.com/repos/clhome/bt_simple/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
    if [ -n "$latest_ver" ]; then
        echo "$latest_ver" > ${PANEL_DIR}/.version
        log_info "当前安装版本: ${latest_ver}"
    fi

    disable_upstream_update
    show_panel_info "$rand_pass"
    log_info "===== 全新安装完成 ====="
}

# =====================================================================
# 场景2: 从 mdserver-web 迁移
# =====================================================================
migrate_from_mw() {
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

    # 备份
    backup_mdserver_web

    # 停止服务
    log_info "停止面板服务..."
    stop_panel

    # 下载并部署
    download_code
    deploy_code

    # 检查依赖
    log_info "检查 Python 依赖..."
    if [ -f ${PANEL_DIR}/bin/activate ]; then
        cd ${PANEL_DIR} && source bin/activate
        pip3 install -r requirements.txt 2>&1 | grep -v 'already satisfied' | tee -a $LOG_FILE
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

    show_panel_info
    echo ""
    log_info "===== mdserver-web 迁移完成 ====="
    echo -e "${YELLOW}提示: 如需回滚请执行: bash $0 rollback_mw${PLAIN}"
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
    echo "  3. 已通过宝塔安装的 OpenResty/Nginx/MySQL/PHP 等软件不受影响"
    echo "  4. 但宝塔面板中配置的站点需要在 bt_simple 中重新添加"
    echo "  5. /www/wwwroot 下的网站文件和数据库数据完整保留"
    echo ""
    echo -e "${YELLOW}迁移后将保留的内容:${PLAIN}"
    echo "  ✅ /www/wwwroot/     - 网站文件"
    echo "  ✅ /www/server/mysql/ - MySQL 数据"
    echo "  ✅ /www/server/php/   - PHP 环境"
    echo "  ✅ /www/backup/       - 备份文件"
    echo ""
    echo -e "${YELLOW}需要重新配置的内容:${PLAIN}"
    echo "  ⚠️  站点列表（需在新面板中重新添加域名）"
    echo "  ⚠️  计划任务"
    echo "  ⚠️  面板账号密码（新面板会生成新的）"
    echo ""

    if ! confirm "是否确认从宝塔面板迁移到 bt_simple? (宝塔面板将被停止但保留)"; then
        log_info "用户取消迁移"
        return
    fi

    # 备份宝塔面板
    backup_bt_panel

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
    download_code
    mv /tmp/bt_simple_deploy ${PANEL_DIR}
    mkdir -p ${PANEL_DIR}/logs
    mkdir -p ${PANEL_DIR}/data

    # 安装依赖
    log_info "安装系统依赖..."
    cd ${PANEL_DIR} && bash scripts/install/${OSNAME}.sh 2>&1 | tee -a $LOG_FILE

    # 启动
    cd ${PANEL_DIR} && bash cli.sh start
    sleep 3

    local n=0
    while [ ! -f /etc/rc.d/init.d/mw ] && [ $n -lt 30 ]; do
        sleep 1
        let n+=1
    done

    if [ -f /etc/rc.d/init.d/mw ]; then
        bash /etc/rc.d/init.d/mw stop
        bash /etc/rc.d/init.d/mw start
    fi

    if [ ! -e /usr/bin/mw ] && [ -f /etc/rc.d/init.d/mw ]; then
        ln -sf /etc/rc.d/init.d/mw /usr/bin/mw
    fi

    disable_upstream_update
    show_panel_info

    echo ""
    log_info "===== 宝塔面板迁移完成 ====="
    echo -e "${YELLOW}提示:${PLAIN}"
    echo "  1. 原宝塔面板备份在: ${BT_DIR}.bak.${TIMESTAMP}"
    echo "  2. 如需回滚请执行: bash $0 rollback_bt"
    echo "  3. 请在新面板中重新添加网站域名"
}

# =====================================================================
# 禁用上游自动更新
# =====================================================================
disable_upstream_update() {
    local mw_script="/etc/rc.d/init.d/mw"
    if [ -f "$mw_script" ]; then
        # 检查是否已禁用
        if grep -q "自动更新已禁用" "$mw_script" 2>/dev/null; then
            return
        fi
        # 在 mw_update 函数中插入禁用逻辑
        sed -i '/^mw_update()/,/^}/{
            /^mw_update()/!{
                /^{/a\    echo "自动更新已禁用(bt_simple fork)，请手动从仓库拉取更新"; return 0
            }
        }' "$mw_script" 2>/dev/null
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
    echo -e "${GREEN}${BOLD}${version}bt_simple 面板安装/迁移完成!${PLAIN}"
    echo -e "=================================================================="
    
    if [ -f /usr/bin/mw ]; then
        # 获取默认信息
        local info=$(mw 10 2>/dev/null)
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
}

# =====================================================================
# 主入口
# =====================================================================
main() {
    check_root
    detect_os
    install_basic_deps
    detect_environment

    mkdir -p $BACKUP_DIR
    echo "===== bt_simple deploy $(date) =====" >> $LOG_FILE

    # 命令行参数处理
    case "$1" in
        rollback_mw)
            rollback_mdserver_web
            exit 0
            ;;
        rollback_bt)
            rollback_bt_panel
            exit 0
            ;;
        uninstall)
            uninstall_panel
            exit 0
            ;;
        -cn)
            FORCE_CN=true
            shift
            ;;
    esac

    show_banner

    if $HAS_BT && $HAS_MW; then
        echo -e "${YELLOW}检测到同时存在宝塔面板和 mdserver-web${PLAIN}"
        echo ""
        echo "  1) 从 mdserver-web 迁移"
        echo "  2) 从宝塔面板迁移"
        echo "  3) 取消"
        echo ""
        read -p "请选择 [1-3]: " choice < /dev/tty
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
        read -p "请选择 [1-2]: " choice < /dev/tty
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
        read -p "请选择 [1-2]: " choice < /dev/tty
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
