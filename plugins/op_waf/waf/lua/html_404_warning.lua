local html = [[
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>御风面板访问警告</title>
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
        <h1>安全防御机制拦截</h1>
        <p>您的 IP 在短时间内产生了大量无效的 404 请求，已触发本站的 <strong>一级安全警告</strong>。</p>
        <p>请停止自动化探测或检查您的链接是否正确。</p>
        <p>当前 IP 已被暂时限制访问 5 分钟，稍后将自动解除。如果您是正常访问，请稍后再试。</p>
        <div class="footer">由 御风面板OP防火墙 提供安全防护</div>
    </div>
</body>
</html>
]]
return html
