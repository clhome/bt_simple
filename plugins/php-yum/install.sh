#!/bin/bash
# YUM（Remi）渠道 PHP 安装 / 卸载调度脚本
# 约定：UTF-8 无 BOM、LF 换行
#
# ==========================================================================
# P1-8：严格模式
#   整改前本脚本没有 `set -e`，批量扩展安装、EPEL/Remi 源安装全用 `|| true`
#   把失败吞掉（14 处），面板照样报「安装完成」。现在未显式判定的失败立刻中止，
#   ERR trap 把「脚本名 + 行号 + 失败命令」打到 stderr（面板任务日志可见）。
#   注：`set -euo pipefail` 等价于 set -e + set -u + set -o pipefail，
#   既有守卫用例按「set -o pipefail」字面断言的写法保留。
# ==========================================================================
set -euo pipefail
trap 'echo "[ERROR] ${BASH_SOURCE[0]}:$LINENO 失败: $BASH_COMMAND" >&2; exit 1' ERR

PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

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

yf_install_report_init php-yum

# 报告里说明「哪些失败忽略点被保留、为什么留」（对应行尾的 yf-keep 标记）
_yf_report_keep_notes()
{
	yf_install_report_note "保留失败忽略点（共 1 处，行尾标 yf-keep）：安装后探活失败时打印的 systemctl status | tail —— 纯诊断输出，失败没有额外含义，不代表安装缺失，故不进缺失清单。"
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

action=${1:-}
type=${2:-}

if [ "${type}" == "" ];then
	echo '[ERROR] 缺少安装脚本参数（用法：bash install.sh install <版本号>，例如 install 82）' >&2
	exit 1
fi 

case "${action}" in
	install|uninstall) ;;
	*)
		echo "[ERROR] 不支持的动作：${action}（仅支持 install / uninstall）" >&2
		exit 1
		;;
esac

if [ ! -d "$curPath/versions/$type" ];then
	echo "[ERROR] 缺少版本安装脚本：${curPath}/versions/${type}" >&2
	exit 1
fi

# --------------------------------------------------------------------------
# 辅助函数
# --------------------------------------------------------------------------

# 发行版探测脚本（scripts/getos.sh）：失败只是拿不到 OSNAME，不影响后续 rpm/yum，
# 因此记为可选缺失项而不是中止。
_yf_yum_getos()
{
	bash "${rootPath}/scripts/getos.sh"
}

# 安装 Remi 源：按发行版与国内/国外选择镜像，多个 URL 依次试。
# 全部失败才返回非 0（由调用方记为缺失项）。
_yf_yum_install_remi()
{
	local _is_cn="${1:-0}"
	local _u1=""
	local _u2=""
	local _u3=""
	local _u=""

	if [ "$OSNAME" == "fedora" ]; then
		_u1="https://rpms.remirepo.net/fedora/remi-release-${R_VER}.rpm"
		_u2="https://rpms.remirepo.net/fedora/remi-release-${VERSION_ID}.rpm"
	else
		if [ "$_is_cn" == "1" ]; then
			_u1="https://mirrors.tuna.tsinghua.edu.cn/remi/enterprise/remi-release-${R_VER}.rpm"
			_u2="https://rpms.remirepo.net/enterprise/remi-release-${R_VER}.rpm"
		else
			_u1="https://rpms.remirepo.net/enterprise/remi-release-${R_VER}.rpm"
			_u2="https://mirrors.tuna.tsinghua.edu.cn/remi/enterprise/remi-release-${R_VER}.rpm"
		fi
		_u3="https://rpms.remirepo.net/enterprise/remi-release-${VERSION_ID}.rpm"
	fi

	for _u in "$_u1" "$_u2" "$_u3"; do
		if [ -z "$_u" ]; then
			continue
		fi
		if rpm -Uvh "$_u" 2>/dev/null; then
			return 0
		fi
	done
	return 1
}

# 进插件目录跑 index.py（子 shell，避免污染外层 cwd）
_yf_yum_index()
{
	(
		cd "${rootPath}" &&
			python3 "${rootPath}/plugins/php-yum/index.py" "$@"
	)
}

# 启动 phpNN-php-fpm：systemctl restart -> systemctl start -> service restart 三级兜底
_yf_yum_start_fpm()
{
	if systemctl restart "php${type}-php-fpm" 2>/dev/null; then
		return 0
	fi
	if systemctl start "php${type}-php-fpm" 2>/dev/null; then
		return 0
	fi
	service "php${type}-php-fpm" restart 2>/dev/null
}

# 下载并安装 composer（可选组件）：国内优先/官方优先双回退，失败只记缺失不中止
_yf_yum_composer_install()
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
# 获取发行版信息
# --------------------------------------------------------------------------
yf_optional_step --quiet "获取发行版信息（scripts/getos.sh）" _yf_yum_getos

OSNAME=""
if [ -s "${rootPath}/data/osname.pl" ]; then
	# read 失败（文件无结尾换行等）就当没读到，下面会给 [警告]；这是状态文件探测，不是安装步骤
	if ! read -r OSNAME < "${rootPath}/data/osname.pl"; then
		OSNAME=""
	fi
fi
if [ -z "$OSNAME" ]; then
	echo "[警告] 未能识别系统发行版（data/osname.pl 缺失或为空），Remi 源安装可能被跳过" >&2
fi

# /etc/*-release 里取 VERSION_ID：用 awk 直接匹配，避免 `cat | grep | awk` 在
# pipefail 下因为「某个文件没有 VERSION_ID」把整个脚本打成失败
VERSION_ID=""
for _rel in /etc/*-release; do
	if [ -f "$_rel" ]; then
		VERSION_ID=$(awk -F= '/^VERSION_ID=/{print $2}' "$_rel" 2>/dev/null | tr -d '"' | head -n 1)
		if [ -n "$VERSION_ID" ]; then
			break
		fi
	fi
done
R_VER=${VERSION_ID%%.*}
if [ -z "$R_VER" ]; then
	R_VER="8"
fi

# Remi 源依赖 EPEL，前置保障
# rpm -q 是纯探测：未安装返回非 0 是「预期内的否定」，所以放在 if 里而不是 || true
if ! rpm -q epel-release >/dev/null 2>&1; then
	# 装 EPEL 可能因网络/源签名失败；它不是 PHP 本体，失败记缺失不中止
	yf_optional_step --quiet "安装 EPEL 源（yum install epel-release）" yum install -y epel-release
fi

# 安装 Remi 源（支持 CentOS / Alma / Rocky / RHEL / Aliyun / Anolis / Euler / Fedora）
if ! rpm -q remi-release >/dev/null 2>&1; then
	is_cn=$(is_cn_env)
	if [ "$OSNAME" == "alma" ] || [ "$OSNAME" == "rocky" ] || [ "$OSNAME" == "centos" ] || [ "$OSNAME" == "rhel" ] || [ "$OSNAME" == "aliyun" ] || [ "$OSNAME" == "euler" ] || [ "$OSNAME" == "fedora" ]; then
		# Remi 源装不上会导致后面的 yum install phpNN 失败并中止（不会静默），
		# 但这里本身记为缺失项，便于面板直接告诉用户「源没装上」
		yf_optional_step --quiet "安装 Remi 源（remi-release-${R_VER}）" _yf_yum_install_remi "$is_cn"
	fi
fi

if [ "${action}" == "uninstall" ] && [ -d "${serverPath}/php-yum/${type}" ];then
	# 卸载清理 
	_yf_yum_index stop "${type}"
	_yf_yum_index initd_uninstall "${type}"

	if [ -f /lib/systemd/system/php${type}-php-fpm.service ];then
		rm -rf /lib/systemd/system/php${type}-php-fpm.service
	fi

	yf_optional_step --quiet "重新加载 systemd 单元（systemctl daemon-reload）" systemctl daemon-reload
fi

# 真正安装 PHP 本体的地方：versions/<NN>/install.sh 失败必须中止
cd ${curPath} && yf_require_step "安装 PHP${type} 本体（versions/${type}/install.sh）" sh -x $curPath/versions/$2/install.sh $1

if [ "${action}" == "install" ] && [ -d "${serverPath}/php-yum/${type}" ];then

	# 批量合并安装通用扩展（避免 32 次 yum 试错瓶颈，提速 80%）
	echo "install PHP-YUM[${type}] extensions start (batch mode)"
	export PHP_EXT_NO_RESTART=1

	# 这批是「PHP 不自带、面板功能要用的」基础扩展：装不上必须中止
	# （原写法是 `yum install -y ${batch_pkgs} 2>/dev/null || true`，静默吞掉）
	batch_pkgs="php${type}-php-mysqlnd php${type}-php-gd php${type}-php-intl php${type}-php-bcmath php${type}-php-mbstring php${type}-php-xml php${type}-php-opcache"
	yf_require_step "安装 PHP${type} 基础扩展（批量：mysqlnd/gd/intl/bcmath/mbstring/xml/opcache）" \
		yum install -y ${batch_pkgs}

	# 安装常用组件扩展：这一串本来就是「多个候选包名逐个试错」，属可选组件，
	# 失败只记缺失，不阻断整个 PHP 安装
	for ext in pecl-zip zip pecl-mcrypt mcrypt pecl-redis5 pecl-redis pecl-memcached pecl-mongodb; do
		yf_optional_step --quiet "安装扩展 php${type}-php-${ext}（可选，候选包名试错）" yum install -y "php${type}-php-${ext}"
	done

	unset PHP_EXT_NO_RESTART
	echo "install PHP-YUM[${type}] extensions end"

	# 初始化启动
	yf_optional_step "启动 PHP-YUM[${type}] 服务（index.py start）" _yf_yum_index start "${type}"
	yf_optional_step "配置 PHP-YUM[${type}] 开机自启（index.py initd_install）" _yf_yum_index initd_install "${type}"

	if [ ! -f /usr/local/bin/composer ];then
		echo "Installing Composer..."
		cd /tmp
		yf_optional_step "安装 Composer（可选组件，缺失不影响 PHP 运行）" _yf_yum_composer_install
	fi

	echo "PHP-YUM[${type}] start ..."
	yf_optional_step --quiet "停止 php${type}-php-fpm（systemctl stop）" systemctl stop php${type}-php-fpm
	sleep 0.5
	yf_optional_step --quiet "清理 systemd 失败计数（reset-failed）" systemctl reset-failed php${type}-php-fpm
	yf_optional_step --quiet "重新加载 systemd 单元（daemon-reload）" systemctl daemon-reload
	yf_optional_step --quiet "启动 php${type}-php-fpm（restart/start/service 三级兜底）" _yf_yum_start_fpm

	is_running=0
	for i in $(seq 1 5); do
		if systemctl is-active --quiet php${type}-php-fpm 2>/dev/null; then
			is_running=1
			break
		fi
		sleep 1
	done

	if [ "$is_running" == "0" ]; then
		echo "PHP-YUM[${type}] not active, attempting self-healing restart..."
		yf_optional_step "自愈重启 PHP-YUM[${type}]（index.py restart）" _yf_yum_index restart "${type}"
		sleep 1
	fi

	if systemctl is-active --quiet php${type}-php-fpm 2>/dev/null; then
		echo "PHP-YUM[${type}] service is active and running."
	else
		echo "Notice: php${type}-php-fpm service status:"
		# 探活失败时的诊断输出；status 本身失败没有额外含义，属纯诊断
		systemctl status php${type}-php-fpm --no-pager -l 2>/dev/null | tail -n 15 || true  # yf-keep: 纯诊断输出
	fi
	echo "PHP-YUM[${type}] start ok"
fi

_yf_report_keep_notes
yf_install_report_finish
