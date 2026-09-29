# coding=utf-8
"""core.yf 子模块：log

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


from . import _getCachedStaticJson, _log, formatDate, getClientIp, getInfo, getJson, getLanguage, getTracebackInfo, isDebugMode


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

def writeFileLog(*args, **kwargs):
    return _pkg().writeFileLog(*args, **kwargs)


def returnJson(status, msg, data=None, *args):
    # 空消息或非字符串快速短路，0ms 直出
    if not msg or not isinstance(msg, str) or not msg.strip():
        if data is None:
            return getJson({'status': status, 'msg': msg})
        return getJson({'status': status, 'msg': msg, 'data': data})

    try:
        from core.i18n import t as _t
        translated_msg = _t(msg, *args)
    except Exception:
        translated_msg = msg

    if data is None:
        return getJson({'status': status, 'msg': translated_msg})
    return getJson({'status': status, 'msg': translated_msg, 'data': data})


def returnMsg(status, msg, args=()):
    try:
        from core.i18n import t as _t
        translated = _t(msg, *args)
        return {'status': status, 'msg': translated, 'data': args}
    except Exception as e:
        _log.debug('[yf] i18n 翻译失败，回退本地词表: %s', e)

    # 回退原字典逻辑
    lang = getLanguage()
    logMessage = _getCachedStaticJson('public', lang)
    keys = logMessage.keys()

    if msg in keys:
        msg = logMessage[msg]
        for i in range(len(args)):
            rep = '{' + str(i + 1) + '}'
            msg = msg.replace(rep, str(args[i]))
    return {'status': status, 'msg': msg, 'data': args}


def debugLog(*data):
    if isDebugMode():
        writeFileLog(str(data))
    return True


def userSafeError(exc, trace_id=None):
    """把内部异常转成「可安全展示给前端」的短消息。

    为什么要脱敏：把 `str(e)` 直接回前端会泄露绝对路径、SQL 片段、依赖版本
    与内网地址 —— 这些恰好是攻击者做下一步利用最想要的信息。
    完整堆栈只进面板日志，前端只拿一个追踪号，便于用户报障时对账。

    追踪号优先复用请求级 `g.request_id`（见 admin/__init__.py 的 before_request），
    这样「用户报的追踪号」与「日志里的请求 ID」是同一个，排查时能直接串起整条链路。
    """
    tid = trace_id
    if not tid:
        try:
            from flask import g as _g
            tid = getattr(_g, 'request_id', None)
        except Exception:
            tid = None
    if not tid:
        try:
            import uuid as _uuid
            tid = _uuid.uuid4().hex[:12]
        except Exception:
            tid = 'unknown'
    try:
        writeFileLog('[userSafeError][%s] %s\n%s' % (tid, exc, getTracebackInfo()))
    except Exception as e:
        # 写日志本身失败，不能递归再写日志
        _log.debug('[yf] 写 userSafeError 日志失败: %s', e)
    return '操作失败，请稍后重试或查看面板日志（追踪号 %s）' % tid


def _logIdentity():
    """取当前操作者身份 (uid, username, ip)。无请求上下文时返回 (0, '', '')。

    历史问题：`writeLog` 把 uid **硬编码为 0**（取 session 的代码被注释掉了），
    于是操作日志里「谁做的」永远查不到，也不记来源 IP —— 商业版的审计合规
    直接卡在这一条上。
    """
    uid, username, ip = 0, '', ''
    in_request = False
    try:
        from flask import session, request
        try:
            request.remote_addr  # 不在请求上下文会抛异常
            in_request = True
        except Exception:
            in_request = False
        if in_request:
            try:
                if 'uid' in session:
                    uid = int(session.get('uid') or 0)
                elif session.get('login'):
                    uid = 1
                username = session.get('username') or ''
            except Exception:
                # 会话不可读（签名失效/未登录）：按匿名处理
                uid, username = 0, ''
    except Exception:
        in_request = False

    if in_request:
        try:
            ip = getClientIp()
        except Exception:
            try:
                from flask import request as _r
                ip = getattr(_r, 'remote_addr', '') or ''
            except Exception:
                ip = ''
    return uid, username, ip


def writeAudit(action, target='', result='ok', detail=''):
    """显式写一条语义化审计记录（推荐在关键写操作里调用）。

    与 `writeLog` 的分工：`writeLog` 记录「面板做了什么」供界面展示；
    `writeAudit` 额外记录「对哪个对象、结果如何」，供合规审计检索。
    永不抛异常。
    """
    try:
        from core import audit
        return audit.write_audit(action=action, target=target,
                                 result=result, detail=detail)
    except Exception:
        return False


def verifyAuditChain(limit=0):
    """校验审计流水哈希链完整性。返回 (ok, problems, checked)。"""
    try:
        from core import audit
        return audit.verify_chain(limit=limit)
    except Exception as exc:
        return False, ['审计校验调用异常：%s' % exc], 0


def writeDbLog(stype, msg, args=(), uid=1, ip=''):
    try:
        import thisdb
        format_msg = getInfo(msg, args)
        thisdb.addLog(stype, format_msg, uid, ip=ip)
        return True
    except Exception as e:
        # 不能只 print：面板进程的 stdout 会丢，日志落盘才能排查
        writeFileLog('writeDbLog 失败: %s' % e)
        return False


##################### notify  end #########################################

# ---------------------------------------------------------------------------------
# 打印相关 START
# ---------------------------------------------------------------------------------

def echoStart(tag):
    print("=" * 89)  # print-ok: panel_tools CLI 输出
    print("★开始{}[{}]".format(tag, formatDate()))  # print-ok: panel_tools CLI 输出
    print("=" * 89)  # print-ok: panel_tools CLI 输出


def echoEnd(tag):
    print("=" * 89)  # print-ok: panel_tools CLI 输出
    print("☆{}完成[{}]".format(tag, formatDate()))  # print-ok: panel_tools CLI 输出
    print("=" * 89)  # print-ok: panel_tools CLI 输出


def echoInfo(msg):
    print("|-{}".format(msg))  # print-ok: panel_tools CLI 输出
