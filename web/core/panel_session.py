# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 作者: midoks & yufeng tec
# ---------------------------------------------------------------------------------
# 服务端会话存储（可撤销 / 可列举 / 可强制下线）
# ---------------------------------------------------------------------------------
"""
为什么需要它：

    历史上登录态只靠 Flask 的**签名 Cookie** 承载（`_login_success` 往 session 写
    `login/username/overdue`）。签名只能证明「这个 Cookie 是我发的」，无法回答
    「它现在还算数吗」—— 于是：

      * 改密码后**无法把别的设备踢下线**（Cookie 在客户端，服务端无副本可吊销）；
      * 看不到「当前有几台设备登录、从哪个 IP」；
      * 账号泄露后唯一的止损手段是「改密码 + 等 Cookie 过期」。

    本模块为每个登录态在 `panel_session` 表里存一条**服务端副本**，
    Cookie 里只放不透明的 `session_id`。校验时查服务端副本，因此可以随时撤销。

降级原则（fail-open）：

    会话表不可用（未建成 / 查询报错）时，`touch()` 返回 True，行为**退回签名
    Cookie 那套**，保证不会把所有人锁在门外；只有「表可用且明确查不到 / 已撤销 /
    已过期」才判为失效（fail-closed）。

    与之对应，`create()` 只在**确认落库成功**时才返回 session_id；
    否则返回空串，调用方保持旧 Cookie 行为（而不是写一个查不到的服务端会话，
    那样会在表刚就绪的瞬间把用户踢下线）。
"""

import logging
import secrets
import threading
import time

log = logging.getLogger('yf.session')

#: 与服务端会话寿命一致（对应 app.config['PERMANENT_SESSION_LIFETIME'] = 1 天）
SESSION_TTL = 24 * 3600
#: last_seen 写库节流（秒）。请求频率再高也不至于每条都写库。
TOUCH_INTERVAL = 60
#: 过期 / 已撤销会话的清理节流（秒）
PRUNE_INTERVAL = 3600
#: 过期 / 已撤销记录保留多久后物理删除（留出排查窗口）
PRUNE_RETAIN = 7 * 24 * 3600

MAX_IP_LEN = 64
MAX_UA_LEN = 255
MAX_NAME_LEN = 64

_READY_CACHE = [None, 0]        # [bool, ts]
_PRUNE_TS = [0]
_LOCK = threading.Lock()


def _now():
    return int(time.time())


def new_session_id():
    """不透明、高熵的会话标识（写进签名 Cookie）。"""
    return secrets.token_urlsafe(32)


def _clip(value, limit):
    return ('' if value is None else str(value))[:limit]


def _table_ready():
    """会话表是否已就绪（带 60s 缓存，避免每次请求都查 schema）。"""
    now = _now()
    cached, ts = _READY_CACHE
    if cached is not None and now - ts < 60:
        return cached
    ready = False
    try:
        import core.yf as yf
        cur = yf.M().query(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='panel_session' LIMIT 1")
        if not isinstance(cur, str):
            ready = bool(cur.fetchall())
    except Exception as exc:
        log.warning('探测 panel_session 表失败（按不可用处理）：%s', exc)
        ready = False
    _READY_CACHE[0] = ready
    _READY_CACHE[1] = now
    return ready


def _query(sql, params=()):
    """执行 SELECT，返回行列表；出错返回 None（与「查无结果」区分开）。"""
    import core.yf as yf
    cur = yf.M().query(sql, params)
    if isinstance(cur, str):
        log.warning('会话查询失败：%s', cur)
        return None
    try:
        return [tuple(r) for r in cur.fetchall()]
    except Exception as exc:
        log.warning('会话查询结果读取失败：%s', exc)
        return None


def _execute(sql, params=()):
    """执行写语句，返回受影响行数；出错返回 None。"""
    import core.yf as yf
    result = yf.M().execute(sql, params)
    if isinstance(result, str):
        log.warning('会话写库失败：%s', result)
        return None
    return result


def create(uid, username, ip='', ua='', expires_at=None):
    """登记一个服务端会话。

    :return: session_id；**只有确认落库成功才返回非空串**（见模块 docstring 的降级原则）
    """
    sid = new_session_id()
    now = _now()
    if not expires_at:
        expires_at = now + SESSION_TTL
    try:
        import core.yf as yf
        last_id = yf.M('panel_session').insert({
            'session_id': sid,
            'uid': int(uid or 0),
            'username': _clip(username, MAX_NAME_LEN),
            'ip': _clip(ip, MAX_IP_LEN),
            'ua': _clip(ua, MAX_UA_LEN),
            'created_at': now,
            'last_seen': now,
            'expires_at': int(expires_at),
            'revoked': 0,
        })
    except Exception as exc:
        log.warning('会话登记失败（本次降级为纯 Cookie 会话）：%s', exc)
        return ''
    if not last_id:
        return ''
    _maybe_prune(now)
    return sid


def touch(session_id):
    """校验会话并顺带刷新 last_seen。

    :return: (valid: bool, reason: str)
        ('unknown', 'disabled')  —— 表不可用 / 查询异常，调用方按放行处理
        ('revoked', ...)         —— 已被撤销
        ('expired', ...)         —— 已过期
        ('ok', ...)              —— 有效
    """
    if not session_id:
        return True, 'unknown'
    rows = _query('SELECT uid, revoked, expires_at, last_seen '
                  'FROM panel_session WHERE session_id=? LIMIT 1', (session_id,))
    if rows is None:
        # 查询异常：无法判定 -> 放行（fail-open）
        return True, 'unknown'
    if not rows:
        if not _table_ready():
            return True, 'unknown'
        return False, 'revoked'
    row = rows[0]
    revoked = int(row[1] or 0) if row[1] is not None else 0
    expires_at = int(row[2] or 0)
    last_seen = int(row[3] or 0)
    now = _now()
    if revoked:
        return False, 'revoked'
    if expires_at and now > expires_at:
        return False, 'expired'
    if now - last_seen >= TOUCH_INTERVAL:
        _execute('UPDATE panel_session SET last_seen=? WHERE session_id=?', (now, session_id))
    return True, 'ok'


def revoke(session_id):
    """撤销单个会话。返回受影响行数（表不可用时返回 None）。"""
    if not session_id:
        return 0
    return _execute('UPDATE panel_session SET revoked=1 WHERE session_id=?', (session_id,))


def revoke_user_sessions(uid, keep_session_id=None):
    """撤销某个用户的全部会话；`keep_session_id` 用于「保留当前设备」。"""
    try:
        uid = int(uid)
    except Exception:
        return 0
    if keep_session_id:
        return _execute('UPDATE panel_session SET revoked=1 WHERE uid=? AND session_id<>?',
                        (uid, keep_session_id))
    return _execute('UPDATE panel_session SET revoked=1 WHERE uid=?', (uid,))


def list_sessions(uid, include_revoked=False, limit=50):
    """列出某用户的会话，按最后活跃时间倒序。返回 list[dict]。"""
    try:
        uid = int(uid)
    except Exception:
        return []
    sql = ('SELECT session_id, uid, username, ip, ua, created_at, last_seen, '
           'expires_at, revoked FROM panel_session WHERE uid=?')
    if not include_revoked:
        sql += ' AND revoked=0'
    sql += ' ORDER BY last_seen DESC LIMIT %d' % max(1, min(int(limit or 50), 200))
    rows = _query(sql, (uid,))
    if rows is None:
        return []
    keys = ('session_id', 'uid', 'username', 'ip', 'ua',
            'created_at', 'last_seen', 'expires_at', 'revoked')
    return [dict(zip(keys, r)) for r in rows]


def get(session_id):
    """按 session_id 取单条（含已撤销），不存在返回 None。"""
    if not session_id:
        return None
    rows = _query('SELECT session_id, uid, username, ip, ua, created_at, last_seen, '
                  'expires_at, revoked FROM panel_session WHERE session_id=? LIMIT 1',
                  (session_id,))
    if not rows:
        return None
    keys = ('session_id', 'uid', 'username', 'ip', 'ua',
            'created_at', 'last_seen', 'expires_at', 'revoked')
    return dict(zip(keys, rows[0]))


def prune(now=None):
    """物理清理「早已过期或撤销」的历史行，避免表无限增长。返回删除行数。"""
    now = now or _now()
    cutoff = now - PRUNE_RETAIN
    return _execute('DELETE FROM panel_session WHERE '
                    '(expires_at>0 AND expires_at<?) OR (revoked=1 AND last_seen<?)',
                    (cutoff, cutoff)) or 0


def _maybe_prune(now):
    """登录时顺带节流清理，不额外起线程/定时器。"""
    with _LOCK:
        if now - _PRUNE_TS[0] < PRUNE_INTERVAL:
            return
        _PRUNE_TS[0] = now
    try:
        prune(now)
    except Exception as exc:
        log.warning('会话清理失败（不影响登录）：%s', exc)


def reset_cache():
    """清空探测缓存（测试用）。"""
    _READY_CACHE[0] = None
    _READY_CACHE[1] = 0
    _PRUNE_TS[0] = 0
