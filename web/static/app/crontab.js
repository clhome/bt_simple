var num = 0;
var g_orderby = 'last_run_time';
var g_order = 'desc';
//查看任务日志
function getLogs(id, task_name) {
  if (typeof task_name == 'undefined') {
    task_name = '';
  }
  var reqTimer = null;
  var reqCount = 0;
  var tips = layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_1') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  var req_log_args = 'id=' + id;
  function requestLogs(layerIndex) {
    var is_refresh = $("#log_refresh_switch").prop('checked');
    if (reqCount > 0 && !is_refresh) return;
    $.post('/crontab/logs', req_log_args, function (rdata) {
      if (reqCount == 0) {
        layer.close(tips);
      }
      if (!rdata.status) {
        layer.close(layerIndex);
        layer.msg(rdata.msg, {
          icon: 2,
          time: 2000
        });
        clearInterval(reqTimer);
        return;
      }
      ;
      if (rdata.msg == '') {
        rdata.msg = lan && lan.crontab && t('crontab.crontab_auto_str_2') || "";
      }
      $("#crontab_log").html(rdata.msg);
      //滚动到最低
      var ob = document.getElementById('crontab_log');
      if (ob) ob.scrollTop = ob.scrollHeight;
      reqCount++;
    }, 'json');
  }
  layer.open({
    type: 1,
    title: lan && lan.crontab && t('crontab.crontab_auto_str_3') || "",
    area: ['60%', '660px'],
    shadeClose: false,
    btn: [lan && lan.crontab && t('crontab.crontab_auto_str_4') || "", lan && lan.crontab && t('crontab.crontab_auto_str_5') || ""],
    closeBtn: 1,
    end: function () {
      if (reqTimer) {
        clearInterval(reqTimer);
      }
    },
    content: '<div class="setchmod bt-form" style="padding:15px;">' + '<div style="margin-bottom: 10px; height: 30px;">' + '<div class="pull-left" style="line-height: 30px;">' + '<label style="font-weight: normal; cursor: pointer; color: #666; user-select: none; margin-right: 15px;">' + (lan && lan.crontab && t('crontab.crontab_auto_str_6') || "") + '</label>' + '<button class="btn btn-default btn-sm" onclick="startTask(' + id + ', \'' + (task_name || '').replace(/'/g, "\\'") + (lan && lan.crontab && t('crontab.crontab_auto_str_7') || "") + (task_name ? (lan && lan.crontab && t('crontab.crontab_auto_str_8') || "") + task_name + '</span>' : '') + '</div>' + '</div>' + '<pre id="crontab_log" style="overflow: auto; border: 0px none; line-height:23px;padding: 5px; margin: 0px; white-space: pre-wrap; height: 495px; background-color: rgb(51,51,51);color:#f1f1f1;border-radius:0px;font-family:"></pre>' + '</div>',
    success: function (layero, index) {
      requestLogs(index);
      reqTimer = setInterval(function () {
        requestLogs(index);
      }, 5000);
      var btnRow = layero.find('.layui-layer-btn');
      btnRow.find('.layui-layer-btn0').css({
        'float': 'left',
        'margin-left': '15px',
        'background-color': '#5cb85c',
        'border-color': '#4cae4c',
        'color': '#fff'
      });
    },
    yes: function (index, layero) {
      closeLogs(id, true);
      return false;
    },
    btn2: function (index, layero) {
      layer.close(index);
    }
  });
}
function getBackupName(hook_data, name) {
  for (var i = 0; i < hook_data.length; i++) {
    if (hook_data[i]['name'] == name) {
      return hook_data[i]['title'];
    }
  }
  return name;
}
function getCronData(page) {
  var search = $('#search_task').val() || '';
  var load = layer.msg(t('public.the'), {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post("/crontab/list?p=" + page + '&search=' + search + '&orderby=' + g_orderby + '&order=' + g_order, '', function (rdata) {
    layer.close(load);
    setSortUI();
    var cbody = "";
    if (rdata.data.length == 0) {
      cbody = lan && lan.crontab && t('crontab.crontab_auto_str_9') || "";
    } else {
      for (var i = 0; i < rdata.data.length; i++) {
        //状态
        var status = rdata.data[i]['status'] == '1' ? '<span class="btOpen" onclick="setTaskStatus(' + rdata.data[i].id + (lan && lan.crontab && t('crontab.crontab_auto_str_10') || "") : '<span onclick="setTaskStatus(' + rdata.data[i].id + (lan && lan.crontab && t('crontab.crontab_auto_str_11') || "");
        var cron_save = '--';
        if (rdata.data[i]['save'] != '') {
          cron_save = rdata.data[i]['save'] + (lan && lan.crontab && t('crontab.crontab_auto_str_12') || "");
        }
        var cron_backupto = '-';
        if (rdata.data[i]['stype'] == 'site' || rdata.data[i]['stype'] == 'path' || rdata.data[i]['stype'] == 'database' || rdata.data[i]['stype'].indexOf('database_') > -1) {
          cron_backupto = lan && lan.crontab && t('crontab.crontab_auto_str_13') || "";
          if (rdata.data[i]['backup_to'] != 'localhost') {
            cron_backupto = getBackupName(rdata['backup_hook'], rdata.data[i]['backup_to']);
          }
        }
        cbody += "<tr><td><input type='checkbox' onclick='checkSelect();' title='" + rdata.data[i].name + "' name='id' value='" + rdata.data[i].id + "'></td>\
					<td>" + rdata.data[i].name + "</td>\
					<td>" + status + "</td>\
					<td>" + rdata.data[i].type + "</td>\
					<td>" + rdata.data[i].cycle + "</td>\
					<td>" + cron_save + "</td>\
					<td>" + cron_backupto + "</td>\
					<td>" + (rdata.data[i].day_type_h == (lan && lan.crontab && t('crontab.crontab_auto_str_14') || "") ? '' : rdata.data[i].day_type_h) + "</td>\
					<td>" + rdata.data[i].last_run_time + "</td>\
					<td>\
						<a href=\"javascript:startTask(" + rdata.data[i].id + ", '" + rdata.data[i].name.replace('\\', '\\\\').replace("'", "\\'").replace('"', '') + (lan && lan.crontab && t('crontab.crontab_auto_str_15') || "") + rdata.data[i].id + (lan && lan.crontab && t('crontab.crontab_auto_str_16') || "") + rdata.data[i].id + ", '" + rdata.data[i].name.replace('\\', '\\\\').replace("'", "\\'").replace('"', '') + (lan && lan.crontab && t('crontab.crontab_auto_str_17') || "") + rdata.data[i].id + " ,'" + rdata.data[i].name.replace('\\', '\\\\').replace("'", "\\'").replace('"', '') + (lan && lan.crontab && t('crontab.crontab_auto_str_18') || "");
      }
    }
    $('#cronbody').html(cbody);
    $('#softPage').html(rdata.page);
  }, 'json');
}

// 设置计划任务状态
function setTaskStatus(id, status) {
  var confirm = layer.confirm(status == '0' ? lan && lan.crontab && t('crontab.crontab_auto_str_19') || "" : lan && lan.crontab && t('crontab.crontab_auto_str_20') || "", {
    title: lan && lan.crontab && t('crontab.crontab_auto_str_21') || "",
    icon: 3,
    closeBtn: 1
  }, function (index) {
    if (index > 0) {
      var loadT = layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_22') || "", {
        icon: 16,
        time: 0,
        shade: [0.3, '#000']
      });
      $.post('/crontab/set_cron_status', {
        id: id
      }, function (rdata) {
        if (!rdata.status) {
          layer.msg(rdata.msg, {
            icon: rdata.status ? 1 : 2
          });
          return;
        }
        showMsg(rdata.msg, function () {
          layer.close(loadT);
          layer.close(confirm);
          getCronData(1);
        }, {
          icon: rdata.status ? 1 : 2
        }, 2000);
      }, 'json');
    }
  });
}

//执行任务脚本
function startTask(id, task_name, is_log_open) {
  if (typeof task_name == 'boolean') {
    is_log_open = task_name;
    task_name = '';
  }
  var loadT = layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_23') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  var data = 'id=' + id;
  $.post('/crontab/start_task', data, function (rdata) {
    layer.close(loadT);
    if (rdata.status) {
      if (!is_log_open) {
        getLogs(id, task_name);
      } else {
        $.post('/crontab/logs', 'id=' + id, function (rdata) {
          if (!rdata.status) return;
          $("#crontab_log").html(rdata.msg);
          var ob = document.getElementById('crontab_log');
          if (ob) ob.scrollTop = ob.scrollHeight;
        }, 'json');
      }
    } else {
      showMsg(rdata.msg, function () {}, {
        icon: rdata.status ? 1 : 2,
        time: 2000
      });
    }
  }, 'json');
}

//清空日志
function closeLogs(id, is_refresh) {
  var loadT = layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_24') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  var data = 'id=' + id;
  $.post('/crontab/del_logs', data, function (rdata) {
    layer.close(loadT);
    if (rdata.status && is_refresh) {
      $("#crontab_log").html(lan && lan.crontab && t('crontab.crontab_auto_str_25') || "");
    }
    showMsg(rdata.msg, function () {
      // layer.closeAll();
    }, {
      icon: rdata.status ? 1 : 2,
      time: 2000
    });
  }, 'json');
}

//删除
function planDel(id, name) {
  safeMessage(t('del', [name]), lan && lan.crontab && t('crontab.crontab_auto_str_26') || "", function () {
    var load = layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_27') || "", {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    var data = 'id=' + id;
    $.post('/crontab/del', data, function (rdata) {
      showMsg(rdata.msg, function () {
        layer.closeAll();
        getCronData(1);
      }, {
        icon: rdata.status ? 1 : 2,
        time: 2000
      });
    }, 'json');
  });
}
function isURL(str_url) {
  var strRegex = '^(https|http|ftp|rtsp|mms)?://.+';
  var re = new RegExp(strRegex);
  if (re.test(str_url)) {
    return true;
  } else {
    return false;
  }
}

//提交
function planAdd() {
  var name = $(".planname input[name='name']").val();
  if (name == '') {
    $(".planname input[name='name']").trigger('focus');
    layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_28') || "", {
      icon: 2
    });
    return;
  }
  $("#cronConfig input[name='name']").val(name);
  var time_type = $(".plancycle").find("b").attr("val");
  $("#cronConfig input[name='type']").val(time_type);
  var is1;
  var is2 = 1;
  switch (time_type) {
    case 'day-n':
      is1 = 31;
      break;
    case 'minute-n':
      is1 = 59;
      break;
    case 'month':
      is1 = 31;
      break;
  }
  var where1 = $('#excode_week b').attr('val');
  $("#cronConfig input[name='where1']").val(where1);
  if (where1 > is1 || where1 < is2) {
    $("#ptime input[name='where1']").trigger('focus');
    layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_29') || "", {
      icon: 2
    });
    return;
  }
  var hour = $("#ptime input[name='hour']").val();
  if (hour > 23 || hour < 0) {
    $("#ptime input[name='hour']").trigger('focus');
    layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_30') || "", {
      icon: 2
    });
    return;
  }
  $("#cronConfig input[name='hour']").val(hour);
  var minute = $("#ptime input[name='minute']").val();
  if (minute > 59 || minute < 0) {
    $("#ptime input[name='minute']").trigger('focus');
    layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_31') || "", {
      icon: 2
    });
    return;
  }
  $("#cronConfig input[name='minute']").val(minute);
  var save = $("#save").val();
  if (save < 0) {
    layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_32') || "", {
      icon: 2
    });
    return;
  }
  $("#cronConfig input[name='save']").val(save);
  $("#cronConfig input[name='week']").val($(".planweek").find("b").attr("val"));
  var cron_type = $(".planjs").find("b").attr("val");
  var sBody = encodeURIComponent($("#implement textarea[name='sbody']").val());
  if (cron_type == 'toShell') {
    if (sBody == '') {
      $("#implement textarea[name='sbody']").trigger('focus');
      layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_33') || "", {
        icon: 2
      });
      return;
    }
  }
  if (cron_type == 'toFile') {
    if ($("#viewfile").val() == '') {
      layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_34') || "", {
        icon: 2
      });
      return;
    }
  }
  var url_address = $("#url_address").val();
  if (cron_type == 'toUrl') {
    if (!isURL(url_address)) {
      layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_35') || "", {
        icon: 2
      });
      $("implement textarea[name='url_address']").trigger('focus');
      return;
    }
  }
  // url_address = encodeURIComponent(url_address);
  $("#cronConfig input[name='url_address']").val(url_address);
  $("#cronConfig input[name='stype']").val(cron_type);
  $("#cronConfig textarea[name='sbody']").val(decodeURIComponent(sBody));
  if (cron_type == 'site' || cron_type == 'database' || cron_type.indexOf('database_') > -1 || cron_type == 'path') {
    var backupTo = $(".planBackupTo").find("b").attr("val");
    $("#backup_to").val(backupTo);
  }
  var day_type = $("input[name='day_type_radio']:checked").val();
  $("#cronConfig input[name='day_type']").val(day_type);
  if (cron_type == 'site' || cron_type == 'path') {
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

  if (time_type == 'minute-n') {
    var where1 = $("#ptime input[name='where1']").val();
    $("#cronConfig input[name='where1']").val(where1);
    var min_start_en = $("#ptime input[name='min_start_en']").prop("checked") ? 1 : 0;
    $("#cronConfig input[name='min_start_en']").val(min_start_en);
    $("#cronConfig input[name='min_start_h']").val($("#ptime input[name='min_start_h']").val() || 0);
    $("#cronConfig input[name='min_start_m']").val($("#ptime input[name='min_start_m']").val() || 0);
    var min_end_en = $("#ptime input[name='min_end_en']").prop("checked") ? 1 : 0;
    $("#cronConfig input[name='min_end_en']").val(min_end_en);
    $("#cronConfig input[name='min_end_h']").val($("#ptime input[name='min_end_h']").val() || 23);
    $("#cronConfig input[name='min_end_m']").val($("#ptime input[name='min_end_m']").val() || 59);
  }
  if (time_type == 'day-n') {
    var where1 = $("#ptime input[name='where1']").val();
    $("#cronConfig input[name='where1']").val(where1);
  }
  if (time_type == 'hour-n') {
    var where1 = $("#ptime input[name='where1']").val();
    $("#cronConfig input[name='where1']").val(where1);
  }
  if (time_type == 'month') {
    var where1 = $("#ptime input[name='where1']").val();
    $("#cronConfig input[name='where1']").val(where1);
  }
  if (time_type == 'week') {
    var where1 = $("#ptime input[name='where1']").val();
    $("#cronConfig input[name='where1']").val(where1);
  }
  layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_36') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  var data = $("#cronConfig").serialize() + '&sbody=' + sBody;
  // console.log(data);
  $.post('/crontab/add', data, function (rdata) {
    if (!rdata.status) {
      layer.msg(rdata.msg, {
        icon: 2,
        time: 2000
      });
      return;
    }
    showMsg(rdata.msg, function () {
      layer.closeAll();
      getCronData(1);
    }, {
      icon: rdata.status ? 1 : 2
    }, 2000);
  }, 'json');
}
initDropdownMenu();
function initDropdownMenu() {
  $(".dropdown ul li a").on('click', function () {
    $('#tag_exclude_dir').hide();
    var txt = $(this).text();
    var type = $(this).attr("value");
    $(this).parents(".dropdown").find("button b").text(txt).attr("val", type);
    switch (type) {
      case 'day':
        closeOpt();
        toHour();
        toMinute();
        break;
      case 'day-n':
        closeOpt();
        toWhere1(lan && lan.crontab && t('crontab.crontab_auto_str_37') || "");
        toHour();
        toMinute();
        break;
      case 'minute-n':
        closeOpt();
        toMinuteN();
        break;
      case 'week':
        closeOpt();
        toWeek();
        toHour();
        toMinute();
        break;
      case 'month':
        closeOpt();
        toWhere1(lan && lan.crontab && t('crontab.crontab_auto_str_38') || "");
        toHour();
        toMinute();
        break;
      case 'toFile':
        toFile();
        break;
      case 'toShell':
        toShell();
        $(".controls").html(lan && lan.crontab && t('crontab.crontab_auto_str_39') || "");
        break;
      case 'rememory':
        rememory();
        $(".controls").html(lan && lan.crontab && t('crontab.crontab_auto_str_40') || "");
        break;
      case 'site':
        toBackup('sites');
        $('#tag_exclude_dir').show();
        $(".controls").html(lan && lan.crontab && t('crontab.crontab_auto_str_41') || "");
        break;
      case 'path':
        $('#tag_exclude_dir').show();
        toBackup('path');
        $(".controls").html(lan && lan.crontab && t('crontab.crontab_auto_str_42') || "");
        break;
      case 'database_mariadb':
      case 'database_mongodb':
      case 'database_postgresql':
      case 'database_mysql-apt':
      case 'database_mysql-yum':
      case 'database':
        toBackup(type);
        $(".controls").html(lan && lan.crontab && t('crontab.crontab_auto_str_43') || "");
        break;
      case 'logs':
        toLogsHtml('logs');
        $(".controls").html(lan && lan.crontab && t('crontab.crontab_auto_str_44') || "");
        break;
      case 'toUrl':
        toUrl();
        $(".controls").html(lan && lan.crontab && t('crontab.crontab_auto_str_45') || "");
        break;
    }
  });
}

//备份
function toLogsHtml(type) {
  var sMsg = "";
  switch (type) {
    case 'sites':
      sMsg = lan && lan.crontab && t('crontab.crontab_auto_str_46') || "";
      sType = "sites";
      break;
    case 'database_mariadb':
    case 'database_mongodb':
    case 'database_postgresql':
    case 'database_mysql-apt':
    case 'database_mysql-yum':
    case 'database':
      sMsg = lan && lan.crontab && t('crontab.crontab_auto_str_47') || "";
      suffix = type.replace('database', '');
      if (suffix != '') {
        suffix = suffix.replace('_', '');
        sMsg = (lan && lan.crontab && t('crontab.crontab_auto_str_48') || "") + suffix + ']';
      }
      sType = type;
      break;
    case 'logs':
      sMsg = lan && lan.crontab && t('crontab.crontab_auto_str_49') || "";
      sType = "logs";
      break;
    case 'path':
      sMsg = lan && lan.crontab && t('crontab.crontab_auto_str_50') || "";
      sType = "path";
      break;
  }
  var data = 'type=' + sType;
  $.post('/crontab/get_data_list', data, function (rdata) {
    $(".planname input[name='name']").attr('readonly', 'true').css({
      "background-color": "#f6f6f6",
      "color": "#666"
    });
    var sOpt = "";
    if (rdata.data.length == 0) {
      layer.msg(t('public.list_empty'), {
        icon: 2
      });
      return;
    }
    for (var i = 0; i < rdata.data.length; i++) {
      if (i == 0) {
        $(".planname input[name='name']").val(sMsg + '[' + rdata.data[i].name + ']');
      }
      sOpt += '<li><a role="menuitem" tabindex="-1" href="javascript:;" value="' + rdata.data[i].name + '">' + rdata.data[i].name + '[' + rdata.data[i].ps + ']</a></li>';
    }
    if (sType != 'path') {
      sOpt = (lan && lan.crontab && t('crontab.crontab_auto_str_51') || "") + sOpt;
    }
    var orderOpt = '';
    for (var i = 0; i < rdata.orderOpt.length; i++) {
      orderOpt += '<li><a role="menuitem" tabindex="-1" href="javascript:;" value="' + rdata.orderOpt[i].name + '">' + rdata.orderOpt[i].title + '</a></li>';
    }
    var changeDir = '';
    if (sType == 'path') {
      changeDir = '<span class="glyphicon glyphicon-folder-open cursor mr20 changePathDir" style="float:left;line-height: 30px;"></span>';
    }
    var sBody = '<div class="dropdown pull-left mr20 check">\
					  <button class="btn btn-default dropdown-toggle sname" type="button" id="backdata" data-toggle="dropdown" style="width:auto">\
						<b id="sname" val="' + rdata.data[0].name + '">' + rdata.data[0].name + '[' + rdata.data[0].ps + ']</b> <span class="caret"></span>\
					  </button>\
					  <ul class="dropdown-menu" role="menu" aria-labelledby="backdata">' + sOpt + '</ul>\
					</div>\
					' + changeDir + (lan && lan.crontab && t('crontab.crontab_auto_str_52') || "");
    $("#implement").html(sBody);
    getselectname();
    $('.changePathDir').on('click', function () {
      changePathCallback($('#sname').val(), function (select_dir) {
        $(".planname input[name='name']").val((lan && lan.crontab && t('crontab.crontab_auto_str_53') || "") + select_dir + ']');
        $('#implement .sname b').attr('val', select_dir).text(select_dir);
      });
    });
    $(".dropdown ul li a").on('click', function () {
      var sname = $("#sname").attr("val");
      if (!sname) return;
      $(".planname input[name='name']").val(sMsg + '[' + sname + ']');
    });
  }, 'json');
}

//备份
function toBackup(type) {
  var sMsg = "";
  switch (type) {
    case 'sites':
      sMsg = lan && lan.crontab && t('crontab.crontab_auto_str_54') || "";
      sType = "sites";
      break;
    case 'database_mariadb':
    case 'database_mongodb':
    case 'database_postgresql':
    case 'database_mysql-apt':
    case 'database_mysql-yum':
    case 'database':
      sMsg = lan && lan.crontab && t('crontab.crontab_auto_str_55') || "";
      suffix = type.replace('database', '');
      if (suffix != '') {
        suffix = suffix.replace('_', '');
        sMsg = (lan && lan.crontab && t('crontab.crontab_auto_str_56') || "") + suffix + ']';
      }
      sType = type;
      break;
    case 'logs':
      sMsg = lan && lan.crontab && t('crontab.crontab_auto_str_57') || "";
      sType = "logs";
      break;
    case 'path':
      sMsg = lan && lan.crontab && t('crontab.crontab_auto_str_58') || "";
      sType = "path";
      break;
  }
  var data = 'type=' + sType;
  $.post('/crontab/get_data_list', data, function (rdata) {
    $(".planname input[name='name']").css({
      "background-color": "#f6f6f6",
      "color": "#666"
    });
    var sOpt = "";
    if (rdata.data.length == 0) {
      layer.msg(t('public.list_empty'), {
        icon: 2
      });
      return;
    }
    for (var i = 0; i < rdata.data.length; i++) {
      if (i == 0) {
        $(".planname input[name='name']").val(sMsg + '[' + rdata.data[i].name + ']');
      }
      sOpt += '<li><a role="menuitem" tabindex="-1" href="javascript:;" value="' + rdata.data[i].name + '">' + rdata.data[i].name + '[' + rdata.data[i].ps + ']</a></li>';
    }
    if (sType != 'path') {
      sOpt = (lan && lan.crontab && t('crontab.crontab_auto_str_59') || "") + sOpt;
    }
    var orderOpt = '';
    for (var i = 0; i < rdata.orderOpt.length; i++) {
      orderOpt += '<li><a role="menuitem" tabindex="-1" href="javascript:;" value="' + rdata.orderOpt[i].name + '">' + rdata.orderOpt[i].title + '</a></li>';
    }
    var changeDir = '';
    if (sType == 'path') {
      changeDir = '<span class="glyphicon glyphicon-folder-open cursor mr20 changePathDir" style="float:left;line-height: 30px;"></span>';
    }
    var sBody = '<div class="dropdown pull-left mr20 check">\
		 	<button class="btn btn-default dropdown-toggle sname" type="button" id="backdata" data-toggle="dropdown" style="width:auto">\
				<b id="sname" val="' + rdata.data[0].name + '">' + rdata.data[0].name + '[' + rdata.data[0].ps + ']</b> <span class="caret"></span>\
		  	</button>\
		 	<ul class="dropdown-menu" role="menu" aria-labelledby="backdata">' + sOpt + '</ul>\
		</div>\
		' + changeDir + (lan && lan.crontab && t('crontab.crontab_auto_str_60') || "") + orderOpt + (lan && lan.crontab && t('crontab.crontab_auto_str_61') || "");
    $("#implement").html(sBody);
    getselectname();
    $('.changePathDir').on('click', function () {
      changePathCallback($('#sname').val(), function (select_dir) {
        $(".planname input[name='name']").val((lan && lan.crontab && t('crontab.crontab_auto_str_62') || "") + select_dir + ']');
        $('#implement .sname b').attr('val', select_dir).text(select_dir);
      });
    });
    $(".dropdown ul li a").on('click', function () {
      var sname = $("#sname").attr("val");
      if (!sname) return;
      $(".planname input[name='name']").val(sMsg + '[' + sname + ']');
    });
  }, 'json');
}

// 编辑计划任务
function editTaskInfo(id) {
  layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_63') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/crontab/get_crond_find', {
    id: id
  }, function (rdata) {
    layer.closeAll();
    // console.log('get_crond_find:', rdata);
    var sTypeName = '',
      sTypeDom = '',
      cycleName = '',
      cycleDom = '',
      weekName = '',
      weekDom = '',
      sNameName = '',
      sNameDom = '',
      backupsName = '',
      backupsDom = '';
    obj = {
      from: {
        id: rdata.id,
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
        attr: rdata.attr,
        day_type: rdata.day_type,
        min_start_en: rdata.min_start_en || 0,
        min_start_h: rdata.min_start_h || 0,
        min_start_m: rdata.min_start_m || 0,
        min_end_en: rdata.min_end_en || 0,
        min_end_h: rdata.min_end_h || 23,
        min_end_m: rdata.min_end_m || 59
      },
      sTypeArray: [['toShell', lan && lan.crontab && t('crontab.crontab_auto_str_64') || ""], ['site', lan && lan.crontab && t('crontab.crontab_auto_str_65') || ""], ['database', lan && lan.crontab && t('crontab.crontab_auto_str_66') || ""], ['logs', lan && lan.crontab && t('crontab.crontab_auto_str_67') || ""], ['path', lan && lan.crontab && t('crontab.crontab_auto_str_68') || ""], ['rememory', lan && lan.crontab && t('crontab.crontab_auto_str_69') || ""], ['toUrl', lan && lan.crontab && t('crontab.crontab_auto_str_70') || ""]],
      cycleArray: [['day', lan && lan.crontab && t('crontab.crontab_auto_str_71') || ""], ['day-n', lan && lan.crontab && t('crontab.crontab_auto_str_72') || ""], ['minute-n', lan && lan.crontab && t('crontab.crontab_auto_str_73') || ""], ['week', lan && lan.crontab && t('crontab.crontab_auto_str_74') || ""], ['month', lan && lan.crontab && t('crontab.crontab_auto_str_75') || ""]],
      weekArray: [[1, lan && lan.crontab && t('crontab.crontab_auto_str_76') || ""], [2, lan && lan.crontab && t('crontab.crontab_auto_str_77') || ""], [3, lan && lan.crontab && t('crontab.crontab_auto_str_78') || ""], [4, lan && lan.crontab && t('crontab.crontab_auto_str_79') || ""], [5, lan && lan.crontab && t('crontab.crontab_auto_str_80') || ""], [6, lan && lan.crontab && t('crontab.crontab_auto_str_81') || ""], [7, lan && lan.crontab && t('crontab.crontab_auto_str_82') || ""]],
      sNameArray: [],
      backupsArray: [],
      create: function (callback) {
        if (obj.from['stype'].indexOf('database_') > -1) {
          name = obj.from['stype'].replace('database_', '');
          sTypeName = (lan && lan.crontab && t('crontab.crontab_auto_str_83') || "") + name + ']';
          sTypeDom += '<li><a role="menuitem"  href="javascript:;" value="' + obj.from['stype'] + '">' + sTypeName + '</a></li>';
        } else {
          for (var i = 0; i < obj['sTypeArray'].length; i++) {
            if (obj.from['stype'] == obj['sTypeArray'][i][0]) {
              sTypeName = obj['sTypeArray'][i][1];
            }
            sTypeDom += '<li><a role="menuitem"  href="javascript:;" value="' + obj['sTypeArray'][i][0] + '">' + obj['sTypeArray'][i][1] + '</a></li>';
          }
        }
        for (var i = 0; i < obj['cycleArray'].length; i++) {
          if (obj.from['type'] == obj['cycleArray'][i][0]) cycleName = obj['cycleArray'][i][1];
          cycleDom += '<li><a role="menuitem"  href="javascript:;" value="' + obj['cycleArray'][i][0] + '">' + obj['cycleArray'][i][1] + '</a></li>';
        }
        for (var i = 0; i < obj['weekArray'].length; i++) {
          if (obj.from['week'] == obj['weekArray'][i][0]) weekName = obj['weekArray'][i][1];
          weekDom += '<li><a role="menuitem"  href="javascript:;" value="' + obj['weekArray'][i][0] + '">' + obj['weekArray'][i][1] + '</a></li>';
        }
        if (obj.from.stype == 'site' || obj.from.stype == 'database' || obj.from.stype == 'path' || obj.from.stype == 'logs' || obj.from['stype'].indexOf('database_') > -1) {
          $.post('/crontab/get_data_list', {
            type: obj.from.stype
          }, function (rdata) {
            // console.log(rdata);
            obj.sNameArray = rdata.data;
            obj.sNameArray.unshift({
              name: 'ALL',
              ps: lan && lan.crontab && t('crontab.crontab_auto_str_84') || ""
            });
            obj.backupsArray = rdata.orderOpt;
            obj.backupsArray.unshift({
              title: lan && lan.crontab && t('crontab.crontab_auto_str_85') || "",
              name: 'localhost'
            });
            for (var i = 0; i < obj['sNameArray'].length; i++) {
              if (obj.from['sname'] == obj['sNameArray'][i]['name']) {
                sNameName = obj['sNameArray'][i]['ps'];
              }
              sNameDom += '<li><a role="menuitem"  href="javascript:;" value="' + obj['sNameArray'][i]['name'] + '">' + obj['sNameArray'][i]['ps'] + '</a></li>';
            }
            for (var i = 0; i < obj['backupsArray'].length; i++) {
              if (obj.from['backup_to'] == obj['backupsArray'][i]['name']) {
                backupsName = obj['backupsArray'][i]['title'];
              }
              backupsDom += '<li><a role="menuitem"  href="javascript:;" value="' + obj['backupsArray'][i]['name'] + '">' + obj['backupsArray'][i]['title'] + '</a></li>';
            }
            callback();
          }, 'json');
        } else {
          callback();
        }
      }
    };
    obj.create(function () {
      var changeDir = '';
      if (obj.from.stype == 'path') {
        changeDir = '<span class="glyphicon glyphicon-folder-open cursor mr20 changePathDir" style="float:left;line-height: 30px;"></span>';
      }
      var exclude_dirs_placeholder = lan && lan.crontab && t('crontab.crontab_auto_str_86') || "";
      layer.open({
        type: 1,
        title: (lan && lan.crontab && t('crontab.crontab_auto_str_87') || "") + rdata.name + ']',
        area: ['900px', '640px'],
        skin: 'layer-create-content',
        shadeClose: false,
        closeBtn: 1,
        content: (lan && lan.crontab && t('crontab.crontab_auto_str_88') || "") + obj.from.type + '">' + sTypeName + '</b>\
								<span class="caret"></span>\
							</button>\
							<ul class="dropdown-menu" role="menu" aria-labelledby="sType">' + sTypeDom + (lan && lan.crontab && t('crontab.crontab_auto_str_89') || "") + obj.from.name + (lan && lan.crontab && t('crontab.crontab_auto_str_90') || "") + obj.from.stype + '">' + cycleName + '</b>\
								<span class="caret"></span>\
							</button>\
							<ul class="dropdown-menu" role="menu" aria-labelledby="cycle">' + cycleDom + '</ul>\
						</div>\
						<div class="pull-left optional_week">\
							<div class="dropdown week_btn pull-left mr20" style="display:' + (obj.from.type == "week" ? 'block;' : 'none') + '">\
								<button class="btn btn-default dropdown-toggle" type="button" data-toggle="dropdown" >\
									<b val="' + obj.from.week + '">' + weekName + '</b> \
									<span class="caret"></span>\
								</button>\
								<ul class="dropdown-menu" role="menu" aria-labelledby="week">' + weekDom + '</ul>\
							</div>\
							<div class="plan_hms pull-left mr20 bt-input-text where1_input" style="display:' + (obj.from.type == "day-n" || obj.from.type == 'month' ? 'block;' : 'none') + '"><span><input type="number" name="where1" class="where1_create" value="' + obj.from.where1 + (lan && lan.crontab && t('crontab.crontab_auto_str_91') || "") + (obj.from.type == "day" || obj.from.type == 'day-n' || obj.from.type == 'hour-n' || obj.from.type == 'week' || obj.from.type == 'month' ? 'block;' : 'none') + '"><span><input type="number" name="hour" class="hour_create" value="' + (obj.from.type == 'hour-n' ? obj.from.where1 : obj.from.hour) + (lan && lan.crontab && t('crontab.crontab_auto_str_92') || "") + (obj.from.type == 'minute-n' ? obj.from.where1 : obj.from.minute) + (lan && lan.crontab && t('crontab.crontab_auto_str_93') || "") + (obj.from.type == "minute-n" ? 'block;' : 'none') + (lan && lan.crontab && t('crontab.crontab_auto_str_94') || "") + (obj.from.min_start_en == 1 ? 'checked' : '') + (lan && lan.crontab && t('crontab.crontab_auto_str_95') || "") + obj.from.min_start_h + '" maxlength="2" max="23" min="0" class="bt-input-text" style="width:50px; margin-right: 5px;">:\
							<input type="number" name="min_start_m_create" value="' + obj.from.min_start_m + '" maxlength="2" max="59" min="0" class="bt-input-text" style="width:50px; margin-right: 15px;">\
							<label style="font-weight:normal;cursor:pointer;margin-right:10px;"><input type="checkbox" name="min_end_en_create" value="1" ' + (obj.from.min_end_en == 1 ? 'checked' : '') + (lan && lan.crontab && t('crontab.crontab_auto_str_96') || "") + obj.from.min_end_h + '" maxlength="2" max="23" min="0" class="bt-input-text" style="width:50px; margin-right: 5px;">:\
							<input type="number" name="min_end_m_create" value="' + obj.from.min_end_m + (lan && lan.crontab && t('crontab.crontab_auto_str_97') || "") + (obj.from.day_type == 0 ? 'checked' : '') + (lan && lan.crontab && t('crontab.crontab_auto_str_98') || "") + (obj.from.day_type == 1 ? 'checked' : '') + (lan && lan.crontab && t('crontab.crontab_auto_str_99') || "") + (obj.from.day_type == 2 ? 'checked' : '') + (lan && lan.crontab && t('crontab.crontab_auto_str_100') || "") + (obj.from.day_type == 3 ? 'checked' : '') + (lan && lan.crontab && t('crontab.crontab_auto_str_101') || "") + sTypeName + '</span>\
						<div style="line-height:34px"><div class="dropdown pull-left mr20 sName_btn" style="display:' + (obj.from.sType != "path" ? 'block;' : 'none') + '">\
							<button class="btn btn-default dropdown-toggle sname" type="button"  data-toggle="dropdown" style="width:auto" disabled="disabled">\
								<b id="sName" val="' + obj.from.sname + '">' + obj.from.sname + '</b>\
								<span class="caret"></span>\
							</button>\
							<ul class="dropdown-menu" role="menu" aria-labelledby="sName">' + sNameDom + '</ul>\
						</div>\
						<div class="info-r" style="float: left;margin-right: 25px;display:' + (obj.from.sType == "path" ? 'block;' : 'none') + '">\
							<input id="inputPath" class="bt-input-text mr5 " type="text" name="path" value="' + obj.from.sName + (lan && lan.crontab && t('crontab.crontab_auto_str_102') || "") + changeDir + (lan && lan.crontab && t('crontab.crontab_auto_str_103') || "") + obj.from.backup_to + '">' + backupsName + '</b>\
									<span class="caret"></span>\
								</button>\
								<ul class="dropdown-menu" role="menu" aria-labelledby="backupTo">' + backupsDom + (lan && lan.crontab && t('crontab.crontab_auto_str_104') || "") + obj.from.save + (lan && lan.crontab && t('crontab.crontab_auto_str_105') || "") + (obj.from.stype == "toShell" ? 'block;' : 'none') + (lan && lan.crontab && t('crontab.crontab_auto_str_106') || "") + obj.from.sbody + '</textarea></div>\
					</div>\
					<div class="clearfix plan ptb10"  style="display:' + (obj.from.stype == "path" || obj.from.stype == "site" ? 'block;' : 'none') + (lan && lan.crontab && t('crontab.crontab_auto_str_107') || "") + exclude_dirs_placeholder + '">' + obj.from.attr + '</textarea></div>\
					</div>\
					<div class="clearfix plan ptb10" style="display:' + (obj.from.stype == "rememory" ? 'block;' : 'none') + (lan && lan.crontab && t('crontab.crontab_auto_str_108') || "") + (obj.from.stype == "toUrl" ? 'block;' : 'none') + (lan && lan.crontab && t('crontab.crontab_auto_str_109') || "") + obj.from.url_address + (lan && lan.crontab && t('crontab.crontab_auto_str_110') || ""),
        success: function () {
          $('.changePathDir').on('click', function () {
            changePathCallback($('#sName').val(), function (select_dir) {
              $('input[name="name"]').val((lan && lan.crontab && t('crontab.crontab_auto_str_111') || "") + select_dir + ']');
              $('.sName_btn .sname b').attr('val', select_dir).text(select_dir);
              obj.from.sname = select_dir;
            });
          });
          if (obj.from.stype == 'toShell') {
            $('.site_list').hide();
          } else if (obj.from.stype == 'rememory') {
            $('.site_list').hide();
          } else if (obj.from.stype == 'toUrl') {
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
          $("input[name='day_type_radio_edit']").on('change', function () {
            obj.from.day_type = $(this).val();
          });
          $('[aria-labelledby="cycle"] a').off().on('click', function () {
            $('.cycle_btn').find('b').attr('val', $(this).attr('value')).html($(this).html());
            var type = $(this).attr('value');
            switch (type) {
              case 'day':
                $('.week_btn').hide();
                $('.where1_input').hide();
                $('.hour_input').show().find('input').val('1');
                $('.minute_input').show().find('input').val('30');
                $('.minute_n_time_range_create').hide();
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
                $('.minute_n_time_range_create').hide();
                obj.from.week = '';
                obj.from.where1 = 1;
                obj.from.hour = 1;
                obj.from.minute = 30;
              case 'minute-n':
                $('.week_btn').hide();
                $('.where1_input').hide();
                $('.hour_input').hide();
                $('.minute_input').show();
                $('.minute_n_time_range_create').show();
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
                $('.minute_n_time_range_create').hide();
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
                $('.minute_n_time_range_create').hide();
                obj.from.week = '';
                obj.from.where1 = 1;
                obj.from.hour = 1;
                obj.from.minute = 30;
                break;
            }
            obj.from.type = $(this).attr('value');
          });
          $('[aria-labelledby="week"] a').off().on('click', function () {
            $('.week_btn').find('b').attr('val', $(this).attr('value')).html($(this).html());
            obj.from.week = $(this).attr('value');
          });
          $('[aria-labelledby="backupTo"] a').off().on('click', function () {
            $('.backup_btn').find('b').attr('val', $(this).attr('value')).html($(this).html());
            obj.from.backup_to = $(this).attr('value');
          });
          $('.plan-submits').off().on('click', function () {
            if (obj.from.type == 'minute-n') {
              obj.from.where1 = obj.from.minute;
              obj.from.minute = '';
              obj.from.min_start_en = $("input[name='min_start_en_create']").prop('checked') ? 1 : 0;
              obj.from.min_start_h = $("input[name='min_start_h_create']").val() || 0;
              obj.from.min_start_m = $("input[name='min_start_m_create']").val() || 0;
              obj.from.min_end_en = $("input[name='min_end_en_create']").prop('checked') ? 1 : 0;
              obj.from.min_end_h = $("input[name='min_end_h_create']").val() || 23;
              obj.from.min_end_m = $("input[name='min_end_m_create']").val() || 59;
            } else if (obj.from.type == 'week') {
              obj.from.where1 = obj.from.week;
            }
            var loadT = layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_112') || "", {
              icon: 16,
              time: 0,
              shade: [0.3, '#000']
            });
            $.post('/crontab/modify_crond', obj.from, function (rdata) {
              if (!rdata.status) {
                layer.msg(rdata.msg, {
                  icon: rdata.status ? 1 : 2
                });
                return;
              }
              showMsg(rdata.msg, function () {
                layer.closeAll();
                getCronData(1);
                initDropdownMenu();
              }, {
                icon: rdata.status ? 1 : 2
              }, 2000);
            }, 'json');
          });
        },
        cancel: function () {
          initDropdownMenu();
        }
      });
    });
  }, 'json');
}

//下拉菜单名称
function getselectname() {
  $(".dropdown ul li a").on('click', function () {
    var txt = $(this).text();
    var type = $(this).attr("value");
    $(this).parents(".dropdown").find("button b").text(txt).attr("val", type);
  });
}
//清理
function closeOpt() {
  $("#ptime").html('');
}
//星期
function toWeek() {
  var mBody = lan && lan.crontab && t('crontab.crontab_auto_str_113') || "";
  $("#ptime").html(mBody);
  getselectname();
}
//指定1
function toWhere1(ix) {
  var mBody = '<div class="plan_hms pull-left mr20 bt-input-text">\
		<span><input type="number" name="where1" value="3" maxlength="2" max="31" min="0"></span>\
		<span class="name">' + ix + '</span>\
	</div>';
  $("#ptime").append(mBody);
}

//N分钟特别带上下限
function toMinuteN() {
  var mBody = lan && lan.crontab && t('crontab.crontab_auto_str_114') || "";
  $("#ptime").append(mBody);
}

//小时
function toHour() {
  var mBody = lan && lan.crontab && t('crontab.crontab_auto_str_115') || "";
  $("#ptime").append(mBody);
}

//分钟
function toMinute() {
  var mBody = lan && lan.crontab && t('crontab.crontab_auto_str_116') || "";
  $("#ptime").append(mBody);
}

//从文件
function toFile() {
  var tBody = lan && lan.crontab && t('crontab.crontab_auto_str_117') || "";
  $("#implement").html(tBody);
  $(".planname input[name='name']").removeAttr('readonly style').val("");
}

//从脚本
function toShell() {
  var tBody = "<textarea class='txtsjs bt-input-text' name='sbody'></textarea>";
  $("#implement").html(tBody);
  $(".planname input[name='name']").removeAttr('readonly style').val("");
}

//从脚本
function toUrl() {
  var tBody = "<input type='text' style='width:400px; height:34px' class='bt-input-text' name='url_address' id='url_address' placeholder='" + t('crontab.url_address') + "' value='http://' />";
  $("#implement").html(tBody);
  $(".planname input[name='name']").removeAttr('readonly style').val("");
}

//释放内存
function rememory() {
  $(".planname input[name='name']").removeAttr('readonly style').val("");
  $(".planname input[name='name']").val(lan && lan.crontab && t('crontab.crontab_auto_str_118') || "");
  $("#implement").html(lan && lan.crontab && t('crontab.crontab_auto_str_119') || "");
  return;
}
//上传
function fileupload() {
  $("#sFile").on('change', function () {
    $("#viewfile").val($("#sFile").val());
  });
  $("#sFile").click();
}

// 显示添加计划任务模态框
function showAddTask() {
  var index = layer.open({
    type: 1,
    title: lan && lan.crontab && t('crontab.crontab_auto_str_120') || "",
    area: ['900px', '650px'],
    skin: 'layer-create-content',
    shadeClose: false,
    closeBtn: 1,
    content: $('#add_task_form_box'),
    btn: [lan && lan.crontab && t('crontab.crontab_auto_str_121') || "", lan && lan.crontab && t('crontab.crontab_auto_str_122') || ""],
    success: function (layero, index) {
      $('#add_task_form_box').show();
      // 重置一下状态
      toShell();
      initDropdownMenu();
    },
    yes: function (index, layero) {
      planAdd();
    },
    cancel: function () {
      $('#add_task_form_box').hide().appendTo('body');
    },
    end: function () {
      $('#add_task_form_box').hide().appendTo('body');
    }
  });
}

// 切换排序
function getCronSort(name) {
  if (g_orderby == name) {
    g_order = g_order == 'asc' ? 'desc' : 'asc';
  } else {
    g_orderby = name;
    g_order = 'desc';
  }
  getCronData(1);
}

// 导出计划任务
function exportTasks() {
  var load = layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_123') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post("/crontab/list?p=1&limit=1000", '', function (rdata) {
    layer.close(load);
    if (!rdata.data || rdata.data.length == 0) {
      layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_124') || "", {
        icon: 2
      });
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
    var blob = new Blob([JSON.stringify(exportData, null, 4)], {
      type: "application/json"
    });
    var url = window.URL.createObjectURL(blob);
    var downloadAnchorNode = document.createElement('a');
    downloadAnchorNode.setAttribute("href", url);
    downloadAnchorNode.setAttribute("download", "crontab_export_" + new Date().getTime() + ".json");
    document.body.appendChild(downloadAnchorNode);
    downloadAnchorNode.click();
    downloadAnchorNode.remove();
    window.URL.revokeObjectURL(url);
    layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_125') || "", {
      icon: 1
    });
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
  reader.onload = function (e) {
    var contents = e.target.result;
    try {
      var tasks = JSON.parse(contents);
      if (!Array.isArray(tasks)) {
        layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_126') || "", {
          icon: 2
        });
        return;
      }
      layer.confirm((lan && lan.crontab && t('crontab.crontab_auto_str_127') || "") + tasks.length + (lan && lan.crontab && t('crontab.crontab_auto_str_128') || ""), {
        icon: 3,
        title: lan && lan.crontab && t('crontab.crontab_auto_str_129') || ""
      }, function (index) {
        layer.close(index);
        importTaskSequential(tasks, 0);
      });
    } catch (err) {
      layer.msg((lan && lan.crontab && t('crontab.crontab_auto_str_130') || "") + err, {
        icon: 2
      });
    }
    obj.value = ''; // 重置文件输入
  };
  reader.readAsText(file);
}

// 顺序导入任务以避免并发冲突
function importTaskSequential(tasks, index) {
  if (index >= tasks.length) {
    layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_131') || "", {
      icon: 1
    });
    getCronData(1);
    return;
  }
  var task = tasks[index];
  var load = layer.msg((lan && lan.crontab && t('crontab.crontab_auto_str_132') || "") + (index + 1) + '/' + tasks.length + '): ' + task.name, {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });

  // 如果没有 type_raw，尝试使用 type
  if (!task.type && task.type_raw) task.type = task.type_raw;
  $.post('/crontab/add', task, function (rdata) {
    layer.close(load);
    if (!rdata.status) {
      console.log((lan && lan.crontab && t('crontab.crontab_auto_str_133') || "") + task.name + ' - ' + rdata.msg);
    }
    importTaskSequential(tasks, index + 1);
  }, 'json').fail(function () {
    layer.close(load);
    importTaskSequential(tasks, index + 1);
  });
}

// 从服务器同步计划任务
function syncServerTasks() {
  layer.confirm(lan && lan.crontab && t('crontab.crontab_auto_str_134') || "", {
    icon: 3,
    title: lan && lan.crontab && t('crontab.crontab_auto_str_135') || ""
  }, function (index) {
    layer.close(index);
    var load = layer.msg(lan && lan.crontab && t('crontab.crontab_auto_str_136') || "", {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.post('/crontab/sync_sys_cron', function (rdata) {
      layer.close(load);
      if (rdata.status) {
        layer.msg(rdata.msg, {
          icon: 1,
          time: 2000
        });
        setTimeout(function () {
          getCronData(1);
        }, 2000);
      } else {
        layer.msg(rdata.msg, {
          icon: 2,
          time: 3000
        });
      }
    }, 'json');
  });
}

// 自动对时间输入框进行补零优化
$(document).on('blur', 'input[type="number"][name*="minute"], input[type="number"][name*="hour"], input[type="number"][name*="min_start"], input[type="number"][name*="min_end"]', function () {
  var val = $(this).val();
  if (val !== '' && !isNaN(val)) {
    var num = parseInt(val, 10);
    if (num >= 0 && num < 10) {
      $(this).val('0' + num);
    } else if (num >= 10) {
      $(this).val(num);
    }
  }
});