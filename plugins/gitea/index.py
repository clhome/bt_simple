# coding: utf-8


import time
import os
import sys
import re
import json
import subprocess
import shutil
import shlex
import functools
import urllib.request
import urllib.error

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
        if exe.endswith(' (deleted)'):
            exe = exe[:-10].strip()
        if exe == bin_path:
            pids.append(name)
            continue
        # 第二判据：读取 cmdline 首字段
        try:
            with open(os.path.join(_PROC_ROOT, name, 'cmdline'), 'rb') as fp:
                raw_cmd = fp.read()
            if raw_cmd:
                cmd0 = raw_cmd.split(b'\x00')[0].decode('utf-8', errors='ignore').strip()
                if cmd0.endswith(' (deleted)'):
                    cmd0 = cmd0[:-10].strip()
                if cmd0 and (os.path.realpath(cmd0) == bin_path or cmd0 == bin_path):
                    pids.append(name)
        except Exception:
            pass
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


def getPortListeningPids(port):
    """检测指定 TCP 端口是否被监听，并返回占用该端口的 PID 列表（字符串列表）。"""
    if not port:
        return []
    pids = []
    # 1. 优先尝试 lsof 查监听进程
    try:
        rc, out, _ = yf.execShellRc(f'lsof -t -iTCP:{shlex.quote(str(port))} -sTCP:LISTEN', timeout=5)
        if rc == 0 and out:
            for p in out.strip().split():
                if p.isdigit():
                    pids.append(p)
    except Exception as _e:
        _log.debug('[gitea] lsof 探测端口异常: %s', _e)

    # 2. 尝试 fuser 探测
    if not pids:
        try:
            rc, out, err = yf.execShellRc(f'fuser {shlex.quote(str(port))}/tcp', timeout=5)
            out_all = (out or '') + ' ' + (err or '')
            for part in out_all.split():
                part = part.strip()
                if part.isdigit():
                    pids.append(part)
        except Exception as _e:
            _log.debug('[gitea] fuser 探测端口异常: %s', _e)

    # 3. 尝试 ss -tlpn 探测
    if not pids:
        try:
            rc, out, _ = yf.execShellRc(f"ss -tlpn 'sport = :{shlex.quote(str(port))}'", timeout=5)
            if rc == 0 and out:
                for m in re.finditer(r'pid=(\d+)', out):
                    pids.append(m.group(1))
        except Exception as _e:
            _log.debug('[gitea] ss 探测端口异常: %s', _e)

    # 4. 如果命令未能取到 PID，但通过 socket 探测端口已被占用，则通过 status() 或进程回读 PID 作为兜底
    if not pids:
        occupied = False
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            res = s.connect_ex(('127.0.0.1', int(port)))
            s.close()
            if res == 0:
                occupied = True
        except Exception:
            pass
        if occupied:
            g_pids = getGiteaPids()
            if g_pids:
                pids.extend(g_pids)
            else:
                pids.append('占用中(未知PID)')

    return sorted(list(set(pids)))


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
        unit_name = getPluginName()
        actual_method = method
        # P1-2: 处理 systemd active(exited) 僵住状态：单元因 RemainAfterExit 被标记为 active 但进程已退出，start 为空操作，需转 restart
        if method == 'start' and status() == 'stop':
            try:
                rc_act, out_act, _ = yf.execShellRc(['systemctl', 'is-active', unit_name], shell=False, timeout=10)
                if (out_act or '').strip() == 'active':
                    rc_sub, out_sub, _ = yf.execShellRc(['systemctl', 'show', '-p', 'SubState', '--value', unit_name], shell=False, timeout=10)
                    if (out_sub or '').strip() == 'exited':
                        _log.info('[gitea] 检测到单元处于 active(exited) 僵死状态，直接转用 restart 拉起')
                        actual_method = 'restart'
            except Exception as _e:
                _log.debug('[gitea] 检查 active(exited) 状态异常: %s', _e)

        rc, out, err = yf.execShellRc('systemctl ' + actual_method + ' ' + unit_name, timeout=120)
        if rc != 0:
            # 旧实现只看 stderr 是否为空：systemctl 失败但输出在 stdout 时会被吞成成功
            _log.debug('[gitea] systemctl %s 失败: %s', actual_method, (err or out).strip())
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

        # 二次兜底：如果执行 start 之后状态依然是 stop，尝试使用 restart 再次拉起
        if method == 'start' and status() == 'stop':
            _log.info('[gitea] start 后服务仍为 stop，尝试以 restart 再次拉起')
            rc_r, _, _ = yf.execShellRc('systemctl restart ' + unit_name, timeout=120)
            if rc_r == 0:
                for _ in range(10):
                    if status() == 'start':
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


# ---------------------------------------------------------------------------
# Gitea 版本检测、最新 Release 嗅探与无损平滑升级 (含秒级故障回滚)
# ---------------------------------------------------------------------------

def getCurrentVersion():
    """获取本地 Gitea 确切版本。
    
    优先执行二进制 `gitea --version` 探测真实运行版本；若尚未启动或执行失败，
    降级读取安装时记录的 `version.pl`。
    """
    bin_path = getGiteaBin()
    if isInstalled() and os.path.exists(bin_path):
        try:
            rc, out, _ = yf.execShellRc(f'{shlex.quote(bin_path)} --version', timeout=5)
            if rc == 0 and out:
                m = re.search(r'Gitea\s+version\s+([0-9]+(?:\.[0-9]+)+)', out, re.I)
                if m:
                    ver = m.group(1).strip()
                    try:
                        ver_file = getServerDir() + '/version.pl'
                        cur_saved = yf.readFile(ver_file)
                        if not isinstance(cur_saved, str) or cur_saved.strip() != ver:
                            yf.writeFile(ver_file, ver)
                    except Exception as e:
                        _log.debug('[gitea] 同步 version.pl 异常已忽略: %s', e)
                    return ver
        except Exception as e:
            _log.debug('[gitea] 执行 gitea --version 失败: %s', e)

    ver_file = getServerDir() + '/version.pl'
    if os.path.exists(ver_file):
        ver = yf.readFile(ver_file)
        if isinstance(ver, str) and ver.strip():
            return ver.strip()
    return ''


def parseSemVer(ver_str):
    """将版本字符串解析并归一化为 (major, minor, patch) 数字三元组。
    
    上游 Gitea 从 28.0.0 起移除了历史的 '1.' 前缀，即 28.x.y 实质为 1.28.y。
    为实现平滑跨版本比对与阶梯安全评估，将首位 >= 28 的版本归一化映射为 (1, major, patch)。
    """
    if not ver_str:
        return (0, 0, 0)
    ver_clean = re.sub(r'^[vV]', '', str(ver_str).strip())
    parts = re.findall(r'\d+', ver_clean)
    if not parts:
        return (0, 0, 0)
    nums = [int(p) for p in parts[:3]]
    while len(nums) < 3:
        nums.append(0)

    # 归一化：上游 28.x.y 对应 1.28.y
    if nums[0] >= 28:
        return (1, nums[0], nums[1])
    return tuple(nums)


def compareSemVer(v1, v2):
    """比较两个语义化版本号。v1 > v2 返回 1; v1 == v2 返回 0; v1 < v2 返回 -1。"""
    t1 = parseSemVer(v1)
    t2 = parseSemVer(v2)
    if t1 > t2:
        return 1
    elif t1 < t2:
        return -1
    return 0


def checkSteppedRisk(curr_ver, target_ver):
    """检测版本跨度与数据库平滑迁移风险。
    
    Gitea ORM 迁移逻辑跨越大版本过多时，可能丢弃非常早期的迁移脚本。
    上游 28.x 即 1.28 线，1.26 -> 28.2 实际跨越 2 个 minor，属于平滑迁移范围。
    若次版本号跨度 > 2 或主版本变动，提供安全提示。
    """
    if not curr_ver or not target_ver:
        return False, ''
    c_maj, c_min, _ = parseSemVer(curr_ver)
    t_maj, t_min, _ = parseSemVer(target_ver)
    
    diff = (t_maj - c_maj) * 100 + (t_min - c_min)
    if diff > 2 or t_maj > c_maj:
        msg = (f"当前版本(v{curr_ver})与目标版本(v{target_ver})跨越了多个主版本。"
               "Gitea 数据库迁移支持平滑向前迁移，但跨度较大时建议确认已备份数据库（如 SQLite 或 MySQL）。"
               "系统在升级前将自动为您对原有可执行程序、配置文件及数据库进行快照，并配备故障自动秒级回滚保障。")
        return True, msg
    return False, ''


class IniCheckResult(tuple):
    """兼顾两元组解包兼容性 (is_safe, warns) 与 .blockings 阻断项属性。"""
    def __new__(cls, is_safe, warns, blockings=None):
        obj = super().__new__(cls, (is_safe, warns))
        obj.is_safe = is_safe
        obj.warns = warns
        obj.blockings = blockings or []
        return obj


def checkAppIniCompatibility():
    """升级前预检 app.ini 中 28.x 相关的废弃/阻断配置项。
    
    返回 IniCheckResult 对象，解包兼容 (is_safe, warns)，同时提供 .blockings 属性。
    """
    conf_path = getServerDir() + '/custom/conf/app.ini'
    if not os.path.exists(conf_path):
        return IniCheckResult(True, [], [])
    content = yf.readFile(conf_path)
    if not content or not isinstance(content, str):
        return IniCheckResult(True, [], [])
    
    warns = []
    blockings = []

    # 1. 废弃配置项 (Warnings)
    if re.search(r'^\s*ALLOWED_DOMAINS\s*=', content, re.M):
        warns.append('检测到已废弃的 ALLOWED_DOMAINS 配置，建议改用 ALLOWED_HOST_LIST')
    if re.search(r'^\s*BLOCKED_DOMAINS\s*=', content, re.M):
        warns.append('检测到已废弃的 BLOCKED_DOMAINS 配置，建议改用 BLOCKED_HOST_LIST')
    if re.search(r'^\s*ALLOW_LOCALNETWORKS\s*=', content, re.M):
        warns.append('检测到已废弃的 ALLOW_LOCALNETWORKS 配置，建议改用 ALLOWED_HOST_LIST')

    # 2. 已移除的 external 预设 (Warning)
    if re.search(r'^\s*EGRESS_MODE\s*=\s*external\b', content, re.M | re.I):
        warns.append('检测到已移除的 external 预设(EGRESS_MODE = external)，28.x 中该预设已被删除，建议调整为 lax 或自定义出站规则')

    # 3. lax 模式下 ALLOWED_HOST_LIST 语义变化组合告警 (Warning)
    m_egress_lax = re.search(r'^\s*EGRESS_MODE\s*=\s*lax\b', content, re.M | re.I)
    if m_egress_lax and re.search(r'^\s*ALLOWED_HOST_LIST\s*=', content, re.M):
        warns.append('检测到 EGRESS_MODE=lax 与 ALLOWED_HOST_LIST 组合：在 lax 模式下，ALLOWED_HOST_LIST 仅作私有地址白名单豁免，不再作为全局出站白名单')

    # 4. 阻止启动的严重配置冲突 (Blockings)
    m = re.search(r'^\s*BLOCKED_HOST_LIST\s*=\s*(.*)', content, re.M)
    if m and '*' in m.group(1):
        blk_msg = 'BLOCKED_HOST_LIST 中包含 * 通配符(28.x 不支持通配符且会阻止服务启动崩溃，请移除 * 改用具体 CIDR 或具体域名)'
        blockings.append(blk_msg)
        warns.append(blk_msg)

    is_safe = (len(blockings) == 0)
    return IniCheckResult(is_safe, warns, blockings)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """禁止自动 302 重定向，用于捕获 Location 标头提取目标 release tag。"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def getLatestReleaseFromGithub(force=False):
    """从 GitHub Releases 探测最新官方发布版本（双通道高可用 + 缓存）。"""
    cache_file = getPluginDir() + '/latest_version_cache.json'
    now_ts = int(time.time())

    # 1. 尝试使用 1 小时有效期的本地缓存
    if not force and os.path.exists(cache_file):
        try:
            cache_content = yf.readFile(cache_file)
            if cache_content:
                cdata = json.loads(cache_content)
                if now_ts - cdata.get('time', 0) < 3600 and cdata.get('version'):
                    cdata['cached'] = True
                    return cdata
        except Exception as e:
            _log.debug('[gitea] 读取版本缓存失败: %s', e)

    latest_ver = ''
    pub_date = ''
    notes = ''
    is_offline = False

    # 2. 通道 A：302 重定向嗅探（无 API 限流，极快）
    probe_urls = ['https://github.com/go-gitea/gitea/releases/latest']
    proxy_prefix = ''
    try:
        proxy_prefix = yf.getGithubProxy()
    except Exception as e:
        _log.debug('[gitea] 获取 GitHub 代理前缀异常: %s', e)
    if proxy_prefix:
        probe_urls.append(yf._makeGithubProxyUrl(proxy_prefix, probe_urls[0]))

    for p_url in probe_urls:
        try:
            opener = urllib.request.build_opener(_NoRedirectHandler)
            req = urllib.request.Request(p_url, headers={'User-Agent': 'curl/7.68.0'})
            try:
                opener.open(req, timeout=6)
            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 307, 308):
                    loc = e.headers.get('Location', '')
                    m = re.search(r'tag/v?([0-9]+(?:\.[0-9]+)+)', loc)
                    if m:
                        latest_ver = m.group(1).strip()
                        break
        except Exception as e:
            _log.debug('[gitea] 302 重定向探测 %s 失败: %s', p_url, e)
            continue

    # 3. 通道 B：GitHub REST API 补充详细信息与 Release Notes
    api_url = 'https://api.github.com/repos/go-gitea/gitea/releases/latest'
    try:
        req = urllib.request.Request(api_url, headers={'User-Agent': 'curl/7.68.0'})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            tag = data.get('tag_name', '').lstrip('v')
            if tag and not latest_ver:
                latest_ver = tag
            pub_date = (data.get('published_at') or '')[:10]
            raw_body = (data.get('body') or '').strip()
            notes = raw_body[:400] + ('...' if len(raw_body) > 400 else '')
    except Exception as e:
        _log.debug('[gitea] GitHub API 探测失败: %s', e)

    # 4. 通道 C：离线兜底（使用 info.json 中声明的最高稳定版）
    if not latest_ver:
        try:
            info_file = getPluginDir() + '/info.json'
            if os.path.exists(info_file):
                info_data = json.loads(yf.readFile(info_file))
                v_list = info_data.get('versions', [])
                if v_list:
                    sorted_v = sorted(v_list, key=functools.cmp_to_key(compareSemVer))
                    latest_ver = sorted_v[-1]
                    notes = '（当前环境无法直接访问 GitHub，已启用离线推荐最高稳定版）'
                    is_offline = True
        except Exception as e:
            _log.debug('[gitea] 读取 info.json 离线版本失败: %s', e)

    res = {
        'version': latest_ver,
        'published_at': pub_date or time.strftime('%Y-%m-%d'),
        'notes': notes or '官方最新稳定版',
        'offline': is_offline,
        'cached': False,
        'time': now_ts
    }

    try:
        yf.writeFile(cache_file, json.dumps(res))
    except Exception as e:
        _log.debug('[gitea] 写入版本缓存失败: %s', e)

    return res


def checkUpdate():
    """面板前端获取更新状态接口。"""
    args = getArgs()
    force = str(args.get('force', '')).lower() in ('1', 'true')
    curr_ver = getCurrentVersion()
    latest_info = getLatestReleaseFromGithub(force=force)
    latest_ver = latest_info.get('version', '')

    has_update = False
    if curr_ver and latest_ver:
        has_update = (compareSemVer(latest_ver, curr_ver) > 0)

    is_risk, risk_msg = checkSteppedRisk(curr_ver, latest_ver)
    ini_res = checkAppIniCompatibility()
    ini_safe = ini_res[0]
    ini_warns = ini_res[1]
    ini_blockings = ini_res[2] if len(ini_res) > 2 else []

    data = {
        'current_version': curr_ver,
        'latest_version': latest_ver,
        'has_update': has_update,
        'published_at': latest_info.get('published_at', ''),
        'notes': latest_info.get('notes', ''),
        'offline': latest_info.get('offline', False),
        'is_stepped_warning': is_risk,
        'warning_msg': risk_msg,
        'ini_safe': ini_safe,
        'ini_warnings': ini_warns,
        'ini_blockings': ini_blockings,
        'is_installed': isInstalled()
    }
    return yf.returnJson(True, 'ok', data)


def getSystemPackageFile(version):
    """依据系统类型与 CPU 架构计算对应的 Gitea 发行文件名。"""
    sys_name = yf.execShell("uname -s")[0].strip()
    sys_arch = yf.execShell("arch")[0].strip()
    if not sys_arch:
        sys_arch = yf.execShell("uname -m")[0].strip()

    if sys_name == 'Darwin':
        v_parts = parseSemVer(version)
        # 上游 28.x 起 (去掉了 1. 前缀)，Darwin 资产文件名不再带 -10.12 后缀
        if v_parts[1] >= 28 or v_parts[0] >= 28:
            return f'gitea-{version}-darwin-amd64'
        return f'gitea-{version}-darwin-10.12-amd64'
    elif sys_arch in ('aarch64', 'arm64'):
        return f'gitea-{version}-linux-arm64'
    else:
        return f'gitea-{version}-linux-amd64'


def cleanOldBackups(backup_dir, keep=2):
    """清理历史升级备份，仅保留最近 keep 批备份，避免占用过多磁盘空间。"""
    try:
        if not os.path.exists(backup_dir):
            return
        pattern = re.compile(r'^(gitea|gitea_sqlite|app\.ini)\.bak\.(\d{8}_\d{6})$')
        groups = {}
        for fname in os.listdir(backup_dir):
            m = pattern.match(fname)
            if m:
                prefix, ts = m.groups()
                groups.setdefault(prefix, []).append((ts, fname))
        for prefix, items in groups.items():
            items.sort(key=lambda x: x[0], reverse=True)
            if len(items) > keep:
                for _, old_fname in items[keep:]:
                    old_path = os.path.join(backup_dir, old_fname)
                    try:
                        os.remove(old_path)
                        _log.debug('[gitea] 自动清理历史过期备份: %s', old_fname)
                    except Exception as e:
                        _log.debug('[gitea] 清理过期备份失败: %s', e)
    except Exception as e:
        _log.debug('[gitea] cleanOldBackups 异常: %s', e)


def upgradeApp():
    """Gitea 无损平滑在线升级接口（含原子备份、架构预检、深层健康巡检与秒级故障回滚）。"""
    if not isInstalled():
        return yf.returnJson(False, 'Gitea 尚未安装，无法执行升级!')

    args = getArgs()
    target_ver = str(args.get('version', '')).strip().lstrip('v')
    if not target_ver:
        latest_info = getLatestReleaseFromGithub(force=False)
        target_ver = latest_info.get('version', '').strip().lstrip('v')

    # 严格校验版本号，阻断任何注入
    if not re.match(r'^[0-9]+(?:\.[0-9]+)+$', target_ver):
        return yf.returnJson(False, '非法的目标版本号参数: ' + target_ver)

    curr_ver = getCurrentVersion()
    if curr_ver and compareSemVer(target_ver, curr_ver) < 0:
        return yf.returnJson(False, f'禁止逆向降级: 目标版本(v{target_ver})低于当前版本(v{curr_ver})')

    # 升级前配置阻断项拦截预检 (P1-4)
    ini_res = checkAppIniCompatibility()
    ini_blockings = ini_res[2] if len(ini_res) > 2 else []
    if ini_blockings:
        return yf.returnJson(False, f'升级失败已触发自动回滚: app.ini 存在阻止 Gitea 启动的致命配置冲突：{"; ".join(ini_blockings)}')

    # 升级前数据库类型检查与外部备份确认 (P1-1)
    conf = getDbConfValue()
    db_type = getGiteaDbType(conf) if conf else 'NONE'
    backup_confirmed = str(args.get('backup_confirmed', args.get('confirmed', ''))).lower() in ('1', 'true', 'yes')
    if db_type in ('mysql', 'postgres', 'postgresql') and not backup_confirmed:
        return yf.returnJson(
            False,
            f'升级失败已触发自动回滚: 当前 Gitea 使用 {db_type} 数据库，跨大版本升级将自动迁移 Schema，若升级失败回滚将无法自动恢复外部数据库结构。'
            '请在升级前手动执行数据库备份（如 mysqldump / pg_dump），确认已备份后勾选确认升级。',
            {'need_backup_confirm': True, 'db_type': db_type}
        )

    server_dir = getServerDir()
    source_dir = yf.getServerDir() + '/source/gitea'
    backup_dir = server_dir + '/backup'
    yf.makeDirs(source_dir)
    yf.makeDirs(backup_dir)

    file_base = getSystemPackageFile(target_ver)
    file_xz = file_base + '.xz'
    xz_path = source_dir + '/' + file_xz
    extracted_bin = source_dir + '/' + file_base
    cur_bin = server_dir + '/gitea'

    # 1. 下载新版本 .xz 安装包
    url_download = f'https://github.com/go-gitea/gitea/releases/download/v{target_ver}/{file_xz}'
    try:
        if os.path.exists(xz_path) and os.path.getsize(xz_path) < 1024 * 1024:
            os.remove(xz_path)
    except Exception as e:
        _log.debug('[gitea] 清理损坏包异常已忽略: %s', e)

    dl_ok = yf.githubDownload(url_download, xz_path, timeout=90, min_size=5 * 1024 * 1024)
    if not dl_ok or not os.path.exists(xz_path):
        return yf.returnJson(False, f'下载新版本安装包失败: {url_download}')

    # 2. 解压并做执行权限赋予
    if os.path.exists(extracted_bin):
        try:
            os.remove(extracted_bin)
        except Exception as e:
            _log.debug('[gitea] 清理旧解压产物异常已忽略: %s', e)
    yf.execShell(f'cd {shlex.quote(source_dir)} && xz -k -d -f {shlex.quote(file_xz)}')
    if not os.path.exists(extracted_bin):
        return yf.returnJson(False, '安装包解压失败，请检查系统 xz 工具是否就绪!')

    yf.execShell(f'chmod +x {shlex.quote(extracted_bin)}')

    # 3. 架构与 glibc 动态兼容预检 (Smoke Test，不区分大小写比对 P0-1)
    probe_rc, probe_out, probe_err = yf.execShellRc(f'{shlex.quote(extracted_bin)} --version', timeout=10)
    probe_full = ((probe_out or '') + ' ' + (probe_err or '')).lower()
    if probe_rc != 0 or 'gitea version' not in probe_full:
        err_msg = (probe_err or probe_out or '执行返回异常').strip()
        try:
            os.remove(extracted_bin)
        except Exception as e:
            _log.debug('[gitea] 清理预检失败二进制异常: %s', e)
        return yf.returnJson(False, f'系统环境预检运行失败: {err_msg}')

    # 4. 升级前安全快照（备份二进制与 SQLite 数据库）
    ts = time.strftime('%Y%m%d_%H%M%S')
    bak_bin = f'{backup_dir}/gitea.bak.{ts}'
    rollback_bin = f'{backup_dir}/gitea.rollback'
    try:
        shutil.copy2(cur_bin, bak_bin)
        shutil.copy2(cur_bin, rollback_bin)
    except Exception as e:
        return yf.returnJson(False, f'创建旧版本二进制快照失败: {e}')

    sqlite_real_path = ''
    sqlite_rollback = ''
    if db_type == 'sqlite3':
        db_path_cfg = conf.get('PATH', 'data/gitea.db')
        sqlite_real_path = db_path_cfg if os.path.isabs(db_path_cfg) else (server_dir + '/' + db_path_cfg)
        if os.path.exists(sqlite_real_path):
            sqlite_rollback = f'{backup_dir}/gitea_sqlite.rollback'
            try:
                shutil.copy2(sqlite_real_path, f'{backup_dir}/gitea_sqlite.bak.{ts}')
                shutil.copy2(sqlite_real_path, sqlite_rollback)
            except Exception as e:
                return yf.returnJson(False, f'升级失败已触发自动回滚: SQLite 数据库快照备份失败，已中止升级: {e}')

    # 备份 app.ini 配置文件快照
    conf_path = server_dir + '/custom/conf/app.ini'
    conf_rollback = f'{backup_dir}/app.ini.rollback'
    if os.path.exists(conf_path):
        try:
            shutil.copy2(conf_path, f'{backup_dir}/app.ini.bak.{ts}')
            shutil.copy2(conf_path, conf_rollback)
        except Exception as e:
            _log.debug('[gitea] 配置文件快照备份异常已忽略: %s', e)

    # 5. 停服并确认旧进程安全退出与端口完全释放 (P1-1, P1-2)
    was_running = (status() == 'start')
    if was_running:
        stop()
        stopped = False
        for _ in range(10):
            if status() == 'stop':
                stopped = True
                break
            time.sleep(1)
        if not stopped:
            return yf.returnJson(False, '升级失败已触发自动回滚: 旧版本 Gitea 服务停止超时（进程仍在运行），升级已安全中止以避免损坏服务。')

    # 严格校验服务端口释放（无进程监听 :3000 或配置端口）
    listen_port = getHttpPort() or '3000'
    port_released = False
    occupied_pids = []
    for _ in range(5):
        occupied_pids = getPortListeningPids(listen_port)
        if not occupied_pids:
            port_released = True
            break
        time.sleep(0.5)

    if not port_released and occupied_pids:
        if was_running:
            start()
        pid_desc = ', '.join(occupied_pids)
        return yf.returnJson(
            False,
            f'升级失败已安全中止: 服务端口 {listen_port} 仍被占用（残留 PID: {pid_desc}），旧进程未完全释放，已拒绝执行文件替换以防服务冲突。'
        )

    try:
        shutil.copy2(extracted_bin, cur_bin)
        yf.execShell(f'chmod +x {shlex.quote(cur_bin)}')
        yf.execShell(f'chown -R www:www {shlex.quote(cur_bin)}')
    except Exception as e:
        if os.path.exists(rollback_bin):
            shutil.copy2(rollback_bin, cur_bin)
            yf.execShell(f'chmod +x {shlex.quote(cur_bin)}')
        if was_running:
            start()
        return yf.returnJson(False, f'文件替换异常，已还原旧版本: {e}')

    # 6. 拉起新版本并执行深层健康巡检（Web 响应与 Schema 迁移完成判定 P1-2）
    start()
    health_ok = False
    port = getHttpPort() or '3000'
    check_url = f'http://127.0.0.1:{port}/'
    max_wait = 30  # 为大库迁移预留最多 30 秒
    for sec in range(max_wait):
        time.sleep(1)
        if status() != 'start':
            _log.error('[gitea] 新版本在启动或数据库迁移期间异常退出')
            health_ok = False
            break
        # 探测 Web 端口连通性
        try:
            req = urllib.request.Request(check_url, headers={'User-Agent': 'yf-gitea-probe'})
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status in (200, 301, 302, 401, 403):
                    health_ok = True
                    break
        except urllib.error.HTTPError as he:
            if he.code in (200, 301, 302, 401, 403):
                health_ok = True
                break
        except Exception as _e:
            _log.debug('[gitea] Web 端口就绪等待中: %s', _e)

    # 兜底：若 HTTP 探针受特定配置拦截但进程持续存活且运行超 15 秒无崩溃，二次检查端口监听
    if not health_ok and status() == 'start':
        try:
            rc, out, _ = yf.execShellRc(f"lsof -i:{shlex.quote(str(port))} -sTCP:LISTEN -t || ss -tlpn 'sport = :{shlex.quote(str(port))}'", timeout=5)
            if rc == 0 and out.strip():
                health_ok = True
        except Exception as _e:
            _log.debug('[gitea] 端口监听检查异常已忽略: %s', _e)

    # 7. 健康检查失败 -> 秒级自动回滚
    if not health_ok:
        _log.error('[gitea] 新版本启动失败或健康巡检未通过，立即触发自动秒级回滚！')
        if os.path.exists(rollback_bin):
            shutil.copy2(rollback_bin, cur_bin)
            yf.execShell(f'chmod +x {shlex.quote(cur_bin)}')
        if sqlite_real_path and os.path.exists(sqlite_rollback):
            try:
                shutil.copy2(sqlite_rollback, sqlite_real_path)
            except Exception as e:
                _log.debug('[gitea] 还原 SQLite 快照失败: %s', e)
        if os.path.exists(conf_rollback) and os.path.exists(conf_path):
            try:
                shutil.copy2(conf_rollback, conf_path)
            except Exception as e:
                _log.debug('[gitea] 还原配置文件快照失败: %s', e)
        start()
        log_file = runLog()
        log_tail = ''
        if os.path.exists(log_file):
            rc, out, _ = yf.execShellRc(f'tail -n 25 {shlex.quote(log_file)}')
            if rc == 0:
                log_tail = out.strip()

        db_notice = ''
        if db_type == 'sqlite3':
            db_notice = 'SQLite 数据库与配置文件已还原至升级前快照，原有数据与配置未受破坏。'
        elif db_type in ('mysql', 'postgres', 'postgresql'):
            db_notice = f'注意：当前数据库类型为 {db_type}，二进制与配置文件已安全回滚至升级前，但若升级期间 Schema 已被变更，请根据需要还原升级前的外部数据库备份。'
        else:
            db_notice = '配置文件与二进制已还原至升级前快照，原有数据与配置未受破坏。'

        return yf.returnJson(False, f'升级失败已触发自动回滚: 已安全恢复至原版本(v{curr_ver})。{db_notice} 日志摘要: {log_tail or "无"}')

    # 8. 升级成功：清理历史多余备份、更新 version.pl 并同步版本缓存 (P1-3, P2-3)
    cleanOldBackups(backup_dir, keep=2)
    yf.writeFile(server_dir + '/version.pl', target_ver + '\n')
    try:
        cache_file = getPluginDir() + '/latest_version_cache.json'
        if os.path.exists(cache_file):
            os.remove(cache_file)
    except Exception as e:
        _log.debug('[gitea] 清理版本缓存异常: %s', e)

    return yf.returnJson(True, f'升级成功: Gitea 成功无损升级至 v{target_ver}！原有配置文件与仓库数据均已完好保留。')


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
    elif func == 'check_update':
        print(checkUpdate())
    elif func == 'upgrade_app':
        print(upgradeApp())
    else:
        print('fail')
