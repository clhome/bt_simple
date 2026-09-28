# coding: utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------
# 计划任务
# ---------------------------------------------------------------------------------

import sys
import os
import json
import time
import signal
import threading

web_dir = os.getcwd() + "/web"
os.chdir(web_dir)
sys.path.append(web_dir)

import core.yf as yf
import thisdb

# ---------------------------------------------------------------------------------
# 事件驱动唤醒（第 0 层空转治理）
# 原实现：重型任务线程固定每 3 秒醒来检查任务表，空闲时纯空转。
# 新实现：Web 侧 yf.triggerTask()/restartPanel() 写入触发文件后，再通过 SIGUSR1
#         唤醒本进程，线程无任务时阻塞等待，仅在兜底超时或收到信号时醒来。
#         非 Linux / 无 SIGUSR1 环境下自动退化为短间隔轮询，功能不回退。
# ---------------------------------------------------------------------------------
_TASK_WAKE_EVENT = threading.Event()      # 唤醒重型任务队列线程
_WATCHDOG_WAKE_EVENT = threading.Event()  # 唤醒看门狗（restart.pl 等文件型触发）
_WAKE_SIGNAL_ENABLED = False


def _on_wake_signal(signum, frame):
    _TASK_WAKE_EVENT.set()
    _WATCHDOG_WAKE_EVENT.set()


def setupWakeSignal():
    global _WAKE_SIGNAL_ENABLED
    if not hasattr(signal, 'SIGUSR1'):
        _WAKE_SIGNAL_ENABLED = False
        return False
    try:
        signal.signal(signal.SIGUSR1, _on_wake_signal)
        _WAKE_SIGNAL_ENABLED = True
    except Exception:
        _WAKE_SIGNAL_ENABLED = False
    return _WAKE_SIGNAL_ENABLED


def writePanelTaskPidFile():
    try:
        with open(yf.getPanelTaskPidFile(), 'w') as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def removePanelTaskPidFile():
    try:
        pid_file = yf.getPanelTaskPidFile()
        if os.path.exists(pid_file):
            os.remove(pid_file)
    except Exception:
        pass

g_log_file = yf.getPanelTaskExecLog()
if not os.path.exists(g_log_file):
    try:
        with open(g_log_file, 'a'):
            pass
    except:
        pass

def execShell(cmdstring, cwd=None, timeout=None, shell=True, task_id=None):
    import subprocess
    import time
    
    if shell and isinstance(cmdstring, str):
        try:
            cmdstring = yf.sanitizeCmdScripts(cmdstring, cwd=cwd)
        except:
            pass

    # 启动进程，捕获 stdout 并将 stderr 重定向到 stdout
    sub_kwargs = {
        'cwd': cwd,
        'stdin': subprocess.PIPE,
        'stdout': subprocess.PIPE,
        'stderr': subprocess.STDOUT,
        'shell': shell,
        'bufsize': 0
    }
    if not yf.isAppleSystem() and os.name != 'nt' and hasattr(os, 'setsid'):
        sub_kwargs['preexec_fn'] = os.setsid

    sub = subprocess.Popen(cmdstring, **sub_kwargs)

    cur_task_pid_file = os.path.join(yf.getPanelDir(), 'tmp', 'panel_task_sub.pid')
    if task_id:
        try:
            with open(cur_task_pid_file, 'w', encoding='utf-8') as pf:
                pf.write(f"{task_id}:{sub.pid}")
        except:
            pass

    try:
        log_file_handle = open(g_log_file, 'w', encoding='utf-8')
    except:
        log_file_handle = None

    task_log_handle = None
    if task_id:
        task_log_file = yf.getPanelDir() + '/tmp/panelTask_{}.log'.format(task_id)
        task_log_dir = os.path.dirname(task_log_file)
        if not os.path.exists(task_log_dir):
            try:
                os.makedirs(task_log_dir, exist_ok=True)
            except:
                pass
        try:
            task_log_handle = open(task_log_file, 'w', encoding='utf-8')
        except:
            pass

    last_flush_time = time.time()
    # 实时读取
    while True:
        line_bytes = sub.stdout.readline()
        if not line_bytes and sub.poll() is not None:
            break
        if line_bytes:
            try:
                line = line_bytes.decode('utf-8', 'ignore')
            except Exception as e:
                line = str(line_bytes)
            
            # 时间样式 [yymmdd HH:MM]，例如 [260522 14:22]
            time_str = time.strftime('[%y%m%d %H:%M] ')
            if log_file_handle:
                try:
                    if line.strip():
                        log_file_handle.write(time_str + line)
                    else:
                        log_file_handle.write(line)
                except:
                    pass
            if task_log_handle:
                try:
                    if line.strip():
                        task_log_handle.write(time_str + line)
                    else:
                        task_log_handle.write(line)
                except:
                    pass

            now = time.time()
            if now - last_flush_time >= 0.5:
                if log_file_handle:
                    try:
                        log_file_handle.flush()
                    except:
                        pass
                if task_log_handle:
                    try:
                        task_log_handle.flush()
                    except:
                        pass
                last_flush_time = now

    if log_file_handle:
        try:
            log_file_handle.flush()
            log_file_handle.close()
        except:
            pass
    if task_log_handle:
        try:
            task_log_handle.close()
        except:
            pass

    if task_id:
        try:
            if os.path.exists(cur_task_pid_file):
                os.remove(cur_task_pid_file)
        except:
            pass

    return (str(sub.returncode), '')


def writeLogs(data, task_id=None):
    # 写输出日志
    try:
        fp = open(g_log_file, 'w+')
        fp.write(data)
        fp.close()
    except:
        pass
    if task_id:
        task_log_file = yf.getPanelDir() + '/tmp/panelTask_{}.log'.format(task_id)
        task_log_dir = os.path.dirname(task_log_file)
        if not os.path.exists(task_log_dir):
            try:
                os.makedirs(task_log_dir, exist_ok=True)
            except:
                pass
        try:
            with open(task_log_file, 'a+', encoding='utf-8') as f:
                f.write(data + "\n")
        except:
            pass

def downloadFile(url, filename, task_id=None):
    # 下载文件
    try:
        import urllib
        import socket
        from urllib.parse import urlparse

        socket.setdefaulttimeout(300)

        url = str(url).strip()
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ('http', 'https'):
            writeLogs(f"Security Error: Download protocol '{parsed.scheme}' not allowed.", task_id)
            return False

        # SSRF 防护：拒绝解析到内网/回环/保留地址的下载地址
        try:
            from utils.urlguard import validate_url
            _ok, _err, _meta = validate_url(url, resolve=True)
            if not _ok:
                writeLogs(f"Security Error: {_err}", task_id)
                return False
        except Exception as _ue:
            writeLogs(f"Security Error: URL security check failed: {_ue}", task_id)
            return False

        target_dir = os.path.dirname(os.path.abspath(filename))
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        headers = ('User-Agent', 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36')
        opener = urllib.request.build_opener()
        opener.addheaders = [headers]
        urllib.request.install_opener(opener)

        # 闭包缓存变量
        downloadHook.last_pre = -1
        downloadHook.last_time = 0

        def downloadHook(count, blockSize, totalSize):
            # 下载文件进度回调
            used = count * blockSize
            pre = int((100.0 * used / totalSize))
            now = time.time()
            
            # 节流机制：进度变化 >= 1% 或 距离上次写入超过 1 秒，才触发写盘
            if pre != downloadHook.last_pre or (now - downloadHook.last_time >= 1.0):
                speed = {'total': totalSize, 'used': used, 'pre': pre}
                writeLogs(json.dumps(speed), task_id)
                downloadHook.last_pre = pre
                downloadHook.last_time = now

        urllib.request.urlretrieve(url, filename=filename, reporthook=downloadHook)

        if not yf.isAppleSystem():
            try:
                import pwd
                import grp
                uid = pwd.getpwnam('www').pw_uid
                gid = grp.getgrnam('www').gr_gid
                os.chown(filename, uid, gid)
            except:
                yf.execShell(['chown', 'www:www', filename], shell=False)

        writeLogs(filename + ' download success!', task_id)
        return True
    except Exception as e:
        writeLogs(str(e), task_id)
        return False

def runPanelTask():
    # 站点过期检查
    siteEdateCheck()

    lock_file = yf.getTriggerTaskLockFile()
    try:
        if os.path.exists(lock_file):
            bash_list = thisdb.getTaskList(status=-1)
            for task in bash_list:
                thisdb.setTaskStatus(task['id'], 0)

            run_list = thisdb.getTaskList(status=0)
            for run_task in run_list:
                start = int(time.time())
                thisdb.setTaskData(run_task['id'], start=start)
                thisdb.setTaskStatus(run_task['id'], -1)

                success = False
                if run_task['type'] == 'download':
                    argv = run_task['cmd'].split('|yf|')
                    success = downloadFile(argv[0], argv[1], task_id=run_task['id'])
                elif run_task['type'] == 'execshell':
                    res = execShell(run_task['cmd'], task_id=run_task['id'])
                    if res and res[0] == '0':
                        success = True
                    else:
                        success = False
                        writeLogs(f"\n[Error] 任务执行失败，退出代码: {res[0] if res else 'unknown'}", task_id=run_task['id'])

                end = int(time.time())
                thisdb.setTaskData(run_task['id'], end=end)
                status = 1 if success else 2
                thisdb.setTaskStatus(run_task['id'], status)

            if thisdb.getTaskUnexecutedCount() < 1:
                os.remove(lock_file)
    except Exception as e:
        print('runPanelTask:',yf.getTracebackInfo())

# 网站到期处理
def siteEdateCheck():
    try:
        from utils.site import sites as YfSites
        website_edate = thisdb.getOption('website_edate', default='0000-00-00')
        now_time_ymd = time.strftime('%Y-%m-%d', time.localtime())

        if website_edate == now_time_ymd:
            return False
        site_list = thisdb.getSitesEdateList(now_time_ymd)
        for site in site_list:
            YfSites.instance().stop(site['id'])
        thisdb.setOption('website_edate', now_time_ymd)
    except Exception as e:
        print('siteEdateCheck:',yf.getTracebackInfo())

# 任务队列
def startPanelTask_step():
    try:
        runPanelTask()
    except Exception as e:
        print('startPanelTask:', yf.getTracebackInfo())

def systemTask_step():
    # 系统监控任务
    from utils.system import monitor
    try:
        monitor_status = thisdb.getOption('monitor_status',type='monitor',default='open')
        if monitor_status == 'open':
            monitor.instance().run()
    except Exception as ex:
        print('systemTask:',yf.getTracebackInfo())


def panelPluginStatusCheck_step():
    # 插件状态缓存
    from utils.plugin import plugin
    try:
        plugin.instance().autoCachePluginStatus()
    except Exception as ex:
        print('panelPluginStatusCheck:',yf.getTracebackInfo())

# -------------------------------------- PHP监控 start --------------------------------------------- #
# 502错误检查步进
def check502Task_step():
    check_file = yf.getPanelDir() + '/data/502Task.pl'
    try:
        if os.path.exists(check_file):
            check502()
    except Exception as e:
        print('check502Task:', yf.getTracebackInfo())

def check502():
    try:
        server_dir = yf.getServerDir()
        php_dir = server_dir + '/php'
        verlist = []
        if os.path.exists(php_dir):
            for name in os.listdir(php_dir):
                # 仅守护拥有编译版二进制的版本，避免 APT 插件创建的空目录误入列表
                if name.isdigit() and os.path.isdir(php_dir + '/' + name) and os.path.exists(php_dir + '/' + name + '/sbin/php-fpm'):
                    verlist.append(name)
        verlist.sort()
        
        for ver in verlist:
            if checkPHPVersion(ver):
                continue
            if startPHPVersion(ver):
                print('检测到PHP-' + ver + '处理异常,已自动修复!')
                yf.writeLog('PHP守护程序', '检测到PHP-' + ver + '处理异常,已自动修复!')

    except Exception as e:
        yf.writeLog('PHP守护程序', '自动修复异常:'+str(e))


# 处理指定PHP版本
def startPHPVersion(version):
    server_dir = yf.getServerDir()
    try:
        # system
        phpService = yf.systemdCfgDir() + '/php' + version + '.service'
        if os.path.exists(phpService):
            yf.execShell(["systemctl", "restart", "php" + version], shell=False)
            if checkPHPVersion(version):
                return True

        # initd
        fpm = server_dir + '/php/init.d/php' + version
        php_path = server_dir + '/php/' + version + '/sbin/php-fpm'
        if not os.path.exists(php_path):
            if os.path.exists(fpm):
                try:
                    os.remove(fpm)
                except:
                    pass
            return False

        if not os.path.exists(fpm):
            return False

        # 尝试重载服务
        yf.execShell([fpm, 'reload'], shell=False)
        if checkPHPVersion(version):
            return True
        # 尝试重启服务
        cgi = '/tmp/php-cgi-' + version + '.sock'
        pid = server_dir + '/php/' + version + '/var/run/php-fpm.pid'
        
        # 安全且高效地杀死该版本的 php 进程，代替多管道 grep/awk
        yf.execShell(['pkill', '-9', '-f', 'php/' + version], shell=False)
        time.sleep(0.5)
        
        # 原生删除 socket 和 pid 文件
        for temp_file in [cgi, pid]:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
                    
        yf.execShell([fpm, 'start'], shell=False)
        if checkPHPVersion(version):
            return True

        # 检查是否正确启动
        if os.path.exists(cgi):
            return True
    except Exception as e:
        print('startPHPVersion:',yf.getTracebackInfo())
        yf.writeLog('PHP守护程序', '自动修复异常:'+str(e))
        return True


def checkPHPVersion(version):
    # 检查指定PHP版本
    try:
        sock = yf.getFpmAddress(version)
        data = yf.requestFcgiPHP(sock, '/phpfpm_status_' + version + '?json')
        result = str(data, encoding='utf-8')
    except Exception as e:
        result = 'Bad Gateway'
    # 检查openresty
    if result.find('Bad Gateway') != -1:
        return False
    if result.find('HTTP Error 404: Not Found') != -1:
        return False

    # 检查Web服务是否启动
    if result.find('Connection refused') != -1:
        return False
    return True

# -------------------------------------- PHP监控 end --------------------------------------------- #


# --------------------------------------OpenResty Auto Restart Start --------------------------------------------- #
# 解决acme.sh续签后,未起效。
def openrestyAutoRestart_step():
    try:
        odir = yf.getServerDir() + '/openresty'
        if not os.path.exists(odir):
            return
        yf.opWeb('reload')
    except Exception as e:
        yf.writeLog('OpenResty检测', '自动修复异常:'+str(e))
# --------------------------------------OpenResty Auto Restart End   --------------------------------------------- #


# ------------------------------------  OpenResty Restart At Once Start ------------------------------------------ #
def openrestyRestartAtOnce_step():
    restart_nginx_tip = yf.getPanelDir()+'/data/restart_nginx.pl'
    if os.path.exists(restart_nginx_tip):
        os.remove(restart_nginx_tip)
        yf.opWeb('reload')
# -----------------------------------   OpenResty Restart At Once End   ------------------------------------------ #


# --------------------------------------Panel Restart Start   --------------------------------------------- #
def restartPanelService_step():
    restart_tip = yf.getPanelDir()+'/data/restart.pl'
    if os.path.exists(restart_tip):
        print("restart panel")
        os.remove(restart_tip)
        yf.panelCmd('restart_panel')
# --------------------------------------Panel Restart End   --------------------------------------------- #

class TaskScheduler:
    def __init__(self):
        self.tasks = []
        
    def add_task(self, func, interval_seconds):
        self.tasks.append({
            'func': func,
            'interval': interval_seconds,
            'next_run': time.time()
        })
        
    def run(self):
        while True:
            now = time.time()
            next_run_times = []
            for task in self.tasks:
                if now >= task['next_run']:
                    try:
                        task['func']()
                    except Exception as e:
                        print("Task {} failed: {}".format(task['func'].__name__, str(e)))
                    task['next_run'] = time.time() + task['interval']
                next_run_times.append(task['next_run'])

            # 精确等待到下一个任务到期（上限 30s），取代固定 2s 空转；
            # 收到 SIGUSR1 唤醒信号时立即重新调度（restart.pl 等文件型触发）。
            next_time = min(next_run_times) if next_run_times else time.time() + 30.0
            wait_time = max(0.1, min(next_time - time.time(), 30.0))
            _WATCHDOG_WAKE_EVENT.wait(timeout=wait_time)
            _WATCHDOG_WAKE_EVENT.clear()

def run():
    # 事件驱动唤醒初始化（SIGUSR1），非 Linux 自动退化为短间隔轮询
    setupWakeSignal()
    writePanelTaskPidFile()

    # 文件型触发（restart.pl / restart_nginx.pl）的检测间隔：
    # 有信号唤醒时可放宽到 10s（与面板重启倒计时一致，且由 Web 侧主动唤醒），
    # 否则保持 3s 保证响应。看门狗本身最快也要每 10s 醒来一次（check502）。
    file_check_interval = 10 if _WAKE_SIGNAL_ENABLED else 3

    # 通道 1：高频轻量看门狗与监控调度器（负责毫秒级高频检测与自愈，绝不执行阻塞长任务）
    watchdog_scheduler = TaskScheduler()
    watchdog_scheduler.add_task(systemTask_step, 15)
    watchdog_scheduler.add_task(check502Task_step, 10)
    watchdog_scheduler.add_task(openrestyRestartAtOnce_step, file_check_interval)
    watchdog_scheduler.add_task(openrestyAutoRestart_step, 86400)
    watchdog_scheduler.add_task(panelPluginStatusCheck_step, 90)
    watchdog_scheduler.add_task(restartPanelService_step, file_check_interval)

    t_watchdog = threading.Thread(target=watchdog_scheduler.run, name="WatchdogSchedulerThread")
    t_watchdog.daemon = True
    t_watchdog.start()

    # 通道 2：重型长耗时任务队列执行器（独立线程执行，软件编译安装期间完全不阻塞通道 1 看门狗）
    def heavy_task_worker():
        while True:
            try:
                startPanelTask_step()
            except Exception as e:
                print("heavy_task_worker error:", str(e))
            # 事件驱动：yf.triggerTask() 发 SIGUSR1 时立即唤醒处理新任务；
            # 兜底超时防止极端漏唤醒，无信号能力时退回 3s 短轮询。
            idle_timeout = 60.0 if _WAKE_SIGNAL_ENABLED else 3.0
            _TASK_WAKE_EVENT.wait(timeout=idle_timeout)
            _TASK_WAKE_EVENT.clear()

    t_heavy = threading.Thread(target=heavy_task_worker, name="HeavyTaskWorkerThread")
    t_heavy.daemon = True
    t_heavy.start()

    # 保持主线程运行
    try:
        while True:
            time.sleep(86400)
    finally:
        removePanelTaskPidFile()

if __name__ == "__main__":
    from admin import setup
    setup.init()
    run()
    
