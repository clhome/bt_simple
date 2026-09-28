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
import base64

from flask import Blueprint, render_template
from flask import request

from admin import session
from admin.user_login_check import panel_login_required

import core.yf as yf
import utils.config as utils_config

from utils.setting import setting as YfSetting

from .setting import blueprint
import thisdb

# ---------------------------------------------------------------------------------
# 关联面板书签：密码落库加密（面板 Salt + Fernet），接口不再回传明文密码。
# 快捷登录所需的登录串由服务端按需现签（/setting/get_panel_login），浏览器 DOM
# 中不再驻留明文口令。历史明文行在读取时兼容透传，并在下次保存时自动升级为密文。
# ---------------------------------------------------------------------------------
_PB_CRYPT_KEY = 'panel_bookmark'
_PB_URL_RE = re.compile(r'^https?://[^\s/]+', re.I)


def _enc_pwd(pwd):
    if not pwd:
        return ''
    try:
        return yf.enDoubleCrypt(_PB_CRYPT_KEY, pwd)
    except Exception:
        return pwd


def _dec_pwd(pwd):
    if not pwd:
        return ''
    try:
        return yf.deDoubleCrypt(_PB_CRYPT_KEY, pwd)
    except Exception:
        return pwd


def _valid_panel_url(url):
    return bool(url) and bool(_PB_URL_RE.match(str(url).strip()))


# 添加面板书签
@blueprint.route('/add_panel_info', endpoint='add_panel_info', methods=['POST'])
@panel_login_required
def add_panel_info():
    title = request.form.get('title', '')
    url = request.form.get('url', '')
    username = request.form.get('username', '')
    password = request.form.get('password', '')

    # 仅允许 http/https 面板地址，避免把 javascript: 之类写库后回传前端
    if not _valid_panel_url(url):
        return yf.returnData(False, 'setting.py_msg_785f90')

    # 校验是还是重复
    isAdd = yf.M('panel').where('title=? OR url=?', (title, url)).count()
    if isAdd:
        return yf.returnData(False, 'setting.py_msg_e23be1')
    isRe = yf.M('panel').add('title,url,username,password,click,add_time',
            (title, url, username, _enc_pwd(password), 0, int(time.time())))
    if isRe:
        return yf.returnData(True, 'common.add_success')
    return yf.returnData(False, 'common.add_failed')


# 取面板书签列表
@blueprint.route('/get_panel_list', endpoint='get_panel_list', methods=['GET','POST'])
@panel_login_required
def get_panel_list():
    data = yf.M('panel').field('id,title,url,username,click,add_time').order('click desc').select()
    return yf.returnData(True, 'ok!', data)


# 按需现签关联面板的快捷登录串（服务端解密后再组 URL，前端不持有明文口令）
@blueprint.route('/get_panel_login', endpoint='get_panel_login', methods=['POST'])
@panel_login_required
def get_panel_login():
    panel_id = request.form.get('id', '')
    row = yf.M('panel').where('id=?', (panel_id,)).find()
    if not row or not row.get('url') or not _valid_panel_url(row.get('url')):
        return yf.returnData(False, 'setting.py_msg_785f90')

    payload = {
        'rand': yf.getRandomString(8),
        'username': row.get('username', ''),
        'password': _dec_pwd(row.get('password', '')),
        'time': int(time.time() * 1000),
    }
    login_args = base64.b64encode(
        json.dumps(payload).encode('utf-8')).decode('utf-8')
    sep = '&' if '?' in row['url'] else '?'
    return yf.returnData(True, 'ok!', {'url': row['url'] + sep + 'login=' + login_args})


# 删除面板书签
@blueprint.route('/del_panel_info', endpoint='del_panel_info', methods=['POST'])
@panel_login_required
def del_panel_info():
    panel_id = request.form.get('id', '')
    isExists = yf.M('panel').where('id=?', (panel_id,)).count()
    if not isExists:
        return yf.returnData(False, 'setting.py_msg_785f90')
    yf.M('panel').where('id=?', (panel_id,)).delete()
    return yf.returnData(True, 'common.del_success')


# 设置面板域名
@blueprint.route('/set_panel_info', endpoint='set_panel_info', methods=['POST'])
@panel_login_required
def set_panel_info():
    title = request.form.get('title', '')
    url = request.form.get('url', '')
    username = request.form.get('username', '')
    password = request.form.get('password', '')
    panel_id = request.form.get('id', '')

    if not _valid_panel_url(url):
        return yf.returnData(False, 'setting.py_msg_785f90')

    # 校验是还是重复
    isSave = yf.M('panel').where('(title=? OR url=?) AND id!=?', (title, url, panel_id)).count()
    if isSave:
        return yf.returnData(False, 'setting.py_msg_e23be1')

    # 密码留空表示“不修改”，避免前端不再回显明文后被误清空
    if password:
        isRe = yf.M('panel').where('id=?', (panel_id,)).save('title,url,username,password',
                                                              (title, url, username, _enc_pwd(password)))
    else:
        isRe = yf.M('panel').where('id=?', (panel_id,)).save('title,url,username',
                                                              (title, url, username))
    if isRe:
        return yf.returnData(True, 'common.edit_success')
    return yf.returnData(False, 'common.edit_failed')
