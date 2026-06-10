
function ftpPost(method,args,callback){
	var _args = null; 
	if (typeof(args) == 'string'){
		_args = JSON.stringify(toArrayObject(args));
	} else {
		_args = JSON.stringify(args);
	}

    var loadT = layer.msg('正在获取...', { icon: 16, time: 0, shade: 0.3 });
    $.post('/plugins/run', {name:'pureftp', func:method, args:_args}, function(data) {
        layer.close(loadT);
        if (!data.status){
            layer.msg(data.msg,{icon:0,time:2000,shade: [0.3, '#000']});
            return;
        }
        if(typeof(callback) == 'function'){
            callback(data);
        }
    },'json'); 
}


function ftpAsyncPost(method,args){
	return syncPost('/plugins/run',
		{name:'pureftp', func:method, args:JSON.stringify(args)}
	);
}

function ftpListFind(){
    var search = $('#ftp_find_user').val();
    if (search==''){
        layer.msg('搜索字符不能为空!',{icon:0,time:2000,shade: [0.3, '#000']});
        return;
    }
    ftpList(1, search);
}

function ftpList(page, search){
	var _data = {};
    if (typeof(page) =='undefined'){
        var page = 1;
    }
    
    _data['page'] = page;
    _data['page_size'] = 10;
    if(typeof(search) != 'undefined'){
        _data['search'] = search;
    }

    ftpPost('get_ftp_list', _data, function(data){

        var rdata = $.parseJSON(data.data);
        // console.log(rdata);
        content = '<div class="info-title-tips" style="display: flex; justify-content: space-between; align-items: center;"><p style="margin: 0;"><span class="glyphicon glyphicon-alert" style="color: #f39c12; margin-right: 10px;"></span>当前FTP地址为：ftp://'+rdata['info']['ip']+':'+rdata['info']['port']+'</p>';
        content += '<button class="btn btn-default btn-sm" onclick="modFtpPort(0,\''+rdata['info']['port']+'\')">修改端口</button></div>';
        content += '<div class="finduser"><input class="bt-input-text mr5 outline_no" type="text" placeholder="查找用户名" id="ftp_find_user" style="height: 28px; border-radius: 3px;width: 150px;">';
        content += '<button class="btn btn-success btn-sm" onclick="ftpListFind();">查找</button>';
        content += '<button class="btn btn-success btn-sm" style="margin-left: 10px;" onclick="addFtp();"><span class="glyphicon glyphicon-plus" style="margin-right: 5px;"></span>新增用户</button></div>';

        content += '<div class="divtable" style="margin-top:5px;"><table class="table table-hover" width="100%" cellspacing="0" cellpadding="0" border="0">';
        content += '<thead><tr>';
        content += '<th style="width:10%;overflow:hidden;">用户名</th>';
        content += '<th style="width:10%;overflow:hidden;">密码</th>';
        content += '<th style="width:10%;">状态</th>';
        content += '<th>根目录</th>';
        content += '<th>备注</th>';
        content += '<th>操作</th>';
        content += '</tr></thead>';

        content += '<tbody>';

        ulist = rdata.data;
        for (i in ulist){
        	// console.log(ulist[i]);
        	status = '<a href="javascript:;" onclick="ftpStart(\''+ulist[i]['id']+'\',\''+ulist[i]['name']+'\')" <span="" style="color:red">已停用<span style="color:red" class="glyphicon glyphicon-pause"></span></a>';
        	if (ulist[i]['status'] == '1'){
        		status = '<a href="javascript:;" title="FTP帐户" onclick="ftpStop(\''+ulist[i]['id']+'\',\''+ulist[i]['name']+'\')"><span style="color:#5CB85C">已启用</span><span style="color:#5CB85C" class="glyphicon glyphicon-play"></span></a>';
        	}
            content += '<tr><td>'+ulist[i]['name']+'</td>'+
        		'<td>'+ulist[i]['password']+'</td>'+
        		'<td>'+status+'</td>' +
        		'<td>'+ulist[i]['path']+'</td>' +
        		'<td>'+ulist[i]['ps']+'</td>' +
            	'<td><a class="btlink" onclick="ftpModPwd(\''+ulist[i]['id']+'\',\''+ulist[i]['name']+'\',\''+ulist[i]['password']+'\')">改密</a> | ' +
            	'<a class="btlink" onclick="ftpDelete(\''+ulist[i]['id']+'\',\''+ulist[i]['name']+'\')">删除</a></td></tr>';
        }

        content += '</tbody>';
        content += '</table></div>';

        page = '<div class="dataTables_paginate paging_bootstrap pagination" style="margin-top:0px;"><ul id="softPage" class="page"><div>';
        page += rdata.page;
        page += '</div></ul></div>';

        content += page;

        $(".soft-man-con").html(content);
    });
}


/**
 *添加FTP帐户
 */
function addFtp() {

	var data = ftpAsyncPost('get_www_dir');
	var defaultPath = data.data;
	var indexFtp = layer.open({
		type: 1,
		area: '500px',
		title: '添加FTP帐户',
		closeBtn: 2,
		shift: 5,
		shadeClose: false,
		btn: ['提交','关闭'],
		content: "<form class='form pd20' id='ftpAdd'>\
					<div class='line'>\
					<span class='tname'>用户名</span>\
					<div class='info-r'><input class='bt-input-text' type='text' id='ftpUser' name='ftp_username' style='width:330px' /></div>\
					</div>\
					<div class='line'>\
					<span class='tname'>密码</span>\
					<div class='info-r'><input class='bt-input-text mr5' type='text' name='ftp_password' id='MyPassword' style='width:330px' value='"+(randomStrPwd(16))+"' /><span title='随机密码' class='glyphicon glyphicon-repeat cursor' onclick='repeatPwd(16)'></span></div>\
					</div>\
					<div class='line'>\
					<span class='tname'>根目录</span>\
					<div class='info-r'><input id='inputPath' class='bt-input-text mr5' type='text' name='path' value='"+defaultPath+"/' placeholder='"+lan.ftp.add_path_title+"'  style='width:330px' /><span class='glyphicon glyphicon-folder-open cursor' onclick='changePath(\"inputPath\")'></span><p class='c9 mt10'>"+lan.ftp.add_path_ps+"</p></div>\
					</div>\
                    <div class='line' style='display:none'>\
					<span class='tname'>备注</span>\
					<div class='info-r'>\
					<input id='ftp_ps' class='bt-input-text' type='text' name='ps' value='' placeholder='备注' />\
					</div></div>\
			      </form>",
		yes:function(index,layero){
			var loadT = layer.load({shade: true,shadeClose: false});
			var data = $("#ftpAdd").serialize();
			ftpPost('add_ftp', data, function(rdata){
				layer.close(loadT);
				layer.close(indexFtp);
				if (rdata.data == 'ok'){
					layer.msg('添加成功!', {icon: 1,time:3000});
				} else {
					layer.msg(rdata.data, {icon: 5,time:3000});
				}

				setTimeout(function(){ftpList();},2000);
			});
			return true;
        },
	});
	
	$("#ftpUser").keyup(function(){
		var ftpName = $(this).val();
		$("#inputPath").val(defaultPath+'/'+ftpName);
		$("#ftp_ps").val(ftpName);
	});
}


/**
 * 删除FTP帐户
 * @param {Number} id 
 * @param {String} ftp_username  欲被删除的用户名
 * @return {bool}
 */
function ftpDelete(id,ftp_username){
	safeMessage(lan.public.del+"["+ftp_username+"]",lan.get('confirm_del',[ftp_username]),function(){
		layer.msg(lan.public.the_del,{icon:16,time:0,shade: [0.3, '#000']});
		var data='&id='+id+'&username='+ftp_username;

		ftpPost('del_ftp', data, function(data){
			layer.msg('删除成功!', {icon: 1});
			ftpList();
		})
	});
}

function modFtpPort(type, port){
	var index = layer.open({
		type: 1,
		skin: 'demo-class',
		area: '500px',
		title: '修改FTP帐户端口',
		content: "<form class='bt-form pd20 pb70'>\
					<div class='line'>\
					<span class='tname'>默认端口</span>\
					<div class='info-r'><input class='bt-input-text mr5' type='text' id='ftpPort' name='ftp_port' style='width:330px' value='"+port+"'/></div>\
					</div>\
					<div class='bt-form-submit-btn'>\
						<button id='ftp_port_close' type='button' class='btn btn-danger btn-sm btn-title'>关闭</button>\
				        <button id='ftp_port_submit' type='button' class='btn btn-success btn-sm btn-title'>提交</button>\
			        </div>\
			      </form>",
	});

	$('#ftp_port_close').click(function(){
		$('.layui-layer-close1').click();
	});

	$('#ftp_port_submit').click(function(){
		var port = $('#ftpPort').val();
		data = 'port='+port
		ftpPost('mod_ftp_port', data,function(data){
			ftpList();
			if (data.data == 'ok'){
				layer.msg('修改成功!', {icon: 1});
			} else {
				layer.msg(data.data, {icon: 2});
			}
			$('.layui-layer-close1').click();
		});
	});

}


function ftpModPwd(id,name,password){
	var index = layer.open({
		type: 1,
		skin: 'demo-class',
		area: '500px',
		title: '修改FTP帐户密码',
		content: "<form class='bt-form pd20 pb70'>\
					<div class='line'>\
					<span class='tname'>用户名</span>\
					<div class='info-r'><input disabled class='bt-input-text mr5' type='text' id='ftpUser' name='ftp_username' style='width:330px' value='"+name+"'/></div>\
					</div>\
					\
					<div class='line'>\
					<span class='tname'>密码</span>\
					<div class='info-r'><input class='bt-input-text mr5' type='text' name='ftp_password' id='MyPassword' style='width:330px' value='"+password+"' /><span title='随机密码' class='glyphicon glyphicon-repeat cursor' onclick='repeatPwd(16)'></span></div>\
					</div>\
					<div class='bt-form-submit-btn'>\
						<button id='ftp_mod_close' type='button' class='btn btn-danger btn-sm btn-title'>关闭</button>\
				        <button id='ftp_mod_submit' type='button' class='btn btn-success btn-sm btn-title'>提交</button>\
			        </div>\
			      </form>",
	});


	$('#ftp_mod_close').click(function(){
		$('.layui-layer-close1').click();
	});

	$('#ftp_mod_submit').click(function(){
		pwd = $('#MyPassword').val();
		data='id='+id+'&name='+name+'&password='+pwd
		ftpPost('mod_ftp', data,function(data){
			ftpList();
			if (data.data == 'ok'){
				layer.msg('修改成功!', {icon: 1});
			}
			$('.layui-layer-close1').click();
		});
	});
}


/**
 * 停止FTP帐号
 * @param {Number} id	FTP的ID
 * @param {String} username	FTP用户名
 */
function ftpStop(id, username) {
	layer.confirm('您真的要停止{1}的FTP吗?'.replace('{1}',username), {
		title: 'FTP帐户',icon:3,
		closeBtn:2
	}, function(index) {
		if (index > 0) {
			var loadT = layer.load({shade: true,shadeClose: false});
			var data='id=' + id + '&username=' + username + '&status=0';
			ftpPost('stop_ftp', data, function(data){
				layer.close(loadT);
				if (data.data == 'ok'){
					showMsg('启动成功!', function(){
						ftpList();
					},{icon: 1});
				} else {
					layer.msg(data.data, {icon: 2});
				}
			});
		}
		$('.layui-layer-close1').click();
	});
}

/**
 * 启动FTP帐号
 * @param {Number} id	FTP的ID
 * @param {String} username	FTP用户名
 */
function ftpStart(id, username) {
	var loadT = layer.load({shade: true,shadeClose: false});
	var data='id=' + id + '&username=' + username + '&status=1';
	ftpPost('start_ftp', data, function(data){
		layer.close(loadT);
		if (data.data == 'ok'){
			showMsg('启动成功!', function(){
				ftpList();
			},{icon: 1});
		} else {
			layer.msg(data.data, {icon: 2});
		}
		
	});
}


function pureftpService() {
    var _name = "pureftp";
    var loadT = layer.msg("正在获取...", { icon: 16, time: 0, shade: 0.3 });
    $.post("/plugins/run", {name: "pureftp", func: "get_ftp_list", args: JSON.stringify({page:1, page_size:1000})}, function(rdata) {
        $.post("/plugins/run", {name: _name, func: "status"}, function(data) {
            layer.close(loadT);
            var _status = data.data;
            var m_status = "当前状态：<span>开启</span><span style=\"color:#20a53a; margin-left:3px;\" class=\"glyphicon glyphicon glyphicon-play\"></span>";
            if (_status != "start"){
                 m_status = "当前状态：<span>停止</span><span style=\"color:red; margin-left:3px;\" class=\"glyphicon glyphicon-pause\"></span>";
            }
            var m_btn = "<button class=\"btn btn-default btn-sm\" onclick=\"pluginOpService('"+_name+"', 'stop', '')\">停止</button> <button class=\"btn btn-default btn-sm\" onclick=\"pluginOpService('"+_name+"', 'restart', '')\">重启</button> <button class=\"btn btn-default btn-sm\" onclick=\"pluginOpService('"+_name+"', 'reload', '')\">重载配置</button>";
            if (_status != "start"){
                m_btn = "<button class=\"btn btn-success btn-sm\" onclick=\"pluginOpService('"+_name+"', 'start', '')\">启动</button>";
            }
            
            var con = "<p class=\"status\">"+m_status+"</p><div class=\"sfm-opt\">"+m_btn+"</div>";

            var ftpData = {info: {ip: "127.0.0.1", port: "21"}, data: []};
            try {
                ftpData = $.parseJSON(rdata.data);
            } catch(e) {}
            
            var innerIp = ftpData.info.ip;
            var outerIp = ftpData.info.external_ip || window.location.hostname;
            var port = ftpData.info.port;
            
            var style = `
            <style>
            .ftp-access-info {
                margin-top: 20px;
                border: 1px solid #d2d6de;
                border-radius: 6px;
                background-color: #fff;
                box-shadow: 0 2px 10px rgba(0, 123, 255, 0.08);
                overflow: hidden;
                font-size: 13px;
                color: #444;
            }
            .ftp-info-header {
                padding: 12px 15px;
                background: linear-gradient(135deg, #f5f7fa 0%, #eef2f5 100%);
                border-bottom: 1px solid #d2d6de;
                font-weight: 600;
                color: #2c3e50;
                font-size: 14px;
                display: flex;
                align-items: center;
            }
            .ftp-info-header .glyphicon {
                color: #007bff;
                margin-right: 8px;
                font-size: 16px;
            }
            .ftp-info-body {
                padding: 15px;
            }
            .ftp-info-item {
                display: flex;
                margin-bottom: 12px;
                align-items: center;
            }
            .ftp-info-item:last-child {
                margin-bottom: 0;
            }
            .ftp-info-label {
                width: 80px;
                color: #666;
                font-weight: 500;
            }
            .ftp-info-value {
                flex: 1;
                color: #007bff;
                font-family: Consolas, "Courier New", monospace;
                background: #f4f8ff;
                padding: 4px 10px;
                border-radius: 4px;
                border: 1px solid #d6e4f5;
                font-weight: 600;
            }
            .ftp-user-table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
            }
            .ftp-user-table th, .ftp-user-table td {
                padding: 8px 12px;
                border: 1px solid #eef2f5;
                text-align: left;
            }
            .ftp-user-table th {
                background-color: #f8f9fa;
                color: #555;
                font-weight: 600;
            }
            .ftp-user-table tr:hover td {
                background-color: #fdfdfe;
            }
            .ftp-user-table .user-badge {
                display: inline-block;
                background-color: #e3f2fd;
                color: #1976d2;
                padding: 2px 8px;
                border-radius: 12px;
                font-weight: 600;
                font-size: 12px;
            }
            .ftp-user-table .path-badge {
                font-family: Consolas, monospace;
                color: #4caf50;
            }
            </style>
            `;

            con += style;
            con += '<div class="ftp-access-info">';
            con += '<div class="ftp-info-header"><span class="glyphicon glyphicon-hdd"></span>FTP 连接与账号管理</div>';
            con += '<div class="ftp-info-body">';
            
            con += '<div class="ftp-info-item"><span class="ftp-info-label">内网地址</span><span class="ftp-info-value">ftp://' + innerIp + ':' + port + '</span></div>';
            if (innerIp !== outerIp) {
                con += '<div class="ftp-info-item"><span class="ftp-info-label">外网地址</span><span class="ftp-info-value">ftp://' + outerIp + ':' + port + '</span></div>';
            } else {
                con += '<div class="ftp-info-item"><span class="ftp-info-label">外网地址</span><span class="ftp-info-value" style="color:#888;border-color:#eee;background:#fafafa;">ftp://' + outerIp + ':' + port + ' (同内网)</span></div>';
            }
            
            if (ftpData.data && ftpData.data.length > 0) {
                con += '<table class="ftp-user-table">';
                con += '<thead><tr><th width="30%">FTP 用户名</th><th>绑定根目录</th></tr></thead><tbody>';
                for (var i = 0; i < ftpData.data.length; i++) {
                    con += '<tr>';
                    con += '<td><span class="user-badge">' + ftpData.data[i].name + '</span></td>';
                    con += '<td><span class="path-badge">' + ftpData.data[i].path + '</span></td>';
                    con += '</tr>';
                }
                con += '</tbody></table>';
            } else {
                con += '<div style="margin-top:15px; padding: 15px; background: #fdfdfe; border: 1px dashed #ccc; border-radius: 4px; text-align: center; color: #999;">暂无用户，请在“管理列表”中添加</div>';
            }
            
            con += '</div></div>';

            var fwTip = `
            <div class="ftp-firewall-tips" style="margin-top: 15px; padding: 15px; background-color: #fffaf0; border: 1px solid #ffeeba; border-left: 4px solid #f39c12; border-radius: 6px; font-size: 13px; color: #555;">
                <div style="font-weight: 600; color: #d35400; margin-bottom: 8px; font-size: 14px;">
                    <span class="glyphicon glyphicon-warning-sign" style="margin-right: 6px;"></span>云服务器与防火墙端口放行提示
                </div>
                <div style="line-height: 1.6;">若您使用的是云服务器（如阿里云、腾讯云等），除了面板自身的防火墙外，请<strong>务必前往云服务商的安全组控制台</strong>放行以下 TCP 端口：</div>
                <ul style="margin-top: 8px; margin-bottom: 0; padding-left: 20px; line-height: 1.6;">
                    <li><strong>控制端口：</strong> <span style="color:#c0392b;font-family:Consolas,monospace;background:#fdebd0;padding:2px 6px;border-radius:3px;">21</span> <span style="color:#888;">（用于 FTP 账号登录与主动模式）</span></li>
                    <li><strong>被动数据端口范围：</strong> <span style="color:#c0392b;font-family:Consolas,monospace;background:#fdebd0;padding:2px 6px;border-radius:3px;">39000-40000</span> <span style="color:#888;">（用于 FTP 被动模式下传输文件与目录列表，不放行会导致连接成功但无法读取目录）</span></li>
                </ul>
            </div>
            `;
            con += fwTip;

            $(".soft-man-con").html(con);
        }, "json");
    }, "json");
}
