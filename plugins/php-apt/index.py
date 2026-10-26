# coding:utf-8

import sys
import io
import os
import time
import re
import json
import shutil
import tempfile


# 动态获取项目根目录，避免因执行脚本时当前工作目录(Cwd)不同而导致 core 依赖导入失败
panel_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
web_dir = os.path.join(panel_root, "web")
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import logging

# P0-2：安全基线表 + 包版本读取（与编译版插件共用同一份基线，不许各写一套）
from core import php_sec_baseline
from core import php_sec_scan
# 索引刷不下来时把「证书校验失败 / 302 到认证页」翻成人话（否则报文只会让用户去改源）
from core import net_probe
# 离线 .deb 通道（内网/无外网机器唯一能升级的那条路）
from core import php_deb_bundle

_log = logging.getLogger('yf.php_apt')

app_debug = False
if yf.isAppleSystem():
    app_debug = True

CURRENT_PLUGIN_VERSION = '2.0'
_PHP_APT_UPGRADE_CHECKING = False

#: 版本号白名单：安装目录名即「主.次」版本（如 7.4 / 8.3），与 getInstalledPhpVersions 的
#  磁盘目录过滤同口径。version 会被拼进文件路径与 shell 命令，是 php-apt 唯一用户可控的
#  「路径/命令片段」入口，必须先校验再使用（formatVersion 只做补点归一化，不做安全校验）。
PHP_APT_VERSION_RE = re.compile(r'^[0-9]{1,3}\.[0-9]{1,3}$')
#: FPM 进程管理方式白名单（写入 pool 配置的 `pm = ` 行）。
PHP_PM_MODES = ('static', 'dynamic', 'ondemand')
#: Session 存储方式白名单（写入 php.ini 的 `session.save_handler` 行）。
PHP_SESSION_HANDLERS = ('files', 'redis', 'memcache', 'memcached')
#: 禁用函数名白名单（逗号分隔）。
PHP_FUNC_LIST_RE = re.compile(r'^[A-Za-z0-9_ ,]{0,4000}$')
#: php.ini 可写键的值白名单：只接受预期取值形态，阻止换行注入任意指令。
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
    'memory_limit': r'^(-1|[0-9]{1,9}[KMG]?)$',
    'post_max_size': r'^[0-9]{1,9}[KMG]?$',
    'upload_max_filesize': r'^[0-9]{1,9}[KMG]?$',
    'error_reporting': r'^[0-9A-Za-z_ &~|^!()-]{1,60}$',
    'date.timezone': r'^[A-Za-z0-9_/+\-]{1,40}$',
}


def formatVersion(v):
    v = str(v).strip()
    if not v:
        return ''
    if '.' in v:
        return v
    if len(v) >= 2:
        return v[0] + '.' + v[1:]
    return v


def isPhpVersion(version):
    """版本号是否为「主.次」形态（防路径穿越与 shell 注入）。"""
    return bool(PHP_APT_VERSION_RE.match(str(version if version is not None else '').strip()))


def versionOrError(version):
    """JSON 信封型入口的版本校验：非法返回 (错误信封, None)，合法返回 (None, 版本)。"""
    v = str(version if version is not None else '').strip()
    if not isPhpVersion(v):
        return (yf.returnJson(False, 'PHP版本参数不合法!'), None)
    return (None, v)


def versionOrFail(version):
    """原始字符串型入口（status/start/conf 等）的版本校验：非法返回错误文案。"""
    v = str(version if version is not None else '').strip()
    if not isPhpVersion(v):
        return 'ERROR: PHP版本参数不合法'
    return None


def validateIniValue(key, value):
    """校验 php.ini 单键取值：返回 (错误消息, 规范化值)，合法时错误消息为 ''。"""
    if not isinstance(value, str):
        value = str(value)
    v = value.strip()
    rule = PHP_INI_KEY_RULES.get(key)
    if rule is None:
        return ('参数值不合法!', None)
    if not re.match(rule, v):
        return ('参数值不合法!', None)
    return ('', v)


def setIniKey(content, key, value):
    """把 `key = value` 写回 ini 文本（含被注释的同名行），保留其余内容。

    用 lambda 做替换体：旧实现直接拿用户值当 re.sub 的替换字符串，值里出现
    `\\1`/`\\g<...>` 会报 re.error 或被当作分组引用。
    """
    pattern = r'(?m)^\s*;?\s*' + re.escape(key) + r'\s*=.*'
    line = '%s = %s' % (key, value)
    if re.search(pattern, content):
        return re.sub(pattern, lambda m: line, content)
    return content.rstrip('\n') + '\n' + line + '\n'


def getPluginName():
    return 'php-apt'


def getAppDir():
    return yf.getServerDir() + '/' + getPluginName()


def getServerDir():
    return '/etc/php'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getPluginVersionFile():
    return getPluginDir() + '/plugin_version.pl'


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
    """获取系统 apt **确实已安装**的 PHP 版本列表（如 ['7.4', '8.1']）。

    只看目录名是不够的：`apt-get remove` 会留下 `/etc/php/<X.Y>` 与 dpkg 的 `rc`
    记录（版本串仍可读），旧实现因此把**已卸载**的 PHP 当成已装；
    真机现场就是这样对 PHP8.2 点「升级到基线」，apt 回
    `Skipping php8.2-fpm, it is not installed and only upgrades are requested`。
    判据改为以 dpkg 包状态为准（`php_sec_scan.read_package_version` 已识别 `rc`）。
    """
    php_dir = getServerDir()
    if not os.path.exists(php_dir):
        return []
    versions = []
    for item in os.listdir(php_dir):
        full_path = os.path.join(php_dir, item)
        if not os.path.isdir(full_path) or not re.match(r'^\d+\.\d+$', item):
            continue
        if not php_sec_scan.read_package_version('apt', item.replace('.', '')):
            _log.debug('[php-apt] 跳过未安装（仅剩目录/配置）的 PHP%s: %s', item, full_path)
            continue
        versions.append(item)
    return sorted(versions)


def missingPackageEnvelope(ver):
    """读不到已装包时给前端的信封：区分「真没装」与「装过但已卸载（rc 残留）」。"""
    hint = remnantHint(ver)
    if hint:
        _logLine('[php-apt] %s' % hint)
        return yf.returnJson(False, hint, {'state': 'remnant'})
    return yf.returnJson(False, '未检测到 apt 包 php%s-fpm，请确认已通过 APT 渠道安装' % ver)


def remnantHint(ver):
    """该版本只剩「已卸载残留」时，给一句可执行的处置办法（不是残留就返回空）。"""
    branch = str(ver or '').replace('.', '')
    try:
        info = php_sec_scan.apt_package_state(branch)
    except Exception as ex:                # noqa: BLE001 —— 提示失败不能让升级流程崩
        _log.debug('[php-apt] 读取 dpkg 包状态失败: %s', ex)
        return ''
    if not info.get('remnant'):
        return ''
    # 注意：purge 的包名**不能**加引号 —— 要让 shell 把 `php8.2-*` 展开成真实包名
    # （apt 自己不认通配符），写成 `'php8.2-*'` 反而会「找不到软件包」。
    # 两条命令刻意分开写：语言包键里出现 `&&` 会被 i18n 污染检测当成注入特征。
    return ('PHP%s 的 apt 包当前状态是 %s（已卸载，仅剩配置文件），apt 无法升级；请先清理残留（两条命令）：apt-get purge -y php%s-* ，再执行 rm -rf /etc/php/%s，然后在面板重新安装 PHP%s'
            % (ver, info.get('state') or 'rc', ver, ver, ver))


def getArgs():
    """解析插件参数。

    面板 `utils/plugin.py::run()` 把 args 当**一个** argv 传进来，前端 `YfPlugin.parseArgs`
    统一发 JSON 字符串，因此 JSON 优先；同时兼容 `k:v` 旧写法。任何畸形入参一律回 {}
    而不是抛 IndexError/JSONDecodeError/TypeError（旧实现 json.loads 出非 dict 时直接崩）。
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


DEFAULT_DISABLE_FUNCTIONS = (
    'passthru,exec,system,chroot,chgrp,chown,shell_exec,popen,proc_open,pcntl_exec,'
    'ini_alter,ini_restore,dl,openlog,syslog,readlink,symlink,popepassthru,pcntl_alarm,'
    'pcntl_fork,pcntl_waitpid,pcntl_wait,pcntl_wifexited,pcntl_wifstopped,pcntl_wifsignaled,'
    'pcntl_wifcontinued,pcntl_wexitstatus,pcntl_wtermsig,pcntl_wstopsig,pcntl_signal,'
    'pcntl_signal_dispatch,pcntl_get_last_error,pcntl_strerror,pcntl_sigprocmask,'
    'pcntl_sigwaitinfo,pcntl_sigtimedwait,pcntl_exec,pcntl_getpriority,pcntl_setpriority,'
    'imap_open,apache_setenv'
)


def getConf(version):
    if not isPhpVersion(version):
        return ''
    path = getServerDir() + '/' + version + '/fpm/php.ini'
    if not os.path.exists(path) or os.path.getsize(path) < 50:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        content = (
            "[PHP]\nengine = On\nshort_open_tag = On\nprecision = 14\n"
            "output_buffering = 4096\nzlib.output_compression = Off\n"
            f"disable_functions = {DEFAULT_DISABLE_FUNCTIONS}\n"
            "max_execution_time = 300\nupload_max_filesize = 50M\npost_max_size = 50M\n"
            "date.timezone = PRC\n"
        )
        yf.writeFile(path, content)
    return path


def getFpmConfFile(version):
    return getServerDir() + '/' + version + '/fpm/pool.d/yf.conf'

def getFpmFile(version):
    return getServerDir() + '/' + version + '/fpm/php-fpm.conf'

def ensureSystemdOverride(version):
    """
    为 PHP-APT 创建 systemd service override 配置：
    1. 彻底解除启动频率超限限制 (StartLimitIntervalSec=0)，杜绝 start-limit-hit 锁定；
    2. 设置异常自动平滑自愈 (Restart=always, RestartSec=3s)；
    3. 给予充足超时缓冲 (TimeoutStartSec=60s)，防止因握手瞬态延迟被 systemd 强杀。
    """
    if yf.isAppleSystem():
        return
    version = formatVersion(version)
    override_dir = f'/etc/systemd/system/php{version}-fpm.service.d'
    override_file = os.path.join(override_dir, 'override.conf')
    override_content = """[Unit]
StartLimitIntervalSec=0

[Service]
Restart=always
RestartSec=3s
TimeoutStartSec=60s
TimeoutStopSec=15s
"""
    try:
        need_write = True
        if os.path.exists(override_file):
            old = yf.readFile(override_file)
            if old and 'StartLimitIntervalSec=0' in old and 'Restart=always' in old:
                need_write = False
        if need_write:
            os.makedirs(override_dir, exist_ok=True)
            yf.writeFile(override_file, override_content)
            yf.execShell('systemctl daemon-reload 2>/dev/null || true')
    except Exception as e:
        yf.writeLog('php-apt', f'注入 systemd override 容灾配置失败: {e}')


def _pidIsPhpFpmMaster(pid, version):
    """pid 是否确属本版本的 php-fpm master。

    防陈旧 pid 文件指向无关存活进程时 `os.kill(pid, 0)` 成功即误报 start（C07 同族）。
    """
    try:
        with open('/proc/%s/comm' % pid, 'r', encoding='utf-8', errors='replace') as fp:
            comm = fp.read().strip()
        if comm != 'php-fpm':
            return False
        with open('/proc/%s/cmdline' % pid, 'rb') as fp:
            args = fp.read().replace(b'\x00', b' ').decode('utf-8', 'replace')
        return ('/etc/php/%s/' % version) in args or ('(%s)' % version) in args
    except Exception:
        return False


def status(version):
    if yf.isAppleSystem():
        return 'stop'

    version = formatVersion(version)
    err = versionOrFail(version)
    if err:
        return err
    try:
        checkPluginUpgrade(version)
    except Exception as _e:
        _log.debug('[php-apt] status 异常已忽略: %s', _e)

    # 1. 优先采用 systemctl is-active
    cmd = "systemctl is-active php" + version + "-fpm"
    data = yf.execShell(cmd)
    st = data[0].strip()
    if st == 'active':
        return 'start'
    elif st == 'activating':
        # 处于启动中过渡状态，检测其进程是否已经就绪，防止误判 stop
        chk_act = yf.execShell(f"ps aux | grep 'php-fpm: master process' | grep -E '(/etc/php/{version}/|\\({version}\\)|php-fpm{version})' | grep -v grep")
        if chk_act and chk_act[0].strip():
            return 'start'

    # 2. 降级通过 pid 文件校验（必须确认 pid 真属于本版本的 php-fpm master）
    pid_file = '/run/php/php' + version + '-fpm.pid'
    if os.path.exists(pid_file):
        try:
            pid_str = yf.readFile(pid_file)
            pid_str = pid_str.strip() if isinstance(pid_str, str) else ''
            if pid_str and pid_str.isdigit():
                pid = int(pid_str)
                if _pidIsPhpFpmMaster(pid, version):
                    return 'start'
        except Exception as _e:
            _log.debug('[php-apt] status 异常已忽略: %s', _e)

    # 3. 降级通过进程树特征匹配（精确匹配 Debian/Ubuntu 原生路径 /etc/php/{version}/ 及别名）
    chk = yf.execShell(f"ps aux | grep 'php-fpm: master process' | grep -E '(/etc/php/{version}/|\\({version}\\)|php-fpm{version})' | grep -v grep")
    if chk and chk[0].strip():
        return 'start'

    return 'stop'



def contentReplace(content, version):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace('{$PHP_VERSION}', version)
    content = content.replace('{$LOCAL_IP}', yf.getLocalIp())

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


def getDstEnablePHP(version):
    sdir = yf.getServerDir()
    dfile = sdir + '/web_conf/php/conf/enable-php-apt' + version + '.conf'
    return dfile


def makeOpConf(version):
    if not isPhpVersion(version):
        return

    sdir = yf.getServerDir()

    dst_dir_conf = sdir + '/web_conf/php/conf'
    if not os.path.exists(dst_dir_conf):
        yf.makeDirs(dst_dir_conf)

    pathinfo = sdir + '/web_conf/php/pathinfo.conf'
    if not os.path.exists(pathinfo):
        source_pathinfo = getPluginDir() + '/conf/pathinfo.conf'
        shutil.copyfile(source_pathinfo, pathinfo)

    info = getPluginDir() + '/info.json'
    content = yf.readFile(info)
    if not content:
        return
    content = json.loads(content)
    versions = content['versions']
    tpl = getPluginDir() + '/conf/enable-php.conf'
    tpl_content = yf.readFile(tpl)
    if not tpl_content:
        return
    dfile = getDstEnablePHP(version)
    if not os.path.exists(dfile):
        w_content = contentReplace(tpl_content, version)
        yf.writeFile(dfile, w_content)


def phpFpmWwwReplace(version):
    service_php_fpm_dir = getServerDir() + '/' + version + '/fpm/pool.d'
    if not os.path.exists(service_php_fpm_dir):
        os.mkdir(service_php_fpm_dir)

    service_php_fpmwww = service_php_fpm_dir + '/www.conf'
    if os.path.exists(service_php_fpmwww):
        # 原来文件备份
        yf.execShell('mv ' + service_php_fpmwww +
                     ' ' + service_php_fpmwww + '.bak')

    service_php_fpm_yf = service_php_fpm_dir + '/yf.conf'
    need_regenerate = False
    if not os.path.exists(service_php_fpm_yf):
        need_regenerate = True
    else:
        raw = yf.readFile(service_php_fpm_yf)
        if not raw or not re.search(r'(?m)^\s*\[[^\]]+\]', raw):
            need_regenerate = True

    if need_regenerate:
        tpl_php_fpmwww = getPluginDir() + '/conf/www.conf'
        content = yf.readFile(tpl_php_fpmwww)
        if not content:
            content = f"[yf]\nuser = www-data\ngroup = www-data\nlisten = /run/php/php{version}-fpm.sock\npm = dynamic\npm.max_children = 30\npm.start_servers = 5\npm.min_spare_servers = 5\npm.max_spare_servers = 20\n"
        content = contentReplace(content, version)
        
        # 动态根据内存计算 FPM 进程数
        try:
            mem_total_str = yf.execShell("LC_ALL=C free -m | grep Mem | awk '{print $2}'")[0].strip()
            if mem_total_str:
                mem_total = int(mem_total_str)
                if mem_total <= 1024:
                    max_children = 20; start_servers = 2; min_spare_servers = 2; max_spare_servers = 5
                elif mem_total <= 2048:
                    max_children = 40; start_servers = 3; min_spare_servers = 3; max_spare_servers = 10
                elif mem_total <= 4096:
                    max_children = 80; start_servers = 5; min_spare_servers = 5; max_spare_servers = 20
                elif mem_total <= 8192:
                    max_children = 120; start_servers = 10; min_spare_servers = 10; max_spare_servers = 30
                else:
                    max_children = 200; start_servers = 15; min_spare_servers = 15; max_spare_servers = 50
                    
                content = re.sub(r'(?m)^pm\.max_children\s*=\s*\d+', f'pm.max_children = {max_children}', content)
                content = re.sub(r'(?m)^pm\.start_servers\s*=\s*\d+', f'pm.start_servers = {start_servers}', content)
                content = re.sub(r'(?m)^pm\.min_spare_servers\s*=\s*\d+', f'pm.min_spare_servers = {min_spare_servers}', content)
                content = re.sub(r'(?m)^pm\.max_spare_servers\s*=\s*\d+', f'pm.max_spare_servers = {max_spare_servers}', content)
        except Exception as e:
            yf.writeLog('php-apt', '动态配置 FPM 进程数失败: ' + str(e))

        yf.writeFile(service_php_fpm_yf, content)
    return True


def deleteConfList(version):
    enable_conf = getDstEnablePHP(version)
    if os.path.exists(enable_conf):
        os.remove(enable_conf)

def phpPrependFile(version):
    # 放置在公共目录 /www/server/php 目录下以免疫 open_basedir 跨站拦截限制
    target_dir = yf.getServerDir() + '/php'
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
    app_start = target_dir + '/app_start_apt.php'
    if not os.path.exists(app_start):
        tpl = getPluginDir() + '/conf/app_start.php'
        content = yf.readFile(tpl)
        content = contentReplace(content, version)
        yf.writeFile(app_start, content)

def phpFpmReplace(version):
    desc_php_fpm = getServerDir() + '/' + version + '/fpm/php-fpm.conf'

    tpl_php_fpm = getPluginDir() + '/conf/php-fpm.conf'
    content = yf.readFile(tpl_php_fpm)
    if not content:
        content = """[global]
pid = /run/php/php{$PHP_VERSION}-fpm.pid
error_log = /var/log/php{$PHP_VERSION}-fpm.log
log_level = notice
systemd_interval = 10
process_control_timeout = 10s
emergency_restart_threshold = 10
emergency_restart_interval = 1m
include=/etc/php/{$PHP_VERSION}/fpm/pool.d/*.conf
"""
    content = contentReplace(content, version)
    yf.writeFile(desc_php_fpm, content)
    return True


def initReplace(version):
    makeOpConf(version)
    phpFpmWwwReplace(version)
    ensureSystemdOverride(version)

    install_ok = getAppDir() + "/" + version + "/install.ok"
    if not os.path.exists(install_ok):
        phpFpmReplace(version)
    else:
        # 即使已安装，也校验 php-fpm.conf 完整性（防止被截断或被 APT 升级覆盖）
        fpm_conf = getServerDir() + '/' + version + '/fpm/php-fpm.conf'
        if os.path.exists(fpm_conf):
            fpm_content = yf.readFile(fpm_conf)
            if not fpm_content or 'include=' not in fpm_content:
                phpFpmReplace(version)

        phpini = getConf(version)
        ssl_crt = yf.getSslCrt()

        if os.path.exists(phpini):
            content = yf.readFile(phpini)
            if content:
                # 替换 ;openssl.cafile= 为 openssl.cafile=ssl_crt，支持可选空格
                content = re.sub(r';\s*openssl\.cafile\s*=\s*', 'openssl.cafile=' + ssl_crt, content)
                # 替换 ;curl.cainfo = 为 curl.cainfo=ssl_crt，支持可选空格
                content = re.sub(r';\s*curl\.cainfo\s*=\s*', 'curl.cainfo=' + ssl_crt, content)
                
                # 优化 php.ini 默认值
                configs_to_set = {
                    'post_max_size': '50M',
                    'upload_max_filesize': '50M',
                    'date.timezone': 'PRC',
                    'short_open_tag': 'On',
                    # cgi.fix_pathinfo 默认值保留 1（P2-16 复评结论，勿随手改 0）：
                    # 站点 vhost（web/misc/nginx/tpl/nginx.conf）引用的
                    # conf/enable-php-<NN>.conf 里，`location ~ [^/]\.php(/|$)` 首行
                    # 就是 `try_files $uri =404` —— 不存在的 .php 路径在 nginx 层
                    # 直接 404，FPM 收不到「不存在的 SCRIPT_FILENAME」⇒
                    # fix_pathinfo 的「向上回退找已存在文件」不会触发。
                    'cgi.fix_pathinfo': '1',
                    'max_execution_time': '300',
                    'display_errors': 'Off',
                    'log_errors': 'On',
                    'expose_php': 'Off',
                    'session.cookie_httponly': 'On',
                    'disable_functions': 'passthru,exec,system,chroot,chgrp,chown,shell_exec,popen,proc_open,pcntl_exec,ini_alter,ini_restore,dl,openlog,syslog,readlink,symlink,popepassthru,pcntl_alarm,pcntl_fork,pcntl_waitpid,pcntl_wait,pcntl_wifexited,pcntl_wifstopped,pcntl_wifsignaled,pcntl_wifcontinued,pcntl_wexitstatus,pcntl_wtermsig,pcntl_wstopsig,pcntl_signal,pcntl_signal_dispatch,pcntl_get_last_error,pcntl_strerror,pcntl_sigprocmask,pcntl_sigwaitinfo,pcntl_sigtimedwait,pcntl_exec,pcntl_getpriority,pcntl_setpriority,imap_open,apache_setenv',
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

                yf.writeFile(phpini, content)

        yf.writeFile(install_ok, 'ok')

    phpPrependFile(version)
    return 'ok'



def tunePhpConfig(version):
    err, version = versionOrError(version)
    if err:
        return err
    php_dir = getServerDir()
    ini_file = php_dir + '/' + version + '/fpm/php.ini'
    if not os.path.exists(ini_file):
        return yf.returnJson(False, '该版本的 PHP 配置文件不存在！')

    content = yf.readFile(ini_file)
    if not content or isinstance(content, bool):
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

    # 替换已有 php-fpm.conf 中的旧引导文件路径，保证存量版本自愈
    fpm_file = php_dir + '/' + version + '/fpm/php-fpm.conf'
    if os.path.exists(fpm_file):
        fpm_content = yf.readFile(fpm_file)
        if fpm_content:
            fpm_content = fpm_content.replace('/php-apt/app_start.php', '/php/app_start_apt.php')
            yf.writeFile(fpm_file, fpm_content)

    phpPrependFile(version)
    
    service_name = "php" + version + "-fpm"
    yf.execShell("systemctl restart " + service_name)
    return yf.returnJson(True, '成功对 PHP-' + version + ' 配置执行一键调优！')


def tuneAllPhpConfig():
    php_dir = getServerDir()
    if not os.path.exists(php_dir):
        return yf.returnJson(False, '/etc/php 目录不存在！')

    versions = []
    for item in os.listdir(php_dir):
        full_path = os.path.join(php_dir, item)
        if os.path.isdir(full_path):
            if re.match(r'^\d+\.\d+$', item):
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
    version = formatVersion(version)
    err = versionOrFail(version)
    if err:
        return err
    if method in ['start', 'restart']:
        initReplace(version)

    if yf.isAppleSystem():
        return 'fail'

    service_name = 'php' + version + '-fpm'

    # 1. 确保系统 run 目录健全
    run_php = '/run/php'
    if not os.path.exists(run_php):
        yf.makeDirs(run_php)
    if not yf.isAppleSystem() and not yf.getOs().startswith('freebsd'):
        yf.execShell(f'chown -R www-data:www-data {run_php} 2>/dev/null || chown -R www:www {run_php} 2>/dev/null')
        yf.execShell(f'chmod 755 {run_php}')

    if method in ['stop', 'restart']:
        yf.execShell(f'systemctl stop {service_name} 2>/dev/null')
        if method == 'restart':
            time.sleep(0.5)

    if method in ['start', 'restart']:
        # 2. 清理残留孤儿 socket（仅在无活动 master 进程时清理）
        sock_file = getFpmAddress(version)
        if isinstance(sock_file, str) and os.path.exists(sock_file):
            chk_m = yf.execShell(f"ps aux | grep 'php-fpm: master process' | grep -E '(/etc/php/{version}/|\\({version}\\)|php-fpm{version})' | grep -v grep")
            if not chk_m[0].strip():
                try:
                    os.remove(sock_file)
                except Exception:
                    yf.execShell(f'rm -f {yf.shlexQuote(sock_file)}')

        # 3. 清理无效僵尸 PID 文件
        pid_file = '/run/php/php' + version + '-fpm.pid'
        if os.path.exists(pid_file):
            try:
                pid_str = yf.readFile(pid_file).strip()
                if pid_str and pid_str.isdigit():
                    pid = int(pid_str)
                    try:
                        os.kill(pid, 0)
                    except OSError:
                        os.remove(pid_file)
            except Exception as _e:
                _log.debug('[php-apt] phpOp 异常已忽略: %s', _e)

        # 4. 重置 systemd 失败状态
        yf.execShell(f'systemctl reset-failed {service_name} 2>/dev/null')

        # 5. 拉起服务并平滑探活（最多 3 秒）
        res = yf.execShell(f'systemctl {method} {service_name}')
        for _ in range(6):
            time.sleep(0.5)
            if status(version) == 'start':
                return 'ok'

        # 降级尝试 service 命令拉起
        yf.execShell(f'service {service_name} {method} 2>/dev/null')
        for _ in range(6):
            time.sleep(0.5)
            if status(version) == 'start':
                return 'ok'


        # 收集诊断日志
        err_msg = res[1].strip() if res and len(res) > 1 and res[1] else ''
        fpm_log_path = f'/var/log/php{version}-fpm.log'
        if os.path.exists(fpm_log_path):
            log_tail = yf.execShell(f'tail -n 6 {fpm_log_path}')[0].strip()
            if log_tail:
                err_msg = f"{err_msg}\n[php-fpm.log]:\n{log_tail}".strip()
        if not err_msg:
            err_msg = f"PHP-{version} (APT) 启动失败，请检查配置或点击【自愈修复】！"
        return err_msg

    elif method == 'stop':
        time.sleep(0.3)
        if status(version) == 'stop':
            return 'ok'
        yf.execShell(f'systemctl stop {service_name} 2>/dev/null')
        return 'ok'
    elif method == 'reload':
        data = yf.execShell(f'systemctl reload {service_name}')
        return 'ok' if data[1] == '' else data[1]

    data = yf.execShell(f'systemctl {method} {service_name}')
    return 'ok' if data[1] == '' else data[1]


def start(version):
    return phpOp(version, 'start')


def stop(version):
    status_res = phpOp(version, 'stop')
    deleteConfList(version)
    return status_res


def restart(version):
    return phpOp(version, 'restart')


def reload(version):
    return phpOp(version, 'reload')


def killAllPhp(version):
    yf.execShell('pkill -9 -f php-fpm')
    return 'ok'


# ---------------------------------------------------------------------------------
# P0-2：升级到安全基线（apt 渠道）
#
# 口径与编译版不同：
#   * 读数读**包版本串**（dpkg-query），不只看 `php -v` —— sury / Debian 安全源会把
#     补丁回移到旧上游版本号（例：`8.2.29-1+deb12u3`），只看数字会把已修复的机器误判成危；
#   * 升级用 `apt-get install --only-upgrade`，不动无关包；
#   * **apt 不能像编译版那样整目录回退**，但可以钉回旧包版本（--allow-downgrades）。
#     自动回退失败时，把命令原样返回给 UI，不给「已回退」的假承诺。
# ---------------------------------------------------------------------------------
APT_UPGRADE_TIMEOUT = 900
#: 包索引刷新超时（`apt-get update`）。刷新失败不阻断升级（本地索引可能仍然可用），
#: 但必须写进日志 —— 「apt 退出码 0 但版本没变」最常见的原因就是索引是旧的。
APT_REFRESH_TIMEOUT = 300
#: 离线通道里 `apt-get -s`（模拟）的超时。模拟只读本地文件，正常 1 秒内结束。
APT_SIMULATE_TIMEOUT = 120

#: 「什么都没升」的判定：apt 在「已是最新/源里没有更新包」时会以 0 退出。
#:
#: 必须同时认英文与**中文**摘要：apt 的输出随 locale 变化（真机实测 zh_CN 下是
#: 「升级了 0 个软件包，新安装了 0 个软件包」），只匹配英文会漏判。
#: **真正的判据是语言无关的**：升级前后 dpkg 包版本串完全相同（`no_op`）。
#: 这个正则只用来决定报文措辞（「源里没有更新包」还是「升级没生效」）。
_NO_UPGRADE_RE = re.compile(
    r'0 upgraded,\s*0 newly installed'
    r'|Nothing to do'
    r'|升级了\s*0\s*个软件包'
    r'|已经是最新版本'
    r'|已是最新版本',
    re.I)


def _logLine(msg):
    """同时写插件日志和 stdout —— 面板任务日志读的是子进程 stdout。"""
    try:
        yf.writeFileLog(msg)
    except Exception as _e:
        _log.debug('[php-apt] writeFileLog 失败: %s', _e)
    try:
        print(msg)
        sys.stdout.flush()
    except Exception as _e:
        _log.debug('[php-apt] 回显失败: %s', _e)


def _firstSourceUrl():
    """从 apt 源配置里取第一个 http(s) 地址（报错原文里没有 URL 时用它做诊断对象）。"""
    paths = ['/etc/apt/sources.list']
    conf_dir = '/etc/apt/sources.list.d'
    try:
        names = sorted(os.listdir(conf_dir))
    except OSError:
        names = []
    paths += [os.path.join(conf_dir, n) for n in names
              if n.endswith('.list') or n.endswith('.sources')]
    for path in paths:
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as fp:
                for line in fp:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    for tok in line.replace('URIs:', ' ').split():
                        if tok.startswith('http://') or tok.startswith('https://'):
                            return tok
        except OSError:
            continue
    return ''


def _diagnoseSource(tail, branch=''):
    """`apt-get update` 失败 → 结构化诊断（类型/结论/处置）。永不抛异常。"""
    try:
        url = net_probe.extract_url(tail) or _firstSourceUrl()
        return net_probe.diagnose(url=url, text=tail, branch=branch)
    except Exception as ex:            # noqa: BLE001 —— 诊断失败不能拖垮升级流程
        _log.debug('[php-apt] 网络诊断异常: %s', ex)
        return {'kind': net_probe.KIND_UNKNOWN, 'blocked': False,
                'summary': '诊断不可用: %s' % ex, 'advice': '', 'url': '', 'host': ''}


def _refreshPackageIndex(branch=''):
    """刷新包索引，返回 (rc, 摘要, 诊断或 None)。失败只记录，不阻断（与 apt 自身一致）。

    失败时**必须**带上诊断：真机现场的报错是「证书校验失败（上网认证网关劫持）」，
    旧报文却让用户去「检查 sources.list 与 sury 源」，改一天也改不好。
    """
    try:
        from core import proc_stream
        # 边跑边回显：apt-get update 可能跑几分钟，捕获输出会让任务日志空白
        rc, tail, _to = proc_stream.run_streaming(['apt-get', 'update'],
                                                 timeout=APT_REFRESH_TIMEOUT, tail_lines=30)
    except Exception as ex:
        _log.debug('[php-apt] apt-get update 异常: %s', ex)
        diag = _diagnoseSource(str(ex), branch)
        _logLine('[php-apt] apt-get update 异常: %s；诊断：%s' % (ex, diag.get('summary')))
        return (-1, str(ex), diag)
    tail = ' '.join((tail or '').split())[-200:]
    # 注意：`apt-get update` 在所有源都因证书失败时**仍以 0 退出**（真机实证，
    # 面板记录的 refresh_rc 就是 0），所以不能只看 rc —— 输出里有网关/证书指纹就得诊断。
    suspicious = rc != 0 or net_probe.classify_text(tail) != net_probe.KIND_UNKNOWN
    if not suspicious:
        return (rc, tail, None)
    diag = _diagnoseSource(tail, branch)
    _logLine('[php-apt] apt-get update %s（rc=%s）: %s'
             % ('失败' if rc != 0 else '有错误', rc, tail))
    _logLine('[php-apt] 网络诊断：%s' % (diag.get('summary') or ''))
    if diag.get('advice'):
        _logLine('[php-apt] 处置建议：%s' % diag['advice'])
    return (rc, tail, diag)


def _queueUpgrade(ver, branch, floor):
    """把升级投递到面板任务队列；返回给前端的信封。"""
    try:
        import thisdb
        cmd = 'cd %s && %s %s upgrade_to_baseline %s' % (
            yf.shlexQuote(yf.getPanelDir()),
            yf.shlexQuote(sys.executable),
            yf.shlexQuote(os.path.abspath(__file__)),
            yf.shlexQuote(ver),
        )
        try:
            thisdb.removeFailedTaskByCmd(cmd)
        except Exception as ex:
            _log.debug('[php-apt] 清理历史失败任务失败（忽略）: %s', ex)
        added = thisdb.addTask(name='PHP%s 升级到安全基线 %s' % (ver, floor), cmd=cmd, status=0)
        yf.triggerTask()
    except Exception as ex:
        return yf.returnJson(False, '投递升级任务失败: %s' % ex)
    if not added:
        return yf.returnJson(True, '该升级任务已在队列中（排队或执行中），请在消息盒子查看进度')
    return yf.returnJson(True, '已提交升级任务（基线 %s），请在消息盒子查看进度' % floor)


def submitBaselineUpgrade(version=''):
    """前端入口：只做前置判定 + 投递任务（apt 升级可能跑几分钟，不能在请求里等）。"""
    err, ver = versionOrError(version)
    if err:
        return err
    branch = ver.replace('.', '')
    floor = php_sec_baseline.branch_floor(branch)
    if not floor:
        return yf.returnJson(False, 'PHP%s 没有安全基线，不支持一键升级' % ver)

    before_pkg = php_sec_scan.read_package_version('apt', branch)
    if not before_pkg:
        return missingPackageEnvelope(ver)
    before, _raw = php_sec_baseline.parse_package_version(before_pkg)
    if php_sec_baseline.has_backport_marker('apt', before_pkg):
        return yf.returnJson(True, 'PHP%s 的 apt 包 %s 已带渠道回移补丁标记，无需升级'
                             % (ver, before_pkg))
    if php_sec_baseline.version_ge(before, floor):
        return yf.returnJson(True, 'PHP%s 已达标（%s ≥ 基线 %s），无需升级' % (ver, before, floor))
    return _queueUpgrade(ver, branch, floor)


def _simulate_argv(repo_args, pkgs):
    """`apt-get -s install --only-upgrade <pkgs>`（只读模拟，不动系统）。"""
    return (['env', 'LC_ALL=C', 'LANG=C', 'apt-get'] + list(repo_args) +
            ['-s', 'install', '--only-upgrade'] + list(pkgs))


def _offlineUpgrade(ver, branch, floor, before_pkg, reason='', report_invalid=False):
    """离线 .deb 通道：自建本地 apt 仓库 → `apt-get -s` 预演 → 真跑 → 回读断言。

    返回信封（成功/失败都返回），**None 表示没有可用离线包**（调用方继续走在线通道）。
    为什么不是 `dpkg -i`：sury 的扩展包全部钉死 `php8.4-common (= 精确版本)`，
    少一个包就会把系统解包到一半再失败（PHP 直接起不来）；apt 会先求解，
    卸载任何东西或求不出解就在**未动文件**的前提下中止。
    """
    try:
        data_dir = yf.getPanelDataDir()
    except Exception as ex:            # noqa: BLE001
        _log.debug('[php-apt] 取 data 目录失败: %s', ex)
        return None
    bundle = php_deb_bundle.offline_bundle(data_dir, branch, floor)
    if not bundle['entries']:
        _logLine('[php-apt] 离线包通道不可用：%s' % bundle['text'])
        return None
    if not bundle['ok']:
        _logLine('[php-apt] 离线包预检未通过：%s' % bundle['text'])
        if not report_invalid:
            # 预检不过不等于升级无望：本地索引可能还能用，先让在线通道试一把
            return None
        why = ('（在线通道原因：%s）' % reason) if reason else ''
        # 模板必须写成**一整条字面量**：i18n 门禁按字面量去语言包里找键，
        # 相邻字符串拼接会让它只看到前半截（变成「漏翻」且语言包里的键成了死键）。
        return yf.returnJson(
            False,
            '离线包预检未通过：%s；处置：把 PHP%s 该分支完整的 .deb（包括已装扩展包的新版本）放进 %s 后重试%s'
            % (bundle['text'], ver, '、'.join(bundle['dirs']), why),
            {'offline': True, 'problems': bundle['problems'], 'refresh_rc': -1})

    _logLine('[php-apt] 离线包通道就绪：%s' % bundle['text'])
    tmp_root = tempfile.mkdtemp(prefix='yf_php_deb_')
    try:
        repo = php_deb_bundle.build_repo(bundle['entries'], os.path.join(tmp_root, 'repo'))
        if not repo['ok']:
            return yf.returnJson(False, '离线包仓库构建失败：%s' % repo['text'],
                                 {'offline': True})
        os.chmod(tmp_root, 0o755)   # 让 apt 的 _apt 用户能读（否则日志里会刷权限警告）
        repo_dir = os.path.dirname(repo['packages'])
        try:
            os.chmod(repo_dir, 0o755)
        except OSError as _e:
            _log.debug('[php-apt] chmod 离线仓库目录失败（不影响升级）: %s', _e)
        repo_args = php_deb_bundle.apt_repo_args(repo_dir)
        from core import proc_stream
        env = dict(os.environ)
        # 系统输出解析必须钉死 locale（中文 locale 下 apt 摘要全是中文，判据会失效）
        env['LC_ALL'] = 'C'
        env['LANG'] = 'C'
        rc, tail, _to = proc_stream.run_streaming(
            ['apt-get'] + repo_args + ['update'],
            timeout=APT_REFRESH_TIMEOUT, tail_lines=10, env=env)
        if rc != 0:
            return yf.returnJson(False, '离线仓库刷新失败（rc=%s）：%s' % (rc, tail),
                                 {'offline': True, 'rc': rc})
        pkgs = php_sec_baseline.apt_package_names(branch)
        # 传**函数调用**而不是裸变量：仓库的 shell 拼接棘轮把「首参是裸变量」
        #（静态看不到构造过程）一律登记为新债。
        _sim_rc, sim_out, sim_err = yf.execShellRc(
            _simulate_argv(repo_args, pkgs), shell=False, timeout=APT_SIMULATE_TIMEOUT)
        parsed = php_deb_bundle.parse_simulation((sim_out or '') + (sim_err or ''))
        can_run, why = php_deb_bundle.judge_simulation(parsed)
        _logLine('[php-apt] 离线升级预演：%s' % why)
        if not can_run:
            return yf.returnJson(False, '离线升级未执行：%s' % why,
                                 {'offline': True, 'simulation': parsed})
        # 升级前先报一句「要动谁」，任务日志里能对上（卸载/新增一目了然）
        yf.writeLog('PHP安全升级', 'PHP%s(apt) 离线包升级：%s' % (ver, why))
        rc, tail, _to = proc_stream.run_streaming(
            ['apt-get'] + repo_args +
            ['-o', 'Dpkg::Options::=--force-confdef',
             '-o', 'Dpkg::Options::=--force-confold',
             'install', '-y', '--only-upgrade'] + pkgs,
            timeout=APT_UPGRADE_TIMEOUT, tail_lines=40, env=env)
        after_pkg = php_sec_scan.read_package_version('apt', branch)
        after, _raw = php_sec_baseline.parse_package_version(after_pkg)
        before, _raw0 = php_sec_baseline.parse_package_version(before_pkg)
        verdict = php_sec_baseline.verify_upgrade(
            branch, before, after,
            backport=php_sec_baseline.has_backport_marker('apt', after_pkg))
        if verdict['ok']:
            try:
                restart(ver)
            except Exception as _e:
                _log.debug('[php-apt] 离线升级后重启 PHP%s-FPM 异常: %s', ver, _e)
            dropPhpSecSnapshot()
            text = '%s（离线包通道）' % verdict['text']
            yf.writeLog('PHP安全升级', 'PHP%s(apt) %s' % (ver, text))
            return yf.returnJson(True, text, {'before': before_pkg, 'after': after_pkg,
                                              'rc': rc, 'offline': True, 'log_tail': tail})
        try:
            restart(ver)
        except Exception as _e:
            _log.debug('[php-apt] 离线升级失败后重启 PHP%s-FPM 异常: %s', ver, _e)
        dropPhpSecSnapshot()
        msg = ('离线包升级失败: %s（apt 退出码 %s）；离线通道没有旧版 .deb，无法自动回退，'
               '如 PHP 已不可用，请把旧版本 .deb 放进同一目录后再升级一次' % (verdict['text'], rc))
        yf.writeLog('PHP安全升级', 'PHP%s(apt) %s' % (ver, msg))
        return yf.returnJson(False, msg, {'before': before_pkg, 'after': after_pkg, 'rc': rc,
                                          'offline': True, 'log_tail': tail})
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def upgradeToBaseline(version=''):
    """任务队列入口：刷新索引 → （必要时走离线包）→ apt 升级 → 回读断言 → 失败钉回旧版本。"""
    err, ver = versionOrError(version)
    if err:
        return err
    branch = ver.replace('.', '')
    floor = php_sec_baseline.branch_floor(branch)
    if not floor:
        return yf.returnJson(False, 'PHP%s 没有安全基线，不支持一键升级' % ver)

    before_pkg = php_sec_scan.read_package_version('apt', branch)
    if not before_pkg:
        return missingPackageEnvelope(ver)
    before, _raw = php_sec_baseline.parse_package_version(before_pkg)
    if php_sec_baseline.has_backport_marker('apt', before_pkg):
        return yf.returnJson(True, 'PHP%s 的 apt 包 %s 已带渠道回移补丁标记，无需升级'
                             % (ver, before_pkg))
    if php_sec_baseline.version_ge(before, floor):
        return yf.returnJson(True, 'PHP%s 已达标（%s ≥ 基线 %s），无需升级' % (ver, before, floor))

    yf.writeLog('PHP安全升级', 'PHP%s(apt) 升级开始：%s → 基线 %s' % (ver, before_pkg, floor))
    upd_rc, upd_tail, diag = _refreshPackageIndex(branch)
    diag = diag or {}
    diag_text = ('；网络诊断：%s' % diag['summary']) if diag.get('summary') else ''
    # 索引刷不下来且是「网络出口不通（认证网关/证书挟持/超时）」⇒ 在线通道注定失败，
    # 直接试离线包；一个包也没扫到才回落到在线通道（保持旧行为：刷新失败不阻断）。
    if upd_rc != 0 and diag.get('blocked'):
        _logLine('[php-apt] 在线通道不可用，尝试离线 .deb 通道（实时证据：%s）'
                 % (diag.get('summary') or 'apt-get update 失败'))
        env = _offlineUpgrade(ver, branch, floor, before_pkg,
                              reason=diag.get('summary') or upd_tail)
        if env is not None:
            return env
    from core import proc_stream
    # 边跑边回显：apt 升级可能跑几分钟，把输出捕获住会让任务日志空白（看着像卡死）
    rc, tail, _to = proc_stream.run_streaming(
        php_sec_baseline.build_apt_upgrade_argv(branch),
        timeout=APT_UPGRADE_TIMEOUT, tail_lines=30)
    combined = tail or ''

    after_pkg = php_sec_scan.read_package_version('apt', branch)
    after, _raw2 = php_sec_baseline.parse_package_version(after_pkg)
    # 语言无关的判据：升级前后 dpkg 包版本串完全相同 ⇒ 确实什么都没升
    no_op = bool(before_pkg) and bool(after_pkg) and before_pkg == after_pkg
    said_no_upgrade = bool(_NO_UPGRADE_RE.search(combined))
    verdict = php_sec_baseline.verify_upgrade(
        branch, before, after,
        backport=php_sec_baseline.has_backport_marker('apt', after_pkg))

    if verdict['ok']:
        try:
            restart(ver)
        except Exception as _e:
            _log.debug('[php-apt] 升级后重启 PHP%s-FPM 异常: %s', ver, _e)
        dropPhpSecSnapshot()
        yf.writeLog('PHP安全升级', 'PHP%s(apt) %s' % (ver, verdict['text']))
        return yf.returnJson(True, verdict['text'], {'before': before_pkg, 'after': after_pkg,
                                                     'rc': rc, 'log_tail': tail})

    # 失败：**先试离线包通道**（在线源里没有新版本时，离线包往往才是唯一出路）
    env = _offlineUpgrade(ver, branch, floor, before_pkg,
                          reason=diag.get('summary') or '', report_invalid=True)
    if env is not None:
        return env

    # 只有「包真的换了」才需要钉回旧版；no_op 时回退是空操作，旧实现照样报
    # 「自动回退成功」，等于给用户假的安心（真机现场就是这么误导的）。
    rollback_argv = []
    rb_rc = -1
    if not no_op:
        rollback_argv = php_sec_baseline.build_apt_rollback_argv(branch, before_pkg)
        if rollback_argv:
            rb_rc, _rb_out, _rb_err = yf.execShellRc(list(rollback_argv), shell=False,
                                                    timeout=APT_UPGRADE_TIMEOUT)
    try:
        restart(ver)
    except Exception as _e:
        _log.debug('[php-apt] 升级失败后重启 PHP%s-FPM 异常: %s', ver, _e)
    dropPhpSecSnapshot()
    extra = ''
    if no_op:
        extra = ('；apt %s（前后包版本串相同：%s），本次未做任何改动'
                 % ('明确报告无可用更新' if said_no_upgrade else '没有升级任何包', before_pkg))
    if diag.get('advice'):
        extra += '；处置：%s' % diag['advice']
    tail_msg = ''
    if rollback_argv:
        tail_msg = '；已尝试回退（%s）：%s\n手工回退：%s' % (
            '成功' if rb_rc == 0 else '未成功，apt 不保证旧版本仍在源内',
            before_pkg, ' '.join(rollback_argv))
    msg = '升级失败: %s（apt 退出码 %s）%s%s%s' % (verdict['text'], rc, extra, diag_text,
                                            tail_msg)
    yf.writeLog('PHP安全升级', 'PHP%s(apt) 升级失败: %s' % (ver, msg))
    return yf.returnJson(False, msg, {'before': before_pkg, 'after': after_pkg, 'rc': rc,
                                      'refresh_rc': upd_rc, 'no_op': no_op,
                                      'diagnosis': diag, 'rollback_rc': rb_rc,
                                      'rollback_argv': rollback_argv, 'log_tail': tail})


def dropPhpSecSnapshot():
    """删掉巡检快照，让首页卡片的告警/结论在升级后立即重新计算。"""
    try:
        path = yf.getPanelDataDir() + '/' + php_sec_scan.SNAPSHOT_FILENAME
        if os.path.exists(path):
            os.remove(path)
    except Exception as _e:
        _log.debug('[php-apt] 清理安全巡检快照失败: %s', _e)


def upgradeSelfHealing(version=''):
    """
    全自动平滑无损升级与环境自愈接口（PHP-APT版）：
    1. 确保 /run/php 目录存在并校准权限；
    2. 清理无效僵死 PID 与孤儿 socket 死锁；
    3. 重置 systemd 失败锁定状态并重载；
    4. 探活已有存活进程，未运行则通过高可用拉起；
    5. 输出详细自愈诊断报告。
    """
    logs = []
    logs.append("开始执行 PHP-APT 插件平滑无损升级与全链路环境自愈流程...")

    if str(version).strip() and not isPhpVersion(version):
        return yf.returnJson(False, 'PHP版本参数不合法!')

    try:
        run_php = '/run/php'
        if not os.path.exists(run_php):
            yf.makeDirs(run_php)
        if not yf.isAppleSystem() and not yf.getOs().startswith('freebsd'):
            yf.execShell(f'chown -R www-data:www-data {run_php} 2>/dev/null || chown -R www:www {run_php} 2>/dev/null')
            yf.execShell(f'chmod 755 {run_php}')
        logs.append("/run/php 临时套接字与 PID 目录已校准健全。")
    except Exception as ex:
        logs.append(f"/run/php 目录校准异常: {ex}")

    target_versions = [formatVersion(version)] if version and str(version).strip() else getInstalledPhpVersions()
    if not target_versions:
        logs.append("未发现已安装的 PHP-APT 版本，完成基础环境自愈。")
        return yf.returnJson(True, "\n".join(logs), {'status': 'ok', 'versions': []})

    results = {}
    for ver in target_versions:
        logs.append(f"\n--- 正在对 PHP-{ver} (APT) 执行环境自愈 ---")
        service_name = f'php{ver}-fpm'

        try:
            initReplace(ver)
            # 清理 /etc/php/{ver}/fpm/php-fpm.conf 中非法的全局 php_value[auto_prepend_file] 指令
            fpm_main_conf = getFpmFile(ver)
            if os.path.exists(fpm_main_conf):
                fpm_txt = yf.readFile(fpm_main_conf)
                if fpm_txt and re.search(r'(?m)^\s*php_value\[auto_prepend_file\]', fpm_txt):
                    cleaned_fpm = re.sub(r'(?m)^\s*php_value\[auto_prepend_file\].*$', '', fpm_txt)
                    yf.writeFile(fpm_main_conf, cleaned_fpm)
                    logs.append(f"已清理 PHP-{ver} 主配置中非法的全局 php_value[auto_prepend_file] 指令。")
            logs.append(f"PHP-{ver} 配置模板与 Web 整合已同步刷新。")
        except Exception as ex:
            logs.append(f"PHP-{ver} 配置自愈异常: {ex}")

        try:
            yf.execShell(f'systemctl reset-failed {service_name} 2>/dev/null')
            yf.execShell('systemctl daemon-reload 2>/dev/null')
        except Exception as ex:
            logs.append(f"Systemd 状态重置异常: {ex}")

        try:
            sock_file = getFpmAddress(ver)
            pid_file = f'/run/php/php{ver}-fpm.pid'
            st = status(ver)
            if st != 'start':
                if isinstance(sock_file, str) and os.path.exists(sock_file):
                    chk_m = yf.execShell(f"ps aux | grep 'php-fpm: master process' | grep -E '(/etc/php/{ver}/|\\({ver}\\)|php-fpm{ver})' | grep -v grep")

                    if not chk_m[0].strip():
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

        cur_status = status(ver)
        if cur_status != 'start':
            logs.append(f"检测到 PHP-{ver} 未运行，正在尝试高可用拉起...")
            start_ret = start(ver)
            logs.append(f"拉起结果: {start_ret}")
        else:
            logs.append(f"PHP-{ver} 当前正在稳定运行中。")

        final_st = status(ver)
        results[ver] = final_st
        logs.append(f"PHP-{ver} 最终服务运行状态: {final_st}")

    is_all_ok = all(v == 'start' for v in results.values()) if results else True
    logs.append("\nPHP-APT 全链路平滑升级与环境自愈完成。")
    return yf.returnJson(is_all_ok, "\n".join(logs), {'results': results})


def _migrate_php_apt_1_to_2(version=''):
    """1.x 升级至 2.0 阶段单次自愈迁移"""
    return upgradeSelfHealing(version)


PHP_APT_MIGRATION_STEPS = [
    ('2.0', _migrate_php_apt_1_to_2),
]


def checkPluginUpgrade(version=''):
    global _PHP_APT_UPGRADE_CHECKING
    if str(version).strip() and not isPhpVersion(version):
        return yf.returnJson(False, 'PHP版本参数不合法!')
    if _PHP_APT_UPGRADE_CHECKING:
        return yf.returnJson(True, '升级自愈正在执行中...')

    ver_file = getPluginVersionFile()
    installed_ver = '1.0'
    if os.path.exists(ver_file):
        try:
            content = yf.readFile(ver_file).strip()
            if content:
                installed_ver = content
        except Exception:
            installed_ver = '1.0'

    if _compare_version(installed_ver, CURRENT_PLUGIN_VERSION) >= 0:
        return yf.returnJson(True, '已是最新版本，无需自愈。')

    _PHP_APT_UPGRADE_CHECKING = True
    try:
        for target_ver, mig_func in PHP_APT_MIGRATION_STEPS:
            if _compare_version(installed_ver, target_ver) < 0:
                mig_func(version)
        try:
            yf.writeFile(ver_file, CURRENT_PLUGIN_VERSION)
        except Exception as _e:
            _log.debug('[php-apt] checkPluginUpgrade 异常已忽略: %s', _e)
        return yf.returnJson(True, '大版本迁移升级自愈成功完成。')
    finally:
        _PHP_APT_UPGRADE_CHECKING = False


def initdStatus(version):
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    err = versionOrFail(version)
    if err:
        return err
    shell_cmd = 'systemctl status php' + version + \
        '-fpm | grep loaded | grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall(version):
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    err = versionOrFail(version)
    if err:
        return err
    yf.execShell('systemctl enable php' + version + '-fpm')
    return 'ok'


def initdUinstall(version):
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    err = versionOrFail(version)
    if err:
        return err
    yf.execShell('systemctl disable php' + version + '-fpm')
    return 'ok'


def fpmLog(version):
    return '/var/log/php' + version + '-fpm.log'


def fpmSlowLog(version):
    return '/var/log/fpm-php' + version + '.www.slow.log'


def getPhpConf(version):
    err, version = versionOrError(version)
    if err:
        return err
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
        {'name': 'cgi.fix_pathinfo', 'type': 0, 'ps': '是否开启pathinfo（本机 nginx 模板已用 try_files 拦截不存在的 .php 路径，开启是安全的）'},
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
        # cgi.fix_pathinfo 默认 1：安全性依赖 nginx 模板的 try_files 防护，
        # 详见 makePhpIni() 内同名注释（php/php-apt/php-yum 三渠道一致）。
        'cgi.fix_pathinfo': '1',
        'date.timezone': 'PRC'
    }
    ini_path = getConf(version)
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
        return yf.returnJson(False, '参数格式错误!')
    filename = getConf(version)
    phpini = yf.readFile(filename)
    if not phpini or isinstance(phpini, bool):
        phpini = ''
    for g in gets:
        if g in args:
            verr, vval = validateIniValue(g, args[g])
            if verr:
                return yf.returnJson(False, verr)
            phpini = setIniKey(phpini, g, vval)
    yf.writeFile(filename, phpini)
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
        # cgi.fix_pathinfo 默认 1：安全性依赖 nginx 模板的 try_files 防护，
        # 详见 makePhpIni() 内同名注释（php/php-apt/php-yum 三渠道一致）。
        'cgi.fix_pathinfo': '1',
        'date.timezone': 'PRC'
    }
    filename = getConf(version)
    phpini = yf.readFile(filename) if os.path.exists(filename) else ''
    if not phpini or isinstance(phpini, bool):
        phpini = ''
    for k, v in defaults_map.items():
        phpini = setIniKey(phpini, k, v)
    yf.writeFile(filename, phpini)
    reload(version)
    return yf.returnJson(True, '配置已成功还原为默认值')


def getLimitConf(version):
    err, version = versionOrError(version)
    if err:
        return err
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
    args = getArgs()
    data = checkArgs(args, ['time'])
    if not data[0]:
        return data[1]

    time_val = str(args['time']).strip()
    if not time_val.isdigit():
        return yf.returnJson(False, '时间参数不合法!')
    if int(time_val) < 30 or int(time_val) > 86400:
        return yf.returnJson(False, '请填写30-86400间的值!')

    filefpm = getFpmConfFile(version)
    conf = yf.readFile(filefpm)
    if not conf or isinstance(conf, bool):
        conf = ''
    rep = r"request_terminate_timeout\s*=\s*([0-9]+)\r?\n"
    if re.search(rep, conf):
        conf = re.sub(rep, "request_terminate_timeout = " + time_val + "\n", conf)
    else:
        conf = conf.rstrip('\n') + "\nrequest_terminate_timeout = " + time_val + "\n"
    yf.writeFile(filefpm, conf)

    fileini = getConf(version)
    phpini = yf.readFile(fileini)
    if not phpini or isinstance(phpini, bool):
        phpini = ''
    phpini = setIniKey(phpini, 'max_execution_time', time_val)
    phpini = setIniKey(phpini, 'max_input_time', time_val)
    yf.writeFile(fileini, phpini)
    return yf.returnJson(True, '设置成功!')


def setMaxSize(version):
    err, version = versionOrError(version)
    if err:
        return err
    args = getArgs()
    data = checkArgs(args, ['max'])
    if not data[0]:
        return data[1]

    maxVal = str(args['max']).strip()
    if not maxVal.isdigit() or int(maxVal) > 102400:
        return yf.returnJson(False, '上传大小参数不合法!')
    if int(maxVal) < 2:
        return yf.returnJson(False, '上传大小限制不能小于2MB!')

    path = getConf(version)
    conf = yf.readFile(path)
    if not conf or isinstance(conf, bool):
        conf = ''
    conf = setIniKey(conf, 'upload_max_filesize', maxVal + 'M')
    conf = setIniKey(conf, 'post_max_size', maxVal + 'M')
    yf.writeFile(path, conf)

    msg = yf.getInfo('设置PHP-{1}最大上传大小为[{2}MB]!', (version, maxVal,))
    yf.writeLog('插件管理[PHP]', msg)
    return yf.returnJson(True, '设置成功!')


def getFpmConfig(version):
    err, version = versionOrError(version)
    if err:
        return err
    filefpm = getFpmConfFile(version)
    if not os.path.exists(filefpm):
        phpFpmWwwReplace(version)
    conf = yf.readFile(filefpm)
    if not conf:
        conf = ""
    data = {}

    rep = r"(?m)^\s*pm\.max_children\s*=\s*([0-9]+)"
    m = re.search(rep, conf)
    data['max_children'] = m.group(1) if m else '30'

    rep = r"(?m)^\s*pm\.start_servers\s*=\s*([0-9]+)"
    m = re.search(rep, conf)
    data['start_servers'] = m.group(1) if m else '5'

    rep = r"(?m)^\s*pm\.min_spare_servers\s*=\s*([0-9]+)"
    m = re.search(rep, conf)
    data['min_spare_servers'] = m.group(1) if m else '5'

    rep = r"(?m)^\s*pm\.max_spare_servers\s*=\s*([0-9]+)"
    m = re.search(rep, conf)
    data['max_spare_servers'] = m.group(1) if m else '10'

    rep = r"(?m)^\s*pm\s*=\s*(\w+)"
    m = re.search(rep, conf)
    data['pm'] = m.group(1) if m else 'dynamic'
    return yf.getJson(data)


def setFpmConfig(version):
    err, version = versionOrError(version)
    if err:
        return err
    args = getArgs()
    if not isinstance(args, dict):
        return yf.returnJson(False, '参数格式错误!')
    max_children = str(args.get('max_children', '30')).strip()
    start_servers = str(args.get('start_servers', '5')).strip()
    min_spare_servers = str(args.get('min_spare_servers', '5')).strip()
    max_spare_servers = str(args.get('max_spare_servers', '10')).strip()
    pm = str(args.get('pm', 'dynamic')).strip()

    for val in (max_children, start_servers, min_spare_servers, max_spare_servers):
        if not val.isdigit() or int(val) < 1 or int(val) > 100000:
            return yf.returnJson(False, '并发参数不合法!')
    if pm not in PHP_PM_MODES:
        return yf.returnJson(False, '运行模式不合法!')
    if int(start_servers) > int(max_children) or int(min_spare_servers) > int(max_spare_servers) \
            or int(max_spare_servers) > int(max_children):
        return yf.returnJson(False, '并发参数不合法!')

    filefpm = getFpmConfFile(version)
    if not os.path.exists(filefpm):
        phpFpmWwwReplace(version)
    conf = yf.readFile(filefpm)
    if not conf:
        conf = ""

    def update_or_append(content, key, val):
        pat = rf'(?m)^\s*;?\s*{re.escape(key)}\s*=.*$'
        repl = f'{key} = {val}'
        if re.search(pat, content):
            return re.sub(pat, repl, content)
        return content.rstrip() + f'\n{repl}\n'

    conf = update_or_append(conf, 'pm.max_children', max_children)
    conf = update_or_append(conf, 'pm.start_servers', start_servers)
    conf = update_or_append(conf, 'pm.min_spare_servers', min_spare_servers)
    conf = update_or_append(conf, 'pm.max_spare_servers', max_spare_servers)
    conf = update_or_append(conf, 'pm', pm)

    yf.writeFile(filefpm, conf)
    reload(version)

    msg = yf.getInfo('设置PHP-{1}并发设置,max_children={2},start_servers={3},min_spare_servers={4},max_spare_servers={5}',
                     (version, max_children, start_servers, min_spare_servers, max_spare_servers,))
    yf.writeLog('插件管理[PHP-APT]', msg)
    return yf.returnJson(True, '设置成功!')


def getFpmAddress(version):
    fpm_address = '/run/php/php{}-fpm.sock'.format(version)
    php_fpm_file = getFpmConfFile(version)
    try:
        content = yf.readFile(php_fpm_file)
        if not content:
            return fpm_address
        tmp = re.findall(r"^(?!\s*;)\s*listen\s*=\s*(.+)", content, re.M)
        if not tmp:
            return fpm_address
        raw_listen = tmp[0].strip()
        if 'sock' in raw_listen:
            return raw_listen
        if ':' in raw_listen:
            listen_tmp = raw_listen.split(':')
            ip = listen_tmp[0].strip()
            port = int(listen_tmp[1].strip())
            fpm_address = (ip if ip else '127.0.0.1', port)
        elif raw_listen.isdigit():
            fpm_address = ('127.0.0.1', int(raw_listen))
        return fpm_address
    except Exception as _e:
        _log.debug('[php-apt] getFpmAddress 异常已忽略: %s', _e)
        return fpm_address


def getFpmStatus(version):
    err, version = versionOrError(version)
    if err:
        return err
    stat = status(version)
    if stat == 'stop':
        return yf.returnJson(False, 'PHP[' + version + ']未启动!!!')

    sock_file = getFpmAddress(version)
    try:
        sock_data = yf.requestFcgiPHP(sock_file, '/phpfpm_status_apt' + version + '?json')

        result = str(sock_data, encoding='utf-8')
        try:
            data = json.loads(result)
        except Exception as e:
            return yf.returnJson(False, '获取状态失败, 返回内容异常: ' + result)
        fTime = time.localtime(int(data['start time']))
        data['start time'] = time.strftime('%Y-%m-%d %H:%M:%S', fTime)
    except Exception as e:
        return yf.returnJson(False, str(e))

    return yf.returnJson(True, "OK", data)


def getSessionConf(version):
    err, version = versionOrError(version)
    if err:
        return err
    filename = getConf(version)
    if not os.path.exists(filename):
        return yf.returnJson(True, 'ok', {"save_handler": "files", "save_path": "", "passwd": "", "port": ""})

    phpini = yf.readFile(filename)
    if not phpini:
        phpini = ""

    rep = r'(?m)^\s*session\.save_handler\s*=\s*([0-9A-Za-z_& ~]+)'
    m_handler = re.search(rep, phpini)
    save_handler = m_handler.group(1).strip() if m_handler else "files"

    reppath = r'(?m)^\s*session\.save_path\s*=\s*"tcp\:\/\/([\d\.]+):(\d+)'
    memcached = r'(?m)^\s*session\.save_path\s*=\s*"([\d\.]+):(\d+)"'
    passrep = r'(?m)^\s*session\.save_path\s*=\s*"tcp://[^=]+=(.*)"'

    m_path = re.search(reppath, phpini)
    if not m_path:
        m_path = re.search(memcached, phpini)

    m_pass = re.search(passrep, phpini)
    passwd = m_pass.group(1).strip() if m_pass else ""

    save_path = ""
    port = ""
    if m_path:
        try:
            save_path = m_path.group(1).strip()
            port = m_path.group(2).strip()
        except Exception as _e:
            _log.debug('[php-apt] getSessionConf 异常已忽略: %s', _e)

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
    port = args['port']
    passwd = str(args['passwd'])
    save_handler = str(args['save_handler']).strip()

    if save_handler not in PHP_SESSION_HANDLERS:
        return yf.returnJson(False, 'Session存储方式不合法!')

    if save_handler != "files":
        iprep = r"^(2(5[0-5]{1}|[0-4]\d{1})|[0-1]?\d{1,2})\.(2(5[0-5]{1}|[0-4]\d{1})|[0-1]?\d{1,2})\.(2(5[0-5]{1}|[0-4]\d{1})|[0-1]?\d{1,2})\.(2(5[0-5]{1}|[0-4]\d{1})|[0-1]?\d{1,2})$"
        if not re.search(iprep, ip):
            return yf.returnJson(False, '请输入正确的IP地址')

        try:
            port = int(port)
            if port >= 65535 or port < 1:
                return yf.returnJson(False, '请输入正确的端口号')
        except Exception as _e:
            _log.debug('[php-apt] setSessionConf 异常已忽略: %s', _e)
            return yf.returnJson(False, '请输入正确的端口号')
        prep = r"[\~\`\/\=\"\'\s]"
        if re.search(prep, passwd):
            return yf.returnJson(False, '请不要输入以下特殊字符: " ~ ` / = "')

    filename = getConf(version)
    if not os.path.exists(filename):
        return yf.returnJson(False, '指定PHP版本不存在!')
    phpini = yf.readFile(filename)
    if not phpini or isinstance(phpini, bool):
        phpini = ""

    session_tmp = getServerDir() + "/tmp/session"

    rep = r'session.save_handler\s*=\s*(.+)\r?\n'
    val = r'session.save_handler = ' + save_handler + '\n'
    phpini = re.sub(rep, val, phpini)

    content = yf.execShell(
        'cat /etc/php/' + version + '/fpm/conf.d/*' + " | grep -v '^;' |tr -s '\n'")
    content = content[0]

    if save_handler == "memcached":
        if not re.search("memcached.so", phpini):
            return yf.returnJson(False, '请先安装%s扩展' % save_handler)
        rep = r'\nsession.save_path\s*=\s*(.+)\r?\n'
        val = r'\nsession.save_path = "%s:%s" \n' % (ip, port)
        if re.search(rep, phpini):
            phpini = re.sub(rep, val, phpini)
        else:
            phpini = re.sub('\n;session.save_path = "' + "/var/lib/php/sessions" + '"',
                            '\n;session.save_path = "' + "/var/lib/php/sessions" + '"' + val, phpini)

    if save_handler == "memcache":
        if not content.find('memcache') > -1:
            return yf.returnJson(False, '请先安装%s扩展' % save_handler)
        rep = r'\nsession.save_path\s*=\s*(.+)\r?\n'
        val = r'\nsession.save_path = "%s:%s" \n' % (ip, port)
        if re.search(rep, phpini):
            phpini = re.sub(rep, val, phpini)
        else:
            phpini = re.sub('\n;session.save_path = "' + "/var/lib/php/sessions" + '"',
                            '\n;session.save_path = "' + "/var/lib/php/sessions" + '"' + val, phpini)

    if save_handler == "redis":
        if not content.find('redis') > -1:
            return yf.returnJson(False, '请先安装%s扩展' % save_handler)
        if passwd:
            passwd = "?auth=" + passwd
        else:
            passwd = ""
        rep = r'\nsession.save_path\s*=\s*(.+)\r?\n'
        val = r'\nsession.save_path = "tcp://%s:%s%s"\n' % (ip, port, passwd)
        res = re.search(rep, phpini)
        if res:
            phpini = re.sub(rep, val, phpini)
        else:
            phpini = re.sub('\n;session.save_path = "' + "/var/lib/php/sessions" + '"',
                            '\n;session.save_path = "' + "/var/lib/php/sessions" + '"' + val, phpini)

    if save_handler == "files":
        rep = r'\nsession.save_path\s*=\s*(.+)\r?\n'
        val = r'\nsession.save_path = "' + session_tmp + '"\n'
        if re.search(rep, phpini):
            phpini = re.sub(rep, val, phpini)
        else:
            phpini = re.sub('\n;session.save_path = "' + "/var/lib/php/sessions" + '"',
                            '\n;session.save_path = "' + "/var/lib/php/sessions" + '"' + val, phpini)

    yf.writeFile(filename, phpini)
    reload(version)
    return yf.returnJson(True, '设置成功!')


def _intShell(cmd):
    """把 shell 输出安全解析成 int（空/畸形输出回 0，不再 ValueError）。"""
    out = yf.execShell(cmd)
    raw = out[0] if out and out[0] else ''
    raw = raw.split('\n')[0].strip()
    return int(raw) if raw.isdigit() else 0


def getSessionCount_Origin(version):
    session_tmp = getServerDir() + "/tmp/session"
    d = ["/tmp", "/var/lib/php/sessions", session_tmp]
    count = 0
    for i in d:
        if not os.path.exists(i):
            yf.makeDirs(i)
        entries = os.listdir(i)
        for l in entries:
            if os.path.isdir(i + "/" + l):
                l1 = os.listdir(i + "/" + l)
                for ll in l1:
                    if "sess_" in ll:
                        count += 1
                continue
            if "sess_" in l:
                count += 1

    old_file = _intShell("find /tmp -mtime +1 -name 'sess_*' -type f | wc -l")
    old_file += _intShell("find " + yf.shlexQuote(session_tmp)
                          + " -mtime +1 -name 'sess_*' -type f | wc -l")
    return {"total": count, "oldfile": old_file}


def getSessionCount(version):
    err, version = versionOrError(version)
    if err:
        return err
    data = getSessionCount_Origin(version)
    return yf.returnJson(True, 'ok!', data)


def cleanSessionOld(version):
    err, version = versionOrError(version)
    if err:
        return err
    yf.execShell("find /tmp -mtime +1 -name 'sess_*' -type f -print0 | xargs -0 -r rm -f")

    session_tmp = getServerDir() + "/tmp/session"
    yf.execShell("find " + yf.shlexQuote(session_tmp)
                 + " -mtime +1 -name 'sess_*' -type f -print0 | xargs -0 -r rm -f")
    old_file_conf = getSessionCount_Origin(version)["oldfile"]
    if old_file_conf == 0:
        return yf.returnJson(True, '清理成功')
    else:
        return yf.returnJson(True, '清理失败')


def getDisableFunc(version):
    err, version = versionOrError(version)
    if err:
        return err
    filename = getConf(version)
    phpini = yf.readFile(filename) if os.path.exists(filename) else ''
    if not phpini or isinstance(phpini, bool):
        phpini = ''

    data = {}
    rep = r"(?m)^\s*;?\s*disable_functions\s*=\s*(.*)$"
    m = re.search(rep, phpini)
    if m and m.group(1).strip():
        data['disable_functions'] = m.group(1).strip()
    else:
        data['disable_functions'] = DEFAULT_DISABLE_FUNCTIONS
        if os.path.exists(filename):
            try:
                if m:
                    phpini = re.sub(rep, f'disable_functions = {DEFAULT_DISABLE_FUNCTIONS}', phpini)
                else:
                    phpini = phpini.rstrip() + f'\ndisable_functions = {DEFAULT_DISABLE_FUNCTIONS}\n'
                yf.writeFile(filename, phpini)
            except Exception as _e:
                _log.debug('[php-apt] getDisableFunc 异常已忽略: %s', _e)
    return yf.getJson(data)


def setDisableFunc(version):
    err, version = versionOrError(version)
    if err:
        return err
    filename = getConf(version)
    if not filename or not os.path.exists(filename):
        return yf.returnJson(False, '指定PHP版本不存在!')

    args = getArgs()
    disable_functions = str(args.get('disable_functions', '')).strip()
    if not PHP_FUNC_LIST_RE.match(disable_functions):
        return yf.returnJson(False, '禁用函数格式不合法!')

    phpini = yf.readFile(filename)
    if not phpini or isinstance(phpini, bool):
        phpini = ""

    phpini = setIniKey(phpini, 'disable_functions', disable_functions)

    msg = yf.getInfo('修改PHP-{1}的禁用函数为[{2}]', (version, disable_functions,))
    yf.writeLog('插件管理[PHP-APT]', msg)
    yf.writeFile(filename, phpini)
    reload(version)
    return yf.returnJson(True, '设置成功!')


def resetDisableFunc(version):
    err, version = versionOrError(version)
    if err:
        return err
    filename = getConf(version)
    if not filename or not os.path.exists(filename):
        return yf.returnJson(False, '指定PHP版本不存在!')
    phpini = yf.readFile(filename) if os.path.exists(filename) else ''
    if not phpini or isinstance(phpini, bool):
        phpini = ""
    phpini = setIniKey(phpini, 'disable_functions', DEFAULT_DISABLE_FUNCTIONS)
    yf.writeFile(filename, phpini)
    reload(version)
    return yf.returnJson(True, '已成功还原为默认禁用函数列表!')


def getPhpinfo(version):
    err = versionOrFail(version)
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
    sock_data = yf.requestFcgiPHP(sock_file, '/phpinfo.php', root_dir)
    yf.removeDir(root_dir)
    phpinfo = str(sock_data, encoding='utf-8')
    return phpinfo


def get_php_info(args):
    if not isinstance(args, dict):
        return 'ERROR: PHP版本参数不合法'
    inputVer = args.get('version', '')
    version = formatVersion(inputVer)
    return getPhpinfo(version)


def getLibConf(version):
    err, version = versionOrError(version)
    if err:
        return err
    fname = getConf(version)
    if not os.path.exists(fname):
        return yf.returnJson(False, '指定PHP版本不存在!')

    # phpini = yf.readFile(fname)
    content = yf.execShell('cat /etc/php/' + version + '/fpm/conf.d/*' + " | grep -v '^;' |tr -s '\n'")
    content = content[0]

    libpath = getPluginDir() + '/versions/phplib.conf'
    raw_lib = yf.readFile(libpath)
    if not raw_lib or isinstance(raw_lib, bool):
        return yf.returnJson(False, '扩展列表配置文件不存在!')
    try:
        phplib = json.loads(raw_lib)
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
                lib['phpversions'].append(tmp1[1].replace('.',''))
        if content.find(lib['check']) == -1:
            lib['status'] = False
        else:
            lib['status'] = True
        libs.append(lib)
    return yf.returnJson(True, 'OK!', libs)


def installLib(version):
    err, version = versionOrError(version)
    if err:
        return err
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']
    
    # 严格校验扩展名称，防范命令注入漏洞
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return yf.returnJson(False, '扩展名称包含非法字符！')

    cmd = "cd " + yf.shlexQuote(getPluginDir() + "/versions") + " && /bin/bash " \
        + yf.shlexQuote("common.sh") + " " + yf.shlexQuote(version) + ' install ' + yf.shlexQuote(name)
    install_name = '安装PHPAPT[' + name + '-' + version + ']'
    import thisdb
    thisdb.addTask(name=install_name,cmd=cmd)

    yf.triggerTask()
    return yf.returnJson(True, '已将下载任务添加到队列!')


def uninstallLib(version):
    err, version = versionOrError(version)
    if err:
        return err
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']

    # 严格校验扩展名称，防范命令注入漏洞
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return yf.returnJson(False, '扩展名称包含非法字符！')

    execstr = "cd " + yf.shlexQuote(getPluginDir() + "/versions") + " && /bin/bash " \
        + yf.shlexQuote("common.sh") + " " + yf.shlexQuote(version) + ' uninstall ' + yf.shlexQuote(name)

    data = yf.execShell(execstr)
    # data[0] == '' and
    if data[1] == '':
        return yf.returnJson(True, '已经卸载成功!')
    else:
        return yf.returnJson(False, '卸载错误信息!:' + data[1])

def getConfAppStart():
    pstart = yf.getServerDir() + '/php-apt/app_start.php'
    return pstart

def opcacheBlacklistFile():
    op_bl = yf.getServerDir() + '/php-apt/opcache-blacklist.txt'
    return op_bl

def installPreInspection(version):
    sys = yf.execShell(
        "cat /etc/*-release | grep PRETTY_NAME |awk -F = '{print $2}' | awk -F '\"' '{print $2}'| awk '{print $1}'")

    if sys[1] != '':
        return '不支持改系统'

    sys_id = yf.execShell(
        "cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}' | awk -F '\"' '{print $2}'")

    sysName = sys[0].strip().lower()
    sysId = sys_id[0].strip()

    if not sysName in ('debian', 'ubuntu'):
        return '仅支持debian,ubuntu'

    return 'ok'

def jsonEnvelopeOk(payload):
    """`yf.returnJson()` 信封是否代表成功（任务队列以退出码判成败，必须严格）。"""
    try:
        return bool(json.loads(payload).get('status'))
    except Exception:
        return False


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print('missing parameters')
        exit(0)

    func = sys.argv[1]

    if func == 'tune_all':
        print(tuneAllPhpConfig())
        exit(0)

    if func == 'check_plugin_upgrade':
        ver = formatVersion(sys.argv[2]) if len(sys.argv) > 2 else ''
        print(checkPluginUpgrade(ver))
        exit(0)

    if func == 'upgrade_self_healing':
        ver = formatVersion(sys.argv[2]) if len(sys.argv) > 2 else ''
        print(upgradeSelfHealing(ver))
        exit(0)

    if len(sys.argv) < 3:
        if func == 'kill_all_php':
            print(killAllPhp(''))
            exit(0)
        print('missing parameters')
        exit(0)

    inputVer = sys.argv[2]
    version = formatVersion(inputVer)
    # 版本号是所有 path/shell 拼接的唯一用户可控入口，统一在此收口校验
    if not isPhpVersion(version):
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
    elif func == 'submit_baseline_upgrade':
        print(submitBaselineUpgrade(version))
    elif func == 'upgrade_to_baseline':
        # 任务队列入口：失败必须以非零退出码结束，否则任务会被记成成功
        _r = upgradeToBaseline(version)
        print(_r)
        sys.exit(0 if jsonEnvelopeOk(_r) else 1)
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
    elif func == 'get_php_info':
        print(getPhpinfo(version))
    elif func == 'get_lib_conf':
        print(getLibConf(version))
    elif func == 'install_lib':
        print(installLib(version))
    elif func == 'uninstall_lib':
        print(uninstallLib(version))
    else:
        print("fail")
