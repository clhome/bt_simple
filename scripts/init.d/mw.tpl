#!/bin/bash
# chkconfig: 2345 55 25
# description: MW Cloud Service

### BEGIN INIT INFO
# Provides:          mw
# Required-Start:    $all
# Required-Stop:     $all
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: starts bs
# Description:       starts the bs
### END INIT INFO

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


PATH=/usr/local/bin:/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export LANG=en_US.UTF-8

PANEL_DIR={$SERVER_PATH}
ROOT_PATH=$(dirname "$PANEL_DIR")
PATH=$PATH:${PANEL_DIR}/bin


if [ -f ${PANEL_DIR}/bin/activate ];then
    source ${PANEL_DIR}/bin/activate
    if [ "$?" != "0" ];then
        echo "load local python env fail!"
    fi
fi

mw_start_panel()
{
    isStart=`ps -ef|grep 'gunicorn -c setting.py app:app' |grep -v grep|awk '{print $2}'`
    if [ "$isStart" == '' ];then
        echo -e "starting bs-panel... \c"
        cd ${PANEL_DIR}/web &&  gunicorn -c setting.py app:app
        port=$(cat ${PANEL_DIR}/data/port.pl)
        isStart=""
        n=0
        while [[ "$isStart" == "" ]];
        do
            echo -e ".\c"
            sleep 0.5
            # isStart=$(lsof -n -P -i:$port|grep LISTEN|grep -v grep|awk '{print $2}'|xargs)
            isStart=$(ss -tulnp | grep ":$port" |grep LISTEN|grep -v grep|awk '{print $2}'|xargs)
            if [[ "$isStart" == "" ]];then
                isStart=$(ps -ef|grep python3|grep mdserver-web|grep app:app|awk '{print $2}'|xargs)
            fi
            let n+=1
            if [ $n -gt 60 ];then
                break;
            fi
        done
        if [ "$isStart" == '' ];then
            echo -e "\033[31mfailed\033[0m"
            echo '------------------------------------------------------'
            tail -n 20 ${PANEL_DIR}/logs/panel_error.log
            echo '------------------------------------------------------'
            echo -e "\033[31mError: bs-panel service startup failed.\033[0m"
            return;
        fi
        echo -e "\033[32mdone\033[0m"
    else
        echo "starting bs-panel... bs(pid $(echo $isStart)) already running"
    fi
}


mw_start_task()
{
    isStart=$(ps aux |grep 'panel_task.py'|grep -v grep|awk '{print $2}')
    if [ "$isStart" == '' ];then
        echo -e "starting bs-tasks... \c"
        cd ${PANEL_DIR} && python3 panel_task.py >> ${PANEL_DIR}/logs/panel_task.log 2>&1 &
        sleep 0.3
        isStart=$(ps aux |grep 'panel_task.py'|grep -v grep|awk '{print $2}')
        if [ "$isStart" == '' ];then
            echo -e "\033[31mfailed\033[0m"
            echo '------------------------------------------------------'
            tail -n 20 ${PANEL_DIR}/logs/panel_task.log
            echo '------------------------------------------------------'
            echo -e "\033[31mError: bs-tasks service startup failed.\033[0m"
            return;
        fi
        echo -e "\033[32mdone\033[0m"
    else
        echo "starting bs-tasks... bs-tasks (pid $(echo $isStart)) already running"
    fi
}

mw_start()
{
    mw_start_task
	mw_start_panel
}

# /www/server/mdserver-web/logs/panel_task.lock && service mw restart_task
mw_stop_task()
{
    if [ -f ${PANEL_DIR}/logs/panel_task.lock ];then
        echo -e "\033[32mthe task is running and cannot be stopped\033[0m"
        return 0
    fi

    echo -e "stopping bs-tasks... \c";
    panel_task=$(ps aux | grep 'panel_task.py'|grep -v grep|awk '{print $2}')
    for p in $panel_task
    do
        kill -9 $p  > /dev/null 2>&1
    done

    zzpids=$(ps -A -o stat,ppid,pid,cmd | grep -e '^[Zz]' | awk '{print $2}')
    for p in $zzpids
    do
        kill -9 $p > /dev/null 2>&1
    done
    echo -e "\033[32mdone\033[0m"
}

mw_stop_panel()
{
    echo -e "stopping bs-panel... \c";
    pidfile=${PANEL_DIR}/logs/panel.pid
    if [ -f $pidfile ];then
        pid=`cat $pidfile`
        kill -9 $pid > /dev/null 2>&1
        rm -f $pidfile
    fi

    APP_LIST=`ps aux|grep 'gunicorn -c setting.py app:app'|grep -v grep|awk '{print $2}'`
    for p in $APP_LIST
    do
        kill -9 $p > /dev/null 2>&1
    done

    APP_LIST=`ps -ef|grep app:app |grep -v grep|awk '{print $2}'`
    for i in $APP_LIST
    do
        kill -9 $i > /dev/null 2>&1
    done
    echo -e "\033[32mdone\033[0m"
}

mw_stop()
{
    mw_stop_task
    mw_stop_panel
}

mw_status()
{
    isStart=$(ps aux|grep 'gunicorn -c setting.py app:app'|grep -v grep|awk '{print $2}')
    if [ "$isStart" != '' ];then
        echo -e "\033[32mbs (pid $(echo $isStart)) already running\033[0m"
    else
        echo -e "\033[31mbs not running\033[0m"
    fi
    
    isStart=$(ps aux |grep 'panel_task.py'|grep -v grep|awk '{print $2}')
    if [ "$isStart" != '' ];then
        echo -e "\033[32mbs-task (pid $isStart) already running\033[0m"
    else
        echo -e "\033[31mbs-task not running\033[0m"
    fi
}


mw_reload()
{
	isStart=$(ps aux|grep 'gunicorn -c setting.py app:app'|grep -v grep|awk '{print $2}')
    
    if [ "$isStart" != '' ];then
    	echo -e "reload bs... \c";
	    arr=`ps aux|grep 'gunicorn -c setting.py app:app'|grep -v grep|awk '{print $2}'`
		for p in $arr
        do
                kill -9 $p
        done
        cd ${PANEL_DIR}/web && gunicorn -c setting.py app:app
        isStart=`ps aux|grep 'gunicorn -c setting.py app:app'|grep -v grep|awk '{print $2}'`
        if [ "$isStart" == '' ];then
            echo -e "\033[31mfailed\033[0m"
            echo '------------------------------------------------------'
            tail -n 20 $mw_path/logs/error.log
            echo '------------------------------------------------------'
            echo -e "\033[31mError: bs service startup failed.\033[0m"
            return;
        fi
        echo -e "\033[32mdone\033[0m"
    else
        echo -e "\033[31mbs not running\033[0m"
        mw_start
    fi
}

mw_close(){
    cd ${PANEL_DIR} && python3 panel_tools.py cli 14
}

mw_open()
{
    cd ${PANEL_DIR} && python3 panel_tools.py cli 15
}

mw_unbind_domain()
{
    if [ -f ${PANEL_DIR}/data/bind_domain.pl ];then
        rm -rf ${PANEL_DIR}/data/bind_domain.pl
    fi
}

mw_unbind_ssl()
{
    if [ -f ${PANEL_DIR}/local ];then
        rm -rf ${PANEL_DIR}/local
    fi

    if [ -f $mw_path/nginx ];then
        rm -rf $mw_path/nginx
    fi

    if [ -f $mw_path/ssl/choose.pl ];then
        rm -rf $mw_path/ssl/choose.pl
    fi
}

error_logs()
{
	tail -n 100 ${PANEL_DIR}/logs/panel_error.log
}

# 00----00----00----00----00----00----00----00----00----00----00----00----00----00

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

mw_install(){
   if [ -f ${PANEL_DIR}/task.py ];then
        echo "与后续版本差异太大,不再提供更新"
        exit 0
    fi

    echo "bash <(curl -fsSL https://panel.yftec.top/deploy.sh) install"
    bash <(curl -fsSL https://panel.yftec.top/deploy.sh)
    mw_clean_lib
    bash <(curl -fsSL https://panel.yftec.top/deploy.sh)
}

mw_update()
{
    if [ -f ${PANEL_DIR}/task.py ];then
        echo "与后续版本差异太大,不再提供更新"
        exit 0
    fi

    echo "bash <(curl -fsSL https://panel.yftec.top/deploy.sh)"
    bash <(curl -fsSL https://panel.yftec.top/deploy.sh)
}

mw_update_dev()
{
    if [ -f ${PANEL_DIR}/task.py ];then
        echo "与后续版本差异太大,不再提供更新"
        exit 0
    fi

    echo "bash <(curl -fsSL https://panel.yftec.top/deploy.sh)"
    mw_clean_lib
    bash <(curl -fsSL https://panel.yftec.top/deploy.sh)
    cd ${PANEL_DIR}
}

mw_dev()
{
    if [ -f ${PANEL_DIR}/task.py ];then
        echo "与后续版本差异太大,不再提供更新"
        exit 0
    fi

    echo "bash <(curl -fsSL https://panel.yftec.top/deploy.sh)"
    bash <(curl -fsSL https://panel.yftec.top/deploy.sh)
    cd ${PANEL_DIR}
}

mw_update_venv()
{
    rm -rf ${PANEL_DIR}/bin
    rm -rf ${PANEL_DIR}/lib64
    rm -rf ${PANEL_DIR}/lib

    echo "bash <(curl -fsSL https://panel.yftec.top/deploy.sh)"
    bash <(curl -fsSL https://panel.yftec.top/deploy.sh)
    
    cd ${PANEL_DIR}
}

mw_mirror()
{
    LOCAL_ADDR=common
    cn=$(curl -fsSL -m 10 -s http://ipinfo.io/json | grep "\"country\": \"CN\"")
    if [ ! -z "$cn" ] || [ "$?" == "0" ] ;then
        LOCAL_ADDR=cn
    fi

    if [ "$LOCAL_ADDR" == "common" ];then
        bash <(curl --insecure -sSL https://raw.githubusercontent.com/supermanito/LinuxMirrors/main/ChangeMirrors.sh)
    else
        bash <(curl -sSL https://linuxmirrors.cn/main.sh)
    fi
    cd ${ROOT_PATH}
}

mw_install_app()
{
    bash $mw_path/scripts/quick/app.sh
}

mw_close_admin_path(){
    cd ${PANEL_DIR} && python3 panel_tools.py cli 6
}

mw_force_kill()
{
    PLIST=`ps -ef|grep app:app |grep -v grep|awk '{print $2}'`
    for i in $PLIST
    do
        kill -9 $i
    done

    pids=`ps -ef|grep task.py | grep -v grep |awk '{print $2}'`
    for p in $pids
    do
        kill -9 $p
    done
}

mw_debug(){
    mw_stop
    mw_force_kill

    port=7200    
    if [ -f ${PANEL_DIR}/data/port.pl ];then
        port=$(cat ${PANEL_DIR}/data/port.pl)
    fi

    if [ -d ${PANEL_DIR}/web ];then
        cd ${PANEL_DIR}/web
    fi
    # gunicorn -b :$port -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1  app:app
    gunicorn -b :$port -k gevent -w 1  app:app
}

mw_connect_mysql(){
    # choose mysql login

    declare -A DB_TYPE

    if [ -d "${ROOT_PATH}/mysql" ];then
        DB_TYPE["mysql"]="mysql"
    fi

    if [ -d "${ROOT_PATH}/mariadb" ];then
        DB_TYPE["mariadb"]="mariadb"
    fi

    if [ -d "${ROOT_PATH}/mysql-apt" ];then
        DB_TYPE["mysql-apt"]="mysql-apt"
    fi

    if [ -d "${ROOT_PATH}/mysql-yum" ];then
        DB_TYPE["mysql-yum"]="mysql-yum"
    fi

    if [ -d "${ROOT_PATH}/mysql-community" ];then
        DB_TYPE["mysql-community"]="mysql-community"
    fi

    SOURCE_LIST_KEY_SORT_TMP=$(echo ${!DB_TYPE[@]} | tr ' ' '\n' | sort -n)
    SOURCE_LIST_KEY=(${SOURCE_LIST_KEY_SORT_TMP//'\n'/})
    SOURCE_LIST_LEN=${#DB_TYPE[*]}

    if [ "$SOURCE_LIST_LEN" == "0" ]; then
        echo -e "no data!"
        exit 1
    fi

    cm_i=0
    for M in ${SOURCE_LIST_KEY[@]}; do
        num=`expr $cm_i + 1`
        AutoSizeStr "${M}" "$num"
        cm_i=`expr $cm_i + 1`
    done
    CHOICE_A=$(echo -e "\n${BOLD}└─ Please select and enter the database you want to log in to [ 1-${SOURCE_LIST_LEN} ]：${PLAIN}")
    read -p "${CHOICE_A}" INPUT

    if [ "$INPUT" == "" ]; then
        INPUT=1
    fi

    if [ "$INPUT" -lt "0" ] || [ "$INPUT" -gt "${SOURCE_LIST_LEN}" ]; then
        echo -e "\nBoundary error not selected!"
        exit 1
    fi

    INPUT=`expr $INPUT - 1`
    INPUT_KEY=${SOURCE_LIST_KEY[$INPUT]}
    CHOICE_DB=${DB_TYPE[$INPUT_KEY]}
    echo "login to ${CHOICE_DB}:"

    pwd=$(cd ${ROOT_PATH}/mdserver-web && python3 ${ROOT_PATH}/mdserver-web/plugins/${CHOICE_DB}/index.py root_pwd)
    if [ "$pwd" == "admin" ];then
        pwd=""
    fi

    if [ "$CHOICE_DB" == "mysql" ];then
        ${ROOT_PATH}/mysql/bin/mysql -uroot -p"${pwd}"
    fi

    if [ "$CHOICE_DB" == "mariadb" ];then
        ${ROOT_PATH}/mariadb/bin/mariadb  -S ${ROOT_PATH}/mariadb/mysql.sock -uroot -p"${pwd}"
    fi

    if [ "$CHOICE_DB" == "mysql-community" ];then
        ${ROOT_PATH}/mysql-community/bin/mysql -S ${ROOT_PATH}/mysql-community/mysql.sock -uroot -p"${pwd}"
    fi

    if [ "$CHOICE_DB" == "mysql-apt" ];then
        ${ROOT_PATH}/mysql-apt/bin/usr/bin/mysql -S ${ROOT_PATH}/mysql-apt/mysql.sock -uroot -p"${pwd}"
    fi

    if [ "$CHOICE_DB" == "mysql-yum" ];then
        ${ROOT_PATH}/mysql-yum/bin/usr/bin/mysql -S ${ROOT_PATH}/mysql-yum/mysql.sock -uroot -p"${pwd}"
    fi
}


mw_connect_pgdb(){
    if [ ! -d "${ROOT_PATH}/postgresql" ];then
        echo -e "postgresql not install!"
        exit 1
    fi


    pwd=$(cd ${PANEL_DIR} && python3 ${PANEL_DIR}/plugins/postgresql/index.py root_pwd)
    export PGPASSWORD=${pwd}
    echo "${ROOT_PATH}/postgresql/bin/psql -U postgres -W"
    ${ROOT_PATH}/postgresql/bin/psql -U postgres -W
}


mw_mongodb(){
    CONF="${ROOT_PATH}/mongodb/mongodb.conf"
    if [ ! -f "$CONF" ]; then
        echo -e "not install mongodb!"
        exit 1
    fi

    MGDB_PORT=$(cat $CONF |grep port|grep -v '#'|awk '{print $2}')
    MGDB_AUTH=$(cat $CONF |grep authorization | grep -v '#'|awk '{print $2}')

    AUTH_STR=""
    if [[ "$MGDB_AUTH" == "enabled" ]];then
        pwd=$(cd ${PANEL_DIR} && python3 ${PANEL_DIR}/plugins/mongodb/index.py root_pwd)
        AUTH_STR="-u root -p ${pwd}"
    fi

    CLIEXEC="${ROOT_PATH}/mongodb/bin/mongosh --port ${MGDB_PORT} ${AUTH_STR}"
    echo $CLIEXEC
    ${CLIEXEC}
}


mw_redis(){
    CONF="${ROOT_PATH}/redis/redis.conf"

    if [ ! -f "$CONF" ]; then
        echo -e "not install redis!"
        exit 1
    fi

    REDISPORT=$(cat $CONF |grep port|grep -v '#'|awk '{print $2}')
    REDISPASS=$(cat $CONF |grep requirepass|grep -v '#'|awk '{print $2}')
    if [ "$REDISPASS" != "" ];then
        REDISPASS=" -a $REDISPASS"
    fi
    CLIEXEC="${ROOT_PATH}/redis/bin/redis-cli -p $REDISPORT$REDISPASS"
    echo $CLIEXEC
    ${CLIEXEC}
}

mw_valkey(){
    CONF="${ROOT_PATH}/valkey/valkey.conf"

    if [ ! -f "$CONF" ]; then
        echo -e "not install valkey!"
        exit 1
    fi

    REDISPORT=$(cat $CONF |grep port|grep -v '#'|awk '{print $2}')
    REDISPASS=$(cat $CONF |grep requirepass|grep -v '#'|awk '{print $2}')
    if [ "$REDISPASS" != "" ];then
        REDISPASS=" -a $REDISPASS"
    fi
    CLIEXEC="${ROOT_PATH}/valkey/bin/valkey-cli -p $REDISPORT$REDISPASS"
    echo $CLIEXEC
    ${CLIEXEC}
}

mw_ssh(){
    cd ${PANEL_DIR} && python3 panel_tools.py cli 202

    if [[ "$?" == "0" ]]; then
        POS=$(echo -e "\n${BLUE}└─ 选择登陆终端：${PLAIN}")
        read -p "${POS}" INPUT
        SSS=`cd ${PANEL_DIR} && python3 panel_tools.py cli 202 $INPUT`
        # echo "info:$SSS"
        # SSS="127.0.0.1|22|root|xx"
        IFS='|' read -r SERVER_IP SERVER_PORT SERVER_USER SERVER_PASS <<< "$SSS"
        echo "Attempting SSH connection to $SERVER_USER@$SERVER_IP:$SERVER_PORT"
        sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -p "$SERVER_PORT" "$SERVER_USER@$SERVER_IP"
    fi
}

mw_venv(){
    cd ${PANEL_DIR} && source bin/activate
}

mw_clean_lib(){
    cd ${PANEL_DIR} && rm -rf lib
    cd ${PANEL_DIR} && rm -rf lib64
    cd ${PANEL_DIR} && rm -rf bin
    cd ${PANEL_DIR} && rm -rf include
}

mw_list(){
    echo -e "bs default         - 显示面板默认信息"
    echo -e "bs db              - 连接MySQL"
    echo -e "bs pgdb            - 连接PostgreSQL"
    echo -e "bs mongdb          - 连接MongoDB"
    echo -e "bs redis           - 连接Redis"
    echo -e "bs valkey          - 连接WalKey"
    echo -e "bs install         - 执行安装脚本"
    echo -e "bs update          - 更新到正式环境最新代码"
    echo -e "bs update_dev      - 更新到测试环境最新代码"
    echo -e "bs migrate_restore - 一键恢复宝塔面板软件数据"
    echo -e "bs debug           - 调式开发面板"
    echo -e "bs list            - 显示命令列表"
}

mw_default(){
    cd ${PANEL_DIR}
    port=7200
    scheme=$(cd ${PANEL_DIR} && python3 ${PANEL_DIR}/panel_tools.py panel_ssl_type)
    
    if [ -f ${PANEL_DIR}/data/port.pl ];then
        port=$(cat ${PANEL_DIR}/data/port.pl)
    fi

    if [ ! -f ${PANEL_DIR}/data/default.pl ];then
        echo -e "\033[33mInstall Failed\033[0m"
        exit 1
    fi

    password=$(cat ${PANEL_DIR}/data/default.pl)

    admin_path=$(cd ${PANEL_DIR} && python3 ${PANEL_DIR}/panel_tools.py admin_path)
    if [ "$address" == "" ];then
        v4=$(cd ${PANEL_DIR} && python3 ${PANEL_DIR}/panel_tools.py getServerIp 4)
        local_ip=$(cd ${PANEL_DIR} && python3 ${PANEL_DIR}/panel_tools.py getLocalIp)
        
        address="内网 御风面板URL: ${scheme}://$local_ip:$port$admin_path"
        if [ "$v4" != "" ] && [ "$v4" != "$local_ip" ]; then
            address="${address}\n外网 御风面板URL: ${scheme}://$v4:$port$admin_path"
        fi
    else
        address="御风面板URL: ${scheme}://$address:$port$admin_path"
    fi

    # bind domain check
    panel_bind_domain=$(cd ${PANEL_DIR} && python3 ${PANEL_DIR}/panel_tools.py panel_bind_domain)
    if [ "$panel_bind_domain" != "" ];then
        address="御风面板URL: ${scheme}://$panel_bind_domain:$port$admin_path\n${address}"
    fi

    show_panel_ip="$port|"
    version=""
    if [ -f ${PANEL_DIR}/.version ]; then
        version="【$(cat ${PANEL_DIR}/.version | sed 's/^v//')】"
    fi
    echo -e "=================================================================="
    echo -e "\033[32m${version}御风面板信息\033[0m"
    echo -e "=================================================================="
    echo -e "$address"
    echo -e `cd ${PANEL_DIR} && python3 ${PANEL_DIR}/panel_tools.py username`
    echo -e `cd ${PANEL_DIR} && python3 ${PANEL_DIR}/panel_tools.py password`
    echo -e "\033[33m提示:\033[0m"
    echo -e "\033[33m如果无法访问面板，请在安全组开放端口 (${show_panel_ip}80|443|22)。\033[0m"
    echo -e "\033[33m请保存好你的密码，为了您的安全性关闭后无法再次显示！如忘记密码请用 bs 11 进行密码重置。\033[0m"
    echo -e "=================================================================="
}

case "$1" in
    'start') mw_start;;
    'stop') mw_stop;;
    'reload') mw_reload;;
    'restart') 
        mw_stop
        sleep 2
        mw_start
        mw_default;;
    'restart_panel')
        mw_stop_panel
        sleep 2
        mw_start_panel
        mw_default;;
    'restart_task')
        mw_stop_task 
        sleep 2
        mw_start_task
        mw_default;;
    'status') mw_status;;
    'logs') error_logs;;
    'close') mw_close;;
    'open') mw_open;;
    'install') mw_install;;
    'update') mw_update;;
    'dev') mw_dev;;
    'update_dev') mw_update_dev;;
    'install_app') mw_install_app;;
    'close_admin_path') mw_close_admin_path;;
    'unbind_domain') mw_unbind_domain;;
    'unbind_ssl') mw_unbind_domain;;
    'debug') mw_debug;;
    'mirror') mw_mirror;;
    'db') mw_connect_mysql;;
    'pgdb') mw_connect_pgdb;;
    'redis') mw_redis;;
    'valkey')mw_valkey;;
    'mongodb') mw_mongodb;;
    'ssh') mw_ssh;;
    'venv') mw_update_venv;;
    'clean_lib') mw_clean_lib;;
    'list') mw_list;;
    'default') mw_default;;
    'migrate_restore')
        cd ${PANEL_DIR} && python3 ${PANEL_DIR}/panel_tools.py cli migrate_restore
        ;;
    'uninstall')
        if [ -f ${PANEL_DIR}/scripts/uninstall.sh ];then
            bash ${PANEL_DIR}/scripts/uninstall.sh
        else
            echo "uninstall script not found!"
        fi
        ;;
    *)
        cd ${PANEL_DIR} && python3 ${PANEL_DIR}/panel_tools.py cli $1
        ;;
esac
