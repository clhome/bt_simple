# -*- coding: utf-8 -*-
"""
死键检测：语言包中「源码里已无任何引用」的键。

判定：把插件下所有源码文件（.js/.html/.py/.tpl/.conf，排除 lang/、__pycache__、
versions/、*.i18n.bak）拼成一个文本，键字面量出现即视为「被引用」。
另兼容源码中把 \n 写成转义序列的情形。

用法:
    python i18n_dead_keys.py            # 全库汇总
    python i18n_dead_keys.py mariadb    # 单插件明细
    python i18n_dead_keys.py --apply    # 删除死键（六语言同步）
"""
import io
import os
import re
import sys
import json

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
PLUGINS = os.path.join(ROOT, 'plugins')
SKIP_DIRS = {'__pycache__', 'versions', 'lang', '.git', 'node_modules'}
# 二进制/媒体类不参与文本扫描
SKIP_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.woff', '.woff2',
            '.ttf', '.eot', '.zip', '.gz', '.tar', '.bz2', '.7z', '.rar',
            '.pyc', '.so', '.dll', '.exe', '.mp4', '.webp', '.pdf')
# 框架侧（共享代码）可能按插件字典查表，这些文件里出现过的键一律保留
FRAMEWORK_FILES = []
for _d in (os.path.join(ROOT, 'web', 'static', 'app'),
           os.path.join(ROOT, 'web', 'admin'),
           os.path.join(ROOT, 'web', 'core')):
    for _root, _dirs, _files in os.walk(_d):
        _dirs[:] = [x for x in _dirs if x not in ('__pycache__', 'node_modules')]
        for _f in _files:
            if _f.endswith(('.js', '.html', '.py')):
                FRAMEWORK_FILES.append(os.path.join(_root, _f))

_FW_CACHE = None


def framework_text():
    global _FW_CACHE
    if _FW_CACHE is None:
        parts = []
        for p in FRAMEWORK_FILES:
            try:
                with open(p, encoding='utf-8', errors='replace') as _f:
                    parts.append(_f.read())
            except Exception:
                pass
        _FW_CACHE = '\n'.join(parts)
    return _FW_CACHE


def source_text(pdir):
    parts = []
    for root, dirs, files in os.walk(pdir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith('.i18n.bak') or fn.lower().endswith(SKIP_EXT):
                continue
            p = os.path.join(root, fn)
            try:
                with open(p, encoding='utf-8', errors='replace') as _f:
                    parts.append(_f.read())
            except Exception:
                pass
    return '\n'.join(parts)


# 引用判定：键必须「整串」出现——要么被引号完整包裹（字符串字面量），
# 要么独占一个 HTML 文本节点。不能用子串匹配，否则键 `上行速度：` 会被
# `上行速度：{1}/秒` 误判为「仍被引用」。
_PAT_CACHE = {}


def _variants(k):
    """源码里可能出现的等价写法：转义序列 / HTML 实体。"""
    out = [k]
    esc = k.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    if esc != k:
        out.append(esc)
    if '&' in k:
        out.append(k.replace('&', '&amp;'))
    return out


def _pattern(v):
    p = _PAT_CACHE.get(v)
    if p is None:
        e = re.escape(v)
        alts = [
            # ① 完整字符串字面量：'键' / "键"
            r"['\"]" + e + r"['\"]",
            # ② HTML 文本节点：>键<  /  >键'（片段以键结尾，如 '…</span> 手动诊断与自愈'）
            r">\s*" + e + r"\s*(?:<|['\"`])",
        ]
        # ③ 冒号前缀契约：前端 YfI18n.translateAny() 对「键 + 变量」型后端消息
        #    取首个冒号（含）作为候选键，因此 `'操作失败: ' + e` 里的 `操作失败:`
        #    在运行时**确实会被查表**。此时键在源码里只作为字面量前缀出现，
        #    后面紧跟空白。仅对以冒号结尾的键启用该分支——否则键 `上行速度：`
        #    会被 `上行速度：{1}/秒` 误判（其后是 `{` 而非空白，故本分支不命中，
        #    但为稳妥仍限定冒号结尾）。
        if v.endswith(':') or v.endswith('：'):
            alts.append(r"['\"]" + e + r"\s")
        p = re.compile('(?:' + '|'.join(alts) + ')')
        _PAT_CACHE[v] = p
    return p


def _referenced(text, k):
    return any(_pattern(v).search(text) for v in _variants(k))


def source_text(pdir):
    parts = []
    for root, dirs, files in os.walk(pdir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith('.i18n.bak') or fn.lower().endswith(SKIP_EXT):
                continue
            p = os.path.join(root, fn)
            try:
                with open(p, encoding='utf-8', errors='replace') as _f:
                    parts.append(_f.read())
            except Exception:
                pass
    return '\n'.join(parts)


def dead_keys(name):
    pdir = os.path.join(PLUGINS, name)
    lp = os.path.join(pdir, 'lang', 'zh-CN.json')
    if not os.path.isfile(lp):
        return []
    with open(lp, encoding='utf-8') as _f:
        keys = list(json.load(_f).keys())
    txt = source_text(pdir)
    fw = framework_text()
    return [k for k in keys if not (_referenced(txt, k) or _referenced(fw, k))]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    apply_ = '--apply' in sys.argv
    names = args or sorted(
        d for d in os.listdir(PLUGINS)
        if os.path.isdir(os.path.join(PLUGINS, d))
        and os.path.isfile(os.path.join(PLUGINS, d, 'lang', 'zh-CN.json'))
    )
    if apply_:
        from i18n_langlib import del_key
    total = 0
    for n in names:
        dk = dead_keys(n)
        if not dk:
            continue
        total += len(dk)
        print('======== %s (%d) ========' % (n, len(dk)))
        for k in dk:
            print('   %r' % k)
        if apply_:
            for k in dk:
                del_key(n, k)
            print('   -> 已删除')
    print('死键总数:', total)
    return 0


if __name__ == '__main__':
    sys.exit(main())
