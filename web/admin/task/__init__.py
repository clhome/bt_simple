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


@blueprint.route('/count', endpoint='task_count',methods=['GET','POST'])
@panel_login_required
def task_count():
    return yf.returnData(True, 'ok',thisdb.getTaskUnexecutedCount())

@blueprint.route('/list', endpoint='list', methods=['POST'])
@panel_login_required
def list():
    p = request.form.get('p', '1')
    limit = request.form.get('limit', '10').strip()
    search = request.form.get('search', '').strip()
    return YfTasks.getTaskPage(int(p), int(limit))

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
        return yf.returnData(False, '任务ID不能为空!')
    import os
    task_log_file = yf.getPanelDir() + '/tmp/panelTask_{}.log'.format(task_id)
    if not os.path.exists(task_log_file):
        return yf.returnData(False, '暂无日志记录。')
    return yf.returnData(True, yf.readFile(task_log_file))


@blueprint.route('/get_task_speed', endpoint='get_task_speed', methods=['POST'])
@panel_login_required
def get_task_speed():
    count = thisdb.getTaskUnexecutedCount()
    if count == 0:
        return yf.returnData(False, '当前没有任务队列在执行-2!')
    
    row = thisdb.getTaskFirstByRun()
    if row is None:
        return yf.returnData(False, '当前没有任务队列在执行-3!')

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
                    return yf.returnData(False, '当前没有任务队列在执行-4:' + str(e))
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
        return yf.returnData(False, '任务ID不能为空!')
    return YfTasks.removeTask(task_id)


    