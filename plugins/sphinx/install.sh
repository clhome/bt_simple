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
sysArch=`arch`


if [ -f ${rootPath}/bin/activate ];then
	source ${rootPath}/bin/activate
fi


bash ${rootPath}/scripts/getos.sh
# echo "bash ${rootPath}/scripts/getos.sh"
OSNAME="macos"
if [ -f ${rootPath}/data/osname.pl ];then
	OSNAME=`cat ${rootPath}/data/osname.pl`	
fi

if [ "${OSNAME}" == "centos" ] || 
	[ "${OSNAME}" == "fedora" ] ||
	[ "${OSNAME}" == "alma" ]; then
	yum install -y postgresql-libs unixODBC
fi

# http://sphinxsearch.com/files/sphinx-3.7.1-da9f8a4-linux-amd64.tar.gz

VERSION=$2

# --------------------------------------------------------------------------
# P1-新：参数闸门（裸调必须明确失败，不能「装了个寂寞」还 exit 0）
#   现场：`bash install.sh install`（无版本号）→ VERSION_NUM 未设置 →
#   拼出 sphinx--linux-amd64.tar.gz（404）→ tar 失败，但 `mkdir -p $serverPath/sphinx`
#   早就建好了，于是走到 `if [ -d $serverPath/sphinx ]` 里打印「安装Sphinx完成」，
#   还写了空的 version.pl，最终 EXIT=0。
#   顺带修掉 `action=$1` 的空值陷阱：以前不带参数会直接走 Uninstall（删目录）。
# --------------------------------------------------------------------------
_yf_sphinx_action=$(printf '%s' "${1:-}" | tr -d '\r')
case "${_yf_sphinx_action}" in
	install|uninstall) ;;
	'')
		echo "[ERROR] 缺少动作参数（用法：bash install.sh install <版本号>，例如 install 3.8.1）" >&2
		exit 1
		;;
	*)
		echo "[ERROR] 不支持的动作：${_yf_sphinx_action}（仅支持 install / uninstall）" >&2
		exit 1
		;;
esac

if [ "${_yf_sphinx_action}" == "install" ]; then
	case "${VERSION}" in
		3.1.1|3.2.1|3.3.1|3.4.1|3.5.1|3.6.1|3.7.1|3.8.1) ;;
		*)
			echo "[ERROR] 版本号缺失或不受支持：'${VERSION}'（支持 3.1.1 / 3.2.1 / 3.3.1 / 3.4.1 / 3.5.1 / 3.6.1 / 3.7.1 / 3.8.1）" >&2
			exit 1
			;;
	esac
fi

# echo $VERSION

if [ "$VERSION" == "3.1.1" ];then
	VERSION_NUM=${VERSION}-612d99f
elif [ "$VERSION" == "3.2.1" ]; then
	VERSION_NUM=${VERSION}-f152e0b
elif [ "$VERSION" == "3.3.1" ]; then
	VERSION_NUM=${VERSION}-b72d67b
elif [ "$VERSION" == "3.4.1" ]; then
	VERSION_NUM=${VERSION}-efbcc65
elif [ "$VERSION" == "3.5.1" ]; then
	VERSION_NUM=${VERSION}-82c60cb
elif [ "$VERSION" == "3.6.1" ]; then
	VERSION_NUM=${VERSION}-c9dbeda
elif [ "$VERSION" == "3.7.1" ]; then
	VERSION_NUM=${VERSION}-da9f8a4
elif [ "$VERSION" == "3.8.1" ]; then
	VERSION_NUM=${VERSION}-d25e0bb
fi

# echo $VERSION_NUM

Install_sphinx()
{
	echo '正在安装Sphinx...'
	# 注意：这里**不能**先 mkdir $serverPath/sphinx。旧代码先建目录，
	# 后面用 `[ -d $serverPath/sphinx ]` 当成功判据 → 下载/解压全失败也会
	# 打印「安装Sphinx完成」。改为最后按 searchd 二进制回读后再建。
	SPHINX_DIR=${serverPath}/source/sphinx
	mkdir -p $SPHINX_DIR

	SPH_NAME=amd64
	if [ "$sysArch" == "arm64" ];then
		SPH_NAME=amd64
	elif [ "$sysArch" == "x86_64" ]; then
		SPH_NAME=amd64
	elif [ "$sysArch" == "aarch64" ]; then
		SPH_NAME=aarch64
	fi

	if [ "$sysName" == "Darwin" ] && [ "$VERSION" == "3.7.1" ];then
		SPH_NAME=aarch64
	fi

	SPH_SYSNAME=linux
	if [ $sysName == 'Darwin' ]; then
		SPH_SYSNAME=darwin
	elif [ "$sysName" == "aarch64" ]; then
		SPH_NAME=aarch64
	elif [ "$sysName" == "freebsd" ]; then
		SPH_NAME=freebsd
	fi

	if [ "$SPH_SYSNAME" == "linux" ];then
		glibc_ver=`ldd  --version | grep libc | awk -F ')' '{print $2}'|awk '{gsub(/^\s+|\s+$/, "");print}'`
		if [ "$VERSION" == "3.7.1" ] && [ `echo "2.29 > $glibc_ver " | bc` -eq 1 ];then
			SPH_NAME=${SPH_NAME}-glibc2.17
		fi
		if [ "$VERSION" == "3.6.1" ] && [ `echo "2.29 > $glibc_ver " | bc` -eq 1 ];then
			SPH_NAME=${SPH_NAME}-glibc2.17
		fi
	fi
	

	FILE_NAME=sphinx-${VERSION_NUM}-${SPH_SYSNAME}-${SPH_NAME}
	FILE_TGZ=${FILE_NAME}.tar.gz

	echo $FILE_TGZ
	# curl -sSLo ${SPHINX_DIR}/${FILE_TGZ} http://sphinxsearch.com/files/${FILE_TGZ}
	# 本地已有包先按内容验（gzip -t），坏了删掉重下；下载后必须验
	if [ -f "${SPHINX_DIR}/${FILE_TGZ}" ] && ! gzip -t "${SPHINX_DIR}/${FILE_TGZ}" 2>/dev/null; then
		echo "[WARN] 本地已有的 ${FILE_TGZ} 不是有效压缩包（多为 HTML 错误页/截断），已删除重下"
		rm -f "${SPHINX_DIR}/${FILE_TGZ}"
	fi
	if [ ! -f ${SPHINX_DIR}/${FILE_TGZ} ];then
		if ! wget -nv -T 120 -t 2 -O ${SPHINX_DIR}/${FILE_TGZ} http://sphinxsearch.com/files/${FILE_TGZ}; then
			echo "[ERROR] 下载 ${FILE_TGZ} 失败（sphinxsearch.com 不可达或版本不存在）" >&2
			rm -f "${SPHINX_DIR}/${FILE_TGZ}"
			exit 1
		fi
	fi
	if [ ! -s "${SPHINX_DIR}/${FILE_TGZ}" ] || ! gzip -t "${SPHINX_DIR}/${FILE_TGZ}" 2>/dev/null; then
		echo "[ERROR] ${FILE_TGZ} 内容无效（不是 gzip 包），请检查网络/镜像" >&2
		rm -f "${SPHINX_DIR}/${FILE_TGZ}"
		exit 1
	fi

	if ! ( cd "${SPHINX_DIR}" && tar -zxf "${FILE_TGZ}" ); then
		echo "[ERROR] 解压 ${FILE_TGZ} 失败（包损坏），已清理，请重试" >&2
		rm -f "${SPHINX_DIR}/${FILE_TGZ}"
		exit 1
	fi

	# 先落到暂存目录，成功后再落到正式目录：避免「半装状态」被当成已安装
	_yf_stage="${serverPath}/sphinx.__staging__"
	rm -rf "${_yf_stage}"
	mkdir -p "${_yf_stage}/bin"
	if ! cp -rf ${SPHINX_DIR}/sphinx-${VERSION}/. "${_yf_stage}/bin/"; then
		echo "[ERROR] 复制 sphinx-${VERSION} 到安装目录失败" >&2
		rm -rf "${_yf_stage}"
		exit 1
	fi
	# 回读：二进制必须在（有的包在 bin/bin/searchd）
	if [ ! -x "${_yf_stage}/bin/searchd" ] && [ ! -x "${_yf_stage}/bin/bin/searchd" ]; then
		echo "[ERROR] 安装产物缺失：${_yf_stage}/bin 下没有 searchd 可执行文件" >&2
		rm -rf "${_yf_stage}"
		exit 1
	fi
	rm -rf $serverPath/sphinx
	mv -f "${_yf_stage}" $serverPath/sphinx
	
	# 成功判据：二进制真的在（不是「目录存在」）
	if [ ! -x "$serverPath/sphinx/bin/searchd" ] && [ ! -x "$serverPath/sphinx/bin/bin/searchd" ]; then
		echo "[ERROR] 安装失败：$serverPath/sphinx 下没有 searchd" >&2
		exit 1
	fi

	echo "${VERSION}" > $serverPath/sphinx/version.pl
	echo '安装Sphinx完成'
	# 面板侧启动/注册失败不影响「已装好」的结论（二进制已回读通过），但不能静默
	if ! (cd ${rootPath} && python3 ${rootPath}/plugins/sphinx/index.py start); then
		echo '[WARN] Sphinx 已安装，但面板侧启动失败（可在面板里手动启动）' >&2
	fi
	if [ $sysName != 'Darwin' ]; then
		if ! (cd ${rootPath} && python3 ${rootPath}/plugins/sphinx/index.py initd_install); then
			echo '[WARN] Sphinx 已安装，但开机自启注册失败' >&2
		fi
	fi

	if [ -d ${SPHINX_DIR}/sphinx-${VERSION} ];then
		rm -rf ${SPHINX_DIR}/sphinx-${VERSION}
	fi
}

Uninstall_sphinx()
{
	# 卸载前置：停 unit + 按「可执行文件在本插件目录下」杀残留（含程序文件已删的僵尸）
	yf_svc_force_stop "${serverPath}/sphinx" sphinx || echo "[WARN] sphinx 仍有进程残留（见上方日志），卸载继续但端口可能被占" >&2
	if [ -f /usr/lib/systemd/system/sphinx.service ] || [ -f /lib/systemd/system/sphinx.service ];then
		systemctl stop sphinx
		systemctl disable sphinx

		if [ -f /usr/lib/systemd/system/sphinx.service ];then
			rm -rf /usr/lib/systemd/system/sphinx.service
		fi

		if [ -f /lib/systemd/system/sphinx.service ];then
			rm -rf /lib/systemd/system/sphinx.service
		fi
		systemctl daemon-reload
	fi

	if [ -f $serverPath/sphinx/initd/sphinx ];then
		$serverPath/sphinx/initd/sphinx stop
	fi

	if [ -d $serverPath/sphinx ];then
		echo "rm -rf $serverPath/sphinx"
		rm -rf $serverPath/sphinx
	fi

	echo "卸载sphinx成功"
}

if [ "${_yf_sphinx_action}" == 'install' ];then
	Install_sphinx
else
	Uninstall_sphinx
fi
