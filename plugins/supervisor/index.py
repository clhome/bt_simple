# coding:utf-8

import sys
import io
import os
import time
import re
import json

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'supervisor'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getConf():
    path = getServerDir() + "/supervisor.conf"
    return path


def getConfTpl():
    path = getPluginDir() + "/conf/supervisor.conf"
    return path


def getSubConfDir():
    return getServerDir() + "/conf.d"


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)
    if args_len == 0:
        return tmp

    # 尝试优先以 JSON 字符串解析整个参数
    first_arg = args[0].strip()
    if (first_arg.startswith('{') and first_arg.endswith('}')) or (first_arg.startswith('[') and first_arg.endswith(']')):
        try:
            return json.loads(first_arg)
        except Exception:
            pass

    # 向下兼容：解析普通键值对，仅分割第一个冒号，防止值里包含冒号时被截断
    if args_len == 1:
        t = args[0].strip('{').strip('}')
        t = t.split(':', 1)
        if len(t) >= 2:
            tmp[t[0].strip('"').strip("'")] = t[1].strip('"').strip("'")
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':', 1)
            if len(t) >= 2:
                tmp[t[0].strip('"').strip("'")] = t[1].strip('"').strip("'")

    return tmp


def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '参数:(' + ck[i] + ')没有!'))
    return (True, yf.returnJson(True, 'ok'))


def checkSafeName(name):
    """
    守护进程名称安全性拦截：只允许英文字母、数字、下划线、中划线和点。
    """
    if not name:
        return False
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', name):
        return False
    return True


def checkSafeFile(filepath):
    """
    配置文件沙盒边界防护：必须在插件的子配置文件目录内，禁止目录穿越
    """
    if not filepath:
        return False
    filepath = os.path.abspath(filepath)
    allowed_dir = os.path.abspath(getServerDir() + '/conf.d')
    return filepath.startswith(allowed_dir) and '..' not in filepath


def getSupervisorctlBin():
    """
    智能定位 supervisorctl 命令路径：
    1. 优先从面板所在的虚拟环境中获取；
    2. 其次通过 which 查找系统全局路径；
    3. 最后退回为默认的 supervisorctl 执行。
    """
    activate_file = yf.getPanelDir() + '/bin/activate'
    if os.path.exists(activate_file):
        bin_path = yf.execShell('source ' + activate_file + ' && which supervisorctl')[0].strip()
        if bin_path and os.path.exists(bin_path):
            return bin_path
    bin_path = yf.execShell('which supervisorctl')[0].strip()
    if bin_path:
        return bin_path
    return 'supervisorctl'


def status():
    data = yf.execShell(
        "ps -ef|grep supervisor | grep -v grep | grep -v index.py | awk '{print $2}'")
    if data[0] == '':
        return 'stop'
    return 'start'


def initDreplace():
    confD = getServerDir() + "/conf.d"
    conf = getServerDir() + "/supervisor.conf"
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/supervisor.service'
    systemServiceTpl = getPluginDir() + '/init.d/supervisor.service'

    service_path = yf.getServerDir()

    if not os.path.exists(confD):
        os.mkdir(confD)

    if not os.path.exists(conf):
        # config replace
        user = 'root'
        if yf.isAppleSystem():
            cmd = "who | sed -n '2, 1p' |awk '{print $1}'"
            user = yf.execShell(cmd)[0].strip()

        conf_content = yf.readFile(getConfTpl())
        conf_content = conf_content.replace('{$SERVER_PATH}', service_path)
        conf_content = conf_content.replace('{$OS_USER}', user)
        yf.writeFile(conf, conf_content)

    if os.path.exists(systemDir) and not os.path.exists(systemService):
        activate_file = yf.getPanelDir() + '/bin/activate'
        if os.path.exists(activate_file):
            supervisord_bin = yf.execShell(
                'source ' + activate_file + '&& which supervisord')[0].strip()
        else:
            supervisord_bin = yf.execShell('which supervisord')[0].strip()

        se_content = yf.readFile(systemServiceTpl)
        se_content = se_content.replace('{$SERVER_PATH}', service_path)
        se_content = se_content.replace('{$SUP_BIN}', supervisord_bin)
        yf.writeFile(systemService, se_content)
        yf.execShell('systemctl daemon-reload')

    return True


def supOp(method):
    initDreplace()

    if not yf.isAppleSystem():
        data = yf.execShell('systemctl ' + method + ' supervisor')
        if data[1] == '':
            return 'ok'
        return data[1]

    if method in ('reload', 'restart'):
        return 'ok'

    cmd = 'supervisord -c ' + getServerDir() + '/supervisor.conf'
    if method == 'stop':
        cmd = "ps -ef|grep supervisor | grep -v grep | grep -v index.py | awk '{print $2}'|xargs kill"
    data = yf.execShell(cmd)
    if data[1] == '':
        return 'ok'
    return data[1]


def start():
    return supOp('start')


def stop():
    return supOp('stop')


def restart():
    return supOp('restart')


def reload():
    return supOp('reload')


def initdStatus():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    shell_cmd = 'systemctl status supervisor | grep loaded | grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    yf.execShell('systemctl enable supervisor')
    return 'ok'


def initdUinstall():
    if not app_debug:
        if yf.isAppleSystem():
            return "Apple Computer does not support"

    # 修复 diable 为 disable 的拼写错误
    yf.execShell('systemctl disable supervisor')
    return 'ok'


def getSupList():
    data = {}

    statusFile = getServerDir() + "/status.txt"
    supCtl = getSupervisorctlBin()
    cmd = "%s -c %s/supervisor.conf update; %s -c %s/supervisor.conf status > %s" % (supCtl, getServerDir(), supCtl, getServerDir(), statusFile)
    yf.execShell(cmd)

    if not os.path.exists(statusFile):
        data['data'] = []
        return yf.getJson(data)

    with open(statusFile, "r") as fr:
        lines = fr.readlines()

    array_list = []
    process_list = []
    for r in lines:
        array = r.split()
        if array and len(array) >= 2:
            d = dict()
            program = array[0].split(':')[0]
            if program in process_list:
                continue
            process_list.append(program)
            d["program"] = program
            d["runStatus"] = array[1]
            if array[1] == "RUNNING":
                d["status"] = "1"
                d["pid"] = array[3][:-1] if len(array) >= 4 else ""
            else:
                d["status"] = "0"
                d["pid"] = ""
            file = getServerDir() + '/conf.d/' + program + ".ini"
            if not os.path.exists(file):
                continue
            try:
                with open(file, "r") as fr_ini:
                    infos = fr_ini.readlines()
                for line in infos:
                    if "command=" in line.strip():
                        d["command"] = "子配置查看"
                    if "user=" in line.strip():
                        d["user"] = line.strip().split('=')[1]
                    if "priority=" in line.strip():
                        d["priority"] = line.strip().split('=')[1]
                    if "numprocs=" in line.strip():
                        d["numprocs"] = line.strip().split('=')[1]
            except Exception:
                pass
            array_list.append(d)

    data = {}
    data['data'] = array_list
    return yf.getJson(data)


def confDList():
    confd_dir = getServerDir() + '/conf.d'
    clist = os.listdir(confd_dir)
    array_list = []
    for x in range(len(clist)):
        t = {}
        t['name'] = clist[x]
        array_list.append(t)

    data = {}
    data['data'] = array_list
    return yf.getJson(data)


def confDlistTraceLog():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not checkSafeName(name):
        return yf.returnJson(False, '进程名称不合法！')

    confd_dir = getServerDir() + '/conf.d/' + name
    if not checkSafeFile(confd_dir):
        return yf.returnJson(False, '非法的配置文件路径！')

    content = yf.readFile(confd_dir)
    rep = r'stdout_logfile\s*=\s*(.*)'
    tmp = re.search(rep, content)
    return tmp.groups()[0].strip()


def confDlistErrorLog():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not checkSafeName(name):
        return yf.returnJson(False, '进程名称不合法！')

    confd_dir = getServerDir() + '/conf.d/' + name
    if not checkSafeFile(confd_dir):
        return yf.returnJson(False, '非法的配置文件路径！')

    content = yf.readFile(confd_dir)
    rep = r'stderr_logfile\s*=\s*(.*)'
    tmp = re.search(rep, content)
    return tmp.groups()[0].strip()


def getUserListData():
    """
    优雅重构：以 Python 原生方式安全、高效读取用户列表，摆脱外部 Shell 交互与临时文件创建
    """
    users = []
    passwd_path = '/etc/passwd'
    if os.path.exists(passwd_path):
        try:
            with open(passwd_path, 'r') as fr:
                users = fr.readlines()
        except Exception:
            pass

    user_list = []
    special = ["bin", "daemon", "adm", "lp", "shutdown", "halt", "mail", "operator", "games",
               "avahi-autoipd", "systemd-bus-proxy", "systemd-network", "dbus", "polkitd", "tss", "ntp"]
    for u in users:
        u = u.strip()
        if not u or u.startswith('#'):
            continue
        parts = re.split(':', u)
        if len(parts) > 0:
            user = parts[0]
            if user in special:
                continue
            user_list.append(user)

    if yf.isAppleSystem() or len(user_list) == 0:
        cmd = "who | sed -n '2, 1p' |awk '{print $1}'"
        user = yf.execShell(cmd)[0].strip()
        if user and user not in user_list:
            user_list.append(user)

    user_list = list(set(user_list))
    user_list.sort()
    return user_list


def getUserList():
    user_list = getUserListData()
    return yf.getJson(user_list)


def addJob():
    args = getArgs()
    data = checkArgs(args, ['name', 'user', 'path', 'command', 'numprocs'])
    if not data[0]:
        return data[1]

    program = args['name']
    if not checkSafeName(program):
        return yf.returnJson(False, '进程名称不合法！仅支持英文字母、数字、下划线、中划线和点。')

    command = args['command']
    path = args['path']
    numprocs = args['numprocs']
    user = args['user']

    log_dir = getServerDir() + '/log/'

    w_body = ""
    w_body += "[program:" + program + "]" + "\n"
    w_body += "command=" + command + "\n"
    w_body += "directory=" + path + "\n"
    w_body += "autorestart=true" + "\n"
    w_body += "startsecs=3" + "\n"
    w_body += "startretries=3" + "\n"
    w_body += "stdout_logfile=" + log_dir + program + ".out.log" + "\n"
    w_body += "stderr_logfile=" + log_dir + program + ".err.log" + "\n"
    w_body += "stdout_logfile_maxbytes=1MB" + "\n"
    w_body += "stderr_logfile_maxbytes=1MB" + "\n"
    w_body += "user=" + user + "\n"
    w_body += "priority=999" + "\n"
    w_body += "numprocs={0}".format(numprocs) + "\n"
    w_body += "process_name=%(program_name)s_%(process_num)02d"

    dstFile = getSubConfDir() + "/" + program + '.ini'
    if not checkSafeFile(dstFile):
        return yf.returnJson(False, '非法的目标配置文件路径！')

    yf.writeFile(dstFile, w_body)

    return yf.returnJson(True, '增加守护进程成功!')


def startJob():
    args = getArgs()
    data = checkArgs(args, ['name', 'status'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not checkSafeName(name):
        return yf.returnJson(False, '进程名称不合法！')

    supCtl = getSupervisorctlBin() + ' -c ' + getServerDir() + "/supervisor.conf"

    status = args['status']

    action = "启动"
    cmd = supCtl + " start " + name + ":"
    if status == 'start':
        action = "停止"
        cmd = supCtl + " stop " + name + ":"
    data = yf.execShell(cmd)

    if data[1] != '':
        return yf.returnJson(False, action + '[' + name + ']失败!')
    return yf.returnJson(True, action + '[' + name + ']成功!')


def restartJob():
    args = getArgs()
    data = checkArgs(args, ['name', 'status'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not checkSafeName(name):
        return yf.returnJson(False, '进程名称不合法！')

    supCtl = getSupervisorctlBin() + ' -c ' + getServerDir() + "/supervisor.conf"

    name = args['name']
    status = args['status']

    cmd = supCtl + " stop " + name + ":"
    data = yf.execShell(cmd)
    cmd = supCtl + " start " + name + ":"
    data = yf.execShell(cmd)

    if data[1] != '':
        return yf.returnJson(False,  '[' + name + ']重启失败!')
    return yf.returnJson(True,  '[' + name + ']重启成功!')


def delJob():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]
    name = args['name']
    if not checkSafeName(name):
        return yf.returnJson(False, '进程名称不合法！')

    supCtl = getSupervisorctlBin() + ' -c ' + getServerDir() + "/supervisor.conf"
    log_dir = getServerDir() + '/log/'

    result = yf.execShell("{0} stop ".format(supCtl) + name + ":")
    program = getServerDir() + "/conf.d/" + name + ".ini"

    # 删除日志文件
    outlog = log_dir + name + ".out.log"
    if os.path.isfile(outlog):
        os.remove(outlog)
    errlog = log_dir + name + ".err.log"
    if os.path.isfile(errlog):
        os.remove(errlog)

    # 删除ini文件
    if os.path.isfile(program):
        os.remove(program)
        result = yf.execShell(
            "{0} update".format(supCtl))
        return yf.returnJson(True, '删除守护进程成功!')
    else:
        result = yf.execShell(
            "{0} update".format(supCtl))
        return yf.returnJson(False, '该守护进程不存在!')


def updateJob():
    args = getArgs()
    data = checkArgs(args, ["name", 'user', 'numprocs', 'priority'])
    if not data[0]:
        return data[1]
    user = args['user']
    numprocs = args['numprocs']
    priority = args['priority']
    name = args['name']
    if not checkSafeName(name):
        return yf.returnJson(False, '进程名称不合法！')

    programFile = getServerDir() + "/conf.d/" + name + ".ini"
    if not checkSafeFile(programFile):
        return yf.returnJson(False, '非法的配置文件路径！')

    mess = {}
    infos = []
    with open(programFile, "r") as fr:
        infos = fr.readlines()

    for line in infos:
        if "command=" in line.strip():
            mess["command"] = line.strip().split('=')[1]
        if "directory=" in line.strip():
            mess["path"] = line.strip().split('=')[1]

    log_file_name = getServerDir() + '/log/' + name

    w_body = ""
    w_body += "[program:" + name + "]" + "\n"
    w_body += "command=" + mess["command"] + "\n"
    w_body += "directory=" + mess["path"] + "\n"
    w_body += "autorestart=true" + "\n"
    w_body += "startsecs=3" + "\n"
    w_body += "startretries=3" + "\n"
    w_body += "stdout_logfile=" + log_file_name + ".out.log" + "\n"
    w_body += "stderr_logfile=" + log_file_name + ".err.log" + "\n"
    w_body += "stdout_logfile_maxbytes=2MB" + "\n"
    w_body += "stderr_logfile_maxbytes=2MB" + "\n"
    w_body += "user=" + user + "\n"
    w_body += "priority=" + priority + "\n"
    w_body += "numprocs={0}".format(numprocs) + "\n"
    w_body += "process_name=%(program_name)s_%(process_num)02d"

    yf.writeFile(programFile, w_body)

    return yf.returnJson(True, '修改守护进程成功!')


def getJobInfo():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]
    name = args['name']
    if not checkSafeName(name):
        return yf.returnJson(False, '进程名称不合法！')

    mess = {}
    infos = []
    info = {}
    program = getServerDir() + "/conf.d/" + name + ".ini"
    if not checkSafeFile(program):
        return yf.returnJson(False, '非法的配置文件路径！')

    with open(program, "r") as fr:
        infos = fr.readlines()
    mess = {}
    for line in infos:
        if "user=" in line.strip():
            mess["user"] = line.strip().split('=')[1]
        if "numprocs=" in line.strip():
            mess["numprocs"] = line.strip().split('=')[1]
        if "priority=" in line.strip():
            mess["priority"] = line.strip().split('=')[1]
    userlist = getUserListData()
    info["userlist"] = userlist
    info["daemoninfo"] = mess
    return yf.getJson(info)


def configTpl():
    path = getServerDir() + '/conf.d'
    pathFile = os.listdir(path)
    tmp = []
    for one in pathFile:
        if one.endswith(".ini"):
            file = path + '/' + one
            tmp.append(file)
    return yf.getJson(tmp)


def readConfigTpl():
    args = getArgs()
    data = checkArgs(args, ['file'])
    if not data[0]:
        return data[1]

    filepath = args['file']
    if not checkSafeFile(filepath):
        return yf.returnJson(False, '非法的配置文件路径！')

    content = yf.readFile(filepath)
    return yf.returnJson(True, 'ok', content)


def readConfigLogTpl():
    args = getArgs()
    data = checkArgs(args, ['file'])
    if not data[0]:
        return data[1]
    file_log = args['file']
    line_log = args['line']
    if not checkSafeFile(file_log):
        return yf.returnJson(False, '非法的配置文件路径！')

    with open(file_log, "r") as fr:
        infos = fr.readlines()

    stdout_logfile = ''
    for line in infos:
        if "stdout_logfile=" in line.strip():
            stdout_logfile = line.strip().split('=')[1]

    if stdout_logfile != '':
        data = yf.getLastLine(stdout_logfile, int(line_log))
        return yf.returnJson(True, 'OK', data)
    return yf.returnJson(False, 'OK', '')


def readConfigLogErrorTpl():
    args = getArgs()
    data = checkArgs(args, ['file'])
    if not data[0]:
        return data[1]
    file_log = args['file']
    line_log = args['line']
    if not checkSafeFile(file_log):
        return yf.returnJson(False, '非法的配置文件路径！')

    with open(file_log, "r") as fr:
        infos = fr.readlines()

    stderr_logfile = ''
    for line in infos:
        if "stderr_logfile=" in line.strip():
            stderr_logfile = line.strip().split('=')[1]

    if stderr_logfile != '':
        data = yf.getLastLine(stderr_logfile, int(line_log))
        return yf.returnJson(True, 'OK', data)
    return yf.returnJson(False, 'OK', '')


def supClearLog():
    args = getArgs()
    data = checkArgs(args, ['file'])
    if not data[0]:
        return data[1]
    file_log = args['file']
    if not checkSafeFile(file_log):
        return yf.returnJson(False, '非法的配置文件路径！')

    with open(file_log, "r") as fr:
        infos = fr.readlines()

    stdout_logfile = ''
    stderr_logfile = ''
    for line in infos:
        if "stdout_logfile=" in line.strip():
            stdout_logfile = line.strip().split('=')[1]
        if "stderr_logfile=" in line.strip():
            stderr_logfile = line.strip().split('=')[1]

    # 原生 Python 安全清空文件，彻底杜绝 Shell 命令拼接与命令注入
    try:
        if stdout_logfile and os.path.exists(stdout_logfile):
            with open(stdout_logfile, 'w') as f:
                f.write('')
        if stderr_logfile and os.path.exists(stderr_logfile):
            with open(stderr_logfile, 'w') as f:
                f.write('')
        return yf.returnJson(True, '清空成功')
    except Exception as e:
        return yf.returnJson(False, '清空失败: ' + str(e))


def runLog():
    return getServerDir() + '/log/supervisor.log'


if __name__ == "__main__":
    func = sys.argv[1]
    if func == 'status':
        print(status())
    elif func == 'start':
        print(start())
    elif func == 'stop':
        print(stop())
    elif func == 'restart':
        print(restart())
    elif func == 'reload':
        print(reload())
    elif func == 'initd_status':
        print(initdStatus())
    elif func == 'initd_install':
        print(initdInstall())
    elif func == 'initd_uninstall':
        print(initdUinstall())
    elif func == 'config_tpl':
        print(configTpl())
    elif func == 'read_config_tpl':
        print(readConfigTpl())
    elif func == 'read_config_log_tpl':
        print(readConfigLogTpl())
    elif func == 'read_config_log_error_tpl':
        print(readConfigLogErrorTpl())
    elif func == 'sup_clear_log':
        print(supClearLog())
    elif func == 'conf':
        print(getConf())
    elif func == 'run_log':
        print(runLog())
    elif func == 'get_user_list':
        print(getUserList())
    elif func == 'get_sup_list':
        print(getSupList())
    elif func == 'confd_list':
        print(confDList())
    elif func == 'confd_list_trace_log':
        print(confDlistTraceLog())
    elif func == 'confd_list_error_log':
        print(confDlistErrorLog())
    elif func == 'add_job':
        print(addJob())
    elif func == 'start_job':
        print(startJob())
    elif func == 'restart_job':
        print(restartJob())
    elif func == 'del_job':
        print(delJob())
    elif func == 'update_job':
        print(updateJob())
    elif func == 'get_job_info':
        print(getJobInfo())
    else:
        print('error')
