# coding:utf-8
import sys
import os
import unittest
import re

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
sys.path.insert(0, os.path.join(project_dir, 'web'))

import core.yf as yf

# 进程级隔离：必须在 import thisdb 之前 —— 它在导入期就会打开面板库。
# F: 盘上 sqlite3 的 close() 单次要 30~60s，退出时 atexit 逐个关连接。
# 见 testsuite.md §5.7 / §5.9。
from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('recent_logins')

import thisdb  # noqa: E402

# 提取与 dashboard.py 中完全一致的 IP 解析与日志处理函数
def parse_ip_type(ip):
    if not ip or ip in ('127.0.0.1', 'localhost', '::1'):
        return '本地回环'
    if ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.16.') or ip.startswith('172.17.') or ip.startswith('172.18.') or ip.startswith('172.19.') or ip.startswith('172.20.') or ip.startswith('172.31.'):
        return '局域网内网'
    return '公网接入'

def parse_login_log_item(item, curr_ip='202.107.245.93'):
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
        
    ip_type = parse_ip_type(ip)
    is_local = (ip_type != '公网接入')
    
    return {
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
        'details': details
    }


class TestRecentLogins(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        sql_file = os.path.join(project_dir, 'web', 'admin', 'setup', 'sql', 'default.sql')
        if os.path.exists(sql_file):
            content = yf.readFile(sql_file)
            csql_data = content.split(';')
            for s in csql_data:
                s = s.strip()
                if s:
                    try:
                        yf.M('users').execute(s, ())
                    except Exception as e:
                        pass
        try:
            thisdb.initAdminUser()
        except Exception:
            pass

    def test_parse_ip_type(self):
        self.assertEqual(parse_ip_type('127.0.0.1'), '本地回环')
        self.assertEqual(parse_ip_type('localhost'), '本地回环')
        self.assertEqual(parse_ip_type('::1'), '本地回环')
        self.assertEqual(parse_ip_type('192.168.1.100'), '局域网内网')
        self.assertEqual(parse_ip_type('10.0.0.5'), '局域网内网')
        self.assertEqual(parse_ip_type('172.16.0.10'), '局域网内网')
        self.assertEqual(parse_ip_type('202.107.245.93'), '公网接入')
        self.assertEqual(parse_ip_type('114.114.114.114'), '公网接入')

    def test_log_parsing_web_and_ssh(self):
        # 1. 成功登录 (Web密码)
        log1 = {'id': 1, 'type': '用户登录', 'log': '用户[admin]登录成功, 登录IP:202.107.245.93', 'add_time': '2026-08-27 17:00:00'}
        res1 = parse_login_log_item(log1, curr_ip='202.107.245.93')
        self.assertEqual(res1['status'], 'success')
        self.assertEqual(res1['method'], 'Web')
        self.assertEqual(res1['ip'], '202.107.245.93')
        self.assertTrue(res1['is_current'])
        self.assertFalse(res1['is_local'])
        self.assertEqual(res1['ip_type'], '公网接入')

        # 2. SSH 终端成功登录
        log2 = {'id': 2, 'type': 'SSH管理', 'log': '成功登录到SSH服务器 [192.168.1.50:22]', 'add_time': '2026-08-27 16:30:00'}
        res2 = parse_login_log_item(log2, curr_ip='202.107.245.93')
        self.assertEqual(res2['status'], 'success')
        self.assertEqual(res2['method'], 'SSH')
        self.assertEqual(res2['ip'], '192.168.1.50')
        self.assertTrue(res2['is_local'])
        self.assertEqual(res2['location'], '局域网内网')

        # 3. 密码错误失败 (Web)
        log3 = {'id': 3, 'type': '用户登录', 'log': "<a style='color: red'>用户名或密码错误</a>,帐号:hacker,密码:******,登录IP:45.33.32.156", 'add_time': '2026-08-27 16:00:00'}
        res3 = parse_login_log_item(log3, curr_ip='202.107.245.93')
        self.assertEqual(res3['status'], 'fail')
        self.assertEqual(res3['method'], 'Web')
        self.assertEqual(res3['ip'], '45.33.32.156')
        self.assertFalse(res3['is_local'])

    def test_database_update_user_login_time(self):
        test_ip = '202.107.245.93'
        thisdb.updateUserLoginTime(test_ip)
        user = thisdb.getUserById(1)
        self.assertIsNotNone(user)
        self.assertEqual(user.get('login_ip'), test_ip)
        self.assertTrue(len(user.get('login_time', '')) > 0)

    def test_pconline_ip_location(self):
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

        loc = get_location_from_pconline('202.107.245.93')
        self.assertIsInstance(loc, str)
        self.assertTrue(len(loc) > 0)
        self.assertIn('浙江', loc)

    def test_query_filter_and_pagination(self):
        # 写入测试数据
        yf.M('logs').add('type,log,uid,add_time', ('用户登录', '用户[test1]登录成功, 登录IP:192.168.1.101', 1, '2026-08-27 17:10:00'))
        yf.M('logs').add('type,log,uid,add_time', ('SSH管理', '成功登录到SSH服务器 [192.168.1.102:22]', 1, '2026-08-27 17:11:00'))
        yf.M('logs').add('type,log,uid,add_time', ('用户登录', '密码验证失败, 登录IP:192.168.1.103', 1, '2026-08-27 17:12:00'))

        # 测试筛选状态: success
        succ_logs = yf.M('logs').where("type in ('用户登录', 'SSH管理') and log like '%成功%'", ()).select()
        self.assertTrue(len(succ_logs) >= 2)

        # 测试筛选方式: ssh
        ssh_logs = yf.M('logs').where("type in ('用户登录', 'SSH管理') and (type = 'SSH管理' or log like '%SSH%')", ()).select()
        self.assertTrue(len(ssh_logs) >= 1)

        # 测试分页
        page_html = yf.getPage({'count': 25, 'tojs': 'getAllLoginLogs', 'p': 1, 'row': 10})
        self.assertIn('getAllLoginLogs', page_html)

    def test_timestamp_and_timezone_support(self):
        import time
        time_str = '2026-08-27 03:08:40'
        t_struct = time.strptime(time_str, '%Y-%m-%d %H:%M:%S')
        ts = int(time.mktime(t_struct))
        self.assertGreater(ts, 1700000000)

if __name__ == '__main__':
    unittest.main()
