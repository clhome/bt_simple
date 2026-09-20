#!/bin/sh
### BEGIN INIT INFO
# Provides:          fail2ban
# Required-Start:    $local_fs $remote_fs $network $syslog
# Required-Stop:     $local_fs $remote_fs $network $syslog
# Should-Start:      $time iptables ip6tables nftables ipset
# Should-Stop:       $time iptables ip6tables nftables ipset
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Start/stop fail2ban intrusion prevention service
# Description:       fail2ban bans hosts that cause multiple authentication errors
### END INIT INFO

PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
DAEMON=/usr/bin/fail2ban-server
CLIENT=/usr/bin/fail2ban-client
NAME=fail2ban
PIDFILE=/run/fail2ban/fail2ban.pid

[ -x "$DAEMON" ] || exit 0

mkdir -p /run/fail2ban

case "$1" in
    start)
        if [ -f "$PIDFILE" ] && kill -0 "$(cat $PIDFILE 2>/dev/null)" 2>/dev/null; then
            echo "$NAME is already running"
            exit 0
        fi
        $DAEMON -xf start
        ;;
    stop)
        $CLIENT stop >/dev/null 2>&1
        ;;
    restart)
        $CLIENT restart
        ;;
    reload)
        $CLIENT reload
        ;;
    status)
        $CLIENT status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|reload|status}"
        exit 1
        ;;
esac

exit 0
