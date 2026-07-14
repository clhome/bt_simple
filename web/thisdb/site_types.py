# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

__FIELD = 'id,name'

import core.yf as yf

def addSiteTypes(name):
    return yf.M('site_types').add("name", (name,))

def getSiteTypesCount():
    return yf.M('site_types').count()

def getSiteTypesCountByName(name):
    return yf.M('site_types').where('name=?', (name,)).count()

def getSiteTypesList():
    # .debug(True)
    return yf.M('site_types').field(__FIELD).order("id asc").select()


