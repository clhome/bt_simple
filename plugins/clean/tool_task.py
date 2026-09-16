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


def getPluginName():
    return 'clean'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getTaskConf():
    return getServerDir() + "/task_config.json"


def getDefaultConfig():
    return {
        "status": False,
        "task_id": -1,
        "period": "day-n",     # day, day-n, hour
        "where1": "7",         # 间隔天数
        "hour": "3",           # 凌晨 3 点执行
        "minute": "15",
        "retention_days": 7,   # 过期归档日志保留天数
        "size_threshold_mb": 0, # 活跃日志截断大小门槛 (0 为只要勾选均截断)
        "categories": ["web", "database", "runtime", "system", "cache"],
        "clean_journal": True,
        "clean_pkg_cache": True,
    }


def getConfigData():
    conf = getTaskConf()
    data = getDefaultConfig()
    if os.path.exists(conf):
        try:
            saved = json.loads(yf.readFile(conf))
            if isinstance(saved, dict):
                data.update(saved)
        except Exception:
            pass
    return data


def saveConfigData(cfg):
    conf = getTaskConf()
    server_dir = getServerDir()
    if not os.path.exists(server_dir):
        os.makedirs(server_dir, exist_ok=True)
    yf.writeFile(conf, json.dumps(cfg, ensure_ascii=False, indent=2))


def isTaskActive():
    """检查计划任务是否在底层数据库中有效存在"""
    cfg = getConfigData()
    task_id = cfg.get("task_id", -1)
    if task_id > 0:
        res = yf.M("crontab").field("id, name").where("id=?", (task_id,)).find()
        if res and res.get("id") == task_id:
            return True
    return False


def createBgTask(custom_cfg=None):
    """创建或更新自动清理计划任务"""
    cfg = getConfigData()
    if custom_cfg and isinstance(custom_cfg, dict):
        cfg.update(custom_cfg)

    # 先移除已有的旧任务，避免重复堆叠
    removeBgTask()

    _name = "[勿删]系统日志清理与磁盘瘦身[" + getPluginName() + "]"

    yf_dir = yf.getPanelDir()
    plugin_path = getPluginDir()
    server_path = getServerDir()
    log_file = server_path + "/clean.log"

    cmd = f'''# Log Clean & Disk Slim
yf_dir="{yf_dir}"
plugin_path="{plugin_path}"
log_file="{log_file}"

echo "★【`date +"%Y-%m-%d %H:%M:%S"`】 START 定时日志清理与磁盘瘦身★" >> $log_file
cd $yf_dir && python3 $plugin_path/index.py clean >> $log_file 2>&1
echo "【`date +"%Y-%m-%d %H:%M:%S"`】 END 清理完成★" >> $log_file
'''

    params = {
        'name': _name,
        'type': cfg.get('period', 'day-n'),
        'week': "",
        'where1': str(cfg.get('where1', '7')),
        'hour': str(cfg.get('hour', '3')),
        'minute': str(cfg.get('minute', '15')),
        'save': "",
        'backup_to': "",
        'stype': "toShell",
        'sname': '',
        'sbody': cmd,
        'url_address': '',
    }

    try:
        task_id = YfCrontab.instance().add(params)
        if task_id and int(task_id) > 0:
            cfg["task_id"] = int(task_id)
            cfg["status"] = True
            saveConfigData(cfg)

            # 记录服务守护启动就绪日志
            try:
                from clean_executor import append_run_log
                now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                ready_log = (
                    f"★【{now_str}】 后台定时守护任务已就绪 (Active)★\n"
                    f"> 计划任务: [ID:{task_id}] {_name}\n"
                    f"> 执行周期: 每隔 {cfg.get('where1', 7)} 天 ({str(cfg.get('hour', 3)).zfill(2)}:{str(cfg.get('minute', 15)).zfill(2)})\n"
                    f"> 归档保留: 过期 {cfg.get('retention_days', 7)} 天历史归档自动清理\n"
                    f"> 安全策略: 等保 2.0 / CIS 核心审计文件受控保护\n"
                    f"> 触发机制: 系统 Crontab 已接管定时调度，等待预定周期到达或手动点击【立即执行一次】\n"
                    + "-" * 72
                )
                append_run_log(ready_log)
            except Exception:
                pass

            return True, f"成功创建定时清理任务 [ID:{task_id}]"
        return False, "添加计划任务失败，未能返回任务 ID"
    except Exception as e:
        return False, f"添加计划任务发生异常: {str(e)}"


def removeBgTask():
    """安全移除自动清理计划任务"""
    cfg = getConfigData()
    task_id = cfg.get("task_id", -1)

    if task_id > 0:
        try:
            res = yf.M("crontab").field("id, name").where("id=?", (task_id,)).find()
            if res and res.get("id") == task_id:
                YfCrontab.instance().delete(task_id)
        except Exception:
            pass

    # 同时清理同名残留任务
    try:
        _name = "[勿删]系统日志清理与磁盘瘦身[" + getPluginName() + "]"
        old_tasks = yf.M("crontab").field("id, name").where("name=?", (_name,)).select()
        if old_tasks and isinstance(old_tasks, list):
            for t in old_tasks:
                YfCrontab.instance().delete(t['id'])
    except Exception:
        pass

    cfg["task_id"] = -1
    cfg["status"] = False
    saveConfigData(cfg)

    try:
        from clean_executor import append_run_log
        now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        stop_log = f"★【{now_str}】 后台定时守护任务已停止 (Inactive)★\n" + "-" * 72
        append_run_log(stop_log)
    except Exception:
        pass

    return True


if __name__ == "__main__":
    if len(sys.argv) > 1:
        action = sys.argv[1]
        if action == "remove":
            removeBgTask()
            print("ok")
        elif action == "add":
            createBgTask()
            print("ok")
