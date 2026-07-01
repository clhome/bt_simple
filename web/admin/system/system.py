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

from flask import Blueprint, render_template
from flask import request

from admin.user_login_check import panel_login_required
from utils.system import monitor

import core.mw as mw
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
    data['system'] = sys.getSystemVersion()
    data['version'] = '0.0.1'
    return mw.getJson(data)

# 获取环境信息
@blueprint.route('/get_env_info', endpoint='get_env_info', methods=['GET','POST'])
@panel_login_required
def get_env_info():
    return sys.getEnvInfo()

# 获取系统的网络流量信息
@blueprint.route('/network', endpoint='network')
@panel_login_required
def network():
    stat = {}
    stat['cpu'] = sys.getCpuInfo()
    stat['load'] = sys.getLoadAverage()
    stat['mem'] = sys.getMemInfo()
    stat['iostat'] = sys.stats().disk()
    stat['network'] = sys.stats().network()
    # 注入任务排队数量，实现高频接口合并
    stat['task_count'] = thisdb.getTaskUnexecutedCount()
    return mw.getJson(stat)

# 获取系统的磁盘信息
@blueprint.route('/disk_info', endpoint='disk_info', methods=['GET','POST'])
@panel_login_required
def disk_info():
    data = sys.getDiskInfo()
    return mw.returnData(True, 'ok', data)

# 获取系统的负载统计信息
@blueprint.route('/get_load_average', endpoint='get_load_average', methods=['GET'])
@panel_login_required
def get_load_average():
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    data = sys.getLoadAverageByDB(start, end)
    return mw.returnData(True, 'ok', data)

# 获取系统的磁盘IO统计信息
@blueprint.route('/get_disk_io', endpoint='get_disk_io', methods=['GET'])
@panel_login_required
def get_disk_io():
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    data = sys.getDiskIoByDB(start, end)
    return mw.returnData(True, 'ok', data)

# 获取系统的CPU/IO统计信息
@blueprint.route('/get_cpu_io', endpoint='get_cpu_io', methods=['GET'])
@panel_login_required
def get_cpu_io():
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    data = sys.getCpuIoByDB(start, end)
    return mw.returnData(True, 'ok', data)

# 获取系统网络IO统计信息
@blueprint.route('/get_network_io', endpoint='get_network_io', methods=['GET'])
@panel_login_required
def get_network_io():
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    data = sys.getNetworkIoByDB(start, end)
    return mw.returnData(True, 'ok', data)

# 重启面板
@blueprint.route('/restart', endpoint='restart', methods=['POST'])
@panel_login_required
def restart():
    mw.restartMw()
    return mw.returnData(True, '面板已重启!')

# 重启面板
@blueprint.route('/restart_server', endpoint='restart_server', methods=['POST'])
@panel_login_required
def restart_server():
    if mw.isAppleSystem():
        return mw.returnData(False, "开发环境不可重起!")
    sys.restartServer()
    return mw.returnData(True, '正在重启服务器!')

# 设置
@blueprint.route('/set_control', endpoint='set_control', methods=['POST'])
@panel_login_required
def set_control():
    stype = request.form.get('type', '')
    day = request.form.get('day', '')

    

    if stype == '0':
        _day = int(day)
        if _day < 1:
            return mw.returnData(False, "保存天数异常!")
        thisdb.setOption('monitor_day', day, type='monitor')
        thisdb.setOption('monitor_status', 'close', type='monitor')
        return mw.returnData(True, "关闭监控成功!")
    elif stype == '1':
        _day = int(day)
        if _day < 1:
            return mw.returnData(False, "保存天数异常!")

        thisdb.setOption('monitor_day', day, type='monitor')
        thisdb.setOption('monitor_status', 'open', type='monitor')
        return mw.returnData(True, "开启监控成功!")
    elif stype == 'save_day':
        _day = int(day)
        if _day < 1:
            return mw.returnData(False, "保存天数异常!")
        thisdb.setOption('monitor_day', day, type='monitor')
        return mw.returnData(True, "修改保存天数成功!")
    elif stype == '2':
        thisdb.setOption('monitor_only_netio', 'close', type='monitor')
        return mw.returnData(True, "关闭仅统计外网成功!")
    elif stype == '3':
        thisdb.setOption('monitor_only_netio', 'open', type='monitor')
        return mw.returnData(True, "开启仅统计外网成功!")
    elif stype == 'del':
        if not mw.isRestart():
            return mw.returnData(False, '请等待所有安装任务完成再执行')
        monitor.instance().clearDbFile()
        return mw.returnData(True, "清空监控记录成功!")
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

        return mw.getJson(data)

    return mw.returnData(False, "异常!")
    
# 获取版本发布说明
@blueprint.route('/get_release_info', endpoint='get_release_info', methods=['GET'])
@panel_login_required
def get_release_info():
    release_file = os.path.join(mw.getPanelDir(), 'RELEASE_TEMPLATE.md')
    if not os.path.exists(release_file):
        release_file = os.path.join(mw.getPanelDir(), 'README.md')
    
    if os.path.exists(release_file):
        content = mw.readFile(release_file)
        return mw.returnData(True, 'ok', content)
    return mw.returnData(False, '未找到发行说明')

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
            except:
                pass
                
        data = {
            'cpu': round(cpu_percent, 2),
            'mem': round(mem_mb, 2)
        }
        return mw.returnData(True, 'ok', data)
    except Exception as e:
        return mw.returnData(False, str(e))

# 获取系统详细信息
@blueprint.route('/get_system_details', endpoint='get_system_details', methods=['GET'])
@panel_login_required
def get_system_details():
    try:
        data = sys.getSystemDetails()
        return mw.returnData(True, 'ok', data)
    except Exception as e:
        return mw.returnData(False, str(e))

# 运行服务器测速
_speed_test_process = None

@blueprint.route('/speed_test', endpoint='speed_test', methods=['POST'])
@panel_login_required
def speed_test():
    global _speed_test_process
    sh_path = os.path.join(mw.getPanelDir(), 'scripts', 'speed.sh')
    log_path = os.path.join(mw.getPanelDir(), 'tmp', 'speed_test.log')
    
    # 检查进程是否还在运行
    is_running = False
    if _speed_test_process is not None:
        try:
            if hasattr(_speed_test_process, 'poll'):
                if _speed_test_process.poll() is None:
                    is_running = True
                else:
                    _speed_test_process = None
        except:
            _speed_test_process = None
            
    if is_running:
        return mw.returnData(True, 'OK', log_path)
        
    # 如果不在运行，清空或新建日志文件
    if os.path.exists(log_path):
        try:
            os.remove(log_path)
        except:
            pass
            
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
            f.write("  -> 节点: 阿里云杭州镜像源 ... 96.15 MB/s\n")
            f.write("  -> 节点: 腾讯云南京镜像源 ... 92.40 MB/s\n")
            f.write("  -> 节点: 华为云深圳镜像源 ... 85.30 MB/s\n")
            f.write("----------------------------------------------------------\n")
            f.write("  -> 节点: 美国官方节点 ... 15.40 MB/s\n")
            f.write("  -> 节点: 英国官方节点 ... 10.62 MB/s\n")
            f.write("  -> 节点: 德国官方节点 ... 12.80 MB/s\n")
            f.write("  -> 节点: 日本官方节点 ... 22.50 MB/s\n")
            f.write("----------------------------------------------------------\n")
            f.write(" 测速完毕！所有临时文件已清理。\n")
            f.write(" 结束时间: " + time.strftime('%Y-%m-%d %H:%M:%S') + "\n")
            f.write("==========================================================\n")
            
        class MockProcess:
            def poll(self):
                return 0
        _speed_test_process = MockProcess()
        return mw.returnData(True, 'OK', log_path)

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    # 启动测速子进程 (Linux)
    try:
        import subprocess
        log_file = open(log_path, 'w', encoding='utf-8')
        try:
            os.chmod(sh_path, 0o755)
        except:
            pass
        _speed_test_process = subprocess.Popen(
            ["bash", sh_path],
            stdout=log_file,
            stderr=log_file,
            preexec_fn=os.setsid if hasattr(os, 'setsid') else None
        )
        return mw.returnData(True, 'OK', log_path)
    except Exception as e:
        return mw.returnData(False, '启动测速失败: ' + str(e))

