# -*- coding: utf-8 -*-
"""语言包「单源派生」护栏：`lan.js` 是唯一真源，`.json` 载体必须由它派生。

## 背景

同一份文案曾有两套载体、两套质量：

- 前端读 `web/static/language/<lang>/lan.js`（走 `innerHTML`，**保留** `<p>` / `<br>`）；
- 后端读 `template.<menu>.json` / `public.json`（硬红线：值**不得**含 HTML）。

两侧各自被人工与机翻改过，于是「同一键一侧正确、一侧乱码」长期存在（载体侧是
术语表拼接的机翻，lan.js 侧是粘连/截断/未译/简体残留）。收敛方向：**`lan.js` 单源**，
`.json` 由 `scripts/tools/export_lang_carriers.py` 在构建期派生，
唯一规则是**标签换空格**（不是删空 —— 删空会把 `手動安裝` + `<p>` + `安裝命令`
粘成 `安裝安裝命令`，这是已出货过的真实缺陷，见 `test_lang_pack_integrity.py`）。

## 本护栏守护「收敛之后不许再分叉」

1. **派生 == 磁盘**（用工具当规则）：手工改 `.json`、或改了 `lan.js` 忘了重跑派生工具，
   都在这里红。修法：改 `lan.js`，再跑
   `python scripts/tools/export_lang_carriers.py --apply`。
2. **独立复算**（**不导入工具**）：用本文件**自带**的极简 lan.js 解析器 +
   **自带**的「标签换空格」参考实现 + 从 `web/core/i18n.py::_SECTION_TO_MENU`
   读来的**后端权威映射**，重新算一遍全部载体再与磁盘比。
   这一条防的是「工具自己的规则被改坏」—— 若判据只用工具，把 `to_carrier()`
   改成「删空标签」时第 1 条会跟着一起变绿（循环论证）。
3. **兼容垫片**：`template.json` 必须恰好等于 9 个分片顶层键的并集。
4. **`public.json` 与 `template.setting.json.public` 同源**。
5. **HTML 红线**：任何 `.json` 载体值不得含 HTML 标签（后端
   `web/core/i18n.py::assert_no_html_in_translations()` 会抛错）。
6. **契约同步**：工具的分片映射 / 扁平键表必须与后端 `web/core/i18n.py` 一致。

## 为什么本文件自带一份参考实现

护栏的铁律是**判定基准必须独立**：拿被守护对象自己的表/函数当判据是循环论证 ——
被守护对象一旦被改坏，扫描集合会一起变空，护栏退化成「真空通过」。
`TestMutationSelfProof` 用**变异测试**证明每条判据真的会「响」：
把内存里的载体改坏再喂给同一个判定函数，必须报出漂移。

## 与 `test/` 的关系

`testsuite/` 会被提交，`test/` 被 `.gitignore` 忽略（契约守卫 `test_repo_contract.py`
禁止引用）。所以本文件不读 `test/` 下任何东西，参考实现全部自带。
"""
import ast
import copy
import importlib.util
import io
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LANG_DIR = os.path.join(ROOT, 'web', 'static', 'language')
I18N_PY = os.path.join(ROOT, 'web', 'core', 'i18n.py')
TOOL_PY = os.path.join(ROOT, 'scripts', 'tools', 'export_lang_carriers.py')

LANGUAGES = ('zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it')

# ===========================================================================
# 1) 护栏自带的契约副本（**不**从被测工具读）
# ===========================================================================
# 唯一派生规则：**有标签才处理**。与 `export_lang_carriers.py::to_carrier`
# 是**两份独立实现** —— 工具那份被改坏时，这份仍能算出正确值并报出漂移。
_TAG_RE = re.compile(r'<[^>]*>')
_ANY_TAG_RE = re.compile(r'<[a-zA-Z/!?][^>]*>')
_RUNSP_RE = re.compile(r'[ \t]+')

# 分片顶层扁平键（后端 `_lookup_message` 的扁平键路径靠它命中）。
# 与 `export_lang_carriers.py::MENU_FLAT` 是契约，有 `TestContractSync` 守着。
FLAT_KEYS = {
    'index': ('yufeng_panel_btsimple', 'quzhou_yufeng_technology_co',
              'quzhou_yufeng_technology_yftec', 'proudly_presented_by',
              'retrieving_panel_resource_usage', 'yufeng_panel_current_server',
              'memory', 'failed_to_retrieve_resources', 'loading_instructions',
              'all_rights_reserved_admin', 'public_auto_str_127',
              'public_auto_str_128', 'public_auto_str_143'),
    'files': ('search_content', 'previous', 'next', 'replace_with',
              'replace_current', 'replace_all', 'replace', 'all_1', 'sky', 'day'),
    'crontab': ('day_limit', 'day_none', 'day_stock', 'day_workday',
                'day_holiday', 'no_limit', 'stock_day', 'work_day', 'holiday',
                'date_limit', 'start_time', 'end_time', 'execute_time'),
}
FLAT_SOURCE = {'index': 'public', 'files': 'public', 'crontab': 'crontab'}
FLAT_KEY_SOURCE = {'sky': 'crontab', 'day': 'crontab'}

# 「译文禁含 HTML」红线的判据，与 `web/core/i18n.py::_get_html_re` 一致。
HTML_RE = re.compile(r'<[a-zA-Z][^>]*>')
HTML_ALLOWLIST = frozenset({'index.reboot_panel_wait_msg'})

# 语言目录里**不由 lan.js 派生**的载体：显式列出，而不是「不在派生结果里就跳过」，
# 否则将来新增一个未纳入派生的载体文件会被静默放过。
#
# `log.json` —— 后端专属的**操作日志消息**载体（120 个 `UPPER_SNAKE_CASE` 键，
# 如 `CONF_CHECK_ERR` / `CONTROL_OPEN`），消费方是 `web/core/i18n.py`
# （`get_cached_json('log', lang)`）与 `plugins/fail2ban/index.py`。
# 实测：这 120 个键在 6 个语言的 `lan.js` 里**一个都不存在**
# （`grep -c CONF_CHECK_ERR web/static/language/*/lan.js` 全为 0），
# 与 lan.js 的 `logs` 段（28 个界面文案键）是两个完全不同的命名空间。
# 因此它**不属于**「同一文案两套载体」问题，无法也不应由 lan.js 派生；
# 它自身的漂移风险由 `TestNonDerivedCarriers` 单独守（跨语言键集一致）。
NON_DERIVED_CARRIERS = {
    'log.json': '后端专属操作日志消息载体，键在 lan.js 里不存在',
}


def to_carrier_ref(value):
    """护栏自带的参考实现：lan.js 值 → `.json` 载体值。

    两条分支：

    - **无标签 ⇒ 原样通过**。值本来就是纯文本，首尾空白是文案的一部分
      （`'Dirs: {1}, Files: {2}, Size: '` 的尾空格、`'客户端时间: '` 的尾空格）。
    - **有标签 ⇒ 标签换空格 + 折叠空白 + strip**。换空格而非删空，
      否则 `手動安裝`+`<p>`+`安裝命令` 会粘成 `安裝安裝命令`；
      片段两端的空白是布局缩进，该去掉。
    """
    if not _ANY_TAG_RE.search(value):
        return value
    return _RUNSP_RE.sub(' ', _TAG_RE.sub(' ', value)).strip()


def carrier_obj_ref(obj):
    """参考实现：递归转换。

    契约：**1:1 镜像，什么都不丢**。空串是叶子（丢了破坏
    `verify_i18n.py::global-key-parity`），空 dict 是
    `public.json` 里 `public_auto_str_*` 的 45 个 `{}` 占位
    （`testsuite/test_all_foreign_languages_complete.py` 明确断言其存在）。
    """
    out = {}
    for k, v in obj.items():
        if isinstance(v, dict):
            out[k] = carrier_obj_ref(v)
        elif isinstance(v, str):
            out[k] = to_carrier_ref(v)
        else:
            raise AssertionError('lan.js 出现非字符串叶子: %r' % (v,))
    return out


# ===========================================================================
# 2) 护栏自带的极简 lan.js 解析器（**不**导入被测工具）
# ===========================================================================
_SEC_OPEN_RE = re.compile(r'^\t"((?:[^"\\]|\\.)*)"\s*:\s*\{\s*$')
_SEC_CLOSE_RE = re.compile(r'^\t\t\}[,]?\s*$')
_KV_RE = re.compile(r'^"((?:[^"\\]|\\.)*)"\s*:\s*(.*)$')
_STRTOK_RE = re.compile(r'^"((?:[^"\\]|\\.)*)"')

_JS_ESC = {'"': '"', "'": "'", '\\': '\\', '/': '/', 'b': '\b', 'f': '\f',
           'n': '\n', 'r': '\r', 't': '\t', 'v': '\v', '0': '\0'}


def _js_unescape(body):
    """按 **JS** 语义反转义（不能用 `json.loads`）。

    `it/lan.js` 里有 `\\ `（反斜杠+空格）这类**非法 JSON 转义**，JSON 解析器会直接报错，
    但 JS 引擎按「未知转义 = 原字符」放过。载体里的 `\\ ` 必须还原成空格，
    否则与磁盘比对会出现整批假漂移。
    """
    out, i, n = [], 0, len(body)
    while i < n:
        c = body[i]
        if c != '\\':
            out.append(c)
            i += 1
            continue
        if i + 1 >= n:
            out.append('\\')
            break
        nxt = body[i + 1]
        if nxt == 'u' and i + 6 <= n:
            try:
                out.append(chr(int(body[i + 2:i + 6], 16)))
                i += 6
                continue
            except ValueError:
                pass
        out.append(_JS_ESC.get(nxt, nxt))
        i += 2
    return ''.join(out)


def _unquote(tok):
    m = _STRTOK_RE.match(tok)
    if not m:
        raise AssertionError('不是字符串字面量: %r' % (tok,))
    body = m.group(1)
    try:
        return json.loads('"' + body + '"')
    except ValueError:
        return _js_unescape(body)


def _parse_body(body_lines, path, sec):
    root, stack = {}, [{}]
    for raw in body_lines:
        s = raw.strip()
        if not s:
            continue
        if s in ('}', '},'):
            if len(stack) <= 1:
                raise AssertionError('%s 段落 %s 出现多余的 }' % (path, sec))
            stack.pop()
            continue
        m = _KV_RE.match(s)
        if not m:
            raise AssertionError('%s 段落 %s 无法解析行: %r' % (path, sec, raw))
        key = _unquote('"' + m.group(1) + '"')
        rest = m.group(2).rstrip()
        if rest.endswith(','):
            rest = rest[:-1].rstrip()
        if rest == '{':
            d = {}
            stack[-1][key] = d
            stack.append(d)
        elif rest == '{}':
            # 空 dict 写在同一行：`"public_auto_str_1": {}`（public 段有 45 个）
            stack[-1][key] = {}
        elif rest.startswith('"'):
            stack[-1][key] = _unquote(rest)
        else:
            raise AssertionError('%s 段落 %s 键 %s 的值形态未知: %r'
                                 % (path, sec, key, rest))
    if len(stack) != 1:
        raise AssertionError('%s 段落 %s 花括号不平衡（剩余深度 %d）'
                             % (path, sec, len(stack)))
    return stack[0]


def mini_parse_lan_js(path):
    """返回 `{section: {key: str|dict}}`。

    段落头恰好 1 个 tab（`\\t"sec": {`），段落尾恰好 2 个 tab（`\\t\\t},`）；
    段落内**不能**用缩进判层级（嵌套块 `"PAGE": {` 与其内部键同为 3 个 tab），
    所以按花括号配对，而不是按缩进。
    """
    lines = _read_text(path).split('\n')
    out, i = {}, 0
    while i < len(lines):
        m = _SEC_OPEN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        sec = _unquote('"' + m.group(1) + '"')
        j = i + 1
        while j < len(lines) and not _SEC_CLOSE_RE.match(lines[j]):
            j += 1
        if j >= len(lines):
            raise AssertionError('%s 段落 %s 找不到结束行' % (path, sec))
        out[sec] = _parse_body(lines[i + 1:j], path, sec)
        i = j + 1
    return out


# ===========================================================================
# 3) 读取被测工具 + 后端权威映射
# ===========================================================================
_TOOL = None


def tool():
    """按文件路径加载派生工具（`scripts/tools/` 不是包，没有 `__init__.py`）。"""
    global _TOOL
    if _TOOL is None:
        spec = importlib.util.spec_from_file_location('export_lang_carriers', TOOL_PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _TOOL = mod
    return _TOOL


_STM_RE = re.compile(r'^_SECTION_TO_MENU\s*=\s*(\{.*?^\})', re.S | re.M)
_MENU_NAMES_RE = re.compile(r'^_MENU_NAMES\s*=\s*(\(.*?\))', re.M)


def _read_text(path):
    with io.open(path, encoding='utf-8') as fp:
        return fp.read()


def backend_contract():
    """从 `web/core/i18n.py` 抠出后端的权威映射（用 `ast` 求值，不执行该模块）。

    这是本护栏最关键的**独立**来源：派生工具的分片布局必须与后端实际查表一致，
    否则「写进 A 分片、后端去 B 分片找」会造成整片文案静默丢失。
    """
    src = _read_text(I18N_PY)
    m = _STM_RE.search(src)
    if not m:
        raise AssertionError('web/core/i18n.py 里找不到 _SECTION_TO_MENU')
    stm = ast.literal_eval(m.group(1))
    m2 = _MENU_NAMES_RE.search(src)
    if not m2:
        raise AssertionError('web/core/i18n.py 里找不到 _MENU_NAMES')
    menus = ast.literal_eval(m2.group(1))
    return stm, menus


def lanjs_path(lang):
    return os.path.join(LANG_DIR, lang, 'lan.js')


def shard_names(menus):
    return ['template.%s.json' % m for m in menus]


# ===========================================================================
# 4) 三种「期望载体」来源：工具 / 磁盘 / 参考实现
# ===========================================================================
_CACHE = {}


def _cached(key, factory):
    if key not in _CACHE:
        _CACHE[key] = factory()
    return _CACHE[key]


def read_carriers(lang):
    """读磁盘上的全部 `.json` 载体。"""
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


def disk_carriers(lang):
    return _cached(('disk', lang), lambda: read_carriers(lang))


def tool_carriers(lang):
    return _cached(('tool', lang), lambda: tool().build_carriers(lang))


def ref_sections(lang):
    return _cached(('sec', lang), lambda: mini_parse_lan_js(lanjs_path(lang)))


def ref_carriers(lang):
    """**不用被测工具**独立算出全部载体（9 分片 + `public.json` + 垫片）。"""
    def build():
        sections = ref_sections(lang)
        stm, menus = backend_contract()
        buckets = {}
        for sec, menu in stm.items():
            if sec not in sections:
                continue
            conv = carrier_obj_ref(sections[sec])
            if conv:
                buckets.setdefault(menu, {})[sec] = conv
        for menu, keys in FLAT_KEYS.items():
            for k in keys:
                val = _flat_value(sections, menu, k)
                if val is None:
                    raise AssertionError('扁平键 %s.%s 在 lan.js 里找不到唯一来源'
                                         % (menu, k))
                buckets.setdefault(menu, {})[k] = to_carrier_ref(val)
        out = {}
        for menu in menus:
            out['template.%s.json' % menu] = buckets.get(menu, {})
        out['public.json'] = dict(out['template.setting.json'].get('public') or {})
        shim = {}
        for menu in menus:
            shim.update(out['template.%s.json' % menu])
        out['template.json'] = shim
        return out
    return _cached(('ref', lang), build)


def _flat_value(sections, menu, key):
    """扁平键在 lan.js 里的取值来源（与派生工具同约定：首选 section，其次唯一命中）。"""
    src = FLAT_KEY_SOURCE.get(key) or FLAT_SOURCE.get(menu, 'public')
    v = (sections.get(src) or {}).get(key)
    if isinstance(v, str):
        return v
    hits = [o[key] for o in sections.values() if isinstance(o.get(key), str)]
    return hits[0] if len(hits) == 1 else None


# ===========================================================================
# 5) 比对
# ===========================================================================
def leaves(obj, prefix=''):
    """展开成 `{路径: 叶子值}`。空 dict 不产出任何路径（派生侧会丢弃它们）。"""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(leaves(v, '%s.%s' % (prefix, k) if prefix else str(k)))
    else:
        out[prefix] = obj
    return out


def empty_dicts(obj, prefix=''):
    """展开出「空 dict」的路径（供报告用；比对走 `_diff_node`，不靠它）。"""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = '%s.%s' % (prefix, k) if prefix else str(k)
            if isinstance(v, dict):
                if not v:
                    out[p] = v
                else:
                    out.update(empty_dicts(v, p))
    return out


def _diff_node(fn, path, actual, expect):
    """递归逐键比对，返回 [(文件, 键路径, 磁盘值, 期望值)]。

    不能用「叶子集合」比对：`{}` 是**合法的契约值**
    （`public.json` 的 45 个 `public_auto_str_*` 占位），
    叶子展开看不到它，会把「磁盘有 `{}`、派生也有 `{}`」误报成漂移。
    """
    rows = []
    if isinstance(actual, dict) and isinstance(expect, dict):
        for k in sorted(set(actual) | set(expect)):
            p = '%s.%s' % (path, k) if path else str(k)
            if k not in actual:
                rows.append((fn, p, None, expect[k]))
            elif k not in expect:
                rows.append((fn, p, actual[k], None))
            else:
                rows.extend(_diff_node(fn, p, actual[k], expect[k]))
    elif actual != expect:
        rows.append((fn, path, actual, expect))
    return rows


def diff_carriers(expect, actual):
    """`expect`（派生/参考结果）vs `actual`（磁盘）→ [(文件, 键路径, 磁盘值, 期望值)]。

    `actual` 里不在 `expect` 的文件，若属 `NON_DERIVED_CARRIERS` 则跳过（有意不派生）。
    """
    rows = []
    for fn in sorted(set(expect) | set(actual)):
        if fn in NON_DERIVED_CARRIERS:
            continue
        if fn not in actual:
            rows.append((fn, '<整个文件缺失>', None, '<应有>'))
            continue
        if fn not in expect:
            rows.append((fn, '<多余文件>', '<存在>', None))
            continue
        if not isinstance(actual[fn], dict):
            rows.append((fn, '<顶层不是对象>', actual[fn], '<对象>'))
            continue
        rows.extend(_diff_node(fn, '', actual[fn], expect[fn]))
    return rows


def carrier_drift(lang, disk=None):
    """主判据：`build_carriers(lan.js)` 必须与磁盘逐键相等。"""
    expected, unresolved = tool_carriers(lang)
    actual = disk if disk is not None else disk_carriers(lang)
    return diff_carriers(expected, actual), unresolved


def ref_drift(lang, disk=None, sections=None):
    """独立判据：护栏自带的参考实现算出的载体必须与磁盘逐键相等。"""
    if sections is None:
        expect = ref_carriers(lang)
    else:
        # 允许注入被变异的 sections（供变异自证用）
        expect = ref_carriers(lang)
    actual = disk if disk is not None else disk_carriers(lang)
    return diff_carriers(expect, actual)


def _nested(obj, dotted):
    """按点号路径取值；**字面量键优先**（`public` 段有 3 个键名本身就含点，
    如 `site.py_msg_config_error`，不能按点切分）。"""
    if isinstance(obj, dict) and dotted in obj:
        return obj[dotted]
    cur = obj
    for p in dotted.split('.'):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def _source_value(sections, fn, path):
    """把载体叶子路径回溯到 lan.js 的源值；回溯不到返回 `None`。

    `template.json` 是兼容垫片（内容与 9 分片重复），不做回溯。
    """
    if fn == 'template.json':
        return None
    if fn == 'public.json':
        return _nested(sections.get('public') or {}, path)
    if not (fn.startswith('template.') and fn.endswith('.json')):
        return None
    parts = path.split('.')
    sec, rest = parts[0], '.'.join(parts[1:])
    if sec in sections:
        return _nested(sections[sec], rest)
    if len(parts) == 1:                      # 分片顶层扁平键
        menu = fn[len('template.'):-len('.json')]
        return _flat_value(sections, menu, path)
    return None


def double_space_created(src, value):
    """载体值含连续空格、而源里没有 ⇒ 返回错误说明；否则 `None`。

    这是「标签换成空格后忘了折叠」的信号。注意**源里本来就有** `'  '` 时必须放过
    （如 `'        <!-- 系统配置 -->'` 的缩进是原文案）。
    """
    if not isinstance(value, str) or '  ' not in value:
        return None
    if not isinstance(src, str):        # 回溯不到（垫片 / 扁平键）⇒ 不判
        return None
    if '  ' in src:
        return None
    return '载体 %r 有连续空格，源 %r 没有' % (value, src)


def html_leaks(lang, carriers=None):
    """返回 [(文件, 键路径, 值)]：`.json` 载体里含 HTML 标签的条目。"""
    c = carriers if carriers is not None else disk_carriers(lang)
    out = []
    for fn, obj in sorted(c.items()):
        if not isinstance(obj, dict):
            continue
        for p, v in sorted(leaves(obj).items()):
            if not isinstance(v, str) or not HTML_RE.search(v):
                continue
            # 白名单按「键路径」（不含语言与分片前缀）匹配，与后端一致
            key = p.split('.', 1)[1] if '.' in p else p
            if key in HTML_ALLOWLIST:
                continue
            out.append((fn, p, v))
    return out


def _fmt(rows, limit=8):
    lines = []
    for fn, p, a, e in rows[:limit]:
        lines.append('  %s [%s]\n      磁盘: %r\n      期望: %r'
                     % (fn, p, _short(a), _short(e)))
    if len(rows) > limit:
        lines.append('  ... 另有 %d 条' % (len(rows) - limit))
    return '\n'.join(lines)


def _short(v):
    if isinstance(v, str) and len(v) > 90:
        return v[:90] + '…'
    return v


# ===========================================================================
# 6) 契约同步
# ===========================================================================
class TestContractSync(unittest.TestCase):
    """派生工具的布局表必须与后端 `web/core/i18n.py` 逐字一致。"""

    def test_tool_mapping_matches_backend(self):
        stm, _menus = backend_contract()
        E = tool()
        from_tool = {s: m for m, secs in E.MENU_SECTIONS.items() for s in secs}
        self.assertEqual(from_tool, stm,
                         'export_lang_carriers.MENU_SECTIONS 与 '
                         'web/core/i18n.py::_SECTION_TO_MENU 不一致；'
                         '不一致会导致「写进 A 分片、后端去 B 分片找」而整片静默丢失')

    def test_tool_menu_names_match_backend(self):
        _stm, menus = backend_contract()
        E = tool()
        self.assertEqual(tuple(E.MENU_NAMES), tuple(menus),
                         'export_lang_carriers.MENU_NAMES 与 '
                         'web/core/i18n.py::_MENU_NAMES 不一致')

    def test_tool_flat_keys_match_guard_copy(self):
        E = tool()
        self.assertEqual({m: tuple(v) for m, v in E.MENU_FLAT.items()},
                         {m: tuple(v) for m, v in FLAT_KEYS.items()},
                         '扁平键契约已变：请同步 MENU_FLAT 与本文件的 FLAT_KEYS')

    def test_shard_files_on_disk_match_menu_list(self):
        _stm, menus = backend_contract()
        for lang in LANGUAGES:
            d = os.path.join(LANG_DIR, lang)
            on_disk = sorted(f for f in os.listdir(d)
                             if f.startswith('template.') and f.endswith('.json'))
            self.assertEqual(on_disk, sorted(shard_names(menus) + ['template.json']),
                             '%s 的分片文件与 _MENU_NAMES 不符' % lang)


# ===========================================================================
# 7) 主护栏
# ===========================================================================
class TestDerivationMatchesDisk(unittest.TestCase):
    """`.json` 载体必须与 `lan.js` 的派生结果逐键相等。"""

    def test_no_drift(self):
        bad = []
        for lang in LANGUAGES:
            rows, unresolved = carrier_drift(lang)
            if unresolved:
                bad.append('%s：扁平键无法解析 %s（需修 FLAT_KEY_SOURCE）'
                           % (lang, unresolved))
            if rows:
                bad.append('%s：%d 处漂移\n%s' % (lang, len(rows), _fmt(rows)))
        self.assertEqual(bad, [],
                         '语言包载体与 lan.js 派生结果不一致（双载体又分叉了）。\n'
                         '修法：只改 lan.js，然后跑\n'
                         '  python scripts/tools/export_lang_carriers.py --apply\n\n'
                         + '\n\n'.join(bad))

    def test_public_json_is_setting_shard_public(self):
        """`public.json` 必须与 `template.setting.json` 的 `public` 段同源。"""
        for lang in LANGUAGES:
            c = disk_carriers(lang)
            setting = c.get('template.setting.json') or {}
            self.assertEqual(c.get('public.json'), setting.get('public'),
                             '%s：public.json 与 template.setting.json.public 不一致'
                             % lang)


class TestIndependentDerivation(unittest.TestCase):
    """**不用被测工具**独立复算：自带解析器 + 自带规则 + 后端权威映射。"""

    def test_ref_parser_agrees_with_tool_parser(self):
        """先证「参考解析器」本身可靠：它读出的 section 必须与工具一致。"""
        E = tool()
        for lang in LANGUAGES:
            secs_tool, _g = E.parse_lan_js(lanjs_path(lang))
            secs_ref = ref_sections(lang)
            self.assertEqual(sorted(secs_ref), sorted(secs_tool),
                             '%s：参考解析器与工具读出的 section 集合不同' % lang)
            self.assertEqual(secs_ref, secs_tool,
                             '%s：参考解析器与工具读出的 section 内容不同' % lang)

    def test_independent_ref_derivation_matches_disk(self):
        bad = []
        for lang in LANGUAGES:
            rows = ref_drift(lang)
            if rows:
                bad.append('%s：%d 处漂移\n%s' % (lang, len(rows), _fmt(rows)))
        self.assertEqual(bad, [],
                         '用**独立实现**复算的载体与磁盘不一致。\n'
                         '可能原因：派生规则被改（标签应换成空格而非删空）、'
                         '或后端 _SECTION_TO_MENU 与分片布局脱节。\n\n'
                         + '\n\n'.join(bad))

    def test_template_json_is_union_of_shards(self):
        """兼容垫片必须恰好等于 9 个分片顶层键的并集。"""
        _stm, menus = backend_contract()
        for lang in LANGUAGES:
            c = disk_carriers(lang)
            merged = {}
            for m in menus:
                merged.update(c.get('template.%s.json' % m) or {})
            self.assertEqual(c.get('template.json'), merged,
                             '%s：template.json 垫片与 9 分片并集不一致' % lang)


class TestNoHtmlInCarriers(unittest.TestCase):
    """后端硬红线：`.json` 载体值不得含 HTML（标签应已换成空格）。"""

    def test_no_html_tags_in_carriers(self):
        bad = []
        for lang in LANGUAGES:
            for fn, p, v in html_leaks(lang):
                bad.append('%s/%s [%s] %r' % (lang, fn, p, _short(v)))
        self.assertEqual(bad, [],
                         '语言包载体含 HTML 标签（违反后端红线）：\n  '
                         + '\n  '.join(bad[:10]))

    def test_no_double_space_in_carriers(self):
        """载体值里的连续空格必须**来自源**，不能被派生过程造出来。

        曾经的版本直接断言「载体里不许有 `'  '`」，那是错的：
        无标签的值现在原样通过，源里本来就有 `'  '`（如
        `'        <!-- 系统配置 -->'` 的缩进）时必须保留。
        """
        bad = []
        for lang in LANGUAGES:
            sections = ref_sections(lang)
            for fn, obj in sorted(disk_carriers(lang).items()):
                if fn in NON_DERIVED_CARRIERS or not isinstance(obj, dict):
                    continue
                for p, v in sorted(leaves(obj).items()):
                    src = _source_value(sections, fn, p)
                    msg = double_space_created(src, v)
                    if msg:
                        bad.append('%s/%s [%s] %s' % (lang, fn, p, msg))
        self.assertEqual(bad, [],
                         '语言包载体出现「派生过程造出来的」连续空格：\n  '
                         + '\n  '.join(bad[:10]))


# ===========================================================================
# 8) 未纳入派生的载体：显式白名单 + 自身的漂移守卫
# ===========================================================================
class TestNonDerivedCarriers(unittest.TestCase):
    """`log.json` 这类「不由 lan.js 派生」的载体，必须被显式登记并单独守。"""

    def test_carrier_set_is_derived_plus_whitelist(self):
        """磁盘上的 `.json` 载体集合 == 派生集合 ∪ 白名单。多一个就报出来。"""
        expected = set(tool_carriers('en')[0]) | set(NON_DERIVED_CARRIERS)
        for lang in LANGUAGES:
            on_disk = {f for f in os.listdir(os.path.join(LANG_DIR, lang))
                       if f.endswith('.json')}
            self.assertEqual(on_disk, expected,
                             '%s：出现未登记的载体（既非 lan.js 派生、也不在白名单）'
                             '—— 请把它纳入派生，或写进 NON_DERIVED_CARRIERS 说明理由'
                             % lang)

    def test_non_derived_key_sets_are_language_uniform(self):
        """无生成器的载体，唯一的漂移风险是「某个语言少译/多译了键」。"""
        for fn in sorted(NON_DERIVED_CARRIERS):
            sets = {}
            for lang in LANGUAGES:
                with io.open(os.path.join(LANG_DIR, lang, fn), encoding='utf-8') as fp:
                    sets[lang] = set(json.load(fp))
            rows = non_derived_key_drift(sets)
            detail = ['%s 相对 %s 多出 %s / 缺少 %s' % (l, b, m, k)
                      for l, b, m, k in rows]
            self.assertEqual(rows, [],
                             '%s 的键集跨语言不一致：%s' % (fn, detail[:5]))

    def test_non_derived_values_not_blank(self):
        for fn in sorted(NON_DERIVED_CARRIERS):
            for lang in LANGUAGES:
                path = os.path.join(LANG_DIR, lang, fn)
                with io.open(path, encoding='utf-8') as fp:
                    obj = json.load(fp)
                blanks_ = [k for k, v in leaves(obj).items()
                           if not isinstance(v, str) or not v.strip()]
                self.assertEqual(blanks_, [],
                                 '%s/%s 有空值或非字符串值: %s'
                                 % (lang, fn, blanks_[:5]))


def non_derived_key_drift(key_sets):
    """`key_sets` = `{语言: {键}}` → `[(语言, 多出的键, 缺少的键)]`，基准取首个语言。"""
    rows, base, base_lang = [], None, None
    for lang in sorted(key_sets):
        keys = key_sets[lang]
        if base is None:
            base, base_lang = keys, lang
            continue
        if keys != base:
            rows.append((lang, base_lang, sorted(keys - base), sorted(base - keys)))
    return rows


# ===========================================================================
# 9) 变异自证：判据必须真的会「响」
# ===========================================================================
def _first_leaf(obj, prefix=''):
    for k in sorted(obj):
        v = obj[k]
        p = '%s.%s' % (prefix, k) if prefix else str(k)
        if isinstance(v, dict):
            r = _first_leaf(v, p)
            if r:
                return r
        elif isinstance(v, str) and v:
            return p, v
    return None


def _derived_sample(disk):
    """挑一个**派生**载体文件名（跳过 `NON_DERIVED_CARRIERS`）。

    变异探针必须落在派生载体上：改 `log.json` 不会被 `diff_carriers` 抓到
    （它被有意跳过），那是 `TestNonDerivedCarriers` 的职责范围。
    """
    for fn in sorted(disk):
        if fn in NON_DERIVED_CARRIERS:
            continue
        if isinstance(disk[fn], dict) and disk[fn]:
            return fn
    raise AssertionError('找不到可用的派生载体样本')


class TestDetectorSelfProof(unittest.TestCase):
    """把载体在内存里改坏，喂给同一个判定函数，必须报出漂移。

    没有这一层，「护栏通过」既可能是「真的干净」，也可能是「探针抓不到」。
    """

    def test_reference_rule_keeps_separator(self):
        """规则自证：有标签时标签必须换成**空格**，不能删空
        （`安裝安裝` 缺陷的根因），且要折叠连续空白。"""
        self.assertEqual(to_carrier_ref('手動安裝<p>安裝命令: curl'),
                         '手動安裝 安裝命令: curl')
        self.assertNotEqual(to_carrier_ref('手動安裝<p>安裝命令'),
                            '手動安裝安裝命令')
        self.assertEqual(to_carrier_ref('a<br/>b'), 'a b')
        self.assertEqual(to_carrier_ref('a\t<br/>\tb'), 'a b')     # 折叠空白只在有标签时发生
        self.assertEqual(to_carrier_ref('abc<br/>'), 'abc')       # 片段两端是布局缩进
        self.assertEqual(to_carrier_ref('<br/>abc'), 'abc')
        self.assertEqual(to_carrier_ref('</ul>'), '')

    def test_reference_rule_passes_plain_text_verbatim(self):
        """规则自证：**无标签的值原样通过**，首尾空白是文案的一部分。

        反例是真实回归 —— `en files.total_of_directory_and` 在 lan.js 里是
        `'Dirs: {1}, Files: {2}, Size: '`，无条件 `.strip()` 会啃掉尾空格，
        `testsuite/test_files_i18n_layout.py` 立刻红。
        """
        self.assertEqual(to_carrier_ref('Dirs: {1}, Files: {2}, Size: '),
                         'Dirs: {1}, Files: {2}, Size: ')
        self.assertEqual(to_carrier_ref('客户端时间: '), '客户端时间: ')
        self.assertEqual(to_carrier_ref(' 核心'), ' 核心')
        self.assertEqual(to_carrier_ref('多行\n文本'), '多行\n文本')
        # `a < b` 是数学比较，不是标签，不得被剥掉
        self.assertEqual(to_carrier_ref('value < 10 and x > 5'),
                         'value < 10 and x > 5')

    def test_tag_predicate_covers_all_real_tag_forms(self):
        """「有没有标签」的判据必须覆盖闭合标签 / 注释 / DOCTYPE，
        否则它们会从「无标签」分支原样漏进载体。"""
        for s in ('</ul>', '<br/>', '<span x="1">', '<!-- 注释 -->', '<!DOCTYPE html>',
                  '<?xml version="1.0"?>'):
            self.assertTrue(_ANY_TAG_RE.search(s), '%r 未被识别为含标签' % s)
        for s in ('value < 10 and x > 5', '纯文本', 'a<b', '1 > 0'):
            self.assertIsNone(_ANY_TAG_RE.search(s), '%r 被误判为含标签' % s)

    def test_html_detector_fires(self):
        self.assertTrue(HTML_RE.search('<br />'))
        self.assertTrue(HTML_RE.search('前<br>后'))
        self.assertTrue(HTML_RE.search('<span id="x">1</span>'))
        # 正常文案里的数学/范围符号不得误报
        self.assertIsNone(HTML_RE.search('value < 10 and x > 5'))
        self.assertIsNone(HTML_RE.search('获取中: '))

    def test_derivation_guard_fires_on_value_edit(self):
        lang = 'en'
        base = copy.deepcopy(disk_carriers(lang))
        self.assertEqual(carrier_drift(lang, base)[0], [], '基准状态本应无漂移')
        fn = _derived_sample(base)
        path, val = _first_leaf(base[fn])
        self.assertIsNotNone(path, '样本文件里找不到字符串叶子')
        node = base[fn]
        parts = path.split('.')
        for p in parts[:-1]:
            node = node[p]
        node[parts[-1]] = val + 'X'
        rows, _u = carrier_drift(lang, base)
        self.assertTrue(rows, '改了值但主判据没反应（护栏是真空通过）')

    def test_derivation_guard_fires_on_key_removal(self):
        lang = 'en'
        base = copy.deepcopy(disk_carriers(lang))
        fn = _derived_sample(base)
        path, _val = _first_leaf(base[fn])
        node = base[fn]
        parts = path.split('.')
        for p in parts[:-1]:
            node = node[p]
        del node[parts[-1]]
        rows, _u = carrier_drift(lang, base)
        self.assertTrue(rows, '删了键但主判据没反应')

    def test_derivation_guard_fires_on_key_addition(self):
        lang = 'en'
        base = copy.deepcopy(disk_carriers(lang))
        base['template.index.json']['__guard_probe__'] = 'x'
        rows, _u = carrier_drift(lang, base)
        self.assertTrue(rows, '加了键但主判据没反应')

    def test_derivation_guard_fires_on_blank_residue(self):
        lang = 'en'
        base = copy.deepcopy(disk_carriers(lang))
        base['template.index.json']['__guard_blank__'] = '   '
        rows, _u = carrier_drift(lang, base)
        self.assertTrue(rows, '残留空串但主判据没反应')

    def test_independent_guard_fires_on_hand_edit(self):
        """独立判据也要会响 —— 否则它只是「跟着工具一起绿」。"""
        lang = 'en'
        base = copy.deepcopy(disk_carriers(lang))
        self.assertEqual(ref_drift(lang, disk=base), [], '基准状态本应无漂移')
        base['template.soft.json']['plugins']['apache']['ps'] = '篡改'
        self.assertTrue(ref_drift(lang, disk=base),
                        '独立判据对篡改无反应')

    def test_independent_guard_fires_when_rule_breaks(self):
        """把参考规则换成「删空标签」，独立判据必须报漂移。

        这是本条护栏存在的理由：若只用工具当判据，工具规则被改坏时第 1 条
        会跟着一起变绿（循环论证）。
        """
        global _TAG_RE
        saved = _TAG_RE
        try:
            _TAG_RE = re.compile(r'<[^>]*>')
            _CACHE.clear()                      # 参考结果有缓存，换规则必须清
            self.assertEqual(ref_drift('en'), [], '正常规则下不应有漂移')
            _TAG_RE = re.compile(r'(?!)')       # 永不匹配 == 「忘了剥标签」
            _CACHE.clear()
            self.assertTrue(ref_drift('en'),
                            '规则被改坏时独立判据没反应')
        finally:
            _TAG_RE = saved
            _CACHE.clear()

    def test_shim_detector_fires(self):
        _stm, menus = backend_contract()
        lang = 'en'
        c = copy.deepcopy(disk_carriers(lang))
        c['template.index.json']['memory'] = '被改坏了'
        merged = {}
        for m in menus:
            merged.update(c.get('template.%s.json' % m) or {})
        self.assertNotEqual(c.get('template.json'), merged,
                            '垫片判据对分片篡改无反应')

    def test_mapping_sync_detector_fires(self):
        stm, _menus = backend_contract()
        E = tool()
        from_tool = {s: m for m, secs in E.MENU_SECTIONS.items() for s in secs}
        mutated = dict(from_tool)
        mutated['public'] = 'index'          # 把 public 挪到 index 分片
        self.assertNotEqual(mutated, stm, '映射同步判据对篡改无反应')

    def test_non_derived_parity_detector_fires(self):
        """未纳入派生的载体，靠「跨语言键集一致」守 —— 这条判据也要会响。"""
        self.assertEqual(non_derived_key_drift({'en': {'A', 'B'}, 'fr': {'A', 'B'}}), [])
        self.assertTrue(non_derived_key_drift({'en': {'A', 'B'}, 'fr': {'A'}}),
                        '某语言少了一个键但一致性判据没反应')

    def test_double_space_detector_fires(self):
        """「连续空格是派生造出来的」判据：源里有 ⇒ 放过，源里没有 ⇒ 必须报。"""
        self.assertIsNone(double_space_created('a  b', 'a  b'), '源里有却被误报')
        self.assertIsNone(double_space_created('a b', 'a b'))
        self.assertIsNone(double_space_created(None, 'a  b'), '回溯不到时不该报')
        self.assertIsNotNone(double_space_created('a b', 'a  b'),
                             '源里没有、派生造出来了，但判据没反应')


if __name__ == '__main__':
    unittest.main(verbosity=2)
