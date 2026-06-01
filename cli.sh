#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
DIR=$(cd "$(dirname "$0")"; pwd)
MDIR=$(dirname "$DIR")

export LC_ALL="en_US.UTF-8"

# echo $DIR

PATH=$PATH:$DIR/bin
if [ -f ${DIR}/bin/activate ];then
	source ${DIR}/bin/activate

	if [ "$?" != "0" ];then
		echo "load local python env fail!"
	fi
fi

mw_start_task()
{
    isStart=$(ps aux |grep 'panel_task.py'|grep -v grep|awk '{print $2}')
    if [ "$isStart" == '' ];then
        echo -e "starting bs-tasks... \c"
        cd $DIR && python3 panel_task.py >> ${DIR}/logs/panel_task.log 2>&1 &
        sleep 0.3
        isStart=$(ps aux |grep 'panel_task.py'|grep -v grep|awk '{print $2}')
        if [ "$isStart" == '' ];then
            echo -e "\033[31mfailed\033[0m"
            echo '------------------------------------------------------'
            tail -n 20 $DIR/logs/panel_task.log
            echo '------------------------------------------------------'
            echo -e "\033[31mError: bs-tasks service startup failed.\033[0m"
            return;
        fi
        echo -e "\033[32mdone\033[0m"
    else
        echo "starting bs-tasks... bs-tasks (pid $(echo $isStart)) already running"
    fi
}

mw_start(){
	# 后台任务
	mw_start_task
	
	cd ${DIR}/web && gunicorn -c setting.py app:app
}


mw_start_debug(){
	if [ ! -f $DIR/logs/panel_task.log ];then
		echo '' > $DIR/logs/panel_task.log
	fi

	python3 panel_task.py >> $DIR/logs/panel_task.log 2>&1 &
	port=7200
    if [ -f /www/server/mdserver-web/data/port.pl ];then
        port=$(cat /www/server/mdserver-web/data/port.pl)
    fi

    if [ -f ${DIR}/data/port.pl ];then
        port=$(cat ${DIR}/data/port.pl)
    fi
    cd ${DIR}/web && gunicorn -b :${port} -k gthread -w 1 app:app
	# cd ${DIR}/web && gunicorn -b :${port} -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 app:app
}

mw_start_panel(){
	port=7200
	if [ -f ${DIR}/data/port.pl ];then
        port=$(cat ${DIR}/data/port.pl)
    fi
	cd ${DIR}/web && gunicorn -b :${port} -k gthread -w 1  app:app
	# cd ${DIR}/web && gunicorn -b :${port} -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1  app:app
	
}

mw_start_bgtask(){
	cd ${DIR}/web && gunicorn -c setting.py app:app
	cd ${DIR} && python3 panel_task.py
}


mw_stop()
{
	APP_LIST=`ps -ef|grep app:app |grep -v grep|awk '{print $2}'`
	for p in $APP_LIST
	do
	    kill -9 $p > /dev/null 2>&1
	done

	TASK_LIST=`ps -ef|grep panel_task.py | grep -v grep |awk '{print $2}'`
    for p in $TASK_LIST
    do
    	kill -9 $p > /dev/null 2>&1
    done

    zzpids=`ps -A -o stat,ppid,pid | grep -e '^[Zz]' | awk '{print $2}'`
    for p in $zzpids
    do
        kill -9 ${p} > /dev/null 2>&1
    done
}

case "$1" in
    'start') mw_start;;
    'stop') mw_stop;;
    'restart') 
		mw_stop 
		sleep 2
		mw_start
		;;
	'debug') 
		mw_stop 
		sleep 2
		mw_start_debug
		;;
	'panel') 
		mw_stop 
		sleep 2
		mw_start_panel
		;;
	'task') 
		# mw_stop 
		mw_start_bgtask
		;;
	'uninstall')
		echo -e "\033[31m！！！ 警告 ！！！\033[0m"
		echo -e "该操作将彻底卸载 bt_simple 面板。"
		read -p "确定要继续吗? [yes/no]: " response
		if [ "$response" == "yes" ]; then
			mw_stop
			rm -f /usr/bin/mw
			rm -f /usr/bin/bs
			rm -f /etc/init.d/mw
			rm -f /etc/init.d/bs
			rm -rf $DIR
			echo "卸载完成。"
		else
			echo "已取消。"
		fi
		;;
esac