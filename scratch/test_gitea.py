# -*- coding: utf-8 -*-
import sys
import os
import re

# 引入被测试的方法
def safe_search_value(value):
    if not value:
        return ""
    return re.sub(r"[^a-zA-Z0-9_\-\u4e00-\u9fa5]", "", str(value))

def safe_file_name(filename):
    if not filename:
        return None
    filename = os.path.basename(filename)
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", filename) or filename in [".", ".."]:
        return None
    return filename

# 测试 SQL 注入
sql_payloads = [
    ("admin' or '1'='1", "adminor11"),
    ("admin' --", "admin"),
    ('admin" union select 1,2--', "adminunionselect12"),
    ("正常用户名_123-测试", "正常用户名_123-测试")
]

print("=== 开始测试 SQL 注入防护 ===")
for payload, expected in sql_payloads:
    res = safe_search_value(payload)
    print("输入: {!r:<35} 过滤后: {!r:<25} 结果: {}".format(payload, res, "通过" if res == expected else "失败"))

# 测试目录穿越 & 命令注入
file_payloads = [
    ("../../../../etc/passwd", "passwd"),
    ("test.sh; rm -rf /;", "test.shrm-rf"),
    ("$(whoami)", "whoami"),
    ("test.sh&whoami", "test.shwhoami"),
    ("..", None),
    (".", None),
    ("valid-script.sh", "valid-script.sh"),
    ("script_1.txt", "script_1.txt")
]

print("\n=== 开始测试 目录穿越 & OS命令注入 防护 ===")
for payload, expected in file_payloads:
    res = safe_file_name(payload)
    print("输入: {!r:<35} 过滤后: {!r:<25} 结果: {}".format(payload, res, "通过" if res == expected else "失败"))
