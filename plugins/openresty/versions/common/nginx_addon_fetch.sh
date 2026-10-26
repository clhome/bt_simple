#!/bin/bash
# ---------------------------------------------------------------------------------
# OpenResty 附加模块（GitHub 源码包）获取器
#
# 为什么需要：7 份 `versions/*/install.sh` 里都写着同一个形状 ——
#
#     if [ ! -d ${openrestyDir}/ngx_cache_purge-master ];then
#         github_download ${openrestyDir}/ngx_cache_purge.tar.gz <url>
#         cd ${openrestyDir} && tar -zxf ngx_cache_purge.tar.gz
#     fi
#     OPTIONS="${OPTIONS} --add-module=${openrestyDir}/ngx_cache_purge-master"
#
# 三个问题：
#   1. **不看 `github_download` 的返回值**：CI 上 GitHub 取不到包（限流/劫持）时，
#      脚本照样往下走；
#   2. **不校验压缩包**：代理返回的 HTML 错误页/截断包会让 `tar` 造出
#      `ngx_cache_purge-master/` 但里面没有 `config` —— 于是 `./configure` 报
#      「no /www/server/source/openresty/ngx_cache_purge-master/config was found」，
#      看起来像 OpenResty 本身编译失败（GitHub Action 实际报障就是这样）；
#   3. 失败后**残留半成品目录**：下次重跑命中 `[ ! -d ... ]` 直接跳过，永久坏掉。
#   4. **包内顶层目录名跟 $_name 对不上就永远装不上**（本轮新增，报告 P1-2）：
#      GitHub archive 包的顶层目录名来自**分支名**。nginx-modules/ngx_cache_purge
#      的默认分支已从 master 改为 main，`refs/heads/master.tar.gz` 仍返回 200，
#      但解出来的是 `ngx_cache_purge-main/`，而守卫/`--add-module` 钉的是 `-master`
#      ⇒ 每次都重新下载、每次都判「缺 config」。本文件因此改成「按包内实际顶层
#      目录解压 → 目录名归一化回 $_name」，不依赖上游分支叫什么。
#
# 本文件把这件事收敛成一个函数：下载 → 校验 gzip 完整性 → 解压 → **校验标记文件**，
# 任一步失败就清空目录重试一次，最终仍失败则打印可执行的诊断并 `exit 1`
# （绝不让残缺模块进 `./configure`）。
# ---------------------------------------------------------------------------------

# 用法: yf_nginx_addon_fetch <openrestyDir> <模块目录名> <下载URL> <标记文件相对路径>
# 例:   yf_nginx_addon_fetch "$openrestyDir" ngx_cache_purge-master \
#           https://github.com/nginx-modules/ngx_cache_purge/archive/refs/heads/master.tar.gz config
# 返回: 0 = 目录已就绪且标记文件存在；非 0 = 失败（已打印原因）
yf_nginx_addon_fetch() {
	local _dir=$1
	local _name=$2
	local _url=$3
	local _marker=${4:-config}
	local _repo=${5:-}
	local _target="$_dir/$_name"
	local _tarball="$_dir/.yf_${_name}.tar.gz"
	local _attempt=0
	local _reason=""

	# ① 已经就绪（有标记文件）⇒ 幂等返回
	if [ -f "$_target/$_marker" ]; then
		return 0
	fi
	# ② 目录在但没有标记文件 = 上一次残留的半成品，先清掉
	if [ -d "$_target" ]; then
		echo "[WARN] 模块目录不完整（缺少 ${_marker}），清理后重新获取: $_target"
		rm -rf "$_target"
	fi

	if ! command -v github_download >/dev/null 2>&1; then
		echo "[ERROR] 缺少 github_download 函数（scripts/github_download.sh 未加载），无法获取 ${_name}"
		return 1
	fi

	while [ "$_attempt" -lt 2 ]; do
		_attempt=$((_attempt + 1))
		rm -f "$_tarball" 2>/dev/null
		echo "[INFO] 获取 nginx 模块 ${_name}（第 ${_attempt} 次）: $_url"
		if ! github_download "$_tarball" "$_url"; then
			_reason="下载失败（GitHub 直连与全部代理均未取到）"
			echo "[WARN] ${_name}: ${_reason}"
			continue
		fi
		if [ ! -s "$_tarball" ]; then
			_reason="下载文件为空"
			echo "[WARN] ${_name}: ${_reason}"
			continue
		fi
		# gzip 完整性：代理返回 HTML 错误页/截断包在这里就会被拦住
		if ! gzip -t "$_tarball" 2>/dev/null; then
			_reason="下载内容不是有效的 gzip 包（多为代理返回的 HTML 错误页或截断包）"
			echo "[WARN] ${_name}: ${_reason}"
			rm -f "$_tarball" 2>/dev/null
			continue
		fi
		rm -rf "$_target" 2>/dev/null
		# 解压用「先 cd 再相对路径」：`tar -f C:/x.tar.gz` 会被 GNU tar 当成
		# `host:path` 远程归档（报 "Cannot connect to C: resolve failed"），
		# 这也是 CI/Windows 上最容易踩的一脚。同理不吞 tar 的报错 —— 它的提示
		# （磁盘满/权限/包损坏）就是最好的诊断。
		#
		# 解压**之前**先读出包内顶层目录名：GitHub archive 包的顶层目录名取自
		# **分支名**，上游一改名就跟 $_name（如 ngx_cache_purge-master）对不上。
		# 真实案例（《问题报告》P1-2）：nginx-modules/ngx_cache_purge 的默认分支
		# 已从 master 改为 main，请求 refs/heads/master.tar.gz 依旧返回 200，但解
		# 出来的目录是 ngx_cache_purge-main/ ⇒ 守卫永远看不到 -master ⇒ 每次都重
		# 下载、每次都判「缺 config」，最后只能靠 git clone 兜底（没装 git 的机器
		# 直接装不上）。修法：按包内实际顶层目录解压，再把目录名归一化回 $_name。
		_top=$(tar -tzf "$_tarball" 2>/dev/null | head -n 1 | cut -d/ -f1)
		case "$_top" in
			'' | . | .. | *..* | */* | *' '*) _top="" ;;
		esac
		if ! ( cd "$_dir" && tar -zxf "./.yf_${_name}.tar.gz" ); then
			_reason="解压失败"
			echo "[WARN] ${_name}: ${_reason}"
			rm -rf "$_target" "$_tarball" 2>/dev/null
			continue
		fi
		# 包内顶层目录与期望名不一致 ⇒ 改名（同层 mv，不跨文件系统）
		if [ -n "$_top" ] && [ "$_top" != "$_name" ] && [ -d "$_dir/$_top" ]; then
			if mv "$_dir/$_top" "$_target"; then
				echo "[INFO] 包内目录名与预期不同（${_top} vs ${_name}），已归一化"
			else
				_reason="包内目录 ${_top} 无法重命名为 ${_name}"
				echo "[WARN] ${_name}: ${_reason}"
				rm -rf "$_dir/$_top" "$_tarball" 2>/dev/null
				continue
			fi
		fi
		rm -f "$_tarball" 2>/dev/null
		if [ -f "$_target/$_marker" ]; then
			echo "[OK] 模块就绪: $_target"
			return 0
		fi
		_reason="解压后缺少 ${_marker}（包结构不对/不是该模块的 master 包）"
		echo "[WARN] ${_name}: ${_reason}"
		rm -rf "$_target" 2>/dev/null
	done

	# ③ 兜底：走 git clone（与 codeload 是不同的限流通道）
	if [ -n "$_repo" ] && command -v github_clone >/dev/null 2>&1; then
		echo "[INFO] tar 包获取失败，改用 git clone 兜底: $_repo"
		rm -rf "$_target" 2>/dev/null
		if github_clone "$_target" "$_repo" && [ -f "$_target/$_marker" ]; then
			echo "[OK] 模块就绪（clone）: $_target"
			return 0
		fi
		_reason="${_reason}；git clone 兜底也失败"
		rm -rf "$_target" 2>/dev/null
	fi

	echo ""
	echo "[ERROR] 无法获取 nginx 附加模块 ${_name}，已中止安装（不进入 configure，避免残缺模块）"
	echo "[ERROR] 最后一次原因: ${_reason:-未知}"
	echo "[ERROR] 处理建议:"
	echo "[ERROR]   1) 确认本机可访问 github.com（或配置可用的代理：见 scripts/proxies.list）"
	echo "[ERROR]   2) 手工下载后解压到 ${_target} 并确保存在 ${_marker}，再重试安装"
	echo "[ERROR]   3) 若为网络限流，请稍后重试（CI 上的 GitHub 匿名下载经常被限流）"
	return 1
}
