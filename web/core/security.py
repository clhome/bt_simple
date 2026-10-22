# coding=utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 作者: midoks & yufeng tec
# ---------------------------------------------------------------------------------
# 请求安全判定（纯函数，无 Flask 依赖，便于单测与复用）
# ---------------------------------------------------------------------------------
"""
把「这个请求该不该放行」的判定从 Flask 上下文里抽出来，理由：

1. **可单测**：真值表（token × referer × 豁免）能直接跑，不依赖起一个 Flask app；
2. **可复用**：其它入口（如未来的独立 API 网关）能用同一套规则；
3. **口径集中**：CSRF 策略只有一处，改口径不会漏改。

策略（OR 语义，刻意保守）：
    非安全方法（POST/PUT/PATCH/DELETE）只要满足以下**任一**条件即放行：
      a. `api_verified=True` —— 请求头 `App-Id`/`App-Secret` **真的**通过了 API 凭据鉴权
         （判定由调用方做，本函数只消费结论；不属于浏览器 CSRF 模型）；
      b. 命中豁免路径（`/hook` 自带 access_key 鉴权、`/.well-known/` 是 ACME 挑战、
         `POST */quick_login` 是跨面板快捷登录，凭据在 body 现验 + 一次性 nonce）；
      c. 双提交 Token 正确；
      d. Referer 或 Origin 的 host 与本机一致。
    四者都不满足 -> 拒绝。

为什么 a 是「鉴权结论」而不是「带头」：
    这里曾经是「带 `App-Id` 头就放行」，等于任何跨站页面只要自己加上这个头
    就能绕过整个 CSRF 防护（头是客户端随便填的，不是凭据）。现在只认调用方
    `api_verified=True` 的结论，参数 `has_app_id` 退化成纯信息（仅用于日志/审计），
    不再参与任何放行判定。

为什么是 OR 而不是「必须 Token」：
    现状只有 Referer 校验，且「Referer/Origin 都为空即拒绝」会误伤
    隐私插件/反向代理剥头的正常用户。先引入 Token 作为**额外**可接受的凭据，
    保证任何今天能过的请求明天还能过（零回归），再据日志决定何时收紧为强制 Token。
"""

import hmac
from urllib.parse import urlparse

UNSAFE_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')

#: 自带鉴权、不属于浏览器 CSRF 模型的路径
CSRF_EXEMPT_PATHS = ('/hook',)

#: 豁免前缀（ACME 挑战等）
CSRF_EXEMPT_PREFIXES = ('/.well-known/',)

#: 跨面板快捷登录端点后缀（仅 POST）。源面板→目标面板天然跨源，拿不到目标的
#: 会话 CSRF token；该端点凭据在 body 里现验 + 一次性 nonce + 统一限流，且旧实现
#: `GET ?login=` 本就属 CSRF 豁免（安全方法），故豁免不扩大暴露面。
CSRF_EXEMPT_POST_SUFFIX = '/quick_login'


def netloc_of(url_str):
    """取 URL 的 host:port（容忍缺 scheme 的写法）。"""
    if not url_str:
        return ''
    if '://' not in url_str:
        url_str = 'http://' + url_str
    try:
        return urlparse(url_str).netloc
    except Exception:
        return ''


def _is_exempt_path(path, method=None):
    if path in CSRF_EXEMPT_PATHS:
        return True
    if any(path.startswith(p) for p in CSRF_EXEMPT_PREFIXES):
        return True
    # 跨面板快捷登录：**只**豁免 POST 且路径恰以 /quick_login 结尾。
    # 用精确后缀而非 `in`/前缀，避免把 /quick_login_evil、/x/quick_login/extra 一起放进来。
    if (method or '').upper() == 'POST' and path.endswith(CSRF_EXEMPT_POST_SUFFIX):
        return True
    return False


def csrf_decision(method, path, host, referer='', origin='',
                  token_expected='', token_supplied='', has_app_id=False,
                  api_verified=False):
    """判定请求是否通过 CSRF 检查。

    :param api_verified: 请求头凭据是否**真的**通过 API 鉴权（由调用方用
                         App-Id/App-Secret 现验得出）。只有它为真才豁免。
    :param has_app_id:   **仅信息用**：请求是否带了 `App-Id` 头。刻意不参与判定，
                         避免再退回「头存在即放行」的捷径。
    :return: (allowed: bool, reason: str)
    """
    method = (method or 'GET').upper()
    if method not in UNSAFE_METHODS:
        return True, 'safe-method'
    if api_verified:
        # 已通过凭据鉴权：自带身份证明，与 CSRF token 同级的「已证明来者是谁」
        return True, 'api-authenticated'
    if _is_exempt_path(path or '', method):
        return True, 'exempt-path'

    token_ok = False
    if token_expected and token_supplied:
        try:
            token_ok = hmac.compare_digest(str(token_supplied), str(token_expected))
        except Exception:
            token_ok = False

    referer_ok = False
    if referer:
        referer_ok = netloc_of(referer) == host
    elif origin:
        referer_ok = netloc_of(origin) == host

    if token_ok and referer_ok:
        return True, 'token+referer'
    if token_ok:
        return True, 'token-only'
    if referer_ok:
        return True, 'referer-only'
    return False, 'no-proof'


def extract_supplied_token(headers, form):
    """从请求中取出客户端提交的 Token：header 优先，其次表单字段。"""
    try:
        value = headers.get('X-CSRF-Token', '') if headers else ''
    except Exception:
        value = ''
    if not value and form:
        try:
            value = form.get('csrf_token', '')
        except Exception:
            value = ''
    return value or ''
