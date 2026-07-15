#!/bin/bash
set -e

# ==========================================
# 面板与环境容器启动守护脚本
# ==========================================

# 1. 如果 MySQL 数据目录挂载了宿主机的空目录，则执行初始化
if [ -d "/www/server/mysql" ] && [ ! -d "/www/server/mysql/data/mysql" ]; then
    echo "Initializing MySQL data directory..."
    mkdir -p /www/server/mysql/data
    chown -R mysql:mysql /www/server/mysql/data
    /www/server/mysql/scripts/mysql_install_db --user=mysql --datadir=/www/server/mysql/data --basedir=/www/server/mysql
fi

# 2. 面板首次启动初始化（生成随机账密）
if [ ! -f "/www/server/mdserver-web/data/panel_initialized.flag" ]; then
    PANEL_USER=${PANEL_USER:-admin}
    PANEL_PASS=${PANEL_PASSWORD:-$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 12 | head -n 1)}
    
    cd /www/server/mdserver-web
    bin/python tools.py username ${PANEL_USER}
    bin/python tools.py panel ${PANEL_PASS}
    
    echo "=========================================================="
    echo "  Mdserver-Web (bt_simple) Docker Initialized!"
    echo "  Username: ${PANEL_USER}"
    echo "  Password: ${PANEL_PASS}"
    echo "  Notice: You can change them later in the panel."
    echo "=========================================================="
    
    touch /www/server/mdserver-web/data/panel_initialized.flag
fi

echo "Starting services..."

# 3. 逐个启动面板与运行环境
[ -f "/etc/init.d/yf" ] && /etc/init.d/yf start
[ -f "/etc/init.d/openresty" ] && /etc/init.d/openresty start
[ -f "/etc/init.d/php74" ] && /etc/init.d/php74 start
[ -f "/etc/init.d/mysql" ] && /etc/init.d/mysql start

# 4. 输出面板默认连接信息
yf default || true

echo "Container is running. Tailing logs..."

# 5. 挂起进程，保持容器持续运行，同时输出部分错误日志
tail -f /www/server/mdserver-web/logs/error.log /www/wwwlogs/*.log 2>/dev/null || sleep infinity
