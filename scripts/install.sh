#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

RED='\033[31m'
GREEN='\033[32m'
YELLOW='\033[33m'
BLUE='\033[34m'
PLAIN='\033[0m'
BOLD='\033[1m'
SUCCESS='[\033[32mOK\033[0m]'
COMPLETE='[\033[32mDONE\033[0m]'
WARN='[\033[33mWARN\033[0m]'
ERROR='[\033[31mERROR\033[0m]'
WORKING='[\033[34m*\033[0m]'


# LANG=en_US.UTF-8
is64bit=`getconf LONG_BIT`

if [ -f /www/server/yufeng_panel/tools.py ];then
	echo -e "存在旧版代码,不能安装!,已知风险的情况下" 
	echo -e "rm -rf /www/server/yufeng_panel"
	echo -e "可安装!" 
	exit 0
fi

LOG_FILE=/var/log/yf-install.log

# =========================================================================
# 严格模式与失败语义（报告 P1-6）
#
# 1) 放在变量初始化**之后**：`set -u` 若在初始化期生效，会把「本可为空」的
#    变量（$cn、$INPUT 等）误判成致命错误。
# 2) `set -e` + ERR trap 保证中间步骤（下载 / 依赖安装 / 启动服务）失败时
#    立即中止，不会再走到结尾打印 "Install completed" 这种假成功。
# 3) 已知允许失败的语句逐条显式 `|| true`，理由写在该行上方。
# =========================================================================
die() {
	local _code=${2:-1}
	echo -e "${ERROR} $1" >&2
	echo -e "${ERROR} 安装日志: ${LOG_FILE}" >&2
	exit "$_code"
}

# 系统资源预检（口径对齐 deploy.sh::check_system_resources()）：
#   内存 < 450MB → 拒绝；根分区(/)或 /www 剩余 ≤ 400MB → 拒绝。
# YF_FAKE_MEM_MB / YF_FAKE_DISK_MB 覆盖读到的值，让守卫用例能构造失败路径
# （testsuite/test_install_scripts_hardening.py）；生产环境不会设置这两个变量。
function check_system_resources() {
	local mem_total root_disk_space www_disk_space

	mem_total="${YF_FAKE_MEM_MB:-$(LC_ALL=C free -m 2>/dev/null | grep Mem | awk '{print $2}' || true)}"
	if [ -z "$mem_total" ]; then
		# free 不可用（极简容器 / macOS）时无法判断，放行而不是误杀
		echo -e "${WARN} 无法读取内存信息，跳过内存预检"
	elif [ "$mem_total" -lt 450 ]; then
		echo -e "${ERROR} 当前服务器内存为: ${mem_total}MB"
		echo -e "${ERROR} 检测到当前服务器内存小于450MB，无法继续安装面板！"
		return 1
	fi

	root_disk_space="${YF_FAKE_DISK_MB:-$(df -m 2>/dev/null | grep '/$' | awk '{print $4}' || true)}"
	if [ -n "$root_disk_space" ] && [ "$root_disk_space" -le 400 ]; then
		echo -e "${ERROR} 系统盘(/)剩余空间不足400M，无法继续安装！"
		return 1
	fi

	www_disk_space="${YF_FAKE_DISK_MB:-$(df -m 2>/dev/null | grep '/www$' | awk '{print $4}' || true)}"
	if [ -n "$www_disk_space" ] && [ "$www_disk_space" -le 400 ]; then
		echo -e "${ERROR} /www盘剩余空间不足400M，无法继续安装！"
		return 1
	fi

	echo -e "${SUCCESS} 系统资源检查通过"
	return 0
}

# =========================================================================
# 供应链闸门（测评报告 P1-2）：未经验证的远端内容一律拒绝 root 执行
#
# 历史上这里有两类「零校验执行」：
#   1) 从 master 分支拉源码包 tar，解包后直接覆盖 /www/server；
#   2) 把官方安装脚本直接管道送进解释器执行。
# 两类写法同时满足「放宽传输层 TLS 校验」「内容零校验」「以 root 执行」，
# 等于把整台服务器交给任何能劫持链路或改写分支的人。
#
# 现在的口径是**默认拒绝**，并且**刻意不提供**环境变量放过口：能静默跳过就等于没堵。
#   * 分支快照没有 Ed25519 发布签名可比对 → 拒绝安装，改用 deploy.sh 或带签名发布包；
#   * 第三方脚本必须哈希校验通过后才执行（见 yf_install_acme_verified）。
# =========================================================================
YF_ACME_VERSION="3.1.6"
# 升级步骤：改 YF_ACME_VERSION 后重新计算官方 tag 源码包的 sha256，并同步 deploy.sh 中的同名常量
YF_ACME_SHA256="0d3f9000ac44a6331314742a88c475f79134e24fc991997883652adc59efc486"

# /www 目录权限固化（《问题报告》P1-1）
#
# 为什么必须显式做：安装器不能假设调用者的 umask。运维按安全基线把 umask 设成
# 027/077（很常见）时，下面那些 `mkdir -p /www/...` 出来的目录就是 770/700
# root:root，而 gitea（systemd User=www）、php-fpm（pool user=www）都要以 www
# 身份进入这些目录 —— 结局是 gitea.service 以 status=200/CHDIR 进崩溃循环、
# php-fpm 打不开站点目录，而面板侧**一点提示都没有**（只能去 journalctl 才发现）。
#
# 取值口径：目录 755（www 只需 r-x 用于穿越与读取），所有者保持 root —— www
# 不得对 /www 有写权；需要写入的插件数据目录由各自 install.sh 单独 chown www。
#
# 回读：chmod 成功不等于 www 进得去（ACL / 挂载选项 / SELinux 都可能挡住），
# 所以最后真以 www 身份 test 一次，失败即让安装器报错退出（不许假成功）。
yf_ensure_www_perms() {
	local _d
	for _d in /www /www/server /www/wwwroot /www/wwwlogs /www/backup /www/backup/database /www/backup/site; do
		if [ -d "$_d" ]; then
			chmod 755 "$_d" || true
		fi
	done
	if ! id www >/dev/null 2>&1; then
		return 0
	fi
	if ! su -s /bin/sh www -c 'test -r /www && test -x /www && test -r /www/server && test -x /www/server' >/dev/null 2>&1; then
		echo -e "${ERROR} /www 权限固化失败：www 用户无法进入 /www 或 /www/server" >&2
		echo -e "${ERROR} 请检查 umask / ACL / 挂载选项后重试" >&2
		return 1
	fi
	return 0
}

# 统一拒绝文案：说明「拒绝什么、为什么、改用哪条路」。调用后直接终止脚本。
yf_refuse_unverified_source() {
	echo -e "${ERROR} 拒绝执行未经验证的远端内容：$1" >&2
	echo -e "${ERROR} 原因：它是**未签名**的分支快照或第三方脚本，没有可校验的 Ed25519 签名／哈希，" >&2
	echo -e "${ERROR}       以 root 身份执行等于把服务器完全交给链路中间人（供应链 fail-closed）。" >&2
	echo -e "${ERROR} 请改用下列任一方式安装/升级：" >&2
	echo -e "${ERROR}   1) bash deploy.sh                  # 下载发布包 → Ed25519 验签 → 解压安装（含回滚）" >&2
	echo -e "${ERROR}   2) 下载**带签名的发布包**，按发布说明安装" >&2
	echo -e "${ERROR}   3) 已 clone 仓库时，在仓库根目录执行 bash scripts/install.sh（走本地复制分支，不下载）" >&2
	exit 1
}

# 计算文件 sha256（优先 sha256sum，退化 shasum/openssl，覆盖精简系统与 macOS）
yf_sha256_file() {
	local _f="$1"
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$_f" 2>/dev/null | awk '{print $1}'
	elif command -v shasum >/dev/null 2>&1; then
		shasum -a 256 "$_f" 2>/dev/null | awk '{print $1}'
	elif command -v openssl >/dev/null 2>&1; then
		openssl dgst -sha256 "$_f" 2>/dev/null | awk '{print $NF}'
	else
		echo ""
	fi
}

# acme.sh：只下载官方固定 tag 的源码包 → sha256 校验通过 → 才解压执行安装。
# 校验和缺失 / 读取失败 / 不匹配一律**不执行**（fail-closed）。
# 返回非 0 不代表安装致命：acme.sh 仅用于自动签发证书，缺失不影响面板本体启动，
# 用户可在面板内手动安装（调用方只告警）。
yf_install_acme_verified() {
	local _tar="/tmp/acme.sh-${YF_ACME_VERSION}.tar.gz"
	local _src="/tmp/acme.sh-src"
	local _actual

	echo -e "${WORKING} 安装 acme.sh（固定版本 v${YF_ACME_VERSION}，sha256 校验通过后才执行）..."
	rm -f "$_tar"
	# 只下载、不执行；HTTP_PREFIX 为选定的代理前缀（直连时就是 https://）
	if ! curl -fsSL -m 60 -o "$_tar" "${HTTP_PREFIX}github.com/acmesh-official/acme.sh/archive/refs/tags/${YF_ACME_VERSION}.tar.gz"; then
		echo -e "${ERROR} acme.sh 下载失败（固定版本 v${YF_ACME_VERSION}），本次不安装 acme.sh" >&2
		rm -f "$_tar"
		return 1
	fi

	_actual=$(yf_sha256_file "$_tar")
	if [ -z "$YF_ACME_SHA256" ] || [ "$_actual" != "$YF_ACME_SHA256" ]; then
		echo -e "${ERROR} acme.sh sha256 校验失败，已拒绝执行该安装包（供应链 fail-closed）" >&2
		echo -e "${ERROR}   期望: ${YF_ACME_SHA256:-<未配置>}" >&2
		echo -e "${ERROR}   实际: ${_actual:-<读取失败>}" >&2
		echo -e "${ERROR}   若官方重打包导致变更，请维护者重新计算并同步本文件与 deploy.sh" >&2
		rm -f "$_tar"
		return 1
	fi
	echo -e "${SUCCESS} acme.sh sha256 校验通过"

	rm -rf "$_src"
	mkdir -p "$_src"
	if ! tar -zxf "$_tar" -C "$_src" --strip-components=1 2>/dev/null; then
		echo -e "${ERROR} acme.sh 解压失败，已中止（未执行其中任何内容）" >&2
		rm -rf "$_src" "$_tar"
		return 1
	fi
	# 校验通过才执行；安装脚本自身返回非 0 只告警，不影响面板本体
	( cd "$_src" && ./acme.sh --install ) || echo -e "${WARN} acme.sh 安装脚本返回非 0，已跳过"
	rm -rf "$_src" "$_tar"
	return 0
}

set -euo pipefail
trap 'die "安装失败（退出码 $?），安装未完成！" $?' ERR

{

HTTP_PREFIX="https://"
LOCAL_ADDR=common
# 地区探测是尽力而为：网络不可达时 $cn 为空即可，不能因它中止安装
cn=$(curl -fsSL -m 10 -s http://ipinfo.io/json | grep "\"country\": \"CN\"" || true)
# 原条件里的 `|| [ "$?" == "0" ]` 取到的是前一个 [ ] 的退出码（恒为 1），是死分支；
# 严格模式下 `|| true` 会把 $? 变成 0，若保留该分支就会把「探测失败」误判成「在中国」
if [ ! -z "$cn" ] ;then
	LOCAL_ADDR=cn
fi

# 代理清单单一真源：scripts/proxies.list（作用域 ui / both）
# `${BASH_SOURCE[0]:-}` + `|| true`：`curl ... | bash` 方式执行时 BASH_SOURCE 为空，
# set -u 下会直接报 unbound variable；取不到目录只退化成「找不到代理清单」
_yf_proxy_list_file="$(cd "$(dirname "${BASH_SOURCE[0]:-}")" 2>/dev/null && pwd || true)/proxies.list"

if [ "$LOCAL_ADDR" != "common" ];then
	declare -A PROXY_URL
	if [ -f "$_yf_proxy_list_file" ]; then
		while IFS='|' read -r _yf_p_name _yf_p_url _yf_p_scope; do
			case "$_yf_p_name" in
				''|'#'*) continue ;;
			esac
			case "$_yf_p_scope" in
				ui|both) PROXY_URL["$_yf_p_name"]="$_yf_p_url" ;;
			esac
		done < "$_yf_proxy_list_file"
	else
		echo -e "\033[33m[WARN]\033[0m 未找到代理清单 $_yf_proxy_list_file，仅提供官方直连。" >&2
	fi
    
    PROXY_URL["source"]="https://"


	SOURCE_LIST_KEY_SORT_TMP=$(echo ${!PROXY_URL[@]} | tr ' ' '\n' | sort -n)
	SOURCE_LIST_KEY=(${SOURCE_LIST_KEY_SORT_TMP//'\n'/})
	SOURCE_LIST_LEN=${#PROXY_URL[*]}
fi


function AutoSizeStr(){
	NAME_STR=$1
	NAME_NUM=$2

	NAME_STR_LEN=`echo "$NAME_STR" | wc -L`
	NAME_NUM_LEN=`echo "$NAME_NUM" | wc -L`

	fix_len=35
	remaining_len=`expr $fix_len - $NAME_STR_LEN - $NAME_NUM_LEN`
	FIX_SPACE=' '
	for ((ass_i=1;ass_i<=$remaining_len;ass_i++))
	do 
		FIX_SPACE="$FIX_SPACE "
	done
	echo -e " ❖   ${1}${FIX_SPACE}${2})"
}

function AutoChooseProxyURL(){
	echo -e "-----------------------------------------------------"
	echo -e "正在为您自动挑选最快的 GitHub 代理节点..."
	echo -e "-----------------------------------------------------"
	
	local TEST_URL="https://raw.githubusercontent.com/clhome/bt_simple/master/README.md"
	local BEST_TIME=999
	local BEST_PREFIX="https://"
	local BEST_NAME="Direct"

	# 测速候选同样来自单一真源（作用域 ui / both）
	declare -A TEST_LIST
	if [ -f "$_yf_proxy_list_file" ]; then
		while IFS='|' read -r _yf_p_name _yf_p_url _yf_p_scope; do
			case "$_yf_p_name" in
				''|'#'*) continue ;;
			esac
			case "$_yf_p_scope" in
				ui|both) TEST_LIST["$_yf_p_name"]="$_yf_p_url" ;;
			esac
		done < "$_yf_proxy_list_file"
	fi

	for name in "${!TEST_LIST[@]}"; do
		local prefix=${TEST_LIST[$name]}
		local full_url="${prefix}${TEST_URL}"
		
		# 使用 curl 测试连接速度，超时 3 秒
		local time_taken=$(curl -s -m 3 -o /dev/null -w "%{time_total}" "$full_url")
		local exit_code=$?

		if [ $exit_code -eq 0 ] && [ "$(echo "$time_taken > 0" | bc -l 2>/dev/null)" -eq 1 ]; then
			echo -e " ❖ 节点 [${name}]: ${time_taken}s"
			# 比较耗时
			if [ "$(echo "$time_taken < $BEST_TIME" | bc -l 2>/dev/null)" -eq 1 ]; then
				BEST_TIME=$time_taken
				BEST_PREFIX=$prefix
				BEST_NAME=$name
			fi
		else
			echo -e " ❖ 节点 [${name}]: \033[31m连接失败\033[0m"
		fi
	done

	if [ "$BEST_NAME" != "Direct" ]; then
		HTTP_PREFIX=$BEST_PREFIX
		echo -e "-----------------------------------------------------"
		echo -e "已自动为您选择最快节点: \033[32m$BEST_NAME\033[0m (耗时: ${BEST_TIME}s)"
		echo -e "-----------------------------------------------------"
	else
		echo -e "-----------------------------------------------------"
		echo -e "\033[31m未发现快速代理节点，将尝试直连或使用默认值。\033[0m"
		HTTP_PREFIX="https://"
		echo -e "-----------------------------------------------------"
	fi
}

function ChooseProxyURL(){
	clear
    echo -e '+---------------------------------------------------+'
    echo -e '|                                                   |'
    echo -e '|   =============================================   |'
    echo -e '|                                                   |'
    echo -e '|     欢迎使用 Linux 一键安装御风面板源码   |'
    echo -e '|                                                   |'
    echo -e '|   =============================================   |'
    echo -e '|                                                   |'
    echo -e '+---------------------------------------------------+'
    echo -e ''
    echo -e '#####################################################'
    echo -e ''
    echo -e '            提供以下国内代理地址可供选择:                  '
    echo -e ''
    echo -e '#####################################################'
    echo -e ''
    cm_i=0
    for V in ${SOURCE_LIST_KEY[@]}; do
    num=`expr $cm_i + 1`
	AutoSizeStr "${V}" "$num"
	cm_i=`expr $cm_i + 1`
	done
    echo -e ''
    echo -e '#####################################################'
    echo -e ''
    echo -e "        系统时间  ${BLUE}$(date "+%Y-%m-%d %H:%M:%S")${PLAIN}"
    echo -e ''
    echo -e '#####################################################'
    CHOICE_A=$(echo -e "\n${BOLD}└─ 请输入你想使用的代理地址 (直接回车将自动测速选择) [ 1-${SOURCE_LIST_LEN} ]：${PLAIN}")

    # 非交互执行（无 tty / curl|bash）时 read 直接 EOF 返回非 0：
    # 按「未输入」处理并走下面的自动测速，不能因它中止安装
    read -p "${CHOICE_A}" INPUT || INPUT=""
    # echo $INPUT
    if [ "$INPUT" == "" ];then
        AutoChooseProxyURL
        return
    fi

    if [ "$INPUT" -lt "0" ];then
		INPUT=1
		TMP_INPUT=`expr $INPUT - 1`
		INPUT_KEY=${SOURCE_LIST_KEY[$TMP_INPUT]}
		echo -e "\n低于边界错误!选择[${BLUE}${INPUT_KEY}${PLAIN}]安装！"
		sleep 2s
	fi

	if [ "$INPUT" -gt "${SOURCE_LIST_LEN}" ];then
		INPUT=${SOURCE_LIST_LEN}
		TMP_INPUT=`expr $INPUT - 1`
		INPUT_KEY=${SOURCE_LIST_KEY[$TMP_INPUT]}
		echo -e "\n超出边界错误!选择[${BLUE}${INPUT_KEY}${PLAIN}]安装！"
		sleep 2s
	fi

    INPUT=`expr $INPUT - 1`
    INPUT_KEY=${SOURCE_LIST_KEY[$INPUT]}
    HTTP_PREFIX=${PROXY_URL[$INPUT_KEY]}
}

if [ "$LOCAL_ADDR" != "common" ];then
	ChooseProxyURL

	if [ "$HTTP_PREFIX" != "https://" ] && [ "$HTTP_PREFIX" != "" ];then
		DOMAIN=`echo $HTTP_PREFIX | sed 's|https://||g'`
		DOMAIN=`echo $DOMAIN | sed 's|/||g'`
		# 自动选择逻辑已经包含了测速，如果是手动选择则保持原有的 ping 检查
		if [ "$INPUT" != "" ]; then
			# 手动选的代理不可达属于致命错误（原来 bare `exit` 以 0 退出 = 假成功）
			if ! ping -c 3 $DOMAIN > /dev/null 2>&1; then
				die "无效代理地址:${DOMAIN}" 1
			fi
		fi
	fi
fi

if [ -f /etc/motd ];then
    echo "welcome to YF panel" > /etc/motd
fi

startTime=`date +%s`

_os=`uname`
echo "use system: ${_os}"

if [ ${_os} == "Darwin" ]; then
	OSNAME='macos'
elif grep -Eqi "openSUSE" /etc/*-release; then
	OSNAME='opensuse'
	zypper refresh
	zypper install cron wget curl zip unzip
elif grep -Eqi "FreeBSD" /etc/*-release; then
	OSNAME='freebsd'
	pkg install -y wget curl zip unzip unrar rar
elif grep -Eqi "EulerOS" /etc/*-release || grep -Eqi "openEuler" /etc/*-release; then
	OSNAME='euler'
	yum install -y wget curl zip unzip tar crontabs
elif grep -Eqi "CentOS" /etc/issue || grep -Eqi "CentOS" /etc/*-release; then
	OSNAME='rhel'
	yum install -y wget curl zip unzip tar crontabs
elif grep -Eqi "Fedora" /etc/issue || grep -Eqi "Fedora" /etc/*-release; then
	OSNAME='rhel'
	yum install -y wget curl zip unzip tar crontabs
elif grep -Eqi "Rocky" /etc/issue || grep -Eqi "Rocky" /etc/*-release; then
	OSNAME='rhel'
	yum install -y wget curl zip unzip tar crontabs
elif grep -Eqi "Anolis" /etc/issue || grep -Eqi "Anolis" /etc/*-release; then
	OSNAME='rhel'
	yum install -y wget curl zip unzip tar crontabs
elif grep -Eqi "AlmaLinux" /etc/issue || grep -Eqi "AlmaLinux" /etc/*-release; then
	OSNAME='rhel'
	yum install -y wget curl zip unzip tar crontabs
elif grep -Eqi "Amazon Linux" /etc/issue || grep -Eqi "Amazon Linux" /etc/*-release; then
	OSNAME='amazon'
	yum install -y wget curl zip unzip tar crontabs
elif grep -Eqi "Debian" /etc/issue || grep -Eqi "Debian" /etc/os-release; then
	OSNAME='debian'
	# apt update -y
	apt install -y wget curl zip unzip tar cron
elif grep -Eqi "Ubuntu" /etc/issue || grep -Eqi "Ubuntu" /etc/os-release; then
	OSNAME='ubuntu'
	# apt update -y
	apt install -y wget curl zip unzip tar cron
elif grep -Eqi "Alpine" /etc/issue || grep -Eqi "Alpine" /etc/*-release; then
	OSNAME='alpine'
	apk update
	apk add devscripts -force-broken-world
	apk add wget zip unzip tar -force-broken-world
else
	OSNAME='unknow'
fi

if [ "$EUID" -ne 0 ] && [ "$OSNAME" != "macos" ];then 
	echo "Please run as root!"
	exit 1
fi

echo "LOCAL:${LOCAL_ADDR}"
echo "OSNAME:${OSNAME}"

# 系统资源预检：口径与 deploy.sh::check_system_resources() 一致。放在真正开始安装之前，
# 避免装到一半才发现内存/磁盘不够。
if ! check_system_resources; then
	die "系统资源不足，无法继续安装面板！" 1
fi

if [ $OSNAME != "macos" ];then
	# 幂等：重复执行本脚本时组/用户已存在，直接跳过，不再让 groupadd/useradd 报错后继续
	if getent group www >/dev/null 2>&1 || grep -q '^www:' /etc/group 2>/dev/null; then
		echo -e "${WARN} 用户组 www 已存在，跳过创建"
	else
		groupadd www
	fi
	if id -u www >/dev/null 2>&1; then
		echo -e "${WARN} 用户 www 已存在，跳过创建"
	else
		useradd -g www -s /usr/sbin/nologin www
	fi

	mkdir -p /www/server
	mkdir -p /www/wwwroot
	mkdir -p /www/wwwlogs
	mkdir -p /www/backup/database
	mkdir -p /www/backup/site

	# mkdir 之后立刻固化权限：不固化则 umask 027 环境下 www 服务全灭（P1-1）
	yf_ensure_www_perms || die "/www 权限固化失败，www 用户下的服务（gitea/php-fpm）将无法启动"

	if [ ! -d /www/server/yufeng_panel ];then
		if [ -f "$PWD/cli.sh" ] && [ -d "$PWD/scripts" ]; then
			echo "Local repository detected, copying files..."
			cp -r $PWD /www/server/yufeng_panel
		else
			# 分支快照（未签名）默认拒绝：见 yf_refuse_unverified_source 上方说明
			yf_refuse_unverified_source "GitHub master 分支源码包（未签名快照）"
		fi
	fi

	# install acme.sh
	# 原先这里有两处零校验执行（master 分支源码包直接执行、官方安装脚本管道送进解释器），
	# 两者都已删除：改为固定 tag + sha256 校验通过后才执行，见 yf_install_acme_verified。
	if [ ! -d /root/.acme.sh ];then
	    if ! yf_install_acme_verified; then
	        echo -e "${WARN} acme.sh 未安装（已拒绝未校验内容，不影响面板本体），可在面板内手动安装"
	    fi

	    if [ -d /root/.acme.sh ];then
	        # 只设置默认 CA：网络不可达时不应中止安装（签发证书时会再设置一次）
	        /root/.acme.sh/acme.sh --set-default-ca --server letsencrypt || echo -e "${WARN} 设置 acme.sh 默认 CA 失败，跳过"
	    fi
	fi
fi

echo "use system version: ${OSNAME}"
if [ "${OSNAME}" == "macos" ];then
	# 不再把远端脚本管道送进解释器：改为执行**已落地**的本地副本。
	# 代码只会来自「本地仓库复制」或「已验签发布包」，路径固定且可审计。
	if [ -f /www/server/yufeng_panel/scripts/install/macos.sh ]; then
		bash /www/server/yufeng_panel/scripts/install/macos.sh
	else
		yf_refuse_unverified_source "scripts/install/macos.sh（远端脚本，无法校验）"
	fi
else
	cd /www/server/yufeng_panel && bash scripts/install/${OSNAME}.sh
fi

if [ "${OSNAME}" == "macos" ];then
	echo "macos end"
	exit 0
fi

cd /www/server/yufeng_panel && bash cli.sh start
# isStart 仅用于排查输出；没匹配到进程时 grep 返回 1，pipefail 下会让赋值非 0 → || true
isStart=`ps -ef|grep 'gunicorn -c setting.py app:app' |grep -v grep|awk '{print $2}' || true`
n=0
while [ ! -f /etc/rc.d/init.d/yf ];
do
    echo -e ".\c"
    sleep 1
    let n+=1
    if [ $n -gt 20 ];then
    	echo -e "start yf fail"
    	exit 1
    fi
done

cd /www/server/yufeng_panel && bash /etc/rc.d/init.d/yf stop
cd /www/server/yufeng_panel && bash /etc/rc.d/init.d/yf start
cd /www/server/yufeng_panel && bash /etc/rc.d/init.d/yf default

sleep 2
if [ ! -e /usr/bin/yf ]; then
	if [ -f /etc/rc.d/init.d/yf ];then
		ln -s /etc/rc.d/init.d/yf /usr/bin/yf
		ln -s /etc/rc.d/init.d/yf /usr/bin/mw
	fi
fi



endTime=`date +%s`
# 耗时不足 1 分钟时 outTime=0，`((...))` 会返回 1；不 || true 的话成功的安装也会被判失败
((outTime=(${endTime}-${startTime})/60)) || true
echo -e "Time consumed:\033[32m $outTime \033[0mMinute!"

} 1> >(tee $LOG_FILE) 2>&1

# 只有上面的安装块整体跑完（没有触发 set -e / ERR trap）才会走到这里打印成功文案
echo -e "\nInstall completed. If error occurs, please contact us with the log file yf-install.log ."
echo "安装完毕，如果出现错误，请带上同目录下的安装日志 yf-install.log 联系我们反馈：admin@yftec.top."