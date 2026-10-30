#!/bin/bash
# APT 渠道 PHP 安装 / 卸载调度脚本
# 约定：UTF-8 无 BOM、LF 换行
#
# ==========================================================================
# P1-8：严格模式
#   整改前本脚本没有 `set -e`，批量扩展安装用 `apt-get install ... || true`
#   把失败整条吞掉（php-apt:155/163），面板照样报「安装完成」。
#   现在未显式判定的失败立刻中止，ERR trap 把「脚本名 + 行号 + 失败命令」
#   打到 stderr（面板任务日志可见）。
#   注：`set -euo pipefail` 等价于 set -e + set -u + set -o pipefail，
#   既有守卫用例按「set -o pipefail」字面断言的写法保留。
# ==========================================================================
set -euo pipefail
trap 'echo "[ERROR] ${BASH_SOURCE[0]}:$LINENO 失败: $BASH_COMMAND" >&2; exit 1' ERR

PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
export DEBIAN_FRONTEND=noninteractive

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")
YF_SCRIPT_DIR="$curPath"

# 共享规范库：可选步骤 / 必需步骤统一落账（scripts/lib_install_report.sh）。
# 两种运行方式都覆盖：① 仓库内直跑 → ../../scripts/；② 已安装面板 → 面板目录。
# 找不到库必须**明确报错退出**（静默跳过等于退回 `|| true`）。
_yf_report_lib="${YF_SCRIPT_DIR}/../../scripts/lib_install_report.sh"
if [ ! -f "$_yf_report_lib" ]; then
	_yf_report_lib="/www/server/yufeng_panel/scripts/lib_install_report.sh"
fi
if [ ! -f "$_yf_report_lib" ]; then
	echo "[ERROR] 缺少共享规范库 scripts/lib_install_report.sh（已查找：${YF_SCRIPT_DIR}/../../scripts/ 与 /www/server/yufeng_panel/scripts/），无法继续安装" >&2
	exit 1
fi
# shellcheck source=../../scripts/lib_install_report.sh
. "$_yf_report_lib"

yf_install_report_init php-apt

# 报告里说明「哪些失败忽略点被保留、为什么留」（对应行尾的 yf-keep 标记）
_yf_report_keep_notes()
{
	yf_install_report_note "保留失败忽略点（共 1 处，行尾标 yf-keep）：安装后探活失败时打印的 systemctl status | tail —— 纯诊断输出，失败没有额外含义，不代表安装缺失，故不进缺失清单。"
}

wait_dpkg_lock() {
	local timeout=30
	while fuser /var/lib/dpkg/lock >/dev/null 2>&1 || fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
		echo "Waiting for other apt/dpkg processes to complete (${timeout}s remaining)..."
		sleep 2
		timeout=$((timeout - 2))
		if [ "$timeout" -le 0 ]; then
			break
		fi
	done
}

is_cn_env() {
	local test_cn
	test_cn=$(curl -s -m 2 -o /dev/null -w "%{http_code}" https://mirrors.aliyun.com 2>/dev/null || echo "000")
	if [ "$test_cn" == "200" ] || [ "$test_cn" == "301" ] || [ "$test_cn" == "302" ]; then
		local geo
		geo=$(curl -fsSL -m 2 https://ipinfo.io/country 2>/dev/null || curl -fsSL -m 2 http://cip.cc 2>/dev/null | grep -i "code.*CN" || echo "")
		if echo "$geo" | grep -qi "CN"; then
			echo "1"
			return
		fi
	fi
	echo "0"
}

if id www &> /dev/null ;then 
    echo "www uid is $(id -u www)"
    echo "www shell is $(grep "^www:" /etc/passwd |cut -d':' -f7)"
else
	# 已存在（别的插件先建过）时 groupadd/useradd 会返回非 0，属「真可选」
	yf_optional_step --quiet "创建 www 用户组（已存在会返回非 0）" groupadd www
	yf_optional_step --quiet "创建 www 用户（已存在会返回非 0）" useradd -g www -s /sbin/nologin www
fi

_os=$(uname)
if [ "$_os" == "Darwin" ]; then
    OSNAME='macos'
elif grep -Eqi "Debian" /etc/issue 2>/dev/null || grep -Eq "Debian" /etc/*-release 2>/dev/null; then
    OSNAME='debian'
elif grep -Eqi "Ubuntu" /etc/issue 2>/dev/null || grep -Eq "Ubuntu" /etc/*-release 2>/dev/null; then
    OSNAME='ubuntu'
else
    OSNAME='unknow'
fi

action=${1:-}
type=${2:-}

if [ "${type}" == "" ];then
	echo '[ERROR] 缺少安装脚本参数（用法：bash install.sh install <版本号>，例如 install 82）' >&2
	exit 1
fi 

if [ ! -d "$curPath/versions/$type" ];then
	echo "[ERROR] 缺少版本安装脚本：${curPath}/versions/${type}" >&2
	exit 1
fi 

# 动作白名单：把空动作/错动作挡在下发之前——否则 versions/<NN>/install.sh 会把
# 非 install 的一切当作卸载执行
case "${action}" in
	install|uninstall) ;;
	*)
		echo "[ERROR] 不支持的动作：${action}（仅支持 install / uninstall）" >&2
		exit 1
		;;
esac

apt_ver=${type:0:1}.${type:1:2}

# --------------------------------------------------------------------------
# 辅助函数
# --------------------------------------------------------------------------

# 添加 ondrej/php PPA（ubuntu）：add-apt-repository 需要交互确认，用 echo y 喂进去。
# 管道 + pipefail 下退出码取自 add-apt-repository，可以如实反映成败。
_yf_apt_add_ppa()
{
	echo "y" | LC_ALL=C.UTF-8 add-apt-repository ppa:ondrej/php
}

# 下载 sury 公钥：国内镜像 / 官方源双回退，两者都失败才返回非 0。
_yf_apt_fetch_gpg_key()
{
	local _is_cn="${1:-0}"
	local _key="${2:-}"
	local _tmp="/tmp/deb.sury.org-php.gpg.tmp"
	local _url1=""
	local _url2=""

	rm -f "$_tmp"
	if [ "$_is_cn" == "1" ]; then
		_url1="https://mirror.sjtu.edu.cn/sury/php/apt.gpg"
		_url2="https://packages.sury.org/php/apt.gpg"
	else
		_url1="https://packages.sury.org/php/apt.gpg"
		_url2="https://mirror.sjtu.edu.cn/sury/php/apt.gpg"
	fi

	if curl -fsSL -m 15 -o "$_tmp" "$_url1"; then
		:
	elif curl -fsSL -m 15 -o "$_tmp" "$_url2"; then
		:
	else
		return 1
	fi
	if [ ! -s "$_tmp" ]; then
		return 1
	fi
	mv -f "$_tmp" "$_key"
	chmod 644 "$_key"
}

# 写 sury 源：$1=1 用交大镜像，否则用官方源；$2=gpg 路径；$3=发行版代号
_yf_apt_write_sury_list()
{
	local _is_cn="${1:-0}"
	local _key="${2:-}"
	local _codename="${3:-bookworm}"

	if [ "$_is_cn" == "1" ]; then
		echo "deb [signed-by=${_key}] https://mirror.sjtu.edu.cn/sury/php/ ${_codename} main" > /etc/apt/sources.list.d/php.list
	else
		echo "deb [signed-by=${_key}] https://packages.sury.org/php/ ${_codename} main" > /etc/apt/sources.list.d/php.list
	fi
}

# 进插件目录跑 index.py（子 shell，避免污染外层 cwd）
_yf_apt_index()
{
	(
		cd "${rootPath}" &&
			python3 "${rootPath}/plugins/php-apt/index.py" "$@"
	)
}

# 用 versions/common.sh 安装单个第三方扩展
_yf_apt_common_ext()
{
	local _ext="${1:-}"
	(
		cd "${rootPath}/plugins/php-apt/versions" &&
			bash common.sh "${apt_ver}" install "${_ext}"
	)
}

# 下载并安装 composer（可选组件）：国内优先/官方优先双回退，失败只记缺失不中止
_yf_apt_composer_install()
{
	local comp_tmp="/tmp/composer.phar.tmp"
	local is_cn=""
	local url_cn="https://mirrors.aliyun.com/composer/composer.phar"
	local url_off="https://getcomposer.org/download/latest-stable/composer.phar"
	local url=""

	export COMPOSER_HOME=/root/.config/composer
	rm -f "$comp_tmp"

	is_cn=$(is_cn_env)
	if [ "$is_cn" == "1" ]; then
		for url in "$url_cn" "$url_off"; do
			if curl -fsSL -m 30 -o "$comp_tmp" "$url"; then
				break
			fi
		done
	else
		for url in "$url_off" "$url_cn"; do
			if curl -fsSL -m 30 -o "$comp_tmp" "$url"; then
				break
			fi
		done
	fi

	if [ ! -s "$comp_tmp" ]; then
		echo "Warning: Composer download failed. You may need to install it manually."
		return 1
	fi

	mv -f "$comp_tmp" /usr/local/bin/composer
	chmod +x /usr/local/bin/composer

	if [ "$is_cn" == "1" ]; then
		echo "Configuring Aliyun mirror for Composer..."
		yf_optional_step --quiet "配置 Composer 阿里云镜像" /usr/local/bin/composer config -g repo.packagist https://mirrors.aliyun.com/composer/
	fi
	return 0
}

# --------------------------------------------------------------------------
# 源准备
# --------------------------------------------------------------------------

if [ "$OSNAME" == "ubuntu" ];then
	# 探测是否已经加过 ondrej PPA：用 glob 判断，避免 `ls | grep` 在 pipefail 下
	# 因为「没匹配到」而把整个脚本打成失败
	find_source=""
	for _src in /etc/apt/sources.list.d/*ondrej*php*; do
		if [ -e "$_src" ]; then
			find_source="$_src"
			break
		fi
	done
	if [ "$find_source" == "" ];then
		wait_dpkg_lock
		yf_require_step "添加 ondrej/php PPA 源（add-apt-repository）" _yf_apt_add_ppa
		wait_dpkg_lock
		yf_require_step "刷新 APT 源索引（添加 PPA 之后）" apt-get update -y
	fi
fi

if [ "$OSNAME" == "debian" ];then
	wait_dpkg_lock
	# 没有这些包就加不了 sury 源，属必需
	yf_require_step "安装 APT 源所需基础包（apt-transport-https / lsb-release / ca-certificates / curl）" \
		apt-get install -y apt-transport-https lsb-release ca-certificates curl
	is_cn=$(is_cn_env)
	gpg_key="/usr/share/keyrings/deb.sury.org-php.gpg"
	mkdir -p /usr/share/keyrings

	# 公钥下载是可选步骤：失败后 apt-get update 会明确报错并中止，不会静默
	yf_optional_step --quiet "下载 sury GPG 公钥（国内镜像/官方源双回退）" _yf_apt_fetch_gpg_key "$is_cn" "$gpg_key"

	if [ ! -f /etc/apt/sources.list.d/php.list ]; then
		codename=""
		if [ -f /etc/os-release ]; then
			codename=$(grep '^VERSION_CODENAME=' /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"'\'' ')
		fi
		if [ -z "${codename}" ] && command -v lsb_release >/dev/null 2>&1; then
			codename=$(lsb_release -sc 2>/dev/null)
		fi
		if [ -z "${codename}" ]; then
			local _deb_ver
			_deb_ver=$(cat /etc/debian_version 2>/dev/null | cut -d. -f1 | tr -d ' ')
			case "${_deb_ver}" in
				13*|trixie*) codename="trixie" ;;
				12*|bookworm*) codename="bookworm" ;;
				11*|bullseye*) codename="bullseye" ;;
				*) codename="bookworm" ;;
			esac
		fi
		_yf_apt_write_sury_list "$is_cn" "$gpg_key" "$codename"
		wait_dpkg_lock
		if ! apt-get update -y; then
			if [ "$is_cn" == "1" ]; then
				echo "Domestic mirror update failed, falling back to official packages.sury.org..."
			else
				echo "Official source update failed, falling back to mirror..."
			fi
			if [ "$is_cn" == "1" ]; then
				_yf_apt_write_sury_list "0" "$gpg_key" "$codename"
			else
				_yf_apt_write_sury_list "1" "$gpg_key" "$codename"
			fi
			wait_dpkg_lock
			yf_require_step "刷新 APT 源索引（sury 源切换镜像后仍失败）" apt-get update -y
		fi
	fi
fi 

if [ "${action}" == "uninstall" ] && [ -d "${serverPath}/php-apt/${type}" ];then
	# 卸载清理
	_yf_apt_index stop "${type}"
	_yf_apt_index initd_uninstall "${type}"

	if [ -f /lib/systemd/system/php${apt_ver}-fpm.service ];then
		rm -rf /lib/systemd/system/php${apt_ver}-fpm.service
	fi

	if [ -f /lib/systemd/system/system/php${apt_ver}-fpm.service ];then
		rm -rf /lib/systemd/system/system/php${apt_ver}-fpm.service
	fi

	yf_optional_step --quiet "重新加载 systemd 单元（systemctl daemon-reload）" systemctl daemon-reload
fi

if [ "${action}" == "install" ]; then
	wait_dpkg_lock
	yf_require_step "刷新 APT 源索引（安装前）" apt-get update -y
fi

# 真正安装 PHP 本体的地方：versions/<NN>/install.sh 失败必须中止
cd ${curPath} && yf_require_step "安装 PHP${apt_ver} 本体（versions/${type}/install.sh）" sh -x $curPath/versions/$2/install.sh $1

if [ "${action}" == "install" ] && [ -d "${serverPath}/php-apt/${type}" ];then

	# 批量安装通用扩展（合并单条 apt-get，大幅提升 5~8 倍速度）
	echo "install PHP-APT[${type}] extensions start (batch mode)"
	export PHP_EXT_NO_RESTART=1

	# 这批是「PHP 不自带、面板功能要用的」基础扩展：装不上必须中止，
	# 否则会得到一个「装好了但 php -m 缺一半」的 PHP（原写法是 ... || true）
	batch_pkgs="php${apt_ver}-curl php${apt_ver}-gd php${apt_ver}-intl php${apt_ver}-xml php${apt_ver}-bcmath php${apt_ver}-mysql php${apt_ver}-mbstring php${apt_ver}-zip"
	wait_dpkg_lock
	yf_require_step "安装 PHP${apt_ver} 基础扩展（批量：curl/gd/intl/xml/bcmath/mysql/mbstring/zip）" \
		apt-get install -y ${batch_pkgs}

	# 流行组件扩展按需安装：redis/memcached/opcache 属可选组件（缺依赖、版本不带包
	# 都可能失败），失败记进缺失清单，但不阻断整个 PHP 安装
	for ext in redis memcached opcache; do
		if [ -f "${rootPath}/plugins/php-apt/versions/common/${ext}.sh" ]; then
			yf_optional_step "安装扩展 ${ext}（versions/common.sh）" _yf_apt_common_ext "${ext}"
		else
			wait_dpkg_lock
			yf_optional_step --quiet "安装扩展 php${apt_ver}-${ext}（apt-get）" apt-get install -y "php${apt_ver}-${ext}"
		fi
	done

	unset PHP_EXT_NO_RESTART
	echo "install PHP-APT[${type}] extensions end"

	if [ ! -f /usr/local/bin/composer ];then
		echo "Installing Composer..."
		cd /tmp
		yf_optional_step "安装 Composer（可选组件，缺失不影响 PHP 运行）" _yf_apt_composer_install
	fi

	# 配置开机自启
	yf_optional_step "配置 PHP-APT[${type}] 开机自启（index.py initd_install）" _yf_apt_index initd_install "${type}"

	# 单次平滑拉起（内部包含配置模板刷新、Systemd Override 容灾注入与孤儿套接字清理）
	echo "Starting PHP-APT[${type}] service..."
	yf_optional_step "启动 PHP-APT[${type}] 服务（index.py restart）" _yf_apt_index restart "${type}"

	# 10 秒平滑探活缓冲（兼容 active 与 activating 运行过渡态）
	is_running=0
	for i in $(seq 1 10); do
		st=$(systemctl is-active php${apt_ver}-fpm 2>/dev/null || echo "inactive")
		if [ "$st" == "active" ]; then
			is_running=1
			break
		fi
		# 若处于 activating 但实际 master 进程已就绪，同样视为启动正常
		if [ "$st" == "activating" ] && ps aux | grep 'php-fpm: master process' | grep -E "(/etc/php/${apt_ver}/|\(${apt_ver}\)|php-fpm${apt_ver})" | grep -qv grep; then
			is_running=1
			break
		fi
		sleep 1
	done

	if [ "$is_running" == "1" ]; then
		echo "PHP-APT[${type}] service is active and running."
	else
		echo "Notice: php${apt_ver}-fpm service status:"
		# 探活失败时的诊断输出；status 本身失败没有额外含义，属纯诊断
		systemctl status php${apt_ver}-fpm --no-pager -l 2>/dev/null | tail -n 15 || true  # yf-keep: 纯诊断输出
	fi
fi

_yf_report_keep_notes
yf_install_report_finish
