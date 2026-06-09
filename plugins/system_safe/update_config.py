import json

config_path = 'f:/git/gitea20250909/bt_simple/plugins/system_safe/conf/config.json'
with open(config_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

if 'ssh' in data:
    del data['ssh']

with open(config_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=4)
print("Updated config.json")
