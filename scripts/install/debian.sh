#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH
export LANG=en_US.UTF-8
export DEBIAN_FRONTEND=noninteractive

function version_gt() { test "$(echo "$@" | tr " " "\n" | sort -V | head -n 1)" != "$1"; }
function version_le() { test "$(echo "$@" | tr " " "\n" | sort -V | head -n 1)" == "$1"; }
function version_lt() { test "$(echo "$@" | tr " " "\n" | sort -rV | head -n 1)" != "$1"; }
function version_ge() { test "$(echo "$@" | tr " " "\n" | sort -rV | head -n 1)" == "$1"; }

VERSION_ID=`cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}' | awk -F "\"" '{print $2}'`

cn=$(curl -fsSL -m 10 http://ipinfo.io/json | grep "\"country\": \"CN\"")

ln -sf /bin/bash /bin/sh

# 前置刷新软件包缓存，防范 404 错误
apt update -y -o Acquire::Languages=none

# 智能批量/分级安装函数
function smart_apt_install() {
    local pkgs=("$@")
    # --no-install-recommends: 跳过非必需的推荐包，大幅减少安装包数量（约减少 60%）
    # --force-unsafe-io: 跳过 dpkg 的 fsync 磁盘同步，加速解压（全新安装环境可安全使用）
    local APT_OPTS="--no-install-recommends -o Dpkg::Options::=--force-unsafe-io"
    echo "正在尝试一次性批量安装系统依赖包..."
    if apt install -y $APT_OPTS "${pkgs[@]}"; then
        return 0
    fi

    echo "警告：批量安装失败，可能因为某些软件包在当前源中不存在。正在尝试逐个检查并安装..."
    for pkg in "${pkgs[@]}"; do
        if ! apt install -y $APT_OPTS "$pkg"; then
            echo "警告: 软件包 $pkg 安装失败，跳过。"
        fi
    done
}

# 32位及Debian 10单独处理rustc
__GET_BIT=`getconf LONG_BIT`
if [ "$__GET_BIT" == "32" ]; then
    apt install -y rustc
fi
if [ "$VERSION_ID" == "10" ]; then
    apt install -y rustc
fi



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
    chrony ntpdate net-tools locales wget curl lsof unzip tar cron expect
    lrzsz xz-utils pv bc python3-pip python3-dev python3-venv
    libncurses5 libncurses5-dev bzip2 p7zip-full libnuma1 libaio1 libaio-dev
    libmecab2 libmm-dev dnsutils apache2-utils numactl xxd sshpass libbrotli-dev
    libvpx-dev libxpm-dev libwebp-dev libfreetype6 libfreetype6-dev libjpeg-dev libpng-dev
    build-essential devscripts autoconf gcc patchelf libffi-dev cmake automake make webp scons
    liblzma-dev libpcre3 libpcre3-dev openssl libssl-dev libargon2-dev
    libmemcached-dev libsasl2-dev imagemagick libmagickcore-dev libmagickwand-dev
    libxml2 libxml2-dev libbz2-dev libmcrypt-dev libpspell-dev
    libgmp-dev libreadline-dev libpq-dev pkg-config libevent-dev
    libldap2-dev libzip-dev libicu-dev libyaml-dev xsltproc libcurl4-openssl-dev
    libprotobuf-dev protobuf-compiler libboost-dev liblz4-tool
    zstd libzstd-dev graphviz bison re2c flex libsqlite3-dev libonig-dev perl g++
    libtool libxslt1-dev libmariadb-dev libmariadb-dev-compat
)

if [ "$VERSION_ID" != "9" ]; then
    PACKAGES+=(libjpeg62-turbo-dev)
fi

smart_apt_install "${PACKAGES[@]}"

# non-free 及旧版专属包单独静默安装，防止源限制或包废弃导致批量安装失败
apt install -y rar unrar > /dev/null 2>&1
apt install -y librecode-dev > /dev/null 2>&1

apt autoremove -y

# SSH 端口检测（置于 net-tools 安装之后，确保 netstat 可用）
SSH_PORT=`netstat -ntpl|grep sshd|grep -v grep | sed -n "1,1p" | awk '{print $4}' | awk -F : '{print $2}'`
if [ "$SSH_PORT" == "" ];then
	SSH_PORT_LINE=`cat /etc/ssh/sshd_config | grep "Port \d*" | tail -1`
	SSH_PORT=${SSH_PORT_LINE/"Port "/""}
fi
echo "SSH PORT:${SSH_PORT}"

# 动态安装 python3-venv 兼容项
P_VER=`python3 -V | awk '{print $2}'`
if version_ge "$P_VER" "3.11.0" ;then
    P_VER_M=`echo "$P_VER" | awk -F. '{print $2}'`
    echo -e "\e[1;31mapt install python3.${P_VER_M}-venv\e[0m"
    apt install -y python3.${P_VER_M}-venv
fi

# 防火墙相关配置
if [ -f /usr/sbin/ufw ];then
	ufw enable
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
    systemctl unmask firewalld
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

# 修复 zlib1g-dev 特殊安装失败的逻辑
echo -e "\e[0;32mfix zlib1g-dev install question start\e[0m"
Install_TmpFile=/tmp/debian-fix-zlib1g-dev.txt
apt install -y zlib1g-dev > ${Install_TmpFile}
if [ "$?" != "0" ];then
	ZLIB1G_BASE_VER=$(cat ${Install_TmpFile} | grep zlib1g | awk -F "=" '{print $2}' | awk -F ")" '{print $1}')
	ZLIB1G_BASE_VER=`echo ${ZLIB1G_BASE_VER} | sed "s/^[ \s]\{1,\}//g;s/[ \s]\{1,\}$//g"`
	echo -e "\e[1;31mapt install zlib1g=${ZLIB1G_BASE_VER} zlib1g-dev\e[0m"
	echo "Y" | apt install zlib1g=${ZLIB1G_BASE_VER}  zlib1g-dev
fi
rm -rf ${Install_TmpFile}
echo -e "\e[0;32mfix zlib1g-dev install question end\e[0m"

# 修复 libunwind-dev 特殊安装失败的逻辑
echo -e "\e[0;32mfix libunwind-dev install question start\e[0m"
Install_TmpFile=/tmp/debian-fix-libunwind-dev.txt
apt install -y libunwind-dev > ${Install_TmpFile}
if [ "$?" != "0" ];then
	liblzma5_BASE_VER=$(cat ${Install_TmpFile} | grep liblzma-dev | awk -F "=" '{print $2}' | awk -F ")" '{print $1}')
	liblzma5_BASE_VER=`echo ${liblzma5_BASE_VER} | sed "s/^[ \s]\{1,\}//g;s/[ \s]\{1,\}$//g"`
	echo -e "\e[1;31mapt install liblzma5=${liblzma5_BASE_VER} libunwind-dev\e[0m"
	echo "Y" | apt install liblzma5=${liblzma5_BASE_VER} libunwind-dev
fi
rm -rf ${Install_TmpFile}
echo -e "\e[0;32mfix libunwind-dev install question end\e[0m"

# 重新生成 locale
localedef -i en_US -f UTF-8 en_US.UTF-8

# Debian 9 特殊 requirements 降级
if [ "$VERSION_ID" == "9" ];then
	sed "s/flask==2.0.3/flask==1.1.1/g" -i /www/server/yufeng_panel/requirements.txt
	sed "s/cryptography==3.3.2/cryptography==2.5/g" -i /www/server/yufeng_panel/requirements.txt
	sed "s/configparser==5.2.0/configparser==4.0.2/g" -i /www/server/yufeng_panel/requirements.txt
	sed "s/flask-socketio==5.2.0/flask-socketio==4.2.0/g" -i /www/server/yufeng_panel/requirements.txt
	sed "s/python-engineio==4.3.2/python-engineio==3.9.0/g" -i /www/server/yufeng_panel/requirements.txt
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

# find /usr/lib -name "*libaio*" 2>/dev/null
if [ ! -f /usr/lib/libaio.so.1 ];then
	if [ -f /usr/lib/x86_64-linux-gnu/libaio.so.1t64 ];then
		ln -s /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/libaio.so.1
	fi
fi

cd /www/server/yufeng_panel/scripts && bash lib.sh
chmod 755 /www/server/yufeng_panel/data