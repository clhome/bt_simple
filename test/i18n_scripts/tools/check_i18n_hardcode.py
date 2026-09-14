#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
I-2 hardcode gate: scan web py/js for Chinese not via t()/i18n
"""
import pathlib, re, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
RE_ZH = re.compile(r'[\u4e00-\u9fff]')
def scan_py():
    hits = []
    for f in (ROOT/'web').rglob('*.py'):
        if '__pycache__' in f.parts: continue
        t = f.read_text(encoding='utf-8', errors='ignore')
        if not RE_ZH.search(t): continue
        for i, line in enumerate(t.splitlines(), 1):
            if not RE_ZH.search(line): continue
            s = line.strip()
            if s.startswith('#'): continue
            if any(k in line for k in ('t(', 'returnData', 'returnJson', 'writeLog', 'getInfo(')):
                continue
            hits.append((str(f.relative_to(ROOT)), i, s[:140]))
    return hits
def scan_js():
    hits=[]
    for f in (ROOT/'web/static').rglob('*.js'):
        t=f.read_text(encoding='utf-8', errors='ignore')
        if not RE_ZH.search(t): continue
        for i,line in enumerate(t.splitlines(),1):
            if RE_ZH.search(line) and 't(' not in line and 'i18n' not in line.lower():
                hits.append((str(f.relative_to(ROOT)), i, line.strip()[:140]))
    return hits
if __name__ == '__main__':
    py = scan_py()
    js = scan_js()
    print(f"hardcode py lines: {len(py)} files_with_zh: {len(set(p for p,_,_ in py))} (baseline 104 -> target 0)")
    print(f"hardcode js lines: {len(js)} files_with_zh: {len(set(p for p,_,_ in js))} (baseline 31 -> target 0)")
    for h in py[:20]:
        print('PY', h)
    for h in js[:20]:
        print('JS', h)
    strict = '--strict' in sys.argv
    limit_py = 0 if strict else 500
    limit_js = 0 if strict else 200
    if len(py) > limit_py or len(js) > limit_js:
        print(f"[FAIL] hardcode exceeds limit py>{limit_py} or js>{limit_js}")
        if strict:
            sys.exit(1)
    else:
        print('[PASS] hardcode under limit')
