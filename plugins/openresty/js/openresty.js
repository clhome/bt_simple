var api = YfPlugin.createApi('openresty');
var pt = YfI18n.createPluginTranslator('openresty');


function orPluginService(_name, version){
    var data = {name:_name, func:'status'}
    if ( typeof(version) != 'undefined' ){
        data['version'] = version;
    } else {
        version = '';
    }

    api.post('status', data, function(data){
        if (data.data == 'start'){
            orPluginSetService(_name, true, version);
        } else {
            orPluginSetService(_name, false, version);
        }
    });
}

function orPluginSetService(_name ,status, version){
    var serviceCon ='<p class="status">' + pt('当前状态：') + '<span>'+(status ? pt('开启') : pt('关闭') )+
        '</span><span style="color: '+
        (status?'#20a53a;':'red;')+
        ' margin-left: 3px;" class="glyphicon ' + (status?'glyphicon glyphicon-play':'glyphicon-pause')+'"></span></p><div class="sfm-opt">\
            <button class="btn btn-default btn-sm" onclick="orPluginOpService(\''+_name+'\',\''+(status?'stop':'start')+'\',\''+version+'\')">'+(status?pt('停止'):pt('启动'))+'</button>\
            <button class="btn btn-default btn-sm" onclick="orPluginOpService(\''+_name+'\',\'restart\',\''+version+'\',\'yes\')">'+pt('重启')+'</button>\
            <button class="btn btn-default btn-sm" onclick="orPluginOpService(\''+_name+'\',\'reload\',\''+version+'\')">'+pt('还原默认配置')+'</button>\
        </div>' + (typeof pluginInitDSwitchHtml === 'function' ? pluginInitDSwitchHtml(_name, version) : '')
        + orPluginCronCardHtml(_name); 
    $(".soft-man-con").html(serviceCon);
    if (typeof pluginInitDSwitchRender === 'function') {
        pluginInitDSwitchRender(_name, version);
    }
    orPluginRefreshCronStatus(_name);
}


function orPluginOpService(a, b, v,request_callback) {

    var c = "name=" + a + "&func=" + b;
    if(v != ''){
        c = c + '&version='+v;
    }

    var d = "";

    switch(b) {
        case "stop":d = pt('停止');break;
        case "start":d = pt('启动');break;
        case "restart":d = pt('重启');break;
        case "reload":d = pt('重载');break;
    }
    layer.confirm( msgTpl(pt('您真的要{1}{2}{3}服务吗？'), [d,a,v]), {icon:3,closeBtn: 2}, function() {
        api.post('get_os',{},function(data){
            var rdata = JSON.parse(data.data);
            if (!rdata['auth']){
                layer.prompt({title: pt('检查到权限不足,需要输入密码!'), formType: 1},function(pwd, index){
                
                    layer.close(index);
                    var data = {'pwd':pwd};
                    c += '&args='+JSON.stringify(data);
                    orPluginOpServiceOp(a,b,c,d,a,v,request_callback);
                });
            } else {
                orPluginOpServiceOp(a,b,c,d,a,v,request_callback);

            }
        });
    })
}

function orPluginOpServiceOp(a,b,c,d,_a,v,request_callback){

    var request_path = "/plugins/run";
    if (request_callback == 'yes'){
        request_path = "/plugins/callback";
    }

    var e = layer.msg(msgTpl(pt('正在{1}{2}{3}服务,请稍候...'),[d,a,v]), {icon: 16,time: 0});
    $.post(request_path, c, function(g) {
        layer.close(e);
        
        var f = g.data == 'ok' ? msgTpl(pt('{1}{2}服务已{3}'),[a,v,d]) : msgTpl(pt('{1}{2}服务{3}失败!'),[a,v,d]);
        layer.msg(f, {icon: g.data == 'ok' ? 1 : 2});
        
        if( b != "reload" && g.data == 'ok' ) {
            if ( b == 'start' ) {
                orPluginSetService(a, true, v);
            } else if ( b == 'stop' ){
                orPluginSetService(a, false, v);
            }
        }

        // 即时联动更新外部状态（0ms乐观对齐 + 异步复查）
        if (g.data == 'ok' && typeof window.refreshExternalPluginStatus === 'function') {
            var targetStatus = (b == 'start' || b == 'restart') ? true : (b == 'stop' ? false : null);
            window.refreshExternalPluginStatus(a, targetStatus);
        }

        if( g.status && g.data != 'ok' ) {
            layer.msg(g.data, {icon: 2,time: 10000,shade: 0.3});
        }

    },'json').fail(function() {
        layer.close(e);
        layer.msg(pt('操作异常!'), {icon: 2});
    });
}


//查看Nginx负载状态
function getOpStatus() {
    var loadT = layer.msg(pt('正在处理，请稍后...'), { icon: 16, time: 0, shade: 0.3 });
    $.post('/plugins/run', {name:'openresty', func:'run_info'}, function(data) {
        layer.close(loadT); 
        try {
            var rdata = JSON.parse(data.data);
            if ('status' in rdata && !rdata.status){
                showMsg(rdata.msg, function(){}, null,3000);
                return;
            }

            var con = "<div><table class='table table-hover table-bordered'>\
                            <tr><th>" + pt('活动连接(Active connections)') + "</th><td>" + rdata.active + "</td></tr>\
                            <tr><th>" + pt('总连接次数(accepts)') + "</th><td>" + rdata.accepts + "</td></tr>\
                            <tr><th>" + pt('总握手次数(handled)') + "</th><td>" + rdata.handled + "</td></tr>\
                            <tr><th>" + pt('总请求数(requests)') + "</th><td>" + rdata.requests + "</td></tr>\
                            <tr><th>" + pt('请求数(Reading)') + "</th><td>" + rdata.Reading + "</td></tr>\
                            <tr><th>" + pt('响应数(Writing)') + "</th><td>" + rdata.Writing + "</td></tr>\
                            <tr><th>" + pt('驻留进程(Waiting)') + "</th><td>" + rdata.Waiting + "</td></tr>\
                         </table></div>";
            $(".soft-man-con").html(con);
        }catch(err){
             showMsg(data.data, function(){}, null,3000);
        }
    },'json').fail(function() {
        // 缺 .fail() 时请求 500/超时会让 loading 遮罩永久卡死（层叠遮罩无法关闭）。
        layer.close(loadT);
        layer.msg(pt('操作异常!'), {icon: 2});
    });
}


function setOpCfg(){
    api.post('get_cfg', {}, function(data){
        var rdata = JSON.parse(data.data);
        // get_cfg 的业务失败（如 openresty 未安装 / 配置文件不存在）也是 HTTP 200 + 内层
        // status:false，必须在这里拦掉：否则 rdata.data 为 undefined，下面的 rdata.length
        // 直接抛异常，界面既无提示也无内容（静默失败）。
        if ('status' in rdata && !rdata.status) {
            showMsg(rdata.msg, function(){}, null, 3000);
            return;
        }
        rdata = rdata.data;
        // console.log(rdata);

        var mlist = '';
        for (var i = 0; i < rdata.length; i++) {
            var w = '70'
            var ibody = '<input style="width: ' + w + 'px;" class="bt-input-text mr5" name="' + rdata[i].name + '" value="' + rdata[i].value + '" type="text" >';
            switch (rdata[i].type) {
                case 0:
                    var selected_1 = (rdata[i].value == 1) ? 'selected' : '';
                    var selected_0 = (rdata[i].value == 0) ? 'selected' : '';
                    ibody = '<select class="bt-input-text mr5" name="' + rdata[i].name + '" style="width: ' + w + 'px;">\
                        <option value="1" ' + selected_1 + '>' + pt('开启') + '</option>\
                        <option value="0" ' + selected_0 + '>' + pt('关闭') + '</option>\
                    </select>';
                    break;
                case 1:
                    var selected_1 = (rdata[i].value == 'on') ? 'selected' : '';
                    var selected_0 = (rdata[i].value == 'off') ? 'selected' : '';
                    ibody = '<select class="bt-input-text mr5" name="' + rdata[i].name + '" style="width: ' + w + 'px;">\
                        <option value="on" ' + selected_1 + '>' + pt('开启') + '</option>\
                        <option value="off" ' + selected_0 + '>' + pt('关闭') + '</option>\
                    </select>';
                    break;
            }
            mlist += '<p style="margin-top:15px;"><span>' + rdata[i].name + '</span>' + ibody + "<b class='unit c9'>"+rdata[i].unit+"</b>" +', <font class="c9">' + pt(rdata[i].ps) + '</font></p>';
        }
        var con = '<style>.conf_p p{margin-bottom: 2px}</style><div class="conf_p" style="margin-bottom:0">\
                        ' + mlist + '\
                        <div style="margin-top:10px; padding-right:15px" class="text-right">\
                            <button class="btn btn-default btn-sm mr5" style="color: #d9534f; border-color: #d9534f;" onclick="restoreDefault()">' + pt('还原默认') + '</button>\
                            <button class="btn btn-success btn-sm mr5" onclick="setOpCfg()">' + pt('刷新') + '</button>\
                            <button class="btn btn-success btn-sm" onclick="submitConf()">' + pt('保存') + '</button>\
                        </div>\
                    </div>'
        $(".soft-man-con").html(con);
    });
}

function restoreDefault() {
    layer.confirm(pt('您确定要将配置还原为默认调优配置吗？这会覆盖您当前的自定义调整并重载服务。'), {icon:3,closeBtn: 2}, function() {
        api.post('get_os',{},function(data){
            var rdata = JSON.parse(data.data);
            var c = "name=openresty&func=reload";
            if (!rdata['auth']){
                layer.prompt({title: pt('检查到权限不足,需要输入密码!'), formType: 1},function(pwd, index){
                    layer.close(index);
                    var data = {'pwd':pwd};
                    c += '&args='+JSON.stringify(data);
                    restoreDefaultOp(c);
                });
            } else {
                restoreDefaultOp(c);
            }
        });
    });
}

function restoreDefaultOp(c) {
    var e = layer.msg(pt('正在还原默认配置,请稍候...'), {icon: 16,time: 0});
    $.post('/plugins/run', c, function(g) {
        layer.close(e);
        if (g.data == 'ok') {
            layer.msg(pt('还原默认配置成功！'), {icon: 1});
            setOpCfg();
            if (typeof window.refreshExternalPluginStatus === 'function') {
                window.refreshExternalPluginStatus('openresty');
            }
        } else {
            layer.msg(pt('还原默认配置失败！'), {icon: 2});
            if( g.status && g.data != 'ok' ) {
                layer.msg(g.data, {icon: 2,time: 10000,shade: 0.3});
            }
        }
    },'json').fail(function() {
        layer.close(e);
        layer.msg(pt('操作异常!'), {icon: 2});
    });
}

function submitConf() {
    var data = {
        worker_processes: $("input[name='worker_processes']").val(),
        worker_connections: $("input[name='worker_connections']").val(),
        keepalive_timeout: $("input[name='keepalive_timeout']").val(),
        zstd: $("select[name='zstd']").val() || 'on',
        brotli: $("select[name='brotli']").val() || 'on',
        gzip: $("select[name='gzip']").val() || 'on',
        gzip_min_length: $("input[name='gzip_min_length']").val(),
        gzip_comp_level: $("input[name='gzip_comp_level']").val(),
        client_max_body_size: $("input[name='client_max_body_size']").val(),
        server_names_hash_bucket_size: $("input[name='server_names_hash_bucket_size']").val(),
        client_header_buffer_size: $("input[name='client_header_buffer_size']").val(),
    };

    // console.log(data);
    api.post('set_cfg', data, function(rdata){
        var rdata = typeof rdata.data === "string" ? JSON.parse(rdata.data) : rdata.data;
        // console.log(rdata);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
        if (rdata.status && typeof window.refreshExternalPluginStatus === 'function') {
            window.refreshExternalPluginStatus('openresty');
        }
    });
}

function orPluginCronCardHtml(_name) {
    _name = _name || 'openresty';
    var html = '<div class="openresty-cron-card" style="margin-top: 18px; padding: 15px 18px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">\
        <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #edf2f7; padding-bottom: 10px; margin-bottom: 10px;">\
            <div style="display: flex; align-items: center;">\
                <span class="glyphicon glyphicon-shield" style="font-size: 15px; color: #20a53a; margin-right: 8px;"></span>\
                <span style="font-size: 13px; font-weight: 600; color: #1e293b;">' + pt('服务守护（检查任务）') + '</span>\
            </div>\
            <span id="openresty_cron_badge" style="display: inline-flex; align-items: center; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; transition: all 0.2s ease;">\
                <span style="width: 6px; height: 6px; border-radius: 50%; background: #94a3b8; margin-right: 6px; display: inline-block;"></span>\
                <span class="badge-text">' + pt('获取中...') + '</span>\
            </span>\
        </div>\
        <div style="font-size: 12px; color: #475569; line-height: 1.6;">\
            <p style="margin-bottom: 5px;">' + pt('自动每 3 分钟巡检一次 OpenResty 服务状态。当检测到僵尸进程或服务异常宕机时，将自动清理异常残留并拉起服务，实现故障自愈。') + '</p>\
            <p style="margin-bottom: 0; color: #64748b;"><span class="glyphicon glyphicon-info-sign" style="color: #3b82f6; margin-right: 4px;"></span>' + pt('指引：生产环境推荐开启以保障网站高可用运行；如需停服维护或断点排查时可随时删除检查任务。') + '</p>\
        </div>\
        <div style="margin-top: 12px; display: flex; gap: 10px; align-items: center;">\
            <button id="openresty_cron_add_btn" class="btn btn-success btn-sm" onclick="cronAddCheck()"><span class="glyphicon glyphicon-plus-sign" style="margin-right: 4px;"></span>' + pt('添加检查任务') + '</button>\
            <button id="openresty_cron_del_btn" class="btn btn-default btn-sm" onclick="cronDelCheck()"><span class="glyphicon glyphicon-trash" style="margin-right: 4px;"></span>' + pt('删除检查任务') + '</button>\
        </div>\
    </div>';
    return html;
}

function orPluginRefreshCronStatus(_name) {
    _name = _name || 'openresty';
    api.post('cron_status', {}, function(data) {
        try {
            var rdata = typeof data.data === 'string' ? JSON.parse(data.data) : data.data;
            var isActive = false;
            if (rdata && rdata.data && rdata.data.is_active) {
                isActive = true;
            }
            var $badge = $('#openresty_cron_badge');
            var $addBtn = $('#openresty_cron_add_btn');
            var $delBtn = $('#openresty_cron_del_btn');

            if (isActive) {
                $badge.html('<span style="width: 6px; height: 6px; border-radius: 50%; background: #10b981; margin-right: 6px; display: inline-block;"></span><span class="badge-text">' + pt('已开启') + '</span>')
                      .css({
                          'background': '#ecfdf5',
                          'color': '#059669',
                          'border-color': '#a7f3d0'
                      });
                $addBtn.html('<span class="glyphicon glyphicon-refresh" style="margin-right: 4px;"></span>' + pt('重新同步检查任务'));
                $delBtn.prop('disabled', false).removeClass('disabled').css('opacity', '1');
            } else {
                $badge.html('<span style="width: 6px; height: 6px; border-radius: 50%; background: #94a3b8; margin-right: 6px; display: inline-block;"></span><span class="badge-text">' + pt('未开启') + '</span>')
                      .css({
                          'background': '#f1f5f9',
                          'color': '#64748b',
                          'border-color': '#e2e8f0'
                      });
                $addBtn.html('<span class="glyphicon glyphicon-plus-sign" style="margin-right: 4px;"></span>' + pt('添加检查任务'));
                $delBtn.prop('disabled', true).addClass('disabled').css('opacity', '0.6');
            }
        } catch (e) {}
    });
}

function cronAddCheck(){
    var loadT = layer.msg(pt('正在添加检查任务...'), { icon: 16, time: 0, shade: 0.3 });
    api.post('cron_add_check', {}, function(data){
        layer.close(loadT);
        var rdata = typeof data.data === 'string' ? JSON.parse(data.data) : data.data;
        var msg = rdata.msg || (rdata.status ? pt('添加检查任务成功') : pt('添加检查任务失败'));
        layer.msg(msg, { icon: rdata.status ? 1 : 2 });
        orPluginRefreshCronStatus('openresty');
    }).fail(function(){
        layer.close(loadT);
        layer.msg(pt('操作异常!'), { icon: 2 });
    });
}

function cronDelCheck(){
    layer.confirm(pt('确定要删除 OpenResty 守护检查任务吗？删除后将不再自动监控与拉起服务。'), {icon: 3, closeBtn: 2, title: pt('删除检查任务')}, function(index){
        layer.close(index);
        var loadT = layer.msg(pt('正在删除检查任务...'), { icon: 16, time: 0, shade: 0.3 });
        api.post('cron_del_check', {}, function(data){
            layer.close(loadT);
            var rdata = typeof data.data === 'string' ? JSON.parse(data.data) : data.data;
            var msg = rdata.msg || (rdata.status ? pt('删除检查任务成功') : pt('删除检查任务失败'));
            layer.msg(msg, { icon: rdata.status ? 1 : 2 });
            orPluginRefreshCronStatus('openresty');
        }).fail(function(){
            layer.close(loadT);
            layer.msg(pt('操作异常!'), { icon: 2 });
        });
    });
}

// ---------------------------------------------------------------------------
// 版本升级提示（服务页顶部黄条）
//
// 数据来自 /plugins/run?func=version_info（**不联网**：只读 data/openresty_release_index.json
// 缓存与内置表，联网刷新交给夜间「御风软件版本在线同步」）。版本号只作为文本渲染，
// 不拼进 innerHTML / 行内 onclick —— 上游页面解析结果属于外部输入，一律当不可信。
// ---------------------------------------------------------------------------
var orInstalledVersion = '';

function orHideVersionTip() {
    var $box = $('#orVerTip');
    if ($box.length) {
        $box.hide().empty();
    }
}

function orVersionCheck() {
    api.post('version_info', {}, function (res) {
        var d = null;
        try {
            d = typeof res.data === 'string' ? JSON.parse(res.data) : res.data;
        } catch (e) {
            d = null;
        }
        if (!d) {
            orHideVersionTip();
            return;
        }
        orInstalledVersion = d.installed || '';
        orRenderVersionTip(d);
    });
}

function orRenderVersionTip(d) {
    var $box = $('#orVerTip');
    if (!$box.length) return;
    if (!d || !d.needs_update || !d.latest) {
        orHideVersionTip();
        return;
    }

    $box.empty().show();

    var tipText = msgTpl(pt('发现新版本 {1}（发布于 {2}），当前版本 {3} 已落后，建议升级。'),
        [d.latest, d.release_date || '-', d.installed || '-']);
    $('<span>').text(tipText).appendTo($box);

    if (d.changelog) {
        $('<a>')
            .attr({ 'href': d.changelog, 'target': '_blank', 'rel': 'noopener noreferrer' })
            .css({ 'margin-left': '10px', 'color': '#b07800', 'text-decoration': 'underline' })
            .text(pt('更新日志'))
            .appendTo($box);
    }

    $('<button type="button" class="btn btn-warning btn-xs or-ver-upgrade">')
        .css({ 'margin-left': '12px' })
        .attr('data-ver', d.latest)
        .text(pt('立即升级'))
        .on('click', function () {
            orUpgradeVersion($(this).attr('data-ver'));
        })
        .appendTo($box);
}

function orUpgradeVersion(ver) {
    if (!ver) return;
    var msg = msgTpl(pt('确认将 OpenResty 从 {1} 升级到 {2} 吗？升级会重新编译并重启服务，期间网站短暂中断。'),
        [orInstalledVersion || '-', ver]);
    layer.confirm(msg, { icon: 3, closeBtn: 1, title: pt('升级确认') }, function (index) {
        layer.close(index);
        var loadT = layer.msg(pt('已提交升级任务，正在后台编译...'), { icon: 16, time: 0, shade: 0.3 });
        $.post('/plugins/install', { name: 'openresty', version: ver, upgrade: 1, type: 0 }, function (r) {
            layer.close(loadT);
            if (r && r.status) {
                orHideVersionTip();
                layer.msg(pt('升级任务已提交，可在消息盒子查看进度'), { icon: 1 });
                if (typeof getTaskCount === 'function') {
                    getTaskCount();
                }
                // 编译完成后自动收尾：隐藏黄条 + 刷新首页卡片/软件商店（不用等用户手动刷新）
                orWatchUpgradeDone(ver);
            } else {
                layer.msg((r && r.msg) || pt('提交升级任务失败'), { icon: 2 });
            }
        }, 'json').fail(function () {
            layer.close(loadT);
            layer.msg(pt('操作异常!'), { icon: 2 });
        });
    });
}

// ---------------------------------------------------------------------------
// 升级收尾联动
//
// 为什么需要：源码安装是后台任务（编译 10~30 分钟），任务结束后面板的已装版本
// 已经变了，但首页卡片/软件商店里的「新版本」角标来自服务端快照——不重新拉取就
// 会一直挂着，用户会以为升级没生效。这里做两件事：
//   1. 本页轮询 version_info，检测到版本变化 → 关黄条 + 提示 + 刷新列表；
//   2. 跨页面的通用信号在 public.js（yfWatchTaskIdle → yf:tasks-changed），
//      即使用户关掉本窗口，首页也会在任务结束几秒内自己刷新。
// 轮询间隔 60s、最长 45 分钟（按 1C 机器上限兜底），结束后自动停止。
// ---------------------------------------------------------------------------
var orUpgradeWatchTimer = null;

function orStopUpgradeWatch() {
    if (orUpgradeWatchTimer) {
        clearTimeout(orUpgradeWatchTimer);
        orUpgradeWatchTimer = null;
    }
}

function orRefreshPanelSoft() {
    try {
        localStorage.removeItem('index_soft_cache_html');
        localStorage.removeItem('index_soft_cache_html_v3');
    } catch (e) {}
    if (typeof getSList === 'function' && $('#softList').length > 0) {
        getSList(true);
    }
    if ($('#indexsoft').length > 0) {
        if (typeof indexListHtml === 'function') {
            indexListHtml();
        } else if (typeof refreshIndexSoft === 'function') {
            refreshIndexSoft();
        }
    }
    if (typeof getTaskCount === 'function') {
        getTaskCount();
    }
}

function orWatchUpgradeDone(targetVer) {
    orStopUpgradeWatch();
    var fromVer = orInstalledVersion || '';
    var startedAt = Date.now();
    var maxMs = 45 * 60 * 1000;
    function tick() {
        if (Date.now() - startedAt > maxMs) {
            orStopUpgradeWatch();
            return;
        }
        api.post('version_info', {}, function (res) {
            var d = null;
            try {
                d = typeof res.data === 'string' ? JSON.parse(res.data) : res.data;
            } catch (e) {
                d = null;
            }
            if (d && d.installed && d.installed !== fromVer && !d.needs_update) {
                orInstalledVersion = d.installed;
                orHideVersionTip();
                layer.msg(msgTpl(pt('OpenResty 已升级到 {1}'), [d.installed]), { icon: 1 });
                orRefreshPanelSoft();
                orStopUpgradeWatch();
                return;
            }
            orUpgradeWatchTimer = setTimeout(tick, 60000);
        });
    }
    orUpgradeWatchTimer = setTimeout(tick, 20000);
}
