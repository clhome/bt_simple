# -*- coding: utf-8 -*-
"""语言包载体导出器：以 ``lan.js`` 为**单一真源**，派生全部 ``.json`` 后端载体。

## 为什么需要它

`web/static/language/<lang>/` 下原本有两套**独立生成**的译文：

    前端真源  lan.js                  走 innerHTML，保留 <p>/<br>
    后端真源  public.json + 9 分片    红线要求「值不得含 HTML」

两条链各读自己的历史基线（`test/restore_and_build_high_quality_i18n.py` 里
`final_sections` 用旧 lan.js、`final_template` 用旧 template.json），于是同一
`(section, key)` 在两侧长期分叉 —— 实测 **2161 条不一致**，且两侧都有机翻 glue。
详见 `文档/语言包双载体分歧审计与收敛方案.md`。

本工具把「两套真源」收敛成「一套真源 + 一个派生」：``.json`` 一律由 ``lan.js``
重新算出。派生规则就是原先手搓、且做错的那一步：

    <p> / <br> 是【分隔符】  →  换成空格，而不是删空

删空会把 `手動安裝` + `<p>` + `安裝命令` 粘成 `安裝安裝命令`（已出货过的缺陷）。

## 用法

    python scripts/tools/export_lang_carriers.py              # 干跑（默认），只报告
    python scripts/tools/export_lang_carriers.py --apply      # 真正写盘
    python scripts/tools/export_lang_carriers.py --report-md out.md

退出码：0 = 派生结果与磁盘一致（或已成功 apply）；1 = 存在不一致（干跑）或丢失键。
"""
import argparse
import io
import json
import os
import re
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    '..', '..'))
LANG_DIR = os.path.join(ROOT, 'web', 'static', 'language')

LANGUAGES = ('zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it')

# ---- 分片布局（与 web/core/i18n.py::_SECTION_TO_MENU 必须逐字一致） ----
MENU_SECTIONS = {
    "index":    ["index", "dashboard", "menu", "auth", "login", "close", "admin", "task"],
    "site":     ["site", "database", "ftp"],
    "files":    ["files", "file", "upload"],
    "security": ["firewall", "ssh"],
    "crontab":  ["crontab"],
    "monitor":  ["control", "system"],
    "logs":     ["logs"],
    "soft":     ["soft", "plugins", "plugin", "jdk", "python_yf"],
    "setting":  ["config", "setting", "common", "public", "utils"],
}
MENU_NAMES = ("index", "site", "files", "security", "crontab", "monitor",
              "logs", "soft", "setting")

# 分片**顶层**的扁平键（后端 _lookup_message 的扁平键路径靠它命中）。
# 与 test/i18n_scripts/tools/merge_template_by_menu.py::MENU_FLAT 一致。
MENU_FLAT = {
    "index": ["yufeng_panel_btsimple", "quzhou_yufeng_technology_co",
              "quzhou_yufeng_technology_yftec", "proudly_presented_by",
              "retrieving_panel_resource_usage", "yufeng_panel_current_server",
              "memory", "failed_to_retrieve_resources", "loading_instructions",
              "all_rights_reserved_admin", "public_auto_str_127",
              "public_auto_str_128", "public_auto_str_143"],
    "files": ["search_content", "previous", "next", "replace_with",
              "replace_current", "replace_all", "replace", "all_1", "sky", "day"],
    "crontab": ["day_limit", "day_none", "day_stock", "day_workday",
                "day_holiday", "no_limit", "stock_day", "work_day", "holiday",
                "date_limit", "start_time", "end_time", "execute_time"],
}

SECTION_TO_MENU = {s: m for m, secs in MENU_SECTIONS.items() for s in secs}

# 扁平键的取值来源 section：优先「与菜单同名的 section」，否则 public。
FLAT_SOURCE = {"index": "public", "files": "public", "crontab": "crontab"}
# 个别扁平键在首选 section 里不存在，显式指定来源（见 --report 的 FLAT 段）
FLAT_KEY_SOURCE = {"sky": "crontab", "day": "crontab"}

_TAG_RE = re.compile(r'<[^>]*>')
# 「值里有没有标签」的判据。**故意比 `_TAG_RE` 严格**：
#   - `<[^>]*>` 会把 `value < 10 and x > 5` 这类数学比较误判成标签；
#   - 这里要求 `<` 后紧跟字母 / `/`（闭合标签 `</ul>`）/ `!`（注释、DOCTYPE）/ `?`，
#     既不误判比较式，又能覆盖全部真标签形态。
_ANY_TAG_RE = re.compile(r'<[a-zA-Z/!?][^>]*>')
_HTML_RE = re.compile(r'<[a-zA-Z][^>]*>')
_RUNSP_RE = re.compile(r'[ \t]+')

_HEX = set('0123456789abcdefABCDEF')
_JS_ESC = {'"': '"', "'": "'", '\\': '\\', '/': '/', 'b': '\b', 'f': '\f',
           'n': '\n', 'r': '\r', 't': '\t', 'v': '\v', '0': '\0'}


def _js_unescape(body):
    """按 **JS** 语义反转义（不能用 json.loads）。

    `it/lan.js` 里存在 `\\ t`（反斜杠+空格）这类**非法 JSON 转义**：
    JS 宽容地把它当空格，`json.loads` 直接抛 `Invalid \\escape`。
    实测 `it` 语言包有 83 处，因此必须自己实现 JS 转义语义。
    """
    out = []
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if c != '\\':
            out.append(c)
            i += 1
            continue
        i += 1
        if i >= n:
            out.append('\\')
            break
        e = body[i]
        if e == 'u':
            hexs = body[i + 1:i + 5]
            if len(hexs) == 4 and all(h in _HEX for h in hexs):
                cp = int(hexs, 16)
                i += 5
                if 0xD800 <= cp <= 0xDBFF and body[i:i + 2] == '\\u':
                    lo_h = body[i + 2:i + 6]
                    if len(lo_h) == 4 and all(h in _HEX for h in lo_h):
                        lo = int(lo_h, 16)
                        if 0xDC00 <= lo <= 0xDFFF:
                            cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                            i += 6
                out.append(chr(cp))
                continue
            out.append('u')
            i += 1
            continue
        if e == 'x':
            hexs = body[i + 1:i + 3]
            if len(hexs) == 2 and all(h in _HEX for h in hexs):
                out.append(chr(int(hexs, 16)))
                i += 3
                continue
            out.append('x')
            i += 1
            continue
        out.append(_JS_ESC.get(e, e))
        i += 1
    return ''.join(out)


# =====================================================================
# 1) lan.js 解析器
# =====================================================================
# lan.js 由 `format_js_obj()` 机器生成，形态规整，但**含嵌套 dict**
# （如 lan.plugins.apache = {title, ps}），所以必须真解析，不能用正则拍平 ——
# 拍平会把内层键提升到父层，导致 `plugins.apache.title` 被判为「不存在」。
class LanJsError(ValueError):
    pass


class _Parser(object):
    def __init__(self, src):
        self.s = src
        self.i = 0

    def fail(self, msg):
        line = self.s.count('\n', 0, self.i) + 1
        raise LanJsError('%s (第 %d 行, 偏移 %d)' % (msg, line, self.i))

    def ws(self):
        s, n = self.s, len(self.s)
        while self.i < n and s[self.i] in ' \t\r\n':
            self.i += 1

    def string(self):
        if self.s[self.i] != '"':
            self.fail('期望字符串字面量')
        start = self.i
        self.i += 1
        while True:
            if self.i >= len(self.s):
                self.fail('字符串未闭合')
            c = self.s[self.i]
            if c == '\\':
                self.i += 2
                continue
            if c == '"':
                self.i += 1
                break
            if c == '\n':
                self.fail('字符串内出现裸换行')
            self.i += 1
        lit = self.s[start:self.i]
        try:
            return json.loads(lit)
        except ValueError:
            # 兼容 JS 特有的宽松转义（如 `\ `、`\'`、`\v`）
            return _js_unescape(lit[1:-1])

    def block(self):
        """从当前位置吃掉一个 `{...}` 代码块，返回块内文本（跳过字符串）。"""
        if self.s[self.i] != '{':
            self.fail('期望 "{"')
        depth = 0
        start = self.i
        while self.i < len(self.s):
            c = self.s[self.i]
            if c == '"':
                self.string()
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    self.i += 1
                    return self.s[start:self.i]
            self.i += 1
        self.fail('代码块未闭合')

    def value(self):
        self.ws()
        c = self.s[self.i]
        if c == '"':
            return self.string()
        if c == '{':
            return self.obj()
        if self.s.startswith('function', self.i):
            self.i += len('function')
            self.ws()
            # 跳过形参列表 `(key,args)`
            if self.s[self.i] == '(':
                depth = 0
                while self.i < len(self.s):
                    ch = self.s[self.i]
                    if ch == '(':
                        depth += 1
                    elif ch == ')':
                        depth -= 1
                        if depth == 0:
                            self.i += 1
                            break
                    self.i += 1
            self.ws()
            return _Fn(self.block())
        self.fail('不支持的取值形态 %r' % c)

    def obj(self):
        if self.s[self.i] != '{':
            self.fail('期望 "{"')
        self.i += 1
        out = {}
        self.ws()
        if self.s[self.i] == '}':
            self.i += 1
            return out
        while True:
            self.ws()
            k = self.string()
            self.ws()
            if self.s[self.i] != ':':
                self.fail('键 %r 后期望 ":"' % k)
            self.i += 1
            out[k] = self.value()
            self.ws()
            c = self.s[self.i]
            if c == ',':
                self.i += 1
                # lan.js 里存在尾随逗号（`...,\n\t\t}`），必须容忍
                self.ws()
                if self.s[self.i] == '}':
                    self.i += 1
                    return out
                continue
            if c == '}':
                self.i += 1
                return out
            self.fail('对象内期望 "," 或 "}"')


class _Fn(object):
    """lan.js 里唯一的函数：`"get":function(key,args){ var msgs = {...} ... }`"""

    def __init__(self, body):
        self.body = body
        self.msgs = {}
        m = re.search(r'var\s+msgs\s*=\s*\{', body)
        if m:
            p = _Parser(body)
            p.i = m.end() - 1
            self.msgs = p.obj()


def parse_lan_js(path):
    """返回 (sections, get_msgs)。sections 保留嵌套结构。"""
    with io.open(path, encoding='utf-8') as fp:
        src = fp.read()
    m = re.search(r'\bvar\s+lan\s*=\s*\{', src)
    if not m:
        raise LanJsError('%s: 找不到 `var lan = {`' % path)
    p = _Parser(src)
    p.i = m.end() - 1
    top = p.obj()
    get_msgs = {}
    sections = {}
    for k, v in top.items():
        if k == 'get':
            if isinstance(v, _Fn):
                get_msgs = v.msgs
        elif isinstance(v, dict):
            sections[k] = v
        else:
            raise LanJsError('%s: section %r 不是对象' % (path, k))
    return sections, get_msgs


# =====================================================================
# 1b) 行级结构定位（文本外科编辑用；**一处定义**，勿在别处复制）
# =====================================================================
# 实测 lan.js 缩进规律（生成器存在 off-by-one，但全文件一致）：
#
#     \t"name": {            ← section 头      (1 tab)
#     \t\t\t"k": "v",        ← section 内键     (3 tab)
#     \t\t\t"nested": {      ← 嵌套块头        (3 tab)
#     \t\t\t\t"k": "v"       ← 嵌套块内键      (4 tab)
#     \t\t\t},               ← 嵌套块闭合      (3 tab，与块头同缩进)
#     \t\t},                 ← section 闭合    (2 tab，比块头多 1)
#
# 所以 section 闭合是 **2 tab**、块闭合是 **与块头同缩进** —— 两者不能混用。
SEC_CLOSE = re.compile(r'^\t\t\}[,]?$')


def find_section_span(lines, sec):
    """返回 section 的 (头行下标, 闭合行下标)；找不到返回 (None, None)。"""
    header = '\t%s: {' % json.dumps(sec, ensure_ascii=False)
    hdr = None
    for i, ln in enumerate(lines):
        if ln == header:
            hdr = i
            break
    if hdr is None:
        return None, None
    for j in range(hdr + 1, len(lines)):
        if SEC_CLOSE.match(lines[j]):
            return hdr, j
    return hdr, None


def find_nested_block_span(lines, open_idx):
    """给定 `\\t*N"key": {` 行下标，返回 (open_idx, close_idx)。

    仅用于 **嵌套块**（块头与闭合同缩进）。section 请用 `find_section_span()`。
    """
    m = re.match(r'^(\t+)"', lines[open_idx])
    if not m or not lines[open_idx].rstrip().endswith('{'):
        raise LanJsError('不是嵌套块开头: %r' % lines[open_idx])
    indent = m.group(1)
    if len(indent) < 3:
        raise LanJsError('缩进 <3 tab 的行不是嵌套块（section 请用 find_section_span）: %r'
                         % lines[open_idx])
    close_pat = re.compile(r'^%s\}[,]?$' % re.escape(indent))
    for j in range(open_idx + 1, len(lines)):
        if close_pat.match(lines[j]):
            return open_idx, j
    raise LanJsError('嵌套块未闭合: %r' % lines[open_idx])


def find_key_line(lines, sec, key, lo=None, hi=None):
    """在 section 范围内定位**恰好一行** `\\t\\t\\t"key": ...`，返回行下标。

    多个/零个命中都抛错 —— 静默改错行的代价远高于报错。

    注意 `lan.js` 的冒号后**不统一**：多数是 `": "`，但也有 `":"`（无空格）。
    所以只按 `"key":` 匹配，不把空格算进前缀。

    键名含点（`site.py_msg_config_error`）时按**字面**匹配，不当作嵌套路径 ——
    嵌套请用 `locate_key()`。
    """
    if lo is None or hi is None:
        lo, hi = find_section_span(lines, sec)
        if lo is None:
            raise LanJsError('找不到 section %r' % sec)
    lit = '\t\t\t%s:' % json.dumps(key, ensure_ascii=False)
    hits = [i for i in range(lo + 1, hi) if lines[i].startswith(lit)]
    if len(hits) != 1:
        raise LanJsError('section %r 内键 %r 命中 %d 行（要求恰好 1 行）'
                         % (sec, key, len(hits)))
    return hits[0]


def locate_key(lines, sec, dotted):
    """定位**嵌套键**的行下标。

    `dotted` 用点分隔嵌套层级：`supervisor.ps` ⇒ `lan.<sec>.supervisor.ps`。
    `lan.js` 里确实有嵌套（`plugins.apache = {title, ps}`、
    `plugins.supervisor = {title, ps}`），所以不能只按字面找键名。
    """
    hdr, close = find_section_span(lines, sec)
    if hdr is None:
        raise LanJsError('找不到 section %r' % sec)
    parts = dotted.split('.')
    lo, hi, indent = hdr, close, 2          # section 内键缩进 = 3 tab
    for p in parts[:-1]:
        lit = '\t' * (indent + 1) + json.dumps(p, ensure_ascii=False) + ': {'
        open_idx = None
        for i in range(lo + 1, hi):
            if lines[i].startswith(lit):
                open_idx = i
                break
        if open_idx is None:
            raise LanJsError('section %r 内找不到嵌套块 %r' % (sec, p))
        b_open, b_close = find_nested_block_span(lines, open_idx)
        lo, hi, indent = b_open, b_close, indent + 1
    lit = '\t' * (indent + 1) + json.dumps(parts[-1], ensure_ascii=False) + ':'
    hits = [i for i in range(lo + 1, hi) if lines[i].startswith(lit)]
    if len(hits) != 1:
        raise LanJsError('section %r 内嵌套键 %r 命中 %d 行（要求恰好 1 行）'
                         % (sec, dotted, len(hits)))
    return hits[0]


def get_nested(sections, sec, dotted):
    """按嵌套路径取值；不是字符串叶子则返回 None。"""
    cur = sections.get(sec)
    for p in dotted.split('.'):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur if isinstance(cur, str) else None


def resolve_key_path(sections, sec, dotted):
    """消解 `dotted` 的语义，返回 `(mode, value)`；解析不出返回 `(None, None)`。

    **带点的键名有两种互不相同的语义，必须靠解析后的结构来消解**：

    - `literal`：键名**本身就含点**。`public` 段有 3 个这样的键
      （`site.py_msg_config_error` / `site.py_msg_error_output` /
      `firewall.py_msg_special_port`），它们是**扁平**键，不是嵌套。
    - `nested`：点表示**嵌套层级**。`plugins` 段有 76 个嵌套块
      （`plugins.apache.ps`、`plugins.supervisor.ps` …）。

    规则：**字面优先**（更具体），字面不中再按层级找。
    实测两侧无冲突：`public` 段没有嵌套块，`plugins` 段没有字面带点的键。
    """
    node = sections.get(sec)
    if isinstance(node, dict) and isinstance(node.get(dotted), str):
        return 'literal', node[dotted]
    cur = node
    for p in dotted.split('.'):
        if not isinstance(cur, dict) or p not in cur:
            return None, None
        cur = cur[p]
    if isinstance(cur, str):
        return 'nested', cur
    return None, None


def key_present(sections, sec, dotted):
    """lan.js 里该逻辑键是否已存在（**字面 或 嵌套 任一形态**）。"""
    mode, _v = resolve_key_path(sections, sec, dotted)
    return mode is not None


def key_line_index(lines, sec, dotted, mode):
    """按 `resolve_key_path()` 给出的 mode 定位键行。"""
    if mode == 'literal':
        return find_key_line(lines, sec, dotted)
    return locate_key(lines, sec, dotted)


def removed_breakdown(fn, old, new, sections):
    """把「`old` 有、`new` 没有」的路径拆成三类，返回 `(真丢失, 去重, 不可表达)`。

    只有**真丢失**才是回归 —— 那是「载体有覆盖、派生后没了」。另两类是**有意移除**：

    1. **去重**：键名含点且派生侧同位置能嵌套取到
       （`plugins.apache.ps` 的扁平写法，见 `redundant_flat_keys()`）。
       实测每语言 76 条（38 个插件 × `.ps`/`.title`），是**唯一的**常态去重来源。
    2. **不可表达**：lan.js 里有这个键，但派生侧确实产不出它。
       历史实例：`crontab.clearfix_plan_ptb_typename` —— lan.js 是 `'</ul>'`，
       而磁盘载体存的是**键名当值**的垃圾占位符。**现在这一类应为 0**：
       `to_carrier_obj()` 已改为「空串保留」，`'</ul>'` 会派生为 `''` 而不是消失，
       于是它走「值变更」通道（`'clearfix_plan_ptb_typename'` → `''`，是修复）。
       本分支保留作安全网：一旦将来又有键真的产不出来，它会被单独计数而非混进真丢失。
    """
    red = redundant_flat_keys(old, new)
    lost, dedup, unrep = [], [], []
    for path, o, n in diff_flat(old, new):
        if n is not None or is_blank(o):
            continue
        if path in red:
            dedup.append(path)
            continue
        try:
            sec, key = logical_key(fn, path, sections)
        except LanJsError:
            lost.append(path)
            continue
        if key_present(sections, sec, key):
            unrep.append(path)
        else:
            lost.append(path)
    return lost, dedup, unrep


def _nested_get(obj, dotted):
    cur = obj
    for p in dotted.split('.'):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def redundant_flat_keys(old, new, prefix=''):
    """`old`（磁盘载体）里「键名含点、且 `new`（派生结果）同位置能**嵌套**取到」
    的键路径集合 —— 这些是**同一逻辑键的第二种写法**，属**去重**，不是丢失。

    实测 `template.<menu>.json` 的 `plugins` 段每语言有 76 个这样的键
    （`apache.ps` / `apache.title` × 38 个插件块），而 `lan.js` 里只有**嵌套**形态。

    为什么删掉扁平写法不算回归：

    - 后端 `_lookup_message('plugins.apache.ps')` 走**深层点号遍历**照样命中
      （`web/core/i18n.py` 第 284~293 行）；
    - 前端 `t()` 是**纯深遍历**，从不读扁平形态
      （`web/static/app/i18n.js` 第 294~301 行）。

    注意判据是「派生侧能嵌套取到」，**不是**「两侧取值相等」——
    另有一批键两种写法取值本就不同（那是**取值分歧**，由派生按 lan.js 收敛，
    并会在嵌套路径上被记成「值变更」，不应被这里吞掉）。
    """
    out = set()
    if not isinstance(old, dict):
        return out
    for k, v in old.items():
        p = '%s.%s' % (prefix, k) if prefix else k
        if isinstance(v, dict):
            out |= redundant_flat_keys(v, new.get(k) if isinstance(new, dict) else None, p)
        elif isinstance(v, str) and '.' in k and isinstance(new, dict):
            if _nested_get(new, k) is not None:
                out.add(p)
    return out


_KEYLINE_RE = re.compile(r'^(\t+"(?:[^"\\]|\\.)*":)([ \t]*)')


def set_key_line(lines, idx, key, value):
    """把 `lines[idx]` 的值换成 `value`，**保留原键字面量、缩进与冒号后空白**、
    保留尾随逗号。"""
    m = _KEYLINE_RE.match(lines[idx])
    if not m:
        raise LanJsError('无法解析键行: %r' % lines[idx])
    had_comma = lines[idx].rstrip().endswith(',')
    lines[idx] = '%s%s%s%s' % (m.group(1), m.group(2),
                               json.dumps(value, ensure_ascii=False),
                               ',' if had_comma else '')


def logical_key(fn, path, sections=None):
    """载体叶子路径 → 逻辑键 (section, key)。

    三种形态：

    1. **`public.json`**：它的顶层路径**整体就是键名**，哪怕键名里带点。
       实例：`public.json` 有个键叫 `site.py_msg_config_error` ——
       若按点切分会被误判成 `site` 段的 `py_msg_config_error`。
       逻辑上它属于 `public` 段（后端 `_lookup_message` 第 1 步
       就是用**扁平键**命中 `public.json`）。
    2. 分片里的 `section.key`（如 `public.auto_refresh`）→ 切分首个点。
    3. **分片顶层**的扁平键（如 `template.crontab.json` 的 `date_limit`）→
       必须按 `build_carriers` 自己的解析规则回溯到来源 section，不能硬编码。
       实例：`FLAT_SOURCE['crontab']='crontab'` ⇒ `('crontab', 'date_limit')`；
       而 `FLAT_SOURCE['index']='public'` ⇒ 归到 `public` 段。

    `sections` 省略时只支持形态 1、2。
    """
    if fn == 'public.json':
        return 'public', path
    parts = path.split('.')
    if len(parts) >= 2:
        return parts[0], '.'.join(parts[1:])
    if sections is not None and fn.startswith('template.') and fn.endswith('.json'):
        menu = fn[len('template.'):-len('.json')]
        if menu in MENU_NAMES:
            src, _val = _find_flat(sections, path, menu)
            if src:
                return src, path
    raise LanJsError('无法把载体顶层扁平键回溯到 section: %s %s' % (fn, path))


# =====================================================================
# 2) 派生规则
# =====================================================================
def to_carrier(value):
    """lan.js 值 → .json 载体值。**两条分支，规则完全不同。**

    ## 分支 1：值里没有标签 ⇒ 本来就是纯文本 ⇒ **原样通过**

    一个字节都不动 —— 不做 strip、不折叠空白。首尾空白是**文案的一部分**：

        实例（真实回归）：`en files.total_of_directory_and`
            lan.js = 'Dirs: {1}, Files: {2}, Size: '   ← 尾空格后直接接数量
            旧实现无条件 .strip() ⇒ 'Dirs: {1}, Files: {2}, Size:'
            ⇒ `testsuite/test_files_i18n_layout.py` 当场红。

        同类的还有 `index.client_time = '客户端时间: '`、`index.auto_str_13 = ' 核心'`
        等 365 处。它们的空白是排版，不是脏数据。

    ## 分支 2：值里有标签 ⇒ 这是 HTML 片段 ⇒ 剥标签 + 归一空白

    `lan.js` 走 `innerHTML`，`<p>`/`<br>` 是**分隔符**；而 .json 载体有
    「值不得含 HTML」红线。所以标签必须换成**空格**，而不是删空 ——
    删空会把 `手動安裝` + `<p>` + `安裝命令` 粘成 `安裝安裝命令`
    （已出货过的真实缺陷，`test_lang_pack_integrity.py` 守着）。

    片段两端的空白是**布局缩进**（`*_auto_str_*` 里大量 `\\t\\t\\t`），不是文案，
    所以这一支要 strip。

    ## 判据选择

    「有没有标签」用 `_ANY_TAG_RE`（比剥标签用的 `_TAG_RE` 严格）：
    既不把 `a < b` 误判成标签，又覆盖 `</ul>` / `<!-- -->` / `<!DOCTYPE>`。
    于是**两个分支的产物都不含 HTML**：分支 1 由判据本身保证
    （无标签 ⇒ 后端红线 `<[a-zA-Z][^>]*>` 更不可能命中），分支 2 由剥标签保证。

    ## 规则取舍的依据

    拿 HEAD 的载体当基准实测四种候选（29472 个叶子）：

        条件 strip（按首尾空白来源）  一致 23875 / 不一致 1469
        完全不 strip                  一致 23522 / 不一致 1822
        无条件 strip（旧实现）         一致 23584 / 不一致 1760
        本实现（无标签则原样）          一致 23933 / 不一致 1411   ← 最优
    """
    if not _ANY_TAG_RE.search(value):
        return value
    v = _RUNSP_RE.sub(' ', _TAG_RE.sub(' ', value))
    return v.strip()


def to_carrier_obj(obj):
    """lan.js 子树 → 载体子树。**1:1 镜像，什么都不丢。**

    ## 为什么「空值」一个都不能丢（这里连踩两次坑）

    早先的写法丢掉「转换后为空」的键（空串 / 纯空白 / 空 dict），
    两处都是**真实回归**，各由一条既有测试当场抓出来：

    **① 丢空串 → `global-key-parity` 假红 3 项**（`scripts/verify_i18n.py`）：

        en 缺 index.L3 / index.auto_str_117 / index.second
        de 缺 index.L3
        it 缺 site.site_auto_str_15

    成因：同一键在 zh-CN 有内容（`index.L3 = '个'`）、在 en/de 是空串，
    空串是**叶子**（`leaf_paths()` 把它算进去），键一丢就少一个叶子路径。

    **② 丢空 dict → `test_public_auto_str_translated` 假红**
    （`testsuite/test_all_foreign_languages_complete.py`）：
    它断言 `public.json` 里 `public_auto_str_*` 前缀的键**多于 100 个**，
    而其中 45 个正是 `{}` 占位（并且该用例专门写了 `elif isinstance(v, dict)`
    分支来遍历它们）⇒ `{}` 是**契约的一部分**，不是噪音。

    结论：键集的对称性与完整性由**源**（`lan.js`）负责，载体无权按值决定键的去留。
    空值本身还是「待补译」的真实信号，藏起来反而看不见：en/de 的 `index.L3`
    载体旧值是机翻垃圾（`'one'` / `'ein'`），而 `L3` 在 zh-CN 是**量词**「个」，
    英文正确取值本就该是空串（`{数量} {N1}` ⇒ "5 websites"）。

    ## 顺带的硬性质

    本函数保证「派生值不含 HTML」：`to_carrier()` 删掉所有成对标签 `<...>` 后，
    残留的 `<` 后面不可能再有 `>`，所以后端红线用的 `<[a-zA-Z][^>]*>` 永不命中。
    """
    out = {}
    for k, v in obj.items():
        if isinstance(v, dict):
            out[k] = to_carrier_obj(v)
        elif isinstance(v, str):
            out[k] = to_carrier(v)
        else:
            # lan.js 里出现非字符串叶子时立刻报错，而不是静默产出垃圾
            raise LanJsError('lan.js 出现非字符串叶子: %r' % (v,))
    return out


def _find_flat(sections, key, menu):
    """按 首选 section → 全量唯一命中 的顺序解析扁平键。"""
    src = FLAT_KEY_SOURCE.get(key) or FLAT_SOURCE.get(menu, 'public')
    sec = sections.get(src) or {}
    if isinstance(sec.get(key), str):
        return src, sec[key]
    hits = [(s, o[key]) for s, o in sections.items()
            if isinstance(o.get(key), str)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return None, None
    return None, None


def build_carriers(lang):
    """返回 {文件名: 对象}（含 9 分片 + public.json + template.json 垫片）。"""
    sections, _get = parse_lan_js(os.path.join(LANG_DIR, lang, 'lan.js'))

    buckets = {}
    for menu in MENU_NAMES:
        bucket = {}
        for sec in MENU_SECTIONS[menu]:
            if sec in sections:
                conv = to_carrier_obj(sections[sec])
                if conv:
                    bucket[sec] = conv
        buckets[menu] = bucket

    unresolved = []
    for menu, keys in MENU_FLAT.items():
        for k in keys:
            _src, val = _find_flat(sections, k, menu)
            if val is None:
                unresolved.append('%s.%s' % (menu, k))
                continue
            buckets[menu][k] = to_carrier(val)

    out = {}
    for menu in MENU_NAMES:
        out['template.%s.json' % menu] = buckets[menu]

    public = dict(buckets['setting'].get('public') or {})
    out['public.json'] = public

    shim = {}
    for menu in MENU_NAMES:
        shim.update(out['template.%s.json' % menu])
    out['template.json'] = shim

    return out, unresolved


# =====================================================================
# 3) 与磁盘比对 / 写入
# =====================================================================
def load_disk(lang):
    d = os.path.join(LANG_DIR, lang)
    out = {}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.json'):
            continue
        try:
            with io.open(os.path.join(d, fn), encoding='utf-8') as fp:
                out[fn] = json.load(fp)
        except ValueError:
            out[fn] = None
    return out


def diff_flat(a, b, prefix=''):
    """递归比对，返回 [(键路径, 旧值, 新值)]。"""
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            p = '%s.%s' % (prefix, k) if prefix else k
            if k not in a:
                out.append((p, None, b[k]))
            elif k not in b:
                out.append((p, a[k], None))
            else:
                out.extend(diff_flat(a[k], b[k], p))
    elif a != b:
        out.append((prefix, a, b))
    return out


def is_blank(v):
    """内容为空的条目：空 dict / 空串 / 纯空白。

    用于判断**磁盘侧旧值**算不算有效覆盖（`removed_breakdown` 用它把
    「旧值本来就是空的」排除出「真丢失」）。

    注意：这不等于「派生时会丢弃」。派生规则是**空 dict 丢、空串留**
    （见 `to_carrier_obj()`）—— 空串是叶子，丢掉会破坏
    `verify_i18n.py::global-key-parity`。所以本函数只用于**旧值**的成色判断。
    """
    if v is None:
        return True
    if isinstance(v, dict):
        return not v
    if isinstance(v, str):
        return not v.strip()
    return False


def main():
    ap = argparse.ArgumentParser(description='从 lan.js 派生 .json 语言包载体')
    ap.add_argument('--apply', action='store_true', help='真正写盘（默认干跑）')
    ap.add_argument('--allow-loss', action='store_true',
                    help='允许丢弃「磁盘有、lan.js 派生不出」的键')
    ap.add_argument('--report-md', metavar='PATH', help='输出 markdown 报告')
    ap.add_argument('--lang', action='append', choices=list(LANGUAGES),
                    help='只处理指定语言（可重复）')
    args = ap.parse_args()

    langs = args.lang or list(LANGUAGES)
    md = []
    rc = 0
    total_changed = total_new = total_lost = total_dedup = total_unrep = 0

    for lang in langs:
        sections, _g = parse_lan_js(os.path.join(LANG_DIR, lang, 'lan.js'))
        carriers, unresolved = build_carriers(lang)
        disk = load_disk(lang)
        md.append('## %s' % lang)
        if unresolved:
            rc = 1
            md.append('')
            md.append('**扁平键无法解析（必须修 `FLAT_KEY_SOURCE`）：** %s'
                      % ', '.join(unresolved))
            print('[%s] 扁平键无法解析: %s' % (lang, unresolved))

        for fn in sorted(carriers):
            new = carriers[fn]
            old = disk.get(fn)
            if old is None:
                md.append('- `%s` 磁盘缺失/非法，将新建（%d 条）' % (fn, _count(new)))
                total_new += _count(new)
                if args.apply:
                    _write(lang, fn, new)
                continue
            d = diff_flat(old, new)
            lost_paths, dedup_paths, unrep_paths = removed_breakdown(
                fn, old, new, sections)
            changed = [x for x in d if x[1] is not None and x[2] is not None]
            added = [x for x in d if x[1] is None]
            total_changed += len(changed)
            total_new += len(added)
            total_lost += len(lost_paths)
            total_dedup += len(dedup_paths)
            total_unrep += len(unrep_paths)
            if lost_paths and not args.allow_loss:
                rc = 1
            if d:
                md.append('- `%s`：变更 %d / 新增 %d / **丢失 %d** / 去重 %d / 不可表达 %d'
                          % (fn, len(changed), len(added), len(lost_paths),
                             len(dedup_paths), len(unrep_paths)))
                for p in lost_paths[:5]:
                    md.append('    - 丢失 `%s`' % p)
                for p, o, n in changed[:3]:
                    md.append('    - `%s`' % p)
                    md.append('        - 旧 `%r`' % (_s(o),))
                    md.append('        - 新 `%r`' % (_s(n),))
            if args.apply:
                _write(lang, fn, new)
        print('[%s] 处理完成' % lang)

    print()
    print('=' * 68)
    print('汇总：值变更 %d / 新增 %d / 丢失 %d / 去重 %d / 不可表达 %d'
          % (total_changed, total_new, total_lost, total_dedup, total_unrep))
    print('  去重     = 载体里「键名含点且派生侧嵌套可达」的冗余写法，派生不再产出')
    print('  不可表达 = lan.js 侧是纯标记值（如 </ul>），.json 载体表达不了，必然丢弃')
    print('模式：%s' % ('--apply 已写盘' if args.apply else '干跑（未写盘）'))
    if args.report_md:
        with io.open(args.report_md, 'w', encoding='utf-8') as fp:
            fp.write('\n'.join(md) + '\n')
        print('报告：%s' % args.report_md)
    return rc


def _count(o):
    if isinstance(o, dict):
        return sum(_count(v) for v in o.values())
    return 1


def _s(v):
    if v is None:
        return None
    return v if len(v) <= 120 else v[:117] + '...'


def _write(lang, fn, obj):
    path = os.path.join(LANG_DIR, lang, fn)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(obj, fp, ensure_ascii=False, indent=2)
        fp.write('\n')


if __name__ == '__main__':
    sys.exit(main())
