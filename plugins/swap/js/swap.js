

function swapPost(method, version, args,callback){
    var loadT = layer.msg('正在获取...', { icon: 16, time: 0, shade: 0.3 });

    var req_data = {};
    req_data['name'] = 'swap';
    req_data['func'] = method;
    req_data['version'] = version;
 
    if (typeof(args) == 'string'){
        req_data['args'] = JSON.stringify(toArrayObject(args));
    } else {
        req_data['args'] = JSON.stringify(args);
    }

    $.post('/plugins/run', req_data, function(data) {
        layer.close(loadT);
        if (!data.status){
            //错误展示10S
            layer.msg(data.msg,{icon:0,time:2000,shade: [10, '#000']});
            return;
        }

        if(typeof(callback) == 'function'){
            callback(data);
        }
    },'json'); 
}


function swapStatus() {
    swapPost('swap_status', '', {}, function(data){
        var rdata = $.parseJSON(data.data);
        var size = rdata.data['size'];
        var system_total = rdata.data['system_total'];

        var spCon = '<div class="conf_p" style="margin-top:30px;margin-bottom:0">\
                        <div style="border-bottom:#ccc 1px solid;padding-bottom:10px;margin-bottom:10px"><span><b>最大使用交换分区: </b></span>\
                        <select class="bt-input-text" name="swap_set" style="margin-left:-4px">\
                            <option value="218MB">218MB</option>\
                            <option value="512MB">512MB</option>\
                            <option value="1GB">1GB</option>\
                            <option value="2GB">2GB</option>\
                            <option value="4GB">4GB</option>\
                        </select>\
                        <span class="ml5">系统当前总 Swap: </span><input style="width:75px;background-color:#eee;text-align:center;font-weight:bold;" class="bt-input-text mr5" name="cur_system_total" type="text" value="' + system_total + '" readonly>MB\
                        <span>插件专属 Swap: </span><input style="width:70px;background-color:#eee;text-align:center;" class="bt-input-text mr5" name="cur_size" type="text" value="' + size + '" readonly>MB\
                        </div>\
                        <p><span>修改</span><input style="width: 70px;" class="bt-input-text mr5" name="size" value="' + size + '" type="number" >MB</p>\
                        <div style="margin-top:10px; padding-right:15px" class="text-right"><button class="btn btn-success btn-sm" onclick="submitSwap()">提交</button></div>\
                    </div>';

        $(".soft-man-con").html(spCon);

        $(".conf_p select[name='swap_set']").change(function() {
            var swap_size = $(this).val();
            if (swap_size.indexOf('GB')>-1){
                swap_size = parseInt(swap_size)*1024;
            } else{
                swap_size = parseInt(swap_size);
            }
            $("input[name='size']").val(swap_size);
        });
    });
}

function submitSwap(){
    var size = $("input[name='size']").val();
    swapPost('change_swap', '',{"size":size}, function(data){
        var rdata = $.parseJSON(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 5 });
        swapStatus();
    });
}

function readme(){
    var readme = '<div class="help-info-text c7" style="line-height:24px; font-size:13px; padding:15px; color:#555;">';
    readme += '<h4 style="margin-top:0; color:#222; font-weight:bold; border-bottom:1px solid #eee; padding-bottom:8px;">Swap (虚拟内存) 配置与使用指南</h4>';
    readme += '<p style="margin-top:10px; text-indent:2em;"><b>什么是 Swap？</b>Swap 也就是虚拟内存，当物理内存 (RAM) 不足时，Linux 系统会自动将部分闲置内存数据临时交换到磁盘上的专属 Swap 空间中，以保证系统稳定运行。配置 Swap 能极大防止因内存溢出 (OOM) 导致关键服务 (如 MySQL、Nginx 等) 被系统强制杀死的现象。</p>';
    readme += '<h5 style="margin-top:20px; color:#333; font-weight:bold;">1. 不同情况下的 Swap 大小配置建议：</h5>';
    readme += '<table class="table" style="width:100%; border-collapse:collapse; margin:10px 0; border:1px solid #e1e4e8; background-color:#fff;">';
    readme += '  <thead>';
    readme += '    <tr style="background-color:#f6f8fa; border-bottom:2px solid #ddd; text-align:left;">';
    readme += '      <th style="padding:10px; border:1px solid #ddd; font-weight:bold; color:#444;">物理内存 (RAM)</th>';
    readme += '      <th style="padding:10px; border:1px solid #ddd; font-weight:bold; color:#444;">推荐 Swap 设定规则</th>';
    readme += '      <th style="padding:10px; border:1px solid #ddd; font-weight:bold; color:#444;">最佳建议值 (MB)</th>';
    readme += '    </tr>';
    readme += '  </thead>';
    readme += '  <tbody>';
    readme += '    <tr><td style="padding:10px; border:1px solid #ddd;"><b>小于 2GB</b></td><td style="padding:10px; border:1px solid #ddd;">物理内存的 <b>2倍</b></td><td style="padding:10px; border:1px solid #ddd; color:#28a745; font-weight:bold;">1024 MB - 2048 MB</td></tr>';
    readme += '    <tr><td style="padding:10px; border:1px solid #ddd;"><b>2GB - 8GB</b></td><td style="padding:10px; border:1px solid #ddd;">与物理内存<b>等大</b>或 <b>1.5倍</b></td><td style="padding:10px; border:1px solid #ddd; color:#28a745; font-weight:bold;">2048 MB - 4096 MB</td></tr>';
    readme += '    <tr><td style="padding:10px; border:1px solid #ddd;"><b>8GB - 16GB</b></td><td style="padding:10px; border:1px solid #ddd;">配置约 <b>4GB</b> 即可</td><td style="padding:10px; border:1px solid #ddd; color:#28a745; font-weight:bold;">4096 MB</td></tr>';
    readme += '    <tr><td style="padding:10px; border:1px solid #ddd;"><b>大于 16GB</b></td><td style="padding:10px; border:1px solid #ddd;">配置 <b>4GB - 8GB</b> 即可</td><td style="padding:10px; border:1px solid #ddd; color:#28a745; font-weight:bold;">4096 MB - 8192 MB</td></tr>';
    readme += '  </tbody>';
    readme += '</table>';
    readme += '<h5 style="margin-top:20px; color:#333; font-weight:bold;">2. 使用注意事项与性能提醒：</h5>';
    readme += '<ul style="padding-left:20px; margin-top:5px; list-style-type:disc;">';
    readme += '  <li style="margin-bottom:8px;"><b>磁盘性能关联</b>：Swap 位于磁盘上，读写性能远低于真实的物理内存。因此，建议将 Swap 空间建立在 <b>SSD 固态硬盘</b> 上。如果在传统的 HDD 机械硬盘上频繁使用 Swap，可能会使磁盘 I/O 瞬间飙高，从而导致系统整体响应变慢。</li>';
    readme += '  <li style="margin-bottom:8px;"><b>后台创建耗时</b>：当您在“配置调整”中手工修改提交时，后台需要通过磁盘写入 (<code>dd</code> 命令) 重新生成指定大小的文件。配置的 Swap 容量越大 (如 4GB 以上)，因需要高负载写入，创建时间可能会持续<b>几秒到几十秒</b>，这属于正常现象，请在提交后耐心等待提示成功。</li>';
    readme += '  <li style="margin-bottom:8px;"><b>系统级 Swap 叠加</b>：本插件创建的 Swapfile 属于插件专属虚拟内存，挂载启用后，会自动与您系统本身已有的 Swap 分区或文件<b>叠加合并生效</b>，两者不产生任何冲突。</li>';
    readme += '</ul>';
    readme += '</div>';
    $('.soft-man-con').html(readme);
}
