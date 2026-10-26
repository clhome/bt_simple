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

Install_phpmyadmin()
{
	if [ -d $serverPath/phpmyadmin ];then
		exit 0
	fi

	mkdir -p ${serverPath}/source/phpmyadmin

	# 《问题报告》次要-1：旧实现把 VER 写死为 5.2.3、不读传入的版本参数，
	# 面板上选 5.2.1 却装出 5.2.3（info.json 里还挂着 4.4.15/4.9.11/5.2.1）。
	# 现在：以 $2 为准，空则用默认 5.2.3；4.x 早期版本没有 .tar.xz，所以两种包都试。
	VER="${2:-}"
	if [ -z "${VER}" ]; then
		VER=5.2.3
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

		# 优先从项目 GitHub Release 下载（自带国内代理加速）
		GH_URL="https://github.com/clhome/bt_simple/releases/download/init/$FILE"
		if ! github_download "$_try_path" "$GH_URL" >/dev/null 2>&1; then
			# GitHub 源不可用：不是失败（下面还有官方源回退），清掉残留半成品
			rm -f "$_try_path" 2>/dev/null
		fi

		# 回退：尝试官方源
		if [ ! -s "$_try_path" ]; then
			rm -f "$_try_path" 2>/dev/null
			echo "GitHub 源不可用，尝试官方源: ${FILE}"
			OFFICIAL_URL="https://files.phpmyadmin.net/phpMyAdmin/${VER}/$FILE"
			if command -v curl >/dev/null 2>&1; then
				curl -fsSL -L --connect-timeout 15 --max-time 300 -o "$_try_path" "$OFFICIAL_URL" || rm -f "$_try_path"
			fi
		fi

		if [ -s "$_try_path" ]; then
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

	echo "${VER}" > ${serverPath}/phpmyadmin/version.pl
	cd ${rootPath} && python3 ${rootPath}/plugins/phpmyadmin/index.py start
	
	echo '安装完成'
}

Uninstall_phpmyadmin()
{
	cd ${rootPath} && python3 ${rootPath}/plugins/phpmyadmin/index.py stop
	
	rm -rf ${serverPath}/phpmyadmin
	echo '卸载完成'
}

action=$1
if [ "${1}" == 'install' ];then
	Install_phpmyadmin
else
	Uninstall_phpmyadmin
fi
