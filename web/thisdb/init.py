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

import core.yf as yf


def initPanelData():
    is_reload = False
    sql_file = yf.getPanelDir() + '/web/admin/setup/sql/default.sql'
    sql_file_md5 = yf.getPanelDir() + '/web/admin/setup/sql/default.md5'
    content = yf.readFile(sql_file)
    content_md5 = yf.md5(content)
    if not os.path.exists(sql_file_md5):
        yf.writeFile(sql_file_md5, content_md5)

    sql = yf.M().dbPos(yf.getPanelDataDir(),'panel')
    csql_data = content.split(';')
    for i in range(len(csql_data)):
        sql.execute(csql_data[i], ())
    return True

def reinstallPanelData():
    is_reload = False
    sql_file = yf.getPanelDir() + '/web/admin/setup/sql/default.sql'
    sql_file_md5 = yf.getPanelDir() + '/web/admin/setup/sql/default.md5'
    content = yf.readFile(sql_file)
    content_md5 = yf.md5(content)
    if not os.path.exists(sql_file_md5):
        yf.writeFile(sql_file_md5, content_md5)

    content_src_md5 = yf.readFile(sql_file)
    if content_md5 != content_src_md5:
        is_reload = True

    __dbfile = yf.getPanelDataDir() + '/panel.db'
    if os.path.exists(__dbfile) and not is_reload:
        return True
    sql = yf.M().dbPos(yf.getPanelDataDir(),'panel')
    csql_data = content.split(';')
    for i in range(len(csql_data)):
        # print(csql_data[i])
        # print(sql.execute(csql_data[i], ()))
        sql.execute(csql_data[i], ())

    yf.writeFile(sql_file_md5, content_md5)
    return True