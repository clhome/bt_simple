#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

if id www &> /dev/null ;then 
    echo "www uid is `id -u www`"
    echo "www shell is `grep "^www:" /etc/passwd |cut -d':' -f7 `"
else
    groupadd www
	useradd -g www -s /sbin/nologin www
	# useradd -g www -s /bin/bash www
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

# cd /www/server/yufeng_panel/plugins/php-yum/versions && bash common.sh 83 install opcache

#获取信息和版本
bash ${rootPath}/scripts/getos.sh
OSNAME=`cat ${rootPath}/data/osname.pl`
VERSION_ID=`cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}' | awk -F "\"" '{print $2}'`
R_VER=${VERSION_ID%%.*}

if ! rpm -q remi-release >/dev/null 2>&1; then
	if [ "$OSNAME" == "alma" ] || [ "$OSNAME" == "rocky" ] || [ "$OSNAME" == "centos" ]; then
		rpm -Uvh http://rpms.remirepo.net/enterprise/remi-release-${R_VER}.rpm || rpm -Uvh http://rpms.remirepo.net/enterprise/remi-release-${VERSION_ID}.rpm || true
	elif [ "$OSNAME" == "fedora" ]; then
		rpm -Uvh http://rpms.remirepo.net/fedora/remi-release-${R_VER}.rpm || rpm -Uvh http://rpms.remirepo.net/fedora/remi-release-${VERSION_ID}.rpm || true
	fi
fi



if [ "${action}" == "uninstall" ] && [ -d ${serverPath}/php-yum/${type} ];then
	#初始化 
	cd ${rootPath} && python3 ${rootPath}/plugins/php-yum/index.py stop ${type}
	cd ${rootPath} && python3 ${rootPath}/plugins/php-yum/index.py initd_uninstall ${type}

	if [ -f /lib/systemd/system/php${type}-php-fpm.service ];then
		rm -rf /lib/systemd/system/php${type}-php-fpm.service
	fi

	systemctl daemon-reload
fi

cd ${curPath} && sh -x $curPath/versions/$2/install.sh $1

if [ "${action}" == "install" ] && [ -d ${serverPath}/php-yum/${type} ];then

	# 安装通用扩展
	echo "install PHP-YUM[${type}] extend start"
	export PHP_EXT_NO_RESTART=1
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install mysqlnd
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install mysql
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install gd
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install iconv
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install exif
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install intl
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install mcrypt
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install bcmath
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install openssl
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install gettext
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install redis
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install memcached
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install mbstring
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install mongodb
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install zip
	cd ${rootPath}/plugins/php-yum/versions && bash common.sh ${type} install simplexml
	unset PHP_EXT_NO_RESTART
	echo "install PHP-YUM[${type}] extend end"

	#初始化 
	cd ${rootPath} && python3 plugins/php-yum/index.py start ${type}
	cd ${rootPath} && python3 plugins/php-yum/index.py initd_install ${type}

	if [ ! -f /usr/local/bin/composer ];then
		echo "Installing Composer..."
		cd /tmp
		export COMPOSER_HOME=/root/.config/composer
		
		# 尝试从国内镜像直接下载已打包好的 composer.phar 提高成功率
		curl -sSLo composer.phar https://mirrors.aliyun.com/composer/composer.phar
		if [ ! -f "composer.phar" ] || [ ! -s "composer.phar" ]; then
			# 退避回官方源直接下载
			curl -sSLo composer.phar https://getcomposer.org/download/latest-stable/composer.phar
		fi

		if [ -f "composer.phar" ] && [ -s "composer.phar" ]; then
			mv composer.phar /usr/local/bin/composer
			chmod +x /usr/local/bin/composer
			
			# 智能测速选择 Composer 镜像源
			echo "Testing Composer mirror speeds..."
			aliyun_time=$(curl -m 2 -s -w "%{time_total}" -o /dev/null https://mirrors.aliyun.com/composer/ || echo "999")
			tencent_time=$(curl -m 2 -s -w "%{time_total}" -o /dev/null https://mirrors.cloud.tencent.com/composer/ || echo "999")
			packagist_time=$(curl -m 2 -s -w "%{time_total}" -o /dev/null https://packagist.org/ || echo "999")
			
			fastest=$(awk -v a="$aliyun_time" -v t="$tencent_time" -v p="$packagist_time" 'BEGIN{
				if(a < t && a < p && a < 2) print "aliyun";
				else if(t < a && t < p && t < 2) print "tencent";
				else print "official";
			}')
			
			if [ "$fastest" == "aliyun" ]; then
				echo "Aliyun mirror is the fastest. Setting Aliyun mirror..."
				/usr/local/bin/composer config -g repo.packagist composer https://mirrors.aliyun.com/composer/
			elif [ "$fastest" == "tencent" ]; then
				echo "Tencent mirror is the fastest. Setting Tencent mirror..."
				/usr/local/bin/composer config -g repo.packagist composer https://mirrors.cloud.tencent.com/composer/
			else
				echo "Official mirror is fast enough or domestic mirrors failed. Using default."
			fi
		elif command -v php >/dev/null 2>&1 || [ -f "/opt/remi/php${type}/root/usr/bin/php" ]; then
			php_bin=$(command -v php || echo "/opt/remi/php${type}/root/usr/bin/php")
			curl -sS https://getcomposer.org/installer | $php_bin
			if [ -f "composer.phar" ]; then
				mv composer.phar /usr/local/bin/composer
				chmod +x /usr/local/bin/composer
			fi
		fi
	fi

	echo "PHP-YUM[${type}] start ..."
	systemctl reset-failed php${type}-php-fpm 2>/dev/null || true
	systemctl daemon-reload 2>/dev/null || true
	systemctl restart php${type}-php-fpm 2>/dev/null || service php${type}-php-fpm restart 2>/dev/null || true
	echo "PHP-YUM[${type}] start ok"
fi


