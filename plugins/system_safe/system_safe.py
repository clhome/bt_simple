# coding:utf-8

import sys
import io
import os
import time
import json
import re
import psutil
from datetime import datetime

sys.dont_write_bytecode = True

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

app_debug = False
if yf.isAppleSystem():
    app_debug = True


class App:

    __state = {True: '开启', False: '关闭'}
    __months = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
                'Jul': '07', 'Aug': '08', 'Sep': '09', 'Sept': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'}
    __name = '系统加固'

    __config = None
    __log_file = None

    def __init__(self):
        pass

    def getPluginName(self):
        return 'system_safe'

    def getPluginDir(self):
        return yf.getPluginDir() + '/' + self.getPluginName()

    def getServerDir(self):
        return yf.getServerDir() + '/' + self.getPluginName()

    def getInitDFile(self):
        if app_debug:
            return '/tmp/' + self.getPluginName()
        return '/etc/init.d/' + self.getPluginName()

    def getInitDTpl(self):
        path = self.getPluginDir() + "/init.d/" + self.getPluginName() + ".tpl"
        return path

    def getArgs(self):
        args = sys.argv[2:]
        tmp = {}
        if not args:
            return tmp

        # 优先尝试 JSON 解析
        try:
            return json.loads(args[0])
        except:
            pass

        for arg in args:
            try:
                t = arg.split(':', 1)
                if len(t) == 2:
                    tmp[t[0]] = t[1]
            except Exception:
                pass
        return tmp

    def checkArgs(self, data, ck=[]):
        for i in range(len(ck)):
            if not ck[i] in data:
                return (False, yf.returnJson(False, '参数:(' + ck[i] + ')没有!'))
        return (True, yf.returnJson(True, 'ok'))

    def getServerConfPath(self):
        return self.getServerDir() + "/config.json"

    def getConf(self):
        cpath = self.getServerConfPath()
        cpath_tpl = self.getPluginDir() + "/conf/config.json"

        if not os.path.exists(cpath):
            t_data = yf.readFile(cpath_tpl)
            t_data = json.loads(t_data)
            t = json.dumps(t_data)
            yf.writeFile(cpath, t)
            return t_data

        t_data = yf.readFile(cpath)
        t_data = json.loads(t_data)
        return t_data

    def writeConf(self, data):
        cpath = self.getServerConfPath()
        tmp_conf = json.dumps(data)
        yf.writeFile(cpath, tmp_conf)

    def initDreplace(self):

        file_tpl = self.getInitDTpl()
        service_path = self.getServerDir()

        initD_path = service_path + '/init.d'
        if not os.path.exists(initD_path):
            os.mkdir(initD_path)

        # init.d
        file_bin = initD_path + '/' + self.getPluginName()
        if not os.path.exists(file_bin):
            # initd replace
            content = yf.readFile(file_tpl)
            content = content.replace('{$SERVER_PATH}', service_path)
            yf.writeFile(file_bin, content)
            yf.execShell('chmod +x ' + file_bin)

        # systemd
        # /usr/lib/systemd/system
        systemDir = yf.systemdCfgDir()
        systemService = systemDir + '/system_safe.service'
        systemServiceTpl = self.getPluginDir() + '/init.d/system_safe.service.tpl'
        if os.path.exists(systemDir) and not os.path.exists(systemService):
            se_content = yf.readFile(systemServiceTpl)
            se_content = se_content.replace('{$SERVER_PATH}', service_path)
            yf.writeFile(systemService, se_content)
            yf.execShell('systemctl daemon-reload')

        return file_bin

    def ssOp(self, method):
        file = self.initDreplace()

        if not yf.isAppleSystem():
            data = yf.execShell('systemctl ' + method +
                                ' ' + self.getPluginName())
            if data[1] == '':
                return 'ok'
            return 'fail'

        data = yf.execShell(file + ' ' + method)
        if data[1] == '':
            return 'ok'
        return 'fail'

    # def status(self):
    #     data = self.getConf()
    #     if not data['open']:
    #         return 'stop'
    #     return 'start'

    def status(self):
        pid_file = self.getServerDir() + '/system_safe.pid'
        if os.path.exists(pid_file):
            try:
                pid = int(yf.readFile(pid_file).strip())
                if psutil.pid_exists(pid):
                    return 'start'
            except:
                pass

        data = yf.execShell(
            'ps -ef|grep "system_safe/system_safe.py bg_start" | grep -v grep | awk \'{print $2}\'')
        if data[0] == '':
            return 'stop'
        return 'start'

    def start(self):
        return self.ssOp('start')

    def writeLog(self, msg):
        yf.writeDbLog(self.__name, msg)

    __limit = 30
    __vmsize = 1048576 * 100
    __wlist = None
    __wslist = None
    __elist = None
    __last_pid_count = 0
    __last_return_time = 0  # 上次返回结果的时间
    __return_timeout = 360

    def getSysProcess(self, get):
        # 是否直接从属性中获取
        stime = time.time()
        if stime - self.__last_return_time < self.__return_timeout:
            if self.__sys_process:
                return True
        self.__last_return_time = stime

        # 本地是否存在系统进程白名单文件
        config_file = self.getServerDir() + '/sys_process.json'
        is_force = False
        if not os.path.exists(config_file):
            yf.writeFile(config_file, json.dumps([]))
            is_force = True

        data = json.loads(yf.readFile(config_file))
        self.__sys_process = data
        return True

    # 取进程白名单列表
    def getProcessWhite(self, get):
        data = self.getConf()
        return data['process']['process_white']

    # 取进程关键词
    def getProcessRule(self, get):
        data = self.getConf()
        return data['process']['process_white_rule']

    # 取进程排除名单
    def getProcessExclude(self, get):
        data = self.getConf()
        return data['process']['process_exclude']

    # 检查白名单
    def checkWhite(self, name):
        if not self.__elist:
            self.__elist = self.getProcessExclude(None)
        if not self.__wlist:
            self.__wlist = self.getProcessWhite(None)
        if not self.__wslist:
            self.__wslist = self.getProcessRule(None)
        self.getSysProcess(None)
        if name in ['yf', 'mw', 'dnf', 'yum',
                    'apt', 'apt-get', 'grep',
                    'awk', 'python', 'node', 'php', 'mysqld',
                    'httpd', 'openresty', 'wget', 'curl', 'openssl',
                    'rspamd', 'supervisord', 'tlsmgr']:
            return True
        if name in self.__elist:
            return True
        if name in self.__sys_process:
            return True
        if name in self.__wlist:
            return True
        for key in self.__wslist:
            if name.find(key) != -1:
                return True
        return False

    def checkMainProccess(self, pid):
        if pid < 1100:
            return
        fname = '/proc/' + str(pid) + '/comm'
        if not os.path.exists(fname):
            return
        name = yf.readFile(fname).strip()
        is_num_name = re.match(r"^\d+$", name)
        if not is_num_name:
            if self.checkWhite(name):
                return
        try:
            p = psutil.Process(pid)
            percent = p.cpu_percent(interval=0.1)
            vm = p.memory_info().vms
            if percent > self.__limit or vm > self.__vmsize:
                cmdline = ' '.join(p.cmdline())
                if cmdline.find('/www/server/cron') != -1:
                    return
                if cmdline.find('/www/server') != -1:
                    return
                if name.find('kworker') != -1 or name.find('mw_') == 0:
                    return
                p.kill()
                self.writeLog("已强制结束异常进程:[%s],PID:[%s],CPU:[%s],CMD:[%s]" % (
                    name, pid, percent, cmdline))
        except:
            print(yf.getTracebackInfo())
            return

    def checkMain(self):
        pids = psutil.pids()
        pid_count = len(pids)
        if self.__last_pid_count == pid_count:
            return
        self.__last_pid_count = pid_count

        try:
            for pid in pids:
                self.checkMainProccess(pid)
        except Exception as e:
            print(yf.getTracebackInfo())

    def processTask(self):

        if not self.__config:
            self.__config = self.getConf()
        if not self.__config:
            return

        is_open_val = 1 if self.__config.get('open', False) else 0
        self.setOpen(is_open_val)
        is_open = 0
        while True:
            if self.__config['process']['open']:
                is_open += 1
                self.checkMain()

            if is_open > 60:
                self.__config = self.getConf()
                is_open = 0
            time.sleep(1)

    def bg_start(self):
        pid_file = self.getServerDir() + '/system_safe.pid'
        yf.writeFile(pid_file, str(os.getpid()))
        try:
            self.processTask()
        except Exception as e:
            print(yf.getTracebackInfo())
            self.bg_stop()
            self.writeLog('【{}】系统加固监控进程启动异常关闭'.format(yf.getDate()))
        return 'ok'

    def bg_stop(self):
        pid_file = self.getServerDir() + '/system_safe.pid'
        if os.path.exists(pid_file):
            try:
                os.remove(pid_file)
            except:
                pass
        try:
            self.setOpen(0)
        except Exception as e:
            print(yf.getTracebackInfo())
            print('【{}】系统加固监控进程停止异常关闭'.format(yf.getDate()))
        return ''

    def stop(self):
        return self.ssOp('stop')

    def restart(self):
        return self.ssOp('restart')

    def reload(self):
        return self.ssOp('reload')

    def initd_status(self):
        if yf.isAppleSystem():
            return "Apple Computer does not support"
        shell_cmd = 'systemctl status %s | grep loaded | grep "enabled;"' % (
            self.getPluginName())
        data = yf.execShell(shell_cmd)
        if data[0] == '':
            return 'fail'
        return 'ok'

    def initd_install(self):
        if yf.isAppleSystem():
            return "Apple Computer does not support"

        yf.execShell('systemctl enable ' + self.getPluginName())
        return 'ok'

    def initd_uninstall(self):
        if yf.isAppleSystem():
            return "Apple Computer does not support"

        yf.execShell('systemctl disable ' + self.getPluginName())
        return 'ok'

    def __lock_path(self, info):
        try:
            if not os.path.exists(info['path']):
                return False
            if not re.match(r'^[a-zA-Z0-9_\-\./\s]+$', info['path']) or '..' in info['path']:
                return False
            if info['chattr'] not in ['i', 'a']:
                return False

            if info['d_mode']:
                os.chmod(info['path'], info['d_mode'])
            if info['chattr']:
                cmd = 'chattr -R +%s "%s"' % (info['chattr'], info['path'])
                yf.execShell(cmd)
            return True
        except Exception as e:

            return False

    def __unlock_path(self, info):
        try:
            if not os.path.exists(info['path']):
                return False
            if not re.match(r'^[a-zA-Z0-9_\-\./\s]+$', info['path']) or '..' in info['path']:
                return False
            if info['chattr'] not in ['i', 'a']:
                return False

            if info['chattr']:
                cmd = 'chattr -R -%s "%s"' % (info['chattr'], info['path'])
                yf.execShell(cmd)

            if info['s_mode']:
                os.chmod(info['path'], info['s_mode'])
            return True
        except Exception as e:
            yf.getTracebackInfo()
            return False

    def __set_safe_state(self, paths, lock=False):
        for path_info in paths:
            if lock:
                self.__lock_path(path_info)
            else:
                self.__unlock_path(path_info)
        return True

    # 转换时间格式
    def __to_date(self, date_str):
        tmp = re.split(r'\s+', date_str)
        s_date = str(datetime.now().year) + '-' + \
            self.__months.get(tmp[0]) + '-' + tmp[1] + ' ' + tmp[2]
        time_array = time.strptime(s_date, "%Y-%m-%d %H:%M:%S")
        time_stamp = int(time.mktime(time_array))
        return time_stamp

    def conf(self):
        data = self.getConf()
        return yf.returnJson(True, 'ok', data)

    def setOpen(self, is_open=-1):
        cpath = self.getServerConfPath()
        data = self.getConf()
        if is_open != -1:
            if is_open == 0:
                data['open'] = False
            else:
                data['open'] = True

        for s_name in data.keys():
            if type(data[s_name]) == bool:
                continue
            if not 'name' in data[s_name]:
                continue
            if not 'paths' in data[s_name]:
                continue
            s_name_status = False
            if data['open']:
                s_name_status = True
            # print(data[s_name]['paths'], data[s_name]['open'])
            self.__set_safe_state(data[s_name]['paths'], s_name_status)
        msg = '已[%s]系统加固功能' % self.__state[data['open']]
        self.writeLog(msg)
        self.writeConf(data)

    def set_safe_status(self):
        args = self.getArgs()
        data = self.checkArgs(args, ['tag', 'status'])
        if not data[0]:
            return data[1]

        tag = args['tag']
        status = args['status']

        # 转换格式
        if status == 'false':
            status = False
        if status == 'true':
            status = True

        if not tag in ['bin', 'service', 'home', 'user', 'bin', 'cron', 'process']:
            return yf.returnJson(False, '不存在此配置[{}]!'.format(tag))

        data = self.getConf()
        data[tag]['open'] = status
        self.writeConf(data)
        return yf.returnJson(True, '设置成功')

    # 取文件或目录锁定状态
    def __get_path_state(self, path):
        if not path or not re.match(r'^[a-zA-Z0-9_\-\./\s]+$', path) or '..' in path:
            return False

        if not os.path.exists(path):
            return 'i'
        if os.path.isfile(path):
            shell_cmd = 'lsattr "%s"|awk \'{print $1}\'' % path
        else:
            shell_cmd = 'lsattr "%s/" |grep "%s$"|awk \'{{print $1}}\'' % (
                os.path.dirname(path), os.path.basename(path))
        result = yf.execShell(shell_cmd)[0]
        if result.find('-i-') != -1:
            return 'i'
        if result.find('-a-') != -1:
            return 'a'
        return False

    # 遍历当前防护状态
    def __list_safe_state(self, paths):
        result = []
        for i in range(len(paths)):
            if not os.path.exists(paths[i]['path']):
                continue
            if os.path.islink(paths[i]['path']):
                continue
            mstate = self.__get_path_state(paths[i]['path'])
            paths[i]['state'] = mstate == paths[i]['chattr']
            paths[i]['s_mode'] = oct(paths[i]['s_mode'])
            paths[i]['d_mode'] = oct(paths[i]['d_mode'])
            result.append(paths[i])
        return result

    def get_safe_data(self):

        args = self.getArgs()
        check = self.checkArgs(args, ['tag'])
        if not check[0]:
            return check[1]

        tag = args['tag']
        if not tag in ['bin', 'service', 'home', 'user', 'bin', 'cron']:
            return yf.returnJson(False, '不存在此配置[{}]!'.format(tag))

        cpath = self.getServerConfPath()
        data = self.getConf()
        tmp = data[tag]
        tmp['paths'] = self.__list_safe_state(tmp['paths'])
        return yf.returnJson(True, {'open': data['open']}, tmp)

    def get_process_data(self):
        data = self.getConf()
        tmp = data['process']
        return yf.returnJson(True, {'open': data['open']}, tmp)

     # 添加防护对象
    def add_safe_path(self):
        args = self.getArgs()
        check = self.checkArgs(args, ['tag', 'path', 'chattr', 'd_mode'])
        if not check[0]:
            return check[1]

        path = args['path']
        tag = args['tag']
        chattr = args['chattr']
        d_mode = args['d_mode']
        if path[-1] == '/':
            path = path[:-1]

        if not path or not re.match(r'^[a-zA-Z0-9_\-\./\s]+$', path) or '..' in path:
            return yf.returnJson(False, '非法的防护路径格式，添加失败！')
        if chattr not in ['i', 'a']:
            return yf.returnJson(False, '非法的属性设置！')

        if not os.path.exists(path):
            return yf.returnJson(False, '指定文件或目录不存在!')
        data = self.getConf()

        for m_path in data[tag]['paths']:
            if path == m_path['path']:
                return yf.returnJson(False, '指定文件或目录已经添加过了!')

        path_info = {}
        path_info['path'] = path
        path_info['chattr'] = chattr
        path_info['s_mode'] = int(oct(os.stat(path).st_mode)[-3:], 8)
        if d_mode != '':
            path_info['d_mode'] = int(d_mode, 8)
        else:
            path_info['d_mode'] = path_info['s_mode']

        data[tag]['paths'].insert(0, path_info)
        if 'paths' in data[tag]:
            yf.execShell('chattr -R -%s "%s"' %
                         (path_info['chattr'], path_info['path']))
            if data['open']:
                self.__set_safe_state([path_info], data[tag]['open'])
        msg = '添加防护对象[%s]到[%s]' % (path, data[tag]['name'])
        self.writeLog(msg)
        self.writeConf(data)
        return yf.returnJson(True, msg)

    # 添加进程白名单
    def add_process_white(self):
        args = self.getArgs()
        check = self.checkArgs(args, ['process_name'])
        if not check[0]:
            return check[1]

        data = self.getConf()
        process_name = args['process_name']
        if process_name in data['process']['process_white']:
            return yf.returnJson(False, '指定进程名已在白名单')
        data['process']['process_white'].insert(0, process_name)
        self.writeConf(data)
        msg = '添加进程名[%s]到进程白名单' % process_name
        self.writeLog(msg)
        self.restart()
        return yf.returnJson(True, msg)

    def del_safe_proccess_name(self):
        args = self.getArgs()
        check = self.checkArgs(args, ['tag', 'index'])
        if not check[0]:
            return check[1]

        tag = args['tag']
        index = int(args['index'])

        cpath = self.getServerConfPath()
        data = self.getConf()

        del(data[tag]['process_white'][index])
        t = json.dumps(data)
        yf.writeFile(cpath, t)
        return yf.returnJson(True, '删除成功')

    def del_safe_path(self):
        args = self.getArgs()
        check = self.checkArgs(args, ['tag', 'index'])
        if not check[0]:
            return check[1]

        tag = args['tag']
        index = int(args['index'])

        cpath = self.getServerConfPath()
        data = self.getConf()

        del(data[tag]['paths'][index])
        t = json.dumps(data)
        yf.writeFile(cpath, t)
        return yf.returnJson(True, '删除成功')

    def get_log_title(self, log_name):
        log_name = log_name.replace('.1', '')
        if log_name in ['auth.log', 'secure'] or log_name.find('auth.') == 0:
            return '授权日志'
        if log_name in ['dmesg'] or log_name.find('dmesg') == 0:
            return '内核缓冲区日志'
        if log_name in ['syslog'] or log_name.find('syslog') == 0:
            return '系统警告/错误日志'
        if log_name in ['btmp']:
            return '失败的登录记录'
        if log_name in ['utmp', 'wtmp']:
            return '登录和重启记录'
        if log_name in ['lastlog']:
            return '用户最后登录'
        if log_name in ['yum.log']:
            return 'yum包管理器日志'
        if log_name in ['anaconda.log']:
            return 'Anaconda日志'
        if log_name in ['dpkg.log']:
            return 'dpkg日志'
        if log_name in ['daemon.log']:
            return '系统后台守护进程日志'
        if log_name in ['boot.log']:
            return '启动日志'
        if log_name in ['kern.log']:
            return '内核日志'
        if log_name in ['maillog', 'mail.log']:
            return '邮件日志'
        if log_name.find('Xorg') == 0:
            return 'Xorg日志'
        if log_name in ['cron.log']:
            return '定时任务日志'
        if log_name in ['alternatives.log']:
            return '更新替代信息'
        if log_name in ['debug']:
            return '调试信息'
        if log_name.find('apt') == 0:
            return 'apt-get相关日志'
        if log_name.find('installer') == 0:
            return '系统安装相关日志'
        if log_name in ['messages']:
            return '综合日志'
        return '{}日志'.format(log_name.split('.')[0])

    def get_sys_logfiles(self):
        log_dir = '/var/log'
        log_files = []
        for log_file in os.listdir(log_dir):

            log_suffix = log_file.split('.')[-1:]
            if log_suffix[0] in ['gz', 'xz', 'bz2', 'asl']:
                continue

            if log_file in ['.', '..', 'faillog', 'fontconfig.log', 'unattended-upgrades', 'tallylog']:
                continue

            # print(log_suffix)
            filename = os.path.join(log_dir, log_file)
            if os.path.isfile(filename):
                file_size = os.path.getsize(filename)
                if not file_size:
                    continue

                tmp = {
                    'name': log_file,
                    'size': file_size,
                    'log_file': filename,
                    'title': self.get_log_title(log_file),
                    'uptime': os.path.getmtime(filename)
                }

                log_files.append(tmp)
            else:
                for next_name in os.listdir(filename):
                    if next_name[-3:] in ['.gz', '.xz']:
                        continue
                    next_file = os.path.join(filename, next_name)
                    if not os.path.isfile(next_file):
                        continue
                    file_size = os.path.getsize(next_file)
                    if not file_size:
                        continue
                    log_name = '{}/{}'.format(log_file, next_name)
                    tmp = {
                        'name': log_name,
                        'size': file_size,
                        'log_file': next_file,
                        'title': self.get_log_title(log_name),
                        'uptime': os.path.getmtime(next_file)
                    }
                    log_files.append(tmp)
        log_files = sorted(log_files, key=lambda x: x['name'], reverse=True)
        return yf.returnJson(True, 'ok', log_files)

    def get_last(self, log_name):
        # 获取日志
        cmd = '''LANG=en_US.UTF-8 last -n 200 -x -f {} |grep -v 127.0.0.1|grep -v " begins"'''.format(
            '/var/log/' + log_name)
        result = yf.execShell(cmd)
        lastlog_list = []
        for _line in result[0].split("\n"):
            if not _line:
                continue
            tmp = {}
            sp_arr = _line.split()
            tmp['用户'] = sp_arr[0]
            if sp_arr[0] == 'runlevel':
                tmp['来源'] = sp_arr[4]
                tmp['端口'] = ' '.join(sp_arr[1:4])
                tmp['时间'] = self.__to_date3(
                    ' '.join(sp_arr[5:])) + ' ' + ' '.join(sp_arr[-2:])
            elif sp_arr[0] in ['reboot', 'shutdown']:
                tmp['来源'] = sp_arr[3]
                tmp['端口'] = ' '.join(sp_arr[1:3])
                if sp_arr[-3] == '-':
                    tmp['时间'] = self.__to_date3(
                        ' '.join(sp_arr[4:])) + ' ' + ' '.join(sp_arr[-3:])
                else:
                    tmp['时间'] = self.__to_date3(
                        ' '.join(sp_arr[4:])) + ' ' + ' '.join(sp_arr[-2:])
            elif sp_arr[1] in ['tty1', 'tty', 'tty2', 'tty3', 'hvc0', 'hvc1', 'hvc2'] or len(sp_arr) == 9:
                tmp['来源'] = ''
                tmp['端口'] = sp_arr[1]
                tmp['时间'] = self.__to_date3(
                    ' '.join(sp_arr[2:])) + ' ' + ' '.join(sp_arr[-3:])
            else:
                tmp['来源'] = sp_arr[2]
                tmp['端口'] = sp_arr[1]
                tmp['时间'] = self.__to_date3(
                    ' '.join(sp_arr[3:])) + ' ' + ' '.join(sp_arr[-3:])

            # tmp['_line'] = _line
            lastlog_list.append(tmp)
        # lastlog_list = sorted(lastlog_list,key=lambda x:x['时间'],reverse=True)
        return yf.returnJson(True, 'ok!', lastlog_list)

    def get_lastlog(self):
        cmd = '''LANG=en_US.UTF-8 lastlog|grep -v Username'''
        result = yf.execShell(cmd)
        lastlog_list = []
        for _line in result[0].split("\n"):
            if not _line:
                continue
            tmp = {}
            sp_arr = _line.split()
            tmp['用户'] = sp_arr[0]
            # tmp['_line'] = _line
            if _line.find('Never logged in') != -1:
                tmp['最后登录时间'] = '0'
                tmp['最后登录来源'] = '-'
                tmp['最后登录端口'] = '-'
                lastlog_list.append(tmp)
                continue
            tmp['最后登录来源'] = sp_arr[2]
            tmp['最后登录端口'] = sp_arr[1]
            tmp['最后登录时间'] = self.__to_date2(' '.join(sp_arr[3:]))

            lastlog_list.append(tmp)
        lastlog_list = sorted(lastlog_list, key=lambda x: x[
                              '最后登录时间'], reverse=True)
        for i in range(len(lastlog_list)):
            if lastlog_list[i]['最后登录时间'] == '0':
                lastlog_list[i]['最后登录时间'] = '从未登录过'
        return yf.returnJson(True, 'ok!', lastlog_list)

    def get_sys_log_with_name(self, log_name):
        if not log_name or not re.match(r'^[a-zA-Z0-9_\-\./]+$', log_name):
            return yf.returnJson(False, '非法的日志文件名，拒绝访问！')

        log_dir = '/var/log'
        log_file = os.path.abspath(log_dir + '/' + log_name)
        if not log_file.startswith(log_dir):
            return yf.returnJson(False, '越界访问，拒绝读取！')

        if log_name in ['wtmp', 'btmp', 'utmp'] or log_name.find('wtmp') == 0 or log_name.find('btmp') == 0 or log_name.find('utmp') == 0:
            return self.get_last(log_name)

        if log_name.find('lastlog') == 0:
            return self.get_lastlog()

        if log_name.find('sa/sa') == 0:
            if log_name.find('sa/sar') == -1:
                return yf.execShell('sar -f "/var/log/%s"' % log_name)[0]

        if not os.path.exists(log_file):
            return yf.returnJson(False, '日志文件不存在!')
        result = yf.getLastLine(log_file, 100)
        log_list = []
        is_string = True
        for _line in result.split("\n"):
            if not _line.strip():
                continue
            if log_name.find('sa/sa') == -1:
                if _line[:3] in self.__months:
                    _msg = _line[16:]
                    _tmp = _msg.split(": ")
                    _act = ''
                    if len(_tmp) > 1:
                        _act = _tmp[0]
                        _msg = _tmp[1]
                    else:
                        _msg = _tmp[0]
                    _line = {
                        "时间": self.__to_date4(_line[:16].strip()),
                        "角色": _act,
                        "事件": _msg
                    }
                    is_string = False
                elif _line[:2] in ['19', '20', '21', '22', '23', '24']:
                    _msg = _line[19:]
                    _tmp = _msg.split(" ")
                    _act = _tmp[1]
                    _msg = ' '.join(_tmp[2:])
                    _line = {
                        "时间": _line[:19].strip(),
                        "角色": _act,
                        "事件": _msg
                    }
                    is_string = False
                elif log_name.find('alternatives') == 0:
                    _tmp = _line.split(": ")
                    _last = _tmp[0].split(" ")
                    _act = _last[0]
                    _msg = ' '.join(_tmp[1:])
                    _line = {
                        "时间": ' '.join(_last[1:]).strip(),
                        "角色": _act,
                        "事件": _msg
                    }
                    is_string = False
                else:
                    if not is_string:
                        if type(_line) != dict:
                            continue

            log_list.append(_line)
        try:
            # if len(log_list) > 1:
            #     if type(log_list[0]) != type(log_list[1]):
            #         del(log_list[0])
            # log_list = sorted(log_list,key=lambda x:x['时间'],reverse=True)
            # return log_list

            _string = []
            _dict = []
            _list = []
            for _line in log_list:
                if isinstance(_line, str):
                    _string.append(_line.strip())
                elif isinstance(_line, dict):
                    _dict.append(_line)
                elif isinstance(_line, list):
                    _list.append(_line)
                else:
                    continue
            _str_len = len(_string)
            _dict_len = len(_dict)
            _list_len = len(_list)
            if _str_len > _dict_len + _list_len:
                return "\n".join(_string)
            elif _dict_len > _str_len + _list_len:
                return yf.returnJson(True, 'ok!', _dict)
            else:
                return yf.returnJson(True, 'ok!', _list)

        except:
            data = '\n'.join(log_list)
            return yf.returnJson(True, 'ok!', data)

    def get_sys_log(self):
        args = self.getArgs()
        check = self.checkArgs(args, ['log_name'])
        if not check[0]:
            return check[1]

        log_name = args['log_name']
        return self.get_sys_log_with_name(log_name)

    def __to_date2(self, date_str):
        tmp = date_str.split()
        s_date = str(tmp[-1]) + '-' + self.__months.get(tmp[1],
                                                        tmp[1]) + '-' + tmp[2] + ' ' + tmp[3]
        return s_date

    def __to_date3(self, date_str):
        tmp = date_str.split()
        s_date = str(datetime.now().year) + '-' + \
            self.__months.get(tmp[1], tmp[1]) + '-' + tmp[2] + ' ' + tmp[3]
        return s_date

    def __to_date4(self, date_str):
        tmp = date_str.split()
        s_date = str(datetime.now().year) + '-' + \
            self.__months.get(tmp[0], tmp[0]) + '-' + tmp[1] + ' ' + tmp[2]
        return s_date

    def op_log(self):
        args = self.getArgs()
        check = self.checkArgs(args, ['p'])
        if not check[0]:
            return check[1]

        p = int(args['p'])
        limit = 10
        start = (p - 1) * limit

        _list = yf.M('logs').field(
            'id,type,log,addtime').where('type=?', (self.__name,)).limit(str(start) + ',' + str(limit)).order('id desc').select()
        data = {}
        data['data'] = _list
        count = yf.M('logs').where('type=?', (self.__name,)).count()
        _page = {}
        _page['count'] = count
        _page['tojs'] = 'ssOpLogList'
        _page['p'] = p
        data['page'] = yf.getPage(_page)
        return yf.returnJson(True, 'ok', data)


def get_sys_log(args):
    classApp = App()
    data = classApp.get_sys_log_with_name(args['log_name'])
    return data

if __name__ == "__main__":
    func = sys.argv[1]
    classApp = App()
    try:
        data = eval("classApp." + func + "()")
        print(data)
    except Exception as e:
        print(yf.getTracebackInfo())
