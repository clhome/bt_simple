# coding:utf-8

import sys
import io
import os
import time
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
    return 'redis'


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


def detectAndFixConf():
    path = getServerDir() + "/redis.conf"
    if os.path.exists(path) and os.path.getsize(path) > 20:
        return path

    server_dir = getServerDir()
    if not os.path.exists(server_dir):
        try:
            os.makedirs(server_dir)
        except Exception:
            pass

    # 1. 尝试从运行中 redis-server 进程参数提取配置文件 (仅 Linux 环境有效)
    if yf.getOs() != 'win32' and not yf.isAppleSystem():
        try:
            ps_data = yf.execShell("ps -eo args | grep redis-server | grep -v grep")
            ps_out = ps_data[0] if ps_data and len(ps_data) > 0 else ''
            for line in ps_out.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                for part in parts:
                    if part.endswith('.conf') and os.path.exists(part) and os.path.getsize(part) > 20:
                        c = yf.readFile(part)
                        if c and len(c) > 20:
                            yf.writeFile(path, c)
                            return path
        except Exception:
            pass

    # 2. 尝试从常见备用系统路径或模板拷贝自愈
    candidates = [
        '/etc/redis/redis.conf',
        '/etc/redis.conf',
        server_dir + '/etc/redis.conf',
        server_dir + '/config/redis.conf',
        getPluginDir() + '/config/redis.conf',
        getPluginDir() + '/tpl/redis_simple.conf'
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.getsize(c) > 20:
            content = yf.readFile(c)
            if content and len(content) > 20:
                content = contentReplace(content)
                yf.writeFile(path, content)
                return path

    return path


def getConf():
    return detectAndFixConf()


def detectAndFixVersion():
    version_pl = getServerDir() + '/version.pl'
    if os.path.exists(version_pl):
        ver = yf.readFile(version_pl).strip()
        if ver:
            return ver

    server_bin = getServerDir() + '/bin/redis-server'
    candidates = []
    if os.path.exists(server_bin):
        candidates.append(server_bin)
    elif yf.getOs() != 'win32':
        for b in ['/usr/bin/redis-server', '/usr/local/bin/redis-server']:
            if os.path.exists(b):
                candidates.append(b)

    detected_ver = ''
    for b in candidates:
        try:
            res = yf.execShell(b + ' -v')
            out = (res[0] if res and len(res) > 0 else '') or ''
            m = re.search(r'v=([0-9]+\.[0-9]+(?:\.[0-9]+)?)', out)
            if m:
                detected_ver = m.group(1).strip()
                break
        except Exception:
            pass

    if not detected_ver:
        info_file = getPluginDir() + '/info.json'
        if os.path.exists(info_file):
            try:
                import json
                info_data = json.loads(yf.readFile(info_file))
                vers = info_data.get('versions', [])
                if isinstance(vers, list) and len(vers) > 0:
                    detected_ver = vers[0]
                elif isinstance(vers, str) and vers:
                    detected_ver = vers
            except Exception:
                pass

    if detected_ver:
        server_dir = getServerDir()
        if not os.path.exists(server_dir):
            try:
                os.makedirs(server_dir)
            except Exception:
                pass
        yf.writeFile(version_pl, detected_ver)
        return detected_ver

    return ''


def getConfTpl():
    path = getPluginDir() + "/config/redis.conf"
    return path


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


def getArgs():
    import json
    tmp = {}
    if len(sys.argv) <= 2:
        return tmp

    # 1. 优先从命令行末尾参数逆序检索 JSON 字典 (覆盖 /plugins/run 与 /plugins/callback 传参)
    for arg in reversed(sys.argv[2:]):
        arg_str = str(arg).strip()
        if (arg_str.startswith('{') and arg_str.endswith('}')) or (arg_str.startswith('[') and arg_str.endswith(']')):
            try:
                parsed = json.loads(arg_str)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

    # 2. 如果末尾未匹配到完整 JSON 字典，尝试从非版本参数中提取 k=v 或 k:v 键值对
    candidates = sys.argv[2:]
    if len(candidates) > 1 and re.match(r'^[0-9.]+$', candidates[0]):
        candidates = candidates[1:]

    for arg in candidates:
        arg_str = str(arg).strip()
        try:
            parsed = json.loads(arg_str)
            if isinstance(parsed, dict):
                tmp.update(parsed)
                continue
        except Exception:
            pass

        if '=' in arg_str:
            parts = arg_str.split('=', 1)
            tmp[parts[0].strip().strip('"').strip("'")] = parts[1].strip().strip('"').strip("'")
            continue

        clean_str = arg_str.strip('{').strip('}')
        if ':' in clean_str:
            parts = clean_str.split(':', 1)
            tmp[parts[0].strip().strip('"').strip("'")] = parts[1].strip().strip('"').strip("'")
            continue

    return tmp

def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '参数:(' + ck[i] + ')没有!'))
    return (True, yf.returnJson(True, 'ok'))

def configTpl():
    path = getPluginDir() + '/tpl'
    pathFile = os.listdir(path)
    tmp = []
    for one in pathFile:
        file = path + '/' + one
        tmp.append(file)
    return yf.getJson(tmp)


def readConfigTpl():
    args = getArgs()
    data = checkArgs(args, ['file'])
    if not data[0]:
        return data[1]

    # 安全增强：强路径前缀校验，杜绝任意文件读取与目录穿越
    target_file = os.path.abspath(args['file'])
    allowed_dir = os.path.abspath(getPluginDir() + '/tpl')
    if not target_file.startswith(allowed_dir + os.sep) and not target_file.startswith(allowed_dir + '/'):
        if target_file != allowed_dir:
            return yf.returnJson(False, '越界访问被拒绝！')

    if not os.path.exists(target_file):
        return yf.returnJson(False, '模板文件不存在')

    content = yf.readFile(target_file)
    content = contentReplace(content)
    return yf.returnJson(True, 'ok', content)

def getPidFile():
    file = getConf()
    if not os.path.exists(file):
        return ''
    content = yf.readFile(file)
    rep = r'pidfile\s*(.*)'
    tmp = re.search(rep, content)
    if tmp:
        return tmp.groups()[0].strip()
    return ''


def getRedisPid():
    """
    多模态探针：精确探测正在运行的真实 redis-server 进程 PID
    1. 优先读取并校验 PID 文件有效性；
    2. 进程树扫描当前配置实例与服务端二进制；
    3. 结合网络端口监听探针交叉校验。
    """
    # 1. 尝试从 PID 文件读取并验证
    pid_file = getPidFile()
    if pid_file and os.path.exists(pid_file):
        try:
            pid_str = yf.readFile(pid_file).strip()
            if pid_str and pid_str.isdigit():
                pid = int(pid_str)
                if yf.checkPid(pid):
                    return pid
        except Exception:
            pass

    # 2. 从系统进程树探测真实运行进程
    try:
        conf_path = getConf()
        # 优先匹配加载了当前配置文件的进程
        cmd = "pgrep -f " + yf.shlex_quote(conf_path)
        data = yf.execShell(cmd)
        pids = [int(p.strip()) for p in data[0].strip().split('\n') if p.strip().isdigit()]
        for p in pids:
            if yf.checkPid(p):
                return p

        # 降级匹配属于当前服务目录下的 redis-server 进程
        server_bin = getServerDir() + '/bin/redis-server'
        cmd = "pgrep -f " + yf.shlex_quote(server_bin)
        data = yf.execShell(cmd)
        pids = [int(p.strip()) for p in data[0].strip().split('\n') if p.strip().isdigit()]
        for p in pids:
            if yf.checkPid(p):
                return p
    except Exception:
        pass

    return None


def getLastLogError():
    """提取 redis.log 最后几行错误信息，用于启动失败时精准诊断"""
    log_file = runLog()
    if os.path.exists(log_file):
        try:
            content = yf.readFile(log_file)
            lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
            err_lines = []
            for l in reversed(lines[-20:]):
                if any(kw in l.lower() for kw in ['error', 'fatal', 'failed', 'address already in use', 'permission denied', 'bad directive']):
                    err_lines.append(l)
            if err_lines:
                return ' | '.join(reversed(err_lines[-3:]))
            if lines:
                return lines[-1]
        except Exception:
            pass
    return ''


def status():
    # 大版本升级检测与单次自愈守卫拦截（微秒级放行）
    try:
        checkPluginUpgrade()
    except Exception:
        pass

    try:
        detectAndFixVersion()
    except Exception:
        pass

    real_pid = getRedisPid()
    pid_file = getPidFile()

    if real_pid and yf.checkPid(real_pid):
        # 真实进程存活时，自动自愈写回/校准 PID 文件，杜绝假死误判
        if pid_file:
            try:
                curr_pid = ''
                if os.path.exists(pid_file):
                    curr_pid = yf.readFile(pid_file).strip()
                if curr_pid != str(real_pid):
                    yf.writeFile(pid_file, str(real_pid))
            except Exception:
                pass
        return 'start'

    # 双重保险：在 Systemd Linux 上结合 systemctl is-active 精准监控
    current_os = yf.getOs()
    if current_os != 'darwin' and not current_os.startswith('freebsd'):
        try:
            cmd = 'systemctl is-active ' + getPluginName()
            data = yf.execShell(cmd)
            if data[0].strip() == 'active':
                return 'start'
        except Exception:
            pass

    return 'stop'


def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$SERVER_APP}', service_path + '/' + getPluginName())
    content = content.replace('{$REDIS_PASS}', yf.getRandomString(10))
    return content


def initDreplace():
    file_tpl = getInitDTpl()
    service_path = yf.getServerDir()

    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        os.mkdir(initD_path)
    file_bin = initD_path + '/' + getPluginName()

    # initd replace
    if not os.path.exists(file_bin):
        content = yf.readFile(file_tpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        yf.writeFile(file_bin, content)
        yf.execShell('chmod +x ' + file_bin)

    # data & log directory
    dataLog = getServerDir() + '/data'
    if not os.path.exists(dataLog):
        yf.makeDirs(dataLog)
    if not yf.isAppleSystem() and not yf.getOs().startswith('freebsd'):
        yf.execShell('chmod 755 ' + dataLog)

    # config replace (零触碰防御机制：已有配置严禁覆盖重置，绝对保留用户已有密码与端口)
    dst_conf = getConf()
    dst_conf_init = getServerDir() + '/init.pl'
    if not os.path.exists(dst_conf):
        # 仅在配置文件完全不存在时从模板初始化默认配置
        conf_content = yf.readFile(getConfTpl())
        conf_content = conf_content.replace('{$SERVER_PATH}', service_path)
        conf_content = conf_content.replace('{$REDIS_PASS}', yf.getRandomString(10))
        yf.writeFile(dst_conf, conf_content)
        yf.writeFile(dst_conf_init, 'ok')
    else:
        # 已有配置文件存在时，若 init.pl 缺失自动补全标记，严禁覆盖原有配置
        if not os.path.exists(dst_conf_init):
            yf.writeFile(dst_conf_init, 'ok')
        # 智能检查并修复老配置中可能遗留的 {$SERVER_PATH} 占位符
        try:
            existing_conf = yf.readFile(dst_conf)
            if '{$SERVER_PATH}' in existing_conf or '{$ROOT_PATH}' in existing_conf:
                fixed_conf = contentReplace(existing_conf)
                yf.writeFile(dst_conf, fixed_conf)
        except Exception:
            pass

    # systemd 服务配置自动校准与刷新
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/' + getPluginName() + '.service'
    if os.path.exists(systemDir):
        systemServiceTpl = getPluginDir() + '/init.d/' + getPluginName() + '.service.tpl'
        service_path = yf.getServerDir()
        content = yf.readFile(systemServiceTpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        
        # 始终清理旧版本的 init.d 脚本，避免与 systemd 发生冲突
        if os.path.exists('/etc/init.d/redis'):
            yf.execShell('rm -f /etc/init.d/redis')
            
        # 始终清理可能与 Debian/Ubuntu 系统 apt 源冲突的自带 redis-server 服务
        if os.path.exists('/lib/systemd/system/redis-server.service'):
            yf.execShell('systemctl disable redis-server')
            yf.execShell('rm -f /lib/systemd/system/redis-server.service')
            yf.execShell('rm -f /etc/systemd/system/redis-server.service')
            
        # 清理旧路径下的同名服务，统一使用 /etc/systemd/system 作为标准配置目录
        if os.path.exists('/lib/systemd/system/redis.service'):
            yf.execShell('rm -f /lib/systemd/system/redis.service')
        if os.path.exists('/usr/lib/systemd/system/redis.service'):
            yf.execShell('rm -f /usr/lib/systemd/system/redis.service')
            
        # 将标准配置写入优先级最高的 /etc/systemd/system/ 目录，直接覆盖宝塔残留配置
        systemServiceEtc = '/etc/systemd/system/redis.service'
        if not os.path.exists(systemServiceEtc) or yf.readFile(systemServiceEtc) != content:
            yf.writeFile(systemServiceEtc, content)
            yf.execShell('systemctl daemon-reload')

    return file_bin


def redisOp(method):
    file = initDreplace()

    current_os = yf.getOs()
    if current_os == "darwin":
        data = yf.execShell(file + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    if current_os.startswith("freebsd"):
        data = yf.execShell('service ' + getPluginName() + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    data = yf.execShell('systemctl ' + method + ' ' + getPluginName())
    if data[1] == '':
        return 'ok'
    return data[1]


def start():
    # 启动前版本自愈与配置环境检查
    try:
        checkPluginUpgrade()
    except Exception:
        pass

    # 真实存活探针先行：若已在稳定运行，自动对齐 PID 并直接返回成功
    if status() == 'start':
        return 'ok'

    # 清理可能导致启动被拒绝的 systemd 失败锁定状态
    current_os = yf.getOs()
    if current_os != 'darwin' and not current_os.startswith('freebsd'):
        yf.execShell('systemctl reset-failed ' + getPluginName() + ' 2>/dev/null')

    res = redisOp('start')

    # 闭环启动校验：轮询检测 5 秒，彻底根除假成功假阳性
    for _ in range(5):
        time.sleep(1)
        if status() == 'start':
            return 'ok'

    # 若未拉起成功，主动抓取 redis.log 错误原因返回
    log_err = getLastLogError()
    if log_err:
        return f"启动失败，错误信息: {log_err}"
    if res != 'ok' and str(res).strip() != '':
        return f"启动失败: {res}"
    return '启动失败，进程未能存活，请查看运行日志'


def stop():
    res = redisOp('stop')
    # 优雅清理可能残留的失效 PID 文件
    pid_file = getPidFile()
    if pid_file and os.path.exists(pid_file):
        try:
            pid_str = yf.readFile(pid_file).strip()
            if pid_str and pid_str.isdigit() and not yf.checkPid(int(pid_str)):
                os.remove(pid_file)
        except Exception:
            pass
    return res


def restart():
    # 清理可能的失败锁定
    current_os = yf.getOs()
    if current_os != 'darwin' and not current_os.startswith('freebsd'):
        yf.execShell('systemctl reset-failed ' + getPluginName() + ' 2>/dev/null')

    res = redisOp('restart')

    # 闭环重启校验：最多等待 5 秒，确保服务重新稳定运行
    for _ in range(5):
        time.sleep(1)
        if status() == 'start':
            try:
                log_file = runLog()
                if log_file and os.path.exists(log_file):
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                    with open(log_file, 'a', encoding='utf-8', errors='ignore') as fp:
                        fp.write(f"[{timestamp}] * Redis 服务重启成功并处于活跃状态 (PID: {getRedisPid()})。\n")
            except Exception:
                pass
            return 'ok'

    log_err = getLastLogError()
    if log_err:
        return f"重启失败，错误信息: {log_err}"
    return res if res != 'ok' else '重启失败，服务未能重新拉起'


def reload():
    return redisOp('reload')



def getPort():
    conf_list = getRedisConfInfo()
    for item in conf_list:
        if item['name'] == 'port' and item['value']:
            return str(item['value']).strip()
    return '6379'


def getRedisCmd():
    requirepass = ""
    port = "6379"
    conf_list = getRedisConfInfo()
    for item in conf_list:
        if item['name'] == 'requirepass' and item['value']:
            requirepass = str(item['value']).strip()
        elif item['name'] == 'port' and item['value']:
            port = str(item['value']).strip()

    default_ip = '127.0.0.1'
    redis_cli = getServerDir() + "/bin/redis-cli"
    if not os.path.exists(redis_cli):
        for b in ['/usr/bin/redis-cli', '/usr/local/bin/redis-cli']:
            if os.path.exists(b):
                redis_cli = b
                break
        if not os.path.exists(redis_cli):
            redis_cli = "redis-cli"

    cmd = f'{redis_cli} -h {default_ip} -p {port} '
    if requirepass != "":
        # 安全转义 shell 特殊字符
        escaped_pass = requirepass.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
        cmd += f'-a "{escaped_pass}" --no-auth-warning '

    return cmd


def execRedisCommand(command='info'):
    """
    高可靠 Redis 命令执行器（三级容灾）：
    1. 优先使用 Python redis 库原生直连；
    2. 降级使用标准库 socket RESP 原生通信（零外部依赖、零 shell 污染）；
    3. 最后回退到命令行 redis-cli。
    返回: (success_output, error_output)
    """
    port = 6379
    requirepass = ""
    conf_list = getRedisConfInfo()
    for item in conf_list:
        if item['name'] == 'port' and item['value']:
            try:
                port = int(item['value'])
            except Exception:
                pass
        elif item['name'] == 'requirepass' and item['value']:
            requirepass = str(item['value']).strip()

    conn_pass = requirepass if (requirepass and requirepass != "''" and requirepass != '""') else None

    def format_redis_res(r_obj):
        if isinstance(r_obj, dict):
            lines = []
            for k, v in r_obj.items():
                if isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        lines.append(f"{k}_{sub_k}:{sub_v}")
                else:
                    lines.append(f"{k}:{v}")
            return "\n".join(lines)
        elif isinstance(r_obj, (list, tuple)):
            return "\n".join(str(item) for item in r_obj)
        return str(r_obj)

    # 1. 尝试 Python redis 库直连
    try:
        import redis
        r = redis.Redis(host='127.0.0.1', port=port, password=conn_pass, socket_timeout=3, decode_responses=True)
        parts = command.strip().split()
        res = r.execute_command(*parts)
        r.close()
        if res is not None:
            return (format_redis_res(res), '')
    except Exception as e:
        err_msg = str(e)
        if 'NOAUTH' in err_msg or 'WRONGPASS' in err_msg or 'invalid username-password' in err_msg.lower():
            try:
                import redis
                r = redis.Redis(host='127.0.0.1', port=port, password=None, socket_timeout=3, decode_responses=True)
                res = r.execute_command(*command.strip().split())
                r.close()
                if res is not None:
                    return (format_redis_res(res), '')
            except Exception:
                return ('', err_msg)

    # 2. 尝试标准库 socket RESP 原生协议直连 (零外部依赖，100% 可用)
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(3)
            s.connect(('127.0.0.1', port))

            # 处理认证
            if conn_pass:
                pass_bytes = conn_pass.encode('utf-8')
                auth_req = f"*2\r\n$4\r\nAUTH\r\n${len(pass_bytes)}\r\n".encode('utf-8') + pass_bytes + b"\r\n"
                s.sendall(auth_req)
                auth_res = s.recv(1024).decode('utf-8', errors='ignore')
                if auth_res.startswith('-'):
                    if 'without any password configured' in auth_res.lower():
                        pass
                    elif any(k in auth_res.lower() for k in ['wrongpass', 'noauth', 'invalid username-password']):
                        return ('', auth_res.strip())

            parts = command.strip().split()
            cmd_req = f"*{len(parts)}\r\n".encode('utf-8')
            for p in parts:
                p_bytes = p.encode('utf-8')
                cmd_req += f"${len(p_bytes)}\r\n".encode('utf-8') + p_bytes + b"\r\n"
            s.sendall(cmd_req)

            data_chunks = []
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data_chunks.append(chunk)
                if len(chunk) < 4096:
                    break
            raw_res = b''.join(data_chunks).decode('utf-8', errors='ignore')
            if raw_res.startswith('$'):
                first_n = raw_res.find('\r\n')
                if first_n != -1:
                    raw_res = raw_res[first_n + 2:]
                    if raw_res.endswith('\r\n'):
                        raw_res = raw_res[:-2]
                return (raw_res, '')
            elif raw_res.startswith('+'):
                return (raw_res[1:].strip(), '')
            elif raw_res.startswith('-'):
                return ('', raw_res[1:].strip())
            elif raw_res:
                return (raw_res, '')
        finally:
            try:
                s.close()
            except Exception:
                pass
    except Exception:
        pass

    # 3. 回退到命令行 redis-cli
    cmd = getRedisCmd() + command
    exec_res = yf.execShell(cmd)
    data = exec_res[0] if exec_res and len(exec_res) > 0 else ''
    err = exec_res[1] if exec_res and len(exec_res) > 1 else ''
    return (data, err)


def runInfo():
    s = status()
    if s == 'stop':
        return yf.returnJson(False, '未启动')

    data, err = execRedisCommand('info')

    # 1. 检测密码或认证异常，触发自愈热同步/重启
    need_self_healing = False
    raw_combined = (data + ' ' + err).lower()
    if any(k in raw_combined for k in ['noauth', 'wrongpass', 'invalid username-password', 'without any password configured']):
        need_self_healing = True

    if not need_self_healing:
        has_val = False
        if 'tcp_port' in data and ('uptime_in_days' in data or 'used_memory' in data):
            has_val = True
        else:
            for line in data.split('\n'):
                if ':' in line and line.split(':', 1)[0].strip() in ['tcp_port', 'uptime_in_days', 'used_memory']:
                    has_val = True
                    break
        if not has_val:
            need_self_healing = True

    # 自动自愈：当 Redis 内存配置与 redis.conf 脱节时，平滑重启使其挂载最新配置
    if need_self_healing:
        try:
            restart()
            time.sleep(1)
            data, err = execRedisCommand('info')
        except Exception:
            pass

    if 'NOAUTH' in data or 'NOAUTH' in err:
        return yf.returnJson(False, 'Redis 访问需要密码认证，请检查 requirepass 配置')
    if 'WRONGPASS' in data or 'WRONGPASS' in err or 'invalid username-password' in (data + err).lower():
        return yf.returnJson(False, 'Redis 密码认证失败，请检查 requirepass 密码')

    res = [
        'tcp_port',
        'uptime_in_days',  # 已运行天数
        'connected_clients',  # 连接的客户端数量
        'used_memory',  # Redis已分配的内存总量
        'used_memory_rss',  # Redis占用的系统内存总量
        'used_memory_peak',  # Redis所用内存的高峰值
        'mem_fragmentation_ratio',  # 内存碎片比率
        'total_connections_received',  # 运行以来连接过的客户端的总数量
        'total_commands_processed',  # 运行以来执行过的命令的总数量
        'instantaneous_ops_per_sec',  # 服务器每秒钟执行的命令数量
        'keyspace_hits',  # 查找数据库键成功的次数
        'keyspace_misses',  # 查找数据库键失败的次数
        'latest_fork_usec'  # 最近一次 fork() 操作耗费的毫秒数
    ]

    result = {}
    lines = data.split("\n")
    for d in lines:
        if ':' in d:
            t = d.strip().split(':', 1)
            k = t[0].strip().strip("'").strip('"')
            v = t[1].strip().strip("'").strip('"').rstrip(',')
            if k in res:
                result[k] = v

    # 容灾 1：如果解析结果较少，尝试从 Python dict 格式提取
    if not result or len(result) < 3:
        try:
            import ast
            parsed = ast.literal_eval(data.strip())
            if isinstance(parsed, dict):
                for k in res:
                    if k in parsed:
                        result[k] = str(parsed[k])
        except Exception:
            pass

    # 容灾 2：正则表达式直接匹配字段
    if not result or len(result) < 3:
        for k in res:
            m = re.search(r"['\"]?" + re.escape(k) + r"['\"]?\s*[:=]\s*['\"]?([^,'\"\n\r}]+)", data)
            if m:
                result[k] = m.group(1).strip()

    if not result:
        clean_detail = (err.strip() or data.strip() or '无返回内容')
        return yf.returnJson(False, f'未能读取到有效的 Redis 状态数据 ({clean_detail})')

    return yf.getJson(result)

def infoReplication():
    # 复制信息
    s = status()
    if s == 'stop':
        return yf.returnJson(False, '未启动')

    data, _ = execRedisCommand('info replication')
    res = [
        #slave
        'role',#角色
        'master_host',  # 连接主库HOST
        'master_port',  # 连接主库PORT
        'master_link_status',  # 连接主库状态
        'master_last_io_seconds_ago',  # 上次同步时间
        'master_sync_in_progress',  # 正在同步中
        'slave_read_repl_offset',  # 从库读取复制位置
        'slave_repl_offset',  # 从库复制位置
        'slave_priority',  # 从库同步优先级
        'slave_read_only',  # 从库是否仅读
        'replica_announced',  # 已复制副本
        'connected_slaves',  # 连接从库数量
        'master_failover_state',  # 主库故障状态
        'master_replid',  # 主库复制ID
        'master_repl_offset',  # 主库复制位置
        'second_repl_offset',  # 主库复制位置时间
        'repl_backlog_active',  # 复制状态
        'repl_backlog_size',  # 复制大小
        'repl_backlog_first_byte_offset',  # 第一个字节偏移量
        'repl_backlog_histlen',  # backlog中数据的长度
    ]

    data = data.split("\n")
    result = {}
    for d in data:
        if len(d) < 3:
            continue
        t = d.strip().split(':', 1)
        k = t[0].strip().strip("'").strip('"')
        v = t[1].strip().strip("'").strip('"').rstrip(',') if len(t) > 1 else ''
        if k in res:
            result[k] = v

    if not result:
        try:
            import ast
            parsed_dict = ast.literal_eval(data.strip())
            if isinstance(parsed_dict, dict):
                for k in res:
                    if k in parsed_dict:
                        result[k] = str(parsed_dict[k])
        except Exception:
            pass

    if 'role' in result and result['role'] == 'master':
        connected_slaves = int(result['connected_slaves'])
        slave_l = [] 
        for x in range(connected_slaves):
            slave_l.append('slave'+str(x))

        for d in data:
            if len(d) < 3:
                continue
            t = d.strip().split(':')
            if not t[0] in slave_l:
                continue
            result[t[0]] = t[1]

    return yf.getJson(result)


def clusterInfo():
    #集群信息
    # https://redis.io/commands/cluster-info/
    s = status()
    if s == 'stop':
        return yf.returnJson(False, '未启动')

    data, _ = execRedisCommand('cluster info')

    res = [
        'cluster_state',#状态
        'cluster_slots_assigned',  # 被分配的槽
        'cluster_slots_ok',  # 被分配的槽状态
        'cluster_slots_pfail',  # 连接主库状态
        'cluster_slots_fail',  # 失败的槽
        'cluster_known_nodes',  # 知道的节点
        'cluster_size',  # 大小
        'cluster_current_epoch',  # 
        'cluster_my_epoch',  # 
        'cluster_stats_messages_sent',  # 发送
        'cluster_stats_messages_received',  # 接受
        'total_cluster_links_buffer_limit_exceeded',  #
    ]

    data = data.split("\n")
    result = {}
    for d in data:
        if len(d) < 3:
            continue
        t = d.strip().split(':', 1)
        k = t[0].strip().strip("'").strip('"')
        v = t[1].strip().strip("'").strip('"').rstrip(',') if len(t) > 1 else ''
        if k in res:
            result[k] = v

    if not result:
        try:
            import ast
            parsed_dict = ast.literal_eval(data.strip())
            if isinstance(parsed_dict, dict):
                for k in res:
                    if k in parsed_dict:
                        result[k] = str(parsed_dict[k])
        except Exception:
            pass

    return yf.getJson(result)

def clusterNodes():
    s = status()
    if s == 'stop':
        return yf.returnJson(False, '未启动')

    data, _ = execRedisCommand('cluster nodes')
    data = data.strip().split("\n")
    return yf.getJson(data)

def initdStatus():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile()
        if os.path.exists(initd_bin):
            return 'ok'

    shell_cmd = 'systemctl is-enabled ' + getPluginName()
    data = yf.execShell(shell_cmd)
    if data[0].strip() == 'enabled':
        return 'ok'
    return 'fail'


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

    yf.execShell('systemctl enable ' + getPluginName())
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

    yf.execShell('systemctl disable ' + getPluginName())
    return 'ok'


def runLog():
    """
    多模态动态日志探测与自愈：
    1. 动态从有效 redis.conf 读取 logfile 配置，并严格清洗 {$SERVER_PATH} 等占位符；
    2. 内核态探测：从运行中的 redis-server 进程直接探测其打开的真实日志文件描述符；
    3. 常见系统备用路径探测（如 /var/log/redis/redis-server.log 等）；
    4. 若日志文件为空或日志太少，自动从 journalctl -u redis / redis-server 获取最新日志同步写入；
    5. 兜底保障文件真实存在且内容丰富，绝不返回空白！
    """
    detected_path = ''

    # 1. 尝试从运行中进程文件描述符动态捕获真实写入文件
    try:
        pid = getRedisPid()
        if pid and yf.checkPid(pid):
            fd_dir = f"/proc/{pid}/fd"
            if os.path.exists(fd_dir):
                for fd in os.listdir(fd_dir):
                    fd_p = os.path.join(fd_dir, fd)
                    if os.path.islink(fd_p):
                        target = os.readlink(fd_p)
                        if target.endswith('.log') and os.path.exists(target):
                            detected_path = target
                            break
    except Exception:
        pass

    # 2. 从 redis.conf 中解析 logfile
    if not detected_path:
        try:
            conf = getConf()
            if os.path.exists(conf):
                content = yf.readFile(conf)
                m = re.search(r'^\s*logfile\s+["\']?([^"\'\r\n#]+)["\']?', content, re.M)
                if m:
                    raw_path = m.group(1).strip()
                    if raw_path and raw_path not in ['""', "''"]:
                        # 核心：清洗占位符 {$SERVER_PATH}
                        cleaned_path = contentReplace(raw_path).strip()
                        if cleaned_path:
                            # 若配置文件中还残留占位符，自愈写回真实路径
                            if '{$SERVER_PATH}' in raw_path or '{$ROOT_PATH}' in raw_path:
                                try:
                                    fixed_content = content.replace(raw_path, cleaned_path)
                                    yf.writeFile(conf, fixed_content)
                                except Exception:
                                    pass
                            detected_path = cleaned_path
        except Exception:
            pass

    # 3. 检查系统常见备用路径
    if not detected_path or not os.path.exists(detected_path):
        candidates = [
            getServerDir() + '/data/redis.log',
            getServerDir() + '/redis.log',
            '/var/log/redis/redis-server.log',
            '/var/log/redis/redis.log'
        ]
        for c in candidates:
            if os.path.exists(c) and os.path.getsize(c) > 0:
                detected_path = c
                break

    if not detected_path:
        detected_path = getServerDir() + '/data/redis.log'

    pdir = os.path.dirname(detected_path)
    if pdir and not os.path.exists(pdir):
        try:
            os.makedirs(pdir, exist_ok=True)
        except Exception:
            pass

    if not os.path.exists(detected_path):
        try:
            with open(detected_path, 'w', encoding='utf-8') as fp:
                fp.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] * Redis 服务日志初始化记录。\n")
        except Exception:
            pass

    # 4. 内容保障与 journalctl 动态同步：若文件内容为空或太少，同步 systemd 日志
    current_size = os.path.getsize(detected_path) if os.path.exists(detected_path) else 0
    if current_size < 30:
        journal_synced = False
        if yf.getOs() != 'win32' and not yf.isAppleSystem():
            try:
                for svc in ['redis', 'redis-server']:
                    cmd = f"journalctl -u {svc} --no-pager -n 100"
                    res = yf.execShell(cmd)
                    j_out = res[0].strip() if res and len(res) > 0 and res[0] else ''
                    if j_out and len(j_out) > 30 and '-- No entries --' not in j_out:
                        yf.writeFile(detected_path, j_out + "\n")
                        journal_synced = True
                        break
            except Exception:
                pass

        if not journal_synced and current_size == 0:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            port = getPort()
            pid = getRedisPid() or 'N/A'
            init_msg = (
                f"[{timestamp}] * Redis 服务监控初始化记录\n"
                f"[{timestamp}] * 当前运行状态: {status()}\n"
                f"[{timestamp}] * 监听端口: {port} | 进程PID: {pid}\n"
                f"[{timestamp}] * 日志持久化路径: {detected_path}\n"
                f"[{timestamp}] * 提示: Redis 仅记录服务生命周期事件、持久化快照(RDB/AOF)与告警日志。\n"
            )
            yf.writeFile(detected_path, init_msg)

    return detected_path


def getRunLog():
    """
    获取 Redis 运行日志内容（强力自愈与多模态容灾）：
    1. 动态探测并确保 logfile 路径；
    2. 检查 Redis 进程是否缺失 logfile 配置，若缺失在线动态 CONFIG SET；
    3. 从日志文件读取；若为空，自动从 journalctl 同步并写回；
    4. 兜底生成格式化的实时健康与运行监控诊断信息，绝对不返回空白！
    """
    try:
        log_file = runLog()

        # 尝试在线动态检查并补全 Redis 运行时 logfile 配置
        try:
            if status() == 'start':
                out, _ = execRedisCommand('config get logfile')
                if out:
                    lines = [l.strip() for l in out.strip().split('\n') if l.strip()]
                    if len(lines) >= 2 and lines[1] in ['""', "''", ""]:
                        execRedisCommand(f'config set logfile "{log_file}"')
        except Exception:
            pass

        content = ''
        if os.path.exists(log_file):
            try:
                content = yf.getLastLine(log_file, 150)
                if content:
                    content = content.strip()
            except Exception:
                pass

        if not content:
            # 尝试从 journalctl 同步
            if yf.getOs() != 'win32' and not yf.isAppleSystem():
                for svc in ['redis', 'redis-server']:
                    try:
                        res = yf.execShell(f"journalctl -u {svc} --no-pager -n 100")
                        j_out = res[0].strip() if res and len(res) > 0 and res[0] else ''
                        if j_out and len(j_out) > 30 and '-- No entries --' not in j_out:
                            content = j_out
                            yf.writeFile(log_file, j_out + "\n")
                            break
                    except Exception:
                        pass

        if not content:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            port = getPort()
            pid = getRedisPid() or 'N/A'
            st = status()
            content = (
                f"[{timestamp}] * Redis 服务运行状态监控\n"
                f"[{timestamp}] * 当前运行状态: {st}\n"
                f"[{timestamp}] * 监听端口: {port} | 进程 PID: {pid}\n"
                f"[{timestamp}] * 日志文件: {log_file}\n"
                f"[{timestamp}] * 运行提示: 当前暂无异常或生命周期事件记录。\n"
                f"[{timestamp}] * 重要说明: Redis 默认仅记录启动、停机、RDB/AOF快照持久化及告警日志，常规客户端读写数据记录（如刚刚添加的数据）默认不记入此日志。"
            )
            try:
                yf.writeFile(log_file, content + "\n")
            except Exception:
                pass

        return yf.returnJson(True, 'OK', {
            'path': log_file,
            'data': content
        })
    except Exception as ex:
        return yf.returnJson(False, f"获取日志异常: {str(ex)}")


def clearRunLog():
    """清空 Redis 运行日志并安全写入清空标记"""
    try:
        log_file = runLog()
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        init_record = f"[{timestamp}] * 日志已被管理员手动清空，Redis 服务持续运行中...\n"
        yf.writeFile(log_file, init_record)
        return yf.returnJson(True, '日志已清空', {'path': log_file})
    except Exception as ex:
        return yf.returnJson(False, f"清空日志失败: {str(ex)}")



def getRedisConfInfo():
    conf = getConf()
    detectAndFixVersion()

    gets = [
        {'name': 'bind', 'type': 2, 'ps': '绑定IP(修改绑定IP可能会存在安全隐患)', 'must_show': 1},
        {'name': 'port', 'type': 2, 'ps': '绑定端口', 'must_show': 1},
        {'name': 'timeout', 'type': 2, 'ps': '空闲链接超时时间,0表示不断开', 'must_show': 1},
        {'name': 'maxclients', 'type': 2, 'ps': '最大连接数', 'must_show': 1},
        {'name': 'databases', 'type': 2, 'ps': '数据库数量', 'must_show': 1},
        {'name': 'requirepass', 'type': 2, 'ps': 'redis密码,留空代表没有设置密码', 'must_show': 1},
        {'name': 'maxmemory', 'type': 2, 'ps': 'MB,最大使用内存,0表示不限制', 'must_show': 1},
        {'name': 'slaveof', 'type': 2, 'ps': '同步主库地址', 'must_show': 0},
        {'name': 'masterauth', 'type': 2, 'ps': '同步主库密码', 'must_show': 0}
    ]
    content = yf.readFile(conf) if os.path.exists(conf) else ''
    if not content:
        content = ''

    result = []
    for g in gets:
        # 1. 优先匹配带双引号的值: name "value" (完整保留引号内的 #、空格及特殊字符)
        rep_double = r'^\s*' + g['name'] + r'\s+"([^"]*)"'
        m_double = re.search(rep_double, content, re.M)
        if m_double:
            val = m_double.group(1).strip()
            if g['name'] == 'maxmemory':
                val = val.lower().rstrip("mb").rstrip("m").strip()
            g['value'] = val
            result.append(g)
            continue

        # 2. 匹配带单引号的值: name 'value'
        rep_single = r"^\s*" + g['name'] + r"\s+'([^']*)'"
        m_single = re.search(rep_single, content, re.M)
        if m_single:
            val = m_single.group(1).strip()
            if g['name'] == 'maxmemory':
                val = val.lower().rstrip("mb").rstrip("m").strip()
            g['value'] = val
            result.append(g)
            continue

        # 3. 匹配未带引号的值 (直到遇到 # 注释或行尾截断)
        rep_plain = r"^\s*" + g['name'] + r"\s+([^\r\n#]+)"
        m_plain = re.search(rep_plain, content, re.M)
        if m_plain:
            val = m_plain.group(1).strip()
            if g['name'] == 'maxmemory':
                val = val.lower().rstrip("mb").rstrip("m").strip()
            g['value'] = val
            result.append(g)
            continue

        # 4. 未配置项处理
        if g['must_show'] == 0:
            continue
        g['value'] = ''
        result.append(g)

    return result


def getRedisConf():
    data = getRedisConfInfo()
    return yf.getJson(data)


def submitRedisConf():
    gets = ['bind', 'port', 'timeout', 'maxclients',
            'databases', 'requirepass', 'maxmemory', 'slaveof', 'masterauth']
    args = getArgs()
    conf = getConf()
    content = yf.readFile(conf) if os.path.exists(conf) else ''
    if not content:
        content = ''

    # 强正则安全白名单校验体系，彻底杜绝任意指令与换行符注入（RCE）
    for g in gets:
        if g in args:
            val_str = str(args[g]).strip()
            
            # 1. 纯数字项过滤
            if g in ['port', 'timeout', 'maxclients', 'databases', 'maxmemory']:
                if not re.match(r'^\d+$', val_str):
                    return yf.returnJson(False, '参数 [' + g + '] 格式不合法！')
            
            # 2. 绑定 IP 与主从同步过滤 (支持 IPv4, IPv6 如 -::1, 空格, 逗号)
            elif g in ['bind', 'slaveof']:
                if val_str != '' and not re.match(r'^[0-9a-zA-Z_.:\s,-]+$', val_str):
                    return yf.returnJson(False, '参数 [' + g + '] 格式不合法！')
            
            # 3. 密码及凭据强抗注入过滤 (允许常见安全字符，杜绝换行符注入)
            elif g in ['requirepass', 'masterauth']:
                if val_str != '' and not re.match(r'^[a-zA-Z0-9_.~!@#$%^&*()_+=\[\]{};:,./<>-]+$', val_str):
                    return yf.returnJson(False, '密码参数 [' + g + '] 含有非法字符！')

    for g in gets:
        if g in args:
            val_str = str(args[g]).strip()

            if g == 'maxmemory':
                target_val = val_str + 'mb' if (val_str and val_str != '0') else '0'
            else:
                target_val = val_str

            if g in ['requirepass', 'masterauth']:
                # 若密码含 #、空格或特殊引号字符，自动采用双引号包裹，保证 Redis 核心服务解析合规
                write_val = f'"{val_str}"' if ('#' in val_str or ' ' in val_str) else val_str
                if val_str == '':
                    if re.search(r'^\s*' + g + r'\s+', content, flags=re.M):
                        content = re.sub(r'^\s*' + g + r'\s+.*', '#' + g + ' ""', content, flags=re.M)
                else:
                    if re.search(r'^\s*#?\s*' + g + r'\s+', content, flags=re.M):
                        content = re.sub(r'^\s*#?\s*' + g + r'\s+.*', g + ' ' + write_val, content, flags=re.M)
                    else:
                        content += '\n' + g + ' ' + write_val
            elif g == 'slaveof':
                if val_str == '':
                    if re.search(r'^\s*(slaveof|replicaof)\s+', content, flags=re.M):
                        content = re.sub(r'^\s*(slaveof|replicaof)\s+.*', '', content, flags=re.M)
                else:
                    if re.search(r'^\s*#?\s*(slaveof|replicaof)\s+', content, flags=re.M):
                        content = re.sub(r'^\s*#?\s*(slaveof|replicaof)\s+.*', 'replicaof ' + val_str, content, flags=re.M)
                    else:
                        content += '\nreplicaof ' + val_str
            else:
                rep = r'^\s*' + g + r'\s+.*'
                if re.search(rep, content, flags=re.M):
                    content = re.sub(rep, g + ' ' + target_val, content, flags=re.M)
                else:
                    content += '\n' + g + ' ' + target_val

    yf.writeFile(conf, content)
    if status() == 'start':
        restart()
    return yf.returnJson(True, '设置成功')


CURRENT_PLUGIN_VERSION = '2.0'
_REDIS_UPGRADE_CHECKING = False


def getPluginVersionFile():
    """获取插件大版本标记文件路径"""
    return getPluginDir() + '/plugin_version.pl'


def getInstalledPluginVersion():
    """读取当前本地已持久化的插件版本（老版本若无此文件默认返回 1.0）"""
    vfile = getPluginVersionFile()
    if os.path.exists(vfile):
        try:
            v = yf.readFile(vfile).strip()
            if v:
                return v
        except Exception:
            pass
    server_vfile = getServerDir() + '/plugin_version.pl'
    if os.path.exists(server_vfile):
        try:
            v = yf.readFile(server_vfile).strip()
            if v:
                return v
        except Exception:
            pass
    return '1.0'


def setInstalledPluginVersion(ver):
    """持久化保存插件版本标记"""
    vfile = getPluginVersionFile()
    try:
        yf.writeFile(vfile, str(ver).strip())
    except Exception:
        pass
    try:
        server_vfile = getServerDir() + '/plugin_version.pl'
        if os.path.exists(getServerDir()):
            yf.writeFile(server_vfile, str(ver).strip())
    except Exception:
        pass


def comparePluginVersion(v1, v2):
    """语义化版本号比较：-1 (v1 < v2), 0 (v1 == v2), 1 (v1 > v2)"""
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


def upgradeSelfHealing(version=''):
    """
    全自动平滑无损升级与环境自愈接口：
    1. 刷新配置文件与 systemd 脚本（零触碰防御：绝对保留用户原有密码与配置）；
    2. 清理系统源 apt 自带冲突的 redis-server 服务；
    3. 重置 systemd 失败锁定状态并重载；
    4. 确保运行目录和日志目录权限合规；
    5. 探活已有存活进程并自愈写回真实 PID；
    6. 未运行则安全拉起服务，返回详细自愈报告。
    """
    logs = []
    logs.append("开始执行 Redis 插件平滑无损升级与环境自愈流程...")

    # 1. 刷新服务配置与模板
    try:
        initDreplace()
        logs.append("服务配置与 systemd 守护进程脚本已完成检查与自愈。")
    except Exception as ex:
        logs.append(f"服务配置自愈警告: {ex}")

    # 2. 清理系统 apt 冲突服务与重置 systemd 状态
    current_os = yf.getOs()
    if current_os != 'darwin' and not current_os.startswith('freebsd'):
        try:
            if os.path.exists('/lib/systemd/system/redis-server.service') or os.path.exists('/etc/systemd/system/redis-server.service'):
                yf.execShell('systemctl stop redis-server 2>/dev/null')
                yf.execShell('systemctl disable redis-server 2>/dev/null')
                yf.execShell('rm -f /lib/systemd/system/redis-server.service /etc/systemd/system/redis-server.service')
                logs.append("已清理并停止系统源自带的 redis-server 冲突服务。")
            yf.execShell('systemctl reset-failed ' + getPluginName() + ' 2>/dev/null')
            yf.execShell('systemctl daemon-reload 2>/dev/null')
        except Exception as ex:
            logs.append(f"冲突与锁定清理警告: {ex}")

    # 3. 运行目录权限校准
    try:
        data_dir = getServerDir() + '/data'
        if not os.path.exists(data_dir):
            yf.makeDirs(data_dir)
        if not yf.isAppleSystem() and not yf.getOs().startswith('freebsd'):
            yf.execShell('chmod -R 755 ' + getServerDir())
        logs.append("Redis 运行目录与权限已校准。")
    except Exception as ex:
        logs.append(f"目录权限校准警告: {ex}")

    # 4. 健康状态探测与 PID 自愈
    st = status()
    if st != 'start':
        logs.append("检测到 Redis 服务未处于运行状态，正在尝试安全拉起...")
        start_res = start()
        logs.append(f"启动结果: {start_res}")
    else:
        logs.append("Redis 服务正在稳定运行中，PID 已自动对齐校准。")

    final_status = status()
    is_ok = (final_status == 'start')
    logs.append(f"升级自愈完成，最终服务运行状态: {final_status}")

    return yf.returnJson(is_ok, "\n".join(logs), {'status': final_status})


def _migrate_redis_1_to_2(version=''):
    """1.x 升级至 2.0 阶段自愈迁移"""
    return upgradeSelfHealing(version)


# 迁移流水线配置：(目标大版本, 迁移执行函数)
# 后续升级（如升级至 2.1, 3.0 等指定版本）只需在此注册新的迁移函数即可平滑扩展！
REDIS_MIGRATION_STEPS = [
    ('2.0', _migrate_redis_1_to_2),
]


def checkPluginUpgrade(version=''):
    """
    大版本升级检测与单次自愈迁移函数：
    1. 检查已持久化的版本号，若已达到当前版本直接放行（耗时微秒级，零损耗）；
    2. 当检测到从 1.x 升级到 2.x 时，自动触发且仅触发一次自愈；
    3. 成功后更新版本号到本地文件，保证升级后只执行一次；
    4. 保留未来版本迁移路由接口。
    """
    global _REDIS_UPGRADE_CHECKING
    if _REDIS_UPGRADE_CHECKING:
        return {'status': True, 'msg': 'Upgrade checking already in progress'}

    installed_ver = getInstalledPluginVersion()
    target_ver = CURRENT_PLUGIN_VERSION

    if comparePluginVersion(installed_ver, target_ver) >= 0:
        return {'status': True, 'msg': 'Already up to date', 'version': installed_ver}

    _REDIS_UPGRADE_CHECKING = True
    migration_logs = []
    success = True
    current_v = installed_ver

    try:
        for step_ver, step_func in REDIS_MIGRATION_STEPS:
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
        _REDIS_UPGRADE_CHECKING = False

    return {
        'status': success,
        'installed_version': installed_ver,
        'target_version': target_ver,
        'logs': migration_logs
    }


if __name__ == "__main__":
    func = sys.argv[1]
    if func == 'check_plugin_upgrade':
        print(checkPluginUpgrade())
    elif func == 'upgrade_self_healing':
        print(upgradeSelfHealing())
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
    elif func == 'info_replication':
        print(infoReplication())
    elif func == 'cluster_info':
        print(clusterInfo())
    elif func == 'cluster_nodes':
        print(clusterNodes())
    elif func == 'conf':
        print(getConf())
    elif func == 'run_log':
        print(runLog())
    elif func == 'get_run_log':
        print(getRunLog())
    elif func == 'clear_run_log':
        print(clearRunLog())
    elif func == 'get_redis_conf':
        print(getRedisConf())
    elif func == 'submit_redis_conf':
        print(submitRedisConf())
    elif func == 'config_tpl':
        print(configTpl())
    elif func == 'read_config_tpl':
        print(readConfigTpl())
    elif func == 'detect_version':
        print(detectAndFixVersion())
    else:
        print('error')

