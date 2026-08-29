var currentType = 'port';
var currentSortDir = ''; // '', 'asc', 'desc'

function togglePortSort() {
  if (currentSortDir === '') {
    currentSortDir = 'asc';
  } else if (currentSortDir === 'asc') {
    currentSortDir = 'desc';
  } else {
    currentSortDir = '';
  }
  var icon = $('#port_sort_icon');
  icon.removeClass('glyphicon-sort glyphicon-sort-by-attributes glyphicon-sort-by-attributes-alt');
  if (currentSortDir === 'asc') {
    icon.addClass('glyphicon-sort-by-attributes').css('color', '#333');
  } else if (currentSortDir === 'desc') {
    icon.addClass('glyphicon-sort-by-attributes-alt').css('color', '#333');
  } else {
    icon.addClass('glyphicon-sort').css('color', '#ccc');
  }
  showAccept(1);
}
function switchTab(type, obj) {
  currentType = type;
  $(".tab-nav-view span").removeClass("active");
  $(obj).addClass("active");
  if (type == 'port') {
    $("#port_firewall_view").show();
    $("#ip_firewall_view").hide();
    $("#th_protocol").show();
    $("#th_port_status").show();
    $("#th_port").text(lan && lan.firewall && t('firewall.firewall_auto_str_1') || "");
  } else {
    $("#port_firewall_view").hide();
    $("#ip_firewall_view").show();
    $("#th_protocol").hide();
    $("#th_port_status").hide();
    $("#th_port").text(lan && lan.firewall && t('firewall.firewall_auto_str_2') || "");
  }
  showAccept(1);
}
$(function () {
  getSshInfo();
  showAccept(1);

  // start 
  $.post('/firewall/get_www_path', function (data) {
    var html = '<a class="btlink" href="javascript:openPath(\'' + data['path'] + '\');">日志目录</a><em id="logSize">0KB</em><button class="btn btn-default btn-sm" onclick="closeLogs();">清空</button>';
    $('#firewall_weblog').html(html);
    $.post('/files/get_dir_size', 'path=' + data['path'], function (rdata) {
      $("#logSize").html(rdata.msg);
    }, 'json');
  }, 'json');
  // end
});
function closeLogs() {
  $.post('/files/close_logs', '', function (rdata) {
    $("#logSize").html(rdata.msg);
    layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_4') || "", {
      icon: 1
    });
  }, 'json');
}
$("#firewalldType").on('change', function () {
  var type = $(this).val();
  var t = lan && lan.firewall && t('firewall.firewall_auto_str_5') || "";
  var m = lan && lan.firewall && t('firewall.firewall_auto_str_6') || "";
  $("#port_input_group").show();
  $("#AcceptAddress").hide();
  $("#toAccept").html(t);
  $("#f-ps").html(m);
});

// 自动同步结束端口
$("#AcceptPortStart").on('keyup change', function () {
  $("#AcceptPortEnd").val($(this).val());
});
function sshMgr() {
  $.post('/firewall/get_ssh_info', '', function (rdata) {
    var ssh_status = rdata.status ? 'checked' : '';
    var pass_prohibit_status = !rdata.pass_prohibit_status ? 'checked' : '';
    var pubkey_prohibit_status = !rdata.pubkey_prohibit_status ? 'checked' : '';
    var root_prohibit_status = !rdata.root_prohibit_status ? 'checked' : '';
    var con = '<div class="pd15" style="padding: 20px;">' +
      '<div style="display: flex; flex-direction: column; gap: 15px;">' +
      '<div style="display: flex; justify-content: space-between; align-items: center; padding-bottom: 12px; border-bottom: 1px solid #f0f0f0;">' +
      '<span style="font-size: 14px; font-weight: 500; color: #333;">' + (lan && lan.firewall && lan.firewall.start_ssh || '启动SSH') + '</span>' +
      '<div class="ssh-item" style="margin-left:0">' +
      '<input class="btswitch btswitch-ios" id="sshswitch" type="checkbox" ' + ssh_status + '>' +
      '<label class="btswitch-btn" for="sshswitch" onclick="setMstscStatus()"></label>' +
      '</div></div>' +
      '<div style="display: flex; justify-content: space-between; align-items: center; padding-bottom: 12px; border-bottom: 1px solid #f0f0f0;">' +
      '<span style="font-size: 14px; font-weight: 500; color: #333;">' + (lan && lan.firewall && lan.firewall.allow_root || '允许root登陆') + '</span>' +
      '<div class="ssh-item" style="margin-left:0">' +
      '<input class="btswitch btswitch-ios" id="root_status" type="checkbox" ' + root_prohibit_status + '>' +
      '<label class="btswitch-btn" for="root_status" onclick="setSshRootStatus()"></label>' +
      '</div></div>' +
      '<div style="display: flex; justify-content: space-between; align-items: center; padding-bottom: 12px; border-bottom: 1px solid #f0f0f0;">' +
      '<span style="font-size: 14px; font-weight: 500; color: #333;">' + (lan && lan.firewall && lan.firewall.allow_pass || '允许密码登陆') + '</span>' +
      '<div class="ssh-item" style="margin-left:0">' +
      '<input class="btswitch btswitch-ios" id="pass_status" type="checkbox" ' + pass_prohibit_status + '>' +
      '<label class="btswitch-btn" for="pass_status" onclick="setSshPassStatus()"></label>' +
      '</div></div>' +
      '<div style="display: flex; justify-content: space-between; align-items: center; padding-bottom: 12px; border-bottom: 1px solid #f0f0f0;">' +
      '<span style="font-size: 14px; font-weight: 500; color: #333;">' + (lan && lan.firewall && lan.firewall.allow_pubkey || '允许密钥登陆') + '</span>' +
      '<div class="ssh-item" style="margin-left:0">' +
      '<input class="btswitch btswitch-ios" id="pubkey_status" type="checkbox" ' + pubkey_prohibit_status + '>' +
      '<label class="btswitch-btn" for="pubkey_status" onclick="setSshPubkeyStatus()"></label>' +
      '</div></div>' +
      '<div style="display: flex; justify-content: space-between; align-items: center; padding-top: 5px;">' +
      '<span style="font-size: 14px; font-weight: 500; color: #333;">' + (lan && lan.firewall && lan.firewall.root_key || 'Root密钥') + '</span>' +
      '<div class="ssh-item" style="margin-left:0; display: flex; gap: 10px;">' +
      '<button class="btn btn-default btn-sm" onclick="downloadRootKey()" style="border-radius: 4px; padding: 5px 12px; font-size: 12px; color: #555;">' + (lan && lan.firewall && lan.firewall.download_key || '下载密钥') + '</button>' +
      '<button class="btn btn-default btn-sm" onclick="resetRootKey()" style="border-radius: 4px; padding: 5px 12px; font-size: 12px; color: #555;">' + (lan && lan.firewall && lan.firewall.reset_key || '重置/生成密钥') + '</button>' +
      '</div></div></div></div>';
    layer.open({
      type: 1,
      title: lan && lan.firewall && t('firewall.firewall_auto_str_12') || "",
      area: ['420px', 'auto'],
      closeBtn: 1,
      shadeClose: false,
      content: '<div id="ssh_list">' + con + '</div>',
      success: function () {}
    });
  }, 'json');
}
function getSshInfo() {
  $.post('/firewall/get_ssh_info', '', function (rdata) {
    if (!rdata.status) {
      $("#mstscPort").attr('disabled', 'disabled');
    }
    $("#mstscPort").val(rdata.port);
    var isPint = '';
    if (rdata.ping) {
      isPing = "<input class='btswitch btswitch-ios' id='noping' type='checkbox'><label class='btswitch-btn' for='noping' onclick='ping(1)'></label>";
    } else {
      isPing = "<input class='btswitch btswitch-ios' id='noping' type='checkbox' checked><label class='btswitch-btn' for='noping' onclick='ping(0)'></label>";
    }
    $("#is_ping").html(isPing);

    // console.log(rdata.firewall_status);
    var fStatus = '';
    if (rdata.firewall_status) {
      fStatus = "<input class='btswitch btswitch-ios' id='firewall_status' type='checkbox' checked><label class='btswitch-btn' for='firewall_status' onclick='firewall(1)'></label>";
    } else {
      fStatus = "<input class='btswitch btswitch-ios' id='firewall_status' type='checkbox'><label class='btswitch-btn' for='firewall_status' onclick='firewall(0)'></label>";
    }
    $("#firewall_status_container").html(fStatus);

    // showAccept(1);
  }, 'json');
}

/**
 * 修改远程端口
 */

function mstsc(port) {
  layer.confirm(lan && lan.firewall && t('firewall.firewall_auto_str_13') || "", {
    title: lan && lan.firewall && t('firewall.firewall_auto_str_14') || ""
  }, function (index) {
    var data = "port=" + port;
    var loadT = layer.load({
      shade: true,
      shadeClose: false
    });
    $.post('/firewall/set_ssh_port', data, function (ret) {
      layer.msg(ret.msg, {
        icon: ret.status ? 1 : 2
      });
      layer.close(loadT);
      getSshInfo();
    }, 'json');
  });
}

/**
 * 更改禁ping状态
 * @param {Int} state 0.禁ping 1.可ping
 */
function ping(status) {
  var msg = status == 1 ? lan && lan.firewall && t('firewall.firewall_auto_str_15') || "" : lan && lan.firewall && t('firewall.firewall_auto_str_16') || "";
  layer.confirm(msg, {
    title: lan && lan.firewall && t('firewall.firewall_auto_str_17') || "",
    closeBtn: 2,
    cancel: function () {
      if (status == 1) {
        $("#noping").prop("checked", true);
      } else {
        $("#noping").prop("checked", false);
      }
    }
  }, function () {
    layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_18') || "", {
      icon: 16,
      time: 20000
    });
    $.post('/firewall/set_ping', 'status=' + status, function (data) {
      layer.closeAll();
      if (data['status'] == true) {
        if (status == 1) {
          layer.msg(data['msg'], {
            icon: 1
          });
        } else {
          layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_19') || "", {
            icon: 1
          });
        }
        setTimeout(function () {
          window.location.reload();
        }, 3000);
      } else {
        layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_20') || "", {
          icon: 2
        });
      }
    }, 'json');
  }, function () {
    if (status == 1) {
      $("#noping").prop("checked", true);
    } else {
      $("#noping").prop("checked", false);
    }
  });
}

/**
 * 更改防火墙状态
 * @param {Int} state 0,开启 1.禁用
 */
function firewall(status) {
  var msg = status == 1 ? lan && lan.firewall && t('firewall.firewall_auto_str_21') || "" : lan && lan.firewall && t('firewall.firewall_auto_str_22') || "";
  layer.confirm(msg, {
    title: lan && lan.firewall && t('firewall.firewall_auto_str_23') || "",
    closeBtn: 2,
    cancel: function () {
      if (status == 1) {
        $("#firewall_status").prop("checked", true);
      } else {
        $("#firewall_status").prop("checked", false);
      }
    }
  }, function () {
    layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_24') || "", {
      icon: 16,
      time: 20000
    });
    $.post('/firewall/set_fw', 'status=' + status, function (data) {
      layer.closeAll();
      if (data['status'] == true) {
        layer.msg(data['msg'], {
          icon: 1
        });
        setTimeout(function () {
          window.location.reload();
        }, 3000);
      } else {
        layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_25') || "", {
          icon: 2
        });
      }
    }, 'json');
  }, function () {
    if (status == 1) {
      $("#firewall_status").prop("checked", true);
    } else {
      $("#firewall_status").prop("checked", false);
    }
  });
}

/**
 * 设置远程服务状态
 * @param {Int} state 0.启用 1.关闭
 */
function setMstscStatus() {
  status = $("#sshswitch").prop("checked") == true ? 1 : 0;
  var msg = status == 1 ? lan && lan.firewall && t('firewall.firewall_auto_str_26') || "" : lan && lan.firewall && t('firewall.firewall_auto_str_27') || "";
  layer.confirm(msg, {
    title: lan && lan.firewall && t('firewall.firewall_auto_str_28') || "",
    closeBtn: 2,
    cancel: function () {
      if (status == 0) {
        $("#sshswitch").prop("checked", false);
      } else {
        $("#sshswitch").prop("checked", true);
      }
    }
  }, function (index) {
    if (index > 0) {
      layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_29') || "", {
        icon: 16,
        time: 20000
      });
      $.post('/firewall/set_ssh_status', 'status=' + status, function (rdata) {
        layer.msg(rdata.msg, {
          icon: rdata.status ? 1 : 2
        });
      }, 'json');
    }
  }, function () {
    if (status == 0) {
      $("#sshswitch").prop("checked", false);
    } else {
      $("#sshswitch").prop("checked", true);
    }
  });
}

/**
 * 设置远程服务状态
 * @param {Int} state 0.启用 1.关闭
 */
function setSshRootStatus() {
  var checked = $("#root_status").prop("checked");
  var status = checked ? 0 : 1;
  var msg = checked ? lan && lan.firewall && t('firewall.firewall_auto_str_30') || "" : lan && lan.firewall && t('firewall.firewall_auto_str_31') || "";
  layer.confirm(msg, {
    title: lan && lan.firewall && t('firewall.firewall_auto_str_32') || "",
    closeBtn: 2,
    cancel: function () {
      if (checked) {
        $("#root_status").prop("checked", false);
      } else {
        $("#root_status").prop("checked", true);
      }
    }
  }, function (index) {
    if (index > 0) {
      layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_33') || "", {
        icon: 16,
        time: 20000
      });
      $.post('/firewall/set_ssh_root_status', 'status=' + status, function (rdata) {
        layer.msg(rdata.msg, {
          icon: rdata.status ? 1 : 2
        });
      }, 'json');
    }
  }, function () {
    if (checked) {
      $("#root_status").prop("checked", false);
    } else {
      $("#root_status").prop("checked", true);
    }
  });
}

/**
 * 设置远程服务状态
 * @param {Int} state 0.启用 1.关闭
 */
function setSshPassStatus() {
  var checked = $("#pass_status").prop("checked");
  var status = checked ? 0 : 1;
  var msg = checked ? lan && lan.firewall && t('firewall.firewall_auto_str_34') || "" : lan && lan.firewall && t('firewall.firewall_auto_str_35') || "";
  layer.confirm(msg, {
    title: lan && lan.firewall && t('firewall.firewall_auto_str_36') || "",
    closeBtn: 2,
    cancel: function () {
      if (checked) {
        $("#pass_status").prop("checked", false);
      } else {
        $("#pass_status").prop("checked", true);
      }
    }
  }, function (index) {
    if (index > 0) {
      layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_37') || "", {
        icon: 16,
        time: 20000
      });
      $.post('/firewall/set_ssh_pass_status', 'status=' + status, function (rdata) {
        layer.msg(rdata.msg, {
          icon: rdata.status ? 1 : 2
        });
      }, 'json');
    }
  }, function () {
    if (checked) {
      $("#pass_status").prop("checked", false);
    } else {
      $("#pass_status").prop("checked", true);
    }
  });
}

/**
 * 设置远程服务状态
 * @param {Int} state 0.启用 1.关闭
 */
function setSshPubkeyStatus() {
  var checked = $("#pubkey_status").prop("checked");
  var status = checked ? 0 : 1;
  var msg = checked ? lan && lan.firewall && t('firewall.firewall_auto_str_38') || "" : lan && lan.firewall && t('firewall.firewall_auto_str_39') || "";
  layer.confirm(msg, {
    title: lan && lan.firewall && t('firewall.firewall_auto_str_40') || "",
    closeBtn: 2,
    cancel: function () {
      if (checked) {
        $("#pubkey_status").prop("checked", false);
      } else {
        $("#pubkey_status").prop("checked", true);
      }
    }
  }, function (index) {
    if (index > 0) {
      layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_41') || "", {
        icon: 16,
        time: 20000
      });
      $.post('/firewall/set_ssh_pubkey_status', 'status=' + status, function (rdata) {
        layer.msg(rdata.msg, {
          icon: rdata.status ? 1 : 2
        });
      }, 'json');
    }
  }, function () {
    if (checked) {
      $("#pubkey_status").prop("checked", false);
    } else {
      $("#pubkey_status").prop("checked", true);
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
  var postData = 'limit=10&p=' + page + "&search_port=" + search_port + "&search_ps=" + search_ps + "&stype=" + currentType;
  if (currentType === 'port' && typeof currentSortDir !== 'undefined' && currentSortDir !== '') {
    postData += "&sort_dir=" + currentSortDir;
  }
  $.post('/firewall/get_list', postData, function (data) {
    layer.close(loadT);
    var body = '';
    for (var i = 0; i < data.data.length; i++) {
      var status = "<div class='ssh-item' style='margin-left:0'>\
					<input class='btswitch btswitch-ios' id='firewall_switch_" + data.data[i].id + "' type='checkbox' " + (data.data[i].status == 1 ? 'checked' : '') + ">\
					<label class='btswitch-btn' for='firewall_switch_" + data.data[i].id + "' onclick=\"setFirewallStatus(" + data.data[i].id + ",'" + data.data[i].port + "','" + data.data[i].protocol + "'," + (data.data[i].status == 1 ? 0 : 1) + ")\"></label>\
				</div>";
      var protocol_td = currentType == 'port' ? "<td>" + data.data[i].protocol + "</td>" : "";
      var port_display = data.data[i].port;
      if (currentType == 'port') {
        port_display = data.data[i].port.indexOf('.') == -1 ? data.data[i].port : (lan && lan.firewall && t('firewall.firewall_auto_str_42') || "") + data.data[i].port + ']';
      } else {
        var type_text = data.data[i].type == 'address_allow' ? '<span style="color:#20a53a;">' + (lan && lan.firewall && lan.firewall.allow_ip || '放行IP') + '</span>' : '<span style="color:red;">' + (lan && lan.firewall && lan.firewall.ban_ip || '禁止IP') + '</span>';
        port_display = type_text + ':[' + data.data[i].port + ']';
      }
      var port_status_td = "";
      if (currentType == 'port') {
        if (data.data[i].port_status) {
          var ps = data.data[i].port_status;
          var ps_json = encodeURIComponent(JSON.stringify(ps));
          port_status_td = "<td><a href='javascript:;' class='btlink' onclick=\"showPortProcessInfo('" + ps_json + "', '" + data.data[i].port + "')\">" + ps.name + "</a></td>";
        } else {
          port_status_td = "<td></td>";
        }
      }
      body += "<tr>\
				<td><em class='dlt-num'>" + data.data[i].id + "</em></td>\
				" + protocol_td + "\
				<td>" + port_display + "</td>\
				" + port_status_td + "\
				<td>" + status + "</td>\
				<td>" + data.data[i].ps + "</td>\
				<td>" + data.data[i].add_time + "</td>\
				<td class='text-right'><a href='javascript:;' class='btlink' onclick=\"delAcceptPort(" + data.data[i].id + ",'" + data.data[i].port + "','" + data.data[i].protocol + (lan && lan.firewall && t('firewall.firewall_auto_str_45') || "");
    }
    if (data.data.length == 0) {
      var colspan = currentType == 'port' ? 8 : 6;
      body = '<tr><td colspan="' + colspan + (lan && lan.firewall && t('firewall.firewall_auto_str_46') || "");
    }
    $("#firewall_body").html(body);
    $("#firewall_page").html(data.page);
  }, 'json');
}

//添加放行
function addAcceptPort() {
  var type = $("#firewalldType").val();
  var ps = $("#Ps").val();
  var protocol = $('select[name="protocol"]').val();
  var action = "add_drop_address";
  var port = "";
  if (type == 'port') {
    var startPort = $("#AcceptPortStart").val();
    var endPort = $("#AcceptPortEnd").val();
    if (isNaN(startPort) || startPort < 1 || startPort > 65535) {
      layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_47') || "", {
        icon: 5
      });
      return;
    }
    if (isNaN(endPort) || endPort < 1 || endPort > 65535) {
      layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_48') || "", {
        icon: 5
      });
      return;
    }
    if (parseInt(endPort) < parseInt(startPort)) {
      layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_49') || "", {
        icon: 5
      });
      return;
    }
    if (startPort == endPort) {
      port = startPort;
    } else {
      port = startPort + ":" + endPort;
    }
    action = "add_accept_port";
  }
  if (ps.length < 1) {
    layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_50') || "", {
      icon: 2
    });
    $("#Ps").trigger('focus');
    return;
  }
  var loadT = layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_51') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/firewall/' + action, 'port=' + port + "&ps=" + ps + '&type=' + type + '&protocol=' + protocol, function (rdata) {
    layer.close(loadT);
    if (rdata.status == true || rdata.status == 'true') {
      layer.msg(rdata.msg, {
        icon: 1
      });
      showAccept(1);
      $("#AcceptPortStart").val('');
      $("#AcceptPortEnd").val('');
      $("#AcceptAddress").val('');
      $("#Ps").val('');
    } else {
      layer.msg(rdata.msg, {
        icon: 2
      });
    }
  }, 'json');
}
function addIpFirewall() {
  var stype = $("#ipFirewallAction").val();
  var ip = $("#IpAddress").val();
  var ps = $("#IpPs").val();
  if (ip == "") {
    layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_52') || "", {
      icon: 2
    });
    return;
  }
  if (ps == "") {
    layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_53') || "", {
      icon: 2
    });
    return;
  }
  var doAdd = function () {
    var loadT = layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_54') || "", {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.post('/firewall/add_accept_port', 'port=' + ip + "&ps=" + ps + '&type=' + stype + '&protocol=tcp/udp', function (rdata) {
      layer.close(loadT);
      if (rdata.status) {
        layer.msg(rdata.msg, {
          icon: 1
        });
        showAccept(1);
        $("#IpAddress").val('');
        $("#IpPs").val('');
      } else {
        layer.msg(rdata.msg, {
          icon: 2
        });
      }
    }, 'json');
  };
  if (stype == 'address_allow') {
    layer.confirm('<span style="color:red;font-weight:bold;">警告：放行该IP将允许其访问服务器所有端口，存在安全风险！</span><br>仅建议用于临时测试，用完请及时关闭。确定继续吗？', {
      title: lan && lan.firewall && t('firewall.firewall_auto_str_56') || "",
      icon: 0,
      btn: [lan && lan.firewall && t('firewall.firewall_auto_str_57') || "", lan && lan.firewall && t('firewall.firewall_auto_str_58') || ""]
    }, function () {
      doAdd();
    });
  } else {
    $.post('/firewall/get_client_ip', '', function (rdata) {
      var clientIp = rdata.ip;
      if (ip == clientIp) {
        layer.msg((lan && lan.firewall && t('firewall.firewall_auto_str_59') || "") + clientIp + (lan && lan.firewall && t('firewall.firewall_auto_str_60') || ""), {
          icon: 2,
          time: 5000
        });
      } else {
        layer.confirm((lan && lan.firewall && t('firewall.firewall_auto_str_61') || "") + ip + (lan && lan.firewall && t('firewall.firewall_auto_str_62') || ""), {
          title: lan && lan.firewall && t('firewall.firewall_auto_str_63') || "",
          icon: 0
        }, function () {
          doAdd();
        });
      }
    });
  }
}

//删除放行
function delAcceptPort(id, port, protocol) {
  var action = "del_drop_address";
  if (currentType == 'port') {
    if (port.indexOf('.') == -1) {
      action = "del_accept_port";
    }
  } else {
    action = "del_accept_port";
  }
  layer.confirm(t('confirm_del', [port]), {
    title: lan && lan.firewall && t('firewall.firewall_auto_str_64') || "",
    closeBtn: 2
  }, function (index) {
    var loadT = layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_65') || "", {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.post("/firewall/" + action, "id=" + id + "&port=" + port + '&protocol=' + protocol + '&stype=' + currentType, function (ret) {
      layer.close(loadT);
      layer.msg(ret.msg, {
        icon: ret.status ? 1 : 2
      });
      showAccept(1);
    }, 'json');
  });
}
function setFirewallStatus(id, port, protocol, status) {
  var loadT = layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_66') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/firewall/set_firewall_status', 'id=' + id + "&port=" + port + "&protocol=" + protocol + "&status=" + status + "&stype=" + currentType, function (rdata) {
    layer.close(loadT);
    layer.msg(rdata.msg, {
      icon: rdata.status ? 1 : 2
    });
    showAccept(1);
  }, 'json');
}
function syncServer() {
  var loadT = layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_67') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/firewall/sync_server', '', function (rdata) {
    layer.close(loadT);
    if (rdata.status) {
      layer.msg(rdata.msg, {
        icon: 1
      });
      showAccept(1);
    } else {
      layer.msg(rdata.msg, {
        icon: 2
      });
    }
  }, 'json').fail(function () {
    layer.close(loadT);
    layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_68') || "", {
      icon: 2
    });
  });
}
function showPortProcessInfo(ps_json, port) {
  var ps = JSON.parse(decodeURIComponent(ps_json));
  var con = '<div style="padding: 20px;">' +
        '<table class="table table-bordered table-hover" style="table-layout: fixed; word-wrap: break-word;">' +
        '<tbody>' +
        '<tr><td width="100" style="background-color: #f9f9f9; font-weight: bold;">进程名</td><td>' + ps.name + '</td></tr>' +
        '<tr><td style="background-color: #f9f9f9; font-weight: bold;">进程pid</td><td>' + ps.pid + '</td></tr>' +
        '<tr><td style="background-color: #f9f9f9; font-weight: bold;">启动命令</td><td>' + ps.cmdline + '</td></tr>' +
        '</tbody></table></div>';
  layer.open({
    type: 1,
    title: port + (lan && lan.firewall && t('firewall.firewall_auto_str_72') || ""),
    area: ['500px', '300px'],
    closeBtn: 1,
    shadeClose: false,
    content: con
  });
}
function downloadRootKey() {
  $.post('/firewall/check_root_ssh_key', function (rdata) {
    if (!rdata.status) {
      layer.msg(rdata.msg, {
        icon: 2
      });
      return;
    }
    window.open('/files/download?filename=/root/.ssh/id_ed25519');
  }, 'json');
}
function resetRootKey() {
  layer.confirm(lan && lan.firewall && t('firewall.firewall_auto_str_73') || "", {
    title: lan && lan.firewall && t('firewall.firewall_auto_str_74') || "",
    icon: 3
  }, function (index) {
    var loadT = layer.msg(lan && lan.firewall && t('firewall.firewall_auto_str_75') || "", {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.post('/firewall/reset_root_ssh_key', {}, function (rdata) {
      layer.close(loadT);
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2,
        time: 3000
      });
    }, 'json');
  });
}