# coding: utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------
# 出网 URL 安全校验（SSRF 纵深防御）
#
# 供计划任务的「访问URL(toUrl)」使用：
#   1. 创建/编辑任务时 validate_url() 解析域名，拒绝解析到内网/回环/链路本地/保留
#      地址的 URL（含域名形式，堵住“字面 IP 判断”被 DNS Rebinding 绕过）；
#   2. 任务运行时由本模块 CLI 再次解析，并把解析出的 IP 通过 curl --resolve 固定，
#      消除“校验与真正发起请求之间 DNS 被改写”的时间窗。
#
# 仅依赖标准库，cron 可直接 `python3 urlguard.py <url>` 调用：
#   退出码 0 且 stdout 输出 "host:port:ip"（IP 字面量时输出空串，无需 --resolve）；
#   退出码非 0 表示不允许请求，stderr 为原因。
# ---------------------------------------------------------------------------------

import ipaddress
import socket
import sys
from urllib.parse import urlparse

# 明确的内网/元数据域名黑名单
_BLOCKED_HOSTNAMES = (
    'localhost',
    'metadata',
    'metadata.google.internal',
    'instance-data',
)


def is_public_ip(ip_str):
    try:
        ip = ipaddress.ip_address(str(ip_str).split('%')[0])
    except ValueError:
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or
                ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def _is_ip_literal(host):
    try:
        ipaddress.ip_address(str(host).split('%')[0])
        return True
    except ValueError:
        return False


def parse_url(url):
    """只做语法层校验，不触发 DNS。返回 (meta, err)。"""
    if not url or not isinstance(url, str):
        return None, 'URL不能为空'
    url = url.strip()
    if len(url) > 2048:
        return None, 'URL过长'
    try:
        parsed = urlparse(url)
    except Exception:
        return None, 'URL解析失败'

    if parsed.scheme not in ('http', 'https'):
        return None, '仅允许 http/https 协议'
    if parsed.username or parsed.password:
        return None, 'URL不允许携带用户名/密码'
    host = parsed.hostname
    if not host:
        return None, 'URL缺少主机名'
    if str(host).lower() in _BLOCKED_HOSTNAMES:
        return None, '禁止请求内网/回环/元数据地址（SSRF 防护）'
    try:
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    except ValueError:
        return None, '端口不合法'

    return {
        'url': url,
        'scheme': parsed.scheme,
        'host': host,
        'port': port,
        'host_is_ip': _is_ip_literal(host),
    }, 'OK'


def resolve_public(host, port):
    """解析 host 的所有 IP，任一落在非公网即判不安全。返回 (ips, err)。"""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception as e:
        return None, '域名解析失败: %s' % e

    ips = []
    for info in infos:
        try:
            addr = info[4][0].split('%')[0]
        except Exception:
            continue
        if addr in ips:
            continue
        if not is_public_ip(addr):
            return None, '目标解析到内网/保留地址(%s)' % addr
        ips.append(addr)

    if not ips:
        return None, '域名无可用的公网解析结果'
    return ips, 'OK'


def validate_url(url, resolve=True):
    """完整校验。返回 (ok, err, meta)；meta['ips'] 在 resolve=True 且非 IP 字面量时存在。"""
    meta, err = parse_url(url)
    if meta is None:
        return False, err, None

    if meta['host_is_ip']:
        if not is_public_ip(meta['host']):
            return False, '禁止请求内网/回环/保留地址（SSRF 防护）', None
        return True, 'OK', meta

    if resolve:
        ips, err = resolve_public(meta['host'], meta['port'])
        if ips is None:
            return False, err, None
        meta['ips'] = ips

    return True, 'OK', meta


def resolve_arg_from_meta(meta):
    """把已解析的 meta 转换为核心 curl 的 --resolve 参数；IP 字面量返回空串。"""
    if not meta:
        return ''
    if meta.get('host_is_ip') or not meta.get('ips'):
        return ''
    ip = meta['ips'][0]
    addr = '[%s]' % ip if ':' in ip else ip
    return '%s:%d:%s' % (meta['host'], meta['port'], addr)


def curl_resolve_arg(url):
    ok, _err, meta = validate_url(url, resolve=True)
    if not ok:
        return ''
    return resolve_arg_from_meta(meta)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.stderr.write('usage: urlguard.py <url>\n')
        sys.exit(2)
    _ok, _err, _meta = validate_url(sys.argv[1], resolve=True)
    if not _ok:
        sys.stderr.write(str(_err) + '\n')
        sys.exit(1)
    sys.stdout.write(resolve_arg_from_meta(_meta))
    sys.exit(0)
