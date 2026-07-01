

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
        var rdata = JSON.parse(data.data);
        var size = parseInt(rdata.data['size']) || 0;           // 插件专属 Swap (MB)
        var system_total = parseInt(rdata.data['system_total']) || 0; // 系统实际总 Swap (MB)
        var mem_total = parseInt(rdata.data['mem_total']) || 0;       // 物理内存总量 (MB)

        // 1. 计算物理内存的 GB 数，保留一位小数
        var mem_gb = (mem_total / 1024).toFixed(1);
        
        // 2. 依据官方建议表格计算目标总 Swap (MB)
        var target_total = 4096; // 默认推荐 4GB
        if (mem_total < 2048) {
            // 小于 2GB：物理内存的 2倍，范围 1024 - 2048 MB
            target_total = Math.min(Math.max(mem_total * 2, 1024), 2048);
        } else if (mem_total >= 2048 && mem_total < 8192) {
            // 2GB - 8GB：与物理内存等大，范围 2048 - 4096 MB
            target_total = Math.min(Math.max(mem_total, 2048), 4096);
        } else if (mem_total >= 8192 && mem_total <= 16384) {
            // 8GB - 16GB：配置约 4GB 即可
            target_total = 4096;
        } else {
            // 大于 16GB：配置 4GB - 8GB，推荐 8192 MB
            target_total = 8192;
        }

        // 3. 计算系统自身原本已挂载的第三方 Swap 分区大小（系统自带 = 系统当前实际总 Swap - 本插件专属的 Swap）
        var system_own = Math.max(0, system_total - size);

        // 4. 插件最佳推荐配置 = 目标总量 - 系统自带 Swap（若结果小于 0，则推荐值归 0）
        var recommend_size = Math.max(0, target_total - system_own);

        // 5. 预设档位（含展示名和 MB 对应关系值）
        var presets = [
            { name: "218MB", value: 218 },
            { name: "512MB", value: 512 },
            { name: "1GB", value: 1024 },
            { name: "2GB", value: 2048 },
            { name: "4GB", value: 4096 },
            { name: "8GB", value: 8192 }
        ];

        // 6. 从预设档位中，选择差值绝对值最小（最接近）的推荐档位
        var closest_preset = presets[0];
        var min_diff = Math.abs(recommend_size - closest_preset.value);
        for (var i = 1; i < presets.length; i++) {
            var diff = Math.abs(recommend_size - presets[i].value);
            if (diff < min_diff) {
                min_diff = diff;
                closest_preset = presets[i];
            }
        }

        // 7. 构建排版精美的 HTML 页面
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
        
        // 预设选择与提交修改横向两端对齐排版
        spCon += '    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%; margin-bottom: 15px; flex-wrap: wrap; gap: 10px;">';
        
        spCon += '      <div style="display: flex; align-items: center;">';
        spCon += '        <span style="font-size: 13px; color: #555; font-weight: 500;">配置容量选择:</span>';
        
        // 动态生成下拉列表，完美匹配当前插件 Swap 容量大小并高亮选中
        var has_exact_preset = false;
        var selectHtml = '<select class="bt-input-text" name="swap_set" style="margin-left: 10px; width: 180px; height: 32px; padding: 0 8px; border-radius: 4px; border: 1px solid #ccc; font-size: 13px;">';
        selectHtml += '  <option value="">请选择...</option>';
        for (var i = 0; i < presets.length; i++) {
            var is_selected = (presets[i].value === size) ? 'selected' : '';
            if (presets[i].value === size) {
                has_exact_preset = true;
            }
            selectHtml += '  <option value="' + presets[i].value + '" ' + is_selected + '>' + presets[i].name + '</option>';
        }
        if (!has_exact_preset && size > 0) {
            selectHtml += '  <option value="' + size + '" selected>当前大小 (' + size + 'MB)</option>';
        }
        selectHtml += '</select>';
        
        spCon += selectHtml;
        spCon += '      </div>';

        // 提交修改按钮
        spCon += '      <div>';
        spCon += '        <button class="btn btn-success btn-sm" style="padding: 6px 20px; font-size: 13px; font-weight: bold; border-radius: 4px;" onclick="submitSwap()">提交修改</button>';
        spCon += '      </div>';
        
        spCon += '    </div>';

        // --- 模块三：智能配置推荐 ---
        spCon += '    <div style="background-color: #eef9f0; border-radius: 4px; padding: 10px; border-left: 4px solid #28a745; margin-bottom: 5px; display: flex; align-items: center;">';
        spCon += '      <div style="font-size: 13px; color: #1e7e34; width:100%;">';
        spCon += '        💡 <b>智能配置推荐</b>：基于您当前的物理内存 <b>' + mem_gb + ' GB</b>，官方推荐总虚拟内存为 <b>' + target_total + ' MB</b>（已扣除系统自带 ' + system_own + ' MB）。因此本插件最接近的最佳推荐档位为 <b style="font-size:14px; text-decoration: underline; cursor: pointer; color: #155724;" onclick="applyRecommendPreset(' + closest_preset.value + ')">' + closest_preset.name + '</b> <span style="font-size: 11px; font-weight: normal; color: #555;">(点击可快速选择)</span>';
        spCon += '      </div>';
        spCon += '    </div>';
        
        spCon += '  </div>';
        spCon += '</div>';

        // 外部右下角公司提示，带有前往官网链接与悬停动效
        spCon += '<div style="text-align: right; margin-top: 15px; font-size: 12px; padding-right: 5px;">';
        spCon += '  <a href="https://www.yftec.top" target="_blank" style="color: #1e7e34; text-decoration: none; font-weight: 500; cursor: pointer;" onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">衢州御风科技有限公司出品</a>';
        spCon += '</div>';

        $(".soft-man-con").html(spCon);
    });
}

function applyRecommendPreset(value) {
    $(".conf_p select[name='swap_set']").val(value);
}

function submitSwap(){
    var size = $(".conf_p select[name='swap_set']").val();
    if (!size) {
        layer.msg("请先选择您想要配置的 Swap 容量！", { icon: 0 });
        return;
    }

    // 启用全屏不可关闭的强阻断 Layer 遮罩，极佳地引导大容量虚拟内存创建过程
    var loadT = layer.msg('系统正在安全创建并格式化 ' + size + 'MB 虚拟内存文件...<br><span style="font-size:11px; color:#ff8c00;">大容量配置（如4G/8G）由于磁盘高负载写入需要 5-30 秒，请勿刷新或关闭页面！</span>', {
        icon: 16,
        time: 0,
        shade: [0.5, '#000']
    });

    var req_data = {};
    req_data['name'] = 'swap';
    req_data['func'] = 'change_swap';
    req_data['version'] = '';
    req_data['args'] = JSON.stringify({"size": size});

    $.post('/plugins/run', req_data, function(data) {
        layer.close(loadT);
        if (!data.status){
            layer.msg(data.msg, {icon: 5, time: 3000});
            return;
        }

        var rdata = JSON.parse(data.data);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 5, time: 3000 });
        swapStatus();
    }, 'json');
}

function readme(){
    var readme = '<div class="help-info-text c7" style="line-height:24px; font-size:13px; padding:15px; color:var(--text-color, #555);">';
    readme += '<h4 style="margin-top:0; color:var(--title-color, #222); font-weight:bold; border-bottom:1px solid var(--border-color, #eee); padding-bottom:8px;">Swap (虚拟内存) 配置与使用指南</h4>';
    readme += '<p style="margin-top:10px; text-indent:2em;"><b>什么是 Swap？</b>Swap 也就是虚拟内存，当物理内存 (RAM) 不足时，Linux 系统会自动将部分闲置内存数据临时交换到磁盘上的专属 Swap 空间中，以保证系统稳定运行。配置 Swap能极大防止因内存溢出 (OOM) 导致关键服务 (如 MySQL、Nginx 等) 被系统强制杀死的现象。</p>';
    readme += '<h5 style="margin-top:20px; color:var(--title-color, #333); font-weight:bold;">1. 不同情况下的 Swap 大小配置建议：</h5>';
    readme += '<table class="table" style="width:100%; border-collapse:collapse; margin:10px 0; border:1px solid var(--border-color, #e1e4e8); background-color:var(--card-bg, #fff); border-radius:4px; overflow:hidden;">';
    readme += '  <thead>';
    readme += '    <tr style="background-color:var(--bg-color, #f6f8fa); border-bottom:2px solid var(--border-color, #ddd); text-align:left;">';
    readme += '      <th style="padding:10px; border:1px solid var(--border-color, #ddd); font-weight:bold; color:var(--title-color, #444);">物理内存 (RAM)</th>';
    readme += '      <th style="padding:10px; border:1px solid var(--border-color, #ddd); font-weight:bold; color:var(--title-color, #444);">推荐 Swap 设定规则</th>';
    readme += '      <th style="padding:10px; border:1px solid var(--border-color, #ddd); font-weight:bold; color:var(--title-color, #444);">最佳建议值 (MB)</th>';
    readme += '    </tr>';
    readme += '  </thead>';
    readme += '  <tbody>';
    readme += '    <tr><td style="padding:10px; border:1px solid var(--border-color, #ddd);"><b>小于 2GB</b></td><td style="padding:10px; border:1px solid var(--border-color, #ddd);">物理内存的 <b>2倍</b></td><td style="padding:10px; border:1px solid var(--border-color, #ddd); color:#28a745; font-weight:bold;">1024 MB - 2048 MB</td></tr>';
    readme += '    <tr><td style="padding:10px; border:1px solid var(--border-color, #ddd);"><b>2GB - 8GB</b></td><td style="padding:10px; border:1px solid var(--border-color, #ddd);">与物理内存<b>等大</b>或 <b>1.5倍</b></td><td style="padding:10px; border:1px solid var(--border-color, #ddd); color:#28a745; font-weight:bold;">2048 MB - 4096 MB</td></tr>';
    readme += '    <tr><td style="padding:10px; border:1px solid var(--border-color, #ddd);"><b>8GB - 16GB</b></td><td style="padding:10px; border:1px solid var(--border-color, #ddd);">配置约 <b>4GB</b> 即可</td><td style="padding:10px; border:1px solid var(--border-color, #ddd); color:#28a745; font-weight:bold;">4096 MB</td></tr>';
    readme += '    <tr><td style="padding:10px; border:1px solid var(--border-color, #ddd);"><b>大于 16GB</b></td><td style="padding:10px; border:1px solid var(--border-color, #ddd);">配置 <b>4GB - 8GB</b> 即可</td><td style="padding:10px; border:1px solid var(--border-color, #ddd); color:#28a745; font-weight:bold;">4096 MB - 8192 MB</td></tr>';
    readme += '  </tbody>';
    readme += '</table>';
    readme += '<h5 style="margin-top:20px; color:var(--title-color, #333); font-weight:bold;">2. 使用注意事项与性能提醒：</h5>';
    readme += '<ul style="padding-left:20px; margin-top:5px; list-style-type:disc;">';
    readme += '  <li style="margin-bottom:8px;"><b>磁盘性能关联</b>：Swap 位于磁盘上，读写性能远低于真实的物理内存。因此，建议将 Swap 空间建立在 <b>SSD 固态硬盘</b> 上。如果在传统的 HDD 机械硬盘上频繁使用 Swap，可能会使磁盘 I/O 瞬间飙高，从而导致系统整体响应变慢。</li>';
    readme += '  <li style="margin-bottom:8px;"><b>后台创建耗时</b>：当您在“配置调整”中手工修改提交时，后台需要通过磁盘写入 (<code>dd</code> 命令) 重新生成指定大小的文件。配置的 Swap 容量越大 (如 4GB 以上)，因需要高负载写入，创建时间可能会持续<b>几秒到几十秒</b>，这属于正常现象，请在提交后耐心等待提示成功。</li>';
    readme += '  <li style="margin-bottom:8px;"><b>系统级 Swap 叠加</b>：本插件创建的 Swapfile 属于插件专属虚拟内存，挂载启用后，会自动与您系统本身已有的 Swap 分区或文件<b>叠加合并生效</b>，两者不产生任何冲突。</li>';
    readme += '</ul>';
    readme += '</div>';
    $('.soft-man-con').html(readme);
}
