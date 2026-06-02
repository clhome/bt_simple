import json
import os

new_rules = [
    [1, r"\$\{jndi:(ldap|rmi|dns|iiop|http|https)://.*?\}", "Log4j JNDI Injection", 0],
    [1, r"(\{\"@type\"\s*:\s*\".*?\"|autoTypeSupport)", "Fastjson RCE", 0],
    [1, r"(class\.module\.classLoader|%24%7B.*?%7D|spring\.cloud\.function\.routing-expression)", "Spring Core/Cloud RCE", 0],
    [1, r"(s=/?think/|think\\\\app|think\\\\config|invokeFunction)", "ThinkPHP RCE", 0],
    [1, r"(?i)(file|gopher|dict|ftp|http|https)://(127\.0\.0\.1|localhost|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|192\.168\.|::1)", "SSRF Local IP Targeting", 0],
    [1, r"(?i)(flushall|config\s+set\s+dir|config\s+set\s+dbfilename|slaveof|bgsave)", "Redis Unauthorized Access/RCE", 0],
    [1, r"(?i)(bash\s+-i|nc\s+-e\s+/bin/|sh\s+-i|perl\s+-MIO|python\s+-c\s+['\"]import\s+pty)", "Reverse Shell/Command Injection", 0]
]

targets = ['args.json', 'post.json', 'cookie.json', 'user_agent.json', 'url.json']
base_dir = r'f:\git\gitea20250909\bt_simple\plugins\op_waf\waf\rule'

for t in targets:
    path = os.path.join(base_dir, t)
    if not os.path.exists(path):
        continue
    with open(path, 'r', encoding='utf-8') as f:
        rules = json.load(f)
    
    # Check if Log4j rule already exists
    exists = False
    for r in rules:
        if len(r) >= 3 and 'Log4j' in str(r[2]):
            exists = True
            break
            
    if not exists:
        rules.extend(new_rules)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(rules, f, ensure_ascii=False, indent=4)
        print('Updated', t)
