var num = 0;
var g_orderby = 'last_run_time';
var g_order = 'desc';
//查看任务日志
function getLogs(id){

	var reqTimer = null;
	var reqCount = 0;

	var tips = layer.msg('正在获取,请稍候...',{icon:16,time:0,shade: [0.3, '#000']});
	var req_log_args = 'id='+id;
	function requestLogs(layerIndex){
    	var is_refresh = $("#log_refresh_switch").prop('checked');
    	if (reqCount > 0 && !is_refresh) return;

		$.post('/crontab/logs', req_log_args, function(rdata){

			if (reqCount == 0){
				layer.close(tips);
			}
			
			if(!rdata.status) {
				layer.close(layerIndex);
				layer.msg(rdata.msg,{icon:2, time:2000});
				clearInterval(reqTimer);
				return;
			};

			if (rdata.msg == ''){
				rdata.msg = '暂无数据!';
			}

			$("#crontab_log").html(rdata.msg);
			//滚动到最低
			var ob = document.getElementById('crontab_log');
            if (ob) ob.scrollTop = ob.scrollHeight; 
			reqCount++;
		},'json');

    }


	layer.open({
		type:1,
		title:"任务执行日志",
		area: ['60%','660px'], 
		shadeClose:false,
		btn:["清空日志", "关闭"],
		closeBtn:1,
		end: function(){
        	if (reqTimer){
        		clearInterval(reqTimer);
        	}
        },
		content:'<div class="setchmod bt-form" style="padding:15px;">'
			+'<div style="margin-bottom: 10px; height: 30px;">'
			+'<div class="pull-left" style="line-height: 30px;">'
			+'<label style="font-weight: normal; cursor: pointer; color: #666; user-select: none; margin-right: 15px;">'
			+'<input type="checkbox" id="log_refresh_switch" checked style="vertical-align: middle; margin-top: -2px; margin-right: 5px;">5秒定时刷新'
			+'</label>'
			+'<button class="btn btn-default btn-sm" onclick="startTask('+id+', true)">执行任务</button>'
			+'</div>'
			+'</div>'
			+'<pre id="crontab_log" style="overflow: auto; border: 0px none; line-height:23px;padding: 5px; margin: 0px; white-space: pre-wrap; height: 495px; background-color: rgb(51,51,51);color:#f1f1f1;border-radius:0px;font-family:"></pre>'
		+'</div>',
		success:function(layero, index){
	    	requestLogs(index);
	    	reqTimer = setInterval(function(){
	    		requestLogs(index);
	    	},5000);

	    	var btnRow = layero.find('.layui-layer-btn');
	    	btnRow.find('.layui-layer-btn0').css({'float':'left','margin-left':'15px','background-color':'#5cb85c','border-color':'#4cae4c','color':'#fff'});
        },

		yes:function(index, layero){
			closeLogs(id, true);
			return false;
		},
		btn2:function(index, layero){
			layer.close(index);
		},
	});
}


function getBackupName(hook_data, name){
	for (var i = 0; i < hook_data.length; i++) {
		if (hook_data[i]['name'] == name){
			return hook_data[i]['title'];
		}
	}
	return name;
}

function getCronData(page){
	var search = $('#search_task').val() || '';
	var load = layer.msg(lan.public.the,{icon:16,time:0,shade: [0.3, '#000']});
	$.post("/crontab/list?p="+page+'&search='+search+'&orderby='+g_orderby+'&order='+g_order,'', function(rdata){
		layer.close(load);
		setSortUI();
		var cbody = "";
		if(rdata.data.length == 0){
			cbody="<tr><td colspan='9' style='text-align: center;'>当前没有计划任务</td></tr>";
		} else {
			for(var i=0;i<rdata.data.length;i++){
				//状态
				var status = rdata.data[i]['status'] == '1' ?
				'<span class="btOpen" onclick="setTaskStatus(' + rdata.data[i].id + ',0)" style="color:rgb(92, 184, 92);cursor:pointer" title="停用该计划任务">正常<span class="glyphicon glyphicon-play"></span></span>' 
				:'<span onclick="setTaskStatus('+ rdata.data[i].id +',1)" class="btClose" style="color:red;cursor:pointer" title="启用该计划任务">停用<span style="color:rgb(255, 0, 0);" class="glyphicon glyphicon-pause"></span></span>';


				var cron_save = '--';
				if (rdata.data[i]['save'] != ''){
					cron_save = rdata.data[i]['save']+'份';
				}

				var cron_backupto = '-';
				if (rdata.data[i]['stype'] == 'site' || rdata.data[i]['stype']=='path' ||  rdata.data[i]['stype']=='database' || rdata.data[i]['stype'].indexOf('database_')>-1 ){
					cron_backupto = '本地磁盘';
					if (rdata.data[i]['backup_to'] != 'localhost'){
						cron_backupto = getBackupName(rdata['backup_hook'],rdata.data[i]['backup_to']);
					}
				}

				cbody += "<tr><td><input type='checkbox' onclick='checkSelect();' title='"+rdata.data[i].name+"' name='id' value='"+rdata.data[i].id+"'></td>\
					<td>"+rdata.data[i].name+"</td>\
					<td>"+status+"</td>\
					<td>"+rdata.data[i].type+"</td>\
					<td>"+rdata.data[i].cycle+"</td>\
					<td>"+cron_save +"</td>\
					<td>"+cron_backupto+"</td>\
					<td>"+(rdata.data[i].day_type_h == '无' ? '' : rdata.data[i].day_type_h)+"</td>\
					<td>"+rdata.data[i].last_run_time+"</td>\
					<td>\
						<a href=\"javascript:startTask("+rdata.data[i].id+");\" class='btlink'>执行</a> | \
						<a href=\"javascript:editTaskInfo('"+rdata.data[i].id+"');\" class='btlink'>编辑</a> | \
						<a href=\"javascript:getLogs("+rdata.data[i].id+");\" class='btlink'>日志</a> | \
						<a href=\"javascript:planDel("+rdata.data[i].id+" ,'"+rdata.data[i].name.replace('\\','\\\\').replace("'","\\'").replace('"','')+"');\" class='btlink'>删除</a>\
					</td>\
				</tr>";
			}
		}
		$('#cronbody').html(cbody);
		$('#softPage').html(rdata.page);
	},'json');
}

// 设置计划任务状态
function setTaskStatus(id,status){
	var confirm = layer.confirm(status == '0'?'计划任务暂停后将无法继续运行，您真的要停用这个计划任务吗？':'该计划任务已停用，是否要启用这个计划任务', {title:'提示',icon:3,closeBtn:1},function(index) {
		if (index > 0) {
			var loadT = layer.msg('正在设置状态，请稍后...',{icon:16,time:0,shade: [0.3, '#000']});
			$.post('/crontab/set_cron_status',{id:id},function(rdata){

				if (!rdata.status){
					layer.msg(rdata.msg,{icon:rdata.status?1:2});
					return;
				}

				showMsg(rdata.msg,function(){
					layer.close(loadT);
					layer.close(confirm);
					getCronData(1);
				},{icon:rdata.status?1:2},2000);

			},'json');
		}
	});
}

//执行任务脚本
function startTask(id, is_log_open){
	var loadT = layer.msg('正在处理,请稍候...',{icon:16,time:0,shade: [0.3, '#000']});
	var data='id='+id;
	$.post('/crontab/start_task',data,function(rdata){
		layer.close(loadT);
		if (rdata.status){
			if (!is_log_open) {
				getLogs(id);
			} else {
				$.post('/crontab/logs', 'id='+id, function(rdata){
					if(!rdata.status) return;
					$("#crontab_log").html(rdata.msg);
					var ob = document.getElementById('crontab_log');
		            if (ob) ob.scrollTop = ob.scrollHeight; 
				},'json');
			}
		} else {
			showMsg(rdata.msg, function(){
			},{icon:rdata.status?1:2,time:2000});
		}
	},'json');
}


//清空日志
function closeLogs(id, is_refresh){
	var loadT = layer.msg('正在处理,请稍候...',{icon:16,time:0,shade: [0.3, '#000']});
	var data='id='+id;
	$.post('/crontab/del_logs',data,function(rdata){
		layer.close(loadT);
		if (rdata.status && is_refresh){
			$("#crontab_log").html('暂无数据!');
		}
		showMsg(rdata.msg, function(){
			// layer.closeAll();
		},{icon:rdata.status?1:2,time:2000});
	},'json');
}


//删除
function planDel(id,name){
	safeMessage(lan.get('del',[name]),'您确定要删除该任务吗?',function(){
		var load = layer.msg('正在处理,请稍候...',{icon:16,time:0,shade: [0.3, '#000']});
		var data='id='+id;
		$.post('/crontab/del',data,function(rdata){
			showMsg(rdata.msg, function(){
				layer.closeAll();
				getCronData(1);
			},{icon:rdata.status?1:2,time:2000});
		},'json');
	});
}
	
function isURL(str_url){
	var strRegex = '^(https|http|ftp|rtsp|mms)?://.+';
	var re=new RegExp(strRegex);
	if (re.test(str_url)){
		return (true);
	}else{
		return (false);
	}
}


//提交
function planAdd(){
	var name = $(".planname input[name='name']").val();
	if(name == ''){
		$(".planname input[name='name']").focus();
		layer.msg('任务名称不能为空!',{icon:2});
		return;
	}
	$("#cronConfig input[name='name']").val(name);
	
	var time_type = $(".plancycle").find("b").attr("val");
	$("#cronConfig input[name='type']").val(time_type);

	
	var is1;
	var is2 = 1;
	switch(time_type){
		case 'day-n':
			is1=31;
			break;
		case 'hour-n':
			is1=23;
			break;
		case 'minute-n':
			is1=59;
			break;
		case 'month':
			is1=31;
			break;
	}
	
	var where1 = $('#excode_week b').attr('val');
	$("#cronConfig input[name='where1']").val(where1);

	if(where1 > is1 || where1 < is2){
		$("#ptime input[name='where1']").focus();
		layer.msg('表单不合法,请重新输入!',{icon:2});
		return;
	}
	
	var hour = $("#ptime input[name='hour']").val();
	if(hour > 23 || hour < 0){
		$("#ptime input[name='hour']").focus();
		layer.msg('小时值不合法!',{icon:2});
		return;
	}
	$("#cronConfig input[name='hour']").val(hour);
	var minute = $("#ptime input[name='minute']").val();
	if(minute > 59 || minute < 0){
		$("#ptime input[name='minute']").focus();
		layer.msg('分钟值不合法!',{icon:2});
		return;
	}
	$("#cronConfig input[name='minute']").val(minute);
	
	var save = $("#save").val();
	if(save < 0){
		layer.msg('不能有负数!',{icon:2});
		return;
	}
	
	$("#cronConfig input[name='save']").val(save);
	$("#cronConfig input[name='week']").val($(".planweek").find("b").attr("val"));

	var cron_type = $(".planjs").find("b").attr("val");
	var sBody = encodeURIComponent($("#implement textarea[name='sbody']").val());

	if (cron_type == 'toShell'){
		if(sBody == ''){
			$("#implement textarea[name='sbody']").focus();
			layer.msg('脚本代码不能为空!',{icon:2});
			return;
		}
	}

	if(cron_type == 'toFile'){
		if($("#viewfile").val() == ''){
			layer.msg('请选择脚本文件!',{icon:2});
			return;
		}
	}
	
	var url_address = $("#url_address").val();
	if(cron_type == 'toUrl'){
		if(!isURL(url_address)){
			layer.msg('URL地址不正确!',{icon:2});
			$("implement textarea[name='url_address']").focus();
			return;
		}
	}
	// url_address = encodeURIComponent(url_address);
	$("#cronConfig input[name='url_address']").val(url_address);
	$("#cronConfig input[name='stype']").val(cron_type);
	$("#cronConfig textarea[name='sbody']").val(decodeURIComponent(sBody));
	
	if(cron_type == 'site' || cron_type == 'database' || cron_type.indexOf('database_')>-1 || cron_type == 'path'){
		var backupTo = $(".planBackupTo").find("b").attr("val");
		$("#backup_to").val(backupTo);
	}

    var day_type = $("input[name='day_type_radio']:checked").val();
    $("#cronConfig input[name='day_type']").val(day_type);

	if (cron_type=='site' || cron_type=='path'){
		var attr = $("#exclude_dir textarea[name='exclude_dir']").val();
		$("#attr").val(attr);
	}
	
	var sname = $("#sname").attr("val");
	$("#cronConfig input[name='sname']").val(sname);

	// if(sName == 'backupAll'){
	// 	var alist = $("ul[aria-labelledby='backdata'] li a");
	// 	var dataList = new Array();
	// 	for(var i=1;i<alist.length;i++){
	// 		var tmp = alist[i].getAttribute('value');
	// 		dataList.push(tmp);
	// 	}
	// 	if(dataList.length < 1){
	// 		layer.msg('对象列表为空，无法继续!',{icon:5});
	// 		return;
	// 	}
	// 	allAddCrontab(dataList,0,'');
	// 	return;
	// }

	if (time_type == 'minute-n'){
		var where1 = $("#ptime input[name='where1']").val();
		$("#cronConfig input[name='where1']").val(where1);
	}

	if (time_type == 'day-n'){
		var where1 = $("#ptime input[name='where1']").val();
		$("#cronConfig input[name='where1']").val(where1);
	}

	if (time_type == 'hour-n'){
		var where1 = $("#ptime input[name='where1']").val();
		$("#cronConfig input[name='where1']").val(where1);
	}

	if (time_type == 'month'){
		var where1 = $("#ptime input[name='where1']").val();
		$("#cronConfig input[name='where1']").val(where1);
	}

	if (time_type == 'week'){
		var where1 = $("#ptime input[name='where1']").val();
		$("#cronConfig input[name='where1']").val(where1);
	}
	

	layer.msg('正在添加,请稍候...!',{icon:16,time:0,shade: [0.3, '#000']});
	var data = $("#cronConfig").serialize() + '&sbody='+sBody;
	// console.log(data);
	$.post('/crontab/add',data,function(rdata){
		if(!rdata.status) {
			layer.msg(rdata.msg,{icon:2, time:2000});
			return;
		}

		showMsg(rdata.msg, function(){
			layer.closeAll();
			getCronData(1);
		},{icon:rdata.status?1:2}, 2000);

	},'json');
}

initDropdownMenu();
function initDropdownMenu(){
	$(".dropdown ul li a").on('click', function(){
		$('#tag_exclude_dir').hide();
		var txt = $(this).text();
		var type = $(this).attr("value");
		$(this).parents(".dropdown").find("button b").text(txt).attr("val",type);
		switch(type){
			case 'day':
				closeOpt();
				toHour();
				toMinute();
				break;
			case 'day-n':
				closeOpt();
				toWhere1('天');
				toHour();
				toMinute();
				break;
			case 'hour':
				closeOpt();
				toMinute();
				break;
			case 'hour-n':
				closeOpt();
				toWhere1('小时');
				toMinute();
				break;
			case 'minute-n':
				closeOpt();
				toWhere1('分钟');
				break;
			case 'week':
				closeOpt();
				toWeek();
				toHour();
				toMinute();
				break;
			case 'month':
				closeOpt();
				toWhere1('日');
				toHour();
				toMinute();
				break;
			case 'toFile':
				toFile();
				break;
			case 'toShell':
				toShell();
				$(".controls").html('脚本内容');
				break;
			case 'rememory':
				rememory();
				$(".controls").html('提示');
				break;
			case 'site':
				toBackup('sites');
				$('#tag_exclude_dir').show();
				$(".controls").html('备份网站');
				break;
			case 'path':
				$('#tag_exclude_dir').show();
				toBackup('path');
				$(".controls").html('备份目录');
				break;
			case 'database_mariadb':
			case 'database_mongodb':
			case 'database_postgresql':
			case 'database_mysql-apt':
			case 'database_mysql-yum':
			case 'database':
				toBackup(type);
				$(".controls").html('备份数据库');
				break;
			case 'logs':
				toLogsHtml('logs');
				$(".controls").html('切割网站');
				break;
			case 'toUrl':
				toUrl();
				$(".controls").html('URL地址');
				break;
		}
	});
}


//备份
function toLogsHtml(type){
	var sMsg = "";
	switch(type){
		case 'sites':
			sMsg = '备份网站';
			sType = "sites";
			break;
		case 'database_mariadb':
		case 'database_mongodb':
		case 'database_postgresql':
		case 'database_mysql-apt':
		case 'database_mysql-yum':
		case 'database':
			sMsg = '备份数据库';
			suffix = type.replace('database','')
			if (suffix != ''){
				suffix = suffix.replace('_','')
				sMsg = '备份数据库['+suffix+']';
			}
			sType = type;
			break;
		case 'logs':
			sMsg = '切割日志';
			sType = "logs";
			break;
		case 'path':
			sMsg = '备份目录';
			sType = "path";
			break;
	}
	var data = 'type='+sType;

	$.post('/crontab/get_data_list',data,function(rdata){
		$(".planname input[name='name']").attr('readonly','true').css({"background-color":"#f6f6f6","color":"#666"});
		var sOpt = "";
		if(rdata.data.length == 0){
			layer.msg(lan.public.list_empty,{icon:2})
			return;
		}

		for(var i=0;i<rdata.data.length;i++){
			if(i==0){
				$(".planname input[name='name']").val(sMsg+'['+rdata.data[i].name+']');
			}
			sOpt += '<li><a role="menuitem" tabindex="-1" href="javascript:;" value="'+rdata.data[i].name+'">'+rdata.data[i].name+'['+rdata.data[i].ps+']</a></li>';			
		}

		
		if (sType != 'path'){
			sOpt = '<li><a role="menuitem" tabindex="-1" href="javascript:;" value="ALL">所有</a></li>' + sOpt;
		}
		
		var orderOpt = '';
		for (var i=0;i<rdata.orderOpt.length;i++){
			orderOpt += '<li><a role="menuitem" tabindex="-1" href="javascript:;" value="'+rdata.orderOpt[i].name+'">'+rdata.orderOpt[i].title+'</a></li>'
		}
		
		
		var changeDir = '';
		if (sType == 'path'){
			changeDir = '<span class="glyphicon glyphicon-folder-open cursor mr20 changePathDir" style="float:left;line-height: 30px;"></span>';
		}

		var sBody = '<div class="dropdown pull-left mr20 check">\
					  <button class="btn btn-default dropdown-toggle sname" type="button" id="backdata" data-toggle="dropdown" style="width:auto">\
						<b id="sname" val="'+rdata.data[0].name+'">'+rdata.data[0].name+'['+rdata.data[0].ps+']</b> <span class="caret"></span>\
					  </button>\
					  <ul class="dropdown-menu" role="menu" aria-labelledby="backdata">'+sOpt+'</ul>\
					</div>\
					'+ changeDir +'\
					</div>\
					<div class="textname pull-left mr20">保留最新</div><div class="plan_hms pull-left mr20 bt-input-text">\
					<span><input type="number" name="save" id="save" value="3" maxlength="4" max="100" min="1"></span>\
					<span class="name">份</span>\
					</div>';
		$("#implement").html(sBody);
		getselectname();

		$('.changePathDir').on('click', function(){
			changePathCallback($('#sname').val(),function(select_dir){
				$(".planname input[name='name']").val('备份目录['+select_dir+']');
				$('#implement .sname b').attr('val',select_dir).text(select_dir);
			});
		});


		$(".dropdown ul li a").on('click', function(){
			var sname = $("#sname").attr("val");
			if(!sname) return;
			$(".planname input[name='name']").val(sMsg+'['+sname+']');
		});
	},'json');

}

//备份
function toBackup(type){
	var sMsg = "";
	switch(type){
		case 'sites':
			sMsg = '备份网站';
			sType = "sites";
			break;
		case 'database_mariadb':
		case 'database_mongodb':
		case 'database_postgresql':
		case 'database_mysql-apt':
		case 'database_mysql-yum':
		case 'database':
			sMsg = '备份数据库';
			suffix = type.replace('database','')
			if (suffix != ''){
				suffix = suffix.replace('_','')
				sMsg = '备份数据库['+suffix+']';
			}
			sType = type;
			break;
		case 'logs':
			sMsg = '切割日志';
			sType = "logs";
			break;
		case 'path':
			sMsg = '备份目录';
			sType = "path";
			break;
	}
	var data = 'type='+sType;

	$.post('/crontab/get_data_list',data,function(rdata){
		$(".planname input[name='name']").css({"background-color":"#f6f6f6","color":"#666"});
		var sOpt = "";
		if(rdata.data.length == 0){
			layer.msg(lan.public.list_empty,{icon:2})
			return;
		}

		for(var i=0;i<rdata.data.length;i++){
			if(i==0){
				$(".planname input[name='name']").val(sMsg+'['+rdata.data[i].name+']');
			}
			sOpt += '<li><a role="menuitem" tabindex="-1" href="javascript:;" value="'+rdata.data[i].name+'">'+rdata.data[i].name+'['+rdata.data[i].ps+']</a></li>';			
		}

		
		if (sType != 'path'){
			sOpt = '<li><a role="menuitem" tabindex="-1" href="javascript:;" value="ALL">所有</a></li>' + sOpt;
		}
		
		var orderOpt = '';
		for (var i=0;i<rdata.orderOpt.length;i++){
			orderOpt += '<li><a role="menuitem" tabindex="-1" href="javascript:;" value="'+rdata.orderOpt[i].name+'">'+rdata.orderOpt[i].title+'</a></li>'
		}
		
		
		var changeDir = '';
		if (sType == 'path'){
			changeDir = '<span class="glyphicon glyphicon-folder-open cursor mr20 changePathDir" style="float:left;line-height: 30px;"></span>';
		}

		var sBody = '<div class="dropdown pull-left mr20 check">\
		 	<button class="btn btn-default dropdown-toggle sname" type="button" id="backdata" data-toggle="dropdown" style="width:auto">\
				<b id="sname" val="'+rdata.data[0].name+'">'+rdata.data[0].name+'['+rdata.data[0].ps+']</b> <span class="caret"></span>\
		  	</button>\
		 	<ul class="dropdown-menu" role="menu" aria-labelledby="backdata">'+sOpt+'</ul>\
		</div>\
		'+ changeDir +'\
		<div class="textname pull-left mr20">备份到</div>\
		<div class="dropdown planBackupTo pull-left mr20">\
		  	<button class="btn btn-default dropdown-toggle" type="button" id="excode" data-toggle="dropdown" style="width:auto;">\
				<b val="localhost">服务器磁盘</b><span class="caret"></span>\
		  	</button>\
		  	<ul class="dropdown-menu" role="menu" aria-labelledby="excode">\
				<li><a role="menuitem" tabindex="-1" href="javascript:;" value="localhost">服务器磁盘</a></li>\
				'+ orderOpt +'\
		  	</ul>\
		</div>\
		<div class="textname pull-left mr20">保留最新</div><div class="plan_hms pull-left mr20 bt-input-text">\
			<span><input type="number" name="save" id="save" value="3" maxlength="4" max="100" min="1"></span>\
			<span class="name">份</span>\
		</div>';
		$("#implement").html(sBody);
		getselectname();

		$('.changePathDir').on('click', function(){
			changePathCallback($('#sname').val(),function(select_dir){
				$(".planname input[name='name']").val('备份目录['+select_dir+']');
				$('#implement .sname b').attr('val',select_dir).text(select_dir);
			});
		});


		$(".dropdown ul li a").on('click', function(){
			var sname = $("#sname").attr("val");
			if(!sname) return;
			$(".planname input[name='name']").val(sMsg+'['+sname+']');
		});
	},'json');

}


// 编辑计划任务
function editTaskInfo(id){
	layer.msg('正在获取,请稍候...',{icon:16,time:0,shade: [0.3, '#000']});
	$.post('/crontab/get_crond_find',{id:id},function(rdata){
		layer.closeAll();
		// console.log('get_crond_find:', rdata);
		var sTypeName = '',sTypeDom = '',cycleName = '',cycleDom = '',weekName = '',weekDom = '',sNameName ='',sNameDom = '',backupsName = '',backupsDom ='';
		obj = {
			from:{
				id:rdata.id,
				name: rdata.name,
				type: rdata['type'],
				stype: rdata.stype,
				where1: rdata.where1,
				hour: rdata.where_hour,
				minute: rdata.where_minute,
				week: rdata.where1,
				sbody: rdata.sbody,
				sname: rdata.sname,
				backup_to: rdata.backup_to,
				save: rdata.save,
				url_address: rdata.url_address,
				attr:rdata.attr,
                day_type: rdata.day_type,
			},
			sTypeArray:[['toShell','Shell脚本'],['site','备份网站'],['database','备份数据库'],['logs','日志切割'],['path','备份目录'],['rememory','释放内存'],['toUrl','访问URL']],
			cycleArray:[['day','每天'],['day-n','N天'],['hour','每小时'],['hour-n','N小时'],['minute-n','N分钟'],['week','每星期'],['month','每月']],
			weekArray:[[1,'周一'],[2,'周二'],[3,'周三'],[4,'周四'],[5,'周五'],[6,'周六'],[7,'周日']],
			sNameArray:[],
			backupsArray:[],
			create:function(callback){
				if (obj.from['stype'].indexOf('database_')>-1){
					name = obj.from['stype'].replace('database_','');
					sTypeName = '备份数据库['+name+']';
					sTypeDom += '<li><a role="menuitem"  href="javascript:;" value="'+ obj.from['stype'] +'">'+ sTypeName +'</a></li>';
				} else {
					for(var i = 0; i <obj['sTypeArray'].length; i++){
						if(obj.from['stype'] == obj['sTypeArray'][i][0]){
							sTypeName  = obj['sTypeArray'][i][1];
						}
						sTypeDom += '<li><a role="menuitem"  href="javascript:;" value="'+ obj['sTypeArray'][i][0] +'">'+ obj['sTypeArray'][i][1] +'</a></li>';
					}
				}

				for(var i = 0; i <obj['cycleArray'].length; i++){
					if(obj.from['type'] == obj['cycleArray'][i][0])  cycleName  = obj['cycleArray'][i][1];
					cycleDom += '<li><a role="menuitem"  href="javascript:;" value="'+ obj['cycleArray'][i][0] +'">'+ obj['cycleArray'][i][1] +'</a></li>';
				}

				for(var i = 0; i <obj['weekArray'].length; i++){
					if(obj.from['week'] == obj['weekArray'][i][0])  weekName  = obj['weekArray'][i][1];
					weekDom += '<li><a role="menuitem"  href="javascript:;" value="'+ obj['weekArray'][i][0] +'">'+ obj['weekArray'][i][1] +'</a></li>';
				}

				if(obj.from.stype == 'site' || obj.from.stype == 'database' || obj.from.stype == 'path' || obj.from.stype == 'logs' || obj.from['stype'].indexOf('database_')>-1){
					$.post('/crontab/get_data_list',{type:obj.from.stype},function(rdata){
						// console.log(rdata);
						obj.sNameArray = rdata.data;
						obj.sNameArray.unshift({name:'ALL',ps:'所有'});
						obj.backupsArray = rdata.orderOpt;
						obj.backupsArray.unshift({title:'服务器磁盘',name:'localhost'});
						for(var i = 0; i <obj['sNameArray'].length; i++){
							if(obj.from['sname'] == obj['sNameArray'][i]['name']){
								sNameName  = obj['sNameArray'][i]['ps'];
							}
							sNameDom += '<li><a role="menuitem"  href="javascript:;" value="'+ obj['sNameArray'][i]['name'] +'">'+ obj['sNameArray'][i]['ps'] +'</a></li>';
						}
						for(var i = 0; i <obj['backupsArray'].length; i++){
							if(obj.from['backup_to'] == obj['backupsArray'][i]['name'])  {
								backupsName  = obj['backupsArray'][i]['title'];
							}
							backupsDom += '<li><a role="menuitem"  href="javascript:;" value="'+ obj['backupsArray'][i]['name'] +'">'+ obj['backupsArray'][i]['title'] +'</a></li>';
						}
						callback();
					},'json');
				}else{
					callback();
				}
			}
		};
		obj.create(function(){

			var changeDir = '';
			if (obj.from.stype == 'path'){
				changeDir = '<span class="glyphicon glyphicon-folder-open cursor mr20 changePathDir" style="float:left;line-height: 30px;"></span>';
			}

			var exclude_dirs_placeholder = "每行一条规则,目录不能以/结尾，示例:\r\n.git \
\r\nstatic/upload \
\r\n*.log";
			layer.open({
				type:1,
				title:'编辑计划任务-['+rdata.name+']',
				area: ['900px','640px'], 
				skin:'layer-create-content',
				shadeClose:false,
				closeBtn:1,
				content:'<div class="setting-con ptb20">\
					<div class="clearfix plan ptb10">\
						<span class="typename c4 pull-left f14 text-right mr20">任务类型</span>\
						<div class="dropdown stype_list pull-left mr20">\
							<button class="btn btn-default dropdown-toggle" type="button" id="excode" data-toggle="dropdown" style="width:auto" disabled="disabled">\
								<b val="'+ obj.from.type +'">'+ sTypeName +'</b>\
								<span class="caret"></span>\
							</button>\
							<ul class="dropdown-menu" role="menu" aria-labelledby="sType">'+ sTypeDom +'</ul>\
						</div>\
					</div>\
					<div class="clearfix plan ptb10">\
						<span class="typename c4 pull-left f14 text-right mr20">任务名称</span>\
						<div class="planname pull-left"><input type="text" name="name" class="bt-input-text sname_create" value="'+ obj.from.name +'"></div>\
					</div>\
					<div class="clearfix plan ptb10">\
						<span class="typename c4 pull-left f14 text-right mr20">执行周期</span>\
						<div class="dropdown  pull-left mr20">\
							<button class="btn btn-default dropdown-toggle cycle_btn" type="button" data-toggle="dropdown" style="width:94px">\
								<b val="'+ obj.from.stype +'">'+ cycleName +'</b>\
								<span class="caret"></span>\
							</button>\
							<ul class="dropdown-menu" role="menu" aria-labelledby="cycle">'+ cycleDom +'</ul>\
						</div>\
						<div class="pull-left optional_week">\
							<div class="dropdown week_btn pull-left mr20" style="display:'+ (obj.from.type == "week"  ?'block;':'none') +'">\
								<button class="btn btn-default dropdown-toggle" type="button" data-toggle="dropdown" >\
									<b val="'+ obj.from.week +'">'+ weekName +'</b> \
									<span class="caret"></span>\
								</button>\
								<ul class="dropdown-menu" role="menu" aria-labelledby="week">'+ weekDom +'</ul>\
							</div>\
							<div class="plan_hms pull-left mr20 bt-input-text where1_input" style="display:'+ (obj.from.type == "day-n" || obj.from.type == 'month' ?'block;':'none') +'"><span><input type="number" name="where1" class="where1_create" value="'+obj.from.where1 +'" maxlength="2" max="23" min="0"></span> <span class="name">日</span> </div>\
							<div class="plan_hms pull-left mr20 bt-input-text hour_input" style="display:'+ (obj.from.type == "day" || obj.from.type == 'day-n' || obj.from.type == 'hour-n' || obj.from.type == 'week' || obj.from.type == 'month'?'block;':'none') +'"><span><input type="number" name="hour" class="hour_create" value="'+ ( obj.from.type == 'hour-n' ? obj.from.where1 : obj.from.hour ) +'" maxlength="2" max="23" min="0"></span> <span class="name">时</span> </div>\
							<div class="plan_hms pull-left mr20 bt-input-text minute_input"><span><input type="number" name="minute" class="minute_create" value="'+ (obj.from.type == 'minute-n' ? obj.from.where1 : obj.from.minute)+'" maxlength="2" max="59" min="0"></span> <span class="name">分</span> </div>\
						</div>\
					</div>\
                    <div class="clearfix plan ptb10">\
                        <span class="typename c4 pull-left f14 text-right mr20">日期限制</span>\
                        <div class="pull-left" style="line-height:34px">\
                            <label class="mr20" style="font-weight:normal;cursor:pointer"><input type="radio" name="day_type_radio_edit" value="0" ' + (obj.from.day_type == 0 ? 'checked' : '') + ' style="width:16px;height:16px;vertical-align:middle;margin-top:-2px"> 无</label>\
                            <label class="mr20" style="font-weight:normal;cursor:pointer"><input type="radio" name="day_type_radio_edit" value="1" ' + (obj.from.day_type == 1 ? 'checked' : '') + ' style="width:16px;height:16px;vertical-align:middle;margin-top:-2px"> 股票开盘日</label>\
                            <label class="mr20" style="font-weight:normal;cursor:pointer"><input type="radio" name="day_type_radio_edit" value="2" ' + (obj.from.day_type == 2 ? 'checked' : '') + ' style="width:16px;height:16px;vertical-align:middle;margin-top:-2px"> 工作日</label>\
                            <label class="mr20" style="font-weight:normal;cursor:pointer"><input type="radio" name="day_type_radio_edit" value="3" ' + (obj.from.day_type == 3 ? 'checked' : '') + ' style="width:16px;height:16px;vertical-align:middle;margin-top:-2px"> 节假日</label>\
                        </div>\
                    </div>\
					<div class="clearfix plan ptb10 site_list" style="display:none">\
						<span class="typename controls c4 pull-left f14 text-right mr20">'+ sTypeName  +'</span>\
						<div style="line-height:34px"><div class="dropdown pull-left mr20 sName_btn" style="display:'+ (obj.from.sType != "path"?'block;':'none') +'">\
							<button class="btn btn-default dropdown-toggle sname" type="button"  data-toggle="dropdown" style="width:auto" disabled="disabled">\
								<b id="sName" val="'+ obj.from.sname +'">'+ obj.from.sname +'</b>\
								<span class="caret"></span>\
							</button>\
							<ul class="dropdown-menu" role="menu" aria-labelledby="sName">'+ sNameDom +'</ul>\
						</div>\
						<div class="info-r" style="float: left;margin-right: 25px;display:'+ (obj.from.sType == "path"?'block;':'none') +'">\
							<input id="inputPath" class="bt-input-text mr5 " type="text" name="path" value="'+ obj.from.sName +'" placeholder="备份目录" style="width:208px;height:33px;" disabled="disabled">\
						</div>\
						'+changeDir+'\
						<div class="textname pull-left mr20">备份到</div>\
							<div class="dropdown  pull-left mr20">\
								<button class="btn btn-default dropdown-toggle backup_btn" type="button"  data-toggle="dropdown" style="width:auto;">\
									<b val="'+ obj.from.backup_to +'">'+ backupsName +'</b>\
									<span class="caret"></span>\
								</button>\
								<ul class="dropdown-menu" role="menu" aria-labelledby="backupTo">'+ backupsDom +'</ul>\
							</div>\
							<div class="textname pull-left mr20">保留最新</div>\
							<div class="plan_hms pull-left mr20 bt-input-text">\
								<span><input type="number" name="save" class="save_create" value="'+ obj.from.save +'" maxlength="4" max="100" min="1"></span><span class="name">份</span>\
							</div>\
						</div>\
					</div>\
					<div class="clearfix plan ptb10"  style="display:'+ (obj.from.stype == "toShell"?'block;':'none') +'">\
						<span class="typename controls c4 pull-left f14 text-right mr20">脚本内容</span>\
						<div style="line-height:34px"><textarea class="txtsjs bt-input-text sbody_create" name="sbody">'+ obj.from.sbody +'</textarea></div>\
					</div>\
					<div class="clearfix plan ptb10"  style="display:'+ ((obj.from.stype == "path"||obj.from.stype == "site")?'block;':'none') +'">\
						<span class="typename exclude_dir c4 pull-left f14 text-right mr20">排除目录</span>\
						<div style="line-height:34px"><textarea class="txtsjs bt-input-text attr_create" name="exclude_dir" placeholder="'+exclude_dirs_placeholder+'">'+ obj.from.attr +'</textarea></div>\
					</div>\
					<div class="clearfix plan ptb10" style="display:'+ (obj.from.stype == "rememory"?'block;':'none') +'">\
						<span class="typename controls c4 pull-left f14 text-right mr20">提示</span>\
						<div style="line-height:34px">释放PHP、MYSQL、PURE-FTPD、OpenResty的内存占用,建议在每天半夜执行!</div>\
					</div>\
					<div class="clearfix plan ptb10" style="display:'+ (obj.from.stype == "toUrl"?'block;':'none') +'">\
						<span class="typename controls c4 pull-left f14 text-right mr20">URL地址</span>\
						<div style="line-height:34px"><input type="text" style="width:400px; height:34px" class="bt-input-text url_create" name="url_address"  placeholder="URL地址" value="'+ obj.from.url_address +'"></div>\
					</div>\
					<div class="clearfix plan ptb10">\
						<div class="bt-submit plan-submits " style="margin-left: 141px;">保存编辑</div>\
					</div>\
				</div>',

				success:function(){

					$('.changePathDir').on('click', function(){
						changePathCallback($('#sName').val(),function(select_dir){
							$('input[name="name"]').val('备份目录['+select_dir+']');
							$('.sName_btn .sname b').attr('val',select_dir).text(select_dir);
							obj.from.sname = select_dir;
						});
					});
					
					if(obj.from.stype == 'toShell'){
						$('.site_list').hide();
					} else if (obj.from.stype == 'rememory') {
						$('.site_list').hide();
					} else if ( obj.from.stype == 'toUrl'){
						$('.site_list').hide();
					} else {
						$('.site_list').show();
					}

					obj.from.minute = $('.minute_create').val();
					obj.from.hour = $('.hour_create').val();
					obj.from.where1 = $('.where1_create').val();

					$('.sname_create').on('blur', function () {
						obj.from.name = $(this).val();
					});
					$('.where1_create').on('blur', function () {
						obj.from.where1 = $(this).val();
					});
		
					$('.hour_create').on('blur', function () {
						obj.from.hour = $(this).val();
					});
		
					$('.minute_create').on('blur', function () {
						obj.from.minute = $(this).val();
					});
		
					$('.save_create').on('blur', function () {
						obj.from.save = $(this).val();
					});
		
					$('.sbody_create').on('blur', function () {
						obj.from.sbody = $(this).val();
					});

					$('.attr_create').on('blur', function () {
						obj.from.attr = $(this).val();
					});

					
					$('.url_create').on('blur', function () {
						obj.from.url_address = $(this).val();
					});

                    $("input[name='day_type_radio_edit']").on('change', function() {
                        obj.from.day_type = $(this).val();
                    });
		
					$('[aria-labelledby="cycle"] a').off().on('click', function () {
						$('.cycle_btn').find('b').attr('val',$(this).attr('value')).html($(this).html());
						var type = $(this).attr('value');
						switch(type){
							case 'day':
								$('.week_btn').hide();
								$('.where1_input').hide();
								$('.hour_input').show().find('input').val('1');
								$('.minute_input').show().find('input').val('30');
								obj.from.week = '';
								obj.from.type = '';
								obj.from.hour = 1;
								obj.from.minute = 30;
							break;
							case 'day-n':
								$('.week_btn').hide();
								$('.where1_input').show().find('input').val('1');
								$('.hour_input').show().find('input').val('1');
								$('.minute_input').show().find('input').val('30');
								obj.from.week = '';
								obj.from.where1 = 1;
								obj.from.hour = 1;
								obj.from.minute = 30;
							break;
							case 'hour':
								$('.week_btn').hide();
								$('.where1_input').hide();
								$('.hour_input').hide();
								$('.minute_input').show().find('input').val('30');
								obj.from.week = '';
								obj.from.where1 = '';
								obj.from.hour = '';
								obj.from.minute = 30;
							break;
							case 'hour-n':
								$('.week_btn').hide();
								$('.where1_input').hide();
								$('.hour_input').show().find('input').val('1');
								$('.minute_input').show().find('input').val('30');
								obj.from.week = '';
								obj.from.where1 = '';
								obj.from.hour = 1;
								obj.from.minute = 30;
							break;
							case 'minute-n':
								$('.week_btn').hide();
								$('.where1_input').hide();
								$('.hour_input').hide();
								$('.minute_input').show();
								obj.from.week = '';
								obj.from.where1 = '';
								obj.from.hour = '';
								obj.from.minute = 30;
								console.log(obj.from);
							break;
							case 'week':
								$('.week_btn').show();
								$('.where1_input').hide();
								$('.hour_input').show();
								$('.minute_input').show();
								obj.from.week = 1;
								obj.from.where1 = '';
								obj.from.hour = 1;
								obj.from.minute = 30;
							break;
							case 'month':
								$('.week_btn').hide();
								$('.where1_input').show();
								$('.hour_input').show();
								$('.minute_input').show();
								obj.from.week = '';
								obj.from.where1 = 1;
								obj.from.hour = 1;
								obj.from.minute = 30;
							break;
						}
						obj.from.type = $(this).attr('value');
					});
		
					$('[aria-labelledby="week"] a').off().on('click', function () {
						$('.week_btn').find('b').attr('val',$(this).attr('value')).html($(this).html());
						obj.from.week = $(this).attr('value');
					});
		
					$('[aria-labelledby="backupTo"] a').off().on('click', function () {
						$('.backup_btn').find('b').attr('val',$(this).attr('value')).html($(this).html());
						obj.from.backup_to = $(this).attr('value');
					});
					$('.plan-submits').off().on('click', function(){
						if(obj.from.type == 'hour-n'){
							obj.from.where1 = obj.from.hour;
							obj.from.hour = '';
						} else if(obj.from.type == 'minute-n') {
							obj.from.where1 = obj.from.minute;
							obj.from.minute = '';
						} else if(obj.from.type == 'week') {
							obj.from.where1 = obj.from.week;
						}
						var loadT = layer.msg('正在保存编辑内容，请稍后...',{icon:16,time:0,shade: [0.3, '#000']});
						$.post('/crontab/modify_crond',obj.from,function(rdata){

							if (!rdata.status){
								layer.msg(rdata.msg,{icon:rdata.status?1:2});
								return;
							}

							showMsg(rdata.msg, function(){
								layer.closeAll();
								getCronData(1);
								initDropdownMenu();
							},{icon:rdata.status?1:2}, 2000);

						},'json');
					});
				}
				,cancel: function(){ 
				    initDropdownMenu();
				}
			});
		});
	},'json');
}


//下拉菜单名称
function getselectname(){
	$(".dropdown ul li a").on('click', function(){
		var txt = $(this).text();
		var type = $(this).attr("value");
		$(this).parents(".dropdown").find("button b").text(txt).attr("val",type);
	});
}
//清理
function closeOpt(){
	$("#ptime").html('');
}
//星期
function toWeek(){
	var mBody = '<div class="dropdown planweek pull-left mr20">\
	 	<button class="btn btn-default dropdown-toggle" type="button" id="excode_week" data-toggle="dropdown">\
			<b val="1">周一</b> <span class="caret"></span>\
	  	</button>\
	  	<ul class="dropdown-menu" role="menu" aria-labelledby="excode_week">\
			<li><a role="menuitem" tabindex="-1" href="javascript:;" value="1">周一</a></li>\
			<li><a role="menuitem" tabindex="-1" href="javascript:;" value="2">周二</a></li>\
			<li><a role="menuitem" tabindex="-1" href="javascript:;" value="3">周三</a></li>\
			<li><a role="menuitem" tabindex="-1" href="javascript:;" value="4">周四</a></li>\
			<li><a role="menuitem" tabindex="-1" href="javascript:;" value="5">周五</a></li>\
			<li><a role="menuitem" tabindex="-1" href="javascript:;" value="6">周六</a></li>\
			<li><a role="menuitem" tabindex="-1" href="javascript:;" value="0">周日</a></li>\
	 	</ul>\
	</div>';
	$("#ptime").html(mBody);
	getselectname();
}
//指定1
function toWhere1(ix){
	var mBody ='<div class="plan_hms pull-left mr20 bt-input-text">\
		<span><input type="number" name="where1" value="3" maxlength="2" max="31" min="0"></span>\
		<span class="name">'+ix+'</span>\
	</div>';
	$("#ptime").append(mBody);
}
//小时
function toHour(){
	var mBody = '<div class="plan_hms pull-left mr20 bt-input-text">\
		<span><input type="number" name="hour" value="1" maxlength="2" max="23" min="0"></span>\
		<span class="name">小时</span>\
	</div>';
	$("#ptime").append(mBody);
}

//分钟
function toMinute(){
	var mBody = '<div class="plan_hms pull-left mr20 bt-input-text">\
		<span><input type="number" name="minute" value="30" maxlength="2" max="59" min="0"></span>\
		<span class="name">分钟</span>\
	</div>';
	$("#ptime").append(mBody);
	
}

//从文件
function toFile(){
	var tBody = '<input type="text" value="" name="file" id="viewfile" onclick="fileupload()" readonly="true">\
		<button class="btn btn-default" onclick="fileupload()">上次</button>';
	$("#implement").html(tBody);
	$(".planname input[name='name']").removeAttr('readonly style').val("");
}

//从脚本
function toShell(){
	var tBody = "<textarea class='txtsjs bt-input-text' name='sbody'></textarea>";
	$("#implement").html(tBody);
	$(".planname input[name='name']").removeAttr('readonly style').val("");
}

//从脚本
function toUrl(){
	var tBody = "<input type='text' style='width:400px; height:34px' class='bt-input-text' name='url_address' id='url_address' placeholder='"+lan.crontab.url_address+"' value='http://' />";
	$("#implement").html(tBody);
	$(".planname input[name='name']").removeAttr('readonly style').val("");
}

//释放内存
function rememory(){
	$(".planname input[name='name']").removeAttr('readonly style').val("");
	$(".planname input[name='name']").val('释放内存');
	$("#implement").html('释放PHP、MYSQL、PURE-FTPD、APACHE、NGINX的内存占用,建议在每天半夜执行!');
	return;
}
//上传
function fileupload(){
	$("#sFile").on('change', function(){
		$("#viewfile").val($("#sFile").val());
	});
	$("#sFile").click();
}

// 显示添加计划任务模态框
function showAddTask() {
    var index = layer.open({
        type: 1,
        title: '添加计划任务',
        area: ['900px', '600px'],
        skin: 'layer-create-content',
        shadeClose: false,
        closeBtn: 1,
        content: $('#add_task_form_box'),
        btn: ['提交', '取消'],
        success: function(layero, index) {
            $('#add_task_form_box').show();
            // 重置一下状态
            toShell(); 
            initDropdownMenu();
        },
        yes: function(index, layero) {
            planAdd();
        },
        cancel: function() {
            $('#add_task_form_box').hide().appendTo('body');
        },
        end: function() {
             $('#add_task_form_box').hide().appendTo('body');
        }
    });
}

// 切换排序
function getCronSort(name) {
    if (g_orderby == name) {
        g_order = (g_order == 'asc' ? 'desc' : 'asc');
    } else {
        g_orderby = name;
        g_order = 'desc';
    }
    getCronData(1);
}

// 导出计划任务
function exportTasks() {
    var load = layer.msg('正在准备导出数据...', { icon: 16, time: 0, shade: [0.3, '#000'] });
    $.post("/crontab/list?p=1&limit=1000", '', function(rdata) {
        layer.close(load);
        if (!rdata.data || rdata.data.length == 0) {
            layer.msg('没有可导出的任务', { icon: 2 });
            return;
        }
        
        var exportData = [];
        for (var i = 0; i < rdata.data.length; i++) {
            var item = rdata.data[i];
            var task = {
                name: item.name,
                type: item.type_raw,
                where1: item.where1,
                hour: item.where_hour,
                minute: item.where_minute,
                save: item.save,
                backup_to: item.backup_to,
                stype: item.stype,
                sname: item.sname,
                sbody: item.sbody,
                url_address: item.url_address,
                attr: item.attr,
                day_type: item.day_type
            };
            exportData.push(task);
        }
        
        var blob = new Blob([JSON.stringify(exportData, null, 4)], {type: "application/json"});
        var url = window.URL.createObjectURL(blob);
        var downloadAnchorNode = document.createElement('a');
        downloadAnchorNode.setAttribute("href",     url);
        downloadAnchorNode.setAttribute("download", "crontab_export_" + new Date().getTime() + ".json");
        document.body.appendChild(downloadAnchorNode);
        downloadAnchorNode.click();
        downloadAnchorNode.remove();
        window.URL.revokeObjectURL(url);
        layer.msg('导出成功', {icon: 1});
    }, 'json');
}

// 触发导入文件选择
function importTasks() {
    $('#import_file').click();
}

// 处理导入文件
function processImport(obj) {
    var file = obj.files[0];
    if (!file) return;
    
    var reader = new FileReader();
    reader.onload = function(e) {
        var contents = e.target.result;
        try {
            var tasks = JSON.parse(contents);
            if (!Array.isArray(tasks)) {
                layer.msg('无效的任务列表格式', { icon: 2 });
                return;
            }
            
            layer.confirm('确定要导入 ' + tasks.length + ' 个计划任务吗？', { icon: 3, title: '提示' }, function(index) {
                layer.close(index);
                importTaskSequential(tasks, 0);
            });
        } catch (err) {
            layer.msg('解析 JSON 失败: ' + err, { icon: 2 });
        }
        obj.value = ''; // 重置文件输入
    };
    reader.readAsText(file);
}

// 顺序导入任务以避免并发冲突
function importTaskSequential(tasks, index) {
    if (index >= tasks.length) {
        layer.msg('导入完成', { icon: 1 });
        getCronData(1);
        return;
    }
    
    var task = tasks[index];
    var load = layer.msg('正在导入(' + (index + 1) + '/' + tasks.length + '): ' + task.name, { icon: 16, time: 0, shade: [0.3, '#000'] });
    
    // 如果没有 type_raw，尝试使用 type
    if (!task.type && task.type_raw) task.type = task.type_raw;

    $.post('/crontab/add', task, function(rdata) {
        layer.close(load);
        if (!rdata.status) {
            console.log('导入失败: ' + task.name + ' - ' + rdata.msg);
        }
        importTaskSequential(tasks, index + 1);
    }, 'json').fail(function(){
        layer.close(load);
        importTaskSequential(tasks, index + 1);
    });
}

// 从服务器同步计划任务
function syncServerTasks() {
    layer.confirm('将导入服务器上存在的系统计划任务，\n 确定要同步吗？', { icon: 3, title: '提示' }, function(index) {
        layer.close(index);
        var load = layer.msg('正在同步,请稍候...', { icon: 16, time: 0, shade: [0.3, '#000'] });
        $.post('/crontab/sync_sys_cron', function(rdata) {
            layer.close(load);
            if (rdata.status) {
                layer.msg(rdata.msg, { icon: 1, time: 2000 });
                setTimeout(function(){
                    getCronData(1);
                }, 2000);
            } else {
                layer.msg(rdata.msg, { icon: 2, time: 3000 });
            }
        }, 'json');
    });
}