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
    return 'dztasks'


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
    path = getServerDir() + "/custom/conf/app.conf"
    return path


def getConfTpl():
    path = getPluginDir() + "/config/dztasks.conf"
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
    # path = getPluginDir() + '/tpl'
    # pathFile = os.listdir(path)
    tmp = []
    return yf.getJson(tmp)


def readConfigTpl():
    try:
        args = getArgs()
        data = checkArgs(args, ['file'])
        if not data[0]:
            return data[1]

        # 1. 强制使用 os.path.basename 阻断任意目录穿越符号 (如 ../)
        safe_file_name = os.path.basename(args['file'])
        
        # 2. 强行锁定只允许读取插件自身的 config/ 配置模板目录，防止越权读取敏感文件
        safe_file_path = getPluginDir() + '/config/' + safe_file_name

        if not os.path.exists(safe_file_path):
            return yf.returnJson(False, '模板配置文件不存在！')

        content = yf.readFile(safe_file_path)
        content = contentReplace(content)
        return yf.returnJson(True, 'ok', content)
    except Exception as e:
        return yf.returnJson(False, '读取模板配置文件发生异常: ' + str(e))


def getPidFile():
    file = getConf()
    content = yf.readFile(file)
    rep = r'pidfile\s*(.*)'
    tmp = re.search(rep, content)
    return tmp.groups()[0].strip()

def status():
    cmd = "ps aux|grep dztasks|grep -v grep|grep -v python|grep -v mdserver-web|awk '{print $2}'"
    data = yf.execShell(cmd)
    if data[0] == '':
        return 'stop'
    return 'start'

def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$SERVER_APP}', service_path + '/dztasks')
    content = content.replace('{$ADMIN_NAME}', yf.getRandomString(6))
    content = content.replace('{$ADMIN_PASS}', yf.getRandomString(10))
    return content



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

    # log
    dataLog = getServerDir() + '/data'
    if not os.path.exists(dataLog):
        yf.execShell('chmod +x ' + file_bin)

    app_dir = getServerDir() + '/custom/conf'
    if not os.path.exists(app_dir):
        yf.makeDirs(app_dir)

    # config replace
    dst_conf = getServerDir() + '/custom/conf/app.conf'
    dst_conf_init = getServerDir() + '/init.pl'
    if not os.path.exists(dst_conf_init):
        content = yf.readFile(getConfTpl())
        # print(content)
        content = contentReplace(content)
        yf.writeFile(dst_conf, content)
        yf.writeFile(dst_conf_init, 'ok')

    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/' + getPluginName() + '.service'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        systemServiceTpl = getPluginDir() + '/init.d/' + getPluginName() + '.service.tpl'
        content = yf.readFile(systemServiceTpl)
        content = contentReplace(content)
        yf.writeFile(systemService, content)
        yf.execShell('systemctl daemon-reload')

    return file_bin


def dzOp(method):
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
    return dzOp('start')


def stop():
    return dzOp('stop')


def restart():
    status = dzOp('restart')

    log_file = runLog()
    yf.execShell("echo '' > " + log_file)
    return status

def reload():
    return dzOp('reload')

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


def runLog():
    return getServerDir() + '/logs.pl'


def getDzPort():
    file = getConf()
    content = yf.readFile(file)
    rep = r'port\s*=\s*(.*)'
    tmp = re.search(rep, content)
    return tmp.groups()[0].strip()

def getDzUsername():
    file = getConf()
    content = yf.readFile(file)
    rep = r'user\s*=\s*(.*)'
    tmp = re.search(rep, content)
    return tmp.groups()[0].strip()

def getDzPassword():
    file = getConf()
    content = yf.readFile(file)
    rep = r'pass\s*=\s*(.*)'
    tmp = re.search(rep, content)
    return tmp.groups()[0].strip()

def getHomePage():
    http_port = getDzPort()
    ip = yf.getLocalIp()
    if yf.isAppleSystem():
        ip = '127.0.0.1'
    url = 'http://'+ip+":"+str(http_port)
    return url

def homePage():
    return yf.returnJson(True, 'ok!', getHomePage())


def runInfo():
    data = {}
    data['url'] = getHomePage()
    data['user'] = getDzUsername()
    data['pass'] = getDzPassword()

    return yf.returnJson(True, 'ok!', data)

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
    elif func == 'run_log':
        print(runLog())
    elif func == 'config_tpl':
        print(configTpl())
    elif func == 'read_config_tpl':
        print(readConfigTpl())
    elif func == 'home_page':
        print(homePage())
    else:
        print('error')
