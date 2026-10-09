# coding:utf-8
import sys
import os
import json
import re
import math
import shutil
import time

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import logging

_log = logging.getLogger('yf.pg_docker')

# 实例名会被拼进容器名（pg-<name>）、实例目录名、/etc/cron.d 文件名与 shell 命令。
# 用 \Z 而非 $：$ 也匹配结尾换行之前，会让 "name\n" 这类值混进 shell/配置。
_INSTANCE_RE = re.compile(r'^[A-Za-z0-9_]{1,64}\Z')
# 库名/用户名会被拼进 docker-compose 的 healthcheck（容器内 CMD-SHELL）与 psql 的 SQL
_DB_IDENT_RE = re.compile(r'^[A-Za-z0-9_]{1,63}\Z')
# 口令会被依次交给 YAML 双引号串、`docker compose` 的变量插值、psql 的 SQL 字面量与
# shell 双引号解释：换行/引号/反斜杠/反引号/$ 任一进来都会被改写或注入，故按白名单放行
# （与 redis/valkey 的密码白名单同口径）。
_PASS_RE = re.compile(r"^[A-Za-z0-9_.@#%^&*()+\-={}\[\]:;,<>?/|!~ ]{1,64}\Z")
# 基础目录会被写进 compose 的卷路径（YAML）与 backup.sh，并决定实例目录位置。
# 只放行绝对路径（POSIX `/…` 或 Windows `C:\…`），其余字符（空格/引号/$/;/换行）
# 一律拒绝 —— 它们会破坏 YAML 或逃逸 shell。
_BASE_DIR_RE = re.compile(r'^(?:/|[A-Za-z]:[\\/])[A-Za-z0-9_./\\\-]{0,200}\Z')
# 备份保留份数会被直接写进 backup.sh 的算术表达式 `$((${DAILY_RETENTION} + 1))`
_RETENTION_RE = re.compile(r'^[0-9]{1,4}\Z')
# 纯数字参数（如内存上限 MB）
_DIGITS_RE = re.compile(r'^[0-9]{1,7}\Z')

_DISK_TYPES = ('ssd', 'hdd_single', 'hdd_raid')
_SCENARIOS = ('general', 'high_concurrency', 'high_throughput')
# 禁止把实例数据放在系统关键路径下：实例目录 = base_dir/<实例名>，
# base_dir 取 / 或 /etc 就等于把系统目录交给容器卷读写。
_BASE_DIR_DENY = ('/etc', '/boot', '/proc', '/sys', '/dev', '/bin', '/sbin',
                  '/lib', '/lib64', '/usr', '/var', '/root')

DEFAULT_BASE_DIR = '/docker_data'


def _valid_instance_name(name):
    return isinstance(name, str) and bool(_INSTANCE_RE.match(name))


def _valid_db_ident(name):
    return isinstance(name, str) and bool(_DB_IDENT_RE.match(name))


def _valid_password(pwd):
    return isinstance(pwd, str) and bool(_PASS_RE.match(pwd))


def _valid_port(port):
    """返回 1..65535 的整数端口；非法值返回 None（由调用方如实报错）。"""
    try:
        value = int(str(port).strip())
    except (TypeError, ValueError):
        return None
    if value < 1 or value > 65535:
        return None
    return value


def _path_under(candidate, root):
    """平台无关的「candidate 是否为 root 本身或 root 的子路径」判断。"""
    cand = candidate.replace('\\', '/').rstrip('/')
    base = root.replace('\\', '/').rstrip('/')
    return cand == base or cand.startswith(base + '/')


def _valid_base_dir(base_dir):
    """返回规范化后的基础目录；非法/越界返回 None。"""
    if not isinstance(base_dir, str):
        return None
    base_dir = base_dir.strip()
    if not _BASE_DIR_RE.match(base_dir):
        return None
    # `..` 检查必须与 _path_under 同口径地折算分隔符：只按 '/' 切会让 Windows 形态的
    # `C:\x\..\etc` 漏网（守卫跑在 Windows 开发机上会假绿）。
    if '..' in base_dir.replace('\\', '/').split('/'):
        return None
    # 同时校验「原样绝对路径」与「realpath 之后」：软链可把 /docker_data 指向 /etc，
    # 而 realpath 在不同平台会给出不同分隔符，_path_under 统一折算。
    deny_roots = list(_BASE_DIR_DENY) + [yf.getServerDir(), os.path.realpath(yf.getServerDir())]
    for candidate in (base_dir, os.path.realpath(base_dir)):
        if candidate.replace('\\', '/').strip('/') == '':
            return None          # 文件系统根（/ 或 os.sep）绝不允许
        if re.match(r'^[A-Za-z]:$', candidate.replace('\\', '/').strip('/')):
            return None          # Windows 盘符根（C:）同样不允许
        for root in deny_roots:
            if root and _path_under(candidate, root):
                return None
    return base_dir


def _instance_dir(inst_name, base_dir):
    """把 instances.json 的记录还原成实例目录；非法记录一律返回 None，调用方如实报错。"""
    if not _valid_instance_name(inst_name):
        return None
    base = _valid_base_dir(base_dir)
    if base is None:
        return None
    return os.path.join(base, inst_name)


def get_cron_file(inst_name):
    return '/etc/cron.d/pg_backup_' + inst_name


def _compose(instance_dir, *args, **kwargs):
    """在实例目录里跑 docker compose；argv 形态 + shell=False，用户输入不进 shell。"""
    timeout = kwargs.pop('timeout', 180)
    return yf.execShellRc(['docker', 'compose'] + list(args), cwd=instance_dir,
                          shell=False, timeout=timeout)


def _container_running(inst_name):
    rc, out, err = yf.execShellRc(['docker', 'inspect', '-f', '{{.State.Running}}', 'pg-' + inst_name],
                                  shell=False, timeout=30)
    return rc == 0 and out.strip() == 'true'


def _container_exists(inst_name):
    rc, out, err = yf.execShellRc(['docker', 'inspect', '-f', '{{.Id}}', 'pg-' + inst_name],
                                  shell=False, timeout=30)
    return rc == 0 and out.strip() != ''


def _cleanup_instance(inst_dir, inst_name, remove_data=False):
    """创建/修改失败后的兜底清理：停容器 + 删 cron + 按需删实例目录。"""
    if os.path.isdir(inst_dir):
        _compose(inst_dir, 'down', timeout=120)
    yf.execShellRc(['docker', 'rm', '-f', 'pg-' + inst_name], shell=False, timeout=60)
    cron_file = get_cron_file(inst_name)
    if os.path.exists(cron_file):
        try:
            os.remove(cron_file)
        except Exception as _e:
            _log.debug('[pg_docker] 清理 cron 失败: %s', _e)
    if remove_data and os.path.isdir(inst_dir) and os.path.realpath(inst_dir) != '/':
        shutil.rmtree(inst_dir, ignore_errors=True)


def _compose_up(instance_dir, attempts=15):
    """启动实例并确认容器真的 Running（旧版只看命令返回，容器没起来也报成功）。"""
    rc, out, err = _compose(instance_dir, 'up', '-d', timeout=300)
    if rc != 0:
        return False, ((out + err).strip() or 'docker compose up 退出码 %s' % rc)
    name = os.path.basename(instance_dir)
    for _ in range(attempts):
        time.sleep(2)
        if _container_running(name):
            return True, ''
    return False, '容器未能进入运行状态'


def installPreInspection():
    check_docker = yf.getServerDir() + '/docker'
    if not os.path.exists(check_docker):
        return '请先安装【御风Docker管理器】'
    return 'ok'

def getPluginName():
    return 'pg_docker'

def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()

def get_mem_mb():
    try:
        mem = yf.readFile('/proc/meminfo')
        if mem:
            m = re.search(r'MemTotal:\s+(\d+)\s+kB', mem)
            if m:
                return int(m.group(1)) // 1024
    except Exception as _e:
        _log.debug('[pg_docker] get_mem_mb 异常已忽略: %s', _e)
    return 2048

def load_instances():
    conf_path = getServerDir() + '/instances.json'
    if os.path.exists(conf_path):
        try:
            return json.loads(yf.readFile(conf_path))
        except Exception as _e:
            _log.debug('[pg_docker] load_instances 异常已忽略: %s', _e)
    return {}

def save_instances(data):
    conf_path = getServerDir() + '/instances.json'
    yf.writeFile(conf_path, json.dumps(data))

def get_list():
    instances_data = load_instances()
    instances = []
    
    # 提前获取全局 docker 资源消耗统计
    stats_map = {}
    try:
        rc, stats_out, stats_err = yf.execShellRc(
            ['docker', 'stats', '--no-stream', '--format', '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}'],
            shell=False, timeout=30)
        if stats_out:
            for line in stats_out.strip().split('\n'):
                parts = line.split('|')
                if len(parts) >= 3:
                    cname = parts[0].strip()
                    cpu_raw = parts[1].replace('%','').strip()
                    mem_raw = parts[2].split('/')[0].strip()
                    
                    try:
                        cpu_val = int(round(float(cpu_raw)))
                    except Exception as _e:
                        _log.debug('[pg_docker] get_list 异常已忽略: %s', _e)
                        cpu_val = 0
                        
                    mem_val = 0
                    try:
                        if 'GiB' in mem_raw:
                            mem_val = int(round(float(mem_raw.replace('GiB','')) * 1024))
                        elif 'MiB' in mem_raw or 'MB' in mem_raw:
                            mem_val = int(round(float(mem_raw.replace('MiB','').replace('MB',''))))
                        elif 'kiB' in mem_raw or 'kB' in mem_raw:
                            mem_val = int(round(float(mem_raw.replace('kiB','').replace('kB','')) / 1024))
                        else:
                            mem_val = 0
                    except Exception as _e:
                        _log.debug('[pg_docker] get_list 异常已忽略: %s', _e)
                        
                    stats_map[cname] = {"cpu": cpu_val, "mem": mem_val}
    except Exception as _e:
        _log.debug('[pg_docker] get_list 异常已忽略: %s', _e)
    
    # 兼容处理：扫描默认目录，把之前未记录的也加进来
    base_dir_default = DEFAULT_BASE_DIR
    if os.path.exists(base_dir_default):
        for item in os.listdir(base_dir_default):
            if item not in instances_data and _valid_instance_name(item):
                instances_data[item] = base_dir_default
    
    for inst_name, base_dir in list(instances_data.items()):
        instance_path = _instance_dir(inst_name, base_dir)
        if instance_path is None:
            # 手改 instances.json 或异常目录名：非法记录直接剔除，绝不进 shell
            del instances_data[inst_name]
            continue
        compose_file = os.path.join(instance_path, "docker-compose.yml")
        if os.path.isdir(instance_path) and os.path.exists(compose_file):
            # 读取一些基本信息
            port = "未知"
            dbname = "未知"
            dbuser = "未知"
            dbpass = "未知"
            try:
                content = yf.readFile(compose_file)
                # 仅显示 pg- 开头的容器，排除其他无关的 docker 容器
                if 'container_name: pg-' not in content and 'container_name: "pg-' not in content:
                    del instances_data[inst_name]
                    continue

                is_external = True
                pm = re.search(r'ports:\s*\n\s*-\s*"(?:(127\.0\.0\.1):)?(\d+):5432"', content)
                if pm:
                    if pm.group(1) == '127.0.0.1':
                        is_external = False
                    port = pm.group(2)
                dbm = re.search(r'POSTGRES_DB:\s*"?(.*?)"?\n', content)
                if dbm:
                    dbname = dbm.group(1)
                usm = re.search(r'POSTGRES_USER:\s*"?(.*?)"?\n', content)
                if usm:
                    dbuser = usm.group(1)
                pwm = re.search(r'POSTGRES_PASSWORD:\s*"?(.*?)"?\n', content)
                if pwm:
                    dbpass = pwm.group(1)
            except Exception as _e:
                _log.debug('[pg_docker] get_list 异常已忽略: %s', _e)
            
            # 检查运行状态
            ps_rc, ps_out, ps_err = _compose(instance_path, 'ps', '-q', timeout=30)
            is_running = ps_rc == 0 and ps_out.strip() != ''
            
            cron_file = get_cron_file(inst_name)
            auto_backup_enabled = os.path.exists(cron_file)
            
            c_stats = stats_map.get(f"pg-{inst_name}", {"cpu": 0, "mem": 0})

            instances.append({
                "name": inst_name,
                "path": instance_path,
                "port": port,
                "is_external": is_external,
                "dbname": dbname,
                "dbuser": dbuser,
                "dbpass": dbpass,
                "status": is_running,
                "auto_backup": auto_backup_enabled,
                "cpu": c_stats["cpu"],
                "mem": c_stats["mem"]
            })
        else:
            # 目录或文件不存在，说明已失效，清理掉
            del instances_data[inst_name]
                
    save_instances(instances_data)
    return yf.returnJson(True, "ok", instances)

def get_config(args):
    try:
        data = json.loads(args)
    except Exception as _e:
        _log.debug('[pg_docker] get_config 异常已忽略: %s', _e)
        return yf.returnJson(False, "参数解析失败")
    
    inst_name = str(data.get('instance_name', '')).strip()
    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")

    instance_path = _instance_dir(inst_name, instances_data[inst_name])
    if instance_path is None:
        return yf.returnJson(False, "实例目录不存在")
    compose_file = os.path.join(instance_path, "docker-compose.yml")
    if not os.path.exists(compose_file):
        return yf.returnJson(False, "配置文件不存在")
        
    content = yf.readFile(compose_file)
    return yf.returnJson(True, "ok", content)

def toggle_status(args):
    try:
        data = json.loads(args)
    except Exception as _e:
        _log.debug('[pg_docker] toggle_status 异常已忽略: %s', _e)
        return yf.returnJson(False, "参数解析失败")
    
    inst_name = str(data.get('instance_name', '')).strip()
    action = str(data.get('action', 'start')).strip()  # 'start' or 'stop'

    if action not in ('start', 'stop'):
        return yf.returnJson(False, "不支持的操作: " + action)

    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")

    instance_path = _instance_dir(inst_name, instances_data[inst_name])
    if instance_path is None or not os.path.isdir(instance_path):
        return yf.returnJson(False, "实例目录不存在")

    if action == 'start':
        # 旧版不看命令退出码也不看容器状态，容器不存在/镜像丢了也回「启动成功」
        rc, out, err = _compose(instance_path, 'start', timeout=120)
        if rc != 0:
            return yf.returnJson(False, "实例操作失败: " + ((out + err).strip()[:200] or '退出码 %s' % rc))
        for _ in range(5):
            time.sleep(1)
            if _container_running(inst_name):
                break
        else:
            return yf.returnJson(False, "实例启动后未就绪，请查看运行日志")
        write_log(inst_name, "start", "启动实例容器成功")
        return yf.returnJson(True, "实例已成功启动")
    else:
        rc, out, err = _compose(instance_path, 'stop', timeout=120)
        if rc != 0:
            return yf.returnJson(False, "实例操作失败: " + ((out + err).strip()[:200] or '退出码 %s' % rc))
        write_log(inst_name, "stop", "停止实例容器成功")
        return yf.returnJson(True, "实例已成功停止")

def get_backups(args):
    try:
        data = json.loads(args)
    except Exception as _e:
        _log.debug('[pg_docker] get_backups 异常已忽略: %s', _e)
        return yf.returnJson(False, "参数解析失败")
        
    inst_name = str(data.get('instance_name', '')).strip()
    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")

    instance_path = _instance_dir(inst_name, instances_data[inst_name])
    if instance_path is None:
        return yf.returnJson(False, "实例目录不存在")
    daily_dir = os.path.join(instance_path, "backups", "daily")
    weekly_dir = os.path.join(instance_path, "backups", "weekly")
    manual_dir = os.path.join(instance_path, "backups", "manual")
    remarks_file = os.path.join(instance_path, "backups", "remarks.json")
    
    remarks_data = {}
    if os.path.exists(remarks_file):
        try:
            remarks_data = json.loads(yf.readFile(remarks_file))
        except Exception as _e:
            _log.debug('[pg_docker] get_backups 异常已忽略: %s', _e)
    
    def scan_dir(path, is_manual=False):
        lst = []
        if os.path.exists(path):
            for f in os.listdir(path):
                if f.endswith('.dump'):
                    fp = os.path.join(path, f)
                    stat = os.stat(fp)
                    size_mb = stat.st_size / (1024 * 1024)
                    item = {
                        "name": f,
                        "path": fp,
                        "size": f"{size_mb:.2f} MB",
                        "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                        "timestamp": stat.st_mtime
                    }
                    if is_manual:
                        item["remark"] = remarks_data.get(f, "")
                    lst.append(item)
        lst.sort(key=lambda x: x["timestamp"], reverse=True)
        return lst

    cron_file = get_cron_file(inst_name)
    auto_backup_enabled = os.path.exists(cron_file)
    
    result = {
        "daily": scan_dir(daily_dir),
        "weekly": scan_dir(weekly_dir),
        "manual": scan_dir(manual_dir, True),
        "auto_backup_enabled": auto_backup_enabled
    }
    return yf.returnJson(True, "ok", result)

def toggle_auto_backup(args):
    try:
        data = json.loads(args)
    except Exception as _e:
        _log.debug('[pg_docker] toggle_auto_backup 异常已忽略: %s', _e)
        return yf.returnJson(False, "参数解析失败")
        
    inst_name = str(data.get('instance_name', '')).strip()
    enable = data.get('enable', False)
    # 字符串 'false' 在 Python 里是 truthy：旧版会把「关闭自动备份」当成开启
    if isinstance(enable, str):
        enable = enable.strip().lower() in ('1', 'true', 'yes', 'on')
    else:
        enable = bool(enable)

    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")

    instance_path = _instance_dir(inst_name, instances_data[inst_name])
    if instance_path is None:
        return yf.returnJson(False, "实例目录不存在")
    script_path = os.path.join(instance_path, "scripts", "backup.sh")
    log_path = os.path.join(instance_path, "logs", "backup.log")
    cron_file = get_cron_file(inst_name)

    if enable:
        if not os.path.isfile(script_path):
            return yf.returnJson(False, "备份脚本不存在，无法开启自动备份")
        cron_content = "0 2 * * * root /bin/bash %s >> %s 2>&1\n" % (
            yf.shlexQuote(script_path), yf.shlexQuote(log_path))
        if not yf.writeFile(cron_file, cron_content):
            return yf.returnJson(False, "配置写入失败")
        write_log(inst_name, "cron", "自动备份计划已开启")
        return yf.returnJson(True, "自动备份计划已开启")
    else:
        if os.path.exists(cron_file):
            try:
                os.remove(cron_file)
            except Exception as e:
                return yf.returnJson(False, "文件不存在或参数错误")
        write_log(inst_name, "cron", "自动备份计划已关闭")
        return yf.returnJson(True, "自动备份计划已关闭")

def create_backup(args):
    try:
        data = json.loads(args)
    except Exception as _e:
        _log.debug('[pg_docker] create_backup 异常已忽略: %s', _e)
        return yf.returnJson(False, "参数解析失败")
        
    inst_name = str(data.get('instance_name', '')).strip()
    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")

    instance_path = _instance_dir(inst_name, instances_data[inst_name])
    if instance_path is None:
        return yf.returnJson(False, "实例目录不存在")
    script_path = os.path.join(instance_path, "scripts", "backup.sh")

    if not os.path.exists(script_path):
        return yf.returnJson(False, "备份脚本不存在，可能实例已损坏")

    # 容器未运行时 backup.sh 会「跳过备份并 exit 0」——旧版据此报「备份成功！」
    if not _container_running(inst_name):
        return yf.returnJson(False, "实例未运行，无法备份。请先启动实例。")

    rc, out, err = yf.execShellRc(['/bin/bash', script_path, 'manual'], shell=False, timeout=900)
    output = (out, err)
    full_output = (out + "\n" + err).strip()
    write_log(inst_name, "manual_backup", full_output)

    if rc != 0 or "备份失败" in out or "备份失败" in err:
        if not full_output:
            return yf.returnJson(False, "备份失败")
        return yf.returnJson(False, f"备份失败！输出: {output[0][:100]} {output[1][:100]}")

    return yf.returnJson(True, "一键备份成功！")

def restore_backup(args):
    try:
        data = json.loads(args)
    except Exception as _e:
        _log.debug('[pg_docker] restore_backup 异常已忽略: %s', _e)
        return yf.returnJson(False, "参数解析失败")
        
    inst_name = str(data.get('instance_name', '')).strip()
    file_path = str(data.get('file_path', '')).strip()

    if not file_path or not os.path.exists(file_path):
        return yf.returnJson(False, "备份文件不存在或参数错误")
        
    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")

    instance_path = _instance_dir(inst_name, instances_data[inst_name])
    if instance_path is None:
        return yf.returnJson(False, "实例目录不存在")
    # 只能还原本实例 backups/ 下的备份：旧版把入参原样拼进 shell，
    # 真机实测 `yf;touch pwn;echo .dump` 以面板身份（root）建出了文件。
    backup_dir = os.path.realpath(os.path.join(instance_path, "backups"))
    real_file = os.path.realpath(file_path)
    if not (real_file == backup_dir or real_file.startswith(backup_dir + os.sep)):
        return yf.returnJson(False, "非法的路径")
    if not os.path.isfile(real_file):
        return yf.returnJson(False, "备份文件不存在")

    script_path = os.path.join(instance_path, "scripts", "restore.sh")
    
    if not os.path.exists(script_path):
        return yf.returnJson(False, "恢复脚本不存在，可能实例已损坏")
        
    # 热修复老实例的 restore.sh，使其通过管道读取文件，避免容器内外路径不一致
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
        target_cmd = 'pg_restore -U ${DB_USER} -d ${DB_NAME} "$RESTORE_FILE"'
        if target_cmd in script_content:
            script_content = script_content.replace(target_cmd, 'pg_restore -U ${DB_USER} -d ${DB_NAME} < "$RESTORE_FILE"')
            with open(script_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(script_content)
    except Exception as _e:
        _log.debug('[pg_docker] restore_backup 异常已忽略: %s', _e)
        
    # argv 形态执行：路径不会进 shell（旧版字符串拼接 = root 命令注入）
    rc, out, err = yf.execShellRc(['/bin/bash', script_path, real_file], shell=False, timeout=1800)
    output = (out, err)
    full_output = (out + "\n" + err).strip()
    write_log(inst_name, "restore", full_output)

    if rc == 0 and "数据还原完成" in (out + err):
        return yf.returnJson(True, "数据已成功还原！")
    return yf.returnJson(False, f"还原可能失败，请检查日志！输出: {output[0][:200]}")

def delete_backup(args):
    try:
        data = json.loads(args)
    except Exception as _e:
        _log.debug('[pg_docker] delete_backup 异常已忽略: %s', _e)
        return yf.returnJson(False, "参数解析失败")
        
    inst_name = str(data.get('instance_name', '')).strip()
    file_path = str(data.get('file_path', '')).strip()
    
    if not file_path:
        return yf.returnJson(False, "文件不存在或参数错误")

    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")

    instance_path = _instance_dir(inst_name, instances_data[inst_name])
    if instance_path is None:
        return yf.returnJson(False, "实例目录不存在")

    # 限定在本实例 backups/ 目录内（realpath 比对）且必须是 .dump 文件：
    # 旧版只用 "/backups/" 子串判断，任意路径都能被删，而后面又引用未定义的
    # instances_data 抛 NameError——文件已被删掉、返回值却是「删除失败」。
    backup_dir = os.path.realpath(os.path.join(instance_path, "backups"))
    real_file = os.path.realpath(file_path)
    if not real_file.startswith(backup_dir + os.sep):
        return yf.returnJson(False, "非法的路径")
    if not real_file.endswith('.dump'):
        return yf.returnJson(False, "非法的路径")
    if not os.path.isfile(real_file):
        return yf.returnJson(False, "备份文件不存在")

    try:
        os.remove(real_file)
        # 删除成功后，顺便清理 remarks.json 中的记录
        remarks_file = os.path.join(instance_path, "backups", "remarks.json")
        if os.path.exists(remarks_file):
            try:
                remarks_data = json.loads(yf.readFile(remarks_file))
                filename = os.path.basename(real_file)
                if filename in remarks_data:
                    del remarks_data[filename]
                    yf.writeFile(remarks_file, json.dumps(remarks_data))
            except Exception as _e:
                _log.debug('[pg_docker] delete_backup 异常已忽略: %s', _e)
                
        write_log(inst_name, "delete_backup", f"删除了备份文件: {real_file}")
        return yf.returnJson(True, "备份删除成功！")
    except Exception as e:
        return yf.returnJson(False, f"删除失败: {str(e)}")

def save_backup_remark(args):
    try:
        data = json.loads(args)
    except Exception as _e:
        _log.debug('[pg_docker] save_backup_remark 异常已忽略: %s', _e)
        return yf.returnJson(False, "参数解析失败")
        
    inst_name = str(data.get('instance_name', '')).strip()
    filename = str(data.get('filename', '')).strip()
    remark = str(data.get('remark', '')).strip()
    
    if not filename:
        return yf.returnJson(False, "文件名不能为空")
    if not re.match(r'^[A-Za-z0-9_.\-]{1,128}\Z', filename):
        return yf.returnJson(False, "文件名不合法")
    # 备注会被前端渲染进 value="..."（存储型 XSS 的上游），长度收敛到 200 字
    if len(remark) > 200:
        return yf.returnJson(False, "备注长度不能超过 200 字")
        
    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")

    instance_path = _instance_dir(inst_name, instances_data[inst_name])
    if instance_path is None:
        return yf.returnJson(False, "实例目录不存在")
    remarks_file = os.path.join(instance_path, "backups", "remarks.json")
    
    remarks_data = {}
    if os.path.exists(remarks_file):
        try:
            remarks_data = json.loads(yf.readFile(remarks_file))
        except Exception as _e:
            _log.debug('[pg_docker] save_backup_remark 异常已忽略: %s', _e)
            
    remarks_data[filename] = remark
    if not yf.writeFile(remarks_file, json.dumps(remarks_data)):
        return yf.returnJson(False, "配置写入失败")
    
    return yf.returnJson(True, "备注保存成功")

def toggle_external_port(args):
    try:
        data = json.loads(args)
    except Exception as _e:
        _log.debug('[pg_docker] toggle_external_port 异常已忽略: %s', _e)
        return yf.returnJson(False, "参数解析失败")
        
    inst_name = str(data.get('instance_name', '')).strip()
    is_ext = data.get('is_external', False)
    
    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")

    instance_path = _instance_dir(inst_name, instances_data[inst_name])
    if instance_path is None:
        return yf.returnJson(False, "实例目录不存在")
    compose_file = os.path.join(instance_path, "docker-compose.yml")
    if not os.path.exists(compose_file):
        return yf.returnJson(False, "配置文件不存在")
        
    content = yf.readFile(compose_file)
    
    pm = re.search(r'ports:\s*\n\s*-\s*"(?:127\.0\.0\.1:)?(\d+):5432"', content)
    if not pm:
        return yf.returnJson(False, "无法解析端口配置")
        
    port = pm.group(1)
    old_ports = pm.group(0)
    
    if is_ext:
        new_ports = f'ports:\n      - "{port}:5432"'
    else:
        new_ports = f'ports:\n      - "127.0.0.1:{port}:5432"'
        
    new_content = content.replace(old_ports, new_ports)
    if not yf.writeFile(compose_file, new_content):
        return yf.returnJson(False, "配置写入失败")

    # 旧版不看命令退出码，容器没起来也报「已重启生效」
    down_rc, down_out, down_err = _compose(instance_path, 'down', timeout=120)
    if down_rc != 0:
        return yf.returnJson(False, "实例操作失败: " + ((down_out + down_err).strip()[:200] or '退出码 %s' % down_rc))
    ok, reason = _compose_up(instance_path)
    if not ok:
        yf.writeFile(compose_file, content)
        return yf.returnJson(False, "配置修改后容器未能就绪，原配置已回滚")

    return yf.returnJson(True, "配置已更新，容器已重启生效")

def modify_config(args):
    try:
        data = json.loads(args)
    except Exception as _e:
        _log.debug('[pg_docker] modify_config 异常已忽略: %s', _e)
        return yf.returnJson(False, "参数解析失败")
        
    inst_name = str(data.get('instance_name', '')).strip()
    db_user = str(data.get('db_user', '')).strip()
    new_pass = str(data.get('new_pass', '')).strip()
    new_port = str(data.get('new_port', '')).strip()
    
    if not inst_name or not new_port:
        return yf.returnJson(False, "参数不完整")

    port_value = _valid_port(new_port)
    if port_value is None:
        return yf.returnJson(False, "宿主机端口不合法")
    if db_user and not _valid_db_ident(db_user):
        return yf.returnJson(False, "数据库用户名不合法")
    if new_pass and not _valid_password(new_pass):
        return yf.returnJson(False, "数据库密码不合法")
        
    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")

    instance_path = _instance_dir(inst_name, instances_data[inst_name])
    if instance_path is None:
        return yf.returnJson(False, "实例目录不存在")
    compose_file = os.path.join(instance_path, "docker-compose.yml")
    if not os.path.exists(compose_file):
        return yf.returnJson(False, "配置文件不存在")
        
    content = yf.readFile(compose_file)
    original_content = content
    
    # 1. 尝试修改密码（如果提供）
    if new_pass:
        # 修改 docker-compose 中的环境变量
        old_pass_match = re.search(r'POSTGRES_PASSWORD:\s*"?(.*?)"?\n', content)
        if old_pass_match:
            old_pass_line = old_pass_match.group(0)
            new_pass_line = f'POSTGRES_PASSWORD: "{new_pass}"\n'
            content = content.replace(old_pass_line, new_pass_line)
        
        # 在容器内执行修改（需保证容器运行中）
        if not _container_running(inst_name):
            return yf.returnJson(False, "实例未运行，无法修改密码。请先启动实例。")
        # argv 形态 + 参数白名单：用户名/口令都不会被 shell 解释
        sql = "ALTER USER %s WITH PASSWORD '%s';" % (db_user, new_pass)
        rc, out, err = yf.execShellRc(['docker', 'exec', 'pg-' + inst_name, 'psql', '-U', db_user,
                                       '-d', 'postgres', '-c', sql], shell=False, timeout=60)
        if rc != 0:
            return yf.returnJson(False, "修改密码失败: " + ((out + err).strip()[:200] or '退出码 %s' % rc))

    # 2. 修改端口
    pm = re.search(r'ports:\s*\n\s*-\s*"(?:127\.0\.0\.1:)?(\d+):5432"', content)
    if pm:
        old_ports = pm.group(0)
        old_port = pm.group(1)
        
        # 检查新端口是否被占用 (如果端口变了)
        if str(new_port) != str(old_port) and yf.isOpenPort(port_value):
            return yf.returnJson(False, f"修改失败：宿主机端口 {new_port} 已被占用，请更换其他端口！")
                
        is_ext = '127.0.0.1' not in old_ports
        if is_ext:
            new_ports = f'ports:\n      - "{new_port}:5432"'
        else:
            new_ports = f'ports:\n      - "127.0.0.1:{new_port}:5432"'
        content = content.replace(old_ports, new_ports)
    else:
        return yf.returnJson(False, "无法解析原端口配置")
        
    if not yf.writeFile(compose_file, content):
        return yf.returnJson(False, "配置写入失败")
    
    # 3. 重启容器（失败就把配置回滚并再次拉起原配置）
    down_rc, down_out, down_err = _compose(instance_path, 'down', timeout=120)
    ok, reason = _compose_up(instance_path)
    if down_rc != 0 or not ok:
        yf.writeFile(compose_file, original_content)
        _compose_up(instance_path)
        return yf.returnJson(False, "配置修改后容器未能就绪，原配置已回滚")
    
    write_log(inst_name, "modify", "已成功修改配置并重启容器")
    return yf.returnJson(True, "配置修改成功，容器已重启")

def create_instance(args):
    try:
        data = json.loads(args)
    except Exception as _e:
        _log.debug('[pg_docker] create_instance 异常已忽略: %s', _e)
        return yf.returnJson(False, "参数解析失败")

    inst_name = str(data.get('instance_name', '')).strip()
    if not _valid_instance_name(inst_name):
        return yf.returnJson(False, "实例名称不能为空且只能包含字母、数字和下划线")

    base_dir = str(data.get('base_dir', DEFAULT_BASE_DIR)).strip() or DEFAULT_BASE_DIR
    base_dir = _valid_base_dir(base_dir)
    if base_dir is None:
        return yf.returnJson(False, "基础存放目录不合法")

    inst_dir = os.path.join(base_dir, inst_name)
    if os.path.exists(inst_dir):
        return yf.returnJson(False, f"实例目录 {inst_dir} 已存在，请使用其他名称")

    db_user = str(data.get('db_user', '')).strip()
    db_pass = str(data.get('db_pass', '')).strip()
    db_name = str(data.get('db_name', '')).strip()
    if not _valid_db_ident(db_user):
        return yf.returnJson(False, "数据库用户名不合法")
    if not _valid_db_ident(db_name):
        return yf.returnJson(False, "数据库名不合法")
    if not _valid_password(db_pass):
        return yf.returnJson(False, "数据库密码不合法")

    # 旧版直接 int(port)：'abc' 抛 ValueError、'99999' 抛 OverflowError（HTTP 变 500），
    # 而 int() 通过的越界端口会写进 compose 让容器永远起不来。
    port = _valid_port(data.get('port', ''))
    if port is None:
        return yf.returnJson(False, "宿主机端口不合法")
    if yf.isOpenPort(port):
        return yf.returnJson(False, f"部署失败：宿主机端口 {port} 已被占用，请更换其他端口！")

    disk_type = str(data.get('disk_type', 'ssd')).strip() or 'ssd'   # ssd, hdd_single, hdd_raid
    scenario = str(data.get('scenario', 'general')).strip() or 'general'  # general, high_concurrency, high_throughput
    if disk_type not in _DISK_TYPES or scenario not in _SCENARIOS:
        return yf.returnJson(False, "参数不合法")

    mem_limit = str(data.get('mem_limit', '') or '').strip()
    if mem_limit and not _DIGITS_RE.match(mem_limit):
        return yf.returnJson(False, "参数不合法")
    # 保留份数会被原样写进 backup.sh 的算术表达式：非数字即 root 命令注入
    daily_retention = str(data.get('daily_retention', 7)).strip()
    weekly_retention = str(data.get('weekly_retention', 30)).strip()
    if not _RETENTION_RE.match(daily_retention) or not _RETENTION_RE.match(weekly_retention):
        return yf.returnJson(False, "参数不合法")

    sys_mem = get_mem_mb()
    try:
        user_mem = int(mem_limit) if mem_limit else int(sys_mem * 0.75)
        if user_mem > sys_mem * 0.75:
            user_mem = int(sys_mem * 0.75)
    except Exception as _e:
        _log.debug('[pg_docker] create_instance 异常已忽略: %s', _e)
        user_mem = int(sys_mem * 0.75)

    if user_mem < 256:
        user_mem = 256

    # 计算内存参数
    shared_buffers_mb = int(user_mem * 0.25)
    effective_cache_size_mb = int(user_mem * 0.75)
    
    # 根据场景计算 work_mem
    work_mem_mb = 8
    maintenance_work_mem_mb = 128
    if scenario == 'high_concurrency':
        work_mem_mb = 16
        maintenance_work_mem_mb = 256
    elif scenario == 'high_throughput':
        work_mem_mb = 8
        maintenance_work_mem_mb = 256

    # 目录创建不再走 shell（用户输入的 base_dir 曾在此处被 $(...) 注入）
    for sub in ('conf', 'data', 'backups/daily', 'backups/weekly',
                'backups/manual', 'scripts', 'logs'):
        os.makedirs(os.path.join(inst_dir, sub), exist_ok=True)

    # 容器内 postgres 以 uid 999 运行，数据目录需可写；chown/chmod 走 argv 形态
    yf.execShellRc(['chown', '-R', '999:999', inst_dir], shell=False, timeout=120)
    yf.execShellRc(['chmod', '-R', '755', inst_dir], shell=False, timeout=120)

    # 2. 生成 postgresql.conf
    pg_conf = []
    pg_conf.append(f"listen_addresses = '*'")
    
    # --- 通用基础配置 (WAL与安全) ---
    pg_conf.append("wal_level = replica")
    pg_conf.append("synchronous_commit = on")
    pg_conf.append("checkpoint_timeout = 15min")
    pg_conf.append("checkpoint_completion_target = 0.9")
    pg_conf.append("max_wal_size = 4GB")
    pg_conf.append("min_wal_size = 512MB")
    pg_conf.append("wal_compression = lz4")
    pg_conf.append("log_min_duration_statement = 500")
    
    # --- 场景差异配置 (在后方追加以覆盖上述默认值) ---
    if scenario == 'high_concurrency':
        pg_conf.append("max_connections = 100")
        pg_conf.append("max_worker_processes = 4")
        pg_conf.append("max_parallel_workers_per_gather = 2")
        pg_conf.append("max_parallel_workers = 4")
        pg_conf.append("default_statistics_target = 200")
        pg_conf.append("log_min_duration_statement = 1000") # 覆盖
    elif scenario == 'high_throughput':
        pg_conf.append("max_connections = 200")
        pg_conf.append("synchronous_commit = off")          # 覆盖
        pg_conf.append("wal_writer_delay = 200ms")
        pg_conf.append("checkpoint_timeout = 30min")        # 覆盖
        pg_conf.append("max_wal_size = 8GB")                # 覆盖
        pg_conf.append("min_wal_size = 1GB")                # 覆盖
    else:
        # general
        pg_conf.append("max_connections = 150")

    pg_conf.append(f"shared_buffers = {shared_buffers_mb}MB")
    pg_conf.append(f"work_mem = {work_mem_mb}MB")
    pg_conf.append(f"maintenance_work_mem = {maintenance_work_mem_mb}MB")
    pg_conf.append(f"effective_cache_size = {effective_cache_size_mb}MB")

    if disk_type == 'ssd':
        pg_conf.append("random_page_cost = 1.1")
        pg_conf.append("effective_io_concurrency = 200")
    elif disk_type == 'hdd_single':
        pg_conf.append("random_page_cost = 4.0")
        pg_conf.append("effective_io_concurrency = 1")
    else:
        pg_conf.append("random_page_cost = 4.0")
        pg_conf.append("effective_io_concurrency = 2")

    pg_conf.append("logging_collector = on")
    pg_conf.append("log_directory = '/var/log/postgresql'")
    pg_conf.append("log_filename = 'postgresql-%Y-%m-%d.log'")
    pg_conf.append("log_line_prefix = '%m [%p] %u@%d '")
    pg_conf.append("log_timezone = 'Asia/Shanghai'")
    pg_conf.append("timezone = 'Asia/Shanghai'")

    if scenario != 'high_throughput':
        pg_conf.append("autovacuum = on")
        pg_conf.append("autovacuum_vacuum_scale_factor = 0.1")
        pg_conf.append("autovacuum_analyze_scale_factor = 0.05")
        pg_conf.append("autovacuum_vacuum_cost_delay = 2ms")

    yf.writeFile(f"{inst_dir}/conf/postgresql.conf", "\n".join(pg_conf))

    # 3. 生成 docker-compose.yml
    docker_compose = f"""services:
  postgres:
    image: postgres:18.4-bookworm
    container_name: pg-{inst_name}
    restart: always
    ports:
      - "{port}:5432"
    environment:
      POSTGRES_DB: "{db_name}"
      POSTGRES_USER: "{db_user}"
      POSTGRES_PASSWORD: "{db_pass}"
      PGDATA: /var/lib/postgresql/data/pgdata
      TZ: Asia/Shanghai
    shm_size: {user_mem}m
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U {db_user} -d {db_name}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    volumes:
      - {inst_dir}/data:/var/lib/postgresql/data
      - {inst_dir}/conf/postgresql.conf:/etc/postgresql/postgresql.conf:ro
      - {inst_dir}/logs:/var/log/postgresql
      - {inst_dir}/backups:/backups
      - /etc/localtime:/etc/localtime:ro
    command: ["postgres", "-c", "config_file=/etc/postgresql/postgresql.conf"]
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "5"
"""
    yf.writeFile(f"{inst_dir}/docker-compose.yml", docker_compose)

    # 4. 生成备份脚本
    backup_sh = f"""#!/bin/bash
set -eo pipefail

CONTAINER_NAME="pg-{inst_name}"
DB_USER="{db_user}"
DB_NAME="{db_name}"
BACKUP_DIR="{inst_dir}/backups"
DAILY_RETENTION={daily_retention}
WEEKLY_RETENTION={weekly_retention}
BACKUP_TYPE=${{1:-auto}}

DATE=$(date +%Y%m%d_%H%M%S)
DAILY_DIR="${{BACKUP_DIR}}/daily"
WEEKLY_DIR="${{BACKUP_DIR}}/weekly"
MANUAL_DIR="${{BACKUP_DIR}}/manual"
FILENAME="${{DB_NAME}}_${{DATE}}.dump"

if [ "$BACKUP_TYPE" == "manual" ]; then
    BACKUP_PATH="${{MANUAL_DIR}}/${{FILENAME}}"
    mkdir -p "$MANUAL_DIR"
else
    BACKUP_PATH="${{DAILY_DIR}}/${{FILENAME}}"
    mkdir -p "$DAILY_DIR" "$WEEKLY_DIR"
fi

if [ "$(docker inspect -f '{{{{.State.Running}}}}' ${{CONTAINER_NAME}} 2>/dev/null)" != "true" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 容器未运行，跳过备份."
    exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始数据库备份: ${{DB_NAME}} (${{BACKUP_TYPE}})..."

docker exec -i ${{CONTAINER_NAME}} pg_dump -U ${{DB_USER}} -d ${{DB_NAME}} -Fc > "${{BACKUP_PATH}}"

if [ -s "${{BACKUP_PATH}}" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 备份成功: ${{BACKUP_PATH}} (大小: $(du -sh ${{BACKUP_PATH}} | awk '{{print $1}}'))"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 备份失败，生成的备份文件为空!"
    rm -f "${{BACKUP_PATH}}"
    exit 1
fi

if [ "$BACKUP_TYPE" == "manual" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 手动备份完成，跳过自动清理."
    exit 0
fi

if [ $(date +%u) -eq 7 ]; then
    cp "${{BACKUP_PATH}}" "${{WEEKLY_DIR}}/${{FILENAME}}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 已同步保存至每周备份目录."
fi

ls -t "${{DAILY_DIR}}"/*.dump 2>/dev/null | tail -n +$((${{DAILY_RETENTION}} + 1)) | xargs -r rm -f
ls -t "${{WEEKLY_DIR}}"/*.dump 2>/dev/null | tail -n +$((${{WEEKLY_RETENTION}} + 1)) | xargs -r rm -f
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 历史备份清理完毕."
"""
    with open(f"{inst_dir}/scripts/backup.sh", 'w', encoding='utf-8', newline='\n') as f:
        f.write(backup_sh)
    yf.execShellRc(['chmod', '+x', inst_dir + '/scripts/backup.sh'], shell=False, timeout=30)

    # 5. 生成恢复脚本
    restore_sh = f"""#!/bin/bash
set -eo pipefail

CONTAINER_NAME="pg-{inst_name}"
DB_USER="{db_user}"
DB_NAME="{db_name}"
RESTORE_FILE=$1

if [ -z "$RESTORE_FILE" ]; then
    echo "错误: 请指定要恢复的备份文件路径!"
    exit 1
fi

echo "⚠️ 警告：即将在 5 秒后清空 ${{DB_NAME}} 并执行还原！"
sleep 5

docker exec -i ${{CONTAINER_NAME}} psql -U ${{DB_USER}} -d ${{DB_NAME}} -c "
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${{DB_NAME}}' AND pid <> pg_backend_pid();
DROP SCHEMA public CASCADE;
CREATE SCHEMA public AUTHORIZATION ${{DB_USER}};
"
docker exec -i ${{CONTAINER_NAME}} pg_restore -U ${{DB_USER}} -d ${{DB_NAME}} < "$RESTORE_FILE"
echo "✅ 数据还原完成！"
"""
    with open(f"{inst_dir}/scripts/restore.sh", 'w', encoding='utf-8', newline='\n') as f:
        f.write(restore_sh)
    yf.execShellRc(['chmod', '+x', inst_dir + '/scripts/restore.sh'], shell=False, timeout=30)

    # 6. 设置独立计划任务
    cron_content = "0 2 * * * root /bin/bash %s >> %s 2>&1\n" % (
        yf.shlexQuote(inst_dir + '/scripts/backup.sh'), yf.shlexQuote(inst_dir + '/logs/backup.log'))
    if not yf.writeFile(get_cron_file(inst_name), cron_content):
        return yf.returnJson(False, "配置写入失败")

    # 7. 启动容器（旧版不看退出码：镜像缺失/端口冲突也回「部署成功」）
    ok, reason = _compose_up(inst_dir)
    if not ok:
        _cleanup_instance(inst_dir, inst_name, remove_data=True)
        return yf.returnJson(False, "创建实例失败: " + reason[:200])

    # 8. 保存记录
    instances_data = load_instances()
    instances_data[inst_name] = base_dir
    save_instances(instances_data)
    
    write_log(inst_name, "create", "实例部署成功！容器已启动。")

    return yf.returnJson(True, "实例部署成功！容器正在启动中...")

def uninstall_instance(args):
    try:
        data = json.loads(args)
    except Exception as _e:
        _log.debug('[pg_docker] uninstall_instance 异常已忽略: %s', _e)
        return yf.returnJson(False, "参数解析失败")
    
    inst_name = str(data.get('instance_name', '')).strip()
    keep_data = data.get('keep_data', True)
    if isinstance(keep_data, str):
        keep_data = keep_data.strip().lower() in ('1', 'true', 'yes', 'on')
    else:
        keep_data = bool(keep_data)
    base_dir = str(data.get('base_dir', DEFAULT_BASE_DIR)).strip() or DEFAULT_BASE_DIR

    if not _valid_instance_name(inst_name):
        return yf.returnJson(False, "实例名称不能为空且只能包含字母、数字和下划线")
    base_dir = _valid_base_dir(base_dir)
    if base_dir is None:
        return yf.returnJson(False, "基础存放目录不合法")

    inst_dir = os.path.join(base_dir, inst_name)
    instances_data = load_instances()
    recorded = inst_name in instances_data
    dir_exists = os.path.isdir(inst_dir)
    if not dir_exists and not recorded and not _container_exists(inst_name):
        # 旧版对不存在的实例也回「实例已成功卸载！」
        return yf.returnJson(False, "找不到该实例")

    # 1. 停止容器
    if dir_exists:
        rc, out, err = _compose(inst_dir, 'down', timeout=120)
        if rc != 0:
            return yf.returnJson(False, "实例操作失败: " + ((out + err).strip()[:200] or '退出码 %s' % rc))
    yf.execShellRc(['docker', 'rm', '-f', 'pg-' + inst_name], shell=False, timeout=60)

    # 2. 清理计划任务
    cron_file = get_cron_file(inst_name)
    if os.path.exists(cron_file):
        try:
            os.remove(cron_file)
        except Exception as e:
            return yf.returnJson(False, f"删除失败: {str(e)}")

    # 3. 清理数据（可选）：只删 base_dir/<实例名> 本身（shutil 取代 rm -rf，去 shell 注入）
    if not keep_data and dir_exists:
        real_dir = os.path.realpath(inst_dir)
        if real_dir == '/' or real_dir != os.path.join(os.path.realpath(base_dir), inst_name):
            return yf.returnJson(False, "基础存放目录不合法")
        shutil.rmtree(real_dir, ignore_errors=True)

    # 4. 移除记录
    instances_data = load_instances()
    if inst_name in instances_data:
        del instances_data[inst_name]
        save_instances(instances_data)
        
    write_log(inst_name, "uninstall", f"实例已被卸载。保留数据: {keep_data}")

    return yf.returnJson(True, "实例已成功卸载！")

def write_log(inst_name, action, msg):
    log_file = os.path.join(getServerDir(), 'plugin.log')
    time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{time_str}] [{inst_name}] [{action}] {msg}\n")
    except Exception as _e:
        _log.debug('[pg_docker] write_log 异常已忽略: %s', _e)

def get_logs(args):
    log_file = os.path.join(getServerDir(), 'plugin.log')
    if not os.path.exists(log_file):
        return yf.returnJson(True, "ok", "")
    
    seven_days_ago = time.time() - 7 * 24 * 3600
    new_lines = []
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for line in lines:
            m = re.match(r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', line)
            if m:
                try:
                    log_time = time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
                    if log_time > seven_days_ago:
                        new_lines.append(line)
                except Exception as _e:
                    _log.debug('[pg_docker] get_logs 异常已忽略: %s', _e)
                    new_lines.append(line)
            else:
                new_lines.append(line)
                
        if len(new_lines) < len(lines):
            with open(log_file, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
    except Exception as _e:
        _log.debug('[pg_docker] get_logs 异常已忽略: %s', _e)
        
    return yf.returnJson(True, "ok", "".join(new_lines))

def clear_logs(args):
    log_file = os.path.join(getServerDir(), 'plugin.log')
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("")
        return yf.returnJson(True, "日志已清空")
    except Exception as e:
        return yf.returnJson(False, f"清空日志失败: {str(e)}")

def check_pg_image(args):
    cmd = "docker images -q postgres:18.4-bookworm"
    res = yf.execShell(cmd)
    if res[0].strip():
        return yf.returnJson(True, "ok")
    return yf.returnJson(False, "not found")

def getTotalStatistics():
    if not os.path.exists(getServerDir()):
        return yf.returnJson(False, "not installed")

    instances_data = load_instances()
    base_dir_default = DEFAULT_BASE_DIR
    if os.path.exists(base_dir_default):
        try:
            for item in os.listdir(base_dir_default):
                if item not in instances_data and _valid_instance_name(item):
                    instances_data[item] = base_dir_default
        except Exception as _e:
            _log.debug('[pg_docker] getTotalStatistics 异常已忽略: %s', _e)

    count = 0
    for inst_name, base_dir in list(instances_data.items()):
        instance_path = _instance_dir(inst_name, base_dir)
        if instance_path is None:
            continue
        compose_file = os.path.join(instance_path, "docker-compose.yml")
        if os.path.isdir(instance_path) and os.path.exists(compose_file):
            try:
                content = yf.readFile(compose_file)
                if 'container_name: pg-' in content or 'container_name: "pg-' in content:
                    count += 1
            except Exception as _e:
                _log.debug('[pg_docker] getTotalStatistics 异常已忽略: %s', _e)

    version = "1.0"
    vfile = getServerDir() + '/version.pl'
    if os.path.exists(vfile):
        try:
            version = yf.readFile(vfile).strip()
        except Exception as _e:
            _log.debug('[pg_docker] getTotalStatistics 异常已忽略: %s', _e)
    else:
        try:
            info_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'info.json')
            if os.path.exists(info_path):
                idata = json.loads(yf.readFile(info_path))
                version = idata.get('versions', '1.0')
        except Exception as _e:
            _log.debug('[pg_docker] getTotalStatistics 异常已忽略: %s', _e)

    data = {
        "status": True,
        "count": count,
        "ver": version
    }
    return yf.returnJson(True, "ok", data)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("error")
        sys.exit(1)
        
    func = sys.argv[1]
    args = sys.argv[2] if len(sys.argv) > 2 else "{}"
    
    if func == 'get_list':
        print(get_list())
    elif func == 'create_instance':
        print(create_instance(args))
    elif func == 'uninstall_instance':
        print(uninstall_instance(args))
    elif func == 'install_pre_inspection':
        print(installPreInspection())
    elif func == 'get_config':
        print(get_config(args))
    elif func == 'toggle_status':
        print(toggle_status(args))
    elif func == 'get_backups':
        print(get_backups(args))
    elif func == 'toggle_auto_backup':
        print(toggle_auto_backup(args))
    elif func == 'create_backup':
        print(create_backup(args))
    elif func == 'delete_backup':
        print(delete_backup(args))
    elif func == 'restore_backup':
        print(restore_backup(args))
    elif func == 'toggle_external_port':
        print(toggle_external_port(args))
    elif func == 'get_logs':
        print(get_logs(args))
    elif func == 'clear_logs':
        print(clear_logs(args))
    elif func == 'save_backup_remark':
        print(save_backup_remark(args))
    elif func == 'check_pg_image':
        print(check_pg_image(args))
    elif func == 'modify_config':
        print(modify_config(args))
    elif func == 'get_total_statistics':
        print(getTotalStatistics())
    else:
        print('error')
