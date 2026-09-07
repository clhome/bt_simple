[Unit]
Description=LVS and VRRP High Availability Monitor (Keepalived)
After=network.target

[Service]
Type=forking
ExecStart={$SERVER_PATH}/keepalived/sbin/keepalived -D
ExecReload=/bin/kill -USR1 $MAINPID
Restart=on-failure

[Install]
WantedBy=multi-user.target