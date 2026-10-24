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


def getLanIp():
    """本机内网（局域网）IPv4 地址，取不到返回 ''。

    只用于界面展示「内网地址」，不参与任何鉴权/校验。取值顺序：
      1) UDP connect 不发包，只让内核按默认路由挑出口网卡（跨平台、无外部依赖）；
      2) ``hostname -I`` 的输出（多网卡/容器环境更准）。
    仅接受私网地址：公网 IP 直接绑在网卡上的机器返回 ''（那种情况下内网
    与外网就是同一个地址，前端会自己去重）。
    """
    import ipaddress
    import socket

    candidates = []
    try:
        _sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            _sock.connect(('8.8.8.8', 53))
            candidates.append(_sock.getsockname()[0])
        finally:
            _sock.close()
    except OSError as _e:
        _log.debug('[yf] 探测内网地址（UDP 出口）失败: %s', _e)

    try:
        _out = execShell('hostname -I 2>/dev/null')
        for _ip in ((_out[0] if _out else '') or '').split():
            candidates.append(_ip.strip())
    except Exception as _e:
        _log.debug('[yf] 探测内网地址（hostname -I）失败: %s', _e)

    for _ip in candidates:
        if not _ip:
            continue
        try:
            _obj = ipaddress.ip_address(_ip)
        except ValueError:
            continue
        if _obj.version != 4 or _obj.is_loopback or _obj.is_link_local:
            continue
        if _obj.is_private:
            return _ip
    return ''


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
        try:
            context.set_ciphers(ciphers)
        except Exception as _e:
            # 套件字串不被当前 OpenSSL 接受（如编译掉了 DHE）时，宁可用 OpenSSL
            # 默认套件把面板起起来，也不要因为一个降级策略把启动弄挂；最低版本
            # TLS 1.2 仍生效。
            _log.error('[yf] 面板 SSL 加密套件不可用，改用 OpenSSL 默认套件: %s', _e)
    if certfile and keyfile:
        context.load_cert_chain(certfile, keyfile)
    return context


#: 面板 SSL 配置所在的 option 名（面板设置页写的就是它）
PANEL_SSL_OPTION = 'panel_ssl'

#: 合法的面板 SSL 证书来源（与 web/utils/setting.py 的口径一致）
PANEL_SSL_CHOOSE = ('local', 'nginx')


def panelSslState(panel_ssl_data=None):
    """面板 SSL 的**实际可用**状态：配置意图 + 磁盘证书文件的一致性判定。

    为什么必须只有这一个入口：`panel_ssl.open` 只是「用户点了开启」，能不能真
    起 HTTPS 取决于 `<面板目录>/ssl/<choose>/{cert.pem,private.pem}` 是否真的在。
    历史实现里各处口径不一 —— gunicorn 配置要 open **且** 证书存在才上 TLS，而
    `checkDomainPanel`（302 到 https）、`SESSION_COOKIE_SECURE`、HSTS 只看 open。
    于是只要证书没落盘就得到「半开状态」：跳到 https 打不开 + Secure Cookie 不被
    回传 → 面板彻底访问不了（实测日志里只剩一条 chmod ... No such file）。

    返回 dict（键名稳定，调用方共享同一份判定）：
      open     配置里的 open 原值（用户意图）
      choose   'local' / 'nginx'，非法值原样带回
      certfile 证书路径（choose 非法时为空串）
      keyfile  私钥路径（choose 非法时为空串）
      ready    cert/key 都在且非空 —— 只有 True 才允许真的上 HTTPS
      degraded open 为真但证书不可用（半开状态，必须按「未启用」处理并显式告警）
    """
    state = {
        'open': False,
        'choose': 'local',
        'certfile': '',
        'keyfile': '',
        'ready': False,
        'degraded': False,
    }

    if panel_ssl_data is None:
        try:
            import thisdb
            panel_ssl_data = thisdb.getOptionByJson(PANEL_SSL_OPTION, default={'open': False})
        except Exception as _e:
            # 读库失败按「未开启」处理：宁可明文 HTTP 可用，也不要半开状态把人锁在外面
            _log.debug('[yf] 读取面板 SSL 配置失败，按未开启处理: %s', _e)
            panel_ssl_data = {'open': False}

    if not isinstance(panel_ssl_data, dict):
        return state

    choose = panel_ssl_data.get('choose') or 'local'
    state['open'] = bool(panel_ssl_data.get('open'))
    state['choose'] = choose
    if choose not in PANEL_SSL_CHOOSE:
        return state

    pdir = getPanelDir()
    state['certfile'] = pdir + '/ssl/' + choose + '/cert.pem'
    state['keyfile'] = pdir + '/ssl/' + choose + '/private.pem'
    if not state['open']:
        return state

    try:
        ready = (os.path.isfile(state['certfile'])
                 and os.path.getsize(state['certfile']) > 0
                 and os.path.isfile(state['keyfile'])
                 and os.path.getsize(state['keyfile']) > 0)
    except OSError as _e:
        _log.debug('[yf] 面板 SSL 证书文件不可用(%s): %s', state['choose'], _e)
        ready = False

    state['ready'] = ready
    state['degraded'] = not ready
    return state


def panelSslContextFactory(certfile=None, keyfile=None, ciphers=None):
    """返回 gunicorn `ssl_context` 需要的 callable（签名必须是 ``(conf, factory)``）。

    gunicorn>=21（本仓下界 22.0.0，实测 26.0.0）把这个配置项定义成**可调用对象**：
    参数固定为 ``(Config, default_ssl_context_factory)``，由 ``validate_callable(2)``
    校验。直接给它一个 SSLContext 实例会被拒：

        Invalid value for ssl_context: <ssl.SSLContext object at 0x...>
        Error: Value is not callable: <ssl.SSLContext object at 0x...>

    更阴的是这只在 stderr 里告警（该配置项被跳过），gunicorn 照常启动，但
    **根本没有 TLS** —— 界面以为开了 HTTPS，实际仍是明文。所以这里返回闭包，
    由 gunicorn 在需要 socket 时再调用。

    gunicorn 的默认工厂已经按 ``conf.certfile`` / ``conf.keyfile`` / ``conf.ciphers``
    装好证书链、也配好了 ALPN，因此我们只在它给出的 context 上补两条必须自己钉死的
    策略（最低 TLS 1.2、关压缩），其余交给 gunicorn 自己实现，避免两边打架。
    """
    def _panel_ssl_context(conf=None, default_ssl_context_factory=None):
        import ssl
        context = None
        if default_ssl_context_factory is not None:
            try:
                context = default_ssl_context_factory()
            except Exception as _e:
                # 默认工厂失败（证书/私钥读不了、ciphers 不被 OpenSSL 接受…）时
                # 退回自建 context，并把真实原因留在日志里。
                _log.error('[yf] gunicorn 默认 SSLContext 构建失败，改用面板自建 context: %s', _e)
                context = None
        if context is None:
            return createPanelSslContext(certfile, keyfile, ciphers)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.options |= ssl.OP_NO_COMPRESSION
        return context

    return _panel_ssl_context


def createLocalSSL():
    pdir = getPanelDir()
    local_dir = pdir+'/ssl/local'
    if not os.path.exists(local_dir):
        execShell('mkdir -p ' + local_dir)

    # 自签证书
    # if os.path.exists('ssl/local/input.pl'):
    #     return True

    # 目录必须真的建得出来：只读挂载 / 权限不足 / 同名文件占位时，后面的 writeFile
    # 只会静默返回 False，界面上「开启成功」、磁盘上什么都没有。这里提前报真实原因。
    try:
        if not os.path.isdir(local_dir):
            os.makedirs(local_dir, exist_ok=True)
    except OSError as _e:
        _log.error('[yf] 面板自签证书目录不可用: %s (%s)', local_dir, _e)
        return False
    if not os.path.isdir(local_dir):
        _log.error('[yf] 面板自签证书目录不可用: %s', local_dir)
        return False

    client_ip = getClientIp()
    # 无请求上下文时（gunicorn 载入配置、面板自愈、命令行调用）getClientIp() 只能
    # 回落 127.0.0.1，签出来的证书 CN 与实际访问地址不符；此时优先用本机 IP。
    try:
        from flask import has_request_context
        if not has_request_context():
            client_ip = getLocalIp() or client_ip
    except Exception as _e:
        _log.debug('[yf] 判断请求上下文失败，按无上下文处理: %s', _e)

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
        # writeFile 的默认契约是「失败只回 False、不抛异常」，历史调用点全都忽略
        # 返回值；这里必须显式校验落盘结果，否则「证书没写出去」会被当成功，
        # 随后 gunicorn 静默退回明文 HTTP（配置却说已开 HTTPS）→ 面板打不开。
        for _name, _body in (('cert.pem', cert_ca), ('private.pem', private_key)):
            _path = local_dir+'/'+_name
            try:
                _ok = writeFile(_path, _body, 'wb+')
            except Exception as _e:
                _log.error('[yf] 面板自签证书写入异常: %s (%s)', _path, _e)
                return False
            try:
                _size = os.path.getsize(_path) if os.path.isfile(_path) else 0
            except OSError as _e:
                _log.error('[yf] 面板自签证书落盘校验失败: %s (%s)', _path, _e)
                _size = 0
            if not _ok or _size == 0:
                _log.error('[yf] 面板自签证书写入失败: %s（真实原因见 logs/debug.log 的 [writeFile] 记录）',
                           _path)
                return False
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
