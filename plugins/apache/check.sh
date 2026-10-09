#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

# Apache 服务名称（systemd unit 由 plugins/apache/index.py::initDreplace 生成）
service_name="httpd"

# Apache 主程序：与 plugins/apache/index.py::status 用同一判据（httpd/bin/httpd），
# 这样「面板显示运行中」与「检查任务认为运行中」不会互相矛盾。
httpd_pat="httpd/bin/httpd"

httpd_pids() {
    ps -ef | grep -F "$httpd_pat" | grep -v grep | grep -v python | awk '{print $2}'
}

# 检查 Apache 是否正在运行
if systemctl is-active --quiet "$service_name"; then
    # 检查是否存在僵尸进程
    zombie_processes=$(httpd_pids | xargs -r ps -o state= -p 2>/dev/null | grep -c Z)
    if [ "$zombie_processes" -gt 0 ]; then
        echo "kill httpd 僵尸进程"
        httpd_pids | xargs -r kill -9
        echo "检测到Apache僵尸进程，正在重启服务..."
        systemctl restart "$service_name"
        echo "服务已重启"
    else
        echo "Apache运行正常"
    fi
else
    echo "kill httpd"
    httpd_pids | xargs -r kill
    echo "Apache未运行，正在启动服务..."
    systemctl start "$service_name"
    echo "服务已启动"
fi

HTTPD_IDS=$(httpd_pids)
if [ "$HTTPD_IDS" == "" ];then
    systemctl start "$service_name"
    echo "Apache未运行，正在启动服务..."
fi
