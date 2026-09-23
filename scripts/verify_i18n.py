# -*- coding: utf-8 -*-
"""
i18n 静态校验（CI 门禁）

自包含单文件，仅依赖标准库。用于把 i18n 治理红线从「文档约定」变成「可执行门禁」。

覆盖检查：
  1. plugin-key-parity      插件六语言键集完全一致
  2. global-key-parity      全局语言包六语言叶子路径完全一致
  3. no-html                译文不含 HTML（白名单除外）
  4. dirty-keys             语言包无「代码型脏键」
  5. pt-argc                无多参 pt()/_t() 调用（括号配对，覆盖动态首参）
  6. msgtpl-pt              所有 msgTpl( 调用的首参必须含 pt(
  7. no-zero-placeholder    无 {0} 占位符（msgTpl 从 {1} 起替换）
  8. backend-msg-prefix     后端消息的「可翻译前缀」不含 HTML
  9. backend-msg-key        后端中文消息能查到语言包键（冒号前缀契约）
 10. nested-layer-hook      插件二级弹窗（嵌套 layer）i18n 钩子已安装

设计约束：**自包含**。检测逻辑与自证夹具全部内嵌，只依赖标准库。
`test/` 被 `.gitignore` 忽略，本脚本不得依赖其中任何文件——否则 CI 里
自证会静默跳过，退化成「永远全绿」的假门禁。

用法:
    python scripts/verify_i18n.py              # 全部检查
    python scripts/verify_i18n.py --verbose    # 附失败明细
    python scripts/verify_i18n.py --check pt-argc
    python scripts/verify_i18n.py --list       # 列出全部检查名
    python scripts/verify_i18n.py --self-test  # 校验检测器本身（已知答案）

退出码: 0 = 全部通过；1 = 存在失败
"""
import argparse
import json
import os
import re
import sys

# 终端编码兜底（Windows GBK 控制台直接跑时避免 UnicodeEncodeError）
try:
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = __import__('io').TextIOWrapper(
            sys.stdout.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_ROOT = os.path.join(WORKSPACE, 'plugins')
GLOBAL_LANG_ROOT = os.path.join(WORKSPACE, 'web', 'static', 'language')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
DEFAULT_LANG = 'zh-CN'

# ---------------------------------------------------------------------------
# 白名单
# ---------------------------------------------------------------------------

# 有意保留 HTML 的键（点号路径）。
# index.reboot_panel_wait_msg 含 <span id="restart-countdown"> 面板重启倒计时锚点，
# web/static/app/index.js 依赖该 id，test/test_reboot_modal_i18n_style.py 专门断言其存在。
# 注意：Python 侧 t() 会 strip_html，故该键只允许前端调用。
HTML_ALLOWLIST = {
    'index.reboot_panel_wait_msg',
}

# 生成脚本残留的空占位键前缀（public_auto_str_NN），P2 阶段清理
EMPTY_PLACEHOLDER_PREFIX = 'public_auto_str_'

# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

SKIP_DIRS = {'__pycache__', 'versions', 'lang', '.git', 'node_modules'}
SRC_EXT = ('.js', '.html', '.htm')

HTML_RE = re.compile(
    r'<(?:br|p|div|span|b|strong|i|a|ul|ol|li|code|small|em|table|tr|td|th|h[1-6])'
    r'\b[^>]*>', re.I)
CJK_RE = re.compile(r'[\u4e00-\u9fff]')


def plugin_names():
    """插件定义：含 lang/zh-CN.json 的目录（自动同步，杜绝硬编码漂移）"""
    if not os.path.isdir(PLUGIN_ROOT):
        return []
    return sorted(
        d for d in os.listdir(PLUGIN_ROOT)
        if os.path.isfile(os.path.join(PLUGIN_ROOT, d, 'lang', DEFAULT_LANG + '.json'))
    )


def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def lang_path(name, lang):
    return os.path.join(PLUGIN_ROOT, name, 'lang', lang + '.json')


def iter_source_files(root):
    """递归产出插件源码文件（.js/.html/.htm），跳过 lang/versions/__pycache__"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith('.i18n.bak'):
                continue
            if fn.endswith(SRC_EXT):
                yield os.path.join(dirpath, fn)


def read_text(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


def leaf_paths(obj, prefix=''):
    """递归展开嵌套 dict，产出 (点号路径, 值)"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaf_paths(v, prefix + '.' + k if prefix else k)
    else:
        yield prefix, obj


# ---------------------------------------------------------------------------
# 检查 1：插件六语言键集一致
# ---------------------------------------------------------------------------

def check_plugin_key_parity(ctx):
    problems = []
    for name in plugin_names():
        base = None
        for lang in LANGS:
            p = lang_path(name, lang)
            if not os.path.isfile(p):
                problems.append('%s/%s.json 缺失' % (name, lang))
                continue
            try:
                keys = set(read_json(p).keys())
            except Exception as e:
                problems.append('%s/%s.json 解析失败: %s' % (name, lang, e))
                continue
            if lang == DEFAULT_LANG:
                base = keys
                continue
            if base is not None:
                diff = (base - keys) | (keys - base)
                if diff:
                    problems.append('%s/%s 与 zh-CN 键集差异 %d: %s'
                                    % (name, lang, len(diff), sorted(diff)[:3]))
    return problems


# ---------------------------------------------------------------------------
# 检查 2：全局语言包六语言叶子路径一致
# ---------------------------------------------------------------------------

def _global_leaf_map(lang):
    """返回 {文件名::叶子路径: 值}"""
    d = os.path.join(GLOBAL_LANG_ROOT, lang)
    out = {}
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.json'):
            continue
        try:
            data = read_json(os.path.join(d, fn))
        except Exception:
            continue
        for path, val in leaf_paths(data):
            out[fn + '::' + path] = val
    return out


def check_global_key_parity(ctx):
    base = _global_leaf_map(DEFAULT_LANG)
    if not base:
        return ['全局语言包目录不存在或为空: %s' % GLOBAL_LANG_ROOT]
    problems = []
    for lang in LANGS:
        if lang == DEFAULT_LANG:
            continue
        cur = _global_leaf_map(lang)
        missing = sorted(set(base) - set(cur))
        extra = sorted(set(cur) - set(base))
        if missing:
            problems.append('%s 缺少 %d 个叶子键，如: %s'
                            % (lang, len(missing), missing[:5]))
        if extra:
            problems.append('%s 多出 %d 个叶子键，如: %s'
                            % (lang, len(extra), extra[:5]))
    return problems


# ---------------------------------------------------------------------------
# 检查 3：译文不含 HTML
# ---------------------------------------------------------------------------

def check_no_html(ctx):
    problems = []
    # 插件包：值不含 HTML
    for name in plugin_names():
        for lang in LANGS:
            p = lang_path(name, lang)
            if not os.path.isfile(p):
                continue
            try:
                data = read_json(p)
            except Exception:
                continue
            for k, v in data.items():
                if isinstance(v, str) and HTML_RE.search(v):
                    problems.append('%s/%s %r -> %r' % (name, lang, k[:40], v[:70]))
    # 全局包：叶子值不含 HTML（白名单除外）
    for lang in LANGS:
        d = os.path.join(GLOBAL_LANG_ROOT, lang)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.json'):
                continue
            try:
                data = read_json(os.path.join(d, fn))
            except Exception:
                continue
            for path, v in leaf_paths(data):
                if isinstance(v, str) and HTML_RE.search(v) and path not in HTML_ALLOWLIST:
                    problems.append('global/%s %s::%s -> %r' % (lang, fn, path, v[:70]))
    return problems


# ---------------------------------------------------------------------------
# 检查 4：语言包无脏键
# ---------------------------------------------------------------------------

# HTML 实体（&lt; &gt; &amp; …）中的分号不是 CSS 声明结尾，需先剥离再判 CSS
ENTITY_RE = re.compile(r'&(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);')

DIRTY_RULES = [
    ('HTML标签', re.compile(r'<[a-zA-Z/][^>]*>')),
    ('JS拼接片段', re.compile(r"'\s*\+|\+\s*'")),
    ('JS多参残留', re.compile(r"'\s*,\s*'")),
    ('JS调用', re.compile(r'\bpt\(|\bmsgTpl\(|\$\(|\blayer\.|\.each\(|function\s*\(')),
    ('属性赋值', re.compile(r"\b(class|placeholder|title|style|href|onclick|onchange|"
                        r"value|type|colspan|rowspan|id|src)\s*=\s*['\"]")),
    ('转义序列', re.compile(r'\\n|\\r|\\t|\\u[0-9a-fA-F]{4}')),
    ('CSS片段', re.compile(r'[a-z-]{3,}\s*:\s*[^;{]+;')),
    # 首尾引号：仅当整个键被同一对引号包起来才算提取残留
    ('首尾引号', re.compile(r"^(['\"]).*\1$")),
    ('纯标点', re.compile(r'^[\s\W_]+$')),
    ('变量拼接', re.compile(r"'\s*\+\s*[A-Za-z_$]|[A-Za-z_$0-9\]\)]\s*\+\s*'")),
]


def classify_dirty(key):
    plain = ENTITY_RE.sub('', key)
    for name, pat in DIRTY_RULES:
        target = plain if name == 'CSS片段' else key
        if pat.search(target):
            return name
    return None


def check_dirty_keys(ctx):
    problems = []
    for name in plugin_names():
        p = lang_path(name, DEFAULT_LANG)
        try:
            data = read_json(p)
        except Exception:
            continue
        for k in data:
            cat = classify_dirty(k)
            if cat:
                problems.append('%s [%s] %r' % (name, cat, k[:70]))
    return problems


# ---------------------------------------------------------------------------
# 检查 5：无多参 pt() / _t()  —— 词法扫描 + 括号配对 + 顶层逗号计数
# ---------------------------------------------------------------------------

REGEX_PREV_KEYWORDS = {
    'return', 'typeof', 'instanceof', 'in', 'of', 'new', 'delete', 'void',
    'throw', 'case', 'do', 'else', 'yield', 'await',
}
IDENT_CHARS = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$')
TARGET_FUNCS = {'pt', '_t'}


def _skip_string(src, i, quote):
    i += 1
    n = len(src)
    while i < n:
        c = src[i]
        if c == '\\':
            i += 2
            continue
        if c == quote:
            return i + 1
        i += 1
    return i


def _skip_template(src, i):
    i += 1
    n = len(src)
    while i < n:
        c = src[i]
        if c == '\\':
            i += 2
            continue
        if c == '`':
            return i + 1
        if c == '$' and i + 1 < n and src[i + 1] == '{':
            i = _skip_balanced(src, i + 1, '{', '}')
            continue
        i += 1
    return i


def _skip_balanced(src, i, open_c, close_c):
    depth = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c == '\\':
            i += 2
            continue
        if c in ('"', "'"):
            i = _skip_string(src, i, c)
            continue
        if c == '`':
            i = _skip_template(src, i)
            continue
        if c == open_c:
            depth += 1
        elif c == close_c:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _skip_regex(src, i):
    i += 1
    n = len(src)
    in_class = False
    while i < n:
        c = src[i]
        if c == '\\':
            i += 2
            continue
        if c == '\n':
            break
        if c == '[':
            in_class = True
        elif c == ']':
            in_class = False
        elif c == '/' and not in_class:
            i += 1
            break
        i += 1
    while i < n and src[i] in 'gimsuy':
        i += 1
    return i


def _match_call(src, open_idx):
    """从 '(' 做括号配对，返回 (结束下标, 顶层逗号位置列表)；不匹配返回 None"""
    depth = 0
    i = open_idx
    commas = []
    prev_was_value = False
    n = len(src)
    while i < n:
        c = src[i]
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            while i < n and src[i] != '\n':
                i += 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            i += 2
            while i < n and not (src[i] == '*' and i + 1 < n and src[i + 1] == '/'):
                i += 1
            i += 2
            continue
        if c == '/' and not prev_was_value:
            i = _skip_regex(src, i)
            prev_was_value = True
            continue
        if c in ('"', "'"):
            i = _skip_string(src, i, c)
            prev_was_value = True
            continue
        if c == '`':
            i = _skip_template(src, i)
            prev_was_value = True
            continue
        if c in '([{':
            depth += 1
            prev_was_value = False
            i += 1
            continue
        if c in ')]}':
            depth -= 1
            if depth == 0:
                return (i, commas) if c == ')' else None
            prev_was_value = True
            i += 1
            continue
        if c == ',' and depth == 1:
            commas.append(i)
        prev_was_value = c in IDENT_CHARS or c in ')]'
        i += 1
    return None


def _scan_pt_argc(src):
    """返回 [(行号, 函数名, 参数个数, 片段)]"""
    hits = []
    i = 0
    line = 1
    prev_token = ''
    prev_was_value = False
    n = len(src)

    while i < n:
        c = src[i]
        if c == '\n':
            line += 1
            i += 1
            continue
        if c in ' \t\r':
            i += 1
            continue

        if c == '/' and i + 1 < n and src[i + 1] == '/':
            while i < n and src[i] != '\n':
                i += 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            i += 2
            while i < n and not (src[i] == '*' and i + 1 < n and src[i + 1] == '/'):
                if src[i] == '\n':
                    line += 1
                i += 1
            i += 2
            continue
        if c == '/' and not prev_was_value:
            i = _skip_regex(src, i)
            prev_token, prev_was_value = '/re/', True
            continue
        if c == '`':
            i = _skip_template(src, i)
            prev_token, prev_was_value = '`tpl`', True
            continue
        if c in ('"', "'"):
            i = _skip_string(src, i, c)
            prev_token, prev_was_value = 'str', True
            continue

        if c in IDENT_CHARS:
            j = i
            while j < n and src[j] in IDENT_CHARS:
                j += 1
            word = src[i:j]
            start_line = line

            # 目标函数名，且前面不是 '.'（排除 obj.pt(...)）
            if word in TARGET_FUNCS and prev_token != '.':
                k = j
                while True:
                    while k < n and src[k] in ' \t\r\n':
                        if src[k] == '\n':
                            line += 1
                        k += 1
                    if k < n and src[k] == '/' and k + 1 < n and src[k + 1] == '/':
                        while k < n and src[k] != '\n':
                            k += 1
                        continue
                    if k < n and src[k] == '/' and k + 1 < n and src[k + 1] == '*':
                        k += 2
                        while k < n and not (src[k] == '*' and k + 1 < n and src[k + 1] == '/'):
                            if src[k] == '\n':
                                line += 1
                            k += 1
                        k += 2
                        continue
                    break
                if k < n and src[k] == '(':
                    res = _match_call(src, k)
                    if res and res[1]:
                        end = res[0]
                        snip = re.sub(r'\s+', ' ', src[max(0, i - 30):min(n, end + 1)]).strip()
                        hits.append((start_line, word, len(res[1]) + 1, snip[:130]))

            prev_token = word
            prev_was_value = word not in REGEX_PREV_KEYWORDS
            i = j
            continue

        prev_token = c
        prev_was_value = c in ')]'
        i += 1

    return hits


def check_pt_argc(ctx):
    problems = []
    for name in plugin_names():
        for path in iter_source_files(os.path.join(PLUGIN_ROOT, name)):
            rel = os.path.relpath(path, WORKSPACE).replace(os.sep, '/')
            for line, fn, argc, snip in _scan_pt_argc(read_text(path)):
                problems.append('%s:%d  %s() 收到 %d 个参数（只接受 1 个）  %s'
                                % (rel, line, fn, argc, snip))
    return problems


# ---------------------------------------------------------------------------
# 检查 6：所有 msgTpl( 的首参必须含 pt(
# ---------------------------------------------------------------------------

def check_msgtpl_pt(ctx):
    problems = []
    pat = re.compile(r'(?<![\w$.])msgTpl\s*\(')
    for name in plugin_names():
        for path in iter_source_files(os.path.join(PLUGIN_ROOT, name)):
            src = read_text(path)
            rel = os.path.relpath(path, WORKSPACE).replace(os.sep, '/')
            for m in pat.finditer(src):
                open_idx = src.index('(', m.start())
                res = _match_call(src, open_idx)
                if not res:
                    continue
                end, commas = res
                # 首参 = 左括号后到第一个顶层逗号（或右括号）之间
                first_end = commas[0] if commas else end
                first_arg = src[open_idx + 1:first_end]
                if 'pt(' not in first_arg:
                    line = src.count('\n', 0, m.start()) + 1
                    snip = re.sub(r'\s+', ' ', first_arg).strip()[:90]
                    problems.append('%s:%d  msgTpl 首参缺少 pt(): %s' % (rel, line, snip))
    return problems


# ---------------------------------------------------------------------------
# 检查 7：无 {0} 占位符
# ---------------------------------------------------------------------------

def check_no_zero_placeholder(ctx):
    problems = []
    # 语言包键
    for name in plugin_names():
        p = lang_path(name, DEFAULT_LANG)
        try:
            data = read_json(p)
        except Exception:
            continue
        for k in data:
            if '{0}' in k:
                problems.append('语言包键 %s %r' % (name, k[:70]))
    # 源码中的 pt('…{0}…')
    pat = re.compile(r"""(?<![\w$.])(?:pt|_t)\s*\(\s*(['"])((?:[^'"\\]|\\.)*)\1""")
    for name in plugin_names():
        for path in iter_source_files(os.path.join(PLUGIN_ROOT, name)):
            src = read_text(path)
            rel = os.path.relpath(path, WORKSPACE).replace(os.sep, '/')
            for m in pat.finditer(src):
                if '{0}' in m.group(2):
                    line = src.count('\n', 0, m.start()) + 1
                    problems.append('%s:%d  %r' % (rel, line, m.group(2)[:70]))
    return problems


# ---------------------------------------------------------------------------
# 检查 8：后端消息前缀必须是纯文本
# ---------------------------------------------------------------------------

# 后端消息契约：
#   前端 YfI18n.translateAny() 对 returnJson 消息做「首个冒号（含）前缀匹配」，
#   因此「可翻译前缀」= 消息首个 : / ： 之前的全部内容，它会被当成语言包键。
#   两条硬性要求：
#     ① 前缀不得含 HTML（否则键含 HTML，违反「译文禁含 HTML」红线）；
#     ② 消息含中文时，前缀也必须含中文 —— 否则中文落在冒号之后，
#        前缀匹配取到的是 'ERROR:' 这类无意义键，中文永远翻不出来。
#   HTML 与技术命令（pip install ...）应留在冒号之后的动态部分。
RETURNJSON_RE = re.compile(r'\breturnJson\s*\(')
HTML_TAG_RE = re.compile(r'<[a-zA-Z/][^>]*>')
CJK_RE = re.compile(r'[\u4e00-\u9fff]')


def _skip_py_string(src, i):
    """跳过 Python 字符串字面量（含三引号），返回闭合引号之后的下标。"""
    n = len(src)
    if src[i:i + 3] in ('"""', "'''"):
        q = src[i:i + 3]
        end = src.find(q, i + 3)
        return (end + 3) if end >= 0 else n
    q = src[i]
    i += 1
    while i < n:
        c = src[i]
        if c == '\\':
            i += 2
            continue
        if c == q:
            return i + 1
        i += 1
    return i


def _py_arg2_leading_literal(src, open_idx):
    """给定 '(' 的下标，返回第二个实参的首个字符串字面量文本（未转义解析）。

    找不到字面量（如第二个实参是 str(e) 这类表达式）时返回 None。
    """
    n = len(src)
    i = open_idx + 1
    depth = 0
    # 跳过第一个实参，定位顶层逗号
    while i < n:
        c = src[i]
        if c in '\'"':
            i = _skip_py_string(src, i)
            continue
        if c in '([{':
            depth += 1
        elif c in ')]}':
            if depth == 0:
                return None
            depth -= 1
        elif c == ',' and depth == 0:
            i += 1
            break
        i += 1
    # 第二个实参：跳过空白与可选的 f/r 前缀
    while i < n and src[i] in ' \t\r\n':
        i += 1
    if i < n and src[i] in 'fFrRbBuU' and i + 1 < n and src[i + 1] in '\'"':
        i += 1
    if i >= n or src[i] not in '\'"':
        return None
    j = _skip_py_string(src, i)
    if src[i:i + 3] in ('"""', "'''"):
        return src[i + 3:j - 3]
    return src[i + 1:j - 1]


def _scan_backend_msg_prefix(src):
    """扫描单份 Python 源码，返回 [(行号, 原因, 前缀文本)] 形式的违规列表。"""
    out = []
    for m in RETURNJSON_RE.finditer(src):
        lit = _py_arg2_leading_literal(src, m.end() - 1)
        if not lit:
            continue
        # 可翻译前缀 = 首个冒号（含）之前
        c1, c2 = lit.find(':'), lit.find('：')
        ci = min(x for x in (c1, c2) if x >= 0) if (c1 >= 0 or c2 >= 0) else -1
        prefix = lit[:ci + 1] if ci >= 0 else lit
        line = src.count('\n', 0, m.start()) + 1
        if HTML_TAG_RE.search(prefix):
            out.append((line, '前缀含 HTML', prefix))
        elif CJK_RE.search(lit) and not CJK_RE.search(prefix):
            out.append((line, '中文落在冒号之后', prefix))
    return out


def check_backend_msg_prefix(ctx):
    problems = []
    for name in plugin_names():
        path = os.path.join(PLUGIN_ROOT, name, 'index.py')
        if not os.path.isfile(path):
            continue
        src = read_text(path)
        rel = os.path.relpath(path, WORKSPACE).replace(os.sep, '/')
        for line, why, prefix in _scan_backend_msg_prefix(src):
            problems.append('%s:%d  %s: %r' % (rel, line, why, prefix[:80]))
    return problems


# ---------------------------------------------------------------------------
# 检查 9：后端中文消息必须能在语言包中查到键
# ---------------------------------------------------------------------------

# 与前端 YfI18n.translateAny() 同构的三级匹配：
#   ① 整串精确匹配（trim 后）
#   ② 冒号前缀匹配：取消息首个 : / ：（含）作为候选键
#   ③ 尾随空格容错：候选键 = 前缀 + rest 的前导空白（无空白时补一个空格）
# 三条都不命中 => 运行时原样显示中文（外语界面漏翻）。
# 运行时限制：冒号位置必须满足 0 < ci <= 40（见 i18n.js 的 `ci > 0 && ci <= 40`）。
PREFIX_MAX_POS = 40

# 已确认由「前端模式表」而非语言包承接的消息（必须写明理由）。
# 守卫会反向验证这些例外「仍然未命中」——一旦补了键，例外即失效，需删除本条。
# 注意：键一律用「首尾空白已剥离」的形式（与 lit.strip() 的查找口径一致）。
BACKEND_MSG_KEY_EXCEPTIONS = {
    ('fail2ban', 'IP格式错误 {}'):
        'fail2ban/js/fail2ban.js 的 f2bMsg() 模式表按「空格 + 参数」承接；'
        '刻意不用冒号分隔，以便与裸消息「IP格式错误」区分',
    ('op_waf', '同步成功，当前共'):
        'op_waf/js/op_waf.js 的 wafMsg() 模式表承接整句（含尾部感叹号与条数）',
}


def _backend_msg_resolves(lit, keys):
    """复刻 translateAny 的匹配规则，判断后端消息字面量能否查到键。"""
    key = lit.strip()
    if not key:
        return True
    if key in keys:                      # ① 精确
        return True
    c1, c2 = key.find(':'), key.find('：')
    ci = -1
    if c1 >= 0 and (c2 < 0 or c1 < c2):
        ci = c1
    elif c2 >= 0:
        ci = c2
    if not (0 < ci <= PREFIX_MAX_POS):   # 无冒号 / 位置越界 -> 无法前缀匹配
        return False
    prefix, rest = key[:ci + 1], key[ci + 1:]
    if prefix in keys:                   # ② 冒号前缀
        return True
    m = re.match(r'\s*', rest)
    sp = m.group(0) if m else ''
    return (prefix + (sp or ' ')) in keys  # ③ 尾随空格容错


def _scan_backend_msg_keys(src, keys):
    """扫描单份 Python 源码，返回 [(行号, 字面量)] 形式的「查不到键」消息列表。"""
    out = []
    for m in RETURNJSON_RE.finditer(src):
        lit = _py_arg2_leading_literal(src, m.end() - 1)
        if not lit or not CJK_RE.search(lit):
            continue
        if _backend_msg_resolves(lit, keys):
            continue
        out.append((src.count('\n', 0, m.start()) + 1, lit))
    return out


def _load_zh_keys(plugin):
    path = os.path.join(PLUGIN_ROOT, plugin, 'lang', 'zh-CN.json')
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as fh:
        return set(json.load(fh))


def check_backend_msg_key(ctx):
    problems = []
    for name in plugin_names():
        path = os.path.join(PLUGIN_ROOT, name, 'index.py')
        keys = _load_zh_keys(name)
        if not (os.path.isfile(path) and keys is not None):
            continue
        rel = os.path.relpath(path, WORKSPACE).replace(os.sep, '/')
        for line, lit in _scan_backend_msg_keys(read_text(path), keys):
            if (name, lit.strip()) in BACKEND_MSG_KEY_EXCEPTIONS:
                continue
            problems.append('%s:%d  语言包查不到键（外语界面会漏翻）: %r'
                            % (rel, line, lit[:70]))

    # 例外失效检查：补了键之后例外必须删除，否则例外列表会无限膨胀、失去意义
    for (name, lit), why in sorted(BACKEND_MSG_KEY_EXCEPTIONS.items()):
        keys = _load_zh_keys(name)
        if keys is None:
            problems.append('例外指向不存在的插件语言包: %s' % name)
            continue
        if _backend_msg_resolves(lit, keys):
            problems.append('例外已失效（%s 的 %r 现已能查到键），请删除该例外：%s'
                            % (name, lit, why))
    return problems


# ---------------------------------------------------------------------------
# 检查 10：插件二级弹窗（嵌套 layer）i18n 钩子
# ---------------------------------------------------------------------------

# 插件常在自己的弹窗内用 layer.open / layer.alert / layer.confirm 打开二级窗口，
# 这些窗口挂在 document.body 下，不在 translatePluginDOM 主容器内（主监听器够不着）。
# soft.js 的 installPluginLayerTranslation() 在插件存续期间改写 layer.open，把二级
# 窗口也交给同一插件字典翻译 —— 一处修复覆盖全部插件。本检查锁死该钩子不被删除。
NESTED_LAYER_HOOK_MARKERS = [
    'function installPluginLayerTranslation(',
    'window.layer.open = function',
    'installPluginLayerTranslation();',
    'window._yfActivePlugin = name',
    'window._yfActivePlugin = null',
]


def check_nested_layer_hook(ctx):
    path = os.path.join(WORKSPACE, 'web', 'static', 'app', 'soft.js')
    if not os.path.isfile(path):
        return ['缺少 web/static/app/soft.js']
    src = read_text(path)
    return ['soft.js 缺少嵌套层 i18n 钩子标记: %r' % m
            for m in NESTED_LAYER_HOOK_MARKERS if m not in src]


# ---------------------------------------------------------------------------
# 注册表与主流程
# ---------------------------------------------------------------------------

CHECKS = [
    ('plugin-key-parity', '插件六语言键集一致', check_plugin_key_parity),
    ('global-key-parity', '全局语言包叶子路径一致', check_global_key_parity),
    ('no-html', '译文不含 HTML（白名单除外）', check_no_html),
    ('dirty-keys', '语言包无代码型脏键', check_dirty_keys),
    ('pt-argc', '无多参 pt()/_t() 调用', check_pt_argc),
    ('msgtpl-pt', 'msgTpl 首参必含 pt(', check_msgtpl_pt),
    ('no-zero-placeholder', '无 {0} 占位符', check_no_zero_placeholder),
    ('backend-msg-prefix', '后端消息可翻译前缀不含 HTML', check_backend_msg_prefix),
    ('backend-msg-key', '后端中文消息可查到语言包键', check_backend_msg_key),
    ('nested-layer-hook', '插件二级弹窗 i18n 钩子已安装', check_nested_layer_hook),
]


# ---------------------------------------------------------------------------
# 自证：证明检测器既不漏报也不误报
# ---------------------------------------------------------------------------

# --- 自证夹具（内嵌） -------------------------------------------------------
#
# 为什么不读 test/ 下的同名文件：`.gitignore:202` 忽略整个 `/test`，CI 检出后
# 夹具不存在，自证只能「静默跳过」——而只跳过、不报错的守卫会制造「永远全绿」
# 的假象，比没有自证更危险。内嵌后本脚本是真正自包含的单文件门禁。
#
# `test/i18n_scripts/tools/fixtures/` 下的同名文件保留给
# `test/test_plugins_i18n_upgrade.py`（本地重守卫）使用。两者是刻意的独立副本，
# 互为交叉验证，不做同步——同步反而会引入「共同失效模式」。

FIXTURE_BACKEND_MSG_PREFIX = r'''# -*- coding: utf-8 -*-
"""backend-msg-prefix 检测器的自证夹具。

契约：前端 YfI18n.translateAny() 用「消息首个冒号（含）前缀」查语言包，
      所以前缀必须纯文本；HTML 只能出现在前缀之后。

本夹具刻意混入 3 处违规写法（BAD）与 6 处合规写法（GOOD），
用于证明检测器既不漏报也不误报。
"""


def bad_samples():
    # BAD-1：HTML 落在前缀内部（首冒号在 URL 里/前缀里）
    return yf.returnJson(False, 'ERROR: 配置出错<br><a style="color:red;">' + err + '</a>')
    # BAD-2：<br> 位于冒号之前
    return yf.returnJson(False, 'MySQLdb组件缺失! <br>进入SSH命令行输入: pip install x')
    # BAD-3：整条消息就是 HTML（无冒号，前缀 = 全文）
    return yf.returnJson(False, '<b>出错了</b>')


def good_samples():
    # GOOD-1：前缀纯文本，HTML 在前缀之后
    return yf.returnJson(False, '配置出错: ' + '<span style="color:red;">' + err + '</span>')
    # GOOD-2：<br> 挪到冒号之后
    return yf.returnJson(False, 'MySQLdb组件缺失! 进入SSH命令行输入: <br>pip install x')
    # GOOD-3：纯文本、无 HTML
    return yf.returnJson(True, '设置成功')
    # GOOD-4：f-string 前缀
    return yf.returnJson(False, f"扫描发生异常: {str(e)}")
    # GOOD-5：URL 里的冒号在动态部分，前缀仍是纯文本
    return yf.returnJson(False, '请先安装初始化，默认地址: http://' + ip + ':3000')
    # GOOD-6：第二个实参不是字面量，跳过
    return yf.returnJson(False, str(e), {'a': 1})
'''

FIXTURE_PT_ARGC_JS = r'''// check_pt_argc.js 自证夹具
// 用途：验证检测器能抓出「多参 pt()」的各类形态（含动态首参）。
// 本夹具故意包含违规写法，禁止作为生产代码。
//
// 期望检测结果：VIOLATIONS = 6

// ---- 违规 1：字面量首参 + 变量（最常见） ----
var a1 = pt('确定要解封 IP ({1}) 吗？', ip);

// ---- 违规 2：动态首参（「首参必须字面量」的正则方案会漏掉这个） ----
var a2 = pt(PATTERNS[i][1], m[1]);

// ---- 违规 3：变量首参 ----
var a3 = pt(msgKey, value);

// ---- 违规 4：多个额外参数 ----
var a4 = pt('确定要{0}实例 [{1}] 吗？', actionName, name);

// ---- 违规 5：跨行调用（括号配对必须跨行工作） ----
var a5 = pt(
    '此处为 {1} 主配置文件',
    _name
);

// ---- 违规 6：嵌套括号内的逗号不能被误计为顶层逗号 ----
var a6 = pt('值 {1}', fn(a, b));

// ==================== 以下为合法写法，不得报错 ====================

var b1 = pt('IP地址');
var b2 = pt(raw);
var b3 = msgTpl(pt('删除 {1}'), [name]);
var b4 = msgTpl(pt('已创建虚拟环境 ({1})'), [item.venvs.length]);
var b5 = pt('a, b, c');                       // 字符串内的逗号不算
var b6 = pt('包含)右括号(');                   // 字符串内的括号不算
var b7 = pt("双引号 ' 单引号");                // 引号混用
var b8 = pt(`模板串 ${x}, 逗号`);              // 模板串内的逗号不算
var b9 = pt('正则 /a,b/ 里的逗号');            // 看似正则实为字符串
var b10 = obj.pt('方法调用', x);               // 非全局 pt（有前缀）→ 不报
var b11 = _t('单参别名');                      // _t 单参合法
// var b12 = pt('注释里的', x);                 // 注释不算
var b13 = pt('转义引号 \' 后跟逗号, 仍算字符串内');
'''

# 每处调用前一行标注 `# EXPECT-OK` / `# EXPECT-MISS`，自证据此推导期望行号。
FIXTURE_BACKEND_MSG_KEY = r'''# -*- coding: utf-8 -*-
"""backend-msg-key 检测器的「已知答案」夹具。

用固定键集调用 _scan_backend_msg_keys()，期望恰好命中 5 处。夹具同时覆盖
「必须放过」的合法写法与「必须抓到」的漏翻写法，证明检测器既不漏报也不误报。

固定键集见 FIXTURE_BACKEND_MSG_KEY_KEYS：
    扫描完成
    获取日志失败:
    读取日志失败:          <- 故意带尾随空格，验证「尾随空格容错」分支
    操作失败:
"""


def ok_exact():
    # EXPECT-OK
    return yf.returnJson(True, '扫描完成', {})


def ok_colon_prefix():
    # EXPECT-OK
    return yf.returnJson(False, '获取日志失败: ' + str(e))


def ok_colon_no_space():
    # EXPECT-OK
    return yf.returnJson(False, '获取日志失败:' + str(e))


def ok_trailing_space_key():
    # EXPECT-OK
    return yf.returnJson(False, '读取日志失败: ' + str(e))


def ok_colon_prefixed_fstring():
    # EXPECT-OK
    return yf.returnJson(False, f'操作失败: {res["error"]}')


def ok_non_chinese():
    # EXPECT-OK
    return yf.returnJson(False, 'Permission denied')


def bad_no_colon_split():
    # EXPECT-MISS
    return yf.returnJson(True, f'清理完成！已释放 {freed} 磁盘空间')


def bad_prefix_missing():
    # EXPECT-MISS
    return yf.returnJson(False, '扫描发生异常: ' + str(e))


def bad_colon_too_far():
    # EXPECT-MISS
    return yf.returnJson(
        False, '这是一条特别长的前缀用来把冒号推到四十个字符之后从而无法匹配: ' + x)


def bad_exact_missing():
    # EXPECT-MISS
    return yf.returnJson(False, '请不要输入以下特殊字符 " ~ ~ / = "')


def bad_chinese_after_colon():
    # EXPECT-MISS
    return yf.returnJson(False, 'ERROR: 配置出错<br>' + detail)
'''

FIXTURE_BACKEND_MSG_KEY_KEYS = frozenset(
    ('扫描完成', '获取日志失败:', '读取日志失败: ', '操作失败:'))

# 外部夹具（可选）：存在则额外跑一遍做交叉验证，不存在不判失败。
FIXTURE_PREFIX = os.path.join(
    WORKSPACE, 'test', 'i18n_scripts', 'tools', 'fixtures', 'backend_msg_prefix.py')


def _tagged_expectations(src):
    """从夹具的 `# EXPECT-OK` / `# EXPECT-MISS` 注释推导期望行号。

    行号不写死在自证里：手写行号是最典型的漂移源——夹具一改期望值就错，
    而「期望值错」和「检测器错」在断言层面无法区分，会把自证变成噪音。
    """
    lines = src.splitlines()
    ok_lines, miss_lines = [], []
    for i, line in enumerate(lines):
        m = re.match(r'\s*#\s*EXPECT-(OK|MISS)\b', line)
        if not m:
            continue
        for j in range(i + 1, len(lines)):
            if 'returnJson(' in lines[j]:
                (ok_lines if m.group(1) == 'OK' else miss_lines).append(j + 1)
                break
    return ok_lines, miss_lines


def self_test():
    """对检测器做「已知答案」验证。

    只跑检查、不做修复的守卫有一个共同风险：写错了恒返回 0，看起来永远「全绿」。
    因此每个新检测器都必须先对「修复前版本」报错，才算有效。
    """
    ok = True

    def report(label, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print('  [%s] %-46s got=%s want=%s' % ('PASS' if good else 'FAIL', label, got, want))

    def skip(label, why):
        print('  [SKIP] %-46s (%s)' % (label, why))

    print('backend-msg-prefix 检测器自证')
    # 1) 内嵌夹具：3 处违规（CI 里也一定跑得到）
    report('内嵌夹具违规数', len(_scan_backend_msg_prefix(FIXTURE_BACKEND_MSG_PREFIX)), 3)
    if os.path.isfile(FIXTURE_PREFIX):
        report('外部夹具违规数（交叉验证）',
               len(_scan_backend_msg_prefix(read_text(FIXTURE_PREFIX))), 3)
    else:
        skip('外部夹具违规数（交叉验证）', 'test/ 下夹具不存在（CI 环境属正常）')

    # 2) 修复前的真实源码：4 个插件各 1 处（本地快照，CI 里不存在）
    selftest_dir = os.path.join(WORKSPACE, 'test', 'tmp_i18n', 'argc_selftest')
    head_ran = 0
    for name in ('apache', 'openresty', 'mariadb', 'mysql'):
        p = os.path.join(selftest_dir, '%s_index_head.py' % name)
        if os.path.isfile(p):
            head_ran += 1
            report('HEAD %s 违规数' % name, len(_scan_backend_msg_prefix(read_text(p))), 1)
    if not head_ran:
        skip('修复前真实源码回归', 'test/tmp_i18n/argc_selftest 不存在（CI 环境属正常）')

    # 3) 修复后的真实源码：0 处
    cur = 0
    for name in plugin_names():
        p = os.path.join(PLUGIN_ROOT, name, 'index.py')
        if os.path.isfile(p):
            cur += len(_scan_backend_msg_prefix(read_text(p)))
    report('当前插件源码违规数', cur, 0)

    # 4) pt() 参数个数检测器自证（内嵌 JS 夹具：6 处多参）
    report('pt_argc JS 内嵌夹具违规数', len(_scan_pt_argc(FIXTURE_PT_ARGC_JS)), 6)

    # 5) backend-msg-key 检测器自证（内嵌 Python 夹具：恰好 5 处未命中）
    want_ok, want_miss = _tagged_expectations(FIXTURE_BACKEND_MSG_KEY)
    # 标注必须解析得出来，否则说明夹具或解析器坏了——先证明「标尺」有效
    report('夹具 EXPECT 标注可解析 (ok, miss)', (len(want_ok), len(want_miss)), (6, 5))
    got_lines = [ln for ln, _ in _scan_backend_msg_keys(
        FIXTURE_BACKEND_MSG_KEY, FIXTURE_BACKEND_MSG_KEY_KEYS)]
    report('backend-msg-key 内嵌夹具未命中行号', got_lines, want_miss)
    report('夹具「合法写法」被误报数', len(set(got_lines) & set(want_ok)), 0)

    # 6) 当前代码库：未命中数必须为 0（例外已在 check_backend_msg_key 中扣除）
    report('当前代码库后端消息未命中数', len(check_backend_msg_key({})), 0)

    print('自证结果: %s' % ('全部通过' if ok else '存在失败'))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description='i18n 静态校验（CI 门禁）')
    ap.add_argument('--verbose', '-v', action='store_true', help='打印失败明细')
    ap.add_argument('--check', help='只运行指定检查')
    ap.add_argument('--list', action='store_true', help='列出全部检查名')
    ap.add_argument('--self-test', action='store_true', help='校验检测器本身（已知答案）')
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if args.list:
        for key, title, _ in CHECKS:
            print('%-22s %s' % (key, title))
        return 0

    selected = CHECKS
    if args.check:
        selected = [c for c in CHECKS if c[0] == args.check]
        if not selected:
            print('[ERROR] 未知检查: %s' % args.check)
            return 1

    print('i18n 静态校验  (工作区: %s)' % WORKSPACE)
    print('插件数: %d' % len(plugin_names()))
    print('-' * 72)

    failed = 0
    for key, title, fn in selected:
        try:
            problems = fn(None)
        except Exception as e:
            problems = ['检查自身异常: %r' % (e,)]
        if problems:
            failed += 1
            print('[FAIL] %-22s %s  (%d 项)' % (key, title, len(problems)))
            if args.verbose:
                for p in problems[:40]:
                    print('         - %s' % p)
                if len(problems) > 40:
                    print('         ... 其余 %d 项省略' % (len(problems) - 40))
        else:
            print('[PASS] %-22s %s' % (key, title))

    print('-' * 72)
    if failed:
        print('结果: 失败 %d / %d 项检查' % (failed, len(selected)))
        return 1
    print('结果: 全部通过 (%d 项检查)' % len(selected))
    return 0


if __name__ == '__main__':
    sys.exit(main())
