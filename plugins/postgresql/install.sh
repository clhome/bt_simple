#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

# 「卸载前彻底停进程」共享库（scripts/lib_service_stop.sh，纯函数，可安全 source）。
# 只 systemctl stop 是不够的：进程若不是该 unit 起的（上次卸载删了 unit／手工启动），
# 就会带着已删除的 datadir/程序文件继续占着端口 —— 见 2026-10-27 MySQL 现场。
for _yf_svc_lib in "${rootPath}/scripts/lib_service_stop.sh" \
                   "${serverPath}/yufeng_panel/scripts/lib_service_stop.sh"; do
	if [ -f "${_yf_svc_lib}" ]; then
		. "${_yf_svc_lib}"
		break
	fi
done
unset _yf_svc_lib


# 版本脚本退出码必须透传（《问题报告》P1-5 机制 C）：见 scripts/lib_version_step.sh
_yf_step_lib="${rootPath}/scripts/lib_version_step.sh"
if [ -f "${_yf_step_lib}" ]; then
	source "${_yf_step_lib}"
fi

# cd /www/server/yufeng_panel/plugins/postgresql && bash install.sh install 16

action="$1"
type="$2"

if ! [[ "$type" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    # Type should be numbers, like 16 or 9.6
    echo '参数格式错误...'
    exit 0
fi

VERSION=(${type//./ })

# 动态检测当前系统的 pip 是否支持 --break-system-packages 参数（兼容新老版本Linux）
PIP_OPT=""
if pip install --help | grep -q "break-system-packages"; then
    PIP_OPT="--break-system-packages"
fi

pip install $PIP_OPT psycopg2-binary

if [ -f "${rootPath}/bin/activate" ];then
	source "${rootPath}/bin/activate"
	pip install psycopg2-binary
fi


if [ -z "${type}" ];then
	# 必须非 0：面板按退出码判定安装结果，`exit 0` 会让「版本脚本都不存在」
	# 也显示成「安装成功」（假成功家族，2026-10-28 统一收紧）
	echo '缺少安装脚本...'
	exit 1
fi 

if [ ! -d "$curPath/versions/$VERSION" ];then
	# 必须非 0：面板按退出码判定安装结果，`exit 0` 会让「版本脚本都不存在」
	# 也显示成「安装成功」（假成功家族，2026-10-28 统一收紧）
	echo '缺少安装脚本2...'
	exit 1
fi

if [ "${action}" == "uninstall" ];then
	# 卸载前置：停 unit + 按「可执行文件在本插件目录下」杀残留（含程序文件已删的僵尸）
	yf_svc_force_stop "${serverPath}/postgresql" postgresql || echo "[WARN] postgresql 仍有进程残留（见上方日志），卸载继续但端口可能被占" >&2
	if [ -f /usr/lib/systemd/system/postgresql.service ] || [ -f /lib/systemd/system/postgresql.service ];then
		systemctl stop postgresql
		systemctl disable postgresql
		rm -rf /usr/lib/systemd/system/postgresql.service
		rm -rf /lib/systemd/system/postgresql.service
		systemctl daemon-reload
	fi
fi

yf_version_step "${action}" "${VERSION}" "$curPath/versions/$VERSION/install.sh" || exit $?

if [ "${action}" == "install" ] && [ -d "$serverPath/postgresql" ];then
	#初始化 
	cd "${rootPath}" && python3 "${rootPath}/plugins/postgresql/index.py" start "${type}"
	cd "${rootPath}" && python3 "${rootPath}/plugins/postgresql/index.py" initd_install "${type}"
fi
