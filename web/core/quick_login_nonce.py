# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 作者: midoks & yufeng tec
# ---------------------------------------------------------------------------------
# 安全入口快捷登录的一次性 nonce（防重放）
# ---------------------------------------------------------------------------------
"""
源面板（另一套独立安装）与目标面板只共享口令、不共享密钥，因此目标面板
**无法验证**源面板签发的 nonce。这里的 nonce 只作「防重放标识」：

    首次见到某个 nonce → 记下并放行；窗口内再次出现同一个 nonce → 拒绝。

存储是**进程内**结构（dict + 锁）：面板默认单 worker（见 web/setting.py 的
``workers = 1``，多 worker 会导致 SocketIO 握手失败，属同一前提）。
若显式设了 ``YF_ALLOW_MULTI_WORKER=1``，nonce 会按进程隔离，重放有可能落到
另一个 worker 而未被识别 —— 与登录封禁缓存等多 worker 限制同源，已在
setting.py 打警告。
"""

import threading
import time

#: nonce 有效期（秒）。与 dashboard.QUICK_LOGIN_TTL_MS 的签发时间窗口对齐。
NONCE_TTL = 60

_LOCK = threading.Lock()
_USED = {}


def burn(nonce, ttl=NONCE_TTL):
    """标记 nonce 已用（用后即焚）。

    返回 ``True`` = 首次见到（放行），``False`` = 空 nonce 或重放（拒绝）。
    顺带清掉已过期的条目，避免结构无限增长。
    """
    if not nonce:
        return False
    now = time.time()
    with _LOCK:
        for key in [k for k, expire_at in _USED.items() if expire_at <= now]:
            _USED.pop(key, None)
        if nonce in _USED:
            return False
        _USED[nonce] = now + ttl
        return True


def reset():
    """清空记录（测试用）。"""
    with _LOCK:
        _USED.clear()
