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

__FIELD = 'id,pid,name,port,add_time'

def getDomainCountByName(name):
    # .debug(True)
    return yf.M('domain').where("name=?", (name,)).count()

def getDomainCountBySiteId(site_id):
    # .debug(True)
    return yf.M('domain').where("pid=?", (site_id,)).count()

def addDomain(site_id, name, port):
    now_time = yf.getDateFromNow()
    insert_data = {
        'pid': site_id,
        'name': name,
        'port':port,
        'add_time': now_time,
    }
    return yf.M('domain').insert(insert_data)
    
def getDomainBySiteId(site_id):
    # .debug(True)
    return yf.M('domain').field(__FIELD).where("pid=?", (site_id,)).select()
    

def deleteDomainId(domain_id):
    return yf.M('domain').where("id=?", (domain_id,)).delete()

def deleteDomainBySiteId(site_id):
    return yf.M('domain').where("pid=?", (site_id,)).delete()
