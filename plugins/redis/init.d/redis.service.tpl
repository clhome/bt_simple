[Unit]
Description=Redis In-Memory Data Store
After=network.target

[Service]
Type=forking
ExecStartPre=-/bin/bash -c "pkill -9 redis-server || true"
ExecStart={$SERVER_PATH}/redis/bin/redis-server {$SERVER_PATH}/redis/redis.conf
ExecReload=/bin/kill -USR2 $MAINPID
Restart=on-failure

[Install]
WantedBy=multi-user.target