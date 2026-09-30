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
from utils.log_i18n import translate_log_type, translate_log_message

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

    # 入参容错交给 thisdb.getLogsList（含页大小上限），避免 int() 抛错变 500
    info = thisdb.getLogsList(page=p, size=size, search=search)

    # 操作日志落库时保存的是中文原文（历史记录亦然），在输出层统一
    # 按当前语言渲染「操作类型」与「详情」，切语言无需重写数据库。
    for item in info['list']:
        item['type'] = translate_log_type(item.get('type'))
        item['log'] = translate_log_message(item.get('log'))

    data = {}
    data['data'] = info['list']
    # 分页必须用 getLogsList 规范化后的整数：yf.getPage 内部是裸 int()，
    # 直接把表单原文喂进去（如 p=abc）会抛 ValueError -> HTTP 500。
    data['page'] = yf.getPage({'count': info['count'], 'tojs': 'getLogs',
                               'p': info['page'], 'row': info['size']})
    return data

# 日志清空 —— 改为「**归档**」而非物理删除
#
# 为什么改：原实现是一键抹掉全部操作痕迹，管理员（或拿到会话的攻击者）
# 可以借此消灭证据，审计合规直接不过。现在先导出到
# `data/log_archive/panel_logs_<时间>.json`，再清空界面日志；
# 且归档动作本身会进审计流水（append-only），所以「何时、由谁清空的」仍可查。
@blueprint.route('/del_panel_logs', endpoint='del_panel_logs', methods=['POST'])
@panel_login_required
def del_panel_logs():
    try:
        path, count = thisdb.archiveLogs()
    except Exception as e:
        # 归档失败必须如实报错：此时**没有清空任何日志**，
        # 复用成功文案会让用户以为清空完成了。
        yf.writeLog('面板设置', '面板操作日志归档失败: %s' % e)
        return yf.returnData(False, 'public.ERROR')
    yf.writeLog('面板设置', '面板操作日志已归档(%d 条)并清空!' % count)
    return yf.returnData(True, 'logs.py_msg_8d2a5b', {'archive': path, 'count': count})


# 审计流水列表（append-only，供合规检索）
@blueprint.route('/get_audit_trail', endpoint='get_audit_trail', methods=['POST'])
@panel_login_required
def get_audit_trail():
    p = request.form.get('p', '1').strip() or '1'
    size = request.form.get('limit', '20').strip() or '20'
    try:
        page = max(1, int(p))
        row = max(1, min(200, int(size)))
    except ValueError:
        page, row = 1, 20

    field = ('id,ts,uid,username,ip,ua,method,path,action,target,result,'
             'detail,request_id,row_hash')
    m = yf.M('panel_audit').field(field)
    total = m.count()
    start = (page - 1) * row
    rows = (yf.M('panel_audit').field(field)
            .limit('%d,%d' % (start, row)).order('id desc').select())
    if not isinstance(rows, list):
        rows = []
    return yf.returnData(True, 'ok', {
        'list': rows,
        'count': total,
        'page': yf.getPage({'count': total, 'tojs': 'getAuditTrail',
                            'p': str(page), 'row': str(row)}),
    })


# 审计哈希链完整性校验（篡改可发现）
@blueprint.route('/verify_audit_chain', endpoint='verify_audit_chain', methods=['POST'])
@panel_login_required
def verify_audit_chain():
    ok, problems, checked = yf.verifyAuditChain()
    if not ok:
        # 链断了是重大事件，必须留痕
        yf.writeLog('面板设置', '审计流水哈希链校验未通过（%d 处异常）' % len(problems))
    return yf.returnData(ok, 'ok', {
        'checked': checked,
        'problems': problems[:50],
    })

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
    try:
        return adult_log.getAuditLogsName(name)
    except Exception as e:
        # 审计读取失败不给前端 500：完整堆栈进日志，前端只拿安全提示。
        return yf.returnData(False, yf.userSafeError(e))









