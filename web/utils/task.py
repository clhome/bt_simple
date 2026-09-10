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
try:
    import pwd
except ImportError:
    pwd = None
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

# 递归终止进程树
def removeTaskRecursion(pid):
    try:
        pid = int(pid)
        if pid <= 1:
            return 'ok'
        if os.name != 'nt':
            import signal
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                time.sleep(0.1)
                os.killpg(os.getpgid(pid), signal.SIGKILL)
                return 'ok'
            except Exception as _e:
                pass
            cmd = "ps -ef|grep %s | grep -v grep |sed -n '2,1p' | awk '{print $2}'" % pid
            sub_pid = yf.execShell(cmd)[0].strip()
            if sub_pid and sub_pid != str(pid):
                removeTaskRecursion(sub_pid)
            yf.safeExecShell(['kill', '-9', str(pid)])
            return str(pid)
        else:
            yf.safeExecShell(['taskkill', '/F', '/T', '/PID', str(pid)])
            return 'ok'
    except Exception:
        return 'ok'

# 删除任务
def removeTask(task_id):
    try:
        name = yf.M('tasks').where('id=?', (task_id,)).getField('name')
        status = yf.M('tasks').where('id=?', (task_id,)).getField('status')
        yf.M('tasks').delete(task_id)

        # 1. 检查是否为当前正在执行的任务 (双重判定：数据库状态为 -1，或 pid 文件记录与当前 task_id 匹配)
        cur_task_pid_file = os.path.join(yf.getPanelDir(), 'tmp', 'panel_task_sub.pid')
        is_cur_running = (str(status) == '-1')
        p_to_kill = None
        if os.path.exists(cur_task_pid_file):
            try:
                content = yf.readFile(cur_task_pid_file).strip()
                if content and ':' in content:
                    t_id, p_id = content.split(':', 1)
                    if str(t_id) == str(task_id):
                        is_cur_running = True
                        if p_id.isdigit():
                            p_to_kill = int(p_id)
            except Exception as _e:
                pass

        if is_cur_running:
            sub_killed = False
            if p_to_kill:
                removeTaskRecursion(p_to_kill)
                sub_killed = True
                try:
                    if os.path.exists(cur_task_pid_file):
                        os.remove(cur_task_pid_file)
                except Exception as _e:
                    pass

            # 2. 保底机制：若未精准获取 PID，仅查找由 panel_task 衍生的工作子进程
            if not sub_killed and os.name != 'nt':
                cmd = "ps -ef | grep 'panel_task.py' | grep -v grep | awk '{print $2}'"
                task_pids = yf.execShell(cmd)[0].strip().split()
                for p in task_pids:
                    yf.safeExecShell(['pkill', '-TERM', '-P', p])

            yf.triggerTask()
    except Exception as e:
        pass

    # 删除日志
    task_log = yf.getPanelDir() + "/tmp/panelTask.pl"
    if os.path.exists(task_log):
        os.remove(task_log)
    
    specific_log = yf.getPanelDir() + "/tmp/panelTask_{}.log".format(task_id)
    if os.path.exists(specific_log):
        try:
            os.remove(specific_log)
        except Exception as _e:
            pass
            
    return yf.returnData(True, 'task.py_msg_454577')