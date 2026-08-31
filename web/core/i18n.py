# -*- coding: utf-8 -*-
"""
御风面板 (bt_simple) 后端 i18n 多语言核心模块
支持 6 种语言：zh-CN, zh-TW, en, fr, de, it
"""

import os
import json
import functools

# 支持语言列表
SUPPORTED_LANGUAGES = [
    {"code": "zh-CN", "name": "简体中文", "nativeName": "简体中文"},
    {"code": "zh-TW", "name": "繁体中文", "nativeName": "繁體中文"},
    {"code": "en",    "name": "English",  "nativeName": "English"},
    {"code": "fr",    "name": "Français", "nativeName": "Français"},
    {"code": "de",    "name": "Deutsch",  "nativeName": "Deutsch"},
    {"code": "it",    "name": "Italiano", "nativeName": "Italiano"}
]

SUPPORTED_CODES = [l["code"] for l in SUPPORTED_LANGUAGES]
DEFAULT_LANG = "zh-CN"

LANG_MAP = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-sg": "zh-CN",
    "zh-hans": "zh-CN",
    "zh-tw": "zh-TW",
    "zh-hk": "zh-TW",
    "zh-mo": "zh-TW",
    "zh-hant": "zh-TW",
    "en": "en",
    "en-us": "en",
    "en-gb": "en",
    "en-ca": "en",
    "en-au": "en",
    "fr": "fr",
    "fr-fr": "fr",
    "fr-ca": "fr",
    "fr-be": "fr",
    "fr-ch": "fr",
    "de": "de",
    "de-de": "de",
    "de-at": "de",
    "de-ch": "de",
    "it": "it",
    "it-it": "it",
    "it-ch": "it",
    "simplified_chinese": "zh-CN",
    "traditional_chinese": "zh-TW"
}

_LANG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../static/language"))

def normalize_lang(lang_code):
    """归一化语言代码"""
    if not lang_code or not isinstance(lang_code, str):
        return None
    clean = lang_code.strip().lower().replace("_", "-")
    if clean in LANG_MAP:
        return LANG_MAP[clean]
    prefix = clean.split("-")[0]
    if prefix in LANG_MAP:
        return LANG_MAP[prefix]
    return None

def parse_accept_language(accept_header):
    """解析 HTTP Accept-Language 请求头"""
    if not accept_header:
        return None
    
    # 格式: en-US,en;q=0.9,fr;q=0.8,zh-CN;q=0.7
    items = []
    for piece in accept_header.split(","):
        parts = piece.strip().split(";")
        code = parts[0].strip()
        q = 1.0
        for p in parts[1:]:
            p = p.strip()
            if p.startswith("q="):
                try:
                    q = float(p[2:])
                except ValueError:
                    pass
        items.append((code, q))
        
    items.sort(key=lambda x: x[1], reverse=True)
    for code, _ in items:
        norm = normalize_lang(code)
        if norm and norm in SUPPORTED_CODES:
            return norm
    return None

def get_current_lang():
    """获取当前请求的语言"""
    # 1. 尝试从 Flask 上下文 g 中读取
    try:
        from flask import g, request
        if getattr(g, 'lang', None):
            return g.lang
            
        # 2. 检查 URL query 参数
        if request and request.args:
            url_lang = normalize_lang(request.args.get('lang', ''))
            if url_lang and url_lang in SUPPORTED_CODES:
                return url_lang
                
        # 3. 检查 Cookie yf_lang
        if request and request.cookies:
            cookie_lang = normalize_lang(request.cookies.get('yf_lang', ''))
            if cookie_lang and cookie_lang in SUPPORTED_CODES:
                return cookie_lang
                
        # 4. 检查 Accept-Language 头
        if request and request.headers:
            accept_lang = parse_accept_language(request.headers.get('Accept-Language', ''))
            if accept_lang:
                return accept_lang
    except (RuntimeError, ImportError):
        # 非请求上下文或 flask 未安装时安全忽略
        pass

    # 5. 检查本地配置文件 data/language.pl
    try:
        import core.yf as yf
        panel_dir = yf.getPanelDir()
        path = os.path.join(panel_dir, 'data/language.pl')
        if os.path.exists(path):
            file_lang = normalize_lang(yf.readFile(path).strip())
            if file_lang and file_lang in SUPPORTED_CODES:
                return file_lang
    except Exception:
        pass

    # 6. 默认回退
    return DEFAULT_LANG

@functools.lru_cache(maxsize=128)
def get_cached_json(name, lang):
    """读取并缓存指定语言的 JSON 文件"""
    norm_lang = normalize_lang(lang) or DEFAULT_LANG
    filepath = os.path.join(_LANG_DIR, norm_lang, f"{name}.json")
    if not os.path.exists(filepath):
        # 尝试默认语言回退
        filepath = os.path.join(_LANG_DIR, DEFAULT_LANG, f"{name}.json")
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _lookup_message(key, lang):
    # 1. 查找 public.json
    pub = get_cached_json("public", lang)
    if key in pub:
        return pub[key]
        
    # 2. 查找 server.json
    srv = get_cached_json("server", lang)
    if key in srv:
        return srv[key]
        
    # 3. 点号分割子模块查找
    if "." in key:
        sec, sub_key = key.split(".", 1)
        sec_dict = get_cached_json(sec, lang)
        if sub_key in sec_dict:
            return sec_dict[sub_key]
            
        tmpl = get_cached_json("template", lang)
        if sec in tmpl and isinstance(tmpl[sec], dict) and sub_key in tmpl[sec]:
            return tmpl[sec][sub_key]
        if key in tmpl:
            return tmpl[key]
    else:
        tmpl = get_cached_json("template", lang)
        if key in tmpl and isinstance(tmpl[key], str):
            return tmpl[key]
    return None

def t(key, *args, lang=None):
    """
    后端翻译主函数
    支持点号键查找、多词典回退及参数格式化（%s、{0}、{1}等）
    """
    if not key or not isinstance(key, str):
        return ""
        
    target_lang = normalize_lang(lang) or get_current_lang()
    
    msg = _lookup_message(key, target_lang)
    if msg is None and target_lang != DEFAULT_LANG:
        msg = _lookup_message(key, DEFAULT_LANG)
        
    if msg is None:
        if args and len(args) == 1 and isinstance(args[0], str) and '{' not in key and '%s' not in key and '{1}' not in args[0] and '{0}' not in args[0] and '%s' not in args[0]:
            return args[0]
        msg = key

    # 参数替换: {1}, {2}, ... 及 {0}, {1}, ... 与 %s 支持
    if args:
        if '%s' in msg and msg.count('%s') == len(args):
            try:
                return msg % args
            except TypeError:
                pass
                
        import re
        has_zero = '{0}' in msg
        def _fmt_sub(m):
            num = int(m.group(1))
            if has_zero:
                if 0 <= num < len(args):
                    return str(args[num])
            else:
                if 1 <= num <= len(args):
                    return str(args[num - 1])
                elif 0 <= num < len(args):
                    return str(args[num])
            return m.group(0)
            
        msg = re.sub(r'\{(\d+)\}', _fmt_sub, msg)
            
    return msg
