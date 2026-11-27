#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
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


sysName=`uname`
action=$1
type=$2

lockFile="/var/run/yf_openresty_install.lock"
if [ -f "${lockFile}" ];then
    pid=$(cat "${lockFile}")
    if ps -p $pid > /dev/null 2>&1; then
        echo "Another OpenResty installation is already running (PID: $pid). Exiting."
        echo "[INFO] 后台已有 OpenResty 安装/升级任务正在运行，请等待其完成后再操作，切勿重复点击。"
        exit 1
    fi
fi
echo $$ > "${lockFile}"
trap "rm -f ${lockFile}" EXIT

VERSION=$2
openrestyDir=${serverPath}/source/openresty

# 升级前先把当前版本号记下来：若新二进制启动失败，回滚时要把 version.pl 改回去，
# 否则面板会以为已经升级完成（历史上正是这么“显示成功但实际在跑旧版”的）。
_old_ver=""
if [ -f "${serverPath}/openresty/version.pl" ]; then
	_old_ver=$(cat "${serverPath}/openresty/version.pl" 2>/dev/null)
fi

# 版本脚本会写**完整上游版本号**（1.31.9.1 / 1.31.1.1）。这里只在其缺失或与本次
# 安装目录无关时才回填目录名（历史行为），否则覆盖会让 1.31.1.1 与 1.31.1.2
# 都落成 "1.31.1"，面板看不出补丁差异。
yf_write_version_pl() {
	local _cur=""
	[ -f "$serverPath/openresty/version.pl" ] && _cur=$(cat "$serverPath/openresty/version.pl" 2>/dev/null)
	case "${_cur}" in
		"${VERSION}"|"${VERSION}".*) return 0 ;;
	esac
	echo "${VERSION}" > "$serverPath/openresty/version.pl"
}

# 编译前检查可用磁盘空间，防止编译到一半把根分区打满导致线上服务崩溃
_yf_check_disk_space() {
	local _min_mb="${YF_OPENRESTY_MIN_DISK_MB:-5120}"
	local _check_dir="${openrestyDir}"
	while [ ! -d "${_check_dir}" ] && [ "${_check_dir}" != "/" ]; do
		_check_dir=$(dirname "${_check_dir}")
	done
	local _free_kb
	_free_kb=$(df -Pk "${_check_dir}" 2>/dev/null | awk 'NR==2 {print $4}')
	if [ -n "${_free_kb}" ] && [ "${_free_kb}" -gt 0 ] 2>/dev/null; then
		local _free_mb=$((_free_kb / 1024))
		if [ "${_free_mb}" -lt "${_min_mb}" ]; then
			echo "[ERROR] 磁盘可用空间不足：编译 OpenResty 建议至少预留 ${_min_mb}MB，当前 ${_check_dir} 所在分区仅剩 ${_free_mb}MB。" >&2
			echo "        请先清理 ${serverPath}/source/ 等历史缓存后重试，已中止操作（现有服务未受影响）。" >&2
			return 1
		fi
	fi
	return 0
}

# 编译或启动失败时还原升级前的 nginx.bak / openresty.bak 并尝试恢复服务
_yf_openresty_rollback() {
	if [ ! -f "${serverPath}/openresty/nginx/sbin/nginx.bak" ]; then
		return 1
	fi
	echo "[WARN] 尝试回滚到升级前的二进制并重新启动..." >&2
	[ -f "${serverPath}/openresty/nginx/sbin/nginx" ] && mv -f "${serverPath}/openresty/nginx/sbin/nginx" "${serverPath}/openresty/nginx/sbin/nginx.failed" 2>/dev/null
	mv -f "${serverPath}/openresty/nginx/sbin/nginx.bak" "${serverPath}/openresty/nginx/sbin/nginx" 2>/dev/null
	chmod +x "${serverPath}/openresty/nginx/sbin/nginx" 2>/dev/null
	if [ -f "${serverPath}/openresty/bin/openresty.bak" ]; then
		[ -f "${serverPath}/openresty/bin/openresty" ] && mv -f "${serverPath}/openresty/bin/openresty" "${serverPath}/openresty/bin/openresty.failed" 2>/dev/null
		mv -f "${serverPath}/openresty/bin/openresty.bak" "${serverPath}/openresty/bin/openresty" 2>/dev/null
		chmod +x "${serverPath}/openresty/bin/openresty" 2>/dev/null
	fi
	if [ -n "${_old_ver}" ]; then
		echo "${_old_ver}" > "${serverPath}/openresty/version.pl"
	fi
	local _rb_out _rb_status
	_rb_out=$(cd "${rootPath}" && python3 "${rootPath}/plugins/openresty/index.py" start 2>&1)
	echo "${_rb_out}"
	_rb_status=$(cd "${rootPath}" && python3 "${rootPath}/plugins/openresty/index.py" status 2>/dev/null)
	if [ "${_rb_status}" = "start" ]; then
		echo "[WARN] 已回滚到 ${_old_ver:-升级前版本} 并恢复服务；请先排查上方失败原因再升级" >&2
		return 0
	fi
	echo "[ERROR] 回滚后仍未启动，请检查 ${serverPath}/openresty/nginx/logs/error.log" >&2
	return 1
}

if id www &> /dev/null ;then 
    echo "www uid is `id -u www`"
    echo "www shell is `grep "^www:" /etc/passwd |cut -d':' -f7 `"
else
    groupadd www
	useradd -g www -s /bin/bash www
fi

if [ "${action}" == "upgrade" ];then
	_yf_check_disk_space || exit 1
	sh $curPath/versions/$2/install.sh $1
	if [ "$?" != "0" ];then
		echo "Sub-script install.sh failed!" >&2
		_yf_openresty_rollback
		exit 1
	fi
	
	yf_write_version_pl

	mkdir -p $serverPath/web_conf/php/conf
	echo 'set $PHP_ENV 0;' > $serverPath/web_conf/php/conf/enable-php-00.conf

	#初始化 
	cd ${rootPath} && python3 ${rootPath}/plugins/openresty/index.py start
	cd ${rootPath} && python3 ${rootPath}/plugins/openresty/index.py initd_install
	_svc_status=$(cd "${rootPath}" && python3 "${rootPath}/plugins/openresty/index.py" status 2>/dev/null)
	if [ "${_svc_status}" != "start" ]; then
		echo "[ERROR] OpenResty 升级后未能保持运行（status=${_svc_status:-unknown}）" >&2
		_yf_openresty_rollback
		exit 1
	fi
	exit 0
fi


if [ "${2}" == "" ];then
	# 必须非 0：面板按退出码判定安装结果，`exit 0` 会让「版本脚本都不存在」
	# 也显示成「安装成功」（假成功家族，2026-10-28 统一收紧）
	echo '缺少安装脚本版本...'
	exit 1
fi 

if [ "${action}" == "uninstall" ];then
	# 卸载前置：停 unit + 按「可执行文件在本插件目录下」杀残留（含程序文件已删的僵尸）
	yf_svc_force_stop "${serverPath}/openresty" openresty || echo "[WARN] openresty 仍有进程残留（见上方日志），卸载继续但端口可能被占" >&2
	if [ -f /usr/lib/systemd/system/openresty.service ] || [ -f /lib/systemd/system/openresty.service ];then
		systemctl stop openresty
		rm -f /usr/lib/systemd/system/openresty.service
		rm -f /lib/systemd/system/openresty.service
		systemctl daemon-reload
	fi

	if [ -f $serverPath/openresty/init.d/openresty ];then
		$serverPath/openresty/init.d/openresty stop
	fi

	rm -rf $serverPath/openresty
fi

# 升级/安装前预检：站点配置语法 + 缺失 enable-php-*.conf 占位自愈。
# 为什么需要（真机 2026-11-27）：用户卸载/降级过 PHP，站点 vhost 里的
# `include .../web_conf/php/conf/enable-php-apt7.1.conf` 还指着已不存在的文件。
# 旧进程带着旧配置还能跑，一旦升级（停服→换二进制→启动）就再也起不来。
# 预检做两件事：先把缺失的 PHP 配置补成占位（该站点 .php 返回 503，不拖垮全局），
# 若仍不通过且是升级，则**在停服前中止**——宁可暂不升，也不要把还在跑的服务弄挂。
if [ "${action}" == "install" ] || [ "${action}" == "upgrade" ];then
	_yf_check_disk_space || exit 1
	if [ -x "${serverPath}/openresty/nginx/sbin/nginx" ]; then
		_yf_precheck_out=$(cd "${rootPath}" && python3 "${rootPath}/plugins/openresty/index.py" conf_precheck 2>&1)
		case "${_yf_precheck_out}" in
			ERROR*)
				if [ -n "${_old_ver}" ]; then
					echo "[ERROR] 升级前配置预检未通过，已中止（现有服务保持运行、未做任何改动）：" >&2
					echo "${_yf_precheck_out}" >&2
					exit 1
				fi
				echo "[WARN] 配置预检未通过（首次安装继续，安装后会再次自愈并尝试启动）：" >&2
				echo "${_yf_precheck_out}" >&2
				;;
		esac
	fi
fi

# 编译安装或升级前，强力停止并清退所有旧的 nginx/openresty 进程，杜绝 80 端口冲突或 Text file busy 故障
if [ "${action}" == "install" ] || [ "${action}" == "upgrade" ];then
	if [ -f /usr/lib/systemd/system/openresty.service ] || [ -f /lib/systemd/system/openresty.service ];then
		systemctl stop openresty
	fi
	if [ -f $serverPath/openresty/init.d/openresty ];then
		$serverPath/openresty/init.d/openresty stop
	fi
	killall -9 nginx 2>/dev/null
	killall -9 openresty 2>/dev/null
	pkill -9 nginx 2>/dev/null
	pkill -9 openresty 2>/dev/null
fi

sh $curPath/versions/$2/install.sh $1
if [ "$?" != "0" ];then
	echo "Sub-script install.sh failed!" >&2
	_yf_openresty_rollback
	exit 1
fi

if [ "${action}" == "install" ] && [ -d $serverPath/openresty ];then
	yf_write_version_pl

	mkdir -p $serverPath/web_conf/php/conf
	echo 'set $PHP_ENV 0;' > $serverPath/web_conf/php/conf/enable-php-00.conf

	#初始化 
	# 顺序：先 start（restyOp 内部会写 systemd unit）再 initd_install（systemctl enable）——
	# 反过来会在 unit 还没写入时 enable 失败，白报一句「设置开机自启失败」。
	_start_out=$(cd "${rootPath}" && python3 "${rootPath}/plugins/openresty/index.py" start 2>&1)
	echo "${_start_out}"
	_initd_out=$(cd "${rootPath}" && python3 "${rootPath}/plugins/openresty/index.py" initd_install 2>&1)
	echo "${_initd_out}"

	# 启动复核：start 可能在配置自愈失败时返回 ERROR，也可能 systemd 返回 0 后进程立即退出。
	# 以「pid + 进程存活」为准（index.py status），不信任退出码。
	if [ ! -f "${serverPath}/openresty/nginx/sbin/nginx" ]; then
		echo "[ERROR] 安装结束后仍找不到 nginx 二进制，安装失败" >&2
		exit 1
	fi
	_svc_status=$(cd "${rootPath}" && python3 "${rootPath}/plugins/openresty/index.py" status 2>/dev/null)
	if [ "${_svc_status}" != "start" ]; then
		echo "[ERROR] OpenResty 已安装但未能保持运行（status=${_svc_status:-unknown}）" >&2
		# 回滚：构建脚本会把旧二进制备份为 nginx.bak，恢复它并重试启动，
		# 保证「升级失败 ≠ 站点下线」。version.pl 也要改回旧值。
		_yf_openresty_rollback
		exit 1
	fi
fi
