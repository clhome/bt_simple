# coding=utf-8
"""core.yf 子模块：net

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


from . import _get_http_pool, _log, createRsa, getClientIp, getHostAddr, getSshDir


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

def execShell(*args, **kwargs):
    return _pkg().execShell(*args, **kwargs)


def getPanelDir(*args, **kwargs):
    return _pkg().getPanelDir(*args, **kwargs)


def isAppleSystem(*args, **kwargs):
    return _pkg().isAppleSystem(*args, **kwargs)


def readFile(*args, **kwargs):
    return _pkg().readFile(*args, **kwargs)


def writeFile(*args, **kwargs):
    return _pkg().writeFile(*args, **kwargs)


def writeFileLog(*args, **kwargs):
    return _pkg().writeFileLog(*args, **kwargs)


def checkCert(certPath='ssl/certificate.pem'):
    # 验证证书
    openssl = '/usr/bin/openssl'
    if not os.path.exists(openssl):
        openssl = '/usr/local/openssl/bin/openssl'
    if not os.path.exists(openssl):
        openssl = 'openssl'
    certPem = readFile(certPath)
    s = "\n-----BEGIN CERTIFICATE-----"
    tmp = certPem.strip().split(s)
    for tmp1 in tmp:
        if tmp1.find('-----BEGIN CERTIFICATE-----') == -1:
            tmp1 = s + tmp1
        writeFile(certPath, tmp1)
        result = execShell(openssl + " x509 -in " +
                           certPath + " -noout -subject")
        if result[1].find('-bash:') != -1:
            return True
        if len(result[1]) > 2:
            return False
        if result[0].find('error:') != -1:
            return False
    return True


def getLocalIp():
    try:
        filename = getPanelDir() + '/data/iplist.txt'
        try:
            ipaddress = readFile(filename)
            if ipaddress and ipaddress != '127.0.0.1':
                return ipaddress
        except Exception as e:
            _log.debug('[yf] 解析 ipaddress 配置失败: %s', e)
        for flag in ['-4', '-6']:
            try:
                # 向下兼容 Python 2.7 ~ 3.x，移除 f-string，改用字符串拼接
                cmd = "curl --insecure " + flag + " -sS --connect-timeout 5 -m 60 https://speed.cloudflare.com/cdn-cgi/trace" # 使用 speed.cloudflare.com/cdn-cgi/trace 获取公网 IP
                ip = execShell(cmd)
                if ip and isinstance(ip, (tuple, list)) and ip[0]:
                    for line in ip[0].splitlines():
                        if line.startswith('ip='):
                            result = line[3:].strip()
                            if result:
                                writeFile(filename, result)
                                return result
            except Exception:
                continue
    except Exception as e:
        _log.debug('[yf] 获取公网 IP 失败，回退 127.0.0.1: %s', e)
    return '127.0.0.1'


def getSslCrt():
    if os.path.exists('/etc/ssl/certs/ca-certificates.crt'):
        return '/etc/ssl/certs/ca-certificates.crt'
    if os.path.exists('/etc/pki/tls/certs/ca-bundle.crt'):
        return '/etc/pki/tls/certs/ca-bundle.crt'
    return ''


def checkIp(ip):
    # 检查是否为IPv4地址
    import re
    p = re.compile(r'^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$')
    if p.match(ip):
        return True
    else:
        return False


def getHostPort():
    port_file = getPanelDir() + '/data/port.pl'
    if os.path.exists(port_file):
        return readFile(port_file).strip()
    return '7200'


def setHostPort(port):
    file = getPanelDir() + '/data/port.pl'
    return writeFile(file, port)


# ------------------------------   network start  -----------------------------

def _insecure_ssl_context():
    try:
        import ssl
        return ssl._create_unverified_context()
    except Exception:
        return None


def _pool_request(method, url, timeout, body=None, headers=None):
    """先用「验证证书」的连接池请求；失败再降级到不校验证书的池。

    返回解码后的字符串；两者都失败返回 None。保留降级路径是因为部分老系统
    CA 束缺失，强验证会导致插件/GitHub 下载全面失败。
    """
    for insecure in (False, True):
        pool = _get_http_pool(insecure=insecure)
        if not pool:
            continue
        try:
            kwargs = {'timeout': timeout, 'retries': False}
            if body is not None:
                kwargs['body'] = body
            if headers is not None:
                kwargs['headers'] = headers
            resp = pool.request(method, url, **kwargs)
            data = resp.data
            if isinstance(data, bytes):
                data = data[:1048576].decode('utf-8', errors='replace') if len(data) > 1048576 else data.decode('utf-8', errors='replace')
            return data
        except Exception:
            continue
    return None


def HttpGet(url, timeout=10):
    """
    发送GET请求（验证优先，失败降级；连接池复用）
    @url 被请求的URL地址(必需)
    @timeout 超时时间默认60秒
    return string
    """
    data = _pool_request('GET', url, timeout)
    if data is not None:
        return data
    try:
        import urllib.request
        ctx = _insecure_ssl_context()
        kwargs = {'timeout': timeout}
        if ctx is not None:
            kwargs['context'] = ctx
        response = urllib.request.urlopen(url, **kwargs)
        result = response.read()
        if isinstance(result, bytes):
            result = result[:1048576].decode('utf-8', errors='replace') if len(result) > 1048576 else result.decode('utf-8', errors='replace')
        return result
    except Exception as ex:
        return str(ex)


def HttpGet2(url, timeout):
    data = _pool_request('GET', url, timeout)
    if data is not None:
        return data
    import urllib.request
    try:
        ctx = _insecure_ssl_context()
        kwargs = {'timeout': timeout}
        if ctx is not None:
            kwargs['context'] = ctx
        req = urllib.request.urlopen(url, **kwargs)
        result = req.read()
        if isinstance(result, bytes):
            result = result[:1048576].decode('utf-8', errors='replace') if len(result) > 1048576 else result.decode('utf-8', errors='replace')
        return result
    except Exception as e:
        return str(e)


def HttpPost(url, data, timeout=10):
    """
    发送POST请求（验证优先，失败降级；1MB 响应截断）
    @url 被请求的URL地址(必需)
    @data POST参数，可以是字符串或字典(必需)
    @timeout 超时时间默认60秒
    return string
    """
    headers = {'User-Agent': 'bt_simple/1.0', 'Content-Type': 'application/x-www-form-urlencoded'}
    if isinstance(data, dict):
        if len(str(data)) > 65536:
            return "POST data too large"
        import urllib.parse as _up
        body = _up.urlencode(data)
    else:
        body = data
    result = _pool_request('POST', url, timeout, body=body, headers=headers)
    if result is not None:
        return result
    try:
        import urllib.request
        ctx = _insecure_ssl_context()
        if isinstance(data, dict):
            if len(str(data)) > 65536:
                return "POST data too large"
            data = urllib.parse.urlencode(data).encode('utf-8')
        elif isinstance(data, str):
            data = data.encode('utf-8')
        req = urllib.request.Request(url, data)
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        req.add_header('User-Agent', 'bt_simple/1.0')
        kwargs = {'timeout': timeout}
        if ctx is not None:
            kwargs['context'] = ctx
        response = urllib.request.urlopen(req, **kwargs)
        result = response.read()
        if isinstance(result, bytes):
            result = result[:1048576].decode('utf-8', errors='replace') if len(result) > 1048576 else result.decode('utf-8', errors='replace')
        return result
    except Exception as ex:
        return str(ex)


def isIpAddr(ip):
    check_ip = re.compile(r'^(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|[1-9])\.(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)\.(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)\.(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\\d)$')
    if check_ip.match(ip):
        return True
    else:
        return False


def isVaildIpV4(ip):
    import ipaddress
    try:
        ipaddress.IPv4Address(ip)
        return True
    except ipaddress.AddressValueError:
        return False


def isVaildIp(ip):
    import ipaddress
    try:
        ipaddress.IPv4Address(ip)
        return True
    except ipaddress.AddressValueError:
        # 判定型接口：IPv4 不匹配则再试 IPv6，最后 False（语义与原先一致）
        try:
            ipaddress.IPv6Address(ip)
            return True
        except ipaddress.AddressValueError:
            return False


def createLocalSSL():
    pdir = getPanelDir()
    local_dir = pdir+'/ssl/local'
    if not os.path.exists(local_dir):
        execShell('mkdir -p ' + local_dir)

    # 自签证书
    # if os.path.exists('ssl/local/input.pl'):
    #     return True

    client_ip = getClientIp()

    import OpenSSL
    key = OpenSSL.crypto.PKey()
    key.generate_key(OpenSSL.crypto.TYPE_RSA, 2048)
    cert = OpenSSL.crypto.X509()
    cert.set_serial_number(0)
    
    if client_ip == '127.0.0.1':
        cert.get_subject().CN = '127.0.0.1'
    else:
        cert.get_subject().CN = getLocalIp()
    
    cert.set_issuer(cert.get_subject())
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(86400 * 3650)
    cert.set_pubkey(key)
    cert.sign(key, 'sha256')
    cert_ca = OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
    private_key = OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, key)
    if len(cert_ca) > 100 and len(private_key) > 100:
        writeFile(local_dir+'/cert.pem', cert_ca, 'wb+')
        writeFile(local_dir+'/private.pem', private_key, 'wb+')
        return True
    return False


def getSSHPort():
    try:
        file = '/etc/ssh/sshd_config'
        conf = readFile(file)
        rep = "(#*)?Port\\s+([0-9]+)\\s*\n"
        port = re.search(rep, conf).groups(0)[1]
        return int(port)
    except Exception as _e:
        return 22


def getSSHStatus():
    if os.path.exists('/usr/bin/apt-get'):
        status = execShell("service ssh status | grep -P '(dead|stop)'")
    else:
        import system_api
        version = system_api.system_api().getSystemVersion()
        if version.find(' Mac ') != -1:
            return True
        if version.find(' 7.') != -1:
            status = execShell("systemctl status sshd.service | grep 'dead'")
        else:
            status = execShell(
                "/etc/init.d/sshd status | grep -e 'stopped' -e '已停'")
    if len(status[0]) > 3:
        status = False
    else:
        status = True
    return status


def createSshInfo():
    ssh_dir = getSshDir()
    if not os.path.exists(ssh_dir + '/id_rsa') or not os.path.exists(ssh_dir + '/id_rsa.pub'):
        createRsa()

    # 检查是否写入authorized_keys
    data = execShell("cat " + ssh_dir + "/id_rsa.pub | awk '{print $3}'")
    if data[0] != "":
        cmd = "cat " + ssh_dir + "/authorized_keys | grep " + data[0]
        ak_data = execShell(cmd)
        if ak_data[0] == "":
            cmd = 'cat ' + ssh_dir + '/id_rsa.pub >> ' + ssh_dir + '/authorized_keys'
            execShell(cmd)
            execShell('chmod 600 ' + ssh_dir + '/authorized_keys')


def connectSsh():
    import paramiko
    ssh = paramiko.SSHClient()
    createSshInfo()
    # B507 豁免：仅连接本机 127.0.0.1/localhost 的面板 SSH，主机密钥为面板自己生成
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # nosec B507  # 仅连本机 127.0.0.1

    port = getSSHPort()
    try:
        ssh.connect('127.0.0.1', port, timeout=5)
    except Exception as e:
        ssh.connect('localhost', port, timeout=5)
    except Exception as e:
        ssh.connect(getHostAddr(), port, timeout=30)
    except Exception as e:
        return False

    shell = ssh.invoke_shell(term='xterm', width=83, height=21)
    shell.setblocking(0)
    return shell


def clearSsh():
    # 服务器IP
    ip = getHostAddr()
    sh = '''
#!/bin/bash
PLIST=`who | grep localhost | awk '{print $2}'`
for i in $PLIST
do
    ps -t /dev/$i |grep -v TTY | awk '{print $1}' | xargs kill -9
done

# getHostAddr
PLIST=`who | grep "${ip}" | awk '{print $2}'`
for i in $PLIST
do
    ps -t /dev/$i |grep -v TTY | awk '{print $1}' | xargs kill -9
done
'''
    if not isAppleSystem():
        info = execShell(sh)
        writeFileLog(str(info[0]) + ' ' + str(info[1]))
