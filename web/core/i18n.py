# -*- coding: utf-8 -*-
"""
御风面板 (bt_simple) 后端 i18n 多语言核心模块
支持 6 种语言：zh-CN, zh-TW, en, fr, de, it
"""

import os
import json
import functools

try:
    from core.resources import get_i18n_cache_size as _get_i18n_cache_size
    _I18N_LRU_SIZE = _get_i18n_cache_size()
except Exception:
    _I18N_LRU_SIZE = 128

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

# 兼容垫片与主菜单分片（参考/优化260910.md §4 / P-2：一个主菜单一个翻译文件）
# 每语言仅 10 个文件：9 主菜单分片 template.<menu>.json + 兼容垫片 template.json
# 垫片由 scripts/tools/merge_template_by_menu_v2.py 从 9 分片重建，二者必须同步存在
_MENU_NAMES = ("index", "site", "files", "security", "crontab", "monitor", "logs", "soft", "setting")

# template.json 顶级 section -> 主菜单分片归属（与 merge 脚本 MENU_SECTIONS 保持一致）
_SECTION_TO_MENU = {
    "index": "index", "dashboard": "index", "menu": "index", "auth": "index",
    "login": "index", "close": "index", "admin": "index", "task": "index",
    "site": "site", "database": "site", "ftp": "site",
    "files": "files", "file": "files", "upload": "files",
    "firewall": "security", "ssh": "security",
    "crontab": "crontab",
    "control": "monitor", "system": "monitor",
    "logs": "logs",
    "soft": "soft", "plugins": "soft", "plugin": "soft", "jdk": "soft", "python_yf": "soft",
    "config": "setting", "setting": "setting", "common": "setting",
    "public": "setting", "utils": "setting",
}

# 无点号 flat 键的确定性查找顺序（分片中 flat 键的唯一归属，首个命中即返回）
_FLAT_MENU_ORDER = ("index", "files", "crontab", "setting")

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

_FILE_LANG_CACHE = None
_FILE_LANG_CACHE_TIME = 0

def _get_file_lang():
    global _FILE_LANG_CACHE, _FILE_LANG_CACHE_TIME
    import time
    now = time.time()
    if _FILE_LANG_CACHE and (now - _FILE_LANG_CACHE_TIME < 60):
        return _FILE_LANG_CACHE
    try:
        import core.yf as yf
        panel_dir = yf.getPanelDir()
        path = os.path.join(panel_dir, 'data/language.pl')
        if os.path.exists(path):
            file_lang = normalize_lang(yf.readFile(path).strip())
            if file_lang and file_lang in SUPPORTED_CODES:
                _FILE_LANG_CACHE = file_lang
                _FILE_LANG_CACHE_TIME = now
                return file_lang
    except Exception:
        pass
    _FILE_LANG_CACHE = DEFAULT_LANG
    _FILE_LANG_CACHE_TIME = now
    return _FILE_LANG_CACHE

def get_current_lang():
    """获取当前请求的语言"""
    # 1. 尝试从 Flask 上下文 g 中读取
    try:
        from flask import g, request
        if getattr(g, 'lang', None):
            return g.lang
            
        # 2. 检查 URL query 参数
        if request and getattr(request, 'args', None):
            url_lang = normalize_lang(request.args.get('lang', ''))
            if url_lang and url_lang in SUPPORTED_CODES:
                g.lang = url_lang
                return url_lang
                
        # 3. 检查 Cookie yf_lang
        if request and getattr(request, 'cookies', None):
            cookie_lang = normalize_lang(request.cookies.get('yf_lang', ''))
            if cookie_lang and cookie_lang in SUPPORTED_CODES:
                g.lang = cookie_lang
                return cookie_lang
                
        # 4. 检查 Accept-Language 头
        if request and getattr(request, 'headers', None):
            accept_lang = parse_accept_language(request.headers.get('Accept-Language', ''))
            if accept_lang:
                g.lang = accept_lang
                return accept_lang
                
        # 如果请求上下文中没有明确指定语言，读取全局配置并缓存到 g 中
        file_lang = _get_file_lang()
        g.lang = file_lang
        return file_lang
    except (RuntimeError, ImportError):
        # 非请求上下文或 flask 未安装时安全忽略
        pass

    # 5. 非请求上下文，直接返回带缓存的全局配置语言
    return _get_file_lang()

@functools.lru_cache(maxsize=_I18N_LRU_SIZE)
def _load_menu_shard(menu, lang):
    """加载单个主菜单分片 template.<menu>.json（低配每页仅触达 1~2 个分片）"""
    norm_lang = normalize_lang(lang) or DEFAULT_LANG
    filepath = os.path.join(_LANG_DIR, norm_lang, "template.%s.json" % menu)
    if not os.path.exists(filepath):
        filepath = os.path.join(_LANG_DIR, DEFAULT_LANG, "template.%s.json" % menu)
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _get_template_menu(menu, lang):
    """按主菜单取翻译词典；分片缺失时回退兼容垫片 template.json 中该菜单 section"""
    data = _load_menu_shard(menu, lang)
    if data is None:
        data = {}
    if not data:
        shim = get_cached_json("template", lang)
        if isinstance(shim, dict) and isinstance(shim.get(menu), dict):
            return shim[menu]
    return data

@functools.lru_cache(maxsize=_I18N_LRU_SIZE)
def get_cached_json(name, lang):
    """读取并缓存指定语言的 JSON 文件；支持 template.<section> 按路由懒加载（low档首屏-50KB）"""
    norm_lang = normalize_lang(lang) or DEFAULT_LANG
    # 点号拆包：template.xxx 优先走主菜单分片（9 分片其一），缺失再回退整包垫片
    if "." in name:
        base, sub = name.split(".", 1)
        if base == "template" and sub in _SECTION_TO_MENU:
            menu = _SECTION_TO_MENU[sub]
            menu_dict = _get_template_menu(menu, lang)
            if isinstance(menu_dict.get(sub), dict):
                return menu_dict[sub]
            if sub in menu_dict:
                return menu_dict[sub]
            return {}
        # 兼容旧路径：template.<section>.json 已随合并删除，尝试垫片取子键
        try:
            fallback = get_cached_json(base, lang) if base != name else {}
            if isinstance(fallback, dict) and sub in fallback:
                return fallback[sub] if not isinstance(fallback[sub], str) else {sub: fallback[sub]}
        except Exception:
            pass
        return {}
    filepath = os.path.join(_LANG_DIR, norm_lang, f"{name}.json")
    if not os.path.exists(filepath):
        filepath = os.path.join(_LANG_DIR, DEFAULT_LANG, f"{name}.json")
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _is_web_request():
    try:
        from flask import has_request_context
        return has_request_context()
    except Exception:
        return False

def _lookup_message(key, lang):
    # 插件私有散列 key (k_xxxx) 仅在前端或插件本地起效，绝不在全局词典中，0ms 快速短路
    if key.startswith("k_"):
        return None

    # 1. 查找 public.json
    pub = get_cached_json("public", lang)
    if key in pub and isinstance(pub[key], str):
        return pub[key]

    # 2. 查找 server.json
    srv = get_cached_json("server", lang)
    if key in srv and isinstance(srv[key], str):
        return srv[key]

    # 3. 主菜单分片查找（9 分片之一，每请求仅触达 1~2 个文件）
    #    点号键：首个段映射主菜单（site.H1 -> template.site.json）
    #    无点号键：flat 归属确定性顺序 index -> files -> crontab -> setting
    if "." in key:
        sec, sub_key = key.split(".", 1)
        if sec != "template":
            menu = _SECTION_TO_MENU.get(sec)
            if menu:
                menu_dict = _get_template_menu(menu, lang)
                curr = menu_dict.get(sec)
                if isinstance(curr, dict):
                    if sub_key in curr and isinstance(curr[sub_key], str):
                        return curr[sub_key]
                    # 深层点号：sec.sub.sub2
                    cur = curr
                    for p in sub_key.split("."):
                        if isinstance(cur, dict) and p in cur:
                            cur = cur[p]
                        else:
                            cur = None
                            break
                    if isinstance(cur, str):
                        return cur
                elif isinstance(curr, str) and sub_key == "":
                    return curr
        # section 未映射或未命中：回退垫片整包深度查找
        tmpl = get_cached_json("template", lang)
        curr = tmpl
        for p in key.split("."):
            if isinstance(curr, dict) and p in curr:
                curr = curr[p]
            else:
                curr = None
                break
        if isinstance(curr, str):
            return curr
        # 点号键在分片 section 内命中（sec.flat 形态）
        if sec in tmpl and isinstance(tmpl.get(sec), dict) and sub_key in tmpl[sec] and isinstance(tmpl[sec][sub_key], str):
            return tmpl[sec][sub_key]
        return None

    # 无点号 flat 键：确定性顺序命中即返回
    for menu in _FLAT_MENU_ORDER:
        menu_dict = _get_template_menu(menu, lang)
        if key in menu_dict and isinstance(menu_dict[key], str):
            return menu_dict[key]
    return None

_HTML_RE = None
def _get_html_re():
    global _HTML_RE
    if _HTML_RE is None:
        import re as _re
        _HTML_RE = _re.compile(r"<[a-zA-Z][^>]*>")
    return _HTML_RE

def escape_html(text):
    import html as _html
    if text is None:
        return ""
    return _html.escape(str(text), quote=True)

def strip_html(text):
    import re as _re
    if not text or not isinstance(text, str):
        return ""
    return _re.sub(r"<[^>]*>", "", text).strip()

def is_html_value(value):
    if not isinstance(value, str):
        return False
    return bool(_get_html_re().search(value))

def assert_no_html_in_translations(raise_on_error=True):
    errors = []
    for lang in SUPPORTED_CODES:
        for sec in ["public", "template", "log", "server"]:
            try:
                data = get_cached_json(sec, lang)
            except Exception:
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
                    elif isinstance(v, str) and is_html_value(v):
                        errors.append(f"{lang}/{sec}.{key}")
    if errors and raise_on_error:
        raise ValueError("[i18n] HTML found in translations (move HTML to template): " + ", ".join(errors[:10]))
    return errors

def t(key, *args, lang=None):
    """
    后端翻译主函数
    支持点号键查找、多词典回退及参数格式化（%s、{0}、{1}等）
    默认对插值参数做 HTML 转义，翻译本身若含 HTML 会被剥离并告警
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

    if isinstance(msg, str) and is_html_value(msg):
        try:
            import logging
            logging.warning("[i18n] translation %s contains HTML, stripped", key)
        except Exception:
            pass
        msg = strip_html(msg)

    if args:
        escaped_args = tuple(escape_html(a) for a in args)
        if '%s' in msg and msg.count('%s') == len(args):
            try:
                return msg % escaped_args
            except TypeError:
                pass
                
        import re
        has_zero = '{0}' in msg
        def _fmt_sub(m):
            num = int(m.group(1))
            if has_zero:
                if 0 <= num < len(escaped_args):
                    return str(escaped_args[num])
            else:
                if 1 <= num <= len(escaped_args):
                    return str(escaped_args[num - 1])
                elif 0 <= num < len(escaped_args):
                    return str(escaped_args[num])
            return m.group(0)
            
        msg = re.sub(r'\{(\d+)\}', _fmt_sub, msg)
            
    return msg

def t_html(key, lang=None, **kwargs):
    msg = t(key, lang=lang)
    if not msg:
        return ""
    import re as _re
    def _repl(m):
        k = m.group(1)
        v = kwargs.get(k, "")
        if v is None:
            return ""
        if k.startswith("html_"):
            return str(v)
        return escape_html(v)
    return _re.sub(r"\{(\w+)\}", _repl, msg)

def t_named(key, lang=None, **kwargs):
    msg = t(key, lang=lang)
    if not msg:
        return ""
    import re as _re
    def _repl(m):
        k = m.group(1)
        if k in kwargs:
            return escape_html(kwargs[k])
        return m.group(0)
    return _re.sub(r"\{(\w+)\}", _repl, msg)
