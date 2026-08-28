# -*- coding: utf-8 -*-
"""
御风面板 (bt_simple) 增强型专业多语言全量词库映射表
支持精准覆盖所有 key 的 6 语言翻译
"""

# lan.js msgs (lan.get)
LAN_MSGS_FULL = {
    "diskinfo_span_1": {
        "en": "Available capacity of disk partition [{1}] is less than 1GB, which may cause MySQL to stop or panel to be inaccessible. Please clean up in time!",
        "fr": "L'espace disponible sur la partition de disque [{1}] est inférieur à 1 Go, ce qui peut entraîner l'arrêt de MySQL ou rendre le panneau inaccessible. Veuillez nettoyer à temps !",
        "de": "Die verfügbare Kapazität der Festplattenpartition [{1}] beträgt weniger als 1 GB, was zum Stoppen von MySQL oder zur Nichtverfügbarkeit des Panels führen kann. Bitte rechtzeitig bereinigen!",
        "it": "La capacità disponibile della partizione disco [{1}] è inferiore a 1 GB, il che potrebbe causare l'arresto di MySQL o l'inaccessibilità del pannello. Si prega di liberare spazio in tempo!"
    },
    "process_kill_confirm": {
        "en": "Terminating process [{1}] (PID: {2}) may affect normal server operation. Continue?",
        "fr": "L'arrêt du processus [{1}] (PID: {2}) peut affecter le fonctionnement normal du serveur. Continuer ?",
        "de": "Das Beenden des Prozesses [{1}] (PID: {2}) kann den normalen Serverbetrieb beeinträchtigen. Fortfahren?",
        "it": "L'arresto del processo [{1}] (PID: {2}) potrebbe influire sul normale funzionamento del server. Continuare?"
    },
    "del": {
        "en": "Delete [{1}]", "fr": "Supprimer [{1}]", "de": "[{1}] löschen", "it": "Elimina [{1}]"
    },
    "del_all_task": {
        "en": "You have selected [{1}] tasks. Once deleted, they cannot be recovered. Are you sure you want to delete them?",
        "fr": "Vous avez sélectionné [{1}] tâches. Une fois supprimées, elles ne peuvent pas être récupérées. Êtes-vous sûr de vouloir les supprimer ?",
        "de": "Sie haben [{1}] Aufgaben ausgewählt. Nach dem Löschen können sie nicht wiederhergestellt werden. Wirklich löschen?",
        "it": "Hai selezionato [{1}] attività. Una volta eliminate, non potranno essere recuperate. Sei sicuro di volerle eliminare?"
    },
    "del_all_task_ok": {
        "en": "Successfully deleted [{1}] tasks!", "fr": "[{1}] tâches supprimées avec succès !", "de": "[{1}] Aufgaben erfolgreich gelöscht!", "it": "[{1}] attività eliminate con successo!"
    },
    "del_all_task_the": {
        "en": "Deleting [{1}], please wait...", "fr": "Suppression de [{1}] en cours, veuillez patienter...", "de": "[{1}] wird gelöscht, bitte warten...", "it": "Eliminazione di [{1}] in corso, attendere..."
    },
    "add_all_task_ok": {
        "en": "Successfully added [{1}] scheduled tasks!", "fr": "[{1}] tâches planifiées ajoutées avec succès !", "de": "[{1}] geplante Aufgaben erfolgreich hinzugefügt!", "it": "[{1}] attività pianificate aggiunte con successo!"
    },
    "add": {
        "en": "Adding [{1}], please wait...", "fr": "Ajout de [{1}] en cours, veuillez patienter...", "de": "[{1}] wird hinzugefügt, bitte warten...", "it": "Aggiunta di [{1}] in corso, attendere..."
    },
    "confirm_del": {
        "en": "Are you sure you want to delete [{1}]?", "fr": "Voulez-vous vraiment supprimer [{1}] ?", "de": "Möchten Sie [{1}] wirklich löschen?", "it": "Sei sicuro di voler eliminare [{1}]?"
    },
    "update_num": {
        "en": "Only {1} files can be uploaded at a time. The rest will be ignored!",
        "fr": "Seuls {1} fichiers peuvent être téléversés à la fois. Les autres seront ignorés !",
        "de": "Es können nur {1} Dateien gleichzeitig hochgeladen werden. Der Rest wird ignoriert!",
        "it": "È possibile caricare solo {1} file alla volta. I restanti verranno ignorati!"
    },
    "service_confirm": {
        "en": "Are you sure you want to {1} the {2} service?", "fr": "Voulez-vous vraiment {1} le service {2} ?", "de": "Möchten Sie den Dienst {2} wirklich {1}?", "it": "Sei sicuro di voler {1} il servizio {2}?"
    },
    "service_the": {
        "en": "{1}ing {2} service, please wait...", "fr": "{1} du service {2} en cours, veuillez patienter...", "de": "Dienst {2} wird {1}, bitte warten...", "it": "{1} del servizio {2} in corso, attendere..."
    },
    "service_ok": {
        "en": "{2} service has been {1}", "fr": "Le service {2} a été {1}", "de": "Dienst {2} wurde {1}", "it": "Il servizio {2} è stato {1}"
    },
    "service_err": {
        "en": "Failed to {1} {2} service!", "fr": "Échec de l'action {1} pour le service {2} !", "de": "{1} für Dienst {2} fehlgeschlagen!", "it": "Impossibile {1} il servizio {2}!"
    },
    "recycle_bin_confirm": {
        "en": "Are you sure you want to move file [{1}] to the recycle bin?", "fr": "Voulez-vous vraiment mettre le fichier [{1}] dans la corbeille ?", "de": "Möchten Sie die Datei [{1}] wirklich in den Papierkorb verschieben?", "it": "Sei sicuro di voler spostare il file [{1}] nel cestino?"
    },
    "recycle_bin_confirm_dir": {
        "en": "Are you sure you want to move directory [{1}] to the recycle bin?", "fr": "Voulez-vous vraiment mettre le répertoire [{1}] dans la corbeille ?", "de": "Möchten Sie das Verzeichnis [{1}] wirklich in den Papierkorb verschieben?", "it": "Sei sicuro di voler spostare la cartella [{1}] nel cestino?"
    },
    "del_all_ftp": {
        "en": "You selected [{1}] FTP accounts. Once deleted, they cannot be recovered. Continue?", "fr": "Vous avez sélectionné [{1}] comptes FTP. Une fois supprimés, ils ne peuvent pas être récupérés. Continuer ?", "de": "Sie haben [{1}] FTP-Konten ausgewählt. Nach dem Löschen können sie nicht wiederhergestellt werden. Fortfahren?", "it": "Hai selezionato [{1}] account FTP. Una volta eliminati, non potranno essere recuperati. Continuare?"
    },
    "del_all_ftp_ok": {
        "en": "Successfully deleted {1} FTP accounts", "fr": "{1} comptes FTP supprimés avec succès", "de": "{1} FTP-Konten erfolgreich gelöscht", "it": "{1} account FTP eliminati con successo"
    },
    "del_all_database": {
        "en": "You selected [{1}] databases. Once deleted, they cannot be recovered. Continue?", "fr": "Vous avez sélectionné [{1}] bases de données. Une fois supprimées, elles ne peuvent pas être récupérées. Continuer ?", "de": "Sie haben [{1}] Datenbanken ausgewählt. Nach dem Löschen können sie nicht wiederhergestellt werden. Fortfahren?", "it": "Hai selezionato [{1}] database. Una volta eliminati, non potranno essere recuperati. Continuare?"
    },
    "del_all_database_ok": {
        "en": "Successfully deleted [{1}] databases!", "fr": "[{1}] bases de données supprimées avec succès !", "de": "[{1}] Datenbanken erfolgreich gelöscht!", "it": "[{1}] database eliminati con successo!"
    },
    "config_edit_ps": {
        "en": "This is the main configuration file for {1}. Please do not modify it if you are not familiar with the rules.",
        "fr": "Il s'agit du fichier de configuration principal pour {1}. Veuillez ne pas le modifier si vous n'êtes pas familier avec les règles.",
        "de": "Dies ist die Hauptkonfigurationsdatei für {1}. Bitte ändern Sie sie nicht, wenn Sie mit den Regeln nicht vertraut sind.",
        "it": "Questo è il file di configurazione principale di {1}. Non modificarlo se non si ha familiarità con le regole."
    },
    "install_confirm": {
        "en": "Are you sure you want to install {1}-{2}?", "fr": "Voulez-vous vraiment installer {1}-{2} ?", "de": "Möchten Sie {1}-{2} wirklich installieren?", "it": "Sei sicuro di voler installare {1}-{2}?"
    },
    "del_all_site": {
        "en": "You selected [{1}] sites. Once deleted, they cannot be recovered. Continue?", "fr": "Vous avez sélectionné [{1}] sites. Une fois supprimés, ils ne peuvent pas être récupérés. Continuer ?", "de": "Sie haben [{1}] Websites ausgewählt. Nach dem Löschen können sie nicht wiederhergestellt werden. Fortfahren?", "it": "Hai selezionato [{1}] siti. Una volta eliminati, non potranno essere recuperati. Continuare?"
    },
    "del_all_site_ok": {
        "en": "Successfully deleted [{1}] sites!", "fr": "[{1}] sites supprimés avec succès !", "de": "[{1}] Websites erfolgreich gelöscht!", "it": "[{1}] siti eliminati con successo!"
    },
    "ssl_enable": {
        "en": "You have enabled certificate [{1}]. To turn it off, click the 'Disable SSL' button.",
        "fr": "Vous avez activé le certificat [{1}]. Pour le désactiver, cliquez sur le bouton 'Désactiver SSL'.",
        "de": "Sie haben das Zertifikat [{1}] aktiviert. Klicken Sie auf 'SSL deaktivieren', um es zu schließen.",
        "it": "Hai abilitato il certificato [{1}]. Per disattivarlo, fai clic sul pulsante 'Disattiva SSL'."
    }
}

# 首页 (lan.index)
LAN_INDEX = {
    "memre": {"en": "Release Memory", "fr": "Libérer la mémoire", "de": "Speicher freigeben", "it": "Libera memoria"},
    "memre_ok": {"en": "Released", "fr": "Libéré", "de": "Freigegeben", "it": "Rilasciata"},
    "memre_ok_0": {"en": "Releasing", "fr": "Libération en cours", "de": "Wird freigegeben", "it": "Rilascio in corso"},
    "memre_ok_1": {"en": "Released", "fr": "Mémoire libérée", "de": "Freigegeben", "it": "Rilasciata"},
    "memre_ok_2": {"en": "Optimal", "fr": "Optimal", "de": "Optimal", "it": "Ottimale"},
    "mem_warning": {"en": "Available physical memory is less than 64MB, which may cause MySQL to stop or 502 errors. Please release memory!", "fr": "La mémoire physique disponible est inférieure à 64 Mo, ce qui peut provoquer l'arrêt de MySQL ou des erreurs 502. Veuillez libérer de la mémoire !", "de": "Der verfügbare physische Speicher beträgt weniger als 64 MB, was zu MySQL-Stopps oder 502-Fehlern führen kann. Bitte Speicher freigeben!", "it": "La memoria fisica disponibile è inferiore a 64 MB, il che potrebbe causare l'arresto di MySQL o errori 502. Prova a liberare memoria!"},
    "user_warning": {"en": "Current panel username is admin, which poses a security risk!", "fr": "Le nom d'utilisateur actuel du panneau est admin, ce qui présente un risque de sécurité !", "de": "Der aktuelle Panel-Benutzername ist admin, was ein Sicherheitsrisiko darstellt!", "it": "L'utente attuale del pannello è admin, il che rappresenta un rischio per la sicurezza!"},
    "cpu_core": {"en": "Cores", "fr": "Cœurs", "de": "Kerne", "it": "Core"},
    "interfacespeed": {"en": "Interface Speed", "fr": "Vitesse d'interface", "de": "Schnittstellengeschwindigkeit", "it": "Velocità interfaccia"},
    "package_num": {"en": "Packets", "fr": "Paquets", "de": "Pakete", "it": "Pacchetti"},
    "interface_net": {"en": "Real-time Traffic", "fr": "Trafic en temps réel", "de": "Echtzeit-Netzwerkverkehr", "it": "Traffico in tempo reale"},
    "net_up": {"en": "Outbound", "fr": "Sortant", "de": "Ausgehend", "it": "In uscita"},
    "net_down": {"en": "Inbound", "fr": "Entrant", "de": "Eingehend", "it": "In entrata"},
    "unit": {"en": "Unit", "fr": "Unité", "de": "Einheit", "it": "Unità"},
    "net_font": {"en": "Arial", "fr": "Arial", "de": "Arial", "it": "Arial"},
    "update_go": {"en": "Update Now", "fr": "Mettre à jour", "de": "Jetzt aktualisieren", "it": "Aggiorna ora"},
    "update_get": {"en": "Fetching version info...", "fr": "Récupération des informations de version...", "de": "Versionsinformationen werden abgerufen...", "it": "Recupero informazioni versione..."},
    "update_check": {"en": "Check Update", "fr": "Vérifier la mise à jour", "de": "Auf Updates prüfen", "it": "Verifica aggiornamenti"},
    "update_to": {"en": "Upgrade to", "fr": "Mettre à niveau vers", "de": "Aktualisieren auf", "it": "Aggiorna a"},
    "update_the": {"en": "Upgrading panel...", "fr": "Mise à niveau du panneau en cours...", "de": "Panel wird aktualisiert...", "it": "Aggiornamento del pannello in corso..."},
    "update_ok": {"en": "Upgrade successful!", "fr": "Mise à niveau réussie !", "de": "Aktualisierung erfolgreich!", "it": "Aggiornamento riuscito!"},
    "update_log": {"en": "Changelog", "fr": "Journal des modifications", "de": "Änderungsprotokoll", "it": "Registro modifiche"},
    "reboot_title": {"en": "Safe Server Reboot", "fr": "Redémarrage sécurisé du serveur", "de": "Sicherer Server-Neustart", "it": "Riavvio sicuro del server"},
    "reboot_warning": {"en": "Note: If your server is running inside a container, please cancel.", "fr": "Remarque : si votre serveur est un conteneur, veuillez annuler.", "de": "Hinweis: Wenn Ihr Server ein Container ist, bitte abbrechen.", "it": "Nota: se il server è un container, annulla."},
    "reboot_ps": {"en": "Safe reboot protects file integrity by performing:", "fr": "Le redémarrage sécurisé protège les fichiers en effectuant :", "de": "Sicherer Neustart schützt Daten durch folgende Schritte:", "it": "Il riavvio sicuro protegge l'integrità dei file eseguendo:"},
    "reboot_ps_1": {"en": "1. Stop Web service", "fr": "1. Arrêt du service Web", "de": "1. Web-Dienst stoppen", "it": "1. Arresto del servizio Web"},
    "reboot_ps_2": {"en": "2. Stop MySQL service", "fr": "2. Arrêt du service MySQL", "de": "2. MySQL-Dienst stoppen", "it": "2. Arresto del servizio MySQL"},
    "reboot_ps_3": {"en": "3. Begin server reboot", "fr": "3. Démarrage du redémarrage serveur", "de": "3. Server-Neustart initiieren", "it": "3. Avvio riavvio server"},
    "reboot_ps_4": {"en": "4. Wait for server boot", "fr": "4. Attente du démarrage", "de": "4. Auf Server-Start warten", "it": "4. Attesa avvio server"},
    "reboot_msg_1": {"en": "Stopping Web service...", "fr": "Arrêt du service Web...", "de": "Web-Dienst wird gestoppt...", "it": "Arresto del servizio Web..."},
    "reboot_msg_2": {"en": "Stopping MySQL service...", "fr": "Arrêt du service MySQL...", "de": "MySQL-Dienst wird gestoppt...", "it": "Arresto del servizio MySQL..."},
    "reboot_msg_3": {"en": "Starting server reboot...", "fr": "Démarrage du redémarrage...", "de": "Server-Neustart beginnt...", "it": "Avvio riavvio del server..."},
    "reboot_msg_4": {"en": "Waiting for server to boot...", "fr": "Attente du démarrage du serveur...", "de": "Warte auf Serverstart...", "it": "In attesa dell'avvio del server..."},
    "reboot_msg_5": {"en": "Server rebooted successfully!", "fr": "Serveur redémarré avec succès !", "de": "Server erfolgreich neu gestartet!", "it": "Server riavviato con successo!"},
    "panel_reboot_title": {"en": "Restart Panel Service", "fr": "Redémarrer le service du panneau", "de": "Panel-Dienst neu starten", "it": "Riavvia servizio pannello"},
    "panel_reboot_msg": {"en": "Panel service is about to restart. Continue?", "fr": "Le service du panneau va redémarrer. Continuer ?", "de": "Der Panel-Dienst wird neu gestartet. Fortfahren?", "it": "Il servizio del pannello sta per essere riavviato. Continuare?"},
    "panel_reboot_to": {"en": "Restarting panel service, please wait...", "fr": "Redémarrage du service du panneau, veuillez patienter...", "de": "Panel-Dienst wird neu gestartet...", "it": "Riavvio del servizio del pannello in corso..."},
    "panel_reboot_ok": {"en": "Panel service restarted successfully!", "fr": "Service du panneau redémarré avec succès !", "de": "Panel-Dienst erfolgreich neu gestartet!", "it": "Servizio del pannello riavviato con successo!"},
    "net_dorp_ip": {"en": "Block this IP", "fr": "Bloquer cette IP", "de": "Diese IP sperren", "it": "Blocca questo IP"},
    "net_doup_ip_msg": {"en": "Blocking this IP will prevent access to the server. You can unblock it in Security. Continue?", "fr": "Bloquer cette IP empêchera l'accès au serveur. Vous pouvez la débloquer dans Sécurité. Continuer ?", "de": "Das Sperren dieser IP verhindert den Zugriff auf den Server. Sie können sie unter Sicherheit entsperren. Fortfahren?", "it": "Il blocco di questo IP impedirà l'accesso al server. È possibile sbloccarlo in Sicurezza. Continuare?"},
    "net_doup_ip_ps": {"en": "Manual Block", "fr": "Blocage manuel", "de": "Manuelle Sperre", "it": "Blocco manuale"},
    "net_doup_ip_to": {"en": "Manual Block", "fr": "Blocage manuel", "de": "Manuelle Sperre", "it": "Blocco manuale"},
    "net_status_title": {"en": "Network Status", "fr": "État du réseau", "de": "Netzwerkstatus", "it": "Stato rete"},
    "net_protocol": {"en": "Protocol", "fr": "Protocole", "de": "Protokoll", "it": "Protocollo"},
    "net_address_dst": {"en": "Local Address", "fr": "Adresse locale", "de": "Lokale Adresse", "it": "Indirizzo locale"},
    "net_address_src": {"en": "Remote Address", "fr": "Adresse distante", "de": "Remote-Adresse", "it": "Indirizzo remoto"},
    "net_address_status": {"en": "Status", "fr": "Statut", "de": "Status", "it": "Stato"},
    "net_process": {"en": "Process", "fr": "Processus", "de": "Prozess", "it": "Processo"},
    "net_process_pid": {"en": "PID", "fr": "PID", "de": "PID", "it": "PID"},
    "process_check": {"en": "Analyzing...", "fr": "Analyse en cours...", "de": "Wird analysiert...", "it": "Analisi in corso..."},
    "process_kill": {"en": "Kill", "fr": "Arrêter", "de": "Beenden", "it": "Termina"},
    "process_kill_title": {"en": "Terminate Process", "fr": "Terminer le processus", "de": "Prozess beenden", "it": "Termina processo"},
    "process_title": {"en": "Process Management", "fr": "Gestion des processus", "de": "Prozessverwaltung", "it": "Gestione processi"},
    "process_pid": {"en": "PID", "fr": "PID", "de": "PID", "it": "PID"},
    "process_name": {"en": "Name", "fr": "Nom", "de": "Name", "it": "Nome"},
    "process_cpu": {"en": "CPU", "fr": "CPU", "de": "CPU", "it": "CPU"},
    "process_mem": {"en": "Memory", "fr": "Mémoire", "de": "Speicher", "it": "Memoria"},
    "process_disk": {"en": "Read/Write", "fr": "Lecture/Écriture", "de": "Lesen/Schreiben", "it": "Lettura/Scrittura"},
    "process_status": {"en": "Status", "fr": "Statut", "de": "Status", "it": "Stato"},
    "process_thread": {"en": "Threads", "fr": "Fils", "de": "Threads", "it": "Thread"},
    "process_user": {"en": "User", "fr": "Utilisateur", "de": "Benutzer", "it": "Utente"},
    "process_act": {"en": "Action", "fr": "Action", "de": "Aktion", "it": "Azione"},
    "kill_msg": {"en": "Terminating process...", "fr": "Arrêt du processus...", "de": "Prozess wird beendet...", "it": "Arresto del processo in corso..."},
    "rep_panel_msg": {"en": "This will attempt to verify and repair panel files. Continue?", "fr": "Cela tentera de vérifier et réparer le panneau. Continuer ?", "de": "Dies versucht, das Panel zu überprüfen und zu reparieren. Fortfahren?", "it": "Verrà tentata la verifica e riparazione del pannello. Continuare?"},
    "rep_panel_title": {"en": "Repair Panel", "fr": "Réparer le panneau", "de": "Panel reparieren", "it": "Ripara pannello"},
    "rep_panel_the": {"en": "Verifying modules...", "fr": "Vérification des modules...", "de": "Module werden überprüft...", "it": "Verifica moduli in corso..."},
    "rep_panel_ok": {"en": "Repair complete, please press Ctrl+F5 to refresh cache!", "fr": "Réparation terminée, veuillez appuyer sur Ctrl+F5 pour rafraîchir le cache !", "de": "Reparatur abgeschlossen, bitte drücken Sie Strg+F5, um den Cache zu leeren!", "it": "Riparazione completata, premi Ctrl+F5 per aggiornare la cache!"}
}

# 菜单 (template.menu)
TEMPLATE_MENU = {
    "M1": {"en": "Dashboard", "fr": "Tableau de bord", "de": "Dashboard", "it": "Dashboard"},
    "M2": {"en": "Websites", "fr": "Sites Web", "de": "Websites", "it": "Siti Web"},
    "M3": {"en": "FTP", "fr": "FTP", "de": "FTP", "it": "FTP"},
    "M4": {"en": "Databases", "fr": "Bases de données", "de": "Datenbanken", "it": "Database"},
    "M5": {"en": "Monitoring", "fr": "Surveillance", "de": "Überwachung", "it": "Monitoraggio"},
    "M6": {"en": "Security", "fr": "Sécurité", "de": "Sicherheit", "it": "Sicurezza"},
    "M7": {"en": "Files", "fr": "Fichiers", "de": "Dateien", "it": "File"},
    "M8": {"en": "Cron Tasks", "fr": "Tâches Cron", "de": "Cron-Aufgaben", "it": "Attività Cron"},
    "M9": {"en": "Software", "fr": "Logiciels", "de": "Software", "it": "Software"},
    "M10": {"en": "Settings", "fr": "Paramètres", "de": "Einstellungen", "it": "Impostazioni"},
    "M11": {"en": "Logout", "fr": "Déconnexion", "de": "Abmelden", "it": "Disconnetti"},
    "HELP": {"en": "Help & Support", "fr": "Aide et support", "de": "Hilfe und Support", "it": "Aiuto e supporto"}
}

# 登录 (template.login)
TEMPLATE_LOGIN = {
    "N1": {"en": "Please enter username", "fr": "Veuillez entrer le nom d'utilisateur", "de": "Bitte Benutzernamen eingeben", "it": "Inserisci il nome utente"},
    "N2": {"en": "Incorrect format", "fr": "Format incorrect", "de": "Ungültiges Format", "it": "Formato non corretto"},
    "N3": {"en": "Username", "fr": "Nom d'utilisateur", "de": "Benutzername", "it": "Nome utente"},
    "N4": {"en": "Please enter password", "fr": "Veuillez entrer le mot de passe", "de": "Bitte Passwort eingeben", "it": "Inserisci la password"},
    "N5": {"en": "Please enter password", "fr": "Veuillez entrer le mot de passe", "de": "Bitte Passwort eingeben", "it": "Inserisci la password"},
    "N6": {"en": "Password", "fr": "Mot de passe", "de": "Passwort", "it": "Password"},
    "N7": {"en": "Please enter 4-digit captcha", "fr": "Veuillez entrer le code à 4 chiffres", "de": "Bitte 4-stelligen Captcha-Code eingeben", "it": "Inserisci il codice di 4 cifre"},
    "N8": {"en": "Incorrect captcha", "fr": "Code de vérification incorrect", "de": "Falscher Captcha-Code", "it": "Codice non corretto"},
    "N9": {"en": "Please enter captcha", "fr": "Veuillez entrer le code", "de": "Bitte Captcha eingeben", "it": "Inserisci il captcha"},
    "N10": {"en": "Click to refresh", "fr": "Cliquez pour changer", "de": "Klicken zum Ändern", "it": "Fai clic per cambiare"},
    "N11": {"en": "Log In", "fr": "Se connecter", "de": "Anmelden", "it": "Accedi"},
    "N12": {"en": "Captcha appears after 3 failed login attempts", "fr": "Le code apparaît après 3 échecs", "de": "Captcha erscheint nach 3 Fehlversuchen", "it": "Il captcha compare dopo 3 tentativi falliti"},
    "N13": {"en": "Forgot password >>", "fr": "Mot de passe oublié >>", "de": "Passwort vergessen >>", "it": "Password dimenticata >>"},
    "JS1": {"en": "Form error, please try again!", "fr": "Erreur de formulaire, veuillez réessayer !", "de": "Formularfehler, bitte erneut versuchen!", "it": "Errore nel modulo, riprova!"},
    "JS2": {"en": "Logging in...", "fr": "Connexion en cours...", "de": "Anmeldung läuft...", "it": "Accesso in corso..."}
}

print("Enhanced dictionary definitions loaded successfully.")
