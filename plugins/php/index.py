# coding:utf-8

import sys
import io
import os
import time
import re
import json
import shutil

# reload(sys)
# sys.setdefaultencoding('utf8')

# 动态获取项目根目录，避免因执行脚本时当前工作目录(Cwd)不同而导致 core 依赖导入失败
panel_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
web_dir = os.path.join(panel_root, "web")
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import logging

_log = logging.getLogger('yf.php')

app_debug = False
if yf.isAppleSystem():
    app_debug = True

CURRENT_PLUGIN_VERSION = '2.0'
_PHP_UPGRADE_CHECKING = False

#: 版本号白名单：纯数字（安装目录名即版本号，如 52/74/80/83/84）。
#  该值会被拼进文件路径与 shell 命令，必须先行校验（穿越 / 注入的唯一入口）。
PHP_VERSION_RE = re.compile(r'^[0-9]{1,3}$')
#: FPM 池名白名单：会被拼进 `etc/php-fpm.d/<pool>.conf` 路径。
PHP_POOL_RE = re.compile(r'^[a-zA-Z0-9_\-]{1,32}$')
#: FPM 进程管理方式白名单（写入 pool 配置的 `pm = ` 行）。
PHP_PM_MODES = ('static', 'dynamic', 'ondemand')
#: Session 存储方式白名单（写入 php.ini 的 `session.save_handler` 行）。
PHP_SESSION_HANDLERS = ('files', 'redis', 'memcache', 'memcached')
#: php.ini 单值白名单：不允许换行/回车/引号/分号（否则可注入任意指令）。
PHP_INI_VALUE_RE = re.compile(r'^[0-9A-Za-z_\-\.,&~|!^/+ *:%\[\]]{0,120}$')
#: 禁用函数名白名单（逗号分隔）。
PHP_FUNC_LIST_RE = re.compile(r'^[A-Za-z0-9_ ,]{0,4000}$')
#: php.ini 可写键的值白名单：只接受预期的取值形态（阻止换行注入任意指令）。
PHP_INI_KEY_RULES = {
    'short_open_tag': r'^(On|Off|1|0)$',
    'asp_tags': r'^(On|Off|1|0)$',
    'file_uploads': r'^(On|Off|1|0)$',
    'display_errors': r'^(On|Off|1|0)$',
    'cgi.fix_pathinfo': r'^[01]$',
    'max_execution_time': r'^[0-9]{1,6}$',
    'max_input_time': r'^[0-9]{1,6}$',
    'max_input_vars': r'^[0-9]{1,9}$',
    'max_file_uploads': r'^[0-9]{1,6}$',
    'default_socket_timeout': r'^[0-9]{1,6}$',
    'memory_limit': r'^[0-9]{1,9}[KMG]?$',
    'post_max_size': r'^[0-9]{1,9}[KMG]?$',
    'upload_max_filesize': r'^[0-9]{1,9}[KMG]?$',
    'error_reporting': r'^[0-9A-Za-z_ &~|^!()-]{1,60}$',
    'date.timezone': r'^[A-Za-z0-9_/+\-]{1,40}$',
}


def validateIniValue(key, value):
    """校验 php.ini 单键取值：返回 (错误消息, 规范化值)，合法时错误消息为 ''。"""
    if not isinstance(value, str):
        value = str(value)
    v = value.strip()
    rule = PHP_INI_KEY_RULES.get(key)
    if rule is None:
        if not PHP_INI_VALUE_RE.match(v):
            return ('参数值不合法!', None)
        return ('', v)
    if not re.match(rule, v):
        return ('参数值不合法!', None)
    return ('', v)


def setIniKey(content, key, value):
    """把 `key = value` 写回 ini 文本（含被注释的同名行），保留其余内容。

    用 lambda 做替换体：旧实现直接拿用户值当 `re.sub` 的替换字符串，
    值里出现 `\\1`/`\\g<...>` 会报 re.error 或被当作分组引用。
    """
    pattern = r'(?m)^\s*;?\s*' + re.escape(key) + r'\s*=.*'
    line = '%s = %s' % (key, value)
    if re.search(pattern, content):
        return re.sub(pattern, lambda m: line, content)
    return content.rstrip('\n') + '\n' + line + '\n'


def getPluginName():
    return 'php'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getPluginVersionFile():
    return getPluginDir() + '/plugin_version.pl'


def isPhpVersion(version):
    """版本号是否为「纯数字」形态（防路径穿越与 shell 注入）。"""
    return bool(PHP_VERSION_RE.match(str(version if version is not None else '').strip()))


def isPhpPool(pool):
    """FPM 池名是否合法（拼进配置文件路径，禁止 `../`）。"""
    return bool(PHP_POOL_RE.match(str(pool if pool is not None else '').strip()))


def isIpv4(value):
    """严格 IPv4 校验（旧实现用非锚定 re.search，`1.2.3.4evil` 也能通过）。"""
    parts = str(value if value is not None else '').strip().split('.')
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit() or len(p) > 3 or int(p) > 255:
            return False
    return True


def versionOrError(version):
    """JSON 信封型入口的版本校验：非法返回 (错误信封, None)，合法返回 (None, 版本)。"""
    v = str(version if version is not None else '').strip()
    if not isPhpVersion(v):
        return (yf.returnJson(False, 'PHP版本参数不合法!'), None)
    return (None, v)


def versionOrFail(version):
    """原始字符串型入口（status/start/conf/fpm_log 等）的版本校验。"""
    v = str(version if version is not None else '').strip()
    if not isPhpVersion(v):
        return 'ERROR: PHP版本参数不合法'
    return None


def getVersionDir(version):
    return getServerDir() + '/' + version


def isInstalled(version):
    """版本目录存在且含 php-fpm 可执行文件、etc 目录或 php.ini 才算「已安装」。

    未安装时禁止一切「自愈/启动」动作：否则会凭空造出 init.d 脚本、systemd unit
    与 var/run、etc/php.ini 等产物（C01~C05 同族缺陷）。
    """
    ver_dir = getVersionDir(version)
    if not os.path.isdir(ver_dir):
        return False
    return (os.path.exists(ver_dir + '/sbin/php-fpm')
            or os.path.isdir(ver_dir + '/etc')
            or os.path.exists(ver_dir + '/etc/php.ini'))


def _procInfo(pid):
    """读取 (comm, args)。仅 Linux 有 /proc；取不到返回 None。"""
    try:
        with open('/proc/%s/comm' % pid, 'r', encoding='utf-8', errors='replace') as fp:
            comm = fp.read().strip()
        with open('/proc/%s/cmdline' % pid, 'rb') as fp:
            args = fp.read().replace(b'\x00', b' ').decode('utf-8', 'replace').strip()
        return (comm, args)
    except Exception:
        return None


def _iterProcesses():
    """枚举 (pid, comm, args)：优先 /proc（Linux），否则退回 ps（macOS/FreeBSD）。"""
    if os.path.isdir('/proc'):
        for entry in os.listdir('/proc'):
            if not entry.isdigit():
                continue
            info = _procInfo(entry)
            if info:
                yield (entry, info[0], info[1])
        return
    data = yf.execShell("ps -eo pid=,comm=,args=")
    for line in (data[0] or '').splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        yield (parts[0], os.path.basename(parts[1]), parts[2])


def _findFpmMaster(version):
    """精确定位某版本的 php-fpm master 进程 PID（找不到返回 ''）。

    判据用进程的 **comm 必须等于 php-fpm**，而不是 `ps | grep` 命令行匹配：
    面板自身/任何无关 python 进程只要命令行里带了 `php-fpm: master process` 与
    `/php/<版本>/` 字样就会被旧写法命中，导致「未运行也报 start」的历史假阳性
    （varnish/sphinx/webstats 同族现场）。
    """
    marker = '/php/%s/' % version
    for pid, comm, args in _iterProcesses():
        if comm != 'php-fpm':
            continue
        if marker in args and 'master process' in args:
            return pid
    return ''


def _pidIsFpmMaster(pid, version):
    """pid 是否确为某版本的 php-fpm master（陈旧 pid 文件指向别的进程时不得算 start）。

    无 /proc 的平台（macOS/FreeBSD）退化为「进程存活即算」，与旧行为一致。
    """
    info = _procInfo(pid)
    if info is None:
        return yf.checkPid(pid)
    comm, args = info
    return comm == 'php-fpm' and ('/php/%s/' % version) in args


def _compare_version(v1, v2):
    p1 = [int(x) for x in re.sub(r'[^\d.]', '', str(v1)).split('.') if x.isdigit()]
    p2 = [int(x) for x in re.sub(r'[^\d.]', '', str(v2)).split('.') if x.isdigit()]
    max_len = max(len(p1), len(p2))
    p1 += [0] * (max_len - len(p1))
    p2 += [0] * (max_len - len(p2))
    if p1 < p2:
        return -1
    elif p1 > p2:
        return 1
    return 0


def getInstalledPhpVersions():
    """获取本机已安装的所有源码版 PHP 版本列表（如 ['56', '74', '80']）"""
    php_dir = getServerDir()
    if not os.path.exists(php_dir):
        return []
    versions = []
    for item in os.listdir(php_dir):
        full_path = os.path.join(php_dir, item)
        if os.path.isdir(full_path) and re.match(r'^\d+$', item):
            if (os.path.exists(os.path.join(full_path, 'sbin', 'php-fpm')) or 
                os.path.exists(os.path.join(full_path, 'etc', 'php.ini')) or
                os.path.exists(os.path.join(full_path, 'bin', 'php'))):
                versions.append(item)
    return sorted(versions)


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getInitDFile(version):
    current_os = yf.getOs()
    if current_os == 'darwin':
        return '/tmp/' + getPluginName()

    if current_os.startswith('freebsd'):
        return '/etc/rc.d/' + getPluginName()
    return '/etc/init.d/' + getPluginName() + version


def getArgs():
    """解析插件参数。

    面板 `utils/plugin.py::run()` 把 args 当**一个** argv 传进来，前端 `YfPlugin.parseArgs`
    统一发 JSON 字符串，因此 JSON 优先；同时兼容 `k:v` 旧写法。任何畸形入参一律回 {}
    而不是抛 IndexError/JSONDecodeError（旧实现 `t[1]` 会崩）。
    """
    args = sys.argv[3:]
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        try:
            parsed = json.loads(args[0])
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
        if parsed is not None:
            # 合法 JSON 但不是对象（数组/字符串/数字）：没有键值语义
            return {}
        t = str(args[0]).strip().strip('{').strip('}')
        if t.strip() == '':
            return {}
        if ':' in t:
            k, v = t.split(':', 1)
            tmp[k.strip('"').strip("'")] = v.strip('"').strip("'")
        return tmp
    elif args_len > 1:
        for i in range(len(args)):
            if ':' not in str(args[i]):
                continue
            t = str(args[i]).split(':', 1)
            tmp[t[0].strip('"').strip("'")] = t[1].strip('"').strip("'")
    return tmp


def checkArgs(data, ck=[]):
    if not isinstance(data, dict):
        return (False, yf.returnJson(False, '参数格式错误!'))
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


def getConf(version):
    path = getVersionDir(version) + '/etc/php.ini'
    try:
        if not os.path.exists(path) or os.path.getsize(path) < 50:
            makePhpIni(version)
    except Exception:
        try:
            makePhpIni(version)
        except Exception as _e:
            _log.debug('[php] getConf 异常已忽略: %s', _e)
    return path


def getFpmConfFile(version, pool='www'):
    args = getArgs()
    if 'pool' in args:
        pool = args['pool']
    if not isPhpPool(pool):
        return ''
    path = getVersionDir(version) + '/etc/php-fpm.d/' + pool + '.conf'
    if not os.path.exists(path):
        try:
            phpFpmPoolReplace(version, pool)
        except Exception as _e:
            _log.debug('[php] getFpmConfFile 异常已忽略: %s', _e)
    return path

def getFpmFile(version):
    path = getVersionDir(version) + '/etc/php-fpm.conf'
    if not os.path.exists(path):
        try:
            phpFpmReplace(version)
        except Exception as _e:
            _log.debug('[php] getFpmFile 异常已忽略: %s', _e)
    return path



def status_progress(version):
    # ps -ef|grep 'php/81' |grep -v grep | grep -v python | awk '{print $2}
    cmd = "ps aux|grep 'php/" + version + \
        "' |grep -v grep | grep -v python | awk '{print $2}'"
    data = yf.execShell(cmd)
    if data[0] == '':
        return 'stop'
    return 'start'


def getPhpSocket(version):
    path = getFpmConfFile(version)
    if not path or not os.path.exists(path):
        return ""
    content = yf.readFile(path)
    if not content:
        return ""
    rep = r'(?m)^\s*;?\s*listen\s*=\s*(.*)'
    tmp = re.search(rep, content)
    if not tmp:
        return ""
    return tmp.groups()[0].strip()


def status(version):
    '''
    双模态精准探活与自愈探针：
    1. 自动触发单次版本跃迁升级自愈（已是最新版本 0 开销放行）；
    2. 进程特征探针：按 /proc 的 comm 精确查找对应版本的 php-fpm master 进程；
    3. 通信与 Socket/PID 自愈校准：真实存活时自动自愈补齐 PID 文件，孤儿死锁时精准剔除。

    假阳性防御：旧写法用 `ps aux | grep 'php-fpm: master process' | grep '/php/<版本>/'`，
    任何命令行带这些字样的 python/无关进程都会被命中（未运行也报 start）；
    降级分支又用 pid 文件 `os.kill(pid, 0)`，陈旧 pid 文件指向其它存活进程时同样误报。
    现改为「comm == php-fpm 且命令行含本版本目录」，pid 文件分支也做同样校验。
    '''
    err = versionOrFail(version)
    if err:
        return err
    try:
        checkPluginUpgrade(version)
    except Exception as _e:
        _log.debug('[php] status 异常已忽略: %s', _e)

    ver_dir = getVersionDir(version)
    pid_file = ver_dir + '/var/run/php-fpm.pid'

    # 1. 精确匹配的 php-fpm master 进程
    live_pid = _findFpmMaster(version)

    # 2. 真实主进程存活
    if live_pid:
        # 走 yf.syncPidFile：面板以 root 运行，绝不能把守护进程的 pid 文件属主改成
        # root（否则守护进程下次启动无法创建自己的 pid 文件，mysql 已真机复现该 P0）
        yf.syncPidFile(pid_file, live_pid)
        return 'start'

    # 3. PID 文件信号探活降级（必须确认 pid 真属于本版本的 php-fpm）
    if os.path.exists(pid_file):
        pid_str = yf.readFile(pid_file)
        pid_str = pid_str.strip() if isinstance(pid_str, str) else ''
        if pid_str.isdigit():
            pid = int(pid_str)
            if _pidIsFpmMaster(pid, version):
                return 'start'
            if not yf.checkPid(pid):
                # 进程已死，安全清理僵尸 PID 文件
                try:
                    os.remove(pid_file)
                except Exception as _e:
                    _log.debug('[php] status 异常已忽略: %s', _e)

    return 'stop'


def contentReplace(content, version):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$PHP_VERSION}', version)
    content = content.replace('{$LOCAL_IP}', yf.getLocalIp())
    content = content.replace('{$SSL_CRT}', yf.getSslCrt())

    if yf.isAppleSystem():
        # user = yf.execShell(
        #     "who | sed -n '2, 1p' |awk '{print $1}'")[0].strip()
        content = content.replace('{$PHP_USER}', 'nobody')
        content = content.replace('{$PHP_GROUP}', 'nobody')

        rep = r'listen.owner\s*=\s*(.+)\r?\n'
        val = ';listen.owner = nobody\n'
        content = re.sub(rep, val, content)

        rep = r'listen.group\s*=\s*(.+)\r?\n'
        val = ';listen.group = nobody\n'
        content = re.sub(rep, val, content)

        rep = r'user\s*=\s*(.+)\r?\n'
        val = ';user = nobody\n'
        content = re.sub(rep, val, content)

        rep = r'[^\.]group\s*=\s*(.+)\r?\n'
        val = ';group = nobody\n'
        content = re.sub(rep, val, content)

    else:
        content = content.replace('{$PHP_USER}', 'www')
        content = content.replace('{$PHP_GROUP}', 'www')
    return content


def makeOpenrestyConf():
    phpversions = ['00', '52', '53', '54', '55', '56',
                   '70', '71', '72', '73', '74', '80', '81', '82', '83','84']

    sdir = yf.getServerDir()

    dst_dir = sdir + '/web_conf/php'
    if not os.path.exists(dst_dir):
        yf.makeDirs(dst_dir)

    dst_dir_conf = sdir + '/web_conf/php/conf'
    if not os.path.exists(dst_dir_conf):
        yf.makeDirs(dst_dir_conf)

    dst_dir_upstream = sdir + '/web_conf/php/upstream'
    if not os.path.exists(dst_dir_upstream):
        yf.makeDirs(dst_dir_upstream)

    dst_pathinfo = sdir + '/web_conf/php/pathinfo.conf'
    if not os.path.exists(dst_pathinfo):
        src_pathinfo = getPluginDir() + '/conf/pathinfo.conf'
        shutil.copyfile(src_pathinfo, dst_pathinfo)

    info = getPluginDir() + '/info.json'
    content = yf.readFile(info)
    if not content:
        yf.writeLog('插件管理[PHP]', '读取 info.json 失败: ' + info)
        return False
    try:
        content = json.loads(content)
    except Exception:
        yf.writeLog('插件管理[PHP]', 'info.json 格式错误: ' + info)
        return False
    versions = content.get('versions') if isinstance(content, dict) else None
    if not versions:
        versions = phpversions
    tpl = getPluginDir() + '/conf/enable-php.conf'
    tpl_content = yf.readFile(tpl)
    if not tpl_content:
        tpl_content = ''
    for x in phpversions:
        dfile = sdir + '/web_conf/php/conf/enable-php-' + x + '.conf'
        if not os.path.exists(dfile):
            if x == '00':
                yf.writeFile(dfile, '')
            else:
                content = contentReplace(tpl_content, x)
                yf.writeFile(dfile, content)

    upstream_tpl = getPluginDir() + '/conf/enable-php-upstream.conf'
    upstream_tpl_content = yf.readFile(upstream_tpl)
    if not upstream_tpl_content:
        upstream_tpl_content = ''
    for x in phpversions:
        dfile = sdir + '/web_conf/php/upstream/enable-php-' + x + '.conf'
        if not os.path.exists(dfile):
            if x == '00':
                yf.writeFile(dfile, '')
            else:
                content = contentReplace(upstream_tpl_content, x)
                yf.writeFile(dfile, content)

    vhost_dir = yf.getServerDir() + '/web_conf/nginx/vhost'
    write_php_upstream_conf = yf.getServerDir()+'/web_conf/php/upstream/*.conf;'
    if not os.path.exists(vhost_dir):
        yf.makeDirs(vhost_dir)

    vhost_php_upstream = vhost_dir+'/0.php_upstream.conf'
    if not os.path.exists(vhost_php_upstream):
        yf.writeFile(vhost_php_upstream,'include '+write_php_upstream_conf)
    return True


def phpPrependFile(version):
    app_start = getServerDir() + '/app_start.php'
    if not os.path.exists(app_start):
        tpl = getPluginDir() + '/conf/app_start.php'
        content = yf.readFile(tpl)
        if not content:
            return False
        content = contentReplace(content, version)
        yf.writeFile(app_start, content)
    return True


def phpFpmReplace(version):
    desc_php_fpm = getVersionDir(version) + '/etc/php-fpm.conf'
    service_dir = getServerDir().replace('\\', '/')
    expected_include = f"{service_dir}/{version}/etc/php-fpm.d/*.conf"

    if version == '52':
        tpl_php_fpm = getPluginDir() + '/conf/php-fpm-52.conf'
        content = yf.readFile(tpl_php_fpm)
        if not content:
            return False
        yf.writeFile(desc_php_fpm, content)
        return True

    if not os.path.exists(desc_php_fpm):
        tpl_php_fpm = getPluginDir() + '/conf/php-fpm.conf'
        content = yf.readFile(tpl_php_fpm)
        if not content:
            return False
        content = contentReplace(content, version)
        yf.writeFile(desc_php_fpm, content)
    else:
        content = yf.readFile(desc_php_fpm)
        if not content or len(content.strip()) < 10:
            tpl_php_fpm = getPluginDir() + '/conf/php-fpm.conf'
            content = yf.readFile(tpl_php_fpm)
            if not content:
                return False
            content = contentReplace(content, version)
            yf.writeFile(desc_php_fpm, content)
            return True

        modified = False
        # 1. 确保包含 [global] 节区
        if '[global]' not in content:
            content = "[global]\n" + content
            modified = True

        # 2. 确保包含 pid 与 error_log
        if not re.search(r'(?m)^\s*pid\s*=', content):
            content += "\npid = run/php-fpm.pid\n"
            modified = True
        if not re.search(r'(?m)^\s*error_log\s*=', content):
            content += "\nerror_log = log/php-fpm.log\n"
            modified = True

        # 3. 清除历史残留的非法全局 php_value
        if 'php_value' in content:
            content = re.sub(r'(?m)^\s*;?\s*php_value\[auto_prepend_file\].*\r?\n?', '', content)
            modified = True

        # 4. 确保存在有效且未注释的绝对路径 include 指令
        inc_match = re.search(r'(?m)^\s*include\s*=\s*(.+)$', content)
        if inc_match:
            inc_val = inc_match.group(1).strip()
            # 若是相对路径（例如 etc/php-fpm.d/*.conf）或非预期绝对路径，矫正为绝对路径
            if not inc_val.startswith('/') or inc_val != expected_include:
                content = re.sub(r'(?m)^\s*include\s*=.*', lambda m: f'include = {expected_include}', content)
                modified = True
        else:
            # 检查是否有被分号注释的 include
            if re.search(r'(?m)^\s*;\s*include\s*=.*', content):
                content = re.sub(r'(?m)^\s*;\s*include\s*=.*', lambda m: f'include = {expected_include}', content)
                modified = True
            else:
                # 没有任何 include，且未在主配置内直接定义 [pool]，则追加 include
                if not re.search(r'(?m)^\s*\[(?!global\])[^\]]+\]', content):
                    content = content.rstrip() + f"\ninclude = {expected_include}\n"
                    modified = True

        if modified:
            yf.writeFile(desc_php_fpm, content)
    return True


def phpFpmPoolReplace(version, pool = 'www'):
    if not isPhpPool(pool):
        return False
    service_php_fpm_dir = getVersionDir(version) + '/etc/php-fpm.d/'

    if not os.path.exists(service_php_fpm_dir):
        yf.makeDirs(service_php_fpm_dir)

    service_php_fpmwww = service_php_fpm_dir + '/' + pool + '.conf'
    need_regenerate = False
    if not os.path.exists(service_php_fpmwww):
        need_regenerate = True
    else:
        raw = yf.readFile(service_php_fpmwww)
        if not raw or f'[{pool}]' not in raw:
            need_regenerate = True

    if need_regenerate:
        tpl_php_fpmwww = getPluginDir() + '/conf/' + pool + '.conf'
        if not os.path.exists(tpl_php_fpmwww):
            tpl_php_fpmwww = getPluginDir() + '/conf/www.conf'
        content = yf.readFile(tpl_php_fpmwww)
        if not content:
            # 极限兜底：如果模板被破坏，生成最小可用安全池配置
            content = f"[{pool}]\nuser = www\ngroup = www\nlisten = /tmp/php-cgi-{version}.sock\nlisten.owner = www\nlisten.group = www\npm = dynamic\npm.max_children = 30\npm.start_servers = 5\npm.min_spare_servers = 5\npm.max_spare_servers = 20\n"
        content = contentReplace(content, version)
        
        # 动态根据内存计算 FPM 进程数
        try:
            mem_total_str = yf.execShell("free -m | grep Mem | awk '{print $2}'")[0].strip()
            if mem_total_str:
                mem_total = int(mem_total_str)
                if mem_total <= 1024:
                    max_children = 30; start_servers = 5; min_spare_servers = 5; max_spare_servers = 10; pm = 'ondemand'
                elif mem_total <= 2048:
                    max_children = 50; start_servers = 5; min_spare_servers = 5; max_spare_servers = 20; pm = 'dynamic'
                elif mem_total <= 4096:
                    max_children = 100; start_servers = 10; min_spare_servers = 10; max_spare_servers = 30; pm = 'dynamic'
                elif mem_total <= 8192:
                    max_children = 150; start_servers = 15; min_spare_servers = 15; max_spare_servers = 30; pm = 'dynamic'
                else:
                    max_children = 300; start_servers = 20; min_spare_servers = 20; max_spare_servers = 50; pm = 'dynamic'
                    
                content = re.sub(r'(?m)^pm\.max_children\s*=\s*\d+', f'pm.max_children = {max_children}', content)
                content = re.sub(r'(?m)^pm\.start_servers\s*=\s*\d+', f'pm.start_servers = {start_servers}', content)
                content = re.sub(r'(?m)^pm\.min_spare_servers\s*=\s*\d+', f'pm.min_spare_servers = {min_spare_servers}', content)
                content = re.sub(r'(?m)^pm\.max_spare_servers\s*=\s*\d+', f'pm.max_spare_servers = {max_spare_servers}', content)
                content = re.sub(r'(?m)^pm\s*=\s*dynamic', f'pm = {pm}', content)
        except Exception as e:
            yf.writeLog('php', '动态配置 FPM 进程数失败: ' + str(e))

        yf.writeFile(service_php_fpmwww, content)
    return True


DEFAULT_DISABLE_FUNCTIONS = (
    'passthru,exec,system,chroot,chgrp,chown,shell_exec,popen,proc_open,pcntl_exec,'
    'ini_alter,ini_restore,dl,openlog,syslog,readlink,symlink,popepassthru,pcntl_alarm,'
    'pcntl_fork,pcntl_waitpid,pcntl_wait,pcntl_wifexited,pcntl_wifstopped,pcntl_wifsignaled,'
    'pcntl_wifcontinued,pcntl_wexitstatus,pcntl_wtermsig,pcntl_wstopsig,pcntl_signal,'
    'pcntl_signal_dispatch,pcntl_get_last_error,pcntl_strerror,pcntl_sigprocmask,'
    'pcntl_sigwaitinfo,pcntl_sigtimedwait,pcntl_exec,pcntl_getpriority,pcntl_setpriority,'
    'imap_open,apache_setenv'
)


def makePhpIni(version):
    # 未安装的版本不得凭空造出 etc/php.ini（会在 /www/server/php 下留下假版本目录）
    if not isInstalled(version):
        return False
    dst_ini = getVersionDir(version) + '/etc/php.ini'
    need_build = False
    if not os.path.exists(dst_ini):
        need_build = True
    else:
        try:
            if os.path.getsize(dst_ini) < 50:
                need_build = True
        except Exception:
            need_build = True

    if need_build:
        src_ini = getPluginDir() + '/conf/php' + version[0:1] + '.ini'
        if not os.path.exists(src_ini):
            major = int(version) if version.isdigit() else 80
            src_ini = getPluginDir() + '/conf/php8.ini' if major >= 80 else getPluginDir() + '/conf/php7.ini'
            if not os.path.exists(src_ini):
                src_ini = getPluginDir() + '/conf/php5.ini'

        content = yf.readFile(src_ini)
        if not content:
            content = "[PHP]\nengine = On\nshort_open_tag = On\n"

        if version == '52':
            content = content + "\nauto_prepend_file=/www/server/php/app_start.php\n"

        content = contentReplace(content, version)

        # 优化 php.ini 默认值
        configs_to_set = {
            'post_max_size': '50M',
            'upload_max_filesize': '50M',
            'date.timezone': 'PRC',
            'short_open_tag': 'On',
            'cgi.fix_pathinfo': '1',
            'max_execution_time': '300',
            'display_errors': 'Off',
            'log_errors': 'On',
            'expose_php': 'Off',
            'session.cookie_httponly': 'On',
            'disable_functions': DEFAULT_DISABLE_FUNCTIONS,
            'opcache.enable': '1',
            'opcache.enable_cli': '1',
            'opcache.memory_consumption': '128',
            'opcache.interned_strings_buffer': '8',
            'opcache.max_accelerated_files': '10000',
            'opcache.revalidate_freq': '60',
            'opcache.save_comments': '1'
        }

        for k, v in configs_to_set.items():
            pattern = r'(?m)^;?\s*' + re.escape(k) + r'\s*=.*'
            if re.search(pattern, content):
                content = re.sub(pattern, f'{k} = {v}', content)
            else:
                content += f'\n{k} = {v}\n'

        os.makedirs(os.path.dirname(dst_ini), exist_ok=True)
        yf.writeFile(dst_ini, content)
    else:
        # 文件已存在且大小正常，检查并自愈补齐缺失的 disable_functions
        content = yf.readFile(dst_ini)
        if content and not re.search(r'(?m)^\s*disable_functions\s*=\s*\S+', content):
            if re.search(r'(?m)^;?\s*disable_functions\s*=.*', content):
                content = re.sub(r'(?m)^;?\s*disable_functions\s*=.*', f'disable_functions = {DEFAULT_DISABLE_FUNCTIONS}', content)
            else:
                content += f'\ndisable_functions = {DEFAULT_DISABLE_FUNCTIONS}\n'
            yf.writeFile(dst_ini, content)


def initReplace(version, force_refresh_service=False):
    if not isInstalled(version):
        return ''
    makeOpenrestyConf()
    makePhpIni(version)

    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        yf.makeDirs(initD_path)

    file_bin = initD_path + '/php' + version
    file_tpl = getPluginDir() + '/init.d/php.tpl'
    if version == '52':
        file_tpl = getPluginDir() + '/init.d/php52.tpl'

    if not os.path.exists(file_bin) or force_refresh_service:
        content = yf.readFile(file_tpl)
        if not content:
            yf.writeLog('插件管理[PHP]', '读取服务脚本模板失败: ' + file_tpl)
            return ''
        content = contentReplace(content, version)
        yf.writeFile(file_bin, content)
        yf.execShell('chmod +x ' + yf.shlexQuote(file_bin))

    phpPrependFile(version)
    phpFpmPoolReplace(version, 'www')
    phpFpmPoolReplace(version, 'backup')
    phpFpmReplace(version)

    session_path = getServerDir() + '/tmp/session'
    if not os.path.exists(session_path):
        yf.makeDirs(session_path)
    if not yf.isAppleSystem() and not yf.getOs().startswith('freebsd'):
        yf.execShell('chown -R www:www ' + yf.shlexQuote(session_path))

    upload_path = getServerDir() + '/tmp/upload'
    if not os.path.exists(upload_path):
        yf.makeDirs(upload_path)
    if not yf.isAppleSystem() and not yf.getOs().startswith('freebsd'):
        yf.execShell('chown -R www:www ' + yf.shlexQuote(upload_path))

    # 运行临时与日志目录健全
    var_run = getVersionDir(version) + '/var/run'
    var_log = getVersionDir(version) + '/var/log'
    if not os.path.exists(var_run):
        yf.makeDirs(var_run)
    if not os.path.exists(var_log):
        yf.makeDirs(var_log)
    if not yf.isAppleSystem() and not yf.getOs().startswith('freebsd'):
        yf.execShell(f'chown -R www:www {yf.shlexQuote(var_run)} {yf.shlexQuote(var_log)}')

    # systemd 守护进程单元自愈与刷新
    systemDir = yf.systemdCfgDir()
    systemService = systemDir + '/php' + version + '.service'

    if os.path.exists(systemDir):
        if not os.path.exists(systemService) or force_refresh_service:
            systemServiceTpl = getPluginDir() + '/init.d/php.service.tpl'
            if version == '52':
                systemServiceTpl = getPluginDir() + '/init.d/php.service.52.tpl'
            service_path = yf.getServerDir()
            se_content = yf.readFile(systemServiceTpl)
            if not se_content:
                yf.writeLog('插件管理[PHP]', '读取 systemd 单元模板失败: ' + systemServiceTpl)
            else:
                se_content = se_content.replace('{$VERSION}', version)
                se_content = se_content.replace('{$SERVER_PATH}', service_path)
                yf.writeFile(systemService, se_content)
                yf.execShell('systemctl daemon-reload')

    return file_bin


def tunePhpConfig(version):
    err = versionOrError(version)[0]
    if err:
        return err
    if not isInstalled(version):
        return yf.returnJson(False, 'PHP版本未安装!')
    ini_file = getConf(version)
    if not os.path.exists(ini_file):
        return yf.returnJson(False, '该版本的 PHP 配置文件不存在！')

    content = yf.readFile(ini_file)
    if not content:
        return yf.returnJson(False, '读取 PHP 配置文件失败！')

    def remove_putenv(match):
        line = match.group(0)
        eq_idx = line.find('=')
        prefix = line[:eq_idx+1]
        funcs_str = line[eq_idx+1:].strip()
        funcs = [f.strip() for f in funcs_str.split(',') if f.strip()]
        if 'putenv' in funcs:
            funcs.remove('putenv')
        return prefix + ' ' + ','.join(funcs) + '\n'

    content = re.sub(r'(?m)^;?\s*disable_functions\s*=.*', remove_putenv, content)

    tune_options = {
        'display_errors': 'Off',
        'log_errors': 'On',
        'expose_php': 'Off',
        'session.cookie_httponly': 'On',
        'opcache.enable': '1',
        'opcache.enable_cli': '1',
        'opcache.memory_consumption': '128',
        'opcache.interned_strings_buffer': '8',
        'opcache.max_accelerated_files': '10000',
        'opcache.revalidate_freq': '60',
        'opcache.save_comments': '1'
    }

    for k, v in tune_options.items():
        pattern = r'(?m)^;?\s*' + re.escape(k) + r'\s*=.*'
        if re.search(pattern, content):
            content = re.sub(pattern, f'{k} = {v}', content)
        else:
            content += f'\n{k} = {v}\n'

    yf.writeFile(ini_file, content)
    
    service_name = "php" + version
    current_os = yf.getOs()
    if current_os == 'darwin':
        file_bin = getServerDir() + '/init.d/php' + version
        yf.execShell(yf.shlexQuote(file_bin) + " restart")
    elif current_os.startswith('freebsd'):
        yf.execShell('service php' + version + ' restart')
    else:
        file_bin = getServerDir() + '/init.d/php' + version
        yf.execShell(yf.shlexQuote(file_bin) + ' stop')
        yf.execShell("systemctl restart " + service_name)

    return yf.returnJson(True, '成功对 PHP-' + version + ' 配置执行一键调优！')



def tuneAllPhpConfig():
    php_dir = getServerDir()
    if not os.path.exists(php_dir):
        return yf.returnJson(False, '/www/server/php 目录不存在！')

    versions = []
    for item in os.listdir(php_dir):
        full_path = os.path.join(php_dir, item)
        if os.path.isdir(full_path):
            if re.match(r'^\d+$', item):
                versions.append(item)

    if not versions:
        return yf.returnJson(False, '没有发现已安装的 PHP 版本！')

    tuned_versions = []
    for ver in versions:
        res = json.loads(tunePhpConfig(ver))
        if res.get('status'):
            tuned_versions.append(ver)

    return yf.returnJson(True, '成功对以下版本的 PHP 配置执行调优: ' + ', '.join(tuned_versions))


def phpOp(version, method):
    err = versionOrFail(version)
    if err:
        return err
    # 未安装的版本一律拒绝：旧实现会先跑 initReplace()，凭空造出 init.d 脚本、
    # systemd unit、etc/php.ini 与 var/run 目录（C01~C05 同族缺陷）
    if not isInstalled(version):
        return 'ERROR: PHP-' + version + ' 未安装'
    file = initReplace(version)

    current_os = yf.getOs()
    if current_os == "darwin":
        data = yf.execShell(yf.shlexQuote(file) + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    if current_os.startswith("freebsd"):
        data = yf.execShell('service php' + version + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[1]

    server_dir = getServerDir()
    ver_dir = server_dir + '/' + version
    pid_file = ver_dir + '/var/run/php-fpm.pid'

    # 兼容清理历史笔误可能生成的 /www/server/{version} 错误目录
    try:
        err_ver_dir = yf.getServerDir() + '/' + version
        if os.path.exists(err_ver_dir) and err_ver_dir != ver_dir:
            # 仅在只有 var/run 等空临时目录时安全清理
            sub_items = os.listdir(err_ver_dir)
            if not sub_items or sub_items == ['var']:
                shutil.rmtree(err_ver_dir, ignore_errors=True)
    except Exception as _e:
        _log.debug('[php] phpOp 异常已忽略: %s', _e)


    if method in ['stop', 'restart']:
        # 优先优雅停止已有服务
        yf.execShell(f'systemctl stop php{version} 2>/dev/null')
        if os.path.exists(file):
            yf.execShell(f'{yf.shlexQuote(file)} stop 2>/dev/null')
        if method == 'restart':
            time.sleep(0.5)

    if method in ['start', 'restart']:
        # 1. 确保日志和 PID 目录存在
        yf.makeDirs(ver_dir + '/var/run')
        yf.makeDirs(ver_dir + '/var/log')
        if not yf.isAppleSystem() and not current_os.startswith('freebsd'):
            yf.execShell(f'chown -R www:www {yf.shlexQuote(ver_dir)}/var/run {yf.shlexQuote(ver_dir)}/var/log')

        # 2. 确保主配置文件与核心工作池绝对健全，彻底杜绝 No pool defined
        try:
            phpFpmReplace(version)
            phpFpmPoolReplace(version, 'www')
        except Exception as e:
            yf.writeLog('php', f'PHP-{version} 配置自愈异常: {e}')

        # 2. 清理残留孤儿 socket（仅在无活动主进程时清理）
        sock = getPhpSocket(version)
        if sock and sock.find(':') == -1 and os.path.exists(sock):
            if not _findFpmMaster(version):
                try:
                    os.remove(sock)
                except Exception:
                    yf.execShell(f'rm -f {yf.shlexQuote(sock)}')

        # 3. 清理无效的僵死 PID 文件
        if os.path.exists(pid_file):
            pid_str = yf.readFile(pid_file)
            pid_str = pid_str.strip() if isinstance(pid_str, str) else ''
            if pid_str.isdigit() and not yf.checkPid(int(pid_str)):
                try:
                    os.remove(pid_file)
                except Exception as _e:
                    _log.debug('[php] phpOp 异常已忽略: %s', _e)

        # 4. 重置 systemd 失败状态
        yf.execShell(f'systemctl reset-failed php{version} 2>/dev/null')

        # 第一级高可用拉起：通过 systemctl
        res = yf.execShell(f'systemctl {method} php{version}')
        time.sleep(0.5)
        if status(version) == 'start':
            return 'ok'

        # 第二级降级拉起：通过 init.d 脚本
        if os.path.exists(file):
            yf.execShell(f'{yf.shlexQuote(file)} {method}')
            time.sleep(0.5)
            if status(version) == 'start':
                return 'ok'

        # 第三级容灾拉起：直接执行 php-fpm 二进制程序
        fpm_bin = f"{ver_dir}/sbin/php-fpm"
        fpm_conf = f"{ver_dir}/etc/php-fpm.conf"
        if os.path.exists(fpm_bin) and os.path.exists(fpm_conf):
            lib_env = "export LD_LIBRARY_PATH=/www/server/lib/icu/lib:/www/server/lib/openssl11/lib:/www/server/lib/libzip/lib:/usr/lib/x86_64-linux-gnu:/usr/lib64:/usr/local/lib:$LD_LIBRARY_PATH"
            direct_cmd = f"{lib_env} && {yf.shlexQuote(fpm_bin)} --daemonize --fpm-config {yf.shlexQuote(fpm_conf)}"
            yf.execShell(direct_cmd)
            time.sleep(0.5)
            if status(version) == 'start':
                return 'ok'

        # 收集诊断日志以供用户排查
        err_msg = res[1].strip() if res and len(res) > 1 and res[1] else ''
        fpm_log_path = ver_dir + '/var/log/php-fpm.log'
        if os.path.exists(fpm_log_path):
            log_tail = yf.execShell(f'tail -n 6 {yf.shlexQuote(fpm_log_path)}')[0].strip()
            if log_tail:
                err_msg = f"{err_msg}\n[php-fpm.log]:\n{log_tail}".strip()
        if not err_msg:
            err_msg = f"PHP-{version} 启动失败，请检查配置文件或点击【自愈修复】！"
        return err_msg

    elif method == 'stop':
        time.sleep(0.3)
        if status(version) == 'stop':
            return 'ok'
        yf.execShell(f'{yf.shlexQuote(file)} stop 2>/dev/null')
        time.sleep(0.3)
        return 'ok' if status(version) == 'stop' else 'ERROR: PHP-' + version + ' 停止失败'

    elif method == 'reload':
        data = yf.execShell(f'systemctl reload php{version} 2>/dev/null || {yf.shlexQuote(file)} reload')
        return 'ok' if data[1] == '' else data[1]

    data = yf.execShell(f'systemctl {method} php{version}')
    if data[1] == '':
        return 'ok'
    return data[1]


def start(version):
    return phpOp(version, 'start')


def stop(version):
    status_res = phpOp(version, 'stop')
    if version == '52':
        file = initReplace(version)
        if file:
            data = yf.execShell(yf.shlexQuote(file) + ' ' + 'stop')
            if data[1] == '':
                return 'ok'
    return status_res


def restart(version):
    return phpOp(version, 'restart')


def reload(version):
    if version == '52':
        return phpOp(version, 'restart')
    return phpOp(version, 'reload')


def killAllPhp(version):
    """强制终止本插件（源码编译版）的所有 php-fpm 进程。

    旧写法 `pkill -9 -f php-fpm` 是**命令行**模糊匹配：连系统包安装的
    php-fpm（comm 为 php-fpm7.4 / php-fpm8.3 / php-fpm8.4，由 php-apt 插件管理）
    一并被 SIGKILL（真机实测：php80/81/83 与 php7.4/8.3/8.4 全部被杀死，
    php80 因 unit 无 Restart 而留在 failed）。现收窄为「comm 精确等于 php-fpm」，
    只影响本插件管理的源码版，并回真实成败。
    """
    rc, out, err = yf.execShellRc('pkill -9 -x php-fpm')
    yf.execShell('rm -f /tmp/php-cgi-*.sock')
    # pkill 无匹配进程时退出码为 1，不算失败
    if rc in (0, 1):
        return 'ok'
    return 'ERROR: ' + (err.strip() or out.strip() or 'kill 失败')


def upgradeSelfHealing(version=''):
    """
    全自动平滑无损升级与环境自愈接口：
    1. 刷新配置文件与 systemd 脚本（零触碰防御：绝对保留用户现有配置与业务运行）；
    2. 创建并补齐缺失的关键临时运行与日志目录（var/run, var/log, session, upload）；
    3. 清理无效僵死 PID 与孤儿 socket 死锁；
    4. 重置 systemd 失败锁定状态并重载；
    5. 多模态精准探活，未运行则通过三级高可用拉起；
    6. 输出详细自愈诊断报告。
    """
    logs = []
    logs.append("开始执行 PHP 插件平滑无损升级与全链路环境自愈流程...")

    current_os = yf.getOs()
    if version and not isPhpVersion(version):
        return yf.returnJson(False, 'PHP版本参数不合法!')

    try:
        session_path = getServerDir() + '/tmp/session'
        upload_path = getServerDir() + '/tmp/upload'
        if not os.path.exists(session_path):
            yf.makeDirs(session_path)
        if not os.path.exists(upload_path):
            yf.makeDirs(upload_path)
        if not yf.isAppleSystem() and not current_os.startswith('freebsd'):
            yf.execShell('id www &>/dev/null || (groupadd www 2>/dev/null && useradd -g www -s /sbin/nologin www 2>/dev/null)')
            yf.execShell(f'chown -R www:www {session_path} {upload_path}')
            yf.execShell(f'chmod 777 {session_path} {upload_path}')
        logs.append("公共 Session 与 Upload 临时目录及 www 权限已校准。")
    except Exception as ex:
        logs.append(f"公共目录校准异常: {ex}")

    target_versions = [version] if version and str(version).strip() else getInstalledPhpVersions()
    if not target_versions:
        logs.append("未发现已安装的 PHP 版本，完成全局基础环境自愈。")
        return yf.returnJson(True, "\n".join(logs), {'status': 'ok', 'versions': []})

    results = {}
    skipped = []
    for ver in target_versions:
        if not isInstalled(ver):
            # 未安装的版本不得自愈：旧实现会凭空造出 etc/php.ini、init.d 脚本、
            # systemd unit 与 var/run、var/log 整棵目录树
            skipped.append(ver)
            logs.append(f"PHP-{ver} 未安装，跳过环境自愈（不创建任何文件）。")
            continue
        logs.append(f"\n--- 正在对 PHP-{ver} 执行环境自愈 ---")
        ver_dir = getVersionDir(ver)

        # 1. 目录结构自愈
        try:
            var_run = ver_dir + '/var/run'
            var_log = ver_dir + '/var/log'
            if not os.path.exists(var_run):
                yf.makeDirs(var_run)
            if not os.path.exists(var_log):
                yf.makeDirs(var_log)
            if not yf.isAppleSystem() and not current_os.startswith('freebsd'):
                yf.execShell(f'chown -R www:www {yf.shlexQuote(var_run)} {yf.shlexQuote(var_log)}')
            logs.append(f"PHP-{ver} 运行日志与 PID 目录结构已校准。")
        except Exception as ex:
            logs.append(f"PHP-{ver} 目录结构校准异常: {ex}")

        # 2. 清洗历史残留的非标准 php-fpm.conf 全局段配置并刷新服务与 systemd 脚本
        try:
            phpFpmReplace(ver)
            phpFpmPoolReplace(ver, 'www')
            phpFpmPoolReplace(ver, 'backup')
            initReplace(ver, force_refresh_service=True)
            logs.append(f"PHP-{ver} 主配置 include 路径、工作池 (Pool) 健全性与服务脚本已刷新对齐。")
        except Exception as ex:
            logs.append(f"PHP-{ver} 服务脚本与配置自愈异常: {ex}")


        # 3. 清理 systemd 失败状态
        if not yf.isAppleSystem() and not current_os.startswith('freebsd'):
            try:
                yf.execShell(f'systemctl reset-failed php{ver} 2>/dev/null')
                yf.execShell('systemctl daemon-reload 2>/dev/null')
            except Exception as ex:
                logs.append(f"Systemd 状态重置异常: {ex}")

        # 4. 孤儿 Socket 与死锁 PID 清理
        try:
            sock_file = getPhpSocket(ver)
            pid_file = ver_dir + '/var/run/php-fpm.pid'
            st = status(ver)
            if st != 'start':
                if sock_file and sock_file.find(':') == -1 and os.path.exists(sock_file):
                    if not _findFpmMaster(ver):
                        try:
                            os.remove(sock_file)
                        except Exception:
                            yf.execShell(f'rm -f {yf.shlexQuote(sock_file)}')
                        logs.append(f"已清理残留的孤儿套接字: {sock_file}")
                if os.path.exists(pid_file):
                    try:
                        os.remove(pid_file)
                    except Exception:
                        yf.execShell(f'rm -f {yf.shlexQuote(pid_file)}')
                    logs.append(f"已清理残留的僵死 PID 文件: {pid_file}")
        except Exception as ex:
            logs.append(f"PHP-{ver} 死锁排查异常: {ex}")

        # 5. 探活与三级容灾拉起
        cur_status = status(ver)
        if cur_status != 'start':
            logs.append(f"检测到 PHP-{ver} 未运行，正在尝试三级高可用拉起...")
            start_ret = start(ver)
            logs.append(f"拉起结果: {start_ret}")
        else:
            logs.append(f"PHP-{ver} 当前正在稳定运行中。")

        final_st = status(ver)
        results[ver] = final_st
        logs.append(f"PHP-{ver} 最终服务运行状态: {final_st}")

    is_all_ok = all(v == 'start' for v in results.values()) if results else False
    logs.append("\nPHP 全链路平滑升级与环境自愈完成。")
    return yf.returnJson(is_all_ok, "\n".join(logs), {'results': results, 'skipped': skipped})


def _migrate_php_1_to_2(version=''):
    """1.x 升级至 2.0 阶段单次自愈迁移"""
    return upgradeSelfHealing(version)


# 迁移流水线配置：(目标大版本, 迁移执行函数)
PHP_MIGRATION_STEPS = [
    ('2.0', _migrate_php_1_to_2),
]


def checkPluginUpgrade(version=''):
    """
    大版本升级检测与单次自愈迁移函数：
    1. 检查已持久化的版本号，若已达到当前版本直接放行（0 性能损耗）；
    2. 当检测到从 1.x 升级到 2.x 时，自动触发且仅触发一次全链路自愈；
    3. 成功后原子写回版本号到本地文件，确保跨分支升级后只执行一次。
    """
    global _PHP_UPGRADE_CHECKING
    if _PHP_UPGRADE_CHECKING:
        return yf.returnJson(True, '升级自愈正在执行中...')

    ver_file = getPluginVersionFile()
    installed_ver = '1.0'
    if os.path.exists(ver_file):
        content = yf.readFile(ver_file)
        # readFile 失败返回 False（不是空串），旧写法直接 .strip() 会 AttributeError
        if isinstance(content, str) and content.strip():
            installed_ver = content.strip()

    if _compare_version(installed_ver, CURRENT_PLUGIN_VERSION) >= 0:
        return yf.returnJson(True, '已是最新版本，无需自愈。')

    _PHP_UPGRADE_CHECKING = True
    try:
        for target_ver, mig_func in PHP_MIGRATION_STEPS:
            if _compare_version(installed_ver, target_ver) < 0:
                mig_func(version)
        yf.writeFile(ver_file, CURRENT_PLUGIN_VERSION)
        return yf.returnJson(True, '大版本迁移升级自愈成功完成。')
    finally:
        _PHP_UPGRADE_CHECKING = False


def initdStatus(version):
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile(version)
        if os.path.exists(initd_bin):
            return 'ok'

    # 用退出码判定（systemctl is-enabled），不再依赖 `systemctl status | grep` 的人类可读输出
    rc, out, err = yf.execShellRc('systemctl is-enabled php' + version)
    if rc == 0 and (out or '').strip() in ('enabled', 'enabled-runtime', 'static', 'indirect'):
        return 'ok'
    return 'fail'


def initdInstall(version):
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        source_bin = initReplace(version)
        if not source_bin:
            return 'ERROR: PHP-' + version + ' 未安装'
        initd_bin = getInitDFile(version)
        shutil.copyfile(source_bin, initd_bin)
        yf.execShell('chmod +x ' + yf.shlexQuote(initd_bin))
        return 'ok'

    if not isInstalled(version):
        return 'ERROR: PHP-' + version + ' 未安装'
    rc, out, err = yf.execShellRc('systemctl enable php' + version)
    if rc == 0:
        return 'ok'
    return 'ERROR: ' + (err.strip() or out.strip() or ('systemctl enable php%s 失败' % version))


def initdUinstall(version):
    current_os = yf.getOs()
    if current_os == 'darwin':
        return "Apple Computer does not support"

    if current_os.startswith('freebsd'):
        initd_bin = getInitDFile(version)
        if os.path.exists(initd_bin):
            os.remove(initd_bin)
        return 'ok'

    if not isInstalled(version):
        return 'ERROR: PHP-' + version + ' 未安装'
    rc, out, err = yf.execShellRc('systemctl disable php' + version)
    if rc == 0:
        return 'ok'
    return 'ERROR: ' + (err.strip() or out.strip() or ('systemctl disable php%s 失败' % version))


def fpmLog(version):
    return getVersionDir(version) + '/var/log/php-fpm.log'


def fpmSlowLog(version):
    return getVersionDir(version) + '/var/log/www-slow.log'


def getPhpConf(version):
    gets = [
        {'name': 'short_open_tag', 'type': 1, 'ps': '短标签支持'},
        {'name': 'asp_tags', 'type': 1, 'ps': 'ASP标签支持'},
        {'name': 'max_execution_time', 'type': 2, 'ps': '最大脚本运行时间'},
        {'name': 'max_input_time', 'type': 2, 'ps': '最大输入时间'},
        {'name': 'max_input_vars', 'type': 2, 'ps': '最大输入数量'},
        {'name': 'memory_limit', 'type': 2, 'ps': '脚本内存限制'},
        {'name': 'post_max_size', 'type': 2, 'ps': 'POST数据最大尺寸'},
        {'name': 'file_uploads', 'type': 1, 'ps': '是否允许上传文件'},
        {'name': 'upload_max_filesize', 'type': 2, 'ps': '允许上传文件的最大尺寸'},
        {'name': 'max_file_uploads', 'type': 2, 'ps': '允许同时上传文件的最大数量'},
        {'name': 'default_socket_timeout', 'type': 2, 'ps': 'Socket超时时间'},
        {'name': 'error_reporting', 'type': 3, 'ps': '错误级别'},
        {'name': 'display_errors', 'type': 1, 'ps': '是否输出详细错误信息'},
        {'name': 'cgi.fix_pathinfo', 'type': 0, 'ps': '是否开启pathinfo'},
        {'name': 'date.timezone', 'type': 3, 'ps': '时区'}
    ]
    defaults_map = {
        'short_open_tag': 'On',
        'asp_tags': 'Off',
        'max_execution_time': '300',
        'max_input_time': '60',
        'max_input_vars': '1000',
        'memory_limit': '128M',
        'post_max_size': '50M',
        'file_uploads': 'On',
        'upload_max_filesize': '50M',
        'max_file_uploads': '20',
        'default_socket_timeout': '60',
        'error_reporting': 'E_ALL & ~E_NOTICE',
        'display_errors': 'Off',
        'cgi.fix_pathinfo': '1',
        'date.timezone': 'PRC'
    }
    ini_path = getConf(version)
    if not os.path.exists(ini_path):
        try:
            makePhpIni(version)
        except Exception as _e:
            _log.debug('[php] getPhpConf 异常已忽略: %s', _e)

    phpini = yf.readFile(ini_path)
    if not phpini or isinstance(phpini, bool):
        phpini = ''

    result = []
    for g in gets:
        rep = r'(?m)^\s*;?\s*' + re.escape(g['name']) + r'\s*=\s*([0-9A-Za-z_& ~|!^/.-]+)'
        tmp = re.search(rep, phpini)
        if tmp:
            g['value'] = tmp.group(1).strip()
        else:
            g['value'] = defaults_map.get(g['name'], '')
        result.append(g)
    return yf.getJson(result)



def submitPhpConf(version):
    err, version = versionOrError(version)
    if err:
        return err
    gets = ['display_errors', 'cgi.fix_pathinfo', 'date.timezone', 'short_open_tag',
            'asp_tags', 'max_execution_time', 'max_input_time', 'max_input_vars', 'memory_limit',
            'post_max_size', 'file_uploads', 'upload_max_filesize', 'max_file_uploads',
            'default_socket_timeout', 'error_reporting']
    args = getArgs()
    if not isinstance(args, dict):
        args = {}
    filename = getServerDir() + '/' + version + '/etc/php.ini'
    phpini = yf.readFile(filename)
    # readFile 失败返回 False（不是空串）→ 旧实现直接 re.sub 会 TypeError
    if not phpini or isinstance(phpini, bool):
        return yf.returnJson(False, '读取 PHP 配置文件失败！')
    origin = phpini
    changed = []
    for g in gets:
        if g not in args:
            continue
        verr, val = validateIniValue(g, args[g])
        if verr:
            return yf.returnJson(False, '参数值不合法!')
        phpini = setIniKey(phpini, g, val)
        changed.append(g)
    if not changed:
        return yf.returnJson(False, '没有需要保存的配置项!')
    if not yf.writeFile(filename, phpini):
        # 写入失败回滚：保证不留下半写状态
        yf.writeFile(filename, origin)
        return yf.returnJson(False, '配置文件写入失败!')
    reload(version)
    return yf.returnJson(True, '设置成功')


def resetPhpConf(version):
    err, version = versionOrError(version)
    if err:
        return err
    defaults_map = {
        'short_open_tag': 'On',
        'asp_tags': 'Off',
        'max_execution_time': '300',
        'max_input_time': '60',
        'max_input_vars': '1000',
        'memory_limit': '128M',
        'post_max_size': '50M',
        'file_uploads': 'On',
        'upload_max_filesize': '50M',
        'max_file_uploads': '20',
        'default_socket_timeout': '60',
        'error_reporting': 'E_ALL & ~E_NOTICE',
        'display_errors': 'Off',
        'cgi.fix_pathinfo': '1',
        'date.timezone': 'PRC'
    }
    filename = getConf(version)
    if not os.path.exists(filename):
        return yf.returnJson(False, '指定PHP版本不存在!')
    phpini = yf.readFile(filename)
    if not phpini or isinstance(phpini, bool):
        return yf.returnJson(False, '读取 PHP 配置文件失败！')
    origin = phpini
    for k, v in defaults_map.items():
        phpini = setIniKey(phpini, k, v)
    if not yf.writeFile(filename, phpini):
        yf.writeFile(filename, origin)
        return yf.returnJson(False, '配置文件写入失败!')
    reload(version)
    return yf.returnJson(True, '配置已成功还原为默认值')


def getLimitConf(version):
    fileini = getConf(version)
    phpini = yf.readFile(fileini)
    if not phpini or isinstance(phpini, bool):
        phpini = ''

    filefpm = getFpmConfFile(version)
    phpfpm = yf.readFile(filefpm)
    if not phpfpm or isinstance(phpfpm, bool):
        phpfpm = ''

    data = {}
    m1 = re.search(r'(?m)^\s*;?\s*upload_max_filesize\s*=\s*([0-9]+)M', phpini)
    data['max'] = m1.group(1).strip() if m1 else '50'

    m2 = re.search(r'(?m)^\s*;?\s*request_terminate_timeout\s*=\s*([0-9]+)', phpfpm)
    data['maxTime'] = m2.group(1).strip() if m2 else 0

    m3 = re.search(r'(?m)^\s*;?\s*cgi\.fix_pathinfo\s*=\s*([0-9]+)', phpini)
    data['pathinfo'] = (m3.group(1).strip() == '1') if m3 else False

    return yf.getJson(data)



def setMaxTime(version):
    err, version = versionOrError(version)
    if err:
        return err
    if not isInstalled(version):
        return yf.returnJson(False, 'PHP版本未安装!')
    args = getArgs()
    data = checkArgs(args, ['time'])
    if not data[0]:
        return data[1]

    raw = str(args['time']).strip()
    # 旧实现直接 int(time)：非数字入参直接把 ValueError traceback 回给前端
    if not re.match(r'^[0-9]{1,6}$', raw):
        return yf.returnJson(False, '请填写30-86400间的值!')
    seconds = int(raw)
    if seconds < 30 or seconds > 86400:
        return yf.returnJson(False, '请填写30-86400间的值!')

    filefpm = getFpmConfFile(version)
    if not filefpm:
        return yf.returnJson(False, 'FPM池名不合法!')
    conf = yf.readFile(filefpm)
    if not conf or isinstance(conf, bool):
        return yf.returnJson(False, '读取 PHP-FPM 配置文件失败!')
    if not re.search(r'(?m)^\s*;?\s*request_terminate_timeout\s*=', conf):
        return yf.returnJson(False, '当前PHP-FPM配置不支持该参数!')
    conf = setIniKey(conf, 'request_terminate_timeout', str(seconds))
    if not _applyFpmConf(version, filefpm, conf):
        return yf.returnJson(False, 'FPM配置校验失败,已回滚!')

    fileini = getServerDir() + "/" + version + "/etc/php.ini"
    phpini = yf.readFile(fileini)
    if not phpini or isinstance(phpini, bool):
        return yf.returnJson(False, '读取 PHP 配置文件失败！')
    phpini = setIniKey(phpini, 'max_execution_time', str(seconds))
    phpini = setIniKey(phpini, 'max_input_time', str(seconds))
    if not yf.writeFile(fileini, phpini):
        return yf.returnJson(False, '配置文件写入失败!')
    reload(version)
    return yf.returnJson(True, '设置成功!')


def setMaxSize(version):
    err, version = versionOrError(version)
    if err:
        return err
    args = getArgs()
    data = checkArgs(args, ['max'])
    if not data[0]:
        return data[1]

    raw = str(args['max']).strip()
    if not re.match(r'^[0-9]{1,9}$', raw):
        return yf.returnJson(False, '参数值不合法!')
    maxVal = int(raw)
    if maxVal < 2:
        return yf.returnJson(False, '上传大小限制不能小于2MB!')
    if maxVal > 1048576:
        return yf.returnJson(False, '上传大小限制过大!')

    path = getConf(version)
    conf = yf.readFile(path)
    if not conf or isinstance(conf, bool):
        return yf.returnJson(False, '读取 PHP 配置文件失败！')
    origin = conf
    conf = setIniKey(conf, 'upload_max_filesize', str(maxVal) + 'M')
    conf = setIniKey(conf, 'post_max_size', str(maxVal) + 'M')
    if not yf.writeFile(path, conf):
        yf.writeFile(path, origin)
        return yf.returnJson(False, '配置文件写入失败!')
    reload(version)

    msg = yf.getInfo('设置PHP-{1}最大上传大小为[{2}MB]!', (version, str(maxVal),))
    yf.writeLog('插件管理[PHP]', msg)
    return yf.returnJson(True, '设置成功!')


def getFpmConfig(version, pool = 'www'):
    err, version = versionOrError(version)
    if err:
        return err
    args = getArgs()
    if isinstance(args, dict) and 'pool' in args:
        pool = args['pool']
    # pool 会拼进写盘路径（旧实现 `{"pool":"../../../evil"}` 真机实测建出了
    # /www/server/php/evil.conf = 任意文件写入）
    if not isPhpPool(pool):
        return yf.returnJson(False, 'FPM池名不合法!')

    filefpm = getVersionDir(version) + '/etc/php-fpm.d/' + pool + '.conf'
    if not os.path.exists(filefpm):
        try:
            phpFpmPoolReplace(version, pool)
        except Exception as _e:
            _log.debug('[php] getFpmConfig 异常已忽略: %s', _e)

    conf = yf.readFile(filefpm)
    if not conf or isinstance(conf, bool):
        conf = ''

    defaults = {
        'max_children': '30',
        'start_servers': '5',
        'min_spare_servers': '5',
        'max_spare_servers': '20',
        'pm': 'dynamic'
    }

    data = {}
    m1 = re.search(r'(?m)^\s*;?\s*pm\.max_children\s*=\s*([0-9]+)', conf)
    data['max_children'] = m1.group(1).strip() if m1 else defaults['max_children']

    m2 = re.search(r'(?m)^\s*;?\s*pm\.start_servers\s*=\s*([0-9]+)', conf)
    data['start_servers'] = m2.group(1).strip() if m2 else defaults['start_servers']

    m3 = re.search(r'(?m)^\s*;?\s*pm\.min_spare_servers\s*=\s*([0-9]+)', conf)
    data['min_spare_servers'] = m3.group(1).strip() if m3 else defaults['min_spare_servers']

    m4 = re.search(r'(?m)^\s*;?\s*pm\.max_spare_servers\s*=\s*([0-9]+)', conf)
    data['max_spare_servers'] = m4.group(1).strip() if m4 else defaults['max_spare_servers']

    m5 = re.search(r'(?m)^\s*;?\s*pm\s*=\s*([a-zA-Z]+)', conf)
    data['pm'] = m5.group(1).strip() if m5 else defaults['pm']

    return yf.getJson(data)


def setFpmConfig(version):
    err, version = versionOrError(version)
    if err:
        return err
    args = getArgs()
    if not isinstance(args, dict):
        args = {}
    # 版本/池名都来自 args，必须重新校验（拼进路径后会被写盘）
    err, version = versionOrError(args.get('version', version))
    if err:
        return err
    pool = args.get('pool', 'www')
    if not isPhpPool(pool):
        return yf.returnJson(False, 'FPM池名不合法!')
    if not isInstalled(version):
        return yf.returnJson(False, 'PHP版本未安装!')

    nums = {}
    for key in ('max_children', 'start_servers', 'min_spare_servers', 'max_spare_servers'):
        raw = str(args.get(key, '')).strip()
        if not re.match(r'^[0-9]{1,6}$', raw) or int(raw) < 1:
            return yf.returnJson(False, '并发参数不合法!')
        nums[key] = int(raw)
    pm = str(args.get('pm', 'dynamic')).strip()
    if pm not in PHP_PM_MODES:
        return yf.returnJson(False, '运行模式不合法!')
    if nums['max_children'] < nums['start_servers'] or nums['max_children'] < nums['max_spare_servers']:
        return yf.returnJson(False, 'max_spare_servers 不能大于 max_children')
    if nums['min_spare_servers'] > nums['start_servers'] or nums['min_spare_servers'] > nums['max_spare_servers']:
        return yf.returnJson(False, 'min_spare_servers 不能大于 max_spare_servers')

    file = getVersionDir(version) + '/etc/php-fpm.d/' + pool + '.conf'
    if not os.path.exists(file):
        try:
            phpFpmPoolReplace(version, pool)
        except Exception as _e:
            _log.debug('[php] setFpmConfig 异常已忽略: %s', _e)

    conf = yf.readFile(file)
    if not conf or isinstance(conf, bool):
        return yf.returnJson(False, '读取 PHP-FPM 配置文件失败!')

    for k, v in (('pm.max_children', nums['max_children']),
                 ('pm.start_servers', nums['start_servers']),
                 ('pm.min_spare_servers', nums['min_spare_servers']),
                 ('pm.max_spare_servers', nums['max_spare_servers']),
                 ('pm', pm)):
        conf = setIniKey(conf, k, v)

    if not _applyFpmConf(version, file, conf):
        return yf.returnJson(False, 'FPM配置校验失败,已回滚!')
    reload(version)

    msg = yf.getInfo('设置PHP-{1}并发设置,max_children={2},start_servers={3},min_spare_servers={4},max_spare_servers={5}', (version, str(nums['max_children']),
                                                                                                                      str(nums['start_servers']), str(nums['min_spare_servers']), str(nums['max_spare_servers']),))
    yf.writeLog('插件管理[PHP]', msg)
    return yf.returnJson(True, '设置成功!')



# def checkFpmStatusFile(version):
#     if not yf.isInstalledWeb():
#         return False

#     dfile = getServerDir() + '/nginx/conf/php_status/phpfpm_status_' + version + '.conf'
#     if not os.path.exists(dfile):
#         tpl = getPluginDir() + '/conf/phpfpm_status.conf'
#         content = yf.readFile(tpl)
#         content = contentReplace(content, version)
#         yf.writeFile(dfile, content)
#         yf.restartWeb()
#     return True


def checkFpmConf(version):
    """`php-fpm -t` 语法校验：返回 (是否通过, 输出)。

    写 pool/php-fpm 配置后必须过这一关：写错一个指令会让 php-fpm 下次 reload
    直接失败（甚至整个服务起不来），所以「写盘 → 校验 → 失败回滚」。
    """
    fpm_bin = getVersionDir(version) + '/sbin/php-fpm'
    conf = getVersionDir(version) + '/etc/php-fpm.conf'
    if not os.path.exists(fpm_bin) or not os.path.exists(conf):
        return (True, '')
    rc, out, err = yf.execShellRc([fpm_bin, '-t', '-y', conf], shell=False, timeout=20)
    text = ((err or '') + (out or '')).strip()
    return (rc == 0, text)


def _applyFpmConf(version, filepath, content):
    """写入 FPM 配置并用 php-fpm -t 校验；校验失败即回滚到写入前内容。"""
    origin = yf.readFile(filepath)
    if not isinstance(origin, str):
        origin = ''
    if not yf.writeFile(filepath, content):
        return False
    ok, msg = checkFpmConf(version)
    if not ok:
        if origin:
            yf.writeFile(filepath, origin)
        yf.writeLog('插件管理[PHP]', 'PHP-%s FPM 配置校验失败，已回滚: %s' % (version, msg))
        return False
    return True


def getFpmAddress(version, pool='www'):
    """解析某池的实际监听地址（unix socket 路径 或 (host, port) 元组）。

    旧实现有两个坑：
      1. `if bind:` 引用了未定义的 `bind` → NameError 被外层 except 吞掉，
         「php-fpm 监听 TCP」时静默回退成 unix socket 路径（连不上，fcgi 必失败）；
      2. 池里写了自定义 socket 路径（非 /tmp/php-cgi-<v>.sock）时仍回默认路径。
    """
    fpm_address = '/tmp/php-cgi-{}.sock'.format(version)
    if pool != 'www':
        fpm_address = '/tmp/php-cgi-{}.{}.sock'.format(version, pool)
    php_fpm_file = getFpmConfFile(version)
    if not php_fpm_file or not os.path.exists(php_fpm_file):
        return fpm_address
    content = yf.readFile(php_fpm_file)
    if not content or isinstance(content, bool):
        return fpm_address
    tmp = re.findall(r"^(?!\s*;)\s*listen\s*=\s*(.+)", content, re.M)
    if not tmp:
        return fpm_address
    listen = tmp[0].strip()
    if 'sock' in listen:
        # 自定义 socket 路径也要按配置返回，不能固定回 /tmp/php-cgi-<v>.sock
        return listen
    try:
        if ':' in listen:
            host, port = listen.rsplit(':', 1)
            host = host.strip().strip('[]')
            if host in ('', '*', '0.0.0.0', '::'):
                host = '127.0.0.1'
            return (host, int(port.strip()))
        return ('127.0.0.1', int(listen))
    except Exception as _e:
        _log.debug('[php] getFpmAddress 异常已忽略: %s', _e)
        return fpm_address


def getFpmStatus(version):
    err, version = versionOrError(version)
    if err:
        return err
    if version == '52':
        return yf.returnJson(False, 'PHP[' + version + ']不支持!!!')

    stat = status(version)
    if stat == 'stop':
        return yf.returnJson(False, 'PHP[' + version + ']未启动!!!')

    args = getArgs()
    if not isinstance(args, dict):
        args = {}
    pool = args.get('pool', 'www')
    if not isPhpPool(pool):
        return yf.returnJson(False, 'FPM池名不合法!')

    sock_file = getFpmAddress(version, pool)
    uri = '/phpfpm_status_' + version + '?json'
    if pool != 'www':
        uri = '/phpfpm_status_' + version + '_'+pool+'?json'
    try:
        sock_data = yf.requestFcgiPHP(sock_file, uri)
    except Exception as e:
        return yf.returnJson(False, str(e))

    # requestFcgiPHP 连接失败时回 False（不是 bytes）→ 旧实现 str(False, encoding=...) 抛 TypeError
    if not isinstance(sock_data, (bytes, bytearray)):
        return yf.returnJson(False, '获取状态失败, 返回内容异常: 连接 php-fpm 失败')

    result = str(sock_data, encoding='utf-8')
    try:
        data = json.loads(result)
    except Exception as e:
        diag_info = ""
        try:
            fpm_conf_path = getFpmConfFile(version, pool)
            conf_content = yf.readFile(fpm_conf_path)
            if not isinstance(conf_content, str):
                conf_content = ''
            status_path_match = re.search(r"^(?!\s*;)\s*pm\.status_path\s*=\s*(.+)", conf_content, re.M)
            listen_match = re.search(r"^(?!\s*;)\s*listen\s*=\s*(.+)", conf_content, re.M)
            diag_info = f"\n[Conf: {fpm_conf_path}]"
            if status_path_match:
                diag_info += f" [status_path: {status_path_match.group(1).strip()}]"
            else:
                diag_info += " [status_path: NOT FOUND]"
            if listen_match:
                diag_info += f" [listen: {listen_match.group(1).strip()}]"
            else:
                diag_info += " [listen: NOT FOUND]"
        except Exception as diag_err:
            diag_info = f"\n[Diag Err: {str(diag_err)}]"
        return yf.returnJson(False, "获取状态失败, 返回内容异常: " + result + diag_info)
    if not isinstance(data, dict) or 'start time' not in data:
        return yf.returnJson(False, '获取状态失败, 返回内容异常: ' + result)
    try:
        fTime = time.localtime(int(data['start time']))
        data['start time'] = time.strftime('%Y-%m-%d %H:%M:%S', fTime)
    except Exception as _e:
        _log.debug('[php] getFpmStatus 时间格式化失败: %s', _e)
    return yf.returnJson(True, "OK", data)


def getSessionConf(version):
    filename = getConf(version)
    if not os.path.exists(filename):
        try:
            makePhpIni(version)
        except Exception as _e:
            _log.debug('[php] getSessionConf 异常已忽略: %s', _e)

    phpini = yf.readFile(filename)
    if not phpini or isinstance(phpini, bool):
        phpini = ''

    rep = r'session\.save_handler\s*=\s*([0-9A-Za-z_& ~]+)'
    save_handler_match = re.search(rep, phpini)
    save_handler = save_handler_match.group(1).strip() if save_handler_match else "files"

    reppath = r'session\.save_path\s*=\s*"tcp\:\/\/([\d\.]+):(\d+)'
    memcached = r'session\.save_path\s*=\s*"([\d\.]+):(\d+)"'
    passrep = r'session\.save_path\s*=\s*"tcp://[\w\.\?\:]+=(.*)"'

    save_path_match = re.search(reppath, phpini) or re.search(memcached, phpini)
    passwd_match = re.search(passrep, phpini)

    port = ""
    save_path = ""
    if save_path_match:
        try:
            save_path = save_path_match.group(1)
            port = save_path_match.group(2)
        except Exception as _e:
            _log.debug('[php] getSessionConf 异常已忽略: %s', _e)

    passwd = passwd_match.group(1).strip() if passwd_match else ""

    data = {"save_handler": save_handler, "save_path": save_path,
            "passwd": passwd, "port": port}
    return yf.returnJson(True, 'ok', data)



def setSessionConf(version):
    err, version = versionOrError(version)
    if err:
        return err

    args = getArgs()
    data = checkArgs(args, ['ip', 'port', 'passwd', 'save_handler'])
    if not data[0]:
        return data[1]

    ip = str(args['ip']).strip()
    port = str(args['port']).strip()
    passwd = str(args['passwd'])
    save_handler = str(args['save_handler']).strip()

    # 存储方式白名单：旧实现任意值都回「设置成功」并原样写进 php.ini
    if save_handler not in PHP_SESSION_HANDLERS:
        return yf.returnJson(False, 'Session存储方式不合法!')

    if save_handler != "files":
        # 旧实现用非锚定的 re.search，`1.2.3.4evil` / 带换行的值也能通过
        if not isIpv4(ip):
            return yf.returnJson(False, '请输入正确的IP地址')
        if not re.match(r'^[0-9]{1,5}$', port):
            return yf.returnJson(False, '请输入正确的端口号')
        if int(port) < 1 or int(port) > 65534:
            return yf.returnJson(False, '请输入正确的端口号')
        if re.search(r'[\r\n"\'\s]', passwd) or re.search(r'[~`/=]', passwd):
            return yf.returnJson(False, '请不要输入以下特殊字符: " ~ ` / = "')

    filename = getConf(version)
    if not os.path.exists(filename):
        return yf.returnJson(False, '指定PHP版本不存在!')
    phpini = yf.readFile(filename)
    if not phpini or isinstance(phpini, bool):
        return yf.returnJson(False, '读取 PHP 配置文件失败！')
    origin = phpini

    session_tmp = getServerDir() + "/tmp/session"

    phpini = setIniKey(phpini, 'session.save_handler', save_handler)

    if save_handler in ('memcached', 'memcache'):
        if not re.search(save_handler + r'\.so', phpini):
            return yf.returnJson(False, '请先安装%s扩展' % save_handler)
        phpini = setIniKey(phpini, 'session.save_path', '"%s:%s"' % (ip, port))

    if save_handler == "redis":
        if not re.search("redis.so", phpini):
            return yf.returnJson(False, '请先安装%s扩展' % save_handler)
        auth = ("?auth=" + passwd) if passwd else ""
        phpini = setIniKey(phpini, 'session.save_path', '"tcp://%s:%s%s"' % (ip, port, auth))

    if save_handler == "files":
        phpini = setIniKey(phpini, 'session.save_path', '"%s"' % session_tmp)

    if not yf.writeFile(filename, phpini):
        yf.writeFile(filename, origin)
        return yf.returnJson(False, '配置文件写入失败!')
    reload(version)
    return yf.returnJson(True, '设置成功!')


def getSessionCount_Origin(version):
    session_tmp = getServerDir() + "/tmp/session"
    d = [session_tmp]
    count = 0
    for i in d:
        if not os.path.exists(i):
            yf.makeDirs(i)
        items = os.listdir(i)
        for l in items:
            if os.path.isdir(i + "/" + l):
                l1 = os.listdir(i + "/" + l)
                for ll in l1:
                    if "sess_" in ll:
                        count += 1
                continue
            if "sess_" in l:
                count += 1

    # -maxdepth 2：旧实现无深度限制地遍历整个 /tmp（每次统计一次全量扫盘）；
    # 并且用 int() 直接吃 shell 输出，find 报错回空串就 ValueError
    s = "find /tmp -maxdepth 2 -type f -mtime +1 -name 'sess_*' 2>/dev/null | wc -l"
    old_file = _intShell(s)

    s = "find " + yf.shlexQuote(session_tmp) + " -maxdepth 2 -type f -mtime +1 -name 'sess_*' 2>/dev/null | wc -l"
    old_file += _intShell(s)
    return {"total": count, "oldfile": old_file}


def _intShell(cmd):
    """执行 shell 并把首行解析为整数（解析不了算 0）。"""
    data = yf.execShell(cmd)
    first = (data[0] or '').split('\n')[0].strip() if data and data[0] else ''
    return int(first) if first.isdigit() else 0


def getSessionCount(version):
    data = getSessionCount_Origin(version)
    return yf.returnJson(True, 'ok!', data)


def cleanSessionOld(version):
    # 旧实现 `find /tmp -mtime +1 | grep 'sess_' | xargs rm -f` 会以 root 删掉 /tmp
    # 下任意路径含 sess_ 的**非 session 文件**（且 xargs 未带 -0/-r，含空格文件名会被拆开）。
    # 收窄为「普通文件 + 名字以 sess_ 开头 + 最多 2 层」，并交回真实成败。
    yf.execShell("find /tmp -maxdepth 2 -type f -mtime +1 -name 'sess_*' -print0 2>/dev/null | xargs -0 -r rm -f")

    session_tmp = getServerDir() + "/tmp/session"
    yf.execShell("find " + yf.shlexQuote(session_tmp) + " -maxdepth 2 -type f -mtime +1 -name 'sess_*' -print0 2>/dev/null | xargs -0 -r rm -f")
    old_file_conf = getSessionCount_Origin(version)["oldfile"]
    if old_file_conf == 0:
        return yf.returnJson(True, '清理成功')
    # 旧实现把失败也包成 status:true（前端只能看消息、图标却是成功）
    return yf.returnJson(False, '清理失败')


def getDisableFunc(version):
    err, version = versionOrError(version)
    if err:
        return err
    filename = getConf(version)
    if not os.path.exists(filename) or os.path.getsize(filename) < 50:
        try:
            makePhpIni(version)
        except Exception as _e:
            _log.debug('[php] getDisableFunc 异常已忽略: %s', _e)

    phpini = yf.readFile(filename)
    if not phpini or isinstance(phpini, bool):
        phpini = ''
    data = {}
    rep = r"(?m)^\s*;?\s*disable_functions\s*=\s*(.*)"
    match = re.search(rep, phpini)
    if match and match.group(1).strip():
        data['disable_functions'] = match.group(1).strip()
    else:
        data['disable_functions'] = DEFAULT_DISABLE_FUNCTIONS
        if os.path.exists(filename):
            try:
                if match:
                    phpini = re.sub(rep, f'disable_functions = {DEFAULT_DISABLE_FUNCTIONS}', phpini)
                else:
                    phpini = phpini.rstrip() + f'\ndisable_functions = {DEFAULT_DISABLE_FUNCTIONS}\n'
                yf.writeFile(filename, phpini)
            except Exception as _e:
                _log.debug('[php] getDisableFunc 异常已忽略: %s', _e)

    return yf.getJson(data)


def setDisableFunc(version, disable_functions=None):
    err, version = versionOrError(version)
    if err:
        return err
    filename = getConf(version)
    if not os.path.exists(filename):
        return yf.returnJson(False, '指定PHP版本不存在!')

    if disable_functions is None:
        args = getArgs()
        if not isinstance(args, dict):
            args = {}
        disable_functions = str(args.get('disable_functions', '')).strip()
    else:
        disable_functions = str(disable_functions).strip()

    # 函数名单白名单：旧实现把用户值直接写进 php.ini 的 `disable_functions = ` 行，
    # 换行即可注入任意指令（如 `allow_url_include = On`）。
    if not PHP_FUNC_LIST_RE.match(disable_functions):
        return yf.returnJson(False, '禁用函数格式不合法!')

    phpini = yf.readFile(filename)
    # 读失败时旧实现把 phpini 当空串，然后 writeFile 覆写 → 整份 php.ini 只剩一行（数据丢失）
    if not phpini or isinstance(phpini, bool):
        return yf.returnJson(False, '读取 PHP 配置文件失败！')

    phpini = setIniKey(phpini, 'disable_functions', disable_functions)

    msg = yf.getInfo('修改PHP-{1}的禁用函数为[{2}]', (version, disable_functions,))
    yf.writeLog('插件管理[PHP]', msg)
    if not yf.writeFile(filename, phpini):
        return yf.returnJson(False, '配置文件写入失败!')
    reload(version)
    return yf.returnJson(True, '设置成功!')


def resetDisableFunc(version):
    return setDisableFunc(version, DEFAULT_DISABLE_FUNCTIONS)



def getPhpinfo(version):
    err, version = versionOrError(version)
    if err:
        return err
    stat = status(version)
    if stat == 'stop':
        return 'PHP[' + version + ']未启动,不可访问!!!'

    sock_file = getFpmAddress(version)
    root_dir = yf.getFatherDir() + '/phpinfo'

    yf.removeDir(root_dir)
    yf.makeDirs(root_dir)
    yf.writeFile(root_dir + '/phpinfo.php', '<?php phpinfo(); ?>')
    try:
        sock_data = yf.requestFcgiPHP(sock_file, '/phpinfo.php', root_dir)
    finally:
        yf.removeDir(root_dir)
    # requestFcgiPHP 连接失败时回 False（不是 bytes）→ 旧实现 str(False, encoding=...) 抛 TypeError
    if not isinstance(sock_data, (bytes, bytearray)):
        return 'PHP[' + version + ']phpinfo 获取失败,请检查 php-fpm 监听地址!'
    return str(sock_data, encoding='utf-8', errors='replace')


def get_php_info(args):
    if not isinstance(args, dict) or 'version' not in args:
        return '缺少必要参数: version'
    return getPhpinfo(args['version'])


def libConfCommon(version):
    fname = getConf(version)
    if not os.path.exists(fname):
        return yf.returnJson(False, '指定PHP版本不存在!')

    phpini = yf.readFile(fname)
    if not phpini or isinstance(phpini, bool):
        return yf.returnJson(False, '读取 PHP 配置文件失败！')

    libpath = getPluginDir() + '/versions/phplib.conf'
    phplib_raw = yf.readFile(libpath)
    if not phplib_raw or isinstance(phplib_raw, bool):
        return yf.returnJson(False, '扩展列表配置文件不存在!')
    try:
        phplib = json.loads(phplib_raw)
    except Exception:
        return yf.returnJson(False, '扩展列表配置文件格式错误!')
    if not isinstance(phplib, list):
        return yf.returnJson(False, '扩展列表配置文件格式错误!')

    libs = []
    tasks = yf.M('tasks').where("status!=?", ('1',)).field('status,name').select()
    for lib in phplib:
        lib['task'] = '1'
        for task in tasks:
            tmp = yf.getStrBetween('[', ']', task['name'])
            if not tmp:
                continue
            tmp1 = tmp.split('-')
            if tmp1[0].lower() == lib['name'].lower():
                lib['task'] = task['status']
                lib['phpversions'] = []
                lib['phpversions'].append(tmp1[1])
        if phpini.find(lib['check']) == -1:
            lib['status'] = False
        else:
            lib['status'] = True
        libs.append(lib)
    return libs


def get_lib_conf(data):
    libs = libConfCommon(data['version'])
    if isinstance(libs, str):
        return libs
    return yf.returnData(True, 'OK!', libs)


def getLibConf(version):
    libs = libConfCommon(version)
    if isinstance(libs, str):
        return libs
    return yf.returnJson(True, 'OK!', libs)


def getLibNames():
    """phplib.conf 里的合法扩展名清单（小写）——作为 shell 命令的白名单。"""
    raw = yf.readFile(getPluginDir() + '/versions/phplib.conf')
    if not raw or isinstance(raw, bool):
        return []
    try:
        libs = json.loads(raw)
    except Exception:
        return []
    names = []
    for lib in (libs if isinstance(libs, list) else []):
        if not isinstance(lib, dict):
            continue
        n = str(lib.get('name', '')).strip()
        if n and re.match(r'^[A-Za-z0-9_\-]{1,32}$', n):
            names.append(n.lower())
    return names


def isLibName(name):
    """扩展名是否合法（必须命中 phplib.conf 白名单）。

    旧实现把 name 直接拼进 shell：`... common.sh 83 install x; touch /tmp/pwned`
    会以 root 真实执行（真机实测已复现），并且 install_lib 还会把该命令**写进后台任务队列**。
    """
    n = str(name if name is not None else '').strip()
    if not re.match(r'^[A-Za-z0-9_\-]{1,32}$', n):
        return False
    return n.lower() in getLibNames()


def installLib(version):
    err, version = versionOrError(version)
    if err:
        return err
    if not isInstalled(version):
        return yf.returnJson(False, 'PHP版本未安装!')
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = str(args['name']).strip()
    if not isLibName(name):
        return yf.returnJson(False, '扩展名称不合法!')
    cmd = "cd " + yf.shlexQuote(getPluginDir() + "/versions") + " && /bin/bash common.sh " + version + ' install ' + name
    install_name = '安装[' + name + '-' + version + ']'
    import thisdb
    thisdb.addTask(name=install_name,cmd=cmd)

    yf.triggerTask()
    return yf.returnJson(True, '已将下载任务添加到队列!')


def uninstallLib(version):
    err, version = versionOrError(version)
    if err:
        return err
    if not isInstalled(version):
        return yf.returnJson(False, 'PHP版本未安装!')
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = str(args['name']).strip()
    if not isLibName(name):
        return yf.returnJson(False, '扩展名称不合法!')
    execstr = "cd " + yf.shlexQuote(getPluginDir() + "/versions") + " && /bin/bash common.sh " + version + ' uninstall ' + name

    rc, out, err_out = yf.execShellRc(execstr)
    out = out or ''
    err_out = err_out or ''
    # common.sh 找不到扩展脚本时只 echo 'no such extension' 且退出码仍为 0
    # （旧实现只看 stderr 空就回「已经卸载成功!」= 假成功）
    if 'no such extension' in (out + err_out):
        return yf.returnJson(False, '未找到该扩展的卸载脚本!')
    if rc != 0:
        return yf.returnJson(False, '卸载信息![通道0]:' + out + "[通道0]:" + err_out)
    return yf.returnJson(True, '已经卸载成功!')


def getConfAppStart():
    pstart = yf.getServerDir() + '/php/app_start.php'
    return pstart

def opcacheBlacklistFile():
    op_bl = yf.getServerDir() + '/php/opcache-blacklist.txt'
    return op_bl


def installPreInspection(version):
    # 仅对PHP52检查
    if version != '52':
        return 'ok'

    sys = yf.execShell(
        "cat /etc/*-release | grep PRETTY_NAME |awk -F = '{print $2}' | awk -F '\"' '{print $2}'| awk '{print $1}'")

    if sys[1] != '':
        return '不支持改系统'

    sys_id = yf.execShell(
        "cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}' | awk -F '\"' '{print $2}'")

    sysName = sys[0].strip().lower()
    sysId = sys_id[0].strip()

    if sysName == 'ubuntu':
        return 'ubuntu已经安装不了'

    if not sysId.isdigit():
        return 'ok'

    if sysName == 'debian' and int(sysId) > 10:
        return 'debian10可以安装'

    if sysName == 'centos' and int(sysId) > 8:
        return 'centos[{}]不可以安装'.format(sysId)

    if sysName == 'fedora':
        sys_id = yf.execShell(
            "cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}'")
        sysId = sys_id[0].strip()
        if not sysId.isdigit():
            return 'ok'
        if int(sysId) > 31:
            return 'fedora[{}]不可安装'.format(sysId)
    return 'ok'


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print('missing parameters')
        exit(0)

    func = sys.argv[1]

    if func == 'tune_all':
        print(tuneAllPhpConfig())
        exit(0)

    if func == 'check_plugin_upgrade':
        ver = sys.argv[2] if len(sys.argv) > 2 else ''
        print(checkPluginUpgrade(ver))
        exit(0)

    if func == 'upgrade_self_healing':
        ver = sys.argv[2] if len(sys.argv) > 2 else ''
        print(upgradeSelfHealing(ver))
        exit(0)

    if len(sys.argv) < 3:
        if func == 'kill_all_php':
            print(killAllPhp(''))
            exit(0)
        print('missing parameters')
        exit(0)

    version = sys.argv[2]

    # 版本号是全模块唯一的用户可控「路径/命令片段」，在统一入口再拦一道：
    # 以下 func 的返回值会被前端当成文件路径直接交给 /files/get_body，
    # 非纯数字版本（如 `../../etc`）会造成任意文件读取面。
    if func in ('conf', 'get_fpm_conf_file', 'get_fpm_file', 'fpm_log', 'fpm_slow_log') \
            and not isPhpVersion(version):
        print('ERROR: PHP版本参数不合法')
        exit(0)

    if func == 'status':
        print(status(version))
    elif func == 'upgrade_self_healing':
        print(upgradeSelfHealing(version))
    elif func == 'check_plugin_upgrade':
        print(checkPluginUpgrade(version))
    elif func == 'start':
        print(start(version))
    elif func == 'stop':
        print(stop(version))
    elif func == 'restart':
        print(restart(version))
    elif func == 'reload':
        print(reload(version))
    elif func == 'kill_all_php':
        print(killAllPhp(version))
    elif func == 'install_pre_inspection':
        print(installPreInspection(version))
    elif func == 'initd_status':
        print(initdStatus(version))
    elif func == 'initd_install':
        print(initdInstall(version))
    elif func == 'initd_uninstall':
        print(initdUinstall(version))
    elif func == 'fpm_log':
        print(fpmLog(version))
    elif func == 'fpm_slow_log':
        print(fpmSlowLog(version))
    elif func == 'conf':
        print(getConf(version))
    elif func == 'app_start':
        print(getConfAppStart())
    elif func == 'opcache_blacklist_file':
        print(opcacheBlacklistFile())
    elif func == 'tune_php_config':
        print(tunePhpConfig(version))
    elif func == 'get_php_conf':
        print(getPhpConf(version))
    elif func == 'get_fpm_conf_file':
        print(getFpmConfFile(version))
    elif func == 'get_fpm_file':
        print(getFpmFile(version))
    elif func == 'submit_php_conf':
        print(submitPhpConf(version))
    elif func == 'reset_php_conf':
        print(resetPhpConf(version))
    elif func == 'get_limit_conf':
        print(getLimitConf(version))
    elif func == 'set_max_time':
        print(setMaxTime(version))
    elif func == 'set_max_size':
        print(setMaxSize(version))
    elif func == 'get_fpm_conf':
        print(getFpmConfig(version))
    elif func == 'set_fpm_conf':
        print(setFpmConfig(version))
    elif func == 'get_fpm_status':
        print(getFpmStatus(version))
    elif func == 'get_session_conf':
        print(getSessionConf(version))
    elif func == 'set_session_conf':
        print(setSessionConf(version))
    elif func == 'get_session_count':
        print(getSessionCount(version))
    elif func == 'clean_session_old':
        print(cleanSessionOld(version))
    elif func == 'get_disable_func':
        print(getDisableFunc(version))
    elif func == 'set_disable_func':
        print(setDisableFunc(version))
    elif func == 'reset_disable_func':
        print(resetDisableFunc(version))
    elif func == 'get_phpinfo':
        print(getPhpinfo(version))
    elif func == 'get_lib_conf':
        print(getLibConf(version))
    elif func == 'install_lib':
        print(installLib(version))
    elif func == 'uninstall_lib':
        print(uninstallLib(version))
    else:
        print("fail")
