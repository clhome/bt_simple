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
import logging

_log = logging.getLogger('yf.op_load_balance')


app_debug = False
if yf.isAppleSystem():
    app_debug = True

# ---------------------------------------------------------------------------------
# 输入白名单
# ---------------------------------------------------------------------------------
# domain / upstream_name / 节点字段都会被拼进 nginx 配置的**文件名**与 upstream 指令，
# 而这些配置落在生产 openresty 的 include 目录（web_conf/nginx/vhost|upstream|rewrite）。
# 只要放行一个换行或分号，就等于「任意 nginx 指令注入」；放行 `../` 就等于任意文件写。
# 因此逐字段白名单 + 数值范围校验，校验失败一律如实报错，绝不落盘。
_DOMAIN_RE = re.compile(r'^(\*\.)?[a-zA-Z0-9_]([a-zA-Z0-9_.\-]{0,251}[a-zA-Z0-9_])?$')
_UPSTREAM_RE = re.compile(r'^[a-zA-Z0-9_]{1,64}$')
_HOST_RE = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9\-._]{0,251}[a-zA-Z0-9])?$')
_IPV4_RE = re.compile(r'^\d{1,3}(\.\d{1,3}){3}$')
_PATH_RE = re.compile(r'^/[^\s\r\n]*$')
_NODE_ALGO = ('polling', 'ip_hash', 'fair', 'url_hash', 'least_conn')
_NODE_STATE = ('0', '1', '2')
_HEALTH_CHECK = ('ok', 'fail')


def _toInt(value, low=None, high=None):
    """把前端来的字符串收敛成 int；非数字/越界回 None（调用方负责如实报错）。"""
    if isinstance(value, bool):
        return None
    try:
        num = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if low is not None and num < low:
        return None
    if high is not None and num > high:
        return None
    return num


def is_valid_domain(domain):
    if not isinstance(domain, str):
        return False
    # 空白/控制字符（尤其换行）先于 strip 拒绝：strip 会把 'a.com\n' 洗成合法域名，
    # 而域名是要拼进配置文件名与 nginx 指令的。
    if re.search(r'\s', domain):
        return False
    if not domain or len(domain) > 253 or '..' in domain:
        return False
    return bool(_DOMAIN_RE.match(domain))


def is_valid_upstream(name):
    if not isinstance(name, str):
        return False
    return bool(_UPSTREAM_RE.match(name.strip()))


def is_valid_node_host(host):
    """节点地址：IPv4 / IPv6 / 主机名，必须是单行（换行会注入任意 upstream 指令）。"""
    if not isinstance(host, str):
        return False
    if re.search(r'\s', host):
        return False
    if not host or len(host) > 253:
        return False
    if ':' in host:
        import ipaddress
        try:
            ipaddress.IPv6Address(host)
            return True
        except Exception as e:
            _log.debug('[op_load_balance] 节点地址不是合法 IPv6: %s', e)
            return False
    if _IPV4_RE.match(host):
        import ipaddress
        try:
            ipaddress.IPv4Address(host)
            return True
        except Exception as e:
            _log.debug('[op_load_balance] 节点地址不是合法 IPv4: %s', e)
            return False
    if '..' in host:
        return False
    # 纯数字+点的串只能是 IPv4：'1.2.3.4.5' 这种当成主机名放过去，
    # 生成的 upstream 在 nginx 启动时就是 host not found。
    if re.match(r'^[0-9.]+$', host):
        return False
    return bool(_HOST_RE.match(host))


def is_valid_node_path(path):
    """节点验证路径：必须是绝对路径且单行（它会拼进探测 URL）。"""
    if not isinstance(path, str):
        return False
    return bool(_PATH_RE.match(path.strip()))


def getPluginName():
    return 'op_load_balance'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getRestyBin():
    return yf.getServerDir() + '/openresty/nginx/sbin/nginx'


def isInstalled():
    """OpenResty 未安装时本插件没有任何可生效的落点，不得凭空造安装产物。"""
    return os.path.exists(getRestyBin())


def webRunning():
    """openresty 是否真在运行：pid 文件存在 **且** pid 存活（陈旧 pid 不得报 start）。"""
    if not isInstalled():
        return False
    pid_file = yf.getServerDir() + '/openresty/nginx/logs/nginx.pid'
    content = yf.readFile(pid_file)
    if not isinstance(content, str) or not content.strip():
        return False
    return bool(yf.checkPid(content.strip()))


def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)
    if args_len == 0:
        return tmp

    # 面板 plugin.run() 只传**一个** argv（前端 YfPlugin.parseArgs 序列化的 JSON）。
    # 旧实现按 `k:v` 硬切，JSON 里的引号与冒号会被切碎（键变成 '"ip"'），
    # 于是带参接口全部静默回「缺少必要参数」；畸形 argv 还会 IndexError 回前端。
    val = args[0].strip()
    if val.startswith('{') and val.endswith('}'):
        try:
            data = json.loads(val)
            if isinstance(data, dict):
                return data
        except Exception as e:
            _log.debug('[op_load_balance] getArgs JSON 解析失败: %s', e)

    for i in range(args_len):
        t = args[i].split(':', 1)
        if len(t) == 2:
            tmp[t[0]] = t[1]
    return tmp


def checkArgs(data, ck=None):
    if ck is None:
        ck = []
    if not isinstance(data, dict):
        data = {}
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


def getConf():
    path = getServerDir() + "/cfg.json"

    # 只读接口（load_balance_list / status）不得凭空建出插件目录
    if not os.path.exists(path):
        return []

    content = yf.readFile(path)
    if not isinstance(content, str) or not content.strip():
        return []
    try:
        data = json.loads(content)
    except Exception as e:
        _log.debug('[op_load_balance] cfg.json 解析失败: %s', e)
        return []
    return data if isinstance(data, list) else []


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
    """重启面板 web 服务；返回是否真的执行（旧实现丢弃返回值 → 假成功）。"""
    if not isInstalled():
        return False
    if not yf.opWeb('stop'):
        return False
    return bool(yf.opWeb('start'))


def loadBalanceConf():
    path = yf.getServerDir() + '/web_conf/nginx/vhost/load_balance.conf'
    return path


def initDreplace():

    if not isInstalled():
        return 'ERROR: 请先安装OpenResty'

    dst_conf_tpl = getPluginDir() + '/conf/load_balance.conf'
    dst_conf = loadBalanceConf()

    if not os.path.exists(dst_conf):
        con = yf.readFile(dst_conf_tpl)
        if not isinstance(con, str) or not con.strip():
            return 'ERROR: 配置文件模板不存在'
        yf.writeFile(dst_conf, con)
    return 'ok'


def status():
    if not isInstalled():
        return 'stop'
    if not webRunning():
        return 'stop'

    dst_conf = loadBalanceConf()
    if not os.path.exists(dst_conf):
        return 'stop'

    return 'start'


def start():
    res = initDreplace()
    if isinstance(res, str) and res.startswith('ERROR:'):
        return res
    if not restartWeb():
        return 'ERROR: OpenResty 启动失败'
    return 'ok'


def stop():
    if not isInstalled():
        return 'ERROR: 请先安装OpenResty'

    dst_conf = loadBalanceConf()
    if os.path.exists(dst_conf):
        os.remove(dst_conf)

    deleteLoadBalanceAllCfg()
    restartWeb()
    return 'ok'


def restart():
    if not isInstalled():
        return 'ERROR: 请先安装OpenResty'
    if not restartWeb():
        return 'ERROR: OpenResty 重启失败'
    return 'ok'


def reload():
    if not isInstalled():
        return 'ERROR: 请先安装OpenResty'
    if not restartWeb():
        return 'ERROR: OpenResty 重载失败'
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
        # cfg.json 里被投毒（或历史脏数据）的记录不得参与删除/覆写：
        # 名字直接拼进路径，非法值等于任意文件删/任意文件写。
        if not isinstance(conf, dict):
            continue
        upstream_name = conf.get('upstream_name', '')
        domain = conf.get('domain', '')
        if not is_valid_upstream(upstream_name) or not is_valid_domain(domain):
            continue

        upstream_file = upstream_dir + '/' + upstream_name + '.conf'
        if os.path.exists(upstream_file):
            os.remove(upstream_file)

        lua_file = lua_dir + '/' + upstream_name + '.lua'
        if os.path.exists(lua_file):
            os.remove(lua_file)

        rewrite_file = rewrite_dir + '/' + domain + '.conf'
        yf.writeFile(rewrite_file, '')

        path = vhost_dir + '/' + domain + '.conf'

        content = yf.readFile(path)
        if isinstance(content, str):
            content = re.sub('include ' + re.escape(upstream_file) + ';' + "\n", '', content)
            yf.writeFile(path, content)

    yf.opLuaInitWorkerFile()


def normalizeNodeList(raw):
    """把前端 node_list 收敛成受校验的列表；不合法回 (None, 错误消息键)。

    旧实现把 weight/max_fails/fail_timeout 原样拼进 upstream 文件，
    且校验循环把 KeyError 一起吞掉 —— 缺一个 ip 键就整段跳过校验。
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception as e:
            _log.debug('[op_load_balance] node_list 不是合法 JSON: %s', e)
            return (None, '节点参数格式不合法')
    if not isinstance(raw, list):
        return (None, '节点参数格式不合法')

    nodes = []
    for item in raw:
        if not isinstance(item, dict):
            return (None, '节点参数格式不合法')

        host = item.get('ip')
        if not is_valid_node_host(host):
            return (None, '节点IP/主机名不合法')

        port = _toInt(item.get('port'), 1, 65535)
        if port is None:
            return (None, '节点端口不合法')

        state = str(item.get('state', '1')).strip()
        if state not in _NODE_STATE:
            return (None, '节点状态不合法')

        weight = _toInt(item.get('weight', 1), 1, 10000)
        if weight is None:
            return (None, '节点权重不合法')

        max_fails = _toInt(item.get('max_fails', 1), 0, 10000)
        if max_fails is None:
            return (None, '节点失败次数不合法')

        fail_timeout = _toInt(item.get('fail_timeout', 10), 1, 86400)
        if fail_timeout is None:
            return (None, '节点恢复时间不合法')

        path = item.get('path', '/')
        if not is_valid_node_path(path):
            path = '/'

        nodes.append({
            'ip': host.strip(),
            'port': str(port),
            'path': path.strip(),
            'state': state,
            'weight': str(weight),
            'max_fails': str(max_fails),
            'fail_timeout': str(fail_timeout),
        })
    return (nodes, None)


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
    if not isinstance(row, int) or row < 0 or row >= len(cfg):
        return False
    conf = cfg[row]
    if not isinstance(conf, dict):
        return False

    domain = conf.get('domain', '')
    upstream_name = conf.get('upstream_name', '')
    if not is_valid_domain(domain) or not is_valid_upstream(upstream_name):
        return False

    nodes, err = normalizeNodeList(conf.get('node_list', []))
    if err:
        return False

    node_algo = conf.get('node_algo', 'polling')
    if node_algo not in _NODE_ALGO:
        node_algo = 'polling'
    node_health_check = conf.get('node_health_check', 'fail')
    if node_health_check not in _HEALTH_CHECK:
        node_health_check = 'fail'

    upstream_dir = yf.getServerDir() + '/web_conf/nginx/upstream'
    rewrite_dir = yf.getServerDir() + '/web_conf/nginx/rewrite'
    vhost_dir = yf.getServerDir() + '/web_conf/nginx/vhost'
    upstream_tpl = getPluginDir() + '/conf/upstream.tpl.conf'
    rewrite_tpl = getPluginDir() + '/conf/rewrite.tpl.conf'

    if not os.path.exists(upstream_dir):
        os.makedirs(upstream_dir)

    # replace vhost start
    vhost_file = vhost_dir + '/' + domain + '.conf'
    vcontent = yf.readFile(vhost_file)
    if not isinstance(vcontent, str):
        vcontent = ''

    vhost_find_str = 'upstream/' + upstream_name + '.conf'
    vhead = 'include ' + yf.getServerDir() + '/web_conf/nginx/' + \
        vhost_find_str + ';'

    vpos = vcontent.find(vhost_find_str)
    if vpos < 0:
        vcontent = vhead + "\n" + vcontent
        yf.writeFile(vhost_file, vcontent)
    # replace vhost end

    # make upstream start
    upstream_file = upstream_dir + '/' + upstream_name + '.conf'
    content = ''
    if len(nodes) > 0:
        content = yf.readFile(upstream_tpl)
        if not isinstance(content, str):
            return False
        slist = makeConfServerList(nodes)
        content = content.replace('{$NODE_SERVER_LIST}', slist)
        content = content.replace('{$UPSTREAM_NAME}', upstream_name)
        if node_algo != 'polling':
            content = content.replace('{$NODE_ALGO}', node_algo + ';')
        else:
            content = content.replace('{$NODE_ALGO}', '')
    yf.writeFile(upstream_file, content)
    # make upstream end

    # make rewrite start
    rewrite_file = rewrite_dir + '/' + domain + '.conf'
    rcontent = ''
    if len(nodes) > 0:
        rcontent = yf.readFile(rewrite_tpl)
        if not isinstance(rcontent, str):
            return False
        rcontent = rcontent.replace('{$UPSTREAM_NAME}', upstream_name)
    yf.writeFile(rewrite_file, rcontent)
    # make rewrite end

    # health check start
    lua_dir = yf.getServerDir() + '/web_conf/nginx/lua/init_worker_by_lua_file'
    lua_init_worker_file = lua_dir + '/' + upstream_name + '.lua'
    if node_health_check == 'ok':
        lua_dir_tpl = getPluginDir() + '/lua/health_check.lua.tpl'
        content = yf.readFile(lua_dir_tpl)
        if not isinstance(content, str):
            return False
        content = content.replace('{$UPSTREAM_NAME}', upstream_name)
        content = content.replace('{$DOMAIN}', domain)
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

    if not isInstalled():
        return yf.returnJson(False, '请先安装OpenResty')

    domain_json = args['domain']
    site_info = None
    if isinstance(domain_json, dict):
        site_info = domain_json
    elif isinstance(domain_json, str):
        try:
            site_info = json.loads(domain_json)
        except Exception as e:
            _log.debug('[op_load_balance] domain 参数不是合法 JSON: %s', e)
    if not isinstance(site_info, dict) or not isinstance(site_info.get('domain'), str):
        return yf.returnJson(False, '域名格式不合法')

    domain = site_info['domain'].strip()
    if not is_valid_domain(domain):
        return yf.returnJson(False, '域名格式不合法')

    upstream_name = str(args['upstream_name']).strip()
    if not is_valid_upstream(upstream_name):
        return yf.returnJson(False, '负载名称格式不合法')

    node_algo = str(args['node_algo']).strip()
    if node_algo not in _NODE_ALGO:
        return yf.returnJson(False, '节点调度不合法')

    node_health_check = str(args['node_health_check']).strip()
    if node_health_check not in _HEALTH_CHECK:
        return yf.returnJson(False, '节点健康检查参数不合法')

    nodes, err = normalizeNodeList(args['node_list'])
    if err:
        return yf.returnJson(False, err)

    cfg = getConf()
    cfg_len = len(cfg)
    item = {}
    item['domain'] = domain
    item['data'] = args['domain']
    item['upstream_name'] = upstream_name
    item['node_algo'] = node_algo
    item['node_list'] = nodes
    item['node_health_check'] = node_health_check
    cfg.append(item)
    writeConf(cfg)

    from utils.site import sites as YfSites
    sobj = YfSites.instance()
    domain_path = yf.getWwwDir() + '/' + domain

    ps = '负载均衡[' + domain + ']'
    res = sobj.add(json.dumps(site_info), '80', ps, domain_path, '00')

    # 站点没建起来就不能留半成品：旧实现丢弃返回值，站点创建失败也回「添加成功」，
    # 还照样把 upstream/vhost 写进生产配置。
    if not isinstance(res, dict) or not res.get('status'):
        del cfg[cfg_len]
        writeConf(cfg)
        msg = res.get('msg') if isinstance(res, dict) else None
        return yf.returnJson(False, msg or '站点创建失败,负载未添加')

    if not makeLoadBalanceAllCfg(cfg_len):
        return yf.returnJson(False, '负载配置生成失败')
    yf.restartWeb()
    return yf.returnJson(True, '添加成功', res)


def edit_load_balance(args):
    data = checkArgs(
        args, ['row', 'node_algo', 'node_list', 'node_health_check'])
    if not data[0]:
        return data[1]

    if not isInstalled():
        return yf.returnJson(False, '请先安装OpenResty')

    row = _toInt(args['row'], 0)
    if row is None:
        return yf.returnJson(False, '参数格式错误!')

    cfg = getConf()
    if row >= len(cfg) or not isinstance(cfg[row], dict):
        return yf.returnJson(False, '负载不存在!')

    node_algo = str(args['node_algo']).strip()
    if node_algo not in _NODE_ALGO:
        return yf.returnJson(False, '节点调度不合法')

    node_health_check = str(args['node_health_check']).strip()
    if node_health_check not in _HEALTH_CHECK:
        return yf.returnJson(False, '节点健康检查参数不合法')

    nodes, err = normalizeNodeList(args['node_list'])
    if err:
        return yf.returnJson(False, err)

    item = cfg[row]
    item['node_algo'] = node_algo
    item['node_list'] = nodes
    item['node_health_check'] = node_health_check
    cfg[row] = item
    writeConf(cfg)

    if not makeLoadBalanceAllCfg(row):
        return yf.returnJson(False, '负载配置生成失败')
    yf.restartWeb()
    return yf.returnJson(True, '修改成功', item)


def loadBalanceList():
    cfg = getConf()
    return yf.returnJson(True, 'ok', cfg)


def loadBalanceDelete():
    args = getArgs()
    data = checkArgs(args, ['row'])
    if not data[0]:
        return data[1]

    row = _toInt(args['row'], 0)
    if row is None:
        return yf.returnJson(False, '参数格式错误!')

    cfg = getConf()
    if row >= len(cfg) or not isinstance(cfg[row], dict):
        return yf.returnJson(False, '负载不存在!')

    item = cfg[row]
    domain = item.get('domain', '')
    upstream_name = item.get('upstream_name', '')

    from utils.site import sites as YfSites
    sobj = YfSites.instance()

    sid = yf.M('sites').where('name=?', (domain,)).getField('id')

    if type(sid) == list:
        del(cfg[row])
        writeConf(cfg)
        return yf.returnJson(False, '已经删除了!')

    res = sobj.delete(sid, '1')
    if not isinstance(res, dict) or not res.get('status'):
        # 站点没删掉就不能先删 upstream/rewrite：vhost 里的 include 会指向不存在的
        # 文件，nginx -t 直接失败，生产 openresty 下次 reload 就起不来。
        return yf.returnJson(False, '删除失败')

    del(cfg[row])
    writeConf(cfg)

    if is_valid_upstream(upstream_name):
        upstream_file = yf.getServerDir() + '/web_conf/nginx/upstream/' + upstream_name + '.conf'
        if os.path.exists(upstream_file):
            os.remove(upstream_file)

        # 健康检查 lua 也必须一起清：留着会被 opLuaInitWorkerFile 拼回
        # init_worker_by_lua_file.lua，向一个已删除的 upstream spawn_checker。
        lua_file = yf.getServerDir() + '/web_conf/nginx/lua/init_worker_by_lua_file/' + \
            upstream_name + '.lua'
        if os.path.exists(lua_file):
            os.remove(lua_file)
        yf.opLuaInitWorkerFile()

    if is_valid_domain(domain):
        rewrite_file = yf.getServerDir() + '/web_conf/nginx/rewrite/' + domain + '.conf'
        if os.path.exists(rewrite_file):
            yf.writeFile(rewrite_file, '')

    return yf.returnJson(True, res.get('msg') or '删除成功')


def http_get(url):
    import urllib.request
    import ssl
    if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
        return False
    try:
        context = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5, context=context) as response:
            status = [200, 301, 302, 404, 403]
            if response.getcode() in status:
                return True
            return False
    except Exception as e:
        _log.debug('[op_load_balance] 探测 %s 失败: %s', url, e)
        return False


def checkUrl():
    args = getArgs()
    data = checkArgs(args, ['ip', 'port', 'path'])
    if not data[0]:
        return data[1]

    ip = str(args['ip']).strip()
    port = _toInt(args['port'], 1, 65535)
    path = args['path']

    # 旧实现把三个参数原样拼进 URL：ip 可以是任意 host（含 169.254.169.254 等内网
    # 地址）、port 任意、path 可带换行，等于把面板当内网探测器用。
    if not is_valid_node_host(ip) or port is None or not is_valid_node_path(path):
        return yf.returnJson(False, '访问节点失败,参数不合法')

    path = path.strip()
    if port == 443:
        url = 'https://' + str(ip) + ':' + str(port) + path
    else:
        url = 'http://' + str(ip) + ':' + str(port) + path
    ret = http_get(url)
    if not ret:
        return yf.returnJson(False, '访问节点[%s]失败' % url)
    return yf.returnJson(True, '访问节点[%s]成功' % url)


def getHealthStatus():
    args = getArgs()
    data = checkArgs(args, ['row'])
    if not data[0]:
        return data[1]

    row = _toInt(args['row'], 0)
    if row is None:
        return yf.returnJson(False, '参数格式错误!')

    cfg = getConf()
    if row >= len(cfg) or not isinstance(cfg[row], dict):
        return yf.returnJson(False, '负载不存在!')

    item = cfg[row]
    domain = item.get('domain', '')
    upstream_name = item.get('upstream_name', '')
    if not is_valid_domain(domain) or not is_valid_upstream(upstream_name):
        return yf.returnJson(False, '负载不存在!')

    url = 'http://' + domain + '/upstream_status_' + upstream_name

    url_data = yf.httpGet(url)
    # httpGet 失败时返回 False/''，旧实现直接 json.loads(False) → TypeError 回前端
    if not isinstance(url_data, str) or not url_data.strip():
        return yf.returnJson(False, '节点健康状态获取失败')
    try:
        peers = json.loads(url_data)
    except Exception as e:
        _log.debug('[op_load_balance] 健康状态响应不是 JSON: %s', e)
        return yf.returnJson(False, '节点健康状态获取失败')
    if not isinstance(peers, list):
        peers = []
    return yf.returnJson(True, 'ok', peers)


def getLogs():
    args = getArgs()
    data = checkArgs(args, ['domain'])
    if not data[0]:
        return data[1]

    domain = str(args['domain']).strip()
    # 返回值会被前端交给 /files/get_last_body 读盘：域名直接拼路径，
    # 不校验就等于把日志读取面扩到日志目录外（`../../` 穿越）。
    if not is_valid_domain(domain):
        return yf.returnJson(False, '日志路径不合法')

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
