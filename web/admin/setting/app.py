# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import re
import json
import os
import time

from flask import Blueprint, render_template
from flask import request

from admin import session
from admin.user_login_check import panel_login_required

import core.yf as yf
import utils.config as utils_config

from .setting import blueprint
import thisdb

# 设置API
@blueprint.route('/set_panel_api', endpoint='set_panel_api', methods=['POST'])
@panel_login_required
def set_panel_api():
    panel_api = thisdb.getOptionByJson('panel_api', default={'open':False})
    if not panel_api['open']:
        panel_api['open'] = True
        thisdb.setOption('panel_api', json.dumps(panel_api))
        return yf.returnData(True, 'setting.py_msg_02d321')
    else:
        panel_api['open'] = False
        thisdb.setOption('panel_api', json.dumps(panel_api))
        return yf.returnData(True, 'setting.py_msg_4b4d08')


# 获取APP列表
@blueprint.route('/get_app_list', endpoint='get_app_list', methods=['POST'])
@panel_login_required
def get_app_list():
    limit = request.form.get('limit', '5').strip()
    page = request.form.get('page', '1').strip()
    tojs = request.form.get('tojs', 'getAppList').strip()

    info = thisdb.getAppList(page=int(page),size=int(limit))
    data = {}
    data['data'] = info['list']
    data['page'] = yf.getPage({'count':info['count'],'tojs':tojs,'p':page,'row':limit})
    return data


# 添加APP列表
@blueprint.route('/add_app', endpoint='add_app', methods=['POST'])
@panel_login_required
def add_app():
    app_id = request.form.get('app_id', '').strip()
    app_secret = request.form.get('app_secret', '1').strip()
    limit_addr = request.form.get('limit_addr', '').strip()
    if limit_addr == '':
        return yf.returnData(False, 'setting.py_msg_d061ab')

    rid = thisdb.addApp(app_id,app_secret,limit_addr)
    if rid > 0:
        return yf.returnData(True, 'common.add_success')
    return yf.returnData(False, 'common.add_failed')

# 添加APP列表
@blueprint.route('/toggle_app_status', endpoint='toggle_app_status', methods=['POST'])
@panel_login_required
def toggle_app_status():
    aid = request.form.get('id', '').strip()
    rid = thisdb.toggleAppStatus(aid)
    if rid > 0:
        return yf.returnData(True, 'setting.py_msg_ad1353')
    return yf.returnData(False, 'setting.py_msg_a16d8d')


# 获取APP列表
@blueprint.route('/delete_app', endpoint='delete_app', methods=['POST'])
@panel_login_required
def delete_app():
    aid = request.form.get('id', '').strip()
    rid = thisdb.deleteAppById(aid)
    if rid > 0:
        return yf.returnData(True, 'common.del_success')
    return yf.returnData(False, 'common.del_failed')
