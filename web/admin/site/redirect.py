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

# 获取重定向列表
@blueprint.route('/get_redirect', endpoint='get_redirect', methods=['POST'])
@panel_login_required
def get_redirect():
    site_name = request.form.get("siteName", '')
    return YfSites.instance().getRedirect(site_name)

# 设置重定向列表
@blueprint.route('/set_redirect', endpoint='set_redirect', methods=['POST'])
@panel_login_required
def set_redirect():
    site_name = request.form.get("siteName", '')
    site_from = request.form.get("from", '')
    to = request.form.get("to", '')                 # redirect to
    type = request.form.get("type", '')             # path / domain
    r_type = request.form.get("r_type", '')         # redirect type
    keep_path = request.form.get("keep_path", '')   # keep path
    return YfSites.instance().setRedirect(site_name, site_from, to, type, r_type, keep_path)


# 设置重定向状态
@blueprint.route('/set_redirect_status', endpoint='set_redirect_status', methods=['POST'])
@panel_login_required
def set_redirect_status():
    site_name = request.form.get("siteName", '')
    status = request.form.get("status")
    redirect_id = request.form.get("id", '')
    return YfSites.instance().setRedirectStatus(site_name, redirect_id, status)

# 获取重定向配置
@blueprint.route('/get_redirect_conf', endpoint='get_redirect_conf', methods=['POST'])
@panel_login_required
def get_redirect_conf():
    site_name = request.form.get("siteName", '')
    redirect_id = request.form.get("id", '')
    return YfSites.instance().getRedirectConf(site_name, redirect_id)

# 设置重定向配置
@blueprint.route('/save_redirect_conf', endpoint='save_redirect_conf', methods=['POST'])
@panel_login_required
def save_redirect_conf():
    site_name = request.form.get("siteName", '')
    redirect_id = request.form.get("id", '')
    config = request.form.get("config", "")
    return YfSites.instance().saveRedirectConf(site_name, redirect_id, config)




# 删除重定向配置
@blueprint.route('/del_redirect', endpoint='del_redirect', methods=['POST'])
@panel_login_required
def del_redirect():
    site_name = request.form.get("siteName", '')
    redirect_id = request.form.get("id", '')
    return YfSites.instance().delRedirect(site_name, redirect_id)









