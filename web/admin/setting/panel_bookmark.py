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
import os
import time

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
# 关联面板书签：密码落库加密（面板 Salt + Fernet），列表接口不回传密码。
# 快捷登录参数由服务端按需现签（/setting/get_panel_login），浏览器 DOM 中不驻留
# 明文口令；口令只在提交给目标面板的 POST body 里，URL 不含凭据。历史明文行在
# 读取时兼容透传，并在下次保存时自动升级为密文。
# ---------------------------------------------------------------------------------
_PB_CRYPT_KEY = 'panel_bookmark'
_PB_URL_RE = re.compile(r'^https?://[^\s/]+', re.I)


def _enc_pwd(pwd):
    """关联面板口令加密（fail-closed）。

    旧实现在加密异常时 `return pwd`，等于把**明文**写进 panel 表；
    现在让 DataCryptUnavailable 向上抛，由端点转成失败返回。
    """
    if not pwd:
        return ''
    return yf.enDoubleCrypt(_PB_CRYPT_KEY, pwd)


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
    # 缺 cryptography：拒绝保存（不落明文），并给出明确错误
    try:
        enc_pwd = _enc_pwd(password)
    except yf.DataCryptUnavailable as _e:
        yf.writeFileLog('[setting] 面板书签口令保存被拒绝（加密不可用）: %s' % _e)
        return yf.returnData(
            False, '数据加密组件不可用（缺少 cryptography），已拒绝保存；请安装 cryptography 后重试')
    isRe = yf.M('panel').add('title,url,username,password,click,add_time',
            (title, url, username, enc_pwd, 0, int(time.time())))
    if isRe:
        return yf.returnData(True, 'common.add_success')
    return yf.returnData(False, 'common.add_failed')


# 取面板书签列表
@blueprint.route('/get_panel_list', endpoint='get_panel_list', methods=['GET','POST'])
@panel_login_required
def get_panel_list():
    data = yf.M('panel').field('id,title,url,username,click,add_time').order('click desc').select()
    return yf.returnData(True, 'ok!', data)


# 目标面板的快捷登录端点：/<安全入口>/quick_login（见 dashboard.py::quick_login）
def _quick_login_url(base):
    url = str(base).strip()
    # 丢掉 base 自带的查询串/锚点，避免拼出畸形地址
    for sep in ('#', '?'):
        if sep in url:
            url = url.split(sep, 1)[0]
    return url.rstrip('/') + '/quick_login'


# 按需现签关联面板的快捷登录参数（服务端解密后再交给前端，前端不持有明文口令）
# 口令只出现在隐藏表单的 POST body 里，URL 不含任何凭据（旧机制把 base64(口令)
# 拼进 `?login=`，会进访问日志/浏览器历史）。
@blueprint.route('/get_panel_login', endpoint='get_panel_login', methods=['POST'])
@panel_login_required
def get_panel_login():
    panel_id = request.form.get('id', '')
    row = yf.M('panel').where('id=?', (panel_id,)).find()
    if not row or not row.get('url') or not _valid_panel_url(row.get('url')):
        return yf.returnData(False, 'setting.py_msg_785f90')

    # nonce 由源面板随机生成，目标面板记为「一次性、短时效」（防重放）；
    # 两套安装只共享口令、不共享密钥，目标面板无法验签，nonce 仅作防重放标识。
    fields = {
        'nonce': yf.getRandomString(32),
        'username': row.get('username', ''),
        'password': _dec_pwd(row.get('password', '')),
        'time': int(time.time() * 1000),
    }
    return yf.returnData(True, 'ok!', {
        'url': _quick_login_url(row.get('url')),
        'fields': fields,
    })


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
        # 缺 cryptography：拒绝保存（不落明文），并给出明确错误
        try:
            enc_pwd = _enc_pwd(password)
        except yf.DataCryptUnavailable as _e:
            yf.writeFileLog('[setting] 面板书签口令保存被拒绝（加密不可用）: %s' % _e)
            return yf.returnData(
                False, '数据加密组件不可用（缺少 cryptography），已拒绝保存；请安装 cryptography 后重试')
        isRe = yf.M('panel').where('id=?', (panel_id,)).save('title,url,username,password',
                                                              (title, url, username, enc_pwd))
    else:
        isRe = yf.M('panel').where('id=?', (panel_id,)).save('title,url,username',
                                                              (title, url, username))
    if isRe:
        return yf.returnData(True, 'common.edit_success')
    return yf.returnData(False, 'common.edit_failed')
