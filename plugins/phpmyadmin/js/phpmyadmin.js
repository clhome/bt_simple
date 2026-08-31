var api = YfPlugin.createApi('phpmyadmin');
var pt = YfI18n.createPluginTranslator('phpmyadmin');
function str2Obj(str){
    var data = {};
    kv = str.split('&');
    for(i in kv){
        v = kv[i].split('=');
        data[v[0]] = v[1];
    }
    return data;
}




function homePage() {
    api.post('get_home_page', '', function(data) {
        var rdata = JSON.parse(data.data);
        if (!rdata.status) {
            layer.msg(rdata.msg, { icon: 0, time: 2000, shade: [0.3, '#000'] });
            return;
        }
        var url = rdata.data;
        var con = '<div class="line" style="margin-top: 15px;">\
                    <button class="btn btn-success btn-sm" onclick="window.open(\'' + url + '\')">进入 phpMyAdmin 主页</button>\
                    <div style="margin-top: 15px; color: #666; font-size: 13px; line-height: 1.8;">\
                        <p>访问地址：<a href="' + url + '" target="_blank" class="btlink">' + url + '</a></p>\
                        <p style="color: #999; font-size: 12px;">提示：如出现 401 认证弹窗，请使用【服务】页面中的随机用户名和密码进行认证。</p>\
                    </div>\
                </div>';
        $(".soft-man-con").html(con);
    });
}

function phpVer(version) {
    api.post('get_set_php_ver', '', function(rdata) {
        var curr_ver = rdata.data || version;
        $.post('/site/get_php_version', function(data) {
            var php_list = data.data || [];
            var body = "<div class='ver line'><span class='tname'>PHP版本</span><select id='phpver' class='bt-input-text mr20' name='phpVersion' style='width:120px'>";
            for (var i = 0; i < php_list.length; i++) {
                var isSelected = (php_list[i].version == curr_ver) ? 'selected' : '';
                body += "<option value='" + php_list[i].version + "' " + isSelected + ">" + php_list[i].name + "</option>";
            }
            body += '</select><button class="btn btn-success btn-sm" onclick="phpVerChange(\'phpversion\',\'get\')">保存</button></div>';
            $(".soft-man-con").html(body);
        }, 'json');
    });
}

function phpVerChange(type, msg) {
    var phpver = $("#phpver").val();
    api.post('set_php_ver', 'phpver='+phpver, function(data){
        if ( data.data == 'ok' ){
            layer.msg('设置成功!',{icon:1,time:2000,shade: [0.3, '#000']});
        } else {
            layer.msg('设置失败!',{icon:2,time:2000,shade: [0.3, '#000']});
        }
    });
}


//phpmyadmin安全设置
function safeConf() {
    api.post('get_pma_option', {}, function(rdata){
        var rdata = JSON.parse(rdata.data);
        if (!rdata.status){
            layer.msg(rdata.msg,{icon:2,time:2000,shade: [0.3, '#000']});
            return;
        }

        var cfg = rdata.data;
        var con = '<div class="ver line">\
                    <span class="tname">访问端口</span>\
                    <input style="width:110px" class="bt-input-text phpmyadmindk mr20" name="Name" id="pmport" value="' + cfg['port'] + '" placeholder="phpmyadmin访问端口" maxlength="5" type="number">\
                    <button class="btn btn-success btn-sm" onclick="setPamPort()">保存</button>\
                </div>\
                <div class="ver line">\
                    <span class="tname">访问切换</span>\
                    <select id="access_choose" class="bt-input-text mr20" name="choose" style="width:110px">\
                        <option value="mariadb" '+(cfg['choose']=="mariadb"?"selected='selected'":"")+'>MariaDB</option>\
                        <option value="mysql" '+ (cfg['choose']=="mysql"?"selected='selected'":"")+'>MySQL</option>\
                        <option value="mysql-community" '+ (cfg['choose']=="mysql-community"?"selected='selected'":"")+'>MySQL[Tar]</option>\
                        <option value="mysql-apt" '+ (cfg['choose']=="mysql-apt"?"selected='selected'":"")+'>MySQL[APT]</option>\
                        <option value="mysql-yum" '+ (cfg['choose']=="mysql-yum"?"selected='selected'":"")+'>MySQL[YUM]</option>\
                    </select>\
                    <button class="btn btn-success btn-sm" onclick="setPmaChoose()">保存</button>\
                </div>\
                <div class="ver line">\
                    <span class="tname">用户名</span>\
                    <input style="width:110px" class="bt-input-text mr20" name="username" id="pmport" value="' + cfg['username'] + '" placeholder="认证用户名" type="text">\
                    <button class="btn btn-success btn-sm" onclick="setPmaUsername()">保存</button>\
                </div>\
                <div class="ver line">\
                    <span class="tname">密码</span>\
                    <input style="width:110px" class="bt-input-text mr20" name="password" id="pmport" value="' + cfg['password'] + '" placeholder="密码" type="text">\
                    <button class="btn btn-success btn-sm" onclick="setPmaPassword()">保存</button>\
                </div>\
                <hr/>\
                <div class="ver line">\
                    <span class="tname">路径名</span>\
                    <input style="width:180px" class="bt-input-text mr20" name="path" id="pmport" value="' + cfg['path'] + '" placeholder="" type="text">\
                    <button class="btn btn-success btn-sm" onclick="setPmaPath()">保存</button>\
                </div>';
        $(".soft-man-con").html(con);
    });
}


function setPmaChoose(){
    var choose = $("#access_choose").val();
    api.post('set_pma_choose',{'choose':choose}, function(data){
        var rdata = JSON.parse(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

function setPmaUsername(){
    var username = $("input[name=username]").val();
    api.post('set_pma_username',{'username':username}, function(data){
        var rdata = JSON.parse(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

function setPmaPassword(){
    var password = $("input[name=password]").val();
    api.post('set_pma_password',{'password':password}, function(data){
        var rdata = JSON.parse(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

function setPmaPath(){
    var path = $("input[name=path]").val();
    api.post('set_pma_path',{'path':path}, function(data){
        var rdata = JSON.parse(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

//修改phpmyadmin端口
function setPamPort() {
    var pmport = $("#pmport").val();
    if (pmport < 80 || pmport > 65535) {
        layer.msg('端口范围不合法!', { icon: 2 });
        return;
    }
    var data = 'port=' + pmport;
    
    api.post('set_pma_port',data, function(data){
        var rdata = JSON.parse(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

function pmaService() {
    pluginService('phpmyadmin');
    setTimeout(function() {
        api.post('get_pma_access_info', '', function(rdata) {
            var data = JSON.parse(rdata.data);
            if (!data.status) {
                return;
            }
            var info = data.data;
            var html = `
            <div class="service-notice" style="margin-top: 15px; padding: 12px 15px; background-color: #f8f9fa; border-left: 4px solid #20a53a; border-radius: 4px; font-size: 13px; color: #555; line-height: 1.6; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                <div style="margin-bottom: 4px;"><b style="color:#333;">` + t('public.reload_configuration_reload', '重载配置 (Reload)') + `</b>` + t('public.smoothly_loads_the_latest', '：平滑加载最新配置。进程重新读取配置而不断开现有连接，实现') + `<b style="color:#20a53a;">` + t('public.zero_business_disruption', '业务零中断') + `</b>` + t('public.recommended_for_use_after', '，推荐日常修改配置后使用。') + `</div>
                <div><b style="color:#333;">` + t('public.restart_the_service_restart', '重启服务 (Restart)') + `</b>` + t('public.forcibly_terminates_and_restarts', '：强制终止并重启所有进程。会导致进行中的请求（如订单提交、文件上传）瞬间中断并抛出 502 错误，仅在极少数异常恢复时使用。') + `</div>
            </div>
            <div class="pma-access-info" style="margin-top: 15px;">
                <div class="pma-info-header">访问与认证信息</div>
                <div class="pma-info-body">
                    <div class="pma-info-item">
                        <span class="pma-info-label">内网地址：</span>
                        <a href="` + info.internal_url + `" target="_blank" class="pma-info-value pma-link">` + info.internal_url + `</a>
                    </div>
                    <div class="pma-info-item">
                        <span class="pma-info-label">外网地址：</span>
                        <a href="` + info.external_url + `" target="_blank" class="pma-info-value pma-link">` + info.external_url + `</a>
                    </div>
                    <div class="pma-info-item">
                        <span class="pma-info-label">用户名：</span>
                        <span class="pma-info-value">` + info.username + `</span>
                    </div>
                    <div class="pma-info-item">
                        <span class="pma-info-label">密码：</span>
                        <span class="pma-info-value">` + info.password + `</span>
                    </div>
                </div>
                <div class="pma-info-footer">
                    <span class="glyphicon glyphicon-info-sign"></span> 
                    注意：打开网页后输入用户名为 <strong>root</strong>，密码请前往 <strong>MySQL => 管理列表 => root密码</strong> 查看
                </div>
            </div>
            <div class="pma-kill-section" style="margin-top: 18px;">
                <button class="btn btn-danger btn-sm" onclick="pluginOpService('php','kill_all_php','','')">` + t('public.kill_all_php_processes', 'kill所有php进程') + `</button>
                <div class="service-notice" style="margin-top: 10px; padding: 12px 15px; background-color: #fff3f3; border-left: 4px solid #d9534f; border-radius: 4px; font-size: 13px; color: #555; line-height: 1.6; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                    <div><b style="color:#d9534f;">` + t('public.note', '注意') + `</b>` + t('public.forcefully_terminate_all_php', '：强制杀掉服务器上所有的 PHP-FPM 进程（包括其他正常运行的 PHP 版本）。这会中断所有 PHP 网站的访问。此功能主要用于解决面板 PHP 启动时报“端口已被占用”、“Socket冲突”等异常问题，') + `<b style="color:red;">` + t('public.after_execution_you_ll', '执行后需要手动回到各个 PHP 版本中重新点击【启动】服务。') + `</b></div>
                </div>
            </div>
            `;
            var style = `
            <style>
            .pma-access-info {
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
            .pma-info-footer strong {
                color: #d9534f;
            }
            </style>
            `;
            if ($(".pma-access-info").length == 0) {
                $(".soft-man-con").append(style + html);
            }
        });
    }, 500);
}