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

_login_cache = {}

def isLogined():
    if 'login' in session  and session['login'] == True and 'username' in session:
        username = session['username']
        now_time = int(time.time())

        # 确保 session 有唯一的 session_id 标识
        session_id = session.get('session_id')
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id

        # 检查短期缓存 (TTL: 20s)
        if session_id in _login_cache:
            cache_time, cache_result = _login_cache[session_id]
            if now_time - cache_time < 20:
                if 'overdue' in session and now_time > session['overdue']:
                    session.clear()
                    return False
                if 'tmp_login_expire' in session and now_time > int(session['tmp_login_expire']):
                    session.clear()
                    return False
                return cache_result

        info = thisdb.getUserByName(username)
        if info is None:
            _login_cache[session_id] = (now_time, False)
            return False

        # print(userInfo)
        if info['name'] != session['username']:
            _login_cache[session_id] = (now_time, False)
            return False

        if 'overdue' in session and now_time > session['overdue']:
            session.clear()
            return False

        if 'tmp_login_expire' in session and now_time > int(session['tmp_login_expire']):
            session.clear()
            return False
            
        _login_cache[session_id] = (now_time, True)
        return True
    return False