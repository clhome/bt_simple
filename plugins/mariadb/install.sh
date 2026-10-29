#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

# 面板虚拟环境（2026-10-28 真机事故）：下面的每一步都是 `python3 .../index.py ...`，
# 而 `python3` 在任务环境里是**系统解释器**（没有 pymysql）→ fix_db_access 里
# `import pymysql.cursors` 直接 ModuleNotFoundError，root 口令不会被同步，
# 面板随后永远报「数据库密码错误」。mysql 插件一直有这个 source，mariadb 漏了。
if [ -f "${rootPath}/bin/activate" ]; then
	source "${rootPath}/bin/activate"
fi

# 版本脚本退出码必须透传（《问题报告》P1-5 机制 C）：见 scripts/lib_version_step.sh
_yf_step_lib="${rootPath}/scripts/lib_version_step.sh"
if [ -f "${_yf_step_lib}" ]; then
	source "${_yf_step_lib}"
fi

# 极速安装用的下载/校验纯函数库（yf_fetch_archive / yf_verify_archive）。
# 不要 source scripts/lib.sh：那是部署脚本，被 source 会 pip install / exit。
for _yf_gh in "${rootPath}/scripts/github_download.sh"               "${serverPath}/yufeng_panel/scripts/github_download.sh"; do
	if [ -f "${_yf_gh}" ]; then
		. "${_yf_gh}" >/dev/null 2>&1
		break
	fi
done
unset _yf_gh

# cd /www/server/yufeng_panel/plugins/mariadb && bash install.sh install 8.2
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py try_slave_sync_bugfix {}
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py do_full_sync  {"db":"xxx","sign":"","begin":1}
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py sync_database_repair  {"db":"xxx","sign":""}
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py init_slave_status
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py install_pre_inspection


# 宿主系统配置自愈：处理 Debian/Ubuntu 上 mysql-common 残留 /etc/mysql/my.cnf 缺失 conf.d 目录的问题
if [ -d /etc/mysql ] || [ -f /etc/mysql/my.cnf ]; then
	mkdir -p /etc/mysql/conf.d /etc/mysql/mysql.conf.d 2>/dev/null
fi

action=$1
type="${2//$'\r'/}"

# 极速安装后缀（2026-10-28，与 mysql 插件同口径）：
#   商店的「安装方式：极速安装(Tar)」会发 `<版本>-fast`，这里剥掉后切到
#   Install_fast_mariadb（官方 bintar），版本目录/版本脚本仍用剥过的 `${type}`。
is_fast=false
if [[ "${type}" == *-fast ]]; then
	is_fast=true
	type="${type%-fast}"
fi

if id mysql &> /dev/null ;then 
    echo "mysql UID is `id -u mysql`"
    echo "mysql Shell is `grep "^mysql:" /etc/passwd |cut -d':' -f7 `"
else
    groupadd mysql
	useradd -g mysql -s /usr/sbin/nologin mysql
fi

if [ "${type}" == "" ];then
	# 必须非 0：面板按退出码判定安装结果，`exit 0` 会让「版本脚本都不存在」
	# 也显示成「安装成功」（假成功家族，2026-10-28 统一收紧）
	echo '缺少安装脚本...'
	exit 1
fi 

# 极速安装不需要 `versions/<x>/` 目录也能装（二进制包由官方提供）
if [ "${is_fast}" == "false" ] && [ ! -d "${curPath}/versions/${type}" ];then
	echo '缺少安装脚本2...'
	exit 1
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
	if [ "${is_fast}" == "true" ]; then
		Install_fast_mariadb "${_to}" || _ok=1
	else
		if ! yf_version_step install "${_to}" "${curPath}/versions/${_to}/install.sh"; then
			_ok=1
		fi
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

# ---------------------------------------------------------------------------
# 极速安装（Tar 二进制）—— 直接部署 MariaDB 官方预编译包，跳过 20~60 分钟的 cmake/make
# （2026-10-28，与 mysql 插件的 `Install_fast_mysql` 同口径）
#
# 事实核对（2026-10-28 逐条实测，不要凭印象改）：
#   * 官方只发布 **x86_64** 的 bintar（目录名 `bintar-linux-systemd-x86_64`）；
#     11.4.5 的目录里**没有** aarch64 → 其它构架必须回退源码编译，不能给假成功；
#   * 该 bintar 目录**只**存在于 archive.mariadb.org（aliyun / 清华 / 腾讯 /
#     ustc / downloads.mariadb.com 都不镜像 bintar，实测 404/403）→ 下载失败要
#     明确报错并建议改源码编译；
#   * 官方不提供 .sha256（只有 .asc 签名）→ 校验链 = 内容魔数 + gzip -t +
#     解压 + **回读** bin/mariadbd，并把 sha256 写进任务日志备查。
#
# 完整补丁版号不在本文件硬编码：从 versions/<分支>/install.sh 的 `MY_VER=` 读取，
# 保证「极速」与「源码编译」两条路径的版本号只有一个真源。
# ---------------------------------------------------------------------------
Install_fast_mariadb() {
	local version_main="$1"
	local os_arch
	os_arch=$(uname -m)
	if [ "${os_arch}" != "x86_64" ]; then
		echo "[ERROR] 极速安装仅支持 x86_64（当前 ${os_arch}）：官方未提供该构架的 MariaDB 预编译包" >&2
		echo "        请选择「源码编译」安装方式" >&2
		return 1
	fi

	# 完整版本号的真源
	local full_ver=""
	local _ver_sh="${curPath}/versions/${version_main}/install.sh"
	if [ -f "${_ver_sh}" ]; then
		full_ver=$(sed -n 's/^MY_VER=\([0-9][0-9.]*\).*/\1/p' "${_ver_sh}" 2>/dev/null | head -1)
	fi
	if [ -z "${full_ver}" ]; then
		echo "[ERROR] 无法确定 MariaDB ${version_main} 的完整版本号（${_ver_sh} 缺少 MY_VER=）" >&2
		return 1
	fi

	local pkg_name="mariadb-${full_ver}-linux-systemd-x86_64.tar.gz"
	local pkg_dir="${serverPath}/source/mariadb"
	local pkg_file="${pkg_dir}/${pkg_name}"
	local base="https://archive.mariadb.org/mariadb-${full_ver}/bintar-linux-systemd-x86_64"

	# 官方 sha256：downloads.mariadb.org 的 REST API 给每个文件带校验和。
	# 取不到**不阻断**（此时按内容魔数 + 完整性校验，并打印实测 sha256 备查）。
	local want_sha=""
	if command -v curl >/dev/null 2>&1; then
		# 用 sed/grep 从 JSON 里取 sha256，不依赖 jq/python：
		# files 数组里每个条目是 {..."file_name":"X",..."sha256sum":"Y"...}，
		# 目标条目不会跨很多行（单行 JSON），按 file_name 定位后取同行 sha256sum。
		local _api="https://downloads.mariadb.org/rest-api/mariadb/${full_ver}/"
		want_sha=$(curl -sL -m 25 "${_api}" 2>/dev/null \
			| tr '}' '\n' \
			| grep -F "\"file_name\": \"${pkg_name}\"" \
			| grep -o '"sha256sum": *"[0-9a-f]\{64\}"' \
			| head -1 \
			| grep -o '[0-9a-f]\{64\}')
	fi
	if [ -n "${want_sha}" ]; then
		echo "官方 sha256: ${want_sha}"
	else
		echo "[WARN] 未取到官方 sha256（REST API 不可达），将只做内容与完整性校验" >&2
	fi

	# 运行期依赖（与 mysql 极速安装一致）：libaio 是 innodb 必需，numactl 可缺
	if [ -f /usr/bin/apt-get ]; then
		DEBIAN_FRONTEND=noninteractive apt-get install -y libaio1 numactl >/dev/null 2>&1 \
			|| echo "[WARN] 安装 libaio/numactl 失败（若启动报缺库请手工装 libaio1）" >&2
	elif [ -f /usr/bin/yum ]; then
		yum install -y libaio numactl >/dev/null 2>&1 \
			|| echo "[WARN] 安装 libaio/numactl 失败（若启动报缺库请手工装 libaio）" >&2
	fi

	mkdir -p "${pkg_dir}" "${serverPath}/mariadb" || return 1

	# 本地已有包先验内容（HTML 错误页/截断包不得进解压）
	if [ -f "${pkg_file}" ] && ! yf_verify_archive "${pkg_file}" 2>/dev/null; then
		echo "[WARN] 本地已有安装包无效（截断/错误页），删除重下：${pkg_file}" >&2
		rm -f "${pkg_file}"
	fi

	if [ ! -f "${pkg_file}" ]; then
		echo "正在下载 MariaDB ${full_ver} 官方预编译包（约 340MB）..."
		echo "  说明：该包仅官方 archive 提供，国内单连接通常只有 10~30KB/s；"
		echo "        这里用 8 连接分段下载（实测聚合 ~150KB/s，约 20~40 分钟）。"
		if command -v yf_multi_download >/dev/null 2>&1; then
			yf_multi_download "${base}/${pkg_name}" "${pkg_file}" 8 "${want_sha}" 3600 || {
				echo "[ERROR] 下载失败或校验不通过：${base}/${pkg_name}" >&2
				echo "        网络受限时请改用「源码编译」安装方式" >&2
				return 1
			}
		elif command -v yf_fetch_archive >/dev/null 2>&1; then
			yf_fetch_archive "${pkg_file}" "${base}/${pkg_name}" 3600 || {
				echo "[ERROR] 下载失败或包内容无效：${base}/${pkg_name}" >&2
				echo "        网络受限时请改用「源码编译」安装方式" >&2
				return 1
			}
		else
			# 走到这里说明 github_download.sh 没被 source 成功（两个助手都不可用）：
			# 不做「裸 wget 下载」兜底 —— 没有内容校验的下载会把 404 页面当压缩包，
			# 而且放宽 TLS 校验也违反仓库口径。
			echo "[ERROR] 缺少下载助手（scripts/github_download.sh 未加载），无法安全下载" >&2
			echo "        请改用「源码编译」安装方式" >&2
			return 1
		fi
	fi

	if command -v sha256sum >/dev/null 2>&1; then
		echo "包 sha256: $(sha256sum "${pkg_file}" | awk '{print $1}')"
	fi

	# 先解到临时目录再 mv 就位：不依赖「目标目录事先存在且为空」——
	# 真机踩过：预先 mkdir 的空目录在下载的 15 分钟里被谁清掉了，
	# 于是 tar -C 报 "无法 open: 没有那个文件或目录"（包其实是好的）。
	local stage_dir="${serverPath}/.mariadb_fast_stage_$$"
	rm -rf "${stage_dir}"
	mkdir -p "${stage_dir}" || return 1
	if ! tar -zxf "${pkg_file}" --strip-components=1 -C "${stage_dir}"; then
		echo "[ERROR] 解压失败（包损坏）：${pkg_file}" >&2
		rm -rf "${stage_dir}"
		return 1
	fi
	# 装后回读：解压出来必须真有 bin/mariadbd
	if [ ! -x "${stage_dir}/bin/mariadbd" ]; then
		echo "[ERROR] 解压后缺少 bin/mariadbd，安装包内容异常" >&2
		rm -rf "${stage_dir}"
		return 1
	fi
	rm -rf "${serverPath}/mariadb"
	if ! mv "${stage_dir}" "${serverPath}/mariadb"; then
		echo "[ERROR] 无法把解压结果移动到 ${serverPath}/mariadb" >&2
		rm -rf "${stage_dir}"
		return 1
	fi

	# 初始化脚本位置在 bintar 里不固定（个别版本只有 bin/mariadb-install-db）：
	# index.py 的 initMysqlData 按 `./scripts/mariadb-install-db` 调用，缺就补个软链
	if [ ! -e "${serverPath}/mariadb/scripts/mariadb-install-db" ] \
	   && [ -e "${serverPath}/mariadb/bin/mariadb-install-db" ]; then
		mkdir -p "${serverPath}/mariadb/scripts"
		ln -sf ../bin/mariadb-install-db "${serverPath}/mariadb/scripts/mariadb-install-db"
	fi

	chown -R mysql:mysql "${serverPath}/mariadb" 2>/dev/null
	rm -f "${pkg_file}" >/dev/null 2>&1
	echo "${version_main}" > "${serverPath}/mariadb/version.pl"
	echo "MariaDB-${version_main} (Tar 极速二进制版 ${full_ver}) 部署完成！"
	return 0
}

if [ "${action}" == "uninstall" ]; then
	# 卸载永远走版本脚本（它只做「停进程 + 删目录」，与安装方式无关，
	# 极速/编译安装的目录布局一致）
	yf_version_step "${action}" "${type}" "${curPath}/versions/${type}/install.sh" || exit $?
elif [ "${is_fast}" == "true" ]; then
	Install_fast_mariadb "${type}" || exit 1
else
	yf_version_step "${action}" "${type}" "${curPath}/versions/${type}/install.sh" || exit $?
fi

if [ "${action}" == "install" ] && [ -d $serverPath/mariadb ];then
	#初始化 
	cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py start ${type}
	cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py initd_install ${type}
	cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py fix_db_access ${type}

	# 装后自检（与 mysql 插件同一口径，2026-10-28）：
	# 只查 `data/mysql` 目录在不在是不够的——目录早就初始化过、但 3306 上跑的是
	# 系统里另装的 MySQL/MariaDB 时，上面每条命令都会「成功」，面板却永远连不上
	# （1045 Access denied），用户只能看到「装完成功、点数据库报密码错误」。
	# self_check 把「实例归属 → 数据目录 → socket/TCP 连通性」一次判清楚，
	# 不通过就非 0 退出，绝不当成功。
	echo "MariaDB 安装自检..."
	if ! (cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py self_check ${type}); then
		echo "[ERROR] MariaDB 自检未通过：实例不可用（详见上方 JSON 的 msg）。" >&2
		echo "        常见原因：3306 端口被系统中另装的 MySQL/MariaDB 占用 → 先停掉它再重装本插件。" >&2
		echo "        排查：ps -ef | grep -E '[m]ariadbd|[m]ysqld'；ss -ltnp | grep 3306" >&2
		exit 1
	fi
fi
