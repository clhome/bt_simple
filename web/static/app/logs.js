$(function () {
  logsLoad();
});
function changeLogsViewH() {
  var l = $(window).height();
  $('.container-fluid .tab-view-box').css('height', l - 80 - 40);
  $('#panelLogs').css('height', l - 80 - 40 - 50);
  $('#logAudit .logAuditTab').css('height', l - 80 - 40 - 50);
  $('#logAudit .logAuditContent').css('height', l - 80 - 40 - 50);
}
function logsLoad() {
  changeLogsViewH();
  $(window).on('resize', function () {
    changeLogsViewH();
  });
  getLogs(1);
}
$('#cutTab .tabs-item').on('click', function () {
  var type = $(this).data('name');
  $('#cutTab .tabs-item').removeClass('active');
  $(this).addClass('active');
  $('.tab-view-box .tab-con').addClass('hide').removeClass('show').removeClass('w-full');
  $('#' + type).addClass('show').addClass('w-full');
  switch (type) {
    case 'panelLogs':
      getLogs(1);
      break;
    case 'logAudit':
      getAuditLogsFiles();
      break;
  }
});
$('#panelLogs .refresh').on('click', function () {
  getLogs(1);
});
$('#panelLogs .clear').on('click', function () {
  delLogs(1);
});
function getAuditLogsFiles() {
  var loadT = layer.msg(lan && lan.logs && t('logs.logs_auto_str_1') || "", {
    icon: 16,
    time: 0,
    shade: 0.3
  });
  $.post('/logs/get_audit_logs_files', {}, function (rdata) {
    var data = rdata.data;
    layer.close(loadT);
    var option = '';
    for (var i = 0; i < data.length; i++) {
      var tip = data[i]['name'] + ' - ' + data[i]['title'] + '(' + toSize(data[i]['size']) + ')';
      if (i == 0) {
        option += '<div class="logAuditItem active" title="' + tip + '" data-file="' + data[i]['name'] + '">' + tip + '</div>';
      } else {
        option += '<div class="logAuditItem" title="' + tip + '" data-file="' + data[i]['name'] + '">' + tip + '</div>';
      }
    }
    $("#logAudit .logAuditTab").html(option);
    getAuditFile(data[0]['name']);
    $('#logAudit .logAuditItem').on('click', function () {
      $('#logAudit .logAuditItem').removeClass('active');
      $(this).addClass('active');
      getAuditFile($(this).data('file'));
    });
  }, 'json');
}
function getAuditFile(log_name) {
  var loadT = layer.msg(lan && lan.logs && t('logs.logs_auto_str_2') || "", {
    icon: 16,
    time: 0,
    shade: 0.3
  });
  $.post('/logs/get_audit_file', {
    log_name: log_name
  }, function (data) {
    layer.close(loadT);
    // console.log(data);
    try {
      if (typeof data == 'object') {
        var plist = data.data;
        var pre_html = lan && lan.logs && t('logs.logs_auto_str_3') || "";

        // var pre_html = '<table class="table table-hover" width="100%" cellspacing="0" cellpadding="0" border="0">\
        //         <thead><tr><th>时间</th><th>角色</th><th>事件</th></tr></thead>\
        //         <tbody></tbody>\
        //     </table>';
        $('#logAudit .logAuditContent').html(pre_html);
        if (plist.length > 0) {
          var tmp = plist[0];
          var thead = '';
          tbody += '<tr>';
          for (var i in tmp) {
            tbody += '<th>' + i + '</th>';
          }
          tbody += '</tr>';
          $('#logAudit .logAuditContent thead').html(tbody);
        }
        var tbody = '';
        for (var i = 0; i < plist.length; i++) {
          tbody += '<tr>';
          for (var vv in plist[i]) {
            tbody += '<td>' + plist[i][vv] + '</td>';
          }
          tbody += '</tr>';
        }
        $('#logAudit .logAuditContent tbody').html(tbody);
        $('#logAudit .refresh').on('click', function () {
          getAuditFile(log_name);
        });
      }
      if (typeof data == 'string') {
        var cc = '<div id="logAuditPre">\
            		<pre style="height: 100%; background-color: rgb(51, 51, 51); color: rgb(255, 255, 255); overflow-x: hidden; overflow-wrap: break-word; white-space: pre-wrap;"><code>' + data + '</code></pre>\
            	</div>';
        $('#logAudit .logAuditContent').html(cc);
      }
    } catch (e) {
      layer.msg(str(e), {
        icon: 2,
        time: 10000,
        shade: [0.3, '#000']
      });
    }
  });
}
function getLogs(page, search) {
  search = search == undefined ? '' : search;
  var loadT = layer.load();
  $.post('/logs/get_log_list', 'limit=10&p=' + page + "&search=" + search, function (data) {
    layer.close(loadT);
    var body = '';
    for (var i = 0; i < data.data.length; i++) {
      body += "<tr>\
						<td><em class='dlt-num'>" + data.data[i].id + "</em></td>\
						<td>" + data.data[i].type + "</td>\
						<td>" + data.data[i].log + "</td>\
						<td>" + data.data[i].add_time + "</td>\
					</tr>";
    }
    $("#operationLog tbody").html(body);
    $("#panelLogs .page").html(data.page);
  }, 'json');
}
function delLogs() {
  layer.confirm(lan && lan.logs && t('logs.logs_auto_str_4') || "", {
    title: lan && lan.logs && t('logs.logs_auto_str_5') || "",
    closeBtn: 2
  }, function () {
    var loadT = layer.msg(lan && lan.logs && t('logs.logs_auto_str_6') || "", {
      icon: 16
    });
    $.post('/logs/del_panel_logs', '', function (rdata) {
      layer.close(loadT);
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
      getLogs(1);
    }, 'json');
  });
}