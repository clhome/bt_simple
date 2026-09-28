# coding=utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 作者: midoks & yufeng tec
# ---------------------------------------------------------------------------------
# 审计流水（append-only + 哈希链）
# ---------------------------------------------------------------------------------
"""
与 `logs` 表的区别（为什么不能复用）：

    `logs` 是**面向界面**的操作日志：内容会被 i18n 翻译层改写后展示，
    历史上还能被 `del_panel_logs` 一键物理清空。
    把它当审计依据有三个硬伤：① 没有操作者身份（`writeLog` 硬编码 uid=0）；
    ② 没有来源 IP / UA / 请求指纹；③ 可被一键抹掉。

    `panel_audit` 是**面向合规**的审计流水：只追加、不修改、不删除，
    并带哈希链 —— 任何中间行被改动或删除，后续行的校验都会断，
    从而具备「篡改可发现」的性质（而不是只靠一句口头承诺）。

哈希链：
    prev_hash = 上一条的 row_hash（首条为 GENESIS）
    row_hash  = sha256(prev_hash + '|' + 规范化字段拼接)

    并发写入的说明：面板默认 workers=1（Flask-SocketIO 约束），
    同进程内用锁串行化；多 worker 场景下极端并发可能产生分叉，
    `verify_chain()` 会把分叉报出来（而不是静默通过）。
"""

import hashlib
import logging
import threading

log = logging.getLogger('yf.audit')

GENESIS = 'GENESIS'

#: 字段长度上限 —— 审计表不能变成「谁都能撑爆」的地方
MAX_LEN = {
    'username': 64,
    'ip': 64,
    'ua': 255,
    'method': 10,
    'path': 255,
    'action': 64,
    'target': 255,
    'result': 16,
    'detail': 2000,
    'request_id': 64,
}

_LOCK = threading.Lock()

#: 需要参与哈希计算的字段（顺序固定！改动会让历史链失效）
_HASH_FIELDS = ('ts', 'uid', 'username', 'ip', 'ua', 'method', 'path',
                'action', 'target', 'result', 'detail', 'request_id')


def _clip(value, key):
    if value is None:
        value = ''
    text = str(value)
    limit = MAX_LEN.get(key)
    if limit and len(text) > limit:
        text = text[:limit]
    return text


def _canonical(row):
    return '|'.join(_clip(row.get(f), f) for f in _HASH_FIELDS)


def compute_hash(prev_hash, row):
    payload = '%s|%s' % (prev_hash or GENESIS, _canonical(row))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _request_context():
    """尽力从 Flask 请求上下文补全身份信息；不在请求中时返回空值。"""
    ctx = {'ip': '', 'ua': '', 'method': '', 'path': '', 'request_id': '',
           'uid': 0, 'username': ''}
    try:
        from flask import request, g, session
    except ImportError:
        return ctx
    try:
        ctx['ip'] = _clip(getattr(request, 'remote_addr', '') or '', 'ip')
        ctx['ua'] = _clip(request.headers.get('User-Agent', ''), 'ua')
        ctx['method'] = _clip(request.method, 'method')
        ctx['path'] = _clip(request.path, 'path')
        ctx['request_id'] = _clip(getattr(g, 'request_id', '') or '', 'request_id')
    except Exception:
        # 不在请求上下文（如 panel_task / CLI）
        return {'ip': '', 'ua': '', 'method': '', 'path': '', 'request_id': '',
                'uid': 0, 'username': ''}
    try:
        if 'uid' in session:
            ctx['uid'] = int(session.get('uid') or 0)
        elif session.get('login'):
            ctx['uid'] = 1
        if 'username' in session:
            ctx['username'] = _clip(session.get('username'), 'username')
    except Exception:
        # 会话不可读（签名失效/未登录）：按匿名处理，不影响主流程
        ctx['uid'] = 0
        ctx['username'] = ''
    if not ctx['ip']:
        try:
            import core.yf as yf
            ctx['ip'] = _clip(yf.getClientIp(), 'ip')
        except Exception:
            # 取不到客户端 IP（无请求上下文/代理头异常）：留空，不编造
            ctx['ip'] = ''
    return ctx


def _last_hash():
    """取链尾 row_hash；表不存在或为空时返回 GENESIS。"""
    try:
        import core.yf as yf
        row = yf.M('panel_audit').field('row_hash').order('id desc').limit('0,1').find()
        if isinstance(row, dict) and row.get('row_hash'):
            return row['row_hash']
    except Exception:
        # 表未就绪（升级中的窗口期）：当链首处理，后续写入会自愈接上
        return GENESIS
    return GENESIS


def write_audit(action, target='', result='ok', detail='',
                 uid=None, username=None, ts=None):
    """追加一条审计流水。**永不抛异常**（审计失败不能拖垮业务操作）。

    :param action:  动作标识，如 'plugin.start' / 'file.delete' / 'site.delete'
    :param target:  操作对象（插件名、路径、站点名……）
    :param result:  'ok' / 'fail' / 'denied'
    :param detail:  补充说明（会被截断，勿塞大文本）
    :return: True/False
    """
    try:
        import core.yf as yf

        ctx = _request_context()
        row = {
            'ts': ts or yf.formatDate(),
            'uid': ctx['uid'] if uid is None else uid,
            'username': ctx['username'] if username is None else username,
            'ip': ctx['ip'],
            'ua': ctx['ua'],
            'method': ctx['method'],
            'path': ctx['path'],
            'action': _clip(action, 'action'),
            'target': _clip(target, 'target'),
            'result': _clip(result, 'result'),
            'detail': _clip(detail, 'detail'),
            'request_id': ctx['request_id'],
        }

        with _LOCK:
            prev = _last_hash()
            row['prev_hash'] = prev
            row['row_hash'] = compute_hash(prev, row)
            yf.M('panel_audit').insert(row)
        return True
    except Exception as exc:
        # 降级到日志：库写不进去（如结构未就绪）时也别把信息丢了。
        # 不再套一层 try/except —— logging 自身不会因记录失败而抛，
        # 多余的静默兜底只会让「审计彻底失效」也无声无息。
        log.warning('审计写入失败：%s', exc)
        return False


def verify_chain(limit=0):
    """校验哈希链完整性。

    :return: (ok: bool, problems: list[str], checked: int)
    """
    problems = []
    checked = 0
    try:
        import core.yf as yf
        query = yf.M('panel_audit').field(
            'id,ts,uid,username,ip,ua,method,path,action,target,result,'
            'detail,request_id,prev_hash,row_hash').order('id asc')
        if limit:
            query = query.limit('0,%d' % int(limit))
        rows = query.select()
    except Exception as exc:
        return False, ['读取审计表失败：%s' % exc], 0

    if not isinstance(rows, list):
        return False, ['审计表读取返回异常类型：%r' % type(rows).__name__], 0

    prev = GENESIS
    for row in rows:
        checked += 1
        if row.get('prev_hash') != prev:
            problems.append('id=%s 的 prev_hash 与上一条的 row_hash 不连续'
                            '（疑似被删除或插入）' % row.get('id'))
        expect = compute_hash(row.get('prev_hash'), row)
        if expect != row.get('row_hash'):
            problems.append('id=%s 的 row_hash 校验不通过（内容被改动）' % row.get('id'))
        prev = row.get('row_hash')
    return (not problems), problems, checked
