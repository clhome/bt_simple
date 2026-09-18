# It's not recommended to modify this file in-place, because it
# will be overwritten during upgrades.  If you want to customize,
# the best way is to use the "systemctl edit" command.

[Unit]
Description=The PHP {$VERSION} FastCGI Process Manager
After=network.target

[Service]
Type=forking
Environment="LD_LIBRARY_PATH=/www/server/lib/icu/lib:/www/server/lib/openssl11/lib:/www/server/lib/libzip/lib:/usr/lib/x86_64-linux-gnu:/usr/lib64:/usr/local/lib:/opt/homebrew/lib:$LD_LIBRARY_PATH"
ExecStartPre=/bin/mkdir -p {$SERVER_PATH}/php/52/var/run {$SERVER_PATH}/php/52/var/log /www/server/php/tmp/session /www/server/php/tmp/upload
ExecStart={$SERVER_PATH}/php/init.d/php{$VERSION} start
ExecStop={$SERVER_PATH}/php/init.d/php{$VERSION} stop
PrivateTmp=false

[Install]
WantedBy=multi-user.target
