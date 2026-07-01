

function pRead(){
	var readme = '<ul class="help-info-text c7">';
    readme += '<li>修改后,点击重启按钮</li>';
    readme += '</ul>';

    $('.soft-man-con').html(readme);   
}


//varnish负载状态  start
function varnishStatus() {
    var loadT = layer.msg('正在获取...', { icon: 16, time: 0, shade: 0.3 });
    $.post('/plugins/run', {name:'varnish', func:'run_info'}, function(data) {
        layer.close(loadT);
        if (!data.status){
            layer.msg(data.msg,{icon:0,time:2000,shade: [0.3, '#000']});
            var errorCon = '<div class="alert alert-warning" style="margin: 15px 0;">Varnish 状态获取失败：' + data.msg + '。请检查 Varnish 服务是否已启动并正常运行。</div>';
            $(".soft-man-con").html(errorCon);
            return;
        }

        var rdata;
        try {
            rdata = typeof(data.data) === 'string' ? JSON.parse(data.data) : data.data;
        } catch(e) {
            layer.msg('解析 Varnish 状态数据失败！', {icon: 0, time: 2000, shade: [0.3, '#000']});
            var errorCon = '<div class="alert alert-warning" style="margin: 15px 0;">解析 Varnish 状态数据失败。这通常是因为 Varnish 服务未正常启动或未生成状态 JSON 序列。</div>';
            $(".soft-man-con").html(errorCon);
            return;
        }

        if (!rdata) {
            var errorCon = '<div class="alert alert-warning" style="margin: 15px 0;">未获取到有效的 Varnish 运行状态。请确保服务已在“服务”标签页中启动。</div>';
            $(".soft-man-con").html(errorCon);
            return;
        }

        // 自适应不同 Varnish 版本的 JSON 数据结构 (有的版本 counters 嵌套在属性下)
        var counters = rdata.counters || rdata;
        var timestamp = rdata.timestamp || '';

        var hitVal = 0;
        var missVal = 0;
        var uptimeVal = 0;

        // 提取 cache_hit
        if (counters['MAIN.cache_hit']) {
            hitVal = parseInt(counters['MAIN.cache_hit'].value || 0);
        } else if (counters['cache_hit']) {
            hitVal = parseInt(counters['cache_hit'].value || 0);
        }

        // 提取 cache_miss
        if (counters['MAIN.cache_miss']) {
            missVal = parseInt(counters['MAIN.cache_miss'].value || 0);
        } else if (counters['cache_miss']) {
            missVal = parseInt(counters['cache_miss'].value || 0);
        }

        // 提取 uptime
        if (counters['MAIN.uptime']) {
            uptimeVal = parseInt(counters['MAIN.uptime'].value || 0);
        } else if (counters['uptime']) {
            uptimeVal = parseInt(counters['uptime'].value || 0);
        }

        // 计算命中率
        var total = hitVal + missVal;
        var hitRate = "0.00";
        if (total > 0) {
            hitRate = ((hitVal / total) * 100).toFixed(2);
        }

        // 格式化 Uptime 秒数为天小时分钟
        var uptimeStr = "0分钟";
        if (uptimeVal > 0) {
            var d = Math.floor(uptimeVal / 86400);
            var h = Math.floor((uptimeVal % 86400) / 3600);
            var m = Math.floor((uptimeVal % 3600) / 60);
            uptimeStr = "";
            if (d > 0) uptimeStr += d + "天";
            if (h > 0) uptimeStr += h + "小时";
            if (m > 0 || uptimeStr === "") uptimeStr += m + "分钟";
        }

        // 渲染现代玻璃拟态的缓存命中率看板卡片
        var headerHtml = '<div style="display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap;">\
            <div style="flex: 1; min-width: 140px; padding: 15px; background: rgba(255, 255, 255, 0.85); border: 1px solid rgba(0,0,0,0.06); border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.02); text-align: center; backdrop-filter: blur(5px);">\
                <div style="font-size: 12px; color: #777; margin-bottom: 5px;">缓存命中率 (Hit Rate)</div>\
                <div style="font-size: 24px; font-weight: 700; color: #20a53a; font-family: \'Outfit\', \'Inter\', sans-serif;">' + hitRate + '%</div>\
            </div>\
            <div style="flex: 1; min-width: 140px; padding: 15px; background: rgba(255, 255, 255, 0.85); border: 1px solid rgba(0,0,0,0.06); border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.02); text-align: center; backdrop-filter: blur(5px);">\
                <div style="font-size: 12px; color: #777; margin-bottom: 5px;">命中 / 未命中 (Hits/Misses)</div>\
                <div style="font-size: 20px; font-weight: 700; color: #333; font-family: \'Outfit\', \'Inter\', sans-serif;">' + hitVal + ' / ' + missVal + '</div>\
            </div>\
            <div style="flex: 1; min-width: 140px; padding: 15px; background: rgba(255, 255, 255, 0.85); border: 1px solid rgba(0,0,0,0.06); border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.02); text-align: center; backdrop-filter: blur(5px);">\
                <div style="font-size: 12px; color: #777; margin-bottom: 5px;">运行时间 (Uptime)</div>\
                <div style="font-size: 20px; font-weight: 700; color: #007bff; font-family: \'Outfit\', \'Inter\', sans-serif;">' + uptimeStr + '</div>\
            </div>\
        </div>';

        // 渲染表格，过滤多余属性并剥除 MAIN. 前缀，提升可读性
        var tmp = "";
        for (let i in counters) {
            if (i === 'timestamp' || i === 'version') continue;
            
            var item = counters[i];
            if (typeof(item) !== 'object') continue;
            
            var keyName = i.replace('MAIN.', '');
            var val = item.value !== undefined ? item.value : item;
            var desc = item.description || '';
            
            tmp += "<tr>\
                <td style='font-family: monospace; font-size: 12px; color: #555; font-weight: 500;'>" + keyName + "</td>\
                <td style='font-family: \"Outfit\", \"Inter\", sans-serif; font-weight: 600; color: #222;'>" + val + "</td>\
                <td style='color: #666; font-size: 13px;'>" + desc + "</td>\
            </tr>";
        }

        if (timestamp) {
            tmp += "<tr>\
                <td style='color: #888; font-weight: 500;'>采样时间 (timestamp)</td>\
                <td colspan='2' style='font-family: monospace; color: #444;'>" + timestamp + "</td>\
            </tr>";
        }

        var Con = headerHtml + '<div class="divtable" style="max-height: 400px; overflow-y: auto; border: 1px solid #ddd; border-radius: 8px;">\
                        <table class="table table-hover table-bordered" style="width: 100%; margin-bottom: 0;">\
                        <thead><tr style="background-color: #f8f9fa;"><th style="width: 35%;">字段</th><th style="width: 20%;">当前值</th><th style="width: 45%;">说明</th></tr></thead>\
                        <tbody>'+tmp+'</tbody>\
                </table></div>';
        $(".soft-man-con").html(Con);
    },'json');
}
//varnish负载状态 end



//varnish service --- 
function varnishPluginConfig(_name, version, func){
    if ( typeof(version) == 'undefined' ){
        version = '';
    }

    var func_name = 'conf';
    if ( typeof(func) != 'undefined' ){
        func_name = func;
    }

    var con = '<p style="color: #666; margin-bottom: 7px">提示：Ctrl+F 搜索关键字，Ctrl+G 查找下一个，Ctrl+S 保存，Ctrl+Shift+R 查找替换!</p>\
                <textarea class="bt-input-text" style="height: 320px; line-height:18px;" id="textBody"></textarea>\
                <button id="onlineEditFileBtn" class="btn btn-success btn-sm" style="margin-top:10px;">保存</button>\
                <ul class="help-info-text c7 ptb15">\
                    <li>此处为'+ _name + version +'主配置文件,若您不了解配置规则,请勿随意修改。</li>\
                </ul>';
    $(".soft-man-con").html(con);

    var loadT = layer.msg('配置文件路径获取中...',{icon:16,time:0,shade: [0.3, '#000']});
    $.post('/plugins/run', {name:_name, func:func_name,version:version},function (data) {
        layer.close(loadT);

        var loadT2 = layer.msg('文件内容获取中...',{icon:16,time:0,shade: [0.3, '#000']});
        var fileName = data.data;
        $.post('/files/get_body', 'path=' + fileName, function(rdata) {
            layer.close(loadT2);
            if (!rdata.status){
                layer.msg(rdata.msg,{icon:0,time:2000,shade: [0.3, '#000']});
                return;
            }
            $("#textBody").empty().text(rdata.data.data);
            $(".CodeMirror").remove();
            var editor = CodeMirror.fromTextArea(document.getElementById("textBody"), {
                extraKeys: {
                    "Ctrl-Space": "autocomplete",
                    "Ctrl-F": "findPersistent",
                    "Ctrl-H": "replaceAll",
                    "Ctrl-S": function() {
                        $("#textBody").text(editor.getValue());
                        pluginConfigSave(fileName);
                    }
                },
                lineNumbers: true,
                matchBrackets:true,
            });
            editor.focus();
            $(".CodeMirror-scroll").css({"height":"300px","margin":0,"padding":0});
            $("#onlineEditFileBtn").click(function(){
                $("#textBody").text(editor.getValue());
                pluginConfigSave(fileName);
            });
        },'json');
    },'json');
}
