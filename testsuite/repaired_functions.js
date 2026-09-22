// 标准修复版 14 个函数，严格闭合 HTML，注入 i18n 多语言，fallback 中文

const functions = {};

functions.webPathEdit = `function webPathEdit(id){
	$.post('/site/get_dir_user_ini','id='+id, function(data){
		var data = data['data'];
		var site_path = data['path'];
		var site_name = data['name'];
		var run_path = data['run_path']['run_path'];
		var user_ini_checked = data.user_ini?'checked':'';
		var logs_checked = data.logs?'checked':'';
		var opt = '';
		var selected = '';
		for(var i=0;i<data.run_path.dirs.length;i++){
			selected = '';
			if(data.run_path.dirs[i] == data.run_path.path){ 
				selected = 'selected';
			}
			opt += '<option value="'+ data.run_path.dirs[i] +'" '+selected+'>'+ data.run_path.dirs[i] +'</option>';
		}
		var content = "<div class='webedit-box soft-man-con'>\\
					<div class='label-input-group ptb10'>\\
						<input type='checkbox' name='userini' id='userini'"+user_ini_checked+" /><label class='mr20' for='userini' style='font-weight:normal'>" + ((lan && lan.site && t('site.preventing_cross_site_attacks')) || '防跨站攻击(open_basedir)') + "</label>\\
						<input type='checkbox' name='logs' id='logs'"+logs_checked+" /><label for='logs' style='font-weight:normal'>" + ((lan && lan.site && t('site.write_an_access_log')) || '写访问日志') + "</label>\\
					</div>\\
					<div class='line mt10'>\\
						<span class='mr5'>" + ((lan && lan.site && t('site.website_directory_1')) || '网站目录') + "</span>\\
						<input class='bt-input-text mr5' type='text' style='width:50%' placeholder='" + ((lan && lan.site && t('site.web_root_dir')) || '网站根目录') + "' value='"+site_path+"' name='webdir' id='inputPath'>\\
						<span onclick='changePath(&quot;inputPath&quot;)' class='glyphicon glyphicon-folder-open cursor mr20'></span>\\
						<button class='btn btn-success btn-sm' onclick='setSitePath("+id+")'>" + ((lan && lan.site && t('site.save')) || '保存') + "</button>\\
					</div>\\
					<div class='line mtb15'>\\
						<span class='mr5'>" + ((lan && lan.site && t('site.runtime_directory')) || '运行目录') + "</span>\\
						<select class='bt-input-text' type='text' style='width:50%; margin-right:41px' name='runPath' id='runPath'>"+opt+"</select>\\
						<button class='btn btn-success btn-sm' onclick='setSiteRunPath("+id+")' style='margin-top: -1px;'>" + ((lan && lan.site && t('site.save')) || '保存') + "</button>\\
					</div>\\
					<ul class='help-info-text c7 ptb10'>\\
						<li>" + ((lan && lan.site && t('site.some_programs_require_subdirectory')) || '部分程序需要指定二级目录作为运行目录，如ThinkPHP5，Laravel') + "</li>\\
						<li>" + ((lan && lan.site && t('site.your_runtime_directory_then')) || '选择您的运行目录，点保存即可') + "</li>\\
					</ul>"
					+'<div class="user_pw_tit" style="margin-top: -8px;padding-top: 11px;">'
						+'<span class="tit">' + ((lan && lan.site && t('site.password_access')) || '密码访问') + '</span>'
						+'<span class="btswitch-p"><input '+(data.pass?'checked':'')+' class="btswitch btswitch-ios" id="pathSafe" type="checkbox">'
							+'<label class="btswitch-btn phpmyadmin-btn" for="pathSafe" onclick="pathSafe('+id+')"></label>'
						+'</span>'
					+'</div>'
					+'<div class="user_pw" style="margin-top: 10px;display:'+(data.pass?'block;':'none;')+'">'
						+'<p><span>' + ((lan && lan.site && t('site.authorized_accounts')) || '授权账号') + '</span><input id="username_get" class="bt-input-text" name="username_get" value="" type="text" placeholder="' + ((lan && lan.site && t('site.if_unchanged_leave_blank')) || '不修改请留空') + '"></p>'
						+'<p><span>' + ((lan && lan.site && t('site.access_password')) || '访问密码') + '</span><input id="password_get_1" class="bt-input-text" name="password_get_1" value="" type="password" placeholder="' + ((lan && lan.site && t('site.if_unchanged_leave_blank')) || '不修改请留空') + '"></p>'
						+'<p><span>' + ((lan && lan.site && t('site.re_enter_password')) || '重复密码') + '</span><input id="password_get_2" class="bt-input-text" name="password_get_1" value="" type="password" placeholder="' + ((lan && lan.site && t('site.if_unchanged_leave_blank')) || '不修改请留空') + '"></p>'
						+'<p><button class="btn btn-success btn-sm" onclick="setPathSafe('+id+')">' + ((lan && lan.site && t('site.save_1')) || '保存') + '</button></p>'
					+'</div>'
				+'</div>';

		$("#webedit-con").html(content);		
		$("#userini").on('change', function(){
			$.post('/site/set_dir_user_ini',{'path':site_path,'run_path':run_path,},function(userini){
				layer.msg(data.msg+'<p style="color:red;">' + ((lan && lan.site && t('site.note_you_must_restart')) || '注意：设置防跨站需要重启PHP才能生效!') + '</p>',{icon:data.status?1:2});
				tryRestartPHP(site_name);
			},'json');
		});
		
		$("#logs").on('change', function(){
			var loadT = layer.msg(((lan && lan.site && t('site.setting_up')) || '正在设置中...'),{icon:16,time:10000,shade: [0.3, '#000']});
			$.post('/site/logs_open','id='+id, function(rdata){
				layer.close(loadT);
				layer.msg(rdata.msg,{icon:rdata.status?1:2});
			},'json');
		});
		
	},'json');
}`;

functions.webBakEdit = `function webBakEdit(id){
	$.post("/data?action=getKey','table=sites&key=ps&id="+id,function(rdata){
		var webBakHtml = "<div class='webEdit-box padding-10'>\\
			<div class='line'>\\
			<label><span>" + ((lan && lan.site && t('site.note_ph')) || '备注') + "</span></label>\\
			<div class='info-r'>\\
			<textarea name='beizhu' id='webbeizhu' col='5' style='width:96%'>"+rdata+"</textarea>\\
			<br><br><button class='btn btn-success btn-sm' onclick='SetSitePs("+id+")'>" + ((lan && lan.site && t('site.save_2')) || '保存') + "</button>\\
			</div>\\
		</div>";
		$("#webedit-con").html(webBakHtml);
	});
}`;

functions.domainEdit = `function domainEdit(id, name, msg, status) {
	$.post('/site/get_domain' ,{pid:id}, function(data) {
		var domain = data.data;

		var echoHtml = "";
		for (var i = 0; i < domain.length; i++) {
			echoHtml += "<tr>\\
				<td><a title='" + ((lan && lan.site && t('site.click_access')) || '点击访问') + "' target='_blank' href='http://" + domain[i].name + (domain[i].port == '80' ? '' : ':' + domain[i].port) + "' class='btlinkbed'>" + domain[i].name + "</a></td>\\
				<td><a class='btlinkbed'>" + domain[i].port + "</a></td>\\
				<td class='text-center'><a class='table-btn-del' href='javascript:;' onclick=\\"delDomain(" + id + ",'" + name + "','" + domain[i].name + "','" + domain[i].port + "',1)\\"><span class='glyphicon glyphicon-trash'></span></a></td>\\
				</tr>";
		}
		var bodyHtml = "<textarea id='newdomain' class='bt-input-text' style='height: 100px; width: 340px;padding:5px 10px;line-height:20px'></textarea>\\
								<input type='hidden' id='newport' value='80' />\\
								<button type='button' class='btn btn-success btn-sm pull-right' style='margin:30px 35px 0 0' onclick=\\"domainAdd(" + id + ",'" + name + "',1)\\">" + ((lan && lan.site && t('site.add')) || '添加') + "</button>\\
							<div class='divtable mtb15' style='height:420px;overflow:auto'>\\
								<table class='table table-hover' width='100%'>\\
								<thead><tr><th>" + ((lan && lan.site && t('site.domain')) || '域名') + "</th><th width='70px'>" + ((lan && lan.site && t('site.port')) || '端口') + "</th><th width='50px' class='text-center'>" + ((lan && lan.site && t('site.operations_5')) || '操作') + "</th></tr></thead>\\
								<tbody id='checkDomain'>" + echoHtml + "</tbody>\\
								</table>\\
							</div>";
		$("#webedit-con").html(bodyHtml);
		if(msg != undefined){
			layer.msg(msg,{icon:status?1:5});
		}
		var placeholder = "<div class='placeholder c9' style='left:28px;width:330px;top:16px;'>" + ((lan && lan.site && t('site.enter_one_domain_name')) || '每行填写一个域名，默认为80端口') + "<br>" + ((lan && lan.site && t('site.how_to_add_wildcard')) || '泛解析添加方法 *.domain.com') + "<br>" + ((lan && lan.site && t('site.if_an_additional_port')) || '如另加端口格式为 www.domain.com:88') + "</div>";
		$('#newdomain').after(placeholder);
		$(".placeholder").on('click', function(){
			$(this).hide();
			$('#newdomain').trigger('focus');
		});
		$('#newdomain').on('focus', function() {
		    $(".placeholder").hide();
		});
		
		$('#newdomain').on('blur', function() {
			if($(this).val().length==0){
				$(".placeholder").show();
			}  
		});
		$("#newdomain").on("input",function(){
			var str = $(this).val();
			if(isChineseChar(str)) {
				$('.btn-zhm').show();
			} else{
				$('.btn-zhm').hide();
			}
		});
	},'json');
}`;

functions.getBackup = `function getBackup(id,name,page){
	if(page == undefined){
		page = '1';
	}
	$.post('/site/get_backup','search='+id+'&limit=5&p='+page,function(frdata){
		var body = '';
		for(var i=0;i<frdata.data.length;i++){
			if(frdata.data[i].type == '1') {
				continue;
			}
			var ftpdown = "<a class='btlink' href='/files/download?filename="+frdata.data[i].filename+"&name="+frdata.data[i].name+"' target='_blank'>" + ((lan && lan.site && t('site.target_blank_download')) || '下载') + "</a> | ";
			body += "<tr><td><span class='glyphicon glyphicon-file'></span>"+frdata.data[i].name+"</td>\\
					<td>"+toSize(frdata.data[i].size)+"</td>\\
					<td>"+frdata.data[i].add_time+"</td>\\
					<td class='text-right' style='color:#ccc'>"+ftpdown+"<a class='btlink' href='javascript:;' onclick=\\"webBackupDelete('"+frdata.data[i].id+"',"+id+")\\">" + ((lan && lan.site && t('site.delete')) || '删除') + "</a></td>\\
				</tr>";
		}
		var ftpdown = '';
		frdata.page = frdata.page.replace(/'/g,'"').replace(/getBackup\\(/g,'getBackup('+id+',0,');
		if(name == 0){
			var sBody = "<table width='100%' id='webBackupList' class='table table-hover'>\\
				<thead><tr><th>" + ((lan && lan.site && t('site.file_name')) || '文件名称') + "</th><th>" + ((lan && lan.site && t('site.file_size')) || '文件大小') + "</th><th>" + ((lan && lan.site && t('site.packing_time')) || '打包时间') + "</th><th width='140px' class='text-right'>" + ((lan && lan.site && t('site.operations_6')) || '操作') + "</th></tr></thead>\\
				<tbody id='webBackupBody' class='list-list'>"+body+"</tbody>\\
			</table>";
			$("#webBackupList").html(sBody);
			$(".page").html(frdata.page);
			return;
		}
		layer.closeAll();
		layer.open({
			type: 1,
			skin: 'demo-class',
			area: '700px',
			title: ((lan && lan.site && t('site.backup_list')) || '备份列表') + ' &gt;&gt; ' + frdata['site']['name'],
			closeBtn: 2,
			shadeClose: true,
			content: "<div class='bt-form pd15'>\\
						<button class='btn btn-default btn-sm' onclick=\\"webBackup('"+frdata['site']['id']+"','"+frdata['site']['name']+"')\\">" + ((lan && lan.site && t('site.pack_and_back_up_1')) || '打包备份') + "</button>\\
						<div class='divtable mtb15'>\\
							<table width='100%' id='webBackupList' class='table table-hover'>\\
							<thead><tr><th>" + ((lan && lan.site && t('site.file_name')) || '文件名称') + "</th><th>" + ((lan && lan.site && t('site.file_size')) || '文件大小') + "</th><th>" + ((lan && lan.site && t('site.packing_time')) || '打包时间') + "</th><th width='140px' class='text-right'>" + ((lan && lan.site && t('site.operations_6')) || '操作') + "</th></tr></thead>\\
							<tbody id='webBackupBody' class='list-list'>"+body+"</tbody>\\
							</table>\\
							<div class='page'>"+frdata.page+"</div>\\
						</div>\\
					</div>"
		});
	},'json');
}`;

functions.webEdit = `function webEdit(id,website,endTime,addtime){
	var webEdit_menu = "<p class='bgw' onclick=\\"domainEdit(" + id + ",'" + website + "')\\">" + ((lan && lan.site && t('site.domain_management')) || '域名管理') + "</p>\\
						<p onclick=\\"dirBinding(" + id + ",'" + website + "')\\">" + ((lan && lan.site && t('site.subdirectory_mapping')) || '子目录绑定') + "</p>\\
						<p onclick=\\"webPathEdit(" + id + ",'" + website + "')\\">" + ((lan && lan.site && t('site.website_directory')) || '网站目录') + "</p>\\
						<p onclick=\\"limitNet(" + id + ",'" + website + "')\\">" + ((lan && lan.site && t('site.data_limit')) || '流量限制') + "</p>\\
						<p onclick=\\"rewrite('" + website + "')\\">" + ((lan && lan.site && t('site.pseudo_static')) || '伪静态') + "</p>\\
						<p onclick=\\"setIndexEdit(" + id + ",'" + website + "')\\">" + ((lan && lan.site && t('site.default_document')) || '默认文档') + "</p>\\
						<p onclick=\\"configFile('" + website + "')\\">" + ((lan && lan.site && t('site.configuration_file')) || '配置文件') + "</p>\\
						<p onclick=\\"setSSL(" + id + ",'" + website + "')\\">SSL</p>\\
						<p onclick=\\"phpVersion('" + website + "')\\">" + ((lan && lan.site && t('site.php_version')) || 'PHP版本') + "</p>\\
						<p onclick=\\"to301('" + website + "')\\">" + ((lan && lan.site && t('site.redirect')) || '重定向') + "</p>\\
						<p onclick=\\"toProxy('" + website + "')\\">" + ((lan && lan.site && t('site.reverse_proxy')) || '反向代理') + "</p>\\
						<p id='site_" + id + "' onclick=\\"security(" + id + ",'" + website + "')\\">" + ((lan && lan.site && t('site.hotlink_protection')) || '防盗链') + "</p>\\
						<p id='site_" + id + "' onclick=\\"getSiteLogs('" + website + "')\\">" + ((lan && lan.site && t('site.response_log')) || '响应日志') + "</p>\\
						<p id='site_" + id + "' onclick=\\"getSiteErrorLogs('" + website + "')\\">" + ((lan && lan.site && t('site.error_log')) || '错误日志') + "</p>";
	$("#webedit-con").html(webEdit_menu);
	layer.open({
		type: 1,
		area: '700px',
		title: ((lan && lan.site && t('site.site_modification')) || '网站修改') + ' &gt;&gt; ' + website,
		closeBtn: 2,
		shift: 5,
		shadeClose: true,
		content: "<div class='site-nav'>\\
					<div class='site-menu'>\\
						"+webEdit_menu+"\\
					</div>\\
					<div class='site-content'>\\
						<div id='webedit-con'></div>\\
					</div>\\
				</div>"
	});
	$(".site-menu p").on('click', function(){
		$(this).addClass("bgw").siblings().removeClass("bgw");
	});
	domainEdit(id,website);
}`;

functions.dirBinding = `function dirBinding(id) {
	$.post('/site/get_dir_binding', 'id=' + id, function(rdata) {
		var opt = '';
		var body = '';
		for (var i = 0; i < rdata.dirs.length; i++) {
			opt += '<option value="' + rdata.dirs[i] + '">' + rdata.dirs[i] + '</option>';
		}
		for (var i = 0; i < rdata.binding.length; i++) {
			body += '<tr>\\
				<td>' + rdata.binding[i].domain + '</td>\\
				<td>' + rdata.binding[i].port + '</td>\\
				<td>' + rdata.binding[i].path + '</td>\\
				<td class="text-right"><a class="btlink" href="javascript:setDirRewrite(' + rdata.binding[i].id + ');">' + ((lan && lan.site && t('site.pseudo_static')) || '伪静态') + '</a> | <a class="btlink" href="javascript:delDirBinding(' + rdata.binding[i].id + ',' + id + ');">' + ((lan && lan.site && t('site.delete')) || '删除') + '</a></td>\\
			</tr>';
		}
		var content = "<div class='divtable pd15'>\\
			<form id='dirBinding'>\\
				<span class='tname'>" + ((lan && lan.site && t('site.domain_name_1')) || '域名') + "</span>\\
				<input class='bt-input-text mr5' type='text' name='domain' style='width: 35%;' placeholder='" + ((lan && lan.site && t('site.domain_name_2')) || '域名') + "' />\\
				<span class='tname'>" + ((lan && lan.site && t('site.subdirectory')) || '子目录') + "</span>\\
				<select class='bt-input-text mr5' name='dirName' style='width: 25%;'>" + opt + "</select>\\
				<input type='hidden' name='id' value='" + id + "'>\\
				<button class='btn btn-success btn-sm' type='button' onclick='addDirBinding(" + id + ")'>" + ((lan && lan.site && t('site.add_1')) || '添加') + "</button>\\
			</form>\\
			<table class='table table-hover mt15'>\\
				<thead><tr><th>" + ((lan && lan.site && t('site.domain_name_1')) || '域名') + "</th><th width='70px'>" + ((lan && lan.site && t('site.port')) || '端口') + "</th><th width='120px'>" + ((lan && lan.site && t('site.subdirectory')) || '子目录') + "</th><th width='100px' class='text-right'>" + ((lan && lan.site && t('site.operations_7')) || '操作') + "</th></tr></thead>\\
				<tbody id='checkDomain'>" + body + "</tbody>\\
			</table>\\
		</div>";
		$("#webedit-con").html(content);
	}, 'json');
}`;

functions.to301 = `function to301(siteName, type, data) {
	if (type == 1) {
		open301(siteName, 0, data);
		return;
	}
	if (type == 2) {
		del301(siteName, data);
		return;
	}
	if (type == 3) {
		open301(siteName, 1, data);
		return;
	}
	var body = '<div class="divtable mtb15" style="padding-left: 15px;padding-right: 15px;">\\
		<button class="btn btn-success btn-sm" id="btn-add-301">' + ((lan && lan.site && t('site.btn_add_301')) || '添加重定向') + '</button>\\
		<div class="divtable mtb15">\\
			<table class="table table-hover">\\
				<thead>\\
					<tr>\\
						<th>' + ((lan && lan.site && t('site.th_301_1')) || '重定向类型') + '</th>\\
						<th>' + ((lan && lan.site && t('site.th_301_2')) || '重定向标识') + '</th>\\
						<th>' + ((lan && lan.site && t('site.th_301_3')) || '重定向方式') + '</th>\\
						<th>' + ((lan && lan.site && t('site.th_301_4')) || '保留URI') + '</th>\\
						<th>' + ((lan && lan.site && t('site.th_301_5')) || '目标URL') + '</th>\\
						<th>' + ((lan && lan.site && t('site.th_301_6')) || '状态') + '</th>\\
						<th style="text-align:right;">' + ((lan && lan.site && t('site.th_301_7')) || '操作') + '</th>\\
					</tr>\\
				</thead>\\
				<tbody id="md-301-body">\\
				</tbody>\\
			</table>\\
		</div>\\
	</div>';
	$("#webedit-con").html(body);
	var loadT = layer.msg(((lan && lan.site && t('site.the_msg')) || '正在获取数据...'), {icon: 16, time: 0, shade: [0.3, '#000']});
	$.post('/site/get_redirect_list', 'siteName=' + siteName, function(data) {
		layer.close(loadT);
		var data = data.data;
		for (var i = 0; i < data.length; i++) {
			var item = data[i];
			var fromDomain = '';
			if (item.type == 1) {
				fromDomain = ((lan && lan.site && t('site.all_sites')) || '整站');
			} else {
				fromDomain = item.domain;
			}
			var switchProxy = '';
			if (item.status == 1) {
				switchProxy = '<span style="color:#20a53a">' + ((lan && lan.site && t('site.start_301')) || '正在重定向') + '</span>';
			} else {
				switchProxy = '<span style="color:red">' + ((lan && lan.site && t('site.stop_301')) || '已停止') + '</span>';
			}
			var isPath = '';
			if (item.rpath == 1) {
				isPath = '<span>' + ((lan && lan.site && t('site.is_path_1')) || '是') + '</span>';
			} else {
				isPath = '<span>' + ((lan && lan.site && t('site.is_path_2')) || '否') + '</span>';
			}
			var redirectpath = '';
			if (item.redirectpath == 301) {
				redirectpath = '301';
			} else {
				redirectpath = '302';
			}
			$('#md-301-body').append('<tr>\\
					<td><span data-index="1"><span>' + fromDomain + '</span></span></td>\\
					<td><span data-index="1"><span>' + item.name + '</span></span></td>\\
					<td><span data-index="2"><span>' + redirectpath + '</span></span></td>\\
					<td><span data-index="3"><span>' + isPath + '</span></span></td>\\
					<td><span data-index="4"><span>' + item.tourl + '</span></span></td>\\
					<td><span data-index="4"><span>' + switchProxy + '</span></span></td>\\
					<td style="text-align:right;">\\
						<span data-index="5" onclick="to301(\\'' + siteName + '\\', 3, \\'' + item.id + '\\')" class="btlink">' + ((lan && lan.site && t('site.btlink_1')) || '详细') + '</span> | \\
						<span data-index="5" onclick="to301(\\'' + siteName + '\\', 2, \\'' + item.id + '\\')" class="btlink">' + ((lan && lan.site && t('site.btlink_2')) || '删除') + '</span>\\
					</td>\\
				</tr>');
		}
		$('#btn-add-301').on('click', function() {
			to301(siteName, 1);
		});
	}, 'json');
}`;

functions.sslAdmin = `function sslAdmin(siteName){
	var loadT = layer.msg(((lan && lan.site && t('site.submitting_task_2')) || '正在提交任务...'),{icon:16,time:0,shade: [0.3, '#000']});
	$.get('/site/get_cert_list',function(data){
		layer.close(loadT);
		var rdata = data['data'];
		var tbody = '';
		for(var i=0;i<rdata.length;i++){
			tbody += '<tr>\\
				<td>'+rdata[i].subject+'</td>\\
				<td>'+rdata[i].dns.join('<br>')+'</td>\\
				<td>'+rdata[i].notAfter+'</td>\\
				<td>'+rdata[i].issuer.split(' ')[0]+'</td>\\
				<td style="text-align: right;"><a onclick="setCertSsl(\\''+rdata[i].subject+'\\',\\''+siteName+'\\')" class="btlink">' + ((lan && lan.site && t('site.btlink_3')) || '部署') + '</a> | <a onclick="removeSsl(\\''+rdata[i].subject+'\\')" class="btlink">' + ((lan && lan.site && t('site.btlink_4')) || '删除') + '</a></td>\\
			</tr>'
		}
		var txt = '<div class="mtb15" style="line-height:30px">\\
		<button style="margin-bottom: 7px;display:none;" class="btn btn-success btn-sm">' + ((lan && lan.site && t('site.add')) || '添加') + '</button>\\
		<div class="divtable"><table class="table table-hover"><thead><tr><th>' + ((lan && lan.site && t('site.domain')) || '域名') + '</th><th>' + ((lan && lan.site && t('site.trust_name')) || '信任名称') + '</th><th>' + ((lan && lan.site && t('site.expiration_date')) || '到期时间') + '</th><th>' + ((lan && lan.site && t('site.brand')) || '品牌') + '</th><th class="text-right" width="75">' + ((lan && lan.site && t('site.operations_5')) || '操作') + '</th></tr></thead>\\
		<tbody>'+tbody+'</tbody>\\
		</table></div></div>';
		$(".tab-con").html(txt);
	},'json');
}`;

functions.setSSL = `function setSSL(id, siteName) {
	var sslHtml = "<div class='warning_info mb10' style='display:none;'>\\
					<p>" + ((lan && lan.site && t('site.friendly_reminder_this_site')) || '温馨提示：当前站点未开启SSL证书访问，站点访问可能存在风险。') + "<button class='btn btn-success btn-xs ml10 cutTabView'>" + ((lan && lan.site && t('site.apply_for_certificate')) || '申请证书') + "</button></p>\\
				</div>\\
				<div class='tab-nav' style='margin-top: 10px;'>\\
					<span class='on' id='now_ssl' onclick=\\"opSSL('now'," + id + ",'" + siteName + "')\\">" + ((lan && lan.site && t('site.current_certificate')) || '当前证书 -') + " <i class='error'>" + ((lan && lan.site && t('site.ssl_not_deployed')) || '[未部署SSL]') + "</i></span>\\
					<span onclick=\\"opSSL('acme'," + id + ",'" + siteName + "')\\">ACME</span>\\
					<span id='ssl_admin' onclick=\\"sslAdmin('" + siteName + "')\\">" + ((lan && lan.site && t('site.certificate_folder')) || '证书夹') + "</span>\\
					<div class='ss-text pull-right mr30' style='position: relative;top:-4px'></div>\\
				</div>\\
				<div class='tab-con' style='padding: 0px;'></div>";
	$("#webedit-con").html(sslHtml);
	$(".tab-nav span").on('click', function () {
		$(this).addClass("on").siblings().removeClass("on");
	});
	$('.cutTabView').on('click', function () {
		$('.tab-nav span').eq(1).click();
	});
	opSSL('now', id, siteName);
}`;

functions.opSSLNow = `function opSSLNow(type, id, siteName, callback){
	var now = '<div class="myKeyCon ptb15">\\
			<div class="ssl_state_info" style="display:none;"></div>\\
		<div class="custom_certificate_info">\\
			<div class="ssl-con-key pull-left mr20">' + ((lan && lan.site && t('site.key_key')) || '密钥(KEY)') + '<br><textarea id="key" class="bt-input-text"></textarea></div>\\
			<div class="ssl-con-key pull-left">' + ((lan && lan.site && t('site.certificate_pem_format_2')) || '证书(PEM格式)') + '<br><textarea id="csr" class="bt-input-text"></textarea></div>\\
		</div>\\
		<div class="ssl-btn pull-left mtb15" style="width:100%">\\
			<button class="btn btn-success btn-sm" onclick="saveSSL(\\''+siteName+'\\')">' + ((lan && lan.public && t('public.save')) || '保存') + '</button>\\
		</div>\\
	</div>\\
	<ul class="help-info-text c7 pull-left">\\
		<li>' + ((lan && lan.site && t('site.paste_the_contents_of')) || '粘贴您的*.key以及*.pem内容，然后保存即可。') + '</li>\\
		<li>' + ((lan && lan.site && t('site.if_your_browser_prompts')) || '如果浏览器提示证书链不完整,请检查是否正确拼接PEM证书') + '</li><li>' + ((lan && lan.site && t('site.pem_format_certificate_domain')) || 'PEM格式证书 = 域名证书.crt + 根证书(root_bundle).crt') + '</li>\\
		<li>' + ((lan && lan.site && t('site.if_no_default_ssl')) || '在未指定SSL默认站点时,未开启SSL的站点使用HTTPS会直接访问到已开启SSL的站点') + '</li>\\
	</ul>';

	$(".tab-con").html(now);
	var key = '';
	var csr = '';
	var loadT = layer.msg(((lan && lan.site && t('site.submitting_task_2')) || '正在提交任务...'),{icon:16,time:0,shade: [0.3, '#000']});
	$.post('/site/get_ssl','site_name='+siteName,function(data){
		layer.close(loadT);
		var rdata = data['data'];

		if (rdata['cert_data']){
			var issuer_o = rdata['cert_data']['issuer_o'] || ((lan && lan.site && t('site.self_signed_unknown')) || '自签名/未知');
			var issuer = rdata['cert_data']['issuer'] || ((lan && lan.site && t('site.unknown')) || '未知');
			var domains = rdata['cert_data']['dns'].join("、");

			var cert_data = "<div class='state_info_flex'>\\
				<div class='state_item'><span>" + ((lan && lan.site && t('site.certificate_categories')) || '证书分类：') + "</span><span class='ellipsis_text'>"+issuer_o+"</span></div>\\
				<div class='state_item'><span>" + ((lan && lan.site && t('site.certificate_brand')) || '证书品牌：') + "</span><span class='ellipsis_text'>"+issuer+"</span></div>\\
			</div>\\
			<div class='state_info_flex'>\\
				<div class='state_item'><span>" + ((lan && lan.site && t('site.expiration_date')) || '到期时间：') + "</span><span class='btlink'>" + ((lan && lan.site && t('site.remaining_1')) || '剩余') + rdata['cert_data']['endtime'] + ((lan && lan.site && t('site.due_date')) || '天到期') + "</span></div>\\
				<div class='state_item'><span>" + ((lan && lan.site && t('site.verified_domain')) || '认证域名：') + "</span><span class='ellipsis_text'>"+domains+"</span></div>\\
			</div>\\
			<div class='state_info_flex'>\\
				<div class='state_item'><span>" + ((lan && lan.site && t('site.enforce_https')) || '强制HTTPS：') + "</span><span class='switch'>\\
					<input class='btswitch btswitch-ios' id='toHttps' type='checkbox'>\\
                    <label class='btswitch-btn' for='toHttps' onclick=\\"httpToHttps('" + siteName + "')\\"></label>\\
				</span></div>\\
			</div>";
			$(".ssl_state_info").html(cert_data);
			$(".ssl_state_info").css('display','block');
		}

		if(rdata.key == false){
			rdata.key = '';
		} else {
			$(".ssl-btn").append('<button style=\\'margin-left:3px;\\' class="btn btn-success btn-sm" onclick="deleteSSL(\\'now\\','+id+',\\''+siteName+'\\')">' + ((lan && lan.site && t('site.delete_4')) || '删除') + '</button>');
		}

		if(rdata.csr == false){
			rdata.csr = '';
		}
		$("#key").val(rdata.key);
		$("#csr").val(rdata.csr);

		$("#toHttps").attr('checked',rdata.httpTohttps);
		if(rdata.status){
			$('.warning_info').css('display','none');
			
			$(".ssl-btn").append("<button class='btn btn-success btn-sm' onclick=\\"ocSSL('close_ssl_conf','"+siteName+"')\\" style='margin-left:3px;'>" + ((lan && lan.site && t('site.ssl')) || '关闭SSL') + "</button>");
			$(".ssl-btn").append("<button class='btn btn-success btn-sm' onclick=\\"renewSSL('acme',"+id+",'"+siteName+"')\\" style='margin-left:3px;'>" + ((lan && lan.site && t('site.msg_2')) || '手动续签') + "</button>");
			$('#now_ssl').html(((lan && lan.site && t('site.current_certificate')) || '当前证书 -') + ' <i style="color:#20a53a;">' + ((lan && lan.site && t('site.ssl_deployed')) || '[已部署SSL]') + '</i>');
		} else{
			$('.warning_info').css('display','block');
			$('#now_ssl').html(((lan && lan.site && t('site.current_certificate')) || '当前证书 -') + ' <i style="color:red;">' + ((lan && lan.site && t('site.ssl_not_deployed')) || '[未部署SSL]') + '</i>');
		}

		if (typeof (callback) != 'undefined'){
			callback(rdata);
		}
	},'json');
}`;

functions.opSSLAcme = `function opSSLAcme(type, id, siteName, callback){
	var acme =  '<div class="apply_ssl">\\
		<div class="label-input-group">\\
			<div class="line">\\
				<span class="tname text-center">' + ((lan && lan.site && t('site.authentication_methods')) || '验证方式') + '</span>\\
				<div style="margin-top:7px;display:inline-block">\\
					<input type="radio" name="apply_type" value="file" id="check_file" checked="checked"/>\\
  					<label class="mr20" for="check_file" style="font-weight:normal">' + ((lan && lan.site && t('site.file_validation')) || '文件验证') + '</label>\\
  					<input type="radio" name="apply_type" value="dns" id="check_dns"/>\\
  					<label class="mr20" for="check_dns" style="font-weight:normal">' + ((lan && lan.site && t('site.dns_verification')) || 'DNS验证') + '</label>\\
  				</div>\\
	  		</div>\\
	  		<div class="line">\\
				<span class="tname text-center">' + ((lan && lan.site && t('site.certificate')) || '证书') + '</span>\\
				<div style="margin-top:7px;display:inline-block">\\
					<input type="radio" name="apply_ca" value="default" id="ca_default" checked="checked"/>\\
  					<label class="mr20" for="ca_default" style="font-weight:normal">' + ((lan && lan.site && t('site.default')) || '默认') + '</label>\\
  					<input type="radio" name="apply_ca" value="let" id="ca_letsencrypt"/>\\
  					<label class="mr20" for="ca_letsencrypt" style="font-weight:normal">letsencrypt</label>\\
  					<input type="radio" name="apply_ca" value="zerossl" id="ca_zerossl"/>\\
  					<label class="mr20" for="ca_zerossl" style="font-weight:normal">zerossl</label>\\
  					<input type="radio" name="apply_ca" value="buypass" id="ca_buypass"/>\\
  					<label class="mr20" for="ca_buypass" style="font-weight:normal">buypass</label>\\
  				</div>\\
	  		</div>\\
	  		<div class="line mtb10" id="dnsapi_option" style="display:none;">\\
				<span class="tname text-center" style="line-height: 42px;">' + ((lan && lan.site && t('site.dns_interface')) || '选择DNS接口') + '</span>\\
				<div style="margin-top:7px;display:inline-block">\\
					<select name="dnspai" class="bt-input-text mr20">\\
						<option value="none">' + ((lan && lan.site && t('site.manual_parsing_2')) || '手动解析') + '</option>\\
					</select>\\
					<button id="dnsapi_set" class="btn btn-default btn-sm btn-title" style="display:none;">' + ((lan && lan.site && t('site.configuration')) || '配置') + '</button>\\
  				</div>\\
	  		</div>\\
  			<div class="check_message line" id="wildcard_domain_block" style="display:none;">\\
  				<div style="margin-left:100px">\\
  					<input type="checkbox" name="wildcard_domain" id="wildcard_domain" checked="checked">\\
  					<label class="mr20" for="wildcard_domain" style="font-weight:normal">' + ((lan && lan.site && t('site.automatic_generation_of_wildcard')) || '自动组合泛域名') + '</label>\\
  				</div>\\
  			</div>\\
  			<div class="check_message line">\\
  				<div style="margin-left:100px; margin-top:8px;">\\
  					<input type="checkbox" name="checkDomain" id="checkDomain" checked="">\\
  					<label class="mr20" for="checkDomain" style="font-weight:normal">' + ((lan && lan.site && t('site.pre_validate_domain_names')) || '提前校验域名(提前发现问题,减少失败率)') + '</label>\\
  				</div>\\
  			</div>\\
  		</div>\\
  		<div class="line mtb10">\\
  			<span class="tname text-center">' + ((lan && lan.site && t('site.email')) || '邮箱') + '</span>\\
  			<input class="bt-input-text" style="width:240px;" type="text" name="admin_email" />\\
  		</div>\\
  		<div class="line mtb10" id="dns_alias" style="display:none;">\\
			<span class="tname text-center">' + ((lan && lan.site && t('site.alias_verification')) || '别名验证') + '</span>\\
			<input class="bt-input-text" style="width:240px;" type="text" name="dns_alias" />\\
			<span> ' + ((lan && lan.site && t('site.not_recommended')) || '(建议别用)') + ' <a class="btlink" target="_blank" href="https://github.com/acmesh-official/acme.sh/wiki/DNS-alias-mode#7-challenge-alias-or-domain-alias">' + ((lan && lan.site && t('site.document_description')) || '文档说明') + '</a></span>\\
		</div>\\
  		<div class="line mtb10">\\
  			<span class="tname text-center">' + ((lan && lan.site && t('site.domain_name_5')) || '域名') + '</span>\\
  			<ul id="ymlist" style="padding: 5px 10px;max-height:180px;overflow:auto; width:240px;border:#ccc 1px solid;border-radius:3px"></ul>\\
  		</div>\\
  		<div class="line mtb10" style="margin-left:100px">\\
  			<button class="btn btn-success btn-sm letsApply">' + ((lan && lan.site && t('site.application')) || '申请') + '</button>\\
  		</div>\\
		<ul class="help-info-text c7" id="lets_help">\\
			<li>' + ((lan && lan.site && t('site.before_applying_please_make')) || '申请之前，请确保域名已解析，如未解析会导致审核失败') + '</li>\\
			<li>' + ((lan && lan.site && t('site.apply_for_free_certificate')) || '由ACME免费申请证书，有效期3个月，支持多域名。默认会自动续签') + '</li>\\
			<li>' + ((lan && lan.site && t('site.if_your_site_uses')) || '若您的站点使用了CDN或301重定向会导致续签失败') + '</li>\\
			<li>' + ((lan && lan.site && t('site.if_no_default_ssl_1')) || '在未指定SSL默认站点时,未开启SSL的站点使用HTTPS会直接访问到已开启SSL的站点') + '</li></ul>\\
	</div>';

	$(".tab-con").html(acme);

	$('input[name="apply_type"]').on('change', function(){
		var val = $(this).val();
		if (val == 'file'){
			$('#dnsapi_option').css('display','none');
			$('#wildcard_domain_block').css('display','none');
			$('#dns_alias').css('display','none');
		} else {
			$('#dnsapi_option').css('display','block');
			$('#wildcard_domain_block').css('display','block');
			$('#dns_alias').css('display','block');
		}
	});

	renderDnsapi();

	$.post('/site/get_ssl','site_name='+siteName+'&ssl_type=acme', function(data){
		var rdata = data['data'];
		if(rdata.csr == false){
			$.post('/site/get_site_domains','id='+id, function(rdata) {
				var data = rdata['data'];
				var opt='';
				for(var i=0;i<data.domains.length;i++){
					var isIP = isValidIP(data.domains[i].name);
					var x = isContains(data.domains[i].name, '*');
					if(!isIP && !x){
						opt += '<li style="line-height:26px">\\
							<input type="checkbox" style="margin-right:5px; vertical-align:-2px" value="'+data.domains[i].name+'">'+data.domains[i].name
						+'</li>';
					}
				}
				$("input[name='admin_email']").val(data.email);
				$("#ymlist").html(opt);
				$("#ymlist li input").on('click', function(e){
					e.stopPropagation();
				});
				$("#ymlist li").on('click', function(){
					var o = $(this).find("input");
					if(o.prop("checked")){
						o.prop("checked",false);
					}
					else{
						o.prop("checked",true);
					}
				});
				$(".letsApply").on('click', function(){
					var c = $("#ymlist input[type='checkbox']");
					var str = [];
					var domains = '';
					for(var i=0; i<c.length; i++){
						if(c[i].checked){
							str.push(c[i].value);
						}
					}
					domains = JSON.stringify(str);
					newAcmeSSL(siteName, id, domains);
				});

				if (typeof (callback) != 'undefined'){
					callback(rdata);
				}
			},'json');
			return;
		}
		var acme = '<div class="myKeyCon ptb15">\\
				<div class="ssl_state_info" style="display:none;"></div>\\
				<div class="custom_certificate_info">\\
					<div class="ssl-con-key pull-left mr20" readonly>' + ((lan && lan.site && t('site.key_key')) || '密钥(KEY)') + '<br><textarea id="key" class="bt-input-text">'+rdata.key+'</textarea></div>\\
					<div class="ssl-con-key pull-left" readonly>' + ((lan && lan.site && t('site.certificate_pem_format_2')) || '证书(PEM格式)') + '<br><textarea id="csr" class="bt-input-text">'+rdata.csr+'</textarea></div>\\
				</div>\\
				<div class="ssl-btn pull-left mtb15" style="width:100%">\\
					<button class="btn btn-success btn-sm" onclick="deploySSL(\\'acme\\','+id+',\\''+siteName+'\\')">' + ((lan && lan.site && t('site.btlink_3')) || '部署') + '</button>\\
					<button class="btn btn-success btn-sm" onclick="deleteSSL(\\'acme\\','+id+',\\''+siteName+'\\')">' + ((lan && lan.site && t('site.delete_4')) || '删除') + '</button>\\
				</div>\\
			</div>\\
			<ul class="help-info-text c7 pull-left">\\
				<li>' + ((lan && lan.site && t('site.free_acme_certificate')) || '已为您自动生成ACME免费证书') + '</li>\\
				<li>' + ((lan && lan.site && t('site.apply_for_free_certificate')) || '由ACME免费申请证书，有效期3个月，支持多域名。默认会自动续签') + '</li>\\
				<li>' + ((lan && lan.site && t('site.paste_key_pem_other')) || '如需使用其他SSL,请切换其他证书后粘贴您的KEY以及PEM内容，然后保存即可。') + '</li>\\
			</ul>';
		$(".tab-con").html(acme);

		if (rdata['cert_data']){
			var issuer_o = rdata['cert_data']['issuer_o'] || ((lan && lan.site && t('site.self_signed_unknown')) || '自签名/未知');
			var issuer = rdata['cert_data']['issuer'] || ((lan && lan.site && t('site.unknown')) || '未知');
			var domains = rdata['cert_data']['dns'].join("、");

			var cert_data = "<div class='state_info_flex'>\\
				<div class='state_item'><span>" + ((lan && lan.site && t('site.certificate_categories')) || '证书分类：') + "</span><span class='ellipsis_text'>"+issuer_o+"</span></div>\\
				<div class='state_item'><span>" + ((lan && lan.site && t('site.certificate_brand')) || '证书品牌：') + "</span><span class='ellipsis_text'>"+issuer+"</span></div>\\
			</div>\\
			<div class='state_info_flex'>\\
				<div class='state_item'><span>" + ((lan && lan.site && t('site.expiration_date')) || '到期时间：') + "</span><span class='btlink'>" + ((lan && lan.site && t('site.remaining_1')) || '剩余') + rdata['cert_data']['endtime'] + ((lan && lan.site && t('site.due_date')) || '天到期') + "</span></div>\\
				<div class='state_item'><span>" + ((lan && lan.site && t('site.verified_domain')) || '认证域名：') + "</span><span class='ellipsis_text'>"+domains+"</span></div>\\
			</div>";
			$(".ssl_state_info").html(cert_data);
			$(".ssl_state_info").css('display','block');
		}
	},'json');
}`;

functions.opSSLLet = `function opSSLLet(type, id, siteName, callback){
	var lets = '<div class="apply_ssl">\\
		<div class="label-input-group">\\
	  		<div class="line">\\
	  			<span class="tname text-center">' + ((lan && lan.site && t('site.admin_email')) || '管理员邮箱') + '</span>\\
	  			<input class="bt-input-text" style="width:240px;" type="text" name="admin_email" />\\
	  		</div>\\
	  		<div class="line mtb10">\\
	  			<span class="tname text-center">' + ((lan && lan.site && t('site.domain_name_5')) || '域名') + '</span>\\
	  			<ul id="ymlist" style="padding: 5px 10px;max-height:180px;overflow:auto; width:240px;border:#ccc 1px solid;border-radius:3px"></ul>\\
	  		</div>\\
	  		<div class="line mtb10" style="margin-left:100px">\\
	  			<button class="btn btn-success btn-sm letsApply">' + ((lan && lan.site && t('site.application')) || '申请') + '</button>\\
	  		</div>\\
	  	</div>\\
		<ul class="help-info-text c7" id="lets_help">\\
			<li>' + ((lan && lan.site && t('site.before_applying_please_make')) || '申请之前，请确保域名已解析，如未解析会导致审核失败') + '</li>\\
			<li>' + ((lan && lan.site && t('site.apply_for_free_certificate_2')) || "由Let's Encrypt免费申请证书，有效期3个月，支持多域名。默认会自动续签") + '</li>\\
			<li>' + ((lan && lan.site && t('site.if_your_site_uses')) || '若您的站点使用了CDN或301重定向会导致续签失败') + '</li>\\
			<li>' + ((lan && lan.site && t('site.if_no_default_ssl_1')) || '在未指定SSL默认站点时,未开启SSL的站点使用HTTPS会直接访问到已开启SSL的站点') + '</li>\\
		</ul>\\
	</div>';
	$(".tab-con").html(lets);

	$.post('/site/get_ssl','site_name='+siteName+'&ssl_type=lets', function(data){
		var rdata = data['data'];
		if(rdata.csr == false){
			$.post('/site/get_site_domains','id='+id, function(rdata) {
				var data = rdata['data'];
				var opt='';
				for(var i=0;i<data.domains.length;i++){
					var isIP = isValidIP(data.domains[i].name);
					var x = isContains(data.domains[i].name, '*');
					if(!isIP && !x){
						opt += '<li style="line-height:26px">\\
							<input type="checkbox" style="margin-right:5px; vertical-align:-2px" value="'+data.domains[i].name+'">'+data.domains[i].name
						+'</li>';
					}
				}
				$("input[name='admin_email']").val(data.email);
				$("#ymlist").html(opt);
				$("#ymlist li input").on('click', function(e){
					e.stopPropagation();
				});
				$("#ymlist li").on('click', function(){
					var o = $(this).find("input");
					if(o.prop("checked")){
						o.prop("checked",false);
					}
					else{
						o.prop("checked",true);
					}
				});
				$(".letsApply").on('click', function(){
					var c = $("#ymlist input[type='checkbox']");
					var str = [];
					var domains = '';
					for(var i=0; i<c.length; i++){
						if(c[i].checked){
							str.push(c[i].value);
						}
					}
					domains = JSON.stringify(str);
					newSSL(siteName, id, domains);
				});

				if (typeof (callback) != 'undefined'){
					callback(rdata);
				}
			},'json');
			return;
		}
		var lets = '<div class="myKeyCon ptb15">\\
				<div class="ssl_state_info" style="display:none;"></div>\\
				<div class="custom_certificate_info">\\
					<div class="ssl-con-key pull-left mr20" readonly>' + ((lan && lan.site && t('site.key_key')) || '密钥(KEY)') + '<br><textarea id="key" class="bt-input-text">'+rdata.key+'</textarea></div>\\
					<div class="ssl-con-key pull-left" readonly>' + ((lan && lan.site && t('site.certificate_pem_format_2')) || '证书(PEM格式)') + '<br><textarea id="csr" class="bt-input-text">'+rdata.csr+'</textarea></div>\\
				</div>\\
				<div class="ssl-btn pull-left mtb15" style="width:100%">\\
					<button class="btn btn-success btn-sm" onclick="deploySSL(\\'lets\\','+id+',\\''+siteName+'\\')">' + ((lan && lan.site && t('site.btlink_3')) || '部署') + '</button>\\
					<button class="btn btn-success btn-sm" onclick="renewSSL(\\'lets\\','+id+',\\''+siteName+'\\')">' + ((lan && lan.site && t('site.renewal')) || '续签') + '</button>\\
					<button class="btn btn-success btn-sm" onclick="deleteSSL(\\'lets\\','+id+',\\''+siteName+'\\')">' + ((lan && lan.site && t('site.delete_4')) || '删除') + '</button>\\
				</div>\\
			</div>\\
			<ul class="help-info-text c7 pull-left">\\
				<li>' + ((lan && lan.site && t('site.free_let_encrypt_certificate')) || "已为您自动生成Let's Encrypt免费证书") + '</li>\\
				<li>' + ((lan && lan.site && t('site.apply_for_free_certificate_2')) || "由Let's Encrypt免费申请证书，有效期3个月，支持多域名。默认会自动续签") + '</li>\\
				<li>' + ((lan && lan.site && t('site.paste_key_pem_other')) || '如需使用其他SSL,请切换其他证书后粘贴您的KEY以及PEM内容，然后保存即可。') + '</li>\\
			</ul>';
		$(".tab-con").html(lets);

		if (rdata['cert_data']){
			var issuer_o = rdata['cert_data']['issuer_o'] || ((lan && lan.site && t('site.self_signed_unknown')) || '自签名/未知');
			var issuer = rdata['cert_data']['issuer'] || ((lan && lan.site && t('site.unknown')) || '未知');
			var domains = rdata['cert_data']['dns'].join("、");

			var cert_data = "<div class='state_info_flex'>\\
				<div class='state_item'><span>" + ((lan && lan.site && t('site.certificate_categories')) || '证书分类：') + "</span><span class='ellipsis_text'>"+issuer_o+"</span></div>\\
				<div class='state_item'><span>" + ((lan && lan.site && t('site.certificate_brand')) || '证书品牌：') + "</span><span class='ellipsis_text'>"+issuer+"</span></div>\\
			</div>\\
			<div class='state_info_flex'>\\
				<div class='state_item'><span>" + ((lan && lan.site && t('site.expiration_date')) || '到期时间：') + "</span><span class='btlink'>" + ((lan && lan.site && t('site.remaining_1')) || '剩余') + rdata['cert_data']['endtime'] + ((lan && lan.site && t('site.due_date')) || '天到期') + "</span></div>\\
				<div class='state_item'><span>" + ((lan && lan.site && t('site.verified_domain')) || '认证域名：') + "</span><span class='ellipsis_text'>"+domains+"</span></div>\\
			</div>";
			$(".ssl_state_info").html(cert_data);
			$(".ssl_state_info").css('display','block');
		}
	},'json');
}`;

functions.ocSSL = `function ocSSL(action,siteName){
	var loadT = layer.msg(((lan && lan.site && t('site.retrieving_the_certificate_list')) || '正在获取证书列表，请稍后..'),{icon:16,time:0,shade: [0.3, '#000']});
	$.post("/site/"+action,'siteName='+siteName+'&updateOf=1',function(rdata){
		layer.close(loadT);
		
		if(!rdata.status){
			if(!rdata.out){
				layer.msg(rdata.msg,{icon:rdata.status?1:2});
				setSSL(siteName);
				return;
			}
			data = "<p>" + ((lan && lan.site && t('site.failed_to_obtain_the')) || '证书获取失败：') + "</p><hr />";
			for(var i=0;i<rdata.out.length;i++){
				data += "<p>" + ((lan && lan.site && t('site.domain_name_3')) || '域名:') + " "+rdata.out[i].Domain+"</p>"
					  + "<p>" + ((lan && lan.site && t('site.error_1')) || '错误类型:') + " "+rdata.out[i].Type+"</p>"
					  + "<p>" + ((lan && lan.site && t('site.details')) || '详情:') + " "+rdata.out[i].Detail+"</p>"
					  + "<hr />";
			}
			layer.msg(data,{icon:2,time:0,shade:0.3,shadeClose:true});
			return;
		}
		layer.msg(rdata.msg,{icon:rdata.status?1:2});
		if(action == 'close_ssl_conf'){
			layer.msg(((lan && lan.site && t('site.closed_ssl_please_be_sure')) || '已关闭SSL,请务必清除浏览器缓存后再访问站点!'),{icon:1,time:5000});
		}
		$(".tab-nav .on").click();
	},'json');
}`;

functions.rewrite = `function rewrite(website){
	$.post('/site/get_rewrite_list','siteName='+website,function(rdata){
		var rlist = '';
		for(var i=0;i<rdata.rewrite.length;i++){
			rlist += "<option value='"+rdata.rewrite[i]+"'>"+rdata.rewrite[i]+"</option>";
		}
		var webBakHtml = "<div class='webedit-box soft-man-con'>\\
						<div class='line'>\\
						<span class='mr5'>" + ((lan && lan.site && t('site.0_template')) || '0.伪静态模板') + "</span>\\
						<select class='bt-input-text' style='width: 260px; margin-right: 15px;' id='myRewrite' name='rewrite'>"+rlist+"</select>\\
						<textarea class='bt-input-text' style='height: 260px; width: 740px; line-height:18px;margin-top:10px;padding:5px;' id='rewriteBody'></textarea></div>\\
						<button id='SetRewriteBtn' class='btn btn-success btn-sm'>" + ((lan && lan.site && t('site.save_3')) || '保存') + "</button>\\
						<button id='SetRewriteBtnTel' class='btn btn-success btn-sm'>" + ((lan && lan.site && t('site.save_as_template')) || '另存为模板') + "</button>\\
						<ul class='help-info-text c7 ptb15'>\\
							<li>" + ((lan && lan.site && t('site.please_your_application_if')) || '请选择您的应用，若设置伪静态后，网站无法正常访问，请尝试设置回default') + "</li>\\
							<li>" + ((lan && lan.site && t('site.you_can_modify_rewrite')) || '您可以对伪静态规则进行修改，修改完后保存即可。') + "</li>\\
						</ul>\\
						</div>";
			$("#webedit-con").html(webBakHtml);
			var editor = CodeMirror.fromTextArea(document.getElementById("rewriteBody"), {
				extraKeys: {
					"Ctrl-Space": "autocomplete",
					"Ctrl-F": "findPersistent",
					"Ctrl-H": "replace",
					"Ctrl-/": function(cm) {
						cm.toggleComment({
							indent: true,
							padding: " ",
							comment: "#"
						});
					},
					"Ctrl-S": function() {
						$("#rewriteBody").empty();
						$("#rewriteBody").text(editor.getValue());
						setRewrite(filename, encodeURIComponent(editor.getValue()));
					},
					"Cmd-S": function() {
						$("#rewriteBody").empty();
						$("#rewriteBody").text(editor.getValue());
						setRewrite(filename, encodeURIComponent(editor.getValue()));
					}
				},
				lineNumbers: true,
				matchBrackets: true,
				mode: "nginx"
			});
			$(".CodeMirror-scroll").css({"height":"300px","margin":0,"padding":0});
			$("#SetRewriteBtn").on('click', function(){
				$("#rewriteBody").empty();
				$("#rewriteBody").text(editor.getValue());
				setRewrite(filename, encodeURIComponent(editor.getValue()));
			});
			$("#SetRewriteBtnTel").on('click', function(){
				$("#rewriteBody").empty();
				$("#rewriteBody").text(editor.getValue());
				setRewriteTel();
			});
			$("#myRewrite").on('change', function(){
				var rewriteName = $(this).val();
				if(rewriteName == '0.当前'){
					var rpath = '/www/server/vhost/rewrite/'+website+'.conf';
					filename = rpath;
					$.post('/files/get_body','path='+rpath,function(fileBody){
						$("#rewriteBody").val(fileBody['data']['data']);
						editor.setValue(fileBody['data']['data']);
					},'json');
				}else{
					$.post('/site/get_rewrite_tpl', {tplname:rewriteName,siteName:website}, function(fileBody){
						$("#rewriteBody").val(fileBody['data']['data']);
						editor.setValue(fileBody['data']['data']);
					},'json');
				}
			});
			var rpath = '/www/server/vhost/rewrite/'+website+'.conf';
			var filename = rpath;
			$.post('/files/get_body','path='+rpath,function(fileBody){
				var centent = fileBody['data']['data'];
				editor.setValue(centent);
			},'json');
	},'json');
}`;

module.exports = functions;
