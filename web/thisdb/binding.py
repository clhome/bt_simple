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

# 站点-子目录绑定

__FIELD = 'id,pid,domain,port,path,add_time'

def getBindingCountByDomain(name):
    # .debug(True)
    return yf.M('binding').where("domain=?", (name,)).count()

def addBinding(pid, domain, port, path):
    now_time = yf.getDateFromNow()
    insert_data = {
        'pid': pid,
        'domain': domain,
        'port':port,
        'path':path,
        'add_time': now_time,
    }
    return yf.M('binding').insert(insert_data)

def getBindingListBySiteId(site_id):
    # .debug(True)
    binding_list = yf.M('binding').field(__FIELD).where('pid=?', (site_id,)).select()
    return binding_list

def getBindingById(site_id):
    return yf.M('binding').where("id=?", (site_id,)).field(__FIELD).find()


def deleteBindingById(binding_id):
    return yf.M('binding').where("id=?", (binding_id,)).delete()

def deleteBindingBySiteId(site_id):
    return yf.M('binding').where("pid=?", (site_id,)).delete()
