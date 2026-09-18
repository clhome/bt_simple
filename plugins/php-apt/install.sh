#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
export DEBIAN_FRONTEND=noninteractive

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

wait_dpkg_lock() {
	local timeout=30
	while fuser /var/lib/dpkg/lock >/dev/null 2>&1 || fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
		echo "Waiting for other apt/dpkg processes to complete (${timeout}s remaining)..."
		sleep 2
		timeout=$((timeout - 2))
		if [ "$timeout" -le 0 ]; then
			break
		fi
	done
}

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

_os=`uname`
if [ ${_os} == "Darwin" ]; then
    OSNAME='macos'
elif grep -Eqi "Debian" /etc/issue || grep -Eq "Debian" /etc/*-release; then
    OSNAME='debian'
elif grep -Eqi "Ubuntu" /etc/issue || grep -Eq "Ubuntu" /etc/*-release; then
    OSNAME='ubuntu'
else
    OSNAME='unknow'
fi

action=$1
type=$2
apt_ver=${type:0:1}.${type:1:2}

if [ "${2}" == "" ];then
	echo '缺少安装脚本...'
	exit 0
fi 

if [ ! -d $curPath/versions/$2 ];then
	echo '缺少安装脚本2...'
	exit 0
fi 

if [ "$OSNAME" == "ubuntu" ];then
	find_source=`ls /etc/apt/sources.list.d 2>/dev/null | grep ondrej-ubuntu-php`
	if [ "$find_source" == "" ];then
		wait_dpkg_lock
		echo "y" | LC_ALL=C.UTF-8 add-apt-repository ppa:ondrej/php && wait_dpkg_lock && apt-get update -y
	fi
fi

if [ "$OSNAME" == "debian" ];then
	wait_dpkg_lock
	apt-get install -y apt-transport-https lsb-release ca-certificates curl
	is_cn=$(is_cn_env)
	gpg_key="/usr/share/keyrings/deb.sury.org-php.gpg"
	mkdir -p /usr/share/keyrings

	gpg_tmp="/tmp/deb.sury.org-php.gpg.tmp"
	rm -f "$gpg_tmp"
	if [ "$is_cn" == "1" ]; then
		curl -fsSL -m 15 -o "$gpg_tmp" https://mirror.sjtu.edu.cn/sury/php/apt.gpg || \
		curl -fsSL -m 15 -o "$gpg_tmp" https://packages.sury.org/php/apt.gpg
	else
		curl -fsSL -m 15 -o "$gpg_tmp" https://packages.sury.org/php/apt.gpg || \
		curl -fsSL -m 15 -o "$gpg_tmp" https://mirror.sjtu.edu.cn/sury/php/apt.gpg
	fi

	if [ -s "$gpg_tmp" ]; then
		mv -f "$gpg_tmp" "$gpg_key"
		chmod 644 "$gpg_key"
	fi

	if [ ! -f /etc/apt/sources.list.d/php.list ]; then
		codename=$(lsb_release -sc 2>/dev/null || echo "bookworm")
		if [ "$is_cn" == "1" ]; then
			echo "deb [signed-by=${gpg_key}] https://mirror.sjtu.edu.cn/sury/php/ ${codename} main" > /etc/apt/sources.list.d/php.list
			wait_dpkg_lock
			if ! apt-get update -y; then
				echo "Domestic mirror update failed, falling back to official packages.sury.org..."
				echo "deb [signed-by=${gpg_key}] https://packages.sury.org/php/ ${codename} main" > /etc/apt/sources.list.d/php.list
				wait_dpkg_lock
				apt-get update -y
			fi
		else
			echo "deb [signed-by=${gpg_key}] https://packages.sury.org/php/ ${codename} main" > /etc/apt/sources.list.d/php.list
			wait_dpkg_lock
			if ! apt-get update -y; then
				echo "Official source update failed, falling back to mirror..."
				echo "deb [signed-by=${gpg_key}] https://mirror.sjtu.edu.cn/sury/php/ ${codename} main" > /etc/apt/sources.list.d/php.list
				wait_dpkg_lock
				apt-get update -y
			fi
		fi
	fi
fi 

if [ "${action}" == "uninstall" ] && [ -d ${serverPath}/php-apt/${type} ];then
	# 卸载清理
	cd ${rootPath} && python3 ${rootPath}/plugins/php-apt/index.py stop ${type}
	cd ${rootPath} && python3 ${rootPath}/plugins/php-apt/index.py initd_uninstall ${type}

	if [ -f /lib/systemd/system/php${apt_ver}-fpm.service ];then
		rm -rf /lib/systemd/system/php${apt_ver}-fpm.service
	fi

	if [ -f /lib/systemd/system/system/php${apt_ver}-fpm.service ];then
		rm -rf /lib/systemd/system/php${apt_ver}-fpm.service
	fi

	systemctl daemon-reload 2>/dev/null || true
fi

if [ "${action}" == "install" ]; then
	wait_dpkg_lock
	apt-get update -y
fi

cd ${curPath} && sh -x $curPath/versions/$2/install.sh $1

if [ "${action}" == "install" ] && [ -d ${serverPath}/php-apt/${type} ];then
	
	# 初始化启动与自愈
	cd ${rootPath} && python3 ${rootPath}/plugins/php-apt/index.py start ${type}
	cd ${rootPath} && python3 ${rootPath}/plugins/php-apt/index.py restart ${type}
	cd ${rootPath} && python3 ${rootPath}/plugins/php-apt/index.py initd_install ${type}

	# 批量安装通用扩展（合并单条 apt-get，大幅提升 5~8 倍速度）
	echo "install PHP-APT[${type}] extensions start (batch mode)"
	export PHP_EXT_NO_RESTART=1

	batch_pkgs="php${apt_ver}-curl php${apt_ver}-gd php${apt_ver}-intl php${apt_ver}-xml php${apt_ver}-bcmath php${apt_ver}-mysql php${apt_ver}-mbstring php${apt_ver}-zip"
	wait_dpkg_lock
	apt-get install -y ${batch_pkgs} 2>/dev/null || true

	# 流行组件扩展按需安装
	for ext in redis memcached opcache; do
		if [ -f "${rootPath}/plugins/php-apt/versions/common/${ext}.sh" ]; then
			cd ${rootPath}/plugins/php-apt/versions && bash common.sh ${apt_ver} install ${ext}
		else
			wait_dpkg_lock
			apt-get install -y php${apt_ver}-${ext} 2>/dev/null || true
		fi
	done

	unset PHP_EXT_NO_RESTART
	echo "install PHP-APT[${type}] extensions end"

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

	systemctl reset-failed php${apt_ver}-fpm 2>/dev/null || true
	systemctl daemon-reload 2>/dev/null || true
	systemctl restart php${apt_ver}-fpm 2>/dev/null || service php${apt_ver}-fpm restart 2>/dev/null || true
	sleep 1
	if systemctl is-active --quiet php${apt_ver}-fpm 2>/dev/null; then
		echo "PHP-APT[${type}] service is active and running."
	else
		echo "Notice: php${apt_ver}-fpm service status:"
		systemctl status php${apt_ver}-fpm --no-pager -l 2>/dev/null | tail -n 15 || true
	fi
fi



