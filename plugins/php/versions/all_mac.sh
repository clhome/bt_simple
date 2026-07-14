#! /bin/sh
export PATH=$PATH:/opt/local/bin:/opt/local/sbin:/opt/local/share/man:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/X11/bin:/opt/homebrew/bin
DIR=$(cd "$(dirname "$0")"; pwd)
ROOT_DIR=$(cd "$(dirname "$0")"; pwd)
pluginPath=$(cd "$DIR/.."; pwd)
rootPath=$(cd "$DIR/../../.."; pwd)
serverPath=$(dirname "$rootPath")

PHP_VER_LIST=(54 55 56 70 71 72 73 74 80 81 82 83 84 85)
# PHP_VER_LIST=(81)
for PHP_VER in ${PHP_VER_LIST[@]}; do
	echo "php${PHP_VER} -- start"
	if [ ! -d  ${serverPath}/php/${PHP_VER} ];then
		cd ${pluginPath} && bash install.sh install ${PHP_VER}
	fi
	echo "php${PHP_VER} -- end"
done

cd $DIR
PHP_VER_LIST=(54 55 56 70 71 72 73 74 80 81 82 83 84 85)
# yar
PHP_EXT_LIST=(ZendGuardLoader pdo mysqlnd sqlite3 openssl opcache mcrypt fileinfo \
	exif gd intl pcntl memcache memcached redis imagemagick xdebug \
	swoole yac apc mongo mongodb solr seaslog mbstring iconv)

for PHP_VER in ${PHP_VER_LIST[@]}; do
	echo "php${PHP_VER} -- start"

	if [ ! -d ${serverPath}/php/${PHP_VER} ];then
		echo "php${PHP_VER} is not installed!"
		continue
	fi

	NON_ZTS_FILENAME=`ls ${serverPath}/php/${PHP_VER}/lib/php/extensions | grep no-debug-non-zts`
	for EXT in ${PHP_EXT_LIST[@]}; do
		extFile=${serverPath}/php/${PHP_VER}/lib/php/extensions/${NON_ZTS_FILENAME}/${EXT}.so
		echo "${PHP_VER} ${EXT} start"
		if [ ! -f $extFile ];then
			bash common.sh  $PHP_VER  install ${EXT}
		fi
		echo "${PHP_VER} ${EXT} end"
	done
	
	echo "php${PHP_VER} -- end"
done

