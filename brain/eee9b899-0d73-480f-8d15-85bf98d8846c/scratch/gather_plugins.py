import os
import json

plugins_dir = r'f:\git\gitea20250909\bt_simple\plugins'
results = []

for plugin_name in os.listdir(plugins_dir):
    plugin_path = os.path.join(plugins_dir, plugin_name)
    if os.path.isdir(plugin_path):
        info_path = os.path.join(plugin_path, 'info.json')
        if os.path.exists(info_path):
            try:
                with open(info_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    results.append({
                        'name': data.get('name'),
                        'title': data.get('title'),
                        'versions': data.get('versions', []),
                        'updates': data.get('updates', [])
                    })
            except Exception as e:
                results.append({'name': plugin_name, 'error': str(e)})

print(json.dumps(results, indent=4, ensure_ascii=False))
