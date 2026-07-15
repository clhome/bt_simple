#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

PLUGIN_PATH=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
curPath=${PLUGIN_PATH}
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

if [ -f ${rootPath}/bin/activate ];then
	source ${rootPath}/bin/activate
fi

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

# lib.sh 可能会改变 curPath 变量和当前工作目录，这里必须强制恢复
curPath=${PLUGIN_PATH}
cd ${PLUGIN_PATH}

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
	echo '缺少安装脚本...'
	exit 0
fi 

echo "[DEBUG] curPath is: '${curPath}'"
echo "[DEBUG] type is: '${type}'"
echo "[DEBUG] BASH_SOURCE[0] is: '${BASH_SOURCE[0]}'"
echo "[DEBUG] pwd is: '$(pwd)'"
echo "[DEBUG] Checking if directory exists: ${curPath}/versions/${type}"

if [ "${is_fast}" == "false" ] && [ ! -d "$curPath/versions/$type" ];then
	echo '缺少源码编译安装脚本...'
	exit 0
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
            wget -nv --no-check-certificate -O "${tmp_file}" "${mirror_url}"
        fi

        if [ -f "${tmp_file}" ]; then
            # 校验一：文件大小检测 (官方包普遍远大于50MB)
            local file_size=$(stat -c%s "${tmp_file}" 2>/dev/null || stat -f%z "${tmp_file}" 2>/dev/null)
            if [ -n "${file_size}" ] && [ "${file_size}" -gt 52428800 ]; then
                # 校验二：文件类型检测 (防止下载到 HTML 错误页)
                if command -v file >/dev/null 2>&1; then
                    local file_type=$(file -b "${tmp_file}")
                    if [[ "${file_type}" == *"XZ compressed"* ]] || [[ "${file_type}" == *"gzip compressed"* ]] || [[ "${file_type}" == *"tar archive"* ]]; then
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
	
	if [ -f /usr/lib/systemd/system/mysql.service ] || [ -f /lib/systemd/system/mysql.service ];then
		systemctl stop mysql
		systemctl disable mysql
		rm -rf /usr/lib/systemd/system/mysql.service
		rm -rf /lib/systemd/system/mysql.service
		systemctl daemon-reload
	fi

    if [ "${is_fast}" == "true" ]; then
        rm -rf $serverPath/mysql
        echo '极速版卸载完成'
        exit 0
    else
        sh -x $curPath/versions/$type/install.sh uninstall
    fi
fi

if [ "${action}" == "install" ]; then
    if [ -d $serverPath/mysql ]; then
        if [ -f $serverPath/mysql/bin/mysql ]; then
            echo 'MySQL 服务已存在，跳过安装。'
            exit 0
        else
            echo '检测到残留的不完整 MySQL 目录，正在清理...'
            rm -rf $serverPath/mysql
        fi
    fi

    if [ "${is_fast}" == "true" ]; then
        Install_fast_mysql "${type}"
    else
        sh -x $curPath/versions/$type/install.sh install
    fi

    if [ -d $serverPath/mysql ]; then
        # 执行初始化与自启动服务写入
        cd ${rootPath} && python3 ${rootPath}/plugins/mysql/index.py start ${type}
        cd ${rootPath} && python3 ${rootPath}/plugins/mysql/index.py initd_install ${type}
        cd ${rootPath} && python3 ${rootPath}/plugins/mysql/index.py fix_db_access ${type}
    fi
fi
