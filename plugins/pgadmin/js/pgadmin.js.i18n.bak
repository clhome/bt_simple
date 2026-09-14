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
        var rdata = JSON.parse(rdata.data);
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
                    <input style="width:180px" class="bt-input-text mr20" name="basic_username" id="pg_basic_user" value="' + cfg['username'] + '" placeholder="基础认证用户名" type="text">\
                    <button class="btn btn-success btn-sm" onclick="setPgUsername()">' + pt('保存') + '</button>\
                </div>\
                <div class="ver line">\
                    <span class="tname">' + pt('基础认证密码') + '</span>\
                    <input style="width:180px" class="bt-input-text mr20" name="basic_password" id="pg_basic_pwd" value="' + cfg['password'] + '" placeholder="基础认证密码" type="text">\
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
        layer.msg('端口范围不合法!', { icon: 2 });
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
            var html = '<div class="pma-access-info">' +
                '<div class="pma-info-header">' + pt('访问与认证信息') + '</div>' +
                '<div class="pma-info-body">' +
                    '<div class="pma-info-item">' +
                        '<span class="pma-info-label">' + pt('内网地址：') + '</span>' +
                        '<a href="' + info.internal_url + '" target="_blank" class="pma-info-value pma-link">' + info.internal_url + '</a>' +
                    '</div>' +
                    '<div class="pma-info-item">' +
                        '<span class="pma-info-label">' + pt('外网地址：') + '</span>' +
                        '<a href="' + info.external_url + '" target="_blank" class="pma-info-value pma-link">' + info.external_url + '</a>' +
                    '</div>' +
                    '<div class="pma-info-item" style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed #eee;">' +
                        '<span class="pma-info-label">' + pt('基础认证账号：') + '</span>' +
                        '<span class="pma-info-value">' + info.username + '</span>' +
                    '</div>' +
                    '<div class="pma-info-item">' +
                        '<span class="pma-info-label">' + pt('基础认证密码：') + '</span>' +
                        '<span class="pma-info-value">' + info.password + '</span>' +
                    '</div>' +
                    '<div class="pma-info-item" style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed #eee;">' +
                        '<span class="pma-info-label">' + pt('登录用户名：') + '</span>' +
                        '<span class="pma-info-value">' + info.web_pg_username + '</span>' +
                    '</div>' +
                    '<div class="pma-info-item">' +
                        '<span class="pma-info-label">' + pt('登录密码：') + '</span>' +
                        '<span class="pma-info-value">' + info.web_pg_password + '</span>' +
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