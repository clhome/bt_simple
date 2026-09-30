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
import os


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
    if not yf.makeDirs(archive_dir):
        raise Exception('归档目录不可用: %s' % archive_dir)
    stamp = yf.formatDate().replace('-', '').replace(':', '').replace(' ', '_')
    base = archive_dir + '/panel_logs_%s' % stamp
    path = base + '.json'
    # 时间戳只精确到秒：同一秒内重复归档必须另起文件名，
    # 否则后一次（此时表已空）会覆盖前一次，旧归档凭空消失。
    seq = 1
    while os.path.exists(path):
        path = '%s_%d.json' % (base, seq)
        seq += 1

    content = yf.getJson({
        'archived_at': yf.formatDate(),
        'count': len(rows),
        'rows': rows,
    })
    # writeFile 失败时**返回 False 而不抛异常**，忽略返回值会导致
    # 「归档没落盘、日志照样被清空」的不可逆丢失（实测复现过）。
    if not yf.writeFile(path, content):
        raise Exception('归档文件写入失败: %s' % path)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise Exception('归档文件为空: %s' % path)

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
    # 入参容错：非法页号/行数回退默认值，避免上层 int() 抛 ValueError 直接 500；
    # 行数上限 200，防止 size 无上限地拉全表（性能/内存）。
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        size = max(1, min(200, int(size)))
    except (TypeError, ValueError):
        size = 10

    search = (search or '').strip()
    field = 'id,type,log,uid,ip,add_time'

    if search:
        # 参数化查询：原实现把 search 直接拼进 SQL（注入）
        where = 'type like ? or log like ?'
        params = ('%' + search + '%', '%' + search + '%')
        count = yf.M('logs').where(where, params).count()
        logs_list = (yf.M('logs').field(field)
                     .where(where, params)
                     .limit('%d,%d' % ((page - 1) * size, size))
                     .order('id desc').select())
    else:
        count = yf.M('logs').count()
        logs_list = (yf.M('logs').field(field)
                     .limit('%d,%d' % ((page - 1) * size, size))
                     .order('id desc').select())

    data = {}
    data['list'] = logs_list if isinstance(logs_list, list) else []
    data['count'] = count
    # 回传规范化后的分页参数：调用方（分页组件）必须与 SQL 用同一套值，
    # 否则非法入参会在分页组件里被二次 int() 解析并抛错。
    data['page'] = page
    data['size'] = size
    return data