#!/bin/bash
# ---------------------------------------------------------------------------------
# 版本脚本执行器 —— 「子脚本失败必须让外层失败」（《问题报告》P1-5 机制 C）
#
# 为什么需要：各插件外层 install.sh 的形状长期是
#
#     sh -x $curPath/versions/$2/install.sh $1        # 只有这一行
#     if [ "${action}" == "install" ] && [ -d $serverPath/xxx ];then
#         ...注册服务、写 version.pl、启动...
#
# 三个后果：
#   1. 版本脚本 `exit 1`（编译失败 / 下载失败）**没人看退出码**，外层继续往下跑，
#      最后以 0 退出 —— 面板显示「安装成功」，机器上却没有二进制；
#   2. 后续的 `index.py start` / `initd_install` 在残缺目录上继续执行，可能造出
#      指向不存在二进制的 systemd unit（下一轮排查会被它带偏）；
#   3. 安装报告（lib_install_report.sh）根本不会被调用，missing/failed 全空。
#
# 本文件只做一件事：跑版本脚本 → **原样保留退出码** → 非 0 时打可定位的 [ERROR]。
# 调用方必须把返回值当失败处理（`|| exit $?`），不许用 `|| true` 吞掉。
#
# 用法：
#   source "${rootPath}/scripts/lib_version_step.sh"
#   yf_version_step install 11.4 "$curPath/versions/11.4/install.sh" || exit $?
# ---------------------------------------------------------------------------------

# yf_version_step <动作> <版本> <版本脚本路径> [额外参数...]
# 返回：版本脚本的退出码（0 成功）；脚本不存在/不可读时返回 1 并打印原因
yf_version_step() {
	local _action=${1:-}
	local _version=${2:-}
	local _script=${3:-}
	if [ "$#" -ge 3 ]; then
		shift 3
	fi

	if [ -z "${_script}" ]; then
		echo "[ERROR] yf_version_step: 缺少版本脚本路径（动作=${_action} 版本=${_version}）" >&2
		return 1
	fi
	if [ ! -f "${_script}" ]; then
		echo "[ERROR] 版本脚本不存在: ${_script}（动作=${_action} 版本=${_version}）" >&2
		return 1
	fi

	# 保持历史调用形态 `sh -x`：日志里有逐行命令，真机排障全靠它
	sh -x "${_script}" "${_action}" "$@"
	local _rc=$?

	if [ "${_rc}" -ne 0 ]; then
		echo "[ERROR] 版本脚本失败：${_script}（动作=${_action} 版本=${_version}），退出码 ${_rc}" >&2
		echo "[ERROR] 已中止本插件安装，不会写 version.pl、不会注册服务（避免假成功）" >&2
		return "${_rc}"
	fi
	return 0
}
