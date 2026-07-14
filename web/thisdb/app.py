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

__FIELD = 'id,app_id,app_secret,white_list,status,add_time,update_time'

def addApp(app_id,app_secret,white_list):
    now_time = yf.getDateFromNow()
    add_data = {
        'app_id': app_id,
        'app_secret': app_secret,
        'status': 1,
        'white_list':white_list,
        'add_time': now_time,
        'update_time': now_time
    }
    return yf.M('app').insert(add_data)

def getAppList(page=1,size=10):  
    m = yf.M('app').field(__FIELD)

    start = (int(page) - 1) * (int(size))
    limit = str(start) + ',' +str(size)
    app_list = m.limit(limit).order('id desc').select()
    count = m.count()

    data = {}
    data['list'] = app_list
    data['count'] = count
    return data

def getAppById(aid):
    return yf.M('app').field(__FIELD).where("id=?", (aid,)).find()

def getAppByAppId(app_id):
    return yf.M('app').field(__FIELD).where("app_id=?", (app_id,)).find()

def deleteAppById(aid):
    return yf.M('app').where("id=?", (aid,)).delete()

def toggleAppStatus(aid):
    info = yf.M('app').field(__FIELD).where("id=?", (aid,)).find()
    if info['status'] == 1:
        return yf.M('app').where('id=?',(aid,)).update({'status':0})
    return yf.M('app').where('id=?',(aid,)).update({'status':1})


def setAppData(aid, status=None, app_id=None, app_secret=None):
    up_data = {}
    if status is not None:
        up_data['status'] = status
    if app_id is not None:
        up_data['app_id'] = app_id
    if app_secret is not None:
        up_data['app_secret'] = app_secret
    return yf.M('app').where('id=?',(aid,)).update(up_data)
