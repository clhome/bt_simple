#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
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

# cd /www/server/yufeng_panel/plugins/mariadb && bash install.sh install 8.2
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py try_slave_sync_bugfix {}
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py do_full_sync  {"db":"xxx","sign":"","begin":1}
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py sync_database_repair  {"db":"xxx","sign":""}
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py init_slave_status
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py install_pre_inspection


action=$1
type=$2

if id mysql &> /dev/null ;then 
    echo "mysql UID is `id -u mysql`"
    echo "mysql Shell is `grep "^mysql:" /etc/passwd |cut -d':' -f7 `"
else
    groupadd mysql
	useradd -g mysql -s /usr/sbin/nologin mysql
fi

if [ "${2}" == "" ];then
	echo '缺少安装脚本...'
	exit 0
fi 

if [ ! -d $curPath/versions/$2 ];then
	echo '缺少安装脚本2...'
	exit 0
fi

if [ "${action}" == "uninstall" ];then
	# 卸载必须先停进程再删目录（否则 mariadbd 带着已删除的 datadir 继续占着 3306，
	# 重装后表现为「数据库密码错误」——与 mysql 插件同一类现场）
	if [ -f "${rootPath}/plugins/mariadb/index.py" ]; then
		if ! (cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py stop_and_kill ${type}); then
			echo "[WARN] 停止/清理残留 mariadbd 时报告了异常（见上方输出），继续卸载" >&2
		fi
	fi

	if [ -f /usr/lib/systemd/system/mariadb.service ] || [ -f /lib/systemd/system/mariadb.service ];then
		if ! systemctl stop mariadb 2>/dev/null; then
			echo "[WARN] systemctl stop mariadb 失败（进程可能不在或不受 systemd 管理）" >&2
		fi
		systemctl disable mariadb 2>/dev/null
		rm -rf /usr/lib/systemd/system/mariadb.service
		rm -rf /lib/systemd/system/mariadb.service
		systemctl daemon-reload
	fi
fi


# ---------------------------------------------------------------------------
# 跨版本升级（2026-10-27，与 mysql 插件同一套口径）
#
# 旧实现：「已装 mariadb → 自愈 + exit 0」，所以面板点「更新到 10.11」只会跑自愈，
# 版本号原地不动。
#
# 安全口径（数据优先）：
#   1. **先备份**整份 server/mariadb（含 data）到 <server>/backup/，备份失败即中止；
#   2. 旧目录改名保留（.mariadb_prev_<ts>），不删；
#   3. 装完新版本后把旧 data 移回来（mv，省时间与空间）；
#   4. 启动 + mariadb-upgrade + 自检；任一步失败 → 停服务、删新目录、旧目录换回来、重启旧版本。
# ---------------------------------------------------------------------------
_yf_maria_backup_dir() {
	echo "${serverPath}/backup"
}

_yf_maria_upgrade_backup() {
	local _from="$1"
	local _to="$2"
	local _ts="$3"
	local _dir="" _need="" _free="" _file=""

	_dir=$(_yf_maria_backup_dir)
	mkdir -p "${_dir}" || { echo "[ERROR] 无法创建备份目录 ${_dir}" >&2; return 1; }

	if [ -d "${serverPath}/mariadb/data" ]; then
		_need=$(du -sk "${serverPath}/mariadb" 2>/dev/null | awk '{print $1}')
		_free=$(df -Pk "${_dir}" 2>/dev/null | awk 'NR==2 {print $4}')
		if [ -n "${_need}" ] && [ -n "${_free}" ]; then
			if [ "${_free}" -lt "$(( _need * 12 / 10 ))" ]; then
				echo "[ERROR] 备份空间不足：需要约 $(( _need / 1024 ))MB，${_dir} 仅剩 $(( _free / 1024 ))MB" >&2
				echo "        请先清理磁盘或调整备份目录（面板设置 → 备份目录）后重试" >&2
				return 1
			fi
		fi
	fi

	_file="${_dir}/mariadb_${_from}_to_${_to}_${_ts}.tar.gz"
	echo "[upgrade] 正在备份 ${serverPath}/mariadb → ${_file}（数据量大时较慢，请耐心等待）" >&2
	if ! tar -czf "${_file}" -C "${serverPath}" mariadb; then
		echo "[ERROR] 备份失败（${_file}），已中止升级，数据未做任何改动" >&2
		rm -f "${_file}" 2>/dev/null
		return 1
	fi
	if [ ! -s "${_file}" ] || ! tar -tzf "${_file}" >/dev/null 2>&1; then
		echo "[ERROR] 备份包损坏（${_file}），已中止升级" >&2
		return 1
	fi
	printf '%s' "${_file}"
	return 0
}

_yf_maria_upgrade() {
	local _from="$1"
	local _to="$2"
	local _ts="" _bak="" _prev="" _ok=0

	_ts=$(date +%Y%m%d_%H%M%S)
	_prev="${serverPath}/.mariadb_prev_${_ts}"

	echo "===== MariaDB 跨版本升级：${_from} → ${_to} ====="

	if [ -f "${rootPath}/plugins/mariadb/index.py" ]; then
		if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mariadb/index.py" stop_and_kill "${_from}" ); then
			echo "[WARN] 停止 MariaDB ${_from} 时报告了异常（继续升级流程）" >&2
		fi
	fi

	if ! _bak=$(_yf_maria_upgrade_backup "${_from}" "${_to}" "${_ts}"); then
		echo "[ERROR] 升级已中止（备份未完成）" >&2
		if [ -f "${rootPath}/plugins/mariadb/index.py" ]; then
			if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mariadb/index.py" start "${_from}" ); then
				echo "[WARN] 备份失败后重启 MariaDB ${_from} 也失败，请手动检查服务状态" >&2
			fi
		fi
		return 1
	fi
	echo "[upgrade] 备份完成：${_bak}"

	if ! mv "${serverPath}/mariadb" "${_prev}"; then
		echo "[ERROR] 无法重命名 ${serverPath}/mariadb（是否被占用？）" >&2
		if [ -f "${rootPath}/plugins/mariadb/index.py" ]; then
			if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mariadb/index.py" start "${_from}" ); then
				echo "[WARN] 目录改名失败后重启 MariaDB ${_from} 也失败，请手动检查服务状态" >&2
			fi
		fi
		return 1
	fi

	echo "[upgrade] 正在安装 MariaDB ${_to} ..."
	if ! yf_version_step install "${_to}" "${curPath}/versions/${_to}/install.sh"; then
		_ok=1
	fi

	if [ "${_ok}" = "0" ] && [ -d "${serverPath}/mariadb" ]; then
		if [ -d "${_prev}/data" ]; then
			echo "[upgrade] 回填数据目录 ..."
			rm -rf "${serverPath}/mariadb/data"
			if ! mv "${_prev}/data" "${serverPath}/mariadb/data"; then
				echo "[ERROR] datadir 回填失败" >&2
				_ok=1
			fi
			chown -R mysql:mysql "${serverPath}/mariadb/data" 2>/dev/null
		fi
		chown -R mysql:mysql "${serverPath}/mariadb" 2>/dev/null

		if [ "${_ok}" = "0" ]; then
			echo "[upgrade] 启动 MariaDB ${_to} ..."
			if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mariadb/index.py" start "${_to}" ); then
				_ok=1
			fi
			if [ "${_ok}" = "0" ]; then
				if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mariadb/index.py" mariadb_upgrade "${_to}" ); then
					echo "[WARN] mariadb-upgrade 未成功，请查任务日志" >&2
				fi
				if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mariadb/index.py" initd_install "${_to}" ); then
					echo "[WARN] 注册 MariaDB ${_to} 开机自启失败（可在面板里手动重试）" >&2
				fi
				if [ ! -d "${serverPath}/mariadb/data/mysql" ]; then
					echo "[ERROR] 升级后数据目录未就绪：${serverPath}/mariadb/data" >&2
					_ok=1
				fi
			fi
		fi
	fi

	if [ "${_ok}" != "0" ]; then
		echo "[ERROR] 升级失败，正在回滚到 ${_from} ..." >&2
		if [ -f "${rootPath}/plugins/mariadb/index.py" ]; then
			if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mariadb/index.py" stop_and_kill "${_to}" ); then
				echo "[WARN] 回滚时停止 MariaDB ${_to} 报告了异常（继续回滚）" >&2
			fi
		fi
		rm -rf "${serverPath}/mariadb"
		if mv "${_prev}" "${serverPath}/mariadb"; then
			if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mariadb/index.py" start "${_from}" ); then
				echo "[WARN] 回滚后启动 MariaDB ${_from} 失败，请手动 systemctl start mariadb" >&2
			fi
			echo "[ERROR] 已回滚到 MariaDB ${_from}；完整备份在 ${_bak}" >&2
		else
			echo "[ERROR] 回滚时无法恢复 ${_prev}，请手工处理；完整备份在 ${_bak}" >&2
		fi
		return 1
	fi

	echo "[upgrade] MariaDB 已升级到 ${_to}"
	echo "[upgrade] 升级前的完整目录保留在 ${_prev}（确认业务正常后可手工删除）"
	echo "[upgrade] 升级前的完整备份：${_bak}"
	echo "${_to}" > "${serverPath}/mariadb/version.pl"
	return 0
}

if [ "${action}" == "install" ] || [ "${action}" == "update" ] || [ "${action}" == "upgrade" ]; then
    if [ -d $serverPath/mariadb ] && [ -f $serverPath/mariadb/bin/mysql ]; then
        _cur_ver=""
        if [ -f "$serverPath/mariadb/version.pl" ]; then
            _cur_ver=$(tr -d '[:space:]' < "$serverPath/mariadb/version.pl")
        fi

        if [ -z "${_cur_ver}" ] || [ "${_cur_ver}" == "${type}" ]; then
            # 同版本（或读不到版本号）：只做自愈，不动二进制（原行为）
            echo "检测到 MariaDB 已存在部署实例，正在执行平滑无损升级与环境自愈 (版本: ${type})..."
            cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py check_plugin_upgrade ${type}
            cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py upgrade_self_healing ${type}
            cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py initd_install ${type}
            echo "MariaDB 平滑无损升级与环境自愈完成！"
            exit 0
        fi

        # 跨版本：必须由面板升级入口显式确认（防误点），且只允许同主版本（10.x / 11.x）
        if [ "${YF_MARIADB_ALLOW_UPGRADE:-0}" != "1" ]; then
            echo "[ERROR] 已安装 MariaDB ${_cur_ver}，安装/更新到 ${type} 需要显式确认。" >&2
            echo "        请在软件商店里点「升级到 ${type}」（会自动备份并支持失败回滚）。" >&2
            exit 1
        fi
        _cur_major=${_cur_ver%%.*}
        _tgt_major=${type%%.*}
        if [ "${_cur_major}" != "${_tgt_major}" ]; then
            echo "[ERROR] 拒绝跨主版本升级：${_cur_ver} → ${type}。" >&2
            echo "        跨主版本（如 10.x→11.x）需要先 mysqldump 导出再重建实例。" >&2
            exit 1
        fi

        _yf_maria_upgrade "${_cur_ver}" "${type}" || exit 1
        exit 0
    fi
fi

yf_version_step "${action}" "${type}" "$curPath/versions/$2/install.sh" || exit $?

if [ "${action}" == "install" ] && [ -d $serverPath/mariadb ];then
	#初始化 
	cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py start ${type}
	cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py initd_install ${type}

	# 装后自检：数据目录必须真的初始化出来（否则面板只能报「数据库密码错误」，
	# 典型原因是 3306 已被系统里另装的 MySQL/MariaDB 占用）
	if [ ! -d "$serverPath/mariadb/data/mysql" ]; then
		echo "[ERROR] MariaDB 自检未通过：$serverPath/mariadb/data 未初始化。" >&2
		echo "        常见原因：3306 端口被系统中另装的 MySQL/MariaDB 占用 → 先停掉它再重装本插件。" >&2
		exit 1
	fi
fi
