var api = YfPlugin.createApi('fail2ban');
var pt = YfI18n.createPluginTranslator('fail2ban');

// 当前面板语言（用于归属地查询等服务端侧的语言联动）
function f2bCurrentLang() {
    try {
        if (window.YfI18n) {
            if (typeof window.YfI18n.getLanguage === 'function') {
                return window.YfI18n.getLanguage() || 'zh-CN';
            }
            if (window.YfI18n.currentLang) {
                return window.YfI18n.currentLang;
            }
        }
    } catch (e) {}
    return 'zh-CN';
}

// jail 名称展示：专用 jail 用可翻译文案呈现
function f2bJailLabel(jail) {
    if (jail === 'yf-manual') {
        return pt('手动黑名单');
    }
    if (jail === 'op-waf') {
        return pt('御风OP防火墙情报联动');
    }
    return jail;
}

// 后端返回消息的多语言渲染。
// 后端为了保持调试信息，会以「可翻译前缀 + 动态参数」的形式返回（如 `IP格式错误 1.2.3.4`），
// 因此这里先把动态部分拆出来，再用带 {1} 的完整键去查表，避免整串拼死的文本查不到译文。
var F2B_MSG_PATTERNS = [
    [/^缺少必要参数:\s*(.+)$/, '缺少必要参数: {1}'],
    // 必须要求「空白 + 非空参数」：否则裸消息 `IP格式错误`（无参数）也会命中，
    // 被渲染成 `IP格式错误 `（尾部空参数），既难看又丢失了纯静态键的查表机会
    [/^IP格式错误\s+(.+)$/, 'IP格式错误 {1}'],
    [/^不支持的防护类型:\s*(.+)$/, '不支持的防护类型: {1}'],
    [/^部分IP封禁失败:\s*(.+)$/, '部分IP封禁失败: {1}'],
    [/^未找到Fail2ban数据库:\s*(.+)$/, '未找到Fail2ban数据库: {1}'],
    [/^无法读取Fail2ban数据库:\s*(.+)$/, '无法读取Fail2ban数据库: {1}']
];

function f2bMsg(msg) {
    msg = String(msg == null ? '' : msg);
    for (var i = 0; i < F2B_MSG_PATTERNS.length; i++) {
        var m = msg.match(F2B_MSG_PATTERNS[i][0]);
        if (m) {
            return msgTpl(pt(F2B_MSG_PATTERNS[i][1]), [m[1]]);
        }
    }
    return pt(msg);
}

// 封禁原因多语言渲染：后端返回可翻译键 reason_code，前端负责本地化
function f2bReasonText(item) {
    var code = (item && (item.reason_code || item.reason)) || '';
    var text = code ? pt(code) : pt('触发防御规则，已被自动拦截');
    if (item && item.restore) {
        text = msgTpl(pt('服务重启，恢复历史封禁 ({1})'), [text]);
    }
    return text;
}

function getVersion(){
    return $('.plugin_version').attr('version');
}

function f2bHome() {
    var loadT = layer.msg(pt('正在获取数据...'), { icon: 16, time: 0, shade: 0.3 });
    api.post('get_home_stats', '', {}, function(data){
        layer.close(loadT);
        var rdata = JSON.parse(data.data);
        var stats = rdata.data;
        
        var todayBans = stats.today_bans || 0;
        var totalBans = stats.total_bans || 0;
        var protectDays = stats.protect_days || 0;
        var jailStats = stats.jail_stats || {};

        var jailNames = {
            'sshd': pt('SSH 防爆破'),
            'ftpd': pt('FTP 防爆破'),
            'mysql': pt('MySQL 防爆破'),
            'dovecot': pt('Dovecot 邮局'),
            'postfix': pt('Postfix 邮局'),
            'global-cc': pt('全局防 CC 攻击'),
            'global-scan': pt('全局防恶意扫描')
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
            jailHtml = '<div style="width: 100%; text-align: center; color: #999; padding: 40px 0;">' + pt('暂无拦截数据') + '</div>';
        }

        var html = '<div style="padding: 15px;">\
            <div style="display: flex; justify-content: space-between; margin-bottom: 20px;">\
                <div style="width: 32%; background: #fd6e1e; border-radius: 6px; padding: 25px 0; text-align: center; color: #fff; box-shadow: 0 4px 8px rgba(253,110,30,.2);">\
                    <div style="font-size: 15px; margin-bottom: 10px;">' + pt('今日拦截 (次)') + '</div>\
                    <div style="font-size: 32px; font-weight: bold;">' + todayBans + '</div>\
                </div>\
                <div style="width: 32%; background: #00b96b; border-radius: 6px; padding: 25px 0; text-align: center; color: #fff; box-shadow: 0 4px 8px rgba(0,185,107,.2);">\
                    <div style="font-size: 15px; margin-bottom: 10px;">' + pt('总拦截 (次)') + '</div>\
                    <div style="font-size: 32px; font-weight: bold;">' + totalBans + '</div>\
                </div>\
                <div style="width: 32%; background: #2f69f8; border-radius: 6px; padding: 25px 0; text-align: center; color: #fff; box-shadow: 0 4px 8px rgba(47,105,248,.2);">\
                    <div style="font-size: 15px; margin-bottom: 10px;">' + pt('安全防护 (天)') + '</div>\
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
                <div style="color: #666;"><span style="color:#20a53a; font-weight:bold; margin-right:5px;">√</span> ' + pt('御风F2B底层防火墙 是一款入侵防御软件，通过监控系统与服务的访问日志，自动将多次尝试失败的恶意源 IP 添加到防火墙的拦截规则中。') + '</div>\
                <div style="color: #666;"><span style="color:#20a53a; font-weight:bold; margin-right:5px;">√</span> ' + pt('系统防护用于防范服务器 SSH、FTP、MySQL 等服务的账号密码暴力破解。') + '</div>\
                <div style="color: #666;"><span style="color:#20a53a; font-weight:bold; margin-right:5px;">√</span> ' + pt('网站防护自动分析 Web 访问日志，有效防御 CC 攻击与高频自动化漏洞扫描，保障业务可用性。') + '</div>\
            </div>\
        </div>';

        $('.soft-man-con').html(html);
    });
}

function f2bService() {
    pluginService('fail2ban');
    var waitTimer = setInterval(function() {
        // 语言无关的就绪判定：服务面板必然渲染 .sfm-opt 容器。
        // 原实现用 indexOf('当前状态') 判断，英文/德文等面板下永远匹配不到，
        // 导致严格模式开关与使用指南整块不显示。
        if ($('.soft-man-con').find('.sfm-opt').length > 0) {
            clearInterval(waitTimer);
            if ($('.soft-man-con').find('#f2b_intro_panel').length === 0) {
                // Fetch the config info to see if strict mode is enabled
                api.post('get_anti_info', '', {}, function(data) {
                    var rdata = {};
                    try {
                        rdata = JSON.parse(data.data);
                    } catch(e) {}
                    var strict = true;
                    if (rdata && rdata.hasOwnProperty('strict')) {
                        strict = rdata.strict;
                    }
                    
                    // Add checkbox next to reload button in .sfm-opt
                    var checkboxHtml = '<label style="margin-left: 30px; font-weight: normal; cursor: pointer; display: inline-flex; align-items: center; vertical-align: middle; user-select: none;">\
                        <input type="checkbox" id="f2b_strict_mode" style="margin-right: 5px; width: 15px; height: 15px; cursor: pointer; margin-top: 0;" ' + (strict ? 'checked' : '') + '> ' + pt('严格模式') + '\
                    </label>\
                    <span style="color: #666; margin-left: 10px; font-size: 12px; vertical-align: middle; display: inline-block;">' + pt('（开启后，任意项目触发将封禁该IP访问所有配置的服务）') + '</span>';
                    
                    var sfmOpt = $('.soft-man-con').find('.sfm-opt');
                    if (sfmOpt.find('#f2b_strict_mode').length === 0) {
                        sfmOpt.append(checkboxHtml);
                    }
                    
                    // Listen to changes on the checkbox
                    $('#f2b_strict_mode').off('change').on('change', function() {
                        var isChecked = $(this).prop('checked');
                        api.post('set_strict_mode', '', { strict: isChecked }, function(res) {
                            var r = JSON.parse(res.data);
                            layer.msg(f2bMsg(r.msg), { icon: r.status ? 1 : 2 });
                        });
                    });
                });

                var infoHtml = '<div id="f2b_intro_panel" class="help-info-text c7" style="margin-top: 15px; padding: 15px; border: 1px dashed #ccc; border-radius: 4px; line-height: 24px;">\
                    <h3 style="margin-top:0; margin-bottom: 10px; font-size: 14px; font-weight: bold; color: #333;">' + pt('📖 御风F2B底层防火墙  使用指南') + '</h3>\
                    <p style="margin-bottom: 5px;"><b>' + pt('御风F2B底层防火墙') + '</b> ' + pt('是一款入侵防御软件，通过监控系统与服务的访问日志，自动将多次尝试失败的恶意源 IP 添加到防火墙的拦截规则中。') + '</p>\
                    <ul style="margin-bottom: 0; padding-left: 20px;">\
                        <li><b>' + pt('系统防护') + '</b>' + pt('：用于防范服务器 SSH、FTP、MySQL 等服务的账号密码暴力破解。') + '</li>\
                        <li><b>' + pt('网站防护') + '</b>' + pt('：自动分析 Web 访问日志，有效防御 CC 攻击与高频自动化漏洞扫描，保障业务可用性。') + '</li>\
                        <li><b>' + pt('IP黑名单') + '</b>' + pt('：您可以在此查看当前被防火墙封禁拦截的攻击源 IP，并支持手动添加或解除封禁。') + '</li>\
                        <li><b>' + pt('严格模式') + '</b>' + pt('：开启后，任意受保护的项目触发拦截，将封禁该 IP 访问所有已配置的防护内容。') + '</li>\
                    </ul>\
                </div>';
                $('.soft-man-con').append(infoHtml);
            }
        }
    }, 100);
    // 5秒后停止检测，防止死循环
    setTimeout(function() { clearInterval(waitTimer); }, 5000);
}



function f2bPostCallbak(method, version, args, callback){
    var loadT = layer.msg(pt('正在获取...'), { icon: 16, time: 0, shade: 0.3 });

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
            layer.msg(f2bMsg(data.msg),{icon:0,time:2000,shade: [0.3, '#000']});
            return;
        }

        if(typeof(callback) == 'function'){
            callback(data);
        }
    },'json'); 
}

function f2bBanIpSave(black_ip){
    api.post('ban_ip_release', '', {}, function(data){
        var rdata = JSON.parse(data.data);
        layer.msg(f2bMsg(rdata.msg), { icon: rdata.status ? 1 : 2 });
    });
}

// 运行日志
function f2bLogs(){
    var con = '<div class="divtable">' +
                '<textarea class="bt-input-text" style="height: 440px; width: 100%; line-height:22px; padding: 10px; background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas, monospace; border: none; border-radius: 4px;" id="f2bLogBody" readonly></textarea>' +
                '<div style="margin-top:10px; display: flex; justify-content: space-between; align-items: center;">' +
                    '<button id="f2bClearLogBtn" class="btn btn-default btn-sm">' + pt('清空日志') + '</button>' +
                    '<button id="f2bRefreshLogBtn" class="btn btn-default btn-sm"><i class="glyphicon glyphicon-refresh"></i> ' + pt('刷新日志') + '</button>' +
                '</div>' +
               '</div>';
    $(".soft-man-con").html(con);
    
    function refreshLog() {
        var loadT = layer.msg(pt('正在获取日志...'), { icon: 16, time: 0, shade: 0.3 });
        api.post('get_last_log', '', {}, function(data){
            layer.close(loadT);
            var rdata = JSON.parse(data.data);
            var logContent = rdata.data || pt('暂无日志数据');
            $("#f2bLogBody").text(logContent);
            var textarea = document.getElementById('f2bLogBody');
            if (textarea) {
                textarea.scrollTop = textarea.scrollHeight;
            }
        });
    }
    refreshLog();
    
    $("#f2bRefreshLogBtn").on('click', function(){
        refreshLog();
    });

    $("#f2bClearLogBtn").on('click', function(){
        layer.confirm(pt('确定要清空 fail2ban 的运行日志吗？'), {title:  pt('清空日志')}, function(index) {
            api.post('clear_log', '', {}, function(data){
                var rdata = JSON.parse(data.data);
                layer.msg(f2bMsg(rdata.msg), { icon: rdata.status ? 1 : 2 });
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
                <input class="bt-input-text" type="text" id="f2b_add_ip_input" placeholder="' + pt('输入IP地址，例如1.1.1.1') + '" style="width: 200px; margin-right: 5px;">\
                <button class="btn btn-success btn-sm" onclick="f2bAddDropIp();">' + pt('添加黑名单') + '</button>\
            </div>\
            <button class="btn btn-default btn-sm" onclick="f2bBanIp();"><i class="glyphicon glyphicon-refresh"></i> ' + pt('刷新') + '</button>\
        </div>\
        <div class="divtable">\
            <table class="table table-hover">\
                <thead>\
                    <tr>\
                        <th width="20%">' + pt('IP 地址') + '</th>\
                        <th width="15%">' + pt('触发规则') + '</th>\
                        <th width="30%">' + pt('IP归属') + '</th>\
                        <th width="20%">' + pt('剩余封禁时间') + '</th>\
                        <th width="15%" style="text-align: right;">' + pt('操作') + '</th>\
                    </tr>\
                </thead>\
                <tbody id="f2b_drop_ip_list_body">\
                    <tr><td colspan="5" style="text-align:center;">' + pt('正在加载数据...') + '</td></tr>\
                </tbody>\
            </table>\
        </div>\
    </div>';

    $('.soft-man-con').html(html);

    api.post('get_active_bans', '', {}, function(data){
        var rdata = JSON.parse(data.data);
        if(!rdata.status) {
            $('#f2b_drop_ip_list_body').html('<tr><td colspan="5" style="text-align:center; color:red;">' + f2bMsg(rdata.msg) + '</td></tr>');
            return;
        }

        var bans = rdata.data;
        if (!bans || bans.length === 0) {
            $('#f2b_drop_ip_list_body').html('<tr><td colspan="5" style="text-align:center;">' + pt('暂无封禁 IP。') + '</td></tr>');
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
                locDisplay = '<span style="color:#999;">' + pt('正在获取...') + '</span>';
                if(pendingIps.indexOf(ip) === -1) pendingIps.push(ip);
            }

            var timeRemaining = '';
            if (bantime < 0) {
                timeRemaining = '<span style="color:#d9534f; font-weight:bold;">' + pt('永久封禁') + '</span>';
            } else {
                var diff = expire_time - nowTimestamp;
                if (diff <= 0) {
                    timeRemaining = '<span style="color:#f0ad4e;">' + pt('即将解封...') + '</span>';
                } else {
                    var hours = Math.floor(diff / 3600);
                    var minutes = Math.floor((diff % 3600) / 60);
                    if (hours > 0) {
                        timeRemaining = hours + ' ' + pt('小时') + ' ' + minutes + ' ' + pt('分钟');
                    } else {
                        timeRemaining = minutes + ' ' + pt('分钟');
                    }
                }
            }
            if (item.manual === true) {
                timeRemaining += ' <span style="color:#2f69f8; font-size:12px;">(' + pt('手动添加') + ')</span>';
            }

            tbodyHtml += '<tr>\
                <td><span style="color:#d9534f; font-family: Consolas, monospace; font-weight:bold;">' + ip + '</span></td>\
                <td>' + f2bJailLabel(jail) + '</td>\
                <td id="' + ipId + '">' + locDisplay + '</td>\
                <td>' + timeRemaining + '</td>\
                <td style="text-align: right;">\
                    <a href="javascript:;" class="btlink" style="color:#20a53a;" onclick="f2bRemoveDropIp(\'' + ip + '\', \'' + jail + '\')">' + pt('解除封禁') + '</a>\
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
                    api.post('getIpLocationBatch', '', {ips: JSON.stringify(ips), lang: f2bCurrentLang()}, function(data) {
                        var loc_res = JSON.parse(data.data);
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
                                    if (!finalStr) finalStr = pt('未知');
                                    
                                    locCache[bItem.query] = finalStr;
                                    $('[id^="ip_loc_' + bItem.query.replace(/\./g, '_').replace(/:/g, '_') + '"]').html(finalStr);
                                } else if (bItem && bItem.query) {
                                    $('[id^="ip_loc_' + bItem.query.replace(/\./g, '_').replace(/:/g, '_') + '"]').html(pt('局域网/保留地址'));
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
    // 单键插值：碎片拼接会让德/法/意等语言语义破碎
    var confirmMsg = msgTpl(pt('确定要解封 IP ({1}) 吗？'), [ip]);
    // 联动封禁提示：让用户明确知道解封会同时作用于内核层与应用层，
    // 根治「在 op_waf 解封了却仍访问不了」的困惑。
    if (jail === 'op-waf' || jail === 'yf-manual') {
        confirmMsg += '<br><span style="color:#8a6100; font-size:12px;">' + pt('该封禁已与「御风OP防火墙」联动，解封会同时解除内核层与应用层的封禁。') + '</span>';
    }
    layer.confirm(confirmMsg, {title:  pt('解除封禁'), icon: 3}, function(index) {
        layer.close(index);
        var loadT = layer.msg(pt('正在解封...'), {icon: 16, time: 0, shade: 0.3});
        
        api.post('unban_active_ip', '', {'ip': ip, 'jail': jail}, function(sdata){
            layer.close(loadT);
            var srdata = JSON.parse(sdata.data);
            if (srdata.status) {
                layer.msg(f2bMsg(srdata.msg), {icon: 1});
            } else {
                layer.msg(f2bMsg(srdata.msg), {icon: 2});
            }
            f2bBanIp();
        });
    });
}

function f2bAddDropIp() {
    var ip = $('#f2b_add_ip_input').val().trim();
    if (!ip) {
        layer.msg(pt('请输入IP地址'), {icon: 2});
        return;
    }
    var loadT = layer.msg(pt('正在添加...'), {icon: 16, time: 0, shade: 0.3});
    api.post('get_black_list', '', {}, function(data){
        var rdata = JSON.parse(data.data);
        var ipListStr = rdata.data;
        var ipList = ipListStr ? ipListStr.split('\n').filter(function(x) { return x.trim() !== ''; }) : [];
        
        if (ipList.indexOf(ip) === -1) {
            ipList.push(ip);
        } else {
            layer.close(loadT);
            layer.msg(pt('该IP已在黑名单中'), {icon: 2});
            return;
        }
        
        api.post('set_black_ip', '', {'black_ip': JSON.stringify(ipList)}, function(sdata){
            layer.close(loadT);
            var srdata = JSON.parse(sdata.data);
            layer.msg(f2bMsg(srdata.msg), {icon: srdata.status ? 1 : 2});
            if (srdata.status) {
                f2bBanIp();
            }
        });
    });
}



// 系统防护
function f2bServerAnti() {
    var loadT = layer.msg(pt('正在获取配置...'), { icon: 16, time: 0, shade: 0.3 });
    api.post('get_anti_info', '', {}, function(data){
        layer.close(loadT);
        var rdata = JSON.parse(data.data);
        var serverRules = (rdata.data && rdata.data.server) ? rdata.data.server : [];
        var defaultSshPort = (rdata.data && rdata.data.default_ssh_port) ? rdata.data.default_ssh_port : '22';
        var defaultMysqlPort = (rdata.data && rdata.data.default_mysql_port) ? rdata.data.default_mysql_port : '3306';
        
        // 预设服务列表
        var presetServices = [
            {name: pt('SSH 防爆破'), mode: 'sshd', port: defaultSshPort, maxretry: 5, findtime: 300, bantime: 86400},
            {name: pt('FTP 防爆破'), mode: 'ftpd', port: '21', maxretry: 5, findtime: 300, bantime: 86400},
            {name: pt('MySQL 防爆破'), mode: 'mysql', port: defaultMysqlPort, maxretry: 5, findtime: 300, bantime: 86400},
            {name: pt('Dovecot (邮局)'), mode: 'dovecot', port: '110', maxretry: 5, findtime: 300, bantime: 86400},
            {name: pt('Postfix (邮局)'), mode: 'postfix', port: '25', maxretry: 5, findtime: 300, bantime: 86400}
        ];

        var tbody = '';
        $.each(presetServices, function(i, item) {
            // 查看是否已配置
            var configured = null;
            $.each(serverRules, function(j, rule) {
                if(rule.mode == item.mode) configured = rule;
            });

            var statusStr = '<span style="color:red">' + pt('未配置') + '</span>';
            var btnStr = '<a href="javascript:;" class="btlink" onclick="f2bConfigService(\''+item.mode+'\', \''+item.name+'\', \''+item.port+'\', \''+item.maxretry+'\', \''+item.findtime+'\', \''+item.bantime+'\')">' + pt('配置') + '</a>';
            
            if(configured) {
                if(configured.act == 'true' || configured.act == true) {
                    statusStr = '<span style="color:green">' + pt('防御中') + '</span>';
                } else {
                    statusStr = '<span style="color:orange">' + pt('已停用') + '</span>';
                }
                btnStr = '<a href="javascript:;" class="btlink" onclick="f2bConfigService(\''+item.mode+'\', \''+item.name+'\', \''+configured.port+'\', \''+configured.maxretry+'\', \''+configured.findtime+'\', \''+configured.bantime+'\')">' + pt('修改') + '</a> | ' +
                         '<a href="javascript:;" class="btlink" onclick="f2bDelAnti(\''+item.mode+'\')">' + pt('删除') + '</a>';
            }

            tbody += '<tr>' +
                        '<td>' + item.name + ' (' + item.mode + ')</td>' +
                        '<td>' + (configured ? configured.port : '-') + '</td>' +
                        '<td>' + (configured ? configured.maxretry + pt('次') + ' / ' + configured.findtime + pt('秒') : '-') + '</td>' +
                        '<td>' + (configured ? configured.bantime + pt('秒') : '-') + '</td>' +
                        '<td>' + statusStr + '</td>' +
                        '<td style="text-align: right;">' + btnStr + '</td>' +
                     '</tr>';
        });

        var con = '<div class="divtable">' +
                  '<table class="table table-hover">' +
                  '<thead><tr><th>' + pt('服务名称') + '</th><th>' + pt('端口') + '</th><th>' + pt('拦截条件') + '</th><th>' + pt('封禁时长') + '</th><th>' + pt('状态') + '</th><th style="text-align: right;">' + pt('操作') + '</th></tr></thead>' +
                  '<tbody>' + tbody + '</tbody>' +
                  '</table>' +
                  '<ul class="help-info-text c7 ptb15"><li>' + pt('系统服务防暴力破解，配置后当多次认证失败时将在底层防火墙直接封禁对应来源IP。') + '</li></ul>' +
                  '</div>';
        $(".soft-man-con").html(con);
    });
}

function f2bConfigService(mode, name, port, maxretry, findtime, bantime) {
    var content = '<div class="bt-form pd20 pb70">' +
        '<div class="line"><span class="tname">' + pt('防爆破服务') + '</span><div class="info-r"><input class="bt-input-text" type="text" disabled value="'+name+'" style="width:250px" /></div></div>' +
        '<div class="line"><span class="tname">' + pt('防护端口') + '</span><div class="info-r"><input class="bt-input-text" name="port" type="text" value="'+port+'" style="width:250px" /></div></div>' +
        '<div class="line"><span class="tname">' + pt('检测周期') + '</span><div class="info-r"><input class="bt-input-text" name="findtime" type="number" value="'+findtime+'" style="width:250px" />  ' + pt('秒') + '</div></div>' +
        '<div class="line"><span class="tname">' + pt('最大失败次数') + '</span><div class="info-r"><input class="bt-input-text" name="maxretry" type="number" value="'+maxretry+'" style="width:250px" />  ' + pt('次') + '</div></div>' +
        '<div class="line"><span class="tname">' + pt('封禁时间') + '</span><div class="info-r"><input class="bt-input-text" name="bantime" type="number" value="'+bantime+'" style="width:250px" />  ' + pt('秒') + '</div></div>' +
        '<div class="line"><span class="tname">' + pt('状态') + '</span><div class="info-r"><select class="bt-input-text" name="act" style="width:250px"><option value="true">' + pt('启用') + '</option><option value="false">' + pt('停用') + '</option></select></div></div>' +
        '</div>';

    layer.open({
        type: 1,
        title: pt('配置防护规则 -') + name,
        area: '450px',
        closeBtn: 1,
        shadeClose: false,
        content: content,
        btn: [pt('提交'), pt('取消')],
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
            api.post('set_anti', '', postData, function(data){
                var rdata = JSON.parse(data.data);
                layer.msg(f2bMsg(rdata.msg), { icon: rdata.status ? 1 : 2 });
                if(rdata.status) {
                    layer.close(index);
                    if (mode.indexOf('-') > 0) f2bSiteAnti(); else f2bServerAnti();
                }
            });
        }
    });
}

function f2bDelAnti(mode) {
    layer.confirm(pt('确定要删除并停用该防护规则吗？'), {title:  pt('停用规则')}, function(index) {
        api.post('del_anti', '', {mode: mode, type: 'edit'}, function(data){
            var rdata = JSON.parse(data.data);
            layer.msg(f2bMsg(rdata.msg), { icon: rdata.status ? 1 : 2 });
            if(rdata.status) {
                layer.close(index);
                if(mode.indexOf('-') > 0) f2bSiteAnti(); else f2bServerAnti();
            }
        });
    });
}

// 网站防护
function f2bSiteAnti() {
    var loadT = layer.msg(pt('正在拉取防护状态...'), { icon: 16, time: 0, shade: 0.3 });
    api.post('get_anti_info', '', {}, function(data){
        layer.close(loadT);
        var rdata = JSON.parse(data.data);
        var siteRules = (rdata.data && rdata.data.site) ? rdata.data.site : [];
        var opWaf = (rdata.data && rdata.data.op_waf) ? rdata.data.op_waf : { installed: false, linked: false };
        var opWafLink = (rdata.data && rdata.data.op_waf_link) ? rdata.data.op_waf_link : { bantime: 86400 };
        
        // 预设服务列表
        var presetServices = [
            {name: pt('全局防 CC 攻击'), mode: 'global-cc', port: '80,443', maxretry: 60, findtime: 60, bantime: 86400},
            {name: pt('全局防恶意扫描'), mode: 'global-scan', port: '80,443', maxretry: 30, findtime: 60, bantime: 86400}
        ];

        var tbody = '';
        $.each(presetServices, function(i, item) {
            // 查看是否已配置
            var configured = null;
            $.each(siteRules, function(j, rule) {
                if(rule.mode == item.mode) configured = rule;
            });

            var statusStr = '<span style="color:red">' + pt('未配置') + '</span>';
            var btnStr = '<a href="javascript:;" class="btlink" onclick="f2bConfigService(\''+item.mode+'\', \''+item.name+'\', \''+item.port+'\', \''+item.maxretry+'\', \''+item.findtime+'\', \''+item.bantime+'\')">' + pt('配置') + '</a>';
            
            if(configured) {
                if(configured.act == 'true' || configured.act == true) {
                    statusStr = '<span style="color:green">' + pt('防御中') + '</span>';
                } else {
                    statusStr = '<span style="color:orange">' + pt('已停用') + '</span>';
                }
                btnStr = '<a href="javascript:;" class="btlink" onclick="f2bConfigService(\''+item.mode+'\', \''+item.name+'\', \''+configured.port+'\', \''+configured.maxretry+'\', \''+configured.findtime+'\', \''+configured.bantime+'\')">' + pt('修改') + '</a> | ' +
                         '<a href="javascript:;" class="btlink" onclick="f2bDelAnti(\''+item.mode+'\')">' + pt('删除') + '</a>';
            }

            tbody += '<tr>' +
                        '<td>' + item.name + ' (' + item.mode + ')</td>' +
                        '<td>' + (configured ? configured.port : item.port) + '</td>' +
                        '<td>' + (configured ? configured.maxretry + pt('次') + ' / ' + configured.findtime + pt('秒') : item.maxretry + pt('次') + ' / ' + item.findtime + pt('秒')) + '</td>' +
                        '<td>' + (configured ? configured.bantime + pt('秒') : item.bantime + pt('秒')) + '</td>' +
                        '<td>' + statusStr + '</td>' +
                        '<td style="text-align: right;">' + btnStr + '</td>' +
                     '</tr>';
        });

        // 本插件是否仍在重复接管 Web 层：global-cc / global-scan 任一处于启用状态
        // （未配置的规则视为未启用 —— 没启用就没有重复，无需提示）
        var siteAntiActive = false;
        $.each(['global-cc', 'global-scan'], function(i, mode) {
            $.each(siteRules, function(j, rule) {
                if (rule.mode == mode && (rule.act == 'true' || rule.act === true)) {
                    siteAntiActive = true;
                }
            });
        });

        // 职责边界提示（三态，仅在检测到 op_waf 时出现）：
        //   A. 本插件仍在重复接管 Web 层 → 黄色警告条 + 「一键停用」按钮
        //   B. 本插件已不再接管 Web 层     → 绿色「已托管」条，明确告知职责已移交，
        //      并顺带说明攻击 IP 的归宿（内核层持久封禁取决于情报联动是否开启）
        //   C. 未安装 op_waf               → 不展示（本插件是唯一的 Web 层防护者）
        var boundaryHtml = '';
        if (opWaf.installed && siteAntiActive) {
            boundaryHtml = '<div style="background:#fff8e6; border:1px solid #ffe1a8; border-radius:6px; padding:14px 16px; margin-bottom:15px;">\
                <div style="color:#8a6100; font-size:13px; font-weight:bold; margin-bottom:8px;">\
                    <span class="glyphicon glyphicon-alert" style="margin-right:6px;"></span>' + pt('检测到「御风OP防火墙」已安装') + '\
                </div>\
                <div style="color:#7a5c1e; font-size:12px; line-height:20px; margin-bottom:10px;">\
                    ' + pt('CC 攻击、恶意扫描等 Web 层威胁由它在应用层实时拦截。若此处再开启 global-cc / global-scan，同一攻击会被重复封禁，且在 OP 防火墙解封后仍会被本插件在内核层封禁，出现「解封了还是访问不了」。建议只保留其一。') + '\
                </div>\
                <button class="btn btn-warning btn-sm" onclick="f2bDisableSiteAnti();">' + pt('一键停用重复的网站防护') + '</button>\
            </div>';
        } else if (opWaf.installed) {
            // 攻击 IP 的归宿：联动开启 → 内核层持久封禁；未开启 → 提示去开启
            var linkHint = opWaf.linked
                ? pt('情报联动已开启：OP 防火墙识别到的攻击 IP 仍会在本插件内核层以 iptables 全端口持久封禁，即使 Nginx 重启也不会失效。')
                : pt('提示：如需让 OP 防火墙识别到的攻击 IP 同时在内核层持久封禁，可在下方开启「御风OP防火墙情报联动」。');
            boundaryHtml = '<div style="background:#f0faf3; border:1px solid #b9e6c8; border-radius:6px; padding:14px 16px; margin-bottom:15px;">\
                <div style="color:#1a7f37; font-size:13px; font-weight:bold; margin-bottom:8px;">\
                    <span class="glyphicon glyphicon-ok-sign" style="margin-right:6px;"></span>' + pt('网站防护已托管至御风OP防火墙') + '\
                </div>\
                <div style="color:#3d6b4d; font-size:12px; line-height:20px; margin-bottom:6px;">\
                    ' + pt('Web 层威胁（CC 攻击 / 恶意扫描）由「御风OP防火墙」在应用层实时拦截，本插件不再重复接管，避免同一攻击被双重封禁、解封后仍无法访问。如需恢复，可在上方表格中重新启用。') + '\
                </div>\
                <div style="color:#5a7a66; font-size:12px; line-height:20px;">' + linkHint + '</div>\
            </div>';
        }

        // 情报联动状态：仅当检测到 op_waf 时展示
        var linkHtml = '';
        if (opWaf.installed) {
            var linkedBadge = opWaf.linked
                ? '<span style="color:#20a53a; font-weight:bold;">' + pt('已接入') + '</span>'
                : '<span style="color:#999;">' + pt('未接入') + '</span>';
            // 开关必须挂在 input 的 onchange 上：<label for=...> 的 onclick 早于
            // checkbox 翻转执行，在那里读状态只会拿到旧值（op_waf 侧曾因此整个开关失效）
            var switchHint = opWaf.linked
                ? pt('已开启：OP 防火墙识别到的攻击 IP 会同步到本插件内核层持久封禁。')
                : pt('当前未开启。开启后，OP 防火墙识别到的攻击 IP 将同步到本插件，在内核层以 iptables 全端口持久封禁。');
            linkHtml = '<div style="background:#f8f9fa; border:1px solid #e9ecef; border-radius:6px; padding:20px; margin-top:10px;">\
                <h4 style="color:#333; font-size:14px; font-weight:bold; margin-top:0; margin-bottom:15px; border-bottom:1px solid #eaeaea; padding-bottom:10px;">\
                    <span class="glyphicon glyphicon-transfer" style="color:#20a53a; margin-right:8px;"></span>' + pt('御风OP防火墙情报联动') + '\
                </h4>\
                <div style="color:#666; font-size:13px; line-height:24px; margin-bottom:10px;">\
                    ' + pt('由 OP 防火墙识别出的攻击 IP，在本插件内核层以 iptables 全端口持久封禁，即使 Nginx 重启也不会失效。') + '\
                </div>\
                <div style="color:#666; font-size:13px; line-height:28px;">\
                    <span style="display:inline-block; width:120px;">' + pt('状态') + '</span>' + linkedBadge + '\
                </div>\
                <div style="color:#666; font-size:13px; line-height:28px;">\
                    <span style="display:inline-block; width:120px; vertical-align:middle;">' + pt('联动开关') + '</span>\
                    <span style="display:inline-flex; align-items:center; vertical-align:middle;">\
                        <input class="btswitch btswitch-ios" id="f2b_op_waf_link_switch" type="checkbox" ' + (opWaf.linked ? 'checked' : '') + ' onchange="f2bToggleOpWafLink();">\
                        <label class="btswitch-btn" for="f2b_op_waf_link_switch" style="margin-left:6px;"></label>\
                        <span style="margin-left:10px; font-size:12px; color:#888;">' + (opWaf.linked ? pt('已开启') : pt('已关闭')) + '</span>\
                    </span>\
                </div>\
                <div style="color:#999; font-size:12px; line-height:20px; margin:4px 0 10px 120px;">' + switchHint + '</div>\
                <div style="color:#666; font-size:13px; line-height:28px;">\
                    <span style="display:inline-block; width:120px;">' + pt('情报来源') + '</span>' + pt('应用层') + ' (op_waf)\
                </div>\
                <div style="color:#666; font-size:13px; line-height:28px;">\
                    <span style="display:inline-block; width:120px;">' + pt('封禁时长') + '</span>\
                    <input class="bt-input-text" type="number" min="1" id="f2b_op_waf_bantime" value="' + (opWafLink.bantime || 86400) + '" style="width:120px; display:inline-block;">\
                    <span style="margin-left:6px;">' + pt('秒') + '</span>\
                    <button class="btn btn-success btn-sm" style="margin-left:10px;" onclick="f2bSetOpWafLink();">' + pt('保存') + '</button>\
                </div>\
                <ul class="help-info-text c7" style="margin-top:10px; margin-bottom:0;"><li>' + pt('解封会同时作用于内核层与应用层，无需在两处重复操作。') + '</li></ul>\
            </div>';
        }

        var con = boundaryHtml +
                  '<div class="divtable">' +
                  '<table class="table table-hover">' +
                  '<thead><tr><th>' + pt('防护类型') + '</th><th>' + pt('端口') + '</th><th>' + pt('拦截条件') + '</th><th>' + pt('封禁时长') + '</th><th>' + pt('状态') + '</th><th style="text-align: right;">' + pt('操作') + '</th></tr></thead>' +
                  '<tbody>' + tbody + '</tbody>' +
                  '</table>' +
                  '<ul class="help-info-text c7 ptb15" style="margin-bottom:0;"><li>' + pt('开启全局防护后，将自动应用到所有网站，对访问日志进行聚合分析和攻击拦截。') + '</li></ul>' +
                  linkHtml +
                  '<div style="background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 6px; padding: 20px; margin-top: 5px;">\
                      <h4 style="color: #333; font-size: 14px; font-weight: bold; margin-top: 0; margin-bottom: 15px; border-bottom: 1px solid #eaeaea; padding-bottom: 10px;">\
                          <span class="glyphicon glyphicon-shield" style="color:#20a53a; margin-right:8px;"></span>' + pt('网站防护机制深度解析') + '\
                      </h4>\
                      <div style="margin-bottom: 15px;">\
                          <div style="color: #333; font-weight: 600; font-size: 13px; margin-bottom: 6px;">\
                              <span style="display:inline-block; width:6px; height:6px; background:#fd6e1e; border-radius:50%; margin-right:8px; vertical-align:middle;"></span>' + pt('全局防 CC 攻击') + ' (global-cc)\
                          </div>\
                          <div style="color: #666; font-size: 13px; line-height: 22px; padding-left: 14px;">\
                              ' + pt('基于自适应的高频请求识别算法，实时监控所有站点的访问频次。当发现独立 IP 异常密集地请求网页或接口，疑似发起资源枯竭型（CC）攻击时，防火墙将在网络底层直接阻断其连接，确保您的服务器性能不被巨量并发请求拖垮。') + '\
                          </div>\
                      </div>\
                      <div>\
                          <div style="color: #333; font-weight: 600; font-size: 13px; margin-bottom: 6px;">\
                              <span style="display:inline-block; width:6px; height:6px; background:#00b96b; border-radius:50%; margin-right:8px; vertical-align:middle;"></span>' + pt('全局防恶意扫描') + ' (global-scan)\
                          </div>\
                          <div style="color: #666; font-size: 13px; line-height: 22px; padding-left: 14px;">\
                              ' + pt('采用启发式的访问日志特征分析机制，敏锐捕捉黑客的漏洞探测、敏感文件窥探及自动化扫描器行为。一旦发现非正常的试探性探测，系统将果断封禁该攻击源，将被动防御化为主动拦截，大幅降低站点被渗透的风险。') + '\
                          </div>\
                      </div>\
                  </div>' +
                  '</div>';
        $(".soft-man-con").html(con);
    });
}

// 一键停用重复的网站防护（仅在检测到「御风OP防火墙」时可用）
function f2bDisableSiteAnti() {
    layer.confirm(pt('确定要停用 global-cc / global-scan 吗？停用后 Web 层威胁由「御风OP防火墙」在应用层负责拦截。'), {title: pt('提示'), icon: 3}, function(index){
        layer.close(index);
        api.post('disable_site_anti', '', {}, function(data){
            layer.msg(f2bMsg(data.msg), {icon: 1});
            f2bSiteAnti();
        });
    });
}

// 保存「御风OP防火墙」情报联动的封禁时长
function f2bSetOpWafLink() {
    var bantime = parseInt($('#f2b_op_waf_bantime').val(), 10);
    if (!bantime || bantime < 1) {
        layer.msg(pt('封禁时长必须为正整数'), {icon: 0});
        return;
    }
    api.post('set_op_waf_link', '', {bantime: bantime}, function(data){
        layer.msg(f2bMsg(data.msg), {icon: 1});
        f2bSiteAnti();
    });
}

// 开启 / 关闭「御风OP防火墙情报联动」
//
// 必须挂在 input 的 onchange 上（不能挂 label 的 onclick）：
// <label for=...> 的 onclick 早于 checkbox 状态翻转执行，在那里读只会拿到旧值。
// 开关的真实状态由 op_waf 持有（它是封禁情报的生产者），本插件只转发用户意图，
// 再回读 spool 确认，因此成功后必须整体重渲染，让界面与对端真实状态一致。
function f2bToggleOpWafLink() {
    var wantOpen = $('#f2b_op_waf_link_switch').is(':checked');
    // 取消 / 失败时把开关拨回操作前的状态，避免「视觉已切换、实际未生效」
    var revert = function () { $('#f2b_op_waf_link_switch').prop('checked', !wantOpen); };
    var msg = wantOpen
        ? pt('确定要开启「御风OP防火墙情报联动」吗？开启后，OP 防火墙识别到的攻击 IP 将同步到本插件，在内核层以 iptables 全端口持久封禁。')
        : pt('确定要关闭「御风OP防火墙情报联动」吗？关闭后 OP 防火墙识别到的攻击 IP 将只在应用层被拦截，不再做内核层持久封禁。');

    layer.confirm(msg, {title: pt('提示'), icon: 3, cancel: revert}, function(index){
        layer.close(index);
        var loadT = layer.msg(pt('正在设置...'), {icon: 16, time: 0, shade: 0.3});
        api.post('set_op_waf_link_open', '', {open: wantOpen ? '1' : '0'}, function(data){
            layer.close(loadT);
            var r = JSON.parse(data.data);
            layer.msg(f2bMsg(r.msg), {icon: r.status ? 1 : 2});
            if (!r.status) { revert(); return; }
            f2bSiteAnti();
        });
    }, revert);
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

    api.post('get_logs_list', '', args, function(rdata){
        var rdata = typeof rdata.data === "string" ? JSON.parse(rdata.data) : rdata.data;
        var list = '';
        var data = rdata.data.data;
        if (data.length > 0){
            for(i in data){
                list += '<tr>';
                list += '<td><span class="overflow_hide" title="' + getLocalTime(data[i]['time']) + '" style="width:145px;">' + getLocalTime(data[i]['time'])+'</span></td>';
                list += '<td><span class="overflow_hide" title="' + data[i]['ip'] + '" style="width:120px; font-family: Consolas, monospace; font-weight:bold; color:#d9534f;">' + data[i]['ip'] +'</span></td>';
                list += '<td><span class="overflow_hide" title="' + data[i]['rule_name'] + '" style="width:100px;">' + data[i]['rule_name'] +'</span></td>';
                var reasonText = f2bReasonText(data[i]);
                list += '<td><span class="overflow_hide" title="' + reasonText + '" style="width:300px;">' + reasonText +'</span></td>';
                list += '<td style="text-align:right;"><a onclick="f2bIpDetails(\''+data[i]['ip']+'\')" href="javascript:;" class="btlink f2b-details" title="' + pt('详情') + '">' + pt('详情') + '</a></td>';
                list += '</tr>';
            }
        } else{
             list += '<tr><td colspan="4" style="text-align:center;">' + pt('封锁日志为空') + '</td></tr>';
        }
        
        var table = '<div class="tablescroll">\
                            <table id="DataBody" class="table table-hover" width="100%" cellspacing="0" cellpadding="0" border="0" style="border: 0 none;">\
                            <thead><tr>\
                            <th>' + pt('时间') + '</th>\
                            <th>IP</th>\
                            <th>' + pt('规则名') + '</th>\
                            <th>' + pt('原因') + '</th>\
                            <th style="text-align:right;">' + pt('操作') + '</th>\
                            </tr></thead>\
                            <tbody>\
                            '+ list +'\
                            </tbody></table>\
                        </div>\
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px;">\
                            <div><button id="exportExcel" class="btn btn-default btn-sm" style="margin-left:5px;">' + pt('导出excel') + '</button></div>\
                            <div id="wsPage" class="dataTables_paginate paging_bootstrap page" style="margin:0;"></div>\
                        </div>';
        $('#ws_table').html(table);
        $('#wsPage').html(rdata.data.page);
    });
}

function f2bIpDetails(ip) {
    var loadT = layer.msg(pt('正在获取详情...'), { icon: 16, time: 0, shade: 0.3 });
    api.post('get_ip_logs', '', {ip: ip}, function(data){
        layer.close(loadT);
        var rdata = JSON.parse(data.data);
        if(!rdata.status) {
            layer.msg(f2bMsg(rdata.msg), {icon: 2});
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
                    actionStr = '<span style="color:#d9534f;"><i class="glyphicon glyphicon-ban-circle"></i> ' + pt('服务重启后继续封禁 (Restore Ban)') + '</span>';
                } else if (line.indexOf(' Unban ') > -1) {
                    actionStr = '<span style="color:#5cb85c;"><i class="glyphicon glyphicon-ok-circle"></i> ' + pt('解除封禁 (Unban)') + '</span>';
                } else if (line.indexOf(' Ban ') > -1) {
                    actionStr = '<span style="color:#d9534f;"><i class="glyphicon glyphicon-ban-circle"></i> ' + pt('封禁 (Ban)') + '</span>';
                } else if (line.indexOf(' Found ') > -1) {
                    actionStr = '<span style="color:#f0ad4e;"><i class="glyphicon glyphicon-warning-sign"></i> ' + pt('发现攻击 (Found)') + '</span>';
                } else {
                    var actMatch = line.match(/\]:\s+\w+\s+\[[^\]]+\]\s+(.*)$/);
                    if(actMatch) {
                        actionStr = $('<div>').text(actMatch[1].replace(new RegExp(ip, 'g'), '').trim()).html();
                    } else {
                        actionStr = '<span style="color:#999;" title="' + $('<div>').text(line).html() + '">' + pt('未知动作') + '</span>'; // 容错处理
                    }
                }
                
                tbodyHtml += '<tr>\
                    <td style="font-family: Consolas, monospace; font-size: 12.5px;">' + timeStr + '</td>\
                    <td>' + $('<div>').text(f2bJailLabel(jailStr)).html() + '</td>\
                    <td>' + actionStr + '</td>\
                </tr>';
            }
        } else {
            tbodyHtml = '<tr><td colspan="3" style="text-align:center;">' + pt('暂无详细记录') + '</td></tr>';
        }
        
        var content = '<div class="pd15">\
                        <div style="display: flex; justify-content: space-between; align-items: center; background: #f4f6f8; padding: 10px 15px; border-radius: 4px; border: 1px solid #e2e2e2; margin-bottom: 15px;">\
                            <div style="font-size: 13px;"><b>' + pt('防护目标IP：') + '</b><span style="font-family: Consolas, monospace; color:#333; margin-left: 5px;">' + $('<div>').text(ip).html() + '</span></div>\
                            <div style="font-size: 13px;"><b>' + pt('历史封禁次数：') + '</b><span style="color:#d9534f; font-weight:bold; font-size:15px; margin: 0 5px;">' + ban_count + '</span>' + pt('次') + '</div>\
                        </div>\
                        <div class="divtable">\
                            <div style="max-height: 380px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px;">\
                                <table class="table table-hover" style="margin:0; border:none;">\
                                    <thead style="position: sticky; top: 0; background: #f2f2f2; z-index: 1;">\
                                        <tr>\
                                            <th width="35%" style="border-bottom: 1px solid #ddd;">' + pt('时间') + '</th>\
                                            <th width="35%" style="border-bottom: 1px solid #ddd;">' + pt('触发规则') + '</th>\
                                            <th width="30%" style="border-bottom: 1px solid #ddd;">' + pt('执行动作') + '</th>\
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
            title: msgTpl(pt('【{1}】 触发详情'), [$('<div>').text(ip).html()]),
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
                        <span style="margin-left:10px">' + pt('时间:') + ' </span>\
                        <div class="input-group" style="margin-left:10px;width:350px;display: inline-table;vertical-align: top;">\
                            <div id="search_time" class="input-group-btn btn-group-sm">\
                                <button data-name="today" type="button" class="btn btn-default cur">' + pt('今日') + '</button>\
                                <button data-name="yesterday" type="button" class="btn btn-default">' + pt('昨日') + '</button>\
                                <button data-name="l7" type="button" class="btn btn-default">' + pt('近7天') + '</button>\
                                <button data-name="l30" type="button" class="btn btn-default">' + pt('近30天') + '</button>\
                            </div>\
                            <span class="last-span"><input data-name="" type="text" id="time_choose" lay-key="1000001_'+randstr+'" class="form-control btn-group-sm" autocomplete="off" placeholder="' + pt('自定义时间') + '" style="display: inline-block;font-size: 12px;padding: 0 10px;height:30px;width: 155px;"></span>\
                        </div>\
                    </div>\
                    <div>\
                        <button id="refreshLogs" class="btn btn-default btn-sm" style="padding-left: 5px;padding-right: 5px; margin-left: 5px;">' + pt('刷新') + '</button>\
                    </div>\
                </div>\
                <div class="divtable mtb10" id="ws_table"></div>\
            </div>';
    $(".soft-man-con").html(html);
    
    $(".soft-man-con").off("click", "#exportExcel").on("click", "#exportExcel", function(){
        var args = {};
        args['page'] = 1;
        // 服务端单次返回上限为 20000 条，避免大日志把内存与响应体打爆
        args['page_size'] = 20000;
        var query_date = 'today';
        if ($('#time_choose').attr("data-name") != '' && $('#time_choose').attr("data-name") != undefined){
            query_date = $('#time_choose').attr("data-name");
        } else {
            query_date = $('#search_time button.cur').attr("data-name");
        }
        args['query_date'] = query_date;
        args['tojs'] = 'f2bLogRequest';

        var loadT = layer.msg(pt('正在导出，请稍候...'), { icon: 16, time: 0, shade: [0.3, '#000'] });
        api.post('get_logs_list', '', args, function(rdata){
            layer.close(loadT);
            var rdata = typeof rdata.data === "string" ? JSON.parse(rdata.data) : rdata.data;
            var data = rdata.data.data;
            if(!data || data.length == 0) {
                layer.msg(pt("没有数据可导出"), {icon: 2});
                return;
            }
            var csv = "\uFEFF" + pt('时间') + ",IP," + pt('规则名') + "," + pt('原因') + "\n";
            for(var i=0; i<data.length; i++) {
                var d = data[i];
                var reason = f2bReasonText(d).replace(/"/g, '""');
                csv += getLocalTime(d.time) + "," + d.ip + "," + d.rule_name + ',"' + reason + '"\n';
            }
            var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = pt('防护历史.csv');
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);

            // 命中服务端上限时明确告知，避免用户误以为导出完整
            if (data.length >= args['page_size']) {
                layer.msg(msgTpl(pt('导出已达到单次上限 {1} 条，请缩小时间范围后重试'), [data.length]), {icon: 0, time: 4000});
            }
        });
    });

    $("#refreshLogs").on('click', function(){
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
                var start = String(timeA[0]+'-'+timeA[1]+'-'+timeA[2]).trim()
                var end = String(timeA[3]+'-'+timeA[4]+'-'+timeA[5]).trim()
                var query_txt = toUnixTime(start + " 00:00:00") + "-"+ toUnixTime(end + " 00:00:00")

                $('#time_choose').attr("data-name",query_txt);
                $('#time_choose').addClass("cur");

                f2bLogRequest(1);
            },
        });
    }

    $('#search_time button').on('click', function(){
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