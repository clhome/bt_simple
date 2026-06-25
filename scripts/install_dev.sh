#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

RED='\033[31m'
GREEN='\033[32m'
YELLOW='\033[33m'
BLUE='\033[34m'
PLAIN='\033[0m'
BOLD='\033[1m'
SUCCESS='[\033[32mOK\033[0m]'
COMPLETE='[\033[32mDONE\033[0m]'
WARN='[\033[33mWARN\033[0m]'
ERROR='[\033[31mERROR\033[0m]'
WORKING='[\033[34m*\033[0m]'

# LANG=en_US.UTF-8
is64bit=`getconf LONG_BIT`


if [ -f /www/server/mdserver-web/tools.py ];then
	echo -e "存在旧版代码,不能安装!,已知风险的情况下" 
	echo -e "rm -rf /www/server/mdserver-web"
	echo -e "可安装!" 
	exit 0
fi

echo -e "您正在安装的是\033[31mbt_simple测试版\033[0m，非开发测试用途请使用正式版 install.sh ！" 
echo -e "You are installing\033[31m bt_simple dev version\033[0m, normally use install.sh for production.\n" 
sleep 1

LOG_FILE=/var/log/mw-install.log

{

HTTP_PREFIX="https://"
LOCAL_ADDR=common
cn=$(curl -fsSL -m 10 -s http://ipinfo.io/json | grep "\"country\": \"CN\"")
if [ ! -z "$cn" ] || [ "$?" == "0" ] ;then
	LOCAL_ADDR=cn
fi

if [ "$LOCAL_ADDR" != "common" ];then
	declare -A PROXY_URL
    PROXY_URL["github_do"]="https://github.do/"
    PROXY_URL["gh_llkk_cc"]="https://gh.llkk.cc/https://"
    PROXY_URL["gh_felicity_ac_cn"]="https://gh.felicity.ac.cn/https://"
    PROXY_URL["ghfast_top"]="https://ghfast.top/"
    PROXY_URL["ghproxy_net"]="https://gh-proxy.org/"
    PROXY_URL["gh_927223_xyz"]="https://gh.927223.xyz/https://"
    PROXY_URL["gh_proxy_net"]="https://gh-proxy.net/"
    
    PROXY_URL["source"]="https://"


	SOURCE_LIST_KEY_SORT_TMP=$(echo ${!PROXY_URL[@]} | tr ' ' '\n' | sort -n)
	SOURCE_LIST_KEY=(${SOURCE_LIST_KEY_SORT_TMP//'\n'/})
	SOURCE_LIST_LEN=${#PROXY_URL[*]}
fi


function AutoSizeStr(){
	NAME_STR=$1
	NAME_NUM=$2

	NAME_STR_LEN=`echo "$NAME_STR" | wc -L`
	NAME_NUM_LEN=`echo "$NAME_NUM" | wc -L`

	fix_len=35
	remaining_len=`expr $fix_len - $NAME_STR_LEN - $NAME_NUM_LEN`
	FIX_SPACE=' '
	for ((ass_i=1;ass_i<=$remaining_len;ass_i++))
	do 
		FIX_SPACE="$FIX_SPACE "
	done
	echo -e " ❖   ${1}${FIX_SPACE}${2})"
}

function AutoChooseProxyURL(){
	echo -e "-----------------------------------------------------"
	echo -e "正在为您自动挑选最快的 GitHub 代理节点..."
	echo -e "-----------------------------------------------------"
	
	local TEST_URL="https://raw.githubusercontent.com/clhome/bt_simple/master/README.md"
	local BEST_TIME=999
	local BEST_PREFIX="https://"
	local BEST_NAME="Direct"

	# 预设稳定测试列表
	declare -A TEST_LIST
	TEST_LIST["gh-proxy.org"]="https://gh-proxy.org/"
	TEST_LIST["ghfast.top"]="https://ghfast.top/"
	TEST_LIST["ghp.ci"]="https://ghp.ci/https://"
	TEST_LIST["github.do"]="https://github.do/"
	TEST_LIST["gh-proxy.net"]="https://gh-proxy.net/"

	for name in "${!TEST_LIST[@]}"; do
		local prefix=${TEST_LIST[$name]}
		local full_url="${prefix}${TEST_URL}"
		
		# 使用 curl 测试连接速度，超时 3 秒
		local time_taken=$(curl -s -m 3 -o /dev/null -w "%{time_total}" "$full_url")
		local exit_code=$?

		if [ $exit_code -eq 0 ] && [ "$(echo "$time_taken > 0" | bc -l 2>/dev/null)" -eq 1 ]; then
			echo -e " ❖ 节点 [${name}]: ${time_taken}s"
			# 比较耗时
			if [ "$(echo "$time_taken < $BEST_TIME" | bc -l 2>/dev/null)" -eq 1 ]; then
				BEST_TIME=$time_taken
				BEST_PREFIX=$prefix
				BEST_NAME=$name
			fi
		else
			echo -e " ❖ 节点 [${name}]: \033[31m连接失败\033[0m"
		fi
	done

	if [ "$BEST_NAME" != "Direct" ]; then
		HTTP_PREFIX=$BEST_PREFIX
		echo -e "-----------------------------------------------------"
		echo -e "已自动为您选择最快节点: \033[32m$BEST_NAME\033[0m (耗时: ${BEST_TIME}s)"
		echo -e "-----------------------------------------------------"
	else
		echo -e "-----------------------------------------------------"
		echo -e "\033[31m未发现快速代理节点，将尝试直连或使用默认值。\033[0m"
		HTTP_PREFIX="https://"
		echo -e "-----------------------------------------------------"
	fi
}

function ChooseProxyURL(){
	clear
    echo -e '+---------------------------------------------------+'
    echo -e '|                                                   |'
    echo -e '|   =============================================   |'
    echo -e '|                                                   |'
    echo -e '|     欢迎使用 Linux 一键安装御风面板源码   |'
    echo -e '|                                                   |'
    echo -e '|   =============================================   |'
    echo -e '|                                                   |'
    echo -e '+---------------------------------------------------+'
    echo -e ''
    echo -e '#####################################################'
    echo -e ''
    echo -e '            提供以下国内代理地址可供选择:                  '
    echo -e ''
    echo -e '#####################################################'
    echo -e ''
    cm_i=0
    for V in ${SOURCE_LIST_KEY[@]}; do
    num=`expr $cm_i + 1`
	AutoSizeStr "${V}" "$num"
	cm_i=`expr $cm_i + 1`
	done
    echo -e ''
    echo -e '#####################################################'
    echo -e ''
    echo -e "        系统时间  ${BLUE}$(date "+%Y-%m-%d %H:%M:%S")${PLAIN}"
    echo -e ''
    echo -e '#####################################################'
    CHOICE_A=$(echo -e "\n${BOLD}└─ 请输入你想使用的代理地址 (直接回车将自动测速选择) [ 1-${SOURCE_LIST_LEN} ]：${PLAIN}")

    read -p "${CHOICE_A}" INPUT
    # echo $INPUT
    if [ "$INPUT" == "" ];then
        AutoChooseProxyURL
        return
    fi

    if [ "$INPUT" -lt "0" ];then
		INPUT=1
		TMP_INPUT=`expr $INPUT - 1`
		INPUT_KEY=${SOURCE_LIST_KEY[$TMP_INPUT]}
		echo -e "\n低于边界错误!选择[${BLUE}${INPUT_KEY}${PLAIN}]安装！"
		sleep 2s
	fi

	if [ "$INPUT" -gt "${SOURCE_LIST_LEN}" ];then
		INPUT=${SOURCE_LIST_LEN}
		TMP_INPUT=`expr $INPUT - 1`
		INPUT_KEY=${SOURCE_LIST_KEY[$TMP_INPUT]}
		echo -e "\n超出边界错误!选择[${BLUE}${INPUT_KEY}${PLAIN}]安装！"
		sleep 2s
	fi

    INPUT=`expr $INPUT - 1`
    INPUT_KEY=${SOURCE_LIST_KEY[$INPUT]}
    HTTP_PREFIX=${PROXY_URL[$INPUT_KEY]}
}

if [ "$LOCAL_ADDR" != "common" ];then
	ChooseProxyURL

	if [ "$HTTP_PREFIX" != "https://" ] && [ "$HTTP_PREFIX" != "" ];then
		DOMAIN=`echo $HTTP_PREFIX | sed 's|https://||g'`
		DOMAIN=`echo $DOMAIN | sed 's|/||g'`
		# 自动选择逻辑已经包含了测速，如果是手动选择则保持原有的 ping 检查
		if [ "$INPUT" != "" ]; then
			ping -c 3 $DOMAIN > /dev/null 2>&1
			if [ "$?" != "0" ];then
				echo "无效代理地址:${DOMAIN}"
				exit
			fi
		fi
	fi
fi

if [ -f /etc/motd ];then
    echo "welcome to YF panel" > /etc/motd
fi

startTime=`date +%s`

_os=`uname`
echo "use system: ${_os}"


if [ ${_os} == "Darwin" ]; then
	OSNAME='macos'
elif grep -Eq "openSUSE" /etc/*-release; then
	OSNAME='opensuse'
	zypper refresh
	zypper install -y  wget curl zip unzip unrar rar
elif grep -Eq "FreeBSD" /etc/*-release; then
	OSNAME='freebsd'
	pkg install -y wget curl zip unzip unrar rar
elif grep -Eqi "EulerOS" /etc/*-release || grep -Eqi "openEuler" /etc/*-release; then
	OSNAME='euler'
	yum install -y wget curl zip unzip tar crontabs
elif grep -Eqi "CentOS" /etc/issue || grep -Eqi "CentOS" /etc/*-release; then
	OSNAME='rhel'
	yum install -y wget zip unzip tar
elif grep -Eqi "Fedora" /etc/issue || grep -Eqi "Fedora" /etc/*-release; then
	OSNAME='rhel'
	yum install -y wget zip unzip tar
elif grep -Eqi "Rocky" /etc/issue || grep -Eqi "Rocky" /etc/*-release; then
	OSNAME='rhel'
	yum install -y wget zip unzip
elif grep -Eqi "Anolis" /etc/issue || grep -Eqi "Anolis" /etc/*-release; then
	OSNAME='rhel'
	yum install -y wget curl zip unzip tar crontabs
elif grep -Eqi "AlmaLinux" /etc/issue || grep -Eqi "AlmaLinux" /etc/*-release; then
	OSNAME='rhel'
	yum install -y wget zip unzip tar 
elif grep -Eqi "Amazon Linux" /etc/issue || grep -Eqi "Amazon Linux" /etc/*-release; then
	OSNAME='amazon'
	yum install -y wget zip unzip tar
elif grep -Eqi "Ubuntu" /etc/issue || grep -Eqi "Ubuntu" /etc/*-release; then
	OSNAME='ubuntu'
	apt install -y wget zip unzip tar
elif grep -Eqi "Debian" /etc/issue || grep -Eqi "Debian" /etc/*-release; then
	OSNAME='debian'
	apt update -y
	apt install -y devscripts
	apt install -y wget zip unzip tar
elif grep -Eqi "Alpine" /etc/issue || grep -Eqi "Alpine" /etc/*-release; then
	OSNAME='alpine'
	apk update
	apk add devscripts -force-broken-world
	apk add curl wget zip unzip tar -force-broken-world
else
	OSNAME='unknow'
fi

if [ "$EUID" -ne 0 ] && [ "$OSNAME" != "macos" ];then 
	echo "Please run as root!"
 	exit
fi


echo "LOCAL:${LOCAL_ADDR}"
echo "OSNAME:${OSNAME}"

if [ $OSNAME != "macos" ];then

	if id www &> /dev/null ;then 
	    echo ""
	else
	    groupadd www
		useradd -g www -s /usr/sbin/nologin www
	fi
	
	mkdir -p /www/server
	mkdir -p /www/wwwroot
	mkdir -p /www/wwwlogs
	mkdir -p /www/backup/database
	mkdir -p /www/backup/site

	if [ ! -d /www/server/mdserver-web ];then
		if [ -f "$PWD/cli.sh" ] && [ -d "$PWD/scripts" ]; then
			echo "Local repository detected, copying files..."
			cp -r $PWD /www/server/mdserver-web
		else
			echo "downloading ${HTTP_PREFIX}github.com/clhome/bt_simple/archive/refs/heads/dev.tar.gz"
			curl --insecure -sSLo /tmp/dev.tar.gz ${HTTP_PREFIX}github.com/clhome/bt_simple/archive/refs/heads/dev.tar.gz
			cd /tmp && tar -zxvf /tmp/dev.tar.gz
			mv -f /tmp/bt_simple-dev /www/server/mdserver-web
			rm -rf /tmp/dev.tar.gz
			rm -rf /tmp/bt_simple-dev
		fi
	fi

	# install acme.sh
	if [ ! -d /root/.acme.sh ];then
	    if [ "$LOCAL_ADDR" != "common" ];then
	        curl -sSL -o /tmp/acme.tar.gz ${HTTP_PREFIX}github.com/acmesh-official/acme.sh/archive/master.tar.gz
	        tar xvzf /tmp/acme.tar.gz -C /tmp
	        cd /tmp/acme.sh-master
	        bash acme.sh install
	    else
	    	curl -fsSL https://get.acme.sh | bash
	    fi
	    
	    if [ -d /root/.acme.sh ];then
	        /root/.acme.sh/acme.sh --set-default-ca --server letsencrypt
	    fi
	fi
fi

echo "use system version: ${OSNAME}"

if [ "${OSNAME}" == "macos" ];then
	curl --insecure -fsSL ${HTTP_PREFIX}raw.githubusercontent.com/clhome/bt_simple/master/scripts/install/macos.sh | bash
else
	cd /www/server/mdserver-web && bash scripts/install/${OSNAME}.sh
fi

if [ "${OSNAME}" == "macos" ];then
	echo "macos end"
	exit 0
fi

cd /www/server/mdserver-web && bash cli.sh start
isStart=`ps -ef|grep 'gunicorn -c setting.py app:app' |grep -v grep|awk '{print $2}'`
n=0
while [ ! -f /etc/rc.d/init.d/mw ];
do
    echo -e ".\c"
    sleep 1
    let n+=1
    if [ $n -gt 20 ];then
    	echo -e "start mw fail"
        exit 1
    fi
done

cd /www/server/mdserver-web && bash /etc/rc.d/init.d/mw stop
cd /www/server/mdserver-web && bash /etc/rc.d/init.d/mw start
cd /www/server/mdserver-web && bash /etc/rc.d/init.d/mw default

sleep 2
if [ ! -e /usr/bin/mw ]; then
	if [ -f /etc/rc.d/init.d/mw ];then
		ln -s /etc/rc.d/init.d/mw /usr/bin/mw
	fi
fi

if [ ! -e /usr/bin/bs ]; then
	if [ -f /etc/rc.d/init.d/mw ];then
		ln -s /etc/rc.d/init.d/mw /usr/bin/bs
	fi
fi

endTime=`date +%s`
((outTime=(${endTime}-${startTime})/60))
echo -e "Time consumed:\033[32m $outTime \033[0mMinute!"

} 1> >(tee $LOG_FILE) 2>&1

echo -e "\nInstall completed. If error occurs, please contact us with the log file mw-install.log ."
echo "安装完毕，如果出现错误，请带上同目录下的安装日志 mw-install.log 联系我们反馈：admin@yftec.top."