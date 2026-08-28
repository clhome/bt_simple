//获取负载
function getLoad(data) {
  setCookie('one', data.one);
  setCookie('five', data.five);
  setCookie('fifteen', data.fifteen);
  var transformLeft,
    transformRight,
    LoadColor,
    Average,
    Occupy,
    AverageText,
    conterError = '';
  var index = $("#LoadList");
  if (Average == undefined) Average = data.one;
  setCookie('conterError', conterError);
  Occupy = Math.round(Average / data.max * 100);
  if (Occupy > 100) Occupy = 100;
  if (Occupy <= 30) {
    LoadColor = '#20a53a';
    AverageText = lan && lan.index && lan.index.auto_str_1 || "";
  } else if (Occupy <= 70) {
    LoadColor = '#6ea520';
    AverageText = lan && lan.index && lan.index.auto_str_2 || "";
  } else if (Occupy <= 90) {
    LoadColor = '#ff9900';
    AverageText = lan && lan.index && lan.index.auto_str_3 || "";
  } else {
    LoadColor = '#dd2f00';
    AverageText = lan && lan.index && lan.index.auto_str_4 || "";
  }
  index.find('.circle').css("background", LoadColor);
  index.find('.mask').css({
    "color": LoadColor
  });
  $("#LoadList .mask").html("<span id='Load'></span>%");
  $('#Load').html(Occupy);
  $('#LoadState').html('<span>' + AverageText + '</span>');
  setImg();
}
$('#LoadList .circle').on('click', function () {
  // getNet();
});
$('#LoadList .mask').on('mouseenter', function () {
  var one, five, fifteen;
  var that = this;
  one = getCookie('one');
  five = getCookie('five');
  fifteen = getCookie('fifteen');
  var text = (lan && lan.index && lan.index.auto_str_5 || "") + one + (lan && lan.index && lan.index.auto_str_6 || "") + five + (lan && lan.index && lan.index.auto_str_7 || "") + fifteen + '';
  layer.tips(text, that, {
    time: 0,
    tips: [1, '#999']
  });
}).on('mouseleave', function () {
  layer.closeAll('tips');
});
function showCpuTips(rdata) {
  $('#cpuChart .mask').off().on('mouseenter', function () {
    var cpuText = '';
    if (rdata.cpu[2].length == 1) {
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
    layer.tips(rdata.cpu[3] + "</br>" + rdata.cpu[5] + (lan && lan.index && lan.index.auto_str_8 || "") + rdata.cpu[4] + (lan && lan.index && lan.index.auto_str_9 || "") + rdata.cpu[1] + (lan && lan.index && lan.index.auto_str_10 || "") + cpuText, this, {
      time: 0,
      tips: [1, '#999']
    });
  }).on('mouseleave', function () {
    layer.closeAll('tips');
  });
}
function rocket(sum, m) {
  var n = sum - m;
  $(".mem-release").find(".mask span").text(n);
}

//释放内存
function reMemory() {
  setTimeout(function () {
    $(".mem-release").find('.mask').css({
      'color': '#20a53a',
      'font-size': '14px'
    }).html('<span style="display:none">1</span>' + lan.index.memre_ok_0 + ' <img src="/static/img/ings.gif">');
    $.post('/system/rememory', '', function (rdata) {
      var percent = getPercent(rdata.memRealUsed, rdata.memTotal);
      var memText = Math.round(rdata.memRealUsed) + "/" + Math.round(rdata.memTotal) + " (MB)";
      percent = Math.round(percent);
      $(".mem-release").find('.mask').css({
        'color': '#20a53a',
        'font-size': '14px'
      }).html("<span style='display:none'>" + percent + "</span>" + lan.index.memre_ok);
      setCookie("mem-before", memText);
      var memNull = Math.round(getCookie("memRealUsed") - rdata.memRealUsed);
      setTimeout(function () {
        if (memNull > 0) {
          $(".mem-release").find('.mask').css({
            'color': '#20a53a',
            'font-size': '14px',
            'line-height': '22px',
            'padding-top': '22px'
          }).html("<span style='display:none'>" + percent + "</span>" + lan.index.memre_ok_1 + "<br>" + memNull + "MB");
        } else {
          $(".mem-release").find('.mask').css({
            'color': '#20a53a',
            'font-size': '14px'
          }).html("<span style='display:none'>" + percent + "</span>" + lan.index.memre_ok_2);
        }
        $(".mem-release").removeClass("mem-action");
        $("#memory").text(memText);
        setCookie("memRealUsed", rdata.memRealUsed);
      }, 1000);
      setTimeout(function () {
        $(".mem-release").find('.mask').removeAttr("style").html("<span>" + percent + "</span>%");
        $(".mem-release").find(".mem-re-min").show();
      }, 2000);
    }, 'json');
  }, 2000);
}
function getPercent(num, total) {
  num = parseFloat(num);
  total = parseFloat(total);
  if (isNaN(num) || isNaN(total)) {
    return "-";
  }
  return total <= 0 ? "0%" : Math.round(num / total * 10000) / 100.00;
}
function getDiskInfo() {
  $.get('/system/disk_info', function (rdata) {
    var rdata = rdata.data;
    var dBody;
    for (var i = 0; i < rdata.length; i++) {
      var LoadColor = setcolor(parseInt(rdata[i].size[3].replace('%', '')), false, 75, 90, 95);

      //判断inode信息是否存在
      var inodes = '';
      if (typeof rdata[i]['inodes'] !== 'undefined') {
        inodes = '<div class="mask" style="color:' + LoadColor + (lan && lan.index && lan.index.auto_str_11 || "") + rdata[i].inodes[0] + (lan && lan.index && lan.index.auto_str_12 || "") + rdata[i].inodes[1] + (lan && lan.index && lan.index.auto_str_13 || "") + rdata[i].inodes[2] + (lan && lan.index && lan.index.auto_str_14 || "") + rdata[i].inodes[3] + '"><span>' + rdata[i].size[3].replace('%', '') + '</span>%</div>';
        var ipre = parseInt(rdata[i].inodes[3].replace('%', ''));
        if (ipre > 95) {
          $("#messageError").show();
          $("#messageError").append((lan && lan.index && lan.index.auto_str_15 || "") + rdata[i].path + (lan && lan.index && lan.index.auto_str_16 || "") + ipre + (lan && lan.index && lan.index.auto_str_17 || ""));
        }
      }
      if (rdata[i].path == '/' || rdata[i].path == '/www') {
        if (rdata[i].size[2].indexOf('M') != -1) {
          $("#messageError").show();
          $("#messageError").append('<p><span class="glyphicon glyphicon-alert" style="color: #ff4040; margin-right: 10px;"></span> ' + lan.get('diskinfo_span_1', [rdata[i].path]) + (lan && lan.index && lan.index.auto_str_18 || ""));
        }
      }
      dBody = '<li class="col-xs-6 col-sm-3 col-md-3 col-lg-2 mtb20 circle-box text-center diskbox">' + '<h3 class="c5 f15">' + rdata[i].path + '</h3>' + '<div class="circle" style="background:' + LoadColor + '">' + '<div class="pie_left">' + '<div class="left"></div>' + '</div>' + '<div class="pie_right">' + '<div class="right"></div>' + '</div>' + inodes + '</div>' + '<h4 class="c5 f15">' + rdata[i].size[1] + '/' + rdata[i].size[0] + '</h4>' + '</li>';
      $("#systemInfoList").append(dBody);
      setImg();
    }
  }, 'json');
}

//清理垃圾
function clearSystem() {
  var loadT = layer.msg(lan && lan.index && lan.index.auto_str_19 || "", {
    icon: 16,
    time: 0,
    shade: [0.3, "#000"]
  });
  $.get('/system?action=ClearSystem', function (rdata) {
    layer.close(loadT);
    layer.msg((lan && lan.index && lan.index.auto_str_20 || "") + rdata[0] + (lan && lan.index && lan.index.auto_str_21 || "") + toSize(rdata[1]) + (lan && lan.index && lan.index.auto_str_22 || ""), {
      icon: 1
    });
  });
}
function setMemImg(info) {
  var memRealUsed = toSize(info.memRealUsed);
  var memTotal = toSize(info.memTotal);
  var memRealUsedVal = memRealUsed.split(' ')[0];
  var memTotalVal = memTotal.split(' ')[0];
  var unit = memTotal.split(' ')[1];
  var mem_txt = memRealUsedVal + '/' + memTotalVal + ' (' + unit + ')';
  setCookie("mem-before", mem_txt);
  $("#memory").html(mem_txt);
  var memPre = Math.floor(info.memRealUsed / (info.memTotal / 100));
  $("#left").html(memPre);
  setcolor(memPre, "#left", 75, 90, 95);
  var memFree = info.memTotal - info.memRealUsed;
  if (memFree / (1024 * 1024) < 64) {
    $("#messageError").show();
    $("#messageError").append(lan && lan.index && lan.index.auto_str_23 || "");
  }
}
function setSystemInfo(system_str) {
  $("#info").html(system_str);
  var _system = system_str;
  $(".ico-system").removeClass("ico-windows ico-centos ico-ubuntu ico-debian ico-fedora ico-mac ico-linux");
  if (_system.indexOf("Windows") != -1) {
    $(".ico-system").addClass("ico-windows");
  } else if (_system.indexOf("CentOS") != -1) {
    $(".ico-system").addClass("ico-centos");
  } else if (_system.indexOf("Ubuntu") != -1) {
    $(".ico-system").addClass("ico-ubuntu");
  } else if (_system.indexOf("Debian") != -1) {
    $(".ico-system").addClass("ico-debian");
  } else if (_system.indexOf("Fedora") != -1) {
    $(".ico-system").addClass("ico-fedora");
  } else if (_system.indexOf("Mac") != -1) {
    $(".ico-system").addClass("ico-mac");
  } else {
    $(".ico-system").addClass("ico-linux");
  }
}
$(document).ready(function () {
  var cachedSystem = localStorage.getItem('cached_system_info');
  if (cachedSystem) {
    setSystemInfo(cachedSystem);
  }
});
function getInfo() {
  $.get("/system/system_total", function (info) {
    setMemImg(info);
    setSystemInfo(info.system);
    localStorage.setItem('cached_system_info', info.system);
    $("#running").html(info.time);
    $("#core").html(info.cpuNum + (lan && lan.index && lan.index.auto_str_24 || ""));
    $("#state").html(parseFloat(info.cpuRealUsed).toFixed(1));
    setcolor(info.cpuRealUsed, "#state", 30, 70, 90);

    // if (info.isuser > 0) {
    //     $("#messageError").show();
    //     $("#messageError").append('<p><span class="glyphicon glyphicon-alert" style="color: #ff4040; margin-right: 10px;"></span>' + lan.index.user_warning + '<span class="c7 mr5" title="此安全问题不可忽略，请尽快处理" style="cursor:no-drop"> [不可忽略]</span><a class="btlink" href="javascript:setUserName();"> [立即修改]</a></p>')
    // }
    setImg();
  }, 'json');
}
function getGpuInfo() {
  $.get('/system/get_gpu_info', function (res) {
    if (!res.status || !res.data || res.data.length === 0) {
      $("#gpuChart").hide();
      return;
    }
    var info = res.data[0]; // 获取第一张显卡的数据
    if (info) {
      $("#gpuChart").show();
      var gpuUse = parseFloat(info.gpu_util || 0).toFixed(1);
      var memUse = parseFloat(info.mem_util || 0).toFixed(1);
      $("#gpu_state").html(gpuUse);
      setcolor(gpuUse, "#gpu_state", 30, 70, 90);
      var memText = info.mem_used + 'M / ' + info.mem_total + 'M';
      $("#gpu_mem").html(memText);
      var tips = (lan && lan.index && lan.index.auto_str_25 || "") + info.name + (lan && lan.index && lan.index.auto_str_26 || "") + (info.temperature || '-') + (lan && lan.index && lan.index.auto_str_27 || "") + memUse + "%";
      $('#gpuChart .mask').off('mouseenter').on('mouseenter', function () {
        layer.tips(tips, this, {
          time: 0,
          tips: [1, '#999']
        });
      }).on('mouseleave', function () {
        layer.closeAll('tips');
      });
    }
  }, 'json').fail(function () {
    $("#gpuChart").hide();
  });
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
  $.get("/system/network?t=" + new Date().getTime(), function (net) {
    console.log(net);
    $("#InterfaceSpeed").html(lan.index.interfacespeed + "： 1.0Gbps");
    $("#upSpeed").html(toSize(net.up));
    $("#downSpeed").html(toSize(net.down));
    $("#downAll").html(toSize(net.downTotal));
    $("#downAll").attr('title', lan.index.package + ':' + net.downPackets);
    $("#upAll").html(toSize(net.upTotal));
    $("#upAll").attr('title', lan.index.package + ':' + net.upPackets);
    $("#core").html(net.cpu[1] + " " + lan.index.cpu_core);
    $("#state").html(parseFloat(net.cpu[0]).toFixed(1));
    setcolor(net.cpu[0], "#state", 30, 70, 90);
    setCookie("upNet", net.up);
    setCookie("downNet", net.down);

    // 自动更新左侧与顶部的排队任务总数，完成首页接口合并
    if (typeof net.task_count !== 'undefined') {
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
  }, 'json');
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
  function ts(m) {
    return m < 10 ? '0' + m : m;
  }
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
    if (getCookie("upNet") > getCookie("downNet")) {
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
    var time = new Date().getTime();
    xData.push(format(time - i * 3 * 1000));
    yData.push(0);
    zData.push(0);
  }
  // 指定图表的配置项和数据
  var option = {
    title: {
      text: lan && lan.index && lan.index.auto_str_28 || "",
      left: 'center',
      textStyle: {
        color: '#888888',
        fontStyle: 'normal',
        fontFamily: lan && lan.index && lan.index.auto_str_29 || "",
        fontSize: 16
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
      name: (lan && lan.index && lan.index.auto_str_30 || "") + default_unit,
      splitLine: {
        lineStyle: {
          color: "#eee"
        }
      },
      axisLine: {
        lineStyle: {
          color: "#666"
        }
      }
    },
    series: [{
      name: lan && lan.index && lan.index.auto_str_31 || "",
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
    }, {
      name: lan && lan.index && lan.index.auto_str_32 || "",
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
            color: 'rgba(30, 144, 255,0.5)'
          }, {
            offset: 1,
            color: 'rgba(30, 144, 255,0.8)'
          }], false)
        }
      },
      itemStyle: {
        normal: {
          color: '#52a9ff'
        }
      },
      lineStyle: {
        normal: {
          width: 1
        }
      }
    }]
  };
  var echartsNetImg = echarts.init(document.getElementById('netImg'));
  window.updateNetChart = function () {
    addData(true);
    echartsNetImg.setOption({
      yAxis: {
        name: (lan && lan.index && lan.index.auto_str_33 || "") + default_unit,
        splitLine: {
          lineStyle: {
            color: "#eee"
          }
        },
        axisLine: {
          lineStyle: {
            color: "#666"
          }
        }
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
  setInterval(function () {
    if (document.visibilityState !== 'visible') {
      return; // 网页切入后台，自动暂停高频轮询以节省能耗与带宽
    }
    getNet();
  }, 3000);

  // 使用刚指定的配置项和数据显示图表。
  echartsNetImg.setOption(option);
  window.addEventListener("resize", function () {
    echartsNetImg.resize();
  });
}
var setImgTimer = null;
function setImg() {
  if (setImgTimer) clearTimeout(setImgTimer);
  setImgTimer = setTimeout(function () {
    $('.circle').each(function (index, el) {
      var num = $(this).find('span').text() * 3.6;
      if (num <= 180) {
        $(this).find('.left').css('transform', "rotate(0deg)");
        $(this).find('.right').css('transform', "rotate(" + num + "deg)");
      } else {
        $(this).find('.right').css('transform', "rotate(180deg)");
        $(this).find('.left').css('transform', "rotate(" + (num - 180) + "deg)");
      }
      ;
    });
    $('.diskbox .mask').off().on('mouseenter', function () {
      layer.closeAll('tips');
      var that = this;
      var conterError = $(this).attr("data");
      layer.tips(conterError, that, {
        time: 0,
        tips: [1, '#999']
      });
    }).on('mouseleave', function () {
      layer.closeAll('tips');
    });
  }, 100);
}

// 检查更新
setTimeout(function () {
  $.get('/system/update_server?type=check', function (rdata) {
    if (rdata.status == false) return;
    if (rdata.data != undefined) {
      $("#toUpdate").html(lan && lan.index && lan.index.auto_str_34 || "");
      $('#toUpdate a').html(lan && lan.index && lan.index.auto_str_35 || "");
      $('#toUpdate a').css("position", "relative");
      return;
    }
  }, 'json').fail(function () {});
}, 3000);

//检查更新
function checkUpdate() {
  var loadT = layer.msg(lan.index.update_get, {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.get('/system/update_server?type=check', function (rdata) {
    layer.close(loadT);
    if (rdata.data == 'download') {
      updateStatus();
      return;
    }
    if (rdata.status === false) {
      layer.confirm(rdata.msg, {
        title: lan.index.update_check,
        icon: 1,
        closeBtn: 1,
        btn: [lan.public.know, lan.public.close]
      });
      return;
    }
    layer.msg(rdata.msg, {
      icon: 1
    });
    if (rdata.data != undefined) updateMsg();
  }, 'json');
}
function updateMsg() {
  var loadT = layer.msg(lan && lan.index && lan.index.auto_str_36 || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.get('/system/update_server?type=info', function (rdata) {
    if (rdata.data == 'download') {
      layer.close(loadT);
      updateStatus();
      return;
    }
    var v = rdata.data.version;
    var isTest = v.split('.').length > 3;
    var tagHtml = isTest ? lan && lan.index && lan.index.auto_str_37 || "" : lan && lan.index && lan.index.auto_str_38 || "";
    var titleHtml = '<div style="display: flex; align-items: center; height: 100%;">' + tagHtml + (lan && lan.index && lan.index.auto_str_39 || "") + v + ']</span></div>';
    var parseContent = function () {
      try {
        return marked.parse(rdata.data.content);
      } catch (e) {
        return rdata.data.content.replace(/\n/g, '<br/>');
      }
    };
    var showIt = function (htmlContent) {
      layer.close(loadT);
      showUpdateUI(v, titleHtml, htmlContent, rdata.data.speed_name);
    };
    if (typeof marked !== 'undefined') {
      showIt(parseContent());
    } else {
      loadScript(staticUrl('/static/js/marked.min.js')).then(function () {
        showIt(parseContent());
      }).catch(function () {
        layer.close(loadT);
        showUpdateUI(v, titleHtml, rdata.data.content.replace(/\n/g, '<br/>'), rdata.data.speed_name);
      });
    }
  }, 'json').fail(function () {
    layer.close(loadT);
    layer.msg(lan && lan.index && lan.index.auto_str_40 || "", {
      icon: 2
    });
  });
}
function showUpdateUI(version, title, content, speedName) {
  layer.open({
    type: 1,
    title: title,
    area: '650px',
    shadeClose: false,
    closeBtn: 1,
    content: '<style>' + '  .update-markdown-wrapper .markdown-body ul, .update-markdown-wrapper .markdown-body ol {' + '      padding-left: 1.2em !important;' + '      margin-bottom: 12px;' + '  }' + '  .update-markdown-wrapper .markdown-body li {' + '      margin-top: 6px;' + '  }' + '  .update-markdown-wrapper .markdown-body p {' + '      margin-bottom: 12px;' + '  }' + '  .update-markdown-wrapper .markdown-body h3, .update-markdown-wrapper .markdown-body h4 {' + '      margin-top: 16px;' + '      margin-bottom: 12px;' + '  }' + '</style>' + '<div class="setchmod bt-form pd20 pb70 update-markdown-wrapper" style="background: #fcfcfc;">' + (content ? '<div class="markdown-body" style="padding: 15px 20px; line-height: 1.6; max-height: 400px; overflow-y: auto; margin-bottom: 20px; background: rgba(255, 255, 255, 0.8); border-radius: 8px; backdrop-filter: blur(10px); box-shadow: 0 4px 15px rgba(0, 0, 0, 0.03); border: 1px solid rgba(0,0,0,0.03);">' + content + '</div>' : '') + '<div class="update-progress-group" style="padding: 15px 20px; background: #fff; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.02); border: 1px solid rgba(0,0,0,0.04);">' + '    <div style="margin-bottom: 12px;">' + (lan && lan.index && lan.index.auto_str_41 || "") + '        <div style="height: 6px; background: #f0f2f5; border-radius: 6px; overflow: hidden; box-shadow: inset 0 1px 2px rgba(0,0,0,0.02);"><div id="download-bar" class="bt-progress-bar" style="width: 0%; height: 100%; position: relative; background: linear-gradient(90deg, #42d392, #20a53a); border-radius: 6px; transition: width 0.4s ease, background 0.4s ease;"></div></div>' + '    </div>' + '    <div style="margin-bottom: 12px;">' + (lan && lan.index && lan.index.auto_str_42 || "") + '        <div style="height: 6px; background: #f0f2f5; border-radius: 6px; overflow: hidden; box-shadow: inset 0 1px 2px rgba(0,0,0,0.02);"><div id="backup-bar" class="bt-progress-bar" style="width: 0%; height: 100%; position: relative; background: linear-gradient(90deg, #42d392, #20a53a); border-radius: 6px; transition: width 0.4s ease, background 0.4s ease;"></div></div>' + '    </div>' + '    <div style="margin-bottom: 4px;">' + (lan && lan.index && lan.index.auto_str_43 || "") + '        <div style="height: 6px; background: #f0f2f5; border-radius: 6px; overflow: hidden; box-shadow: inset 0 1px 2px rgba(0,0,0,0.02);"><div id="install-bar" class="bt-progress-bar" style="width: 0%; height: 100%; position: relative; background: linear-gradient(90deg, #42d392, #20a53a); border-radius: 6px; transition: width 0.4s ease, background 0.4s ease;"></div></div>' + '    </div>' + '</div>' + '<div class="bt-form-submit-btn" style="margin-top: 20px;">' + (lan && lan.index && lan.index.auto_str_44 || "") + '<button type="button" id="start-update-btn" class="btn btn-success btn-sm btn-title" style="border-radius:6px; padding: 6px 18px; margin-left: 10px; font-weight: 500; background-color: #20a53a; border-color: #20a53a; transition: all 0.2s;" onclick="executeSteps(\'' + version + (lan && lan.index && lan.index.auto_str_45 || "") + (lan && lan.index && lan.index.auto_str_46 || "") + '</div>' + '</div>',
    success: function () {
      var bracket = $("#download-tip-bracket");
      bracket.text(lan && lan.index && lan.index.auto_str_47 || "");
    }
  });
}
function executeSteps(version) {
  $("#start-update-btn").attr("disabled", true).addClass("disabled").text(lan && lan.index && lan.index.auto_str_48 || "");
  $(".layui-layer-close").hide(); // 过程中禁止手动关闭

  updateStep('download', version, '#download-bar', '#download-percent', function () {
    updateStep('backup', version, '#backup-bar', '#backup-percent', function () {
      updateStep('install', version, '#install-bar', '#install-percent', function () {
        $("#start-update-btn").hide();
        $("#hard-refresh-btn").show().removeClass("btn-default").addClass("btn-success");
        $(".layui-layer-close").show();
        layer.msg(lan && lan.index && lan.index.auto_str_49 || "", {
          icon: 1,
          time: 5000
        });
      });
    });
  });
}
function hardRefreshWithCountdown() {
  var count = 10;
  var msgBox = layer.msg((lan && lan.index && lan.index.auto_str_50 || "") + count + (lan && lan.index && lan.index.auto_str_51 || ""), {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  var timer = setInterval(function () {
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
  $(textId).text(lan && lan.index && lan.index.auto_str_52 || "");
  var intervalId = null;
  if (step == 'download') {
    $(barId).css("width", "0%");
    var startTime = new Date().getTime();
    var tenMinutes = 10 * 60 * 1000;
    var twentyMinutes = 20 * 60 * 1000;
    var bracket = $("#download-tip-bracket");
    var nodeName = lan && lan.index && lan.index.auto_str_53 || "";
    bracket.text((lan && lan.index && lan.index.auto_str_54 || "") + nodeName + (lan && lan.index && lan.index.auto_str_55 || ""));
    setTimeout(function () {
      $.get('/system/update_server?type=info', function (rdata) {
        if (rdata && rdata.data && rdata.data.speed_name) {
          if (rdata.data.speed_name === 'Direct') {
            nodeName = 'github.com';
          } else {
            nodeName = rdata.data.speed_name;
          }
        } else {
          nodeName = 'github.com';
        }
      }, 'json');
    }, 500);
    intervalId = setInterval(function () {
      var now = new Date().getTime();
      var elapsed = now - startTime;

      // 请求全局网速更新面板UI
      $.get('/system/network', function (netData) {
        if (netData && netData.network && netData.network.ALL && netData.network.ALL.down) {
          var speed = (netData.network.ALL.down / 1048576).toFixed(2);
          bracket.text((lan && lan.index && lan.index.auto_str_56 || "") + nodeName + (lan && lan.index && lan.index.auto_str_57 || "") + speed + " mbps）");
        }
      }, 'json');
      if (elapsed >= twentyMinutes) {
        clearInterval(intervalId);
        $(textId).text(lan && lan.index && lan.index.auto_str_58 || "").css("color", "#ff4d4f");
        $(barId).css("background", "#ff4d4f");
        layer.alert(lan && lan.index && lan.index.auto_str_59 || "", {
          icon: 2,
          title: lan && lan.index && lan.index.auto_str_60 || ""
        }, function (index) {
          layer.close(index);
          location.reload();
        });
        return;
      }
      var progress = 0;
      if (elapsed < tenMinutes) {
        progress = elapsed / tenMinutes * 95;
      } else {
        progress = 95;
      }
      $(barId).css("width", progress.toFixed(2) + "%");
      $(textId).text(Math.floor(progress) + "%");
    }, 1000);
  } else {
    $(barId).css("width", "40%");
  }
  $.get('/system/update_server?type=update&version=' + version + '&step=' + step, function (rdata) {
    if (intervalId) clearInterval(intervalId);
    if (rdata.status) {
      $(barId).css("width", "100%");
      $(textId).text(lan && lan.index && lan.index.auto_str_61 || "").css("color", "#20a53a");
      if (callback) callback();
    } else {
      $(textId).text(lan && lan.index && lan.index.auto_str_62 || "").css("color", "#ff4d4f");
      $(barId).css("background", "#ff4d4f");
      layer.msg(rdata.msg, {
        icon: 2
      });
      $("#start-update-btn").attr("disabled", false).removeClass("disabled").text(lan && lan.index && lan.index.auto_str_63 || "");
      $(".layui-layer-close").show();
    }
  }, 'json').fail(function () {
    if (intervalId) clearInterval(intervalId);
    if (step == 'install') {
      $(barId).css("width", "100%");
      $(textId).text(lan && lan.index && lan.index.auto_str_64 || "").css("color", "#20a53a");
      if (callback) callback();
    } else {
      $(textId).text(lan && lan.index && lan.index.auto_str_65 || "").css("color", "#ff4d4f");
      $(barId).css("background", "#ff4d4f");
      layer.msg(lan && lan.index && lan.index.auto_str_66 || "", {
        icon: 2
      });
      $(".layui-layer-close").show();
    }
  });
}
function pluginIndexService(pname, pfunc, callback) {
  $.post('/plugins/run', {
    name: 'openresty',
    func: pfunc
  }, function (data) {
    if (!data.status) {
      layer.msg(data.msg, {
        icon: 0,
        time: 2000,
        shade: [0.3, '#000']
      });
      return;
    }
    if (typeof callback == 'function') {
      callback(data);
    }
  }, 'json');
}

//重启服务器
function reBoot() {
  layer.open({
    type: 1,
    title: lan && lan.index && lan.index.auto_str_67 || "",
    area: ['350px', '250px'],
    closeBtn: 1,
    shadeClose: false,
    content: lan && lan.index && lan.index.auto_str_68 || ""
  });
  $('.rebt-con a').on('click', function () {
    var type = $(this).attr('data-id');
    switch (type) {
      case 'panel':
        layer.confirm(lan && lan.index && lan.index.auto_str_69 || "", {
          title: lan && lan.index && lan.index.auto_str_70 || "",
          closeBtn: 1,
          icon: 3
        }, function () {
          var loadT = layer.load();
          $.post('/system/restart', '', function (rdata) {
            layer.close(loadT);
            var count = 10;
            var msgBox = layer.msg((lan && lan.index && lan.index.auto_str_71 || "") + count + (lan && lan.index && lan.index.auto_str_72 || ""), {
              icon: 16,
              time: 0,
              shade: [0.3, '#000']
            });
            var timer = setInterval(function () {
              count--;
              if (count <= 0) {
                clearInterval(timer);
                layer.close(msgBox);
                window.location.href = window.location.pathname + '?t=' + new Date().getTime();
              } else {
                $('#restart-countdown').text(count);
              }
            }, 1000);
          }, 'json');
        });
        break;
      case 'repair':
        layer.confirm(lan && lan.index && lan.index.auto_str_73 || "", {
          title: lan && lan.index && lan.index.auto_str_74 || "",
          closeBtn: 1,
          icon: 3
        }, function () {
          var version = $("#version").text();
          showUpdateUI(version, (lan && lan.index && lan.index.auto_str_75 || "") + version + ']</span>', lan && lan.index && lan.index.auto_str_76 || "");
        });
        break;
      case 'server':
        var rebootbox = layer.open({
          type: 1,
          title: lan && lan.index && lan.index.auto_str_77 || "",
          area: ['500px', '280px'],
          closeBtn: 1,
          shadeClose: false,
          content: lan && lan.index && lan.index.auto_str_78 || ""
        });
        setTimeout(function () {
          $(".btn-reboot").on('click', function () {
            rebootbox.close();
          });
          $(".WSafeRestart").on('click', function () {
            var body = '<div class="SafeRestartCode pd15" style="line-height:26px"></div>';
            $(".bt-window-restart").html(body);
            $(".SafeRestartCode").append(lan && lan.index && lan.index.auto_str_79 || "");
            pluginIndexService('openresty', 'stop', function (r1) {
              $(".SafeRestartCode p").addClass('c9');
              $(".SafeRestartCode").append(lan && lan.index && lan.index.auto_str_80 || "");
              pluginIndexService('mysql', 'stop', function (r2) {
                $(".SafeRestartCode p").addClass('c9');
                $(".SafeRestartCode").append(lan && lan.index && lan.index.auto_str_81 || "");
                $.post('/system/restart_server', '', function (rdata) {
                  $(".SafeRestartCode p").addClass('c9');
                  $(".SafeRestartCode").append(lan && lan.index && lan.index.auto_str_82 || "");
                  var sEver = setInterval(function () {
                    $.get("/system/system_total", function (info) {
                      clearInterval(sEver);
                      $(".SafeRestartCode p").addClass('c9');
                      $(".SafeRestartCode").append(lan && lan.index && lan.index.auto_str_83 || "");
                      setTimeout(function () {
                        layer.closeAll();
                      }, 3000);
                    });
                  }, 3000);
                });
              });
            });
          });
        }, 100);
        break;
    }
  });
}

//修复面板
function repPanel() {
  layer.confirm(lan.index.rep_panel_msg, {
    title: lan.index.rep_panel_title,
    closeBtn: 1,
    icon: 3
  }, function () {
    var loadT = layer.msg(lan.index.rep_panel_the, {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.get('/system?action=RepPanel', function (rdata) {
      layer.close(loadT);
      layer.msg(lan.index.rep_panel_ok, {
        icon: 1
      });
    }).fail(function () {
      layer.close(loadT);
      layer.msg(lan.index.rep_panel_ok, {
        icon: 1
      });
    });
  });
}

//获取警告信息
function getWarning() {
  $.get('/ajax?action=GetWarning', function (wlist) {
    var num = 0;
    for (var i = 0; i < wlist.data.length; i++) {
      if (wlist.data[i].ignore_count >= wlist.data[i].ignore_limit) continue;
      if (wlist.data[i].ignore_time != 0 && wlist.time - wlist.data[i].ignore_time < wlist.data[i].ignore_timeout) continue;
      var btns = '';
      for (var n = 0; n < wlist.data[i].btns.length; n++) {
        if (wlist.data[i].btns[n].type == 'javascript') {
          btns += '<a href="javascript:WarningTo(\'' + wlist.data[i].btns[n].url + '\',' + wlist.data[i].btns[n].reload + ');" class="' + wlist.data[i].btns[n].class + '"> ' + wlist.data[i].btns[n].title + '</a>';
        } else {
          btns += '<a href="' + wlist.data[i].btns[n].url + '" class="' + wlist.data[i].btns[n].class + '" target="' + wlist.data[i].btns[n].target + '"> ' + wlist.data[i].btns[n].title + '</a>';
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
  var loadT = layer.msg(lan.public.the_get, {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post(to_url, {}, function (rdata) {
    layer.close(loadT);
    layer.msg(rdata.msg, {
      icon: rdata.status ? 1 : 2
    });
    if (rdata.status && def) setTimeout(function () {
      location.reload();
    }, 1000);
  }, 'json');
}
function setSafeHide() {
  setCookie('safeMsg', '1');
  $("#safeMsg").remove();
}

//查看报告
function showDanger(num, port) {
  var atxt = lan && lan.index && lan.index.auto_str_84 || "";
  if (port == "22") {
    atxt = lan && lan.index && lan.index.auto_str_85 || "";
  }
  layer.open({
    type: 1,
    area: ['720px', '410px'],
    title: lan && lan.index && lan.index.auto_str_86 || "",
    closeBtn: 1,
    shift: 5,
    content: (lan && lan.index && lan.index.auto_str_87 || "") + num + (lan && lan.index && lan.index.auto_str_88 || "") + atxt + (lan && lan.index && lan.index.auto_str_89 || "")
  });
  $(".showDanger td").css("padding", "8px");
}
function pluginInit() {
  $.post('/plugins/init', function (data) {
    if (!data.status) {
      return false;
    }
    var rdata = data.data;
    var plugin_list = '';
    for (var i = 0; i < rdata.length; i++) {
      var ver = rdata[i]['versions'];
      var select_list = '';
      if (typeof ver == 'string') {
        select_list = '<option value="' + ver + '">' + rdata[i]['title'] + ' - ' + ver + '</option>';
      } else {
        for (var vi = 0; vi < ver.length; vi++) {
          if (ver[vi] == rdata[i]['default_ver']) {
            select_list += '<option value="' + ver[vi] + '" selected="selected">' + rdata[i]['title'] + ' - ' + ver[vi] + '</option>';
          } else {
            select_list += '<option value="' + ver[vi] + '">' + rdata[i]['title'] + ' - ' + ver[vi] + '</option>';
          }
        }
      }
      var pn_checked = '<input id="data_' + rdata[i]['name'] + '" type="checkbox" checked>';
      if (rdata[i]['name'] == 'swap') {
        var pn_checked = '<input id="data_' + rdata[i]['name'] + '" type="checkbox" disabled="disabled" checked>';
      }
      plugin_list += '<li><span class="ico"><img src="/plugins/file?name=' + rdata[i]['name'] + '&f=ico.png"></span>\
            <span class="name">\
                <select id="select_' + rdata[i]['name'] + '" class="sl-s-info">' + select_list + '</select>\
            </span>\
            <span class="pull-right">' + pn_checked + '</span></li>';
    }
    layer.open({
      type: 1,
      title: lan && lan.index && lan.index.auto_str_90 || "",
      area: ["380px", "auto"],
      skin: 'layui-layer-modern',
      closeBtn: 1,
      shadeClose: false,
      content: (lan && lan.index && lan.index.auto_str_91 || "") + plugin_list + (lan && lan.index && lan.index.auto_str_92 || ""),
      success: function (l, index) {
        $('.rec-box-con .onekey').on('click', function () {
          var _this = $(this);
          if (_this.hasClass('disabled')) return;
          _this.addClass('disabled');
          var post_data = [];
          for (var i = 0; i < rdata.length; i++) {
            var key_ver = '#select_' + rdata[i]['name'];
            var key_checked = '#data_' + rdata[i]['name'];
            var val_checked = $(key_checked).prop("checked");
            if (val_checked) {
              var tmp = {};
              var val_key = $(key_ver).val();
              tmp['version'] = val_key;
              tmp['name'] = rdata[i]['name'];
              post_data.push(tmp);
            }
          }
          $.post('/plugins/init_install', 'list=' + JSON.stringify(post_data), function (data) {
            showMsg(data.msg, function () {
              if (data.status) {
                layer.closeAll();
                messageBox();
              } else {
                $('.rec-box-con .onekey').removeClass('disabled');
              }
            }, {
              icon: data.status ? 1 : 2
            }, 2000);
          }, 'json').fail(function () {
            $('.rec-box-con .onekey').removeClass('disabled');
          });
        });
      },
      cancel: function () {
        layer.confirm(lan && lan.index && lan.index.auto_str_93 || "", {
          btn: [lan && lan.index && lan.index.auto_str_94 || "", lan && lan.index && lan.index.auto_str_95 || ""],
          title: lan && lan.index && lan.index.auto_str_96 || ""
        }, function () {
          $.post('/files/create_dir', 'path=/www/server/php', function (rdata) {
            layer.closeAll();
          }, 'json');
        });
      }
    });
  }, 'json');
}
function loadKeyDataCount() {
  var plist = ['mysql', 'gogs', 'gitea', 'op_waf', 'fail2ban'];
  var post_data = [];
  for (var i = 0; i < plist.length; i++) {
    post_data.push({
      name: plist[i],
      func: 'get_total_statistics'
    });
  }
  $.post('/plugins/run_batch', {
    list: JSON.stringify(post_data)
  }, function (data) {
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
      } catch (e) {
        continue;
      }
      if (!rdata || !rdata['status']) continue;
      var show_name = pname;
      if (pname == 'op_waf') {
        show_name = lan && lan.index && lan.index.auto_str_97 || "";
      } else if (pname == 'mysql') {
        show_name = 'MySQL';
      } else if (pname == 'gogs') {
        show_name = 'Gogs';
      } else if (pname == 'gitea') {
        show_name = 'Gitea';
      } else if (pname == 'fail2ban') {
        show_name = lan && lan.index && lan.index.auto_str_98 || "";
      }
      var onclick_str = 'softMain(\'' + pname + '\',\'' + show_name + '\',\'' + rdata['data']['ver'] + '\')';
      if (pname == 'mysql') {
        onclick_str = 'window.DEFAULT_ACTIVE_TAB = \'dbList\'; ' + onclick_str;
      }
      if (pname == 'op_waf') {
        onclick_str = 'window.DEFAULT_ACTIVE_TAB = \'wafIndex\'; ' + onclick_str;
      }
      var html = '<li class="sys-li-box col-xs-3 col-sm-3 col-md-3 col-lg-3">\
                    <p class="name f15 c9">' + show_name + '</p>\
                    <div class="val"><a class="btlink" onclick="' + onclick_str + '">' + rdata['data']['count'] + '</a></div>\
                </li>';
      $('#index_overview').append(html);
    }
  }, 'json');
}
$(function () {
  $(".mem-release").on('mouseenter', function () {
    $(this).addClass("shine_green");
    if (!$(this).hasClass("mem-action")) {
      $(this).find(".mem-re-min").hide();
      $(this).find(".mask").css({
        "color": "#d2edd8"
      });
      $(this).find(".mem-re-con").css({
        "display": "block"
      });
      $(this).find(".mem-re-con").animate({
        "top": "0",
        opacity: 1
      });
      $("#memory").text(lan && lan.index && lan.index.auto_str_99 || "");
    }
  }).on('mouseleave', function () {
    $(this).removeClass("shine_green");
    $(this).find(".mask").css({
      "color": "#20a53a"
    });
    $(this).find(".mem-re-con").css({
      "top": "15px",
      opacity: 1,
      "display": "none"
    });
    $("#memory").text(getCookie("mem-before"));
    $(this).find(".mem-re-min").hide();
  }).on('click', function () {
    $(this).find(".mem-re-min").hide();
    if (!$(this).hasClass("mem-action")) {
      reMemory();
      var btlen = $(".mem-release").find(".mask span").text();
      $(this).addClass("mem-action");
      $(this).find(".mask").css({
        "color": "#20a53a"
      });
      $(this).find(".mem-re-con").animate({
        "top": "-400px",
        opacity: 0
      });
      $(this).find(".pie_right .right").css({
        "transform": "rotate(3deg)"
      });
      for (var i = 0; i < btlen; i++) {
        setTimeout("rocket(" + btlen + "," + i + ")", i * 30);
      }
    }
  });
  $("select[name='network-io'],select[name='disk-io']").on('change', function () {
    var key = $(this).val(),
      type = $(this).attr('name');
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
  $('#index_overview').on('click', '.sys-li-box', function (e) {
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
  common: {
    ts: function (m) {
      return m < 10 ? '0' + m : m;
    },
    format: function (sjc) {
      var time = new Date(sjc);
      var h = time.getHours();
      var mm = time.getMinutes();
      var s = time.getSeconds();
      return h + ':' + mm + ':' + s;
    },
    getTime: function () {
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
  },
  net: {
    table: null,
    data: {
      xData: [],
      yData: [],
      zData: []
    },
    default_unit: 'KB/s',
    init_select: false,
    init: function () {
      for (var i = 8; i >= 0; i--) {
        var time = new Date().getTime();
        index.net.data.xData.push(index.common.format(time - i * 3 * 1000));
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
    render: function () {
      index.net.table.setOption({
        yAxis: {
          name: (lan && lan.index && lan.index.auto_str_100 || "") + index.net.default_unit,
          splitLine: {
            lineStyle: {
              color: "#eee"
            }
          },
          axisLine: {
            lineStyle: {
              color: "#666"
            }
          }
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
    defaultOption: function () {
      var option = {
        title: {
          text: "",
          left: 'center',
          textStyle: {
            color: '#888888',
            fontStyle: 'normal',
            fontFamily: lan && lan.index && lan.index.auto_str_101 || "",
            fontSize: 16
          }
        },
        tooltip: {
          trigger: 'axis',
          formatter: function (config) {
            var _config = config,
              _tips = (lan && lan.index && lan.index.auto_str_102 || "") + _config[0].axisValue + "<br />";
            for (var i = 0; i < config.length; i++) {
              if (typeof config[i].data == "undefined") {
                return false;
              }
              _tips += '<span style="display: inline-block;width: 10px;height: 10px;border-radius: 50%;background: ' + config[i].color + ';"></span>&nbsp;&nbsp;<span>' + config[i].seriesName + '：' + config[i].data + ' ' + index.net.default_unit + '</span><br />';
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
          name: (lan && lan.index && lan.index.auto_str_103 || "") + index.net.default_unit,
          splitLine: {
            lineStyle: {
              color: "#eee"
            }
          },
          axisLine: {
            lineStyle: {
              color: "#666"
            }
          }
        },
        series: [{
          name: lan && lan.index && lan.index.auto_str_104 || "",
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
        }, {
          name: lan && lan.index && lan.index.auto_str_105 || "",
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
                color: 'rgba(30, 144, 255,0.5)'
              }, {
                offset: 1,
                color: 'rgba(30, 144, 255,0.8)'
              }], false)
            }
          },
          itemStyle: {
            normal: {
              color: '#52a9ff'
            }
          },
          lineStyle: {
            normal: {
              width: 1
            }
          }
        }]
      };
      return option;
    },
    add: function (up, down) {
      var _net = this;
      var limit = 8;
      var d = new Date();
      if (_net.data.xData.length >= limit) _net.data.xData.splice(0, 1);
      if (_net.data.yData.length >= limit) _net.data.yData.splice(0, 1);
      if (_net.data.zData.length >= limit) _net.data.zData.splice(0, 1);
      _net.data.xData.push(d.getHours() + ':' + d.getMinutes() + ':' + d.getSeconds());
      if (up > down) {
        var upTmp = toSizePos(up);
        var upTmpSize = upTmp['name'].split(' ')[0];
        index.net.default_unit = upTmp['name'].split(' ')[1] + '/s';
        var downTmpSize = toSizePos(down, upTmp['pos'])['name'].split(' ')[0];
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
    renderSelect: function (net) {
      // console.log(net);
      if (!index.net.init_select) {
        var option = '';
        var network = net.network;
        var network_io_key = getCookie('network_io_key');
        for (var name in network) {
          if (name == 'ALL') {
            option += '<option value="' + name + (lan && lan.index && lan.index.auto_str_106 || "");
          } else if (network_io_key == name) {
            option += '<option value="' + name + '" selected>' + name + '</option>';
          } else {
            option += '<option value="' + name + '">' + name + '</option>';
          }
        }
        $('select[name="network-io"]').html(option);
        index.net.init_select = true;
      }
    }
  },
  iostat: {
    table: null,
    data: {
      xData: [],
      yData: [],
      zData: [],
      tipsData: []
    },
    init_select: false,
    default_unit: 'MB/s',
    init: function () {
      for (var i = 8; i >= 0; i--) {
        var time = new Date().getTime();
        index.iostat.data.xData.push(index.common.format(time - i * 3 * 1000));
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
    render: function () {
      index.iostat.table.setOption({
        tooltip: {
          trigger: 'axis',
          formatter: function (config) {
            var _config = config,
              _tips = (lan && lan.index && lan.index.auto_str_107 || "") + _config[0].axisValue + "<br />",
              options = {
                read_bytes: lan && lan.index && lan.index.auto_str_108 || "",
                read_count: lan && lan.index && lan.index.auto_str_109 || "",
                read_merged_count: lan && lan.index && lan.index.auto_str_110 || "",
                read_time: lan && lan.index && lan.index.auto_str_111 || "",
                write_bytes: lan && lan.index && lan.index.auto_str_112 || "",
                write_count: lan && lan.index && lan.index.auto_str_113 || "",
                write_merged_count: lan && lan.index && lan.index.auto_str_114 || "",
                write_time: lan && lan.index && lan.index.auto_str_115 || ""
              },
              data = index.iostat.data.tipsData[config[0].dataIndex],
              list = ['read_count', 'write_count', 'read_merged_count', 'write_merged_count', 'read_time', 'write_time'];
            for (var i = 0; i < config.length; i++) {
              if (typeof config[i].data == "undefined") {
                return false;
              }
              _tips += '<span style="display: inline-block;width: 10px;height: 10px;border-radius: 50%;background: ' + config[i].color + ';"></span>&nbsp;&nbsp;<span>' + config[i].seriesName + '：' + config[i].data + ' MB/s' + '</span><br />';
            }
            $.each(list, function (index, item) {
              if (typeof data[item] != 'undefined') {
                _tips += '<span style="display: inline-block;width: 10px;height: 10px;"></span>&nbsp;&nbsp;<span style="' + (item.indexOf('time') > -1 ? 'color:' + (data[item] > 100 && data[item] < 1000 ? '#ff9900' : data[item] >= 1000 ? 'red' : '#20a53a') : '') + '">' + options[item] + '：' + data[item] + (item.indexOf('time') > -1 ? ' ms' : lan && lan.index && lan.index.auto_str_116 || "") + '</span><br />';
              }
            });
            return _tips;
          }
        },
        yAxis: {
          name: (lan && lan.index && lan.index.auto_str_117 || "") + index.iostat.default_unit,
          splitLine: {
            lineStyle: {
              color: "#eee"
            }
          },
          axisLine: {
            lineStyle: {
              color: "#666"
            }
          }
        },
        xAxis: {
          data: index.iostat.data.xData
        },
        series: [{
          name: lan && lan.index && lan.index.auto_str_118 || "",
          data: index.iostat.data.yData
        }, {
          name: lan && lan.index && lan.index.auto_str_119 || "",
          data: index.iostat.data.zData
        }]
      });
    },
    defaultOption: function () {
      var option = {
        title: {
          text: "",
          left: 'center',
          textStyle: {
            color: '#888888',
            fontStyle: 'normal',
            fontFamily: lan && lan.index && lan.index.auto_str_120 || "",
            fontSize: 16
          }
        },
        tooltip: {
          trigger: 'axis'
        },
        legend: {
          data: [lan && lan.index && lan.index.auto_str_121 || "", lan && lan.index && lan.index.auto_str_122 || ""],
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
          name: (lan && lan.index && lan.index.auto_str_123 || "") + index.iostat.default_unit,
          splitLine: {
            lineStyle: {
              color: "#eee"
            }
          },
          axisLine: {
            lineStyle: {
              color: "#666"
            }
          }
        },
        series: [{
          name: lan && lan.index && lan.index.auto_str_124 || "",
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
              width: 1
            }
          }
        }, {
          name: lan && lan.index && lan.index.auto_str_125 || "",
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
              width: 1
            }
          }
        }]
      };
      return option;
    },
    renderSelect: function (data) {
      if (!index.iostat.init_select) {
        var option = '';
        var iostat = data.iostat;
        var disk_io_key = getCookie('disk_io_key');
        for (var name in iostat) {
          if (name == 'ALL') {
            option += '<option value="' + name + (lan && lan.index && lan.index.auto_str_126 || "");
          } else if (disk_io_key == name) {
            option += '<option value="' + name + '" selected>' + name + '</option>';
          } else {
            option += '<option value="' + name + '">' + name + '</option>';
          }
        }
        $('select[name="disk-io"]').html(option);
        index.iostat.init_select = true;
      }
    },
    add: function (read, write, data) {
      var _iostat = this;
      var limit = 8;
      var d = new Date();
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
    }
  },
  getData: function () {
    $.get("/system/network", function (net) {
      //网络IO
      var network_io_key = getCookie('network_io_key');
      var network_data = net.network;
      var network_select = network_data['ALL'];
      if (network_io_key && network_io_key != '') {
        network_select = network_data[network_io_key];
      }
      index.net.add(network_select.up, network_select.down);
      index.net.render();
      index.net.renderSelect(net);
      $("#upSpeed").html(toSize(network_select.up));
      $("#downSpeed").html(toSize(network_select.down));
      $("#downAll").html(toSize(network_select.downTotal));
      $("#downAll").attr('title', (lan && lan.index && lan.index.auto_str_127 || "") + network_select.downPackets);
      $("#upAll").html(toSize(network_select.upTotal));
      $("#upAll").attr('title', (lan && lan.index && lan.index.auto_str_128 || "") + network_select.upPackets);

      //磁盘IO
      var disk_io_key = getCookie('disk_io_key');
      var iostat_data = net.iostat;
      var iostat_select = iostat_data['ALL'];
      if (disk_io_key && disk_io_key != '') {
        iostat_select = iostat_data[disk_io_key];
      }
      index.iostat.add(iostat_select.read_bytes, iostat_select.write_bytes, iostat_select);
      index.iostat.render();
      index.iostat.renderSelect(net);
      $("#readBytes").html(toSize(iostat_select.read_bytes));
      $("#writeBytes").html(toSize(iostat_select.write_bytes));
      $("#diskIops").html(iostat_select.read_count + ":" + iostat_select.write_count + (lan && lan.index && lan.index.auto_str_129 || ""));
      $("#diskTime").html(iostat_select.read_time + ":" + iostat_select.write_time + " ms");
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
      if ($("#gpuChart").length > 0) {
        getGpuInfo();
      }
    }, 'json');
  },
  task: function () {
    // index.getData();
    setInterval(function () {
      index.getData();
    }, 3000);
  },
  init: function () {
    index.net.init();
    index.iostat.init();
    index.task();
  }
};
function showSystemDetails() {
  var loadT = layer.msg(lan && lan.index && lan.index.auto_str_130 || "", {
    icon: 16,
    time: 0,
    shade: 0.3
  });
  $.get('/system/get_system_details', function (res) {
    layer.close(loadT);
    if (!res.status) {
      layer.msg((lan && lan.index && lan.index.auto_str_131 || "") + res.msg, {
        icon: 2
      });
      return;
    }
    var data = res.data;
    var css = '<style>' + '.glass-layer { background: rgba(255,255,255,0.65) !important; backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px); border: 1px solid rgba(255,255,255,0.8) !important; box-shadow: 0 10px 30px rgba(0,0,0,0.1) !important; border-radius: 12px !important; will-change: transform, opacity; transform: translateZ(0); }' + '.glass-layer .layui-layer-title { background: transparent !important; border-bottom: 1px solid rgba(0,0,0,0.08) !important; font-weight: bold; color: #333; font-size:15px; border-radius: 12px 12px 0 0 !important; }' + '.glass-card { background: rgba(255,255,255,0.5); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.7); border-radius: 10px; padding: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); height: 100%; transition: all 0.3s ease; will-change: transform, box-shadow; transform: translateZ(0); }' + '.glass-card:hover { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0,0,0,0.08); background: rgba(255,255,255,0.7); }' + '.glass-card h4 { margin-top: 0; margin-bottom: 12px; color: #222; font-size: 15px; font-weight: bold; display: flex; align-items: center; }' + '.glass-card table td { border: none !important; color: #555; padding: 5px 0 !important; font-size: 13px; }' + '.glass-card table td:last-child { text-align: right; font-weight: 500; color: #111; }' + '.glass-card table tr:not(:last-child) td { border-bottom: 1px dashed rgba(0,0,0,0.06) !important; }' + '.glass-progress-bg { height: 6px; background: rgba(0,0,0,0.08); border-radius: 3px; margin: 5px 0; overflow: hidden; box-shadow: inset 0 1px 2px rgba(0,0,0,0.05); }' + '.glass-progress-bar { height: 100%; border-radius: 3px; transition: width 0.6s ease; }' + '</style>';
    var renderProgress = function (percent, type) {
      var color = '#20a53a';
      if (percent > 80) color = '#e74c3c';else if (percent > 60) color = '#f39c12';
      return '<div class="glass-progress-bg">' + '<div class="glass-progress-bar" style="width: ' + percent + '%; background-color: ' + color + ';"></div>' + '</div>';
    };
    var renderFlags = function (flags) {
      if (!flags) flags = {
        'AES': false,
        'VMX': false,
        'AVX2': false,
        'AVX512': false
      };
      var getDesc = function (k) {
        if (k === 'AES') return lan && lan.index && lan.index.auto_str_132 || "";
        if (k === 'VMX') return lan && lan.index && lan.index.auto_str_133 || "";
        if (k === 'AVX2') return lan && lan.index && lan.index.auto_str_134 || "";
        if (k === 'AVX512') return lan && lan.index && lan.index.auto_str_135 || "";
        return k;
      };
      var html = '';
      for (var key in flags) {
        var desc = getDesc(key);
        if (flags[key]) {
          html += (lan && lan.index && lan.index.auto_str_136 || "") + desc + '">' + key + '</span>';
        } else {
          html += (lan && lan.index && lan.index.auto_str_137 || "") + desc + '">' + key + '</span>';
        }
      }
      return html;
    };
    var renderTcpCc = function (activeCc) {
      if (!activeCc || activeCc === (lan && lan.index && lan.index.auto_str_138 || "") || activeCc === "X") return "-";
      var algorithms = ['BBR', 'Cubic', 'Reno'];
      var getDesc = function (a) {
        if (a === 'BBR') return lan && lan.index && lan.index.auto_str_139 || "";
        if (a === 'Cubic') return lan && lan.index && lan.index.auto_str_140 || "";
        if (a === 'Reno') return lan && lan.index && lan.index.auto_str_141 || "";
        return a;
      };
      var html = '';
      var activeLower = activeCc.toLowerCase();
      var found = false;
      for (var i = 0; i < algorithms.length; i++) {
        var algo = algorithms[i];
        var desc = getDesc(algo);
        if (algo.toLowerCase() === activeLower) {
          html += (lan && lan.index && lan.index.auto_str_142 || "") + desc + '">' + algo + '</span>';
          found = true;
        } else {
          html += (lan && lan.index && lan.index.auto_str_143 || "") + desc + '">' + algo + '</span>';
        }
      }
      if (!found) {
        html += (lan && lan.index && lan.index.auto_str_144 || "") + activeCc + '</span>';
      }
      return html;
    };
    var html = css + '<div style="padding: 15px 20px; overflow:hidden;">' + '<div class="row">' +
    // 操作系统
    '<div class="col-sm-4" style="margin-bottom:15px;">' + '<div class="glass-card">' + (lan && lan.index && lan.index.auto_str_145 || "") + '<table class="table table-condensed" style="margin-bottom:0;">' + (lan && lan.index && lan.index.auto_str_146 || "") + data.os.system + '</td></tr>' + (lan && lan.index && lan.index.auto_str_147 || "") + data.os.kernel + '</td></tr>' + (lan && lan.index && lan.index.auto_str_148 || "") + data.os.arch + '</td></tr>' + (lan && lan.index && lan.index.auto_str_149 || "") + data.os.virtualization + '</td></tr>' + '</table>' + '</div>' + '</div>' +
    // CPU
    '<div class="col-sm-4" style="margin-bottom:15px;">' + '<div class="glass-card">' + (lan && lan.index && lan.index.auto_str_150 || "") + '<table class="table table-condensed" style="margin-bottom:0;">' + (lan && lan.index && lan.index.auto_str_151 || "") + data.cpu.model + '</td></tr>' + (lan && lan.index && lan.index.auto_str_152 || "") + data.cpu.cores + (lan && lan.index && lan.index.auto_str_153 || "") + data.cpu.threads + (lan && lan.index && lan.index.auto_str_154 || "") + (lan && lan.index && lan.index.auto_str_155 || "") + data.cpu.freq + '</td></tr>' + (lan && lan.index && lan.index.auto_str_156 || "") + renderFlags(data.cpu.flags) + '</td></tr>' + '</table>' + '</div>' + '</div>' +
    // 网络与状态
    '<div class="col-sm-4" style="margin-bottom:15px;">' + '<div class="glass-card">' + (lan && lan.index && lan.index.auto_str_157 || "") + '<table class="table table-condensed" style="margin-bottom:0;">' + (lan && lan.index && lan.index.auto_str_158 || "") + (data.network.ipv4 === "X" ? "-" : data.network.ipv4) + '<br>' + (data.network.ipv6 === "X" ? "-" : data.network.ipv6.split("%")[0]) + '</td></tr>' + (lan && lan.index && lan.index.auto_str_159 || "") + data.network.isp + ' (' + data.network.location + ')</td></tr>' + (lan && lan.index && lan.index.auto_str_160 || "") + renderTcpCc(data.network.tcp_cc) + '</td></tr>' + (lan && lan.index && lan.index.auto_str_161 || "") + data.status.load + '</td></tr>' + '</table>' + '</div>' + '</div>' +
    // 内存
    '<div class="col-sm-6" style="margin-bottom:0;">' + '<div class="glass-card">' + (lan && lan.index && lan.index.auto_str_162 || "") + '<table class="table table-condensed" style="margin-bottom:0;">' + (lan && lan.index && lan.index.auto_str_163 || "") + data.memory.used + ' / ' + data.memory.total + ' (' + data.memory.percent.toFixed(1) + '%)</td></tr>' + '<tr><td colspan="2" style="padding-top:2px !important; padding-bottom:8px !important;">' + renderProgress(data.memory.percent) + '</td></tr>' + (lan && lan.index && lan.index.auto_str_164 || "") + data.memory.swap_used + ' / ' + data.memory.swap_total + ' (' + data.memory.swap_percent.toFixed(1) + '%)</td></tr>' + '<tr><td colspan="2" style="padding-top:2px !important; padding-bottom:0 !important;">' + renderProgress(data.memory.swap_percent) + '</td></tr>' + '</table>' + '</div>' + '</div>' +
    // 磁盘
    '<div class="col-sm-6" style="margin-bottom:0;">' + '<div class="glass-card">' + (lan && lan.index && lan.index.auto_str_165 || "") + '<table class="table table-condensed" style="margin-bottom:0;">' + (lan && lan.index && lan.index.auto_str_166 || "") + data.disk.used + ' / ' + data.disk.total + '</td></tr>' + '<tr><td colspan="2" style="padding-top:2px !important; padding-bottom:8px !important;">' + renderProgress(data.disk.percent) + '</td></tr>' + (lan && lan.index && lan.index.auto_str_167 || "") + data.disk.free + ' (' + (100 - data.disk.percent).toFixed(1) + '%)</td></tr>' + '<tr><td colspan="2" style="padding-top:2px !important; padding-bottom:0 !important;"><div style="height:6px; margin:5px 0;"></div></td></tr>' + '</table>' + '</div>' + '</div>' + '</div>' + '</div>';
    layer.open({
      type: 1,
      title: lan && lan.index && lan.index.auto_str_168 || "",
      area: ['900px', '500px'],
      // 增加高度，彻底消除滚动条
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
    } catch (e) {
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
  $("#sp-write-val").text(lan && lan.index && lan.index.auto_str_169 || "");
  $("#sp-write-bar").css('width', '0%');
  $("#sp-read-val").text(lan && lan.index && lan.index.auto_str_170 || "").css('color', '#94a3b8');
  $("#sp-read-bar").css('width', '0%');

  // 重置云节点状态
  $('.node-row').each(function () {
    $(this).css({
      'background': '#f8fafc',
      'border-color': '#f1f5f9'
    });
    $(this).find('.node-icon').attr('class', 'node-icon glyphicon glyphicon-time').css({
      'animation': '',
      'color': '#94a3b8'
    });
    $(this).find('.node-speed').text(lan && lan.index && lan.index.auto_str_171 || "").css('color', '#64748b');
  });
  startRealNewTest();
}

// 发起后台测速并开启轮询
function startRealNewTest() {
  var loadT = layer.msg(lan && lan.index && lan.index.auto_str_172 || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/system/speed_test', {}, function (rdata) {
    layer.close(loadT);
    if (!rdata.status) {
      layer.msg(rdata.msg, {
        icon: 2
      });
      $("#btn-re-test").show();
      return;
    }
    runLogPolling(rdata.data);
  }, 'json');
}

// 渲染测速弹窗公共方法
function renderSpeedTestModal(historyData) {
  var elegantHtml = '<div class="elegant-speed-container" style="padding: 20px; background: #fafafa; font-family: -apple-system,BlinkMacSystemFont,PingFang SC,Hiragino Sans GB,Microsoft YaHei,Helvetica Neue,Helvetica,Arial,sans-serif; color: #333; height: 100%; overflow-y: auto;">' + '    <div class="row" style="margin-left: -10px; margin-right: -10px;">' + (lan && lan.index && lan.index.auto_str_173 || "") + '        <div class="col-xs-6" style="padding-left: 10px; padding-right: 10px;">' + '            <div style="background: #fff; border-radius: 8px; border: 1px solid #eef2f6; padding: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.02); height: 195px;">' + '                <div style="font-weight: 600; color: #475569; margin-bottom: 12px; font-size: 13px; display: flex; align-items: center; gap: 6px;">' + (lan && lan.index && lan.index.auto_str_174 || "") + '                </div>' + '                <div id="sp-sys-loader" style="color: #94a3b8; text-align: center; padding-top: 40px; font-size: 12px;">' + (lan && lan.index && lan.index.auto_str_175 || "") + '                </div>' + '                <table id="sp-sys-table" class="table table-condensed" style="font-size: 12px; margin-bottom: 0; display: none; border:none;">' + (lan && lan.index && lan.index.auto_str_176 || "") + '                    <tr>' + (lan && lan.index && lan.index.auto_str_177 || "") + '                        <td id="sp-cpu" style="font-weight:500; color:#1e293b; border-top:none; padding:6px 0; line-height: 1.4;">' + '                            <div id="sp-cpu-model" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 280px;">-</div>' + '                            <div id="sp-cpu-detail" style="font-size: 11px; color: #64748b; margin-top: 2px; font-weight: normal; display: none;">-</div>' + '                        </td>' + '                    </tr>' + (lan && lan.index && lan.index.auto_str_178 || "") + (lan && lan.index && lan.index.auto_str_179 || "") + '                </table>' + '            </div>' + '        </div>' + (lan && lan.index && lan.index.auto_str_180 || "") + '        <div class="col-xs-6" style="padding-left: 10px; padding-right: 10px;">' + '            <div style="background: #fff; border-radius: 8px; border: 1px solid #eef2f6; padding: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.02); height: 195px;">' + '                <div style="font-weight: 600; color: #475569; margin-bottom: 12px; font-size: 13px; display: flex; align-items: center; gap: 6px;">' + (lan && lan.index && lan.index.auto_str_181 || "") + '                </div>' + '                <div id="sp-io-loader" style="color: #94a3b8; text-align: center; padding-top: 40px; font-size: 12px;">' + (lan && lan.index && lan.index.auto_str_182 || "") + '                </div>' + '                <div id="sp-io-container" style="display: none; padding-top: 8px;">' + '                    <div style="margin-bottom: 15px;">' + '                        <div style="display:flex; justify-content: space-between; font-size:12px; margin-bottom: 4px;">' + (lan && lan.index && lan.index.auto_str_183 || "") + (lan && lan.index && lan.index.auto_str_184 || "") + '                        </div>' + '                        <div style="height: 6px; background: #f1f5f9; border-radius: 3px; overflow: hidden;">' + '                            <div id="sp-write-bar" style="width: 0%; height: 100%; background: linear-gradient(90deg, #42d392, #20a53a); transition: width 0.5s ease;"></div>' + '                        </div>' + '                    </div>' + '                    <div>' + '                        <div style="display:flex; justify-content: space-between; font-size:12px; margin-bottom: 4px;">' + (lan && lan.index && lan.index.auto_str_185 || "") + (lan && lan.index && lan.index.auto_str_186 || "") + '                        </div>' + '                        <div style="height: 6px; background: #f1f5f9; border-radius: 3px; overflow: hidden;">' + '                            <div id="sp-read-bar" style="width: 0%; height: 100%; background: linear-gradient(90deg, #38bdf8, #0284c7); transition: width 0.5s ease;"></div>' + '                        </div>' + '                    </div>' + '                </div>' + '            </div>' + '        </div>' + '    </div>' + (lan && lan.index && lan.index.auto_str_187 || "") + '    <div style="background: #fff; border-radius: 8px; border: 1px solid #eef2f6; padding: 15px; margin-top: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.02);">' + '        <div style="font-weight: 600; color: #475569; margin-bottom: 12px; font-size: 13px; display: flex; align-items: center; justify-content: space-between;">' + '            <div style="display: flex; align-items: center; gap: 6px;">' + (lan && lan.index && lan.index.auto_str_188 || "") + '            </div>' + (lan && lan.index && lan.index.auto_str_189 || "") + '        </div>' + '        <div style="display: flex; flex-direction: column; gap: 8px;" id="sp-nodes-list">' + (lan && lan.index && lan.index.auto_str_190 || "") + '                <div style="display:flex; align-items:center; gap: 8px; font-size: 12px; font-weight: 500; color: #334155;">' + '                    <span class="node-icon glyphicon glyphicon-time" style="color:#94a3b8; font-size: 12px;"></span>' + (lan && lan.index && lan.index.auto_str_191 || "") + '                </div>' + (lan && lan.index && lan.index.auto_str_192 || "") + '            </div>' + (lan && lan.index && lan.index.auto_str_193 || "") + '                <div style="display:flex; align-items:center; gap: 8px; font-size: 12px; font-weight: 500; color: #334155;">' + '                    <span class="node-icon glyphicon glyphicon-time" style="color:#94a3b8; font-size: 12px;"></span>' + (lan && lan.index && lan.index.auto_str_194 || "") + '                </div>' + (lan && lan.index && lan.index.auto_str_195 || "") + '            </div>' + (lan && lan.index && lan.index.auto_str_196 || "") + '                <div style="display:flex; align-items:center; gap: 8px; font-size: 12px; font-weight: 500; color: #334155;">' + '                    <span class="node-icon glyphicon glyphicon-time" style="color:#94a3b8; font-size: 12px;"></span>' + (lan && lan.index && lan.index.auto_str_197 || "") + '                </div>' + (lan && lan.index && lan.index.auto_str_198 || "") + '            </div>' + (lan && lan.index && lan.index.auto_str_199 || "") + '            <div style="margin: 14px 0 10px 0; border-top: 1px dashed #e2e8f0; text-align: center; position: relative; height: 10px;">' + (lan && lan.index && lan.index.auto_str_200 || "") + '            </div>' + (lan && lan.index && lan.index.auto_str_201 || "") + '                <div style="display:flex; align-items:center; gap: 8px; font-size: 12px; font-weight: 500; color: #334155;">' + '                    <span class="node-icon glyphicon glyphicon-time" style="color:#94a3b8; font-size: 12px;"></span>' + (lan && lan.index && lan.index.auto_str_202 || "") + '                </div>' + (lan && lan.index && lan.index.auto_str_203 || "") + '            </div>' + (lan && lan.index && lan.index.auto_str_204 || "") + '                <div style="display:flex; align-items:center; gap: 8px; font-size: 12px; font-weight: 500; color: #334155;">' + '                    <span class="node-icon glyphicon glyphicon-time" style="color:#94a3b8; font-size: 12px;"></span>' + (lan && lan.index && lan.index.auto_str_205 || "") + '                </div>' + (lan && lan.index && lan.index.auto_str_206 || "") + '            </div>' + (lan && lan.index && lan.index.auto_str_207 || "") + '                <div style="display:flex; align-items:center; gap: 8px; font-size: 12px; font-weight: 500; color: #334155;">' + '                    <span class="node-icon glyphicon glyphicon-time" style="color:#94a3b8; font-size: 12px;"></span>' + (lan && lan.index && lan.index.auto_str_208 || "") + '                </div>' + (lan && lan.index && lan.index.auto_str_209 || "") + '            </div>' + (lan && lan.index && lan.index.auto_str_210 || "") + '                <div style="display:flex; align-items:center; gap: 8px; font-size: 12px; font-weight: 500; color: #334155;">' + '                    <span class="node-icon glyphicon glyphicon-time" style="color:#94a3b8; font-size: 12px;"></span>' + (lan && lan.index && lan.index.auto_str_211 || "") + '                </div>' + (lan && lan.index && lan.index.auto_str_212 || "") + '            </div>' + '        </div>' + '    </div>' + '    <pre id="speed_log_lst" style="display:none;"></pre>' + (lan && lan.index && lan.index.auto_str_213 || "") + '    <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 18px; user-select: none;">' + '        <div>' + '            <button id="btn-re-test" class="btn btn-default btn-xs" style="display: none; padding: 4px 12px; font-size: 11px; color: #475569; background: #fff; border: 1px solid #cbd5e1; border-radius: 4px; transition: all 0.2s ease; font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,0.05);" onclick="triggerSpeedReTest()">' + (lan && lan.index && lan.index.auto_str_214 || "") + '            </button>' + '        </div>' + '        <div style="display: flex; align-items: center; gap: 4px; font-size: 11px; color: #94a3b8; font-weight: 500;">' + '            <span class="glyphicon glyphicon-copyright-mark" style="font-size: 10px;"></span>' + (lan && lan.index && lan.index.auto_str_215 || "") + '        </div>' + '    </div>' + '    <style>' + '        @keyframes spin {' + '            0% { transform: rotate(0deg); }' + '            100% { transform: rotate(360deg); }' + '        }' + '    </style>' + '</div>';

  // 打开弹出层
  layer.open({
    title: lan && lan.index && lan.index.auto_str_216 || "",
    type: 1,
    closeBtn: 1,
    shade: 0.3,
    area: ["860px", "760px"],
    content: elegantHtml,
    success: function (layers, index) {
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
              cpuDetail = (lan && lan.index && lan.index.auto_str_217 || "") + detailParts[0] + (lan && lan.index && lan.index.auto_str_218 || "") + detailParts[1];
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
          var wPercent = Math.min(100, Math.round(wSpeed / 600 * 100));
          if (historyData.write_speed.indexOf('GB/s') > -1) wPercent = 100;
          $("#sp-write-bar").css('width', wPercent + '%');
        }
        if (historyData.read_speed) {
          $("#sp-read-val").text(historyData.read_speed).css('color', '#20a53a');
          var rSpeed = parseFloat(historyData.read_speed);
          var rPercent = Math.min(100, Math.round(rSpeed / 800 * 100));
          if (historyData.read_speed.indexOf('GB/s') > -1) rPercent = 100;
          $("#sp-read-bar").css('width', rPercent + '%');
        }

        // 还原云节点
        if (historyData.nodes) {
          Object.keys(historyData.nodes).forEach(function (nodeName) {
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
                $row.find('.node-speed').text(lan && lan.index && lan.index.auto_str_219 || "").css('color', '#ef4444');
                $row.css({
                  'background': 'rgba(239,68,68,0.03)',
                  'border-color': 'rgba(239,68,68,0.15)'
                });
              } else if (node.status === 'skipped') {
                $row.find('.node-speed').text(lan && lan.index && lan.index.auto_str_220 || "").css('color', '#94a3b8');
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
  var speedTimer = setInterval(function () {
    if ($("#speed_log_lst").length < 1) {
      clearInterval(speedTimer);
      return;
    }
    $.post('/files/get_last_body', {
      path: log_path,
      line: '150'
    }, function (res) {
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
                cpuDetail = (lan && lan.index && lan.index.auto_str_221 || "") + detailParts[0] + (lan && lan.index && lan.index.auto_str_222 || "") + detailParts[1];
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
          var wPercent = Math.min(100, Math.round(wSpeed / 600 * 100));
          if (data.write_speed.indexOf('GB/s') > -1) wPercent = 100;
          $("#sp-write-bar").css('width', wPercent + '%');
        }
        if (data.read_speed) {
          $("#sp-read-val").text(data.read_speed).css('color', '#20a53a');
          var rSpeed = parseFloat(data.read_speed);
          var rPercent = Math.min(100, Math.round(rSpeed / 800 * 100));
          if (data.read_speed.indexOf('GB/s') > -1) rPercent = 100;
          $("#sp-read-bar").css('width', rPercent + '%');
        } else if (data.write_speed) {
          $("#sp-read-val").text(lan && lan.index && lan.index.auto_str_223 || "").css('color', '#94a3b8');
        }

        // 节点状态渲染
        Object.keys(data.nodes).forEach(function (nodeName) {
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
              $row.find('.node-speed').text(lan && lan.index && lan.index.auto_str_224 || "").css('color', '#ef4444');
              $row.css({
                'background': 'rgba(239,68,68,0.03)',
                'border-color': 'rgba(239,68,68,0.15)'
              });
            }
          }
        });

        // 判断结束
        if (res.data.indexOf(lan && lan.index && lan.index.auto_str_225 || "") > -1 || res.data.indexOf(lan && lan.index && lan.index.auto_str_226 || "") > -1) {
          clearInterval(speedTimer);
          $('.node-row').each(function () {
            var nodeName = $(this).attr('data-node');
            var txt = $(this).find('.node-speed').text();
            if (txt === (lan && lan.index && lan.index.auto_str_227 || "") || txt === (lan && lan.index && lan.index.auto_str_228 || "")) {
              $(this).find('.node-speed').text(lan && lan.index && lan.index.auto_str_229 || "").css('color', '#94a3b8');
              $(this).find('.node-icon').attr('class', 'node-icon glyphicon glyphicon-ban-circle').css('color', '#94a3b8');
              data.nodes[nodeName] = {
                status: 'skipped',
                speed: lan && lan.index && lan.index.auto_str_230 || ""
              };
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
    if (line.indexOf(lan && lan.index && lan.index.auto_str_231 || "") > -1) {
      data.cpu = line.replace(lan && lan.index && lan.index.auto_str_232 || "", '').trim();
    } else if (line.indexOf(lan && lan.index && lan.index.auto_str_233 || "") > -1) {
      data.mem = line.replace(lan && lan.index && lan.index.auto_str_234 || "", '').trim();
    } else if (line.indexOf(lan && lan.index && lan.index.auto_str_235 || "") > -1) {
      data.disk = line.replace(lan && lan.index && lan.index.auto_str_236 || "", '').trim();
    } else if (line.indexOf(lan && lan.index && lan.index.auto_str_237 || "") > -1) {
      data.os = line.replace(lan && lan.index && lan.index.auto_str_238 || "", '').trim();
    } else if (line.indexOf(lan && lan.index && lan.index.auto_str_239 || "") > -1) {
      data.write_speed = line.replace(lan && lan.index && lan.index.auto_str_240 || "", '').trim();
    } else if (line.indexOf(lan && lan.index && lan.index.auto_str_241 || "") > -1) {
      data.read_speed = line.replace(lan && lan.index && lan.index.auto_str_242 || "", '').trim();
    } else if (line.indexOf(lan && lan.index && lan.index.auto_str_243 || "") > -1 || line.indexOf(lan && lan.index && lan.index.auto_str_244 || "") > -1) {
      var nodePart = line.replace(lan && lan.index && lan.index.auto_str_245 || "", '').replace(lan && lan.index && lan.index.auto_str_246 || "", '').trim();
      var parts = nodePart.split('...');
      if (parts.length >= 1) {
        var nodeName = parts[0].trim();
        var nodeStatus = 'running';
        var nodeSpeed = lan && lan.index && lan.index.auto_str_247 || "";
        if (parts.length >= 2 && parts[1].trim() !== '') {
          var val = parts[1].trim();
          if (val.indexOf(lan && lan.index && lan.index.auto_str_248 || "") > -1 || val.indexOf(lan && lan.index && lan.index.auto_str_249 || "") > -1) {
            nodeStatus = 'running';
            nodeSpeed = lan && lan.index && lan.index.auto_str_250 || "";
          } else if (val.indexOf(lan && lan.index && lan.index.auto_str_251 || "") > -1 || val.indexOf(lan && lan.index && lan.index.auto_str_252 || "") > -1) {
            nodeStatus = 'failed';
            nodeSpeed = lan && lan.index && lan.index.auto_str_253 || "";
          } else {
            nodeStatus = 'finished';
            nodeSpeed = val;
          }
        }
        data.nodes[nodeName] = {
          status: nodeStatus,
          speed: nodeSpeed
        };
      }
    }
  }
  return data;
}

// 获取 IP 归属地缓存（localStorage，有效期 30 天，且自动过滤未知脏缓存）
function getIpLocationFromCache(ip) {
  if (!ip) return null;
  try {
    var cacheStr = localStorage.getItem('bt_ip_loc_cache');
    if (cacheStr) {
      var cache = JSON.parse(cacheStr);
      var item = cache[ip];
      if (item && item.loc && Date.now() - (item.t || 0) < 30 * 86400000) {
        // 若历史缓存为“未知归属地”或“未知”，视为失效并重新向后端拉取
        if (item.loc === (lan && lan.index && lan.index.auto_str_254 || "") || item.loc === (lan && lan.index && lan.index.auto_str_255 || "") || item.loc === (lan && lan.index && lan.index.auto_str_256 || "")) {
          return null;
        }
        return item.loc;
      }
    }
  } catch (e) {}
  return null;
}

// 保存 IP 归属地到 localStorage
function saveIpLocationToCache(ip, loc) {
  if (!ip || !loc) return;
  // 若解析为未知归属地，不写入长期缓存，留待下一次重试自愈
  if (loc === (lan && lan.index && lan.index.auto_str_257 || "") || loc === (lan && lan.index && lan.index.auto_str_258 || "") || loc === (lan && lan.index && lan.index.auto_str_259 || "")) return;
  try {
    var cache = {};
    var cacheStr = localStorage.getItem('bt_ip_loc_cache');
    if (cacheStr) {
      cache = JSON.parse(cacheStr);
    }
    cache[ip] = {
      loc: loc,
      t: Date.now()
    };
    localStorage.setItem('bt_ip_loc_cache', JSON.stringify(cache));
  } catch (e) {}
}

// 异步按需拉取公网 IP 归属地并更新缓存与视图
function fetchAndRenderIpLocations(ipsToFetch) {
  if (!ipsToFetch || ipsToFetch.length === 0) return;
  var uniqueIps = Array.from(new Set(ipsToFetch));
  for (var i = 0; i < uniqueIps.length; i++) {
    (function (targetIp) {
      $.post('/get_ip_location', {
        ip: targetIp
      }, function (res) {
        if (res && res.status && res.data && res.data.location) {
          var loc = res.data.location;
          saveIpLocationToCache(targetIp, loc);
          // 局部更新视图中所有该 IP 的位置占位符
          var $targets = $('[data-ip-loc="' + targetIp + '"]');
          $targets.text(loc).attr('title', loc).removeClass('ip-loc-pending').addClass('ip-loc-text');
        }
      }, 'json').fail(function () {
        var $targets = $('[data-ip-loc="' + targetIp + '"]');
        $targets.text(lan && lan.index && lan.index.auto_str_260 || "").removeClass('ip-loc-pending');
      });
    })(uniqueIps[i]);
  }
}

// 客户端本地时区时间转换格式化 (根据用户浏览器所在时区动态格式化 YYYY-MM-DD HH:mm:ss)
function formatClientLocalTime(timestamp, fallbackStr) {
  if (!timestamp) return fallbackStr || '-';
  try {
    var ts = parseInt(timestamp, 10);
    if (isNaN(ts) || ts <= 0) return fallbackStr || '-';
    if (ts < 10000000000) ts = ts * 1000;
    var date = new Date(ts);
    if (isNaN(date.getTime())) return fallbackStr || '-';
    var y = date.getFullYear();
    var m = (date.getMonth() + 1 < 10 ? '0' : '') + (date.getMonth() + 1);
    var d = (date.getDate() < 10 ? '0' : '') + date.getDate();
    var h = (date.getHours() < 10 ? '0' : '') + date.getHours();
    var min = (date.getMinutes() < 10 ? '0' : '') + date.getMinutes();
    var s = (date.getSeconds() < 10 ? '0' : '') + date.getSeconds();
    return y + '-' + m + '-' + d + ' ' + h + ':' + min + ':' + s;
  } catch (e) {
    return fallbackStr || '-';
  }
}

// 渲染首页右下角最近登录微表格
function renderRecentLoginsTable(data) {
  if (!data) return;
  if (data.current_ip) {
    $('#recentLoginCurrentIp').text(data.current_ip);
  }
  var list = data.list || [];
  if (list.length === 0) {
    $('#recentLoginsTableBody').html(lan && lan.index && lan.index.auto_str_261 || "");
    return;
  }
  var html = '<table class="table recent-logins-table">';
  html += '<thead><tr>';
  html += lan && lan.index && lan.index.auto_str_262 || "";
  html += lan && lan.index && lan.index.auto_str_263 || "";
  html += lan && lan.index && lan.index.auto_str_264 || "";
  html += lan && lan.index && lan.index.auto_str_265 || "";
  html += lan && lan.index && lan.index.auto_str_266 || "";
  html += '</tr></thead><tbody>';
  var ipsToQuery = [];
  for (var i = 0; i < list.length; i++) {
    var item = list[i];
    var isSuccess = item.status === 'success';
    var statusBadge = isSuccess ? lan && lan.index && lan.index.auto_str_267 || "" : lan && lan.index && lan.index.auto_str_268 || "";
    var methodBadge = item.method === 'SSH' ? '<span class="login-method-badge method-ssh" title="' + (item.details || lan && lan.index && lan.index.auto_str_269 || "") + '">SSH</span>' : '<span class="login-method-badge method-web" title="' + (item.details || lan && lan.index && lan.index.auto_str_270 || "") + '">Web</span>';
    var currentMark = item.is_current ? lan && lan.index && lan.index.auto_str_271 || "" : '';

    // 归属地计算与本地缓存
    var locationHtml = '';
    if (item.is_local) {
      var locText = item.location || item.ip_type || '局域网';
      locationHtml = '<span class="f11 c9" title="' + locText + '">' + locText + '</span>';
    } else {
      var cachedLoc = getIpLocationFromCache(item.ip);
      if (cachedLoc) {
        locationHtml = '<span class="f11 c6 ip-loc-text" data-ip-loc="' + item.ip + '" title="' + cachedLoc + '">' + cachedLoc + '</span>';
      } else {
        locationHtml = '<span class="f11 c9 ip-loc-pending" data-ip-loc="' + item.ip + (lan && lan.index && lan.index.auto_str_272 || "");
        ipsToQuery.push(item.ip);
      }
    }
    var localDisplayTime = formatClientLocalTime(item.timestamp, item.log_time);
    var timeTitle = (lan && lan.index && lan.index.auto_str_273 || "") + localDisplayTime + (item.log_time ? (lan && lan.index && lan.index.auto_str_274 || "") + item.log_time : '');
    html += '<tr>';
    html += '<td>' + statusBadge + '</td>';
    html += '<td>' + methodBadge + '</td>';
    html += '<td><span class="login-ip-code">' + (item.ip || '-') + '</span>' + currentMark + '</td>';
    html += '<td>' + locationHtml + '</td>';
    html += '<td style="text-align: right;" class="c9 f11" title="' + timeTitle + '">' + localDisplayTime + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  $('#recentLoginsTableBody').html(html);

  // 异步查询未缓存的公网 IP 归属地
  if (ipsToQuery.length > 0) {
    fetchAndRenderIpLocations(ipsToQuery);
  }
}

// 获取并渲染首页右下角最近 2 次登录记录 (SWR 会话缓存机制：切菜单秒开 + 60s 智能冷却)
function getRecentLogins(forceRefresh) {
  var CACHE_KEY = 'bt_recent_logins_cache';
  var TTL = 60 * 1000; // 60秒智能冷却
  var cachedData = null;
  var lastTime = 0;
  try {
    var raw = sessionStorage.getItem(CACHE_KEY);
    if (raw) {
      var parsed = JSON.parse(raw);
      if (parsed && parsed.data) {
        cachedData = parsed.data;
        lastTime = parsed.t || 0;
      }
    }
  } catch (e) {}

  // 1. 若有会话缓存，第一时间 0ms 瞬间渲染（切换菜单时实现 0 延迟秒开，无闪烁）
  if (cachedData) {
    renderRecentLoginsTable(cachedData);
  }

  // 2. 检查是否处于冷却期内（且非强制刷新）
  var now = Date.now();
  if (!forceRefresh && cachedData && now - lastTime < TTL) {
    // 在 60 秒有效期内直接复用缓存，不再向后端发送请求
    return;
  }

  // 3. 超过冷却期或无缓存时，发起网络请求
  $.post('/get_recent_logins', {
    limit: 2
  }, function (rdata) {
    if (!rdata || !rdata.status) {
      if (!cachedData) {
        $('#recentLoginsTableBody').html(lan && lan.index && lan.index.auto_str_275 || "");
      }
      return;
    }
    var data = rdata.data || {};
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify({
        data: data,
        t: Date.now()
      }));
    } catch (e) {}
    renderRecentLoginsTable(data);
  }, 'json').fail(function () {
    if (!cachedData) {
      $('#recentLoginsTableBody').html(lan && lan.index && lan.index.auto_str_276 || "");
    }
  });
}

// 弹窗展示全部登录记录 (支持分页与多维筛选)
function showAllLoginLogs() {
  var modalHtml = lan && lan.index && lan.index.auto_str_277 || "";
  layer.open({
    type: 1,
    title: lan && lan.index && lan.index.auto_str_278 || "",
    area: ['780px', '530px'],
    closeBtn: 1,
    shadeClose: false,
    content: modalHtml,
    success: function () {
      $('#loginLogStatusFilter, #loginLogMethodFilter').on('change', function () {
        getAllLoginLogs(1);
      });
      getAllLoginLogs(1);
    }
  });
}

// 分页拉取登录记录
function getAllLoginLogs(page) {
  var p = page || 1;
  var status = $('#loginLogStatusFilter').val() || 'all';
  var method = $('#loginLogMethodFilter').val() || 'all';
  $('#allLoginLogsList').html(lan && lan.index && lan.index.auto_str_279 || "");
  $.post('/get_recent_logins', {
    p: p,
    limit: 10,
    status: status,
    method: method,
    tojs: 'getAllLoginLogs'
  }, function (rdata) {
    if (!rdata || !rdata.status) {
      $('#allLoginLogsList').html(lan && lan.index && lan.index.auto_str_280 || "");
      $('#allLoginLogsPage').html('');
      return;
    }
    var data = rdata.data || {};
    var list = data.list || [];
    if (list.length === 0) {
      $('#allLoginLogsList').html(lan && lan.index && lan.index.auto_str_281 || "");
      $('#allLoginLogsPage').html('');
      return;
    }
    var tbodyHtml = '';
    var ipsToQuery = [];
    for (var i = 0; i < list.length; i++) {
      var item = list[i];
      var isSuccess = item.status === 'success';
      var statusBadge = isSuccess ? lan && lan.index && lan.index.auto_str_282 || "" : lan && lan.index && lan.index.auto_str_283 || "";
      var methodBadge = item.method === 'SSH' ? '<span class="login-method-badge method-ssh">SSH</span>' : '<span class="login-method-badge method-web">Web</span>';
      var currentMark = item.is_current ? lan && lan.index && lan.index.auto_str_284 || "" : '';
      var locationHtml = '';
      if (item.is_local) {
        var locText = item.location || item.ip_type || '局域网';
        locationHtml = '<span class="f12 c9" title="' + locText + '">' + locText + '</span>';
      } else {
        var cachedLoc = getIpLocationFromCache(item.ip);
        if (cachedLoc) {
          locationHtml = '<span class="f12 c6 ip-loc-text" data-ip-loc="' + item.ip + '" title="' + cachedLoc + '">' + cachedLoc + '</span>';
        } else {
          locationHtml = '<span class="f12 c9 ip-loc-pending" data-ip-loc="' + item.ip + (lan && lan.index && lan.index.auto_str_285 || "");
          ipsToQuery.push(item.ip);
        }
      }
      var localDisplayTime = formatClientLocalTime(item.timestamp, item.log_time);
      var timeTitle = (lan && lan.index && lan.index.auto_str_286 || "") + localDisplayTime + (item.log_time ? (lan && lan.index && lan.index.auto_str_287 || "") + item.log_time : '');
      tbodyHtml += '<tr>';
      tbodyHtml += '<td>' + statusBadge + '</td>';
      tbodyHtml += '<td>' + methodBadge + '</td>';
      tbodyHtml += '<td><span class="login-ip-code">' + (item.ip || '-') + '</span>' + currentMark + '</td>';
      tbodyHtml += '<td>' + locationHtml + '</td>';
      tbodyHtml += '<td><span class="f12 c6" title="' + (item.details || '-') + '">' + (item.details || '-') + '</span></td>';
      tbodyHtml += '<td style="text-align: right;" class="c9 f12" title="' + timeTitle + '">' + localDisplayTime + '</td>';
      tbodyHtml += '</tr>';
    }
    $('#allLoginLogsList').html(tbodyHtml);
    $('#allLoginLogsPage').html(data.page || '');
    if (ipsToQuery.length > 0) {
      fetchAndRenderIpLocations(ipsToQuery);
    }
  }, 'json').fail(function () {
    $('#allLoginLogsList').html(lan && lan.index && lan.index.auto_str_288 || "");
    $('#allLoginLogsPage').html('');
  });
}