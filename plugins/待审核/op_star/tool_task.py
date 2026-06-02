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

import core.mw as mw
from utils.crontab import crontab as MwCrontab

def getPluginName():
    return 'op_star'

def getPluginDir():
    return mw.getPluginDir() + '/' + getPluginName()

def getServerDir():
    # 统一指向安装目录 /www/server/openstar
    return mw.getServerDir() + '/openstar'

def getTaskConf():
    return getServerDir() + "/task_config.json"

def getConfigData():
    conf = getTaskConf()
    if os.path.exists(conf):
        return json.loads(mw.readFile(conf))
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
    cfg = getConfigData()
    _name = "[勿删]OP高性能防火墙后台任务"
    res = mw.M("crontab").field("id, name").where("name=?", (_name,)).find()
    if res:
        return True

    if "task_id" in cfg.keys() and cfg["task_id"] > 0:
        res = mw.M("crontab").field("id, name").where(
            "id=?", (cfg["task_id"],)).find()
        if res and res["id"] == cfg["task_id"]:
            print("计划任务已经存在!")
            return True

    mw_dir = mw.getPanelDir()
    cmd = '''
mw_dir=%s
rname=%s
plugin_path=%s
script_path=%s
logs_file=$plugin_path/${rname}_task.log
''' % (mw_dir, name, getServerDir(), getPluginDir())
    cmd += 'echo "★【`date +"%Y-%m-%d %H:%M:%S"`】 START★" >> $logs_file' + "\n"
    cmd += 'echo ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>" >> $logs_file' + "\n"
    cmd += 'echo "cd $mw_dir && source bin/activate && python3 $script_path/tool_task.py run >> $logs_file 2>&1"' + "\n"
    cmd += 'cd $mw_dir && source bin/activate && python3 $script_path/tool_task.py run >> $logs_file 2>&1' + "\n"
    cmd += 'echo "【`date +"%Y-%m-%d %H:%M:%S"`】 END★" >> $logs_file' + "\n"
    cmd += 'echo "<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" >> $logs_file' + "\n"

    params = {
        'name': _name,
        'type': cfg['period'],
        'week': "",
        'where1': cfg['where1'],
        'hour': cfg['hour'],
        'minute': cfg['minute'],
        'save': "",
        'backup_to': "",
        'stype': "toShell",
        'sname': '',
        'sbody': cmd,
        'url_address': '',
    }

    task_id = MwCrontab.instance().add(params)
    if task_id > 0:
        cfg["task_id"] = task_id        
        mw.writeFile(getTaskConf(), json.dumps(cfg))

def removeBgTask():
    cfg = getConfigData()
    if "task_id" in cfg.keys() and cfg["task_id"] > 0:
        res = mw.M("crontab").field("id, name").where("id=?", (cfg["task_id"],)).find()
        if res and res["id"] == cfg["task_id"]:
            data = MwCrontab.instance().delete(cfg["task_id"])
            if data['status']:
                cfg["task_id"] = -1
                mw.writeFile(getTaskConf(), json.dumps(cfg))
                return True
    return False

def run():
    """
    自动清理 OpenStar 中多于 7 天的攻击日志
    """
    log_dir = getServerDir() + '/logs'
    if not os.path.exists(log_dir):
        print("日志文件夹不存在")
        return 'ok'

    now_t = time.time()
    # 7 天的时间秒数
    expire_sec = 7 * 24 * 3600
    
    print("开始清理过期日志...")
    for filename in os.listdir(log_dir):
        if not filename.endswith('.log') and not filename.endswith('.json'):
            continue
        filepath = os.path.join(log_dir, filename)
        if os.path.isfile(filepath):
            file_mtime = os.path.getmtime(filepath)
            if now_t - file_mtime > expire_sec:
                try:
                    os.remove(filepath)
                    print("已清理过期日志文件: " + filename)
                except Exception as e:
                    print("清理失败: " + str(e))
    print("清理完成。")
    return 'ok'

if __name__ == "__main__":
    if len(sys.argv) > 1:
        action = sys.argv[1]
        if action == "remove" or action == "stop":
            removeBgTask()
        elif action == "add" or action == "start":
            createBgTask()
        elif action == "run":
            run()
