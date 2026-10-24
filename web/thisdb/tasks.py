# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import core.yf as yf

__FIELD = 'id,name,type,start,end,cmd,status,add_time'

# ---------------------------------------------------------------------------------
# 任务状态语义（**全仓唯一定义**，改动前先看这里）：
#
#   0  = 排队中（等待执行）
#   -1 = 执行中
#   1  = 成功
#   2  = 失败（有日志、可重试）
#
# 关键口径：**失败不是「未执行」**。历史实现把所有 `status != 1` 都当成「未执行」，
# 于是任务失败后：
#   * 消息盒子把 status=2 渲染成「等待」，用户看到任务永远卡在那儿（真实用户报障）；
#   * `getTaskUnexecutedCount() >= 1` 恒成立 → 触发文件永远不删、面板重启后反复重跑；
#   * `addTask()` 因「同 cmd 的任务还在队列里」拒绝再入队 → 点第二次升级**静默无效**。
# 因此下面所有「活跃 / 未执行」判定一律只认 (0, -1)，失败任务单独统计/清理。
# ---------------------------------------------------------------------------------

#: 「活跃」状态（排队 + 执行中）：会阻塞同 cmd 重复入队、计入未执行数。
TASK_ACTIVE_STATUSES = (0, -1)
#: 失败状态（用户需要看到并能重试/删除）。
TASK_FAILED_STATUS = 2
#: 成功状态。
TASK_SUCCESS_STATUS = 1


def getTaskCount(status = -1) -> int:
    return yf.M('tasks').where('status=?',(1,)).count()


# 未执行任务总数（只算排队中/执行中；失败任务不计入）
def getTaskUnexecutedCount() -> int:
    return yf.M('tasks').where('status IN (?,?)', TASK_ACTIVE_STATUSES).count()


def getTaskFailedCount() -> int:
    """失败任务总数（消息盒子用；与未执行数分开，避免「失败」被当成「卡住」）。"""
    return yf.M('tasks').where('status=?', (TASK_FAILED_STATUS,)).count()


def getTaskActiveList(page = 1, size = 10):
    """排队中 + 执行中的任务（按入队顺序）。"""
    start = (page - 1) * size
    limit = str(start) + ',' + str(size)
    return yf.M('tasks').where('status IN (?,?)', TASK_ACTIVE_STATUSES) \
        .field(__FIELD).limit(limit).order('id asc').select()


def getTaskRecentFailed(size = 5):
    """最近失败的任务（按 id 倒序）。只用于展示，不参与任何「是否还在跑」的判定。"""
    if size < 1:
        return []
    return yf.M('tasks').where('status=?', (TASK_FAILED_STATUS,)) \
        .field(__FIELD).limit(str(int(size))).order('id desc').select()


def removeFailedTaskByCmd(cmd):
    """删掉「同一条命令」的失败任务，让用户重试后列表里不留旧尸体。

    只删 status=2（失败），绝不动排队中/执行中/成功的任务。返回删除条数。
    """
    if not cmd:
        return 0
    rows = yf.M('tasks').where('status=? AND cmd=?', (TASK_FAILED_STATUS, cmd)).field('id').select()
    removed = 0
    for row in rows or []:
        try:
            task_id = row['id']
        except (TypeError, KeyError, IndexError) as _e:
            yf.writeFileLog('removeFailedTaskByCmd 解析任务行失败: %s' % _e)
            continue
        delTask(task_id)
        removed += 1
    return removed


def delTask(task_id):
    """按 id 删除任务（幂等）。"""
    try:
        int(task_id)
    except (TypeError, ValueError):
        return False
    yf.M('tasks').where('id=?',(int(task_id),)).delete()
    return True

def addTaskByDownload(name = '下载文件',cmd = None,type = 'download',status = 0):
    '''
    添加后台任务
    :name -> str 类型
    :cmd -> str 日志内容 (必填)
    :type -> str 用户ID
    '''
    if cmd is None:
        return False

    add_time = yf.formatDate()
    insert_data = {
        'name':name,
        'type':type,
        'cmd':cmd,
        'start':0,
        'end':0,
        'status':status,
        'add_time':add_time,
    }
    yf.M('tasks').insert(insert_data)
    return True

def addTask(
    name = '常用任务',
    cmd = None,
    type = 'execshell',
    status = 0,
):
    '''
    添加后台任务
    :name -> str 类型
    :cmd -> str 日志内容 (必填)
    :type -> str 用户ID
    '''
    if cmd is None:
        return False

    # 检查是否已经在执行队列中：**只看排队中/执行中**（0/-1）。
    # 历史实现用 `status!=1`，于是「上一次同命令的任务失败了」会让这次永远进不了队，
    # 而调用方又拿不到原因 —— 用户看到的就是「点升级没反应」。
    isTask = yf.M('tasks').where('status IN (?,?) AND cmd=?',
                                 TASK_ACTIVE_STATUSES + (cmd,)).count()
    if isTask > 0:
        return False

    add_time = yf.formatDate()
    insert_data = {
        'name':name,
        'type':type,
        'cmd':cmd,
        'start':0,
        'end':0,
        'status':status,
        'add_time':add_time,
    }
    yf.M('tasks').insert(insert_data)
    return True


def getTaskList(
    status = 1,
    page = 1,
    size = 10,
):
    start = (page - 1) * size
    limit = str(start) + ',' + str(size)
    task_list = yf.M('tasks').where('status=?', (status,)).field(__FIELD).limit(limit).order('id asc').select()
    return task_list

def getTaskPage(
    status = 1,
    page = 1,
    size = 10,
):
    start = (page - 1) * size
    limit = str(start) + ',' + str(size)
    task_list = yf.M('tasks').where('', ()).field(__FIELD).limit(limit).order('id desc').select()
    count = yf.M('tasks').where('', ()).count()

    rdata = {}
    rdata['list'] = task_list
    rdata['count'] = count
    return rdata

def getTaskFirstByRun() -> None:
    # 「正在跑/等着跑」的第一条：只认 0/-1，失败任务不能顶上来被当成当前任务
    data = yf.M('tasks').where('status IN (?,?)', TASK_ACTIVE_STATUSES)         .field(__FIELD).order('id asc').find()
    if data is None:
        return None
    return data

def getTaskRunList(page = 1,size = 10):
    start = (page - 1) * size
    limit = str(start) + ',' + str(size)
    task_list = yf.M('tasks').where('status!=?', (1,)).field(__FIELD).limit(limit).order('id asc').select()
    return task_list

def getTaskRunAll():
    task_list = yf.M('tasks').where('status!=?', (1,)).field(__FIELD).order('id asc').select()
    return task_list

def getTaskRunPage(page = 1, size = 10):
    start = (page - 1) * size
    limit = str(start) + ',' + str(size)

    task_list = yf.M('tasks').where('status!=?', (1,)).field(__FIELD).limit(limit).order('id asc').select()
    count = yf.M('tasks').where('status!=?', (1,)).count()

    rdata = {}
    rdata['list'] = task_list
    rdata['count'] = count
    return rdata


def setTaskStatus(task_id,status = 0):
    yf.M('tasks').where('id=?',(task_id,)).update({'status':status})
    return True

def setTaskData(id, start = None,end = None):
    if start is not None:
        yf.M('tasks').where('id=?',(id,)).update({'start':start})
    if end is not None:
        yf.M('tasks').where('id=?',(id,)).update({'end':end})
    return True