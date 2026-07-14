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
    return 'gorse'


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
    path = getServerDir() + "/gorse.toml"
    return path


def getConfTpl():
    path = getPluginDir() + "/config/gorse.toml"
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
            t = t.split(':',1)
            tmp[t[0]] = t[1]
        tmp[t[0]] = t[1]
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':',1)
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
    # pid_file = getPidFile()
    # if not os.path.exists(pid_file):
    #     return 'stop'

    cmd = "ps aux|grep gorse |grep -v grep | grep -v python | grep -v mdserver-web | awk '{print $2}'"
    data = yf.execShell(cmd)

    if data[0] == '':
        return 'stop'
    return 'start'


def initRedisConf():
    requirepass = ""
    conf = yf.getServerDir() + '/redis/redis.conf'
    content = yf.readFile(conf)
    rep = r"^(requirepass)\s*([.0-9A-Za-z_& ~]+)"
    tmp = re.search(rep, content, re.M)
    if tmp:
        requirepass = tmp.groups()[1]

    port = "6379"
    rep = r"^(port)\s*([.0-9A-Za-z_& ~]+)"
    tmp = re.search(rep, content, re.M)
    if tmp:
        port = tmp.groups()[1]

    return 'redis://:'+requirepass+'@127.0.0.1:'+port+'/3'

def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$CONFIG_ADMIN}', yf.getRandomString(6))
    content = content.replace('{$CONFIG_PASS}', yf.getRandomString(10))
    content = content.replace('{$CONFIG_REDIS}', initRedisConf())
    return content


def initDreplace():

    file_tpl = getInitDTpl()
    service_path = yf.getServerDir()

    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        yf.makeDirs(initD_path)

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
        yf.execShell('chmod +x ' + file_bin)

    # config replace
    dst_conf = getServerDir() + '/gorse.toml'
    dst_conf_init = getServerDir() + '/init.pl'
    if not os.path.exists(dst_conf_init):
        content = yf.readFile(getConfTpl())
        content = content.replace('{$SERVER_PATH}', service_path)
        content = contentReplace(content)
        yf.writeFile(dst_conf, content)
        yf.writeFile(dst_conf_init, 'ok')

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

    return file_bin


def gorseOp(method):
    file = initDreplace()

    # print(file)

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
    return gorseOp('start')


def stop():
    return gorseOp('stop')


def restart():
    status = gorseOp('restart')
    log_file = runLog()
    yf.execShell("echo '' > " + log_file)
    return status


def reload():
    return gorseOp('reload')


def getPort():
    conf = getServerDir() + '/gorse.conf'
    content = yf.readFile(conf)

    rep = "^(" + 'port' + ')\\s*([.0-9A-Za-z_& ~]+)'
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

    shell_cmd = 'systemctl status ' + getPluginName() + ' | grep loaded | grep "enabled;"'
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

def getGorseInfo():
    conf_file = getConf()
    content = yf.readFile(conf_file)

    rdata = {}

    rep = r'dashboard_user_name\s*=\s*"(.*)"'
    tmp = re.search(rep, content)
    tmp = re.search(rep, content, re.M)
    if tmp:
        rdata['dashboard_user_name'] = tmp.groups()[0]


    rep = r'dashboard_password\s*=\s*"(.*)"'
    tmp = re.search(rep, content)
    tmp = re.search(rep, content, re.M)
    if tmp:
        rdata['dashboard_password'] = tmp.groups()[0]

    rep = r'http_port\s*=\s*(.*)'
    tmp = re.search(rep, content)
    tmp = re.search(rep, content, re.M)
    if tmp:
        rdata['http_port'] = tmp.groups()[0]

    rdata['ip'] = yf.getHostAddr()
    return yf.returnJson(True,'ok', rdata)

def installPreInspection():
    redis_path = yf.getServerDir() + "/redis"
    if not os.path.exists(redis_path):
        return "默认需要安装Redis"

    mongodb_path = yf.getServerDir() + "/mongodb"
    if not os.path.exists(mongodb_path):
        return "默认需要安装MongoDB"

    if not yf.isAppleSystem():
        glibc_ver = yf.getGlibcVersion()
        if float(glibc_ver) < 2.32:
            return '当前libc{}过低，需要大于2.31'.format(glibc_ver)
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
        print(getConf())
    elif func == 'run_log':
        print(runLog())
    elif func == 'config_tpl':
        print(configTpl())
    elif func == 'read_config_tpl':
        print(readConfigTpl())
    elif func == 'info':
        print(getGorseInfo())
    else:
        print('error')
