#!/bin/bash
# ==========================================================================
# 御风面板 —— 插件安装「可选/必需步骤」统一落账库（P1-8）
#
# 约定：UTF-8 无 BOM、LF 换行；纯 bash，不依赖 jq / python 等外部程序，
#       可被已经 `set -euo pipefail` 的 install.sh 直接 `source`（本文件内部
#       不做任何会被 errexit 反噬的裸命令调用）。
#
# 为什么需要它：整改前 36 个 plugins/*/install.sh 里 0 个用 `set -e`，另有 49 处
# `|| true` 把「装失败」的退出码吞掉 —— 面板显示「安装完成」，实际缺了半天扩展，
# 用户最后只能靠 `php -m` 自己发现。这个库把「每个命令失败意味着什么」显式化：
#
#   yf_optional_step "<描述>" <命令...>   真可选：失败不中止，记进 missing 列表并打 [WARN]
#   yf_require_step  "<描述>" <命令...>   必需：失败打 [ERROR]，记进 failed 列表后 exit 1
#
# 用法（完整示例见 plugins/fail2ban/install.sh）：
#   . .../scripts/lib_install_report.sh
#   yf_install_report_init fail2ban
#   yf_optional_step --quiet "安装 rsyslog（可选，缺它只影响 file backend）" \
#       apt-get install -y rsyslog
#   yf_require_step "安装 fail2ban 及 iptables/ipset 依赖" \
#       apt-get install -y fail2ban iptables ipset
#   yf_install_report_note "保留 || true：清理残留目录，路径不存在属正常"
#   yf_install_report_finish
#
# 报告文件：$(yf_install_report_path <plugin>)
#           = ${serverPath:-/www/server}/plugin_install_report/<plugin>.json
#           （测试/离线用 YF_INSTALL_REPORT_DIR 覆盖根目录，见 yf_install_report_dir）
#
# 报告结构（python -c 'import json,sys; print(json.load(open(sys.argv[1])))' 可直接解析）：
# {
#   "plugin": "fail2ban",
#   "status": "ok" | "degraded" | "failed",
#   "started_at": "2026-02-01 10:00:00", "finished_at": "...", "duration_seconds": 12,
#   "server_path": "/www/server",
#   "report_path": "/www/server/plugin_install_report/fail2ban.json",
#   "missing": [{"step": "安装 rsyslog", "exit_code": 100, "command": "apt-get"}],
#   "failed":  [{"step": "安装 fail2ban", "exit_code": 100, "command": "apt-get"}],
#   "notes":   ["保留 || true：..."],
#   "missing_count": 1, "failed_count": 0,
#   "schema_version": 1
# }
#   status: failed=有必需步骤失败；degraded=没有必需步骤失败但有缺失项；ok=全成功。
#
# 与 UI 的契约：UI 只读这个 JSON，不需要解析安装日志。缺失项非空时面板应把
# 「安装完成（有 N 项缺失）」连同 missing[*].step 展示出来，而不是直接报「成功」。
# ==========================================================================

# 模块级状态（source 前已存在的值会被 init 重置；这里给默认值是为了在
# `set -u` 下即使没调 init 也不会 unbound）。
YF_REPORT_SCHEMA_VERSION=1
YF_REPORT_PLUGIN=""
YF_REPORT_STARTED_AT=""
YF_REPORT_STARTED_EPOCH=""
YF_REPORT_MISSING_STEP=()
YF_REPORT_MISSING_RC=()
YF_REPORT_MISSING_CMD=()
YF_REPORT_FAILED_STEP=()
YF_REPORT_FAILED_RC=()
YF_REPORT_FAILED_CMD=()
YF_REPORT_NOTES=()

#: 最近一次 yf_optional_step / yf_require_step 执行的退出码。
#: yf_optional_step 恒返回 0（否则会被调用方的 `set -e` 当成致命错误），
#: 需要按失败结果做后续分支时读这个变量。
YF_LAST_STEP_RC=0

# --------------------------------------------------------------------------
# 报告路径
# --------------------------------------------------------------------------

# yf_install_report_dir
#   打印报告根目录。优先级：$YF_INSTALL_REPORT_DIR（测试/离线用） >
#   ${serverPath:-/www/server}/plugin_install_report
#   之所以留 serverPath 兜底，是因为 install.sh 在「仓库内直跑」时 serverPath
#   会被推导成仓库父目录，不一定是 /www/server。
yf_install_report_dir()
{
	if [ -n "${YF_INSTALL_REPORT_DIR:-}" ]; then
		printf '%s' "${YF_INSTALL_REPORT_DIR}"
		return 0
	fi
	printf '%s' "${serverPath:-/www/server}/plugin_install_report"
}

# yf_install_report_path <plugin>
#   打印某个插件的报告文件绝对路径（供 UI / 测试 / 运维直接读取）。
yf_install_report_path()
{
	printf '%s/%s.json' "$(yf_install_report_dir)" "${1:-unknown}"
}

# --------------------------------------------------------------------------
# 内部工具
# --------------------------------------------------------------------------

# _yf_json_escape <字符串>
#   把任意文本转成可以安全塞进 JSON 双引号里的形式（反斜杠、双引号、换行、
#   回车、制表符）。只做 JSON 必需的最小转义，不含任何外部依赖。
_yf_json_escape()
{
	local _s="${1:-}"
	local _nl=$'\n'
	local _cr=$'\r'
	local _tab=$'\t'
	_s=${_s//\\/\\\\}
	_s=${_s//\"/\\\"}
	_s=${_s//${_nl}/\\n}
	_s=${_s//${_cr}/\\r}
	_s=${_s//${_tab}/\\t}
	printf '%s' "${_s}"
}

# _yf_report_append <missing|failed> <描述> <退出码> <命令首词>
#   追加一条记录。用 `${#arr[@]}` 当下标而不是 `arr+=(...)`，保证 bash 3.2
#   （macOS 自带）也能跑。
_yf_report_append()
{
	local _kind="${1:-}"
	local _step="${2:-}"
	local _rc="${3:-0}"
	local _cmd="${4:-}"
	case "${_kind}" in
		missing)
			YF_REPORT_MISSING_STEP[${#YF_REPORT_MISSING_STEP[@]}]="${_step}"
			YF_REPORT_MISSING_RC[${#YF_REPORT_MISSING_RC[@]}]="${_rc}"
			YF_REPORT_MISSING_CMD[${#YF_REPORT_MISSING_CMD[@]}]="${_cmd}"
			;;
		failed)
			YF_REPORT_FAILED_STEP[${#YF_REPORT_FAILED_STEP[@]}]="${_step}"
			YF_REPORT_FAILED_RC[${#YF_REPORT_FAILED_RC[@]}]="${_rc}"
			YF_REPORT_FAILED_CMD[${#YF_REPORT_FAILED_CMD[@]}]="${_cmd}"
			;;
		*)
			return 0
			;;
	esac
	return 0
}

# _yf_report_duration
#   打印从 init 到现在的秒数（无法计算时打印 0）。
_yf_report_duration()
{
	local _now=0
	local _start="${YF_REPORT_STARTED_EPOCH:-0}"
	_now=$(date +%s 2>/dev/null || echo 0)
	case "${_start}" in
		'' | *[!0-9]*) _start=0 ;;
	esac
	case "${_now}" in
		'' | *[!0-9]*) _now=0 ;;
	esac
	if [ "${_start}" -le 0 ] || [ "${_now}" -lt "${_start}" ]; then
		printf '0'
		return 0
	fi
	printf '%s' "$((_now - _start))"
}

# _yf_report_emit_json
#   把当前状态以 JSON 形式打到 stdout（纯输出，不碰文件系统）。
#   拆成独立函数是为了让「重定向失败」也能被 `if !` 捕获，不会在 set -e 下
#   把一次成功的安装变成失败。
_yf_report_emit_json()
{
	local _plugin="${YF_REPORT_PLUGIN:-unknown}"
	local _status="ok"
	local _missing_n=${#YF_REPORT_MISSING_STEP[@]}
	local _failed_n=${#YF_REPORT_FAILED_STEP[@]}
	local _notes_n=${#YF_REPORT_NOTES[@]}
	local _target=""
	local _i=0
	local _sep=""

	_target=$(yf_install_report_path "${_plugin}")

	if [ "${_failed_n}" -gt 0 ]; then
		_status="failed"
	elif [ "${_missing_n}" -gt 0 ]; then
		_status="degraded"
	fi

	printf '{\n'
	printf '  "schema_version": %s,\n' "${YF_REPORT_SCHEMA_VERSION}"
	printf '  "plugin": "%s",\n' "$(_yf_json_escape "${_plugin}")"
	printf '  "status": "%s",\n' "${_status}"
	printf '  "started_at": "%s",\n' "$(_yf_json_escape "${YF_REPORT_STARTED_AT}")"
	printf '  "finished_at": "%s",\n' "$(_yf_json_escape "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo '')")"
	printf '  "duration_seconds": %s,\n' "$(_yf_report_duration)"
	printf '  "server_path": "%s",\n' "$(_yf_json_escape "${serverPath:-}")"
	printf '  "report_path": "%s",\n' "$(_yf_json_escape "${_target}")"

	printf '  "missing": ['
	_sep=""
	for ((_i = 0; _i < _missing_n; _i++)); do
		printf '%s\n    {"step": "%s", "exit_code": %s, "command": "%s"}' \
			"${_sep}" \
			"$(_yf_json_escape "${YF_REPORT_MISSING_STEP[_i]}")" \
			"${YF_REPORT_MISSING_RC[_i]:-0}" \
			"$(_yf_json_escape "${YF_REPORT_MISSING_CMD[_i]}")"
		_sep=","
	done
	if [ "${_missing_n}" -gt 0 ]; then printf '\n  '; fi
	printf '],\n'

	printf '  "failed": ['
	_sep=""
	for ((_i = 0; _i < _failed_n; _i++)); do
		printf '%s\n    {"step": "%s", "exit_code": %s, "command": "%s"}' \
			"${_sep}" \
			"$(_yf_json_escape "${YF_REPORT_FAILED_STEP[_i]}")" \
			"${YF_REPORT_FAILED_RC[_i]:-0}" \
			"$(_yf_json_escape "${YF_REPORT_FAILED_CMD[_i]}")"
		_sep=","
	done
	if [ "${_failed_n}" -gt 0 ]; then printf '\n  '; fi
	printf '],\n'

	printf '  "notes": ['
	_sep=""
	for ((_i = 0; _i < _notes_n; _i++)); do
		printf '%s\n    "%s"' "${_sep}" "$(_yf_json_escape "${YF_REPORT_NOTES[_i]}")"
		_sep=","
	done
	if [ "${_notes_n}" -gt 0 ]; then printf '\n  '; fi
	printf '],\n'

	printf '  "missing_count": %s,\n' "${_missing_n}"
	printf '  "failed_count": %s\n' "${_failed_n}"
	printf '}\n'
	return 0
}

# _yf_report_write_json
#   把当前状态落盘（先写 .tmp 再 mv，避免 UI 读到半截 JSON）。
#   失败返回 1，由调用方决定是否 [WARN]（安装本身成功时不该因为写报告失败而失败）。
_yf_report_write_json()
{
	local _dir=""
	local _target=""
	local _tmp=""

	_dir=$(yf_install_report_dir)
	_target=$(yf_install_report_path "${YF_REPORT_PLUGIN:-unknown}")

	if ! mkdir -p "${_dir}" 2>/dev/null; then
		echo "[WARN] 无法创建报告目录 ${_dir}" >&2
		return 1
	fi

	_tmp="${_target}.tmp.$$"
	if ! _yf_report_emit_json > "${_tmp}" 2>/dev/null; then
		echo "[WARN] 无法写入报告临时文件 ${_tmp}" >&2
		rm -f "${_tmp}" 2>/dev/null
		return 1
	fi

	if [ ! -s "${_tmp}" ]; then
		echo "[WARN] 报告临时文件为空 ${_tmp}" >&2
		rm -f "${_tmp}" 2>/dev/null
		return 1
	fi

	if ! mv -f "${_tmp}" "${_target}" 2>/dev/null; then
		echo "[WARN] 无法写入报告文件 ${_target}" >&2
		rm -f "${_tmp}" 2>/dev/null
		return 1
	fi
	return 0
}

# ---------------- 对外 5 个函数（报告四件套 + 失败中止） ----------------

# yf_install_report_init <plugin_name>
#   初始化一份新报告：重置缺失/失败/备注列表，记录插件名与开始时间。
#   必须在任何 yf_optional_step / yf_require_step 之前调用（否则记录会落到
#   空插件名下）。
yf_install_report_init()
{
	YF_REPORT_PLUGIN="${1:-unknown}"
	YF_REPORT_STARTED_AT=$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo '')
	YF_REPORT_STARTED_EPOCH=$(date +%s 2>/dev/null || echo 0)
	YF_REPORT_MISSING_STEP=()
	YF_REPORT_MISSING_RC=()
	YF_REPORT_MISSING_CMD=()
	YF_REPORT_FAILED_STEP=()
	YF_REPORT_FAILED_RC=()
	YF_REPORT_FAILED_CMD=()
	YF_REPORT_NOTES=()
	YF_LAST_STEP_RC=0
	return 0
}

# yf_optional_step [--quiet] "<描述>" <命令...>
#   执行「真可选」步骤：失败**不中止**，把缺失项（描述 / 退出码 / 命令首词）
#   追加进报告 missing 列表，并在 stderr 打 [WARN]。
#   --quiet：把该命令自身的输出丢弃（等价于原来的 `>/dev/null 2>&1`），
#            但 [WARN] 仍然可见 —— 这正是整改前 `|| true` 做不到的事。
#   恒返回 0；需要判断成败时读 $YF_LAST_STEP_RC。
yf_optional_step()
{
	local _quiet=0
	local _desc=""
	local _cmd=""
	local _rc=0

	if [ "${1:-}" = "--quiet" ]; then
		_quiet=1
		shift
	fi
	_desc="${1:-}"
	if [ "$#" -gt 0 ]; then
		shift
	fi
	_cmd="${1:-}"

	if [ "$#" -eq 0 ]; then
		YF_LAST_STEP_RC=0
		return 0
	fi

	if [ "${_quiet}" = "1" ]; then
		if "$@" >/dev/null 2>&1; then
			_rc=0
		else
			_rc=$?
		fi
	else
		if "$@"; then
			_rc=0
		else
			_rc=$?
		fi
	fi

	YF_LAST_STEP_RC=${_rc}
	if [ "${_rc}" -ne 0 ]; then
		_yf_report_append missing "${_desc}" "${_rc}" "${_cmd}"
		echo "[WARN] 可选步骤失败（已记入缺失清单）：${_desc}（退出码 ${_rc}，命令 ${_cmd}）" >&2
	fi
	return 0
}

# yf_install_report_fail "<描述>" [退出码] [命令首词]
#   把一条「必需步骤失败」记进报告 failed 列表，打 [ERROR]，落盘后 exit 1。
#   yf_require_step 与各插件的 die() 共用它（die 失败时同样要有报告可查）。
#   恒不返回（进程退出）。
yf_install_report_fail()
{
	local _desc="${1:-未知失败}"
	local _rc="${2:-1}"
	local _cmd="${3:-}"

	case "${_rc}" in
		'' | *[!0-9]*) _rc=1 ;;
	esac
	_yf_report_append failed "${_desc}" "${_rc}" "${_cmd}"
	echo "[ERROR] 必需步骤失败：${_desc}（退出码 ${_rc}，命令 ${_cmd:-?}），安装已中止" >&2
	# 失败也要留证据：把（含 failed 项的）报告写出来，供面板/运维定位
	if ! _yf_report_write_json >/dev/null 2>&1; then
		echo "[WARN] 失败报告未能落盘，仅保留上面的 [ERROR] 输出" >&2
	fi
	exit 1
}

# yf_require_step "<描述>" <命令...>
#   执行「必需」步骤：失败即**中止**——记录到报告 failed 列表，
#   在 stderr 打 [ERROR] + 描述 + 退出码，落盘报告（status=failed）后 exit 1。
#   成功恒返回 0（失败路径直接退出进程）。
yf_require_step()
{
	local _desc=""
	local _cmd=""
	local _rc=0

	_desc="${1:-}"
	if [ "$#" -gt 0 ]; then
		shift
	fi
	_cmd="${1:-}"

	if [ "$#" -eq 0 ]; then
		YF_LAST_STEP_RC=0
		return 0
	fi

	if "$@"; then
		_rc=0
	else
		_rc=$?
	fi

	YF_LAST_STEP_RC=${_rc}
	if [ "${_rc}" -ne 0 ]; then
		yf_install_report_fail "${_desc}" "${_rc}" "${_cmd}"
	fi
	return 0
}

# yf_install_report_note "<说明>"
#   往报告的 notes 里追加一条人工说明。用于「确实保留的 || true」等
#   必须在报告里解释清楚为什么留的点（UI / 审计会看到）。
yf_install_report_note()
{
	YF_REPORT_NOTES[${#YF_REPORT_NOTES[@]}]="${1:-}"
	return 0
}

# yf_install_report_finish
#   落盘报告到 $(yf_install_report_path <plugin>)（目录不存在则创建），
#   并打印缺失清单摘要（没有缺失项时打印「无缺失项」）。
#   总是返回 0：报告写不出去只 [WARN]，不能反过来把一次成功的安装判成失败。
yf_install_report_finish()
{
	local _missing_n=${#YF_REPORT_MISSING_STEP[@]}
	local _failed_n=${#YF_REPORT_FAILED_STEP[@]}
	local _i=0
	local _path=""

	_path=$(yf_install_report_path "${YF_REPORT_PLUGIN:-unknown}")
	if ! _yf_report_write_json; then
		echo "[WARN] 安装报告未能写入 ${_path}（安装结果本身不受影响）" >&2
	fi

	echo "==== 插件安装报告：${YF_REPORT_PLUGIN:-unknown} ===="
	echo "报告文件：${_path}"
	if [ "${_failed_n}" -gt 0 ]; then
		echo "失败项 ${_failed_n} 条（必需步骤）："
		for ((_i = 0; _i < _failed_n; _i++)); do
			echo "[失败] ${YF_REPORT_FAILED_STEP[_i]}（退出码 ${YF_REPORT_FAILED_RC[_i]:-0}，命令 ${YF_REPORT_FAILED_CMD[_i]}）"
		done
	fi
	if [ "${_missing_n}" -eq 0 ] && [ "${_failed_n}" -eq 0 ]; then
		echo "无缺失项（所有必需步骤与可选步骤均成功）"
	else
		echo "缺失项 ${_missing_n} 条（可选步骤）："
		for ((_i = 0; _i < _missing_n; _i++)); do
			echo "[缺失] ${YF_REPORT_MISSING_STEP[_i]}（退出码 ${YF_REPORT_MISSING_RC[_i]:-0}，命令 ${YF_REPORT_MISSING_CMD[_i]}）"
		done
	fi
	echo "======================================"
	return 0
}
