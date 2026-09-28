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


import core.yf as yf

def clearLog():
    yf.M('logs').where('id>?', (0,)).delete()
    yf.M('logs').execute("update sqlite_sequence set seq=0 where name='logs'")
    return True


def archiveLogs():
    """归档操作日志：**先导出到文件，再清空表**。

    为什么不再直接物理删除：`del_panel_logs` 原来是「一键抹掉全部操作痕迹」，
    管理员（或拿到会话的攻击者）可以借此消灭证据，审计合规直接不过。
    归档保留可追溯性；而归档动作本身会进审计流水（append-only），
    所以「何时、由谁执行了清空」仍然查得到。

    :return: (归档文件路径, 条数)；失败抛异常由调用方处理
    """
    rows = yf.M('logs').field('id,type,log,uid,ip,add_time').order('id asc').select()
    if not isinstance(rows, list):
        rows = []

    archive_dir = yf.getPanelDataDir() + '/log_archive'
    yf.makeDirs(archive_dir)
    stamp = yf.formatDate().replace('-', '').replace(':', '').replace(' ', '_')
    path = archive_dir + '/panel_logs_%s.json' % stamp
    yf.writeFile(path, yf.getJson({
        'archived_at': yf.formatDate(),
        'count': len(rows),
        'rows': rows,
    }))

    clearLog()
    return path, len(rows)


def addLog(type, log, uid = 1, ip = '') -> bool:
    '''
    添加日志
    :type -> str 类型 (必填)
    :log -> str 日志内容 (必填)
    :uid -> int 用户ID
    :ip -> str 来源 IP
    '''
    add_time = yf.formatDate()
    insert_data = {
        'type':type,
        'log':log,
        'uid':uid,
        'ip':ip,
        'add_time':add_time,
    }
    yf.M('logs').insert(insert_data)
    return True


def getLogsList(page = 1,size = 10,search = ''):
    sql_where = ''
    if search != '' :
        sql_where = " type like '%" + search + "%' or log like '%" + search + "%' "

    field = 'id,type,log,uid,ip,add_time'
    dbM = dbC = yf.M('logs').field(field)

    if sql_where != '':
        count = yf.M('logs').field(field).where(sql_where).count()
    else:
        count = yf.M('logs').field(field).count()

    start = (int(page) - 1) * (int(size))
    limit = str(start) + ',' +str(size)
    logs_list = yf.M('logs').field(field).limit(limit).order('id desc').select()

    data = {}
    data['list'] = logs_list
    data['count'] = count
    return data