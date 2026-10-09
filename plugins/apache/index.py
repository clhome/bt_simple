# coding:utf-8

import sys
import io
import os
import time
import json
import threading
import subprocess
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
    return 'apache'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getHttpdBin():
    return getServerDir() + '/httpd/bin/httpd'


def isInstalled():
    # 判据用主程序 httpd 是否存在，而不是安装目录是否存在：confReplace() 只写
    # httpd/conf/httpd.conf，会让空目录看起来「已安装」，随后 initDreplace 就在
    # 没有二进制的情况下伪造出 init.d 脚本与 systemd unit（真机实测：对未安装的
    # apache 调一次 reload 就生成了可被 `systemctl enable` 的假 httpd.service）。
    return os.path.exists(getHttpdBin())


def detectMpmModule(content):
    r"""判定当前生效的 MPM 模块名（prefork / worker / event ...）。

    旧实现 `re.search(r"mpm_(\w+)_module", content)` 命中的是**第一个**出现处，
    而 httpd-mpm.conf 第一行就是 `<IfModule !mpm_netware_module>` —— 于是无论实际
    构建的是哪个 MPM，面板都只显示 netware 的参数、set_cfg 也只写进永不生效的
    netware 块（真机夹具实测：改 StartServers 后 prefork 块纹丝不动）。
    优先问安装的二进制（`httpd -V` 的 `Server MPM:`，静态 MPM 构建同样适用），
    取不到再退回配置文件里第一个**非取反**的 `<IfModule mpm_XXX_module>` 块。
    """
    if isInstalled():
        try:
            out = yf.execShell(getHttpdBin() + ' -V', timeout=10)
        except Exception:
            out = None
        if out:
            m = re.search(r"Server MPM:\s*(\w+)", out[0] + out[1])
            if m:
                return m.group(1).lower()
    m = re.search(r"<IfModule\s+mpm_(\w+?)_module\s*>", content)
    if m:
        return m.group(1)
    return ""


def getInitDFile():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return '/tmp/' + getPluginName()

    if current_os.startswith('freebsd'):
        return '/etc/rc.d/' + getPluginName()

    return '/etc/init.d/' + getPluginName()


def getArgs():
    # utils/plugin.py::run() 把前端序列化后的 args 作为**一个** argv 传进来
    # （cmd_list=[python, path, func, version?, args]），所以必须优先按 JSON 解析；
    # 旧实现只按 `k:v` 切 → 键变成带引号的 `"StartServers"` → 带参接口恒静默失效。
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        val = args[0].strip()
        if val.startswith('{') and val.endswith('}'):
            try:
                parsed = json.loads(val)
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                return parsed
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
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


def clearTemp():
    path_bin = getServerDir() + "/httpd"


def getConf():
    path = getServerDir() + "/httpd/conf/httpd.conf"
    return path


def getConfMpm():
    path = getServerDir() + "/httpd/conf/extra/httpd-mpm.conf"
    return path


def getConfTpl():
    path = getPluginDir() + '/conf/httpd.conf'
    return path


def getOs():
    data = {}
    data['os'] = yf.getOs()
    data['auth'] = True
    return yf.getJson(data)


def getInitDTpl():
    path = getPluginDir() + "/init.d/httpd.tpl"
    return path


def getPidFile():
    file = getConf()
    content = yf.readFile(file)
    # readFile 读不到返回 False；且模板里没有 `pid ...;` 形态的指令（Apache 用
    # `PidFile "logs/httpd.pid"`，无分号），两处都会让旧实现抛异常
    if not content:
        return None
    rep = r'pid\s*(.*);'
    tmp = re.search(rep, content)
    if not tmp:
        return None
    return tmp.groups()[0].strip()


def getFileOwner(filename):
    import pwd
    stat = os.lstat(filename)
    uid = stat.st_uid
    pw = pwd.getpwuid(uid)
    return pw.pw_name


def checkAuthEq(file, owner='root'):
    fowner = getFileOwner(file)
    if (fowner == owner):
        return True
    return False


def confReplace():
    service_path = yf.getServerDir()
    content = yf.readFile(getConfTpl())
    # yf.readFile 读不到返回 False（不是空串），直接 .replace() 会 AttributeError
    if not content:
        return False
    content = content.replace('{$SERVER_PATH}', service_path)

    # 主配置文件
    nconf = getServerDir() + '/httpd/conf/httpd.conf'
    yf.writeFile(nconf, content)
    return True


def initDreplace():

    file_tpl = getInitDTpl()
    service_path = yf.getServerDir()

    initD_path = getServerDir() + '/init.d'

    # Apache 未安装：不得伪造安装产物（init.d 脚本 / systemd unit）。旧实现在这里
    # `print("ok"); exit(0)` —— start/restart 对未安装的 apache 也回 ok（假启动），
    # 而 reload 会先经 confReplace 建出 conf 目录，再一路生成 systemd unit。
    if not isInstalled():
        return None

    # init.d
    file_bin = initD_path + '/' + getPluginName()
    if not os.path.exists(initD_path):
        os.mkdir(initD_path)

        # initd replace
        content = yf.readFile(file_tpl)
        if not content:
            return None
        content = content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(file_bin, content)
        yf.execShell('chmod +x ' + file_bin)

        # config replace
        confReplace()

    # systemd
    # /usr/lib/systemd/system
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/httpd.service'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        systemServiceTpl = getPluginDir() + '/init.d/httpd.service.tpl'
        se_content = yf.readFile(systemServiceTpl)
        if not se_content:
            return None
        se_content = se_content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(systemService, se_content)
        yf.execShell('systemctl daemon-reload')

    return file_bin


def status():
    cmd = "ps -ef|grep 'httpd/bin/httpd' |grep -v grep | grep -v python | awk '{print $2}'"
    data = yf.execShell(cmd)
    if data[0] == '':
        return 'stop'
    return 'start'


def restyOp(method):
    if not isInstalled():
        return 'ERROR: apache 未安装'

    file = initDreplace()
    if not file:
        return 'ERROR: apache 未安装'

    # 启动时,先检查一下配置文件
    check = getHttpdBin() + " -t"
    check_data = yf.execShell(check)
    if not check_data[1].find('Syntax OK') > -1:
        return check_data[1]

    current_os = yf.getOs()
    if current_os == "darwin":
        data = yf.execShell(file + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    if current_os.startswith("freebsd"):
        yf.execShell('service httpd '+method)
        if data[1] == '':
            return 'ok'
        return data[1]

    data = yf.execShell('systemctl ' + method + ' httpd')
    if data[1] == '':
        return 'ok'
    return data[1]


def op_submit_systemctl_restart():
    current_os = yf.getOs()
    if current_os.startswith("freebsd"):
        yf.execShell('service httpd restart')
        return True

    yf.execShell('systemctl restart httpd')
    return True


def op_submit_init_restart(file):
    yf.execShell(file + ' restart')


def restyOp_restart():
    if not isInstalled():
        return 'ERROR: apache 未安装'

    file = initDreplace()
    if not file:
        return 'ERROR: apache 未安装'

    # 启动时,先检查一下配置文件
    check = getHttpdBin() + " -t"
    check_data = yf.execShell(check)
    if not check_data[1].find('Syntax OK') > -1:
        return 'ERROR: 配置出错<br><a style="color:red;">' + check_data[1].replace("\n", '<br>') + '</a>'

    if not yf.isAppleSystem():
        threading.Timer(2, op_submit_systemctl_restart).start()
        return 'ok'

    threading.Timer(2, op_submit_init_restart, args=(file,)).start()
    return 'ok'


def start():
    return restyOp('start')


def stop():
    r = restyOp('stop')

    # 兜底清理残留进程：与 status 用同一判据（限定 httpd 主程序路径 + 排除 python 自匹配），
    # 旧写法 `grep httpd` 会连带匹配 `vim httpd.conf` 这类无关进程。
    yf.execShell("ps -ef|grep '" + getHttpdBin() + "' |grep -v grep | grep -v python | awk '{print $2}'|xargs -r kill")
    return r


def restart():
    return restyOp_restart()


def reload():
    if not isInstalled():
        return 'ERROR: apache 未安装'
    if not confReplace():
        return 'ERROR: 配置文件模板缺失'
    return restyOp('reload')


def initdStatus():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile()
        if os.path.exists(initd_bin):
            return 'ok'

    shell_cmd = 'systemctl status httpd | grep loaded | grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    # freebsd initd install
    if not isInstalled():
        return 'ERROR: apache 未安装'

    if current_os.startswith('freebsd'):
        import shutil
        source_bin = initDreplace()
        if not source_bin:
            return 'ERROR: apache 未安装'
        initd_bin = getInitDFile()
        shutil.copyfile(source_bin, initd_bin)
        yf.execShell('chmod +x ' + initd_bin)
        yf.execShell('sysrc httpd_enable="YES"')
        return 'ok'

    rc, out, err = yf.execShellRc('systemctl enable httpd')
    if rc != 0:
        return 'ERROR: 设置开机自启失败: ' + (err or out)
    return 'ok'


def initdUinstall():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile()
        os.remove(initd_bin)
        yf.execShell('sysrc httpd_enable="NO"')
        return 'ok'

    rc, out, err = yf.execShellRc('systemctl disable httpd')
    if rc != 0:
        return 'ERROR: 取消开机自启失败: ' + (err or out)
    return 'ok'

def getHttpdStatusPort():
    conf = yf.getServerDir() + '/apache/httpd/conf/httpd.conf'
    content = yf.readFile(conf)
    if not content:
        return None
    rep = r'^\s*Listen\s*(?:\d+\.\d+\.\d+\.\d+:)?(\d+)'  # 匹配非注释行的 Listen 指令，忽略大小写
    tmp = re.search(rep, content, re.IGNORECASE | re.MULTILINE)
    if tmp:
        port = tmp.groups()[0].strip()
        return port
    return None


def runInfoDone(data):
    result = {}
    if not data:
        return result
    
    # 解析服务器状态数据
    lines = data.strip().split('\n')
    for line in lines:
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            result[key] = value
    
    return result


def runInfo():
    op_status = status()
    if op_status == 'stop':
        return yf.returnJson(False, "未启动!")

    port = getHttpdStatusPort()
    if not port:
        return yf.returnJson(False, "无法获取端口信息!")
    
    # 取Openresty负载状态
    try:
        url = 'http://127.0.0.1:%s/server-status?auto' % port
        result = yf.httpGet(url, timeout=3)
        data = runInfoDone(result)
        return yf.getJson(data)
    except Exception as e:
        try:
            url = 'http://' + yf.getHostAddr() + ':%s/server-status?auto' % port
            result = yf.httpGet(url)
            data = runInfoDone(result)
            return yf.getJson(data)
        except Exception as e:
            return yf.returnJson(False, "apache异常!")
        
    except Exception as e:
        return yf.returnJson(False, "apache not started!")


def errorLogPath():
    return getServerDir() + '/httpd/logs/error.log'


def getCfg():
    cfg = getConfMpm()
    content = yf.readFile(cfg)
    if not content:
        return yf.returnJson(False, 'apache 未安装或配置文件不存在!')

    unitrep = "[kmgKMG]"

    # 获取当前 MPM 模块
    mpm_module = detectMpmModule(content)
    
    # MPM 配置参数
    mpm_cfg_args = {
        "prefork": [
            {"name": "StartServers", "ps": "服务器进程启动数量", 'type': 2},
            {"name": "MinSpareServers", "ps": "保持空闲的最小服务器进程数", 'type': 2},
            {"name": "MaxSpareServers", "ps": "保持空闲的最大服务器进程数", 'type': 2},
            {"name": "MaxRequestWorkers", "ps": "允许启动的最大服务器进程数", 'type': 2},
            {"name": "MaxConnectionsPerChild", "ps": "服务器进程服务的最大连接数", 'type': 2},
        ],
        "worker": [
            {"name": "StartServers", "ps": "初始服务器进程数", 'type': 2},
            {"name": "MinSpareThreads", "ps": "保持空闲的最小工作线程数", 'type': 2},
            {"name": "MaxSpareThreads", "ps": "保持空闲的最大工作线程数", 'type': 2},
            {"name": "ThreadsPerChild", "ps": "每个服务器进程的工作线程数", 'type': 2},
            {"name": "MaxRequestWorkers", "ps": "最大工作线程数", 'type': 2},
            {"name": "MaxConnectionsPerChild", "ps": "服务器进程服务的最大连接数", 'type': 2},
        ],
        "event": [
            {"name": "StartServers", "ps": "初始服务器进程数", 'type': 2},
            {"name": "MinSpareThreads", "ps": "保持空闲的最小工作线程数", 'type': 2},
            {"name": "MaxSpareThreads", "ps": "保持空闲的最大工作线程数", 'type': 2},
            {"name": "ThreadsPerChild", "ps": "每个服务器进程的工作线程数", 'type': 2},
            {"name": "MaxRequestWorkers", "ps": "最大工作线程数", 'type': 2},
            {"name": "MaxConnectionsPerChild", "ps": "服务器进程服务的最大连接数", 'type': 2},
        ],
        "netware": [
            {"name": "ThreadStackSize", "ps": "每个工作线程分配的堆栈大小", 'type': 2},
            {"name": "StartThreads", "ps": "服务器启动时启动的工作线程数", 'type': 2},
            {"name": "MinSpareThreads", "ps": "保持空闲的最小线程数", 'type': 2},
            {"name": "MaxSpareThreads", "ps": "保持空闲的最大线程数", 'type': 2},
            {"name": "MaxThreads", "ps": "同时活跃的最大工作线程数", 'type': 2},
            {"name": "MaxConnectionsPerChild", "ps": "线程服务的最大连接数", 'type': 2},
        ],
        "mpmt_os2": [
            {"name": "StartServers", "ps": "维护的服务器进程数", 'type': 2},
            {"name": "MinSpareThreads", "ps": "每个进程的最小空闲线程数", 'type': 2},
            {"name": "MaxSpareThreads", "ps": "每个进程的最大空闲线程数", 'type': 2},
            {"name": "MaxConnectionsPerChild", "ps": "每个服务器进程的最大连接数", 'type': 2},
        ],
        "winnt": [
            {"name": "ThreadsPerChild", "ps": "服务器进程中的工作线程数", 'type': 2},
            {"name": "MaxConnectionsPerChild", "ps": "服务器进程服务的最大连接数", 'type': 2},
        ]
    }
    
    # 通用配置参数
    common_cfg_args = [
        {"name": "MaxMemFree", "ps": "每个分配器允许持有的最大空闲KB数", 'type': 2},
    ]
    
    # 合并配置参数
    cfg_args = []
    if mpm_module in mpm_cfg_args:
        cfg_args.extend(mpm_cfg_args[mpm_module])
    cfg_args.extend(common_cfg_args)

    rdata = []
    for i in cfg_args:
        # 匹配 MPM 特定配置
        rep = r"<IfModule mpm_%s_module>.*?(%s)\s+(\w+).*?</IfModule>" % (mpm_module, i["name"])
        k = re.search(rep, content, re.DOTALL)
        
        # 如果没有找到 MPM 特定配置，尝试匹配通用配置
        if not k:
            rep = r"(%s)\s+(\w+)" % i["name"]
            k = re.search(rep, content)
        
        if not k:
            continue
        
        key = k.group(1)
        v = k.group(2) if len(k.groups()) > 1 else ""

        if re.search(unitrep, v):
            u = str.upper(v[-1])
            v = v[:-1]
            if len(u) == 1:
                psstr = u + "B，" + i["ps"]
            else:
                psstr = u + "，" + i["ps"]
        else:
            u = ""

        kv = {"name": key, "value": v, "unit": u,
              "ps": i["ps"], "type": i["type"]}
        rdata.append(kv)
    return yf.returnJson(True, "ok", rdata)

def replaceChar(value, index, new_char):
    return value[:index] + new_char + value[index+1:]

def setCfg():
    args = getArgs()
    
    # 检查参数，允许动态参数
    cfg = getConfMpm()
    content = yf.readFile(cfg)
    if not content:
        return yf.returnJson(False, 'apache 未安装或配置文件不存在!')
    yf.backFile(cfg)

    # 获取当前 MPM 模块
    mpm_module = detectMpmModule(content)

    # 验证参数值
    for k, v in args.items():
        k = str(k).strip()
        v = str(v).strip()
        # 只接受纯数字：旧写法 `re.search(r"\d+", v)` 放行 `7; rm -rf /`、`7\nFoo`，
        # 这类值会被原样写进 httpd-mpm.conf（换行可注入任意指令）。
        if not re.match(r"^\d+$", v):
            return yf.returnJson(False, '参数值错误,请输入数字整数')
        # 参数名必须是合法标识符：它会被拼进正则与配置文本（旧写法即正则注入面）。
        if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", k):
            continue

        # 替换 MPM 特定配置
        if mpm_module:
            def replace_mpm_config(match):
                return match.group(1) + k + match.group(2) + v + match.group(3)
            rep = r"(<IfModule mpm_%s_module>.*?)%s(\s+)\d+(.*?</IfModule>)" % (mpm_module, re.escape(k))
            if re.search(rep, content, re.DOTALL):
                content = re.sub(rep, replace_mpm_config, content, flags=re.DOTALL)

        # 替换通用配置
        def replace_common_config(match):
            return k + match.group(1) + v
        rep = r"%s(\s+)\d+" % re.escape(k)
        if re.search(rep, content):
            content = re.sub(rep, replace_common_config, content)

    yf.writeFile(cfg, content)
    isError = yf.checkHttpdConfig()
    if (isError != True):
        yf.restoreFile(cfg)
        # 后端消息契约：可翻译前缀必须是「纯文本 + 冒号」且位于消息开头，
        # HTML 只能出现在前缀之后（否则键会含 HTML，违反红线）。
        return yf.returnJson(False, '配置出错: ' + '<span style="color:red;">' + isError.replace("\n", '<br>') + '</span>')

    yf.restartWeb()
    return yf.returnJson(True, '设置成功')


def cronAddCheck():
    try:
        import tool_task
        tool_task.createBgTask()
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

def cronCheck():
    return 'ok'


def installPreInspection():
    return 'ok'


if __name__ == "__main__":

    version = '2.4'
    version_pl = getServerDir() + "/version.pl"
    if os.path.exists(version_pl):
        version = yf.readFile(version_pl)


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
    elif func == 'install_pre_inspection':
        print(installPreInspection())
    elif func == 'conf':
        print(getConf())
    elif func == 'get_os':
        print(getOs())
    elif func == 'run_info':
        print(runInfo())
    elif func == 'error_log':
        print(errorLogPath())
    elif func == 'get_cfg':
        print(getCfg())
    elif func == 'set_cfg':
        print(setCfg())
    elif func == 'check':
        print(cronCheck())
    elif func == 'cron_add_check':
        print(cronAddCheck())
    elif func == 'cron_del_check':
        print(cronDelCheck())
    else:
        print('error')
