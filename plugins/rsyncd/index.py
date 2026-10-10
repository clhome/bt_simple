# coding: utf-8

import time
import random
import os
import json
import logging
import re
import sys

_log = logging.getLogger('yf.plugin.rsyncd')

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf


app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'rsyncd'


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


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
        # tmp['"name"'] = '""}'，于是**所有带参接口恒回「缺少必要参数」**
        # （真机实测 /plugins/run get_rec '{"name":""}' → 缺少必要参数: name）。
        if val.startswith('{') and val.endswith('}'):
            try:
                data = json.loads(val)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                _log.debug('[rsyncd] getArgs JSON 解析失败: %s', e)
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


def checkArgs(data, ck=[]):
    if not isinstance(data, dict):
        return (False, yf.returnJson(False, '缺少必要参数: ' + (ck[0] if ck else '')))
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


def checkNameSafe(name):
    if not isinstance(name, str) or not re.match(r'^[a-zA-Z0-9_\-]+$', name):
        return False
    return True


#: 控制字符（含 \r \n \0 与 DEL）：写进 rsyncd.conf / lsyncd.conf / shell 命令都会
#: 造成配置注入或语法错误，任何来自前端的字符串都必须先过这一关。
_CTRL_RE = re.compile(r'[\x00-\x1f\x7f]')


def hasCtrl(s):
    return isinstance(s, str) and bool(_CTRL_RE.search(s))


def escapeLuaString(s):
    """转义 Lua 字符串里的反斜杠/引号/控制字符。

    不转义时：值里一个 `"` 就能闭合字符串注入任意 Lua 语句（lsyncd 以 root 运行，
    `os.execute` 即 root RCE），一个真实换行会让生成的 lsyncd.conf 语法错误、
    lsyncd 起不来。与 C03 `op_waf/class/luamaker.py`、C06
    `webstats/class/LuaMaker.py::_escapeLuaString` 同族同口径。
    """
    out = []
    for ch in str(s):
        if ch == '\\':
            out.append('\\\\')
        elif ch == '"':
            out.append('\\"')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        elif ord(ch) < 0x20 or ord(ch) == 0x7f:
            out.append('\\%d' % ord(ch))
        else:
            out.append(ch)
    return ''.join(out)


def normBool(v):
    """把前端传来的 'true'/'false'（大小写不限）归一；其余一律 None（不合法）。"""
    s = str(v).strip().lower()
    if s in ('true', 'false'):
        return s
    return None


def normInt(v, lo, hi, default=None):
    """归一整数并做范围校验。

    空值返回 default；非整数或超范围返回 None（不合法）。旧前端在「新建发送任务」时
    会把未初始化的输入框值当字符串 'undefined' 发上来，这里一并当作空值处理。
    """
    if v is None or str(v).strip() in ('', 'undefined', 'null'):
        return default
    try:
        n = int(str(v).strip())
    except Exception:
        return None
    if n < lo or n > hi:
        return None
    return n


def isInstalled():
    """已安装判据 = install.sh 落下的 version.pl。

    不能用「目录存在」：yf.writeFile 会自动建父目录，未安装的机器也会被凭空造出
    /www/server/rsyncd 与整套 systemd/init.d 产物（真机实测 HEAD 版 `start`
    在未安装时造出 lsyncd.conf 与 init.d/lsyncd 后 exit(0) 报「成功」）。
    """
    return os.path.exists(getServerDir() + '/version.pl')


#: `systemctl is-enabled` 的「已启用」状态集合（单元类型/systemd 版本不同词不同）
_UNIT_ENABLED_STATES = ('enabled', 'enabled-runtime', 'alias', 'static', 'indirect', 'generated')


def unitEnabled(unit):
    """按 `systemctl is-enabled` 的退出码判定单元是否已启用。

    旧实现 `systemctl status <unit> | grep loaded | grep "enabled;"` 依赖人类可读输出：
    单元由 SysV 脚本生成时 status 显示 `Loaded: loaded (/etc/init.d/rsyncd; generated)`
    （没有 `enabled;`）→ 已启用的服务被误判 fail；locale/版本差异同理（与 C02 openresty 同族）。
    """
    rc, out, _err = yf.execShellRc(['systemctl', 'is-enabled', unit], shell=False, timeout=15)
    if rc != 0:
        return False
    return (out or '').strip() in _UNIT_ENABLED_STATES


def getPidFile():
    """从 rsyncd.conf 读 pid file；读不到就退回 rsync 默认路径。"""
    conf = yf.readFile(appConf())
    if isinstance(conf, str):
        m = re.search(r'(?mi)^\s*pid file\s*=\s*(\S+)', conf)
        if m:
            return m.group(1)
    return '/var/run/rsyncd.pid'


def rsyncDaemonPids():
    """真正的 rsync --daemon 进程号列表（直读 /proc：不 fork、不自我匹配）。"""
    pids = []
    try:
        names = os.listdir('/proc')
    except Exception:
        return pids
    for n in names:
        if not n.isdigit():
            continue
        try:
            with open('/proc/%s/comm' % n, 'r') as fp:
                if fp.read().strip() != 'rsync':
                    continue
            with open('/proc/%s/cmdline' % n, 'rb') as fp:
                cmdline = fp.read().decode('utf-8', 'replace').replace('\x00', ' ')
        except Exception:
            continue
        if '--daemon' in cmdline:
            pids.append(int(n))
    return pids


def pidAlive(pid):
    try:
        os.kill(pid, 0)
    except OSError as err:
        import errno
        return err.errno == errno.EPERM
    except Exception:
        return False
    return True


def readSecretPwd(secrets_file):
    """读 rsyncd secrets 文件里的口令。

    返回 (pwd, err)。yf.readFile 失败返回 **False**（不是空串），旧实现直接
    `.strip().split(':')` → AttributeError；没有 `:` 时 `pwd[1]` → IndexError。
    """
    content = yf.readFile(secrets_file)
    if not isinstance(content, str):
        return (None, '密码文件读取失败！')
    parts = content.strip().split(':')
    if len(parts) < 2 or parts[1] == '':
        return (None, '密码文件读取失败！')
    return (parts[1], None)


#: 接收模块路径禁入区：以 `read only = false` 把这些路径暴露成 rsync 共享，
#: 等于把面板源码 / 系统配置 / 生产库开放为可写共享。
def invalidRecvPath(path):
    try:
        real = os.path.realpath(path)
    except Exception:
        return True
    panel_dir = os.path.realpath(yf.getPanelDir())
    if real == panel_dir or real.startswith(panel_dir + os.sep):
        return True
    for p in ('/etc', '/usr', '/bin', '/sbin', '/lib', '/lib64', '/boot', '/dev',
              '/proc', '/sys', '/run', '/var/run', '/root'):
        if real == p or real.startswith(p + os.sep):
            return True
    return False


def sendListData():
    """取 config.json（含 send.list）；文件缺失/损坏时返回 None，不再抛 traceback。"""
    data = getDefaultConf()
    if not isinstance(data, dict):
        return None
    send = data.get('send')
    if not isinstance(send, dict) or not isinstance(send.get('list'), list):
        return None
    return data


def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$SERVER_PATH}', service_path)
    return content


def status():
    # 真判据 = 存在 rsync --daemon 进程，用 pid 文件 + /proc 精确核对。
    # 历史沿革（真机实测 2026-10-10）：`ps -ef|grep rsync |grep -v grep | grep -v python
    # | awk '{print $2}'` 在 **rsyncd 完全未安装** 的机器上恒回 'start' ——
    # execShell(shell=True) 自己那层 `sh -c "ps -ef|grep rsync …"` 的 cmdline 里含 'rsync'，
    # 管道匹配到了自身（HTTP /plugins/run status 实测回 start，而 pgrep -x rsync 为空）。
    pid_file = getPidFile()
    if pid_file:
        raw = yf.readFile(pid_file)
        if isinstance(raw, str) and raw.strip().isdigit():
            pid = int(raw.strip())
            try:
                with open('/proc/%d/comm' % pid, 'r') as fp:
                    comm = fp.read().strip()
            except Exception:
                comm = ''
            if comm == 'rsync' and pidAlive(pid):
                return 'start'
    if rsyncDaemonPids():
        return 'start'
    return 'stop'


def appConf():
    return getServerDir() + '/rsyncd.conf'


def appAuthPwd(name):
    nameDir = getServerDir() + '/receive/' + name
    if not os.path.exists(nameDir):
        yf.makeDirs(nameDir)
    return nameDir + '/auth.db'


def getLog():
    conf_path = appConf()
    conf = yf.readFile(conf_path)
    # readFile 失败返回 False：旧实现直接交给 re.search → TypeError traceback
    if not isinstance(conf, str):
        return ''
    rep = r'log file\s*=\s*(.*)'
    tmp = re.search(rep, conf)
    if not tmp:
        return ''
    return tmp.groups()[0]


def getLsyncdLog():
    path = getServerDir() + "/lsyncd.conf"
    conf = yf.readFile(path)
    if not isinstance(conf, str):
        return ''
    rep = r'logfile\s*=\s*\"(.*)\"'
    tmp = re.search(rep, conf)
    if not tmp:
        return ''
    return tmp.groups()[0]


def __release_port(port):
    from collections import namedtuple
    try:
        from utils.firewall import Firewall as YfFirewall
        YfFirewall.instance().addAcceptPort(port, 'RSYNC同步', 'port')
        return port
    except Exception as e:
        return "Release failed {}".format(e)


def openPort():
    for i in ["873"]:
        __release_port(i)
    return True


def initDReceive():
    # 未安装：不得伪造 init.d 脚本 / systemd unit / conf（旧实现会全套造出来）
    if not isInstalled():
        return ''

    rsync_bin = yf.execShell('which rsync')[0].strip()
    if rsync_bin == '':
        # 旧实现 print('rsync missing!') + exit(0)：面板据此报「成功」而什么都没做
        print('rsync missing!')
        return ''

    # conf
    conf_path = appConf()
    conf_tpl_path = getPluginDir() + '/conf/rsyncd.conf'
    if not os.path.exists(conf_path):
        content = yf.readFile(conf_tpl_path)
        if not isinstance(content, str):
            return ''
        yf.writeFile(conf_path, content)

    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        os.mkdir(initD_path)

    file_bin = initD_path + '/' + getPluginName()
    file_tpl = getInitDTpl()
    # initd replace
    if not os.path.exists(file_bin):
        content = yf.readFile(file_tpl)
        if not isinstance(content, str):
            return ''
        content = contentReplace(content)
        yf.writeFile(file_bin, content)
        yf.execShell('chmod +x ' + yf.shlexQuote(file_bin))

    lock_file = getServerDir() + "/installed_rsyncd.pl"
    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/rsyncd.service'
    systemServiceTpl = getPluginDir() + '/init.d/rsyncd.service.tpl'
    if not os.path.exists(lock_file):
        service_path = yf.getServerDir()
        se = yf.readFile(systemServiceTpl)
        if not isinstance(se, str):
            return ''
        se = se.replace('{$SERVER_PATH}', service_path)
        se = se.replace('{$RSYNC_BIN}', rsync_bin)
        yf.writeFile(systemService, se)
        yf.execShell('systemctl daemon-reload')

        yf.writeFile(lock_file, "ok")
        openPort()

    rlog = getLog()
    if rlog and os.path.exists(rlog):
        yf.writeFile(rlog, '')
    return file_bin


def initDSend():
    # 未安装 / lsyncd 不存在：一律零产物（不写 conf、不写 init.d、不碰 systemd）
    if not isInstalled():
        return ''

    lsyncd_bin = yf.execShell('which lsyncd')[0].strip()
    if lsyncd_bin == '':
        print('lsyncd missing!')
        return ''

    service_path = yf.getServerDir()

    conf_path = getServerDir() + '/lsyncd.conf'
    conf_tpl_path = getPluginDir() + '/conf/lsyncd.conf'
    if not os.path.exists(conf_path):
        content = yf.readFile(conf_tpl_path)
        if not isinstance(content, str):
            return ''
        content = content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(conf_path, content)

    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        os.mkdir(initD_path)

    # initd replace
    file_bin = initD_path + '/lsyncd'
    file_tpl = getPluginDir() + "/init.d/lsyncd.tpl"
    if not os.path.exists(file_bin):
        content = yf.readFile(file_tpl)
        if not isinstance(content, str):
            return ''
        content = contentReplace(content)
        yf.writeFile(file_bin, content)
        yf.execShell('chmod +x ' + yf.shlexQuote(file_bin))

    lock_file = getServerDir() + "/installed.pl"
    # systemd
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/lsyncd.service'
    systemServiceTpl = getPluginDir() + '/init.d/lsyncd.service.tpl'
    if not os.path.exists(lock_file):
        content = yf.readFile(systemServiceTpl)
        if not isinstance(content, str):
            return ''
        content = content.replace('{$SERVER_PATH}', service_path)
        content = content.replace('{$LSYNCD_BIN}', lsyncd_bin)
        yf.writeFile(systemService, content)
        yf.execShell('systemctl daemon-reload')

        yf.writeFile(lock_file, "ok")

    lslog = getLsyncdLog()
    if lslog and os.path.exists(lslog):
        yf.writeFile(lslog, '')

    return file_bin


def getDefaultConf():
    path = getServerDir() + "/config.json"
    data = yf.readFile(path)
    # readFile 失败返回 False，旧实现直接 json.loads(False) → TypeError traceback
    if not isinstance(data, str):
        return None
    try:
        return json.loads(data)
    except Exception:
        return None


def setDefaultConf(data):
    path = getServerDir() + "/config.json"
    if not isinstance(data, dict):
        return False
    return bool(yf.writeFile(path, json.dumps(data)))


def initConfigJson():
    path = getServerDir() + "/config.json"
    tpl = getPluginDir() + "/conf/config.json"
    if not os.path.exists(path):
        data = yf.readFile(tpl)
        if not isinstance(data, str):
            return False
        try:
            data = json.loads(data)
        except Exception:
            return False
        yf.writeFile(path, json.dumps(data))
    return True


def initDreplace():
    if not isInstalled():
        return ''

    # 接收侧（rsyncd）是主功能：rsync 缺失/模板读不到即为失败
    file_bin = initDReceive()
    if not file_bin:
        return ''

    initDSend()
    initConfigJson()

    return file_bin


def rsyncOp(method):
    if not isInstalled():
        return 'ERROR: rsyncd 未安装'

    file = initDreplace()
    if not file:
        return 'ERROR: rsync 未安装或配置模板缺失'

    if not yf.isAppleSystem():
        # 成败必须看退出码：execShell 的 (stdout, stderr) 契约无法区分「失败」与「无输出」
        rc, _out, _err = yf.execShellRc(['systemctl', method, getPluginName()], shell=False, timeout=120)
        return 'ok' if rc == 0 else 'fail'

    data = yf.execShell(yf.shlexQuote(file) + ' ' + method)
    if data[1] == '':
        return 'ok'
    return 'fail'


def lsyncdOp(method):
    if not isInstalled():
        return 'skip'
    if yf.isAppleSystem():
        return 'fail'
    rc, _out, err = yf.execShellRc(['systemctl', method, 'lsyncd'], shell=False, timeout=120)
    if rc == 0:
        return 'ok'
    # 单元不存在（本机没装 lsyncd）不算失败，但绝不报 ok
    if 'not found' in (err or '') or 'No such file' in (err or ''):
        return 'skip'
    return 'fail'


def combineOps(rsync_res, lsyncd_res):
    """两侧结果合并：主功能失败即失败；lsyncd 的失败不能被吞成 ok。"""
    if rsync_res != 'ok':
        return rsync_res
    if lsyncd_res == 'fail':
        return 'fail'
    return 'ok'


def start():
    return combineOps(rsyncOp('start'), lsyncdOp('start'))


def stop():
    return combineOps(rsyncOp('stop'), lsyncdOp('stop'))


def restart():
    return combineOps(rsyncOp('restart'), lsyncdOp('restart'))


def reload():
    return combineOps(rsyncOp('reload'), lsyncdOp('reload'))


def initdStatus():
    if yf.isAppleSystem():
        return "Apple Computer does not support"
    if not (unitEnabled('rsyncd') and unitEnabled('lsyncd')):
        return 'fail'
    return 'ok'


def initdInstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"
    if not isInstalled():
        return 'ERROR: rsyncd 未安装'

    rc_l, _out, _err = yf.execShellRc(['systemctl', 'enable', 'lsyncd'], shell=False, timeout=30)
    rc_r, _out2, _err2 = yf.execShellRc(['systemctl', 'enable', 'rsyncd'], shell=False, timeout=30)
    if rc_r != 0 or rc_l != 0:
        return 'fail'
    return 'ok'


def initdUinstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"
    if not isInstalled():
        return 'ERROR: rsyncd 未安装'

    yf.execShellRc(['systemctl', 'disable', 'lsyncd'], shell=False, timeout=30)
    yf.execShellRc(['systemctl', 'disable', 'rsyncd'], shell=False, timeout=30)
    return 'ok'


def getRecListData():
    path = appConf()
    content = yf.readFile(path)
    # readFile 失败返回 False：旧实现交给 re.findall → TypeError traceback
    # （真机实测未安装时 /plugins/run rec_list 直接把 traceback 回给前端）
    if not isinstance(content, str):
        return []

    flist = re.findall("\\[(.*)\\]", content)

    flist_len = len(flist)
    ret_list = []
    for i in range(flist_len):
        tmp = {}
        tmp['name'] = flist[i]
        n = i + 1
        reg = ''
        if n == flist_len:
            reg = r'\[' + flist[i] + r'\](.*)\[?'
        else:
            reg = r'\[' + flist[i] + r'\](.*)\[' + flist[n] + r'\]'

        t1 = re.search(reg, content, re.S)
        if t1:
            args = t1.groups()[0]
            # print('args start', args, 'args_end')
            t2 = re.findall(r'\s*(.*)\s*\=\s*?(.*)?', args, re.M | re.I)
            for i in range(len(t2)):
                tmp[t2[i][0].strip()] = t2[i][1].strip()
        ret_list.append(tmp)

    return ret_list


def getRecListDataBy(name):
    if not checkNameSafe(name):
        return None
    l = getRecListData()
    for x in range(len(l)):
        if name == l[x]["name"]:
            return l[x]
    return None


def getRecList():
    ret_list = getRecListData()
    return yf.returnJson(True, 'ok', ret_list)


def addRec():
    args = getArgs()
    data = checkArgs(args, ['name', 'path', 'pwd', 'ps'])
    if not data[0]:
        return data[1]

    args_name = args['name']
    if not checkNameSafe(args_name):
        return yf.returnJson(False, '名称只能包含字母、数字、下划线和中划线！')

    args_pwd = args['pwd']
    args_path = args['path']
    args_ps = args['ps']

    # 这三个值会被**逐字**写进 rsyncd.conf（path / comment / secrets file 行）：
    # 任何换行或控制字符都是配置注入（例如 comment 里塞 "\nread only = true"），
    # 口令还会写进 secrets 文件（格式 name:pwd，含 ':' 会截断口令）。
    if not isinstance(args_path, str) or hasCtrl(args_path) or not os.path.isabs(args_path) \
            or args_path.strip() == '/' or invalidRecvPath(args_path):
        return yf.returnJson(False, '路径格式不合法！')
    if not isinstance(args_ps, str) or hasCtrl(args_ps) or len(args_ps) > 255:
        return yf.returnJson(False, '参数格式不合法！')
    if not isinstance(args_pwd, str) or hasCtrl(args_pwd) or ':' in args_pwd \
            or args_pwd == '' or len(args_pwd) > 128:
        return yf.returnJson(False, '密码格式不合法！')

    if not yf.isAppleSystem():
        if os.path.exists(args_path):
            import utils.file as utils_file
            info = utils_file.getAccess(args_path)
            file_chown = info['chown']
            if file_chown != 'www':
                return yf.returnJson(False, '建议手动执行命令: chown -R www:www '+ args_path)
        else:
            # 变量路径不得进 shell：列表参数 + os.makedirs，避免 `;`/`$()` 注入
            if not yf.makeDirs(args_path):
                return yf.returnJson(False, '路径格式不合法！')
            yf.safeExecShell(['chown', '-R', 'www:www', args_path])
            yf.safeExecShell(['chmod', '-R', '755', args_path])

    delRecBy(args_name)

    auth_path = appAuthPwd(args_name)
    pwd_content = args_name + ':' + args_pwd + "\n"
    if not yf.writeFile(auth_path, pwd_content):
        return yf.returnJson(False, '写入密码文件失败！')
    yf.execShell("chmod 600 " + yf.shlexQuote(auth_path))

    path = appConf()
    old_content = yf.readFile(path)
    if not isinstance(old_content, str):
        old_content = ''

    con = "\n\n" + '[' + args_name + ']' + "\n"
    con += 'path = ' + args_path + "\n"
    con += 'comment = ' + args_ps + "\n"
    con += 'auth users = ' + args_name + "\n"
    con += 'ignore errors' + "\n"
    con += 'secrets file = ' + auth_path + "\n"
    con += 'read only = false'

    hosts_allow = args.get('hosts_allow', '')
    if hosts_allow is None:
        hosts_allow = ''
    if not isinstance(hosts_allow, str):
        return yf.returnJson(False, 'IP白名单格式错误！')
    hosts_allow = hosts_allow.strip()
    if hosts_allow:
        if hasCtrl(hosts_allow) or not re.match(r'^[0-9a-zA-Z\.\,\/\s\*]+$', hosts_allow):
            return yf.returnJson(False, 'IP白名单格式错误！')
        con += "\n" + 'hosts allow = ' + hosts_allow

    content = old_content.strip() + "\n" + con
    if not yf.writeFile(path, content):
        return yf.returnJson(False, '写入配置失败，已回滚！')
    # 回读校验：rsync 没有 --check-config 之类只校验不启动的开关（真机实测：坏 conf
    # 也能把 daemon 拉起来），所以用插件自己的解析器回读，读不出刚写的模块就回滚。
    got = getRecListDataBy(args_name)
    if not got or got.get('path') != args_path:
        yf.writeFile(path, old_content)
        return yf.returnJson(False, '写入配置失败，已回滚！')
    return yf.returnJson(True, '添加成功')


def getRec():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not isinstance(name, str):
        return yf.returnJson(False, '参数格式不合法！')
    if name != "" and not checkNameSafe(name):
        return yf.returnJson(False, '名称只能包含字母、数字、下划线和中划线！')

    if name == "":
        tmp = {}
        tmp["name"] = ""
        tmp["comment"] = ""
        tmp["path"] = yf.getWwwDir()
        tmp["pwd"] = yf.getRandomString(16)
        return yf.returnJson(True, 'OK', tmp)

    data = getRecListDataBy(name)
    if not data:
        return yf.returnJson(False, '同步任务不存在！')

    pwd, err = readSecretPwd(data.get('secrets file', ''))
    if err:
        return yf.returnJson(False, err)
    data['pwd'] = pwd
    return yf.returnJson(True, 'OK', data)


def delRecBy(name):
    if not checkNameSafe(name):
        return False
    try:
        path = appConf()
        content = yf.readFile(path)
        if not isinstance(content, str):
            return False

        reclist = getRecListData()
        ret_list_len = len(reclist)
        is_end = False
        next_name = ''
        secrets_file = ''
        found = False
        for x in range(ret_list_len):
            tmp = reclist[x]
            if tmp['name'] == name:
                found = True
                secrets_file = tmp.get('secrets file', '')
                if x + 1 == ret_list_len:
                    is_end = True
                else:
                    next_name = reclist[x + 1]['name']
        if not found:
            return False

        reg = ''
        if is_end:
            reg = r'\[' + name + r'\]\s*(.*)'
        else:
            # 旧实现在这里多写了一个反斜杠（r'\\\\['）→ 正则永远匹配不到，
            # 删非末位模块恒失败，addRec 的去重也因此静默失效（同名模块重复堆积）
            reg = r'\[' + name + r'\]\s*(.*)\s*\[' + next_name + r'\]'

        conre = re.search(reg, content, re.S)
        if not conre:
            return False

        new_content = content.replace("[" + name + "]\n" + conre.groups()[0], '')
        if not yf.writeFile(path, new_content):
            return False

        # 先确认配置段已摘除，再删口令目录；且口令目录必须落在本插件的 receive/ 下
        # （secrets file 值可经面板文件编辑器改写，旧实现对任意路径 removeDir）
        secrets_dir = os.path.dirname(secrets_file)
        recv_root = os.path.realpath(getServerDir() + '/receive')
        if secrets_dir and os.path.realpath(secrets_dir).startswith(recv_root + os.sep) \
                and os.path.exists(secrets_dir):
            yf.removeDir(secrets_dir)
    except Exception:
        return False
    return True


def delRec():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]
    name = args['name']
    if not checkNameSafe(name):
        return yf.returnJson(False, '名称只能包含字母、数字、下划线和中划线！')
    ok = delRecBy(name)
    if ok:
        return yf.returnJson(True, '删除成功!')
    return yf.returnJson(False, '删除失败!')


def cmdRecSecretKey():
    import base64

    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not checkNameSafe(name):
        return yf.returnJson(False, '名称只能包含字母、数字、下划线和中划线！')
    info = getRecListDataBy(name)
    if not info:
        return yf.returnJson(False, '同步任务不存在！')

    pwd, err = readSecretPwd(info.get('secrets file', ''))
    if err:
        return yf.returnJson(False, err)

    m = {"A": info['name'], "B": pwd, "C": "873"}
    m = json.dumps(m)
    m = m.encode("utf-8")
    m = base64.b64encode(m)
    cmd = m.decode("utf-8")
    return yf.returnJson(True, 'OK!', cmd)


def cmdRecCmd():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not checkNameSafe(name):
        return yf.returnJson(False, '名称只能包含字母、数字、下划线和中划线！')
    info = getRecListDataBy(name)
    if not info:
        return yf.returnJson(False, '同步任务不存在！')
    ip = yf.getLocalIp()

    # 旧实现 `echo "<口令>" > /tmp/<name>.pass` 把**明文口令**未转义拼进 shell 并回显：
    # 口令含 `"`/`$(...)`/`;` 时用户一复制执行就注入，且口令原样出现在响应里。
    # 现改为交互式（rsync 守护进程模式会提示输入口令）：响应里不再有口令，
    # 也不再在 /tmp 落一个明文口令文件。
    cmd = 'rsync -arv --progress --delete /project ' + name + '@' + ip + '::' + name
    return yf.returnJson(True, 'OK!', cmd)


# ----------------------------- rsyncdSend start -------------------------

def lsyncdReload():
    # 旧实现 `ps -ef|grep lsyncd |grep -v grep | grep -v python` 是 cmdline 子串匹配：
    # 任何命令行里含 "lsyncd" 的无关进程都会命中 → 走 restart 而不是 start。
    # pgrep -x 只按进程名精确匹配（无匹配时 rc=1）。
    rc, out, _err = yf.execShellRc(['pgrep', '-x', 'lsyncd'], shell=False, timeout=10)
    if rc != 0 or not (out or '').strip():
        yf.execShellRc(['systemctl', 'start', 'lsyncd'], shell=False, timeout=120)
    else:
        yf.execShellRc(['systemctl', 'restart', 'lsyncd'], shell=False, timeout=120)


def makeLsyncdConf(data):
    """生成 lsyncd.conf 与每个发送任务的同步命令；返回 (ok, err)。

    值全部来自前端（config.json 可经面板文件编辑器直改），而 lsyncd 以 root 运行：
    Lua 字符串未转义时一个 `"` 就能注入任意 Lua 语句，`delete`/`delay`/`bwlimit` 等
    直接拼在字符串外更是裸注入；生成的 send/<name>/cmd 还会被 bash 与面板计划任务
    执行，路径/主机名未引用即命令注入。
    """
    if not isinstance(data, dict):
        return (False, '配置文件读取失败！')
    lsyncd_data = data.get('send')
    if not isinstance(lsyncd_data, dict):
        return (False, '配置文件读取失败！')
    lsyncd_setting = lsyncd_data.get('default')
    lsyncd_list = lsyncd_data.get('list')
    if not isinstance(lsyncd_setting, dict) or not isinstance(lsyncd_list, list):
        return (False, '配置文件读取失败！')

    content = "settings {\n"
    for x in lsyncd_setting:
        v = lsyncd_setting[x]
        if isinstance(v, str):
            content += "\t" + escapeLuaString(x) + ' = "' + escapeLuaString(v) + '",\n'
        elif isinstance(v, bool):
            content += "\t" + escapeLuaString(x) + ' = ' + ('true' if v else 'false') + ",\n"
        elif isinstance(v, int):
            content += "\t" + escapeLuaString(x) + ' = ' + str(v) + ",\n"
        elif isinstance(v, float):
            content += "\t" + escapeLuaString(x) + ' = ' + repr(v) + ",\n"
        else:
            # 旧实现把 list/dict/None 静默丢弃（生成半截配置），这里直接拒绝
            return (False, '参数格式不合法！')
    content += "}\n\n"

    send_dir = getServerDir() + "/send"
    rsync_bin = ''
    if lsyncd_list:
        rsync_bin = yf.execShell('which rsync')[0].strip()
        if rsync_bin == '':
            return (False, '参数格式不合法！')

    if len(lsyncd_list) > 0:
        for t in lsyncd_list:
            if not isinstance(t, dict):
                return (False, '参数格式不合法！')
            name = t.get('name')
            if not checkNameSafe(name):
                return (False, '名称只能包含字母、数字、下划线和中划线！')
            path = t.get('path')
            if not isinstance(path, str) or hasCtrl(path) or not os.path.isabs(path):
                return (False, '路径格式不合法！')
            ip = t.get('ip')
            if not isinstance(ip, str) or hasCtrl(ip) or not re.match(r'^[0-9a-zA-Z\.\-:]+$', ip.strip()):
                return (False, 'IP格式不合法！')
            delete = normBool(t.get('delete'))
            realtime = normBool(t.get('realtime'))
            delay = normInt(t.get('delay'), 0, 86400)
            rsync_cfg = t.get('rsync')
            if not isinstance(rsync_cfg, dict):
                return (False, '参数格式不合法！')
            port = normInt(rsync_cfg.get('port'), 1, 65535)
            bwlimit = normInt(rsync_cfg.get('bwlimit'), 0, 1024 * 1024 * 100)
            compress = normBool(rsync_cfg.get('compress'))
            exclude = t.get('exclude')
            if not isinstance(exclude, list) or len(exclude) > 500 \
                    or not all(isinstance(x, str) and not hasCtrl(x) and len(x) <= 255 for x in exclude):
                return (False, '参数格式不合法！')
            password = t.get('password')
            if not isinstance(password, str) or hasCtrl(password):
                return (False, '密码格式不合法！')
            if None in (delete, realtime, delay, port, bwlimit, compress):
                return (False, '参数格式不合法！')

            name_dir = send_dir + "/" + name
            if not os.path.exists(name_dir):
                yf.makeDirs(name_dir)

            cmd_exclude = name_dir + "/exclude"
            cmd_exclude_txt = ""
            for x in exclude:
                cmd_exclude_txt += x + "\n"
            yf.writeFile(cmd_exclude, cmd_exclude_txt)

            cmd_pass = name_dir + "/pass"
            if os.path.exists(cmd_pass):
                yf.execShell("chmod 755 " + yf.shlexQuote(cmd_pass))
            if not yf.writeFile(cmd_pass, password):
                return (False, '写入配置失败！')
            yf.execShell("chmod 600 " + yf.shlexQuote(cmd_pass))

            remote_addr = name + '@' + ip + "::" + name
            # 同步命令会被写进 send/<name>/cmd 并交给 bash / 面板计划任务执行：
            # 逐段 shlexQuote（path/ip 等都是前端可控输入），否则 `;`/`$()` 即注入
            parts = [yf.shlexQuote(rsync_bin), '-avzP',
                     '--port=' + str(port), '--bwlimit=' + str(bwlimit)]
            if delete == 'true':
                parts.append('--delete')
            parts += ['--exclude-from=' + yf.shlexQuote(cmd_exclude),
                      '--password-file=' + yf.shlexQuote(cmd_pass),
                      yf.shlexQuote(path), yf.shlexQuote(remote_addr)]
            if not yf.writeFile(name_dir + "/cmd", ' '.join(parts)):
                return (False, '写入配置失败！')
            yf.execShell("chmod +x " + yf.shlexQuote(name_dir + "/cmd"))

            if realtime == "false":
                continue

            exclude_str = "{" + ", ".join('"' + escapeLuaString(x) + '"' for x in exclude) + "}"

            content += "sync {\n"
            content += "\tdefault.rsync,\n"
            content += "\tsource = \"" + escapeLuaString(path) + "\",\n"
            content += "\ttarget = \"" + escapeLuaString(remote_addr) + "\",\n"
            content += "\tdelete = " + delete + ",\n"
            content += "\tdelay = " + str(delay) + ",\n"
            content += "\tinit = false,\n"
            content += "\texclude = " + exclude_str + ",\n"

            # rsync
            content += "\trsync = {\n"
            content += "\t\tbinary = \"" + escapeLuaString(rsync_bin) + "\",\n"
            content += "\t\tarchive = true,\n"
            content += "\t\tverbose = true,\n"
            content += "\t\tcompress = " + compress + ",\n"
            content += "\t\tpassword_file = \"" + escapeLuaString(cmd_pass) + "\",\n"
            content += "\t\t_extra = {\"--bwlimit=" + str(bwlimit) + "\", \"--port=" + str(port) + "\"},\n"
            content += "\t}\n"
            content += "}\n"

    path = getServerDir() + "/lsyncd.conf"
    if not yf.writeFile(path, content):
        return (False, '写入配置失败！')

    lsyncdReload()

    import tool_task
    tool_task.createBgTask(lsyncd_list)
    return (True, '')


def lsyncdListFindIp(slist, ip):
    for x in range(len(slist)):
        if slist[x]["ip"] == ip:
            return (True, x)
    return (False, -1)


def lsyncdListFindName(slist, name):
    for x in range(len(slist)):
        if slist[x]["name"] == name:
            return (True, x)
    return (False, -1)


def lsyncdList():
    data = sendListData()
    if data is None:
        return yf.returnJson(False, '配置文件读取失败！')
    return yf.returnJson(True, "设置成功!", data['send'])


def lsyncdGet():
    import base64
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not checkNameSafe(name):
        return yf.returnJson(False, '名称只能包含字母、数字、下划线和中划线！')

    data = sendListData()
    if data is None:
        return yf.returnJson(False, '配置文件读取失败！')

    slist = data['send']["list"]
    res = lsyncdListFindName(slist, name)

    rsync = {
        'bwlimit': "1024",
        "compress": "true",
        "archive": "true",
        "verbose": "true"
    }

    info = {
        "secret_key": '',
        "ip": '',
        "path": yf.getServerDir(),
        'rsync': rsync,
        'realtime': "true",
        'delete': "false",
        # 新建任务时这三个字段旧实现没给：前端输入框 value 变成字符串 'undefined'
        # 并原样提交（服务端拒绝）——这里补上确定默认值。
        'period': "day",
        'hour': "0",
        'minute': "0",
        'minute-n': "1",
        'delay': "3",
    }
    if res[0]:
        list_index = res[1]
        info = slist[list_index]
        m = {"A": info['name'], "B": info["password"], "C": "873"}
        m = json.dumps(m)
        m = m.encode("utf-8")
        m = base64.b64encode(m)
        info['secret_key'] = m.decode("utf-8")
    return yf.returnJson(True, "OK", info)


def lsyncdDelete():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not checkNameSafe(name):
        return yf.returnJson(False, '名称只能包含字母、数字、下划线和中划线！')

    data = sendListData()
    if data is None:
        return yf.returnJson(False, '配置文件读取失败！')
    slist = data['send']["list"]
    res = lsyncdListFindName(slist, name)
    if not res[0]:
        return yf.returnJson(False, '同步任务不存在！')
    slist.pop(res[1])

    data['send']["list"] = slist
    ok, err = makeLsyncdConf(data)
    if not ok:
        return yf.returnJson(False, err)
    if not setDefaultConf(data):
        return yf.returnJson(False, '写入配置失败！')
    return yf.returnJson(True, "OK")


def lsyncdAdd():
    import base64

    args = getArgs()
    data = checkArgs(args, ['ip', 'conn_type', 'path', 'delay', 'period', 'bwlimit'])
    if not data[0]:
        return data[1]

    ip = args['ip']
    path = args['path']

    # ip/path 会被写进 lsyncd.conf（Lua 字符串）与 send/<name>/cmd（shell 命令）
    if not isinstance(ip, str) or hasCtrl(ip) or not re.match(r'^[0-9a-zA-Z\.\-:]+$', ip.strip()):
        return yf.returnJson(False, 'IP格式不合法！')
    ip = ip.strip()
    if not isinstance(path, str) or hasCtrl(path) or not os.path.isabs(path):
        return yf.returnJson(False, '路径格式不合法！')

    if not yf.isAppleSystem():
        if os.path.exists(path):
            import utils.file as utils_file
            info = utils_file.getAccess(path)
            file_chown = info['chown']
            if file_chown != 'www':
                return yf.returnJson(False, '建议手动执行命令: chown -R www:www '+ path)
        else:
            # 变量路径不得进 shell：列表参数 + os.makedirs，避免 `;`/`$()` 注入
            if not yf.makeDirs(path):
                return yf.returnJson(False, '路径格式不合法！')
            yf.safeExecShell(['chown', '-R', 'www:www', path])
            yf.safeExecShell(['chmod', '-R', '755', path])

    conn_type = args['conn_type']
    if conn_type not in ('key', 'user'):
        return yf.returnJson(False, '参数格式不合法！')

    delete = normBool(args.get('delete'))
    realtime = normBool(args.get('realtime'))
    compress = normBool(args.get('compress'))
    if None in (delete, realtime, compress):
        return yf.returnJson(False, '参数格式不合法！')

    delay = normInt(args.get('delay'), 0, 86400)
    bwlimit = normInt(args.get('bwlimit'), 0, 1024 * 1024 * 100)
    if delay is None or bwlimit is None:
        return yf.returnJson(False, '参数格式不合法！')

    period = args.get('period')
    if period not in ('day', 'minute-n'):
        return yf.returnJson(False, '参数格式不合法！')
    hour = normInt(args.get('hour'), 0, 23, default=0)
    minute = normInt(args.get('minute'), 0, 59, default=0)
    minute_n = normInt(args.get('minute-n'), 1, 1440, default=1)
    if None in (hour, minute, minute_n):
        return yf.returnJson(False, '参数格式不合法！')

    info = {
        "ip": ip,
        "path": path,
        "delete": delete,
        "realtime": realtime,
        'delay': delay,
        "conn_type": conn_type,
        "period": period,
        "hour": hour,
        "minute": minute,
        "minute-n": minute_n,
    }

    if conn_type == "key":

        secret_key_check = checkArgs(args, ['secret_key'])
        if not secret_key_check[0]:
            return secret_key_check[1]

        secret_key = args['secret_key']
        if not isinstance(secret_key, str) or len(secret_key) > 4096:
            return yf.returnJson(False, "接收密钥格式错误!")
        try:
            m = base64.b64decode(secret_key)
            m = json.loads(m)
            info['name'] = m['A']
            info['password'] = m['B']
            info['port'] = m['C']
        except Exception:
            return yf.returnJson(False, "接收密钥格式错误!")
    else:
        data = checkArgs(args, ['sname', 'password'])
        if not data[0]:
            return data[1]

        info['name'] = args['sname']
        info['password'] = args['password']
        info['port'] = args['port']

    if not checkNameSafe(info['name']):
        return yf.returnJson(False, '名称只能包含字母、数字、下划线和中划线！')
    if not isinstance(info['password'], str) or hasCtrl(info['password']) or len(info['password']) > 128:
        return yf.returnJson(False, '密码格式不合法！')

    try:
        port_num = int(info['port'])
        if not (1 <= port_num <= 65535):
            raise ValueError
        info['port'] = port_num
    except Exception:
        return yf.returnJson(False, "端口格式不合法！")

    rsync = {
        'bwlimit': bwlimit,
        "port": info['port'],
        "compress": compress,
        "archive": "true",
        "verbose": "true"
    }

    info['rsync'] = rsync

    data = sendListData()
    if data is None:
        return yf.returnJson(False, '配置文件读取失败！')

    slist = data['send']["list"]
    res = lsyncdListFindName(slist, info['name'])

    if not 'exclude' in info:
        if res[0]:
            info["exclude"] = slist[res[1]]['exclude']
        else:
            info["exclude"] = [
                "/**.upload.tmp", "**/*.log", "**/*.tmp",
                "**/*.temp", ".git", ".gitignore", ".user.ini",
            ]

    if res[0]:
        list_index = res[1]
        slist[list_index] = info
    else:
        slist.append(info)

    data['send']["list"] = slist

    # 先出配置/命令（失败即不动 config.json），再落库
    ok, err = makeLsyncdConf(data)
    if not ok:
        return yf.returnJson(False, err)
    if not setDefaultConf(data):
        return yf.returnJson(False, '写入配置失败！')
    return yf.returnJson(True, "设置成功!")


def lsyncdRun():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not checkNameSafe(name):
        return yf.returnJson(False, '名称只能包含字母、数字、下划线 and 中划线！')

    send_dir = getServerDir() + "/send"
    app_dir = send_dir + "/" + name

    # 命令文件不存在时旧实现仍回「执行成功」（假成功）
    if not os.path.exists(app_dir + "/cmd"):
        return yf.returnJson(False, '同步任务不存在！')

    cmd = "bash " + yf.shlexQuote(app_dir + "/cmd") + " >> " + yf.shlexQuote(app_dir + "/run.log") + " 2>&1 &"
    yf.execShell(cmd)
    return yf.returnJson(True, "执行成功!")


def lsyncdConfLog():
    logs_path = getServerDir() + "/lsyncd.log"
    return logs_path


def lsyncdLog():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not checkNameSafe(name):
        return yf.returnJson(False, '名称只能包含字母、数字、下划线 and 中划线！')

    send_dir = getServerDir() + "/send"
    app_dir = send_dir + "/" + name
    return app_dir + "/run.log"


def findSendItem(name):
    """按名取发送任务；不存在返回 None（旧实现 res[1] == -1 会取到 slist[-1] 末项）"""
    data = sendListData()
    if data is None:
        return None
    slist = data['send']["list"]
    res = lsyncdListFindName(slist, name)
    if not res[0]:
        return None
    return (data, res[1])


def lsyncdGetExclude():
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not checkNameSafe(name):
        return yf.returnJson(False, '名称只能包含字母、数字、下划线 and 中划线！')

    found = findSendItem(name)
    if found is None:
        return yf.returnJson(False, '同步任务不存在！')
    data, i = found
    info = data['send']["list"][i]
    return yf.returnJson(True, "OK!", info.get('exclude', []))


def normExclude(v):
    if not isinstance(v, str) or hasCtrl(v) or v == '' or len(v) > 255:
        return None
    return v


def lsyncdRemoveExclude():
    args = getArgs()
    data = checkArgs(args, ['name', 'exclude'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not checkNameSafe(name):
        return yf.returnJson(False, '名称只能包含字母、数字、下划线 and 中划线！')

    exclude = normExclude(args['exclude'])
    if exclude is None:
        return yf.returnJson(False, '参数格式不合法！')

    found = findSendItem(name)
    if found is None:
        return yf.returnJson(False, '同步任务不存在！')
    data, i = found
    info = data['send']["list"][i]

    exclude_list = info.get('exclude', [])
    if not isinstance(exclude_list, list):
        exclude_list = []
    exclude_pop_key = -1
    for x in range(len(exclude_list)):
        if exclude_list[x] == exclude:
            exclude_pop_key = x

    if exclude_pop_key > -1:
        exclude_list.pop(exclude_pop_key)

    data['send']["list"][i]['exclude'] = exclude_list
    ok, err = makeLsyncdConf(data)
    if not ok:
        return yf.returnJson(False, err)
    if not setDefaultConf(data):
        return yf.returnJson(False, '写入配置失败！')
    return yf.returnJson(True, "OK!", exclude_list)


def lsyncdAddExclude():
    args = getArgs()
    data = checkArgs(args, ['name', 'exclude'])
    if not data[0]:
        return data[1]

    name = args['name']
    if not checkNameSafe(name):
        return yf.returnJson(False, '名称只能包含字母、数字、下划线 and 中划线！')

    exclude = normExclude(args['exclude'])
    if exclude is None:
        return yf.returnJson(False, '参数格式不合法！')

    found = findSendItem(name)
    if found is None:
        return yf.returnJson(False, '同步任务不存在！')
    data, i = found
    info = data['send']["list"][i]

    exclude_list = info.get('exclude', [])
    if not isinstance(exclude_list, list):
        exclude_list = []
    if len(exclude_list) >= 500:
        return yf.returnJson(False, '参数格式不合法！')
    exclude_list.append(exclude)

    data['send']["list"][i]['exclude'] = exclude_list
    ok, err = makeLsyncdConf(data)
    if not ok:
        return yf.returnJson(False, err)
    if not setDefaultConf(data):
        return yf.returnJson(False, '写入配置失败！')
    return yf.returnJson(True, "OK!", exclude_list)

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
    elif func == 'conf':
        print(appConf())
    elif func == 'run_log':
        print(getLog())
    elif func == 'rec_list':
        print(getRecList())
    elif func == 'add_rec':
        print(addRec())
    elif func == 'del_rec':
        print(delRec())
    elif func == 'get_rec':
        print(getRec())
    elif func == 'cmd_rec_secret_key':
        print(cmdRecSecretKey())
    elif func == 'cmd_rec_cmd':
        print(cmdRecCmd())
    elif func == 'lsyncd_list':
        print(lsyncdList())
    elif func == 'lsyncd_add':
        print(lsyncdAdd())
    elif func == 'lsyncd_get':
        print(lsyncdGet())
    elif func == 'lsyncd_delete':
        print(lsyncdDelete())
    elif func == 'lsyncd_run':
        print(lsyncdRun())
    elif func == 'lsyncd_log':
        print(lsyncdLog())
    elif func == 'lsyncd_conf_log':
        print(lsyncdConfLog())
    elif func == 'lsyncd_get_exclude':
        print(lsyncdGetExclude())
    elif func == 'lsyncd_remove_exclude':
        print(lsyncdRemoveExclude())
    elif func == 'lsyncd_add_exclude':
        print(lsyncdAddExclude())
    else:
        print('error')
