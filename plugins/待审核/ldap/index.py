# coding:utf-8

import sys
import io
import os
import time
import re

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'ldap'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getInitDFile():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return '/tmp/' + getPluginName()

    if current_os.startswith('freebsd'):
        return '/etc/rc.d/' + getPluginName()

    return '/etc/init.d/' + getPluginName()


def getConf():
    # path = getServerDir() + "/redis.conf"
    path = "/etc/ldap/ldap.conf"
    return path


def getConfTpl():
    path = getPluginDir() + "/config/ldap.conf"
    return path


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


def getArgs():
    args = sys.argv[3:]
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        t = args[0].strip('{').strip('}')
        if t.strip() == '':
            tmp = []
        else:
            t = t.split(':')
            tmp[t[0]] = t[1]
        tmp[t[0]] = t[1]
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':')
            tmp[t[0]] = t[1]
    return tmp

def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '参数:(' + ck[i] + ')没有!'))
    return (True, yf.returnJson(True, 'ok'))

def configTpl():
    path = "/etc/ldap/schema"
    pathFile = os.listdir(path)
    tmp = []
    for one in pathFile:
        file = path + '/' + one
        tmp.append(file)
    return yf.getJson(tmp)


def readConfigTpl():
    args = getArgs()
    data = checkArgs(args, ['file'])
    if not data[0]:
        return data[1]

    content = yf.readFile(args['file'])
    content = contentReplace(content)
    return yf.returnJson(True, 'ok', content)

def getPidFile():
    file = getConf()
    content = yf.readFile(file)
    rep = r'pidfile\s*(.*)'
    tmp = re.search(rep, content)
    return tmp.groups()[0].strip()

def status():
    pid_file = "/var/run/slapd/slapd.pid"
    if not os.path.exists(pid_file):
        return 'stop'

    # data = yf.execShell(
    #     "ps aux|grep redis |grep -v grep | grep -v python | grep -v mdserver-web | awk '{print $2}'")

    # if data[0] == '':
    #     return 'stop'
    return 'start'

def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    return content

def initDreplace():
    service_path = yf.getServerDir()

    conf = getConf()
    conf_tpl = getConfTpl()
    if not os.path.exists(conf):
        content = yf.readFile(conf_tpl)
        content = contentReplace(content)
        yf.writeFile(conf, content)
    return True


def ladpOp(method):
    initDreplace()

    current_os = yf.getOs()
    if current_os == "darwin":
        return 'ok'

    if current_os.startswith("freebsd"):
        data = yf.execShell('service slapd ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    data = yf.execShell('systemctl ' + method + ' slapd')
    if data[1] == '':
        return 'ok'
    return data[1]


def start():
    return ladpOp('start')


def stop():
    return ladpOp('stop')


def restart():
    status = ladpOp('restart')

    log_file = runLog()
    yf.execShell("echo '' > " + log_file)
    return status


def reload():
    return ladpOp('reload')


def getPort():
    conf = getConf()
    content = yf.readFile(conf)

    rep = r"^(port)\s*([.0-9A-Za-z_& ~]+)"
    tmp = re.search(rep, content, re.M)
    if tmp:
        return tmp.groups()[1]
    return '6379'


def initdStatus():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile()
        if os.path.exists(initd_bin):
            return 'ok'

    shell_cmd = 'systemctl status slapd | grep loaded | grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    # freebsd initd install
    if current_os.startswith('freebsd'):
        import shutil
        source_bin = initDreplace()
        initd_bin = getInitDFile()
        shutil.copyfile(source_bin, initd_bin)
        yf.execShell('chmod +x ' + initd_bin)
        yf.execShell('sysrc slapd_enable="YES"')
        return 'ok'

    yf.execShell('systemctl enable slapd')
    return 'ok'


def initdUinstall():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile()
        os.remove(initd_bin)
        yf.execShell('sysrc slapd_enable="NO"')
        return 'ok'

    yf.execShell('systemctl disable slapd')
    return 'ok'


def runLog():
    return getServerDir() + '/data/redis.log'


def getRedisConfInfo():
    conf = getConf()

    gets = [
        {'name': 'bind', 'type': 2, 'ps': '绑定IP(修改绑定IP可能会存在安全隐患)','must_show':1},
        {'name': 'port', 'type': 2, 'ps': '绑定端口','must_show':1},
        {'name': 'timeout', 'type': 2, 'ps': '空闲链接超时时间,0表示不断开','must_show':1},
        {'name': 'maxclients', 'type': 2, 'ps': '最大连接数','must_show':1},
        {'name': 'databases', 'type': 2, 'ps': '数据库数量','must_show':1},
        {'name': 'requirepass', 'type': 2, 'ps': 'redis密码,留空代表没有设置密码','must_show':1},
        {'name': 'maxmemory', 'type': 2, 'ps': 'MB,最大使用内存,0表示不限制','must_show':1},
        {'name': 'slaveof', 'type': 2, 'ps': '同步主库地址','must_show':0},
        {'name': 'masterauth', 'type': 2, 'ps': '同步主库密码', 'must_show':0}
    ]
    content = yf.readFile(conf)

    result = []
    for g in gets:
        rep = r"^(" + g['name'] + r'\)\s*([.0-9A-Za-z_& ~]+)'
        tmp = re.search(rep, content, re.M)
        if not tmp:
            if g['must_show'] == 0:
                continue

            g['value'] = ''
            result.append(g)
            continue
        g['value'] = tmp.groups()[1]
        if g['name'] == 'maxmemory':
            g['value'] = g['value'].strip("mb")
        result.append(g)

    return result


def getRedisConf():
    data = getRedisConfInfo()
    return yf.getJson(data)


def submitRedisConf():
    gets = ['bind', 'port', 'timeout', 'maxclients',
            'databases', 'requirepass', 'maxmemory','slaveof','masterauth']
    args = getArgs()
    conf = getConf()
    content = yf.readFile(conf)
    for g in gets:
        if g in args:
            rep = g + r'\s*([.0-9A-Za-z_& ~]+)'
            val = g + ' ' + args[g]

            if g == 'maxmemory':
                val = g + ' ' + args[g] + "mb"

            if g == 'requirepass' and args[g] == '':
                content = re.sub('requirepass', '#requirepass', content)
            if g == 'requirepass' and args[g] != '':
                content = re.sub('#requirepass', 'requirepass', content)
                content = re.sub(rep, val, content)

            if g != 'requirepass':
                content = re.sub(rep, val, content)
    yf.writeFile(conf, content)
    reload()
    return yf.returnJson(True, '设置成功')

def installPreInspection():
    slapd_path = '/etc/ldap/slapd.d'
    if not os.path.exists(slapd_path):
        return "需要手动执行:apt install -y slapd ldap-utils"
    return 'ok'


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
    elif func == 'install_pre_inspection':
        print(installPreInspection())
    elif func == 'run_info':
        print(runInfo())
    elif func == 'conf':
        print(getConf())
    elif func == 'run_log':
        print(runLog())
    elif func == 'get_redis_conf':
        print(getRedisConf())
    elif func == 'submit_redis_conf':
        print(submitRedisConf())
    elif func == 'config_tpl':
        print(configTpl())
    elif func == 'read_config_tpl':
        print(readConfigTpl())
    else:
        print('error')
