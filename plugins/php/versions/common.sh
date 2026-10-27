#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH=$PATH:/opt/homebrew/bin

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(cd "$curPath/../../.."; pwd)
serverPath=$(dirname "$rootPath")

version=$1
action=$2
extName=$3

# ---------------------------------------------------------------------------
# 参数白名单（与 index.py 的 isPhpVersion / isLibName 同口径，纵深防御）：
# version 会被拼进源码目录、extName 会被拼进脚本路径 → 非法即拒绝。
# ---------------------------------------------------------------------------
if ! printf '%s' "$version" | grep -Eq '^[0-9]{1,3}$'; then
	echo "ERROR: invalid version: ${version}" >&2
	exit 1
fi
if ! printf '%s' "$extName" | grep -Eq '^[a-zA-Z0-9_-]+$'; then
	echo "ERROR: invalid extension name: ${extName}" >&2
	exit 1
fi
case "$action" in
	install|uninstall) ;;
	*)
		echo "ERROR: invalid action: ${action}" >&2
		exit 1
		;;
esac

FILE=${curPath}/${version}/${extName}.sh
FILE_COMMON=${curPath}/common/${extName}.sh

# ---------------------------------------------------------------------------
# 退出码必须向上传递（旧实现的最大坑）：
#   扩展脚本里失败路径是 `return 1`（例如 curl.sh 的「扩展产物缺失」），
#   但本脚本跑完 bash 后只 echo 几行调试信息就退出 0 →
#   面板任务列表里「安装扩展」永远是成功，用户以为装上了。
# 现在：脚本缺失 → 非 0；扩展脚本非 0 → 原样透传。
# ---------------------------------------------------------------------------
if [ "$action" == 'install' ]; then
	if [ -f "$FILE" ]; then
		cd "${curPath}/${version}" || exit 1
		bash "${extName}.sh" install "${version}"
		_rc=$?
	elif [ -f "$FILE_COMMON" ]; then
		cd "${curPath}/common" || exit 1
		bash "${extName}.sh" install "${version}"
		_rc=$?
	else
		echo "no such extension: ${extName}" >&2
		exit 1
	fi
else
	if [ -f "$FILE" ]; then
		cd "${curPath}/${version}" || exit 1
		bash "${extName}.sh" uninstall "${version}"
		_rc=$?
	elif [ -f "$FILE_COMMON" ]; then
		cd "${curPath}/common" || exit 1
		bash "${extName}.sh" uninstall "${version}"
		_rc=$?
	else
		echo "no such extension: ${extName}" >&2
		exit 1
	fi
fi

if [ "${_rc}" != "0" ]; then
	echo "[ERROR] ${action} ${extName} 失败（${extName}.sh 退出码 ${_rc}）" >&2
fi
exit "${_rc}"
