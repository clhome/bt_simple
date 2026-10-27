#!/bin/bash
if [ -f $(dirname $0)/../../scripts/lib_make_jobs.sh ]; then source $(dirname $0)/../../scripts/lib_make_jobs.sh; elif [ -f /www/server/yufeng_panel/scripts/lib_make_jobs.sh ]; then source /www/server/yufeng_panel/scripts/lib_make_jobs.sh; fi
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")



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
		echo "[ERROR] 缺少动作参数（用法：bash install.sh install <版本号>，例如 install 7.4.8）" >&2
		exit 1
		;;
	*)
		echo "[ERROR] 不支持的动作：${_yf_redis_action}（仅支持 install / update / upgrade / uninstall）" >&2
		exit 1
		;;
esac

if [ "${_yf_redis_action}" != "uninstall" ]; then
	case "${VERSION}" in
		''|*[!0-9.]*|*.*.*.*)
			echo "[ERROR] 版本号缺失或非法：'${VERSION}'（应形如 7.4.8），拒绝拼 redis-.tar.gz 这类空版本包" >&2
			exit 1
			;;
		*.*.*) ;;
		*)
			echo "[ERROR] 版本号缺失或非法：'${VERSION}'（应形如 7.4.8）" >&2
			exit 1
			;;
	esac
fi

Install_App()
{
	if [ -d $serverPath/redis ] && [ -f $serverPath/redis/bin/redis-server ]; then
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

	echo '正在安装脚本文件...'
	mkdir -p $serverPath/source
	mkdir -p $serverPath/source/redis

	FILE_TGZ=redis-${VERSION}.tar.gz
	REDIS_DIR=$serverPath/source/redis


	# 下载与校验（与同族脚本同一个坑：`wget -O` 不看退出码、`tar` 失败也往下走，
	# 结果「下载失败 → 编译一个空目录 → 报一堆无关错误」，或把 HTML 错误页当压缩包）。
	# 口径：已有包先按**内容**验（gzip -t），坏了就删；下载后必须验；解压失败即中止。
	_yf_redis_tgz="$REDIS_DIR/${FILE_TGZ}"
	if [ -f "$_yf_redis_tgz" ] && ! gzip -t "$_yf_redis_tgz" 2>/dev/null; then
		echo "[WARN] 本地已有的 ${FILE_TGZ} 不是有效压缩包（多为 HTML 错误页/截断），已删除重下"
		rm -f "$_yf_redis_tgz"
	fi
	if [ ! -f "$_yf_redis_tgz" ]; then
		if command -v yf_download >/dev/null 2>&1; then
			yf_download "$_yf_redis_tgz" "https://download.redis.io/releases/${FILE_TGZ}" 300
		else
			wget -nv -T 120 -t 2 -O "$_yf_redis_tgz" "https://download.redis.io/releases/${FILE_TGZ}"
		fi
		if [ ! -s "$_yf_redis_tgz" ] || ! gzip -t "$_yf_redis_tgz" 2>/dev/null; then
			echo "[ERROR] 下载 ${FILE_TGZ} 失败或内容无效（不是 gzip 包），请检查网络/镜像" >&2
			rm -f "$_yf_redis_tgz"
			exit 1
		fi
	fi

	if ! ( cd "$REDIS_DIR" && tar -zxf "${FILE_TGZ}" ); then
		echo "[ERROR] 解压 ${FILE_TGZ} 失败（包损坏），已清理，请重试" >&2
		rm -f "$_yf_redis_tgz"
		exit 1
	fi

	# 获取CPU核心数用于多核并行编译加速
	cpuCore=$(nproc 2>/dev/null)
	if [ -z "$cpuCore" ]; then
		cpuCore="1"
# --- yf adaptive clamp (1C512M -> -j1) ---
if command -v yf_make_jobs >/dev/null 2>&1; then _yf_jobs=$(yf_make_jobs 2>/dev/null || echo ""); if [ -n "$_yf_jobs" ] && [ "$_yf_jobs" -ge 1 ] 2>/dev/null; then cpuCore="$_yf_jobs"; fi; fi
	fi

	CMD_MAKE=`which gmake`
	# 编译/安装失败必须中止。旧写法在 `cd redis-<ver>` 失败（解包目录名不符）或 make
	# 报错时只是「没装上」，随后走到 `[ -d $serverPath/redis ]` 的 else 分支打印
	# 「安装失败!」然后 exit 0 —— 面板看到的是成功。
	if [ "$?" == "0" ];then
		if ! ( cd "redis-${VERSION}" && gmake BUILD_TLS=yes -j ${cpuCore} PREFIX="$serverPath/redis" install ); then
			echo "[ERROR] redis 编译/安装失败（gmake，见上方输出）" >&2
			exit 1
		fi
	else
		if ! ( cd "redis-${VERSION}" && make BUILD_TLS=yes -j ${cpuCore} PREFIX="$serverPath/redis" install ); then
			echo "[ERROR] redis 编译/安装失败（make，见上方输出）" >&2
			exit 1
		fi
	fi

	# 装后回读：没有 redis-server 就等于没装上（不能写 version.pl、不能报「安装完成」）
	if [ ! -x "$serverPath/redis/bin/redis-server" ]; then
		echo "[ERROR] 安装产物缺失：$serverPath/redis/bin/redis-server 不存在或不可执行" >&2
		exit 1
	fi

	if [ -d $serverPath/redis ];then
		mkdir -p $serverPath/redis/data
		if [ ! -f $serverPath/redis/redis.conf ];then
			sed '/^ *#/d' redis.conf > $serverPath/redis/redis.conf
		else
			sed -i 's/slave-serve-stale-data/replica-serve-stale-data/g' $serverPath/redis/redis.conf
			sed -i 's/slave-read-only/replica-read-only/g' $serverPath/redis/redis.conf
			sed -i 's/slave-priority/replica-priority/g' $serverPath/redis/redis.conf
			sed -i 's/client-output-buffer-limit slave/client-output-buffer-limit replica/g' $serverPath/redis/redis.conf
			sed -i '/ziplist/d' $serverPath/redis/redis.conf
			sed -i '/intset/d' $serverPath/redis/redis.conf
		fi

		# 系统内核参数自动优化 (消除 Redis 经典警告)
		VM_OVERCOMMIT_MEMORY=$(cat /etc/sysctl.conf | grep vm.overcommit_memory)
		NET_CORE_SOMAXCONN=$(cat /etc/sysctl.conf | grep net.core.somaxconn)
		if [ -z "${VM_OVERCOMMIT_MEMORY}" ] && [ -z "${NET_CORE_SOMAXCONN}" ];then
			echo "vm.overcommit_memory = 1" >> /etc/sysctl.conf
			echo "net.core.somaxconn = 1024" >> /etc/sysctl.conf
			sysctl -p
		fi

		# ARM架构兼容优化
		ARM_CHECK=$(uname -a | grep aarch64)
		if [ "${ARM_CHECK}" ];then
			echo "ignore-warnings ARM64-COW-BUG" >> $serverPath/redis/redis.conf
		fi

		echo "${VERSION}" > $serverPath/redis/version.pl
		echo '安装完成'

		cd ${rootPath} && python3 ${rootPath}/plugins/redis/index.py start
		cd ${rootPath} && python3 ${rootPath}/plugins/redis/index.py initd_install
		
	else
		# 不能只打一句「安装失败!」就 exit 0：面板会当成成功。
		echo "[ERROR] 安装失败：${serverPath}/redis 目录不存在" >&2
		exit 1
	fi

	if [ -d ${REDIS_DIR}/redis-${VERSION} ];then
		rm -rf ${REDIS_DIR}/redis-${VERSION}
	fi
}

Uninstall_App()
{
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
