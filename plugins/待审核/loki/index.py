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

import core.mw as mw

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'loki'


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
    path = getServerDir() + "/conf/loki-config.yaml"
    return path

def getPromtailConf():
    path = getServerDir() + "/conf/promtail-config.yaml"
    return path

def getConfTpl():
    path = getPluginDir() + "/conf/loki-config.yaml"
    return path

def getPromtailConfTpl():
    path = getPluginDir() + "/conf/promtail-config.yaml"
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

def getPidFile():
    file = getConf()
    content = yf.readFile(file)
    rep = r'pidfile\s*(.*)'
    tmp = re.search(rep, content)
    return tmp.groups()[0].strip()

def status():
    cmd = "ps aux|grep loki |grep -v grep | grep -v python | grep -v mdserver-web | awk '{print $2}'"
    data = yf.execShell(cmd)
    if data[0] == '':
        return 'stop'
    return 'start'

def getInstallVerion():
    version_pl = getServerDir() + "/version.pl"
    version = yf.readFile(version_pl).strip()
    return version

def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$APP_PATH}', service_path+"/loki")
    content = content.replace('{$LOG_PATH}', service_path+"/loki/logs")
    return content


# def openPort():
#     try:
#         from utils.firewall import Firewall as MwFirewall
#         MwFirewall.instance().addAcceptPort('3000', 'grafana', 'port')
#         return port
#     except Exception as e:
#         return "Release failed {}".format(e)
#     return True


def initDreplace():
    # 初始化OP配置
    init_file = getServerDir() + '/init.pl'
    if not os.path.exists(init_file):
        # openPort()
        yf.writeFile(init_file, 'ok')

    conf_dir = getServerDir()+'/conf'
    if not os.path.exists(conf_dir):
        yf.makeDirs(conf_dir)

    file_tpl = getConfTpl()
    dst_file = getConf()
    if not os.path.exists(dst_file):
        content = yf.readFile(file_tpl)
        content = contentReplace(content)
        yf.writeFile(dst_file, content)


    file_tpl = getPromtailConfTpl()
    dst_file = getPromtailConf()
    if not os.path.exists(dst_file):
        content = yf.readFile(file_tpl)
        content = contentReplace(content)
        yf.writeFile(dst_file, content)

    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/' + getPluginName() + '.service'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        systemServiceTpl = getPluginDir() + '/init.d/' + getPluginName() + '.service.tpl'
        service_path = yf.getServerDir()
        content = yf.readFile(systemServiceTpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(systemService, content)
        yf.execShell('systemctl daemon-reload')

    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/promtail.service'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        systemServiceTpl = getPluginDir() + '/init.d/promtail.service.tpl'
        service_path = yf.getServerDir()
        content = yf.readFile(systemServiceTpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(systemService, content)
        yf.execShell('systemctl daemon-reload')

    return True


def gOp(method):
    initDreplace()

    data = yf.execShell('systemctl ' + method + ' '+getPluginName())
    if data[1] != '':
        return data[1]

    data = yf.execShell('systemctl ' + method + ' promtail')
    if data[1] != '':
        return data[1]
    return 'ok'


def start():
    return gOp('start')

def stop():
    return gOp('stop')

def restart():
    return gOp('restart')

def reload():
    return gOp('reload')

def initdStatus():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    shell_cmd = 'systemctl status loki|grep loaded|grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'

    shell_cmd = 'systemctl status promtail|grep loaded|grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    data = yf.execShell('systemctl enable loki')
    if data[1] != '':
        return data[1]

    data = yf.execShell('systemctl enable promtail')
    if data[1] != '':
        return data[1]
    return 'ok'


def initdUinstall():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    data = yf.execShell('systemctl disable loki')
    if data[1] != '':
        return data[1]

    data = yf.execShell('systemctl enable promtail')
    if data[1] != '':
        return data[1]
    return 'ok'

def grafanaUrl():
    ip = yf.getLocalIp()
    return 'http://'+ip+':'+"3100"

def installPreInspection():
    return 'ok'


def uninstallPreInspection():
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
    elif func == 'uninstall_pre_inspection':
        print(uninstallPreInspection())
    elif func == 'conf':
        print(getConf())
    elif func == 'promtail_conf':
        print(getPromtailConf())
    elif func == 'grafana_url':
        print(grafanaUrl())
    else:
        print('error')
