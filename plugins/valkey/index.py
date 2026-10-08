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
import logging

_log = logging.getLogger('yf.valkey')

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'valkey'


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


def getConf():
    path = getServerDir() + "/valkey.conf"
    return path


def getConfTpl():
    path = getPluginDir() + "/config/valkey.conf"
    return path


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


def getArgs():
    """解析调用参数。

    真实调用形态（web/utils/plugin.py::run）：
        <面板 python> plugins/valkey/index.py <func> [version] <args-json>
    args 是前端 JSON.stringify 出来的对象串（如 {"port":"6389"}）。
    旧实现从 argv[3:] 起读、且只认 `k:v` 单值对，于是：
      - 不带 version 调用时（argv[2] 就是参数）参数被整体跳过；
      - JSON 对象串被按第一个冒号整段切碎（键名变成 "port"、值变成 "6389","bind":"…"），
        键名永远匹配不上 -> 提交配置静默失效却仍回「设置成功」（假成功）。
    与 redis 插件同口径：从 argv[2:] 起扫，支持 JSON 字典 / k=v / k:v。
    """
    import json
    tmp = {}
    if len(sys.argv) <= 2:
        return tmp

    # 1. 先找完整的 JSON 字典（/plugins/run 与 /plugins/callback 的传参形态）
    for arg in reversed(sys.argv[2:]):
        arg_str = str(arg).strip()
        if (arg_str.startswith('{') and arg_str.endswith('}')) or (arg_str.startswith('[') and arg_str.endswith(']')):
            try:
                parsed = json.loads(arg_str)
                if isinstance(parsed, dict):
                    return parsed
            except Exception as _e:
                _log.debug('[valkey] getArgs 解析 JSON 参数失败: %s', _e)

    # 2. 退化为 k=v / k:v 键值对解析（跳过被当成位置参数的 version 数字）
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
        except Exception as _e:
            _log.debug('[valkey] getArgs 解析 JSON 参数失败: %s', _e)

        if '=' in arg_str:
            parts = arg_str.split('=', 1)
            tmp[parts[0].strip().strip('"').strip("'")] = parts[1].strip().strip('"').strip("'")
            continue

        clean_str = arg_str.strip('{').strip('}')
        if ':' in clean_str:
            parts = clean_str.split(':', 1)
            tmp[parts[0].strip().strip('"').strip("'")] = parts[1].strip().strip('"').strip("'")

    return tmp

def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
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

    # 安全增强：路径前缀校验，杜绝任意文件读取与目录穿越
    target_file = os.path.abspath(args['file'])
    allowed_dir = os.path.abspath(getPluginDir() + '/tpl')
    if not target_file.startswith(allowed_dir + os.sep) and not target_file.startswith(allowed_dir + '/'):
        if target_file != allowed_dir:
            return yf.returnJson(False, '越界访问被拒绝！')

    # 必须是可读普通文件：传目录（或读失败）时 readFile 返回 False，旧写法会在
    # contentReplace(False) 上抛 AttributeError（真机 traceback）。
    if not os.path.isfile(target_file):
        return yf.returnJson(False, '模板文件不存在')

    content = yf.readFile(target_file)
    if content is False:
        return yf.returnJson(False, '模板文件不存在')
    content = contentReplace(content)
    return yf.returnJson(True, 'ok', content)

def getPidFile():
    file = getConf()
    content = yf.readFile(file)
    if not content:
        return ""
    rep = r'pidfile\s*(.*)'
    tmp = re.search(rep, content)
    if tmp:
        return tmp.groups()[0].strip()
    return ""

def status():
    """运行状态判定。

    旧实现只看 conf 里 pidfile 指向的文件**是否存在**：进程被杀/崩溃后残留的陈旧
    pid 文件会让面板一直显示「运行中」（假阳性），读接口随后全部对着一个死进程
    发命令。这里要求 pid 真实存活，不满足再退一步问 systemd；与 redis 插件同口径
    （差别：valkey 不写回 pid 文件，避免 root 面板改动守护进程 pid 文件属主）。
    """
    pid_file = getPidFile()
    if pid_file and os.path.exists(pid_file):
        try:
            raw = yf.readFile(pid_file)
            pid_str = raw.strip() if raw else ''
            if pid_str.isdigit() and yf.checkPid(int(pid_str)):
                return 'start'
        except Exception as _e:
            _log.debug('[valkey] status 读取 pid 文件失败: %s', _e)

    current_os = yf.getOs()
    if current_os != 'darwin' and not current_os.startswith('freebsd'):
        try:
            data = yf.execShell('systemctl is-active ' + getPluginName())
            if data[0].strip() == 'active':
                return 'start'
        except Exception as _e:
            _log.debug('[valkey] status 探测 systemd 状态失败: %s', _e)

    return 'stop'

def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$SERVER_APP}', service_path + '/'+getPluginName())
    content = content.replace('{$VALKEY_PASS}', yf.getRandomString(10))
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

    # log
    dataLog = getServerDir() + '/data'
    if not os.path.exists(dataLog):
        yf.makeDirs(dataLog)
        yf.execShell('chmod +x ' + file_bin)

    # config replace
    dst_conf = getConf()
    dst_conf_init = getServerDir() + '/init.pl'
    if not os.path.exists(dst_conf_init):
        content = yf.readFile(getConfTpl())
        content = content.replace('{$SERVER_PATH}', service_path)
        content = content.replace('{$VALKEY_PASS}', yf.getRandomString(10))

        yf.writeFile(dst_conf, content)
        yf.writeFile(dst_conf_init, 'ok')

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


def wkOp(method):
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
    res = wkOp('start')

    # 闭环校验：systemctl 返回成功 ≠ 进程真的活着（配置写坏时进程会立刻退出）。
    # 不做就绪轮询就 return ok 就是假成功，面板显示「已启动」而服务其实没起来。
    for _ in range(5):
        time.sleep(1)
        if status() == 'start':
            return 'ok'

    if res != 'ok' and str(res).strip() != '':
        return '启动失败: ' + str(res)
    return '启动失败，进程未能存活，请查看运行日志'


def stop():
    return wkOp('stop')


def restart():
    res = wkOp('restart')

    # 同 start()：不轮询就回 ok 会让「保存配置→重启」假成功，而 submitRedisConf 的
    # 回滚判据正是本函数返回值（返回非 ok 才回滚），所以必须真的确认已就绪。
    for _ in range(5):
        time.sleep(1)
        if status() == 'start':
            log_file = runLog()
            yf.execShell("echo '' > " + log_file)
            return 'ok'

    if res != 'ok' and str(res).strip() != '':
        return '重启失败: ' + str(res)
    return '重启失败，服务未能重新拉起'


def reload():
    return wkOp('reload')


def getPort():
    conf_list = getRedisConfInfo()
    for item in conf_list:
        if item['name'] == 'port' and item['value']:
            return str(item['value']).strip()
    return '6379'


def getRedisCmd():
    """构造 valkey-cli 的**参数列表**（绝不拼成 shell 字符串）。

    为什么必须是列表：调用点一旦把字符串交给 yf.execShell，参数就由 shell 解释，
    而 port/requirepass 都来自 valkey.conf（submit_redis_conf 可写）——真机夹具
    实测：conf 里写 `port 6389 & touch yftest_b06_rce`，执行时 `& touch …`
    会以 root 身份跑起来（命令注入）。列表化后参数不再经 shell，密码也无需转义。
    """
    requirepass = ""
    port = "6379"
    conf_list = getRedisConfInfo()
    for item in conf_list:
        if item['name'] == 'requirepass' and item['value']:
            requirepass = str(item['value']).strip()
        elif item['name'] == 'port' and item['value']:
            port = str(item['value']).strip()

    valkey_cli = getServerDir() + "/bin/valkey-cli"
    if not os.path.exists(valkey_cli):
        for b in ['/usr/bin/valkey-cli', '/usr/local/bin/valkey-cli']:
            if os.path.exists(b):
                valkey_cli = b
                break
        else:
            valkey_cli = "valkey-cli"

    argv = [valkey_cli, '-h', '127.0.0.1', '-p', port]
    if requirepass != "":
        argv += ['-a', requirepass, '--no-auth-warning']
    return argv


def valkeyCli(*args):
    """以 shell=False 执行 valkey-cli，返回 (stdout, stderr)。

    所有读接口的唯一执行入口：命令内容永远不经过 shell（见 getRedisCmd 的说明），
    并统一带 5s 超时，避免服务挂死时把面板请求线程一并拖住。
    """
    rc, out, err = yf.execShellRc(getRedisCmd() + list(args), shell=False, timeout=5)
    if rc != 0 and not err:
        err = 'valkey-cli 执行失败(rc=%s)' % rc
    return (out or '', err or '')


def runInfo():
    s = status()
    if s == 'stop':
        return yf.returnJson(False, '未启动')

    data, err = valkeyCli('info')
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
    data = data.split("\n")
    result = {}
    for d in data:
        if len(d) < 3:
            continue
        t = d.strip().split(':', 1)
        if not t[0] in res:
            continue
        result[t[0]] = t[1]

    if not result:
        # 空结果必须如实报错：旧实现直接回 {}，前端拿到的是一张全是 undefined 的表，
        # 运维会以为「服务正常只是没数据」，实际可能是 cli/密码/端口出了问题。
        detail = (err.strip() or data.strip() or '无返回内容')
        return yf.returnJson(False, '未能读取到有效的 Valkey 状态数据: ' + detail)

    return yf.getJson(result)


def infoReplication():
    # 复制信息
    s = status()
    if s == 'stop':
        return yf.returnJson(False, '未启动')

    data, _ = valkeyCli('info', 'replication')
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
        if not t[0] in res:
            continue
        result[t[0]] = t[1]

    if 'role' in result and result['role'] == 'master':
        # connected_slaves 缺失/非数字时不能直接 int()：INFO 被截断或换实现时
        # 实测 KeyError → 接口 500 / 子进程 traceback。缺失即按 0 个从库处理。
        try:
            connected_slaves = int(result.get('connected_slaves', 0) or 0)
        except (TypeError, ValueError):
            connected_slaves = 0
        slave_l = [] 
        for x in range(connected_slaves):
            slave_l.append('slave'+str(x))

        for d in data:
            if len(d) < 3:
                continue
            # 只按第一个冒号切分：从库行是 `slave0:ip=..,port=..`，IPv6 场景值里
            # 还会再出现冒号，旧的 split(':') 会把值截断。
            t = d.strip().split(':', 1)
            if t[0] not in slave_l or len(t) < 2:
                continue
            result[t[0]] = t[1]

    return yf.getJson(result)


def clusterInfo():
    #集群信息
    # https://redis.io/commands/cluster-info/
    s = status()
    if s == 'stop':
        return yf.returnJson(False, '未启动')

    data, _ = valkeyCli('cluster', 'info')

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
        if not t[0] in res:
            continue
        result[t[0]] = t[1]

    return yf.getJson(result)

def clusterNodes():
    s = status()
    if s == 'stop':
        return yf.returnJson(False, '未启动')

    data, _ = valkeyCli('cluster', 'nodes')

    # 空应答必须回空列表：旧的 strip().split('\n') 会产出 ['']，前端把这条假数据
    # 渲染成一行空行，而不是「无数据/未设置集群」。
    data = [line for line in data.strip().split("\n") if line.strip()]
    return yf.getJson(data)

def initdStatus():
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile()
        if os.path.exists(initd_bin):
            return 'ok'

    # 旧写法 `systemctl status … | grep loaded | grep "enabled;"` 依赖人类可读输出：
    # 状态行在非英文 locale 下会被翻译（"已加载"），进而把「已启用」误判成 fail；
    # 改成机器可读的 is-enabled 判定（redis 插件同口径，输出永不本地化）。
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
    return getServerDir() + '/data/valkey.log'


def getRedisConfInfo():
    conf = getConf()

    gets = [
        {'name': 'bind', 'type': 2, 'ps': '绑定IP(修改绑定IP可能会存在安全隐患)','must_show':1},
        {'name': 'port', 'type': 2, 'ps': '绑定端口','must_show':1},
        {'name': 'timeout', 'type': 2, 'ps': '空闲链接超时时间,0表示不断开','must_show':1},
        {'name': 'maxclients', 'type': 2, 'ps': '最大连接数','must_show':1},
        {'name': 'databases', 'type': 2, 'ps': '数据库数量','must_show':1},
        {'name': 'requirepass', 'type': 2, 'ps': 'redis密码,留空代表没有设置密码','must_show':1},
        {'name': 'maxmemory', 'type': 2, 'ps': 'MB,最大使用内存,0表示不限制','must_show':1},
        {'name': 'slaveof', 'type': 2, 'ps': '同步主库地址','must_show':0},
        {'name': 'masterauth', 'type': 2, 'ps': '同步主库密码', 'must_show':0}
    ]
    content = yf.readFile(conf) if os.path.exists(conf) else ''
    if not content:
        content = ''

    result = []
    for g in gets:
        # 1. 优先匹配双引号值: name "value"（完整保留引号内的 #、空格等特殊字符，
        #    与新 submitRedisConf 写回时的引号包裹口径对应）
        m_double = re.search(r'^\s*' + g['name'] + r'\s+"([^"]*)"', content, re.M)
        if m_double:
            val = m_double.group(1).strip()
            if g['name'] == 'maxmemory':
                val = val.lower().rstrip("mb").rstrip("m").strip()
            g['value'] = val
            result.append(g)
            continue

        # 2. 匹配单引号值: name 'value'
        m_single = re.search(r"^\s*" + g['name'] + r"\s+'([^']*)'", content, re.M)
        if m_single:
            val = m_single.group(1).strip()
            if g['name'] == 'maxmemory':
                val = val.lower().rstrip("mb").rstrip("m").strip()
            g['value'] = val
            result.append(g)
            continue

        # 3. 匹配未带引号的值（读到行尾或 # 注释为止）
        m_plain = re.search(r'^\s*' + g['name'] + r'\s+([^\r\n#]+)', content, re.M)
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
    # 落盘前的原配置快照：写坏/重启失败时整份回滚，绝不许「设置成功」假成功
    original_content = content

    # 强正则白名单校验，杜绝任意指令与换行符注入（RCE）
    for g in gets:
        if g in args:
            val_str = str(args[g]).strip()

            # 1. 纯数字项（port 另加 1..65535 范围：越界端口写下去服务必然起不来）
            if g in ['port', 'timeout', 'maxclients', 'databases', 'maxmemory']:
                if not re.match(r'^\d+$', val_str) or (g == 'port' and not (1 <= int(val_str) <= 65535)):
                    return yf.returnJson(False, '参数 [' + g + '] 格式不合法！')

            # 2. 绑定 IP 与主从同步（支持 IPv4/IPv6、半角空格分隔、逗号）
            #    这里刻意不用 \s：\s 含 \n/\r/\f/\v，而 Redis/Valkey 配置解析器会把
            #    这些字符当换行/分隔符 —— 等于把任意指令注入 valkey.conf。真机夹具实测
            #    bind="127.0.0.1\nport 1" 通过旧校验，`port 1` 被写进了配置文件。
            elif g in ['bind', 'slaveof']:
                if val_str != '' and not re.match(r'^[0-9a-zA-Z_.,:\- ]+$', val_str):
                    return yf.returnJson(False, '参数 [' + g + '] 格式不合法！')

            # 3. 密码/凭据（允许常用安全符号，杜绝换行注入）
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
                # 含 # / 空格的密码必须引号包裹，否则服务会把 # 之后当注释截断
                write_val = f'"{val_str}"' if ('#' in val_str or ' ' in val_str) else val_str
                if val_str == '':
                    if re.search(r'^[ \t]*' + g + r'[ \t]+', content, flags=re.M):
                        content = re.sub(r'^[ \t]*' + g + r'[ \t]+.*', '#' + g + ' ""', content, flags=re.M)
                else:
                    if re.search(r'^[ \t]*#?[ \t]*' + g + r'[ \t]+', content, flags=re.M):
                        content = re.sub(r'^[ \t]*#?[ \t]*' + g + r'[ \t]+.*', g + ' ' + write_val, content, flags=re.M)
                    else:
                        content += '\n' + g + ' ' + write_val
            elif g == 'slaveof':
                if val_str == '':
                    if re.search(r'^[ \t]*(slaveof|replicaof)[ \t]+', content, flags=re.M):
                        content = re.sub(r'^[ \t]*(slaveof|replicaof)[ \t]+.*', '', content, flags=re.M)
                else:
                    if re.search(r'^[ \t]*#?[ \t]*(slaveof|replicaof)[ \t]+', content, flags=re.M):
                        content = re.sub(r'^[ \t]*#?[ \t]*(slaveof|replicaof)[ \t]+.*', 'replicaof ' + val_str, content, flags=re.M)
                    else:
                        content += '\nreplicaof ' + val_str
            else:
                # 行首缩进只用 [ \t]：旧实现是无锚点正则，会把配置里**其他行**（含注释）
                # 的同名片段一并改写，于是「原值重提一次」也改动文件（真机夹具实测：
                # 密码清空两次得到 #requirepass -> ##requirepass，字节每次都在漂）。
                rep = r'^[ \t]*' + g + r'[ \t]+.*'
                if re.search(rep, content, flags=re.M):
                    content = re.sub(rep, g + ' ' + target_val, content, flags=re.M)
                else:
                    content += '\n' + g + ' ' + target_val

    # 落盘 + 闭环校验：写坏要能回滚，失败绝不许假成功。
    # 旧实现不看 writeFile 结果、也不看 reload 结果，永远回「设置成功」。
    if not yf.writeFile(conf, content):
        return yf.returnJson(False, '配置文件写入失败！')
    if status() == 'start':
        res = restart()
        if res != 'ok':
            yf.writeFile(conf, original_content)
            restart()
            return yf.returnJson(False, 'Valkey 重启失败，配置已回滚！')
    return yf.returnJson(True, '设置成功')

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
    elif func == 'get_redis_conf':
        print(getRedisConf())
    elif func == 'submit_redis_conf':
        print(submitRedisConf())
    elif func == 'config_tpl':
        print(configTpl())
    elif func == 'read_config_tpl':
        print(readConfigTpl())
    else:
        print('error')
