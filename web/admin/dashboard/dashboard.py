# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import io
import time
import base64
import json
import os
import sys

from flask import Blueprint, render_template
from flask import make_response
from flask import redirect
from flask import Response
from flask import request,g

from admin.common import isLogined
from admin.user_login_check import panel_login_required
from admin import cache,session

import core.yf as yf
import thisdb


blueprint = Blueprint('dashboard', __name__, url_prefix='/', template_folder='../../templates')
@blueprint.route('/', endpoint='index', methods=['GET'])
@panel_login_required
def index():
    name = thisdb.getOption('template', default='default')
    return render_template('%s/index.html' % name)

# 安全路径
@blueprint.route('/<path>',endpoint='admin_safe_path',methods=['GET'])
def admin_safe_path(path):
    login = request.args.get('login', '')
    if login != '':
        try:
            # print(login)
            login_str = base64.b64decode(login)
            login_str = login_str.decode('utf-8')
            data = json.loads(login_str)

            time_now = time.time() * 1000
            time_diff = time_now - data['time']

            if time_diff > 2000:
                return redirect('/')


            info = thisdb.getUserByName(data['username'])
            if info is None:
                return redirect('/')

            if info['password'] != yf.md5(data['password']):
                return redirect('/')

            session['login'] = True
            session['username'] = info['name']
            session['overdue'] = int(time.time()) + 7 * 24 * 60 * 60

            client_ip = yf.getClientIp()
            thisdb.updateUserLoginTime(client_ip)
            yf.writeLog('用户登录', '用户[{1}]通过安全入口快捷登录成功, 登录IP:{2}', (info['name'], client_ip))
            return redirect('/')
        except Exception as e:
            pass
        

    db_path = thisdb.getOption('admin_path', default='')
    name = thisdb.getOption('template', default='default')
    if isLogined():
       return redirect('/')
    if db_path == path:
        return render_template('%s/login.html' % name)

    unauthorized_status = thisdb.getOption('unauthorized_status', default='0')
    if unauthorized_status == '0':
        return render_template('%s/path.html' % name)
    return Response(status=int(unauthorized_status))

# 获取最近登录记录 (支持专业精致微表格展示)
def parse_ip_type(ip):
    if not ip or ip in ('127.0.0.1', 'localhost', '::1'):
        return '本地回环'
    if ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.16.') or ip.startswith('172.17.') or ip.startswith('172.18.') or ip.startswith('172.19.') or ip.startswith('172.20.') or ip.startswith('172.31.'):
        return '局域网内网'
    return '公网接入'

def get_location_from_pconline(ip):
    try:
        import urllib.request
        import json
        url = 'https://whois.pconline.com.cn/ipJson.jsp?ip=' + ip + '&json=true'
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
        with urllib.request.urlopen(req, timeout=3) as response:
            content = response.read()
            try:
                text = content.decode('gbk')
            except Exception:
                try:
                    text = content.decode('gb18030')
                except Exception:
                    text = content.decode('utf-8', errors='ignore')
            data = json.loads(text)
            if data and 'addr' in data:
                pro = data.get('pro', '').replace('省', '')
                city = data.get('city', '').replace('市', '')
                addr = data.get('addr', '')
                proCode = data.get('proCode', '')
                if proCode == '999999' or (not pro and not city):
                    return addr if addr else "海外/未知"
                
                loc = f"{pro} {city}".strip()
                if not loc:
                    loc = addr
                return loc
    except Exception:
        pass
    return "未知归属地"

@blueprint.route('/get_ip_location', endpoint='get_ip_location', methods=['GET', 'POST'])
@panel_login_required
def get_ip_location():
    ip = request.values.get('ip', '').strip()
    if not ip:
        return yf.returnData(False, 'ip不能为空')
    
    ip_type = parse_ip_type(ip)
    if ip_type != '公网接入':
        return yf.returnData(True, 'ok', {'ip': ip, 'location': ip_type, 'is_local': True})
    
    loc = get_location_from_pconline(ip)
    return yf.returnData(True, 'ok', {'ip': ip, 'location': loc, 'is_local': False})

@blueprint.route('/get_recent_logins', endpoint='get_recent_logins', methods=['GET', 'POST'])
@panel_login_required
def get_recent_logins():
    import re
    import time
    curr_ip = yf.getClientIp()
    try:
        limit = int(request.values.get('limit', 2))
    except Exception:
        limit = 2
    if limit > 50: limit = 50

    try:
        page = int(request.values.get('p', 1))
    except Exception:
        page = 1
    if page < 1: page = 1

    status_filter = request.values.get('status', 'all').strip()
    method_filter = request.values.get('method', 'all').strip()
    tojs = request.values.get('tojs', 'getAllLoginLogs').strip()

    where_clauses = ["type in ('用户登录', 'SSH管理')"]
    params = []

    if status_filter == 'success':
        where_clauses.append("log like '%成功%'")
    elif status_filter == 'fail':
        where_clauses.append("(log like '%错误%' or log like '%失败%' or log like '%封禁%')")

    if method_filter == 'web':
        where_clauses.append("type = '用户登录'")
    elif method_filter == 'ssh':
        where_clauses.append("(type = 'SSH管理' or log like '%SSH%' or log like '%ssh%')")

    sql_where = " and ".join(where_clauses)
    
    total_count = 0
    raw_logs = []
    try:
        total_count = yf.M('logs').where(sql_where, tuple(params)).count()
        start = (page - 1) * limit
        limit_str = f"{start},{limit}"
        raw_logs = yf.M('logs').field('id,type,log,uid,add_time').where(sql_where, tuple(params)).order('id desc').limit(limit_str).select()
    except Exception as ex:
        print("get_recent_logins db error:", ex)
        raw_logs = []
    
    result_list = []
    if isinstance(raw_logs, list):
        for item in raw_logs:
            log_type = item.get('type', '')
            log_text = item.get('log', '')
            time_str = item.get('add_time', '')
            
            # 状态判断
            if '成功' in log_text:
                status = 'success'
                status_text = '成功'
            elif '错误' in log_text or '失败' in log_text or '封禁' in log_text:
                status = 'fail'
                status_text = '失败'
            else:
                status = 'info'
                status_text = '记录'
                
            # 登录方式 (Web / SSH)
            if log_type == 'SSH管理' or 'SSH' in log_text or 'ssh' in log_text:
                method = 'SSH'
            else:
                method = 'Web'

            # IP 提取
            ip_match = re.search(r'(?:登录IP:|IP:|服务器\s*\[)\s*([0-9a-fA-F:\.]+)', log_text)
            if ip_match:
                ip = ip_match.group(1).strip()
                # 排除 port 形式
                if ':' in ip and not ip.startswith(':'):
                    parts = ip.split(':')
                    if len(parts) == 2 and parts[1].isdigit():
                        ip = parts[0]
            else:
                ip_general = re.search(r'([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})', log_text)
                ip = ip_general.group(1).strip() if ip_general else curr_ip
                
            # 详细类型说明
            if method == 'SSH':
                details = 'SSH终端登录'
            elif '二次验证' in log_text:
                details = '2FA二次验证'
            elif '安全入口' in log_text:
                details = '安全入口快捷'
            elif '验证码错误' in log_text:
                details = '验证码错误'
            elif '用户名或密码错误' in log_text:
                details = '密码错误'
            else:
                details = 'Web密码登录'
                
            # 计算 Unix 时间戳（秒）
            log_timestamp = 0
            if time_str:
                try:
                    t_struct = time.strptime(time_str[:19], '%Y-%m-%d %H:%M:%S')
                    log_timestamp = int(time.mktime(t_struct))
                except Exception:
                    pass
            if not log_timestamp:
                log_timestamp = int(time.time())

            ip_type = parse_ip_type(ip)
            is_local = (ip_type != '公网接入')

            result_list.append({
                'id': item.get('id'),
                'method': method,
                'ip': ip,
                'ip_type': ip_type,
                'is_local': is_local,
                'location': ip_type if is_local else '',
                'is_current': (ip == curr_ip),
                'status': status,
                'status_text': status_text,
                'log_time': time_str,
                'timestamp': log_timestamp,
                'details': details
            })
        
    # 如果没有任何登录历史且第一页无筛选，兜底展示一条当前用户记录
    if not result_list and page == 1 and status_filter == 'all' and method_filter == 'all':
        user_info = thisdb.getUserById(1) or {}
        last_time = user_info.get('login_time') or yf.formatDate()
        last_ip = user_info.get('login_ip') or curr_ip
        ip_type = parse_ip_type(last_ip)
        is_local = (ip_type != '公网接入')
        
        now_ts = int(time.time())
        try:
            t_struct = time.strptime(last_time[:19], '%Y-%m-%d %H:%M:%S')
            now_ts = int(time.mktime(t_struct))
        except Exception:
            pass

        result_list.append({
            'id': 1,
            'method': 'Web',
            'ip': last_ip,
            'ip_type': ip_type,
            'is_local': is_local,
            'location': ip_type if is_local else '',
            'is_current': (last_ip == curr_ip),
            'status': 'success',
            'status_text': '成功',
            'log_time': last_time,
            'timestamp': now_ts,
            'details': '当前活跃会话'
        })
        total_count = 1
        
    page_html = ''
    try:
        page_html = yf.getPage({
            'count': total_count,
            'tojs': tojs,
            'p': page,
            'row': limit
        })
    except Exception as ex:
        print("getPage error:", ex)
        page_html = ''

    return yf.returnData(True, 'ok', {
        'current_ip': curr_ip,
        'list': result_list,
        'count': total_count,
        'page': page_html
    })

# 仅针对webhook插件
@blueprint.route("/hook", methods=['POST', 'GET'])
def webhook():
    # 兼容获取关键数据
    access_key = request.args.get('access_key', '').strip()
    if access_key == '':
        access_key = request.form.get('access_key', '').strip()

    params = request.args.get('params', '').strip()
    if params == '':
        params = request.form.get('params', '').strip()

    input_args = {
        'access_key': access_key,
        'params': params,
    }

    wh_install_path = yf.getServerDir() + '/webhook'
    if not os.path.exists(wh_install_path):
        return yf.returnData(False, '请先安装WebHook插件!')

    package = yf.getPanelDir() + "/plugins/webhook"
    if not package in sys.path:
        sys.path.append(package)
        
    try:
        import webhook_index
        return webhook_index.runShellArgs(input_args)
    except Exception as e:
        return str(e)
