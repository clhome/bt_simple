# coding:utf-8

import sys
import os
import time
import json
import logging

_log = logging.getLogger('yf')

# 自适应定位面板 web 目录并注入环境
cur_dir = os.path.dirname(os.path.abspath(__file__))
panel_dir = os.path.dirname(os.path.dirname(cur_dir))
web_dir = os.path.join(panel_dir, "web")
if os.path.exists(web_dir) and web_dir not in sys.path:
    sys.path.insert(0, web_dir)

import core.yf as yf
from utils.crontab import crontab as YfCrontab

TASK_NAME = "[勿删]御风JDK在线版本同步"


def getPluginName():
    return 'jdk'


def getPluginDir():
    return cur_dir


def getServerDir():
    srv = yf.getServerDir() + '/' + getPluginName()
    return srv


def getTaskConf():
    s_dir = getServerDir()
    if os.path.exists(s_dir):
        return os.path.join(s_dir, "task_config.json")
    return os.path.join(getPluginDir(), "task_config.json")


def getConfigData():
    conf = getTaskConf()
    if os.path.exists(conf):
        try:
            content = yf.readFile(conf)
            if content:
                data = json.loads(content)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            # 配置文件损坏时回退默认值
            return {
                "task_id": -1,
                "period": "day",
                "where1": "",
                "hour": "2",
                "minute": "10",
            }

    return {
        "task_id": -1,
        "period": "day",
        "where1": "",
        "hour": "2",
        "minute": "10",
    }


def createBgTask():
    return createBgTaskByName(getPluginName())


def createBgTaskByName(name):
    cfg = getConfigData()

    # 构造定时任务 Bash 执行脚本（使用 tee -a 双向同步输出到文件与控制台，方便在计划任务弹窗中直接回显）
    yf_dir = yf.getPanelDir()
    script_path = getPluginDir()
    server_dir = getServerDir()
    log_dir = server_dir if os.path.exists(server_dir) else script_path
    log_file = os.path.join(log_dir, "jdk_sync.log").replace('\\', '/')

    cmd = '''yf_dir=%s
script_path=%s
logs_file=%s
''' % (yf_dir, script_path.replace('\\', '/'), log_file)
    cmd += 'echo "★【`date +"%Y-%m-%d %H:%M:%S"`】 START★" | tee -a "$logs_file"\n'
    cmd += 'echo ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>" | tee -a "$logs_file"\n'
    cmd += 'if [ -f "$yf_dir/bin/activate" ]; then\n'
    cmd += '    cd "$yf_dir" && source bin/activate\n'
    cmd += 'fi\n'
    cmd += 'python3 "$script_path/tool_task.py" run 2>&1 | tee -a "$logs_file"\n'
    cmd += 'echo "【`date +"%Y-%m-%d %H:%M:%S"`】 END★" | tee -a "$logs_file"\n'
    cmd += 'echo "<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" | tee -a "$logs_file"\n'

    # 1. 查询数据库中是否已存在同名任务
    res = yf.M("crontab").field("id, name, echo, sbody").where("name=?", (TASK_NAME,)).find()
    if res and res.get("id"):
        task_id = int(res["id"])
        if cfg.get("task_id") != task_id:
            cfg["task_id"] = task_id
            yf.writeFile(getTaskConf(), json.dumps(cfg))
        # 平滑升级：若数据库中的脚本仍是旧版单向重定向，自动同步为带实时控制台回显的脚本
        if res.get("sbody") != cmd:
            try:
                yf.M("crontab").where("id=?", (task_id,)).save({"sbody": cmd})
                YfCrontab.instance().syncToCrond(task_id)
            except Exception as _e:
                _log.debug('[jdk] syncToCrond update failed: %s', _e)
        return True

    # 2. 如果配置中记录过 task_id，二次检查该 ID 是否依然有效
    if "task_id" in cfg and cfg["task_id"] > 0:
        res = yf.M("crontab").field("id, name, sbody").where("id=?", (cfg["task_id"],)).find()
        if res and res.get("id") == cfg["task_id"]:
            if res.get("sbody") != cmd:
                try:
                    yf.M("crontab").where("id=?", (cfg["task_id"],)).save({"sbody": cmd})
                    YfCrontab.instance().syncToCrond(cfg["task_id"])
                except Exception as _e:
                    _log.debug('[jdk] syncToCrond update failed: %s', _e)
            return True

    params = {
        'name': TASK_NAME,
        'type': cfg.get('period', 'day'),
        'week': '',
        'where1': str(cfg.get('where1', '')),
        'hour': str(cfg.get('hour', '2')),
        'minute': str(cfg.get('minute', '10')),
        'save': '',
        'backup_to': '',
        'stype': 'toShell',
        'sname': '',
        'sbody': cmd,
        'url_address': '',
    }

    task_id = YfCrontab.instance().add(params)
    if task_id and int(task_id) > 0:
        cfg["task_id"] = int(task_id)
        yf.writeFile(getTaskConf(), json.dumps(cfg))
        return True
    return False


def removeBgTask():
    cfg = getConfigData()
    task_id = cfg.get("task_id", -1)

    # 1. 按 ID 删除
    if task_id > 0:
        res = yf.M("crontab").field("id, name").where("id=?", (task_id,)).find()
        if res and res.get("id") == task_id:
            data = YfCrontab.instance().delete(task_id)
            if data and data.get('status'):
                cfg["task_id"] = -1
                yf.writeFile(getTaskConf(), json.dumps(cfg))
                return True

    # 2. 按名称兜底清理残留
    res = yf.M("crontab").field("id, name").where("name=?", (TASK_NAME,)).find()
    if res and res.get("id"):
        data = YfCrontab.instance().delete(int(res["id"]))
        cfg["task_id"] = -1
        yf.writeFile(getTaskConf(), json.dumps(cfg))
        return bool(data and data.get('status'))

    cfg["task_id"] = -1
    yf.writeFile(getTaskConf(), json.dumps(cfg))
    return True


def _get_jdk_main_class():
    try:
        from plugins.jdk.index import jdk_main
        return jdk_main
    except ImportError as e:
        if cur_dir not in sys.path:
            sys.path.insert(0, cur_dir)
        try:
            import index as jdk_index
            return getattr(jdk_index, 'jdk_main', None)
        except Exception as err:
            return None


def run():
    now_str = time.strftime('%Y-%m-%d %H:%M:%S')
    print("[%s] [INFO] 开始执行御风JDK在线版本库自动同步..." % now_str)

    try:
        main_cls = _get_jdk_main_class()
        if not main_cls:
            print("[%s] [ERROR] 无法加载 jdk_main 类，中止同步" % now_str)
            return False

        inst = main_cls()
        # 强制穿透刷新抓取清华/Adoptium最新版本并更新 versions.json
        online_list = inst.get_online_jdks(force_update=True)
        if online_list and isinstance(online_list, list):
            print("[%s] [SUCCESS] 在线版本库同步完成，当前可用版本列表：" % time.strftime('%Y-%m-%d %H:%M:%S'))
            for item in online_list:
                ver = item.get('version', '')
                url = item.get('url', '')
                filename = os.path.basename(url) if url else ''
                rel_date = item.get('release_date', '')
                print("  - %s: %s (发布时间: %s)" % (ver, filename, rel_date or '-'))
            return True
        else:
            print("[%s] [WARN] 未获取到有效在线版本，保留本地预设基准版本" % time.strftime('%Y-%m-%d %H:%M:%S'))
            return False
    except Exception as e:
        print("[%s] [ERROR] 在线版本库同步过程中发生异常: %s" % (time.strftime('%Y-%m-%d %H:%M:%S'), str(e)))
        return False


def status():
    cfg = getConfigData()
    res = yf.M("crontab").field("id, name, status").where("name=?", (TASK_NAME,)).find()
    cache_file = os.path.join(getPluginDir(), 'versions.json')
    cache_exists = os.path.exists(cache_file)
    cache_mtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(cache_file))) if cache_exists else '无'

    info = {
        "task_name": TASK_NAME,
        "configured_task_id": cfg.get("task_id", -1),
        "db_task": res if res else None,
        "versions_cache_exists": cache_exists,
        "versions_cache_mtime": cache_mtime,
    }
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return info


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else 'run'
    if action == 'run':
        run()
    elif action == 'add':
        if createBgTask():
            print("计划任务添加/已确认: %s" % TASK_NAME)
        else:
            print("计划任务添加失败")
            sys.exit(1)
    elif action == 'remove':
        if removeBgTask():
            print("计划任务已移除: %s" % TASK_NAME)
        else:
            print("计划任务移除失败")
            sys.exit(1)
    elif action == 'status':
        status()
    else:
        print("Usage: python3 tool_task.py {run|add|remove|status}")
        sys.exit(1)

