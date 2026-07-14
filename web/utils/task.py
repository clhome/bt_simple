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
import pwd
import time

import core.yf as yf
import thisdb

def getTaskPage(page=1,size=10):
    info = thisdb.getTaskPage(page=page, size=size)

    rdata = {}
    rdata['data'] = info['list']
    rdata['count'] = info['count']
    rdata['page'] = yf.getPage({'count':info['count'],'tojs':'remind','p':page,'row':size})
    return rdata

# 删除进程下的所有进程
def removeTaskRecursion(pid):
    cmd = "ps -ef|grep %s | grep -v grep |sed -n '2,1p' | awk '{print $2}'" % pid
    sub_pid = yf.execShell(cmd)
    if sub_pid[0].strip() == '':
        return 'ok'

    if sub_pid[0].strip() == pid :
        return 'ok'

    removeTaskRecursion(sub_pid[0].strip())
    yf.execShell('kill -9 ' + sub_pid[0].strip())
    return sub_pid[0].strip()

# 删除任务
def removeTask(task_id):
    try:
        name = yf.M('tasks').where('id=?', (task_id,)).getField('name')
        status = yf.M('tasks').where('id=?', (task_id,)).getField('status')
        yf.M('tasks').delete(task_id)
        if str(status) == '-1':
            cmd = "ps aux | grep 'panel_task.py' | grep -v grep |awk '{print $2}'"
            task_pid = yf.execShell(cmd)
            task_list = task_pid[0].strip().split("\n")
            for i in range(len(task_list)):
                removeTaskRecursion(task_list[i])
                t = yf.execShell('kill -9 ' + task_list[i])
                print(t)
            yf.triggerTask()
            yf.restartTask()
    except Exception as e:
        yf.restartTask()

    # 删除日志
    task_log = yf.getPanelDir() + "/tmp/panelTask.pl"
    if os.path.exists(task_log):
        os.remove(task_log)
    
    specific_log = yf.getPanelDir() + "/tmp/panelTask_{}.log".format(task_id)
    if os.path.exists(specific_log):
        try:
            os.remove(specific_log)
        except:
            pass
            
    return yf.returnData(True, '任务已删除!')