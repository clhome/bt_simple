#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

if [ -f ${rootPath}/bin/activate ];then
	source ${rootPath}/bin/activate
fi

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

action=$1
type=$2
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

if [ "${is_fast}" == "false" ] && [ ! -d $curPath/versions/$type ];then
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
    local url=""

    if [[ "${version_main}" == "5.7" ]]; then
        mysql_full_ver="5.7.44"
        suffix_name="${mysql_full_ver}-linux-glibc2.12-${os_arch}"
        tar_file="mysql-${suffix_name}.tar.gz"
        url="https://cdn.mysql.com/Downloads/MySQL-5.7/${tar_file}"
    elif [[ "${version_main}" == "8.0" ]]; then
        mysql_full_ver="8.0.40"
        suffix_name="${mysql_full_ver}-linux-glibc2.28-${os_arch}"
        tar_file="mysql-${suffix_name}.tar.xz"
        url="https://cdn.mysql.com/Downloads/MySQL-8.0/${tar_file}"
    elif [[ "${version_main}" == "8.2" ]]; then
        mysql_full_ver="8.2.0"
        suffix_name="${mysql_full_ver}-linux-glibc2.28-${os_arch}"
        tar_file="mysql-${suffix_name}.tar.xz"
        url="https://cdn.mysql.com/Downloads/MySQL-8.2/${tar_file}"
    elif [[ "${version_main}" == "8.4" ]]; then
        mysql_full_ver="8.4.3"
        suffix_name="${mysql_full_ver}-linux-glibc2.28-${os_arch}"
        tar_file="mysql-${suffix_name}.tar.xz"
        url="https://cdn.mysql.com/Downloads/MySQL-8.4/${tar_file}"
    elif [[ "${version_main}" == "9.0" ]]; then
        mysql_full_ver="9.0.1"
        suffix_name="${mysql_full_ver}-linux-glibc2.28-${os_arch}"
        tar_file="mysql-${suffix_name}.tar.xz"
        url="https://cdn.mysql.com/Downloads/MySQL-9.0/${tar_file}"
    elif [[ "${version_main}" == "9.7" ]]; then
        mysql_full_ver="9.7.0"
        suffix_name="${mysql_full_ver}-linux-glibc2.28-${os_arch}"
        tar_file="mysql-${suffix_name}.tar.xz"
        url="https://cdn.mysql.com/Downloads/MySQL-9.7/${tar_file}"
    else
        # 动态兜底逻辑
        mysql_full_ver="${version_main}.0"
        suffix_name="${mysql_full_ver}-linux-glibc2.28-${os_arch}"
        tar_file="mysql-${suffix_name}.tar.xz"
        url="https://cdn.mysql.com/Downloads/MySQL-${version_main}/${tar_file}"
    fi

    local my_dir=${serverPath}/source/mysql
    mkdir -p ${my_dir}
    mkdir -p ${serverPath}/mysql

    echo "正在从 ${url} 下载部署包..."
    if command -v mw_download &> /dev/null; then
        mw_download ${my_dir}/${tar_file} ${url}
    else
        wget --no-check-certificate -O ${my_dir}/${tar_file} ${url}
    fi

    if [ -f ${my_dir}/${tar_file} ]; then
        echo "包下载完成，正在进行解压部署..."
        cd ${my_dir}
        if [[ "${tar_file}" == *.tar.xz ]]; then
            tar -Jxf ${tar_file}
        else
            tar -zxf ${tar_file}
        fi
        
        # 拷贝到目标运行目录，并设置正确的拥有者
        cp -rf ${my_dir}/mysql-${suffix_name}/* ${serverPath}/mysql/
        chown -R mysql:mysql ${serverPath}/mysql/
        
        # 清理多余缓存文件
        rm -rf ${my_dir}/mysql-${suffix_name}
        rm -f ${my_dir}/${tar_file}

        # 写入 version.pl 标识文件
        echo "${version_main}" > ${serverPath}/mysql/version.pl
        echo "MySQL-${version_main} (Tar 极速二进制版) 核心部署部署成功！"
        return 0
    else
        echo "网络错误：下载 MySQL 通用预编译包失败，请检查官方源状态！"
        exit 1
    fi
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
        echo 'MySQL 服务已存在，跳过安装。'
        exit 0
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
    fi
fi
