# -*- coding: utf-8 -*-
"""
御风面板多语言词库安全合并与自动扩充工具
"""

import os
import sys
import json
import re

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(TOOLS_DIR)

from generate_languages import to_traditional_chinese
from phrases_data import CORE_PHRASES

def translate_phrase(text, target_lang):
    """根据核心字典或规则将中文翻译成目标语言"""
    if target_lang == "zh-CN":
        return text
    if target_lang == "zh-TW":
        return to_traditional_chinese(text)
    
    if text in CORE_PHRASES and target_lang in CORE_PHRASES[text]:
        return CORE_PHRASES[text][target_lang]
    
    # 常用词汇规则替换
    res = text
    for zh, trans in CORE_PHRASES.items():
        if zh in res and target_lang in trans:
            res = res.replace(zh, trans[target_lang])
    return res

def build_trans_entry(zh_cn_text):
    """为单条中文文本构建 6 国语言结构"""
    return {
        "zh-CN": zh_cn_text,
        "zh-TW": to_traditional_chinese(zh_cn_text),
        "en": translate_phrase(zh_cn_text, "en"),
        "fr": translate_phrase(zh_cn_text, "fr"),
        "de": translate_phrase(zh_cn_text, "de"),
        "it": translate_phrase(zh_cn_text, "it"),
    }

def merge_dict_file(section_name, json_file_path):
    import phrases_full
    dict_full = phrases_full.FULL_I18N_DICTIONARY

    # 1. 修复历史问题（如果有）
    if "menu" in dict_full and "site" in dict_full["menu"] and isinstance(dict_full["menu"]["site"], dict):
        menu_site = dict_full["menu"]["site"]
        # 如果包含 auto_str 则迁移
        auto_keys = [k for k in menu_site if k.startswith("site_auto_str_")]
        if auto_keys:
            if "site" not in dict_full:
                dict_full["site"] = {}
            for k in auto_keys:
                dict_full["site"][k] = menu_site[k]
                del menu_site[k]
            dict_full["menu"]["site"] = {
                "zh-CN": "网站", "zh-TW": "網站", "en": "Websites", "fr": "Sites Web", "de": "Websites", "it": "Siti Web"
            }
            print(f"Fixed menu.site: moved {len(auto_keys)} keys to dict_full['site']")

    if not os.path.exists(json_file_path):
        print(f"File not found: {json_file_path}")
        return

    with open(json_file_path, "r", encoding="utf-8") as f:
        extracted = json.load(f)

    if section_name not in dict_full:
        dict_full[section_name] = {}

    count = 0
    for k, v in extracted.items():
        if k not in dict_full[section_name]:
            dict_full[section_name][k] = build_trans_entry(v)
            count += 1

    print(f"Added {count} new keys to section [{section_name}]")

    # 序列化写回 phrases_full.py
    py_path = os.path.join(TOOLS_DIR, "phrases_full.py")
    with open(py_path, "w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write('"""\n御风面板 (bt_simple) 完整多语言词库映射总表\n"""\n\n')
        f.write("FULL_I18N_DICTIONARY = ")
        f.write(json.dumps(dict_full, indent=4, ensure_ascii=False))
        f.write("\n")

    print(f"Successfully saved updated dictionary to {py_path}")

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        sec = sys.argv[1]
        jpath = sys.argv[2]
        merge_dict_file(sec, jpath)
    else:
        print("Usage: python merge_i18n_dict.py <section_name> <json_file_path>")
