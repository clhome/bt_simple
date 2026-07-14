#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH
LANG=en_US.UTF-8


# systemctl stop SuSEfirewall2

cd /www/server/yufeng_panel/scripts && bash lib.sh
chmod 755 /www/server/yufeng_panel/data

if [ -f /etc/rc.d/init.d/yf ];then
    bash /etc/rc.d/init.d/yf stop && rm -rf /www/server/yufeng_panel/scripts/init.d/yf && rm -rf /etc/rc.d/init.d/yf
fi

echo -e "start mw"
cd /www/server/yufeng_panel && bash cli.sh start
isStart=`ps -ef|grep 'gunicorn -c setting.py app:app' |grep -v grep|awk '{print $2}'`
n=0
while [[ ! -f /etc/rc.d/init.d/yf ]];
do
    echo -e ".\c"
    sleep 1
    let n+=1
    if [ $n -gt 20 ];then
        echo -e "start mw fail"
        exit 1
    fi
done
echo -e "start mw success"

cd /www/server/yufeng_panel && bash /etc/rc.d/init.d/yf stop
cd /www/server/yufeng_panel && bash /etc/rc.d/init.d/yf start
