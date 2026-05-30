var yufeng_systemd = {
    plugin_name: 'yufeng_systemd',
    
    init: function() {
        this.get_list();
    },
    
    // 获取列表
    get_list: function() {
        var loadT = layer.msg('正在获取服务列表...', {icon: 16, time: 0, shade: 0.3});
        this.request('get_services', {}, function(res) {
            layer.close(loadT);
            var tbody = $('#yufeng_service_list');
            if (!res.status) {
                tbody.html('<tr><td colspan="4" style="text-align:center;color:red;">' + res.msg + '</td></tr>');
                return;
            }
            
            var data = res.data;
            if (data.length === 0) {
                tbody.html('<tr><td colspan="4" style="text-align:center;">暂无专属守护服务</td></tr>');
                return;
            }
            
            var html = '';
            for (var i = 0; i < data.length; i++) {
                var item = data[i];
                var status_html = '';
                if (item.status === 'active') {
                    status_html = '<span class="status-active">运行中</span> <a class="btlink" onclick="yufeng_systemd.control(\''+item.name+'\', \'stop\')">[停止]</a>';
                } else if (item.status === 'failed') {
                    status_html = '<span class="status-failed">异常崩溃(Failed)</span> <a class="btlink" onclick="yufeng_systemd.control(\''+item.name+'\', \'start\')">[修复启动]</a>';
                } else {
                    status_html = '<span class="status-inactive">已停止</span> <a class="btlink" onclick="yufeng_systemd.control(\''+item.name+'\', \'start\')">[启动]</a>';
                }
                
                var enabled_html = item.enabled ? 
                    '<span style="color:#20a53a">已开启</span> <a class="btlink" onclick="yufeng_systemd.control(\''+item.name+'\', \'disable\')">[关闭]</a>' : 
                    '<span style="color:#888">已关闭</span> <a class="btlink" onclick="yufeng_systemd.control(\''+item.name+'\', \'enable\')">[开启]</a>';
                    
                html += '<tr>' +
                        '<td>' + item.name + '</td>' +
                        '<td>' + status_html + '</td>' +
                        '<td>' + enabled_html + '</td>' +
                        '<td style="text-align: right;">' +
                            '<a class="btlink btn-yufeng" onclick="yufeng_systemd.get_logs(\''+item.name+'\')">日志</a> | ' +
                            '<a class="btlink btn-yufeng" onclick="yufeng_systemd.control(\''+item.name+'\', \'restart\')">重启</a> | ' +
                            '<a class="btlink btn-yufeng" onclick="yufeng_systemd.open_edit(\''+item.name+'\')">修改</a> | ' +
                            '<a class="btlink btn-yufeng" style="color:red;" onclick="yufeng_systemd.delete(\''+item.name+'\')">删除</a>' +
                        '</td>' +
                    '</tr>';
            }
            tbody.html(html);
        });
    },
    
    // 打开编辑/新增弹窗
    open_edit: function(service_name) {
        var is_edit = service_name ? true : false;
        var title = is_edit ? '修改服务 [' + service_name + ']' : '添加专属守护服务';
        
        var form_html = '<div class="pd15" id="yf_form">' +
            '<div class="bt-form">' +
                '<div class="line">' +
                    '<span class="tname">服务名称</span>' +
                    '<div class="info-r">' +
                        '<input name="service_name" class="bt-input-text" type="text" value="' + (service_name||'') + '" ' + (is_edit?'readonly style="background:#eee;"':'') + ' placeholder="仅限英文字母、数字、下划线、中划线">' +
                    '</div>' +
                '</div>' +
                '<div class="line">' +
                    '<span class="tname">配置模式</span>' +
                    '<div class="info-r">' +
                        '<select class="bt-input-text" name="mode" onchange="yufeng_systemd.toggle_mode(this.value)">' +
                            '<option value="simple">极简向导模式 (推荐)</option>' +
                            '<option value="advanced">高级代码模式</option>' +
                        '</select>' +
                        '<span class="c9" style="margin-left: 10px;">无论哪种模式，底层均会强制接管并注入 YuFeng 标签</span>' +
                    '</div>' +
                '</div>' +
                
                '<!-- 极简模式区域 -->' +
                '<div id="yf_simple_area">' +
                    '<div class="line">' +
                        '<span class="tname">运行用户</span>' +
                        '<div class="info-r">' +
                            '<select class="bt-input-text" name="run_user">' +
                                '<option value="www">www (推荐)</option>' +
                                '<option value="root">root (最高权限，极不推荐Web服务使用)</option>' +
                            '</select>' +
                        '</div>' +
                    '</div>' +
                    '<div class="line">' +
                        '<span class="tname">项目路径</span>' +
                        '<div class="info-r">' +
                            '<input name="work_dir" class="bt-input-text mr5" type="text" style="width:300px;" value="" placeholder="必须为绝对路径，如 /www/wwwroot/my_site">' +
                            '<span class="glyphicon glyphicon-folder-open cursor" onclick="bt.select_path(\'work_dir\')"></span>' +
                        '</div>' +
                    '</div>' +
                    '<div class="line">' +
                        '<span class="tname">启动命令</span>' +
                        '<div class="info-r">' +
                            '<input name="exec_start" class="bt-input-text" type="text" style="width:300px;" value="" placeholder="如: /usr/bin/node server.js">' +
                        '</div>' +
                    '</div>' +
                '</div>' +
                
                '<!-- 高级模式区域 -->' +
                '<div id="yf_advanced_area" style="display:none;">' +
                    '<div class="line">' +
                        '<span class="tname">服务配置</span>' +
                        '<div class="info-r">' +
                            '<textarea name="service_content" class="bt-input-text" style="width: 400px; height: 200px; background:#222; color:#0f0; padding:10px; font-family: Consolas, monospace;"></textarea>' +
                            '<p class="c9 mt10">请务必保留 [Unit] 和 [Service] 节点。Documentation 标签系统将在后台强制覆盖。</p>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
                
                '<div class="line">' +
                    '<div class="info-r" style="margin-top: 20px;">' +
                        '<button class="btn btn-success btn-sm" onclick="yufeng_systemd.save_service()">提交保存</button>' +
                    '</div>' +
                '</div>' +
            '</div>' +
        '</div>';
        
        layer.open({
            type: 1,
            title: title,
            area: ['600px', '500px'],
            closeBtn: 1,
            shadeClose: false,
            content: form_html,
            success: function(layero, index) {
                // 如果是编辑高级模式，需要回显数据
                if (is_edit) {
                    var loadT = layer.msg('正在获取配置...', {icon:16, time:0});
                    yufeng_systemd.request('get_service_detail', {service_name: service_name}, function(res) {
                        layer.close(loadT);
                        if(res.status) {
                            $('textarea[name="service_content"]').val(res.data);
                            // 由于解析简单内容较为复杂，编辑模式下默认推荐使用高级模式回显
                            $('select[name="mode"]').val('advanced').trigger('change');
                        }
                    });
                } else {
                    var default_tpl = "[Unit]\nDescription=Managed by BT yufeng_systemd Plugin\nAfter=network-online.target\n\n[Service]\nType=simple\nUser=www\nWorkingDirectory=/www/wwwroot/\nExecStart=\nRestart=always\nRestartSec=5\n\n[Install]\nWantedBy=multi-user.target\n";
                    $('textarea[name="service_content"]').val(default_tpl);
                }
            }
        });
    },
    
    toggle_mode: function(mode) {
        if (mode === 'simple') {
            $('#yf_simple_area').show();
            $('#yf_advanced_area').hide();
        } else {
            $('#yf_simple_area').hide();
            $('#yf_advanced_area').show();
        }
    },
    
    save_service: function() {
        var data = {
            service_name: $('input[name="service_name"]').val(),
            mode: $('select[name="mode"]').val()
        };
        
        if (!data.service_name) {
            layer.msg('服务名称不能为空', {icon: 2});
            return;
        }
        
        if (data.mode === 'simple') {
            data.run_user = $('select[name="run_user"]').val();
            data.work_dir = $('input[name="work_dir"]').val();
            data.exec_start = $('input[name="exec_start"]').val();
            if (!data.work_dir || !data.exec_start) {
                layer.msg('项目路径和启动命令不能为空', {icon: 2});
                return;
            }
        } else {
            data.service_content = $('textarea[name="service_content"]').val();
            if (data.service_content.indexOf('[Unit]') === -1 || data.service_content.indexOf('[Service]') === -1) {
                layer.msg('高级配置必须包含 [Unit] 和 [Service] 节点', {icon: 2});
                return;
            }
        }
        
        var loadT = layer.msg('正在保存并重启服务...', {icon: 16, time: 0, shade: 0.3});
        this.request('create_or_modify_service', data, function(res) {
            layer.close(loadT);
            layer.msg(res.msg, {icon: res.status ? 1 : 2});
            if (res.status) {
                layer.closeAll('page');
                yufeng_systemd.get_list();
            }
        });
    },
    
    control: function(service_name, action) {
        var action_name = {
            'start': '启动',
            'stop': '停止',
            'restart': '重启',
            'enable': '开启自启',
            'disable': '关闭自启'
        }[action];
        
        layer.confirm('确定要 ' + action_name + ' 服务 [' + service_name + '] 吗？', {icon: 3, title: '提示'}, function(index) {
            layer.close(index);
            var loadT = layer.msg('正在执行...', {icon: 16, time: 0, shade: 0.3});
            yufeng_systemd.request('control_service', {service_name: service_name, action: action}, function(res) {
                layer.close(loadT);
                layer.msg(res.msg, {icon: res.status ? 1 : 2});
                if (res.status) {
                    yufeng_systemd.get_list();
                }
            });
        });
    },
    
    delete: function(service_name) {
        layer.confirm('确定要彻底删除专属守护服务 [' + service_name + '] 吗？<br><br><span style="color:red">注意：删除前必须先停止该服务。</span>', {icon: 3, title: '危险操作'}, function(index) {
            layer.close(index);
            var loadT = layer.msg('正在删除...', {icon: 16, time: 0, shade: 0.3});
            yufeng_systemd.request('delete_service', {service_name: service_name}, function(res) {
                layer.close(loadT);
                layer.msg(res.msg, {icon: res.status ? 1 : 2});
                if (res.status) {
                    yufeng_systemd.get_list();
                }
            });
        });
    },
    
    get_logs: function(service_name) {
        var loadT = layer.msg('正在获取日志...', {icon: 16, time: 0, shade: 0.3});
        this.request('get_service_logs', {service_name: service_name}, function(res) {
            layer.close(loadT);
            if (res.status) {
                var escapeHtml = function(text) {
                    var map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
                    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
                };
                var log_content = (window.bt && typeof bt.htmlEncode === 'function') ? bt.htmlEncode(res.data) : escapeHtml(res.data);
                
                var log_html = '<div style="padding: 10px; background-color: #333; color: #fff; height: 100%; overflow: auto; font-family: Consolas, monospace; font-size: 12px; white-space: pre-wrap;">' + log_content + '</div>';
                layer.open({
                    type: 1,
                    title: '运行日志 (最近100行防OOM) - [' + service_name + ']',
                    area: ['800px', '500px'],
                    shadeClose: true,
                    content: log_html
                });
            } else {
                layer.msg(res.msg, {icon: 2});
            }
        });
    },
    
    // 基础请求封装
    request: function(method, args, callback) {
        var url = '/plugin?action=a&name=' + this.plugin_name + '&s=' + method;
        $.ajax({
            url: url,
            type: 'POST',
            data: args,
            success: function(res) {
                if (typeof callback === 'function') {
                    callback(res);
                }
            },
            error: function() {
                layer.msg('网络请求异常，请检查面板后端日志。', {icon: 2});
            }
        });
    }
};
