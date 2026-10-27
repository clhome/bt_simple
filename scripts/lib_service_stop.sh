#!/bin/bash
# 卸载/重装前的「服务彻底停止」共享函数库（可安全 source 的纯函数）
#
# ## 为什么需要
# 2026-10-27 真机：MySQL 卸载脚本只 `rm -rf $serverPath/mysql`，而 `initd_uninstall`
# 只 `disable` 不 `stop`。于是 mysqld 带着**已删除的 datadir/socket/可执行文件**
# 继续占着 3306；重装时 start() 看到 `getMysqldPid()` 命中这个僵尸 → 判定「已在运行」
# → **初始化被整段跳过** → data 目录造不出来 → 面板 ORM 退回 TCP 连到僵尸 → 1045
# 「数据库密码错误」，怎么点【修复】都没用。
#
# 同族问题排查：redis / valkey / mongodb / gitea / pureftp / rsyncd / supervisor /
# sphinx / postgresql / openresty / apache / php-fpm 的卸载都只有
# `systemctl stop <unit>`（外加 `initd stop`）。**只要进程不是该 unit 起的**
# （上一次卸载删了 unit 但没杀进程 / 手工启动 / unit 改名），就杀不掉，症状与 MySQL 同款。
#
# ## 口径
#   yf_svc_stop_units   <unit...>        停 + disable（systemctl/initd 都试，尽力而为）
#   yf_kill_by_exe_prefix <abs-dir>      杀掉 **可执行文件位于该目录下** 的进程
#                                        （/proc/<pid>/exe 前缀匹配；TERM→KILL）
#   yf_svc_rm_units     <unit...>        删 unit 文件 + daemon-reload
#   yf_svc_force_stop   <abs-dir> [unit...]
#                                        组合包：停 unit → 按 exe 归属杀 → 删 unit
#                                        → 回读是否还有残留（返回 1 表示没清干净）
#
# 注意：`yf_kill_by_exe_prefix` 只按**可执行文件路径**匹配，不会因为进程名相同就
# 杀掉系统里另一套同名服务（例如 /usr/sbin/mysqld 与我们 /www/server/mysql/bin/mysqld）。

# /proc 里的 exe 软链；对「文件已删但进程还在」的情况会带 ' (deleted)' 后缀，需要去掉
_yf_svc_pid_exe() {
	local _pid="$1"
	local _exe=""
	[ -r "/proc/${_pid}/exe" ] || return 1
	_exe=$(readlink "/proc/${_pid}/exe" 2>/dev/null) || return 1
	case "${_exe}" in
		*" (deleted)") _exe="${_exe% (deleted)}" ;;
	esac
	printf '%s' "${_exe}"
}

# yf_kill_by_exe_prefix <abs-dir> [term-wait 秒]
#   杀掉可执行文件位于 <abs-dir> 之下的所有进程；输出被处理的 pid 列表（可能为空）。
#   返回 0 表示「目录下已无进程」，1 表示仍有残留（或参数非法）。
yf_kill_by_exe_prefix() {
	local _dir="${1:-}"
	local _wait="${2:-3}"
	local _prefix _pids _pid _exe _alive _i

	case "${_dir}" in
		'' | '/' | '/usr' | '/usr/' | '/bin' | '/sbin' | '/etc' | '/var' | '/home')
			echo "[ERROR] yf_kill_by_exe_prefix: 拒绝在危险路径上按前缀杀进程: '${_dir}'" >&2
			return 1
			;;
	esac
	[ -d "${_dir}" ] || return 0     # 目录都不在了：没有「属于它」的进程可杀
	[ -d /proc ] || return 0         # 非 Linux：不做这种自杀式清理

	_prefix="$(cd "${_dir}" 2>/dev/null && pwd -P)" || return 0
	_prefix="${_prefix%/}/"

	_pids=""
	for _p in /proc/[0-9]*; do
		_pid="${_p#/proc/}"
		_exe=$(_yf_svc_pid_exe "${_pid}") || continue
		case "${_exe}" in
			"${_prefix}"*) _pids="${_pids} ${_pid}" ;;
		esac
	done

	if [ -z "${_pids}" ]; then
		return 0
	fi

	echo "[svc] 发现 ${_prefix} 下的残留进程:${_pids}，先 TERM" >&2
	for _pid in ${_pids}; do
		kill "${_pid}" 2>/dev/null
	done
	_i=0
	while [ "${_i}" -lt "${_wait}" ]; do
		_alive=""
		for _pid in ${_pids}; do
			kill -0 "${_pid}" 2>/dev/null && _alive="${_alive} ${_pid}"
		done
		[ -z "${_alive}" ] && break
		sleep 1
		_i=$((_i + 1))
	done

	_alive=""
	for _pid in ${_pids}; do
		kill -0 "${_pid}" 2>/dev/null && _alive="${_alive} ${_pid}"
	done
	if [ -n "${_alive}" ]; then
		echo "[svc] TERM 未退出:${_alive}，发送 KILL" >&2
		for _pid in ${_alive}; do
			kill -9 "${_pid}" 2>/dev/null
		done
		sleep 1
	fi

	_alive=""
	for _pid in ${_pids}; do
		kill -0 "${_pid}" 2>/dev/null && _alive="${_alive} ${_pid}"
	done
	if [ -n "${_alive}" ]; then
		echo "[svc][ERROR] 仍有进程杀不掉:${_alive}" >&2
		return 1
	fi
	echo "[svc] 残留进程已清理:${_pids}" >&2
	return 0
}

# yf_svc_stop_units <unit...>：停 + 取消自启（systemd 与 init.d 都试一遍）
yf_svc_stop_units() {
	local _u
	for _u in "$@"; do
		[ -n "${_u}" ] || continue
		if command -v systemctl >/dev/null 2>&1; then
			systemctl stop "${_u}" 2>/dev/null
			systemctl disable "${_u}" 2>/dev/null
		fi
		service "${_u}" stop 2>/dev/null
		# init.d 脚本直接调（面板自己写过 initd 的情况）
		if [ -x "/etc/init.d/${_u}" ]; then
			"/etc/init.d/${_u}" stop 2>/dev/null
		fi
	done
	return 0
}

# yf_svc_rm_units <unit...>：删 unit 文件（两处常见路径）+ daemon-reload
yf_svc_rm_units() {
	local _u
	for _u in "$@"; do
		[ -n "${_u}" ] || continue
		rm -f "/usr/lib/systemd/system/${_u}.service" \
		      "/lib/systemd/system/${_u}.service" \
		      "/etc/systemd/system/${_u}.service" 2>/dev/null
	done
	if command -v systemctl >/dev/null 2>&1; then
		systemctl daemon-reload 2>/dev/null
	fi
	return 0
}

# yf_svc_force_stop <abs-dir> [unit...]
#   卸载/重装前的统一入口：停 unit → 按 exe 归属杀残留 → 删 unit → 回读。
#   返回 0 = 目录下已无进程；1 = 仍有残留（调用方可据此告警，但通常仍继续删目录）。
yf_svc_force_stop() {
	local _dir="${1:-}"
	shift 2>/dev/null || true

	if [ -z "${_dir}" ]; then
		echo "[ERROR] yf_svc_force_stop: 缺少安装目录参数" >&2
		return 1
	fi

	yf_svc_stop_units "$@"
	yf_kill_by_exe_prefix "${_dir}" || true
	yf_svc_rm_units "$@"

	# 回读：目录下还有没有进程
	if [ -d /proc ] && [ -d "${_dir}" ]; then
		local _prefix _pid _exe
		_prefix="$(cd "${_dir}" 2>/dev/null && pwd -P)"
		_prefix="${_prefix%/}/"
		for _p in /proc/[0-9]*; do
			_pid="${_p#/proc/}"
			_exe=$(_yf_svc_pid_exe "${_pid}") || continue
			case "${_exe}" in
				"${_prefix}"*)
					echo "[svc][ERROR] 卸载不彻底：仍有进程 ${_pid} (${_exe}) 在运行" >&2
					return 1
					;;
			esac
		done
	fi
	return 0
}
