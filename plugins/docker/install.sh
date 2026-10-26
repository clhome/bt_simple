#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

VERSION=$2

Install_Docker()
{
	echo '正在安装脚本文件...'
	mkdir -p $serverPath/source

	# 0. 安装基础依赖工具 rsync（用于保障 Docker 目录安全迁移功能）
	#    失败只影响「目录迁移」这一项功能，不阻止引擎安装，但必须让人看见。
	if ! which rsync &> /dev/null; then
		echo '正在补充安装基础依赖工具 rsync...'
		if [ -f /usr/bin/yum ]; then
			yum install -y rsync || echo '[WARN] rsync 安装失败（只影响 Docker 目录迁移功能）' >&2
		elif [ -f /usr/bin/apt-get ]; then
			apt-get update -y && apt-get install -y rsync || echo '[WARN] rsync 安装失败（只影响 Docker 目录迁移功能）' >&2
		fi
	fi

	# 1. 智能检测系统是否已存在 Docker 引擎（防止覆盖破坏原本正在运行的第三方容器引擎）
	if which docker &> /dev/null; then
		echo '系统已检测到已安装 Docker 引擎，跳过底层引擎安装，直接进行面板对接配置...'
	else
		echo '系统未检测到 Docker 引擎，开始为您安全部署标准 Docker 环境...'
		LOCAL_ADDR=$(get_local_addr)
		# 《问题报告》P1-3 机制①：**绝不** `curl ... | bash`。
		# curl 失败时 bash 读空 stdin 依旧 exit 0 —— 「apt 源不通却打印安装成功」的根因之一。
		# 改为先落盘、验「非空 + 是 shell 脚本」、再执行。
		_yf_docker_installer=/tmp/yf-docker-install.$$.sh
		rm -f "$_yf_docker_installer"
		if [ "$LOCAL_ADDR" == "cn" ];then
			_yf_docker_url="https://gitee.com/tech-shrimp/docker_installer/releases/download/latest/linux.sh"
		else
			_yf_docker_url="https://get.docker.com"
		fi
		echo "下载 Docker 安装脚本: $_yf_docker_url"
		if command -v curl >/dev/null 2>&1; then
			curl -fsSL --connect-timeout 20 --max-time 300 -o "$_yf_docker_installer" "$_yf_docker_url" || rm -f "$_yf_docker_installer"
		fi
		if [ ! -s "$_yf_docker_installer" ] && command -v wget >/dev/null 2>&1; then
			wget -nv -T 60 -t 2 -O "$_yf_docker_installer" "$_yf_docker_url" || rm -f "$_yf_docker_installer"
		fi
		# 404 页面/截断包在这里被拦住（真正的一键脚本一定以 shebang 开头）
		if [ ! -s "$_yf_docker_installer" ] || ! head -c 2 "$_yf_docker_installer" | grep -q '#!'; then
			rm -f "$_yf_docker_installer"
			echo '下载 Docker 安装脚本失败（源不可用或被劫持），已中止安装' >&2
			exit 1
		fi
		if [ "$LOCAL_ADDR" == "cn" ];then
			bash "$_yf_docker_installer" -s docker --mirror Aliyun || {
				rm -f "$_yf_docker_installer"
				echo 'Docker 引擎安装脚本执行失败（多为 apt 源不可达或 apt 锁被占用），已中止安装' >&2
				exit 1
			}
		else
			bash "$_yf_docker_installer" || {
				rm -f "$_yf_docker_installer"
				echo 'Docker 引擎安装脚本执行失败，已中止安装' >&2
				exit 1
			}
		fi
		rm -f "$_yf_docker_installer"

		# 《问题报告》P1-3 机制②：启动/自启的退出码必须看。
		# 下面用 if 而不是 `|| true`：允许「已经启动过」这类无害失败，但真正的
		# 启动失败会落到后面的 is-active / docker info 回读上并让安装失败。
		if ! systemctl start docker 2>/dev/null; then
			if ! service docker start 2>/dev/null; then
				echo '[WARN] systemctl/service 启动 docker 均失败，将由 docker info 回读判定'
			fi
		fi
		if ! systemctl enable docker >/dev/null 2>&1; then
			echo '[WARN] 设置 docker 开机自启失败（不影响本次安装，可稍后手动 systemctl enable docker）'
		fi

		# 引擎回读：二进制在不在（脚本 exit 0 不代表装上了）
		if ! command -v docker >/dev/null 2>&1; then
			echo 'Docker 引擎安装失败：系统中找不到 docker 可执行文件（请看上方安装脚本输出）' >&2
			exit 1
		fi

		# 服务回读：is-active（有 systemd 时）+ docker info（真正的功能性判据，给慢启动留重试）
		if command -v systemctl >/dev/null 2>&1; then
			if ! systemctl is-active docker >/dev/null 2>&1; then
				echo 'Docker 服务未启动（systemctl is-active docker 非 active），已中止安装' >&2
				exit 1
			fi
		fi
		_yf_docker_try=0
		while [ "$_yf_docker_try" -lt 10 ]; do
			if docker info >/dev/null 2>&1; then
				break
			fi
			_yf_docker_try=$((_yf_docker_try + 1))
			sleep 2
		done
		if ! docker info >/dev/null 2>&1; then
			echo 'Docker 引擎已安装但 daemon 不可用（docker info 失败），已中止安装' >&2
			echo '排查：journalctl -u docker -n 50 --no-pager' >&2
			exit 1
		fi
		echo 'Docker 引擎安装完成且 daemon 可用'
	fi

	# 2. 强行创建面板的管理专属目录
	if [ ! -d  $serverPath/docker ];then
		mkdir -p $serverPath/docker
	fi

	# 3. 安装 Python SDK 支持库（注入国内清华加速源以防大陆网络超时卡死）
	echo '正在安装面板配套的 Python 管理库依赖...'
	install_python_deps() {
		local pip_cmd=$1
		local LOCAL_ADDR=$(get_local_addr)
		if [ "$LOCAL_ADDR" == "cn" ]; then
			# 依次尝试清华源、阿里云源和官方源
			$pip_cmd install docker pytz -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
			if [ $? -ne 0 ]; then
				echo "清华源安装失败，尝试使用阿里云源..."
				$pip_cmd install docker pytz -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
				if [ $? -ne 0 ]; then
					echo "阿里云源安装失败，尝试使用官方源..."
					$pip_cmd install docker pytz
				fi
			fi
		else
			$pip_cmd install docker pytz
		fi
	}

	if [ -f ${rootPath}/bin/pip3 ];then
		install_python_deps "${rootPath}/bin/pip3" || _yf_pip_rc=$?
	else
		install_python_deps "pip3" || _yf_pip_rc=$?
	fi
	# 《问题报告》P1-3 机制④：面板 docker 页依赖 python 的 docker SDK，
	# 装不上就不能算装好（旧实现完全没人看这个退出码）。
	if [ "${_yf_pip_rc:-0}" -ne 0 ]; then
		echo '面板配套 Python 库（docker/pytz）安装失败，Docker 插件不可用，已中止安装' >&2
		exit 1
	fi
	
	# 3.5 回读：SDK 真的能 import 吗（pip 成功 ≠ 装到了当前解释器）
	if ! python3 -c 'import docker' >/dev/null 2>&1; then
		echo 'Python docker SDK 回读失败（import docker 失败），Docker 插件不可用' >&2
		exit 1
	fi
	
	# 4. 写入面板安装状态和版本标识并启动面板配套后台服务
	# 《问题报告》P1-3 机制③：成功门不再是「本脚本刚 mkdir 的目录存在」这种恒真判断，
	# 而是上面已经回读过的引擎/服务/SDK 三项。
	if [ -d $serverPath/docker ];then
		echo "${VERSION}" > $serverPath/docker/version.pl
		echo '安装Docker插件成功！'

		cd ${rootPath} && python3 ${rootPath}/plugins/docker/index.py start
		cd ${rootPath} && python3 ${rootPath}/plugins/docker/index.py initd_install
	fi
}

Uninstall_Docker()
{
	# 温和、零破坏性卸载：仅移除面板管理端配置与插件状态，安全保留宿主机底层的公共 Docker 引擎服务和所有容器业务数据！
	rm -rf $serverPath/docker
	echo "卸载Docker插件完成（系统底层Docker引擎服务及您的业务容器已安全保留）"
}

action=$1
if [ "${1}" == 'install' ];then
	Install_Docker
else
	Uninstall_Docker
fi
