#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")


action=$1
version=$2
sys_os=`uname`

if [ -f ${rootPath}/bin/activate ];then
	source ${rootPath}/bin/activate
fi

if [ "$sys_os" == "Darwin" ];then
	BAK='_bak'
else
	BAK=''
fi

Install_App(){
	echo '正在安装脚本文件...'
	mkdir -p $serverPath/op_load_balance
	echo "${version}" > $serverPath/op_load_balance/version.pl
	# start 会写 web_conf/nginx/vhost/load_balance.conf 并 reload openresty：
	# 未装 OpenResty 时它回 'ERROR: 请先安装OpenResty'，不能再报「安装成功」
	out=$(cd ${rootPath} && python3 ${rootPath}/plugins/op_load_balance/index.py start 2>&1)
	if [ "$out" != 'ok' ]; then
		echo "安装OP负载均衡失败: ${out}"
		exit 1
	fi
	echo '安装OP负载均衡成功!'
}

Uninstall_App(){
	cd ${rootPath} && python3 ${rootPath}/plugins/op_load_balance/index.py stop
	# stop 在未装 OpenResty 时会拒绝执行，这里兜底清掉本插件自己写进 vhost 目录的文件
	rm -f $serverPath/web_conf/nginx/vhost/load_balance.conf
	rm -rf $serverPath/op_load_balance
}


action=$1
if [ "${1}" == 'install' ];then
	Install_App
else
	Uninstall_App
fi
