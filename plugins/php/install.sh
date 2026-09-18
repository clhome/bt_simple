#!/bin/bash
if [ -f $(dirname $0)/../../scripts/lib_make_jobs.sh ]; then source $(dirname $0)/../../scripts/lib_make_jobs.sh; elif [ -f /www/server/yufeng_panel/scripts/lib_make_jobs.sh ]; then source /www/server/yufeng_panel/scripts/lib_make_jobs.sh; fi
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")
sysName=`uname`

# cd /www/server/yufeng_panel/plugins/php && bash install.sh install 73
# cd /www/server/yufeng_panel/plugins/php && bash install.sh install 85
# https://www.php.net/releases

if id www &> /dev/null ;then 
    echo "www uid is `id -u www`"
    echo "www shell is `grep "^www:" /etc/passwd |cut -d':' -f7 `"
else
    groupadd www
	useradd -g www -s /sbin/nologin www
	# useradd -g www -s /bin/bash www
fi

action=$1
type=${2//./}

if [ "${type}" == "" ];then
	echo '缺少安装脚本...'
	exit 0
fi 

if [ ! -d $curPath/versions/$type ];then
	echo '缺少安装脚本2...'
	exit 0
fi


# if [ "${action}" == "install" ] && [ -d $serverPath/php/${type} ];then
# 	exit 0
# fi

if [ "${action}" == "uninstall" ];then
	
	if [ -f /usr/lib/systemd/system/php${type}.service ] || [ -f /lib/systemd/system/php${type}.service ] ;then
		systemctl stop php${type}
		systemctl disable php${type}
		rm -rf /usr/lib/systemd/system/php${type}.service
		rm -rf /lib/systemd/system/php${type}.service
		systemctl daemon-reload
	fi
fi

cd ${curPath} && sh -x $curPath/versions/$type/install.sh $1


if [ "${action}" == "install" ] && [ -d ${serverPath}/php/${type} ];then

	#初始化 
	cd ${rootPath} && python3 ${rootPath}/plugins/php/index.py start ${type}
	cd ${rootPath} && python3 ${rootPath}/plugins/php/index.py initd_install ${type}

	# 安装通用扩展
	# 导出 cpuCore 供扩展脚本使用多核编译
	_env_lib=${rootPath}/plugins/php/lib/common_env.sh
	if [ -f "$_env_lib" ]; then source "$_env_lib"; fi
	export cpuCore
	echo "install PHP${type} extend start (cpuCore=${cpuCore})"
# --- yf adaptive clamp (1C512M -> -j1) ---
if command -v yf_make_jobs >/dev/null 2>&1; then _yf_jobs=$(yf_make_jobs 2>/dev/null || echo ""); if [ -n "$_yf_jobs" ] && [ "$_yf_jobs" -ge 1 ] 2>/dev/null; then cpuCore="$_yf_jobs"; fi; fi

	export PHP_EXT_NO_RESTART=1

	cd ${rootPath}/plugins/php/versions/common && bash curl.sh install ${type}
	cd ${rootPath}/plugins/php/versions/common && bash gd.sh install ${type}
	cd ${rootPath}/plugins/php/versions/common && bash readline.sh install ${type}
	cd ${rootPath}/plugins/php/versions/common && bash iconv.sh install ${type}
	cd ${rootPath}/plugins/php/versions/common && bash exif.sh install ${type}
	cd ${rootPath}/plugins/php/versions/common && bash intl.sh install ${type}
	cd ${rootPath}/plugins/php/versions/common && bash mcrypt.sh install ${type}
	cd ${rootPath}/plugins/php/versions/common && bash openssl.sh install ${type}
	cd ${rootPath}/plugins/php/versions/common && bash bcmath.sh install ${type}
	cd ${rootPath}/plugins/php/versions/common && bash gettext.sh install ${type}
	cd ${rootPath}/plugins/php/versions/common && bash redis.sh install ${type}
	cd ${rootPath}/plugins/php/versions/common && bash memcached.sh install ${type}
	cd ${rootPath}/plugins/php/versions/common && bash pcntl.sh install ${type}
	cd ${rootPath}/plugins/php/versions/common && bash zip.sh install ${type}
	cd ${rootPath}/plugins/php/versions/common && bash zlib.sh install ${type}

	unset PHP_EXT_NO_RESTART
	echo "install PHP${type} extend end"

	# 统筹清理中间编译临时解压源码，释放磁盘空间
	rm -rf ${serverPath}/source/php/php${type} 2>/dev/null || true
	rm -rf ${serverPath}/source/php${type} 2>/dev/null || true

	# 统一执行一次最终重启并探活
	systemctl reset-failed php${type} 2>/dev/null || true
	systemctl daemon-reload 2>/dev/null || true
	systemctl restart php${type} 2>/dev/null || service php${type} restart 2>/dev/null || bash ${rootPath}/plugins/php/versions/lib.sh ${type} restart 2>/dev/null || true
	sleep 1
	if systemctl is-active --quiet php${type} 2>/dev/null; then
		echo "PHP${type} service is active and running."
	else
		echo "Notice: PHP${type} service status:"
		systemctl status php${type} --no-pager -l 2>/dev/null | tail -n 15 || true
	fi

	if [ ! -f /usr/local/bin/composer ] && [ "$sysName" != "Darwin" ] ;then
		echo "Installing Composer..."
		cd /tmp
		export COMPOSER_HOME=/root/.config/composer
		export PATH=${serverPath}/php/${type}/bin:$PATH
		comp_tmp="/tmp/composer.phar.tmp"
		rm -f "$comp_tmp"
		
		is_cn=$(curl -s -m 2 -o /dev/null -w "%{http_code}" https://mirrors.aliyun.com 2>/dev/null || echo "000")
		if [ "$is_cn" == "200" ] || [ "$is_cn" == "301" ] || [ "$is_cn" == "302" ]; then
			curl -fsSL -m 30 -o "$comp_tmp" https://mirrors.aliyun.com/composer/composer.phar || \
			curl -fsSL -m 30 -o "$comp_tmp" https://getcomposer.org/download/latest-stable/composer.phar
		else
			curl -fsSL -m 30 -o "$comp_tmp" https://getcomposer.org/download/latest-stable/composer.phar || \
			curl -fsSL -m 30 -o "$comp_tmp" https://mirrors.aliyun.com/composer/composer.phar
		fi

		if [ -s "$comp_tmp" ]; then
			mv -f "$comp_tmp" /usr/local/bin/composer
			chmod +x /usr/local/bin/composer
			
			if [ "$is_cn" == "200" ] || [ "$is_cn" == "301" ] || [ "$is_cn" == "302" ]; then
				echo "Configuring Aliyun mirror for Composer..."
				/usr/local/bin/composer config -g repo.packagist composer https://mirrors.aliyun.com/composer/ 2>/dev/null || true
			fi
		else
			echo "Warning: Composer download failed. You may need to install it manually."
		fi
	fi
fi


