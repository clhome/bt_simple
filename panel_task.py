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
import logging

_log = logging.getLogger('yf.panel_task')

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
    except Exception as _e:
        _log.debug('[panel_task] 写任务守护 PID 文件失败: %s', _e)


def removePanelTaskPidFile():
    try:
        pid_file = yf.getPanelTaskPidFile()
        if os.path.exists(pid_file):
            os.remove(pid_file)
    except Exception as _e:
        _log.debug('[panel_task] 清理任务守护 PID 文件失败: %s', _e)

g_log_file = yf.getPanelTaskExecLog()
if not os.path.exists(g_log_file):
    try:
        with open(g_log_file, 'a'):
            pass
    except Exception as _e:
        _log.debug('[panel_task] 创建任务日志文件失败: %s', _e)

# 任务最大运行时长（秒）：避免卡死任务永久堵死队列，超时则杀进程组并标记失败。
# 取一个足够宽裕的上限（编译/大库导入等重活仍能跑完），只堵“永不返回”。
TASK_MAX_RUNTIME = 7200        # execshell 类任务（含软件编译安装）
DOWNLOAD_MAX_RUNTIME = 3600    # download 类任务


def execShell(cmdstring, cwd=None, timeout=None, shell=True, task_id=None):
    import subprocess
    import time
    
    if shell and isinstance(cmdstring, str):
        try:
            cmdstring = yf.sanitizeCmdScripts(cmdstring, cwd=cwd)
        except Exception as _e:
            _log.debug('[panel_task] 清洗命令脚本 CRLF 失败: %s', _e)

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

    # 超时看门狗：到点杀掉整个进程组（setsid 后子进程及其派生进程同组）
    timed_out = {'v': False}

    def _kill_tree():
        try:
            if hasattr(os, 'killpg') and not yf.isAppleSystem() and os.name != 'nt':
                os.killpg(os.getpgid(sub.pid), signal.SIGKILL)
            else:
                sub.kill()
        except Exception as _e:
            _log.debug('[panel_task] 终止进程树失败: %s', _e)
            try:
                sub.kill()
            except Exception as _e2:
                _log.debug('[panel_task] 兜底 kill 也失败: %s', _e2)

    if timeout and timeout > 0:
        def _watchdog():
            try:
                sub.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out['v'] = True
                _kill_tree()
            except Exception as _e:
                _log.debug('[panel_task] 等待子进程异常: %s', _e)

        _wt = threading.Thread(target=_watchdog, name='PanelTaskTimeoutWatchdog')
        _wt.daemon = True
        _wt.start()

    cur_task_pid_file = os.path.join(yf.getPanelDir(), 'tmp', 'panel_task_sub.pid')
    if task_id:
        try:
            with open(cur_task_pid_file, 'w', encoding='utf-8') as pf:
                pf.write(f"{task_id}:{sub.pid}")
        except Exception as _e:
            _log.debug('[panel_task] 写当前任务 PID 文件失败: %s -> %s', cur_task_pid_file, _e)

    try:
        log_file_handle = open(g_log_file, 'w', encoding='utf-8')
    except Exception as _e:
        _log.debug('[panel_task] 打开全局任务日志失败: %s', _e)
        log_file_handle = None

    task_log_handle = None
    if task_id:
        task_log_file = yf.getPanelDir() + '/tmp/panelTask_{}.log'.format(task_id)
        task_log_dir = os.path.dirname(task_log_file)
        if not os.path.exists(task_log_dir):
            try:
                os.makedirs(task_log_dir, exist_ok=True)
            except Exception as _e:
                _log.debug('[panel_task] 创建任务日志目录失败: %s', _e)
        try:
            task_log_handle = open(task_log_file, 'w', encoding='utf-8')
        except Exception as _e:
            _log.debug('[panel_task] 打开任务专属日志失败: %s -> %s', task_log_file, _e)

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
                except Exception as _e:
                    _log.debug('[panel_task] 写全局任务日志失败: %s', _e)
            if task_log_handle:
                try:
                    if line.strip():
                        task_log_handle.write(time_str + line)
                    else:
                        task_log_handle.write(line)
                except Exception as _e:
                    _log.debug('[panel_task] 写任务专属日志失败: %s', _e)

            now = time.time()
            if now - last_flush_time >= 0.5:
                if log_file_handle:
                    try:
                        log_file_handle.flush()
                    except Exception as _e:
                        _log.debug('[panel_task] flush 全局日志失败: %s', _e)
                if task_log_handle:
                    try:
                        task_log_handle.flush()
                    except Exception as _e:
                        _log.debug('[panel_task] flush 任务日志失败: %s', _e)
                last_flush_time = now

    if log_file_handle:
        try:
            log_file_handle.flush()
            log_file_handle.close()
        except Exception as _e:
            _log.debug('[panel_task] 关闭全局任务日志失败: %s', _e)
    if task_log_handle:
        try:
            task_log_handle.close()
        except Exception as _e:
            _log.debug('[panel_task] 关闭任务专属日志失败: %s', _e)

    if task_id:
        try:
            if os.path.exists(cur_task_pid_file):
                os.remove(cur_task_pid_file)
        except Exception as _e:
            _log.debug('[panel_task] 清理当前任务 PID 文件失败: %s', _e)

    if timed_out['v']:
        # 超时被杀：向任务日志明确告知，上游据此置为失败而不是误判为成功
        msg = '\n[Error] 任务执行超时（超过 %s 秒），已强制终止!\n' % timeout
        writeLogs(msg, task_id=task_id)
        try:
            sub.wait(timeout=5)
        except Exception as _e:
            _log.debug('[panel_task] 超时后等待子进程退出失败: %s', _e)
        for _pipe in (sub.stdout, sub.stdin):
            try:
                if _pipe:
                    _pipe.close()
            except Exception as _e:
                _log.debug('[panel_task] 关闭超时任务管道失败: %s', _e)
        return ('timeout', msg)

    for _pipe in (sub.stdout, sub.stdin):
        try:
            if _pipe:
                _pipe.close()
        except Exception as _e:
            _log.debug('[panel_task] 关闭任务管道失败: %s', _e)
    return (str(sub.returncode), '')


def writeLogs(data, task_id=None):
    # 写输出日志
    try:
        fp = open(g_log_file, 'w+')
        fp.write(data)
        fp.close()
    except Exception as _e:
        _log.debug('[panel_task] 覆盖写全局任务日志失败: %s', _e)
    if task_id:
        task_log_file = yf.getPanelDir() + '/tmp/panelTask_{}.log'.format(task_id)
        task_log_dir = os.path.dirname(task_log_file)
        if not os.path.exists(task_log_dir):
            try:
                os.makedirs(task_log_dir, exist_ok=True)
            except Exception as _e:
                _log.debug('[panel_task] 创建任务日志目录失败: %s', _e)
        try:
            with open(task_log_file, 'a+', encoding='utf-8') as f:
                f.write(data + "\n")
        except Exception as _e:
            _log.debug('[panel_task] 追加写任务日志失败: %s', _e)

def _make_safe_redirect_handler():
    """构造一个对每次跳转都重新做 SSRF 校验的重定向处理器。

    原实现只对初始 URL 做了 urlguard 校验，但 urllib 默认跟随 302/301，
    攻击者可用公网 URL 302 跳 http://169.254.169.254/ 绕过校验。
    """
    import urllib.request as _ur
    import urllib.error as _ue
    from utils.urlguard import validate_url as _validate

    class _SafeRedirectHandler(_ur.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            _ok, _err, _meta = _validate(newurl, resolve=True)
            if not _ok:
                raise _ue.HTTPError(newurl, code,
                                    'redirect blocked: %s' % _err, headers, fp)
            return super(_SafeRedirectHandler, self).redirect_request(
                req, fp, code, msg, headers, newurl)

    return _SafeRedirectHandler()


def downloadFile(url, filename, task_id=None):
    # 下载文件
    try:
        import urllib
        import urllib.request
        from urllib.parse import urlparse

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
        # 每次跳转重新做 SSRF 校验；超时改为局部参数（不再污染整个进程的 socket 默认超时）
        opener = urllib.request.build_opener(_make_safe_redirect_handler())
        opener.addheaders = [headers]

        resp = opener.open(url, timeout=300)
        try:
            total = resp.headers.get('Content-Length')
            total = int(total) if (total and str(total).isdigit()) else 0
        except Exception:
            total = 0

        used = 0
        last_pre = -1
        last_time = 0.0
        deadline = time.time() + DOWNLOAD_MAX_RUNTIME
        try:
            with open(filename, 'wb') as out:
                while True:
                    if time.time() > deadline:
                        writeLogs('[Error] 下载超时（超过 %s 秒），已终止!' % DOWNLOAD_MAX_RUNTIME, task_id)
                        return False
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
                    used += len(chunk)
                    now = time.time()
                    if total:
                        pre = int(100.0 * used / total)
                        # 节流：进度变化 >= 1% 或距上次写入超过 1 秒
                        if pre != last_pre or (now - last_time >= 1.0):
                            writeLogs(json.dumps({'total': total, 'used': used, 'pre': pre}), task_id)
                            last_pre = pre
                            last_time = now
        finally:
            try:
                resp.close()
            except Exception as _e:
                _log.debug('[panel_task] 关闭 HTTP 响应失败: %s', _e)

        if not yf.isAppleSystem():
            try:
                import pwd
                import grp
                uid = pwd.getpwnam('www').pw_uid
                gid = grp.getgrnam('www').gr_gid
                os.chown(filename, uid, gid)
            except Exception as _e:
                _log.debug('[panel_task] os.chown 失败，回退 execShell: %s', _e)
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
                    res = execShell(run_task['cmd'], timeout=TASK_MAX_RUNTIME, task_id=run_task['id'])
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
            yf.execShell(["systemctl", "restart", "php" + version], shell=False, timeout=yf.EXEC_SERVICE_TIMEOUT)
            if checkPHPVersion(version):
                return True

        # initd
        fpm = server_dir + '/php/init.d/php' + version
        php_path = server_dir + '/php/' + version + '/sbin/php-fpm'
        if not os.path.exists(php_path):
            if os.path.exists(fpm):
                try:
                    os.remove(fpm)
                except Exception as _e:
                    _log.debug('[panel_task] 清理 fpm 文件失败: %s', _e)
            return False

        if not os.path.exists(fpm):
            return False

        # 尝试重载服务
        yf.execShell([fpm, 'reload'], shell=False, timeout=yf.EXEC_SERVICE_TIMEOUT)
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
                except Exception as _e:
                    _log.debug('[panel_task] 清理 PHP-FPM 临时文件失败: %s -> %s', temp_file, _e)
                    
        yf.execShell([fpm, 'start'], shell=False, timeout=yf.EXEC_SERVICE_TIMEOUT)
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


# -------------------------------------- 面板自身库备份 Start ------------------------------------------ #
# 测评报告 P1 第 7 条：面板自身的 data/panel.db 此前没有任何定时备份 —— 站点/数据库有计划
# 任务备份（scripts/backup.py，由用户创建的任务触发），deploy.sh 升级前也会打包整个面板目录，
# 但日常运行中面板库本身没有任何回滚点：误删、写坏、磁盘故障都无处可退。
#
# 为什么必须用 SQLite 在线备份 API 而不是文件复制（cp / shutil.copyfile）：
# 面板库跑在 WAL 模式下（web/core/db.py 的 `PRAGMA journal_mode=WAL`），已提交但尚未
# checkpoint 的事务**只存在于 panel.db-wal 里**。实测：刚建表并提交的小库，主文件里连表
# 都没有（内容全在 -wal）。直接复制主库文件得到的是「缺最近事务」的旧快照，恢复后表现为
# 数据静默丢失；把 -wal/-shm 一起拷又会与主库版本不匹配而损坏。
# `sqlite3.Connection.backup()` 走 SQLite 自己的页级在线备份协议，不阻塞业务写入，
# 拿到的必然是一致快照（含 WAL 中已提交的内容）。
#
# 备份目录选 `yf.getBackupDir()/panel_db`（默认 /www/backup/panel_db）：
#   * 与站点备份 `<backup>/site`、数据库备份 `<backup>/database` 同源同盘，沿用用户在面板里
#     配置的 `backup_path`，一并被运维的 /www/backup 备份与迁移流程覆盖；
#   * 不放进 `data/`：备份必须与「可能被写坏的库」分开存放，否则磁盘/目录级故障会一起丢。
#
# 保留份数取 14：备份按天做（每日一份），14 份 ≈ 两周回滚窗口 —— 面板库通常只有几 MB，
# 两周的副本成本可以忽略，而「几天后才发现数据不对」是最常见的场景。
PANEL_DB_BACKUP_KEEP = 14            # 保留最近 14 份（每日一份 ≈ 两周回滚窗口）
PANEL_DB_BACKUP_INTERVAL = 86400     # 每天备份一次
PANEL_DB_BACKUP_PREFIX = 'panel_db_'
PANEL_DB_BACKUP_SUFFIX = '.db'


def getPanelDbBackupDir():
    # 面板自身库的备份目录（用户改了 backup_path 就跟着走）
    return yf.getBackupDir() + '/panel_db'


def cleanupPanelDbBackups(backup_dir, keep):
    """只清理本模块自己命名的备份，保留最近 keep 份，返回被删除的文件列表。

    **绝不用通配符删别的文件**：先按 `PANEL_DB_BACKUP_PREFIX*PANEL_DB_BACKUP_SUFFIX`
    精确匹配文件名，再确认匹配到的是普通文件（不是目录/软链），最后按修改时间
    从新到旧保留 keep 份。`keep` 之外的候选一个都不碰。
    """
    removed = []
    try:
        names = os.listdir(backup_dir)
    except OSError as e:
        _log.warning('[panel_db_backup] 无法列出备份目录 %s: %s', backup_dir, e)
        return removed

    backups = []
    for name in names:
        if not (name.startswith(PANEL_DB_BACKUP_PREFIX) and name.endswith(PANEL_DB_BACKUP_SUFFIX)):
            continue
        path = os.path.join(backup_dir, name)
        if not os.path.isfile(path):
            continue
        backups.append((os.path.getmtime(path), path))

    backups.sort(reverse=True)
    for _mtime, path in backups[keep:]:
        try:
            os.remove(path)
            removed.append(path)
        except OSError as e:
            _log.warning('[panel_db_backup] 清理过期备份失败: %s -> %s', path, e)
    return removed


def backupPanelDb(db_file=None, backup_dir=None, keep=None):
    """在线备份面板自身库，返回 `(是否成功, 备份文件路径 或 失败原因)`。

    默认落点即生产路径（`<面板>/data/panel.db` → `yf.getBackupDir()/panel_db`）；
    留出覆盖口是为了让用例/排障能在临时目录里验证，不必碰真实面板库。

    本函数**不抛异常**：它跑在通道 1 看门狗线程上，异常抛出去会打断同一轮里其它
    自愈任务，而且失败信息也不会有任何记录。失败一律以 `(False, 原因)` 返回。

    恢复步骤见 README「面板自身数据库自动备份与恢复」小节，以及本文件末尾注释。
    """
    tmp_target = None
    try:
        import sqlite3

        if keep is None:
            keep = PANEL_DB_BACKUP_KEEP
        keep = int(keep)
        if keep < 1:
            keep = 1

        db_file = db_file or (yf.getPanelDataDir() + '/panel.db')
        backup_dir = backup_dir or getPanelDbBackupDir()

        if not os.path.isfile(db_file):
            return (False, '面板库不存在: %s' % db_file)

        os.makedirs(backup_dir, exist_ok=True)
        filename = PANEL_DB_BACKUP_PREFIX + time.strftime('%Y%m%d_%H%M%S') + PANEL_DB_BACKUP_SUFFIX
        target = os.path.join(backup_dir, filename)
        tmp_target = target + '.tmp'

        # timeout=30 与面板自身的 PRAGMA busy_timeout 一致：业务写入持锁时等它，
        # 而不是立刻报 database is locked。
        src_conn = sqlite3.connect(db_file, timeout=30)
        try:
            dst_conn = sqlite3.connect(tmp_target, timeout=30)
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
        finally:
            src_conn.close()

        # 先写临时名再原子改名：中断/崩溃不会在备份目录里留下「半个库」——
        # 半截备份比没有备份更危险（看起来像备份，真恢复时才炸）。
        os.replace(tmp_target, target)
        tmp_target = None
        cleanupPanelDbBackups(backup_dir, keep)
        return (True, target)
    except Exception as e:
        if tmp_target and os.path.exists(tmp_target):
            try:
                os.remove(tmp_target)
            except OSError as _e:
                _log.debug('[panel_db_backup] 清理失败残留 %s 失败: %s', tmp_target, _e)
        return (False, '%s: %s' % (e.__class__.__name__, e))


# ---------------------------------------------------------------------------------
# PHP 运行时安全基线巡检（P0-2）
#
# 为什么必须挂在面板任务进程里：面板并不知道「用户装的是 8.2.30 还是 8.2.35」，
# 而这两个版本里只有一个能抗 CVE-2026-109618/109619。巡检每日跑一次，把结果写成
# `data/php_sec_scan.json` 快照，首页告警卡片直接读快照（不在页面请求里跑 shell）。
#
# 失败只记日志、绝不抛：巡检挂了不影响任何其它任务。
# 无 PHP 时不告警（空态），离线时用内置基线表并在结果里带上基线表日期。
# ---------------------------------------------------------------------------------
PHP_SEC_SCAN_INTERVAL = 86400        # 每天巡检一次


def getPhpSecSnapshotFile():
    # 文件名以核心模块里的常量为准（巡检与告警卡片必须读同一个文件）
    from core import php_sec_scan
    return yf.getPanelDataDir() + '/' + php_sec_scan.SNAPSHOT_FILENAME


def phpSecurityScan_step():
    try:
        from core import php_sec_scan
        data = php_sec_scan.scan(
            server_php_dir=yf.getServerDir() + '/php',
            offline=yf.extNetDisabled(),
        )
        php_sec_scan.write_snapshot(data, getPhpSecSnapshotFile())
        if data.get('alarm'):
            # 告警要进面板日志：页面卡片只在首页可见，日志是可追溯的。
            _log.warning('[php_sec_scan] %s', data.get('summary'))
            yf.writeLog('PHP安全巡检', data.get('summary') or '')
        else:
            _log.info('[php_sec_scan] %s', data.get('summary'))
    except Exception:
        # 巡检失败不得影响其它任务；保留上一次快照（比清空更接近事实）
        _log.warning('[php_sec_scan] 巡检失败: %s', yf.getTracebackInfo())
        print('phpSecurityScan:', yf.getTracebackInfo())


def panelDbBackup_step():
    # 面板自身库定时在线备份（失败只记日志并返回，绝不影响其它任务）
    try:
        ok, detail = backupPanelDb()
        if ok:
            _log.info('[panel_db_backup] 备份完成: %s', detail)
            yf.writeLog('面板数据库备份', '备份完成:' + detail)
        else:
            _log.warning('[panel_db_backup] 备份失败: %s', detail)
            yf.writeLog('面板数据库备份', '备份失败:' + detail)
    except Exception:
        print('panelDbBackup:', yf.getTracebackInfo())
# -------------------------------------- 面板自身库备份 End   ------------------------------------------ #


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
    # 面板自身库备份：与 openrestyAutoRestart_step 同为「每日一次」的长周期任务。
    # 放在通道 1 是因为 SQLite 在线备份本身很轻（面板库通常几 MB，页级备份毫秒级），
    # 而通道 2 只执行用户创建的计划任务、不接受内建任务。
    # TaskScheduler 的首次运行时刻就是启动时刻，因此每次面板任务进程启动都会先落一份
    # 快照（升级/重启后立刻有回滚点），后续按 PANEL_DB_BACKUP_INTERVAL 节流。
    watchdog_scheduler.add_task(panelDbBackup_step, PANEL_DB_BACKUP_INTERVAL)
    # PHP 运行时安全基线巡检（P0-2）：每日一次。同为长周期任务，理由同上 ——
    # 采集本身只读几个版本号（`php -v` / `dpkg-query` / `rpm`，毫秒级），
    # 但要把结果落快照供首页告警卡片读取，所以放在通道 1 的每日槽位。
    watchdog_scheduler.add_task(phpSecurityScan_step, PHP_SEC_SCAN_INTERVAL)

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

# ---------------------------------------------------------------------------------
# 恢复面板自身库（data/panel.db）—— 备份文件在 `<backup_path>/panel_db/panel_db_<时间戳>.db`
# ---------------------------------------------------------------------------------
#   1. 停面板与任务进程：`bs stop`（等价于停掉 gunicorn 与 panel_task.py）。
#      必须在面板停下的状态下替换，否则运行中的进程会继续往旧库写、并可能用旧连接
#      覆盖回去。
#   2. 处理 WAL/SHM：删掉 `data/panel.db-wal` 与 `data/panel.db-shm`（以及 `panel.db-journal`）。
#      这两个文件属于**被替换掉的旧库**，留着会被 SQLite 当成新库的未提交 WAL 回放，
#      轻则数据回退到旧状态，重则报 `database disk image is malformed`。备份文件本身
#      是一致快照，不需要、也不能搭配 -wal 使用。
#   3. 备份坏库留档（可选但强烈建议）：`mv data/panel.db data/panel.db.broken`。
#   4. 用备份覆盖：`cp <backup_path>/panel_db/panel_db_<时间戳>.db data/panel.db`，
#      并确保属主仍是面板用户（`chown www:www data/panel.db`）。
#   5. 起面板：`bs start`，随后在面板里确认站点/用户/计划任务等数据已回退到备份时刻。
#
# 手动触发一次备份：`python3 panel_task.py backup_panel_db`（失败时退出码非 0）。
# ---------------------------------------------------------------------------------

if __name__ == "__main__":
    from admin import setup
    setup.init()

    # 手动触发入口（运维/排障）：python3 panel_task.py backup_panel_db
    if len(sys.argv) > 1 and sys.argv[1] == 'backup_panel_db':
        _ok, _detail = backupPanelDb()
        print('[panel_db_backup] %s: %s' % ('ok' if _ok else 'failed', _detail))
        sys.exit(0 if _ok else 1)

    run()
    
