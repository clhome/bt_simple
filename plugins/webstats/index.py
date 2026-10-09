# coding:utf-8

import sys
import io
import os
import time
import json
import re
import logging

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

_log = logging.getLogger('yf.webstats')


app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'webstats'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


sys.path.append(getPluginDir() + "/class")
from LuaMaker import LuaMaker


def listToLuaFile(path, lists):
    content = LuaMaker.makeLuaTable(lists)
    content = "return " + content
    yf.writeFile(path, content)


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getConf():
    conf = getServerDir() + "/lua/config.json"
    return conf


def getArgs():
    # 前端 utils/plugin.py::run() 把整个 args 当作**一个** argv 传进来，且是 JSON 文本。
    # 旧实现只按 ':' 切分，于是 {"page":"1","page_size":"10"} 被切成
    # 键 '"page"' / 值 '"1","page_size"' —— 所有带参接口恒回「缺少必要参数」。
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        val = args[0].strip()
        if val.startswith('{') and val.endswith('}'):
            try:
                data = json.loads(val)
            except Exception as e:
                _log.debug('[webstats] getArgs JSON 解析失败: %s', e)
                data = None
            if isinstance(data, dict):
                return data
        t = val.strip('{').strip('}')
        if t.strip() == '':
            return tmp
        t = t.split(':', 1)
        if len(t) == 2:
            k = t[0].strip().strip('"').strip("'")
            v = t[1].strip().strip('"').strip("'")
            tmp[k] = v
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':', 1)
            if len(t) == 2:
                k = t[0].strip().strip('"').strip("'")
                v = t[1].strip().strip('"').strip("'")
                tmp[k] = v

    return tmp


def checkArgs(data, ck=[]):
    if not isinstance(data, dict):
        return (False, yf.returnJson(False, '参数格式错误'))
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


def isSafeSiteName(name):
    """站点名（日志目录名）白名单：拒绝路径分隔符与 ``..``。

    站点名会直接拼成 ``<serverDir>/webstats/logs/<site>/`` 并据此建 sqlite 库，
    历史实现未校验，``site='../../../../tmp/x'`` 可让面板以 root 身份在任意
    目录建出目录与库文件。
    """
    name = str(name or '').strip()
    if not name or len(name) > 255:
        return False
    if '/' in name or '\\' in name or '..' in name or '\x00' in name:
        return False
    # 名字会参与路径拼接与 ATTACH DATABASE 语句，拒绝引号/空白/分隔符
    for ch in name:
        if ch in "'\"`;" or ch.isspace():
            return False
    return True


def getSiteArg(args, key='site'):
    """取并校验站点参数。返回 (True, site) 或 (False, 错误信封)。"""
    site = str(args.get(key, '') or '').strip()
    if not isSafeSiteName(site):
        return False, yf.returnJson(False, '站点参数不合法')
    return True, site


_QUERY_DATE_RE = re.compile(r'^\d{1,12}-\d{1,12}$')
# 2100-01-01：超过它 time.localtime() 会抛 OSError/ValueError
_MAX_QUERY_TS = 4102444800


def normalizeQueryDate(value):
    """校验时间范围参数：today/yesterday/l7/l30 或 ``<epoch>-<epoch>``。

    自定义范围来自前端 laydate，形如 ``1700000000-1700086400``。
    非日期（如 'abc'）在旧实现里会走到 ``exlist[1]`` 抛 IndexError。
    """
    value = str(value or '').strip()
    if value in ('today', 'yesterday', 'l7', 'l30'):
        return value
    if _QUERY_DATE_RE.match(value):
        a, b = value.split('-', 1)
        ia, ib = int(a), int(b)
        if ia > ib or ib > _MAX_QUERY_TS:
            return None
        return value
    return None


def toIntArg(value, min_v=None, max_v=None):
    """表单/JSON 传来的值安全转 int；非数字或越界返回 None。"""
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if min_v is not None and n < min_v:
        return None
    if max_v is not None and n > max_v:
        return None
    return n


_MAX_PAGE_SIZE = 1000


def checkPager(args):
    """校验分页参数。返回 (True, page, page_size) 或 (False, 错误信封)。

    旧实现把 page_size 直接拼进 ``LIMIT``：负数在 SQLite 里等于**不限制**
    （一次把整库拉回内存），超大值同理。
    """
    page = toIntArg(args.get('page'), 1, 10 ** 9)
    page_size = toIntArg(args.get('page_size'), 1, _MAX_PAGE_SIZE)
    if page is None or page_size is None:
        return False, yf.returnJson(False, '参数格式错误')
    return True, page, page_size


def readConfJson():
    """读 <serverDir>/webstats/lua/config.json。

    返回 (True, dict) 或 (False, 错误信封)。yf.readFile() 读不到时返回 **False**
    （不是空串），旧实现直接 json.loads(False) → TypeError traceback。
    """
    content = yf.readFile(getConf())
    if not content:
        return False, yf.returnJson(False, '配置文件不存在或无法读取')
    try:
        return True, json.loads(content)
    except Exception as e:
        _log.debug('[webstats] config.json 解析失败: %s', e)
        return False, yf.returnJson(False, '配置文件不存在或无法读取')


def splitLines(value):
    """按「真实换行」或「字面 \\n」切分多行配置项。

    JSON 单 argv 形态下前端 textarea 的换行是真实换行；旧实现只 split('\\n')，
    整段文本被当成单元素列表写进 lua，生成的文件含裸换行 → luajit 语法错误。
    """
    value = str(value or '')
    return [x for x in re.split(r'\r?\n|\\n', value) if x != '']


def luaConf():
    return yf.getServerDir() + '/web_conf/nginx/vhost/webstats.conf'


def status():
    path = luaConf()
    if not os.path.exists(path):
        return 'stop'
    return 'start'


def loadLuaFile(name):
    lua_dir = getServerDir() + "/lua"
    lua_dst = lua_dir + "/" + name

    if not os.path.exists(lua_dst):
        lua_tpl = getPluginDir() + '/lua/' + name
        content = yf.readFile(lua_tpl)
        if not content:
            _log.debug('[webstats] lua 模板不存在或无法读取: %s', lua_tpl)
            return False
        content = content.replace('{$SERVER_APP}', getServerDir())
        content = content.replace('{$ROOT_PATH}', yf.getServerDir())
        yf.writeFile(lua_dst, content)
    return True


def loadLuaFileReload(name):
    lua_dir = getServerDir() + "/lua"
    lua_dst = lua_dir + "/" + name

    lua_tpl = getPluginDir() + '/lua/' + name
    content = yf.readFile(lua_tpl)
    if not content:
        _log.debug('[webstats] lua 模板不存在或无法读取: %s', lua_tpl)
        return False
    content = content.replace('{$SERVER_APP}', getServerDir())
    content = content.replace('{$ROOT_PATH}', yf.getServerDir())
    yf.writeFile(lua_dst, content)
    return True


def loadConfigFile():
    conf_tpl = getPluginDir() + "/conf/config.json"

    content = yf.readFile(conf_tpl)
    if not content:
        _log.debug('[webstats] config.json 模板不存在或无法读取: %s', conf_tpl)
        return False
    try:
        content = json.loads(content)
    except Exception as e:
        _log.debug('[webstats] config.json 模板解析失败: %s', e)
        return False

    dst_conf_json = getServerDir() + "/lua/config.json"
    if not os.path.exists(dst_conf_json):
        yf.writeFile(dst_conf_json, json.dumps(content))

    dst_conf_lua = getServerDir() + "/lua/webstats_config.lua"
    if not os.path.exists(dst_conf_lua):
        listToLuaFile(dst_conf_lua, content)
    return True


# def loadConfigFileReload():
#     -- 配置生活或可使用
#     lua_dir = getServerDir() + "/lua"
#     conf_tpl = getPluginDir() + "/conf/config.json"

#     content = yf.readFile(conf_tpl)
#     content = json.loads(content)

#     dst_conf_json = getServerDir() + "/lua/config.json"
#     yf.writeFile(dst_conf_json, json.dumps(content))

#     dst_conf_lua = getServerDir() + "/lua/webstats_config.lua"
#     listToLuaFile(dst_conf_lua, content)


def loadLuaSiteFile():
    lua_dir = getServerDir() + "/lua"

    content = makeSiteConfig()
    for index in range(len(content)):
        if not isSafeSiteName(content[index]['name']):
            _log.debug('[webstats] 跳过不安全的站点名: %r', content[index]['name'])
            continue
        pSqliteDb('web_log', content[index]['name'])

    lua_site_json = lua_dir + "/sites.json"
    yf.writeFile(lua_site_json, json.dumps(content))

    # 设置默认列表
    default_json = lua_dir + "/default.json"
    ddata = {}
    dlist = []
    for i in content:
        dlist.append(i["name"])

    dlist.append('unset')
    ddata["list"] = dlist
    if len(ddata["list"]) < 1:
        ddata["default"] = "unset"
    else:
        ddata["default"] = dlist[0]

    yf.writeFile(default_json, json.dumps(ddata))

    lua_site = lua_dir + "/webstats_sites.lua"

    tmp = {
        "name": "unset",
        "domains": [],
    }
    content.append(tmp)
    listToLuaFile(lua_site, content)


def loadDebugLogFile():
    debug_log = getServerDir() + "/debug.log"
    lua_dir = getServerDir() + "/lua"
    yf.writeFile(debug_log, '')


def pSqliteDb(dbname='web_logs', site_name='unset', name="logs"):

    if not isSafeSiteName(site_name):
        raise ValueError('unsafe site name: %r' % (site_name,))

    db_dir = getServerDir() + '/logs/' + site_name
    logs_root = os.path.realpath(getServerDir() + '/logs')
    if not os.path.realpath(db_dir).startswith(logs_root + os.sep):
        raise ValueError('site dir escapes logs root: %r' % (site_name,))
    if not os.path.exists(db_dir):
        yf.makeDirs(db_dir)

    file = db_dir + '/' + name + '.db'
    if not os.path.exists(file):
        conn = yf.M(dbname).dbPos(db_dir, name)
        sql = yf.readFile(getPluginDir() + '/conf/init.sql')
        if not sql:
            _log.debug('[webstats] init.sql 不存在或无法读取')
            return conn
        sql_list = sql.split(';')
        for index in range(len(sql_list)):
            conn.execute(sql_list[index])
    else:
        conn = yf.M(dbname).dbPos(db_dir, name)

    conn.execute("PRAGMA synchronous = 0")
    conn.execute("PRAGMA cache_size = 8000")
    conn.execute("PRAGMA page_size = 32768")
    conn.execute("PRAGMA journal_mode = wal")
    conn.execute("PRAGMA journal_size_limit = 1073741824")
    return conn


def makeSiteConfig():
    siteM = yf.M('sites')
    domainM = yf.M('domain')
    slist = siteM.field('id,name').where(
        'status=?', (1,)).order('id desc').select()

    data = []
    for s in slist:
        tmp = {}
        tmp['name'] = s['name']

        dlist = domainM.field('id,name').where(
            'pid=?', (s['id'],)).order('id desc').select()

        _t = []
        for d in dlist:
            _t.append(d['name'])

        tmp['domains'] = _t
        data.append(tmp)

    return data


def checkReady():
    """运行前置检查。未就绪返回错误字符串，就绪返回 True。

    旧实现在未安装时也返回 'ok' 并凭空建出 web_conf/nginx/vhost/webstats.conf，
    紧接着 luaRestart() 停/启**生产 openresty** —— 而该 vhost 会 include
    webstats_log.lua（依赖 lsqlite3.so），缺库时 nginx 起不来 = 生产 web 宕机。
    """
    if not os.path.exists(yf.getServerDir() + '/openresty'):
        return 'ERROR: 请先安装OpenResty'
    server_webstats = getServerDir()
    if not (os.path.exists(server_webstats + '/version.pl')
            or os.path.exists(server_webstats + '/lua/lsqlite3.so')):
        return 'ERROR: 网站统计插件未安装'
    return True


def initDreplace():

    service_path = getServerDir()

    for fl in ('webstats_common.lua', 'webstats_log.lua'):
        if not os.path.exists(getPluginDir() + '/lua/' + fl):
            return 'ERROR: webstats lua 模板缺失: ' + fl
    if not os.path.exists(getPluginDir() + '/conf/init.sql'):
        return 'ERROR: webstats init.sql 缺失'

    pSqliteDb()

    path = luaConf()
    path_tpl = getPluginDir() + '/conf/webstats.conf'
    if not os.path.exists(path):
        content = yf.readFile(path_tpl)
        if not content:
            _log.debug('[webstats] vhost 模板不存在或无法读取: %s', path_tpl)
            return 'ERROR: webstats vhost 模板缺失'
        content = content.replace('{$SERVER_APP}', service_path)
        content = content.replace('{$ROOT_PATH}', yf.getServerDir())
        yf.writeFile(path, content)

    # 已经安装的
    al_config = getServerDir() + "/lua/config.json"
    if os.path.exists(al_config):
        try:
            tmp = json.loads(yf.readFile(al_config))
        except Exception as e:
            _log.debug('[webstats] 读取已存在 config.json 失败: %s', e)
            tmp = None
        if tmp and tmp.get('global') and (
                tmp['global'].get('record_post_args')
                or tmp['global'].get('record_get_403_args')):
            openLuaNeedRequestBody()
        else:
            closeLuaNeedRequestBody()

    lua_dir = getServerDir() + "/lua"
    if not os.path.exists(lua_dir):
        yf.makeDirs(lua_dir)

    log_path = getServerDir() + "/logs"
    if not os.path.exists(log_path):
        yf.makeDirs(log_path)

    file_list = [
        'webstats_common.lua',
        'webstats_log.lua',
    ]

    for fl in file_list:
        if loadLuaFile(fl) is False:
            return 'ERROR: webstats lua 模板读取失败: ' + fl

    if loadConfigFile() is False:
        return 'ERROR: webstats config.json 模板读取失败'
    loadLuaSiteFile()
    loadDebugLogFile()

    if not yf.isAppleSystem():
        yf.execShell("chown -R www:www " + getServerDir())
    return 'ok'


def luaRestart():
    yf.opWeb("stop")
    yf.opWeb("start")


def start():
    ready = checkReady()
    if ready is not True:
        return ready

    ret = initDreplace()
    if ret != 'ok':
        return ret

    import tool_task
    tool_task.createBgTask()

    # issues:326
    luaRestart()
    return 'ok'


def stop():
    path = luaConf()
    existed = os.path.exists(path)
    if existed:
        os.remove(path)

    import tool_task
    tool_task.removeBgTask()

    # 未安装/无 vhost 时不必重启生产 openresty
    if existed:
        luaRestart()
    return 'ok'


def restart():
    ready = checkReady()
    if ready is not True:
        return ready

    ret = initDreplace()
    if ret != 'ok':
        return ret
    loadDebugLogFile()
    luaRestart()
    return 'ok'


def reload():
    ready = checkReady()
    if ready is not True:
        return ready

    ret = initDreplace()
    if ret != 'ok':
        return ret

    file_list = [
        'webstats_common.lua',
        'webstats_log.lua',
    ]
    for fl in file_list:
        if loadLuaFileReload(fl) is False:
            return 'ERROR: webstats lua 模板读取失败: ' + fl

    loadDebugLogFile()

    luaRestart()
    return 'ok'


def getGlobalConf():
    ok, content = readConfJson()
    if not ok:
        return content
    return yf.returnJson(True, 'ok', content)


def openLuaNeedRequestBody():
    conf = luaConf()
    content = yf.readFile(conf)
    if not content:
        return False
    content = re.sub(r"lua_need_request_body (.*);",
                     'lua_need_request_body on;', content)
    yf.writeFile(conf, content)
    return True


def closeLuaNeedRequestBody():
    conf = luaConf()
    content = yf.readFile(conf)
    if not content:
        return False
    content = re.sub(r"lua_need_request_body (.*);",
                     'lua_need_request_body off;', content)
    yf.writeFile(conf, content)
    return True


def setGlobalConf():
    args = getArgs()

    ok, content = readConfJson()
    if not ok:
        return content

    open_force_get_request_body = False
    for v in ['record_post_args', 'record_get_403_args']:
        data = checkArgs(args, [v])
        if data[0]:
            rval = False
            if args[v] == "true":
                rval = True
                open_force_get_request_body = True

            content['global'][v] = rval

    # 开启强制获取日志配置
    if open_force_get_request_body:
        openLuaNeedRequestBody()
    else:
        closeLuaNeedRequestBody()

    for v in ['ip_top_num', 'uri_top_num', 'save_day']:
        data = checkArgs(args, [v])
        if data[0]:
            n = toIntArg(args[v], 0, 10 ** 9)
            if n is None:
                return yf.returnJson(False, '参数格式错误')
            content['global'][v] = n

    for v in ['cdn_headers', 'exclude_extension', 'exclude_status', 'exclude_ip']:
        data = checkArgs(args, [v])
        if data[0]:
            content['global'][v] = splitLines(args[v])

    data = checkArgs(args, ['exclude_url'])
    if data[0]:
        exclude_url = args['exclude_url'].strip(";")
        exclude_url_val = []
        if exclude_url != "":
            exclude_url_list = exclude_url.split(";")
            for i in exclude_url_list:
                t = i.split("|")
                if len(t) != 2:
                    return yf.returnJson(False, '参数格式错误')
                val = {}
                val['mode'] = t[0]
                val['url'] = t[1]
                exclude_url_val.append(val)
        content['global']['exclude_url'] = exclude_url_val

    yf.writeFile(getConf(), json.dumps(content))
    conf_lua = getServerDir() + "/lua/webstats_config.lua"
    listToLuaFile(conf_lua, content)
    luaRestart()
    return yf.returnJson(True, '设置成功')


def getSiteConf():
    args = getArgs()

    check = checkArgs(args, ['site'])
    if not check[0]:
        return check[1]

    ok, domain = getSiteArg(args)
    if not ok:
        return domain

    ok, content = readConfJson()
    if not ok:
        return content

    site_conf = {}
    if domain in content:
        site_conf = content[domain]
    else:
        site_conf["cdn_headers"] = content['global']['cdn_headers']
        site_conf["exclude_extension"] = content['global']['exclude_extension']
        site_conf["exclude_status"] = content['global']['exclude_status']
        site_conf["exclude_ip"] = content['global']['exclude_ip']
        site_conf["exclude_url"] = content['global']['exclude_url']
        site_conf["record_post_args"] = content['global']['record_post_args']
        site_conf["record_get_403_args"] = content[
            'global']['record_get_403_args']

    return yf.returnJson(True, 'ok', site_conf)


def setSiteConf():
    args = getArgs()
    check = checkArgs(args, ['site'])
    if not check[0]:
        return check[1]

    ok, domain = getSiteArg(args)
    if not ok:
        return domain

    ok, content = readConfJson()
    if not ok:
        return content

    site_conf = {}
    if domain in content:
        site_conf = content[domain]
    else:
        site_conf["cdn_headers"] = content['global']['cdn_headers']
        site_conf["exclude_extension"] = content['global']['exclude_extension']
        site_conf["exclude_status"] = content['global']['exclude_status']
        site_conf["exclude_ip"] = content['global']['exclude_ip']
        site_conf["exclude_url"] = content['global']['exclude_url']
        site_conf["record_post_args"] = content['global']['record_post_args']
        site_conf["record_get_403_args"] = content[
            'global']['record_get_403_args']

    for v in ['record_post_args', 'record_get_403_args']:
        data = checkArgs(args, [v])
        if data[0]:
            rval = False
            if args[v] == "true":
                rval = True
            site_conf[v] = rval

    for v in ['ip_top_num', 'uri_top_num', 'save_day']:
        data = checkArgs(args, [v])
        if data[0]:
            n = toIntArg(args[v], 0, 10 ** 9)
            if n is None:
                return yf.returnJson(False, '参数格式错误')
            site_conf[v] = n

    for v in ['cdn_headers', 'exclude_extension', 'exclude_status', 'exclude_ip']:
        data = checkArgs(args, [v])
        if data[0]:
            site_conf[v] = splitLines(args[v])

    data = checkArgs(args, ['exclude_url'])
    if data[0]:
        exclude_url = args['exclude_url'].strip(";")
        exclude_url_val = []
        if exclude_url != "":
            exclude_url_list = exclude_url.split(";")
            for i in exclude_url_list:
                t = i.split("|")
                if len(t) != 2:
                    return yf.returnJson(False, '参数格式错误')
                val = {}
                val['mode'] = t[0]
                val['url'] = t[1]
                exclude_url_val.append(val)
        site_conf['exclude_url'] = exclude_url_val

    content[domain] = site_conf

    yf.writeFile(getConf(), json.dumps(content))
    conf_lua = getServerDir() + "/lua/webstats_config.lua"
    listToLuaFile(conf_lua, content)
    luaRestart()
    return yf.returnJson(True, '设置成功')


def getSiteListData():
    lua_dir = getServerDir() + "/lua"
    path = lua_dir + "/default.json"
    data = yf.readFile(path)
    if not data:
        return {"list": ["unset"], "default": "unset"}
    try:
        return json.loads(data)
    except Exception as e:
        _log.debug('[webstats] default.json 解析失败: %s', e)
        return {"list": ["unset"], "default": "unset"}


def getDefaultSite():
    data = getSiteListData()
    return yf.returnJson(True, 'OK', data)


def setDefaultSite(name):
    if not isSafeSiteName(name):
        return yf.returnJson(False, '站点参数不合法')
    name = str(name).strip()
    lua_dir = getServerDir() + "/lua"
    path = lua_dir + "/default.json"
    data = yf.readFile(path)
    if not data:
        return yf.returnJson(False, '配置文件不存在或无法读取')
    try:
        data = json.loads(data)
    except Exception as e:
        _log.debug('[webstats] default.json 解析失败: %s', e)
        return yf.returnJson(False, '配置文件不存在或无法读取')
    data['default'] = name
    yf.writeFile(path, json.dumps(data))
    return yf.returnJson(True, 'OK')


def toSumField(sql):
    l = sql.split(",")
    field = ""
    for x in l:
        field += "sum(" + x + ") as " + x + ","
    field = field.strip(',')
    return field


def getSiteStatInfo(domain, query_date):
    conn = pSqliteDb('request_stat', domain)
    conn = conn.where("1=1", ())

    field = 'time,req,pv,uv,ip,length'
    field_sum = toSumField(field.replace("time,", ""))

    time_field = "substr(time,1,6),"

    field_sum = time_field + field_sum
    conn = conn.field(field_sum)
    if query_date == "today":
        todayTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 0 * 86400))
        conn.andWhere("time >= ?", (todayTime,))
    elif query_date == "yesterday":
        startTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 1 * 86400))
        endTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time()))
        conn.andWhere("time>=? and time<=?", (startTime, endTime))
    elif query_date == "l7":
        todayTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 7 * 86400))
        conn.andWhere("time >= ?", (todayTime,))
    elif query_date == "l30":
        todayTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 30 * 86400))
        conn.andWhere("time >= ?", (todayTime,))
    else:
        exlist = str(query_date).split("-")
        try:
            start = time.strftime(
                '%Y%m%d00', time.localtime(int(exlist[0])))
            end = time.strftime(
                '%Y%m%d23', time.localtime(int(exlist[1])))
        except (IndexError, ValueError, OverflowError, OSError):
            start = end = '0'
        conn.andWhere("time >= ? and time <= ? ", (start, end,))

    # 统计总数
    stat_list = conn.inquiry(field)
    del(stat_list[0]['time'])
    return stat_list[0]


def getOverviewList():
    args = getArgs()
    check = checkArgs(args, ['site', 'query_date', 'order'])
    if not check[0]:
        return check[1]

    ok, domain = getSiteArg(args)
    if not ok:
        return domain

    query_date = normalizeQueryDate(args['query_date'])
    if query_date is None:
        return yf.returnJson(False, '时间范围参数不合法')
    order = args['order']

    setDefaultSite(domain)
    conn = pSqliteDb('request_stat', domain)
    conn = conn.where("1=1", ())

    field = 'time,req,pv,uv,ip,length'
    field_sum = toSumField(field.replace("time,", ""))

    time_field = "substr(time,1,8),"
    if order == "hour":
        time_field = "substr(time,9,10),"

    field_sum = time_field + field_sum
    conn = conn.field(field_sum)
    if query_date == "today":
        todayTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 0 * 86400))
        conn.andWhere("time >= ?", (todayTime,))
    elif query_date == "yesterday":
        startTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 1 * 86400))
        endTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time()))
        conn.andWhere("time>=? and time<=?", (startTime, endTime))
    elif query_date == "l7":
        todayTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 7 * 86400))
        conn.andWhere("time >= ?", (todayTime,))
    elif query_date == "l30":
        todayTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 30 * 86400))
        conn.andWhere("time >= ?", (todayTime,))
    else:
        exlist = str(query_date).split("-")
        try:
            start = time.strftime(
                '%Y%m%d00', time.localtime(int(exlist[0])))
            end = time.strftime(
                '%Y%m%d23', time.localtime(int(exlist[1])))
        except (IndexError, ValueError, OverflowError, OSError):
            start = end = '0'
        conn.andWhere("time >= ? and time <= ? ", (start, end,))

    # 统计总数
    stat_list = conn.inquiry(field)
    del(stat_list[0]['time'])

    # 分组统计
    dlist = conn.group(time_field.strip(",")).inquiry(field)

    data = {}
    data['data'] = dlist
    data['stat_list'] = stat_list[0]

    return yf.returnJson(True, 'ok', data)


def getSiteList():
    args = getArgs()
    check = checkArgs(args, ['query_date'])
    if not check[0]:
        return check[1]

    query_date = normalizeQueryDate(args['query_date'])
    if query_date is None:
        return yf.returnJson(False, '时间范围参数不合法')

    data = getSiteListData()
    data_list = data["list"]

    rdata = []
    for x in data_list:
        if not isSafeSiteName(x):
            continue
        tmp = getSiteStatInfo(x, query_date)
        tmp["site"] = x
        rdata.append(tmp)
    return yf.returnJson(True, 'ok', rdata)


def getLogsRealtimeInfo():
    '''
    实时信息
    '''
    import datetime
    args = getArgs()
    check = checkArgs(args, ['site', 'type','second'])
    if not check[0]:
        return check[1]

    domain = args['site']
    dtype = args['type']
    second = toIntArg(args['second'], 1, 30 * 86400)
    if second is None:
        return yf.returnJson(False, '参数格式错误')

    conn = pSqliteDb('web_logs', domain)
    timeInt = time.mktime(datetime.datetime.now().timetuple())

    conn = conn.where("time>=?", (int(timeInt) - second,))

    field = 'time,body_length'
    field_sum = toSumField(field.replace("time,", ""))
    time_field = "substr(time,1,2) as time,"
    time_field = time_field + field_sum
    clist = conn.field(time_field.strip(",")).group(
        'substr(time,1,2)').inquiry(field)

    body_count = 0
    if len(clist) > 0:
        body_count = clist[0]['body_length']

    req_count = conn.count()

    data = {}
    data['realtime_traffic'] = body_count
    data['realtime_request'] = req_count

    return yf.returnJson(True, 'ok', data)


def attacHistoryLogHack(conn, site_name, query_date='today'):
    if query_date == "today":
        return
    db_dir = getServerDir() + '/logs/' + site_name
    file = db_dir + '/history_logs.db'
    if os.path.exists(file):
        attach = "ATTACH DATABASE '" + file + "' as 'history_logs'"
        # print(attach)
        r = conn.originExecute(attach)
        sql_table = "(select * from web_logs union all select * from history_logs.web_logs)"
        # print(sql_table)
        conn.table(sql_table)


def getLogsList():
    args = getArgs()
    check = checkArgs(args, ['page', 'page_size','site', 'method', 
            'status_code', 'spider_type', 'request_time', 'query_date', 'search_uri'])
    if not check[0]:
        return check[1]

    pager = checkPager(args)
    if not pager[0]:
        return pager[1]
    page, page_size = pager[1], pager[2]

    ok, domain = getSiteArg(args)
    if not ok:
        return domain

    query_date = normalizeQueryDate(args['query_date'])
    if query_date is None:
        return yf.returnJson(False, '时间范围参数不合法')

    tojs = args.get('tojs', '')
    method = args['method']
    status_code = args['status_code']
    request_time = args['request_time']
    request_size = args.get('request_size', 'all')
    spider_type = args['spider_type']
    search_uri = args['search_uri']
    referer = args.get('referer', 'all')
    ip = args.get('ip', '')

    # 耗时/大小筛选：允许 all 或纯数字区间（前端 select 固定值）
    for name, val in (('request_time', request_time), ('request_size', request_size)):
        if val != 'all' and not re.match(r'^\d+(\-\d+)?$', str(val).strip()):
            return yf.returnJson(False, '参数格式错误')

    # 蜘蛛筛选：normal/only_spider/no_spider 或正整数蜘蛛类型 id
    if spider_type not in ('normal', 'only_spider', 'no_spider'):
        spider_type_id = toIntArg(spider_type, 1, 10 ** 9)
        if spider_type_id is None:
            return yf.returnJson(False, '参数格式错误')
        spider_type = spider_type_id

    setDefaultSite(domain)

    limit = str(page_size) + ' offset ' + str(page_size * (page - 1))
    conn = pSqliteDb('web_logs', domain)

    field = 'time,ip,domain,server_name,method,is_spider,protocol,status_code,request_headers,ip_list,client_port,body_length,user_agent,referer,request_time,uri,body_length'
    condition = ''
    conn = conn.field(field)
    conn = conn.where("1=1", ())

    if referer != 'all':
        if referer == '1':
            conn = conn.andWhere("referer <> ? ", ('',))
        elif referer == '-1':
            conn = conn.andWhere("referer is null ", ())

    if ip != '':
        conn = conn.andWhere("ip=?", (ip,))

    if method != "all":
        conn = conn.andWhere("method=?", (method,))

    if request_time != "all":
        request_time_s = request_time.strip().split('-')
        # print(request_time_s)
        if len(request_time_s) == 2:
            conn = conn.andWhere("request_time>=? and request_time<?", (request_time_s[0],request_time_s[1],))
        if len(request_time_s) == 1:
            conn = conn.andWhere("request_time>=?", (request_time,))

    if request_size != "all":
        request_size_s = request_size.strip().split('-')
        # print(int(request_size_s[0])*1024)
        if len(request_size_s) == 2:
            conn = conn.andWhere("body_length>=? and body_length<?", (int(request_size_s[0])*1024,int(request_size_s[1])*1024,))
        if len(request_size_s) == 1:
            conn = conn.andWhere("body_length>=?", (int(request_size_s[0])*1024,))

    if spider_type == "normal":
        pass
    elif spider_type == "only_spider":
        conn = conn.andWhere("is_spider>?", (0,))
    elif spider_type == "no_spider":
        conn = conn.andWhere("is_spider=?", (0,))
    elif int(spider_type) > 0:
        conn = conn.andWhere("is_spider=?", (spider_type,))

    todayTime = time.strftime('%Y-%m-%d 00:00:00', time.localtime())
    todayUt = int(time.mktime(time.strptime(todayTime, "%Y-%m-%d %H:%M:%S")))
    if query_date == 'today':
        conn = conn.andWhere("time>=?", (todayUt,))
    elif query_date == "yesterday":
        conn = conn.andWhere("time>=? and time<=?", (todayUt - 86400, todayUt))
    elif query_date == "l7":
        conn = conn.andWhere("time>=?", (todayUt - 7 * 86400,))
    elif query_date == "l30":
        conn = conn.andWhere("time>=?", (todayUt - 30 * 86400,))
    else:
        exlist = query_date.split("-")
        conn = conn.andWhere("time>=? and time<=?", (exlist[0], exlist[1]))

    if search_uri != "":
        conn = conn.andWhere("uri like ?", ('%' + search_uri + '%',))

    if status_code != "all":
        conn = conn.andWhere("status_code=?", (status_code,))

    attacHistoryLogHack(conn, domain, query_date)

    conn.changeTextFactoryToBytes()
    clist = conn.limit(limit).order('time desc').inquiry()

    for x in range(len(clist)):
        req_line = clist[x]
        for cx in req_line:
            v = req_line[cx]
            if type(v) == bytes:
                try:
                    clist[x][cx] = v.decode('utf-8')
                except Exception as e:
                    v = str(v)
                    v = v.replace("b'",'').strip("'")
                    clist[x][cx] = v
            else:
                clist[x][cx] = v

    # print(clist)
    count_key = "count(*) as num"
    count = conn.field(count_key).limit('').order('').inquiry()
    # print(count)
    count = count[0][count_key]

    data = {}
    _page = {}
    _page['count'] = count
    _page['p'] = page
    _page['row'] = page_size
    _page['tojs'] = tojs
    data['page'] = yf.getPage(_page)
    data['data'] = clist

    return yf.returnJson(True, 'ok', data)


def getLogsErrorList():
    args = getArgs()
    check = checkArgs(args, ['page', 'page_size',
                             'site', 'status_code', 'query_date'])
    if not check[0]:
        return check[1]

    pager = checkPager(args)
    if not pager[0]:
        return pager[1]
    page, page_size = pager[1], pager[2]

    ok, domain = getSiteArg(args)
    if not ok:
        return domain

    query_date = normalizeQueryDate(args['query_date'])
    if query_date is None:
        return yf.returnJson(False, '时间范围参数不合法')

    tojs = args.get('tojs', '')
    status_code = args['status_code']
    setDefaultSite(domain)

    limit = str(page_size) + ' offset ' + str(page_size * (page - 1))
    conn = pSqliteDb('web_logs', domain)

    field = 'time,ip,domain,server_name,method,protocol,status_code,ip_list,client_port,body_length,user_agent,referer,request_time,uri,body_length'
    conn = conn.field(field)
    conn = conn.where("1=1", ())

    if status_code != "all":
        if status_code.find("x") > -1:
            status_code = status_code.replace("x", "%")
            conn = conn.andWhere("status_code like ?", (status_code,))
        else:
            conn = conn.andWhere("status_code=?", (status_code,))
    else:
        conn = conn.andWhere(
            "(status_code like '50%' or status_code like '40%')", ())

    todayTime = time.strftime('%Y-%m-%d 00:00:00', time.localtime())
    todayUt = int(time.mktime(time.strptime(todayTime, "%Y-%m-%d %H:%M:%S")))
    if query_date == 'today':
        conn = conn.andWhere("time>=?", (todayUt,))
    elif query_date == "yesterday":
        conn = conn.andWhere("time>=? and time<=?", (todayUt - 86400, todayUt))
    elif query_date == "l7":
        conn = conn.andWhere("time>=?", (todayUt - 7 * 86400,))
    elif query_date == "l30":
        conn = conn.andWhere("time>=?", (todayUt - 30 * 86400,))
    else:
        exlist = query_date.split("-")
        conn = conn.andWhere("time>=? and time<=?", (exlist[0], exlist[1]))

    attacHistoryLogHack(conn, domain, query_date)

    clist = conn.limit(limit).order('time desc').inquiry()
    count_key = "count(*) as num"
    count = conn.field(count_key).limit('').order('').inquiry()
    count = count[0][count_key]

    data = {}
    _page = {}
    _page['count'] = count
    _page['p'] = page
    _page['row'] = page_size
    _page['tojs'] = tojs
    data['page'] = yf.getPage(_page)
    data['data'] = clist

    return yf.returnJson(True, 'ok', data)


def getClientStatList():
    args = getArgs()
    check = checkArgs(args, ['page', 'page_size',
                             'site', 'query_date'])
    if not check[0]:
        return check[1]

    pager = checkPager(args)
    if not pager[0]:
        return pager[1]
    page, page_size = pager[1], pager[2]

    ok, domain = getSiteArg(args)
    if not ok:
        return domain

    query_date = normalizeQueryDate(args['query_date'])
    if query_date is None:
        return yf.returnJson(False, '时间范围参数不合法')

    tojs = args.get('tojs', '')
    setDefaultSite(domain)

    conn = pSqliteDb('client_stat', domain)
    stat = pSqliteDb('client_stat', domain)

    # 列表
    limit = str(page_size) + ' offset ' + str(page_size * (page - 1))
    field = 'time,weixin,android,iphone,mac,windows,linux,edeg,firefox,msie,metasr,qh360,theworld,tt,maxthon,opera,qq,uc,pc2345,safari,chrome,machine,mobile,other'
    field_sum = toSumField(field.replace("time,", ""))
    time_field = "substr(time,1,8),"
    field_sum = time_field + field_sum

    stat = stat.field(field_sum)
    if query_date == "today":
        todayTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 0 * 86400))
        stat.where("time >= ?", (todayTime,))
    elif query_date == "yesterday":
        startTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 1 * 86400))
        endTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time()))
        stat.where("time>=? and time<=?", (startTime, endTime))
    elif query_date == "l7":
        todayTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 7 * 86400))
        stat.where("time >= ?", (todayTime,))
    elif query_date == "l30":
        todayTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 30 * 86400))
        stat.where("time >= ?", (todayTime,))
    else:
        exlist = query_date.split("-")
        start = time.strftime(
            '%Y%m%d00', time.localtime(int(exlist[0])))
        end = time.strftime(
            '%Y%m%d23', time.localtime(int(exlist[1])))
        stat.where("time >= ? and time <= ? ", (start, end,))

    # 图表数据
    statlist = stat.group('substr(time,1,4)').inquiry(field)

    if len(statlist) > 0:
        del(statlist[0]['time'])

        pc = 0
        pc_key_list = ['chrome', 'qh360', 'edeg', 'firefox', 'safari', 'msie',
                       'metasr', 'theworld', 'tt', 'maxthon', 'opera', 'qq', 'pc2345']

        for x in pc_key_list:
            pc += statlist[0][x]

        mobile = 0
        mobile_key_list = ['mobile', 'android', 'iphone', 'weixin']
        for x in mobile_key_list:
            mobile += statlist[0][x]
        reqest_total = pc + mobile

        sum_data = {
            "pc": pc,
            "mobile": mobile,
            "reqest_total": reqest_total,
        }

        statlist = sorted(statlist[0].items(),
                          key=lambda x: x[1], reverse=True)
        _statlist = statlist[0:10]
        __statlist = {}
        statlist = []
        for x in _statlist:
            __statlist[x[0]] = x[1]
        statlist.append(__statlist)
    else:
        sum_data = {
            "pc": 0,
            "mobile": 0,
            "reqest_total": 0,
        }
        statlist = []

    # 列表数据
    conn = conn.field(field_sum)
    clist = conn.group('substr(time,1,8)').limit(
        limit).order('time desc').inquiry(field)

    sql = "SELECT count(*) num from (\
            SELECT count(*) as num FROM client_stat GROUP BY substr(time,1,8)\
        )"
    result = conn.query(sql, ())
    result = list(result)
    count = result[0][0]

    data = {}
    _page = {}
    _page['count'] = count
    _page['p'] = page
    _page['row'] = page_size
    _page['tojs'] = tojs
    data['page'] = yf.getPage(_page)
    data['data'] = clist
    data['stat_list'] = statlist
    data['sum_data'] = sum_data

    return yf.returnJson(True, 'ok', data)


def getDateRangeList(start, end):
    dlist = []
    if start > end:
        for x in list(range(start, 32, 1)):
            dlist.append(x)

        for x in list(range(1, end, 1)):
            dlist.append(x)
    else:
        for x in list(range(start, end, 1)):
            dlist.append(x)

    return dlist


def dayRangeList(start_day, end_day):
    """[start_day, end_day] 闭区间的日号列表（跨月时环绕）。"""
    if start_day <= end_day:
        return list(range(start_day, end_day + 1))
    return list(range(start_day, 32)) + list(range(1, end_day + 1))


def dayFlowField(query_date, prefix):
    """自定义时间范围（<epoch>-<epoch>）→ 按 day/flow 列求和字段。"""
    a, b = query_date.split('-', 1)
    rlist = dayRangeList(time.localtime(int(a)).tm_mday,
                         time.localtime(int(b)).tm_mday)
    field_day = "".join("+cast(day" + str(x) + " as TEXT)" for x in rlist).strip("+")
    field_flow = "".join("+cast(flow" + str(x) + " as TEXT)" for x in rlist).strip("+")
    return prefix + ",(" + field_day + ') as day,(' + field_flow + ") as flow"


def getIpStatList():
    args = getArgs()
    check = checkArgs(args, ['site', 'query_date'])
    if not check[0]:
        return check[1]

    ok, domain = getSiteArg(args)
    if not ok:
        return domain

    tojs = args.get('tojs', '')
    query_date = normalizeQueryDate(args['query_date'])
    if query_date is None:
        return yf.returnJson(False, '时间范围参数不合法')
    setDefaultSite(domain)

    conn = pSqliteDb('ip_stat', domain)

    origin_field = "ip,day,flow"

    if query_date == "today":
        ftime = time.localtime(time.time())
        day = ftime.tm_mday

        field_day = "day" + str(day)
        field_flow = "flow" + str(day)
        # print(field_day, field_flow)

        field = "ip," + field_day + ' as day,' + field_flow + " as flow"

        conn = conn.field(field)
        conn = conn.where("day>? and flow>?", (0, 0,))

    elif query_date == "yesterday":

        ftime = time.localtime(time.time() - 86400)
        day = ftime.tm_mday

        field_day = "day" + str(day)
        field_flow = "flow" + str(day)

        field = "ip," + field_day + ' as day,' + field_flow + " as flow"

        conn = conn.field(field)
        conn = conn.where("day>? and flow>?", (0, 0,))
    elif query_date == "l7":

        field_day = ""
        field_flow = ""

        now_time = time.localtime(time.time())
        end_day = now_time.tm_mday

        start_time = time.localtime(time.time() - 7 * 86400)
        start_day = start_time.tm_mday

        rlist = getDateRangeList(start_day, end_day)

        for x in rlist:
            field_day += "+cast(day" + str(x) + " as TEXT)"
            field_flow += "+cast(flow" + str(x) + " as TEXT)"

        field_day = field_day.strip("+")
        field_flow = field_flow.strip("+")

        field = "ip,(" + field_day + ') as day,(' + field_flow + ") as flow"
        conn = conn.field(field)
        conn = conn.where("day>? and flow>?", (0, 0,))

    elif query_date == "l30":

        field_day = ""
        field_flow = ""

        for x in list(range(1, 32, 1)):
            field_day += "+cast(day" + str(x) + " as TEXT)"
            field_flow += "+cast(flow" + str(x) + " as TEXT)"

        field_day = field_day.strip("+")
        field_flow = field_flow.strip("+")

        # print(field_day)
        # print(field_flow)
        field = "ip,(" + field_day + ') as day,(' + field_flow + ") as flow"
        conn = conn.field(field)
        conn = conn.where("day>? and flow>?", (0, 0,))

    else:
        # 自定义时间范围（前端 laydate 传 <epoch>-<epoch>）
        field = dayFlowField(query_date, 'ip')
        conn = conn.field(field)
        conn = conn.where("day>? and flow>?", (0, 0,))

    clist = conn.order("flow desc").limit("50").inquiry(origin_field)
    # print(clist)

    total_req = 0
    total_flow = 0

    gepip_mmdb = getServerDir() + '/GeoLite2-City.mmdb'
    geoip_exists = False
    if os.path.exists(gepip_mmdb):
        import geoip2.database
        reader = geoip2.database.Reader(gepip_mmdb)
        geoip_exists = True
        # response = reader.city("172.70.206.144")
        # print(response.country.names["zh-CN"])
        # print(response.subdivisions.most_specific.names["zh-CN"])
        # print(response.city.names["zh-CN"])

    for x in clist:
        total_req += x['day']
        total_flow += x['flow']

    for i in range(len(clist)):
        clist[i]['day_rate'] = round((clist[i]['day'] / total_req) * 100, 2)
        clist[i]['flow_rate'] = round((clist[i]['flow'] / total_flow) * 100, 2)
        ip = clist[i]['ip']

        if ip == "127.0.0.1":
            clist[i]['area'] = "本地"
        elif geoip_exists:
            try:
                response = reader.city(ip)
                country = response.country.names["zh-CN"]

                # print(ip, response.subdivisions)
                _subdivisions = response.subdivisions
                try:
                    if len(_subdivisions) < 1:
                        subdivisions = ""
                    else:
                        subdivisions = "," + response.subdivisions.most_specific.names[
                            "zh-CN"]
                except Exception as e:
                    subdivisions = ""

                try:
                    if 'zh-CN' in response.city.names:
                        city = "," + response.city.names["zh-CN"]
                    else:
                        city = "," + response.city.names["en"]
                except Exception as e:
                    city = ""

                clist[i]['area'] = country + subdivisions + city
            except Exception as e:
                clist[i]['area'] = "内网?"

    return yf.returnJson(True, 'ok', clist)


def getUriStatList():
    args = getArgs()
    check = checkArgs(args, ['site', 'query_date'])
    if not check[0]:
        return check[1]

    ok, domain = getSiteArg(args)
    if not ok:
        return domain

    tojs = args.get('tojs', '')
    query_date = normalizeQueryDate(args['query_date'])
    if query_date is None:
        return yf.returnJson(False, '时间范围参数不合法')
    setDefaultSite(domain)

    conn = pSqliteDb('uri_stat', domain)

    origin_field = "uri,day,flow"

    if query_date == "today":
        ftime = time.localtime(time.time())
        day = ftime.tm_mday

        field_day = "day" + str(day)
        field_flow = "flow" + str(day)
        # print(field_day, field_flow)

        field = "uri," + field_day + ' as day,' + field_flow + " as flow"

        conn = conn.field(field)
        conn = conn.where("day>? and flow>?", (0, 0,))

    elif query_date == "yesterday":

        ftime = time.localtime(time.time() - 86400)
        day = ftime.tm_mday

        field_day = "day" + str(day)
        field_flow = "flow" + str(day)

        field = "uri," + field_day + ' as day,' + field_flow + " as flow"

        conn = conn.field(field)
        conn = conn.where("day>? and flow>?", (0, 0,))
    elif query_date == "l7":

        field_day = ""
        field_flow = ""

        now_time = time.localtime(time.time())
        end_day = now_time.tm_mday

        start_time = time.localtime(time.time() - 7 * 86400)
        start_day = start_time.tm_mday

        rlist = getDateRangeList(start_day, end_day)

        for x in rlist:
            field_day += "+cast(day" + str(x) + " as TEXT)"
            field_flow += "+cast(flow" + str(x) + " as TEXT)"

        field_day = field_day.strip("+")
        field_flow = field_flow.strip("+")

        field = "uri,(" + field_day + ') as day,(' + field_flow + ") as flow"
        conn = conn.field(field)
        conn = conn.where("day>? and flow>?", (0, 0,))

    elif query_date == "l30":

        field_day = ""
        field_flow = ""

        for x in list(range(1, 32, 1)):
            field_day += "+cast(day" + str(x) + " as TEXT)"
            field_flow += "+cast(flow" + str(x) + " as TEXT)"

        field_day = field_day.strip("+")
        field_flow = field_flow.strip("+")

        # print(field_day)
        # print(field_flow)
        field = "uri,(" + field_day + ') as day,(' + field_flow + ") as flow"
        conn = conn.field(field)
        conn = conn.where("day>? and flow>?", (0, 0,))

    else:
        # 自定义时间范围（前端 laydate 传 <epoch>-<epoch>）
        field = dayFlowField(query_date, 'uri')
        conn = conn.field(field)
        conn = conn.where("day>? and flow>?", (0, 0,))

    clist = conn.order("flow desc").limit("50").inquiry(origin_field)

    total_req = 0
    total_flow = 0

    for x in clist:
        total_req += x['day']
        total_flow += x['flow']

    for i in range(len(clist)):
        clist[i]['day_rate'] = round((clist[i]['day'] / total_req) * 100, 2)
        clist[i]['flow_rate'] = round((clist[i]['flow'] / total_flow) * 100, 2)

    return yf.returnJson(True, 'ok', clist)


def getWebLogCount(domain, query_date):
    conn = pSqliteDb('web_logs', domain)

    todayTime = time.strftime('%Y-%m-%d 00:00:00', time.localtime())
    todayUt = int(time.mktime(time.strptime(todayTime, "%Y-%m-%d %H:%M:%S")))
    if query_date == 'today':
        conn = conn.where("time>=?", (todayUt,))
    elif query_date == "yesterday":
        conn = conn.where("time>=? and time<=?", (todayUt - 86400, todayUt))
    elif query_date == "l7":
        conn = conn.where("time>=?", (todayUt - 7 * 86400,))
    elif query_date == "l30":
        conn = conn.where("time>=?", (todayUt - 30 * 86400,))
    else:
        exlist = str(query_date).split("-")
        if len(exlist) != 2:
            return 0
        conn = conn.where("time>=? and time<=?", (exlist[0], exlist[1]))

    count_key = "count(*) as num"
    count = conn.field(count_key).limit('').order('').inquiry()
    count = count[0][count_key]
    return count


def getSpiderStatList():
    args = getArgs()
    check = checkArgs(args, ['page', 'page_size',
                             'site', 'query_date'])
    if not check[0]:
        return check[1]

    pager = checkPager(args)
    if not pager[0]:
        return pager[1]
    page, page_size = pager[1], pager[2]

    ok, domain = getSiteArg(args)
    if not ok:
        return domain

    query_date = normalizeQueryDate(args['query_date'])
    if query_date is None:
        return yf.returnJson(False, '时间范围参数不合法')

    tojs = args.get('tojs', '')
    setDefaultSite(domain)

    conn = pSqliteDb('spider_stat', domain)
    stat = pSqliteDb('spider_stat', domain)

    total_req = getWebLogCount(domain, query_date)

    # 列表
    limit = str(page_size) + ' offset ' + str(page_size * (page - 1))
    field = 'time,bytes,bing,soso,yahoo,sogou,google,baidu,qh360,youdao,yandex,dnspod,other'
    field_sum = toSumField(field.replace("time,", ""))
    time_field = "substr(time,1,8),"
    field_sum = time_field + field_sum

    stat = stat.field(field_sum)
    if query_date == "today":
        todayTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 0 * 86400))
        stat.where("time >= ?", (todayTime,))
    elif query_date == "yesterday":
        startTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 1 * 86400))
        endTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time()))
        stat.where("time>=? and time<=?", (startTime, endTime))
    elif query_date == "l7":
        todayTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 7 * 86400))
        stat.where("time >= ?", (todayTime,))
    elif query_date == "l30":
        todayTime = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 30 * 86400))
        stat.where("time >= ?", (todayTime,))
    else:
        exlist = query_date.split("-")
        start = time.strftime(
            '%Y%m%d00', time.localtime(int(exlist[0])))
        end = time.strftime(
            '%Y%m%d23', time.localtime(int(exlist[1])))
        stat.where("time >= ? and time <= ? ", (start, end,))

    # 图表数据
    statlist = stat.group('substr(time,1,4)').inquiry(field)

    if len(statlist) > 0:
        del(statlist[0]['time'])

        spider_total = 0
        for x in statlist[0]:
            spider_total += statlist[0][x]

        sum_data = {"spider": spider_total, "reqest_total": total_req}
        statlist = sorted(statlist[0].items(),
                          key=lambda x: x[1], reverse=True)
        _statlist = statlist[0:9]
        __statlist = {}
        statlist = []
        for x in _statlist:
            __statlist[x[0]] = x[1]
        statlist.append(__statlist)
    else:
        sum_data = {"spider": 0, "reqest_total": total_req}
        statlist = []

    # 列表数据
    conn = conn.field(field_sum)
    clist = conn.group('substr(time,1,8)').limit(
        limit).order('time desc').inquiry(field)

    sql = "SELECT count(*) num from (\
            SELECT count(*) as num FROM spider_stat GROUP BY substr(time,1,8)\
        )"
    result = conn.query(sql, ())
    result = list(result)
    count = result[0][0]

    data = {}
    _page = {}
    _page['count'] = count
    _page['p'] = page
    _page['row'] = page_size
    _page['tojs'] = tojs
    data['page'] = yf.getPage(_page)
    data['data'] = clist
    data['stat_list'] = statlist
    data['sum_data'] = sum_data

    return yf.returnJson(True, 'ok', data)


def installPreInspection():
    check_op = yf.getServerDir() + "/openresty"
    if not os.path.exists(check_op):
        return "请先安装OpenResty"
    return 'ok'


def runInfo():
    """运行信息。webstats 没有独立守护进程，运行态由 vhost 配置是否存在决定。"""
    return status()

def uninstallPreInspection():
    stop()
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
    elif func == 'uninstall_pre_inspection':
        print(uninstallPreInspection())
    elif func == 'run_info':
        print(runInfo())
    elif func == 'get_global_conf':
        print(getGlobalConf())
    elif func == 'set_global_conf':
        print(setGlobalConf())
    elif func == 'get_site_conf':
        print(getSiteConf())
    elif func == 'set_site_conf':
        print(setSiteConf())
    elif func == 'get_default_site':
        print(getDefaultSite())
    elif func == 'get_overview_list':
        print(getOverviewList())
    elif func == 'get_site_list':
        print(getSiteList())
    elif func == 'get_logs_list':
        print(getLogsList())
    elif func == 'get_logs_error_list':
        print(getLogsErrorList())
    elif func == 'get_logs_realtime_info':
        print(getLogsRealtimeInfo())
    elif func == 'get_client_stat_list':
        print(getClientStatList())
    elif func == 'get_ip_stat_list':
        print(getIpStatList())
    elif func == 'get_uri_stat_list':
        print(getUriStatList())
    elif func == 'get_spider_stat_list':
        print(getSpiderStatList())
    else:
        print('error')
