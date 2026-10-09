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
import logging

_log = logging.getLogger('yf.openresty')

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'openresty'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getRestyBin():
    return getServerDir() + '/nginx/sbin/nginx'


def isInstalled():
    # 判据用主程序 nginx 是否存在，而不是安装目录是否存在：confReplace() 会写出
    # nginx/conf/nginx.conf，让空目录看起来「已安装」，随后 initDreplace 就在没有
    # 二进制的情况下伪造出 init.d 脚本与 systemd unit（与 C01 apache 同源缺陷）。
    return os.path.exists(getRestyBin())


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
    # 旧实现的 `k:v` 回退在畸形 argv（无冒号 / 非对象）上直接 IndexError，整段
    # traceback 回给前端；version 单独成 argv 时也会被误当参数。
    args = sys.argv[2:]
    tmp = {}
    for raw in args:
        val = str(raw).strip()
        if not val:
            continue
        if val.startswith('{') and val.endswith('}'):
            try:
                parsed = json.loads(val)
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                tmp.update({str(k).strip(): str(v).strip() for k, v in parsed.items()})
                continue
        parts = val.strip('{').strip('}').split(':', 1)
        if len(parts) == 2:
            k = parts[0].strip().strip('"').strip("'").strip('\\')
            v = parts[1].strip().strip('"').strip("'").strip('\\')
            if k:
                tmp[k] = v
    return tmp


def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


def clearTemp():
    path_bin = getServerDir() + "/nginx"
    yf.removeDir(path_bin + '/client_body_temp')
    yf.removeDir(path_bin + '/fastcgi_temp')
    yf.removeDir(path_bin + '/proxy_temp')
    yf.removeDir(path_bin + '/scgi_temp')
    yf.removeDir(path_bin + '/uwsgi_temp')


def getConf():
    path = getServerDir() + "/nginx/conf/nginx.conf"
    return path


def healGzipConf(content):
    need_write = False
    # 1. 升级/补齐 gzip_proxied any;
    proxied_pattern = r'gzip_proxied\s+[^;\n\r]+;'
    if re.search(proxied_pattern, content):
        if not re.search(r'gzip_proxied\s+any\s*;', content):
            content = re.sub(proxied_pattern, 'gzip_proxied   any;', content)
            need_write = True
    elif re.search(r'\bgzip\s+(on|off)\s*;', content):
        content = re.sub(r'(\bgzip\s+(?:on|off)\s*;)', r'\1\n    gzip_proxied   any;', content, count=1)
        need_write = True

    # 2. 补齐 gzip_static on;
    if not re.search(r'\bgzip_static\s+(on|off|always)\s*;', content):
        if re.search(r'gzip_proxied\s+any\s*;', content):
            content = re.sub(r'(gzip_proxied\s+any\s*;)', r'\1\n    gzip_static    on;', content, count=1)
            need_write = True
        elif re.search(r'\bgzip\s+(on|off)\s*;', content):
            content = re.sub(r'(\bgzip\s+(?:on|off)\s*;)', r'\1\n    gzip_static    on;', content, count=1)
            need_write = True

    return content, need_write


def confSelfHeal():
    try:
        conf_file = getConf()
        if os.path.exists(conf_file):
            content = yf.readFile(conf_file)
            need_write = False
            
            # 智能将 error_log 级别从 cri/crit 修正并升级为通用且利于诊断 of error;，杜绝崩溃日志被高过滤遮蔽
            pattern = r'(error_log\s+[^;;\n\r]+?)\b(cri|crit)\b\s*;?'
            if re.search(pattern, content):
                content = re.sub(pattern, r'\1error;', content)
                need_write = True

            # 智能升级与补齐 Gzip 代理传输及预压缩静态文件优化配置
            content, gzip_healed = healGzipConf(content)
            if gzip_healed:
                need_write = True
                
            if need_write:
                yf.writeFile(conf_file, content)
        
        # 执行目录权限与属主自愈，防止降权到 www 后 worker 进程写入 logs/temp 失败崩溃
        directoryPermissionSelfHeal()

        # 深度解耦自愈：若 OP 高性能防火墙 (OpenStar) 未安装或已被物理删除，则在此自动清理残留挂载，以杜绝 dofile init.lua 失败导致 OpenResty 启动崩溃
        openstar_dir = yf.getServerDir() + '/openstar'
        lua_conf_dir = yf.getServerDir() + '/web_conf/nginx/lua'
        if not os.path.exists(openstar_dir):
            openstar_removes = [
                os.path.join(lua_conf_dir, 'init_by_lua_file', 'openstar_init_preload.lua'),
                os.path.join(lua_conf_dir, 'init_worker_by_lua_file', 'openstar_init_worker.lua'),
                os.path.join(lua_conf_dir, 'access_by_lua_file', 'openstar_access.lua'),
                yf.getServerDir() + '/web_conf/nginx/vhost/openstar.conf'
            ]
            need_remake = False
            for r_path in openstar_removes:
                if os.path.exists(r_path):
                    try:
                        os.remove(r_path)
                        need_remake = True
                    except Exception as e:
                        _log.debug('[openresty] confSelfHeal 异常已忽略: %s', e)
            if need_remake:
                yf.opLuaMakeAll()
    except Exception as e:
        _log.debug('[openresty] confSelfHeal 异常已忽略: %s', e)


def directoryPermissionSelfHeal():
    try:
        user = 'www'
        user_group = 'www'
        
        # 兼容 macOS/FreeBSD 等非 Linux 系统
        current_os = yf.getOs()
        if current_os == 'darwin':
            user = 'root'
            user_group = 'staff'
            
        nginx_dir = getServerDir() + "/nginx"
        if os.path.exists(nginx_dir):
            # 定义所有降权后必须可写的 temp 与 log 目录
            target_dirs = [
                nginx_dir + "/logs",
                nginx_dir + "/client_body_temp",
                nginx_dir + "/fastcgi_temp",
                nginx_dir + "/proxy_temp",
                nginx_dir + "/scgi_temp",
                nginx_dir + "/uwsgi_temp",
                nginx_dir + "/proxy_cache_temp",
                nginx_dir + "/fastcgi_cache_temp"
            ]
            for d in target_dirs:
                if not os.path.exists(d):
                    os.makedirs(d, exist_ok=True)
                
                # 递归地将属主赋予 www:www，并赋予 755 读写执行权限
                yf.execShell(f"chown -R {user}:{user_group} {d}")
                yf.execShell(f"chmod -R 755 {d}")

            # 自动计算并加固全局站点日志目录 wwwlogs，防止虚拟主机因无写权限闪退且无 error.log 记录
            try:
                wwwlogs_dir = os.path.abspath(yf.getServerDir() + "/../wwwlogs")
                if not os.path.exists(wwwlogs_dir):
                    os.makedirs(wwwlogs_dir, exist_ok=True)
                yf.execShell(f"chown -R {user}:{user_group} {wwwlogs_dir}")
                yf.execShell(f"chmod -R 755 {wwwlogs_dir}")
            except Exception as _e:
                _log.debug('[openresty] directoryPermissionSelfHeal 异常已忽略: %s', _e)
    except Exception as e:
        _log.debug('[openresty] directoryPermissionSelfHeal 异常已忽略: %s', e)


def getPortPid(port=80):
    try:
        # 优先使用 ss
        res = yf.execShell("ss -tpln")
        if res[0] == '' or res[1] != '':
            res = yf.execShell("netstat -tpln")
        
        # 匹配监听指定端口的行，例如 :80 
        lines = res[0].split('\n')
        for line in lines:
            if (':%s ' % port) in line or (':%s\t' % port) in line or ('.:%s ' % port) in line:
                # ss 匹配 pid
                pid_match = re.search(r'pid=(\d+)', line)
                if pid_match:
                    return int(pid_match.group(1))
                # netstat 匹配 pid
                pid_match_ns = re.search(r'(\d+)/[\w.-]+', line)
                if pid_match_ns:
                    return int(pid_match_ns.group(1))
    except Exception as e:
        _log.debug('[openresty] getPortPid 异常已忽略: %s', e)
    return None


def getProcessName(pid):
    try:
        comm_file = f"/proc/{pid}/comm"
        if os.path.exists(comm_file):
            return yf.readFile(comm_file).strip()
    except Exception as _e:
        _log.debug('[openresty] getProcessName 异常已忽略: %s', _e)
    return "unknown"


def getSystemdErrorDetail():
    detail = ""
    try:
        res = yf.execShell("journalctl -n 20 -u openresty --no-pager")
        if res[0] != '':
            detail += "\n[系统服务日志明细]:\n" + res[0]
    except Exception as _e:
        _log.debug('[openresty] getSystemdErrorDetail 异常已忽略: %s', _e)

    try:
        err_log_file = getServerDir() + '/nginx/logs/error.log'
        if os.path.exists(err_log_file):
            log_content = yf.readFile(err_log_file)
            if log_content:
                lines = log_content.strip().split('\n')
                last_lines = lines[-20:]
                detail += "\n[OpenResty 错误日志明细 (error.log)]:\n" + "\n".join(last_lines)
    except Exception as _e:
        _log.debug('[openresty] getSystemdErrorDetail 异常已忽略: %s', _e)

    return detail


def getConfTpl():
    path = getPluginDir() + '/conf/nginx.conf'
    return path


def checkModuleSupport(module_name):
    ng_exe = getServerDir() + "/nginx/sbin/nginx"
    if not os.path.exists(ng_exe):
        return False
    try:
        import subprocess
        p = subprocess.Popen([ng_exe, "-V"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        conf_str = (out.decode('utf-8', errors='ignore') + err.decode('utf-8', errors='ignore')).lower()
        return module_name.lower() in conf_str
    except Exception as e:
        return False


def getOs():
    data = {}
    data['os'] = yf.getOs()
    ng_exe_bin = getServerDir() + "/nginx/sbin/nginx"

    # if yf.isAppleSystem():
    #     data['auth'] = True
    #     return yf.getJson(data)

    if checkAuthEq(ng_exe_bin, 'root'):
        data['auth'] = True
    else:
        data['auth'] = False
    return yf.getJson(data)


def getInitDTpl():
    path = getPluginDir() + "/init.d/nginx.tpl"
    return path


def getPidFile():
    file = getConf()
    content = yf.readFile(file)
    # yf.readFile 读不到返回 False（不是空串），且配置里可能没有 pid 指令，
    # 旧实现两处都会抛异常（TypeError / AttributeError）回给前端。
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

    user = 'www'
    user_group = 'www'

    current_os = yf.getOs()
    if current_os == 'darwin':
        # macosx do
        import getpass
        try:
            user = os.environ.get('SUDO_USER') or getpass.getuser()
        except Exception:
            user = 'root'
        user_group = 'staff'
        content = content.replace('{$EVENT_MODEL}', 'kqueue')
    elif current_os.startswith('freebsd'):
        content = content.replace('{$EVENT_MODEL}', 'kqueue')
    else:
        content = content.replace('{$EVENT_MODEL}', 'epoll')

    content = content.replace('{$OS_USER}', user)
    content = content.replace('{$OS_USER_GROUP}', user_group)

    # 模块支持自适应安全检测：若当前二进制未编译 brotli 或 zstd 模块，自动安全降级为 off，防启动崩溃
    if not checkModuleSupport('brotli'):
        content = re.sub(r'brotli\s+on\s*;', 'brotli off;', content)
    if not checkModuleSupport('zstd'):
        content = re.sub(r'zstd\s+on\s*;', 'zstd off;', content)

    # 主配置文件
    nconf = getServerDir() + '/nginx/conf/nginx.conf'
    yf.writeFile(nconf, content)

    # lua配置
    lua_conf_dir = yf.getServerDir() + '/web_conf/nginx/lua'
    if not os.path.exists(lua_conf_dir):
        yf.makeDirs(lua_conf_dir)

    lua_conf = lua_conf_dir + '/lua.conf'
    lua_conf_tpl = getPluginDir() + '/conf/lua.conf'
    lua_content = yf.readFile(lua_conf_tpl)
    lua_content = lua_content.replace('{$SERVER_PATH}', service_path)
    yf.writeFile(lua_conf, lua_content)

    empty_lua = lua_conf_dir + '/empty.lua'
    if not os.path.exists(empty_lua):
        yf.writeFile(empty_lua, '')

    # 物理清除废弃防火墙 op_waf 残留挂载文件及配置，防止未物理清理彻底时失效的 require 模块阻碍正常启动
    opwaf_removes = [
        os.path.join(lua_conf_dir, 'access_by_lua_file', 'opwaf_init.lua'),
        os.path.join(lua_conf_dir, 'init_worker_by_lua_file', 'opwaf_init_worker.lua'),
        os.path.join(lua_conf_dir, 'init_by_lua_file', 'waf_init_preload.lua'),
        yf.getServerDir() + '/web_conf/nginx/vhost/opwaf.conf'
    ]
    for r_path in opwaf_removes:
        if os.path.exists(r_path):
            try:
                os.remove(r_path)
            except Exception as e:
                _log.debug('[openresty] confReplace 异常已忽略: %s', e)

    # 深度解耦自愈：若 OP 高性能防火墙 (OpenStar) 未安装或已被物理删除，则在此自动清理残留挂载，以杜绝 dofile init.lua 失败导致 OpenResty 启动崩溃
    openstar_dir = yf.getServerDir() + '/openstar'
    if not os.path.exists(openstar_dir):
        openstar_removes = [
            os.path.join(lua_conf_dir, 'init_by_lua_file', 'openstar_init_preload.lua'),
            os.path.join(lua_conf_dir, 'init_worker_by_lua_file', 'openstar_init_worker.lua'),
            os.path.join(lua_conf_dir, 'access_by_lua_file', 'openstar_access.lua'),
            yf.getServerDir() + '/web_conf/nginx/vhost/openstar.conf'
        ]
        for r_path in openstar_removes:
            if os.path.exists(r_path):
                try:
                    os.remove(r_path)
                except Exception as e:
                    _log.debug('[openresty] confReplace 异常已忽略: %s', e)

    yf.opLuaMakeAll()

    # 静态配置
    php_conf = yf.getServerDir() + '/web_conf/php/conf'
    if not os.path.exists(php_conf):
        yf.makeDirs(php_conf)
    static_conf = yf.getServerDir() + '/web_conf/php/conf/enable-php-00.conf'
    if not os.path.exists(static_conf):
        yf.writeFile(static_conf, 'set $PHP_ENV 0;')

    # vhost
    vhost_dir = yf.getServerDir() + '/web_conf/nginx/vhost'
    vhost_tpl_dir = getPluginDir() + '/conf/vhost'
    if not os.path.exists(vhost_dir):
        yf.makeDirs(vhost_dir)

    vhost_list = ['0.websocket.conf', '0.nginx_status.conf']
    for f in vhost_list:
        a_conf = vhost_dir + '/' + f
        a_conf_tpl = vhost_tpl_dir + '/' + f
        if not os.path.exists(a_conf):
            yf.writeFile(a_conf, yf.readFile(a_conf_tpl))

    # copy resty lib
    src_resty_dir = getPluginDir()+'/resty/*'
    dst_resty_dir = getServerDir()+'/lualib/resty'
    yf.execShell('cp -rf ' + src_resty_dir + ' ' + dst_resty_dir)
    return True


def initDreplace():

    file_tpl = getInitDTpl()
    service_path = yf.getServerDir()

    initD_path = getServerDir() + '/init.d'

    # openresty 未安装：不得伪造安装产物（init.d 脚本 / systemd unit）。旧实现在这里
    # `print("ok"); exit(0)` —— start/stop/restart 对未安装的 openresty 也回 ok（假启动），
    # 而 reload 会先经 confReplace 建出 nginx/conf 目录，再一路生成 systemd unit。
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

    # give nginx root permission
    ng_exe_bin = getRestyBin()
    if not checkAuthEq(ng_exe_bin, 'root'):
        user = 'www'
        user_group = 'www'
        current_os = yf.getOs()
        if current_os == 'darwin':
            user = 'root'
            user_group = 'staff'
        args = getArgs()
        if not 'pwd' in args:
            print("权限不足，需要认证启动!")
            exit(0)

        sudoPwd = args['pwd']
        cmd_own = 'chown -R ' + user+':' + user_group + ' ' + ng_exe_bin
        # 密码来自前端/插件 args，必须 shell 转义：旧写法直接 `echo %s|sudo -S %s`
        # 拼进 shell，`pwd` 传 `x; touch /tmp/pwned #` 就能以 root 执行任意命令。
        safe_pwd = yf.shlexQuote(sudoPwd)
        yf.execShell('echo %s|sudo -S %s' % (safe_pwd, cmd_own))
        cmd_mod = 'chmod 755 ' + ng_exe_bin
        yf.execShell('echo %s|sudo -S %s' % (safe_pwd, cmd_mod))
        cmd_s = 'chmod u+s ' + ng_exe_bin
        yf.execShell('echo %s|sudo -S %s' % (safe_pwd, cmd_s))

    # systemd
    # /usr/lib/systemd/system
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/openresty.service'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        systemServiceTpl = getPluginDir() + '/init.d/openresty.service.tpl'
        se_content = yf.readFile(systemServiceTpl)
        if not se_content:
            return None
        se_content = se_content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(systemService, se_content)
        yf.execShell('systemctl daemon-reload')

    return file_bin


def status():
    pid_file = getPidFile()
    if not pid_file or not os.path.exists(pid_file):
        return 'stop'
    # pid 文件在进程被强杀后会残留：必须确认该 pid 真的还活着，否则界面会显示
    # 「运行中」而实际已停（假阳性），用户也无法再启动。
    try:
        pid = int(str(yf.readFile(pid_file)).strip())
    except (TypeError, ValueError):
        return 'stop'
    if pid <= 0:
        return 'stop'
    if os.path.isdir('/proc'):
        return 'start' if os.path.exists('/proc/%d' % pid) else 'stop'
    rc, _out, _err = yf.execShellRc('kill -0 %d' % pid)
    return 'start' if rc == 0 else 'stop'


def restyOp(method):
    if not isInstalled():
        return 'ERROR: openresty 未安装'

    # 执行配置语法自愈，杜绝常见语法损坏阻碍启动
    confSelfHeal()

    # 在启动、重启或重载时，智能检查端口冲突并自愈
    if method in ['start', 'restart', 'reload']:
        port = 80
        pid = getPortPid(port)
        if pid:
            pname = getProcessName(pid)
            if pname in ['nginx', 'openresty']:
                # 发现脱管残留的孤儿 nginx/openresty，强退释放端口
                yf.execShell(f"kill -9 {pid}")
                time.sleep(0.5)
            else:
                # 被其他服务占用，返回友好而清晰的错误
                return f"ERROR: 端口 {port} 已被服务 [{pname}] (PID: {pid}) 占用。请先停用该服务后再启动 OpenResty！"

    file = initDreplace()
    if not file:
        return 'ERROR: openresty 初始化脚本模板缺失'

    # 启动时,先检查一下配置文件
    check = getRestyBin() + " -t"
    check_data = yf.execShell(check)
    if not check_data[1].find('test is successful') > -1:
        return check_data[1]

    current_os = yf.getOs()
    if current_os == "darwin":
        data = yf.execShell(file + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    if current_os.startswith("freebsd"):
        data = yf.execShell('service openresty ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    data = yf.execShell('systemctl ' + method + ' openresty')
    if data[1] == '':
        return 'ok'
    
    # 启动失败时追加最详尽的日志细节，让用户秒懂错误原因
    err_detail = getSystemdErrorDetail()
    return data[1] + "\n" + err_detail


def op_submit_systemctl_restart():
    current_os = yf.getOs()
    if current_os.startswith("freebsd"):
        yf.execShell('service openresty restart')
        return True

    yf.execShell('systemctl restart openresty')
    return True


def op_submit_init_restart(file):
    yf.execShell(file + ' restart')


def restyOp_restart():
    if not isInstalled():
        return 'ERROR: openresty 未安装'

    # 执行配置语法自愈，杜绝常见语法损坏阻碍启动
    confSelfHeal()
    file = initDreplace()
    if not file:
        return 'ERROR: openresty 初始化脚本模板缺失'

    # 启动时,先检查一下配置文件
    check = getRestyBin() + " -t"
    check_data = yf.execShell(check)
    if not check_data[1].find('test is successful') > -1:
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
    pid_file = getPidFile()
    if pid_file and os.path.exists(pid_file):
        os.remove(pid_file)
    return r


def restart():
    return restyOp_restart()


def reload():
    if not isInstalled():
        return 'ERROR: openresty 未安装'
    if not confReplace():
        return 'ERROR: openresty 配置文件模板缺失'
    return restyOp('reload')


def initdStatus():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile()
        if os.path.exists(initd_bin):
            return 'ok'

    # `systemctl status | grep loaded | grep "enabled;"` 依赖人类可读输出（语言/格式一变
    # 就误判），改用 systemctl is-enabled 的退出码 + 单字输出判定开机自启。
    rc, out, _err = yf.execShellRc('systemctl is-enabled openresty')
    if rc == 0 and out.strip().startswith('enabled'):
        return 'ok'
    return 'fail'


def initdInstall():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if not isInstalled():
        return 'ERROR: openresty 未安装'

    # freebsd initd install
    if current_os.startswith('freebsd'):
        import shutil
        source_bin = initDreplace()
        if not source_bin:
            return 'ERROR: openresty 初始化脚本模板缺失'
        initd_bin = getInitDFile()
        shutil.copyfile(source_bin, initd_bin)
        yf.execShell('chmod +x ' + initd_bin)
        yf.execShell('sysrc ' + getPluginName() + '_enable="YES"')
        return 'ok'

    rc, out, err = yf.execShellRc('systemctl enable openresty')
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
        yf.execShell('sysrc ' + getPluginName() + '_enable="NO"')
        return 'ok'

    rc, out, err = yf.execShellRc('systemctl disable openresty')
    if rc != 0:
        return 'ERROR: 取消开机自启失败: ' + (err or out)
    return 'ok'

def getNgxStatusPort():
    ngx_status_file = yf.getServerDir() + '/web_conf/nginx/vhost/0.nginx_status.conf'
    content = yf.readFile(ngx_status_file)
    if not content:
        return None
    rep = r'listen\s*(.*);'
    tmp = re.search(rep, content)
    if not tmp:
        return None
    port =  tmp.groups()[0].strip()
    return port


def runInfo():
    op_status = status()
    if op_status == 'stop':
        return yf.returnJson(False, "未启动!")

    port = getNgxStatusPort()
    if not port:
        return yf.returnJson(False, "oprenresty异常!")
    # 取Openresty负载状态
    try:
        url = 'http://127.0.0.1:%s/nginx_status' % port
        result = yf.httpGet(url, timeout=3)
        tmp = result.split()
        data = {}
        data['active'] = tmp[2]
        data['accepts'] = tmp[9]
        data['handled'] = tmp[7]
        data['requests'] = tmp[8]
        data['Reading'] = tmp[11]
        data['Writing'] = tmp[13]
        data['Waiting'] = tmp[15]
        return yf.getJson(data)
    except Exception as e:
        try:
            url = 'http://' + yf.getHostAddr() + ':%s/nginx_status' % port
            result = yf.httpGet(url)
            tmp = result.split()
            data = {}
            data['active'] = tmp[2]
            data['accepts'] = tmp[9]
            data['handled'] = tmp[7]
            data['requests'] = tmp[8]
            data['Reading'] = tmp[11]
            data['Writing'] = tmp[13]
            data['Waiting'] = tmp[15]
            return yf.getJson(data)
        except Exception as e:
            return yf.returnJson(False, "oprenresty异常!")
        
    except Exception as e:
        return yf.returnJson(False, "oprenresty not started!")


def errorLogPath():
    return getServerDir() + '/nginx/logs/error.log'


def getCfg():
    cfg = getConf()
    content = yf.readFile(cfg)
    # yf.readFile 读不到返回 False（不是空串），旧实现直接 re.search(pattern, False)
    # → TypeError，整段 traceback 回给前端。
    if not content:
        return yf.returnJson(False, 'openresty 未安装或配置文件不存在!')

    # 检测模块支持情况
    has_zstd = checkModuleSupport('zstd')
    has_brotli = checkModuleSupport('brotli')

    unitrep = "[kmgKMG]"
    cfg_args = [
        {"name": "worker_processes", "ps": "处理进程,auto表示自动,数字表示进程数", 'type': 2, 'default': 'auto'},
        {"name": "worker_connections", "ps": "最大并发链接数", 'type': 2, 'default': '51200'},
        {"name": "keepalive_timeout", "ps": "连接超时时间", 'type': 2, 'default': '60'},
        {"name": "zstd", "ps": "是否开启zstd压缩传输" + ("" if has_zstd else "(当前OpenResty未编译此模块，不支持)"), 'type': 1, 'default': 'off'},
        {"name": "brotli", "ps": "是否开启brotli压缩传输" + ("" if has_brotli else "(当前OpenResty未编译此模块，不支持)"), 'type': 1, 'default': 'on'},
        {"name": "gzip", "ps": "是否开启gzip压缩传输", 'type': 1, 'default': 'on'},
        {"name": "gzip_min_length", "ps": "最小压缩文件", 'type': 2, 'default': '1k'},
        {"name": "gzip_comp_level", "ps": "压缩率", 'type': 2, 'default': '6'},
        {"name": "client_max_body_size", "ps": "最大上传文件", 'type': 2, 'default': '20m'},
        {"name": "server_names_hash_bucket_size",
            "ps": "服务器名字的hash表大小", 'type': 2, 'default': '64'},
        {"name": "client_header_buffer_size", "ps": "客户端请求头buffer大小", 'type': 2, 'default': '32k'},
    ]

    # {"name": "client_body_buffer_size", "ps": "请求主体缓冲区"}
    rdata = []
    for i in cfg_args:
        rep = r"(%s)\s+(\w+)" % i["name"]
        k = re.search(rep, content)
        if not k:
            k_val = i["name"]
            v_val = i.get('default', '')
        else:
            k_val = k.group(1)
            v_val = k.group(2)

        if re.search(unitrep, v_val):
            u = str.upper(v_val[-1])
            v_show = v_val[:-1]
            if len(u) == 1:
                psstr = u + "B，" + i["ps"]
            else:
                psstr = u + "，" + i["ps"]
        else:
            u = ""
            v_show = v_val

        kv = {"name": k_val, "value": v_show, "unit": u,
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
    content = yf.readFile(cfg)
    if not content:
        return yf.returnJson(False, 'openresty 未安装或配置文件不存在!')
    yf.backFile(cfg)

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

    # 每个调优项的值形态：worker_processes 允许 auto，压缩开关只允许 on/off，
    # 其余一律纯数字（单位由前端单独展示，不进值里）。
    value_rules = {
        'worker_processes': r'^(auto|\d+)$',
        'worker_connections': r'^\d+$',
        'keepalive_timeout': r'^\d+$',
        'zstd': r'^(on|off)$',
        'brotli': r'^(on|off)$',
        'gzip': r'^(on|off)$',
        'gzip_min_length': r'^\d+$',
        'gzip_comp_level': r'^\d+$',
        'client_max_body_size': r'^\d+$',
        'server_names_hash_bucket_size': r'^\d+$',
        'client_header_buffer_size': r'^\d+$',
    }
    switch_keys = ('worker_processes', 'gzip', 'zstd', 'brotli')

    # print(args)
    for k, v in args.items():
        k = str(k).strip()
        v = str(v).strip()
        # 参数名白名单：旧实现把任意键直接拼进 re.sub 的正则（正则注入面），
        # 未知键还会被无脑写进配置。
        if k not in value_rules:
            continue
        # 值必须匹配该项的严格形态：旧实现只要求「含数字」，放行 `60;\n# ...`
        # 这类换行注入（真机实测被原样写进 nginx.conf 并 reload）。
        if not re.match(value_rules[k], v):
            if k in switch_keys:
                return yf.returnJson(False, '参数值错误')
            return yf.returnJson(False, '参数值错误,请输入数字整数')

        rep = r"%s\s+[^kKmMgG\;\n]+" % re.escape(k)

        # 如果是 zstd 或 brotli，且当前 OpenResty 没有编译对应的模块，且原配置文件里没有这一项，直接忽略不处理，杜绝 Nginx 无法启动报错
        if k == "zstd" and not checkModuleSupport('zstd'):
            if not re.search(rep, content):
                continue
        if k == "brotli" and not checkModuleSupport('brotli'):
            if not re.search(rep, content):
                continue

        if k == "worker_processes" :
            k_wca = "worker_cpu_affinity"
            rep_wca = r"%s\s+[^\;\n]+" % k_wca
            v_wca = makeWorkerCpuAffinity(v)
            if re.search(rep_wca, content):
                newconf = "%s %s" % (k_wca, v_wca)
                content = re.sub(rep_wca, newconf, content)
            else:
                content = "worker_cpu_affinity %s;\n" % v_wca + content

        if re.search(rep, content):
            newconf = "%s %s" % (k, v)
            content = re.sub(rep, newconf, content)
        else:
            # 原配置文件不存在此项，自动按区域优雅补齐
            if k == "worker_processes":
                content = "worker_processes %s;\n" % v + content
            elif k == "worker_connections":
                # 写入 events 块中
                content = re.sub(r'(events\s*\{)', r'\1\n    worker_connections %s;' % v, content, 1)
            else:
                # 其他参数（如 zstd, brotli, gzip等）写入 http 块中
                content = re.sub(r'(http\s*\{)', r'\1\n    %s %s;' % (k, v), content, 1)

    # 智能检查与优化 Gzip 代理响应和静态预压缩配置
    content, _ = healGzipConf(content)

    yf.writeFile(cfg, content)
    isError = yf.checkWebConfig()
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
        return yf.returnJson(False, '添加检查任务失败: ' + str(e))


def cronDelCheck():
    try:
        import tool_task
        tool_task.removeBgTask()
        return yf.returnJson(True, '删除检查任务成功')
    except Exception as e:
        return yf.returnJson(False, '删除检查任务失败: ' + str(e))


def cronStatus():
    try:
        import tool_task
        is_active, task_id, status = tool_task.checkBgTaskStatus()
        return yf.returnJson(True, 'ok', {
            'is_active': is_active,
            'task_id': task_id,
            'status': status
        })
    except Exception as e:
        return yf.returnJson(False, str(e), {
            'is_active': False,
            'task_id': -1,
            'status': 0
        })


def cronCheck():
    return cronStatus()


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
    elif func == 'cron_status':
        print(cronStatus())
    elif func == 'cron_add_check':
        print(cronAddCheck())
    elif func == 'cron_del_check':
        print(cronDelCheck())
    else:
        print('error')
