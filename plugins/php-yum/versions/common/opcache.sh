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

cfgDir=/etc/opt/remi

OP_BL=${serverPath}/php-yum/opcache-blacklist.txt
if [ ! -f $OP_BL ];then
	touch $OP_BL
fi
ext_dir=${cfgDir}/php${version}/php.d
ext_file=${ext_dir}/10-opcache.ini

echo $ext_file

if [ "$actionType" == 'install' ];then
	yum install -y php${version}-php-${LIBNAME}
	echo "ls ${cfgDir}/php${version}/php.d | grep "${LIBNAME}.ini"| cut -d \  -f 1"
	find_opcache=`ls ${cfgDir}/php${version}/php.d | grep "${LIBNAME}.ini"| cut -d \  -f 1`
	echo $find_opcache
	if [ "$find_opcache" != "" ];then
		ext_file=${ext_dir}/${find_opcache}
	fi
	# 1. 确保 php.ini 中不包含重复的 zend_extension=opcache，统一由 php.d 模块化管理
	sed -i '/zend_extension.*opcache/d' /etc/opt/remi/php${version}/php.ini 2>/dev/null || true

	# 2. 清理 php.d 下任何多余的孤儿或重复 ini 文件（确保只保留 10-opcache.ini）
	for dup_f in ${ext_dir}/*${LIBNAME}*.ini; do
		if [ -f "$dup_f" ] && [ "$dup_f" != "$ext_file" ]; then
			rm -f "$dup_f" 2>/dev/null || true
		fi
	done

	# 3. 规范化 ext_file 中的 zend_extension：清理重复行，确保全局仅有 1 处加载
	real_target=$(readlink -f "$ext_file" 2>/dev/null || echo "$ext_file")
	if [ -f "$real_target" ]; then
		sed -i '/zend_extension.*opcache/d' "$real_target" 2>/dev/null || true
		sed -i "1i zend_extension=${LIBNAME}" "$real_target" 2>/dev/null || echo "zend_extension=${LIBNAME}" > "$real_target"
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

		# JIT 配置：PHP 80+ 支持 JIT，PHP 84+ 需要字符串语法
		if [ "$version" -ge "80" ] 2>/dev/null; then
			if [ "$version" -ge "84" ] 2>/dev/null; then
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
	if [ -f ${ext_dir}/10-opcache.ini.rpmsave ];then
		ext_file=${ext_dir}/10-opcache.ini.rpmsave
	fi

	# yum remove -y php83-php-opcache
	yum remove -y php${version}-php-${LIBNAME}
	rm -rf $ext_file
	echo 'cannot uninstall'
fi