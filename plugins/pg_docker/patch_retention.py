import os
import json

base_dir = '/docker_data'
json_path = 'f:/git/gitea20250909/bt_simple/plugins/pg_docker/instances.json'
data = {}
if os.path.exists(json_path):
    with open(json_path, 'r') as f:
        try:
            data = json.load(f)
        except:
            pass
else:
    if os.path.exists(base_dir):
        for item in os.listdir(base_dir):
            if os.path.isdir(os.path.join(base_dir, item)):
                data[item] = base_dir

for inst_name, d in data.items():
    p = os.path.join(d, inst_name, 'scripts', 'backup.sh')
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f:
            old_c = f.read()
        
        # We need to extract the existing DB_USER and DB_NAME
        db_user = ""
        db_name = ""
        daily_retention = 7
        weekly_retention = 30
        for line in old_c.split('\n'):
            if line.startswith('DB_USER='):
                db_user = line.split('=')[1].strip('"')
            elif line.startswith('DB_NAME='):
                db_name = line.split('=')[1].strip('"')
            elif line.startswith('DAILY_RETENTION='):
                try: daily_retention = int(line.split('=')[1])
                except: pass
            elif line.startswith('WEEKLY_RETENTION='):
                try: weekly_retention = int(line.split('=')[1])
                except: pass
                
        inst_dir = os.path.join(d, inst_name)
        new_c = f"""#!/bin/bash
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
        with open(p, 'w', encoding='utf-8') as f:
            f.write(new_c)
        print(f"Patched {p}")
