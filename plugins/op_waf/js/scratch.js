
function setHoneypotDialog() {
    owPost('waf_conf', {}, function(data){
        var tmp = $.parseJSON(data.data);
        var rdata = $.parseJSON(tmp.data);
        var paths = [];
        if (rdata.honeypot && rdata.honeypot.paths) {
            paths = rdata.honeypot.paths;
        }

        var html = '<div style="padding: 20px;">\
            <div style="margin-bottom: 15px; color:#666;">\
                请配置高危蜜罐路径（每行一个）。当访客尝试请求以下任意路径时，防火墙会立刻将其信誉积分扣满（默认 100 分）并触发封禁。推荐填入不存在的敏感路径。\
            </div>\
            <textarea id="honeypot_paths_input" style="width: 100%; height: 250px; line-height: 22px; padding: 10px; border: 1px solid #ccc; border-radius: 4px; resize: vertical; white-space: pre; font-family: Consolas, monospace;">' + paths.join('\n') + '</textarea>\
            <div style="margin-top: 15px; text-align: right;">\
                <button class="btn btn-success btn-sm" onclick="saveHoneypotPaths()">保存配置</button>\
            </div>\
        </div>';

        layer.open({
            type: 1,
            title: '蜜罐高危路径配置',
            area: ['500px', '450px'],
            closeBtn: 1,
            shadeClose: false,
            content: html
        });
    });
}

function saveHoneypotPaths() {
    var rawText = $('#honeypot_paths_input').val();
    var lines = rawText.split('\n');
    var paths = [];
    for (var i = 0; i < lines.length; i++) {
        var line = $.trim(lines[i]);
        if (line !== '') {
            if (line.charAt(0) !== '/') {
                line = '/' + line;
            }
            paths.push(line);
        }
    }
    
    var loadT = layer.msg('正在保存配置...', {icon: 16, time: 0, shade: 0.3});
    owPost('setHoneypotPaths', {paths: JSON.stringify(paths)}, function(res_raw) {
        layer.close(loadT);
        var res = $.parseJSON(res_raw.data);
        layer.msg(res.msg, {icon: res.status ? 1 : 2});
        if (res.status) {
            setTimeout(function(){
                layer.closeAll();
                wafGloabl();
            }, 1000);
        }
    });
}
