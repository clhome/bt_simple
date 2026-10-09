# coding:utf-8

import sys
import io
import os
import time
import re
import json
import shutil

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'php'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getInitDFile(version):
    current_os = yf.getOs()
    if current_os == 'darwin':
        return '/tmp/' + getPluginName()

    if current_os.startswith('freebsd'):
        return '/etc/rc.d/' + getPluginName()
    return '/etc/init.d/' + getPluginName() + version


def getConf(version):
    path = getServerDir() + '/' + version + '/etc/php.ini'
    return path


def getFpmConfFile(version):
    return getServerDir() + '/' + version + '/etc/php-fpm.d/www.conf'


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
    if not os.path.exists(path):
        return ""
    content = yf.readFile(path)
    if not content:
        return ""
    rep = r'(?m)^\s*;?\s*listen\s*=\s*(.*)'
    tmp = re.search(rep, content)
    if not tmp:
        return ""
    return tmp.groups()[0].strip()


def _phpFpmMasterPids(version):
    """按 /proc/<pid>/comm 精确识别 php-fpm master（避免命令行模糊匹配的假阳性）。"""
    pids = []
    marker = '/php/%s/' % version
    if not os.path.isdir('/proc'):
        return pids
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        try:
            with open('/proc/%s/comm' % entry, 'r', encoding='utf-8', errors='replace') as fp:
                comm = fp.read().strip()
            if comm != 'php-fpm':
                continue
            with open('/proc/%s/cmdline' % entry, 'rb') as fp:
                args = fp.read().replace(b'\x00', b' ').decode('utf-8', 'replace')
        except Exception:
            continue
        if marker in args and 'master process' in args:
            pids.append(entry)
    return pids


def status(version):
    '''
    统一对齐双模态精准探活
    '''
    try:
        import plugins.php.index as php_main
        return php_main.status(version)
    except Exception:
        # 回退路径同样用 comm 精确判定：旧写法 `ps|grep 'php/<v>' | grep -v python`
        # 仍会把命令行里带该字样的无关进程当成 start（varnish/sphinx 同族假阳性）
        sock = getPhpSocket(version)
        if _phpFpmMasterPids(version):
            return 'start'
        if not sock:
            return 'stop'
        if sock.find(':') != -1:
            return 'stop'
        if not os.path.exists(sock):
            return 'stop'
        return 'start'


def getFpmAddress(version):
    fpm_address = '/tmp/php-cgi-{}.sock'.format(version)
    php_fpm_file = getFpmConfFile(version)
    if not os.path.exists(php_fpm_file):
        return fpm_address
    try:
        content = yf.readFile(php_fpm_file)
        tmp = re.findall(r"listen\s*=\s*(.+)", content)
        if not tmp:
            return fpm_address
        raw_addr = tmp[0].strip()
        if raw_addr.find('sock') != -1:
            return raw_addr
        if raw_addr.find(':') != -1:
            listen_tmp = raw_addr.split(':')
            host = listen_tmp[0].strip() if listen_tmp[0].strip() else '127.0.0.1'
            fpm_address = (host, int(listen_tmp[1].strip()))
        else:
            fpm_address = ('127.0.0.1', int(raw_addr))
        return fpm_address
    except Exception:
        return fpm_address


def getPhpinfo(version):
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


def libConfCommon(version):
    fname = getConf(version)
    if not os.path.exists(fname):
        return yf.returnJson(False, '指定PHP版本不存在!')

    phpini = yf.readFile(fname)
    # readFile 失败返回 False（不是空串）→ 旧实现 phpini.find(...) 抛 AttributeError
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

    php_dir = getServerDir() + "/" + version
    ext_dir = php_dir + "/lib/php/extensions"

    # 未安装/未编译扩展目录时旧实现 os.listdir 直接 FileNotFoundError（真机 HTTP 回 traceback）
    ext_list = os.listdir(ext_dir) if os.path.isdir(ext_dir) else []
    for sodir in ext_list:
        if sodir.find("no-debug-non-zts") > -1:
            ext_dir += "/"+ sodir
            break

    libs = []
    tasks = yf.M('tasks').where("status!=?", ('1',)).field('status,name').select()
    for lib in phplib:
        if not isinstance(lib, dict):
            continue
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

        lib['status'] = False
        if phpini.find(lib['check']) > -1:
            lib['status'] = True
        sofile = ext_dir+"/"+lib['check']
        # 自定义，比较特殊的方式
        if os.path.exists(sofile):
            if os.path.getsize(sofile) == 7:
                lib['status'] = True
        libs.append(lib)
    return libs


def get_php_info(args):
    if not isinstance(args, dict) or 'version' not in args:
        return '缺少必要参数: version'
    return getPhpinfo(args['version'])


def get_lib_conf(data):
    if not isinstance(data, dict) or 'version' not in data:
        return yf.returnJson(False, '缺少必要参数: version')
    libs = libConfCommon(data['version'])
    if isinstance(libs, str):
        return libs
    return yf.returnData(True, 'OK!', libs)
