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
from utils.crontab import crontab as MwCrontab


app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'clean'


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
        "period": "day-n",
        "where1": "7",
        "hour": "0",
        "minute": "15",
    }


def createBgTask():
    removeBgTask()
    createBgTaskByName(getPluginName())


def createBgTaskByName(name):
    args = getConfigData()
    _name = "[勿删]日志清理[" + name + "]"
    res = yf.M("crontab").field("id, name").where("name=?", (_name,)).find()
    if res:
        return True

    if "task_id" in args and args["task_id"] > 0:
        res = yf.M("crontab").field("id, name").where(
            "id=?", (args["task_id"],)).find()
        if res and res["id"] == args["task_id"]:
            print("计划任务已经存在!")
            return True

    mw_dir = yf.getPanelDir()
    cmd = '''
mw_dir=%s
rname=%s
plugin_path=%s
script_path=%s
logs_file=$plugin_path/${rname}.log
''' % (mw_dir, name, getServerDir(), getPluginDir())
    cmd += 'echo "★【`date +"%Y-%m-%d %H:%M:%S"`】 STSRT★" >> $logs_file' + "\n"
    cmd += 'echo ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>" >> $logs_file' + "\n"
    cmd += 'echo "python3 $script_path/index.py clean >> $logs_file 2>&1"' + "\n"
    cmd += 'cd $mw_dir && python3 $script_path/index.py clean >> $logs_file 2>&1' + "\n"
    cmd += 'echo "【`date +"%Y-%m-%d %H:%M:%S"`】 END★" >> $logs_file' + "\n"
    cmd += 'echo "<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" >> $logs_file' + "\n"

    params = {
        'name': _name,
        'type': args['period'],
        'week': "",
        'where1': args['where1'],
        'hour': args['hour'],
        'minute': args['minute'],
        'save': "",
        'backup_to': "",
        'stype': "toShell",
        'sname': '',
        'sbody': cmd,
        'url_address': '',
    }

    task_id = MwCrontab.instance().add(params)
    if task_id > 0:
        args["task_id"] = task_id
        args["name"] = name
        yf.writeFile(getTaskConf(), json.dumps(args))


def removeBgTask():
    cfg = getConfigData()
    if "task_id" in cfg and cfg["task_id"] > 0:
        res = yf.M("crontab").field("id, name").where(
            "id=?", (cfg["task_id"],)).find()
        if res and res["id"] == cfg["task_id"]:
            data = MwCrontab.instance().delete(cfg["task_id"])
            if data["status"]:
                cfg["task_id"] = -1
                yf.writeFile(getTaskConf(), json.dumps(cfg))
                return True
    return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        action = sys.argv[1]
        if action == "remove":
            removeBgTask()
        elif action == "add":
            createBgTask()
