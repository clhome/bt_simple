# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import re
import json
import os
import time

from flask import Blueprint, render_template
from flask import request

from admin import session
from admin.user_login_check import panel_login_required


import core.yf as yf
import thisdb
import utils.config as utils_config


# 默认页面
blueprint = Blueprint('setting', __name__, url_prefix='/setting', template_folder='../../templates')
@blueprint.route('/index', endpoint='index')
@panel_login_required
def index():
    name = thisdb.getOption('template', default='default')
    return render_template('%s/setting.html' % name)

# 设置面板名称
@blueprint.route('/set_webname', endpoint='set_webname', methods=['POST'])
@panel_login_required
def set_webname():
    webname = request.form.get('webname', '')
    src_webname = thisdb.getOption('title')
    if webname != src_webname:
        thisdb.setOption('title', webname)
    return yf.returnData(True, '面板别名保存成功!')

# 设置服务器IP
@blueprint.route('/set_ip', endpoint='set_ip', methods=['POST'])
@panel_login_required
def set_ip():
    host_ip = request.form.get('host_ip', '')
    src_host_ip = thisdb.getOption('server_ip')
    if host_ip != src_host_ip:
        thisdb.setOption('server_ip', host_ip)
    return yf.returnData(True, 'IP保存成功!')

# 默认备份目录
@blueprint.route('/set_backup_dir', endpoint='set_backup_dir', methods=['POST'])
@panel_login_required
def set_backup_dir():
    backup_path = request.form.get('backup_path', '')
    src_backup_path = thisdb.getOption('backup_path')
    if backup_path != src_backup_path:
        thisdb.setOption('backup_path', backup_path)
    return yf.returnData(True, '修改默认备份目录成功!')

# 默认站点目录
@blueprint.route('/set_www_dir', endpoint='set_www_dir', methods=['POST'])
@panel_login_required
def set_www_dir():
    sites_path = request.form.get('sites_path', '')
    src_sites_path = thisdb.getOption('site_path')
    if sites_path != src_sites_path:
        thisdb.setOption('site_path', sites_path)
    return yf.returnData(True, '修改默认建站目录成功!')


# 设置安全入口
@blueprint.route('/set_admin_path', endpoint='set_admin_path', methods=['POST'])
@panel_login_required
def set_admin_path():
    admin_path = request.form.get('admin_path', '')
    admin_path_sensitive = [
        '/', '/close', '/login',
        '/do_login', '/site', '/sites',
        '/download_file', '/control', '/crontab',
        '/firewall', '/files', '/config', '/setting','/monitor'
        '/soft', '/system', '/code',
        '/ssl', '/plugins', '/hook'
    ]

    if admin_path == '':
        admin_path = '/'

    if admin_path != '/':
        if len(admin_path) < 6:
            return yf.returnData(False, '安全入口地址长度不能小于6位!')
        if admin_path in admin_path_sensitive:
            return yf.returnData(False, '该入口已被面板占用,请使用其它入口!')
        if not re.match(r"^/[\w]+$", admin_path):
            return yf.returnData(False, '入口地址格式不正确,示例: /mw_rand')
    
    src_admin_path = thisdb.getOption('admin_path')
    if admin_path != src_admin_path:
        thisdb.setOption('admin_path', admin_path[1:])
    return yf.returnData(True, '修改成功!')



# 设置BasicAuth认证
@blueprint.route('/set_basic_auth', endpoint='set_basic_auth', methods=['POST'])
@panel_login_required
def set_basic_auth():
    basic_user = request.form.get('basic_user', '').strip()
    basic_pwd = request.form.get('basic_pwd', '').strip()
    basic_open = request.form.get('is_open', '').strip()
    
    __file = yf.getCommonFile()
    path = __file['basic_auth']

    is_open = True
    if basic_open == 'false':
        is_open = False

    if basic_open == 'false':
        thisdb.setOption('basic_auth', json.dumps({'open':False}))
        yf.writeLog('面板设置', '设置BasicAuth状态为: %s' % is_open)
        return yf.returnData(True, '删除BasicAuth成功!')

    if basic_user == '' or basic_pwd == '':
        return yf.returnData(False, '用户和密码不能为空!')

    salt = yf.getRandomString(6)
    data = {}
    data['salt'] = salt
    data['basic_user'] = yf.md5(basic_user + salt)
    data['basic_pwd'] = yf.md5(basic_pwd + salt)
    data['open'] = is_open

    thisdb.setOption('basic_auth', json.dumps(data))
    yf.writeLog('面板设置', '设置BasicAuth状态为: %s' % is_open)
    return yf.returnData(True, '设置成功!')


# 设置面板未登录状态
@blueprint.route('/set_status_code', endpoint='set_status_code', methods=['POST'])
@panel_login_required
def set_status_code():
    status_code = request.form.get('status_code', '').strip()
    if re.match(r"^\d+$", status_code):
        status_code = int(status_code)
        if status_code != 0:
            if status_code < 100 or status_code > 999:
                return yf.returnData(False, '状态码范围错误!!')
    else:
        return yf.returnData(False, '状态码范围错误!')

    info = utils_config.getUnauthStatus(code=str(status_code))
    thisdb.setOption('unauthorized_status', str(status_code))
    yf.writeLog('面板设置', '将未授权响应状态码设置为:{0}:{1}'.format(status_code,info['text']))
    return yf.returnData(True, '设置成功!')

# 设置面板调式模式
@blueprint.route('/open_debug', endpoint='open_debug', methods=['POST'])
@panel_login_required
def open_debug():
    debug = thisdb.getOption('debug',default='close')
    if debug == 'open':
        thisdb.setOption('debug','close')
        return yf.returnData(True, '开发模式关闭!')
    thisdb.setOption('debug','open')
    return yf.returnData(True, '开发模式开启!')


# 设置面板开关
@blueprint.route('/close_panel', endpoint='close_panel', methods=['POST'])
@panel_login_required
def close_panel():
    admin_close = thisdb.getOption('admin_close',default='no')
    if admin_close == 'no':
        thisdb.setOption('admin_close','yes')
        return yf.returnData(True, '关闭面板成功!')
    thisdb.setOption('admin_close','no')
    return yf.returnData(True, '开启面板成功!')

# 设置IPV6状态
@blueprint.route('/set_ipv6_status', endpoint='set_ipv6_status', methods=['POST'])
@panel_login_required
def set_ipv6_status():
    __file = yf.getCommonFile()
    ipv6_file = __file['ipv6']
    if os.path.exists(ipv6_file):
        os.remove(ipv6_file)
        yf.writeLog('面板设置', '关闭面板IPv6兼容!')
        yf.returnData('面板设置', '关闭面板IPv6兼容!')
    else:
        yf.writeFile(ipv6_file, 'True')
        yf.writeLog('面板设置', '开启面板IPv6兼容!')
    yf.restartMw()
    return yf.returnData(True, '设置成功!')

# 设置CDN状态
@blueprint.route('/set_cdn_status', endpoint='set_cdn_status', methods=['POST'])
@panel_login_required
def set_cdn_status():
    use_cdn = thisdb.getOption('use_cdn', default='no')
    if use_cdn == 'no':
        thisdb.setOption('use_cdn', 'yes')
        yf.writeLog('面板设置', '开启CDN加速!')
        return yf.returnData(True, '开启CDN加速成功!')
    thisdb.setOption('use_cdn', 'no')
    yf.writeLog('面板设置', '关闭CDN加速!')
    return yf.returnData(True, '关闭CDN加速成功!')

# 设置GPU检测状态
@blueprint.route('/set_gpu_detect', endpoint='set_gpu_detect', methods=['POST'])
@panel_login_required
def set_gpu_detect():
    gpu_detect = thisdb.getOption('gpu_detect', default='no')
    if gpu_detect == 'no':
        thisdb.setOption('gpu_detect', 'yes')
        utils_config._global_var_cache_time = 0
        yf.writeLog('面板设置', '开启英伟达GPU首页检测!')
        return yf.returnData(True, '开启英伟达GPU首页检测成功!')
    thisdb.setOption('gpu_detect', 'no')
    utils_config._global_var_cache_time = 0
    yf.writeLog('面板设置', '关闭英伟达GPU首页检测!')
    return yf.returnData(True, '关闭英伟达GPU首页检测成功!')

# 设置面板用户
@blueprint.route('/set_name', endpoint='set_name', methods=['POST'])
@panel_login_required
def set_name():
    name1 = request.form.get('name1', '')
    name2 = request.form.get('name2', '')
    if name1 != name2:
        return yf.returnData(False, '两次输入的用户名不一致，请重新输入!')
    if len(name1) < 3:
        return yf.returnData(False, '用户名长度不能少于3位')
    thisdb.setUserByName(session['username'], name1)
    session['username'] = name1
    return yf.returnData(True, '用户修改成功!')

# 设置面板密码
@blueprint.route('/set_password', endpoint='set_password', methods=['POST'])
@panel_login_required
def set_password():
    password1 = request.form.get('password1', '')
    password2 = request.form.get('password2', '')
    if password1 != password2:
        return yf.returnData(False, '两次输入的密码不一致，请重新输入!')
    if len(password1) < 5:
        return yf.returnData(False, '用户密码不能小于5位!')

    thisdb.setUserPwdByName(session['username'], password1)
    return yf.returnData(True, '密码修改成功!')

# 设置面板端口
@blueprint.route('/set_port', endpoint='set_port', methods=['POST'])
@panel_login_required
def set_port():
    port = request.form.get('port', '')
    if port != yf.getHostPort():
        from utils.firewall import Firewall as MwFirewall

        sysCfgDir = yf.systemdCfgDir()
        if os.path.exists(sysCfgDir + "/firewalld.service"):
            if not MwFirewall.instance().getFwStatus():
                return yf.returnData(False, 'firewalld必须先启动!')

        yf.setHostPort(port)
        msg = yf.getInfo('放行端口[{1}]成功', (port,))
        yf.writeLog("防火墙管理", msg)

        MwFirewall.instance().addAcceptPort(port, 'PANEL端口-配置修改', 'port')
        yf.restartMw()

    return yf.returnData(True, '端口保存成功!')

# 保存菜单配置
@blueprint.route('/save_menu_config', endpoint='save_menu_config', methods=['POST'])
@panel_login_required
def save_menu_config():
    try:
        menu_data = request.form.get('menu_data', '')
        if not menu_data:
            return yf.returnData(False, '菜单数据不能为空!')
        
        menus = json.loads(menu_data)
        if not isinstance(menus, list):
            return yf.returnData(False, '菜单数据格式错误!')
            
        panel_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        menu_file = panel_dir + '/data/menu.json'
        yf.writeFile(menu_file, json.dumps(menus))
        
        # 更新内存缓存
        utils_config._menu_cache = menus
        utils_config._global_var_cache_time = 0
        
        return yf.returnData(True, '菜单配置保存成功!')
    except Exception as e:
        return yf.returnData(False, '保存失败: ' + str(e))

# 检测数据库备份状态
@blueprint.route('/check_migrate_backup', endpoint='check_migrate_backup', methods=['POST'])
@panel_login_required
def check_migrate_backup():
    import os
    has_mysql = False
    databases = []
    old_data_dir = ""
    if os.path.exists("/www/server/data_bt_bak"):
        old_data_dir = "/www/server/data_bt_bak"
    elif os.path.exists("/www/server/mysql_bt_bak/data"):
        old_data_dir = "/www/server/mysql_bt_bak/data"
        
    if old_data_dir:
        has_mysql = True
        ignore_dbs = ['mysql', 'performance_schema', 'information_schema', 'sys', 'test']
        try:
            for f in os.listdir(old_data_dir):
                if os.path.isdir(os.path.join(old_data_dir, f)) and f not in ignore_dbs:
                    databases.append(f)
        except:
            pass
            
    return yf.getJson({'mysql': has_mysql, 'databases': databases})

# 数据库迁移恢复
@blueprint.route('/migrate_restore', endpoint='migrate_restore', methods=['POST'])
@panel_login_required
def migrate_restore():
    try:
        args = []
        if request.form.get('mysql', '') == '1':
            args.append('mysql')
            dbs = request.form.get('dbs', '*')
            if dbs != '*':
                args.append('--dbs=' + dbs)
            
        import sys
        import os
        panel_dir = yf.getPanelDir()
        log_file = "/tmp/migrate_restore.log"
        yf.writeFile(log_file, "正在初始化迁移任务...\n")
        
        cmd = "cd " + panel_dir + " && echo yes | " + sys.executable + " -u " + panel_dir + "/panel_tools.py migrate_restore " + " ".join(args) + " > " + log_file + " 2>&1 &"
        os.system(cmd)
        
        yf.writeLog('面板设置', '执行数据库迁移恢复: ' + cmd)
        return yf.returnData(True, "迁移已启动")
    except Exception as e:
        return yf.returnData(False, "迁移启动失败：" + str(e))

@blueprint.route('/get_migrate_log', endpoint='get_migrate_log', methods=['POST'])
@panel_login_required
def get_migrate_log():
    import os
    log_file = "/tmp/migrate_restore.log"
    if not os.path.exists(log_file):
        return yf.returnData(False, "日志文件不存在或尚未生成")
    content = yf.readFile(log_file)
    return yf.returnData(True, content)

# 网站列表迁移检测
@blueprint.route('/check_migrate_sites', endpoint='check_migrate_sites', methods=['POST'])
@panel_login_required
def check_migrate_sites():
    import glob
    import os
    paths = glob.glob('/www/server/panel.bak.*/data/db/site.db')
    if os.path.exists('/www/server/panel/data/db/site.db'):
        paths.append('/www/server/panel/data/db/site.db')
    paths = list(set(paths))
    paths.sort(reverse=True)
    return yf.getJson({'paths': paths})

# 执行网站列表迁移
@blueprint.route('/migrate_sites', endpoint='migrate_sites', methods=['POST'])
@panel_login_required
def migrate_sites():
    try:
        db_path = request.form.get('db_path', '').strip()
        if not db_path:
            return yf.returnData(False, "数据库路径不能为空")
            
        import sys
        import os
        panel_dir = yf.getPanelDir()
        log_file = "/tmp/migrate_sites.log"
        yf.writeFile(log_file, "正在初始化站点导入任务...\n")
        
        cmd = "cd " + panel_dir + " && " + sys.executable + " -u " + panel_dir + "/panel_tools.py import_bt_sites " + db_path + " > " + log_file + " 2>&1 &"
        os.system(cmd)
        
        yf.writeLog('面板设置', '执行宝塔站点导入: ' + cmd)
        return yf.returnData(True, "站点导入已启动")
    except Exception as e:
        return yf.returnData(False, "站点导入启动失败：" + str(e))

# 获取网站列表迁移日志
@blueprint.route('/get_migrate_sites_log', endpoint='get_migrate_sites_log', methods=['POST'])
@panel_login_required
def get_migrate_sites_log():
    import os
    log_file = "/tmp/migrate_sites.log"
    if not os.path.exists(log_file):
        return yf.returnData(False, "日志文件不存在或尚未生成")
    content = yf.readFile(log_file)
    return yf.returnData(True, content)

# 获取宝塔备份列表
@blueprint.route('/get_bt_backups', endpoint='get_bt_backups', methods=['POST'])
@panel_login_required
def get_bt_backups():
    import os
    data = []
    
    server_path = "/www/server/"
    if not os.path.exists(server_path):
        return yf.getJson({'status': True, 'data': []})
        
    targets = {
        'mysql_bt_bak': ('MySQL主程序备份', '无特殊影响，释放硬盘空间'),
        'data_bt_bak': ('MySQL用户数据备份', '彻底删除备份数据库，无法使用数据库还原功能'),
        'nginx_bt_bak': ('Nginx环境备份', '无特殊影响，释放硬盘空间'),
        'php_bt_bak': ('PHP环境备份', '无特殊影响，释放硬盘空间'),
        'redis_bt_bak': ('Redis环境备份', '无特殊影响，释放硬盘空间'),
        'postgresql_bt_bak': ('PgSQL环境备份', '无法恢复旧版PgSQL数据库')
    }
    
    from utils.file import getDirSize
    
    for f in os.listdir(server_path):
        full_path = os.path.join(server_path, f)
        if not os.path.isdir(full_path):
            continue
            
        desc = ""
        warning = ""
        if f in targets:
            desc = targets[f][0]
            warning = targets[f][1]
        elif f.startswith('panel.bak.'):
            desc = "原面板备份"
            warning = "无法回滚至原宝塔面板"
            
        if desc:
            try:
                size = getDirSize(full_path)
            except:
                size = 0
            data.append({'name': f, 'path': full_path, 'desc': desc, 'warning': warning, 'type': 'dir', 'size': yf.toSize(size)})
            
    # 按名称排序
    data.sort(key=lambda x: x['name'])
    return yf.getJson({'status': True, 'data': data})

# 压缩宝塔备份目录
@blueprint.route('/compress_bt_backup', endpoint='compress_bt_backup', methods=['POST'])
@panel_login_required
def compress_bt_backup():
    path = request.form.get('path', '')
    if not path or not path.startswith('/www/server/'):
        return yf.returnData(False, '参数错误或无权限')
    
    import os
    if not os.path.exists(path) or not os.path.isdir(path):
        return yf.returnData(False, '目录不存在')
        
    parent_dir = os.path.dirname(path)
    base_name = os.path.basename(path)
    cmd = "cd {} && zip -r {}.zip {}".format(parent_dir, base_name, base_name)
    yf.execShell(cmd)
    
    return yf.returnData(True, '压缩成功，文件保存在同级目录下')

# 删除宝塔备份
@blueprint.route('/delete_bt_backup', endpoint='delete_bt_backup', methods=['POST'])
@panel_login_required
def delete_bt_backup():
    path = request.form.get('path', '')
    if not path or not path.startswith('/www/server/'):
        return yf.returnData(False, '参数错误或无权限')
    
    import os, shutil
    if not os.path.exists(path):
        return yf.returnData(False, '文件/目录不存在')
        
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return yf.returnData(True, '删除成功')
    except Exception as e:
        return yf.returnData(False, '删除失败: ' + str(e))

# 设置首页提醒
@blueprint.route('/set_home_notice', endpoint='set_home_notice', methods=['POST'])
@panel_login_required
def set_home_notice():
    home_notice = request.form.get('home_notice', '')
    if len(home_notice) > 50:
        return yf.returnData(False, '首页提醒最长不能超过50个字!')
    
    src_home_notice = thisdb.getOption('home_notice')
    if home_notice != src_home_notice:
        thisdb.setOption('home_notice', home_notice)
    return yf.returnData(True, '首页提醒保存成功!')
