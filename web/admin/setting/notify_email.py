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

# 获取邮件信息
@blueprint.route('/get_notify_email', endpoint='get_notify_email', methods=['POST'])
@panel_login_required
def get_notify_email():
    notify_email = thisdb.getOptionByJson('notify_email', default={'open':False}, type='notify')
    if not isinstance(notify_email, dict):
        notify_email = {'open': False}

    if 'cfg' in notify_email:
        decrypt_data = yf.deDoubleCrypt('email', notify_email['cfg'])
        try:
            notify_email['email'] = json.loads(decrypt_data)
        except Exception:
            # 历史脏数据(非 JSON)不得把接口打成 500 —— 退回空表单。
            yf.writeFileLog('[setting] notify_email.cfg 不是合法 JSON,已按空配置处理')
            notify_email['email'] = {'smtp_host':'','smtp_port':'','smtp_ssl':'','to_mail_addr':'','username':'','password':''}
    else:
        notify_email['email'] = {'smtp_host':'','smtp_port':'','smtp_ssl':'','to_mail_addr':'','username':'','password':''}
    
    return yf.returnData(True,'ok',notify_email)


# 设置邮件信息
@blueprint.route('/set_notify_email', endpoint='set_notify_email', methods=['POST'])
@panel_login_required
def set_notify_email():
    tag = request.form.get('tag', '').strip()
    data = request.form.get('data', '').strip()

    # 写入侧校验:非 JSON 对象一旦落库,读取侧 json.loads 会失败
    # —— 而 get_notify_email 每次面板重启都会被调用(全站 500,只能改库救回)。
    try:
        parsed = json.loads(data)
    except Exception:
        return yf.returnData(False, 'ARGS_ERR')
    if not isinstance(parsed, dict):
        return yf.returnData(False, 'ARGS_ERR')

    crypt_data = yf.enDoubleCrypt(tag, data)
    
    notify_email = thisdb.getOptionByJson('notify_email', default={'open':False}, type='notify')
    notify_email['cfg'] = crypt_data

    thisdb.setOption('notify_email', json.dumps(notify_email), type='notify')
    return yf.returnData(True, 'common.set_success')


# 设置邮件测试
@blueprint.route('/set_notify_email_test', endpoint='set_notify_email_test', methods=['POST'])
@panel_login_required
def set_notify_email_test():
    tag = request.form.get('tag', '').strip()
    tag_data = request.form.get('data', '').strip()

    # 入参不是合法 JSON 对象时,bare json.loads 会抛 ValueError 把接口打成 500
    try:
        data = json.loads(tag_data)
    except Exception:
        return yf.returnData(False, 'ARGS_ERR')
    if not isinstance(data, dict):
        return yf.returnData(False, 'ARGS_ERR')

    data.setdefault('mail_test', '')
    test_pass = yf.emailNotifyTest(data)
    if test_pass == True:
        return yf.returnData(True, 'setting.py_msg_45001d')
    return yf.returnData(False, 'admin.py_msg_557e74', None, test_pass)

# 切换邮件开关
@blueprint.route('/set_notify_email_enable', endpoint='set_notify_email_enable', methods=['POST'])
@panel_login_required
def set_notify_email_enable():
    tag = request.form.get('tag', '').strip()
    data = request.form.get('data', '').strip()

    notify_email = thisdb.getOptionByJson('notify_email', default={'open':False}, type='notify')
    if not isinstance(notify_email, dict):
        notify_email = {'open': False}

    if notify_email['open']:
        op_action = '关闭'
        notify_email['open'] = False
    else:
        op_action = '开启'
        notify_email['open'] = True

    thisdb.setOption('notify_email', json.dumps(notify_email), type='notify')
    return yf.returnData(True, op_action+'成功')