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
    return 'mosquitto'


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
    path = getServerDir() + "/etc/mosquitto/mosquitto.conf"
    return path


def runLog():
    path = getServerDir() + "/data/mosquitto.log"
    return path


def getConfTpl():
    path = getPluginDir() + "/config/mosquitto.conf"
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
            return tmp
        parts = t.split(':')
        if len(parts) >= 2:
            tmp[parts[0]] = parts[1]
    elif args_len > 1:
        for i in range(len(args)):
            parts = args[i].split(':')
            if len(parts) >= 2:
                tmp[parts[0]] = parts[1]
    return tmp


def status():
    data = yf.execShell(
        "ps aux|grep mosquitto |grep -v grep | grep -v python | grep -v mdserver-web | awk '{print $2}'")

    if data[0] == '':
        return 'stop'
    return 'start'


def initDreplace():

    file_tpl = getInitDTpl()
    service_path = yf.getServerDir()

    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        os.mkdir(initD_path)
    file_bin = initD_path + '/' + getPluginName()

    # initd replace
    if not os.path.exists(file_bin):
        content = yf.readFile(file_tpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(file_bin, content)
        yf.execShell('chmod +x ' + file_bin)

    # log
    dataLog = getServerDir() + '/data'
    if not os.path.exists(dataLog):
        os.makedirs(dataLog)
    
    # 强制安全权限归属校验，保证低权限降权运行时具有写日志和读配置的权限
    yf.execShell('chown -R mosquitto:mosquitto ' + getServerDir())

    # config replace
    dst_conf = getServerDir() + '/etc/mosquitto/' + getPluginName() + '.conf'
    dst_conf_init = getServerDir() + '/init.pl'
    if not os.path.exists(dst_conf_init):
        conf_content = yf.readFile(getConfTpl())
        conf_content = conf_content.replace('{$SERVER_PATH}', service_path)

        yf.writeFile(dst_conf, conf_content)
        yf.writeFile(dst_conf_init, 'ok')

    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/' + getPluginName() + '.service'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        systemServiceTpl = getPluginDir() + '/init.d/' + getPluginName() + '.service.tpl'
        service_path = yf.getServerDir()
        se_content = yf.readFile(systemServiceTpl)
        se_content = se_content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(systemService, se_content)
        yf.execShell('systemctl daemon-reload')

    return file_bin


def mqttOp(method):
    file = initDreplace()

    current_os = yf.getOs()
    if current_os == "darwin":
        data = yf.execShell(file + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    if current_os.startswith("freebsd"):
        data = yf.execShell('service ' + getPluginName() + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    data = yf.execShell('systemctl ' + method + ' ' + getPluginName())
    if data[1] == '':
        return 'ok'
    return data[1]


def start():
    return mqttOp('start')


def stop():
    return mqttOp('stop')


def restart():
    status = mqttOp('restart')

    log_file = runLog()
    yf.execShell("echo '' > " + log_file)
    return status


def reload():
    return mqttOp('reload')


def initdStatus():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile()
        if os.path.exists(initd_bin):
            return 'ok'

    shell_cmd = 'systemctl status ' + \
        getPluginName() + ' | grep loaded | grep "enabled;"'
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
        yf.execShell('sysrc ' + getPluginName() + '_enable="YES"')
        return 'ok'

    yf.execShell('systemctl enable ' + getPluginName())
    return 'ok'


def initdUinstall():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile()
        os.remove(initd_bin)
        yf.execShell('sysrc ' + getPluginName() + '_enable="NO"')
        return 'ok'

    yf.execShell('systemctl disable ' + getPluginName())
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
    elif func == 'conf':
        print(getConf())
    elif func == 'run_log':
        print(runLog())
    else:
        print('error')
