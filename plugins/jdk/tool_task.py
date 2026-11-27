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
    """确保「御风软件版本在线同步」系统任务存在（JDK 已并入统一同步任务）。

    历史背景：本插件曾自建一条 `[勿删]御风JDK在线版本同步`。OpenResty 也需要同形的
    在线版本同步后，两条几乎一样的系统任务只会让日志/状态分裂，故统一到
    `web/core/version_sync.py` 的一条任务里（`scripts/version_sync.py run`）。
    这里保留函数名，是因为 `plugins/jdk/index.py::_ensure_crontab_task()` 仍在调用。
    """
    try:
        from core.version_sync import ensure_task
    except ImportError:
        # 极端情况下（web 目录未进 sys.path）退化为「只建旧任务」，保证 JDK 仍能自愈
        return _create_legacy_bg_task()
    try:
        return bool(ensure_task(force=True))
    except Exception as _e:
        _log.debug('[jdk] ensure unified version-sync task failed: %s', _e)
        return False


def createBgTaskByName(name):
    """兼容旧调用点（name 参数已无意义，统一任务只有一条）。"""
    return createBgTask()


def _create_legacy_bg_task():
    """旧形态 JDK 单独任务（仅在统一引擎不可用时兜底）。"""
    cfg = getConfigData()
    yf_dir = yf.getPanelDir()
    script_path = getPluginDir().replace('\\', '/')
    log_file = os.path.join(getServerDir(), "jdk_sync.log").replace('\\', '/')

    cmd = '''yf_dir=%s
script_path=%s
logs_file=%s
''' % (yf_dir, script_path, log_file)
    cmd += 'if [ -f "$yf_dir/bin/activate" ]; then\n'
    cmd += '    cd "$yf_dir" && source bin/activate\n'
    cmd += 'fi\n'
    cmd += 'python3 "$script_path/tool_task.py" run 2>&1 | tee -a "$logs_file"\n'

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


def _norm_row(row):
    """计划任务查询结果归一化。

    面板 DB 层对 `field('id, name, ...')` 的多列查询会给后续列名带前导空格
    （实测 {'id': 5, ' name': ..., ' sbody': ...}），不归一化时 `row.get('name')`
    永远为 None。
    """
    if isinstance(row, dict):
        return {str(k).strip(): v for k, v in row.items()}
    return row


def removeBgTask():
    """只清理**历史 JDK 单独任务**；统一同步任务由用户显式删除。

    为什么不顺手删统一任务：它同时负责 OpenResty，卸载 JDK 插件不该连带停掉
    OpenResty 的版本情报同步。需要整体停用时用
    `python3 scripts/version_sync.py remove`。
    """
    cfg = getConfigData()
    task_id = cfg.get("task_id", -1)
    removed = False

    if task_id > 0:
        res = _norm_row(yf.M("crontab").field("id, name").where("id=?", (task_id,)).find())
        if res and res.get("id") == task_id and str(res.get("name") or "") == TASK_NAME:
            data = YfCrontab.instance().delete(task_id)
            removed = bool(data and data.get('status'))

    res = _norm_row(yf.M("crontab").field("id, name").where("name=?", (TASK_NAME,)).find())
    if res and res.get("id"):
        data = YfCrontab.instance().delete(int(res["id"]))
        removed = removed or bool(data and data.get('status'))

    cfg["task_id"] = -1
    yf.writeFile(getTaskConf(), json.dumps(cfg))
    return removed or True


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

    unified = None
    try:
        from core.version_sync import status as _vs_status
        unified = _vs_status()
    except Exception as _e:
        _log.debug('[jdk] 读取统一同步任务状态失败: %s', _e)

    info = {
        "task_name": TASK_NAME,
        "configured_task_id": cfg.get("task_id", -1),
        "db_task": res if res else None,
        "unified_task": (unified or {}).get('task'),
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

