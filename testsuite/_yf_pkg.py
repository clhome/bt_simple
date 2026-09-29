# -*- coding: utf-8 -*-
"""`web/core/yf` 源码读取 —— 同时兼容「单文件」与「拆包」两种形态。

2026-09-29 起 `web/core/yf.py`（3206 行）被拆成 `web/core/yf/` 包
（`paths` / `shell` / `fileio` / `log` / `net` / `textutil` / `security` /
`github` / `system` / `panel` / `misc`）。

有 6 个守卫用例原本按路径 `open('web/core/yf.py')` 读源码并搜函数体，
拆包后必须继续覆盖**同一批代码**（否则守卫会静默失效——文件不存在就报错、
改成 skip 就更糟）。所以统一走本模块：

* :func:`source_text`   —— 拼接全部源码，语义等价于拆包前的单文件文本；
* :func:`module_files`  —— 拆包后各子模块的绝对路径（单文件形态返回 `[yf.py]`）；
* :func:`resolve_text`  —— 把 yf 的路径映射到拼接文本，其它路径正常读取。

两种形态都支持是有意为之：迁移守卫与执行拆包是两步，中间必须保持全绿。
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SINGLE = os.path.join(ROOT, 'web', 'core', 'yf.py')
_PKG_DIR = os.path.join(ROOT, 'web', 'core', 'yf')


def is_packaged():
    """当前是否为拆包形态。"""
    return not os.path.isfile(_SINGLE) and os.path.isdir(_PKG_DIR)


def module_files():
    """yf 的源码文件列表。

    单文件形态 → `[<root>/web/core/yf.py]`；
    拆包形态   → 包内全部 `.py`（`__init__.py` 排在最前，顺序稳定）。
    """
    if os.path.isfile(_SINGLE):
        return [_SINGLE]
    if os.path.isdir(_PKG_DIR):
        names = sorted(n for n in os.listdir(_PKG_DIR) if n.endswith('.py'))
        return [os.path.join(_PKG_DIR, n) for n in names]
    return []


def source_text():
    """全部源码拼接（LF 归一化）。拆包前后语义等价。"""
    parts = []
    for path in module_files():
        with open(path, encoding='utf-8') as fh:
            parts.append(fh.read().replace('\r\n', '\n'))
    return '\n'.join(parts)


def resolve_text(path):
    """读源码；凡是 yf 的路径（含旧的 `web/core/yf.py`）都返回拼接文本。"""
    norm = os.path.abspath(str(path)).replace('\\', '/')
    if norm.endswith('/web/core/yf.py') or '/web/core/yf/' in norm:
        return source_text()
    with open(path, encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')
