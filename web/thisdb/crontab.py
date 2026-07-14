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

import core.yf as mw

__field = 'id,name,type,where1,where_hour,where_minute,echo,status,save,backup_to,stype,sname,sbody,url_address,attr,day_type,last_run_time,add_time,update_time'

# 尝试增加 last_run_time 字段 (迁移逻辑)
try:
    mw.M('crontab').execute("ALTER TABLE crontab ADD COLUMN last_run_time TEXT")
except:
    pass

# 尝试增加 day_type 字段 (迁移逻辑)
try:
    mw.M('crontab').execute("ALTER TABLE crontab ADD COLUMN day_type INTEGER DEFAULT 0")
except:
    pass

def addCrontab(data):
    now_time = mw.formatDate()
    data['add_time'] = now_time
    data['update_time'] = now_time
    if 'day_type' not in data:
        data['day_type'] = 0
    return mw.M('crontab').insert(data)

def getCronByName(name):
    return mw.M('crontab').where("name=?", (name,)).find()

def setCrontabData(cron_id, data):
    mw.M('crontab').where('id=?', (cron_id,)).update(data)
    return True

def setCrontabStatus(cron_id, status):
    mw.M('crontab').where('id=?', (cron_id,)).update({'status':status})
    return True

def getCrond(id):
    return mw.M('crontab').where('id=?', (id,)).field(__field).find()

def deleteCronById(cron_id):
    mw.M('crontab').where("id=?", (cron_id,)).delete()
    return True

def getCrontabList(
    page = 1,
    size = 10,
    search = '',
    orderby = 'last_run_time',
    order = 'desc'
):
    start = (int(page) - 1) * size
    limit = str(start) + ',' + str(size)

    if orderby == '':
        orderby = 'last_run_time'
    if order == '':
        order = 'desc'

    order_str = orderby + ' ' + order

    m = mw.M('crontab')
    if search != '':
        m = m.where("name LIKE ?", ('%' + search + '%',))
    
    cron_list = m.field(__field).limit(limit).order(order_str).select()

    m_count = mw.M('crontab')
    if search != '':
        m_count = m_count.where("name LIKE ?", ('%' + search + '%',))
    count = m_count.count()

    data = {}
    data['count'] = count
    data['list'] = cron_list
    return data

