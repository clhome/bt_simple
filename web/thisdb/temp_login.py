# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import time

import core.yf as yf

__FIELD = 'id,token,salt,state,login_time,login_addr,logout_time,expire,add_time'

def addTempLogin(token = None,expire = None):
    if expire is None:
        start_time = int(time.time())
        expire=start_time+3600

    if token is None:
        salt = yf.getRandomString(12)
        r = yf.getRandomString(48)
        token = yf.md5(r + salt)
    
    now_time = yf.formatDate()
    insert_data = {
        'token':token,
        'salt':'0',
        'state':0,
        'login_time':0,
        'login_addr':'',
        'expire':expire,
        'add_time':now_time,
    }

    return yf.M('temp_login').insert(insert_data)

def getTempLoginPage(page = 1,size = 10):
    start = (page - 1) * size
    limit = str(start) + ',' + str(size)
    tl_list = yf.M('temp_login').where('', ()).field(__FIELD).limit(limit).order('id desc').select()
    count = yf.M('temp_login').where('', ()).count()

    rdata = {}
    rdata['list'] = tl_list
    rdata['count'] = count
    return rdata

def getTempLoginByToken(token,
) -> None:
    '''
    获取用户信息通过用户名
    '''
    data = yf.M('temp_login').where('token=?', (token,)).field(__FIELD).order('id asc').find()
    return data

def deleteTempLoginById(id) :
    return yf.M('temp_login').where('id=?', (id,)).delete()

def clearTempLogin()->bool:
    '''
    清空过期数据
    '''

    now_time = int(time.time())
    yf.M('temp_login').where('expire<?', (now_time,)).delete()
    return True