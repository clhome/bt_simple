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

import core.yf as yf
import logging

_log = logging.getLogger('yf.thisdb.crontab')

__field = 'id,name,type,where1,where_hour,where_minute,echo,status,save,backup_to,stype,sname,sbody,url_address,attr,day_type,min_start_en,min_start_h,min_start_m,min_end_en,min_end_h,min_end_m,last_run_time,add_time,update_time'

# ORDER BY 是直接拼进 SQL 的（无法参数化），只能白名单：
# 不校验就等于把排序列开给任意 SQLite 表达式。
__order_fields = ('id', 'name', 'type', 'where1', 'where_hour', 'where_minute', 'echo',
                  'status', 'save', 'backup_to', 'stype', 'sname', 'last_run_time',
                  'add_time', 'update_time', 'day_type')

# 尝试增加 last_run_time 字段 (迁移逻辑)
try:
    yf.M('crontab').execute("ALTER TABLE crontab ADD COLUMN last_run_time TEXT")
except Exception as _e:
    _log.debug('[thisdb.crontab] 添加 last_run_time 列失败（通常为已存在）: %s', _e)

# 尝试增加 day_type 字段 (迁移逻辑)
try:
    yf.M('crontab').execute("ALTER TABLE crontab ADD COLUMN day_type INTEGER DEFAULT 0")
except Exception as _e:
    _log.debug('[thisdb.crontab] 添加 day_type 列失败（通常为已存在）: %s', _e)

# 尝试增加 min_start/end 相关字段 (迁移逻辑)
for col, ctype in [("min_start_en", "INTEGER DEFAULT 0"), ("min_start_h", "INTEGER DEFAULT 0"), ("min_start_m", "INTEGER DEFAULT 0"), ("min_end_en", "INTEGER DEFAULT 0"), ("min_end_h", "INTEGER DEFAULT 23"), ("min_end_m", "INTEGER DEFAULT 59")]:
    try:
        yf.M('crontab').execute(f"ALTER TABLE crontab ADD COLUMN {col} {ctype}")
    except Exception as _e:
        _log.debug('[thisdb.crontab] 添加列 %s 失败（通常为已存在）: %s', col, _e)

def addCrontab(data):
    now_time = yf.formatDate()
    data['add_time'] = now_time
    data['update_time'] = now_time
    if 'day_type' not in data:
        data['day_type'] = 0
    return yf.M('crontab').insert(data)

def getCronByName(name):
    return yf.M('crontab').where("name=?", (name,)).find()

def setCrontabData(cron_id, data):
    yf.M('crontab').where('id=?', (cron_id,)).update(data)
    return True

def setCrontabStatus(cron_id, status):
    yf.M('crontab').where('id=?', (cron_id,)).update({'status':status})
    return True

def getCrond(id):
    return yf.M('crontab').where('id=?', (id,)).field(__field).find()

def deleteCronById(cron_id):
    yf.M('crontab').where("id=?", (cron_id,)).delete()
    return True

def getCrontabList(
    page = 1,
    size = 10,
    search = '',
    orderby = 'last_run_time',
    order = 'desc'
):
    try:
        page = max(int(page), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = 10
    size = min(max(size, 1), 1000)

    start = (page - 1) * size
    limit = str(start) + ',' + str(size)

    if orderby not in __order_fields:
        orderby = 'last_run_time'
    if str(order).lower() not in ('asc', 'desc'):
        order = 'desc'

    order_str = orderby + ' ' + str(order).lower()

    m = yf.M('crontab')
    if search != '':
        m = m.where("name LIKE ?", ('%' + search + '%',))
    
    cron_list = m.field(__field).limit(limit).order(order_str).select()

    m_count = yf.M('crontab')
    if search != '':
        m_count = m_count.where("name LIKE ?", ('%' + search + '%',))
    count = m_count.count()

    data = {}
    data['count'] = count
    data['list'] = cron_list
    return data

