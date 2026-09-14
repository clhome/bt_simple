# -*- coding: utf-8 -*-
"""
HTML 片段专项修复器（红线 1）

目标：把 JS 字符串字面量中的 HTML 标签与中文文本分离，标签留在代码，纯文本交给 pt()：
    '...<span class="x">已完成</span>...'  ->  '...<span class="x">' + pt('已完成') + '</span>...'

设计原则（安全性优先）：
  1. 全文扫描，正确处理反斜杠续行的多行字符串与转义字符。
  2. 只在"当前处于某个 JS 字符串内部"的位置做替换，绝不误吞字符串外的代码。
  3. 拆出的纯文本写入语言包；HTML 标签原样保留。
  4. 已含 pt( 的串跳过（避免二次处理）。
  5. 默认 dry-run，--apply 才写盘。

用法：
    python scripts/i18n_fix_html.py plugins            # dry-run
    python scripts/i18n_fix_html.py plugins --apply    # 实际写入
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from i18n_glossary_common import COMMON
from i18n_glossary_extra import EXTRA
from i18n_glossary_special import FINAL, HTML_TEXT

GLOSSARY = {**COMMON, **EXTRA, **FINAL, **HTML_TEXT}
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
HAN = re.compile(r'[\u4e00-\u9fff]')
TAG = re.compile(r'<[a-zA-Z/][^<>]*>')


def scan_literals(src):
    """
    全文扫描 JS 字符串字面量，返回 [(start_content, end_content, quote), ...]。
    - 正确处理 \\ 转义、\\ 行续接、以及 '..' / ".." 两种引号。
    - 跳过行注释 // 与块注释 /* */。
    - 返回的是「内容」区间（不含两侧引号）。
    """
    out = []
    i, n = 0, len(src)
    q = None          # 当前字符串引号
    cstart = 0        # 内容起点
    in_line_c = False
    in_block_c = False
    while i < n:
        c = src[i]
        if in_line_c:
            if c == '\n':
                in_line_c = False
            i += 1
            continue
        if in_block_c:
            if c == '*' and i + 1 < n and src[i + 1] == '/':
                in_block_c = False
                i += 2
                continue
            i += 1
            continue
        if q is None:
            if c == '/' and i + 1 < n and src[i + 1] == '/':
                in_line_c = True
                i += 2
                continue
            if c == '/' and i + 1 < n and src[i + 1] == '*':
                in_block_c = True
                i += 2
                continue
            if c in ('"', "'"):
                q = c
                cstart = i + 1
            i += 1
            continue
        else:
            if c == '\\':
                i += 2           # 跳过转义字符（含 \ 续行）
                continue
            if c == q:
                out.append((cstart, i, q))
                q = None
            i += 1
    return out


def split_literal(content):
    """
    把含 HTML 标签 + 中文的字符串内容拆成 [('raw', 片段), ('pt', 文本), ...]。
    返回 None 表示无需/无法处理。
    """
    if not TAG.search(content):
        return None
    if not HAN.search(content):
        return None
    if 'pt(' in content:
        return None

    # 以 HTML 状态机解析：只有"处于标签之外、且此前确实闭合过一个标签"的区域才算文本节点
    # 这是关键：若内容以属性尾部开头（如 '" placeholder="xx">'），在遇到首个 '>' 之前
    # 都属于属性区，绝不能当作文本包裹。
    segments = []          # 真正的 DOM 文本节点区间
    i, n = 0, len(content)
    ts = None              # 当前文本起点
    seen_tag_end = False   # 是否已遇到过一个 '>'（用于排除属性尾部）
    while i < n:
        c = content[i]
        if c == '<':
            if ts is not None:
                segments.append((ts, i))
                ts = None
            j = content.find('>', i)
            if j == -1:
                i = n
                break
            seen_tag_end = True
            i = j + 1
        else:
            if ts is None:
                # 只有已经闭合过标签，后续内容才可能是文本节点
                if seen_tag_end:
                    ts = i
            i += 1
    if ts is not None:
        segments.append((ts, n))

    keep = []
    for s, e in segments:
        seg = content[s:e]
        # 文本节点内不应再出现未闭合的引号/等号等属性残片
        if HAN.search(seg) and seg.strip():
            keep.append((s, e))
    if not keep:
        return None

    parts = []
    pos = 0
    for s, e in keep:
        seg = content[s:e]
        lead = len(seg) - len(seg.lstrip())
        trail = len(seg) - len(seg.rstrip())
        a, b = s + lead, e - trail
        if a > pos:
            parts.append(('raw', content[pos:a]))
        parts.append(('pt', content[a:b]))
        pos = b
    if pos < n:
        parts.append(('raw', content[pos:]))
    return parts


def node_check(src_text, tag='tmp'):
    """用 node --check 校验一段 JS 源码是否语法合法。返回 (ok, err)。"""
    import subprocess, tempfile
    NODE = r"C:\Users\wzucc\.workbuddy-ai\binaries\node\versions\22.22.2-2\node.exe"
    fd, p = tempfile.mkstemp(suffix='.js', prefix='i18nchk_')
    os.close(fd)
    try:
        with open(p, 'w', encoding='utf-8', newline='') as f:
            f.write(src_text)
        r = subprocess.run([NODE, '--check', p], capture_output=True, text=True)
        return (r.returncode == 0), (r.stderr.strip().splitlines()[0] if r.returncode else '')
    finally:
        try:
            os.remove(p)
        except OSError:
            pass


def process_file(fp, collected, apply_changes):
    src = open(fp, encoding='utf-8', errors='ignore').read()
    lits = scan_literals(src)
    fixes = []
    for (s, e, q) in lits:
        content = src[s:e]
        parts = split_literal(content)
        if not parts:
            continue
        pieces = []
        for kind, val in parts:
            if kind == 'raw':
                if val == '':
                    continue
                # raw 段用外层引号包住；内部出现同款引号需转义
                pieces.append(q + val.replace(q, '\\' + q) + q)
            else:
                if "'" not in val:
                    pieces.append("pt('%s')" % val)
                elif '"' not in val:
                    pieces.append('pt("%s")' % val)
                else:
                    pieces.append("pt('%s')" % val.replace("'", "\\'"))
        expr = ' + '.join(pieces) if pieces else "''"
        fixes.append((s - 1, e + 1, expr, [v for k, v in parts if k == 'pt']))

    if not fixes:
        return 0

    # 逐条应用 + 语法闸门：任何一条导致语法错误就回滚该条
    accepted = []
    cur = src
    for (s, e, r, txts) in reversed(fixes):
        trial = cur[:s] + r + cur[e:]
        ok, err = node_check(trial)
        if ok:
            accepted.append((s, e, r, txts))
            cur = trial

    if not accepted:
        return 0
    for _, _, _, txts in accepted:
        for t in txts:
            collected.add(t)
    if apply_changes:
        with open(fp, 'w', encoding='utf-8', newline='') as f:
            f.write(cur)
    return len(accepted)


def add_keys(plugin_dir, keys):
    lang_dir = os.path.join(plugin_dir, 'lang')
    order_path = os.path.join(lang_dir, 'zh-CN.json')
    if not os.path.exists(order_path):
        return
    base = json.load(open(order_path, encoding='utf-8'))
    for k in keys:
        if k not in base:
            base[k] = k
    order = list(base.keys())
    for lang in LANGS:
        p = os.path.join(lang_dir, lang + '.json')
        d = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
        for k in base:
            if k in d:
                continue
            if lang in ('zh-CN', 'zh-TW'):
                d[k] = k
            elif k in GLOSSARY and lang in GLOSSARY[k]:
                d[k] = GLOSSARY[k][lang]
            else:
                d[k] = k
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({k: d[k] for k in order if k in d}, f, ensure_ascii=False, indent=1)
            f.write('\n')


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else 'plugins'
    apply_changes = '--apply' in sys.argv
    total_fixed = 0
    total_keys = 0
    for name in sorted(os.listdir(root)):
        pdir = os.path.join(root, name)
        if not os.path.isdir(pdir):
            continue
        collected = set()
        fixed = 0
        for r, dirs, files in os.walk(pdir):
            if '__pycache__' in r or os.path.basename(r) == 'lang':
                continue
            for fn in files:
                if fn.endswith('.js') and not fn.endswith('.i18n.bak') and not fn.endswith('.min.js'):
                    fixed += process_file(os.path.join(r, fn), collected, apply_changes)
        if collected:
            add_keys(pdir, collected)
            total_keys += len(collected)
        if fixed:
            print(f"{name}: 拆分 {fixed} 处, 新增词条 {len(collected)}")
            total_fixed += fixed
    print(f"\n总计: 拆分 {total_fixed} 处, 新增词条 {total_keys}")
    print("模式:", "APPLIED" if apply_changes else "DRY-RUN")


if __name__ == '__main__':
    main()
