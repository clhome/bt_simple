# coding:utf-8

import sys
import io
import os
import time
import threading
import subprocess
import re


web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.mw as mw

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'caddy'


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


def getArgs():
    args = sys.argv[2:]
    # print(args)
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        t = args[0].strip('{').strip('}')
        t = t.split(':',2)
        tmp[t[0]] = t[1]
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':',2)
            tmp[t[0]] = t[1]
    # print(tmp)
    return tmp


def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '参数:(' + ck[i] + ')没有!'))
    return (True, yf.returnJson(True, 'ok'))


def getOs():
    data = {}
    data['os'] = yf.getOs()
    data['auth'] = True
    return yf.getJson(data)

def getConf():
    path = getServerDir() + "/Caddyfile"
    return path


def getConfTpl():
    path = getPluginDir() + '/conf/Caddyfile'
    return path


def getInitDTpl():
    path = getPluginDir() + "/init.d/caddy.tpl"
    return path

def initDreplace():
    file_tpl = getInitDTpl()
    service_path = yf.getServerDir()
    initD_path = getServerDir() + '/init.d'

    # init.d
    file_bin = initD_path + '/' + getPluginName()

    if not os.path.exists(initD_path):
        os.mkdir(initD_path)

        # initd replace
        content = yf.readFile(file_tpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(file_bin, content)
        yf.execShell('chmod +x ' + file_bin)

    caddy_file = getConf()
    if not os.path.exists(caddy_file):
        caddy_file_tpl = getConfTpl()
        content = yf.readFile(systemServiceTpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(caddy_file, content)

    # systemd
    # /usr/lib/systemd/system
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/caddy.service'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        systemServiceTpl = getPluginDir() + '/init.d/caddy.service.tpl'
        se_content = yf.readFile(systemServiceTpl)
        se_content = se_content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(systemService, se_content)
        yf.execShell('systemctl daemon-reload')

    return file_bin


def status():
    cmd = "ps -ef|grep 'caddy run' |grep -v grep | grep -v python | awk '{print $2}'"
    data = yf.execShell(cmd)
    if data[0] == '':
        return 'stop'
    return 'start'
    

def caddyOp(method):
    file = initDreplace()

    current_os = yf.getOs()
    if current_os == "darwin":
        data = yf.execShell(file + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    if current_os.startswith("freebsd"):
        data = yf.execShell('service caddy ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    data = yf.execShell('systemctl ' + method + ' caddy')
    if data[1] == '':
        return 'ok'
    return data[1]

def start():
    return caddyOp('start')


def stop():
    r = caddyOp('stop')
    return r


def restart():
    return restyOp_restart()


def reload():
    confReplace()
    return caddyOp('reload')


def initdStatus():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile()
        if os.path.exists(initd_bin):
            return 'ok'

    shell_cmd = 'systemctl status caddy | grep loaded | grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    # freebsd initd install
    if current_os.startswith('freebsd'):
        import shutil
        source_bin = initDreplace()
        initd_bin = getInitDFile()
        shutil.copyfile(source_bin, initd_bin)
        yf.execShell('chmod +x ' + initd_bin)
        yf.execShell('sysrc ' + getPluginName() + '_enable="YES"')
        return 'ok'

    yf.execShell('systemctl enable caddy')
    return 'ok'


def initdUinstall():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile()
        os.remove(initd_bin)
        yf.execShell('sysrc ' + getPluginName() + '_enable="NO"')
        return 'ok'

    yf.execShell('systemctl disable caddy')
    return 'ok'


def runInfo():
    op_status = status()
    if op_status == 'stop':
        return yf.returnJson(False, "未启动!")


def errorLogPath():
    return getServerDir() + '/nginx/logs/error.log'


def getCfg():
    cfg = getConf()
    content = yf.readFile(cfg)

    unitrep = "[kmgKMG]"
    cfg_args = [
        {"name": "worker_processes", "ps": "处理进程,auto表示自动,数字表示进程数", 'type': 2},
        {"name": "worker_connections", "ps": "最大并发链接数", 'type': 2},
        {"name": "keepalive_timeout", "ps": "连接超时时间", 'type': 2},
        {"name": "zstd", "ps": "是否开启zstd压缩传输", 'type': 1},
        {"name": "brotli", "ps": "是否开启brotli压缩传输", 'type': 1},
        {"name": "gzip", "ps": "是否开启gzip压缩传输", 'type': 1},
        {"name": "gzip_min_length", "ps": "最小压缩文件", 'type': 2},
        {"name": "gzip_comp_level", "ps": "压缩率", 'type': 2},
        {"name": "client_max_body_size", "ps": "最大上传文件", 'type': 2},
        {"name": "server_names_hash_bucket_size",
            "ps": "服务器名字的hash表大小", 'type': 2},
        {"name": "client_header_buffer_size", "ps": "客户端请求头buffer大小", 'type': 2},
    ]

    # {"name": "client_body_buffer_size", "ps": "请求主体缓冲区"}
    rdata = []
    for i in cfg_args:
        rep = r"(%s)\s+(\w+)" % i["name"]
        k = re.search(rep, content)
        if not k:
            return yf.returnJson(False, "获取 key {} 失败".format(k))
        k = k.group(1)
        v = re.search(rep, content)
        if not v:
            return yf.returnJson(False, "获取 value {} 失败".format(v))
        v = v.group(2)

        if re.search(unitrep, v):
            u = str.upper(v[-1])
            v = v[:-1]
            if len(u) == 1:
                psstr = u + "B，" + i["ps"]
            else:
                psstr = u + "，" + i["ps"]
        else:
            u = ""

        kv = {"name": k, "value": v, "unit": u,
              "ps": i["ps"], "type": i["type"]}
        rdata.append(kv)

    return yf.returnJson(True, "ok", rdata)

def replaceChar(value, index, new_char):
    return value[:index] + new_char + value[index+1:]

def makeWorkerCpuAffinity(val):
    if val == "auto":
        return "auto"

    if yf.isNumber(val):
        core_num = int(val)
        default_core_str = "0"*core_num
        core_num_arr = []
        for x in range(core_num):
            t = replaceChar(default_core_str, x , "1")
            core_num_arr.append(t)
        return " ".join(core_num_arr)

    return 'auto'

def setCfg():

    args = getArgs()
    data = checkArgs(args, [
        'worker_processes', 'worker_connections', 'keepalive_timeout','zstd','brotli',
        'gzip', 'gzip_min_length', 'gzip_comp_level', 'client_max_body_size',
        'server_names_hash_bucket_size', 'client_header_buffer_size'
    ])
    if not data[0]:
        return data[1]

    cfg = getConf()
    yf.backFile(cfg)
    content = yf.readFile(cfg)

    unitrep = "[kmgKMG]"
    cfg_args = [
        {"name": "worker_processes", "ps": "处理进程,auto表示自动,数字表示进程数", 'type': 2},
        {"name": "worker_connections", "ps": "最大并发链接数", 'type': 2},
        {"name": "keepalive_timeout", "ps": "连接超时时间", 'type': 2},
        {"name": "zstd", "ps": "是否开启zstd压缩传输", 'type': 1},
        {"name": "brotli", "ps": "是否开启brotli压缩传输", 'type': 1},
        {"name": "gzip", "ps": "是否开启压缩传输", 'type': 1},
        {"name": "gzip_min_length", "ps": "最小压缩文件", 'type': 2},
        {"name": "gzip_comp_level", "ps": "压缩率", 'type': 2},
        {"name": "client_max_body_size", "ps": "最大上传文件", 'type': 2},
        {"name": "server_names_hash_bucket_size",
            "ps": "服务器名字的hash表大小", 'type': 2},
        {"name": "client_header_buffer_size", "ps": "客户端请求头buffer大小", 'type': 2},
    ]

    # print(args)
    for k, v in args.items():
        # print(k, v)
        rep = r"%s\s+[^kKmMgG\;\n]+" % k
        if k == "worker_processes" or k == "gzip":
            if not re.search(r"auto|on|off|\d+", v):
                return yf.returnJson(False, '参数值错误')
        elif k == "zstd" or k == "brotli":
            if not re.search(r"auto|on|off|\d+", v):
                return yf.returnJson(False, '参数值错误')
        else:
            if not re.search(r"\d+", v):
                return yf.returnJson(False, '参数值错误,请输入数字整数')

        if k == "worker_processes" :
            k_wca = "worker_cpu_affinity"
            rep_wca = r"%s\s+[^\;\n]+" % k_wca
            v_wca = makeWorkerCpuAffinity(v)
            newconf = "%s %s" % (k_wca, v_wca)
            content = re.sub(rep_wca, newconf, content)


        if re.search(rep, content):
            newconf = "%s %s" % (k, v)
            content = re.sub(rep, newconf, content)
        elif re.search(rep, content):
            newconf = "%s %s" % (k, v)
            content = re.sub(rep, newconf, content)

    yf.writeFile(cfg, content)
    isError = yf.checkWebConfig()
    if (isError != True):
        yf.restoreFile(cfg)
        return yf.returnJson(False, 'ERROR: 配置出错<br><a style="color:red;">' + isError.replace("\n", '<br>') + '</a>')

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

    version = '1.27.1'
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
