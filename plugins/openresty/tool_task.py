# coding:utf-8

import sys
import io
import os
import time
import json

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
from utils.crontab import crontab as YfCrontab


app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'openresty'


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
        return json.loads(yf.readFile(getTaskConf()))
    return {
        "task_id": -1,
        "period": "minute-n",
        "where1": "3",
        "hour": "0",
        "minute": "0",
    }


def checkBgTaskStatus():
    _name = "[OpenResty]检查任务"
    res = yf.M("crontab").field("id, name, status").where("name=?", (_name,)).find()
    if res and res.get("id"):
        return True, res["id"], res.get("status", 1)

    cfg = getConfigData()
    if "task_id" in cfg and cfg["task_id"] > 0:
        res = yf.M("crontab").field("id, name, status").where(
            "id=?", (cfg["task_id"],)).find()
        if res and res["id"] == cfg["task_id"]:
            return True, res["id"], res.get("status", 1)

    return False, -1, 0


def createBgTask():
    removeBgTask()
    return createBgTaskByName(getPluginName())


def createBgTaskByName(name):
    args = getConfigData()
    _name = "[OpenResty]检查任务"
    res = yf.M("crontab").field("id, name").where("name=?", (_name,)).find()
    if res:
        args["task_id"] = res["id"]
        args["name"] = name
        yf.writeFile(getTaskConf(), json.dumps(args))
        return True

    if "task_id" in args and args["task_id"] > 0:
        res = yf.M("crontab").field("id, name").where(
            "id=?", (args["task_id"],)).find()
        if res and res["id"] == args["task_id"]:
            return True

    yf_dir = yf.getPanelDir()
    cmd = '''
yf_dir=%s
rname=%s
plugin_path=%s
script_path=%s
''' % (yf_dir, name, getServerDir(), getPluginDir())
    cmd += 'echo "bash $script_path/check.sh"' + "\n"
    cmd += 'cd $yf_dir && bash $script_path/check.sh' + "\n"

    params = {
        'name': _name,
        'type': args.get('period', 'minute-n'),
        'week': "",
        'where1': str(args.get('where1', '3')),
        'hour': str(args.get('hour', '0')),
        'minute': str(args.get('minute', '0')),
        'save': "",
        'backup_to': "",
        'stype': "toShell",
        'sname': '',
        'sbody': cmd,
        'url_address': '',
    }

    task_id = YfCrontab.instance().add(params)
    if task_id > 0:
        args["task_id"] = task_id
        args["name"] = name
        yf.writeFile(getTaskConf(), json.dumps(args))
        return True
    return False


def removeBgTask():
    cfg = getConfigData()
    task_id = -1
    _name = "[OpenResty]检查任务"
    res = yf.M("crontab").field("id, name").where("name=?", (_name,)).find()
    if res and res.get("id"):
        task_id = res["id"]
    elif "task_id" in cfg and cfg["task_id"] > 0:
        task_id = cfg["task_id"]

    success = False
    if task_id > 0:
        res = yf.M("crontab").field("id, name").where("id=?", (task_id,)).find()
        if res and res["id"] == task_id:
            data = YfCrontab.instance().delete(task_id)
            if data and data.get("status", False):
                success = True

    cfg["task_id"] = -1
    yf.writeFile(getTaskConf(), json.dumps(cfg))
    return success or True


if __name__ == "__main__":
    if len(sys.argv) > 1:
        action = sys.argv[1]
        if action == "remove":
            removeBgTask()
        elif action == "add":
            createBgTask()
        elif action == "status":
            print(checkBgTaskStatus())
