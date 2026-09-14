#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阻断翻译文件携带 HTML 滑坡：CI / pre-commit 拦截
允许白名单仅用于渐进迁移期，默认 0 白名单即失败
"""
import json, re, sys, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[2] / "web" / "static" / "language"
HTML_RE = re.compile(r"<[a-zA-Z][^>]*>")
# 渐进迁移白名单：留空即视为已完成
ALLOWLIST: set[str] = set()

fails = []
for p in ROOT.rglob("*.json"):
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[error] {p}: {e}")
        fails.append(str(p))
        continue
    stack = [(data, "")]
    while stack:
        cur, prefix = stack.pop()
        if not isinstance(cur, dict):
            continue
        for k, v in cur.items():
            key = f"{prefix}{k}"
            if isinstance(v, dict):
                stack.append((v, key + "."))
            elif isinstance(v, str) and HTML_RE.search(v):
                rel = f"{p.relative_to(ROOT)}:{key}"
                if rel in ALLOWLIST or key in ALLOWLIST or p.name in ALLOWLIST:
                    continue
                fails.append(rel)
                safe = v[:90].replace(chr(10),' ').encode('utf-8','replace').decode('utf-8','replace')
                print(f"[FAIL] {rel} -> {safe}")

if fails:
    print(f"\n共 {len(fails)} 处翻译仍含 HTML。修复指引：HTML 抽至 web/static/app/tpl/*，翻译仅保留纯文本。")
    sys.exit(1)
else:
    print("i18n HTML check passed: 全部翻译为纯文本")
