# -*- coding: utf-8 -*-
"""
御风面板 (bt_simple) 完整多语言词库构建器
生成 zh-CN, zh-TW, en, fr, de, it 全套语言包
"""

import os
import re
import json
import sys

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

BASE_LANG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../web/static/language"))
SRC_DIR = os.path.join(BASE_LANG_DIR, "zh-CN")

from generate_languages import to_traditional_chinese, LANGUAGES
from phrases_data import CORE_PHRASES
from phrases_enhanced import LAN_MSGS_FULL, LAN_INDEX, TEMPLATE_MENU, TEMPLATE_LOGIN
from phrases_full import FULL_I18N_DICTIONARY

# 模式替换字典（支持带参数模板）
PATTERN_TRANSLATIONS = [
    # 消息类
    (r"成功删除\[\{1\}\]个任务!", {
        "en": "Successfully deleted {1} tasks!",
        "fr": "Suppression réussie de {1} tâches!",
        "de": "Erfolgreich {1} Aufgaben gelöscht!",
        "it": "Eliminate con successo {1} attività!"
    }),
    (r"成功添加\[\{1\}\]个计划任务!", {
        "en": "Successfully added {1} scheduled tasks!",
        "fr": "Ajout réussi de {1} tâches planifiées!",
        "de": "Erfolgreich {1} geplante Aufgaben hinzugefügt!",
        "it": "Aggiunte con successo {1} attività pianificate!"
    }),
    (r"成功删除\{1\}个FTP帐户", {
        "en": "Successfully deleted {1} FTP accounts",
        "fr": "Suppression réussie de {1} comptes FTP",
        "de": "Erfolgreich {1} FTP-Konten gelöscht",
        "it": "Eliminati con successo {1} account FTP"
    }),
    (r"成功删除\[\{1\}\]个数据库!", {
        "en": "Successfully deleted {1} databases!",
        "fr": "Suppression réussie de {1} bases de données!",
        "de": "Erfolgreich {1} Datenbanken gelöscht!",
        "it": "Eliminati con successo {1} database!"
    }),
    (r"成功删除\[\{1\}\]个站点!", {
        "en": "Successfully deleted {1} sites!",
        "fr": "Suppression réussie de {1} sites!",
        "de": "Erfolgreich {1} Websites gelöscht!",
        "it": "Eliminati con successo {1} siti!"
    }),
    (r"您真的要删除\[\{1\}\]吗？", {
        "en": "Are you sure you want to delete [{1}]?",
        "fr": "Voulez-vous vraiment supprimer [{1}] ?",
        "de": "Möchten Sie [{1}] wirklich löschen?",
        "it": "Sei sicuro di voler eliminare [{1}]?"
    }),
    (r"您确定要删除该任务吗\?", {
        "en": "Are you sure you want to delete this task?",
        "fr": "Êtes-vous sûr de vouloir supprimer cette tâche ?",
        "de": "Möchten Sie diese Aufgabe wirklich löschen?",
        "it": "Sei sicuro di voler eliminare questa attività?"
    }),
    (r"您确实要把此文件\[\{1\}\]放入回收站吗\?", {
        "en": "Are you sure you want to move this file [{1}] to the recycle bin?",
        "fr": "Voulez-vous vraiment mettre ce fichier [{1}] dans la corbeille ?",
        "de": "Möchten Sie diese Datei [{1}] wirklich in den Papierkorb verschieben?",
        "it": "Sei sicuro di voler spostare questo file [{1}] nel cestino?"
    }),
    (r"您确实要把此目录\[\{1\}\]放入回收站吗\?", {
        "en": "Are you sure you want to move this directory [{1}] to the recycle bin?",
        "fr": "Voulez-vous vraiment mettre ce répertoire [{1}] dans la corbeille ?",
        "de": "Möchten Sie dieses Verzeichnis [{1}] wirklich in den Papierkorb verschieben?",
        "it": "Sei sicuro di voler spostare questa cartella [{1}] nel cestino?"
    }),
    (r"您真的要安装\{1\}-\{2\}吗\?", {
        "en": "Are you sure you want to install {1}-{2}?",
        "fr": "Voulez-vous vraiment installer {1}-{2} ?",
        "de": "Möchten Sie {1}-{2} wirklich installieren?",
        "it": "Sei sicuro di voler installare {1}-{2}?"
    }),
    (r"您真的要卸载\[\{1\}-\{2\}\]吗\?", {
        "en": "Are you sure you want to uninstall [{1}-{2}]?",
        "fr": "Voulez-vous vraiment désinstaller [{1}-{2}] ?",
        "de": "Möchten Sie [{1}-{2}] wirklich deinstallieren?",
        "it": "Sei sicuro di voler disinstallare [{1}-{2}]?"
    }),
    (r"结束进程名\[\{1\}\],PID\[\{2\}\]后可能会影响服务器的正常运行，继续吗？", {
        "en": "Terminating process [{1}] (PID: {2}) may affect server operation. Continue?",
        "fr": "Arrêter le processus [{1}] (PID: {2}) peut affecter le serveur. Continuer ?",
        "de": "Das Beenden des Prozesses [{1}] (PID: {2}) kann den Server beeinträchtigen. Fortfahren?",
        "it": "La terminazione del processo [{1}] (PID: {2}) potrebbe influire sul server. Continuare?"
    }),
    (r"成功升级到\{1\}", {
        "en": "Successfully upgraded to {1}",
        "fr": "Mise à niveau réussie vers {1}",
        "de": "Erfolgreich auf {1} aktualisiert",
        "it": "Aggiornato con successo a {1}"
    }),
    (r"网站\[\{1\}\]添加域名\[\{2\}\]成功!", {
        "en": "Successfully added domain [{2}] to site [{1}]!",
        "fr": "Domaine [{2}] ajouté avec succès au site [{1}] !",
        "de": "Domain [{2}] erfolgreich zur Website [{1}] hinzugefügt!",
        "it": "Dominio [{2}] aggiunto con successo al sito [{1}]!"
    }),
    (r"网站\[\{1\}\]删除域名\[\{2\}\]成功!", {
        "en": "Successfully removed domain [{2}] from site [{1}]!",
        "fr": "Domaine [{2}] supprimé avec succès du site [{1}] !",
        "de": "Domain [{2}] erfolgreich von der Website [{1}] entfernt!",
        "it": "Dominio [{2}] rimosso con successo dal sito [{1}]!"
    }),
    (r"添加网站\[\{1\}\]成功!", {
        "en": "Successfully added site [{1}]!",
        "fr": "Site [{1}] ajouté avec succès !",
        "de": "Website [{1}] erfolgreich hinzugefügt!",
        "it": "Sito [{1}] aggiunto con successo!"
    }),
    (r"删除网站\[\{1\}\]成功!", {
        "en": "Successfully deleted site [{1}]!",
        "fr": "Site [{1}] supprimé avec succès !",
        "de": "Website [{1}] erfolgreich gelöscht!",
        "it": "Sito [{1}] eliminato con successo!"
    }),
    (r"用户名或密码错误,您还可以尝试\[\{1\}\]次!", {
        "en": "Invalid username or password, {1} attempts remaining!",
        "fr": "Nom d'utilisateur ou mot de passe incorrect, il vous reste {1} tentatives !",
        "de": "Falscher Benutzername oder Passwort, noch {1} Versuche übrig!",
        "it": "Nome utente o password non validi, rimangono {1} tentativi!"
    }),
    (r"您当前的IP为\[\{1\}\]，请使用正确的IP访问!", {
        "en": "Your current IP is [{1}], please use an authorized IP to access!",
        "fr": "Votre adresse IP actuelle est [{1}], veuillez utiliser une IP autorisée !",
        "de": "Ihre aktuelle IP ist [{1}], bitte verwenden Sie eine autorisierte IP!",
        "it": "Il tuo IP corrente è [{1}], accedi tramite un IP autorizzato!"
    }),
]

def translate_text(text, target_lang):
    """根据目标语言翻译一段文本"""
    if target_lang == "zh-CN":
        return text
    if target_lang == "zh-TW":
        return to_traditional_chinese(text)
    
    # 检查精确匹配
    if text in CORE_PHRASES and target_lang in CORE_PHRASES[text]:
        return CORE_PHRASES[text][target_lang]
    
    # 检查正则模式匹配
    for pattern, trans_map in PATTERN_TRANSLATIONS:
        if re.search(pattern, text) and target_lang in trans_map:
            return trans_map[target_lang]
            
    # 通用替换翻译策略
    res = text
    # 占位符保护
    placeholders = re.findall(r'\{[0-9]+\}', res)
    for idx, p in enumerate(placeholders):
        res = res.replace(p, f"___PH_{idx}___")
        
    # 部分关键短语替换
    for zh, trans in CORE_PHRASES.items():
        if zh in res and target_lang in trans:
            res = res.replace(zh, trans[target_lang])
            
    for idx, p in enumerate(placeholders):
        res = res.replace(f"___PH_{idx}___", p)
        
    return res

def translate_dict(data, target_lang):
    """递归翻译字典结构"""
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            new_dict[k] = translate_dict(v, target_lang)
        return new_dict
    elif isinstance(data, list):
        return [translate_dict(item, target_lang) for item in data]
    elif isinstance(data, str):
        return translate_text(data, target_lang)
    else:
        return data

# 读取源语言文件
def clean_dirty_keys(data):
    """清理遗留的破坏性脏键与 HTML 片段"""
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if "add-tab-btn" in k or "<select" in k or "<table" in k or k.startswith("files_auto_str_"):
                continue
            if isinstance(v, str):
                if "')\">" in v or "');\">" in v or "')>" in v or "');>" in v or "add-tab-btn" in v:
                    continue
                if v.startswith("')") or v.startswith("\\')"):
                    continue
            cleaned[k] = clean_dirty_keys(v)
        return cleaned
    return data


def load_sources():
    with open(os.path.join(SRC_DIR, "public.json"), "r", encoding="utf-8") as f:
        src_pub = clean_dirty_keys(json.load(f))

    with open(os.path.join(SRC_DIR, "template.json"), "r", encoding="utf-8") as f:
        src_tmpl = clean_dirty_keys(json.load(f))

    with open(os.path.join(SRC_DIR, "log.json"), "r", encoding="utf-8") as f:
        src_log = clean_dirty_keys(json.load(f))

    with open(os.path.join(SRC_DIR, "lan.js"), "r", encoding="utf-8") as f:
        lan_content = f.read()

    src_get = {}
    msgs_match = re.search(r'var msgs = (\{[\s\S]*?\n\t*\})', lan_content)
    if msgs_match:
        for k, v in re.findall(r'"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)"', msgs_match.group(1)):
            src_get[k] = v.replace('\\"', '"')

    src_secs = {}
    section_matches = re.findall(r'"([a-zA-Z0-9_]+)"\s*:\s*\{([^}]+)\}', lan_content)
    for sec_name, sec_body in section_matches:
        if sec_name == "get":
            continue
        items = {}
        for k, v in re.findall(r'"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)"', sec_body):
            items[k] = v.replace('\\"', '"')
        src_secs[sec_name] = items

    return src_pub, src_tmpl, src_log, src_get, src_secs



def merge_nested_dict(target, source, code):
    """递归合并多语言字典"""
    for k, v in source.items():
        if isinstance(v, dict):
            # 判断是否是叶子翻译映射
            if any(c in v for c in ["en", "zh-CN", "zh-TW", "fr", "de", "it"]):
                if code in v:
                    target[k] = v[code]
                elif code == "zh-CN":
                    target[k] = v.get("zh-CN", "")
                elif code == "zh-TW":
                    target[k] = v.get("zh-TW", to_traditional_chinese(v.get("zh-CN", "")))
                else:
                    target[k] = v.get(code, v.get("en", ""))
            else:
                if k not in target or not isinstance(target[k], dict):
                    target[k] = {}
                merge_nested_dict(target[k], v, code)
        else:
            target[k] = v

def format_js_obj(obj, indent=2):
    """递归将 Python 字典格式化为合法的 JS 对象字符串"""
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        lines = ["{"]
        items = []
        for k, v in obj.items():
            k_str = json.dumps(k, ensure_ascii=False)
            v_str = format_js_obj(v, indent + 1)
            items.append("\t" * indent + f"{k_str}: {v_str}")
        lines.append(",\n".join(items))
        lines.append("\t" * (indent - 1) + "}")
        return "\n".join(lines)
    else:
        return json.dumps(obj, ensure_ascii=False)

def build_lan_js(target_lang, src_get, src_secs, src_pub=None):
    """为指定语言构建 lan.js 文件字符串"""
    translated_get = {}
    for k, v in src_get.items():
        if k in LAN_MSGS_FULL and target_lang in LAN_MSGS_FULL[k]:
            translated_get[k] = LAN_MSGS_FULL[k][target_lang]
        else:
            translated_get[k] = translate_text(v, target_lang)
    
    lines = ["var lan = {", '\t"get":function(key,args){', '\t\tvar msgs = {']
    get_items = []
    for k, v in translated_get.items():
        get_items.append(f'\t\t\t{json.dumps(k, ensure_ascii=False)}:{json.dumps(v, ensure_ascii=False)}')
    lines.append(",\n".join(get_items))
    lines.append("\t\t}\n")
    lines.append("\t\tif(!msgs[key]) return '';")
    lines.append("\t\tvar msg = msgs[key];")
    lines.append("\t\tfor(var i=0;i<args.length;i++){")
    lines.append("\t\t\tmsg = msg.replace('{'+(i+1)+'}',args[i]+'');")
    lines.append("\t\t}")
    lines.append("\t\treturn msg;")
    lines.append("\t},")
    
    all_sec_names = list(src_secs.keys())
    if "public" not in all_sec_names:
        all_sec_names.insert(0, "public")
    for s in FULL_I18N_DICTIONARY:
        if s not in all_sec_names:
            all_sec_names.append(s)
            
    sec_blocks = []
    for sec_name in all_sec_names:
        sec_data = src_secs.get(sec_name, {})
        if sec_name == "public" and not sec_data and src_pub:
            sec_data = src_pub
            
        translated_sec = {}
        for k, v in sec_data.items():
            if sec_name == "index" and k in LAN_INDEX and target_lang in LAN_INDEX[k]:
                translated_sec[k] = LAN_INDEX[k][target_lang]
            else:
                translated_sec[k] = translate_text(v, target_lang)
                
        if sec_name in FULL_I18N_DICTIONARY:
            merge_nested_dict(translated_sec, FULL_I18N_DICTIONARY[sec_name], target_lang)
                
        sec_str = f'\t{json.dumps(sec_name, ensure_ascii=False)}: ' + format_js_obj(translated_sec, 2)
        sec_blocks.append(sec_str)
        
    lines.append(",\n\n".join(sec_blocks))
    lines.append("};\n")
    return "\n".join(lines)

def run():
    import restore_and_build_high_quality_i18n
    restore_and_build_high_quality_i18n.FULL_I18N_DICTIONARY = FULL_I18N_DICTIONARY
    restore_and_build_high_quality_i18n.run_high_quality_build()

    # 生成 lang.json 和 list.json
    lang_metadata = {
        "default": "zh-CN",
        "supported": LANGUAGES
    }
    with open(os.path.join(BASE_LANG_DIR, "lang.json"), "w", encoding="utf-8", newline='\n') as f:
        json.dump(lang_metadata, f, indent=2, ensure_ascii=False)
        
    list_json_data = [
        {"name": l["code"], "title": l["nativeName"]} for l in LANGUAGES
    ]
    with open(os.path.join(BASE_LANG_DIR, "list.json"), "w", encoding="utf-8", newline='\n') as f:
        json.dump(list_json_data, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    run()

