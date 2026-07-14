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

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'pgadmin'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


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


def getConf():
    return yf.getServerDir() + '/web_conf/nginx/vhost/pgadmin.conf'


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

        cfg = getCfg()
        auth = cfg['username']+':'+cfg['password']
        url = 'http://' + auth + '@' + ip + ':' + port + '/'
        return yf.returnJson(True, 'OK', url)
    except Exception as e:
        return yf.returnJson(False, '插件未启动!')



def contentReplace(content):
    cfg = getCfg()
    service_path = yf.getServerDir()

    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$APP_PATH}', service_path+'/'+getPluginName()+'/data')

    port = cfg["port"]
    rep = r'listen\s*(.*);'
    content = re.sub(rep, "listen " + port + ';', content)
    return content


def initCfg():
    cfg = getServerDir() + "/cfg.json"
    if not os.path.exists(cfg):
        data = {}
        data['port'] = '5051'
        data['path'] = ''
        data['username'] = 'admin'
        data['password'] = 'admin'

        data['web_pg_username'] = 'yftec@gmail.com'
        data['web_pg_password'] = 'admin'
        yf.writeFile(cfg, json.dumps(data))


def setCfg(key, val):
    cfg = getServerDir() + "/cfg.json"
    data = yf.readFile(cfg)
    data = json.loads(data)
    data[key] = val
    yf.writeFile(cfg, json.dumps(data))


def getCfg():
    cfg = getServerDir() + "/cfg.json"
    data = yf.readFile(cfg)
    data = json.loads(data)
    return data


def returnCfg():
    cfg = getServerDir() + "/cfg.json"
    data = yf.readFile(cfg)
    return data


def __release_port(port):
    from collections import namedtuple
    try:
        from utils.firewall import Firewall as MwFirewall
        MwFirewall.instance().addAcceptPort(port, 'pgAdmin默认端口', 'port')
        return port
    except Exception as e:
        return "Release failed {}".format(e)


def __delete_port(port):
    from collections import namedtuple
    try:
        from utils.firewall import Firewall as MwFirewall
        MwFirewall.instance().delAcceptPort(port, 'tcp')
        return port
    except Exception as e:
        return "Release failed {}".format(e)


def openPort():
    conf = getCfg()
    port = conf['port']
    for i in [port]:
        __release_port(i)
    return True


def delPort():
    conf = getCfg()
    port = conf['port']
    for i in [port]:
        __delete_port(i)
    return True


def cleanNginxLog():
    log_a = accessLog()
    log_e = errorLog()

    for i in [log_a, log_e]:
        if os.path.exists(i):
            cmd = "echo '' > " + i
            yf.execShell(cmd)

def getPythonName():
    cmd = "ls /www/server/pgadmin/run/lib/ | grep python | cut -d \\  -f 1 | awk 'END {print}'"
    data = yf.execShell(cmd)
    return data[0].strip();

def initPgConfFile():
    pyname = getPythonName()
    file_tpl = getPluginDir() + '/conf/config_local.py'
    dst_file = getServerDir()+'/run/lib/'+pyname+'/site-packages/pgadmin4/config_local.py'
    if not os.path.exists(dst_file):
        service_path = yf.getServerDir()
        content = yf.readFile(file_tpl)
        content = content.replace('{$DATA_PATH}', service_path+'/'+getPluginName()+'/data')
        yf.writeFile(dst_file, content)


def initReplace():
    initPgConfFile()

    file_tpl = getPluginDir() + '/conf/pgadmin.conf'
    file_run = getConf()
    if not os.path.exists(file_run):
        content = yf.readFile(file_tpl)
        content = contentReplace(content)
        yf.writeFile(file_run, content)

    pass_path = getServerDir() + '/pg.pass'
    if not os.path.exists(pass_path):
        username = yf.getRandomString(8)
        password = yf.getRandomString(10)
        pass_cmd = username + ':' + yf.hasPwd(password)
        setCfg('username', username)
        setCfg('password', password)
        yf.writeFile(pass_path, pass_cmd)

    # pg_conf = getCfg()
    judge_file = getServerDir()+'/data/pgadmin4/pgadmin4.db'
    if not os.path.exists(judge_file):
        pg_init_bash = getPluginDir()+'/pg_init.sh'
        pg_rand = yf.getRandomString(8)
        pg_username = "yftec_"+pg_rand+"@gmail.com"
        setCfg('web_pg_username', pg_username)
        pg_password = yf.getRandomString(10)
        setCfg('web_pg_password', pg_password)
        t = yf.execShell("bash "+ pg_init_bash + " " + pg_username + " " + pg_password)
        # print(t)

    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/pgadmin.service'

    if os.path.exists(systemDir) and not os.path.exists(systemService):
        systemServiceTpl = getPluginDir() + '/init.d/pgadmin.service.tpl'
        service_path = yf.getServerDir()
        content = yf.readFile(systemServiceTpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        content = content.replace('{$PY_VER}', getPythonName())

        
        yf.writeFile(systemService, content)
        yf.execShell('systemctl daemon-reload')


def pgOp(method):
    file = initReplace()

    current_os = yf.getOs()
    if current_os == "darwin":
        return 'ok'

    if current_os.startswith("freebsd"):
        data = yf.execShell('service' + getPluginName() + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    data = yf.execShell('systemctl ' + method+ ' ' + getPluginName())
    if data[1] == '':
        return 'ok'
    return data[1]

def status():
    sock = '/tmp/pgadmin4.sock'
    if os.path.exists(sock):
        return 'start'
    return 'stop'


def start():
    initCfg()
    openPort()

    pgOp('start')

    yf.restartWeb()
    return 'ok'


def stop():
    pgOp('stop')

    conf = getConf()
    if os.path.exists(conf):
        os.remove(conf)

    delPort()
    yf.restartWeb()
    return 'ok'


def restart():
    cleanNginxLog()
    state = pgOp('restart')
    yf.restartWeb()
    return state


def reload():
    cleanNginxLog()
    return pgOp('reload')

def getPgOption():
    data = getCfg()
    return yf.returnJson(True, 'ok', data)


def getPgPort():
    try:
        port = getPort()
        return yf.returnJson(True, 'OK', port)
    except Exception as e:
        # print(e)
        return yf.returnJson(False, '插件未启动!')


def setPgPort():
    args = getArgs()
    data = checkArgs(args, ['port'])
    if not data[0]:
        return data[1]

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

    setCfg("port", port)
    yf.restartWeb()
    return yf.returnJson(True, '修改成功!')


def setPgUsername():
    args = getArgs()
    data = checkArgs(args, ['username'])
    if not data[0]:
        return data[1]

    username = args['username']
    setCfg('username', username)

    cfg = getCfg()
    pma_path = getServerDir() + '/pg.pass'
    username = yf.getRandomString(10)
    pass_cmd = cfg['username'] + ':' + yf.hasPwd(cfg['password'])
    yf.writeFile(pma_path, pass_cmd)

    yf.restartWeb()
    return yf.returnJson(True, '修改成功!')


def setPgPassword():
    args = getArgs()
    data = checkArgs(args, ['password'])
    if not data[0]:
        return data[1]

    password = args['password']
    setCfg('password', password)

    cfg = getCfg()
    pma_path = getServerDir() + '/pg.pass'
    username = yf.getRandomString(10)
    pass_cmd = cfg['username'] + ':' + yf.hasPwd(cfg['password'])
    yf.writeFile(pma_path, pass_cmd)

    yf.restartWeb()
    return yf.returnJson(True, '修改成功!')


def accessLog():
    return getServerDir() + '/access.log'

def errorLog():
    return getServerDir() + '/error.log'


def installVersion():
    return yf.readFile(getServerDir() + '/version.pl')

def getPgAccessInfo():
    try:
        data = {}
        cfg = getCfg()
        port = getPort()
        
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            internal_ip = s.getsockname()[0]
            s.close()
        except:
            internal_ip = '127.0.0.1'
            
        try:
            external_ip = yf.getHostAddr()
        except:
            external_ip = internal_ip
        
        data['internal_url'] = 'http://' + internal_ip + ':' + port + '/'
        data['external_url'] = 'http://' + external_ip + ':' + port + '/'
        data['username'] = cfg['username']
        data['password'] = cfg['password']
        data['web_pg_username'] = cfg.get('web_pg_username', '')
        data['web_pg_password'] = cfg.get('web_pg_password', '')
        return yf.returnJson(True, 'ok', data)
    except Exception as e:
        return yf.returnJson(False, '插件未启动!')

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
    elif func == 'conf':
        print(getConf())
    elif func == 'version':
        print(installVersion())
    elif func == 'get_cfg':
        print(returnCfg())
    elif func == 'get_home_page':
        print(getHomePage())
    elif func == 'get_pg_port':
        print(getPgPort())
    elif func == 'set_pg_port':
        print(setPgPort())
    elif func == 'get_pg_option':
        print(getPgOption())
    elif func == 'set_pg_username':
        print(setPgUsername())
    elif func == 'set_pg_password':
        print(setPgPassword())
    elif func == 'access_log':
        print(accessLog())
    elif func == 'error_log':
        print(errorLog())
    elif func == 'get_pg_access_info':
        print(getPgAccessInfo())
    else:
        print('error')
