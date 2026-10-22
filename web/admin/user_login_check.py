# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------


from flask import render_template
from flask import Response
from flask import request

from functools import wraps

from admin import session
from admin.common import isLogined

import thisdb
import hmac
import ipaddress
import logging
import re

import core.yf as yf

# 白名单的写入点是 admin/setting/app.py 的 add_app（`limit_addr` 表单字段），
# 界面上是「IP白名单(每行1个)」的 textarea，落到库里就是这段原始文本。
# 粘贴时常常混进逗号 / 分号 / 多余空格 / CRLF，这里统一按「空白 + 逗号 + 分号」切分。
_WHITE_LIST_SPLIT = re.compile(r'[\s,;]+')

# 请求头 / 代理可能给出的 IPv4-mapped IPv6 前缀（与 yf.getClientIp 的口径一致）
_V4_MAPPED = '::ffff:'

#: 审计动作名（便于日志检索；也便于用例断言）
AUDIT_ACTION = 'api.auth'

_log = logging.getLogger('yf.admin.login_check')


def _normalize_ip(value):
    """把一段 IP 文本规范化成可比较的形式；非法输入返回空串。

    `::ffff:1.2.3.4` 这类 IPv4-mapped 写法统一折叠成 `1.2.3.4`，
    否则「白名单里写 1.2.3.4、实际来源是 ::ffff:1.2.3.4」会误判为不在名单内。
    """
    text = (value or '').strip()
    if text.startswith(_V4_MAPPED):
        text = text[len(_V4_MAPPED):]
    if text == '':
        return ''
    try:
        return str(ipaddress.ip_address(text))
    except (TypeError, ValueError):
        return ''


def _parse_white_list(raw):
    """把库里 `white_list` 的原始文本解析成条目列表。

    :return: 条目列表；**空列表表示不限制来源 IP**（向后兼容旧数据）。
    """
    if raw is None:
        return []
    return [seg.strip() for seg in _WHITE_LIST_SPLIT.split(str(raw)) if seg.strip()]


def _ip_in_white_list(client_ip, raw_list):
    """来源 IP 是否命中白名单条目。

    条目既支持单个 IP（`1.2.3.4` / `2001:db8::1`），也顺带支持 CIDR 网段
    （`10.0.0.0/8`）——两者用 ipaddress 走同一条判断，写单个 IP 时等价于 /32、/128。
    空名单的「不限制」语义由 :func:`_api_credential_decision` 负责，这里只答「命中没命中」。
    """
    ip_text = _normalize_ip(client_ip)
    if ip_text == '':
        # 取不到来源 IP 时按「不命中」处理（fail closed），不给脏数据开后门
        return False

    ip_obj = ipaddress.ip_address(ip_text)
    for entry in _parse_white_list(raw_list):
        try:
            if '/' in entry:
                # 网段条目：原样交给 ipaddress（CIDR 里不做 ::ffff: 折叠）
                network = ipaddress.ip_network(entry, strict=False)
            else:
                # 单个 IP：先折叠 ::ffff: 前缀，再按 /32、/128 处理（与原口径一致）
                entry_ip = _normalize_ip(entry)
                if entry_ip == '':
                    continue
                network = ipaddress.ip_network(entry_ip, strict=False)
            if ip_obj in network:
                return True
        except (TypeError, ValueError):
            # 名单里的脏条目（拼错、留了说明文字）跳过，不影响其它条目
            continue
    return False


def _status_enabled(status):
    """凭据是否启用。`1` = 启用、`0` = 停用（见 thisdb/app.py:toggleAppStatus）。

    其它任何取值（None / 空串 / 脏数据）一律按**停用**处理：默认关门。
    """
    try:
        return int(status) == 1
    except (TypeError, ValueError):
        return False


def _secret_equal(given, expected):
    """定时安全地比较密钥（保持原实现的 hmac.compare_digest，防时序侧信道）。"""
    try:
        return hmac.compare_digest(given or '', expected or '')
    except TypeError:
        # 非 ASCII / 非字符串（脏数据）比较会抛 TypeError，直接判不相等
        return False


def _field(info, key):
    """从凭据记录里取字段，兼容 dict 与「类 dict」的查询结果。"""
    try:
        return info.get(key)
    except AttributeError:
        return None


def _api_credential_decision(app_id, app_secret, info, client_ip, open_flag):
    """API 凭据鉴权的**纯判定**：不查库、不写审计、不构造 Response。

    判定顺序（任何一步不过就停，且不泄露「哪一步之后的细节」给调用方响应）：
        面板 API 开关 → 凭据是否存在 → status 是否启用 → 来源 IP 是否在白名单内 → 密钥比对

    :param app_id:     请求头 `App-Id`
    :param app_secret: 请求头 `App-Secret`（**绝不进日志**）
    :param info:       thisdb.getAppByAppId() 的记录；凭据不存在时为 None
    :param client_ip:  来源 IP（由 yf.getClientIp() 取，勿用 request.remote_addr）
    :param open_flag:  面板设置 `panel_api.open`
    :return: (allowed: bool, reason: str)
             reason 取值：`ok` / `ok:white_list=empty` / `api_closed` /
             `app_not_found` / `status_disabled` / `ip_not_allowed:<ip>` / `bad_secret`
    """
    if not open_flag:
        # 面板 API 未开启：直接关门（而不是回落到登录态分支，避免「关掉 API 仍能凭凭据进来」）
        return False, 'api_closed'

    if info is None:
        return False, 'app_not_found'

    if not _status_enabled(_field(info, 'status')):
        # 被停用的凭据不得再拥有管理员等价权限
        return False, 'status_disabled'

    white_list = _field(info, 'white_list')
    white_list_empty = not _parse_white_list(white_list)
    if not white_list_empty and not _ip_in_white_list(client_ip, white_list):
        return False, 'ip_not_allowed:%s' % (client_ip or 'unknown')

    if not _secret_equal(app_secret, _field(info, 'app_secret')):
        return False, 'bad_secret'

    return True, 'ok:white_list=empty' if white_list_empty else 'ok'


def _write_api_audit(app_id, result, reason, client_ip):
    """写一条 API 鉴权审计（`api.auth`）。

    detail 里只放 app_id / 来源 IP / 判定原因，**绝不放 app_secret**。
    `core.audit.write_audit` 自身永不抛异常；这里再兜一层，只是防「审计模块导入失败」
    把接口打成 500。
    """
    detail = 'app_id=%s ip=%s reason=%s' % (app_id or 'unknown', client_ip or 'unknown', reason)
    try:
        import core.audit as audit
        audit.write_audit(AUDIT_ACTION, target=app_id or 'unknown', result=result, detail=detail)
    except Exception as exc:
        # `core.audit.write_audit` 自身永不抛异常；这里兜的是「审计模块导入失败」
        # （升级窗口期 / 文件缺失），只降级记日志，绝不把接口打成 500。
        _log.warning('api.auth 审计写入失败：%s', exc)


def panel_login_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):
        # 面板API调用检查
        app_id = request.headers.get('App-Id','')
        app_secret = request.headers.get('App-Secret','')
        if app_id != '' and app_secret != '':
            # 选项缺失时默认关闭（与初始化写入的 {'open': False} 口径一致）
            panel_api = thisdb.getOptionByJson('panel_api', default={"open":False})
            open_flag = bool(_field(panel_api, 'open')) if isinstance(panel_api, dict) else False

            info = None
            if open_flag:
                info = thisdb.getAppByAppId(app_id)

            client_ip = yf.getClientIp()
            allowed, reason = _api_credential_decision(app_id, app_secret, info, client_ip, open_flag)

            if allowed:
                _write_api_audit(app_id, 'ok', reason, client_ip)
                return func(*args, **kwargs)

            _write_api_audit(app_id, 'denied', reason, client_ip)
            if reason == 'app_not_found':
                # 保持原实现的 404（凭据不存在），其余一律 403 且不带任何响应体细节
                return Response(status=404)
            return Response(status=403)

        if not isLogined():
            unauthorized_status = thisdb.getOption('unauthorized_status', default='0')
            if unauthorized_status == '0':
                return render_template('default/path.html')
            return Response(status=int(unauthorized_status))

        return func(*args, **kwargs)
    return wrapper
