# coding:utf-8

import sys
import io
import os
import time
import re
import string
import subprocess

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'haproxy'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getInitDFile():
    if app_debug:
        return '/tmp/' + getPluginName()
    return '/etc/init.d/' + getPluginName()


def getConfTpl():
    path = getPluginDir() + "/conf/haproxy.conf"
    return path


def getConf():
    path = getServerDir() + "/haproxy.conf"
    return path


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
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


def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '参数:(' + ck[i] + ')没有!'))
    return (True, yf.returnJson(True, 'ok'))


def configTpl():
    path = getPluginDir() + '/tpl'
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

    filename = os.path.basename(args['file'])
    if not filename.endswith('.tpl'):
        return yf.returnJson(False, '仅支持读取.tpl模板文件！')

    tpl_dir = getPluginDir() + '/tpl'
    file_path = tpl_dir + '/' + filename
    if not os.path.exists(file_path):
        return yf.returnJson(False, '模板文件不存在！')

    content = yf.readFile(file_path)
    content = contentReplace(content)
    return yf.returnJson(True, 'ok', content)


def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$HA_USER}', yf.getRandomString(8))
    content = content.replace('{$HA_PWD}', yf.getRandomString(10))
    content = content.replace('{$SERVER_APP}', service_path + '/haproxy')
    return content


def status():
    data = yf.execShell(
        "ps -ef|grep haproxy |grep -v grep | grep -v python | awk '{print $2}'")
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
        content = contentReplace(content)
        yf.writeFile(file_bin, content)
        yf.execShell('chmod +x ' + file_bin)

    # config replace
    conf_bin = getConf()
    if not os.path.exists(conf_bin):
        conf_content = yf.readFile(getConfTpl())
        conf_content = contentReplace(conf_content)
        yf.writeFile(getServerDir() + '/haproxy.conf', conf_content)

    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/haproxy.service'
    systemServiceTpl = getPluginDir() + '/init.d/haproxy.service.tpl'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        service_path = yf.getServerDir()
        se_content = yf.readFile(systemServiceTpl)
        se_content = se_content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(systemService, se_content)
        yf.execShell('systemctl daemon-reload')

    return file_bin


def haOp(method):
    file = initDreplace()

    # check config
    sdir = getServerDir()
    cmd_check = sdir+'/sbin/haproxy -c -f ' + sdir + '/haproxy.conf'
    chk_data = yf.execShell(cmd_check)
    if chk_data[1]!= '':
        return chk_data[1]

    if not yf.isAppleSystem():
        data = yf.execShell('systemctl ' + method + ' haproxy')
        if data[1] == '':
            return 'ok'
        return 'fail'

    data = yf.execShell(file + ' ' + method)
    if data[1] == '':
        return 'ok'
    return data[1]


def start():
    return haOp('start')


def stop():
    return haOp('stop')


def restart():
    return haOp('restart')


def reload():
    return haOp('reload')


def initdStatus():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    shell_cmd = 'systemctl status haproxy | grep loaded | grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    yf.execShell('systemctl enable haproxy')
    return 'ok'


def initdUinstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    yf.execShell('systemctl disable haproxy')
    return 'ok'


def runLog():
    path = getServerDir() + "/haproxy.log"
    return path


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
    elif func == 'config_tpl':
        print(configTpl())
    elif func == 'read_config_tpl':
        print(readConfigTpl())
    elif func == 'run_log':
        print(runLog())
    else:
        print('error')
