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
	# 依赖前置提示（《问题报告》次要-2）：本插件本身行为已经是诚实的（index.py
	# start 回 'ERROR: 请先安装OpenResty' 时这里 exit 1），但那是**建完目录、写完
	# version.pl 之后**才知道的。依赖提前判一次，用户在点安装的当下就能看到原因，
	# 也不会在未装 OpenResty 的机器上留下半个插件目录。
	if [ ! -d "$serverPath/openresty" ]; then
		echo "安装前置检查未通过：OP负载均衡依赖 OpenResty，请先安装 OpenResty（面板-软件商店-OpenResty）后再回来装本插件" >&2
		exit 1
	fi

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
