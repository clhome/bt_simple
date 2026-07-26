import os
import json

base_dir = '/docker_data'
json_path = 'instances.json'
data = {}
if os.path.exists(json_path):
    with open(json_path, 'r') as f:
        try:
            data = json.load(f)
        except:
            pass
else:
    # also try checking default base dir
    if os.path.exists(base_dir):
        for item in os.listdir(base_dir):
            if os.path.isdir(os.path.join(base_dir, item)):
                data[item] = base_dir

for inst, d in data.items():
    p = os.path.join(d, inst, 'scripts', 'backup.sh')
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f:
            c = f.read()
        if 'docker inspect' not in c:
            check = '''
if [ "$(docker inspect -f '{{.State.Running}}' ${CONTAINER_NAME} 2>/dev/null)" != "true" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 容器未运行，跳过备份."
    exit 0
fi
'''
            c = c.replace('mkdir -p "$DAILY_DIR"', check + '\nmkdir -p "$DAILY_DIR"')
            with open(p, 'w', encoding='utf-8') as f:
                f.write(c)
            print(f'Patched {p}')
