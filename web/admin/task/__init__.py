# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import json
import time

from flask import Blueprint, render_template
from flask import request

from admin.user_login_check import panel_login_required

import core.yf as yf
import utils.task as YfTasks
import thisdb

blueprint = Blueprint('task', __name__, url_prefix='/task', template_folder='../../templates/default')


# 分页/标识参数容错解析。
# 原实现直接 int(request.form.get(...))，非数字入参抛 ValueError -> HTTP 500；
# 且未设上限，limit=-1 或极大值在 SQLite 下等价于无 LIMIT，一次拉全表。
_TASK_PAGE_LIMIT_MAX = 100


def _to_positive_int(value, default, maximum=None):
    try:
        num = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if num < 1:
        return default
    if maximum is not None and num > maximum:
        return maximum
    return num


def _is_task_id(value):
    # 任务 id 必须为正整数：id 会被拼进日志文件路径，
    # 历史实现允许 `1/../../../../var/log/x` 借已存在目录穿越读取任意 *.log 文件。
    text = str(value).strip()
    return text.isdigit() and int(text) > 0


@blueprint.route('/count', endpoint='task_count',methods=['GET','POST'])
@panel_login_required
def task_count():
    return yf.returnData(True, 'ok',thisdb.getTaskUnexecutedCount())

@blueprint.route('/list', endpoint='list', methods=['POST'])
@panel_login_required
def list():
    p = _to_positive_int(request.form.get('p', '1'), 1)
    limit = _to_positive_int(request.form.get('limit', '10'), 10, _TASK_PAGE_LIMIT_MAX)
    return YfTasks.getTaskPage(p, limit)

@blueprint.route('/get_exec_log', endpoint='get_exec_log', methods=['POST'])
@panel_login_required
def get_exec_log():
    file = yf.getPanelTaskExecLog()
    return yf.getLastLine(file, 100)


@blueprint.route('/get_task_log_by_id', endpoint='get_task_log_by_id', methods=['POST'])
@panel_login_required
def get_task_log_by_id():
    task_id = request.form.get('id', '')
    if task_id == '':
        return yf.returnData(False, 'task.py_msg_db6ce6')
    if not _is_task_id(task_id):
        return yf.returnData(False, 'public.ARGS_ERR')
    import os
    task_log_file = yf.getPanelDir() + '/tmp/panelTask_{}.log'.format(int(task_id))
    if not os.path.exists(task_log_file):
        return yf.returnData(False, 'task.py_msg_ecca58')
    return yf.returnData(True, yf.readFile(task_log_file))


@blueprint.route('/get_task_speed', endpoint='get_task_speed', methods=['POST'])
@panel_login_required
def get_task_speed():
    count = thisdb.getTaskUnexecutedCount()
    if count == 0:
        return yf.returnData(False, 'task.py_msg_3bc537')
    
    row = thisdb.getTaskFirstByRun()
    if row is None:
        return yf.returnData(False, 'task.py_msg_320fa8')

    task_logfile = yf.getPanelTaskExecLog()

    data = {}
    data['name'] = row['name']
    data['cmd'] = row['cmd']

    if row['type'] == 'download':
        readLine = ''
        for i in range(3):
            try:
                readLine = yf.readFile(task_logfile)
                data['msg'] = json.loads(readLine)
                data['isDownload'] = True
            except Exception as e:
                if i == 2:
                    thisdb.setTaskStatus(row['id'],0)
                    return yf.returnData(False, 'admin.py_msg_ce742b', None, str(e))
            time.sleep(0.5)
    else:
        data['msg'] = yf.getLastLine(task_logfile, 10)
        data['isDownload'] = False

    data['count'] = count
    data['task'] = thisdb.getTaskRunList(1,6)
    return data

@blueprint.route('/remove_task', endpoint='remove_task', methods=['POST'])
@panel_login_required
def remove_task():
    task_id = request.form.get('id', '')
    if task_id == '':
        return yf.returnData(False, 'task.py_msg_db6ce6')
    if not _is_task_id(task_id):
        return yf.returnData(False, 'public.ARGS_ERR')
    # 任务不存在时如实返回失败，避免对不存在的 id 也回「任务已删除!」的假成功。
    if yf.M('tasks').where('id=?', (int(task_id),)).getField('id') is None:
        return yf.returnData(False, 'common.del_failed')
    return YfTasks.removeTask(int(task_id))


    