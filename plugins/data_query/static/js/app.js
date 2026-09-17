// 全局插件国际化翻译安全兜底（采用函数声明保证变量提升与零引用异常）
function pt(str) {
    if (window._raw_pt && typeof window._raw_pt === 'function') {
        try { return window._raw_pt(str); } catch(e){}
    }
    if (typeof window.pt === 'function' && window.pt !== pt) {
        try { return window.pt(str); } catch(e){}
    }
    if (window.YfI18n && typeof window.YfI18n.createPluginTranslator === 'function') {
        try {
            if (!window._dq_translator) {
                window._dq_translator = window.YfI18n.createPluginTranslator('data_query');
            }
            return window._dq_translator(str);
        } catch(e){}
    }
    return str;
}
if (typeof window.pt === 'function') {
    window._raw_pt = window.pt;
}
window.pt = pt;

$(function() {
    var tag = $.getUrlParam('tag');
    if(tag == 'data_query'){
        initDataQuery();
    }
});

function redisPostCB(method, args, callback){
    var loadT = layer.msg('正在获取...', { icon: 16, time: 0, shade: 0.3 });

    var req_data = {};
    req_data['name'] = 'data_query';
    req_data['func'] = method;
    req_data['script']='nosql_redis';
    if (!args || typeof(args) !== 'object') {
        args = {};
    }
    args['version'] = '';
 
    if (typeof(args) == 'string' && args == ''){
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

function mgdbPostCB(method, args, callback){
    var loadT = layer.msg('正在获取...', { icon: 16, time: 0, shade: 0.3 });

    var req_data = {};
    req_data['name'] = 'data_query';
    req_data['func'] = method;
    req_data['script']='nosql_mongodb';
    if (!args || typeof(args) !== 'object') {
        args = {};
    }
    args['version'] = '';
 
    if (typeof(args) == 'string' && args == ''){
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

function memPostCB(method, args, callback){
    var loadT = layer.msg('正在获取...', { icon: 16, time: 0, shade: 0.3 });

    var req_data = {};
    req_data['name'] = 'data_query';
    req_data['func'] = method;
    req_data['script']='nosql_memcached';
    if (!args || typeof(args) !== 'object') {
        args = {};
    }
    args['version'] = '';
 
    if (typeof(args) == 'string' && args == ''){
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

function myPostCB(method, args, callback){
    var loadT = layer.msg('正在获取...', { icon: 16, time: 0, shade: 0.3 });

    var req_data = {};
    req_data['name'] = 'data_query';
    req_data['func'] = method;
    req_data['script']='sql_mysql';
    if (!args || typeof(args) !== 'object') {
        args = {};
    }
    args['version'] = '';
 
    if (typeof(args) == 'string' && args == ''){
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

function myPostCBN(method, args, callback){
    var req_data = {};
    req_data['name'] = 'data_query';
    req_data['func'] = method;
    req_data['script']='sql_mysql';
    if (!args || typeof(args) !== 'object') {
        args = {};
    }
    args['version'] = '';
 
    if (typeof(args) == 'string' && args == ''){
        req_data['args'] = JSON.stringify(toArrayObject(args));
    } else {
        req_data['args'] = JSON.stringify(args);
    }

    $.post('/plugins/callback', req_data, function(data) {
        if (!data.status){
            if(typeof(callback) == 'function'){
                callback(data);
            }
            return;
        }

        if(typeof(callback) == 'function'){
            callback(data);
        }
    },'json'); 
}

function pgPostCB(method, args, callback){
    var loadT = layer.msg('正在获取...', { icon: 16, time: 0, shade: 0.3 });

    var req_data = {};
    req_data['name'] = 'data_query';
    req_data['func'] = method;
    req_data['script'] = 'sql_postgresql';
    if (!args || typeof(args) !== 'object') {
        args = {};
    }
    args['version'] = '';

    if (typeof(args) == 'string' && args == ''){
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

function pgPostCBN(method, args, callback){
    var req_data = {};
    req_data['name'] = 'data_query';
    req_data['func'] = method;
    req_data['script'] = 'sql_postgresql';
    if (!args || typeof(args) !== 'object') {
        args = {};
    }
    args['version'] = '';

    if (typeof(args) == 'string' && args == ''){
        req_data['args'] = JSON.stringify(toArrayObject(args));
    } else {
        req_data['args'] = JSON.stringify(args);
    }

    $.post('/plugins/callback', req_data, function(data) {
        if (!data.status){
            if(typeof(callback) == 'function'){
                callback(data);
            }
            return;
        }

        if(typeof(callback) == 'function'){
            callback(data);
        }
    },'json'); 
}

function loadDbPort(dbType, containerSelector, sid){
    if (sid === undefined || sid === null) {
        sid = 0;
    }
    var req_data = {
        name: 'data_query',
        args: JSON.stringify({sid: sid})
    };
    if (dbType === 'mysql') {
        req_data.script = 'sql_mysql';
        req_data.func = 'get_db_port';
    } else if (dbType === 'postgresql') {
        req_data.script = 'sql_postgresql';
        req_data.func = 'get_db_port';
    } else if (dbType === 'redis') {
        req_data.script = 'nosql_redis';
        req_data.func = 'get_db_port';
    } else if (dbType === 'mongodb') {
        req_data.script = 'nosql_mongodb';
        req_data.func = 'get_db_port';
    } else if (dbType === 'memcached') {
        req_data.script = 'nosql_memcached';
        req_data.func = 'get_db_port';
    }

    $.post('/plugins/callback', req_data, function(res){
        if (res && res.data && res.data.data && res.data.data.port) {
            var port = res.data.data.port;
            $(containerSelector + ' input[name="db_port"]').val(port).attr('placeholder', port);
        }
    }, 'json');
}

function bindSaveDbPort(dbType, containerSelector, getSidFunc){
    $(containerSelector + ' .btn_save_port').off('click').on('click', function(){
        var sid = 0;
        if (typeof(getSidFunc) === 'function'){
            sid = getSidFunc() || 0;
        }
        var portVal = $(containerSelector + ' input[name="db_port"]').val();
        if (!portVal || isNaN(portVal) || parseInt(portVal) < 1 || parseInt(portVal) > 65535){
            layer.msg('请输入有效的端口号(1-65535)!', {icon: 2});
            return;
        }

        var req_data = {
            name: 'data_query',
            args: JSON.stringify({sid: sid, port: parseInt(portVal)})
        };
        if (dbType === 'mysql') {
            req_data.script = 'sql_mysql';
            req_data.func = 'set_db_port';
        } else if (dbType === 'postgresql') {
            req_data.script = 'sql_postgresql';
            req_data.func = 'set_db_port';
        } else if (dbType === 'redis') {
            req_data.script = 'nosql_redis';
            req_data.func = 'set_db_port';
        } else if (dbType === 'mongodb') {
            req_data.script = 'nosql_mongodb';
            req_data.func = 'set_db_port';
        } else if (dbType === 'memcached') {
            req_data.script = 'nosql_memcached';
            req_data.func = 'set_db_port';
        }

        var loadT = layer.msg('正在保存端口...', { icon: 16, time: 0, shade: 0.3 });
        $.post('/plugins/callback', req_data, function(res){
            layer.close(loadT);
            if (res && res.data){
                var d = res.data;
                layer.msg(d.msg, {icon: d.status ? 1 : 2});
            } else {
                layer.msg('保存端口完成', {icon: 1});
            }
        }, 'json');
    });
}

function mysqlGetSid(){ return $('#mysql select[name=sid]').val() || 'mysql'; }
function pgGetSid(){ return $('#postgresql select[name=sid]').val() || 'pgsql'; }
function redisGetSid(){ return $('#redis select[name=sid]').val() || 'local'; }
function mongodbGetSid(){ return $('#mongodb select[name=sid]').val() || 'local'; }
function memcachedGetSid(){ return $('#memcached select[name=sid]').val() || 'local'; }

function selectTab(tab = 'redis'){
    $('.tab-view-box .tab-con').addClass('hide').removeClass('show').removeClass('w-full');
    $('#'+tab).removeClass('hide').addClass('w-full');
}

function showInstallLayer(){
    $('.mask_layer').css('display','block');
}

function closeInstallLayer(){
    $('.mask_layer').css('display','none');
}

// 全局连接状态字典
var dqConnectionStates = {
    mysql: { connected: false, status: 'disconnected', sid: 'mysql' },
    postgresql: { connected: false, status: 'disconnected', sid: 'pgsql' },
    redis: { connected: false, status: 'disconnected', sid: 'local' },
    mongodb: { connected: false, status: 'disconnected', sid: 'local' },
    memcached: { connected: false, status: 'disconnected', sid: 'local' }
};

// 数据管理专属 DOM 翻译增强器（确保全量元素与控制栏精准多语言适配）
function translateDataQueryDOM($container) {
    if (!$container || $container.length === 0) return;

    // 1. 控制栏文字标签（如 "数据库连接:", "端口:" 等）
    $container.find('.dq-conn-item > span:not(.glyphicon)').each(function() {
        var $sp = $(this);
        if ($sp.children().length > 0) return;
        var orig = $sp.attr('data-i18n-orig');
        if (!orig) {
            orig = $sp.text().trim();
            if (orig) $sp.attr('data-i18n-orig', orig);
        }
        if (orig && orig !== ':') {
            var trans = pt(orig);
            if (trans && trans !== orig) $sp.text(trans);
        }
    });

    // 2. 状态徽章文字与空状态卡片标题/描述
    $container.find('.dq-status-badge .status-text, .empty-title, .empty-desc').each(function() {
        var $el = $(this);
        if ($el.children().length > 0) return;
        var orig = $el.attr('data-i18n-orig');
        if (!orig) {
            orig = $el.text().trim();
            if (orig) $el.attr('data-i18n-orig', orig);
        }
        if (orig) {
            var trans = pt(orig);
            if (trans && trans !== orig) $el.text(trans);
        }
    });

    // 3. 按钮文字、按钮 title 与输入框 placeholder
    $container.find('.btn_sync_servers .btn-text, .btn_create_conn span:not(.glyphicon), .btn_manage_conn span:not(.glyphicon)').each(function() {
        var $el = $(this);
        var orig = $el.attr('data-i18n-orig');
        if (!orig) {
            orig = $el.text().trim();
            if (orig) $el.attr('data-i18n-orig', orig);
        }
        if (orig) {
            var trans = pt(orig);
            if (trans && trans !== orig) $el.text(trans);
        }
    });

    $container.find('button, .btn, input[placeholder]').each(function() {
        var $el = $(this);
        var title = $el.attr('title');
        if (title) {
            var origTitle = $el.attr('data-i18n-title-orig');
            if (!origTitle) {
                origTitle = title;
                $el.attr('data-i18n-title-orig', origTitle);
            }
            var transTitle = pt(origTitle);
            if (transTitle && transTitle !== origTitle) $el.attr('title', transTitle);
        }
        var ph = $el.attr('placeholder');
        if (ph) {
            var origPh = $el.attr('data-i18n-ph-orig');
            if (!origPh) {
                origPh = ph;
                $el.attr('data-i18n-ph-orig', origPh);
            }
            var transPh = pt(origPh);
            if (transPh && transPh !== origPh) $el.attr('placeholder', transPh);
        }
    });

    // 4. 下拉框 optgroup 分组标签
    $container.find('optgroup').each(function() {
        var $og = $(this);
        var origLabel = $og.attr('data-i18n-label-orig');
        if (!origLabel) {
            origLabel = $og.attr('label') || '';
            if (origLabel) $og.attr('data-i18n-label-orig', origLabel);
        }
        if (origLabel) {
            var transLabel = pt(origLabel);
            if (transLabel && transLabel !== origLabel) $og.attr('label', transLabel);
        }
    });

    // 5. 联动全局插件翻译器
    if (window.YfI18n && typeof window.YfI18n.translatePluginDOM === 'function') {
        window.YfI18n.translatePluginDOM($container, 'data_query');
    }
}

// 更新连接状态与 UI 呈现
function updateDbConnectionUI(dbType, status, errorMsg) {
    var state = dqConnectionStates[dbType] || { connected: false, status: 'disconnected', sid: '0' };
    state.status = status;
    state.connected = (status === 'connected');
    dqConnectionStates[dbType] = state;

    var $tab = $('#' + dbType);
    var $badge = $tab.find('.dq-status-badge');
    var $btn = $tab.find('.btn_toggle_conn');
    var $empty = $tab.find('.dq-empty-state');
    var $panel = $tab.find('.dq-data-panel');

    $badge.removeClass('disconnected connecting connected error').addClass(status);
    var statusText = pt('未连接');
    if (status === 'connecting') statusText = pt('连接中...');
    else if (status === 'connected') statusText = pt('已连接');
    else if (status === 'error') statusText = pt('连接失败');
    $badge.find('.status-text').text(statusText);

    // 空状态标题与按钮文案国际化
    var emptyTitles = {
        mysql: pt('当前未连接 MySQL 数据库'),
        postgresql: pt('当前未连接 PostgreSQL 数据库'),
        redis: pt('当前未连接 Redis 数据库'),
        mongodb: pt('当前未连接 MongoDB 数据库'),
        memcached: pt('当前未连接 Memcached 数据库')
    };
    $empty.find('.empty-title').text(emptyTitles[dbType] || pt('当前未连接数据库'));
    $empty.find('.btn_empty_connect').html('<span class="glyphicon glyphicon-flash"></span> ' + pt('立即连接数据库'));

    if (state.connected) {
        $btn.removeClass('btn-success').addClass('btn-danger')
            .html('<span class="glyphicon glyphicon-remove"></span> <span class="btn-text">' + pt('断开') + '</span>');
        $empty.hide();
        $panel.show();
    } else {
        $btn.removeClass('btn-danger').addClass('btn-success')
            .html('<span class="glyphicon glyphicon-flash"></span> <span class="btn-text">' + pt('连接') + '</span>');
        $panel.hide();
        $empty.show();
        if (errorMsg) {
            var isPgDriverErr = (dbType === 'postgresql' && (errorMsg.indexOf('psycopg2') !== -1 || errorMsg.indexOf('驱动') !== -1));
            var descHtml = '<span style="color:#ef4444;"><i class="glyphicon glyphicon-exclamation-sign"></i> ' + pt('连接失败: ') + pt(errorMsg) + '</span>';
            if (isPgDriverErr) {
                descHtml += '<div style="margin-top:14px;"><button class="btn btn-success btn-sm btn_empty_install_pg_driver" style="padding:6px 16px;"><span class="glyphicon glyphicon-download-alt"></span> ' + pt('立即安装驱动并查看日志') + '</button></div>';
            }
            $empty.find('.empty-desc').html(descHtml);
            if (isPgDriverErr) {
                $empty.find('.btn_empty_install_pg_driver').off('click').on('click', function(){
                    showInstallPgDriverDialog();
                });
            }
        } else {
            $empty.find('.empty-desc').text(pt('默认不主动建立网络连接。请确认上方选择的连接配置，然后点击【连接】按钮建立会话。'));
        }
    }

    translateDataQueryDOM($tab);
}

// 通用服务器与自定义连接列表加载
function loadUnifiedServerList(dbType, callback) {
    var req_data = {
        name: 'data_query',
        func: 'getUnifiedServerList',
        script: 'common_db',
        args: JSON.stringify({ db_type: dbType })
    };

    $.post('/plugins/callback', req_data, function(res) {
        var items = (res && res.data && res.data.data) ? res.data.data : [];
        var localGroup = [];
        var remoteGroup = [];
        var defaultVal = '';

        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            if (it.is_default && !defaultVal) {
                defaultVal = it.val;
            }
            if (it.group === 'remote') {
                remoteGroup.push(it);
            } else {
                localGroup.push(it);
            }
        }

        if (!defaultVal && items.length > 0) {
            defaultVal = items[0].val;
        }

        var html = '';
        if (localGroup.length > 0) {
            html += '<optgroup label="' + pt('本地与容器配置') + '">';
            for (var j = 0; j < localGroup.length; j++) {
                var pAttr = localGroup[j].port ? (' data-port="' + localGroup[j].port + '"') : '';
                html += '<option value="' + localGroup[j].val + '"' + pAttr + '>' + localGroup[j].name + '</option>';
            }
            html += '</optgroup>';
        }

        if (remoteGroup.length > 0) {
            html += '<optgroup label="' + pt('已保存连接记录') + '">';
            for (var k = 0; k < remoteGroup.length; k++) {
                var rpAttr = remoteGroup[k].port ? (' data-port="' + remoteGroup[k].port + '"') : '';
                html += '<option value="' + remoteGroup[k].val + '"' + rpAttr + '>' + remoteGroup[k].name + '</option>';
            }
            html += '</optgroup>';
        }

        if (items.length === 0) {
            html = '<option value="0">' + pt('无可用服务器') + '</option>';
        }

        var $tab = $('#' + dbType);
        var $select = $tab.find('select[name=sid]');
        $select.html(html);

        // 优先尝试从 localStorage 还原上次选中的连接
        var lastSid = localStorage.getItem('dq_last_sid_' + dbType);
        if (lastSid && lastSid !== '0' && $select.find('option[value="' + lastSid + '"]').length > 0) {
            $select.val(lastSid);
        } else if (defaultVal) {
            $select.val(defaultVal);
        }

        var currentSid = $select.val();
        // 自动回填端口
        var $selectedOpt = $select.find('option:selected');
        var optPort = $selectedOpt.attr('data-port');
        if (optPort) {
            $tab.find('input[name="db_port"]').val(optPort);
        }
        loadDbPort(dbType, '#' + dbType, currentSid);

        $select.off('change').on('change', function() {
            var selectedSid = $(this).val();
            localStorage.setItem('dq_last_sid_' + dbType, selectedSid);
            var $opt = $(this).find('option:selected');
            var p = $opt.attr('data-port');
            if (p) {
                $tab.find('input[name="db_port"]').val(p);
            }
            loadDbPort(dbType, '#' + dbType, selectedSid);
            // 切换连接时重置为未连接状态
            updateDbConnectionUI(dbType, 'disconnected');
        });

        translateDataQueryDOM($tab);

        if (typeof(callback) === 'function') {
            callback(items);
        }
    }, 'json');
}

// 统一绑定连接栏事件
function bindConnectionBar(dbType, connectFunc, disconnectFunc) {
    var $tab = $('#' + dbType);

    // 切换连接 / 断开按钮
    $tab.find('.btn_toggle_conn').off('click').on('click', function() {
        if (dqConnectionStates[dbType] && dqConnectionStates[dbType].connected) {
            if (typeof(disconnectFunc) === 'function') disconnectFunc();
        } else {
            if (typeof(connectFunc) === 'function') connectFunc();
        }
    });

    // Empty State 卡片上的连接按钮
    $tab.find('.btn_empty_connect').off('click').on('click', function() {
        if (typeof(connectFunc) === 'function') connectFunc();
    });

    // ➕ 新建连接
    $tab.find('.btn_create_conn').off('click').on('click', function() {
        openConnectionModal(dbType, null, function(saved) {
            loadUnifiedServerList(dbType, function() {
                if (saved && saved.id) {
                    $tab.find('select[name=sid]').val('conn_' + saved.id).trigger('change');
                }
            });
        });
    });

    // ⚙️ 管理连接
    $tab.find('.btn_manage_conn').off('click').on('click', function() {
        openManageConnectionsModal(dbType);
    });

    // 端口保存
    $tab.find('.btn_save_port').off('click').on('click', function() {
        var portVal = $tab.find('input[name="db_port"]').val();
        if (!portVal || isNaN(portVal) || parseInt(portVal) < 1 || parseInt(portVal) > 65535) {
            layer.msg(pt('请输入有效的端口号(1-65535)!'), { icon: 2 });
            return;
        }

        var loadT = layer.msg(pt('正在保存端口...'), { icon: 16, time: 0, shade: 0.3 });
        $.post('/plugins/callback', {
            name: 'data_query',
            func: 'setDbPort',
            script: 'common_db',
            args: JSON.stringify({ db_type: dbType, port: parseInt(portVal) })
        }, function(res) {
            layer.close(loadT);
            var d = res ? res.data : null;
            if (d && d.status) {
                layer.msg(d.msg || pt('保存端口完成'), { icon: 1 });
            } else {
                layer.msg((d && d.msg) ? d.msg : pt('保存端口完成'), { icon: 1 });
            }
        }, 'json');
    });
}

// 打开新建/编辑连接模态框 (Navicat 风格)
function openConnectionModal(defaultDbType, editId, onSavedCallback) {
    var isEdit = !!editId;
    var title = isEdit ? pt('编辑数据库连接') : pt('新建数据库连接');

    var modalHtml = '<div class="dq-modal-form">' +
        '<div class="dq-form-row">' +
        '   <label><span style="color:#ef4444;">*</span> ' + pt('连接名称') + ':</label>' +
        '   <div class="form-con"><input type="text" id="dq_conn_name" placeholder="' + pt('例如: 生产主库、测试环境') + '" class="bt-input-text"></div>' +
        '</div>' +
        '<div class="dq-form-row">' +
        '   <label><span style="color:#ef4444;">*</span> ' + pt('数据库类型') + ':</label>' +
        '   <div class="form-con">' +
        '       <select id="dq_conn_dbtype" class="bt-input-text"' + (isEdit ? ' disabled' : '') + '>' +
        '           <option value="mysql">MySQL</option>' +
        '           <option value="postgresql">PostgreSQL</option>' +
        '           <option value="redis">Redis</option>' +
        '           <option value="mongodb">MongoDB</option>' +
        '           <option value="memcached">Memcached</option>' +
        '       </select>' +
        '   </div>' +
        '</div>' +
        '<div class="dq-form-row">' +
        '   <label><span style="color:#ef4444;">*</span> ' + pt('主机地址') + ':</label>' +
        '   <div class="form-con"><input type="text" id="dq_conn_host" value="127.0.0.1" placeholder="127.0.0.1 或 域名" class="bt-input-text"></div>' +
        '</div>' +
        '<div class="dq-form-row">' +
        '   <label><span style="color:#ef4444;">*</span> ' + pt('端口') + ':</label>' +
        '   <div class="form-con"><input type="number" id="dq_conn_port" value="3306" placeholder="3306" class="bt-input-text"></div>' +
        '</div>' +
        '<div class="dq-form-row" id="row_dq_conn_username">' +
        '   <label>' + pt('用户名') + ':</label>' +
        '   <div class="form-con"><input type="text" id="dq_conn_username" placeholder="root / postgres" class="bt-input-text"></div>' +
        '</div>' +
        '<div class="dq-form-row" id="row_dq_conn_password">' +
        '   <label>' + pt('密码') + ':</label>' +
        '   <div class="form-con">' +
        '       <input type="password" id="dq_conn_password" placeholder="' + (isEdit ? pt('留空或保留******不修改') : pt('请输入密码')) + '" class="bt-input-text">' +
        '       <span class="glyphicon glyphicon-eye-open dq-pwd-toggle" title="' + pt('显示/隐藏密码') + '"></span>' +
        '   </div>' +
        '</div>' +
        '<div class="dq-form-row" id="row_dq_conn_authdb">' +
        '   <label>' + pt('初始/认证库') + ':</label>' +
        '   <div class="form-con"><input type="text" id="dq_conn_authdb" placeholder="' + pt('选填，可留空 (如 postgres / admin)') + '" class="bt-input-text"></div>' +
        '</div>' +
        '<div class="dq-form-row">' +
        '   <label>' + pt('备注说明') + ':</label>' +
        '   <div class="form-con"><input type="text" id="dq_conn_notes" placeholder="' + pt('选填备注') + '" class="bt-input-text"></div>' +
        '</div>' +
        '<div style="display:flex; justify-content:space-between; align-items:center; margin-top:20px; padding-top:15px; border-top:1px solid #e2e8f0;">' +
        '   <button type="button" class="btn btn-default btn-sm" id="btn_dq_test_conn"><span class="glyphicon glyphicon-flash"></span> ' + pt('测试连接') + '</button>' +
        '   <div>' +
        '       <button type="button" class="btn btn-default btn-sm mr5" id="btn_dq_cancel_conn">' + pt('取消') + '</button>' +
        '       <button type="button" class="btn btn-success btn-sm" id="btn_dq_save_conn">' + pt('保存') + '</button>' +
        '   </div>' +
        '</div>' +
        '<div id="dq_test_result" style="margin-top:10px; font-size:12px; display:none;"></div>' +
        '</div>';

    var layerIdx = layer.open({
        type: 1,
        title: title,
        area: ['520px', 'auto'],
        closeBtn: 1,
        shadeClose: false,
        content: modalHtml,
        success: function(layero, index) {
            var defaultPorts = { mysql: 3306, postgresql: 5432, redis: 6379, mongodb: 27017, memcached: 11211 };

            if (!isEdit && defaultDbType) {
                $('#dq_conn_dbtype').val(defaultDbType);
                $('#dq_conn_port').val(defaultPorts[defaultDbType] || 3306);
            }

            // 密码显示/隐藏切换
            layero.find('.dq-pwd-toggle').on('click', function() {
                var $pwd = $('#dq_conn_password');
                var isPassword = $pwd.attr('type') === 'password';
                $pwd.attr('type', isPassword ? 'text' : 'password');
                $(this).toggleClass('glyphicon-eye-open glyphicon-eye-close');
            });

            // 切换类型时自动带出默认端口
            $('#dq_conn_dbtype').on('change', function() {
                var t = $(this).val();
                $('#dq_conn_port').val(defaultPorts[t] || 3306);
            });

            // 如果是编辑已有连接，回填数据
            if (isEdit) {
                var loadT = layer.msg(pt('正在加载连接详情...'), { icon: 16, time: 0, shade: 0.3 });
                $.post('/plugins/callback', {
                    name: 'data_query',
                    func: 'getConnection',
                    script: 'common_db',
                    args: JSON.stringify({ id: editId })
                }, function(res) {
                    layer.close(loadT);
                    if (res && res.data && res.data.status && res.data.data) {
                        var c = res.data.data;
                        $('#dq_conn_name').val(c.name);
                        $('#dq_conn_dbtype').val(c.db_type);
                        $('#dq_conn_host').val(c.host);
                        $('#dq_conn_port').val(c.port);
                        $('#dq_conn_username').val(c.username);
                        $('#dq_conn_password').val(c.password);
                        $('#dq_conn_authdb').val(c.auth_db);
                        $('#dq_conn_notes').val(c.notes);
                    } else {
                        layer.msg(pt('加载连接失败'), { icon: 2 });
                    }
                }, 'json');
            }

            // 测试连接按钮
            $('#btn_dq_test_conn').on('click', function() {
                var host = $('#dq_conn_host').val().trim();
                var port = $('#dq_conn_port').val().trim();
                var db_type = $('#dq_conn_dbtype').val();
                var username = $('#dq_conn_username').val().trim();
                var password = $('#dq_conn_password').val();
                var auth_db = $('#dq_conn_authdb').val().trim();

                if (!host) {
                    layer.msg(pt('请输入主机地址'), { icon: 2 });
                    return;
                }

                var $resBox = $('#dq_test_result');
                $resBox.show().html('<span style="color:#64748b;"><span class="glyphicon glyphicon-refresh"></span> ' + pt('正在测试连通性...') + '</span>');

                $.post('/plugins/callback', {
                    name: 'data_query',
                    func: 'testConnection',
                    script: 'common_db',
                    args: JSON.stringify({
                        id: isEdit ? editId : null,
                        db_type: db_type,
                        host: host,
                        port: port,
                        username: username,
                        password: password,
                        auth_db: auth_db
                    })
                }, function(res) {
                    var d = res ? res.data : null;
                    if (d && d.status) {
                        $resBox.html('<span style="color:#16a34a;"><span class="glyphicon glyphicon-ok-sign"></span> ' + d.msg + '</span>');
                    } else {
                        var emsg = (d && d.msg) ? d.msg : pt('连接测试失败');
                        $resBox.html('<span style="color:#dc2626;"><span class="glyphicon glyphicon-remove-sign"></span> ' + emsg + '</span>');
                    }
                }, 'json');
            });

            // 取消按钮
            $('#btn_dq_cancel_conn').on('click', function() {
                layer.close(layerIdx);
            });

            // 保存按钮
            $('#btn_dq_save_conn').on('click', function() {
                var name = $('#dq_conn_name').val().trim();
                var db_type = $('#dq_conn_dbtype').val();
                var host = $('#dq_conn_host').val().trim();
                var port = $('#dq_conn_port').val().trim();
                var username = $('#dq_conn_username').val().trim();
                var password = $('#dq_conn_password').val();
                var auth_db = $('#dq_conn_authdb').val().trim();
                var notes = $('#dq_conn_notes').val().trim();

                if (!name) {
                    layer.msg(pt('请输入连接名称'), { icon: 2 });
                    return;
                }
                if (!host) {
                    layer.msg(pt('请输入主机地址'), { icon: 2 });
                    return;
                }
                if (!port) {
                    layer.msg(pt('请输入有效端口'), { icon: 2 });
                    return;
                }

                var loadSave = layer.msg(pt('正在保存连接...'), { icon: 16, time: 0, shade: 0.3 });
                $.post('/plugins/callback', {
                    name: 'data_query',
                    func: 'saveConnection',
                    script: 'common_db',
                    args: JSON.stringify({
                        id: isEdit ? editId : null,
                        name: name,
                        db_type: db_type,
                        host: host,
                        port: port,
                        username: username,
                        password: password,
                        auth_db: auth_db,
                        notes: notes
                    })
                }, function(res) {
                    layer.close(loadSave);
                    var d = res ? res.data : null;
                    if (d && d.status) {
                        layer.msg(d.msg || pt('保存成功'), { icon: 1 });
                        layer.close(layerIdx);
                        if (typeof(onSavedCallback) === 'function') {
                            onSavedCallback(d.data);
                        }
                    } else {
                        layer.msg((d && d.msg) ? d.msg : pt('保存连接失败'), { icon: 2 });
                    }
                }, 'json');
            });
        }
    });
}

// 打开连接管理列表模态框 (Navicat 风格)
function openManageConnectionsModal(defaultDbType) {
    var manageHtml = '<div style="padding: 15px 20px;">' +
        '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">' +
        '   <div style="font-size:13px; font-weight:600; color:#334155;">' + pt('已保存的数据库连接记录') + '</div>' +
        '   <button class="btn btn-success btn-xs" id="btn_modal_add_conn"><span class="glyphicon glyphicon-plus"></span> ' + pt('新建连接') + '</button>' +
        '</div>' +
        '<div class="divtable">' +
        '   <table class="table table-hover">' +
        '       <thead>' +
        '           <tr>' +
        '               <th>' + pt('名称') + '</th>' +
        '               <th>' + pt('类型') + '</th>' +
        '               <th>' + pt('主机:端口') + '</th>' +
        '               <th>' + pt('用户名') + '</th>' +
        '               <th>' + pt('备注') + '</th>' +
        '               <th style="text-align:right;">' + pt('操作') + '</th>' +
        '           </tr>' +
        '       </thead>' +
        '       <tbody id="dq_conn_list_tbody">' +
        '           <tr><td colspan="6" style="text-align:center;color:#999;padding:20px;">' + pt('正在加载连接列表...') + '</td></tr>' +
        '       </tbody>' +
        '   </table>' +
        '</div>' +
        '</div>';

    var layerIdx = layer.open({
        type: 1,
        title: pt('连接管理器 (Navicat 式)'),
        area: ['680px', '460px'],
        closeBtn: 1,
        shadeClose: false,
        content: manageHtml,
        success: function(layero, index) {
            function reloadList() {
                $.post('/plugins/callback', {
                    name: 'data_query',
                    func: 'getConnectionList',
                    script: 'common_db',
                    args: JSON.stringify({ db_type: defaultDbType || '' })
                }, function(res) {
                    var items = (res && res.data && res.data.data) ? res.data.data : [];
                    if (items.length === 0) {
                        $('#dq_conn_list_tbody').html('<tr><td colspan="6" style="text-align:center;color:#94a3b8;padding:25px;">' + pt('暂无保存的远程连接，请点击右上角新建') + '</td></tr>');
                        return;
                    }
                    var rows = '';
                    for (var i = 0; i < items.length; i++) {
                        var c = items[i];
                        rows += '<tr>' +
                            '<td><b>' + c.name + '</b></td>' +
                            '<td><span class="badge" style="background:#e2e8f0;color:#334155;font-weight:normal;">' + c.db_type + '</span></td>' +
                            '<td>' + c.host + ':' + c.port + '</td>' +
                            '<td>' + (c.username || '-') + '</td>' +
                            '<td><span style="color:#64748b;font-size:11px;">' + (c.notes || '-') + '</span></td>' +
                            '<td style="text-align:right;white-space:nowrap;">' +
                            '   <a class="btlink btn-test-c mr5" data-id="' + c.id + '" href="javascript:;">' + pt('测试') + '</a>' +
                            '   <a class="btlink btn-edit-c mr5" data-id="' + c.id + '" href="javascript:;">' + pt('编辑') + '</a>' +
                            '   <a class="btlink btn-del-c" data-id="' + c.id + '" data-name="' + c.name + '" href="javascript:;" style="color:#ef4444;">' + pt('删除') + '</a>' +
                            '</td>' +
                            '</tr>';
                    }
                    $('#dq_conn_list_tbody').html(rows);

                    // 绑定行操作
                    layero.find('.btn-test-c').off('click').on('click', function() {
                        var id = $(this).data('id');
                        var loadT = layer.msg(pt('正在测试连接...'), { icon: 16, time: 0, shade: 0.3 });
                        $.post('/plugins/callback', {
                            name: 'data_query',
                            func: 'testConnection',
                            script: 'common_db',
                            args: JSON.stringify({ id: id })
                        }, function(tRes) {
                            layer.close(loadT);
                            var d = tRes ? tRes.data : null;
                            if (d && d.status) {
                                layer.msg(d.msg, { icon: 1, time: 3000 });
                            } else {
                                layer.msg((d && d.msg) ? d.msg : pt('测试失败'), { icon: 2, time: 3500 });
                            }
                        }, 'json');
                    });

                    layero.find('.btn-edit-c').off('click').on('click', function() {
                        var id = $(this).data('id');
                        openConnectionModal(defaultDbType, id, function() {
                            reloadList();
                            loadUnifiedServerList(defaultDbType);
                        });
                    });

                    layero.find('.btn-del-c').off('click').on('click', function() {
                        var id = $(this).data('id');
                        var cname = $(this).data('name');
                        layer.confirm(pt('确定要删除连接配置【%s】吗？', cname), { icon: 3, title: pt('删除确认') }, function(cIdx) {
                            layer.close(cIdx);
                            $.post('/plugins/callback', {
                                name: 'data_query',
                                func: 'deleteConnection',
                                script: 'common_db',
                                args: JSON.stringify({ id: id })
                            }, function(delRes) {
                                var d = delRes ? delRes.data : null;
                                if (d && d.status) {
                                    layer.msg(pt('删除成功'), { icon: 1 });
                                    reloadList();
                                    loadUnifiedServerList(defaultDbType);
                                } else {
                                    layer.msg((d && d.msg) ? d.msg : pt('删除失败'), { icon: 2 });
                                }
                            }, 'json');
                        });
                    });
                }, 'json');
            }

            reloadList();

            $('#btn_modal_add_conn').on('click', function() {
                openConnectionModal(defaultDbType, null, function() {
                    reloadList();
                    loadUnifiedServerList(defaultDbType);
                });
            });
        }
    });
}

function initTabFunc(tab){
    switch(tab){
        case 'redis':initTabRedis();break;
        case 'mongodb':initTabMongodb();break;
        case 'memcached':initTabMemcached();break;
        case 'mysql':initTabMySQL();break;
        case 'postgresql':initTabPostgresql();break;
        default:initTabRedis();break;
    }
}

// ==========================================
// 🔄 服务器同步与配置覆盖确认模态框
// ==========================================
function openSyncServersModal() {
    var loadT = layer.msg(pt('正在扫描本地与容器数据库配置...'), { icon: 16, time: 0, shade: 0.3 });
    var req_data = {
        name: 'data_query',
        func: 'previewLocalSyncDiff',
        script: 'common_db',
        args: JSON.stringify({})
    };

    $.post('/plugins/callback', req_data, function(res) {
        layer.close(loadT);
        var d = res ? res.data : null;
        if (!d || !d.status) {
            layer.msg((d && d.msg) ? d.msg : pt('扫描服务配置失败'), { icon: 2 });
            return;
        }
        var info = d.data || {};
        var items = info.items || [];
        if (items.length === 0) {
            layer.msg(pt('未检测到任何本地数据库或容器服务'), { icon: 7 });
            return;
        }
        renderSyncServersDialog(items);
    }, 'json').fail(function() {
        layer.close(loadT);
        layer.msg(pt('网络或服务请求超时'), { icon: 2 });
    });
}

function renderSyncServersDialog(items) {
    var hasDiff = items.some(function(it) {
        return it.status === 'new' || it.status === 'modified';
    });

    var rowsHtml = '';
    for (var i = 0; i < items.length; i++) {
        var it = items[i];
        var isChecked = (it.status === 'new' || it.status === 'modified') ? 'checked' : '';
        var badgeHtml = '';
        if (it.status === 'new') {
            badgeHtml = '<span class="dq-badge-new">' + pt('新增') + '</span>';
        } else if (it.status === 'modified') {
            badgeHtml = '<span class="dq-badge-modified">' + pt('变更') + '</span>';
        } else {
            badgeHtml = '<span class="dq-badge-identical">' + pt('一致') + '</span>';
        }

        var oldStr = '-';
        if (it.old_config) {
            oldStr = it.old_config.host + ':' + it.old_config.port;
            if (it.old_config.username) oldStr += ' (' + it.old_config.username + ')';
        }

        var newStr = it.new_config.host + ':' + it.new_config.port;
        if (it.new_config.username) newStr += ' (' + it.new_config.username + ')';

        var diffStr = '';
        if (it.diff_details && it.diff_details.length > 0) {
            diffStr = '<span class="dq-sync-diff-text">' + it.diff_details.join('; ') + '</span>';
        } else {
            diffStr = '<span style="color:#94a3b8;">' + pt('无变动') + '</span>';
        }

        var connNameDisplay = it.target_name || it.name;
        if (it.name && it.target_name && it.name !== it.target_name) {
            connNameDisplay = it.name + ' ➔ ' + it.target_name;
        }

        rowsHtml += '<tr data-idx="' + i + '">' +
            '<td style="text-align:center;"><input type="checkbox" class="sync_item_chk" data-idx="' + i + '" ' + isChecked + '></td>' +
            '<td><span style="text-transform:uppercase; font-weight:600; color:#475569;">' + it.db_type + '</span></td>' +
            '<td>' + connNameDisplay + '</td>' +
            '<td>' + badgeHtml + '</td>' +
            '<td>' + oldStr + '</td>' +
            '<td style="font-weight:500;">' + newStr + '</td>' +
            '<td>' + diffStr + '</td>' +
            '</tr>';
    }

    var tipText = hasDiff 
        ? pt('检测到本地数据库配置与已保存配置存在差异。请在下方勾选需要覆盖或导入的配置（未勾选项将保持不变）：')
        : pt('所有本地数据库配置均已与当前保存信息保持一致。您可以按需重新同步：');

    var dialogHtml = '<div class="dq-sync-dialog">' +
        '<div class="sync-tip-box">' +
        '   <i class="glyphicon glyphicon-info-sign" style="color:#20a53a; margin-right:4px;"></i> ' + tipText +
        '</div>' +
        '<div class="divtable" style="max-height: 270px; overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 4px;">' +
        '   <table class="table table-hover dq-sync-table" style="margin-bottom:0;">' +
        '       <thead>' +
        '           <tr>' +
        '               <th width="40" style="text-align:center;"><input type="checkbox" id="sync_select_all" ' + (hasDiff ? 'checked' : '') + '></th>' +
        '               <th>' + pt('类型') + '</th>' +
        '               <th>' + pt('连接名称') + '</th>' +
        '               <th>' + pt('状态') + '</th>' +
        '               <th>' + pt('当前保存配置') + '</th>' +
        '               <th>' + pt('探测最新配置') + '</th>' +
        '               <th>' + pt('差异对比') + '</th>' +
        '           </tr>' +
        '       </thead>' +
        '       <tbody>' + rowsHtml + '</tbody>' +
        '   </table>' +
        '</div>' +
        '<div style="display:flex; justify-content:space-between; align-items:center; margin-top:15px;">' +
        '   <div>' +
        '       <a href="javascript:;" id="btn_sync_select_diff" class="btlink" style="margin-right:12px; font-size:12px;">' + pt('仅选有差异项') + '</a>' +
        '       <a href="javascript:;" id="btn_sync_clear_all" class="btlink" style="font-size:12px; color:#64748b;">' + pt('取消全选') + '</a>' +
        '   </div>' +
        '   <div>' +
        '       <button type="button" class="btn btn-default btn-sm btn_cancel_sync mr5">' + pt('取消') + '</button>' +
        '       <button type="button" class="btn btn-success btn-sm btn_confirm_sync">' +
        '           <span class="glyphicon glyphicon-ok"></span> ' + pt('确认覆盖并同步') +
        '       </button>' +
        '   </div>' +
        '</div>' +
        '</div>';

    var syncLayerIndex = layer.open({
        type: 1,
        title: '<span class="glyphicon glyphicon-refresh" style="color:#20a53a; margin-right:6px;"></span>' + pt('服务器同步与配置覆盖确认'),
        area: ['760px', '460px'],
        closeBtn: 2,
        shadeClose: false,
        content: dialogHtml,
        success: function(layero) {
            // 全选联动
            $('#sync_select_all').on('change', function() {
                var checked = $(this).prop('checked');
                $('.sync_item_chk').prop('checked', checked);
            });

            $('#btn_sync_select_diff').on('click', function() {
                $('.sync_item_chk').each(function() {
                    var idx = parseInt($(this).attr('data-idx'));
                    var it = items[idx];
                    $(this).prop('checked', it.status === 'new' || it.status === 'modified');
                });
            });

            $('#btn_sync_clear_all').on('click', function() {
                $('.sync_item_chk').prop('checked', false);
                $('#sync_select_all').prop('checked', false);
            });

            layero.find('.btn_cancel_sync').on('click', function() {
                layer.close(syncLayerIndex);
            });

            layero.find('.btn_confirm_sync').on('click', function() {
                var selected = [];
                $('.sync_item_chk:checked').each(function() {
                    var idx = parseInt($(this).attr('data-idx'));
                    selected.push(items[idx]);
                });

                if (selected.length === 0) {
                    layer.msg(pt('请至少选择一项需要同步的配置'), { icon: 7 });
                    return;
                }

                var applyingLoad = layer.msg(pt('正在应用配置覆盖并同步...'), { icon: 16, time: 0, shade: 0.3 });
                $.post('/plugins/callback', {
                    name: 'data_query',
                    func: 'applyLocalSync',
                    script: 'common_db',
                    args: JSON.stringify({ sync_items: selected })
                }, function(resp) {
                    layer.close(applyingLoad);
                    var d = resp ? resp.data : null;
                    if (d && d.status) {
                        layer.close(syncLayerIndex);
                        layer.msg(d.msg || pt('同步完成'), { icon: 1, time: 2000 });
                        // 重新加载当前活动 Tab 的连接列表
                        var curTab = $('#cutTab .tabs-item.active').data('name') || 'mysql';
                        loadUnifiedServerList(curTab);
                    } else {
                        layer.msg((d && d.msg) ? d.msg : pt('应用配置同步失败'), { icon: 2 });
                    }
                }, 'json').fail(function() {
                    layer.close(applyingLoad);
                    layer.msg(pt('网络异常，请重试'), { icon: 2 });
                });
            });

            if (window.YfI18n && typeof window.YfI18n.translatePluginDOM === 'function') {
                window.YfI18n.translatePluginDOM(layero, 'data_query');
            }
        }
    });
}

function initDataQuery(){
    var tab = $('#cutTab .tabs-item.active').data('name');
    initTabFunc(tab);
    $('#cutTab .tabs-item').on('click', function(){
        var tab = $(this).data('name');
        $('#cutTab .tabs-item').removeClass('active');
        $(this).addClass('active');
        selectTab(tab);
        initTabFunc(tab);
        translateDataQueryDOM($('.main-content'));
    });

    // 绑定右上角服务器同步按钮
    $('.btn_sync_servers').off('click').on('click', function(){
        openSyncServersModal();
    });

    translateDataQueryDOM($('.main-content'));
}

function connectRedis(){
    updateDbConnectionUI('redis', 'connecting');
    redisGetList(function(success, errMsg){
        if (success){
            updateDbConnectionUI('redis', 'connected');
            layer.msg(pt('Redis 数据库连接成功！'), {icon: 1, time: 2000});
        } else {
            updateDbConnectionUI('redis', 'error', errMsg || pt('无法连接 Redis，请确认服务已启动或密码正确'));
        }
    });
}

function disconnectRedis(){
    updateDbConnectionUI('redis', 'disconnected');
    layer.msg(pt('已断开 Redis 连接'), {icon: 1, time: 1500});
}

function initTabRedis(){
    loadUnifiedServerList('redis', function(){
        updateDbConnectionUI('redis', dqConnectionStates['redis'].connected ? 'connected' : 'disconnected');
    });

    bindConnectionBar('redis', connectRedis, disconnectRedis);

    $('#redis_add_key').off('click').on('click', function(){
        redisAdd();
    });

    $('#redis_ksearch').off('click').on('keyup', function(e){
        if (e.keyCode == 13){
            var val = $(this).val();
            if (val == ''){
                layer.msg(pt('搜索不能为空!'),{icon:7});
                return;
            }
            redisGetKeyList(1, val);
        }
    });

    $('#redis_ksearch_span').off('click').on('click', function(){
        var val = $('#redis_ksearch').val();
        if (val == ''){
            layer.msg(pt('搜索不能为空!'),{icon:7});
            return;
        }
        redisGetKeyList(1, val);
    });

    $('#redis_batch_del').off('click').on('click', function(){
        redisBatchDel();
    });

    $('#redis_clear_all').off('click').on('click', function(){
        redisBatchClear();
    });

    readerTableChecked();
}

function connectMongodb(){
    updateDbConnectionUI('mongodb', 'connecting');
    mongodbGetList(function(success, errMsg){
        if (success){
            updateDbConnectionUI('mongodb', 'connected');
            layer.msg(pt('MongoDB 数据库连接成功！'), {icon: 1, time: 2000});
        } else {
            updateDbConnectionUI('mongodb', 'error', errMsg || pt('无法连接 MongoDB，请确认服务状态与认证配置'));
        }
    });
}

function disconnectMongodb(){
    updateDbConnectionUI('mongodb', 'disconnected');
    layer.msg(pt('已断开 MongoDB 连接'), {icon: 1, time: 1500});
}

function initTabMongodb(){
    loadUnifiedServerList('mongodb', function(){
        updateDbConnectionUI('mongodb', dqConnectionStates['mongodb'].connected ? 'connected' : 'disconnected');
    });

    bindConnectionBar('mongodb', connectMongodb, disconnectMongodb);

    $('.mongodb_find').off('click').on('click', function(){
        mongodbGetDataList(1);
    });

    $('.mongodb_refresh').off('click').on('click', function(){
        mongodbGetDataList(1);
    });
}

function connectMemcached(){
    updateDbConnectionUI('memcached', 'connecting');
    memcachedGetList(function(success, errMsg){
        if (success){
            updateDbConnectionUI('memcached', 'connected');
            layer.msg(pt('Memcached 连接成功！'), {icon: 1, time: 2000});
        } else {
            updateDbConnectionUI('memcached', 'error', errMsg || pt('无法连接 Memcached 服务'));
        }
    });
}

function disconnectMemcached(){
    updateDbConnectionUI('memcached', 'disconnected');
    layer.msg(pt('已断开 Memcached 连接'), {icon: 1, time: 1500});
}

function initTabMemcached(){
    loadUnifiedServerList('memcached', function(){
        updateDbConnectionUI('memcached', dqConnectionStates['memcached'].connected ? 'connected' : 'disconnected');
    });

    bindConnectionBar('memcached', connectMemcached, disconnectMemcached);

    $('#memcached_add_key').off('click').on('click', function(){
        memcachedAdd();
    });

    $('#memcached_clear_all').off('click').on('click', function(){
        var sid = memcachedGetSid();
        memPostCB('clear',{'sid':sid} ,function(rdata){
            showMsg(rdata.data.msg,function(){
                if (rdata.data.status){
                    memcachedGetList();
                }
            },{icon: rdata.data.status ? 1 : 2}, 2000);
        });
    });

    $('#memcached_ksearch').off('click').on('keyup', function(e){
        if (e.keyCode == 13){
            var val = $(this).val();
            if (val == ''){
                layer.msg(pt('搜索不能为空!'),{icon:7});
                return;
            }
            memcachedGetKeyList(1);
        }
    });

    $('#memcached_ksearch_span').off('click').on('click', function(){
        var val = $('#memcached_ksearch').val();
        if (val == ''){
            layer.msg(pt('搜索不能为空!'),{icon:7});
            return;
        }
        memcachedGetKeyList(1);
    });

    $('#memcached_batch_del').off('click').on('click', function(){
        memcachedBatchDel();
    });
}

var mysql_timer = null;

function connectMySQL(){
    updateDbConnectionUI('mysql', 'connecting');
    mysqlGetDbList(function(success, errMsg){
        if (success){
            updateDbConnectionUI('mysql', 'connected');
            layer.msg(pt('MySQL 数据库连接成功！'), {icon: 1, time: 2000});
            mysqlProcessList();

            clearInterval(mysql_timer);    
            mysql_timer = setInterval(function(){
                var fname = $('#cutTab .tab-list .active').data('name');
                if (fname != 'mysql' || !dqConnectionStates['mysql'].connected){
                    clearInterval(mysql_timer);
                    return;
                }
                var sid = mysqlGetSid();
                if (sid === undefined || sid === null) {
                    return;
                }
                var name = $('#mysql_list_tab .tab-nav span.on').data('name');
                mysqlRunMysqlTab(name);
            }, 3000);
        } else {
            updateDbConnectionUI('mysql', 'error', errMsg || pt('连接失败，请检查配置与服务状态'));
        }
    });
}

function disconnectMySQL(){
    clearInterval(mysql_timer);
    updateDbConnectionUI('mysql', 'disconnected');
    layer.msg(pt('已断开 MySQL 连接'), {icon: 1, time: 1500});
}

function initTabMySQL(){
    loadUnifiedServerList('mysql', function(){
        updateDbConnectionUI('mysql', dqConnectionStates['mysql'].connected ? 'connected' : 'disconnected');
    });

    bindConnectionBar('mysql', connectMySQL, disconnectMySQL);

    $('#mysql_list_tab .tab-nav span').off('click').on('click', function(){
        $('#mysql_list_tab .tab-nav span').removeClass('on');
        $(this).addClass('on');
        var name = $(this).data('name');
        mysqlRunMysqlTab(name);
    });

    $('#mysql_find').off('click').on('click', function(){
        mysqlGetDataList(1);
    });

    mysqlCommonFunc();
}

function dqEscapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function mysqlCommonFuncMysqlNSQL(){
    var _t = (typeof pt === 'function') ? pt : function(k){ return k; };
    function renderSQL(){
        var sid = mysqlGetSid();
        var filter_db = $('#filter_db').is(':checked');
        myPostCBN('get_topn_list',{'sid':sid,'filter_db':filter_db ? 'yes':'no'} ,function(rdata){
            var data = rdata.data;
            if (data['status']){
                var items = data.data;
                var tbody = '';
                for (var i = 0; i < items.length; i++) {
                    var t = '<tr>';
                    t += '<td class="dq-sql-cell">' + dqEscapeHtml(items[i].query) + '</td>';
                    t += '<td>' + dqEscapeHtml(items[i].db) + '</td>';
                    t += '<td>' + dqEscapeHtml(items[i].last_seen) + '</td>';
                    t += '<td>' + dqEscapeHtml(items[i].exec_count) + '</td>';
                    t += '<td>' + dqEscapeHtml(items[i].max_latency) + '</td>';
                    t += '<td>' + dqEscapeHtml(items[i].avg_latency) + '</td>';
                    t += '</tr>';
                    tbody += t;
                }
                $('#topn_list tbody').html(tbody);
            } else {
                layer.msg(data.msg,{icon:2});
            }
        });
    }

    var sql_timer = null;
    layer.open({
        type: 1,
        title: _t("查询执行次数最频繁的前N条SQL语句"),
        area: ['1200px', '560px'],
        closeBtn: 1,
        shadeClose: false,
        content: '<div class="bt-form dq-common-dialog">\
            <div class="dq-common-header clearfix">\
                <div class="mr20 pull-left" style="border-right: 1px solid #e2e8f0; padding-right: 20px;">\
                    <div class="ss-text pull-left">\
                        <em>' + _t('实时监控') + '</em>\
                        <div class="ssh-item">\
                            <input class="btswitch btswitch-ios" id="real_time_monitoring" type="checkbox">\
                            <label id="real_time_label" class="btswitch-btn" for="real_time_monitoring"></label>\
                        </div>\
                    </div>\
                    <div class="ss-text pull-left" style="padding-left:10px;">\
                        <em>' + _t('过滤数据库') + '</em>\
                        <div class="ssh-item">\
                            <input class="btswitch btswitch-ios" id="filter_db" type="checkbox">\
                            <label class="btswitch-btn" for="filter_db"></label>\
                        </div>\
                    </div>\
                </div>\
            </div>\
            <div class="dq-common-table-wrap">\
                <table class="table table-hover dq-common-table" id="topn_list">\
                    <thead>\
                        <th>SQL</th>\
                        <th style="width:110px;">' + _t('数据名') + '</th>\
                        <th style="width:160px;">' + _t('最近时间') + '</th>\
                        <th style="width:90px;">' + _t('总次数') + '</th>\
                        <th style="width:100px;">' + _t('最大时间') + '</th>\
                        <th style="width:100px;">' + _t('平均时间') + '</th>\
                    </thead>\
                    <tbody></tbody>\
                </table>\
            </div>\
        </div>',
        success:function(i,l){
            renderSQL();

            $('#real_time_label').on('click', function(){
                sql_timer = setInterval(function(){
                    var t = $('#real_time_monitoring').is(':checked');
                    if (t){
                        renderSQL();
                    } else{
                        clearInterval(sql_timer);
                    }
                }, 3000);
            });
        },
        end: function(){
            if (sql_timer) clearInterval(sql_timer);
        }
    });
}

function mysqlCommonFuncMysqlNet(){
    var _t = (typeof pt === 'function') ? pt : function(k){ return k; };
    function renderSQL(){
        var sid = mysqlGetSid();
        myPostCBN('get_net_list',{'sid':sid} ,function(rdata){
            var data = rdata.data;
            if (data['status']){
                var items = data.data;
                var tbody = '';
                for (var i = 0; i < items.length; i++) {
                    var t = '<tr>';
                    t += '<td>'+dqEscapeHtml(items[i]['current_time'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['select'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['insert'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['update'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['delete'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['conn'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['max_conn'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['recv_mbps'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['send_mbps'])+'</td>';
                    t += '</tr>';
                    tbody += t;
                }
                $('#net_list tbody').html(tbody);
            } else {
                layer.msg(data.msg,{icon:2});
            }
        });
    }

    var sql_timer = null;
    layer.open({
        type: 1,
        title: _t("MySQL服务器的QPS/TPS/网络带宽指标"),
        area: ['860px', '420px'],
        closeBtn: 1,
        shadeClose: false,
        content: '<div class="bt-form dq-common-dialog">\
            <div class="dq-common-header clearfix">\
                <div class="mr20 pull-left" style="border-right: 1px solid #e2e8f0; padding-right: 20px;">\
                    <div class="ss-text pull-left">\
                        <em>' + _t('实时监控') + '</em>\
                        <div class="ssh-item">\
                            <input class="btswitch btswitch-ios" id="real_qps_monitoring" type="checkbox">\
                            <label id="real_qps_label" class="btswitch-btn" for="real_qps_monitoring"></label>\
                        </div>\
                    </div>\
                </div>\
            </div>\
            <div class="dq-common-table-wrap">\
                <table class="table table-hover dq-common-table" id="net_list">\
                    <thead>\
                        <th style="width:160px;">' + _t('时间') + '</th>\
                        <th>Select</th>\
                        <th>Insert</th>\
                        <th>Update</th>\
                        <th>Delete</th>\
                        <th>Conn</th>\
                        <th>Max_conn</th>\
                        <th>Recv</th>\
                        <th>Send</th>\
                    </thead>\
                    <tbody></tbody>\
                </table>\
            </div>\
        </div>',
        success:function(i,l){
            renderSQL();

            $('#real_qps_label').on('click', function(){
                sql_timer = setInterval(function(){
                    var t = $('#real_qps_monitoring').is(':checked');
                    if (t){
                        renderSQL();
                    } else{
                        clearInterval(sql_timer);
                    }
                }, 3000);
            });
        },
        end: function(){
            if (sql_timer) clearInterval(sql_timer);
        }
    });
}

function mysqlCommonFuncRedundantIndexes(){
    var _t = (typeof pt === 'function') ? pt : function(k){ return k; };
    function renderSQL(){
        var sid = mysqlGetSid();
        myPostCBN('get_redundant_indexes',{'sid':sid} ,function(rdata){
            var data = rdata.data;
            if (data['status']){
                var items = data.data;
                var tbody = '';
                for (var i = 0; i < items.length; i++) {
                    var t = '<tr>';
                    t += '<td>'+dqEscapeHtml(items[i]['table_schema'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['table_name'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['redundant_index_name'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['redundant_index_columns'])+'</td>';
                    t += '<td class="dq-sql-cell">'+dqEscapeHtml(items[i]['sql_drop_index'])+'</td>';
                    t += '<td><a class="exec btlink" index="'+i+'">' + _t('执行') + '</a></td>';
                    t += '</tr>';
                    tbody += t;
                }
                $('#redundant_indexes tbody').html(tbody);
                $('#redundant_indexes tbody .exec').on('click', function(){
                    var index = $(this).attr('index');
                    myPostCB('redundant_indexes_cmd', {'sid':sid, 'index':index}, function(rdata){
                        var data = rdata.data;
                        showMsg(data.msg,function(){
                            if (data.status){
                                renderSQL();
                            }
                        },{icon: data.status ? 1 : 2}, 2000);
                    });
                });
            } else {
                layer.msg(data.msg,{icon:2});
            }
        });
    }

    layer.open({
        type: 1,
        title: _t("查看重复或冗余的索引"),
        area: ['1100px', '520px'],
        closeBtn: 1,
        shadeClose: false,
        content: '<div class="bt-form dq-common-dialog">\
            <div class="dq-common-table-wrap">\
                <table class="table table-hover dq-common-table" id="redundant_indexes">\
                    <thead>\
                        <th style="width:120px;">' + _t('数据库名') + '</th>\
                        <th style="width:110px;">' + _t('表名') + '</th>\
                        <th style="width:120px;">' + _t('冗余索引名') + '</th>\
                        <th style="width:130px;">' + _t('冗余索引列名') + '</th>\
                        <th>' + _t('删除冗余索引SQL') + '</th>\
                        <th style="width:60px;">' + _t('操作') + '</th>\
                    </thead>\
                    <tbody></tbody>\
                </table>\
            </div>\
        </div>',
        success:function(i,l){
            renderSQL();
        }
    });
}

function mysqlCommonFuncTableInfo(){
    var _t = (typeof pt === 'function') ? pt : function(k){ return k; };
    function renderSQL(){
        var sid = mysqlGetSid();
        myPostCBN('get_table_info',{'sid':sid} ,function(rdata){
            var data = rdata.data;
            if (data['status']){
                var items = data.data;
                var tbody = '';
                for (var i = 0; i < items.length; i++) {
                    var t = '<tr>';
                    t += '<td>'+dqEscapeHtml(items[i]['TABLE_SCHEMA'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['TABLE_NAME'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['ENGINE'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['DATA_LENGTH'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['INDEX_LENGTH'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['TOTAL_LENGTH'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['COLUMN_NAME'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['COLUMN_TYPE'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['AUTO_INCREMENT'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['RESIDUAL_AUTO_INCREMENT'])+'</td>';
                    t += '</tr>';
                    tbody += t;
                }
                $('#mysql_data_id tbody').html(tbody);
            } else {
                layer.msg(data.msg,{icon:2});
            }
        });
    }

    layer.open({
        type: 1,
        title: _t("统计库里每个表的大小"),
        area: ['1200px', '520px'],
        closeBtn: 1,
        shadeClose: false,
        content: '<div class="bt-form dq-common-dialog">\
            <div class="dq-common-table-wrap">\
                <table class="table table-hover dq-common-table" id="mysql_data_id">\
                    <thead>\
                        <th style="width:110px;">' + _t('库名') + '</th>\
                        <th style="width:110px;">' + _t('表名') + '</th>\
                        <th style="width:90px;">' + _t('储存引擎') + '</th>\
                        <th style="width:110px;">' + _t('数据大小(GB)') + '</th>\
                        <th style="width:110px;">' + _t('索引大小(GB)') + '</th>\
                        <th style="width:90px;">' + _t('总计(GB)') + '</th>\
                        <th style="width:110px;">' + _t('主键自增字段') + '</th>\
                        <th style="width:130px;">' + _t('主键字段属性') + '</th>\
                        <th style="width:110px;">' + _t('主键自增当前') + '</th>\
                        <th style="width:110px;">' + _t('主键自增剩余') + '</th>\
                    </thead>\
                    <tbody></tbody>\
                </table>\
            </div>\
        </div>',
        success:function(i,l){
            renderSQL();
        }
    });
}

function mysqlCommonFuncConnCount(){
    var _t = (typeof pt === 'function') ? pt : function(k){ return k; };
    function renderSQL(){
        var sid = mysqlGetSid();
        myPostCBN('get_conn_count',{'sid':sid} ,function(rdata){
            var data = rdata.data;
            if (data['status']){
                var items = data.data;
                var tbody = '';
                for (var i = 0; i < items.length; i++) {
                    var t = '<tr>';
                    t += '<td>'+dqEscapeHtml(items[i]['user'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['db'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['Client_IP'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['count'])+'</td>';
                    t += '</tr>';
                    tbody += t;
                }
                $('#app_ip_list tbody').html(tbody);
            } else {
                layer.msg(data.msg,{icon:2});
            }
        });
    }

    var sql_timer = null;
    layer.open({
        type: 1,
        title: _t("查看应用端IP连接数总和"),
        area: ['750px', '450px'],
        closeBtn: 1,
        shadeClose: false,
        content: '<div class="bt-form dq-common-dialog">\
            <div class="dq-common-header clearfix">\
                <div class="mr20 pull-left" style="border-right: 1px solid #e2e8f0; padding-right: 20px;">\
                    <div class="ss-text pull-left">\
                        <em>' + _t('实时监控') + '</em>\
                        <div class="ssh-item">\
                            <input class="btswitch btswitch-ios" id="app_ip_monitoring" type="checkbox">\
                            <label id="app_ip_label" class="btswitch-btn" for="app_ip_monitoring"></label>\
                        </div>\
                    </div>\
                </div>\
            </div>\
            <div class="dq-common-table-wrap">\
                <table class="table table-hover dq-common-table" id="app_ip_list">\
                    <thead>\
                        <th style="width:160px;">' + _t('连接用户') + '</th>\
                        <th style="width:120px;">' + _t('数据库名') + '</th>\
                        <th>' + _t('应用端IP') + '</th>\
                        <th style="width:80px;">' + _t('数量') + '</th>\
                    </thead>\
                    <tbody></tbody>\
                </table>\
            </div>\
        </div>',
        success:function(i,l){
            renderSQL();

            $('#app_ip_label').on('click', function(){
                sql_timer = setInterval(function(){
                    var t = $('#app_ip_monitoring').is(':checked');
                    if (t){
                        renderSQL();
                    } else{
                        clearInterval(sql_timer);
                    }
                }, 3000);
            });
        },
        end: function(){
            if (sql_timer) clearInterval(sql_timer);
        }
    });
}

function mysqlCommonFuncFpkInfo(){
    var _t = (typeof pt === 'function') ? pt : function(k){ return k; };
    function renderSQL(){
        var sid = mysqlGetSid();
        myPostCBN('get_fpk_info',{'sid':sid} ,function(rdata){
            var data = rdata.data;
            if (data['status']){
                var items = data.data;
                var tbody = '';
                for (var i = 0; i < items.length; i++) {
                    var t = '<tr>';
                    t += '<td>'+dqEscapeHtml(items[i]['table_schema'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['table_name'])+'</td>';
                    t += '</tr>';
                    tbody += t;
                }
                $('#mysql_data_id tbody').html(tbody);
            } else {
                layer.msg(data.msg,{icon:2});
            }
        });
    }

    layer.open({
        type: 1,
        title: _t("快速找出没有主键的表"),
        area: ['800px', '450px'],
        closeBtn: 1,
        shadeClose: false,
        content: '<div class="bt-form dq-common-dialog">\
            <div class="dq-common-table-wrap">\
                <table class="table table-hover dq-common-table" id="mysql_data_id">\
                    <thead>\
                        <th style="width:50%;">' + _t('库名') + '</th>\
                        <th style="width:50%;">' + _t('表名') + '</th>\
                    </thead>\
                    <tbody></tbody>\
                </table>\
            </div>\
        </div>',
        success:function(i,l){
            renderSQL();
        }
    });
}

function mysqlCommonFuncLockSQL(){
    var _t = (typeof pt === 'function') ? pt : function(k){ return k; };
    function renderSQL(){
        var sid = mysqlGetSid();
        myPostCBN('get_lock_sql',{'sid':sid} ,function(rdata){
            var data = rdata.data;
            if (data['status']){
                var items = data.data;
                var tbody = '';
                for (var i = 0; i < items.length; i++) {
                    var t = '<tr>';
                    t += '<td>'+dqEscapeHtml(items[i]['trx_id'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['trx_state'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['trx_started'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['processlist_id'])+'</td>';
                    t += '<td class="dq-sql-cell">'+dqEscapeHtml(items[i]['info'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['user'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['host'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['db'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['command'])+'</td>';
                    t += '<td>'+dqEscapeHtml(items[i]['state'])+'</td>';
                    t += '<td class="dq-sql-cell">'+dqEscapeHtml(items[i]['sql_kill_blocking_query'])+'</td>';
                    t += '<td><a class="exec btlink" index="'+i+'">' + _t('执行') + '</a></td>';
                    t += '</tr>';
                    tbody += t;
                }
                $('#mysql_data_id tbody').html(tbody);

                $('#mysql_data_id tbody .exec').on('click', function(){
                    var index = $(this).attr('index');
                    var pid = items[index]['processlist_id'];
                    myPostCB('kill_lock_pid', {'sid':sid, 'pid':pid}, function(rdata){
                        var data = rdata.data;
                        showMsg(data.msg,function(){
                            if (data.status){
                                renderSQL();
                            }
                        },{icon: data.status ? 1 : 2}, 2000);
                    });
                });
            } else {
                layer.msg(data.msg,{icon:2});
            }
        });
    }

    layer.open({
        type: 1,
        title: _t("查看当前锁阻塞的SQL"),
        area: ['1150px', '520px'],
        closeBtn: 1,
        shadeClose: false,
        content: '<div class="bt-form dq-common-dialog">\
            <div class="dq-common-header clearfix">\
                <div class="pull-left">\
                    <button id="kill_all" type="button" class="btn btn-default btn-sm">' + _t('关闭所有阻塞') + '</button>\
                </div>\
            </div>\
            <div class="dq-common-table-wrap">\
                <table class="table table-hover dq-common-table" id="mysql_data_id">\
                    <thead>\
                        <th style="width:80px;">' + _t('事务ID') + '</th>\
                        <th style="width:80px;">' + _t('事务状态') + '</th>\
                        <th style="width:150px;">' + _t('执行时间') + '</th>\
                        <th style="width:80px;">' + _t('线程ID') + '</th>\
                        <th style="width:200px;">Info</th>\
                        <th style="width:70px;">user</th>\
                        <th style="width:100px;">host</th>\
                        <th style="width:70px;">db</th>\
                        <th style="width:70px;">command</th>\
                        <th style="width:70px;">state</th>\
                        <th style="width:140px;">kill</th>\
                        <th style="width:60px;">' + _t('操作') + '</th>\
                    </thead>\
                    <tbody></tbody>\
                </table>\
            </div>\
        </div>',
        success:function(i,l){
            renderSQL();

            $('#kill_all').off('click').on('click', function(){
                var sid = mysqlGetSid();
                myPostCB('kill_all_lock', {'sid':sid}, function(rdata){
                    var data = rdata.data;
                    showMsg(data.msg,function(){
                        if (data.status){
                            renderSQL();
                        }
                    },{icon: data.status ? 1 : 2}, 2000);
                });
            });
        }
    });
}

function mysqlCommonFuncDeadlockInfo(){
    var _t = (typeof pt === 'function') ? pt : function(k){ return k; };
    function renderSQL(){
        var sid = mysqlGetSid();
        myPostCBN('get_deadlock_info',{'sid':sid} ,function(rdata){
            var data = rdata.data;
            $('#info_log').val(data.data || '');
            var ob = document.getElementById('info_log');
            if (ob) ob.scrollTop = ob.scrollHeight; 
        });
    }

    layer.open({
        type: 1,
        title: _t("查看死锁信息"),
        area: ['850px', '480px'],
        closeBtn: 1,
        shadeClose: false,
        content: '<div class="bt-form dq-common-dialog">\
            <textarea readonly="" style="margin:0; width:100%; height:100%; box-sizing:border-box; background-color:#1e293b; color:#f8fafc; font-family:monospace; padding:10px; border-radius:4px; border:1px solid #334155; resize:none;" id="info_log"></textarea>\
        </div>',
        success:function(i,l){
            renderSQL();
        }
    });
}

function mysqlCommonFuncSlaveStatus(){
    var _t = (typeof pt === 'function') ? pt : function(k){ return k; };
    function renderSQL(){
        var sid = mysqlGetSid();
        myPostCBN('get_slave_status',{'sid':sid} ,function(rdata){
            var data = rdata.data;
            $('#info_log').val(data.data || '');
            var ob = document.getElementById('info_log');
            if (ob) ob.scrollTop = ob.scrollHeight; 
        });
    }

    layer.open({
        type: 1,
        title: _t("查看主从复制信息"),
        area: ['850px', '480px'],
        closeBtn: 1,
        shadeClose: false,
        content: '<div class="bt-form dq-common-dialog">\
            <textarea readonly="" style="margin:0; width:100%; height:100%; box-sizing:border-box; background-color:#1e293b; color:#f8fafc; font-family:monospace; padding:10px; border-radius:4px; border:1px solid #334155; resize:none;" id="info_log"></textarea>\
        </div>',
        success:function(i,l){
            renderSQL();
        }
    });
}

function mysqlCommonFunc(){
    $('#mysql_common').off('click').on('click', function(){
        var _t = (typeof pt === 'function') ? pt : function(k){ return k; };
        layer.open({
            type: 1,
            title: _t("MySQL常用功能"),
            area: ['640px', '260px'],
            closeBtn: 1,
            shadeClose: false,
            content: '<div class="bt-form dq-common-dialog">\
                <div class="dq-common-buttons-grid">\
                    <button id="mysql_top_nsql" type="button" class="btn btn-default btn-sm">' + _t('查询执行次数最频繁的前N条SQL语句') + '</button>\
                    <button id="mysql_net_stat" type="button" class="btn btn-default btn-sm">' + _t('MySQL服务器的QPS/TPS/网络带宽指标') + '</button>\
                    <button id="mysql_redundant_indexes" type="button" class="btn btn-default btn-sm">' + _t('查看重复或冗余的索引') + '</button>\
                    <button id="mysql_table_info" type="button" class="btn btn-default btn-sm">' + _t('统计库里每个表的大小') + '</button>\
                    <button id="mysql_conn_count" type="button" class="btn btn-default btn-sm">' + _t('查看应用端IP连接数总和') + '</button>\
                    <button id="mysql_fpk_info" type="button" class="btn btn-default btn-sm">' + _t('快速找出没有主键的表') + '</button>\
                    <button id="mysql_lock_sql" type="button" class="btn btn-default btn-sm">' + _t('查看当前锁阻塞的SQL') + '</button>\
                    <button id="mysql_deadlock_info" type="button" class="btn btn-default btn-sm">' + _t('查看死锁信息') + '</button>\
                    <button id="mysql_slave_status" type="button" class="btn btn-default btn-sm">' + _t('查看主从复制信息') + '</button>\
                </div>\
            </div>',
            success:function(i,l){
                $('#mysql_top_nsql').on('click', function(){
                    mysqlCommonFuncMysqlNSQL();
                });

                $('#mysql_net_stat').on('click', function(){
                    mysqlCommonFuncMysqlNet();
                });

                $('#mysql_redundant_indexes').on('click', function(){
                    mysqlCommonFuncRedundantIndexes();
                });

                $('#mysql_table_info').on('click', function(){
                    mysqlCommonFuncTableInfo();
                });

                $('#mysql_conn_count').on('click', function(){
                    mysqlCommonFuncConnCount();
                });

                $('#mysql_fpk_info').on('click', function(){
                    mysqlCommonFuncFpkInfo();
                });

                $('#mysql_lock_sql').on('click', function(){
                    mysqlCommonFuncLockSQL();
                });

                $('#mysql_deadlock_info').on('click', function(){
                    mysqlCommonFuncDeadlockInfo();
                });

                $('#mysql_slave_status').on('click', function(){
                    mysqlCommonFuncSlaveStatus();
                });
            }
        });
    });
}

function mysqlRunMysqlTab(name){
    switch(name){
        case 'proccess':mysqlProcessList();break;
        case 'status':mysqlStatusList();break;
        case 'stats':mysqlStatsList();break;
    }
}

// ------------------------- mysql start -------------------------------
function mysqlGetSid(){
    return $('#mysql select[name=sid]').val();
    // return 0;
}

function mysqlGetDbName(){
    return $('#mysql .mysql_db_list select[name=mysql_db]').val();
}

function mysqlGetTableName(){
    var table = $('#mysql .mysql_table_list select[name=mysql_table]').val();
    if (!table){
        return '';
    }
    return table;
}

function mysqlInitField(f, data){
    var option_html = '<option value="0">' + pt('无字段') + '</option>';
    for (var i = 0; i < f.length; i++) {
        if (data['soso_field'] == f[i]){
            option_html+= '<option value="'+f[i]+'" selected>'+f[i]+'</option>';
        } else {
            option_html+= '<option value="'+f[i]+'">'+f[i]+'</option>';
        }

        
    }

    $('select[name="mysql_field_key"]').html(option_html);

    $('#mysql_find').off('click').on('click', function(){
        var val = $('input[name="mysql_field_value"]').val();
        if (val == ''){
            layer.msg('搜索不能为空!',{icon:7});
            return;
        }
        mysqlGetDataList(1);
    });
}


function mysqlGetServerList(call_func){
    myPostCBN('get_server_list', {}, function(rdata){
        var rdata = rdata.data;
        if (rdata.data.length != 0){
            var items = rdata.data;
            var content = '';
            for (var i = 0; i < items.length; i++) {
                var t = items[i];
                if (i == 0){
                    content += '<option value="'+t['val']+'" selected>'+t['name']+'</option>';
                } else {
                    content += '<option value="'+t['val']+'">'+t['name']+'</option>';
                }
            }


            $('#mysql select[name=sid]').html(content);
            $('#mysql select[name=sid]').off('change').on('change', function(){
                loadDbPort('mysql', '#mysql', $(this).val());
                mysqlGetDbList();
            });
            if (typeof(call_func) == 'function'){
                call_func();
            }
            closeInstallLayer();
        } else {
            showInstallLayer();
        }
    });
}

function mysqlGetDbList(call_back){
    var sid = mysqlGetSid();
    myPostCBN('get_db_list', {'sid': sid}, function(rdata){
        var res = rdata ? rdata.data : null;
        if (res && res.status){
            var items = (res.data && res.data['list']) ? res.data['list'] : [];
            var isConnected = !(res.data && res.data.is_connected === false);
            var content = '';
            for (var i = 0; i < items.length; i++) {
                var name = items[i];
                if (i == 0){
                    content += '<option value="'+name+'" selected>database['+name+']</option>';
                } else {
                    content += '<option value="'+name+'">database['+name+']</option>';
                }
            }
            if (items.length == 0) {
                content = '<option value="">' + pt('无可用数据库') + '</option>';
            }
            $('#mysql .mysql_db_list select[name=mysql_db]').html(content);
            $('#mysql .mysql_db_list select[name=mysql_db]').off('change').on('change', function(){
                mysqlGetTableList(1);
            });

            if (!isConnected) {
                var connErr = (res && res.data && res.data.error_msg) ? res.data.error_msg : '';
                var alertMsg = connErr ? (pt('未连接到 MySQL 服务: ') + connErr) : pt('未连接到 MySQL 服务，已列出可用数据库，请自主选择连接');
                layer.msg(alertMsg, {icon: 0, time: 3500, maxWidth: 650});
                $('#mysql .mysql_table_list select[name=mysql_table]').html('<option value="">' + pt('未连接服务') + '</option>');
                var currentPort = $('#mysql input[name="db_port"]').val() || $('#mysql input[name=port]').val() || '3306';
                var displayErr = connErr || (pt('未连接到 MySQL 服务 (端口: ') + currentPort + ')');
                $('#mysql .mysql_list tbody').html('<tr><td colspan="10" style="text-align:center;color:#999;padding:30px;">' +
                    '<div style="font-size:15px;color:#d9534f;margin-bottom:10px;"><i class="glyphicon glyphicon-exclamation-sign"></i> ' + displayErr + '</div>' +
                    '<div style="color:#777;font-size:13px;margin-bottom:15px;">' + pt('当前未成功直连 MySQL 服务。上方下拉框已为您列出全部可用数据库，您可以选择一个数据库尝试连接，或检查服务状态与端口密码。') + '</div>' +
                    '<button class="btn btn-default btn-sm" onclick="mysqlGetDbList();"><span class="glyphicon glyphicon-refresh"></span> ' + pt('刷新/重试连接') + '</button>' +
                    '</td></tr>');
                $('#mysql .mysql_list_page').html('');
                if (typeof(call_back) === 'function') {
                    call_back(false, connErr || pt('未连接到 MySQL 服务'));
                }
            } else {
                mysqlGetTableList(1);
                if (typeof(call_back) === 'function') {
                    call_back(true);
                }
            }
        } else {
            var errMsg = (res && res.msg) ? res.msg : pt('未连接到 MySQL 服务');
            var fallbackList = (res && res.data && res.data.list && res.data.list.length > 0) ? res.data.list : ['mysql'];
            var content = '';
            for (var i = 0; i < fallbackList.length; i++) {
                var name = fallbackList[i];
                if (i == 0) {
                    content += '<option value="'+name+'" selected>database['+name+']</option>';
                } else {
                    content += '<option value="'+name+'">database['+name+']</option>';
                }
            }
            $('#mysql .mysql_db_list select[name=mysql_db]').html(content);
            $('#mysql .mysql_db_list select[name=mysql_db]').off('change').on('change', function(){
                mysqlGetTableList(1);
            });
            $('#mysql .mysql_table_list select[name=mysql_table]').html('<option value="">' + pt('数据表空') + '</option>');
            $('#mysql .mysql_list tbody').html('<tr><td colspan="10" style="text-align:center;color:#999;padding:30px;">' +
                '<div style="color:#d9534f;font-size:15px;margin-bottom:10px;"><i class="glyphicon glyphicon-exclamation-sign"></i> ' + errMsg + '</div>' +
                '<div style="color:#777;font-size:13px;margin-bottom:15px;">' + pt('已为您保留可用数据库选项，您可以切换选择库尝试连接，或检查配置后重试。') + '</div>' +
                '<button class="btn btn-default btn-sm" onclick="mysqlGetDbList();"><span class="glyphicon glyphicon-refresh"></span> ' + pt('重试连接') + '</button>' +
                '</td></tr>');
            $('#mysql .mysql_list_page').html('');
            if (typeof(call_back) === 'function') {
                call_back(false, errMsg);
            }
        }
    });
}

function mysqlGetTableList(p){
    var sid = mysqlGetSid();
    var db = mysqlGetDbName();

    if (!db){
        return;
    }

    myPostCBN('get_table_list', {'sid': sid, 'db': db}, function(rdata){
        var res = rdata ? rdata.data : null;
        if (res && res.status){
            var items = (res.data && res.data['list']) ? res.data['list'] : [];
            var content = '';
            for (var i = 0; i < items.length; i++) {
                var name = items[i];
                if (i == 0){
                    content += '<option value="'+name+'" selected>table['+name+']</option>';
                } else {
                    content += '<option value="'+name+'">table['+name+']</option>';
                }
            }
            if (items.length == 0) {
                content = '<option value="">数据表空</option>';
            }
            $('#mysql .mysql_table_list select[name=mysql_table]').html(content);
            $('#mysql .mysql_table_list select[name=mysql_table]').off('change').on('change', function(){
                mysqlGetDataList(1);
            });

            mysqlGetDataList(1);
        } else {
            var errMsg = (res && res.msg) ? res.msg : '无法连接数据库或获取数据表失败';
            $('#mysql .mysql_table_list select[name=mysql_table]').html('<option value="">数据表空</option>');
            $('#mysql .mysql_list tbody').html('<tr><td colspan="10" style="text-align:center;color:#999;padding:30px;">' +
                '<div style="color:#d9534f;margin-bottom:10px;font-size:14px;"><i class="glyphicon glyphicon-exclamation-sign"></i> 尝试连接数据库 [' + db + '] 失败</div>' +
                '<div style="color:#666;font-size:12px;margin-bottom:15px;">' + errMsg + '</div>' +
                '<button class="btn btn-default btn-sm" onclick="mysqlGetTableList(1);"><span class="glyphicon glyphicon-refresh"></span> 重新连接此库</button>' +
                '</td></tr>');
            $('#mysql .mysql_list_page').html('');
        }
    });
}

function mysqlGetDataList(p){
    var sid = mysqlGetSid();
    var db = mysqlGetDbName();
    var table = mysqlGetTableName();

    var mysql_field = $('select[name="mysql_field_key"]').val();
    var mysql_value = $('input[name="mysql_field_value"]').val();

    var request_data = {
        'sid':sid,
        'db':db,
        'table':table,
        'p':p
    };

    if (mysql_field != '0'){
        request_data['where'] = {
            field : mysql_field,
            value : mysql_value
        };
    } else {
        request_data['where'] = {};
    }

    myPostCB('get_data_list',request_data ,function(rdata){

        if (rdata.data.status){
            var data = rdata.data.data;
            var dlist = data['list'];

            var fields = mongodbGetDataFields(dlist);
            if (fields.length != 0 ){
                mysqlInitField(fields,data);
            }
        
            var header_field = '';
            for (var i =0 ; i<fields.length ; i++) {
                header_field += '<th>'+fields[i]+'</th>';
            }
            $('#mysql_table thead tr').html(header_field);

            var tbody = '';
            for (var i = 0; i < dlist.length; i++) {
                tbody += '<tr>';
                for (var j = 0; j < fields.length; j++) {
                    var f = fields[j];
                    if (f in dlist[i]) {
                        tbody += '<td title="'+dlist[i][f]+'">'+dlist[i][f]+'</td>';
                    } else {
                        tbody += '<td>undefined</td>';
                    }
                }
                tbody += '</tr>';
            }

            $('#mysql_table tbody').html(tbody);
            $('#mysql .mysql_list_page').html(data.page);
        }
        // 
    });
}


function mysqlProcessList(){
    var sid = mysqlGetSid();
    var request_data = {};
    request_data['sid'] = sid;
    myPostCBN('get_proccess_list',request_data ,function(rdata){
        if (rdata.data.status){
            var data = rdata.data.data;
            var dlist = data['list'];

            var fields = mongodbGetDataFields(dlist);
        
            var header_field = '';
            for (var i =0 ; i<fields.length ; i++) {
                header_field += '<th>'+fields[i]+'</th>';
            }
            $('#mysql_ot_table thead tr').html(header_field);

            var tbody = '';
            for (var i = 0; i < dlist.length; i++) {
                tbody += '<tr>';
                for (var j = 0; j < fields.length; j++) {
                    var f = fields[j];
                    if (f in dlist[i]) {
                        tbody += '<td title="'+dlist[i][f]+'">'+dlist[i][f]+'</td>';
                    } else {
                        tbody += '<td>undefined</td>';
                    }
                }
                tbody += '</tr>';
            }

            $('#mysql_ot_table tbody').html(tbody);
        }
    });
}

function mysqlStatusList(){
    var sid = mysqlGetSid();
    var request_data = {};
    request_data['sid'] = sid;
    myPostCBN('get_status_list',request_data ,function(rdata){
        // console.log(rdata);
        if (rdata.data.status){
            var data = rdata.data.data;
            var dlist = data['list'];

            var fields = mongodbGetDataFields(dlist);
        
            var header_field = '';
            for (var i =0 ; i<fields.length ; i++) {
                header_field += '<th>'+fields[i]+'</th>';
            }
            $('#mysql_ot_table thead tr').html(header_field);

            var tbody = '';
            for (var i = 0; i < dlist.length; i++) {
                tbody += '<tr>';
                for (var j = 0; j < fields.length; j++) {
                    var f = fields[j];
                    if (f in dlist[i]) {
                        tbody += '<td title="'+dlist[i][f]+'">'+dlist[i][f]+'</td>';
                    } else {
                        tbody += '<td>undefined</td>';
                    }
                }
                tbody += '</tr>';
            }

            $('#mysql_ot_table tbody').html(tbody);
        }
    });
}

function mysqlStatsList(){
    var sid = mysqlGetSid();
    var request_data = {};
    request_data['sid'] = sid;
    myPostCBN('get_stats_list',request_data ,function(rdata){
        // console.log(rdata);
        if (rdata.data.status){
            var data = rdata.data.data;
            var dlist = data['list'];

            var fields = mongodbGetDataFields(dlist);
        
            var header_field = '';
            for (var i =0 ; i<fields.length ; i++) {
                header_field += '<th>'+fields[i]+'</th>';
            }
            $('#mysql_ot_table thead tr').html(header_field);

            var tbody = '';
            for (var i = 0; i < dlist.length; i++) {
                tbody += '<tr>';
                for (var j = 0; j < fields.length; j++) {
                    var f = fields[j];
                    if (f in dlist[i]) {
                        tbody += '<td title="'+dlist[i][f]+'">'+dlist[i][f]+'</td>';
                    } else {
                        tbody += '<td>undefined</td>';
                    }
                }
                tbody += '</tr>';
            }

            $('#mysql_ot_table tbody').html(tbody);
        }
    });
}


// ------------------------- mysql start -------------------------------

// ------------------------- memcached start -------------------------------
function memcachedGetSid(){
    return $('#memcached select[name=sid]').val() || 'local';
}

function memcachedGetItem(){
    return $('#memcached .item_list select').val();
}

function memcachedGetList(call_back){
    var sid = memcachedGetSid();
    memPostCB('get_items',{'sid':sid} ,function(rdata){
        if (rdata && rdata.data && rdata.data.status){

            var items = rdata.data.data['items'] || [];
            var content = '';
            for (var i = 0; i < items.length; i++) {
                var name = items[i];
                if (i == 0){
                    content += '<option value="'+name+'" selected>items['+name+']</option>';
                } else {
                    content += '<option value="'+name+'">items['+name+']</option>';
                }
            }
            if (items.length == 0) {
                content = '<option value="">' + pt('无可用 Item') + '</option>';
            }
            $('#memcached .item_list select').html(content);
            $('#memcached .item_list select').off('change').on('change', function(){
                memcachedGetKeyList(1);
            });
            closeInstallLayer();
            memcachedGetKeyList(1);
            if (typeof(call_back) === 'function') {
                call_back(true);
            }
        } else {
            showInstallLayer();
            var emsg = (rdata && rdata.data && rdata.data.msg) ? rdata.data.msg : pt('无法连接 Memcached 服务');
            if (typeof(call_back) === 'function') {
                call_back(false, emsg);
            }
        }
    });
}

function memcachedGetKeyList(p){
    var item_id = memcachedGetItem();
    var sid = memcachedGetSid();
    memPostCB('get_key_list',{'sid':sid,'item_id':item_id,'p':p} ,function(rdata){
        if (rdata.data.status){
            var data = rdata.data.data;
            var dlist = data['list'];

            var tbody = '';
            for (var i = 0; i < dlist.length; i++) {
                tbody += '<tr>';

                tbody += "<td><input type='checkbox' class='check' name='id' onclick='checkSelect();'></td>";

                tbody += '<td>'+ dlist[i]['k'] +'</td>';
                tbody += '<td><span style="width:100px;" class="size_ellipsis">'+dlist[i]['v']+'</span><span data-index="'+i+'" class="ico-copy cursor copy ml5" title="复制值"></span></td>';
                tbody += '<td>'+ dlist[i]['s'] +'</td>';

                if (dlist[i]['t'] == '0'){
                    tbody += '<td>' + pt('永久') + '</td>';
                } else {
                    tbody += '<td>'+ dlist[i]['t'] +'</td>';
                }

                tbody += '<td style="text-align:right;">\
                        <a href="javascript:;" data-index="'+i+'" class="btlink del" title="删除">删除</a>\
                        </td>';

                tbody += '</tr>';
            }

            $('.memcached_table_content tbody').html(tbody);
            $('.memcached_list_page').html(data.page);


            $('.del').on('click', function(){
                var i = $(this).data('index');
                memcachedDeleteKey(dlist[i]['k']);
            });

            $('.copy').on('click', function(){
                var i = $(this).data('index');
                copyText(dlist[i]['v']);
            });
        } else {
            $('.memcached_table_content tbody').html('');
        }
    });
}

function memcachedDeleteKey(key){
    layer.confirm('确定要删除?', {btn: ['确定', '取消']}, function(){
        var data = {};
        data['sid'] = memcachedGetSid();
        data['key'] = key;
        memPostCB('del_val', data, function(rdata){
            showMsg(rdata.data.msg,function(){
                if (rdata.data.status){
                    memcachedGetKeyList(1);
                }
            },{icon: rdata.data.status ? 1 : 2}, 2000);
        });
    });
}


function memcachedAdd(){
    layer.open({
        type: 1,
        area: '480px',
        title: '添加Key至服务器',
        closeBtn: 1,
        shift: 0,
        shadeClose: false,
        btn:['确定','取消'],
        content: "<form class='bt-form pd20'>\
            <div class='line'>\
                <span class='tname'>" + pt('键') + "</span>\
                <div class='info-r c4'>\
                    <input class='bt-input-text' type='text' name='key' placeholder='键' style='width:260px;'/>\
                </div>\
            </div>\
            <div class='line'>\
                <span class='tname'>" + pt('值') + "</span>\
                <div class='info-r c4'>\
                    <textarea class='bt-input-text' name='val' style='width:260px;height:100px;'></textarea>\
                </div>\
            </div>\
            <div class='line'>\
                <span class='tname'>" + pt('有效期') + "</span>\
                <div class='info-r c4'>\
                    <input class='bt-input-text mr5' type='number' name='endtime' value='60' style='width:260px;'/>\
                </div>\
            </div>\
            <div class='line'>\
                <div>\
                    <ul class='help-info-text c7' style='margin-left:30px;'><li>" + pt('有效期为0表示永久') + "</li>\
                </div>\
            </div>\
        </form>",
        success:function(){
        },
        yes: function(index){
            var data = {};
            data['sid'] = memcachedGetSid();
            data['key'] = $('input[name="key"]').val();
            data['val'] = $('textarea[name="val"]').val();
            data['endtime'] = $('input[name="endtime"]').val();

            memPostCB('set_kv', data ,function(rdata){
                showMsg(rdata.data.msg,function(){
                    layer.close(index);
                    memcachedGetList();
                },{icon: rdata.data.status ? 1 : 2}, 1000); 
            });
        }
    });
}

// ------------------------- memcached end ---------------------------------

// ------------------------- mongodb start ---------------------------------
function mongodbGetSid(){
    return $('#mongodb select[name=sid]').val() || 'local';
}

function mongodbGetDbName(){
    return $('.db_list select[name="db"]').val();
}

function mongodbInitField(f, data){
    var option_html = '<option value="0">' + pt('无字段') + '</option>';
    for (var i = 0; i < f.length; i++) {
        if (data['soso_field'] == f[i]){
            option_html+= '<option value="'+f[i]+'" selected>'+f[i]+'</option>';
        } else {
            option_html+= '<option value="'+f[i]+'">'+f[i]+'</option>';
        }

        
    }

    $('select[name="mongodb_field_key"]').html(option_html);

    $('#mongodb .mongodb_find').off('click').on('click', function(){
        var val = $('input[name="mongodb_field_value"]').val();
        if (val == ''){
            layer.msg('搜索不能为空!',{icon:7});
            return;
        }
        mongodbDataList(1);
    });

    $('#mongodb .mongodb_refresh').off('click').on('click', function(){
        mongodbDataList(1);
    });
}

var mogodb_db_list;
function mongodbCollectionName(){
    // console.log(mogodb_db_list);
    var v = mogodb_db_list.getValue('value');
    if (v.length == 0){
        // console.log($('#mongodb').data('collection'));
        return $('#mongodb').data('collection');
    }
    return v[0];
}

function mongodbGetList(call_back){
    var sid = mongodbGetSid();
    mgdbPostCB('get_db_list',{'sid':sid} ,function(rdata){
        if (rdata && rdata.data && rdata.data.status){
            var list = rdata.data.data['list'] || [];
            var content = '';
            for (var i = 0; i < list.length; i++) {
                var name = list[i];
                if (i == 0){
                    content += '<option value="'+name+'" selected>'+name+'</option>';
                } else {
                    content += '<option value="'+name+'">'+name+'</option>';
                }
            }
            if (list.length == 0) {
                content = '<option value="">' + pt('无可用数据库') + '</option>';
            }
            $('.db_list select').html(content);

            if (list.length > 0) {
                mongodbGetCollections(list[0]);
            }

            $('#mongodb_select .db_list select[name="db"]').off('change').on('change', function(){
                var collection_name = $(this).val();
                mongodbGetCollections(collection_name);
            });

            closeInstallLayer();
            if (typeof(call_back) === 'function') {
                call_back(true);
            }
        } else {
            showInstallLayer();
            var emsg = (rdata && rdata.data && rdata.data.msg) ? rdata.data.msg : pt('无法连接 MongoDB 服务');
            if (typeof(call_back) === 'function') {
                call_back(false, emsg);
            }
        }
    });
}


function mongodbGetCollections(name){
    var sid = mongodbGetSid();
    
    mgdbPostCB('get_collections_list',{'sid':sid,'name':name} ,function(rdata){
        // console.log(rdata);
        if (rdata.data.status){
            var list = rdata.data.data['collections'];

            var select_list = [];
            for (var i = 0; i < list.length; i++) {
                var t = {};
                t['name'] = list[i];
                t['value'] = list[i];

                if (i == 0){
                    t['selected'] = true;
                }

                select_list.push(t);
            }

            mogodb_db_list = xmSelect.render({
                el: '#mongodb_search', 
                radio: true,
                toolbar: {show: true},
                data: select_list,
                on: function(data){
                    //arr:  当前多选已选中的数据
                    var arr = data.arr;
                    //change, 此次选择变化的数据,数组
                    var change = data.change;
                    //isAdd, 此次操作是新增还是删除
                    var isAdd = data.isAdd;
                    if (isAdd){
                        $('#mongodb').data('collection',change[0].value);

                        setTimeout(function(){
                            mongodbDataList(1);
                        },200);
                    }
                },
            });

            if (select_list.length > 0){

                setTimeout(function(){
                    mongodbDataList(1);
                },200);
            } 
        }
    });
}

function mongodbGetDataFields(data){
    var fields = [];
    for (var i = 0; i < data.length; i++) {    
        var d = data[i];
        for (var j in d) {
            if (fields.indexOf(j) == -1 ){
                fields.push(j);              
            }
        }
    }
    return fields;
}

function mongodbDataList(p){
    var sid = mongodbGetSid();
    var db = mongodbGetDbName();
    var collection = mongodbCollectionName();

    var mongodb_field = $('select[name="mongodb_field_key"]').val();
    var mongodb_value = $('input[name="mongodb_field_value"]').val();

    var request_data = {
        'sid':sid,
        'db':db,
        'collection':collection,
        "p":p,
    };

    if (mongodb_field != '0'){
        request_data['where'] = {
            field : mongodb_field,
            value : mongodb_value
        };
    } else {
        request_data['where'] = {};
    }

    // console.log({'sid':sid,'db':db,'collection':collection,"p":p});
    mgdbPostCB('get_data_list', request_data, function(rdata){
        if (rdata.data.status){
            var data = rdata.data.data;
            var dlist = data['list'];
            // console.log(dlist);

            var fields = mongodbGetDataFields(dlist);
            if (fields.length != 0 ){
                mongodbInitField(fields,data);
            }
            
            // console.log(fields);

            var header_field = '';
            for (var i =0 ; i<fields.length ; i++) {
                header_field += '<th>'+fields[i]+'</th>';
            }
            header_field += '<th class="text-right">' + pt('操作') + '</th>';

            $('#mongodb .mongodb_table thead tr').html(header_field);

            var tbody = '';
            for (var i = 0; i < dlist.length; i++) {
                tbody += '<tr>';
                for (var j = 0; j < fields.length; j++) {
                    var f = fields[j];

                    if (f in dlist[i]) {
                        if (f == '_id' ){
                            tbody += '<td>'+dlist[i]['_id']['$oid']+'</td>';
                        } else {
                            tbody += '<td>'+dlist[i][f]+'</td>';
                        }
                    } else {
                        tbody += '<td>undefined</td>';
                    }
                }

                tbody += '<td style="text-align:right;">\
                        <a href="javascript:;" data-index="'+i+'" class="btlink del" title="删除">删除</a>\
                        </td>';

                tbody += '</tr>';
            }

            // console.log($(window).width()-230);
            $('#mongodb_table').css('width', $(document).width()+240).parent().css('width', $(document).width()-240).css('overflow','scroll');
            $('#mongodb').css('width',$(document).width()-240).css('overflow','hidden');
            $('#mongodb .mongodb_table tbody').html(tbody);
            $('#mongodb .mongodb_list_page').html(data.page);

            $('#mongodb .del').on('click', function(){
                var i = $(this).data('index');
                mongodbDel(dlist[i]['_id']['$oid']);
            });
        }
    });
}

function mongodbDel(mgdb_id){
    // console.log(mgdb_id);
    var sid = mongodbGetSid();
    var db = mongodbGetDbName();
    var collection = mongodbCollectionName();
    mgdbPostCB('del_by_id',{'sid':sid,'db':db,'collection':collection,"_id":mgdb_id} ,function(rdata){
        showMsg(rdata.data.msg,function(){
            if (rdata.data.status){
                mongodbDataList(1);
            }
        },{icon: rdata.data.status ? 1 : 2}, 2000);
    });
}

// ------------------------- mongodb end ---------------------------------

// ------------------------- redis start ---------------------------------
function redisGetSid(){
    return $('#redis select[name=sid]').val() || 'local';
}

function redisGetIdx(){
    return $('#redis_list_tab .tab-nav span.on').data('id') || 0;
}

function redisGetList(call_back){
    var sid = redisGetSid();
    redisPostCB('get_list',{'sid':sid} ,function(rdata){
        if (rdata && rdata.data && rdata.data.status){
            var list = rdata.data.data || [];
            var content = '';
            for (var i = 0; i < list.length; i++) {
                if (i == 0){
                    content += '<span data-id="'+i+'" class="on">'+list[i]['name'] + '('+ list[i]['keynum'] +')</span>'; 
                } else {
                    content += '<span data-id="'+i+'">'+list[i]['name'] + '('+ list[i]['keynum'] +')</span>'; 
                }
            }
            if (list.length == 0) {
                content = '<span class="on">db0(0)</span>';
            }
            $('#redis_list_tab .tab-nav').html(content);

            $('#redis_list_tab .tab-nav span').off('click').on('click', function(){
                $('#redis_list_tab .tab-nav span').removeClass('on');
                $(this).addClass('on');
                redisGetKeyList(1);
            });
            redisGetKeyList(1);
            closeInstallLayer();
            if (typeof(call_back) === 'function') {
                call_back(true);
            }
        } else {
            showInstallLayer();
            var emsg = (rdata && rdata.data && rdata.data.msg) ? rdata.data.msg : pt('无法连接 Redis 服务');
            if (typeof(call_back) === 'function') {
                call_back(false, emsg);
            }
        }
    });
}

function redisGetKeyList(page,search = ''){

    var args = {};
    args['sid'] = redisGetSid();
    args['idx'] = redisGetIdx();
    args['p'] = page;
    args['search'] = search;

    var input_search_val = $('#redis_ksearch').val();
    if (input_search_val!=''){
        args['search'] = input_search_val;
    }

    redisPostCB('get_dbkey_list', args, function(rdata){
        if (rdata.data.status){
            var data = rdata.data.data.data;
            var tbody = '';
            for (var i = 0; i < data.length; i++) {


                tbody += '<tr>';
                tbody += "<td><input type='checkbox' class='check' name='id' title='"+data[i].name+"' onclick='checkSelect();' value='"+data[i].name+"'></td>";
                tbody += '<td style="width:100px;">'+data[i].name+'</td>';
                tbody += '<td><span style="width:100px;" class="size_ellipsis">'+data[i].val+'</span><span data-index="'+i+'" class="ico-copy cursor copy ml5" title="复制值"></span></td>';
                tbody += '<td>'+data[i].type+'</td>';
                tbody += '<td>'+data[i].len+'</td>';

                if (data[i].endtime == -1){
                    tbody += '<td>' + pt('永久') + '</td>';
                } else {
                    tbody += '<td>'+data[i].endtime+'</td>';
                }

                tbody += '<td style="width:200px;text-align:right; color:#bbb">\
                        <a href="javascript:;" data-index="'+i+'" class="btlink edit" title="编辑">编辑</a> | \
                        <a href="javascript:;" class="btlink" onclick="redisDeleteKey(\''+data[i].name+'\')">删除</a>\
                        </td>';

                tbody += '</tr>';
            }

            // console.log(tbody);
            $('.redis_table_content tbody').html(tbody);
            $('.redis_list_page').html(rdata.data.data.page);


            $('.edit').on('click', function(){
                var i = $(this).data('index');
                redisEditKv(data[i].name,data[i].val,data[i].endtime);
            });

            $('.copy').on('click', function(){
                var i = $(this).data('index');
                copyText(data[i].val);
            });

        }
    });
}

function redisDeleteKey(name){
    layer.confirm('确定要删除?', {btn: ['确定', '取消']}, function(){
        var data = {};
        data['idx'] = redisGetIdx();
        data['sid'] = redisGetSid();
        data['name'] = name;
        redisPostCB('del_val', data, function(rdata){
            showMsg(rdata.data.msg,function(){
                if (rdata.data.status){
                    redisGetList();
                }
            },{icon: rdata.data.status ? 1 : 2}, 2000);
        });
    });
}

function redisAdd(){
    layer.open({
        type: 1,
        area: '480px',
        title: '添加Key至服务器',
        closeBtn: 1,
        shift: 0,
        shadeClose: false,
        btn:['确定','取消'],
        content: "<form class='bt-form pd20'>\
            <div class='line'>\
                <span class='tname'>" + pt('数据库') + "</span>\
                <div class='info-r c4'>\
                    <select name='idx' class='bt-input-text' style='width:260px;'>\
                        <option value='0'>DB(0)</option>\
                    </select>\
                </div>\
            </div>\
            <div class='line'>\
                <span class='tname'>" + pt('键') + "</span>\
                <div class='info-r c4'>\
                    <input class='bt-input-text' type='text' name='key' placeholder='键' style='width:260px;'/>\
                </div>\
            </div>\
            <div class='line'>\
                <span class='tname'>" + pt('值') + "</span>\
                <div class='info-r c4'>\
                    <textarea class='bt-input-text' name='val' style='width:260px;height:100px;'></textarea>\
                </div>\
            </div>\
            <div class='line'>\
                <span class='tname'>" + pt('有效期') + "</span>\
                <div class='info-r c4'>\
                    <input class='bt-input-text mr5' type='number' name='endtime' value='60' style='width:260px;'/>\
                </div>\
            </div>\
            <div class='line'>\
                <div>\
                    <ul class='help-info-text c7' style='margin-left:30px;'><li>" + pt('有效期为0表示永久') + "</li>\
                </div>\
            </div>\
        </form>",
        success:function(){
            var db_list = $('#redis_list_tab .tab-nav span');
            var db_list_count = db_list.length;

            var idx_html = '';
            for (var i = 0; i < db_list_count; i++) {
                idx_html += "<option value='"+i+"'>DB("+i+")</option>";
            }
            $('select[name=idx]').html(idx_html);
        },
        yes: function(index){
            var data = {};
            data['idx'] = $('select[name=idx]').val();
            data['sid'] = redisGetSid();
            data['name'] = $('input[name="key"]').val();
            data['val'] = $('textarea[name="val"]').val();
            data['endtime'] = $('input[name="endtime"]').val();

            redisPostCB('set_kv', data ,function(rdata){
                showMsg(rdata.data.msg,function(){
                    layer.close(index);
                    redisGetList();
                },{icon: rdata.data.status ? 1 : 2}, 1000); 
            });
        }
    });
}

function redisEditKv(name, val, endtime){
    layer.open({
        type: 1,
        area: '480px',
        title: '编辑['+name+']Key',
        closeBtn: 1,
        shift: 0,
        shadeClose: false,
        btn:['确定','取消'],
        content: "<form class='bt-form pd20'>\
            <div class='line'>\
                <span class='tname'>" + pt('数据库') + "</span>\
                <div class='info-r c4'>\
                    <select name='idx' class='bt-input-text' style='width:260px;'>\
                        <option value='0'>DB(0)</option>\
                    </select>\
                </div>\
            </div>\
            <div class='line'>\
                <span class='tname'>" + pt('键') + "</span>\
                <div class='info-r c4'>\
                    <input class='bt-input-text' type='text' name='key' placeholder='键' style='width:260px;'/>\
                </div>\
            </div>\
            <div class='line'>\
                <span class='tname'>" + pt('值') + "</span>\
                <div class='info-r c4'>\
                    <textarea class='bt-input-text' name='val' style='width:260px;height:100px;'></textarea>\
                </div>\
            </div>\
            <div class='line'>\
                <span class='tname'>" + pt('有效期') + "</span>\
                <div class='info-r c4'>\
                    <input class='bt-input-text mr5' type='number' name='endtime' value='60' style='width:260px;'/>\
                </div>\
            </div>\
            <div class='line'>\
                <div>\
                    <ul class='help-info-text c7' style='margin-left:30px;'><li>" + pt('有效期为0表示永久') + "</li>\
                </div>\
            </div>\
        </form>",
        success:function(){
            var idx = redisGetIdx();
            var idx_html = "<option value='"+idx+"'>DB("+idx+")</option>";
            $('select[name=idx]').html(idx_html).attr('readonly','readonly');
            $('input[name="key"]').val(name).attr('readonly','readonly');
            $('textarea[name="val"]').val(val);

            if (endtime == -1){
                $('input[name="endtime"]').val(0);
            } else {
                $('input[name="endtime"]').val(endtime);
            }            
        },
        yes: function(index){
            var data = {};
            data['idx'] = $('select[name=idx]').val();
            data['sid'] = redisGetSid();
            data['name'] = $('input[name="key"]').val();
            data['val'] = $('textarea[name="val"]').val();
            data['endtime'] = $('input[name="endtime"]').val();
            redisPostCB('set_kv', data ,function(rdata){
                showMsg(rdata.data.msg,function(){
                    if (rdata.data.status){
                        layer.close(index);
                        redisGetList();
                    }
                },{icon: rdata.data.status ? 1 : 2}, 1000);
            });
        }
    });
}

function redisBatchDel(){
    var keys = [];
    $('input[type="checkbox"].check:checked').each(function () {
        keys.push($(this).val());
    });
    if (keys.length == 0){
        layer.msg('没有选中数据!',{icon:7});
        return;
    } 

    layer.confirm('确定要批量删除?', {btn: ['确定', '取消']}, function(){
        var data = {};
        data['idx'] = redisGetIdx();
        data['sid'] = redisGetSid();
        data['keys'] = keys;
        redisPostCB('batch_del_val', data, function(rdata){
            showMsg(rdata.data.msg,function(){
                if (rdata.data.status){
                   redisGetList(); 
                }
            },{icon: rdata.data.status ? 1 : 2}, 2000);
        });
    });
}

function redisBatchClear(){
    var xm_db_list;
    layer.open({
        type: 1,
        area: ['480px','180px'],
        title: '清空【本地服务器】数据库',
        closeBtn: 1,
        shift: 0,
        shadeClose: false,
        btn:['确定','取消'],
        content: "<form class='bt-form pd20'>\
            <div class='line'>\
                <span class='tname'>" + pt('选择数据库') + "</span>\
                <div class='info-r'>\
                    <div id='select_db'></div>\
                </div>\
            </div>\
        </form>",
        success:function(l,i){
            var db_list = $('#redis_list_tab .tab-nav span');
            var db_list_count = db_list.length;

            var idx_db = [];
            for (var i = 0; i < db_list_count; i++) {
                var t = {};
                t['name'] = "DB("+i+")";
                t['value'] = i;
                idx_db.push(t);
            }

            xm_db_list = xmSelect.render({
                el: '#select_db', 
                repeat: false,
                toolbar: {show: true},
                data: idx_db,
            });

            $(l).find('.layui-layer-content').css('overflow','visible');
        },
        yes: function(index){
            var xm_db_val = xm_db_list.getValue('value');
            layer.confirm('确定要批量清空?', {btn: ['确定', '取消']}, function(){
                var data = {};
                data['sid'] = redisGetSid();
                data['idxs'] = xm_db_val;
                redisPostCB('clear_flushdb', data, function(rdata){
                    showMsg(rdata.data.msg,function(){
                        if (rdata.data.status){
                           redisGetList();
                           layer.close(index);
                        }
                    },{icon: rdata.data.status ? 1 : 2}, 2000);
                });
            });
        }
    });
}
// ------------------------- redis end ---------------------------------

// ------------------------- postgresql start ---------------------------
var pg_timer = null;

function connectPostgreSQL(){
    updateDbConnectionUI('postgresql', 'connecting');
    pgGetDbList(function(success, errMsg){
        if (success){
            updateDbConnectionUI('postgresql', 'connected');
            layer.msg(pt('PostgreSQL 数据库连接成功！'), {icon: 1, time: 2000});
            pgProcessList();

            clearInterval(pg_timer);    
            pg_timer = setInterval(function(){
                var fname = $('#cutTab .tabs-item.active').data('name');
                if (fname != 'postgresql' || !dqConnectionStates['postgresql'].connected){
                    clearInterval(pg_timer);
                    return;
                }
                var sid = pgGetSid();
                if (sid === undefined || sid === null) {
                    return;
                }
                var name = $('#pg_list_tab .tab-nav span.on').data('name');
                pgRunPgTab(name);
            }, 3000);
        } else {
            updateDbConnectionUI('postgresql', 'error', errMsg || pt('连接失败，请检查配置与服务状态'));
        }
    });
}

function disconnectPostgreSQL(){
    clearInterval(pg_timer);
    updateDbConnectionUI('postgresql', 'disconnected');
    layer.msg(pt('已断开 PostgreSQL 连接'), {icon: 1, time: 1500});
}

function initTabPostgresql(){
    loadUnifiedServerList('postgresql', function(){
        updateDbConnectionUI('postgresql', dqConnectionStates['postgresql'].connected ? 'connected' : 'disconnected');
    });

    bindConnectionBar('postgresql', connectPostgreSQL, disconnectPostgreSQL);

    $('#pg_list_tab .tab-nav span').off('click').on('click', function(){
        $('#pg_list_tab .tab-nav span').removeClass('on');
        $(this).addClass('on');
        var name = $(this).data('name');
        pgRunPgTab(name);
    });

    $('#pg_find').off('click').on('click', function(){
        var val = $('input[name="pg_field_value"]').val();
        if (val == ''){
            layer.msg(pt('搜索不能为空!'),{icon:7});
            return;
        }
        pgGetDataList(1);
    });

    $('#pg_refresh').off('click').on('click', function(){
        pgGetDataList(1);
    });
}

function pgRunPgTab(name){
    switch(name){
        case 'proccess': pgProcessList(); break;
        case 'status': pgStatusList(); break;
        case 'stats': pgStatsList(); break;
    }
}

function pgGetSid(){
    return $('#postgresql select[name=sid]').val() || 'pgsql';
}

function pgGetDbName(){
    return $('#postgresql .pg_db_list select[name=pg_db]').val();
}

function pgGetTableName(){
    var table = $('#postgresql .pg_table_list select[name=pg_table]').val();
    return table || '';
}

function pgInitField(f, data){
    var option_html = '<option value="0">' + pt('无字段') + '</option>';
    for (var i = 0; i < f.length; i++) {
        if (data['soso_field'] == f[i]){
            option_html += '<option value="'+f[i]+'" selected>'+f[i]+'</option>';
        } else {
            option_html += '<option value="'+f[i]+'">'+f[i]+'</option>';
        }
    }
    $('select[name="pg_field_key"]').html(option_html);
}

function pgGetServerList(call_func){
    pgPostCBN('get_server_list', {}, function(rdata){
        var res = rdata ? rdata.data : null;
        var items = (res && res.data && res.data.length != 0) ? res.data : [{'name': '本地 PostgreSQL (127.0.0.1)', 'val': 'pgsql'}];
        var content = '';
        for (var i = 0; i < items.length; i++) {
            var t = items[i];
            if (i == 0){
                content += '<option value="'+t['val']+'" selected>'+t['name']+'</option>';
            } else {
                content += '<option value="'+t['val']+'">'+t['name']+'</option>';
            }
        }
        $('#postgresql select[name=sid]').html(content);
        $('#postgresql select[name=sid]').off('change').on('change', function(){
            loadDbPort('postgresql', '#postgresql', $(this).val());
            pgGetDbList();
        });
        if (typeof(call_func) == 'function'){
            call_func();
        }
        closeInstallLayer();
    });
}

function showInstallPgDriverDialog() {
    var timer = null;
    layer.open({
        type: 1,
        title: "安装 PostgreSQL (psycopg2-binary) 驱动",
        area: ['750px', '480px'],
        closeBtn: 1,
        shadeClose: false,
        content: '<div class="bt-form pd20" style="background:#1e1e1e;color:#eee;height:100%;box-sizing:border-box;display:flex;flex-direction:column;">' +
            '<div style="margin-bottom:10px;font-size:13px;color:#bbb;display:flex;justify-content:space-between;align-items:center;">' +
                '<span><i class="glyphicon glyphicon-console"></i> 正在调用后台 pip 安装 psycopg2-binary 驱动，请稍候...</span>' +
                '<span id="pg_install_status_badge" class="badge" style="background:#f0ad4e;">准备中</span>' +
            '</div>' +
            '<pre id="pg_driver_log_view" style="flex:1;background:#121212;color:#00ff66;font-family:Consolas,Menlo,monospace;font-size:12px;padding:12px;border:1px solid #333;overflow-y:auto;white-space:pre-wrap;word-break:break-all;border-radius:4px;margin-bottom:10px;">正在连接安装任务...\n</pre>' +
            '<div style="text-align:right;">' +
                '<button id="btn_pg_driver_close" class="btn btn-default btn-sm" style="display:none;">关闭</button>' +
            '</div>' +
        '</div>',
        success: function(layero, index) {
            pgPostCBN('install_pg_driver', {}, function(rdata) {
                function pollLog() {
                    pgPostCBN('get_install_driver_log', {}, function(res) {
                        if (res && res.data && res.data.data) {
                            var logData = res.data.data;
                            var logContent = logData.log || '';
                            var logDom = $('#pg_driver_log_view');
                            if (logDom.length) {
                                logDom.text(logContent);
                                logDom.scrollTop(logDom[0].scrollHeight);
                            }

                            if (logData.is_finished) {
                                if (timer) {
                                    clearInterval(timer);
                                    timer = null;
                                }
                                $('#btn_pg_driver_close').show();
                                if (logData.success) {
                                    $('#pg_install_status_badge').css('background', '#5cb85c').text('安装成功');
                                    layer.msg('PostgreSQL 驱动安装成功！', {icon: 1, time: 2000});
                                    setTimeout(function() {
                                        layer.close(index);
                                        $('#postgresql .btn_install_pg_driver').remove();
                                        pgGetDbList();
                                    }, 1800);
                                } else {
                                    $('#pg_install_status_badge').css('background', '#d9534f').text('安装失败');
                                }
                            } else {
                                $('#pg_install_status_badge').css('background', '#0275d8').text('安装中...');
                            }
                        }
                    });
                }
                pollLog();
                timer = setInterval(pollLog, 1500);
            });

            $('#btn_pg_driver_close').on('click', function() {
                layer.close(index);
            });
        },
        end: function() {
            if (timer) {
                clearInterval(timer);
                timer = null;
            }
        }
    });
}

function pgGetDbList(call_back){
    var sid = pgGetSid();
    pgPostCBN('get_db_list', {'sid': sid}, function(rdata){
        var res = rdata ? rdata.data : null;
        if (res && res.status){
            $('#postgresql .btn_install_pg_driver').remove();
            var items = (res.data && res.data['list']) ? res.data['list'] : [];
            var content = '';
            for (var i = 0; i < items.length; i++) {
                var name = items[i];
                if (i == 0){
                    content += '<option value="'+name+'" selected>database['+name+']</option>';
                } else {
                    content += '<option value="'+name+'">database['+name+']</option>';
                }
            }
            if (items.length == 0) {
                content = '<option value="">' + pt('无可用数据库') + '</option>';
            }
            $('#postgresql .pg_db_list select[name=pg_db]').html(content);
            $('#postgresql .pg_db_list select[name=pg_db]').off('change').on('change', function(){
                pgGetTableList(1);
            });
            pgGetTableList(1);
            if (typeof(call_back) === 'function') {
                call_back(true);
            }
        } else {
            var isDriverMissing = (res && res.data && res.data.driver_missing) || (res && res.msg && res.msg.indexOf('psycopg2') !== -1);
            var errMsg = (res && res.msg) ? res.msg : pt('未连接到 PostgreSQL 服务');

            if (isDriverMissing) {
                // 驱动缺失：自动弹窗询问用户是否安装驱动
                if (!window._pgDriverConfirming) {
                    window._pgDriverConfirming = true;
                    var confirmTitle = pt('驱动缺失提示');
                    var confirmMsg = pt('检测到当前系统尚未安装 PostgreSQL (psycopg2) 驱动，无法建立数据库连接。是否立即自动安装驱动？');
                    layer.confirm(confirmMsg, {
                        icon: 0,
                        title: confirmTitle,
                        btn: [pt('立即安装'), pt('取消')],
                        end: function() {
                            window._pgDriverConfirming = false;
                        }
                    }, function(cIndex){
                        window._pgDriverConfirming = false;
                        layer.close(cIndex);
                        showInstallPgDriverDialog();
                    }, function(cIndex){
                        window._pgDriverConfirming = false;
                        layer.close(cIndex);
                    });
                }

                if (!$('#postgresql .btn_install_pg_driver').length) {
                    var btnHtml = '<button class="btn btn-success btn-sm btn_install_pg_driver" style="margin-left:8px;vertical-align:top;" title="' + pt('一键安装 psycopg2-binary 驱动') + '"><span class="glyphicon glyphicon-download-alt"></span> ' + pt('一键安装驱动') + '</button>';
                    $('#postgresql .db_port_save').after(btnHtml);
                    $('#postgresql .btn_install_pg_driver').off('click').on('click', function(){
                        showInstallPgDriverDialog();
                    });
                }
                $('#postgresql .pg_db_list select[name=pg_db]').html('<option value="">' + pt('未安装 psycopg2 驱动 (请点击一键安装)') + '</option>');
                $('#postgresql .pg_table_list select[name=pg_table]').html('<option value="">' + pt('数据表空') + '</option>');

                var installCardHtml = '<tr><td colspan="10" style="text-align:center;color:#666;padding:45px 20px;">' +
                    '<div style="font-size:18px;color:#d9534f;margin-bottom:12px;font-weight:600;"><i class="glyphicon glyphicon-exclamation-sign"></i> ' + pt('未安装 PostgreSQL (psycopg2) 驱动') + '</div>' +
                    '<div style="color:#777;font-size:13px;margin-bottom:20px;max-width:550px;margin-left:auto;margin-right:auto;line-height:1.6;">' + pt('系统检测到当前面板环境尚未安装 PostgreSQL 数据库驱动（psycopg2-binary），无法进行连接与数据管理。您可以点击下方按钮一键安装并查看实时日志。') + '</div>' +
                    '<button class="btn btn-success btn_pg_install_guide" style="padding:7px 20px;font-size:14px;"><span class="glyphicon glyphicon-download-alt"></span> ' + pt('一键安装驱动并查看日志') + '</button>' +
                    '</td></tr>';
                $('#postgresql .pg_list tbody').html(installCardHtml);
                $('#postgresql .btn_pg_install_guide').off('click').on('click', function(){
                    showInstallPgDriverDialog();
                });
                $('#postgresql .pg_list_page').html('');
            } else {
                $('#postgresql .btn_install_pg_driver').remove();
                $('#postgresql .pg_db_list select[name=pg_db]').html('<option value="">' + errMsg + '</option>');
                $('#postgresql .pg_table_list select[name=pg_table]').html('<option value="">' + pt('数据表空') + '</option>');
                $('#postgresql .pg_list tbody').html('<tr><td colspan="10" style="text-align:center;color:#999;padding:30px;">' +
                    '<div style="color:#d9534f;font-size:15px;margin-bottom:10px;"><i class="glyphicon glyphicon-exclamation-sign"></i> ' + errMsg + '</div>' +
                    '<button class="btn btn-default btn-sm" onclick="pgGetDbList();"><span class="glyphicon glyphicon-refresh"></span> ' + pt('刷新/重试连接') + '</button>' +
                    '</td></tr>');
                $('#postgresql .pg_list_page').html('');
            }
            if (typeof(call_back) === 'function') {
                call_back(false, errMsg);
            }
        }
    });
}

function pgGetTableList(p){
    var sid = pgGetSid();
    var db = pgGetDbName();
    if (!db){
        return;
    }
    pgPostCBN('get_table_list', {'sid': sid, 'db': db}, function(rdata){
        var res = rdata ? rdata.data : null;
        if (res && res.status){
            var items = (res.data && res.data['list']) ? res.data['list'] : [];
            var content = '';
            for (var i = 0; i < items.length; i++) {
                var name = items[i];
                if (i == 0){
                    content += '<option value="'+name+'" selected>table['+name+']</option>';
                } else {
                    content += '<option value="'+name+'">table['+name+']</option>';
                }
            }
            if (items.length == 0) {
                content = '<option value="">数据表空</option>';
            }
            $('#postgresql .pg_table_list select[name=pg_table]').html(content);
            $('#postgresql .pg_table_list select[name=pg_table]').off('change').on('change', function(){
                pgGetDataList(1);
            });
            pgGetDataList(1);
        } else {
            var errMsg = (res && res.msg) ? res.msg : '无法连接数据库或获取数据表失败';
            $('#postgresql .pg_table_list select[name=pg_table]').html('<option value="">数据表空</option>');
            $('#postgresql .pg_list tbody').html('<tr><td colspan="10" style="text-align:center;color:#999;padding:30px;">' +
                '<div style="color:#d9534f;margin-bottom:10px;font-size:14px;"><i class="glyphicon glyphicon-exclamation-sign"></i> 尝试连接数据库 [' + db + '] 失败</div>' +
                '<div style="color:#666;font-size:12px;margin-bottom:15px;">' + errMsg + '</div>' +
                '<button class="btn btn-default btn-sm" onclick="pgGetTableList(1);"><span class="glyphicon glyphicon-refresh"></span> 重新连接此库</button>' +
                '</td></tr>');
            $('#postgresql .pg_list_page').html('');
        }
    });
}

function pgGetDataList(p){
    var sid = pgGetSid();
    var db = pgGetDbName();
    var table = pgGetTableName();
    var pg_field = $('select[name="pg_field_key"]').val();
    var pg_value = $('input[name="pg_field_value"]').val();

    var request_data = {
        'sid': sid,
        'db': db,
        'table': table,
        'p': p
    };
    if (pg_field && pg_field != '0'){
        request_data['where'] = {
            field: pg_field,
            value: pg_value
        };
    } else {
        request_data['where'] = {};
    }

    pgPostCB('get_data_list', request_data, function(rdata){
        if (rdata.data && rdata.data.status){
            var data = rdata.data.data;
            var dlist = data['list'] || [];

            var fields = mongodbGetDataFields(dlist);
            if (fields.length != 0 ){
                pgInitField(fields, data);
            }
        
            var header_field = '';
            for (var i = 0; i < fields.length; i++) {
                header_field += '<th>'+fields[i]+'</th>';
            }
            $('#pg_table thead tr').html(header_field);

            var tbody = '';
            for (var i = 0; i < dlist.length; i++) {
                tbody += '<tr>';
                for (var j = 0; j < fields.length; j++) {
                    var f = fields[j];
                    if (f in dlist[i]) {
                        tbody += '<td title="'+dlist[i][f]+'">'+dlist[i][f]+'</td>';
                    } else {
                        tbody += '<td>undefined</td>';
                    }
                }
                tbody += '</tr>';
            }
            $('#pg_table tbody').html(tbody);
            $('#postgresql .pg_list_page').html(data.page || '');
        }
    });
}

function pgProcessList(){
    var sid = pgGetSid();
    pgPostCBN('get_proccess_list', {'sid': sid}, function(rdata){
        if (rdata.data && rdata.data.status){
            var data = rdata.data.data;
            var dlist = data['list'] || [];
            var fields = mongodbGetDataFields(dlist);
            var header_field = '';
            for (var i = 0; i < fields.length; i++) {
                header_field += '<th>'+fields[i]+'</th>';
            }
            $('#pg_ot_table thead tr').html(header_field);

            var tbody = '';
            for (var i = 0; i < dlist.length; i++) {
                tbody += '<tr>';
                for (var j = 0; j < fields.length; j++) {
                    var f = fields[j];
                    if (f in dlist[i]) {
                        tbody += '<td title="'+dlist[i][f]+'">'+dlist[i][f]+'</td>';
                    } else {
                        tbody += '<td>undefined</td>';
                    }
                }
                tbody += '</tr>';
            }
            $('#pg_ot_table tbody').html(tbody);
        }
    });
}

function pgStatusList(){
    var sid = pgGetSid();
    pgPostCBN('get_status_list', {'sid': sid}, function(rdata){
        if (rdata.data && rdata.data.status){
            var data = rdata.data.data;
            var dlist = data['list'] || [];
            var fields = mongodbGetDataFields(dlist);
            var header_field = '';
            for (var i = 0; i < fields.length; i++) {
                header_field += '<th>'+fields[i]+'</th>';
            }
            $('#pg_ot_table thead tr').html(header_field);

            var tbody = '';
            for (var i = 0; i < dlist.length; i++) {
                tbody += '<tr>';
                for (var j = 0; j < fields.length; j++) {
                    var f = fields[j];
                    if (f in dlist[i]) {
                        tbody += '<td title="'+dlist[i][f]+'">'+dlist[i][f]+'</td>';
                    } else {
                        tbody += '<td>undefined</td>';
                    }
                }
                tbody += '</tr>';
            }
            $('#pg_ot_table tbody').html(tbody);
        }
    });
}

function pgStatsList(){
    var sid = pgGetSid();
    pgPostCBN('get_stats_list', {'sid': sid}, function(rdata){
        if (rdata.data && rdata.data.status){
            var data = rdata.data.data;
            var dlist = data['list'] || [];
            var fields = mongodbGetDataFields(dlist);
            var header_field = '';
            for (var i = 0; i < fields.length; i++) {
                header_field += '<th>'+fields[i]+'</th>';
            }
            $('#pg_ot_table thead tr').html(header_field);

            var tbody = '';
            for (var i = 0; i < dlist.length; i++) {
                tbody += '<tr>';
                for (var j = 0; j < fields.length; j++) {
                    var f = fields[j];
                    if (f in dlist[i]) {
                        tbody += '<td title="'+dlist[i][f]+'">'+dlist[i][f]+'</td>';
                    } else {
                        tbody += '<td>undefined</td>';
                    }
                }
                tbody += '</tr>';
            }
            $('#pg_ot_table tbody').html(tbody);
        }
    });
}
// ------------------------- postgresql end -----------------------------

