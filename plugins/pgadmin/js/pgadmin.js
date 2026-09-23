var api = YfPlugin.createApi('pgadmin');
var pt = YfI18n.createPluginTranslator('pgadmin');


function homePage(){
    api.post('get_home_page', '', function(data){
        var rdata = JSON.parse(data.data);
        if (!rdata.status){
            layer.msg(rdata.msg,{icon:0,time:2000,shade: [0.3, '#000']});
            return;
        }
        var con = '<button class="btn btn-default btn-sm" onclick="window.open(\'' + rdata.data + '\')">' + pt('主页') + '</button>';
        $(".soft-man-con").html(con);
    });
}


//pgadmin安全设置
function safeConf() {
    api.post('get_pg_option', {}, function(rdata){
        var rdata = typeof rdata.data === "string" ? JSON.parse(rdata.data) : rdata.data;
        if (!rdata.status){
            layer.msg(rdata.msg,{icon:2,time:2000,shade: [0.3, '#000']});
            return;
        }

        var cfg = rdata.data;
        var con = '<div class="ver line">\
                    <span class="tname">' + pt('访问端口') + '</span>\
                    <input style="width:180px" class="bt-input-text phpmyadmindk mr20" name="port" id="pmport" value="' + cfg['port'] + '" placeholder="pgadmin访问端口" maxlength="5" type="number">\
                    <button class="btn btn-success btn-sm" onclick="setPgPort()">' + pt('保存') + '</button>\
                </div>\
                <div class="ver line">\
                    <span class="tname">' + pt('基础认证用户名') + '</span>\
                    <input style="width:180px" class="bt-input-text mr20" name="basic_username" id="pg_basic_user" value="' + cfg['username'] + '" placeholder="' + pt('基础认证用户名') + '" type="text">\
                    <button class="btn btn-success btn-sm" onclick="setPgUsername()">' + pt('保存') + '</button>\
                </div>\
                <div class="ver line">\
                    <span class="tname">' + pt('基础认证密码') + '</span>\
                    <input style="width:180px" class="bt-input-text mr20" name="basic_password" id="pg_basic_pwd" value="' + cfg['password'] + '" placeholder="' + pt('基础认证密码') + '" type="text">\
                    <button class="btn btn-success btn-sm" onclick="setPgPassword()">' + pt('保存') + '</button>\
                </div>\
                <hr/>\
                <div class="ver line" style="font-weight: bold; margin-bottom: 10px;">' + pt('pgAdmin系统登录信息') + '</div>\
                <div class="ver line">\
                    <span class="tname">' + pt('PG登录邮箱') + '</span>\
                    <input style="width:180px" class="bt-input-text mr20" name="web_pg_username" id="pg_web_user" value="' + cfg['web_pg_username'] + '" placeholder="PG登录邮箱" type="text">\
                    <button class="btn btn-success btn-sm" onclick="setWebPgUsername()">' + pt('保存') + '</button>\
                </div>\
                <div class="ver line">\
                    <span class="tname">' + pt('PG登录密码') + '</span>\
                    <input style="width:180px" class="bt-input-text mr20" name="web_pg_password" id="pg_web_pwd" value="' + cfg['web_pg_password'] + '" placeholder="PG登录密码" type="text">\
                    <button class="btn btn-success btn-sm" onclick="setWebPgPassword()">' + pt('保存') + '</button>\
                </div>';
        $(".soft-man-con").html(con);
    });
}

function setPgUsername(){
    var username = $("#pg_basic_user").val();
    api.post('set_pg_username',{'username':username}, function(data){
        var rdata = JSON.parse(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

function setPgPassword(){
    var password = $("#pg_basic_pwd").val();
    api.post('set_pg_password',{'password':password}, function(data){
        var rdata = JSON.parse(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

function setWebPgUsername(){
    var username = $("#pg_web_user").val();
    api.post('set_web_pg_username',{'username':username}, function(data){
        var rdata = JSON.parse(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

function setWebPgPassword(){
    var password = $("#pg_web_pwd").val();
    api.post('set_web_pg_password',{'password':password}, function(data){
        var rdata = JSON.parse(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

//修改phpmyadmin端口
function setPgPort() {
    var pmport = $("#pmport").val();
    if (pmport < 80 || pmport > 65535) {
        layer.msg(pt('端口范围不合法!'), { icon: 2 });
        return;
    }
    var data = 'port=' + pmport;
    
    api.post('set_pg_port',data, function(data){
        var rdata = JSON.parse(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

function pgService() {
    pluginService('pgadmin');
    setTimeout(function() {
        api.post('get_pg_access_info', '', function(rdata) {
            var data = JSON.parse(rdata.data);
            if (!data.status) {
                return;
            }
            var info = data.data;
            // 这些值都来自 cfg.json（面板上可改），直接拼进 innerHTML 会被
            // 当标签执行 —— 一律先做实体转义再拼接
            var html = '<div class="pma-access-info">' +
                '<div class="pma-info-header">' + pt('访问与认证信息') + '</div>' +
                '<div class="pma-info-body">' +
                    '<div class="pma-info-item">' +
                        '<span class="pma-info-label">' + pt('内网地址：') + '</span>' +
                        '<a href="' + yfMsgEscape(info.internal_url) + '" target="_blank" class="pma-info-value pma-link">' + yfMsgEscape(info.internal_url) + '</a>' +
                    '</div>' +
                    '<div class="pma-info-item">' +
                        '<span class="pma-info-label">' + pt('外网地址：') + '</span>' +
                        '<a href="' + yfMsgEscape(info.external_url) + '" target="_blank" class="pma-info-value pma-link">' + yfMsgEscape(info.external_url) + '</a>' +
                    '</div>' +
                    '<div class="pma-info-item" style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed #eee;">' +
                        '<span class="pma-info-label">' + pt('基础认证账号：') + '</span>' +
                        '<span class="pma-info-value">' + yfMsgEscape(info.username) + '</span>' +
                    '</div>' +
                    '<div class="pma-info-item">' +
                        '<span class="pma-info-label">' + pt('基础认证密码：') + '</span>' +
                        '<span class="pma-info-value">' + yfMsgEscape(info.password) + '</span>' +
                    '</div>' +
                    '<div class="pma-info-item" style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed #eee;">' +
                        '<span class="pma-info-label">' + pt('登录用户名：') + '</span>' +
                        '<span class="pma-info-value">' + yfMsgEscape(info.web_pg_username) + '</span>' +
                    '</div>' +
                    '<div class="pma-info-item">' +
                        '<span class="pma-info-label">' + pt('登录密码：') + '</span>' +
                        '<span class="pma-info-value">' + yfMsgEscape(info.web_pg_password) + '</span>' +
                    '</div>' +
                    '<div class="pma-info-item">' +
                        '<span class="pma-info-label">' + pt('账号状态：') + '</span>' +
                        '<span class="pma-info-value">' + (info.account_ok ? pt('正常') : pt('异常')) + '</span>' +
                        '<span class="pma-info-label">' + pt('口令校验：') + '</span>' +
                        '<span class="pma-info-value">' + pgPasswordText(info.password_ok) + '</span>' +
                    '</div>' +
                    '<div class="pma-info-item">' +
                        '<button class="btn btn-default btn-sm" onclick="checkPgAccount()">' + pt('检测账号') + '</button>' +
                        '<button class="btn btn-success btn-sm" style="margin-left:8px" onclick="fixPgLogin()">' + pt('修复登录') + '</button>' +
                    '</div>' +
                '</div>' +
                '<div class="pma-info-footer">' +
                    '<span class="glyphicon glyphicon-info-sign"></span> ' +
                    pt('注意：访问网页需要先输入基础认证账号密码，然后在系统登录界面输入登录用户名和密码。') +
                '</div>' +
            '</div>';
            var style = `
            <style>
            .pma-access-info {
                margin-top: 20px;
                border: 1px solid #e2e2e2;
                border-radius: 6px;
                background-color: #fcfcfc;
                box-shadow: 0 2px 5px rgba(0,0,0,0.02);
                overflow: hidden;
                font-size: 13px;
                color: #555;
            }
            .pma-info-header {
                padding: 10px 15px;
                background-color: #f5f6fa;
                border-bottom: 1px solid #e2e2e2;
                font-weight: 600;
                color: #333;
                font-size: 14px;
            }
            .pma-info-body {
                padding: 15px;
            }
            .pma-info-item {
                display: flex;
                margin-bottom: 10px;
                align-items: center;
            }
            .pma-info-item:last-child {
                margin-bottom: 0;
            }
            .pma-info-label {
                width: 100px;
                color: #666;
                font-weight: 500;
            }
            .pma-info-value {
                flex: 1;
                color: #333;
                font-family: Consolas, monospace;
                background: #f0f0f0;
                padding: 2px 8px;
                border-radius: 4px;
                word-break: break-all;
            }
            .pma-link {
                color: #20a53a;
                text-decoration: none;
                transition: color 0.3s;
            }
            .pma-link:hover {
                color: #167a2a;
                text-decoration: underline;
            }
            .pma-info-footer {
                padding: 10px 15px;
                background-color: #fff8e1;
                border-top: 1px solid #ffecb3;
                color: #8a6d3b;
                font-size: 12px;
                line-height: 1.5;
            }
            </style>
            `;
            if ($(".pma-access-info").length == 0) {
                $(".soft-man-con").append(style + html);
            }
        });
    }, 500);
}

//账号诊断：确认面板上显示的凭据在 pgAdmin 数据库里真实可用
function checkPgAccount() {
    api.post('check_pg_account', '', function(rdata) {
        var rdata = typeof rdata.data === "string" ? JSON.parse(rdata.data) : rdata.data;
        if (!rdata.status) {
            layer.msg(rdata.msg, { icon: 2, time: 2000, shade: [0.3, '#000'] });
            return;
        }
        var d = rdata.data;
        var rows = '' +
            '<div class="pma-info-item">' +
                '<span class="pma-info-label">' + pt('数据库：') + '</span>' +
                '<span class="pma-info-value">' + yfMsgEscape(d.db_path) + '</span>' +
            '</div>' +
            '<div class="pma-info-item">' +
                '<span class="pma-info-label">' + pt('账号状态：') + '</span>' +
                '<span class="pma-info-value">' + (d.account_ok ? pt('正常') : pt('异常')) + '</span>' +
            '</div>' +
            '<div class="pma-info-item">' +
                '<span class="pma-info-label">' + pt('口令校验：') + '</span>' +
                '<span class="pma-info-value">' + pgPasswordText(d.password_ok) + '</span>' +
            '</div>' +
            '<div class="pma-info-item">' +
                '<span class="pma-info-label">' + pt('账号数：') + '</span>' +
                '<span class="pma-info-value">' + yfMsgEscape((d.users || []).length) + '</span>' +
            '</div>' +
            '<div class="pma-info-item">' +
                '<span class="pma-info-label">' + pt('原因：') + '</span>' +
                '<span class="pma-info-value">' + yfMsgEscape(d.account_reason || '') + '</span>' +
            '</div>' +
            '<div class="pma-info-item">' +
                '<button class="btn btn-success btn-sm" onclick="fixPgLogin()">' + pt('修复登录') + '</button>' +
            '</div>';
        // 「账号状态正常」不等于「能登录」：口令对不上时账号状态照样是正常的，
        // 所以这里以 login_ok（结构 + 口令双通过）为准
        var tip = (d.login_ok === true) ? '' :
            '<div class="pma-info-footer">' +
            pt('登录自检未通过，点「修复登录」自动重建账号。') + '</div>';
        // layer.open(type:1) 的 content/title 都是裸 innerHTML 注入，
        // 这里只拼 pt() 译文与已转义的值
        layer.open({
            type: 1,
            title: pt('检测账号'),
            area: ['620px', 'auto'],
            content: '<div class="pma-access-info"><div class="pma-info-body">' +
                rows + '</div>' + tip + '</div>'
        });
    });
}

//口令校验结果 -> 展示文案：true 正常 / false 异常 / null 无法判定
function pgPasswordText(v) {
    if (v === true) {
        return pt('正常');
    }
    if (v === false) {
        return pt('异常');
    }
    return pt('无法判定');
}

//一键修复登录：把面板显示的账号与口令强制写进 pgAdmin 配置库，并回读校验。
//强制是重点 —— 不做任何「账号看起来健康就跳过」的判断，因为
//「账号健康」并不等于「面板显示的口令能登录」（库里可能还是上一轮的旧哈希）。
function fixPgLogin() {
    var load = layer.load(2);
    api.post('fix_login', '', function(rdata) {
        layer.close(load);
        var d = typeof rdata.data === "string" ? JSON.parse(rdata.data) : rdata.data;
        if (!d || !d.status) {
            layer.msg((d && d.msg) ? yfMsgEscape(d.msg) : pt('修复登录'), { icon: 2, time: 4000 });
            return;
        }
        var info = d.data || {};
        var ok = (info.password_ok === true);
        // reason 是后端拼出来的文案（含库路径、异常摘要），layer.msg 走 innerHTML，
        // 必须转义后再拼
        layer.msg((ok ? pt('登录自检通过') : pt('登录自检未通过')) + '：' + yfMsgEscape(info.reason || ''),
            { icon: ok ? 1 : 2, time: 5000 });
    });
}