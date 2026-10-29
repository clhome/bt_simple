#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

PLUGIN_PATH=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
curPath=${PLUGIN_PATH}
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

# 版本脚本退出码必须透传（《问题报告》P1-5 机制 C）：见 scripts/lib_version_step.sh
_yf_step_lib="${rootPath}/scripts/lib_version_step.sh"
if [ -f "${_yf_step_lib}" ]; then
	source "${_yf_step_lib}"
fi

if [ -f ${rootPath}/bin/activate ];then
	source ${rootPath}/bin/activate
fi

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

# lib.sh 可能会改变 curPath 变量和当前工作目录，这里必须强制恢复
curPath=${PLUGIN_PATH}
cd ${PLUGIN_PATH}

# 宿主系统配置自愈：处理 Debian/Ubuntu 上 mysql-common 残留 /etc/mysql/my.cnf 缺失 conf.d 目录的问题
if [ -d /etc/mysql ] || [ -f /etc/mysql/my.cnf ]; then
	mkdir -p /etc/mysql/conf.d /etc/mysql/mysql.conf.d 2>/dev/null
fi

action="${1//$'\r'/}"
type="${2//$'\r'/}"
is_fast=false



# 自动匹配剥离 -fast 后缀并切换模式
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

echo "[DEBUG] curPath is: '${curPath}'"
echo "[DEBUG] type is: '${type}'"
echo "[DEBUG] BASH_SOURCE[0] is: '${BASH_SOURCE[0]}'"
echo "[DEBUG] pwd is: '$(pwd)'"
echo "[DEBUG] Checking if directory exists: ${curPath}/versions/${type}"

if [ "${is_fast}" == "false" ] && [ ! -d "$curPath/versions/$type" ];then
	# 必须非 0：面板按退出码判定安装结果，`exit 0` 会让「版本脚本都不存在」
	# 也显示成「安装成功」（假成功家族，2026-10-28 统一收紧）
	echo '缺少源码编译安装脚本...' >&2
	exit 1
fi


# 极速 Tar 二进制安装核心实现
Install_fast_mysql() {
    local version_main=$1
    echo "开始执行极速 Tar 二进制部署流程 (版本: ${version_main})..."
    
    # 1. 静默检测并补齐系统底层依赖链接库 (YUM / APT)
    echo '正在检测并安装系统依赖包 (libaio, numactl)...'
    if [ -f /usr/bin/yum ]; then
        yum install -y libaio numactl libtirpc wget tar xz
    elif [ -f /usr/bin/apt-get ]; then
        apt-get update -y
        apt-get install -y libaio1 libaio-dev numactl libtirpc-dev wget tar xz-utils
    fi

    # 2. 定位系统架构
    local os_arch=`arch`
    if [ "${os_arch}" == "x86_64" ]; then
        os_arch="x86_64"
    elif [ "${os_arch}" == "aarch64" ]; then
        os_arch="aarch64"
    fi

    # 3. 根据大版本动态生成包名和官方 CDN 地址
    local mysql_full_ver=""
    local suffix_name=""
    local tar_file=""
    local download_path=""

    if [[ "${version_main}" == "5.7" ]]; then
        mysql_full_ver="5.7.44"
        suffix_name="${mysql_full_ver}-linux-glibc2.12-${os_arch}"
        tar_file="mysql-${suffix_name}.tar.gz"
        download_path="MySQL-5.7"
    elif [[ "${version_main}" == "8.0" ]]; then
        mysql_full_ver="8.0.46"
        suffix_name="${mysql_full_ver}-linux-glibc2.28-${os_arch}"
        tar_file="mysql-${suffix_name}.tar.xz"
        download_path="MySQL-8.0"
    elif [[ "${version_main}" == "8.2" ]]; then
        mysql_full_ver="8.2.0"
        suffix_name="${mysql_full_ver}-linux-glibc2.28-${os_arch}"
        tar_file="mysql-${suffix_name}.tar.xz"
        download_path="MySQL-8.2"
    elif [[ "${version_main}" == "8.4" ]]; then
        mysql_full_ver="8.4.3"
        suffix_name="${mysql_full_ver}-linux-glibc2.28-${os_arch}"
        tar_file="mysql-${suffix_name}.tar.xz"
        download_path="MySQL-8.4"
    elif [[ "${version_main}" == "9.0" ]]; then
        mysql_full_ver="9.0.1"
        suffix_name="${mysql_full_ver}-linux-glibc2.28-${os_arch}"
        tar_file="mysql-${suffix_name}.tar.xz"
        download_path="MySQL-9.0"
    elif [[ "${version_main}" == "9.7" ]]; then
        mysql_full_ver="9.7.0"
        suffix_name="${mysql_full_ver}-linux-glibc2.28-${os_arch}"
        tar_file="mysql-${suffix_name}.tar.xz"
        download_path="MySQL-9.7"
    else
        # 动态兜底逻辑
        mysql_full_ver="${version_main}.0"
        suffix_name="${mysql_full_ver}-linux-glibc2.28-${os_arch}"
        tar_file="mysql-${suffix_name}.tar.xz"
        download_path="MySQL-${version_main}"
    fi

    local my_dir=${serverPath}/source/mysql
    mkdir -p ${my_dir}
    mkdir -p ${serverPath}/mysql

    local ext="tar.xz"
    if [[ "${tar_file}" == *.tar.gz ]]; then
        ext="tar.gz"
    fi
    local huawei_base="https://mirrors.huaweicloud.com/mysql/Downloads/${download_path}/"

    # 下载源列表（国内镜像优先，官方源兜底）
    local mirrors=()
    mirrors+=("${huawei_base}${tar_file}")
    mirrors+=(
        "https://mirrors.aliyun.com/mysql/${download_path}/${tar_file}"
        "https://mirrors.tuna.tsinghua.edu.cn/mysql/downloads/${download_path}/${tar_file}"
        "https://cdn.mysql.com/Downloads/${download_path}/${tar_file}"
        "https://downloads.mysql.com/archives/get/p/23/file/${tar_file}"
    )

    local download_success=false
    for mirror_url in "${mirrors[@]}"; do
        echo "正在尝试从节点下载部署包: ${mirror_url}"
        
        local tmp_file="/tmp/${tar_file}"
        rm -f "${tmp_file}"
        
        if command -v yf_download &> /dev/null; then
            yf_download "${tmp_file}" "${mirror_url}"
        else
            wget -nv -O "${tmp_file}" "${mirror_url}"
        fi

        if [ -f "${tmp_file}" ]; then
            # 校验一：文件大小检测 (官方包普遍远大于50MB)
            local file_size=$(stat -c%s "${tmp_file}" 2>/dev/null || stat -f%z "${tmp_file}" 2>/dev/null)
            if [ -n "${file_size}" ] && [ "${file_size}" -gt 52428800 ]; then
                # 校验二：文件类型检测 (防止下载到 HTML 错误页)
                if command -v file >/dev/null 2>&1; then
                    local file_type=$(file -b "${tmp_file}")
                    if [[ "${file_type}" == *"XZ compressed"* ]] || [[ "${file_type}" == *"gzip compressed"* ]] || [[ "${file_type}" == *"tar archive"* ]]; then
                        # 校验三：压缩流完整性（截断包/坏包在这里拦住，别等解压才报）
                        if [[ "${ext}" == "tar.xz" ]]; then
                            if command -v xz >/dev/null 2>&1 && ! xz -t "${tmp_file}" >/dev/null 2>&1; then
                                echo "校验失败：xz 完整性检查不通过（包被截断），切换下一个节点..."
                                rm -f "${tmp_file}"
                                continue
                            fi
                        elif command -v gzip >/dev/null 2>&1 && ! gzip -t "${tmp_file}" >/dev/null 2>&1; then
                            echo "校验失败：gzip 完整性检查不通过（包被截断），切换下一个节点..."
                            rm -f "${tmp_file}"
                            continue
                        fi
                        # 校验四：记录 sha256（官方未提供统一校验文件，故记录到面板日志备查；有 .sha256 时严格比对）
                        if command -v sha256sum >/dev/null 2>&1; then
                            local _sha
                            _sha=$(sha256sum "${tmp_file}" | awk '{print $1}')
                            echo "包 sha256: ${_sha}" 
                            local _sha_txt
                            _sha_txt=$( (curl -fsSL -m 20 "${mirror_url}.sha256" 2>/dev/null | head -c 200) || echo '')
                            if [ -n "${_sha_txt}" ]; then
                                if printf '%s' "${_sha_txt}" | grep -qi "${_sha}"; then
                                    echo "sha256 官方校验通过"
                                else
                                    echo "校验失败：sha256 与官方 .sha256 不一致，切换下一个节点..."
                                    rm -f "${tmp_file}"
                                    continue
                                fi
                            fi
                        fi
                        echo "包下载完成且校验通过。"
                        mv -f "${tmp_file}" "${my_dir}/${tar_file}"
                        download_success=true
                        break
                    else
                        echo "校验失败：文件类型异常 (${file_type})，可能是 404/503 页面。切换下一个节点..."
                    fi
                else
                    # 缺少 file 命令时，依赖大小作为基础校验
                    echo "包下载完成，文件大小校验通过。"
                    mv -f "${tmp_file}" "${my_dir}/${tar_file}"
                    download_success=true
                    break
                fi
            else
                echo "校验失败：文件大小异常 (${file_size} bytes)，可能下载不完整或为报错页面。切换下一个节点..."
            fi
        else
            echo "下载失败，文件未生成。切换下一个节点..."
        fi
        # 清理异常文件以便下一次重试
        rm -f "${tmp_file}"
        rm -f "${my_dir}/${tar_file}"
    done

    if [ "${download_success}" != "true" ]; then
        echo "网络错误：所有节点的 MySQL 通用预编译包均下载失败或文件损坏！"
        rm -rf ${serverPath}/mysql
        exit 1
    fi

    echo "包下载并校验完成，正在进行多线程解压部署..."
    cd ${my_dir}
    
    # 优化一与优化三：直接解压至目标目录消除多余 cp，且使用 xz 多线程解压
    if [[ "${tar_file}" == *.tar.xz ]]; then
        if command -v xz >/dev/null 2>&1 && xz --help | grep -q "T, --threads"; then
            tar -I 'xz -T0' -xf ${tar_file} --strip-components=1 -C ${serverPath}/mysql/
        else
            tar -Jxf ${tar_file} --strip-components=1 -C ${serverPath}/mysql/
        fi
    else
        tar -zxf ${tar_file} --strip-components=1 -C ${serverPath}/mysql/
    fi
    
    # 装后回读：解压出来必须真有 bin/mysqld，否则就是「解压成功但内容不对」
    if [ ! -x "${serverPath}/mysql/bin/mysqld" ]; then
        echo "[ERROR] 解压后缺少 ${serverPath}/mysql/bin/mysqld，安装包内容异常" >&2
        rm -rf ${serverPath}/mysql
        exit 1
    fi

    # 优化二：清理占用数百MB空间的无效测试和文档目录，提高 I/O 效率
    echo "正在清理无关的测试组件与文档，释放磁盘空间..."
    rm -rf ${serverPath}/mysql/mysql-test
    rm -rf ${serverPath}/mysql/docs
    rm -rf ${serverPath}/mysql/man
    
    # 设置正确的拥有者
    chown -R mysql:mysql ${serverPath}/mysql/
    
    # 清理安装包
    rm -f ${my_dir}/${tar_file}

    # 写入 version.pl 标识文件
    echo "${version_main}" > ${serverPath}/mysql/version.pl
    echo "MySQL-${version_main} (Tar 极速二进制版) 核心部署部署成功！"
    return 0
}


if [ "${action}" == "uninstall" ]; then
	# 卸载必须先把「本插件的 mysqld 进程」彻底停掉再删目录（2026-10-27 真机）：
	#   旧实现只 rm -rf，进程会带着已删除的 datadir/socket 继续占着 3306；
	#   下次装完面板退回 TCP 就连到这个僵尸进程上 → 永远「数据库密码错误」，
	#   而 /www/server/mysql/data 根本没初始化成功 → 「日志」页 500。
	# stop_and_kill 只杀 exe 属于本插件的进程，不会动系统里别的 MySQL/MariaDB。
	if [ -f "${rootPath}/plugins/mysql/index.py" ]; then
		# 清理是「尽力而为」：失败要留一行可读日志，但不应阻断后面的删目录
		if ! (cd ${rootPath} && python3 ${rootPath}/plugins/mysql/index.py stop_and_kill ${type}); then
			echo "[WARN] 停止/清理残留 mysqld 时报告了异常（见上方输出），继续卸载" >&2
		fi
	fi

	if [ -f /usr/lib/systemd/system/mysql.service ] || [ -f /lib/systemd/system/mysql.service ];then
		if ! systemctl stop mysql 2>/dev/null; then
			echo "[WARN] systemctl stop mysql 失败（进程可能不在或不受 systemd 管理）" >&2
		fi
		systemctl disable mysql 2>/dev/null
		rm -rf /usr/lib/systemd/system/mysql.service
		rm -rf /lib/systemd/system/mysql.service
		systemctl daemon-reload 2>/dev/null
	fi

    if [ "${is_fast}" == "true" ]; then
        rm -rf $serverPath/mysql
        echo '极速版卸载完成'
        exit 0
    else
        yf_version_step uninstall "${type}" "$curPath/versions/$type/install.sh" || exit $?
    fi

	# 卸载后回读：进程还在就明确告警（否则下一次安装会踩这个坑）
	if [ -f "${rootPath}/plugins/mysql/index.py" ]; then
		if ! (cd ${rootPath} && python3 ${rootPath}/plugins/mysql/index.py stop_and_kill ${type}); then
			echo "[WARN] 卸载后自检发现仍有 mysqld 残留，请手动确认：ps -ef | grep mysqld" >&2
		fi
	fi
fi


# ---------------------------------------------------------------------------
# 跨版本升级（2026-10-27）
#
# 背景：旧实现在「已装 mysql」时无条件走「自愈 + exit 0」，所以面板点「更新到 5.7」
# 只会跑自愈脚本，版本号原地不动（用户实测反馈）。
#
# 安全口径（数据优先）：
#   1. **先备份**整份 server/mysql（含 data）到 <server>/backup/，备份失败即中止，
#      一个字节都不动；
#   2. 旧目录**改名保留**（.mysql_prev_<ts>），不是删掉；
#   3. 装完新版本后把旧 data 移回来（mv，不复制，省时间与空间）；
#   4. 启动 + 自检；任何一步失败 → 停服务、删新目录、把旧目录改回来、重启旧版本；
#   5. 成功才提示「原目录保留在 …，确认无误后可手动删除」。
#
# 官方升级路径提示（不强制，但会打印）：
#   MySQL 官方只承诺 5.5→5.6→5.7 逐级升级；本脚本允许直接跨到同大版本 LTS（如
#   5.5→5.7），失败会自动回滚，但**跨大版本（5.x→8.x/9.x）不给建议、也不在本入口内**。
# ---------------------------------------------------------------------------
_yf_mysql_backup_dir() {
	echo "${serverPath}/backup"
}

# 备份整个实例目录；成功时把备份文件路径打到 stdout
_yf_mysql_upgrade_backup() {
	local _from="$1"
	local _to="$2"
	local _ts="$3"
	local _dir="" _need="" _free="" _file=""

	_dir=$(_yf_mysql_backup_dir)
	mkdir -p "${_dir}" || { echo "[ERROR] 无法创建备份目录 ${_dir}" >&2; return 1; }

	if [ -d "${serverPath}/mysql/data" ]; then
		_need=$(du -sk "${serverPath}/mysql" 2>/dev/null | awk '{print $1}')
		_free=$(df -Pk "${_dir}" 2>/dev/null | awk 'NR==2 {print $4}')
		# 备份是压缩包，按 1.2 倍原大小保守估算
		if [ -n "${_need}" ] && [ -n "${_free}" ]; then
			if [ "${_free}" -lt "$(( _need * 12 / 10 ))" ]; then
				echo "[ERROR] 备份空间不足：需要约 $(( _need / 1024 ))MB，${_dir} 仅剩 $(( _free / 1024 ))MB" >&2
				echo "        请先清理磁盘或调整备份目录（面板设置 → 备份目录）后重试" >&2
				return 1
			fi
		fi
	fi

	_file="${_dir}/mysql_${_from}_to_${_to}_${_ts}.tar.gz"
	echo "[upgrade] 正在备份 ${serverPath}/mysql → ${_file}（数据量大时较慢，请耐心等待）" >&2
	if ! tar -czf "${_file}" -C "${serverPath}" mysql; then
		echo "[ERROR] 备份失败（${_file}），已中止升级，数据未做任何改动" >&2
		rm -f "${_file}" 2>/dev/null
		return 1
	fi
	# 回读：备份包必须非空且能列出内容，否则视为失败
	if [ ! -s "${_file}" ] || ! tar -tzf "${_file}" >/dev/null 2>&1; then
		echo "[ERROR] 备份包损坏（${_file}），已中止升级" >&2
		return 1
	fi
	printf '%s' "${_file}"
	return 0
}

# 主流程：$1=已装版本 $2=目标版本
_yf_mysql_upgrade() {
	local _from="$1"
	local _to="$2"
	local _ts="" _bak="" _prev="" _ok=0

	_ts=$(date +%Y%m%d_%H%M%S)
	_prev="${serverPath}/.mysql_prev_${_ts}"

	echo "===== MySQL 跨版本升级：${_from} → ${_to} ====="
	case "${_from}" in
		5.5 | 5.6)
			if [ "${_to}" = "5.7" ]; then
				echo "[提示] 官方升级路径为 5.5→5.6→5.7；本次直接升到 5.7，失败会自动回滚。"
			fi
			;;
	esac

	# 1. 停服务（含僵尸进程清理）
	if [ -f "${rootPath}/plugins/mysql/index.py" ]; then
		if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mysql/index.py" stop_and_kill "${_from}" ); then
			echo "[WARN] 停止 MySQL ${_from} 时报告了异常（继续升级流程）" >&2
		fi
	fi

	# 2. 备份（失败即中止，不动数据）
	if ! _bak=$(_yf_mysql_upgrade_backup "${_from}" "${_to}" "${_ts}"); then
		echo "[ERROR] 升级已中止（备份未完成）" >&2
		# 备份失败时把服务拉回来，避免「升级没成还把库停了」
		if [ -f "${rootPath}/plugins/mysql/index.py" ]; then
			if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mysql/index.py" start "${_from}" ); then
				echo "[WARN] 备份失败后重启 MySQL ${_from} 也失败，请手动检查服务状态" >&2
			fi
		fi
		return 1
	fi
	echo "[upgrade] 备份完成：${_bak}"

	# 3. 旧目录改名保留（不删）
	if ! mv "${serverPath}/mysql" "${_prev}"; then
		echo "[ERROR] 无法重命名 ${serverPath}/mysql（是否被占用？）" >&2
		if [ -f "${rootPath}/plugins/mysql/index.py" ]; then
			if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mysql/index.py" start "${_from}" ); then
				echo "[WARN] 目录改名失败后重启 MySQL ${_from} 也失败，请手动检查服务状态" >&2
			fi
		fi
		return 1
	fi

	# 4. 安装目标版本（此时目录不存在，走正常安装分支）
	echo "[upgrade] 正在安装 MySQL ${_to} ..."
	if [ "${is_fast}" == "true" ]; then
		Install_fast_mysql "${_to}" || _ok=1
	else
		yf_version_step install "${_to}" "${curPath}/versions/${_to}/install.sh" || _ok=1
	fi

	if [ "${_ok}" = "0" ] && [ -d "${serverPath}/mysql" ]; then
		# 5. 回填数据目录：新装的 data 是空的，直接换成旧的（mv，省时省空间）
		if [ -d "${_prev}/data" ]; then
			echo "[upgrade] 回填数据目录 ..."
			rm -rf "${serverPath}/mysql/data"
			if ! mv "${_prev}/data" "${serverPath}/mysql/data"; then
				echo "[ERROR] datadir 回填失败" >&2
				_ok=1
			fi
			chown -R mysql:mysql "${serverPath}/mysql/data" 2>/dev/null
		fi
		chown -R mysql:mysql "${serverPath}/mysql" 2>/dev/null

		# 6. 启动 + 自检（失败即回滚）
		if [ "${_ok}" = "0" ]; then
			echo "[upgrade] 启动 MySQL ${_to} 并自检 ..."
			( cd "${rootPath}" && python3 "${rootPath}/plugins/mysql/index.py" start "${_to}" ) || _ok=1
			if [ "${_ok}" = "0" ]; then
				if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mysql/index.py" mysql_upgrade "${_to}" ); then
					echo "[WARN] mysql_upgrade 未成功（8.0+ 由 mysqld 自动升级；5.7 请查任务日志）" >&2
				fi
				if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mysql/index.py" initd_install "${_to}" ); then
					echo "[WARN] 注册 MySQL ${_to} 开机自启失败（可在面板里手动重试）" >&2
				fi
				( cd "${rootPath}" && python3 "${rootPath}/plugins/mysql/index.py" self_check "${_to}" ) || _ok=1
			fi
		fi
	fi

	if [ "${_ok}" != "0" ]; then
		echo "[ERROR] 升级失败，正在回滚到 ${_from} ..." >&2
		if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mysql/index.py" stop_and_kill "${_to}" ); then
			echo "[WARN] 回滚时停止 MySQL ${_to} 报告了异常（继续回滚）" >&2
		fi
		rm -rf "${serverPath}/mysql"
		if mv "${_prev}" "${serverPath}/mysql"; then
			if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/mysql/index.py" start "${_from}" ); then
				echo "[WARN] 回滚后启动 MySQL ${_from} 失败，请手动 systemctl start mysql" >&2
			fi
			echo "[ERROR] 已回滚到 MySQL ${_from}；完整备份在 ${_bak}" >&2
		else
			echo "[ERROR] 回滚时无法恢复 ${_prev}，请手工处理；完整备份在 ${_bak}" >&2
		fi
		return 1
	fi

	echo "[upgrade] MySQL 已升级到 ${_to}"
	echo "[upgrade] 升级前的完整目录保留在 ${_prev}（确认业务正常后可手工删除）"
	echo "[upgrade] 升级前的完整备份：${_bak}"
	# 写 version.pl（版本脚本可能已写过，这里确保是目标版本）
	echo "${_to}" > "${serverPath}/mysql/version.pl"
	return 0
}

if [ "${action}" == "install" ] || [ "${action}" == "update" ] || [ "${action}" == "upgrade" ]; then
    # 装前清理：上次卸载只 rm -rf 没停进程时，mysqld 会带着已删除的程序文件
    # 与 datadir 继续占着 3306；此时装完 start() 会误以为「已在运行」而跳过初始化，
    # data 目录永远造不出来（真机现场 2026-10-27）。clean_stale 只杀这种僵尸进程，
    # 不碰正常运行的实例（健康实例走下面的「平滑升级」分支）。
    if [ -f "${rootPath}/plugins/mysql/index.py" ]; then
        if ! (cd ${rootPath} && python3 ${rootPath}/plugins/mysql/index.py clean_stale ${type}); then
            echo "[WARN] 清理卸载残留进程失败（若 3306 被占用，安装会在自检阶段报错）" >&2
        fi
    fi

    if [ -d $serverPath/mysql ]; then
        if [ -f $serverPath/mysql/bin/mysql ]; then
            _cur_ver=""
            if [ -f "$serverPath/mysql/version.pl" ]; then
                _cur_ver=$(tr -d '[:space:]' < "$serverPath/mysql/version.pl")
            fi

            if [ -z "${_cur_ver}" ] || [ "${_cur_ver}" == "${type}" ]; then
                # 同版本（或读不到版本号）：只做自愈，不动二进制（原行为）
                echo "检测到 MySQL 已存在部署实例，正在执行平滑无损升级与环境自愈 (版本: ${type})..."
                cd ${rootPath} && python3 ${rootPath}/plugins/mysql/index.py check_plugin_upgrade ${type}
                cd ${rootPath} && python3 ${rootPath}/plugins/mysql/index.py upgrade_self_healing ${type}
                cd ${rootPath} && python3 ${rootPath}/plugins/mysql/index.py initd_install ${type}
                echo "MySQL 平滑无损升级与环境自愈完成！"
                exit 0
            fi

            # 跨版本：必须由面板升级入口显式确认（防误点），且只允许同主版本
            if [ "${YF_MYSQL_ALLOW_UPGRADE:-0}" != "1" ]; then
                echo "[ERROR] 已安装 MySQL ${_cur_ver}，安装/更新到 ${type} 需要显式确认。" >&2
                echo "        请在软件商店里点「升级到 ${type}」（会自动备份并支持失败回滚）。" >&2
                exit 1
            fi
            _cur_major=${_cur_ver%%.*}
            _tgt_major=${type%%.*}
            if [ "${_cur_major}" != "${_tgt_major}" ]; then
                echo "[ERROR] 拒绝跨主版本升级：${_cur_ver} → ${type}。" >&2
                echo "        跨主版本（如 5.x→8.x）会触发 MySQL 数据字典不兼容，请先升到同主版本的 LTS，" >&2
                echo "        或用 mysqldump 导出后重建实例。" >&2
                exit 1
            fi

            _yf_mysql_upgrade "${_cur_ver}" "${type}" || exit 1
            exit 0
        else
            echo '检测到残留的不完整 MySQL 目录，正在清理...'
            rm -rf $serverPath/mysql
        fi
    fi


    if [ "${is_fast}" == "true" ]; then
        Install_fast_mysql "${type}"
    else
        yf_version_step install "${type}" "$curPath/versions/$type/install.sh" || exit $?
    fi

    if [ -d $serverPath/mysql ]; then
        # 再次确保宿主 /etc/mysql 缺失目录已被补齐（防止第三方 apt 触发器重建残损 my.cnf 导致自检 abort）
        if [ -d /etc/mysql ] || [ -f /etc/mysql/my.cnf ]; then
            mkdir -p /etc/mysql/conf.d /etc/mysql/mysql.conf.d 2>/dev/null
        fi

        # 执行初始化与自启动服务写入
        cd ${rootPath} && python3 ${rootPath}/plugins/mysql/index.py start ${type}
        cd ${rootPath} && python3 ${rootPath}/plugins/mysql/index.py initd_install ${type}
        cd ${rootPath} && python3 ${rootPath}/plugins/mysql/index.py fix_db_access ${type}

        # 装后自检（2026-10-27 真机：装完「成功」但点性能优化只报「数据库密码错误」）
        #   典型现场：机器上另有系统装的 MySQL/MariaDB 占着 3306，面板误判自己的实例在跑，
        #   所有 SQL 打到别人的库 → 1045；自己的 /www/server/mysql/data 根本没初始化。
        #   自检把「实例归属 / 数据目录 / 连通性」一次判清楚，不通过就非 0 退出。
        echo "MySQL 安装自检..."
        if ! (cd ${rootPath} && python3 ${rootPath}/plugins/mysql/index.py self_check ${type}); then
            echo "[ERROR] MySQL 自检未通过：实例不可用（详见上方 JSON 的 msg）。" >&2
            echo "        常见原因：3306 端口被系统中另装的 MySQL/MariaDB 占用 → 先停掉它再重装本插件。" >&2
            echo "        排查：ps -ef | grep -E '[m]ysqld|[m]ariadbd'；ss -ltnp | grep 3306" >&2
            exit 1
        fi
    fi
fi
