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
    return 'mtproxy'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getServiceTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".service.tpl"
    return path


def getConfEnvTpl():
    path = getPluginDir() + "/conf/mt.toml"
    return path


def getConfEnv():
    path = getServerDir() + "/mt.toml"
    return path


def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        t = args[0].strip('{').strip('}')
        t = t.split(':')
        tmp[t[0]] = t[1]
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':')
            tmp[t[0]] = t[1]

    return tmp

def status():
    cmd = "ps -ef|grep mtproxy| grep mtg |grep -v grep | grep -v python  | awk '{print $2}'"
    data = yf.execShell(cmd)
    if data[0] == '':
        return 'stop'
    return 'start'


def getServiceFile():
    systemDir = yf.systemdCfgDir()
    return systemDir + '/mtproxy.service'


def getMtproxyPort():
    return '8349'


def __release_port(port):
    from collections import namedtuple
    try:
        from utils.firewall import Firewall as MwFirewall
        MwFirewall.instance().addAcceptPort(port, 'mtproxy', 'port')
        return port
    except Exception as e:
        return "Release failed {}".format(e)

def __delete_port(port):
    from collections import namedtuple
    try:
        from utils.firewall import Firewall as MwFirewall
        MwFirewall.instance().delAcceptPortCmd(port, 'tcp')
        return port
    except Exception as e:
        return "Delete failed {}".format(e)

def openPort():
    port = getMtproxyPort()
    for i in [port]:
        __release_port(i)
    return True

def delPort():
    port = getMtproxyPort()
    for i in [port]:
        __delete_port(i)
    return True


def initDreplace():

    envTpl = getConfEnvTpl()
    dstEnv = getConfEnv()
    cmd = getServerDir() + '/mtg/mtg generate-secret `head -c 16 /dev/urandom | xxd -ps`'
    secret = yf.execShell(cmd)
    if not os.path.exists(dstEnv):
        env_content = yf.readFile(envTpl)
        env_content = env_content.replace('{$PORT}', getMtproxyPort())
        env_content = env_content.replace('{$SECRET}', secret[0].strip())
        yf.writeFile(dstEnv, env_content)
        openPort()

    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/mtproxy.service'
    systemServiceTpl = getServiceTpl()
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        service_path = yf.getServerDir()
        se_content = yf.readFile(systemServiceTpl)
        se_content = se_content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(systemService, se_content)
        yf.execShell('systemctl daemon-reload')

    return 'ok'


def mtOp(method):
    file = initDreplace()

    if not yf.isAppleSystem():
        yf.execShell('systemctl daemon-reload')
        data = yf.execShell('systemctl ' + method + ' mtproxy')
        if data[1] == '':
            return 'ok'
        return data[1]

    return 'fail'


def start():
    return mtOp('start')


def stop():
    return mtOp('stop')


def restart():
    return mtOp('restart')


def reload():
    return mtOp('reload')


def initdStatus():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    shell_cmd = 'systemctl status mtproxy | grep loaded | grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'

def initdInstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"
    yf.execShell('systemctl enable mtproxy')
    return 'ok'


def initdUinstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"
    yf.execShell('systemctl disable mtproxy')
    return 'ok'

def getMtproxyUrl():
    conf = getConfEnv()
    content = yf.readFile(conf)


    rep = r'bind-to\s*=\s*(.*)'
    tmp = re.search(rep, content)
    bind_to = tmp.groups()[0].strip()
    bind_to = bind_to.strip('"')

    rep = r'secret\s*=\s*(.*)'
    tmp = re.search(rep, content)
    secret = tmp.groups()[0].strip()
    secret = secret.strip('"')

    info = bind_to.split(":")

    ip = yf.getLocalIp()

    url = 'tg://proxy?server={0}&port={1}&secret={2}'.format(ip, info[1], secret)
    return yf.returnJson(True, 'ok', url)

def installPreInspection():
    sys = yf.execShell("cat /etc/*-release | grep PRETTY_NAME |awk -F = '{print $2}' | awk -F '\"' '{print $2}'| awk '{print $1}'")

    if sys[1] != '':
        return '不支持该系统'

    sys_id = yf.execShell("cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}' | awk -F '\"' '{print $2}'")

    sysName = sys[0].strip().lower()
    sysId = sys_id[0].strip()

    if sysName in ('opensuse'):
        return '不支持该系统'

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
    elif func == 'conf':
        print(getServiceFile())
    elif func == 'conf_env':
        print(getConfEnv())
    elif func == 'url':
        print(getMtproxyUrl())
    else:
        print('error')
