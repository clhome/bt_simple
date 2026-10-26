# coding: utf-8
"""包源可达性诊断 —— 把「证书校验失败 / 302 到认证页」翻译成人话。

## 为什么需要它

真机现场（2026-10-26）报障「PHP 升级到安全基线失败」，任务日志是：

    错误:1 https://mirrors.tuna.tsinghua.edu.cn/debian bookworm InRelease
      Certificate verification failed: The certificate is NOT trusted. The certificate
      issuer is unknown. The name in the certificate does not match the expected.
    ...
    W: 部分索引文件下载失败。如果忽略它们，那将转而使用旧的索引文件。
    升级了 0 个软件包，新安装了 0 个软件包 ... 有 182 个软件包未被升级。

而旧实现的报文是「请检查 /etc/apt/sources.list 与 sury 源，并确认 apt-get update 成功」——
把**本机外网被上网认证网关（Dr.COM）劫持**说成了**源配置写错**。运维照着去改源，
改一天也改不好：`curl http://任意域名/` 会 302 到内网门户，`https://` 被换成网关的
自签证书（实测 `CN=demotest.doctorcom.com`），apt 的证书校验必然失败。

本模块只做一件事：给定「刚才那条命令的报错原文 + 一个待探测的主机」，输出
`{kind, blocked, summary, advice}` 这几样人话，让插件把**真正的**处置办法
（完成上网认证 / 用离线包 / 指向内网镜像）写进任务日志。

## 纪律

* **纯标准库**、不 import yf/Flask —— testsuite 在任何机器上都能直接断言分类逻辑；
* **永不抛异常**：探测失败只是「少一条证据」，不能让升级流程因为诊断而崩；
* **探测有界**：单次探测默认 5 秒，最多探两次（HTTP 80 + TLS 443）；
* **不跟随 302**：认证网关的指纹正是「3xx 跳到内网门户」，跟随就再也看不到它了；
* **不猜**：认证页/自签证书是**证据**，报文里要带出来（哪个 URL、跳到哪、证书是谁）。
"""

import ipaddress
import logging
import re
import socket
import ssl

# 刻意**不**在模块顶层 `import http.client`：本仓 `web/utils/email.py` 与标准库 `email`
# 同名，凡是把 `web/utils` 放进 sys.path 的进程（testsuite 就是这样 import 插件的），
# `http.client` → `email.parser` 会被解析成那个 `email.py` 并直接 ImportError。
# 探测模块是诊断用的附属品，不能因为这种历史阴影把插件启动搞崩 —— 所以按需导入，
# 导入失败也只降级成「这条证据没拿到」。

_log = logging.getLogger('yf.net_probe')

#: 包源不可用类型。
KIND_OK = 'ok'                            # 源可达（能正常握手/返回真内容）
KIND_CAPTIVE_PORTAL = 'captive_portal'    # 被上网认证网关拦截（302 到内网门户 / 认证页）
KIND_TLS_INTERCEPT = 'tls_intercept'      # HTTPS 被中间人替换证书（自签/域名不符）
KIND_DNS = 'dns'                          # 域名解析失败
KIND_TIMEOUT = 'timeout'                  # 连接超时（大概率没有外网出口）
KIND_REFUSED = 'refused'                  # 连接被拒绝
KIND_HTTP_ERROR = 'http_error'            # 源可达但返回 4xx/5xx（镜像自身问题）
KIND_UNKNOWN = 'unknown'                  # 认不出来（不许瞎猜）

#: 这些类型意味着「换源/改配置也没用，必须先解决网络出口」。
BLOCKED_KINDS = (KIND_CAPTIVE_PORTAL, KIND_TLS_INTERCEPT, KIND_DNS, KIND_TIMEOUT)

#: 从命令输出里认类型（小写匹配）。顺序即优先级：先认 TLS，再认门户。
_TEXT_MARKERS = (
    (KIND_TLS_INTERCEPT, (
        'certificate verification failed',
        'ssl certificate problem',
        'server certificate verification failed',
        'certificate verify failed',
        'certificate is not trusted',
        'the certificate issuer is unknown',
        'self-signed certificate',
        'self signed certificate',
        'unable to get local issuer certificate',
        'certificate has expired',
        'could not handshake',
        '证书校验失败',
        '证书验证失败',
        '证书不受信任',
    )),
    (KIND_CAPTIVE_PORTAL, (
        'webloginid',
        '<!doctype html',            # 把 HTML 当包索引/压缩包，几乎都是网关劫持
        '上网登录页',
        '上网认证',
        'drcom',
    )),
    (KIND_DNS, (
        'temporary failure resolving',
        'could not resolve',
        'name or service not known',
        'nodename nor servname',
        'no address associated with hostname',
        '无法解析',
        '域名解析',
    )),
    (KIND_TIMEOUT, (
        'connection timed out',
        'operation timed out',
        'timed out',
        '连接超时',
    )),
    (KIND_REFUSED, (
        'connection refused',
        'failed to connect',
        'network is unreachable',
        'no route to host',
        '无法连接',
    )),
    (KIND_HTTP_ERROR, (
        'http error 4',
        'http error 5',
        'error:1  ',
        '404  not found',
        '403  forbidden',
    )),
)

#: 认证页正文的指纹（与 `_TEXT_MARKERS` 里那批同源，但这是**实测响应体**的判据）。
_PORTAL_BODY_MARKERS = (
    'webloginid',
    'drcom',
    'drup',
    'srun',
    '上网登录页',
    '上网认证',
    '登录页',
    '请先登录',
    '网络接入认证',
)

#: 认证页/门户常见形态（用于报文里报「跳到了哪」）。
_URL_RE = re.compile(r'https?://[^\s\'"<>()\[\]]+', re.I)
_TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S)

#: 单个探测的超时（秒）。
DEFAULT_TIMEOUT = 5.0


def classify_text(text):
    """从 apt/yum/wget 的报错原文认类型（纯函数，不联网）。"""
    low = str(text or '').lower()
    if not low.strip():
        return KIND_UNKNOWN
    for kind, markers in _TEXT_MARKERS:
        for mark in markers:
            if mark in low:
                return kind
    return KIND_UNKNOWN


def extract_url(text):
    """从报错原文里取第一个 URL（apt 的 `W: 无法下载 <url> ...` 就在里面）。"""
    m = _URL_RE.search(str(text or ''))
    return m.group(0).rstrip('.,;:') if m else ''


def host_of(url):
    """`https://a.b/c` → `a.b`（不引入 urllib.parse 之外的分支）。"""
    raw = str(url or '').strip()
    if not raw:
        return ''
    m = re.match(r'^[a-zA-Z][a-zA-Z0-9+.\-]*://([^/?#:]+)', raw)
    if m:
        return m.group(1).strip().lower()
    m = re.match(r'^([^/?#:]+)', raw)
    return m.group(1).strip().lower() if m else ''


def _is_private_host(host):
    """IP 字面量是否内网/环回（认证网关几乎总是内网地址）。"""
    raw = str(host or '').strip()
    if not raw:
        return False
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return False
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local)


def _close_quietly(obj):
    """关连接/套接字：失败无所谓，但要留一行 debug（门禁禁止 `except: pass`）。"""
    if obj is None:
        return
    try:
        obj.close()
    except Exception as ex:            # noqa: BLE001 —— close 失败不影响诊断结论
        _log.debug('[net_probe] close 失败: %s', ex)


def _title_of(body):
    m = _TITLE_RE.search(body or '')
    if not m:
        return ''
    return ' '.join(m.group(1).split())[:60]


def _ipv4_of(host):
    """取该主机的第一个 IPv4（取不到返回空串）。

    为什么要**只走 IPv4**：镜像站普遍双栈，而内网/认证网关的机器通常没有 IPv6 出口。
    走 `socket.create_connection` 的默认顺序时，一个 IPv6 尝试的 5 秒超时就会把整个
    探测吃掉（现场就出现过：同一台机器手动 curl 能拿到 302 认证页，面板探测却什么都
    探不到）——探测不出来就等于诊断不出来。apt 自己也是走 IPv4（报错里带 `[IP: ... 443]`）。
    """
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
    except OSError as ex:
        _log.debug('[net_probe] getaddrinfo(%s, AF_INET) 失败: %s', host, ex)
        return ''
    for info in infos:
        addr = info[4][0]
        if addr:
            return addr
    return ''


def probe_http(host, port=80, timeout=DEFAULT_TIMEOUT, path='/'):
    """探一次明文 HTTP（**不跟随 302**）。返回 dict，失败也有 `error` 字段。"""
    out = {'code': 0, 'server': '', 'location': '', 'title': '', 'body': '', 'error': '',
           'ip': ''}
    if not host:
        out['error'] = 'no host'
        return out
    ip = _ipv4_of(host)
    conn = None
    try:
        import http.client           # 理由见文件头「按需导入」
    except Exception as ex:          # noqa: BLE001
        out['error'] = 'http.client 不可用: %s' % ex
        return out
    try:
        # 连 IP、带原始 Host 头：既避开 IPv6 超时，又不会因 Host 不对拿到默认站点
        conn = http.client.HTTPConnection(ip or host, port, timeout=timeout)
        out['ip'] = ip or host
        conn.request('GET', path or '/', headers={
            'Host': host,
            'User-Agent': 'yf-panel/net-probe',
            'Accept': '*/*',
            'Connection': 'close',
        })
        resp = conn.getresponse()
        raw = resp.read(4096) or b''
        out['code'] = int(getattr(resp, 'status', 0) or 0)
        out['server'] = str(resp.getheader('Server') or '')
        out['location'] = str(resp.getheader('Location') or '')
        body = raw.decode('utf-8', 'replace')
        out['body'] = body[:2048]
        out['title'] = _title_of(body)
    except Exception as ex:            # noqa: BLE001 —— 诊断永不抛
        _log.debug('[net_probe] probe_http(%s) 失败: %s', host, ex)
        out['error'] = '%s: %s' % (type(ex).__name__, ex)
    finally:
        _close_quietly(conn)
    return out


def probe_tls(host, port=443, timeout=DEFAULT_TIMEOUT):
    """探一次 TLS（**严格校验证书**，按系统 CA）。连 IPv4，但 SNI/证书比对仍按域名。"""
    out = {'ok': False, 'error': '', 'ip': ''}
    if not host:
        out['error'] = 'no host'
        return out
    ip = _ipv4_of(host) or host
    out['ip'] = ip
    ctx = ssl.create_default_context()
    sock = None
    try:
        sock = socket.create_connection((ip, port), timeout=timeout)
        tls = ctx.wrap_socket(sock, server_hostname=host)
        out['ok'] = True
        out['version'] = tls.version() or ''
        _close_quietly(tls)
    except ssl.SSLCertVerificationError as ex:
        out['error'] = str(getattr(ex, 'verify_message', '') or ex)
    except Exception as ex:            # noqa: BLE001
        out['error'] = '%s: %s' % (type(ex).__name__, ex)
    finally:
        _close_quietly(sock)
    return out


def looks_like_portal(http_info):
    """这次 HTTP 探测像不像「被认证网关接管了」？

    三个判据，任一命中即算（彼此独立，避免单一特征被 CDN 误伤）：

      1. `Server` 头是 Dr.COM 一类的网关（`DrcomServer1.0`）；
      2. 响应体是认证/登录页（标题或正文含 `WebLoginID`/`上网登录页` 等指纹）；
      3. 3xx 跳转到**内网地址**（正常镜像的 http→https 跳转目标是公网/CDN，
         而认证网关跳的是 `http://172.17.1.121` 这种内网门户）。
    """
    info = http_info or {}
    if 'drcom' in str(info.get('server') or '').lower():
        return True
    haystack = ('%s %s' % (info.get('title') or '', info.get('body') or '')).lower()
    for mark in _PORTAL_BODY_MARKERS:
        if mark in haystack:
            return True
    code = int(info.get('code') or 0)
    location = str(info.get('location') or '')
    if code in (301, 302, 303, 307, 308) and location:
        if _is_private_host(host_of(location)):
            return True
    return False


def _offline_hint(branch=''):
    sub = ('/%s' % branch) if branch else '/<分支>'
    return ('离线通道：把该分支的 .deb 包放进面板 data/php_deb%s/ 后重试'
            '（面板会用本地包升级，不依赖外网）' % sub)


def _summary(kind, ctx):
    """按类型拼一句「发生了什么 + 证据」。ctx 里的值都来自**实测**。"""
    url = ctx.get('url') or ''
    host = ctx.get('host') or ''
    portal = ctx.get('portal') or {}
    tls = ctx.get('tls') or {}
    ev = []
    if portal.get('code'):
        ev.append('HTTP %s' % portal['code'])
    if portal.get('location'):
        ev.append('跳转到 %s' % portal['location'])
    if portal.get('server'):
        ev.append('Server: %s' % portal['server'])
    if portal.get('title'):
        ev.append('认证页标题「%s」' % portal['title'])
    if tls.get('error'):
        ev.append('HTTPS 证书校验失败：%s' % str(tls['error'])[:160])
    evidence = '，'.join(ev)
    if kind == KIND_CAPTIVE_PORTAL:
        head = '本机外网被上网认证网关拦截（%s）' % (host or url or '包源主机')
        return head + ('；' + evidence if evidence else '')
    if kind == KIND_TLS_INTERCEPT:
        head = '包源的 HTTPS 证书校验失败（%s）' % (host or url or '包源主机')
        return head + ('：' + evidence if evidence else '')
    if kind == KIND_DNS:
        return '包源域名解析失败（%s）' % (host or url or '包源主机')
    if kind == KIND_TIMEOUT:
        return '连接包源超时（%s）——本机大概率没有可用的外网出口' % (host or url or '包源主机')
    if kind == KIND_REFUSED:
        return '连接包源被拒绝/不可达（%s）' % (host or url or '包源主机')
    if kind == KIND_HTTP_ERROR:
        return '包源返回错误页（%s）——镜像自身可能异常，换镜像后再试' % (host or url or '包源主机')
    if kind == KIND_OK:
        return '包源可达（%s）' % (host or url or '')
    return '包源不可达，原因未能识别'


def _advice(kind, ctx):
    branch = ctx.get('branch') or ''
    if kind == KIND_CAPTIVE_PORTAL:
        portal = ctx.get('portal') or {}
        where = portal.get('location') or ('http://%s/' % (ctx.get('host') or ''))
        return ('先在本机完成上网认证（浏览器打开 %s），认证通过后 apt 才能刷新索引；'
                '完全内网不能认证的机器请用离线包：%s' % (where, _offline_hint(branch)))
    if kind == KIND_TLS_INTERCEPT:
        return ('对端出示的证书不受系统 CA 信任，说明链路上有网关/代理在做中间人；'
                '不要关掉证书校验（等于给供应链开后门），请让网关放行包源，或 %s'
                % _offline_hint(branch))
    if kind == KIND_DNS:
        return '检查 /etc/resolv.conf 与 DNS 服务（能 ping 通 IP 但解析不出域名时，先修 DNS）'
    if kind == KIND_TIMEOUT:
        return ('本机没有可用外网出口（或包源被防火墙拦）；先确认 `curl -I http://%s/` 能通，'
                '或 %s' % (ctx.get('host') or '包源主机', _offline_hint(branch)))
    if kind == KIND_REFUSED:
        return '包源端口不可达（防火墙/代理拒绝）；改用内网镜像或 %s' % _offline_hint(branch)
    if kind == KIND_HTTP_ERROR:
        return '换一个镜像源（面板不自动跳过 4xx/5xx 的镜像）'
    if kind == KIND_OK:
        return ''
    return '原始报错见任务日志；可先在本机执行 `apt-get update` 复现'


def diagnose(url=None, text='', timeout=DEFAULT_TIMEOUT, branch='',
             http_probe=None, tls_probe=None):
    """给「报错原文 + 一个 URL」下结论。

    返回 `{kind, blocked, url, host, summary, advice, portal, tls}`：

      * `kind`     —— `KIND_*` 之一；
      * `blocked`  —— True 表示「换源没用，必须先解决网络出口」；
      * `summary`  —— 一句话结论（带实测证据，直接写进任务日志/消息框）；
      * `advice`   —— 可执行的处置办法。

    `http_probe`/`tls_probe` 可注入（testsuite 用它断言「不联网也能判定」）。
    """
    hp = http_probe or probe_http
    tp = tls_probe or probe_tls
    url = str(url or '').strip()
    kind = classify_text(text)
    host = host_of(url)
    ctx = {'url': url, 'host': host, 'branch': branch, 'portal': {}, 'tls': {}}

    # 只有「源不可达」类才值得真去探一次；源可达（ok/http_error）时探测无意义。
    if host and kind in (KIND_UNKNOWN, KIND_TLS_INTERCEPT, KIND_CAPTIVE_PORTAL,
                         KIND_TIMEOUT, KIND_REFUSED):
        try:
            portal = hp(host, timeout=timeout)
        except Exception as ex:        # noqa: BLE001 —— 注入的实现也不许把诊断搞崩
            _log.debug('[net_probe] http_probe 注入实现失败: %s', ex)
            portal = {}
        ctx['portal'] = portal or {}
        if looks_like_portal(ctx['portal']):
            # 明文被跳内网门户 ⇒ 就是认证网关；这也顺带解释了 HTTPS 为何证书不符
            kind = KIND_CAPTIVE_PORTAL
        if kind in (KIND_TLS_INTERCEPT, KIND_CAPTIVE_PORTAL, KIND_UNKNOWN):
            try:
                ctx['tls'] = tp(host, timeout=timeout) or {}
            except Exception as ex:    # noqa: BLE001
                _log.debug('[net_probe] tls_probe 注入实现失败: %s', ex)
                ctx['tls'] = {}
            if kind == KIND_UNKNOWN and not ctx['tls'].get('ok') and ctx['tls'].get('error'):
                kind = KIND_TLS_INTERCEPT
            if kind == KIND_CAPTIVE_PORTAL and ctx['tls'].get('ok'):
                # 明文门户 + HTTPS 正常 ⇒ 不是劫持，别乱扣帽子
                kind = KIND_UNKNOWN

    return {
        'kind': kind,
        'blocked': kind in BLOCKED_KINDS,
        'url': url,
        'host': host,
        'summary': _summary(kind, ctx),
        'advice': _advice(kind, ctx),
        'portal': ctx.get('portal') or {},
        'tls': ctx.get('tls') or {},
    }
