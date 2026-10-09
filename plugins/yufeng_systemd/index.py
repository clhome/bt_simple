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

import core.yf as yf
import logging

_log = logging.getLogger('yf.yufeng_systemd')

__target_tag = 'YuFeng'

#: 专属 unit 的归属标记：两种历史写法都视为「本插件创建/接管」
_OWN_TAGS = (f"Documentation=tag:{__target_tag}", "Documentation=https://yufeng.tag")
#: unit 名白名单：首个字符必须是字母/数字（否则 `-rf`、`--now` 这类名字会被 systemctl 当成选项）
_SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
_UNIT_DIR = '/etc/systemd/system'


def _arg_str(args, key, default=''):
    """取字符串参数。

    getArgs() 的 JSON 里同一字段可能是数字/None/对象，旧实现直接 `.strip()`
    会抛 AttributeError（真机实测 7/7 接口整段堆栈）。非字符串统一转成字符串，
    让后续白名单去判断合法性，而不是崩成 500。
    """
    val = args.get(key, default)
    if val is None:
        return default
    if not isinstance(val, str):
        val = str(val)
    return val.strip()


def _unit_path(service_name):
    return f"{_UNIT_DIR}/{service_name}.service"


def _read_text(path):
    """读文件，失败回 None（旧实现直接 open → 不可读即整段堆栈）。"""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception as _e:
        _log.debug('[yufeng_systemd] 读取 %s 失败: %s', path, _e)
        return None


def _is_owned(content):
    return bool(content) and any(tag in content for tag in _OWN_TAGS)


def _unit_state(service_id):
    """一次 `systemctl show` 取回机器可读状态。

    旧实现对每个 unit 连开 3 个 `systemctl is-active/is-failed/is-enabled` 子进程
    （真机实测 3 unit = 12 次 fork），这里收敛成 1 次并直接读属性值，
    避免文本匹配带来的假阳性。
    """
    state = {'active': '', 'file': '', 'need_reload': False}
    res = _run_cmd(f"systemctl show -p ActiveState -p UnitFileState -p NeedDaemonReload {service_id}")
    for line in res['data'].splitlines():
        key, _, val = line.partition('=')
        key, val = key.strip(), val.strip()
        if key == 'ActiveState':
            state['active'] = val
        elif key == 'UnitFileState':
            state['file'] = val
        elif key == 'NeedDaemonReload':
            state['need_reload'] = (val.lower() == 'yes')
    return state


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
        except Exception as _e:
            _log.debug('[yufeng_systemd] getArgs 异常已忽略: %s', _e)
        try:
            if val.startswith('{') and val.endswith('}'):
                return json.loads(val)
        except Exception as _e:
            _log.debug('[yufeng_systemd] getArgs 异常已忽略: %s', _e)
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
        return {"status": False, "error": str(e), "data": ""}

def _sync_daemon_reload(service_id):
    """检测外部修改并自动同步"""
    if _unit_state(service_id)['need_reload']:
        _run_cmd("systemctl daemon-reload")

def get_services():
    """获取且仅获取 YuFeng 标签的服务"""
    services = []
    for file_path in sorted(glob.glob(f'{_UNIT_DIR}/*.service')):
        content = _read_text(file_path)
        if not _is_owned(content):
            continue
        service_name = os.path.basename(file_path)[:-len('.service')]
        # 与 control/delete 同一把尺子：名字不合法（含 `.`、`@`、空格等）的 unit
        # 那些入口一律拒绝，列表里也就不该出现，否则用户点了必然报错。
        if not _SERVICE_NAME_RE.match(service_name):
            continue
        service_id = f"{service_name}.service"
        state = _unit_state(service_id)
        services.append({
            "id": service_id,
            "name": service_name,
            "status": state['active'] or 'unknown',
            "enabled": state['file'].startswith('enabled'),
        })
    return yf.returnJson(True, "获取成功", services)

def get_service_detail():
    args = getArgs()
    service_name = _arg_str(args, 'service_name')
    if not _SERVICE_NAME_RE.match(service_name):
        return yf.returnJson(False, "服务名不合法")

    content = _read_text(_unit_path(service_name))
    if content is None:
        return yf.returnJson(False, "服务不存在")

    if not _is_owned(content):
        return yf.returnJson(False, "越权拦截：非专属服务禁止读取配置！")

    return yf.returnJson(True, "获取成功", content)

def create_or_modify_service():
    args = getArgs()
    service_name = _arg_str(args, 'service_name')
    mode = _arg_str(args, 'mode', 'simple') or 'simple'
    
    if not _SERVICE_NAME_RE.match(service_name):
        return yf.returnJson(False, "服务名只能包含字母、数字、下划线和中划线！")
        
    service_id = f"{service_name}.service"
    file_path = _unit_path(service_name)
    service_content = ""

    # 归属闸：同名 unit 已存在但不是本插件接管的，一律拒绝（旧实现直接覆盖写入，
    # 真机实测可把系统自带的 redis.service 之类整个换成面板内容并 enable+restart）。
    if os.path.exists(file_path):
        existing = _read_text(file_path)
        if existing is None:
            return yf.returnJson(False, "读取已有服务配置失败，拒绝覆盖")
        if not _is_owned(existing):
            return yf.returnJson(False, "越权拦截：同名非专属服务已存在，禁止覆盖！")
    
    if mode == 'simple':
        user_name = _arg_str(args, 'run_user', 'www')
        work_dir = _arg_str(args, 'work_dir')
        exec_start = _arg_str(args, 'exec_start')
        
        # CRLF Injection 防御
        user_name = re.sub(r'[\r\n\x00]', '', user_name)
        work_dir = re.sub(r'[\r\n\x00]', '', work_dir)
        exec_start = re.sub(r'[\r\n\x00]', '', exec_start)

        # 运行用户直接进 `User=`，带空格/引号会写出语法错误或被 systemd 忽略的 unit
        if not re.match(r"^[a-zA-Z0-9_.-]+$", user_name):
            return yf.returnJson(False, "运行用户不合法！")
        
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
        user_content = _arg_str(args, 'service_content')
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
    _run_cmd(f"systemctl reset-failed {service_id}")
    enable_res = _run_cmd(f"systemctl enable {service_id}")
    start_res = _run_cmd(f"systemctl restart {service_id}")

    # 旧实现无论 enable/restart 成败都回「配置成功并已启动」：真机实测运行用户不存在时
    # 服务只到 activating，前端却提示已启动。这里回读机器可读状态并如实报错。
    state = _unit_state(service_id)
    active_state = state['active'] or 'unknown'
    file_state = state['file'] or 'unknown'
    problems = []
    if not enable_res["status"]:
        problems.append("开机自启设置失败")
    if not start_res["status"]:
        problems.append("启动命令执行失败")
    if state['active'] != 'active':
        problems.append("当前状态: %s" % active_state)
    if problems:
        detail = (start_res["error"] or enable_res["error"] or '').strip()[:200]
        msg = "服务配置已保存，但" + "、".join(problems)
        if detail:
            msg += "：" + detail
        return yf.returnJson(False, msg)
    if not state['file'].startswith('enabled'):
        return yf.returnJson(False, f"服务已启动，但开机自启未生效（当前: {file_state}）")

    return yf.returnJson(True, "服务配置成功并已启动")

def control_service():
    args = getArgs()
    service_name = _arg_str(args, 'service_name')
    action = _arg_str(args, 'action')
    
    if not _SERVICE_NAME_RE.match(service_name):
        return yf.returnJson(False, "服务名不合法")
        
    if action not in ['start', 'stop', 'restart', 'enable', 'disable']:
        return yf.returnJson(False, "不支持的操作")
        
    service_id = f"{service_name}.service"
    file_body = _read_text(_unit_path(service_name))
    if file_body is None:
        return yf.returnJson(False, "服务不存在")
    if not _is_owned(file_body):
        return yf.returnJson(False, "越权拦截：非专属服务禁止操作！")
            
    _sync_daemon_reload(service_id)
    
    if action in ['start', 'restart']:
        _run_cmd(f"systemctl reset-failed {service_id}")
        
    res = _run_cmd(f"systemctl {action} {service_id}")
    if not res["status"]:
        return yf.returnJson(False, f"操作失败: {res['error'] or res['data']}")

    # 退出码 0 不等于目标状态达成（Type=simple 的 unit 起不来时 systemctl start 依旧 rc=0，
    # 真机实测：运行用户不存在的 unit 回「操作成功」）。回读状态再回话。
    state = _unit_state(service_id)
    active = state['active'] or 'unknown'
    file_state = state['file'] or 'unknown'
    if action in ('start', 'restart') and state['active'] != 'active':
        return yf.returnJson(False, f"操作失败：服务未进入 active 状态（当前: {active}）")
    if action == 'stop' and state['active'] not in ('inactive', 'failed'):
        return yf.returnJson(False, f"操作失败：服务未停止（当前: {active}）")
    if action in ('enable', 'disable') and state['file'].startswith('enabled') != (action == 'enable'):
        return yf.returnJson(False, f"操作失败：自启状态未生效（当前: {file_state}）")

    return yf.returnJson(True, "操作成功")

def delete_service():
    args = getArgs()
    service_name = _arg_str(args, 'service_name')
    if not _SERVICE_NAME_RE.match(service_name):
        return yf.returnJson(False, "服务名不合法")
        
    service_id = f"{service_name}.service"
    file_path = _unit_path(service_name)
    
    file_body = _read_text(file_path)
    if file_body is None:
        return yf.returnJson(False, "服务不存在")
        
    if not _is_owned(file_body):
        return yf.returnJson(False, "越权拦截：非专属服务禁止删除！")

    state = _unit_state(service_id)
    if state['active'] in ('active', 'activating', 'deactivating', 'reloading'):
        return yf.returnJson(False, "请先停止该服务后再进行删除")
            
    _run_cmd(f"systemctl disable {service_id}")
    try:
        os.remove(file_path)
    except Exception as e:
        return yf.returnJson(False, f"删除服务文件失败: {str(e)}")
    
    # 清理日志清空时间文件
    clear_file = f"{file_path}.clear_time"
    if os.path.exists(clear_file):
        try:
            os.remove(clear_file)
        except Exception as _e:
            _log.debug('[yufeng_systemd] delete_service 异常已忽略: %s', _e)
            
    _run_cmd("systemctl daemon-reload")
    _run_cmd(f"systemctl reset-failed {service_id}")
    
    return yf.returnJson(True, "服务删除成功")

def get_service_logs():
    args = getArgs()
    service_name = _arg_str(args, 'service_name')
    if not _SERVICE_NAME_RE.match(service_name):
        return yf.returnJson(False, "服务名不合法")
        
    service_id = f"{service_name}.service"
    file_path = _unit_path(service_name)

    # 旧实现不校验归属也不校验存在：任意系统服务的 journal 都能被面板拉出来
    # （真机实测对非专属/不存在的 unit 均回 status:true）。
    file_body = _read_text(file_path)
    if file_body is None:
        return yf.returnJson(False, "服务不存在")
    if not _is_owned(file_body):
        return yf.returnJson(False, "越权拦截：非专属服务禁止读取日志！")
    
    since_arg = ""
    clear_time = _read_text(f"{file_path}.clear_time")
    if clear_time:
        clear_time = clear_time.strip()
        # 只接受自己写进去的时间戳格式，避免文件被篡改后拼出额外 journalctl 参数
        if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', clear_time):
            since_arg = f'--since "{clear_time}"'
            
    cmd = f"journalctl -u {service_id} {since_arg} -n 100 --no-pager"
    res = _run_cmd(cmd)
    
    if res["status"]:
        return yf.returnJson(True, "获取成功", res["data"])
    else:
        return yf.returnJson(False, f"获取日志失败: {res['error']}")

def clear_service_logs():
    args = getArgs()
    service_name = _arg_str(args, 'service_name')
    if not _SERVICE_NAME_RE.match(service_name):
        return yf.returnJson(False, "服务名不合法")
        
    file_path = _unit_path(service_name)
    clear_file = f"{file_path}.clear_time"

    # 日志「清空」= 记一个 since 时间点；旧实现对任意名字都白名单直写
    # /etc/systemd/system/<name>.service.clear_time（真机实测：非专属甚至不存在的
    # 服务都回「日志已成功清空」并留下旁路文件）。
    file_body = _read_text(file_path)
    if file_body is None:
        return yf.returnJson(False, "服务不存在")
    if not _is_owned(file_body):
        return yf.returnJson(False, "越权拦截：非专属服务禁止清空日志！")
    
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
