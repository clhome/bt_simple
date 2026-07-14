#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH
# LANG=en_US.UTF-8
is64bit=`getconf LONG_BIT`

startTime=`date +%s`

if [ -f /www/server/yufeng_panel/tools.py ];then
    echo -e "存在旧版代码,不能安装!,已知风险的情况下" 
    echo -e "rm -rf /www/server/yufeng_panel"
    echo -e "可安装!" 
    exit 0
fi


_os=`uname`
echo "use system: ${_os}"

if [ "$EUID" -ne 0 ]
  then echo "Please run as root!"
  exit
fi

if [ ${_os} != "Darwin" ] && [ ! -d /www/server/yufeng_panel/logs ]; then
    mkdir -p /www/server/yufeng_panel/logs
fi

LOG_FILE=/var/log/yf-update.log
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
    echo -e '|     欢迎使用 Linux 一键安装mdserver-web面板源码   |'
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

if [ ${_os} == "Darwin" ]; then
    OSNAME='macos'
elif grep -Eqi "openSUSE" /etc/*-release; then
    OSNAME='opensuse'
    zypper refresh
elif grep -Eqi "EulerOS" /etc/*-release || grep -Eqi "openEuler" /etc/*-release; then
    OSNAME='euler'
elif grep -Eqi "FreeBSD" /etc/*-release; then
    OSNAME='freebsd'
elif grep -Eqi "CentOS" /etc/issue || grep -Eqi "CentOS" /etc/*-release; then
    OSNAME='rhel'
    yum install -y wget zip unzip
elif grep -Eqi "Fedora" /etc/issue || grep -Eqi "Fedora" /etc/*-release; then
    OSNAME='rhel'
    yum install -y wget zip unzip
elif grep -Eqi "Rocky" /etc/issue || grep -Eqi "Rocky" /etc/*-release; then
    OSNAME='rhel'
    yum install -y wget zip unzip
elif grep -Eqi "AlmaLinux" /etc/issue || grep -Eqi "AlmaLinux" /etc/*-release; then
    OSNAME='rhel'
    yum install -y wget zip unzip
elif grep -Eqi "Anolis" /etc/issue || grep -Eqi "Anolis" /etc/*-release; then
    OSNAME='rhel'
    yum install -y wget curl zip unzip tar crontabs
elif grep -Eqi "Amazon Linux" /etc/issue || grep -Eqi "Amazon Linux" /etc/*-release; then
    OSNAME='amazon'
    yum install -y wget zip unzip
elif grep -Eqi "Debian" /etc/issue || grep -Eqi "Debian" /etc/*-release; then
    OSNAME='debian'
    apt install -y wget zip unzip
elif grep -Eqi "Ubuntu" /etc/issue || grep -Eqi "Ubuntu" /etc/*-release; then
    OSNAME='ubuntu'
    apt install -y wget zip unzip
elif grep -Eqi "Raspbian" /etc/issue || grep -Eqi "Raspbian" /etc/*-release; then
    OSNAME='raspbian'
elif grep -Eqi "Alpine" /etc/issue || grep -Eqi "Alpine" /etc/*-release; then
    OSNAME='alpine'
    apk update
    apk add devscripts -force-broken-world
    apk add wget zip unzip tar -force-broken-world
else
    OSNAME='unknow'
fi

echo "LOCAL:${LOCAL_ADDR}"

CP_CMD=/usr/bin/cp
if [ -f /bin/cp ];then
        CP_CMD=/bin/cp
fi

echo "update bt_simple code start"

curl --insecure -sSLo /tmp/master.tar.gz ${HTTP_PREFIX}github.com/clhome/bt_simple/archive/refs/heads/master.tar.gz
cd /tmp && tar -zxf /tmp/master.tar.gz
$CP_CMD -rf /tmp/bt_simple-master/* /www/server/yufeng_panel
rm -rf /tmp/master.tar.gz
rm -rf /tmp/bt_simple-master

echo "update bt_simple code end"


#pip uninstall public
echo "use system version: ${OSNAME}"
cd /www/server/yufeng_panel && bash scripts/update/${OSNAME}.sh

bash /etc/rc.d/init.d/yf restart
bash /etc/rc.d/init.d/yf default

if [ -f /usr/bin/yf ];then
    rm -rf /usr/bin/yf
    rm -rf /usr/bin/mw
    rm -rf /usr/bin/bs
fi

if [ -f /usr/bin/bs ];then
    rm -rf /usr/bin/bs
fi

if [ ! -e /usr/bin/yf ]; then
    if [ ! -f /usr/bin/yf ];then
        ln -s /etc/rc.d/init.d/yf /usr/bin/mw
    fi
fi



endTime=`date +%s`
((outTime=($endTime-$startTime)/60))
echo -e "Time consumed:\033[32m $outTime \033[0mMinute!"

} 1> >(tee $LOG_FILE) 2>&1