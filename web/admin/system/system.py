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
import logging

_log = logging.getLogger('yf.system')

from flask import Blueprint, render_template
from flask import request

from admin.user_login_check import panel_login_required
from utils.system import monitor
from utils.system.monitor import MONITOR_DAY_MAX

import core.yf as yf
import utils.system as sys
import thisdb

blueprint = Blueprint('system', __name__, url_prefix='/system', template_folder='../../templates')

# 获取系统的统计信息
@blueprint.route('/system_total', endpoint='system_total', methods=['GET','POST'])
@panel_login_required
def system_total():
    data = sys.getMemInfo()
    cpu = sys.getCpuInfo(interval=None)
    data['cpuNum'] = cpu[1]
    data['cpuRealUsed'] = cpu[0]
    data['time'] = sys.getBootTime()
    days, hours, min_val = sys.getBootTimeDetail()
    data['boot_time'] = {'days': days, 'hours': hours, 'min': min_val}
    data['system'] = sys.getSystemVersion()
    data['version'] = '0.0.1'
    return yf.getJson(data)

# 获取环境信息
@blueprint.route('/get_env_info', endpoint='get_env_info', methods=['GET','POST'])
@panel_login_required
def get_env_info():
    return sys.getEnvInfo()

# 获取系统的网络流量信息（1.5秒服务端缓存，避免首页+messageBox双轮询重复采集）
_network_cache = None
_network_cache_time = 0

@blueprint.route('/network', endpoint='network')
@panel_login_required
def network():
    import time
    global _network_cache, _network_cache_time
    now = time.time()
    if _network_cache is not None and (now - _network_cache_time) < 1.5:
        return _network_cache

    stat = {}
    stat['cpu'] = sys.getCpuInfo()
    stat['load'] = sys.getLoadAverage()
    stat['mem'] = sys.getMemInfo()
    stat['iostat'] = sys.stats().disk()
    stat['network'] = sys.stats().network()
    # 注入任务排队数量，实现高频接口合并
    stat['task_count'] = thisdb.getTaskUnexecutedCount()
    result = yf.getJson(stat)

    _network_cache = result
    _network_cache_time = now
    return result

# 获取系统的磁盘信息
@blueprint.route('/disk_info', endpoint='disk_info', methods=['GET','POST'])
@panel_login_required
def disk_info():
    data = sys.getDiskInfo()
    return yf.returnData(True, 'ok', data)

# 获取系统的GPU信息
@blueprint.route('/get_gpu_info', endpoint='get_gpu_info', methods=['GET','POST'])
@panel_login_required
def get_gpu_info():
    data = sys.getGpuInfo()
    if data['status']:
        return yf.returnData(True, 'ok', data['data'])
    return yf.returnData(False, data['msg'])

# 获取系统的负载统计信息
@blueprint.route('/get_load_average', endpoint='get_load_average', methods=['GET'])
@panel_login_required
def get_load_average():
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    data = sys.getLoadAverageByDB(start, end)
    return yf.returnData(True, 'ok', data)

# 获取系统的磁盘IO统计信息
@blueprint.route('/get_disk_io', endpoint='get_disk_io', methods=['GET'])
@panel_login_required
def get_disk_io():
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    data = sys.getDiskIoByDB(start, end)
    return yf.returnData(True, 'ok', data)

# 获取系统的CPU/IO统计信息
@blueprint.route('/get_cpu_io', endpoint='get_cpu_io', methods=['GET'])
@panel_login_required
def get_cpu_io():
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    data = sys.getCpuIoByDB(start, end)
    return yf.returnData(True, 'ok', data)

# 获取系统网络IO统计信息
@blueprint.route('/get_network_io', endpoint='get_network_io', methods=['GET'])
@panel_login_required
def get_network_io():
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    data = sys.getNetworkIoByDB(start, end)
    return yf.returnData(True, 'ok', data)

# 重启面板
@blueprint.route('/restart', endpoint='restart', methods=['POST'])
@panel_login_required
def restart():
    yf.restartPanel()
    return yf.returnData(True, 'system.py_msg_7dc7d8')

# 重启服务器
@blueprint.route('/restart_server', endpoint='restart_server', methods=['POST'])
@panel_login_required
def restart_server():
    if yf.isAppleSystem():
        return yf.returnData(False, 'system.py_msg_529504')
    # 判定必须在返回之前：sys.restartServer 是异步的（线程内再判一次），
    # 只在线程里判，会让「有任务在跑、实际不会重启」也回报“正在重启服务器”。
    if not yf.isRestart():
        return yf.returnData(False, 'system.py_msg_0322b3')
    sys.restartServer()
    return yf.returnData(True, 'system.py_msg_b52eca')

# 监控数据保存天数上限 3650 天由 monitor 模块单源定义（utils/system/monitor.py）。
def _parseMonitorDay(value):
    """把「保存天数」入参解析成 1..MONITOR_DAY_MAX 的整数，非法返回 None。

    旧实现直接 ``int(day)``：非数字（API 调用、手填）抛 ValueError → HTTP 500，
    超大值被原样写库 → 清理阈值溢出、存储无限增长。
    """
    try:
        day = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if day < 1 or day > MONITOR_DAY_MAX:
        return None
    return day


# 设置
@blueprint.route('/set_control', endpoint='set_control', methods=['POST'])
@panel_login_required
def set_control():
    stype = request.form.get('type', '')
    day = request.form.get('day', '')

    if stype == '0':
        _day = _parseMonitorDay(day)
        if _day is None:
            return yf.returnData(False, 'system.py_msg_ddb6e3')
        thisdb.setOption('monitor_day', str(_day), type='monitor')
        thisdb.setOption('monitor_status', 'close', type='monitor')
        return yf.returnData(True, 'system.py_msg_68486f')
    elif stype == '1':
        _day = _parseMonitorDay(day)
        if _day is None:
            return yf.returnData(False, 'system.py_msg_ddb6e3')

        thisdb.setOption('monitor_day', str(_day), type='monitor')
        thisdb.setOption('monitor_status', 'open', type='monitor')
        return yf.returnData(True, 'system.py_msg_029959')
    elif stype == 'save_day':
        _day = _parseMonitorDay(day)
        if _day is None:
            return yf.returnData(False, 'system.py_msg_ddb6e3')
        thisdb.setOption('monitor_day', str(_day), type='monitor')
        return yf.returnData(True, 'system.py_msg_dc0177')
    elif stype == '2':
        thisdb.setOption('monitor_only_netio', 'close', type='monitor')
        return yf.returnData(True, 'system.py_msg_6c542d')
    elif stype == '3':
        thisdb.setOption('monitor_only_netio', 'open', type='monitor')
        return yf.returnData(True, 'system.py_msg_80a4f1')
    elif stype == 'del':
        if not yf.isRestart():
            return yf.returnData(False, 'system.py_msg_3bd322')
        monitor.instance().clearDbFile()
        return yf.returnData(True, 'system.py_msg_563ff5')
    else:
        monitor_status = thisdb.getOption('monitor_status', default='open', type='monitor')
        monitor_day = thisdb.getOption('monitor_day', default='30', type='monitor')
        monitor_only_netio = thisdb.getOption('monitor_only_netio', default='open', type='monitor')
        data = {}
        data['day'] = monitor_day
        if monitor_status == 'open':   
            data['status'] = True
        else:
            data['status'] = False
        if monitor_only_netio == 'open':
            data['stat_all_status'] = True
        else:
            data['stat_all_status'] = False

        return yf.getJson(data)

    return yf.returnData(False, 'system.py_msg_8042ad')
    
# 释放内存（首页内存圈的 reMemory()）
#
# 契约由前端决定，不能自创 envelope：`web/static/app/index.js::reMemory()` 直接读
# **顶层** `rdata.memRealUsed` / `rdata.memTotal`（单位 MB，见该函数里
# `formatMemPair(rdata.memRealUsed * 1024 * 1024, ...)`），所以和设备信息类接口
# （`/system/system_total`、`/system/network`）一样走 `yf.getJson(data)` 平铺输出。
# 内存口径与首页其余位置完全一致：都取 `sys.getMemInfo()`，只是换算成 MB。
@blueprint.route('/rememory', endpoint='rememory', methods=['POST'])
@panel_login_required
def rememory():
    script = os.path.join(yf.getPanelDir(), 'scripts', 'rememory.sh')
    if not os.path.exists(script):
        yf.writeFileLog('[system] 释放内存失败：脚本不存在 %s' % script)
        return yf.returnData(False, 'system.exception')
    # 列表传参 + 显式超时：脚本路径取自面板安装目录
    rc, _out, err = yf.execShellRc(['bash', script], shell=False, timeout=180)
    if rc != 0:
        yf.writeFileLog('[system] 释放内存失败 rc=%s err=%s' % (rc, str(err)[:200]))
        return yf.returnData(False, 'system.exception')
    mem = sys.getMemInfo()
    data = {
        'memTotal': round(mem['memTotal'] / 1048576, 2),
        'memRealUsed': round(mem['memRealUsed'] / 1048576, 2),
    }
    return yf.getJson(data)


# 获取版本发布说明
@blueprint.route('/get_release_info', endpoint='get_release_info', methods=['GET'])
@panel_login_required
def get_release_info():
    release_file = os.path.join(yf.getPanelDir(), 'RELEASE_TEMPLATE.md')
    if not os.path.exists(release_file):
        release_file = os.path.join(yf.getPanelDir(), 'README.md')
    
    if os.path.exists(release_file):
        content = yf.readFile(release_file)
        return yf.returnData(True, 'ok', content)
    return yf.returnData(False, 'system.py_msg_d56c7a')

# 获取面板自身占用的系统资源
@blueprint.route('/get_panel_resources', endpoint='get_panel_resources', methods=['GET'])
@panel_login_required
def get_panel_resources():
    import psutil
    import os
    try:
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        cpu_percent = process.cpu_percent(interval=0.1)
        mem_mb = mem_info.rss / 1024 / 1024
        
        children = process.children(recursive=True)
        for child in children:
            try:
                cpu_percent += child.cpu_percent(interval=0)
                mem_mb += child.memory_info().rss / 1024 / 1024
            except Exception as _e:
                # 子进程可能在遍历途中退出，属预期（高频路径，仅 debug）
                _log.debug('[system] 子进程资源采集失败: %s', _e)
                
        data = {
            'cpu': round(cpu_percent, 2),
            'mem': round(mem_mb, 2)
        }
        return yf.returnData(True, 'ok', data)
    except Exception as e:
        return yf.returnData(False, str(e))

# 获取系统详细信息
@blueprint.route('/get_system_details', endpoint='get_system_details', methods=['GET'])
@panel_login_required
def get_system_details():
    try:
        data = sys.getSystemDetails()
        return yf.returnData(True, 'ok', data)
    except Exception as e:
        return yf.returnData(False, str(e))

# 运行服务器测速
_speed_test_process = None

@blueprint.route('/speed_test', endpoint='speed_test', methods=['POST'])
@panel_login_required
def speed_test():
    global _speed_test_process
    sh_path = os.path.join(yf.getPanelDir(), 'scripts', 'speed.sh')
    log_path = os.path.join(yf.getPanelDir(), 'tmp', 'speed_test.log')
    
    # 检查进程是否还在运行
    is_running = False
    if _speed_test_process is not None:
        try:
            if hasattr(_speed_test_process, 'poll'):
                if _speed_test_process.poll() is None:
                    is_running = True
                else:
                    _speed_test_process = None
        except Exception as _e:
            _speed_test_process = None
            
    if is_running:
        return yf.returnData(True, 'OK', log_path)
        
    # 如果不在运行，清空或新建日志文件
    if os.path.exists(log_path):
        try:
            os.remove(log_path)
        except Exception as _e:
            _log.debug('[system] 清理测速日志失败: %s -> %s', log_path, _e)
            
    # Windows 环境模拟
    if os.name == 'nt':
        import time
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("==========================================================\n")
            f.write("          御风面板 (BT-Simple) 服务器测速工具 (Windows 模拟)\n")
            f.write("==========================================================\n")
            f.write(" 开始时间: " + time.strftime('%Y-%m-%d %H:%M:%S') + "\n")
            f.write("----------------------------------------------------------\n")
            f.write(" [1] 系统基本信息\n")
            f.write(" CPU 型号: Intel(R) Core(TM) i7-12700K CPU @ 3.60GHz (12 核)\n")
            f.write(" 物理内存: 16384 MB\n")
            f.write(" 硬盘分区: C盘共 500G, 已用 240G, 剩余 260G\n")
            f.write(" 操作系统: Windows 11 家庭中文版\n")
            f.write(" 系统架构: x86_64\n")
            f.write("----------------------------------------------------------\n")
            f.write(" [2] 磁盘 I/O 读写性能测试\n")
            f.write(" 正在进行磁盘写入测试 (写入 512MB 数据)...\n")
            f.write(" 磁盘写入速度: 382.5 MB/s\n")
            f.write(" 正在进行磁盘读取测试 (读取 512MB 数据)...\n")
            f.write(" 磁盘读取速度: 512.8 MB/s\n")
            f.write("----------------------------------------------------------\n")
            f.write(" [3] 网络下载速度测试 (多区域节点)\n")
            f.write("  -> 节点: 阿里云杭州镜像源 ... 769.20 Mbps\n")
            f.write("  -> 节点: 腾讯云南京镜像源 ... 739.20 Mbps\n")
            f.write("  -> 节点: 华为云深圳镜像源 ... 682.40 Mbps\n")
            f.write("----------------------------------------------------------\n")
            f.write("  -> 节点: 美国官方节点 ... 123.20 Mbps\n")
            f.write("  -> 节点: 英国官方节点 ... 84.96 Mbps\n")
            f.write("  -> 节点: 德国官方节点 ... 102.40 Mbps\n")
            f.write("  -> 节点: 日本官方节点 ... 180.00 Mbps\n")
            f.write("----------------------------------------------------------\n")
            f.write(" 测速完毕！所有临时文件已清理。\n")
            f.write(" 结束时间: " + time.strftime('%Y-%m-%d %H:%M:%S') + "\n")
            f.write("==========================================================\n")
            
        class MockProcess:
            def poll(self):
                return 0
        _speed_test_process = MockProcess()
        return yf.returnData(True, 'OK', log_path)

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    # 启动测速子进程 (Linux)
    try:
        import subprocess
        log_file = open(log_path, 'w', encoding='utf-8')
        try:
            os.chmod(sh_path, 0o755)
        except Exception as _e:
            _log.debug('[system] 测速脚本加执行位失败: %s', _e)
            
        sub_env = os.environ.copy()
        try:
            import psutil
            mem_info = psutil.virtual_memory()
            total_mb = int(mem_info.total / 1024 / 1024)
            sub_env['TOTAL_MEM_MB'] = str(total_mb)
        except Exception as _e:
            _log.debug('[system] 采集总内存失败: %s', _e)
            
        _speed_test_process = subprocess.Popen(
            ["bash", sh_path],
            stdout=log_file,
            stderr=log_file,
            env=sub_env,
            preexec_fn=os.setsid if hasattr(os, 'setsid') else None
        )
        return yf.returnData(True, 'OK', log_path)
    except Exception as e:
        return yf.returnData(False, 'admin.py_msg_a96e77', None, str(e))

