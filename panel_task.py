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
import threading

web_dir = os.getcwd() + "/web"
os.chdir(web_dir)
sys.path.append(web_dir)

import core.yf as yf
import thisdb

g_log_file = yf.getPanelTaskExecLog()
if not os.path.exists(g_log_file):
    os.system("touch " + g_log_file)

def execShell(cmdstring, cwd=None, timeout=None, shell=True, task_id=None):
    import subprocess
    import time
    
    # 启动进程，捕获 stdout 并将 stderr 重定向到 stdout
    sub = subprocess.Popen(cmdstring, cwd=cwd, stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           shell=shell, bufsize=0)

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
                    log_file_handle.flush()
                except:
                    pass
            if task_log_handle:
                try:
                    if line.strip():
                        task_log_handle.write(time_str + line)
                    else:
                        task_log_handle.write(line)
                    task_log_handle.flush()
                except:
                    pass

    if log_file_handle:
        try:
            log_file_handle.close()
        except:
            pass
    if task_log_handle:
        try:
            task_log_handle.close()
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
        socket.setdefaulttimeout(300)

        headers = ('User-Agent', 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36')
        opener = urllib.request.build_opener()
        opener.addheaders = [headers]
        urllib.request.install_opener(opener)

        def downloadHook(count, blockSize, totalSize):
            # 下载文件进度回调
            used = count * blockSize
            pre = int((100.0 * used / totalSize))
            speed = {'total': totalSize, 'used': used, 'pre': pre}
            writeLogs(json.dumps(speed), task_id)

        urllib.request.urlretrieve(url, filename=filename, reporthook=downloadHook)

        if not yf.isAppleSystem():
            os.system('chown www.www ' + filename)

        writeLogs(filename + ' download success!', task_id)
    except Exception as e:
        writeLogs(str(e), task_id)
    return True

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

                if run_task['type'] == 'download':
                    argv = run_task['cmd'].split('|yf|')
                    downloadFile(argv[0], argv[1], task_id=run_task['id'])
                elif run_task['type'] == 'execshell':
                    execShell(run_task['cmd'], task_id=run_task['id'])

                end = int(time.time())
                thisdb.setTaskData(run_task['id'], end=end)
                thisdb.setTaskStatus(run_task['id'], 1)

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
                if name.isdigit() and os.path.isdir(php_dir + '/' + name):
                    verlist.append(name)
        verlist.sort()
        
        for ver in verlist:
            php_path = php_dir + '/' + ver + '/sbin/php-fpm'
            if not os.path.exists(php_path):
                continue
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
            yf.execShell("systemctl restart php" + version)
            if checkPHPVersion(version):
                return True

        # initd
        fpm = server_dir + '/php/init.d/php' + version
        php_path = server_dir + '/php/' + version + '/sbin/php-fpm'
        if not os.path.exists(php_path):
            if os.path.exists(fpm):
                os.remove(fpm)
            return False

        if not os.path.exists(fpm):
            return False

        # 尝试重载服务
        os.system(fpm + ' reload')
        if checkPHPVersion(version):
            return True
        # 尝试重启服务
        cgi = '/tmp/php-cgi-' + version + '.sock'
        pid = server_dir + '/php/' + version + '/var/run/php-fpm.pid'
        data = yf.execShell("ps -ef | grep php/" + version +" | grep -v grep|grep -v python |awk '{print $2}'")
        if data[0] != '':
            os.system("ps -ef | grep php/" + version + " | grep -v grep|grep -v python |awk '{print $2}' | xargs kill ")
        time.sleep(0.5)
        if not os.path.exists(cgi):
            os.system('rm -f ' + cgi)
        if not os.path.exists(pid):
            os.system('rm -f ' + pid)
        os.system(fpm + ' start')
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
        event = threading.Event()
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
            
            # 计算距离下一次最近任务的等待时间
            next_time = min(next_run_times)
            wait_time = next_time - time.time()
            # 限制等待范围 0.1s - 2.0s，兼顾 CPU 挂起节能与文件检查的响应延时
            wait_time = max(0.1, min(wait_time, 2.0))
            event.wait(timeout=wait_time)

def run():
    scheduler = TaskScheduler()
    
    scheduler.add_task(systemTask_step, 15)
    scheduler.add_task(check502Task_step, 10)
    scheduler.add_task(openrestyRestartAtOnce_step, 3)
    scheduler.add_task(openrestyAutoRestart_step, 86400)
    scheduler.add_task(panelPluginStatusCheck_step, 90)
    scheduler.add_task(restartPanelService_step, 3)
    scheduler.add_task(startPanelTask_step, 5)

    def thread_runner():
        scheduler.run()
        
    t = threading.Thread(target=thread_runner)
    if sys.version_info.major == 3 and sys.version_info.minor >= 10:
        t.daemon = True
    else:
        t.setDaemon(True)
    t.start()

    # 保持主线程运行
    while True:
        time.sleep(86400)

if __name__ == "__main__":
    from admin import setup
    setup.init()
    run()
    
