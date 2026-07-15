# coding:utf-8

import sys
import io
import os
import time
import subprocess
import json
import re

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf


app_debug = False
if yf.isAppleSystem():
    app_debug = True


def is_valid_domain(domain):
    return bool(re.match(r'^[a-zA-Z0-9_*.-]+$', domain)) and not '..' in domain


def is_valid_upstream(name):
    return bool(re.match(r'^[a-zA-Z0-9_]+$', name))


def getPluginName():
    return 'op_load_balance'


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


def getConf():
    path = getServerDir() + "/cfg.json"

    if not os.path.exists(path):
        yf.writeFile(path, '[]')

    c = yf.readFile(path)
    return json.loads(c)


def writeConf(data):
    path = getServerDir() + "/cfg.json"
    yf.writeFile(path, json.dumps(data))


def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$APP_PATH}', app_path)
    return content


def restartWeb():
    yf.opWeb('stop')
    yf.opWeb('start')


def loadBalanceConf():
    path = yf.getServerDir() + '/web_conf/nginx/vhost/load_balance.conf'
    return path


def initDreplace():

    dst_conf_tpl = getPluginDir() + '/conf/load_balance.conf'
    dst_conf = loadBalanceConf()

    if not os.path.exists(dst_conf):
        con = yf.readFile(dst_conf_tpl)
        yf.writeFile(dst_conf, con)


def status():
    if not yf.getWebStatus():
        return 'stop'

    dst_conf = loadBalanceConf()
    if not os.path.exists(dst_conf):
        return 'stop'

    return 'start'


def start():
    initDreplace()
    restartWeb()
    return 'ok'


def stop():
    dst_conf = loadBalanceConf()
    os.remove(dst_conf)

    deleteLoadBalanceAllCfg()
    restartWeb()
    return 'ok'


def restart():
    restartWeb()
    return 'ok'


def reload():
    restartWeb()
    return 'ok'


def installPreInspection():
    check_op = yf.getServerDir() + "/openresty"
    if not os.path.exists(check_op):
        return "请先安装OpenResty"
    return 'ok'


def deleteLoadBalanceAllCfg():
    cfg = getConf()
    upstream_dir = yf.getServerDir() + '/web_conf/nginx/upstream'
    lua_dir = yf.getServerDir() + '/web_conf/nginx/lua/init_worker_by_lua_file'
    rewrite_dir = yf.getServerDir() + '/web_conf/nginx/rewrite'
    vhost_dir = yf.getServerDir() + '/web_conf/nginx/vhost'

    for conf in cfg:
        upstream_file = upstream_dir + '/' + conf['upstream_name'] + '.conf'
        if os.path.exists(upstream_file):
            os.remove(upstream_file)

        lua_file = lua_dir + '/' + conf['upstream_name'] + '.lua'
        if os.path.exists(lua_file):
            os.remove(lua_file)

        rewrite_file = rewrite_dir + '/' + conf['domain'] + '.conf'
        yf.writeFile(rewrite_file, '')

        path = vhost_dir + '/' + conf['domain'] + '.conf'

        content = yf.readFile(path)
        if isinstance(content, str):
            content = re.sub('include ' + upstream_file + ';' + "\n", '', content)
            yf.writeFile(path, content)

    yf.opLuaInitWorkerFile()


def makeConfServerList(data):
    slist = ''
    for x in data:
        slist += 'server '
        slist += x['ip'] + ':' + x['port']

        if x['state'] == '0':
            slist += ' down;\n\t'
            continue

        if x['state'] == '2':
            slist += ' backup;\n\t'
            continue

        slist += ' weight=' + x['weight']
        slist += ' max_fails=' + x['max_fails']
        slist += ' fail_timeout=' + x['fail_timeout'] + "s;\n\t"
    return slist


def makeLoadBalanceAllCfg(row):
    # 生成所有配置
    cfg = getConf()

    upstream_dir = yf.getServerDir() + '/web_conf/nginx/upstream'
    rewrite_dir = yf.getServerDir() + '/web_conf/nginx/rewrite'
    vhost_dir = yf.getServerDir() + '/web_conf/nginx/vhost'
    upstream_tpl = getPluginDir() + '/conf/upstream.tpl.conf'
    rewrite_tpl = getPluginDir() + '/conf/rewrite.tpl.conf'

    if not os.path.exists(upstream_dir):
        os.makedirs(upstream_dir)

    conf = cfg[row]

    # replace vhost start
    vhost_file = vhost_dir + '/' + conf['domain'] + '.conf'
    vcontent = yf.readFile(vhost_file)
    if not isinstance(vcontent, str):
        vcontent = ''

    vhost_find_str = 'upstream/' + conf['upstream_name'] + '.conf'
    vhead = 'include ' + yf.getServerDir() + '/web_conf/nginx/' + \
        vhost_find_str + ';'

    vpos = vcontent.find(vhost_find_str)
    if vpos < 0:
        vcontent = vhead + "\n" + vcontent
        yf.writeFile(vhost_file, vcontent)
    # replace vhost end

    # make upstream start
    upstream_file = upstream_dir + '/' + conf['upstream_name'] + '.conf'
    content = ''
    if len(conf['node_list']) > 0:
        content = yf.readFile(upstream_tpl)
        slist = makeConfServerList(conf['node_list'])
        content = content.replace('{$NODE_SERVER_LIST}', slist)
        content = content.replace('{$UPSTREAM_NAME}', conf['upstream_name'])
        if conf['node_algo'] != 'polling':
            content = content.replace('{$NODE_ALGO}', conf['node_algo'] + ';')
        else:
            content = content.replace('{$NODE_ALGO}', '')
    yf.writeFile(upstream_file, content)
    # make upstream end

    # make rewrite start
    rewrite_file = rewrite_dir + '/' + conf['domain'] + '.conf'
    rcontent = ''
    if len(conf['node_list']) > 0:
        rcontent = yf.readFile(rewrite_tpl)
        rcontent = rcontent.replace('{$UPSTREAM_NAME}', conf['upstream_name'])
    yf.writeFile(rewrite_file, rcontent)
    # make rewrite end

    # health check start
    lua_dir = yf.getServerDir() + '/web_conf/nginx/lua/init_worker_by_lua_file'
    lua_init_worker_file = lua_dir + '/' + conf['upstream_name'] + '.lua'
    if conf['node_health_check'] == 'ok':
        lua_dir_tpl = getPluginDir() + '/lua/health_check.lua.tpl'
        content = yf.readFile(lua_dir_tpl)
        content = content.replace('{$UPSTREAM_NAME}', conf['upstream_name'])
        content = content.replace('{$DOMAIN}', conf['domain'])
        yf.writeFile(lua_init_worker_file, content)
    else:
        if os.path.exists(lua_init_worker_file):
            os.remove(lua_init_worker_file)

    yf.opLuaInitWorkerFile()
    # health check end
    return True


def add_load_balance(args):

    data = checkArgs(
        args, ['domain', 'upstream_name', 'node_algo', 'node_list', 'node_health_check'])
    if not data[0]:
        return data[1]

    domain_json = args['domain']

    tmp = json.loads(domain_json)
    domain = tmp['domain']

    if not is_valid_domain(domain):
        return yf.returnJson(False, '域名格式不合法')

    if not is_valid_upstream(args['upstream_name']):
        return yf.returnJson(False, '负载名称格式不合法')

    try:
        nodes = args['node_list']
        if isinstance(nodes, str):
            nodes = json.loads(nodes)
        for x in nodes:
            if not is_valid_domain(x['ip']):
                return yf.returnJson(False, '节点IP/主机名不合法')
            if not re.match(r'^[0-9]+$', str(x['port'])):
                return yf.returnJson(False, '节点端口不合法')
    except Exception as e:
        pass

    cfg = getConf()
    cfg_len = len(cfg)
    tmp = {}
    tmp['domain'] = domain
    tmp['data'] = args['domain']
    tmp['upstream_name'] = args['upstream_name']
    tmp['node_algo'] = args['node_algo']
    tmp['node_list'] = args['node_list']
    tmp['node_health_check'] = args['node_health_check']
    cfg.append(tmp)
    writeConf(cfg)

    import site_api
    sobj = site_api.site_api()
    domain_path = yf.getWwwDir() + '/' + domain

    ps = '负载均衡[' + domain + ']'
    data = sobj.add(domain_json, '80', ps, domain_path, '00')

    makeLoadBalanceAllCfg(cfg_len)
    yf.restartWeb()
    return yf.returnJson(True, '添加成功', data)


def edit_load_balance(args):
    data = checkArgs(
        args, ['row', 'node_algo', 'node_list', 'node_health_check'])
    if not data[0]:
        return data[1]

    row = int(args['row'])

    cfg = getConf()
    tmp = cfg[row]
    tmp['node_algo'] = args['node_algo']
    tmp['node_list'] = args['node_list']
    tmp['node_health_check'] = args['node_health_check']
    cfg[row] = tmp
    writeConf(cfg)

    makeLoadBalanceAllCfg(row)
    yf.restartWeb()
    return yf.returnJson(True, '修改成功', data)


def loadBalanceList():
    cfg = getConf()
    return yf.returnJson(True, 'ok', cfg)


def loadBalanceDelete():
    args = getArgs()
    data = checkArgs(args, ['row'])
    if not data[0]:
        return data[1]

    row = int(args['row'])

    cfg = getConf()
    data = cfg[row]

    import site_api
    sobj = site_api.site_api()

    sid = yf.M('sites').where('name=?', (data['domain'],)).getField('id')

    if type(sid) == list:
        del(cfg[row])
        writeConf(cfg)
        return yf.returnJson(False, '已经删除了!')

    status = sobj.delete(sid, data['domain'], 1)
    status_data = json.loads(status)

    if status_data['status']:
        del(cfg[row])
        writeConf(cfg)

    upstream_dir = yf.getServerDir() + '/web_conf/nginx/upstream'
    rewrite_dir = yf.getServerDir() + '/web_conf/nginx/rewrite'

    upstream_file = upstream_dir + '/' + data['upstream_name'] + '.conf'
    if os.path.exists(upstream_file):
        os.remove(upstream_file)

    rewrite_file = rewrite_dir + '/' + data['domain'] + '.conf'
    if os.path.exists(rewrite_file):
        yf.writeFile(rewrite_file, '')

    return yf.returnJson(status_data['status'], status_data['msg'])


def http_get(url):
    import urllib.request
    import ssl
    try:
        context = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5, context=context) as response:
            status = [200, 301, 302, 404, 403]
            if response.getcode() in status:
                return True
            return False
    except Exception as e:
        return False


def checkUrl():
    args = getArgs()
    data = checkArgs(args, ['ip', 'port', 'path'])
    if not data[0]:
        return data[1]

    ip = args['ip']
    port = args['port']
    path = args['path']

    if port == '443':
        url = 'https://' + str(ip) + ':' + str(port) + str(path.strip())
    else:
        url = 'http://' + str(ip) + ':' + str(port) + str(path.strip())
    ret = http_get(url)
    if not ret:
        return yf.returnJson(False, '访问节点[%s]失败' % url)
    return yf.returnJson(True, '访问节点[%s]成功' % url)


def getHealthStatus():
    args = getArgs()
    data = checkArgs(args, ['row'])
    if not data[0]:
        return data[1]

    row = int(args['row'])

    cfg = getConf()
    data = cfg[row]

    url = 'http://' + data['domain'] + \
        '/upstream_status_' + data['upstream_name']

    url_data = yf.httpGet(url)
    return yf.returnJson(True, 'ok', json.loads(url_data))


def getLogs():
    args = getArgs()
    data = checkArgs(args, ['domain'])
    if not data[0]:
        return data[1]

    domain = args['domain']
    logs = yf.getLogsDir() + '/' + domain + '.log'
    return logs

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
    elif func == 'add_load_balance':
        args = getArgs()
        print(add_load_balance(args))
    elif func == 'edit_load_balance':
        args = getArgs()
        print(edit_load_balance(args))
    elif func == 'load_balance_list':
        print(loadBalanceList())
    elif func == 'load_balance_delete':
        print(loadBalanceDelete())
    elif func == 'check_url':
        print(checkUrl())
    elif func == 'get_logs':
        print(getLogs())
    elif func == 'get_health_status':
        print(getHealthStatus())
    else:
        print('error')
