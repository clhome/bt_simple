// 全局存储图表实例
window.chartInstances = {};

// 节流处理 resize
var resizeTimer = null;
$(window).on('resize', function () {
  if (resizeTimer) clearTimeout(resizeTimer);
  resizeTimer = setTimeout(function () {
    for (var key in window.chartInstances) {
      if (window.chartInstances[key]) window.chartInstances[key].resize();
    }
  }, 100);
});

// 图表放大功能
function enlargeChart(chartId, title) {
  if (!window.chartInstances[chartId]) {
    return layer.msg((window.lan && lan.control && lan.control.the_chart_has_not) || t('control.the_chart_has_not', '图表未加载完成'));
  }
  if (!title) {
    var titleMap = {
      'compute_view': (window.lan && lan.control && lan.control.compute_resources) || t('control.compute_resources', '计算资源 (CPU & 内存)'),
      'getload_average_view': (window.lan && lan.control && lan.control.average_load) || t('control.average_load', '平均负载 (1/5/15分钟)'),
      'diskview': (window.lan && lan.control && lan.control.disk_io) || t('control.disk_io', '磁盘 I/O'),
      'network': (window.lan && lan.control && lan.control.net_io) || t('control.net_io', '网络 I/O')
    };
    title = titleMap[chartId] || '';
  }
  var chart = window.chartInstances[chartId];
  var option = chart.getOption();
  layer.open({
    type: 1,
    title: title + ((window.lan && lan.control && lan.control.enlarge) || t('control.enlarge', ' - 放大视图')),
    area: ['85%', '85%'],
    shadeClose: true,
    content: '<div id="enlarge_chart_container" style="width: 100%; height: 100%; padding: 20px;"></div>',
    success: function (layero, index) {
      var enlargeChartInst = echarts.init(document.getElementById('enlarge_chart_container'));
      enlargeChartInst.setOption(option);
      $(window).on('resize.enlarge', function () {
        enlargeChartInst.resize();
      });
    },
    end: function () {
      $(window).off('resize.enlarge');
    }
  });
}

// 辅助时间函数
function getBeforeDate(n) {
  var d = new Date();
  d.setDate(d.getDate() - n);
  var year = d.getFullYear();
  var mon = d.getMonth() + 1;
  var day = d.getDate();
  return year + "/" + (mon < 10 ? '0' + mon : mon) + "/" + (day < 10 ? '0' + day : day);
}

function getToday() {
  var d = new Date();
  var year = d.getFullYear();
  var mon = d.getMonth() + 1;
  var day = d.getDate();
  return year + "/" + (mon < 10 ? '0' + mon : mon) + "/" + (day < 10 ? '0' + day : day);
}

function getTimeRangeByDay(day) {
  var now = new Date().getTime() / 1000;
  var b, e;
  if (day === '24h' || day === 24) {
    b = now - 86400;
    e = now;
  } else if (day == 0) {
    b = new Date(getToday() + " 00:00:01").getTime() / 1000;
    e = now;
  } else if (day == 1) {
    b = new Date(getBeforeDate(day) + " 00:00:01").getTime() / 1000;
    e = new Date(getBeforeDate(day) + " 23:59:59").getTime() / 1000;
  } else {
    b = new Date(getBeforeDate(day) + " 00:00:01").getTime() / 1000;
    e = now;
  }
  return { b: Math.round(b), e: Math.round(e) };
}

// 时序数据智能均值降采样算法（Bucket Averaging）
// 当采样点过多时（如 24 小时 1440 点、7 天 10080 点），按等时间窗口取均值，稳定在约 288 点左右
function aggregateSeries(rdata, fields, maxPoints) {
  maxPoints = maxPoints || 288;
  if (!rdata || rdata.length <= maxPoints) return rdata;

  var step = Math.ceil(rdata.length / maxPoints);
  var res = [];
  for (var i = 0; i < rdata.length; i += step) {
    var chunk = rdata.slice(i, Math.min(i + step, rdata.length));
    if (chunk.length === 0) continue;
    var item = {};
    // 时间取该窗口中段的采样时间
    item.addtime = chunk[Math.floor(chunk.length / 2)].addtime;
    for (var f = 0; f < fields.length; f++) {
      var field = fields[f];
      var sum = 0;
      var count = 0;
      for (var c = 0; c < chunk.length; c++) {
        var v = parseFloat(chunk[c][field]);
        if (!isNaN(v)) {
          sum += v;
          count++;
        }
      }
      var avg = count > 0 ? (sum / count) : 0;
      item[field] = (field === 'read_bytes' || field === 'write_bytes') ? avg : Number(avg.toFixed(2));
    }
    res.push(item);
  }
  return res;
}

// 全局连接组同步
function syncMonitorGroup() {
  setTimeout(function () {
    try {
      echarts.connect('monitorGroup');
    } catch (e) {}
  }, 200);
}

// 统一加载全部图表
function loadAllCharts(b, e) {
  compute(b, e);
  getload(b, e);
  disk(b, e);
  network(b, e);
  syncMonitorGroup();
}

// 顶部全局时间切换
function setGlobalDay(day) {
  $('.globalSearchTime .gt').removeClass('on');
  $('.globalSearchTime .gt[data-day="' + day + '"]').addClass('on');

  var tr = getTimeRangeByDay(day);
  loadAllCharts(tr.b, tr.e);
}

// 渲染底部全局整体拖拉条
var isSyncingDataZoom = false;
function renderGlobalTimeline(xData) {
  if (!document.getElementById('global_timeline_view') || !xData || xData.length === 0) return;
  var sliderChart = echarts.init(document.getElementById('global_timeline_view'));

  var option = {
    animationDurationUpdate: 0,
    grid: {
      top: 0,
      left: 105,
      right: 105,
      bottom: 0
    },
    xAxis: {
      type: 'category',
      show: false,
      boundaryGap: false,
      data: xData
    },
    yAxis: {
      type: 'value',
      show: false
    },
    dataZoom: [{
      type: 'slider',
      show: true,
      xAxisIndex: 0,
      start: 0,
      end: 100,
      top: 3,
      bottom: 3,
      left: 105,
      right: 105,
      borderColor: 'transparent',
      backgroundColor: '#f1f5f9',
      fillerColor: 'rgba(32, 165, 58, 0.18)',
      labelFormatter: function (value, valueStr) {
        if (!valueStr) return '';
        return valueStr.length >= 14 ? valueStr.substring(0, 11) : valueStr;
      },
      handleIcon: 'M10.7,11.9v-1.3H9.3v1.3c-4.9,0.3-8.8,4.4-8.8,9.4c0,5,3.9,9.1,8.8,9.4v1.3h1.3v-1.3c4.9-0.3,8.8-4.4,8.8-9.4C19.5,16.3,15.6,12.2,10.7,11.9z M13.3,24.4H6.7V23h6.6V24.4z M13.3,19.6H6.7v-1.4h6.6V19.6z',
      handleSize: '85%',
      handleStyle: {
        color: '#20a53a',
        borderColor: '#fff',
        borderWidth: 1.5,
        shadowBlur: 3,
        shadowColor: 'rgba(0, 0, 0, 0.35)'
      },
      textStyle: {
        color: '#666',
        fontSize: 11
      }
    }]
  };

  sliderChart.setOption(option);
  window.chartInstances['global_timeline_view'] = sliderChart;

  // 监听全局拖拉条事件，同步缩放所有 4 个核心图表（使用 requestAnimationFrame 节流控制在 60fps）
  var sliderRafId = null;
  sliderChart.off('dataZoom');
  sliderChart.on('dataZoom', function (params) {
    if (isSyncingDataZoom) return;
    if (sliderRafId) cancelAnimationFrame(sliderRafId);
    sliderRafId = requestAnimationFrame(function () {
      isSyncingDataZoom = true;
      var start = params.start !== undefined ? params.start : (params.batch && params.batch[0] ? params.batch[0].start : 0);
      var end = params.end !== undefined ? params.end : (params.batch && params.batch[0] ? params.batch[0].end : 100);

      var charts = ['compute_view', 'getload_average_view', 'diskview', 'network'];
      for (var i = 0; i < charts.length; i++) {
        var chart = window.chartInstances[charts[i]];
        if (chart) {
          chart.dispatchAction({
            type: 'dataZoom',
            start: start,
            end: end
          });
        }
      }
      setTimeout(function () {
        isSyncingDataZoom = false;
      }, 30);
    });
  });
}

// 为卡片图表绑定内部缩放双向同步到全局滑块
function bindInsideZoomSync(chartInst) {
  var insideRafId = null;
  chartInst.off('dataZoom');
  chartInst.on('dataZoom', function (params) {
    if (isSyncingDataZoom) return;
    if (insideRafId) cancelAnimationFrame(insideRafId);
    insideRafId = requestAnimationFrame(function () {
      isSyncingDataZoom = true;
      var start = params.start !== undefined ? params.start : (params.batch && params.batch[0] ? params.batch[0].start : 0);
      var end = params.end !== undefined ? params.end : (params.batch && params.batch[0] ? params.batch[0].end : 100);

      var slider = window.chartInstances['global_timeline_view'];
      if (slider) {
        slider.dispatchAction({
          type: 'dataZoom',
          start: start,
          end: end
        });
      }

      var charts = ['compute_view', 'getload_average_view', 'diskview', 'network'];
      for (var i = 0; i < charts.length; i++) {
        var otherChart = window.chartInstances[charts[i]];
        if (otherChart && otherChart !== chartInst) {
          otherChart.dispatchAction({
            type: 'dataZoom',
            start: start,
            end: end
          });
        }
      }
      setTimeout(function () {
        isSyncingDataZoom = false;
      }, 30);
    });
  });
}

// 1. 计算资源 (CPU & 内存) - 单次请求渲染双折线
function compute(b, e) {
  $.get('/system/get_cpu_io?start=' + b + '&end=' + e, function (res) {
    if (!document.getElementById('compute_view')) return;
    var rawData = res.data || [];
    // 智能均值降采样
    var rdata = aggregateSeries(rawData, ['pro', 'mem']);
    var myChartCompute = echarts.init(document.getElementById('compute_view'));
    myChartCompute.group = 'monitorGroup';

    var xData = [];
    var cpuData = [];
    var memData = [];

    for (var i = 0; i < rdata.length; i++) {
      xData.push(rdata[i].addtime);
      cpuData.push(rdata[i].pro);
      memData.push(rdata[i].mem);
    }

    var cpuLabel = (window.lan && lan.control && lan.control.cpu) || t('control.cpu', 'CPU');
    var memLabel = (window.lan && lan.control && lan.control.mem) || t('control.mem', '内存');
    var percentLabel = (window.lan && lan.public && lan.public.pre) || t('public.pre', '百分比(%)');
    var timeLabel = (window.lan && lan.public && lan.public.time) || t('public.time', '时间');

    var option = {
      animationDurationUpdate: 0,
      grid: {
        top: 35,
        left: '8%',
        right: '4%',
        bottom: 25
      },
      legend: {
        data: [cpuLabel, memLabel],
        top: 5,
        right: '4%'
      },
      tooltip: {
        trigger: 'axis',
        triggerOn: 'none', // 移动过程中不显示，由停顿200ms统一触发
        transitionDuration: 0,
        className: 'monitor-chart-tooltip',
        confine: true,
        axisPointer: {
          type: 'cross',
          snap: true,
          animation: false
        },
        formatter: function (params) {
          if (!params || params.length === 0) return '';
          var tip = '<b>' + timeLabel + '：' + params[0].axisValue + '</b>';
          for (var i = 0; i < params.length; i++) {
            var val = params[i].value !== undefined && params[i].value !== null ? params[i].value : '0';
            tip += '<br />' + params[i].marker + ' ' + params[i].seriesName + ': <b>' + val + '%</b>';
          }
          return tip;
        }
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: xData,
        axisPointer: {
          snap: true
        },
        axisLine: {
          lineStyle: {
            color: "#666"
          }
        }
      },
      yAxis: {
        type: 'value',
        name: percentLabel,
        boundaryGap: [0, '100%'],
        min: 0,
        max: 100,
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
      dataZoom: [{
        type: 'inside',
        start: 0,
        end: 100
      }],
      series: [
        {
          name: cpuLabel,
          type: 'line',
          smooth: false,
          symbol: 'none',
          sampling: 'lttb',
          itemStyle: {
            color: 'rgb(0, 153, 238)'
          },
          lineStyle: {
            width: 1.8
          },
          data: cpuData
        },
        {
          name: memLabel,
          type: 'line',
          smooth: false,
          symbol: 'none',
          sampling: 'lttb',
          itemStyle: {
            color: 'rgb(147, 38, 255)'
          },
          lineStyle: {
            width: 1.8
          },
          data: memData
        }
      ]
    };

    myChartCompute.setOption(option);
    window.chartInstances['compute_view'] = myChartCompute;
    bindInsideZoomSync(myChartCompute);

    // 渲染底部时间滑块
    renderGlobalTimeline(xData);
  }, 'json');
}

// 2. 平均负载 (1/5/15分钟)
function getload(b, e) {
  $.get('/system/get_load_average?start=' + b + '&end=' + e, function (res) {
    if (!document.getElementById('getload_average_view')) return;
    var rawData = res.data || [];
    // 智能均值降采样
    var rdata = aggregateSeries(rawData, ['one', 'five', 'fifteen']);
    var myChartAverage = echarts.init(document.getElementById('getload_average_view'));
    myChartAverage.group = 'monitorGroup';

    var xData = [];
    var oneData = [];
    var fiveData = [];
    var fifteenData = [];

    for (var i = 0; i < rdata.length; i++) {
      xData.push(rdata[i].addtime);
      oneData.push(rdata[i].one);
      fiveData.push(rdata[i].five);
      fifteenData.push(rdata[i].fifteen);
    }

    var label1 = (window.lan && lan.control && lan.control.minute_2) || t('control.minute_2', '1分钟');
    var label5 = (window.lan && lan.control && lan.control.minutes_4) || t('control.minutes_4', '5分钟');
    var label15 = (window.lan && lan.control && lan.control.minutes_5) || t('control.minutes_5', '15分钟');
    var loadTitle = (window.lan && lan.control && lan.control.load_details) || t('control.load_details', '负载详情');
    var timeLabel = (window.lan && lan.public && lan.public.time) || t('public.time', '时间');

    var option = {
      animationDurationUpdate: 0,
      grid: {
        top: 35,
        left: '8%',
        right: '4%',
        bottom: 25
      },
      legend: {
        data: [label1, label5, label15],
        top: 5,
        right: '4%'
      },
      tooltip: {
        trigger: 'axis',
        triggerOn: 'none', // 移动过程中不显示，由停顿200ms统一触发
        transitionDuration: 0,
        className: 'monitor-chart-tooltip',
        confine: true,
        axisPointer: {
          type: 'cross',
          snap: true,
          animation: false
        },
        formatter: function (params) {
          if (!params || params.length === 0) return '';
          var tip = '<b>' + timeLabel + '：' + params[0].axisValue + '</b>';
          for (var i = 0; i < params.length; i++) {
            var val = params[i].value !== undefined && params[i].value !== null ? params[i].value : '0.00';
            tip += '<br />' + params[i].marker + ' ' + params[i].seriesName + ': <b>' + val + '</b>';
          }
          return tip;
        }
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: xData,
        axisPointer: {
          snap: true
        },
        axisLine: {
          lineStyle: {
            color: "#666"
          }
        }
      },
      yAxis: {
        type: 'value',
        name: loadTitle,
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
      dataZoom: [{
        type: 'inside',
        start: 0,
        end: 100
      }],
      series: [
        {
          name: label1,
          type: 'line',
          smooth: false,
          symbol: 'none',
          sampling: 'lttb',
          itemStyle: {
            color: 'rgb(30, 144, 255)'
          },
          lineStyle: {
            width: 1.8
          },
          data: oneData
        },
        {
          name: label5,
          type: 'line',
          smooth: false,
          symbol: 'none',
          sampling: 'lttb',
          itemStyle: {
            color: 'rgb(0, 178, 45)'
          },
          lineStyle: {
            width: 1.8
          },
          data: fiveData
        },
        {
          name: label15,
          type: 'line',
          smooth: false,
          symbol: 'none',
          sampling: 'lttb',
          itemStyle: {
            color: 'rgb(147, 38, 255)'
          },
          lineStyle: {
            width: 1.8
          },
          data: fifteenData
        }
      ]
    };

    myChartAverage.setOption(option);
    window.chartInstances['getload_average_view'] = myChartAverage;
    bindInsideZoomSync(myChartAverage);
  }, 'json');
}

// 3. 磁盘 I/O
function disk(b, e) {
  $.get('/system/get_disk_io?start=' + b + '&end=' + e, function (res) {
    if (!document.getElementById('diskview')) return;
    var rawData = res.data || [];
    // 智能均值降采样
    var rdata = aggregateSeries(rawData, ['read_bytes', 'write_bytes']);
    var myChartDisk = echarts.init(document.getElementById('diskview'));
    myChartDisk.group = 'monitorGroup';

    var rData = [];
    var wData = [];
    var xData = [];

    for (var i = 0; i < rdata.length; i++) {
      rData.push((rdata[i].read_bytes / 1024 / 60).toFixed(3));
      wData.push((rdata[i].write_bytes / 1024 / 60).toFixed(3));
      xData.push(rdata[i].addtime);
    }

    var readLabel = (window.lan && lan.control && lan.control.number_of_bytes_read) || t('control.number_of_bytes_read', '读取字节数');
    var writeLabel = (window.lan && lan.control && lan.control.number_of_bytes_written) || t('control.number_of_bytes_written', '写入字节数');
    var unitLabel = (window.lan && lan.control && lan.control.unit_kb) || t('control.unit_kb', '单位(KB)');
    var timeLabel = (window.lan && lan.public && lan.public.time) || t('public.time', '时间');

    var option = {
      animationDurationUpdate: 0,
      grid: {
        top: 35,
        left: '8%',
        right: '4%',
        bottom: 25
      },
      legend: {
        data: [readLabel, writeLabel],
        top: 5,
        right: '4%'
      },
      tooltip: {
        trigger: 'axis',
        triggerOn: 'none', // 移动过程中不显示，由停顿200ms统一触发
        transitionDuration: 0,
        className: 'monitor-chart-tooltip',
        confine: true,
        axisPointer: {
          type: 'cross',
          snap: true,
          animation: false
        },
        formatter: function (params) {
          if (!params || params.length === 0) return '';
          var tip = '<b>' + timeLabel + '：' + params[0].axisValue + '</b>';
          for (var i = 0; i < params.length; i++) {
            var val = params[i].value !== undefined && params[i].value !== null ? params[i].value : '0';
            tip += '<br />' + params[i].marker + ' ' + params[i].seriesName + ': <b>' + val + ' Kb/s</b>';
          }
          return tip;
        }
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: xData,
        axisPointer: {
          snap: true
        },
        axisLine: {
          lineStyle: {
            color: "#666"
          }
        }
      },
      yAxis: {
        type: 'value',
        name: unitLabel,
        boundaryGap: [0, '100%'],
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
      dataZoom: [{
        type: 'inside',
        start: 0,
        end: 100
      }],
      series: [
        {
          name: readLabel,
          type: 'line',
          smooth: false,
          symbol: 'none',
          sampling: 'lttb',
          itemStyle: {
            color: 'rgb(255, 70, 131)'
          },
          lineStyle: {
            width: 1.8
          },
          data: rData
        },
        {
          name: writeLabel,
          type: 'line',
          smooth: false,
          symbol: 'none',
          sampling: 'lttb',
          itemStyle: {
            color: 'rgba(46, 165, 186, 0.85)'
          },
          lineStyle: {
            width: 1.8
          },
          data: wData
        }
      ]
    };

    myChartDisk.setOption(option);
    window.chartInstances['diskview'] = myChartDisk;
    bindInsideZoomSync(myChartDisk);
  }, 'json');
}

// 4. 网络 I/O
function network(b, e) {
  $.get('/system/get_network_io?start=' + b + '&end=' + e, function (res) {
    if (!document.getElementById('network')) return;
    var rawData = res.data || [];
    // 智能均值降采样
    var rdata = aggregateSeries(rawData, ['up', 'down']);
    var myChartNetwork = echarts.init(document.getElementById('network'));
    myChartNetwork.group = 'monitorGroup';

    var xData = [];
    var yData = [];
    var zData = [];

    for (var i = 0; i < rdata.length; i++) {
      xData.push(rdata[i].addtime);
      yData.push(rdata[i].up);
      zData.push(rdata[i].down);
    }

    var upLabel = (window.lan && lan.control && lan.control.up) || t('control.up', '上行');
    var downLabel = (window.lan && lan.control && lan.control.down) || t('control.down', '下行');
    var unitLabel = (window.lan && lan.control && lan.control.unit_kb) || t('control.unit_kb', '单位(KB)');
    var timeLabel = (window.lan && lan.public && lan.public.time) || t('public.time', '时间');

    var option = {
      animationDurationUpdate: 0,
      grid: {
        top: 35,
        left: '8%',
        right: '4%',
        bottom: 25
      },
      legend: {
        data: [upLabel, downLabel],
        top: 5,
        right: '4%'
      },
      tooltip: {
        trigger: 'axis',
        triggerOn: 'none', // 移动过程中不显示，由停顿200ms统一触发
        transitionDuration: 0,
        className: 'monitor-chart-tooltip',
        confine: true,
        axisPointer: {
          type: 'cross',
          snap: true,
          animation: false
        },
        formatter: function (params) {
          if (!params || params.length === 0) return '';
          var tip = '<b>' + timeLabel + '：' + params[0].axisValue + '</b>';
          for (var i = 0; i < params.length; i++) {
            var val = params[i].value !== undefined && params[i].value !== null ? params[i].value : '0';
            tip += '<br />' + params[i].marker + ' ' + params[i].seriesName + ': <b>' + val + ' Kb/s</b>';
          }
          return tip;
        }
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: xData,
        axisPointer: {
          snap: true
        },
        axisLine: {
          lineStyle: {
            color: "#666"
          }
        }
      },
      yAxis: {
        type: 'value',
        name: unitLabel,
        boundaryGap: [0, '100%'],
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
      dataZoom: [{
        type: 'inside',
        start: 0,
        end: 100
      }],
      series: [
        {
          name: upLabel,
          type: 'line',
          smooth: false,
          symbol: 'none',
          sampling: 'lttb',
          itemStyle: {
            color: 'rgb(255, 140, 0)'
          },
          lineStyle: {
            width: 1.8
          },
          data: yData
        },
        {
          name: downLabel,
          type: 'line',
          smooth: false,
          symbol: 'none',
          sampling: 'lttb',
          itemStyle: {
            color: 'rgb(30, 144, 255)'
          },
          lineStyle: {
            width: 1.8
          },
          data: zData
        }
      ]
    };

    myChartNetwork.setOption(option);
    window.chartInstances['network'] = myChartNetwork;
    bindInsideZoomSync(myChartNetwork);
  }, 'json');
}

// 统一鼠标悬停控制：移动中不显示 Tooltip（零开销），停顿至少 200ms 时 4 个图表同步显示该时刻详情
var hoverDebounceTimer = null;
var activeDataIndex = -1;

$(document).on('mousemove', '.monitor-chart', function (e) {
  var chartId = $(this).attr('id');
  var chart = window.chartInstances[chartId];
  if (!chart) return;

  // 只要鼠标在移动，立即隐藏所有已弹出的 Tooltip
  if (hoverDebounceTimer) clearTimeout(hoverDebounceTimer);
  if (activeDataIndex !== -1) {
    activeDataIndex = -1;
    var charts = ['compute_view', 'getload_average_view', 'diskview', 'network'];
    for (var i = 0; i < charts.length; i++) {
      var c = window.chartInstances[charts[i]];
      if (c) c.dispatchAction({ type: 'hideTip' });
    }
  }

  var rect = this.getBoundingClientRect();
  var mouseX = e.clientX - rect.left;
  var mouseY = e.clientY - rect.top;

  // 鼠标停下来至少 200ms 后才触发显示
  hoverDebounceTimer = setTimeout(function () {
    try {
      if (!chart.containPixel({ gridIndex: 0 }, [mouseX, mouseY])) return;
      var rawIdx = chart.convertFromPixel({ xAxisIndex: 0 }, mouseX);
      if (rawIdx === undefined || rawIdx === null || isNaN(rawIdx)) return;
      var dataIndex = Math.round(rawIdx);
      activeDataIndex = dataIndex;

      // 4 大图表同步弹出该数据索引处的时刻详情
      var charts = ['compute_view', 'getload_average_view', 'diskview', 'network'];
      for (var j = 0; j < charts.length; j++) {
        var targetChart = window.chartInstances[charts[j]];
        if (targetChart) {
          targetChart.dispatchAction({
            type: 'showTip',
            seriesIndex: 0,
            dataIndex: dataIndex
          });
        }
      }
    } catch (err) {}
  }, 200);
});

$(document).on('mouseleave', '.monitor-chart', function () {
  if (hoverDebounceTimer) clearTimeout(hoverDebounceTimer);
  activeDataIndex = -1;
  var charts = ['compute_view', 'getload_average_view', 'diskview', 'network'];
  for (var i = 0; i < charts.length; i++) {
    var c = window.chartInstances[charts[i]];
    if (c) c.dispatchAction({ type: 'hideTip' });
  }
});

// 页面初始化与交互绑定
$(function () {
  // 默认加载最近24小时数据
  setGlobalDay('24h');

  // 展开/收起日历弹窗
  $(document).on('click', '.searcTime .st', function (e) {
    e.stopPropagation();
    var $time = $(this).next();
    $('.searcTime .time').not($time).hide();
    $time.toggle();
  });

  $(document).on('click', function (e) {
    if (!$(e.target).closest('.searcTime').length) {
      $('.searcTime .time').hide();
    }
  });

  // 渲染日期时间范围选择器
  if (document.getElementById('global_rtime')) {
    laydate.render({
      elem: '#global_rtime',
      type: 'datetime',
      range: true
    });
    var b = getBeforeDate(28).replaceAll('/', '-') + " 00:00:00";
    var e = getBeforeDate(0).replaceAll('/', '-') + " 23:59:59";
    $('#global_rtime').val(b + ' - ' + e);
  }

  // 自定义时间提交按钮
  $('.sbtn').on('click', function () {
    $(".searcTime .time").hide();
    var rtime = $(this).parent().find(".rtime").val();
    if (!rtime) return;
    var rarr = rtime.split(' - ');
    var b = Math.round(new Date(rarr[0]).getTime() / 1000);
    var e = Math.round(new Date(rarr[1]).getTime() / 1000);

    $('.searcTime .gt').removeClass('on');
    loadAllCharts(b, e);
  });

  // 获取监控状态
  getStatus();
});

// 取监控状态
function getStatus() {
  var loadT = layer.msg((window.lan && lan.control && lan.control.loading_please_wait) || t('control.loading_please_wait', '正在加载，请稍候...'), {
    icon: 16,
    time: 0
  });
  $.post('/system/set_control', 'type=-1', function (rdata) {
    layer.close(loadT);
    if (rdata.status) {
      $("#openJK").html("<input class='btswitch btswitch-ios' id='ctswitch' type='checkbox' checked><label class='btswitch-btn' for='ctswitch' onclick='setControl(\"openjk\", true)'></label>");
    } else {
      $("#openJK").html("<input class='btswitch btswitch-ios' id='ctswitch' type='checkbox'><label class='btswitch-btn' for='ctswitch' onclick='setControl(\"openjk\",false)'></label>");
    }
    if (rdata.stat_all_status) {
      $("#statAll").html("<input class='btswitch btswitch-ios' id='stat_witch' type='checkbox' checked><label class='btswitch-btn' for='stat_witch' onclick='setControl(\"stat\",true)'></label>");
    } else {
      $("#statAll").html("<input class='btswitch btswitch-ios' id='stat_witch' type='checkbox'><label class='btswitch-btn' for='stat_witch' onclick='setControl(\"stat\",false)'></label>");
    }
    $("#save_day").val(rdata.day);
  }, 'json');
}

// 设置监控状态
function setControl(act, value) {
  var type = '';
  var day = $("#save_day").val();

  if (act == 'openjk') {
    type = $("#ctswitch").prop('checked') ? '0' : '1';
    if (day < 1) {
      layer.msg((window.lan && lan.control && lan.control.the_number_of_days) || t('control.the_number_of_days', '天数不能小于1'), {
        icon: 2
      });
      return;
    }
  } else if (act == 'stat') {
    type = $("#stat_witch").prop('checked') ? '2' : '3';
  } else if (act == 'save_day') {
    type = 'save_day';
    if (day < 1) {
      layer.msg((window.lan && lan.control && lan.control.the_number_of_days_1) || t('control.the_number_of_days_1', '天数不能小于1'), {
        icon: 2
      });
      return;
    }
  }

  var loadT = layer.msg((window.lan && lan.control && lan.control.processing_please_wait) || t('control.processing_please_wait', '正在处理，请稍候...'), {
    icon: 16,
    time: 0
  });
  $.post('/system/set_control', 'type=' + type + '&day=' + day, function (rdata) {
    showMsg(rdata.msg, function () {
      layer.close(loadT);
    }, {
      icon: rdata.status ? 1 : 2
    });
  }, 'json');
}

// 清理记录
function closeControl() {
  layer.confirm((window.lan && lan.control && lan.control.did_you_really_delete) || t('control.did_you_really_delete', '真的要清空所有监控记录吗？'), {
    title: (window.lan && lan.control && lan.control.clear_history) || t('control.clear_history', '清空历史记录'),
    icon: 3,
    closeBtn: 1
  }, function () {
    var loadT = layer.msg((window.lan && lan.control && lan.control.processing_please_wait_1) || t('control.processing_please_wait_1', '正在处理，请稍候...'), {
      icon: 16,
      time: 0
    });
    $.post('/system/set_control', 'type=del', function (rdata) {
      showMsg(rdata.msg, function () {
        layer.close(loadT);
      }, {
        icon: rdata.status ? 1 : 2
      });
    }, 'json');
  });
}