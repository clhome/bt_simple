# coding:utf-8

import sys
import io
import os
import time

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.mw as mw

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'varnish'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getInitDFile():
    if app_debug:
        return '/tmp/' + getPluginName()
    return '/etc/init.d/' + getPluginName()


def getConf():
    path = '/etc/varnish/vcl.conf'
    if os.path.exists(path):
        return path
    path = "/etc/varnish/default.vcl"
    return path


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$SERVER_APP}', service_path + '/varnish')
    return content


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


def status():
    data = yf.execShell(
        "ps -ef|grep varnish |grep -v grep | grep -v python | grep -v mdserver-web | awk '{print $2}'")

    if data[0] == '':
        return 'stop'
    return 'start'


def vaOp(method):
    yf.execShell("systemctl daemon-reload")
    data = yf.execShell('systemctl ' + method + ' ' + getPluginName())
    if data[1] == '':
        return 'ok'
    return 'fail'


def start():
    return vaOp('start')


def stop():
    return vaOp('stop')


def restart():
    return vaOp('restart')


def reload():
    return vaOp('reload')


def runInfo():
    cmd = "varnishstat -j"
    data = yf.execShell(cmd)[0].strip()
    return data


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

    # 安全检查：限制读取的文件必须是 tpl 目录下的模板
    target_file = os.path.abspath(args['file'])
    tpl_dir = os.path.abspath(getPluginDir() + '/tpl')
    
    # 确保文件处于 tpl_dir 内部并且以 .vcl 结尾
    if not target_file.startswith(tpl_dir + os.sep) or not target_file.endswith('.vcl'):
        return yf.returnJson(False, '越权访问拦截：仅允许读取模板目录下的VCL配置文件！')

    content = yf.readFile(target_file)
    content = contentReplace(content)
    return yf.returnJson(True, 'ok', content)


def initdStatus():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    shell_cmd = 'systemctl status ' + \
        getPluginName() + ' | grep loaded | grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    yf.execShell('systemctl enable ' + getPluginName())
    return 'ok'


def initdUinstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    yf.execShell('systemctl disable ' + getPluginName())
    return 'ok'


def runLog():

    if os.path.exists("/var/log/varnish/varnish.log"):
        return "/var/log/varnish/varnish.log"

    return "/var/log/varnish/varnishncsa.log"


def confService():
    return yf.systemdCfgDir() + '/varnish.service'

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
    elif func == 'run_info':
        print(runInfo())
    elif func == 'conf':
        print(getConf())
    elif func == 'conf_service':
        print(confService())
    elif func == 'run_log':
        print(runLog())
    elif func == 'config_tpl':
        print(configTpl())
    elif func == 'read_config_tpl':
        print(readConfigTpl())
    else:
        print('error')
