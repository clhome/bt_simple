#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

# OpenResty服务名称（systemd unit 由 plugins/openresty/index.py::initDreplace 生成）
service_name="openresty"

# 面板/server 目录从脚本自身位置反推，与 core/yf.getServerDir() 口径一致：
#   <panel>/plugins/openresty/check.sh -> panel=<panel>, server=dirname(panel)（目录名为 server）
script_dir=$(cd "$(dirname "$0")" && pwd)
panel_dir=$(dirname "$(dirname "$script_dir")")
server_dir=$(dirname "$panel_dir")
if [ "$(basename "$server_dir")" != "server" ]; then
    server_dir="$panel_dir/server"
fi
resty_bin="$server_dir/openresty/bin/openresty"
pid_file="$server_dir/openresty/nginx/logs/nginx.pid"

# 只认 OpenResty 自己的进程：旧写法 `ps -ef|grep nginx` 会命中任何命令行里含 nginx 的
# 无关进程（vim nginx.conf、tail -f nginx 日志、面板自身的 python 命令行），从而把
# 「未运行」误判成「运行中」或误杀无关进程；`xargs kill` 缺 -r 时还会空跑一次。
resty_pids() {
    ps -ef | grep -E "$resty_bin|nginx: worker process" | grep -v grep | grep -v python | awk '{print $2}'
}

# 检查OpenResty是否正在运行
if systemctl is-active --quiet "$service_name"; then
    # 僵尸进程判定以 pid 文件里的主进程为准（nginx 自己维护），避免 ps 文本匹配的假阳性
    master_pid=""
    if [ -f "$pid_file" ]; then
        master_pid=$(cat "$pid_file" 2>/dev/null | tr -dc '0-9')
    fi
    zombie_processes=0
    if [ -n "$master_pid" ]; then
        zombie_processes=$(ps -o state= -p "$master_pid" 2>/dev/null | grep -c Z)
    fi
    if [ "$zombie_processes" -gt 0 ]; then
        echo "kill openresty 僵尸进程"
        resty_pids | xargs -r kill -9
        echo "检测到OpenResty僵尸进程，正在重启服务..."
        systemctl restart "$service_name"
        echo "服务已重启"
    else
        echo "OpenResty运行正常"
    fi
else
    echo "kill openresty"
    resty_pids | xargs -r kill
    echo "OpenResty未运行，正在启动服务..."
    systemctl start "$service_name"
    echo "服务已启动"
fi

RESTY_IDS=$(resty_pids)
if [ "$RESTY_IDS" == "" ];then
    systemctl start "$service_name"
    echo "OpenResty未运行，正在启动服务..."
fi
