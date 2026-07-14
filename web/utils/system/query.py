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
import sys
import re
import time
import math
import psutil


import core.yf as yf

# --------------------------------------------  数据查询相关 --------------------------------------------
def get_sampling_condition(table, start, end):
    # 底层数据库级降采样：极大降低 Python 内存使用和字典拼装开销
    try:
        count = yf.M(table).dbPos(yf.getPanelDataDir(), 'system')\
            .where("addtime>=? AND addtime<=?", (start, end)).count()
        he = 1
        if count > 1000:
            he = 3
        if count > 10000:
            he = 15
        where_str = "addtime>=? AND addtime<=?"
        if he > 1:
            where_str += " AND (id % " + str(he) + ") = 0"
        return where_str
    except:
        return "addtime>=? AND addtime<=?"

# 格式化addtime列
def toAddtime(data, tomem=False):
    import time
    if tomem:
        import psutil
        mPre = (psutil.virtual_memory().total / 1024 / 1024) / 100
    length = len(data)
    he = 1
    if length > 100:
        he = 1
    if length > 1000:
        he = 3
    if length > 10000:
        he = 15
    if he == 1:
        for i in range(length):
            data[i]['addtime'] = time.strftime(
                '%m/%d %H:%M', time.localtime(float(data[i]['addtime'])))
            if tomem and data[i]['mem'] > 100:
                data[i]['mem'] = data[i]['mem'] / mPre

        return data
    else:
        count = 0
        tmp = []
        for value in data:
            if count < he:
                count += 1
                continue
            value['addtime'] = time.strftime(
                '%m/%d %H:%M', time.localtime(float(value['addtime'])))
            if tomem and value['mem'] > 100:
                value['mem'] = value['mem'] / mPre
            tmp.append(value)
            count = 0
        return tmp

# 格式化addtime列
def toUseAddtime(data):
    dlen = len(data)
    for i in range(dlen):
        data[i]['addtime'] = time.strftime('%m/%d %H:%M:%S', time.localtime(float(data[i]['addtime'])))
    return data

def getLoadAverageByDB(start, end):
    # 获取系统的负载统计信息
    where_str = get_sampling_condition('load_average', start, end)
    data = yf.M('load_average').dbPos(yf.getPanelDataDir(),'system')\
        .where(where_str, (start, end,))\
        .field('pro,one,five,fifteen,addtime')\
        .order('id asc').select()
    data = toUseAddtime(data)
    return data

def getDiskIoByDB(start, end):
    # 获取系统的磁盘IO统计信息
    where_str = get_sampling_condition('diskio', start, end)
    data = yf.M('diskio').dbPos(yf.getPanelDataDir(),'system')\
        .where(where_str, (start, end))\
        .field('read_count,write_count,read_bytes,write_bytes,read_time,write_time,addtime')\
        .order('id asc').select()
    data = toUseAddtime(data)
    return data

def getCpuIoByDB(start, end):
    # 获取系统的CPU/IO统计信息
    where_str = get_sampling_condition('cpuio', start, end)
    data = yf.M('cpuio').dbPos(yf.getPanelDataDir(),'system')\
        .where(where_str,(start, end))\
        .field('pro,mem,addtime')\
        .order('id asc').select()
    data = toUseAddtime(data)
    return data

def getNetworkIoByDB(start, end):
    # 获取系统网络IO统计信息
    # id,
    where_str = get_sampling_condition('network', start, end)
    data = yf.M('network').dbPos(yf.getPanelDataDir(),'system')\
        .where(where_str, (start, end))\
        .field('up,down,total_up,total_down,down_packets,up_packets,addtime')\
        .order('id asc').select()
    data = toUseAddtime(data)
    return data

# --------------------------------------------  数据查询相关 --------------------------------------------
