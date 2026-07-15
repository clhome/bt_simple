#!/bin/bash
# chkconfig: 2345 55 25
# description: YF Swap Service

### BEGIN INIT INFO
# Provides:          yf-swap
# Required-Start:    $all
# Required-Stop:     $all
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: starts yf-swap
# Description:       starts the yf-swap
### END INIT INFO


PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin

app_file={$SERVER_PATH}

app_start(){
	if ! grep -q "$app_file" /proc/swaps; then
        echo -e "Starting swap... \c"
        swapon $app_file
        echo -e "\033[32mdone\033[0m"
    else
        echo "Starting swap already running"
    fi
}

app_stop()
{
    if grep -q "$app_file" /proc/swaps; then
        echo -e "Stopping swap... \c"
        swapoff $app_file
        echo -e "\033[32mdone\033[0m"
    else
        echo "Stopping swap already stopped"
    fi
}

app_status()
{
    if grep -q "$app_file" /proc/swaps; then
        echo -e "\033[32mswap already running\033[0m"
    else
        echo -e "\033[31mswap not running\033[0m"
    fi
}

case "$1" in
    'start') app_start;;
    'stop') app_stop;;
    'restart'|'reload') 
        app_stop
        app_start;;
    'status') app_status;;
esac