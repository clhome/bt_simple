# -*- coding: utf-8 -*-
"""
bt_simple 插件 i18n 校验器
检查项：
  1. 所有 lang/*.json 语法合法
  2. 6 个语言包键集与 zh-CN 完全一致（无缺失/多余）
  3. 语言包 value 不含 HTML（红线 1）
  4. 所有插件 JS 语法合法
  5. 源码中残留的未包裹中文串统计
"""
import json, os, re, subprocess, sys

HAN = re.compile(r'[\u4e00-\u9fff]')
HTML_RE = re.compile(r'<[a-zA-Z][\s\S]*>')
LINE_COMMENT = re.compile(r'^\s*(//|\*|/\*)')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
NODE = r"C:\Users\wzucc\.workbuddy-ai\binaries\node\versions\22.22.2-2\node.exe"

root = sys.argv[1] if len(sys.argv) > 1 else 'plugins'
errors, warns = [], []
stats = {}

for name in sorted(os.listdir(root)):
    pdir = os.path.join(root, name)
    ld = os.path.join(pdir, 'lang')
    if not os.path.isdir(ld):
        continue
    base_p = os.path.join(ld, 'zh-CN.json')
    if not os.path.exists(base_p):
        errors.append(f"{name}: 缺少 zh-CN.json")
        continue
    try:
        base = json.load(open(base_p, encoding='utf-8'))
    except Exception as e:
        errors.append(f"{name}: zh-CN.json 解析失败 {e}")
        continue
    base_keys = set(base)

    # 2/3. 语言包对齐 + HTML 检查
    for lang in LANGS:
        p = os.path.join(ld, lang + '.json')
        if not os.path.exists(p):
            errors.append(f"{name}: 缺少 {lang}.json")
            continue
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception as e:
            errors.append(f"{name}/{lang}.json 解析失败 {e}")
            continue
        missing = base_keys - set(d)
        extra = set(d) - base_keys
        if missing:
            errors.append(f"{name}/{lang}.json 缺 {len(missing)} 键: {list(missing)[:3]}")
        if extra:
            warns.append(f"{name}/{lang}.json 多 {len(extra)} 键: {list(extra)[:3]}")
        for k, v in d.items():
            if isinstance(v, str) and HTML_RE.search(v):
                errors.append(f"{name}/{lang}.json HTML 入包: {k[:40]}")

    # 4. JS 语法
    for r, dirs, files in os.walk(pdir):
        if '__pycache__' in r:
            continue
        for fn in files:
            if not fn.endswith('.js') or fn.endswith('.i18n.bak'):
                continue
            fp = os.path.join(r, fn)
            res = subprocess.run([NODE, '--check', fp], capture_output=True, text=True)
            if res.returncode != 0:
                errors.append(f"{name}: JS 语法错误 {fn} :: {res.stderr.strip().splitlines()[0][:120]}")

    # 5. 残留未包裹
    residual = 0
    for r, dirs, files in os.walk(pdir):
        if '__pycache__' in r or os.path.basename(r) == 'lang':
            continue
        for fn in files:
            if not fn.endswith('.js'):
                continue
            for line in open(os.path.join(r, fn), encoding='utf-8', errors='ignore').read().split('\n'):
                if LINE_COMMENT.match(line.strip()):
                    continue
                if 'pt(' in line or 'msgTpl(' in line:
                    continue
                for m in re.finditer(r'(["\'])([^"\']*[\u4e00-\u9fff][^"\']*)\1', line):
                    v = m.group(2).strip()
                    if len(v) >= 2 and v not in base_keys:
                        residual += 1
    stats[name] = residual

print("=" * 70)
print(f"语言包键数: ", end="")
tot = 0
for name in sorted(os.listdir(root)):
    p = os.path.join(root, name, 'lang', 'zh-CN.json')
    if os.path.exists(p):
        tot += len(json.load(open(p, encoding='utf-8')))
print(f"{tot} 条（合计）")

res_total = sum(stats.values())
print(f"残留未包裹中文串: {res_total}")
if res_total:
    for n, c in sorted(stats.items(), key=lambda x: -x[1]):
        if c:
            print(f"   {n}: {c}")
print(f"\n错误 {len(errors)} 项 / 警告 {len(warns)} 项")
for e in errors[:60]:
    print("  [ERR]", e)
for w in warns[:15]:
    print("  [WARN]", w)
