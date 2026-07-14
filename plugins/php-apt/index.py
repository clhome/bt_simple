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

import core.mw as mw

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def localVersion(v):
    return v[0:1]+v[2:3]

def getPluginName():
    return 'php-apt'


def getAppDir():
    return yf.getServerDir()+'/'+getPluginName()

def getServerDir():
    return '/etc/php'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


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


def getConf(version):
    path = getServerDir() + '/' + version + '/fpm/php.ini'
    return path


def getFpmConfFile(version):
    return getServerDir() + '/' + version + '/fpm/pool.d/yf.conf'

def getFpmFile(version):
    return getServerDir() + '/' + version + '/fpm/php-fpm.conf'

def status(version):
    if yf.isAppleSystem():
        return 'stop'
    # 使用 systemctl is-active 精准判定服务状态，防止 grep 模糊匹配造成的误判
    cmd = "systemctl is-active php" + version + "-fpm"
    data = yf.execShell(cmd)
    if data[0].strip() == 'active':
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

    service_php_fpm_mw = service_php_fpm_dir + '/yf.conf'
    if not os.path.exists(service_php_fpm_mw):
        tpl_php_fpmwww = getPluginDir() + '/conf/www.conf'
        content = yf.readFile(tpl_php_fpmwww)
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

        yf.writeFile(service_php_fpm_mw, content)


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
    if method == 'start':
        initReplace(version)

    if yf.isAppleSystem():
        return 'fail'
    
    if method in ['start', 'restart', 'reload']:
        sock_file = getFpmAddress(version)
        if isinstance(sock_file, str) and os.path.exists(sock_file):
            os.system('rm -f ' + sock_file)
        pid_file = '/run/php/php' + version + '-fpm.pid'
        if os.path.exists(pid_file):
            pid = yf.readFile(pid_file).strip()
            if pid:
                os.system('kill -9 ' + pid)
    
    data = yf.execShell('systemctl ' + method + ' ' +'php' + version + '-fpm')
    if data[1] == '':
        return 'ok'
    return data[1]


def start(version):
    return phpOp(version, 'start')


def stop(version):
    status = phpOp(version, 'stop')
    deleteConfList(version)
    return status


def restart(version):
    return phpOp(version, 'restart')


def reload(version):
    return phpOp(version, 'reload')

def killAllPhp(version):
    yf.execShell('pkill -f php-fpm')
    return 'ok'


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
    phpini = yf.readFile(getConf(version))
    result = []
    for g in gets:
        rep = g['name'] + r'\s*=\s*([0-9A-Za-z_& ~]+)(\s*;?|\r?\n)'
        tmp = re.search(rep, phpini)
        if not tmp:
            continue
        g['value'] = tmp.groups()[0]
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
    for g in gets:
        if g in args:
            rep = g + r'\s*=\s*(.+)\r?\n'
            val = g + ' = ' + args[g] + '\n'
            phpini = re.sub(rep, val, phpini)
    yf.writeFile(filename, phpini)
    reload(version)
    return yf.returnJson(True, '设置成功')


def getLimitConf(version):
    fileini = getConf(version)
    phpini = yf.readFile(fileini)
    filefpm = getFpmConfFile(version)
    phpfpm = yf.readFile(filefpm)

    # print fileini, filefpm
    data = {}
    try:
        rep = r"upload_max_filesize\s*=\s*([0-9]+)M"
        tmp = re.search(rep, phpini).groups()
        data['max'] = tmp[0]
    except:
        data['max'] = '50'

    try:
        rep = r"request_terminate_timeout\s*=\s*([0-9]+)\n"
        tmp = re.search(rep, phpfpm).groups()
        data['maxTime'] = tmp[0]
    except:
        data['maxTime'] = 0

    try:
        rep = r"\n;*\s*cgi\.fix_pathinfo\s*=\s*([0-9]+)\s*\n"
        tmp = re.search(rep, phpini).groups()

        if tmp[0] == '1':
            data['pathinfo'] = True
        else:
            data['pathinfo'] = False
    except:
        data['pathinfo'] = False

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
    conf = yf.readFile(filefpm)
    data = {}
    rep = r"\s*pm.max_children\s*=\s*([0-9]+)\s*"
    tmp = re.search(rep, conf).groups()
    data['max_children'] = tmp[0]

    rep = r"\s*pm.start_servers\s*=\s*([0-9]+)\s*"
    tmp = re.search(rep, conf).groups()
    data['start_servers'] = tmp[0]

    rep = r"\s*pm.min_spare_servers\s*=\s*([0-9]+)\s*"
    tmp = re.search(rep, conf).groups()
    data['min_spare_servers'] = tmp[0]

    rep = r"\s*pm.max_spare_servers \s*=\s*([0-9]+)\s*"
    tmp = re.search(rep, conf).groups()
    data['max_spare_servers'] = tmp[0]

    rep = r"\s*pm\s*=\s*(\w+)\s*"
    tmp = re.search(rep, conf).groups()
    data['pm'] = tmp[0]
    return yf.getJson(data)


def setFpmConfig(version):
    args = getArgs()
    # if not 'max' in args:
    #     return 'missing time args!'

    # version = args['version']
    max_children = args['max_children']
    start_servers = args['start_servers']
    min_spare_servers = args['min_spare_servers']
    max_spare_servers = args['max_spare_servers']
    pm = args['pm']

    filefpm = getFpmConfFile(version)
    conf = yf.readFile(filefpm)

    rep = r"\s*pm.max_children\s*=\s*([0-9]+)\s*"
    conf = re.sub(rep, "\npm.max_children = " + max_children, conf)

    rep = r"\s*pm.start_servers\s*=\s*([0-9]+)\s*"
    conf = re.sub(rep, "\npm.start_servers = " + start_servers, conf)

    rep = r"\s*pm.min_spare_servers\s*=\s*([0-9]+)\s*"
    conf = re.sub(rep, "\npm.min_spare_servers = " + min_spare_servers, conf)

    rep = r"\s*pm.max_spare_servers \s*=\s*([0-9]+)\s*"
    conf = re.sub(rep, "\npm.max_spare_servers = " + max_spare_servers + "\n", conf)

    rep = r"\s*pm\s*=\s*(\w+)\s*"
    conf = re.sub(rep, "\npm = " + pm + "\n", conf)

    yf.writeFile(filefpm, conf)
    reload(version)

    msg = yf.getInfo('设置PHP-{1}并发设置,max_children={2},start_servers={3},min_spare_servers={4},max_spare_servers={5}',
                     (version, max_children, start_servers, min_spare_servers, max_spare_servers,))
    yf.writeLog('插件管理[PHP]', msg)
    return yf.returnJson(True, '设置成功!')


def getFpmAddress(version):
    fpm_address = '/run/php/php{}-fpm.sock'.format(version)
    php_fpm_file = getFpmConfFile(version)
    try:
        content = yf.readFile(php_fpm_file)
        tmp = re.findall(r"^(?!\s*;)\s*listen\s*=\s*(.+)", content, re.M)
        if not tmp:
            return fpm_address
        if tmp[0].find('sock') != -1:
            return fpm_address
        if tmp[0].find(':') != -1:
            listen_tmp = tmp[0].split(':')
            if bind:
                fpm_address = (listen_tmp[0], int(listen_tmp[1]))
            else:
                fpm_address = ('127.0.0.1', int(listen_tmp[1]))
        else:
            fpm_address = ('127.0.0.1', int(tmp[0]))
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
        return yf.returnJson(False, '指定PHP版本不存在!')

    phpini = yf.readFile(filename)

    rep = r'session.save_handler\s*=\s*([0-9A-Za-z_& ~]+)(\s*;?|\r?\n)'
    save_handler = re.search(rep, phpini)
    if save_handler:
        save_handler = save_handler.group(1)
    else:
        save_handler = "files"

    reppath = r'\nsession.save_path\s*=\s*"tcp\:\/\/([\d\.]+):(\d+).*\r?\n'
    passrep = r'\nsession.save_path\s*=\s*"tcp://[\w\.\?\:]+=(.*)"\r?\n'
    memcached = r'\nsession.save_path\s*=\s*"([\d\.]+):(\d+)"'
    save_path = re.search(reppath, phpini)
    if not save_path:
        save_path = re.search(memcached, phpini)
    passwd = re.search(passrep, phpini)
    port = ""
    if passwd:
        passwd = passwd.group(1)
    else:
        passwd = ""
    if save_path:
        port = save_path.group(2)
        save_path = save_path.group(1)

    else:
        save_path = ""

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
            yf.execShell('mkdir -p %s' % i)
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
    if not os.path.exists(filename):
        return yf.returnJson(False, '指定PHP版本不存在!')

    phpini = yf.readFile(filename)
    data = {}
    rep = r"disable_functions\s*=\s{0,1}(.*)\n"
    tmp = re.search(rep, phpini).groups()
    data['disable_functions'] = tmp[0]
    return yf.getJson(data)


def setDisableFunc(version):
    filename = getConf(version)
    if not os.path.exists(filename):
        return yf.returnJson(False, '指定PHP版本不存在!')

    args = getArgs()
    disable_functions = args['disable_functions']

    phpini = yf.readFile(filename)
    rep = r"disable_functions\s*=\s*.*\n"
    phpini = re.sub(rep, 'disable_functions = ' +
                    disable_functions + "\n", phpini)

    msg = yf.getInfo('修改PHP-{1}的禁用函数为[{2}]', (version, disable_functions,))
    yf.writeLog('插件管理[PHP-YUM]', msg)
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
    os.system("rm -rf " + root_dir)
    phpinfo = str(sock_data, encoding='utf-8')
    return phpinfo


def get_php_info(args):
    inputVer = args['version']
    version = inputVer[0] + '.' + inputVer[1]
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

    if len(sys.argv) < 3:
        print('missing parameters')
        exit(0)

    inputVer = sys.argv[2]
    version = inputVer[0] + '.' + inputVer[1]

    if func == 'status':
        print(status(version))
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
