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
import core.yf as mw
from utils.crontab import crontab
from croniter import croniter
from datetime import datetime
import thisdb

def cron_todb(data):
    rdata = {'type': 'day', 'where1': '', 'hour': '0', 'minute': '0'}
    
    if data[3] == "*" and data[2] != "*" and data[2].find('/') == -1:
        rdata['type'] = 'month'
        rdata['where1'] = data[2]
        rdata['hour'] = data[1] if data[1] != '*' else '0'
        rdata['minute'] = data[0] if data[0] != '*' else '0'
    elif data[3] == "*" and data[4] != "*" and data[4].find('/') == -1:
        rdata['type'] = 'week'
        rdata['where1'] = data[4]
        rdata['hour'] = data[1] if data[1] != '*' else '0'
        rdata['minute'] = data[0] if data[0] != '*' else '0'
    elif data[3] == "*" and data[4] == "*" and data[2] == "*" and data[1].find('/') == -1 and data[0].find('/') == -1:
        rdata['type'] = 'day'
        rdata['hour'] = data[1] if data[1] != '*' else '0'
        rdata['minute'] = data[0] if data[0] != '*' else '0'
    elif data[2].find("/") > -1:
        rdata['type'] = 'day-n'
        rdata['where1'] = data[2].split('/')[1] if '/' in data[2] else '1'
        rdata['hour'] = data[1] if data[1] != '*' else '0'
        rdata['minute'] = data[0] if data[0] != '*' else '0'
    elif data[1].find("/") > -1:
        rdata['type'] = 'hour-n'
        rdata['where1'] = data[1].split('/')[1] if '/' in data[1] else '1'
        rdata['minute'] = data[0] if data[0] != '*' else '0'
    elif data[0].find("/") > -1:
        rdata['type'] = 'minute-n'
        rdata['where1'] = data[0].split('/')[1] if '/' in data[0] else '1'
        rdata['minute'] = ''
        
    return rdata

def init_acme_cron():
    name = "[勿删]ACME定时强制更新"
    res = mw.M("crontab").field("id, name").where("name=?", (name,)).find()
    if res:
        return False

    cmd = "/root/.acme.sh/acme.sh --cron --force --standalone"
    params = {
        'name': name,
        'type': 'day-n',
        'week': "",
        'where1': "15",
        'hour': 4,
        'minute': 15,
        'save': "",
        'backup_to': "",
        'stype': "toShell",
        'sname': '',
        'sbody': cmd,
        'url_address': '',
        'attr':'',
    }

    crontab.instance().add(params)
    return True

def init_auto_update():
    name = "[可删]面板自动更新"
    res = mw.M("crontab").field("id, name").where("name=?", (name,)).find()
    if res:
        return False

    cmd = "mw update"
    params = {
        'name': name,
        'type': 'month',
        'week': "",
        'where1': "1",
        'hour': 4,
        'minute': 15,
        'save': "",
        'backup_to': "",
        'stype': "toShell",
        'sname': '',
        'sbody': cmd,
        'url_address': '',
        'attr':'',
    }

    crontab.instance().add(params)
    return True

# 识别linux计划任务
def init_cron():
    file = ''
    cron_file = [
        '/var/spool/cron/crontabs/root',
        '/var/spool/cron/root',
    ]
    for i in cron_file:
        if os.path.exists(i):
            file = i
            break

    if file == "":
        return 0

    count = 0
    with open(file) as f:
        for line in f.readlines():
            cron_line = line.strip()
            if cron_line.startswith("#") or not cron_line:
                continue

            parts = cron_line.split(maxsplit=5)
            if len(parts) < 6:
                continue
                
            cron_expression = parts[:5]
            command = parts[5]

            info = cron_todb(cron_expression)
            
            # 尝试识别面板生成的任务
            if command.find("/www/server/cron/") > -1:
                # 提取 hash (echo)
                # 例如 /www/server/cron/27ebacfd7e79a01c69c22d41a345ca58 >> ...
                try:
                    hash_val = command.split("/www/server/cron/")[1].split(" ")[0].strip()
                    res = mw.M('crontab').where('echo=?', (hash_val,)).find()
                    if not res:
                        # 尝试从文件中恢复 name, sbody 等（如果文件存在）
                        cron_path = mw.getServerDir() + '/cron/' + hash_val
                        sbody = ''
                        if os.path.exists(cron_path):
                            sbody = mw.readFile(cron_path)
                            
                        if not sbody:
                            sbody = command
                        
                        add_dbdata = {
                            'name': f'[恢复任务] {hash_val[-8:]}',
                            'type': info.get('type', 'day'),
                            'where1': info.get('where1', ''),
                            'where_hour': info.get('hour', '0'),
                            'where_minute': info.get('minute', '0'),
                            'save': "",
                            'backup_to': "",
                            'sname': "",
                            'sbody': sbody,
                            'stype': "toShell",
                            'echo': hash_val,
                            'url_address': ''
                        }
                        thisdb.addCrontab(add_dbdata)
                        count += 1
                except:
                    pass
            else:
                # 其它系统任务
                # 先根据 echo 匹配，避免重复
                res = mw.M('crontab').where('echo=?', (command,)).find()
                # 或者通过 sbody 匹配
                res2 = mw.M('crontab').where('sbody=?', (command,)).find()
                if not res and not res2:
                    name_prefix = command[:15] + '...' if len(command) > 15 else command
                    # 避免系统内置名称冲突
                    if mw.M('crontab').where('name=?', (f'[系统任务] {name_prefix}',)).find():
                        name_prefix += f"_{cron_expression[0]}"
                        
                    add_dbdata = {
                        'name': f'[系统任务] {name_prefix}',
                        'type': info.get('type', 'day'),
                        'where1': info.get('where1', ''),
                        'where_hour': info.get('hour', '0'),
                        'where_minute': info.get('minute', '0'),
                        'save': "",
                        'backup_to': "",
                        'sname': "",
                        'sbody': command,
                        'stype': "toShell",
                        'echo': command, # 使用原始命令作为echo标识
                        'url_address': ''
                    }
                    thisdb.addCrontab(add_dbdata)
                    count += 1

    return count

def sync_all_tasks():
    count = 0
    if init_acme_cron():
        count += 1
    if init_auto_update():
        count += 1
    
    count += init_cron()
    return count
