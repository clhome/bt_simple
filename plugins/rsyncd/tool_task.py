# coding:utf-8

import sys
import io
import os
import time
import json
import logging

_log = logging.getLogger('yf.plugin.rsyncd')


web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
from utils.crontab import crontab as YfCrontab



app_debug = False
if yf.isAppleSystem():
    app_debug = True


def checkNameSafe(name):
    import re
    if not re.match(r'^[a-zA-Z0-9_\-]+$', name):
        return False
    return True


def getPluginName():
    return 'rsyncd'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getTaskConf():
    conf = getServerDir() + "/task_config.json"
    return conf


def getConfigData():
    conf = getTaskConf()
    if os.path.exists(conf):
        raw = yf.readFile(conf)
        # readFile 失败返回 False，旧实现直接 json.loads(False) → TypeError 崩溃
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    return data
            except Exception as e:
                _log.debug('[rsyncd] task_config.json 解析失败: %s', e)
    return []


def sendListFromConf():
    """从 config.json 取 send.list（CLI 手动重建计划任务时用）。"""
    raw = yf.readFile(getServerDir() + "/config.json")
    if not isinstance(raw, str):
        return []
    try:
        cfg = json.loads(raw)
    except Exception:
        return []
    if isinstance(cfg, dict) and isinstance(cfg.get('send'), dict) \
            and isinstance(cfg['send'].get('list'), list):
        return cfg['send']['list']
    return []


def getConfigTpl():
    tpl = {
        "name": "",
        "task_id": -1,
    }
    return tpl


def createBgTask(data=None):
    if data is None:
        data = sendListFromConf()
    if not isinstance(data, list):
        print("错误：同步任务列表格式非法！")
        return False
    removeBgTask()
    for d in data:
        if not isinstance(d, dict):
            continue
        if d.get('realtime') == "false":
            createBgTaskByName(d.get('name'), d)
    return True


def createBgTaskByName(name, args):
    if not checkNameSafe(name):
        print("错误：名称只能包含字母、数字、下划线和中划线！")
        return False
    cfg = getConfigTpl()
    _name = "[勿删]同步插件定时任务[" + name + "]"
    res = yf.M("crontab").field("id, name").where("name=?", (_name,)).find()
    if res:
        return True

    if "task_id" in cfg.keys() and cfg["task_id"] > 0:
        res = yf.M("crontab").field("id, name").where("id=?", (cfg["task_id"],)).find()
        if res and res["id"] == cfg["task_id"]:
            print("计划任务已经存在!")
            return True

    period = args.get('period')
    _hour = ''
    _minute = ''
    _where1 = ''
    _type_day = "day"
    if period == 'day':
        _type_day = 'day'
        _hour = args.get('hour', 0)
        _minute = args.get('minute', 0)
    elif period == 'minute-n':
        _type_day = 'minute-n'
        _where1 = args.get('minute-n', 1)
        _minute = ''
    else:
        # 旧实现直接 args['period'] → 缺键即 KeyError；周期非法也不得凭空建 day 任务
        print("错误：定时周期格式非法！")
        return False

    # name 已过白名单、getServerDir() 是受控绝对路径，仍统一 shell 引用
    cmd = '''
rname=%s
plugin_path=%s
logs_file=$plugin_path/send/${rname}/run.log
''' % (yf.shlexQuote(name), yf.shlexQuote(getServerDir()))
    cmd += 'echo "★【`date +"%Y-%m-%d %H:%M:%S"`】 STSRT" >> $logs_file' + "\n"
    cmd += 'echo ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>" >> $logs_file' + "\n"
    cmd += 'bash $plugin_path/send/${rname}/cmd >> $logs_file 2>&1' + "\n"
    cmd += 'echo "【`date +"%Y-%m-%d %H:%M:%S"`】 END★" >> $logs_file' + "\n"
    cmd += 'echo "<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" >> $logs_file' + "\n"

    params = {
        'name': _name,
        'type': _type_day,
        'week': "",
        'where1': _where1,
        'hour': _hour,
        'minute': _minute,
        'save': "",
        'backup_to': "",
        'stype': "toShell",
        'sname': '',
        'sbody': cmd,
        'url_address': '',
    }

    task_id = YfCrontab.instance().add(params)
    if task_id > 0:
        cfg["task_id"] = task_id
        cfg["name"] = name

        _dd = getConfigData()
        _dd.append(cfg)
        if not yf.writeFile(getTaskConf(), json.dumps(_dd)):
            print("错误：计划任务登记写入失败！")
            return False
        return True
    return False


def removeBgTask():
    """删除全部由本插件创建的计划任务。

    旧实现只删第一条命中的任务，却把 task_config.json 清成 '[]'：其余
    [勿删]同步插件定时任务[...] 的 crontab 行失去登记、永久残留并继续执行。
    """
    cfg_list = getConfigData()
    removed = 0
    for cfg in cfg_list:
        if not isinstance(cfg, dict):
            continue
        task_id = cfg.get('task_id', -1)
        if not isinstance(task_id, int) or task_id <= 0:
            continue
        res = yf.M("crontab").field("id, name").where("id=?", (task_id,)).find()
        if res and res["id"] == task_id:
            data = YfCrontab.instance().delete(task_id)
            if data[0]:
                removed += 1
    if cfg_list:
        yf.writeFile(getTaskConf(), '[]')
    return removed > 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        action = sys.argv[1]
        if action == "remove":
            removeBgTask()
        elif action == "add":
            createBgTask()
