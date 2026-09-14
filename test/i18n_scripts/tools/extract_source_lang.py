# -*- coding: utf-8 -*-
"""
提取现有 zh-CN 的所有词条并结构化
为生成真正的 phrases_data.py 提供素材
"""

import os
import re
import json

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../web/static/language/zh-CN"))

# 1. 提取 public.json
with open(os.path.join(base_dir, "public.json"), "r", encoding="utf-8") as f:
    public_data = json.load(f)

# 2. 提取 template.json
with open(os.path.join(base_dir, "template.json"), "r", encoding="utf-8") as f:
    template_data = json.load(f)

# 3. 提取 log.json
with open(os.path.join(base_dir, "log.json"), "r", encoding="utf-8") as f:
    log_data = json.load(f)

# 4. 解析 lan.js
with open(os.path.join(base_dir, "lan.js"), "r", encoding="utf-8") as f:
    lan_content = f.read()

# 解析 lan.js 中的 get msgs 以及各个 section
lan_msgs = {}
msgs_match = re.search(r'var msgs = (\{[\s\S]*?\n\t*\})', lan_content)
if msgs_match:
    try:
        # 用正则匹配键值
        for k, v in re.findall(r'"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)"', msgs_match.group(1)):
            lan_msgs[k] = v.replace('\\"', '"')
    except Exception as e:
        print("Error parsing lan.get:", e)

lan_sections = {}
# 匹配类似 "index":{ ... }, "config":{ ... } 等
section_matches = re.findall(r'"([a-zA-Z0-9_]+)"\s*:\s*\{([^}]+)\}', lan_content)
for sec_name, sec_body in section_matches:
    if sec_name == "get":
        continue
    items = {}
    for k, v in re.findall(r'"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)"', sec_body):
        items[k] = v.replace('\\"', '"')
    lan_sections[sec_name] = items

stats = {
    "public_count": len(public_data),
    "template_sections": len(template_data),
    "template_total_keys": sum(len(v) for v in template_data.values() if isinstance(v, dict)),
    "log_count": len(log_data),
    "lan_get_count": len(lan_msgs),
    "lan_sections": {k: len(v) for k, v in lan_sections.items()}
}

print(json.dumps(stats, indent=2, ensure_ascii=False))
