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
import logging

_log = logging.getLogger('yf.supervisor')

app_debug = False
if yf.isAppleSystem():
    app_debug = True

# supervisorctl 是「连不上也会长时间阻塞」的交互式客户端，必须带超时：
# 面板 gunicorn 是 gthread 1 worker/4 threads，一条挂死命令会拖垮整个面板。
SUP_CTL_TIMEOUT = 20
SUP_SYSTEMCTL_TIMEOUT = 60

# 配置值白名单：supervisor 的配置是逐行 `key=value` 解析的，值里出现换行就等于
# 多写了一条指令（`command='x\nautostart=true'`）→ 可注入任意 [program:x] 段。
_CTRL_CHARS_RE = re.compile(r'[\x00-\x1f\x7f]')
_NUMPROCS_RE = re.compile(r'^[1-9]\d{0,3}$')
_PRIORITY_RE = re.compile(r'^-?\d{1,4}$')
_OS_USER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.\-]{0,31}$')


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
            parsed = json.loads(first_arg)
            # JSON 合法但非对象（`[]` / `123` / `"x"`）时不能原样返回：调用方一律按
            # dict 取值，`args['name']` 会 TypeError，真机直接 500。
            if not isinstance(parsed, dict):
                return {}
            return parsed
        except Exception as _e:
            _log.debug('[supervisor] getArgs 异常已忽略: %s', _e)

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
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
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


def checkSafeConfValue(value):
    """配置值校验：非空且不含任何控制字符（含换行）。

    supervisor 配置文件是逐行解析的，值里带 `\n` 等于多写了一条指令；
    实测 `command='x\nautostart=true'`、`numprocs='1\nuser=root'` 都能改变配置语义。
    """
    if value is None:
        return False
    v = str(value)
    if not v.strip():
        return False
    return not _CTRL_CHARS_RE.search(v)


def checkSafeLogPath(filepath):
    """日志文件沙盒：只允许清空面板自己写在 <server>/supervisor/log/ 下的日志。

    日志路径来自 conf.d/*.ini 的 stdout_logfile 行（本插件的写类 sink），
    若配置文件里被写成 `stdout_logfile=/etc/shadow`，「清空日志」就会变成
    root 任意文件截断。
    """
    if not filepath:
        return False
    real = os.path.realpath(filepath)
    log_dir = os.path.realpath(getServerDir() + '/log')
    return real == log_dir or real.startswith(log_dir + os.sep)


def _firstAbsPath(out):
    """从 `command -v` / `which` 的输出里取第一条真实存在的绝对路径。"""
    for line in str(out or '').splitlines():
        line = line.strip()
        if line and os.path.isabs(line) and os.path.exists(line):
            return line
    return ''


def findSupBin(name):
    """定位 supervisor 可执行文件：面板虚拟环境 → 系统 PATH；找不到回空串。

    必须回空串（而非裸名字）：调用方要靠它判断「是否已安装」，裸名字会让未安装的
    机器看起来像已安装。激活虚拟环境用 POSIX 的 `.`（不是 `source`）：execShell 默认
    走 /bin/sh，在默认 /bin/sh 是 dash 的系统（CentOS/Debian 常见）上 `source` 直接报错，
    旧实现的虚拟环境分支在那里从未生效过。
    """
    activate_file = yf.getPanelDir() + '/bin/activate'
    if os.path.exists(activate_file):
        out = yf.execShell('. ' + yf.shlexQuote(activate_file) + ' && command -v ' + name,
                           timeout=15)[0]
        path = _firstAbsPath(out)
        if path:
            return path
    return _firstAbsPath(yf.execShell('command -v ' + name, timeout=15)[0])


def getSupervisordBin():
    return findSupBin('supervisord')


def getSupervisorctlBin():
    """智能定位 supervisorctl：面板虚拟环境 → 系统 PATH → 裸名字（保持旧契约）。"""
    return findSupBin('supervisorctl') or 'supervisorctl'


def isInstalled():
    """已安装判据：install.sh 建的面板安装目录 `<server>/supervisor` 存在，且能找到 supervisord。

    为什么不能只看可执行文件：真机实测面板虚拟环境里就有 bin/supervisord（pip 脚本），
    但 `<server>/supervisor` 与 systemd unit 都不存在、服务 not running，面板按 info.json
    的 checks/path（`server/supervisor`）显示的也是「未安装」。此时
    HEAD 的 initDreplace 会照写 conf.d/主配置/systemd unit（ExecStart 指向未安装的路径），
    等于在未安装机器上伪造产物，并把结果吞成成功。
    """
    if not os.path.isdir(getServerDir()):
        return False
    return bool(getSupervisordBin())


def _pidIsSupervisord(pid):
    """pid 是否确为 supervisord 主进程。

    pip 装的 supervisord 是带 shebang 的 python 脚本，内核把 /proc/<pid>/comm 记成
    解释器名（python3），所以 comm 命中不了时还要看 cmdline 里的脚本名。
    """
    try:
        with open('/proc/%s/comm' % str(pid), 'r', encoding='utf-8', errors='replace') as fp:
            comm = fp.read().strip()
        if comm == 'supervisord':
            return True
        if not comm.startswith('python'):
            return False
        with open('/proc/%s/cmdline' % str(pid), 'rb') as fp:
            argv = fp.read().decode('utf-8', 'replace').split('\x00')
        # argv[0]=解释器, argv[1]=脚本：只有脚本名恰为 supervisord 才算
        return len(argv) > 1 and os.path.basename(argv[1]) == 'supervisord'
    except Exception:
        return False


def getSupervisordPid():
    """当前存活的 supervisord pid（读不到或对不上则回 ''）。

    pid 文件 + /proc 双重校验：只认「本插件写下的 pid 文件」且「该 pid 真是
    supervisord」，同时避开两种假阳性——陈旧 pid（pid 复用后指向任意存活进程）与
    `ps -ef|grep supervisor`（把命令行含该字样的无关进程当成 supervisord）。
    """
    pid_file = getServerDir() + '/run/supervisor.pid'
    if not os.path.exists(pid_file):
        return ''
    pid = str(yf.readFile(pid_file) or '').strip()
    if not pid.isdigit() or not _pidIsSupervisord(pid):
        return ''
    return pid


def status():
    # 只认 pid 文件 + /proc 双重校验，不用 `ps -ef|grep supervisor`：真机实测旧写法
    # 会把命令行里含 supervisor 字样的无关进程（面板自己拉起的探针、
    # `tail -f .../supervisor.log`）当成 supervisord → 未安装也报 start；
    # 顺带省掉每次状态轮询的 3 个管道进程。
    return 'start' if getSupervisordPid() else 'stop'


def initDreplace():
    if not isInstalled():
        # 未安装：不造 conf.d / 主配置 / systemd unit（零产物），也不 daemon-reload
        return False

    confD = getServerDir() + "/conf.d"
    conf = getServerDir() + "/supervisor.conf"
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/supervisor.service'
    systemServiceTpl = getPluginDir() + '/init.d/supervisor.service'

    service_path = yf.getServerDir()

    if not os.path.exists(confD):
        os.makedirs(confD, exist_ok=True)

    if not os.path.exists(conf):
        # config replace
        user = 'root'
        if yf.isAppleSystem():
            cmd = "who | sed -n '2, 1p' |awk '{print $1}'"
            user = yf.execShell(cmd)[0].strip()

        conf_content = yf.readFile(getConfTpl())
        if conf_content is False:
            return False
        conf_content = conf_content.replace('{$SERVER_PATH}', service_path)
        conf_content = conf_content.replace('{$OS_USER}', user)
        yf.writeFile(conf, conf_content)

    if os.path.exists(systemDir) and not os.path.exists(systemService):
        supervisord_bin = getSupervisordBin()
        # 取不到主程序时宁可不写 unit：以前会把 {$SUP_BIN} 替换成空串，
        # 留下 ExecStart=" -c .../supervisor.conf" 的坏 unit 并被 systemd 记入单元列表
        if supervisord_bin:
            se_content = yf.readFile(systemServiceTpl)
            if se_content is not False:
                se_content = se_content.replace('{$SERVER_PATH}', service_path)
                se_content = se_content.replace('{$SUP_BIN}', supervisord_bin)
                yf.writeFile(systemService, se_content)
                yf.execShell('systemctl daemon-reload', timeout=30)

    return True


def supOp(method):
    if not isInstalled():
        # 未安装：如实报错且零产物。原因写 stderr——面板 /plugins/run 以 stderr 判定
        # 插件失败并把消息回给前端，只 print 到 stdout 会被当成成功。
        sys.stderr.write('supervisor 未安装!')
        return 'fail'

    initDreplace()

    if not yf.isAppleSystem():
        # 成败看退出码：execShell 的 (stdout, stderr) 契约区分不了「失败」与「无输出」
        rc, out, err = yf.execShellRc(['systemctl', method, getPluginName()],
                                      shell=False, timeout=SUP_SYSTEMCTL_TIMEOUT)
        if rc == 0:
            return 'ok'
        sys.stderr.write((err or out or '').strip() or 'supervisor 操作失败!')
        return 'fail'

    if method in ('reload', 'restart'):
        return 'ok'

    if method == 'stop':
        # 同族缺陷：旧写法 `ps -ef|grep supervisor|…|xargs kill` 会误杀命令行含
        # supervisor 字样的无关进程；只认 pid 文件里那个真正的 supervisord。
        pid = getSupervisordPid()
        if not pid:
            return 'ok'
        try:
            os.kill(int(pid), 15)
            return 'ok'
        except Exception as e:
            sys.stderr.write(str(e))
            return 'fail'

    rc, out, err = yf.execShellRc([getSupervisordBin(), '-c',
                                   getServerDir() + '/supervisor.conf'],
                                  shell=False, timeout=SUP_SYSTEMCTL_TIMEOUT)
    if rc == 0:
        return 'ok'
    sys.stderr.write((err or out or '').strip() or 'supervisor 操作失败!')
    return 'fail'


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

    if not isInstalled():
        return 'fail'

    # 机器可读判据：旧写法 `systemctl status … |grep loaded |grep "enabled;"` 依赖
    # 人类可读输出（语言/版式一变就误判），未安装时也会被误报成「已设置开机启动」。
    rc, out, err = yf.execShellRc(['systemctl', 'is-enabled', getPluginName()],
                                  shell=False, timeout=15)
    if rc == 0 and out.strip().startswith('enabled'):
        return 'ok'
    return 'fail'


def initdOp(action):
    """systemctl enable/disable 的真成败（旧实现无条件回 'ok'：未安装也显示已开启）。"""
    if not isInstalled():
        sys.stderr.write('supervisor 未安装!')
        return 'fail'

    rc, out, err = yf.execShellRc(['systemctl', action, getPluginName()],
                                  shell=False, timeout=30)
    if rc == 0:
        return 'ok'
    sys.stderr.write((err or out or '').strip() or 'supervisor 操作失败!')
    return 'fail'


def initdInstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    return initdOp('enable')


def initdUinstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    return initdOp('disable')


def getSupList():
    if not isInstalled():
        # 未安装：不去跑 supervisorctl（两条无意义子进程），直接回空列表
        return yf.getJson({'data': []})

    data = {}

    statusFile = getServerDir() + "/status.txt"
    supCtl = yf.shlexQuote(getSupervisorctlBin())
    supConf = yf.shlexQuote(getServerDir() + "/supervisor.conf")
    cmd = "%s -c %s update; %s -c %s status > %s" % (
        supCtl, supConf, supCtl, supConf, yf.shlexQuote(statusFile))
    # 带超时：supervisord 卡住时 supervisorctl 会一直等，不能把面板子进程一起拖死
    yf.execShell(cmd, timeout=SUP_CTL_TIMEOUT)

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
            except Exception as _e:
                _log.debug('[supervisor] getSupList 异常已忽略: %s', _e)
            array_list.append(d)

    data = {}
    data['data'] = array_list
    return yf.getJson(data)


def confDList():
    confd_dir = getServerDir() + '/conf.d'
    if not os.path.isdir(confd_dir):
        # 未安装/目录缺失时不能 os.listdir：旧写法直接 FileNotFoundError → 前端 500
        return yf.getJson({'data': []})

    clist = sorted(os.listdir(confd_dir))
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
    if content is False:
        return ''
    rep = r'stdout_logfile\s*=\s*(.*)'
    tmp = re.search(rep, content)
    if not tmp:
        # 契约：前端 pluginRollingLogs 把返回值当「日志文件路径」用，所以不能回 JSON 信封；
        # 读不到就回空串（旧写法 yf.readFile 回 False / re.search 回 None 时
        # content 上做 re.search 或 tmp.groups() 直接 AttributeError/TypeError → 500）
        return ''
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
    if content is False:
        return ''
    rep = r'stderr_logfile\s*=\s*(.*)'
    tmp = re.search(rep, content)
    if not tmp:
        # 同 confDlistTraceLog：读不到/配置里没有该指令时回空串，不抛异常也不回信封
        return ''
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
        except Exception as _e:
            _log.debug('[supervisor] getUserListData 异常已忽略: %s', _e)

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

    if not isInstalled():
        # 未安装：不写 conf.d（零产物），如实报错
        return yf.returnJson(False, 'supervisor 未安装!')

    program = str(args['name']).strip()
    if not checkSafeName(program):
        return yf.returnJson(False, '进程名称不合法！仅支持英文字母、数字、下划线、中划线和点。')

    command = str(args['command'])
    path = str(args['path'])
    numprocs = str(args['numprocs']).strip()
    user = str(args['user']).strip()

    # 配置值白名单：值里带换行 = 往 supervisor 配置里注入任意指令/段
    if not checkSafeConfValue(command) or not checkSafeConfValue(path) \
            or not checkSafeConfValue(user):
        return yf.returnJson(False, '配置内容不合法!')
    if not _OS_USER_RE.match(user) or user not in getUserListData():
        return yf.returnJson(False, '启动用户不存在!')
    if not _NUMPROCS_RE.match(numprocs):
        return yf.returnJson(False, '进程数量不合法!')

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

    if not yf.writeFile(dstFile, w_body):
        return yf.returnJson(False, '写入配置失败!')

    return yf.returnJson(True, '增加守护进程成功!')


def startJob():
    args = getArgs()
    data = checkArgs(args, ['name', 'status'])
    if not data[0]:
        return data[1]

    if not isInstalled():
        return yf.returnJson(False, 'supervisor 未安装!')

    name = str(args['name']).strip()
    if not checkSafeName(name):
        return yf.returnJson(False, '进程名称不合法！')

    supCtl = getSupervisorctlBin() + ' -c ' + yf.shlexQuote(getServerDir() + "/supervisor.conf")

    status = str(args['status'])

    action = "启动"
    cmd = supCtl + " start " + yf.shlexQuote(name + ':')
    if status == 'start':
        action = "停止"
        cmd = supCtl + " stop " + yf.shlexQuote(name + ':')
    rc, out, err = yf.execShellRc(cmd, timeout=SUP_CTL_TIMEOUT)

    # supervisorctl 对「没有该进程」这类错误是 "name: ERROR (no such process)" 走 stdout 且
    # 退出码可能为 0，只看 stderr 会把失败报成成功
    if rc != 0 or 'ERROR' in str(out):
        return yf.returnJson(False, action + '[' + name + ']失败!')
    return yf.returnJson(True, action + '[' + name + ']成功!')


def restartJob():
    args = getArgs()
    data = checkArgs(args, ['name', 'status'])
    if not data[0]:
        return data[1]

    if not isInstalled():
        return yf.returnJson(False, 'supervisor 未安装!')

    name = str(args['name']).strip()
    if not checkSafeName(name):
        return yf.returnJson(False, '进程名称不合法！')

    supCtl = getSupervisorctlBin() + ' -c ' + yf.shlexQuote(getServerDir() + "/supervisor.conf")

    yf.execShellRc(supCtl + " stop " + yf.shlexQuote(name + ':'), timeout=SUP_CTL_TIMEOUT)
    rc, out, err = yf.execShellRc(supCtl + " start " + yf.shlexQuote(name + ':'),
                                  timeout=SUP_CTL_TIMEOUT)

    if rc != 0 or 'ERROR' in str(out):
        return yf.returnJson(False, '[' + name + ']重启失败!')
    return yf.returnJson(True, '[' + name + ']重启成功!')


def delJob():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]
    if not isInstalled():
        return yf.returnJson(False, 'supervisor 未安装!')

    name = str(args['name']).strip()
    if not checkSafeName(name):
        return yf.returnJson(False, '进程名称不合法！')

    supCtl = getSupervisorctlBin() + ' -c ' + yf.shlexQuote(getServerDir() + "/supervisor.conf")
    log_dir = getServerDir() + '/log/'

    program = getServerDir() + "/conf.d/" + name + ".ini"
    if not os.path.isfile(program):
        return yf.returnJson(False, '该守护进程不存在!')

    yf.execShellRc(supCtl + " stop " + yf.shlexQuote(name + ':'), timeout=SUP_CTL_TIMEOUT)

    # 删除日志文件
    outlog = log_dir + name + ".out.log"
    if os.path.isfile(outlog):
        os.remove(outlog)
    errlog = log_dir + name + ".err.log"
    if os.path.isfile(errlog):
        os.remove(errlog)

    os.remove(program)
    yf.execShellRc(supCtl + " update", timeout=SUP_CTL_TIMEOUT)
    return yf.returnJson(True, '删除守护进程成功!')


def updateJob():
    args = getArgs()
    data = checkArgs(args, ["name", 'user', 'numprocs', 'priority'])
    if not data[0]:
        return data[1]
    if not isInstalled():
        return yf.returnJson(False, 'supervisor 未安装!')

    user = str(args['user']).strip()
    numprocs = str(args['numprocs']).strip()
    priority = str(args['priority']).strip()
    name = str(args['name']).strip()
    if not checkSafeName(name):
        return yf.returnJson(False, '进程名称不合法！')

    programFile = getServerDir() + "/conf.d/" + name + ".ini"
    if not checkSafeFile(programFile):
        return yf.returnJson(False, '非法的配置文件路径！')

    # 参数白名单（旧实现直接把裸值拼进配置，numprocs/priority 可注入任意指令行）
    if not checkSafeConfValue(user):
        return yf.returnJson(False, '配置内容不合法!')
    if not _OS_USER_RE.match(user) or user not in getUserListData():
        return yf.returnJson(False, '启动用户不存在!')
    if not _NUMPROCS_RE.match(numprocs):
        return yf.returnJson(False, '进程数量不合法!')
    if not _PRIORITY_RE.match(priority) or not (-999 <= int(priority) <= 999):
        return yf.returnJson(False, '优先级参数不合法!')

    content = yf.readFile(programFile)
    if content is False:
        return yf.returnJson(False, '配置文件不存在!')

    mess = {}
    for line in content.splitlines():
        s = line.strip()
        if s.startswith('command='):
            # split('=', 1)：旧写法 split('=')[1] 会把带 `=` 的命令截断
            # （`command=env A=1 /bin/run` → 只剩 `env A`），改一次配置就丢掉命令
            mess["command"] = s.split('=', 1)[1]
        elif s.startswith('directory='):
            mess["path"] = s.split('=', 1)[1]
    if not mess.get("command") or not mess.get("path"):
        return yf.returnJson(False, '配置文件不存在!')

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

    if not yf.writeFile(programFile, w_body):
        return yf.returnJson(False, '写入配置失败!')

    return yf.returnJson(True, '修改守护进程成功!')


def getJobInfo():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]
    name = str(args['name']).strip()
    if not checkSafeName(name):
        return yf.returnJson(False, '进程名称不合法！')

    info = {}
    program = getServerDir() + "/conf.d/" + name + ".ini"
    if not checkSafeFile(program):
        return yf.returnJson(False, '非法的配置文件路径！')

    content = yf.readFile(program)
    if content is False:
        # 旧写法裸 open()：配置文件不存在时 FileNotFoundError → 前端 500
        return yf.returnJson(False, '配置文件不存在!')

    # 缺省值兜底：前端修改弹窗直接把这些值回填到 input，缺键会显示 undefined
    mess = {'user': '', 'numprocs': '1', 'priority': '999'}
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("user="):
            mess["user"] = s.split('=', 1)[1]
        elif s.startswith("numprocs="):
            mess["numprocs"] = s.split('=', 1)[1]
        elif s.startswith("priority="):
            mess["priority"] = s.split('=', 1)[1]
    userlist = getUserListData()
    info["userlist"] = userlist
    info["daemoninfo"] = mess
    return yf.getJson(info)


def configTpl():
    path = getServerDir() + '/conf.d'
    if not os.path.isdir(path):
        # 未安装时旧写法 os.listdir 直接 FileNotFoundError → 前端子配置页 500
        return yf.getJson([])
    tmp = []
    for one in sorted(os.listdir(path)):
        if one.endswith(".ini"):
            file = path + '/' + one
            tmp.append(file)
    return yf.getJson(tmp)


def parseLineCount(value):
    """日志行数参数：非数字/非正数一律回 None（旧实现裸 int() → ValueError 500）。"""
    try:
        num = int(str(value).strip())
    except Exception:
        return None
    return num if num > 0 else None


def readConfigTpl():
    args = getArgs()
    data = checkArgs(args, ['file'])
    if not data[0]:
        return data[1]

    filepath = args['file']
    if not checkSafeFile(filepath):
        return yf.returnJson(False, '非法的配置文件路径！')

    content = yf.readFile(filepath)
    if content is False:
        # readFile 失败时回的是 False：旧写法把它当内容回给前端（页面显示 "false"）
        return yf.returnJson(False, '配置文件不存在!')
    return yf.returnJson(True, 'ok', content)


def readConfigLogTpl():
    args = getArgs()
    data = checkArgs(args, ['file', 'line'])
    if not data[0]:
        return data[1]
    file_log = args['file']
    line_log = parseLineCount(args['line'])
    if line_log is None:
        return yf.returnJson(False, '参数格式错误!')
    if not checkSafeFile(file_log):
        return yf.returnJson(False, '非法的配置文件路径！')

    content = yf.readFile(file_log)
    if content is False:
        return yf.returnJson(False, '配置文件不存在!')

    stdout_logfile = ''
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("stdout_logfile="):
            stdout_logfile = s.split('=', 1)[1]

    if stdout_logfile != '':
        data = yf.getLastLine(stdout_logfile, line_log)
        return yf.returnJson(True, 'OK', data)
    return yf.returnJson(False, 'OK', '')


def readConfigLogErrorTpl():
    args = getArgs()
    data = checkArgs(args, ['file', 'line'])
    if not data[0]:
        return data[1]
    file_log = args['file']
    line_log = parseLineCount(args['line'])
    if line_log is None:
        return yf.returnJson(False, '参数格式错误!')
    if not checkSafeFile(file_log):
        return yf.returnJson(False, '非法的配置文件路径！')

    content = yf.readFile(file_log)
    if content is False:
        return yf.returnJson(False, '配置文件不存在!')

    stderr_logfile = ''
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("stderr_logfile="):
            stderr_logfile = s.split('=', 1)[1]

    if stderr_logfile != '':
        data = yf.getLastLine(stderr_logfile, line_log)
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

    content = yf.readFile(file_log)
    if content is False:
        return yf.returnJson(False, '配置文件不存在!')

    stdout_logfile = ''
    stderr_logfile = ''
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("stdout_logfile="):
            stdout_logfile = s.split('=', 1)[1]
        elif s.startswith("stderr_logfile="):
            stderr_logfile = s.split('=', 1)[1]

    for path in (stdout_logfile, stderr_logfile):
        # 写类 sink 必须带沙盒：配置里被改成 stdout_logfile=/etc/shadow 时，
        # 「清空日志」就是 root 任意文件截断
        if path and not checkSafeLogPath(path):
            return yf.returnJson(False, '日志路径不合法!')

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
