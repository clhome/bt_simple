#!/bin/bash
# ---------------------------------------------------------------------------------
# PHP 源码包获取器（多镜像 / 劫持检测 / sha256 强校验 / 离线包）
#
# 为什么要有这个文件：
#   旧实现在每个 `versions/<NN>/install.sh` 里各写了一遍「先问 ipinfo 是否中国 → 试南京
#   镜像 → 再试官方 → sha256 不符就 `rm` 掉并 `exit 1`」。这在真实机器上表现为：
#     * 内网/校园网网关把 HTTPS 劫持成认证页时，`wget -O` 写下的是一个 3KB 的 HTML，
#       脚本只回一句「下载文件不完整,重新安装」就退出 —— 用户完全无从判断是网络问题；
#     * 只有一个镜像、没有重试，某个镜像当天抖动就直接失败；
#     * 无法离线安装（内网机器根本没有外网）。
#
# 本文件把这件事收敛成**唯一实现**，对外只暴露一个函数：
#
#     yf_php_fetch_source <version> <sha256> <dest_file>
#
#   返回 0 = 文件已就绪且哈希通过；非 0 = 失败（已打印「每个镜像的失败原因 + 处理建议」）。
#
# 关键纪律：
#   * **哈希 fail-closed**：期望哈希非法/为空时直接拒绝下载，绝不「跳过校验」；
#   * **不许把 HTML 当压缩包**：落地前检查 xz 魔数，HTML/空文件/截断文件一律丢弃并说明；
#   * **离线优先**：已存在的合法包、以及运维手工放进来的包（data/php_src、source/php）
#     都直接复用，内网机器只要把包传上来就能装；
#   * **可配置镜像**：`YF_PHP_MIRROR`（前缀目录或含 `{file}` 的模板）优先于内置列表。
# ---------------------------------------------------------------------------------

# 单一真源的 TLS 参数（scripts/github_download.sh::yf_wget_tls_extra_args）。
# 默认**严格校验证书**；只有用户显式 `YF_INSECURE_DOWNLOAD=1` 时才放宽并打 [WARN]。
# 刻意不在这里另写一份「跳过证书校验」的参数：那样等于绕过仓库的 TLS 棘轮守卫。
_yf_php_tls_lib=""
for _p in "${rootPath:-/www/server/yufeng_panel}/scripts/github_download.sh" \
          "/www/server/yufeng_panel/scripts/github_download.sh"; do
	if [ -f "$_p" ]; then
		# shellcheck disable=SC1090
		. "$_p" >/dev/null 2>&1
		_yf_php_tls_lib="$_p"
		break
	fi
done
unset _p

# 这些镜像都提供 php.net 的 distributions 目录镜像（路径形如 /php/php-8.3.36.tar.xz）。
# 官方源放第一位：只有它有「发布即最新」的保证；镜像可能有同步延迟。
YF_PHP_SOURCE_MIRRORS="
https://www.php.net/distributions/
https://mirrors.aliyun.com/php/
https://mirrors.tuna.tsinghua.edu.cn/php/
https://mirrors.ustc.edu.cn/php/
https://mirrors.cloud.tencent.com/php/
https://mirrors.nju.edu.cn/php/
"

# 计算 sha256，兼容精简系统与 macOS
yf_php_sha256() {
	local _f=$1
	if [ ! -f "$_f" ]; then
		return 1
	fi
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$_f" 2>/dev/null | awk '{print $1}'
	elif command -v shasum >/dev/null 2>&1; then
		shasum -a 256 "$_f" 2>/dev/null | awk '{print $1}'
	elif command -v openssl >/dev/null 2>&1; then
		openssl dgst -sha256 "$_f" 2>/dev/null | awk '{print $NF}'
	else
		return 1
	fi
}

# 判断文件是不是真正的 xz 包（魔数 FD 37 7A 58 5A 00）
yf_php_is_xz() {
	local _f=$1
	[ -f "$_f" ] || return 1
	local _magic
	_magic=$(head -c 6 "$_f" 2>/dev/null | od -An -tx1 2>/dev/null | tr -d ' \n')
	case "$_magic" in
		fd377a585a00) return 0 ;;
	esac
	return 1
}

# 判断文件是不是 HTML（网络劫持 / 认证页 / 404 页的典型形态）
yf_php_is_html() {
	local _f=$1
	[ -f "$_f" ] || return 1
	if head -c 512 "$_f" 2>/dev/null | grep -qiE '<(html|!doctype|head|meta|body)'; then
		return 0
	fi
	return 1
}

# 人话描述一个「坏文件」的形态，用于日志
yf_php_describe_file() {
	local _f=$1
	if [ ! -f "$_f" ]; then
		echo "文件不存在"
		return
	fi
	local _size
	_size=$(wc -c < "$_f" 2>/dev/null | tr -d ' ')
	if [ "$_size" = "0" ]; then
		echo "空文件(0 字节)"
		return
	fi
	if yf_php_is_xz "$_f"; then
		echo "xz 压缩包(${_size} 字节)"
		return
	fi
	if yf_php_is_html "$_f"; then
		# 抓一段标题，帮助判断是「运营商认证页」还是「404」
		local _title _raw
		_raw=$(head -c 4096 "$_f" 2>/dev/null | tr -d '\r\n')
		_title=$(echo "$_raw" | grep -oiE '<title[^>]*>[^<]*' | head -1 \
			| sed -e 's/^[^>]*>//' | cut -c1-60)
		echo "HTML 页面(${_size} 字节${_title:+，标题:${_title}})"
		return
	fi
	echo "非 xz 内容(${_size} 字节)"
}

# 校验「文件是否可直接使用」：xz 魔数 + sha256 逐字符比对
# 用法: yf_php_verify_source <file> <sha256>
yf_php_verify_source() {
	local _f=$1
	local _expect=$2
	if [ ! -f "$_f" ]; then
		return 1
	fi
	if ! yf_php_is_xz "$_f"; then
		return 1
	fi
	local _actual
	_actual=$(yf_php_sha256 "$_f") || return 1
	[ -n "$_actual" ] || return 1
	[ "$_actual" = "$_expect" ]
}

# 离线候选目录（运维手工上传的包就放这里；顺序 = 优先级）
yf_php_offline_dirs() {
	local _src_dir=$1
	echo "$_src_dir"
	echo "${serverPath:-/www/server}/source/php"
	echo "/www/server/source/php"
	# 面板 data/php_src：面板侧「上传源码包」落这里（root 可写）
	echo "${rootPath:-/www/server/yufeng_panel}/data/php_src"
}

# 打印所有可用的下载地址（tar.xz）
yf_php_candidate_urls() {
	local _ver=$1
	local _file="php-${_ver}.tar.xz"
	if [ -n "${YF_PHP_MIRROR}" ]; then
		case "${YF_PHP_MIRROR}" in
			*'{file}'*) echo "${YF_PHP_MIRROR//\{file\}/$_file}" ;;
			*'/'*)      echo "${YF_PHP_MIRROR}${_file}" ;;
			*)          echo "${YF_PHP_MIRROR}/${_file}" ;;
		esac
	fi
	local _prefix
	for _prefix in $YF_PHP_SOURCE_MIRRORS; do
		[ -n "$_prefix" ] || continue
		echo "${_prefix}${_file}"
	done
}

# 打印离线目录里已存在的候选文件
yf_php_offline_candidates() {
	local _ver=$1
	local _src_dir=$2
	local _dir
	for _dir in $(yf_php_offline_dirs "$_src_dir"); do
		[ -n "$_dir" ] || continue
		if [ -f "${_dir}/php-${_ver}.tar.xz" ]; then
			echo "${_dir}/php-${_ver}.tar.xz"
		fi
	done
}

# 用 wget 拉一个地址到目标文件；成功仅代表「有字节落盘」，内容由调用方校验
yf_php_wget() {
	local _url=$1
	local _dest=$2
	local _log=$3
	local _tls_args=""
	if command -v yf_wget_tls_extra_args >/dev/null 2>&1; then
		# 注意：不加引号（空值必须展开成「没有参数」）
		# shellcheck disable=SC2046
		_tls_args=$(yf_wget_tls_extra_args "$_url")
	fi
	rm -f "$_dest" 2>/dev/null
	# shellcheck disable=SC2086
	wget -nv $_tls_args --tries=2 --timeout=30 --dns-timeout=10 \
		-O "$_dest" "$_url" >"$_log" 2>&1
}

# 主入口：保证 <dest_file> 存在且 sha256 == <sha256>
# 用法: yf_php_fetch_source <version> <sha256> <dest_file>
yf_php_fetch_source() {
	local _ver=$1
	local _sha=$2
	local _dest=$3

	if ! echo "$_ver" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
		echo "[ERROR] PHP 版本号非法: '${_ver}'（必须是 x.y.z）"
		return 1
	fi
	if ! echo "$_sha" | grep -Eiq '^[0-9a-f]{64}$'; then
		# fail-closed：没有可信哈希就不下载（下载了也无法验证来源）
		echo "[ERROR] 缺少可用的官方 sha256（'${_sha}'），拒绝下载以保持完整性校验"
		return 1
	fi
	_sha=$(echo "$_sha" | tr 'A-Z' 'a-z')

	# ① 目标位置已有合法包：直接用（幂等）
	if yf_php_verify_source "$_dest" "$_sha"; then
		echo "[INFO] 复用已校验的源码包: $_dest"
		return 0
	fi
	# ② 坏包（HTML/截断/哈希不符）：保留证据后清掉
	if [ -f "$_dest" ]; then
		if yf_php_is_xz "$_dest"; then
			echo "[WARN] 已存在的源码包是 xz 包但与目标版本哈希不符（可能是旧版本残留），已清理后重下"
		else
			echo "[WARN] 已存在的源码包不可用（$(yf_php_describe_file "$_dest")），已清理后重下"
		fi
		rm -f "$_dest" 2>/dev/null
	fi

	# ③ 离线包：运维把 php-<ver>.tar.xz 放到 source/php 或 data/php_src 即可
	local _offline
	for _offline in $(yf_php_offline_candidates "$_ver" "$(dirname "$_dest")"); do
		if yf_php_verify_source "$_offline" "$_sha"; then
			echo "[INFO] 使用离线源码包: $_offline"
			cp -f "$_offline" "$_dest" 2>/dev/null && return 0
		else
			if yf_php_is_xz "$_offline"; then
				echo "[WARN] 离线源码包的哈希与目标版本不符（版本不对？），忽略: $_offline"
			else
				echo "[WARN] 离线源码包不是有效的 xz 包（$(yf_php_describe_file "$_offline")），忽略: $_offline"
			fi
		fi
	done

	# ④ 在线下载：逐个镜像试，每个都校验
	local _log
	_log=$(mktemp 2>/dev/null || echo "/tmp/yf_php_dl.$$")
	local _url
	local _last_reason="没有可用镜像"
	if ! command -v wget >/dev/null 2>&1; then
		echo "[ERROR] 系统缺少 wget，无法下载。请安装 wget，或把 php-${_ver}.tar.xz 放到 $(dirname "$_dest") 后重试"
		rm -f "$_log" 2>/dev/null
		return 1
	fi

	for _url in $(yf_php_candidate_urls "$_ver"); do
		echo "[INFO] 尝试下载: $_url"
		if ! yf_php_wget "$_url" "$_dest" "$_log"; then
			_last_reason="wget 失败（$(tail -n 1 "$_log" 2>/dev/null | tr -d '\r')）"
			echo "[WARN] 下载失败: $_url -> $_last_reason"
			rm -f "$_dest" 2>/dev/null
			continue
		fi
		if ! yf_php_is_xz "$_dest"; then
			_last_reason="返回内容不是 xz 包：$(yf_php_describe_file "$_dest")"
			echo "[WARN] 该地址返回的不是源码包: $_url -> $_last_reason"
			rm -f "$_dest" 2>/dev/null
			continue
		fi
		local _actual
		_actual=$(yf_php_sha256 "$_dest") || _actual=""
		if [ -z "$_actual" ]; then
			_last_reason="无法计算 sha256（缺少 sha256sum/shasum/openssl）"
			echo "[WARN] $_last_reason"
			rm -f "$_dest" 2>/dev/null
			break
		fi
		if [ "$_actual" != "$_sha" ]; then
			_last_reason="sha256 不匹配（期望 ${_sha}，实际 ${_actual}）"
			echo "[WARN] 校验失败: $_url -> $_last_reason"
			rm -f "$_dest" 2>/dev/null
			continue
		fi
		echo "[OK] 源码包下载并校验通过: $_url"
		rm -f "$_log" 2>/dev/null
		return 0
	done
	rm -f "$_log" 2>/dev/null

	# ⑤ 全失败：把「试过哪些地址」和「怎么自救」讲清楚（旧实现只有一句「下载文件不完整」）
	echo ""
	echo "[ERROR] 无法获取 PHP ${_ver} 源码包（已尝试 $(echo $(yf_php_candidate_urls "$_ver") | wc -w) 个地址）"
	echo "[ERROR] 最后一次失败原因: ${_last_reason}"
	echo "[ERROR] 常见原因与处理:"
	echo "[ERROR]   1) 本机不能访问外网 / 需要网关认证：先在主机上确认能打开 https://www.php.net/"
	echo "[ERROR]   2) 公司/校园网把 HTTPS 劫持成登录页（返回 HTML）：请配置放行或走代理"
	echo "[ERROR]   3) 内网镜像：在面板「软件 → PHP → 设置 → 常用功能 → 源码镜像」填写前缀，"
	echo "[ERROR]       或给升级任务设置环境变量 YF_PHP_MIRROR=https://你的镜像/php/ 后重试"
	echo "[ERROR]   4) 完全离线：手工下载 php-${_ver}.tar.xz 后放到下面任一目录再重试"
	yf_php_offline_dirs "$(dirname "$_dest")" | sed 's/^/[ERROR]      - /'
	return 1
}
