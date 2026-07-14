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

from .option  import getOption

__FIELD = 'id,name,path,status,ps,edate,type_id,add_time,update_time'

def checkSitesDomainIsExist(domain, port):
    nums = yf.M('domain').where("name=? AND port=?", (domain, port,)).count()
    if nums>0:
        return True

    nums = yf.M('binding').where("name=? AND port=?", (domain, port,)).count()
    if nums>0:
        return True
    return False

def getSitesCount():
    return yf.M('sites').count()

def getSitesById(site_id):
    return yf.M('sites').field(__FIELD).where("id=?", (site_id,)).find()

def getSitesByName(site_name):
    return yf.M('sites').field(__FIELD).where("name=?", (site_name,)).find()

def getSitesDomainById(site_id):
    data = {}
    domains = yf.M('domain').where('pid=?', (site_id,)).field('name,id').select()
    binding = yf.M('binding').where('pid=?', (site_id,)).field('domain,id').select()
    for b in binding:
        t = {}
        t['name'] = b['domain']
        t['id'] = b['id']
        domains.append(t)
    data['domains'] = domains
    data['email'] = getOption('ssl_email', default='')
    return data

def addSites(name, path, ps=None):
    now_time = yf.getDateFromNow()
    if ps is None:
        ps = name
    insert_data = {
        'name': name,
        'path': path,
        'status': 1,
        'ps': ps,
        'type_id':0,
        'edate':'0000-00-00',
        'add_time': now_time,
        'update_time': now_time
    }
    return yf.M('sites').insert(insert_data)


def isSitesExist(name):
    if yf.M('sites').where("name=?", (name,)).count() > 0:
        return True
    return False

def getSitesEdateList(edate):
    elist = yf.M('sites').field(__FIELD).where('edate>? AND edate<? AND status=?', ('0000-00-00', edate, 1,)).select()
    return elist

def getSitesList(
    page = 1,
    size = 10,
    type_id = 0,
    search = '',
    order = None,
):
    sql_where = ''
    if search != '' :
        sql_where = " name like '%" + search + "%' or ps like '%" + search + "%' "
    if type_id != '' and int(type_id) >= 0 and search != '' :
        sql_where = sql_where + " and type_id=" + str(type_id) + ""
    if type_id != '' and int(type_id) >= 0:
        sql_where = " type_id=" + str(type_id)

    dbM = dbC = yf.M('sites').field(__FIELD)

    if sql_where != '':
        count = dbC.where(sql_where).count()
        dbM.where(sql_where)
    else:
        count = dbC.count()

    start = (int(page) - 1) * (int(size))
    limit = str(start) + ',' +str(size)

    # 修改排序逻辑，确保status='0'（已停止）的网站总是在最后
    if order is None:
        order = ''
    else:
        order = str(order).strip()

    if order.find("none") > -1 or order == '':
        final_order = 'status desc, id desc'
    else:
        final_order = 'status desc, ' + order

    site_list = dbM.limit(limit).order(final_order).select()

    data = {}
    data['list'] = site_list
    data['count'] = count
    return data


def deleteSitesById(site_id):
    return yf.M('sites').where("id=?", (site_id,)).delete()

def setSitesData(site_id, edate = None, ps = None, path = None,status = None):
    update_data = {}
    if edate is not None:
        update_data['edate'] = edate
    if ps is not None:
        update_data['ps'] = ps

    if path is not None:
        update_data['path'] = path

    if status is not None:
        update_data['status'] = status

    return yf.M('sites').where('id=?',(site_id,)).update(update_data)

