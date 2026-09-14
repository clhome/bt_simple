local html = [[
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title data-i18n-title="御风面板访问警告">御风面板访问警告</title>
    <style>
        body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f8f9fa; color: #333; text-align: center; padding-top: 50px; }
        .container { max-width: 600px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        h1 { color: #e74c3c; font-size: 24px; }
        p { font-size: 16px; line-height: 1.5; color: #666; }
        .footer { margin-top: 20px; font-size: 12px; color: #aaa; }
    </style>
</head>
<body>
    <div class="container">
        <h1 data-i18n="安全防御机制拦截">安全防御机制拦截</h1>
        <p><span data-i18n="您的 IP 在短时间内产生了大量无效的 404 请求，已触发本站的 ">您的 IP 在短时间内产生了大量无效的 404 请求，已触发本站的 </span><strong data-i18n="一级安全警告">一级安全警告</strong><span data-i18n="。">。</span></p>
        <p data-i18n="请停止自动化探测或检查您的链接是否正确。">请停止自动化探测或检查您的链接是否正确。</p>
        <p data-i18n="当前 IP 已被暂时限制访问 5 分钟，稍后将自动解除。如果您是正常访问，请稍后再试。">当前 IP 已被暂时限制访问 5 分钟，稍后将自动解除。如果您是正常访问，请稍后再试。</p>
        <div class="footer"><span data-i18n="由 御风面板OP防火墙 提供安全防护">由 御风面板OP防火墙 提供安全防护</span></div>
    </div>
<script>
(function(){var D={"zh-TW":{"。":"。","一级安全警告":"一級安全警告","安全防御机制拦截":"安全防禦機制攔截","御风面板访问警告":"御風面板訪問警告","您的 IP 在短时间内产生了大量无效的 404 请求，已触发本站的 ":"您的 IP 在短時間內產生了大量無效的 404 請求，已觸發本站的 ","当前 IP 已被暂时限制访问 5 分钟，稍后将自动解除。如果您是正常访问，请稍后再试。":"當前 IP 已被暫時限制訪問 5 分鐘，稍後將自動解除。如果您是正常訪問，請稍後再試。","请停止自动化探测或检查您的链接是否正确。":"請停止自動化探測或檢查您的鏈接是否正確。","由 御风面板OP防火墙 提供安全防护":"由 御風面板OP防火牆 提供安全防護"},"en":{"。":".","一级安全警告":"Level-1 Security Warning","安全防御机制拦截":"Blocked by Security Defense","御风面板访问警告":"Yufeng Panel Access Warning","您的 IP 在短时间内产生了大量无效的 404 请求，已触发本站的 ":"Your IP has generated a large number of invalid 404 requests in a short period and has triggered ","当前 IP 已被暂时限制访问 5 分钟，稍后将自动解除。如果您是正常访问，请稍后再试。":"Your IP has been temporarily blocked for 5 minutes and will be automatically unblocked shortly. If you are a legitimate visitor, please try again later.","请停止自动化探测或检查您的链接是否正确。":"Please stop automated probing or check whether your link is correct.","由 御风面板OP防火墙 提供安全防护":"Protected by Yufeng Panel OP Firewall"},"de":{"。":".","一级安全警告":"Sicherheitswarnung Stufe 1","安全防御机制拦截":"Durch Sicherheitsabwehr blockiert","御风面板访问警告":"Yufeng Panel Zugriffswarnung","您的 IP 在短时间内产生了大量无效的 404 请求，已触发本站的 ":"Ihre IP hat in kurzer Zeit eine große Anzahl ungültiger 404-Anfragen erzeugt und hat die folgende Warnung ausgelöst: ","当前 IP 已被暂时限制访问 5 分钟，稍后将自动解除。如果您是正常访问，请稍后再试。":"Ihre IP wurde vorübergehend für 5 Minuten gesperrt und wird in Kürze automatisch entsperrt. Wenn Sie ein legitimer Besucher sind, versuchen Sie es später erneut.","请停止自动化探测或检查您的链接是否正确。":"Bitte stellen Sie automatisierte Sondierungen ein oder prüfen Sie, ob Ihr Link korrekt ist.","由 御风面板OP防火墙 提供安全防护":"Geschützt durch Yufeng Panel OP Firewall"},"fr":{"。":".","一级安全警告":"Avertissement de sécurité niveau 1","安全防御机制拦截":"Bloqué par le système de défense","御风面板访问警告":"Avertissement d'accès au panneau Yufeng","您的 IP 在短时间内产生了大量无效的 404 请求，已触发本站的 ":"Votre IP a généré un grand nombre de requêtes 404 invalides en peu de temps et a déclenché l'avertissement suivant : ","当前 IP 已被暂时限制访问 5 分钟，稍后将自动解除。如果您是正常访问，请稍后再试。":"Votre IP a été temporairement bloquée pendant 5 minutes et sera débloquée automatiquement sous peu. Si vous êtes un visiteur légitime, veuillez réessayer plus tard.","请停止自动化探测或检查您的链接是否正确。":"Veuillez cesser le sondage automatisé ou vérifier si votre lien est correct.","由 御风面板OP防火墙 提供安全防护":"Protégé par le pare-feu OP du panneau Yufeng"},"it":{"。":".","一级安全警告":"Avviso di sicurezza di livello 1","安全防御机制拦截":"Bloccato dal sistema di difesa","御风面板访问警告":"Avviso di accesso al pannello Yufeng","您的 IP 在短时间内产生了大量无效的 404 请求，已触发本站的 ":"Il tuo IP ha generato un gran numero di richieste 404 non valide in breve tempo e ha attivato il seguente avviso: ","当前 IP 已被暂时限制访问 5 分钟，稍后将自动解除。如果您是正常访问，请稍后再试。":"Il tuo IP è stato temporaneamente bloccato per 5 minuti e verrà sbloccato automaticamente a breve. Se sei un visitatore legittimo, riprova più tardi.","请停止自动化探测或检查您的链接是否正确。":"Interrompi la scansione automatizzata o verifica che il tuo link sia corretto.","由 御风面板OP防火墙 提供安全防护":"Protetto dal firewall OP del pannello Yufeng"}};var m=/[?&]lang=([A-Za-z-]+)/.exec(location.search);var L=m?m[1]:(navigator.language||"zh-CN");if(D[L]===undefined){var b=L.split("-")[0].toLowerCase();if(b==="zh"){L="zh-CN";}else{for(var k in D){if(k.split("-")[0].toLowerCase()===b){L=k;break;}}}}var T=D[L];if(!T)return;function tr(k){return T[k]||k;}var ns=document.querySelectorAll("[data-i18n]");for(var i=0;i<ns.length;i++){var n=ns[i];n.textContent=tr(n.getAttribute("data-i18n"));}var ts=document.querySelectorAll("[data-i18n-title]");for(var j=0;j<ts.length;j++){document.title=tr(ts[j].getAttribute("data-i18n-title"));}})();
</script>
</body>
</html>
]]
return html
