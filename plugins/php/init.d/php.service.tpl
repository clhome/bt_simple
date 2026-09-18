# It's not recommended to modify this file in-place, because it
# will be overwritten during upgrades.  If you want to customize,
# the best way is to use the "systemctl edit" command.
# systemctl daemon-reload

[Unit]
Description=The PHP {$VERSION} FastCGI Process Manager
After=network.target syslog.target

[Service]
Type=simple
Environment="LD_LIBRARY_PATH=/www/server/lib/icu/lib:/www/server/lib/openssl11/lib:/www/server/lib/libzip/lib:/usr/lib/x86_64-linux-gnu:/usr/lib64:/usr/local/lib:/opt/homebrew/lib:$LD_LIBRARY_PATH"
PIDFile={$SERVER_PATH}/php/{$VERSION}/var/run/php-fpm.pid
ExecStartPre=/bin/mkdir -p {$SERVER_PATH}/php/{$VERSION}/var/run {$SERVER_PATH}/php/{$VERSION}/var/log /www/server/php/tmp/session /www/server/php/tmp/upload
ExecStart={$SERVER_PATH}/php/{$VERSION}/sbin/php-fpm --nodaemonize --fpm-config {$SERVER_PATH}/php/{$VERSION}/etc/php-fpm.conf
ExecReload=/bin/kill -USR2 $MAINPID
Restart=on-failure
RestartSec=3s
PrivateTmp=false

[Install]
WantedBy=multi-user.target
