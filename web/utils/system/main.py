# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import os
import sys
import re
import time
import math
import psutil

import core.mw as mw

from threading import Thread
from time import sleep

def mw_async(f):
    def wrapper(*args, **kwargs):
        thr = Thread(target=f, args=args, kwargs=kwargs)
        thr.start()
    return wrapper

@mw_async
def restartServer():
    if not mw.isRestart():
        return mw.returnData(False, '请等待所有安装任务完成再执行!')
    mw.execShell("sync && init 6 &")
    return mw.returnData(True, '命令发送成功!')

def getPid(self, pname):
    try:
        pids = psutil.pids()
        for pid in pids:
            if psutil.Process(pid).name() == pname:
                return True
        return False
    except:
        return False

def getEnvInfo():
    data = {}
    data['status'] = True
    sdir = mw.getServerDir()

    data['webserver'] = '未安装'
    if os.path.exists(sdir + '/openresty/nginx/sbin/nginx'):
        data['webserver'] = 'OpenResty'
    data['php'] = []
    phpversions = ['52', '53', '54', '55', '56', '70', '71', '72', '73', '74', '80', '81', '82', '83', '84']
    phpPath = sdir + '/php/'
    for pv in phpversions:
        if not os.path.exists(phpPath + pv + '/bin/php'):
            continue
        data['php'].append(pv)
    data['mysql'] = False
    if os.path.exists(sdir + '/mysql/bin/mysql'):
        data['mysql'] = True
    try:
        diskInfo = psutil.disk_usage('/www')
    except:
        diskInfo = psutil.disk_usage('/')
    data['disk'] = diskInfo[2]
    return mw.returnData(True, 'ok', data)

def getDiskInfo():
    # 取磁盘分区信息
    temp = mw.execShell("df -h -P|grep '/'|grep -v tmpfs | grep -v devfs")[0]
    tempInodes = mw.execShell("df -i -P|grep '/'|grep -v tmpfs | grep -v devfs")[0]
    temp1 = temp.split('\n')
    tempInodes1 = tempInodes.split('\n')
    diskInfo = []
    n = 0
    cuts = ['/mnt/cdrom', '/boot', '/boot/efi', '/dev',
            '/dev/shm', '/zroot', '/run/lock', '/run', '/run/shm', '/run/user']
    for tmp in temp1:
        n += 1
        inodes = tempInodes1[n - 1].split()
        disk = tmp.split()
        if len(disk) < 5:
            continue
        if disk[1].find('M') != -1:
            continue
        if disk[1].find('K') != -1:
            continue
        if len(disk[5].split('/')) > 4:
            continue
        if disk[5] in cuts:
            continue
        arr = {}
        arr['path'] = disk[5]
        tmp1 = [disk[1], disk[2], disk[3], disk[4]]
        arr['size'] = tmp1
        arr['inodes'] = [inodes[1], inodes[2], inodes[3], inodes[4]]
        diskInfo.append(arr)
    return diskInfo


def getLoadAverage():
    if hasattr(os, 'getloadavg'):
        c = os.getloadavg()
    else:
        c = (0.0, 0.0, 0.0)
    data = {}
    data['one'] = round(float(c[0]), 2)
    data['five'] = round(float(c[1]), 2)
    data['fifteen'] = round(float(c[2]), 2)
    data['max'] = psutil.cpu_count() * 2
    data['limit'] = data['max']
    data['safe'] = data['max'] * 0.75
    return data

def getSystemVersion():
    # 取操作系统版本
    current_os = mw.getOs()
    # sys_temper = self.getSystemDeviceTemperature()
    # print(sys_temper)
    # mac
    if current_os == 'darwin':
        data = mw.execShell('sw_vers')[0]
        data_list = data.strip().split("\n")
        mac_version = ''
        for x in data_list:
            xlist = x.split("\t")
            mac_version += xlist[len(xlist)-1] + ' '

        arch_ver = mw.execShell("arch")
        return mac_version + " (" + arch_ver[0].strip() + ")"

    # freebsd
    if current_os.startswith('freebsd'):
        version = mw.execShell(
            "cat /etc/*-release | grep PRETTY_NAME | awk -F = '{print $2}' | awk -F '\"' '{print $2}'")
        arch_ver = mw.execShell(
            "sysctl -a | egrep -i 'hw.machine_arch' | awk -F ':' '{print $2}'")
        return version[0].strip() + " (" + arch_ver[0].strip() + ")"

    redhat_series = '/etc/redhat-release'
    if os.path.exists(redhat_series):
        version = mw.readFile('/etc/redhat-release')
        version = version.replace('release ', '').strip()

        arch_ver = mw.execShell("arch")
        return version + " (" + arch_ver[0].strip() + ")"

    os_series = '/etc/os-release'
    if os.path.exists(os_series):
        version = mw.execShell(
            "cat /etc/*-release | grep PRETTY_NAME | awk -F = '{print $2}' | awk -F '\"' '{print $2}'")

        arch_ver = mw.execShell("arch")
        return version[0].strip() + " (" + arch_ver[0].strip() + ")"

def getBootTime():
    # 取系统启动时间
    if os.path.exists('/proc/uptime'):
        uptime = mw.readFile('/proc/uptime')
        run_time = uptime.split()[0]
    else:
        start_time = psutil.boot_time()
        run_time = time.time() - start_time
        
    tStr = float(run_time)
    min = tStr / 60
    hours = min / 60
    days = math.floor(hours / 24)
    hours = math.floor(hours - (days * 24))
    min = math.floor(min - (days * 60 * 24) - (hours * 60))
    return mw.getInfo('已不间断运行: {1}天{2}小时{3}分钟', (str(int(days)), str(int(hours)), str(int(min))))

def getCpuInfo(interval=None):
    # 取CPU信息
    cpuCount = psutil.cpu_count()
    cpuLogicalNum = psutil.cpu_count(logical=False)
    
    # 极简与高性能重构：一次性非阻塞获取所有核心的使用率百分比
    used_all = psutil.cpu_percent(interval=interval, percpu=True)
    
    # 物理折算：总使用率恒等于各核心使用率的算术平均值。避免了二次调用 psutil.cpu_percent 导致的快照被消耗失真问题
    if used_all:
        used = round(sum(used_all) / len(used_all), 2)
    else:
        used = 0.0
        
    cpuLogicalNum = 0
    if os.path.exists('/proc/cpuinfo'):
        c_tmp = mw.readFile('/proc/cpuinfo')
        d_tmp = re.findall("physical id.+", c_tmp)
        cpuLogicalNum = len(set(d_tmp))

    cpu_name = mw.getCpuType() + " * {}".format(cpuLogicalNum)
    return used, cpuCount, used_all, cpu_name, cpuCount, cpuLogicalNum

def getMemInfo():
    # 取内存信息
    mem = psutil.virtual_memory()
    if sys.platform == 'darwin':
        memInfo = {'memTotal': mem.total}
        memInfo['memRealUsed'] = memInfo['memTotal'] * (mem.percent / 100)
    elif sys.platform == 'win32' or not hasattr(mem, 'buffers'):
        memInfo = {
            'memTotal': mem.total,
            'memFree': getattr(mem, 'free', mem.available),
            'memBuffers': 0,
            'memCached': 0
        }
        memInfo['memRealUsed'] = getattr(mem, 'used', mem.total - mem.available)
    else:
        memInfo = {
            'memTotal': mem.total,
            'memFree': mem.free,
            'memBuffers': mem.buffers,
            'memCached': mem.cached
        }
        memInfo['memRealUsed'] = memInfo['memTotal'] - memInfo['memFree'] - memInfo['memBuffers'] - memInfo['memCached']
    return memInfo

def getMemUsed():
    # 取内存使用率
    try:
        import psutil
        mem = psutil.virtual_memory()

        if mw.getOs() == 'darwin':
            return mem.percent
        elif sys.platform == 'win32' or not hasattr(mem, 'buffers'):
            return mem.percent

        memInfo = {'memTotal': mem.total / 1024 / 1024, 'memFree': mem.free / 1024 / 1024,
                   'memBuffers': mem.buffers / 1024 / 1024, 'memCached': mem.cached / 1024 / 1024}
        tmp = memInfo['memTotal'] - memInfo['memFree'] - \
            memInfo['memBuffers'] - memInfo['memCached']
        tmp1 = memInfo['memTotal'] / 100
        return (tmp / tmp1)
    except Exception as ex:
        return 1

def getSystemDetails():
    import platform
    import json
    import socket
    
    details = {}
    
    # --- 1. 操作系统 (OS) ---
    os_info = {}
    os_info['system'] = getSystemVersion()
    os_info['kernel'] = platform.release()
    os_info['arch'] = platform.machine()
    
    virt = "未知"
    if sys.platform != 'win32':
        virt_cmd = mw.execShell('systemd-detect-virt')[0].strip()
        if virt_cmd and 'not found' not in virt_cmd and 'No such' not in virt_cmd:
            virt = virt_cmd.upper()
        else:
            virt_cmd2 = mw.execShell("cat /sys/class/dmi/id/product_name")[0].strip()
            if virt_cmd2:
                virt = virt_cmd2
    os_info['virtualization'] = virt
    details['os'] = os_info
    
    # --- 2. CPU ---
    cpu_info = {}
    cpu_info['model'] = mw.getCpuType()
    cpu_info['cores'] = psutil.cpu_count(logical=False)
    cpu_info['threads'] = psutil.cpu_count()
    
    try:
        freq = psutil.cpu_freq()
        if freq and freq.max > 0:
            cpu_info['freq'] = f"{int(freq.max)} MHz"
        else:
            # Fallback 1: Extract from CPU model string
            match = re.search(r'@\s*([\d\.]+)\s*(GHz|MHz)', cpu_info['model'], re.IGNORECASE)
            if match:
                val = float(match.group(1))
                if match.group(2).upper() == 'GHZ':
                    val *= 1000
                cpu_info['freq'] = f"{int(val)} MHz"
            else:
                cpu_info['freq'] = "未知"
    except:
        cpu_info['freq'] = "未知"
        
    cache = "未知"
    aes_vmx = "x / x"
    if sys.platform != 'win32' and os.path.exists('/proc/cpuinfo'):
        cpuinfo_text = mw.readFile('/proc/cpuinfo')
        if cpuinfo_text:
            cache_match = re.search(r'cache size\s*:\s*(.+)', cpuinfo_text)
            if cache_match:
                cache = cache_match.group(1)
            
            # Fallback 2: Read from /proc/cpuinfo if still unknown
            if cpu_info.get('freq', '未知') == '未知':
                freq_match = re.search(r'cpu MHz\s*:\s*([\d\.]+)', cpuinfo_text, re.IGNORECASE)
                if freq_match:
                    cpu_info['freq'] = f"{int(float(freq_match.group(1)))} MHz"
            
            has_aes = 'aes' in cpuinfo_text
            has_vmx = 'vmx' in cpuinfo_text or 'svm' in cpuinfo_text
            has_avx2 = 'avx2' in cpuinfo_text
            has_avx512 = 'avx512' in cpuinfo_text
            
            cpu_info['flags'] = {'AES': has_aes, 'VMX': has_vmx, 'AVX2': has_avx2, 'AVX512': has_avx512}
            
    cpu_info['cache'] = cache
    details['cpu'] = cpu_info
    
    # --- 3. 磁盘 (Disk) ---
    disk_info = {}
    try:
        usage = psutil.disk_usage('/')
        disk_info['total'] = mw.toSize(usage.total)
        disk_info['used'] = mw.toSize(usage.used)
        disk_info['free'] = mw.toSize(usage.free)
        disk_info['percent'] = usage.percent
    except:
        disk_info['total'] = "0"
        disk_info['used'] = "0"
        disk_info['free'] = "0"
        disk_info['percent'] = 0
    details['disk'] = disk_info
    
    # --- 4. 系统状态 (System Status) ---
    status_info = {}
    if os.path.exists('/proc/uptime'):
        uptime = mw.readFile('/proc/uptime')
        run_time = float(uptime.split()[0])
    else:
        run_time = float(time.time() - psutil.boot_time())
        
    min_time = run_time / 60
    hours = min_time / 60
    days = math.floor(hours / 24)
    hours = math.floor(hours - (days * 24))
    min_time = math.floor(min_time - (days * 60 * 24) - (hours * 60))
    status_info['uptime'] = f"{int(days)} days, {int(hours)} hour {int(min_time)} min"
    
    load = getLoadAverage()
    status_info['load'] = f"{load['one']}, {load['five']}, {load['fifteen']}"
    details['status'] = status_info
    
    # --- 5. 网络 (Network) ---
    net_info = {}
    ipv4 = "X"
    ipv6 = "X"
    try:
        for interface, snics in psutil.net_if_addrs().items():
            if interface == 'lo': continue
            for snic in snics:
                if snic.family == socket.AF_INET and ipv4 == "X":
                    ipv4 = snic.address
                elif snic.family == getattr(socket, 'AF_INET6', -1) and ipv6 == "X":
                    ipv6 = snic.address
    except:
        pass
    net_info['ipv4'] = ipv4
    net_info['ipv6'] = ipv6
    
    tcp_cc = "未知"
    if sys.platform != 'win32' and os.path.exists('/proc/sys/net/ipv4/tcp_congestion_control'):
        tcp_cc = mw.readFile('/proc/sys/net/ipv4/tcp_congestion_control').strip()
    net_info['tcp_cc'] = tcp_cc.capitalize() if tcp_cc != "未知" else tcp_cc
    
    ip_data = None
    ip_cache_file = '/tmp/panel_ip_info.json' if sys.platform != 'win32' else os.path.join(mw.getRunDir(), 'tmp', 'panel_ip_info.json')
    if os.path.exists(ip_cache_file) and time.time() - os.path.getmtime(ip_cache_file) < 86400:
        try:
            ip_data = json.loads(mw.readFile(ip_cache_file))
        except:
            pass
            
    if not ip_data:
        try:
            ip_res = mw.execShell('curl -fsSL -m 3 http://ipinfo.io/json')[0]
            if ip_res:
                ip_data = json.loads(ip_res)
                mw.writeFile(ip_cache_file, json.dumps(ip_data))
        except:
            pass
            
    net_info['isp'] = "未知"
    net_info['location'] = "未知"
    if ip_data:
        net_info['isp'] = ip_data.get('org', "未知")
        net_info['location'] = f"{ip_data.get('city', '')}/{ip_data.get('country', '')}"
    details['network'] = net_info
    
    # --- 6. 内存 (Memory) ---
    mem_info = {}
    mem = psutil.virtual_memory()
    mem_info['total'] = mw.toSize(mem.total)
    used = getattr(mem, 'used', mem.total - mem.available)
    mem_info['used'] = mw.toSize(used)
    mem_info['percent'] = mem.percent
    
    try:
        swap = psutil.swap_memory()
        mem_info['swap_total'] = mw.toSize(swap.total)
        mem_info['swap_used'] = mw.toSize(swap.used)
        mem_info['swap_percent'] = swap.percent
    except:
        mem_info['swap_total'] = "0"
        mem_info['swap_used'] = "0"
        mem_info['swap_percent'] = 0
    details['memory'] = mem_info
    
    return details
