#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

sysName=`uname`
echo "use system: ${sysName}"

# --------------------------------------------------------------------------
# 问题报告「phpmyadmin 版本接线」：请求 5.2.1 却实装 5.2.3。
#   根因不是 URL 拼接，而是 **bash 函数有自己的位置参数**：`VER="${2:-}"` 写在
#   Install_phpmyadmin() 里，而调用处是无参调用，于是函数内 $2 恒为空 → 永远退回
#   默认 5.2.3。必须在**脚本层**取 $2（见下面的 SCRIPT_VER）。
# --------------------------------------------------------------------------
SCRIPT_VER="${2:-}"

_yf_pma_action="$(printf '%s' "${1:-}" | tr -d '')"
case "${_yf_pma_action}" in
	install|uninstall) ;;
	'')
		echo "[ERROR] 缺少动作参数（用法：bash install.sh install <版本号>，例如 install 5.2.1）" >&2
		exit 1
		;;
	*)
		echo "[ERROR] 不支持的动作：${_yf_pma_action}（仅支持 install / uninstall）" >&2
		exit 1
		;;
esac

Install_phpmyadmin()
{
	if [ -d $serverPath/phpmyadmin ];then
		exit 0
	fi

	mkdir -p ${serverPath}/source/phpmyadmin

	# 《问题报告》次要-1：旧实现把 VER 写死为 5.2.3、不读传入的版本参数，
	# 面板上选 5.2.1 却装出 5.2.3（info.json 里还挂着 4.4.15/4.9.11/5.2.1）。
	# 现在：以 $2 为准，空则用默认 5.2.3；4.x 早期版本没有 .tar.xz，所以两种包都试。
	VER="${SCRIPT_VER}"
	if [ -z "${VER}" ]; then
		# 面板总会传版本；此处仅为手工调用兜底：取 info.json 声明的最后一个版本
		VER=$(sed -n 's/.*"\([0-9][0-9.]*\)".*//p' "$curPath/info.json" 2>/dev/null | tail -n 1)
		[ -n "${VER}" ] || VER=5.2.3
	fi
	# 版本号会进 URL 与目录名，白名单拦住路径穿越/命令注入
	case "${VER}" in
		*[!0-9.]* | '' )
			echo "非法的 phpMyAdmin 版本号: ${VER}" >&2
			exit 1
			;;
	esac
	echo "准备安装 phpMyAdmin ${VER}"
	FDIR=phpMyAdmin-${VER}-all-languages
	FILEPATH=''

	for _ext in tar.xz tar.gz; do
		FILE=phpMyAdmin-${VER}-all-languages.${_ext}
		_try_path=$serverPath/source/phpmyadmin/$FILE

		# 确保已加载完整校验库
		if ! command -v yf_verify_archive >/dev/null 2>&1; then
			if [ -f "${rootPath}/scripts/github_download.sh" ]; then
				source "${rootPath}/scripts/github_download.sh"
			fi
		fi

		# 优先从项目 GitHub Release 下载（自带国内代理加速）
		GH_URL="https://github.com/clhome/bt_simple/releases/download/init/$FILE"
		if github_download "$_try_path" "$GH_URL" >/dev/null 2>&1; then
			if command -v yf_verify_archive >/dev/null 2>&1; then
				if ! yf_verify_archive "$_try_path"; then
					echo "[WARN] GitHub 节点下载的 ${FILE} 完整性校验失败（可能遭遇网络截断或代理错误），清理后回退" >&2
					rm -f "$_try_path" 2>/dev/null
				fi
			fi
		else
			rm -f "$_try_path" 2>/dev/null
		fi

		# 回退：尝试官方源
		if [ ! -f "$_try_path" ] || [ ! -s "$_try_path" ]; then
			rm -f "$_try_path" 2>/dev/null
			echo "GitHub 源不可用或包损坏，尝试官方源: ${FILE}"
			OFFICIAL_URL="https://files.phpmyadmin.net/phpMyAdmin/${VER}/$FILE"
			if command -v curl >/dev/null 2>&1; then
				curl -fsSL -L --connect-timeout 15 --max-time 300 -o "$_try_path" "$OFFICIAL_URL" || rm -f "$_try_path" 2>/dev/null
			elif command -v wget >/dev/null 2>&1; then
				wget -q -O "$_try_path" --timeout=300 "$OFFICIAL_URL" || rm -f "$_try_path" 2>/dev/null
			fi

			if [ -f "$_try_path" ] && command -v yf_verify_archive >/dev/null 2>&1; then
				if ! yf_verify_archive "$_try_path"; then
					echo "[WARN] 官方源下载的 ${FILE} 校验失败，继续尝试下一格式..." >&2
					rm -f "$_try_path" 2>/dev/null
				fi
			fi
		fi

		if [ -f "$_try_path" ] && [ -s "$_try_path" ]; then
			FILEPATH=$_try_path
			break
		fi
	done

	if [ -z "${FILEPATH}" ]; then
		echo "phpMyAdmin ${VER} 下载失败（GitHub 与官方源均不可用，请检查网络连通性）" >&2
		exit 1
	fi

	# 解压（tar 自动识别压缩格式）；腾出解压目录后校验，失败不留半成品
	cd $serverPath/source/phpmyadmin || { echo "无法进入 $serverPath/source/phpmyadmin" >&2; exit 1; }
	rm -rf "$FDIR"
	if ! tar -xf "$FILEPATH"; then
		echo "解压失败: ${FILEPATH}" >&2
		rm -f "$FILEPATH"
		exit 1
	fi

	if [ ! -d $serverPath/source/phpmyadmin/$FDIR ]; then
		echo "下载失败或文件损坏（解压后找不到 ${FDIR}），请检查网络连通性" >&2
		rm -rf "$FDIR"
		rm -f "$FILEPATH" 2>/dev/null
		exit 1
	fi
	
	mkdir -p ${serverPath}/phpmyadmin
	cp -r $serverPath/source/phpmyadmin/$FDIR $serverPath/phpmyadmin/
	cd $serverPath/phpmyadmin/ && mv $FDIR phpmyadmin
	rm -rf $serverPath/source/phpmyadmin/$FDIR

	# 产物回读：安装布局是 <server>/phpmyadmin/phpmyadmin/（index.py 启动时再改名为随机子目录），
	# 已归一化的机器则是 <server>/phpmyadmin/index.php —— 两种都算装好。
	if [ ! -f ${serverPath}/phpmyadmin/index.php ] && 	   [ ! -f ${serverPath}/phpmyadmin/phpmyadmin/index.php ]; then
		echo "[ERROR] 安装产物缺失：${serverPath}/phpmyadmin 下没有 index.php（phpMyAdmin 未解包成功）" >&2
		exit 1
	fi

	echo "${VER}" > ${serverPath}/phpmyadmin/version.pl
	_installed=$(cat ${serverPath}/phpmyadmin/version.pl 2>/dev/null)
	if [ "${_installed}" != "${VER}" ]; then
		echo "[ERROR] 版本回读不一致：请求 ${VER}，落盘 ${_installed}" >&2
		exit 1
	fi

	# 面板侧启动失败不改变「已装好」的结论，但不能静默
	(cd ${rootPath} && python3 ${rootPath}/plugins/phpmyadmin/index.py start) || 		echo "[WARN] phpMyAdmin 已安装，但面板侧启动失败（可在面板里手动启动）" >&2

	echo "安装完成（phpMyAdmin ${VER}）"

}

Uninstall_phpmyadmin()
{
	cd ${rootPath} && python3 ${rootPath}/plugins/phpmyadmin/index.py stop
	
	rm -rf ${serverPath}/phpmyadmin
	echo '卸载完成'
}

if [ "${_yf_pma_action}" == 'install' ];then
	Install_phpmyadmin
else
	Uninstall_phpmyadmin
fi
