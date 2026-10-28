#!/bin/bash
if [ -f $(dirname $0)/../../scripts/lib_make_jobs.sh ]; then source $(dirname $0)/../../scripts/lib_make_jobs.sh; elif [ -f /www/server/yufeng_panel/scripts/lib_make_jobs.sh ]; then source /www/server/yufeng_panel/scripts/lib_make_jobs.sh; fi
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
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




VERSION=$2

# --------------------------------------------------------------------------
# P1-新：参数闸门（裸调必须明确失败，不能「装了个寂寞」还 exit 0）
#   现场：`bash install.sh install`（无版本号）→ 拼出 redis-.tar.gz（404），
#   日志里写「安装失败!」，脚本最终却是 EXIT=0，面板照样报「安装完成」。
#   与 0cdc966 里 php-apt/php-yum/pureftp/valkey/mongodb/ollama 的 fail-fast 对齐。
# --------------------------------------------------------------------------
_yf_redis_action=$(printf '%s' "${1:-}" | tr -d '\r')
case "${_yf_redis_action}" in
	install|update|upgrade|uninstall) ;;
	'')
		echo "[ERROR] 缺少动作参数（用法：bash install.sh install <版本号>，例如 install 7.2.17）" >&2
		exit 1
		;;
	*)
		echo "[ERROR] 不支持的动作：${_yf_redis_action}（仅支持 install / update / upgrade / uninstall）" >&2
		exit 1
		;;
esac

# 版本号闸门：**三段补丁版**（7.2.17）或**两段系列号**（7.2）都接受。
# 系列号由下面的 _yf_redis_resolve_version 解析成「该系列当前最新补丁版」，
# 这样软件商店里永远只有 3 个选项，上游发多少补丁版都不用改前端。
if [ "${_yf_redis_action}" != "uninstall" ]; then
	case "${VERSION}" in
		''|*[!0-9.]*|*.*.*.*|*..*|.*|*.)
			echo "[ERROR] 版本号缺失或非法：'${VERSION}'（应形如 7.2.17 或系列号 7.2），拒绝拼 redis-.tar.gz 这类空版本包" >&2
			exit 1
			;;
		*.*.*|*.*) ;;
		*)
			echo "[ERROR] 版本号缺失或非法：'${VERSION}'（应形如 7.2.17 或系列号 7.2）" >&2
			exit 1
			;;
	esac
fi


# ---------------------------------------------------------------------------
# 系列号 → 当前最新补丁版
#
# 面板（`web/utils/plugin.py::install`）下发任务前已经解析过；这里是**兜底**：
# 手工 `bash install.sh install 7.2`、或旧面板残留的排队任务进来时也能装对版本。
# 解析不了就 fail-fast —— 绝不拼 `redis-.tar.gz`（历史上就是这么 404 的）。
# ---------------------------------------------------------------------------
_yf_redis_resolve_version() {
	local want="$1" got=""
	case "${want}" in
		*.*.*) printf '%s' "${want}"; return 0;;
		*.*) ;;
		*) return 1;;
	esac
	if [ -f "${rootPath}/plugins/redis/index.py" ]; then
		got=$( cd "${rootPath}" && python3 "${rootPath}/plugins/redis/index.py" resolve_version "${want}" 2>/dev/null | tr -d '[:space:]' )
	fi
	case "${got}" in
		*.*.*) printf '%s' "${got}"; return 0;;
	esac
	return 1
}

# a 是否严格大于 b（按**数字段**比较；任一侧判不了返回 1）。
# 不用字符串比较：`7.2.9` vs `7.2.17`、`8.2.11` vs `8.10.3` 字典序都会判反。
_yf_redis_ver_gt() {
	local a="$1" b="$2" i=0 x y
	local -a ap bp
	IFS='.' read -r -a ap <<< "${a}"
	IFS='.' read -r -a bp <<< "${b}"
	while [ "$i" -lt "${#ap[@]}" ] || [ "$i" -lt "${#bp[@]}" ]; do
		x="${ap[$i]:-0}"
		y="${bp[$i]:-0}"
		case "${x}" in ''|*[!0-9]*) return 1;; esac
		case "${y}" in ''|*[!0-9]*) return 1;; esac
		if [ "${x}" -gt "${y}" ]; then return 0; fi
		if [ "${x}" -lt "${y}" ]; then return 1; fi
		i=$((i + 1))
	done
	return 1
}

if [ "${_yf_redis_action}" != "uninstall" ]; then
	case "${VERSION}" in
		*.*.*) ;;
		*)
			_yf_redis_resolved=$(_yf_redis_resolve_version "${VERSION}") || _yf_redis_resolved=""
			if [ -z "${_yf_redis_resolved}" ]; then
				echo "[ERROR] 无法把系列号 '${VERSION}' 解析成具体补丁版（面板离线且没有内置表？）" >&2
				echo "        请直接指定补丁版重试，例如：bash install.sh install 7.2.17" >&2
				exit 1
			fi
			echo "系列 ${VERSION} → 当前最新补丁版 ${_yf_redis_resolved}"
			VERSION="${_yf_redis_resolved}"
			;;
	esac
fi


# ---------------------------------------------------------------------------
# 源码：下载 + 按内容校验 + 解压
#
# 与同族脚本同一个坑：`wget -O` 不看退出码、`tar` 失败也往下走，结果
# 「下载失败 → 编译一个空目录 → 报一堆无关错误」，或把 HTML 错误页当压缩包。
# 口径：已有包先按**内容**验（gzip -t），坏了就删；下载后必须验；解压失败即中止。
# ---------------------------------------------------------------------------
_yf_redis_fetch_source() {
	local ver="$1"
	local file_tgz="redis-${ver}.tar.gz"
	local source_dir="${serverPath}/source/redis"
	local tgz=""

	mkdir -p "${source_dir}" || {
		echo "[ERROR] 无法创建源码目录 ${source_dir}" >&2
		return 1
	}
	tgz="${source_dir}/${file_tgz}"

	if [ -f "${tgz}" ] && ! gzip -t "${tgz}" 2>/dev/null; then
		echo "[WARN] 本地已有的 ${file_tgz} 不是有效压缩包（多为 HTML 错误页/截断），已删除重下"
		rm -f "${tgz}"
	fi
	if [ ! -f "${tgz}" ]; then
		if command -v yf_download >/dev/null 2>&1; then
			yf_download "${tgz}" "https://download.redis.io/releases/${file_tgz}" 300
		else
			wget -nv -T 120 -t 2 -O "${tgz}" "https://download.redis.io/releases/${file_tgz}"
		fi
		if [ ! -s "${tgz}" ] || ! gzip -t "${tgz}" 2>/dev/null; then
			echo "[ERROR] 下载 ${file_tgz} 失败或内容无效（不是 gzip 包），请检查网络/镜像" >&2
			rm -f "${tgz}"
			return 1
		fi
	fi

	if ! ( cd "${source_dir}" && tar -zxf "${file_tgz}" ); then
		echo "[ERROR] 解压 ${file_tgz} 失败（包损坏），已清理，请重试" >&2
		rm -f "${tgz}"
		return 1
	fi
	if [ ! -d "${source_dir}/redis-${ver}" ]; then
		echo "[ERROR] 解压后未找到源码目录 ${source_dir}/redis-${ver}（包结构与预期不符）" >&2
		return 1
	fi
	return 0
}

# 编译并安装到指定 PREFIX（不碰 $serverPath/redis 里已有的数据与配置）
_yf_redis_build() {
	local ver="$1" prefix="$2"
	local source_dir="${serverPath}/source/redis"
	local cpuCore="" cmd_make="" _j=""

	cpuCore=$(nproc 2>/dev/null)
	if [ -z "$cpuCore" ]; then
		cpuCore="1"
	fi
	# --- yf adaptive clamp (1C512M -> -j1) ---
	if command -v yf_make_jobs >/dev/null 2>&1; then
		_j=$(yf_make_jobs 2>/dev/null || echo "")
		if [ -n "${_j}" ] && [ "${_j}" -ge 1 ] 2>/dev/null; then
			cpuCore="${_j}"
		fi
	fi

	cmd_make=$(command -v gmake 2>/dev/null) || cmd_make=""
	mkdir -p "${prefix}" || {
		echo "[ERROR] 无法创建安装前缀 ${prefix}" >&2
		return 1
	}
	if [ -n "${cmd_make}" ]; then
		if ! ( cd "${source_dir}/redis-${ver}" && gmake BUILD_TLS=yes -j "${cpuCore}" PREFIX="${prefix}" install ); then
			echo "[ERROR] redis 编译/安装失败（gmake，见上方输出）" >&2
			return 1
		fi
	else
		if ! ( cd "${source_dir}/redis-${ver}" && make BUILD_TLS=yes -j "${cpuCore}" PREFIX="${prefix}" install ); then
			echo "[ERROR] redis 编译/安装失败（make，见上方输出）" >&2
			return 1
		fi
	fi

	# 装后回读：没有 redis-server 就等于没装上（不能写 version.pl、不能报「安装完成」）
	if [ ! -x "${prefix}/bin/redis-server" ]; then
		echo "[ERROR] 安装产物缺失：${prefix}/bin/redis-server 不存在或不可执行" >&2
		return 1
	fi
	return 0
}

# 系统内核参数与架构相关的一次性优化（新装与升级都要保证）
_yf_redis_tune_system() {
	local vm_overcommit net_somaxconn arm_check
	vm_overcommit=$(grep vm.overcommit_memory /etc/sysctl.conf 2>/dev/null)
	net_somaxconn=$(grep net.core.somaxconn /etc/sysctl.conf 2>/dev/null)
	if [ -z "${vm_overcommit}" ] && [ -z "${net_somaxconn}" ];then
		echo "vm.overcommit_memory = 1" >> /etc/sysctl.conf
		echo "net.core.somaxconn = 1024" >> /etc/sysctl.conf
		sysctl -p
	fi
	arm_check=$(uname -a | grep aarch64)
	if [ "${arm_check}" ]; then
		echo "ignore-warnings ARM64-COW-BUG" >> $serverPath/redis/redis.conf
	fi
}

# ---------------------------------------------------------------------------
# 同大版本升级（2026-10-28，用户口径：同大版本支持升级）
#
# 旧实现：「已装 redis → 自愈 + exit 0」，于是面板点「更新到 7.2.17」只跑自愈，
# 二进制原地不动、版本号却被改写 —— 用户看到「升级完成」，实际还是旧版本。
#
# 安全口径（数据优先）：
#   1. 停服停不掉就中止（绝不边跑边换二进制）；
#   2. **先备份** data + 配置到 <server>/backup/，备份失败即中止；备份前查磁盘空间；
#   3. 新版本编译到 `.redis.new.<ts>`，不动现有 data/ 与 redis.conf；
#   4. 换二进制：旧 bin 改名为 `redis.bin.prev.<ts>`（保留，可手工回滚）；
#   5. 启动 + 回读 `redis-server -v` 必须是目标版本；任一步失败 → 停服、换回旧 bin、重启。
# 只允许**同主版本且目标更新**（降级会读不了新版本写出的 RDB/AOF，面板不提供）。
# ---------------------------------------------------------------------------
# 尽力把 Redis 拉起来／停下来（中止与回滚路径专用）：
# 失败只打 [WARN]，**不覆盖**原始错误原因（否则用户只会看到「启动失败」，
# 看不到真正的「备份空间不足」）。刻意不用 `|| true`：那样连告警都没有。
_yf_redis_try_start() {
	local ver="$1"
	if ( cd "${rootPath}" && python3 "${rootPath}/plugins/redis/index.py" start ); then
		return 0
	fi
	echo "[WARN] 重新启动 Redis ${ver} 失败，请手动执行：systemctl start redis" >&2
	echo "        （或：${serverPath}/redis/bin/redis-server ${serverPath}/redis/redis.conf）" >&2
	return 0
}

_yf_redis_try_stop() {
	local ver="$1"
	if ( cd "${rootPath}" && python3 "${rootPath}/plugins/redis/index.py" stop ); then
		return 0
	fi
	echo "[WARN] 停止 Redis ${ver} 时报告了异常（继续回滚流程）" >&2
	return 0
}

_yf_redis_upgrade() {
	local from="$1" to="$2"
	local ts="" bak="" staging="" prev_bin="" ok=0 live_ver=""

	ts=$(date +%Y%m%d_%H%M%S)
	staging="${serverPath}/.redis.new.${ts}"
	prev_bin="${serverPath}/redis.bin.prev.${ts}"

	echo "===== Redis 同大版本升级：${from} → ${to} ====="

	# ---- 1) 停服 ----
	echo "[upgrade] 停止 Redis ${from} ..."
	if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/redis/index.py" stop ); then
		echo "[ERROR] 停止 Redis 失败，升级已中止（服务仍在运行，未做任何改动）" >&2
		return 1
	fi

	# ---- 2) 备份（数据 + 配置）----
	mkdir -p "${serverPath}/backup" || {
		echo "[ERROR] 无法创建备份目录 ${serverPath}/backup，升级已中止" >&2
		_yf_redis_try_start "${from}"
		return 1
	}
	local need free
	need=$(du -sk "${serverPath}/redis/data" 2>/dev/null | awk '{print $1}')
	free=$(df -Pk "${serverPath}/backup" 2>/dev/null | awk 'NR==2 {print $4}')
	if [ -n "${need}" ] && [ -n "${free}" ]; then
		if [ "${free}" -lt "$(( need / 2 + need + 10240 ))" ]; then
			echo "[ERROR] 备份空间不足：数据目录约 $(( need / 1024 ))MB，${serverPath}/backup 仅剩 $(( free / 1024 ))MB" >&2
			echo "        请先清理磁盘后重试（已重启 Redis ${from}，数据未做任何改动）" >&2
			_yf_redis_try_start "${from}"
			return 1
		fi
	fi
	bak="${serverPath}/backup/redis_${from}_to_${to}_${ts}.tar.gz"
	echo "[upgrade] 备份数据与配置 → ${bak}"
	if ! tar -czf "${bak}" -C "${serverPath}" redis/data redis/redis.conf 2>/dev/null; then
		# 有些机器上 data 目录可能不存在（纯内存/自定义配置），退化为整目录备份
		echo "[WARN] 常规备份失败，改为整目录备份（数据量大时较慢）" >&2
		if ! tar -czf "${bak}" -C "${serverPath}" redis; then
			echo "[ERROR] 备份失败（${bak}），已中止升级" >&2
			rm -f "${bak}" 2>/dev/null
			_yf_redis_try_start "${from}"
			return 1
		fi
	fi
	if [ ! -s "${bak}" ] || ! tar -tzf "${bak}" >/dev/null 2>&1; then
		echo "[ERROR] 备份包损坏（${bak}），已中止升级" >&2
		rm -f "${bak}" 2>/dev/null
		_yf_redis_try_start "${from}"
		return 1
	fi
	echo "[upgrade] 备份完成：${bak}"

	# ---- 3) 编译新版本到临时前缀 ----
	if ! _yf_redis_fetch_source "${to}"; then
		echo "[ERROR] 升级已中止（源码准备失败），正在重启 Redis ${from}" >&2
		_yf_redis_try_start "${from}"
		return 1
	fi
	if ! _yf_redis_build "${to}" "${staging}"; then
		echo "[ERROR] 升级已中止（新版本编译失败），正在重启 Redis ${from}" >&2
		rm -rf "${staging}"
		_yf_redis_try_start "${from}"
		return 1
	fi

	# ---- 4) 换二进制（data/ 与 redis.conf 原地不动）----
	if ! mv "${serverPath}/redis/bin" "${prev_bin}"; then
		echo "[ERROR] 无法重命名 ${serverPath}/redis/bin（是否被占用？），升级已中止" >&2
		rm -rf "${staging}"
		_yf_redis_try_start "${from}"
		return 1
	fi
	if ! mv "${staging}/bin" "${serverPath}/redis/bin"; then
		echo "[ERROR] 无法替换 ${serverPath}/redis/bin，正在回滚" >&2
		if ! mv "${prev_bin}" "${serverPath}/redis/bin" 2>/dev/null; then
			echo "[ERROR] 替换 bin 失败后也未能还原 ${prev_bin}，请手工处理（备份：${bak}）" >&2
		fi
		rm -rf "${staging}"
		_yf_redis_try_start "${from}"
		return 1
	fi
	rm -rf "${staging}"

	# ---- 5) 启动 + 回读版本 ----
	echo "[upgrade] 启动 Redis ${to} ..."
	( cd "${rootPath}" && python3 "${rootPath}/plugins/redis/index.py" start ) || ok=1
	if [ "${ok}" = "0" ]; then
		live_ver=$("${serverPath}/redis/bin/redis-server" -v 2>/dev/null | sed -n 's/.*v=\([0-9][0-9.]*\).*/\1/p')
		if [ "${live_ver}" != "${to}" ]; then
			echo "[ERROR] 升级后二进制版本回读不符：期望 ${to}，实际 '${live_ver}'" >&2
			ok=1
		fi
	fi
	if [ "${ok}" = "0" ]; then
		if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/redis/index.py" initd_install ); then
			echo "[WARN] 注册 Redis 开机自启失败（可在面板里手动重试）" >&2
		fi
	fi

	if [ "${ok}" != "0" ]; then
		echo "[ERROR] 升级失败，正在回滚到 ${from} ..." >&2
		_yf_redis_try_stop "${from}"
		rm -rf "${serverPath}/redis/bin"
		if mv "${prev_bin}" "${serverPath}/redis/bin"; then
			if ! ( cd "${rootPath}" && python3 "${rootPath}/plugins/redis/index.py" start ); then
				echo "[WARN] 回滚后启动 Redis ${from} 失败，请手动执行：/etc/init.d/redis start" >&2
			fi
			echo "[ERROR] 已回滚到 Redis ${from}；完整备份在 ${bak}" >&2
		else
			echo "[ERROR] 回滚时无法恢复 ${prev_bin}，请手工处理；完整备份在 ${bak}" >&2
		fi
		return 1
	fi

	echo "${to}" > "${serverPath}/redis/version.pl"
	echo "[upgrade] Redis 已升级到 ${to}"
	echo "[upgrade] 升级前的二进制保留在 ${prev_bin}（确认业务正常后可手工删除）"
	echo "[upgrade] 升级前的数据备份：${bak}"
	return 0
}

Install_App()
{
	if [ -d $serverPath/redis ] && [ -f $serverPath/redis/bin/redis-server ]; then
		_cur_ver=""
		if [ -f "$serverPath/redis/version.pl" ]; then
			_cur_ver=$(tr -d '[:space:]' < "$serverPath/redis/version.pl" 2>/dev/null) || _cur_ver=""
		fi
		if [ -z "${_cur_ver}" ] || [ "${_cur_ver}" == "${VERSION}" ]; then
			echo "检测到 Redis 已存在部署实例，正在执行平滑无损升级与环境自愈 (版本: ${VERSION})..."
			if [ -n "${VERSION}" ]; then
				echo "${VERSION}" > $serverPath/redis/version.pl
			fi
			# 执行平滑升级与大版本自愈迁移（配置校验、服务守护进程注册、状态对齐）
			cd ${rootPath} && python3 ${rootPath}/plugins/redis/index.py detect_version
			cd ${rootPath} && python3 ${rootPath}/plugins/redis/index.py check_plugin_upgrade
			cd ${rootPath} && python3 ${rootPath}/plugins/redis/index.py upgrade_self_healing
			cd ${rootPath} && python3 ${rootPath}/plugins/redis/index.py initd_install
			echo "Redis 平滑无损升级与环境自愈完成！"
			exit 0
		fi

		# ---- 换版本（同大版本）----
		# 必须由面板「升级到 x.y.z」入口显式确认，避免误点/脚本误调把线上实例换掉。
		if [ "${YF_REDIS_ALLOW_UPGRADE:-0}" != "1" ]; then
			echo "[ERROR] 已安装 Redis ${_cur_ver}，安装/更新到 ${VERSION} 需要显式确认。" >&2
			echo "        请在软件商店里点「升级到 ${VERSION}」（会自动备份数据并支持失败回滚）。" >&2
			exit 1
		fi
		_cur_major=${_cur_ver%%.*}
		_tgt_major=${VERSION%%.*}
		if [ "${_cur_major}" != "${_tgt_major}" ]; then
			echo "[ERROR] 拒绝跨主版本升级：${_cur_ver} → ${VERSION}。" >&2
			echo "        Redis 跨大版本（如 6.x→7.x）的数据格式与配置项差异较大，面板不做一键升级；" >&2
			echo "        请先备份数据（BGSAVE/COPY 文件），再卸载重装目标版本。" >&2
			exit 1
		fi
		if _yf_redis_ver_gt "${_cur_ver}" "${VERSION}"; then
			echo "[ERROR] 拒绝降级：已装 ${_cur_ver} 比目标 ${VERSION} 更新。" >&2
			echo "        Redis 降级读不了新版本写出的 RDB/AOF，面板不提供降级。" >&2
			exit 1
		fi

		_yf_redis_upgrade "${_cur_ver}" "${VERSION}" || exit 1
		exit 0
	fi

	echo '正在安装脚本文件...'
	mkdir -p $serverPath/source
	mkdir -p $serverPath/source/redis

	_yf_redis_fetch_source "${VERSION}" || exit 1
	_yf_redis_build "${VERSION}" "$serverPath/redis" || exit 1

	if [ -d $serverPath/redis ];then
		mkdir -p $serverPath/redis/data
		if [ ! -f $serverPath/redis/redis.conf ];then
			# 用插件自带的配置模板（绝对路径）：旧写法读的是 `./redis.conf`，
			# 依赖调用方 cwd，面板外的 cwd 下根本没有这个文件 → 生成 0 字节配置，
			# 只能靠 index.py 的 detectAndFixConf 兜底自愈。
			if [ -f "${curPath}/config/redis.conf" ]; then
				sed '/^ *#/d' "${curPath}/config/redis.conf" > $serverPath/redis/redis.conf
			fi
		else
			sed -i 's/slave-serve-stale-data/replica-serve-stale-data/g' $serverPath/redis/redis.conf
			sed -i 's/slave-read-only/replica-read-only/g' $serverPath/redis/redis.conf
			sed -i 's/slave-priority/replica-priority/g' $serverPath/redis/redis.conf
			sed -i 's/client-output-buffer-limit slave/client-output-buffer-limit replica/g' $serverPath/redis/redis.conf
			sed -i '/ziplist/d' $serverPath/redis/redis.conf
			sed -i '/intset/d' $serverPath/redis/redis.conf
		fi

		# 系统内核参数自动优化 (消除 Redis 经典警告) + ARM 架构兼容
		_yf_redis_tune_system

		echo "${VERSION}" > $serverPath/redis/version.pl
		echo '安装完成'

		cd ${rootPath} && python3 ${rootPath}/plugins/redis/index.py start
		cd ${rootPath} && python3 ${rootPath}/plugins/redis/index.py initd_install
		
	else
		# 不能只打一句「安装失败!」就 exit 0：面板会当成成功。
		echo "[ERROR] 安装失败：${serverPath}/redis 目录不存在" >&2
		exit 1
	fi

	if [ -d ${serverPath}/source/redis/redis-${VERSION} ];then
		rm -rf ${serverPath}/source/redis/redis-${VERSION}
	fi
}

Uninstall_App()
{
	# 卸载前置：停 unit + 按「可执行文件在本插件目录下」杀残留（含程序文件已删的僵尸）
	yf_svc_force_stop "${serverPath}/redis" redis || echo "[WARN] redis 仍有进程残留（见上方日志），卸载继续但端口可能被占" >&2
	if [ -f /usr/lib/systemd/system/redis.service ];then
		systemctl stop redis
		systemctl disable redis
		rm -rf /usr/lib/systemd/system/redis.service
		systemctl daemon-reload
	fi

	if [ -f /lib/systemd/system/redis.service ];then
		systemctl stop redis
		systemctl disable redis
		rm -rf /lib/systemd/system/redis.service
		systemctl daemon-reload
	fi

	if [ -f $serverPath/redis/initd/redis ];then
		$serverPath/redis/initd/redis stop
	fi

	if [ -d $serverPath/redis ];then
		rm -rf $serverPath/redis
	fi
	
	echo "卸载redis成功"
}

action="${_yf_redis_action}"
if [ "${action}" == 'install' ] || [ "${action}" == 'update' ] || [ "${action}" == 'upgrade' ];then
	Install_App
else
	Uninstall_App
fi
