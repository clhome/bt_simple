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


def getConf():
    path = f2bEtcDir() + "/fail2ban.conf"
    return path


def getConfTpl():
    path = getPluginDir() + "/tpl/fail2ban.conf"
    return path


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


def getArgs():
    args = sys.argv[3:]
    tmp = {}
    args_len = len(args)
    if args_len == 0:
        return tmp

    # 优先尝试将 args[0] 当作完整的 JSON 来解析
    if args_len == 1:
        try:
            val = args[0].strip()
            if val.startswith('{') and val.endswith('}'):
                try:
                    tmp = json.loads(val)
                    if isinstance(tmp, dict):
                        return tmp
                except Exception:
                    pass
        except Exception:
            pass

    # 传统的 key:value 参数提取
    for arg in args:
        try:
            if not arg:
                continue
            t = arg.strip().strip('{').strip('}')
            if not t:
                continue
            t_list = t.split(':')
            if len(t_list) >= 2:
                k = t_list[0].strip().strip('"').strip("'")
                v = ':'.join(t_list[1:]).strip().strip('"').strip("'")
                tmp[k] = v
        except (IndexError, TypeError, AttributeError):
            pass
    return tmp

def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, mw.returnJson(False, '参数:(' + ck[i] + ')没有!'))
    return (True, mw.returnJson(True, 'ok'))

def configTpl():
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
    pid_file = getPidFile()
    if not os.path.exists(pid_file):
        return 'stop'
    return 'start'

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

    # 更新本地缓存，保留 new_ip_list 里的合法 IP 覆盖 ip_list
    ip_list = [ip for ip in new_ip_list if re.search(rep_ip, ip) or re.search(rep_ipv6, ip)]

    mw.writeFile(getBlackFile(), json.dumps(ip_list))
    return mw.returnJson(True, "添加黑名单成功")

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
    _set_up_path = "/www/server/panel/plugin/fail2ban"
    _config = _set_up_path + "/config.json"
    _status = _set_up_path + "/status.json"
    _black_list = _set_up_path + "/black_list.json"
    _jail_local_file = "/etc/fail2ban/jail.local"
    _tmp_log_file = _set_up_path + "/tmp_log.json"


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
        print(get_fail2ban_inst().set_anti(mw.dict_obj(args)))
    elif func == 'del_anti':
        args = getArgs()
        print(get_fail2ban_inst().del_anti(mw.dict_obj(args)))
    elif func == 'get_anti_info':
        args = getArgs()
        print(mw.returnJson(True, 'ok', get_fail2ban_inst().get_anti_info(mw.dict_obj(args))))
    elif func == 'get_status':
        args = getArgs()
        print(get_fail2ban_inst().get_status(mw.dict_obj(args)))
    elif func == 'ban_ip_release':
        args = getArgs()
        print(get_fail2ban_inst().ban_ip_release(mw.dict_obj(args)))
    elif func == 'get_mode_list':
        args = getArgs()
        print(mw.returnJson(True, 'ok', get_fail2ban_inst().get_mode_list(mw.dict_obj(args))))
    elif func == 'get_all_sitename':
        args = getArgs()
        print(mw.returnJson(True, 'ok', get_fail2ban_inst().get_all_sitename(mw.dict_obj(args))))
    elif func == 'ban_ip':
        args = getArgs()
        print(get_fail2ban_inst().ban_ip(mw.dict_obj(args)))
    elif func == 'unban_ip':
        args = getArgs()
        print(get_fail2ban_inst().unban_ip(mw.dict_obj(args)))
    elif func == 'get_last_log':
        args = getArgs()
        print(mw.returnJson(True, 'ok', get_fail2ban_inst().get_last_log(mw.dict_obj(args))))
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
    else:
        print('error')
