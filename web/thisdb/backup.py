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

__FIELD = 'id,pid,type,name,filename,size,add_time'

def addBackup(pid,name,filename,size,type=0):

    add_time = yf.formatDate()
    insert_data = {
        'type':type,
        'name':name,
        'pid':pid,
        'filename':filename,
        'size':size,
        'add_time':add_time,
    }
    yf.M('backup').insert(insert_data)
    return True

def getBackupById(bp_id):
    return yf.M('backup').field(__FIELD).where("id=?", (bp_id,)).find()

def getBackupPage(site_id,page = 1,size = 10):
    start = (int(page) - 1) * int(size)
    limit = str(start) + ',' + str(size)
    bk_list = yf.M('backup').where('pid=?', (site_id,)).field(__FIELD).limit(limit).order('id desc').select()
    count = yf.M('backup').where('pid=?', (site_id,)).count()

    rdata = {}
    rdata['list'] = bk_list
    rdata['count'] = count
    return rdata

def deleteBackupById(bp_id):
    return yf.M('backup').where("id=?", (bp_id,)).delete()
