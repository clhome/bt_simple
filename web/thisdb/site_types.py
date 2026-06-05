# coding:utf-8

# ---------------------------------------------------------------------------------
# MW-Linux面板
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

__FIELD = 'id,name'

import core.mw as mw

def addSiteTypes(name):
    return mw.M('site_types').add("name", (name,))

def getSiteTypesCount():
    return mw.M('site_types').count()

def getSiteTypesCountByName(name):
    return mw.M('site_types').where('name=?', (name,)).count()

def getSiteTypesList():
    # .debug(True)
    return mw.M('site_types').field(__FIELD).order("id asc").select()


