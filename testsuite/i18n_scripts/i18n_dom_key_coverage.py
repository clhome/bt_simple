# -*- coding: utf-8 -*-
"""
精确统计「由 translatePluginDOM 兜底翻译的 DOM 文本/属性」是否在 zh-CN.json 有键。
严格复刻 web/static/app/i18n.js 的白名单选择器与排除规则，消除误报。

白名单（i18n.js:474-513）：
  A 菜单 : .bt-w-menu p / .man-menu-sub span / .setting_ul .setting_ul_li span
  B 属性 : input|textarea[placeholder] / span|a|label[title] / .table_config[title]
  C 文本 : th / .tname / .c9 / select option / button / .btn / h3 / h4 / h5
           .alert* / .lead / .plugin-con p / td>span / td>a.btlink / td>label
           div[style*=color:#cf1322] / div[style*=font-weight]
           .pma-info-header / .ollama-info-header
排除：C 组节点若含子元素 div/p/ul/ol/table/input/select/textarea/.line/.bt-w-menu/.soft-man-con 则跳过

用法:
    python i18n_dom_key_coverage.py            # 汇总表
    python i18n_dom_key_coverage.py mongodb    # 单插件明细
"""
import os
import re
import sys
import json
import glob
from html.parser import HTMLParser

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
PLUGINS = os.path.join(ROOT, 'plugins')
CJK = re.compile(r'[\u4e00-\u9fa5]')
SKIP = re.compile(r'^[\s\W_]*$')

EXCLUDE_CLASSES = {'line', 'bt-w-menu', 'soft-man-con'}
EXCLUDE_TAGS = {'div', 'p', 'ul', 'ol', 'table', 'input', 'select', 'textarea'}


class Node(object):
    __slots__ = ('tag', 'attrs', 'children', 'text', 'parent')

    def __init__(self, tag, attrs, parent):
        self.tag = tag
        self.attrs = attrs
        self.children = []
        self.text = []
        self.parent = parent

    @property
    def cls(self):
        return set((self.attrs.get('class') or '').split())

    def has_excluded_child(self):
        for c in self.children:
            if c.tag in EXCLUDE_TAGS:
                return True
            if c.cls & EXCLUDE_CLASSES:
                return True
        return False

    def plain_text(self):
        """忽略 i / span.glyphicon 图标后的文本"""
        parts = []
        for c in self.children:
            if c.tag == 'i':
                continue
            if c.tag == 'span' and 'glyphicon' in c.cls:
                continue
            parts.append(c.all_text())
        return ''.join(self.text + parts)

    def all_text(self):
        parts = list(self.text)
        for c in self.children:
            parts.append(c.all_text())
        return ''.join(parts)


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('#root', {}, None)
        self.cur = self.root
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
            return
        if self.skip:
            return
        n = Node(tag, dict(attrs), self.cur)
        self.cur.children.append(n)
        if tag not in ('br', 'img', 'input', 'hr', 'meta', 'link'):
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        if self.skip or tag in ('script', 'style'):
            return
        n = Node(tag, dict(attrs), self.cur)
        self.cur.children.append(n)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            if self.skip:
                self.skip -= 1
            return
        if self.skip:
            return
        # 回溯到匹配祖先
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        if self.skip:
            return
        self.cur.text.append(data)


def is_group_c(n):
    tag, cl = n.tag, n.cls
    ptag = n.parent.tag if n.parent else ''
    pcl = n.parent.cls if n.parent else set()
    if tag in ('th', 'h3', 'h4', 'h5', 'button', 'option'):
        return True
    if tag == 'span' and (cl & {'tname', 'c9', 'pma-info-header', 'ollama-info-header'}):
        return True
    if tag == 'span' and ptag == 'td':
        return True
    if tag == 'a' and ('btlink' in cl or ptag == 'td'):
        return True
    if tag == 'label' and ptag == 'td':
        return True
    if tag == 'div' and (cl & {'alert', 'alert-title', 'alert-heading'}):
        return True
    if tag == 'p' and ('lead' in cl or 'plugin-con' in pcl):
        return True
    if cl & {'tname', 'c9', 'pma-info-header', 'ollama-info-header'}:
        return True
    style = (n.attrs.get('style') or '').replace(' ', '')
    if tag == 'div' and ('#cf1322' in style or 'font-weight' in style):
        return True
    return False


def is_group_a(n):
    if n.tag == 'p' and n.parent and 'bt-w-menu' in n.parent.cls:
        return True
    if n.tag == 'span' and n.parent and (n.parent.cls & {'man-menu-sub'} or
                                         'setting_ul_li' in n.parent.cls):
        return True
    return False


def walk(n, attr_hits, text_hits):
    for c in n.children:
        walk(c, attr_hits, text_hits)
    # 属性位
    ph = n.attrs.get('placeholder')
    if ph and n.tag in ('input', 'textarea') and CJK.search(ph):
        attr_hits.append(ph.strip())
    ti = n.attrs.get('title')
    if ti and (n.tag in ('span', 'a', 'label') or 'table_config' in n.cls) and CJK.search(ti):
        attr_hits.append(ti.strip())
    # 文本位
    if is_group_a(n) or is_group_c(n):
        if n.has_excluded_child():
            return
        t = n.plain_text().strip()
        if t and CJK.search(t):
            text_hits.append(t)


def find_html(plugin):
    d = os.path.join(PLUGINS, plugin)
    out = []
    for pat in ('index.html', '*.html', 'static/html/*.html', 'static/*.html',
                'templates/*.html', 'views/*.html'):
        out += glob.glob(os.path.join(d, pat))
    return sorted(set(out))


# ---------------------------------------------------------------------------
# 全量模式：translatePluginDOM 的「通用文本节点兜底」覆盖域
#
# i18n.js 的 1.3 规则用 TreeWalker 扫**所有文本节点**（父节点非 skip 标签即处理），
# 1.1 规则用 `[placeholder], [title]` 通配**任意标签**。因此新的不变量是：
#   凡是静态 HTML 里「含中文的文本节点 / placeholder / title」，语言包都必须有键，
#   否则该处界面在非中文语言下仍是中文（且门禁不会红 —— 静默失效）。
# 与上面白名单模式互补：白名单模式守「已知位置」，本模式守「全部位置」。
# ---------------------------------------------------------------------------
SKIP_TAGS_FULL = {'script', 'style', 'noscript', 'iframe', 'textarea', 'title'}


def collect_full(n, out):
    for c in n.children:
        collect_full(c, out)
    if n.tag in SKIP_TAGS_FULL:
        return
    # 逐个文本节点判定（与 TreeWalker 语义一致，不跨节点合并）
    for chunk in n.text:
        t = chunk.strip()
        if t and CJK.search(t):
            out.add(t)
    for attr in ('placeholder', 'title'):
        v = n.attrs.get(attr)
        if v and CJK.search(v):
            out.add(v.strip())


def collect_from_html(src):
    """从一段 HTML 文本里收集「含中文的文本节点 / placeholder / title」。"""
    tb = TreeBuilder()
    try:
        tb.feed(src)
    except Exception:
        pass
    out = set()
    collect_full(tb.root, out)
    return out


def analyze_full(plugin):
    """返回 (含中文的文本节点/属性值总数, 语言包无键的清单)"""
    lp = os.path.join(PLUGINS, plugin, 'lang', 'zh-CN.json')
    if not os.path.isfile(lp):
        return None
    with open(lp, encoding='utf-8') as f:
        keys = set(json.load(f).keys())
    dom = set()
    for fp in find_html(plugin):
        with open(fp, encoding='utf-8', errors='replace') as _f:
            dom |= collect_from_html(_f.read())
    dom = {x for x in dom if not SKIP.match(x)}
    miss = sorted(x for x in dom if x not in keys)
    return len(dom), miss


def analyze(plugin):
    lp = os.path.join(PLUGINS, plugin, 'lang', 'zh-CN.json')
    if not os.path.isfile(lp):
        return None
    with open(lp, encoding='utf-8') as f:
        keys = set(json.load(f).keys())
    dom = set()
    for fp in find_html(plugin):
        with open(fp, encoding='utf-8', errors='replace') as _f:
            src = _f.read()
        tb = TreeBuilder()
        try:
            tb.feed(src)
        except Exception:
            pass
        ah, th = [], []
        walk(tb.root, ah, th)
        for s in ah + th:
            if not SKIP.match(s):
                dom.add(s)
    miss = sorted(x for x in dom if x not in keys)
    return len(dom), miss


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    full = '--full' in sys.argv
    names = args or sorted(
        d for d in os.listdir(PLUGINS)
        if os.path.isdir(os.path.join(PLUGINS, d))
        and os.path.isfile(os.path.join(PLUGINS, d, 'lang', 'zh-CN.json'))
    )
    fn = analyze_full if full else analyze
    rows = []
    for n in names:
        r = fn(n)
        if r:
            rows.append((n, r[0], r[1]))
    rows.sort(key=lambda r: -len(r[2]))
    print('%-18s %8s %8s' % ('plugin', 'dom_zh', 'no_key'))
    print('-' * 38)
    tot = tm = 0
    for n, c, miss in rows:
        tot += c
        tm += len(miss)
        if miss:
            print('%-18s %8d %8d' % (n, c, len(miss)))
    print('-' * 38)
    print('%-18s %8d %8d' % ('TOTAL(%d)' % len(rows), tot, tm))
    if args or full:
        for n, c, miss in rows:
            if miss:
                print('\n== %s (%d) ==' % (n, len(miss)))
                for v in miss:
                    print('   %r' % v)
    return 0


if __name__ == '__main__':
    sys.exit(main())
