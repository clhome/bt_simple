# -*- coding: utf-8 -*-
"""
bt_simple 插件 i18n 特殊处理规则
处理那些不能简单整串入包的情况：
  - HTML 片段：标签留代码，纯文本入包（红线 1）
  - CSV 表头：保留 \\uFEFF 与 \\n（红线 4）
  - 代码内注释/调试串：跳过
"""

# 需要拆分的 HTML 片段：原串 -> (前缀, 待翻译纯文本, 后缀)
HTML_SPLIT = {
    "<td>永久</td>": ("<td>", "永久", "</td>"),
    "<th>名称(标识)</th>": ("<th>", "名称(标识)", "</th>"),
    ">Master[主]配置</span><span class=": (">", "Master[主]配置", "</span><span class="),
    ">Slave[从]配置</span><span class=": (">", "Slave[从]配置", "</span><span class="),
    ">同步账户[DB]</span><div class=": (">", "同步账户[DB]", "</span><div class="),
    ">应用池[pool]：</span><select class=": (">", "应用池[pool]：", "</span><select class="),
    ">浏览量(PV)<i class=": (">", "浏览量(PV)", "<i class="),
    ">访客量(UV)<i class=": (">", "访客量(UV)", "<i class="),
    "编辑[": ("", "编辑", "["),
}

# HTML 片段内待翻译的纯文本
HTML_TEXT = {
    "永久": {"en": "Permanent", "de": "Dauerhaft", "fr": "Permanent", "it": "Permanente"},
    "名称(标识)": {"en": "Name (identifier)", "de": "Name (Kennung)", "fr": "Nom (identifiant)", "it": "Nome (identificatore)"},
    "Master[主]配置": {"en": "Master configuration", "de": "Master-Konfiguration", "fr": "Configuration maître", "it": "Configurazione master"},
    "Slave[从]配置": {"en": "Slave configuration", "de": "Slave-Konfiguration", "fr": "Configuration esclave", "it": "Configurazione slave"},
    "同步账户[DB]": {"en": "Sync account [DB]", "de": "Synchronisierungskonto [DB]", "fr": "Compte de synchronisation [DB]", "it": "Account di sincronizzazione [DB]"},
    "应用池[pool]：": {"en": "Pool: ", "de": "Pool: ", "fr": "Pool : ", "it": "Pool: "},
    "浏览量(PV)": {"en": "Page views (PV)", "de": "Seitenaufrufe (PV)", "fr": "Pages vues (PV)", "it": "Visualizzazioni (PV)"},
    "访客量(UV)": {"en": "Visitors (UV)", "de": "Besucher (UV)", "fr": "Visiteurs (UV)", "it": "Visitatori (UV)"},
    "编辑": {"en": "Edit", "de": "Bearbeiten", "fr": "Modifier", "it": "Modifica"},
}

# CSV 表头：保留格式控制符，仅翻译字段名
CSV_HEADER = {
    "时间,IP,规则名,原因": {"en": "Time,IP,Rule,Reason", "de": "Zeit,IP,Regel,Grund", "fr": "Heure,IP,Règle,Raison", "it": "Ora,IP,Regola,Motivo"},
    "时间,域名,IP,URI,规则名,原因": {"en": "Time,Domain,IP,URI,Rule,Reason", "de": "Zeit,Domain,IP,URI,Regel,Grund", "fr": "Heure,Domaine,IP,URI,Règle,Raison", "it": "Ora,Dominio,IP,URI,Regola,Motivo"},
}

FINAL = {
    "Dovecot (邮局)": {"en": "Dovecot (mail server)", "de": "Dovecot (Mailserver)", "fr": "Dovecot (serveur mail)", "it": "Dovecot (server mail)"},
    "Postfix (邮局)": {"en": "Postfix (mail server)", "de": "Postfix (Mailserver)", "fr": "Postfix (serveur mail)", "it": "Postfix (server mail)"},
    "编辑[": {"en": "Edit [", "de": "Bearbeiten [", "fr": "Modifier [", "it": "Modifica ["},
    "永久": {"en": "Permanent", "de": "Dauerhaft", "fr": "Permanent", "it": "Permanente"},
    "名称(标识)": {"en": "Name (identifier)", "de": "Name (Kennung)", "fr": "Nom (identifiant)", "it": "Nome (identificatore)"},
    "Master[主]配置": {"en": "Master configuration", "de": "Master-Konfiguration", "fr": "Configuration maître", "it": "Configurazione master"},
    "Slave[从]配置": {"en": "Slave configuration", "de": "Slave-Konfiguration", "fr": "Configuration esclave", "it": "Configurazione slave"},
    "同步账户[DB]": {"en": "Sync account [DB]", "de": "Synchronisierungskonto [DB]", "fr": "Compte de synchronisation [DB]", "it": "Account di sincronizzazione [DB]"},
    "应用池[pool]：": {"en": "Pool: ", "de": "Pool: ", "fr": "Pool : ", "it": "Pool: "},
    "浏览量(PV)": {"en": "Page views (PV)", "de": "Seitenaufrufe (PV)", "fr": "Pages vues (PV)", "it": "Visualizzazioni (PV)"},
    "访客量(UV)": {"en": "Visitors (UV)", "de": "Besucher (UV)", "fr": "Visiteurs (UV)", "it": "Visitatori (UV)"},
    "时间,IP,规则名,原因": {"en": "Time,IP,Rule,Reason", "de": "Zeit,IP,Regel,Grund", "fr": "Heure,IP,Règle,Raison", "it": "Ora,IP,Regola,Motivo"},
    "时间,域名,IP,URI,规则名,原因": {"en": "Time,Domain,IP,URI,Rule,Reason", "de": "Zeit,Domain,IP,URI,Regel,Grund", "fr": "Heure,Domaine,IP,URI,Règle,Raison", "it": "Ora,Dominio,IP,URI,Regola,Motivo"},
}
