# coding=utf-8
"""core.yf 子模块：textutil

本文件由 ``scripts/tools/split_yf_module.py`` 从原 ``web/core/yf.py`` 按 AST
行号机械搬迁而来（**未改写任何函数体**）。修改请直接改本文件，不要手工搬回去。
"""



import os
import sys
import time
import threading
import string
import json
import hashlib
import hmac
import shlex
import datetime
import subprocess
import glob
import base64
import re
import logging
from random import Random
import functools


def getRandomString(length):
    # 取随机字符串
    rnd_str = ''
    chars = 'AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz0123456789'
    chrlen = len(chars) - 1
    random = Random()
    for i in range(length):
        rnd_str += chars[random.randint(0, chrlen)]
    return rnd_str


def getUniqueId():
    """
    根据时间生成唯一ID
    :return:
    """
    current_time = datetime.datetime.now()
    str_time = current_time.strftime('%Y%m%d%H%M%S%f')[:-3]
    unique_id = "{0}".format(str_time)
    return unique_id


def getDate():
    # 取格式时间
    import time
    return time.strftime('%Y-%m-%d %X', time.localtime())


def getDateFromNow(tf_format="%Y-%m-%d %H:%M:%S", time_zone="Asia/Shanghai"):
    # 取格式时间
    import time
    if hasattr(time, 'tzset'):
        time.tzset()
    return time.strftime(tf_format, time.localtime())


def getDataFromInt(val):
    time_format = '%Y-%m-%d %H:%M:%S'
    time_str = time.localtime(val)
    return time.strftime(time_format, time_str)


def toSize(size, middle='') -> str:
    """
    字节单位转换
    """
    units = ('b', 'KB', 'MB', 'GB', 'TB')
    s = units[0]
    for u in units:
        if size < 1024:
            return str(round(size, 2)) + middle + u
        size = float(size) / 1024.0
        s = u
    return str(round(size, 2)) + middle + u


def formatDate(fmat="%Y-%m-%d %H:%M:%S", times=None, time_zone=None):
    # 格式化指定时间戳
    if not times:
        times = int(time.time())
    
    # if time_zone is None:
    #     try:
    #         import tzlocal
    #         time_zone = str(tzlocal.get_localzone())
    #     except:
    #         try:
    #             time_zone = time.tzname[0]
    #         except:
    #             time_zone = None
    
    if time_zone:
        old_tz = os.environ.get('TZ')
        os.environ['TZ'] = time_zone
        time.tzset()
        time_local = time.localtime(times)
        result = time.strftime(fmat, time_local)
        if old_tz:
            os.environ['TZ'] = old_tz
        else:
            del os.environ['TZ']
        time.tzset()
        return result
    else:
        time_local = time.localtime(times)
        return time.strftime(fmat, time_local)


def strfToTime(sdate):
    # 转换时间
    import time
    return time.strftime('%Y-%m-%d', time.strptime(sdate, '%b %d %H:%M:%S %Y %Z'))


def inArray(arrays, searchStr):
    # 搜索数据中是否存在
    for key in arrays:
        if key == searchStr:
            return True

    return False


def getFileSuffix(file):
    tmp = file.split('.')
    ext = tmp[len(tmp) - 1]
    return ext


def getPathSuffix(path):
    return os.path.splitext(path)[-1]


def getStrBetween(startStr, endStr, srcStr):
    # 字符串取中间
    start = srcStr.find(startStr)
    if start == -1:
        return None
    end = srcStr.find(endStr)
    if end == -1:
        return None
    return srcStr[start + 1:end]


def getLastLine(path, num, p=1):
    try:
        import html
        if not os.path.exists(path):
            return ""
        if num <= 0 or p <= 0:
            return ""

        file_size = os.path.getsize(path)
        if file_size == 0:
            return ""

        start_line = (p - 1) * num
        needed_count = start_line + num

        lines = []
        buf = b""
        block_size = 8192

        with open(path, 'rb') as fp:
            pos = file_size
            while pos > 0 and len(lines) < needed_count:
                read_size = min(block_size, pos)
                pos -= read_size
                fp.seek(pos)
                chunk = fp.read(read_size)
                buf = chunk + buf

                while b'\n' in buf:
                    idx = buf.rfind(b'\n')
                    line_bytes = buf[idx + 1:]
                    buf = buf[:idx]
                    if line_bytes or lines:
                        try:
                            line_str = line_bytes.decode('utf-8', errors='replace').rstrip('\r')
                        except Exception as _e:
                            line_str = str(line_bytes)
                        lines.append(html.escape(line_str))
                        if len(lines) >= needed_count:
                            break

            if buf and len(lines) < needed_count:
                try:
                    line_str = buf.decode('utf-8', errors='replace').rstrip('\r')
                except Exception as _e:
                    line_str = str(buf)
                lines.append(html.escape(line_str))

        paged_lines = lines[start_line:needed_count]
        paged_lines.reverse()
        return "\n".join(paged_lines)
    except Exception as e:
        return str(e)


def isNumber(s):
    # 判定型接口：非数字是正常分支而非错误，故不记日志（避免高频噪音）；
    # 先用 float，失败再试 unicode 数字（语义与原先完全一致）。
    try:
        float(s)
        return True
    except ValueError:
        try:
            import unicodedata
            unicodedata.numeric(s)
            return True
        except (TypeError, ValueError):
            return False


def getDefault(data,val,def_val=''):
    if val in data:
        return data[val]
    return def_val


# ---------------------------------------------------------------------------------
# 数据库 START
# ---------------------------------------------------------------------------------

##################### ssl start #########################################

def strfDate(sdate):
    return time.strftime('%Y-%m-%d', time.strptime(sdate, '%Y%m%d%H%M%S'))
