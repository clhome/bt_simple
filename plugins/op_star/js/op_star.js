// OP 高性能防火墙 (OpenStar) 前端核心交互
function osPost(method, args, callback){
    var loadT = layer.msg('正在获取最新规则...', { icon: 16, time: 0, shade: 0.3 });
    $.post('/plugins/run', {name:'op_star', func:method, args:JSON.stringify(args)}, function(data) {
        layer.close(loadT);
        if (!data.status){
            layer.msg(data.msg,{icon:0,time:2000,shade: [0.3, '#000']});
            return;
        }
        
        try {
            var inner = $.parseJSON(data.data);
            if(inner && typeof inner.status !== 'undefined') {
                if(inner.status === false) {
                    layer.msg(inner.msg, {icon:0, time:2000, shade: [0.3, '#000']});
                    return;
                }
                data.data = typeof inner.data === 'string' ? inner.data : JSON.stringify(inner.data);
            }
        } catch(e) {}
        
        if(typeof(callback) == 'function'){
            callback(data);
        }
    },'json'); 
}

function osPostN(method, args, callback){
    $.post('/plugins/run', {name:'op_star', func:method, args:JSON.stringify(args)}, function(data) {
        if (!data.status){
            layer.msg(data.msg,{icon:0,time:2000,shade: [0.3, '#000']});
            return;
        }
        
        try {
            var inner = $.parseJSON(data.data);
            if(inner && typeof inner.status !== 'undefined') {
                if(inner.status === false) {
                    layer.msg(inner.msg, {icon:0, time:2000, shade: [0.3, '#000']});
                    return;
                }
                data.data = typeof inner.data === 'string' ? inner.data : JSON.stringify(inner.data);
            }
        } catch(e) {}
        
        if(typeof(callback) == 'function'){
            callback(data);
        }
    },'json'); 
}

// ---------------- 服务管理 ----------------
function pluginService(name){
    osPost('status', {}, function(data){
        var status_html = '';
        if(data.data == 'start'){
            status_html = '<span style="color:#20a53a;font-weight:bold;"><span class="glyphicon glyphicon-play"></span> 正在运行</span>';
        } else {
            status_html = '<span style="color:#fc6d26;font-weight:bold;"><span class="glyphicon glyphicon-pause"></span> 已停止</span>';
        }
        
        var con = '<div class="card-box">\
            <p style="font-size:16px;margin-bottom:15px;font-weight:bold;color:#333;">OP高性能防火墙 (OpenStar) 服务状态</p>\
            <div style="margin-bottom:15px;">当前状态: ' + status_html + '</div>\
            <div class="rule_btn">\
                <button class="btn btn-success btn-sm" onclick="toggleService(\'start\')">启动服务</button>\
                <button class="btn btn-danger btn-sm" onclick="toggleService(\'stop\')">停止服务</button>\
                <button class="btn btn-warning btn-sm" onclick="toggleService(\'reload\')">重载规则</button>\
            </div>\
            <div class="help-info-text" style="margin-top:20px;">\
                <li>启动服务后，OpenStar 防火墙会自动注入 OpenResty 引擎的全局生命周期中进行动态过滤。</li>\
                <li>若您修改了底层的配置文件，可以点击“重载规则”立即热更新配置，无需重启 Nginx 服务。</li>\
            </div>\
        </div>';
        
        $(".soft-man-con").html(con);
    });
}

function toggleService(act){
    var loadT = layer.msg('正在处理，请稍候...', { icon: 16, time: 0, shade: 0.3 });
    osPost(act, {}, function(data){
        layer.close(loadT);
        layer.msg('操作成功！',{icon:1,time:1500});
        setTimeout(function(){
            pluginService('op_star');
        }, 1000);
    });
}

// ---------------- 仪表盘 ----------------
function wafDashboard(){
    var con = '<div class="screen">\
        <div class="line">\
            <span class="name">安全防护状态</span>\
            <span class="val" style="color:#a8ffb2;">防御中</span>\
        </div>\
        <div class="line">\
            <span class="name">网络CC拦截</span>\
            <span class="val" id="cc_blocked_cnt">0</span>\
        </div>\
        <div class="line">\
            <span class="name">今日阻断总数</span>\
            <span class="val" id="today_blocked_cnt">0</span>\
        </div>\
        <div class="line">\
            <span class="name">累计防护请求</span>\
            <span class="val" id="total_protect_cnt">0</span>\
        </div>\
    </div>';
    
    con += '<div class="card-box" style="margin-top:20px;">\
        <p style="font-size:15px;font-weight:bold;margin-bottom:15px;color:#333;">WAF 防御运行概要</p>\
        <table class="table table-hover">\
            <thead>\
                <tr>\
                    <th>引擎内核</th>\
                    <th>版本</th>\
                    <th>防御类型</th>\
                    <th>开源作者</th>\
                </tr>\
            </thead>\
            <tbody>\
                <tr>\
                    <td>OpenStar (基于 OpenResty)</td>\
                    <td>最新分支</td>\
                    <td>SQL注入/XSS/恶意扫描/CC攻击/恶意Cookie/POST攻击</td>\
                    <td>starjun</td>\
                </tr>\
            </tbody>\
        </table>\
    </div>';
    
    $(".soft-man-con").html(con);
    
    // 从日志API中加载真实的拦截数据
    osPostN('get_logs', {}, function(data){
        var logs = [];
        try {
            logs = $.parseJSON(data.data);
        } catch(e) {
            logs = [];
        }
        
        if(logs && logs.length > 0){
            var ccCnt = 0;
            for(var i=0; i<logs.length; i++){
                if(logs[i].rule == 'network_Mod') ccCnt++;
            }
            $("#cc_blocked_cnt").text(ccCnt);
            $("#today_blocked_cnt").text(logs.length);
            $("#total_protect_cnt").text(logs.length);
        } else {
            // 新安装或无阻断日志时，恪守事实优先原则，展现真实的 0 次拦截
            $("#cc_blocked_cnt").text(0);
            $("#today_blocked_cnt").text(0);
            $("#total_protect_cnt").text(0);
        }
    });
}

// ---------------- 防护全局开关 ----------------
function wafGlobalConfig(){
    osPost('get_rule', {rule_name: 'base'}, function(data){
        var config = $.parseJSON(data.data);
        
        var con = '<div class="card-box">\
            <p style="font-size:15px;font-weight:bold;margin-bottom:15px;color:#333;">OpenStar 安全防御模块总控开关</p>\
            <table class="table table-hover">\
                <thead>\
                    <tr>\
                        <th>安全防御模块</th>\
                        <th>说明</th>\
                        <th class="text-right">模块开关</th>\
                    </tr>\
                </thead>\
                <tbody id="global_switch_body"></tbody>\
            </table>\
        </div>';
        
        $(".soft-man-con").html(con);
        
        var tbody = '';
        var modules = {
            "allow": ["全局白名单", "开启或关闭全局安全白名单过滤"],
            "ipMod": ["IP 黑白名单过滤", "基于客户端 IP / IP 网段的主动阻断或放行过滤"],
            "host_methodMod": ["域名及方法过滤", "限制未授权域名及非标准 HTTP 请求方法"],
            "uriMod": ["URI 资源防护", "拦截匹配特定恶意正则规则的请求 URI 路径"],
            "useragentMod": ["User-Agent 过滤", "阻断恶意爬虫、扫描器以及不合法浏览器的访问"],
            "cookieMod": ["恶意 Cookie 拦截", "检测并拦截通过 Cookie 进行的渗透或越权攻击行为"],
            "argsMod": ["URL 参数过滤 (GET)", "对 GET 请求传入的参数值进行敏感 SQL注入 与 XSS 检测"],
            "postMod": ["POST 报文过滤", "对表单或 JSON 提交的 POST 请求内容进行深层匹配与防御"],
            "networkMod": ["CC 流量与频次防护", "根据访问频率和频次阀值拦截暴力刷新与恶意攻击源IP"]
        };
        
        $.each(modules, function(key, val){
            var state = config[key] == 'on' ? 'checked' : '';
            tbody += '<tr>\
                <td><strong>' + val[0] + ' (' + key + ')</strong></td>\
                <td style="color:#666;">' + val[1] + '</td>\
                <td class="text-right">\
                    <input class="btswitch btswitch-ios" id="switch_' + key + '" type="checkbox" ' + state + '>\
                    <label class="btswitch-btn" style="width:2.2em;height:1.2em;margin-bottom: 0;display:inline-block;" for="switch_' + key + '" onclick="toggleGlobalModule(\'' + key + '\')"></label>\
                </td>\
            </tr>';
        });
        
        $("#global_switch_body").html(tbody);
    });
}

function toggleGlobalModule(key){
    osPostN('get_rule', {rule_name: 'base'}, function(data){
        var config = $.parseJSON(data.data);
        config[key] = config[key] == 'on' ? 'off' : 'on';
        
        osPost('save_rule', {rule_name: 'base', rule_data: JSON.stringify(config)}, function(res){
            layer.msg('配置成功且已热加载重载！',{icon:1,time:1000});
            wafGlobalConfig();
        });
    });
}

// ---------------- 拦截规则管理 ----------------
var currentRuleName = 'args_Mod';

function wafRulesConfig(ruleName){
    if(ruleName) currentRuleName = ruleName;
    
    var navs = {
        'args_Mod': 'GET 参数过滤',
        'cookie_Mod': 'Cookie 安全过滤',
        'useragent_Mod': 'User-Agent 过滤',
        'uri_Mod': 'URI 资源过滤',
        'post_Mod': 'POST 载荷过滤'
    };
    
    var nav_html = '<div style="margin-bottom:15px;" class="btn-group">';
    $.each(navs, function(k, v){
        var active_class = k == currentRuleName ? 'btn-success' : 'btn-default';
        nav_html += '<button type="button" class="btn btn-sm ' + active_class + '" onclick="wafRulesConfig(\'' + k + '\')">' + v + '</button>';
    });
    nav_html += '</div>';
    
    osPost('get_rule', {rule_name: currentRuleName}, function(data){
        var rules = [];
        try {
            rules = $.parseJSON(data.data);
        } catch(e) {
            rules = [];
        }
        
        var table_body = '';
        if(rules && rules.length > 0){
            for(var i=0; i<rules.length; i++){
                var rule = rules[i];
                var regex = '';
                if(typeof(rule.rule) == 'object'){
                    regex = rule.rule.join(' | ');
                } else {
                    regex = rule.rule;
                }
                
                var state_icon = rule.state == 'on' ? '<span style="color:#20a53a;font-weight:bold;">已启用</span>' : '<span style="color:#999;">已禁用</span>';
                var action_color = rule.action == 'deny' ? 'color:#fc6d26;font-weight:bold;' : 'color:#f0ad4e;font-weight:bold;';
                
                table_body += '<tr>\
                    <td><code>' + regex + '</code></td>\
                    <td>' + (rule.name || '默认内置防御规则') + '</td>\
                    <td><span style="' + action_color + '">' + rule.action.toUpperCase() + '</span></td>\
                    <td>' + state_icon + '</td>\
                    <td class="text-right">\
                        <a class="btlink" onclick="toggleRuleState(' + i + ')">切换状态</a> | \
                        <a class="btlink" onclick="deleteRule(' + i + ')">删除</a>\
                    </td>\
                </tr>';
            }
        } else {
            table_body = '<tr><td colspan="5" style="text-align:center;color:#999;">暂无规则数据</td></tr>';
        }
        
        var con = nav_html + '<div class="card-box">\
            <div style="margin-bottom:15px;height:30px;">\
                <span style="font-size:14px;font-weight:bold;color:#333;">【' + navs[currentRuleName] + '】安全匹配正则列表</span>\
                <button class="btn btn-success btn-xs va0 pull-right" onclick="addWafRuleDialog()">添加防护规则</button>\
            </div>\
            <div style="max-height:400px;overflow-y:auto;">\
                <table class="table table-hover">\
                    <thead>\
                        <tr>\
                            <th width="350">安全阻断匹配正则表达式 (Regex)</th>\
                            <th>规则描述</th>\
                            <th>执行动作</th>\
                            <th>启用状态</th>\
                            <th class="text-right">操作</th>\
                        </tr>\
                    </thead>\
                    <tbody>' + table_body + '</tbody>\
                </table>\
            </div>\
            <div class="help-info-text">\
                <li>请谨慎添加自定义正则表达式规则，非标准的正则匹配可能会引发 WAF 的误阻断导致业务异常。</li>\
                <li>点击“切换状态”可自由定义当前阻断规则在 OpenStar 中是否生效。</li>\
            </div>\
        </div>';
        
        $(".soft-man-con").html(con);
    });
}

function addWafRuleDialog(){
    layer.open({
        type: 1,
        title: "添加自定义防护阻断规则",
        area: '500px',
        closeBtn: 1,
        shadeClose: false,
        content: '<form class="bt-form pd20 pb70">\
                <div class="line">\
                    <span class="tname">正则表达式</span>\
                    <div class="info-r"><input class="bt-input-text" style="width:300px;" name="rule_regex" type="text" placeholder="例: \\bselect\\b.*\\bfrom\\b" /></div>\
                </div>\
                <div class="line">\
                    <span class="tname">阻断动作</span>\
                    <div class="info-r">\
                        <select class="bt-input-text" style="width:200px" name="rule_action">\
                            <option value="deny">DENY (阻断并返回403)</option>\
                            <option value="log">LOG (仅记录审计日志不拦截)</option>\
                        </select>\
                    </div>\
                </div>\
                <div class="line">\
                    <span class="tname">规则描述</span>\
                    <div class="info-r"><input class="bt-input-text" style="width:300px;" name="rule_desc" type="text" placeholder="例: 防御常规SQL注入读取" /></div>\
                </div>\
                <div class="bt-form-submit-btn">\
                    <button type="button" class="btn btn-success btn-sm" onclick="saveWafRule()">保存并应用</button>\
                </div>\
            </form>'
    });
}

function saveWafRule(){
    var regex = $("input[name='rule_regex']").val().trim();
    var action = $("select[name='rule_action']").val();
    var desc = $("input[name='rule_desc']").val().trim();
    
    if(!regex){
        layer.msg('请输入正则表达式！');
        return;
    }
    
    osPostN('get_rule', {rule_name: currentRuleName}, function(data){
        var rules = [];
        try {
            rules = $.parseJSON(data.data);
        } catch(e) {
            rules = [];
        }
        
        var new_rule = {
            "state": "on",
            "action": action,
            "rule": [regex, "j"],
            "name": desc || "用户自定义防护规则"
        };
        
        rules.push(new_rule);
        
        osPost('save_rule', {rule_name: currentRuleName, rule_data: JSON.stringify(rules)}, function(res){
            layer.closeAll();
            layer.msg('新增规则保存并成功热重载！',{icon:1,time:1500});
            wafRulesConfig();
        });
    });
}

function toggleRuleState(index){
    osPostN('get_rule', {rule_name: currentRuleName}, function(data){
        var rules = $.parseJSON(data.data);
        rules[index].state = rules[index].state == 'on' ? 'off' : 'on';
        
        osPost('save_rule', {rule_name: currentRuleName, rule_data: JSON.stringify(rules)}, function(res){
            layer.msg('规则状态已更新且重载！',{icon:1,time:1000});
            wafRulesConfig();
        });
    });
}

function deleteRule(index){
    safeMessage('删除规则', '您确认要删除这条匹配正则规则吗？', function(){
        osPostN('get_rule', {rule_name: currentRuleName}, function(data){
            var rules = $.parseJSON(data.data);
            rules.splice(index, 1);
            
            osPost('save_rule', {rule_name: currentRuleName, rule_data: JSON.stringify(rules)}, function(res){
                layer.msg('规则已彻底删除！',{icon:1,time:1500});
                wafRulesConfig();
            });
        });
    });
}

// ---------------- IP 黑白名单 ----------------
function wafIpList(){
    osPost('get_rule', {rule_name: 'ip_Mod'}, function(data){
        var rules = [];
        try {
            rules = $.parseJSON(data.data);
        } catch(e) {
            rules = [];
        }
        
        var table_body = '';
        if(rules && rules.length > 0){
            for(var i=0; i<rules.length; i++){
                var rule = rules[i];
                var type_color = rule[1] == 'allow' ? 'color:#20a53a;font-weight:bold;' : 'color:#fc6d26;font-weight:bold;';
                
                table_body += '<tr>\
                    <td><code>' + rule[0] + '</code></td>\
                    <td><span style="' + type_color + '">' + (rule[1] == 'allow' ? '放行 (白名单)' : '封锁 (黑名单)') + '</span></td>\
                    <td>' + (rule[2] || '主动机房防护') + '</td>\
                    <td class="text-right"><a class="btlink" onclick="deleteIpRule(' + i + ')">移除</a></td>\
                </tr>';
            }
        } else {
            table_body = '<tr><td colspan="4" style="text-align:center;color:#999;">暂无 IP 黑白名单记录</td></tr>';
        }
        
        var con = '<div class="card-box">\
            <div style="border-bottom:#eee 1px solid;margin-bottom:15px;padding-bottom:15px">\
                <span style="font-size:14px;font-weight:bold;color:#333;margin-right:15px;">主动 IP 策略管理</span>\
                <input class="bt-input-text" id="add_ip_address" type="text" style="width:220px;margin-right:10px;" placeholder="IP或网段,例: 1.1.1.1 或 1.1.1.0/24" />\
                <select class="bt-input-text" id="add_ip_action" style="width:140px;margin-right:10px;">\
                    <option value="deny">DENY (加入黑名单)</option>\
                    <option value="allow">ALLOW (加入白名单)</option>\
                </select>\
                <input class="bt-input-text" id="add_ip_desc" type="text" style="width:180px;margin-right:15px;" placeholder="描述" />\
                <button class="btn btn-success btn-sm va0" onclick="addIpRule()">添加策略</button>\
            </div>\
            <div style="max-height:350px;overflow-y:auto;">\
                <table class="table table-hover">\
                    <thead>\
                        <tr>\
                            <th>受控 IP 地址 / CIDR 网段</th>\
                            <th>策略动作</th>\
                            <th>策略说明</th>\
                            <th class="text-right">操作</th>\
                        </tr>\
                    </thead>\
                    <tbody>' + table_body + '</tbody>\
                </table>\
            </div>\
            <div class="help-info-text">\
                <li><b>白名单 (ALLOW)</b>：加入白名单的 IP 访问网站时，将跳过 WAF 的所有正则和安全规则检测，拥有最高通行权。</li>\
                <li><b>黑名单 (DENY)</b>：加入黑名单的 IP 只要请求站点，WAF 会直接拦截并切断连接，完美应对恶意脚本和代理源。</li>\
            </div>\
        </div>';
        
        $(".soft-man-con").html(con);
    });
}

function addIpRule(){
    var ip = $("#add_ip_address").val().trim();
    var action = $("#add_ip_action").val();
    var desc = $("#add_ip_desc").val().trim();
    
    if(!ip){
        layer.msg('请输入受控 IP 地址或 CIDR 网段！');
        return;
    }
    
    osPostN('get_rule', {rule_name: 'ip_Mod'}, function(data){
        var rules = [];
        try {
            rules = $.parseJSON(data.data);
        } catch(e) {
            rules = [];
        }
        
        // OpenStar IP 规则是包含 [IP, 动作, 描述] 的嵌套数组
        var new_rule = [ip, action, desc || "管理员主动设置"];
        rules.push(new_rule);
        
        osPost('save_rule', {rule_name: 'ip_Mod', rule_data: JSON.stringify(rules)}, function(res){
            layer.msg('IP 策略添加成功并已加载应用！',{icon:1,time:1500});
            wafIpList();
        });
    });
}

function deleteIpRule(index){
    safeMessage('移除策略', '您确认要彻底删除该 IP 的防护策略吗？', function(){
        osPostN('get_rule', {rule_name: 'ip_Mod'}, function(data){
            var rules = $.parseJSON(data.data);
            rules.splice(index, 1);
            
            osPost('save_rule', {rule_name: 'ip_Mod', rule_data: JSON.stringify(rules)}, function(res){
                layer.msg('策略成功移除！',{icon:1,time:1500});
                wafIpList();
            });
        });
    });
}

// ---------------- 封锁历史 ----------------
function wafBlockedHistory(){
    osPost('get_logs', {}, function(data){
        var logs = [];
        try {
            logs = $.parseJSON(data.data);
        } catch(e) {
            logs = [];
        }
        
        var table_body = '';
        if(logs && logs.length > 0){
            // 日志倒序排列展示最新封锁
            for(var i = logs.length - 1; i >= 0; i--){
                var log = logs[i];
                var date_str = log.time ? new Date(log.time * 1000).toLocaleString() : '最近';
                
                table_body += '<tr>\
                    <td>' + date_str + '</td>\
                    <td><code>' + (log.ip || '未知来源') + '</code></td>\
                    <td>' + (log.host || '通用监听') + '</td>\
                    <td><span class="overflow_hide" style="max-width:180px;">' + (log.uri || '/') + '</span></td>\
                    <td><span class="label label-danger">' + (log.rule || 'WAF阻断') + '</span></td>\
                    <td><span style="color:#fc6d26;font-weight:bold;">BLOCKED</span></td>\
                </tr>';
            }
        } else {
            // 恪守事实优先，无真实攻击日志时，直接展示暂无数据提示
            table_body = '<tr><td colspan="6" style="text-align:center;color:#999;">暂无 WAF 拦截封锁历史记录</td></tr>';
        }
        
        var con = '<div class="card-box">\
            <p style="font-size:15px;font-weight:bold;margin-bottom:15px;color:#333;">OpenStar 安全防御审计日志</p>\
            <div style="max-height:400px;overflow-y:auto;">\
                <table class="table table-hover">\
                    <thead>\
                        <tr>\
                            <th>拦截发生时间</th>\
                            <th>客户端攻击源 IP</th>\
                            <th>攻击目标域名</th>\
                            <th>请求路径 (URI)</th>\
                            <th>触发安全规则模块</th>\
                            <th>防护动作</th>\
                        </tr>\
                    </thead>\
                    <tbody>' + table_body + '</tbody>\
                </table>\
            </div>\
            <div class="help-info-text">\
                <li>此处显示的是最近 100 条触发 WAF 正则拦截或 CC 防御阻断的真实审计日志。</li>\
                <li>如果发现有正常用户 IP 被误杀，可以复制其 IP 前往“黑白名单”中一键加入白名单放行。</li>\
            </div>\
        </div>';
        
        $(".soft-man-con").html(con);
    });
}

function time() {
    return Math.floor(new Date().getTime() / 1000);
}

// ---------------- 安全模板管理 ----------------
function wafTemplates(){
    osPost('get_templates', {}, function(data){
        var templates = [];
        try {
            templates = $.parseJSON(data.data);
        } catch(e) {
            templates = [];
        }
        
        var tpl_html = '';
        if(templates && templates.length > 0){
            for(var i=0; i<templates.length; i++){
                var tpl = templates[i];
                var modules_str = '';
                if(tpl.modules && tpl.modules.length > 0){
                    for(var j=0; j<tpl.modules.length; j++){
                        modules_str += '<span class="label label-info" style="margin-right:5px;margin-bottom:3px;display:inline-block;">' + tpl.modules[j] + '</span>';
                    }
                }
                
                var icon_class = 'glyphicon-shield';
                var card_border = '#20a53a';
                if(tpl.id == 'cc_defense'){
                    icon_class = 'glyphicon-flash';
                    card_border = '#f0ad4e';
                } else if(tpl.id == 'strict_mode'){
                    icon_class = 'glyphicon-lock';
                    card_border = '#fc6d26';
                }
                
                tpl_html += '<div class="card-box" style="border-left:4px solid ' + card_border + ';">\
                    <div style="margin-bottom:10px;">\
                        <span class="glyphicon ' + icon_class + '" style="color:' + card_border + ';font-size:18px;margin-right:8px;"></span>\
                        <strong style="font-size:15px;color:#333;">' + tpl.name + '</strong>\
                    </div>\
                    <p style="color:#666;font-size:13px;margin-bottom:10px;">' + tpl.desc + '</p>\
                    <div style="margin-bottom:12px;">' + modules_str + '</div>\
                    <button class="btn btn-success btn-sm" onclick="applyTemplate(\'' + tpl.id + '\', \'' + tpl.name + '\')">一键应用此模板</button>\
                </div>';
            }
        } else {
            tpl_html = '<div class="card-box" style="text-align:center;color:#999;">暂无可用的安全防护模板</div>';
        }
        
        var con = '<div class="card-box" style="background:#f8f9fa;border:none;">\
            <p style="font-size:16px;font-weight:bold;margin-bottom:8px;color:#333;">安全防护模板中心</p>\
            <p style="color:#666;font-size:13px;margin-bottom:0;">选择一个适合您站点的安全防护模板，一键应用即可获得完整的基础防护能力。</p>\
        </div>' + tpl_html + '\
        <div class="help-info-text">\
            <li>应用模板会<b>覆盖</b>对应模块的现有规则配置，请在应用前确认。</li>\
            <li>模板中未涉及的模块（如 IP 黑白名单）不受影响，您的手动配置会保留。</li>\
            <li>应用后可在"防护开关"和"拦截规则"标签页中查看和微调具体规则。</li>\
        </div>';
        
        $(".soft-man-con").html(con);
    });
}

function applyTemplate(tpl_id, tpl_name){
    safeMessage('应用安全模板', '确认要应用安全模板【' + tpl_name + '】吗？<br><br><span style="color:#fc6d26;">注意：应用模板将覆盖对应模块的现有规则配置！</span>', function(){
        osPost('apply_template', {tpl_id: tpl_id}, function(data){
            layer.msg('模板应用成功！', {icon: 1, time: 2000});
            setTimeout(function(){
                wafTemplates();
            }, 1000);
        });
    });
}
