//获取负载
function getLoad(data) {
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

$('#LoadList .circle').on('click', function() {
    // getNet();
});

$('#LoadList .mask').on('mouseenter', function() {
    var one, five, fifteen;
    var that = this;
    one = getCookie('one');
    five = getCookie('five');
    fifteen = getCookie('fifteen');
    var text = '最近1分钟平均负载：' + one + '</br>最近5分钟平均负载：' + five + '</br>最近15分钟平均负载：' + fifteen + '';
    layer.tips(text, that, { time: 0, tips: [1, '#999'] });
}).on('mouseleave', function() {
    layer.closeAll('tips');
});


function showCpuTips(rdata){
    $('#cpuChart .mask').off().on('mouseenter', function() {
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
    }).on('mouseleave', function() {
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
        $("#state").html(parseFloat(info.cpuRealUsed).toFixed(1));
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
        $("#state").html(parseFloat(net.cpu[0]).toFixed(1));
        setcolor(net.cpu[0], "#state", 30, 70, 90);
        setCookie("upNet", net.up);
        setCookie("downNet", net.down);

        // 自动更新左侧与顶部的排队任务总数，完成首页接口合并
        if (typeof(net.task_count) !== 'undefined') {
            $(".task").text(net.task_count);
        }

        //负载
        getLoad(net.load);

        //内存
        setMemImg(net.mem);

        //绑定hover事件
        setImg();
        showCpuTips(net);

        if (typeof window.updateNetChart === 'function') {
            window.updateNetChart();
        }
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
    window.updateNetChart = function() {
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
    };

    setInterval(function() {
        if (document.visibilityState !== 'visible') {
            return; // 网页切入后台，自动暂停高频轮询以节省能耗与带宽
        }
        getNet();
    }, 3000);

    // 使用刚指定的配置项和数据显示图表。
    echartsNetImg.setOption(option);
    window.addEventListener("resize", function() {
        echartsNetImg.resize();
    });
}


var setImgTimer = null;
function setImg() {
    if (setImgTimer) clearTimeout(setImgTimer);
    setImgTimer = setTimeout(function() {
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

        $('.diskbox .mask').off().on('mouseenter', function() {
            layer.closeAll('tips');
            var that = this;
            var conterError = $(this).attr("data");
            layer.tips(conterError, that, { time: 0, tips: [1, '#999'] });
        }).on('mouseleave', function() {
            layer.closeAll('tips');
        });
    }, 100);
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
    },'json').fail(function() {
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
        var isTest = (v.split('.').length > 3);
        var tagHtml = isTest ? 
            '<span style="background-color: #f0ad4e; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; line-height: 1.4; display: inline-block; margin-right: 8px;">测试版本</span>' : 
            '<span style="background-color: #20a53a; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; line-height: 1.4; display: inline-block; margin-right: 8px;">正式版本</span>';
        var titleHtml = '<div style="display: flex; align-items: center; height: 100%;">' + tagHtml + '<span style="font-size: 14px; font-weight: bold; color: #333;">版本更新 [' + v + ']</span></div>';

        var parseContent = function() {
            try {
                return marked.parse(rdata.data.content);
            } catch(e) {
                return rdata.data.content.replace(/\n/g, '<br/>');
            }
        };

        var showIt = function(htmlContent) {
            showUpdateUI(v, titleHtml, htmlContent, rdata.data.speed_name);
        };

        if (typeof marked !== 'undefined') {
            showIt(parseContent());
        } else {
            loadScript(staticUrl('/static/js/marked.min.js')).then(function() {
                showIt(parseContent());
            }).catch(function() {
                showIt(rdata.data.content.replace(/\n/g, '<br/>'));
            });
        }
    },'json');
}

function showUpdateUI(version, title, content, speedName) {
    layer.open({
        type: 1,
        title: title,
        area: '650px',
        shadeClose: false,
        closeBtn: 1,
        content: '<style>'
                + '  .update-markdown-wrapper .markdown-body ul, .update-markdown-wrapper .markdown-body ol {'
                + '      padding-left: 1.2em !important;'
                + '      margin-bottom: 12px;'
                + '  }'
                + '  .update-markdown-wrapper .markdown-body li {'
                + '      margin-top: 6px;'
                + '  }'
                + '  .update-markdown-wrapper .markdown-body p {'
                + '      margin-bottom: 12px;'
                + '  }'
                + '  .update-markdown-wrapper .markdown-body h3, .update-markdown-wrapper .markdown-body h4 {'
                + '      margin-top: 16px;'
                + '      margin-bottom: 12px;'
                + '  }'
                + '</style>'
                + '<div class="setchmod bt-form pd20 pb70 update-markdown-wrapper" style="background: #fcfcfc;">'
                + (content ? '<div class="markdown-body" style="padding: 15px 20px; line-height: 1.6; max-height: 400px; overflow-y: auto; margin-bottom: 20px; background: rgba(255, 255, 255, 0.8); border-radius: 8px; backdrop-filter: blur(10px); box-shadow: 0 4px 15px rgba(0, 0, 0, 0.03); border: 1px solid rgba(0,0,0,0.03);">' + content + '</div>' : '')
                + '<div class="update-progress-group" style="padding: 15px 20px; background: #fff; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.02); border: 1px solid rgba(0,0,0,0.04);">'
                + '    <div style="margin-bottom: 12px;">'
                + '        <div style="display:flex; justify-content: space-between; margin-bottom: 6px;"><span class="f12" style="color:#555; font-weight:500;">1. 下载并解压更新包<span id="download-tip-bracket" style="color: #20a53a; font-size: 11px; margin-left: 5px;">（请耐心等待，预计时间5分钟，具体根据您的网络情况而定）</span></span><span id="download-percent" class="f12" style="color:#20a53a; font-weight:600;">0%</span></div>'
                + '        <div style="height: 6px; background: #f0f2f5; border-radius: 6px; overflow: hidden; box-shadow: inset 0 1px 2px rgba(0,0,0,0.02);"><div id="download-bar" class="bt-progress-bar" style="width: 0%; height: 100%; position: relative; background: linear-gradient(90deg, #42d392, #20a53a); border-radius: 6px; transition: width 0.4s ease, background 0.4s ease;"></div></div>'
                + '    </div>'
                + '    <div style="margin-bottom: 12px;">'
                + '        <div style="display:flex; justify-content: space-between; margin-bottom: 6px;"><span class="f12" style="color:#555; font-weight:500;">2. 备份系统核心文件</span><span id="backup-percent" class="f12" style="color:#20a53a; font-weight:600;">0%</span></div>'
                + '        <div style="height: 6px; background: #f0f2f5; border-radius: 6px; overflow: hidden; box-shadow: inset 0 1px 2px rgba(0,0,0,0.02);"><div id="backup-bar" class="bt-progress-bar" style="width: 0%; height: 100%; position: relative; background: linear-gradient(90deg, #42d392, #20a53a); border-radius: 6px; transition: width 0.4s ease, background 0.4s ease;"></div></div>'
                + '    </div>'
                + '    <div style="margin-bottom: 4px;">'
                + '        <div style="display:flex; justify-content: space-between; margin-bottom: 6px;"><span class="f12" style="color:#555; font-weight:500;">3. 安装更新并重启服务</span><span id="install-percent" class="f12" style="color:#20a53a; font-weight:600;">0%</span></div>'
                + '        <div style="height: 6px; background: #f0f2f5; border-radius: 6px; overflow: hidden; box-shadow: inset 0 1px 2px rgba(0,0,0,0.02);"><div id="install-bar" class="bt-progress-bar" style="width: 0%; height: 100%; position: relative; background: linear-gradient(90deg, #42d392, #20a53a); border-radius: 6px; transition: width 0.4s ease, background 0.4s ease;"></div></div>'
                + '    </div>'
                + '</div>'
                + '<div class="bt-form-submit-btn" style="margin-top: 20px;">'
                + '<button type="button" class="btn btn-danger btn-sm btn-title" style="border-radius:6px; padding: 6px 18px; font-weight: 500; transition: all 0.2s;" onclick="layer.closeAll()">取消</button>'
                + '<button type="button" id="start-update-btn" class="btn btn-success btn-sm btn-title" style="border-radius:6px; padding: 6px 18px; margin-left: 10px; font-weight: 500; background-color: #20a53a; border-color: #20a53a; transition: all 0.2s;" onclick="executeSteps(\''+version+'\')" >开始执行</button>'
                + '<button type="button" id="hard-refresh-btn" class="btn btn-default btn-sm btn-title" style="display:none; border-radius:6px; padding: 6px 18px; margin-left: 10px;" onclick="location.href=location.pathname+\'?t=\'+new Date().getTime()" >强制刷新</button>'
                + '</div>'
                + '</div>',
        success: function() {
            var bracket = $("#download-tip-bracket");
            bracket.text("（请耐心等待，预计时间5分钟，具体根据您的网络情况而定）");
        }
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

function hardRefreshWithCountdown() {
    var count = 10;
    var msgBox = layer.msg('服务正在重启中，请等待... <span id="restart-countdown">' + count + '</span> 秒', { icon: 16, time: 0, shade: [0.3, '#000'] });
    var timer = setInterval(function() {
        count--;
        if (count <= 0) {
            clearInterval(timer);
            layer.close(msgBox);
            window.location.href = window.location.pathname + '?t=' + new Date().getTime();
        } else {
            $('#restart-countdown').text(count);
        }
    }, 1000);
}

function updateStep(step, version, barId, textId, callback) {
    $(textId).text("处理中...");
    var intervalId = null;

    if (step == 'download') {
        $(barId).css("width", "0%");
        var startTime = new Date().getTime();
        var tenMinutes = 10 * 60 * 1000;
        var twentyMinutes = 20 * 60 * 1000;
        
        var bracket = $("#download-tip-bracket");
        bracket.text("（请耐心等待，预计时间5分钟，具体根据您的网络情况而定）");
        setTimeout(function() {
            bracket.text("（查找最近加速节点）");
            $.get('/system/update_server?type=info', function(rdata) {
                if (rdata && rdata.data && rdata.data.speed_name && rdata.data.speed_name !== 'Direct') {
                    setTimeout(function() {
                        bracket.text("（正在使用 " + rdata.data.speed_name + " 节点进行加速下载）");
                    }, 800);
                } else {
                    setTimeout(function() {
                        bracket.text("（请耐心等待，预计时间5分钟，具体根据您的网络情况而定）");
                    }, 800);
                }
            }, 'json');
        }, 1000);
        
        intervalId = setInterval(function() {
            var now = new Date().getTime();
            var elapsed = now - startTime;
            
            if (elapsed >= twentyMinutes) {
                clearInterval(intervalId);
                $(textId).text("超时").css("color", "#ff4d4f");
                $(barId).css("background", "#ff4d4f");
                layer.alert("您当前的网络状态欠佳，请稍后再试", {icon: 2, title: '下载超时'}, function(index){
                    layer.close(index);
                    location.reload();
                });
                return;
            }
            
            var progress = 0;
            if (elapsed < tenMinutes) {
                progress = (elapsed / tenMinutes) * 95;
            } else {
                progress = 95;
            }
            $(barId).css("width", progress.toFixed(2) + "%");
            $(textId).text(Math.floor(progress) + "%");
        }, 1000);
    } else {
        $(barId).css("width", "40%");
    }
    
    $.get('/system/update_server?type=update&version=' + version + '&step=' + step, function(rdata) {
        if (intervalId) clearInterval(intervalId);
        if (rdata.status) {
            $(barId).css("width", "100%");
            $(textId).text("已完成").css("color", "#20a53a");
            if (callback) callback();
        } else {
            $(textId).text("失败").css("color", "#ff4d4f");
            $(barId).css("background", "#ff4d4f");
            layer.msg(rdata.msg, {icon: 2});
            $("#start-update-btn").attr("disabled", false).removeClass("disabled").text("重试");
            $(".layui-layer-close").show();
        }
    }, 'json').fail(function() {
        if (intervalId) clearInterval(intervalId);
        if (step == 'install') {
            $(barId).css("width", "100%");
            $(textId).text("已完成").css("color", "#20a53a");
            if (callback) callback();
        } else {
            $(textId).text("连接失败").css("color", "#ff4d4f");
            $(barId).css("background", "#ff4d4f");
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
                <div class="rebt-li"><a data-id="server" class="btn-reboot-server" href="javascript:;"><span class="glyphicon glyphicon-off" style="margin-right: 5px;"></span>重启服务器</a></div>\
                <div class="rebt-li"><a data-id="panel" class="btn-reboot-panel" href="javascript:;"><span class="glyphicon glyphicon-refresh" style="margin-right: 5px;"></span>重启面板</a></div>\
                <div class="rebt-li"><a data-id="repair" class="btn-reboot-repair" href="javascript:;"><span class="glyphicon glyphicon-wrench" style="margin-right: 5px;"></span>修复服务器</a></div>\
                <div style="color:red;text-align:center;margin-top:10px;font-weight:bold;clear:both;">注意：修复服务器会覆盖安装bt_simple面板</div>\
            </div>'
    });

    $('.rebt-con a').on('click', function () {
        var type = $(this).attr('data-id');
        switch (type) {
            case 'panel':
                layer.confirm('即将重启面板服务，继续吗？', { title: '重启面板服务', closeBtn: 1, icon: 3 }, function () {
                    var loadT = layer.load();
                    $.post('/system/restart','',function (rdata) {
                        layer.close(loadT);
                        var count = 10;
                        var msgBox = layer.msg('面板正在重启中，请等待... <span id="restart-countdown">' + count + '</span> 秒', { icon: 16, time: 0, shade: [0.3, '#000'] });
                        var timer = setInterval(function() {
                            count--;
                            if (count <= 0) {
                                clearInterval(timer);
                                layer.close(msgBox);
                                window.location.href = window.location.pathname + '?t=' + new Date().getTime();
                            } else {
                                $('#restart-countdown').text(count);
                            }
                        }, 1000);
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
                    $(".btn-reboot").on('click', function () {
                        rebootbox.close();
                    })
                    $(".WSafeRestart").on('click', function () {
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
        }).fail(function() {
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
                $('.rec-box-con .onekey').on('click', function(){
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
    var plist = ['mysql', 'gogs', 'gitea', 'op_waf', 'fail2ban'];
    var post_data = [];
    for (var i = 0; i < plist.length; i++) {
        post_data.push({name: plist[i], func: 'get_total_statistics'});
    }

    $.post('/plugins/run_batch', {list: JSON.stringify(post_data)}, function(data) {
        for (var i = 0; i < plist.length; i++) {
            var pname = plist[i];
            var rdata_raw = data[pname];
            if (!rdata_raw) continue;
            
            var rdata;
            try {
                if (typeof rdata_raw === 'string') {
                    rdata_raw = JSON.parse(rdata_raw);
                }
                rdata = typeof rdata_raw.data === 'string' ? JSON.parse(rdata_raw.data) : rdata_raw.data;
            } catch(e) {
                continue;
            }
            if (!rdata || !rdata['status']) continue;

            var show_name = pname;
            if (pname == 'op_waf') {
                show_name = '御风OP防火墙';
            } else if (pname == 'mysql') {
                show_name = 'MySQL';
            } else if (pname == 'gogs') {
                show_name = 'Gogs';
            } else if (pname == 'gitea') {
                show_name = 'Gitea';
            } else if (pname == 'fail2ban') {
                show_name = '御风F2B底层防火墙';
            }
            var onclick_str = 'softMain(\''+pname+'\',\''+show_name+'\',\''+rdata['data']['ver']+'\')';
            if (pname == 'mysql') {
                onclick_str = 'window.DEFAULT_ACTIVE_TAB = \'dbList\'; ' + onclick_str;
            }
            if (pname == 'op_waf') {
                onclick_str = 'window.DEFAULT_ACTIVE_TAB = \'wafIndex\'; ' + onclick_str;
            }
            var html = '<li class="sys-li-box col-xs-3 col-sm-3 col-md-3 col-lg-3">\
                    <p class="name f15 c9">'+show_name+'</p>\
                    <div class="val"><a class="btlink" onclick="' + onclick_str + '">'+rdata['data']['count']+'</a></div>\
                </li>';
            $('#index_overview').append(html);
        }
    }, 'json');
}

$(function() {
    $(".mem-release").on('mouseenter', function() {
        $(this).addClass("shine_green");
        if (!($(this).hasClass("mem-action"))) {
            $(this).find(".mem-re-min").hide();
            $(this).find(".mask").css({ "color": "#d2edd8" });
            $(this).find(".mem-re-con").css({ "display": "block" });
            $(this).find(".mem-re-con").animate({ "top": "0", opacity: 1 });
            $("#memory").text('内存释放');
        }
    }).on('mouseleave', function() {
        $(this).removeClass("shine_green");
        $(this).find(".mask").css({ "color": "#20a53a" });
        $(this).find(".mem-re-con").css({ "top": "15px", opacity: 1, "display": "none" });
        $("#memory").text(getCookie("mem-before"));
        $(this).find(".mem-re-min").hide();
    }).on('click', function() {
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

    $("select[name='network-io'],select[name='disk-io']").on('change', function () {
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

    $('.tabs-nav span').on('click', function () {
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
    });

    // 首页概览卡片支持整块点击跳转事件委托
    $('#index_overview').on('click', '.sys-li-box', function(e) {
        if ($(e.target).is('a') || $(e.target).parents('a').length > 0) {
            return;
        }
        var $a = $(this).find('a.btlink');
        if ($a.length) {
            var href = $a.attr('href');
            if (href) {
                window.location.href = href;
                return;
            }
            $a.trigger('click');
        }
    });
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

function showSystemDetails() {
    var loadT = layer.msg('正在获取系统详细信息...', { icon: 16, time: 0, shade: 0.3 });
    $.get('/system/get_system_details', function(res) {
        layer.close(loadT);
        if (!res.status) {
            layer.msg('获取系统信息失败: ' + res.msg, { icon: 2 });
            return;
        }
        var data = res.data;
        
        var css = '<style>' +
            '.glass-layer { background: rgba(255,255,255,0.65) !important; backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px); border: 1px solid rgba(255,255,255,0.8) !important; box-shadow: 0 10px 30px rgba(0,0,0,0.1) !important; border-radius: 12px !important; }' +
            '.glass-layer .layui-layer-title { background: transparent !important; border-bottom: 1px solid rgba(0,0,0,0.08) !important; font-weight: bold; color: #333; font-size:15px; border-radius: 12px 12px 0 0 !important; }' +
            '.glass-card { background: rgba(255,255,255,0.5); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.7); border-radius: 10px; padding: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); height: 100%; transition: all 0.3s ease; }' +
            '.glass-card:hover { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0,0,0,0.08); background: rgba(255,255,255,0.7); }' +
            '.glass-card h4 { margin-top: 0; margin-bottom: 12px; color: #222; font-size: 15px; font-weight: bold; display: flex; align-items: center; }' +
            '.glass-card table td { border: none !important; color: #555; padding: 5px 0 !important; font-size: 13px; }' +
            '.glass-card table td:last-child { text-align: right; font-weight: 500; color: #111; }' +
            '.glass-card table tr:not(:last-child) td { border-bottom: 1px dashed rgba(0,0,0,0.06) !important; }' +
            '.glass-progress-bg { height: 6px; background: rgba(0,0,0,0.08); border-radius: 3px; margin: 5px 0; overflow: hidden; box-shadow: inset 0 1px 2px rgba(0,0,0,0.05); }' +
            '.glass-progress-bar { height: 100%; border-radius: 3px; transition: width 0.6s ease; }' +
            '</style>';

        var renderProgress = function(percent, type) {
            var color = '#20a53a';
            if (percent > 80) color = '#e74c3c';
            else if (percent > 60) color = '#f39c12';
            return '<div class="glass-progress-bg">' +
                   '<div class="glass-progress-bar" style="width: ' + percent + '%; background-color: ' + color + ';"></div>' +
                   '</div>';
        };

                var renderFlags = function(flags) {
            if (!flags) flags = {'AES': false, 'VMX': false, 'AVX2': false, 'AVX512': false};
            var getDesc = function(k) {
                if (k === 'AES') return 'AES：决定了 HTTPS、SSH 等加密解密性能是否有硬件加速。';
                if (k === 'VMX') return 'VMX：决定了服务器是否支持硬件级虚拟化（能否开虚拟机）。';
                if (k === 'AVX2') return 'AVX2：决定了服务器基础的向量运算和浮点运算性能。';
                if (k === 'AVX512') return 'AVX512：决定了是否支持最新的高性能科学计算与 AI 推理指令。';
                return k;
            };
            var html = '';
            for (var key in flags) {
                var desc = getDesc(key);
                if (flags[key]) {
                    html += '<span style="color:#20a53a; font-weight:bold; margin-right:6px; " title="[支持] ' + desc + '">' + key + '</span>';
                } else {
                    html += '<span style="color:#ccc; margin-right:6px; " title="[不支持] ' + desc + '">' + key + '</span>';
                }
            }
            return html;
        };

        var renderTcpCc = function(activeCc) {
            if (!activeCc || activeCc === "未知" || activeCc === "X") return "-";
            var algorithms = ['BBR', 'Cubic', 'Reno'];
            var getDesc = function(a) {
                if (a === 'BBR') return 'BBR：由 Google 开发，能最大化利用带宽，降低延迟。';
                if (a === 'Cubic') return 'Cubic：Linux 默认算法，适合高带宽、低延迟环境。';
                if (a === 'Reno') return 'Reno：传统的拥塞算法，对丢包较敏感。';
                return a;
            };
            var html = '';
            var activeLower = activeCc.toLowerCase();
            var found = false;
            for (var i = 0; i < algorithms.length; i++) {
                var algo = algorithms[i];
                var desc = getDesc(algo);
                if (algo.toLowerCase() === activeLower) {
                    html += '<span style="color:#20a53a; font-weight:bold; margin-right:6px; " title="[当前生效] ' + desc + '">' + algo + '</span>';
                    found = true;
                } else {
                    html += '<span style="color:#ccc; margin-right:6px; " title="[未生效] ' + desc + '">' + algo + '</span>';
                }
            }
            if (!found) {
                html += '<span style="color:#20a53a; font-weight:bold; margin-right:6px; " title="[当前生效]">' + activeCc + '</span>';
            }
            return html;
        };

        var html = css + '<div style="padding: 15px 20px; overflow:hidden;">' +
            '<div class="row">' +
            
            // 操作系统
            '<div class="col-sm-4" style="margin-bottom:15px;">' +
                '<div class="glass-card">' +
                    '<h4><i class="glyphicon glyphicon-modal-window" style="color:#20a53a; margin-right:8px;"></i>操作系统</h4>' +
                    '<table class="table table-condensed" style="margin-bottom:0;">' +
                        '<tr title="操作系统具体的发行版及版本号"><td style="width:70px;">发行版本</td><td>' + data.os.system + '</td></tr>' +
                        '<tr title="系统核心程序版本，影响底层功能和驱动支持"><td>内核版本</td><td>' + data.os.kernel + '</td></tr>' +
                        '<tr title="CPU和操作系统的位数架构，通常为x86_64或aarch64"><td>系统架构</td><td>' + data.os.arch + '</td></tr>' +
                        '<tr title="当前系统运行的物理机或虚拟机环境平台"><td>底层环境</td><td>' + data.os.virtualization + '</td></tr>' +
                    '</table>' +
                '</div>' +
            '</div>' +

            // CPU
            '<div class="col-sm-4" style="margin-bottom:15px;">' +
                '<div class="glass-card">' +
                    '<h4><i class="glyphicon glyphicon-tasks" style="color:#20a53a; margin-right:8px;"></i>处理器</h4>' +
                    '<table class="table table-condensed" style="margin-bottom:0;">' +
                        '<tr title="处理器具体的品牌和型号名称"><td style="width:70px;">硬件型号</td><td>' + data.cpu.model + '</td></tr>' +
                        '<tr title="处理器的物理核心数与逻辑线程总数"><td>核心线程</td><td>' + data.cpu.cores + ' 核 / ' + data.cpu.threads + ' 线程</td></tr>' +
                        '<tr title="处理器当前运行的基础时钟频率"><td>基础频率</td><td>' + data.cpu.freq + '</td></tr>' +
                        '<tr title="处理器支持的高级指令集特性，影响加解密、虚拟化及AI运算性能"><td>指令集</td><td>' + renderFlags(data.cpu.flags) + '</td></tr>' +
                    '</table>' +
                '</div>' +
            '</div>' +

            // 网络与状态
            '<div class="col-sm-4" style="margin-bottom:15px;">' +
                '<div class="glass-card">' +
                    '<h4><i class="glyphicon glyphicon-globe" style="color:#20a53a; margin-right:8px;"></i>网络与状态</h4>' +
                    '<table class="table table-condensed" style="margin-bottom:0;">' +
                        '<tr title="服务器对外的公网或内网IP地址"><td style="width:70px;">IPv4/v6</td><td style="word-break:break-all; font-size:11.5px; line-height:1.3; padding:2px 0 !important;">' + (data.network.ipv4 === "X" ? "-" : data.network.ipv4) + '<br>' + (data.network.ipv6 === "X" ? "-" : data.network.ipv6.split("%")[0]) + '</td></tr>' +
                        '<tr title="服务器所在机房的网络运营商及地理位置"><td>网络节点</td><td>' + data.network.isp + ' (' + data.network.location + ')</td></tr>' +
                        '<tr title="决定网络传输速度和稳定性的 TCP 拥塞控制策略"><td>拥塞算法</td><td>' + renderTcpCc(data.network.tcp_cc) + '</td></tr>' +
                        '<tr title="系统近 1 / 5 / 15 分钟内的平均活跃进程数，反映系统繁忙程度"><td>负载平均</td><td>' + data.status.load + '</td></tr>' +
                    '</table>' +
                '</div>' +
            '</div>' +

            // 内存
            '<div class="col-sm-6" style="margin-bottom:0;">' +
                '<div class="glass-card">' +
                    '<h4><i class="glyphicon glyphicon-hdd" style="color:#20a53a; margin-right:8px;"></i>物理内存 & Swap</h4>' +
                    '<table class="table table-condensed" style="margin-bottom:0;">' +
                        '<tr title="服务器安装的实际物理内存容量及当前使用率"><td style="width:70px;">物理内存</td><td>' + data.memory.used + ' / ' + data.memory.total + ' (' + data.memory.percent.toFixed(1) + '%)</td></tr>' +
                        '<tr><td colspan="2" style="padding-top:2px !important; padding-bottom:8px !important;">' + renderProgress(data.memory.percent) + '</td></tr>' +
                        '<tr title="当物理内存不足时充当临时内存的磁盘虚拟空间(Swap)"><td>交换分区</td><td>' + data.memory.swap_used + ' / ' + data.memory.swap_total + ' (' + data.memory.swap_percent.toFixed(1) + '%)</td></tr>' +
                        '<tr><td colspan="2" style="padding-top:2px !important; padding-bottom:0 !important;">' + renderProgress(data.memory.swap_percent) + '</td></tr>' +
                    '</table>' +
                '</div>' +
            '</div>' +

            // 磁盘
            '<div class="col-sm-6" style="margin-bottom:0;">' +
                '<div class="glass-card">' +
                    '<h4><i class="glyphicon glyphicon-floppy-disk" style="color:#20a53a; margin-right:8px;"></i>磁盘容量</h4>' +
                    '<table class="table table-condensed" style="margin-bottom:0;">' +
                        '<tr title="系统根目录所在磁盘的总容量与已用空间"><td>根目录</td><td>' + data.disk.used + ' / ' + data.disk.total + '</td></tr>' +
                        '<tr><td colspan="2" style="padding-top:2px !important; padding-bottom:8px !important;">' + renderProgress(data.disk.percent) + '</td></tr>' +
                        '<tr title="磁盘当前尚未被占用、可供存储的剩余物理空间"><td>剩余可用</td><td>' + data.disk.free + ' (' + (100 - data.disk.percent).toFixed(1) + '%)</td></tr>' +
                        '<tr><td colspan="2" style="padding-top:2px !important; padding-bottom:0 !important;"><div style="height:6px; margin:5px 0;"></div></td></tr>' +
                    '</table>' +
                '</div>' +
            '</div>' +

            '</div>' +
            '</div>';

        layer.open({
            type: 1,
            title: '系统详情',
            area: ['900px', '500px'], // 增加高度，彻底消除滚动条
            shadeClose: true,
            closeBtn: 1,
            skin: 'glass-layer',
            content: html
        });
    }, 'json');
}

// 运行服务器测速
// 运行服务器测速
function runSpeedTest() {
    var cacheDataStr = localStorage.getItem('bt_speed_test_result');
    var cacheData = null;
    if (cacheDataStr) {
        try {
            cacheData = JSON.parse(cacheDataStr);
        } catch(e) {
            cacheData = null;
        }
    }
    
    // 如果存在缓存且有基本 CPU 信息，说明上次测速成功，直接展示历史数据
    if (cacheData && cacheData.cpu) {
        renderSpeedTestModal(cacheData);
    } else {
        // 否则直接发起新测速
        renderSpeedTestModal(null);
    }
}

// 重置界面并启动新测速
function triggerSpeedReTest() {
    $("#btn-re-test").hide();
    
    // 重置系统配置卡片
    $("#sp-sys-table").hide();
    $("#sp-sys-loader").show();
    $("#sp-os").text('-');
    $("#sp-cpu-model").text('-');
    $("#sp-cpu-detail").hide();
    $("#sp-mem").text('-');
    $("#sp-disk").text('-');
    
    // 重置磁盘IO卡片
    $("#sp-io-container").hide();
    $("#sp-io-loader").show();
    $("#sp-write-val").text('测试中...');
    $("#sp-write-bar").css('width', '0%');
    $("#sp-read-val").text('等待中...').css('color', '#94a3b8');
    $("#sp-read-bar").css('width', '0%');
    
    // 重置云节点状态
    $('.node-row').each(function() {
        $(this).css({
            'background': '#f8fafc',
            'border-color': '#f1f5f9'
        });
        $(this).find('.node-icon').attr('class', 'node-icon glyphicon glyphicon-time').css({
            'animation': '',
            'color': '#94a3b8'
        });
        $(this).find('.node-speed').text('排队中').css('color', '#64748b');
    });
    
    startRealNewTest();
}

// 发起后台测速并开启轮询
function startRealNewTest() {
    var loadT = layer.msg('正在初始化测速环境...', { icon: 16, time: 0, shade: [0.3, '#000'] });
    $.post('/system/speed_test', {}, function(rdata) {
        layer.close(loadT);
        if (!rdata.status) {
            layer.msg(rdata.msg, { icon: 2 });
            $("#btn-re-test").show();
            return;
        }
        runLogPolling(rdata.data);
    }, 'json');
}

// 渲染测速弹窗公共方法
function renderSpeedTestModal(historyData) {
    var elegantHtml = 
        '<div class="elegant-speed-container" style="padding: 20px; background: #fafafa; font-family: -apple-system,BlinkMacSystemFont,PingFang SC,Hiragino Sans GB,Microsoft YaHei,Helvetica Neue,Helvetica,Arial,sans-serif; color: #333; height: 100%; overflow-y: auto;">' +
        '    <div class="row" style="margin-left: -10px; margin-right: -10px;">' +
        '        <!-- 系统配置 -->' +
        '        <div class="col-xs-6" style="padding-left: 10px; padding-right: 10px;">' +
        '            <div style="background: #fff; border-radius: 8px; border: 1px solid #eef2f6; padding: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.02); height: 195px;">' +
        '                <div style="font-weight: 600; color: #475569; margin-bottom: 12px; font-size: 13px; display: flex; align-items: center; gap: 6px;">' +
        '                    <span class="glyphicon glyphicon-info-sign" style="color: #20a53a; font-size:14px;"></span> 系统基本信息' +
        '                </div>' +
        '                <div id="sp-sys-loader" style="color: #94a3b8; text-align: center; padding-top: 40px; font-size: 12px;">' +
        '                    <span class="glyphicon glyphicon-refresh" style="animation: spin 1.2s linear infinite; display: inline-block; margin-right: 6px;"></span>环境准备中...' +
        '                </div>' +
        '                <table id="sp-sys-table" class="table table-condensed" style="font-size: 12px; margin-bottom: 0; display: none; border:none;">' +
        '                    <tr style="border:none;"><td style="color:#64748b; width:95px; border-top:none; padding:6px 0; white-space: nowrap;">系统版本</td><td id="sp-os" style="font-weight:500; color:#1e293b; border-top:none; padding:6px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 280px;">-</td></tr>' +
        '                    <tr>' +
        '                        <td style="color:#64748b; width:95px; border-top:none; padding:6px 0; white-space: nowrap; vertical-align: top;">CPU型号</td>' +
        '                        <td id="sp-cpu" style="font-weight:500; color:#1e293b; border-top:none; padding:6px 0; line-height: 1.4;">' +
        '                            <div id="sp-cpu-model" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 280px;">-</div>' +
        '                            <div id="sp-cpu-detail" style="font-size: 11px; color: #64748b; margin-top: 2px; font-weight: normal; display: none;">-</div>' +
        '                        </td>' +
        '                    </tr>' +
        '                    <tr><td style="color:#64748b; width:95px; border-top:none; padding:6px 0; white-space: nowrap;">物理内存</td><td id="sp-mem" style="font-weight:500; color:#1e293b; border-top:none; padding:6px 0; white-space: nowrap;">-</td></tr>' +
        '                    <tr><td style="color:#64748b; width:95px; border-top:none; padding:6px 0; white-space: nowrap;">硬盘大小</td><td id="sp-disk" style="font-weight:500; color:#1e293b; border-top:none; padding:6px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 280px;">-</td></tr>' +
        '                </table>' +
        '            </div>' +
        '        </div>' +
        '        <!-- 磁盘IO -->' +
        '        <div class="col-xs-6" style="padding-left: 10px; padding-right: 10px;">' +
        '            <div style="background: #fff; border-radius: 8px; border: 1px solid #eef2f6; padding: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.02); height: 195px;">' +
        '                <div style="font-weight: 600; color: #475569; margin-bottom: 12px; font-size: 13px; display: flex; align-items: center; gap: 6px;">' +
        '                    <span class="glyphicon glyphicon-hdd" style="color: #20a53a; font-size:14px;"></span> 磁盘 I/O 读写性能' +
        '                </div>' +
        '                <div id="sp-io-loader" style="color: #94a3b8; text-align: center; padding-top: 40px; font-size: 12px;">' +
        '                    <span class="glyphicon glyphicon-refresh" style="animation: spin 1.2s linear infinite; display: inline-block; margin-right: 6px;"></span>等待测速信号...' +
        '                </div>' +
        '                <div id="sp-io-container" style="display: none; padding-top: 8px;">' +
        '                    <div style="margin-bottom: 15px;">' +
        '                        <div style="display:flex; justify-content: space-between; font-size:12px; margin-bottom: 4px;">' +
        '                            <span style="color:#64748b;">磁盘写入速度</span>' +
        '                            <span id="sp-write-val" style="font-weight:600; color:#20a53a;">测试中...</span>' +
        '                        </div>' +
        '                        <div style="height: 6px; background: #f1f5f9; border-radius: 3px; overflow: hidden;">' +
        '                            <div id="sp-write-bar" style="width: 0%; height: 100%; background: linear-gradient(90deg, #42d392, #20a53a); transition: width 0.5s ease;"></div>' +
        '                        </div>' +
        '                    </div>' +
        '                    <div>' +
        '                        <div style="display:flex; justify-content: space-between; font-size:12px; margin-bottom: 4px;">' +
        '                            <span style="color:#64748b;">磁盘读取速度</span>' +
        '                            <span id="sp-read-val" style="font-weight:600; color:#94a3b8;">等待中...</span>' +
        '                        </div>' +
        '                        <div style="height: 6px; background: #f1f5f9; border-radius: 3px; overflow: hidden;">' +
        '                            <div id="sp-read-bar" style="width: 0%; height: 100%; background: linear-gradient(90deg, #38bdf8, #0284c7); transition: width 0.5s ease;"></div>' +
        '                        </div>' +
        '                    </div>' +
        '                </div>' +
        '            </div>' +
        '        </div>' +
        '    </div>' +
        '    <!-- 下载速度 -->' +
        '    <div style="background: #fff; border-radius: 8px; border: 1px solid #eef2f6; padding: 15px; margin-top: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.02);">' +
        '        <div style="font-weight: 600; color: #475569; margin-bottom: 12px; font-size: 13px; display: flex; align-items: center; justify-content: space-between;">' +
        '            <div style="display: flex; align-items: center; gap: 6px;">' +
        '                <span class="glyphicon glyphicon-globe" style="color: #20a53a; font-size:14px;"></span> 多区域节点下载测速' +
        '            </div>' +
        '            <span style="font-size: 11px; color: #94a3b8; font-weight: normal;">(统一下载 15.4MB 的 ls-lR.gz 文件作为测速基准)</span>' +
        '        </div>' +
        '        <div style="display: flex; flex-direction: column; gap: 8px;" id="sp-nodes-list">' +
        '            <div class="node-row" data-node="阿里云杭州镜像源" style="display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: #f8fafc; border-radius: 6px; border: 1px solid #f1f5f9; transition: all 0.3s ease;">' +
        '                <div style="display:flex; align-items:center; gap: 8px; font-size: 12px; font-weight: 500; color: #334155;">' +
        '                    <span class="node-icon glyphicon glyphicon-time" style="color:#94a3b8; font-size: 12px;"></span>' +
        '                    <span>阿里云杭州镜像源</span>' +
        '                </div>' +
        '                <div class="node-speed" style="font-size: 12px; font-weight: 600; color:#64748b;">排队中</div>' +
        '            </div>' +
        '            <div class="node-row" data-node="腾讯云南京镜像源" style="display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: #f8fafc; border-radius: 6px; border: 1px solid #f1f5f9; transition: all 0.3s ease;">' +
        '                <div style="display:flex; align-items:center; gap: 8px; font-size: 12px; font-weight: 500; color: #334155;">' +
        '                    <span class="node-icon glyphicon glyphicon-time" style="color:#94a3b8; font-size: 12px;"></span>' +
        '                    <span>腾讯云南京镜像源</span>' +
        '                </div>' +
        '                <div class="node-speed" style="font-size: 12px; font-weight: 600; color:#64748b;">排队中</div>' +
        '            </div>' +
        '            <div class="node-row" data-node="华为云深圳镜像源" style="display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: #f8fafc; border-radius: 6px; border: 1px solid #f1f5f9; transition: all 0.3s ease;">' +
        '                <div style="display:flex; align-items:center; gap: 8px; font-size: 12px; font-weight: 500; color: #334155;">' +
        '                    <span class="node-icon glyphicon glyphicon-time" style="color:#94a3b8; font-size: 12px;"></span>' +
        '                    <span>华为云深圳镜像源</span>' +
        '                </div>' +
        '                <div class="node-speed" style="font-size: 12px; font-weight: 600; color:#64748b;">排队中</div>' +
        '            </div>' +
        '            <!-- 境内外分割线 -->' +
        '            <div style="margin: 14px 0 10px 0; border-top: 1px dashed #e2e8f0; text-align: center; position: relative; height: 10px;">' +
        '                <span style="background: #fff; padding: 0 14px; font-size: 11px; color: #94a3b8; font-weight: 600; position: absolute; top: -10px; left: 50%; transform: translateX(-50%); letter-spacing: 0.5px;">境外测试节点 (US / UK / DE / JP)</span>' +
        '            </div>' +
        '            <div class="node-row" data-node="美国官方节点" style="display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: #f8fafc; border-radius: 6px; border: 1px solid #f1f5f9; transition: all 0.3s ease;">' +
        '                <div style="display:flex; align-items:center; gap: 8px; font-size: 12px; font-weight: 500; color: #334155;">' +
        '                    <span class="node-icon glyphicon glyphicon-time" style="color:#94a3b8; font-size: 12px;"></span>' +
        '                    <span>美国官方节点</span>' +
        '                </div>' +
        '                <div class="node-speed" style="font-size: 12px; font-weight: 600; color:#64748b;">排队中</div>' +
        '            </div>' +
        '            <div class="node-row" data-node="英国官方节点" style="display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: #f8fafc; border-radius: 6px; border: 1px solid #f1f5f9; transition: all 0.3s ease;">' +
        '                <div style="display:flex; align-items:center; gap: 8px; font-size: 12px; font-weight: 500; color: #334155;">' +
        '                    <span class="node-icon glyphicon glyphicon-time" style="color:#94a3b8; font-size: 12px;"></span>' +
        '                    <span>英国官方节点</span>' +
        '                </div>' +
        '                <div class="node-speed" style="font-size: 12px; font-weight: 600; color:#64748b;">排队中</div>' +
        '            </div>' +
        '            <div class="node-row" data-node="德国官方节点" style="display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: #f8fafc; border-radius: 6px; border: 1px solid #f1f5f9; transition: all 0.3s ease;">' +
        '                <div style="display:flex; align-items:center; gap: 8px; font-size: 12px; font-weight: 500; color: #334155;">' +
        '                    <span class="node-icon glyphicon glyphicon-time" style="color:#94a3b8; font-size: 12px;"></span>' +
        '                    <span>德国官方节点</span>' +
        '                </div>' +
        '                <div class="node-speed" style="font-size: 12px; font-weight: 600; color:#64748b;">排队中</div>' +
        '            </div>' +
        '            <div class="node-row" data-node="日本官方节点" style="display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: #f8fafc; border-radius: 6px; border: 1px solid #f1f5f9; transition: all 0.3s ease;">' +
        '                <div style="display:flex; align-items:center; gap: 8px; font-size: 12px; font-weight: 500; color: #334155;">' +
        '                    <span class="node-icon glyphicon glyphicon-time" style="color:#94a3b8; font-size: 12px;"></span>' +
        '                    <span>日本官方节点</span>' +
        '                </div>' +
        '                <div class="node-speed" style="font-size: 12px; font-weight: 600; color:#64748b;">排队中</div>' +
        '            </div>' +
        '        </div>' +
        '    </div>' +
        '    <pre id="speed_log_lst" style="display:none;"></pre>' +
        '    <!-- 底部控制栏与出品信息 -->' +
        '    <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 18px; user-select: none;">' +
        '        <div>' +
        '            <button id="btn-re-test" class="btn btn-default btn-xs" style="display: none; padding: 4px 12px; font-size: 11px; color: #475569; background: #fff; border: 1px solid #cbd5e1; border-radius: 4px; transition: all 0.2s ease; font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,0.05);" onclick="triggerSpeedReTest()">' +
        '                <span class="glyphicon glyphicon-repeat" style="font-size: 10px; margin-right: 4px;"></span>再次测试' +
        '            </button>' +
        '        </div>' +
        '        <div style="display: flex; align-items: center; gap: 4px; font-size: 11px; color: #94a3b8; font-weight: 500;">' +
        '            <span class="glyphicon glyphicon-copyright-mark" style="font-size: 10px;"></span>' +
        '            <span>衢州御风科技有限公司出品</span>' +
        '        </div>' +
        '    </div>' +
        '    <style>' +
        '        @keyframes spin {' +
        '            0% { transform: rotate(0deg); }' +
        '            100% { transform: rotate(360deg); }' +
        '        }' +
        '    </style>' +
        '</div>';

    // 打开弹出层
    layer.open({
        title: '<span style="display: inline-flex; align-items: center; gap: 6px;"><svg viewBox="0 0 64 64" width="16" height="16" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle;"><path d="M16 22 h32 v30 h-32 z" /><path d="M26 22 L28 8 h8 L38 22" /><path d="M23 36 v16 M29 36 v16 M35 36 v16 M41 36 v16" stroke-width="3.5" /><path d="M24 52 v6 h16 v-6" /></svg>服务器性能与带宽测速</span>',
        type: 1,
        closeBtn: 1,
        shade: 0.3,
        area: ["860px", "740px"],
        content: elegantHtml,
        success: function(layers, index) {
            if (historyData) {
                // 有历史缓存，直接渲染还原数据
                $("#sp-sys-loader").hide();
                $("#sp-sys-table").show();
                if (historyData.os) $("#sp-os").text(historyData.os).attr('title', historyData.os);
                
                if (historyData.cpu) {
                    var cpuRaw = historyData.cpu;
                    var cpuModel = cpuRaw;
                    var cpuDetail = '';
                    if (cpuRaw.indexOf(' @ ') > -1) {
                        var parts = cpuRaw.split(' @ ');
                        cpuModel = parts[0].trim();
                        cpuDetail = parts[1].trim();
                    } else if (cpuRaw.indexOf('@') > -1) {
                        var parts = cpuRaw.split('@');
                        cpuModel = parts[0].trim();
                        cpuDetail = parts[1].trim();
                    }
                    
                    if (cpuDetail) {
                        var cleanDetail = cpuDetail.replace('(', '').replace(')', '');
                        var detailParts = cleanDetail.split(' ');
                        if (detailParts.length >= 2) {
                            cpuDetail = '主频 ' + detailParts[0] + ' | 核心数 ' + detailParts[1];
                        } else {
                            cpuDetail = cleanDetail;
                        }
                        $("#sp-cpu-detail").text(cpuDetail).show();
                    } else {
                        $("#sp-cpu-detail").hide();
                    }
                    $("#sp-cpu-model").text(cpuModel).attr('title', cpuRaw);
                }
                if (historyData.mem) $("#sp-mem").text(historyData.mem);
                if (historyData.disk) $("#sp-disk").text(historyData.disk);
                
                // 还原磁盘IO
                if (historyData.write_speed) {
                    $("#sp-io-loader").hide();
                    $("#sp-io-container").show();
                    $("#sp-write-val").text(historyData.write_speed);
                    var wSpeed = parseFloat(historyData.write_speed);
                    var wPercent = Math.min(100, Math.round((wSpeed / 600) * 100));
                    if (historyData.write_speed.indexOf('GB/s') > -1) wPercent = 100;
                    $("#sp-write-bar").css('width', wPercent + '%');
                }
                
                if (historyData.read_speed) {
                    $("#sp-read-val").text(historyData.read_speed).css('color', '#20a53a');
                    var rSpeed = parseFloat(historyData.read_speed);
                    var rPercent = Math.min(100, Math.round((rSpeed / 800) * 100));
                    if (historyData.read_speed.indexOf('GB/s') > -1) rPercent = 100;
                    $("#sp-read-bar").css('width', rPercent + '%');
                }
                
                // 还原云节点
                if (historyData.nodes) {
                    Object.keys(historyData.nodes).forEach(function(nodeName) {
                        var node = historyData.nodes[nodeName];
                        var $row = $('.node-row[data-node="' + nodeName + '"]');
                        if ($row.length > 0) {
                            if (node.status === 'finished') {
                                $row.find('.node-icon').attr('class', 'node-icon glyphicon glyphicon-ok-sign').css({
                                    'animation': '',
                                    'color': '#20a53a'
                                });
                                $row.find('.node-speed').text(node.speed).css('color', '#20a53a');
                                $row.css({
                                    'background': 'rgba(32,165,58,0.05)',
                                    'border-color': 'rgba(32,165,58,0.2)'
                                });
                            } else if (node.status === 'failed') {
                                $row.find('.node-icon').attr('class', 'node-icon glyphicon glyphicon-remove-sign').css({
                                    'animation': '',
                                    'color': '#ef4444'
                                });
                                $row.find('.node-speed').text('超时/失败').css('color', '#ef4444');
                                $row.css({
                                    'background': 'rgba(239,68,68,0.03)',
                                    'border-color': 'rgba(239,68,68,0.15)'
                                });
                            } else if (node.status === 'skipped') {
                                $row.find('.node-speed').text('已跳过').css('color', '#94a3b8');
                                $row.find('.node-icon').attr('class', 'node-icon glyphicon glyphicon-ban-circle').css({
                                    'animation': '',
                                    'color': '#94a3b8'
                                });
                            }
                        }
                    });
                }
                
                // 历史记录下，默认展示再次测试按钮
                $("#btn-re-test").show();
            } else {
                // 无历史缓存，直接触发一次全新的真实测速
                startRealNewTest();
            }
        }
    });
}

// 轮询并渲染测速日志
function runLogPolling(log_path) {
    var speedTimer = setInterval(function() {
        if ($("#speed_log_lst").length < 1) {
            clearInterval(speedTimer);
            return;
        }
        
        $.post('/files/get_last_body', { path: log_path, line: '150' }, function(res) {
            if (res.status && res.data) {
                $("#speed_log_lst").html(res.data);
                
                var data = parseSpeedLog(res.data);
                
                // 渲染系统配置
                if (data.os || data.cpu || data.mem || data.disk) {
                    $("#sp-sys-loader").hide();
                    $("#sp-sys-table").show();
                    if (data.os) $("#sp-os").text(data.os).attr('title', data.os);
                    if (data.cpu) {
                        var cpuRaw = data.cpu;
                        var cpuModel = cpuRaw;
                        var cpuDetail = '';
                        if (cpuRaw.indexOf(' @ ') > -1) {
                            var parts = cpuRaw.split(' @ ');
                            cpuModel = parts[0].trim();
                            cpuDetail = parts[1].trim();
                        } else if (cpuRaw.indexOf('@') > -1) {
                            var parts = cpuRaw.split('@');
                            cpuModel = parts[0].trim();
                            cpuDetail = parts[1].trim();
                        }
                        
                        if (cpuDetail) {
                            var cleanDetail = cpuDetail.replace('(', '').replace(')', '');
                            var detailParts = cleanDetail.split(' ');
                            if (detailParts.length >= 2) {
                                cpuDetail = '主频 ' + detailParts[0] + ' | 核心数 ' + detailParts[1];
                            } else {
                                cpuDetail = cleanDetail;
                            }
                            $("#sp-cpu-detail").text(cpuDetail).show();
                        } else {
                            $("#sp-cpu-detail").hide();
                        }
                        $("#sp-cpu-model").text(cpuModel).attr('title', cpuRaw);
                    }
                    if (data.mem) $("#sp-mem").text(data.mem);
                    if (data.disk) $("#sp-disk").text(data.disk);
                }
                
                // 磁盘IO渲染
                if (data.write_speed) {
                    $("#sp-io-loader").hide();
                    $("#sp-io-container").show();
                    $("#sp-write-val").text(data.write_speed);
                    var wSpeed = parseFloat(data.write_speed);
                    var wPercent = Math.min(100, Math.round((wSpeed / 600) * 100));
                    if (data.write_speed.indexOf('GB/s') > -1) wPercent = 100;
                    $("#sp-write-bar").css('width', wPercent + '%');
                }
                
                if (data.read_speed) {
                    $("#sp-read-val").text(data.read_speed).css('color', '#20a53a');
                    var rSpeed = parseFloat(data.read_speed);
                    var rPercent = Math.min(100, Math.round((rSpeed / 800) * 100));
                    if (data.read_speed.indexOf('GB/s') > -1) rPercent = 100;
                    $("#sp-read-bar").css('width', rPercent + '%');
                } else if (data.write_speed) {
                    $("#sp-read-val").text('测试中...').css('color', '#94a3b8');
                }
                
                // 节点状态渲染
                Object.keys(data.nodes).forEach(function(nodeName) {
                    var node = data.nodes[nodeName];
                    var $row = $('.node-row[data-node="' + nodeName + '"]');
                    if ($row.length > 0) {
                        if (node.status === 'running') {
                            $row.find('.node-icon').attr('class', 'node-icon glyphicon glyphicon-refresh').css({
                                'animation': 'spin 1.2s linear infinite',
                                'color': '#20a53a'
                            });
                            $row.find('.node-speed').text(node.speed).css('color', '#20a53a');
                            $row.css({
                                'background': 'rgba(32,165,58,0.03)',
                                'border-color': 'rgba(32,165,58,0.15)'
                            });
                        } else if (node.status === 'finished') {
                            $row.find('.node-icon').attr('class', 'node-icon glyphicon glyphicon-ok-sign').css({
                                'animation': '',
                                'color': '#20a53a'
                            });
                            $row.find('.node-speed').text(node.speed).css('color', '#20a53a');
                            $row.css({
                                'background': 'rgba(32,165,58,0.05)',
                                'border-color': 'rgba(32,165,58,0.2)'
                            });
                        } else if (node.status === 'failed') {
                            $row.find('.node-icon').attr('class', 'node-icon glyphicon glyphicon-remove-sign').css({
                                'animation': '',
                                'color': '#ef4444'
                            });
                            $row.find('.node-speed').text('超时/失败').css('color', '#ef4444');
                            $row.css({
                                'background': 'rgba(239,68,68,0.03)',
                                'border-color': 'rgba(239,68,68,0.15)'
                            });
                        }
                    }
                });
                
                // 判断结束
                if (res.data.indexOf('测速完毕') > -1 || res.data.indexOf('结束时间:') > -1) {
                    clearInterval(speedTimer);
                    $('.node-row').each(function() {
                        var nodeName = $(this).attr('data-node');
                        var txt = $(this).find('.node-speed').text();
                        if (txt === '排队中' || txt === '等待中') {
                            $(this).find('.node-speed').text('已跳过').css('color', '#94a3b8');
                            $(this).find('.node-icon').attr('class', 'node-icon glyphicon glyphicon-ban-circle').css('color', '#94a3b8');
                            data.nodes[nodeName] = { status: 'skipped', speed: '已跳过' };
                        }
                    });
                    
                    // 序列化测速完毕的真实数据并持久化到浏览器 localStorage
                    localStorage.setItem('bt_speed_test_result', JSON.stringify(data));
                    $("#btn-re-test").fadeIn(300);
                }
            }
        }, 'json');
    }, 1000);
}


// 辅助解析日志函数
function parseSpeedLog(logText) {
    var data = {
        cpu: '',
        mem: '',
        disk: '',
        os: '',
        write_speed: '',
        read_speed: '',
        nodes: {}
    };
    
    var lines = logText.split('\n');
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        
        if (line.indexOf('CPU 型号:') > -1) {
            data.cpu = line.replace('CPU 型号:', '').trim();
        } else if (line.indexOf('物理内存:') > -1) {
            data.mem = line.replace('物理内存:', '').trim();
        } else if (line.indexOf('硬盘分区:') > -1) {
            data.disk = line.replace('硬盘分区:', '').trim();
        } else if (line.indexOf('操作系统:') > -1) {
            data.os = line.replace('操作系统:', '').trim();
        } else if (line.indexOf('磁盘写入速度:') > -1) {
            data.write_speed = line.replace('磁盘写入速度:', '').trim();
        } else if (line.indexOf('磁盘读取速度:') > -1) {
            data.read_speed = line.replace('磁盘读取速度:', '').trim();
        } else if (line.indexOf('-> 节点:') > -1 || line.indexOf('-&gt; 节点:') > -1) {
            var nodePart = line.replace('-> 节点:', '').replace('-&gt; 节点:', '').trim();
            var parts = nodePart.split('...');
            if (parts.length >= 1) {
                var nodeName = parts[0].trim();
                var nodeStatus = 'running';
                var nodeSpeed = '下载中...';
                if (parts.length >= 2 && parts[1].trim() !== '') {
                    var val = parts[1].trim();
                    if (val.indexOf('正在测试') > -1 || val.indexOf('测试中') > -1) {
                        nodeStatus = 'running';
                        nodeSpeed = '下载中...';
                    } else if (val.indexOf('连接超时') > -1 || val.indexOf('失败') > -1) {
                        nodeStatus = 'failed';
                        nodeSpeed = '超时/失败';
                    } else {
                        nodeStatus = 'finished';
                        nodeSpeed = val;
                    }
                }
                data.nodes[nodeName] = { status: nodeStatus, speed: nodeSpeed };
            }
        }
    }
    return data;
}