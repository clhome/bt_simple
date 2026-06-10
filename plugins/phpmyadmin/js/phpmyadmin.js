function str2Obj(str){
    var data = {};
    kv = str.split('&');
    for(i in kv){
        v = kv[i].split('=');
        data[v[0]] = v[1];
    }
    return data;
}

function pmaPost(method,args,callback){

    var _args = null; 
    if (typeof(args) == 'string'){
        _args = JSON.stringify(str2Obj(args));
    } else {
        _args = JSON.stringify(args);
    }

    var loadT = layer.msg('正在获取...', { icon: 16, time: 0, shade: 0.3 });
    $.post('/plugins/run', {name:'phpmyadmin', func:method, args:_args}, function(data) {
        layer.close(loadT);
        if (!data.status){
            layer.msg(data.msg,{icon:0,time:2000,shade: [0.3, '#000']});
            return;
        }

        if(typeof(callback) == 'function'){
            callback(data);
        }
    },'json'); 
}


function pmaAsyncPost(method,args){

    var _args = null; 
    if (typeof(args) == 'string'){
        _args = JSON.stringify(str2Obj(args));
    } else {
        _args = JSON.stringify(args);
    }
    return syncPost('/plugins/run', {name:'phpmyadmin', func:method, args:_args}); 
}

function homePage(){
    pmaPost('get_home_page', '', function(data){
        var rdata = $.parseJSON(data.data);
        if (!rdata.status){
            layer.msg(rdata.msg,{icon:0,time:2000,shade: [0.3, '#000']});
            return;
        }
        var con = '<button class="btn btn-default btn-sm" onclick="window.open(\'' + rdata.data + '\')">主页</button>';
        $(".soft-man-con").html(con);
    });
}

//phpmyadmin切换php版本
function phpVer(version) {

    var _version = pmaAsyncPost('get_set_php_ver','')
    if (_version['data'] != ''){
        version = _version['data'];
    }

    $.post('/site/get_php_version', function(data) {
        var rdata = data['data'];
        // console.log(rdata);
        var body = "<div class='ver line'><span class='tname'>PHP版本</span><select id='phpver' class='bt-input-text mr20' name='phpVersion' style='width:110px'>";
        var optionSelect = '';
        for (var i = 0; i < rdata.length; i++) {
            optionSelect = rdata[i].version == version ? 'selected' : '';
            body += "<option value='" + rdata[i].version + "' " + optionSelect + ">" + rdata[i].name + "</option>"
        }
        body += '</select><button class="btn btn-success btn-sm" onclick="phpVerChange(\'phpversion\',\'get\')">保存</button></div>';
        $(".soft-man-con").html(body);
    },'json');
}

function phpVerChange(type, msg) {
    var phpver = $("#phpver").val();
    pmaPost('set_php_ver', 'phpver='+phpver, function(data){
        if ( data.data == 'ok' ){
            layer.msg('设置成功!',{icon:1,time:2000,shade: [0.3, '#000']});
        } else {
            layer.msg('设置失败!',{icon:2,time:2000,shade: [0.3, '#000']});
        }
    });
}


//phpmyadmin安全设置
function safeConf() {
    pmaPost('get_pma_option', {}, function(rdata){
        var rdata = $.parseJSON(rdata.data);
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
    pmaPost('set_pma_choose',{'choose':choose}, function(data){
        var rdata = $.parseJSON(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

function setPmaUsername(){
    var username = $("input[name=username]").val();
    pmaPost('set_pma_username',{'username':username}, function(data){
        var rdata = $.parseJSON(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

function setPmaPassword(){
    var password = $("input[name=password]").val();
    pmaPost('set_pma_password',{'password':password}, function(data){
        var rdata = $.parseJSON(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

function setPmaPath(){
    var path = $("input[name=path]").val();
    pmaPost('set_pma_path',{'path':path}, function(data){
        var rdata = $.parseJSON(data.data);
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
    
    pmaPost('set_pma_port',data, function(data){
        var rdata = $.parseJSON(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

function pmaService() {
    pluginService('phpmyadmin');
    setTimeout(function() {
        pmaPost('get_pma_access_info', '', function(rdata) {
            var data = $.parseJSON(rdata.data);
            if (!data.status) {
                return;
            }
            var info = data.data;
            var html = `
            <div class="pma-access-info">
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
            `;
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