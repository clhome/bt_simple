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
        if len(parts) > 1:
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
        if hasattr(g, 'lang') and g.lang:
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
    except Exception:
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

def t(key, *args, lang=None):
    """
    后端翻译主函数
    支持点号键查找及参数格式化
    """
    if not key or not isinstance(key, str):
        return ""
        
    target_lang = normalize_lang(lang) or get_current_lang()
    
    # 优先从 public.json 中查找
    public_dict = get_cached_json("public", target_lang)
    msg = None
    
    if key in public_dict:
        msg = public_dict[key]
    else:
        # 支持点号分割如 "index.memre", "login.N1"
        if "." in key:
            parts = key.split(".", 1)
            sec = parts[0]
            sub_key = parts[1]
            sec_dict = get_cached_json(sec, target_lang)
            if sub_key in sec_dict:
                msg = sec_dict[sub_key]
            else:
                tmpl_dict = get_cached_json("template", target_lang)
                if sec in tmpl_dict and isinstance(tmpl_dict[sec], dict) and sub_key in tmpl_dict[sec]:
                    msg = tmpl_dict[sec][sub_key]
                    
    if msg is None:
        # 尝试回退默认语言
        if target_lang != DEFAULT_LANG:
            default_dict = get_cached_json("public", DEFAULT_LANG)
            if key in default_dict:
                msg = default_dict[key]
                
    if msg is None:
        msg = key

    # 参数替换: {1}, {2}, ... 及 {0}, {1}, ...
    if args:
        for idx, arg in enumerate(args):
            msg = msg.replace("{" + str(idx + 1) + "}", str(arg))
            msg = msg.replace("{" + str(idx) + "}", str(arg))
            
    return msg
