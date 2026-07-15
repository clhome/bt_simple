#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
export LANG=en_US.UTF-8
is64bit=`getconf LONG_BIT`

if [ -f /etc/motd ];then
    echo "" > /etc/motd
fi

startTime=`date +%s`

_os=`uname`
echo "use system: ${_os}"

if [ "$EUID" -ne 0 ]
  then echo "Please run as root!"
  exit
fi

UNINSTALL_CHECK()
{
    echo -e "----------------------------------------------------"
    echo -e "暂时只能卸载OpenResty/PHP/MySQL/Redis/Memcached"
    echo -e "其他插件先手动卸载!"
    echo -e "----------------------------------------------------"
    echo -e "已知风险/输入yes强制卸载![yes/no]"
    read -p "输入yes强制卸载: " yes;
    if [ "$yes" != "yes" ];then
        echo -e "------------"
        echo "取消卸载"
        exit 1
    else
        echo "开始卸载!"
    fi
}


UNINSTALL_MySQL()
{
    if [ -d /www/server/mysql ];then
        echo -e "----------------------------------------------------"
        echo -e "检查已有MySQL环境，卸载可能影响现有站点及数据"
        echo -e "----------------------------------------------------"
        echo -e "已知风险/输入yes强制卸载![yes/no]"
        read -p "输入yes强制卸载: " yes;
        if [ "$yes" != "yes" ];then
            echo -e "------------"
            echo "取消卸载MySQL"
        else
            MYSQL_VER="8.0"
            if [ -f /www/server/mysql/version.pl ];then
                MYSQL_VER=$(cat /www/server/mysql/version.pl)
            fi
            cd /www/server/yufeng_panel/plugins/mysql && sh install.sh uninstall ${MYSQL_VER}
            echo "卸载MySQL ${MYSQL_VER} 成功!"
        fi
    fi
}

UNINSTALL_OP()
{
    if [ -f /www/server/openresty ];then
        echo -e "----------------------------------------------------"
        echo -e "检查已有OpenResty环境，卸载可能影响现有站点及数据"
        echo -e "----------------------------------------------------"
        echo -e "已知风险/输入yes强制卸载![yes/no]"
        read -p "输入yes强制卸载: " yes;
        if [ "$yes" != "yes" ];then
            echo -e "------------"
            echo "取消卸载OpenResty"
        else
            cd /www/server/yufeng_panel/plugins/openresty && sh install.sh uninstall
            echo "卸载OpenResty成功!"
        fi
    fi
}

UNINSTALL_PHP()
{
    if [ -d /www/server/php ];then
        echo -e "----------------------------------------------------"
        echo -e "检查已有PHP环境，卸载可能影响现有站点及数据"
        echo -e "----------------------------------------------------"
        read -p "输入yes强制卸载所有PHP[yes/no]: " yes;
        if [ "$yes" != "yes" ];then
            echo -e "------------"
            echo "取消卸载PHP"
        else
            PHP_VER_LIST=$(ls /www/server/php)
            for PHP_VER in ${PHP_VER_LIST}; do
                if [ -d /www/server/php/${PHP_VER} ];then
                    echo "正在卸载 PHP ${PHP_VER} ..."
                    cd /www/server/yufeng_panel/plugins/php && bash install.sh uninstall ${PHP_VER}
                    echo "卸载 PHP ${PHP_VER} 成功!"
                fi
            done
        fi
    fi
}

UNINSTALL_MEMCACHED()
{
    if [ -d /www/server/memcached ];then
        echo -e "----------------------------------------------------"
        echo -e "检查已有Memcached环境，卸载可能影响现有站点及数据"
        echo -e "----------------------------------------------------"
        read -p "输入yes强制卸载所有Memcached[yes/no]: " yes;
        if [ "$yes" != "yes" ];then
            echo -e "------------"
            echo "取消卸载Memcached"
        else
            cd /www/server/yufeng_panel/plugins/memcached && bash install.sh uninstall
            echo "卸载Memcached成功"
        fi
    fi
}

UNINSTALL_REDIS()
{
    if [ -d /www/server/redis ];then
        echo -e "----------------------------------------------------"
        echo -e "检查已有Redis环境，卸载可能影响现有站点及数据"
        echo -e "----------------------------------------------------"
        read -p "输入yes强制卸载所有Redis[yes/no]: " yes;
        if [ "$yes" != "yes" ];then
            echo -e "------------"
            echo "取消卸载Redis"
        else
            REDIS_VER="7.0.4"
            if [ -f /www/server/redis/version.pl ];then
                REDIS_VER=$(cat /www/server/redis/version.pl)
            fi
            cd /www/server/yufeng_panel/plugins/redis && bash install.sh uninstall ${REDIS_VER}
            echo "卸载Redis ${REDIS_VER} 成功"
        fi
    fi
}

UNINSTALL_YF()
{
    echo -e "----------------------------------------------------"
    echo -e "检查已有yufeng_panel环境，卸载可能影响现有站点及数据"
    echo -e "----------------------------------------------------"
    read -p "输入yes强制卸载面板: " yes;
    if [ "$yes" != "yes" ];then
        echo -e "------------"
        echo "取消卸载面板"
    else
        rm -rf /usr/bin/mw
        rm -rf /etc/init.d/mw
        rm -rf /usr/bin/yf
        rm -rf /etc/init.d/yf
        systemctl daemon-reload
        rm -rf /www/server/yufeng_panel
        echo "卸载面板成功"
    fi
}

UNINSTALL_CHECK

UNINSTALL_OP
UNINSTALL_PHP
UNINSTALL_MySQL
UNINSTALL_MEMCACHED
UNINSTALL_REDIS
UNINSTALL_YF

endTime=`date +%s`
((outTime=(${endTime}-${startTime})/60))
echo -e "Time consumed:\033[32m $outTime \033[0mMinute!"
