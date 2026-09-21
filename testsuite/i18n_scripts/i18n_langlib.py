# -*- coding: utf-8 -*-
"""
语言包读写工具库（供其他 i18n 脚本复用）

统一处理：
  - 六语言加载 / 保存
  - 保持各插件原有缩进（默认 4，个别插件为 1）
  - UTF-8 无 BOM、LF 行尾
  - 键集一致性校验
"""
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLUGIN_ROOT = os.path.join(BASE_DIR, 'plugins')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']


def plugin_dir(name):
    return os.path.join(PLUGIN_ROOT, name)


def lang_path(name, lang):
    return os.path.join(PLUGIN_ROOT, name, 'lang', lang + '.json')


def read_text(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def detect_indent(text):
    m = re.search(r'\n(\s+)"', text)
    return len(m.group(1)) if m else 4


def load(name, lang):
    p = lang_path(name, lang)
    if not os.path.exists(p):
        return None
    return json.loads(read_text(p))


def load_all(name):
    return {lang: load(name, lang) for lang in LANGS if os.path.exists(lang_path(name, lang))}


def save(name, lang, data):
    p = lang_path(name, lang)
    indent = detect_indent(read_text(p))
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
        f.write('\n')


def save_all(name, dicts):
    for lang, data in dicts.items():
        if data is not None:
            save(name, lang, data)


def add_key(name, key, translations, overwrite=False):
    """新增键到六语言；translations 为 {lang: value}，缺失语言回退到 zh-CN 值"""
    dicts = load_all(name)
    if 'zh-CN' not in dicts:
        raise RuntimeError('%s 缺少 zh-CN 语言包' % name)
    zh_val = translations.get('zh-CN', key)
    for lang, d in dicts.items():
        if lang in translations:
            v = translations[lang]
        else:
            v = zh_val
        if key in d and not overwrite:
            continue
        d[key] = v
    save_all(name, dicts)


def del_key(name, key):
    dicts = load_all(name)
    n = 0
    for lang, d in dicts.items():
        if d.pop(key, None) is not None:
            n += 1
    save_all(name, dicts)
    return n


def check_consistency(name):
    """返回 {lang: 与 zh-CN 的键集差异}"""
    dicts = load_all(name)
    if 'zh-CN' not in dicts:
        return {'__error__': 'no zh-CN'}
    base = set(dicts['zh-CN'])
    out = {}
    for lang, d in dicts.items():
        if lang == 'zh-CN':
            continue
        diff = set(d) ^ base
        if diff:
            out[lang] = sorted(diff)
    return out
