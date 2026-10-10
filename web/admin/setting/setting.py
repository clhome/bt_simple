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
import shutil
import sys
import time

from flask import Blueprint, render_template
from flask import request

from admin import session
from admin.common import invalidate_login_cache
from admin.user_login_check import panel_login_required


import core.yf as yf
import core.panel_session as panel_session
import core.login_guard as login_guard
import thisdb
import utils.config as utils_config


# 默认页面
blueprint = Blueprint('setting', __name__, url_prefix='/setting', template_folder='../../templates')

# 分页/行数入参的统一容错解析。
# 裸 `int(request.form.get('page'))` 会被任意非数字入参打成 500(真机实测
# `/setting/get_app_list?page=abc`、`/setting/get_temp_login?limit=abc`),
# 且 SQLite 下负 LIMIT 等于不限量(会把整表拉出来)。
def _parse_page_args(page, limit, default_page=1, default_limit=10, max_limit=100):
    def _to_int(val, fallback):
        try:
            if val is None or isinstance(val, bool):
                return fallback
            text = str(val).strip()
            if not text or not re.match(r'^[+-]?\d+$', text):
                return fallback
            return int(text)
        except Exception:
            return fallback

    p = _to_int(page, default_page)
    size = _to_int(limit, default_limit)
    if p < 1:
        p = default_page
    if size < 1:
        size = 1
    elif size > max_limit:
        size = max_limit
    return p, size


# 「默认备份目录 / 默认建站目录」入参校验。
# 历史上这两个路由无任何校验且无条件返回成功：真机实测可把 backup_path 设成
# 不存在的路径，而备份写入点走 yf.getBackupDir()、列表/删除读取点走另一处目录，
# 两者不同源 → 面板「数据库备份」列表恒空；site_path 同样可被设成任意目录。
# 返回 (path, err_key)：path 为空串表示校验失败，err_key 为已有 i18n 键。
def _check_dir_option(value, kind='backup'):
    path = (value or '').strip()
    if not path:
        return '', 'DIR_EMPTY'
    # 面板只跑 Linux，这里按 POSIX 绝对路径判定；`os.path.isabs` 兼顾本机
    # （Windows）跑守卫用例的场景（`os.path.isabs('/etc')` 在 Windows 上为 False）。
    if not path.startswith('/') and not os.path.isabs(path):
        return '', 'py_msg_e05503'
    try:
        from utils.file import safePath
        ok, _reason = safePath(path, write=True)
    except Exception:
        ok = False
    if not ok:
        return '', ('PATH_ERROR' if kind == 'site' else 'py_msg_e05503')
    path = os.path.normpath(path)
    if os.path.exists(path):
        if not os.path.isdir(path):
            return '', 'py_msg_2ccda7'
    else:
        # 只允许在**已存在的父目录**下新建子目录：否则一个手滑的入参就能在
        # 根下凭空造出一整条目录树（真机实测 `/nonexistent/x/y` 被 makedirs 建出来）。
        parent = os.path.dirname(path)
        if not parent or not os.path.isdir(parent):
            return '', 'py_msg_2ccda7'
        try:
            os.makedirs(path, exist_ok=True)
        except Exception:
            return '', 'py_msg_2ccda7'
    if not os.access(path, os.W_OK):
        return '', 'py_msg_e05503'
    return path, ''


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
        utils_config.clearGlobalVarCache()
    return yf.returnData(True, 'setting.py_msg_ca5110')

# 设置服务器IP
@blueprint.route('/set_ip', endpoint='set_ip', methods=['POST'])
@panel_login_required
def set_ip():
    host_ip = request.form.get('host_ip', '')
    src_host_ip = thisdb.getOption('server_ip')
    if host_ip != src_host_ip:
        thisdb.setOption('server_ip', host_ip)
        utils_config.clearGlobalVarCache()
    return yf.returnData(True, 'setting.py_msg_9adea2')

# 默认备份目录
@blueprint.route('/set_backup_dir', endpoint='set_backup_dir', methods=['POST'])
@panel_login_required
def set_backup_dir():
    backup_path, err = _check_dir_option(request.form.get('backup_path', ''), kind='backup')
    if err:
        return yf.returnData(False, err)
    src_backup_path = thisdb.getOption('backup_path')
    if backup_path != src_backup_path:
        thisdb.setOption('backup_path', backup_path)
        utils_config.clearGlobalVarCache()
        yf.writeLog('面板设置', '默认备份目录修改为: {1}', (backup_path,))
    return yf.returnData(True, 'setting.py_msg_b179f2')

# 默认站点目录
@blueprint.route('/set_www_dir', endpoint='set_www_dir', methods=['POST'])
@panel_login_required
def set_www_dir():
    sites_path, err = _check_dir_option(request.form.get('sites_path', ''), kind='site')
    if err:
        return yf.returnData(False, err)
    src_sites_path = thisdb.getOption('site_path')
    if sites_path != src_sites_path:
        thisdb.setOption('site_path', sites_path)
        utils_config.clearGlobalVarCache()
        yf.writeLog('面板设置', '默认建站目录修改为: {1}', (sites_path,))
    return yf.returnData(True, 'setting.py_msg_d75d39')


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
            return yf.returnData(False, 'setting.py_msg_eeb5dc')
        if admin_path in admin_path_sensitive:
            return yf.returnData(False, 'setting.py_msg_829da6')
        if not re.match(r"^/[\w]+$", admin_path):
            return yf.returnData(False, 'setting.py_msg_16eb02')
    
    src_admin_path = thisdb.getOption('admin_path')
    if admin_path != src_admin_path:
        thisdb.setOption('admin_path', admin_path[1:])
    return yf.returnData(True, 'common.edit_success')



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
        return yf.returnData(True, 'setting.py_msg_096c84')

    if basic_user == '' or basic_pwd == '':
        return yf.returnData(False, 'setting.py_msg_6fea4c')

    salt = yf.getRandomString(6)
    data = {}
    data['salt'] = salt
    # 口令用 bcrypt 存储；salt 仅用于兼容历史 MD5 存量值的一次性比对，
    # 校验侧见 web/admin/__init__.py。
    data['basic_user'] = yf.hasPwd(basic_user + salt)
    data['basic_pwd'] = yf.hasPwd(basic_pwd + salt)
    data['open'] = is_open

    thisdb.setOption('basic_auth', json.dumps(data))
    yf.writeLog('面板设置', '设置BasicAuth状态为: %s' % is_open)
    return yf.returnData(True, 'common.set_success')


# 设置面板未登录状态
@blueprint.route('/set_status_code', endpoint='set_status_code', methods=['POST'])
@panel_login_required
def set_status_code():
    status_code = request.form.get('status_code', '').strip()
    if re.match(r"^\d+$", status_code):
        status_code = int(status_code)
        if status_code != 0:
            if status_code < 100 or status_code > 999:
                return yf.returnData(False, 'setting.py_msg_9716ed')
    else:
        return yf.returnData(False, 'setting.py_msg_a68173')

    info = utils_config.getUnauthStatus(code=str(status_code))
    thisdb.setOption('unauthorized_status', str(status_code))
    utils_config.clearGlobalVarCache()
    yf.writeLog('面板设置', '将未授权响应状态码设置为:{0}:{1}'.format(status_code,info['text']))
    return yf.returnData(True, 'common.set_success')

# 设置面板调式模式
@blueprint.route('/open_debug', endpoint='open_debug', methods=['POST'])
@panel_login_required
def open_debug():
    debug = thisdb.getOption('debug',default='close')
    if debug == 'open':
        thisdb.setOption('debug','close')
        utils_config.clearGlobalVarCache()
        return yf.returnData(True, 'setting.py_msg_2f9e9a')
    thisdb.setOption('debug','open')
    utils_config.clearGlobalVarCache()
    return yf.returnData(True, 'setting.py_msg_e82416')


# 设置面板开关
@blueprint.route('/close_panel', endpoint='close_panel', methods=['POST'])
@panel_login_required
def close_panel():
    admin_close = thisdb.getOption('admin_close',default='no')
    if admin_close == 'no':
        thisdb.setOption('admin_close','yes')
        utils_config.clearGlobalVarCache()
        return yf.returnData(True, 'setting.py_msg_77f082')
    thisdb.setOption('admin_close','no')
    utils_config.clearGlobalVarCache()
    return yf.returnData(True, 'setting.py_msg_a55770')

# 设置IPV6状态
@blueprint.route('/set_ipv6_status', endpoint='set_ipv6_status', methods=['POST'])
@panel_login_required
def set_ipv6_status():
    __file = yf.getCommonFile()
    ipv6_file = __file['ipv6']
    if os.path.exists(ipv6_file):
        os.remove(ipv6_file)
        yf.writeLog('面板设置', '关闭面板IPv6兼容!')
    else:
        yf.writeFile(ipv6_file, 'True')
        yf.writeLog('面板设置', '开启面板IPv6兼容!')
    yf.restartPanel()
    return yf.returnData(True, 'common.set_success')

# 设置CDN状态
@blueprint.route('/set_cdn_status', endpoint='set_cdn_status', methods=['POST'])
@panel_login_required
def set_cdn_status():
    use_cdn = thisdb.getOption('use_cdn', default='no')
    if use_cdn == 'no':
        thisdb.setOption('use_cdn', 'yes')
        utils_config.clearGlobalVarCache()
        yf.writeLog('面板设置', '开启CDN加速!')
        return yf.returnData(True, 'setting.py_msg_a2a860')
    thisdb.setOption('use_cdn', 'no')
    utils_config.clearGlobalVarCache()
    yf.writeLog('面板设置', '关闭CDN加速!')
    return yf.returnData(True, 'setting.py_msg_befc80')

# 设置GPU检测状态
@blueprint.route('/set_gpu_detect', endpoint='set_gpu_detect', methods=['POST'])
@panel_login_required
def set_gpu_detect():
    gpu_detect = thisdb.getOption('gpu_detect', default='no')
    if gpu_detect == 'no':
        thisdb.setOption('gpu_detect', 'yes')
        utils_config.clearGlobalVarCache()
        yf.writeLog('面板设置', '开启英伟达GPU首页检测!')
        return yf.returnData(True, 'setting.py_msg_9cfee3')
    thisdb.setOption('gpu_detect', 'no')
    utils_config.clearGlobalVarCache()
    yf.writeLog('面板设置', '关闭英伟达GPU首页检测!')
    return yf.returnData(True, 'setting.py_msg_d0a336')

# 设置面板自动更新状态
# 安全口径：自动更新**默认关闭**；开启后会在计划任务里新增 `yf update`，
# 关闭时会立即移除该任务（不必等面板重启）。
@blueprint.route('/set_auto_update_status', endpoint='set_auto_update_status', methods=['POST'])
@panel_login_required
def set_auto_update_status():
    auto_update = thisdb.getOption('auto_update', default='no')
    if auto_update == 'no':
        thisdb.setOption('auto_update', 'yes')
        yf.writeLog('面板设置', '开启面板自动更新!')
    else:
        thisdb.setOption('auto_update', 'no')
        yf.writeLog('面板设置', '关闭面板自动更新!')
    utils_config.clearGlobalVarCache()

    # 立即同步计划任务（否则要等下次面板启动才生效）
    try:
        from admin.setup.init_cron import init_auto_update
        init_auto_update()
    except Exception as e:
        yf.writeLog('面板设置', '自动更新计划任务同步异常: %s' % e)

    return yf.returnData(True, 'common.set_success')

# 设置面板用户
@blueprint.route('/set_name', endpoint='set_name', methods=['POST'])
@panel_login_required
def set_name():
    name1 = request.form.get('name1', '')
    name2 = request.form.get('name2', '')
    if name1 != name2:
        return yf.returnData(False, 'setting.py_msg_91b70d')
    if len(name1) < 3:
        return yf.returnData(False, 'setting.py_msg_24ce37')
    thisdb.setUserByName(session['username'], name1)
    session['username'] = name1
    return yf.returnData(True, 'setting.py_msg_410e38')

# 设置面板密码
@blueprint.route('/set_password', endpoint='set_password', methods=['POST'])
@panel_login_required
def set_password():
    username = session.get('username', '')
    if not username:
        return yf.returnData(False, '登录超时，请重新登录！')

    old_password = request.form.get('old_password', '').strip()
    password1 = request.form.get('password1', '').strip()
    password2 = request.form.get('password2', '').strip()

    user_info = thisdb.getUserByName(username)
    if not user_info:
        return yf.returnData(False, '用户不存在！')

    # 原密码校验（支持 bcrypt 及历史 MD5/SHA256 回退）
    if not old_password:
        return yf.returnData(False, '请输入原密码！')

    if not yf.checkPwdCompat(old_password, user_info.get('password', '')):
        return yf.returnData(False, '原密码错误，请重新输入！')

    if password1 != password2:
        return yf.returnData(False, '两次输入的密码不一致！')

    if len(password1) < 8:
        return yf.returnData(False, '新密码长度至少需要8位！')

    import re
    if not re.search(r'[A-Za-z]', password1) or not re.search(r'[0-9]', password1):
        return yf.returnData(False, '新密码必须同时包含英文字母和数字！')

    if password1 == old_password:
        return yf.returnData(False, '新密码不能与原密码相同！')

    thisdb.setUserPwdByName(username, password1)
    yf.writeLog('面板设置', '管理员[{1}]成功修改了面板密码', (username,))

    # 强制下线：撤销该账号的全部服务端会话（含当前会话），
    # 其他设备下一次请求即被登出；同时清空进程内登录缓存，避免 20s 延迟。
    try:
        panel_session.revoke_user_sessions(session.get('uid') or 1)
    except Exception as exc:
        yf.writeFileLog('改密后撤销其它会话失败（不阻断改密）：%s' % exc)
    invalidate_login_cache()

    # 会话注销，强制重新使用新密码登录
    session.clear()
    session['login'] = False
    session['overdue'] = 0

    return yf.returnData(True, '密码修改成功，请使用新密码重新登录！')

# 登录会话管理（可列举 / 可强制下线）
@blueprint.route('/get_sessions', endpoint='get_sessions', methods=['POST'])
@panel_login_required
def get_sessions():
    uid = session.get('uid') or 1
    current = session.get('session_id') or ''
    try:
        rows = panel_session.list_sessions(uid)
    except Exception:
        rows = []
    data = []
    for r in rows:
        sid = r.get('session_id', '') or ''
        data.append({
            'session_id': sid,
            'ip': r.get('ip', '') or '-',
            'ua': r.get('ua', '') or '-',
            'created_at': yf.formatDate('%Y-%m-%d %H:%M:%S', int(r.get('created_at') or 0)),
            'last_seen': yf.formatDate('%Y-%m-%d %H:%M:%S', int(r.get('last_seen') or 0)),
            'current': sid == current,
        })
    return yf.returnData(True, '获取成功', data)


@blueprint.route('/revoke_session', endpoint='revoke_session', methods=['POST'])
@panel_login_required
def revoke_session():
    uid = session.get('uid') or 1
    sid = (request.form.get('session_id', '') or '').strip()
    if not sid:
        return yf.returnData(False, '参数错误')
    # 只能下线自己的会话（先从服务端副本确认归属，防越权操作他人会话）
    row = panel_session.get(sid)
    if not row or int(row.get('uid') or 0) != int(uid):
        return yf.returnData(False, '会话不存在')
    panel_session.revoke(sid)
    invalidate_login_cache(sid)
    yf.writeAudit('session.revoke', target=sid[:12], result='ok',
                  detail='管理员下线了一个登录会话')
    # 若下线的正是当前会话，同时也结束本地登录态
    if sid == (session.get('session_id') or ''):
        session.clear()
    return yf.returnData(True, '已下线该会话')


@blueprint.route('/unlock_login', endpoint='unlock_login', methods=['POST'])
@panel_login_required
def unlock_login():
    """清除当前账号与来源 IP 的登录失败封禁（防“账号维度锁定”误伤管理员）。"""
    username = session.get('username') or ''
    try:
        client_ip = yf.getClientIp()
    except Exception:
        client_ip = ''
    login_guard.reset(client_ip, username)
    yf.writeAudit('login.unban', target=username, result='ok', detail='管理员解除登录封禁')
    return yf.returnData(True, '已解除登录封禁')


# 设置面板端口
@blueprint.route('/set_port', endpoint='set_port', methods=['POST'])
@panel_login_required
def set_port():
    port = (request.form.get('port', '') or '').strip()

    # 端口白名单:旧实现把请求值直接写进 `data/port.pl` —— 真机实测 `port=abc`
    # 回「端口保存成功!」但 gunicorn 从此不再监听,面板整体从网络里消失;
    # `70000` 同样写盘;`60376; touch /tmp/x` 会把整串命令写进配置文件。
    from utils.firewall import parsePortSpec
    span = parsePortSpec(port)
    if span is None or span[0] != span[1]:
        return yf.returnData(False, 'setting.py_msg_9716ed')
    port = str(span[0])

    if port != yf.getHostPort():
        from utils.firewall import Firewall as YfFirewall

        sysCfgDir = yf.systemdCfgDir()
        if os.path.exists(sysCfgDir + "/firewalld.service"):
            if not YfFirewall.instance().getFwStatus():
                return yf.returnData(False, 'setting.py_msg_61e312')

        yf.setHostPort(port)
        msg = yf.getInfo('放行端口[{1}]成功', (port,))
        yf.writeLog("防火墙管理", msg)

        YfFirewall.instance().addAcceptPort(port, 'PANEL端口-配置修改', 'port')
        yf.restartPanel()

    return yf.returnData(True, 'setting.py_msg_922e9d')

# 保存菜单配置
@blueprint.route('/save_menu_config', endpoint='save_menu_config', methods=['POST'])
@panel_login_required
def save_menu_config():
    try:
        menu_data = request.form.get('menu_data', '')
        if not menu_data:
            return yf.returnData(False, 'setting.py_msg_d697e5')
        
        menus = json.loads(menu_data)
        if not isinstance(menus, list):
            return yf.returnData(False, 'setting.py_msg_e6c1aa')

        # 写入侧校验:坏条目一旦落盘,layout.html 的 `t('menu.' + item.id)`
        # 会让面板每一页 500(与 A11 hook_menu 同机制)。
        try:
            valid = utils_config._filter_menu_items(menus)
        except AttributeError:
            valid = []
        if len(valid) != len(menus) or not valid:
            return yf.returnData(False, 'setting.py_msg_e6c1aa')

        # 核心菜单完整性校验: 必须包含系统全部内置菜单ID, 不允许恶意剔除核心项或随意伪造ID
        default_ids = set(getattr(utils_config, 'DEFAULT_MENU_IDS', []))
        submitted_ids = set(item.get('id') for item in valid)
        if default_ids and not default_ids.issubset(submitted_ids):
            return yf.returnData(False, 'setting.py_msg_e6c1aa')

        panel_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        menu_file = panel_dir + '/data/menu.json'
        yf.writeFile(menu_file, json.dumps(valid))
        
        # 更新内存缓存
        utils_config._menu_cache = valid
        utils_config.clearGlobalVarCache()
        
        return yf.returnData(True, 'setting.py_msg_a087ab')
    except Exception as e:
        return yf.returnData(False, 'admin.py_msg_2cf3ac', None, str(e))

# 重置菜单配置为默认
@blueprint.route('/reset_menu_config', endpoint='reset_menu_config', methods=['POST'])
@panel_login_required
def reset_menu_config():
    try:
        utils_config.reset_menu_config()
        return yf.returnData(True, 'setting.py_msg_a087ab')
    except Exception as e:
        return yf.returnData(False, 'admin.py_msg_2cf3ac', None, str(e))

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
        except Exception as _e:
            yf.writeFileLog('[setting] 扫描旧 MySQL 数据目录失败: %s' % _e)
            
    return yf.getJson({'mysql': has_mysql, 'databases': databases})

# 数据库迁移恢复
@blueprint.route('/migrate_restore', endpoint='migrate_restore', methods=['POST'])
@panel_login_required
def migrate_restore():
    try:
        args = []
        if request.form.get('mysql', '') == '1':
            args.append('mysql')
            dbs = request.form.get('dbs', '*').strip()
            if dbs != '*':
                import re
                if not re.match(r'^[a-zA-Z0-9_\-]+(,[a-zA-Z0-9_\-]+)*$', dbs):
                    return yf.returnData(False, 'setting.py_msg_invalid_dbs')
                args.append('--dbs=' + dbs)

        panel_dir = yf.getPanelDir()
        log_file = "/tmp/migrate_restore.log"
        yf.writeFile(log_file, "正在初始化迁移任务...\n")
        
        safe_args = [yf.shlexQuote(a) for a in args]
        q_panel_dir = yf.shlexQuote(panel_dir)
        q_py = yf.shlexQuote(sys.executable)
        q_tool = yf.shlexQuote(os.path.join(panel_dir, 'panel_tools.py'))
        q_log = yf.shlexQuote(log_file)
        args_str = (' ' + ' '.join(safe_args)) if safe_args else ''
        cmd = f"cd {q_panel_dir} && echo yes | {q_py} -u {q_tool} migrate_restore{args_str} > {q_log} 2>&1 &"
        yf.execShell(cmd)
        
        yf.writeLog('面板设置', '执行数据库迁移恢复: ' + cmd)
        return yf.returnData(True, 'setting.py_msg_f04eaf')
    except Exception as e:
        return yf.returnData(False, 'admin.py_msg_fedd95', None, str(e))

@blueprint.route('/get_migrate_log', endpoint='get_migrate_log', methods=['POST'])
@panel_login_required
def get_migrate_log():
    import os
    log_file = "/tmp/migrate_restore.log"
    if not os.path.exists(log_file):
        return yf.returnData(False, 'setting.py_msg_bf59b6')
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
            return yf.returnData(False, 'setting.py_msg_ceaa07')
        # 函数内不能再 `import os`:那会把 `os` 变成局部名,使上面这行的 `os.path`
        # 抛 UnboundLocalError(真机实测接口恒回
        # 「cannot access local variable 'os' where it is not associated with a value」)。
        if not os.path.exists(db_path) or not db_path.endswith('.db'):
            return yf.returnData(False, 'setting.py_msg_invalid_db_path')

        panel_dir = yf.getPanelDir()
        log_file = "/tmp/migrate_sites.log"
        yf.writeFile(log_file, "正在初始化站点导入任务...\n")
        
        q_panel_dir = yf.shlexQuote(panel_dir)
        q_py = yf.shlexQuote(sys.executable)
        q_tool = yf.shlexQuote(os.path.join(panel_dir, 'panel_tools.py'))
        q_db = yf.shlexQuote(db_path)
        q_log = yf.shlexQuote(log_file)
        cmd = f"cd {q_panel_dir} && {q_py} -u {q_tool} import_bt_sites {q_db} > {q_log} 2>&1 &"
        yf.execShell(cmd)
        
        yf.writeLog('面板设置', '执行宝塔站点导入: ' + cmd)
        return yf.returnData(True, 'setting.py_msg_be3f67')
    except Exception as e:
        return yf.returnData(False, 'admin.py_msg_7314ec', None, str(e))

# 获取网站列表迁移日志
@blueprint.route('/get_migrate_sites_log', endpoint='get_migrate_sites_log', methods=['POST'])
@panel_login_required
def get_migrate_sites_log():
    import os
    log_file = "/tmp/migrate_sites.log"
    if not os.path.exists(log_file):
        return yf.returnData(False, 'setting.py_msg_bf59b6')
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
            except Exception as _e:
                size = 0
            data.append({'name': f, 'path': full_path, 'desc': desc, 'warning': warning, 'type': 'dir', 'size': yf.toSize(size)})
            
    # 按名称排序
    data.sort(key=lambda x: x['name'])
    return yf.getJson({'status': True, 'data': data})

# 宝塔备份目录的路径安全校验。返回合法绝对路径,非法回 ''。
# 旧实现只判 `startswith('/www/server/')`,于是 `/www/server/../../../etc`
# 直接通过 —— 真机实测 `compress_bt_backup` 在 **`/etc.zip`** 生成 43MB 的 /etc 整包,
# `delete_bt_backup` 能真删站外目录。这里再加一层 realpath 必须严格位于
# /www/server/ 之内(拦 `..` 与软链外逃)。
def _safe_bt_backup_path(path):
    path = (path or '').strip()
    if not path or not path.startswith('/www/server/'):
        return ''
    try:
        real = os.path.realpath(path)
    except Exception:
        return ''
    # 注意:不能忽视 `os.sep` 的平台差异 —— 用 normpath 拼出前缀列表更稳。
    base = os.path.realpath('/www/server')
    prefix = base.rstrip('/\\') + os.sep
    if not real.startswith(prefix):
        return ''
    return real


# 压缩宝塔备份目录
@blueprint.route('/compress_bt_backup', endpoint='compress_bt_backup', methods=['POST'])
@panel_login_required
def compress_bt_backup():
    path = _safe_bt_backup_path(request.form.get('path', ''))
    if not path:
        return yf.returnData(False, 'setting.py_msg_e05503')

    if not os.path.exists(path) or not os.path.isdir(path):
        return yf.returnData(False, 'setting.py_msg_2ccda7')

    parent_dir = os.path.dirname(path)
    base_name = os.path.basename(path)
    out_zip = os.path.join(parent_dir, base_name + '.zip')
    # 不能拼 shell:base_name 来自目录名,历史实现把它原样拼进 `zip -r {}.zip {}`。
    rc, out, err = yf.execShellRc(
        ['zip', '-r', out_zip, base_name], cwd=parent_dir, shell=False, timeout=1800)
    if rc != 0:
        yf.writeFileLog('[setting] 压缩宝塔备份失败: %s' % (err or out))
        return yf.returnData(False, 'admin.py_msg_ead17e')

    return yf.returnData(True, 'setting.py_msg_55a0e5')


# 删除宝塔备份
@blueprint.route('/delete_bt_backup', endpoint='delete_bt_backup', methods=['POST'])
@panel_login_required
def delete_bt_backup():
    path = _safe_bt_backup_path(request.form.get('path', ''))
    if not path:
        return yf.returnData(False, 'setting.py_msg_e05503')

    if not os.path.exists(path):
        return yf.returnData(False, 'setting.py_msg_ed9f63')

    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return yf.returnData(True, 'common.del_success')
    except Exception as e:
        return yf.returnData(False, 'admin.py_msg_ead17e', None, str(e))

# 设置首页提醒
@blueprint.route('/set_home_notice', endpoint='set_home_notice', methods=['POST'])
@panel_login_required
def set_home_notice():
    home_notice = request.form.get('home_notice', '')
    if len(home_notice) > 50:
        return yf.returnData(False, 'setting.py_msg_c97b19')
    
    src_home_notice = thisdb.getOption('home_notice')
    if home_notice != src_home_notice:
        thisdb.setOption('home_notice', home_notice)
        utils_config.clearGlobalVarCache()
    return yf.returnData(True, 'setting.py_msg_a3bec2')

# 获取支持语言列表及当前语言
@blueprint.route('/get_languages', endpoint='get_languages', methods=['GET', 'POST'])
def get_languages():
    from core.i18n import SUPPORTED_LANGUAGES, get_current_lang
    return yf.returnData(True, 'ok', {
        'languages': SUPPORTED_LANGUAGES,
        'current': get_current_lang()
    })

# 设置语言偏好
@blueprint.route('/set_language', endpoint='set_language', methods=['POST'])
def set_language():
    from flask import jsonify, make_response
    from core.i18n import SUPPORTED_CODES, normalize_lang, DEFAULT_LANG
    from admin.common import isLogined

    lang = request.form.get('lang', '')
    norm_lang = normalize_lang(lang)
    if not norm_lang or norm_lang not in SUPPORTED_CODES:
        norm_lang = DEFAULT_LANG

    # 安全防护：仅当已登录管理员发起时，才持久化写入服务端全局配置文件
    # 未登录访客仅设置客户端自身的 Cookie，杜绝任意访客篡改系统全局默认语言
    if isLogined():
        panel_dir = yf.getPanelDir()
        lang_file = os.path.join(panel_dir, 'data/language.pl')
        yf.writeFile(lang_file, norm_lang)

    res_data = yf.returnData(True, 'common.set_success', {'lang': norm_lang})
    response = make_response(jsonify(res_data))
    response.set_cookie('yf_lang', norm_lang, max_age=365*86400, path='/', samesite='Lax')
    return response
