# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 作者: midoks & yufeng tec
# ---------------------------------------------------------------------------------
# 登录失败限流（IP + 账号双维度，落库）
# ---------------------------------------------------------------------------------
"""
为什么要把计数从进程内存搬到数据库：

    旧实现用 `admin.cache`（FileSystemCache / 进程内存）按 **IP** 单维度计数：

      * **无账号维度** —— 攻击者换 IP 撞同一个账号，或用一个 IP 撞很多账号，都能绕过；
      * 多 worker / 重启后计数不一致（FileSystemCache 虽跨进程，但会被清、会丢）。

    现在改为「IP 与账号各记一份，任一超限即锁定」，并落 `panel_login_failure` 表，
    重启与多 worker 下口径一致。

降级原则（与 panel_session 一致）：

    表不可用或查询异常时，自动退回**进程内存**计数（即旧行为），
    保证限流不会因为库没建好而彻底消失，也不会因此把登录打死。

降级的**可见化**（P2-8）：

    上面这条 fail-open 取舍本身**不改**（表不可用不能把登录全部打死，那等于
    可用性事故），但「退化成进程内存」意味着多 worker 下每个进程各算各的、
    计数不再共享 —— 也就是「爆破防护 / 改密码踢下线」会**静默失效**。
    因此新增 `status()`：把「现在到底是 db 还是 memory、为什么」暴露给面板首页，
    由首页显著告警。本模块的 `is_banned()` / 计数写入行为**一行未动**。
"""

import logging
import threading
import time

log = logging.getLogger('yf.login_guard')

#: 连续失败次数上限
LOGIN_FAIL_LIMIT = 5
#: 失败计数窗口（秒）
LOGIN_LIMIT_TTL = 10000
#: 触发上限后的封禁时长（秒）
LOGIN_BAN_TTL = 3600

MAX_VALUE_LEN = 128

#: `status()` 结果的短时缓存（秒）。首页每次刷新都会问一次状态，
#: 探表（`sqlite_master` + 一次最小读）不必每秒都做；5s 内复用上一个判定结果。
STATUS_CACHE_TTL = 5

#: 探测结果缓存：[是否就绪, 探测时刻]（60s 内复用，和 panel_session 同口径）
_READY_CACHE = [None, 0]
#: 最近一次真实探测的**理由**（`_table_ready()` 内部判定口径，供 `status()` 说明降级原因）
_READY_REASON = ['']
#: `status()` 短时缓存：{'data': dict|None, 'ts': int}
_STATUS_CACHE = {'data': None, 'ts': 0}
_STATUS_LOCK = threading.Lock()

_MEM = {}
_MEM_LOCK = threading.Lock()

#: 就绪理由（`status()['reason']` 的 db 态取值）
_REASON_OK = 'ok'
#: 表不存在（未初始化 / 迁移未执行）
_REASON_NO_TABLE = 'panel_login_failure 表不存在（未初始化或迁移未执行）'
#: 兜底理由：探测被替身绕过、或缓存里没有理由时使用（保证 memory 态 reason 永远非空）
_REASON_DEGRADED = 'panel_login_failure 表不可用（未初始化或探测未通过），已降级为进程内计数'


def _now():
    return int(time.time())


def _clip(value):
    return ('' if value is None else str(value))[:MAX_VALUE_LEN]


def _targets(ip=None, username=None):
    """返回需要计数的 (kind, value) 列表 —— 双维度都在这里定义。"""
    out = []
    ip = _clip(ip)
    if ip:
        out.append(('ip', ip))
    username = _clip(username)
    if username:
        out.append(('user', username))
    return out


def _table_ready():
    """`panel_login_failure` 表是否就绪（带 60s 缓存）。

    判定理由写进 `_READY_REASON`，供 `status()` 回答「为什么降级」；
    返回值口径与改造前完全一致（bool），限流语义不受影响。
    """
    now = _now()
    cached, ts = _READY_CACHE
    if cached is not None and now - ts < 60:
        return cached
    ready = False
    try:
        import core.yf as yf
        cur = yf.M().query("SELECT 1 FROM sqlite_master WHERE type='table' "
                           "AND name='panel_login_failure' LIMIT 1")
        if isinstance(cur, str):
            _READY_REASON[0] = '查询 sqlite_master 失败：%s' % cur
        else:
            ready = bool(cur.fetchall())
            _READY_REASON[0] = _REASON_OK if ready else _REASON_NO_TABLE
    except Exception as exc:
        log.warning('探测 panel_login_failure 表失败（按不可用处理）：%s', exc)
        ready = False
        _READY_REASON[0] = '探测 panel_login_failure 表异常：%s' % exc
    _READY_CACHE[0] = ready
    _READY_CACHE[1] = now
    return ready


def _query(sql, params=()):
    import core.yf as yf
    cur = yf.M().query(sql, params)
    if isinstance(cur, str):
        log.warning('登录限流查询失败：%s', cur)
        return None
    try:
        return [tuple(r) for r in cur.fetchall()]
    except Exception as exc:
        log.warning('登录限流查询结果读取失败：%s', exc)
        return None


def _execute(sql, params=()):
    import core.yf as yf
    result = yf.M().execute(sql, params)
    if isinstance(result, str):
        log.warning('登录限流写库失败：%s', result)
        return None
    return result


# ---------------------------------------------------------------- 内存降级

def _mem_bump(kind, value, now):
    with _MEM_LOCK:
        item = _MEM.get((kind, value))
        if item is None or now - item['last'] > LOGIN_LIMIT_TTL:
            item = {'count': 0, 'last': now, 'banned_until': 0}
        item['count'] += 1
        item['last'] = now
        if item['count'] >= LOGIN_FAIL_LIMIT:
            item['banned_until'] = now + LOGIN_BAN_TTL
        _MEM[(kind, value)] = item
        return item['count'], item['banned_until'] > now


def _mem_banned(kind, value, now):
    with _MEM_LOCK:
        item = _MEM.get((kind, value))
        return bool(item and item['banned_until'] > now)


def _mem_count(kind, value, now):
    with _MEM_LOCK:
        item = _MEM.get((kind, value))
        if item is None or now - item['last'] > LOGIN_LIMIT_TTL:
            return 0
        return item['count']


def _mem_reset(kind, value):
    with _MEM_LOCK:
        _MEM.pop((kind, value), None)


# ---------------------------------------------------------------- 落库实现

def _bump(kind, value, now):
    """记录一次失败，返回 (窗口内计数, 是否已封禁)。"""
    rows = _query('SELECT fail_count, last_at, banned_until FROM panel_login_failure '
                  'WHERE kind=? AND value=? LIMIT 1', (kind, value))
    if rows is None:
        return _mem_bump(kind, value, now)
    if rows:
        count = int(rows[0][0] or 0)
        last_at = int(rows[0][1] or 0)
        banned_until = int(rows[0][2] or 0)
        if now - last_at > LOGIN_LIMIT_TTL:
            count = 0
            banned_until = 0
        count += 1
        if count >= LOGIN_FAIL_LIMIT:
            banned_until = now + LOGIN_BAN_TTL
        _execute('UPDATE panel_login_failure SET fail_count=?, last_at=?, banned_until=? '
                 'WHERE kind=? AND value=?', (count, now, banned_until, kind, value))
        return count, banned_until > now
    count = 1
    banned_until = now + LOGIN_BAN_TTL if count >= LOGIN_FAIL_LIMIT else 0
    try:
        import core.yf as yf
        last_id = yf.M('panel_login_failure').insert({
            'kind': kind, 'value': value, 'fail_count': count,
            'first_at': now, 'last_at': now, 'banned_until': banned_until,
        })
    except Exception as exc:
        log.warning('登录失败计数落库异常，退回内存计数：%s', exc)
        return _mem_bump(kind, value, now)
    if not last_id:
        return _mem_bump(kind, value, now)
    return count, banned_until > now


def is_banned(ip=None, username=None):
    """是否处于封禁中（IP 或账号任一命中）。"""
    now = _now()
    for kind, value in _targets(ip, username):
        rows = _query('SELECT banned_until FROM panel_login_failure '
                      'WHERE kind=? AND value=? LIMIT 1', (kind, value))
        if rows is None:
            if _mem_banned(kind, value, now):
                return True
            continue
        if rows and int(rows[0][0] or 0) > now:
            return True
    return False


def register_failure(ip=None, username=None):
    """记录一次失败。返回 (是否已封禁, 剩余可尝试次数)。"""
    now = _now()
    blocked = False
    remain = LOGIN_FAIL_LIMIT
    for kind, value in _targets(ip, username):
        count, banned = _bump(kind, value, now)
        if banned:
            blocked = True
        remain = min(remain, max(0, LOGIN_FAIL_LIMIT - count))
    return blocked, remain


def failure_count(ip=None, username=None):
    """窗口内最大失败次数（用于「有失败记录则强制验证码」）；无记录返回 0。"""
    now = _now()
    best = 0
    for kind, value in _targets(ip, username):
        rows = _query('SELECT fail_count, last_at FROM panel_login_failure '
                      'WHERE kind=? AND value=? LIMIT 1', (kind, value))
        if rows is None:
            best = max(best, _mem_count(kind, value, now))
            continue
        if not rows:
            continue
        count = int(rows[0][0] or 0)
        last_at = int(rows[0][1] or 0)
        if now - last_at > LOGIN_LIMIT_TTL:
            count = 0
        best = max(best, count)
    return best


def reset(ip=None, username=None):
    """登录成功（或管理员解封）后清空两个维度的失败计数。"""
    for kind, value in _targets(ip, username):
        _mem_reset(kind, value)
        _execute('DELETE FROM panel_login_failure WHERE kind=? AND value=?', (kind, value))


def reset_cache():
    """清空探测缓存（测试用）。"""
    _READY_CACHE[0] = None
    _READY_CACHE[1] = 0
    _READY_REASON[0] = ''
    _reset_status_cache()


# ---------------------------------------------------------------- 状态可见化


def _status_dict(ready, reason):
    """组装 `status()` 的返回结构（固定四个键，前端可放心取值）。"""
    return {
        'table_ready': bool(ready),
        'backend': 'db' if ready else 'memory',
        'reason': reason or _REASON_DEGRADED,
        'checked_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }


def _probe_status():
    """真正探一次后端可用性，返回 `_status_dict()` 结构。

    两段判定：
      1. 表在不在（`_table_ready()`，理由取自它写下的 `_READY_REASON`）；
      2. 表在**不代表能读** —— 锁表 / 库损坏时 `_query()` 会拿到错误串并返回 None，
         此时依旧按 memory 态上报（限流实际上已经在走内存计数了）。

    任何异常都收敛成**本函数的返回值**，绝不向上抛：这个函数会被首页渲染路径调用。
    """
    try:
        ready = bool(_table_ready())
    except Exception as exc:
        log.warning('登录限流状态探测异常（按降级处理）：%s', exc)
        return _status_dict(False, '状态探测异常：%s' % exc)

    if not ready:
        reason = _READY_REASON[0]
        # 探测被替身绕过 / 缓存里没留理由时，用兜底文案，保证 reason 永远非空
        if not reason or reason == _REASON_OK:
            reason = _REASON_DEGRADED
        return _status_dict(False, reason)

    try:
        if _query('SELECT 1 FROM panel_login_failure LIMIT 1') is None:
            return _status_dict(False, '登录限流查询不可用（读取 panel_login_failure 失败）')
    except Exception as exc:
        log.warning('登录限流状态探测：查询异常（按降级处理）：%s', exc)
        return _status_dict(False, '查询 panel_login_failure 异常：%s' % exc)

    return _status_dict(True, _REASON_OK)


def _reset_status_cache():
    """清空 `status()` 的短时缓存（测试 / 修复后手动刷新用）。"""
    with _STATUS_LOCK:
        _STATUS_CACHE['data'] = None
        _STATUS_CACHE['ts'] = 0


def status():
    """登录限流后端状态（只读、绝不抛异常、5s 短时缓存）。

    返回::

        {'table_ready': bool, 'backend': 'db' | 'memory',
         'reason': str, 'checked_at': str}

    `backend == 'memory'` 表示计数已退化为**进程内**实现（多 worker 下限流失效），
    面板首页据此显示告警。本函数**不改变**任何限流行为，只做可见化。
    """
    now = _now()
    with _STATUS_LOCK:
        cached = _STATUS_CACHE['data']
        if cached is not None and now - _STATUS_CACHE['ts'] < STATUS_CACHE_TTL:
            return dict(cached)
    try:
        fresh = _probe_status()
    except Exception as exc:      # 兜底：可见化功能绝不允许影响登录/首页
        log.warning('登录限流状态探测失败（按降级处理）：%s', exc)
        fresh = _status_dict(False, '状态探测失败：%s' % exc)
    with _STATUS_LOCK:
        _STATUS_CACHE['data'] = fresh
        _STATUS_CACHE['ts'] = _now()
    return dict(fresh)
