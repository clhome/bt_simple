#!/bin/bash
# fail2ban 插件安装 / 卸载脚本
# 约定：UTF-8 无 BOM、LF 换行
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH
export DEBIAN_FRONTEND=noninteractive

# ==========================================================================
# P1-8：严格模式
#   之前的版本只有 `set -o pipefail`，失败命令一律靠 `|| true` 吞掉，
#   面板一律显示「安装完成」。现在任何未被显式判定的失败都会立即中止，
#   ERR trap 负责把「脚本名 + 行号 + 失败命令」打到 stderr（面板任务日志可见）。
#   注：`set -euo pipefail` 等价于 set -e + set -u + set -o pipefail，
#   既有守卫用例按「set -o pipefail」字面断言的写法保留。
# ==========================================================================
set -euo pipefail
trap 'echo "[ERROR] ${BASH_SOURCE[0]}:$LINENO 失败: $BASH_COMMAND" >&2; exit 1' ERR

curPath=$(pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")
YF_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

VERSION=${2:-}
if [ -z "$VERSION" ]; then
	VERSION="1.2.0"
fi

MANUAL_LOG=/var/log/fail2ban-manual.log
BACKUP_DIR="${serverPath}/backup/fail2ban"

# ==========================================================================
# 共享规范库：可选步骤 / 必需步骤统一落账（scripts/lib_install_report.sh）
#   同时兼容两种运行方式：
#     ① 仓库内直跑：plugins/fail2ban/install.sh -> ../../scripts/
#     ② 已安装面板：/www/server/yufeng_panel/scripts/
#   找不到库必须**明确报错退出**——静默跳过等于把严格模式又退回 `|| true`。
# ==========================================================================
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

# cd /www/server/yufeng_panel/plugins/fail2ban && bash install.sh install 1.2.0
# cd /www/server/yufeng_panel && python3 plugins/fail2ban/index.py config_tpl

die()
{
	echo "[错误] $1" >&2
	# 走规范库的失败出口：先把失败项记进报告再 exit 1（面板可定位，不是只留一行日志）
	yf_install_report_fail "${1:-fail2ban 安装中止}" 1 die
}

warn()
{
	echo "[警告] $1" >&2
}

# 报告里逐条说明「哪些 || true 被保留、为什么留」（UI / 审计可见）。
# 只列无法归入 optional 的纯清理/纯探测点，见各行的 `# yf-keep:` 注释。
_yf_report_keep_notes()
{
	yf_install_report_note "保留失败忽略点（共 7 处，均在 clean_leftover 清理函数内，行尾标 yf-keep）：rm -rf / rm -f / rmdir 失败只可能是「路径本来不存在」「目录非空」「权限不足」三种情况，都不代表安装缺失；若把它们记成缺失项，每次正常卸载都会刷 5~7 条假告警，运行目录/日志的清理失败也不应阻断卸载。"
}

# dpkg 中断状态修复：机器上没有待配置的包时 dpkg 也可能返回非 0，属「真可选」。

# APT 安装 fail2ban：先按「本体 + 依赖」整体装，整体失败再退化为只装本体。
# 两步都失败才算安装失败（由调用方的 yf_require_step 负责中止）。
_install_pkg_apt()
{
	if apt-get install -o Dpkg::Options::=--force-confmiss \
		-o Dpkg::Options::=--force-confdef \
		-o Dpkg::Options::=--force-confnew \
		-y fail2ban iptables ipset python3-systemd; then
		return 0
	fi
	echo "[警告] fail2ban + iptables + ipset + python3-systemd 整体安装失败，退化为仅安装 fail2ban" >&2
	apt-get install -o Dpkg::Options::=--force-confmiss \
		-o Dpkg::Options::=--force-confdef \
		-o Dpkg::Options::=--force-confnew \
		-y fail2ban
}

# dnf / yum 安装 fail2ban：同样的「整体 -> 仅本体」退化策略。$1 = dnf|yum
_install_pkg_rpm()
{
	local _mgr="${1:-yum}"
	if "$_mgr" install -y fail2ban iptables ipset; then
		return 0
	fi
	echo "[警告] ${_mgr} 安装 fail2ban + iptables + ipset 失败，退化为仅安装 fail2ban" >&2
	"$_mgr" install -y fail2ban
}

# 安装 fail2ban 及其运行依赖：
#   iptables / ipset   —— 封禁动作（banaction_allports）依赖
#   python3-systemd    —— backend = systemd 时读取日志依赖
install_pkg()
{
	if command -v apt-get >/dev/null 2>&1; then
		yf_optional_step --quiet "修复 dpkg 中断状态（dpkg --configure -a）" dpkg --configure -a
		# 源索引刷新失败不一定是致命的（本地缓存仍可装），但必须进报告，不许静默
		yf_optional_step --quiet "刷新 APT 源索引（apt-get update -qq）" apt-get update -qq
		# 本体 + 封禁/日志依赖是必需的：装不上就中止（原来这里靠 || true 吞掉）
		yf_require_step "安装 fail2ban 及 iptables/ipset/python3-systemd 依赖" _install_pkg_apt
		# rsyslog 只有 backend=file 时才需要，缺它不影响主流程
		yf_optional_step --quiet "安装 rsyslog（file backend 可选依赖）" apt-get install -y rsyslog
		return 0
	fi

	if command -v dnf >/dev/null 2>&1; then
		# epel-release 已装时 dnf 会返回非 0，属「真可选」
		yf_optional_step --quiet "安装 EPEL 源（dnf install epel-release，已装会返回非 0）" dnf install -y epel-release
		yf_require_step "安装 fail2ban 及 iptables/ipset 依赖（dnf）" _install_pkg_rpm dnf
		return 0
	fi

	if command -v yum >/dev/null 2>&1; then
		yf_optional_step --quiet "安装 EPEL 源（yum install epel-release，已装会返回非 0）" yum install -y epel-release
		yf_require_step "安装 fail2ban 及 iptables/ipset 依赖（yum）" _install_pkg_rpm yum
		return 0
	fi

	warn '未识别的包管理器（没有 apt-get / dnf / yum），请手动安装 fail2ban'
	return 1
}

# 校验安装是否真正生效（避免装失败却继续启动）
verify_install()
{
	command -v fail2ban-client >/dev/null 2>&1
}

# 启动服务 / 写开机自启：在 plugins 根目录下执行 index.py（它按自身路径定位资源）
_yf_plugin_index()
{
	(
		cd "${rootPath}" &&
			python3 "${rootPath}/plugins/fail2ban/index.py" "$@"
	)
}

Install_App()
{
	yf_install_report_init fail2ban
	_yf_report_keep_notes

	echo '正在安装脚本文件...'
	mkdir -p "${serverPath}/source"

	# 创建前置运行目录与日志占位文件
	mkdir -p /run/fail2ban
	mkdir -p /var/lib/fail2ban
	mkdir -p /www/wwwlogs
	[ -f /www/wwwlogs/default.log ] || touch /www/wwwlogs/default.log
	[ -f "$MANUAL_LOG" ] || touch "$MANUAL_LOG"

	echo '正在安装 fail2ban 依赖...'
	yf_require_step "安装 fail2ban 及其运行依赖" install_pkg

	if ! verify_install; then
		die '未检测到 fail2ban-client，安装未生效，已中止'
	fi

	mkdir -p "${serverPath}/fail2ban"
	echo "${VERSION}" > "${serverPath}/fail2ban/version.pl"
	echo '安装fail2ban完成'

	# 启动与开机自启失败不推翻「已安装」的结论，但必须记进缺失清单（原来只 warn）
	yf_optional_step "启动 fail2ban 服务（index.py start）" _yf_plugin_index start
	yf_optional_step "配置 fail2ban 开机自启（index.py initd_install）" _yf_plugin_index initd_install

	yf_install_report_finish
}

# 停止服务（systemd / SysV / 客户端三路兜底）—— 服务不存在时各路都会返回非 0，
# 全部按「真可选」处理：记进报告，但绝不阻断卸载。
stop_service()
{
	if command -v systemctl >/dev/null 2>&1; then
		yf_optional_step --quiet "停止 fail2ban 服务（systemctl stop）" systemctl stop fail2ban
		yf_optional_step --quiet "取消 fail2ban 自启（systemctl disable）" systemctl disable fail2ban
	fi
	if [ -x "${serverPath}/fail2ban/initd/fail2ban" ]; then
		yf_optional_step --quiet "停止 fail2ban 服务（initd stop）" "${serverPath}/fail2ban/initd/fail2ban" stop
	fi
	if command -v fail2ban-client >/dev/null 2>&1; then
		yf_optional_step --quiet "停止 fail2ban 进程（fail2ban-client stop）" fail2ban-client stop
	fi
}

# 卸载前备份 /etc/fail2ban，避免用户自定义过滤器/监狱配置丢失
backup_etc()
{
	[ -d /etc/fail2ban ] || return 0
	mkdir -p "$BACKUP_DIR"
	local ts=""
	ts=$(date +%Y%m%d%H%M%S)
	if tar -czf "${BACKUP_DIR}/etc_fail2ban_${ts}.tar.gz" -C /etc fail2ban >/dev/null 2>&1; then
		echo "已备份原配置到 ${BACKUP_DIR}/etc_fail2ban_${ts}.tar.gz"
	else
		warn "备份 /etc/fail2ban 失败（继续卸载，但自定义配置可能丢失）：${BACKUP_DIR}/etc_fail2ban_${ts}.tar.gz"
	fi
}

remove_service_unit()
{
	local unit=""
	for unit in /usr/lib/systemd/system/fail2ban.service \
		/lib/systemd/system/fail2ban.service \
		/etc/systemd/system/fail2ban.service; do
		[ -f "$unit" ] && rm -f "$unit"
	done
	if command -v systemctl >/dev/null 2>&1; then
		yf_optional_step --quiet "重新加载 systemd 单元（systemctl daemon-reload）" systemctl daemon-reload
	fi
	return 0
}

# 卸载软件包（iptables / ipset 为系统级依赖，不随插件卸载）
# 卸载阶段的目标是「能删就删干净」，单个包 purge/remove 失败不阻断收尾清理，
# 因此全部记为可选缺失项（原来 4 处 || true 静默吞掉，现在进报告）。
remove_pkg()
{
	if command -v apt-get >/dev/null 2>&1; then
		yf_optional_step --quiet "修复 dpkg 中断状态（卸载前）" dpkg --configure -a
		yf_optional_step --quiet "卸载 fail2ban 包（apt-get purge）" apt-get purge -y fail2ban
		yf_optional_step --quiet "清理无用依赖（apt-get autoremove）" apt-get autoremove -y
		return 0
	fi
	if command -v dnf >/dev/null 2>&1; then
		yf_optional_step --quiet "卸载 fail2ban 包（dnf remove）" dnf remove -y fail2ban
		return 0
	fi
	if command -v yum >/dev/null 2>&1; then
		yf_optional_step --quiet "卸载 fail2ban 包（yum remove）" yum remove -y fail2ban
		return 0
	fi
	return 0
}

# 包管理器卸载后仍残留在 /etc/fail2ban 的文件视为用户自定义配置，予以保留
preserve_or_remove_etc()
{
	[ -d /etc/fail2ban ] || return 0
	if [ -z "$(find /etc/fail2ban -type f -print -quit 2>/dev/null)" ]; then
		rm -rf /etc/fail2ban
	else
		warn "/etc/fail2ban 中存在用户自定义配置，已保留（备份见 ${BACKUP_DIR}）"
	fi
}

# 清理运行与数据残留
# 下面 7 行行尾的失败忽略是**故意保留**的（报告 notes 里已逐条说明）：
# rm/rmdir 失败只可能是「路径不存在 / 目录非空 / 权限不足」，都不构成安装缺失，
# 也不该让卸载失败。每行都带 `yf-keep` 标记，供 P1-8 的棘轮守卫识别。
clean_leftover()
{
	rm -rf /var/lib/fail2ban 2>/dev/null || true          # yf-keep: 残留目录，不存在属正常
	rm -rf /run/fail2ban 2>/dev/null || true              # yf-keep: 运行目录，不存在属正常
	rm -f /var/run/fail2ban/fail2ban.sock 2>/dev/null || true  # yf-keep: 套接字可能已被删
	rmdir /var/run/fail2ban 2>/dev/null || true           # yf-keep: 目录非空/不存在都算正常
	rm -f /var/log/fail2ban.log 2>/dev/null || true       # yf-keep: 日志可能从未生成
	rm -f /var/log/fail2ban.log.[0-9]* 2>/dev/null || true # yf-keep: 轮转日志可能不存在
	rm -f "$MANUAL_LOG" 2>/dev/null || true               # yf-keep: 手动日志可能从未生成
}

Uninstall_App()
{
	yf_install_report_init fail2ban
	_yf_report_keep_notes

	echo '正在卸载 fail2ban...'
	stop_service
	backup_etc
	remove_service_unit
	remove_pkg
	preserve_or_remove_etc
	clean_leftover

	if [ -d "${serverPath}/fail2ban" ]; then
		rm -rf "${serverPath}/fail2ban"
	fi

	echo "卸载fail2ban成功"
	yf_install_report_finish
}

action=${1:-}
case "$action" in
	install)
		Install_App
		;;
	uninstall)
		Uninstall_App
		;;
	*)
		echo "Usage: bash install.sh {install|uninstall} [version]"
		exit 1
		;;
esac
