# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

"""明文 HTTP 告警判定（P2-2）。

## 为什么只做「告警」而不改默认值

面板在**未开启面板 SSL** 时，会话 Cookie（`SESSION_COOKIE_NAME=YF_VER_1_INSECURE`）走的是
明文 HTTP，链路上任何一跳都能嗅探到它 —— 拿到即等价于登录态。彻底的修法是
「默认自签 TLS + Secure Cookie」，但那会改变部署形态（首次访问的证书警告、
反代/端口/防火墙联动），不属于本任务，故本任务**只做显著告警**：

* 登录页 + 首页显著位置提示「当前为明文 HTTP，登录 Cookie 可被嗅探」；
* **不动** `web/admin/__init__.py` 里 `SESSION_COOKIE_SECURE` 的既有开关逻辑
  （仅当 `panel_ssl.open` 为真时才设 Secure），也**不动**部署默认值。

## 判定口径

「明文 HTTP」= 请求既不是 `https`，反代头也没声明已被 TLS 终止：

1. `request.is_secure`（Werkzeug 依据 `wsgi.url_scheme` 判定）为真 → 已加密；
2. `request.scheme == 'https'` → 已加密（与 1 同源，保留以防自定义 Request 子类）；
3. `X-Forwarded-Proto` 值含 `https` → 已加密（反代终止 TLS 的常见写法，
   多级代理链会写成 `https, http`，只要含 `https` 即认为链路已加密）；
4. `X-Forwarded-Scheme` 值含 `https` → 已加密（个别反代的写法）；
5. 以上都没有 → **明文**。

再叠加「面板 SSL 是否开启」：`thisdb.getOptionByJson('panel_ssl', default={'open':False})`
的 `open` 为真时，站点本身已由面板自带的 TLS 承载，此时不打明文告警
（口径与 `web/admin/__init__.py:113` 完全相同）。

## 可测性

:`func:`plain_http_warning_decision` 是**纯函数**：不碰 flask、不碰数据库，
全部输入靠参数传入，用例可逐条覆盖；取真实请求/配置的胶水在
:func:`plain_http_warning` 里，且任何取数失败都不阻断页面渲染。
"""

#: 转发头里代表「链路已加密」的标记（小写比较）
_HTTPS_MARK = 'https'

#: `panel_ssl` 选项缺失时的默认值（与 web/admin/__init__.py:113 同口径）
_PANEL_SSL_DEFAULT = {'open': False}


def _looks_https(value):
    """请求头/协议名是否表示「已加密」。

    只做「值里含 https」的判定：反代可能把多级链路串成 `https, http`、
    也可能带端口写成 `https:443`，两种都应认为链路已被 TLS 终止。
    """
    if not value:
        return False
    try:
        return _HTTPS_MARK in str(value).strip().lower()
    except Exception:
        return False


def _panel_ssl_open(panel_ssl):
    """`panel_ssl` 配置里 `open` 是否为真。

    `panel_ssl` 传 `None` / 非 dict（选项缺失、读库异常）一律按默认
    `{'open': False}` 处理 —— 「配置读不到」不能当成「已经加密」，
    否则告警会静默消失（这正是本任务要避免的失效模式）。
    """
    if isinstance(panel_ssl, dict):
        return bool(panel_ssl.get('open'))
    return bool(_PANEL_SSL_DEFAULT.get('open'))


def plain_http_warning_decision(is_secure=False, scheme='', forwarded_proto='',
                                forwarded_scheme='', panel_ssl=None):
    """纯函数：是否需要给页面打「明文 HTTP」告警。

    :param is_secure: `request.is_secure`
    :param scheme: `request.scheme`（`http` / `https`）
    :param forwarded_proto: `X-Forwarded-Proto` 头原值，缺省传 `''` / `None`
    :param forwarded_scheme: `X-Forwarded-Scheme` 头原值，缺省传 `''` / `None`
    :param panel_ssl: `thisdb.getOptionByJson('panel_ssl', default={'open':False})`
                      的结果；`None` / 非 dict 视为「选项缺失」，按默认处理
    :return: `(should_warn, https_hint)`
             * `should_warn` —— True 表示要在页面上显示明文告警；
             * `https_hint`  —— 「凭什么判为已加密」的短标记，仅用于日志/排查，
               告警时为 `''`。
    """
    if is_secure:
        return False, 'is_secure'
    if _looks_https(scheme):
        return False, 'scheme'
    if _looks_https(forwarded_proto):
        return False, 'x-forwarded-proto'
    if _looks_https(forwarded_scheme):
        return False, 'x-forwarded-scheme'
    if _panel_ssl_open(panel_ssl):
        return False, 'panel_ssl'
    return True, ''


def _read_panel_ssl_option():
    """读 `panel_ssl` 选项；读不到（含 DB 不可用）按默认 `{'open': False}`。"""
    try:
        import thisdb
        return thisdb.getOptionByJson('panel_ssl', default=dict(_PANEL_SSL_DEFAULT))
    except Exception:
        return dict(_PANEL_SSL_DEFAULT)


def plain_http_warning(request_obj=None, panel_ssl=None):
    """从当前请求 + 面板配置取数，返回 `(should_warn, https_hint)`。

    :param request_obj: 传入 flask 的 `request`（或任何有 `is_secure` /
                        `scheme` / `headers` 的对象）；`None` 时自动取 flask 的
                        request 代理，取不到就当作「没有请求信息」→ 按明文判。
    :param panel_ssl: 显式传入 `panel_ssl` 配置（用例/调试用）；`None` 时读库。
    """
    if request_obj is None:
        try:
            from flask import request as request_obj
        except Exception:
            request_obj = None

    is_secure = False
    scheme = ''
    forwarded_proto = ''
    forwarded_scheme = ''

    if request_obj is not None:
        try:
            is_secure = bool(request_obj.is_secure)
        except Exception:
            is_secure = False
        try:
            scheme = request_obj.scheme or ''
        except Exception:
            scheme = ''
        try:
            headers = request_obj.headers
            forwarded_proto = headers.get('X-Forwarded-Proto', '') or ''
            forwarded_scheme = headers.get('X-Forwarded-Scheme', '') or ''
        except Exception:
            forwarded_proto = ''
            forwarded_scheme = ''

    if panel_ssl is None:
        panel_ssl = _read_panel_ssl_option()

    return plain_http_warning_decision(
        is_secure=is_secure,
        scheme=scheme,
        forwarded_proto=forwarded_proto,
        forwarded_scheme=forwarded_scheme,
        panel_ssl=panel_ssl,
    )


def plain_http_warning_flag(request_obj=None, panel_ssl=None):
    """模板上下文用的布尔标志（模板里 `{% if plain_http_warning %}`）。"""
    return plain_http_warning(request_obj=request_obj, panel_ssl=panel_ssl)[0]
