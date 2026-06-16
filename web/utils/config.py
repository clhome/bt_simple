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
import json

import core.mw as mw
import thisdb

_menu_cache = None

def get_menu_config():
    global _menu_cache
    if _menu_cache is not None:
        return _menu_cache
        
    panel_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    menu_file = panel_dir + '/data/menu.json'
    if not os.path.exists(menu_file):
        default_menu = [
            {"id": "memuA", "name": "首页", "class": "menu_home", "url": "/", "show": True},
            {"id": "memuAsite", "name": "网站", "class": "menu_web", "url": "/site/index", "show": True},
            {"id": "memuAmonitor", "name": "监控", "class": "menu_control", "url": "/monitor/index", "show": True},
            {"id": "memuAfirewall", "name": "安全", "class": "menu_firewall", "url": "/firewall/index", "show": True},
            {"id": "memuAfiles", "name": "文件", "class": "menu_folder", "url": "/files/index", "show": True},
            {"id": "memuAlogs", "name": "日志", "class": "menu_logs", "url": "/logs/index", "show": True},
            {"id": "memuAcrontab", "name": "计划任务", "class": "menu_day", "url": "/crontab/index", "show": True},
            {"id": "memuAsoft", "name": "软件管理", "class": "menu_soft", "url": "/soft/index", "show": True},
            {"id": "memuAsetting", "name": "面板设置", "class": "menu_set", "url": "/setting/index", "show": True}
        ]
        mw.writeFile(menu_file, json.dumps(default_menu))
        _menu_cache = default_menu
    else:
        try:
            content = mw.readFile(menu_file)
            _menu_cache = json.loads(content)
        except Exception as e:
            _menu_cache = []
    
    return _menu_cache

def getUnauthStatus(
    code= '0'
):
    code = str(code)
    data = {}
    data['code'] = code
    if code == '0':
        data['text'] = "默认-安全入口错误提示"
    elif code == '400':
        data['text'] = "400-客户端请求错误"
    elif code == '401':
        data['text'] = "401-未授权访问"
    elif code == '403':
        data['text'] = "403-拒绝访问"
    elif code == '404':
        data['text'] = "404-页面不存在"
    elif code == '408':
        data['text'] = "408-客户端超时"
    elif code == '416':
        data['text'] = "416-无效的请求"
    else:
        data['code'] = '0'
        data['text'] = "默认-安全入口错误提示"
    return data

def getGlobalVar():
    '''
    获取全局变量
    '''
    data = {}
    data['title'] = thisdb.getOption('title', default='御风面板（BtSimple）')
    
    ip = thisdb.getOption('server_ip', default='127.0.0.1')
    if ip in ['127.0.0.1', 'localhost', '::1', '']:
        ip = mw.getLocalIp()
    data['ip'] = ip

    data['site_path'] = thisdb.getOption('site_path', default=mw.getFatherDir()+'/wwwroot')
    data['backup_path'] = thisdb.getOption('backup_path', default=mw.getFatherDir()+'/backup')
    data['admin_path'] = '/'+thisdb.getOption('admin_path', default='')
    data['debug'] = thisdb.getOption('debug', default='close')
    data['admin_close'] = thisdb.getOption('admin_close', default='no')
    data['site_count'] = thisdb.getSitesCount()
    data['port'] = mw.getHostPort()

    __file = mw.getCommonFile()
    if os.path.exists(__file['ipv6']):
        data['ipv6'] = 'checked'
    else:
        data['ipv6'] = ''

    # 获取ROOT用户名
    data['username'] = mw.M('users').where("id=?", (1,)).getField('name')

    # 获取未认证状态信息
    unauthorized_status = thisdb.getOption('unauthorized_status', default='0')
    data['unauthorized_status'] = getUnauthStatus(code=unauthorized_status)
    data['basic_auth'] = thisdb.getOptionByJson('basic_auth', default={'open':False})
    data['two_step_verification'] = thisdb.getOptionByJson('two_step_verification', default={'open':False})

    # 服务器时间
    sformat = 'date +"%Y-%m-%d %H:%M:%S %Z %z"'
    data['systemdate'] = mw.execShell(sformat)[0].strip()


    data['hook_menu'] = thisdb.getOptionByJson('hook_menu',type='hook',default=[])
    data['hook_global_static'] = thisdb.getOptionByJson('hook_global_static',type='hook',default=[])
    data['hook_database'] = thisdb.getOptionByJson('hook_database',type='hook',default=[])

    data['menu_list'] = get_menu_config()

    # 邮件通知设置
    data['notify_email'] = thisdb.getOptionByJson('notify_email', default={'open':False}, type='notify')
    data['notify_tgbot'] = thisdb.getOptionByJson('notify_tgbot', default={'open':False}, type='notify')
    
    data['panel_api'] = thisdb.getOptionByJson('panel_api', default={'open':False})
    data['panel_ssl'] = thisdb.getOptionByJson('panel_ssl', default={'open':False})
    data['panel_domain'] = thisdb.getOption('panel_domain', default='')
    data['use_cdn'] = thisdb.getOption('use_cdn', default='no')
    
    return data