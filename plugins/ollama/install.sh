#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

# 版本脚本退出码必须透传（《问题报告》P1-5 机制 C）：见 scripts/lib_version_step.sh
_yf_step_lib="${rootPath}/scripts/lib_version_step.sh"
if [ -f "${_yf_step_lib}" ]; then
	source "${_yf_step_lib}"
fi

action=$1
type=$2

# 显式 install/uninstall 分支：旧实现无参数/拼错参数也会继续往下跑版本脚本，
# 而版本脚本的 else 兜底会执行整段卸载（userdel + rm -rf ~/.ollama 等）
if [ "${action}" != "install" ] && [ "${action}" != "uninstall" ];then
	echo '参数不合法，用法: install.sh install|uninstall <版本号>'
	exit 1
fi

if [ "${type}" == "" ];then
	echo '缺少安装脚本...'
	exit 1
fi

# 版本号白名单：旧实现只用 `-d` 判目录存在，`1.1/../../../tmp/x` 这类穿越值
# 只要目标目录存在就会以 root 执行面板外的任意 install.sh
case "${type}" in
	*[!0-9.]*|'')
		echo '版本号不合法...'
		exit 1
		;;
esac

if [ ! -d "${curPath}/versions/${type}" ];then
	echo '缺少安装脚本2...'
	exit 1
fi

yf_version_step "${action}" "${type}" "${curPath}/versions/${type}/install.sh" || exit $?

if [ "${action}" == "uninstall" ];then
	if [ -f /usr/lib/systemd/system/ollama.service ] || [ -f /lib/systemd/system/ollama.service ] ;then
		systemctl stop ollama
		systemctl disable ollama
		rm -rf /usr/lib/systemd/system/ollama.service
		rm -rf /lib/systemd/system/ollama.service
		systemctl daemon-reload
	fi
fi
