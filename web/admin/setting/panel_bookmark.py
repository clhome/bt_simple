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

from utils.setting import setting as MwSetting

from .setting import blueprint
import thisdb

# 添加面板书签
@blueprint.route('/add_panel_info', endpoint='add_panel_info', methods=['POST'])
@panel_login_required
def add_panel_info():
    title = request.form.get('title', '')
    url = request.form.get('url', '')
    username = request.form.get('username', '')
    password = request.form.get('password', '')

    # 校验是还是重复
    isAdd = yf.M('panel').where('title=? OR url=?', (title, url)).count()
    if isAdd:
        return yf.returnData(False, '备注或面板地址重复!')
    isRe = yf.M('panel').add('title,url,username,password,click,add_time',
            (title, url, username, password, 0, int(time.time())))
    if isRe:
        return yf.returnData(True, '添加成功!')
    return yf.returnData(False, '添加失败!')

# 取面板书签列表
@blueprint.route('/get_panel_list', endpoint='get_panel_list', methods=['GET','POST'])
@panel_login_required
def get_panel_list():
    data = yf.M('panel').field('id,title,url,username,password,click,add_time').order('click desc').select()
    return yf.returnData(True, 'ok!', data)


# 删除面板书签
@blueprint.route('/del_panel_info', endpoint='del_panel_info', methods=['GET','POST'])
@panel_login_required
def del_panel_info():
    panel_id = request.form.get('id', '')
    isExists = yf.M('panel').where('id=?', (panel_id,)).count()
    if not isExists:
        return yf.returnData(False, '指定面板资料不存在!')
    yf.M('panel').where('id=?', (panel_id,)).delete()
    return yf.returnData(True, '删除成功!')


# 设置面板域名
@blueprint.route('/set_panel_info', endpoint='set_panel_info', methods=['POST'])
@panel_login_required
def set_panel_info():
    title = request.form.get('title', '')
    url = request.form.get('url', '')
    username = request.form.get('username', '')
    password = request.form.get('password', '')
    panel_id = request.form.get('id', '')
    # 校验是还是重复
    isSave = yf.M('panel').where('(title=? OR url=?) AND id!=?', (title, url, panel_id)).count()
    if isSave:
        return yf.returnData(False, '备注或面板地址重复!')

    # 更新到数据库
    isRe = yf.M('panel').where('id=?', (panel_id,)).save('title,url,username,password', (title, url, username, password))
    if isRe:
        return yf.returnData(True, '修改成功!')
    return yf.returnData(False, '修改失败!')

