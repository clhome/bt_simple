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
    f2bPost('ban_ip_release', '', {}, function(data){
        var rdata = $.parseJSON(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}

// 运行日志
function f2bLogs(){
    var con = '<div class="divtable">' +
                '<textarea class="bt-input-text" style="height: 440px; width: 100%; line-height:18px; padding: 10px;" id="f2bLogBody" readonly></textarea>' +
                '<button id="f2bClearLogBtn" class="btn btn-default btn-sm" style="margin-top:10px;">清空日志</button>' +
               '</div>';
    $(".soft-man-con").html(con);
    
    function refreshLog() {
        var loadT = layer.msg('正在获取日志...', { icon: 16, time: 0, shade: 0.3 });
        f2bPost('get_last_log', '', {}, function(data){
            layer.close(loadT);
            var rdata = $.parseJSON(data.data);
            $("#f2bLogBody").text(rdata.data);
            var textarea = document.getElementById('f2bLogBody');
            textarea.scrollTop = textarea.scrollHeight;
        });
    }
    refreshLog();
    
    $("#f2bClearLogBtn").click(function(){
        layer.confirm('确定要清空 fail2ban 的运行日志吗？', {title: '清空日志'}, function(index) {
            f2bPost('clear_log', '', {}, function(data){
                var rdata = $.parseJSON(data.data);
                layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
                if (rdata.status) {
                    refreshLog();
                }
                layer.close(index);
            });
        });
    });
}

function f2bBanIp() {
    var html = '<div class="waf-drop-ip-con">\
        <div style="margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center;">\
            <div style="display:flex; align-items:center;">\
                <input class="bt-input-text" type="text" id="f2b_add_ip_input" placeholder="输入IP地址，例如1.1.1.1" style="width: 200px; margin-right: 5px;">\
                <button class="btn btn-success btn-sm" onclick="f2bAddDropIp();">添加黑名单</button>\
            </div>\
            <button class="btn btn-default btn-sm" onclick="f2bBanIp();"><i class="glyphicon glyphicon-refresh"></i> 刷新</button>\
        </div>\
        <div class="divtable">\
            <table class="table table-hover">\
                <thead>\
                    <tr>\
                        <th width="35%">IP 地址</th>\
                        <th width="35%">IP归属</th>\
                        <th width="30%" style="text-align: right;">操作</th>\
                    </tr>\
                </thead>\
                <tbody id="f2b_drop_ip_list_body">\
                    <tr><td colspan="3" style="text-align:center;">正在加载数据...</td></tr>\
                </tbody>\
            </table>\
        </div>\
    </div>';

    $('.soft-man-con').html(html);

    f2bPost('get_black_list', '', {}, function(data){
        var rdata = $.parseJSON(data.data);
        var ipListStr = rdata.data;
        var ipList = ipListStr ? ipListStr.split('\n').filter(function(x) { return x.trim() !== ''; }) : [];

        if (!ipList || ipList.length === 0) {
            $('#f2b_drop_ip_list_body').html('<tr><td colspan="3" style="text-align:center;">暂无黑名单 IP。</td></tr>');
            return;
        }

        // 读取缓存
        var cacheStr = localStorage.getItem('f2b_ip_loc_cache');
        var locCache = {};
        if (cacheStr) {
            try { locCache = JSON.parse(cacheStr); } catch(e) {}
        }

        var tbodyHtml = '';
        var pendingIps = [];
        
        for (var i = 0; i < ipList.length; i++) {
            var ip = ipList[i].trim();
            if (!ip) continue;
            var ipId = 'ip_loc_' + ip.replace(/\./g, '_').replace(/:/g, '_');
            var locStr = locCache[ip];
            var locDisplay = '';
            if (locStr) {
                locDisplay = locStr;
            } else {
                locDisplay = '<span style="color:#999;">正在获取...</span>';
                pendingIps.push(ip);
            }

            tbodyHtml += '<tr>\
                <td><span style="color:#d9534f; font-family: Consolas, monospace; font-weight:bold;">' + ip + '</span></td>\
                <td id="' + ipId + '">' + locDisplay + '</td>\
                <td style="text-align: right;">\
                    <a href="javascript:;" class="btlink" style="color:#20a53a;" onclick="f2bRemoveDropIp(\'' + ip + '\')">删除</a>\
                </td>\
            </tr>';
        }
        $('#f2b_drop_ip_list_body').html(tbodyHtml);

        // 如果有未命中的，分片请求
        if (pendingIps.length > 0) {
            var chunkSize = 100;
            for (var i = 0; i < pendingIps.length; i += chunkSize) {
                var chunk = pendingIps.slice(i, i + chunkSize);
                (function(ips) {
                    f2bPost('getIpLocationBatch', '', {ips: JSON.stringify(ips)}, function(data) {
                        var loc_res = $.parseJSON(data.data);
                        if (loc_res.status && loc_res.data) {
                            var batchData = loc_res.data;
                            for (var j = 0; j < batchData.length; j++) {
                                var item = batchData[j];
                                if (item && item.query && item.status === 'success') {
                                    var country = item.country || '';
                                    var regionName = item.regionName || '';
                                    var city = item.city || '';
                                    var org = item.org || '';
                                    
                                    var locParts = [];
                                    if (country) locParts.push(country);
                                    if (regionName && regionName !== country) locParts.push(regionName);
                                    if (city && city !== regionName) locParts.push(city);
                                    if (org) locParts.push(org);
                                    
                                    var finalStr = locParts.join('_');
                                    if (!finalStr) finalStr = '未知';
                                    
                                    locCache[item.query] = finalStr;
                                    var pId = 'ip_loc_' + item.query.replace(/\./g, '_').replace(/:/g, '_');
                                    $('#' + pId).html(finalStr);
                                } else if (item && item.query) {
                                    locCache[item.query] = '局域网/保留地址';
                                    var pId = 'ip_loc_' + item.query.replace(/\./g, '_').replace(/:/g, '_');
                                    $('#' + pId).html('局域网/保留地址');
                                }
                            }
                            localStorage.setItem('f2b_ip_loc_cache', JSON.stringify(locCache));
                        }
                    });
                })(chunk);
            }
        }
    });
}

function f2bRemoveDropIp(ip) {
    layer.confirm('确定要删除该 IP (' + ip + ') 并解封吗？', {title: '删除黑名单', icon: 3}, function(index) {
        layer.close(index);
        var loadT = layer.msg('正在删除...', {icon: 16, time: 0, shade: 0.3});
        
        // 先获取现有列表，过滤掉这个IP然后再保存
        f2bPost('get_black_list', '', {}, function(data){
            var rdata = $.parseJSON(data.data);
            var ipListStr = rdata.data;
            var ipList = ipListStr ? ipListStr.split('\n').filter(function(x) { return x.trim() !== '' && x.trim() !== ip; }) : [];
            
            f2bPost('set_black_ip', '', {'black_ip': JSON.stringify(ipList)}, function(sdata){
                layer.close(loadT);
                var srdata = $.parseJSON(sdata.data);
                layer.msg('已删除并尝试解封该IP', {icon: 1});
                f2bBanIp();
            });
        });
    });
}

function f2bAddDropIp() {
    var ip = $('#f2b_add_ip_input').val().trim();
    if (!ip) {
        layer.msg('请输入IP地址', {icon: 2});
        return;
    }
    var loadT = layer.msg('正在添加...', {icon: 16, time: 0, shade: 0.3});
    f2bPost('get_black_list', '', {}, function(data){
        var rdata = $.parseJSON(data.data);
        var ipListStr = rdata.data;
        var ipList = ipListStr ? ipListStr.split('\n').filter(function(x) { return x.trim() !== ''; }) : [];
        
        if (ipList.indexOf(ip) === -1) {
            ipList.push(ip);
        } else {
            layer.close(loadT);
            layer.msg('该IP已在黑名单中', {icon: 2});
            return;
        }
        
        f2bPost('set_black_ip', '', {'black_ip': JSON.stringify(ipList)}, function(sdata){
            layer.close(loadT);
            var srdata = $.parseJSON(sdata.data);
            layer.msg(srdata.msg, {icon: srdata.status ? 1 : 2});
            if (srdata.status) {
                f2bBanIp();
            }
        });
    });
}



// 系统防护
function f2bServerAnti() {
    var loadT = layer.msg('正在获取配置...', { icon: 16, time: 0, shade: 0.3 });
    f2bPost('get_anti_info', '', {}, function(data){
        layer.close(loadT);
        var rdata = $.parseJSON(data.data);
        var serverRules = (rdata.data && rdata.data.server) ? rdata.data.server : [];
        var defaultSshPort = (rdata.data && rdata.data.default_ssh_port) ? rdata.data.default_ssh_port : '22';
        
        // 预设服务列表
        var presetServices = [
            {name: 'SSH 防爆破', mode: 'sshd', port: defaultSshPort, maxretry: 5, findtime: 300, bantime: 86400},
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
                    if (mode.indexOf('-') > 0) f2bSiteAnti(); else f2bServerAnti();
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
    var loadT = layer.msg('正在拉取防护状态...', { icon: 16, time: 0, shade: 0.3 });
    f2bPost('get_anti_info', '', {}, function(data){
        layer.close(loadT);
        var rdata = $.parseJSON(data.data);
        var siteRules = (rdata.data && rdata.data.site) ? rdata.data.site : [];
        
        // 预设服务列表
        var presetServices = [
            {name: '全局防 CC 攻击', mode: 'global-cc', port: '80,443', maxretry: 60, findtime: 60, bantime: 86400},
            {name: '全局防恶意扫描', mode: 'global-scan', port: '80,443', maxretry: 30, findtime: 60, bantime: 86400}
        ];

        var tbody = '';
        $.each(presetServices, function(i, item) {
            // 查看是否已配置
            var configured = null;
            $.each(siteRules, function(j, rule) {
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
                        '<td>' + (configured ? configured.port : item.port) + '</td>' +
                        '<td>' + (configured ? configured.maxretry + '次 / ' + configured.findtime + '秒' : item.maxretry + '次 / ' + item.findtime + '秒') + '</td>' +
                        '<td>' + (configured ? configured.bantime + '秒' : item.bantime + '秒') + '</td>' +
                        '<td>' + statusStr + '</td>' +
                        '<td style="text-align: right;">' + btnStr + '</td>' +
                     '</tr>';
        });

        var con = '<div class="divtable">' +
                  '<table class="table table-hover">' +
                  '<thead><tr><th>防护类型</th><th>端口</th><th>拦截条件</th><th>封禁时长</th><th>状态</th><th style="text-align: right;">操作</th></tr></thead>' +
                  '<tbody>' + tbody + '</tbody>' +
                  '</table>' +
                  '<ul class="help-info-text c7 ptb15"><li>开启全局防护后，将自动应用到所有网站，对访问日志进行聚合分析和攻击拦截。</li></ul>' +
                  '</div>';
        $(".soft-man-con").html(con);
    });
}