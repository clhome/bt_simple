# coding:utf-8

import sys
import io
import os
import time
import re

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.mw as mw
import json

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'task_manager'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()

def getArgs():
    args = sys.argv[3:]
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        t = args[0].strip('{').strip('}')
        if t.strip() == '':
            tmp = {}
        else:
            try:
                tmp = json.loads(args[0])
            except:
                t_arr = t.split(':', 1)
                if len(t_arr) == 2:
                    tmp[t_arr[0]] = t_arr[1]
    elif args_len > 1:
        for i in range(len(args)):
            t_arr = args[i].split(':', 1)
            if len(t_arr) == 2:
                tmp[t_arr[0]] = t_arr[1]
    return tmp

def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '参数:(' + ck[i] + ')没有!'))
    return (True, yf.returnJson(True, 'ok'))

def status():
    return 'start'


if __name__ == "__main__":
    func = sys.argv[1]
    if func == 'status':
        print(status())
    else:
        print('error')
