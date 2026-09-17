var api = YfPlugin.createApi('redis');
var pt = YfI18n.createPluginTranslator('redis');


function redisPostCallbak(method, version, args,callback){
    var loadT = layer.msg(pt('正在获取...'), { icon: 16, time: 0, shade: 0.3 });

    var req_data = {};
    req_data['name'] = 'redis';
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

//redis状态  start
function redisStatus(version) {
    api.post('run_info', version, {}, function(data){
        var rdata = {};
        try {
            rdata = JSON.parse(data.data);
        } catch(e) {
            rdata = {};
        }

        if ('status' in rdata && !rdata.status){
            layer.msg(rdata.msg || pt('获取负载状态失败'), {icon: 0, time: 2000, shade: [0.3, '#000']});
            return;
        }

        var getVal = function(key, fallback) {
            return (rdata && rdata[key] !== undefined && rdata[key] !== null && rdata[key] !== '') ? rdata[key] : (fallback !== undefined ? fallback : '-');
        };

        var hits = parseInt(rdata.keyspace_hits || 0);
        var misses = parseInt(rdata.keyspace_misses || 0);
        var hit = (hits + misses > 0) ? ((hits / (hits + misses)) * 100).toFixed(2) + '%' : '0.00%';
        var formatMem = function(v) {
            if (v === undefined || v === null || v === '' || v === '-') return '-';
            return (typeof toSize === 'function') ? toSize(v) : (v + ' B');
        };

        var con = '<div class="divtable">\
                        <table class="table table-hover table-bordered" style="width: 100%; max-width: 680px;">\
                        <thead><th style="width: 200px;">' + pt('字段') + '</th><th style="width: 160px;">' + pt('当前值') + '</th><th>' + pt('说明') + '</th></thead>\
                        <tbody>\
                            <tr><th>uptime_in_days</th><td>' + getVal('uptime_in_days') + '</td><td>' + pt('已运行天数') + '</td></tr>\
                            <tr><th>tcp_port</th><td>' + getVal('tcp_port') + '</td><td>' + pt('当前监听端口') + '</td></tr>\
                            <tr><th>connected_clients</th><td>' + getVal('connected_clients') + '</td><td>' + pt('连接的客户端数量') + '</td></tr>\
                            <tr><th>used_memory_rss</th><td>' + formatMem(rdata.used_memory_rss) + '</td><td>' + pt('Redis当前占用的系统内存总量') + '</td></tr>\
                            <tr><th>used_memory</th><td>' + formatMem(rdata.used_memory) + '</td><td>' + pt('Redis当前已分配的内存总量') + '</td></tr>\
                            <tr><th>used_memory_peak</th><td>' + formatMem(rdata.used_memory_peak) + '</td><td>' + pt('Redis历史分配内存的峰值') + '</td></tr>\
                            <tr><th>mem_fragmentation_ratio</th><td>' + getVal('mem_fragmentation_ratio', '-') + (rdata.mem_fragmentation_ratio ? '%' : '') + '</td><td>' + pt('内存碎片比率') + '</td></tr>\
                            <tr><th>total_connections_received</th><td>' + getVal('total_connections_received') + '</td><td>' + pt('运行以来连接过的客户端的总数量') + '</td></tr>\
                            <tr><th>total_commands_processed</th><td>' + getVal('total_commands_processed') + '</td><td>' + pt('运行以来执行过的命令的总数量') + '</td></tr>\
                            <tr><th>instantaneous_ops_per_sec</th><td>' + getVal('instantaneous_ops_per_sec') + '</td><td>' + pt('服务器每秒钟执行的命令数量') + '</td></tr>\
                            <tr><th>keyspace_hits</th><td>' + getVal('keyspace_hits') + '</td><td>' + pt('查找数据库键成功的次数') + '</td></tr>\
                            <tr><th>keyspace_misses</th><td>' + getVal('keyspace_misses') + '</td><td>' + pt('查找数据库键失败的次数') + '</td></tr>\
                            <tr><th>hit</th><td>' + hit + '</td><td>' + pt('查找数据库键命中率') + '</td></tr>\
                            <tr><th>latest_fork_usec</th><td>' + getVal('latest_fork_usec') + '</td><td>' + pt('最近一次 fork() 操作耗费的微秒数') + '</td></tr>\
                        <tbody>\
                </table></div>';
        $(".soft-man-con").html(con);
    });
}

function replStatus(version){
    api.post('info_replication', version, {},function(data){
        var rdata = JSON.parse(data.data);

        if ('status' in rdata && !rdata.status){
            layer.msg(rdata.msg,{icon:0,time:2000,shade: [0.3, '#000']});
            return;
        }

        var kv = {
            'role':'角色',
            'master_host':'连接主库HOST',
            'master_port':'连接主库PORT',
            'master_link_status':'连接主库状态',
            'master_last_io_seconds_ago':'上次同步时间',
            'master_sync_in_progress':'正在同步中',
            'slave_read_repl_offset':'从库读取复制位置',
            'slave_repl_offset':'从库复制位置',
            'slave_read_only':'从库是否仅读',
            'replica_announced':'已复制副本',
            'connected_slaves':'连接数量',
            'master_failover_state':'主库故障状态',
            'master_replid':'主库复制ID',
            'master_repl_offset':'主库复制位置',
            'repl_backlog_size':'backlog复制大小',
            'second_repl_offset':'复制位置时间',
            'repl_backlog_first_byte_offset':'第一个字节偏移量',
            'repl_backlog_histlen':'backlog中数据的长度',
            'repl_backlog_active':'开启复制缓冲区',
            'slave_priority':'同步优先级',
        }

        var tbody_text = '';
        for (k in rdata){
            if (k == 'master_replid'){
                tbody_text += '<tr><th>'+k+'</th><td class="overflow_hide" style="width:155px;display: inline-block;border: none;">' + rdata[k] + '</td><td>'+kv[k]+'</td></tr>';
            } else{

                if (k.substring(0,5) == 'slave' && !isNaN(k.substring(5))){
                    tbody_text += '<tr><th>'+k+'</th><td class="overflow_hide" style="width:155px;display: inline-block;border: none;" title="'+rdata[k]+'">' + rdata[k] + '</td><td>' + pt('从库配置信息') + '</td></tr>';
                } else{
                    tbody_text += '<tr><th>'+k+'</th><td>' + rdata[k] + '</td><td>'+kv[k]+'</td></tr>';
                }

                
            }   
        }

        var con = '<div class="divtable">\
                        <table class="table table-hover table-bordered" style="width: 490px;">\
                        <thead><th style="width:80px;">' + pt('字段') + '</th><th style="width:90px;">' + pt('当前值') + '</th><th>' + pt('说明') + '</th></thead>\
                        <tbody>'+tbody_text+'<tbody>\
                </table></div>';
        $(".soft-man-con").html(con);
    });
}

function clusterStatus(version){
    api.post('cluster_info', version, {},function(data){
        var rdata = JSON.parse(data.data);

        if ('status' in rdata && !rdata.status){
            layer.msg(rdata.msg,{icon:0,time:2000,shade: [0.3, '#000']});
            return;
        }

        var kv = {
            'cluster_state':'集群状态',
            'cluster_slots_assigned':'被分配的槽',
            'cluster_slots_ok':'被分配的槽状态',
            'cluster_known_nodes':'知道的节点',
            'cluster_size':'大小',
            'cluster_stats_messages_sent':'发送',
            'cluster_stats_messages_received':'接收',
            'cluster_current_epoch':'集群当前epoch',
            'cluster_my_epoch':'当前我的epoch',
            'cluster_slots_pfail':'处于PFAIL状态的槽数',
            'cluster_slots_fail':'处于FAIL状态的槽数',
            'total_cluster_links_buffer_limit_exceeded':'超出缓冲区总数',
        }

        var tbody_text = '';
        for (k in rdata){
            var desc = k;
            if (k in kv){
                desc = kv[k];
            }

            if (k == 'master_replid'){
                tbody_text += '<tr><th>'+k+'</th><td class="overflow_hide" style="width:155px;display: inline-block;border: none;">' + rdata[k] + '</td><td>'+desc+'</td></tr>';
            } else{
                tbody_text += '<tr><th>'+k+'</th><td>' + rdata[k] + '</td><td>'+desc+'</td></tr>';
            }   
        }

        if (tbody_text == ''){
            tbody_text += '<tr><td colspan="3" style="text-align:center;">' + pt('无数据/未设置集群') + '</td></tr>';
        }

        var con = '<div class="divtable">\
                        <table class="table table-hover table-bordered" style="width: 490px;">\
                        <thead><th style="width:80px;">' + pt('字段') + '</th><th style="width:90px;">' + pt('当前值') + '</th><th>' + pt('说明') + '</th></thead>\
                        <tbody>'+tbody_text+'<tbody>\
                </table></div>';
        $(".soft-man-con").html(con);
    });
}

function clusterNodes(version){
    api.post('cluster_nodes', version, {},function(data){
        var rdata = JSON.parse(data.data);

        if ('status' in rdata && !rdata.status){
            layer.msg(rdata.msg,{icon:0,time:2000,shade: [0.3, '#000']});
            return;
        }

        // console.log(rdata);
        var tbody_text = '';
        for (k in rdata){
            tbody_text += '<tr><td>'+ rdata[k] +'</td></tr>';
        }

        if (tbody_text == ''){
            tbody_text += '<tr><td style="text-align:center;">' + pt('无数据/未设置集群') + '</td></tr>';
        }

        var con = '<div class="divtable">\
                        <table class="table table-hover table-bordered" style="width: 490px;">\
                        <thead><th style="width:80px;text-align:center;">' + pt('节点信息') + '</th></thead>\
                        <tbody>'+tbody_text+'<tbody>\
                </table></div>';
        $(".soft-man-con").html(con);
    });
}

//redis状态 end

//配置修改
function getRedisConfig(version) {
    api.post('get_redis_conf', version, '', function(data){
        var rdata = [];
        try {
            rdata = JSON.parse(data.data);
        } catch(e) {
            rdata = [];
        }
        var mlist = '';
        for (var i = 0; i < rdata.length; i++) {
            var item = rdata[i];
            // 所有配置项，input 框保持宽度一致（统一为 200px）
            var w = '200';
            var ibody = '<input style="width: ' + w + 'px; height: 34px;" class="bt-input-text mr5" name="' + item.name + '" value="' + item.value + '" type="text" >';
            switch (item.type) {
                case 0:
                    var selected_1 = (item.value == 1) ? 'selected' : '';
                    var selected_0 = (item.value == 0) ? 'selected' : '';
                    ibody = '<select class="bt-input-text mr5" name="' + item.name + '" style="width: ' + w + 'px; height: 34px;"><option value="1" ' + selected_1 + '>' + pt('开启') + '</option><option value="0" ' + selected_0 + '>' + pt('关闭') + '</option></select>';
                    break;
                case 1:
                    var selected_1 = (item.value == 'On') ? 'selected' : '';
                    var selected_0 = (item.value == 'Off') ? 'selected' : '';
                    ibody = '<select class="bt-input-text mr5" name="' + item.name + '" style="width: ' + w + 'px; height: 34px;"><option value="On" ' + selected_1 + '>' + pt('开启') + '</option><option value="Off" ' + selected_0 + '>' + pt('关闭') + '</option></select>';
                    break;
            }
            mlist += '<div class="redis-form-row" style="display:flex;align-items:center;margin-bottom:14px;min-height:36px;width:100%;">\
                        <label class="redis-form-label" style="width:115px;min-width:115px;text-align:right;padding-right:14px;font-weight:600;color:#374151;flex-shrink:0;margin:0;">' + item.name + '</label>\
                        <div class="redis-form-body" style="display:flex;align-items:center;flex:1;flex-wrap:nowrap;width:auto;margin:0;">\
                            ' + ibody + '\
                            <div class="redis-field-desc" style="display:inline-block !important;width:auto !important;max-width:none !important;text-align:left !important;margin-left:14px !important;color:#6b7280;font-size:13px;white-space:nowrap !important;line-height:1.5;">' + pt(item.ps) + '</div>\
                        </div>\
                     </div>';
        }
        var con = '<div class="redis-conf-wrap" style="width:100%;margin-bottom:0;padding-top:10px;box-sizing:border-box;">' + mlist + '\
                        <div style="margin-top:24px;padding-left:129px;" class="form-btn-group">\
                            <button class="btn btn-success btn-sm mr10" onclick="getRedisConfig(\'' + version + '\')">' + pt('刷新') + '</button>\
                            <button class="btn btn-success btn-sm" onclick="submitConf(\'' + version + '\')">' + pt('保存') + '</button>\
                        </div>\
                    </div>';
        $(".soft-man-con").html(con);
    });
}

//提交配置
function submitConf(version) {
    var bind = $("input[name='bind']").val();
    var port = $("input[name='port']").val();
    var timeout = $("input[name='timeout']").val();
    var maxclients = $("input[name='maxclients']").val();
    var databases = $("input[name='databases']").val();
    var requirepass = $("input[name='requirepass']").val();
    var maxmemory = $("input[name='maxmemory']").val();

    // 前置正则校验，保障提交数据的合规与安全
    var num_reg = /^\d+$/;
    var ip_reg = /^[0-9a-zA-Z_.:\s,-]+$/;
    var pass_reg = /^[a-zA-Z0-9_.~!@#$%^&*()_+=-]*$/;

    if (!num_reg.test(port)) {
        layer.msg(pt('端口必须为纯数字！'), {icon: 2});
        return;
    }
    if (!num_reg.test(timeout)) {
        layer.msg(pt('超时时间必须为纯数字！'), {icon: 2});
        return;
    }
    if (!num_reg.test(maxclients)) {
        layer.msg(pt('最大连接数必须为纯数字！'), {icon: 2});
        return;
    }
    if (!num_reg.test(databases)) {
        layer.msg(pt('数据库数量必须为纯数字！'), {icon: 2});
        return;
    }
    if (!num_reg.test(maxmemory)) {
        layer.msg(pt('最大内存量必须为纯数字！'), {icon: 2});
        return;
    }
    if (bind && !ip_reg.test(bind)) {
        layer.msg(pt('绑定IP地址格式不合法！'), {icon: 2});
        return;
    }
    if (requirepass && !pass_reg.test(requirepass)) {
        layer.msg(pt('Redis密码包含非法字符！建议仅包含字母、数字与常用安全符号'), {icon: 2});
        return;
    }

    var data = {
        version: version,
        bind: bind,
        'port': port,
        'timeout': timeout,
        maxclients: maxclients,
        databases: databases,
        requirepass: requirepass,
        maxmemory: maxmemory,
    };

    var loadT = layer.msg(pt('正在保存配置并应用...'), {icon: 16, time: 0, shade: 0.3});
    api.post('submit_redis_conf', version, data, function(ret_data){
        layer.close(loadT);
        var rdata = JSON.parse(ret_data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
    });
}


function redisReadme(){
    // 动态获取 Redis 路径，彻底消除硬编码，提升极佳的自适应交互体验
    api.post('conf', '', {}, function(data){
        var conf_path = data.data;
        var redis_bin_dir = conf_path.substring(0, conf_path.lastIndexOf('/')) + '/bin';
        
        var cmd_01 = redis_bin_dir + '/redis-cli --cluster create 127.0.0.1:6379 127.0.0.1:6380 127.0.0.1:6381 --cluster-replicas 0';
        var cmd_02 = redis_bin_dir + '/redis-cli --cluster create 127.0.0.1:6379 127.0.0.1:6380 127.0.0.1:6381 127.0.0.1:6382 127.0.0.1:6383 127.0.0.1:6384 --cluster-replicas 1';

        var readme = '<ul class="help-info-text c7">';
        readme += '<li style="margin-top: 10px;"><strong>' + pt('💡 动态集群创建示例 1 (不带副本)：') + '</strong></li>';
        readme += '<li style="background-color: #f7f9fa; padding: 12px; border-radius: 6px; font-family: monospace; word-break: break-all; margin: 8px 0 16px 0; border: 1px solid #e1e4e6; color: #2c3e50; font-size: 13px; line-height: 1.5;">' + cmd_01 + '</li>';
        readme += '<li><strong>' + pt('💡 动态集群创建示例 2 (带 1 个副本)：') + '</strong></li>';
        readme += '<li style="background-color: #f7f9fa; padding: 12px; border-radius: 6px; font-family: monospace; word-break: break-all; margin: 8px 0 8px 0; border: 1px solid #e1e4e6; color: #2c3e50; font-size: 13px; line-height: 1.5;">' + cmd_02 + '</li>';
        readme += '</ul>';

        $('.soft-man-con').html(readme);   
    });
}


// redis 运行日志专属现代化视图
function redisRunLog() {
    var loadT = layer.msg(pt('正在获取运行日志...'), { icon: 16, time: 0, shade: 0.3 });
    api.post('get_run_log', '', {}, function(res) {
        layer.close(loadT);
        var rdata = {};
        try {
            rdata = JSON.parse(res.data);
        } catch (e) {
            rdata = { status: false, msg: res.data || pt('获取日志失败') };
        }

        if (!rdata.status) {
            layer.msg(rdata.msg || pt('获取日志失败'), { icon: 0, time: 2000, shade: [0.3, '#000'] });
            return;
        }

        var logData = rdata.data || {};
        var logPath = (typeof logData === 'object' && logData.path) ? logData.path : '-';
        var logContent = (typeof logData === 'object' && logData.data) ? logData.data : (typeof logData === 'string' ? logData : '');

        var con = '<div class="redis-log-container" style="padding: 6px 0; box-sizing: border-box;">\
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px;">\
                <div style="display: flex; align-items: center; font-size: 13px; color: #4b5563;">\
                    <span style="font-weight: 600; margin-right: 6px;">' + pt('日志文件') + ':</span>\
                    <code style="font-size: 12px; color: #2563eb; background-color: #eff6ff; padding: 2px 8px; border-radius: 4px; border: 1px solid #dbeafe;">' + logPath + '</code>\
                </div>\
                <div style="display: flex; gap: 8px;">\
                    <button class="btn btn-default btn-sm btn-redis-refresh-log" style="display: inline-flex; align-items: center; height: 30px; font-size: 12px;">\
                        <span class="glyphicon glyphicon-refresh" style="margin-right: 4px;"></span> ' + pt('刷新日志') + '\
                    </button>\
                    <button class="btn btn-default btn-sm btn-redis-clear-log" style="display: inline-flex; align-items: center; height: 30px; font-size: 12px; color: #dc2626;">\
                        <span class="glyphicon glyphicon-trash" style="margin-right: 4px;"></span> ' + pt('清空日志') + '\
                    </button>\
                </div>\
            </div>\
            <div style="background-color: #f0fdf4; border-left: 4px solid #16a34a; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #166534; line-height: 1.6;">\
                <span class="glyphicon glyphicon-info-sign" style="margin-right: 6px; font-size: 13px;"></span>\
                <strong>' + pt('说明') + '：</strong>' + pt('Redis 运行日志仅记录服务生命周期（启动/关闭）、持久化快照(RDB/AOF)及错误告警；常规键值读写记录不写入此日志。') + '\
            </div>\
            <textarea readonly style="margin: 0px; width: 100%; height: 430px; background-color: #1e293b; color: #f8fafc; font-family: Consolas, Monaco, monospace; font-size: 12px; line-height: 1.6; padding: 10px 12px; border-radius: 6px; border: 1px solid #334155; resize: none; box-sizing: border-box; overflow-y: auto;" id="redis_run_log_content">' + logContent + '</textarea>\
        </div>';

        $(".soft-man-con").html(con);
        var ob = document.getElementById('redis_run_log_content');
        if (ob) {
            ob.scrollTop = ob.scrollHeight;
        }

        // 绑定刷新事件
        $(".btn-redis-refresh-log").off('click').on('click', function() {
            redisRunLog();
        });

        // 绑定清空事件
        $(".btn-redis-clear-log").off('click').on('click', function() {
            layer.confirm(pt('确认清空当前 Redis 运行日志吗？'), { icon: 3, title: pt('提示') }, function(index) {
                layer.close(index);
                var clearLoad = layer.msg(pt('正在清空...'), { icon: 16, time: 0, shade: 0.3 });
                api.post('clear_run_log', '', {}, function(cres) {
                    layer.close(clearLoad);
                    var crdata = {};
                    try {
                        crdata = JSON.parse(cres.data);
                    } catch (e) {
                        crdata = { status: false, msg: cres.data };
                    }
                    if (crdata.status) {
                        layer.msg(pt('日志已清空'), { icon: 1, time: 1500 });
                        redisRunLog();
                    } else {
                        layer.msg(crdata.msg || pt('清空运行日志失败'), { icon: 2, time: 2000 });
                    }
                });
            });
        });
    });
}


