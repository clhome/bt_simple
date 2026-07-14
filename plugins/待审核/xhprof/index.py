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

import core.mw as mw
from utils.site import sites as MwSites

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'xhprof'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        val = args[0].strip().strip("'").strip('"')
        if val.startswith('{') and val.endswith('}'):
            try:
                return json.loads(val)
            except Exception as e:
                pass
        t = val.strip('{').strip('}').split(':')
        if len(t) >= 2:
            tmp[t[0].strip().strip('"').strip("'")] = t[1].strip().strip('"').strip("'")
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].strip().strip("'").strip('"').split(':')
            if len(t) >= 2:
                tmp[t[0].strip().strip('"').strip("'")] = t[1].strip().strip('"').strip("'")

    return tmp


def getConf():
    return yf.getServerDir() + '/web_conf/nginx/vhost/xhprof.conf'


def getPort():
    file = getConf()
    content = yf.readFile(file)
    rep = r'listen\s*(.*);'
    tmp = re.search(rep, content)
    return tmp.groups()[0].strip()


def getHomePage():
    try:
        port = getPort()
        ip = '127.0.0.1'
        if not yf.isAppleSystem():
            ip = yf.getLocalIp()
        url = 'http://' + ip + ':' + port + '/index.php'
        return yf.returnJson(True, 'OK', url)
    except Exception as e:
        return yf.returnJson(False, '插件未启动!')


def getPhpVer(expect=74):
    php_vers = MwSites.instance().getPhpVersion()
    v = php_vers['data']
    for i in range(len(v)):
        t = int(v[i]['version'])
        if (t >= expect):
            return str(t)
    return str(expect)


def getCachePhpVer():
    cacheFile = getServerDir() + '/php.pl'
    v = ''
    if os.path.exists(cacheFile):
        v = yf.readFile(cacheFile)
    else:
        v = getPhpVer()
        yf.writeFile(cacheFile, v)
    return v


def contentReplace(content):
    service_path = yf.getServerDir()
    php_ver = getCachePhpVer()
    # print php_ver
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$PHP_VER}', php_ver)
    content = content.replace('{$LOCAL_IP}', yf.getLocalIp())
    return content


def contentReplacePHP(content, version):
    service_path = yf.getServerDir()
    # print php_ver
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$PHP_VER}', version)
    return content


def status():
    conf = getConf()
    if os.path.exists(conf):
        return 'start'
    return 'stop'

def getConfAppStart():
    pstart = yf.getServerDir() + '/php/app_start.php'
    return pstart


def phpPrependFile():
    app_start = getConfAppStart()
    tpl = yf.getPluginDir() + '/php/conf/app_start.php'
    content = yf.readFile(tpl)
    content = contentReplace(content)
    yf.writeFile(app_start, content)
    return True

def start():
    phpPrependFile()

    file_tpl = getPluginDir() + '/conf/xhprof.conf'
    file_run = getConf()

    if not os.path.exists(file_run):
        centent = yf.readFile(file_tpl)
        centent = contentReplace(centent)
        yf.writeFile(file_run, centent)

    yf.restartWeb()
    return 'ok'


def stop():
    conf = getConf()
    if os.path.exists(conf):
        os.remove(conf)
    yf.restartWeb()
    return 'ok'


def restart():
    return start()


def reload():
    return start()


def setPhpVer():
    args = getArgs()

    if not 'phpver' in args:
        return 'phpver missing'

    cacheFile = getServerDir() + '/php.pl'
    yf.writeFile(cacheFile, args['phpver'])

    file_tpl = getPluginDir() + '/conf/xhprof.conf'
    file_run = getConf()

    content = yf.readFile(file_tpl)
    content = contentReplacePHP(content, args['phpver'])
    yf.writeFile(file_run, content)

    yf.restartWeb()
    return 'ok'


def getSetPhpVer():
    cacheFile = getServerDir() + '/php.pl'
    if os.path.exists(cacheFile):
        return yf.readFile(cacheFile).strip()
    return ''


def getXhPort():
    try:
        port = getPort()
        return yf.returnJson(True, 'OK', port)
    except Exception as e:
        return yf.returnJson(False, '插件未启动!')


def setXhPort():
    args = getArgs()
    if not 'port' in args:
        return yf.returnJson(False, 'port missing!')

    port = args['port']
    if port == '80':
        return yf.returnJson(False, '80端不能使用!')

    file = getConf()
    if not os.path.exists(file):
        return yf.returnJson(False, '插件未启动!')
    content = yf.readFile(file)
    rep = r'listen\s*(.*);'
    content = re.sub(rep, "listen " + port + ';', content)
    yf.writeFile(file, content)
    yf.restartWeb()
    return yf.returnJson(True, '修改成功!')


def installPreInspection():
    path = yf.getServerDir() + '/php'
    if not os.path.exists(path):
        return "先安装一个可用的PHP版本!"
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
    elif func == 'install_pre_inspection':
        print(installPreInspection())
    elif func == 'conf':
        print(getConf())
    elif func == 'get_home_page':
        print(getHomePage())
    elif func == 'set_php_ver':
        print(setPhpVer())
    elif func == 'get_set_php_ver':
        print(getSetPhpVer())
    elif func == 'get_xhprof_port':
        print(getXhPort())
    elif func == 'set_xhprof_port':
        print(setXhPort())
    elif func == 'app_start':
        print(getConfAppStart())
    else:
        print('error')
