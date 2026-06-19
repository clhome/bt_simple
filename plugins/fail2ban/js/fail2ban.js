function getVersion(){
    return $('.plugin_version').attr('version');
}

function f2bHome() {
    var loadT = layer.msg('正在获取数据...', { icon: 16, time: 0, shade: 0.3 });
    f2bPost('get_home_stats', '', {}, function(data){
        layer.close(loadT);
        var rdata = $.parseJSON(data.data);
        var stats = rdata.data;
        
        var todayBans = stats.today_bans || 0;
        var totalBans = stats.total_bans || 0;
        var protectDays = stats.protect_days || 0;
        var jailStats = stats.jail_stats || {};

        var jailNames = {
            'sshd': 'SSH 防爆破',
            'ftpd': 'FTP 防爆破',
            'mysql': 'MySQL 防爆破',
            'dovecot': 'Dovecot 邮局',
            'postfix': 'Postfix 邮局',
            'global-cc': '全局防 CC 攻击',
            'global-scan': '全局防恶意扫描'
        };

        var jailHtml = '';
        var count = 0;
        for (var jail in jailStats) {
            var name = jailNames[jail] || jail;
            var num = jailStats[jail];
            jailHtml += '<div style="width: 23%; background: #fff; border: 1px solid #f0f0f0; border-radius: 4px; padding: 20px 0; text-align: center; margin-bottom: 15px; margin-right: 2%; box-shadow: 0 1px 2px rgba(0,0,0,.05); float: left;">\
                            <div style="font-size: 13px; color: #666; margin-bottom: 10px;">' + name + '</div>\
                            <div style="font-size: 24px; font-weight: bold; color: #333;">' + num + '</div>\
                        </div>';
            count++;
        }
        
        if (count === 0) {
            jailHtml = '<div style="width: 100%; text-align: center; color: #999; padding: 40px 0;">暂无拦截数据</div>';
        }

        var html = '<div style="padding: 15px;">\
            <div style="display: flex; justify-content: space-between; margin-bottom: 20px;">\
                <div style="width: 32%; background: #fd6e1e; border-radius: 6px; padding: 25px 0; text-align: center; color: #fff; box-shadow: 0 4px 8px rgba(253,110,30,.2);">\
                    <div style="font-size: 15px; margin-bottom: 10px;">今日拦截 (次)</div>\
                    <div style="font-size: 32px; font-weight: bold;">' + todayBans + '</div>\
                </div>\
                <div style="width: 32%; background: #00b96b; border-radius: 6px; padding: 25px 0; text-align: center; color: #fff; box-shadow: 0 4px 8px rgba(0,185,107,.2);">\
                    <div style="font-size: 15px; margin-bottom: 10px;">总拦截 (次)</div>\
                    <div style="font-size: 32px; font-weight: bold;">' + totalBans + '</div>\
                </div>\
                <div style="width: 32%; background: #2f69f8; border-radius: 6px; padding: 25px 0; text-align: center; color: #fff; box-shadow: 0 4px 8px rgba(47,105,248,.2);">\
                    <div style="font-size: 15px; margin-bottom: 10px;">安全防护 (天)</div>\
                    <div style="font-size: 32px; font-weight: bold;">' + protectDays + '</div>\
                </div>\
            </div>\
            \
            <div style="background: #fcfcfc; border: 1px solid #f0f0f0; border-radius: 6px; padding: 20px 20px 5px 20px; overflow: hidden; margin-bottom: 20px;">\
                ' + jailHtml + '\
                <div style="clear: both;"></div>\
            </div>\
            \
            <div style="background: #f0f9f4; border-left: 4px solid #20a53a; padding: 15px 20px; border-radius: 4px; color: #333; line-height: 28px; font-size: 13px;">\
                <div style="color: #666;"><span style="color:#20a53a; font-weight:bold; margin-right:5px;">√</span> Fail2ban 是一款入侵防御软件，通过监控系统与服务的访问日志，自动将多次尝试失败的恶意源 IP 添加到防火墙的拦截规则中。</div>\
                <div style="color: #666;"><span style="color:#20a53a; font-weight:bold; margin-right:5px;">√</span> 系统防护用于防范服务器 SSH、FTP、MySQL 等服务的账号密码暴力破解。</div>\
                <div style="color: #666;"><span style="color:#20a53a; font-weight:bold; margin-right:5px;">√</span> 网站防护自动分析 Web 访问日志，有效防御 CC 攻击与高频自动化漏洞扫描，保障业务可用性。</div>\
            </div>\
        </div>';

        $('.soft-man-con').html(html);
    });
}

function f2bService() {
    pluginService('fail2ban');
    var waitTimer = setInterval(function() {
        if ($('.soft-man-con').text().indexOf('当前状态') !== -1) {
            clearInterval(waitTimer);
            if ($('.soft-man-con').find('#f2b_intro_panel').length === 0) {
                var infoHtml = '<div id="f2b_intro_panel" class="help-info-text c7" style="margin-top: 15px; padding: 15px; border: 1px dashed #ccc; border-radius: 4px; line-height: 24px;">\
                    <h3 style="margin-top:0; margin-bottom: 10px; font-size: 14px; font-weight: bold; color: #333;">📖 Fail2ban 使用指南</h3>\
                    <p style="margin-bottom: 5px;"><b>Fail2ban</b> 是一款入侵防御软件，通过监控系统与服务的访问日志，自动将多次尝试失败的恶意源 IP 添加到防火墙的拦截规则中。</p>\
                    <ul style="margin-bottom: 0; padding-left: 20px;">\
                        <li><b>系统防护</b>：用于防范服务器 SSH、FTP、MySQL 等服务的账号密码暴力破解。</li>\
                        <li><b>网站防护</b>：自动分析 Web 访问日志，有效防御 CC 攻击与高频自动化漏洞扫描，保障业务可用性。</li>\
                        <li><b>IP黑名单</b>：您可以在此查看当前被防火墙封禁拦截的攻击源 IP，并支持手动添加或解除封禁。</li>\
                    </ul>\
                </div>';
                $('.soft-man-con').append(infoHtml);
            }
        }
    }, 100);
    // 5秒后停止检测，防止死循环
    setTimeout(function() { clearInterval(waitTimer); }, 5000);
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
                '<textarea class="bt-input-text" style="height: 440px; width: 100%; line-height:22px; padding: 10px; background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas, monospace; border: none; border-radius: 4px;" id="f2bLogBody" readonly></textarea>' +
                '<div style="margin-top:10px;"><button id="f2bClearLogBtn" class="btn btn-default btn-sm">清空日志</button></div>' +
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
                        <th width="20%">IP 地址</th>\
                        <th width="15%">触发规则</th>\
                        <th width="30%">IP归属</th>\
                        <th width="20%">剩余封禁时间</th>\
                        <th width="15%" style="text-align: right;">操作</th>\
                    </tr>\
                </thead>\
                <tbody id="f2b_drop_ip_list_body">\
                    <tr><td colspan="5" style="text-align:center;">正在加载数据...</td></tr>\
                </tbody>\
            </table>\
        </div>\
    </div>';

    $('.soft-man-con').html(html);

    f2bPost('get_active_bans', '', {}, function(data){
        var rdata = $.parseJSON(data.data);
        if(!rdata.status) {
            $('#f2b_drop_ip_list_body').html('<tr><td colspan="5" style="text-align:center; color:red;">' + rdata.msg + '</td></tr>');
            return;
        }

        var bans = rdata.data;
        if (!bans || bans.length === 0) {
            $('#f2b_drop_ip_list_body').html('<tr><td colspan="5" style="text-align:center;">暂无封禁 IP。</td></tr>');
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
        var nowTimestamp = Math.floor(Date.now() / 1000);
        
        for (var i = 0; i < bans.length; i++) {
            var item = bans[i];
            var ip = item.ip;
            var jail = item.jail;
            var bantime = item.bantime;
            var expire_time = item.expire_time;
            
            var ipId = 'ip_loc_' + ip.replace(/\./g, '_').replace(/:/g, '_') + '_' + i;
            var locStr = locCache[ip];
            var locDisplay = '';
            if (locStr) {
                locDisplay = locStr;
            } else {
                locDisplay = '<span style="color:#999;">正在获取...</span>';
                if(pendingIps.indexOf(ip) === -1) pendingIps.push(ip);
            }

            var timeRemaining = '';
            if (bantime < 0) {
                timeRemaining = '<span style="color:#d9534f; font-weight:bold;">永久封禁</span>';
            } else {
                var diff = expire_time - nowTimestamp;
                if (diff <= 0) {
                    timeRemaining = '<span style="color:#f0ad4e;">即将解封...</span>';
                } else {
                    var hours = Math.floor(diff / 3600);
                    var minutes = Math.floor((diff % 3600) / 60);
                    if (hours > 0) {
                        timeRemaining = hours + ' 小时 ' + minutes + ' 分钟';
                    } else {
                        timeRemaining = minutes + ' 分钟';
                    }
                }
            }

            tbodyHtml += '<tr>\
                <td><span style="color:#d9534f; font-family: Consolas, monospace; font-weight:bold;">' + ip + '</span></td>\
                <td>' + jail + '</td>\
                <td id="' + ipId + '">' + locDisplay + '</td>\
                <td>' + timeRemaining + '</td>\
                <td style="text-align: right;">\
                    <a href="javascript:;" class="btlink" style="color:#20a53a;" onclick="f2bRemoveDropIp(\'' + ip + '\', \'' + jail + '\')">解除封禁</a>\
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
                                var bItem = batchData[j];
                                if (bItem && bItem.query && bItem.status === 'success') {
                                    var country = bItem.country || '';
                                    var regionName = bItem.regionName || '';
                                    var city = bItem.city || '';
                                    var org = bItem.org || '';
                                    
                                    var locParts = [];
                                    if (country) locParts.push(country);
                                    if (regionName && regionName !== country) locParts.push(regionName);
                                    if (city && city !== regionName) locParts.push(city);
                                    if (org) locParts.push(org);
                                    
                                    var finalStr = locParts.join('_');
                                    if (!finalStr) finalStr = '未知';
                                    
                                    locCache[bItem.query] = finalStr;
                                    $('[id^="ip_loc_' + bItem.query.replace(/\./g, '_').replace(/:/g, '_') + '"]').html(finalStr);
                                } else if (bItem && bItem.query) {
                                    locCache[bItem.query] = '局域网/保留地址';
                                    $('[id^="ip_loc_' + bItem.query.replace(/\./g, '_').replace(/:/g, '_') + '"]').html('局域网/保留地址');
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

function f2bRemoveDropIp(ip, jail) {
    layer.confirm('确定要解除对 IP (' + ip + ') 的封禁吗？', {title: '解除封禁', icon: 3}, function(index) {
        layer.close(index);
        var loadT = layer.msg('正在解封...', {icon: 16, time: 0, shade: 0.3});
        
        f2bPost('unban_active_ip', '', {'ip': ip, 'jail': jail}, function(sdata){
            layer.close(loadT);
            var srdata = $.parseJSON(sdata.data);
            if (srdata.status) {
                layer.msg(srdata.msg, {icon: 1});
            } else {
                layer.msg(srdata.msg, {icon: 2});
            }
            f2bBanIp();
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
        var defaultMysqlPort = (rdata.data && rdata.data.default_mysql_port) ? rdata.data.default_mysql_port : '3306';
        
        // 预设服务列表
        var presetServices = [
            {name: 'SSH 防爆破', mode: 'sshd', port: defaultSshPort, maxretry: 5, findtime: 300, bantime: 86400},
            {name: 'FTP 防爆破', mode: 'ftpd', port: '21', maxretry: 5, findtime: 300, bantime: 86400},
            {name: 'MySQL 防爆破', mode: 'mysql', port: defaultMysqlPort, maxretry: 5, findtime: 300, bantime: 86400},
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

function f2bLogRequest(page){
    var args = {};   
    args['page'] = page;
    args['page_size'] = 10;
    
    var query_date = 'today';
    if ($('#time_choose').attr("data-name") != '' && $('#time_choose').attr("data-name") != undefined){
        query_date = $('#time_choose').attr("data-name");
    } else {
        query_date = $('#search_time button.cur').attr("data-name");
    }

    args['query_date'] = query_date;
    args['tojs'] = 'f2bLogRequest';

    f2bPost('get_logs_list', '', args, function(rdata){
        var rdata = $.parseJSON(rdata.data);
        var list = '';
        var data = rdata.data.data;
        if (data.length > 0){
            for(i in data){
                list += '<tr>';
                list += '<td><span class="overflow_hide" title="' + getLocalTime(data[i]['time']) + '" style="width:145px;">' + getLocalTime(data[i]['time'])+'</span></td>';
                list += '<td><span class="overflow_hide" title="' + data[i]['ip'] + '" style="width:120px; font-family: Consolas, monospace; font-weight:bold; color:#d9534f;">' + data[i]['ip'] +'</span></td>';
                list += '<td><span class="overflow_hide" title="' + data[i]['rule_name'] + '" style="width:100px;">' + data[i]['rule_name'] +'</span></td>';
                list += '<td><span class="overflow_hide" title="' + data[i]['reason'] + '" style="width:300px;">' + data[i]['reason'] +'</span></td>';
                list += '<td style="text-align:right;"><a onclick="f2bIpDetails(\''+data[i]['ip']+'\')" href="javascript:;" class="btlink f2b-details" title="详情">详情</a></td>';
                list += '</tr>';
            }
        } else{
             list += '<tr><td colspan="4" style="text-align:center;">封锁日志为空</td></tr>';
        }
        
        var table = '<div class="tablescroll">\
                            <table id="DataBody" class="table table-hover" width="100%" cellspacing="0" cellpadding="0" border="0" style="border: 0 none;">\
                            <thead><tr>\
                            <th>时间</th>\
                            <th>IP</th>\
                            <th>规则名</th>\
                            <th>原因</th>\
                            <th style="text-align:right;">操作</th>\
                            </tr></thead>\
                            <tbody>\
                            '+ list +'\
                            </tbody></table>\
                        </div>\
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px;">\
                            <div><button id="exportExcel" class="btn btn-default btn-sm" style="margin-left:5px;">导出excel</button></div>\
                            <div id="wsPage" class="dataTables_paginate paging_bootstrap page" style="margin:0;"></div>\
                        </div>';
        $('#ws_table').html(table);
        $('#wsPage').html(rdata.data.page);
    });
}

function f2bIpDetails(ip) {
    var loadT = layer.msg('正在获取详情...', { icon: 16, time: 0, shade: 0.3 });
    f2bPost('get_ip_logs', '', {ip: ip}, function(data){
        layer.close(loadT);
        var rdata = $.parseJSON(data.data);
        if(!rdata.status) {
            layer.msg(rdata.msg, {icon: 2});
            return;
        }
        var logs = rdata.data.logs;
        var ban_count = rdata.data.ban_count;
        
        var tbodyHtml = '';
        if(logs.length > 0) {
            for(var i=0; i<logs.length; i++) {
                var line = logs[i]; // 原始日志行
                
                // 提取时间: "2026-06-19 04:51:02"
                var timeMatch = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
                var timeStr = timeMatch ? timeMatch[1] : '-';
                
                // 提取规则名: "[global-cc]"
                var jailMatch = line.match(/\]:\s+\w+\s+\[([^\]]+)\]/);
                var jailStr = jailMatch ? jailMatch[1] : '-';
                
                // 提取并美化动作
                var actionStr = '-';
                if (line.indexOf(' Restore Ban ') > -1) {
                    actionStr = '<span style="color:#d9534f;"><i class="glyphicon glyphicon-ban-circle"></i> 服务重启后继续封禁 (Restore Ban)</span>';
                } else if (line.indexOf(' Unban ') > -1) {
                    actionStr = '<span style="color:#5cb85c;"><i class="glyphicon glyphicon-ok-circle"></i> 解除封禁 (Unban)</span>';
                } else if (line.indexOf(' Ban ') > -1) {
                    actionStr = '<span style="color:#d9534f;"><i class="glyphicon glyphicon-ban-circle"></i> 封禁 (Ban)</span>';
                } else if (line.indexOf(' Found ') > -1) {
                    actionStr = '<span style="color:#f0ad4e;"><i class="glyphicon glyphicon-warning-sign"></i> 发现攻击 (Found)</span>';
                } else {
                    var actMatch = line.match(/\]:\s+\w+\s+\[[^\]]+\]\s+(.*)$/);
                    if(actMatch) {
                        actionStr = $('<div>').text(actMatch[1].replace(new RegExp(ip, 'g'), '').trim()).html();
                    } else {
                        actionStr = '<span style="color:#999;" title="' + $('<div>').text(line).html() + '">未知动作</span>'; // 容错处理
                    }
                }
                
                tbodyHtml += '<tr>\
                    <td style="font-family: Consolas, monospace; font-size: 12.5px;">' + timeStr + '</td>\
                    <td>' + $('<div>').text(jailStr).html() + '</td>\
                    <td>' + actionStr + '</td>\
                </tr>';
            }
        } else {
            tbodyHtml = '<tr><td colspan="3" style="text-align:center;">暂无详细记录</td></tr>';
        }
        
        var content = '<div class="pd15">\
                        <div style="display: flex; justify-content: space-between; align-items: center; background: #f4f6f8; padding: 10px 15px; border-radius: 4px; border: 1px solid #e2e2e2; margin-bottom: 15px;">\
                            <div style="font-size: 13px;"><b>防护目标IP：</b><span style="font-family: Consolas, monospace; color:#333; margin-left: 5px;">' + $('<div>').text(ip).html() + '</span></div>\
                            <div style="font-size: 13px;"><b>历史封禁次数：</b><span style="color:#d9534f; font-weight:bold; font-size:15px; margin: 0 5px;">' + ban_count + '</span>次</div>\
                        </div>\
                        <div class="divtable">\
                            <div style="max-height: 380px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px;">\
                                <table class="table table-hover" style="margin:0; border:none;">\
                                    <thead style="position: sticky; top: 0; background: #f2f2f2; z-index: 1;">\
                                        <tr>\
                                            <th width="35%" style="border-bottom: 1px solid #ddd;">时间</th>\
                                            <th width="35%" style="border-bottom: 1px solid #ddd;">触发规则</th>\
                                            <th width="30%" style="border-bottom: 1px solid #ddd;">执行动作</th>\
                                        </tr>\
                                    </thead>\
                                    <tbody>\
                                        ' + tbodyHtml + '\
                                    </tbody>\
                                </table>\
                            </div>\
                        </div>\
                    </div>';
        
        layer.open({
            type: 1,
            title: "【"+$('<div>').text(ip).html() + "】 触发详情",
            area: '650px',
            closeBtn: 1,
            shadeClose: false,
            content: content
        });
    });
}

function f2bSiteHistory(){
    var randstr = getRandomString(10);
    var html = '<div>\
                <div style="display: flex; align-items: center; justify-content: space-between; padding-bottom:10px;">\
                    <div style="display: flex; align-items: center;">\
                        <span style="margin-left:10px">时间: </span>\
                        <div class="input-group" style="margin-left:10px;width:350px;display: inline-table;vertical-align: top;">\
                            <div id="search_time" class="input-group-btn btn-group-sm">\
                                <button data-name="today" type="button" class="btn btn-default cur">今日</button>\
                                <button data-name="yesterday" type="button" class="btn btn-default">昨日</button>\
                                <button data-name="l7" type="button" class="btn btn-default">近7天</button>\
                                <button data-name="l30" type="button" class="btn btn-default">近30天</button>\
                            </div>\
                            <span class="last-span"><input data-name="" type="text" id="time_choose" lay-key="1000001_'+randstr+'" class="form-control btn-group-sm" autocomplete="off" placeholder="自定义时间" style="display: inline-block;font-size: 12px;padding: 0 10px;height:30px;width: 155px;"></span>\
                        </div>\
                    </div>\
                    <div>\
                        <button id="refreshLogs" class="btn btn-default btn-sm" style="padding-left: 5px;padding-right: 5px; margin-left: 5px;">刷新</button>\
                    </div>\
                </div>\
                <div class="divtable mtb10" id="ws_table"></div>\
            </div>';
    $(".soft-man-con").html(html);
    
    $(".soft-man-con").off("click", "#exportExcel").on("click", "#exportExcel", function(){
        var args = {};
        args['page'] = 1;
        args['page_size'] = 100000;
        var query_date = 'today';
        if ($('#time_choose').attr("data-name") != '' && $('#time_choose').attr("data-name") != undefined){
            query_date = $('#time_choose').attr("data-name");
        } else {
            query_date = $('#search_time button.cur').attr("data-name");
        }
        args['query_date'] = query_date;
        args['tojs'] = 'f2bLogRequest';

        var loadT = layer.msg('正在导出，请稍候...', { icon: 16, time: 0, shade: [0.3, '#000'] });
        f2bPost('get_logs_list', '', args, function(rdata){
            layer.close(loadT);
            var rdata = $.parseJSON(rdata.data);
            var data = rdata.data.data;
            if(!data || data.length == 0) {
                layer.msg("没有数据可导出", {icon: 2});
                return;
            }
            var csv = "\uFEFF时间,IP,规则名,原因\n";
            for(var i=0; i<data.length; i++) {
                var d = data[i];
                csv += getLocalTime(d.time) + "," + d.ip + "," + d.rule_name + "," + '"' + (d.reason||'').replace(/"/g, '""') + '"\n';
            }
            var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = "防护历史.csv";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        });
    });

    $("#refreshLogs").click(function(){
        f2bLogRequest(1);
    });

    //日期范围
    if(typeof laydate !== 'undefined') {
        laydate.render({
            elem: '#time_choose',
            value:'',
            range:true,
            done:function(value, startDate, endDate){
                if(!value){
                    return false;
                }

                $('#search_time button').each(function(){
                    $(this).removeClass('cur');
                });

                var timeA  = value.split('-');
                var start = $.trim(timeA[0]+'-'+timeA[1]+'-'+timeA[2])
                var end = $.trim(timeA[3]+'-'+timeA[4]+'-'+timeA[5])
                var query_txt = toUnixTime(start + " 00:00:00") + "-"+ toUnixTime(end + " 00:00:00")

                $('#time_choose').attr("data-name",query_txt);
                $('#time_choose').addClass("cur");

                f2bLogRequest(1);
            },
        });
    }

    $('#search_time button').click(function(){
        $('#search_time button').each(function(){
            if ($(this).hasClass('cur')){
                $(this).removeClass('cur');
            }
        });
        $('#time_choose').attr("data-name",'');
        $('#time_choose').removeClass("cur");
        $('#time_choose').val('');

        $(this).addClass('cur');

        f2bLogRequest(1);
    });

    f2bLogRequest(1);
}