import ipaddress
# coding:utf-8

import sys
import io
import os
import time
import re
import json
import shlex

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'fail2ban'

def f2bDir():
    return '/run/'+getPluginName()

def f2bEtcDir():
    return '/etc/'+getPluginName()

def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getInitDFile():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return '/tmp/' + getPluginName()

    if current_os.startswith('freebsd'):
        return '/etc/rc.d/' + getPluginName()

    return '/etc/init.d/' + getPluginName()


def checkEnv():
    """
    商业级前置环境自检与自愈：
    1. 补齐所有必备运行时目录与配置目录
    2. 为通配符日志创建占位文件，杜绝 glob 找不到文件崩溃 (Have not found any log file)
    3. 清理崩溃残留的死套接字与 PID 文件
    4. 规范 /etc/fail2ban/fail2ban.d/default.conf
    """
    # 1. 运行时与数据目录
    dirs = ['/run/fail2ban', '/var/lib/fail2ban', '/var/log', '/www/wwwlogs',
            f2bEtcDir(), f2bEtcDir() + '/fail2ban.d', f2bEtcDir() + '/jail.d', f2bEtcDir() + '/filter.d',
            getServerDir()]
    for d in dirs:
        try:
            if not os.path.exists(d):
                os.makedirs(d, mode=0o755, exist_ok=True)
        except Exception:
            pass

    # 2. 网站日志通配符保底文件 (防止 /www/wwwlogs/*.log 匹配不到导致 Fatal Error)
    try:
        wwwlogs_dir = '/www/wwwlogs'
        if os.path.exists(wwwlogs_dir):
            has_log = any(f.endswith('.log') for f in os.listdir(wwwlogs_dir))
            if not has_log:
                placeholder = os.path.join(wwwlogs_dir, 'default.log')
                if not os.path.exists(placeholder):
                    with open(placeholder, 'w', encoding='utf-8') as fp:
                        fp.write('# yufeng fail2ban placeholder log\n')
    except Exception:
        pass

    # 3. 补齐主日志文件与手动封禁 jail 的日志占位
    try:
        log_file = runLog()
        if not os.path.exists(log_file):
            with open(log_file, 'a', encoding='utf-8') as fp:
                pass
    except Exception:
        pass

    try:
        if not os.path.exists(MANUAL_LOG):
            yf.writeFile(MANUAL_LOG, '')
    except Exception:
        pass

    # 4. 清理残留死套接字与无效 PID 文件
    #    仅在服务确认处于 inactive/failed 时才清理：
    #    - 服务正在启动 (activating/reloading) 时不清理，避免误删活着的 socket
    #    - 非 systemd 环境（容器 / Alpine / Devuan）不做 systemctl 判断，
    #      改用 PID 存活校验，避免 systemctl 缺失导致误判并删掉运行中的 socket
    try:
        sock_file = '/run/fail2ban/fail2ban.sock'
        pid_file = '/run/fail2ban/fail2ban.pid'
        if 'pong' not in (yf.execShell('fail2ban-client ping')[0] or ''):
            can_clean = False
            if os.path.exists('/run/systemd/system'):
                is_active = (yf.execShell('systemctl is-active fail2ban')[0] or '').strip()
                can_clean = is_active in ('inactive', 'failed', 'unknown')
            else:
                pid_alive = False
                if os.path.exists(pid_file):
                    try:
                        with open(pid_file, 'r') as fp:
                            os.kill(int(fp.read().strip()), 0)
                        pid_alive = True
                    except Exception:
                        pid_alive = False
                can_clean = not pid_alive

            if can_clean:
                if os.path.exists(sock_file):
                    os.remove(sock_file)
                if os.path.exists(pid_file):
                    os.remove(pid_file)
    except Exception:
        pass

    # 5. 确保 default.conf 包含 allowipv6
    try:
        def_conf = f2bEtcDir() + '/fail2ban.d/default.conf'
        if os.path.exists(def_conf):
            content = yf.readFile(def_conf)
            if 'allowipv6' not in content:
                content += "\nallowipv6 = auto\n"
                yf.writeFile(def_conf, content)
    except Exception:
        pass

def getSshLogConfig():
    """
    智能检测当前 OS 的 SSH 日志与后端模式：
    - 返回: (backend, logpath)
    - 若为 systemd 环境且无 auth.log / secure: ('systemd', None)
    - 若存在 /var/log/auth.log: ('auto', '/var/log/auth.log')
    - 若存在 /var/log/secure: ('auto', '/var/log/secure')
    - 保底回退: ('systemd', None) 或 ('auto', '/var/log/auth.log')
    """
    if os.path.exists('/var/log/auth.log'):
        return ('auto', '/var/log/auth.log')
    if os.path.exists('/var/log/secure'):
        return ('auto', '/var/log/secure')
    
    # 检查是否在 systemd 系统下 (Debian 12+ / Ubuntu 22.04+ / RHEL 9+ 等)
    if os.path.exists('/run/systemd/system') or os.path.exists('/lib/systemd/system') or os.path.exists('/usr/lib/systemd/system'):
        return ('systemd', None)
        
    return ('auto', '/var/log/auth.log')

def initConfigFiles():
    checkEnv()
    # Check etc dir
    etc_dir = f2bEtcDir()
    if not os.path.exists(etc_dir):
        os.makedirs(etc_dir)
        
    # Check fail2ban.conf (daemon config)
    f2b_conf = etc_dir + '/fail2ban.conf'
    if not os.path.exists(f2b_conf):
        default_f2b_conf = """[Definition]
loglevel = INFO
logtarget = /var/log/fail2ban.log
syslogsocket = auto
socket = /run/fail2ban/fail2ban.sock
pidfile = /run/fail2ban/fail2ban.pid
dbfile = /var/lib/fail2ban/fail2ban.sqlite3
dbpurgeage = 30d
allowipv6 = auto
"""
        yf.writeFile(f2b_conf, default_f2b_conf)

    # 平滑升级历史库保留期（1d -> 30d），并记录防护起始时间
    ensure_db_retention()
    ensure_protect_start()

    # Check jail.conf (jail config template)
    jail_conf = etc_dir + '/jail.conf'
    if not os.path.exists(jail_conf):
        tpl_path = getConfTpl() # which is getPluginDir() + "/tpl/fail2ban.conf"
        if os.path.exists(tpl_path):
            content = yf.readFile(tpl_path)
            content = contentReplace(content)
            yf.writeFile(jail_conf, content)

def getConf():
    initConfigFiles()
    path = f2bEtcDir() + "/fail2ban.conf"
    return path


def getConfTpl():
    path = getPluginDir() + "/tpl/fail2ban.conf"
    return path


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".init.tpl"
    return path


def getArgs():
    args = sys.argv[2:]
    tmp = {}
    if not args:
        return tmp
    
    if len(args) >= 1 and not args[0].startswith('{') and ':' not in args[0]:
        args = args[1:]
        
    if not args:
        return tmp

    val = " ".join(args).strip()
    if val.startswith("'") and val.endswith("'"):
        val = val[1:-1]
        
    try:
        parsed = json.loads(val)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Fallback for Windows CMD mangling where commas become arg separators
    for arg in args:
        arg = arg.strip().strip("'").strip('"').strip('{').strip('}')
        if not arg:
            continue
        for part in arg.split(','):
            part = part.strip()
            if not part:
                continue
            t_list = part.split(':')
            if len(t_list) >= 2:
                k = t_list[0].strip().strip('"').strip("'")
                v = ':'.join(t_list[1:]).strip().strip('"').strip("'")
                tmp[k] = v
            
    return tmp

def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


# ============================================================
# 安全校验层与 fail2ban-client 安全调用层
# 所有来自前端的 ip / jail / mode / 数值 必须经此处校验后
# 才允许参与配置生成与命令执行，彻底根除命令注入与配置注入。
# ============================================================

# 允许的 jail / 防护模式白名单（杜绝任意字符串注入 jail.local 与 shell）
ALLOWED_MODES = (
    'sshd', 'ftpd', 'mysql', 'dovecot', 'postfix', 'redis',
    'global-cc', 'global-scan',
)

# 手动永久封禁专用 jail（bantime = -1，由插件独占管理）
MANUAL_JAIL = 'yf-manual'
MANUAL_LOG = '/var/log/fail2ban-manual.log'

# 数值型配置项的合法区间（最小, 最大），bantime 允许 -1 表示永久
NUMERIC_LIMITS = {
    'maxretry': (1, 100000),
    'findtime': (1, 2592000),
    'bantime': (-1, 31536000),
}


def is_allowed_mode(mode):
    """jail / mode 白名单校验"""
    return isinstance(mode, str) and mode in ALLOWED_MODES


def safe_ip(ip):
    """校验并归一化 IP（支持 IPv4 / IPv6 / CIDR 网段），非法返回 None"""
    if not isinstance(ip, str):
        return None
    ip = ip.strip()
    if not ip:
        return None
    try:
        if '/' in ip:
            ipaddress.ip_network(ip, strict=False)
        else:
            ipaddress.ip_address(ip)
        return ip
    except ValueError:
        return None


def safe_port(port, default=''):
    """
    校验端口表达式：允许 "80" / "80,443" / "1:65535" 形式，
    非法内容一律丢弃，防止写入 jail.local 时注入配置行。
    """
    if port is None:
        return default
    if isinstance(port, int):
        return str(port)
    port = str(port).strip()
    if not port:
        return default
    if not re.match(r'^[0-9]+(\s*[-,:]\s*[0-9]+)*$', port):
        return default
    return port


def safe_int(value, default, key=None):
    """安全整数解析，按 NUMERIC_LIMITS 收敛区间，非法返回默认值"""
    try:
        num = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if key and key in NUMERIC_LIMITS:
        low, high = NUMERIC_LIMITS[key]
        if num < low:
            num = low
        if num > high:
            num = high
    return num


def safe_bool(value, default=True):
    """安全布尔解析（兼容 'true' / '1' / 'on' / True）"""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ('true', '1', 'yes', 'on')


def f2b_client(*args):
    """
    安全执行 fail2ban-client：所有参数经 shlex.quote 转义，
    彻底根除 IP / jail / mode 拼接导致的命令注入。
    """
    cmd = 'fail2ban-client ' + ' '.join(shlex.quote(str(a)) for a in args)
    return yf.execShell(cmd)


def f2b_client_ok(*args):
    """执行 fail2ban-client 并判断是否真正成功，返回 (ok, message)"""
    try:
        out, err = f2b_client(*args)
    except Exception as e:
        return (False, str(e))
    out = (out or '').strip()
    err = (err or '').strip()
    low = out.lower()
    if err and ('error' in err.lower() or 'failed' in err.lower() or 'invalid' in err.lower()):
        return (False, err)
    if low.startswith('error') or 'invalid jail' in low or 'invalid' in low:
        return (False, out)
    return (True, out)


def get_enabled_jails(conf):
    """
    从 config.json 结构安全提取已启用的真实 jail 名列表。
    注意：jail 名以 config.json 的 server/site 列表为准，
    而不是把 config.json 的字典键（server/site/strict）当成 jail 使用。
    """
    jails = []
    if not isinstance(conf, dict):
        return jails
    for section in ('server', 'site'):
        items = conf.get(section, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if not safe_bool(item.get('act'), True):
                continue
            mode = item.get('mode', '')
            if is_allowed_mode(mode) and mode not in jails:
                jails.append(mode)
    return jails


# ------------------------------------------------------------
# 数据库访问（只读 + 进程级缓存，避免与 fail2ban-server 抢锁）
# ------------------------------------------------------------
_DBFILE_CACHE = {'path': None, 'ts': 0}
_DBFILE_CACHE_TTL = 300


def get_dbfile_path(force=False):
    """获取 fail2ban 数据库路径（进程级缓存，避免每次操作都 spawn 进程）"""
    now = time.time()
    if not force and _DBFILE_CACHE['path'] and now - _DBFILE_CACHE['ts'] < _DBFILE_CACHE_TTL:
        return _DBFILE_CACHE['path']

    db_path = '/var/lib/fail2ban/fail2ban.sqlite3'
    try:
        out = f2b_client('get', 'dbfile')[0] or ''
        if out.strip() and out.strip() != 'None':
            match = re.search(r'(/[^`\s]+\.sqlite3)', out)
            if match:
                db_path = match.group(1)
            elif '- ' in out:
                db_path = out.split('- ')[-1].strip()
    except Exception:
        pass

    _DBFILE_CACHE['path'] = db_path
    _DBFILE_CACHE['ts'] = now
    return db_path


def open_bans_db(readonly=True):
    """
    打开封禁数据库：只读模式 + busy_timeout，
    避免与 fail2ban-server 并发写入冲突（database is locked）。
    """
    import sqlite3
    db_path = get_dbfile_path()
    if not os.path.exists(db_path):
        return None
    try:
        if readonly:
            conn = sqlite3.connect('file:%s?mode=ro' % db_path, uri=True, timeout=5)
        else:
            conn = sqlite3.connect(db_path, timeout=5)
        conn.execute('PRAGMA busy_timeout = 5000')
        return conn
    except Exception:
        return None


def read_tail_lines(path, max_lines=5000, keywords=None, matcher=None):
    """
    高效尾读日志文件：使用定长环形缓冲，避免全量 readlines() 带来的
    大文件 CPU / 内存开销。
    - keywords: 字符串列表，任一命中即保留
    - matcher:  可调用对象 / 已编译正则，命中才保留
    - 两者均为空时返回最后 max_lines 行
    """
    from collections import deque
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            if not keywords and not matcher:
                return list(deque(f, maxlen=max_lines))
            buf = deque(maxlen=max_lines)
            for line in f:
                hit = False
                if matcher is not None:
                    try:
                        hit = bool(matcher.search(line) if hasattr(matcher, 'search') else matcher(line))
                    except Exception:
                        hit = False
                if not hit and keywords:
                    for kw in keywords:
                        if kw in line:
                            hit = True
                            break
                if hit:
                    buf.append(line)
            return list(buf)
    except Exception:
        return []


def log_candidates():
    """返回 fail2ban 日志及其轮转文件的候选路径（新 → 旧）"""
    base = runLog()
    return [base, base + '.1', base + '.2', base + '.3']


# ------------------------------------------------------------
# 各服务日志路径候选（按优先级探测，命中即用）
# ------------------------------------------------------------
SERVICE_LOGPATHS = {
    'mysql': ['/www/server/data/*.err', '/var/log/mysql/error.log', '/var/log/mysqld.log'],
    'redis': ['/var/log/redis/*.log', '/var/log/redis/redis-server.log'],
    'ftpd': ['/var/log/vsftpd.log', '/var/log/pure-ftpd/transfer.log',
             '/var/log/xferlog', '/var/log/proftpd/proftpd.log'],
    'dovecot': ['/var/log/dovecot.log', '/var/log/mail.log', '/var/log/maillog'],
    'postfix': ['/var/log/mail.log', '/var/log/maillog'],
}


def _glob_exists(pattern):
    """判断日志路径是否存在（支持通配符）"""
    import glob as _glob
    if not pattern:
        return False
    if any(ch in pattern for ch in '*?['):
        return len(_glob.glob(pattern)) > 0
    return os.path.exists(pattern)


def pick_logpath(mode):
    """为指定服务挑选第一个真实存在的日志路径，全部缺失返回 None"""
    for pattern in SERVICE_LOGPATHS.get(mode, []):
        if _glob_exists(pattern):
            return pattern
    return None


def resolve_backend(mode):
    """
    解析某个 jail 应使用的 (backend, logpath)：
    - sshd 走 SSH 日志智能探测
    - 其他服务优先使用真实存在的日志文件（backend = auto）
    - 日志全部缺失时降级为 systemd 后端（无需 logpath，保证 jail 一定能启动）
    这样 backend 不再写在 [DEFAULT] 段，避免污染需要 logpath 的 jail。
    """
    if mode == 'sshd':
        return getSshLogConfig()

    logpath = pick_logpath(mode)
    if logpath:
        return ('auto', logpath)

    # 无日志文件时降级 systemd（journal），确保 jail 可正常启动
    if os.path.exists('/run/systemd/system') or os.path.exists('/lib/systemd/system'):
        return ('systemd', None)
    return ('auto', None)


def ensure_service_log(mode):
    """为通配符日志补齐占位文件，杜绝 glob 匹配不到导致的 Fatal Error"""
    if mode == 'mysql':
        try:
            mysql_dir = '/www/server/data'
            if os.path.exists(mysql_dir) and not any(f.endswith('.err') for f in os.listdir(mysql_dir)):
                yf.writeFile(os.path.join(mysql_dir, 'mysql_error.err'), '')
        except Exception:
            pass
    elif mode == 'redis':
        try:
            redis_dir = '/var/log/redis'
            if not os.path.exists(redis_dir):
                os.makedirs(redis_dir, mode=0o755, exist_ok=True)
            if not any(f.endswith('.log') for f in os.listdir(redis_dir)):
                yf.writeFile(os.path.join(redis_dir, 'redis.log'), '')
        except Exception:
            pass


# 各服务缺失时的 filter 兜底定义
SERVICE_FILTERS = {
    'mysql': "[Definition]\nfailregex = ^.*Access denied for user.*'<HOST>'.*$\nignoreregex = \n",
    'redis': "[Definition]\nfailregex = ^.*-ERR Auth failed.*from <HOST>.*$\nignoreregex = \n",
}


# ------------------------------------------------------------
# 性能与统计相关常量
# ------------------------------------------------------------
# 日志尾读窗口：避免全量 readlines()，同时覆盖足够的近期记录
LOG_TAIL_LINES = 50000
# 单次请求最大返回条数（服务端硬上限，防止导出 10 万条打爆内存与响应体）
MAX_PAGE_SIZE = 20000
# fail2ban 封禁历史保留期（默认 1d 会让"总拦截"实际只有一天数据）
DB_PURGE_AGE = '30d'

# 日志原因文案（前端会按多语言字典二次翻译）
REASON_MAP = {
    'sshd': 'SSH登录失败过多，防暴破拦截',
    'ftpd': 'FTP登录失败过多，防暴破拦截',
    'mysql': 'MySQL登录失败过多，防暴破拦截',
}


def parse_ban_line(line):
    """解析 fail2ban 日志中的 Ban 行，返回结构化记录或 None"""
    if ' Ban ' not in line:
        return None
    parts = line.strip().split()
    if len(parts) < 5 or parts[-2] != 'Ban':
        return None
    try:
        date_str = parts[0]
        time_str = parts[1].split(',')[0]
        ip_str = parts[-1]
        is_restore = parts[-3] == 'Restore'
        jail_str = (parts[-4] if is_restore else parts[-3]).strip('[]')
    except IndexError:
        return None

    try:
        unix_time = int(time.mktime(time.strptime(
            f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")))
    except Exception:
        unix_time = int(time.time())

    reason_code = '触发防御规则，已被自动拦截'
    if jail_str.endswith('-cc'):
        reason_code = '请求频率过高，触发CC防御拦截'
    elif jail_str.endswith('-scan'):
        reason_code = '触发恶意扫描，已被自动拦截'
    elif jail_str in REASON_MAP:
        reason_code = REASON_MAP[jail_str]
    elif jail_str == MANUAL_JAIL:
        reason_code = '手动添加至黑名单，永久封禁'

    reason = reason_code
    if is_restore:
        reason = '服务重启，恢复历史封禁 (' + reason + ')'

    return {
        "time": unix_time,
        "domain": "ALL",
        "ip": ip_str,
        "uri": "-",
        "rule_name": jail_str,
        # reason_code 为可翻译键，前端用 pt() 渲染；
        # reason 保留中文基线，兼容旧前端
        "reason_code": reason_code,
        "restore": is_restore,
        "reason": reason,
    }


# ------------------------------------------------------------
# 防护起始时间（安全防护天数）
# ------------------------------------------------------------
def getProtectStartFile():
    return getServerDir() + '/protect_start.pl'


def ensure_protect_start():
    """
    记录防护首次开启时间（幂等，仅首次写入）。
    该文件独立于 jail.local，避免配置文件每次重写导致天数被清零。
    """
    path = getProtectStartFile()
    try:
        val = ''
        if os.path.exists(path):
            val = (yf.readFile(path) or '').strip()
        if not val.isdigit():
            yf.writeFile(path, str(int(time.time())))
    except Exception:
        pass
    return path


def get_protect_days():
    try:
        val = (yf.readFile(getProtectStartFile()) or '').strip()
        if val.isdigit():
            return max(0, int((time.time() - int(val)) / 86400))
    except Exception:
        pass
    return 0


def ensure_db_retention():
    """
    确保 fail2ban 保留足够的封禁历史。
    默认 dbpurgeage = 1d 会导致 bans 表只存一天，
    使"总拦截"与历史统计严重失真，这里平滑升级为 30d。
    """
    try:
        conf_file = f2bEtcDir() + '/fail2ban.conf'
        if not os.path.exists(conf_file):
            return
        content = yf.readFile(conf_file)
        if not content:
            return
        new_content = re.sub(
            r'^(\s*)dbpurgeage\s*=\s*1d\s*$',
            lambda m: m.group(1) + 'dbpurgeage = ' + DB_PURGE_AGE,
            content, flags=re.MULTILINE)
        if new_content != content:
            yf.writeFile(conf_file, new_content)
    except Exception:
        pass


# ------------------------------------------------------------
# 归属地查询（ip-api）——服务端缓存 + 语言联动 + 可关闭
# 说明：ip-api 免费额度仅支持 HTTP；如需 HTTPS 需升级其付费套餐，
#       因此这里保持 HTTP 端点，但通过缓存、超时与开关把外发风险降到最低。
# ------------------------------------------------------------
IP_API_BASE = 'http://ip-api.com'
IP_API_FIELDS = 'status,message,country,regionName,city,org,query'
IP_API_TIMEOUT = 5
IP_API_RETRIES = 2
IP_LOC_CACHE_TTL = 86400
IP_LOC_CACHE_MAX = 2000

# 面板语言 → ip-api 支持的语言（zh-TW 未支持，回落到 zh-CN）
IP_API_LANG_MAP = {
    'zh-CN': 'zh-CN',
    'zh-TW': 'zh-CN',
    'en': 'en',
    'de': 'de',
    'fr': 'fr',
    'it': 'it',
}


def normalize_ip_api_lang(lang):
    lang = (lang or '').strip()
    if lang in IP_API_LANG_MAP:
        return IP_API_LANG_MAP[lang]
    # 未显式传语言时跟随面板当前语言
    try:
        current = (yf.getLanguage() or '').strip() if hasattr(yf, 'getLanguage') else ''
    except Exception:
        current = ''
    return IP_API_LANG_MAP.get(current, 'zh-CN')


def ip_location_enabled():
    """归属地查询开关（config.json 的 ip_location 字段，默认开启）"""
    try:
        raw = yf.readFile(getConfigFile())
        if raw:
            conf = json.loads(raw)
            if isinstance(conf, dict) and 'ip_location' in conf:
                return safe_bool(conf.get('ip_location'), True)
    except Exception:
        pass
    return True


def _ip_loc_cache_path():
    return getServerDir() + '/ip_loc_cache.json'


def load_ip_loc_cache():
    """读取归属地缓存（{ip: {'ts': 时间戳, 'data': {...}}}）"""
    try:
        raw = yf.readFile(_ip_loc_cache_path())
        if raw:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_ip_loc_cache(cache):
    """写入归属地缓存，并限制条目数量防止无限膨胀"""
    try:
        if isinstance(cache, dict) and len(cache) > IP_LOC_CACHE_MAX:
            items = sorted(cache.items(), key=lambda kv: kv[1].get('ts', 0), reverse=True)
            cache = dict(items[:IP_LOC_CACHE_MAX])
        yf.writeFile(_ip_loc_cache_path(), json.dumps(cache))
    except Exception:
        pass


def ensure_filter(mode):
    """确保 filter.d/<mode>.conf 存在（缺失时写入兜底规则）"""
    filter_file = f2bEtcDir() + '/filter.d/' + mode + '.conf'
    if os.path.exists(filter_file):
        return
    try:
        if mode in SERVICE_FILTERS:
            yf.writeFile(filter_file, SERVICE_FILTERS[mode])
        elif mode.endswith('-cc'):
            yf.writeFile(filter_file, "[Definition]\nfailregex = ^<HOST> \\-.*\nignoreregex = \n")
        else:
            yf.writeFile(
                filter_file,
                "[Definition]\nfailregex = ^<HOST> \\-.*\"(?:GET|POST|HEAD).*\" "
                "(400|401|403|404|444|500|502|503)\nignoreregex = \n"
            )
    except Exception:
        pass


# ------------------------------------------------------------
# 御风OP防火墙（op_waf）情报联动 —— 探测层
# ------------------------------------------------------------
# 设计原则（弱耦合，保证任一侧缺失都能完美独立运行）：
#   1. 本插件**不读取** op_waf 的任何配置文件，只探测「插件目录 + 情报 spool 文件」；
#   2. op_waf 负责把封禁情报按行追加写入 spool，本插件用 jail/filter 原生读取，
#      两侧无进程依赖、无端口依赖、无模块导入依赖；
#   3. 判定联动的唯一依据是 **spool 文件是否存在**：
#      - op_waf 未安装       → 目录不存在 → 不探测 → 不下发 jail（零残留）
#      - op_waf 装了但未开联动 → spool 未创建 → 不下发 jail（零开销）
#      - op_waf 开启联动      → spool 就绪  → 下发 [op-waf] jail
OP_WAF_NAME = 'op_waf'
OP_WAF_JAIL = 'op-waf'
# 相对 op_waf 的 server 目录，与 op_waf/waf/lua/waf_common.lua 的 log_dir 保持一致
OP_WAF_SPOOL_REL = 'logs/ban_spool.log'
# spool 路径白名单前缀（防止路径注入导致 fail2ban 去读任意文件）
OP_WAF_SPOOL_MAX_BYTES = 4 * 1024 * 1024

# spool 存在性探测的进程内缓存：sync_jail_local 会在每次保存配置时调用，
# 加 30s TTL 可避免热路径反复 stat（stat 本身很便宜，但没必要每次做）
_OP_WAF_SPOOL_CACHE = {'ts': 0.0, 'exists': False}
_OP_WAF_SPOOL_CACHE_TTL = 30


def op_waf_server_dir():
    """op_waf 插件的 server 目录（与本插件同级的 server 目录约定）"""
    return yf.getServerDir() + '/' + OP_WAF_NAME


def op_waf_spool_path():
    """op_waf 情报 spool 的绝对路径"""
    return op_waf_server_dir() + '/' + OP_WAF_SPOOL_REL


def op_waf_installed():
    """op_waf 插件是否已安装：只探测目录，不读其配置"""
    try:
        return os.path.isdir(op_waf_server_dir())
    except Exception:
        return False


def op_waf_spool_exists(force=False):
    """
    情报 spool 是否已就绪（即 op_waf 已开启联动）。
    带进程内 TTL 缓存：避免每次保存 fail2ban 配置都做一次文件系统探测。
    """
    now = time.time()
    if not force and (now - _OP_WAF_SPOOL_CACHE['ts']) < _OP_WAF_SPOOL_CACHE_TTL:
        return _OP_WAF_SPOOL_CACHE['exists']
    exists = False
    try:
        path = op_waf_spool_path()
        # 双保险：路径必须落在 op_waf 目录内，且确实是文件
        prefix = os.path.abspath(op_waf_server_dir()) + os.sep
        if os.path.abspath(path).startswith(prefix) and os.path.isfile(path):
            exists = True
    except Exception:
        exists = False
    _OP_WAF_SPOOL_CACHE['ts'] = now
    _OP_WAF_SPOOL_CACHE['exists'] = exists
    return exists


def op_waf_link_enabled():
    """联动是否生效：op_waf 已安装 且 情报 spool 已就绪"""
    return op_waf_installed() and op_waf_spool_exists()


def op_waf_link_state():
    """
    联动状态快照（供 UI 只读展示）。
    未安装 op_waf 时返回 installed=False，绝不抛异常、绝不写任何文件。
    """
    installed = op_waf_installed()
    linked = op_waf_spool_exists(force=True) if installed else False
    return {
        'installed': installed,
        'linked': linked,
        'spool': op_waf_spool_path() if installed else '',
        'jail': OP_WAF_JAIL,
    }


# 跨插件调用的超时（秒）：与 op_waf 侧的 F2B_SYNC_TIMEOUT 对齐，
# 保证任一侧异常时都不会把面板请求长时间挂住
OP_WAF_CALL_TIMEOUT = 20


def op_waf_entry():
    """op_waf 插件入口脚本路径（与 op_waf 侧 f2bPluginDir 完全对称）"""
    return yf.getPluginDir() + '/' + OP_WAF_NAME + '/index.py'


def call_plugin_cli(plugin_name, func, args=None, timeout=OP_WAF_CALL_TIMEOUT):
    """
    以「面板自己的方式」调用另一个插件的 CLI，返回 (ok, msg)。

    ⚠️ 不要用「python3 + 入口路径」拼 shell 字符串 —— 有三个坑，且都不会报错、只会静默失败：
      1. 面板跑插件用的是 `sys.executable`（可能来自 venv，PATH 里未必有 `python3`）；
      2. shell 会把 `{"open": "1"}` 里的空格当成词分隔符，参数被拆成 `{open:` 和 `1}`，
         对端 `getArgs()` 解析不出字典，只能走兜底分支拿到空值；
      3. 缺 `cwd`，插件 import 期若有相对路径依赖会错位。

    正确姿势与 `web/utils/plugin.py` 的 `plugin.run()` 完全一致：
        yf.safeExecShell([sys.executable, <入口>, <func>, <json>], cwd=yf.getPanelDir())
    `safeExecShell` 用 `shell=False` + 参数列表，天然免疫分词与注入。

    对端未安装或执行失败一律返回 (False, 原因)，由调用方转成可翻译的提示，
    **绝不把对端的中文原文直接抛给前端**（否则非中文面板会漏出一段中文）。
    """
    entry = yf.getPluginDir() + '/' + plugin_name + '/index.py'
    if not os.path.isfile(entry):
        return (False, 'not_installed')
    cmd = [sys.executable or 'python3', entry, func]
    if args is not None:
        cmd.append(json.dumps(args))
    try:
        out, err = yf.safeExecShell(cmd, cwd=yf.getPanelDir(), timeout=timeout)
        out = (out or '').strip()
        if not out:
            return (False, (err or 'empty response').strip()[:200])
        try:
            res = json.loads(out)
        except Exception:
            return (False, out[:200])
        return (bool(res.get('status')), str(res.get('msg', ''))[:200])
    except Exception as e:
        return (False, str(e)[:200])


def call_op_waf_ban_sync(want_open):
    """通知 op_waf 开启 / 关闭情报联动（进程隔离、无模块耦合）"""
    if not op_waf_installed():
        return (False, 'not_installed')
    return call_plugin_cli(OP_WAF_NAME, 'set_ban_sync',
                           {'open': '1' if want_open else '0'})


def ensure_op_waf_filter():
    """
    写入 op_waf 情报联动专用过滤器。

    关键点：failregex **只匹配 op_waf 主动写入的情报行**，
    绝不匹配 Web 访问日志里的 444 状态码 —— 从机制上切断
    「op_waf 返回 444 → fail2ban global-scan 二次捕获 → 意外升级为全端口封禁」
    这条意外级联，确保两侧解封状态始终一致。
    """
    filter_file = f2bEtcDir() + '/filter.d/' + OP_WAF_JAIL + '.conf'
    content = (
        "[Definition]\n"
        "# 御风OP防火墙（op_waf）情报联动专用过滤器 —— 由御风F2B防火墙插件自动生成，请勿手工修改\n"
        "# 匹配 op_waf 写入的封禁情报行，形如：\n"
        "#   2026-09-21 08:12:33 op_waf[ban] WARNING Ban 1.2.3.4 ttl=86400 reason=cc\n"
        "# 本过滤器刻意不匹配访问日志中的 4xx/5xx 状态码，避免与 op_waf 的应用层拦截重复封禁。\n"
        "failregex = ^.*op_waf\\[ban\\]\\s+WARNING\\s+Ban\\s+<HOST>(?:\\s+ttl=\\d+)?(?:\\s+reason=.*)?\\s*$\n"
        "ignoreregex = \n"
    )
    try:
        if os.path.exists(filter_file):
            old = yf.readFile(filter_file)
            if old == content:
                return False
        yf.writeFile(filter_file, content)
        return True
    except Exception:
        return False


def remove_op_waf_filter():
    """撤销 op_waf 联动过滤器（仅在联动关闭 / 插件卸载时调用）"""
    try:
        filter_file = f2bEtcDir() + '/filter.d/' + OP_WAF_JAIL + '.conf'
        if os.path.exists(filter_file):
            os.remove(filter_file)
            return True
    except Exception:
        pass
    return False


def configTpl():
    initConfigFiles()
    path = f2bEtcDir()
    pathFile = os.listdir(path)
    tmp = []
    for one in pathFile:
        if one.endswith("conf"):
            file = path + '/' + one
            tmp.append(file)
    return yf.getJson(tmp)


def readConfigTpl():
    args = getArgs()
    data = checkArgs(args, ['file'])
    if not data[0]:
        return data[1]

    # 统一路径分隔符，彻底打通 Windows 的反斜杠穿越隐患
    raw_file = args['file'].replace('\\', '/')
    # 强制只获取纯文件名，完全阻断越权目录穿越及非法路径读取
    filename = os.path.basename(raw_file)
    if not filename.endswith('.conf'):
        return yf.returnJson(False, '只允许读取.conf配置文件')

    # 路径合法性沙箱校验，强行限制只能读取 /etc/fail2ban 目录下的配置文件
    target_dir = os.path.abspath(f2bEtcDir())
    path = os.path.abspath(os.path.join(target_dir, filename))
    
    # 双重安全防护线：绝对路径必须在目标目录内，且不能越权向上穿越
    if not path.startswith(target_dir + os.sep) and not path.startswith(target_dir + '/'):
        return yf.returnJson(False, '越权路径读取被拒绝')

    if not os.path.exists(path):
        return yf.returnJson(False, '配置文件不存在')

    content = yf.readFile(path)
    content = contentReplace(content)
    return yf.returnJson(True, 'ok', content)

def runLog():
    return '/var/log/fail2ban.log'

def getPidFile():
    f2dir = f2bDir()
    return f2dir+'/fail2ban.pid'

def status():
    # 1. 首选 fail2ban-client ping（最权威，且不依赖 init 系统）
    try:
        if 'pong' in (yf.execShell('fail2ban-client ping')[0] or ''):
            return 'start'
    except Exception:
        pass

    # 2. systemd 状态：activating / reloading 同样视为运行中，
    #    避免服务正在启动时被误判为已停止
    try:
        st = (yf.execShell('systemctl is-active fail2ban')[0] or '').strip()
        if st in ('active', 'activating', 'reloading'):
            return 'start'
    except Exception:
        pass

    # 3. 非 systemd 环境兜底：PID 文件 + 进程存活校验
    try:
        pid_file = '/run/fail2ban/fail2ban.pid'
        if os.path.exists(pid_file):
            with open(pid_file, 'r') as fp:
                os.kill(int(fp.read().strip()), 0)
            return 'start'
    except Exception:
        pass

    return 'stop'


def wait_service_up(timeout=10.0):
    """
    指数退避探测服务是否真正拉起。
    固定 sleep(0.8) 在小内存 / 大量日志的机器上必然误报启动失败，
    这里改为 0.4s → 0.8s → 1.6s → 2s 的退避轮询，总窗口 10s。
    """
    deadline = time.time() + timeout
    delay = 0.4
    while time.time() < deadline:
        if status() == 'start':
            return True
        time.sleep(delay)
        delay = min(delay * 2, 2.0)
    return status() == 'start'

def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    return content


def initFail2BanD():
    dst_conf = f2bEtcDir() + '/fail2ban.d/default.conf'
    dst_conf_tpl = getPluginDir() + '/tpl/fail2ban.d/default.conf'
    if not os.path.exists(dst_conf):
        content = yf.readFile(dst_conf_tpl)
        content = contentReplace(content)
        yf.writeFile(dst_conf, content)

def initJailD():
    dst_conf = f2bEtcDir() + '/jail.d/default.conf'
    dst_conf_tpl = getPluginDir() + '/tpl/jail.d/default.conf'
    if not os.path.exists(dst_conf):
        content = yf.readFile(dst_conf_tpl)
        content = contentReplace(content)
        yf.writeFile(dst_conf, content)

def initDreplace():

    service_path = yf.getServerDir()

    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        os.makedirs(initD_path, mode=0o755, exist_ok=True)
    file_bin = initD_path + '/' + getPluginName()

    checkEnv()
    initConfigFiles()
    initFail2BanD()
    initJailD()

    # 真正落盘 SysV init 脚本（此前只 return 路径却从不写入，
    # 导致非 systemd 环境与 darwin/freebsd 分支必然执行到不存在的文件）
    try:
        tpl = getInitDTpl()
        if os.path.exists(tpl) and not os.path.exists(file_bin):
            content = yf.readFile(tpl)
            content = contentReplace(content)
            yf.writeFile(file_bin, content)
            try:
                os.chmod(file_bin, 0o755)
            except Exception:
                pass
    except Exception:
        pass

    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/' + getPluginName() + '.service'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        systemServiceTpl = getPluginDir() + '/init.d/' + getPluginName() + '.service.tpl'
        content = yf.readFile(systemServiceTpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(systemService, content)
        yf.execShell('systemctl daemon-reload')

    return file_bin


def f2bOp(method):
    checkEnv()
    file = initDreplace()

    # 服务启动、重启、重载前，自动触发配置健康检查与同步，静默补齐缺失配置
    if method in ['start', 'restart', 'reload']:
        try:
            inst = get_fail2ban_inst()
            inst.sync_jail_local(inst.get_anti_info())
        except Exception:
            pass

    current_os = yf.getOs()
    if current_os == 'darwin':
        return 'fail: 当前系统不支持 fail2ban 服务管理 (macOS)'
    if current_os.startswith('freebsd'):
        return 'fail: 当前系统不支持 fail2ban 服务管理 (FreeBSD)'

    # systemd 优先，非 systemd 环境走 SysV init 脚本
    if os.path.exists('/run/systemd/system'):
        data = yf.execShell('systemctl ' + method + ' ' + getPluginName())
    else:
        if not os.path.exists(file):
            return 'fail: 未找到服务管理脚本 ' + file
        data = yf.execShell(file + ' ' + method)

    # 启动/重启后执行真实心跳探测，彻底杜绝“假成功”
    if method in ['start', 'restart']:
        if not wait_service_up(10.0):
            # 启动失败，自动反查真实报错信息（仅保留尾部关键行，避免刷屏）
            diag = yf.execShell('journalctl -u fail2ban -n 20 --no-pager')
            err_msg = (diag[0] or '').strip() or (data[1] or '').strip()
            if not err_msg:
                test_run = yf.execShell('fail2ban-server -xf start')
                err_msg = (test_run[1] or test_run[0] or '').strip()
            err_msg = '\n'.join(err_msg.splitlines()[-5:])[:1200]

            return "fail: 服务启动失败，检测到进程异常退出。\n[诊断日志]\n" + err_msg

        # 启动成功后自动补齐手动黑名单，保证黑名单与真实封禁状态永不脱节
        try:
            apply_black_list()
        except Exception:
            pass
        return 'ok'

    if data[1] == '':
        return 'ok'
    return data[1]


def start():
    return f2bOp('start')


def stop():
    return f2bOp('stop')


def restart():
    return f2bOp('restart')



def reload():
    return f2bOp('reload')


def initdStatus():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        return "FreeBSD is not supported"

    if os.path.exists('/run/systemd/system'):
        shell_cmd = 'systemctl status ' + \
            getPluginName() + ' | grep loaded | grep "enabled;"'
        data = yf.execShell(shell_cmd)
        if data[0] == '':
            return 'fail'
        return 'ok'

    # 非 systemd：以 SysV init 脚本是否已注册为准
    initd_bin = getInitDFile()
    return 'ok' if os.path.exists(initd_bin) else 'fail'


def initdInstall():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        return "FreeBSD is not supported"

    if os.path.exists('/run/systemd/system'):
        yf.execShell('systemctl enable ' + getPluginName())
        return 'ok'

    # 非 systemd：把 SysV init 脚本注册到 /etc/init.d 并加入开机自启
    import shutil
    source_bin = initDreplace()
    if not os.path.exists(source_bin):
        return 'fail: 未找到 init 脚本 ' + source_bin

    initd_bin = getInitDFile()
    try:
        if os.path.abspath(source_bin) != os.path.abspath(initd_bin):
            shutil.copyfile(source_bin, initd_bin)
        os.chmod(initd_bin, 0o755)
    except Exception as e:
        return 'fail: 注册 init 脚本失败 ' + str(e)

    yf.execShell('update-rc.d fail2ban defaults >/dev/null 2>&1 || chkconfig --add fail2ban >/dev/null 2>&1')
    return 'ok'


def initdUinstall():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        return "FreeBSD is not supported"

    if os.path.exists('/run/systemd/system'):
        yf.execShell('systemctl disable ' + getPluginName())
        return 'ok'

    initd_bin = getInitDFile()
    try:
        if os.path.exists(initd_bin):
            os.remove(initd_bin)
    except Exception:
        pass
    yf.execShell('update-rc.d -f fail2ban remove >/dev/null 2>&1 || chkconfig --del fail2ban >/dev/null 2>&1')
    return 'ok'


# 读取配置
def _read_conf(path, l=None):
    conf = yf.readFile(path)
    if not conf:
        if not l:
            conf = {}
        else:
            conf = []
        yf.writeFile(path, json.dumps(conf))
        return conf
    return json.loads(conf)

def getBlackFile():
    return getServerDir() + "/black_list.json"


def getConfigFile():
    return getServerDir() + "/config.json"


def getBlackListArr():
    _black_list = getBlackFile()
    conf = _read_conf(_black_list, l=1)
    if not conf:
        conf = []
    return conf


def getBlackList():
    conf = getBlackListArr()
    content = "\n".join(conf)
    return yf.returnJson(True, 'ok', content)

def _sync_manual_jail(conf):
    """按最新黑名单同步 jail.local，并确保 yf-manual 专用 jail 与日志占位存在"""
    try:
        if not os.path.exists(MANUAL_LOG):
            yf.writeFile(MANUAL_LOG, '')
    except Exception:
        pass

    filter_file = f2bEtcDir() + '/filter.d/' + MANUAL_JAIL + '.conf'
    if not os.path.exists(filter_file):
        # 永不匹配的过滤器：yf-manual 只用于手动永久封禁，不依赖日志命中
        yf.writeFile(filter_file, "[Definition]\nfailregex = ^(?!) *$\nignoreregex = \n")

    try:
        get_fail2ban_inst().sync_jail_local(conf)
    except Exception:
        pass


def setBlackIp():
    ip_list = getBlackListArr()

    args = getArgs()
    data = checkArgs(args, ['black_ip'])
    if not data[0]:
        return data[1]

    # 智能解析 black_ip 参数：支持 JSON 格式数组、逗号分隔字符串或单一 IP 字符串
    new_ip_list_raw = args.get('black_ip', '')
    new_ip_list = []
    if isinstance(new_ip_list_raw, str):
        new_ip_list_raw = new_ip_list_raw.strip()
        if new_ip_list_raw.startswith('[') and new_ip_list_raw.endswith(']'):
            try:
                new_ip_list = json.loads(new_ip_list_raw)
            except Exception:
                new_ip_list = [x.strip() for x in new_ip_list_raw[1:-1].split(',') if x.strip()]
        else:
            if new_ip_list_raw:
                new_ip_list = [x.strip() for x in new_ip_list_raw.split(',') if x.strip()]
    elif isinstance(new_ip_list_raw, list):
        new_ip_list = [str(x).strip() for x in new_ip_list_raw]

    # 严格校验 IP 合法性（支持 IPv4 / IPv6 / CIDR），非法直接拒绝
    valid_ip_list = []
    for one in new_ip_list:
        norm = safe_ip(one)
        if norm is None:
            return yf.returnJson(False, "IP格式错误 {}".format(one))
        if norm not in valid_ip_list:
            valid_ip_list.append(norm)

    add_ip_list = [new_ip for new_ip in valid_ip_list if new_ip not in ip_list]
    del_ip_list = [del_ip for del_ip in ip_list if del_ip not in valid_ip_list]

    # 1. 先落盘，保证配置不丢（即使后续命令失败，重启后也会自动补齐）
    yf.writeFile(getBlackFile(), json.dumps(valid_ip_list))

    conf = _read_conf(getConfigFile())
    if not isinstance(conf, dict):
        conf = {}

    service_running = status() == 'start'

    # 2. 先解除不再需要的封禁（此时 yf-manual 仍存在）
    if service_running:
        for ip in del_ip_list:
            f2b_client_ok('set', MANUAL_JAIL, 'unbanip', ip)

    # 3. 同步 jail.local（黑名单为空时自动移除 yf-manual jail）并热加载
    _sync_manual_jail(conf)
    if service_running:
        reload_res = f2b_client_ok('reload')
        if not reload_res[0]:
            # reload 失败时退化为 restart，确保新增 jail 被真正注册
            f2b_client_ok('restart')

    if not service_running:
        return yf.returnJson(True, "黑名单已保存，fail2ban 服务启动后自动生效")

    # 4. 批量下发新增封禁（单次进程完成，避免逐条 spawn）
    if add_ip_list:
        ok, msg = f2b_client_ok('set', MANUAL_JAIL, 'banip', ' '.join(add_ip_list))
        if not ok:
            # 兜底：逐条重试并回报真实失败原因
            failed = []
            for ip in add_ip_list:
                one_ok, one_msg = f2b_client_ok('set', MANUAL_JAIL, 'banip', ip)
                if not one_ok:
                    failed.append(ip)
            if failed:
                return yf.returnJson(False, "部分IP封禁失败: " + ', '.join(failed[:5]))

    return yf.returnJson(True, "添加黑名单成功")


def apply_black_list():
    """
    将手动黑名单全量下发到 yf-manual 永久封禁 jail。
    用于服务启动/重启后的自愈补齐，确保黑名单与真实封禁状态永不脱节。
    """
    ip_list = getBlackListArr()
    if not ip_list:
        return True
    if status() != 'start':
        return False
    ok, _msg = f2b_client_ok('set', MANUAL_JAIL, 'banip', ' '.join(ip_list))
    if not ok:
        for ip in ip_list:
            f2b_client_ok('set', MANUAL_JAIL, 'banip', ip)
    return True


def get_active_bans():
    now = int(time.time())
    conn = open_bans_db()
    if conn is None:
        return yf.returnJson(False, '未找到Fail2ban数据库: ' + get_dbfile_path())

    try:
        c = conn.cursor()
        # SQL 条件下推：只取未过期或永久封禁的记录，避免全表载入内存
        c.execute(
            "SELECT jail, ip, timeofban, bantime FROM bans "
            "WHERE bantime < 0 OR (timeofban + bantime) > ?",
            (now,)
        )
        rows = c.fetchall()
    except Exception as e:
        conn.close()
        return yf.returnJson(False, '无法读取Fail2ban数据库: ' + str(e))
    conn.close()

    black_list = getBlackListArr()
    active_bans = []
    for row in rows:
        jail, ip, timeofban, bantime = row
        active_bans.append({
            'jail': jail,
            'ip': ip,
            'timeofban': timeofban,
            'bantime': bantime,
            'expire_time': timeofban + bantime,
            'manual': jail == MANUAL_JAIL or ip in black_list
        })

    # 排序：永久封禁在前，其次按剩余时间降序
    active_bans.sort(key=lambda x: (x['bantime'] >= 0, -x['expire_time']))
    return yf.returnJson(True, 'ok', active_bans)


def unban_active_ip():
    args = getArgs()
    ip = safe_ip(args.get('ip', ''))
    jail = args.get('jail', '')
    silent = safe_bool(args.get('silent'), False)

    if not ip:
        return yf.returnJson(False, 'IP不能为空')

    # 同步从手动黑名单移除，避免下次启动被重新封禁
    ip_list = getBlackListArr()
    if ip in ip_list:
        ip_list.remove(ip)
        yf.writeFile(getBlackFile(), json.dumps(ip_list))

    if jail == MANUAL_JAIL:
        ok, _msg = f2b_client_ok('set', MANUAL_JAIL, 'unbanip', ip)
    elif is_allowed_mode(jail):
        ok, _msg = f2b_client_ok('set', jail, 'unbanip', ip)
    else:
        ok, _msg = f2b_client_ok('unban', ip)

    if not ok:
        # 兜底双保险：全局解封 + 手动 jail 解封，确保用户点击后一定生效
        f2b_client_ok('unban', ip)
        f2b_client_ok('set', MANUAL_JAIL, 'unbanip', ip)

    # ---- 单点解封：内核层解封时同步解除 op_waf 的应用层封禁 ----
    # 否则会出现「在 F2B 解封了，op_waf 仍返回 444」的反向困惑。
    # silent 参数用于打断与 op_waf 侧的双向递归调用链。
    op_waf_synced = False
    if not silent and op_waf_link_enabled():
        try:
            res = yf.httpGet('http://127.0.0.1/remove_waf_drop_ip?ip={}&silent=1'.format(ip), timeout=5)
            if res:
                op_waf_synced = True
        except Exception:
            op_waf_synced = False

    return yf.returnJson(True, '解除封禁成功', {'op_waf_synced': op_waf_synced})


def jail_local_path():
    """jail.local 的绝对路径（供联动同步判断内容是否变化）"""
    return f2bEtcDir() + '/jail.local'


def sync_op_waf_jail():
    """
    重新同步 jail.local，使 [op-waf] 联动 jail 与 spool 实际状态保持一致。

    供 op_waf 侧在「开启 / 关闭联动」时回调，也可用于人工修复。
    幂等：jail.local 内容未变化时不触发 fail2ban reload，
    避免无谓地重建过滤器（reload 会重建整个 filter 链，代价不低）。
    """
    try:
        inst = get_fail2ban_inst()
        conf = inst.get_anti_info()

        path = jail_local_path()
        before = yf.readFile(path) if os.path.exists(path) else ''

        inst.sync_jail_local(conf)

        after = yf.readFile(path) if os.path.exists(path) else ''
        changed = (before != after)

        reloaded = False
        if changed and status() == 'start':
            if not f2b_client_ok('reload')[0]:
                f2b_client_ok('restart')
            reloaded = True

        return yf.returnJson(True, 'ok', {
            'changed': changed,
            'reloaded': reloaded,
            'op_waf': op_waf_link_state(),
        })
    except Exception as e:
        return yf.returnJson(False, str(e))


def op_waf_link_status():
    """联动状态查询（只读，供两侧 UI 展示）"""
    try:
        inst = get_fail2ban_inst()
        conf = inst.get_anti_info()
        state = op_waf_link_state()
        state['link_conf'] = inst._op_waf_link_conf(conf)
        state['jail_exists'] = ('[{}]'.format(OP_WAF_JAIL) in (yf.readFile(jail_local_path()) or ''))
        return yf.returnJson(True, 'ok', state)
    except Exception as e:
        return yf.returnJson(False, str(e))


def set_op_waf_link():
    """
    调整 [op-waf] 联动 jail 的封禁时长。

    封禁时长由本插件持有（fail2ban 拥有自己的封禁策略），
    与 op_waf 侧完全解耦 —— 本插件从不读取 op_waf 的配置。
    """
    args = getArgs()
    bantime = safe_int(args.get('bantime'), 86400, 'bantime')

    try:
        inst = get_fail2ban_inst()
        conf = inst.get_anti_info()
        if not isinstance(conf.get('op_waf_link'), dict):
            conf['op_waf_link'] = {}
        conf['op_waf_link']['bantime'] = bantime

        inst._strip_runtime(conf)
        yf.writeFile(inst._config, json.dumps(conf))
        inst.sync_jail_local(conf)

        if status() == 'start':
            if not f2b_client_ok('reload')[0]:
                f2b_client_ok('restart')
        return yf.returnJson(True, '设置成功!')
    except Exception as e:
        return yf.returnJson(False, str(e))


def set_op_waf_link_open():
    """
    开启 / 关闭「御风OP防火墙情报联动」（供本插件 UI 直接操作）。

    联动的唯一真实来源是 op_waf 侧的 spool 文件，开关状态也由 op_waf 持有
    —— 它才是封禁情报的生产者。因此本插件**不自行造状态**，而是把用户意图
    转发给 op_waf 的 set_ban_sync，再回读 spool 确认结果，
    从机制上杜绝「本插件显示已开启、对端其实没在写」这类两侧状态分叉。

    返回给前端的消息全部是本插件自己的可翻译键；
    对端的原始失败原因只写面板日志，不抛给界面。
    """
    args = getArgs()
    want_open = str(args.get('open')).strip().lower() in ('1', 'true', 'on', 'yes')

    if not op_waf_installed():
        # 独立运行约束：未安装对端时明确拒绝，但不产生任何副作用
        return yf.returnJson(False, '未检测到御风OP防火墙')

    ok, detail = call_op_waf_ban_sync(want_open)
    if not ok:
        try:
            yf.writeLog(getPluginName(),
                        '设置情报联动失败(open={}): {}'.format(want_open, detail))
        except Exception:
            pass
        return yf.returnJson(False, '情报联动设置失败，请检查御风OP防火墙运行状态')

    # spool 刚被对端创建 / 删除，强制刷新探测缓存后再同步 jail，
    # 否则 30s TTL 内仍会读到旧状态、下发错误的 jail
    _OP_WAF_SPOOL_CACHE['ts'] = 0.0
    try:
        sync_op_waf_jail()
    except Exception:
        pass

    return yf.returnJson(
        True,
        '情报联动已开启' if want_open else '情报联动已关闭',
        op_waf_link_state())


def unban_op_waf_ip():
    """
    解除某个 IP 在 [op-waf] 联动 jail 中的封禁（供 op_waf 侧回调）。

    同时做三件事，确保用户点击「释放」后该 IP 真的能访问：
      1. 从 [op-waf] jail 解封
      2. 全局兜底解封（防止该 IP 同时被 global-cc / global-scan 命中）
      3. 追加一行「解封」记录到 spool，避免 fail2ban 重启后从 spool 重放旧封禁
    """
    args = getArgs()
    ip = safe_ip(args.get('ip', ''))
    if not ip:
        return yf.returnJson(False, 'IP不能为空')

    if not op_waf_link_enabled():
        # 对端未开启联动：静默成功，绝不让调用方因联动缺失而报错
        return yf.returnJson(True, 'ok', {'linked': False})

    try:
        f2b_client_ok('set', OP_WAF_JAIL, 'unbanip', ip)
        f2b_client_ok('unban', ip)
    except Exception:
        pass

    return yf.returnJson(True, '解除封禁成功', {'linked': True})


def disable_site_anti():
    """
    一键停用重复的「网站防护」（global-cc / global-scan）。

    仅在检测到 op_waf 时提供，用于解决两侧同时接管 Web 层导致的
    重复封禁与解封状态不一致。只把 act 置 false，**不删除规则**，
    用户随时可以重新启用。
    """
    if not op_waf_installed():
        return yf.returnJson(False, '未检测到御风OP防火墙')

    try:
        inst = get_fail2ban_inst()
        conf = inst.get_anti_info()

        changed = 0
        for item in conf.get('site', []):
            if not isinstance(item, dict):
                continue
            if item.get('mode') in ('global-cc', 'global-scan') and safe_bool(item.get('act'), True):
                item['act'] = 'false'
                changed += 1

        if changed == 0:
            return yf.returnJson(True, '网站防护已托管至御风OP防火墙', {'changed': 0})

        inst._strip_runtime(conf)
        yf.writeFile(inst._config, json.dumps(conf))
        inst.sync_jail_local(conf)

        if status() == 'start':
            if not f2b_client_ok('reload')[0]:
                f2b_client_ok('restart')
        return yf.returnJson(True, '网站防护已托管至御风OP防火墙', {'changed': changed})
    except Exception as e:
        return yf.returnJson(False, str(e))


def runInfo():
    # 获取 Jail 状态与封禁详情
    jails = []
    banned_count = 0
    banned_ips = {}

    # status() 只探测一次（原实现重复调用 3 次，每次都要 spawn 进程）
    current_status = status()

    if current_status == 'start':
        ret = yf.execShell('fail2ban-client status')
        if ret[0] != '':
            match = re.search(r'Jail list:\s+(.*)', ret[0])
            if match:
                jails = [j.strip() for j in match.group(1).split(',') if j.strip()]

        # 遍历各个 Jail 获取具体被封禁的 IP 和统计数量
        for jail in jails:
            jail_status = f2b_client('status', jail)
            if jail_status[0] != '':
                # 解析当前封禁数量 (Currently banned)
                count_match = re.search(r'Currently banned:\s+(\d+)', jail_status[0])
                if count_match:
                    banned_count += int(count_match.group(1))

                # 解析封禁 IP 列表 (Banned IP list)
                ip_match = re.search(r'Banned IP list:\s+(.*)', jail_status[0])
                if ip_match:
                    ips = [ip.strip() for ip in ip_match.group(1).split() if ip.strip()]
                    if ips:
                        banned_ips[jail] = ips

    # 读取日志的最后 20 行（尾读，避免全量 readlines）
    log_lines = read_tail_lines(runLog(), max_lines=20)

    res = {
        'status': current_status,
        'jails': jails,
        'banned_count': banned_count,
        'banned_ips': banned_ips,
        'log': ''.join(log_lines)
    }
    return yf.returnJson(True, 'ok', res)



class fail2ban_main:
    def __init__(self):
        self._set_up_path = getServerDir()
        self._config = self._set_up_path + "/config.json"
        self._status = self._set_up_path + "/status.json"
        self._black_list = self._set_up_path + "/black_list.json"
        self._jail_local_file = f2bEtcDir() + "/jail.local"
        self._tmp_log_file = self._set_up_path + "/tmp_log.json"

    def parse_inner_args(self, args):
        if 'args' in args and isinstance(args['args'], str):
            try:
                import json
                raw_args = args['args'].replace('\\"', '"')
                inner_args = json.loads(raw_args)
                args.update(inner_args)
            except Exception as e:
                args['args_parse_error'] = str(e)
                args['args_raw'] = args['args']
        return args

    def get_ssh_port(self):
        try:
            conf = yf.readFile('/etc/ssh/sshd_config')
            if conf:
                import re
                m = re.search(r"^\s*Port\s+([0-9]+)", conf, re.MULTILINE)
                if m:
                    return m.group(1)
        except Exception:
            pass
        return '22'

    def get_mysql_port(self):
        try:
            mysql_cnf = yf.getServerDir() + '/mysql/etc/my.cnf'
            paths = [mysql_cnf, '/etc/my.cnf']
            for path in paths:
                if os.path.exists(path):
                    conf = yf.readFile(path)
                    if conf:
                        import re
                        m = re.search(r"^\s*port\s*=\s*([0-9]+)", conf, re.MULTILINE | re.IGNORECASE)
                        if m:
                            return m.group(1)
        except Exception:
            pass
        return '3306'

    def _site_default_act(self):
        """
        网站防护（global-cc / global-scan）的**默认**启用状态。

        检测到「御风OP防火墙」已安装时默认返回 'false'：
        Web 层（CC / 恶意扫描 / 注入 / 地区限制）由 op_waf 在应用层实时拦截，
        若本插件同时开启 global-cc / global-scan，同一攻击会被重复封禁 ——
        且 op_waf 侧的封禁存在 nginx 共享内存（reload 即失效），本插件却是
        iptables 全端口持久封禁，导致「在 op_waf 解封后仍访问不了」。

        注意：仅影响「初始化默认值」。已有配置一律不改写，
        绝不静默变更用户已保存的设置。
        """
        try:
            return 'false' if op_waf_installed() else 'true'
        except Exception:
            return 'true'

    def get_anti_info(self, args=None):
        default_sshd = {
            "mode": "sshd",
            "port": self.get_ssh_port(),
            "maxretry": "5",
            "findtime": "300",
            "bantime": "86400",
            "act": "true"
        }
        
        default_global_cc = {
            "mode": "global-cc",
            "port": "80,443",
            "maxretry": "60",
            "findtime": "60",
            "bantime": "86400",
            "act": self._site_default_act()
        }
        
        default_global_scan = {
            "mode": "global-scan",
            "port": "80,443",
            "maxretry": "30",
            "findtime": "60",
            "bantime": "86400",
            "act": self._site_default_act()
        }
        
        try:
            conf = yf.readFile(self._config)
            if not conf:
                conf_data = {"server": [default_sshd], "site": [default_global_cc, default_global_scan], "strict": True}
                yf.writeFile(self._config, json.dumps(conf_data))
                self.sync_jail_local(conf_data)
                return self._decorate_conf(conf_data)
                
            conf_data = json.loads(conf)
            if not isinstance(conf_data, dict):
                conf_data = {"server": [], "site": [default_global_cc, default_global_scan], "strict": True}
                
            # If server config is completely empty, initialize it with sshd defaults
            if 'server' not in conf_data or not isinstance(conf_data['server'], list) or len(conf_data['server']) == 0:
                conf_data['server'] = [default_sshd]
                yf.writeFile(self._config, json.dumps(conf_data))
                self.sync_jail_local(conf_data)
                
            if 'site' not in conf_data or not isinstance(conf_data['site'], list):
                conf_data['site'] = [default_global_cc, default_global_scan]
                yf.writeFile(self._config, json.dumps(conf_data))
                self.sync_jail_local(conf_data)
                
            if 'strict' not in conf_data:
                conf_data['strict'] = True
                yf.writeFile(self._config, json.dumps(conf_data))
                self.sync_jail_local(conf_data)
                
            return self._decorate_conf(conf_data)
        except Exception:
            # Re-initialize on corruption
            conf_data = {
                "server": [default_sshd], 
                "site": [default_global_cc, default_global_scan], 
                "strict": True, 
                "default_ssh_port": self.get_ssh_port(), 
                "default_mysql_port": self.get_mysql_port()
            }
            yf.writeFile(self._config, json.dumps({"server": [default_sshd], "site": [default_global_cc, default_global_scan], "strict": True}))
            self.sync_jail_local(conf_data)
            return self._decorate_conf(conf_data)

    def _op_waf_link_conf(self, conf):
        """
        [op-waf] 联动 jail 的可调参数。
        封禁时长由本插件持有（fail2ban 拥有自己的封禁策略），
        与 op_waf 侧完全解耦 —— 本插件从不读取 op_waf 的配置。
        """
        raw = conf.get('op_waf_link') if isinstance(conf, dict) else None
        if not isinstance(raw, dict):
            raw = {}
        return {'bantime': safe_int(raw.get('bantime'), 86400, 'bantime')}

    def _decorate_conf(self, conf_data):
        """
        给返回给前端的配置补充「运行时只读信息」（不写盘）：
          - default_ssh_port / default_mysql_port：表单占位用
          - op_waf：御风OP防火墙联动状态（未安装时 installed=False，零异常）
        """
        try:
            conf_data['default_ssh_port'] = self.get_ssh_port()
            conf_data['default_mysql_port'] = self.get_mysql_port()
        except Exception:
            pass
        try:
            conf_data['op_waf'] = op_waf_link_state()
            conf_data['op_waf_link'] = self._op_waf_link_conf(conf_data)
        except Exception:
            conf_data['op_waf'] = {'installed': False, 'linked': False}
        return conf_data

    def get_all_sitename(self, args=None):
        try:
            _list = yf.M('sites').field('id,name,path').order('id desc').select()
            data = {}
            if type(_list) == str or not _list:
                return data
            for i in range(len(_list)):
                data[_list[i]['name']] = _list[i]
            return data
        except Exception:
            return {}

    def sync_jail_local(self, conf):
        checkEnv()
        if not isinstance(conf, dict):
            conf = {}
        strict = safe_bool(conf.get('strict'), True)

        # [DEFAULT] 段只放全局无害项。
        # backend 必须逐 jail 声明：若写在 DEFAULT，systemd 后端会忽略
        # mysql/redis 的 logpath，导致这两个 jail 静默失效。
        content = "[DEFAULT]\n"
        content += "allowipv6 = auto\n\n"

        # ---- 系统服务防护 ----
        for item in conf.get('server', []):
            if not isinstance(item, dict):
                continue
            mode = item.get('mode', '')
            if not is_allowed_mode(mode) or not safe_bool(item.get('act'), True):
                continue

            # 必须先补齐占位日志与兜底 filter，再解析 backend/logpath：
            # 否则「日志目录存在但尚无 .err 文件」的服务会因 glob 未命中而被整段跳过
            ensure_service_log(mode)
            ensure_filter(mode)

            backend, logpath = resolve_backend(mode)

            # 无日志且无法降级 systemd 时跳过该 jail：
            # 宁可少一个 jail，也不能让一个没有 logpath 的 jail 拖垮整个 fail2ban
            if not logpath and backend != 'systemd':
                continue

            content += f"[{mode}]\n"
            content += "enabled = true\n"
            content += f"port = {safe_port(item.get('port'), '')}\n"
            content += f"backend = {backend}\n"
            if logpath:
                content += f"logpath = {logpath}\n"
            if strict:
                content += "banaction = %(banaction_allports)s\n"
            content += f"maxretry = {safe_int(item.get('maxretry'), 5, 'maxretry')}\n"
            content += f"findtime = {safe_int(item.get('findtime'), 300, 'findtime')}\n"
            content += f"bantime = {safe_int(item.get('bantime'), 86400, 'bantime')}\n\n"

        # ---- 网站防护 ----
        for item in conf.get('site', []):
            if not isinstance(item, dict):
                continue
            mode = item.get('mode', '')
            if not is_allowed_mode(mode) or not safe_bool(item.get('act'), True):
                continue

            content += f"[{mode}]\n"
            content += "enabled = true\n"
            content += "backend = auto\n"
            content += f"port = {safe_port(item.get('port'), '80,443')}\n"
            content += f"filter = {mode}\n"
            content += "logpath = /www/wwwlogs/*.log\n"
            if strict:
                content += "banaction = %(banaction_allports)s\n"
            content += f"maxretry = {safe_int(item.get('maxretry'), 60, 'maxretry')}\n"
            content += f"findtime = {safe_int(item.get('findtime'), 60, 'findtime')}\n"
            content += f"bantime = {safe_int(item.get('bantime'), 86400, 'bantime')}\n\n"

            ensure_filter(mode)

        # ---- 手动黑名单专用永久封禁 jail ----
        # 仅在黑名单非空时下发，避免给不使用该功能的用户增加无谓 jail。
        # filter 永不匹配，只通过 fail2ban-client set yf-manual banip 下发，
        # bantime = -1 实现真正的永久封禁（不再是 UI 层的假象）。
        if getBlackListArr():
            content += f"[{MANUAL_JAIL}]\n"
            content += "enabled = true\n"
            content += f"filter = {MANUAL_JAIL}\n"
            content += "backend = auto\n"
            content += f"logpath = {MANUAL_LOG}\n"
            content += "port = 0:65535\n"
            content += "banaction = %(banaction_allports)s\n"
            content += "maxretry = 1\n"
            content += "findtime = 60\n"
            content += "bantime = -1\n\n"

        # ---- 御风OP防火墙（op_waf）情报联动 jail ----
        # 仅当 op_waf 已开启联动（即 spool 文件就绪）时才下发。
        # op_waf 未安装 / 未开启联动 → spool 不存在 → 完全不下发，零残留，
        # 本插件行为与未引入联动前 100% 一致。
        #
        # backend = polling + pollinterval = 2：情报文件写入频率极低（仅封禁事件），
        # 轮询只做 stat，开销可忽略；2 秒延迟对「持久封禁」这一目标完全够用，
        # 且不依赖 pyinotify，任何环境下都能工作。
        if op_waf_link_enabled():
            link_conf = self._op_waf_link_conf(conf)
            ensure_op_waf_filter()
            content += f"[{OP_WAF_JAIL}]\n"
            content += "enabled = true\n"
            content += f"filter = {OP_WAF_JAIL}\n"
            content += "backend = polling\n"
            content += "pollinterval = 2\n"
            content += f"logpath = {op_waf_spool_path()}\n"
            content += "port = 0:65535\n"
            # 联动封禁一律全端口：op_waf 已在应用层实时拦下请求，
            # 内核层要做的是「持久阻断」，避免攻击者换协议绕过。
            content += "banaction = %(banaction_allports)s\n"
            content += "maxretry = 1\n"
            content += "findtime = 60\n"
            content += f"bantime = {link_conf['bantime']}\n\n"
        else:
            # 联动未生效时清掉历史遗留的过滤器，避免手工误用
            remove_op_waf_filter()

        yf.writeFile(self._jail_local_file, content)

    def _strip_runtime(self, conf):
        """
        回写 config.json 前剔除「运行时只读字段」。

        get_anti_info() 会附加 op_waf / default_ssh_port / default_mysql_port
        供前端渲染使用；这些字段不属于持久化配置，若跟着 set_anti / del_anti /
        set_strict_mode 一起落盘会污染配置文件（历史遗留问题，一并清理）。
        """
        if not isinstance(conf, dict):
            return conf
        for key in ('op_waf', 'default_ssh_port', 'default_mysql_port'):
            conf.pop(key, None)
        return conf

    def set_anti(self, args):
        args = self.parse_inner_args(args)
        mode = args.get('mode', '')

        # jail / mode 白名单强校验：杜绝任意字符串注入 jail.local 与 shell
        if not is_allowed_mode(mode):
            return yf.returnJson(False, '不支持的防护类型: ' + str(mode))

        conf = self.get_anti_info()
        is_site = mode.endswith('-cc') or mode.endswith('-scan')

        target_list = conf.get('site', []) if is_site else conf.get('server', [])

        # 全部数值与端口经严格校验后再写入，防止配置注入与非法值
        new_item = {
            'port': safe_port(args.get('port'), '80,443' if is_site else ''),
            'maxretry': safe_int(args.get('maxretry'), 60 if is_site else 5, 'maxretry'),
            'findtime': safe_int(args.get('findtime'), 60 if is_site else 300, 'findtime'),
            'bantime': safe_int(args.get('bantime'), 86400, 'bantime'),
            'act': 'true' if safe_bool(args.get('act'), True) else 'false',
        }

        found = False
        for i in range(len(target_list)):
            if target_list[i].get('mode') == mode:
                target_list[i].update(new_item)
                found = True
                break

        if not found:
            item = {'mode': mode}
            item.update(new_item)
            target_list.append(item)

        if is_site:
            conf['site'] = target_list
        else:
            conf['server'] = target_list

        self._strip_runtime(conf)
        yf.writeFile(self._config, json.dumps(conf))
        self.sync_jail_local(conf)

        # Reload fail2ban via existing method or systemctl
        if status() == 'start':
            if not f2b_client_ok('reload')[0]:
                f2b_client_ok('restart')
        return yf.returnJson(True, '设置成功!')

    def del_anti(self, args):
        args = self.parse_inner_args(args)
        mode = args.get('mode', '')

        if not is_allowed_mode(mode):
            return yf.returnJson(False, '不支持的防护类型: ' + str(mode))

        conf = self.get_anti_info()

        is_site = mode.endswith('-cc') or mode.endswith('-scan')

        target_list = conf.get('site', []) if is_site else conf.get('server', [])
        new_list = [item for item in target_list if item.get('mode') != mode]

        if is_site:
            conf['site'] = new_list
        else:
            conf['server'] = new_list

        self._strip_runtime(conf)
        yf.writeFile(self._config, json.dumps(conf))
        self.sync_jail_local(conf)

        if status() == 'start':
            if not f2b_client_ok('reload')[0]:
                f2b_client_ok('restart')
        return yf.returnJson(True, '删除成功!')

    def set_strict_mode(self, args):
        args = self.parse_inner_args(args)
        strict = safe_bool(args.get('strict'), True)

        conf = self.get_anti_info()
        conf['strict'] = strict
        self._strip_runtime(conf)
        yf.writeFile(self._config, json.dumps(conf))
        self.sync_jail_local(conf)

        if status() == 'start':
            if not f2b_client_ok('reload')[0]:
                f2b_client_ok('restart')
        return yf.returnJson(True, '设置成功!')

    def get_status(self, args):
        return yf.returnJson(True, 'ok')

    def ban_ip_release(self, args):
        return yf.returnJson(True, 'ok')

    def get_mode_list(self, args):
        return yf.returnJson(True, 'ok', [])

    def ban_ip(self, args):
        return yf.returnJson(True, 'ok')

    def unban_ip(self, args):
        return yf.returnJson(True, 'ok')

    def get_last_log(self, args):
        content = ""
        # 尾读最后 200 行，避免依赖 shell tail
        lines = read_tail_lines(runLog(), max_lines=200)
        if lines:
            content = ''.join(lines).strip()

        # 若主日志为空或服务处于停止状态，智能聚合 Systemd 诊断日志
        if not content or status() == 'stop':
            journal_data = yf.execShell('journalctl -u fail2ban -n 100 --no-pager')
            if journal_data[0] and journal_data[0].strip():
                prefix = "=== 提示: 当前显示 Systemd 诊断日志 (Journalctl) ===\n\n"
                if content:
                    content = content + "\n\n" + prefix + journal_data[0].strip()
                else:
                    content = prefix + journal_data[0].strip()

        return yf.returnJson(True, 'ok', content)

    def clear_log(self, args):
        log_file = runLog()
        # 直接写文件，避免 echo 走 shell
        try:
            yf.writeFile(log_file, '')
        except Exception:
            return yf.returnJson(False, '清空日志失败')
        return yf.returnJson(True, '清空日志成功!')

    def _fetch_ip_location(self, ips, lang):
        """调用 ip-api 批量接口获取归属地（每批最多 100 个 IP）"""
        import urllib.request
        out = []
        chunk_size = 100
        for i in range(0, len(ips), chunk_size):
            chunk = ips[i:i + chunk_size]
            body = json.dumps(chunk).encode('utf-8')
            ok = False
            for attempt in range(IP_API_RETRIES):
                try:
                    url = IP_API_BASE + '/batch?lang=' + lang + '&fields=' + IP_API_FIELDS
                    req = urllib.request.Request(url)
                    req.add_header('Content-Type', 'application/json')
                    resp = urllib.request.urlopen(req, data=body, timeout=IP_API_TIMEOUT)
                    data = json.loads(resp.read().decode('utf-8'))
                    if isinstance(data, list):
                        out.extend(data)
                        ok = True
                        break
                except Exception:
                    if attempt < IP_API_RETRIES - 1:
                        time.sleep(0.4)
            if not ok:
                out.extend([{"query": ip, "status": "fail"} for ip in chunk])
        return out

    def getIpLocationBatch(self, args):
        args = self.parse_inner_args(args)
        ips_json = args.get('ips', '[]')
        lang = normalize_ip_api_lang(args.get('lang', ''))

        try:
            ips = json.loads(ips_json) if isinstance(ips_json, str) else ips_json
            if not isinstance(ips, list):
                return yf.returnJson(False, 'ips must be a JSON array', [])
        except Exception as e:
            return yf.returnJson(False, str(e), [])

        ips = [x for x in (safe_ip(one) for one in ips) if x]
        if not ips:
            return yf.returnJson(True, 'ok!', [])

        if not ip_location_enabled():
            return yf.returnJson(True, 'ok!', [{"query": ip, "status": "fail"} for ip in ips])

        now = int(time.time())
        cache = load_ip_loc_cache()
        result = []
        pending = []
        for ip in ips:
            hit = cache.get(ip)
            if hit and now - hit.get('ts', 0) < IP_LOC_CACHE_TTL:
                result.append(hit.get('data', {}))
            else:
                pending.append(ip)

        if pending:
            fetched = self._fetch_ip_location(pending, lang)
            for item in fetched:
                q = item.get('query') if isinstance(item, dict) else None
                if q:
                    cache[q] = {'ts': now, 'data': item}
                result.append(item)
            save_ip_loc_cache(cache)

        return yf.returnJson(True, 'ok!', result)

    def getIpLocation(self, args):
        args = self.parse_inner_args(args)
        ip = safe_ip(args.get('ip', ''))
        lang = normalize_ip_api_lang(args.get('lang', ''))

        if not ip:
            return yf.returnJson(False, 'IP格式错误', [])

        if not ip_location_enabled():
            return yf.returnJson(False, '归属地查询已关闭', [])

        now = int(time.time())
        cache = load_ip_loc_cache()
        hit = cache.get(ip)
        if hit and now - hit.get('ts', 0) < IP_LOC_CACHE_TTL:
            return yf.returnJson(True, 'ok!', hit.get('data', {}))

        fetched = self._fetch_ip_location([ip], lang)
        if fetched and isinstance(fetched[0], dict) and fetched[0].get('status') == 'success':
            cache[ip] = {'ts': now, 'data': fetched[0]}
            save_ip_loc_cache(cache)
            return yf.returnJson(True, 'ok!', fetched[0])

        return yf.returnJson(False, '获取归属地失败', [])

    def get_logs_list(self, args):
        args = self.parse_inner_args(args)
        page = safe_int(args.get('page', 1), 1)
        page_size = safe_int(args.get('page_size', 10), 10)
        query_date = args.get('query_date', 'today')
        tojs = args.get('tojs', '')

        if page <= 0:
            page = 1
        if page_size <= 0:
            page_size = 10
        # 服务端硬上限：防止导出 10 万条把内存与响应体打爆
        if page_size > MAX_PAGE_SIZE:
            page_size = MAX_PAGE_SIZE

        logs = []
        # 尾读主日志与轮转日志（新 → 旧），避免全量 readlines()
        for path in log_candidates():
            if not os.path.exists(path):
                continue
            for line in read_tail_lines(path, max_lines=LOG_TAIL_LINES, keywords=(' Ban ',)):
                parsed = parse_ban_line(line)
                if parsed:
                    logs.append(parsed)

        logs.reverse()

        now = int(time.time())
        today_start = int(time.mktime(time.strptime(
            time.strftime("%Y-%m-%d 00:00:00", time.localtime()), "%Y-%m-%d %H:%M:%S")))

        if query_date == 'today':
            start_time = today_start
            end_time = now + 86400
        elif query_date == 'yesterday':
            start_time = today_start - 86400
            end_time = today_start
        elif query_date == 'l7':
            start_time = today_start - 86400 * 6
            end_time = now + 86400
        elif query_date == 'l30':
            start_time = today_start - 86400 * 29
            end_time = now + 86400
        elif '-' in str(query_date):
            try:
                start_time, end_time = [int(x) for x in str(query_date).split('-')]
            except Exception:
                start_time = 0
                end_time = now + 86400
        else:
            start_time = 0
            end_time = now + 86400

        filtered_logs = [log for log in logs if start_time <= log['time'] <= end_time]

        total_count = len(filtered_logs)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paged_logs = filtered_logs[start_idx:end_idx]

        _page = {}
        _page['count'] = total_count
        _page['p'] = page
        _page['row'] = page_size
        _page['tojs'] = tojs

        data = {
            "page": yf.getPage(_page),
            "data": paged_logs
        }

        return yf.returnJson(True, 'ok!', data)

    def get_ip_logs(self, args):
        args = self.parse_inner_args(args)
        raw_ip = args.get('ip', '')

        if not raw_ip and isinstance(args.get('args'), dict):
            raw_ip = args['args'].get('ip', '')

        ip = safe_ip(raw_ip)
        if not ip:
            # 不再回显整个 args，避免内部结构泄露
            return yf.returnJson(False, 'IP不能为空')

        # 使用词边界匹配，避免 1.1.1.1 命中 1.1.1.10
        ip_re = re.compile(r'(?<![\d.])' + re.escape(ip) + r'(?![\d.])')

        logs = []
        ban_count = 0
        for path in log_candidates():
            if not os.path.exists(path):
                continue
            for line in read_tail_lines(path, max_lines=LOG_TAIL_LINES, matcher=ip_re):
                logs.append(line.strip())
                if ' Ban ' in line:
                    ban_count += 1

        logs.reverse()
        data = {
            "ban_count": ban_count,
            "logs": logs
        }
        return yf.returnJson(True, 'ok!', data)

    def get_home_stats(self, args):
        now = int(time.time())
        today_start = int(time.mktime(time.strptime(
            time.strftime("%Y-%m-%d 00:00:00", time.localtime()), "%Y-%m-%d %H:%M:%S")))

        total_bans = 0
        today_bans = 0
        jail_stats = {}

        conn = open_bans_db()
        if conn is not None:
            try:
                c = conn.cursor()
                c.execute("SELECT count(*) FROM bans")
                row = c.fetchone()
                if row:
                    total_bans = row[0]

                c.execute("SELECT count(*) FROM bans WHERE timeofban >= ?", (today_start,))
                row = c.fetchone()
                if row:
                    today_bans = row[0]

                c.execute("SELECT jail, count(*) FROM bans GROUP BY jail")
                for r in c.fetchall():
                    jail_stats[r[0]] = r[1]
            except Exception:
                pass
            finally:
                conn.close()

        # 安全防护天数：取插件记录的首次防护时间（幂等持久化）。
        # 不再使用 bans 表最小 timeofban —— 该值受 dbpurgeage 限制，
        # 最多只能反映最近 N 天，导致"防护天数"长期显示 0~1 天。
        protect_days = get_protect_days()

        data = {
            "total_bans": total_bans,
            "today_bans": today_bans,
            "protect_days": protect_days,
            "jail_stats": jail_stats
        }
        return yf.returnJson(True, 'ok!', data)

    def get_total_statistics(self, args):
        if not os.path.exists('/www/server/fail2ban'):
            return yf.returnJson(False, "not installed")

        home_res = self.get_home_stats(args)
        try:
            home_data = json.loads(home_res)
            if home_data.get('status') and home_data.get('data'):
                today_bans = home_data['data'].get('today_bans', 0)
                total_bans = home_data['data'].get('total_bans', 0)
                count_str = str(today_bans) + '/' + str(total_bans)

                version = "1.0"
                try:
                    ver_content = yf.readFile(getPluginDir() + '/info.json')
                    if ver_content:
                        vdata = json.loads(ver_content)
                        # info.json 的 versions 是数组，必须取标量，
                        # 否则 ["1.2.0"] 会拼进首页 onclick 破坏 HTML 属性
                        raw_ver = vdata.get('versions', '1.0')
                        if isinstance(raw_ver, list):
                            version = str(raw_ver[-1]) if raw_ver else '1.0'
                        else:
                            version = str(raw_ver)
                except Exception:
                    pass

                res = {
                    "count": count_str,
                    "ver": version
                }
                return yf.returnJson(True, "ok", res)
        except Exception:
            pass

        return yf.returnJson(False, "error")


fail2ban_inst = None
def get_fail2ban_inst():
    global fail2ban_inst
    if fail2ban_inst is None:
        fail2ban_inst = fail2ban_main()
    return fail2ban_inst

if __name__ == "__main__":
    func = sys.argv[1]
    
    # Class methods wrapper
    if func == 'set_anti':
        args = getArgs()
        print(get_fail2ban_inst().set_anti(args))
    elif func == 'del_anti':
        args = getArgs()
        print(get_fail2ban_inst().del_anti(args))
    elif func == 'set_strict_mode':
        args = getArgs()
        print(get_fail2ban_inst().set_strict_mode(args))
    elif func == 'get_anti_info':
        args = getArgs()
        print(yf.returnJson(True, 'ok', get_fail2ban_inst().get_anti_info(args)))
    elif func == 'get_status':
        args = getArgs()
        print(get_fail2ban_inst().get_status(args))
    elif func == 'ban_ip_release':
        args = getArgs()
        print(get_fail2ban_inst().ban_ip_release(args))
    elif func == 'get_mode_list':
        args = getArgs()
        print(yf.returnJson(True, 'ok', get_fail2ban_inst().get_mode_list(args)))
    elif func == 'get_all_sitename':
        args = getArgs()
        print(yf.returnJson(True, 'ok', get_fail2ban_inst().get_all_sitename(args)))
    elif func == 'ban_ip':
        args = getArgs()
        print(get_fail2ban_inst().ban_ip(args))
    elif func == 'unban_ip':
        args = getArgs()
        print(get_fail2ban_inst().unban_ip(args))
    elif func == 'get_last_log':
        args = getArgs()
        print(get_fail2ban_inst().get_last_log(args))
    elif func == 'clear_log':
        args = getArgs()
        print(get_fail2ban_inst().clear_log(args))
    elif func == 'getIpLocationBatch':
        args = getArgs()
        print(get_fail2ban_inst().getIpLocationBatch(args))
    elif func == 'getIpLocation':
        args = getArgs()
        print(get_fail2ban_inst().getIpLocation(args))
    elif func == 'get_logs_list':
        args = getArgs()
        print(get_fail2ban_inst().get_logs_list(args))
    elif func == 'get_ip_logs':
        args = getArgs()
        print(get_fail2ban_inst().get_ip_logs(args))
    elif func == 'status':
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
    elif func == 'run_info':
        print(runInfo())
    elif func == 'conf':
        print(getConf())
    elif func == 'run_log':
        print(runLog())
    elif func == 'config_tpl':
        print(configTpl())
    elif func == 'read_config_tpl':
        print(readConfigTpl())
    elif func == 'get_black_list':
        print(getBlackList())
    elif func == 'set_black_ip':
        print(setBlackIp())
    elif func == 'get_active_bans':
        print(get_active_bans())
    elif func == 'unban_active_ip':
        print(unban_active_ip())
    elif func == 'get_home_stats':
        args = getArgs()
        print(get_fail2ban_inst().get_home_stats(args))
    elif func == 'get_total_statistics':
        args = getArgs()
        print(get_fail2ban_inst().get_total_statistics(args))
    # ---- 御风OP防火墙（op_waf）情报联动 ----
    elif func == 'sync_op_waf_jail':
        print(sync_op_waf_jail())
    elif func == 'op_waf_link_status':
        print(op_waf_link_status())
    elif func == 'set_op_waf_link':
        print(set_op_waf_link())
    elif func == 'set_op_waf_link_open':
        print(set_op_waf_link_open())
    elif func == 'unban_op_waf_ip':
        print(unban_op_waf_ip())
    elif func == 'disable_site_anti':
        print(disable_site_anti())
    else:
        print('error')
