# coding:utf-8

import sys
import io
import os
import time
import re
import json
import shutil


# 动态获取项目根目录，避免因执行脚本时当前工作目录(Cwd)不同而导致 core 依赖导入失败
panel_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
web_dir = os.path.join(panel_root, "web")
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

app_debug = False
if yf.isAppleSystem():
    app_debug = True

CURRENT_PLUGIN_VERSION = '2.0'
_PHP_APT_UPGRADE_CHECKING = False


def formatVersion(v):
    v = str(v).strip()
    if not v:
        return ''
    if '.' in v:
        return v
    if len(v) >= 2:
        return v[0] + '.' + v[1:]
    return v


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
    """获取系统 apt 安装的已就绪 PHP 版本列表（如 ['7.4', '8.1']）"""
    php_dir = getServerDir()
    if not os.path.exists(php_dir):
        return []
    versions = []
    for item in os.listdir(php_dir):
        full_path = os.path.join(php_dir, item)
        if os.path.isdir(full_path) and re.match(r'^\d+\.\d+$', item):
            versions.append(item)
    return sorted(versions)


def getArgs():
    args = sys.argv[3:]
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        try:
            tmp = json.loads(args[0])
        except Exception:
            t = args[0].strip('{').strip('}')
            t = t.split(':')
            if len(t) >= 2:
                tmp[t[0]] = t[1]
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':')
            if len(t) >= 2:
                tmp[t[0]] = t[1]
    return tmp


def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '参数:(' + ck[i] + ')没有!'))
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

def status(version):
    if yf.isAppleSystem():
        return 'stop'

    version = formatVersion(version)
    try:
        checkPluginUpgrade(version)
    except Exception:
        pass

    # 1. 优先采用 systemctl is-active
    cmd = "systemctl is-active php" + version + "-fpm"
    data = yf.execShell(cmd)
    if data[0].strip() == 'active':
        return 'start'

    # 2. 降级通过 pid 文件校验
    pid_file = '/run/php/php' + version + '-fpm.pid'
    if os.path.exists(pid_file):
        try:
            pid_str = yf.readFile(pid_file).strip()
            if pid_str and pid_str.isdigit():
                pid = int(pid_str)
                os.kill(pid, 0)
                return 'start'
        except Exception:
            pass

    # 3. 降级通过进程树特征匹配
    chk = yf.execShell(f"ps aux | grep 'php-fpm: master process' | grep '({version})' | grep -v grep")
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
    content = json.loads(content)
    versions = content['versions']
    tpl = getPluginDir() + '/conf/enable-php.conf'
    tpl_content = yf.readFile(tpl)
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
            mem_total_str = yf.execShell("free -m | grep Mem | awk '{print $2}'")[0].strip()
            if mem_total_str:
                mem_total = int(mem_total_str)
                if mem_total <= 1024:
                    max_children = 30; start_servers = 5; min_spare_servers = 5; max_spare_servers = 10
                elif mem_total <= 2048:
                    max_children = 50; start_servers = 5; min_spare_servers = 5; max_spare_servers = 20
                elif mem_total <= 4096:
                    max_children = 100; start_servers = 10; min_spare_servers = 10; max_spare_servers = 30
                elif mem_total <= 8192:
                    max_children = 150; start_servers = 15; min_spare_servers = 15; max_spare_servers = 30
                else:
                    max_children = 300; start_servers = 20; min_spare_servers = 20; max_spare_servers = 50
                    
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
    content = contentReplace(content, version)
    yf.writeFile(desc_php_fpm, content)
    return True


def initReplace(version):
    makeOpConf(version)
    phpFpmWwwReplace(version)

    install_ok = getAppDir() + "/" + localVersion(version) + "/install.ok"
    if not os.path.exists(install_ok):
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
    # systemd
    # yf.execShell('systemctl daemon-reload')
    return 'ok'


def tunePhpConfig(version):
    php_dir = getServerDir()
    ini_file = php_dir + '/' + version + '/fpm/php.ini'
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
            chk_m = yf.execShell(f"ps aux | grep 'php-fpm: master process' | grep '({version})' | grep -v grep")
            if not chk_m[0].strip():
                try:
                    os.remove(sock_file)
                except Exception:
                    yf.execShell(f'rm -f {sock_file}')

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
            except Exception:
                pass

        # 4. 重置 systemd 失败状态
        yf.execShell(f'systemctl reset-failed {service_name} 2>/dev/null')

        # 5. 拉起服务
        res = yf.execShell(f'systemctl {method} {service_name}')
        time.sleep(0.5)
        if status(version) == 'start':
            return 'ok'

        # 降级尝试 service 命令拉起
        yf.execShell(f'service {service_name} {method} 2>/dev/null')
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
                    chk_m = yf.execShell(f"ps aux | grep 'php-fpm: master process' | grep '({ver})' | grep -v grep")
                    if not chk_m[0].strip():
                        try:
                            os.remove(sock_file)
                        except Exception:
                            yf.execShell(f'rm -f {sock_file}')
                        logs.append(f"已清理残留的孤儿套接字: {sock_file}")
                if os.path.exists(pid_file):
                    try:
                        os.remove(pid_file)
                    except Exception:
                        yf.execShell(f'rm -f {pid_file}')
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
        except Exception:
            pass
        return yf.returnJson(True, '大版本迁移升级自愈成功完成。')
    finally:
        _PHP_APT_UPGRADE_CHECKING = False


def initdStatus(version):
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    shell_cmd = 'systemctl status php' + version + \
        '-fpm | grep loaded | grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall(version):
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    yf.execShell('systemctl enable php' + version + '-fpm')
    return 'ok'


def initdUinstall(version):
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    yf.execShell('systemctl disable php' + version + '-fpm')
    return 'ok'


def fpmLog(version):
    return '/var/log/php' + version + '-fpm.log'


def fpmSlowLog(version):
    return '/var/log/fpm-php' + version + '.www.slow.log'


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
    gets = ['display_errors', 'cgi.fix_pathinfo', 'date.timezone', 'short_open_tag',
            'asp_tags', 'max_execution_time', 'max_input_time', 'max_input_vars', 'memory_limit',
            'post_max_size', 'file_uploads', 'upload_max_filesize', 'max_file_uploads',
            'default_socket_timeout', 'error_reporting']
    args = getArgs()
    filename = getConf(version)
    phpini = yf.readFile(filename)
    if not phpini or isinstance(phpini, bool):
        phpini = ''
    for g in gets:
        if g in args:
            rep = r'(?m)^\s*;?\s*' + re.escape(g) + r'\s*=.*'
            val = f'{g} = {args[g]}'
            if re.search(rep, phpini):
                phpini = re.sub(rep, val, phpini)
            else:
                phpini += f'\n{val}\n'
    yf.writeFile(filename, phpini)
    reload(version)
    return yf.returnJson(True, '设置成功')


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
    args = getArgs()
    data = checkArgs(args, ['time'])
    if not data[0]:
        return data[1]

    time = args['time']
    if int(time) < 30 or int(time) > 86400:
        return yf.returnJson(False, '请填写30-86400间的值!')

    filefpm = getFpmConfFile(version)
    conf = yf.readFile(filefpm)
    rep = r"request_terminate_timeout\s*=\s*([0-9]+)\n"
    conf = re.sub(rep, "request_terminate_timeout = " + time + "\n", conf)
    yf.writeFile(filefpm, conf)

    fileini = getConf(version)
    phpini = yf.readFile(fileini)
    rep = r"max_execution_time\s*=\s*([0-9]+)\r?\n"
    phpini = re.sub(rep, "max_execution_time = " + time + "\n", phpini)
    rep = r"max_input_time\s*=\s*([0-9]+)\r?\n"
    phpini = re.sub(rep, "max_input_time = " + time + "\n", phpini)
    yf.writeFile(fileini, phpini)
    return yf.returnJson(True, '设置成功!')


def setMaxSize(version):
    args = getArgs()
    data = checkArgs(args, ['max'])
    if not data[0]:
        return data[1]

    maxVal = args['max']
    if int(maxVal) < 2:
        return yf.returnJson(False, '上传大小限制不能小于2MB!')

    path = getConf(version)
    conf = yf.readFile(path)
    rep = r"\nupload_max_filesize\s*=\s*[0-9]+M"
    conf = re.sub(rep, u'\nupload_max_filesize = ' + maxVal + 'M', conf)
    rep = r"\npost_max_size\s*=\s*[0-9]+M"
    conf = re.sub(rep, u'\npost_max_size = ' + maxVal + 'M', conf)
    yf.writeFile(path, conf)

    msg = yf.getInfo('设置PHP-{1}最大上传大小为[{2}MB]!', (version, maxVal,))
    yf.writeLog('插件管理[PHP]', msg)
    return yf.returnJson(True, '设置成功!')


def getFpmConfig(version):
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
    args = getArgs()
    max_children = str(args.get('max_children', '30')).strip()
    start_servers = str(args.get('start_servers', '5')).strip()
    min_spare_servers = str(args.get('min_spare_servers', '5')).strip()
    max_spare_servers = str(args.get('max_spare_servers', '10')).strip()
    pm = str(args.get('pm', 'dynamic')).strip()

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
    except:
        return fpm_address


def getFpmStatus(version):

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
        except Exception:
            pass

    data = {"save_handler": save_handler, "save_path": save_path,
            "passwd": passwd, "port": port}
    return yf.returnJson(True, 'ok', data)


def setSessionConf(version):

    args = getArgs()

    ip = args['ip']
    port = args['port']
    passwd = args['passwd']
    save_handler = args['save_handler']

    if save_handler != "files":
        iprep = r"(2(5[0-5]{1}|[0-4]\d{1})|[0-1]?\d{1,2})\.(2(5[0-5]{1}|[0-4]\d{1})|[0-1]?\d{1,2})\.(2(5[0-5]{1}|[0-4]\d{1})|[0-1]?\d{1,2})\.(2(5[0-5]{1}|[0-4]\d{1})|[0-1]?\d{1,2})"
        if not re.search(iprep, ip):
            return yf.returnJson(False, '请输入正确的IP地址')

        try:
            port = int(port)
            if port >= 65535 or port < 1:
                return yf.returnJson(False, '请输入正确的端口号')
        except:
            return yf.returnJson(False, '请输入正确的端口号')
        prep = r"[\~\`\/\=]"
        if re.search(prep, passwd):
            return yf.returnJson(False, '请不要输入以下特殊字符 " ~ ` / = "')

    filename = getConf(version)
    if not os.path.exists(filename):
        return yf.returnJson(False, '指定PHP版本不存在!')
    phpini = yf.readFile(filename)

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


def getSessionCount_Origin(version):
    session_tmp = getServerDir() + "/tmp/session"
    d = ["/tmp", "/var/lib/php/sessions", session_tmp]
    count = 0
    for i in d:
        if not os.path.exists(i):
            yf.makeDirs(i)
        list = os.listdir(i)
        for l in list:
            if os.path.isdir(i + "/" + l):
                l1 = os.listdir(i + "/" + l)
                for ll in l1:
                    if "sess_" in ll:
                        count += 1
                continue
            if "sess_" in l:
                count += 1

    s = "find /tmp -mtime +1 |grep 'sess_' | wc -l"
    old_file = int(yf.execShell(s)[0].split("\n")[0])

    s = "find " + session_tmp + " -mtime +1 |grep 'sess_'|wc -l"
    old_file += int(yf.execShell(s)[0].split("\n")[0])
    return {"total": count, "oldfile": old_file}


def getSessionCount(version):
    data = getSessionCount_Origin(version)
    return yf.returnJson(True, 'ok!', data)


def cleanSessionOld(version):
    s = "find /tmp -mtime +1 |grep 'sess_'|xargs rm -f"
    yf.execShell(s)

    session_tmp = getServerDir() + "/tmp/session"
    s = "find " + session_tmp + " -mtime +1 |grep 'sess_' |xargs rm -f"
    yf.execShell(s)
    old_file_conf = getSessionCount_Origin(version)["oldfile"]
    if old_file_conf == 0:
        return yf.returnJson(True, '清理成功')
    else:
        return yf.returnJson(True, '清理失败')


def getDisableFunc(version):
    filename = getConf(version)
    phpini = yf.readFile(filename) if os.path.exists(filename) else ''
    if not phpini:
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
            except Exception:
                pass
    return yf.getJson(data)


def setDisableFunc(version):
    filename = getConf(version)
    if not os.path.exists(filename):
        return yf.returnJson(False, '指定PHP版本不存在!')

    args = getArgs()
    disable_functions = str(args.get('disable_functions', '')).strip()

    phpini = yf.readFile(filename)
    if not phpini:
        phpini = ""

    rep = r"(?m)^\s*;?\s*disable_functions\s*=.*$"
    if re.search(rep, phpini):
        phpini = re.sub(rep, 'disable_functions = ' + disable_functions, phpini)
    else:
        phpini = phpini.rstrip() + '\ndisable_functions = ' + disable_functions + '\n'

    msg = yf.getInfo('修改PHP-{1}的禁用函数为[{2}]', (version, disable_functions,))
    yf.writeLog('插件管理[PHP-APT]', msg)
    yf.writeFile(filename, phpini)
    reload(version)
    return yf.returnJson(True, '设置成功!')


def getPhpinfo(version):
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
    inputVer = args['version']
    version = formatVersion(inputVer)
    return getPhpinfo(version)


def getLibConf(version):
    fname = getConf(version)
    if not os.path.exists(fname):
        return yf.returnJson(False, '指定PHP版本不存在!')

    # phpini = yf.readFile(fname)
    content = yf.execShell('cat /etc/php/' + version + '/fpm/conf.d/*' + " | grep -v '^;' |tr -s '\n'")
    content = content[0]

    libpath = getPluginDir() + '/versions/phplib.conf'
    phplib = json.loads(yf.readFile(libpath))

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
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']
    
    # 严格校验扩展名称，防范命令注入漏洞
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return yf.returnJson(False, '扩展名称包含非法字符！')

    cmd = "cd " + getPluginDir() + "/versions && /bin/bash  common.sh " + version + ' install ' + name
    install_name = '安装PHPAPT[' + name + '-' + version + ']'
    import thisdb
    thisdb.addTask(name=install_name,cmd=cmd)

    yf.triggerTask()
    return yf.returnJson(True, '已将下载任务添加到队列!')


def uninstallLib(version):
    args = getArgs()
    data = checkArgs(args, ['name'])
    if not data[0]:
        return data[1]

    name = args['name']

    # 严格校验扩展名称，防范命令注入漏洞
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return yf.returnJson(False, '扩展名称包含非法字符！')

    execstr = "cd " + getPluginDir() + "/versions && /bin/bash common.sh " + version + ' uninstall ' + name

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
