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

# ---------------------------------------------------------------------------
# 出站 HTTP 用途分级（P2-6）
#
# 背景：本模块的 HTTP 客户端原先在 TLS 校验失败时会**静默降级为不校验证书**，
# 且不打任何日志。凭据类请求（bot token）与代码类下载（安装包/脚本/发布物）
# 一旦被中间人诱导降级就是直接失守；而低敏探测（本机接口、负载状态）在缺失 CA
# 束的老系统上又确实需要降级才能工作。因此按「这次请求承载什么」分级，降级许
# 可由分级决定，并且**任何降级都必须留痕**（不许静默）：
#
#   PURPOSE_LOW        低敏：查 IP 归属地、探测版本号/负载状态、本机 127.0.0.1
#                      接口、通知类。允许降级，但每次降级都写日志。
#   PURPOSE_CODE       代码类：下载可执行内容/安装包/脚本/发布物。禁止降级，
#                      校验失败即放弃并写明确原因。
#   PURPOSE_CREDENTIAL 凭据类：携带或换取凭据（token、口令、密钥、认证请求）。
#                      禁止降级，同上。
#
# 默认值是 PURPOSE_LOW：既有调用点不传也保持原行为（签名向后兼容）。
# 未知分级按「禁止降级」处理（fail-closed），避免分级名拼错反而静默放宽。
#
# 分级表（调用点 → purpose）。改调用点时请同步维护这张表：
#   low        plugins/apache/index.py runInfo（本机 server-status 负载状态）
#   low        plugins/openresty/index.py runInfo（本机 nginx_status）
#   low        plugins/op_load_balance/index.py getHealthStatus（节点 upstream 状态）
#   low        plugins/op_waf/index.py cleanDropIp / getDropIpList / removeDropIp
#              （127.0.0.1 的 WAF 内部接口）
#   low        plugins/op_waf/index.py testRun（本机站点自测）
#   low        plugins/fail2ban/index.py 解封联动（127.0.0.1 的 WAF 接口）
#   credential web/core/yf/panel.py tgbotNotifyHttpPost（path 里带 bot token）
#   code       暂无调用点：安装件下载走 panel_task.py 与 P1-3 的 shell 下载面，
#              常量与门禁已就绪供后续复用
# 转发层（不吃分级、原样透传）：web/core/yf/__init__.py 的 httpGet / httpPost。
# ---------------------------------------------------------------------------
PURPOSE_LOW = 'low'
PURPOSE_CODE = 'code'
PURPOSE_CREDENTIAL = 'credential'

#: 允许在 TLS 校验失败后降级为「不校验证书」的用途（**只有**低敏）。
_PURPOSE_DOWNGRADE_ALLOWED = {
    PURPOSE_LOW: True,
    PURPOSE_CODE: False,
    PURPOSE_CREDENTIAL: False,
}

#: 日志脱敏用：整个 query string / netloc 里的 userinfo / telegram bot token。
_RE_URL_QUERY = re.compile(r'\?[^\s\'")]*')
_RE_URL_USERINFO = re.compile(r'//[^/\s@]+@')
_RE_URL_TG_TOKEN = re.compile(r'/bot\d+:[A-Za-z0-9_-]+')


def _maskUrl(url):
    """脱敏 URL：只保留 ``scheme://host/path``。

    去掉 userinfo（``user:pass@``）与整个 query string（``?token=...``）——这两处
    最常夹带凭据；path 保留是为了日志还能定位到具体接口。telegram 的 bot token
    藏在 path 里（``/bot<id>:<token>/sendMessage``），额外单独擦掉。
    """
    try:
        if not isinstance(url, str):
            url = str(url)
        from urllib.parse import urlsplit
        parts = urlsplit(url.strip())
        try:
            host = parts.hostname or ''
            port = parts.port
        except ValueError:
            host, port = '', None
        netloc = host
        if port:
            netloc = '%s:%s' % (host, port)
        path = _RE_URL_TG_TOKEN.sub('/bot<已脱敏>', parts.path or '/')
        if parts.scheme:
            return '%s://%s%s' % (parts.scheme, netloc, path)
        if netloc:
            return '//%s%s' % (netloc, path)
        return path
    except Exception:
        return '<url 脱敏失败>'


def _errText(err):
    """异常转一行文本（带类型名），用于日志里的「原因」。"""
    try:
        return '%s: %s' % (type(err).__name__, err)
    except Exception:
        return '未知异常'


def _maskDetail(detail, url=None):
    """擦掉细节文本里可能夹带的原始 URL / query string / userinfo。

    urllib3 的异常（如 MaxRetryError）会把请求 URL 原样带进 message，直接写日志
    等于把凭据抄进日志，所以这里先整体替换成脱敏 URL，再用正则兜底擦残留。
    """
    try:
        text = detail if isinstance(detail, str) else str(detail)
    except Exception:
        return '<无法格式化>'
    if isinstance(url, str) and url and url in text:
        text = text.replace(url, _maskUrl(url))
    text = _RE_URL_USERINFO.sub('//', text)
    text = _RE_URL_QUERY.sub('?<已脱敏>', text)
    return text


def _httpPolicyLog(text):
    """写一条分级相关日志（降级 / 拒绝降级）。

    写日志失败绝不影响请求流程，也不许因此变成「静默」——退一步至少打 _log。
    """
    try:
        writeFileLog('[yf.net] ' + text)
    except Exception as e:
        _log.warning('[yf.net] 写 HTTP 分级日志失败: %s | 原日志: %s', e, text)


def _purposeAllowsDowngrade(purpose):
    """该用途是否允许在 TLS 校验失败后降级为「不校验证书」。

    未知用途 fail-closed（禁止降级）并留痕，避免分级名拼错反而放宽了校验。
    """
    if purpose is None:
        # 显式传 None 视同 low（兼容「不知道分级」的老调用形态）
        return True
    if isinstance(purpose, str) and purpose in _PURPOSE_DOWNGRADE_ALLOWED:
        return _PURPOSE_DOWNGRADE_ALLOWED[purpose]
    _httpPolicyLog('未知 purpose=%r，按禁止降级处理（只认 %s / %s / %s）'
                   % (purpose, PURPOSE_LOW, PURPOSE_CODE, PURPOSE_CREDENTIAL))
    return False


def _httpPolicyRefuse(method, url, purpose, detail=None):
    """code / credential 禁止降级的统一收口：写明确原因并返回错误串。

    返回错误串（而不是抛异常）与既有 `HttpGet` 的失败返回形态保持一致；错误里
    只带脱敏后的 URL，避免凭据随返回值回流到前端。
    """
    reason = 'TLS 校验失败/请求失败' if detail is None else _maskDetail(_errText(detail), url)
    _httpPolicyLog('禁止降级：purpose=%s 不允许改用不校验证书的通道（%s %s，原因：%s）'
                   % (purpose, method, _maskUrl(url), reason))
    return '请求失败（purpose=%s 禁止降级为不校验证书）: %s %s' % (purpose, method, _maskUrl(url))


def _insecure_ssl_context():
    try:
        import ssl
        return ssl._create_unverified_context()
    except Exception:
        return None


def _pool_request(method, url, timeout, body=None, headers=None, purpose=PURPOSE_LOW):
    """先用「验证证书」的连接池请求；失败后**按 purpose 决定是否降级**。

    - ``purpose=PURPOSE_LOW``（默认）：允许降级到不校验证书的池，但**每次降级都
      写日志**（purpose + 脱敏 url + 「已降级为不校验证书」），不许静默；保留这条
      路径是因为部分老系统 CA 束缺失，强验证会让本机探测/负载状态页全面失败。
    - ``purpose=PURPOSE_CODE`` / ``PURPOSE_CREDENTIAL``：禁止降级，验证失败即放弃，
      返回 None，并写明确原因（含 purpose 与脱敏后的 url）。

    返回解码后的字符串；失败返回 None。
    """
    allow_downgrade = _purposeAllowsDowngrade(purpose)
    verified_error = None
    for insecure in (False, True):
        if insecure:
            # 到这里说明「验证证书」的一轮已经失败（异常 / 池不可用）
            if not allow_downgrade:
                _httpPolicyLog('禁止降级：purpose=%s 不允许改用不校验证书的连接池'
                               '（%s %s，原因：%s）'
                               % (purpose, method, _maskUrl(url),
                                  _maskDetail(_errText(verified_error) if verified_error
                                              else '验证证书的连接池不可用', url)))
                return None
            _httpPolicyLog('已降级为不校验证书重试：purpose=%s（%s %s，原因：%s）'
                           % (purpose, method, _maskUrl(url),
                              _maskDetail(_errText(verified_error) if verified_error
                                          else '验证证书的连接池不可用', url)))
        pool = _get_http_pool(insecure=insecure)
        if not pool:
            if not insecure and verified_error is None:
                verified_error = '验证证书的连接池不可用'
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
        except Exception as e:
            if not insecure:
                verified_error = e
            else:
                _log.debug('[yf.net] 降级池请求仍失败: %s',
                           _maskDetail(_errText(e), url))
            continue
    return None


def HttpGet(url, timeout=10, purpose=PURPOSE_LOW):
    """
    发送GET请求（验证优先；失败后按 purpose 决定是否降级；连接池复用）
    @url 被请求的URL地址(必需)
    @timeout 超时时间默认10秒
    @purpose 用途分级：low/code/credential，默认 low（向后兼容）。
             code/credential 禁止任何降级（含下方 urllib 不校验兜底）。
    return string
    """
    data = _pool_request('GET', url, timeout, purpose=purpose)
    if data is not None:
        return data
    if _purposeAllowsDowngrade(purpose):
        # 低敏：允许兜底用「不校验证书」的 urllib 上下文，但必须留痕（不许静默）
        _httpPolicyLog('已降级为不校验证书兜底请求：purpose=%s（GET %s，连接池均失败）'
                       % (purpose, _maskUrl(url)))
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
            # 失败细节同样脱敏后再回流（异常文本可能夹带原始 URL）
            return _maskDetail(_errText(ex), url)
    return _httpPolicyRefuse('GET', url, purpose)


def HttpGet2(url, timeout, purpose=PURPOSE_LOW):
    """同 HttpGet（连接池版），purpose 语义一致（默认 low，向后兼容）。"""
    data = _pool_request('GET', url, timeout, purpose=purpose)
    if data is not None:
        return data
    if _purposeAllowsDowngrade(purpose):
        _httpPolicyLog('已降级为不校验证书兜底请求：purpose=%s（GET %s，连接池均失败）'
                       % (purpose, _maskUrl(url)))
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
            return _maskDetail(_errText(e), url)
    return _httpPolicyRefuse('GET', url, purpose)


def HttpPost(url, data, timeout=10, purpose=PURPOSE_LOW):
    """
    发送POST请求（验证优先；失败后按 purpose 决定是否降级；1MB 响应截断）
    @url 被请求的URL地址(必需)
    @data POST参数，可以是字符串或字典(必需)
    @timeout 超时时间默认10秒
    @purpose 用途分级：low/code/credential，默认 low（向后兼容）。
             带凭据的 POST（如 bot token）必须显式传 credential。
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
    result = _pool_request('POST', url, timeout, body=body, headers=headers, purpose=purpose)
    if result is not None:
        return result
    if _purposeAllowsDowngrade(purpose):
        _httpPolicyLog('已降级为不校验证书兜底请求：purpose=%s（POST %s，连接池均失败）'
                       % (purpose, _maskUrl(url)))
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
            return _maskDetail(_errText(ex), url)
    return _httpPolicyRefuse('POST', url, purpose)


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


def createPanelSslContext(certfile=None, keyfile=None, ciphers=None):
    """构造面板 HTTPS 监听用的 SSLContext，显式锁定最低 TLS 1.2。

    交给 gunicorn 的 `ssl_context` 配置项直接使用（gunicorn>=20.1），因此最低
    版本由本函数掌控，而不是依赖 gunicorn 自身的默认协商（可能退到 TLS 1.0/1.1）。
    刻意不 import gunicorn，便于单测直接断言 `minimum_version`。

    certfile/keyfile 传空时只构造「策略」不加载证书（供测试断言策略用）。
    """
    import ssl
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.options |= ssl.OP_NO_COMPRESSION
    if ciphers:
        context.set_ciphers(ciphers)
    if certfile and keyfile:
        context.load_cert_chain(certfile, keyfile)
    return context


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
        # 私钥权限不得依赖进程 umask：显式收紧为 0600（仅属主可读写），
        # 与 data/secret_key.pl 的既有做法一致。
        try:
            os.chmod(local_dir+'/private.pem', 0o600)
        except OSError as _e:
            _log.warning('[yf] 面板 SSL 私钥权限收紧失败: %s', _e)
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
