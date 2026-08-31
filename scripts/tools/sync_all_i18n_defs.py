# -*- coding: utf-8 -*-
"""
同步并深度清洗多语言全量词典至 phrases_full.py，强制 LF 输出全套语言包
"""

import os
import sys
import json

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(TOOLS_DIR)

from build_all_languages import clean_dirty_keys, BASE_LANG_DIR, SRC_DIR
import phrases_full

dict_full = phrases_full.FULL_I18N_DICTIONARY

# 1. common 关键字段
if "common" not in dict_full:
    dict_full["common"] = {}

dict_full["common"]["brand_panel"] = {
    "zh-CN": "御风面板", "zh-TW": "御風面板", "en": "Yufeng Panel", "fr": "Panneau Yufeng", "de": "Yufeng-Panel", "it": "Pannello Yufeng"
}

# 2. public 关键操作按钮与品牌字段
if "public" not in dict_full:
    dict_full["public"] = {}

PUBLIC_ENTRIES = {
    "install": {"zh-CN": "安装", "zh-TW": "安裝", "en": "Install", "fr": "Installer", "de": "Installieren", "it": "Installa"},
    "uninstall": {"zh-CN": "卸载", "zh-TW": "解除安裝", "en": "Uninstall", "fr": "Désinstaller", "de": "Deinstallieren", "it": "Disinstalla"},
    "set": {"zh-CN": "设置", "zh-TW": "設定", "en": "Settings", "fr": "Paramètres", "de": "Einstellungen", "it": "Impostazioni"},
    "update": {"zh-CN": "更新", "zh-TW": "更新", "en": "Update", "fr": "Mettre à jour", "de": "Aktualisieren", "it": "Aggiorna"},
    "unknown": {"zh-CN": "未知", "zh-TW": "未知", "en": "Unknown", "fr": "Inconnu", "de": "Unbekannt", "it": "Sconosciuto"},
    "brand_company": {"zh-CN": "御风科技", "zh-TW": "御風科技", "en": "Yufeng Technology", "fr": "Technologie Yufeng", "de": "Yufeng-Technologie", "it": "Tecnologia Yufeng"},
    "ip_privacy_check": {"zh-CN": "IP隐私安全检测", "zh-TW": "IP隱私安全檢測", "en": "IP Privacy & Security Check", "fr": "Test de confidentialité et sécurité IP", "de": "IP-Datenschutz- und Sicherheitsprüfung", "it": "Controllo privacy e sicurezza IP"},
    "tools_box": {"zh-CN": "御风工具箱", "zh-TW": "御風工具箱", "en": "Yufeng Toolbox", "fr": "Boîte à outils Yufeng", "de": "Yufeng-Toolbox", "it": "Strumenti Yufeng"},
    "company_signature": {"zh-CN": "衢州御风科技有限公司出品", "zh-TW": "衢州御風科技有限公司出品", "en": "Produced by Quzhou Yufeng Technology Co., Ltd.", "fr": "Produit par Quzhou Yufeng Technology Co., Ltd.", "de": "Präsentiert von Quzhou Yufeng Technology Co., Ltd.", "it": "Prodotto da Quzhou Yufeng Technology Co., Ltd."},
    "source_code": {"zh-CN": "源码", "zh-TW": "源碼", "en": "Source Code", "fr": "Code source", "de": "Quellcode", "it": "Codice sorgente"},
    "message_box": {"zh-CN": "消息盒子", "zh-TW": "消息盒子", "en": "Message Box", "fr": "Boîte de messages", "de": "Nachrichtenbox", "it": "Casella messaggi"},
    "task_list": {"zh-CN": "任务列表", "zh-TW": "任務列表", "en": "Task List", "fr": "Liste des tâches", "de": "Aufgabenliste", "it": "Elenco attività"},
    "message_list": {"zh-CN": "消息列表", "zh-TW": "消息列表", "en": "Message List", "fr": "Liste des messages", "de": "Nachrichtenliste", "it": "Elenco messaggi"},
    "execution_log": {"zh-CN": "执行日志", "zh-TW": "執行日誌", "en": "Execution Log", "fr": "Journal d'exécution", "de": "Ausführungsprotokoll", "it": "Registro di esecuzione"},
    "execution_log_1": {"zh-CN": "执行日志", "zh-TW": "執行日誌", "en": "Execution Log", "fr": "Journal d'exécution", "de": "Ausführungsprotokoll", "it": "Registro di esecuzione"},
    "memory_1": {"zh-CN": "内存:", "zh-TW": "記憶體:", "en": "Memory:", "fr": "Mémoire :", "de": "Speicher:", "it": "Memoria:"},
    "uplink": {"zh-CN": "上行:", "zh-TW": "上行:", "en": "Up:", "fr": "Envoi :", "de": "Upload:", "it": "Invio:"},
    "downstream": {"zh-CN": "下行:", "zh-TW": "下行:", "en": "Down:", "fr": "Téléchargement :", "de": "Download:", "it": "Download:"},
    "if_task_has_not": {"zh-CN": "若任务长时间未执行，请尝试在首页点【重启面板】来重置任务队列", "zh-TW": "若任務長時間未執行，請嘗試在首頁點【重啟面板】來重置任務隊列", "en": "If tasks are not executing for a long time, try clicking [Restart Panel] on Homepage to reset task queue", "fr": "Si les tâches ne s'exécutent pas pendant longtemps, essayez de redémarrer le panneau sur la page d'accueil", "de": "Wenn Aufgaben längere Zeit nicht ausgeführt werden, starten Sie das Panel auf der Startseite neu", "it": "Se le attività non vengono eseguite per molto tempo, prova a riavviare il pannello nella Home"},
    "there_are_currently_no": {"zh-CN": "当前没有任务!", "zh-TW": "當前沒有任務!", "en": "There are currently no tasks!", "fr": "Il n'y a actuellement aucune tâche !", "de": "Derzeit keine Aufgaben!", "it": "Al momento non ci sono attività!"},
    "retrieving_logs": {"zh-CN": "正在获取日志...", "zh-TW": "正在獲取日誌...", "en": "Retrieving logs...", "fr": "Récupération des journaux...", "de": "Protokolle abrufen...", "it": "Recupero log in corso..."},
    "completed": {"zh-CN": "已完成", "zh-TW": "已完成", "en": "Completed", "fr": "Terminé", "de": "Abgeschlossen", "it": "Completato"},
    "done": {"zh-CN": "已完成", "zh-TW": "已完成", "en": "Done", "fr": "Terminé", "de": "Fertig", "it": "Fatto"},
    "time_taken": {"zh-CN": "耗时[", "zh-TW": "耗時[", "en": "Time taken [", "fr": "Durée [", "de": "Dauer [", "it": "Tempo impiegato ["},
    "processing_1": {"zh-CN": "处理中", "zh-TW": "處理中", "en": "Processing", "fr": "Traitement en cours", "de": "In Bearbeitung", "it": "In elaborazione"},
    "waiting_1": {"zh-CN": "等待中", "zh-TW": "等待中", "en": "Waiting", "fr": "En attente", "de": "Warten", "it": "In attesa"},
    "installing_1": {"zh-CN": "安装中", "zh-TW": "安裝中", "en": "Installing", "fr": "Installation en cours", "de": "Wird installiert", "it": "Installazione in corso"},
    "installing_2": {"zh-CN": "正在安装", "zh-TW": "正在安裝", "en": "Installing", "fr": "Installation en cours", "de": "Wird installiert", "it": "Installazione in corso"},
    "scanning": {"zh-CN": "正在扫描", "zh-TW": "正在掃描", "en": "Scanning", "fr": "Analyse en cours", "de": "Scannen", "it": "Scansione in corso"},
    "downloading": {"zh-CN": "下载中", "zh-TW": "下載中", "en": "Downloading", "fr": "Téléchargement en cours", "de": "Wird heruntergeladen", "it": "Download in corso"},
    "scan": {"zh-CN": "扫描", "zh-TW": "掃描", "en": "Scan", "fr": "Analyser", "de": "Scannen", "it": "Scansiona"},
    "close": {"zh-CN": "关闭", "zh-TW": "關閉", "en": "Close", "fr": "Fermer", "de": "Schließen", "it": "Chiudi"},
    "del": {"zh-CN": "删除", "zh-TW": "刪除", "en": "Delete", "fr": "Supprimer", "de": "Löschen", "it": "Elimina"},
    "task_name": {"zh-CN": "任务名称", "zh-TW": "任務名稱", "en": "Task Name", "fr": "Nom de la tâche", "de": "Aufgabenname", "it": "Nome attività"},
    "task_time": {"zh-CN": "添加时间", "zh-TW": "添加時間", "en": "Time Added", "fr": "Heure d'ajout", "de": "Hinzugefügt am", "it": "Ora di aggiunta"},
    "task_tip_read": {"zh-CN": "标记已读", "zh-TW": "標記已讀", "en": "Mark as Read", "fr": "Marquer comme lu", "de": "Als gelesen markieren", "it": "Segna come letto"},
    "task_tip_all": {"zh-CN": "全部已读", "zh-TW": "全部已讀", "en": "Mark All Read", "fr": "Tout marquer comme lu", "de": "Alle als gelesen markieren", "it": "Segna tutto come letto"},
    "db_name_msg": {"zh-CN": "请输入数据库名称确认删除:", "zh-TW": "請輸入資料庫名稱確認刪除:", "en": "Please enter database name to confirm deletion:", "fr": "Veuillez entrer le nom de la base pour confirmer la suppression :", "de": "Geben Sie den Datenbanknamen ein, um das Löschen zu bestätigen:", "it": "Inserisci il nome del database per confermare l'eliminazione:"},
    "db_name_err": {"zh-CN": "输入的数据库名称不正确!", "zh-TW": "輸入的資料庫名稱不正確!", "en": "Incorrect database name entered!", "fr": "Nom de base de données incorrect !", "de": "Ungültiger Datenbankname eingegeben!", "it": "Nome database inserito non corretto!"},
    "cal_msg": {"zh-CN": "计算结果：", "zh-TW": "計算結果：", "en": "Calculate: ", "fr": "Résultat du calcul : ", "de": "Berechnungsergebnis: ", "it": "Risultato del calcolo: "},
    "task_close": {"zh-CN": "任务已取消", "zh-TW": "任務已取消", "en": "Task cancelled", "fr": "Tâche annulée", "de": "Aufgabe abgebrochen", "it": "Attività annullata"},
    "task_add": {"zh-CN": "已添加至任务列表", "zh-TW": "已添加至任務列表", "en": "Added to task list", "fr": "Ajouté à la liste des tâches", "de": "Zur Aufgabenliste hinzugefügt", "it": "Aggiunto all'elenco delle attività"},
    "panel_err_empty": {"zh-CN": "所有字段均不能为空", "zh-TW": "所有欄位均不能為空", "en": "All fields cannot be empty", "fr": "Tous les champs sont obligatoires", "de": "Alle Felder dürfen nicht leer sein", "it": "Tutti i campi non possono essere vuoti"}
}

for k, v in PUBLIC_ENTRIES.items():
    dict_full["public"][k] = v

# 3. menu 关键字段
if "menu" not in dict_full:
    dict_full["menu"] = {}

dict_full["menu"]["memuAsoft"] = {"zh-CN": "软件", "zh-TW": "軟體", "en": "Software", "fr": "Logiciels", "de": "Software", "it": "Software"}
dict_full["menu"]["M9"] = {"zh-CN": "软件", "zh-TW": "軟體", "en": "Software", "fr": "Logiciels", "de": "Software", "it": "Software"}
dict_full["menu"]["soft"] = {"zh-CN": "软件", "zh-TW": "軟體", "en": "Software", "fr": "Logiciels", "de": "Software", "it": "Software"}

# 4. index 关键字段
if "index" not in dict_full:
    dict_full["index"] = {}

dict_full["index"]["disk_size_format"] = {
    "zh-CN": "根分区共 {0}, 已用 {1}, 剩余 {2}",
    "zh-TW": "根分區共 {0}, 已用 {1}, 剩餘 {2}",
    "en": "Root {0}, Used {1}, Free {2}",
    "fr": "Racine {0}, Utilisé {1}, Libre {2}",
    "de": "Root {0}, Belegt {1}, Frei {2}",
    "it": "Root {0}, Usato {1}, Libero {2}"
}

# 彻底清洗 dict_full
cleaned_dict_full = clean_dirty_keys(dict_full)

# 写回 phrases_full.py (强制 LF)
py_path = os.path.join(TOOLS_DIR, "phrases_full.py")
with open(py_path, "w", encoding="utf-8", newline='\n') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write('"""\n御风面板 (bt_simple) 完整多语言词库映射总表\n"""\n\n')
    f.write("FULL_I18N_DICTIONARY = ")
    f.write(json.dumps(cleaned_dict_full, indent=4, ensure_ascii=False))
    f.write("\n")
print(f"Cleaned and saved {py_path}")

# 5. 清洗 zh-CN/template.json (强制 LF)
zh_tmpl_path = os.path.join(SRC_DIR, "template.json")
with open(zh_tmpl_path, "r", encoding="utf-8") as f:
    raw = json.load(f)

cleaned_tmpl = clean_dirty_keys(raw)
with open(zh_tmpl_path, "w", encoding="utf-8", newline='\n') as f:
    json.dump(cleaned_tmpl, f, indent=2, ensure_ascii=False)
print("Cleaned and saved zh-CN/template.json")

# 6. 清洗 zh-CN/lan.js (强制 LF)
zh_lan_path = os.path.join(SRC_DIR, "lan.js")
with open(zh_lan_path, "r", encoding="utf-8") as f:
    lan_lines = f.read().splitlines()
cleaned_lines = [l for l in lan_lines if "files_auto_str_" not in l and "\\')\">" not in l and "')\">" not in l]
with open(zh_lan_path, "w", encoding="utf-8", newline='\n') as f:
    f.write("\n".join(cleaned_lines) + "\n")
print("Cleaned and saved zh-CN/lan.js")

# 7. 运行高质量母语构建
import importlib
import restore_and_build_high_quality_i18n
importlib.reload(restore_and_build_high_quality_i18n)
restore_and_build_high_quality_i18n.FULL_I18N_DICTIONARY = cleaned_dict_full
restore_and_build_high_quality_i18n.run_high_quality_build()

# 8. 确保所有 static/language 下的文件全部为 LF
for root, dirs, files in os.walk(BASE_LANG_DIR):
    for fn in files:
        if fn.endswith(('.json', '.js')):
            fp = os.path.join(root, fn)
            with open(fp, 'rb') as f:
                content = f.read()
            if b'\r\n' in content:
                content = content.replace(b'\r\n', b'\n')
                with open(fp, 'wb') as f:
                    f.write(content)

print("All language bundles successfully built with LF line endings!")

