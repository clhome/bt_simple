// 全局 JS 错误捕获，方便诊断无反应的异常
window.onerror = function(message, source, lineno, colno, error) {
    var err_msg = "JS 异常: " + message + "\n文件: " + source + "\n行号: " + lineno + ":" + colno;
    console.error(err_msg, error);
    if (window.layer) {
        layer.alert(err_msg.replace(/\n/g, '<br>'), {icon: 2, title: "JavaScript 运行错误"});
    } else {
        alert(err_msg);
    }
    return false;
};

var yufeng_systemd = {
    plugin_name: 'yufeng_systemd',
    
    init: function() {
        this.show_tab('config');
        this.get_list();
    },
    
    show_tab: function(tab_name) {
        $('.tab-con').hide();
        $('#yufeng_' + tab_name + '_tab').show();
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
                    status_html = '<a class="btn btn-success btn-xs" onclick="yufeng_systemd.control(\''+item.name+'\', \'stop\')" title="点击停止服务" style="width:80px;">运行中 ▶</a>';
                } else if (item.status === 'failed') {
                    status_html = '<a class="btn btn-warning btn-xs" onclick="yufeng_systemd.control(\''+item.name+'\', \'start\')" title="点击尝试修复并启动" style="width:80px;">崩溃报错 ⚠</a>';
                } else {
                    status_html = '<a class="btn btn-danger btn-xs" onclick="yufeng_systemd.control(\''+item.name+'\', \'start\')" title="点击启动服务" style="width:80px;">已停止 ⏹</a>';
                }
                
                var enabled_html = item.enabled ? 
                    '<a class="btn btn-success btn-xs" onclick="yufeng_systemd.control(\''+item.name+'\', \'disable\')" title="点击取消开机自启" style="width:80px;">已开启 ▶</a>' : 
                    '<a class="btn btn-default btn-xs" onclick="yufeng_systemd.control(\''+item.name+'\', \'enable\')" title="点击允许开机自启" style="width:80px;">已关闭 ⏹</a>';
                    
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
        
        var form_html = '<div id="yufeng_service_form" class="bt-form pd20">' +
            '<div class="form-horizontal">' +
                '<div class="line">' +
                    '<span class="tname">服务名称</span>' +
                    '<div class="info-r">' +
                        '<input name="service_name" class="bt-input-text mr5" type="text" style="width:150px; ' + (is_edit ? 'background-color: #f5f5f5;' : '') + '" value="' + (service_name||'') + '" ' + (is_edit?'readonly':'') + ' placeholder="如: my_node_app">' +
                        '<span style="color: #ff4d4f; margin-left: 10px; font-weight: bold;">请勿使用中文名称</span>' +
                    '</div>' +
                '</div>' +
                '<div class="line">' +
                    '<span class="tname">配置模式</span>' +
                    '<div class="info-r">' +
                        '<select class="bt-input-text mr5" name="mode" onchange="yufeng_systemd.toggle_mode(this.value)">' +
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
                            '<input id="work_dir" name="work_dir" class="bt-input-text mr5" type="text" style="width:380px;" value="" placeholder="必须为绝对路径，如 /www/wwwroot/my_site">' +
                            '<span class="glyphicon glyphicon-folder-open cursor" onclick="changePath(\'work_dir\')"></span>' +
                        '</div>' +
                    '</div>' +
                    '<div class="line">' +
                        '<span class="tname">启动命令</span>' +
                        '<div class="info-r">' +
                            '<input name="exec_start" class="bt-input-text" type="text" style="width:410px;" value="" placeholder="如: /usr/bin/node server.js">' +
                        '</div>' +
                    '</div>' +
                    '<div class="line" style="margin-top: 15px;">' +
                        '<span class="tname"></span>' +
                        '<div class="info-r">' +
                            '<div style="background-color: #fcf8e3; border: 1px solid #faebcc; border-radius: 4px; padding: 10px; width: 410px; font-size: 12px; color: #8a6d3b; line-height: 1.6;">' +
                                '<strong>Python 虚拟环境启动示例：</strong><br>' +
                                '<code style="font-family: Consolas, monospace; background: none; border: none; color: #c7254e; padding: 0; font-weight: bold; word-break: break-all;">/www/wwwroot/my_python_project/venv/bin/python main.py</code>' +
                            '</div>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
                
                '<!-- 高级模式区域 -->' +
                '<div id="yf_advanced_area" style="display:none;">' +
                    '<div class="line">' +
                        '<span class="tname">服务配置</span>' +
                        '<div class="info-r">' +
                            '<textarea name="service_content" class="bt-input-text" style="width: 440px; height: 290px; background:#222; color:#0f0; padding:10px; font-family: Consolas, monospace; line-height: 1.3;"></textarea>' +
                            '<p class="c9 mt10">请务必保留 [Unit] 和 [Service] 节点。Documentation 标签系统将在后台强制覆盖。</p>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
            '</div>' +
        '</div>';
        
        layer.open({
            type: 1,
            title: title,
            area: ['600px', '520px'],
            offset: 'auto',
            closeBtn: 1,
            shadeClose: false,
            btn: ['提交保存', '取消'],
            content: form_html,
            yes: function(index, layero) {
                yufeng_systemd.save_service();
            },
            success: function(layero, index) {
                // 如果是编辑高级模式，需要回显数据
                if (is_edit) {
                    var loadT = layer.msg('正在获取配置...', {icon:16, time:0});
                    yufeng_systemd.request('get_service_detail', {service_name: service_name}, function(res) {
                        layer.close(loadT);
                        if(res.status) {
                            var content = res.data;
                            $('#yufeng_service_form textarea[name="service_content"]').val(content);
                            
                            // 尝试回显极简模式的数据
                            var userMatch = content.match(/^User=(.*)$/m);
                            var workDirMatch = content.match(/^WorkingDirectory=(.*)$/m);
                            var execStartMatch = content.match(/^ExecStart=(.*)$/m);
                            
                            if (userMatch && workDirMatch && execStartMatch) {
                                $('#yufeng_service_form select[name="run_user"]').val(String(userMatch[1]).trim());
                                $('#yufeng_service_form input[name="work_dir"]').val(String(workDirMatch[1]).trim());
                                $('#yufeng_service_form input[name="exec_start"]').val(String(execStartMatch[1]).trim());
                                // 如果能成功解析关键字段，则默认停留在极简模式
                                $('#yufeng_service_form select[name="mode"]').val('simple').trigger('change');
                            } else {
                                // 结构复杂，退化到高级模式
                                $('#yufeng_service_form select[name="mode"]').val('advanced').trigger('change');
                            }
                        }
                    });
                } else {
                    var default_tpl = "[Unit]\nDescription=Managed by yufeng_systemd Plugin\nAfter=network-online.target\n\n[Service]\nType=simple\nUser=www\nWorkingDirectory=/www/wwwroot/\nExecStart=\nRestart=always\nRestartSec=5\n\n[Install]\nWantedBy=multi-user.target\n";
                    $('#yufeng_service_form textarea[name="service_content"]').val(default_tpl);
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
            service_name: $('#yufeng_service_form input[name="service_name"]').val(),
            mode: $('#yufeng_service_form select[name="mode"]').val()
        };
        
        if (!data.service_name) {
            layer.msg('服务名称不能为空', {icon: 2});
            return;
        }
        
        // 校验服务名称格式，防止非 ASCII 字符或非法字符导致 Systemd 报错或后端拦截无反应
        var name_pattern = /^[a-zA-Z0-9_-]+$/;
        if (!name_pattern.test(data.service_name)) {
            layer.msg('服务名只能包含字母、数字、下划线和中划线！', {icon: 2});
            return;
        }
        
        if (data.mode === 'simple') {
            data.run_user = $('#yufeng_service_form select[name="run_user"]').val();
            data.work_dir = $('#yufeng_service_form input[name="work_dir"]').val();
            data.exec_start = $('#yufeng_service_form input[name="exec_start"]').val();
            if (!data.work_dir || !data.exec_start) {
                layer.msg('项目路径和启动命令不能为空', {icon: 2});
                return;
            }
        } else {
            data.service_content = $('#yufeng_service_form textarea[name="service_content"]').val();
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
                
                var log_html = '<div id="yufeng_log_box" style="padding: 10px; background-color: #333; color: #fff; height: 380px; overflow: auto; font-family: Consolas, monospace; font-size: 12px; white-space: pre-wrap;">' + (log_content || '暂无运行日志') + '</div>';
                layer.open({
                    type: 1,
                    title: '运行日志 (最近100行防OOM) - [' + service_name + ']',
                    area: ['800px', '500px'],
                    shadeClose: true,
                    btn: ['清空日志', '关闭'],
                    content: log_html,
                    yes: function(index, layero) {
                        layer.confirm('确定要清空该服务的运行日志吗？', {icon: 3, title: '提示'}, function(c_index) {
                            layer.close(c_index);
                            var loadC = layer.msg('正在清空...', {icon: 16, time: 0, shade: 0.3});
                            yufeng_systemd.request('clear_service_logs', {service_name: service_name}, function(c_res) {
                                layer.close(loadC);
                                layer.msg(c_res.msg, {icon: c_res.status ? 1 : 2});
                                if (c_res.status) {
                                    yufeng_systemd.request('get_service_logs', {service_name: service_name}, function(new_res) {
                                        if (new_res.status) {
                                            var new_log = (window.bt && typeof bt.htmlEncode === 'function') ? bt.htmlEncode(new_res.data) : escapeHtml(new_res.data);
                                            $('#yufeng_log_box').html(new_log || '暂无运行日志');
                                        }
                                    });
                                }
                            });
                        });
                    }
                });
            } else {
                layer.msg(res.msg, {icon: 2});
            }
        });
    },
    
    // 基础请求封装
    request: function(method, args, callback) {
        var req_data = {
            name: this.plugin_name,
            func: method,
            args: btoa(encodeURIComponent(JSON.stringify(args))),
            version: ''
        };
        $.ajax({
            url: '/plugins/run',
            type: 'POST',
            data: req_data,
            dataType: 'json',
            success: function(data) {
                if (!data.status) {
                    layer.msg(data.msg, {icon: 2});
                    return;
                }
                var rdata;
                try {
                    rdata = JSON.parse(data.data);
                } catch (e) {
                    rdata = data.data;
                }
                if (typeof callback === 'function') {
                    callback(rdata);
                }
            },
            error: function() {
                layer.msg('网络请求异常，请检查面板后端日志。', {icon: 2});
            }
        });
    },
    
    copy_text: function(text) {
        var tempInput = document.createElement("input");
        tempInput.value = text;
        document.body.appendChild(tempInput);
        tempInput.select();
        document.execCommand("copy");
        document.body.removeChild(tempInput);
        layer.msg('已复制示例命令到剪贴板', {icon: 1, time: 1000});
    }
};

window.yufeng_systemd = yufeng_systemd;
