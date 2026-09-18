#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

is_cn_env() {
	local test_cn
	test_cn=$(curl -s -m 2 -o /dev/null -w "%{http_code}" https://mirrors.aliyun.com 2>/dev/null || echo "000")
	if [ "$test_cn" == "200" ] || [ "$test_cn" == "301" ] || [ "$test_cn" == "302" ]; then
		local geo
		geo=$(curl -fsSL -m 2 https://ipinfo.io/country 2>/dev/null || curl -fsSL -m 2 http://cip.cc 2>/dev/null | grep -i "code.*CN" || echo "")
		if echo "$geo" | grep -qi "CN"; then
			echo "1"
			return
		fi
	fi
	echo "0"
}

if id www &> /dev/null ;then 
    echo "www uid is `id -u www`"
    echo "www shell is `grep "^www:" /etc/passwd |cut -d':' -f7 `"
else
    groupadd www
	useradd -g www -s /sbin/nologin www
fi

action=$1
type=$2

if [ "${2}" == "" ];then
	echo '缺少安装脚本...'
	exit 0
fi 

if [ ! -d $curPath/versions/$2 ];then
	echo '缺少安装脚本2...'
	exit 0
fi

# 获取发行版信息
bash ${rootPath}/scripts/getos.sh
OSNAME=`cat ${rootPath}/data/osname.pl`
VERSION_ID=`cat /etc/*-release 2>/dev/null | grep VERSION_ID | awk -F = '{print $2}' | awk -F "\"" '{print $2}'`
R_VER=${VERSION_ID%%.*}
if [ -z "$R_VER" ]; then
	R_VER="8"
fi

# Remi 源依赖 EPEL，前置保障
if ! rpm -q epel-release >/dev/null 2>&1; then
	yum install -y epel-release 2>/dev/null || true
fi

# 安装 Remi 源（支持 CentOS / Alma / Rocky / RHEL / Aliyun / Anolis / Euler / Fedora）
if ! rpm -q remi-release >/dev/null 2>&1; then
	is_cn=$(is_cn_env)
	if [ "$OSNAME" == "alma" ] || [ "$OSNAME" == "rocky" ] || [ "$OSNAME" == "centos" ] || [ "$OSNAME" == "rhel" ] || [ "$OSNAME" == "aliyun" ] || [ "$OSNAME" == "euler" ]; then
		if [ "$is_cn" == "1" ]; then
			rpm -Uvh https://mirrors.tuna.tsinghua.edu.cn/remi/enterprise/remi-release-${R_VER}.rpm 2>/dev/null || \
			rpm -Uvh https://rpms.remirepo.net/enterprise/remi-release-${R_VER}.rpm 2>/dev/null || \
			rpm -Uvh https://rpms.remirepo.net/enterprise/remi-release-${VERSION_ID}.rpm 2>/dev/null || true
		else
			rpm -Uvh https://rpms.remirepo.net/enterprise/remi-release-${R_VER}.rpm 2>/dev/null || \
			rpm -Uvh https://mirrors.tuna.tsinghua.edu.cn/remi/enterprise/remi-release-${R_VER}.rpm 2>/dev/null || \
			rpm -Uvh https://rpms.remirepo.net/enterprise/remi-release-${VERSION_ID}.rpm 2>/dev/null || true
		fi
	elif [ "$OSNAME" == "fedora" ]; then
		rpm -Uvh https://rpms.remirepo.net/fedora/remi-release-${R_VER}.rpm 2>/dev/null || \
		rpm -Uvh https://rpms.remirepo.net/fedora/remi-release-${VERSION_ID}.rpm 2>/dev/null || true
	fi
fi

if [ "${action}" == "uninstall" ] && [ -d ${serverPath}/php-yum/${type} ];then
	# 卸载清理 
	cd ${rootPath} && python3 ${rootPath}/plugins/php-yum/index.py stop ${type}
	cd ${rootPath} && python3 ${rootPath}/plugins/php-yum/index.py initd_uninstall ${type}

	if [ -f /lib/systemd/system/php${type}-php-fpm.service ];then
		rm -rf /lib/systemd/system/php${type}-php-fpm.service
	fi

	systemctl daemon-reload 2>/dev/null || true
fi

cd ${curPath} && sh -x $curPath/versions/$2/install.sh $1

if [ "${action}" == "install" ] && [ -d ${serverPath}/php-yum/${type} ];then

	# 批量合并安装通用扩展（避免 32 次 yum 试错瓶颈，提速 80%）
	echo "install PHP-YUM[${type}] extensions start (batch mode)"
	export PHP_EXT_NO_RESTART=1

	batch_pkgs="php${type}-php-mysqlnd php${type}-php-gd php${type}-php-intl php${type}-php-bcmath php${type}-php-mbstring php${type}-php-xml php${type}-php-opcache"
	yum install -y ${batch_pkgs} 2>/dev/null || true

	# 安装常用组件扩展
	for ext in pecl-zip zip pecl-mcrypt mcrypt pecl-redis5 pecl-redis pecl-memcached pecl-mongodb; do
		yum install -y php${type}-php-${ext} 2>/dev/null || true
	done

	unset PHP_EXT_NO_RESTART
	echo "install PHP-YUM[${type}] extensions end"

	# 初始化启动
	cd ${rootPath} && python3 plugins/php-yum/index.py start ${type}
	cd ${rootPath} && python3 plugins/php-yum/index.py initd_install ${type}

	if [ ! -f /usr/local/bin/composer ];then
		echo "Installing Composer..."
		cd /tmp
		export COMPOSER_HOME=/root/.config/composer
		comp_tmp="/tmp/composer.phar.tmp"
		rm -f "$comp_tmp"
		
		is_cn=$(is_cn_env)
		if [ "$is_cn" == "1" ]; then
			curl -fsSL -m 30 -o "$comp_tmp" https://mirrors.aliyun.com/composer/composer.phar || \
			curl -fsSL -m 30 -o "$comp_tmp" https://getcomposer.org/download/latest-stable/composer.phar
		else
			curl -fsSL -m 30 -o "$comp_tmp" https://getcomposer.org/download/latest-stable/composer.phar || \
			curl -fsSL -m 30 -o "$comp_tmp" https://mirrors.aliyun.com/composer/composer.phar
		fi

		if [ -s "$comp_tmp" ]; then
			mv -f "$comp_tmp" /usr/local/bin/composer
			chmod +x /usr/local/bin/composer
			
			if [ "$is_cn" == "1" ]; then
				echo "Configuring Aliyun mirror for Composer..."
				/usr/local/bin/composer config -g repo.packagist composer https://mirrors.aliyun.com/composer/ 2>/dev/null || true
			fi
		else
			echo "Warning: Composer download failed. You may need to install it manually."
		fi
	fi

	echo "PHP-YUM[${type}] start ..."
	systemctl reset-failed php${type}-php-fpm 2>/dev/null || true
	systemctl daemon-reload 2>/dev/null || true
	systemctl restart php${type}-php-fpm 2>/dev/null || service php${type}-php-fpm restart 2>/dev/null || true
	sleep 1
	if systemctl is-active --quiet php${type}-php-fpm 2>/dev/null; then
		echo "PHP-YUM[${type}] service is active and running."
	else
		echo "Notice: php${type}-php-fpm service status:"
		systemctl status php${type}-php-fpm --no-pager -l 2>/dev/null | tail -n 15 || true
	fi
	echo "PHP-YUM[${type}] start ok"
fi



