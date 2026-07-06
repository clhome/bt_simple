//全局存储图表实例
window.chartInstances = {};

//节流处理 resize
var resizeTimer = null;
$(window).on('resize', function() {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function() {
        for (var key in window.chartInstances) {
            if (window.chartInstances[key]) window.chartInstances[key].resize();
        }
    }, 100);
});

//图表放大功能
function enlargeChart(chartId, title) {
	if (!window.chartInstances[chartId]) return layer.msg('图表尚未加载完毕');
	var chart = window.chartInstances[chartId];
	var option = chart.getOption();
	layer.open({
		type: 1,
		title: title + ' (放大)',
		area: ['80%', '80%'],
		shadeClose: true,
		content: '<div id="enlarge_chart_container" style="width: 100%; height: 100%; padding: 20px;"></div>',
		success: function(layero, index) {
			var enlargeChartInst = echarts.init(document.getElementById('enlarge_chart_container'));
			enlargeChartInst.setOption(option);
			$(window).on('resize.enlarge', function() {
				enlargeChartInst.resize();
			});
		},
		end: function() {
			$(window).off('resize.enlarge');
		}
	});
}

//默认显示7天周期图表
setTimeout(function(){
	Wday(0,'getload');
},100);
setTimeout(function(){
	Wday(0,'cpu');
},200);
setTimeout(function(){
	Wday(0,'mem');
},500);
setTimeout(function(){
	Wday(0,'disk');
},100);
setTimeout(function(){
	Wday(0,'network');
},1500);


$(".searcTime .st").on('click', function(){
	var status = $(this).data('status');
	if (status == 'show'){
		$(this).next().hide();
		$(this).data('status','hide');
	} else{
		$(this).next().show();
		$(this).data('status','show');
	}
});

//自定义时间-切换
$(".searcTime .st").on('mouseenter', function(){
	$(this).data('status','show');
	$(this).next().show();
}).on('mouseleave', function(){
	// $(this).next().hide();
	// $(this).next().hover(function(){
	// 	$(this).show();
	// },function(){
	// 	$(this).hide();
	// })
})

$(".searcTime .gt").on('click', function(){
	$(this).addClass("on").siblings().removeClass("on");
})


//渲染日期时间范围 start
var render_dlist = [
	'loadbtn_rtime',
	'cpubtn_rtime',
	'membtn_rtime',
	'diskbtn_rtime',
	'networkbtn_rtime'
];

$(function() {
	for (var i = 0; i < render_dlist.length; i++) {
		
		laydate.render({
			elem: '#'+render_dlist[i]
			,type: 'datetime'
			,range: true
		});


		var b = getBeforeDate(28).replaceAll('/','-') + " 00:00:00";
		var e = getBeforeDate(0).replaceAll('/','-') + " 23:59:59";

		$('#'+render_dlist[i]).val(b + ' - ' + e);
	}
});
//渲染日期时间范围 end


$('.sbtn').on('click', function(){
	$(".searcTime .st").next().hide();

	var rtime = $(this).parent().find(".rtime").val();
	var rarr = rtime.split(' - ');

	var b = (new Date(rarr[0]).getTime())/1000;
	var e = (new Date(rarr[1]).getTime())/1000;

	b = Math.round(b);
	e = Math.round(e);

	if ($(this).hasClass('loadbtn')){
		getload(b,e);
	} else if ($(this).hasClass('cpubtn')){
		cpu(b,e);
	}else if ($(this).hasClass('membtn')){
		mem(b,e);
	} else if ($(this).hasClass('diskbtn')){
		disk(b,e);
	}
});

//指定天数
function Wday(day,name){
	var now = (new Date().getTime())/1000;
	if(day==0){
		var b = (new Date(getToday() + " 00:00:01").getTime())/1000;
			b = Math.round(b);
		var e = Math.round(now);
	}
	if(day==1){
		var b = (new Date(getBeforeDate(day) + " 00:00:01").getTime())/1000;
		var e = (new Date(getBeforeDate(day) + " 23:59:59").getTime())/1000;
		b = Math.round(b);
		e = Math.round(e);
	}
	else{
		var b = (new Date(getBeforeDate(day) + " 00:00:01").getTime())/1000;
			b = Math.round(b);
		var e = Math.round(now);
	}
	switch (name){
		case "cpu":
			cpu(b, e);
			break;
		case "mem":
			mem(b, e);
			break;
		case "disk":
			disk(b, e);
			break;
		case "network":
			network(b, e);
			break;
		case "getload":
			getload(b, e);
			break;
	}
}

function getToday(){
   var mydate = new Date();
   var str = "" + mydate.getFullYear() + "/";
   str += (mydate.getMonth()+1) + "/";
   str += mydate.getDate();
   return str;
}

getStatus();
//取监控状态
function getStatus(){
	loadT = layer.msg('正在读取,请稍候...',{icon:16,time:0})
	$.post('/system/set_control','type=-1',function(rdata){
		layer.close(loadT);

		if(rdata.status){
			$("#openJK").html("<input class='btswitch btswitch-ios' id='ctswitch' type='checkbox' checked><label class='btswitch-btn' for='ctswitch' onclick='setControl(\"openjk\", true)'></label>");
		} else {
			$("#openJK").html("<input class='btswitch btswitch-ios' id='ctswitch' type='checkbox'><label class='btswitch-btn' for='ctswitch' onclick='setControl(\"openjk\",false)'></label>");
		}

		if(rdata.stat_all_status){
			$("#statAll").html("<input class='btswitch btswitch-ios' id='stat_witch' type='checkbox' checked><label class='btswitch-btn' for='stat_witch' onclick='setControl(\"stat\",true)'></label>");
		} else{
			$("#statAll").html("<input class='btswitch btswitch-ios' id='stat_witch' type='checkbox'><label class='btswitch-btn' for='stat_witch' onclick='setControl(\"stat\",false)'></label>");
		}

		$("#save_day").val(rdata.day);

	},'json');
}


//设置监控状态
function setControl(act, value=false){

	if (act == 'openjk'){
		var type = $("#ctswitch").prop('checked')?'0':'1';
		var day = $("#save_day").val();
		if(day < 1){
			layer.msg('保存天数不合法!',{icon:2});
			return;
		}
	} else if (act == 'stat'){
		var type = $("#stat_witch").prop('checked')?'2':'3';
	} else if (act == 'save_day'){
		var type = 'save_day';
		var day = $("#save_day").val();

		if(day < 1){
			layer.msg('保存天数不合法!',{icon:2});
			return;
		}
	}
	
	loadT = layer.msg('正在处理,请稍候...',{icon:16,time:0})
	$.post('/system/set_control','type='+type+'&day='+day,function(rdata){
		showMsg(rdata.msg, function(){
			layer.close(loadT);
		},{icon:rdata.status?1:2})
	},'json');
}


//清理记录
function closeControl(){
	layer.confirm('您真的清空所有监控记录吗？',{title:'清空记录',icon:3,closeBtn:1}, function() {
		loadT = layer.msg('正在处理,请稍候...',{icon:16,time:0})
		$.post('/system/set_control','type=del',function(rdata){
			showMsg(rdata.msg, function(){
				layer.close(loadT);
			},{icon:rdata.status?1:2})
		},'json');
	});
}


//定义周期时间
function getBeforeDate(n){
    var n = n;
    var d = new Date();
    var year = d.getFullYear();
    var mon=d.getMonth()+1;
    var day=d.getDate();
    if(day <= n){
		if(mon>1) {
		  	mon = mon-1;
		} else {
			year = year-1;
			mon = 12;
		}
	}
	d.setDate(d.getDate()-n);
	year = d.getFullYear();
	mon=d.getMonth()+1;
	day=d.getDate();
  	s = year+"/"+(mon<10?('0'+mon):mon)+"/"+(day<10?('0'+day):day);
	return s;
}
//cpu
function cpu(b,e){
	$.get('/system/get_cpu_io?start='+b+'&end='+e,function(rdata){
		if (!document.getElementById('cupview')) return;
		var rdata = rdata.data;
		var myChartCpu = echarts.init(document.getElementById('cupview'));
		var xData = [];
		var yData = [];
		//var zData = [];
		
		for(var i = 0; i < rdata.length; i++){
			xData.push(rdata[i].addtime);
			yData.push(rdata[i].pro);
			//zData.push(rdata[i].mem);
		}
		option = {
			grid: {
				bottom: 85
			},
			tooltip: {
				trigger: 'axis',
				axisPointer: { type: 'cross' },
				formatter: '{b}<br />{a}: {c}%'
			},
			xAxis: {
				type: 'category',
				boundaryGap: false,
				data: xData,
				axisLine:{ lineStyle:{ color:"#666"} } 
			},
			yAxis: {
				type: 'value',
				name: lan.public.pre,
				boundaryGap: [0, '100%'],
				min:0,
				max: 100,
				splitLine:{ lineStyle:{ color:"#ddd" } },
				axisLine:{ lineStyle:{ color:"#666" } }
			},
			dataZoom: [{
				type: 'inside',
				start: 0,
				end: 100,
				zoomLock:true
			}, {
				start: 0,
				end: 100,
				bottom: 25,
				handleIcon: 'M10.7,11.9v-1.3H9.3v1.3c-4.9,0.3-8.8,4.4-8.8,9.4c0,5,3.9,9.1,8.8,9.4v1.3h1.3v-1.3c4.9-0.3,8.8-4.4,8.8-9.4C19.5,16.3,15.6,12.2,10.7,11.9z M13.3,24.4H6.7V23h6.6V24.4z M13.3,19.6H6.7v-1.4h6.6V19.6z',
				handleSize: '80%',
				handleStyle: {
					color: '#fff',
					shadowBlur: 3,
					shadowColor: 'rgba(0, 0, 0, 0.6)',
					shadowOffsetX: 2,
					shadowOffsetY: 2
				}
			}],
			series: [
				{
					name:'CPU',
					type:'line',
					smooth:true,
					symbol: 'none',
					sampling: 'average',
					itemStyle: { normal: { color: 'rgb(0, 153, 238)' } },
					data: yData
				}
			]
		};
		myChartCpu.setOption(option);
		window.chartInstances['cupview'] = myChartCpu;
	},'json');
}

//内存
function mem(b,e){
	$.get('/system/get_cpu_io?start='+b+'&end='+e,function(rdata){
		if (!document.getElementById('memview')) return;
		var rdata = rdata.data;
		var myChartMen = echarts.init(document.getElementById('memview'));
		var xData = [];
		//var yData = [];
		var zData = [];
		
		for(var i = 0; i < rdata.length; i++){
			xData.push(rdata[i].addtime);
			//yData.push(rdata[i].pro);
			zData.push(rdata[i].mem);
		}
		option = {
			grid: {
				bottom: 70
			},
			tooltip: {
				trigger: 'axis',
				axisPointer: { type: 'cross' },
				formatter: '{b}<br />{a}: {c}%'
			},
			xAxis: {
				type: 'category',
				boundaryGap: false,
				data: xData,
				axisLine:{ lineStyle:{ color:"#666" } }
			},
			yAxis: {
				type: 'value',
				name: lan.public.pre,
				boundaryGap: [0, '100%'],
				min:0,
				max: 100,
				splitLine:{ lineStyle:{ color:"#ddd" } },
				axisLine:{ lineStyle:{ color:"#666" } }
			},
			dataZoom: [{
				type: 'inside',
				start: 0,
				end: 100,
				zoomLock:true
			}, {
				start: 0,
				end: 100,
				bottom: 10,
				handleIcon: 'M10.7,11.9v-1.3H9.3v1.3c-4.9,0.3-8.8,4.4-8.8,9.4c0,5,3.9,9.1,8.8,9.4v1.3h1.3v-1.3c4.9-0.3,8.8-4.4,8.8-9.4C19.5,16.3,15.6,12.2,10.7,11.9z M13.3,24.4H6.7V23h6.6V24.4z M13.3,19.6H6.7v-1.4h6.6V19.6z',
				handleSize: '80%',
				handleStyle: {
					color: '#fff',
					shadowBlur: 3,
					shadowColor: 'rgba(0, 0, 0, 0.6)',
					shadowOffsetX: 2,
					shadowOffsetY: 2
				}
			}],
			series: [
				{
					name:lan.index.process_mem,
					type:'line',
					smooth:true,
					symbol: 'none',
					sampling: 'average',
					itemStyle: { normal: { color: 'rgb(0, 153, 238)' } },
					data: zData
				}
			]
		};
		myChartMen.setOption(option);
		window.chartInstances['memview'] = myChartMen;
	},'json');
}

//磁盘io
function disk(b,e){
	$.get('/system/get_disk_io?start='+b+'&end='+e,function(rdata){
		if (!document.getElementById('diskview')) return;
		var rdata = rdata.data;
		var myChartDisk = echarts.init(document.getElementById('diskview'));
		var rData = [];
		var wData = [];
		var xData = [];
		//var yData = [];
		//var zData = [];
		
		for(var i = 0; i < rdata.length; i++){
			rData.push((rdata[i].read_bytes/1024/60).toFixed(3));
			wData.push((rdata[i].write_bytes/1024/60).toFixed(3));
			xData.push(rdata[i].addtime);
			//yData.push(rdata[i].read_count);
			//zData.push(rdata[i].write_count);
		}
		option = {
			grid: {
				bottom: 70
			},
			tooltip: {
				trigger: 'axis',
				axisPointer: {
					type: 'cross'
				},
				formatter:"时间：{b0}<br />{a0}: {c0} Kb/s<br />{a1}: {c1} Kb/s", 
			},
			legend: {
				data:['读取字节数','写入字节数']
			},
			xAxis: {
				type: 'category',
				boundaryGap: false,
				data: xData,
				axisLine:{ lineStyle:{ color:"#666" }}
			},
			yAxis: {
				type: 'value',
				name: '单位:KB/s',
				boundaryGap: [0, '100%'],
				splitLine:{ lineStyle:{ color:"#ddd"} },
				axisLine:{ lineStyle:{ color:"#666" } }
			},
			dataZoom: [{
				type: 'inside',
				start: 0,
				end: 100,
				zoomLock:true
			}, {
				start: 0,
				end: 100,
				bottom: 10,
				handleIcon: 'M10.7,11.9v-1.3H9.3v1.3c-4.9,0.3-8.8,4.4-8.8,9.4c0,5,3.9,9.1,8.8,9.4v1.3h1.3v-1.3c4.9-0.3,8.8-4.4,8.8-9.4C19.5,16.3,15.6,12.2,10.7,11.9z M13.3,24.4H6.7V23h6.6V24.4z M13.3,19.6H6.7v-1.4h6.6V19.6z',
				handleSize: '80%',
				handleStyle: {
					color: '#fff',
					shadowBlur: 3,
					shadowColor: 'rgba(0, 0, 0, 0.6)',
					shadowOffsetX: 2,
					shadowOffsetY: 2
				}
			}],
			series: [
				{
					name:'读取字节数',
					type:'line',
					smooth:true,
					symbol: 'none',
					sampling: 'average',
					itemStyle: { normal: { color: 'rgb(255, 70, 131)' } },
					data: rData
				},
				{
					name:'写入字节数',
					type:'line',
					smooth:true,
					symbol: 'none',
					sampling: 'average',
					itemStyle: { normal: { color: 'rgba(46, 165, 186, .7)'} },
					data: wData
				}
			]
		};
		myChartDisk.setOption(option);
		window.chartInstances['diskview'] = myChartDisk;
	},'json');
}

//网络Io
function network(b,e){
	$.get('/system/get_network_io?start='+b+'&end='+e,function(rdata){
		if (!document.getElementById('network')) return;
		var rdata = rdata.data;
		var myChartNetwork = echarts.init(document.getElementById('network'));
		var aData = [];
		var bData = [];
		var cData = [];
		var dData = [];
		var xData = [];
		var yData = [];
		var zData = [];
		
		for(var i = 0; i < rdata.length; i++){
			aData.push(rdata[i].total_up);
			bData.push(rdata[i].total_down);
			cData.push(rdata[i].down_packets);
			dData.push(rdata[i].up_packets);
			xData.push(rdata[i].addtime);
			yData.push(rdata[i].up);
			zData.push(rdata[i].down);
		}
		option = {
			grid: {
				bottom: 70
			},
			tooltip: {
				trigger: 'axis',
				axisPointer: { type: 'cross' },
				formatter:"时间：{b0}<br />{a0}: {c0} Kb/s<br />{a1}: {c1} Kb/s", 
			},
			legend: {
				data:[lan.index.net_up,lan.index.net_down]
			},
			xAxis: {
				type: 'category',
				boundaryGap: false,
				data: xData,
				axisLine:{ lineStyle:{ color:"#666" } }
			},
			yAxis: {
				type: 'value',
				name: '单位:KB/s',
				boundaryGap: [0, '100%'],
				splitLine:{ lineStyle:{ color:"#ddd" } },
				axisLine:{ lineStyle:{ color:"#666" } }
			},
			dataZoom: [{
				type: 'inside',
				start: 0,
				end: 100,
				zoomLock:true
			}, {
				start: 0,
				end: 100,
				bottom: 10,
				handleIcon: 'M10.7,11.9v-1.3H9.3v1.3c-4.9,0.3-8.8,4.4-8.8,9.4c0,5,3.9,9.1,8.8,9.4v1.3h1.3v-1.3c4.9-0.3,8.8-4.4,8.8-9.4C19.5,16.3,15.6,12.2,10.7,11.9z M13.3,24.4H6.7V23h6.6V24.4z M13.3,19.6H6.7v-1.4h6.6V19.6z',
				handleSize: '80%',
				handleStyle: {
					color: '#fff',
					shadowBlur: 3,
					shadowColor: 'rgba(0, 0, 0, 0.6)',
					shadowOffsetX: 2,
					shadowOffsetY: 2
				}
			}],
			series: [
				{
					name:lan.index.net_up,
					type:'line',
					smooth:true,
					symbol: 'none',
					sampling: 'average',
					itemStyle: { normal: { color: 'rgb(255, 140, 0)' } },
					data: yData
				},
				{
					name:lan.index.net_down,
					type:'line',
					smooth:true,
					symbol: 'none',
					sampling: 'average',
					itemStyle: { normal: { color: 'rgb(30, 144, 255)' } },
					data: zData
				}
			]
		};
		myChartNetwork.setOption(option);
		window.chartInstances['network'] = myChartNetwork;
	},'json');
}
//负载
function getload_old(b,e){
	$.get('/system/get_load_average?start='+b+'&end='+e,function(rdata){
		var rdata = data.data;
		var myChartgetload = echarts.init(document.getElementById('getloadview'));
		var aData = [];
		var bData = [];
		var xData = [];
		var yData = [];
		var zData = [];
		
		for(var i = 0; i < rdata.length; i++){
			xData.push(rdata[i].addtime);
			yData.push(rdata[i].pro);
			zData.push(rdata[i].one);
			aData.push(rdata[i].five);
			bData.push(rdata[i].fifteen);
		}
		option = {
			grid: {
				bottom: 70
			},
			tooltip: {
				trigger: 'axis'
			},
			calculable: true,
			legend: {
				data:['系统资源使用率','1分钟','5分钟','15分钟'],
				selectedMode: 'single',
			},
			xAxis: {
				type: 'category',
				boundaryGap: false,
				data: xData,
				axisLine:{
					lineStyle:{
						color:"#666"
					}
				}
			},
			yAxis: {
				type: 'value',
				name: '',
				boundaryGap: [0, '100%'],
				splitLine:{
					lineStyle:{
						color:"#ddd"
					}
				},
				axisLine:{
					lineStyle:{
						color:"#666"
					}
				}
			},
			dataZoom: [{
				type: 'inside',
				start: 0,
				end: 100,
				zoomLock:true
			}, {
				start: 0,
				end: 100,
				bottom: 10,
				handleIcon: 'M10.7,11.9v-1.3H9.3v1.3c-4.9,0.3-8.8,4.4-8.8,9.4c0,5,3.9,9.1,8.8,9.4v1.3h1.3v-1.3c4.9-0.3,8.8-4.4,8.8-9.4C19.5,16.3,15.6,12.2,10.7,11.9z M13.3,24.4H6.7V23h6.6V24.4z M13.3,19.6H6.7v-1.4h6.6V19.6z',
				handleSize: '80%',
				handleStyle: {
					color: '#fff',
					shadowBlur: 3,
					shadowColor: 'rgba(0, 0, 0, 0.6)',
					shadowOffsetX: 2,
					shadowOffsetY: 2
				}
			}],
			series: [
				{
					name:'系统资源使用率',
					type:'line',
					smooth:true,
					symbol: 'none',
					sampling: 'average',
					itemStyle: {
						normal: {
							color: 'rgb(255, 140, 0)'
						}
					},
					data: yData
				},
				{
					name:'1分钟',
					type:'line',
					smooth:true,
					symbol: 'none',
					sampling: 'average',
					itemStyle: {
						normal: {
							color: 'rgb(30, 144, 255)'
						}
					},
					data: zData
				},
				{
					name:'5分钟',
					type:'line',
					smooth:true,
					symbol: 'none',
					sampling: 'average',
					itemStyle: {
						normal: {
							color: 'rgb(0, 178, 45)'
						}
					},
					data: aData
				},
				{
					name:'15分钟',
					type:'line',
					smooth:true,
					symbol: 'none',
					sampling: 'average',
					itemStyle: {
						normal: {
							color: 'rgb(147, 38, 255)'
						}
					},
					data: bData
				}
			]
		};
		myChartgetload.setOption(option);
		window.addEventListener("resize",function(){
			myChartgetload.resize();
		});
	},'json');
}
//系统负载
function getload(b,e){
	$.get('/system/get_load_average?start='+b+'&end='+e,function(rdata){
		if (!document.getElementById('getload_resource_view')) return;
		var rdata = rdata.data;
		
		var myChartResource = echarts.init(document.getElementById('getload_resource_view'));
		var myChartAverage = echarts.init(document.getElementById('getload_average_view'));
		
		var aData = [], bData = [], xData = [], yData = [], zData = [];
		for(var i = 0; i < rdata.length; i++){
			xData.push(rdata[i].addtime);
			yData.push(rdata[i].pro);
			zData.push(rdata[i].one);
			aData.push(rdata[i].five);
			bData.push(rdata[i].fifteen);
		}

		// Resource View
		var optionResource = {
			tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
			grid: { top: 30, left: '10%', right: '5%', bottom: 70 },
			xAxis: { type: 'category', boundaryGap: false, data: xData, axisLine: { lineStyle: { color: '#666' } } },
			yAxis: { type: 'value', name: '资源使用率%', splitLine: { lineStyle: { color: '#ddd' } }, axisLine: { lineStyle: { color: '#666' } }, min: 0, max: 100 },
			dataZoom: [{
				type: 'inside', start: 0, end: 100, zoomLock:true
			}, {
				start: 0, end: 100, bottom: 10,
				handleIcon: 'M10.7,11.9v-1.3H9.3v1.3c-4.9,0.3-8.8,4.4-8.8,9.4c0,5,3.9,9.1,8.8,9.4v1.3h1.3v-1.3c4.9-0.3,8.8-4.4,8.8-9.4C19.5,16.3,15.6,12.2,10.7,11.9z M13.3,24.4H6.7V23h6.6V24.4z M13.3,19.6H6.7v-1.4h6.6V19.6z',
				handleSize: '80%', handleStyle: { color: '#fff', shadowBlur: 3, shadowColor: 'rgba(0, 0, 0, 0.6)', shadowOffsetX: 2, shadowOffsetY: 2 }
			}],
			series: [{ name: '资源使用率%', type: 'line', smooth: true, symbol: 'none', sampling: 'average', itemStyle: { normal: { color: 'rgb(255, 140, 0)' } }, areaStyle: { normal: { color: 'rgba(255, 140, 0, 0.2)' } }, data: yData }]
		};
		myChartResource.setOption(optionResource);
		window.chartInstances['getload_resource_view'] = myChartResource;

		// Average View
		var optionAverage = {
			tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
			legend: { data: ['1分钟', '5分钟', '15分钟'], top: 0, right: '5%' },
			grid: { top: 30, left: '10%', right: '5%', bottom: 70 },
			xAxis: { type: 'category', boundaryGap: false, data: xData, axisLine: { lineStyle: { color: '#666' } } },
			yAxis: { type: 'value', name: '负载详情', splitLine: { lineStyle: { color: '#ddd' } }, axisLine: { lineStyle: { color: '#666' } } },
			dataZoom: [{
				type: 'inside', start: 0, end: 100, zoomLock:true
			}, {
				start: 0, end: 100, bottom: 10,
				handleIcon: 'M10.7,11.9v-1.3H9.3v1.3c-4.9,0.3-8.8,4.4-8.8,9.4c0,5,3.9,9.1,8.8,9.4v1.3h1.3v-1.3c4.9-0.3,8.8-4.4,8.8-9.4C19.5,16.3,15.6,12.2,10.7,11.9z M13.3,24.4H6.7V23h6.6V24.4z M13.3,19.6H6.7v-1.4h6.6V19.6z',
				handleSize: '80%', handleStyle: { color: '#fff', shadowBlur: 3, shadowColor: 'rgba(0, 0, 0, 0.6)', shadowOffsetX: 2, shadowOffsetY: 2 }
			}],
			series: [
				{ name: '1分钟', type: 'line', smooth: true, symbol: 'none', sampling: 'average', itemStyle: { normal: { color: 'rgb(30, 144, 255)' } }, data: zData },
				{ name: '5分钟', type: 'line', smooth: true, symbol: 'none', sampling: 'average', itemStyle: { normal: { color: 'rgb(0, 178, 45)' } }, data: aData },
				{ name: '15分钟', type: 'line', smooth: true, symbol: 'none', sampling: 'average', itemStyle: { normal: { color: 'rgb(147, 38, 255)' } }, data: bData }
			]
		};
		myChartAverage.setOption(optionAverage);
		window.chartInstances['getload_average_view'] = myChartAverage;
	},'json');
}