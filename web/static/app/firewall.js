var currentType = 'port';
var currentSortDir = ''; // '', 'asc', 'desc'

/**
 * 端口/IP/协议/备注都来自数据库（用户可控），以前直接拼进 innerHTML：
 * 备注里存 <img src=x onerror=...> 就是存储型 XSS（/firewall/get_list 原样返回）。
 */
function yfFwText(v) {
  if (typeof YfI18n !== 'undefined' && YfI18n && typeof YfI18n.escapeHtml === 'function') {
    return YfI18n.escapeHtml(v == null ? '' : String(v));
  }
  return String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/**
 * 行内 onclick="fn('...')" 里的 JS 字符串字面量：HTML 转义挡不住注入
 * （浏览器会先把实体还原成引号再交给 JS 解析），必须按 JS 字符串转义；
 * 引号一律走实体，否则会直接终止 HTML 属性值，变成属性注入。
 */
function yfFwJsStr(v) {
  return String(v == null ? '' : v)
    .replace(/\\/g, '\\\\')
    .replace(/&/g, '&amp;')
    .replace(/'/g, "\\'")
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\r/g, '\\r')
    .replace(/\n/g, '\\n');
}

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
    $("#th_port").text(lan && lan.firewall && t('firewall.port_ip') || "");
  } else {
    $("#port_firewall_view").hide();
    $("#ip_firewall_view").show();
    $("#th_protocol").hide();
    $("#th_port_status").hide();
    $("#th_port").text(lan && lan.firewall && t('firewall.ip_address_range') || "");
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
    layer.msg(lan && lan.firewall && t('firewall.cleaned_up') || "", {
      icon: 1
    });
  }, 'json');
}
$("#firewalldType").on('change', function () {
  var type = $(this).val();
  var t = lan && lan.firewall && t('firewall.clearance') || "";
  var m = lan && lan.firewall && t('firewall.note_enter_only_the') || "";
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
      '<div style="display: flex;flex-wrap:wrap; justify-content: space-between; align-items: center; padding-bottom: 12px; border-bottom: 1px solid #f0f0f0;">' +
      '<span style="font-size: 14px; font-weight: 500; color: #333;">' + (lan && lan.firewall && lan.firewall.allow_pubkey || '允许密钥登陆') + '</span>' +
      '<div class="ssh-item" style="margin-left:0">' +
      '<input class="btswitch btswitch-ios" id="pubkey_status" type="checkbox" ' + pubkey_prohibit_status + '>' +
      '<label class="btswitch-btn" for="pubkey_status" onclick="setSshPubkeyStatus()"></label>' +
      '</div></div>' +
      '<div style="display: flex;flex-wrap:wrap; justify-content: space-between; align-items: center; padding-top: 5px;">' +
      '<span style="font-size: 14px; font-weight: 500; color: #333;">' + (lan && lan.firewall && lan.firewall.root_key || 'Root密钥') + '</span>' +
      '<div class="ssh-item" style="margin-left:0; display: flex; gap: 10px;">' +
      '<button class="btn btn-default btn-sm" onclick="downloadRootKey()" style="border-radius: 4px; padding: 5px 12px; font-size: 12px; color: #555;">' + (lan && lan.firewall && lan.firewall.download_key || '下载密钥') + '</button>' +
      '<button class="btn btn-default btn-sm" onclick="resetRootKey()" style="border-radius: 4px; padding: 5px 12px; font-size: 12px; color: #555;">' + (lan && lan.firewall && lan.firewall.reset_key || '重置/生成密钥') + '</button>' +
      '</div></div></div></div>';
    layer.open({
      type: 1,
      title: lan && lan.firewall && t('firewall.ssh_management') || "",
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
  layer.confirm(lan && lan.firewall && t('firewall.changing_the_remote_port') || "", {
    title: lan && lan.firewall && t('firewall.remote_port') || ""
  }, function (index) {
    var data = "port=" + encodeURIComponent(port);
    // 后端 500（例如旧实现的 set_ssh_port 收到非数字）时没有 .fail 会把这个
    // 全屏遮罩永久卡住（shadeClose:false，点都点不掉）
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
    }, 'json').fail(function () {
      layer.close(loadT);
      layer.msg(lan && lan.firewall && t('firewall.failed_to_connect_to') || "", {
        icon: 2
      });
    });
  });
}

/**
 * 更改禁ping状态
 * @param {Int} state 0.禁ping 1.可ping
 */
function ping(status) {
  var msg = status == 1 ? lan && lan.firewall && t('firewall.disabling_ping_will_not') || "" : lan && lan.firewall && t('firewall.lifting_the_ping_block') || "";
  layer.confirm(msg, {
    title: lan && lan.firewall && t('firewall.is_ping_blocked') || "",
    closeBtn: 2,
    cancel: function () {
      if (status == 1) {
        $("#noping").prop("checked", true);
      } else {
        $("#noping").prop("checked", false);
      }
    }
  }, function () {
    layer.msg(lan && lan.firewall && t('firewall.processing_please_wait') || "", {
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
          layer.msg(lan && lan.firewall && t('firewall.ping_restriction_has_been') || "", {
            icon: 1
          });
        }
        setTimeout(function () {
          window.location.reload();
        }, 3000);
      } else {
        layer.msg(lan && lan.firewall && t('firewall.failed_to_connect_to') || "", {
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
  var msg = status == 1 ? lan && lan.firewall && t('firewall.disabling_the_firewall_will') || "" : lan && lan.firewall && t('firewall.enable_the_firewall_to') || "";
  layer.confirm(msg, {
    title: lan && lan.firewall && t('firewall.is_the_firewall_enabled') || "",
    closeBtn: 2,
    cancel: function () {
      if (status == 1) {
        $("#firewall_status").prop("checked", true);
      } else {
        $("#firewall_status").prop("checked", false);
      }
    }
  }, function () {
    layer.msg(lan && lan.firewall && t('firewall.processing_please_wait_1') || "", {
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
        layer.msg(lan && lan.firewall && t('firewall.failed_to_connect_to_1') || "", {
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
  var msg = status == 1 ? lan && lan.firewall && t('firewall.disabling_the_ssh_service') || "" : lan && lan.firewall && t('firewall.are_you_sure_you') || "";
  layer.confirm(msg, {
    title: lan && lan.firewall && t('firewall.warning') || "",
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
      layer.msg(lan && lan.firewall && t('firewall.processing_please_wait_2') || "", {
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
  var msg = checked ? lan && lan.firewall && t('firewall.are_you_sure_you_1') || "" : lan && lan.firewall && t('firewall.are_you_sure_you_2') || "";
  layer.confirm(msg, {
    title: lan && lan.firewall && t('firewall.warning_1') || "",
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
      layer.msg(lan && lan.firewall && t('firewall.processing_please_wait_3') || "", {
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
  var msg = checked ? lan && lan.firewall && t('firewall.are_you_sure_you_3') || "" : lan && lan.firewall && t('firewall.are_you_sure_you_4') || "";
  layer.confirm(msg, {
    title: lan && lan.firewall && t('firewall.warning_2') || "",
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
      layer.msg(lan && lan.firewall && t('firewall.processing_please_wait_4') || "", {
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
  var msg = checked ? lan && lan.firewall && t('firewall.are_you_sure_you_5') || "" : lan && lan.firewall && t('firewall.are_you_sure_you_6') || "";
  layer.confirm(msg, {
    title: lan && lan.firewall && t('firewall.warning_3') || "",
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
      layer.msg(lan && lan.firewall && t('firewall.processing_please_wait_5') || "", {
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
      // 行内 onclick 的参数先按 JS 字符串转义（port/ps 都可能含引号）
      var row = data.data[i];
      var port_js = yfFwJsStr(row.port);
      var protocol_js = yfFwJsStr(row.protocol);
      var status = "<div class='ssh-item' style='margin-left:0'>\
					<input class='btswitch btswitch-ios' id='firewall_switch_" + data.data[i].id + "' type='checkbox' " + (data.data[i].status == 1 ? 'checked' : '') + ">\
					<label class='btswitch-btn' for='firewall_switch_" + data.data[i].id + "' onclick=\"setFirewallStatus(" + row.id + ",'" + port_js + "','" + protocol_js + "'," + (row.status == 1 ? 0 : 1) + ")\"></label>\
				</div>";
      var protocol_td = currentType == 'port' ? "<td>" + yfFwText(row.protocol) + "</td>" : "";
      var port_display = yfFwText(row.port);
      if (currentType == 'port') {
        port_display = row.port.indexOf('.') == -1 ? yfFwText(row.port) : (lan && lan.firewall && t('firewall.block_ip') || "") + yfFwText(row.port) + ']';
      } else {
        var type_text = row.type == 'address_allow' ? '<span style="color:#20a53a;">' + (lan && lan.firewall && lan.firewall.allow_ip || '放行IP') + '</span>' : '<span style="color:red;">' + (lan && lan.firewall && lan.firewall.ban_ip || '禁止IP') + '</span>';
        port_display = type_text + ':[' + yfFwText(row.port) + ']';
      }
      var port_status_td = "";
      if (currentType == 'port') {
        if (data.data[i].port_status) {
          var pinfo = row.port_status;
          var ps_json = encodeURIComponent(JSON.stringify(pinfo));
          port_status_td = "<td><a href='javascript:;' class='btlink' onclick=\"showPortProcessInfo('" + yfFwJsStr(ps_json) + "', '" + port_js + "')\">" + yfFwText(pinfo.name) + "</a></td>";
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
				<td>" + yfFwText(row.ps) + "</td>\
				<td>" + yfFwText(row.add_time) + "</td>\
				<td class='text-right'><a href='javascript:;' class='btlink' onclick=\"delAcceptPort(" + row.id + ",'" + port_js + "','" + protocol_js + '\')">' + (lan && lan.public && t('public.delete') || '删除') + '</a></td>\t\t\t</tr>';
    }
    if (data.data.length == 0) {
      var colspan = currentType == 'port' ? 8 : 6;
      body = '<tr><td colspan="' + colspan + '" style="text-align: center;">' + (lan && lan.firewall && t('firewall.no_data') || '当前没有数据') + '</td></tr>';
    }
    $("#firewall_body").html(body);
    $("#firewall_page").html(data.page);
  }, 'json').fail(function () {
    layer.close(loadT);
    layer.msg(lan && lan.firewall && t('firewall.failed_to_connect_to') || "", {
      icon: 2
    });
  });
}

//添加放行
function addAcceptPort() {
  var type = $("#firewalldType").val();
  var ps = $("#Ps").val();
  var protocol = $('select[name="protocol"]').val();
  // 后端只有 /firewall/add_accept_port：旧的 add_drop_address 路由并不存在，
  // 打过去会 404 -> 成功回调不执行 -> loading 遮罩永不关闭
  var action = "add_accept_port";
  var port = "";
  if (type == 'port') {
    var startPort = $("#AcceptPortStart").val();
    var endPort = $("#AcceptPortEnd").val();
    if (isNaN(startPort) || startPort < 1 || startPort > 65535) {
      layer.msg(lan && lan.firewall && t('firewall.the_starting_port_range') || "", {
        icon: 5
      });
      return;
    }
    if (isNaN(endPort) || endPort < 1 || endPort > 65535) {
      layer.msg(lan && lan.firewall && t('firewall.the_end_of_the') || "", {
        icon: 5
      });
      return;
    }
    if (parseInt(endPort) < parseInt(startPort)) {
      layer.msg(lan && lan.firewall && t('firewall.the_end_port_cannot') || "", {
        icon: 5
      });
      return;
    }
    if (startPort == endPort) {
      port = startPort;
    } else {
      port = startPort + ":" + endPort;
    }
  }
  if (ps.length < 1) {
    layer.msg(lan && lan.firewall && t('firewall.remarks_notes_cannot_be') || "", {
      icon: 2
    });
    $("#Ps").trigger('focus');
    return;
  }
  var loadT = layer.msg(lan && lan.firewall && t('firewall.adding_please_wait') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/firewall/add_accept_port', 'port=' + encodeURIComponent(port) + "&ps=" + encodeURIComponent(ps) + '&type=' + type + '&protocol=' + protocol, function (rdata) {
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
  }, 'json').fail(function () {
    layer.close(loadT);
    layer.msg(lan && lan.firewall && t('firewall.failed_to_connect_to') || "", {
      icon: 2
    });
  });
}
function addIpFirewall() {
  var stype = $("#ipFirewallAction").val();
  var ip = $("#IpAddress").val();
  var ps = $("#IpPs").val();
  if (ip == "") {
    layer.msg(lan && lan.firewall && t('firewall.please_enter_an_ip') || "", {
      icon: 2
    });
    return;
  }
  if (ps == "") {
    layer.msg(lan && lan.firewall && t('firewall.please_enter_note') || "", {
      icon: 2
    });
    return;
  }
  var doAdd = function () {
    var loadT = layer.msg(lan && lan.firewall && t('firewall.adding_please_wait_1') || "", {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.post('/firewall/add_accept_port', 'port=' + encodeURIComponent(ip) + "&ps=" + encodeURIComponent(ps) + '&type=' + stype + '&protocol=tcp/udp', function (rdata) {
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
    }, 'json').fail(function () {
      layer.close(loadT);
      layer.msg(lan && lan.firewall && t('firewall.failed_to_connect_to') || "", {
        icon: 2
      });
    });
  };
  if (stype == 'address_allow') {
    layer.confirm('<span style="color:red;font-weight:bold;">警告：放行该IP将允许其访问服务器所有端口，存在安全风险！</span><br>仅建议用于临时测试，用完请及时关闭。确定继续吗？', {
      title: lan && lan.firewall && t('firewall.high_risk_trading_alert') || "",
      icon: 0,
      btn: [lan && lan.firewall && t('firewall.confirm') || "", lan && lan.firewall && t('firewall.cancel') || ""]
    }, function () {
      doAdd();
    });
  } else {
    $.post('/firewall/get_client_ip', '', function (rdata) {
      var clientIp = rdata.ip;
      if (ip == clientIp) {
        layer.msg((lan && lan.firewall && t('firewall.the_current_client_ip') || "") + clientIp + '<br><span style="color:red;">' + (lan && lan.firewall && t('firewall.ban_warning') || '禁止将其设为黑名单，否则您将无法访问面板！') + '</span>', {
          icon: 2,
          time: 5000
        });
      } else {
        layer.confirm((lan && lan.firewall && t('firewall.are_you_sure_you_7') || "") + ip + (lan && lan.firewall && t('firewall.add_to_the_blacklist') || ""), {
          title: lan && lan.firewall && t('firewall.blacklist_confirmation') || "",
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
  // 后端只有 /firewall/del_accept_port：旧的 del_drop_address 分支会打到不存在的
  // 路由（404 -> 成功回调不执行 -> 这里的 loading 遮罩永远不关）
  layer.confirm(t('confirm_del', [port]), {
    title: lan && lan.firewall && t('firewall.delete_firewall_rules') || "",
    closeBtn: 2
  }, function (index) {
    var loadT = layer.msg(lan && lan.firewall && t('firewall.deleting_please_wait') || "", {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.post("/firewall/del_accept_port", "id=" + id + "&port=" + encodeURIComponent(port) + '&protocol=' + encodeURIComponent(protocol) + '&stype=' + currentType, function (ret) {
      layer.close(loadT);
      layer.msg(ret.msg, {
        icon: ret.status ? 1 : 2
      });
      showAccept(1);
    }, 'json').fail(function () {
      layer.close(loadT);
      layer.msg(lan && lan.firewall && t('firewall.failed_to_connect_to') || "", {
        icon: 2
      });
    });
  });
}
function setFirewallStatus(id, port, protocol, status) {
  var loadT = layer.msg(lan && lan.firewall && t('firewall.processing_please_wait_6') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/firewall/set_firewall_status', 'id=' + id + "&port=" + encodeURIComponent(port) + "&protocol=" + encodeURIComponent(protocol) + "&status=" + status + "&stype=" + currentType, function (rdata) {
    layer.close(loadT);
    layer.msg(rdata.msg, {
      icon: rdata.status ? 1 : 2
    });
    showAccept(1);
  }, 'json').fail(function () {
    layer.close(loadT);
    layer.msg(lan && lan.firewall && t('firewall.failed_to_connect_to') || "", {
      icon: 2
    });
  });
}
function syncServer() {
  var loadT = layer.msg(lan && lan.firewall && t('firewall.synchronizing_server_firewall_rules') || "", {
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
    layer.msg(lan && lan.firewall && t('firewall.the_synchronization_request_failed') || "", {
      icon: 2
    });
  });
}
function showPortProcessInfo(ps_json, port) {
  var ps = JSON.parse(decodeURIComponent(ps_json));
  // 进程名/命令行来自系统（用户可控的进程名同样能带 < > 引号）
  var con = '<div style="padding: 20px;">' +
        '<table class="table table-bordered table-hover" style="table-layout: fixed; word-wrap: break-word;">' +
        '<tbody>' +
        '<tr><td width="100" style="background-color: #f9f9f9; font-weight: bold;">进程名</td><td>' + yfFwText(ps.name) + '</td></tr>' +
        '<tr><td style="background-color: #f9f9f9; font-weight: bold;">进程pid</td><td>' + yfFwText(ps.pid) + '</td></tr>' +
        '<tr><td style="background-color: #f9f9f9; font-weight: bold;">启动命令</td><td>' + yfFwText(ps.cmdline) + '</td></tr>' +
        '</tbody></table></div>';
  layer.open({
    type: 1,
    title: yfFwText(port) + (lan && lan.firewall && t('firewall.details_on_processes_using') || ""),
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
  layer.confirm(lan && lan.firewall && t('firewall.after_the_reset_the') || "", {
    title: lan && lan.firewall && t('firewall.reset_root_key') || "",
    icon: 3
  }, function (index) {
    var loadT = layer.msg(lan && lan.firewall && t('firewall.the_key_pair_is') || "", {
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