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


def getPluginName():
    return 'op_waf'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)
    if args_len > 0:
        val = args[0].strip()
        try:
            if val.startswith('{') and val.endswith('}'):
                return json.loads(val)
        except Exception:
            pass

        import base64
        import urllib.parse
        try:
            decoded = urllib.parse.unquote(base64.b64decode(val.encode('utf-8')).decode('utf-8'))
            if decoded.startswith('{') and decoded.endswith('}'):
                return json.loads(decoded)
        except Exception:
            pass

        for i in range(args_len):
            t = args[i].split(':', 1)
            if len(t) == 2:
                tmp[t[0]] = t[1]
    return tmp


def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            # 单一完整消息键（前端 wafMsg() 负责用 {1} 插值本地化）。
            # 原实现 '参数:(' + ck[i] + ')没有!' 是碎片拼接，
            # 会产生 ')没有!' / '参数:(' 两个无法翻译的脏键。
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


sys.path.append(getPluginDir() + "/class")
from luamaker import luamaker


def listToLuaFile(path, lists):
    content = luamaker.makeLuaTable(lists)
    content = "return " + content
    yf.writeFile(path, content)


def htmlToLuaFile(path, content):
    content = "return [[" + content + "]]"
    yf.writeFile(path, content)


def getConf():
    path = yf.getServerDir() + "/openresty/nginx/conf/nginx.conf"
    return path


def dstWafConfPath():
    return yf.getServerDir() + "/web_conf/nginx/vhost/opwaf.conf"


def pSqliteDb(dbname='logs'):
    name = "waf"
    db_dir = getServerDir() + '/logs/'

    if not os.path.exists(db_dir):
        yf.makeDirs(db_dir)

    file = db_dir + name + '.db'
    if not os.path.exists(file):
        conn = yf.M(dbname).dbPos(db_dir, name)
        sql = yf.readFile(getPluginDir() + '/conf/init.sql')
        sql_list = sql.split(';')
        for index in range(len(sql_list)):
            conn.execute(sql_list[index])
    else:
        conn = yf.M(dbname).dbPos(db_dir, name)

    conn.execute("PRAGMA synchronous = 0")
    conn.execute("PRAGMA page_size = 4096")
    conn.execute("PRAGMA journal_mode = wal")
    conn.execute("PRAGMA journal_size_limit = 1073741824")
    return conn


def initDomainInfo(conf_reload=False):
    data = []
    path_domains = getJsonPath('domains')
    _list = yf.M('sites').field('id,name,path').where(
        'status=?', ('1',)).order('id desc').select()

    for i in range(len(_list)):
        tmp = {}
        tmp['name'] = _list[i]['name']
        tmp['path'] = _list[i]['path']

        _list_domain = yf.M('domain').field('name').where(
            'pid=?', (_list[i]['id'],)).order('id desc').select()

        tmp_j = []
        for j in range(len(_list_domain)):
            tmp_j.append(_list_domain[j]['name'])

        tmp['domains'] = tmp_j
        data.append(tmp)
    cjson = yf.getJson(data)
    yf.writeFile(path_domains, cjson)


def initSiteInfo(conf_reload=False):
    data = []

    path_site = getJsonPath('site')
    path_domains = getJsonPath('domains')
    path_config = getJsonPath('config')

    config_contents = yf.readFile(path_config)
    config_contents = json.loads(config_contents)

    domain_contents = yf.readFile(path_domains)
    domain_contents = json.loads(domain_contents)

    try:
        site_contents = yf.readFile(path_site)
        if not site_contents:
            site_contents = "{}"
    except Exception as e:
        site_contents = "{}"

    site_contents = json.loads(site_contents)
    site_contents_new = {}
    for x in range(len(domain_contents)):
        name = domain_contents[x]['name']
        if name in site_contents:
            site_contents_new[name] = site_contents[name]
            # 兼容老数据的 allow_curl 字段并自动平滑迁移
            if 'curl_protection' not in site_contents_new[name]:
                if 'allow_curl' in site_contents_new[name]:
                    site_contents_new[name]['curl_protection'] = not site_contents_new[name]['allow_curl']
                    del site_contents_new[name]['allow_curl']
                else:
                    site_contents_new[name]['curl_protection'] = True
            if 'allow_curl' in site_contents_new[name]:
                del site_contents_new[name]['allow_curl']
        else:
            tmp = {}
            tmp['cdn'] = True
            tmp['log'] = True
            tmp['get'] = True
            tmp['post'] = True
            tmp['open'] = True

            tmp['cc'] = config_contents['cc']
            tmp['retry'] = config_contents['retry']
            tmp['get'] = config_contents['get']
            tmp['post'] = config_contents['post']
            tmp['user-agent'] = config_contents['user-agent']
            tmp['cookie'] = config_contents['cookie']
            tmp['scan'] = config_contents['scan']
            tmp['safe_verify'] = config_contents['safe_verify']
            tmp['curl_protection'] = True

            cdn_header = ['x-forwarded-for',
                          'x-real-ip',
                          'x-forwarded',
                          'forwarded-for',
                          'forwarded',
                          'true-client-ip',
                          'client-ip',
                          'ali-cdn-real-ip',
                          'cdn-src-ip',
                          'cdn-real-ip',
                          'cf-connecting-ip',
                          'x-cluster-client-ip',
                          'wl-proxy-client-ip',
                          'proxy-client-ip',
                          'true-client-ip',
                          'HTTP_CF_CONNECTING_IP']
            tmp['cdn_header'] = cdn_header

            disable_upload_ext = ["php", "jsp"]
            tmp['disable_upload_ext'] = disable_upload_ext

            disable_path = ['sql']
            tmp['disable_ext'] = disable_path

            site_contents_new[name] = tmp

    cjson = yf.getJson(site_contents_new)
    yf.writeFile(path_site, cjson)


def initTotalInfo(conf_reload=False):
    data = []

    path_total = getJsonPath('total')
    path_domains = getJsonPath('domains')

    domain_contents = yf.readFile(path_domains)
    if not domain_contents or type(domain_contents) == bool:
        domain_contents = "[]"
    domain_contents = json.loads(domain_contents)

    try:
        total_contents = yf.readFile(path_total)
        if not total_contents or type(total_contents) == bool:
            total_contents = "{}"
    except Exception as e:
        total_contents = "{}"

    total_contents = json.loads(total_contents)
    total_contents_new = {}
    for x in range(len(domain_contents)):
        name = domain_contents[x]['name']
        if 'sites' in total_contents and name in total_contents['sites']:
            pass
        else:
            if 'sites' not in total_contents:
                total_contents['sites'] = {}
            tmp = {}
            tmp['cdn'] = 0
            tmp['log'] = 0
            tmp['get'] = 0
            tmp['post'] = 0
            tmp['total'] = 0
            tmp['path'] = 0
            tmp['php_path'] = 0
            tmp['upload_ext'] = 0
            total_contents['sites'][name] = tmp

    total_contents['start_time'] = str(time.time())
    cjson = yf.getJson(total_contents)
    yf.writeFile(path_total, cjson)


def contentReplace(content):
    service_path = yf.getServerDir()
    waf_root = getServerDir()
    waf_path = waf_root + "/waf"
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$WAF_PATH}', waf_path)
    content = content.replace('{$WAF_ROOT}', waf_root)

    if yf.isAppleSystem():
        content = content.replace('{$MMDB_FILE_SUFFIX}', 'dylib')
    else:
        content = content.replace('{$MMDB_FILE_SUFFIX}', 'so')

    return content


def autoMakeLuaConfSingle(file, conf_reload=False):
    path = getServerDir() + "/waf/rule/" + file + ".json"
    if not os.path.exists(path):
        plugin_src = getPluginDir() + "/waf/rule/" + file + ".json"
        if os.path.exists(plugin_src):
            yf.makeDirs(os.path.dirname(path))
            yf.writeFile(path, yf.readFile(plugin_src))
    dst_path = getServerDir() + "/waf/conf/rule_" + file + ".lua"
    if not os.path.exists(dst_path) or conf_reload:
        content = yf.readFile(path)
        if type(content) == bool or not content:
            content = "[]"
        # print(content)
        content = json.loads(content)
        yf.makeDirs(os.path.dirname(dst_path))
        listToLuaFile(dst_path, content)


def autoCpImport(file):
    path = getPluginDir() + "/waf/" + file + ".json"
    dst_path = getServerDir() + "/waf/" + file + ".json"
    content = yf.readFile(path)
    yf.writeFile(dst_path, content)


def autoMakeLuaImportSingle(file, conf_reload=False):
    path = getServerDir() + "/waf/" + file + ".json"
    if not os.path.exists(path):
        plugin_src = getPluginDir() + "/waf/" + file + ".json"
        if os.path.exists(plugin_src):
            yf.makeDirs(os.path.dirname(path))
            yf.writeFile(path, yf.readFile(plugin_src))
    dst_path = getServerDir() + "/waf/conf/waf_" + file + ".lua"
    if not os.path.exists(dst_path) or conf_reload:
        content = yf.readFile(path)
        if type(content) == bool or not content:
            content = "{}"
        # print(content)
        content = json.loads(content)
        yf.makeDirs(os.path.dirname(dst_path))
        listToLuaFile(dst_path, content)


def autoMakeLuaHtmlSingle(file, conf_reload=False):
    path = getServerDir() + "/waf/html/" + file + ".html"
    plugin_src = getPluginDir() + "/waf/html/" + file + ".html"
    if not os.path.exists(path):
        if os.path.exists(plugin_src):
            yf.makeDirs(os.path.dirname(path))
            yf.writeFile(path, yf.readFile(plugin_src))
    else:
        # 平滑升级旧版模板：若缺少多语言 waf-i18n 支持或含有旧版公司名称，自动备份并升级为最新国际化模板
        content_old = yf.readFile(path)
        if isinstance(content_old, str) and os.path.exists(plugin_src):
            if 'waf-i18n' not in content_old or '熠风' in content_old:
                bak_path = path + ".wafbak"
                if not os.path.exists(bak_path):
                    yf.writeFile(bak_path, content_old)
                yf.writeFile(path, yf.readFile(plugin_src))
                conf_reload = True
    dst_path = getServerDir() + "/waf/html/html_" + file + ".lua"
    if not os.path.exists(dst_path) or conf_reload:
        content = yf.readFile(path)
        if type(content) == bool or not content:
            content = ""
        yf.makeDirs(os.path.dirname(dst_path))
        htmlToLuaFile(dst_path, content)


def autoCpHtml(file):
    path = getPluginDir() + "/waf/html/" + file + ".html"
    dst_path = getServerDir() + "/waf/html/" + file + ".html"
    content = yf.readFile(path)
    yf.writeFile(dst_path, content)


def autoMakeLuaConf(conf_reload=False, cp_reload=False):
    conf_list = ['args', 'cookie', 'ip_black', 'ip_white',
                 'ipv6_black', 'post', 'scan_black', 'url',
                 'url_white', 'user_agent', 'ssrf', 'vuln', 'spider_ip']
    for x in conf_list:
        autoMakeLuaConfSingle(x, conf_reload)

    import_list = ['config', 'site', 'domains', 'area_limit']
    for x in import_list:
        autoMakeLuaImportSingle(x, conf_reload)

    html_list = ['get', 'post', 'safe_js', 'user_agent', 'cookie', 'other']
    for x in html_list:
        if cp_reload:
            autoCpHtml(x)
        autoMakeLuaHtmlSingle(x, conf_reload)


def initDefaultInfo(conf_reload=False):
    path = getServerDir()
    dst_path = path + "/waf/default.pl"
    default_site = ''
    if os.path.exists(dst_path):
        val = yf.readFile(dst_path)
        if val and val.strip():
            return True
    source_path = path + "/waf/domains.json"
    content = yf.readFile(source_path)
    dlist = []
    dlist.append('ALL')
    try:
        if content:
            content_json = json.loads(content)
            for i in content_json:
                dlist.append(i["name"])
    except Exception:
        pass

    ddata = {}
    ddata["list"] = dlist
    default_site = "ALL"

    yf.writeFile(dst_path, default_site)



def getSiteListData():
    path = getServerDir()
    source_path = path + "/waf/domains.json"
    dst_path = path + "/waf/default.pl"

    content = yf.readFile(source_path)
    dlist = []
    dlist.append('ALL')
    try:
        if content:
            content_json = json.loads(content)
            for i in content_json:
                dlist.append(i["name"])
    except Exception:
        pass

    default_site = yf.readFile(dst_path)
    if default_site:
        default_site = default_site.strip()
    if not default_site or default_site == 'unset':
        default_site = 'ALL'

    data = {}
    data['list'] = dlist
    data['default'] = default_site
    return data


def setDefaultSite(name):
    path = getServerDir()
    dst_path = path + "/waf/default.pl"
    yf.writeFile(dst_path, name)
    return yf.returnJson(True, 'OK')


def getDefaultSite():
    data = getSiteListData()
    return yf.returnJson(True, 'OK', data)


def getCountry():
    data = ['中国大陆以外的地区(包括[中国特别行政区:港,澳,台])', '中国大陆(不包括[中国特别行政区:港,澳,台])', '中国香港', '中国澳门', '中国台湾',
            '美国', '日本', '英国', '德国', '韩国', '法国', '巴西', '加拿大', '意大利', '澳大利亚', '荷兰', '俄罗斯', '印度', '瑞典', '西班牙', '墨西哥',
            '比利时', '南非', '波兰', '瑞士', '阿根廷', '印度尼西亚', '埃及', '哥伦比亚', '土耳其', '越南', '挪威', '芬兰', '丹麦', '乌克兰', '奥地利',
            '伊朗', '智利', '罗马尼亚', '捷克', '泰国', '沙特阿拉伯', '以色列', '新西兰', '委内瑞拉', '摩洛哥', '马来西亚', '葡萄牙', '爱尔兰', '新加坡',
            '欧洲联盟', '匈牙利', '希腊', '菲律宾', '巴基斯坦', '保加利亚', '肯尼亚', '阿拉伯联合酋长国', '阿尔及利亚', '塞舌尔', '突尼斯', '秘鲁', '哈萨克斯坦',
            '斯洛伐克', '斯洛文尼亚', '厄瓜多尔', '哥斯达黎加', '乌拉圭', '立陶宛', '塞尔维亚', '尼日利亚', '克罗地亚', '科威特', '巴拿马', '毛里求斯', '白俄罗斯',
            '拉脱维亚', '多米尼加', '卢森堡', '爱沙尼亚', '苏丹', '格鲁吉亚', '安哥拉', '玻利维亚', '赞比亚', '孟加拉国', '巴拉圭', '波多黎各', '坦桑尼亚',
            '塞浦路斯', '摩尔多瓦', '阿曼', '冰岛', '叙利亚', '卡塔尔', '波黑', '加纳', '阿塞拜疆', '马其顿', '约旦', '萨尔瓦多', '伊拉克', '亚美尼亚', '马耳他',
            '危地马拉', '巴勒斯坦', '斯里兰卡', '特立尼达和多巴哥', '黎巴嫩', '尼泊尔', '纳米比亚', '巴林', '洪都拉斯', '莫桑比克', '尼加拉瓜', '卢旺达', '加蓬',
            '阿尔巴尼亚', '利比亚', '吉尔吉斯坦', '柬埔寨', '古巴', '喀麦隆', '乌干达', '塞内加尔', '乌兹别克斯坦', '黑山', '关岛', '牙买加', '蒙古', '文莱',
            '英属维尔京群岛', '留尼旺', '库拉索岛', '科特迪瓦', '开曼群岛', '巴巴多斯', '马达加斯加', '伯利兹', '新喀里多尼亚', '海地', '马拉维', '斐济', '巴哈马',
            '博茨瓦纳', '扎伊尔', '阿富汗', '莱索托', '百慕大', '埃塞俄比亚', '美属维尔京群岛', '列支敦士登', '津巴布韦', '直布罗陀', '苏里南', '马里', '也门',
            '老挝', '塔吉克斯坦', '安提瓜和巴布达', '贝宁', '法属玻利尼西亚', '圣基茨和尼维斯', '圭亚那', '布基纳法索', '马尔代夫', '泽西岛', '摩纳哥', '巴布亚新几内亚',
            '刚果', '塞拉利昂', '吉布提', '斯威士兰', '缅甸', '毛里塔尼亚', '法罗群岛', '尼日尔', '安道尔', '阿鲁巴', '布隆迪', '圣马力诺', '利比里亚',
            '冈比亚', '不丹', '几内亚', '圣文森特岛', '荷兰加勒比区', '圣马丁', '多哥', '格陵兰', '佛得角', '马恩岛', '索马里', '法属圭亚那', '西萨摩亚',
            '土库曼斯坦', '瓜德罗普', '马里亚那群岛', '瓦努阿图', '马提尼克', '赤道几内亚', '南苏丹', '梵蒂冈', '格林纳达', '所罗门群岛', '特克斯和凯科斯群岛', '多米尼克',
            '乍得', '汤加', '瑙鲁', '圣多美和普林西比', '安圭拉岛', '法属圣马丁', '图瓦卢', '库克群岛', '密克罗尼西亚联邦', '根西岛', '东帝汶', '中非',
            '几内亚比绍', '帕劳', '美属萨摩亚', '厄立特里亚', '科摩罗', '圣皮埃尔和密克隆', '瓦利斯和富图纳', '英属印度洋领地', '托克劳', '马绍尔群岛', '基里巴斯',
            '纽埃', '诺福克岛', '蒙特塞拉特岛', '朝鲜', '马约特', '圣卢西亚', '圣巴泰勒米岛']
    return yf.returnJson(True, 'ok', data)


def cleanUserAgentJsonRule():
    path = getServerDir() + "/waf/rule/user_agent.json"
    if not os.path.exists(path):
        return False
    try:
        content = yf.readFile(path)
        if not content:
            return False
        rules = json.loads(content)
        modified = False
        for rule in rules:
            if len(rule) > 1 and "非法脚本" in rule[2]:
                regex = rule[1]
                if "curl|" in regex:
                    rule[1] = regex.replace("curl|", "")
                    modified = True
                elif "|curl" in regex:
                    rule[1] = regex.replace("|curl", "")
                    modified = True
        if modified:
            yf.writeFile(path, json.dumps(rules, ensure_ascii=False))
            return True
    except Exception as e:
        print("cleanUserAgentJsonRule error: " + str(e))
    return False


def autoMakeConfig(conf_reload=False, cp_reload=False):
    if cleanUserAgentJsonRule():
        conf_reload = True
    initDomainInfo(conf_reload)
    initSiteInfo(conf_reload)
    initTotalInfo(conf_reload)
    autoMakeLuaConf(conf_reload, cp_reload)
    initDefaultInfo(conf_reload)


def setConfRestartWeb():
    if not hasattr(yf, 'isYufengPanel') or not yf.isYufengPanel():
        return yf.returnJson(False, __import__('base64').b64decode('5oKo55qE6Z2i5p2/546v5aKD5LiN5Yy56YWN77yM6K+36LCo5oWO5L2/55So77yB').decode('utf-8'))
    autoMakeConfig(True, False)
    # 优先平滑 reload，保障长连接与在线请求不被强制掐断
    res = yf.opWeb('reload')
    if not res:
        yf.opWeb('stop')
        yf.opWeb('start')


def restartWeb():
    yf.opWeb('stop')
    yf.opWeb('start')


def makeOpDstRunLua(conf_reload=False):
    if not hasattr(yf, 'isYufengPanel') or not yf.isYufengPanel():
        return yf.returnJson(False, __import__('base64').b64decode('5oKo55qE6Z2i5p2/546v5aKD5LiN5Yy56YWN77yM6K+36LCo5oWO5L2/55So77yB').decode('utf-8'))
    root_init_dir = yf.getServerDir() + '/web_conf/nginx/lua/init_by_lua_file'
    root_worker_dir = yf.getServerDir() + '/web_conf/nginx/lua/init_worker_by_lua_file'
    root_access_dir = yf.getServerDir() + '/web_conf/nginx/lua/access_by_lua_file'
    root_log_dir = yf.getServerDir() + '/web_conf/nginx/lua/log_by_lua_file'
    path = getServerDir()
    path_tpl = getPluginDir()

    waf_common_dst = path + "/waf/lua/waf_common.lua"
    if not os.path.exists(waf_common_dst) or conf_reload:
        waf_common_tpl = path_tpl + "/waf/lua/waf_common.lua"
        content = yf.readFile(waf_common_tpl)
        content = contentReplace(content)
        yf.writeFile(waf_common_dst, content)

    waf_init_dst = root_init_dir + "/waf_init_preload.lua"
    if not os.path.exists(waf_init_dst) or conf_reload:
        waf_init_tpl = path_tpl + "/waf/lua/init_preload.lua"
        content = yf.readFile(waf_init_tpl)
        content = contentReplace(content)
        yf.writeFile(waf_init_dst, content)

    init_worker_dst = root_worker_dir + '/opwaf_init_worker.lua'
    if not os.path.exists(init_worker_dst) or conf_reload:
        init_worker_tpl = path_tpl + "/waf/lua/init_worker.lua"
        content = yf.readFile(init_worker_tpl)
        content = contentReplace(content)
        yf.writeFile(init_worker_dst, content)

    access_file_dst = root_access_dir + '/opwaf_init.lua'
    if not os.path.exists(access_file_dst) or conf_reload:
        access_file_tpl = path_tpl + "/waf/lua/init.lua"
        access_file_dst_s = path + "/waf/lua/init.lua"
        content = yf.readFile(access_file_tpl)
        content = contentReplace(content)
        yf.writeFile(access_file_dst, content)
        yf.writeFile(access_file_dst_s, content)

    log_file_dst = root_log_dir + '/opwaf_log.lua'
    if not os.path.exists(log_file_dst) or conf_reload:
        log_file_tpl = path_tpl + "/waf/lua/log.lua"
        log_file_dst_s = path + "/waf/lua/log.lua"
        if os.path.exists(log_file_tpl):
            content = yf.readFile(log_file_tpl)
            content = contentReplace(content)
            yf.writeFile(log_file_dst, content)
            yf.writeFile(log_file_dst_s, content)

    waf_mmdb_dst = path + "/waf/lua/waf_maxminddb.lua"
    if not os.path.exists(waf_mmdb_dst) or conf_reload:
        waf_mmdb_tpl = path_tpl + "/waf/lua/waf_maxminddb.lua"
        content = yf.readFile(waf_mmdb_tpl)
        content = contentReplace(content)
        yf.writeFile(waf_mmdb_dst, content)

    yf.opLuaMakeAll()
    return True


def makeOpDstStopLua():
    root_init_dir = yf.getServerDir() + '/web_conf/nginx/lua/init_by_lua_file'
    root_worker_dir = yf.getServerDir() + '/web_conf/nginx/lua/init_worker_by_lua_file'
    root_access_dir = yf.getServerDir() + '/web_conf/nginx/lua/access_by_lua_file'

    waf_init_dst = root_init_dir + "/waf_init_preload.lua"
    if os.path.exists(waf_init_dst):
        os.remove(waf_init_dst)

    init_worker_dst = root_worker_dir + '/opwaf_init_worker.lua'
    if os.path.exists(init_worker_dst):
        os.remove(init_worker_dst)

    access_file_dst = root_access_dir + '/opwaf_init.lua'
    if os.path.exists(access_file_dst):
        os.remove(access_file_dst)

    root_log_dir = yf.getServerDir() + '/web_conf/nginx/lua/log_by_lua_file'
    log_file_dst = root_log_dir + '/opwaf_log.lua'
    if os.path.exists(log_file_dst):
        os.remove(log_file_dst)

    wafconf = dstWafConfPath()
    if os.path.exists(wafconf):
        os.remove(wafconf)

    yf.opLuaMakeAll()
    return True


def initDreplace():
    path = getServerDir()
    if not os.path.exists(path + '/waf/lua'):
        sdir = getPluginDir() + '/waf'
        yf.safeExecShell(["cp", "-rf", sdir, path])

    logs_path = path + '/logs'
    if not os.path.exists(logs_path):
        yf.makeDirs(logs_path)

    debug_log = path + '/debug.log'
    if not os.path.exists(debug_log):
        yf.writeFile(debug_log, '')

    config = path + '/waf/config.json'
    content = yf.readFile(config)
    content = json.loads(content)
    content['reqfile_path'] = path + "/waf/html"
    yf.writeFile(config, yf.getJson(content))

    makeOpDstRunLua()

    waf_conf = dstWafConfPath()
    if not os.path.exists(waf_conf):
        waf_tpl = getPluginDir() + "/conf/luawaf.conf"
        content = yf.readFile(waf_tpl)
        content = contentReplace(content)
        yf.writeFile(waf_conf, content)

    autoMakeConfig(True, False)

    pSqliteDb()

    if not yf.isAppleSystem():
        yf.safeExecShell(["chown", "-R", "www:www", path])
    return path


def status():
    path = getConf()
    if not os.path.exists(path):
        return 'stop'

    waf_conf = dstWafConfPath()
    if not os.path.exists(waf_conf):
        return 'stop'
    return 'start'


def start():
    if not hasattr(yf, 'isYufengPanel') or not yf.isYufengPanel():
        return yf.returnJson(False, __import__('base64').b64decode('5oKo55qE6Z2i5p2/546v5aKD5LiN5Yy56YWN77yM6K+36LCo5oWO5L2/55So77yB').decode('utf-8'))
    initDreplace()

    import tool_task
    tool_task.createBgTask()

    restartWeb()
    return 'ok'


def stop():

    makeOpDstStopLua()

    import tool_task
    tool_task.removeBgTask()

    restartWeb()
    return 'ok'


def restart():
    restartWeb()
    return 'ok'


def reload():
    if not hasattr(yf, 'isYufengPanel') or not yf.isYufengPanel():
        return yf.returnJson(False, __import__('base64').b64decode('5oKo55qE6Z2i5p2/546v5aKD5LiN5Yy56YWN77yM6K+36LCo5oWO5L2/55So77yB').decode('utf-8'))
    yf.opWeb('stop')

    makeOpDstRunLua(True)
    autoMakeConfig(True, False)

    elog = yf.getServerDir() + "/openresty/nginx/logs/error.log"
    if os.path.exists(elog):
        yf.removeDir(elog)

    yf.opWeb('start')
    return 'ok'

def reload_hook():
    s = status()
    if s == 'start':
        return reload()
    return 'ok'


def getJsonPath(name):
    path = getServerDir() + "/waf/" + name + ".json"
    return path


def getRuleJsonPath(name):
    path = getServerDir() + "/waf/rule/" + name + ".json"
    return path


# ------------------------------------------------------------
# 御风F2B防火墙（fail2ban）情报联动 —— 生产侧
# ------------------------------------------------------------
# 设计原则（弱耦合，保证任一侧缺失都能完美独立运行）：
#   1. 本插件是「情报生产方」：只负责把识别到的攻击 IP 追加写入 spool 文件；
#   2. **不依赖** fail2ban 的任何模块、端口、配置 —— 两侧唯一契约是 spool 文件格式；
#   3. spool 文件的存在性就是联动的唯一开关：
#        开启 → 创建 spool（fail2ban 据此下发 [op-waf] jail）
#        关闭 / 卸载 → 删除 spool（fail2ban 据此撤销 jail，零残留）
#   4. fail2ban 未安装时拒绝开启联动，绝不产生无人消费的垃圾文件。
F2B_NAME = 'fail2ban'
# 与 fail2ban 侧 OP_WAF_SPOOL_REL 严格一致 —— 这是两侧唯一需要对齐的常量
BAN_SPOOL_REL = 'logs/ban_spool.log'
# 单次通知对端的超时（秒）：避免对端异常时拖住面板请求
F2B_SYNC_TIMEOUT = 20


def f2bPluginDir():
    return yf.getPluginDir() + '/' + F2B_NAME


def f2bServerDir():
    return yf.getServerDir() + '/' + F2B_NAME


def f2bInstalled():
    """fail2ban 插件是否已安装：同时校验 server 目录与插件入口，避免半残状态误判"""
    try:
        return (os.path.isdir(f2bServerDir())
                and os.path.isfile(f2bPluginDir() + '/index.py'))
    except Exception:
        return False


def banSpoolPath():
    """情报 spool 的绝对路径（必须与 fail2ban 的 [op-waf] jail logpath 一致）"""
    return getServerDir() + '/' + BAN_SPOOL_REL


def readBanSyncConf():
    """读取 ban_sync 配置段（缺失时返回安全默认值，绝不抛异常）"""
    try:
        content = yf.readFile(getJsonPath('config'))
        cobj = json.loads(content) if content else {}
    except Exception:
        cobj = {}
    bs = cobj.get('ban_sync')
    if not isinstance(bs, dict):
        bs = {}
    return {'open': bool(bs.get('open'))}


def callFail2banSync():
    """
    通知 fail2ban 重新同步 [op-waf] jail。

    复用面板既有的插件调用约定（python3 <panelDir>/plugins/<name>/index.py <func>），
    进程隔离、无模块耦合；对端未安装或执行失败一律静默降级，
    绝不影响本插件自身的防护能力。
    """
    if not f2bInstalled():
        return (False, 'not_installed')
    try:
        entry = f2bPluginDir() + '/index.py'
        out, err = yf.execShell('python3 ' + entry + ' sync_op_waf_jail', timeout=F2B_SYNC_TIMEOUT)
        out = (out or '').strip()
        if not out:
            return (False, (err or 'empty response').strip()[:200])
        try:
            res = json.loads(out)
            return (bool(res.get('status')), res.get('msg', ''))
        except Exception:
            return (False, out[:200])
    except Exception as e:
        return (False, str(e)[:200])


def getBanSync():
    """联动配置与可用性（供 UI 展示，只读）"""
    try:
        conf = readBanSyncConf()
        spool = banSpoolPath()
        return yf.returnJson(True, 'ok!', {
            'open': conf['open'],
            'f2b_installed': f2bInstalled(),
            'spool': spool,
            'spool_exists': os.path.isfile(spool),
        })
    except Exception as e:
        return yf.returnJson(False, str(e))


def setBanSync():
    """
    开启 / 关闭「联动御风F2B防火墙持久封禁」。

    联动语义：本插件在应用层实时发现攻击 → 把攻击 IP 交给 fail2ban，
    由它在内核层以 iptables 全端口**持久**封禁（Nginx 重启也不失效）。
    这正是「op_waf 负责发现，fail2ban 负责持久封禁」的落地实现。
    """
    args = getArgs()
    data = checkArgs(args, ['open'])
    if not data[0]:
        return data[1]

    want_open = str(args.get('open')).strip().lower() in ('1', 'true', 'on', 'yes')

    # 先校验前置条件，避免写入「开了但没人消费」的状态
    if want_open and not f2bInstalled():
        return yf.returnJson(False, '未检测到「御风F2B防火墙」插件，请先安装后再开启联动。')

    conf_path = getJsonPath('config')
    try:
        content = yf.readFile(conf_path)
        cobj = json.loads(content) if content else {}
        if not isinstance(cobj, dict):
            cobj = {}
    except Exception:
        cobj = {}

    if not isinstance(cobj.get('ban_sync'), dict):
        cobj['ban_sync'] = {}
    cobj['ban_sync']['open'] = want_open
    yf.writeFile(conf_path, yf.getJson(cobj))

    # 1. 只重编 waf_config.lua（避免全量重编 nginx 配置），让 Lua 侧拿到新开关
    try:
        autoMakeLuaImportSingle('config', True)
    except Exception:
        pass

    # 2. 维护 spool 文件 —— 它是联动开关的唯一真实来源
    spool = banSpoolPath()
    if want_open:
        try:
            yf.makeDirs(os.path.dirname(spool))
            if not os.path.exists(spool):
                yf.writeFile(spool, '')
        except Exception as e:
            # 创建失败则回滚开关，保持两侧状态一致
            cobj['ban_sync']['open'] = False
            yf.writeFile(conf_path, yf.getJson(cobj))
            try:
                autoMakeLuaImportSingle('config', True)
            except Exception:
                pass
            # 详情写入面板日志，返回给前端的消息保持为可翻译的单一键
            try:
                yf.writeLog('OP防火墙', '创建情报文件失败: ' + str(e))
            except Exception:
                pass
            return yf.returnJson(False, '创建情报文件失败')
    else:
        try:
            if os.path.exists(spool):
                os.remove(spool)
        except Exception:
            pass

    # 3. 通知 fail2ban 重新同步 jail（幂等；对端异常不影响本插件开关本身）
    sync_ok, sync_msg = callFail2banSync()

    # 4. 平滑 reload，让 Lua 侧立即生效（reload 不掐断在线连接）
    try:
        yf.opWeb('reload')
    except Exception:
        pass

    # 返回消息必须是「可翻译的单一完整键」：拼接式文案在德/法/意下语义会破碎
    if not sync_ok and sync_msg != 'not_installed':
        msg = ('联动已开启（内核层同步失败，请检查御风F2B防火墙服务状态）' if want_open
               else '联动已关闭（内核层同步失败，请检查御风F2B防火墙服务状态）')
    else:
        msg = '联动已开启' if want_open else '联动已关闭'
    return yf.returnJson(True, msg, {'open': want_open, 'sync': sync_ok})


def getRule():
    args = getArgs()
    data = checkArgs(args, ['rule_name'])
    if not data[0]:
        return data[1]

    rule_name = args['rule_name']
    fpath = getRuleJsonPath(rule_name)
    content = yf.readFile(fpath)
    return yf.returnJson(True, 'ok', content)


def addRule():
    args = getArgs()
    data = checkArgs(args, ['ruleName', 'ruleValue', 'ps'])
    if not data[0]:
        return data[1]

    ruleValue = args['ruleValue']
    ruleName = args['ruleName']
    ps = args['ps']

    fpath = getRuleJsonPath(ruleName)
    content = yf.readFile(fpath)
    content = json.loads(content)

    tmp_k = []
    tmp_k.append(1)
    tmp_k.append(ruleValue)
    tmp_k.append(ps)
    tmp_k.append(1)

    content.append(tmp_k)

    cjson = yf.getJson(content)
    yf.writeFile(fpath, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!', content)


def removeRule():
    args = getArgs()
    data = checkArgs(args, ['ruleName', 'index'])
    if not data[0]:
        return data[1]

    index = int(args['index'])
    ruleName = args['ruleName']

    fpath = getRuleJsonPath(ruleName)
    content = yf.readFile(fpath)
    content = json.loads(content)

    k = content[index]
    content.remove(k)

    cjson = yf.getJson(content)
    yf.writeFile(fpath, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!', content)


def setRuleState():
    args = getArgs()
    data = checkArgs(args, ['ruleName', 'index'])
    if not data[0]:
        return data[1]

    index = int(args['index'])
    ruleName = args['ruleName']

    fpath = getRuleJsonPath(ruleName)
    content = yf.readFile(fpath)
    content = json.loads(content)

    b = content[index][0]
    if b == 1:
        content[index][0] = 0
    else:
        content[index][0] = 1

    cjson = yf.getJson(content)
    yf.writeFile(fpath, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!', content)


def modifyRule():
    args = getArgs()
    data = checkArgs(args, ['index', 'ruleName', 'ruleBody', 'rulePs'])
    if not data[0]:
        return data[1]

    index = int(args['index'])
    ruleName = args['ruleName']
    ruleBody = args['ruleBody']
    rulePs = args['rulePs']

    fpath = getRuleJsonPath(ruleName)
    content = yf.readFile(fpath)
    content = json.loads(content)

    tmp = content[index]

    tmp_k = []
    tmp_k.append(tmp[0])
    tmp_k.append(ruleBody)
    tmp_k.append(rulePs)
    tmp_k.append(tmp[3])

    content[index] = tmp_k

    cjson = yf.getJson(content)
    yf.writeFile(fpath, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!', content)


def getSiteRule():
    args = getArgs()
    data = checkArgs(args, ['siteName', 'ruleName'])
    if not data[0]:
        return data[1]

    siteName = args['siteName']
    siteRule = args['ruleName']

    path = getJsonPath('site')
    content = yf.readFile(path)
    content = json.loads(content)

    r = content[siteName][siteRule]

    cjson = yf.getJson(r)
    return yf.returnJson(True, 'ok!', cjson)


def addSiteRule():
    args = getArgs()
    data = checkArgs(args, ['siteName', 'ruleName', 'ruleValue'])
    if not data[0]:
        return data[1]

    siteName = args['siteName']
    siteRule = args['ruleName']
    ruleValue = args['ruleValue']

    path = getJsonPath('site')
    content = yf.readFile(path)
    content = json.loads(content)

    content[siteName][siteRule].append(ruleValue)

    cjson = yf.getJson(content)
    yf.writeFile(path, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!')


def addIpWhite():
    args = getArgs()
    data = checkArgs(args, ['start_ip', 'end_ip'])
    if not data[0]:
        return data[1]

    start_ip = args['start_ip']
    end_ip = args['end_ip']

    path = getRuleJsonPath('ip_white')
    content = yf.readFile(path)
    content = json.loads(content)

    data = []

    start_ip_list = start_ip.split('.')
    tmp = []
    for x in range(len(start_ip_list)):
        tmp.append(int(start_ip_list[x]))

    end_ip_list = end_ip.split('.')
    tmp2 = []
    for x in range(len(end_ip_list)):
        tmp2.append(int(end_ip_list[x]))

    data.append(tmp)
    data.append(tmp2)

    if data in content:
        return yf.returnJson(False, '该 IP 段已存在白名单中!')

    content.append(data)

    cjson = yf.getJson(content)
    yf.writeFile(path, cjson)
    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!')


def removeIpWhite():
    args = getArgs()
    data = checkArgs(args, ['index'])
    if not data[0]:
        return data[1]

    index = args['index']

    path = getRuleJsonPath('ip_white')
    content = yf.readFile(path)
    content = json.loads(content)

    k = content[int(index)]
    content.remove(k)

    cjson = yf.getJson(content)
    yf.writeFile(path, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!')


def addIpBlack():
    args = getArgs()
    data = checkArgs(args, ['start_ip', 'end_ip'])
    if not data[0]:
        return data[1]

    start_ip = args['start_ip']
    end_ip = args['end_ip']

    path = getRuleJsonPath('ip_black')
    content = yf.readFile(path)
    content = json.loads(content)

    data = []

    start_ip_list = start_ip.split('.')
    tmp = []
    for x in range(len(start_ip_list)):
        tmp.append(int(start_ip_list[x]))

    end_ip_list = end_ip.split('.')
    tmp2 = []
    for x in range(len(end_ip_list)):
        tmp2.append(int(end_ip_list[x]))

    data.append(tmp)
    data.append(tmp2)

    if data in content:
        return yf.returnJson(False, '该 IP 段已存在黑名单中!')

    content.append(data)

    cjson = yf.getJson(content)
    yf.writeFile(path, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!')


def removeIpBlack():
    args = getArgs()
    data = checkArgs(args, ['index'])
    if not data[0]:
        return data[1]

    index = args['index']

    path = getRuleJsonPath('ip_black')
    content = yf.readFile(path)
    content = json.loads(content)

    k = content[int(index)]
    content.remove(k)

    cjson = yf.getJson(content)
    yf.writeFile(path, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!')


def setIpv6Black():
    args = getArgs()
    data = checkArgs(args, ['addr'])
    if not data[0]:
        return data[1]

    addr = args['addr'].replace('_', ':')
    path = getRuleJsonPath('ipv6_black')

    content = yf.readFile(path)
    content = json.loads(content)
    content.append(addr)

    cjson = yf.getJson(content)
    yf.writeFile(path, cjson)
    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!')


def delIpv6Black():
    args = getArgs()
    data = checkArgs(args, ['addr'])
    if not data[0]:
        return data[1]

    addr = args['addr'].replace('_', ':')
    path = getRuleJsonPath('ipv6_black')

    content = yf.readFile(path)
    content = json.loads(content)

    content.remove(addr)
    cjson = yf.getJson(content)
    yf.writeFile(path, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!')


def removeSiteRule():
    args = getArgs()
    data = checkArgs(args, ['siteName', 'ruleName', 'index'])
    if not data[0]:
        return data[1]

    siteName = args['siteName']
    siteRule = args['ruleName']
    index = args['index']

    path = getJsonPath('site')
    content = yf.readFile(path)
    content = json.loads(content)

    ruleValue = content[siteName][siteRule][int(index)]
    content[siteName][siteRule].remove(ruleValue)

    cjson = yf.getJson(content)
    yf.writeFile(path, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!')


def setObjStatus():
    args = getArgs()
    data = checkArgs(args, ['obj', 'statusCode'])
    if not data[0]:
        return data[1]

    conf = getJsonPath('config')
    content = yf.readFile(conf)
    cobj = json.loads(content)

    o = args['obj']
    status = int(args['statusCode'])
    cobj[o]['status'] = status

    cjson = yf.getJson(cobj)
    yf.writeFile(conf, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!')


def setRetry():
    args = getArgs()
    data = checkArgs(args, ['retry', 'retry_time',
                            'retry_cycle', 'is_open_global'])
    if not data[0]:
        return data[1]

    conf = getJsonPath('config')
    content = yf.readFile(conf)
    cobj = json.loads(content)
    
    ## 修复数据类型错误
    tmp = args
    tmp['retry'] = int(tmp['retry'])
    tmp['retry_time'] = int(tmp['retry_time'])
    tmp['retry_cycle'] = int(tmp['retry_cycle'])
    
    cobj['retry'] = tmp
    cjson = yf.getJson(cobj)
    yf.writeFile(conf, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!', [])


def setSafeVerify():
    args = getArgs()
    data = checkArgs(args, ['auto', 'time', 'cpu', 'mode'])
    if not data[0]:
        return data[1]

    conf = getJsonPath('config')
    content = yf.readFile(conf)
    cobj = json.loads(content)

    cobj['safe_verify']['time'] = args['time']
    cobj['safe_verify']['cpu'] = int(args['cpu'])
    cobj['safe_verify']['mode'] = args['mode']

    if args['auto'] == '0':
        cobj['safe_verify']['auto'] = False
    else:
        cobj['safe_verify']['auto'] = True

    cjson = yf.getJson(cobj)
    yf.writeFile(conf, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!', [])


def setSiteRetry():
    return yf.returnJson(True, '设置成功-?!', [])


def setCcConf():
    args = getArgs()
    data = checkArgs(args, ['siteName', 'cycle', 'limit',
                            'endtime', 'is_open_global'])
    if not data[0]:
        return data[1]

    conf = getJsonPath('config')
    content = yf.readFile(conf)
    cobj = json.loads(content)

    tmp = cobj['cc']

    tmp['cycle'] = int(args['cycle'])
    tmp['limit'] = int(args['limit'])
    tmp['endtime'] = int(args['endtime'])
    tmp['is_open_global'] = args['is_open_global']
    tmp['increase'] = args['increase']
    cobj['cc'] = tmp

    cjson = yf.getJson(cobj)
    yf.writeFile(conf, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!', [])


def setSiteCcConf():
    return yf.returnJson(False, '暂未开发!', [])


def saveScanRule():
    args = getArgs()
    data = checkArgs(args, ['header', 'cookie', 'args'])
    if not data[0]:
        return data[1]

    path = getRuleJsonPath('scan_black')
    cjson = yf.getJson(args)
    yf.writeFile(path, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!', [])


def getSiteConfig():
    path = getJsonPath('site')
    content = yf.readFile(path)

    content = json.loads(content)

    total = getJsonPath('total')
    total_content = yf.readFile(total)
    total_content = json.loads(total_content)

    # print total_content

    for x in content:
        tmp = []
        tmp_v = {}
        if 'sites' in total_content and x in total_content['sites']:
            tmp_v = total_content['sites'][x]

        # 正确映射前端 v.total 索引顺序，并解决 kx in tmp_v 的整型对比 Bug
        key_list = ['post', 'get', 'cc', 'user-agent', 'cookie', 'cdn', 'curl_protection']
        for kx in range(len(key_list)):
            ktmp = {}
            k_name = key_list[kx]
            if k_name == 'user-agent':
                k_name = 'user_agent'
            
            # 由于 curl 的拦截统计在 lua 中归于 user_agent，此列也可以选用此拦截数或独立输出
            if k_name == 'curl_protection':
                k_name = 'user_agent'

            if k_name in tmp_v:
                ktmp['value'] = tmp_v[k_name]
            else:
                ktmp['value'] = 0
            ktmp['key'] = key_list[kx]
            tmp.append(ktmp)

        # print tmp
        content[x]['total'] = tmp

    content = yf.getJson(content)
    return yf.returnJson(True, 'ok!', content)


def getSiteConfigByName():
    args = getArgs()
    data = checkArgs(args, ['siteName'])
    if not data[0]:
        return data[1]
    path = getJsonPath('site')
    content = yf.readFile(path)
    content = json.loads(content)

    siteName = args['siteName']
    retData = {}
    if siteName in content:
        # 平滑迁移与兼容已存在的 allow_curl 字段
        if 'curl_protection' not in content[siteName]:
            if 'allow_curl' in content[siteName]:
                content[siteName]['curl_protection'] = not content[siteName]['allow_curl']
                del content[siteName]['allow_curl']
            else:
                content[siteName]['curl_protection'] = True
            cjson = yf.getJson(content)
            yf.writeFile(path, cjson)
        if 'allow_curl' in content[siteName]:
            del content[siteName]['allow_curl']
            cjson = yf.getJson(content)
            yf.writeFile(path, cjson)
        retData = content[siteName]

    return yf.returnJson(True, 'ok!', retData)


def addSiteCdnHeader():
    args = getArgs()
    data = checkArgs(args, ['siteName', 'cdn_header'])
    if not data[0]:
        return data[1]
    path = getJsonPath('site')
    content = yf.readFile(path)
    content = json.loads(content)

    siteName = args['siteName']
    retData = {}
    if siteName in content:
        content[siteName]['cdn_header'].append(args['cdn_header'])

    cjson = yf.getJson(content)
    yf.writeFile(path, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '添加成功!')


def removeSiteCdnHeader():
    args = getArgs()
    data = checkArgs(args, ['siteName', 'cdn_header'])
    if not data[0]:
        return data[1]
    path = getJsonPath('site')
    content = yf.readFile(path)
    content = json.loads(content)

    siteName = args['siteName']
    retData = {}
    if siteName in content:
        content[siteName]['cdn_header'].remove(args['cdn_header'])

    cjson = yf.getJson(content)
    yf.writeFile(path, cjson)

    setConfRestartWeb()
    return yf.returnJson(True, '删除成功!')


def outputData():
    args = getArgs()
    data = checkArgs(args, ['sname'])
    if not data[0]:
        return data[1]

    path = getRuleJsonPath(args['sname'])
    content = yf.readFile(path)
    return yf.returnJson(True, 'ok', content)


def importData():
    args = getArgs()
    data = checkArgs(args, ['sname', 'pdata'])
    if not data[0]:
        return data[1]

    path = getRuleJsonPath(args['sname'])

    source_data = yf.readFile(path)
    source_data = json.loads(source_data)

    save_data = []
    save_data.append(source_data[0])
    pdata = args['pdata'].strip()
    try:
        pdata = json.loads(pdata)
        yf.writeFile(path, json.dumps(pdata))
    except Exception as e:
        pdata = pdata.split("\\n")
        for x in pdata:
            pval = x.strip()
            if pval != "":
                vv = json.loads(pval)
                save_data.append(vv[0])
        yf.writeFile(path, json.dumps(save_data))
    # restartWeb()
    return yf.returnJson(True, '设置成功!')


def getLogsList():
    args = getArgs()
    data = checkArgs(args, ['site', 'page', 'page_size', 'tojs'])
    if not data[0]:
        return data[1]

    page = int(args['page'])
    page_size = int(args['page_size'])
    domain = args['site']
    tojs = args['tojs']

    setDefaultSite(domain)

    conn = pSqliteDb('logs')

    field = 'time,ip,domain,server_name,method,uri,user_agent,rule_name,reason'
    limit = str(page_size) + ' offset ' + str(page_size * (page - 1))

    condition = ''
    conn = conn.field(field)
    conn = conn.where("1=1", ())
    if domain != 'ALL':
        conn = conn.where("domain=?", (domain,))

    clist = conn.limit(limit).order('time desc').inquiry()
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

    return yf.returnJson(True, 'ok!', data)


def getSafeLogs():
    args = getArgs()
    data = checkArgs(args, ['siteName', 'toDate', 'p'])
    if not data[0]:
        return data[1]

    site_name = str(args['siteName']).strip()
    to_date = str(args['toDate']).strip()
    # 严格校验参数，防止路径穿越攻击
    if not re.match(r'^[a-zA-Z0-9_\.\-]+$', site_name) or '..' in site_name or '/' in site_name or '\\' in site_name:
        return yf.returnJson(False, "站点名称包含非法字符!")
    if not re.match(r'^[0-9_\-]+$', to_date):
        return yf.returnJson(False, "日期参数格式错误!")

    path = getServerDir() + '/logs'
    log_file = os.path.abspath(path + '/' + site_name + '_' + to_date + '.log')
    if not log_file.startswith(os.path.abspath(path)):
        return yf.returnJson(False, "非法访问路径!")

    if not os.path.exists(log_file):
        return yf.returnJson(False, "文件不存在!")

    retData = []
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    retData.append(json.loads(line))
                except Exception:
                    pass
                if len(retData) >= 5000:
                    break
    except Exception as e:
        return yf.returnJson(False, "读取日志失败: " + str(e))

    return yf.returnJson(True, '获取成功!', retData)


def setObjOpen():
    args = getArgs()
    data = checkArgs(args, ['obj'])
    if not data[0]:
        return data[1]

    conf = getJsonPath('config')
    content = yf.readFile(conf)
    cobj = json.loads(content)

    o = args['obj']
    if cobj[o]["open"]:
        cobj[o]["open"] = False
    else:
        cobj[o]["open"] = True

    cjson = yf.getJson(cobj)
    yf.writeFile(conf, cjson)
    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!')


def setSiteObjOpen():
    args = getArgs()
    data = checkArgs(args, ['siteName', 'obj'])
    if not data[0]:
        return data[1]

    siteName = args['siteName']
    obj = args['obj']

    path = getJsonPath('site')
    content = yf.readFile(path)
    content = json.loads(content)

    if obj not in content[siteName]:
        content[siteName][obj] = True
    elif type(content[siteName][obj]) == bool:
        if content[siteName][obj]:
            content[siteName][obj] = False
        else:
            content[siteName][obj] = True
    else:
        if content[siteName][obj]['open']:
            content[siteName][obj]['open'] = False
        else:
            content[siteName][obj]['open'] = True

    cjson = yf.getJson(content)
    yf.writeFile(path, cjson)
    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!')


def getWafSrceen():
    conf = getJsonPath('total')
    return yf.readFile(conf)


def getTotalStatistics():
    data = {}
    isInstall = os.path.exists(getServerDir() + '/waf/total.json')
    if isInstall:
        try:
            content = yf.readFile(getServerDir() + '/waf/total.json')
            total_data = json.loads(content)
            total = total_data.get('total', 0)
            today_total = 0
            
            today_str = time.strftime('%Y-%m-%d', time.localtime())
            if total_data.get('today_date') == today_str:
                today_total = total_data.get('today_total', 0)
                
            data['status'] = True
            data['count'] = f"{today_total}/{total}"
            
            info_path = getPluginDir() + '/info.json'
            info_data = json.loads(yf.readFile(info_path))
            data['ver'] = info_data['versions'][0]
            return yf.returnJson(True, 'ok', data)
        except Exception as e:
            pass
            
    data['status'] = False
    data['count'] = '0/0'
    return yf.returnJson(False, 'fail', data)


def getWafConf():
    conf = getJsonPath('config')
    raw = yf.readFile(conf)
    try:
        cobj = json.loads(raw) if raw else {}
    except Exception:
        cobj = {}
    if not isinstance(cobj, dict):
        cobj = {}
    # 注入运行时只读信息（不落盘）：供 UI 判断联动开关是否可开启
    try:
        cobj['f2b_installed'] = f2bInstalled()
    except Exception:
        cobj['f2b_installed'] = False
    return yf.getJson(cobj)


def areaLimitSwitch():
    args = getArgs()
    data = checkArgs(args, ['area_limit'])
    if not data[0]:
        return data[1]

    path_config = getJsonPath('config')

    config_contents = yf.readFile(path_config)
    config_contents = json.loads(config_contents)

    msg = '关闭成功!'
    if args['area_limit'] == 'on':
        msg = '开启成功!'
        config_contents['area_limit'] = True
    else:
        config_contents['area_limit'] = False

    yf.writeFile(path_config, json.dumps(config_contents))

    autoMakeConfig(True, True)
    restart()
    return yf.returnJson(True, msg)


def getAreaLimit():
    conf = getJsonPath('area_limit')
    if not os.path.exists(conf):
        yf.writeFile(conf, '[]')

    d = yf.readFile(conf)
    data = json.loads(d)
    return yf.returnJson(True, 'ok!', data)


def delAreaLimit():
    args = getArgs()
    data = checkArgs(args, ['site', 'types', 'region'])
    if not data[0]:
        return data[1]

    type_list = ["refuse", "accept"]
    if not args['types'] in type_list:
        return yf.returnJson(False, '输入的类型错误!')

    region_l = args['region'].split(",")
    site_l = args['site'].split(",")

    paramMode = {}
    for i in region_l:
        if not i:
            continue
        i = i.strip()
        if not i in paramMode:
            paramMode[i] = "1"

    sitesMode = {}
    for i in site_l:
        i = i.strip()
        if not i:
            continue

        if not i in sitesMode:
            sitesMode[i] = "1"

    if len(paramMode) == 0:
        return yf.returnJson(False, '输入的请求类型错误!')
    if len(sitesMode) == 0:
        return yf.returnJson(False, '输入的站点错误!')

    conf = getJsonPath('area_limit')
    t_data = json.loads(yf.readFile(conf))

    data = {"site": sitesMode, "types": args['types'], "region": paramMode}
    if not data in t_data:
        return yf.returnJson(False, '不存在!')

    t_data.remove(data)
    yf.writeFile(conf, json.dumps(t_data))

    setConfRestartWeb()
    return yf.returnJson(True, '删除成功!')


def addAreaLimit():
    args = getArgs()
    data = checkArgs(args, ['site', 'types', 'region'])
    if not data[0]:
        return data[1]

    type_list = ["refuse", "accept"]
    if not args['types'] in type_list:
        return yf.returnJson(False, '输入的类型错误!')

    region_l = args['region'].split(",")
    site_l = args['site'].split(",")

    paramMode = {}
    for i in region_l:
        if not i:
            continue
        i = i.strip()
        if not i in paramMode:
            paramMode[i] = "1"

    if '海外' in paramMode and '中国' in paramMode:
        return yf.returnJson(False, '不允许设置【中国大陆】和【中国大陆以外地区】一同开启地区限制!')

    sitesMode = {}
    for i in site_l:
        i = i.strip()
        if not i:
            continue

        if not i in sitesMode:
            sitesMode[i] = "1"

    if len(paramMode) == 0:
        return yf.returnJson(False, '输入的请求类型错误!')
    if len(sitesMode) == 0:
        return yf.returnJson(False, '输入的站点错误!')

    conf = getJsonPath('area_limit')
    t_data = json.loads(yf.readFile(conf))

    data = {"site": sitesMode, "types": args['types'], "region": paramMode}
    if data in t_data:
        return yf.returnJson(False, '已存在!')

    t_data.insert(0, data)
    yf.writeFile(conf, json.dumps(t_data))

    setConfRestartWeb()
    return yf.returnJson(True, '添加成功!')


def cleanDropIp():
    url = "http://127.0.0.1/clean_waf_drop_ip"
    data = yf.httpGet(url)
    return yf.returnJson(True, 'ok!', data)


def getDropIpList():
    url = "http://127.0.0.1/get_waf_drop_ip"
    try:
        data = yf.httpGet(url)
        res = json.loads(data)
        if res['status'] == 0:
            return yf.returnJson(True, 'ok!', res['msg'])
        return yf.returnJson(False, 'Failed to fetch', [])
    except Exception as e:
        return yf.returnJson(False, str(e), [])

def get_location_from_pconline(ip):
    try:
        import urllib.request
        import json
        url = 'https://whois.pconline.com.cn/ipJson.jsp?ip=' + ip + '&json=true'
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
        with urllib.request.urlopen(req, timeout=3) as response:
            content = response.read()
            try:
                text = content.decode('gbk')
            except Exception:
                text = content.decode('utf-8', errors='ignore')
            data = json.loads(text)
            if data and 'addr' in data:
                country = "中国"
                pro = data.get('pro', '')
                city = data.get('city', '')
                proCode = data.get('proCode', '')
                regionName = pro
                
                if proCode == '999999' or (not pro and not city):
                    country = "海外/未知"
                    regionName = ""
                    city = ""
                else:
                    # 特殊海外或港澳台地区判定
                    overseas = ["澳大利亚", "美国", "日本", "韩国", "新加坡", "德国", "法国", "英国", "加拿大", "香港", "澳门", "台湾", "荷兰", "俄罗斯"]
                    for area in overseas:
                        if area in pro:
                            country = area
                            regionName = ""
                            city = ""
                            break
                
                org = ""
                addr = data.get('addr', '')
                if addr:
                    parts = addr.split()
                    if len(parts) > 1:
                        org = parts[-1]
                
                return {
                    "status": "success",
                    "country": country,
                    "regionName": regionName,
                    "city": city,
                    "org": org,
                    "query": ip
                }
    except Exception:
        pass
    return {
        "status": "fail",
        "query": ip
    }

# ------------------------------------------------------------
# IP 归属地查询：语言策略
# ------------------------------------------------------------
# 与 fail2ban 插件的 IP_API_LANG_MAP 保持一致，避免同一 IP
# 在 F2B 里显示 "Berlin, Germany"、在 OP 防火墙里却显示中文地名。
# ip-api 不支持 zh-TW，回落到 zh-CN。
IP_API_LANG_MAP = {
    'zh-CN': 'zh-CN',
    'zh-TW': 'zh-CN',
    'en': 'en',
    'de': 'de',
    'fr': 'fr',
    'it': 'it',
}


def normalize_ip_api_lang(lang):
    """把面板语言归一化为 ip-api 支持的语言；未显式传入时跟随面板当前语言"""
    lang = (lang or '').strip()
    if lang in IP_API_LANG_MAP:
        return IP_API_LANG_MAP[lang]
    try:
        current = (yf.getLanguage() or '').strip() if hasattr(yf, 'getLanguage') else ''
    except Exception:
        current = ''
    return IP_API_LANG_MAP.get(current, 'zh-CN')


def getIpLocationBatch():
    args = getArgs()
    data = checkArgs(args, ['ips'])
    if not data[0]:
        return data[1]
    
    ips_json = args['ips']
    api_lang = normalize_ip_api_lang(args.get('lang', ''))
    try:
        import urllib.request
        ips = json.loads(ips_json)
        if not isinstance(ips, list):
            return yf.returnJson(False, 'ips must be a JSON array', [])
        
        import urllib.request
        import time
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request('http://ip-api.com/batch?lang=' + api_lang)
                req.add_header('Content-Type', 'application/json')
                response = urllib.request.urlopen(req, data=ips_json.encode('utf-8'), timeout=10)
                result = response.read().decode('utf-8')
                return yf.returnJson(True, 'ok!', json.loads(result))
            except Exception as e:
                if attempt == max_retries - 1:
                    result_list = [{"query": ip, "status": "fail"} for ip in ips]
                    return yf.returnJson(True, 'ok!', result_list)
                time.sleep(0.5)
    except Exception as e:
        return yf.returnJson(False, str(e), [])

def getIpLocation():
    args = getArgs()
    data = checkArgs(args, ['ip'])
    if not data[0]:
        return data[1]
    
    ip = args['ip']
    api_lang = normalize_ip_api_lang(args.get('lang', ''))
    try:
        import urllib.request
        import time
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                url = 'http://ip-api.com/json/' + ip + '?lang=' + api_lang
                response = urllib.request.urlopen(url, timeout=10)
                result = response.read().decode('utf-8')
                res_data = json.loads(result)
                if res_data.get('status') == 'success':
                    return yf.returnJson(True, 'ok!', res_data)
                raise Exception("ip-api failed")
            except Exception as e:
                if attempt == max_retries - 1:
                    return yf.returnJson(False, '获取归属地失败', [])
                time.sleep(0.5)
    except Exception as e:
        return yf.returnJson(False, str(e), [])
def removeDropIp():
    args = getArgs()
    data = checkArgs(args, ['ip'])
    if not data[0]:
        return data[1]
    ip = str(args['ip']).strip()
    # silent 用于打断与 fail2ban 侧的双向递归调用链（对方解封时回调本接口）
    silent = str(args.get('silent', '')).strip().lower() in ('1', 'true', 'on', 'yes')

    url = "http://127.0.0.1/remove_waf_drop_ip?ip=" + ip
    try:
        res_data = yf.httpGet(url)
        res = json.loads(res_data)
        if res['status'] != 0:
            return yf.returnJson(False, res.get('msg', '释放失败'))
    except Exception as e:
        return yf.returnJson(False, str(e))

    # ---- 单点解封：应用层解封时同步解除 fail2ban 的内核层封禁 ----
    # 否则会出现「在 op_waf 点了释放，IP 却仍被 iptables 全端口封禁」的困惑。
    f2b_synced = False
    if not silent and readBanSyncConf()['open'] and f2bInstalled():
        try:
            entry = f2bPluginDir() + '/index.py'
            out, _err = yf.execShell(
                'python3 ' + entry + ' unban_op_waf_ip '
                + json.dumps({'ip': ip, 'silent': '1'}),
                timeout=F2B_SYNC_TIMEOUT)
            if out and json.loads(out.strip()).get('status'):
                f2b_synced = True
        except Exception:
            f2b_synced = False

    return yf.returnJson(True, '释放成功!', {'f2b_synced': f2b_synced})


def getDropIpLogs():
    args = getArgs()
    data = checkArgs(args, ['ip'])
    if not data[0]:
        return data[1]
    ip = args['ip']
    
    conn = pSqliteDb('logs')
    field = 'time,ip,domain,server_name,method,uri,user_agent,rule_name,reason'
    limit = '50'
    
    conn = conn.field(field)
    conn = conn.where("ip=?", (ip,))
    conn = conn.order('time desc')
    
    logs = conn.limit(limit).select()
    
    # Format to JS readable time
    for log in logs:
        try:
            log['time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(log['time']))
        except Exception:
            pass
            
    return yf.returnJson(True, 'ok!', logs)


def addTrustedProxy():
    args = getArgs()
    data = checkArgs(args, ['ip'])
    if not data[0]:
        return data[1]
    
    conf = getJsonPath('config')
    content = yf.readFile(conf)
    cobj = json.loads(content)
    
    if "trusted_proxy" not in cobj:
        cobj["trusted_proxy"] = []
    
    if args['ip'] not in cobj["trusted_proxy"]:
        cobj["trusted_proxy"].append(args['ip'])
        
    cjson = yf.getJson(cobj)
    yf.writeFile(conf, cjson)
    setConfRestartWeb()
    return yf.returnJson(True, '添加成功!')


def removeTrustedProxy():
    args = getArgs()
    data = checkArgs(args, ['index'])
    if not data[0]:
        return data[1]
    
    index = int(args['index'])
    conf = getJsonPath('config')
    content = yf.readFile(conf)
    cobj = json.loads(content)
    
    if "trusted_proxy" in cobj and index < len(cobj["trusted_proxy"]):
        cobj["trusted_proxy"].pop(index)
        cjson = yf.getJson(cobj)
        yf.writeFile(conf, cjson)
        setConfRestartWeb()
        return yf.returnJson(True, '删除成功!')
    return yf.returnJson(False, '删除失败!')


def setHoneypotPaths():
    args = getArgs()
    data = checkArgs(args, ['paths'])
    if not data[0]:
        return data[1]

    conf = getJsonPath('config')
    content = yf.readFile(conf)
    cobj = json.loads(content)

    paths = args['paths']
    if type(paths) == str:
        paths = json.loads(paths)

    if 'honeypot' not in cobj:
        cobj['honeypot'] = {
            "status": 444,
            "ps": "自动蜜罐防护，拦截自动扫描器和嗅探脚本",
            "open": True,
            "paths": []
        }

    cobj['honeypot']['paths'] = paths
    yf.writeFile(conf, json.dumps(cobj))
    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!')


def getSpiderConf():
    conf_path = getJsonPath('config')
    rule_path = getRuleJsonPath('spider_ip')
    if not os.path.exists(rule_path):
        plugin_rule_path = getPluginDir() + "/waf/rule/spider_ip.json"
        if os.path.exists(plugin_rule_path):
            rule_path = plugin_rule_path

    spider_conf = {
        'open': True,
        'mode': 'downgrade',
        'status': 444,
        'ps': '智能蜘蛛识别与伪造拦截'
    }
    if os.path.exists(conf_path):
        try:
            cobj = json.loads(yf.readFile(conf_path))
            if 'spider' in cobj:
                spider_conf.update(cobj['spider'])
        except Exception:
            pass

    ip_list = []
    if os.path.exists(rule_path):
        try:
            ip_list = json.loads(yf.readFile(rule_path))
        except Exception:
            pass

    engine_stats = {
        'baidu': 0,
        'google': 0,
        'bing': 0,
        'bytedance': 0,
        'huawei': 0,
        'sogou': 0,
        '360': 0,
        'shenma': 0,
        'yandex': 0,
        'custom': 0,
        'total': len(ip_list)
    }
    for item in ip_list:
        ps = item[1] if len(item) > 1 else ''
        if '百度' in ps:
            engine_stats['baidu'] += 1
        elif '谷歌' in ps:
            engine_stats['google'] += 1
        elif '必应' in ps:
            engine_stats['bing'] += 1
        elif '字节' in ps:
            engine_stats['bytedance'] += 1
        elif '华为' in ps:
            engine_stats['huawei'] += 1
        elif '搜狗' in ps:
            engine_stats['sogou'] += 1
        elif '360' in ps:
            engine_stats['360'] += 1
        elif '神马' in ps:
            engine_stats['shenma'] += 1
        elif 'Yandex' in ps or 'yandex' in ps:
            engine_stats['yandex'] += 1
        else:
            engine_stats['custom'] += 1

    return yf.returnJson(True, 'ok', {
        'config': spider_conf,
        'stats': engine_stats,
        'total_rules': len(ip_list)
    })


def setSpiderMode():
    args = getArgs()
    data = checkArgs(args, ['mode'])
    if not data[0]:
        return data[1]
    mode = args['mode'].strip().lower()
    if mode not in ['downgrade', 'block']:
        return yf.returnJson(False, '模式不支持，仅支持 downgrade 或 block')

    conf = getJsonPath('config')
    if not os.path.exists(conf):
        src_conf = getPluginDir() + '/waf/config.json'
        if os.path.exists(src_conf):
            yf.makeDirs(os.path.dirname(conf))
            yf.writeFile(conf, yf.readFile(src_conf))
    content = yf.readFile(conf)
    if type(content) == bool or not content:
        content = '{}'
    cobj = json.loads(content)
    if 'spider' not in cobj:
        cobj['spider'] = {
            "open": True,
            "mode": "downgrade",
            "status": 444,
            "ps": "智能蜘蛛识别与伪造拦截"
        }
    cobj['spider']['mode'] = mode
    yf.writeFile(conf, json.dumps(cobj))
    setConfRestartWeb()
    return yf.returnJson(True, '设置成功!')


def getSpiderIpList():
    rule_path = getRuleJsonPath('spider_ip')
    if not os.path.exists(rule_path):
        plugin_rule_path = getPluginDir() + "/waf/rule/spider_ip.json"
        if os.path.exists(plugin_rule_path):
            rule_path = plugin_rule_path
    ip_list = []
    if os.path.exists(rule_path):
        try:
            content = yf.readFile(rule_path)
            if type(content) != bool and content:
                ip_list = json.loads(content)
        except Exception:
            pass
    return yf.returnJson(True, 'ok', ip_list)


def addSpiderIp():
    args = getArgs()
    data = checkArgs(args, ['ip', 'ps'])
    if not data[0]:
        return data[1]
    ip = args['ip'].strip()
    ps = args['ps'].strip() or '自定义蜘蛛'

    rule_path = getRuleJsonPath('spider_ip')
    if not os.path.exists(rule_path):
        plugin_rule_path = getPluginDir() + "/waf/rule/spider_ip.json"
        if os.path.exists(plugin_rule_path):
            yf.makeDirs(os.path.dirname(rule_path))
            yf.writeFile(rule_path, yf.readFile(plugin_rule_path))
    ip_list = []
    if os.path.exists(rule_path):
        try:
            content = yf.readFile(rule_path)
            if type(content) != bool and content:
                ip_list = json.loads(content)
        except Exception:
            pass

    for item in ip_list:
        if item[0] == ip:
            return yf.returnJson(False, '该 IP/网段 已存在!')

    ip_list.append([ip, ps])
    yf.makeDirs(os.path.dirname(rule_path))
    yf.writeFile(rule_path, json.dumps(ip_list))
    autoMakeLuaConfSingle('spider_ip', True)
    setConfRestartWeb()
    return yf.returnJson(True, '添加成功!')


def removeSpiderIp():
    args = getArgs()
    data = checkArgs(args, ['index'])
    if not data[0]:
        return data[1]
    index = int(args['index'])
    rule_path = getRuleJsonPath('spider_ip')
    if not os.path.exists(rule_path):
        return yf.returnJson(False, '规则文件不存在!')
    try:
        content = yf.readFile(rule_path)
        if type(content) == bool or not content:
            return yf.returnJson(False, '规则文件为空!')
        ip_list = json.loads(content)
        if 0 <= index < len(ip_list):
            ip_list.pop(index)
            yf.writeFile(rule_path, json.dumps(ip_list))
            autoMakeLuaConfSingle('spider_ip', True)
            setConfRestartWeb()
            return yf.returnJson(True, '删除成功!')
    except Exception as e:
        return yf.returnJson(False, '删除失败: ' + str(e))
    return yf.returnJson(False, '指定的索引不存在!')


def syncSpiderIp():
    src_file = getPluginDir() + "/waf/rule/spider_ip.json"
    dst_file = getServerDir() + "/waf/rule/spider_ip.json"
    if os.path.exists(src_file):
        content = yf.readFile(src_file)
        custom_rules = []
        if os.path.exists(dst_file):
            try:
                curr_content = yf.readFile(dst_file)
                if type(curr_content) != bool and curr_content:
                    curr_rules = json.loads(curr_content)
                    for r in curr_rules:
                        ps = r[1] if len(r) > 1 else ''
                        if '自定义' in ps or ps == '':
                            custom_rules.append(r)
            except Exception:
                pass

        base_rules = json.loads(content)
        existing_ips = {r[0] for r in base_rules}
        for cr in custom_rules:
            if cr[0] not in existing_ips:
                base_rules.append(cr)
                existing_ips.add(cr[0])

        yf.makeDirs(os.path.dirname(dst_file))
        yf.writeFile(dst_file, json.dumps(base_rules))
        autoMakeLuaConfSingle('spider_ip', True)
        setConfRestartWeb()
        return yf.returnJson(True, '同步成功，当前共 ' + str(len(base_rules)) + ' 条权威蜘蛛规则（已保留自定义规则）!')
    return yf.returnJson(False, '内置规则文件不存在!')


def testRun():
    # args = getArgs()
    # data = checkArgs(args, ['siteName'])
    # if not data[0]:
    #     return data[1]

    default_path = getServerDir() + "/waf/default.pl"
    default_site = yf.readFile(default_path)
    if default_site:
        default_site = default_site.strip()
    else:
        default_site = 'ALL'
    url = "http://" + default_site + '/?t=../etc/passwd'
    returnData = yf.httpGet(url, 10)

    # url = "https://" + default_site + '/?t=../etc/passwd'
    # returnData = yf.httpGet(url, 3)
    return yf.returnJson(True, '测试运行成功!', returnData)


def installPreInspection():
    check_op = yf.getServerDir() + "/openresty"
    if not os.path.exists(check_op):
        return "请先安装OpenResty"
    return 'ok'


if __name__ == "__main__":
    func = sys.argv[1]
    if func not in ['status', 'install_pre_inspection']:
        if not hasattr(yf, 'isYufengPanel') or not yf.isYufengPanel():
            print(yf.returnJson(False, __import__('base64').b64decode('5oKo55qE6Z2i5p2/546v5aKD5LiN5Yy56YWN77yM6K+36LCo5oWO5L2/55So77yB').decode('utf-8')))
            sys.exit(0)
    elif func == 'install_pre_inspection':
        if not hasattr(yf, 'isYufengPanel') or not yf.isYufengPanel():
            print(__import__('base64').b64decode('5oKo55qE6Z2i5p2/546v5aKD5LiN5Yy56YWN77yM6K+36LCo5oWO5L2/55So77yB').decode('utf-8'))
            sys.exit(0)
            
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
    elif func == 'get_rule':
        print(getRule())
    elif func == 'add_rule':
        print(addRule())
    elif func == 'remove_rule':
        print(removeRule())
    elif func == 'set_rule_state':
        print(setRuleState())
    elif func == 'modify_rule':
        print(modifyRule())
    elif func == 'get_site_rule':
        print(getSiteRule())
    elif func == 'add_site_rule':
        print(addSiteRule())
    elif func == 'add_ip_white':
        print(addIpWhite())
    elif func == 'remove_ip_white':
        print(removeIpWhite())
    elif func == 'add_ip_black':
        print(addIpBlack())
    elif func == 'remove_ip_black':
        print(removeIpBlack())
    elif func == 'set_ipv6_black':
        print(setIpv6Black())
    elif func == 'del_ipv6_black':
        print(delIpv6Black())
    elif func == 'remove_site_rule':
        print(removeSiteRule())
    elif func == 'set_obj_status':
        print(setObjStatus())
    elif func == 'set_obj_open':
        print(setObjOpen())
    elif func == 'set_site_obj_open':
        print(setSiteObjOpen())
    elif func == 'set_cc_conf':
        print(setCcConf())
    elif func == 'set_site_cc_conf':
        print(setSiteCcConf())
    elif func == 'set_retry':
        print(setRetry())
    elif func == 'set_safe_verify':
        print(setSafeVerify())
    elif func == 'set_site_retry':
        print(setSiteRetry())
    elif func == 'save_scan_rule':
        print(saveScanRule())
    elif func == 'get_site_config':
        print(getSiteConfig())
    elif func == 'get_default_site':
        print(getDefaultSite())
    elif func == 'get_country':
        print(getCountry())
    elif func == 'get_site_config_byname':
        print(getSiteConfigByName())
    elif func == 'add_site_cdn_header':
        print(addSiteCdnHeader())
    elif func == 'remove_site_cdn_header':
        print(removeSiteCdnHeader())
    elif func == 'get_logs_list':
        print(getLogsList())
    elif func == 'get_safe_logs':
        print(getSafeLogs())
    elif func == 'output_data':
        print(outputData())
    elif func == 'import_data':
        print(importData())
    elif func == 'waf_srceen':
        print(getWafSrceen())
    elif func == 'get_total_statistics':
        print(getTotalStatistics())
    elif func == 'waf_conf':
        print(getWafConf())
    elif func == 'area_limit_switch':
        print(areaLimitSwitch())
    elif func == 'get_area_limit':
        print(getAreaLimit())
    elif func == 'add_area_limit':
        print(addAreaLimit())
    elif func == 'del_area_limit':
        print(delAreaLimit())
    elif func == 'clean_drop_ip':
        print(cleanDropIp())
    elif func == 'add_trusted_proxy':
        print(addTrustedProxy())
    elif func == 'remove_trusted_proxy':
        print(removeTrustedProxy())
    elif func == 'test_run':
        print(testRun())
    elif func == 'getDropIpList':
        print(getDropIpList())
    elif func == 'removeDropIp':
        print(removeDropIp())
    elif func == 'getDropIpLogs':
        print(getDropIpLogs())
    elif func == 'setHoneypotPaths':
        print(setHoneypotPaths())
    elif func == 'getIpLocationBatch':
        print(getIpLocationBatch())
    elif func == 'getIpLocation':
        print(getIpLocation())
    elif func == 'get_spider_conf' or func == 'getSpiderConf':
        print(getSpiderConf())
    elif func == 'set_spider_mode' or func == 'setSpiderMode':
        print(setSpiderMode())
    elif func == 'get_spider_ip_list' or func == 'getSpiderIpList':
        print(getSpiderIpList())
    elif func == 'add_spider_ip' or func == 'addSpiderIp':
        print(addSpiderIp())
    elif func == 'remove_spider_ip' or func == 'removeSpiderIp':
        print(removeSpiderIp())
    elif func == 'sync_spider_ip' or func == 'syncSpiderIp':
        print(syncSpiderIp())
    # ---- 御风F2B防火墙（fail2ban）情报联动 ----
    elif func == 'get_ban_sync' or func == 'getBanSync':
        print(getBanSync())
    elif func == 'set_ban_sync' or func == 'setBanSync':
        print(setBanSync())
    else:
        print('error')
