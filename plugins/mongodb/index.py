# coding:utf-8

import sys
import io
import os
import time
import re
import json
import datetime
import tarfile
import yaml

# 库名/用户名/集合名白名单（`\Z` 挡尾随换行，见 check_safe_name 注释）
_SAFE_NAME_RE = re.compile(r'^[a-zA-Z0-9_\-]+\Z')
# 备份/导入文件名白名单：首字符必须是字母数字下划线，挡掉 `.`/`..`/隐藏文件
_DB_BACKUP_FILE_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.\-]*\Z')
# 允许通过面板授予的库角色（与 getAllRole/getDbAccess 展示的角色集一致）
_DB_ACCESS_ROLES = ('read', 'readWrite', 'dbOwner', 'userAdmin')

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import logging

_log = logging.getLogger('yf.mongodb')

app_debug = False
if yf.isAppleSystem():
    app_debug = True


# /usr/lib/systemd/system/mongod.service

# python3 " + yf.getPanelDir() + "/plugins/mongodb/index.py repl_init 
# python3 " + yf.getPanelDir() + "/plugins/mongodb/index.py run_repl_info
# python3 " + yf.getPanelDir() + "/plugins/mongodb/index.py test_data
# python3 " + yf.getPanelDir() + "/plugins/mongodb/index.py run_info

def getPluginName():
    return 'mongodb'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getInitDFile():
    if app_debug:
        return '/tmp/' + getPluginName()
    return '/etc/init.d/' + getPluginName()


def getConf():
    path = getServerDir() + "/mongodb.conf"
    return path

def getConfKey():
    key = getServerDir() + "/mongodb.key"
    return key

def getConfTpl():
    path = getPluginDir() + "/config/mongodb.conf"
    return path

def _defaultConfigData():
    return {
        "systemLog": {
            "destination": "file",
            "logAppend": True,
            "path": getServerDir() + "/logs/mongodb.log"
        },
        "storage": {
            "dbPath": getServerDir() + "/data",
            "directoryPerDB": True,
            "journal": {
                "enabled": True
            }
        },
        "processManagement": {
            "fork": True,
            "pidFilePath": getServerDir() + "/mongodb.pid"
        },
        "net": {
            "port": 27017,
            "bindIp": "0.0.0.0"
        },
        "security": {
            "authorization": "enabled",
            "javascriptEnabled": False
        }
    }


def getConfigData():
    """读取并解析 mongodb.conf，**永远返回 dict**。

    历史实现只兜住「yaml 抛异常」：配置文件被清空时 `yaml.safe_load('')` 返回 None、
    只写了标量时返回 str/int —— 都不抛异常，于是 `getConfigData()` 返回非 dict，
    调用方 `data['net']` 直接 TypeError（接口 500）。
    """
    cfg = getConf()
    config_data = yf.readFile(cfg)
    config = None
    if config_data:
        try:
            config = yaml.safe_load(config_data)
        except Exception as _e:
            _log.debug('[mongodb] getConfigData 解析失败: %s', _e)
            config = None
    if not isinstance(config, dict):
        config = _defaultConfigData()
    return config

def setConfig(config_data):
    # t = status()
    cfg = getConf()
    try:
        yf.writeFile(cfg, yaml.safe_dump(config_data))
    except Exception as _e:
        _log.debug('[mongodb] setConfig 异常已忽略: %s', _e)
        return False
    return True

def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


def getConfIp():
    net = getConfigData().get('net') or {}
    ip = net.get('bindIp')
    if not isinstance(ip, str) or not ip.strip():
        return '127.0.0.1'
    return ip

def getConfLocalIp():
    return '127.0.0.1'

def getConfPort():
    net = getConfigData().get('net') or {}
    try:
        return int(str(net.get('port', 27017)).strip())
    except Exception:
        return 27017

def getConfAuth():
    sec = getConfigData().get('security') or {}
    auth = sec.get('authorization')
    return auth if auth in ('enabled', 'disabled') else 'disabled'
    # file = getConf()
    # content = yf.readFile(file)
    # rep = 'auth\s*=\s*(.*)'
    # tmp = re.search(rep, content)
    # return tmp.groups()[0].strip()

def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        val = args[0].strip()
        # 前端（YfPlugin.parseArgs）把参数序列化成 JSON 字符串，由 utils/plugin.py::run()
        # 作为**单个** argv 传入。历史实现只按 `k:v` 切第一段，JSON 会被整体塞进
        # tmp['"id"'] = '"1","name":...'，于是**所有带参接口恒回「缺少必要参数」**
        # （真机实测：set_db_ps/get_db_backup_list/del_db/... 全部不可用）。
        if val.startswith('{') and val.endswith('}'):
            try:
                data = json.loads(val)
                if isinstance(data, dict):
                    return data
            except Exception as _e:
                _log.debug('[mongodb] getArgs JSON 解析失败: %s', _e)
        t = val.strip('{').strip('}')
        if t.strip() == '':
            tmp = {}
        else:
            t = t.split(':', 1)
            if len(t) == 2:
                k = t[0].strip().strip('"').strip("'")
                v = t[1].strip().strip('"').strip("'")
                tmp[k] = v
    elif args_len > 1:
        for i in range(len(args)):
            if ':' in args[i]:
                t = args[i].split(':', 1)
                k = t[0].strip().strip('"').strip("'")
                v = t[1].strip().strip('"').strip("'")
                tmp[k] = v

    return tmp


def check_safe_name(val):
    r"""库名/用户名/集合名白名单。

    用 `\Z` 而不是 `$`：Python 的 `$` 也匹配「结尾换行之前」，`'yftest\n'` 能通过
    校验后被拼进配置/命令（与 B03 postgres 同族缺陷）。
    """
    if not val:
        return False
    return bool(_SAFE_NAME_RE.match(str(val)))


def _parsePageArgs(args, default_size=10, max_size=100):
    """分页参数容错夹取：非数字回默认值，越界夹到合法区间（历史实现 `int(args['page'])`
    对 `page=abc` 直接 ValueError → 接口 500）。"""
    try:
        page = int(str(args.get('page', 1)).strip())
    except Exception:
        page = 1
    try:
        page_size = int(str(args.get('page_size', default_size)).strip())
    except Exception:
        page_size = default_size
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = default_size
    if page_size > max_size:
        page_size = max_size
    return page, page_size


def _validConfPath(val):
    """配置文件里的路径项：必须是非空绝对路径且不含换行/NUL。

    历史实现把任意串直接写进 mongodb.conf（`data_path=''`、`log='a\nb'`），mongod
    下次启动即失败，而接口仍回「设置成功」（与 B01/B02/B03 的端口不校验同族）。
    """
    val = str(val).strip()
    if not val or not val.startswith('/'):
        return False
    if '\n' in val or '\r' in val or '\x00' in val:
        return False
    return True


def _validBindIp(val):
    """bindIp 白名单：单个 IP 或逗号分隔的 IP 列表（IPv4/IPv6 字面量）。

    用 ipaddress 判定而不是十六进制字符集：`[0-9a-fA-F:.]+` 会放行 `abc`、`deadbeef`
    这类非 IP 串（写进 mongodb.conf 后 mongod 启动失败）。
    """
    import ipaddress
    val = str(val).strip()
    if not val:
        return False
    for ip in val.split(','):
        ip = ip.strip()
        if not ip:
            return False
        try:
            ipaddress.ip_address(ip)
        except Exception:
            return False
    return True


def _requireRunning():
    """读类接口的统一前置检查：服务未运行时如实回「未启动!」，不去连驱动。"""
    if status() == 'stop':
        return yf.returnJson(False, '未启动!')
    return None


def _safeExtractTar(tar_path, dest_dir):
    """安全解压 tar.gz：拒绝绝对路径/`..`/软硬链接/设备与管道文件，并做 realpath 兜底。

    面板 python 是 3.11，`tarfile.extractall` 没有 `filter=` 参数（3.12+ 才有 data
    filter），历史实现直接 extractall(path=dest) → tar 内 `../x` 成员可写到 dest 之外
    （面板以 root 运行 = 任意文件写）。
    :return: (ok, err)
    """
    dest_real = os.path.realpath(dest_dir)
    try:
        with tarfile.open(tar_path, 'r:gz') as tar_ref:
            for member in tar_ref.getmembers():
                name = member.name
                if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                    return (False, '备份包内含非法条目: ' + name)
                if name.startswith('/') or '..' in name.split('/'):
                    return (False, '备份包内含越界条目: ' + name)
                target = os.path.realpath(os.path.join(dest_real, name))
                if target != dest_real and not target.startswith(dest_real + os.sep):
                    return (False, '备份包内含越界条目: ' + name)
            tar_ref.extractall(path=dest_real)
    except Exception as e:
        return (False, str(e))
    return (True, '')

def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))

def status():
    if not yf.isAppleSystem():
        status_cmd = 'systemctl is-active mongodb'
        res = yf.execShell(status_cmd)
        if res[0].strip() == 'active':
            return 'start'

    # pid 文件路径以配置为准（配置缺失时回默认路径），不再硬编码 log/ 子目录：
    # 历史实现读 `.../mongodb/log/mongodb.pid`，而 mongod.conf 的 pidFilePath 是
    # `.../mongodb/mongodb.pid`，快速探针永远命不中。
    pid_file = getPidFile()
    if os.path.exists(pid_file):
        try:
            pid = int(yf.readFile(pid_file).strip())
            if os.path.exists("/proc/" + str(pid)):
                return 'start'
        except Exception as _e:
            _log.debug('[mongodb] status 异常已忽略: %s', _e)

    # pgrep -x 为精确进程名匹配，不会命中插件自己的 `python3 .../mongodb/index.py status`
    data = yf.execShell("pgrep -x mongod")
    if data[0].strip() != '':
        return 'start'
    return 'stop'


def getPidFile():
    pm = getConfigData().get('processManagement') or {}
    pid = pm.get('pidFilePath')
    if isinstance(pid, str) and pid.strip():
        return pid.strip()
    return getServerDir() + '/mongodb.pid'

def pSqliteDb(dbname='users'):
    file = getServerDir() + '/mongodb.db'
    name = 'mongodb'

    sql_file = getPluginDir() + '/config/mongodb.sql'
    import_sql = yf.readFile(sql_file)
    # print(sql_file,import_sql)
    md5_sql = yf.md5(import_sql)

    import_sign = False
    save_md5_file = getServerDir() + '/import_mongodb.md5'
    if os.path.exists(save_md5_file):
        save_md5_sql = yf.readFile(save_md5_file)
        if save_md5_sql != md5_sql:
            import_sign = True
            yf.writeFile(save_md5_file, md5_sql)
    else:
        yf.writeFile(save_md5_file, md5_sql)

    if not os.path.exists(file) or import_sql:
        conn = yf.M(dbname).dbPos(getServerDir(), name)
        csql_list = import_sql.split(';')
        for index in range(len(csql_list)):
            conn.execute(csql_list[index], ())

    conn = yf.M(dbname).dbPos(getServerDir(), name)
    return conn

def mongdbClientS():
    import pymongo
    port = getConfPort()
    auth = getConfAuth()
    ip = getConfLocalIp()
    mg_root = pSqliteDb('config').where('id=?', (1,)).getField('mg_root')

    if auth == 'disabled':
        client = pymongo.MongoClient(host=ip, port=int(port), directConnection=True)
    else:
        # print(auth,mg_root)
        client = pymongo.MongoClient(host=ip, port=int(port), directConnection=True, username='root',password=mg_root)
    return client

def mongdbClient():
    import pymongo
    port = getConfPort()
    auth = getConfAuth()
    ip = getConfLocalIp()
    mg_root = pSqliteDb('config').where('id=?', (1,)).getField('mg_root')
    # print(ip,port,auth,mg_root)
    if auth == 'disabled':
        client = pymongo.MongoClient(host=ip, port=int(port), directConnection=True)
    else:
        # uri = "mongodb://root:"+mg_root+"@127.0.0.1:"+str(port)
        # client = pymongo.MongoClient(uri)
        client = pymongo.MongoClient(host=ip, port=int(port), directConnection=True, username='root',password=mg_root)
    return client


def initDreplace():

    mg_key = getServerDir() + "/mongodb.key"
    if not os.path.exists(mg_key):
        yf.execShell("openssl rand -base64 756 >> "+mg_key)
        yf.execShell("chmod 400 "+mg_key)

    file_tpl = getInitDTpl()
    service_path = yf.getServerDir()

    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        os.mkdir(initD_path)
    file_bin = initD_path + '/' + getPluginName()

    logs_dir = getServerDir() + '/logs'
    if not os.path.exists(logs_dir):
        os.mkdir(logs_dir)

    data_dir = getServerDir() + '/data'
    if not os.path.exists(data_dir):
        os.mkdir(data_dir)

    # 兼容从宝塔迁移过来的配置文件
    dst_conf = getServerDir() + '/mongodb.conf'
    bt_conf = getServerDir() + '/config.conf'
    if not os.path.exists(dst_conf):
        if os.path.exists(bt_conf):
            yf.execShell(f"cp -f {bt_conf} {dst_conf}")
        else:
            conf_content = yf.readFile(getConfTpl())
            conf_content = conf_content.replace('{$SERVER_PATH}', service_path)
            yf.writeFile(dst_conf, conf_content)

    install_ok = getServerDir() + "/install.lock"
    if os.path.exists(install_ok):
        return file_bin
    yf.writeFile(install_ok, 'ok')

    # initd replace
    content = yf.readFile(file_tpl)
    content = content.replace('{$SERVER_PATH}', service_path)
    yf.writeFile(file_bin, content)
    yf.execShell('chmod +x ' + file_bin)

    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/mongodb.service'
    systemServiceTpl = getPluginDir() + '/init.d/mongodb.service.tpl'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        service_path = yf.getServerDir()
        se_content = yf.readFile(systemServiceTpl)
        se_content = se_content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(systemService, se_content)
        yf.execShell('systemctl daemon-reload')

    return file_bin


def mgOp(method):
    file = initDreplace()
    if yf.isAppleSystem():
        data = yf.execShell(file + ' ' + method)
        # print(data)
        if data[1] == '':
            return 'ok'
        return data[1]

    # 用带退出码的执行：历史实现只看 stderr 是否为空，systemctl 失败（服务不存在、
    # 单元加载失败）也被报成 'ok'（假成功，上层据此认为已启动/已重启）。
    rc, out, err = yf.execShellRc('systemctl ' + method + ' ' + getPluginName())
    if rc == 0:
        return 'ok'
    return 'fail: ' + (err.strip() or out.strip() or ('rc=%s' % rc))


def start():
    yf.execShell(
        'export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/www/server/lib/openssl11/lib')
    if status() == 'start':
        return 'ok'
    res = mgOp('start')
    if res != 'ok':
        return res
    for _ in range(8):
        if status() == 'start':
            return 'ok'
        time.sleep(1)
    # 8 秒仍未就绪：如实返回失败，绝不把 'ok' 回给上层造成「已启动」误判
    return 'error: mongodb 启动后未就绪（%s）' % res


def stop():
    res = mgOp('stop')
    for _ in range(5):
        if status() == 'stop':
            break
        time.sleep(1)
    return res


def reload():
    return mgOp('reload')


def restart():
    if os.path.exists("/tmp/mongodb-27017.sock"):
        yf.removeDir("/tmp/mongodb-27017.sock")

    res = mgOp('restart')
    if res != 'ok':
        return res
    for _ in range(8):
        if status() == 'start':
            return 'ok'
        time.sleep(1)
    return 'error: mongodb 重启后未就绪（%s）' % res


def getConfig():
    t = status()
    if t == 'stop':
        return yf.returnJson(False,'未启动!')
    d = getConfigData()
    return yf.returnJson(True,'ok',d)

def saveConfig():
    d = getConfigData()
    args = getArgs()
    data = checkArgs(args, ['bind_ip','port','data_path','log','pid_file_path'])
    if not data[0]:
        return data[1]

    # 先校验后落盘：非法值（端口非数字/越界、路径非绝对、bindIp 垃圾）写进
    # mongodb.conf 会让 mongod 下次启动直接失败，而接口仍回「设置成功」。
    port = str(args['port']).strip()
    if not re.match(r'^[0-9]+\Z', port) or not (1 <= int(port) <= 65535):
        return yf.returnJson(False, '端口不合法!')
    bind_ip = str(args['bind_ip']).strip()
    if not _validBindIp(bind_ip):
        return yf.returnJson(False, '参数不合法: bind_ip')
    data_path = str(args['data_path']).strip()
    log_path = str(args['log']).strip()
    pid_file_path = str(args['pid_file_path']).strip()
    for k, v in (('data_path', data_path), ('log', log_path), ('pid_file_path', pid_file_path)):
        if not _validConfPath(v):
            return yf.returnJson(False, '参数不合法: ' + k)

    d.setdefault('net', {})
    d['net']['bindIp'] = bind_ip
    d['net']['port'] = int(port)
    d.setdefault('storage', {})['dbPath'] = data_path
    d.setdefault('systemLog', {})['path'] = log_path
    d.setdefault('processManagement', {})['pidFilePath'] = pid_file_path
    if not setConfig(d):
        return yf.returnJson(False, '设置失败: 配置文件写入失败')
    res = restart()
    if res != 'ok':
        return yf.returnJson(False, '设置失败: 服务未就绪(' + str(res) + ')')
    return yf.returnJson(True,'设置成功')

def initMgRoot(password='',force=0):
    d = getConfigData()
    auth_t = d['security']['authorization']
    if force == 1:
        d['security']['authorization'] = 'disabled'
        setConfig(d)
        restart()

    try:
        client = mongdbClient()
        db = client.admin

        db_all_rules = [
            {'role': 'root', 'db': 'admin'},
            {'role': 'clusterAdmin', 'db': 'admin'},
            {'role': 'readAnyDatabase', 'db': 'admin'},
            {'role': 'readWriteAnyDatabase', 'db': 'admin'},
            {'role': 'userAdminAnyDatabase', 'db': 'admin'},
            {'role': 'dbAdminAnyDatabase', 'db': 'admin'},
            {'role': 'userAdmin', 'db': 'admin'},
            {'role': 'dbAdmin', 'db': 'admin'}
        ]

        if password =='':
            mg_pass = yf.getRandomString(8)
        else:
            mg_pass = password

        try:
            db.command("createUser", "root", pwd=mg_pass, roles=db_all_rules)
        except Exception as e:
            if force == 0:
                db.command("updateUser", "root", pwd=mg_pass, roles=db_all_rules)
            else:
                db.command('dropUser','root')
                db.command("createUser", "root", pwd=mg_pass, roles=db_all_rules)
        pSqliteDb('config').where('id=?', (1,)).save('mg_root',(mg_pass,))
    finally:
        # 无论改密成败都必须把 authorization 恢复：历史实现只在成功路径恢复，
        # 中途异常会把面板留在「认证已关闭」状态（且 root 口令未写入面板库）。
        if force == 1:
            d['security']['authorization'] = auth_t
            setConfig(d)
            restart()
    return True

def initUserRoot():
    d = getConfigData()
    auth_t = d['security']['authorization']
    d['security']['authorization'] = 'disabled'
    setConfig(d)
    restart()
    time.sleep(1)

    try:
        client = mongdbClient()
        db = client.admin

        db_all_rules = [
            {'role': 'root', 'db': 'admin'},
            {'role': 'clusterAdmin', 'db': 'admin'},
            {'role': 'readAnyDatabase', 'db': 'admin'},
            {'role': 'readWriteAnyDatabase', 'db': 'admin'},
            {'role': 'userAdminAnyDatabase', 'db': 'admin'},
            {'role': 'dbAdminAnyDatabase', 'db': 'admin'},
            {'role': 'userAdmin', 'db': 'admin'},
            {'role': 'dbAdmin', 'db': 'admin'}
        ]
        mg_pass = yf.getRandomString(8)
        try:
            db.command("createUser", "root", pwd=mg_pass, roles=db_all_rules)
        except Exception as e:
            _log.debug('[mongodb] initUserRoot createUser 失败，回退 dropUser+createUser: %s', e)
            db.command('dropUser','root')
            db.command("createUser", "root", pwd=mg_pass, roles=db_all_rules)

        pSqliteDb('config').where('id=?', (1,)).save('mg_root',(mg_pass,))
    finally:
        d['security']['authorization'] = auth_t
        setConfig(d)
        restart()
    return True

def setConfigAuth():
    init_db_root = getServerDir() + '/init_db_root.lock'
    if not os.path.exists(init_db_root):
        initUserRoot()
        yf.writeFile(init_db_root,'ok')

    d = getConfigData()
    d.setdefault('security', {})
    if d['security'].get('authorization') == 'enabled':
        d['security']['authorization'] = 'disabled'
        # 用 pop：历史实现 del d['security']['keyFile'] 在配置缺该项时 KeyError
        d['security'].pop('keyFile', None)
        setConfig(d)
        res = restart()
        if res != 'ok':
            return yf.returnJson(False, '设置失败: 服务未就绪(' + str(res) + ')')
        return yf.returnJson(True,'关闭成功')
    else:
        # 开启认证必须先有 keyFile（集群内部认证用），否则 mongod 起不来
        key_file = getConfKey()
        if not os.path.exists(key_file):
            return yf.returnJson(False, '设置失败: 缺少 keyFile ' + key_file)
        d['security']['authorization'] = 'enabled'
        d['security']['keyFile'] = key_file
        setConfig(d)
        res = restart()
        if res != 'ok':
            return yf.returnJson(False, '设置失败: 服务未就绪(' + str(res) + ')')
        return yf.returnJson(True,'开启成功')

def runInfo():
    '''
    cd <面板目录> && source bin/activate && python3 plugins/mongodb/index.py run_info
    '''
    r = _requireRunning()
    if r:
        return r
    try:
        client = mongdbClient()
        db = client.admin
        serverStatus = db.command('serverStatus')
        listDbs = client.list_database_names()

        result = {}
        result["host"] = serverStatus['host']
        result["version"] = serverStatus['version']
        result["uptime"] = serverStatus['uptime']
        result['db_path'] = getServerDir() + "/data"
        result["connections"] = serverStatus['connections']['current']
        result["collections"] = len(listDbs)

        pf = serverStatus['opcounters']
        result['pf'] = pf
    except Exception as e:
        return yf.returnJson(False, '操作失败: ' + str(e))
    return yf.getJson(result)


def runDocInfo():
    r = _requireRunning()
    if r:
        return r
    try:
        client = mongdbClient()
        serverStatus = client.admin.command('serverStatus')
        listDbs = client.list_database_names()
        showDbList = []
        result = {}
        for x in range(len(listDbs)):
            mongd = client[listDbs[x]]
            stats = mongd.command({"dbstats": 1})
            if 'operationTime' in stats:
                del stats['operationTime']

            if '$clusterTime' in stats:
                del stats['$clusterTime']
            showDbList.append(stats)

        result["dbs"] = showDbList
    except Exception as e:
        return yf.returnJson(False, '操作失败: ' + str(e))
    return yf.getJson(result)

def runReplInfo():
    client = mongdbClient()
    db = client.admin
    result = {}
    try:
        serverStatus = db.command('serverStatus')
    except Exception as e:
        return yf.returnJson(False, str(e))

    d = getConfigData()
    if 'replication' in d and 'replSetName' in d['replication']:
        result['repl_name'] = d['replication']['replSetName']

    result['status'] = '无'
    result['doc_name'] = '无'
    if 'repl' in serverStatus:
        repl = serverStatus['repl']
        # print(repl)
        result['status'] = '从'
        if 'ismaster' in repl and repl['ismaster']:
            result['status'] = '主'

        if 'secondary' in repl and not repl['secondary']:
            result['status'] = '主'

        result['setName'] = yf.getDefault(repl,'setName', '') 
        result['primary'] = yf.getDefault(repl,'primary', '') 
        result['me'] = yf.getDefault(repl,'me', '') 

        hosts = yf.getDefault(repl,'hosts', '') 
        result['hosts'] = ','.join(hosts)

    result['members'] = []
    try:
        members_list = []
        replStatus = db.command('replSetGetStatus')
        if 'members' in replStatus:
            members = replStatus['members']
            for m in members:
                t = {}
                t['name'] = m['name']
                t['stateStr'] = m['stateStr']
                t['uptime'] = m['uptime']
                members_list.append(t)
        result['members'] = members_list
    except Exception as e:
        _log.debug('[mongodb] runReplInfo 异常已忽略: %s', e)
        
    return yf.returnJson(True, 'OK', result)

def getDbList():
    args = getArgs()
    page, page_size = _parsePageArgs(args)
    search = str(args.get('search', '') or '')
    data = {}

    conn = pSqliteDb('databases')
    limit = str((page - 1) * page_size) + ',' + str(page_size)
    condition = ''
    param = ()
    if search != '':
        # 参数化：历史实现把 search 直接拼进 LIKE（`name like '%x' OR '1'='1%'`），
        # 可注入读出任意行（与 B01/B02 的 SQL 注入同族）。
        condition = "name like ?"
        param = ('%' + search + '%',)
    field = 'id,name,username,password,accept,rw,ps,addtime'
    clist = conn.where(condition, param).field(
        field).limit(limit).order('id desc').select()

    for x in range(0, len(clist)):
        dbname = clist[x]['name']
        blist = getDbBackupListFunc(dbname)
        clist[x]['is_backup'] = False
        if len(blist) > 0:
            clist[x]['is_backup'] = True

    count = conn.where(condition, param).count()
    _page = {}
    _page['count'] = count
    _page['p'] = page
    _page['row'] = page_size
    _page['tojs'] = 'dbList'
    data['page'] = yf.getPage(_page)
    data['data'] = clist

    info = {}
    info['root_pwd'] = '******'
    data['info'] = info
    return yf.getJson(data)
    # return yf.returnJson(True,'ok',data)

def addDb():
    t = status()
    if t == 'stop':
        return yf.returnJson(False,'未启动!')

    args = getArgs()
    data = checkArgs(args, ['ps','name','db_user','password'])
    if not data[0]:
        return data[1]

    data_name = str(args['name']).strip()
    if not data_name:
        return yf.returnJson(False, "数据库名不能为空！")

    username = str(args['db_user']).strip()
    if not check_safe_name(data_name) or not check_safe_name(username):
        return yf.returnJson(False, "安全拦截：数据库名与用户名仅允许英文字母、数字和下划线与中划线！")

    nameArr = ['admin', 'config', 'local']
    if data_name in nameArr:
        return yf.returnJson(False, "数据库名是保留名称!")

    addTime = time.strftime('%Y-%m-%d %X', time.localtime())
    # auth为true时如果__DB_USER为空则将它赋值为 root，用于开启本地认证后数据库用户为空的情况
    auth_status = getConfAuth() == "enabled"

    if auth_status:
        # 保持上面校验过的（已 strip 的）库名/用户名，不回退到未 strip 的原值
        username = str(args['db_user']).strip()
        password = str(args['password'])
    else:
        username = data_name
        password = ''

    try:
        client = mongdbClient()
        client[data_name].zchat.insert_one({})
        user_roles = [{'role': 'dbOwner', 'db': data_name}, {'role': 'userAdmin', 'db': data_name}]
        if auth_status:
            client.admin.command("createUser", username, pwd=password, roles=user_roles)
    except Exception as ex:
        # 驱动侧失败必须如实报错（历史实现让它抛出去变 traceback）
        return yf.returnJson(False, '操作失败: ' + str(ex))

    ps = str(args['ps'])
    if ps == '':
        ps = data_name

    # 添加入SQLITE
    pSqliteDb('databases').add('name,username,password,accept,ps,addtime', (data_name, username, password, '127.0.0.1', ps, addTime))
    return yf.returnJson(True, '添加成功')


def delDb():
    sqlite_db = pSqliteDb('databases')

    args = getArgs()
    data = checkArgs(args, ['id', 'name'])
    if not data[0]:
        return data[1]

    name = str(args['name']).strip()
    if not check_safe_name(name):
        return yf.returnJson(False, "安全拦截：非法数据库名！")

    try:
        sid = args['id']
        find = sqlite_db.where("id=?", (sid,)).field('id,name,username,password,accept,ps,addtime').find()
        # 记录不存在时历史实现直接 find['accept'] → TypeError traceback
        if not find:
            return yf.returnJson(False, '数据库不存在!')
        username = find['username']

        client = mongdbClient()
        client.drop_database(name)

        try:
            client.admin.command('dropUser',username)
        except Exception as e:
            _log.debug('[mongodb] delDb 异常已忽略: %s', e)

        # 删除SQLITE
        sqlite_db.where("id=?", (sid,)).delete()
        return yf.returnJson(True, '删除成功!')
    except Exception as ex:
        return yf.returnJson(False, '删除失败!' + str(ex))


def delDbTable():
    args = getArgs()
    data = checkArgs(args, ['table_name', 'name'])
    if not data[0]:
        return data[1]

    name = str(args['name']).strip()
    table_name = str(args['table_name']).strip()
    # 库名/集合名双白名单：历史实现无任何校验，`name=admin` 可直接 drop 系统库集合
    if not check_safe_name(name):
        return yf.returnJson(False, "安全拦截：非法数据库名！")
    if not check_safe_name(table_name):
        return yf.returnJson(False, '集合名称不合法!')
    if name in ['admin', 'config', 'local']:
        return yf.returnJson(False, "数据库名是保留名称!")

    try:
        client = mongdbClient()
        client[name][table_name].drop()
        return yf.returnJson(True, '删除成功!')
    except Exception as ex:
        return yf.returnJson(False, '删除失败!' + str(ex))

def setRootPwd(version=''):
    args = getArgs()
    data = checkArgs(args, ['password'])
    if not data[0]:
        return data[1]

    #强制修改
    force = 0
    if 'force' in args and args['force'] == '1':
        force = 1

    password = args['password']
    if password == '******':
        return yf.returnJson(True, '数据库root密码未发生变更')
    try:
        msg = ''
        if force == 1:
            msg = ',无须强制!'
        initMgRoot(password, force)
        return yf.returnJson(True, '数据库root密码修改成功!'+msg)
    except Exception as ex:
        return yf.returnJson(False, '修改错误:' + str(ex))

def setUserPwd(version=''):
    args = getArgs()
    # id 必须纳入 checkArgs：历史实现只在后面裸取 args['id']，缺参时 KeyError traceback
    data = checkArgs(args, ['password', 'name', 'id'])
    if not data[0]:
        return data[1]

    newpassword = str(args['password'])
    username = str(args['name']).strip()
    uid = args['id']
    name = None
    try:
        sqlite_db = pSqliteDb('databases')
        name = sqlite_db.where('id=?', (uid,)).getField('name')
        if not name:
            return yf.returnJson(False, '数据库不存在!')
        user_roles = [{'role': 'dbOwner', 'db': name}, {'role': 'userAdmin', 'db': name}]

        client = mongdbClient()
        db = client.admin
        try:
            db.command("updateUser", username, pwd=newpassword, roles=user_roles)
        except Exception as e:
            db.command("createUser", username, pwd=newpassword, roles=user_roles)

        sqlite_db.where("id=?", (uid,)).setField('password', newpassword)
        return yf.returnJson(True, yf.getInfo('修改数据库[{1}]密码成功!', (name,)))
    except Exception as ex:
        return yf.returnJson(False, yf.getInfo('修改数据库[{1}]密码失败[{2}]!', (name or uid, str(ex),)))


def syncGetDatabases():
    r = _requireRunning()
    if r:
        return r
    try:
        client = mongdbClient()
        sqlite_db = pSqliteDb('databases')
        data = client.admin.command({"listDatabases": 1})
    except Exception as ex:
        return yf.returnJson(False, '操作失败: ' + str(ex))
    nameArr = ['admin', 'config', 'local']
    n = 0

    for value in data['databases']:
        vdb_name = value["name"]
        b = False
        for key in nameArr:
            if vdb_name == key:
                b = True
                break
        if b:
            continue
        if sqlite_db.where("name=?", (vdb_name,)).count() > 0:
            continue

        host = '127.0.0.1'
        ps = vdb_name
        addTime = time.strftime('%Y-%m-%d %X', time.localtime())
        if sqlite_db.add('name,username,password,accept,ps,addtime', (vdb_name, vdb_name, '', host, ps, addTime)):
            n += 1

    msg = yf.getInfo('本次共从服务器获取了{1}个数据库!', (str(n),))
    return yf.returnJson(True, msg)

def setDbPs():
    args = getArgs()
    data = checkArgs(args, ['id', 'name', 'ps'])
    if not data[0]:
        return data[1]

    ps = str(args['ps'])
    sid = args['id']
    name = str(args['name'])
    try:
        psdb = pSqliteDb('databases')
        # 不存在的 id 不得回「成功」（历史缺陷：假成功，备注实际未落库）
        if not psdb.where("id=?", (sid,)).count():
            return yf.returnJson(False, yf.getInfo('修改数据库[{1}]备注失败!', (name,)))
        psdb.where("id=?", (sid,)).setField('ps', ps)
        return yf.returnJson(True, yf.getInfo('修改数据库[{1}]备注成功!', (name,)))
    except Exception as e:
        return yf.returnJson(False, yf.getInfo('修改数据库[{1}]备注失败!', (name,)))


def getDbInfo():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    db_name = str(args['name']).strip()
    if not check_safe_name(db_name):
        return yf.returnJson(False, "安全拦截：非法数据库名！")
    r = _requireRunning()
    if r:
        return r

    try:
        client = mongdbClient()
        db = client[db_name]

        result = {}
        t = db.command("dbStats")
        result['collections'] = t['collections']
        result['avgObjSize'] = t['avgObjSize']
        result['dataSize'] = t['dataSize']
        result['storageSize'] = t['storageSize']
        result['indexSize'] = t['indexSize']

        result["collection_list"] = []
        for collection_name in db.list_collection_names():
            collection = db.command("collStats", collection_name)
            item = {
                "collection_name": collection_name,
                "count": collection.get("count"),  # 文档数
                "size": collection.get("size"),  # 内存中的大小
                "avg_obj_size": collection.get("avgObjSize"),  # 对象平均大小
                "storage_size": collection.get("storageSize"),  # 存储大小
                "capped": collection.get("capped"),
                "nindexes": collection.get("nindexes"),  # 索引数
                "total_index_size": collection.get("totalIndexSize"),  # 索引大小
            }
            result["collection_list"].append(item)
    except Exception as ex:
        return yf.returnJson(False, '操作失败: ' + str(ex))

    return yf.returnJson(True,'ok', result)

def toDbBase(find):
    client = mongdbClient()
    db_admin = client.admin
    data_name = find['name']
    db = client[data_name]

    db.zchat.insert_one({})
    user_roles = [{'role': 'dbOwner', 'db': data_name}, {'role': 'userAdmin', 'db': data_name}]
    try:
        db_admin.command("createUser", find['username'], pwd=find['password'], roles=user_roles)
    except Exception as e:
        db_admin.command("updateUser", find['username'], pwd=find['password'], roles=user_roles)
    return 1

def syncToDatabases():
    args = getArgs()
    data = checkArgs(args, ['type', 'ids'])
    if not data[0]:
        return data[1]

    try:
        stype = int(str(args['type']).strip())
    except Exception:
        return yf.returnJson(False, '参数不合法: type')
    sqlite_db = pSqliteDb('databases')
    n = 0

    try:
        if stype == 0:
            data = sqlite_db.field('id,name,username,password,accept').select()
            for value in data:
                result = toDbBase(value)
                if result == 1:
                    n += 1
        else:
            try:
                ids = json.loads(args['ids'])
            except Exception:
                return yf.returnJson(False, '参数不合法: ids')
            if not isinstance(ids, list):
                return yf.returnJson(False, '参数不合法: ids')
            for value in ids:
                find = sqlite_db.where("id=?", (value,)).field(
                    'id,name,username,password,accept').find()
                if not find:
                    continue
                result = toDbBase(find)
                if result == 1:
                    n += 1
    except Exception as ex:
        return yf.returnJson(False, '操作失败: ' + str(ex))
    msg = yf.getInfo('本次共同步了{1}个数据库!', (str(n),))
    return yf.returnJson(True, msg)


def getAllRole():
    r = _requireRunning()
    if r:
        return r
    mongo_role = {
        # 数据库用户角色
        "read": "读取数据(read)",
        "readWrite": "读取和写入数据(readWrite)",
        # 数据库管理角色
        # "dbAdmin": "数据库管理员",
        "dbOwner": "数据库所有者(dbOwner)",
        "userAdmin": "用户管理员(userAdmin)",
        # 集群管理角色
        # "clusterAdmin": "集群管理员",
        # "clusterManager": "集群管理器",
        # "clusterMonitor": "集群监视器",
        # "hostManager": "主机管理员",
        # 备份和恢复角色
        # "backup": "备份数据",
        # "restore": "还原数据",
        # 所有数据库角色
        # "readAnyDatabase": "任意数据库读取",
        # "readWriteAnyDatabase": "任意数据库读取和写入",
        # "userAdminAnyDatabase": "任意数据库用户管理员",
        # "dbAdminAnyDatabase": "任意数据库管理员",
        # 超级用户角色
        # "root": "超级管理员",
        # 内部角色
        # "__queryableBackup": "可查询备份",
        # "__system": "系统角色",
        # "enableSharding": "启用分片",
    }

    try:
        client = mongdbClient()
        db = client.admin

        # 获取所有角色
        role_data = db.command('rolesInfo', showBuiltinRoles=True)
        result = []
        for role in role_data["roles"]:
            if mongo_role.get(role["role"]) is not None:
                role["name"] = mongo_role.get(role["role"])
                result.append(role)
    except Exception as ex:
        return yf.returnJson(False, '操作失败: ' + str(ex))
    return yf.returnJson(True, 'ok', result)

def getDbAccess():
    args = getArgs()
    data = checkArgs(args, ['username'])
    if not data[0]:
        return data[1]

    username = str(args['username']).strip()
    if not check_safe_name(username):
        return yf.returnJson(False, "安全拦截：非法数据库名！")

    mongo_role = {
        # 数据库用户角色
        "read": "读取数据(read)",
        "readWrite": "读取和写入数据(readWrite)",
        # 数据库管理角色
        # "dbAdmin": "数据库管理员",
        "dbOwner": "数据库所有者(dbOwner)",
        "userAdmin": "用户管理员(userAdmin)",
        # 集群管理角色
        # "clusterAdmin": "集群管理员",
        # "clusterManager": "集群管理器",
        # "clusterMonitor": "集群监视器",
        # "hostManager": "主机管理员",
        # 备份和恢复角色
        # "backup": "备份数据",
        # "restore": "还原数据",
        # 所有数据库角色
        # "readAnyDatabase": "任意数据库读取",
        # "readWriteAnyDatabase": "任意数据库读取和写入",
        # "userAdminAnyDatabase": "任意数据库用户管理员",
        # "dbAdminAnyDatabase": "任意数据库管理员",
        # 超级用户角色
        # "root": "超级管理员",
        # 内部角色
        # "__queryableBackup": "可查询备份",
        # "__system": "系统角色",
        # "enableSharding": "启用分片",
    }

    try:
        client = mongdbClient()
        db = client.admin
        role_data = db.command('rolesInfo', showBuiltinRoles=True)
        all_role_list = []
        for role in role_data["roles"]:
            if mongo_role.get(role["role"]) is not None:
                role["name"] = mongo_role.get(role["role"])
                all_role_list.append(role)

        result = {
            "user": username,
            "db": username,
            "roles": [],
            "all_roles":all_role_list,
        }

        user_data = db.command('usersInfo', username)
        if user_data:
            if len(user_data["users"]) != 0:
                user = user_data["users"][0]
                result["user"] = user.get("user", username)
                result["db"] = user.get("db", username)
                result["roles"] = user.get("roles", [])
    except Exception as ex:
        return yf.returnJson(False, '操作失败: ' + str(ex))

    return yf.returnJson(True, 'ok', result)

def setDbAccess():
    args = getArgs()
    data = checkArgs(args, ['username', 'select','name'])
    if not data[0]:
        return data[1]
    username = str(args['username']).strip()
    select = str(args['select'])
    name = str(args['name']).strip()

    if not check_safe_name(username) or not check_safe_name(name):
        return yf.returnJson(False, "安全拦截：非法数据库名！")

    # 角色白名单：历史实现把 select 直接 split 后原样送给 updateUser，
    # `select=root` 可把库用户提权成超级管理员。
    user_roles = []
    for role in select.split(','):
        role = role.strip()
        if role == '':
            continue
        if role not in _DB_ACCESS_ROLES:
            return yf.returnJson(False, '权限类型不合法!')
        user_roles.append({'role': role, 'db': name})
    if not user_roles:
        return yf.returnJson(False, '权限类型不合法!')

    mg_pass = pSqliteDb('config').where('id=?', (1,)).getField('mg_root')

    try:
        client = mongdbClient()
        db = client.admin
        try:
            db.command("updateUser", username, pwd=mg_pass, roles=user_roles)
        except Exception as e:
            _log.debug('[mongodb] setDbAccess updateUser 失败，回退 dropUser+createUser: %s', e)
            db.command('dropUser',username)
            db.command("createUser", username, pwd=mg_pass, roles=user_roles)
    except Exception as ex:
        return yf.returnJson(False, '设置失败: ' + str(ex))

    return yf.returnJson(True, '设置成功!')

def getReplConfigData():
    f = getServerDir()+'/repl.json'
    if os.path.exists(f):
        c = yf.readFile(f)
        try:
            data = json.loads(c)
        except Exception as _e:
            _log.debug('[mongodb] getReplConfigData 解析失败: %s', _e)
            data = None
        # 文件被写坏/被截断时不得把 JSONDecodeError 抛给上层（接口 500）
        if isinstance(data, dict):
            if not isinstance(data.get('nodes'), list):
                data['nodes'] = []
            if not isinstance(data.get('name'), str):
                data['name'] = ''
            return data
    t = {}
    t['name'] =  ''
    t['nodes'] = []
    yf.writeFile(f, yf.getJson(t))
    return t

def setReplConfigData(c):
    f = getServerDir()+'/repl.json'
    yf.writeFile(f, yf.getJson(c))
    return c

def getReplConfig():
    c = getReplConfigData()
    return yf.returnJson(True, 'ok!', c)

def replSetName():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = str(args['name']).strip()
    if not check_safe_name(name):
        return yf.returnJson(False, '副本名称不合法!')

    c = getReplConfigData()
    c['name'] =  name
    setReplConfigData(c)

    d = getConfigData()
    # 配置里没有 replication 段时历史实现 KeyError traceback
    d.setdefault('replication', {})
    d['replication']['replSetName'] = name
    setConfig(d)
    res = restart()
    if res != 'ok':
        return yf.returnJson(False, '设置失败: 服务未就绪(' + str(res) + ')')

    return yf.returnJson(True, '设置成功!')

def replSetNode():
    args = getArgs()
    data = checkArgs(args, ['node','priority','arbiterOnly','votes','idx'])
    if not data[0]:
        return data[1]

    c = getReplConfigData()
    nodes = c['nodes']
    add_node = str(args['node']).strip()
    # 节点形态校验：必须是 host:port（历史实现允许空串/垃圾串入库，
    # replInit 时整组初始化失败且无从排查）
    m = re.match(r'^([A-Za-z0-9_.\-]+):([0-9]{1,5})\Z', add_node)
    if not m or not (1 <= int(m.group(2)) <= 65535):
        return yf.returnJson(False, '节点格式不合法!')

    try:
        idx = int(str(args['idx']).strip())
        priority = int(str(args['priority']).strip())
        arbiterOnly = int(str(args['arbiterOnly']).strip())
        votes = int(str(args['votes']).strip())
    except Exception:
        return yf.returnJson(False, '参数不合法: 节点参数必须是数字')

    if priority<0 or priority>100:
        return yf.returnJson(False, 'priority应该在[0-100]之间!')
    if arbiterOnly not in (0, 1):
        return yf.returnJson(False, '参数不合法: arbiterOnly')
    if votes not in (0, 1):
        return yf.returnJson(False, '参数不合法: votes')

    # 编辑状态
    if idx>-1:
        # 越界 idx 不得回「编辑成功」（历史缺陷：静默什么也没改却报成功）
        if idx >= len(nodes):
            return yf.returnJson(False, '节点不存在!')
        for i in range(len(nodes)):
            if i != idx and nodes[i].get('host') == add_node:
                return yf.returnJson(False, add_node+',节点已经存在!')
        nodes[idx]['host'] = add_node
        nodes[idx]['priority'] = priority
        nodes[idx]['votes'] = votes
        nodes[idx]['arbiterOnly'] = arbiterOnly
        c['nodes'] = nodes
        setReplConfigData(c)
        return yf.returnJson(True, '编辑成功!')

    is_have = False
    for x in nodes:
        if x.get('host') == add_node:
            is_have = True

    if is_have:
        return yf.returnJson(False, add_node+',节点已经存在!')

    t = {}
    t['host'] = add_node
    t['priority'] = priority
    t['votes'] = votes
    t['arbiterOnly'] = arbiterOnly

    nodes.append(t)
    c['nodes'] = nodes
    setReplConfigData(c)
    return yf.returnJson(True, '添加成功!')


def delReplNode():
    args = getArgs()
    data = checkArgs(args, ['node'])
    if not data[0]:
        return data[1]

    c = getReplConfigData()
    nodes = c['nodes']
    del_node = str(args['node']).strip()

    filter_nodes = []
    for x in nodes:
        if x.get('host') != del_node:
            filter_nodes.append(x)

    # 不存在的节点不得回「删除成功」（历史缺陷：假成功，配置实际未变）
    if len(filter_nodes) == len(nodes):
        return yf.returnJson(False, '节点不存在!')

    c['nodes'] = filter_nodes
    setReplConfigData(c)

    return yf.returnJson(True, '删除节点'+del_node+'成功!')


def replInit():
    c = getReplConfigData()

    name = c['name']
    nodes = c['nodes']

    if name == '':
        return yf.returnJson(False, '副本名不能为空!')

    # d = getConfigData()
    # d['replication']['replSetName'] = name
    # setConfig(d)
    # restart()

    if len(nodes) == 0:
        return yf.returnJson(False, '节点不能为空!')

    cfg_node = []

    now_time_t = int(time.time())

    for x in range(len(nodes)):
        n = nodes[x]
        t = {}
        t['_id'] = x
        t['host'] = n['host']
        if 'priority' in n:
            t['priority'] = int(n['priority'])

        if 'votes' in n:
            t['votes'] = int(n['votes'])

        if 'arbiterOnly' in n and n['arbiterOnly'] == 1:
            t['arbiterOnly'] = True

        cfg_node.append(t)

    # print(cfg_node)
    # return yf.returnJson(False, '设置副本成功!')

    config = {
        '_id': name,
        'members': cfg_node
    }

    try:
        client = mongdbClient()
        client.admin.command('replSetInitiate',config)
    except Exception as e:
        err_msg = str(e)
        if getattr(e, 'code', None) == 23 or 'already initialized' in err_msg:
            config['version'] = int(now_time_t)
            try:
                client.admin.command('replSetReconfig',config,force=True,maxTimeMS=10)
            except Exception as re_err:
                return yf.returnJson(False, str(re_err))
            
            return yf.returnJson(True, '重置副本同步成功!')
        return yf.returnJson(False, str(e))

    return yf.returnJson(True, '设置副本初始化成功!')

def replClose():
    d = getConfigData()
    rep = d.get('replication')
    # 配置缺 replication 段时历史实现 KeyError traceback
    if isinstance(rep, dict) and 'replSetName' in rep:
        del rep['replSetName']
        setConfig(d)
        restart()

    res = restart()
    if res != 'ok':
        return yf.returnJson(False, '设置失败: 服务未就绪(' + str(res) + ')')

    return yf.returnJson(True, '关闭副本同步成功!')

def getDbBackupDir():
    """备份目录的唯一来源：必须与写入侧 scripts/backup.py 同源（yf.getBackupDir()）。

    历史缺陷：读取/删除侧硬编码 `yf.getFatherDir()+'/backup/database'`，用户改过
    备份目录后备份文件写进新目录、列表却永远读旧目录（与 B01/B02 同族）。
    """
    return yf.getBackupDir() + '/database'


def getDbImportDir():
    """外部导入目录（与 importDbExternal 的解压目录同源）。"""
    return yf.getBackupDir() + '/mongodb_import'


def getDbBackupListFunc(dbname=''):
    bkDir = getDbBackupDir()
    # 读取侧不得因备份目录不存在而抛 FileNotFoundError（getDbList 每行调一次，
    # 目录缺失时整页 500）；也不在读取路径上造目录，交给写入侧。
    if not os.path.exists(bkDir):
        return []
    blist = os.listdir(bkDir)
    r = []

    bname = 'mongodb_' + dbname
    blen = len(bname)
    for x in blist:
        fbstr = x[0:blen]
        if fbstr == bname:
            r.append(x)
    return r

def getDbBackupList():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    r = getDbBackupListFunc(str(args['name']))
    bkDir = getDbBackupDir()
    rr = []
    for x in range(0, len(r)):
        p = bkDir + '/' + r[x]
        data = {}
        data['name'] = r[x]

        rsize = os.path.getsize(p)
        data['size'] = yf.toSize(rsize)

        t = os.path.getctime(p)
        t = time.localtime(t)

        data['time'] = time.strftime('%Y-%m-%d %H:%M:%S', t)
        rr.append(data)

        data['file'] = p

    return yf.returnJson(True, 'ok', rr)

def getDbBackupImportList():

    bkImportDir = getDbImportDir()
    if not os.path.exists(bkImportDir):
        yf.makeDirs(bkImportDir)

    blist = os.listdir(bkImportDir)

    rr = []
    for x in range(0, len(blist)):
        name = blist[x]
        p = bkImportDir + '/' + name
        # 目录（如解压残留）不得当文件算大小：os.path.getsize 会 IsADirectoryError
        if not os.path.isfile(p):
            continue
        data = {}
        data['name'] = name

        rsize = os.path.getsize(p)
        data['size'] = yf.toSize(rsize)

        t = os.path.getctime(p)
        t = time.localtime(t)

        data['time'] = time.strftime('%Y-%m-%d %H:%M:%S', t)
        rr.append(data)

        data['file'] = p

    rdata = {
        "list": rr,
        "upload_dir": bkImportDir,
    }
    return yf.returnJson(True, 'ok', rdata)

def deleteDbBackup():
    args = getArgs()
    data = checkArgs(args, ['filename', 'path'])
    if not data[0]:
        return data[1]

    filename = str(args['filename'])
    # 文件名白名单（历史缺陷：path=/tmp&filename=任意文件 可以 root 删任意文件）
    if not _DB_BACKUP_FILE_RE.match(filename):
        return yf.returnJson(False, '备份文件名不合法!')

    path = str(args['path']).strip()
    allowed = [os.path.realpath(getDbBackupDir()), os.path.realpath(getDbImportDir())]
    if path == '':
        base = getDbBackupDir()
    else:
        real = os.path.realpath(path)
        if real not in allowed:
            return yf.returnJson(False, '备份目录不合法!')
        base = real

    full_file = os.path.join(base, filename)
    if os.path.realpath(os.path.dirname(full_file)) != os.path.realpath(base):
        return yf.returnJson(False, '备份文件名不合法!')
    if not os.path.exists(full_file):
        return yf.returnJson(False, '备份文件不存在!')
    try:
        os.remove(full_file)
    except Exception as ex:
        return yf.returnJson(False, '删除失败: ' + str(ex))
    return yf.returnJson(True, 'ok')

def setDbBackup():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = str(args['name']).strip()
    if not check_safe_name(name):
        return yf.returnJson(False, "安全拦截：非法数据库名！")

    scDir = getPluginDir() + '/scripts/backup.py'
    if not os.path.exists(scDir):
        return yf.returnJson(False, '数据库备份失败:' + name)

    import subprocess
    # 同步执行并判退出码/失败标记：历史实现 Popen 后立即回 'ok'，而脚本自身因
    # `os.chdir(yf.getPanelDir())` 写在 import 之前而 NameError 崩掉，备份从未发生
    # 也报「成功」（真机实测：set_db_backup 恒回 ok 且备份目录无新文件）。
    # 超时 540s 略低于 utils/plugin.py 的 600s 交互式上限，避免子进程把面板挂死。
    try:
        p = subprocess.Popen([sys.executable, scDir, 'database', name, '3'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate(timeout=540)
    except subprocess.TimeoutExpired:
        try:
            p.kill()
            p.communicate()
        except Exception as _e:
            _log.debug('[mongodb] setDbBackup 超时后清理失败: %s', _e)
        return yf.returnJson(False, '数据库备份失败:' + name)
    except Exception as e:
        return yf.returnJson(False, '启动备份任务失败: ' + str(e))

    out_s = (out or b'').decode('utf-8', 'replace')
    err_s = (err or b'').decode('utf-8', 'replace')
    if p.returncode != 0 or '备份失败' in out_s or '备份失败' in err_s:
        # 写面板文件日志（而不是 stderr）：utils/plugin.py::run() 把「非空 stderr」当成
        # 整个调用失败，会把这条诊断文本顶替掉返回给前端的真实提示。
        yf.writeFileLog('[mongodb] setDbBackup 失败 name=%s rc=%s err=%s' % (name, p.returncode, err_s[:300]))
        return yf.returnJson(False, '数据库备份失败:' + name)
    return yf.returnJson(True, 'ok')


def getListBson(dbname=''):
    bkDir = getDbImportDir() + '/' + dbname
    if not os.path.exists(bkDir):
        return []
    blist = os.listdir(bkDir)
    r = []

    bname = 'bson' 
    blen = len(bname)
    for x in blist:
        if x.endswith(bname):
            r.append(x)
    return r

def rootPwd():
    return pSqliteDb('config').where(
        'id=?', (1,)).getField('mg_root')

def importDbExternal():
    args = getArgs()
    data = checkArgs(args, ['file', 'name'])
    if not data[0]:
        return data[1]

    file = str(args['file'])
    name = str(args['name']).strip()

    # 安全检查：数据库名走白名单，文件名走白名单（挡 `..`/`/`/`\`/隐藏文件）
    if not check_safe_name(name) or not _DB_BACKUP_FILE_RE.match(file):
        return yf.returnJson(False, '安全拦截：非法数据库名或导入文件名！')

    import_dir = getDbImportDir() + '/'
    port = getConfPort()

    file_path = import_dir + file
    if not os.path.exists(file_path):
        return yf.returnJson(False, '文件突然消失?')

    exts = ['gz', 'tgz', 'zip']
    ext = yf.getFileSuffix(file)
    if ext not in exts:
        return yf.returnJson(False, '导入数据库格式不对!')

    auth = getConfAuth()
    mg_root = pSqliteDb('config').where('id=?', (1,)).getField('mg_root')

    file_dir = import_dir + name
    try:
        if not os.path.exists(file_dir):
            yf.makeDirs(file_dir)

        ok, err = _safeExtractTar(file_path, file_dir)
        if not ok:
            return yf.returnJson(False, '解压备份文件失败: ' + err)

        bson_list = getListBson(name)
        if len(bson_list) == 0:
            return yf.returnJson(False, '导入失败: 压缩包内未找到 .bson 文件')

        # mongorestore 的 --dir 是**目录**（解压目录本身就是 mongodump 的输出根），
        # 历史实现传 os.path.join(file_dir, x)（单个 .bson 文件）必然失败。
        restore_bin = getServerDir() + "/bin/mongorestore"
        import subprocess
        cmd = [restore_bin]
        if auth != 'disabled':
            cmd.extend(['--authenticationDatabase', 'admin', '-u', 'root', '-p', mg_root])
        cmd.extend(['--port', str(port), '--dir', file_dir])

        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = p.communicate()
            err_out = stderr.decode('utf-8', errors='ignore')
            if p.returncode != 0 or 'error' in err_out.lower():
                return yf.returnJson(False, '导入失败: ' + err_out)
        except Exception as e:
            return yf.returnJson(False, '执行导入命令时发生异常: ' + str(e))
    finally:
        # 删除临时目录（不论成败，避免在导入目录里留下解压残留）
        if os.path.exists(file_dir):
            import shutil
            try:
                shutil.rmtree(file_dir)
            except Exception as _e:
                _log.debug('[mongodb] importDbExternal 清理临时目录失败: %s', _e)

    return yf.returnJson(True, 'ok')


def importDbBackup():
    args = getArgs()
    data = checkArgs(args, ['file', 'name'])
    if not data[0]:
        return data[1]

    file = str(args['file'])
    name = str(args['name']).strip()

    # 安全检查（文件名白名单：挡 `..`/`/`/`\`/隐藏文件）
    if not check_safe_name(name) or not _DB_BACKUP_FILE_RE.match(file):
        return yf.returnJson(False, '安全拦截：非法数据库名或备份文件名！')

    port = getConfPort()

    backup_dir = getDbBackupDir() + '/'
    file_tgz = backup_dir + file
    file_dir = backup_dir + file.replace('.tar.gz', '')

    if not os.path.exists(file_tgz):
        return yf.returnJson(False, '备份文件不存在!')

    try:
        if not os.path.exists(file_dir):
            yf.makeDirs(file_dir)

        ok, err = _safeExtractTar(file_tgz, file_dir)
        if not ok:
            return yf.returnJson(False, '解压备份文件失败: ' + err)

        auth = getConfAuth()
        mg_root = pSqliteDb('config').where('id=?', (1,)).getField('mg_root')

        restore_bin = getServerDir() + "/bin/mongorestore"
        import subprocess

        cmd = [restore_bin]
        if auth != 'disabled':
            cmd.extend(['-u', 'root', '-p', mg_root])
        cmd.extend(['--port', str(port), '--dir', file_dir])

        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = p.communicate()
            err_out = stderr.decode('utf-8', errors='ignore')
            if p.returncode != 0:
                return yf.returnJson(False, '导入备份失败: ' + err_out)
        except Exception as e:
            return yf.returnJson(False, '执行导入备份发生异常: ' + str(e))
    finally:
        # 删除解压的临时目录（不论成败，避免在备份目录里留下解压残留）
        if os.path.exists(file_dir):
            import shutil
            try:
                shutil.rmtree(file_dir)
            except Exception as _e:
                _log.debug('[mongodb] importDbBackup 清理临时目录失败: %s', _e)

    return yf.returnJson(True, 'ok')

def testData():
    '''
    cd <面板目录> && source bin/activate && python3 plugins/mongodb/index.py test_data
    '''
    import pymongo
    from pymongo import ReadPreference
    
    client = mongdbClient()

    db = client.test
    col = db["demo"]

    rndStr = yf.getRandomString(10)
    insert_dict = { "name": "v1", "value": rndStr}
    x = col.insert_one(insert_dict)
    print(x)


def test():
    '''
    cd <面板目录> && python3 plugins/mongodb/index.py set_config_auth  {}
    cd <面板目录> && source bin/activate && python3 plugins/mongodb/index.py test
    python3 plugins/mongodb/index.py test
    '''
    # https://pymongo.readthedocs.io/en/stable/examples/high_availability.html
    # import pymongo
    # from pymongo import ReadPreference
    
    client = mongdbClient()
    db = client.admin

    mg_pass = yf.getRandomString(10)
    config = {
        '_id': 'test',
        'members': [
            {'_id': 0, 'host': '127.0.0.1:27019'},
            {'_id': 1, 'host': '127.0.0.1:27017'},
        ]
    }

    rsStatus = client.admin.command('replSetInitiate',config)
    print(rsStatus)

    # 需要通过命令行操作
    # rs.initiate({
    #     _id: 'test',
    #     members: [
    #     {
    #         _id: 1,
    #         host: '127.0.0.1:27019',
    #         priority: 2
    #     }, 
    #     {
    #         _id: 2,
    #         host: '127.0.0.1:27017',
    #         priority: 1
    #     }

    #     ]
    # });

    # > rs.status();  // 查询状态
    # // "stateStr" : "PRIMARY", 主节点
    # // "stateStr" : "SECONDARY", 副本节点

    # > rs.add({"_id":3, "host":"127.0.0.1:27318","priority":0,"votes":0});


    # serverStatus = db.command('serverStatus')
    # print(serverStatus)
    
    return yf.returnJson(True, 'OK')


def initdStatus():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    shell_cmd = 'systemctl status mongodb | grep loaded | grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    yf.execShell('systemctl enable mongodb')
    return 'ok'


def initdUinstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    yf.execShell('systemctl disable mongodb')
    return 'ok'


def runLog():
    try:
        d = getConfigData()
        f = d.get('systemLog', {}).get('path', '')
        if not f:
            f = getServerDir() + '/log/mongodb.log'
    except Exception:
        f = getServerDir() + '/log/mongodb.log'
        
    if os.path.exists(f):
        return f
        
    # 回退检查两个常见的默认路径
    fallback_1 = getServerDir() + '/logs/mongodb.log'
    if os.path.exists(fallback_1):
        return fallback_1
        
    return f

def cronAddCheck():
    try:
        import tool_task
        # 看返回结果：crontab.add() 失败时 createBgTask 会回 False，
        # 历史实现无条件回「添加检查任务成功」（假成功）。
        if not tool_task.createBgTask():
            return yf.returnJson(False, '添加检查任务失败:'+'写入计划任务失败')
        return yf.returnJson(True, '添加检查任务成功')
    except Exception as e:
        return yf.returnJson(False, '添加检查任务失败:'+str(e))

def cronDelCheck():
    try:
        import tool_task
        tool_task.removeBgTask()
        return yf.returnJson(True, '删除检查任务成功')
    except Exception as e:
        return yf.returnJson(False, '删除检查任务失败:'+str(e))


def installPreInspectionDebainCheck(sysId,version):
    if version == '8.0':
        try:
            sid = int(str(sysId).strip())
        except Exception:
            # VERSION_ID 不是纯数字（如 '12 (bookworm)'）时不得抛 ValueError
            return ''
        if sid < 12:
            return "[%s]需要至少debain[12]" % (version,)
    return ''

def installPreInspection(version):
    if yf.isAppleSystem():
        return 'ok'

    # 安全预检 CPU 的 AVX 指令集，避免 5.0+ 部署在无 AVX 系统上崩溃
    if version in ['5.0', '6.0', '7.0', '8.0', '8.2']:
        has_avx = False
        if os.path.exists('/proc/cpuinfo'):
            cpuinfo = yf.readFile('/proc/cpuinfo')
            if 'avx' in cpuinfo.lower():
                has_avx = True
        if not has_avx:
            return '预检失败：MongoDB ' + version + ' 强依赖 CPU 的 AVX 指令集，当前服务器 CPU 未检测到 AVX 标志，运行将导致 Illegal instruction 核心崩溃。建议安装 4.4 版本或升级服务器 CPU 环境。'

    cmd = "cat /etc/*-release | grep PRETTY_NAME |awk -F = '{print $2}' | awk -F '\"' '{print $2}'| awk '{print $1}'"
    sys = yf.execShell(cmd)

    if sys[1] != '':
        return '暂时不支持该系统'

    sys_id = yf.execShell("cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}' | awk -F '\"' '{print $2}'")

    sysName = sys[0].strip().lower()
    sysId = sys_id[0].strip()

    supportOs = ['centos', 'ubuntu', 'debian', 'opensuse']
    if not sysName in supportOs:
        return '暂时仅支持{}'.format(','.join(supportOs))

    if sysName == 'debian':
        check = installPreInspectionDebainCheck(sysId, version) 
        if check != '':
            return check

    return 'ok'

def uninstallPreInspection(version):
    stop()

    from utils.plugin import plugin as YfPlugin
    YfPlugin.instance().removeIndex(getPluginName(), version)

    return "强制删除会删除MongoDB[{}]数据目录<br/>  {}".format(version, getServerDir())

if __name__ == "__main__":
    func = sys.argv[1]

    version = '4.4'
    if (len(sys.argv) > 2):
        version = sys.argv[2]

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
        print(installPreInspection(version))
    elif func == 'uninstall_pre_inspection':
        print(uninstallPreInspection(version))
    elif func == 'initd_status':
        print(initdStatus())
    elif func == 'initd_install':
        print(initdInstall())
    elif func == 'initd_uninstall':
        print(initdUinstall())
    elif func == 'run_info':
        print(runInfo())
    elif func == 'run_doc_info':
        print(runDocInfo())
    elif func == 'run_repl_info':
        print(runReplInfo())
    elif func == 'conf':
        print(getConf())
    elif func == 'config_key':
        print(getConfKey())
    elif func == 'get_config':
        print(getConfig())
    elif func == 'set_config':
        print(saveConfig())
    elif func == 'set_config_auth':
        print(setConfigAuth())
    elif func == 'root_pwd':
        print(rootPwd())
    elif func == 'get_db_list':
        print(getDbList())
    elif func == 'add_db':
        print(addDb())
    elif func == 'del_db':
        print(delDb())
    elif func == 'del_db_table':
        print(delDbTable())
    elif func == 'set_root_pwd':
        print(setRootPwd())
    elif func == 'set_user_pwd':
        print(setUserPwd())
    elif func == 'sync_get_databases':
        print(syncGetDatabases())
    elif func == 'sync_to_databases':
        print(syncToDatabases())
    elif func == 'set_db_ps':
        print(setDbPs())
    elif func == 'get_db_info':
        print(getDbInfo())
    elif func == 'get_all_role':
        print(getAllRole())
    elif func == 'get_db_access':
        print(getDbAccess())
    elif func == 'set_db_access':
        print(setDbAccess())
    elif func == 'repl_set_name':
        print(replSetName())
    elif func == 'repl_set_node':
        print(replSetNode())
    elif func == 'get_repl_config':
        print(getReplConfig())
    elif func == 'del_repl_node':
        print(delReplNode())
    elif func == 'repl_init':
        print(replInit())
    elif func == 'repl_close':
        print(replClose())
    elif func == 'get_db_backup_list':
        print(getDbBackupList())
    elif func == 'get_db_backup_import_list':
        print(getDbBackupImportList())
    elif func == 'delete_db_backup':
        print(deleteDbBackup())
    elif func == 'set_db_backup':
        print(setDbBackup())
    elif func == 'import_db_external':
        print(importDbExternal())
    elif func == 'import_db_backup':
        print(importDbBackup())
    elif func == 'run_log':
        print(runLog())
    elif func == 'test':
        print(test())
    elif func == 'test_data':
        print(testData())
    elif func == 'cron_add_check':
        print(cronAddCheck())
    elif func == 'cron_del_check':
        print(cronDelCheck())
    else:
        print('error')
