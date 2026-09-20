#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")
sourcePath=${serverPath}/source/php

actionType=$1
version=$2

sysName=`uname`
LIBNAME=opcache

ext_dir=/etc/php/${version}/fpm/conf.d
ext_file=${ext_dir}/10-opcache.ini

echo $ext_file

OP_BL=${serverPath}/php-apt/opcache-blacklist.txt
if [ ! -f $OP_BL ];then
	touch $OP_BL
fi

if [ "$actionType" == 'install' ];then
	apt install -y php${version}-${LIBNAME}

	echo "ls ${ext_dir} | grep "${LIBNAME}.ini"| cut -d \  -f 1"
	find_opcache=`ls ${ext_dir} | grep "${LIBNAME}.ini"| cut -d \  -f 1`
	echo $find_opcache
	if [ "$find_opcache" != "" ];then
		ext_file=${ext_dir}/${find_opcache}
	fi
	# 1. 确保 php.ini 中不包含重复的 zend_extension=opcache，统一由 conf.d 模块化管理
	sed -i '/zend_extension.*opcache/d' /etc/php/${version}/fpm/php.ini 2>/dev/null || true

	# 2. 清理 conf.d 下任何多余的孤儿或重复 ini 文件（确保只保留 10-opcache.ini）
	for dup_f in ${ext_dir}/*${LIBNAME}*.ini; do
		if [ -f "$dup_f" ] && [ "$dup_f" != "$ext_file" ]; then
			rm -f "$dup_f" 2>/dev/null || true
		fi
	done

	# 3. 规范化 ext_file 中的 zend_extension：清理重复行，确保全局仅有 1 处加载
	real_target=$(readlink -f "$ext_file" 2>/dev/null || echo "$ext_file")
	if [ -f "$real_target" ]; then
		sed -i '/zend_extension.*opcache/d' "$real_target" 2>/dev/null || true
		if [ "$version" != "8.5" ]; then
			sed -i "1i zend_extension=${LIBNAME}.so" "$real_target" 2>/dev/null || echo "zend_extension=${LIBNAME}.so" > "$real_target"
		fi
	fi

	if grep -q "opcache\.enable" "$ext_file" 2>/dev/null; then
		echo "opcache already configured in $ext_file, skipping duplicate config."
	else
		echo "opcache.enable=1" >> $ext_file
		echo "opcache.memory_consumption=128" >> $ext_file
		echo "opcache.interned_strings_buffer=8" >> $ext_file
		echo "opcache.max_accelerated_files=4000" >> $ext_file
		echo "opcache.revalidate_freq=60" >> $ext_file
		echo "opcache.fast_shutdown=1" >> $ext_file
		echo "opcache.enable_cli=1" >> $ext_file

		# JIT 配置：PHP 8.0+ 支持 JIT，PHP 8.4+ 需要字符串语法
		ver_major_minor=$(echo "$version" | tr -d '.')
		if [ "$ver_major_minor" -ge "80" ] 2>/dev/null; then
			if [ "$ver_major_minor" -ge "84" ] 2>/dev/null; then
				echo "opcache.jit=tracing" >> $ext_file
			else
				echo "opcache.jit=1205" >> $ext_file
			fi
			echo "opcache.jit_buffer_size=64M" >> $ext_file
		fi

		echo "opcache.save_comments=0" >> $ext_file
		echo "opcache.blacklist_filename=${OP_BL}" >> $ext_file
	fi

elif [ "$actionType" == 'uninstall' ];then
	rm -rf $ext_file
	echo 'cannot uninstall'
fi