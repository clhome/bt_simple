# -*- coding: utf-8 -*-
"""
bt_simple 插件 i18n 提取器
扫描 plugins/<name>/ 下 JS/HTML 中的用户可见中文，输出待翻译清单与包裹建议。
用法: python i18n_extract.py [--plugin NAME] [--json OUT]
"""
import json, os, re, sys, argparse

HAN = re.compile(r'[\u4e00-\u9fff]')
LINE_COMMENT = re.compile(r'^\s*(//|\*|/\*)')
# 已是格式化/占位符的字符串，无需包裹
PLACEHOLDER_OK = re.compile(r'^\{[\d\w]+\}$')


def strip_html_blocks(txt):
    txt = re.sub(r'<script[\s\S]*?</script>', '', txt, flags=re.I)
    txt = re.sub(r'<style[\s\S]*?</style>', '', txt, flags=re.I)
    txt = re.sub(r'<!--[\s\S]*?-->', '', txt)
    return txt


def classify(s):
    if re.search(r'<[a-zA-Z/]', s):
        return 'HTML'
    if re.search(r'\{\d+\}', s) or re.search(r'\{\w+\}', s):
        return 'TPL'
    return 'PLAIN'


def load_base_keys(plugin_dir):
    """zh-CN.json 是原文基线，其键集即已登记词条。"""
    f = os.path.join(plugin_dir, 'lang', 'zh-CN.json')
    if not os.path.exists(f):
        return None
    with open(f, encoding='utf-8') as fh:
        return set(json.load(fh).keys())


def scan_js(path, base_keys, plugin, plugin_dir):
    """扫描 JS：区分已包裹 / 未包裹。返回 (unwrapped, wrapped) 项列表。"""
    out = []
    rel = os.path.relpath(path, plugin_dir).replace('\\', '/')
    code_lines = open(path, encoding='utf-8', errors='ignore').read().split('\n')
    for idx, line in enumerate(code_lines, 1):
        stripped = line.strip()
        if LINE_COMMENT.match(stripped):
            continue
        # 跳过 URL / 文件路径 / 纯代码注释行
        for m in re.finditer(r'(["\'])([^"\']*[\u4e00-\u9fff][^"\']*)\1', line):
            raw = m.group(2).strip()
            if len(raw) < 2 or raw in base_keys:
                continue
            if PLACEHOLDER_OK.match(raw):
                continue
            # 整行是注释（行内 // 之后）
            pos = m.start()
            slash = line.find('//')
            if slash != -1 and pos > slash:
                continue
            wrapped = 'pt(' in line or 'msgTpl(' in line
            out.append({
                'plugin': plugin, 'file': rel,
                'line': idx, 'text': raw, 'kind': classify(raw), 'wrapped': wrapped,
                'code': stripped[:200],
            })
    return out


def scan_html(path, base_keys, plugin, plugin_dir):
    """扫描 HTML：仅取标签间纯文本与关键属性。"""
    txt = strip_html_blocks(open(path, encoding='utf-8', errors='ignore').read())
    rel = os.path.relpath(path, plugin_dir).replace('\\', '/')
    found = {}
    for m in re.finditer(r'>([^<>]+)<', txt):
        s = re.sub(r'\s+', ' ', m.group(1)).strip()
        if s and HAN.search(s) and len(s) >= 2 and s not in base_keys:
            found.setdefault(s, None)
    for m in re.finditer(r'(?:placeholder|title|value|data-title)\s*=\s*["\']([^"\']*[\u4e00-\u9fff][^"\']*)["\']', txt):
        s = re.sub(r'\s+', ' ', m.group(1)).strip()
        if len(s) >= 2 and s not in base_keys:
            found.setdefault(s, None)
    return [{'plugin': plugin, 'file': rel, 'line': 0, 'text': k, 'kind': classify(k),
             'wrapped': True, 'code': 'HTML text node'} for k in found]


def run(plugins_root, only=None):
    results = []
    for name in sorted(os.listdir(plugins_root)):
        pdir = os.path.join(plugins_root, name)
        if not os.path.isdir(pdir) or (only and name != only):
            continue
        base_keys = load_base_keys(pdir)
        if base_keys is None:
            continue
        for root, dirs, files in os.walk(pdir):
            if '__pycache__' in root or os.path.basename(root) == 'lang':
                continue
            for fn in files:
                fp = os.path.join(root, fn)
                if fn.endswith('.js'):
                    results += scan_js(fp, base_keys, name, pdir)
                elif fn.endswith('.html'):
                    results += scan_html(fp, base_keys, name, pdir)
    return results


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--plugin')
    ap.add_argument('--json')
    ap.add_argument('--root', default='.')
    a = ap.parse_args()
    items = run(a.root, a.plugin)
    unwrapped = [i for i in items if not i['wrapped']]
    print(f"总计 {len(items)} 处；未包裹 {len(unwrapped)} 处")
    for i in items:
        flag = ' ' if i['wrapped'] else '!'
        print(f"{flag} {i['plugin']:<22}{i['file']}:{i['line']:<6}{i['kind']:<6}{i['text'][:60]}")
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
