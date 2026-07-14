# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------


from flask import Blueprint, render_template
from flask import request

from admin.user_login_check import panel_login_required

import core.yf as mw
import utils.system as sys

from .system import blueprint

# 升级检测
@blueprint.route('/update_server', endpoint='update_server')
@panel_login_required
def update_server():
    panel_type = request.args.get('type', 'check')
    version = request.args.get('version', '')
    step = request.args.get('step', 'all')
    return sys.updateServer(panel_type, version, step=step)



