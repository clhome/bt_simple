# coding:utf-8

import sys
import io
import os
import time

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

def getPluginName():
    return 'linux_sys_opt'

def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()

def get_mem_mb():
    try:
        mem = yf.readFile('/proc/meminfo')
        if mem:
            import re
            m = re.search(r'MemTotal:\s+(\d+)\s+kB', mem)
            if m:
                return int(m.group(1)) // 1024
    except:
        pass
    return 2048


def get_status():
    data = {}
    
    # 辅助函数读取 sysctl
    def read_sysctl(key):
        res = yf.execShell(f"sysctl -n {key}")
        if res[1] == '' and res[0].strip() != '':
            return res[0].strip()
        return "未设置"
        
    data['vm_swappiness'] = read_sysctl('vm.swappiness')
    data['vm_dirty_background_ratio'] = read_sysctl('vm.dirty_background_ratio')
    data['vm_dirty_ratio'] = read_sysctl('vm.dirty_ratio')
    data['net_core_somaxconn'] = read_sysctl('net.core.somaxconn')
    data['vm_max_map_count'] = read_sysctl('vm.max_map_count')
    data['fs_file_max'] = read_sysctl('fs.file-max')
    data['net_ipv4_tcp_tw_reuse'] = read_sysctl('net.ipv4.tcp_tw_reuse')
    data['net_ipv4_ip_local_port_range'] = read_sysctl('net.ipv4.ip_local_port_range')
    data['net_ipv4_tcp_max_syn_backlog'] = read_sysctl('net.ipv4.tcp_max_syn_backlog')
    data['net_ipv4_tcp_max_tw_buckets'] = read_sysctl('net.ipv4.tcp_max_tw_buckets')
    
    # THP
    thp_enabled = "未知"
    if os.path.exists('/sys/kernel/mm/transparent_hugepage/enabled'):
        thp_enabled = yf.readFile('/sys/kernel/mm/transparent_hugepage/enabled').strip()
    data['thp_enabled'] = thp_enabled
    
    data['mem_mb'] = get_mem_mb()
    
    return yf.returnJson(True, "ok", data)

def apply_opt():
    mem_mb = get_mem_mb()
    
    # 动态参数
    if mem_mb <= 2048:
        somaxconn = 1024
        syn_backlog = 2048
        tw_buckets = 5000
        file_max = 1048576
    elif mem_mb <= 8192:
        somaxconn = 4096
        syn_backlog = 8192
        tw_buckets = 20000
        file_max = 2097152
    else:
        somaxconn = 8192
        syn_backlog = 16384
        tw_buckets = 50000
        file_max = 6553500

    # 写入 sysctl 配置
    conf = f"""
# 1. 降低 Swap 换出倾向
vm.swappiness = 10
# 2. 脏页平滑刷盘
vm.dirty_background_ratio = 5
vm.dirty_ratio = 10
# 3. 适度提高 TCP 监听队列上限
net.core.somaxconn = {somaxconn}
# 4. 增加进程可拥有的最大 VMA 数量
vm.max_map_count = 262144
# 5. 系统级最大文件描述符数量
fs.file-max = {file_max}
# 6. TIME_WAIT socket 复用
net.ipv4.tcp_tw_reuse = 1
# 7. 扩大向外连接的端口范围
net.ipv4.ip_local_port_range = 1024 65000
# 8. 应对高并发与 SYN 攻击
net.ipv4.tcp_max_syn_backlog = {syn_backlog}
# 9. 限制最大 TIME_WAIT 数量，省内存
net.ipv4.tcp_max_tw_buckets = {tw_buckets}
"""
    yf.writeFile("/etc/sysctl.d/99-yufeng-server.conf", conf)
    yf.execShell("sysctl --system")
    
    # THP 优化
    if os.path.exists('/sys/kernel/mm/transparent_hugepage/enabled'):
        yf.execShell("echo never > /sys/kernel/mm/transparent_hugepage/enabled")
        yf.execShell("echo never > /sys/kernel/mm/transparent_hugepage/defrag")
        
        # CentOS/RHEL tuned
        if yf.execShell("command -v tuned-adm")[1] == '':
            tuned_conf = """
[main]
summary=Universal server profile with disabled THP
include=throughput-performance

[vm]
transparent_hugepages=never
"""
            yf.execShell("mkdir -p /etc/tuned/no-thp-universal")
            yf.writeFile("/etc/tuned/no-thp-universal/tuned.conf", tuned_conf)
            yf.execShell("tuned-adm profile no-thp-universal")
        
        # Debian/Ubuntu Systemd
        systemd_conf = """
[Unit]
Description=Disable Transparent Huge Pages (THP) for Database and Web Engines
After=sysinit.target local-fs.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo never > /sys/kernel/mm/transparent_hugepage/enabled && echo never > /sys/kernel/mm/transparent_hugepage/defrag'

[Install]
WantedBy=basic.target
"""
        yf.writeFile("/etc/systemd/system/disable-thp.service", systemd_conf)
        yf.execShell("systemctl daemon-reload")
        yf.execShell("systemctl enable --now disable-thp.service")
        
    return yf.returnJson(True, "全平台内核优化配置已成功生效！")

if __name__ == "__main__":
    func = sys.argv[1]
    if func == 'status':
        print('start')
    elif func == 'start':
        print('ok')
    elif func == 'stop':
        print('ok')
    elif func == 'restart':
        print('ok')
    elif func == 'reload':
        print('ok')
    elif func == 'get_status':
        print(get_status())
    elif func == 'apply_opt':
        print(apply_opt())
    else:
        print('error')
