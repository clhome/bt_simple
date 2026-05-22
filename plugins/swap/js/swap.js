

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
        var size = rdata.data['size'];           // 插件专属 Swap (MB)
        var system_total = rdata.data['system_total']; // 系统实际总 Swap (MB)
        var mem_total = rdata.data['mem_total'];       // 物理内存总量 (MB)

        // 1. 计算物理内存的 GB 数，保留一位小数
        var mem_gb = (mem_total / 1024).toFixed(1);
        
        // 2. 动态计算最佳推荐配置 Swap 值
        var recommend_size = 2048; // 默认推荐 2GB
        if (mem_total < 2048) {
            recommend_size = mem_total * 2;
        } else if (mem_total >= 2048 && mem_total <= 8192) {
            recommend_size = mem_total;
        } else {
            recommend_size = 4096;
        }

        // 3. 构建排版精美的 HTML 页面
        var spCon = '<div class="conf_p" style="padding: 15px; background-color: #fafbfc; border-radius: 6px; border: 1px solid #e1e4e8; margin-top: 15px;">';
        
        // --- 模块一：当前状态模块 ---
        spCon += '  <div style="margin-bottom: 20px;">';
        spCon += '    <h4 style="margin: 0 0 12px 0; font-size: 14px; font-weight: bold; color: #333; border-left: 3px solid #20a53a; padding-left: 8px;">📊 系统当前 Swap 状态</h4>';
        spCon += '    <div style="display: flex; gap: 15px; margin-top: 8px;">';
        
        // 状态卡片 1：系统总 Swap
        spCon += '      <div style="flex: 1; padding: 12px; background: #fff; border: 1px solid #e1e4e8; border-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">';
        spCon += '        <div style="font-size: 12px; color: #666; margin-bottom: 4px;">系统实际总 Swap (已启用)</div>';
        spCon += '        <div style="font-size: 18px; font-weight: bold; color: #1f2d3d;">' + system_total + ' <span style="font-size: 12px; font-weight: normal; color: #888;">MB</span></div>';
        spCon += '      </div>';
        
        // 状态卡片 2：插件专属 Swap
        spCon += '      <div style="flex: 1; padding: 12px; background: #fff; border: 1px solid #e1e4e8; border-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">';
        spCon += '        <div style="font-size: 12px; color: #666; margin-bottom: 4px;">插件专属 Swapfile 文件</div>';
        spCon += '        <div style="font-size: 18px; font-weight: bold; color: #1f2d3d;">' + size + ' <span style="font-size: 12px; font-weight: normal; color: #888;">MB</span></div>';
        spCon += '      </div>';
        
        spCon += '    </div>';
        spCon += '  </div>';

        // --- 模块二：调整配置模块 ---
        spCon += '  <div style="border-top: 1px solid #e9ebec; padding-top: 15px; margin-bottom: 10px;">';
        spCon += '    <h4 style="margin: 0 0 15px 0; font-size: 14px; font-weight: bold; color: #333; border-left: 3px solid #007bff; padding-left: 8px;">⚙️ 调整插件虚拟内存配置</h4>';
        
        // 快捷预设与自定义大小表单
        spCon += '    <div style="display: flex; align-items: center; gap: 15px; flex-wrap: wrap; margin-bottom: 12px;">';
        
        spCon += '      <div>';
        spCon += '        <span style="font-size: 13px; color: #555;">快捷预设容量:</span>';
        spCon += '        <select class="bt-input-text" name="swap_set" style="margin-left: 5px; width: 100px; height: 30px; padding: 0 5px; border-radius: 4px;">';
        spCon += '            <option value="">请选择...</option>';
        spCon += '            <option value="218MB">218MB</option>';
        spCon += '            <option value="512MB">512MB</option>';
        spCon += '            <option value="1GB">1GB</option>';
        spCon += '            <option value="2GB">2GB</option>';
        spCon += '            <option value="4GB">4GB</option>';
        spCon += '        </select>';
        spCon += '      </div>';

        spCon += '      <div style="display: flex; align-items: center;">';
        spCon += '        <span style="font-size: 13px; color: #555;">自定义修改为:</span>';
        spCon += '        <input style="width: 80px; height: 30px; margin-left: 5px; text-align: center; border-radius: 4px; border: 1px solid #ccc;" class="bt-input-text mr5" name="size" value="' + size + '" type="number" >';
        spCon += '        <span style="font-size: 13px; color: #555; margin-left: 2px;">MB</span>';
        spCon += '      </div>';
        
        spCon += '    </div>';

        // --- 模块三：智能配置推荐 ---
        spCon += '    <div style="background-color: #eef9f0; border-radius: 4px; padding: 10px; border-left: 4px solid #28a745; margin-bottom: 15px; display: flex; align-items: center;">';
        spCon += '      <div style="font-size: 13px; color: #1e7e34; width:100%;">';
        spCon += '        💡 <b>智能配置推荐</b>：基于您当前的物理内存 <b>' + mem_gb + ' GB</b>，最佳推荐配置的 Swap 大小为 <b style="font-size:14px; text-decoration: underline; cursor: pointer; color: #155724;" onclick="applyRecommendSize(' + recommend_size + ')">' + recommend_size + ' MB</b> <span style="font-size: 11px; font-weight: normal; color: #555;">(点击可快速填入)</span>';
        spCon += '      </div>';
        spCon += '    </div>';

        // 提交按钮
        spCon += '    <div class="text-right" style="padding-right: 5px;">';
        spCon += '      <button class="btn btn-success btn-sm" style="padding: 6px 16px; font-size: 13px; font-weight: bold; border-radius: 4px;" onclick="submitSwap()">提交修改</button>';
        spCon += '    </div>';
        
        spCon += '  </div>';
        spCon += '</div>';

        $(".soft-man-con").html(spCon);

        // 绑定下拉框 change 联动
        $(".conf_p select[name='swap_set']").change(function() {
            var swap_size = $(this).val();
            if (!swap_size) return;
            if (swap_size.indexOf('GB') > -1) {
                swap_size = parseInt(swap_size) * 1024;
            } else {
                swap_size = parseInt(swap_size);
            }
            $("input[name='size']").val(swap_size);
        });
    });
}

function applyRecommendSize(size) {
    $("input[name='size']").val(size);
    $(".conf_p select[name='swap_set']").val("");
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
