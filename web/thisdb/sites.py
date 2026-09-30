# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import re

import core.yf as yf

from .option  import getOption

__FIELD = 'id,name,path,status,ps,edate,type_id,add_time,update_time'

#: 列表排序只允许按站点表自己的列排（order 由前端传入，不能直接拼进 SQL）
_ORDER_FIELD = ('id', 'name', 'path', 'status', 'ps', 'edate', 'type_id',
                'add_time', 'update_time')
_ORDER_RE = re.compile(r'^([A-Za-z_]+)(\s+(asc|desc))?$', re.IGNORECASE)


def safeOrder(order):
    """排序子句白名单，不合法返回 ''（调用方回退默认排序）。"""
    order = str(order or '').strip()
    m = _ORDER_RE.match(order)
    if not m or m.group(1).lower() not in _ORDER_FIELD:
        return ''
    return order

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
    # search/type_id/order 都来自前端表单：
    #   旧实现把 search 直接拼进 WHERE、order 直接拼进 ORDER BY（SQL 注入）；
    #   而且 type_id >= 0 时会用 " type_id=N" 覆盖掉 search 条件，搜索框形同虚设。
    try:
        page = int(page)
    except Exception:
        page = 1
    try:
        size = int(size)
    except Exception:
        size = 10
    if page < 1:
        page = 1
    if size < 1:
        size = 10

    search = str(search or '').strip()
    where = ''
    params = []
    if search != '':
        where = "(name like ? or ps like ?)"
        params = ['%' + search + '%', '%' + search + '%']

    try:
        type_id = int(type_id)
    except Exception:
        type_id = -1
    if type_id >= 0:
        if where != '':
            where += ' and '
        where += 'type_id=?'
        params.append(type_id)

    dbC = yf.M('sites').field(__FIELD)
    if where != '':
        count = dbC.where(where, tuple(params)).count()
    else:
        count = dbC.count()

    start = (page - 1) * size
    limit = str(start) + ',' + str(size)

    # 修改排序逻辑，确保status='0'（已停止）的网站总是在最后
    final_order = safeOrder(order)
    if final_order == '':
        final_order = 'status desc, id desc'
    else:
        final_order = 'status desc, ' + final_order

    dbM = yf.M('sites').field(__FIELD)
    if where != '':
        dbM.where(where, tuple(params))
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

