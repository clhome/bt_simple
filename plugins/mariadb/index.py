# coding:utf-8

import sys
import io
import os
import time
import subprocess
import re
import json
import shlex
import tempfile


web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import core.db_pwd as db_pwd
import core.db_root as db_root
import logging

_log = logging.getLogger('yf.mariadb')


if yf.isAppleSystem():
    cmd = 'ls /usr/local/lib/ | grep python  | cut -d \\  -f 1 | awk \'END {print}\''
    info = yf.execShell(cmd)
    p = "/usr/local/lib/" + info[0].strip() + "/site-packages"
    sys.path.append(p)


app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'mariadb'


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
        # JSON 负载：调用方用 shlexQuote 传入时会保留双引号，优先按 JSON 解析。
        if val.startswith('{') and val.endswith('}'):
            try:
                return json.loads(val)
            except Exception as _e:
                _log.debug('[mariadb] getArgs 异常已忽略: %s', _e)
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
            t = args[i].split(':', 1)
            if len(t) == 2:
                k = t[0].strip().strip('"').strip("'")
                v = t[1].strip().strip('"').strip("'")
                tmp[k] = v
    return tmp


def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


def _parsePageArgs(args, def_page=1, def_size=10, max_size=100):
    """分页参数容错（与 plugins/postgresql/index.py 同名同签名同语义）。

    历史缺陷是分页参数直接 int()：page=abc 直接 ValueError traceback（面板 500），
    负页码拼出的 SQL LIMIT 也非法。非数字/空/None 回退默认值，page<1 夹到 1，
    size<1 回默认值，size>max_size 封顶（各接口默认值/上限按调用处传参决定）。
    """
    def _toInt(v, default):
        try:
            if v is None or str(v).strip() == '':
                return default
            return int(str(v).strip())
        except Exception:
            return default

    page = _toInt(args.get('page'), def_page)
    size = _toInt(args.get('page_size'), def_size)
    if page < 1:
        page = 1
    if size < 1:
        size = def_size
    if size > max_size:
        size = max_size
    return page, size


def safe_check_args(db_name=None, sign_val=None, username=None):
    # 与 mysql 插件同名同口径，统一委托给 yf.dbSafeCheckArgs。
    # 本文件历史上整文件 0 处白名单（测评报告 P0-1③「修了一半」），收敛到 yf 一处实现后
    # 两端不可能再单侧漂移。
    return yf.dbSafeCheckArgs(db_name=db_name, sign_val=sign_val, username=username)


def getBackupDir():
    bk_path = yf.getBackupDir() + "/database/mariadb"
    if not os.path.isdir(bk_path):
        yf.makeDirs(bk_path)
    return bk_path


def getConf():
    path = getServerDir() + '/etc/my.cnf'
    return path


_MYCNF_CACHE = {'key': None, 'content': ''}


def _readCnf():
    """读取 my.cnf 内容（按「路径 + mtime + size + 读取实现」失效）。

    getDbPort()/getSocketFile() 等在同一请求里会被反复调用（实测本文件 27/3/10 次），
    每次都重新读盘 + 正则。这里只缓存「同一份未变化的文件内容」：文件一旦被改写
    （mtime/size 变）立刻失效，因此语义与直读一致，不会读到旧值。
    把 yf.readFile 的当前实现也计入 key，避免测试 patch 掉 yf.readFile 后跨用例串味。
    """
    path = getConf()
    try:
        st = os.stat(path)
    except OSError:
        _MYCNF_CACHE.update({'key': None, 'content': ''})
        return ''
    key = (path, st.st_mtime_ns, st.st_size, yf.readFile)
    if _MYCNF_CACHE['key'] == key:
        return _MYCNF_CACHE['content']
    content = yf.readFile(path)
    if not isinstance(content, str):
        content = ''
    _MYCNF_CACHE.update({'key': key, 'content': content})
    return content


def _cnfValue(pattern, default=''):
    """从 my.cnf 取 pattern 第 1 个捕获组；文件缺失/无该配置时返回 default。

    历史实现在 10 个 getter 里直接 `re.search(rep, content)` + `tmp.groups()`，
    当 my.cnf 缺失（content=False）或未配置该项（tmp=None）时会抛
    TypeError/AttributeError（mysql 侧对应函数多数已有守卫，此处对齐并统一收口）。
    """
    content = _readCnf()
    if content:
        tmp = re.search(pattern, content)
        if tmp:
            return tmp.groups()[0].strip()
    return default


def getDataDir():
    datadir = _cnfValue(r'datadir\s*=\s*(.*)')
    if datadir:
        return datadir
    for d in [getServerDir() + '/data', '/var/lib/mysql', '/www/server/data']:
        if os.path.exists(d):
            return d
    return getServerDir() + '/data'

def getLogBinName():
    return _cnfValue(r'log-bin\s*=\s*(.*)', 'mysql-bin')

def getPidFile():
    pid = _cnfValue(r'pid-file\s*=\s*(.*)')
    if pid:
        return pid
    for p in [getServerDir() + '/data/mysql.pid', '/var/run/mysqld/mysqld.pid', '/tmp/mysql.pid']:
        if os.path.exists(p):
            return p
    return getServerDir() + '/data/mysql.pid'


def getDbPort():
    return _cnfValue(r'port\s*=\s*(.*)', '3306')


def getDbServerId():
    return _cnfValue(r'server-id\s*=\s*(.*)', '1')


def getSocketFile():
    sock = _cnfValue(r'socket\s*=\s*(.*)')
    if sock:
        return sock
    for s in ['/tmp/mysql.sock', '/var/run/mysqld/mysqld.sock', getServerDir() + '/mysql.sock']:
        if os.path.exists(s):
            return s
    return '/tmp/mysql.sock'


def getInitdTpl(version=''):
    path = getPluginDir() + '/init.d/mariadb' + version + '.tpl'
    if not os.path.exists(path):
        path = getPluginDir() + '/init.d/mariadb.tpl'
    return path


def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$SERVER_APP_PATH}', service_path + '/mariadb')
    server_id = int(time.time())
    content = content.replace('{$SERVER_ID}', str(server_id))

    if yf.isAppleSystem():
        user = yf.execShell(
            "who | sed -n '2, 1p' |awk '{print $1}'")[0].strip()
        content = content.replace('user = mysql', 'user = ' + user)
    return content


def pSqliteDb(dbname='databases'):
    name = 'mariadb' if os.path.exists(getServerDir() + '/mariadb.db') else 'mysql'
    file = getServerDir() + '/' + name + '.db'

    import_sql = yf.readFile(getPluginDir() + '/conf/mariadb.sql')
    md5_sql = yf.md5(import_sql)

    import_sign = False
    save_md5_file = getServerDir() + '/import_sql.md5'
    if os.path.exists(save_md5_file):
        save_md5_sql = yf.readFile(save_md5_file)
        if save_md5_sql != md5_sql:
            import_sign = True
            yf.writeFile(save_md5_file, md5_sql)
    else:
        yf.writeFile(save_md5_file, md5_sql)
        import_sign = True

    if not os.path.exists(file) or import_sign:
        conn = yf.M(dbname).dbPos(getServerDir(), name)
        csql_list = import_sql.split(';')
        for index in range(len(csql_list)):
            sql_item = csql_list[index].strip()
            if sql_item:
                try:
                    conn.execute(sql_item, ())
                except Exception as _e:
                    _log.debug('[mariadb] pSqliteDb 异常已忽略: %s', _e)

    conn = yf.M(dbname).dbPos(getServerDir(), name)
    # 幂等自愈：为老版本数据库 databases 表自动补齐缺失的 rw 权限列
    try:
        col_res = conn.query("PRAGMA table_info('databases')")
        existing_cols = []
        if col_res and not isinstance(col_res, str):
            for c in col_res:
                col_name = c.get('name') if isinstance(c, dict) else (c[1] if isinstance(c, (list, tuple)) and len(c) > 1 else None)
                if col_name:
                    existing_cols.append(col_name)
        if existing_cols and 'rw' not in existing_cols:
            conn.execute("ALTER TABLE `databases` ADD COLUMN `rw` TEXT DEFAULT 'all'")
    except Exception as _e:
        _log.debug('[mariadb] pSqliteDb 异常已忽略: %s', _e)

    # 原生 sqlite3 终极兜底，确保在各种运行环境下均能 100% 幂等加列成功
    try:
        if os.path.exists(file):
            import sqlite3 as raw_sqlite3
            s_conn = raw_sqlite3.connect(file)
            s_cur = s_conn.cursor()
            s_cur.execute("PRAGMA table_info('databases')")
            raw_cols = [r[1] for r in s_cur.fetchall() if len(r) > 1]
            if raw_cols and 'rw' not in raw_cols:
                s_cur.execute("ALTER TABLE `databases` ADD COLUMN `rw` TEXT DEFAULT 'all'")
                s_conn.commit()
            s_conn.close()
    except Exception as _e:
        _log.debug('[mariadb] pSqliteDb 异常已忽略: %s', _e)
    return conn

# ---------------------------------------------------------------------------
# P2-4：数据库口令「静态加密」的唯一读写入口（实现见 web/core/db_pwd.py）
#
# 落库形态：`yfenc:<Fernet token>`；历史明文（无标记）读写都原样通过，**无需迁移**。
# 这两个函数是本插件唯一允许碰 `config.mysql_root` 的地方，其余代码一律走
# `getRootPwd()` / `_saveRootPwd()`，避免「改了写点漏了读点」的单侧漂移。
# ---------------------------------------------------------------------------

def _chmod600(path):
    """把明文口令快照文件收紧到 0600（P2-4）。失败只记日志，不影响自愈主流程。"""
    try:
        os.chmod(path, 0o600)
        return True
    except Exception as _e:
        try:
            yf.writeFileLog('[db_pwd] 明文口令快照 %s 权限收紧失败: %s' % (path, _e))
        except Exception as _e2:
            _log.warning('[mariadb] 记录权限收紧失败日志失败: %s', _e2)
        return False


# 加密命名空间（固定常量）：本插件写的东西统一用这一个 key。
# root 口令与「库用户」口令共用同一命名空间，是为了让外部读取方（如 sphinx 读
# mysql 的 databases.password）只需要知道「这是哪个插件的数据」一个常量。
# 注意：本插件用 'mariadb_root' 命名空间，**不能**复用 mysql 的
# —— 否则同一台机上两个插件互相解不开对方的密文。
_PWD_SCOPE = db_pwd.SCOPE_MARIADB_ROOT


def _storedRootPwd():
    """读取 config.mysql_root 的**落库原值**（可能是 yfenc: 密文，也可能是历史明文）。

    唯一允许直读该字段的地方；读出来的值必须再过 `db_pwd.decrypt_pwd()` 才能当口令用。
    """
    return pSqliteDb('config').where('id=?', (1,)).getField('mysql_root')


def getRootPwd(default=''):
    """读取并解密 MariaDB root 口令（P2-4）。

    密文 → 解密；历史明文 → 原样返回（向后兼容）；解不开 → fail-closed 返回 default，
    绝不把密文当口令拼进命令（那会变成「密码错误」这种看不出根因的故障）。

    注意：本插件的命名空间是 `SCOPE_MARIADB_ROOT`（'mariadb_root'），**不能**复用
    mysql 的 —— 否则同一台机上两个插件互相解不开对方的密文。
    """
    pwd = db_pwd.decrypt_pwd(_PWD_SCOPE, _storedRootPwd())
    return default if pwd is None else pwd


def _saveRootPwd(pwd):
    """把 root 口令加密后写回 config.mysql_root（P2-4：禁止明文落库）。"""
    return pSqliteDb('config').where('id=?', (1,)).save(
        'mysql_root', (db_pwd.encrypt_pwd(_PWD_SCOPE, pwd),))


def _encUserPwd(pwd):
    """加密「数据库用户」口令（落 databases.password）。空口令原样返回（不加密）。"""
    return db_pwd.encrypt_pwd(_PWD_SCOPE, pwd)


def _decUserPwd(stored):
    """解密「数据库用户」口令；历史明文原样返回；解不开返回 None（fail-closed）。"""
    return db_pwd.decrypt_pwd(_PWD_SCOPE, stored)


def _decUserRows(rows):
    """列表接口的行内口令就地解密：前端要能看到可复制的**明文**。

    解不开的行给空串（而不是把密文丢给前端 —— 用户会复制一坨 base64 去登录）。
    """
    for row in rows or []:
        if isinstance(row, dict) and 'password' in row:
            row['password'] = _decUserPwd(row.get('password')) or ''
    return rows


def pMysqlDb(name=''):
    # pymysql
    db = yf.getMyORM()
    # MySQLdb |
    # db = yf.getMyORMDb()

    db.setDbConf(getConf())
    db.setPort(getDbPort())
    db.setSocket(getSocketFile())
    db.setDbName(name)

    pwd = getRootPwd()
    db.setPwd(pwd)
    return db


def makeInitRsaKey(version=''):
    datadir = getServerDir() + "/data"

    mysql_pem = datadir + "/mysql.pem"
    if not os.path.exists(mysql_pem):
        rdata = yf.execShell(
            'cd ' + datadir + ' && openssl genrsa -out mysql.pem 1024')
        # print(data)
        rdata = yf.execShell(
            'cd ' + datadir + ' && openssl rsa -in mysql.pem -pubout -out mysql.pub')
        # print(rdata)

        if not yf.isAppleSystem():
            yf.execShell('cd ' + datadir + ' && chmod 400 mysql.pem')
            yf.execShell('cd ' + datadir + ' && chmod 444 mysql.pub')
            yf.execShell('cd ' + datadir + ' && chown mysql:mysql mysql.pem')
            yf.execShell('cd ' + datadir + ' && chown mysql:mysql mysql.pub')


def initDreplace(version=''):
    initd_tpl = getInitdTpl(version)

    mysql_conf_dir = getServerDir() + '/etc'
    if not os.path.exists(mysql_conf_dir):
        os.mkdir(mysql_conf_dir)

    mysql_conf = mysql_conf_dir + '/my.cnf'
    if not os.path.exists(mysql_conf):
        mysql_conf_tpl = getPluginDir() + '/conf/my.cnf'
        content = yf.readFile(mysql_conf_tpl)
        content = contentReplace(content)
        yf.writeFile(mysql_conf, content)

    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        os.mkdir(initD_path)

    file_bin = initD_path + '/' + getPluginName()
    if not os.path.exists(file_bin):
        content = yf.readFile(initd_tpl)
        content = contentReplace(content)
        yf.writeFile(file_bin, content)
        yf.execShell('chmod +x ' + file_bin)

    mysql_tmp = getServerDir() + '/tmp'
    if not os.path.exists(mysql_tmp):
        os.mkdir(mysql_tmp)
        yf.execShell("chown -R mysql:mysql " + mysql_tmp)

    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/mariadb.service'
    systemServiceTpl = getPluginDir() + '/init.d/mariadb.service.tpl'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        service_path = yf.getServerDir()
        se_content = yf.readFile(systemServiceTpl)
        se_content = se_content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(systemService, se_content)
        yf.execShell('systemctl daemon-reload')

    if yf.getOs() != 'darwin':
        yf.execShell('chown -R mysql mysql ' + getServerDir())
    return file_bin


CURRENT_PLUGIN_VERSION = '2.0'
_MARIADB_UPGRADE_CHECKING = False


def getPluginVersionFile():
    """获取 MariaDB 插件版本标记文件路径"""
    return getPluginDir() + '/plugin_version.pl'


def getInstalledPluginVersion():
    """读取本地已持久化的插件版本（老版本若无此文件默认返回 1.0）"""
    vfile = getPluginVersionFile()
    if os.path.exists(vfile):
        try:
            v = yf.readFile(vfile).strip()
            if v:
                return v
        except Exception as _e:
            _log.debug('[mariadb] getInstalledPluginVersion 异常已忽略: %s', _e)
    server_vfile = getServerDir() + '/plugin_version.pl'
    if os.path.exists(server_vfile):
        try:
            v = yf.readFile(server_vfile).strip()
            if v:
                return v
        except Exception as _e:
            _log.debug('[mariadb] getInstalledPluginVersion 异常已忽略: %s', _e)
    return '1.0'


def setInstalledPluginVersion(ver):
    """持久化保存插件版本标记"""
    vfile = getPluginVersionFile()
    try:
        yf.writeFile(vfile, str(ver).strip())
    except Exception as _e:
        _log.debug('[mariadb] setInstalledPluginVersion 异常已忽略: %s', _e)
    try:
        server_vfile = getServerDir() + '/plugin_version.pl'
        if os.path.exists(getServerDir()):
            yf.writeFile(server_vfile, str(ver).strip())
    except Exception as _e:
        _log.debug('[mariadb] setInstalledPluginVersion 异常已忽略: %s', _e)


def comparePluginVersion(v1, v2):
    """语义化版本号比较"""
    def parse_ver(v):
        parts = []
        for p in str(v).strip().split('.'):
            if p.isdigit():
                parts.append(int(p))
            else:
                nums = re.findall(r'\d+', p)
                parts.append(int(nums[0]) if nums else 0)
        return parts

    p1 = parse_ver(v1)
    p2 = parse_ver(v2)
    max_len = max(len(p1), len(p2))
    p1 += [0] * (max_len - len(p1))
    p2 += [0] * (max_len - len(p2))
    if p1 < p2:
        return -1
    elif p1 > p2:
        return 1
    return 0


def getMariadbPid():
    """
    精准检测系统中正在运行的 mariadbd / mariadb / mysqld 守护进程 PID
    """
    try:
        # 1. 优先使用 pgrep
        for proc in ['[m]ariadbd', '[m]ariadb', '[m]ysqld']:
            res = yf.execShell(f"pgrep -f '{proc}'")
            if res and res[0].strip():
                pids = [p.strip() for p in res[0].strip().split() if p.strip().isdigit()]
                for p in reversed(pids):
                    pid_int = int(p)
                    if yf.checkPid(pid_int):
                        return pid_int

        # 2. ps 过滤识别
        ps_cmd = "ps -ef | grep -E 'mariadbd|mariadb|mysqld' | grep -v grep | awk '{print $2}'"
        ps_res = yf.execShell(ps_cmd)
        if ps_res and ps_res[0].strip():
            pids = [p.strip() for p in ps_res[0].strip().split() if p.strip().isdigit()]
            for p in reversed(pids):
                pid_int = int(p)
                if yf.checkPid(pid_int):
                    return pid_int
    except Exception as _e:
        _log.debug('[mariadb] getMariadbPid 异常已忽略: %s', _e)
    return None


# ---------------------------------------------------------------------------
# 实例归属判定 + 装后自检（2026-10-28：与 mysql 插件对齐）
#
#   为什么需要（mysql 侧已修，mariadb 是同一个口子）：
#   `getMariadbPid()` 取的是「机器上任意 mariadbd/mysqld」。若机器上另有系统装的
#   MySQL/MariaDB 占着 3306（apt/yum 装过、或以前装过别家的面板），面板会误判
#   「我的实例在跑」：
#     * `status()` 回 'start' → `start()` 立刻 return 'ok' → 首次安装的
#       `initMariaDbPwd()`（写 root 口令）被整段跳过 → 面板记的口令与库里永远对不上，
#       用户看到的就是「安装完成，但点数据库管理报 Access denied (using password: YES)」；
#     * 所有 SQL 都打到别人那个实例上；
#     * `fixDbAccess`（面板【修复】）更危险：会把**别人的**实例停掉、开
#       skip-grant-tables、改它的 root 口令。
#   这里把「进程是谁」查清楚，供 start / 自检 / 修复 使用。
#  ---------------------------------------------------------------------------
def _readProcLink(pid, name):
    try:
        return os.readlink('/proc/%d/%s' % (pid, name))
    except Exception:
        return ''


def _readProcCmdline(pid):
    try:
        with open('/proc/%d/cmdline' % pid, 'rb') as fp:
            return fp.read().decode('utf-8', 'replace').replace(chr(0), ' ').strip()
    except Exception:
        return ''


def _readProcCwd(pid):
    try:
        return os.readlink('/proc/%d/cwd' % pid)
    except Exception:
        return ''


#: /proc 扫描结果缓存（TTL 2s，见 getRunningMariadbdProcs）
_PROC_CACHE = {'at': 0.0, 'procs': []}


def _procAvailable():
    """本机是否有 /proc（Linux）。没有就无法判定实例归属，调用方按「未知」处理。"""
    return os.path.isdir('/proc')


def getRunningMariadbdProcs():
    """列出所有存活的 mariadbd/mysqld 进程：`[{'pid','exe','cmdline','data_dir'}]`。

    只读 /proc（不启子进程）；/proc 不可用（macOS 等）时返回空列表，调用方按
    「无法判定」处理，不能据此断言实例有问题。
    """
    global _PROC_CACHE
    now = time.time()
    if _PROC_CACHE.get('at') and now - _PROC_CACHE['at'] < 2:
        return [dict(x) for x in _PROC_CACHE['procs']]

    procs = []
    if not _procAvailable():
        return procs
    try:
        names = os.listdir('/proc')
    except Exception as _e:
        _log.debug('[mariadb] 读取 /proc 失败: %s', _e)
        return procs
    for name in names:
        if not name.isdigit():
            continue
        pid = int(name)
        exe = _readProcLink(pid, 'exe')
        cmdline = _readProcCmdline(pid)
        # 只认**可执行文件本身**是 mariadbd/mysqld 的进程：不能拿整条 cmdline 做
        # 子串匹配，`bash -c "... mariadbd ..."` 这种命令行会被误当成数据库进程。
        base = os.path.basename(exe).lower() if exe else ''
        if base:
            if not (base.startswith('mariadbd') or base.startswith('mysqld')):
                continue
        else:
            argv0 = os.path.basename((cmdline.split(' ') or [''])[0]).lower()
            if not (argv0.startswith('mariadbd') or argv0.startswith('mysqld')):
                continue
        data_dir = ''
        m = re.search(r'--datadir=(\S+)', cmdline)
        if m:
            data_dir = m.group(1).strip('"').strip("'")
        if not data_dir:
            data_dir = _readProcCwd(pid)
        # 卸载时只删目录没停进程：程序文件被删但进程还在，readlink 带 ' (deleted)'。
        # 这必须认成「我们自己的僵尸进程」，否则会被误判成「别人的实例」。
        deleted = exe.endswith(' (deleted)')
        if deleted:
            exe = exe[:-len(' (deleted)')]
        procs.append({'pid': pid, 'exe': exe, 'cmdline': cmdline,
                      'data_dir': data_dir, 'deleted': deleted})
    _PROC_CACHE = {'at': time.time(), 'procs': [dict(x) for x in procs]}
    return procs


def instanceOwnership():
    """判定「正在跑的 mariadbd/mysqld 是不是本插件这个实例」。

    返回 dict：
      status: ok | not_running | foreign_only | mixed | stale_ours |
              datadir_missing | unknown
      ours / stale / foreign: 进程列表
      datadir_exists / socket_exists: 本插件的数据目录、socket 是否就位
      reason: 面向用户的中文说明（status 非 ok 时非空）
    """
    serverdir = getServerDir()
    our_dir = os.path.realpath(serverdir)
    our_exes = set()
    for _n in ('mariadbd', 'mysqld'):
        our_exes.add(os.path.realpath(os.path.join(our_dir, 'bin', _n)))
    datadir = ''
    try:
        datadir = getDataDir()
    except Exception as _e:
        _log.debug('[mariadb] 读取 datadir 失败: %s', _e)
    # 这里不能用 getSocketFile()（它在某些分支里会回到进程探测，容易递归），
    # 只读配置里的 socket 路径即可满足「文件在不在」的判定。
    socket_file = ''
    try:
        socket_file = _cnfValue(r'socket\s*=\s*(.*)') or (serverdir + '/mysql.sock')
    except Exception as _e:
        _log.debug('[mariadb] 读取 socket 失败: %s', _e)

    procs = getRunningMariadbdProcs()
    if not procs and not _procAvailable():
        return {'status': 'unknown', 'ours': [], 'stale': [], 'foreign': [],
                'datadir_exists': bool(datadir) and os.path.isdir(datadir),
                'socket_exists': bool(socket_file) and os.path.exists(socket_file),
                'reason': ''}

    ours = []
    stale = []
    foreign = []
    our_cmd_marks = (our_dir + '/bin/mariadbd', our_dir + '/bin/mysqld')
    for p in procs:
        exe = os.path.realpath(p['exe']) if p['exe'] else ''
        is_ours = bool(exe) and (exe in our_exes or exe.startswith(our_dir + os.sep))
        if not is_ours and exe:
            is_ours = any(mark in p['cmdline'] for mark in our_cmd_marks)
        if is_ours and p.get('deleted'):
            stale.append(p)
        elif is_ours:
            ours.append(p)
        else:
            foreign.append(p)

    datadir_exists = bool(datadir) and os.path.isdir(datadir)
    socket_exists = bool(socket_file) and os.path.exists(socket_file)

    if stale and not ours and not foreign:
        status = 'stale_ours'
        reason = ('本插件的 mariadbd 是上次卸载/升级残留（程序文件已删除但进程还在，pid=%s），'
                  '它会一直占着 3306 并让新实例无法初始化。点面板「卸载」或重装本插件即可清理'
                  % [p['pid'] for p in stale])
    elif not procs:
        status = 'not_running'
        reason = 'MariaDB 进程未运行'
    elif ours and not foreign:
        status = 'ok'
        reason = ''
    elif foreign and not (ours or stale):
        status = 'foreign_only'
        reason = ('本机正在运行的 mariadbd/mysqld 不是本面板的实例（进程：%s），'
                  '很可能是系统里另装过 MySQL/MariaDB 占用了 3306。'
                  '请先停掉它（systemctl stop mysql / systemctl stop mariadb / '
                  'apt remove --purge mysql-server mariadb-server）再重装本插件'
                  % ', '.join('%s(%s)' % (p['pid'], p['exe'] or p['cmdline'][:60])
                              for p in foreign[:3]))
    else:
        status = 'mixed'
        reason = '同时存在本面板与其他 MySQL/MariaDB 实例，端口冲突会导致口令/数据错乱，请只保留一个'

    if status == 'ok' and not datadir_exists:
        status = 'datadir_missing'
        reason = '数据目录不存在（%s）：MariaDB 未完成初始化（install 阶段被跳过或失败）' % (datadir or '未知')

    return {'status': status, 'ours': ours + stale, 'stale': stale, 'foreign': foreign,
            'datadir_exists': datadir_exists, 'socket_exists': socket_exists,
            'reason': reason}


def _result(status, msg):
    """构造**内部**结果 dict：翻译照做（走 i18n），但**不**序列化成 JSON 字符串。

    不能直接用 `yf.returnJson`：那是给「即将输出到 HTTP/CLI 的最后一步」用的，
    返回 str；内部函数一旦返回 str，调用方 `.get('status')` 就炸。
    """
    try:
        res = yf.returnMsg(status, msg)
        if isinstance(res, dict):
            return {'status': bool(res.get('status')), 'msg': res.get('msg', msg)}
    except Exception as _e:
        _log.debug('[mariadb] returnMsg 异常，回退原文案: %s', _e)
    return {'status': bool(status), 'msg': msg}


def _resultDict(res):
    """把内部返回值统一成 dict（dict 原样 / JSON 串解析 / 其余按失败文本）。

    历史坑（mysql 插件踩过、CI 直接红在 `'str' object has no attribute 'get'`）：
    某个内部函数返回了 JSON **字符串**，调用方却按 dict 用 `.get('status')`。
    这里做一次归一化，保证无论上游返回哪种形态都不会崩、也不会「假失败」。
    """
    if isinstance(res, dict):
        return res
    if isinstance(res, (bytes, bytearray)):
        try:
            res = res.decode('utf-8', 'replace')
        except Exception:
            res = str(res)
    if isinstance(res, str):
        try:
            val = json.loads(res)
            if isinstance(val, dict):
                return val
        except Exception as _e:
            _log.debug('[mariadb] 内部结果不是 JSON，按失败文本处理: %s', _e)
        return {'status': False, 'msg': res}
    return {'status': False, 'msg': str(res)}


def selfCheck(version=''):
    """安装/修复后的整体自检：归属 → 数据目录 → socket/TCP 连通性。

    存在的意义：旧 install.sh 只看 `[ -d $serverPath/mariadb/data/mysql ]` 就算成功，
    于是「3306 被别的实例占着、自己的 data 没初始化 / root 口令与面板不一致」也能报
    「安装完成」，用户点数据库管理才看到「数据库密码错误」。

    返回值必须是 **dict**（`{'status': bool, 'msg': str}`）：调用方（`fix_db_access`
    与 `self_check` 命令行）都按 dict 取值，想输出 JSON 由调用方自己 `json.dumps`。
    """
    own = instanceOwnership()
    if own['status'] in ('foreign_only', 'mixed', 'stale_ours'):
        return _result(False, '实例异常: ' + own['reason'])
    if not own['datadir_exists']:
        return _result(False, '实例异常: ' + (own['reason'] or '数据目录不存在'))
    if own['status'] == 'not_running':
        return _result(False, 'MariaDB未启动')

    serverdir = getServerDir()
    mysql_bin = serverdir + '/bin/mariadb'
    if not os.path.exists(mysql_bin):
        mysql_bin = serverdir + '/bin/mysql'
    pwd = getRootPwd()
    sock = getSocketFile()
    port = getDbPort()

    # 只读验证，不改口令：口令不一致属于「点【修复】」的场景，不该在自检里偷偷改库。
    details = []
    if sock and os.path.exists(sock):
        ok, d = db_root.verify_pwd(mysql_bin, pwd, socket_file=sock, timeout=15)
        if ok:
            return _result(True, '自检通过')
        details.append('socket: ' + d)
    ok, d = db_root.verify_pwd(mysql_bin, pwd, port=port, host='127.0.0.1', timeout=15)
    if ok:
        return _result(True, '自检通过')
    details.append('TCP: ' + d)
    return _result(False, '连接自检失败: ' + ' | '.join(details))


def cleanOrphanSockets():
    """
    仅在确认没有任何 mariadb/mysqld 进程存活时，安全清理残留孤儿套接字死锁
    """
    if getMariadbPid() is not None:
        return
    candidate_socks = [
        getSocketFile(),
        '/tmp/mysql.sock',
        '/tmp/mysql.sock.lock',
        '/tmp/mariadb.sock',
        getServerDir() + '/mysql.sock',
        getServerDir() + '/data/mysql.sock'
    ]
    for s in candidate_socks:
        if s and os.path.exists(s):
            try:
                os.remove(s)
            except Exception as _e:
                _log.debug('[mariadb] cleanOrphanSockets 异常已忽略: %s', _e)


def upgradeSelfHealing(version=''):
    """
    MariaDB 平滑无损升级与环境自愈核心接口：
    1. 刷新 systemd 服务配置与重载；
    2. 幂等补齐 SQLite databases.rw 权限字段；
    3. 同步 root 密码快照 (mysql_root.pl, default.pl)；
    4. 清理孤儿套接字死锁，多模态检测状态并自愈写回 PID。
    """
    logs = []
    logs.append("开始执行 MariaDB 插件平滑无损升级与环境自愈流程...")

    target_ver = str(version).strip()
    if not target_ver:
        version_pl = getServerDir() + "/version.pl"
        if os.path.exists(version_pl):
            target_ver = yf.readFile(version_pl).strip()
        else:
            target_ver = '10.6'

    # 1. 刷新 systemd 服务配置
    try:
        initDreplace()
        system_dir = yf.systemdCfgDir()
        service = system_dir + '/mariadb.service'
        if os.path.exists(system_dir):
            tpl = getPluginDir() + '/init.d/mariadb.service.tpl'
            if os.path.exists(tpl):
                content = yf.readFile(tpl).replace('{$SERVER_PATH}', yf.getServerDir())
                if not os.path.exists(service) or yf.readFile(service) != content:
                    yf.writeFile(service, content)
                    yf.execShell('systemctl daemon-reload')
        logs.append("MariaDB systemd 服务配置已自愈校准。")
    except Exception as ex:
        logs.append(f"服务配置自愈警告: {ex}")

    # 2. 检查目录权限
    try:
        if not yf.isAppleSystem():
            yf.execShell('chown -R mysql:mysql ' + getServerDir())
            ddir = getDataDir()
            if os.path.exists(ddir):
                yf.execShell('chown -R mysql:mysql ' + ddir)
                yf.execShell('chmod 750 ' + ddir)
        logs.append("MariaDB 目录权限已校准。")
    except Exception as ex:
        logs.append(f"权限校准警告: {ex}")

    # 3. 幂等迁移 SQLite 数据库字段与密码同步
    try:
        psdb = pSqliteDb('databases')
        root_pwd = getRootPwd() or ''
        if root_pwd:
            root_pl = getServerDir() + '/mysql_root.pl'
            default_pl = getServerDir() + '/default.pl'
            # P2-4：这两个快照文件是**明文**口令（给 `bs 10 / show_panel_pwd` 显示用），
            # 落盘后立刻收紧到 0600；chmod 失败记日志，绝不静默留 0644。
            if not os.path.exists(root_pl):
                yf.writeFile(root_pl, root_pwd)
                _chmod600(root_pl)
            if not os.path.exists(default_pl):
                yf.writeFile(default_pl, root_pwd)
                _chmod600(default_pl)
        logs.append("SQLite 元数据与 root 密码快照已自动同步。")
    except Exception as ex:
        logs.append(f"元数据同步警告: {ex}")

    # 4. 健康状态自愈
    st = status(target_ver)
    if st != 'start':
        logs.append("检测到 MariaDB 服务未处于运行状态，正在尝试安全拉起...")
        start_res = start(target_ver)
        logs.append(f"启动结果: {start_res}")
    else:
        logs.append("MariaDB 服务正在稳定运行中，PID 已自动对齐校准。")

    final_status = status(target_ver)
    is_ok = (final_status == 'start')
    logs.append(f"自愈完成，最终服务运行状态: {final_status}")
    return yf.returnJson(is_ok, "\n".join(logs), {'status': final_status, 'version': target_ver})


def _migrate_mariadb_1_to_2(version=''):
    """MariaDB 1.x -> 2.0 升级自愈迁移"""
    return upgradeSelfHealing(version)


# 迁移流水线配置：(目标大版本, 迁移执行函数)
# 保留后续扩展接口：未来升级至 2.1, 3.0 等只需在此追加注册
MARIADB_MIGRATION_STEPS = [
    ('2.0', _migrate_mariadb_1_to_2),
]


def checkPluginUpgrade(version=''):
    """
    MariaDB 大版本升级检测与单次自愈迁移函数：
    1. 检查已持久化的版本号，若已达到当前版本直接放行（耗时微秒级，零损耗）；
    2. 当检测到从 1.x 升级到 2.x 时，自动触发且仅触发一次自愈；
    3. 成功后更新版本号到本地文件，保证升级后只执行一次；
    4. 保留未来版本迁移路由接口。
    """
    global _MARIADB_UPGRADE_CHECKING
    if _MARIADB_UPGRADE_CHECKING:
        return {'status': True, 'msg': 'Upgrade checking already in progress'}

    installed_ver = getInstalledPluginVersion()
    target_ver = CURRENT_PLUGIN_VERSION

    if comparePluginVersion(installed_ver, target_ver) >= 0:
        return {'status': True, 'msg': 'Already up to date', 'version': installed_ver}

    _MARIADB_UPGRADE_CHECKING = True
    migration_logs = []
    success = True
    current_v = installed_ver

    try:
        for step_ver, step_func in MARIADB_MIGRATION_STEPS:
            if comparePluginVersion(current_v, step_ver) < 0:
                try:
                    res = step_func(version)
                    migration_logs.append(f"升级迁移 {current_v} -> {step_ver} 执行成功: {res}")
                    current_v = step_ver
                    setInstalledPluginVersion(step_ver)
                except Exception as ex:
                    success = False
                    migration_logs.append(f"升级迁移 {current_v} -> {step_ver} 发生异常: {ex}")
                    break

        if success and comparePluginVersion(current_v, target_ver) < 0:
            setInstalledPluginVersion(target_ver)
    finally:
        _MARIADB_UPGRADE_CHECKING = False

    return {
        'status': success,
        'installed_version': installed_ver,
        'target_version': target_ver,
        'logs': migration_logs
    }


def status(version=''):
    """
    多模态精准健康状态检查与 PID 自动自愈
    """
    # 0. 升级守卫：仅在检测到版本升级时静默自愈一次，之后 0 开销放行
    try:
        checkPluginUpgrade(version)
    except Exception as _e:
        _log.debug('[mariadb] status 异常已忽略: %s', _e)

    # 1. 优先检查标准 PID 文件中的进程真实存活性
    pid_file = getPidFile()
    if os.path.exists(pid_file):
        try:
            pid_str = yf.readFile(pid_file).strip()
            if pid_str and pid_str.isdigit():
                pid_int = int(pid_str)
                if yf.checkPid(pid_int):
                    return 'start'
        except Exception as _e:
            _log.debug('[mariadb] status 异常已忽略: %s', _e)

    # 2. 多模态探活：PID 文件失效或丢失时，探测系统真实运行中的 mariadb
    live_pid = getMariadbPid()
    if live_pid is not None:
        # 自动自愈：将真实存活的 PID 写回 pid_file，保证后续快速探针直接命中。
        # 必须走 yf.syncPidFile：面板以 root 运行而 mariadbd 以 mysql 用户运行，
        # 直接写会把 pid 文件属主改成 root，导致服务下次启动无法创建 pid 文件
        # 而启动失败（mysql 插件已真机复现该 P0：Errcode 13 - Permission denied）。
        yf.syncPidFile(pid_file, live_pid)
        return 'start'

    # 3. Socket 响应探针
    sock_path = getSocketFile()
    if sock_path and os.path.exists(sock_path):
        import socket
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect(sock_path)
            s.close()
            # 能握手说明 mariadbd 绝对存活（写回同样必须走安全助手，见上方说明）
            yf.syncPidFile(pid_file, getMariadbPid())
            return 'start'
        except Exception as _e:
            _log.debug('[mariadb] status 异常已忽略: %s', _e)

    # 4. systemctl 兜底状态确认
    if not yf.isAppleSystem():
        try:
            sc_res = yf.execShell('systemctl is-active mariadb')
            if sc_res and sc_res[0].strip() == 'active':
                yf.syncPidFile(pid_file, getMariadbPid())
                return 'start'
        except Exception as _e:
            _log.debug('[mariadb] status 异常已忽略: %s', _e)

    return 'stop'


def binLog():
    args = getArgs()
    conf = getConf()
    con = yf.readFile(conf)

    if con.find('#log-bin=mysql-bin') != -1:
        if 'status' in args:
            return yf.returnJson(False, '0')
        con = con.replace('#log-bin=mysql-bin', 'log-bin=mysql-bin')
        con = con.replace('#binlog_format=mixed', 'binlog_format=mixed')
        yf.writeFile(conf, con)
        yf.execShell('sync')
        restart()
    else:
        path = getDataDir()
        if 'status' in args:
            dsize = 0
            for n in os.listdir(path):
                if len(n) < 9:
                    continue
                if n[0:9] == 'mysql-bin':
                    dsize += os.path.getsize(path + '/' + n)
            return yf.returnJson(True, dsize)
        con = con.replace('log-bin=mysql-bin', '#log-bin=mysql-bin')
        con = con.replace('binlog_format=mixed', '#binlog_format=mixed')
        yf.writeFile(conf, con)
        yf.execShell('sync')
        restart()
        yf.execShell('rm -f ' + path + '/mysql-bin.*')

    
    return yf.returnJson(True, '设置成功!')

def binLogList():
    args = getArgs()
    data = checkArgs(args, ['page', 'page_size', 'tojs'])
    if not data[0]:
        return data[1]

    # 分页参数容错：历史缺校验，page=abc 直接 ValueError traceback 到前端
    try:
        page = int(str(args['page']).strip())
        page_size = int(str(args['page_size']).strip())
    except (TypeError, ValueError):
        return yf.returnJson(False, '分页参数不合法!')
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10
    elif page_size > 100:
        page_size = 100

    data_dir = getDataDir()
    log_bin_name = getLogBinName()

    alist = os.listdir(data_dir)
    log_bin_l = []
    for x in range(len(alist)):
        f = alist[x]
        t = {}
        if f.startswith(log_bin_name) and not f.endswith('.index'):
            abspath = data_dir + '/' + f
            t['name'] = f
            t['size'] = os.path.getsize(abspath)
            t['time'] = yf.getDataFromInt(os.path.getctime(abspath))
            log_bin_l.append(t)

    log_bin_l = sorted(log_bin_l, key=lambda x: x['time'], reverse=True)

    # print(log_bin_l)
    # print(data_dir, log_bin_name)

    count = len(log_bin_l)

    page_start = (page - 1) * page_size
    page_end = page_start + page_size
    if page_end > count:
        page_end = count

    data = {}
    page_args = {}
    page_args['count'] = count
    page_args['p'] = page
    page_args['row'] = page_size
    # 缺 tojs 时回退到本接口的前端回调（js/mariadb.js::myBinLogsRender，它自己就是
    # `api.post('binlog_list', ...)` 的发起方）；历史上缺参即 KeyError traceback。
    page_args['tojs'] = args.get('tojs', 'myBinLogsRender')
    data['page'] = yf.getPage(page_args)
    data['data'] = log_bin_l[page_start:page_end]

    return yf.getJson(data)


def cleanBinLog():
    db = pMysqlDb()
    cleanTime = time.strftime('%Y-%m-%d %H:%i:%s', time.localtime())
    db.execute("PURGE MASTER LOGS BEFORE '" + cleanTime + "';")
    return yf.returnJson(True, '清理BINLOG成功!')


def getErrorLog():
    args = getArgs()
    path = getDataDir()
    filename = ''
    for n in os.listdir(path):
        if len(n) < 5:
            continue
        if n == 'error.log':
            filename = path + '/' + n
            break
    # print filename
    if not os.path.exists(filename):
        return yf.returnJson(False, '指定文件不存在!')
    if 'close' in args:
        yf.writeFile(filename, '')
        return yf.returnJson(False, '日志已清空')
    info = yf.getLastLine(filename, 18)
    return yf.returnJson(True, 'OK', info)


def getShowLogFile():
    # 未配置时返回空串（旧实现会直接 AttributeError），由调用方按「无慢日志」处理
    return _cnfValue(r'slow-query-log-file\s*=\s*(.*)')


def pGetDbUser():
    if yf.isAppleSystem():
        user = yf.execShell(
            "who | sed -n '2, 1p' |awk '{print $1}'")[0].strip()
        return user
    return 'mysql'


def initMysqlData():
    datadir = getDataDir()
    if not os.path.exists(datadir + '/mysql'):
        serverdir = getServerDir()
        myconf = serverdir + "/etc/my.cnf"
        user = pGetDbUser()
        cmd = 'cd ' + serverdir + ' && ./scripts/mariadb-install-db ' + \
            ' --defaults-file=' + myconf
        data = yf.execShell(cmd)
        # print(data[0])
        # print(data[1])

        if not yf.isAppleSystem():
            yf.execShell('chown -R mysql:mysql ' + serverdir + '/data')
            yf.execShell('chmod -R 755 ' + serverdir + '/data')
        return False
    return True


def _applyRootPwd(pwd, current_pwd=None, scene='初始化'):
    """把 root 口令写入**全部本地 host**（localhost / 127.0.0.1 / ::1）并验证。

    与 mysql 插件同一个实现（`web/core/db_root.py`）。只改 `root@localhost` 是
    「安装完就提示数据库密码错误」的根因：`mariadb-install-db` 会建
    `root@127.0.0.1` / `root@::1`，插件 my.cnf 又带 `skip_name_resolve=1`，
    此时走 TCP 的连接会拿 127.0.0.1 那条的**旧（空）口令**去认证，报 1045。

    验证通过才保存口令（旧实现无论成败都先 `_saveRootPwd`，失败后
    面板记的口令与库里永远对不上）。
    """
    serverdir = getServerDir()
    res = db_root.apply_root_pwd(
        mysql_bin=serverdir + '/bin/mariadb',
        version='10.0',
        pwd=pwd,
        myconf=serverdir + '/etc/my.cnf',
        socket_file=getSocketFile(),
        port=getDbPort(),
        current_pwd=current_pwd,
    )
    if res.ok:
        _saveRootPwd(pwd)
        return True
    yf.writeFileLog('[mariadb] %s时写入 root 口令失败（未保存新口令）: %s'
                    % (scene, res.detail or res))
    return False


def _waitDbReady(myconf, timeout=60):
    """等 mariadb 可无口令连上（初始化后首次启动可能还在做数据目录初始化）。"""
    serverdir = getServerDir()
    mysql_bin = serverdir + '/bin/mariadb'
    deadline = time.time() + timeout
    while time.time() < deadline:
        ok, _detail = db_root.run_sql(mysql_bin, 'SELECT 1;', myconf=myconf, pwd=None, timeout=15)
        if ok:
            return True
        time.sleep(2)
    yf.writeFileLog('[mariadb] 等待数据库就绪超时（%ss），仍将尝试写入 root 口令' % timeout)
    return False


def initMariaDbPwd():
    serverdir = getServerDir()
    myconf = serverdir + "/etc/my.cnf"
    pwd = yf.getRandomString(16)

    # 固定 sleep 不可靠（慢机器没 ready 就发 SQL，失败又没人看）：改为探活
    _waitDbReady(myconf)

    if not _applyRootPwd(pwd, current_pwd=None, scene='首次安装初始化'):
        # 不保存没生效的口令，返回 False 让调用方记日志（服务本身是好的）
        return False

    db_option = "-S " + getSocketFile()

    # 删除空账户
    drop_empty_user = serverdir + '/bin/mysql ' + db_option + ' -uroot -p' + \
        pwd + ' -e "use mysql;delete from user where USER=\'\'"'
    yf.execShell(drop_empty_user)

    # 删除测试数据库
    drop_test_db = serverdir + '/bin/mysql ' + db_option + ' -uroot -p' + \
        pwd + ' -e "drop database test";'
    yf.execShell(drop_test_db)

    # 删除冗余账户
    # hostname 来自 `hostname` 命令输出（OS 派生）：既进 shell 又进 SQL。
    # 旧实现把 hostname 裸拼进 `-e "drop user ''@'<hostname>'"`：双引号内 `"`/`$()`/反引号
    # 会逃逸成 root 命令注入。这里 SQL 层转义单引号，整条 `-e` 参数再走 yf.shlexQuote。
    hostname = yf.execShell('hostname')[0].strip()
    if hostname != 'localhost':
        sql_hostname = hostname.replace("'", "''")
        drop_hostname =  serverdir + '/bin/mysql  --defaults-file=' + \
            myconf + ' -uroot -p' + pwd + ' -e ' + \
            yf.shlexQuote("drop user ''@'" + sql_hostname + "'")
        yf.execShell(drop_hostname)

        drop_root_hostname =  serverdir + '/bin/mysql  --defaults-file=' + \
            myconf + ' -uroot -p' + pwd + ' -e ' + \
            yf.shlexQuote("drop user 'root'@'" + sql_hostname + "'")
        yf.execShell(drop_root_hostname)
    return True


def myOp(version, method):
    # import commands
    init_file = initDreplace()
    cmd = init_file + ' ' + method
    try:
        isInited = initMysqlData()
        if not isInited:
            if yf.isAppleSystem():
                setSkipGrantTables(True)
                cmd_init_start = [init_file, 'start']
                subprocess.Popen(cmd_init_start, stdout=subprocess.PIPE, shell=False,
                                 bufsize=4096, stderr=subprocess.PIPE)

                time.sleep(6)
            else:
                yf.execShell('systemctl start mariadb')

            if not initMariaDbPwd():
                yf.writeFileLog('[mariadb] 首次安装后设置 root 口令失败（性能/当前状态会报密码错误），'
                                '请在数据库管理列表点【修复】重试')

            if yf.isAppleSystem():
                setSkipGrantTables(False)
                cmd_init_stop = [init_file, 'stop']
                subprocess.Popen(cmd_init_stop, stdout=subprocess.PIPE, shell=False,
                                 bufsize=4096, stderr=subprocess.PIPE)
                time.sleep(3)
            else:
                yf.execShell('systemctl stop mariadb')

        if yf.isAppleSystem():
            sub = subprocess.Popen([init_file, method], stdout=subprocess.PIPE, shell=False,
                                   bufsize=4096, stderr=subprocess.PIPE)
            sub.wait(5)
        else:
            yf.execShell('systemctl ' + method + ' mariadb')

        return 'ok'
    except Exception as e:
        return str(e)


def appCMD(version, action):
    makeInitRsaKey(version)
    return myOp(version, action)


def start(version=''):
    # 0. 僵尸进程处理（与 mysql 插件同一口径）：上次卸载只 rm -rf 没停进程时，
    #    mariadbd 会带着已删除的 datadir/socket 继续占 3306。此时 status() 会把它
    #    当「在跑」→ 直接 return ok → **初始化被整段跳过**（/www/server/mariadb/data
    #    永远造不出来），之后所有查询都连到这个僵尸上（密码不符 → 1045）。
    #    这里先把它清掉，让下面的正常流程去做 initialize + 设口令。
    try:
        _own = instanceOwnership()
        if _own.get('status') == 'stale_ours':
            yf.writeFileLog('[mariadb] 发现卸载残留的 mariadbd（程序文件已删除），先清理: %s'
                            % [p['pid'] for p in _own.get('stale') or []])
            stopAndKill(version)
    except Exception as _e:
        _log.debug('[mariadb] 僵尸进程清理异常（继续按常规启动）: %s', _e)

    # 1. 状态自愈与防误杀：若服务已在正常运行，坚决禁止 pkill -9 强杀！
    st = status(version)
    if st == 'start':
        return 'ok'
    cleanOrphanSockets()
    res = appCMD(version, 'start')
    for _ in range(8):
        if status(version) == 'start':
            return 'ok'
        time.sleep(1)
    # 8 秒仍未就绪：如实返回失败，绝不把 'ok' 回给上层造成「已启动」误判
    return 'error: mariadb 启动后未就绪（%s）' % res


def stop(version=''):
    return appCMD(version, 'stop')


def restart(version=''):
    stop(version)
    time.sleep(1)
    cleanOrphanSockets()
    res = appCMD(version, 'start')
    for _ in range(8):
        if status(version) == 'start':
            return 'ok'
        time.sleep(1)
    # 8 秒仍未就绪：如实返回失败（上层据此兜底拉起 / 报错，而非误以为重启成功）
    return 'error: mariadb 重启后未就绪（%s）' % res


def reload(version=''):
    return appCMD(version, 'reload')


def initdStatus():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    shell_cmd = 'systemctl status mariadb | grep loaded | grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    yf.execShell('systemctl enable mariadb')
    return 'ok'


def initdUinstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    # 只 disable 不 stop：进程会带着已删除的 datadir 继续占着 3306，
    # 重装后表现为「数据库密码错误」（与 mysql 插件同一类现场）
    yf.execShell('systemctl stop mariadb')
    yf.execShell('systemctl disable mariadb')
    return 'ok'


def runMariaUpgrade(version=''):
    """跨版本升级后跑 `mariadb-upgrade`（10.4+ 才有这个命令；老版本用 mysql_upgrade）。

    失败不阻断升级（二进制与数据都已换好，系统表升级失败只影响新特性，会在
    装后自检的连通性里体现），但必须把输出写进任务日志便于追查。
    """
    serverdir = getServerDir()
    bin_path = ''
    for cand in ('/bin/mariadb-upgrade', '/bin/mysql_upgrade'):
        if os.path.isfile(serverdir + cand):
            bin_path = serverdir + cand
            break
    if not bin_path:
        return yf.returnJson(False, 'mariadb-upgrade not found under %s/bin' % serverdir)

    pwd = getRootPwd()
    fd = None
    path = ''
    try:
        fd, path = tempfile.mkstemp(prefix='bt_mariadb_upg_', suffix='.cnf')
        content = '[client]\nuser=root\npassword="%s"\nsocket=%s\n' % (
            str(pwd).replace('\\', '\\\\').replace('"', '\\"'),
            getSocketFile())
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(content)
        try:
            os.chmod(path, 0o600)
        except OSError as e:
            _log.debug('[mariadb] 收紧 mariadb-upgrade 临时文件权限失败: %s', e)
    except Exception as e:
        return yf.returnJson(False, 'mariadb_upgrade: cannot prepare credentials (%s)'
                             % str(e)[:80])

    try:
        rc, out, err = yf.execShellRc(
            [bin_path, '--defaults-extra-file=' + path, '--force'],
            shell=False, timeout=1800)
    except Exception as e:
        yf.writeFileLog('[mariadb] mariadb-upgrade 执行异常: %s' % str(e)[:200])
        return yf.returnJson(False, 'mariadb_upgrade: execution error')
    finally:
        try:
            os.remove(path)
        except OSError as e:
            _log.debug('[mariadb] 删除 mariadb-upgrade 临时文件失败: %s', e)

    text = ' '.join(((out or '') + ' ' + (err or '')).split())[:400]
    if rc != 0:
        yf.writeFileLog('[mariadb] mariadb-upgrade 返回 %s: %s' % (rc, text))
        return yf.returnJson(False, 'mariadb_upgrade rc=%s: %s' % (rc, text))
    yf.writeFileLog('[mariadb] mariadb-upgrade 完成: %s' % text)
    return yf.returnJson(True, 'mariadb_upgrade ok')


def stopAndKill(version=''):
    """停服务 + 杀掉「exe 属于本插件」的残留 mariadbd/mysqld（卸载/重装前调用）。

    旧卸载路径只有 rm -rf（initd_uninstall 也只 disable 不 stop），
    僵尸进程会占着 3306，导致下一次安装完仍不可用。
    """
    import signal as _sig
    import time as _time

    logs = []
    try:
        stop(version)
        logs.append('已请求停止 mariadb 服务')
    except Exception as _e:
        logs.append('停止服务异常: %s' % _e)

    serverdir = os.path.realpath(getServerDir())
    ours = []
    if os.path.isdir('/proc'):
        for name in os.listdir('/proc'):
            if not name.isdigit():
                continue
            try:
                exe = os.path.realpath(os.readlink('/proc/%s/exe' % name))
            except Exception:
                continue
            if exe.startswith(serverdir + os.sep) and os.path.basename(exe) in ('mariadbd', 'mysqld'):
                ours.append(int(name))
    for sig, wait in ((_sig.SIGTERM, 2.0), (_sig.SIGKILL, 1.0)):
        for pid in ours:
            try:
                os.kill(pid, sig)
            except Exception as _e:
                _log.debug('[mariadb] kill(%s) 失败: %s', pid, _e)
        if not ours:
            break
        _time.sleep(wait)
        alive = []
        for pid in ours:
            try:
                os.kill(pid, 0)
                alive.append(pid)
            except OSError as _e:
                # 进程已退出（ESRCH）/无权限：都不算「还活着」
                _log.debug('[mariadb] pid %s 存活探测失败（视为已退出）: %s', pid, _e)
        if not alive:
            logs.append('残留进程已清理')
            break
        ours = alive

    try:
        initdUinstall()
    except Exception as _e:
        logs.append('移除自启配置异常: %s' % _e)

    if ours:
        return yf.returnJson(False, '清理未彻底: mariadbd 仍在运行（pid=%s）' % ours)
    return yf.returnJson(True, '卸载清理完成')


def getMyDbPos():
    return _cnfValue(r'datadir\s*=\s*(.*)', getServerDir() + '/data')


def setMyDbPos():
    args = getArgs()
    data = checkArgs(args, ['datadir'])
    if not data[0]:
        return data[1]

    s_datadir = getMyDbPos()
    t_datadir = yf.safeDatadir(args['datadir'])
    if not t_datadir:
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')
    if t_datadir == s_datadir:
        return yf.returnJson(False, '与当前存储目录相同，无法迁移文件!')

    if not os.path.exists(t_datadir):
        yf.makeDirs(t_datadir)

    # 拼接侧双保险：datadir 已过白名单，仍逐段 shlexQuote，`/*` 保持未引用以维持 glob
    q_s_datadir = yf.shlexQuote(s_datadir)
    q_t_datadir = yf.shlexQuote(t_datadir)
    stop()
    yf.execShell('cp -rf ' + q_s_datadir + '/* ' + q_t_datadir + '/')
    yf.execShell('chown -R mysql mysql ' + q_t_datadir)
    yf.execShell('chmod -R 755 ' + q_t_datadir)
    yf.execShell('rm -f ' + q_t_datadir + '/*.pid')
    yf.execShell('rm -f ' + q_t_datadir + '/*.err')

    path = getServerDir()
    myfile = path + '/etc/my.cnf'
    mycnf = yf.readFile(myfile)
    yf.writeFile(path + '/etc/my_backup.cnf', mycnf)

    mycnf = mycnf.replace(s_datadir, t_datadir)
    yf.writeFile(myfile, mycnf)
    start()

    result = yf.execShell(
        'ps aux|grep mysqld| grep -v grep|grep -v python')
    if len(result[0]) > 10:
        yf.writeFile('data/datadir.pl', t_datadir)
        return yf.returnJson(True, '存储目录迁移成功!')
    else:
        yf.execShell('pkill -9 mysqld')
        yf.writeFile(myfile, yf.readFile(path + '/etc/my_backup.cnf'))
        start()
        return yf.returnJson(False, '文件迁移失败!')


def getMyPort():
    return _cnfValue(r'port\s*=\s*(.*)', '3306')


def setMyPort():
    args = getArgs()
    data = checkArgs(args, ['port'])
    if not data[0]:
        return data[1]

    # 端口先白名单校验再写盘：历史缺校验，`abc` 会被写进 my.cnf 使 mariadb 起不来，
    # 接口仍回「编辑成功!」（假成功）。
    port = str(args['port']).strip()
    if not re.match(r"^[0-9]+$", port) or not (1 <= int(port) <= 65535):
        return yf.returnJson(False, '端口不合法!')
    file = getConf()
    content = yf.readFile(file)
    if not content:
        return yf.returnJson(False, '配置文件中未找到端口配置!')
    rep = r"port\s*=\s*([0-9]+)\s*\n"
    if not re.search(rep, content):
        return yf.returnJson(False, '配置文件中未找到端口配置!')
    content = re.sub(rep, 'port = ' + port + '\n', content)
    yf.writeFile(file, content)
    res = restart()
    if res != 'ok':
        return yf.returnJson(False, '修改端口后服务未就绪: ' + str(res))
    return yf.returnJson(True, '编辑成功!')

# python3 plugins/mariadb/index.py run_info  {}
def runInfo(version):

    if status(version) == 'stop':
        return yf.returnJson(False, 'MySQL未启动', [])

    # 与 mysql 插件同一类现场（2026-10-27）：数据目录不存在时下面 query 必然失败，
    # 报出来的又是「数据库密码错误」，用户怎么点【修复】都没用。这里先判目录。
    datadir = ''
    try:
        datadir = getDataDir()
    except Exception as _e:
        _log.debug('[mariadb] 读取 datadir 失败: %s', _e)
    if not datadir or not os.path.isdir(datadir):
        return yf.returnJson(False, '实例异常: 数据目录不存在（%s），MariaDB 未完成初始化或端口被其他实例占用'
                             % (datadir or '未知'), [])

    db = pMysqlDb()
    data = db.query('show global status')
    isError = isSqlError(data)
    if isError != None:
        return isError

    gets = ['Max_used_connections', 'Com_commit', 'Com_rollback', 'Questions', 'Innodb_buffer_pool_reads', 'Innodb_buffer_pool_read_requests', 'Key_reads', 'Key_read_requests', 'Key_writes',
            'Key_write_requests', 'Qcache_hits', 'Qcache_inserts', 'Bytes_received', 'Bytes_sent', 'Aborted_clients', 'Aborted_connects',
            'Created_tmp_disk_tables', 'Created_tmp_tables', 'Innodb_buffer_pool_pages_dirty', 'Opened_files', 'Open_tables', 'Opened_tables', 'Select_full_join',
            'Select_range_check', 'Sort_merge_passes', 'Table_locks_waited', 'Threads_cached', 'Threads_connected', 'Threads_created', 'Threads_running', 'Connections', 'Uptime']

    result = {}
    # print(data)
    for d in data:
        vname = d["Variable_name"]
        for g in gets:
            if vname == g:
                result[g] = d["Value"]

    # print(result, int(result['Uptime']))
    result['Run'] = int(time.time()) - int(result['Uptime'])
    tmp = db.query('show master status')
    try:
        result['File'] = tmp[0]["File"]
        result['Position'] = tmp[0]["Position"]
    except Exception as _e:
        _log.debug('[mariadb] runInfo 异常已忽略: %s', _e)
        result['File'] = 'OFF'
        result['Position'] = 'OFF'
    return yf.getJson(result)


def myDbStatus():
    result = {}
    db = pMysqlDb()
    data = db.query('show variables')
    isError = isSqlError(data)
    if isError != None:
        return isError

    gets = ['table_open_cache', 'thread_cache_size', 'key_buffer_size', 'tmp_table_size', 'max_heap_table_size', 'innodb_buffer_pool_size',
            'innodb_additional_mem_pool_size', 'innodb_log_buffer_size', 'max_connections', 'sort_buffer_size', 'read_buffer_size', 'read_rnd_buffer_size', 'join_buffer_size', 'thread_stack', 'binlog_cache_size']
    result['mem'] = {}
    for d in data:
        vname = d['Variable_name']
        for g in gets:
            # print(g)
            if vname == g:
                result['mem'][g] = d["Value"]
    return yf.getJson(result)


def setDbStatus():
    gets = ['key_buffer_size', 'tmp_table_size', 'max_heap_table_size', 'innodb_buffer_pool_size', 'innodb_log_buffer_size', 'max_connections',
            'table_open_cache', 'thread_cache_size', 'sort_buffer_size', 'read_buffer_size', 'read_rnd_buffer_size', 'join_buffer_size', 'thread_stack', 'binlog_cache_size']
    emptys = ['max_connections', 'thread_cache_size', 'table_open_cache']
    args = getArgs()
    conFile = getConf()
    content = yf.readFile(conFile)
    n = 0
    for g in gets:
        s = 'M'
        if n > 5:
            s = 'K'
        if g in emptys:
            s = ''
        rep = r'\s*' + g + r'\s*=\s*\d+(M|K|k|m|G)?\n'
        c = g + ' = ' + str(args[g]) + s + '\n'
        if content.find(g) != -1:
            content = re.sub(rep, '\n' + c, content, 1)
        else:
            content = content.replace('[mysqld]\n', '[mysqld]\n' + c)
        n += 1
    yf.writeFile(conFile, content)
    return yf.returnJson(True, '设置成功!')


def isSqlError(mysqlMsg):
    # 检测数据库执行错误
    mysqlMsg = str(mysqlMsg)
    # 后端消息契约：可翻译前缀 = 首个冒号（含）之前，必须是纯文本；
    # 换行等 HTML 必须挪到冒号之后，技术命令留在动态部分、不进语言包。
    if "MySQLdb" in mysqlMsg:
        return yf.returnJson(False, 'MySQLdb组件缺失! 进入SSH命令行输入: <br>pip install mysql-python | pip install mysqlclient==2.0.3')
    if "2002," in mysqlMsg:
        return yf.returnJson(False, '数据库连接失败,请检查数据库服务是否启动!')
    if "2003," in mysqlMsg:
        return yf.returnJson(False, "Can't connect to MySQL server on '127.0.0.1' (61)")
    if "using password:" in mysqlMsg:
        return yf.returnJson(False, "数据库密码错误,在管理列表-点击【修复】!", 'pwd')
    if "1045," in mysqlMsg:
        return yf.returnJson(False, '连接错误!')
    if "SQL syntax" in mysqlMsg:
        return yf.returnJson(False, 'SQL语法错误!')
    if "Connection refused" in mysqlMsg:
        return yf.returnJson(False, '数据库连接失败,请检查数据库服务是否启动!')
    if "1133," in mysqlMsg:
        return yf.returnJson(False, '数据库用户不存在!')
    if "1007," in mysqlMsg:
        return yf.returnJson(False, '数据库已经存在!')
    return None


def checkSqlExec(result):
    if result is None:
        return None
    err = isSqlError(result)
    if err is not None:
        return err
    if isinstance(result, Exception):
        return yf.returnJson(False, 'SQL执行失败: ' + str(result))
    return None


def __createUser(dbname, username, password, address):
    pdb = pMysqlDb('mysql')

    is_root = (username == 'root' or dbname == '*')
    db_target = '*.*' if is_root else ('`' + dbname + '`.*')

    # 口令走 ORM 参数化（pymysql 按 SQL 语义转义），不再手写 `\'`。
    # 账号名/host 一并参数化：本仓 ORM 经 pymysql 做客户端 `%` 插值，SQL 文本里只要
    # 残留一个 `%`（host 通配符）就会让 `%\`` 触发 ValueError，故不留裸 `%`。
    # 1. 创建或更新 localhost 用户
    r_local = pdb.execute(
        "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s",
        (username, 'localhost', password))
    if isSqlError(r_local) is not None or isinstance(r_local, Exception):
        pdb.execute(
            "ALTER USER %s@%s IDENTIFIED BY %s", (username, 'localhost', password))

    grant_local = "grant all privileges on %s to `%s`@`localhost`" % (db_target, username)
    if is_root:
        grant_local += " with grant option"
    pdb.execute(grant_local)

    # 2. 遍历各 host 创建与授权
    for a in address.split(','):
        a = a.strip()
        if not a or a == 'localhost':
            continue
        r_host = pdb.execute(
            "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s", (username, a, password))
        if isSqlError(r_host) is not None or isinstance(r_host, Exception):
            pdb.execute(
                "ALTER USER %s@%s IDENTIFIED BY %s", (username, a, password))
        grant_host = "grant all privileges on %s to `%s`@`%s`" % (db_target, username, a)
        if is_root:
            grant_host += " with grant option"
        pdb.execute(grant_host)

    pdb.execute("flush privileges")


def getDbBackupListFunc(dbname=''):
    bkDir = getBackupDir()
    blist = os.listdir(bkDir)
    r = []

    db_path = getServerDir()
    version_prefix = 'mariadb104'
    version_file = db_path + '/version.pl'
    if os.path.exists(version_file):
        ver = yf.readFile(version_file).strip()
        parts = ver.split('.')
        if len(parts) >= 2:
            version_prefix = parts[0] + parts[1]
        elif len(parts) == 1:
            version_prefix = parts[0]
        
        if 'mariadb' in db_path:
            version_prefix = 'mariadb' + version_prefix
        else:
            version_prefix = 'mysql' + version_prefix
    else:
        if 'mariadb' in db_path:
            version_prefix = 'mariadb104'
        else:
            version_prefix = 'mysql57'

    new_prefix = version_prefix + '_' + dbname + '_'
    old_prefix = 'db_' + dbname + '_'
    for x in blist:
        is_match = False
        if x.startswith(new_prefix) or x.startswith(old_prefix):
            is_match = True
        elif x == version_prefix + '_' + dbname + '.gz' or x == 'db_' + dbname + '.gz':
            is_match = True
        if is_match:
            r.append(x)
    return r


def setDbBackup():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not re.match(r"^[\w\.-]+$", name):
        return yf.returnJson(False, '数据库名称不合法!')

    scDir = getPluginDir() + '/scripts/backup.py'
    import subprocess
    cmd = ['python3', scDir, 'database', name, '3']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    # 旧实现直接丢弃 out/err 并无条件返回成功：备份脚本报错也会显示「备份成功」。
    # 这里与 mysql 侧对齐，必须看到明确的失败信号才允许报错。
    out_s = (out or b'').decode('utf-8', 'replace')
    err_s = (err or b'').decode('utf-8', 'replace')
    if p.returncode != 0 or '备份失败' in out_s or '备份失败' in err_s:
        _log.warning('[mariadb] setDbBackup 失败 name=%s rc=%s err=%s', name, p.returncode, err_s[:500])
        return yf.returnJson(False, '数据库备份失败: ' + name)
    return yf.returnJson(True, 'ok')


def importDbBackup():
    args = getArgs()
    data = checkArgs(args, ['file', 'name'])
    if not data[0]:
        return data[1]

    file = args['file']
    name = args['name']

    if not re.match(r"^[\w\.-]+$", name):
        return yf.returnJson(False, '数据库名称不合法!')
    if '..' in file or not re.match(r"^[\w\.\s-]+\.?(gz)?$", file):
        return yf.returnJson(False, '文件名不合法!')

    file_path = getBackupDir() + '/' + file
    file_path_sql = getBackupDir() + '/' + file.replace('.gz', '')

    import subprocess
    if not os.path.exists(file_path_sql):
        p = subprocess.Popen(['gzip', '-d', file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.communicate()

    pwd = getRootPwd()
    sock = getSocketFile()

    mysql_bin = getServerDir() + '/bin/mariadb'
    if not os.path.exists(mysql_bin):
        mysql_bin = getServerDir() + '/bin/mysql'

    cmd = [mysql_bin, '-S', sock, '-uroot', '-p' + str(pwd or ''), name]
    try:
        with open(file_path_sql, 'r', encoding='utf-8', errors='ignore') as f:
            p = subprocess.Popen(cmd, stdin=f, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = p.communicate()
            if p.returncode != 0:
                return yf.returnJson(False, '导入失败: ' + stderr.decode('utf-8', errors='ignore'))
    except Exception as e:
        return yf.returnJson(False, '导入过程发生异常: ' + str(e))

    return yf.returnJson(True, 'ok')


def rootPwd():
    return getRootPwd()


# 「导入外部 SQL 包」的安全解压组件（与 mysql 插件共用 plugins/mysql/import_archive.py）
_IMPORT_ARCHIVE_MOD = None


def _loadImportArchive():
    """加载共享的安全解压组件；加载失败返回 None（调用方按 fail-closed 拒绝导入）。

    按文件路径加载而不是 `import plugins.mysql.import_archive`：`plugins` 不是包
    （无 `__init__.py`），面板又是按脚本路径动态加载插件的，仓库根目录不保证在
    `sys.path` 里，直接 import 随时可能失败。
    """
    global _IMPORT_ARCHIVE_MOD
    if _IMPORT_ARCHIVE_MOD is not None:
        return _IMPORT_ARCHIVE_MOD
    try:
        import importlib.util
        plugins_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        mod_path = os.path.join(plugins_dir, 'mysql', 'import_archive.py')
        spec = importlib.util.spec_from_file_location('bt_import_archive', mod_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _IMPORT_ARCHIVE_MOD = mod
    except Exception as e:
        _log.warning('[mariadb] 导入包解压组件加载失败: %s', e)
        return None
    return _IMPORT_ARCHIVE_MOD


def _safeExtractImportArchive(file_path, import_dir, kind, target_name=''):
    """校验 + 解压导入包（fail-closed）。返回 (ok, import_sql, msg)。

    校验不通过或组件不可用时一律不解压：返回失败原因，目录外零落盘、目录内无残留。
    """
    mod = _loadImportArchive()
    if mod is None:
        return False, '', '导入包解压组件加载失败，已拒绝解压（未写入任何文件）'
    try:
        return mod.safeExtractImportArchive(file_path, import_dir, kind, target_name)
    except Exception as e:
        _log.warning('[mariadb] 导入包解压异常(%s): %s', file_path, e)
        return False, '', '导入包解压异常，已拒绝解压: %s' % e


# python3 plugins/mariadb/index.py import_db_external {"file":"xx.sql","name":"demo1"}
# python3 plugins/mariadb/index.py import_db_external {"file":"db_demo1_20231221_203614 2.sql","name":"demo1"}
def importDbExternal():
    args = getArgs()
    data = checkArgs(args, ['file', 'name'])
    if not data[0]:
        return data[1]

    file = args['file']
    name = args['name']

    if '..' in file or '..' in name:
        return yf.returnJson(False, '路径参数不合法!')

    import_dir = yf.getBackupDir() + '/import/'
    file_path = os.path.join(import_dir, file)
    if not os.path.exists(file_path):
        return yf.returnJson(False, '源文件不存在: ' + file, {'log': '错误: 文件未找到: ' + file_path})

    exts = ['sql', 'gz', 'zip']
    ext = yf.getFileSuffix(file)
    if ext not in exts:
        return yf.returnJson(False, '导入数据库格式不对!', {'log': '错误: 不支持的文件格式 .' + str(ext)})

    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    file_size_str = yf.toSize(file_size) if hasattr(yf, 'toSize') else str(file_size) + ' B'

    tmp = file.split('/')[-1]
    tmpFile = tmp.replace('.sql.' + ext, '.sql').replace('.' + ext, '.sql').replace('tar.', '')

    import_sql = ""
    extract_msg = ""
    start_time = time.time()

    def _rejectLog(reason):
        """导入包被拒时的结构化日志（不解压、不落地任何文件）。"""
        return f"==================================================\n" \
               f"【MariaDB 外部数据库导入日志】\n" \
               f"目标数据库: {name}\n" \
               f"导入源文件: {file} ({file_size_str})\n" \
               f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}\n" \
               f"解压结果: {reason}\n" \
               f"错误提示: 压缩包成员校验未通过，已拒绝解压，未写入任何文件！\n" \
               f"=================================================="

    if file.find("sql.gz") > -1 or file.endswith('.gz'):
        try:
            import gzip
            target_sql = os.path.join(import_dir, tmpFile)
            with gzip.open(file_path, 'rb') as f_in:
                with open(target_sql, 'wb') as f_out:
                    import shutil
                    shutil.copyfileobj(f_in, f_out)
            import_sql = target_sql
            extract_msg = "解压 gzip 完成 -> " + tmpFile
        except Exception as e:
            extract_msg = "解压 gzip 失败: " + str(e)

    elif file.find(".zip") > -1:
        # 解压前先过成员名校验（safeArchiveCheck），不过就一个文件都不落地
        ok, import_sql, extract_msg = _safeExtractImportArchive(
            file_path, import_dir, 'zip', tmpFile)
        if not ok:
            return yf.returnJson(False, extract_msg, {
                'log': _rejectLog(extract_msg), 'exit_code': 1, 'has_error': True})

    elif file.find("tar.gz") > -1 or file.endswith('.tgz'):
        # 解压前先过成员名校验（safeArchiveCheck），不过就一个文件都不落地
        ok, import_sql, extract_msg = _safeExtractImportArchive(
            file_path, import_dir, 'tar', tmpFile)
        if not ok:
            return yf.returnJson(False, extract_msg, {
                'log': _rejectLog(extract_msg), 'exit_code': 1, 'has_error': True})

    elif file.lower().endswith('.sql'):
        import_sql = file_path

    if not import_sql or not os.path.exists(import_sql):
        err_log = f"==================================================\n" \
                  f"【MariaDB 外部数据库导入日志】\n" \
                  f"目标数据库: {name}\n" \
                  f"导入源文件: {file} ({file_size_str})\n" \
                  f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}\n" \
                  f"解压结果: {extract_msg}\n" \
                  f"错误提示: 未找到有效的 SQL 文件，导入终止！\n" \
                  f"=================================================="
        return yf.returnJson(False, '未找到SQL文件', {'log': err_log, 'exit_code': 1, 'has_error': True})

    sql_file_size = os.path.getsize(import_sql)
    if sql_file_size == 0:
        err_log = f"==================================================\n" \
                  f"【MariaDB 外部数据库导入日志】\n" \
                  f"目标数据库: {name}\n" \
                  f"导入源文件: {file} ({file_size_str})\n" \
                  f"SQL 文件大小: 0 字节 (空文件)\n" \
                  f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}\n" \
                  f"错误提示: 待导入的 SQL 文件内容为空 (0 字节)，无需导入！\n" \
                  f"=================================================="
        if ext != 'sql' and os.path.exists(import_sql):
            try:
                os.remove(import_sql)
            except Exception as _e:
                _log.debug('[mariadb] importDbExternal 异常已忽略: %s', _e)
        return yf.returnJson(False, 'SQL文件内容为空', {'log': err_log, 'exit_code': 1, 'has_error': True})

    pwd = getRootPwd()
    sock = getSocketFile()
    my_cnf = getConf()

    mysql_bin = getServerDir() + '/bin/mariadb'
    if not os.path.exists(mysql_bin):
        mysql_bin = getServerDir() + '/bin/mysql'
    if not os.path.exists(mysql_bin):
        import shutil
        which_bin = shutil.which('mariadb') or shutil.which('mysql')
        if which_bin:
            mysql_bin = which_bin

    cmd = [mysql_bin]
    if os.path.exists(my_cnf):
        cmd.append('--defaults-file=' + my_cnf)
    cmd.append('--default-character-set=utf8mb4')
    if sock and os.path.exists(sock):
        cmd.extend(['-S', sock])
    cmd.extend(['-uroot', '-p' + str(pwd), '-f', name])

    stdout_text = ""
    stderr_text = ""
    returncode = 0

    import subprocess
    try:
        with open(import_sql, 'rb') as f_in:
            p = subprocess.Popen(cmd, stdin=f_in, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout_bytes, stderr_bytes = p.communicate()
            returncode = p.returncode

        try:
            stdout_text = stdout_bytes.decode('utf-8')
        except UnicodeDecodeError:
            stdout_text = stdout_bytes.decode('gbk', errors='replace')

        try:
            stderr_text = stderr_bytes.decode('utf-8')
        except UnicodeDecodeError:
            stderr_text = stderr_bytes.decode('gbk', errors='replace')
    except Exception as e:
        returncode = 1
        stderr_text = "执行命令发生异常: " + str(e)

    duration = round(time.time() - start_time, 2)

    if ext != 'sql' and os.path.exists(import_sql):
        try:
            os.remove(import_sql)
        except Exception as _e:
            _log.debug('[mariadb] importDbExternal 异常已忽略: %s', _e)

    # 分析执行状态与错误
    stderr_clean = stderr_text.replace('[Warning] Using a password on the command line interface can be insecure.', '').strip()
    is_success = (returncode == 0)
    if returncode != 0:
        is_success = False
    elif 'error' in stderr_clean.lower() and not ('unknown collation' in stderr_clean.lower() and is_success):
        is_success = False

    log_lines = []
    log_lines.append("==================================================")
    log_lines.append("【MariaDB 外部数据库导入日志】")
    log_lines.append(f"目标数据库: {name}")
    log_lines.append(f"导入源文件: {file} ({file_size_str})")
    if extract_msg:
        log_lines.append(f"解压记录: {extract_msg}")
    log_lines.append(f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")
    log_lines.append(f"执行耗时: {duration} 秒")
    log_lines.append(f"进程退出码: {returncode}")
    log_lines.append("--------------------------------------------------")
    if stdout_text.strip():
        log_lines.append("[标准输出 (stdout)]:")
        log_lines.append(stdout_text.strip())
    else:
        log_lines.append("[标准输出 (stdout)]: (无输出内容)")
    log_lines.append("")
    if stderr_text.strip():
        log_lines.append("[控制台提示 / 错误 (stderr)]:")
        log_lines.append(stderr_text.strip())
    else:
        log_lines.append("[控制台提示 / 错误 (stderr)]: (无错误或警告信息)")
    log_lines.append("--------------------------------------------------")
    if is_success:
        log_lines.append("执行结论: 数据库导入执行完毕！")
        if not stdout_text.strip() and not stderr_clean:
            log_lines.append("提示: MariaDB 未返回任何异常信息，数据已成功写入数据库。")
    else:
        log_lines.append("执行结论: 数据库导入失败或存在异常！")
        log_lines.append("排查建议: 请检查上方控制台输出，核对 SQL 文件内容格式、表结构权限或字符集。若 SQL 内包含 USE/CREATE DATABASE 语句，可能导入至了其他数据库中。")
    log_lines.append("==================================================")
    full_log = "\n".join(log_lines)

    # 持久化最近一次导入日志
    try:
        log_dir = os.path.join(import_dir, '.logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        yf.writeFile(os.path.join(log_dir, file + '.log'), full_log)
    except Exception as _e:
        _log.debug('[mariadb] importDbExternal 异常已忽略: %s', _e)

    msg = '导入成功!' if is_success else '导入失败或存在异常!'
    return yf.returnJson(is_success, msg, {'log': full_log, 'exit_code': returncode, 'has_error': not is_success})

def importDbExternalProgress():
    args = getArgs()
    data = checkArgs(args, ['file', 'name'])
    if not data[0]:
        return data[1]

    file = args['file']
    name = args['name']

    import_dir = yf.getBackupDir() + '/import/'
    log_dir = os.path.join(import_dir, '.logs')
    log_file = os.path.join(log_dir, file + '.log')

    if os.path.exists(log_file):
        content = yf.readFile(log_file)
        if content and content.strip():
            return yf.returnJson(True, 'ok', {'log': content, 'has_log': True})

    # 无记录时的友好提示
    file_path = os.path.join(import_dir, file)
    file_size_str = yf.toSize(os.path.getsize(file_path)) if os.path.exists(file_path) else '未知大小'
    empty_log = f"==================================================\n" \
                f"【MariaDB 外部数据库导入日志】\n" \
                f"目标数据库: {name}\n" \
                f"导入源文件: {file} ({file_size_str})\n" \
                f"查询时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n" \
                f"--------------------------------------------------\n" \
                f"[状态提示]:\n" \
                f"该文件暂无执行导入的历史日志记录。\n" \
                f"请点击操作列的【导入】按钮执行导入，执行后将在此实时展示完整日志。\n" \
                f"=================================================="
    return yf.returnJson(True, 'ok', {'log': empty_log, 'has_log': False})

def importDbExternalProgressBar():
    args = getArgs()
    data = checkArgs(args, ['file', 'name'])
    if not data[0]:
        return data[1]

    file = args['file']
    name = args['name']

    if not re.match(r"^[\w\.-]+$", name):
        return yf.returnJson(False, '数据库名称不合法!')
    if '..' in file or not re.match(r"^[\w\.\s-]+\.?(gz|zip)?$", file):
        return yf.returnJson(False, '文件名不合法!')

    import_dir = yf.getBackupDir() + '/import/'

    file_path = import_dir + file
    if not os.path.exists(file_path):
        return yf.returnJson(False, '文件突然消失?')

    exts = ['sql', 'gz', 'zip']
    ext = yf.getFileSuffix(file)
    if ext not in exts:
        return yf.returnJson(False, '导入数据库格式不对!')

    tmpFile = file.split('/')[-1]
    tmpFile = tmpFile.replace('.sql.' + ext, '.sql')
    tmpFile = tmpFile.replace('.' + ext, '.sql')
    tmpFile = tmpFile.replace('tar.', '')

    import_sql = ""
    import subprocess

    if file.find("sql.gz") > -1:
        try:
            with open(import_dir + tmpFile, 'wb') as out_f:
                p = subprocess.Popen(['gzip', '-dc', file_path], stdout=out_f, stderr=subprocess.PIPE)
                p.communicate()
            import_sql = import_dir + tmpFile
        except Exception as e:
            return yf.returnJson(False, '解压 gzip 发生异常: ' + str(e))

    elif file.find(".zip") > -1:
        try:
            p = subprocess.Popen(['unzip', '-o', file_path, '-d', import_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            p.communicate()
            import_sql = import_dir + tmpFile
        except Exception as e:
            return yf.returnJson(False, '解压 zip 发生异常: ' + str(e))

    elif file.find("tar.gz") > -1:
        try:
            p = subprocess.Popen(['tar', '-zxvf', file_path, '-C', import_dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            p.communicate()
            import_sql = import_dir + tmpFile
        except Exception as e:
            return yf.returnJson(False, '解压 tar.gz 发生异常: ' + str(e))

    elif file.find(".sql") > -1 and file.find(".sql.gz") == -1:
        import_sql = import_dir + file

    if import_sql == "" or not os.path.exists(import_sql):
        return yf.returnJson(False, '未找到SQL文件')

    pwd = getRootPwd()
    sock = getSocketFile()

    my_cnf = getConf()
    mysql_bin = getServerDir() + '/bin/mariadb'
    if not os.path.exists(mysql_bin):
        mysql_bin = getServerDir() + '/bin/mysql'

    pv_cmd = ['pv', '-t', '-p', import_sql]
    mysql_cmd = [mysql_bin, '--defaults-file=' + my_cnf, '-uroot', '-p' + str(pwd or ''), '-f', name]

    try:
        p_pv = subprocess.Popen(pv_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p_mysql = subprocess.Popen(mysql_cmd, stdin=p_pv.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p_pv.stdout.close()
        stdout, stderr = p_mysql.communicate()
        p_pv.communicate()
    except Exception as e:
        _log.debug('[mariadb] importDbExternalProgressBar 异常已忽略: %s', e)

    return ""


def deleteDbBackup():
    args = getArgs()
    data = checkArgs(args, ['filename', 'path'])
    if not data[0]:
        return data[1]

    filename = str(args['filename'])
    # 文件名 + 目录双白名单：历史实现直接 os.remove(path + '/' + filename)，
    # 任意 path（含 ../ 与绝对路径）都能删掉备份目录以外的文件。
    if not _DB_BACKUP_FILE_RE.match(filename):
        return yf.returnJson(False, '备份文件名不合法!')

    path = str(args['path']).strip()
    allowed = [os.path.realpath(getBackupDir()), os.path.realpath(yf.getBackupDir() + '/import')]
    if path == '':
        base = getBackupDir()
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


def getDbBackupList():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    r = getDbBackupListFunc(args['name'])
    bkDir = getBackupDir()
    if not os.path.exists(bkDir):
        os.mkdir(bkDir)

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

    bkImportDir = yf.getBackupDir() + '/import'
    if not os.path.exists(bkImportDir):
        os.mkdir(bkImportDir)

    blist = os.listdir(bkImportDir)

    rr = []
    for x in range(0, len(blist)):
        name = blist[x]
        if name.startswith('.'):
            continue
        p = bkImportDir + '/' + name
        if os.path.isdir(p):
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


def getDbList():
    args = getArgs()
    # 分页容错：历史缺陷是分页参数裸 int() → page=abc 直接 ValueError traceback（面板 500）
    page, page_size = _parsePageArgs(args)
    search = ''
    data = {}

    if 'search' in args:
        search = args['search']

    conn = pSqliteDb('databases')
    limit = str((page - 1) * page_size) + ',' + str(page_size)
    condition = ''
    if not search == '':
        condition = "name like '%" + search + "%'"
    field = 'id,pid,name,username,password,accept,rw,ps,addtime'
    clist = conn.where(condition, ()).field(
        field).limit(limit).order('addtime desc, id desc').select()
    # P2-4：口令列落库为密文，回前端前还原成明文（解不开给空串，不丢密文给前端）
    _decUserRows(clist)

    for x in range(0, len(clist)):
        dbname = clist[x]['name']
        blist = getDbBackupListFunc(dbname)
        # print(blist)
        clist[x]['is_backup'] = False
        if len(blist) > 0:
            clist[x]['is_backup'] = True
        if not clist[x].get('rw'):
            clist[x]['rw'] = 'all'

    count = conn.where(condition, ()).count()
    _page = {}
    _page['count'] = count
    _page['p'] = page
    _page['row'] = page_size
    _page['tojs'] = 'dbList'
    data['page'] = yf.getPage(_page)
    data['data'] = clist

    info = {}
    info['root_pwd'] = getRootPwd()
    try:
        info['port'] = getDbPort()
    except Exception:
        info['port'] = '3306'
    data['info'] = info

    return yf.getJson(data)


def syncGetDatabases():
    pdb = pMysqlDb('mysql')
    psdb = pSqliteDb('databases')
    data = pdb.query('show databases')
    isError = isSqlError(data)
    if isError != None:
        return isError
    users = pdb.query(
        "select User,Host from user where User!='root' AND Host!='localhost' AND Host!=''")
    nameArr = ['information_schema', 'performance_schema', 'mysql', 'sys']
    n = 0

    # print(users)
    for value in data:
        vdb_name = value["Database"]
        b = False
        for key in nameArr:
            if vdb_name == key:
                b = True
                break
        if b:
            continue
        if psdb.where("name=?", (vdb_name,)).count() > 0:
            continue
        host = '127.0.0.1'
        for user in users:
            if vdb_name == user["User"]:
                host = user["Host"]
                break

        ps = vdb_name
        if vdb_name == 'test':
            ps = yf.getMsg('DATABASE_TEST')
        addTime = time.strftime('%Y-%m-%d %X', time.localtime())
        if psdb.add('name,username,password,accept,ps,addtime', (vdb_name, vdb_name, '', host, ps, addTime)):
            n += 1

    msg = yf.getInfo('本次共从服务器获取了{1}个数据库!', (str(n),))
    return yf.returnJson(True, msg)


def toDbBase(find):
    pdb = pMysqlDb()
    psdb = pSqliteDb('databases')
    # P2-4：落库口令已是密文，先还原成明文再判长度/建用户（历史明文原样通过）
    password = _decUserPwd(find.get('password')) or ''
    if len(password) < 3:
        find['username'] = find['name']
        password = yf.md5(str(time.time()) + find['name'])[0:10]
        find['password'] = password
        psdb.where("id=?", (find['id'],)).save(
            'password,username', (_encUserPwd(password), find['username']))

    result = pdb.execute("create database `" + find['name'] + "`")
    if "using password:" in str(result):
        return -1
    if "Connection refused" in str(result):
        return -1

    __createUser(find['name'], find['username'], password, find['accept'])
    return 1


def syncToDatabases():
    args = getArgs()
    data = checkArgs(args, ['type', 'ids'])
    if not data[0]:
        return data[1]

    pdb = pMysqlDb()
    result = pdb.execute("show databases")
    isError = isSqlError(result)
    if isError:
        return isError

    # type 容错：历史缺陷是 type 裸 int() → type=abc 直接 ValueError traceback（面板 500）。
    # 非法/缺失一律回规范 JSON 错误，合法取值（0=全部数据库 / 其它=按 ids 同步）语义不变。
    try:
        stype = int(str(args['type']).strip())
    except (TypeError, ValueError):
        return yf.returnJson(False, '参数 type 不合法，必须是整数!')
    psdb = pSqliteDb('databases')
    n = 0

    if stype == 0:
        data = psdb.field('id,name,username,password,accept').select()
        for value in data:
            result = toDbBase(value)
            if result == 1:
                n += 1
    else:
        data = json.loads(args['ids'])
        for value in data:
            find = psdb.where("id=?", (value,)).field(
                'id,name,username,password,accept').find()
            # print find
            result = toDbBase(find)
            if result == 1:
                n += 1
    msg = yf.getInfo('本次共同步了{1}个数据库!', (str(n),))
    return yf.returnJson(True, msg)


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
    try:
        pdb = pMysqlDb('mysql')
        result = pdb.query("show databases")
        isError = isSqlError(result)
        if isError != None:
            if force == 1:
                _saveRootPwd(password)
                return yf.returnJson(True, '【强制修改】数据库root密码修改成功(不意为成功连接数据)!')
            return isError

        # 用「当前能连上的旧口令」作凭证，一次覆盖 localhost / 127.0.0.1 / ::1，
        # 并**验证通过后才保存**（只改 localhost 会让走 TCP 的调用继续用旧口令）。
        current_pwd = getRootPwd()
        if not _applyRootPwd(password, current_pwd=current_pwd, scene='修改 root 口令'):
            return yf.returnJson(False, '修改错误: 新口令写入失败或无法用新口令连接数据库！')

        msg = ''
        if force == 1:
            msg = ',无须强制!'

        return yf.returnJson(True, '数据库root密码修改成功!' + msg)
    except Exception as ex:
        return yf.returnJson(False, '修改错误:' + str(ex))


def setUserPwd(version=''):
    args = getArgs()
    data = checkArgs(args, ['password', 'name', 'id'])
    if not data[0]:
        return data[1]

    newpassword = args['password']
    username = str(args['name']).strip()
    uid = str(args['id']).strip()
    name = username

    # username/host 进 SQL 账号字面量；仍过白名单（纵深防御），口令改走 ORM 参数化。
    if not _DB_USER_IDENT_RE.match(username):
        return yf.returnJson(False, yf.getInfo('修改数据库[{1}]密码失败[{2}]!', (name, '用户名不合法',)))
    if not re.match(r"^[0-9]+$", uid):
        return yf.returnJson(False, yf.getInfo('修改数据库[{1}]密码失败[{2}]!', (name, '参数不合法',)))

    try:
        pdb = pMysqlDb()
        psdb = pSqliteDb('databases')
        data = psdb.field('id,name,accept').where('id=?', (uid,)).find()
        # 历史缺陷：id 不存在时 data 为 None → data['accept'] KeyError，
        # except 分支再引用未赋值的 name → NameError traceback 直达前端。
        if not data:
            return yf.returnJson(False, yf.getInfo('修改数据库[{1}]密码失败[{2}]!', (name, '记录不存在',)))
        if data.get('name'):
            name = data['name']

        r = pdb.execute("SET PASSWORD FOR %s@%s = %s", (username, 'localhost', newpassword))

        accept = data.get('accept') or ''
        alist = accept.split(',')
        for x in alist:
            x = x.strip()
            if x == '':
                continue
            if not _DB_USER_IDENT_RE.match(x):
                continue
            r = pdb.execute("SET PASSWORD FOR %s@%s = %s", (username, x, newpassword))

        # P2-4：库用户新口令加密落库（明文只在本次调用内存在）
        psdb.where("id=?", (uid,)).setField('password', _encUserPwd(newpassword))

        orm = pMysqlDb()
        orm.execute("flush privileges")
        return yf.returnJson(True, yf.getInfo('修改数据库[{1}]密码成功!', (data['name'],)))
    except Exception as ex:
        return yf.returnJson(False, yf.getInfo('修改数据库[{1}]密码失败[{2}]!', (data['name'], str(ex),)))


def setDbPs():
    args = getArgs()
    data = checkArgs(args, ['id', 'name', 'ps'])
    if not data[0]:
        return data[1]

    ps = args['ps']
    sid = args['id']
    name = args['name']
    try:
        psdb = pSqliteDb('databases')
        # 不存在的 id 必须如实报错（历史缺陷：回「成功」且 setField 实际未命中）
        if not psdb.where("id=?", (sid,)).count():
            return yf.returnJson(False, yf.getInfo('修改数据库[{1}]备注失败!', (name,)))
        psdb.where("id=?", (sid,)).setField('ps', ps)
        return yf.returnJson(True, yf.getInfo('修改数据库[{1}]备注成功!', (name,)))
    except Exception as e:
        # 历史缺陷：失败分支回 True（假成功）
        return yf.returnJson(False, yf.getInfo('修改数据库[{1}]备注失败!', (name,)))


def addDb():
    args = getArgs()
    data = checkArgs(args,
                     ['password', 'name', 'codeing', 'db_user', 'dataAccess', 'ps'])
    if not data[0]:
        return data[1]

    if not 'address' in args:
        address = ''
    else:
        address = args['address'].strip()

    dbname = args['name'].strip()
    dbuser = args['db_user'].strip()
    codeing = args['codeing'].strip()
    password = args['password'].strip()
    dataAccess = args['dataAccess'].strip()
    ps = args['ps'].strip()

    reg = r"^[\w\.-]+$"
    if not re.match(reg, args['name']):
        return yf.returnJson(False, '数据库名称不能带有特殊符号!')
    checks = ['root', 'mysql', 'test', 'sys', 'panel_logs']
    # dbuser/address 会被拼进 `drop user 'u'@'h'`（标识符无法参数化）→ 白名单化
    if dbuser in checks or len(dbuser) < 1 or not _DB_USER_IDENT_RE.match(dbuser):
        return yf.returnJson(False, '数据库用户名不合法!')
    if dbname in checks or len(dbname) < 1:
        return yf.returnJson(False, '数据库名称不合法!')
    for a in address.split(','):
        if a and not _DB_USER_IDENT_RE.match(a):
            return yf.returnJson(False, '访问地址不合法!')

    if len(password) < 1:
        password = yf.md5(time.time())[0:8]

    wheres = {
        'utf8':   'utf8_general_ci',
        'utf8mb4': 'utf8mb4_general_ci',
        'gbk':    'gbk_chinese_ci',
        'big5':   'big5_chinese_ci'
    }
    # codeing 会被拼进 CREATE DATABASE；历史缺校验，非法值直接 KeyError traceback
    if codeing not in wheres:
        return yf.returnJson(False, '数据库编码不合法!')
    codeStr = wheres[codeing]

    pdb = pMysqlDb()
    psdb = pSqliteDb('databases')

    if psdb.where("name=? or username=?", (dbname, dbuser)).count():
        return yf.returnJson(False, '数据库已存在!')

    result = pdb.execute("create database `" + dbname +
                         "` DEFAULT CHARACTER SET " + codeing + " COLLATE " + codeStr)
    # print result
    isError = isSqlError(result)
    if isError != None:
        return isError

    pdb.execute("drop user '" + dbuser + "'@'localhost'")
    for a in address.split(','):
        pdb.execute("drop user '" + dbuser + "'@'" + a + "'")

    __createUser(dbname, dbuser, password, address)

    addTime = time.strftime('%Y-%m-%d %X', time.localtime())
    # P2-4：新建库用户的初始口令加密落库（__createUser 仍用明文）
    stored_user_pwd = _encUserPwd(password)
    psdb.add('pid,name,username,password,accept,rw,ps,addtime',
             (0, dbname, dbuser, stored_user_pwd, address, 'all', ps, addTime))
    return yf.returnJson(True, '添加成功!')


# 面板自建的用户名 / mysql.user.Host 允许的字符集：DROP USER 里的用户名是标识符，
# 无法用参数占位，只能白名单化后再拼字面量，避免 `'; DROP ...` 这类注入。
_DB_USER_IDENT_RE = re.compile(r'^[A-Za-z0-9_.:%-]+$')

# 备份文件名白名单：文件名会拼进 os.path.join 后被删除，禁止路径分隔符与 `..`。
_DB_BACKUP_FILE_RE = re.compile(r'^[A-Za-z0-9_.-]+$')


def _dropUserTargets(username, hosts):
    """拼 `'user'@'host'` 字面量列表；任一项含白名单外字符则整体放弃（返回空表）。

    整体放弃而不是部分跳过：宁可留下待人工清理的授权，也不要拼出半截语句。
    """
    user = str(username or '')
    if not _DB_USER_IDENT_RE.match(user):
        return []
    targets = []
    for host in hosts:
        h = str(host or '')
        if not _DB_USER_IDENT_RE.match(h):
            return []
        targets.append("'" + user + "'@'" + h + "'")
    return targets


def delDb():
    args = getArgs()
    data = checkArgs(args, ['id', 'name'])
    if not data[0]:
        return data[1]
    try:
        sid = args['id']
        name = args['name']
        # 库名白名单：name 会被拼进 DROP DATABASE 的反引号标识符（无法参数化）
        if not re.match(r"^[\w\.-]+$", name):
            return yf.returnJson(False, '数据库名称不合法!')

        psdb = pSqliteDb('databases')
        find = psdb.where("id=?", (sid,)).field(
            'id,pid,name,username,password,accept,ps,addtime').find()
        if not find:
            return yf.returnJson(False, '删除失败! 数据库在面板记录中不存在。')

        username = find['username']

        # 数据库连接参数
        db_host = 'localhost'
        db_port = int(getDbPort())
        db_pass = getRootPwd()
        db_socket = getSocketFile()

        import pymysql
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        # 与 mysql 插件同构：连接超时 + 1008 容错 + 返回值不丢弃 + 单条 DROP USER。
        # 历史实现走 ORM 且把 pdb.execute() 的返回值全部丢弃：
        # 「库已不存在」、「用户不存在」这类失败完全不可见，前端一律看到「删除成功」。
        def doDeleteDb(read_timeout_val=30):
            conn = None
            try:
                conn = pymysql.connect(
                    host=db_host,
                    user='root',
                    password=db_pass,
                    port=db_port,
                    unix_socket=db_socket,
                    connect_timeout=5,
                    read_timeout=read_timeout_val,
                    cursorclass=pymysql.cursors.DictCursor
                )
                with conn.cursor() as cursor:
                    # 1. 删除数据库（库已不存在时忽略该错误）
                    try:
                        cursor.execute("DROP DATABASE `" + name + "`")
                    except Exception as e_db:
                        # 1008 == ER_DB_DROP_EXISTS
                        if getattr(e_db, 'args', None) and e_db.args[0] == 1008:
                            pass
                        else:
                            raise e_db

                    # 2/3/4. 一次取出该用户在 mysql.user 里的**全部** Host，再用单条
                    #        DROP USER 批量删除（原来是本地 1 条 + 每个 Host 1 条）。
                    #        不用 IF EXISTS（MySQL 5.7.8+ 才有），兼容 5.5/5.6。
                    cursor.execute("SELECT Host FROM mysql.user WHERE User=%s", (username,))
                    targets = _dropUserTargets(username, [r['Host'] for r in cursor.fetchall()])
                    if targets:
                        cursor.execute("DROP USER " + ','.join(targets))
                    else:
                        _log.warning('[mariadb] delDb 跳过删除用户（用户名/Host 含非白名单字符）: %s', username)

                    # 5. 刷新权限
                    cursor.execute("FLUSH PRIVILEGES")

                conn.commit()
                return True, None
            except Exception as e:
                return False, e
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception as _e:
                        _log.debug('[mariadb] delDb 异常已忽略: %s', _e)

        ok, err = doDeleteDb(read_timeout_val=30)
        if not ok:
            # 超过 30 秒超时或遇到锁等待阻碍，自动重启数据库后重试一次
            try:
                db_version = version
            except NameError:
                db_version = "10.6"
                version_pl = getServerDir() + "/version.pl"
                if os.path.exists(version_pl):
                    db_version = yf.readFile(version_pl).strip()

            yf.writeFileLog('删除数据库卡住或发生异常，触发超时30秒保护逻辑，正在重启 mariadb...')
            rst = restart(db_version)
            if rst != 'ok':
                # 重启未就绪：兜底再拉起一次，避免把「数据库服务已停」留给现场
                _log.warning('[mariadb] delDb 重启未就绪，兜底拉起: %s', rst)
                yf.writeFileLog('mariadb 重启未就绪，兜底拉起: ' + str(rst))
                start(db_version)
            time.sleep(3)

            ok2, err2 = doDeleteDb(read_timeout_val=60)
            if not ok2:
                # 兜底：无论删除成败，都必须把数据库服务拉回可用状态
                svc = status(db_version)
                if svc != 'start':
                    _log.warning('[mariadb] delDb 重试失败且服务未运行(%s)，兜底拉起', svc)
                    start(db_version)
                    svc = status(db_version)
                raise Exception("重启后尝试删除数据库依然失败: " + str(err2)
                                + "（mariadb 当前状态: " + str(svc) + "）")

        # 删除SQLITE
        psdb.where("id=?", (sid,)).delete()
        return yf.returnJson(True, '删除成功!')
    except Exception as ex:
        return yf.returnJson(False, '删除失败!' + str(ex))


def getDbAccess():
    args = getArgs()
    data = checkArgs(args, ['username'])
    if not data[0]:
        return data[1]
    username = str(args['username'])
    # username 直接拼进 SQL 字面量（历史缺陷：`x' OR '1'='1` 能列出全部 Host）
    if not _DB_USER_IDENT_RE.match(username):
        return yf.returnJson(False, '数据库用户名不合法!')
    pdb = pMysqlDb('mysql')

    users = pdb.query("select Host from user where User=%s AND Host!='localhost'", (username,))

    isError = isSqlError(users)
    if isError != None:
        return isError

    if not isinstance(users, (list, tuple)):
        return yf.returnJson(False, '获取数据库用户失败!')

    if len(users) < 1:
        return yf.returnJson(True, "127.0.0.1")
    accs = []
    for c in users:
        accs.append(c["Host"])
    userStr = ','.join(accs)
    return yf.returnJson(True, userStr)


def setDbAccess():
    args = getArgs()
    data = checkArgs(args, ['username', 'access'])
    if not data[0]:
        return data[1]
    name = args['username'].strip()
    access = args['access'].strip()
    pdb = pMysqlDb('mysql')
    psdb = pSqliteDb('databases')

    try:
        is_root = (name == 'root')
        if is_root:
            password = getRootPwd()
            if not password:
                return yf.returnJson(False, '获取ROOT数据库密码失败!')
            dbname = '*'
            rw = 'all'
        else:
            # 兼容按 username 或 name 查询
            db_info = psdb.where('username=?', (name,)).field('name,username,password,accept,rw').find()
            if not db_info:
                db_info = psdb.where('name=?', (name,)).field('name,username,password,accept,rw').find()
            if not db_info:
                # 后端消息契约：面向用户的提示统一为「可翻译前缀: 动态参数」，
                # 分隔符必须是 : / ：，前端 YfI18n.translateAny() 才能按冒号前缀命中语言包。
                return yf.returnJson(False, '数据库用户不存在: ' + name)

            dbname = db_info.get('name') or name
            name = db_info.get('username') or name
            # P2-4：databases.password 落库为密文，先还原成明文再用
            password = _decUserPwd(db_info.get('password')) or ''
            req_rw = args.get('rw', '').strip()
            if req_rw in ['all', 'rw', 'r']:
                rw = req_rw
            else:
                rw = db_info.get('rw') or 'all'

            if not password:
                return yf.returnJson(False, '数据库用户密码为空，请先修改或重置密码: ' + name)

        # 查询已有非 localhost 的 Host
        # 用户名来自用户入参（或 sqlite databases 表）：走 ORM 参数化，禁止拼进 SQL 文本
        users = pdb.query("select Host from user where User=%s AND Host!='localhost'",
                          (name,))
        err = checkSqlExec(users)
        if err is not None:
            return err

        # `name` 会被拼进 drop user / CREATE USER 的标识符（无法参数化）→ 拼前白名单
        if not _DB_USER_IDENT_RE.match(name):
            return yf.returnJson(False, '数据库用户名不合法!')

        if isinstance(users, list):
            for us in users:
                h = str(us.get("Host") if isinstance(us, dict) else us[0])
                if not _DB_USER_IDENT_RE.match(h):
                    continue
                pdb.execute("drop user '" + name + "'@'" + h + "'")

        # 解析目标 host 列表
        target_hosts = []
        for a in access.split(','):
            a = a.strip()
            if a and a not in target_hosts:
                target_hosts.append(a)

        if not target_hosts:
            target_hosts = ['127.0.0.1']

        db_target = '*.*' if is_root else ('`' + dbname + '`.*')

        # 为每个 host 创建用户并授权（口令/账号走 ORM 参数化，不手写 `\'`）
        for a in target_hosts:
            r_create = pdb.execute(
                "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s", (name, a, password))
            if checkSqlExec(r_create) is not None:
                r_alt = pdb.execute(
                    "ALTER USER %s@%s IDENTIFIED BY %s", (name, a, password))
                if checkSqlExec(r_alt) is not None:
                    # 兼容老版本
                    pdb.execute(
                        "GRANT USAGE ON *.* TO %s@%s IDENTIFIED BY %s", (name, a, password))

            if is_root:
                grant_sql = "GRANT ALL PRIVILEGES ON *.* TO `%s`@`%s` WITH GRANT OPTION" % (name, a)
            else:
                pdb.execute("REVOKE ALL PRIVILEGES ON " + db_target + " FROM `" + name + "`@`" + a + "`")
                if rw == 'rw':
                    grant_sql = "GRANT SELECT, INSERT, UPDATE, DELETE ON %s TO `%s`@`%s`" % (db_target, name, a)
                elif rw == 'r':
                    grant_sql = "GRANT SELECT ON %s TO `%s`@`%s`" % (db_target, name, a)
                else:
                    grant_sql = "GRANT ALL PRIVILEGES ON %s TO `%s`@`%s`" % (db_target, name, a)

            r_grant = pdb.execute(grant_sql)
            err_grant = checkSqlExec(r_grant)
            if err_grant is not None:
                return err_grant

        # 对非 root 用户，同时确保 localhost 正常授权
        if not is_root:
            r_local = pdb.execute(
                "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s", (name, 'localhost', password))
            if checkSqlExec(r_local) is not None:
                pdb.execute(
                    "ALTER USER %s@%s IDENTIFIED BY %s", (name, 'localhost', password))
            pdb.execute("REVOKE ALL PRIVILEGES ON " + db_target + " FROM `" + name + "`@`localhost`")
            if rw == 'rw':
                pdb.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON %s TO `%s`@`localhost`" % (db_target, name))
            elif rw == 'r':
                pdb.execute("GRANT SELECT ON %s TO `%s`@`localhost`" % (db_target, name))
            else:
                pdb.execute("GRANT ALL PRIVILEGES ON %s TO `%s`@`localhost`" % (db_target, name))

        pdb.execute("flush privileges")

        # 更新 sqlite，同步更新 accept 与 rw 字段
        if not is_root:
            psdb.where('username=?', (name,)).setField('accept', access)
            psdb.where('username=?', (name,)).setField('rw', rw)

        return yf.returnJson(True, '设置成功!')
    except Exception as ex:
        return yf.returnJson(False, '设置数据库权限异常: ' + str(ex))

def openSkipGrantTables():
    mycnf = getConf()
    content = yf.readFile(mycnf)
    content = content.replace('#skip-grant-tables','skip-grant-tables')
    yf.writeFile(mycnf, content)
    return True

def closeSkipGrantTables():
    mycnf = getConf()
    content = yf.readFile(mycnf)
    content = content.replace('skip-grant-tables','#skip-grant-tables')
    yf.writeFile(mycnf, content)
    return True


def resetDbRootPwd(version):
    """在 `--skip-grant-tables` 模式下重置 root 口令（【修复】按钮走这里）。

    先写入口令、**验证通过后才保存**，并覆盖 localhost / 127.0.0.1 / ::1
    （只改 localhost 时走 TCP 的那条路仍然用空口令，报 1045）。
    skip-grant 模式下无凭证连接，因此 `current_pwd=None`。
    """
    pwd = yf.getRandomString(16)
    return _applyRootPwd(pwd, current_pwd=None, scene='修复 root 口令')

def fixDbAccess(version):

    pdb = pMysqlDb()
    mdb_ddir = getDataDir()
    if not os.path.exists(mdb_ddir):
        return yf.returnJson(False, '数据目录不存在,尝试重启重建!')

    # 【修复】只允许动「我们自己的实例」（与 mysql 插件同一口径，2026-10-28）：
    # 机器上若另有一个 MySQL/MariaDB 占着 3306，旧实现会把那个实例停掉、加
    # skip-grant-tables、改它 root 口令——既修不好本插件，又破坏系统里原有的数据库。
    own = instanceOwnership()
    if own['status'] in ('foreign_only', 'mixed'):
        return yf.returnJson(False, '修复失败: 实例异常（端口可能被其他 MySQL/MariaDB 占用）')

    try:
        psdb = pSqliteDb('databases')
        data = pdb.query('show databases')
        isError = isSqlError(data)
        if isError != None:
            # 重置密码
            appCMD(version, 'stop')
            openSkipGrantTables()
            appCMD(version, 'start')
            time.sleep(3)
            reset_ok = resetDbRootPwd(version)

            appCMD(version, 'stop')
            closeSkipGrantTables()
            appCMD(version, 'start')
            if not reset_ok:
                # 不能报「修复成功」：否则用户以为好了，实际连不上（口令已打码写进日志）
                return yf.returnJson(False, '修复失败: 无法写入并验证 root 口令，请查看面板日志！')
            # 修好之后跑一次自检：回「修复成功」但实际仍连不上，比直接报错更坏
            check = _resultDict(selfCheck(version))
            if not check.get('status'):
                return yf.getJson(check)
            return yf.returnJson(True, '修复成功!')
        return yf.returnJson(True, '正常无需修复!')
    except Exception as e:
        return yf.returnJson(False, '修复失败请重试!')


def setDbRw(version=''):
    args = getArgs()
    data = checkArgs(args, ['username', 'id', 'rw'])
    if not data[0]:
        return data[1]

    username = str(args['username'])
    uid = str(args['id'])
    rw = args['rw']
    if rw not in ('rw', 'r', 'all'):
        return yf.returnJson(False, '权限类型不合法!')
    if not _DB_USER_IDENT_RE.match(username):
        return yf.returnJson(False, '数据库用户名不合法!')

    pdb = pMysqlDb('mysql')
    psdb = pSqliteDb('databases')
    dbname = psdb.where("id=?", (uid,)).getField('name')
    if not dbname or not re.match(r"^[\w\.-]+$", str(dbname)):
        return yf.returnJson(False, '数据库不存在!')
    dbname = str(dbname)

    users = pdb.query("select Host from user where User=%s", (username,))
    if not isinstance(users, (list, tuple)):
        return yf.returnJson(False, '获取数据库用户失败!')

    failed = False
    # show grants for demo@"127.0.0.1";
    for x in users:
        host = str(x["Host"] if isinstance(x, dict) else x[0])
        if not _DB_USER_IDENT_RE.match(host):
            failed = True
            continue
        # REVOKE ALL PRIVILEGES ON `imail`.* FROM 'imail'@'127.0.0.1';
        pdb.execute("REVOKE ALL PRIVILEGES ON `%s`.* FROM '%s'@'%s'" % (dbname, username, host))

        if rw == 'rw':
            sql = "GRANT SELECT, INSERT, UPDATE, DELETE ON `%s`.* TO '%s'@'%s'" % (dbname, username, host)
        elif rw == 'r':
            sql = "GRANT SELECT ON `%s`.* TO '%s'@'%s'" % (dbname, username, host)
        else:
            sql = "GRANT ALL PRIVILEGES ON `%s`.* TO '%s'@'%s'" % (dbname, username, host)
        res = pdb.execute(sql)
        # 历史缺陷：无论 SQL 成败都回「切换成功!」（假成功）
        if isinstance(res, Exception) or isinstance(res, str):
            failed = True
    pdb.execute("flush privileges")
    r = psdb.where("id=?", (uid,)).setField('rw', rw)
    # print(r)
    if failed:
        return yf.returnJson(False, "切换失败!")
    return yf.returnJson(True, "切换成功!")


def getDbInfo():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    db_name = args['name']
    # 库名是用户入参：标识符位置（show tables from）无法参数化，先过白名单；
    # information_schema 查询的 table_schema 走参数化（下方）。
    db_name = yf.safeIdentifier(db_name)
    if not db_name:
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')
    pdb = pMysqlDb()
    # print 'show tables from `%s`' % db_name
    tables = pdb.query('show tables from `%s`' % db_name)
    if isinstance(tables, Exception):
        return yf.returnJson(False, '获取表列表失败: ' + str(tables))

    ret = {}
    sql = "select sum(DATA_LENGTH)+sum(INDEX_LENGTH) as sum_size from information_schema.tables  where table_schema=%s"
    data_sum = pdb.query(sql, (db_name,))

    data = 0
    if not isinstance(data_sum, Exception) and len(data_sum) > 0 and data_sum[0]['sum_size'] != None:
        data = data_sum[0]['sum_size']

    ret['data_size'] = yf.toSize(data)
    ret['database'] = db_name

    ret3 = []
    
    # optimize: single query for all tables
    table_status_list = pdb.query("show table status from `%s`" % db_name)
    if isinstance(table_status_list, Exception):
        return yf.returnJson(False, '获取表状态失败: ' + str(table_status_list))
        
    for table in table_status_list:
        tmp = {}
        tmp['type'] = table.get("Engine", "Unknown")
        tmp['rows_count'] = table.get("Rows", 0)
        tmp['collation'] = table.get("Collation", "Unknown")

        data_size = 0
        if table.get('Avg_row_length') != None:
            data_size = table['Avg_row_length']

        if table.get('Data_length') != None:
            data_size = table['Data_length']

        tmp['data_byte'] = data_size
        tmp['data_size'] = yf.toSize(data_size)
        tmp['table_name'] = table.get("Name", "Unknown")
        ret3.append(tmp)

    ret['tables'] = (ret3)

    return yf.getJson(ret)


def repairTable():
    args = getArgs()
    data = checkArgs(args, ['db_name', 'tables'])
    if not data[0]:
        return data[1]

    db_name = args['db_name']
    # 库名是用户入参：标识符位置无法参数化，先过白名单
    db_name = yf.safeIdentifier(db_name)
    if not db_name:
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')
    tables = json.loads(args['tables'])
    pdb = pMysqlDb()
    mtable = pdb.query('show tables from `%s`' % db_name)
    err = isSqlError(mtable)
    if err:
        return err

    ret = []
    key = "Tables_in_" + db_name
    for i in mtable:
        for tn in tables:
            if tn == i.get(key):
                ret.append(tn)

    if len(ret) > 0:
        err_list = []
        for i in ret:
            r = pdb.execute('REPAIR TABLE `%s`.`%s`' % (db_name, i))
            sql_err = isSqlError(r)
            if sql_err:
                err_list.append("%s: %s" % (i, r))
        if err_list:
            return yf.returnJson(False, "部分表修复未完成: " + "; ".join(err_list))
        return yf.returnJson(True, "数据表修复操作执行完毕!")
    return yf.returnJson(False, "未找到指定的有效数据表!")


def optTable():
    args = getArgs()
    data = checkArgs(args, ['db_name', 'tables'])
    if not data[0]:
        return data[1]

    db_name = args['db_name']
    # 库名是用户入参：标识符位置无法参数化，先过白名单
    db_name = yf.safeIdentifier(db_name)
    if not db_name:
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')
    tables = json.loads(args['tables'])
    pdb = pMysqlDb()
    mtable = pdb.query('show tables from `%s`' % db_name)
    err = isSqlError(mtable)
    if err:
        return err

    ret = []
    key = "Tables_in_" + db_name
    for i in mtable:
        for tn in tables:
            if tn == i.get(key):
                ret.append(tn)

    if len(ret) > 0:
        err_list = []
        for i in ret:
            r = pdb.execute('OPTIMIZE TABLE `%s`.`%s`' % (db_name, i))
            sql_err = isSqlError(r)
            if sql_err:
                err_list.append("%s: %s" % (i, r))
        if err_list:
            return yf.returnJson(False, "部分表优化失败: " + "; ".join(err_list))
        return yf.returnJson(True, "数据表优化完成，磁盘碎片已回收整理!")
    return yf.returnJson(False, "未找到指定的有效数据表!")


def alterTable():
    args = getArgs()
    data = checkArgs(args, ['db_name', 'tables', 'table_type'])
    if not data[0]:
        return data[1]

    db_name = args['db_name']
    tables = json.loads(args['tables'])
    table_type = args['table_type'].strip()
    if table_type not in ['InnoDB', 'MyISAM']:
        return yf.returnJson(False, "不支持的目标存储引擎类型!")

    # 库名是用户入参：标识符位置无法参数化，先过白名单
    db_name = yf.safeIdentifier(db_name)
    if not db_name:
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')
    pdb = pMysqlDb()
    mtable = pdb.query('show tables from `%s`' % db_name)
    err = isSqlError(mtable)
    if err:
        return err

    ret = []
    key = "Tables_in_" + db_name
    for i in mtable:
        for tn in tables:
            if tn == i.get(key):
                ret.append(tn)

    if len(ret) > 0:
        err_list = []
        for i in ret:
            r = pdb.execute('ALTER TABLE `%s`.`%s` ENGINE=%s' %
                        (db_name, i, table_type))
            sql_err = isSqlError(r)
            if sql_err:
                err_list.append("%s: %s" % (i, r))
        if err_list:
            return yf.returnJson(False, "部分表引擎转换失败: " + "; ".join(err_list))
        # 后端消息契约：可翻译前缀 = 首个冒号（含）之前，动态参数一律走拼接。
        # 原先的 "%s!" %-格式化会在后端就把引擎名拼进消息，前端前缀匹配拿不到键。
        return yf.returnJson(True, "数据表引擎已成功转换为: " + table_type)
    return yf.returnJson(False, "未找到指定的有效数据表!")


def getTotalStatistics():
    st = status()
    data = {}

    isInstall = os.path.exists(getServerDir() + '/version.pl')

    if st == 'start' and isInstall:
        data['status'] = True
        data['count'] = pSqliteDb('databases').count()
        data['ver'] = yf.readFile(getServerDir() + '/version.pl').strip()
        return yf.returnJson(True, 'ok', data)
    else:
        data['status'] = False
        data['count'] = 0
        return yf.returnJson(False, 'fail', data)


def recognizeDbMode():
    conf = getConf()
    con = yf.readFile(conf)
    rep = r"!include %s/(.*)?\.cnf" % (getServerDir() + "/etc/mode",)
    mode = 'none'
    try:
        data = re.findall(rep, con, re.M)
        mode = data[0]
    except Exception as e:
        _log.debug('[mariadb] recognizeDbMode 异常已忽略: %s', e)
    return mode


def getDbrunMode(version=''):
    mode = recognizeDbMode()
    return yf.returnJson(True, "ok", {'mode': mode})


def setDbrunMode(version=''):
    if version == '5.5':
        return yf.returnJson(False, "不支持切换")

    args = getArgs()
    data = checkArgs(args, ['mode', 'reload'])
    if not data[0]:
        return data[1]

    mode = args['mode']
    dbreload = args['reload']

    if not mode in ['classic', 'gtid']:
        return yf.returnJson(False, "mode的值无效:" + mode)

    origin_mode = recognizeDbMode()
    path = getConf()
    con = yf.readFile(path)
    rep = r"!include %s/%s\.cnf" % (getServerDir() + "/etc/mode", origin_mode)
    rep_after = "!include %s/%s.cnf" % (getServerDir() + "/etc/mode", mode)
    con = re.sub(rep, rep_after, con)
    yf.writeFile(path, con)

    if version == '5.6':
        dbreload = 'yes'
    else:
        db = pMysqlDb()
        # The value of @@GLOBAL.GTID_MODE can only be changed one step at a
        # time: OFF <-> OFF_PERMISSIVE <-> ON_PERMISSIVE <-> ON. Also note that
        # this value must be stepped up or down simultaneously on all servers.
        # See the Manual for instructions.
        if mode == 'classic':
            db.query('set global enforce_gtid_consistency=off')
            db.query('set global gtid_mode=on')
            db.query('set global gtid_mode=on_permissive')
            db.query('set global gtid_mode=off_permissive')
            db.query('set global gtid_mode=off')
        elif mode == 'gtid':
            db.query('set global enforce_gtid_consistency=on')
            db.query('set global gtid_mode=off')
            db.query('set global gtid_mode=off_permissive')
            db.query('set global gtid_mode=on_permissive')
            db.query('set global gtid_mode=on')

    if dbreload == "yes":
        restart(version)

    return yf.returnJson(True, "切换成功!")


def findBinlogDoDb():
    conf = getConf()
    con = yf.readFile(conf)
    rep = r"binlog-do-db\s*?=\s*?(.*)"
    dodb = re.findall(rep, con, re.M)
    return dodb


def findBinlogSlaveDoDb():
    conf = getConf()
    con = yf.readFile(conf)
    rep = r"replicate-do-db\s*?=\s*?(.*)"
    dodb = re.findall(rep, con, re.M)
    return dodb


def setDbMasterAccess():
    args = getArgs()
    data = checkArgs(args, ['username', 'access'])
    if not data[0]:
        return data[1]
    username = args['username'].strip()
    access = args['access'].strip()
    pdb = pMysqlDb('mysql')
    psdb = pSqliteDb('master_replication_user')

    try:
        user_info = psdb.where("username=?", (username,)).find()
        if not user_info:
            return yf.returnJson(False, '复制用户不存在: ' + username)
        password = user_info.get('password') or ''
        if not password:
            return yf.returnJson(False, '复制用户密码为空!')

        # 用户名来自用户入参：走 ORM 参数化，禁止拼进 SQL 文本
        users = pdb.query("select Host from user where User=%s AND Host!='localhost'",
                          (username,))
        err = checkSqlExec(users)
        if err is not None:
            return err

        # `username` 会被拼进 drop user / CREATE USER 的标识符（无法参数化）→ 拼前白名单
        if not _DB_USER_IDENT_RE.match(username):
            return yf.returnJson(False, '用户名不合法!')

        if isinstance(users, list):
            for us in users:
                h = str(us.get("Host") if isinstance(us, dict) else us[0])
                if not _DB_USER_IDENT_RE.match(h):
                    continue
                pdb.execute("drop user '" + username + "'@'" + h + "'")

        # host 会被拼进 `user`@`host` 反引号标识符（GRANT 语句无法参数化）→ 白名单
        target_hosts = []
        for a in access.split(','):
            a = a.strip()
            if not a:
                continue
            if not _DB_USER_IDENT_RE.match(a):
                return yf.returnJson(False, '访问地址不合法: ' + a)
            if a not in target_hosts:
                target_hosts.append(a)

        if not target_hosts:
            target_hosts = ['127.0.0.1']

        for a in target_hosts:
            r_create = pdb.execute(
                "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s", (username, a, password))
            if checkSqlExec(r_create) is not None:
                pdb.execute(
                    "ALTER USER %s@%s IDENTIFIED BY %s", (username, a, password))
            r_grant = pdb.execute(
                "grant all privileges on *.* to `%s`@`%s` with grant option" % (username, a))
            err_grant = checkSqlExec(r_grant)
            if err_grant is not None:
                return err_grant

        pdb.execute("flush privileges")
        psdb.where('username=?', (username,)).setField('accept', access)
        return yf.returnJson(True, '设置成功!')
    except Exception as ex:
        return yf.returnJson(False, '设置复制用户权限异常: ' + str(ex))

def resetMaster(version=''):
    pdb = pMysqlDb()
    r = pdb.execute('reset master')
    isError = isSqlError(r)
    if isError != None:
        return isError
    return yf.returnJson(True, '重置成功!')

def getMasterDbList(version=''):
    args = getArgs()
    # 分页容错：历史缺陷是分页参数裸 int() → page=abc 直接 ValueError traceback
    page, page_size = _parsePageArgs(args)
    search = ''
    data = {}

    if 'search' in args:
        search = args['search']

    conn = pSqliteDb('databases')
    limit = str((page - 1) * page_size) + ',' + str(page_size)
    condition = ''
    dodb = findBinlogDoDb()
    data['dodb'] = dodb

    slave_dodb = findBinlogSlaveDoDb()

    if not search == '':
        condition = "name like '%" + search + "%'"
    field = 'id,pid,name,username,password,accept,ps,addtime'
    clist = conn.where(condition, ()).field(
        field).limit(limit).order('addtime desc, id desc').select()
    # P2-4：口令列落库为密文，回前端前还原成明文
    _decUserRows(clist)
    count = conn.where(condition, ()).count()

    for x in range(0, len(clist)):
        if clist[x]['name'] in dodb:
            clist[x]['master'] = 1
        else:
            clist[x]['master'] = 0

        if clist[x]['name'] in slave_dodb:
            clist[x]['slave'] = 1
        else:
            clist[x]['slave'] = 0

    _page = {}
    _page['count'] = count
    _page['p'] = page
    _page['row'] = page_size
    _page['tojs'] = 'dbList'
    data['page'] = yf.getPage(_page)
    data['data'] = clist

    return yf.getJson(data)


def setDbMaster(version):
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    conf = getConf()
    con = yf.readFile(conf)
    rep = r"(binlog-do-db\s*?=\s*?(.*))"
    dodb = re.findall(rep, con, re.M)

    isHas = False
    for x in range(0, len(dodb)):

        if dodb[x][1] == args['name']:
            isHas = True

            con = con.replace(dodb[x][0] + "\n", '')
            yf.writeFile(conf, con)

    if not isHas:
        prefix = '#binlog-do-db'
        con = con.replace(prefix, prefix + "\nbinlog-do-db=" + args['name'])
        yf.writeFile(conf, con)

    restart(version)
    time.sleep(4)
    return yf.returnJson(True, '设置成功', [args, dodb])


def setDbSlave(version):
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    conf = getConf()
    con = yf.readFile(conf)
    rep = r"(replicate-do-db\s*?=\s*?(.*))"
    dodb = re.findall(rep, con, re.M)

    isHas = False
    for x in range(0, len(dodb)):
        if dodb[x][1] == args['name']:
            isHas = True

            con = con.replace(dodb[x][0] + "\n", '')
            yf.writeFile(conf, con)

    if not isHas:
        prefix = '#replicate-do-db'
        con = con.replace(prefix, prefix + "\nreplicate-do-db=" + args['name'])
        yf.writeFile(conf, con)

    restart(version)
    time.sleep(4)
    return yf.returnJson(True, '设置成功', [args, dodb])


def getMasterStatus(version=''):
    try:
        if status(version) == 'stop':
            return yf.returnJson(False, 'MySQL未启动,或正在启动中...!', [])

        conf = getConf()
        content = yf.readFile(conf)
        master_status = False
        if content.find('#log-bin') == -1 and content.find('log-bin') > 1:
            dodb = findBinlogDoDb()
            if len(dodb) > 0:
                master_status = True

        data = {}
        data['mode'] = recognizeDbMode()
        data['status'] = master_status

        pdb = pMysqlDb('mysql')
        dlist = pdb.query('show slave status')
        if len(dlist) < 1:
            dlist = pdb.query("show all slaves status")

        for v in dlist:
            if v["Slave_IO_Running"] == 'Yes' or v["Slave_SQL_Running"] == 'Yes':
                data['slave_status'] = True

        return yf.returnJson(master_status, '设置成功', data)
    except Exception as e:
        return yf.returnJson(False, "数据库密码错误,在管理列表-点击【修复】!", 'pwd')


def setMasterStatus(version=''):

    conf = getConf()
    con = yf.readFile(conf)

    if con.find('#log-bin') != -1:
        return yf.returnJson(False, '必须开启二进制日志')

    sign = 'mdserver_ms_open'

    dodb = findBinlogDoDb()
    if not sign in dodb:
        prefix = '#binlog-do-db'
        con = con.replace(prefix, prefix + "\nbinlog-do-db=" + sign)
        yf.writeFile(conf, con)
    else:
        con = con.replace("binlog-do-db=" + sign + "\n", '')
        rep = r"(binlog-do-db\s*?=\s*?(.*))"
        dodb = re.findall(rep, con, re.M)
        for x in range(0, len(dodb)):
            con = con.replace(dodb[x][0] + "\n", '')
        yf.writeFile(conf, con)

    restart(version)
    return yf.returnJson(True, '设置成功')


def getMasterRepSlaveList(version=''):
    args = getArgs()
    # 分页容错：历史缺陷是分页参数裸 int() → page=abc 直接 ValueError traceback
    page, page_size = _parsePageArgs(args)
    search = ''
    data = {}

    if 'search' in args:
        search = args['search']

    conn = pSqliteDb('master_replication_user')
    limit = str((page - 1) * page_size) + ',' + str(page_size)
    condition = ''

    if not search == '':
        condition = "name like '%" + search + "%'"
    field = 'id,username,password,accept,ps,addtime'
    clist = conn.where(condition, ()).field(
        field).limit(limit).order('id desc').select()
    count = conn.where(condition, ()).count()

    _page = {}
    _page['count'] = count
    _page['p'] = page
    _page['row'] = page_size
    _page['tojs'] = 'getMasterRepSlaveList'
    data['page'] = yf.getPage(_page)
    data['data'] = clist

    return yf.getJson(data)


def addMasterRepSlaveUser(version=''):
    args = getArgs()
    data = checkArgs(args, ['username', 'password'])
    if not data[0]:
        return data[1]

    if not 'address' in args:
        address = ''
    else:
        address = args['address'].strip()

    username = args['username'].strip()
    password = args['password'].strip()
    # ps = args['ps'].strip()
    # address = args['address'].strip()
    # dataAccess = args['dataAccess'].strip()

    reg = r"^[\w-]+$"
    if not re.match(reg, username):
        return yf.returnJson(False, '用户名不能带有特殊符号!')
    checks = ['root', 'mysql', 'test', 'sys', 'panel_logs']
    if username in checks or len(username) < 1:
        return yf.returnJson(False, '用户名不合法!')
    if password in checks or len(password) < 1:
        return yf.returnJson(False, '密码不合法!')

    if len(password) < 1:
        password = yf.md5(time.time())[0:8]

    pdb = pMysqlDb()
    psdb = pSqliteDb('master_replication_user')

    if psdb.where("username=?", (username,)).count() > 0:
        return yf.returnJson(False, '用户已存在!')

    # 口令/账号走 ORM 参数化（不手写 `\'`）；`'%%'` 是 host 通配符经 pymysql 插值后的形态
    sql_create = "CREATE USER IF NOT EXISTS %s@'%%' IDENTIFIED BY %s;"
    pdb.execute(sql_create, (username, password))
    sql_alter = "ALTER USER %s@'%%' IDENTIFIED BY %s;"
    pdb.execute(sql_alter, (username, password))

    sql = "GRANT REPLICATION SLAVE ON *.* TO %s@'%%';"
    result = pdb.execute(sql, (username,))

    isError = isSqlError(result)
    if isError != None:
        return isError

    sql_select = "grant select,reload,REPLICATION CLIENT,PROCESS on *.* to '" + username + "'@'%';"
    pdb.execute(sql_select)
    pdb.execute('FLUSH PRIVILEGES;')

    addTime = time.strftime('%Y-%m-%d %X', time.localtime())
    psdb.add('username,password,accept,ps,addtime',
             (username, password, '%', '', addTime))
    return yf.returnJson(True, '添加成功!')


def getMasterRepSlaveUserCmdSsh(version):

    args = getArgs()
    data = checkArgs(args, ['username', 'db'])
    if not data[0]:
        return data[1]

    psdb = pSqliteDb('master_replication_user')
    f = 'username,password'
    username = args['username']
    if username == '':
        count = psdb.count()
        if count == 0:
            return yf.returnJson(False, '请添加同步账户!')

        clist = psdb.field(f).limit('1').order('id desc').select()
    else:
        clist = psdb.field(f).where("username=?", (username,)).limit(
            '1').order('id desc').select()

    if len(clist) == 0:
        return yf.returnJson(False, '错误同步账户!')

    ip = yf.getLocalIp()
    port = getMyPort()
    db = pMysqlDb()

    mstatus = db.query('show master status')
    if len(mstatus) == 0:
        return yf.returnJson(False, '未开启!')

    mode = recognizeDbMode()

    # 查找同步点
    # SELECT BINLOG_GTID_POS('master1-bin.000002', 561866201);

    sid = getDbServerId()
    connection_name = ""
    if sid != '':
        connection_name = "'r{}' ".format(sid)

    # MASTER_USE_GTID={current_pos|slave_pos|no}
    # current_pos  依赖-> select @@global.gtid_current_pos;
    # slave_pos  依赖-> select @@global.gtid_slave_pos;
    # no -> 啥都不依赖,保证多主同步成功。同步出现问题,根据日志查找问题。

    base_sql = "CHANGE MASTER " + connection_name + "TO MASTER_HOST='" + ip + "', MASTER_PORT=" + port + ", MASTER_USER='" + \
            clist[0]['username']  + "', MASTER_PASSWORD='" + \
            clist[0]['password'];
    sql = ''
    sql += base_sql + "', MASTER_LOG_FILE='" + mstatus[0]["File"] + \
            "',MASTER_LOG_POS=" + str(mstatus[0]["Position"])
    data = {}
    data['cmd'] = sql
    data["info"] = clist[0]
    data['mode'] = mode
    return yf.returnJson(True, 'ok!', data)

def getMasterRepSlaveUserCmd(version):

    args = getArgs()
    data = checkArgs(args, ['username', 'db'])
    if not data[0]:
        return data[1]

    psdb = pSqliteDb('master_replication_user')
    f = 'username,password'
    username = args['username']
    if username == '':
        count = psdb.count()
        if count == 0:
            return yf.returnJson(False, '请添加同步账户!')

        clist = psdb.field(f).limit('1').order('id desc').select()
    else:
        clist = psdb.field(f).where("username=?", (username,)).limit(
            '1').order('id desc').select()

    if len(clist) == 0:
        return yf.returnJson(False, '错误同步账户!')

    ip = yf.getLocalIp()
    port = getMyPort()
    db = pMysqlDb()

    mstatus = db.query('show master status')
    if len(mstatus) == 0:
        return yf.returnJson(False, '未开启!')

    mode = recognizeDbMode()

    # 查找同步点
    # SELECT BINLOG_GTID_POS('master1-bin.000002', 561866201);

    sid = getDbServerId()
    connection_name = ""
    if sid != '':
        connection_name = "'r{}' ".format(sid)

    # MASTER_USE_GTID={current_pos|slave_pos|no}
    # current_pos  依赖-> select @@global.gtid_current_pos;
    # slave_pos  依赖-> select @@global.gtid_slave_pos;
    # no -> 啥都不依赖,保证多主同步成功。同步出现问题,根据日志查找问题。

    base_sql = "CHANGE MASTER " + connection_name + "TO MASTER_HOST='" + ip + "', MASTER_PORT=" + port + ", MASTER_USER='" + \
            clist[0]['username']  + "', MASTER_PASSWORD='" + \
            clist[0]['password'];
    sql = ''
    sql += base_sql + "', MASTER_LOG_FILE='" + mstatus[0]["File"] + \
            "',MASTER_LOG_POS=" + str(mstatus[0]["Position"])
    sql += "<br/><hr/>";
    sql += base_sql + "',MASTER_USE_GTID=slave_pos,MASTER_CONNECT_RETRY=10;";    
    sql += "<br/>";

    data = {}
    data['cmd'] = sql
    data["info"] = clist[0]
    data['mode'] = mode

    return yf.returnJson(True, 'ok!', data)


def delMasterRepSlaveUser(version=''):
    args = getArgs()
    data = checkArgs(args, ['username'])
    if not data[0]:
        return data[1]

    name = str(args['username'])
    # 用户名会拼进 `drop user 'u'@'h'`（标识符无法参数化）→ 白名单化
    if not _DB_USER_IDENT_RE.match(name):
        return yf.returnJson(False, '用户名不合法!')

    pdb = pMysqlDb()
    psdb = pSqliteDb('master_replication_user')
    pdb.execute("drop user '" + name + "'@'%'")
    pdb.execute("drop user '" + name + "'@'localhost'")

    users = pdb.query("select Host from user where User=%s AND Host!='localhost'", (name,))
    if not isinstance(users, (list, tuple)):
        users = []
    for us in users:
        host = str(us["Host"] if isinstance(us, dict) else us[0])
        if not _DB_USER_IDENT_RE.match(host):
            continue
        pdb.execute("drop user '" + name + "'@'" + host + "'")

    psdb.where("username=?", (args['username'],)).delete()

    return yf.returnJson(True, '删除成功!')


def updateMasterRepSlaveUser(version=''):
    args = getArgs()
    data = checkArgs(args, ['username', 'password'])
    if not data[0]:
        return data[1]

    username = args['username']
    password = args['password']
    if not _DB_USER_IDENT_RE.match(username):
        return yf.returnJson(False, '用户名不合法!')

    pdb = pMysqlDb()
    psdb = pSqliteDb('master_replication_user')
    pdb.execute("drop user '" + username + "'@'%'")

    # 口令/账号走 ORM 参数化（不手写 `\'`）；`'%%'` 是 host 通配符经 pymysql 插值后的形态
    sql_create = "CREATE USER IF NOT EXISTS %s@'%%' IDENTIFIED BY %s;"
    pdb.execute(sql_create, (username, password))
    sql_alter = "ALTER USER %s@'%%' IDENTIFIED BY %s;"
    pdb.execute(sql_alter, (username, password))

    pdb.execute("GRANT REPLICATION SLAVE ON *.* TO %s@'%%';", (username,))

    psdb.where("username=?", (username,)).save(
        'password', password)

    return yf.returnJson(True, '更新成功!')


def getSlaveSSHList(version=''):
    args = getArgs()
    data = checkArgs(args, ['page', 'page_size'])
    if not data[0]:
        return data[1]

    # 分页容错：历史缺陷是分页参数裸 int() → page=abc 直接 ValueError traceback。
    # def_size=5 与 postgresql 同接口一致（js/mariadb.js::getSlaveSSHPage 也是 page_size=5）。
    page, page_size = _parsePageArgs(args, def_size=5)

    conn = pSqliteDb('slave_id_rsa')
    limit = str((page - 1) * page_size) + ',' + str(page_size)

    field = 'id,ip,port,db_user,id_rsa,ps,addtime'
    clist = conn.field(field).limit(limit).order('id desc').select()
    count = conn.count()

    data = {}
    _page = {}
    _page['count'] = count
    _page['p'] = page
    _page['row'] = page_size
    # 缺 tojs 时回退到本接口的前端回调（js/mariadb.js::getSlaveSSHPage）
    _page['tojs'] = args.get('tojs', 'getSlaveSSHPage')
    data['page'] = yf.getPage(_page)
    data['data'] = clist

    return yf.getJson(data)


def getSlaveSyncUserByIp(version=''):
    args = getArgs()
    data = checkArgs(args, ['ip'])
    if not data[0]:
        return data[1]

    ip = args['ip']

    conn = pSqliteDb('slave_sync_user')
    data = conn.field('ip,port,user,pass,mode,cmd').where(
        "ip=?", (ip,)).select()
    return yf.returnJson(True, 'ok', data)


def addSlaveSyncUser(version=''):
    import base64

    args = getArgs()
    data = checkArgs(args, ['ip'])
    if not data[0]:
        return data[1]

    ip = args['ip']
    if ip == "":
        return yf.returnJson(True, 'ok')
    ip = yf.safeSyncIp(ip)
    if not ip:
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')

    data = checkArgs(args, ['port', 'user', 'pass', 'mode'])
    if not data[0]:
        return data[1]

    cmd = args['cmd']
    # 写入侧白名单：端口 1–65535、用户名限字符集（拒引号/空白/shell 元字符）；
    # 口令只拒控制字符（用户裁定 P0-1④），安全性由触发侧的 shlexQuote / SQL 参数化承担。
    port = yf.safeSyncPort(args['port'])
    user = yf.safeSyncUser(args['user'])
    apass = yf.safeSyncPass(args['pass'])
    mode = args['mode']
    if not (port and user and apass):
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')
    port = str(port)
    addTime = time.strftime('%Y-%m-%d %X', time.localtime())

    conn = pSqliteDb('slave_sync_user')
    data = conn.field('ip').where("ip=?", (ip,)).select()
    if len(data) > 0:
        res = conn.where("ip=?", (ip,)).save(
            'port,user,pass,mode,cmd', (port, user, apass, mode, cmd))
    else:
        # 列名列表曾重复 `user`（与 mysql 侧逐字节相同；SQLite 容忍重复列名并忽略
        # 第二个，值恰好仍逐列对齐，故未暴露），但这是「换 ORM/换库即静默错列」的
        # landmine，且与值元组长度不一致。同族参照：本文件 `slave_id_rsa` 的 add 调用是 7 列 7 值。
        conn.add('ip,port,user,cmd,pass,mode,addtime',
                 (ip, port, user, cmd, apass, mode, addTime))

    return yf.returnJson(True, '设置成功!')


def delSlaveSyncUser(version=''):
    args = getArgs()
    data = checkArgs(args, ['ip'])
    if not data[0]:
        return data[1]

    ip = args['ip']

    conn = pSqliteDb('slave_sync_user')
    conn.where("ip=?", (ip,)).delete()
    return yf.returnJson(True, '删除成功!')


def getSlaveSyncUserList(version=''):
    args = getArgs()
    data = checkArgs(args, ['page', 'page_size'])
    if not data[0]:
        return data[1]

    # 分页容错：历史缺陷是分页参数裸 int() → page=abc 直接 ValueError traceback。
    # def_size=5 与同族的「从库 SSH」列表一致（js/mariadb.js::getSlaveSyncUserPage 亦为 5）。
    page, page_size = _parsePageArgs(args, def_size=5)

    conn = pSqliteDb('slave_sync_user')
    limit = str((page - 1) * page_size) + ',' + str(page_size)

    field = 'id,ip,port,user,pass,cmd,addtime'
    clist = conn.field(field).limit(limit).order('id desc').select()
    count = conn.count()

    data = {}
    _page = {}
    _page['count'] = count
    _page['p'] = page
    _page['row'] = page_size
    # 缺 tojs 时回退到本接口的前端回调（js/mariadb.js::getSlaveSyncUserPage）
    _page['tojs'] = args.get('tojs', 'getSlaveSyncUserPage')
    data['page'] = yf.getPage(_page)
    data['data'] = clist

    return yf.getJson(data)


def getSyncModeFile():
    return getServerDir() + "/sync.mode"


def getSlaveSyncMode(version):
    sync_mode = getSyncModeFile()
    if os.path.exists(sync_mode):
        mode = yf.readFile(sync_mode).strip()
        return yf.returnJson(True, 'ok', mode)
    return yf.returnJson(False, 'fail')


def setSlaveSyncMode(version):
    args = getArgs()
    data = checkArgs(args, ['mode'])
    if not data[0]:
        return data[1]
    mode = args['mode']
    sync_mode = getSyncModeFile()

    if mode == 'none':
        os.remove(sync_mode)
    else:
        yf.writeFile(sync_mode, mode)
    return yf.returnJson(True, '设置成功', mode)


def getSlaveSSHByIp(version=''):
    args = getArgs()
    data = checkArgs(args, ['ip'])
    if not data[0]:
        return data[1]

    ip = args['ip']

    conn = pSqliteDb('slave_id_rsa')
    data = conn.field('ip,port,db_user,id_rsa').where("ip=?", (ip,)).select()
    return yf.returnJson(True, 'ok', data)


def addSlaveSSH(version=''):
    import base64

    args = getArgs()
    data = checkArgs(args, ['ip'])
    if not data[0]:
        return data[1]

    ip = args['ip']
    if ip == "":
        return yf.returnJson(True, 'ok')
    # 写入侧白名单（与 addSlaveSyncUser 对称）：slave_id_rsa.ip 会被拼进 SSH 命令与
    # 主库回传的 CHANGE MASTER TO 语句，必须限为合法 IP
    ip = yf.safeSyncIp(ip)
    if not ip:
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')

    data = checkArgs(args, ['port', 'id_rsa', 'db_user'])
    if not data[0]:
        return data[1]

    id_rsa = args['id_rsa']
    port = args['port']
    db_user = args['db_user']
    user = 'root'
    addTime = time.strftime('%Y-%m-%d %X', time.localtime())

    conn = pSqliteDb('slave_id_rsa')
    data = conn.field('ip,id_rsa').where("ip=?", (ip,)).select()
    if len(data) > 0:
        res = conn.where("ip=?", (ip,)).save(
            'port,id_rsa,db_user', (port, id_rsa, db_user))
    else:
        conn.add('ip,port,user,id_rsa,db_user,ps,addtime',
                 (ip, port, user, id_rsa, db_user, '', addTime))

    return yf.returnJson(True, '设置成功!')


def delSlaveSSH(version=''):
    args = getArgs()
    data = checkArgs(args, ['ip'])
    if not data[0]:
        return data[1]

    ip = args['ip']

    conn = pSqliteDb('slave_id_rsa')
    conn.where("ip=?", (ip,)).delete()
    return yf.returnJson(True, 'ok')


def updateSlaveSSH(version=''):
    args = getArgs()
    data = checkArgs(args, ['ip', 'id_rsa'])
    if not data[0]:
        return data[1]

    ip = args['ip']
    id_rsa = args['id_rsa']
    conn = pSqliteDb('slave_id_rsa')
    conn.where("ip=?", (ip,)).save('id_rsa', (id_rsa,))
    return yf.returnJson(True, 'ok')


def getSlaveList(version=''):
    db = pMysqlDb()
    dlist = db.query('show slave status')
    if len(dlist) == 0:
        dlist = db.query('show all slaves status')

    data = {}
    data['data'] = dlist
    return yf.getJson(data)

def trySlaveSyncBugfix(version=''):
    if status(version) == 'stop':
        return yf.returnJson(False, 'MySQL未启动', [])

    mode_file = getSyncModeFile()
    if not os.path.exists(mode_file):
        return yf.returnJson(False, '需要先设置同步配置')

    mode = yf.readFile(mode_file)
    if mode != 'sync-user':
        return yf.returnJson(False, '仅支持【同步账户】模式')

    conn = pSqliteDb('slave_sync_user')
    slave_sync_data = conn.field('ip,port,user,pass,mode,cmd').select()
    if len(slave_sync_data) < 1:
        return yf.returnJson(False, '需要先添加【同步用户】配置!')

    # print(slave_sync_data)
    # 本地从库
    sdb = pMysqlDb()

    gtid_purged = ''

    for i in range(len(slave_sync_data)):
        port = slave_sync_data[i]['port']
        password = slave_sync_data[i]['pass']
        host = slave_sync_data[i]['ip']
        user = slave_sync_data[i]['user']

        # print(port, password, host)

        mdb = yf.getMyORM()
        mdb.setHost(host)
        mdb.setPort(port)
        mdb.setUser(user)
        mdb.setPwd(password)
        mdb.setSocket('')

        # var_gtid = mdb.query('show VARIABLES like "%gtid_purged%"')
        var_gtid = mdb.query('select @@global.gtid_current_pos as Value')
        #print(var_gtid)
        if len(var_gtid) > 0:
            gtid_purged += var_gtid[0]['Value'] + ','

    gtid_purged = gtid_purged.strip(',')
    sql = "set @@global.gtid_slave_pos='" + gtid_purged + "'"

    sdb.query('stop all slaves')
    # print(sql)
    sdb.query(sql)
    sdb.query('start all slaves')
    return yf.returnJson(True, '修复成功!')

def getSlaveSyncCmd(version=''):
    root = yf.getPanelDir()
    cmd = 'cd ' + root + ' && python3 ' + root + \
        '/plugins/mariadb/index.py do_full_sync {"db":"all","sign":""}'
    return yf.returnJson(True, 'ok', cmd)


def initSlaveStatus(version=''):
    mode_file = getSyncModeFile()
    if not os.path.exists(mode_file):
        return yf.returnJson(False, '需要先设置同步配置')

    mode = yf.readFile(mode_file)
    if mode == 'ssh':
        return initSlaveStatusSSH(version)
    if mode == 'sync-user':
        return initSlaveStatusSyncUser(version)


def parseSlaveSyncCmd(cmd):
    a = {}
    vlist = cmd.split(',')

    has_connection_name = vlist[0]

    pattern_c = r"CHANGE MASTER \'(.*)\' TO MASTER_HOST"
    match_val = re.match(pattern_c, has_connection_name, re.I)
    if match_val:
        m_groups = match_val.groups()
        a['Connection_name'] = m_groups[0]

    for i in vlist:
        tmp = i.strip()
        tmp_a = tmp.split(" ")
        real_tmp = tmp_a[len(tmp_a) - 1]
        kv = real_tmp.split("=")
        a[kv[0]] = kv[1].replace("'", '').replace("'", '').replace(";", '')
    return a

# python3 plugins/mariadb/index.py init_slave_status  {} 
def initSlaveStatusSyncUser(version=''):
    conn = pSqliteDb('slave_sync_user')

    slave_data = conn.field('id,ip,port,user,pass,mode,cmd').select()
    if len(slave_data) < 1:
        return yf.returnJson(False, '需要先添加同步用户配置!')

    pdb = pMysqlDb()
    if len(slave_data) == 1:
        dlist = pdb.query('show slave status')
        if len(dlist) > 0:
            return yf.returnJson(False, '已经初始化好了zz...')

    msg = ''

    pdb.query("stop slave")
    pdb.query("stop all slaves")

    local_mode = recognizeDbMode()
    for x in range(len(slave_data)):
        slave_t = slave_data[x]
        base_t = 'IP:' + slave_t['ip'] + ",PORT:" + \
            slave_t['port'] + ",USER:" + slave_t['user']

        mode_name = 'classic'
        if slave_data[x]['mode'] == '1':
            mode_name = 'gtid'

        if local_mode != mode_name:
            msg += base_t + '->同步模式不一致'
            continue

        cmd_sql = slave_t['cmd']
        if cmd_sql == '':
            msg += base_t + '->同步命令不能为空'
            continue

        try:
            pinfo = parseSlaveSyncCmd(cmd_sql)
        except Exception as e:
            return yf.returnJson(False, base_t + '->CMD同步命令不合规范:'+str(e))

        pdb.query(cmd_sql)

    pdb.query("start slave")
    pdb.query("start all slaves ")

    if msg == '':
        msg = '初始化成功!'
    return yf.returnJson(True, msg)


def initSlaveStatusSSH(version=''):
    db = pMysqlDb()
    dlist = db.query('show slave status')
    if len(dlist) == 0:
        dlist = db.query('show all slaves status')

    conn = pSqliteDb('slave_id_rsa')
    ssh_list = conn.field('ip,port,id_rsa,db_user').select()

    if len(ssh_list) < 1:
        return yf.returnJson(False, '需要先配置【[主]SSH配置】!')

    import paramiko
    paramiko.util.log_to_file('paramiko.log')
    ssh = paramiko.SSHClient()

    for data in ssh_list:
        ip = data['ip']
        master_port = data['port']
        SSH_PRIVATE_KEY = "/tmp/t_ssh_" + ip + ".txt"

        yf.writeFile(SSH_PRIVATE_KEY, data['id_rsa'].replace('\\n', '\n'))
        yf.execShell("chmod 600 " + SSH_PRIVATE_KEY)

        try:
            key = paramiko.RSAKey.from_private_key_file(SSH_PRIVATE_KEY)
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(hostname=ip, port=int(master_port),
                        username='root', pkey=key)

            db_user = data['db_user']
            cmd = 'cd ' + yf.shlexQuote(yf.getPanelDir()) + \
                ' && source bin/activate && python3 ' + \
                yf.shlexQuote(yf.getPanelDir() + '/plugins/mariadb/index.py') + \
                ' get_master_rep_slave_user_cmd_ssh ' + \
                yf.shlexQuote(json.dumps({'username': db_user, 'db': ''}))
            stdin, stdout, stderr = ssh.exec_command(cmd)
            result = stdout.read()
            result = result.decode('utf-8')
            if result.strip() == "":
                return yf.returnJson(False, '[主][' + ip + ']:获取同步命令失败!')
            cmd_data = json.loads(result)
            time.sleep(1)
            ssh.close()
            if not cmd_data['status']:
                return yf.returnJson(False, '[主][' + ip + ']:' + cmd_data['msg'])

            local_mode = recognizeDbMode()
            if local_mode != cmd_data['data']['mode']:
                return yf.returnJson(False, '[主][' + ip + ']【{}】从【{}】,运行模式不一致!'.format(cmd_data['data']['mode'], local_mode))

            u = cmd_data['data']['info']
            ps = u['username'] + "|" + u['password']
            conn.where('ip=?', (ip,)).setField('ps', ps)
            db.query('stop slave')
            db.query('stop all slaves')

            # 保证同步IP一致
            # ip 来自 slave_id_rsa（写入侧 addSlaveSSH 无校验），且会被拼进回传的
            # CHANGE MASTER TO 语句：拼 SQL 前必须白名单（否则 `'` 可从字符串里逃逸）
            safe_ip = yf.safeSyncIp(ip)
            if not safe_ip:
                return yf.returnJson(False, '[主][' + ip + ']:IP不合法，拒绝执行!')
            cmd = cmd_data['data']['cmd']
            if cmd.find('SOURCE_HOST') > -1:
                cmd = re.sub(r"SOURCE_HOST='(.*?)'",
                             "SOURCE_HOST='" + safe_ip + "'", cmd, 1)

            if cmd.find('MASTER_HOST') > -1:
                cmd = re.sub(r"MASTER_HOST='(.*?)'",
                             "MASTER_HOST='" + safe_ip + "'", cmd, 1)

            # 回传命令必须是一条 CHANGE MASTER TO / CHANGE REPLICATION SOURCE TO：
            # 否则主库侧用户可控的同步凭据可拼出任意 SQL
            cmd = yf.safeReplicationCmd(cmd)
            if not cmd:
                return yf.returnJson(False, '[主][' + ip + ']:同步命令不合规范，拒绝执行!')
            # print(cmd)
            # db.query 失败时返回 ORMError（SQL 错）或错误文本（连接失败）而不抛异常：
            # 必须显式判定，否则 CHANGE MASTER 从未生效仍会报「初始化成功!」（假成功）
            exec_res = db.query(cmd)
            if isinstance(exec_res, Exception) or isinstance(exec_res, str):
                return yf.returnJson(False, '[主][' + ip + ']:同步命令执行失败!' + str(exec_res))
            db.query("start slave")
            db.query("start all slaves")
            if os.path.exists(SSH_PRIVATE_KEY):
                yf.removeDir(SSH_PRIVATE_KEY)
        except Exception as e:
            return yf.returnJson(False, '[主][' + ip + ']:SSH认证配置连接失败!' + str(e))

    return yf.returnJson(True, '初始化成功!')


def setSlaveStatus(version=''):
    mode_file = getSyncModeFile()
    if not os.path.exists(mode_file):
        return yf.returnJson(False, '需要先设置同步配置')

    pdb = pMysqlDb()
    dlist = pdb.query('show slave status')
    if len(dlist) == 0:
        dlist = pdb.query('show all slaves status')

    if len(dlist) == 0:
        return yf.returnJson(False, '需要手动添加同步账户或者执行初始化!')

    for v in dlist:
        connection_name = ''
        cmd = "slave"
        if 'Connection_name' in v and v['Connection_name']:
            # 渠道名来自服务器回显（SHOW SLAVE STATUS），标识符位置无法参数化：白名单
            connection_name = yf.safeIdentifier(v['Connection_name'])
            if not connection_name:
                # 复用既有可翻译键：渠道名与「参数」同属非法字符拒绝
                return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')
            cmd = "slave '{}'".format(connection_name)

        if (v["Slave_IO_Running"] == 'Yes' or v["Slave_SQL_Running"] == 'Yes'):
            pdb.query("stop {}".format(cmd))
        else:
            pdb.query("start {}".format(cmd))

    return yf.returnJson(True, '设置成功!')


def deleteSlave(version=''):
    args = getArgs()
    db = pMysqlDb()
    if 'sign' in args:
        # sign 是用户入参，作为渠道名标识符无法参数化：白名单
        sign = yf.safeIdentifier(args['sign'])
        if not sign:
            return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')
        db.query("stop slave '{}'".format(sign))
        db.query("reset slave '{}' all".format(sign))
    else:
        db.query('stop slave')
        db.query('reset slave all')
    return yf.returnJson(True, '删除成功!')


def dumpMysqlData(version=''):
    args = getArgs()
    data = checkArgs(args, ['db'])
    if not data[0]:
        return data[1]

    db_arg = str(args['db']).strip()
    pwd = getRootPwd()
    mysql_dir = getServerDir()
    myconf = mysql_dir + "/etc/my.cnf"

    option = ''
    mode = recognizeDbMode()
    if mode == 'gtid':
        option = ' --set-gtid-purged=off '

    dump_file = '/tmp/dump.sql.gz'
    raw_file = '/tmp/dump.sql'
    if db_arg.lower() == 'all':
        # binlog-do-db 列表来自 my.cnf，仍逐个白名单化后再进命令
        dbs = [d.strip() for d in findBinlogDoDb() if re.match(r"^[\w\.-]+$", d.strip())]
        if not dbs:
            return 'fail'
    else:
        # 库名会被拼进命令；历史缺陷：`test1; touch /tmp/x` 以 root 在 shell 里执行
        if not re.match(r"^[\w\.-]+$", db_arg):
            return 'fail'
        dbs = [db_arg]

    dump_bin = mysql_dir + '/bin/mariadb-dump'
    if not os.path.exists(dump_bin):
        dump_bin = mysql_dir + '/bin/mysqldump'

    # 不再用 `dump | gzip` 管道：dump 非零退出时 gzip 仍返回 0，失败也会报 ok。
    # 改成 argv 列表 + 显式判退出码 + 单独压缩（不再经过 shell）。
    cmd = [dump_bin, '--defaults-file=' + myconf, '-uroot', '-p' + str(pwd), '--force']
    if option.strip():
        cmd.append(option.strip())
    cmd.append('--databases')
    cmd.extend(dbs)

    for f in (raw_file, dump_file):
        yf.deleteFile(f)
    try:
        with open(raw_file, 'wb') as _fo:
            _p = subprocess.Popen(cmd, stdout=_fo, stderr=subprocess.PIPE)
            _p.communicate(timeout=600)
            rc = _p.returncode
    except Exception:
        return 'fail'
    if rc != 0:
        return 'fail'
    rc2, _out, _err = yf.execShellRc(['gzip', '-f', raw_file], shell=False)
    if rc2 != 0 or not os.path.exists(dump_file) or os.path.getsize(dump_file) < 32:
        return 'fail'
    return 'ok'

############### --- 重要 数据补足同步 ---- ###########

def getSyncMysqlDB(dbname,sign = ''):
    conn = pSqliteDb('slave_sync_user')
    if sign != '':
        data = conn.field('ip,port,user,pass,mode,cmd').where('ip=?', (sign,)).find()
    else:
        data = conn.field('ip,port,user,pass,mode,cmd').find()
    if not data:
        # find() 查不到返回 None；旧实现 data['user'] 直接 TypeError。
        # 由调用方如实报错，不在这里造一个半残的 ORM 对象。
        return None
    user = data['user']
    apass = data['pass']
    port = data['port']
    ip = data['ip']
    # 远程数据
    sync_db = yf.getMyORM()
    # MySQLdb |
    sync_db.setPort(port)
    sync_db.setHost(ip)
    sync_db.setUser(user)
    sync_db.setPwd(apass)
    sync_db.setDbName(dbname)
    sync_db.setTimeout(60)
    return sync_db

def syncDatabaseRepairTempFile():
    tmp_log = yf.getYfLogs()+ '/mariadb-check.log'
    return tmp_log

def syncDatabaseRepairLog(version=''):
    import subprocess
    import sys
    import json
    args = getArgs()
    data = checkArgs(args, ['db','sign','op'])
    if not data[0]:
        return data[1]

    sync_args_db = args['db']
    sync_args_sign = args['sign']
    op = args['op']

    if not safe_check_args(db_name=sync_args_db, sign_val=sync_args_sign):
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')

    tmp_log = syncDatabaseRepairTempFile()
    json_args = json.dumps({"db": sync_args_db, "sign": sync_args_sign})
    script_path = yf.getPluginDir() + '/mariadb/index.py'
    cmd_list = [sys.executable, script_path, 'sync_database_repair', json_args]

    cmd = shlex.join(cmd_list)

    if op == 'get':
        log = yf.getLastLine(tmp_log, 15)
        return yf.returnJson(True, log)

    if op == 'cmd':
        return yf.returnJson(True, 'ok', cmd)

    if op == 'do':
        try:
            with open(tmp_log, 'w', encoding='utf-8') as f:
                f.write("开始执行\n")
            log_file = open(tmp_log, 'a', encoding='utf-8')
            subprocess.Popen(cmd_list, stdout=log_file, stderr=log_file)
            return yf.returnJson(True, 'ok')
        except Exception as e:
            return yf.returnJson(False, '启动修复失败: ' + str(e))

    return yf.returnJson(False, '无效请求!')


def syncDatabaseRepair(version=''):
    time_stats_s = time.time()
    tmp_log = syncDatabaseRepairTempFile()

    from pymysql.converters import escape_string
    args = getArgs()
    data = checkArgs(args, ['db','sign'])
    if not data[0]:
        return data[1]

    sync_args_db = args['db']
    sync_args_sign = args['sign']
    if not safe_check_args(db_name=sync_args_db, sign_val=sync_args_sign):
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')

    # 本地数据
    local_db = pMysqlDb()
    # 远程数据
    sync_db = getSyncMysqlDB(sync_args_db,sync_args_sign)
    if sync_db is None:
        return yf.returnJson(False, '错误同步账户!')

    tables = local_db.query('show tables from `%s`' % sync_args_db)
    table_key = "Tables_in_" + sync_args_db
    inconsistent_table = []

    tmp_dir = '/tmp/sync_db_repair'
    yf.makeDirs(tmp_dir)

    for tb in tables:

        table_name = sync_args_db+'.'+tb[table_key]
        table_check_file = tmp_dir+'/'+table_name+'.txt'

        if os.path.exists(table_check_file):
            # print(table_name+', 已检查OK')
            continue

        primary_key_sql = "SHOW INDEX FROM "+table_name+" WHERE Key_name = 'PRIMARY';";
        primary_key_data = local_db.query(primary_key_sql)
        # print(primary_key_sql,primary_key_data)
        pkey_name = '*'
        if len(primary_key_data) == 1:
            pkey_name = primary_key_data[0]['Column_name']
        # print(pkey_name)
        if pkey_name != '*' :
            # 智能校验(由于服务器同步可能会慢,比较总数总是对不上)
            cmd_local_newpk_sql = 'select ' + pkey_name + ' from ' + table_name + " order by " + pkey_name + " desc limit 1"
            cmd_local_newpk_data = local_db.query(cmd_local_newpk_sql)
            # print(cmd_local_newpk_data)
            if len(cmd_local_newpk_data) == 1:
                # 比较总数
                cmd_count_sql = 'select count('+pkey_name+') as num from '+table_name + ' where '+pkey_name + ' <= '+ str(cmd_local_newpk_data[0][pkey_name])
                local_count_data = local_db.query(cmd_count_sql)
                sync_count_data = sync_db.query(cmd_count_sql)

                if local_count_data != sync_count_data:
                    print(cmd_count_sql)
                    print("all data compare: ",local_count_data, sync_count_data)
                else:
                    print(table_name+' smart compare check ok.')
                    yf.writeFile(tmp_log, table_name+' smart compare check ok.\n','a+')
                    yf.execShell("echo 'ok' > "+table_check_file)
                    continue



        # 比较总数
        cmd_count_sql = 'select count('+pkey_name+') as num from '+table_name
        local_count_data = local_db.query(cmd_count_sql)
        sync_count_data = sync_db.query(cmd_count_sql)

        if local_count_data != sync_count_data:
            print("all data compare: ",local_count_data, sync_count_data)
            inconsistent_table.append(table_name)
            diff = sync_count_data[0]['num'] - local_count_data[0]['num']
            print(table_name+', need sync. diff,'+str(diff))
            yf.writeFile(tmp_log, table_name+', need sync. diff,'+str(diff)+'\n','a+')
        else:
            print(table_name+' check ok.')
            yf.writeFile(tmp_log, table_name+' check ok.\n','a+')
            yf.execShell("echo 'ok' > "+table_check_file)


    # inconsistent_table = ['xx.xx']
    # 数据对齐
    for table_name in inconsistent_table:
        is_break = False
        while not is_break:
            local_db.ping()
            # 远程数据
            sync_db.ping()

            print("check table:"+table_name)
            yf.writeFile(tmp_log, "check table:"+table_name+'\n','a+')
            table_name_pos = 0
            table_name_pos_file = tmp_dir+'/'+table_name+'.pos.txt'
            primary_key_sql = "SHOW INDEX FROM "+table_name+" WHERE Key_name = 'PRIMARY';";
            primary_key_data = local_db.query(primary_key_sql)
            pkey_name = primary_key_data[0]['Column_name']

            if os.path.exists(table_name_pos_file):
                table_name_pos = yf.readFile(table_name_pos_file)
            

            data_select_sql = 'select * from '+table_name + ' where '+pkey_name+' > '+str(table_name_pos)+' limit 10000'
            print(data_select_sql)
            local_select_data = local_db.query(data_select_sql)

            time_s = time.time()
            sync_select_data = sync_db.query(data_select_sql)
            print(f'sync query cos:{time.time() - time_s:.4f}s')
            yf.writeFile(tmp_log, f'sync query cos:{time.time() - time_s:.4f}s\n','a+')

            # print(local_select_data)
            # print(sync_select_data)
            
            # print(len(local_select_data))
            # print(len(sync_select_data))
            print('pos:',str(table_name_pos),'local compare sync,',local_select_data == sync_select_data)
                

            cmd_count_sql = 'select count('+pkey_name+') as num from '+table_name
            local_count_data = local_db.query(cmd_count_sql)
            time_s = time.time()
            sync_count_data = sync_db.query(cmd_count_sql)
            print(f'sync count data cos:{time.time() - time_s:.4f}s')
            print(local_count_data,sync_count_data)
            # 数据同步有延迟，相等即任务数据补足完成
            if local_count_data[0]['num'] == sync_count_data[0]['num']:
                is_break = True
                break

            diff = sync_count_data[0]['num'] - local_count_data[0]['num']
            print("diff," + str(diff)+' line data!')

            if local_select_data == sync_select_data:
                data_count = len(local_select_data)
                if data_count == 0:
                    # yf.writeFile(table_name_pos_file, '0')
                    print(table_name+",data is equal ok..")
                    is_break = True
                    break

                # print(table_name,data_count)
                pos = local_select_data[data_count-1][pkey_name]
                print('pos',pos)
                progress = pos/sync_count_data[0]['num']
                print('progress,%.2f' % progress+'%')
                yf.writeFile(table_name_pos_file, str(pos))
            else:
                sync_select_data_len = len(sync_select_data)
                skip_idx = 0
                # 主库PK -> 查询本地 | 保证一致
                if sync_select_data_len > 0:
                    for idx in range(sync_select_data_len):
                        sync_idx_data = sync_select_data[idx]
                        local_idx_data = None
                        if idx in local_select_data:
                            local_idx_data = local_select_data[idx]
                        if sync_select_data[idx] == local_idx_data:
                            skip_idx = idx
                            pos = local_select_data[idx][pkey_name]
                            yf.writeFile(table_name_pos_file, str(pos))

                        # print(insert_data)
                        local_inquery_sql = 'select * from ' + table_name+ ' where ' +pkey_name+' = '+ str(sync_idx_data[pkey_name])
                        # print(local_inquery_sql)
                        ldata = local_db.query(local_inquery_sql)
                        # print('ldata:',ldata)
                        if len(ldata) == 0:
                            print("id:"+ str(sync_idx_data[pkey_name])+ " no exists, insert")
                            insert_sql = 'insert into ' + table_name
                            field_str = ''
                            value_str = ''
                            for field in sync_idx_data:
                                field_str += '`'+field+'`,'
                                value_str += '\''+escape_string(str(sync_idx_data[field]))+'\','
                            field_str = '(' +field_str.strip(',')+')'
                            value_str = '(' +value_str.strip(',')+')'
                            insert_sql = insert_sql+' '+field_str+' values'+value_str+';'
                            print(insert_sql)
                            r = local_db.execute(insert_sql)
                            print(r)
                        else:
                            # print('compare sync->local:',sync_idx_data ==  ldata[0] )
                            if ldata[0] == sync_idx_data:
                                continue

                            print("id:"+ str(sync_idx_data[pkey_name])+ " data is not equal, update")
                            update_sql = 'update ' + table_name
                            field_str = ''
                            value_str = ''
                            for field in sync_idx_data:
                                if field == pkey_name:
                                    continue
                                field_str += '`'+field+'`=\''+escape_string(str(sync_idx_data[field]))+'\','
                            field_str = field_str.strip(',')
                            update_sql = update_sql+' set '+field_str+' where '+pkey_name+'=\''+str(sync_idx_data[pkey_name])+'\';'
                            print(update_sql)
                            r = local_db.execute(update_sql)
                            print(r)

                # 本地PK -> 查询主库 | 保证一致
                # local_select_data_len = len(local_select_data)
                # if local_select_data_len > 0:
                #     for idx in range(local_select_data_len):
                #         if idx < skip_idx:
                #             continue
                #         local_idx_data = local_select_data[idx]
                #         print('local idx check', idx, skip_idx)
                #         local_inquery_sql = 'select * from ' + table_name+ ' where ' +pkey_name+' = '+ str(local_idx_data[pkey_name])
                #         print(local_inquery_sql)
                #         sdata = sync_db.query(local_inquery_sql)
                #         sdata_len = len(sdata)
                #         print('sdata:',sdata,sdata_len)
                #         if sdata_len == 0:
                #             delete_sql = 'delete from ' + table_name + ' where ' +pkey_name+' = '+ str(local_idx_data[pkey_name])
                #             print(delete_sql)
                #             r = local_db.execute(delete_sql)
                #             print(r)
                #             break
                    

            if is_break:
                print("break all")
                break
            time.sleep(3)
    print(f'data check cos:{time.time() - time_stats_s:.4f}s')
    print("data supplementation completed")
    yf.removeDir(tmp_dir)
    return 'ok'


############### --- 重要 同步---- ###########


def asyncTmpfile():
    path = '/tmp/mariadb_async_status.txt'
    return path


def writeDbSyncStatus(data):
    path = asyncTmpfile()
    yf.writeFile(path, json.dumps(data))


def fullSync(version=''):
    args = getArgs()
    data = checkArgs(args, ['db', 'begin'])
    if not data[0]:
        return data[1]
    if not safe_check_args(db_name=args['db'], sign_val=args.get('sign')):
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')

    sign = ''
    if 'sign' in args:
        sign = args['sign']

    status_file = asyncTmpfile()
    if args['begin'] == '1':
        # 拼接侧双保险：db/sign 已过白名单，仍逐段 shlexQuote（子进程 getArgs 按 JSON 解析）
        payload = json.dumps({'db': args['db'], 'sign': sign})
        cmd = 'cd ' + yf.shlexQuote(yf.getPanelDir()) + ' && python3 ' + \
            yf.shlexQuote(getPluginDir() + '/index.py') + ' do_full_sync ' + \
            yf.shlexQuote(payload) + ' &'
        # print(cmd)
        yf.execShell(cmd)
        return json.dumps({'code': 0, 'msg': '同步数据中!', 'progress': 0})

    if os.path.exists(status_file):
        c = yf.readFile(status_file)
        tmp = json.loads(c)
        if tmp['code'] == 1:
            sys_dump_sql = "/tmp/dump.sql"
            if os.path.exists(sys_dump_sql):
                dump_size = os.path.getsize(sys_dump_sql)
                tmp['msg'] = tmp['msg'] + ":" + "同步文件:" + yf.toSize(dump_size)
            c = json.dumps(tmp)

        # if tmp['code'] == 6:
        #     os.remove(status_file)
        return c

    return json.dumps({'code': 0, 'msg': '点击开始,开始同步!', 'progress': 0})


def fullSyncCmd():
    time_all_s = time.time()
    args = getArgs()
    data = checkArgs(args, ['db', 'sign'])
    if not data[0]:
        return data[1]

    db = args['db']
    sign = args['sign']
    if not safe_check_args(db_name=db, sign_val=sign):
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')

    cmd = 'cd ' + yf.shlexQuote(yf.getPanelDir()) + ' && source bin/activate && python3 ' + \
        yf.shlexQuote(yf.getPanelDir() + '/plugins/mariadb/index.py') + ' do_full_sync ' + \
        yf.shlexQuote(json.dumps({"db": db, "sign": sign}))
    return yf.returnJson(True,'ok',cmd)

# python3 plugins/mariadb/index.py do_full_sync {"db":"demo1","sign":"","beigin":"1"}
def doFullSync(version=''):
    args = getArgs()
    db = args.get('db')
    sign = args.get('sign')
    if not safe_check_args(db_name=db, sign_val=sign):
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')
    mode_file = getSyncModeFile()
    if not os.path.exists(mode_file):
        return yf.returnJson(False, '需要先设置同步配置')

    mode = yf.readFile(mode_file)
    if mode == 'ssh':
        return doFullSyncSSH(version)
    if mode == 'sync-user':
        return doFullSyncUser(version)


def doFullSyncUser(version=''):
    which_pv = yf.execShell('which pv')
    is_exist_pv = False
    if os.path.exists(which_pv[0]):
        is_exist_pv = True


    args = getArgs()
    data = checkArgs(args, ['db', 'sign'])
    if not data[0]:
        return data[1]
    if not safe_check_args(db_name=args['db'], sign_val=args['sign']):
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')

    time_all_s = time.time()
    sync_db = args['db']
    sync_sign = args['sign']

    # print(sync_sign, sync_db)
    db = pMysqlDb()

    conn = pSqliteDb('slave_sync_user')
    if sync_sign != '':
        data = conn.field('ip,port,user,pass,mode,cmd').where(
            'ip=?', (sync_sign,)).find()
    else:
        data = conn.field('ip,port,user,pass,mode,cmd').find()

    if not data:
        writeDbSyncStatus({'code': 0, 'msg': '请添加同步账户!', 'progress': 0})
        return False
    # 触发侧再校验一次：库里的值可能是加固前的写入侧存进去的，不能只信写入侧
    user = yf.safeSyncUser(data['user'])
    apass = yf.safeSyncPass(data['pass'])
    port = yf.safeSyncPort(data['port'])
    ip = yf.safeSyncIp(data['ip'])
    if not (user and apass and port and ip):
        writeDbSyncStatus({'code': 0, 'msg': '同步账户配置非法，请重新添加!', 'progress': 0})
        return False

    bak_file = '/tmp/tmp.sql'
    if os.path.exists(bak_file):
        yf.removeDir(bak_file)

    writeDbSyncStatus({'code': 0, 'msg': '开始同步...', 'progress': 0})

    dmp_option = ''
    mode = recognizeDbMode()
    # if mode == 'gtid':
    #     dmp_option = ' --set-gtid-purged=off '

    writeDbSyncStatus({'code': 1, 'msg': '远程导出数据...', 'progress': 10})

    find_run_dump = yf.execShell('ps -ef | grep mariadb-dump | grep -v grep')
    if find_run_dump[0] != "":
        print("正在远程导出数据中,别着急...")
        writeDbSyncStatus({'code': 3.1, 'msg': '正在远程导出数据中,别着急...', 'progress': 39})
        return False

    time_s = time.time()
    if not os.path.exists(bak_file):
        dmp_option += " --master-data=1 --apply-slave-statements --include-master-host-port "

        # https://mariadb.com/kb/zh-cn/mariadb-dump/
        dump_sql_data = getServerDir() + "/bin/mariadb-dump " + dmp_option + " -f --default-character-set=utf8 --single-transaction --compress -q -h" + \
            yf.shlexQuote(ip) + " -P" + yf.shlexQuote(port) + " -u" + yf.shlexQuote(user) + " -p" + \
            yf.shlexQuote(apass) + " " + sync_db + ">" + yf.shlexQuote(bak_file)
        print(dump_sql_data)
        yf.execShell(dump_sql_data)

    time_e = time.time()
    export_cos = time_e - time_s
    print("export cos:", export_cos)
    writeDbSyncStatus({'code': 3, 'msg': '导出耗时:'+str(int(export_cos))+'秒,正在到本地导入数据中...', 'progress': 40})


    find_run_import = yf.execShell('ps -ef | grep mariadb| grep '+ bak_file +' | grep -v grep')
    if find_run_import[0] != "":
        print("正在导入数据中,别着急...")
        writeDbSyncStatus({'code': 4.1, 'msg': '正在导入数据中,别着急...', 'progress': 59})
        return False

    # if os.path.exists(bak_file):
    #     db.execute('reset master')

    time_s = time.time()
    if os.path.exists(bak_file):
        pwd = getRootPwd()
        sock = getSocketFile()

        # pwd/sock/bak_file/sync_db 均为拼接进 shell 的变量，逐段 shlexQuote
        if is_exist_pv:
            my_import_cmd = getServerDir() + '/bin/mariadb -S ' + yf.shlexQuote(sock) + ' -uroot -p' + yf.shlexQuote(pwd) + ' ' + yf.shlexQuote(sync_db)
            my_import_cmd = "pv -t -p " + yf.shlexQuote(bak_file) + '|' + my_import_cmd
            print(my_import_cmd)
            yf.execShell(my_import_cmd)
        else:
            my_import_cmd = getServerDir() + '/bin/mariadb -S ' + yf.shlexQuote(sock) + ' -uroot -p' + yf.shlexQuote(pwd) + ' ' + yf.shlexQuote(sync_db) + ' < ' + yf.shlexQuote(bak_file)
            print(my_import_cmd)
            yf.execShell(my_import_cmd)

    time_e = time.time()
    import_cos = time_e - time_s
    print("import cos:", import_cos)
    writeDbSyncStatus({'code': 4, 'msg': '导入耗时:'+str(int(import_cos))+'秒', 'progress': 60})

    time.sleep(3)

    pinfo = parseSlaveSyncCmd(data['cmd'])
    # print(pinfo)
    if 'Connection_name' in pinfo and pinfo['Connection_name']:
        # Connection_name 来自 slave_sync_user 表里存的 cmd（用户可控），标识符无法参数化：白名单
        channel = yf.safeIdentifier(pinfo['Connection_name'])
        if not channel:
            writeDbSyncStatus({'code': 0, 'msg': '同步渠道名非法，拒绝执行!', 'progress': 0})
            return False
        db.query("start slave '{}'".format(channel))
    else:
        db.query("start slave")

    writeDbSyncStatus({'code': 6, 'msg': '从库重启完成...', 'progress': 100})

    if os.path.exists(bak_file):
        yf.removeDir(bak_file)
    return True


def doFullSyncSSH(version=''):

    args = getArgs()
    data = checkArgs(args, ['db', 'sign'])
    if not data[0]:
        return data[1]
    if not safe_check_args(db_name=args['db'], sign_val=args['sign']):
        return yf.returnJson(False, '安全警告：参数包含非法字符，拒绝执行!')

    db = pMysqlDb()

    sync_db = args['db']
    sync_sign = args['sign']

    id_rsa_conn = pSqliteDb('slave_id_rsa')
    if sync_sign != '':
        data = id_rsa_conn.field('ip,port,db_user,id_rsa').where(
            'ip=?', (sync_sign,)).find()
    else:
        data = id_rsa_conn.field('ip,port,db_user,id_rsa').find()
    if not data:
        writeDbSyncStatus({'code': 0, 'msg': '请添加同步账户!', 'progress': 0})
        return 'fail'

    SSH_PRIVATE_KEY = "/tmp/mysql_sync_id_rsa.txt"
    id_rsa = data['id_rsa'].replace('\\n', '\n')
    yf.writeFile(SSH_PRIVATE_KEY, id_rsa)

    ip = data["ip"]
    master_port = data['port']
    db_user = data['db_user']
    print("master ip:", ip)

    writeDbSyncStatus({'code': 0, 'msg': '开始同步...', 'progress': 0})

    import paramiko
    paramiko.util.log_to_file('paramiko.log')
    ssh = paramiko.SSHClient()

    print(SSH_PRIVATE_KEY)
    if not os.path.exists(SSH_PRIVATE_KEY):
        writeDbSyncStatus({'code': 0, 'msg': '需要配置SSH......', 'progress': 0})
        return 'fail'

    try:
        yf.execShell("chmod 600 " + SSH_PRIVATE_KEY)
        key = paramiko.RSAKey.from_private_key_file(SSH_PRIVATE_KEY)
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        print(ip, master_port)

        # pkey=key
        # key_filename=SSH_PRIVATE_KEY
        ssh.connect(hostname=ip, port=int(master_port),
                    username='root', pkey=key)
    except Exception as e:
        print(str(e))
        writeDbSyncStatus(
            {'code': 0, 'msg': 'SSH配置错误:' + str(e), 'progress': 0})
        return 'fail'

    writeDbSyncStatus({'code': 0, 'msg': '登录Master成功...', 'progress': 5})
    dbname = args['db']
    cmd = "cd " + yf.getPanelDir() + " && source bin/activate &&  python3 plugins/mariadb/index.py dump_mysql_data {\"db\":'" + dbname + "'}"
    print(cmd)
    stdin, stdout, stderr = ssh.exec_command(cmd)
    result = stdout.read()
    result = result.decode('utf-8')
    if result.strip() == 'ok':
        writeDbSyncStatus({'code': 1, 'msg': '主服务器备份完成...', 'progress': 30})
    else:
        writeDbSyncStatus(
            {'code': 1, 'msg': '主服务器备份失败...:' + str(result), 'progress': 100})
        return 'fail'

    print("同步文件", "start")
    # cmd = 'scp -P' + str(master_port) + ' -i ' + SSH_PRIVATE_KEY + \
    #     ' root@' + ip + ':/tmp/dump.sql.gz /tmp'
    t = ssh.get_transport()
    sftp = paramiko.SFTPClient.from_transport(t)
    copy_status = sftp.get("/tmp/dump.sql.gz", "/tmp/dump.sql.gz")
    print("同步信息:", copy_status)
    print("同步文件", "end")
    if copy_status == None:
        writeDbSyncStatus({'code': 2, 'msg': '数据同步本地完成...', 'progress': 40})

    cmd = 'cd ' + yf.shlexQuote(yf.getPanelDir()) + \
        ' && source bin/activate && python3 ' + \
        yf.shlexQuote(yf.getPanelDir() + '/plugins/mariadb/index.py') + \
        ' get_master_rep_slave_user_cmd ' + \
        yf.shlexQuote(json.dumps({'username': db_user, 'db': ''}))
    stdin, stdout, stderr = ssh.exec_command(cmd)
    result = stdout.read()
    result = result.decode('utf-8')

    if result == '':
        writeDbSyncStatus({'code': 1, 'msg': '同步命令获取失败!', 'progress': 100})
        return 'fail'

    cmd_data = json.loads(result)

    db.query('stop slave')
    db.query('stop all slaves')
    writeDbSyncStatus({'code': 3, 'msg': '停止从库完成...', 'progress': 45})

    cmd = cmd_data['data']['cmd']
    # 保证同步IP一致
    # ip 来自 slave_id_rsa（写入侧 addSlaveSSH 无校验）：拼进 SQL 前必须白名单
    safe_ip = yf.safeSyncIp(ip)
    if not safe_ip:
        writeDbSyncStatus({'code': 0, 'msg': '同步账户IP不合法，拒绝执行!', 'progress': 0})
        return 'fail'
    if cmd.find('SOURCE_HOST') > -1:
        cmd = re.sub(r"SOURCE_HOST='(.*)'", "SOURCE_HOST='" + safe_ip + "'", cmd, 1)

    if cmd.find('MASTER_HOST') > -1:
        cmd = re.sub(r"MASTER_HOST='(.*)'", "MASTER_HOST='" + safe_ip + "'", cmd, 1)

    # 回传命令必须是一条 CHANGE MASTER TO / CHANGE REPLICATION SOURCE TO
    cmd = yf.safeReplicationCmd(cmd)
    if not cmd:
        writeDbSyncStatus({'code': 0, 'msg': '同步命令不合规范，拒绝执行!', 'progress': 0})
        return 'fail'

    db.query(cmd)
    uinfo = cmd_data['data']['info']
    ps = uinfo['username'] + "|" + uinfo['password']
    id_rsa_conn.where('ip=?', (ip,)).setField('ps', ps)
    writeDbSyncStatus({'code': 4, 'msg': '刷新从库同步信息完成...', 'progress': 50})

    pwd = getRootPwd()
    root_dir = getServerDir()
    msock = root_dir + "/mysql.sock"
    yf.execShell("cd /tmp && gzip -d dump.sql.gz")
    cmd = root_dir + "/bin/mysql -S " + msock + \
        " -uroot -p" + str(pwd or '') + " < /tmp/dump.sql"
    import_data = yf.execShell(cmd)
    if import_data[0] == '':
        print(import_data[1])
        writeDbSyncStatus({'code': 5, 'msg': '导入数据完成...', 'progress': 90})
    else:
        print(import_data[0])
        writeDbSyncStatus({'code': 5, 'msg': '导入数据失败...', 'progress': 100})
        return 'fail'

    db.query("start slave")
    db.query("start all slaves")
    writeDbSyncStatus({'code': 6, 'msg': '从库重启完成...', 'progress': 100})

    yf.removeDir(SSH_PRIVATE_KEY)
    yf.removeDir('/tmp/dump.sql')
    return True


def installPreInspection(version):
    # 互斥检查：MySQL 已安装时不允许同时安装 MariaDB
    mysql_path = yf.getServerDir() + "/mysql"
    if os.path.exists(mysql_path) and os.path.exists(mysql_path + "/bin"):
        return "检测到 MySQL 已安装，MariaDB 与 MySQL 不能同时共存，请先卸载 MySQL 再安装 MariaDB！"

    swap_path = yf.getServerDir() + "/swap"
    if not os.path.exists(swap_path):
        return "为了稳定安装MariaDB,先安装swap插件!"
    return 'ok'


def uninstallPreInspection(version):
    stop(version)
    if yf.isDebugMode():
        return 'ok'

    return "请手动删除MariaDB[{}]<br/> rm -rf {}".format(version, getServerDir())

if __name__ == "__main__":
    func = sys.argv[1]

    version = "10.6"
    version_pl = getServerDir() + "/version.pl"
    if os.path.exists(version_pl):
        version = yf.readFile(version_pl).strip()

    if func == 'check_plugin_upgrade':
        print(checkPluginUpgrade(version))
    elif func == 'upgrade_self_healing':
        print(upgradeSelfHealing(version))
    elif func == 'status':
        print(status(version))
    elif func == 'self_check':
        # 归一化：selfCheck 正常返回 dict；万一被外部/历史实现换成 JSON 串也不会崩
        #（mysql 插件旧写法在这里 AttributeError → 自检通过却 exit 1）
        _sc = _resultDict(selfCheck(version))
        print(json.dumps(_sc, ensure_ascii=False))
        sys.exit(0 if _sc.get('status') else 1)
    elif func == 'mariadb_upgrade':
        print(runMariaUpgrade(version))
    elif func == 'stop_and_kill':
        print(stopAndKill(version))
    elif func == 'start':
        print(start(version))
    elif func == 'stop':
        print(stop(version))
    elif func == 'restart':
        print(restart(version))
    elif func == 'reload':
        print(reload(version))
    elif func == 'initd_status':
        print(initdStatus())
    elif func == 'initd_install':
        print(initdInstall())
    elif func == 'initd_uninstall':
        print(initdUinstall())
    elif func == 'install_pre_inspection':
        print(installPreInspection(version))
    elif func == 'uninstall_pre_inspection':
        print(uninstallPreInspection(version))
    elif func == 'run_info':
        print(runInfo(version))
    elif func == 'db_status':
        print(myDbStatus())
    elif func == 'set_db_status':
        print(setDbStatus())
    elif func == 'conf':
        print(getConf())
    elif func == 'bin_log':
        print(binLog())
    elif func == 'binlog_list':
        print(binLogList())
    elif func == 'clean_bin_log':
        print(cleanBinLog())
    elif func == 'error_log':
        print(getErrorLog())
    elif func == 'show_log':
        print(getShowLogFile())
    elif func == 'my_db_pos':
        print(getMyDbPos())
    elif func == 'set_db_pos':
        print(setMyDbPos())
    elif func == 'my_port':
        print(getMyPort())
    elif func == 'set_my_port':
        print(setMyPort())
    elif func == 'init_pwd':
        print(initMysqlPwd())
    elif func == 'root_pwd':
        print(rootPwd())
    elif func == 'get_db_list':
        print(getDbList())
    elif func == 'set_db_backup':
        print(setDbBackup())
    elif func == 'import_db_backup':
        print(importDbBackup())
    elif func == 'import_db_external':
        print(importDbExternal())
    elif func == 'import_db_external_progress':
        print(importDbExternalProgress())
    elif func == 'import_db_external_progress_bar':
        print(importDbExternalProgressBar())
    elif func == 'delete_db_backup':
        print(deleteDbBackup())
    elif func == 'get_db_backup_list':
        print(getDbBackupList())
    elif func == 'get_db_backup_import_list':
        print(getDbBackupImportList())
    elif func == 'add_db':
        print(addDb())
    elif func == 'del_db':
        print(delDb())
    elif func == 'sync_get_databases':
        print(syncGetDatabases())
    elif func == 'sync_to_databases':
        print(syncToDatabases())
    elif func == 'set_root_pwd':
        print(setRootPwd(version))
    elif func == 'set_user_pwd':
        print(setUserPwd(version))
    elif func == 'get_db_access':
        print(getDbAccess())
    elif func == 'set_db_access':
        print(setDbAccess())
    elif func == 'fix_db_access':
        print(fixDbAccess(version))
    elif func == 'get_db_rw':
        print(setDbRw(version))
    elif func == 'set_db_ps':
        print(setDbPs())
    elif func == 'get_db_info':
        print(getDbInfo())
    elif func == 'repair_table':
        print(repairTable())
    elif func == 'opt_table':
        print(optTable())
    elif func == 'alter_table':
        print(alterTable())
    elif func == 'get_total_statistics':
        print(getTotalStatistics())
    elif func == 'get_dbrun_mode':
        print(getDbrunMode(version))
    elif func == 'set_dbrun_mode':
        print(setDbrunMode(version))
    elif func == 'reset_master':
        print(resetMaster(version))
    elif func == 'get_masterdb_list':
        print(getMasterDbList(version))
    elif func == 'get_master_status':
        print(getMasterStatus(version))
    elif func == 'set_master_status':
        print(setMasterStatus(version))
    elif func == 'set_db_master':
        print(setDbMaster(version))
    elif func == 'set_db_slave':
        print(setDbSlave(version))
    elif func == 'set_dbmaster_access':
        print(setDbMasterAccess())
    elif func == 'get_master_rep_slave_list':
        print(getMasterRepSlaveList(version))
    elif func == 'add_master_rep_slave_user':
        print(addMasterRepSlaveUser(version))
    elif func == 'del_master_rep_slave_user':
        print(delMasterRepSlaveUser(version))
    elif func == 'update_master_rep_slave_user':
        print(updateMasterRepSlaveUser(version))
    elif func == 'get_master_rep_slave_user_cmd_ssh':
        print(getMasterRepSlaveUserCmdSsh(version))
    elif func == 'get_master_rep_slave_user_cmd':
        print(getMasterRepSlaveUserCmd(version))
    elif func == 'get_slave_list':
        print(getSlaveList(version))
    elif func == 'try_slave_sync_bugfix':
        print(trySlaveSyncBugfix(version))
    elif func == 'get_slave_sync_cmd':
        print(getSlaveSyncCmd(version))
    elif func == 'get_slave_ssh_list':
        print(getSlaveSSHList(version))
    elif func == 'get_slave_ssh_by_ip':
        print(getSlaveSSHByIp(version))
    elif func == 'add_slave_ssh':
        print(addSlaveSSH(version))
    elif func == 'del_slave_ssh':
        print(delSlaveSSH(version))
    elif func == 'update_slave_ssh':
        print(updateSlaveSSH(version))
    elif func == 'get_slave_sync_user_list':
        print(getSlaveSyncUserList(version))
    elif func == 'get_slave_sync_user_by_ip':
        print(getSlaveSyncUserByIp(version))
    elif func == 'add_slave_sync_user':
        print(addSlaveSyncUser(version))
    elif func == 'del_slave_sync_user':
        print(delSlaveSyncUser(version))
    elif func == 'get_slave_sync_mode':
        print(getSlaveSyncMode(version))
    elif func == 'set_slave_sync_mode':
        print(setSlaveSyncMode(version))
    elif func == 'init_slave_status':
        print(initSlaveStatus(version))
    elif func == 'set_slave_status':
        print(setSlaveStatus(version))
    elif func == 'delete_slave':
        print(deleteSlave(version))
    elif func == 'full_sync':
        print(fullSync(version))
    elif func == 'do_full_sync':
        print(doFullSync(version))
    elif func == 'full_sync_cmd':
        print(fullSyncCmd())
    elif func == 'dump_mysql_data':
        print(dumpMysqlData(version))
    elif func == 'sync_database_repair':
        print(syncDatabaseRepair())
    elif func == 'sync_database_repair_log':
        print(syncDatabaseRepairLog())
    else:
        print('error')
