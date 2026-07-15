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
    return 'sphinx'

def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()

sys.path.append(getPluginDir() +"/class")

def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getInitDFile():
    if app_debug:
        return '/tmp/' + getPluginName()
    return '/etc/init.d/' + getPluginName()


def getConfTpl():
    path = getPluginDir() + "/conf/sphinx.conf"
    return path


def getConf():
    path = getServerDir() + "/sphinx.conf"
    return path


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)

    if args_len == 0:
        return tmp

    if args_len == 1:
        val = args[0].strip()
        if val.startswith('{') and val.endswith('}'):
            try:
                import json
                return json.loads(val)
            except Exception as e:
                pass

    for i in range(len(args)):
        t = args[i].split(':', 1)
        if len(t) == 2:
            tmp[t[0]] = t[1]
        elif len(t) == 1:
            tmp[t[0]] = ''
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


def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$SERVER_APP}', service_path + '/'+getPluginName())
    return content


def status():
    data = yf.execShell(
        "ps -ef|grep sphinx |grep -v grep | grep -v mdserver-web | awk '{print $2}'")
    # print(data)
    if data[0] == '':
        return 'stop'
    return 'start'


def mkdirAll():
    content = yf.readFile(getConf())
    rep = r'path\s*=\s*(.*)'
    p = re.compile(rep)
    tmp = p.findall(content)

    for x in tmp:
        if x.find('binlog') != -1:
            yf.makeDirs(x)
        else:
            yf.makeDirs(os.path.dirname(x))


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
        yf.writeFile(getServerDir() + '/sphinx.conf', conf_content)

    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/sphinx.service'
    systemServiceTpl = getPluginDir() + '/init.d/sphinx.service.tpl'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        se_content = yf.readFile(systemServiceTpl)
        se_content = se_content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(systemService, se_content)
        yf.execShell('systemctl daemon-reload')

    mkdirAll()
    return file_bin


def checkIndexSph():
    content = yf.readFile(getConf())
    rep = r'path\s*=\s*(.*)'
    p = re.compile(rep)
    tmp = p.findall(content)
    for x in tmp:
        if x.find('binlog') != -1:
            continue
        else:
            p = x + '.sph'
            if os.path.exists(p):
                return False
    return True


def sphOp(method):
    file = initDreplace()

    if not yf.isAppleSystem():
        data = yf.execShell('systemctl ' + method + ' ' + getPluginName())
        if data[1] == '':
            return 'ok'
        return 'fail'

    data = yf.execShell(file + ' ' + method)
    if data[1] == '':
        return 'ok'
    return data[1]


def start():
    import tool_cron
    tool_cron.createBgTask()
    return sphOp('start')


def stop():
    import tool_cron
    tool_cron.removeBgTask()
    return sphOp('stop')


def restart():
    return sphOp('restart')


def reload():
    return sphOp('reload')


def rebuild():
    file = initDreplace()
    cmd = file + ' rebuild'
    data = yf.execShell(cmd)
    if data[0].find('successfully')<0:
        return data[0].replace("\n","<br/>")
    return 'ok'


def initdStatus():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    shell_cmd = 'systemctl status sphinx | grep loaded | grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    yf.execShell('systemctl enable sphinx')
    return 'ok'


def initdUinstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    yf.execShell('systemctl disable sphinx')
    return 'ok'


def runLog():
    path = getConf()
    content = yf.readFile(path)
    rep = r'log\s*=\s*(.*)'
    tmp = re.search(rep, content)
    return tmp.groups()[0]


def getPort():
    path = getConf()
    content = yf.readFile(path)
    rep = r'listen\s*=\s*(.*)'
    tmp = re.search(rep, content)
    return tmp.groups()[0]


def queryLog():
    path = getConf()
    content = yf.readFile(path)
    rep = r'query_log\s*=\s*(.*)'
    tmp = re.search(rep, content)
    return tmp.groups()[0]


def runStatus():
    s = status()
    if s != 'start':
        return yf.returnJson(False, '没有启动程序')

    sys.path.append(getPluginDir() + "/class")
    import sphinxapi

    sh = sphinxapi.SphinxClient()
    port = getPort()
    sh.SetServer('127.0.0.1', port)
    info_status = sh.Status()

    rData = {}
    for x in range(len(info_status)):
        rData[info_status[x][0]] = info_status[x][1]

    return yf.returnJson(True, 'ok', rData)


def sphinxConfParse():
    file = getConf()
    bin_dir = getServerDir()
    content = yf.readFile(file)
    rep = r'index\s(.*)'
    sindex = re.findall(rep, content)
    indexlen = len(sindex)
    cmd = {}
    cmd['cmd'] = bin_dir + '/bin/bin/indexer -c ' + bin_dir + '/sphinx.conf'

    cmd['index'] = []
    cmd_index = []
    cmd_delta = []
    if indexlen > 0:
        for x in range(indexlen):
            name = sindex[x].strip()
            if name == '':
                continue
            if  name.find(':') != -1:
                cmd_delta.append(name.strip())
            else:
                cmd_index.append(name.strip())

    # print(cmd_index)
    # print(cmd_delta)

    for ci in cmd_index:
        val = {}
        val['index'] = ci

        for cd in cmd_delta:
            cd = cd.replace(" ", '')
            if cd.find(":"+ci) > -1:
                val['delta'] = cd.split(":")[0].strip()
                break

        cmd['index'].append(val)
    return cmd


def sphinxCmd():
    data = sphinxConfParse()
    if 'index' in data:
        return yf.returnJson(True, 'ok', data)
    else:
        return yf.returnJson(False, 'no index')

def makeDbToSphinxTest():        
    conf_file = getConf()
    import  sphinx_make
    sph_make = sphinx_make.sphinxMake()
    conf = sph_make.makeSqlToSphinxAll()

    yf.writeFile(conf_file,conf)
    print(conf)
    # makeSqlToSphinxTable()
    return True

def makeDbToSphinx():
    args = getArgs()
    check = checkArgs(args, ['db','tables','is_delta','is_cover'])
    if not check[0]:
        return check[1]

    db = args['db']
    tables = args['tables']
    is_delta = args['is_delta']
    is_cover = args['is_cover']

    if is_cover != 'yes':
        return yf.returnJson(False,'暂时仅支持覆盖!')

    sph_file = getConf()

    import  sphinx_make
    sph_make = sphinx_make.sphinxMake()

    version_pl = getServerDir() + "/version.pl"
    if os.path.exists(version_pl):
        version = yf.readFile(version_pl).strip()
        sph_make.setVersion(version)

    if not sph_make.checkDbName(db):
        return yf.returnJson(False,'保留数据库名称,不可用!')
    is_delta_bool = False
    if is_delta == 'yes':
        is_delta_bool = True
    if is_cover == 'yes':
        tables = tables.split(',')
        content = sph_make.makeSqlToSphinx(db, tables, is_delta_bool)
        yf.writeFile(sph_file,content)
        mkdirAll()
        return yf.returnJson(True,'设置成功!')

    return yf.returnJson(True,'测试中')


# 全量更新
def updateAll():
    data = sphinxConfParse()
    cmd = data['cmd']
    if not 'index' in data:
        return '无更新'
    index = data['index']

    pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
    for x in range(len(index)):
        idx_name = index[x]['index']
        if not pattern.match(idx_name):
            print("安全拦截: 非法的索引名称 ->", idx_name)
            continue
        cmd_index = cmd + ' ' + idx_name + ' --rotate'
        print(cmd_index)
        os.system(cmd_index)
    return ''

#增量更新
def updateDelta():
    data = sphinxConfParse()
    cmd = data['cmd']
    if not 'index' in data:
        return '无更新'
    index = data['index']

    pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
    for x in range(len(index)):
        idx_name = index[x]['index']
        if not pattern.match(idx_name):
            print("安全拦截: 非法的索引名称 ->", idx_name)
            continue

        if 'delta' in index[x]:
            delta_name = index[x]['delta']
            if not pattern.match(delta_name):
                print("安全拦截: 非法的增量索引名称 ->", delta_name)
                continue
            cmd_index = cmd + ' ' + delta_name + ' --rotate'
            print(cmd_index)
            os.system(cmd_index)

            cmd_index_merge = cmd + ' --merge ' + idx_name + ' ' + delta_name + ' --rotate'
            print(cmd_index_merge)
            os.system(cmd_index_merge)
        else:
            print(idx_name,'no delta')

    return ''

def installPreInspection(version):
    if yf.isAppleSystem():
        return 'ok'
    data = yf.execShell('arch')
    if data[0].strip().startswith('aarch'):
        return '不支持aarch架构'
    return 'ok'

if __name__ == "__main__":
    version = "3.1.1"
    version_pl = getServerDir() + "/version.pl"
    if os.path.exists(version_pl):
        version = yf.readFile(version_pl).strip()

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
    elif func == 'rebuild':
        print(rebuild())
    elif func == 'initd_status':
        print(initdStatus())
    elif func == 'initd_install':
        print(initdInstall())
    elif func == 'initd_uninstall':
        print(initdUinstall())
    elif func == 'install_pre_inspection':
        print(installPreInspection(version))
    elif func == 'conf':
        print(getConf())
    elif func == 'config_tpl':
        print(configTpl())
    elif func == 'read_config_tpl':
        print(readConfigTpl())
    elif func == 'run_log':
        print(runLog())
    elif func == 'query_log':
        print(queryLog())
    elif func == 'run_status':
        print(runStatus())
    elif func == 'sphinx_cmd':
        print(sphinxCmd())
    elif func == 'db_to_sphinx':
        print(makeDbToSphinx())
    elif func == 'update_all':
        print(updateAll())
    elif func == 'update_delta':
        print(updateDelta())
    else:
        print('error')
