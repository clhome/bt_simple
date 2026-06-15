function getVersion(){
    return $('.plugin_version').attr('version');
}

function f2bPost(method, version, args,callback){
    var loadT = layer.msg('正在获取...', { icon: 16, time: 0, shade: 0.3 });

    var req_data = {};
    req_data['name'] = 'fail2ban';
    req_data['func'] = method;
    req_data['version'] = version;
 
    if (typeof(args) == 'string'){
        req_data['args'] = JSON.stringify(toArrayObject(args));
    } else {
        req_data['args'] = JSON.stringify(args);
    }

    $.post('/plugins/run', req_data, function(data) {
        layer.close(loadT);
        if (!data.status){
            //错误展示10S
            layer.msg(data.msg,{icon:0,time:2000,shade: [10, '#000']});
            return;
        }

        if(typeof(callback) == 'function'){
            callback(data);
        }
    },'json'); 
}

function f2bPostCallbak(method, version, args, callback){
    var loadT = layer.msg('正在获取...', { icon: 16, time: 0, shade: 0.3 });

    var req_data = {};
    req_data['name'] = 'fail2ban';
    req_data['func'] = method;
    args['version'] = version;
 
    if (typeof(args) == 'string'){
        req_data['args'] = JSON.stringify(toArrayObject(args));
    } else {
        req_data['args'] = JSON.stringify(args);
    }

    $.post('/plugins/callback', req_data, function(data) {
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

function f2bBanIpSave(black_ip){
    var ver = getVersion();
    f2bPost('set_black_ip', ver, {'black_ip':black_ip}, function(data){
        var rdata = $.parseJSON(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

function f2bBanIp(){
    var con = '<p style="color: #666; margin-bottom: 7px">提示：Ctrl+F 搜索关键字，Ctrl+G 查找下一个，Ctrl+S 保存，Ctrl+Shift+R 查找替换!</p>\
                <textarea class="bt-input-text" style="height: 320px; line-height:18px;" id="textBody"></textarea>\
                <button id="onlineEditFileBtn" class="btn btn-success btn-sm" style="margin-top:10px;">保存</button>\
                <ul class="help-info-text c7 ptb15">\
                    <li>如有多个请以换行隔开例：<br/>\
                    192.168.1.1<br/>\
                    192.168.1.0/24\
                    </li>\
                </ul>';

    $(".soft-man-con").html(con);
    $("#textBody").empty();
    var editor = CodeMirror.fromTextArea(document.getElementById("textBody"), {
        extraKeys: {
            "Ctrl-Space": "autocomplete",
            "Ctrl-F": "findPersistent",
            "Ctrl-H": "replaceAll",
            "Ctrl-S": function() {
                $("#textBody").text(editor.getValue());
                f2bPost('set_black_list', '', {'black_ip':editor.getValue()}, function(data){
                    var rdata = $.parseJSON(data.data);
                    layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
                });

                f2bBanIpSave(editor.getValue());
            }
        },
        lineNumbers: true,
        matchBrackets:true,
    });
    editor.focus();

    f2bPost('get_black_list', '', {}, function(data){
        var rdata = $.parseJSON(data.data);
        $("#textBody").text(rdata.data);
    });

    $("#onlineEditFileBtn").click(function(){
        f2bBanIpSave(editor.getValue());
    });
}



// 系统防护
function f2bServerAnti() {
    var loadT = layer.msg('正在获取配置...', { icon: 16, time: 0, shade: 0.3 });
    f2bPost('get_anti_info', '', {}, function(data){
        layer.close(loadT);
        var rdata = $.parseJSON(data.data);
        var serverRules = rdata.server || [];
        
        // 预设服务列表
        var presetServices = [
            {name: 'SSH 防爆破', mode: 'sshd', port: '22', maxretry: 5, findtime: 300, bantime: 86400},
            {name: 'FTP 防爆破', mode: 'ftpd', port: '21', maxretry: 5, findtime: 300, bantime: 86400},
            {name: 'MySQL 防爆破', mode: 'mysql', port: '3306', maxretry: 5, findtime: 300, bantime: 86400},
            {name: 'Dovecot (邮局)', mode: 'dovecot', port: '110', maxretry: 5, findtime: 300, bantime: 86400},
            {name: 'Postfix (邮局)', mode: 'postfix', port: '25', maxretry: 5, findtime: 300, bantime: 86400}
        ];

        var tbody = '';
        $.each(presetServices, function(i, item) {
            // 查看是否已配置
            var configured = null;
            $.each(serverRules, function(j, rule) {
                if(rule.mode == item.mode) configured = rule;
            });

            var statusStr = '<span style="color:red">未配置</span>';
            var btnStr = '<a href="javascript:;" class="btlink" onclick="f2bConfigService(\''+item.mode+'\', \''+item.name+'\', \''+item.port+'\', \''+item.maxretry+'\', \''+item.findtime+'\', \''+item.bantime+'\')">配置</a>';
            
            if(configured) {
                if(configured.act == 'true' || configured.act == true) {
                    statusStr = '<span style="color:green">防御中</span>';
                } else {
                    statusStr = '<span style="color:orange">已停用</span>';
                }
                btnStr = '<a href="javascript:;" class="btlink" onclick="f2bConfigService(\''+item.mode+'\', \''+item.name+'\', \''+configured.port+'\', \''+configured.maxretry+'\', \''+configured.findtime+'\', \''+configured.bantime+'\')">修改</a> | ' +
                         '<a href="javascript:;" class="btlink" onclick="f2bDelAnti(\''+item.mode+'\')">删除</a>';
            }

            tbody += '<tr>' +
                        '<td>' + item.name + ' (' + item.mode + ')</td>' +
                        '<td>' + (configured ? configured.port : '-') + '</td>' +
                        '<td>' + (configured ? configured.maxretry + '次 / ' + configured.findtime + '秒' : '-') + '</td>' +
                        '<td>' + (configured ? configured.bantime + '秒' : '-') + '</td>' +
                        '<td>' + statusStr + '</td>' +
                        '<td style="text-align: right;">' + btnStr + '</td>' +
                     '</tr>';
        });

        var con = '<div class="divtable">' +
                  '<table class="table table-hover">' +
                  '<thead><tr><th>服务名称</th><th>端口</th><th>拦截条件</th><th>封禁时长</th><th>状态</th><th style="text-align: right;">操作</th></tr></thead>' +
                  '<tbody>' + tbody + '</tbody>' +
                  '</table>' +
                  '<ul class="help-info-text c7 ptb15"><li>系统服务防暴力破解，配置后当多次认证失败时将在底层防火墙直接封禁对应来源IP。</li></ul>' +
                  '</div>';
        $(".soft-man-con").html(con);
    });
}

function f2bConfigService(mode, name, port, maxretry, findtime, bantime) {
    var content = '<div class="bt-form pd20 pb70">' +
        '<div class="line"><span class="tname">防爆破服务</span><div class="info-r"><input class="bt-input-text" type="text" disabled value="'+name+'" style="width:250px" /></div></div>' +
        '<div class="line"><span class="tname">防护端口</span><div class="info-r"><input class="bt-input-text" name="port" type="text" value="'+port+'" style="width:250px" /></div></div>' +
        '<div class="line"><span class="tname">检测周期</span><div class="info-r"><input class="bt-input-text" name="findtime" type="number" value="'+findtime+'" style="width:250px" />  秒</div></div>' +
        '<div class="line"><span class="tname">最大失败次数</span><div class="info-r"><input class="bt-input-text" name="maxretry" type="number" value="'+maxretry+'" style="width:250px" />  次</div></div>' +
        '<div class="line"><span class="tname">封禁时间</span><div class="info-r"><input class="bt-input-text" name="bantime" type="number" value="'+bantime+'" style="width:250px" />  秒</div></div>' +
        '<div class="line"><span class="tname">状态</span><div class="info-r"><select class="bt-input-text" name="act" style="width:250px"><option value="true">启用</option><option value="false">停用</option></select></div></div>' +
        '</div>';

    layer.open({
        type: 1,
        title: '配置防护规则 - ' + name,
        area: '450px',
        closeBtn: 1,
        shadeClose: false,
        content: content,
        btn: ['提交', '取消'],
        yes: function (index, layero) {
            var postData = {
                type: 'add',
                mode: mode,
                port: $('input[name="port"]').val(),
                findtime: $('input[name="findtime"]').val(),
                maxretry: $('input[name="maxretry"]').val(),
                bantime: $('input[name="bantime"]').val(),
                act: $('select[name="act"]').val()
            };
            f2bPost('set_anti', '', postData, function(data){
                var rdata = $.parseJSON(data.data);
                layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
                if(rdata.status) {
                    layer.close(index);
                    f2bServerAnti();
                }
            });
        }
    });
}

function f2bDelAnti(mode) {
    layer.confirm('确定要删除并停用该防护规则吗？', {title: '停用规则'}, function(index) {
        f2bPost('del_anti', '', {mode: mode, type: 'edit'}, function(data){
            var rdata = $.parseJSON(data.data);
            layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
            if(rdata.status) {
                layer.close(index);
                if(mode.indexOf('-') > 0) f2bSiteAnti(); else f2bServerAnti();
            }
        });
    });
}

// 网站防护
function f2bSiteAnti() {
    var loadT = layer.msg('正在拉取站点及防护状态...', { icon: 16, time: 0, shade: 0.3 });
    
    // 我们需要获取站点列表以及已配置的规则
    f2bPost('get_all_sitename', '', {}, function(siteData){
        var siteRes = $.parseJSON(siteData.data);
        var sites = Object.keys(siteRes.data || {});
        
        f2bPost('get_anti_info', '', {}, function(data){
            layer.close(loadT);
            var rdata = $.parseJSON(data.data);
            var siteRules = rdata.site || [];
            
            var tbody = '';
            $.each(sites, function(i, siteName) {
                var ccRule = null;
                var scanRule = null;
                $.each(siteRules, function(j, rule) {
                    if(rule.mode == siteName + '-cc') ccRule = rule;
                    if(rule.mode == siteName + '-scan') scanRule = rule;
                });

                var ccStatus = ccRule ? (ccRule.act == 'true' ? '<span style="color:green">生效中</span>' : '<span style="color:orange">已停用</span>') : '<span style="color:#ccc">未配置</span>';
                var scanStatus = scanRule ? (scanRule.act == 'true' ? '<span style="color:green">生效中</span>' : '<span style="color:orange">已停用</span>') : '<span style="color:#ccc">未配置</span>';
                
                var ccBtn = ccRule 
                    ? '<a href="javascript:;" class="btlink" onclick="f2bConfigSite(\''+siteName+'\', \'cc\', \''+ccRule.port+'\', \''+ccRule.maxretry+'\', \''+ccRule.findtime+'\', \''+ccRule.bantime+'\')">修改CC</a> | <a href="javascript:;" class="btlink" onclick="f2bDelAnti(\''+siteName+'-cc\')">删</a>'
                    : '<a href="javascript:;" class="btlink" onclick="f2bConfigSite(\''+siteName+'\', \'cc\', \'80,443\', \'60\', \'60\', \'86400\')">配CC</a>';
                    
                var scanBtn = scanRule 
                    ? '<a href="javascript:;" class="btlink" onclick="f2bConfigSite(\''+siteName+'\', \'scan\', \''+scanRule.port+'\', \''+scanRule.maxretry+'\', \''+scanRule.findtime+'\', \''+scanRule.bantime+'\')">修改扫描</a> | <a href="javascript:;" class="btlink" onclick="f2bDelAnti(\''+siteName+'-scan\')">删</a>'
                    : '<a href="javascript:;" class="btlink" onclick="f2bConfigSite(\''+siteName+'\', \'scan\', \'80,443\', \'15\', \'60\', \'86400\')">配防扫</a>';

                tbody += '<tr>' +
                            '<td>' + siteName + '</td>' +
                            '<td>' + ccStatus + '</td>' +
                            '<td>' + scanStatus + '</td>' +
                            '<td style="text-align: right;">' + ccBtn + ' | ' + scanBtn + '</td>' +
                         '</tr>';
            });

            if(sites.length == 0) {
                tbody = '<tr><td colspan="4" style="text-align:center;">暂无网站</td></tr>';
            }

            var con = '<div class="divtable">' +
                      '<div style="margin-bottom: 10px;">' +
                      '<span style="background-color: #dff0d8; color: #3c763d; padding: 5px 10px; border-radius: 4px; font-size: 12px; border: 1px solid #d6e9c6;">' +
                      '💡 <b>机制提示：</b>自动检测高级 WAF，若已安装 <b>OP_WAF</b>，防扫描与CC将自动监听 WAF 拦截事件执行底层 IP 物理封杀（零性能损耗）。否则退化为日志分析模式。' +
                      '</span>' +
                      '</div>' +
                      '<table class="table table-hover">' +
                      '<thead><tr><th>站点名称</th><th>防CC状态</th><th>防扫描状态</th><th style="text-align: right;">操作</th></tr></thead>' +
                      '<tbody>' + tbody + '</tbody>' +
                      '</table>' +
                      '</div>';
            $(".soft-man-con").html(con);
        });
    });
}

function f2bConfigSite(siteName, type, port, maxretry, findtime, bantime) {
    var typeName = type == 'cc' ? '防 CC 攻击' : '防恶意扫描';
    var modeName = siteName + '-' + type;
    var content = '<div class="bt-form pd20 pb70">' +
        '<div class="line"><span class="tname">防护站点</span><div class="info-r"><input class="bt-input-text" type="text" disabled value="'+siteName+'" style="width:250px" /></div></div>' +
        '<div class="line"><span class="tname">防护类型</span><div class="info-r"><input class="bt-input-text" type="text" disabled value="'+typeName+'" style="width:250px" /></div></div>' +
        '<div class="line"><span class="tname">防护端口</span><div class="info-r"><input class="bt-input-text" name="port" type="text" value="'+port+'" style="width:250px" /></div></div>' +
        '<div class="line"><span class="tname">检测周期</span><div class="info-r"><input class="bt-input-text" name="findtime" type="number" value="'+findtime+'" style="width:250px" />  秒</div></div>' +
        '<div class="line"><span class="tname">最大触发次数</span><div class="info-r"><input class="bt-input-text" name="maxretry" type="number" value="'+maxretry+'" style="width:250px" />  次</div></div>' +
        '<div class="line"><span class="tname">封禁时间</span><div class="info-r"><input class="bt-input-text" name="bantime" type="number" value="'+bantime+'" style="width:250px" />  秒</div></div>' +
        '<div class="line"><span class="tname">状态</span><div class="info-r"><select class="bt-input-text" name="act" style="width:250px"><option value="true">启用</option><option value="false">停用</option></select></div></div>' +
        '</div>';

    layer.open({
        type: 1,
        title: '配置站点规则 - ' + siteName,
        area: '450px',
        closeBtn: 1,
        shadeClose: false,
        content: content,
        btn: ['提交', '取消'],
        yes: function (index, layero) {
            var postData = {
                type: 'add',
                mode: modeName,
                port: $('input[name="port"]').val(),
                findtime: $('input[name="findtime"]').val(),
                maxretry: $('input[name="maxretry"]').val(),
                bantime: $('input[name="bantime"]').val(),
                act: $('select[name="act"]').val()
            };
            f2bPost('set_anti', '', postData, function(data){
                var rdata = $.parseJSON(data.data);
                layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
                if(rdata.status) {
                    layer.close(index);
                    f2bSiteAnti();
                }
            });
        }
    });
}