#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import sys
import argparse
import shutil

# 定义需要扫描的目录
SCAN_DIRS = [
    'web/static/app',
    'web/templates',
    'plugins',
    'web/static/js/jquery.dragsort-0.5.2.min.js'
]

# 需要排除的特定文件（例如第三方库、已有的压缩文件等）
EXCLUDE_FILES = [
    'jquery-1.12.4.min.js',
    'jquery-ui.min.js',
    'bootstrap.min.js',
    'codemirror.min.js',
    'echarts.min.js',
    'clipboard.min.js',
    'marked.min.js',
    'xm-select.js',
    'socket.io.min.js'
]

# 定义扫描和替换规则
# 格式: (规则名, 匹配正则表达式, 替换模板, 描述)
REPLACE_RULES = [
    # 1. $.parseJSON -> JSON.parse (直接字符串替换即可，安全)
    (
        '$.parseJSON',
        re.compile(r'\$\.parseJSON'),
        'JSON.parse',
        '$.parseJSON 替换为 JSON.parse'
    ),
    # 2. $.trim(嵌套单层小括号, 如 $(id).val()) -> String($(id).val()).trim()
    (
        '$.trim_nested',
        re.compile(r'\$\.trim\(\s*(\$\([^)]+\)\.[a-zA-Z0-9_]+\([^)]*\))\s*\)'),
        r'String(\1).trim()',
        '$.trim($(el).val()) 替换为 String($(el).val()).trim()'
    ),
    # 3. $.trim(无小括号变量, 如 data[i]) -> String(data[i]).trim()
    (
        '$.trim_simple',
        re.compile(r'\$\.trim\(\s*([^()]+)\s*\)'),
        r'String(\1).trim()',
        '$.trim(var) 替换为 String(var).trim()'
    ),
    # 4. .bind('event', fn) -> .on('event', fn)
    (
        '.bind',
        re.compile(r'\.bind\(\s*(\'[^\']+\'|"[^"]+")\s*,\s*'),
        r'.on(\1, ',
        '.bind(event, fn) 替换为 .on(event, fn)'
    ),
    # 5. .unbind('event') -> .off('event')
    (
        '.unbind_event',
        re.compile(r'\.unbind\(\s*(\'[^\']+\'|"[^"]+")\s*\)'),
        r'.off(\1)',
        '.unbind(event) 替换为 .off(event)'
    ),
    # 6. .unbind() -> .off()
    (
        '.unbind_all',
        re.compile(r'\.unbind\(\s*\)'),
        '.off()',
        '.unbind() 替换为 .off()'
    ),
    # 7. $(document).ready(function() { -> $(function() {
    (
        '$(document).ready',
        re.compile(r'\$\(document\)\.ready\(\s*function\s*\(\)\s*\{'),
        '$(function() {',
        '$(document).ready() 缩写为 $(function())'
    ),
    # 8. .error(function) -> .fail(function) (jQuery 3.x 移除了 jQXHR.error)
    (
        '.error_to_fail',
        re.compile(r'\.error\(\s*'),
        '.fail(',
        '.error(fn) 替换为 .fail(fn)'
    ),
    # 9. .size() -> .length (jQuery 3.x 移除了 .size())
    (
        '.size_to_length',
        re.compile(r'\.size\(\)'),
        '.length',
        '.size() 替换为 .length'
    ),
    # 10. 事件简写绑定（匿名函数）如 .click(function() { -> .on('click', function() {
    (
        'event_shorthand_fn',
        re.compile(r'\.(click|dblclick|blur|focus|resize|scroll|mousedown|mouseup|mousemove|mouseover|mouseout|mouseenter|mouseleave|change|select|submit|keydown|keypress|keyup)\(\s*function\b'),
        r".on('\1', function",
        '事件简写绑定（匿名函数）替换为 .on()'
    ),
    # 11. 事件简写绑定（回调变量）如 .resize(autoHeight) -> .on('resize', autoHeight)
    (
        'event_shorthand_var',
        re.compile(r'\.(click|dblclick|blur|focus|resize|scroll|mousedown|mouseup|mousemove|mouseover|mouseout|mouseenter|mouseleave|change|select|submit|keydown|keypress|keyup)\(\s*([a-zA-Z0-9_$.]+)\s*\)'),
        r".on('\1', \2)",
        '事件简写绑定（回调变量）替换为 .on()'
    )
]

def scan_files(root_dir):
    """递归获取所有需要扫描的文件"""
    target_files = []
    # 增加第三方目录排除
    exclude_dirs = ['lib', 'vendor', 'jquery', 'node_modules']
    
    for d in SCAN_DIRS:
        dir_path = os.path.join(root_dir, d)
        if not os.path.exists(dir_path):
            continue
        
        if os.path.isfile(dir_path):
            if not any(ex in os.path.basename(dir_path) for ex in EXCLUDE_FILES):
                target_files.append(dir_path)
            continue

        for root, dirs, files in os.walk(dir_path):
            # 过滤不需要扫描的第三方目录
            dirs[:] = [d for d in dirs if d.lower() not in exclude_dirs]
            
            for file in files:
                # 排除文件名以 jquery 开头的第三方插件/库文件，但特许 dragsort 插件以自动修复 .size()
                if file.lower().startswith('jquery') and not file.lower().startswith('jquery-3.7.1') and 'dragsort' not in file.lower():
                    continue
                if file.endswith(('.js', '.html')):
                    if not any(ex in file for ex in EXCLUDE_FILES):
                        target_files.append(os.path.join(root, file))
    return target_files


def process_file(filepath, fix=False):
    """处理单个文件，执行匹配或替换"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"[-] 读取文件失败: {filepath}, 错误: {e}")
        return 0, []

    modified_content = content
    findings = []

    for name, pattern, repl, desc in REPLACE_RULES:
        matches = pattern.findall(modified_content)
        if matches:
            for match in matches:
                # 记录发现的匹配项
                findings.append((name, desc, str(match)))
            if fix:
                modified_content = pattern.sub(repl, modified_content)

    if fix and modified_content != content:
        # 备份原文件
        bak_path = filepath + '.bak'
        shutil.copyfile(filepath, bak_path)
        
        # 写入修复后的文件，强制使用 LF 换行，UTF-8 编码
        # 为了符合 core_philosophy 保持无 BOM UTF-8
        with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
            f.write(modified_content)
        print(f"[+] 已修复并备份: {filepath}")
        return len(findings), findings
    
    return len(findings), findings

def main():
    parser = argparse.ArgumentParser(description='jQuery 废弃 API 扫描与修复工具')
    parser.add_argument('--report', action='store_true', help='生成待修改点详细报告')
    parser.add_argument('--fix', action='store_true', help='自动修复文件并生成 .bak 备份')
    args = parser.parse_args()

    # 默认如果没传参数，就执行 report 报告模式
    if not args.report and not args.fix:
        args.report = True

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    files = scan_files(root_dir)
    print(f"[*] 共扫描到 {len(files)} 个待检测 JS/HTML 文件...")

    total_findings = 0
    all_reports = []

    for filepath in files:
        count, findings = process_file(filepath, fix=args.fix)
        if count > 0:
            total_findings += count
            rel_path = os.path.relpath(filepath, root_dir)
            all_reports.append((rel_path, findings))

    print("\n" + "="*50)
    if args.fix:
        print(f"[!] 自动修复完成。共修改了 {len(all_reports)} 个文件中的 {total_findings} 处潜在废弃 API。")
        print("[!] 请使用 git diff 审查变更。审查无误后可以删除 .bak 备份文件。")
    else:
        print(f"[!] 扫描完成。共发现 {total_findings} 处待修改点：\n")
        for rel_path, findings in all_reports:
            print(f"文件: {rel_path}")
            for rule_name, desc, match_str in findings:
                print(f"  - [{rule_name}] {desc} (匹配项: {match_str.strip()})")
            print("-" * 50)

if __name__ == '__main__':
    main()
