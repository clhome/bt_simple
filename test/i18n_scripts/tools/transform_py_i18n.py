# -*- coding: utf-8 -*-
"""
御风面板 Python 后端代码多语言自动重构与提取工具（增强版）
"""

import os
import sys
import re
import json
import hashlib

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(TOOLS_DIR)

from merge_i18n_dict import merge_dict_file

def has_chinese(text):
    if not isinstance(text, str):
        return False
    return any('\u4e00' <= c <= '\u9fa5' for c in text)

def generate_key(prefix, text):
    direct_map = {
        '操作成功!': 'common.action_success',
        '操作成功': 'common.action_success',
        '操作失败!': 'common.action_failed',
        '操作失败': 'common.action_failed',
        '设置成功!': 'common.set_success',
        '设置成功': 'common.set_success',
        '设置失败!': 'common.set_failed',
        '设置失败': 'common.set_failed',
        '修改成功!': 'common.edit_success',
        '修改成功': 'common.edit_success',
        '修改失败!': 'common.edit_failed',
        '修改失败': 'common.edit_failed',
        '添加成功!': 'common.add_success',
        '添加成功': 'common.add_success',
        '添加失败!': 'common.add_failed',
        '添加失败': 'common.add_failed',
        '删除成功!': 'common.del_success',
        '删除成功': 'common.del_success',
        '删除失败!': 'common.del_failed',
        '删除失败': 'common.del_failed',
        '参数错误!': 'common.args_err',
        '参数错误': 'common.args_err',
        '指定参数错误!': 'common.args_err',
        '连接服务器失败!': 'common.connect_err',
        '目录不能为空!': 'file.dir_empty',
        '文件不存在!': 'file.not_exists',
        '日志为空': 'common.log_empty',
        '模版不存在!': 'site.template_not_exists',
        '模版已经存在!': 'site.template_exists',
        '模版内容不能为空!': 'site.template_empty',
        'SSL开启成功!': 'site.ssl_enabled',
        '证书已保存!': 'site.cert_saved',
        '连接成功': 'common.connect_success',
        '连接成功!': 'common.connect_success',
        '连接成功.': 'common.connect_success',
        '已连接': 'common.connected',
    }
    
    clean = text.strip()
    if clean in direct_map:
        return direct_map[clean]
        
    short_hash = hashlib.md5(clean.encode('utf-8')).hexdigest()[:6]
    return f"{prefix}.py_msg_{short_hash}"

def process_python_file(filepath, module_prefix):
    with open(filepath, 'r', encoding='utf-8') as f:
        code = f.read()

    extracted_dict = {}

    # 1. 匹配 .format(...) 模式: (yf.returnData|self.returnMsg)(status, '中文{}'.format(var))
    def repl_format(match):
        prefix_call = match.group(1)
        status = match.group(2)
        quote = match.group(3)
        msg = match.group(4)
        args_part = match.group(5)
        
        if not has_chinese(msg):
            return match.group(0)
            
        count = 0
        def to_brace(m):
            nonlocal count
            count += 1
            return f"{{{count}}}"
            
        template_msg = re.sub(r'\{[a-zA-Z0-9_]*\}', to_brace, msg)
        key = generate_key(module_prefix, template_msg)
        sec = key.split('.')[0]
        sub = key.split('.')[1] if '.' in key else key
        
        if sec not in extracted_dict:
            extracted_dict[sec] = {}
        extracted_dict[sec][sub] = template_msg
        
        if prefix_call.startswith('self.'):
            return f"{prefix_call}({status}, '{key}', {args_part})"
        return f"{prefix_call}({status}, '{key}', None, {args_part})"

    pattern_format = re.compile(r'(yf\.(?:returnData|returnJson|returnMsg)|self\.returnMsg)\(\s*([^,]+?)\s*,\s*(["\'])(.*?)\3\.format\((.*?)\)\)')

    # 2. 匹配 % 模式: (yf.returnData|self.returnMsg)(status, '中文 %s' % var)
    def repl_percent(match):
        prefix_call = match.group(1)
        status = match.group(2)
        quote = match.group(3)
        msg = match.group(4)
        vars_part = match.group(5)
        
        if not has_chinese(msg):
            return match.group(0)
            
        count = 0
        def to_brace(m):
            nonlocal count
            count += 1
            return f"{{{count}}}"
            
        template_msg = re.sub(r'%[sd]', to_brace, msg)
        key = generate_key(module_prefix, template_msg)
        sec = key.split('.')[0]
        sub = key.split('.')[1] if '.' in key else key
        
        if sec not in extracted_dict:
            extracted_dict[sec] = {}
        extracted_dict[sec][sub] = template_msg
        
        vars_clean = vars_part.strip()
        if vars_clean.startswith('(') and vars_clean.endswith(')'):
            args_str = vars_clean[1:-1].strip()
        else:
            args_str = vars_clean
            
        if prefix_call.startswith('self.'):
            return f"{prefix_call}({status}, '{key}', {args_str})"
        return f"{prefix_call}({status}, '{key}', None, {args_str})"

    pattern_percent = re.compile(r'(yf\.(?:returnData|returnJson|returnMsg)|self\.returnMsg)\(\s*([^,]+?)\s*,\s*(["\'])(.*?)\3\s*%\s*([a-zA-Z0-9_\.\(\)\,\s\[\]\'\"]+?)\)')

    # 3. 匹配字符串拼接 + 模式: (yf.returnData|self.returnMsg)(status, '中文' + expr)
    def repl_concat(match):
        prefix_call = match.group(1)
        status = match.group(2)
        quote = match.group(3)
        msg = match.group(4)
        expr = match.group(5)
        
        if not has_chinese(msg):
            return match.group(0)
            
        template_msg = msg + "{1}"
        key = generate_key(module_prefix, template_msg)
        sec = key.split('.')[0]
        sub = key.split('.')[1] if '.' in key else key
        
        if sec not in extracted_dict:
            extracted_dict[sec] = {}
        extracted_dict[sec][sub] = template_msg
        
        if prefix_call.startswith('self.'):
            return f"{prefix_call}({status}, '{key}', {expr.strip()})"
        return f"{prefix_call}({status}, '{key}', None, {expr.strip()})"

    pattern_concat = re.compile(r'(yf\.(?:returnData|returnJson|returnMsg)|self\.returnMsg)\(\s*([^,]+?)\s*,\s*(["\'])(.*?)\3\s*\+\s*([a-zA-Z0-9_\.\(\)\,\s\[\]\'\"]+?)\)')

    # 4. 匹配简单静态字符串
    def repl_simple(match):
        prefix_call = match.group(1)
        status = match.group(2)
        quote = match.group(3)
        msg = match.group(4)
        rest = match.group(5) or ''
        
        if not has_chinese(msg):
            return match.group(0)
            
        key = generate_key(module_prefix, msg)
        sec = key.split('.')[0]
        sub = key.split('.')[1] if '.' in key else key
        
        if sec not in extracted_dict:
            extracted_dict[sec] = {}
        extracted_dict[sec][sub] = msg
        
        return f"{prefix_call}({status}, '{key}'{rest})"

    pattern_simple = re.compile(r'(yf\.(?:returnData|returnJson|returnMsg)|self\.returnMsg)\(\s*([^,]+?)\s*,\s*(["\'])(.*?)\3(\s*,.*?)?\)')

    new_code = pattern_format.sub(repl_format, code)
    new_code = pattern_percent.sub(repl_percent, new_code)
    new_code = pattern_concat.sub(repl_concat, new_code)
    new_code = pattern_simple.sub(repl_simple, new_code)

    if new_code != code:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_code)
        print(f"[REFACTORED] {filepath}")
    else:
        print(f"[UNCHANGED] {filepath}")

    return extracted_dict

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python transform_py_i18n.py <file_or_dir> <module_prefix>")
        sys.exit(1)
        
    target = sys.argv[1]
    mod = sys.argv[2]
    
    all_extracted = {}
    if os.path.isfile(target):
        ext = process_python_file(target, mod)
        for s, d in ext.items():
            if s not in all_extracted: all_extracted[s] = {}
            all_extracted[s].update(d)
    else:
        for root, dirs, files in os.walk(target):
            for f in files:
                if f.endswith('.py'):
                    fp = os.path.join(root, f)
                    ext = process_python_file(fp, mod)
                    for s, d in ext.items():
                        if s not in all_extracted: all_extracted[s] = {}
                        all_extracted[s].update(d)
                        
    for sec, entries in all_extracted.items():
        if entries:
            scratch_path = os.path.join(TOOLS_DIR, f"_temp_{sec}.json")
            with open(scratch_path, 'w', encoding='utf-8') as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
            merge_dict_file(sec, scratch_path)
            if os.path.exists(scratch_path):
                os.remove(scratch_path)
                
    print("Transformation completed.")
