[Unit]
Description=Redis In-Memory Data Store
After=network.target

[Service]
Type=forking
PIDFile={$SERVER_PATH}/redis/redis.pid
ExecStart={$SERVER_PATH}/redis/bin/redis-server {$SERVER_PATH}/redis/redis.conf
ExecReload=/bin/kill -USR2 $MAINPID
TimeoutStartSec=30
TimeoutStopSec=30
Restart=on-failure
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target