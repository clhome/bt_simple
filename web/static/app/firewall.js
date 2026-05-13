setTimeout(function(){
	getSshInfo();
},500);
	
setTimeout(function(){
	showAccept(1);
},1000);

var currentType = 'port';
function switchTab(type, obj) {
    currentType = type;
    $(".tab-nav-view span").removeClass("active");
    $(obj).addClass("active");
    
    if (type == 'port') {
        $("#port_firewall_view").show();
        $("#ip_firewall_view").hide();
        $("#th_protocol").show();
        $("#th_port").text("端口/IP");
    } else {
        $("#port_firewall_view").hide();
        $("#ip_firewall_view").show();
        $("#th_protocol").hide();
        $("#th_port").text("IP地址/段");
    }
    showAccept(1);
}

	
$(function(){
	// start 
	$.post('/firewall/get_www_path',function(data){
		var html ='<a class="btlink" href="javascript:openPath(\''+data['path']+'\');">日志目录</a>\
				<em id="logSize">0KB</em>\
				<button class="btn btn-default btn-sm" onclick="closeLogs();">清空</button>';
		$('#firewall_weblog').html(html);

		$.post('/files/get_dir_size','path='+data['path'], function(rdata){
			$("#logSize").html(rdata.msg);
		},'json');
	},'json');
	// end
});

function closeLogs(){
	$.post('/files/close_logs','',function(rdata){
		$("#logSize").html(rdata.msg);
		layer.msg('已清理!',{icon:1});
	},'json');
}

$("#firewalldType").change(function(){
	var type = $(this).val();
	var t = '放行';
	var m = '说明: 仅输入开始端口即可放行单个端口';
	$("#port_input_group").show();
	$("#AcceptAddress").hide();
	$("#toAccept").html(t);
	$("#f-ps").html(m);
});

// 自动同步结束端口
$("#AcceptPortStart").on('keyup change', function(){
	$("#AcceptPortEnd").val($(this).val());
});


function sshMgr(){
	$.post('/firewall/get_ssh_info', '', function(rdata){
		var ssh_status = rdata.status ? 'checked':'';
		var pass_prohibit_status = rdata.pass_prohibit_status ? 'checked':'';
		var pubkey_prohibit_status = rdata.pubkey_prohibit_status ? 'checked':'';
		var root_prohibit_status = rdata.root_prohibit_status ? 'checked':'';
		var con = '<div class="pd15">\
            <div class="divtable">\
                <table class="table table-hover waftable">\
                    <thead><tr><th>名称</th><th width="80">状态</th></tr></thead>\
                    <tbody>\
                        <tr>\
                            <td>启动SSH</td>\
                            <td>\
                                <div class="ssh-item" style="margin-left:0">\
                                    <input class="btswitch btswitch-ios" id="sshswitch" type="checkbox" '+ssh_status+'>\
                                    <label class="btswitch-btn" for="sshswitch" onclick=\'setMstscStatus()\'></label>\
                                </div>\
                            </td>\
                        </tr>\
                        <tr>\
                            <td>禁止root登陆</td>\
                            <td>\
                                <div class="ssh-item" style="margin-left:0">\
                                    <input class="btswitch btswitch-ios" id="root_status" type="checkbox" '+root_prohibit_status+'>\
                                    <label class="btswitch-btn" for="root_status" onclick=\'setSshRootStatus()\'></label>\
                                </div>\
                            </td>\
                        </tr>\
                        <tr>\
                            <td>禁止密码登陆</td>\
                            <td>\
                                <div class="ssh-item" style="margin-left:0">\
                                    <input class="btswitch btswitch-ios" id="pass_status" type="checkbox" '+pass_prohibit_status+'>\
                                    <label class="btswitch-btn" for="pass_status" onclick=\'setSshPassStatus()\'></label>\
                                </div>\
                            </td>\
                        </tr>\
                        <tr>\
                            <td>禁止密钥登陆</td>\
                            <td>\
                                <div class="ssh-item" style="margin-left:0">\
                                    <input class="btswitch btswitch-ios" id="pubkey_status" type="checkbox" '+pubkey_prohibit_status+'>\
                                    <label class="btswitch-btn" for="pubkey_status" onclick=\'setSshPubkeyStatus()\'></label>\
                                </div>\
                            </td>\
                        </tr>\
                    </tbody>\
                </table>\
            </div>\
        </div>';
        layer.open({
	        type: 1,
	        title: "SSH管理",
	        area: ['300px', '310px'],
	        closeBtn: 1,
	        shadeClose: false,
	        content: '<div id="ssh_list">'+con+'</div>',
	        success:function(){
	        },
	    });
	},'json');
}


function getSshInfo(){
	$.post('/firewall/get_ssh_info', '', function(rdata){
		if(!rdata.status){
			$("#mstscPort").attr('disabled','disabled');
		}
		
		$("#mstscPort").val(rdata.port);
		var isPint = '';
		if(rdata.ping){
			isPing = "<input class='btswitch btswitch-ios' id='noping' type='checkbox'><label class='btswitch-btn' for='noping' onclick='ping(1)'></label>";
		}else{
			isPing = "<input class='btswitch btswitch-ios' id='noping' type='checkbox' checked><label class='btswitch-btn' for='noping' onclick='ping(0)'></label>";
		}
		$("#is_ping").html(isPing);

		// console.log(rdata.firewall_status);
		var fStatus = '';
		if (rdata.firewall_status){
			fStatus = "<input class='btswitch btswitch-ios' id='firewall_status' type='checkbox' checked><label class='btswitch-btn' for='firewall_status' onclick='firewall(1)'></label>";
		}else{
			fStatus = "<input class='btswitch btswitch-ios' id='firewall_status' type='checkbox'><label class='btswitch-btn' for='firewall_status' onclick='firewall(0)'></label>";
		}
		$("#firewall_status").html(fStatus);
		
		// showAccept(1);

	},'json');
}


/**
 * 修改远程端口
 */

function mstsc(port) {
	layer.confirm('更改远程端口时，将会注消所有已登录帐户，您真的要更改远程端口吗？', {title: '远程端口'}, function(index) {
		var data = "port=" + port;
		var loadT = layer.load({
			shade: true,
			shadeClose: false
		});
		$.post('/firewall/set_ssh_port', data, function(ret) {
			layer.msg(ret.msg,{icon:ret.status?1:2})
			layer.close(loadT);
			getSshInfo();
		},'json');
	});
}

/**
 * 更改禁ping状态
 * @param {Int} state 0.禁ping 1.可ping
 */
function ping(status){
	var msg = status == 1 ? '禁PING后不影响服务器正常使用，但无法ping通服务器，您真的要禁PING吗？' : '解除禁PING状态可能会被黑客发现您的服务器，您真的要解禁吗？';
	layer.confirm(msg,{title:'是否禁ping',closeBtn:2,cancel:function(){
		if(status == 1){
			$("#noping").prop("checked",true);
		} else {
			$("#noping").prop("checked",false);
		}
	}},function(){
		layer.msg('正在处理,请稍候...',{icon:16,time:20000});
		$.post('/firewall/set_ping','status='+status, function(data) {
			layer.closeAll();
			if (data['status'] == true) {
				if(status == 1){
					layer.msg(data['msg'], {icon: 1});
				} else {
					layer.msg('已解除禁PING', {icon: 1});
				}
				setTimeout(function(){window.location.reload();},3000);
			} else {
				layer.msg('连接服务器失败', {icon: 2});
			}
		},'json');
	},function(){
		if(status == 1){
			$("#noping").prop("checked",true);
		} else {
			$("#noping").prop("checked",false);
		}
	});
}



/**
 * 更改防火墙状态
 * @param {Int} state 0,开启 1.禁用
 */
function firewall(status){
	var msg = status == 1 ? '禁用防火墙会增加服务器不安全性，您真的要禁用防火墙吗？' : '开启防火墙,增加服务器安全!';
	layer.confirm(msg,{title:'是否开启防火墙!',closeBtn:2,cancel:function(){
		if(status == 1){
			$("#firewall_status").prop("checked",true);
		} else {
			$("#firewall_status").prop("checked",false);
		}
	}},function(){
		layer.msg('正在处理,请稍候...',{icon:16,time:20000});
		$.post('/firewall/set_fw','status='+status, function(data) {
			layer.closeAll();
			if (data['status'] == true) {
				layer.msg(data['msg'], {icon: 1});
				setTimeout(function(){window.location.reload();},3000);
			} else {
				layer.msg('连接服务器失败', {icon: 2});
			}
		},'json');
	},function(){
		if(status == 1){
			$("#firewall_status").prop("checked",true);
		} else {
			$("#firewall_status").prop("checked",false);
		}
	});
}


/**
 * 设置远程服务状态
 * @param {Int} state 0.启用 1.关闭
 */
function setMstscStatus(){
	status = $("#sshswitch").prop("checked")==true?1:0;
	var msg = status==1?'停用SSH服务的同时也将注销所有已登录用户,继续吗？':'确定启用SSH服务吗？';
	layer.confirm(msg,{title:'警告',closeBtn:2,cancel:function(){
		if(status == 0){
			$("#sshswitch").prop("checked",false);
		} else {
			$("#sshswitch").prop("checked",true);
		}
	}},function(index){
		if(index > 0){
			layer.msg('正在处理,请稍候...',{icon:16,time:20000});
			$.post('/firewall/set_ssh_status','status='+status,function(rdata){
				layer.msg(rdata.msg,{icon:rdata.status?1:2});
			},'json');
		}
	},function(){
		if(status == 0){
			$("#sshswitch").prop("checked",false);
		} else {
			$("#sshswitch").prop("checked",true);
		}
	});
}

/**
 * 设置远程服务状态
 * @param {Int} state 0.启用 1.关闭
 */
function setSshRootStatus(){
	status = $("#root_status").prop("checked")==true?1:0;
	var msg = status==1?'开启密码登陆,继续吗？':'确定禁止密码登陆吗？';
	layer.confirm(msg,{title:'警告',closeBtn:2,cancel:function(){
		if(status == 0){
			$("#root_status").prop("checked",false);
		} else {
			$("#root_status").prop("checked",true);
		}
	}},function(index){
		if(index > 0){
			layer.msg('正在处理,请稍候...',{icon:16,time:20000});
			$.post('/firewall/set_ssh_root_status','status='+status,function(rdata){
				layer.msg(rdata.msg,{icon:rdata.status?1:2});
			},'json');
		}
	},function(){
		if(status == 0){
			$("#root_status").prop("checked",false);
		} else {
			$("#root_status").prop("checked",true);
		}
	});
}

/**
 * 设置远程服务状态
 * @param {Int} state 0.启用 1.关闭
 */
function setSshPassStatus(){
	status = $("#pass_status").prop("checked")==true?1:0;
	var msg = status==1?'开启密码登陆,继续吗？':'确定禁止密码登陆吗？';
	layer.confirm(msg,{title:'警告',closeBtn:2,cancel:function(){
		if(status == 0){
			$("#pass_status").prop("checked",false);
		} else {
			$("#pass_status").prop("checked",true);
		}
	}},function(index){
		if(index > 0){
			layer.msg('正在处理,请稍候...',{icon:16,time:20000});
			$.post('/firewall/set_ssh_pass_status','status='+status,function(rdata){
				layer.msg(rdata.msg,{icon:rdata.status?1:2});
			},'json');
		}
	},function(){
		if(status == 0){
			$("#pass_status").prop("checked",false);
		} else {
			$("#pass_status").prop("checked",true);
		}
	});
}



/**
 * 设置远程服务状态
 * @param {Int} state 0.启用 1.关闭
 */
function setSshPubkeyStatus(){
	status = $("#pubkey_status").prop("checked")==true?1:0;
	var msg = status==1?'开启密码登陆,继续吗？':'确定禁止密码登陆吗？';
	layer.confirm(msg,{title:'警告',closeBtn:2,cancel:function(){
		if(status == 0){
			$("#pubkey_status").prop("checked",false);
		} else {
			$("#pubkey_status").prop("checked",true);
		}
	}},function(index){
		if(index > 0){
			layer.msg('正在处理,请稍候...',{icon:16,time:20000});
			$.post('/firewall/set_ssh_pubkey_status','status='+status,function(rdata){
				layer.msg(rdata.msg,{icon:rdata.status?1:2});
			},'json');
		}
	},function(){
		if(status == 0){
			$("#pubkey_status").prop("checked",false);
		} else {
			$("#pubkey_status").prop("checked",true);
		}
	});
}



/**
 * 取回数据
 * @param {Int} page  分页号
 */
function showAccept(page) {
	var search_port = "";
	var search_ps = "";
	if (currentType == 'port') {
		search_port = $("#SearchPort").val();
		search_ps = $("#SearchPs").val();
	} else {
		search_port = $("#SearchIp").val();
		search_ps = $("#SearchIpPs").val();
	}
	var stype = currentType == 'port' ? 'port' : ''; // stype will be set by the active selection if not 'port'

	var loadT = layer.load();
	$.post('/firewall/get_list','limit=10&p=' + page+"&search_port="+search_port+"&search_ps="+search_ps+"&stype="+currentType, function(data) {
		layer.close(loadT);
		var body = '';
		for (var i = 0; i < data.data.length; i++) {
			var status = "<div class='ssh-item' style='margin-left:0'>\
					<input class='btswitch btswitch-ios' id='firewall_switch_"+data.data[i].id+"' type='checkbox' "+(data.data[i].status==1?'checked':'')+">\
					<label class='btswitch-btn' for='firewall_switch_"+data.data[i].id+"' onclick=\"setFirewallStatus(" + data.data[i].id + ",'" + data.data[i].port + "','"+data.data[i].protocol+"',"+(data.data[i].status==1?0:1)+")\"></label>\
				</div>";
			
			var protocol_td = currentType == 'port' ? "<td>" + data.data[i].protocol + "</td>" : "";
			var port_display = data.data[i].port;
			if (currentType == 'port'){
				port_display = (data.data[i].port.indexOf('.') == -1?'放行端口'+':['+data.data[i].port+']':'屏蔽IP'+':['+data.data[i].port+']');
			} else {
				var type_text = data.data[i].type == 'address_allow' ? '<span style="color:#20a53a;">放行IP</span>' : '<span style="color:red;">禁止IP</span>';
				port_display = type_text + ':[' + data.data[i].port + ']';
			}

			body += "<tr>\
				<td><em class='dlt-num'>" + data.data[i].id + "</em></td>\
				" + protocol_td + "\
				<td>" + port_display + "</td>\
				<td>" + status + "</td>\
				<td>" + data.data[i].ps + "</td>\
				<td>" + data.data[i].add_time + "</td>\
				<td class='text-right'><a href='javascript:;' class='btlink' onclick=\"delAcceptPort(" + data.data[i].id + ",'" + data.data[i].port + "','"+data.data[i].protocol+"')\">删除</a></td>\
			</tr>";
		}

		if (data.data.length == 0){
			var colspan = currentType == 'port' ? 7 : 6;
			body = '<tr><td colspan="'+colspan+'" style="text-align: center;">当前没有数据</td></tr>';
		}

		$("#firewall_body").html(body);
		$("#firewall_page").html(data.page);
	},'json');
}

//添加放行
function addAcceptPort(){
	var type = $("#firewalldType").val();
	var ps = $("#Ps").val();
	var protocol = $('select[name="protocol"]').val();
	var action = "add_drop_address";
	var port = "";

	if(type == 'port'){
		var startPort = $("#AcceptPortStart").val();
		var endPort = $("#AcceptPortEnd").val();

		if(isNaN(startPort) || startPort < 1 || startPort > 65535 ){
			layer.msg('开始端口范围不合法!',{icon:5});
			return;
		}
		if(isNaN(endPort) || endPort < 1 || endPort > 65535 ){
			layer.msg('结束端口范围不合法!',{icon:5});
			return;
		}

		if (parseInt(endPort) < parseInt(startPort)){
			layer.msg('结束端口不能小于开始端口!',{icon:5});
			return;
		}

		if (startPort == endPort){
			port = startPort;
		} else {
			port = startPort + ":" + endPort;
		}
		action = "add_accept_port";
	}
	
	if(ps.length < 1){
		layer.msg('备注/说明 不能为空!',{icon:2});
		$("#Ps").focus();
		return;
	}
	var loadT = layer.msg('正在添加,请稍候...',{icon:16,time:0,shade: [0.3, '#000']})
	$.post('/firewall/'+action,'port='+port+"&ps="+ps+'&type='+type+'&protocol='+protocol,function(rdata){
		layer.close(loadT);
		if(rdata.status == true || rdata.status == 'true'){
			layer.msg(rdata.msg,{icon:1});
			showAccept(1);
			$("#AcceptPortStart").val('');
			$("#AcceptPortEnd").val('');
			$("#AcceptAddress").val('');
			$("#Ps").val('');
		}else{
			layer.msg(rdata.msg,{icon:2});
		}
	},'json');
}

function addIpFirewall() {
    var stype = $("#ipFirewallAction").val();
    var ip = $("#IpAddress").val();
    var ps = $("#IpPs").val();

    if (ip == "") {
        layer.msg("请输入IP地址", {icon: 2});
        return;
    }

    if (ps == "") {
        layer.msg("请输入备注", {icon: 2});
        return;
    }

    var doAdd = function() {
        var loadT = layer.msg('正在添加,请稍候...', {icon: 16, time: 0, shade: [0.3, '#000']})
        $.post('/firewall/add_accept_port', 'port=' + ip + "&ps=" + ps + '&type=' + stype + '&protocol=tcp/udp', function(rdata) {
            layer.close(loadT);
            if (rdata.status) {
                layer.msg(rdata.msg, {icon: 1});
                showAccept(1);
                $("#IpAddress").val('');
                $("#IpPs").val('');
            } else {
                layer.msg(rdata.msg, {icon: 2});
            }
        }, 'json');
    }

    if (stype == 'address_allow') {
        layer.confirm('<span style="color:red;font-weight:bold;">警告：放行该IP将允许其访问服务器所有端口，存在安全风险！</span><br>仅建议用于临时测试，用完请及时关闭。确定继续吗？', {
            title: '高风险操作提示',
            icon: 0,
            btn: ['确定', '取消']
        }, function() {
            doAdd();
        });
    } else {
        $.post('/firewall/get_client_ip', '', function(rdata) {
            var clientIp = rdata.ip;
            if (ip == clientIp) {
                layer.msg('当前客户端IP为：' + clientIp + '<br><span style="color:red;">禁止将其设为黑名单，否则您将无法访问面板！</span>', {icon: 2, time: 5000});
            } else {
                layer.confirm('确定要将IP [' + ip + '] 加入黑名单吗？该IP将无法访问本服务器任何端口。', {
                    title: '黑名单确认',
                    icon: 0
                }, function() {
                    doAdd();
                });
            }
        });
    }
}

//删除放行
function delAcceptPort(id, port,protocol) {
	var action = "del_drop_address";
	if (currentType == 'port'){
		if(port.indexOf('.') == -1){
			action = "del_accept_port";
		}
	} else {
		action = "del_accept_port";
	}
	
	layer.confirm(lan.get('confirm_del',[port]), {title: '删除防火墙规则',closeBtn:2}, function(index) {
		var loadT = layer.msg('正在删除,请稍候...',{icon:16,time:0,shade: [0.3, '#000']})
		$.post("/firewall/"+action, "id=" + id + "&port=" + port+'&protocol='+protocol+'&stype='+currentType, function(ret) {
			layer.close(loadT);
			layer.msg(ret.msg,{icon:ret.status?1:2})
			showAccept(1);
		},'json');
	});
}

function setFirewallStatus(id, port, protocol, status){
	var loadT = layer.msg('正在处理,请稍候...',{icon:16,time:0,shade: [0.3, '#000']})
	$.post('/firewall/set_firewall_status','id='+id+"&port="+port+"&protocol="+protocol+"&status="+status+"&stype="+currentType,function(rdata){
		layer.close(loadT);
		layer.msg(rdata.msg,{icon:rdata.status?1:2});
		showAccept(1);
	},'json');
}

function syncServer() {
    var loadT = layer.msg('正在同步服务器防火墙规则, 请稍候...', {icon: 16, time: 0, shade: [0.3, '#000']});
    $.post('/firewall/sync_server', '', function(rdata) {
        layer.close(loadT);
        if (rdata.status) {
            layer.msg(rdata.msg, {icon: 1});
            showAccept(1);
        } else {
            layer.msg(rdata.msg, {icon: 2});
        }
    }, 'json').error(function() {
        layer.close(loadT);
        layer.msg('同步请求失败，请检查网络连接或服务器状态。', {icon: 2});
    });
}
