# coding: utf-8


import time
import os
import sys
import re
import json
import subprocess

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import logging

_log = logging.getLogger('yf.gitea')

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'gitea'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getInitDFile():
    if app_debug:
        return '/tmp/' + getPluginName()
    return '/etc/init.d/' + getPluginName()


def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        val = args[0].strip()
        # 前端（YfPlugin.parseArgs）把参数序列化成 JSON 字符串，由 utils/plugin.py::run()
        # 作为**单个** argv 传入。旧实现只按 `k:v` 切第一段 → JSON 被整体塞进
        # tmp['"page"']，于是**所有带参接口恒回「缺少必要参数」**
        # （真机实测 /plugins/run user_project_list '{"name":"x"}' → 缺少参数name）。
        if val.startswith('{') and val.endswith('}'):
            try:
                data = json.loads(val)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                _log.debug('[gitea] getArgs JSON 解析失败: %s', e)
        t = val.strip('{').strip('}')
        if t.strip() == '':
            tmp = {}
        else:
            t = t.split(':', 1)
            if len(t) == 2:
                tmp[t[0].strip().strip('"').strip("'")] = t[1].strip().strip('"').strip("'")
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':', 1)
            if len(t) == 2:
                tmp[t[0].strip().strip('"').strip("'")] = t[1].strip().strip('"').strip("'")

    return tmp


# ---------------------------------------------------------------------------
# 用户名 / 项目名白名单
#
# user 与 name 都会被拼进服务器路径 `<ROOT>/<user>/<name>.git`（随后 makeDirs /
# writeFile / chmod / chown / deleteFile），也会进入 shell 命令。它们必须是
# **单一目录段**：允许 Gitea 合法命名（字母/数字/下划线/中划线/点），显式拒绝
# `.`、`..`、`/`、绝对路径、空格、控制字符与任何 shell 元字符。
# 旧实现只做存在性检查，真机实测 `user=../../tmp/yf_probe_D10/trav` 可在任意
# 目录以 root 建目录写脚本、`user=a;touch /tmp/yf_probe_D10/PWNED;#` 可直接
# 执行命令（root RCE）。
# ---------------------------------------------------------------------------
_OWNER_RE = re.compile(r'^[A-Za-z0-9_\-][A-Za-z0-9_.\-]{0,38}$')
_REPO_RE = re.compile(r'^[A-Za-z0-9_\-][A-Za-z0-9_.\-]{0,99}$')


def validOwner(value):
    v = str(value if value is not None else '').strip()
    if v in ('.', '..') or not _OWNER_RE.match(v):
        return None
    return v


def validRepo(value):
    v = str(value if value is not None else '').strip()
    if v in ('.', '..') or not _REPO_RE.match(v):
        return None
    return v


def ownerRepoOrError(args):
    """校验 user/name；返回 (user, repo, err)，err 非空时前两项为 None。"""
    user = validOwner(args.get('user'))
    repo = validRepo(args.get('name'))
    if not user or not repo:
        return None, None, yf.returnJson(False, '非法的用户名或项目名!')
    return user, repo, None


def repoRootOrError():
    """仓库根目录（app.ini 的 ROOT）；未安装初始化时返回 (None, 错误信封)。"""
    root = getRootPath()
    if not root:
        return None, yf.returnJson(False, "请先安装初始化，默认地址: http://" + yf.getLocalIp() + ":3000")
    return root, None


def pageArgs(args):
    """解析 page/page_size；非法返回 (None, None, 错误信封)。"""
    try:
        page = int(str(args.get('page', '1')).strip())
        page_size = int(str(args.get('page_size', '10')).strip())
    except Exception:
        return None, None, yf.returnJson(False, '分页参数不合法!')
    if page < 1 or page_size < 1:
        return None, None, yf.returnJson(False, '分页参数不合法!')
    if page_size > 500:
        page_size = 500
    return page, page_size, None


def safe_search_value(value):
    if not value:
        return ""
    # 仅保留汉字、英文字母、数字、下划线和中划线，彻底阻断任何 SQL 注入
    return re.sub(r"[^a-zA-Z0-9_\-\u4e00-\u9fa5]", "", str(value))


def safe_file_name(filename):
    if not filename:
        return None
    # 强制提取文件名，剥离所有目录前缀，彻底阻断目录穿越
    filename = os.path.basename(filename)
    # 强校验文件名是否仅包含安全字符，且不能是空或仅有点
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", filename) or filename in [".", ".."]:
        return None
    return filename


def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


def isInstalled():
    """是否已安装：以安装目录下的 gitea 二进制为准（info.json 的 checks/path）。"""
    return os.path.exists(getServerDir() + '/gitea')


def getGiteaBin():
    return getServerDir() + '/gitea'


def getGiteaPids():
    """精确找出 gitea 主进程：`comm == 'gitea'` 且可执行文件就是安装目录下的 gitea。

    旧实现 `ps -ef|grep gitea|grep -v grep|grep -v python` 是**子串匹配**：真机实测
    服务已 `systemctl stop` 后，一个无关进程 `exec -a yf-gitea-decoy sleep 300`
    就让 status() 假报 start。这里只认「进程名 + 可执行文件路径」双判据，零 fork。
    """
    bin_path = os.path.realpath(getGiteaBin())
    pids = []
    try:
        names = os.listdir(_PROC_ROOT)
    except Exception as e:
        _log.debug('[gitea] 读取 %s 失败: %s', _PROC_ROOT, e)
        return pids
    for name in names:
        if not name.isdigit():
            continue
        try:
            with open(os.path.join(_PROC_ROOT, name, 'comm'), 'r') as fp:
                comm = fp.read().strip()
        except Exception:
            continue
        if comm != 'gitea':
            continue
        try:
            exe = os.path.realpath(os.path.join(_PROC_ROOT, name, 'exe'))
        except Exception:
            exe = ''
        if exe == bin_path:
            pids.append(name)
    return pids


_UNIT_ENABLED_STATES = ('enabled', 'enabled-runtime', 'alias', 'static', 'indirect', 'generated')

# /proc 根路径。写成模块常量只为让「进程精确判据」能在非 Linux 环境（开发机/CI）
# 用夹具目录真跑（同 task_manager 的 _PROC_ROOT）。
_PROC_ROOT = '/proc'


def getInitdConfTpl():
    path = getPluginDir() + "/init.d/gitea.tpl"
    return path


def getInitdConf():
    path = getServerDir() + "/init.d/gitea"
    return path


def getConf():
    path = getServerDir() + "/custom/conf/app.ini"

    if not os.path.exists(path):
        # 后端消息契约：可翻译前缀必须是「纯文本 + 冒号」，HTML 不得进入前缀
        # （否则违反「译文禁含 HTML」红线，且首个冒号会落在 URL 里导致前缀匹配失败）。
        return yf.returnJson(False, "请先安装初始化，默认地址: http://" + yf.getLocalIp() + ":3000")
    return path


def getConfTpl():
    path = getPluginDir() + "/conf/app.ini"
    return path


def status():
    # 精确判据：安装目录下的 gitea 二进制进程（comm + exe 双匹配），零 fork。
    # 未安装 / 未运行 / 只有同名诱饵进程时一律如实回 stop。
    if getGiteaPids():
        return 'start'
    return 'stop'


def getHomeDir():
    if yf.isAppleSystem():
        user = yf.execShell(
            "who | sed -n '2, 1p' |awk '{print $1}'")[0].strip()
        return '/Users/' + user
    else:
        return '/home/www'


def getRunUser():
    if yf.isAppleSystem():
        user = yf.execShell(
            "who | sed -n '2, 1p' |awk '{print $1}'")[0].strip()
        return user
    else:
        return 'www'

__SR = '''#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
export USER=%s
export HOME=%s && ''' % ( getRunUser(), getHomeDir())


def contentReplace(content):

    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$RUN_USER}', getRunUser())
    content = content.replace('{$HOME_DIR}', getHomeDir())

    return content


def initDreplace():

    # 未安装不造任何产物（旧版会建目录/写 init 脚本/写 systemd unit，
    # unit 的 ExecStart 指向不存在的二进制）。
    if not isInstalled():
        return ''

    file_tpl = getInitdConfTpl()
    service_path = yf.getServerDir()

    git_dir = yf.getServerDir() + '/git'
    if not os.path.exists(git_dir):
        yf.makeDirs(git_dir)
        yf.execShell('chown -R www:www ' + yf.shlexQuote(git_dir))


    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        yf.makeDirs(initD_path)
    file_bin = initD_path + '/' + getPluginName()

    if not os.path.exists(file_bin):
        content = yf.readFile(file_tpl)
        if content:
            content = contentReplace(content)
            yf.writeFile(file_bin, content)
            yf.execShell('chmod +x ' + yf.shlexQuote(file_bin))

    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/gitea.service'
    systemServiceTpl = getPluginDir() + '/init.d/gitea.service.tpl'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        service_path = yf.getServerDir()
        se_content = yf.readFile(systemServiceTpl)
        if se_content:
            se_content = se_content.replace('{$SERVER_PATH}', service_path)
            yf.writeFile(systemService, se_content)
            yf.execShell('systemctl daemon-reload')

    log_path = getServerDir() + '/log'
    if not os.path.exists(log_path):
        yf.makeDirs(log_path)

    return file_bin


def getRootUrl():
    conf_path = getServerDir() + "/custom/conf/app.ini"
    if not os.path.exists(conf_path):
        return ''
    content = yf.readFile(conf_path)
    if not content: return ''
    rep = r'ROOT_URL\s*=\s*(.*)'
    tmp = re.search(rep, content)
    if tmp:
        return tmp.groups()[0]

    rep = r'EXTERNAL_URL\s*=\s*(.*)'
    tmp = re.search(rep, content)
    if tmp:
        return tmp.groups()[0]
    return ''


def getSshPort():
    conf_path = getServerDir() + "/custom/conf/app.ini"
    if not os.path.exists(conf_path):
        return ''
    content = yf.readFile(conf_path)
    if not content: return ''
    rep = r'SSH_PORT\s*=\s*(.*)'
    tmp = re.search(rep, content)
    if not tmp:
        return ''
    return tmp.groups()[0]


def getHttpPort():
    conf_path = getServerDir() + "/custom/conf/app.ini"
    if not os.path.exists(conf_path):
        return ''
    content = yf.readFile(conf_path)
    if not content: return ''
    rep = r'HTTP_PORT\s*=\s*(.*)'
    tmp = re.search(rep, content)
    if not tmp:
        return ''
    return tmp.groups()[0]


def getRootPath():
    conf_path = getServerDir() + "/custom/conf/app.ini"
    if not os.path.exists(conf_path):
        return ''
    content = yf.readFile(conf_path)
    if not content: return ''
    rep = r'ROOT\s*=\s*(.*)'
    tmp = re.search(rep, content)
    if not tmp:
        return ''
    return tmp.groups()[0].strip()


def getAccessUrl():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception as _e:
        _log.debug('[gitea] getAccessUrl 异常已忽略: %s', _e)
        lan_ip = '127.0.0.1'

    wan_ip = yf.getHostAddr()
    port = getHttpPort()
    
    if not port:
        port = '3000'

    data = {
        'lan': 'http://' + lan_ip + ':' + port,
        'wan': 'http://' + wan_ip + ':' + port
    }
    return yf.returnJson(True, 'OK', data)


def getDbConfValue():
    conf = getConf()
    if not os.path.exists(conf):
        return {}

    content = yf.readFile(conf)
    if not content:
        return {}
    rep_scope = r"\[database\](.*?)\["
    tmp = re.findall(rep_scope, content, re.S)
    if not tmp:
        # app.ini 无 [database] 段（损坏/未初始化完成）：旧实现 tmp[0] 直接 IndexError
        return {}

    rep = '(\\w*)\\s*=\\s*(.*)'
    tmp = re.findall(rep, tmp[0])
    r = {}
    for x in range(len(tmp)):
        k = tmp[x][0]
        v = tmp[x][1]
        r[k] = v
    return r


def pMysqlDb(conf):
    for k in ('HOST', 'USER', 'NAME'):
        if not conf.get(k):
            _log.debug('[gitea] app.ini [database] 缺少 %s', k)
            return None
    if not conf.get('PASSWD') and not conf.get('PASSWORD'):
        _log.debug('[gitea] app.ini [database] 缺少口令字段')
        return None
    host = conf['HOST'].split(':')
    if len(host) < 2 or not host[1].strip().isdigit():
        _log.debug('[gitea] app.ini [database] HOST 格式异常: %r', conf['HOST'])
        return None
    # pymysql
    db = yf.getMyORM()
    # MySQLdb |
    # db = yf.getMyORMDb()

    db.setPort(int(host[1]))
    db.setUser(conf['USER'])

    if 'PASSWD' in conf:
        db.setPwd(conf['PASSWD'])
    else:
        db.setPwd(conf['PASSWORD'])

    db.setDbName(conf['NAME'])
    # db.setSocket(getSocketFile())
    db.setCharset("utf8")
    return db


def pSqliteDb(conf):
    # print(conf)
    import db
    psDb = db.Sql()

    if not conf.get('PATH'):
        _log.debug('[gitea] app.ini [database] 缺少 PATH')
        return None

    # 默认
    gsdir = getServerDir() + '/data'
    dbname = 'gitea'
    if conf['PATH'][0] == '/':
        # 绝对路径
        pass
    else:
        path = conf['PATH'].split('/')
        if len(path) < 2:
            _log.debug('[gitea] app.ini [database] PATH 格式异常: %r', conf['PATH'])
            return None
        gsdir = getServerDir() + '/' + path[0]
        dbname = path[1].split('.')[0]

    # print(gsdir, dbname)
    psDb.dbPos(gsdir, dbname)
    return psDb


def getGiteaDbType(conf):

    if 'DB_TYPE' in conf:
        return conf['DB_TYPE']

    if 'TYPE' in conf:
        return conf['TYPE']

    return 'NONE'


def pQuery(sql):
    """执行查询；数据库类型不受支持/配置读不到时返回 None（调用方如实报错）。

    旧实现在这里 `print(...)` 后 `exit(0)` —— 插件子进程以**退出码 0** 结束、
    且 stdout 不是 JSON，真机实测 `get_total_statistics` 回「仅支持mysql|sqlite3配置」
    而面板侧因 JSON 解析失败报错（假成功 + 非契约输出）。
    """
    conf = getDbConfValue()
    gtype = getGiteaDbType(conf)
    if gtype == 'sqlite3':
        db = pSqliteDb(conf)
        if db is None:
            return None
        data = db.query(sql, []).fetchall()
        return data
    elif gtype == 'mysql':
        db = pMysqlDb(conf)
        if db is None:
            return None
        return db.query(sql)

    _log.debug('[gitea] 不支持的数据库类型: %s', gtype)
    return None


def isSqlError(mysqlMsg):
    # 检测数据库执行错误
    _mysqlMsg = str(mysqlMsg)
    # print _mysqlMsg
    if "MySQLdb" in _mysqlMsg:
        return yf.returnData(False, 'MySQLdb组件缺失! <br>进入SSH命令行输入： pip install mysql-python')
    if "2002," in _mysqlMsg:
        return yf.returnData(False, '数据库连接失败,请检查数据库服务是否启动!')
    if "using password:" in _mysqlMsg:
        return yf.returnData(False, '数据库管理密码错误!')
    if "Connection refused" in _mysqlMsg:
        return yf.returnData(False, '数据库连接失败,请检查数据库服务是否启动!')
    if "1133," in _mysqlMsg:
        return yf.returnData(False, '数据库用户不存在!')
    if "1007," in _mysqlMsg:
        return yf.returnData(False, '数据库已经存在!')
    if "1044," in _mysqlMsg:
        return yf.returnData(False, mysqlMsg[1])
    if "2003," in _mysqlMsg:
        return yf.returnData(False, "Can't connect to MySQL server on '127.0.0.1' (61)")
    return yf.returnData(True, 'OK')


def appOp(method):
    if not isInstalled():
        # 未安装：不造 unit/init 脚本、不调 systemctl，如实报失败
        _log.debug('[gitea] %s 被拒：未安装', method)
        return 'fail'

    file = initDreplace()

    if not yf.isAppleSystem():
        rc, out, err = yf.execShellRc('systemctl ' + method + ' ' + getPluginName(), timeout=120)
        if rc != 0:
            # 旧实现只看 stderr 是否为空：systemctl 失败但输出在 stdout 时会被吞成成功
            _log.debug('[gitea] systemctl %s 失败: %s', method, (err or out).strip())
            return 'fail'
        # 启/停/重启后回读真实进程，杜绝「命令返回 0 但服务没起来」的假成功
        if method in ('start', 'restart', 'reload'):
            want = 'start'
        else:
            want = 'stop'
        for _ in range(10):
            if status() == want:
                return 'ok'
            time.sleep(0.5)
        _log.debug('[gitea] %s 后状态未就绪', method)
        return 'fail'

    data = yf.execShell(__SR + file + ' ' + method)
    if data[1] == '':
        return 'ok'
    return data[0]


def start():
    return appOp('start')


def stop():
    return appOp('stop')


def restart():
    return appOp('restart')


def reload():
    return appOp('reload')


def initdStatus():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    if not isInstalled():
        return 'fail'

    # `systemctl status | grep loaded | grep "enabled;"` 依赖人类可读输出：
    # SysV 生成的单元显示 `generated`（无 `enabled;`）→ 已启用被误判 fail；
    # 改用 `is-enabled` 的退出码 + 状态白名单。
    rc, out, _err = yf.execShellRc(['systemctl', 'is-enabled', getPluginName()], shell=False, timeout=15)
    if rc != 0:
        return 'fail'
    if (out or '').strip() in _UNIT_ENABLED_STATES:
        return 'ok'
    return 'fail'


def initdInstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    if not isInstalled():
        return 'fail'

    # 旧实现无条件回 ok：单元不存在 / systemctl 失败时也报「已开启」
    rc, out, err = yf.execShellRc(['systemctl', 'enable', getPluginName()], shell=False, timeout=30)
    if rc != 0:
        _log.debug('[gitea] enable 失败: %s', (err or out).strip())
        return 'fail'
    return 'ok'


def initdUinstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    if not isInstalled():
        return 'fail'

    rc, out, err = yf.execShellRc(['systemctl', 'disable', getPluginName()], shell=False, timeout=30)
    if rc != 0:
        _log.debug('[gitea] disable 失败: %s', (err or out).strip())
        return 'fail'
    return 'ok'


def runLog():
    log_path = getServerDir() + '/log/gitea.log'
    return log_path


def postReceiveLog():
    log_path = getServerDir() + '/log/hooks/post-receive.log'
    return log_path


def getGogsConf():
    conf = getConf()
    if not os.path.exists(conf):
        return yf.returnJson(False, "请先安装初始化，默认地址: http://" + yf.getLocalIp() + ":3000")

    gets = [
        {'name': 'DOMAIN', 'type': -1, 'ps': '服务器域名'},
        {'name': 'ROOT_URL', 'type': -1, 'ps': '公开的完整URL路径'},
        {'name': 'HTTP_ADDR', 'type': -1, 'ps': '应用HTTP监听地址'},
        {'name': 'HTTP_PORT', 'type': -1, 'ps': '应用 HTTP 监听端口号'},

        {'name': 'START_SSH_SERVER', 'type': 2, 'ps': '启动内置SSH服务器'},
        {'name': 'SSH_PORT', 'type': -1, 'ps': 'SSH 端口号'},

        {'name': 'REQUIRE_SIGNIN_VIEW', 'type': 2, 'ps': '强制登录浏览'},
        {'name': 'ENABLE_CAPTCHA', 'type': 2, 'ps': '启用验证码服务'},
        {'name': 'DISABLE_REGISTRATION', 'type': 2, 'ps': '禁止注册,只能由管理员创建帐号'},
        {'name': 'ENABLE_NOTIFY_MAIL', 'type': 2, 'ps': '是否开启邮件通知'},

        {'name': 'FORCE_PRIVATE', 'type': 2, 'ps': '强制要求所有新建的仓库都是私有'},

        {'name': 'SHOW_FOOTER_BRANDING', 'type': 2, 'ps': 'Gitea推广信息'},
        {'name': 'SHOW_FOOTER_VERSION', 'type': 2, 'ps': 'Gitea版本信息'},
        {'name': 'SHOW_FOOTER_TEMPLATE_LOAD_TIME', 'type': 2, 'ps': 'Gitea模板加载时间'},
    ]
    conf = yf.readFile(conf)
    if not conf:
        return yf.returnJson(False, '配置文件读取失败!')
    result = []

    for g in gets:
        rep = g['name'] + '\\s*=\\s*(.*)'
        tmp = re.search(rep, conf)
        if not tmp:
            continue
        g['value'] = tmp.groups()[0]
        result.append(g)
    return yf.returnJson(True, 'OK', result)


def submitGogsConf():
    gets = ['DOMAIN',
            'ROOT_URL',
            'HTTP_ADDR',
            'HTTP_PORT',
            'START_SSH_SERVER',
            'SSH_PORT',
            'REQUIRE_SIGNIN_VIEW',
            'FORCE_PRIVATE',
            'ENABLE_CAPTCHA',
            'DISABLE_REGISTRATION',
            'ENABLE_NOTIFY_MAIL',
            'SHOW_FOOTER_BRANDING',
            'SHOW_FOOTER_VERSION',
            'SHOW_FOOTER_TEMPLATE_LOAD_TIME']
    args = getArgs()
    filename = getConf()
    if not os.path.exists(filename):
        return yf.returnJson(False, "请先安装初始化，默认地址: http://" + yf.getLocalIp() + ":3000")
    conf = yf.readFile(filename)
    if not conf:
        return yf.returnJson(False, '配置文件读取失败!')

    # 值会直接写回 app.ini。拒绝换行/回车：否则可通过值注入新的配置行/段
    # （如 `false\n[server]\nROOT_URL = http://evil`）。同时用 lambda 做替换，
    # 避免 re.sub 把值里的 `\1` / `\g<0>` 当反向引用解析。
    for g in gets:
        if g in args:
            val = args[g]
            if not isinstance(val, str):
                val = str(val)
            if '\n' in val or '\r' in val:
                return yf.returnJson(False, '配置值不合法!')
            rep = g + '\\s*=\\s*(.*)'
            line = g + ' = ' + val
            conf = re.sub(rep, lambda _m, _v=line: _v, conf)
    if not yf.writeFile(filename, conf):
        return yf.returnJson(False, '配置文件读取失败!')
    restart()
    return yf.returnJson(True, '设置成功')


def gogsEditTpl():
    data = {}
    data['post_receive'] = getPluginDir() + '/hook/post-receive.tpl'
    data['commit'] = getPluginDir() + '/hook/commit.tpl'
    return yf.getJson(data)


def userList():

    conf = getConf()
    if not os.path.exists(conf):
        return yf.returnJson(False, "请先安装初始化，默认地址: http://" + yf.getLocalIp() + ":3000")

    conf = getDbConfValue()
    gtype = getGiteaDbType(conf)
    if gtype != 'mysql':
        return yf.returnJson(False, "仅支持mysql数据操作!")

    import math
    args = getArgs()

    data = checkArgs(args, ['page', 'page_size'])
    if not data[0]:
        return data[1]

    page, page_size, err = pageArgs(args)
    if err:
        return err
    search = ''
    if 'search' in args:
        search = safe_search_value(args['search'])

    user_where1 = ''
    user_where2 = ''
    if search != '':
        user_where1 = ' where name like "%' + search + '%"'
        user_where2 = ' where name like "%' + search + '%"'

    data = {}

    data['root_url'] = getRootUrl()

    start = (page - 1) * page_size
    list_count = pQuery('select count(id) as num from user' + user_where1)
    if not list_count:
        return yf.returnJson(False, '仅支持mysql|sqlite3配置')
    count = list_count[0]["num"]
    list_data = pQuery(
        'select id,name,email from user ' + user_where2 + ' order by id desc limit ' + str(start) + ',' + str(page_size))
    data['list'] = yf.getPage({'count': count, 'p': page,
                               'row': page_size, 'tojs': 'gogsUserList'})
    data['page'] = page
    data['page_size'] = page_size
    data['page_count'] = int(math.ceil(count / page_size))
    data['data'] = list_data
    return yf.returnJson(True, 'OK', data)


def checkRepoListIsHasScript(data):
    path = getRootPath()
    for x in range(len(data)):
        # 名字来自 Gitea 数据库，同样只当单段路径用；非法就当作无脚本
        user = validOwner(data[x]['name'])
        repo = validRepo(data[x]['repo'])
        data[x]['has_hook'] = False
        if not path or not user or not repo:
            continue
        path_tmp = path + '/' + user + '/' + repo + '.git/custom_hooks/commit'
        if os.path.exists(path_tmp):
            data[x]['has_hook'] = True
    return data


def repoList():

    conf = getConf()
    if not os.path.exists(conf):
        return yf.returnJson(False, "请先安装初始化，默认地址: http://" + yf.getLocalIp() + ":3000")

    conf = getDbConfValue()
    gtype = getGiteaDbType(conf)
    if gtype != 'mysql':
        return yf.returnJson(False, "仅支持mysql数据操作!")

    import math
    args = getArgs()

    data = checkArgs(args, ['page', 'page_size'])
    if not data[0]:
        return data[1]

    page, page_size, err = pageArgs(args)
    if err:
        return err
    search = ''
    if 'search' in args:
        search = safe_search_value(args['search'])

    data = {}

    data['root_url'] = getRootUrl()

    repo_where1 = ''
    repo_where2 = ''
    if search != '':
        repo_where1 = ' where name like "%' + search + '%"'
        repo_where2 = ' where r.name like "%' + search + '%"'

    start = (page - 1) * page_size
    list_count = pQuery(
        'select count(id) as num from repository' + repo_where1)
    if not list_count:
        return yf.returnJson(False, '仅支持mysql|sqlite3配置')
    count = list_count[0]["num"]
    sql = 'select r.id,r.owner_id,r.name as repo, u.name from repository r left join user u on r.owner_id=u.id ' + repo_where2 + ' order by r.id desc limit ' + \
        str(start) + ',' + str(page_size)
    # print(sql)
    list_data = pQuery(sql)
    # print(list_data)
    list_data = checkRepoListIsHasScript(list_data)

    data['list'] = yf.getPage({'count': count, 'p': page,
                               'row': page_size, 'tojs': 'gogsRepoListPage'})
    data['page'] = page
    data['page_size'] = page_size
    data['page_count'] = int(math.ceil(count / page_size))
    data['data'] = list_data
    return yf.returnJson(True, 'OK', data)


def getAllUserProject(user, search=''):
    root, err = repoRootOrError()
    if err:
        return []
    path = root + '/' + user
    dlist = []
    if os.path.exists(path):
        try:
            names = os.listdir(path)
        except Exception as e:
            _log.debug('[gitea] 读取项目目录失败: %s', e)
            return dlist
        for filename in names:
            tmp = {}
            filePath = path + '/' + filename
            if os.path.isdir(filePath):
                if search == '':
                    tmp['name'] = filename.replace('.git', '')
                    dlist.append(tmp)
                else:
                    if filename.find(search) != -1:
                        tmp['name'] = filename.replace('.git', '')
                        dlist.append(tmp)
    return dlist


def checkProjectListIsHasScript(user, data):
    root = getRootPath()
    path = root + '/' + user
    for x in range(len(data)):
        name = data[x]['name'] + '.git'
        path_tmp = path + '/' + name + '/hooks/post-receive.d/post-receive'
        if os.path.exists(path_tmp):
            data[x]['has_hook'] = True
        else:
            data[x]['has_hook'] = False
    return data


def userProjectList():
    import math
    args = getArgs()

    if not 'name' in args:
        return yf.returnJson(False, '缺少参数name')

    user = validOwner(args['name'])
    if not user:
        return yf.returnJson(False, '非法的用户名或项目名!')

    root, err = repoRootOrError()
    if err:
        return err

    page, page_size, err = pageArgs({'page': args.get('page', '1'),
                                     'page_size': args.get('page_size', '5')})
    if err:
        return err
    search = ''
    if 'search' in args:
        search = str(args['search'])

    data = {}

    ulist = getAllUserProject(user, search)
    dlist_sum = len(ulist)

    start = (page - 1) * page_size
    ret_data = ulist[start:start + page_size]
    ret_data = checkProjectListIsHasScript(user, ret_data)

    data['root_url'] = getRootUrl()
    data['data'] = ret_data
    data['args'] = args
    data['list'] = yf.getPage(
        {'count': dlist_sum, 'p': page, 'row': page_size, 'tojs': 'userProjectListPost'})

    return yf.returnJson(True, 'OK', data)


def projectScriptEdit():
    args = getArgs()

    user, repo, err = ownerRepoOrError(args)
    if err:
        return err
    root, err = repoRootOrError()
    if err:
        return err

    post_receive = root + '/' + user + '/' + repo + '.git/custom_hooks/commit'
    if os.path.exists(post_receive):
        return yf.returnJson(True, 'OK', {'path': post_receive})
    else:
        return yf.returnJson(False, 'file does not exist')


def projectScriptLoad():
    args = getArgs()
    data = checkArgs(args, ['user', 'name'])
    if not data[0]:
        return data[1]

    user, repo, err = ownerRepoOrError(args)
    if err:
        return '非法的用户名或项目名!'
    root, err = repoRootOrError()
    if err:
        return '请先安装初始化!'

    path = root + '/' + user + '/' + repo + '.git'
    post_receive_tpl = getPluginDir() + '/hook/post-receive.tpl'
    post_receive = path + '/hooks/post-receive.d/post-receive'

    if not os.path.exists(path + '/custom_hooks'):
        yf.makeDirs(path + '/custom_hooks')
        yf.execShell('chown -R www:www ' + yf.shlexQuote(path + '/custom_hooks'))

    pct_content = yf.readFile(post_receive_tpl)
    if not pct_content:
        # readFile 失败返回 False（不是空串），旧实现直接 .replace() → AttributeError
        return '模板文件读取失败!'
    pct_content = pct_content.replace('{$PATH}', path + '/custom_hooks')
    if not yf.writeFile(post_receive, pct_content):
        return '脚本写入失败!'
    # 755：该脚本在 git push 时以 www 身份执行，777 等于任何本地用户都能改写它（本地提权）
    yf.execShell('chmod 755 ' + yf.shlexQuote(post_receive))
    yf.execShell('chown -R www:www ' + yf.shlexQuote(post_receive))

    commit_tpl = getPluginDir() + '/hook/commit.tpl'
    commit = path + '/custom_hooks/commit'

    codeDir = yf.getFatherDir() + '/git'

    cc_content = yf.readFile(commit_tpl)
    if not cc_content:
        return '模板文件读取失败!'

    gitPath = root
    cc_content = cc_content.replace('{$GITROOTURL}', gitPath)
    cc_content = cc_content.replace('{$CODE_DIR}', codeDir)
    cc_content = cc_content.replace('{$USERNAME}', user)
    cc_content = cc_content.replace('{$PROJECT}', repo)
    cc_content = cc_content.replace('{$WEB_ROOT}', yf.getWwwDir())
    if not yf.writeFile(commit, cc_content):
        return '脚本写入失败!'
    yf.execShell('chmod 755 ' + yf.shlexQuote(commit))
    yf.execShell('chown -R www:www ' + yf.shlexQuote(commit))

    return 'ok'


def projectScriptUnload():
    args = getArgs()
    data = checkArgs(args, ['user', 'name'])
    if not data[0]:
        return data[1]

    user, repo, err = ownerRepoOrError(args)
    if err:
        return '非法的用户名或项目名!'
    root, err = repoRootOrError()
    if err:
        return '请先安装初始化!'

    post_receive = root + '/' + user + '/' + repo + '.git/hooks/post-receive.d/post-receive'
    yf.deleteFile(post_receive)

    commit = root + '/' + user + '/' + repo + '.git/custom_hooks/commit'
    yf.deleteFile(commit)
    return 'ok'


def projectScriptDebug():
    args = getArgs()
    data = checkArgs(args, ['user', 'name'])
    if not data[0]:
        return data[1]

    user, repo, err = ownerRepoOrError(args)
    if err:
        return err
    root, err = repoRootOrError()
    if err:
        return err

    commit_log = root + '/' + user + '/' + repo + '.git/custom_hooks/sh.log'

    data = {}
    if os.path.exists(commit_log):
        data['status'] = True
        data['path'] = commit_log
    else:
        data['status'] = False
        data['msg'] = '没有日志文件'

    return yf.getJson(data)


def projectScriptRun():
    args = getArgs()
    data = checkArgs(args, ['user', 'name'])
    if not data[0]:
        return data[1]

    user, repo, err = ownerRepoOrError(args)
    if err:
        return err
    root, err = repoRootOrError()
    if err:
        return err

    path = root + '/' + user + '/' + repo + '.git'
    commit_sh = path + '/custom_hooks/commit'
    commit_log = path + '/custom_hooks/sh.log'
    if not os.path.exists(commit_sh):
        return yf.returnJson(False, '脚本文件不存在!')

    repo_dir = yf.getServerDir() + '/git/' + repo

    try:
        with open(commit_log, 'w') as err_log:
            subprocess.Popen(['sh', '-x', commit_sh], stdout=subprocess.PIPE, stderr=err_log, shell=False, bufsize=4096)
    except Exception as e:
        _log.debug('[gitea] projectScriptRun 异常已忽略: %s', e)
    subprocess.Popen(['chown', '-R', 'www:www', repo_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, bufsize=4096)
    return yf.returnJson(True, '脚本文件执行成功,观察日志!')


def projectScriptSelf():
    args = getArgs()
    data = checkArgs(args, ['user', 'name'])
    if not data[0]:
        return data[1]

    user, repo, err = ownerRepoOrError(args)
    if err:
        return err
    root, err = repoRootOrError()
    if err:
        return err

    custom_hooks = root + '/' + user + '/' + repo + '.git/custom_hooks'

    self_path = custom_hooks + '/self'
    if not os.path.exists(self_path):
        yf.makeDirs(self_path)
        yf.execShell("chown -R www:www " + yf.shlexQuote(self_path))

    self_logs_path = custom_hooks + '/self_logs'
    if not os.path.exists(self_logs_path):
        yf.makeDirs(self_logs_path)
        yf.execShell("chown -R www:www " + yf.shlexQuote(self_logs_path))

    self_hook_file = custom_hooks + '/self_hook.sh'
    self_hook_exist = False
    if os.path.exists(self_hook_file):
        self_hook_exist = True

    dlist = []
    if os.path.exists(self_path):
        for filename in os.listdir(self_path):
            tmp = {}
            filePath = self_path + '/' + filename
            if os.path.isfile(filePath):
                tmp['path'] = filePath
                tmp['name'] = os.path.basename(filePath)
                tmp['is_hidden'] = False
                if tmp['name'].endswith('.txt'):
                    tmp['is_hidden'] = True

                dlist.append(tmp)

    dlist_sum = len(dlist)
    rdata = {}
    rdata['data'] = dlist
    rdata['self_hook'] = self_hook_exist
    rdata['list'] = yf.getPage(
        {'count': dlist_sum, 'p': 1, 'row': 100, 'tojs': 'self_page'})

    return yf.returnJson(True, 'ok', rdata)


def projectScriptSelf_Create():
    args = getArgs()
    data = checkArgs(args, ['user', 'name', 'file'])
    if not data[0]:
        return data[1]

    user, repo, err = ownerRepoOrError(args)
    if err:
        return err
    root, err = repoRootOrError()
    if err:
        return err
    file = safe_file_name(args['file'])
    if not file:
        return yf.returnJson(False, '非法的文件名!')

    if not file.endswith('.sh'):
        file = file + '.sh'

    self_path = root + '/' + user + '/' + repo + '.git/custom_hooks/self'

    if not os.path.exists(self_path):
        yf.makeDirs(self_path)

    abs_file = self_path + '/' + file
    if os.path.exists(abs_file):
        return yf.returnJson(False, '脚本已经存在!')

    if not yf.writeFile(abs_file, "#!/bin/bash\necho `date +'%Y-%m-%d %H:%M:%S'`\n"):
        return yf.returnJson(False, '脚本写入失败!')
    yf.execShell('chown -R www:www ' + yf.shlexQuote(abs_file))
    rdata = {}
    rdata['abs_file'] = abs_file
    return yf.returnJson(True, '创建文件成功!', rdata)


def projectScriptSelf_Del():
    args = getArgs()
    data = checkArgs(args, ['user', 'name', 'file'])
    if not data[0]:
        return data[1]

    user, repo, err = ownerRepoOrError(args)
    if err:
        return err
    root, err = repoRootOrError()
    if err:
        return err
    file = safe_file_name(args['file'])
    if not file:
        return yf.returnJson(False, '非法的文件名!')

    custom_hooks = root + '/' + user + '/' + repo + '.git/custom_hooks'
    self_path = custom_hooks + '/self'

    abs_file = self_path + '/' + file
    if not os.path.exists(abs_file):
        return yf.returnJson(False, '脚本已经删除!')

    os.remove(abs_file)

    # 日志也删除
    log_file = custom_hooks + '/self_logs/' + file + '.log'
    if os.path.exists(log_file):
        os.remove(log_file)

    return yf.returnJson(True, '脚本删除成功!')


def projectScriptSelf_Logs():
    args = getArgs()
    data = checkArgs(args, ['user', 'name', 'file'])
    if not data[0]:
        return data[1]

    user, repo, err = ownerRepoOrError(args)
    if err:
        return err
    root, err = repoRootOrError()
    if err:
        return err
    file = safe_file_name(args['file'])
    if not file:
        return yf.returnJson(False, '非法的文件名!')

    self_path = root + '/' + user + '/' + repo + '.git/custom_hooks/self_logs'

    if not os.path.exists(self_path):
        yf.makeDirs(self_path)

    logs_file = self_path + '/' + file + '.log'
    if os.path.exists(logs_file):
        rdata = {}
        rdata['path'] = logs_file
        return yf.returnJson(True, 'ok', rdata)

    return yf.returnJson(False, '日志不存在!')


def projectScriptSelf_Run():
    args = getArgs()
    data = checkArgs(args, ['user', 'name', 'file'])
    if not data[0]:
        return data[1]

    user, repo, err = ownerRepoOrError(args)
    if err:
        return err
    root, err = repoRootOrError()
    if err:
        return err
    file = safe_file_name(args['file'])
    if not file:
        return yf.returnJson(False, '非法的文件名!')

    custom_hooks = root + '/' + user + '/' + repo + '.git/custom_hooks'
    self_path = custom_hooks + '/self/' + file
    self_logs_path = custom_hooks + '/self_logs/' + file + '.log'

    # 二重防御：物理上检查脚本是否存在，阻断恶意命令注入
    if not os.path.exists(self_path):
        return yf.returnJson(False, '脚本文件不存在!')

    shell = "sh -x " + yf.shlexQuote(self_path) + " 2>" + yf.shlexQuote(self_logs_path) + ' &'
    yf.execShell(shell)
    yf.execShell("chown -R www:www " + yf.shlexQuote(self_logs_path))
    return yf.returnJson(True, '执行成功!')


def projectScriptSelf_Rename():
    args = getArgs()
    data = checkArgs(args, ['user', 'name', 'o_file', 'n_file'])
    if not data[0]:
        return data[1]

    user, repo, err = ownerRepoOrError(args)
    if err:
        return err
    root, err = repoRootOrError()
    if err:
        return err
    o_file = safe_file_name(args['o_file'])
    n_file = safe_file_name(args['n_file'])
    if not o_file or not n_file:
        return yf.returnJson(False, '非法的文件名!')

    if not o_file.endswith('.sh'):
        o_file = o_file + '.sh'
    if not n_file.endswith('.sh'):
        n_file = n_file + '.sh'

    custom_hooks = root + '/' + user + '/' + repo + '.git/custom_hooks'
    self_path = custom_hooks + '/self'

    if not os.path.exists(self_path):
        yf.makeDirs(self_path)

    o_file_abs = self_path + '/' + o_file
    if not os.path.exists(o_file_abs):
        return yf.returnJson(False, '原文件已经不存在了!')

    n_file_abs = self_path + '/' + n_file
    os.rename(o_file_abs, n_file_abs)

    # 日志也删除
    log_file = custom_hooks + '/self_logs/' + o_file + '.log'
    if os.path.exists(log_file):
        os.remove(log_file)

    return yf.returnJson(True, '重命名成功!')


def projectScriptSelf_Enable():
    args = getArgs()
    data = checkArgs(args, ['user', 'name', 'enable'])
    if not data[0]:
        return data[1]

    user, repo, err = ownerRepoOrError(args)
    if err:
        return err
    root, err = repoRootOrError()
    if err:
        return err
    enable = str(args['enable'])

    custom_path = root + '/' + user + '/' + repo + '.git/custom_hooks'

    # 替换commit配置
    commit_path = custom_path + '/commit'
    note = '#Gitea Script Don\'t Remove and Change'

    self_file = custom_path + '/self_hook.sh'
    self_hook_tpl = getPluginDir() + '/hook/self_hook.tpl'

    if enable == '1':
        # 先读 commit（缺了就失败）再落任何产物：否则写入 self_hook.sh 之后才发现
        # commit 不存在，会留下一个“半成品”文件。
        commit_content = yf.readFile(commit_path)
        if not commit_content:
            # readFile 失败返回 False（不是空串），旧实现 False += str → TypeError
            return yf.returnJson(False, '请先加载脚本!')

        content = yf.readFile(self_hook_tpl)
        if not content:
            return yf.returnJson(False, '模板文件读取失败!')
        content = content.replace('{$HOOK_DIR}', custom_path + '/self')
        content = content.replace(
            '{$HOOK_LOGS_DIR}', custom_path + '/self_logs')
        if not yf.writeFile(self_file, content):
            return yf.returnJson(False, '脚本写入失败!')
        # 755：该脚本在 git push 时以 www 身份执行，777 = 任意本地用户可改写（本地提权）
        yf.execShell("chmod 755 " + yf.shlexQuote(self_file))
        yf.execShell("chown -R www:www " + yf.shlexQuote(self_file))

        commit_content += "\n\n" + "bash " + self_file + " " + note
        if not yf.writeFile(commit_path, commit_content):
            return yf.returnJson(False, '脚本写入失败!')

        return yf.returnJson(True, '开启成功!')
    else:
        commit_content = yf.readFile(commit_path)
        if not commit_content:
            return yf.returnJson(False, '请先加载脚本!')
        rep = ".*" + note
        commit_content = re.sub(rep, '', commit_content, re.M)
        commit_content = commit_content.strip()
        if not yf.writeFile(commit_path, commit_content):
            return yf.returnJson(False, '脚本写入失败!')
        if os.path.exists(self_file):
            os.remove(self_file)
        return yf.returnJson(True, '关闭成功!')


def projectScriptSelf_Status():
    args = getArgs()
    data = checkArgs(args, ['user', 'name', 'file', 'status'])
    if not data[0]:
        return data[1]

    user, repo, err = ownerRepoOrError(args)
    if err:
        return err
    root, err = repoRootOrError()
    if err:
        return err
    file = safe_file_name(args['file'])
    status = str(args['status'])
    if not file:
        return yf.returnJson(False, '非法的文件名!')

    custom_hooks = root + '/' + user + '/' + repo + '.git/custom_hooks'
    self_path = custom_hooks + '/self'

    if not os.path.exists(self_path):
        yf.makeDirs(self_path)

    # 日志也删除
    log_file = custom_hooks + '/self_logs/' + file + '.log'
    if os.path.exists(log_file):
        os.remove(log_file)

    if status == '1':
        file_abs = self_path + '/' + file
        file_text_abs = self_path + '/' + file + '.txt'
        if os.path.exists(file_abs):
            os.rename(file_abs, file_text_abs)
            return yf.returnJson(True, '开始禁用成功!')
    else:
        file_abs = self_path + '/' + file.replace('.txt', '')
        file_text_abs = self_path + '/' + file
        if os.path.exists(file_text_abs):
            os.rename(file_text_abs, file_abs)
            return yf.returnJson(True, '开始使用成功!')

    return yf.returnJson(False, '禁用失败!')


def getRsaPublic():
    ssh_dir = getHomeDir() + '/.ssh'
    path = ssh_dir + '/id_rsa.pub'

    if not os.path.exists(path):
        if not os.path.exists(ssh_dir):
            try:
                os.makedirs(ssh_dir)
                yf.execShell("chmod 700 " + ssh_dir)
            except Exception as _e:
                _log.debug('[gitea] getRsaPublic 异常已忽略: %s', _e)
        # 静默在后台自动一键生成免密密钥对
        cmd = 'ssh-keygen -t rsa -N "" -f ' + ssh_dir + '/id_rsa'
        yf.execShell(cmd)
        if not yf.isAppleSystem():
            yf.execShell("chown -R www:www " + ssh_dir)

    content = yf.readFile(path)
    if not content:
        content = "读取本机公钥失败，请检查家目录权限，或手动在命令行中运行 ssh-keygen。"
    else:
        content = content.strip()

    data = {}
    data['pub_key'] = content
    return yf.getJson(data)


def getTotalStatistics():
    st = status()
    data = {}
    if st.strip() == 'start':
        conf = getConf()
        if not os.path.exists(conf):
            return yf.returnJson(False, "请先安装初始化，默认地址: http://" + yf.getLocalIp() + ":3000")
        list_count = pQuery('select count(id) as num from repository')
        if not list_count:
            return yf.returnJson(False, '仅支持mysql|sqlite3配置')
        count = list_count[0]["num"]
        data['status'] = True
        data['count'] = count
        ver = yf.readFile(getServerDir() + '/version.pl')
        # readFile 失败返回 False（不是空串），旧实现 False.strip() → AttributeError
        data['ver'] = ver.strip() if isinstance(ver, str) else ''
        return yf.returnJson(True, 'ok', data)

    data['status'] = False
    data['count'] = 0
    return yf.returnJson(False, 'fail', data)


def uninstallPreInspection():
    repo_dir = getServerDir() + "/data/gitea-repositories"
    if not os.path.exists(repo_dir):
        return 'ok'
    dir_list = os.listdir(repo_dir)
    if len(dir_list) > 0:
        return "有项目数据!请手动删除Gitea<br/> rm -rf {}".format(getServerDir())
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
    elif func == 'uninstall_pre_inspection':
        print(uninstallPreInspection())
    elif func == 'run_log':
        print(runLog())
    elif func == 'post_receive_log':
        print(postReceiveLog())
    elif func == 'conf':
        print(getConf())
    elif func == 'init_conf':
        print(getInitdConf())
    elif func == 'get_gogs_conf':
        print(getGogsConf())
    elif func == 'submit_gogs_conf':
        print(submitGogsConf())
    elif func == 'gogs_edit_tpl':
        print(gogsEditTpl())
    elif func == 'user_list':
        print(userList())
    elif func == 'repo_list':
        print(repoList())
    elif func == 'user_project_list':
        print(userProjectList())
    elif func == 'project_script_edit':
        print(projectScriptEdit())
    elif func == 'project_script_load':
        print(projectScriptLoad())
    elif func == 'project_script_unload':
        print(projectScriptUnload())
    elif func == 'project_script_debug':
        print(projectScriptDebug())
    elif func == 'project_script_run':
        print(projectScriptRun())
    elif func == 'project_script_self':
        print(projectScriptSelf())
    elif func == 'project_script_self_create':
        print(projectScriptSelf_Create())
    elif func == 'project_script_self_del':
        print(projectScriptSelf_Del())
    elif func == 'project_script_self_logs':
        print(projectScriptSelf_Logs())
    elif func == 'project_script_self_run':
        print(projectScriptSelf_Run())
    elif func == 'project_script_self_rename':
        print(projectScriptSelf_Rename())
    elif func == 'project_script_self_enable':
        print(projectScriptSelf_Enable())
    elif func == 'project_script_self_status':
        print(projectScriptSelf_Status())
    elif func == 'get_rsa_public':
        print(getRsaPublic())
    elif func == 'get_total_statistics':
        print(getTotalStatistics())
    elif func == 'get_access_url':
        print(getAccessUrl())
    else:
        print('fail')
