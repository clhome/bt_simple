# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import time

from admin import session
import thisdb
import core.panel_session as panel_session

_login_cache = {}
_LOGIN_CACHE_TTL = 20        # 登录状态短期缓存（秒）
_LOGIN_CACHE_MAX = 4096      # 缓存条目上限，超过则触发淘汰
_login_cache_last_prune = 0


def invalidate_login_cache(session_id=None):
    """撤销会话后立即失效进程内登录缓存。

    没有这一步的话，撤销最长要等 `_LOGIN_CACHE_TTL`（20s）才生效，
    达不到「B 设备下一次请求即被登出」的验收标准。
    多 worker 场景下其他进程仍有 ≤20s 延迟（面板默认 workers=1）。
    """
    if session_id:
        _login_cache.pop(session_id, None)
    else:
        _login_cache.clear()


def _client_ip():
    try:
        import core.yf as yf
        return yf.getClientIp()
    except Exception:
        try:
            from flask import request
            return request.remote_addr or ''
        except Exception:
            return ''


def _client_ua():
    try:
        from flask import request
        return request.headers.get('User-Agent', '') or ''
    except Exception:
        return ''


def _prune_login_cache(now_time):
    """定时清理过期的登录状态缓存，避免长驻进程内存单调增长。"""
    global _login_cache_last_prune
    if now_time - _login_cache_last_prune < 60 and len(_login_cache) < _LOGIN_CACHE_MAX:
        return
    _login_cache_last_prune = now_time
    for key in [k for k, v in _login_cache.items() if now_time - v[0] >= _LOGIN_CACHE_TTL]:
        _login_cache.pop(key, None)
    if len(_login_cache) > _LOGIN_CACHE_MAX:
        # 兜底：淘汰最旧的一半
        stale = sorted(_login_cache, key=lambda k: _login_cache[k][0])
        for key in stale[:len(stale) // 2]:
            _login_cache.pop(key, None)

def _check_session_expiry(now_time):
    """Cookie 内的时间戳校验（与 PERMANENT_SESSION_LIFETIME 统一为 1 天）。"""
    if 'overdue' in session and now_time > session['overdue']:
        session.clear()
        return False
    if 'tmp_login_expire' in session and now_time > int(session['tmp_login_expire']):
        session.clear()
        return False
    return True


def isLogined():
    if 'login' in session  and session['login'] == True and 'username' in session:
        username = session['username']
        now_time = int(time.time())
        _prune_login_cache(now_time)

        session_id = session.get('session_id') or ''

        # ---- 服务端会话校验：这是「可撤销 / 可强制下线」的落点 ----
        # 先看 20s 短期缓存；撤销动作会主动清缓存（invalidate_login_cache），
        # 因此缓存不会拖慢「B 设备下一次请求即被登出」。
        # 表不可用时 touch() 返回 True（fail-open），行为退回纯签名 Cookie。
        if session_id:
            cached = _login_cache.get(session_id)
            if cached and now_time - cached[0] < _LOGIN_CACHE_TTL:
                if not cached[1]:
                    return False
                return _check_session_expiry(now_time)

            valid, _reason = panel_session.touch(session_id)
            if not valid:
                session.clear()
                _login_cache.pop(session_id, None)
                return False

        info = thisdb.getUserByName(username)
        if info is None:
            if session_id:
                _login_cache[session_id] = (now_time, False)
            return False

        # print(userInfo)
        if info['name'] != session['username']:
            if session_id:
                _login_cache[session_id] = (now_time, False)
            return False

        if not _check_session_expiry(now_time):
            return False

        # 升级前的旧 Cookie（没有服务端副本）：一次性登记，纳入可撤销管理。
        # create() 只有在确认落库成功时才返回 session_id（否则保持旧行为）。
        if not session_id:
            session_id = panel_session.create(
                info.get('id') or 0, username, _client_ip(), _client_ua(),
                expires_at=session.get('overdue') or (now_time + panel_session.SESSION_TTL))
            if session_id:
                session['session_id'] = session_id

        if session_id:
            _login_cache[session_id] = (now_time, True)
        return True
    return False