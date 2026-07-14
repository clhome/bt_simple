# coding: utf-8
import sys
import os
import json
import re
import glob
import subprocess
import shlex

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.mw as mw

__target_tag = 'YuFeng'

def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)
    if args_len > 0:
        val = args[0].strip()
        import base64
        import urllib.parse
        try:
            decoded = urllib.parse.unquote(base64.b64decode(val).decode('utf-8'))
            if decoded.startswith('{') and decoded.endswith('}'):
                return json.loads(decoded)
        except Exception:
            pass
        try:
            if val.startswith('{') and val.endswith('}'):
                return json.loads(val)
        except Exception:
            pass
        for i in range(args_len):
            t = args[i].split(':', 1)
            if len(t) == 2:
                tmp[t[0]] = t[1]
    return tmp

def _run_cmd(cmd):
    """安全命令执行封装"""
    try:
        res = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        return {"status": res.returncode == 0, "data": res.stdout.strip(), "error": res.stderr.strip()}
    except Exception as e:
        return {"status": False, "msg": str(e), "data": ""}

def _sync_daemon_reload(service_id):
    """检测外部修改并自动同步"""
    res = _run_cmd(f"systemctl show --property=NeedDaemonReload {service_id}")
    if "NeedDaemonReload=yes" in res["data"]:
        _run_cmd("systemctl daemon-reload")

def get_services():
    """获取且仅获取 YuFeng 标签的服务"""
    services = []
    for file_path in glob.glob('/etc/systemd/system/*.service'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if f"Documentation=tag:{__target_tag}" in content or "Documentation=https://yufeng.tag" in content:
                    current_id = os.path.basename(file_path)
                    status_res = _run_cmd(f"systemctl is-active {current_id}")
                    active_status = status_res["data"]
                    failed_res = _run_cmd(f"systemctl is-failed {current_id}")
                    is_failed = failed_res["data"] == "failed"
                    enabled_res = _run_cmd(f"systemctl is-enabled {current_id}")
                    services.append({
                        "id": current_id,
                        "name": current_id.replace('.service', ''),
                        "status": "failed" if is_failed else active_status,
                        "enabled": enabled_res["data"] == "enabled"
                    })
        except Exception:
            continue
    return yf.returnJson(True, "获取成功", services)

def get_service_detail():
    args = getArgs()
    service_name = args.get('service_name', '').strip()
    if not re.match(r"^[a-zA-Z0-9_-]+$", service_name):
        return yf.returnJson(False, "服务名不合法")
        
    file_path = f"/etc/systemd/system/{service_name}.service"
    if not os.path.exists(file_path):
        return yf.returnJson(False, "服务不存在")
        
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    if f"Documentation=tag:{__target_tag}" not in content and "Documentation=https://yufeng.tag" not in content:
        return yf.returnJson(False, "越权拦截：非专属服务禁止读取配置！")
        
    return yf.returnJson(True, "获取成功", content)

def create_or_modify_service():
    args = getArgs()
    service_name = args.get('service_name', '').strip()
    mode = args.get('mode', 'simple')
    
    if not re.match(r"^[a-zA-Z0-9_-]+$", service_name):
        return yf.returnJson(False, "服务名只能包含字母、数字、下划线和中划线！")
        
    service_id = f"{service_name}.service"
    file_path = f"/etc/systemd/system/{service_id}"
    service_content = ""
    
    if mode == 'simple':
        user_name = args.get('run_user', 'www').strip()
        work_dir = args.get('work_dir', '').strip()
        exec_start = args.get('exec_start', '').strip()
        
        # CRLF Injection 防御
        user_name = re.sub(r'[\r\n]', '', user_name)
        work_dir = re.sub(r'[\r\n]', '', work_dir)
        exec_start = re.sub(r'[\r\n]', '', exec_start)
        
        if not work_dir.startswith('/'):
            return yf.returnJson(False, "工作目录必须是绝对路径（以 / 开头）")
        if not exec_start:
            return yf.returnJson(False, "启动命令不能为空")
            
        service_content = f"""[Unit]
Description=Managed by yufeng_systemd Plugin
Documentation=https://yufeng.tag
After=network-online.target

[Service]
Type=simple
User={user_name}
WorkingDirectory={work_dir}
ExecStart={exec_start}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    else:
        user_content = args.get('service_content', '').strip()
        if not user_content or '[Unit]' not in user_content or '[Service]' not in user_content:
            return yf.returnJson(False, "配置格式错误，必须包含 [Unit] 和 [Service] 节点")
            
        content = re.sub(r'^Documentation=.*$\n?', '', user_content, flags=re.MULTILINE)
        service_content = content.replace('[Unit]', f'[Unit]\nDocumentation=https://yufeng.tag')
        service_content = re.sub(r'\n+', '\n', service_content)

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(service_content)
    except Exception as e:
        return yf.returnJson(False, f"保存配置文件失败: {str(e)}")
        
    _run_cmd("systemctl daemon-reload")
    _run_cmd(f"systemctl enable {service_id}")
    _run_cmd(f"systemctl restart {service_id}")
    _run_cmd(f"systemctl reset-failed {service_id}")
    
    return yf.returnJson(True, "服务配置成功并已启动")

def control_service():
    args = getArgs()
    service_name = args.get('service_name', '').strip()
    action = args.get('action', '').strip()
    
    if not re.match(r"^[a-zA-Z0-9_-]+$", service_name):
        return yf.returnJson(False, "服务名不合法")
        
    if action not in ['start', 'stop', 'restart', 'enable', 'disable']:
        return yf.returnJson(False, "不支持的操作")
        
    service_id = f"{service_name}.service"
    file_path = f"/etc/systemd/system/{service_id}"
    if not os.path.exists(file_path):
        return yf.returnJson(False, "服务不存在")
    with open(file_path, 'r', encoding='utf-8') as f:
        file_body = f.read()
        if f"Documentation=tag:{__target_tag}" not in file_body and "Documentation=https://yufeng.tag" not in file_body:
            return yf.returnJson(False, "越权拦截：非专属服务禁止操作！")
            
    _sync_daemon_reload(service_id)
    
    if action in ['start', 'restart']:
        _run_cmd(f"systemctl reset-failed {service_id}")
        
    res = _run_cmd(f"systemctl {action} {service_id}")
    if res["status"]:
        return yf.returnJson(True, "操作成功")
    else:
        return yf.returnJson(False, f"操作失败: {res['error']}")

def delete_service():
    args = getArgs()
    service_name = args.get('service_name', '').strip()
    if not re.match(r"^[a-zA-Z0-9_-]+$", service_name):
        return yf.returnJson(False, "服务名不合法")
        
    service_id = f"{service_name}.service"
    file_path = f"/etc/systemd/system/{service_id}"
    
    if not os.path.exists(file_path):
        return yf.returnJson(False, "服务不存在")
        
    with open(file_path, 'r', encoding='utf-8') as f:
        file_body = f.read()
        if f"Documentation=tag:{__target_tag}" not in file_body and "Documentation=https://yufeng.tag" not in file_body:
            return yf.returnJson(False, "越权拦截：非专属服务禁止删除！")
            
    active_status = _run_cmd(f"systemctl is-active {service_id}")["data"]
    if active_status == "active":
        return yf.returnJson(False, "请先停止该服务后再进行删除")
        
    _run_cmd(f"systemctl disable {service_id}")
    os.remove(file_path)
    
    # 清理日志清空时间文件
    clear_file = f"/etc/systemd/system/{service_id}.clear_time"
    if os.path.exists(clear_file):
        try:
            os.remove(clear_file)
        except Exception:
            pass
            
    _run_cmd("systemctl daemon-reload")
    
    return yf.returnJson(True, "服务删除成功")

def get_service_logs():
    args = getArgs()
    service_name = args.get('service_name', '').strip()
    if not re.match(r"^[a-zA-Z0-9_-]+$", service_name):
        return yf.returnJson(False, "服务名不合法")
        
    service_id = f"{service_name}.service"
    clear_file = f"/etc/systemd/system/{service_id}.clear_time"
    
    since_arg = ""
    if os.path.exists(clear_file):
        try:
            with open(clear_file, 'r', encoding='utf-8') as f:
                clear_time = f.read().strip()
                if clear_time:
                    since_arg = f'--since "{clear_time}"'
        except Exception:
            pass
            
    cmd = f"journalctl -u {service_id} {since_arg} -n 100 --no-pager"
    res = _run_cmd(cmd)
    
    if res["status"]:
        return yf.returnJson(True, "获取成功", res["data"])
    else:
        return yf.returnJson(False, f"获取日志失败: {res['error']}")

def clear_service_logs():
    args = getArgs()
    service_name = args.get('service_name', '').strip()
    if not re.match(r"^[a-zA-Z0-9_-]+$", service_name):
        return yf.returnJson(False, "服务名不合法")
        
    service_id = f"{service_name}.service"
    clear_file = f"/etc/systemd/system/{service_id}.clear_time"
    
    import time
    now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    
    try:
        with open(clear_file, 'w', encoding='utf-8') as f:
            f.write(now_str)
        return yf.returnJson(True, "日志已成功清空")
    except Exception as e:
        return yf.returnJson(False, f"清空日志失败: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("error")
        sys.exit()
    func = sys.argv[1]
    if func == 'get_services':
        print(get_services())
    elif func == 'get_service_detail':
        print(get_service_detail())
    elif func == 'create_or_modify_service':
        print(create_or_modify_service())
    elif func == 'control_service':
        print(control_service())
    elif func == 'delete_service':
        print(delete_service())
    elif func == 'get_service_logs':
        print(get_service_logs())
    elif func == 'clear_service_logs':
        print(clear_service_logs())
    else:
        print('error')
