# coding:utf-8

import sys
import io
import os
import time
import re
import ast
import json
import shlex
import subprocess
import posixpath

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import logging

_log = logging.getLogger('yf.docker')

try:
    import docker
except Exception as e:
    docker = None



app_debug = False
if yf.isAppleSystem():
    app_debug = True


#: 容器名白名单（与 docker 自身的容器名规则一致）：首字符字母数字，
#: 其后字母数字/下划线/点/短横线。真机实测旧实现把 `name` 原样交给 docker API，
#: 空名/含引号的名字要到 docker 报错才知道；且这个名字会被 `docker_exec` 拼进
#: 交给 webssh 的命令行，必须在这里一次挡住。
CONTAINER_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$')

#: 容器端口/协议白名单（协议可省略，与 docker-py 的 convert_port_bindings 一致：默认 tcp）
CONTAINER_PORT_RE = re.compile(r'^([0-9]{1,5})(/(tcp|udp))?$')
#: 镜像加速器地址白名单（写入 /etc/docker/daemon.json 的 registry-mirrors）
MIRROR_URL_RE = re.compile(r'^https?://[A-Za-z0-9._:\-]{1,200}(/[A-Za-z0-9._\-/]{0,100})?$')

#: 镜像引用白名单：registry[:port]/path[:tag][@digest]。
#: 禁止空白/引号/分号/反引号/`$()` 与前导 `-`（后者会被 docker CLI 当选项解释）。
IMAGE_REF_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._:/@-]{0,254}$')
#: 宿主机绑定地址（端口映射）：只允许 IPv4/IPv6 字面量的字符集，
#: 拒空白/引号/HTML/`$()` 等一切可注入字符（该值最终进 PortBindings JSON）
HOST_IP_RE = re.compile(r'^[0-9a-fA-F:.]{1,45}$')

#: 禁止映射进容器的宿主机目录（含其子目录）。
#: 真机实测（2026-10-10）：旧实现 `volumes=json.loads(volumes)` 无任何校验，
#: `{"/": {"bind": "/host", "mode": "rw"}}` 直接建出容器，容器内
#: `cat /host/etc/shadow` 读到了宿主机 root 口令哈希；叠加硬编码的
#: `privileged=True` 即为宿主机 root 接管。
FORBIDDEN_MOUNT_SOURCES = (
    '/', '/etc', '/root', '/boot', '/bin', '/sbin', '/lib', '/lib32', '/lib64',
    '/libx32', '/usr', '/proc', '/sys', '/dev', '/run', '/var/run',
    '/var/lib/docker', '/www/server',
)
#: 唯一例外：前端为特权容器固定拼的 cgroup 挂载（真机验证该挂载本身必需），
#: 其余 /sys 下路径一律拒绝。
ALLOWED_MOUNT_SOURCES = ('/sys/fs/cgroup',)

#: 端口映射里允许的容器内挂载目标禁止为容器根目录
MOUNT_MODE_RE = re.compile(r'^(rw|ro)$')


def toInt(val, default=None, lo=None, hi=None):
    """前端数字参数安全转换：非法/越界一律返回 default，绝不抛 ValueError。"""
    try:
        v = int(str(val).strip())
    except Exception:
        return default
    if lo is not None and v < lo:
        return default
    if hi is not None and v > hi:
        return default
    return v


def readJsonFile(path, default):
    """读取 JSON 配置：文件缺失 / `yf.readFile` 返回 False / 内容损坏 / 类型不符
    一律降级为 default。旧实现直接 `json.loads(yf.readFile(p))`，真机实测
    iplist.json 损坏时三个接口（get/del/add）全部 JSONDecodeError traceback。"""
    if not os.path.exists(path):
        return default
    content = yf.readFile(path)
    if not content:
        return default
    try:
        data = json.loads(content)
    except Exception:
        return default
    return data


def isTruthy(val):
    """前端复选框/字符串布尔：只认白名单真值，其余一律 False。"""
    return str(val if val is not None else '').strip().lower() in ('1', 'true', 'yes', 'on')


def normMountPath(path):
    """按 POSIX 语义规范化挂载路径。

    必须用 posixpath 而不是 os.path：插件只在 Linux/macOS 上跑，
    而 os.path.normpath 在 Windows 上会把 `/etc` 变成 `\\etc`，
    黑名单对比全部失效（本地 CI 与真机行为不一致）。
    """
    return posixpath.normpath(str(path).replace('\\', '/'))


def forbiddenMountSource(source):
    """返回拒绝原因；None 表示放行。source 为宿主机绝对路径。"""
    if not isinstance(source, str):
        return '路径不是字符串'
    source = source.strip()
    if not source:
        return '路径为空'
    normalized = normMountPath(source)
    # 面板目录必须先判：Windows 开发机上它是 `F:/...`，不以 `/` 开头，
    # 若先走「非绝对路径 = 命名卷」分支就永远不会命中。
    panel_dir = normMountPath(yf.getPanelDir())
    if normalized == panel_dir or normalized.startswith(panel_dir + '/'):
        return panel_dir
    if not source.startswith('/'):
        # docker 里非绝对路径是「命名卷」，不是宿主机目录，放行
        return None
    if normalized in ALLOWED_MOUNT_SOURCES:
        return None
    if normalized.endswith('docker.sock'):
        return '禁止挂载 docker 套接字'
    for item in FORBIDDEN_MOUNT_SOURCES:
        if item == '/':
            # 根目录只按等值判定：`'/'.startswith('/')` 会把所有绝对路径都判成根
            if normalized == '/':
                return '/'
            continue
        if normalized == item or normalized.startswith(item + '/'):
            return item
    return None


def validateMounts(raw):
    """校验目录映射，返回 (volumes, err)。

    **docker-py 的 volumes 字典语义：键 = 宿主机路径，`bind` = 容器内路径**
    （真机 `docker inspect` 实证：`{"/etc": {"bind": "/hostetc"}}` 得到
    `Source=/etc, Destination=/hostetc`；前端也是把「服务器目录」当键、
    「容器目录」当 bind）。因此黑名单必须卡在**键**上。
    另外 docker-py 7.2 的 `containers.run(volumes=...)` 只支持 dict 形态，
    值给字符串会 `AttributeError: 'str' object has no attribute 'get'`（未捕获 → 500）。
    """
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return ({}, None)
        try:
            volumes = json.loads(text)
        except Exception:
            return (None, '目录映射参数不合法')
    elif isinstance(raw, dict):
        volumes = raw
    else:
        return (None, '目录映射参数不合法')

    if not isinstance(volumes, dict):
        return (None, '目录映射参数不合法')

    result = {}
    for host_path, spec in volumes.items():
        if not isinstance(host_path, str) or not host_path.startswith('/') or len(host_path) > 255:
            return (None, '目录映射参数不合法')
        if not isinstance(spec, dict):
            return (None, '目录映射参数不合法')
        target = spec.get('bind')
        mode = str(spec.get('mode', 'rw')).strip().lower()
        if not MOUNT_MODE_RE.match(mode):
            return (None, '目录映射参数不合法')
        if not isinstance(target, str) or not target.startswith('/'):
            return (None, '目录映射参数不合法')
        if normMountPath(target) == '/':
            return (None, '不允许映射到容器根目录')
        reason = forbiddenMountSource(host_path)
        if reason:
            return (None, '不允许映射宿主机敏感目录: ' + host_path)
        result[host_path] = {'bind': target, 'mode': mode}
    return (result, None)


def validatePorts(raw):
    """校验端口映射，返回 (ports, host_ports, err)。

    ports 形如 `{"5432/tcp": ["0.0.0.0", 15432]}`（前端形态，真机验证该形态
    能被 docker-py 正确解析成 HostIp/HostPort）。host_ports 供防火墙放行使用。
    """
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return ({}, [], None)
        try:
            ports = ast.literal_eval(text)
        except Exception:
            return (None, None, '端口设置值范围无效，范围 [1-65535]')
    elif isinstance(raw, (dict, list, tuple)):
        ports = raw
    else:
        return (None, None, '端口设置值范围无效，范围 [1-65535]')

    if not isinstance(ports, dict):
        return (None, None, '端口设置值范围无效，范围 [1-65535]')

    result = {}
    host_ports = []
    for cport, spec in ports.items():
        m = CONTAINER_PORT_RE.match(str(cport).strip().lower())
        if not m:
            return (None, None, '端口设置值范围无效，范围 [1-65535]')
        if not (1 <= int(m.group(1)) <= 65535):
            return (None, None, '端口设置值范围无效，范围 [1-65535]')
        protocol = m.group(3) or 'tcp'
        if isinstance(spec, (list, tuple)):
            if len(spec) != 2:
                return (None, None, '端口设置值范围无效，范围 [1-65535]')
            host_ip, host_port = spec[0], spec[1]
        else:
            host_ip, host_port = '0.0.0.0', spec
        host_port = toInt(host_port, None, 1, 65535)
        if host_port is None:
            return (None, None, '端口设置值范围无效，范围 [1-65535]')
        host_ip = str(host_ip if host_ip is not None else '').strip() or '0.0.0.0'
        if host_ip not in ('0.0.0.0', '::') and not HOST_IP_RE.match(host_ip):
            return (None, None, '端口设置值范围无效，范围 [1-65535]')
        key = '%d/%s' % (int(m.group(1)), protocol)
        # 必须是 tuple：docker-py 的 convert_port_bindings 对 list 会按「多个绑定」
        # 逐个展开（真机实测报 `invalid port specification: "0.0.0.0"`），
        # 对 2 元 tuple 才按 (HostIp, HostPort) 解析。
        result[key] = (host_ip, host_port)
        host_ports.append(str(host_port))
    return (result, host_ports, None)


#: Docker 数据目录（daemon.json 的 data-root / migrate 目标）禁止落点：
#: 这些位置被写坏会让 docker 起不来或直接覆盖系统目录。
FORBIDDEN_DATA_ROOTS = (
    '/', '/etc', '/root', '/boot', '/bin', '/sbin', '/lib', '/lib32', '/lib64',
    '/libx32', '/usr', '/proc', '/sys', '/dev', '/run', '/var/run', '/www/server',
)


def invalidDataRoot(path):
    """返回拒绝原因；None 表示放行。要求绝对路径且不在系统目录内。"""
    if not isinstance(path, str) or not path.strip():
        return '路径为空'
    path = path.strip()
    if not path.startswith('/'):
        return '不是绝对路径'
    normalized = normMountPath(path)
    if normalized == '/':
        return '/'
    for item in FORBIDDEN_DATA_ROOTS:
        if item == '/':
            continue
        if normalized == item or normalized.startswith(item + '/'):
            return item
    panel_dir = normMountPath(yf.getPanelDir())
    if normalized == panel_dir or normalized.startswith(panel_dir + '/'):
        return panel_dir
    return None


def getDClient():
    if docker is None:
        raise Exception("Python模块[docker]未安装，请在终端执行 'pip3 install docker pytz' 进行安装，或重新安装本插件！")
    try:
        client = docker.from_env()
    except Exception as e:
        client = docker.DockerClient(
            base_url='unix:///var/run/docker.sock')
    return client


def getPluginName():
    return 'docker'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getConf():
    path = getServerDir() + "/redis.conf"
    return path


def getConfTpl():
    path = getPluginDir() + "/config/redis.conf"
    return path


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


def getArgs():
    """取前端参数。

    面板 `utils/plugin.py::run()` 把前端 args 作为**一个** argv 传进来
    （`/plugins/run` 的 args 字段 = JSON.stringify({...})）；`/plugins/run` 允许
    带 `version`，此时 argv 末尾才是 JSON。旧实现只看 `args_len == 1`，
    带 version 的调用会退化成 `k:v` 切分（键变成 `"1.0"`，所有带参接口恒回
    「缺少必要参数」）；且 `json.loads('null')`/`'123'` 会得到 None/int，
    随后 `checkArgs` 的 `'name' in None` 直接 TypeError 500。
    """
    argv = sys.argv[2:]
    # 1. 先逆序找完整的 JSON 字典（覆盖 version + args 两段形态）
    for arg in reversed(argv):
        text = str(arg).strip()
        if not (text.startswith('{') and text.endswith('}')):
            continue
        try:
            parsed = json.loads(text)
        except Exception as _e:
            _log.debug('[docker] getArgs 异常已忽略: %s', _e)
            continue
        if isinstance(parsed, dict):
            return parsed

    # 2. 降级：兼容旧 `k:v` / `k=v` 形态
    tmp = {}
    for arg in argv:
        text = str(arg).strip().strip('{').strip('}')
        if not text:
            continue
        sep = '=' if ('=' in text and (':' not in text or text.index('=') < text.index(':'))) else ':'
        if sep not in text:
            continue
        k, v = text.split(sep, 1)
        tmp[k.strip().strip('"').strip("'")] = v.strip().strip('"').strip("'")
    return tmp


def checkArgs(data, ck=[]):
    if not isinstance(data, dict):
        return (False, yf.returnJson(False, '缺少必要参数: ' + ','.join(ck)))
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


def status():
    try:
        c = getDClient()
        if c.ping():
            return 'start'
    except Exception as e:
        _log.debug('[docker] status 异常已忽略: %s', e)
    return 'stop'


def initDreplace():
    return ''


def dockerOp(method):
    if yf.isAppleSystem():
        return 'fail'

    # 列表化 + 白名单：method 只可能是调用方写死的四个动作，
    # 不再把参数拼进 shell（同族 SHELL_concat 面）。
    if method not in ('start', 'stop', 'restart', 'reload'):
        return 'fail'
    rc, out, err = yf.execShellRc(['systemctl', method, getPluginName()],
                                  shell=False, timeout=300)
    if rc == 0:
        return 'ok'
    # 旧实现以「stderr 为空」当成功：systemctl 失败时 stderr 可能为空 → 假成功
    return (err or out or 'fail').strip() or 'fail'


def start():
    return dockerOp('start')


def stop():
    return dockerOp('stop')


def restart():
    status = dockerOp('restart')
    return status


def reload():
    return dockerOp('reload')


def initdStatus():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    # `systemctl status | grep loaded | grep "enabled;"` 依赖人类可读输出，
    # 改 is-enabled 退出码 + 已启用态白名单（同 D09/D10/D11）。
    rc, out, _err = yf.execShellRc(['systemctl', 'is-enabled', getPluginName()],
                                   shell=False, timeout=30)
    if rc == 0:
        return 'ok'
    return 'ok' if (out or '').strip() in ('enabled', 'enabled-runtime',
                                           'static', 'indirect', 'generated', 'alias') else 'fail'


def initdInstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    rc, out, err = yf.execShellRc(['systemctl', 'enable', getPluginName()],
                                  shell=False, timeout=60)
    if rc == 0:
        return 'ok'
    return (err or out or 'fail').strip() or 'fail'


def initdUinstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    rc, out, err = yf.execShellRc(['systemctl', 'disable', getPluginName()],
                                  shell=False, timeout=60)
    if rc == 0:
        return 'ok'
    return (err or out or 'fail').strip() or 'fail'

# UTC时间转换为时间戳


def utc_to_local(utc_time_str, utc_format='%Y-%m-%dT%H:%M:%S'):
    import datetime
    import time
    try:
        utc_dt = datetime.datetime.strptime(utc_time_str, utc_format)
        utc_dt = utc_dt.replace(tzinfo=datetime.timezone.utc)
        local_dt = utc_dt.astimezone()
        local_format = "%Y-%m-%d %H:%M"
        time_str = local_dt.strftime(local_format)
        return int(time.mktime(time.strptime(time_str, local_format)))
    except Exception as _e:
        _log.debug('[docker] utc_to_local 异常已忽略: %s', _e)
        return 0


def conList():
    c = getDClient()
    clist = c.containers.list(all=True)
    conList = []
    for con in clist:
        tmp = con.attrs
        tmp['Created'] = utc_to_local(tmp['Created'].split('.')[0])
        conList.append(tmp)
    return conList


def conListData():
    try:
        clist = conList()
    except Exception as e:
        err_msg = str(e)
        if 'Connection' in err_msg or 'connect' in err_msg.lower() or 'refused' in err_msg.lower():
            return yf.returnJson(False, '未开启Docker')
        return yf.returnJson(False, '获取容器列表失败: ' + err_msg)
    return yf.returnJson(True, 'ok', clist)


def dockerRemoveCon():
    args = getArgs()
    data = checkArgs(args, ['Hostname'])
    if not data[0]:
        return data[1]

    Hostname = str(args['Hostname']).strip()

    c = getDClient()
    try:
        conFind = c.containers.get(Hostname)
        try:
            path_list = conFind.attrs['GraphDriver'][
                'Data']['LowerDir'].split(':')
            for i in path_list:
                # 列表化：路径来自 docker 自身，含空格/特殊字符时不得被 shell 二次解释
                yf.execShellRc(['chattr', '-R', '-i', i], shell=False, timeout=30)
        except Exception as _e:
            _log.debug('[docker] dockerRemoveCon 异常已忽略: %s', _e)
        # v=True：连带删除镜像声明的匿名卷。真机实测旧实现（不传 v）下
        # `docker volume ls` 累积了 42 个 ACTIVE=0 的孤儿卷（42.82MB 可回收）。
        conFind.remove(force=True, v=True)
        return yf.returnJson(True, '成功删除!')
    except docker.errors.APIError as ex:
        return yf.returnJson(False, '删除失败!' + str(ex))
    except Exception as ex:
        return yf.returnJson(False, '删除失败!' + str(ex))


def dockerLogCon():

    args = getArgs()
    data = checkArgs(args, ['Hostname'])
    if not data[0]:
        return data[1]

    Hostname = str(args['Hostname']).strip()

    c = getDClient()
    try:
        conFind = c.containers.get(Hostname)
        if not conFind:
            return yf.returnJson(False, 'The specified container does not exist!')
        log = conFind.logs()
        if not isinstance(log, str):
            log = log.decode()
        return yf.returnJson(True, log)
    except docker.errors.APIError as ex:
        return yf.returnJson(False, 'Get Logs failed')


def dockerRunCon():
    # 启动容器
    args = getArgs()
    data = checkArgs(args, ['Hostname'])
    if not data[0]:
        return data[1]

    Hostname = str(args['Hostname']).strip()
    c = getDClient()
    try:
        conFind = c.containers.get(Hostname)
        if not conFind:
            return yf.returnJson(False, 'The specified container does not exist!')
        conFind.start()
        return yf.returnJson(True, '启动成功!')
    except docker.errors.APIError as ex:
        return yf.returnJson(False, '启动失败!' + str(ex))
    except Exception as ex:
        return yf.returnJson(False, '启动失败!' + str(ex))


def dockerStopCon():
    # 停止容器
    args = getArgs()
    data = checkArgs(args, ['Hostname'])
    if not data[0]:
        return data[1]

    Hostname = str(args['Hostname']).strip()
    c = getDClient()
    try:
        conFind = c.containers.get(Hostname)
        if not conFind:
            return yf.returnJson(False, 'The specified container does not exist!')
        conFind.stop()
        return yf.returnJson(True, '停止成功!')
    except docker.errors.APIError as ex:
        return yf.returnJson(False, '停止失败!' + str(ex))
    except Exception as ex:
        return yf.returnJson(False, '停止失败!' + str(ex))


def dockerExec():
    # 容器执行命令
    args = getArgs()
    data = checkArgs(args, ['Hostname'])
    if not data[0]:
        return data[1]

    Hostname = str(args['Hostname']).strip()

    debug_path = 'data/debug.pl'
    if os.path.exists(debug_path):
        return yf.returnJson(False, '开发模式不能进入!')

    # 容器名白名单：该返回值会被前端直接送进 webssh 的命令行
    # （`clear && docker container exec -it <name> /bin/sh`），
    # 真机实测旧实现下 Hostname=`a'; touch /root/PWNED; #` 原样回到响应里。
    if not CONTAINER_NAME_RE.match(Hostname):
        return yf.returnJson(False, '容器名称不合法，仅允许字母、数字、下划线、点和短横线')

    c = getDClient()
    try:
        conFind = c.containers.get(Hostname)
        cmd = 'docker container exec -it %s /bin/sh' % yf.shlexQuote(Hostname)
        return yf.returnJson(True, cmd)
    except docker.errors.APIError as ex:
        return yf.returnJson(False, '连接失败!')
    except Exception as ex:
        return yf.returnJson(False, '连接失败!')


def imageList():
    imageList = []
    c = getDClient()
    ilist = c.images.list()

    disk_usage_map = {}
    try:
        out, err = yf.execShell("docker image ls --format '{{.Repository}}:{{.Tag}}|{{.Size}}'")
        if out:
            for line in out.strip().split('\n'):
                parts = line.split('|')
                if len(parts) >= 2:
                    disk_usage_map[parts[0]] = parts[1]
    except Exception as _e:
        _log.debug('[docker] imageList 异常已忽略: %s', _e)
    for image in ilist:
        tmp_attrs = image.attrs
        repo_tags = tmp_attrs.get('RepoTags', None)
        # 跳过悬空镜像（RepoTags 为 None 或空列表）
        if not repo_tags:
            continue
        if len(repo_tags) == 1:
            tmp_image = {}
            tmp_image['Id'] = tmp_attrs['Id'].split(':')[1][:12]
            tmp_image['RepoTags'] = repo_tags[0]
            tmp_image['Size'] = tmp_attrs['Size']
            tmp_image['VirtualSize'] = tmp_attrs.get('VirtualSize', tmp_attrs['Size'])
            tmp_image['SharedSize'] = tmp_attrs.get('SharedSize', 0)
            tmp_image['DiskUsage'] = disk_usage_map.get(repo_tags[0], '')
            tmp_image['Labels'] = tmp_attrs.get('Config', {}).get('Labels', None)
            tmp_image['Comment'] = tmp_attrs.get('Comment', '')
            tmp_image['Created'] = utc_to_local(
                tmp_attrs['Created'].split('.')[0])
            imageList.append(tmp_image)
        else:
            for i in range(len(repo_tags)):
                tmp_image = {}
                tmp_image['Id'] = tmp_attrs['Id'].split(':')[1][:12]
                tmp_image['RepoTags'] = repo_tags[i]
                tmp_image['Size'] = tmp_attrs['Size']
                tmp_image['VirtualSize'] = tmp_attrs.get('VirtualSize', tmp_attrs['Size'])
                tmp_image['SharedSize'] = tmp_attrs.get('SharedSize', 0)
                tmp_image['DiskUsage'] = disk_usage_map.get(repo_tags[i], '')
                tmp_image['Labels'] = tmp_attrs.get('Config', {}).get('Labels', None)
                tmp_image['Comment'] = tmp_attrs.get('Comment', '')
                tmp_image['Created'] = utc_to_local(
                    tmp_attrs['Created'].split('.')[0])
                imageList.append(tmp_image)
    imageList = sorted(imageList, key=lambda x: x['Created'], reverse=True)
    return imageList



def docker_pull_with_mirror():
    args = getArgs()
    data = checkArgs(args, ['images', 'mirrors'])
    if not data[0]:
        return data[1]

    original_images = str(args['images']).strip()
    mirrors_str = str(args['mirrors']).strip()

    if not IMAGE_REF_RE.match(original_images):
        return yf.returnJson(False, '镜像名称不合法')

    if ':' not in original_images:
        original_images = original_images + ':latest'

    import shlex
    import time as _time

    script_path = yf.getPluginDir() + '/docker/pull_task.py'

    # 用面板自己的解释器（sys.executable）：真机实测 Debian 12 只有 python3，
    # 旧实现写死的 `python` 不存在 → 拉取任务 100% 「command not found」失败。
    execstr = "cd " + yf.getPluginDir() + "/docker && " + shlex.quote(sys.executable) + \
        " " + shlex.quote(script_path) + " " + shlex.quote(original_images) + " " + shlex.quote(mirrors_str)

    # 将拉取任务加入系统的后台任务队列（消息盒子）
    yf.M('tasks').add('name,type,status,add_time,start,end,cmd',
                      ('拉取 Docker 镜像: ' + original_images, 'execshell', '0',
                       _time.strftime('%Y-%m-%d %H:%M:%S'), '0', '0', execstr))

    # 唤醒后台队列
    yf.triggerTask()

    return yf.returnJson(True, '已将拉取任务加入消息盒子队列，请在任务列表中查看实时进度！')


def dockerPull():
    # pull Dockr 官方镜像
    args = getArgs()
    data = checkArgs(args, ['images'])
    if not data[0]:
        return data[1]

    images = str(args['images']).strip()
    if not IMAGE_REF_RE.match(images):
        return yf.returnJson(False, '镜像名称不合法')
    if ':' in images:
        pass
    else:
        images = images + ':latest'

    c = getDClient()
    try:
        ret = c.images.pull(images)
        if ret:
            return yf.returnJson(True, '拉取成功！')
        else:
            return yf.returnJson(False, '拉取失败，请检查镜像名称或是否需要登录docker进行下载')
    except Exception as e:
        ret = yf.execShell('docker image pull %s' % shlex.quote(images))
        stderr_out = ret[1].strip() if len(ret) > 1 else ret[-1].strip()
        if 'Error' in stderr_out or 'error' in stderr_out or 'invalid' in stderr_out or 'not found' in stderr_out or 'denied' in stderr_out:
            err_msg = stderr_out if stderr_out else str(e)
            return yf.returnJson(False, '拉取失败: ' + err_msg)
        else:
            return yf.returnJson(True, '拉取成功！')


def dockerPlulPath(path):
    if not path and path == '':
        return yf.returnJson(False, 'Invalid address')

    path = str(path).strip()
    if not IMAGE_REF_RE.match(path):
        return yf.returnJson(False, '镜像名称不合法')

    ret = yf.execShell('docker image pull %s' % shlex.quote(path))
    stderr_out = ret[1].strip() if len(ret) > 1 else ret[-1].strip()
    if 'Error' in stderr_out or 'error' in stderr_out or 'invalid' in stderr_out or 'not found' in stderr_out or 'denied' in stderr_out:
        return yf.returnJson(False, '拉取失败: ' + stderr_out)
    else:
        return yf.returnJson(True, '拉取成功！')


def dockerPullReg():
    # pull Dockr 官方镜像
    args = getArgs()
    data = checkArgs(args, ['path'])
    if not data[0]:
        return data[1]

    path = args['path']
    return dockerPlulPath(path)


# 判断镜像是否存在
def checkImage(path):
    image_list = imageList()
    for i in image_list:
        if path == i["RepoTags"]:
            return yf.returnData(False, '镜像已存在!')


def dockerPullPrivateNew():
    # pull Dockr 官方镜像
    args = getArgs()
    data = checkArgs(args, ['path'])
    if not data[0]:
        return data[1]

    path = args['path']
    check = checkImage(path)
    if check:
        return yf.getJson(check)

    my_repo = repoList()
    if not isinstance(my_repo, dict) or not my_repo.get('data'):
        return yf.returnJson(False, '未登录任何私人存储库，请登录然后拉取')
    return dockerPlulPath(path)


def imageListData():
    try:
        ilist = imageList()
    except Exception as e:
        err_msg = str(e)
        if 'Connection' in err_msg or 'connect' in err_msg.lower() or 'refused' in err_msg.lower():
            return yf.returnJson(False, '未开启Docker')
        return yf.returnJson(False, '获取镜像列表失败: ' + err_msg)
    return yf.returnJson(True, 'ok', ilist)


def dockerRemoveImage():
    args = getArgs()
    data = checkArgs(args, ['imageId', 'repoTags'])
    if not data[0]:
        return data[1]

    repoTags = args['repoTags']
    imageId = args['imageId']

    c = getDClient()
    try:
        c.images.remove(repoTags)
        return yf.returnJson(True, '成功删除')
    except Exception as _e:
        _log.debug('[docker] dockerRemoveImage 异常已忽略: %s', _e)
        try:
            c.images.remove(imageId)
            return yf.returnJson(True, '成功删除!')
        except docker.errors.APIError as ex:
            return yf.returnJson(False, '删除失败, 当前镜像正在使用! ' + str(ex))
        except Exception as ex:
            return yf.returnJson(False, '删除失败, 当前镜像正在使用! ' + str(ex))


def getImageListFunc(dbname=''):
    bkDir = yf.getFatherDir() + '/backup/docker'
    blist = os.listdir(bkDir)
    r = []

    bname = 'db_' + dbname
    blen = len(bname)
    for x in blist:
        fbstr = x[0:blen]
        if fbstr == bname:
            r.append(x)
    return r


def dockerImagePickDir():
    bkDir = yf.getFatherDir() + '/backup/docker'
    if not os.path.exists(bkDir):
        os.makedirs(bkDir, exist_ok=True)
    return yf.returnJson(True, 'ok', bkDir)


def dockerImagePickList():
    bkDir = yf.getFatherDir() + '/backup/docker'
    if not os.path.exists(bkDir):
        try:
            os.makedirs(bkDir, exist_ok=True)
        except Exception as _e:
            _log.debug('[docker] dockerImagePickList 异常已忽略: %s', _e)

    # 严格限定支持的镜像归档扩展名
    allowed_exts = ('.tar', '.tar.gz', '.tgz')

    rr = []
    try:
        if os.path.exists(bkDir):
            filenames = os.listdir(bkDir)
            for fname in filenames:
                if fname.startswith('.'):
                    continue
                lower_name = fname.lower()
                if not any(lower_name.endswith(ext) for ext in allowed_exts):
                    continue

                p = os.path.join(bkDir, fname).replace('\\', '/')
                if not os.path.isfile(p):
                    continue

                rsize = os.path.getsize(p)
                mtime = os.path.getmtime(p)
                t_struct = time.localtime(mtime)

                data = {
                    'name': fname,
                    'size': yf.toSize(rsize),
                    'raw_size': rsize,
                    'mtime': mtime,
                    'time': time.strftime('%Y-%m-%d %H:%M:%S', t_struct),
                    'file': p
                }
                rr.append(data)

            # 按修改时间倒序排列（最新备份排在前面）
            rr.sort(key=lambda x: x['mtime'], reverse=True)
    except Exception as ex:
        return yf.returnJson(False, '获取镜像备份列表失败: ' + str(ex))

    return yf.returnJson(True, 'ok', rr)


def dockerImagePickSave():
    # image 导出打包
    args = getArgs()
    data = checkArgs(args, ['images'])
    if not data[0]:
        return data[1]

    raw_images = args.get('images', '').strip()
    if not raw_images:
        return yf.returnJson(False, '请至少选择一个需要导出的镜像')

    img_list = raw_images.split()
    if not img_list:
        return yf.returnJson(False, '请选择有效的镜像名称')

    # 分别安全转义每一个镜像名称并以空格连接
    quoted_images = ' '.join(shlex.quote(img) for img in img_list)

    bkDir = yf.getFatherDir() + '/backup/docker'
    if not os.path.exists(bkDir):
        try:
            os.makedirs(bkDir, exist_ok=True)
        except Exception as _e:
            _log.debug('[docker] dockerImagePickSave 异常已忽略: %s', _e)

    file_name = bkDir + '/' + str(time.strftime('%Y%m%d_%H%M%S', time.localtime())) + '.tar.gz'
    quoted_file = shlex.quote(file_name)

    try:
        cmd = 'docker image save %s | gzip > %s' % (quoted_images, quoted_file)
        out, err = yf.execShell(cmd)

        # 检查是否成功生成文件且大小大于0
        if not os.path.exists(file_name) or os.path.getsize(file_name) == 0:
            if os.path.exists(file_name):
                try:
                    os.remove(file_name)
                except Exception as _e:
                    _log.debug('[docker] dockerImagePickSave 异常已忽略: %s', _e)
            err_msg = (err or '').strip() or (out or '').strip()
            if not err_msg:
                err_msg = '导出镜像失败，请检查 Docker 服务状态及镜像是否存在'
            return yf.returnJson(False, '导出镜像失败: ' + err_msg)

        return yf.returnJson(True, '导出镜像 {} 成功!'.format(os.path.basename(file_name)))
    except Exception as ex:
        if os.path.exists(file_name) and os.path.getsize(file_name) == 0:
            try:
                os.remove(file_name)
            except Exception as _e:
                _log.debug('[docker] dockerImagePickSave 异常已忽略: %s', _e)
        return yf.returnJson(False, '操作失败: ' + str(ex))


def dockerImagePickLoad():
    # 镜像文件导入
    args = getArgs()
    data = checkArgs(args, ['file'])
    if not data[0]:
        return data[1]

    file_path = args.get('file', '').strip()
    if not file_path:
        return yf.returnJson(False, '缺少文件路径参数')

    bkDir = os.path.realpath(os.path.abspath(yf.getFatherDir() + '/backup/docker'))
    abs_file = os.path.realpath(os.path.abspath(file_path))

    # 路径安全检查：防止路径遍历，限制在 backup/docker 目录下
    # （realpath 而非 abspath：目录内放一个指向 /etc/shadow 的软链就能绕过 abspath 判定）
    try:
        common = os.path.commonpath([abs_file, bkDir])
        if common != bkDir:
            return yf.returnJson(False, '非法的镜像文件路径，仅允许导入备份目录下的文件')
    except Exception:
        return yf.returnJson(False, '文件路径校验失败')

    if not os.path.exists(abs_file) or not os.path.isfile(abs_file):
        return yf.returnJson(False, '镜像文件不存在: ' + os.path.basename(file_path))

    lower_path = abs_file.lower()
    allowed_exts = ('.tar', '.tar.gz', '.tgz')
    if not any(lower_path.endswith(ext) for ext in allowed_exts):
        return yf.returnJson(False, '不支持的文件格式，仅支持 .tar, .tar.gz, .tgz 镜像归档文件')

    try:
        quoted_path = shlex.quote(abs_file)
        if lower_path.endswith('.tar'):
            cmd = 'docker image load < %s' % quoted_path
        else:
            cmd = 'gunzip -c %s | docker image load' % quoted_path

        out, err = yf.execShell(cmd)
        err_str = (err or '').strip()
        out_str = (out or '').strip()

        # 检查是否包含明确的错误响应
        lower_err = err_str.lower()
        if 'error response from daemon' in lower_err or 'error' in lower_err or 'not in gzip format' in lower_err or 'invalid tar' in lower_err:
            return yf.returnJson(False, '导入镜像失败: ' + (err_str or out_str))

        if 'error response from daemon' in out_str.lower():
            return yf.returnJson(False, '导入镜像失败: ' + out_str)

        msg = '导入镜像文件成功!'
        if 'Loaded image' in out_str:
            loaded_lines = [line.strip() for line in out_str.split('\n') if 'Loaded image' in line]
            if loaded_lines:
                msg = '导入成功: ' + ', '.join(loaded_lines)

        return yf.returnJson(True, msg)
    except Exception as ex:
        return yf.returnJson(False, '操作失败: ' + str(ex))



def dockerLoginCheck(user_name, user_pass, registry):
    # 登陆验证。口令只走 stdin（--password-stdin）：旧实现把 `-p <口令>` 拼进命令行，
    # 口令会出现在宿主机 `ps` 输出里（本机任何用户可见），docker CLI 自身也会告警。
    cmd = ['docker', 'login', '--username', str(user_name), '--password-stdin']
    registry = str(registry or '').strip()
    if registry:
        cmd.append(registry)
    try:
        proc = subprocess.run(cmd, input=str(user_pass), capture_output=True,
                              text=True, timeout=60)
    except Exception as _e:
        _log.debug('[docker] dockerLoginCheck 异常已忽略: %s', _e)
        return False
    return proc.returncode == 0


def loadIpList(ipConf):
    """返回 (iplist, err)；文件缺失视为空池，损坏/类型不对返回可翻译信封。

    损坏时不得静默覆盖：旧实现把损坏文件当空列表后写回，用户原有 IP 池被清空。
    """
    data = readJsonFile(ipConf, None)
    if data is None:
        if os.path.exists(ipConf):
            return (None, yf.returnJson(False, 'IP地址池数据已损坏，请先删除 iplist.json'))
        return ([], None)
    if not isinstance(data, list):
        return (None, yf.returnJson(False, 'IP地址池数据已损坏，请先删除 iplist.json'))
    return ([i for i in data if isinstance(i, dict)], None)


def getDockerIpListData():
    # 取IP列表
    path = getServerDir()
    ipConf = path + '/iplist.json'
    iplist, err = loadIpList(ipConf)
    if err:
        return []
    return iplist


def getDockerIpList():
    data = getDockerIpListData()
    return yf.returnJson(True, 'ok!', data)


def dockerAddIP():
    # 添加IP
    args = getArgs()
    data = checkArgs(args, ['address', 'netmask', 'gateway'])
    if not data[0]:
        return data[1]

    path = getServerDir()
    ipConf = path + '/iplist.json'
    iplist, err = loadIpList(ipConf)
    if err:
        return err

    ipInfo = {}
    for field in ('address', 'netmask', 'gateway'):
        value = str(args[field]).strip()
        # 该值会被拼进端口映射的绑定地址（dockerCreateCon），也是前端表格的回显源：
        # 旧实现任意字符串（含 `<img src=x onerror=...>`）都存进 iplist.json。
        if not value or not HOST_IP_RE.match(value):
            return yf.returnJson(False, 'IP地址不合法')
        ipInfo[field] = value
    iplist.append(ipInfo)
    if not yf.writeFile(ipConf, json.dumps(iplist)):
        return yf.returnJson(False, '添加失败!')
    return yf.returnJson(True, '添加成功!')


def dockerDelIP():
    # 删除IP
    args = getArgs()
    data = checkArgs(args, ['address'])
    if not data[0]:
        return data[1]

    path = getServerDir()
    ipConf = path + '/iplist.json'
    iplist, err = loadIpList(ipConf)
    if err:
        return err
    if not iplist:
        return yf.returnJson(False, '指定的IP不存在。！')
    newList = []
    for ipInfo in iplist:
        if ipInfo.get('address') == args['address']:
            continue
        newList.append(ipInfo)
    if not yf.writeFile(ipConf, json.dumps(newList)):
        return yf.returnJson(False, '删除失败!')
    return yf.returnJson(True, '成功删除!')


def getDockerCreateInfo():
    # 取创建依赖
    import psutil
    data = {}
    data['images'] = imageList()
    data['memSize'] = int(psutil.virtual_memory().total / 1024 / 1024)
    data['iplist'] = getDockerIpListData()
    return yf.returnJson(True, 'ok!', data)


def __release_port(port):
    try:
        from utils.firewall import Firewall as YfFirewall
        YfFirewall.instance().addAcceptPort(str(port), 'docker', 'port')
        return port
    except Exception as e:
        return "Release failed {}".format(e)


def dockerPortCheck():
    args = getArgs()
    data = checkArgs(args, ['port'])
    if not data[0]:
        return data[1]

    port = str(args['port']).strip()
    # 前端传的是「地址:端口」（地址为 `*` 表示 0.0.0.0）；旧实现把整串当端口号
    # 丢给 socket.connect → getaddrinfo 直接报错 → 恒回「未被占用」，
    # 冲突检测形同虚设（默认的 0.0.0.0 走 `*` 分支，100% 命中这个缺陷）。
    if ':' in port:
        port = port.rsplit(':', 1)[1].strip()
    if not re.match(r'^[0-9]{1,5}$', port) or not (1 <= int(port) <= 65535):
        return yf.returnJson(False, '端口设置值范围无效，范围 [1-65535]')

    if IsPortExists(port):
        return yf.returnJson(True, 'ok')
    return yf.returnJson(False, 'fail')


def IsPortExists(port):
    # 判断端口是否被占用（任一地址上监听即视为占用）。
    # 必须转成 int：socket.connect 在 Windows 上不接受数字字符串端口
    # （Linux 上恰好能过），同一份代码两个平台行为不一致。
    port = toInt(port, None, 1, 65535)
    if port is None:
        return False
    for ip in ('0.0.0.0', '127.0.0.1'):
        if __check_dst_port(ip=ip, port=port):
            return True
    return False


def __check_dst_port(ip, port, timeout=3):
    # 端口检测
    import socket
    ok = True
    try:
        s = socket.socket()
        s.settimeout(timeout)
        s.connect((ip, port))
        s.close()
    except Exception as _e:
        _log.debug('[docker] __check_dst_port 异常已忽略: %s', _e)
        ok = False
    return ok


def dockerCreateCon():
    args = getArgs()
    data = checkArgs(args, ['name', 'environments', 'command',
                            'entrypoint', 'image', 'mem_limit', 'ports', 'volumes'])
    if not data[0]:
        return data[1]

    name = str(args['name']).strip()
    if not CONTAINER_NAME_RE.match(name):
        return yf.returnJson(False, '容器名称不合法，仅允许字母、数字、下划线、点和短横线')

    environments = str(args['environments']).strip().split()

    command = args['command'] if args['command'] != '' else None
    entrypoint = args['entrypoint'] if args['entrypoint'] != '' else None

    image = str(args['image']).strip()
    if not IMAGE_REF_RE.match(image):
        return yf.returnJson(False, '镜像名称不合法')

    mem_limit = toInt(args['mem_limit'], None, 1, 1048576)
    if mem_limit is None:
        return yf.returnJson(False, '内存配额不合法')

    cpu_shares = toInt(args.get('cpu_shares', 100), None, 1, 100)
    if cpu_shares is None:
        # 旧实现是裸 int()：`cpu_shares=abc` 真机实测 ValueError 直接冒到前端
        return yf.returnJson(False, 'CPU配额设置值范围应为 [1-100]!')

    # 安全：原 eval(ports) 的任意代码执行已改 ast.literal_eval；
    # 本次再补齐「每个映射的合法性」校验（容器端口/协议/宿主端口/绑定地址）。
    ports_parsed, host_ports, err = validatePorts(args['ports'])
    if err:
        return yf.returnJson(False, err)

    volumes_parsed, err = validateMounts(args['volumes'])
    if err:
        return yf.returnJson(False, err)

    # 特权容器默认关闭（旧实现硬编码 privileged=True，用户无法选择，
    # 且叠加未校验的卷挂载 = 宿主机 root 接管）。需要时由前端显式传 privileged。
    privileged = isTruthy(args.get('privileged', ''))

    try:
        c = getDClient()
        conObject = c.containers.run(
            name=name,
            image=image,
            mem_limit=str(mem_limit) + 'M',
            ports=ports_parsed,
            auto_remove=False,
            command=command,
            detach=True,
            stdin_open=True,
            tty=True,
            entrypoint=entrypoint,
            privileged=privileged,
            volumes=volumes_parsed,
            cpu_shares=cpu_shares,
            environment=environments
        )
        if conObject:
            # 映射到宿主机的端口逐个放行：旧实现把整个 ports 字典字符串
            # 传给 __release_port，firewall 侧 parsePortSpec 直接判非法 →
            # 规则一条也没下发（真机实测 addAcceptPort 返回 False），
            # 容器起了但端口对外不通。
            for host_port in host_ports:
                __release_port(host_port)
            return yf.returnJson(True, '创建成功!')

        return yf.returnJson(False, '创建失败!')
    except docker.errors.APIError as ex:
        return yf.returnJson(False, '创建失败!' + str(ex))
    except Exception as ex:
        # docker-py 自身对非法参数会抛 ValueError/AttributeError
        # （如 volumes 值给字符串）——旧实现只 catch APIError，直接 500 traceback
        return yf.returnJson(False, '创建失败!' + str(ex))


def dockerLogin():
    args = getArgs()

    # print(args)
    data = checkArgs(args, ['user', 'passwd', 'hub_name',
                            'namespace', 'registry', 'repository_name'])
    if not data[0]:
        return data[1]

    user_name = args['user']
    user_pass = args['passwd']
    registry = args['registry']
    hub_name = args['hub_name']
    namespace = args['namespace']
    repository_name = args['repository_name']

    ret_status = dockerLoginCheck(user_name, user_pass, registry)
    path = getServerDir()
    if ret_status:
        user_file = path + '/user.json'
        user_info = readJsonFile(user_file, [])
        if not isinstance(user_info, list):
            return yf.returnJson(False, '登录失败!')

        ret = {}
        ret['user_name'] = user_name
        # 口令不回存：该字段在整个插件里没有任何读取方（docker 自身的凭据在
        # ~/.docker/config.json），旧实现把明文口令写进 data/docker/user.json。
        ret['user_pass'] = ''
        ret['registry'] = registry
        ret['hub_name'] = hub_name
        ret['namespace'] = namespace
        ret['repository_name'] = repository_name
        if not registry:
            ret['registry'] = "docker.io"
        user_info.append(ret)
        if not yf.writeFile(user_file, json.dumps(user_info)):
            return yf.returnJson(False, '登录失败!')
        return yf.returnJson(True, '成功登录!')
    return yf.returnJson(False, '登录失败!')


# 删除用户信息
def delete_user_info(registry):
    path = getServerDir()
    user_file = path + '/user.json'
    user_info = readJsonFile(user_file, [])
    if not isinstance(user_info, list):
        return False
    # 旧实现边遍历边 del，命中后立即 return：同名多条目只删得掉一条
    kept = [i for i in user_info
            if not (isinstance(i, dict) and registry in i.values())]
    if len(kept) == len(user_info):
        return False
    yf.writeFile(user_file, json.dumps(kept))
    return True


def dockerLogout():
    args = getArgs()
    data = checkArgs(args, ['registry'])
    if not data[0]:
        return data[1]

    registry = str(args['registry']).strip()
    # 旧实现：非 docker.io 的 registry 直接落到函数末尾返回 None（假成功）；
    # 且无论 docker logout 成败都回 status=true（失败也报「退出失败」但为绿色）。
    target = '' if registry in ('docker.io', '') else registry
    cmd = ['docker', 'logout'] if not target else ['docker', 'logout', target]
    # execShell 的 shell=False 分支会把 list 交给 shlex.split（TypeError），
    # 需要列表化调用必须走 execShellRc（真机实测 execShell 会抛 traceback）。
    rc, out, err = yf.execShellRc(cmd, shell=False, timeout=60)
    removed = delete_user_info(registry or 'docker.io')
    # 旧实现无论成败都回 status=true（假成功），且非 docker.io 的 registry 直接
    # 落到函数末尾返回 None。真机实测 `docker logout` 对未登录的 registry 也回
    # “Removing login credentials …” 且 rc=0，因此还要看插件自己的记录有没有被删掉。
    if rc != 0 or not removed:
        return yf.returnJson(False, '退出失败')
    return yf.returnJson(True, '退出成功')



def get_daemon_json_path():
    import os
    if yf.isAppleSystem():
        return os.path.expanduser('~/.docker/daemon.json')
    elif os.name == 'nt':
        return os.path.expanduser('~/.docker/daemon.json')
    return '/etc/docker/daemon.json'

def get_accelerator():
    daemon_file = get_daemon_json_path()
    if not os.path.exists(daemon_file):
        return yf.returnJson(True, 'ok', [])
    try:
        content = yf.readFile(daemon_file)
        if not content:
            return yf.returnJson(True, 'ok', [])
        data = json.loads(content)
        mirrors = data.get('registry-mirrors', [])
        if isinstance(mirrors, str):
            mirrors = [mirrors]
        return yf.returnJson(True, 'ok', mirrors)
    except Exception as e:
        return yf.returnJson(False, '解析 daemon.json 失败: ' + str(e))

def set_accelerator():
    args = getArgs()
    data = checkArgs(args, ['mirrors'])
    if not data[0]:
        return data[1]

    mirrors_str = args['mirrors']
    try:
        if mirrors_str.strip() == '':
            mirrors = []
        else:
            mirrors = json.loads(mirrors_str)
            if not isinstance(mirrors, list):
                return yf.returnJson(False, '参数格式错误，期望 JSON 数组')
    except Exception as _e:
        _log.debug('[docker] set_accelerator 异常已忽略: %s', _e)
        return yf.returnJson(False, '参数解析失败，非有效的 JSON 数组')

    # 逐条校验：这些值会写进 /etc/docker/daemon.json 并重启 docker，
    # 非 URL 内容（如 `</textarea><script>` 或随便一行垃圾）既会写坏守护进程配置
    # （docker 起不来 = 全机容器宕），又会被 get_accelerator → 前端 textarea 原样回显。
    for item in mirrors:
        if not isinstance(item, str) or not MIRROR_URL_RE.match(item.strip()):
            return yf.returnJson(False, '镜像加速器地址不合法')
    mirrors = [item.strip() for item in mirrors]

    daemon_file = get_daemon_json_path()
    daemon_dir = os.path.dirname(daemon_file)
    if not os.path.exists(daemon_dir):
        try:
            os.makedirs(daemon_dir)
        except Exception as _e:
            _log.debug('[docker] set_accelerator 异常已忽略: %s', _e)

    data = {}
    if os.path.exists(daemon_file):
        try:
            content = yf.readFile(daemon_file)
            if content:
                data = json.loads(content)
        except Exception as _e:
            _log.debug('[docker] set_accelerator 异常已忽略: %s', _e)

    if mirrors:
        data['registry-mirrors'] = mirrors
    else:
        if 'registry-mirrors' in data:
            del data['registry-mirrors']

    try:
        yf.writeFile(daemon_file, json.dumps(data, indent=4))
        if not yf.isAppleSystem() and os.name != 'nt':
            yf.execShell('systemctl daemon-reload')
            yf.execShell('systemctl restart docker')
        return yf.returnJson(True, '加速器配置已保存并重启 Docker 服务使之生效！')
    except Exception as e:
        return yf.returnJson(False, '配置保存失败: ' + str(e))

def repoList():
    path = getServerDir()
    repostory_info = []
    user_file = path + '/user.json'

    user_info = readJsonFile(user_file, [])
    if not isinstance(user_info, list):
        return yf.returnJson(True, 'ok', repostory_info)
    for i in user_info:
        if not isinstance(i, dict):
            continue
        tmp = {}
        tmp["hub_name"] = i.get("hub_name", '')
        tmp["registry"] = i.get("registry", '')
        tmp["namespace"] = i.get("namespace", '')
        tmp['repository_name'] = i.get("repository_name", '')
        repostory_info.append(tmp)

    return yf.returnJson(True, 'ok', repostory_info)


def getDockerDirInfo():
    try:
        # Get Docker Root Dir
        cmd_root = "docker info --format '{{.DockerRootDir}}'"
        out, err = yf.execShell(cmd_root)
        docker_root = out.strip() if out else "/var/lib/docker"

        # Size of images
        cmd_df = "docker system df --format '{{.Type}}|{{.Size}}'"
        out_df, err_df = yf.execShell(cmd_df)
        image_size = '0B'
        container_size = '0B'
        if out_df:
            for line in out_df.strip().split('\n'):
                parts = line.split('|')
                if len(parts) >= 2:
                    if parts[0] == 'Images':
                        image_size = parts[1]
                    elif parts[0] == 'Containers':
                        container_size = parts[1]
        
        data = {
            'docker_root': docker_root,
            'image_size': image_size,
            'container_size': container_size,
        }
        return yf.returnJson(True, 'ok', data)
    except Exception as e:
        return yf.returnJson(False, str(e))


def checkDockerMigrateSpace():
    args = getArgs()
    data = checkArgs(args, ['new_path'])
    if not data[0]:
        return data[1]

    new_path = str(args['new_path']).strip()
    if not new_path:
        return yf.returnJson(False, '新路径不能为空')
    reason = invalidDataRoot(new_path)
    if reason:
        return yf.returnJson(False, '不安全的目录路径: ' + reason)

    try:
        cmd_root = "docker info --format '{{.DockerRootDir}}'"
        out, err = yf.execShell(cmd_root)
        docker_root = out.strip() if out else "/var/lib/docker"

        if docker_root == new_path:
            return yf.returnJson(False, '新路径不能与当前路径相同')

        if not os.path.exists(new_path):
            try:
                os.makedirs(new_path)
            except Exception as e:
                return yf.returnJson(False, '无法创建新路径，请检查权限或路径格式: ' + str(e))

        cmd_du = 'du -sk %s' % shlex.quote(docker_root)
        out_du, err_du = yf.execShell(cmd_du)
        required_kb = 0
        if out_du:
            try:
                required_kb = int(out_du.strip().split()[0])
            except Exception as _e:
                _log.debug('[docker] checkDockerMigrateSpace 异常已忽略: %s', _e)

        cmd_df = 'df -P -k %s' % shlex.quote(new_path)
        out_df, err_df = yf.execShell(cmd_df)
        if out_df and required_kb > 0:
            try:
                lines = out_df.strip().split('\n')
                if len(lines) >= 2:
                    parts = lines[-1].split()
                    available_kb = int(parts[3])
                    req_size = yf.toSize(required_kb * 1024)
                    avail_size = yf.toSize(available_kb * 1024)
                    
                    if required_kb > available_kb * 0.95:
                        return yf.returnJson(False, '目标分区空间不足！预估需要: %s，目标可用: %s' % (req_size, avail_size))
                    
                    return yf.returnJson(True, 'ok', {'required': req_size, 'available': avail_size})
            except Exception as _e:
                _log.debug('[docker] checkDockerMigrateSpace 异常已忽略: %s', _e)
        
        return yf.returnJson(True, 'ok', {'required': '未知', 'available': '未知'})
    except Exception as e:
        return yf.returnJson(False, str(e))


def migrateDockerDir():
    args = getArgs()
    data = checkArgs(args, ['new_path'])
    if not data[0]:
        return data[1]

    new_path = str(args['new_path']).strip()
    if not new_path:
        return yf.returnJson(False, '新路径不能为空')
    # 该路径会被 os.makedirs + rsync 写入并写进 daemon.json 的 data-root
    # （随后重启 docker）：写错位置（/etc、面板目录…）会让 docker 起不来。
    reason = invalidDataRoot(new_path)
    if reason:
        return yf.returnJson(False, '不安全的目录路径: ' + reason)

    try:
        # 获取当前根目录
        cmd_root = "docker info --format '{{.DockerRootDir}}'"
        out, err = yf.execShell(cmd_root)
        docker_root = out.strip() if out else "/var/lib/docker"

        if docker_root == new_path:
            return yf.returnJson(False, '新路径不能与当前路径相同')

        if not os.path.exists(new_path):
            os.makedirs(new_path)

        # 检查剩余空间
        cmd_du = 'du -sk %s' % shlex.quote(docker_root)
        out_du, err_du = yf.execShell(cmd_du)
        required_kb = 0
        if out_du:
            try:
                required_kb = int(out_du.strip().split()[0])
            except Exception as _e:
                _log.debug('[docker] migrateDockerDir 异常已忽略: %s', _e)

        cmd_df = 'df -P -k %s' % shlex.quote(new_path)
        out_df, err_df = yf.execShell(cmd_df)
        if out_df and required_kb > 0:
            try:
                lines = out_df.strip().split('\n')
                if len(lines) >= 2:
                    parts = lines[-1].split()
                    available_kb = int(parts[3])
                    # 预留 5% 缓冲空间，防止把目标分区写满
                    if required_kb > available_kb * 0.95:
                        req_size = yf.toSize(required_kb * 1024)
                        avail_size = yf.toSize(available_kb * 1024)
                        return yf.returnJson(False, '目标分区空间不足！预估需要: %s，目标可用: %s' % (req_size, avail_size))
            except Exception as _e:
                _log.debug('[docker] migrateDockerDir 异常已忽略: %s', _e)

        # 停止docker
        yf.execShell('systemctl stop docker')
        yf.execShell('systemctl stop docker.socket')

        # 检查并安装 rsync
        check_rsync = yf.execShell('which rsync')
        if not check_rsync[0].strip():
            yf.execShell('yum install -y rsync || apt-get install -y rsync')

        # 同步数据
        sync_cmd = 'rsync -a %s/ %s/' % (shlex.quote(docker_root), shlex.quote(new_path))
        out, err = yf.execShell(sync_cmd)
        if err and err.strip():
            # 有时可能只是无害的警告，或者rsync未找到
            if "未找到命令" in err or "command not found" in err:
                raise Exception("数据同步失败: 系统缺少 rsync，并且自动安装失败，请手动执行 yum install rsync 或 apt-get install rsync")
            raise Exception("数据同步失败: " + err.strip())

        # 修改daemon.json
        daemon_file = get_daemon_json_path()
        daemon_dir = os.path.dirname(daemon_file)
        if not os.path.exists(daemon_dir):
            os.makedirs(daemon_dir)

        data = {}
        if os.path.exists(daemon_file):
            try:
                content = yf.readFile(daemon_file)
                if content:
                    data = json.loads(content)
            except Exception as _e:
                _log.debug('[docker] migrateDockerDir 异常已忽略: %s', _e)

        data['data-root'] = new_path
        yf.writeFile(daemon_file, json.dumps(data, indent=4))

        # 启动docker
        if not yf.isAppleSystem() and os.name != 'nt':
            yf.execShell('systemctl daemon-reload')
            yf.execShell('systemctl start docker.socket')
            yf.execShell('systemctl start docker')
        
        return yf.returnJson(True, '迁移成功！')
    except Exception as e:
        # 尝试恢复
        if not yf.isAppleSystem() and os.name != 'nt':
            yf.execShell('systemctl start docker.socket')
            yf.execShell('systemctl start docker')
        return yf.returnJson(False, '迁移失败: ' + str(e))


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
        print(getConf())
    elif func == 'con_list':
        print(conListData())
    elif func == 'docker_con_log':
        print(dockerLogCon())
    elif func == 'docker_remove_con':
        print(dockerRemoveCon())
    elif func == 'docker_run_con':
        print(dockerRunCon())
    elif func == 'docker_stop_con':
        print(dockerStopCon())
    elif func == 'docker_exec':
        print(dockerExec())
    elif func == 'docker_pull_with_mirror':
        print(docker_pull_with_mirror())
    elif func == 'docker_pull':
        print(dockerPull())
    elif func == 'docker_pull_reg':
        print(dockerPullReg())
    elif func == 'image_list':
        print(imageListData())
    elif func == 'image_pick_dir':
        print(dockerImagePickDir())
    elif func == 'image_pick_save':
        print(dockerImagePickSave())
    elif func == 'image_pick_load':
        print(dockerImagePickLoad())
    elif func == 'image_pick_list':
        print(dockerImagePickList())
    elif func == 'docker_get_iplist':
        print(getDockerIpList())
    elif func == 'docker_del_ip':
        print(dockerDelIP())
    elif func == 'docker_add_ip':
        print(dockerAddIP())
    elif func == 'get_docker_create_info':
        print(getDockerCreateInfo())
    elif func == 'docker_create_con':
        print(dockerCreateCon())
    elif func == 'docker_remove_image':
        print(dockerRemoveImage())
    elif func == 'docker_port_check':
        print(dockerPortCheck())
    elif func == 'docker_login':
        print(dockerLogin())
    elif func == 'docker_logout':
        print(dockerLogout())
    elif func == 'get_accelerator':
        print(get_accelerator())
    elif func == 'set_accelerator':
        print(set_accelerator())
    elif func == 'repo_list':
        print(repoList())
    elif func == 'get_docker_dir_info':
        print(getDockerDirInfo())
    elif func == 'migrate_docker_dir':
        print(migrateDockerDir())
    elif func == 'check_docker_migrate_space':
        print(checkDockerMigrateSpace())
    else:
        print('error')
