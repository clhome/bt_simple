var ollama = {
    plugin_name: 'ollama',
    pull_timer: null,

    init: function () {
        var _this = this;
        
        // 动态注入精心准备的高端现代 Vanilla CSS 样式系统
        var style = '<style id="ollama-dynamic-style">' +
            '.ollama-container { padding: 5px 15px; }' +
            '.ollama-card {' +
            '    background: rgba(255, 255, 255, 0.85);' +
            '    border-radius: 12px;' +
            '    padding: 20px;' +
            '    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04);' +
            '    margin-bottom: 20px;' +
            '    border: 1px solid rgba(255, 255, 255, 0.7);' +
            '    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);' +
            '}' +
            '.ollama-card:hover {' +
            '    transform: translateY(-3px);' +
            '    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.07);' +
            '}' +
            '.ollama-flex { display: flex; gap: 20px; }' +
            '.ollama-flex-col { flex: 1; }' +
            '.ollama-btn {' +
            '    border-radius: 6px;' +
            '    padding: 7px 18px;' +
            '    font-weight: 500;' +
            '    transition: all 0.2s ease;' +
            '    display: inline-block;' +
            '    cursor: pointer;' +
            '    border: none;' +
            '    outline: none;' +
            '    text-align: center;' +
            '    font-size: 13px;' +
            '}' +
            '.ollama-btn-primary {' +
            '    background: linear-gradient(135deg, #4f46e5, #6366f1);' +
            '    color: white !important;' +
            '}' +
            '.ollama-btn-primary:hover {' +
            '    background: linear-gradient(135deg, #4338ca, #4f46e5);' +
            '    box-shadow: 0 4px 12px rgba(79, 70, 229, 0.25);' +
            '}' +
            '.ollama-btn-primary:active { transform: scale(0.96); }' +
            '.ollama-btn-danger {' +
            '    background: #ef4444;' +
            '    color: white !important;' +
            '}' +
            '.ollama-btn-danger:hover {' +
            '    background: #dc2626;' +
            '    box-shadow: 0 4px 12px rgba(239, 68, 68, 0.25);' +
            '}' +
            '.ollama-btn-danger:active { transform: scale(0.96); }' +
            '.ollama-btn-default {' +
            '    background: #f1f5f9;' +
            '    color: #475569 !important;' +
            '    border: 1px solid #e2e8f0;' +
            '}' +
            '.ollama-btn-default:hover {' +
            '    background: #e2e8f0;' +
            '}' +
            '.ollama-input {' +
            '    border: 1px solid #cbd5e1;' +
            '    border-radius: 6px;' +
            '    padding: 8px 12px;' +
            '    outline: none;' +
            '    transition: all 0.2s ease;' +
            '    width: 100%;' +
            '    font-size: 13px;' +
            '}' +
            '.ollama-input:focus {' +
            '    border-color: #6366f1;' +
            '    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);' +
            '}' +
            '.ollama-textarea {' +
            '    width: 100%;' +
            '    height: 400px;' +
            '    background-color: #1e1e2e;' +
            '    color: #cdd6f4;' +
            '    font-family: "Consolas", "Courier New", monospace;' +
            '    padding: 15px;' +
            '    border-radius: 8px;' +
            '    border: 1px solid #313244;' +
            '    resize: none;' +
            '    outline: none;' +
            '    line-height: 1.5;' +
            '}' +
            '.ollama-table {' +
            '    width: 100%;' +
            '    border-collapse: collapse;' +
            '    margin-top: 10px;' +
            '}' +
            '.ollama-table th {' +
            '    background: #f8fafc;' +
            '    color: #64748b;' +
            '    font-weight: 600;' +
            '    padding: 10px 12px;' +
            '    border-bottom: 2px solid #e2e8f0;' +
            '    text-align: left;' +
            '    font-size: 13px;' +
            '}' +
            '.ollama-table td {' +
            '    padding: 11px 12px;' +
            '    border-bottom: 1px solid #f1f5f9;' +
            '    color: #334155;' +
            '    font-size: 13px;' +
            '}' +
            '.ollama-form-group {' +
            '    margin-bottom: 16px;' +
            '}' +
            '.ollama-form-label {' +
            '    display: block;' +
            '    font-weight: 600;' +
            '    color: #475569;' +
            '    margin-bottom: 6px;' +
            '    font-size: 13px;' +
            '}' +
            '.ollama-tip {' +
            '    font-size: 12px;' +
            '    color: #94a3b8;' +
            '    margin-top: 5px;' +
            '}' +
            '.ollama-help-card {' +
            '    background: #f8fafc;' +
            '    border-left: 4px solid #6366f1;' +
            '    border-radius: 4px;' +
            '    padding: 12px 16px;' +
            '    margin-bottom: 15px;' +
            '}' +
            '.ollama-help-code {' +
            '    background: #e2e8f0;' +
            '    padding: 2px 6px;' +
            '    border-radius: 4px;' +
            '    font-family: monospace;' +
            '    color: #be123c;' +
            '}' +
            '</style>';

        if ($('#ollama-dynamic-style').length === 0) {
            $('head').append(style);
        }

        // 绑定菜单栏高亮点击行为
        $('.bt-w-menu p').off('click').click(function () {
            $(this).addClass('bgw').siblings().removeClass('bgw');
        });
    },

    send: function (info) {
        var tips = info['tips'];
        var method = info['method'];
        var args = info['data'] || {};
        var callback = info['success'];

        var loadT = layer.msg(tips, { icon: 16, time: 0, shade: 0.3 });

        var data = {};
        data['name'] = this.plugin_name;
        data['func'] = method;
        data['version'] = $('.plugin_version').attr('version') || '1.1';
        data['args'] = JSON.stringify(args);

        $.post('/plugins/run', data, function (res) {
            layer.close(loadT);
            if (!res.status) {
                layer.msg(res.msg, { icon: 2, time: 5000 });
                return;
            }

            var ret_data = null;
            try {
                ret_data = JSON.parse(res.data);
            } catch (e) {
                ret_data = res.data;
            }

            if (typeof (callback) == 'function') {
                callback(ret_data);
            }
        }, 'json').fail(function () {
            layer.close(loadT);
            layer.msg('请求后端接口失败！', { icon: 2, time: 3000 });
        });
    },

    // --- 服务管理模块 ---
    service: function () {
        pluginService('ollama', $('.plugin_version').attr('version'));
        setTimeout(function() {
            ollama.send({
                tips: '正在获取访问信息...',
                method: 'get_ollama_access_info',
                success: function (res) {
                    if (!res.status) {
                        return;
                    }
                    var info = res.data;
                    var html = `
                    <div class="ollama-access-info">
                        <div class="ollama-info-header"><span class="glyphicon glyphicon-link"></span> 远程访问与接口测试指南</div>
                        <div class="ollama-info-body">
                            <div class="ollama-info-desc">
                                如需让局域网内其他主机或公网访问本机的 Ollama API 服务，请进入 <b>“服务配置”</b> 菜单，将绑定 Host 修改为 <code style="color:#d9534f;background:#f9f2f4;padding:2px 4px;border-radius:3px;">0.0.0.0:11434</code>，并勾选允许放行防火墙选项。配置生效后，您可通过以下地址进行 API 连通性测试：
                            </div>
                            <div class="ollama-info-item">
                                <span class="ollama-info-label">内网地址：</span>
                                <a href="` + info.internal_url + `" target="_blank" class="ollama-info-value ollama-link">` + info.internal_url + `</a>
                            </div>
                            <div class="ollama-info-item">
                                <span class="ollama-info-label">外网地址：</span>
                                <a href="` + info.external_url + `" target="_blank" class="ollama-info-value ollama-link">` + info.external_url + `</a>
                            </div>
                        </div>
                    </div>
                    `;
                    var style = `
                    <style>
                    .ollama-access-info {
                        margin-top: 20px;
                        border: 1px solid #e5e7eb;
                        border-radius: 8px;
                        background-color: #ffffff;
                        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
                        overflow: hidden;
                        font-size: 13px;
                        color: #374151;
                        transition: all 0.3s ease;
                    }
                    .ollama-access-info:hover {
                        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -2px rgba(0, 0, 0, 0.04);
                    }
                    .ollama-info-header {
                        padding: 12px 16px;
                        background: linear-gradient(to right, #f8fafc, #f1f5f9);
                        border-bottom: 1px solid #e5e7eb;
                        font-weight: 600;
                        color: #1e293b;
                        font-size: 14px;
                    }
                    .ollama-info-body {
                        padding: 16px;
                    }
                    .ollama-info-desc {
                        margin-bottom: 15px;
                        line-height: 1.6;
                        color: #475569;
                    }
                    .ollama-info-item {
                        display: flex;
                        margin-bottom: 12px;
                        align-items: center;
                    }
                    .ollama-info-item:last-child {
                        margin-bottom: 0;
                    }
                    .ollama-info-label {
                        width: 80px;
                        color: #64748b;
                        font-weight: 500;
                    }
                    .ollama-info-value {
                        flex: 1;
                        color: #0f172a;
                        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
                        background: #f8fafc;
                        padding: 4px 10px;
                        border-radius: 6px;
                        border: 1px solid #e2e8f0;
                        word-break: break-all;
                    }
                    .ollama-link {
                        color: #4f46e5;
                        text-decoration: none;
                        transition: all 0.2s;
                    }
                    .ollama-link:hover {
                        color: #4338ca;
                        text-decoration: underline;
                        background: #e0e7ff;
                        border-color: #c7d2fe;
                    }
                    </style>
                    `;
                    if ($(".ollama-access-info").length == 0) {
                        $(".soft-man-con").append(style + html);
                    }
                }
            });
        }, 500);
    },

    // --- 大模型管理模块 ---
    models: function () {
        var _this = this;
        var html = '<div class="ollama-container">';
        
        // 核心双栏布局卡片
        html += '<div class="ollama-flex">';
        
        // 左栏：拉取模型卡片
        html += '  <div class="ollama-flex-col" style="flex: 0 0 320px;">';
        html += '    <div class="ollama-card">';
        html += '      <h4 style="margin-top:0;margin-bottom:15px;color:#1e293b;font-weight:600;font-size:14px;">拉取新模型 (Pull Model)</h4>';
        html += '      <div class="ollama-form-group">';
        html += '        <label class="ollama-form-label">模型名 / 标签</label>';
        html += '        <input type="text" id="pull_model_input" class="ollama-input" placeholder="输入如: deepseek-r1:7b">';
        html += '        <p class="ollama-tip">输入想下载的 Ollama 官方模型与版本号，模型名字可在 Ollama 官网库中检索。</p>';
        html += '      </div>';
        html += '      <button class="ollama-btn ollama-btn-primary" style="width:100%;" onclick="ollama.pullModel()">立即开始拉取</button>';
        html += '    </div>';
        html += '  </div>';

        // 右栏：已下载模型卡片
        html += '  <div class="ollama-flex-col">';
        html += '    <div class="ollama-card">';
        html += '      <h4 style="margin-top:0;margin-bottom:15px;color:#1e293b;font-weight:600;font-size:14px;">本地大模型库 (Local Library)</h4>';
        html += '      <div id="local_models_list" style="max-height: 250px; overflow-y: auto;">';
        html += '        <p style="color:#64748b;">正在加载模型列表...</p>';
        html += '      </div>';
        html += '    </div>';
        html += '  </div>';
        
        html += '</div>'; // End ollama-flex

        // 下卡片：驻留内存大模型卡片
        html += '<div class="ollama-card" style="margin-top:10px;">';
        html += '  <h4 style="margin-top:0;margin-bottom:15px;color:#1e293b;font-weight:600;font-size:14px;">正在内存/显存运行中模型 (Running Models)</h4>';
        html += '  <div id="running_models_list">';
        html += '    <p style="color:#64748b;">正在加载运行模型...</p>';
        html += '  </div>';
        html += '</div>';

        html += '</div>';

        $('.soft-man-con').html(html);

        // 异步渲染列表数据
        _this.refreshModelsList();
    },

    refreshModelsList: function () {
        var _this = this;
        
        // 1. 刷新已下载模型
        _this.send({
            tips: '正在读取本地大模型库...',
            method: 'get_models',
            success: function (res) {
                var container = $('#local_models_list');
                if (!res.status) {
                    container.html('<p style="color:#ef4444;font-size:13px;padding:10px 0;"><span class="glyphicon glyphicon-warning-sign"></span> ' + res.msg + '</p>');
                    return;
                }
                
                var models = res.data;
                if (!models || models.length === 0) {
                    container.html('<p style="color:#64748b;text-align:center;padding:25px 0;">当前本地库无模型，请在左侧拉取下载！</p>');
                    return;
                }

                var listHtml = '<table class="ollama-table">';
                listHtml += '<thead><tr><th>模型名称</th><th>ID</th><th>大小</th><th>修改时间</th><th style="text-align:right;">操作</th></tr></thead><tbody>';
                for (var i = 0; i < models.length; i++) {
                    var m = models[i];
                    listHtml += '<tr>';
                    listHtml += '  <td style="font-weight:600;">' + m.name + '</td>';
                    listHtml += '  <td><code style="font-size:11px;">' + m.id + '</code></td>';
                    listHtml += '  <td>' + m.size + '</td>';
                    listHtml += '  <td>' + m.modified + '</td>';
                    listHtml += '  <td style="text-align:right;"><button class="ollama-btn ollama-btn-danger" style="padding:3px 10px;font-size:11px;" onclick="ollama.deleteModel(\'' + m.name + '\')">删除</button></td>';
                    listHtml += '</tr>';
                }
                listHtml += '</tbody></table>';
                container.html(listHtml);
            }
        });

        // 2. 刷新正在运行模型
        _this.send({
            tips: '正在读取运行中模型...',
            method: 'get_running_models',
            success: function (res) {
                var container = $('#running_models_list');
                if (!res.status) {
                    container.html('<p style="color:#64748b;">无法获取运行中模型，服务未启动或尚未加载模型。</p>');
                    return;
                }
                
                var models = res.data;
                if (!models || models.length === 0) {
                    container.html('<p style="color:#64748b;text-align:center;padding:15px 0;font-size:12px;background:#f8fafc;border-radius:6px;">当前没有模型在显存/内存中驻留（空闲 5 分钟后会自动卸载释出显存）</p>');
                    return;
                }

                var listHtml = '<table class="ollama-table">';
                listHtml += '<thead><tr><th>模型名称</th><th>ID</th><th>大小</th><th>运行计算介质</th><th>活跃释放剩余</th></tr></thead><tbody>';
                for (var i = 0; i < models.length; i++) {
                    var m = models[i];
                    listHtml += '<tr>';
                    listHtml += '  <td style="font-weight:600;color:#4f46e5;">' + m.name + '</td>';
                    listHtml += '  <td><code>' + m.id + '</code></td>';
                    listHtml += '  <td>' + m.size + '</td>';
                    listHtml += '  <td><span class="label label-success" style="font-size:11px;">' + m.processor + '</span></td>';
                    listHtml += '  <td>' + m.until + '</td>';
                    listHtml += '</tr>';
                }
                listHtml += '</tbody></table>';
                container.html(listHtml);
            }
        });
    },

    pullModel: function () {
        var _this = this;
        var model_name = $('#pull_model_input').val().trim();
        if (!model_name) {
            layer.msg('请输入要拉取的模型名称！', { icon: 2 });
            return;
        }

        _this.send({
            tips: '正在初始化后台拉取任务...',
            method: 'pull_model',
            data: { 'model_name': model_name },
            success: function (res) {
                if (!res.status) {
                    layer.msg(res.msg, { icon: 2 });
                    return;
                }
                
                // 拉取任务已启动，打开进度查看模态窗口
                _this.showPullProgressModal(model_name);
            }
        });
    },

    showPullProgressModal: function (model_name) {
        var _this = this;
        
        var modalHtml = '<div style="padding:15px;">' +
            '<p style="margin-bottom:10px;font-size:13px;font-weight:600;color:#334155;">正在拉取模型: <span style="color:#4f46e5;">' + model_name + '</span> (请勿关闭此窗口直到拉取完成)</p>' +
            '<textarea id="pull_log_textarea" class="ollama-textarea" readonly>正在加载拉取进度日志...\n</textarea>' +
            '</div>';

        var index = layer.open({
            type: 1,
            title: '模型拉取进度',
            area: ['600px', '500px'],
            content: modalHtml,
            cancel: function () {
                // 窗口关闭时清除定时器
                if (_this.pull_timer) {
                    clearInterval(_this.pull_timer);
                    _this.pull_timer = null;
                }
                // 刷新模型列表
                _this.refreshModelsList();
            }
        });

        // 启动轮询读取日志
        _this.pull_timer = setInterval(function () {
            _this.send({
                tips: '正在刷新进度...',
                method: 'get_pull_log',
                success: function (res) {
                    if (!res.status) return;
                    
                    var data = res.data;
                    var logArea = $('#pull_log_textarea');
                    
                    if (logArea.length > 0) {
                        logArea.val(data.log);
                        // 始终自动滚动至最底端
                        logArea.scrollTop(logArea[0].scrollHeight);
                    }

                    if (data.status === 'success') {
                        clearInterval(_this.pull_timer);
                        _this.pull_timer = null;
                        layer.msg('模型 ' + model_name + ' 下载拉取成功！', { icon: 1 });
                        setTimeout(function () {
                            layer.close(index);
                            _this.refreshModelsList();
                        }, 2000);
                    } else if (data.status === 'failed') {
                        clearInterval(_this.pull_timer);
                        _this.pull_timer = null;
                        layer.msg('模型拉取失败，请检查名称或网络！', { icon: 2 });
                    }
                }
            });
        }, 1200);
    },

    deleteModel: function (model_name) {
        var _this = this;
        
        layer.confirm('确认要彻底删除大模型 <b style="color:#ef4444;">' + model_name + '</b> 吗？这会立刻释放其占用的磁盘空间！', {
            title: '删除确认',
            icon: 3,
            btn: ['确认删除', '取消']
        }, function () {
            _this.send({
                tips: '正在从本地删除模型...',
                method: 'delete_model',
                data: { 'model_name': model_name },
                success: function (res) {
                    if (res.status) {
                        layer.msg(res.msg, { icon: 1 });
                        _this.refreshModelsList();
                    } else {
                        layer.msg(res.msg, { icon: 2 });
                    }
                }
            });
        });
    },

    // --- 服务配置配置模块 ---
    config: function () {
        var _this = this;
        
        _this.send({
            tips: '正在读取服务环境变量配置...',
            method: 'get_config',
            success: function (res) {
                if (!res.status) {
                    $('.soft-man-con').html('<p style="color:#ef4444;padding:20px;">' + res.msg + '</p>');
                    return;
                }

                var config = res.data;
                var html = '<div class="ollama-container">';
                html += '  <div class="ollama-card">';
                html += '    <h4 style="margin-top:0;margin-bottom:15px;color:#1e293b;font-weight:600;font-size:14px;">Ollama 服务环境变量配置</h4>';
                html += '    <div style="font-size:12px;color:#64748b;background:#f8fafc;padding:10px 15px;border-radius:6px;margin-bottom:15px;border:1px dashed #cbd5e1;">';
                html += '      <span class="glyphicon glyphicon-info-sign"></span> 系统已自动检索到配置文件: <code style="font-size:11px;">' + (config.service_file || '未找到') + '</code><br/>';
                html += '      配置保存后，插件会自动执行 <code style="font-size:10px;">systemctl daemon-reload</code> 与服务重启，使新配置即时生效。';
                html += '    </div>';

                // Host 配置
                html += '    <div class="ollama-form-group">';
                html += '      <label class="ollama-form-label">服务绑定 Host & 端口 (OLLAMA_HOST)</label>';
                html += '      <input type="text" id="cfg_host_input" class="ollama-input" value="' + config.host + '" placeholder="如: 127.0.0.1:11434">';
                html += '      <p class="ollama-tip">默认绑定 <code style="font-size:11px;">127.0.0.1:11434</code>。如果您想允许局域网或公网通过 Open WebUI 或 API 访问它，请更改为 <code style="font-size:11px;">0.0.0.0:11434</code>。</p>';
                html += '    </div>';

                // Models 路径配置
                html += '    <div class="ollama-form-group">';
                html += '      <label class="ollama-form-label">大模型存储物理目录 (OLLAMA_MODELS)</label>';
                html += '      <input type="text" id="cfg_models_input" class="ollama-input" value="' + config.models_path + '" placeholder="如: /usr/share/ollama/.ollama/models">';
                html += '      <p class="ollama-tip">大模型文件非常庞大，默认会存放在 root 的 home 盘下。若系统根分区较小，强烈建议修改为挂载了大数据盘的路径（例如 <code style="font-size:11px;">/www/server/ollama/models</code>）。</p>';
                html += '    </div>';

                // 防火墙联动
                var firewall_checked = config.port_open ? 'checked' : '';
                var is_disabled = config.host.indexOf('0.0.0.0') === -1 ? 'disabled' : '';
                
                html += '    <div class="ollama-form-group" id="firewall_group" style="padding:10px 0;">';
                html += '      <label style="font-weight:500;color:#475569;font-size:13px;cursor:pointer;display:inline-flex;align-items:center;">';
                html += '        <input type="checkbox" id="cfg_firewall_input" value="1" ' + firewall_checked + ' ' + is_disabled + ' style="margin-top:0;margin-right:8px;"> 自动在系统防火墙中放行 11434 端口（允许外网或跨主机访问）';
                html += '      </label>';
                html += '    </div>';

                // 提交按钮
                html += '    <button class="ollama-btn ollama-btn-primary" style="margin-top:10px;" onclick="ollama.saveConfig()">保存并应用配置</button>';
                html += '  </div>';
                html += '</div>';

                $('.soft-man-con').html(html);

                // 联动绑定，在 host 不为 0.0.0.0 时禁用防火墙选项
                $('#cfg_host_input').on('input propertychange', function () {
                    var hostVal = $(this).val();
                    if (hostVal.indexOf('0.0.0.0') !== -1) {
                        $('#cfg_firewall_input').prop('disabled', false);
                    } else {
                        $('#cfg_firewall_input').prop('disabled', true).prop('checked', false);
                    }
                });
            }
        });
    },

    saveConfig: function () {
        var _this = this;
        var host = $('#cfg_host_input').val().trim();
        var models_path = $('#cfg_models_input').val().trim();
        var port_open = $('#cfg_firewall_input').is(':checked');

        if (!host) {
            layer.msg('绑定 Host 不能为空！', { icon: 2 });
            return;
        }

        _this.send({
            tips: '正在重载 Systemd 并重启 Ollama 服务...',
            method: 'set_config',
            data: {
                'host': host,
                'models_path': models_path,
                'port_open': port_open ? 'true' : 'false'
            },
            success: function (res) {
                if (res.status) {
                    layer.msg(res.msg, { icon: 1 });
                    // 重刷配置页面
                    setTimeout(function () { _this.config(); }, 1000);
                } else {
                    layer.msg(res.msg, { icon: 2 });
                }
            }
        });
    },

    // --- 服务运行日志模块 ---
    logs: function () {
        var _this = this;
        var html = '<div class="ollama-container">';
        html += '  <div class="ollama-card">';
        html += '    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">';
        html += '      <h4 style="margin:0;color:#1e293b;font-weight:600;font-size:14px;">Ollama 运行系统日志 (最新 100 行)</h4>';
        html += '      <button class="ollama-btn ollama-btn-default" style="padding:4px 12px;font-size:11px;" onclick="ollama.refreshLogs()"><span class="glyphicon glyphicon-refresh"></span> 刷新日志</button>';
        html += '    </div>';
        html += '    <textarea id="ollama_log_textarea" class="ollama-textarea" style="height:390px;" readonly>正在加载系统服务日志...\n</textarea>';
        html += '  </div>';
        html += '</div>';

        $('.soft-man-con').html(html);

        _this.refreshLogs();
    },

    refreshLogs: function () {
        var _this = this;
        _this.send({
            tips: '正在获取系统运行日志...',
            method: 'get_service_logs',
            success: function (res) {
                var logArea = $('#ollama_log_textarea');
                if (!res.status) {
                    logArea.val('获取日志失败：' + res.msg);
                    return;
                }
                
                logArea.val(res.data);
                logArea.scrollTop(logArea[0].scrollHeight);
            }
        });
    },

    // --- 使用说明说明模块 ---
    readme: function () {
        var readme = '<div class="ollama-container">';
        readme += '  <div class="ollama-card">';
        readme += '    <h4 style="margin-top:0;margin-bottom:15px;color:#1e293b;font-weight:600;font-size:14px;">Ollama 快速集成与常用命令指引</h4>';
        
        readme += '    <div class="ollama-help-card">';
        readme += '      <strong>🖥️ 常用 Shell 命令操作：</strong><br/>';
        readme += '      您可在服务器终端通过以下常用命令对大模型进行管控与调试：';
        readme += '      <table class="table" style="margin-top:8px;font-size:12px;margin-bottom:0;">';
        readme += '        <tr><td><span class="ollama-help-code">ollama list</span></td><td>列出所有已下载的本地大模型库。</td></tr>';
        readme += '        <tr><td><span class="ollama-help-code">ollama run deepseek-r1:7b</span></td><td>交互式启动并进入指定大模型的命令行会话终端。</td></tr>';
        readme += '        <tr><td><span class="ollama-help-code">ollama ps</span></td><td>查看当前处于显存或内存活跃加载状态的模型。</td></tr>';
        readme += '        <tr><td><span class="ollama-help-code">ollama stop &lt;模型&gt;</span></td><td>从内存/显存中卸载释出特定大模型（不影响本地库）。</td></tr>';
        readme += '        <tr><td><span class="ollama-help-code">ollama rm &lt;模型&gt;</span></td><td>从本地库中永久物理删除对应模型以释放磁盘存储。</td></tr>';
        readme += '      </table>';
        readme += '    </div>';

        readme += '    <div class="ollama-help-card" style="border-left-color: #10b981;">';
        readme += '      <strong>🔌 API 对外集成说明：</strong><br/>';
        readme += '      Ollama 完美兼容 OpenAI 的标准的 API 通信协议，可通过配置为其他 Web UI 服务或 Python 脚本提供能力支持：<br/>';
        readme += '      <table class="table" style="margin-top:8px;font-size:12px;margin-bottom:0;">';
        readme += '        <tr><td><strong>API 端点 (Base URL)</strong></td><td><span class="ollama-help-code">http://&lt;服务器IP&gt;:11434/v1</span> (外网集成请在配置中绑定 0.0.0.0)</td></tr>';
        readme += '        <tr><td><strong>API Key (密钥)</strong></td><td>不需要任何 API Key。如有需要，可在前台客户端输入任意非空字符。</td></tr>';
        readme += '        <tr><td><strong>测试 API 连接命令</strong></td><td><span class="ollama-help-code">curl http://127.0.0.1:11434/api/tags</span></td></tr>';
        readme += '      </table>';
        readme += '    </div>';

        readme += '    <div class="ollama-help-card" style="border-left-color: #f59e0b;margin-bottom:0;">';
        readme += '      <strong>💡 极速安装与显卡驱动相关说明：</strong><br/>';
        readme += '      Ollama 会在启动模型时自动尝试探测服务器中安装的显卡（Nvidia GPU 等），如果 CUDA 驱动匹配，将会自动利用 GPU 加速大模型的吞吐渲染，使得响应输出快上数十倍！若无显卡，Ollama 将会回退使用 CPU 进行数学推理。';
        readme += '    </div>';
        
        readme += '  </div>';
        readme += '</div>';
        
        $('.soft-man-con').html(readme);
    }
};

