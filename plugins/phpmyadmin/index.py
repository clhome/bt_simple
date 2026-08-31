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

import core.yf as yf
import thisdb
from utils.site import sites as YfSites

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'phpmyadmin'


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


def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, 'k_f4104dc6' + ck[i] + ')没有!'))
    return (True, yf.returnJson(True, 'ok'))


def getConf():
    return yf.getServerDir() + '/web_conf/nginx/vhost/phpmyadmin.conf'


def getConfInc():
    return getServerDir() + "/" + getCfg()['path'] + '/config.inc.php'


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
        auth = cfg.get('username', 'admin') + ':' + cfg.get('password', 'admin')
        rand_path = cfg['path']
        url = 'http://' + auth + '@' + ip + ':' + port + '/' + rand_path + '/index.php'
        return yf.returnJson(True, 'OK', url)
    except Exception as e:
        return yf.returnJson(False, 'k_c3567d85')


def getPhpVer(expect=55):
    php_vers = YfSites.instance().getPhpVersion()
    v = php_vers['data']
    is_find = False
    for i in range(len(v)):
        t = str(v[i]['version'])
        if (t == expect):
            is_find = True
            return str(t)
        expect_str = str(expect)
        new_ex = expect_str[0:1]+"."+expect_str[1:2]
        if t.find(new_ex) > -1:
            is_find = True
            return str(t)
    if not is_find:
        if len(v) > 1:
            return v[1]['version']
        return v[0]['version']
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
    tmp = yf.execShell(
        'cat /dev/urandom | head -n 32 | md5sum | head -c 16')
    blowfish_secret = tmp[0].strip()
    # print php_ver
    php_conf_dir = yf.getServerDir() + '/web_conf/php/conf'
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$PHP_CONF_PATH}', php_conf_dir)
    content = content.replace('{$PHP_VER}', php_ver)
    content = content.replace('{$BLOWFISH_SECRET}', blowfish_secret)

    cfg = getCfg()

    if cfg['choose'] == "mysql":
        content = content.replace('{$CHOOSE_DB}', 'mysql')
        content = content.replace('{$CHOOSE_DB_DIR}', 'mysql')
    elif cfg['choose'] == "mysql-community":
        content = content.replace('{$CHOOSE_DB}', 'mysql-community')
        content = content.replace('{$CHOOSE_DB_DIR}', 'mysql-community')
    elif cfg['choose'] == "mysql-apt":
        content = content.replace('{$CHOOSE_DB}', 'mysql')
        content = content.replace('{$CHOOSE_DB_DIR}', 'mysql-apt')
    elif cfg['choose'] == "mysql-yum":
        content = content.replace('{$CHOOSE_DB}', 'mysql')
        content = content.replace('{$CHOOSE_DB_DIR}', 'mysql-yum')
    else:
        content = content.replace('{$CHOOSE_DB}', 'MariaDB')
        content = content.replace('{$CHOOSE_DB_DIR}', 'mariadb')

    content = content.replace('{$PMA_PATH}', cfg['path'])

    port = cfg["port"]
    rep = r'listen\s*(.*);'
    content = re.sub(rep, "listen " + port + ';', content)
    return content


def initCfg():
    cfg = getServerDir() + "/cfg.json"
    if not os.path.exists(cfg):
        data = {}
        data['port'] = '888'
        data['choose'] = 'mysql'
        data['path'] = ''
        data['username'] = yf.getRandomString(8)
        data['password'] = yf.getRandomString(10)
        yf.writeFile(cfg, json.dumps(data))


def setCfg(key, val):
    cfg = getServerDir() + "/cfg.json"
    data = {}
    if os.path.exists(cfg):
        try:
            data = json.loads(yf.readFile(cfg))
        except:
            data = {}
    data[key] = val
    yf.writeFile(cfg, json.dumps(data))


def getCfg():
    cfg = getServerDir() + "/cfg.json"
    if not os.path.exists(cfg):
        initCfg()
    data = {}
    try:
        data = json.loads(yf.readFile(cfg))
    except:
        initCfg()
        data = json.loads(yf.readFile(cfg))

    # 确保护盾随机子目录 (path) 存在且有效
    path = data.get('path', '').strip()
    server_dir = getServerDir()
    need_save = False

    # 兼容处理：如果已有的 path 带有 phpmyadmin_ 前缀，则去掉它并重命名物理目录
    if path.startswith('phpmyadmin_'):
        new_path = path.replace('phpmyadmin_', '', 1)
        if os.path.exists(server_dir + "/" + path):
            try:
                os.rename(server_dir + "/" + path, server_dir + "/" + new_path)
            except:
                yf.execShell("mv " + server_dir + "/" + path + " " + server_dir + "/" + new_path)
        path = new_path
        data['path'] = path
        need_save = True

    # 1. 确保配置中存在合法的 path
    if not path:
        path = yf.getRandomString(8).lower()
        data['path'] = path
        need_save = True

    # 2. 如果已配置的 path 存在且有效，直接返回
    if os.path.exists(server_dir + "/" + path):
        if need_save:
            try:
                yf.writeFile(cfg, json.dumps(data))
            except:
                pass
        return data

    # 3. 自动探测 server_dir 下只有一个目录时（因为去掉了前缀不好正则，且该目录下一般只有这一个主程序目录）
    found_path = ''
    if os.path.exists(server_dir):
        # 找除了 tmp 等已知系统目录外的唯一长随机字符串目录
        for item in os.listdir(server_dir):
            if item != 'tmp' and item != 'phpmyadmin' and os.path.isdir(os.path.join(server_dir, item)):
                if len(item) >= 4: # 假设保护目录至少4个字符
                    found_path = item
                    break
        
        # 4. 如果找到其他物理目录，纠正配置
        if found_path and found_path != path:
            data['path'] = found_path
            path = found_path
            need_save = True
        
        # 5. 如果没找到，但有 phpmyadmin 目录，重命名为当前配置的 path
        if not found_path and os.path.exists(server_dir + "/phpmyadmin") and os.path.isdir(server_dir + "/phpmyadmin"):
            dst = server_dir + "/" + path
            try:
                os.rename(server_dir + "/phpmyadmin", dst)
            except:
                yf.execShell("mv " + server_dir + "/phpmyadmin " + dst)

    if need_save:
        try:
            yf.writeFile(cfg, json.dumps(data))
        except:
            pass

    return data


def returnCfg():
    return json.dumps(getCfg())


def status():
    conf = getConf()
    pma_path = getCfg().get('path', '')
    conf_inc = getServerDir() + "/" + pma_path + '/config.inc.php'
    # 两个文件都在，才算启动成功
    if os.path.exists(conf) and os.path.exists(conf_inc):
        return 'start'
    return 'stop'


def __release_port(port):
    from collections import namedtuple
    try:
        from utils.firewall import Firewall as YfFirewall
        YfFirewall.instance().addAcceptPort(port, 'phpMyAdmin默认端口', 'port')
        return port
    except Exception as e:
        return "Release failed {}".format(e)


def __delete_port(port):
    from collections import namedtuple
    try:
        from utils.firewall import Firewall as YfFirewall
        YfFirewall.instance().delAcceptPortCmd(port, 'tcp')
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


def start():
    initCfg()
    openPort()

    file_tpl = getPluginDir() + '/conf/phpmyadmin.conf'
    file_run = getConf()
    if not os.path.exists(file_run):
        centent = yf.readFile(file_tpl)
        centent = contentReplace(centent)
        yf.writeFile(file_run, centent)

    pma_path = getServerDir() + '/pma.pass'
    cfg = getCfg()
    if not os.path.exists(pma_path):
        username = cfg.get('username') or yf.getRandomString(8)
        password = cfg.get('password') or yf.getRandomString(10)
        pass_cmd = username + ':' + yf.hasPwd(password)
        setCfg('username', username)
        setCfg('password', password)
        yf.writeFile(pma_path, pass_cmd)

    conf_inc = getConfInc()
    if not os.path.exists(conf_inc):
        conf_tpl = getPluginDir() + '/conf/config.inc.php'
        centent = yf.readFile(conf_tpl)
        centent = contentReplace(centent)
        yf.writeFile(conf_inc, centent)

    tmp = os.path.dirname(conf_inc) + '/tmp'
    if not os.path.exists(tmp):
        try:
            os.mkdir(tmp)
            yf.execShell("chown -R www:www " + tmp)
        except:
            pass

    log_a = accessLog()
    log_e = errorLog()

    for i in [log_a, log_e]:
        if os.path.exists(i):
            cmd = "echo '' > " + i
            yf.execShell(cmd)

    yf.restartWeb()
    return 'ok'


def stop():
    conf = getConf()
    if os.path.exists(conf):
        os.remove(conf)
    delPort()
    yf.restartWeb()
    return 'ok'


def restart():
    return start()


def reload():
    file_tpl = getPluginDir() + '/conf/phpmyadmin.conf'
    file_run = getConf()
    if os.path.exists(file_run):
        centent = yf.readFile(file_tpl)
        centent = contentReplace(centent)
        yf.writeFile(file_run, centent)
    return start()


def setPhpVer():
    args = getArgs()

    if not 'phpver' in args:
        return 'phpver missing'

    cacheFile = getServerDir() + '/php.pl'
    yf.writeFile(cacheFile, args['phpver'])

    file_tpl = getPluginDir() + '/conf/phpmyadmin.conf'
    file_run = getConf()

    content = yf.readFile(file_tpl)
    content = contentReplace(content)
    yf.writeFile(file_run, content)

    yf.restartWeb()
    return 'ok'


def getSetPhpVer():
    cacheFile = getServerDir() + '/php.pl'
    if os.path.exists(cacheFile):
        return yf.readFile(cacheFile).strip()
    return ''


def getPmaOption():
    data = getCfg()
    return yf.returnJson(True, 'ok', data)


def getPmaPort():
    try:
        port = getPort()
        return yf.returnJson(True, 'OK', port)
    except Exception as e:
        # print(e)
        return yf.returnJson(False, 'k_c3567d85')


def setPmaPort():
    args = getArgs()
    data = checkArgs(args, ['port'])
    if not data[0]:
        return data[1]

    port = args['port']
    if port == '80':
        return yf.returnJson(False, 'k_f87ed051')

    file = getConf()
    if not os.path.exists(file):
        return yf.returnJson(False, 'k_c3567d85')
    content = yf.readFile(file)
    rep = r'listen\s*(.*);'
    content = re.sub(rep, "listen " + port + ';', content)
    yf.writeFile(file, content)

    setCfg("port", port)
    yf.restartWeb()
    return yf.returnJson(True, 'k_9844f9b3')


def setPmaChoose():
    args = getArgs()
    data = checkArgs(args, ['choose'])
    if not data[0]:
        return data[1]

    choose = args['choose']
    setCfg('choose', choose)

    pma_path = getCfg()['path']
    conf_run = getServerDir() + "/" + pma_path + '/config.inc.php'

    conf_tpl = getPluginDir() + '/conf/config.inc.php'
    content = yf.readFile(conf_tpl)
    content = contentReplace(content)
    yf.writeFile(conf_run, content)

    yf.restartWeb()
    return yf.returnJson(True, 'k_9844f9b3')


def setPmaUsername():
    args = getArgs()
    data = checkArgs(args, ['username'])
    if not data[0]:
        return data[1]

    username = args['username']
    setCfg('username', username)

    cfg = getCfg()
    pma_path = getServerDir() + '/pma.pass'
    username = yf.getRandomString(10)
    pass_cmd = cfg['username'] + ':' + yf.hasPwd(cfg['password'])
    yf.writeFile(pma_path, pass_cmd)

    yf.restartWeb()
    return yf.returnJson(True, 'k_9844f9b3')


def setPmaPassword():
    args = getArgs()
    data = checkArgs(args, ['password'])
    if not data[0]:
        return data[1]

    password = args['password']
    setCfg('password', password)

    cfg = getCfg()
    pma_path = getServerDir() + '/pma.pass'
    username = yf.getRandomString(10)
    pass_cmd = cfg['username'] + ':' + yf.hasPwd(cfg['password'])
    yf.writeFile(pma_path, pass_cmd)

    yf.restartWeb()
    return yf.returnJson(True, 'k_9844f9b3')


def setPmaPath():
    args = getArgs()
    data = checkArgs(args, ['path'])
    if not data[0]:
        return data[1]

    path = args['path']

    if len(path) < 5:
        return yf.returnJson(False, 'k_e8f30f98')

    old_path = getServerDir() + "/" + getCfg()['path']
    new_path = getServerDir() + "/" + path

    yf.execShell("mv " + old_path + " " + new_path)
    setCfg('path', path)
    return yf.returnJson(True, 'k_9844f9b3')


def accessLog():
    return getServerDir() + '/access.log'


def errorLog():
    return getServerDir() + '/error.log'


def installVersion():
    return yf.readFile(getServerDir() + '/version.pl')

def pluginsDbSupport():
    data = {}

    data['installed'] = 'no'
    install_path = getServerDir()
    if not os.path.exists(install_path):
        return yf.returnJson(True, 'ok', data) 

    data['installed'] = 'ok'
    data['status'] = status()
    if (data['status'] == 'stop'):
        return yf.returnJson(True, 'ok', data)

    data['cfg'] = getCfg()
    port = getPort()
    ip = '127.0.0.1'
    if not yf.isAppleSystem():
        ip = thisdb.getOption('server_ip')

    cfg = data['cfg']
    auth = cfg['username']+':'+cfg['password']
    rand_path = cfg['path']
    home_page = 'http://' + auth + '@' + ip + ':' + port + '/' + rand_path + '/index.php'

    data['home_page'] = home_page
    data['version'] = installVersion().strip()

    return yf.returnJson(True, 'ok', data)

def installPreInspection():
    php_confdir = yf.getServerDir()+'/web_conf/php/conf'
    if not os.path.exists(php_confdir):
        return "必须先安装一个php版本!"
    return 'ok'

def getPmaAccessInfo():
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
        
        rand_path = cfg['path']
        
        data['internal_url'] = 'http://' + internal_ip + ':' + port + '/' + rand_path + '/index.php'
        data['external_url'] = 'http://' + external_ip + ':' + port + '/' + rand_path + '/index.php'
        data['username'] = cfg.get('username', 'admin')
        data['password'] = cfg.get('password', 'admin')
        data['path'] = rand_path
        return yf.returnJson(True, 'ok', data)
    except Exception as e:
        return yf.returnJson(False, 'k_c3567d85')

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
    elif func == 'version':
        print(installVersion())
    elif func == 'get_cfg':
        print(returnCfg())
    elif func == 'config_inc':
        print(getConfInc())
    elif func == 'get_home_page':
        print(getHomePage())
    elif func == 'set_php_ver':
        print(setPhpVer())
    elif func == 'get_set_php_ver':
        print(getSetPhpVer())
    elif func == 'get_pma_port':
        print(getPmaPort())
    elif func == 'set_pma_port':
        print(setPmaPort())
    elif func == 'get_pma_option':
        print(getPmaOption())
    elif func == 'set_pma_choose':
        print(setPmaChoose())
    elif func == 'set_pma_username':
        print(setPmaUsername())
    elif func == 'set_pma_password':
        print(setPmaPassword())
    elif func == 'set_pma_path':
        print(setPmaPath())
    elif func == 'access_log':
        print(accessLog())
    elif func == 'error_log':
        print(errorLog())
    elif func == 'plugins_db_support':
        print(pluginsDbSupport())
    elif func == 'get_pma_access_info':
        print(getPmaAccessInfo())
    else:
        print('error')
