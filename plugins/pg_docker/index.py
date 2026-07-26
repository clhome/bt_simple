# coding:utf-8
import sys
import os
import json
import re
import math
import time

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

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
    except:
        pass
    return 2048

def load_instances():
    conf_path = getServerDir() + '/instances.json'
    if os.path.exists(conf_path):
        try:
            return json.loads(yf.readFile(conf_path))
        except:
            pass
    return {}

def save_instances(data):
    conf_path = getServerDir() + '/instances.json'
    yf.writeFile(conf_path, json.dumps(data))

def get_list():
    instances_data = load_instances()
    instances = []
    
    # 兼容处理：扫描默认目录，把之前未记录的也加进来
    base_dir_default = "/docker_data"
    if os.path.exists(base_dir_default):
        for item in os.listdir(base_dir_default):
            if item not in instances_data:
                instances_data[item] = base_dir_default
    
    for inst_name, base_dir in list(instances_data.items()):
        instance_path = os.path.join(base_dir, inst_name)
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
            except:
                pass
            
            # 检查运行状态
            status_cmd = f"cd {instance_path} && docker compose ps -q"
            res = yf.execShell(status_cmd)
            is_running = False
            if res[0].strip() != '':
                is_running = True
            
            instances.append({
                "name": inst_name,
                "path": instance_path,
                "port": port,
                "is_external": is_external,
                "dbname": dbname,
                "dbuser": dbuser,
                "dbpass": dbpass,
                "status": is_running
            })
        else:
            # 目录或文件不存在，说明已失效，清理掉
            del instances_data[inst_name]
                
    save_instances(instances_data)
    return yf.returnJson(True, "ok", instances)

def get_config(args):
    try:
        data = json.loads(args)
    except:
        return yf.returnJson(False, "参数解析失败")
    
    inst_name = data.get('instance_name', '').strip()
    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")
    
    compose_file = os.path.join(instances_data[inst_name], inst_name, "docker-compose.yml")
    if not os.path.exists(compose_file):
        return yf.returnJson(False, "配置文件不存在")
        
    content = yf.readFile(compose_file)
    return yf.returnJson(True, "ok", content)

def toggle_status(args):
    try:
        data = json.loads(args)
    except:
        return yf.returnJson(False, "参数解析失败")
    
    inst_name = data.get('instance_name', '').strip()
    action = data.get('action', 'start') # 'start' or 'stop'
    
    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")
    
    instance_path = os.path.join(instances_data[inst_name], inst_name)
    if not os.path.exists(instance_path):
        return yf.returnJson(False, "实例目录不存在")
        
    if action == 'start':
        yf.execShell(f"cd {instance_path} && docker compose start")
        return yf.returnJson(True, "实例已成功启动")
    else:
        yf.execShell(f"cd {instance_path} && docker compose stop")
        return yf.returnJson(True, "实例已成功停止")

def get_backups(args):
    try:
        data = json.loads(args)
    except:
        return yf.returnJson(False, "参数解析失败")
        
    inst_name = data.get('instance_name', '').strip()
    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")
        
    instance_path = os.path.join(instances_data[inst_name], inst_name)
    daily_dir = os.path.join(instance_path, "backups", "daily")
    weekly_dir = os.path.join(instance_path, "backups", "weekly")
    
    def scan_dir(path):
        lst = []
        if os.path.exists(path):
            for f in os.listdir(path):
                if f.endswith('.dump'):
                    fp = os.path.join(path, f)
                    stat = os.stat(fp)
                    size_mb = round(stat.st_size / (1024 * 1024), 2)
                    lst.append({
                        "name": f,
                        "path": fp,
                        "size": f"{size_mb} MB",
                        "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                        "timestamp": stat.st_mtime
                    })
        lst.sort(key=lambda x: x["timestamp"], reverse=True)
        return lst

    cron_file = f"/etc/cron.d/pg_backup_{inst_name}"
    auto_backup_enabled = os.path.exists(cron_file)
    
    result = {
        "daily": scan_dir(daily_dir),
        "weekly": scan_dir(weekly_dir),
        "auto_backup_enabled": auto_backup_enabled
    }
    return yf.returnJson(True, "ok", result)

def toggle_auto_backup(args):
    try:
        data = json.loads(args)
    except:
        return yf.returnJson(False, "参数解析失败")
        
    inst_name = data.get('instance_name', '').strip()
    enable = data.get('enable', False)
    
    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")
        
    instance_path = os.path.join(instances_data[inst_name], inst_name)
    script_path = os.path.join(instance_path, "scripts", "backup.sh")
    log_path = os.path.join(instance_path, "logs", "backup.log")
    cron_file = f"/etc/cron.d/pg_backup_{inst_name}"
    
    if enable:
        cron_content = f"0 2 * * * root /bin/bash {script_path} >> {log_path} 2>&1\n"
        yf.writeFile(cron_file, cron_content)
        return yf.returnJson(True, "自动备份计划已开启")
    else:
        if os.path.exists(cron_file):
            os.remove(cron_file)
        return yf.returnJson(True, "自动备份计划已关闭")

def create_backup(args):
    try:
        data = json.loads(args)
    except:
        return yf.returnJson(False, "参数解析失败")
        
    inst_name = data.get('instance_name', '').strip()
    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")
        
    instance_path = os.path.join(instances_data[inst_name], inst_name)
    script_path = os.path.join(instance_path, "scripts", "backup.sh")
    
    if not os.path.exists(script_path):
        return yf.returnJson(False, "备份脚本不存在，可能实例已损坏")
        
    # Execute backup script
    output = yf.execShell(f"/bin/bash {script_path}")
    if "备份失败" in output[0] or "备份失败" in output[1]:
        return yf.returnJson(False, f"备份失败！输出: {output[0]} {output[1]}")
    
    return yf.returnJson(True, "一键备份成功！")

def restore_backup(args):
    try:
        data = json.loads(args)
    except:
        return yf.returnJson(False, "参数解析失败")
        
    inst_name = data.get('instance_name', '').strip()
    file_path = data.get('file_path', '').strip()
    
    if not file_path or not os.path.exists(file_path):
        return yf.returnJson(False, "备份文件不存在或参数错误")
        
    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")
        
    instance_path = os.path.join(instances_data[inst_name], inst_name)
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
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)
    except:
        pass
        
    # Execute restore script in background or wait for it.
    output = yf.execShell(f"/bin/bash {script_path} {file_path}")
    if "数据还原完成" in output[0] or "数据还原完成" in output[1]:
        return yf.returnJson(True, "数据已成功还原！")
    else:
        return yf.returnJson(False, f"还原可能失败，请检查日志！输出: {output[0][:200]}")

def delete_backup(args):
    try:
        data = json.loads(args)
    except:
        return yf.returnJson(False, "参数解析失败")
        
    inst_name = data.get('instance_name', '').strip()
    file_path = data.get('file_path', '').strip()
    
    if not file_path or not os.path.exists(file_path):
        return yf.returnJson(False, "文件不存在或参数错误")
        
    # Ensure it's inside the backup dir for safety
    if "/backups/" not in file_path:
        return yf.returnJson(False, "非法的路径")
        
    try:
        os.remove(file_path)
        return yf.returnJson(True, "备份删除成功！")
    except Exception as e:
        return yf.returnJson(False, f"删除失败: {str(e)}")

def toggle_external_port(args):
    try:
        data = json.loads(args)
    except:
        return yf.returnJson(False, "参数解析失败")
        
    inst_name = data.get('instance_name', '').strip()
    is_ext = data.get('is_external', False)
    
    instances_data = load_instances()
    if inst_name not in instances_data:
        return yf.returnJson(False, "找不到该实例")
        
    instance_path = os.path.join(instances_data[inst_name], inst_name)
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
        
    content = content.replace(old_ports, new_ports)
    yf.writeFile(compose_file, content)
    
    yf.execShell(f"cd {instance_path} && docker compose down && docker compose up -d")
    
    return yf.returnJson(True, "配置已更新，容器已重启生效")

def create_instance(args):
    try:
        data = json.loads(args)
    except:
        return yf.returnJson(False, "参数解析失败")

    inst_name = data.get('instance_name', '').strip()
    if not inst_name or not re.match(r'^[a-zA-Z0-9_]+$', inst_name):
        return yf.returnJson(False, "实例名称不能为空且只能包含字母、数字和下划线")

    base_dir = data.get('base_dir', '/docker_data').strip()
    if not base_dir:
        base_dir = '/docker_data'
    
    inst_dir = os.path.join(base_dir, inst_name)
    if os.path.exists(inst_dir):
        return yf.returnJson(False, f"实例目录 {inst_dir} 已存在，请使用其他名称")

    db_user = data.get('db_user', 'postgres')
    db_pass = data.get('db_pass', '123456')
    db_name = data.get('db_name', 'mydb')
    port = data.get('port', '5432')
    disk_type = data.get('disk_type', 'ssd') # ssd, hdd_single, hdd_raid
    scenario = data.get('scenario', 'general') # general, high_concurrency, high_throughput
    mem_limit = data.get('mem_limit', '')
    daily_retention = data.get('daily_retention', 7)
    weekly_retention = data.get('weekly_retention', 30)

    sys_mem = get_mem_mb()
    try:
        user_mem = int(mem_limit) if mem_limit else int(sys_mem * 0.75)
        if user_mem > sys_mem * 0.75:
            user_mem = int(sys_mem * 0.75)
    except:
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

    # 1. 创建目录
    yf.execShell(f"mkdir -p {inst_dir}/conf")
    yf.execShell(f"mkdir -p {inst_dir}/data")
    yf.execShell(f"mkdir -p {inst_dir}/backups/daily")
    yf.execShell(f"mkdir -p {inst_dir}/backups/weekly")
    yf.execShell(f"mkdir -p {inst_dir}/scripts")
    yf.execShell(f"mkdir -p {inst_dir}/logs")
    
    yf.execShell(f"chown -R 999:999 {inst_dir}")
    yf.execShell(f"chmod -R 755 {inst_dir}")

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

DATE=$(date +%Y%m%d_%H%M%S)
DAILY_DIR="${{BACKUP_DIR}}/daily"
WEEKLY_DIR="${{BACKUP_DIR}}/weekly"
FILENAME="${{DB_NAME}}_${{DATE}}.dump"
BACKUP_PATH="${{DAILY_DIR}}/${{FILENAME}}"

mkdir -p "$DAILY_DIR" "$WEEKLY_DIR"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始数据库备份: ${{DB_NAME}}..."

docker exec -i ${{CONTAINER_NAME}} pg_dump -U ${{DB_USER}} -d ${{DB_NAME}} -Fc > "${{BACKUP_PATH}}"

if [ -s "${{BACKUP_PATH}}" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 备份成功: ${{BACKUP_PATH}} (大小: $(du -sh ${{BACKUP_PATH}} | awk '{{print $1}}'))"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 备份失败，生成的备份文件为空!"
    rm -f "${{BACKUP_PATH}}"
    exit 1
fi

if [ $(date +%u) -eq 7 ]; then
    cp "${{BACKUP_PATH}}" "${{WEEKLY_DIR}}/${{FILENAME}}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 已同步保存至每周备份目录."
fi

find "${{DAILY_DIR}}" -type f -name "*.dump" -mtime +${{DAILY_RETENTION}} -exec rm -f {{}} \\;
find "${{WEEKLY_DIR}}" -type f -name "*.dump" -mtime +${{WEEKLY_RETENTION}} -exec rm -f {{}} \\;
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 历史备份清理完毕."
"""
    yf.writeFile(f"{inst_dir}/scripts/backup.sh", backup_sh)
    yf.execShell(f"chmod +x {inst_dir}/scripts/backup.sh")

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
    yf.writeFile(f"{inst_dir}/scripts/restore.sh", restore_sh)
    yf.execShell(f"chmod +x {inst_dir}/scripts/restore.sh")

    # 6. 设置独立计划任务
    cron_content = f"0 2 * * * root /bin/bash {inst_dir}/scripts/backup.sh >> {inst_dir}/logs/backup.log 2>&1\n"
    yf.writeFile(f"/etc/cron.d/pg_backup_{inst_name}", cron_content)

    # 7. 启动容器
    yf.execShell(f"cd {inst_dir} && docker compose up -d")

    # 8. 保存记录
    instances_data = load_instances()
    instances_data[inst_name] = base_dir
    save_instances(instances_data)

    return yf.returnJson(True, "实例部署成功！容器正在启动中...")

def uninstall_instance(args):
    try:
        data = json.loads(args)
    except:
        return yf.returnJson(False, "参数解析失败")
    
    inst_name = data.get('instance_name', '').strip()
    keep_data = data.get('keep_data', True)
    base_dir = data.get('base_dir', '/docker_data').strip()

    if not inst_name:
        return yf.returnJson(False, "实例名称不能为空")
    
    inst_dir = os.path.join(base_dir, inst_name)
    
    # 1. 停止容器
    if os.path.exists(inst_dir):
        yf.execShell(f"cd {inst_dir} && docker compose down")
    else:
        # 如果目录不存在，可能只是通过其他方式启动的，尝试通过名字停掉
        yf.execShell(f"docker rm -f pg-{inst_name}")

    # 2. 清理计划任务
    if os.path.exists(f"/etc/cron.d/pg_backup_{inst_name}"):
        yf.execShell(f"rm -f /etc/cron.d/pg_backup_{inst_name}")

    # 3. 清理数据（可选）
    if not keep_data and os.path.exists(inst_dir):
        yf.execShell(f"rm -rf {inst_dir}")

    # 4. 移除记录
    instances_data = load_instances()
    if inst_name in instances_data:
        del instances_data[inst_name]
        save_instances(instances_data)

    return yf.returnJson(True, "实例已成功卸载！")


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
    elif func == 'manual_backup':
        print(manual_backup(args))
    elif func == 'delete_backup':
        print(delete_backup(args))
    elif func == 'restore_backup':
        print(restore_backup(args))
    elif func == 'toggle_external_port':
        print(toggle_external_port(args))
    else:
        print('error')
