# coding:utf-8

# ---------------------------------------------------------------------------------
# MW-Linux面板
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

def panel_login_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):
        # 面板API调用检查
        app_id = request.headers.get('App-Id','')
        app_secret = request.headers.get('App-Secret','')
        if app_id != '' and app_secret != '':
            panel_api = thisdb.getOptionByJson('panel_api', default={"open":True})
            if panel_api['open']:
                info = thisdb.getAppByAppId(app_id)
                if info is None:
                    return Response(status=404)
                if not hmac.compare_digest(app_secret, info['app_secret']):
                    return Response(status=403)
                return func(*args, **kwargs)

        if not isLogined():
            unauthorized_status = thisdb.getOption('unauthorized_status', default='0')
            if unauthorized_status == '0':
                return render_template('default/path.html')
            return Response(status=int(unauthorized_status))

        return func(*args, **kwargs)
    return wrapper