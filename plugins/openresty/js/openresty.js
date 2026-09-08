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
    var serviceCon ='<p class="status">' + pt('当前状态：', '当前状态：') + '<span>'+(status ? pt('开启', '开启') : pt('关闭', '关闭') )+
        '</span><span style="color: '+
        (status?'#20a53a;':'red;')+
        ' margin-left: 3px;" class="glyphicon ' + (status?'glyphicon glyphicon-play':'glyphicon-pause')+'"></span></p><div class="sfm-opt">\
            <button class="btn btn-default btn-sm" onclick="orPluginOpService(\''+_name+'\',\''+(status?'stop':'start')+'\',\''+version+'\')">'+(status?pt('停止', '停止'):pt('启动', '启动'))+'</button>\
            <button class="btn btn-default btn-sm" onclick="orPluginOpService(\''+_name+'\',\'restart\',\''+version+'\',\'yes\')">'+pt('重启', '重启')+'</button>\
            <button class="btn btn-default btn-sm" onclick="orPluginOpService(\''+_name+'\',\'reload\',\''+version+'\')">'+pt('还原默认配置', '还原默认配置')+'</button>\
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
        case "stop":d = '停止';break;
        case "start":d = '启动';break;
        case "restart":d = '重启';break;
        case "reload":d = '重载';break;
    }
    layer.confirm( msgTpl('您真的要{1}{2}{3}服务吗？', [d,a,v]), {icon:3,closeBtn: 2}, function() {
        api.post('get_os',{},function(data){
            var rdata = JSON.parse(data.data);
            if (!rdata['auth']){
                layer.prompt({title: '检查到权限不足,需要输入密码!', formType: 1},function(pwd, index){
                
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

    var e = layer.msg(msgTpl('正在{1}{2}{3}服务,请稍候...',[d,a,v]), {icon: 16,time: 0});
    $.post(request_path, c, function(g) {
        layer.close(e);
        
        var f = g.data == 'ok' ? msgTpl('{1}{2}服务已{3}',[a,v,d]) : msgTpl('{1}{2}服务{3}失败!',[a,v,d]);
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
        layer.msg('操作异常!', {icon: 2});
    });
}


//查看Nginx负载状态
function getOpStatus() {
    var loadT = layer.msg('正在处理，请稍后...', { icon: 16, time: 0, shade: 0.3 });
    $.post('/plugins/run', {name:'openresty', func:'run_info'}, function(data) {
        layer.close(loadT); 
        try {
            var rdata = JSON.parse(data.data);
            if ('status' in rdata && !rdata.status){
                showMsg(rdata.msg, function(){}, null,3000);
                return;
            }

            var con = "<div><table class='table table-hover table-bordered'>\
                            <tr><th>活动连接(Active connections)</th><td>" + rdata.active + "</td></tr>\
                            <tr><th>总连接次数(accepts)</th><td>" + rdata.accepts + "</td></tr>\
                            <tr><th>总握手次数(handled)</th><td>" + rdata.handled + "</td></tr>\
                            <tr><th>总请求数(requests)</th><td>" + rdata.requests + "</td></tr>\
                            <tr><th>请求数(Reading)</th><td>" + rdata.Reading + "</td></tr>\
                            <tr><th>响应数(Writing)</th><td>" + rdata.Writing + "</td></tr>\
                            <tr><th>驻留进程(Waiting)</th><td>" + rdata.Waiting + "</td></tr>\
                         </table></div>";
            $(".soft-man-con").html(con);
        }catch(err){
             showMsg(data.data, function(){}, null,3000);
        }
    },'json');
}


function setOpCfg(){
    api.post('get_cfg', {}, function(data){
        var rdata = JSON.parse(data.data);
        var rdata = rdata.data;
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
                        <option value="1" ' + selected_1 + '>开启</option>\
                        <option value="0" ' + selected_0 + '>关闭</option>\
                    </select>';
                    break;
                case 1:
                    var selected_1 = (rdata[i].value == 'on') ? 'selected' : '';
                    var selected_0 = (rdata[i].value == 'off') ? 'selected' : '';
                    ibody = '<select class="bt-input-text mr5" name="' + rdata[i].name + '" style="width: ' + w + 'px;">\
                        <option value="on" ' + selected_1 + '>开启</option>\
                        <option value="off" ' + selected_0 + '>关闭</option>\
                    </select>';
                    break;
            }
            mlist += '<p style="margin-top:15px;"><span>' + rdata[i].name + '</span>' + ibody + "<b class='unit c9'>"+rdata[i].unit+"</b>" +', <font class="c9">' + rdata[i].ps + '</font></p>';
        }
        var con = '<style>.conf_p p{margin-bottom: 2px}</style><div class="conf_p" style="margin-bottom:0">\
                        ' + mlist + '\
                        <div style="margin-top:10px; padding-right:15px" class="text-right">\
                            <button class="btn btn-default btn-sm mr5" style="color: #d9534f; border-color: #d9534f;" onclick="restoreDefault()">还原默认</button>\
                            <button class="btn btn-success btn-sm mr5" onclick="setOpCfg()">刷新</button>\
                            <button class="btn btn-success btn-sm" onclick="submitConf()">保存</button>\
                        </div>\
                    </div>'
        $(".soft-man-con").html(con);
    });
}

function restoreDefault() {
    layer.confirm('您确定要将配置还原为默认调优配置吗？这会覆盖您当前的自定义调整并重载服务。', {icon:3,closeBtn: 2}, function() {
        api.post('get_os',{},function(data){
            var rdata = JSON.parse(data.data);
            var c = "name=openresty&func=reload";
            if (!rdata['auth']){
                layer.prompt({title: '检查到权限不足,需要输入密码!', formType: 1},function(pwd, index){
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
    var e = layer.msg('正在还原默认配置,请稍候...', {icon: 16,time: 0});
    $.post('/plugins/run', c, function(g) {
        layer.close(e);
        if (g.data == 'ok') {
            layer.msg('还原默认配置成功！', {icon: 1});
            setOpCfg();
            if (typeof window.refreshExternalPluginStatus === 'function') {
                window.refreshExternalPluginStatus('openresty');
            }
        } else {
            layer.msg('还原默认配置失败！', {icon: 2});
            if( g.status && g.data != 'ok' ) {
                layer.msg(g.data, {icon: 2,time: 10000,shade: 0.3});
            }
        }
    },'json').fail(function() {
        layer.close(e);
        layer.msg('操作异常!', {icon: 2});
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
        var rdata = JSON.parse(rdata.data);
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
                <span style="font-size: 13px; font-weight: 600; color: #1e293b;">' + pt('服务守护（检查任务）', '服务守护（检查任务）') + '</span>\
            </div>\
            <span id="openresty_cron_badge" style="display: inline-flex; align-items: center; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; transition: all 0.2s ease;">\
                <span style="width: 6px; height: 6px; border-radius: 50%; background: #94a3b8; margin-right: 6px; display: inline-block;"></span>\
                <span class="badge-text">' + pt('获取中...', '获取中...') + '</span>\
            </span>\
        </div>\
        <div style="font-size: 12px; color: #475569; line-height: 1.6;">\
            <p style="margin-bottom: 5px;">' + pt('自动每 3 分钟巡检一次 OpenResty 服务状态。当检测到僵尸进程或服务异常宕机时，将自动清理异常残留并拉起服务，实现故障自愈。', '自动每 3 分钟巡检一次 OpenResty 服务状态。当检测到僵尸进程或服务异常宕机时，将自动清理异常残留并拉起服务，实现故障自愈。') + '</p>\
            <p style="margin-bottom: 0; color: #64748b;"><span class="glyphicon glyphicon-info-sign" style="color: #3b82f6; margin-right: 4px;"></span>' + pt('指引：生产环境推荐开启以保障网站高可用运行；如需停服维护或断点排查时可随时删除检查任务。', '指引：生产环境推荐开启以保障网站高可用运行；如需停服维护或断点排查时可随时删除检查任务。') + '</p>\
        </div>\
        <div style="margin-top: 12px; display: flex; gap: 10px; align-items: center;">\
            <button id="openresty_cron_add_btn" class="btn btn-success btn-sm" onclick="cronAddCheck()"><span class="glyphicon glyphicon-plus-sign" style="margin-right: 4px;"></span>' + pt('添加检查任务', '添加检查任务') + '</button>\
            <button id="openresty_cron_del_btn" class="btn btn-default btn-sm" onclick="cronDelCheck()"><span class="glyphicon glyphicon-trash" style="margin-right: 4px;"></span>' + pt('删除检查任务', '删除检查任务') + '</button>\
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
                $badge.html('<span style="width: 6px; height: 6px; border-radius: 50%; background: #10b981; margin-right: 6px; display: inline-block;"></span><span class="badge-text">' + pt('已开启', '已开启') + '</span>')
                      .css({
                          'background': '#ecfdf5',
                          'color': '#059669',
                          'border-color': '#a7f3d0'
                      });
                $addBtn.html('<span class="glyphicon glyphicon-refresh" style="margin-right: 4px;"></span>' + pt('重新同步检查任务', '重新同步检查任务'));
                $delBtn.prop('disabled', false).removeClass('disabled').css('opacity', '1');
            } else {
                $badge.html('<span style="width: 6px; height: 6px; border-radius: 50%; background: #94a3b8; margin-right: 6px; display: inline-block;"></span><span class="badge-text">' + pt('未开启', '未开启') + '</span>')
                      .css({
                          'background': '#f1f5f9',
                          'color': '#64748b',
                          'border-color': '#e2e8f0'
                      });
                $addBtn.html('<span class="glyphicon glyphicon-plus-sign" style="margin-right: 4px;"></span>' + pt('添加检查任务', '添加检查任务'));
                $delBtn.prop('disabled', true).addClass('disabled').css('opacity', '0.6');
            }
        } catch (e) {}
    });
}

function cronAddCheck(){
    var loadT = layer.msg(pt('正在添加检查任务...', '正在添加检查任务...'), { icon: 16, time: 0, shade: 0.3 });
    api.post('cron_add_check', {}, function(data){
        layer.close(loadT);
        var rdata = typeof data.data === 'string' ? JSON.parse(data.data) : data.data;
        var msg = rdata.msg || (rdata.status ? pt('添加检查任务成功', '添加检查任务成功') : pt('添加检查任务失败', '添加检查任务失败'));
        layer.msg(msg, { icon: rdata.status ? 1 : 2 });
        orPluginRefreshCronStatus('openresty');
    }).fail(function(){
        layer.close(loadT);
        layer.msg(pt('操作异常!', '操作异常!'), { icon: 2 });
    });
}

function cronDelCheck(){
    layer.confirm(pt('确定要删除 OpenResty 守护检查任务吗？删除后将不再自动监控与拉起服务。', '确定要删除 OpenResty 守护检查任务吗？删除后将不再自动监控与拉起服务。'), {icon: 3, closeBtn: 2, title: pt('删除检查任务', '删除检查任务')}, function(index){
        layer.close(index);
        var loadT = layer.msg(pt('正在删除检查任务...', '正在删除检查任务...'), { icon: 16, time: 0, shade: 0.3 });
        api.post('cron_del_check', {}, function(data){
            layer.close(loadT);
            var rdata = typeof data.data === 'string' ? JSON.parse(data.data) : data.data;
            var msg = rdata.msg || (rdata.status ? pt('删除检查任务成功', '删除检查任务成功') : pt('删除检查任务失败', '删除检查任务失败'));
            layer.msg(msg, { icon: rdata.status ? 1 : 2 });
            orPluginRefreshCronStatus('openresty');
        }).fail(function(){
            layer.close(loadT);
            layer.msg(pt('操作异常!', '操作异常!'), { icon: 2 });
        });
    });
}












