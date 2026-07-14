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

import core.yf as yf
import utils.adult_log as adult_log
import thisdb

# 日志页面
blueprint = Blueprint('logs', __name__, url_prefix='/logs', template_folder='../../templates')
@blueprint.route('/index', endpoint='index')
@panel_login_required
def index():
    name = thisdb.getOption('template', default='default')
    return render_template('%s/logs.html' % name)

# 日志列表
@blueprint.route('/get_log_list', endpoint='get_log_list', methods=['POST'])
@panel_login_required
def get_log_list():
    p = request.form.get('p', '1').strip()
    size = request.form.get('limit', '10').strip()
    search = request.form.get('search', '').strip()

    info = thisdb.getLogsList(page=int(p),size=int(size), search=search)

    data = {}
    data['data'] = info['list']
    data['page'] = yf.getPage({'count':info['count'],'tojs':'getLogs','p':p,'row':size})
    return data

# 日志清空
@blueprint.route('/del_panel_logs', endpoint='del_panel_logs', methods=['POST'])
@panel_login_required
def del_panel_logs():
    thisdb.clearLog()
    yf.writeLog('面板设置', '面板操作日志已清空!')
    return yf.returnData(True, '面板操作日志已清空!')

# 系统审计日志列表
@blueprint.route('/get_audit_logs_files', endpoint='get_audit_logs_files', methods=['POST'])
@panel_login_required
def get_audit_logs_files():
    logs_file = adult_log.getAuditLogsFiles()
    return yf.returnData(True, 'ok', logs_file)

# 系统审计日志列表
@blueprint.route('/get_audit_file', endpoint='get_audit_file', methods=['POST'])
@panel_login_required
def get_audit_file():
    name = request.form.get('log_name', '').strip()
    return adult_log.getAuditLogsName(name)









