# -*- coding: utf-8 -*-
"""
扫描「中文片段 + 变量 + 中文片段」的句中拼接（违反 {n} 模板化红线）。

覆盖 4 种组合（A/C 可为字面量或 pt('...')）：
    1.  '中文A' + expr + '中文C'
    2.  pt('中文A') + expr + '中文C'
    3.  '中文A' + expr + pt('中文C')
    4.  pt('中文A') + expr + pt('中文C')   <- 仍然违反，需合并为单句模板

判定：若 A 尾或 C 头紧邻 HTML 标签（> 或 <），视为结构性拼接，跳过。

用法:
    python i18n_concat_audit.py            # 全库
    python i18n_concat_audit.py docker     # 单插件
"""
import io
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
PLUGINS = os.path.join(ROOT, 'plugins')
CJK = r'[\u4e00-\u9fa5]'
EXPR = r"""[A-Za-z_$][\w$]*(?:\.[\w$]+|\[[^\]]*\])*(?:\([^()]*\))?(?:\s*\+\s*[A-Za-z_$][\w$]*(?:\.[\w$]+|\[[^\]]*\])*)*"""

# 操作数：单引号字面量 / 双引号字面量 / pt('...')
OPERAND = (
    r"""(?:'((?:[^'\\\n]|\\.)*%s(?:[^'\\\n]|\\.)*)'"""        # g1
    r"""|"((?:[^"\\\n]|\\.)*%s(?:[^"\\\n]|\\.)*)\""""          # g2
    r"""|pt\s*\(\s*'((?:[^'\\\n]|\\.)*%s(?:[^'\\\n]|\\.)*)'\s*\))"""  # g3
) % (CJK, CJK, CJK)

PAT = re.compile(OPERAND + r"\s*\+\s*(" + EXPR + r")\s*\+\s*" + OPERAND)


def strip_comments(js):
    out, i, n = [], 0, len(js)
    while i < n:
        c = js[i]
        if c in '\'"':
            q = c
            out.append(c)
            i += 1
            while i < n:
                out.append(js[i])
                if js[i] == '\\':
                    if i + 1 < n:
                        out.append(js[i + 1])
                    i += 2
                    continue
                if js[i] == q:
                    i += 1
                    break
                i += 1
            continue
        if c == '/' and i + 1 < n:
            if js[i + 1] == '/':
                while i < n and js[i] != '\n':
                    i += 1
                continue
            if js[i + 1] == '*':
                i += 2
                while i + 1 < n and not (js[i] == '*' and js[i + 1] == '/'):
                    i += 1
                i += 2
                continue
        out.append(c)
        i += 1
    return ''.join(out)


def boundary_ok(a, c):
    return a.rstrip().endswith('>') or c.lstrip().startswith('<')


def find_js_files(pdir):
    out = []
    for sub in ('js', os.path.join('static', 'js')):
        d = os.path.join(pdir, sub)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith('.js') and not f.endswith('.i18n.bak'):
                    out.append(os.path.join(d, f))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    names = args or sorted(d for d in os.listdir(PLUGINS)
                           if os.path.isdir(os.path.join(PLUGINS, d)))
    total = 0
    per_plugin = {}
    for n in names:
        pdir = os.path.join(PLUGINS, n)
        if not os.path.isdir(pdir):
            continue
        hits = []
        for jf in find_js_files(pdir):
            src = strip_comments(open(jf, encoding='utf-8', errors='replace').read())
            for m in PAT.finditer(src):
                g = m.groups()
                a = g[0] or g[1] or g[2]
                e = g[3]
                c = g[4] or g[5] or g[6]
                a_wrapped = g[2] is not None
                c_wrapped = g[6] is not None
                if boundary_ok(a, c):
                    continue
                line = src[:m.start()].count('\n') + 1
                hits.append((os.path.relpath(jf, ROOT).replace('\\', '/'), line,
                             a, e, c, a_wrapped, c_wrapped))
        if hits:
            per_plugin[n] = len(hits)
            total += len(hits)
            if args:
                print('======== %s (%d) ========' % (n, len(hits)))
                for f, ln, a, e, c, aw, cw in hits:
                    print('  %s:%d' % (f, ln))
                    print('     %s%r + %s + %s%r' % ('pt' if aw else '', a,
                                                     e, 'pt' if cw else '', c))
                print()
    if not args:
        for n, c in sorted(per_plugin.items(), key=lambda x: -x[1]):
            print('%-20s %d' % (n, c))
    print('句中拼接可疑总数:', total)


if __name__ == '__main__':
    main()
