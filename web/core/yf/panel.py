# coding=utf-8
"""core.yf 子模块：panel

本文件由 ``scripts/tools/split_yf_module.py`` 从原 ``web/core/yf.py`` 按 AST
行号机械搬迁而来（**未改写任何函数体**）。修改请直接改本文件，不要手工搬回去。
"""



import os
import sys
import time
import threading
import string
import json
import hashlib
import hmac
import shlex
import datetime
import subprocess
import glob
import base64
import re
import logging
from random import Random
import functools


from . import deDoubleCrypt, getFileSuffix, getInfo, getNotifyPath, getPanelTaskPidFile, getTracebackInfo, getTriggerTaskLockFile, httpPost, notifyMessageTry


# ---------------------------------------------------------------------------
# 猴补丁兼容层（codemod 生成，勿手改）
# 下面这些符号被 testsuite 用 `yf.X = ...` 替换过，且 yf 内部有调用点。
# 真实定义在 `core/yf/__init__.py`；这里必须**运行时**经包命名空间解析，
# 否则会出现「补丁设了、内部调用仍走原实现」的假绿。
# 注意：这些名字不出现在 __init__ 的重导出清单里，避免自我覆盖成死循环。
# ---------------------------------------------------------------------------
def _pkg():
    """取包命名空间（shim 运行时解析用）。"""
    return sys.modules[__package__]

def M(*args, **kwargs):
    return _pkg().M(*args, **kwargs)


def execShell(*args, **kwargs):
    return _pkg().execShell(*args, **kwargs)


def getPanelDir(*args, **kwargs):
    return _pkg().getPanelDir(*args, **kwargs)


def getServerDir(*args, **kwargs):
    return _pkg().getServerDir(*args, **kwargs)


def opWeb(*args, **kwargs):
    return _pkg().opWeb(*args, **kwargs)


def readFile(*args, **kwargs):
    return _pkg().readFile(*args, **kwargs)


def safeExecShell(*args, **kwargs):
    return _pkg().safeExecShell(*args, **kwargs)


def systemdCfgDir(*args, **kwargs):
    return _pkg().systemdCfgDir(*args, **kwargs)


def writeFile(*args, **kwargs):
    return _pkg().writeFile(*args, **kwargs)


def writeFileLog(*args, **kwargs):
    return _pkg().writeFileLog(*args, **kwargs)


def writeLog(*args, **kwargs):
    return _pkg().writeLog(*args, **kwargs)


# ------------------------------   network end  -----------------------------

# ------------------------------   panel start  -----------------------------

def isRestart():
    # 检查是否允许重启
    num = M('tasks').where('status!=?', ('1',)).count()
    if num > 0:
        return False
    return True


def wakePanelTask():
    # 事件驱动：通知后台 panel_task 进程立即处理新任务，避免其固定间隔空转。
    # 仅在有 /proc 的 Linux 环境下按 cmdline 严格校验 PID 归属后才发信号，
    # 杜绝 PID 复用导致的误伤（panel_task.py 会注册 SIGUSR1 处理器）。
    import signal
    if not hasattr(signal, 'SIGUSR1'):
        return False
    try:
        if not os.path.isdir('/proc'):
            return False
        pid_file = getPanelTaskPidFile()
        if not os.path.exists(pid_file):
            return False
        with open(pid_file, 'r') as f:
            pid = int((f.read() or '').strip())
        if pid <= 1:
            return False
        cmdline_file = '/proc/%d/cmdline' % pid
        if not os.path.exists(cmdline_file):
            return False
        with open(cmdline_file, 'rb') as cf:
            cmdline = cf.read().decode('utf-8', 'ignore')
        if 'panel_task.py' not in cmdline:
            return False
        os.kill(pid, signal.SIGUSR1)
        return True
    except Exception:
        return False


def triggerTask():
    lock_file = getTriggerTaskLockFile()
    writeFile(lock_file, 'True')
    # 立即唤醒后台任务进程，替代固定 3 秒空转轮询
    wakePanelTask()


def restartTask():
    initd = getPanelDir() + '/scripts/init.d/yf'
    if os.path.exists(initd):
        safeExecShell([initd, 'restart_task'])
    return True


def restartPanel():
    restart_file = getPanelDir()+'/data/restart.pl'
    writeFile(restart_file, 'True')
    # 立即唤醒看门狗执行重启，替代 3 秒空转检测
    wakePanelTask()
    return True


def panelCmd(method):
    allowed = ('restart_task', 'reload', 'restart', 'stop', 'start')
    if method not in allowed:
        method = 'reload'
    import subprocess as _sp
    log_fp = open('/tmp/panelCmd.log', 'ab')
    for _cmd in (getPanelDir() + '/scripts/init.d/yf', '/etc/init.d/yf'):
        if os.path.exists(_cmd):
            try:
                _sp.Popen([_cmd, method], stdout=log_fp, stderr=_sp.STDOUT, start_new_session=True)
            except Exception as e:
                writeFileLog('[yf] 启动 systemd 服务失败: %s -> %s' % (_cmd, e))
            return


# ------------------------------    panel end    -----------------------------

# ------------------------------ openresty start -----------------------------

def getOpVer():
    version = ''
    version_file_pl = getServerDir() + '/openresty/version.pl'
    if os.path.exists(version_file_pl):
        version = readFile(version_file_pl)
        version = version.strip()
    return version


def checkWebConfig():
    op_dir = getServerDir() + '/openresty/nginx'
    # "ulimit -n 10240 && " +
    cmd = op_dir + "/sbin/nginx -t -c " + op_dir + "/conf/nginx.conf"
    result = execShell(cmd)
    searchStr = 'test is successful'
    if result[1].find(searchStr) == -1:
        msg = getInfo('配置文件错误[openresty]: {1}', (result[1],))
        writeLog("软件管理", msg)
        return result[1]
    return True


def checkHttpdConfig():
    op_dir = getServerDir() + '/apache/httpd'
    # "ulimit -n 10240 && " +
    cmd = op_dir + "/bin/httpd -t"
    result = execShell(cmd)
    searchStr = 'Syntax OK'
    if result[1].find(searchStr) == -1:
        msg = getInfo('配置文件错误[httpd]: {1}', (result[1],))
        writeLog("软件管理", msg)
        return result[1]
    return True


def getWebStatus():
    pid = getServerDir() + '/openresty/nginx/logs/nginx.pid'
    if os.path.exists(pid):
        return True
    return False


def restartWeb():
    return opWeb("reload")


def isInstalledWeb():
    path = getServerDir() + '/openresty/nginx/sbin/nginx'
    if os.path.exists(path):
        return True
    return False


def _do_reload():
    systemd = systemdCfgDir() + '/openresty.service'
    if os.path.exists(systemd):
        execShell('systemctl reload openresty')
        return True
    sys_initd = '/etc/init.d/openresty'
    if os.path.exists(sys_initd):
        safeExecShell([sys_initd, 'reload'])
        return True
    initd = getServerDir() + '/openresty/init.d/openresty'
    if os.path.exists(initd):
        execShell(initd + ' reload')
        return True
    return False


def opLuaMake(cmd_name):
    path = getServerDir() + '/web_conf/nginx/lua/lua.conf'
    root_dir = getServerDir() + '/web_conf/nginx/lua/' + cmd_name
    dst_path = getServerDir() + '/web_conf/nginx/lua/' + cmd_name + '.lua'
    def_path = getServerDir() + '/web_conf/nginx/lua/empty.lua'

    if not os.path.exists(root_dir):
        execShell('mkdir -p ' + root_dir)

    files = []
    for fl in os.listdir(root_dir):
        suffix = getFileSuffix(fl)
        if suffix != 'lua':
            continue
        flpath = os.path.join(root_dir, fl)
        files.append(flpath)

    if len(files) > 0:
        def_path = dst_path
        content = ''
        for f in files:
            t = readFile(f)
            f_base = os.path.basename(f)
            content += '-- ' + '*' * 20 + ' ' + f_base + ' start ' + '*' * 20 + "\n"
            content += t
            content += "\n" + '-- ' + '*' * 20 + ' ' + f_base + ' end ' + '*' * 20 + "\n"
        writeFile(dst_path, content)
    else:
        if os.path.exists(dst_path):
            os.remove(dst_path)

    conf = readFile(path)
    if not isinstance(conf, str):
        conf = ''
    if conf:
        conf = re.sub(cmd_name + ' (.*);',
                      lambda m: cmd_name + " " + def_path.replace('\\', '/') + ";", conf)
        writeFile(path, conf)


def opLuaInitFile():
    opLuaMake('init_by_lua_file')


def opLuaInitWorkerFile():
    opLuaMake('init_worker_by_lua_file')


def opLuaInitAccessFile():
    opLuaMake('access_by_lua_file')


def opLuaMakeAll():
    opLuaInitFile()
    opLuaInitWorkerFile()
    opLuaInitAccessFile()


# ------------------------------ openresty end -----------------------------

# ---------------------------------------------------------------------------------
# PHP START
# ---------------------------------------------------------------------------------

def getFpmConfFile(version):
    return getServerDir() + '/php/' + version + '/etc/php-fpm.d/www.conf'


def getFpmAddress(version, bind=False):
    fpm_address = '/tmp/php-cgi-{}.sock'.format(version)
    php_fpm_file = getFpmConfFile(version)
    try:
        content = readFile(php_fpm_file)
        tmp = re.findall(r"listen\s*=\s*(.+)", content)
        if not tmp:
            return fpm_address
        if tmp[0].find('sock') != -1:
            return fpm_address
        if tmp[0].find(':') != -1:
            listen_tmp = tmp[0].split(':')
            # 修复：原实现在此处引用了未定义的 `bind`，NameError 被外层 except 吞掉，
            # 于是「php-fpm 监听 TCP 端口」时静默回退到 unix socket 路径（连不上）。
            # 这里补回丢失的 `bind` 参数（默认 False = 回退本机，与下方 bare-port 分支同口径）。
            # 注：fcgi_client.FCGIApp::_getConnection 对 tuple 走 socket.create_connection，
            # 即 TCP 连接，所以返回元组是有意设计。
            if bind:
                fpm_address = (listen_tmp[0], int(listen_tmp[1]))
            else:
                fpm_address = ('127.0.0.1', int(listen_tmp[1]))
        else:
            fpm_address = ('127.0.0.1', int(tmp[0]))
        return fpm_address
    except Exception as _e:
        return fpm_address


def requestFcgiPHP(sock, uri, document_root='/tmp', method='GET', pdata=b''):
    # 直接请求到PHP-FPM
    # version php版本
    # uri 请求uri
    # filename 要执行的php文件
    # args 请求参数
    # method 请求方式

    import utils.php.fpm as fpm
    p = fpm.fpm(sock, document_root)

    if type(pdata) == dict:
        # 修复：原实现调用了不存在的 url_encode（每次 pdata 为 dict 时必 NameError 500）。
        # load_url_public 内部 len(content) + StringIO(content)，故必须传 str，不要 .encode()。
        import urllib.parse
        pdata = urllib.parse.urlencode(pdata)
    result = p.load_url_public(uri, pdata, method)
    return result


# ---------------------------------------------------------------------------------
# PHP END
# ---------------------------------------------------------------------------------


# ---------------------------------------------------------------------------------
# 数据库 START
# ---------------------------------------------------------------------------------

def getMyORM():
    '''
    获取MySQL资源的ORM
    '''
    import core.orm as orm
    o = orm.ORM()
    return o


##################### ssh  end   #########################################
        
##################### notify  start #########################################


def initNotifyConfig():
    p = getNotifyPath()
    if not os.path.exists(p):
        writeFile(p, '{}')
    return True


def getNotifyData(is_parse=False):
    initNotifyConfig()
    notify_file = getNotifyPath()
    notify_data = readFile(notify_file)

    data = json.loads(notify_data)

    if is_parse:
        tag_list = ['tgbot', 'email']
        for t in tag_list:
            if t in data and 'cfg' in data[t]:
                data[t]['data'] = json.loads(deDoubleCrypt(t, data[t]['cfg']))
    return data


def writeNotify(data):
    p = getNotifyPath()
    return writeFile(p, json.dumps(data))


def tgbotNotifyChatID():
    data = getNotifyData(True)
    if 'tgbot' in data and 'enable' in data['tgbot']:
        if data['tgbot']['enable']:
            t = data['tgbot']['data']
            return t['chat_id']
    return ''


def tgbotNotifyObject():
    data = getNotifyData(True)
    if 'tgbot' in data and 'enable' in data['tgbot']:
        if data['tgbot']['enable']:
            t = data['tgbot']['data']
            import telebot
            # 修复：原实现引用未定义的 app_token（必 NameError）。与 tgbotNotifyChatID 同源取键。
            bot = telebot.TeleBot(t['app_token'])
            return True, bot
    return False, None


def tgbotNotifyMessage(app_token, chat_id, msg):
    import telebot
    bot = telebot.TeleBot(app_token)
    try:
        data = bot.send_message(chat_id, msg)
        return True
    except Exception as e:
        writeFileLog(str(e))
    return False


def tgbotNotifyHttpPost(app_token, chat_id, msg):
    try:
        url = 'https://api.telegram.org/bot' + app_token + '/sendMessage'
        post_data = {
            'chat_id': chat_id,
            'text': msg,
        }
        rdata = httpPost(url, post_data)
        return True
    except Exception as e:
        writeFileLog(str(e))
        return str(e)
    return False


def tgbotNotifyTest(app_token, chat_id):
    msg = 'MW-通知验证测试OK'
    return tgbotNotifyHttpPost(app_token, chat_id, msg)


def emailNotifyMessage(data):
    '''
    邮件通知
    '''
    import utils.email as email
    try:
        if data['smtp_ssl'] == 'ssl':
            r = email.sendSSL(data['smtp_host'], data['smtp_port'],
                           data['username'], data['password'],
                           data['to_mail_addr'], data['subject'], data['content'])
        else:
            r = email.send(data['smtp_host'], data['smtp_port'],
                        data['username'], data['password'],
                        data['to_mail_addr'], data['subject'], data['content'])

            writeFileLog(str(r))
        return True
    except Exception as e:
        writeFileLog(getTracebackInfo())
        return str(e)
    return False


def emailNotifyTest(data):
    # print(data)
    data['subject'] = 'MW通知测试'
    data['content'] = data['mail_test']
    return emailNotifyMessage(data)


def notifyMessage(msg, stype='common', trigger_time=300, is_write_log=True):
    try:
        return notifyMessageTry(msg, stype, trigger_time, is_write_log)
    except Exception as e:
        writeFileLog(getTracebackInfo())
        return False
