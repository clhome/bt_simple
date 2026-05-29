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
if mw.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'openresty'


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
            return (False, mw.returnJson(False, '参数:(' + ck[i] + ')没有!'))
    return (True, mw.returnJson(True, 'ok'))


def clearTemp():
    path_bin = getServerDir() + "/nginx"
    mw.execShell('rm -rf ' + path_bin + '/client_body_temp')
    mw.execShell('rm -rf ' + path_bin + '/fastcgi_temp')
    mw.execShell('rm -rf ' + path_bin + '/proxy_temp')
    mw.execShell('rm -rf ' + path_bin + '/scgi_temp')
    mw.execShell('rm -rf ' + path_bin + '/uwsgi_temp')


def getConf():
    path = getServerDir() + "/nginx/conf/nginx.conf"
    return path


def confSelfHeal():
    try:
        conf_file = getConf()
        if os.path.exists(conf_file):
            content = mw.readFile(conf_file)
            need_write = False
            
            # 智能将 error_log 级别从 cri/crit 修正并升级为通用且利于诊断 of error;，杜绝崩溃日志被高过滤遮蔽
            pattern = r'(error_log\s+[^;;\n\r]+?)\b(cri|crit)\b\s*;?'
            if re.search(pattern, content):
                content = re.sub(pattern, r'\1error;', content)
                need_write = True
                
            if need_write:
                mw.writeFile(conf_file, content)
        
        # 执行目录权限与属主自愈，防止降权到 www 后 worker 进程写入 logs/temp 失败崩溃
        directoryPermissionSelfHeal()

        # 深度解耦自愈：若 OP 高性能防火墙 (OpenStar) 未安装或已被物理删除，则在此自动清理残留挂载，以杜绝 dofile init.lua 失败导致 OpenResty 启动崩溃
        openstar_dir = mw.getServerDir() + '/openstar'
        lua_conf_dir = mw.getServerDir() + '/web_conf/nginx/lua'
        if not os.path.exists(openstar_dir):
            openstar_removes = [
                os.path.join(lua_conf_dir, 'init_by_lua_file', 'openstar_init_preload.lua'),
                os.path.join(lua_conf_dir, 'init_worker_by_lua_file', 'openstar_init_worker.lua'),
                os.path.join(lua_conf_dir, 'access_by_lua_file', 'openstar_access.lua'),
                mw.getServerDir() + '/web_conf/nginx/vhost/openstar.conf'
            ]
            need_remake = False
            for r_path in openstar_removes:
                if os.path.exists(r_path):
                    try:
                        os.remove(r_path)
                        need_remake = True
                    except Exception as e:
                        pass
            if need_remake:
                mw.opLuaMakeAll()
    except Exception as e:
        pass


def directoryPermissionSelfHeal():
    try:
        user = 'www'
        user_group = 'www'
        
        # 兼容 macOS/FreeBSD 等非 Linux 系统
        current_os = mw.getOs()
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
                mw.execShell(f"chown -R {user}:{user_group} {d}")
                mw.execShell(f"chmod -R 755 {d}")

            # 自动计算并加固全局站点日志目录 wwwlogs，防止虚拟主机因无写权限闪退且无 error.log 记录
            try:
                wwwlogs_dir = os.path.abspath(mw.getServerDir() + "/../wwwlogs")
                if not os.path.exists(wwwlogs_dir):
                    os.makedirs(wwwlogs_dir, exist_ok=True)
                mw.execShell(f"chown -R {user}:{user_group} {wwwlogs_dir}")
                mw.execShell(f"chmod -R 755 {wwwlogs_dir}")
            except:
                pass
    except Exception as e:
        pass


def getPortPid(port=80):
    try:
        # 优先使用 ss
        res = mw.execShell("ss -tpln")
        if res[0] == '' or res[1] != '':
            res = mw.execShell("netstat -tpln")
        
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
        pass
    return None


def getProcessName(pid):
    try:
        comm_file = f"/proc/{pid}/comm"
        if os.path.exists(comm_file):
            return mw.readFile(comm_file).strip()
    except:
        pass
    return "unknown"


def getSystemdErrorDetail():
    detail = ""
    try:
        res = mw.execShell("journalctl -n 20 -u openresty --no-pager")
        if res[0] != '':
            detail += "\n[系统服务日志明细]:\n" + res[0]
    except:
        pass

    try:
        err_log_file = getServerDir() + '/nginx/logs/error.log'
        if os.path.exists(err_log_file):
            log_content = mw.readFile(err_log_file)
            if log_content:
                lines = log_content.strip().split('\n')
                last_lines = lines[-20:]
                detail += "\n[OpenResty 错误日志明细 (error.log)]:\n" + "\n".join(last_lines)
    except:
        pass

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
    data['os'] = mw.getOs()
    ng_exe_bin = getServerDir() + "/nginx/sbin/nginx"

    # if mw.isAppleSystem():
    #     data['auth'] = True
    #     return mw.getJson(data)

    if checkAuthEq(ng_exe_bin, 'root'):
        data['auth'] = True
    else:
        data['auth'] = False
    return mw.getJson(data)


def getInitDTpl():
    path = getPluginDir() + "/init.d/nginx.tpl"
    return path


def getPidFile():
    file = getConf()
    content = mw.readFile(file)
    rep = r'pid\s*(.*);'
    tmp = re.search(rep, content)
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
    service_path = mw.getServerDir()
    content = mw.readFile(getConfTpl())
    content = content.replace('{$SERVER_PATH}', service_path)

    user = 'www'
    user_group = 'www'

    current_os = mw.getOs()
    if current_os == 'darwin':
        # macosx do
        # user = mw.execShell(
        #     "who | sed -n '2, 1p' |awk '{print $1}'")[0].strip()
        user = 'midoks'
        user_group = 'staff'
        content = content.replace('{$EVENT_MODEL}', 'kqueue')
    elif current_os.startswith('freebsd'):
        content = content.replace('{$EVENT_MODEL}', 'kqueue')
    else:
        content = content.replace('{$EVENT_MODEL}', 'epoll')

    content = content.replace('{$OS_USER}', user)
    content = content.replace('{$OS_USER_GROUP}', user_group)

    # ng_conf_md5 = ''
    # ng_conf_md5_file = getServerDir() + '/nginx_conf.md5'
    # if not os.path.exists(ng_conf_md5_file):
    #     ng_conf_md5 = mw.md5(content)
    #     mw.writeFile(ng_conf_md5_file, ng_conf_md5)
    # else:
    #     ng_conf_md5 = mw.writeFile(ng_conf_md5_file).strip()

    # 主配置文件
    nconf = getServerDir() + '/nginx/conf/nginx.conf'
    mw.writeFile(nconf, content)

    # lua配置
    lua_conf_dir = mw.getServerDir() + '/web_conf/nginx/lua'
    if not os.path.exists(lua_conf_dir):
        mw.execShell('mkdir -p ' + lua_conf_dir)

    lua_conf = lua_conf_dir + '/lua.conf'
    lua_conf_tpl = getPluginDir() + '/conf/lua.conf'
    lua_content = mw.readFile(lua_conf_tpl)
    lua_content = lua_content.replace('{$SERVER_PATH}', service_path)
    mw.writeFile(lua_conf, lua_content)

    empty_lua = lua_conf_dir + '/empty.lua'
    if not os.path.exists(empty_lua):
        mw.writeFile(empty_lua, '')

    # 物理清除废弃防火墙 op_waf 残留挂载文件及配置，防止未物理清理彻底时失效的 require 模块阻碍正常启动
    opwaf_removes = [
        os.path.join(lua_conf_dir, 'access_by_lua_file', 'opwaf_init.lua'),
        os.path.join(lua_conf_dir, 'init_worker_by_lua_file', 'opwaf_init_worker.lua'),
        os.path.join(lua_conf_dir, 'init_by_lua_file', 'waf_init_preload.lua'),
        mw.getServerDir() + '/web_conf/nginx/vhost/opwaf.conf'
    ]
    for r_path in opwaf_removes:
        if os.path.exists(r_path):
            try:
                os.remove(r_path)
            except Exception as e:
                pass

    # 深度解耦自愈：若 OP 高性能防火墙 (OpenStar) 未安装或已被物理删除，则在此自动清理残留挂载，以杜绝 dofile init.lua 失败导致 OpenResty 启动崩溃
    openstar_dir = mw.getServerDir() + '/openstar'
    if not os.path.exists(openstar_dir):
        openstar_removes = [
            os.path.join(lua_conf_dir, 'init_by_lua_file', 'openstar_init_preload.lua'),
            os.path.join(lua_conf_dir, 'init_worker_by_lua_file', 'openstar_init_worker.lua'),
            os.path.join(lua_conf_dir, 'access_by_lua_file', 'openstar_access.lua'),
            mw.getServerDir() + '/web_conf/nginx/vhost/openstar.conf'
        ]
        for r_path in openstar_removes:
            if os.path.exists(r_path):
                try:
                    os.remove(r_path)
                except Exception as e:
                    pass

    mw.opLuaMakeAll()

    # 静态配置
    php_conf = mw.getServerDir() + '/web_conf/php/conf'
    if not os.path.exists(php_conf):
        mw.execShell('mkdir -p ' + php_conf)
    static_conf = mw.getServerDir() + '/web_conf/php/conf/enable-php-00.conf'
    if not os.path.exists(static_conf):
        mw.writeFile(static_conf, 'set $PHP_ENV 0;')

    # vhost
    vhost_dir = mw.getServerDir() + '/web_conf/nginx/vhost'
    vhost_tpl_dir = getPluginDir() + '/conf/vhost'
    if not os.path.exists(vhost_dir):
        mw.execShell('mkdir -p ' + vhost_dir)

    vhost_list = ['0.websocket.conf', '0.nginx_status.conf']
    for f in vhost_list:
        a_conf = vhost_dir + '/' + f
        a_conf_tpl = vhost_tpl_dir + '/' + f
        if not os.path.exists(a_conf):
            mw.writeFile(a_conf, mw.readFile(a_conf_tpl))

    # copy resty lib
    src_resty_dir = getPluginDir()+'/resty/*'
    dst_resty_dir = getServerDir()+'/lualib/resty'
    mw.execShell('cp -rf ' + src_resty_dir + ' ' + dst_resty_dir)


def initDreplace():

    file_tpl = getInitDTpl()
    service_path = mw.getServerDir()

    initD_path = getServerDir() + '/init.d'

    # OpenResty is not installed
    if not os.path.exists(getServerDir()):
        print("ok")
        exit(0)

    # init.d
    file_bin = initD_path + '/' + getPluginName()
    if not os.path.exists(initD_path):
        os.mkdir(initD_path)

        # initd replace
        content = mw.readFile(file_tpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        mw.writeFile(file_bin, content)
        mw.execShell('chmod +x ' + file_bin)

        # config replace
        confReplace()

    # give nginx root permission
    ng_exe_bin = getServerDir() + "/nginx/sbin/nginx"
    if not checkAuthEq(ng_exe_bin, 'root'):
        user = 'www'
        user_group = 'www'
        current_os = mw.getOs()
        if current_os == 'darwin':
            user = 'root'
            user_group = 'staff'
        args = getArgs()
        if not 'pwd' in args:
            print("权限不足，需要认证启动!")
            exit(0)

        sudoPwd = args['pwd']
        cmd_own = 'chown -R ' + user+':' + user_group + ' ' + ng_exe_bin
        mw.execShell('echo %s|sudo -S %s' % (sudoPwd, cmd_own))
        cmd_mod = 'chmod 755 ' + ng_exe_bin
        mw.execShell('echo %s|sudo -S %s' % (sudoPwd, cmd_mod))
        cmd_s = 'chmod u+s ' + ng_exe_bin
        mw.execShell('echo %s|sudo -S %s' % (sudoPwd, cmd_s))

    # systemd
    # /usr/lib/systemd/system
    systemDir = mw.systemdCfgDir()
    systemService = systemDir + '/openresty.service'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        systemServiceTpl = getPluginDir() + '/init.d/openresty.service.tpl'
        se_content = mw.readFile(systemServiceTpl)
        se_content = se_content.replace('{$SERVER_PATH}', service_path)
        mw.writeFile(systemService, se_content)
        mw.execShell('systemctl daemon-reload')

    return file_bin


def status():
    pid_file = getPidFile()
    if not os.path.exists(pid_file):
        return 'stop'
    return 'start'


def restyOp(method):
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
                mw.execShell(f"kill -9 {pid}")
                time.sleep(0.5)
            else:
                # 被其他服务占用，返回友好而清晰的错误
                return f"ERROR: 端口 {port} 已被服务 [{pname}] (PID: {pid}) 占用。请先停用该服务后再启动 OpenResty！"

    file = initDreplace()

    # 启动时,先检查一下配置文件
    check = getServerDir() + "/bin/openresty -t"
    check_data = mw.execShell(check)
    if not check_data[1].find('test is successful') > -1:
        return check_data[1]

    current_os = mw.getOs()
    if current_os == "darwin":
        data = mw.execShell(file + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    if current_os.startswith("freebsd"):
        data = mw.execShell('service openresty ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    data = mw.execShell('systemctl ' + method + ' openresty')
    if data[1] == '':
        return 'ok'
    
    # 启动失败时追加最详尽的日志细节，让用户秒懂错误原因
    err_detail = getSystemdErrorDetail()
    return data[1] + "\n" + err_detail


def op_submit_systemctl_restart():
    current_os = mw.getOs()
    if current_os.startswith("freebsd"):
        mw.execShell('service openresty restart')
        return True

    mw.execShell('systemctl restart openresty')
    return True


def op_submit_init_restart(file):
    mw.execShell(file + ' restart')


def restyOp_restart():
    # 执行配置语法自愈，杜绝常见语法损坏阻碍启动
    confSelfHeal()
    file = initDreplace()

    # 启动时,先检查一下配置文件
    check = getServerDir() + "/bin/openresty -t"
    check_data = mw.execShell(check)
    if not check_data[1].find('test is successful') > -1:
        return 'ERROR: 配置出错<br><a style="color:red;">' + check_data[1].replace("\n", '<br>') + '</a>'

    if not mw.isAppleSystem():
        threading.Timer(2, op_submit_systemctl_restart).start()
        return 'ok'

    threading.Timer(2, op_submit_init_restart, args=(file,)).start()
    return 'ok'


def start():
    return restyOp('start')


def stop():
    r = restyOp('stop')
    pid_file = getPidFile()
    if os.path.exists(pid_file):
        os.remove(pid_file)
    return r


def restart():
    return restyOp_restart()


def reload():
    confReplace()
    return restyOp('reload')


def initdStatus():
    current_os = mw.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile()
        if os.path.exists(initd_bin):
            return 'ok'

    shell_cmd = 'systemctl status openresty | grep loaded | grep "enabled;"'
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

    mw.execShell('systemctl enable openresty')
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

    mw.execShell('systemctl disable openresty')
    return 'ok'

def getNgxStatusPort():
    ngx_status_file = mw.getServerDir() + '/web_conf/nginx/vhost/0.nginx_status.conf'
    content = mw.readFile(ngx_status_file)
    rep = r'listen\s*(.*);'
    tmp = re.search(rep, content)
    port =  tmp.groups()[0].strip()
    return port


def runInfo():
    op_status = status()
    if op_status == 'stop':
        return mw.returnJson(False, "未启动!")

    port = getNgxStatusPort()
    # 取Openresty负载状态
    try:
        url = 'http://127.0.0.1:%s/nginx_status' % port
        result = mw.httpGet(url, timeout=3)
        tmp = result.split()
        data = {}
        data['active'] = tmp[2]
        data['accepts'] = tmp[9]
        data['handled'] = tmp[7]
        data['requests'] = tmp[8]
        data['Reading'] = tmp[11]
        data['Writing'] = tmp[13]
        data['Waiting'] = tmp[15]
        return mw.getJson(data)
    except Exception as e:
        try:
            url = 'http://' + mw.getHostAddr() + ':%s/nginx_status' % port
            result = mw.httpGet(url)
            tmp = result.split()
            data = {}
            data['active'] = tmp[2]
            data['accepts'] = tmp[9]
            data['handled'] = tmp[7]
            data['requests'] = tmp[8]
            data['Reading'] = tmp[11]
            data['Writing'] = tmp[13]
            data['Waiting'] = tmp[15]
            return mw.getJson(data)
        except Exception as e:
            return mw.returnJson(False, "oprenresty异常!")
        
    except Exception as e:
        return mw.returnJson(False, "oprenresty not started!")


def errorLogPath():
    return getServerDir() + '/nginx/logs/error.log'


def getCfg():
    cfg = getConf()
    content = mw.readFile(cfg)

    # 检测模块支持情况
    has_zstd = checkModuleSupport('zstd')
    has_brotli = checkModuleSupport('brotli')

    unitrep = "[kmgKMG]"
    cfg_args = [
        {"name": "worker_processes", "ps": "处理进程,auto表示自动,数字表示进程数", 'type': 2, 'default': 'auto'},
        {"name": "worker_connections", "ps": "最大并发链接数", 'type': 2, 'default': '51200'},
        {"name": "keepalive_timeout", "ps": "连接超时时间", 'type': 2, 'default': '60'},
        {"name": "zstd", "ps": "是否开启zstd压缩传输" + ("" if has_zstd else "(当前OpenResty未编译此模块，不支持)"), 'type': 1, 'default': 'off'},
        {"name": "brotli", "ps": "是否开启brotli压缩传输" + ("" if has_brotli else "(当前OpenResty未编译此模块，不支持)"), 'type': 1, 'default': 'off'},
        {"name": "gzip", "ps": "是否开启gzip压缩传输", 'type': 1, 'default': 'on'},
        {"name": "gzip_min_length", "ps": "最小压缩文件", 'type': 2, 'default': '1k'},
        {"name": "gzip_comp_level", "ps": "压缩率", 'type': 2, 'default': '6'},
        {"name": "client_max_body_size", "ps": "最大上传文件", 'type': 2, 'default': '20m'},
        {"name": "server_names_hash_bucket_size",
            "ps": "服务器名字的hash表大小", 'type': 2, 'default': '32'},
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

    return mw.returnJson(True, "ok", rdata)

def replaceChar(value, index, new_char):
    return value[:index] + new_char + value[index+1:]

def makeWorkerCpuAffinity(val):
    if val == "auto":
        return "auto"

    if mw.isNumber(val):
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
    mw.backFile(cfg)
    content = mw.readFile(cfg)

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

        # 如果是 zstd 或 brotli，且当前 OpenResty 没有编译对应的模块，且原配置文件里没有这一项，直接忽略不处理，杜绝 Nginx 无法启动报错
        if k == "zstd" and not checkModuleSupport('zstd'):
            if not re.search(rep, content):
                continue
        if k == "brotli" and not checkModuleSupport('brotli'):
            if not re.search(rep, content):
                continue

        if k == "worker_processes" or k == "gzip" or k == "zstd" or k == "brotli":
            if not re.search(r"auto|on|off|\d+", v):
                return mw.returnJson(False, '参数值错误')
        else:
            if not re.search(r"\d+", v):
                return mw.returnJson(False, '参数值错误,请输入数字整数')

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

    mw.writeFile(cfg, content)
    isError = mw.checkWebConfig()
    if (isError != True):
        mw.restoreFile(cfg)
        return mw.returnJson(False, 'ERROR: 配置出错<br><a style="color:red;">' + isError.replace("\n", '<br>') + '</a>')

    mw.restartWeb()
    return mw.returnJson(True, '设置成功')


def cronAddCheck():
    try:
        import tool_task
        tool_task.createBgTask()
        return mw.returnJson(True, '添加检查任务成功')
    except Exception as e:
        return mw.returnJson(False, '添加检查任务失败:'+str(e))

def cronDelCheck():
    try:
        import tool_task
        tool_task.removeBgTask()
        return mw.returnJson(True, '删除检查任务成功')
    except Exception as e:
        return mw.returnJson(False, '删除检查任务失败:'+str(e))

def cronCheck():
    return 'ok'


def installPreInspection():
    return 'ok'


if __name__ == "__main__":

    version = '1.27.1'
    version_pl = getServerDir() + "/version.pl"
    if os.path.exists(version_pl):
        version = mw.readFile(version_pl)


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
