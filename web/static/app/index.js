//获取负载
function getLoad(data) {
    $("#LoadList .mask").html("<span id='Load' style='font-size:14px'>获取中..</span>");
    setCookie('one', data.one);
    setCookie('five', data.five);
    setCookie('fifteen', data.fifteen);
    var transformLeft, transformRight, LoadColor, Average, Occupy, AverageText, conterError = '';
    var index = $("#LoadList");
    if (Average == undefined) Average = data.one;
    setCookie('conterError', conterError);
    Occupy = Math.round((Average / data.max) * 100);
    if (Occupy > 100) Occupy = 100;
    if (Occupy <= 30) {
        LoadColor = '#20a53a';
        AverageText = '运行流畅';
    } else if (Occupy <= 70) {
        LoadColor = '#6ea520';
        AverageText = '运行正常';
    } else if (Occupy <= 90) {
        LoadColor = '#ff9900';
        AverageText = '运行缓慢';
    } else {
        LoadColor = '#dd2f00';
        AverageText = '运行堵塞';
    }
    index.find('.circle').css("background", LoadColor);
    index.find('.mask').css({ "color": LoadColor });
    $("#LoadList .mask").html("<span id='Load'></span>%");
    $('#Load').html(Occupy);
    $('#LoadState').html('<span>' + AverageText + '</span>');
    setImg();
}

$('#LoadList .circle').click(function() {
    // getNet();
});

$('#LoadList .mask').hover(function() {
    var one, five, fifteen;
    var that = this;
    one = getCookie('one');
    five = getCookie('five');
    fifteen = getCookie('fifteen');
    var text = '最近1分钟平均负载：' + one + '</br>最近5分钟平均负载：' + five + '</br>最近15分钟平均负载：' + fifteen + '';
    layer.tips(text, that, { time: 0, tips: [1, '#999'] });
}, function() {
    layer.closeAll('tips');
});


function showCpuTips(rdata){
    $('#cpuChart .mask').unbind().hover(function() {
        var cpuText = '';
        if (rdata.cpu[2].length == 1){
            var cpuUse = parseFloat(rdata.cpu[2][0] == 0 ? 0 : rdata.cpu[2][0]).toFixed(1);
            cpuText += 'CPU-1：' + cpuUse + '%';
        } else {
            for (var i = 1; i < rdata.cpu[2].length + 1; i++) {
                var cpuUse = parseFloat(rdata.cpu[2][i - 1] == 0 ? 0 : rdata.cpu[2][i - 1]).toFixed(1);
                if (i % 2 != 0) {
                    cpuText += 'CPU-' + i + '：' + cpuUse + '%&nbsp;|&nbsp;';
                } else {
                    cpuText += 'CPU-' + i + '：' + cpuUse + '%';
                    cpuText += '\n';
                }
            } 
        }
        layer.tips(rdata.cpu[3] + "</br>" + rdata.cpu[5] + "个物理CPU，" + (rdata.cpu[4]) + "个物理核心，" + rdata.cpu[1] + "个逻辑核心</br>" + cpuText, this, { time: 0, tips: [1, '#999'] });
    }, function() {
        layer.closeAll('tips');
    });
}


function rocket(sum, m) {
    var n = sum - m;
    $(".mem-release").find(".mask span").text(n);
}

//释放内存
function reMemory() {
    setTimeout(function() {
        $(".mem-release").find('.mask').css({ 'color': '#20a53a', 'font-size': '14px' }).html('<span style="display:none">1</span>' + lan.index.memre_ok_0 + ' <img src="/static/img/ings.gif">');
        $.post('/system/rememory', '', function(rdata) {
            var percent = getPercent(rdata.memRealUsed, rdata.memTotal);
            var memText = Math.round(rdata.memRealUsed) + "/" + Math.round(rdata.memTotal) + " (MB)";
            percent = Math.round(percent);
            $(".mem-release").find('.mask').css({ 'color': '#20a53a', 'font-size': '14px' }).html("<span style='display:none'>" + percent + "</span>" + lan.index.memre_ok);
            setCookie("mem-before", memText);
            var memNull = Math.round(getCookie("memRealUsed") - rdata.memRealUsed);
            setTimeout(function() {
                if (memNull > 0) {
                    $(".mem-release").find('.mask').css({ 'color': '#20a53a', 'font-size': '14px', 'line-height': '22px', 'padding-top': '22px' }).html("<span style='display:none'>" + percent + "</span>" + lan.index.memre_ok_1 + "<br>" + memNull + "MB");
                } else {
                    $(".mem-release").find('.mask').css({ 'color': '#20a53a', 'font-size': '14px' }).html("<span style='display:none'>" + percent + "</span>" + lan.index.memre_ok_2);
                }
                $(".mem-release").removeClass("mem-action");
                $("#memory").text(memText);
                setCookie("memRealUsed", rdata.memRealUsed);
            }, 1000);
            setTimeout(function() {
                $(".mem-release").find('.mask').removeAttr("style").html("<span>" + percent + "</span>%");
                $(".mem-release").find(".mem-re-min").show();
            }, 2000)
        },'json');
    }, 2000);
}

function getPercent(num, total) {
    num = parseFloat(num);
    total = parseFloat(total);
    if (isNaN(num) || isNaN(total)) {
        return "-";
    }
    return total <= 0 ? "0%" : (Math.round(num / total * 10000) / 100.00);
}

function getDiskInfo() {
    $.get('/system/disk_info', function(rdata) {
        var rdata = rdata.data;
        var dBody;
        for (var i = 0; i < rdata.length; i++) {
            var LoadColor = setcolor(parseInt(rdata[i].size[3].replace('%', '')), false, 75, 90, 95);

            //判断inode信息是否存在
            var inodes = '';
            if ( typeof(rdata[i]['inodes']) !=='undefined' ){
                inodes = '<div class="mask" style="color:' + LoadColor + '" data="Inode信息<br>总数：' + rdata[i].inodes[0] + '<br>已使用：' + rdata[i].inodes[1] + '<br>可用：' + rdata[i].inodes[2] + '<br>Inode使用率：' + rdata[i].inodes[3] + '"><span>' + rdata[i].size[3].replace('%', '') + '</span>%</div>';

                var ipre = parseInt(rdata[i].inodes[3].replace('%', ''));
                if (ipre > 95) {
                    $("#messageError").show();
                    $("#messageError").append('<p><span class="glyphicon glyphicon-alert" style="color: #ff4040; margin-right: 10px;"></span>分区[' + rdata[i].path + ']当前Inode使用率超过' + ipre + '%，当使用率满100%时将无法在此分区创建文件，请及时清理!<a class="btlink" href="javascript:ClearSystem();">[清理垃圾]</a></p>');
                }
            }

            if (rdata[i].path == '/' || rdata[i].path == '/www') {
                if (rdata[i].size[2].indexOf('M') != -1) {
                    $("#messageError").show();
                    $("#messageError").append('<p><span class="glyphicon glyphicon-alert" style="color: #ff4040; margin-right: 10px;"></span> ' + lan.get('diskinfo_span_1', [rdata[i].path]) + '<a class="btlink" href="javascript:ClearSystem();">[清理垃圾]</a></p>');
                } 
            }
           
            dBody = '<li class="col-xs-6 col-sm-3 col-md-3 col-lg-2 mtb20 circle-box text-center diskbox">' +
                '<h3 class="c5 f15">' + rdata[i].path + '</h3>' +
                '<div class="circle" style="background:' + LoadColor + '">' +
                '<div class="pie_left">' +
                '<div class="left"></div>' +
                '</div>' +
                '<div class="pie_right">' +
                '<div class="right"></div>' +
                '</div>'+ inodes +'</div>' +
                '<h4 class="c5 f15">' + rdata[i].size[1] + '/' + rdata[i].size[0] + '</h4>' +
                '</li>'
            $("#systemInfoList").append(dBody);
            setImg();
        }
    },'json');
}

//清理垃圾
function clearSystem() {
    var loadT = layer.msg('正在清理系统垃圾 <img src="/static/img/ing.gif">', { icon: 16, time: 0, shade: [0.3, "#000"] });
    $.get('/system?action=ClearSystem', function(rdata) {
        layer.close(loadT);
        layer.msg('清理完成,共清理[' + rdata[0] + ']个文件,释放[' + toSize(rdata[1]) + ']磁盘空间!', { icon: 1 });
    });
}

function setMemImg(info){

    var memRealUsed = toSize(info.memRealUsed);
    var memTotal = toSize(info.memTotal);

    var memRealUsedVal = memRealUsed.split(' ')[0];
    var memTotalVal = memTotal.split(' ')[0];
    var unit = memTotal.split(' ')[1];

    var mem_txt = memRealUsedVal + '/' + memTotalVal + ' ('+ unit +')';
    setCookie("mem-before", mem_txt);
    $("#memory").html(mem_txt);

    var memPre = Math.floor(info.memRealUsed / (info.memTotal / 100));
    $("#left").html(memPre);
    setcolor(memPre, "#left", 75, 90, 95);

    var memFree = info.memTotal - info.memRealUsed;
    if (memFree/(1024*1024) < 64) {
        $("#messageError").show();
        $("#messageError").append('<p><span class="glyphicon glyphicon-alert" style="color: #ff4040; margin-right: 10px;">当前可用物理内存小于64M，这可能导致MySQL自动停止，站点502等错误，请尝试释放内存！</span></p>')
    }
}

function getInfo() {
    $.get("/system/system_total", function(info) {

        setMemImg(info);

        $("#info").html(info.system);
        $("#running").html(info.time);
        var _system = info.system;
        if(_system.indexOf("Windows") != -1){
            $(".ico-system").addClass("ico-windows");
        } else if(_system.indexOf("CentOS") != -1) {
            $(".ico-system").addClass("ico-centos");
        } else if(_system.indexOf("Ubuntu") != -1) {
            $(".ico-system").addClass("ico-ubuntu");
        } else if(_system.indexOf("Debian") != -1) {
            $(".ico-system").addClass("ico-debian");
        } else if(_system.indexOf("Fedora") != -1) {
            $(".ico-system").addClass("ico-fedora");
        } else if(_system.indexOf("Mac") != -1){
            $(".ico-system").addClass("ico-mac");
        } else {
            $(".ico-system").addClass("ico-linux");
        }
        $("#core").html(info.cpuNum + ' 核心');
        $("#state").html(info.cpuRealUsed);
        setcolor(info.cpuRealUsed, "#state", 30, 70, 90);
       

        // if (info.isuser > 0) {
        //     $("#messageError").show();
        //     $("#messageError").append('<p><span class="glyphicon glyphicon-alert" style="color: #ff4040; margin-right: 10px;"></span>' + lan.index.user_warning + '<span class="c7 mr5" title="此安全问题不可忽略，请尽快处理" style="cursor:no-drop"> [不可忽略]</span><a class="btlink" href="javascript:setUserName();"> [立即修改]</a></p>')
        // }
        setImg();
    },'json');
}


function setcolor(pre, s, s1, s2, s3) {
    var LoadColor;
    if (pre <= s1) {
        LoadColor = '#20a53a';
    } else if (pre <= s2) {
        LoadColor = '#6ea520';
    } else if (pre <= s3) {
        LoadColor = '#ff9900';
    } else {
        LoadColor = '#dd2f00';
    }
    if (s == false) {
        return LoadColor;
    }
    var co = $(s).parent('.mask');
    co.css("color", LoadColor);
    co.parent('.circle').css("background", LoadColor);
}


function getNet() {
    var up, down;
    $.get("/system/network", function(net) {

        console.log(net);

        $("#InterfaceSpeed").html(lan.index.interfacespeed + "： 1.0Gbps");
        $("#upSpeed").html(toSize(net.up));
        $("#downSpeed").html(toSize(net.down));
        $("#downAll").html(toSize(net.downTotal));
        $("#downAll").attr('title', lan.index.package + ':' + net.downPackets)
        $("#upAll").html(toSize(net.upTotal));
        $("#upAll").attr('title', lan.index.package + ':' + net.upPackets)
        $("#core").html(net.cpu[1] + " " + lan.index.cpu_core);
        $("#state").html(net.cpu[0]);
        setcolor(net.cpu[0], "#state", 30, 70, 90);
        setCookie("upNet", net.up);
        setCookie("downNet", net.down);

        //负载
        getLoad(net.load);

        //内存
        setMemImg(net.mem);

        //绑定hover事件
        setImg();
        showCpuTips(net);

    },'json');
}

//网络IO
function netImg() {
    
    var xData = [];
    var yData = [];
    var zData = [];

    function getTime() {
        var now = new Date();
        var hour = now.getHours();
        var minute = now.getMinutes();
        var second = now.getSeconds();
        if (minute < 10) {
            minute = "0" + minute;
        }
        if (second < 10) {
            second = "0" + second;
        }
        var nowdate = hour + ":" + minute + ":" + second;
        return nowdate;
    }

    function ts(m) { return m < 10 ? '0' + m : m }

    function format(sjc) {
        var time = new Date(sjc);
        var h = time.getHours();
        var mm = time.getMinutes();
        var s = time.getSeconds();
        return ts(h) + ':' + ts(mm) + ':' + ts(s);
    }

    var default_unit = 'KB/s';
    function addData(shift) {
        xData.push(getTime());

        if (getCookie("upNet") > getCookie("downNet") ){
            tmp = getCookie("upNet");
        } else {
            tmp = getCookie("downNet");
        }
        var tmpSize = toSize(tmp);
        default_unit = tmpSize.split(' ')[1] + '/s';


        var upNetTmp = toSize(getCookie("upNet"));
        var downNetTmp = toSize(getCookie("downNet"));
        
        var upNetTmpSize = upNetTmp.split(' ')[0];
        var downNetTmp = downNetTmp.split(' ')[0];
        
        yData.push(upNetTmpSize);
        zData.push(downNetTmp);
        if (shift) {
            xData.shift();
            yData.shift();
            zData.shift();
        }
    }
    for (var i = 8; i >= 0; i--) {
        var time = (new Date()).getTime();
        xData.push(format(time - (i * 3 * 1000)));
        yData.push(0);
        zData.push(0);
    }
    // 指定图表的配置项和数据
    var option = {
        title: {
            text: "接口流量实时",
            left: 'center',
            textStyle: {
                color: '#888888',
                fontStyle: 'normal',
                fontFamily: "宋体",
                fontSize: 16,
            }
        },
        tooltip: {
            trigger: 'axis'
        },
        legend: {
            data: [lan.index.net_up, lan.index.net_down],
            bottom: '2%'
        },
        xAxis: {
            type: 'category',
            boundaryGap: false,
            data: xData,
            axisLine: {
                lineStyle: {
                    color: "#666"
                }
            }
        },
        yAxis: {
            name:  '单位 '+ default_unit,
            splitLine: {
                lineStyle: { color: "#eee" }
            },
            axisLine: {
                lineStyle: { color: "#666" }
            }
        },
        series: [{
            name: '上行',
            type: 'line',
            data: yData,
            smooth: true,
            showSymbol: false,
            symbol: 'circle',
            symbolSize: 6,
            areaStyle: {
                normal: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{
                        offset: 0,
                        color: 'rgba(255, 140, 0,0.5)'
                    }, {
                        offset: 1,
                        color: 'rgba(255, 140, 0,0.8)'
                    }], false)
                }
            },
            itemStyle: {
                normal: {
                    color: '#f7b851'
                }
            },
            lineStyle: {
                normal: {
                    width: 1
                }
            }
        },
        {
            name: '下行',
            type: 'line',
            data: zData,
            smooth: true,
            showSymbol: false,
            symbol: 'circle',
            symbolSize: 6,
            areaStyle: {
                normal: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{
                        offset: 0,
                        color: 'rgba(30, 144, 255,0.5)',
                    }, {
                        offset: 1,
                        color: 'rgba(30, 144, 255,0.8)',
                    }], false)
                }
            },
            itemStyle: {
                normal: {
                    color: '#52a9ff',
                }
            },
            lineStyle: {
                normal: {
                    width: 1,
                }
            }
        }]
    };

    var echartsNetImg = echarts.init(document.getElementById('netImg'));
    setInterval(function() {
        getNet();
        addData(true);
        echartsNetImg.setOption({
            yAxis: {
                name:  '单位 '+ default_unit,
                splitLine: { lineStyle: { color: "#eee" } },
                axisLine: { lineStyle: { color: "#666" } }
            },
            xAxis: {
                data: xData
            },
            series: [{
                name: lan.index.net_up,
                data: yData
            }, {
                name: lan.index.net_down,
                data: zData
            }]
        });
    }, 3000);

    // 使用刚指定的配置项和数据显示图表。
    echartsNetImg.setOption(option);
    window.addEventListener("resize", function() {
        echartsNetImg.resize();
    });
}


function setImg() {
    $('.circle').each(function(index, el) {
        var num = $(this).find('span').text() * 3.6;
        if (num <= 180) {
            $(this).find('.left').css('transform', "rotate(0deg)");
            $(this).find('.right').css('transform', "rotate(" + num + "deg)");
        } else {
            $(this).find('.right').css('transform', "rotate(180deg)");
            $(this).find('.left').css('transform', "rotate(" + (num - 180) + "deg)");
        };
    });

    $('.diskbox .mask').unbind().hover(function() {
        layer.closeAll('tips');
        var that = this;
        var conterError = $(this).attr("data");
        layer.tips(conterError, that, { time: 0, tips: [1, '#999'] });
    }, function() {
        layer.closeAll('tips');
    });
}

// 检查更新
setTimeout(function() {
    $.get('/system/update_server?type=check', function(rdata) {
        if (rdata.status == false) return;
        if (rdata.data != undefined) {
            $("#toUpdate").html('<a class="btlink" href="javascript:updateMsg();">更新</a>');
            $('#toUpdate a').html('更新<i style="display: inline-block; color: red; font-size: 40px;position: absolute;top: -35px; font-style: normal; right: -8px;">.</i>');
            $('#toUpdate a').css("position","relative");
            return;
        }
    },'json').error(function() {
    });
}, 3000);


//检查更新
function checkUpdate() {
    var loadT = layer.msg(lan.index.update_get, { icon: 16, time: 0, shade: [0.3, '#000'] });
    $.get('/system/update_server?type=check', function(rdata) {
        layer.close(loadT);

        if (rdata.data == 'download'){
            updateStatus();return;
        }

        if (rdata.status === false) {
            layer.confirm(rdata.msg, { title: lan.index.update_check, icon: 1, closeBtn: 1, btn: [lan.public.know, lan.public.close] });
            return;
        }
        layer.msg(rdata.msg, { icon: 1 });
        if (rdata.data != undefined) updateMsg();
    },'json');
}

function updateMsg(){
    $.get('/system/update_server?type=info',function(rdata){
        if (rdata.data == 'download'){
            updateStatus();return;
        }
        var v = rdata.data.version;
        var v_info = (v.split('.').length > 3) ? 
            "<span class='label label-warning'>测试版本</span>" : 
            "<span class='label label-success arrowed'>正式版本</span>";

        var htmlContent = '';
        try {
            htmlContent = marked.parse(rdata.data.content);
        } catch(e) {
            htmlContent = rdata.data.content.replace(/\n/g, '<br/>');
        }
        showUpdateUI(v, v_info + '<span class="badge badge-inverse">版本更新 ['+v+']</span>', htmlContent);
    },'json');
}

function showUpdateUI(version, title, content) {
    layer.open({
        type: 1,
        title: title,
        area: '600px',
        shadeClose: false,
        closeBtn: 2,
        content: '<div class="setchmod bt-form pd20 pb70">'
                + (content ? '<div class="markdown-body" style="padding: 0 0 10px; line-height: 24px; max-height: 200px; overflow-y: auto; margin-bottom: 20px; border-bottom: 1px solid #eee;">' + content + '</div>' : '')
                + '<div class="update-progress-group" style="padding: 10px 0;">'
                + '    <div style="margin-bottom: 15px;">'
                + '        <div style="display:flex; justify-content: space-between; margin-bottom: 5px;"><span class="f12 c6">1. 下载并解压更新包（请耐心等待，预计时间5分钟，具体根据您的网络情况而定）</span><span id="download-percent" class="f12 c6">0%</span></div>'
                + '        <div style="height: 12px; background: #eee; border-radius: 6px; overflow: hidden;"><div id="download-bar" class="bt-progress-bar" style="width: 0%; height: 100%; position: relative;"></div></div>'
                + '    </div>'
                + '    <div style="margin-bottom: 15px;">'
                + '        <div style="display:flex; justify-content: space-between; margin-bottom: 5px;"><span class="f12 c6">2. 备份系统核心文件</span><span id="backup-percent" class="f12 c6">0%</span></div>'
                + '        <div style="height: 12px; background: #eee; border-radius: 6px; overflow: hidden;"><div id="backup-bar" class="bt-progress-bar" style="width: 0%; height: 100%; position: relative;"></div></div>'
                + '    </div>'
                + '    <div style="margin-bottom: 15px;">'
                + '        <div style="display:flex; justify-content: space-between; margin-bottom: 5px;"><span class="f12 c6">3. 安装更新并重启服务</span><span id="install-percent" class="f12 c6">0%</span></div>'
                + '        <div style="height: 12px; background: #eee; border-radius: 6px; overflow: hidden;"><div id="install-bar" class="bt-progress-bar" style="width: 0%; height: 100%; position: relative;"></div></div>'
                + '    </div>'
                + '</div>'
                + '<div class="bt-form-submit-btn">'
                + '<button type="button" class="btn btn-danger btn-sm btn-title" onclick="layer.closeAll()">取消</button>'
                + '<button type="button" id="start-update-btn" class="btn btn-success btn-sm btn-title" onclick="executeSteps(\''+version+'\')" >开始执行</button>'
                + '<button type="button" id="hard-refresh-btn" class="btn btn-default btn-sm btn-title" style="display:none;" onclick="location.href=location.pathname+\'?t=\'+new Date().getTime()" >强制刷新</button>'
                + '</div>'
                + '</div>'
    });
}

function executeSteps(version) {
    $("#start-update-btn").attr("disabled", true).addClass("disabled").text("正在处理...");
    $(".layui-layer-close").hide(); // 过程中禁止手动关闭
    
    updateStep('download', version, '#download-bar', '#download-percent', function() {
        updateStep('backup', version, '#backup-bar', '#backup-percent', function() {
            updateStep('install', version, '#install-bar', '#install-percent', function() {
                $("#start-update-btn").hide();
                $("#hard-refresh-btn").show().removeClass("btn-default").addClass("btn-success");
                $(".layui-layer-close").show();
                layer.msg("操作成功完成！请点击强制刷新。", {icon: 1, time: 5000});
            });
        });
    });
}

function updateStep(step, version, barId, textId, callback) {
    $(textId).text("处理中...");
    $(barId).css("width", "40%");
    
    $.get('/system/update_server?type=update&version=' + version + '&step=' + step, function(rdata) {
        if (rdata.status) {
            $(barId).css("width", "100%");
            $(textId).text("已完成");
            if (callback) callback();
        } else {
            $(textId).text("失败").css("color", "red");
            $(barId).css("background-color", "red");
            layer.msg(rdata.msg, {icon: 2});
            $("#start-update-btn").attr("disabled", false).removeClass("disabled").text("重试");
            $(".layui-layer-close").show();
        }
    }, 'json').error(function() {
        if (step == 'install') {
            $(barId).css("width", "100%");
            $(textId).text("已完成");
            if (callback) callback();
        } else {
            $(textId).text("连接失败").css("color", "red");
            layer.msg("与服务器连接断开，请检查网络。", {icon: 2});
            $(".layui-layer-close").show();
        }
    });
}



function pluginIndexService(pname,pfunc, callback){
    $.post('/plugins/run', {name:'openresty', func:pfunc}, function(data) {
        if (!data.status){
            layer.msg(data.msg,{icon:0,time:2000,shade: [0.3, '#000']});
            return;
        }

        if(typeof(callback) == 'function'){
            callback(data);
        }
    },'json'); 
}

//重启服务器
function reBoot() {
    layer.open({
        type: 1,
        title: '重启/修复 服务器',
        area: ['350px', '250px'],
        closeBtn: 1,
        shadeClose: false,
        content: '<div class="rebt-con">\
                <div class="rebt-li"><a data-id="server" href="javascript:;">重启服务器</a></div>\
                <div class="rebt-li"><a data-id="panel" href="javascript:;">重启面板</a></div>\
                <div class="rebt-li"><a data-id="repair" href="javascript:;">修复服务器</a></div>\
                <div style="color:red;text-align:center;margin-top:10px;font-weight:bold;clear:both;">注意：修复服务器会覆盖安装bt_simple面板</div>\
            </div>'
    });

    $('.rebt-con a').click(function () {
        var type = $(this).attr('data-id');
        switch (type) {
            case 'panel':
                layer.confirm('即将重启面板服务，继续吗？', { title: '重启面板服务', closeBtn: 1, icon: 3 }, function () {
                    var loadT = layer.load();
                    $.post('/system/restart','',function (rdata) {
                        layer.close(loadT);
                        layer.msg(rdata.msg);
                        setTimeout(function () { 
                            window.location.href = window.location.pathname + '?t=' + new Date().getTime(); 
                        }, 3000);
                    },'json');
                });
                break;
            case 'repair':
                layer.confirm('确定要修复服务器吗？这将会重新覆盖安装当前版本的面板文件。', { title: '修复服务器', closeBtn: 1, icon: 3 }, function () {
                    var version = $("#version").text();
                    showUpdateUI(version, '<span class="badge badge-inverse">系统修复 ['+version+']</span>', '正在准备修复系统核心文件...');
                });
                break;
            case 'server':
                var rebootbox = layer.open({
                    type: 1,
                    title: '安全重启服务器',
                    area: ['500px', '280px'],
                    closeBtn: 1,
                    shadeClose: false,
                    content: "<div class='bt-form bt-window-restart'>\
                            <div class='pd15'>\
                            <p style='color:red; margin-bottom:10px; font-size:15px;'>注意，若您的服务器是一个容器，请取消。</p>\
                            <div class='SafeRestart' style='line-height:26px'>\
                                <p>安全重启有利于保障文件安全，将执行以下操作：</p>\
                                <p>1.停止Web服务</p>\
                                <p>2.停止MySQL服务</p>\
                                <p>3.开始重启服务器</p>\
                                <p>4.等待服务器启动</p>\
                            </div>\
                            </div>\
                            <div class='bt-form-submit-btn'>\
                                <button type='button' class='btn btn-danger btn-sm btn-reboot'>取消</button>\
                                <button type='button' class='btn btn-success btn-sm WSafeRestart' >确定</button>\
                            </div>\
                        </div>"
                });
                setTimeout(function () {
                    $(".btn-reboot").click(function () {
                        rebootbox.close();
                    })
                    $(".WSafeRestart").click(function () {
                        var body = '<div class="SafeRestartCode pd15" style="line-height:26px"></div>';
                        $(".bt-window-restart").html(body);
                        $(".SafeRestartCode").append("<p>正在停止Web服务</p>");
                        pluginIndexService('openresty', 'stop', function (r1) {
                            $(".SafeRestartCode p").addClass('c9');
                            $(".SafeRestartCode").append("<p>正在停止MySQL服务...</p>");
                            pluginIndexService('mysql','stop', function (r2) {
                                $(".SafeRestartCode p").addClass('c9');
                                $(".SafeRestartCode").append("<p>开始重启服务器...</p>");
                                $.post('/system/restart_server', '',function (rdata) {
                                    $(".SafeRestartCode p").addClass('c9');
                                    $(".SafeRestartCode").append("<p>等待服务器启动...</p>");
                                    var sEver = setInterval(function () {
                                       $.get("/system/system_total", function(info) {
                                            clearInterval(sEver);
                                            $(".SafeRestartCode p").addClass('c9');
                                            $(".SafeRestartCode").append("<p>服务器重启成功!...</p>");
                                            setTimeout(function () {
                                                layer.closeAll();
                                            }, 3000);
                                        })
                                    }, 3000);
                                })
                            })
                        })
                    })
                }, 100);
                break;
        }
    });
}

//修复面板
function repPanel() {
    layer.confirm(lan.index.rep_panel_msg, { title: lan.index.rep_panel_title, closeBtn: 1, icon: 3 }, function() {
        var loadT = layer.msg(lan.index.rep_panel_the, { icon: 16, time: 0, shade: [0.3, '#000'] });
        $.get('/system?action=RepPanel', function(rdata) {
            layer.close(loadT);
            layer.msg(lan.index.rep_panel_ok, { icon: 1 });
        }).error(function() {
            layer.close(loadT);
            layer.msg(lan.index.rep_panel_ok, { icon: 1 });
        });
    });
}

//获取警告信息
function getWarning() {
    $.get('/ajax?action=GetWarning', function(wlist) {
        var num = 0;
        for (var i = 0; i < wlist.data.length; i++) {
            if (wlist.data[i].ignore_count >= wlist.data[i].ignore_limit) continue;
            if (wlist.data[i].ignore_time != 0 && (wlist.time - wlist.data[i].ignore_time) < wlist.data[i].ignore_timeout) continue;
            var btns = '';
            for (var n = 0; n < wlist.data[i].btns.length; n++) {
                if (wlist.data[i].btns[n].type == 'javascript') {
                    btns += '<a href="javascript:WarningTo(\'' + wlist.data[i].btns[n].url + '\',' + wlist.data[i].btns[n].reload + ');" class="' + wlist.data[i].btns[n].class + '"> ' + wlist.data[i].btns[n].title + '</a>'
                } else {
                    btns += '<a href="' + wlist.data[i].btns[n].url + '" class="' + wlist.data[i].btns[n].class + '" target="' + wlist.data[i].btns[n].target + '"> ' + wlist.data[i].btns[n].title + '</a>'
                }
            }
            $("#messageError").append('<p><img src="' + wlist.icon[wlist.data[i].icon] + '" style="margin-right:14px;vertical-align:-3px">' + wlist.data[i].body + btns + '</p>');
            num++;
        }
        if (num > 0) $("#messageError").show();
    });
}

//按钮调用
function warningTo(to_url, def) {
    var loadT = layer.msg(lan.public.the_get, { icon: 16, time: 0, shade: [0.3, '#000'] });
    $.post(to_url, {}, function(rdata) {
        layer.close(loadT);
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
        if (rdata.status && def) setTimeout(function() { location.reload(); }, 1000);
    },'json');
}

function setSafeHide() {
    setCookie('safeMsg', '1');
    $("#safeMsg").remove();
}

//查看报告
function showDanger(num, port) {
    var atxt = "因未使用安全隔离登录，所有IP都可以尝试连接，存在较高风险，请立即处理。";
    if (port == "22") {
        atxt = "因未修改SSH默认22端口，且未使用安全隔离登录，所有IP都可以尝试连接，存在较高风险，请立即处理。";
    }
    layer.open({
        type: 1,
        area: ['720px', '410px'],
        title: '安全提醒(如你想放弃任何安全提醒通知，请删除宝塔安全登录插件)',
        closeBtn: 1,
        shift: 5,
        content: '<div class="pd20">\
                <table class="f14 showDanger">\
                    <tbody>\
                    <tr><td class="text-right" width="150">风险类型：</td><td class="f16" style="color:red">暴力破解 <a href="https://www.bt.cn/bbs/thread-9562-1-1.html" class="btlink f14" style="margin-left:10px" target="_blank">说明</a></td></tr>\
                    <tr><td class="text-right">累计遭遇攻击总数：</td><td class="f16" style="color:red">' + num + ' <a href="javascript:showDangerIP();" class="btlink f14" style="margin-left:10px">详细</a><span class="c9 f12" style="margin-left:10px">（数据直接来源本服务器日志）</span></td></tr>\
                    <tr><td class="text-right">风险等级：</td><td class="f16" style="color:red">较高风险</td></tr>\
                    <tr><td class="text-right" style="vertical-align:top">风险描述：</td><td style="line-height:20px">' + atxt + '</td></tr>\
                    <tr><td class="text-right" style="vertical-align:top">可参考解决方案：</td><td><p style="margin-bottom:8px">方案一：修改SSH默认端口，修改SSH验证方式为数字证书，清除近期登陆日志。</p><p>方案二：购买宝塔企业运维版，一键部署安全隔离服务，高效且方便。</p></td></tr>\
                    </tbody>\
                </table>\
            </div>'
    });
    $(".showDanger td").css("padding", "8px");
}

function pluginInit(){
    $.post('/plugins/init', function(data){
        if (!data.status){
            return false;
        }

        var rdata = data.data;
        var plugin_list = '';

        for (var i = 0; i < rdata.length; i++) {
            var ver = rdata[i]['versions'];
            var select_list = '';
            if (typeof(ver)=='string'){
                select_list = '<option value="' + ver +'">' + rdata[i]['title'] + ' - ' + ver + '</option>';
            } else {
                for (var vi = 0; vi < ver.length; vi++) {

                    if (ver[vi] == rdata[i]['default_ver']){
                        select_list += '<option value="'+ver[vi]+'" selected="selected">'+ rdata[i]['title'] + ' - '+ ver[vi] + '</option>';
                    } else {
                        select_list += '<option value="'+ver[vi]+'">'+ rdata[i]['title'] + ' - '+ ver[vi] + '</option>';
                    }
                }
            }

            var pn_checked = '<input id="data_'+rdata[i]['name']+'" type="checkbox" checked>';
            if (rdata[i]['name'] == 'swap'){
                var pn_checked = '<input id="data_'+rdata[i]['name']+'" type="checkbox" disabled="disabled" checked>';
            }
            
            plugin_list += '<li><span class="ico"><img src="/plugins/file?name='+rdata[i]['name']+'&f=ico.png"></span>\
            <span class="name">\
                <select id="select_'+rdata[i]['name']+'" class="sl-s-info">'+select_list+'</select>\
            </span>\
            <span class="pull-right">'+pn_checked+'</span></li>';
        }

        layer.open({
            type: 1,
            title: '推荐安装',
            area: ["320px", "400px"],
            closeBtn: 2,
            shadeClose: false,
            content:"\
        <div class='rec-install'>\
            <div class='important-title'>\
                <p><span class='glyphicon glyphicon-alert' style='color: #f39c12; margin-right: 10px;'></span>推荐以下一键套件，或在<a href='javascript:jump()' style='color:#20a53a'>软件管理</a>按需选择。</p>\
                <!-- <button style='margin-top: 8px;height: 30px;' type='button' class='btn btn-sm btn-default no-show-rec-btn'>不再显示推荐</button> -->\
            </div>\
            <div class='rec-box'>\
                <h3 style='text-align: center'>经典LNMP</h3>\
                <div class='rec-box-con'>\
                    <ul class='rec-list'>" + plugin_list + "</ul>\
                    <div class='onekey'>一键安装</div>\
                </div>\
            </div>\
        </div>",
            success:function(l,index){
                $('.rec-box-con .onekey').click(function(){
                    var post_data = [];
                    for (var i = 0; i < rdata.length; i++) {
                        var key_ver = '#select_'+rdata[i]['name'];
                        var key_checked = '#data_'+rdata[i]['name'];

                        var val_checked = $(key_checked).prop("checked");
                        if (val_checked){

                            var tmp = {};
                            var val_key = $(key_ver).val();

                            tmp['version'] = val_key;
                            tmp['name'] = rdata[i]['name'];
                            post_data.push(tmp);
                        }
                    }

                    $.post('/plugins/init_install', 'list='+JSON.stringify(post_data), function(data){
                        showMsg(data.msg, function(){
                            if (data.status){
                                layer.closeAll();
                                messageBox();
                            }
                        },{ icon: data.status ? 1 : 2 },2000);
                    },'json');
                });   
            },
            cancel:function(){
                layer.confirm('是否不再显示推荐安装套件?', {btn : ['确定', '取消'],title: "不再显示推荐?"}, function() {
                    $.post('/files/create_dir', 'path=/www/server/php', function(rdata) {
                        layer.closeAll();
                    },'json');
                });
            }
        });
    },'json');
}

function loadKeyDataCount(){
    var plist = ['mysql', 'gogs', 'gitea'];
    for (var i = 0; i < plist.length; i++) {
        pname = plist[i];
        function call(pname){
            $.post('/plugins/run', {name:pname, func:'get_total_statistics'}, function(data) {
                try {
                    var rdata = $.parseJSON(data['data']);
                } catch(e){
                    return;
                }
                if (!rdata['status']){
                    return;
                }
                var html = '<li class="sys-li-box col-xs-3 col-sm-3 col-md-3 col-lg-3">\
                        <p class="name f15 c9">'+pname+'</p>\
                        <div class="val"><a class="btlink" onclick="softMain(\''+pname+'\',\''+pname+'\',\''+rdata['data']['ver']+'\')">'+rdata['data']['count']+'</a></div>\
                    </li>';
                $('#index_overview').append(html);
            },'json');
        }
        call(pname);
    }
}

$(function() {
    $(".mem-release").hover(function() {
        $(this).addClass("shine_green");
        if (!($(this).hasClass("mem-action"))) {
            $(this).find(".mem-re-min").hide();
            $(this).find(".mask").css({ "color": "#d2edd8" });
            $(this).find(".mem-re-con").css({ "display": "block" });
            $(this).find(".mem-re-con").animate({ "top": "0", opacity: 1 });
            $("#memory").text('内存释放');
        }
    }, function() {
        $(this).removeClass("shine_green");
        $(this).find(".mask").css({ "color": "#20a53a" });
        $(this).find(".mem-re-con").css({ "top": "15px", opacity: 1, "display": "none" });
        $("#memory").text(getCookie("mem-before"));
        $(this).find(".mem-re-min").hide();
    }).click(function() {
        $(this).find(".mem-re-min").hide();
        if (!($(this).hasClass("mem-action"))) {
            reMemory();
            var btlen = $(".mem-release").find(".mask span").text();
            $(this).addClass("mem-action");
            $(this).find(".mask").css({ "color": "#20a53a" });
            $(this).find(".mem-re-con").animate({ "top": "-400px", opacity: 0 });
            $(this).find(".pie_right .right").css({ "transform": "rotate(3deg)" });
            for (var i = 0; i < btlen; i++) {
                setTimeout("rocket(" + btlen + "," + i + ")", i * 30);
            }
        }
    });

    $("select[name='network-io'],select[name='disk-io']").change(function () {
        var key = $(this).val(), type = $(this).attr('name');
        if (type == 'network-io') {
            if (key == 'ALL') {
                key = '';
            }
            setCookie('network_io_key', key);
        } else {
            if (key == 'ALL') {
                key = '';
            }
            setCookie('disk_io_key', key);
        }
    });

    $('.tabs-nav span').click(function () {
        var indexs = $(this).index();
        $(this).addClass('active').siblings().removeClass('active');
        $('.tabs-content .tabs-item:eq(' + indexs + ')').addClass('tabs-active').siblings().removeClass('tabs-active');
        $('.tabs-down select:eq(' + indexs + ')').removeClass('hide').siblings().addClass('hide');
        switch (indexs) {
        case 0:
          index.net.table.resize();
          break;
        case 1:
          index.iostat.table.resize();
          break;
        }
    })
});

var index = {
    common:{
        ts:function (m) { return m < 10 ? '0' + m : m },
        format:function (sjc) {
            var time = new Date(sjc);
            var h = time.getHours();
            var mm = time.getMinutes();
            var s = time.getSeconds();
            return h+ ':' + mm + ':' +s;
        },
        getTime:function () {
            var now = new Date();
            var hour = now.getHours();
            var minute = now.getMinutes();
            var second = now.getSeconds();
            if (minute < 10) {
                minute = "0" + minute;
            }
            if (second < 10) {
                second = "0" + second;
            }
            var nowdate = hour + ":" + minute + ":" + second;
            return nowdate;
        },
    },
    net: {
        table: null,
        data: {
          xData: [],
          yData: [],
          zData: []
        },
        default_unit : 'KB/s',
        init_select : false,
        init: function(){
            for (var i = 8; i >= 0; i--) {
                var time = (new Date()).getTime();
                index.net.data.xData.push(index.common.format(time - (i * 3 * 1000)));
                index.net.data.yData.push(0);
                index.net.data.zData.push(0);
            }

            index.net.table = echarts.init(document.getElementById('netImg'));
            var option = index.net.defaultOption();
            index.net.table.setOption(option);

            window.addEventListener("resize", function () {
                index.net.table.resize();
            });
        },
        render:function(){
            index.net.table.setOption({
                yAxis: {
                    name:  '单位 '+ index.net.default_unit,
                    splitLine: { lineStyle: { color: "#eee" } },
                    axisLine: { lineStyle: { color: "#666" } }
                },
                xAxis: {
                    data: index.net.data.xData
                },
                series: [{
                    name: lan.index.net_up,
                    data: index.net.data.yData
                }, {
                    name: lan.index.net_down,
                    data: index.net.data.zData
                }]
            });
        },
        defaultOption:function(){
            var option = {
                title: {
                    text: "",
                    left: 'center',
                    textStyle: {
                        color: '#888888',
                        fontStyle: 'normal',
                        fontFamily: "宋体",
                        fontSize: 16,
                    }
                },
                tooltip: {
                    trigger: 'axis',
                    formatter :function (config) {
                        var _config = config, _tips = "时间：" + _config[0].axisValue + "<br />";
                        for (var i = 0; i < config.length; i++) {
                            if (typeof config[i].data == "undefined") {
                                return false;
                            }
                            _tips += '<span style="display: inline-block;width: 10px;height: 10px;border-radius: 50%;background: ' + config[i].color + ';"></span>&nbsp;&nbsp;<span>' + config[i].seriesName + '：' + config[i].data + ' '+ index.net.default_unit + '</span><br />'
                        }
                        return _tips;
                    }

                },
                legend: {
                    data: [lan.index.net_up, lan.index.net_down],
                    bottom: '2%'
                },
                xAxis: {
                    type: 'category',
                    boundaryGap: false,
                    data: index.net.data.xData,
                    axisLine: {
                        lineStyle: {
                            color: "#666"
                        }
                    }
                },
                yAxis: {
                    name:  '单位 '+ index.net.default_unit,
                    splitLine: {
                        lineStyle: { color: "#eee" }
                    },
                    axisLine: {
                        lineStyle: { color: "#666" }
                    }
                },
                series: [{
                    name: '上行',
                    type: 'line',
                    data: index.net.data.yData,
                    smooth: true,
                    showSymbol: false,
                    symbol: 'circle',
                    symbolSize: 6,
                    areaStyle: {
                        normal: {
                            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{
                                offset: 0,
                                color: 'rgba(255, 140, 0,0.5)'
                            }, {
                                offset: 1,
                                color: 'rgba(255, 140, 0,0.8)'
                            }], false)
                        }
                    },
                    itemStyle: {
                        normal: {
                            color: '#f7b851'
                        }
                    },
                    lineStyle: {
                        normal: {
                            width: 1
                        }
                    }
                },
                {
                    name: '下行',
                    type: 'line',
                    data: index.net.data.zData,
                    smooth: true,
                    showSymbol: false,
                    symbol: 'circle',
                    symbolSize: 6,
                    areaStyle: {
                        normal: {
                            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{
                                offset: 0,
                                color: 'rgba(30, 144, 255,0.5)',
                            }, {
                                offset: 1,
                                color: 'rgba(30, 144, 255,0.8)',
                            }], false)
                        }
                    },
                    itemStyle: {
                        normal: {
                            color: '#52a9ff',
                        }
                    },
                    lineStyle: {
                        normal: {
                            width: 1,
                        }
                    }
                }]
            };
            return option;
        },

        
        add: function (up, down) {
            var _net = this;
            var limit = 8;
            var d = new Date()
            if (_net.data.xData.length >= limit) _net.data.xData.splice(0, 1);
            if (_net.data.yData.length >= limit) _net.data.yData.splice(0, 1);
            if (_net.data.zData.length >= limit) _net.data.zData.splice(0, 1);

            _net.data.xData.push(d.getHours() + ':' + d.getMinutes() + ':' + d.getSeconds());

            if (up>down){
                var upTmp = toSizePos(up);
                var upTmpSize = upTmp['name'].split(' ')[0];
                index.net.default_unit = upTmp['name'].split(' ')[1] + '/s';

                var downTmpSize = toSizePos(down,upTmp['pos'])['name'].split(' ')[0];
                // console.log('up',upTmp['pos'],toSizePos(down, upTmp['pos']),downTmpSize);

                _net.data.zData.push(downTmpSize);
                _net.data.yData.push(upTmpSize);
            } else {

                var downTmp = toSizePos(down);
                var downTmpSize = downTmp['name'].split(' ')[0];
                index.net.default_unit = downTmp['name'].split(' ')[1] + '/s';

                var upTmpSize = toSizePos(up, downTmp['pos'])['name'].split(' ')[0];
                // console.log('down',downTmp['pos'],toSizePos(up, downTmp['pos']),upTmpSize);

                _net.data.zData.push(downTmpSize);
                _net.data.yData.push(upTmpSize);
            }
            
        },
        renderSelect:function(net){
            // console.log(net);
            if (!index.net.init_select){
                var option = '';
                var network = net.network;
                var network_io_key = getCookie('network_io_key');

                for (var name in network) {
                    if (name == 'ALL'){
                        option += '<option value="'+name+'">全部</option>';
                    } else if (network_io_key == name){
                        option += '<option value="'+name+'" selected>'+name+'</option>';
                    } else {
                        option += '<option value="'+name+'">'+name+'</option>';
                    }
                }
                $('select[name="network-io"]').html(option);
                index.net.init_select = true;
            }
        }
    },

    iostat:{
        table: null,
        data: {
          xData: [],
          yData: [],
          zData: [],
          tipsData: []
        },
        init_select:false,
        default_unit : 'MB/s',
        init:function(){
            for (var i = 8; i >= 0; i--) {
                var time = (new Date()).getTime();
                index.iostat.data.xData.push(index.common.format(time - (i * 3 * 1000)));
                index.iostat.data.yData.push(0);
                index.iostat.data.zData.push(0);
                index.iostat.data.tipsData.push({});
            }

            index.iostat.table = echarts.init(document.getElementById('ioStat'));
            var option = index.iostat.defaultOption();
            index.iostat.table.setOption(option);

            window.addEventListener("resize", function () {
                index.iostat.table.resize();
            });
        },

        render:function(){
            index.iostat.table.setOption({
                tooltip: {
                    trigger: 'axis',
                    formatter :function (config) {
                        var _config = config, _tips = "时间：" + _config[0].axisValue + "<br />", options = {
                            read_bytes: '读取字节数',
                            read_count: '读取次数 ',
                            read_merged_count: '合并读取次数',
                            read_time: '读取延迟',
                            write_bytes: '写入字节数',
                            write_count: '写入次数',
                            write_merged_count: '合并写入次数',
                            write_time: '写入延迟',
                        }, data = index.iostat.data.tipsData[config[0].dataIndex], list = ['read_count', 'write_count', 'read_merged_count', 'write_merged_count', 'read_time', 'write_time',];
                        for (var i = 0; i < config.length; i++) {
                            if (typeof config[i].data == "undefined") {
                                return false;
                            }
                            _tips += '<span style="display: inline-block;width: 10px;height: 10px;border-radius: 50%;background: ' + config[i].color + ';"></span>&nbsp;&nbsp;<span>' + config[i].seriesName + '：' + config[i].data + ' MB/s' + '</span><br />'
                        }
                        $.each(list, function (index, item) {

                            if (typeof data[item] != 'undefined'){
                                _tips += '<span style="display: inline-block;width: 10px;height: 10px;"></span>&nbsp;&nbsp;<span style="' + (item.indexOf('time') > -1 ? ('color:' + ((data[item] > 100 && data[item] < 1000) ? '#ff9900' : (data[item] >= 1000 ? 'red' : '#20a53a'))) : '') + '">' + options[item] + '：' + data[item] + (item.indexOf('time') > -1 ? ' ms' : ' 次/秒') + '</span><br />';
                            }
                        })
                        return _tips;
                    }
                },
                yAxis: {
                    name:  '单位 '+ index.iostat.default_unit,
                    splitLine: { lineStyle: { color: "#eee" } },
                    axisLine: { lineStyle: { color: "#666" } }
                },
                xAxis: {
                    data: index.iostat.data.xData
                },
                series: [{
                    name: "读取",
                    data: index.iostat.data.yData
                }, {
                    name: "写入",
                    data: index.iostat.data.zData
                }]
            });
        },
        defaultOption:function(){
            var option = {
                title: {
                    text: "",
                    left: 'center',
                    textStyle: {
                        color: '#888888',
                        fontStyle: 'normal',
                        fontFamily: "宋体",
                        fontSize: 16,
                    }
                },
                tooltip: {
                    trigger: 'axis'
                },
                legend: {
                    data: ["读取", "写入"],
                    bottom: '2%'
                },
                xAxis: {
                    type: 'category',
                    boundaryGap: false,
                    data: index.iostat.data.xData,
                    axisLine: {
                        lineStyle: {
                            color: "#666"
                        }
                    }
                },
                yAxis: {
                    name:  '单位 '+ index.iostat.default_unit,
                    splitLine: {
                        lineStyle: { color: "#eee" }
                    },
                    axisLine: {
                        lineStyle: { color: "#666" }
                    }
                },
                series: [{
                    name: '读取',
                    type: 'line',
                    data: index.iostat.data.yData,
                    smooth: true,
                    showSymbol: false,
                    symbol: 'circle',
                    areaStyle: {
                        normal: {
                            color: 'rgb(255, 70, 131)'
                        }
                    },
                    itemStyle: {
                        normal: {
                            color: 'rgb(255, 70, 131)'
                        }
                    },
                    lineStyle: {
                        normal: {
                            width: 1,
                        }
                    }
                },
                {
                    name: '写入',
                    type: 'line',
                    data: index.iostat.data.zData,
                    smooth: true,
                    showSymbol: false,
                    symbol: 'circle',
                    symbolSize: 6,
                    areaStyle: {
                        normal: {
                            color: 'rgba(46, 165, 186, .7)'
                        }
                    },
                    itemStyle: {
                        normal: {
                            color: 'rgba(46, 165, 186, .7)'
                        }
                    },
                    lineStyle: {
                        normal: {
                            width: 1,
                        }
                    }
                }]
            };
            return option;
        },

        renderSelect:function(data){
            if (!index.iostat.init_select){
                var option = '';
                var iostat = data.iostat;
                var disk_io_key = getCookie('disk_io_key');

                for (var name in iostat) {
                    if (name == 'ALL'){
                        option += '<option value="'+name+'">全部</option>';
                    } else if (disk_io_key == name){
                        option += '<option value="'+name+'" selected>'+name+'</option>';
                    } else {
                        option += '<option value="'+name+'">'+name+'</option>';
                    }
                }
                $('select[name="disk-io"]').html(option);
                index.iostat.init_select = true;
            }
        },
        add: function (read, write, data) {
            var _iostat = this;
            var limit = 8;
            var d = new Date()
            if (_iostat.data.xData.length >= limit) _iostat.data.xData.splice(0, 1);
            if (_iostat.data.yData.length >= limit) _iostat.data.yData.splice(0, 1);
            if (_iostat.data.zData.length >= limit) _iostat.data.zData.splice(0, 1);
            if (_iostat.data.tipsData.length >= limit) _iostat.data.tipsData.splice(0, 1);


            var readTmpSize = toSizeMB(read).split(' ')[0];
            var writeTmpSize = toSizeMB(write).split(' ')[0];

            _iostat.data.zData.push(writeTmpSize);
            _iostat.data.yData.push(readTmpSize);
            _iostat.data.tipsData.push(data);
            _iostat.data.xData.push(d.getHours() + ':' + d.getMinutes() + ':' + d.getSeconds());
        },

    },
    getData:function(){

        $.get("/system/network", function(net) {

            //网络IO
            var network_io_key = getCookie('network_io_key');
            var network_data = net.network;
            var network_select = network_data['ALL'];
            if (network_io_key && network_io_key != ''){
                network_select = network_data[network_io_key];
            }

            index.net.add(network_select.up,network_select.down);
            index.net.render();
            index.net.renderSelect(net);

            $("#upSpeed").html(toSize(network_select.up));
            $("#downSpeed").html(toSize(network_select.down));

            $("#downAll").html(toSize(network_select.downTotal));
            $("#downAll").attr('title','数据包:' + network_select.downPackets)
            $("#upAll").html(toSize(network_select.upTotal));
            $("#upAll").attr('title','数据包:' + network_select.upPackets)


            //磁盘IO
            var disk_io_key = getCookie('disk_io_key');
            var iostat_data = net.iostat;
            var iostat_select = iostat_data['ALL'];
            if (disk_io_key && disk_io_key != ''){
                iostat_select = iostat_data[disk_io_key];
            }

            index.iostat.add(iostat_select.read_bytes,iostat_select.write_bytes, iostat_select);
            index.iostat.render();
            index.iostat.renderSelect(net);

            $("#readBytes").html(toSize(iostat_select.read_bytes));
            $("#writeBytes").html(toSize(iostat_select.write_bytes));
            $("#diskIops").html(iostat_select.read_count+":"+iostat_select.write_count+ " 次");
            $("#diskTime").html(iostat_select.read_time+":"+iostat_select.write_time +" ms");


            $("#core").html(net.cpu[1] + " " + lan.index.cpu_core);
            $("#state").html(net.cpu[0]);
            
            setcolor(net.cpu[0], "#state", 30, 70, 90);
            //负载
            getLoad(net.load);
            //内存
            setMemImg(net.mem);
            //绑定hover事件
            setImg();
            showCpuTips(net);

        },'json');
    },
    task:function(){
        // index.getData();
        setInterval(function() {
            index.getData();
        }, 3000);
    },
    init: function(){
        index.net.init();
        index.iostat.init();
        index.task();
    }
}
