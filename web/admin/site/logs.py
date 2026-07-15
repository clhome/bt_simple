# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import os
import json

from flask import Blueprint, render_template
from flask import request

from admin.user_login_check import panel_login_required

from utils.plugin import plugin as YfPlugin
from utils.site import sites as YfSites

import core.yf as yf
import thisdb

from .site import blueprint

@blueprint.route('/get_logs', endpoint='get_logs',methods=['POST'])
@panel_login_required
def get_logs():
    siteName = request.form.get('siteName', '')
    return YfSites.instance().getLogs(siteName)


@blueprint.route('/get_error_logs', endpoint='get_error_logs',methods=['POST'])
@panel_login_required
def get_error_logs():
    siteName = request.form.get('siteName', '')
    return YfSites.instance().getErrorLogs(siteName)







