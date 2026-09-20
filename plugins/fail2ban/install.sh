#!/bin/bash
# fail2ban 插件安装 / 卸载脚本
# 约定：UTF-8 无 BOM、LF 换行
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH
export DEBIAN_FRONTEND=noninteractive
set -o pipefail

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

VERSION=$2
if [ -z "$VERSION" ]; then
	VERSION="1.2.0"
fi

MANUAL_LOG=/var/log/fail2ban-manual.log
BACKUP_DIR="${serverPath}/backup/fail2ban"

# cd /www/server/yufeng_panel/plugins/fail2ban && bash install.sh install 1.2.0
# cd /www/server/yufeng_panel && python3 plugins/fail2ban/index.py config_tpl

die()
{
	echo "[错误] $1" >&2
	exit 1
}

warn()
{
	echo "[警告] $1" >&2
}

# 安装 fail2ban 及其运行依赖：
#   iptables / ipset   —— 封禁动作（banaction_allports）依赖
#   python3-systemd    —— backend = systemd 时读取日志依赖
install_pkg()
{
	if command -v apt-get >/dev/null 2>&1; then
		dpkg --configure -a >/dev/null 2>&1 || true
		apt-get update -qq >/dev/null 2>&1 || true
		apt-get install -o Dpkg::Options::="--force-confmiss" \
			-o Dpkg::Options::="--force-confdef" \
			-o Dpkg::Options::="--force-confnew" \
			-y fail2ban iptables ipset python3-systemd || \
		apt-get install -o Dpkg::Options::="--force-confmiss" \
			-o Dpkg::Options::="--force-confdef" \
			-o Dpkg::Options::="--force-confnew" \
			-y fail2ban || return 1
		apt-get install -y rsyslog >/dev/null 2>&1 || true
		return 0
	fi

	if command -v dnf >/dev/null 2>&1; then
		dnf install -y epel-release >/dev/null 2>&1 || true
		dnf install -y fail2ban iptables ipset || dnf install -y fail2ban || return 1
		return 0
	fi

	if command -v yum >/dev/null 2>&1; then
		yum install -y epel-release >/dev/null 2>&1 || true
		yum install -y fail2ban iptables ipset || yum install -y fail2ban || return 1
		return 0
	fi

	warn '未识别的包管理器，请手动安装 fail2ban'
	return 1
}

# 校验安装是否真正生效（避免装失败却继续启动）
verify_install()
{
	command -v fail2ban-client >/dev/null 2>&1
}

Install_App()
{
	echo '正在安装脚本文件...'
	mkdir -p $serverPath/source

	# 创建前置运行目录与日志占位文件
	mkdir -p /run/fail2ban
	mkdir -p /var/lib/fail2ban
	mkdir -p /www/wwwlogs
	[ -f /www/wwwlogs/default.log ] || touch /www/wwwlogs/default.log
	[ -f "$MANUAL_LOG" ] || touch "$MANUAL_LOG"

	echo '正在安装 fail2ban 依赖...'
	if ! install_pkg; then
		die 'fail2ban 安装失败，请检查网络或软件源后重试'
	fi

	if ! verify_install; then
		die '未检测到 fail2ban-client，安装未生效，已中止'
	fi

	mkdir -p $serverPath/fail2ban
	echo "${VERSION}" > $serverPath/fail2ban/version.pl
	echo '安装fail2ban完成'

	cd ${rootPath} && python3 ${rootPath}/plugins/fail2ban/index.py start \
		|| warn 'fail2ban 启动失败，请在面板中查看运行日志'
	cd ${rootPath} && python3 ${rootPath}/plugins/fail2ban/index.py initd_install \
		|| warn 'fail2ban 开机自启配置失败，请在面板中重新开启'
}

# 停止服务（systemd / SysV / 客户端三路兜底）
stop_service()
{
	if command -v systemctl >/dev/null 2>&1; then
		systemctl stop fail2ban >/dev/null 2>&1 || true
		systemctl disable fail2ban >/dev/null 2>&1 || true
	fi
	if [ -x "${serverPath}/fail2ban/initd/fail2ban" ]; then
		"${serverPath}/fail2ban/initd/fail2ban" stop >/dev/null 2>&1 || true
	fi
	if command -v fail2ban-client >/dev/null 2>&1; then
		fail2ban-client stop >/dev/null 2>&1 || true
	fi
}

# 卸载前备份 /etc/fail2ban，避免用户自定义过滤器/监狱配置丢失
backup_etc()
{
	[ -d /etc/fail2ban ] || return 0
	mkdir -p "$BACKUP_DIR"
	ts=$(date +%Y%m%d%H%M%S)
	if tar -czf "${BACKUP_DIR}/etc_fail2ban_${ts}.tar.gz" -C /etc fail2ban >/dev/null 2>&1; then
		echo "已备份原配置到 ${BACKUP_DIR}/etc_fail2ban_${ts}.tar.gz"
	fi
}

remove_service_unit()
{
	for unit in /usr/lib/systemd/system/fail2ban.service \
				/lib/systemd/system/fail2ban.service \
				/etc/systemd/system/fail2ban.service; do
		[ -f "$unit" ] && rm -f "$unit"
	done
	if command -v systemctl >/dev/null 2>&1; then
		systemctl daemon-reload >/dev/null 2>&1 || true
	fi
}

# 卸载软件包（iptables / ipset 为系统级依赖，不随插件卸载）
remove_pkg()
{
	if command -v apt-get >/dev/null 2>&1; then
		dpkg --configure -a >/dev/null 2>&1 || true
		apt-get purge -y fail2ban >/dev/null 2>&1 || true
		apt-get autoremove -y >/dev/null 2>&1 || true
		return 0
	fi
	if command -v dnf >/dev/null 2>&1; then
		dnf remove -y fail2ban >/dev/null 2>&1 || true
		return 0
	fi
	if command -v yum >/dev/null 2>&1; then
		yum remove -y fail2ban >/dev/null 2>&1 || true
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
clean_leftover()
{
	rm -rf /var/lib/fail2ban 2>/dev/null || true
	rm -rf /run/fail2ban 2>/dev/null || true
	rm -f /var/run/fail2ban/fail2ban.sock 2>/dev/null || true
	rmdir /var/run/fail2ban 2>/dev/null || true
	rm -f /var/log/fail2ban.log 2>/dev/null || true
	rm -f /var/log/fail2ban.log.[0-9]* 2>/dev/null || true
	rm -f "$MANUAL_LOG" 2>/dev/null || true
}

Uninstall_App()
{
	echo '正在卸载 fail2ban...'
	stop_service
	backup_etc
	remove_service_unit
	remove_pkg
	preserve_or_remove_etc
	clean_leftover

	if [ -d $serverPath/fail2ban ]; then
		rm -rf $serverPath/fail2ban
	fi

	echo "卸载fail2ban成功"
}

action=$1
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
