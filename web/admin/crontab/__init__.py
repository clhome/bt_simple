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

from utils.crontab import crontab as YfCrontab
import core.yf as yf
import thisdb

blueprint = Blueprint('crontab', __name__, url_prefix='/crontab', template_folder='../../templates')
@blueprint.route('/index', endpoint='index')
@panel_login_required
def index():
    name = thisdb.getOption('template', default='default')
    return render_template('%s/crontab.html' % name)

# 计划任务列表
@blueprint.route('/list', endpoint='list', methods=['POST'])
@panel_login_required
def list():
    def _int_arg(name, default):
        try:
            return int(request.args.get(name, default))
        except (TypeError, ValueError):
            return int(default)

    page = max(_int_arg('p', 1), 1)
    # 上限 1000：导出功能就是按 limit=1000 拉全量，再大只会白拉数据
    limit = min(max(_int_arg('limit', 10), 1), 1000)
    search = request.args.get('search', '').strip()
    orderby = request.args.get('orderby', 'last_run_time').strip()
    order = request.args.get('order', 'desc').strip()
    return YfCrontab.instance().getCrontabList(page=page,size=limit, search=search, orderby=orderby, order=order)

# 计划任务日志
@blueprint.route('/logs', endpoint='logs', methods=['POST'])
@panel_login_required
def logs():
    cron_id = request.form.get('id', '')
    return YfCrontab.instance().cronLog(cron_id)

# 删除计划任务
@blueprint.route('/del', endpoint='del', methods=['POST'])
@panel_login_required
def crontab_del():
    cron_id = request.form.get('id', '')   
    return YfCrontab.instance().delete(cron_id)

# 删除计划任务日志
@blueprint.route('/del_logs', endpoint='del_logs', methods=['POST'])
@panel_login_required
def del_logs():
    cron_id = request.form.get('id', '')   
    return YfCrontab.instance().delLogs(cron_id)


# 设置计划任务状态
@blueprint.route('/set_cron_status', endpoint='set_cron_status', methods=['POST'])
@panel_login_required
def set_cron_status():
    cron_id = request.form.get('id', '')   
    return YfCrontab.instance().setCronStatus(cron_id)

# 设置计划任务状态
@blueprint.route('/get_data_list', endpoint='get_data_list', methods=['POST'])
@panel_login_required
def get_data_list():
    stype = request.form.get('type', '')
    return YfCrontab.instance().getDataList(stype)


# 获取计划任务
@blueprint.route('/get_crond_find', endpoint='get_crond_find', methods=['POST'])
@panel_login_required
def get_crond_find():
    cron_id = request.form.get('id', '')
    data = YfCrontab.instance().getCrondFind(cron_id)
    if data is None:
        return yf.returnData(False, 'common.param_error')
    return data

# 修改计划任务
@blueprint.route('/modify_crond', endpoint='modify_crond', methods=['POST'])
@panel_login_required
def modify_crond():
    request_data = {}
    
    request_data['name'] = request.form.get('name', '')
    request_data['type'] = request.form.get('type', '')
    request_data['week'] = request.form.get('week', '')
    request_data['where1'] = request.form.get('where1', '')
    request_data['hour'] = request.form.get('hour', '')
    request_data['minute'] = request.form.get('minute', '')
    request_data['save'] = request.form.get('save', '')
    request_data['backup_to'] = request.form.get('backup_to', '')
    request_data['stype'] = request.form.get('stype', '')
    request_data['sname'] = request.form.get('sname', '')
    request_data['sbody'] = request.form.get('sbody', '')
    request_data['url_address'] = request.form.get('url_address', '')
    request_data['attr'] = request.form.get('attr', '')
    request_data['day_type'] = request.form.get('day_type', '0')
    for _k, _d in (('min_start_en', '0'), ('min_start_h', '0'), ('min_start_m', '0'),
                   ('min_end_en', '0'), ('min_end_h', '23'), ('min_end_m', '59')):
        request_data[_k] = request.form.get(_k, _d)
    # 导入（导出文件里没有 week 字段）时周任务只剩 where1：补回 week，否则周字段为空
    if request_data['type'] == 'week' and request_data['week'] == '':
        request_data['week'] = request_data['where1']
    cron_id = request.form.get('id', '')
    data = YfCrontab.instance().modifyCrond(cron_id,request_data)
    return data

# 执行计划任务
@blueprint.route('/start_task', endpoint='start_task', methods=['POST'])
@panel_login_required
def start_task():
    cron_id = request.form.get('id', '')
    return YfCrontab.instance().startTask(cron_id)

# 添加计划任务
@blueprint.route('/add', endpoint='add', methods=['POST'])
@panel_login_required
def add():
    request_data = {}
    request_data['name'] = request.form.get('name', '')
    request_data['type'] = request.form.get('type', '')
    request_data['week'] = request.form.get('week', '')
    request_data['where1'] = request.form.get('where1', '')
    request_data['hour'] = request.form.get('hour', '')
    request_data['minute'] = request.form.get('minute', '')
    request_data['save'] = request.form.get('save', '')
    request_data['backup_to'] = request.form.get('backup_to', '')
    request_data['stype'] = request.form.get('stype', '')
    request_data['sname'] = request.form.get('sname', '')
    request_data['sbody'] = request.form.get('sbody', '')
    request_data['url_address'] = request.form.get('url_address', '')
    request_data['attr'] = request.form.get('attr', '')
    request_data['day_type'] = request.form.get('day_type', '0')
    for _k, _d in (('min_start_en', '0'), ('min_start_h', '0'), ('min_start_m', '0'),
                   ('min_end_en', '0'), ('min_end_h', '23'), ('min_end_m', '59')):
        request_data[_k] = request.form.get(_k, _d)
    # 导入（导出文件里没有 week 字段）时周任务只剩 where1：补回 week，否则周字段为空
    if request_data['type'] == 'week' and request_data['week'] == '':
        request_data['week'] = request_data['where1']

    info = thisdb.getCronByName(request_data['name'])
    if info is not None:
        return yf.returnData(False, 'crontab.py_msg_2c1843')

    try:
        data = YfCrontab.instance().add(request_data)
        if isinstance(data, dict):
            return data
        if data > 0:
            return yf.returnData(True, 'common.add_success')
        return yf.returnData(False, 'common.add_failed')
    except Exception as e:
        return yf.returnData(False, 'admin.py_msg_a71a3c', None, str(e))

# 同步系统级和面板内置计划任务
@blueprint.route('/sync_sys_cron', endpoint='sync_sys_cron', methods=['POST'])
@panel_login_required
def sync_sys_cron():
    try:
        from admin.setup.init_cron import sync_all_tasks
        count = sync_all_tasks()
        if count > 0:
            return yf.returnData(True, 'crontab.py_msg_9d44d8', None, count)
        else:
            return yf.returnData(True, 'crontab.py_msg_f47dfc')
    except Exception as e:
        return yf.returnData(False, 'admin.py_msg_11ca8c', None, str(e))
