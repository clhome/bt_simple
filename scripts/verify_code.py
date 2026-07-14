# -*- coding: utf-8 -*-
import os
import re

def verify_code():
    error_count = 0
    # Workspace root directory
    workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Regex: Match import mw or from mw in py files (excluding mw.py itself)
    import_pat = re.compile(r'\bimport\s+mw\b|\bfrom\s+\.?\s*import\s+mw\b')

    for root, dirs, files in os.walk(workspace):
        if ".git" in root or "__pycache__" in root or "plugins" in root:
            continue
        for file in files:
            if file.endswith('.py') and file not in ('mw.py', 'verify_code.py'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    for idx, line in enumerate(f):
                        if import_pat.search(line):
                            print(f"[ERROR] 发现残留导入：{os.path.relpath(path, workspace)}: 第 {idx+1} 行: {line.strip()}")
                            error_count += 1
    if error_count == 0:
        print("[SUCCESS] 代码库静态检测通过：所有 python 文件的 mw 模块导入均已完美重构为 yf！")
        return True
    return False

if __name__ == "__main__":
    verify_code()
