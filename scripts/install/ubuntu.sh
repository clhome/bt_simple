#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH
export LANG=en_US.UTF-8
export DEBIAN_FRONTEND=noninteractive

function version_gt() { test "$(echo "$@" | tr " " "\n" | sort -V | head -n 1)" != "$1"; }
function version_le() { test "$(echo "$@" | tr " " "\n" | sort -V | head -n 1)" == "$1"; }
function version_lt() { test "$(echo "$@" | tr " " "\n" | sort -rV | head -n 1)" != "$1"; }
function version_ge() { test "$(echo "$@" | tr " " "\n" | sort -rV | head -n 1)" == "$1"; }


if grep -Eq "Ubuntu" /etc/*-release; then
    sudo ln -sf /bin/bash /bin/sh
    #sudo dpkg-reconfigure dash
fi

# 前置更新软件包源，防止 404
apt update -y -o Acquire::Languages=none

# 智能批量/分级安装函数
function smart_apt_install() {
    local pkgs=("$@")
    echo "正在尝试一次性批量安装系统依赖包..."
    if apt install -y "${pkgs[@]}"; then
        return 0
    fi
    
    echo "警告：批量安装失败，可能因为某些软件包在当前源中不存在。正在尝试逐个检查并安装..."
    for pkg in "${pkgs[@]}"; do
        if ! apt install -y "$pkg"; then
            echo "警告: 软件包 $pkg 安装失败，跳过。"
        fi
    done
}

# SSH 端口检测
SSH_PORT=`netstat -ntpl|grep sshd|grep -v grep | sed -n "1,1p" | awk '{print $4}' | awk -F : '{print $2}'`
if [ "$SSH_PORT" == "" ];then
	SSH_PORT_LINE=`cat /etc/ssh/sshd_config | grep "Port \d*" | tail -1`
	SSH_PORT=${SSH_PORT_LINE/"Port "/""}
fi
echo "SSH PORT:${SSH_PORT}"

# 区域与语言设置
if [ ! -f /usr/sbin/locale-gen ];then
	apt install -y locales
	sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen
	locale-gen en_US.UTF-8
	locale-gen zh_CN.UTF-8
	localedef -v -c -i en_US -f UTF-8 en_US.UTF-8 > /dev/null 2>&1
	update-locale LANG=en_US.UTF-8
else
	locale-gen en_US.UTF-8
	locale-gen zh_CN.UTF-8
	localedef -v -c -i en_US -f UTF-8 en_US.UTF-8 > /dev/null 2>&1
fi

# 批量安装常规系统依赖
PACKAGES=(
    chrony ntpdate wget curl unzip lsof xz-utils python3-pip python3-venv
    python3-dev expect pv bc cron net-tools libncurses5 libncurses5-dev software-properties-common
    bzip2 p7zip-full libnuma1 libaio1 libaio-dev libmecab2 numactl libmm-dev
    dnsutils xxd libprotobuf-dev protobuf-compiler libboost-dev liblz4-tool zstd sshpass
    libzstd-dev libbrotli-dev devscripts autoconf gcc lrzsz libffi-dev cmake automake make
    webp scons libwebp-dev liblzma-dev libunwind-dev libpcre3 libpcre3-dev openssl libssl-dev
    libargon2-dev libmemcached-dev libsasl2-dev imagemagick libmagickcore-dev libmagickwand-dev
    libxml2 libxml2-dev libbz2-dev libmcrypt-dev libpspell-dev librecode-dev libgmp-dev
    libreadline-dev libxpm-dev libpq-dev pkg-config zlib1g-dev libjpeg-dev
    libpng-dev libfreetype6 libjpeg62-turbo-dev libfreetype6-dev libevent-dev libldap2-dev
    libzip-dev libicu-dev libyaml-dev xsltproc build-essential libcurl4-openssl-dev
    graphviz bison re2c flex libsqlite3-dev
    libonig-dev perl g++ libtool libxslt1-dev libmariadb-dev libmariadb-dev-compat patchelf
)

smart_apt_install "${PACKAGES[@]}"

# non-free 包单独静默安装，防止由于源限制导致批量依赖报错
apt install -y rar unrar > /dev/null 2>&1


apt autoremove -y

# 动态安装 python3-venv 兼容项
P_VER=`python3 -V | awk '{print $2}'`
if version_ge "$P_VER" "3.11.0" ;then
    P_VER_M=`echo "$P_VER" | awk -F. '{print $2}'`
    echo -e "\e[1;31mapt install python3.${P_VER_M}-venv\e[0m"
    apt install -y python3.${P_VER_M}-venv
fi

# 防火墙相关配置
if [ -f /usr/sbin/ufw ];then
	echo 'y' | ufw enable
	if [ "$SSH_PORT" != "" ];then
		ufw allow $SSH_PORT/tcp
	else
		ufw allow 22/tcp
	fi
	ufw allow 80/tcp
	ufw allow 443/tcp
	ufw allow 443/udp
fi

if [ ! -f /usr/sbin/ufw ];then
	apt install -y firewalld
	systemctl enable firewalld
	if [ "$SSH_PORT" != "" ];then
		firewall-cmd --permanent --zone=public --add-port=${SSH_PORT}/tcp
	else
		firewall-cmd --permanent --zone=public --add-port=22/tcp
	fi
	firewall-cmd --permanent --zone=public --add-port=80/tcp
	firewall-cmd --permanent --zone=public --add-port=443/tcp
	firewall-cmd --permanent --zone=public --add-port=443/udp
	systemctl start firewalld
	sed -i 's#IndividualCalls=no#IndividualCalls=yes#g' /etc/firewalld/firewalld.conf
	firewall-cmd --reload
fi

# 创建 curl 头链接
if [ ! -d /usr/include/curl ];then
	SYS_ARCH=`arch`
	if [ -f /usr/include/x86_64-linux-gnu/curl ];then
		ln -s /usr/include/x86_64-linux-gnu/curl /usr/include/curl
	else
		ln -s /usr/include/${SYS_ARCH}-linux-gnu/curl /usr/include/curl
	fi 
fi

# Ubuntu 22.04 特殊处理
VERSION_ID=`cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}' | awk -F "\"" '{print $2}'`
if [ "${VERSION_ID}" == "22.04" ];then
	apt install -y python3-cffi
    pip3 install -U --force-reinstall --no-binary :all: gevent
fi

# find /usr/lib -name "*libaio*" 2>/dev/null
if [ ! -f /usr/lib/libaio.so.1 ];then
	if [ -f /usr/lib/x86_64-linux-gnu/libaio.so.1t64 ];then
		ln -s /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/libaio.so.1
	fi
fi

cd /www/server/yufeng_panel/scripts && bash lib.sh
chmod 755 /www/server/yufeng_panel/data


if [ "${VERSION_ID}" == "22.04" ];then
	apt install -y python3-cffi
    pip3 install -U --force-reinstall --no-binary :all: gevent
fi

