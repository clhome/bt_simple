# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

"""
面板日志（操作日志 / 日志审计）多国语言适配。

背景
----
面板操作日志在写入数据库时保存的是「中文原文」（如 ``文件[/x]保存成功``），
日志审计的文件标题同样由后端硬编码生成。二者在前端是直接渲染的，
因此非中文界面下会漏出中文。

设计
----
1. ``log.json`` 是后端专属的「操作日志消息词典」（键为语义化的
   ``FILE_SAVE_SUCCESS`` 等）。本模块把它反向索引为
   ``中文原文 -> 键``，再借助 :func:`core.i18n.t` 渲染成当前语言。
2. 对于已在库中的历史记录、以及由 ``yf.getInfo`` 提前插值过的整句，
   使用「模板正则」匹配：把 ``{1}`` / ``{}`` / ``%s`` 视为捕获组，
   抽回参数后按目标语言重新渲染（不同语言可自由调整 ``{n}`` 顺序）。
3. 匹配不到的一律原样返回 —— 操作系统 / 命令行输出的中文不从面板
   词典里来，按约定不处理。

对外只暴露两个函数：:func:`translate_log_type` 与 :func:`translate_log_message`。
"""

import functools
import re

# 中文（含全角）判定：只有含中文的日志才需要翻译，纯英文/路径直接短路
_CJK_RE = re.compile(u'[\u4e00-\u9fff]')

# 译文里不应出现 HTML（i18n 红线），反向索引时跳过，避免把标签当模板
_HTML_RE = re.compile(r'<[a-zA-Z/][^>]*>')

# 占位符：{1} {2} / {} / %s / %d
_PH_RE = re.compile(r'\{(\d+)\}|\{\}|%s|%d')

# 句尾标点：词典里的模板带 ``!``、库里历史记录可能没有，匹配时统一容忍
_TAIL_PUNCT = u'!！。.,，;；'

# 类型键前缀（TYPE_*）与标题键前缀（TITLE_*）不参与「消息正文」反向索引
_NON_MSG_PREFIXES = ('TYPE_', 'TITLE_')


def _normalize(text):
    """折叠空白并去除首尾空白，规避历史记录里空格数量不一致的问题。"""
    if not isinstance(text, str):
        return ''
    return re.sub(r'\s+', ' ', text).strip()


def _build_placeholder_regex(value):
    """把带占位符的词典模板编译成捕获组正则，返回 (regex, 占位符序号列表)。

    ``{n}`` 使用显式序号；``{}`` / ``%s`` / ``%d`` 按出现顺序自动编号。
    句尾标点做可选处理，以兼容 ``文件[x]保存成功`` 与 ``文件[x]保存成功!``。
    """
    parts = []
    indices = []
    auto = 0
    pos = 0
    for m in _PH_RE.finditer(value):
        parts.append(re.escape(value[pos:m.start()]).replace(r'\ ', r'\s*'))
        if m.group(1):
            idx = int(m.group(1))
        else:
            auto += 1
            idx = auto
        indices.append(idx)
        parts.append('(.*?)')
        pos = m.end()
    tail = value[pos:]
    # 模板尾部标点整体可选，避免「有无感叹号」造成漏翻
    tail_stripped = tail.rstrip(_TAIL_PUNCT)
    parts.append(re.escape(tail_stripped).replace(r'\ ', r'\s*'))
    try:
        regex = re.compile('^' + ''.join(parts) + r'[%s]*$' % re.escape(_TAIL_PUNCT),
                           re.DOTALL)
    except re.error:
        return None, None
    return regex, indices


@functools.lru_cache(maxsize=8)
def _index(lang):
    """构建「中文值 -> 键」反向索引；``lang`` 固定取 zh-CN 原文。

    返回 ``(exact, regex_list, types)``：

    - ``exact``: 无占位符的整句 -> 键
    - ``regex_list``: ``[(regex, indices, key, weight), ...]``（按字面量长度降序，优先精确模板）
    - ``types``: 日志类型中文 -> 类型键
    """
    from core.i18n import get_cached_json

    exact = {}
    regex_items = []
    types = {}

    # log.json 优先，其次 public.json（两者都是平面键，能直接 _t(key)）
    for name in ('log', 'public'):
        try:
            data = get_cached_json(name, lang)
        except Exception:
            data = {}
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if not isinstance(value, str):
                continue
            if key.startswith('TYPE_'):
                types.setdefault(_normalize(value), key)
                continue
            if _HTML_RE.search(value):
                continue
            if key.startswith(_NON_MSG_PREFIXES):
                continue
            norm = _normalize(value)
            if _PH_RE.search(norm):
                regex, indices = _build_placeholder_regex(norm)
                if regex is not None:
                    regex_items.append((regex, indices, key, len(_PH_RE.sub('', norm))))
            else:
                exact.setdefault(norm, key)

    regex_items.sort(key=lambda x: -x[3])
    return exact, tuple(regex_items), types


def _translate(key, args):
    try:
        from core.i18n import t as _t
        return _t(key, *args)
    except Exception:
        return key


def translate_log_type(stype):
    """翻译日志「操作类型」列。

    - 词典里有的中文类型（如 ``文件管理``）按目标语言渲染；
    - 带后缀的动态类型（如 ``插件管理[PHP]``、``通知管理[SSL]``）翻译前缀，后缀原样保留；
    - 形如 ``fail2ban`` 的插件名不属于中文，原样返回。
    """
    if not stype or not isinstance(stype, str):
        return stype
    _exact, _regex, types = _index('zh-CN')

    key = types.get(_normalize(stype))
    if key:
        return _translate(key, ())

    # 动态后缀：通知管理[SSL] / 插件管理[PHP] / 站点[xxx] 等
    pos = stype.find('[')
    if pos > 0:
        prefix = _normalize(stype[:pos])
        pkey = types.get(prefix)
        if pkey:
            return _translate(pkey, ()) + stype[pos:]
    return stype


def _match(norm, exact, regex_list):
    """返回 (key, args) 或 None。先整句精确（含句尾标点容错），再模板正则。"""
    key = exact.get(norm)
    if key is None:
        key = exact.get(norm.rstrip(_TAIL_PUNCT).strip())
    if key is not None:
        return key, ()

    for regex, indices, key, _weight in regex_list:
        m = regex.match(norm)
        if not m:
            continue
        groups = m.groups()
        size = max(indices) if indices else 0
        args = [''] * size
        for i, idx in enumerate(indices):
            if 1 <= idx <= size and i < len(groups):
                args[idx - 1] = groups[i] if groups[i] is not None else ''
        return key, args
    return None


def translate_log_message(message):
    """翻译日志「详情」列，匹配不到时原样返回（含操作系统输出的中文）。"""
    if not message or not isinstance(message, str) or not _CJK_RE.search(message):
        return message

    exact, regex_list, _types = _index('zh-CN')

    hit = _match(_normalize(message), exact, regex_list)
    if hit is None and _HTML_RE.search(message):
        # 少量历史消息把 UI 用的 HTML 片段也写进了日志
        # （如登录失败：<a style=...>用户名或密码错误</a>,帐号:...），
        # 剥掉标签后再试一次；译文一律不含 HTML（i18n 红线）。
        hit = _match(_normalize(_HTML_RE.sub('', message)), exact, regex_list)

    if hit is None:
        return message
    key, args = hit
    return _translate(key, args)
