import ipaddress
# coding:utf-8

import sys
import io
import os
import time
import re
import json

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.mw as mw

app_debug = False
if mw.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'fail2ban'

def f2bDir():
    return '/run/'+getPluginName()

def f2bEtcDir():
    return '/etc/'+getPluginName()

def getPluginDir():
    return mw.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return mw.getServerDir() + '/' + getPluginName()


def getInitDFile():
    current_os = mw.getOs()
    if current_os == 'darwin':
        return '/tmp/' + getPluginName()

    if current_os.startswith('freebsd'):
        return '/etc/rc.d/' + getPluginName()

    return '/etc/init.d/' + getPluginName()


def initConfigFiles():
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
dbpurgeage = 1d
"""
        mw.writeFile(f2b_conf, default_f2b_conf)

    # Check jail.conf (jail config template)
    jail_conf = etc_dir + '/jail.conf'
    if not os.path.exists(jail_conf):
        tpl_path = getConfTpl() # which is getPluginDir() + "/tpl/fail2ban.conf"
        if os.path.exists(tpl_path):
            content = mw.readFile(tpl_path)
            content = contentReplace(content)
            mw.writeFile(jail_conf, content)

def getConf():
    initConfigFiles()
    path = f2bEtcDir() + "/fail2ban.conf"
    return path


def getConfTpl():
    path = getPluginDir() + "/tpl/fail2ban.conf"
    return path


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
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
            return (False, mw.returnJson(False, '参数:(' + ck[i] + ')没有!'))
    return (True, mw.returnJson(True, 'ok'))

def configTpl():
    initConfigFiles()
    path = f2bEtcDir()
    pathFile = os.listdir(path)
    tmp = []
    for one in pathFile:
        if one.endswith("conf"):
            file = path + '/' + one
            tmp.append(file)
    return mw.getJson(tmp)


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
        return mw.returnJson(False, '只允许读取.conf配置文件')

    # 路径合法性沙箱校验，强行限制只能读取 /etc/fail2ban 目录下的配置文件
    target_dir = os.path.abspath(f2bEtcDir())
    path = os.path.abspath(os.path.join(target_dir, filename))
    
    # 双重安全防护线：绝对路径必须在目标目录内，且不能越权向上穿越
    if not path.startswith(target_dir + os.sep) and not path.startswith(target_dir + '/'):
        return mw.returnJson(False, '越权路径读取被拒绝')

    if not os.path.exists(path):
        return mw.returnJson(False, '配置文件不存在')

    content = mw.readFile(path)
    content = contentReplace(content)
    return mw.returnJson(True, 'ok', content)

def runLog():
    return '/var/log/fail2ban.log'

def getPidFile():
    f2dir = f2bDir()
    return f2dir+'/fail2ban.pid'

def status():
    data = mw.execShell('fail2ban-client ping')
    if 'pong' in data[0]:
        return 'start'
        
    # Fallback to systemctl check
    data = mw.execShell('systemctl is-active fail2ban')
    if data[0].strip() == 'active':
        return 'start'
        
    return 'stop'

def contentReplace(content):
    service_path = mw.getServerDir()
    content = content.replace('{$ROOT_PATH}', mw.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    return content


def initFail2BanD():
    dst_conf = f2bEtcDir() + '/fail2ban.d/default.conf'
    dst_conf_tpl = getPluginDir() + '/tpl/fail2ban.d/default.conf'
    if not os.path.exists(dst_conf):
        content = mw.readFile(dst_conf_tpl)
        content = contentReplace(content)
        mw.writeFile(dst_conf, content)

def initJailD():
    dst_conf = f2bEtcDir() + '/jail.d/default.conf'
    dst_conf_tpl = getPluginDir() + '/tpl/jail.d/default.conf'
    if not os.path.exists(dst_conf):
        content = mw.readFile(dst_conf_tpl)
        content = contentReplace(content)
        mw.writeFile(dst_conf, content)

def initDreplace():

    file_tpl = getInitDTpl()
    service_path = mw.getServerDir()

    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        os.mkdir(initD_path)
    file_bin = initD_path + '/' + getPluginName()

    # config replace
    # dst_conf = getConf()
    # dst_conf_init = getServerDir() + '/init.pl'
    # if not os.path.exists(dst_conf_init):
    #     content = mw.readFile(getConfTpl())
    #     content = contentReplace(content)
    #     mw.writeFile(dst_conf, content)
    #     mw.writeFile(dst_conf_init, 'ok')

    initConfigFiles()
    initFail2BanD()
    initJailD()

    # systemd
    systemDir = mw.systemdCfgDir()
    systemService = systemDir + '/' + getPluginName() + '.service'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        systemServiceTpl = getPluginDir() + '/init.d/' + getPluginName() + '.service.tpl'
        content = mw.readFile(systemServiceTpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        mw.writeFile(systemService, content)
        mw.execShell('systemctl daemon-reload')

    return file_bin


def f2bOp(method):
    file = initDreplace()

    # 服务启动、重启、重载前，自动触发配置健康检查与同步，静默补齐缺失配置
    if method in ['start', 'restart', 'reload']:
        try:
            inst = get_fail2ban_inst()
            inst.sync_jail_local(inst.get_anti_info())
        except Exception:
            pass

    current_os = mw.getOs()
    if current_os == "darwin":
        data = mw.execShell(file + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    if current_os.startswith("freebsd"):
        data = mw.execShell('service ' + getPluginName() + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    data = mw.execShell('systemctl ' + method + ' ' + getPluginName())
    if data[1] == '':
        return 'ok'
    return data[1]


def start():
    return f2bOp('start')


def stop():
    return f2bOp('stop')


def restart():
    status = f2bOp('restart')

    log_file = runLog()
    mw.execShell("echo '' > " + log_file)
    return status


def reload():
    return f2bOp('reload')


def initdStatus():
    current_os = mw.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile()
        if os.path.exists(initd_bin):
            return 'ok'

    shell_cmd = 'systemctl status ' + \
        getPluginName() + ' | grep loaded | grep "enabled;"'
    data = mw.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall():
    current_os = mw.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    # freebsd initd install
    if current_os.startswith('freebsd'):
        import shutil
        source_bin = initDreplace()
        initd_bin = getInitDFile()
        shutil.copyfile(source_bin, initd_bin)
        mw.execShell('chmod +x ' + initd_bin)
        mw.execShell('sysrc ' + getPluginName() + '_enable="YES"')
        return 'ok'

    mw.execShell('systemctl enable ' + getPluginName())
    return 'ok'


def initdUinstall():
    current_os = mw.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile()
        os.remove(initd_bin)
        mw.execShell('sysrc ' + getPluginName() + '_enable="NO"')
        return 'ok'

    mw.execShell('systemctl disable ' + getPluginName())
    return 'ok'


# 读取配置
def _read_conf(path, l=None):
    conf = mw.readFile(path)
    if not conf:
        if not l:
            conf = {}
        else:
            conf = []
        mw.writeFile(path, json.dumps(conf))
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
    return mw.returnJson(True, 'ok', content)

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

    # 将 new_ip_list 为空字符串的情形处理迁移为列表为空
    data = _read_conf(getConfigFile())

    if len(new_ip_list) == 0:
        for d in data:
            for ip in ip_list:
                mw.execShell('fail2ban-client -vvv set {jail} unbanip {ip}'.format(jail=d, ip=ip))
                _delete_db_ban(ip, d)

        mw.writeFile(getBlackFile(), json.dumps([]))
        return mw.returnJson(True, "禁止IP成功")

    add_ip_list = [new_ip for new_ip in new_ip_list if new_ip not in ip_list]
    del_ip_list = [del_ip for del_ip in ip_list if del_ip not in new_ip_list]
    rep_ip = "^(25[0-5]|2[0-4]\\d|[0-1]?\\d?\\d)(\\.(25[0-5]|2[0-4]\\d|[0-1]?\\d?\\d)){3}($|[\\/\\d]+$)"
    rep_ipv6 = "^\\s*((([0-9A-Fa-f]{1,4}:){7}(([0-9A-Fa-f]{1,4})|:))|(([0-9A-Fa-f]{1,4}:){6}(:|((25[0-5]|2[0-4]\\d|[01]?\\d{1,2})(\\.(25[0-5]|2[0-4]\\d|[01]?\\d{1,2})){3})|(:[0-9A-Fa-f]{1,4})))|(([0-9A-Fa-f]{1,4}:){5}((:((25[0-5]|2[0-4]\\d|[01]?\\d{1,2})(\\.(25[0-5]|2[0-4]\\d|[01]?\\d{1,2})){3})?)|((:[0-9A-Fa-f]{1,4}){1,2})))|(([0-9A-Fa-f]{1,4}:){4}(:[0-9A-Fa-f]{1,4}){0,1}((:((25[0-5]|2[0-4]\\d|[01]?\\d{1,2})(\\.(25[0-5]|2[0-4]\\d|[01]?\\d{1,2})){3})?)|((:[0-9A-Fa-f]{1,4}){1,2})))|(([0-9A-Fa-f]{1,4}:){3}(:[0-9A-Fa-f]{1,4}){0,2}((:((25[0-5]|2[0-4]\\d|[01]?\\d{1,2})(\\.(25[0-5]|2[0-4]\\d|[01]?\\d{1,2})){3})?)|((:[0-9A-Fa-f]{1,4}){1,2})))|(([0-9A-Fa-f]{1,4}:){2}(:[0-9A-Fa-f]{1,4}){0,3}((:((25[0-5]|2[0-4]\\d|[01]?\\d{1,2})(\\.(25[0-5]|2[0-4]\\d|[01]?\\d{1,2})){3})?)|((:[0-9A-Fa-f]{1,4}){1,2})))|(([0-9A-Fa-f]{1,4}:)(:[0-9A-Fa-f]{1,4}){0,4}((:((25[0-5]|2[0-4]\\d|[01]?\\d{1,2})(\\.(25[0-5]|2[0-4]\\d|[01]?\\d{1,2})){3})?)|((:[0-9A-Fa-f]{1,4}){1,2})))|(((25[0-5]|2[0-4]\\d|[01]?\\d{1,2})(\\.(25[0-5]|2[0-4]\\d|[01]?\\d{1,2})){3})))(%.+)?\\s*$"

    # 检查IP格式
    for ip in add_ip_list:
        if not re.search(rep_ip, ip) and not re.search(rep_ipv6, ip):
            return mw.returnJson(False, "IP格式错误 {}".format(ip))

    # 添加新IP到黑名单
    for d in data:
        for ip in add_ip_list:
            mw.execShell('fail2ban-client -vvv set {jail} banip {ip}'.format(jail=d, ip=ip))

    # 检查是否有清理掉的IP
    for d in data:
        for ip in del_ip_list:
            mw.execShell('fail2ban-client -vvv set {jail} unbanip {ip}'.format(jail=d, ip=ip))
            _delete_db_ban(ip, d)

    # 更新本地缓存，保留 new_ip_list 里的合法 IP 覆盖 ip_list
    ip_list = [ip for ip in new_ip_list if re.search(rep_ip, ip) or re.search(rep_ipv6, ip)]

    mw.writeFile(getBlackFile(), json.dumps(ip_list))
    return mw.returnJson(True, "添加黑名单成功")

def get_active_bans():
    import sqlite3
    import time
    db_path = '/var/lib/fail2ban/fail2ban.sqlite3'
    # 尝试从 client 获取 db 路径
    ret = mw.execShell('fail2ban-client get dbfile')
    if ret[0] and ret[0].strip() and ret[0].strip() != 'None':
        import re
        match = re.search(r'(/[^`\s]+\.sqlite3)', ret[0])
        if match:
            db_path = match.group(1)
        elif '- ' in ret[0]:
            db_path = ret[0].split('- ')[-1].strip()

    active_bans = []
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT jail, ip, timeofban, bantime FROM bans")
            rows = c.fetchall()
            now = int(time.time())
            
            # 手动添加的黑名单 IPs，用于在 UI 中优先标识
            black_list = getBlackListArr()

            for row in rows:
                jail, ip, timeofban, bantime = row
                expire_time = timeofban + bantime
                # 未过期的封禁或者是永久封禁
                if bantime < 0 or expire_time > now or ip in black_list:
                    # 如果是从 black_list 来的，强行设为永久封禁
                    if ip in black_list:
                        bantime = -1
                    
                    active_bans.append({
                        'jail': jail,
                        'ip': ip,
                        'timeofban': timeofban,
                        'bantime': bantime,
                        'expire_time': expire_time
                    })
            conn.close()
        except Exception as e:
            return mw.returnJson(False, '无法读取Fail2ban数据库: ' + str(e))
    else:
        return mw.returnJson(False, '未找到Fail2ban数据库: ' + db_path)

    # 排序，永久封禁排在最前，其次按剩余时间降序排序
    active_bans.sort(key=lambda x: (x['bantime'] >= 0, -x['expire_time']))
    return mw.returnJson(True, 'ok', active_bans)

def _delete_db_ban(ip, jail=None):
    db_path = '/var/lib/fail2ban/fail2ban.sqlite3'
    ret = mw.execShell('fail2ban-client get dbfile')
    if ret[0] and ret[0].strip() and ret[0].strip() != 'None':
        import re
        match = re.search(r'(/[^`\s]+\.sqlite3)', ret[0])
        if match:
            db_path = match.group(1)
        elif '- ' in ret[0]:
            db_path = ret[0].split('- ')[-1].strip()

    if os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            if jail:
                c.execute("DELETE FROM bans WHERE ip = ? AND jail = ?", (ip, jail))
            else:
                c.execute("DELETE FROM bans WHERE ip = ?", (ip,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            pass
    return False

def unban_active_ip():
    args = getArgs()
    ip = args.get('ip', '')
    jail = args.get('jail', '')
    
    if not ip:
        return mw.returnJson(False, 'IP不能为空')
        
    if jail:
        mw.execShell('fail2ban-client -vvv set {jail} unbanip {ip}'.format(jail=jail, ip=ip))
        _delete_db_ban(ip, jail)
    else:
        mw.execShell('fail2ban-client -vvv unban {ip}'.format(ip=ip))
        _delete_db_ban(ip)
        
    # 同时从 black_list 中移除
    ip_list = getBlackListArr()
    if ip in ip_list:
        ip_list.remove(ip)
        mw.writeFile(getBlackFile(), json.dumps(ip_list))
        
    return mw.returnJson(True, '解除封禁成功')

def runInfo():
    # 获取 Jail 状态与封禁详情
    jails = []
    banned_count = 0
    banned_ips = {}
    
    if status() == 'start':
        ret = mw.execShell('fail2ban-client status')
        if ret[0] != '':
            match = re.search(r'Jail list:\s+(.*)', ret[0])
            if match:
                jails = [j.strip() for j in match.group(1).split(',') if j.strip()]
                
        # 遍历各个 Jail 获取具体被封禁的 IP 和统计数量
        for jail in jails:
            jail_status = mw.execShell('fail2ban-client status {}'.format(jail))
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

    # 读取日志的最后20行
    log_file = runLog()
    log_lines = []
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                log_lines = lines[-20:]
        except Exception:
            pass

    res = {
        'status': status(),
        'jails': jails,
        'banned_count': banned_count,
        'banned_ips': banned_ips,
        'log': ''.join(log_lines)
    }
    return mw.returnJson(True, 'ok', res)



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
            conf = mw.readFile('/etc/ssh/sshd_config')
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
            mysql_cnf = mw.getServerDir() + '/mysql/etc/my.cnf'
            paths = [mysql_cnf, '/etc/my.cnf']
            for path in paths:
                if os.path.exists(path):
                    conf = mw.readFile(path)
                    if conf:
                        import re
                        m = re.search(r"^\s*port\s*=\s*([0-9]+)", conf, re.MULTILINE | re.IGNORECASE)
                        if m:
                            return m.group(1)
        except Exception:
            pass
        return '3306'

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
            "act": "true"
        }
        
        default_global_scan = {
            "mode": "global-scan",
            "port": "80,443",
            "maxretry": "30",
            "findtime": "60",
            "bantime": "86400",
            "act": "true"
        }
        
        try:
            conf = mw.readFile(self._config)
            if not conf:
                conf_data = {"server": [default_sshd], "site": [default_global_cc, default_global_scan], "strict": True}
                mw.writeFile(self._config, json.dumps(conf_data))
                self.sync_jail_local(conf_data)
                return conf_data
                
            conf_data = json.loads(conf)
            if not isinstance(conf_data, dict):
                conf_data = {"server": [], "site": [default_global_cc, default_global_scan], "strict": True}
                
            # If server config is completely empty, initialize it with sshd defaults
            if 'server' not in conf_data or not isinstance(conf_data['server'], list) or len(conf_data['server']) == 0:
                conf_data['server'] = [default_sshd]
                mw.writeFile(self._config, json.dumps(conf_data))
                self.sync_jail_local(conf_data)
                
            if 'site' not in conf_data or not isinstance(conf_data['site'], list):
                conf_data['site'] = [default_global_cc, default_global_scan]
                mw.writeFile(self._config, json.dumps(conf_data))
                self.sync_jail_local(conf_data)
                
            if 'strict' not in conf_data:
                conf_data['strict'] = True
                mw.writeFile(self._config, json.dumps(conf_data))
                self.sync_jail_local(conf_data)
                
            conf_data['default_ssh_port'] = self.get_ssh_port()
            conf_data['default_mysql_port'] = self.get_mysql_port()
            return conf_data
        except Exception:
            # Re-initialize on corruption
            conf_data = {
                "server": [default_sshd], 
                "site": [default_global_cc, default_global_scan], 
                "strict": True, 
                "default_ssh_port": self.get_ssh_port(), 
                "default_mysql_port": self.get_mysql_port()
            }
            mw.writeFile(self._config, json.dumps({"server": [default_sshd], "site": [default_global_cc, default_global_scan], "strict": True}))
            self.sync_jail_local(conf_data)
            return conf_data

    def get_all_sitename(self, args=None):
        try:
            _list = mw.M('sites').field('id,name,path').order('id desc').select()
            data = {}
            if type(_list) == str or not _list:
                return data
            for i in range(len(_list)):
                data[_list[i]['name']] = _list[i]
            return data
        except Exception:
            return {}

    def sync_jail_local(self, conf):
        content = ""
        strict = conf.get('strict', True)
        for item in conf.get('server', []):
            if str(item.get('act')).lower() == 'true':
                mode = item['mode']
                content += f"[{mode}]\n"
                content += "enabled = true\n"
                content += f"port = {item.get('port', '')}\n"
                if strict:
                    content += "banaction = %(banaction_allports)s\n"
                content += f"maxretry = {item.get('maxretry', 5)}\n"
                content += f"findtime = {item.get('findtime', 300)}\n"
                content += f"bantime = {item.get('bantime', 86400)}\n"
                
                # 为 mysql / redis 等自定义服务配置日志路径并确保 filter 配置文件存在
                if mode == 'mysql':
                    content += "logpath = /www/server/data/*.err\n"
                    filter_file = f"/etc/fail2ban/filter.d/{mode}.conf"
                    if not os.path.exists(filter_file):
                        filter_content = "[Definition]\nfailregex = ^.*Access denied for user.*'<HOST>'.*$\nignoreregex = "
                        mw.writeFile(filter_file, filter_content)
                elif mode == 'redis':
                    content += "logpath = /var/log/redis/*.log\n"
                    filter_file = f"/etc/fail2ban/filter.d/{mode}.conf"
                    if not os.path.exists(filter_file):
                        filter_content = "[Definition]\nfailregex = ^.*-ERR Auth failed.*from <HOST>.*$\nignoreregex = "
                        mw.writeFile(filter_file, filter_content)
                
                content += "\n"
                
        for item in conf.get('site', []):
            if str(item.get('act')).lower() == 'true':
                mode = item['mode']
                
                content += f"[{mode}]\n"
                content += "enabled = true\n"
                content += "backend = auto\n"
                content += f"port = {item.get('port', '80,443')}\n"
                content += f"filter = {mode}\n"
                content += "logpath = /www/wwwlogs/*.log\n"
                if strict:
                    content += "banaction = %(banaction_allports)s\n"
                content += f"maxretry = {item.get('maxretry', 5)}\n"
                content += f"findtime = {item.get('findtime', 300)}\n"
                content += f"bantime = {item.get('bantime', 86400)}\n\n"
                
                # Ensure the filter exists
                filter_file = f"/etc/fail2ban/filter.d/{mode}.conf"
                if not os.path.exists(filter_file):
                    if mode.endswith('-cc'):
                        filter_content = "[Definition]\nfailregex = ^<HOST> \\-.*\nignoreregex = "
                    else:
                        filter_content = "[Definition]\nfailregex = ^<HOST> \\-.*\"(?:GET|POST|HEAD).*\" (400|401|403|404|444|500|502|503)\nignoreregex = "
                    mw.writeFile(filter_file, filter_content)
                
        mw.writeFile(self._jail_local_file, content)

    def set_anti(self, args):
        args = self.parse_inner_args(args)
        conf = self.get_anti_info()
        mode = args.get('mode', '')
        is_site = False
        if mode.endswith('-cc') or mode.endswith('-scan'):
            is_site = True
        
        target_list = conf.get('site', []) if is_site else conf.get('server', [])
        
        found = False
        for i in range(len(target_list)):
            if target_list[i]['mode'] == mode:
                target_list[i]['port'] = args.get('port', target_list[i].get('port', ''))
                target_list[i]['maxretry'] = args.get('maxretry', target_list[i].get('maxretry', 5))
                target_list[i]['findtime'] = args.get('findtime', target_list[i].get('findtime', 300))
                target_list[i]['bantime'] = args.get('bantime', target_list[i].get('bantime', 86400))
                target_list[i]['act'] = args.get('act', target_list[i].get('act', 'true'))
                found = True
                break
                
        if not found:
            target_list.append({
                'mode': mode,
                'port': args.get('port', ''),
                'maxretry': args.get('maxretry', '5'),
                'findtime': args.get('findtime', '300'),
                'bantime': args.get('bantime', '86400'),
                'act': args.get('act', 'true')
            })
            
        if is_site:
            conf['site'] = target_list
        else:
            conf['server'] = target_list
            
        mw.writeFile(self._config, json.dumps(conf))
        self.sync_jail_local(conf)
        
        # Reload fail2ban via existing method or systemctl
        mw.execShell('systemctl reload fail2ban')
        return mw.returnJson(True, '设置成功!')

    def del_anti(self, args):
        args = self.parse_inner_args(args)
        mode = args.get('mode', '')
        conf = self.get_anti_info()
        
        is_site = False
        if mode.endswith('-cc') or mode.endswith('-scan'):
            is_site = True
            
        target_list = conf.get('site', []) if is_site else conf.get('server', [])
        new_list = [item for item in target_list if item['mode'] != mode]
        
        if is_site:
            conf['site'] = new_list
        else:
            conf['server'] = new_list
            
        mw.writeFile(self._config, json.dumps(conf))
        self.sync_jail_local(conf)
        
        mw.execShell('systemctl reload fail2ban')
        return mw.returnJson(True, '删除成功!')

    def set_strict_mode(self, args):
        args = self.parse_inner_args(args)
        strict_val = args.get('strict', 'true')
        if isinstance(strict_val, str):
            strict = strict_val.lower() == 'true'
        else:
            strict = bool(strict_val)
        conf = self.get_anti_info()
        conf['strict'] = strict
        mw.writeFile(self._config, json.dumps(conf))
        self.sync_jail_local(conf)
        
        mw.execShell('systemctl reload fail2ban')
        return mw.returnJson(True, '设置成功!')

    def get_status(self, args):
        return mw.returnJson(True, 'ok')

    def ban_ip_release(self, args):
        return mw.returnJson(True, 'ok')

    def get_mode_list(self, args):
        return mw.returnJson(True, 'ok', [])

    def ban_ip(self, args):
        return mw.returnJson(True, 'ok')

    def unban_ip(self, args):
        return mw.returnJson(True, 'ok')

    def get_last_log(self, args):
        log_file = runLog()
        if not os.path.exists(log_file):
            return mw.returnJson(True, 'ok', '')
        
        data = mw.execShell('tail -n 200 ' + log_file)
        return mw.returnJson(True, 'ok', data[0])

    def clear_log(self, args):
        log_file = runLog()
        mw.execShell('echo "" > ' + log_file)
        return mw.returnJson(True, '清空日志成功!')

    def getIpLocationBatch(self, args):
        args = self.parse_inner_args(args)
        ips_json = args.get('ips', '[]')
        try:
            import json
            import urllib.request
            ips = json.loads(ips_json)
            if not isinstance(ips, list):
                return mw.returnJson(False, 'ips must be a JSON array', [])
            
            import urllib.request
            import time
            
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    req = urllib.request.Request('http://ip-api.com/batch?lang=zh-CN')
                    req.add_header('Content-Type', 'application/json')
                    response = urllib.request.urlopen(req, data=ips_json.encode('utf-8'), timeout=10)
                    result = response.read().decode('utf-8')
                    return mw.returnJson(True, 'ok!', json.loads(result))
                except Exception as e:
                    if attempt == max_retries - 1:
                        # 所有重试均失败
                        result_list = [{"query": ip, "status": "fail"} for ip in ips]
                        return mw.returnJson(True, 'ok!', result_list)
                    time.sleep(0.5)
        except Exception as e:
            return mw.returnJson(False, str(e), [])

    def getIpLocation(self, args):
        args = self.parse_inner_args(args)
        ip = args.get('ip', '')
        try:
            import json
            import urllib.request
            import urllib.request
            import time
            
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    url = 'http://ip-api.com/json/' + ip + '?lang=zh-CN'
                    response = urllib.request.urlopen(url, timeout=10)
                    result = response.read().decode('utf-8')
                    return mw.returnJson(True, 'ok!', json.loads(result))
                except Exception as e:
                    if attempt == max_retries - 1:
                        return mw.returnJson(False, '获取归属地失败', [])
                    time.sleep(0.5)
        except Exception as e:
            return mw.returnJson(False, str(e), [])


    def get_logs_list(self, args):
        args = self.parse_inner_args(args)
        page = int(args.get('page', 1))
        page_size = int(args.get('page_size', 10))
        query_date = args.get('query_date', 'today')
        tojs = args.get('tojs', '')

        log_file = runLog()
        
        logs = []
        if os.path.exists(log_file):
            try:
                import time
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        if ' Ban ' in line:
                            parts = line.strip().split()
                            if len(parts) >= 4 and parts[-2] == 'Ban':
                                date_str = parts[0]
                                time_str = parts[1].split(',')[0]
                                ip_str = parts[-1]
                                
                                is_restore = False
                                if parts[-3] == 'Restore':
                                    jail_str = parts[-4].strip('[]')
                                    is_restore = True
                                else:
                                    jail_str = parts[-3].strip('[]')
                                
                                try:
                                    time_obj = time.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                                    unix_time = int(time.mktime(time_obj))
                                except:
                                    unix_time = int(time.time())
                                
                                reason = "触发防御规则，已被自动拦截"
                                if jail_str.endswith('-cc'):
                                    reason = "请求频率过高，触发CC防御拦截"
                                elif jail_str.endswith('-scan'):
                                    reason = "触发恶意扫描，已被自动拦截"
                                elif jail_str == 'sshd':
                                    reason = "SSH登录失败过多，防暴破拦截"
                                elif jail_str == 'ftpd':
                                    reason = "FTP登录失败过多，防暴破拦截"
                                elif jail_str == 'mysql':
                                    reason = "MySQL登录失败过多，防暴破拦截"
                                elif jail_str == 'panel.yftec.top-cc' or jail_str.endswith('-cc'):
                                    reason = "面板/网站请求频率过高，触发CC拦截"
                                    
                                if is_restore:
                                    reason = "服务重启，恢复历史封禁 (" + reason + ")"

                                logs.append({
                                    "time": unix_time,
                                    "domain": "ALL",
                                    "ip": ip_str,
                                    "uri": "-",
                                    "rule_name": jail_str,
                                    "reason": reason
                                })
            except Exception as e:
                pass

        logs.reverse()

        filtered_logs = []
        import time
        now = int(time.time())
        today_start = int(time.mktime(time.strptime(time.strftime("%Y-%m-%d 00:00:00", time.localtime()), "%Y-%m-%d %H:%M:%S")))
        
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
        elif '-' in query_date:
            try:
                start_time, end_time = [int(x) for x in query_date.split('-')]
            except:
                start_time = 0
                end_time = now + 86400
        else:
            start_time = 0
            end_time = now + 86400
            
        for log in logs:
            if start_time <= log['time'] <= end_time:
                filtered_logs.append(log)

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
            "page": mw.getPage(_page),
            "data": paged_logs
        }
        
        return mw.returnJson(True, 'ok!', data)

    def get_ip_logs(self, args):
        args = self.parse_inner_args(args)
        ip = args.get('ip', '')
        
        if not ip and 'args' in args:
            if isinstance(args['args'], dict):
                ip = args['args'].get('ip', '')
            elif isinstance(args['args'], str):
                import re
                m = re.search(r'"ip"\s*:\s*"([^"]+)"', args['args'].replace('\\', ''))
                if m:
                    ip = m.group(1)

        if not ip:
            return mw.returnJson(False, f'IP不能为空! args dump: {str(args)}')

        log_file = runLog()
        logs = []
        ban_count = 0
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        if ip in line:
                            logs.append(line.strip())
                            if ' Ban ' in line:
                                ban_count += 1
            except Exception as e:
                pass

        logs.reverse()
        data = {
            "ban_count": ban_count,
            "logs": logs
        }
        return mw.returnJson(True, 'ok!', data)

    def get_home_stats(self, args):
        import sqlite3
        import time
        db_path = '/var/lib/fail2ban/fail2ban.sqlite3'
        ret = mw.execShell('fail2ban-client get dbfile')
        if ret[0] and ret[0].strip() and ret[0].strip() != 'None':
            import re
            match = re.search(r'(/[^`\s]+\.sqlite3)', ret[0])
            if match:
                db_path = match.group(1)
            elif '- ' in ret[0]:
                db_path = ret[0].split('- ')[-1].strip()

        now = int(time.time())
        today_start = int(time.mktime(time.strptime(time.strftime("%Y-%m-%d 00:00:00", time.localtime()), "%Y-%m-%d %H:%M:%S")))
        
        total_bans = 0
        today_bans = 0
        jail_stats = {}
        protect_days = 0

        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                
                # Total bans
                c.execute("SELECT count(*) FROM bans")
                total_bans_row = c.fetchone()
                if total_bans_row:
                    total_bans = total_bans_row[0]
                    
                # Today bans
                c.execute("SELECT count(*) FROM bans WHERE timeofban >= ?", (today_start,))
                today_bans_row = c.fetchone()
                if today_bans_row:
                    today_bans = today_bans_row[0]
                    
                # Jail stats
                c.execute("SELECT jail, count(*) FROM bans GROUP BY jail")
                for row in c.fetchall():
                    jail_stats[row[0]] = row[1]
                    
                # Protect days
                c.execute("SELECT min(timeofban) FROM bans")
                oldest_ban = c.fetchone()
                if oldest_ban and oldest_ban[0]:
                    protect_days = int((now - oldest_ban[0]) / 86400)
                
                conn.close()
            except Exception as e:
                pass
                
        if protect_days <= 0:
            jail_local = f2bEtcDir() + "/jail.local"
            if os.path.exists(jail_local):
                protect_days = int((now - os.path.getctime(jail_local)) / 86400)
                if protect_days < 0:
                    protect_days = 0

        data = {
            "total_bans": total_bans,
            "today_bans": today_bans,
            "protect_days": protect_days,
            "jail_stats": jail_stats
        }
        return mw.returnJson(True, 'ok!', data)

    def get_total_statistics(self, args):
        home_res = self.get_home_stats(args)
        try:
            import json
            home_data = json.loads(home_res)
            if home_data.get('status') and home_data.get('data'):
                today_bans = home_data['data'].get('today_bans', 0)
                total_bans = home_data['data'].get('total_bans', 0)
                count_str = str(today_bans) + '/' + str(total_bans)
                ver_content = mw.readFile(getPluginDir() + '/info.json')
                version = "1.0"
                if ver_content:
                    try:
                        vdata = json.loads(ver_content)
                        version = vdata.get('versions', "1.0")
                    except:
                        pass
                res = {
                    "count": count_str,
                    "ver": version
                }
                return mw.returnJson(True, "ok", res)
        except:
            pass
            
        return mw.returnJson(False, "error")

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
        print(mw.returnJson(True, 'ok', get_fail2ban_inst().get_anti_info(args)))
    elif func == 'get_status':
        args = getArgs()
        print(get_fail2ban_inst().get_status(args))
    elif func == 'ban_ip_release':
        args = getArgs()
        print(get_fail2ban_inst().ban_ip_release(args))
    elif func == 'get_mode_list':
        args = getArgs()
        print(mw.returnJson(True, 'ok', get_fail2ban_inst().get_mode_list(args)))
    elif func == 'get_all_sitename':
        args = getArgs()
        print(mw.returnJson(True, 'ok', get_fail2ban_inst().get_all_sitename(args)))
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
    else:
        print('error')
