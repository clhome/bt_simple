#!/bin/bash
# 编译版 PHP 安装 / 卸载调度脚本
# 约定：UTF-8 无 BOM、LF 换行
#
# ==========================================================================
# P1-8：严格模式
#   整改前本脚本没有 `set -e`，15 个扩展编译 + 本体安装全都不看退出码，
#   面板一律显示「安装完成」。现在未显式判定的失败立刻中止，
#   ERR trap 把「脚本名 + 行号 + 失败命令」打到 stderr（面板任务日志可见）。
#   注：`set -euo pipefail` 等价于 set -e + set -u + set -o pipefail，
#   既有守卫用例按「set -o pipefail」字面断言的写法保留。
# ==========================================================================
set -euo pipefail
trap 'echo "[ERROR] ${BASH_SOURCE[0]}:$LINENO 失败: $BASH_COMMAND" >&2; exit 1' ERR

YF_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

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

# 多核编译任务数库：只是「尽量 -jN」的加速器，缺了不影响安装（给 [警告]，不静默）
_yf_jobs_lib="${YF_SCRIPT_DIR}/../../scripts/lib_make_jobs.sh"
if [ ! -f "$_yf_jobs_lib" ]; then
	_yf_jobs_lib="/www/server/yufeng_panel/scripts/lib_make_jobs.sh"
fi
if [ -f "$_yf_jobs_lib" ]; then
	# shellcheck source=../../scripts/lib_make_jobs.sh
	. "$_yf_jobs_lib"
else
	echo "[警告] 缺少 scripts/lib_make_jobs.sh，编译并行度退化为默认值" >&2
fi

PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")
sysName=$(uname)

yf_install_report_init php

# 报告里说明「哪些失败忽略点被保留、为什么留」（对应各行行尾的 yf-keep 标记）。
_yf_report_keep_notes()
{
	yf_install_report_note "保留失败忽略点（共 3 处，行尾标 yf-keep）：① source/php 与 source/php/phpNN 中间编译目录的 rm -rf ×2 —— 目录可能已被编译脚本自行清理，不存在属正常，清理失败也不该让已装好的 PHP 判成安装失败；② systemctl status | tail —— 纯诊断输出，失败没有额外含义。三者都不代表安装缺失，故不进缺失清单。"
}
_yf_report_keep_notes

# cd /www/server/yufeng_panel/plugins/php && bash install.sh install 73
# cd /www/server/yufeng_panel/plugins/php && bash install.sh install 85
# https://www.php.net/releases

if id www &> /dev/null ;then 
    echo "www uid is $(id -u www)"
    echo "www shell is $(grep "^www:" /etc/passwd |cut -d':' -f7)"
else
	# 已存在（例如别的插件先建过 www 组）时 groupadd/useradd 会返回非 0，属「真可选」
	yf_optional_step --quiet "创建 www 用户组（已存在会返回非 0）" groupadd www
	yf_optional_step --quiet "创建 www 用户（已存在会返回非 0）" useradd -g www -s /sbin/nologin www
fi

action=${1:-}
type=${2:-}
type=${type//./}

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

# set -u 保护：未显式设置 YF_ALLOW_UNSAFE_PHP 时下面那句判断会直接 unbound variable
YF_ALLOW_UNSAFE_PHP=${YF_ALLOW_UNSAFE_PHP:-0}

# if [ "${action}" == "install" ] && [ -d $serverPath/php/${type} ];then
# 	exit 0
# fi

# ==========================================================================
# P0-4：老旧/高危 PHP 版本的「自担风险」拦截（默认拒绝）
#
# 背景：编译版 PHP 的下架分成两类原因，提示文案不能混用 ——
#   ① 5.2~7.3：上游早已 EOL，存在**已知未修复**的 RCE（CVE-2026-109618/109619，
#      php2shell），官方不会有补丁；面板无法把它们变安全，只能默认拒绝，
#      禁止公网使用。
#   ② 7.4 / 8.0 / 8.1：这些分支的**编译版**上游已停止维护（源码树不再出安全版），
#      但 Debian/Ubuntu 的 sury 源与 CentOS/RHEL 的 Remi 源仍在出**安全回移补丁**，
#      所以安全路径是「改用 APT 渠道 / YUM 渠道」，而不是继续编译安装。
#
# 因此这里对上述版本一律 exit 1，只有显式设置 YF_ALLOW_UNSAFE_PHP=1 才放行
# （放行时会再打印一次风险警告）。存量机器不受影响：拦截只作用于 action=install，
# uninstall / restart / stop 等动作仍可正常执行。
# 守卫用例：testsuite/test_php_unsupported_versions.py
# ==========================================================================
YF_UNSAFE_PHP_VERSIONS="52 53 54 55 56 70 71 72 73"
YF_DELISTED_PHP_VERSIONS="74 80 81"

if [ "${action}" == "install" ];then
	YF_PHP_RISK=""
	case " ${YF_UNSAFE_PHP_VERSIONS} " in
		*" ${type} "*) YF_PHP_RISK="存在已知未修复 RCE（CVE-2026-109618/109619），禁止公网使用" ;;
	esac
	if [ "${YF_PHP_RISK}" == "" ];then
		case " ${YF_DELISTED_PHP_VERSIONS} " in
			*" ${type} "*) YF_PHP_RISK="编译版已下架（上游不再出安全版本），请改用 APT/YUM 渠道获取 sury / Remi 安全回移补丁" ;;
		esac
	fi

	if [ "${YF_PHP_RISK}" != "" ];then
		if [ "${YF_ALLOW_UNSAFE_PHP}" != "1" ];then
			echo "================================================================"
			echo " 拒绝安装 PHP${type}"
			echo " 原因：${YF_PHP_RISK}"
			echo " 默认已从版本列表下架，不提供安装。"
			echo " 确需安装请显式设置 YF_ALLOW_UNSAFE_PHP=1："
			echo "   YF_ALLOW_UNSAFE_PHP=1 bash install.sh install ${type}"
			echo "================================================================"
			exit 1
		fi
		echo "================================================================"
		echo " 警告：PHP${type} 属于不安全版本，已按 YF_ALLOW_UNSAFE_PHP=1 强制放行"
		echo " 风险：${YF_PHP_RISK}"
		echo " 请仅在隔离/内网环境自担风险使用，切勿暴露到公网。"
		echo "================================================================"
	fi
fi

if [ "${action}" == "uninstall" ];then
	
	if [ -f /usr/lib/systemd/system/php${type}.service ] || [ -f /lib/systemd/system/php${type}.service ] ;then
		yf_optional_step --quiet "停止 php${type} 服务（systemctl stop）" systemctl stop php${type}
		yf_optional_step --quiet "取消 php${type} 开机自启（systemctl disable）" systemctl disable php${type}
		rm -rf /usr/lib/systemd/system/php${type}.service
		rm -rf /lib/systemd/system/php${type}.service
		yf_optional_step --quiet "重新加载 systemd 单元（systemctl daemon-reload）" systemctl daemon-reload
	fi
fi

# --------------------------------------------------------------------------
# 辅助：所有「进插件目录跑 index.py」的动作走子 shell，避免污染外层 cwd
# --------------------------------------------------------------------------
_yf_php_index()
{
	(
		cd "${rootPath}" &&
			python3 "${rootPath}/plugins/php/index.py" "$@"
	)
}

# 编译单个通用扩展：扩展脚本在 versions/common/ 下，$1 = 扩展名（不含 .sh）
_yf_php_ext()
{
	local _ext="${1:-}"
	(
		cd "${rootPath}/plugins/php/versions/common" &&
			bash "${_ext}.sh" install "${type}"
	)
}

# 重启 PHP：systemctl -> service -> 插件自带 lib.sh 三级兜底。
# 任一级成功即返回 0；三级全失败才返回非 0（由调用方记进缺失清单）。
_yf_php_restart()
{
	if systemctl restart "php${type}" 2>/dev/null; then
		return 0
	fi
	if service "php${type}" restart 2>/dev/null; then
		return 0
	fi
	bash "${rootPath}/plugins/php/versions/lib.sh" "${type}" restart 2>/dev/null
}

# 下载并安装 composer（可选组件）：国内优先/官方优先双回退，失败只记缺失不中止。
_yf_php_composer_install()
{
	local comp_tmp="/tmp/composer.phar.tmp"
	local is_cn=""
	local url_cn="https://mirrors.aliyun.com/composer/composer.phar"
	local url_off="https://getcomposer.org/download/latest-stable/composer.phar"
	local url=""

	export COMPOSER_HOME=/root/.config/composer
	export PATH=${serverPath}/php/${type}/bin:$PATH
	rm -f "$comp_tmp"

	is_cn=$(curl -s -m 2 -o /dev/null -w "%{http_code}" https://mirrors.aliyun.com 2>/dev/null || echo "000")
	if [ "$is_cn" == "200" ] || [ "$is_cn" == "301" ] || [ "$is_cn" == "302" ]; then
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

	if [ "$is_cn" == "200" ] || [ "$is_cn" == "301" ] || [ "$is_cn" == "302" ]; then
		echo "Configuring Aliyun mirror for Composer..."
		yf_optional_step --quiet "配置 Composer 阿里云镜像" /usr/local/bin/composer config -g repo.packagist https://mirrors.aliyun.com/composer/
	fi
	return 0
}

# PHP 本体安装：versions/<NN>/install.sh 是真正编译的地方，失败必须中止
cd ${curPath} && yf_require_step "编译安装 PHP${type}（versions/${type}/install.sh）" sh -x $curPath/versions/$type/install.sh $1


if [ "${action}" == "install" ] && [ -d "${serverPath}/php/${type}" ];then

	#初始化 
	yf_optional_step "启动 PHP${type} 服务（index.py start）" _yf_php_index start ${type}
	yf_optional_step "配置 PHP${type} 开机自启（index.py initd_install）" _yf_php_index initd_install ${type}

	# 安装通用扩展
	# 导出 cpuCore 供扩展脚本使用多核编译
	_env_lib=${rootPath}/plugins/php/lib/common_env.sh
	# set -u 保护：common_env.sh 会读 ${cpuCore}，未定义时在 set -u 下直接崩 unbound variable
	cpuCore=${cpuCore:-0}
	if [ -f "$_env_lib" ]; then source "$_env_lib"; fi
	cpuCore=${cpuCore:-1}
	export cpuCore
	echo "install PHP${type} extend start (cpuCore=${cpuCore})"
# --- yf adaptive clamp (1C512M -> -j1) ---
# 必须把 ${type} 传进去：8.4+ 的 JIT IR 单任务峰值达 1.5G，不传版本就吃不到
# 《问题报告》里那条「按版本 + 内存」的保护分支（且旧版无参调用在 set -u 下直接
# unbound variable → ERR trap → 整个 PHP 安装/更新被打断）。
if command -v yf_make_jobs >/dev/null 2>&1; then _yf_jobs=$(yf_make_jobs "${type}" 2>/dev/null || echo ""); if [ -n "$_yf_jobs" ] && [ "$_yf_jobs" -ge 1 ] 2>/dev/null; then cpuCore="$_yf_jobs"; fi; fi

	export PHP_EXT_NO_RESTART=1

	# 通用扩展里「PHP 不自带、几乎所有面板用户都要」的那批：编译失败即中止，
	# 否则面板会得到一个「装好了但 php -m 缺一半」的 PHP（P1-8 的核心问题）。
	yf_require_step "编译扩展 curl" _yf_php_ext curl
	yf_require_step "编译扩展 gd" _yf_php_ext gd
	yf_require_step "编译扩展 readline" _yf_php_ext readline
	yf_require_step "编译扩展 iconv" _yf_php_ext iconv
	yf_require_step "编译扩展 exif" _yf_php_ext exif
	yf_require_step "编译扩展 intl" _yf_php_ext intl
	# mcrypt：上游 7.2 起才有可用版本、8.4 起彻底移除；mcrypt.sh 对这两种情况
	# 是按设计 exit 1 打印 "not need"，因此只在 7.2~8.3 区间作为必需扩展安装，
	# 免得把「按设计跳过」误记成缺失项。
	if [ "${type}" -ge 72 ] 2>/dev/null && [ "${type}" -lt 84 ] 2>/dev/null; then
		yf_require_step "编译扩展 mcrypt" _yf_php_ext mcrypt
	fi
	yf_require_step "编译扩展 openssl" _yf_php_ext openssl
	yf_require_step "编译扩展 bcmath" _yf_php_ext bcmath
	yf_require_step "编译扩展 gettext" _yf_php_ext gettext
	yf_require_step "编译扩展 redis" _yf_php_ext redis
	# memcached 依赖系统的 libmemcached 与 memcached 服务，属可选组件：
	# 装不上记进缺失清单，但不应该毁掉整个 PHP 安装
	yf_optional_step "编译扩展 memcached（依赖 libmemcached，可缺）" _yf_php_ext memcached
	yf_require_step "编译扩展 pcntl" _yf_php_ext pcntl
	yf_require_step "编译扩展 zip" _yf_php_ext zip
	yf_require_step "编译扩展 zlib" _yf_php_ext zlib

	unset PHP_EXT_NO_RESTART
	echo "install PHP${type} extend end"

	# 统筹清理中间编译临时解压源码，释放磁盘空间
	# 这两处保留失败忽略：源码目录可能本来就不存在（编译脚本已自行清理），
	# 清理失败也不该让「已装好的 PHP」判成安装失败。
	rm -rf "${serverPath}/source/php/php${type}" 2>/dev/null || true  # yf-keep: 中间目录可能已不存在
	rm -rf "${serverPath}/source/php${type}" 2>/dev/null || true      # yf-keep: 中间目录可能已不存在

	# 统一执行一次最终重启并探活
	yf_optional_step --quiet "清理 systemd 失败计数（reset-failed php${type}）" systemctl reset-failed php${type}
	yf_optional_step --quiet "重新加载 systemd 单元（daemon-reload）" systemctl daemon-reload
	yf_optional_step "重启 PHP${type} 服务（systemctl/service/lib.sh 三级兜底）" _yf_php_restart
	sleep 1
	if systemctl is-active --quiet php${type} 2>/dev/null; then
		echo "PHP${type} service is active and running."
	else
		echo "Notice: PHP${type} service status:"
		# 探活失败时打印一段诊断信息；status 本身失败没有额外含义，属纯诊断输出
		systemctl status php${type} --no-pager -l 2>/dev/null | tail -n 15 || true  # yf-keep: 纯诊断输出
	fi

	if [ ! -f /usr/local/bin/composer ] && [ "$sysName" != "Darwin" ] ;then
		echo "Installing Composer..."
		cd /tmp
		yf_optional_step "安装 Composer（可选组件，缺失不影响 PHP 运行）" _yf_php_composer_install
	fi

	yf_install_report_finish
fi
