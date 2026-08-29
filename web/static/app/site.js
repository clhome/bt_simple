$("#site_search_input").on('keyup', function (event) {
  if (event.keyCode == 13) {
    getWeb(1, -1, $(this).val());
  }
});
$('#site_search').on('click', function () {
  getWeb(1, -1, $('#site_search_input').val());
});

//设置到期日期
function getDate(a) {
  var dd = new Date();
  dd.setTime(dd.getTime() + (a == undefined || isNaN(parseInt(a)) ? 0 : parseInt(a)) * 86400000);
  var y = dd.getFullYear();
  var m = dd.getMonth() + 1;
  var d = dd.getDate();
  return y + "-" + (m < 10 ? '0' + m : m) + "-" + (d < 10 ? '0' + d : d);
}

/**
 * 取回网站数据列表
 * @param {Number} page   当前页
 * @param {String} search 搜索条件
 */
var current_site_page = 1;
function getWeb(page, type_id, search) {
  if (page != undefined) {
    current_site_page = page;
  }
  if (typeof search == 'undefined') {
    search = $('#site_search_input').val();
  }
  var page = page == undefined ? '1' : page;
  var order = getCookie('order');
  if (order) {
    order = '&order=' + order;
  } else {
    order = '&order=add_time desc';
  }
  var type = '';
  if (typeof type_id == 'undefined') {
    type = '&type_id=-1';
  } else {
    type = '&type_id=' + type_id;
  }
  var pdata = 'limit=10&p=' + page + '&search=' + search + order + type;
  var loadT = layer.load();
  //取回数据
  $.post('/site/list', pdata, function (data) {
    layer.close(loadT);
    //构造数据列表
    var body = '';
    $("#webBody").html(body);
    var list = data.data;
    window.site_list_cache = list;
    for (var i = 0; i < list.length; i++) {
      //当前站点状态
      var trClass = '';
      if (list[i].status == (lan && lan.site && t('site.site_auto_str_1') || "") || list[i].status == '1') {
        var status = ((lan && lan.site && t('site.site_auto_str_2') || '<a href=\'javascript:;\' title=\'停用这个站点\' onclick="webStop(')) + list[i].id + ",'" + list[i].name + ('\')" class=\'btn-defsult\'><span style=\'color:rgb(92, 184, 92)\'>' + (lan && lan.site && t('site.site_auto_str_3') || '运行中') + '</span><span style=\'color:rgb(92, 184, 92)\' class=\'glyphicon glyphicon-play\'></span></a>');
      } else {
        var status = ((lan && lan.site && t('site.site_auto_str_4') || '<a href=\'javascript:;\' title=\'启用这个站点\' onclick="webStart(')) + list[i].id + ",'" + list[i].name + ('\')" class=\'btn-defsult\'><span style=\'color:red\'>' + (lan && lan.site && t('site.site_auto_str_5') || '已停止') + '</span><span style=\'color:rgb(255, 0, 0);\' class=\'glyphicon glyphicon-pause\'></span></a>');
        trClass = ' class="danger-row"';
      }

      //是否有备份
      if (list[i].backup_count > 0) {
        var backup = "<a href='javascript:;' class='btlink' onclick=\"getBackup(" + list[i].id + ((lan && lan.site && t('site.site_auto_str_6') || ')">有备份') + '</a>');
      } else {
        var backup = "<a href='javascript:;' class='btlink' onclick=\"getBackup(" + list[i].id + ((lan && lan.site && t('site.site_auto_str_7') || ')">无备份') + '</a>');
      }
      //是否设置有效期
      var web_end_time = list[i].edate == "0000-00-00" ? lan && lan.site && t('site.site_auto_str_8') || "" : list[i].edate;
      //表格主体
      var shortwebname = list[i].name;
      var shortpath = list[i].path;
      if (list[i].name.length > 30) {
        shortwebname = list[i].name.substring(0, 30) + "...";
      }
      if (list[i].path.length > 30) {
        shortpath = list[i].path.substring(0, 30) + "...";
      }
      var idname = list[i].name.replace(/\./g, '_');
      var php_show_text = list[i].php_version == '00' ? lan && lan.site && t('site.site_auto_str_9') || "" : list[i].php_version.length == 2 ? list[i].php_version.substring(0, 1) + '.' + list[i].php_version.substring(1) : list[i].php_version;
      var php_text = "<a class='btlink php_version_click' href='javascript:;' onclick=\"changePHPVersion(0, '" + list[i].name + "', '" + list[i].php_version + "')\" style='color:#20a53a'>" + php_show_text + "</a>";
      var ssl_text = list[i].ssl_days == -1 ? "<a class='btlink' href='javascript:;' onclick=\"webEdit(" + list[i].id + ",'" + list[i].name + "','" + list[i].edate + "','" + list[i].add_time + ((lan && lan.site && t('site.site_auto_str_10') || '\', \'ssl\')" style=\'color:#bbb\'>未部署') + '</a>') : list[i].ssl_days < 10 ? "<a class='btlink' href='javascript:;' onclick=\"webEdit(" + list[i].id + ",'" + list[i].name + "','" + list[i].edate + "','" + list[i].add_time + ((lan && lan.site && t('site.site_auto_str_11') || '\', \'ssl\')" style=\'color:red\'>剩余')) + list[i].ssl_days + ((lan && lan.site && t('site.site_auto_str_12') || '天') + '</a>') : "<a class='btlink' href='javascript:;' onclick=\"webEdit(" + list[i].id + ",'" + list[i].name + "','" + list[i].edate + "','" + list[i].add_time + ((lan && lan.site && t('site.site_auto_str_13') || '\', \'ssl\')" style=\'color:#20a53a\'>剩余')) + list[i].ssl_days + ((lan && lan.site && t('site.site_auto_str_14') || '天') + '</a>');
      var daily_traffic = toSize(list[i].daily_traffic);
      var add_time_str = list[i].add_time && list[i].add_time.length >= 10 ? list[i].add_time.substring(0, 10) : list[i].add_time;
      body = "<tr" + trClass + "><td><input type='checkbox' name='id' title='" + list[i].name + "' onclick='checkSelect();' value='" + list[i].id + "'></td>\
					<td><a class='btlink webtips' href='javascript:;' onclick=\"webEdit(" + list[i].id + ",'" + list[i].name + "','" + list[i].edate + "','" + list[i].add_time + "')\" title='" + list[i].name + "'>" + shortwebname + "</td>\
					<td>" + status + "</td>\
					<td>" + backup + ('</td>					<td>' + (lan && lan.site && t('site.site_auto_str_15') || '<a class=\'btlink\' title=\'打开目录')) + list[i].path + "' href=\"javascript:openPath('" + data.data[i].path + "');\">" + shortpath + "</a></td>\
					<td>" + add_time_str + "</td>\
					<td>" + daily_traffic + "</td>\
					<td>" + php_text + "</td>\
					<td id='ssl_state_" + idname + "'>" + ssl_text + "</td>\
					<td><a class='btlink setTimes' id='site_" + list[i].id + "' data-ids='" + list[i].id + "'>" + web_end_time + "</a></td>\
					<td><a class='btlinkbed' href='javascript:;' data-id='" + list[i].id + "'>" + list[i].ps + "</a></td>\
					<td style='text-align:right; color:#bbb'>\
					<a href='javascript:;' class='btlink' onclick=\"webEdit(" + list[i].id + ",'" + list[i].name + "','" + list[i].edate + "','" + list[i].add_time + ((lan && lan.site && t('site.site_auto_str_16') || '\', \'config\')">设置') + '</a>                        | <a href=\'javascript:;\' class=\'btlink\' onclick="webDelete(\'') + list[i].id + "','" + list[i].name + ((lan && lan.site && t('site.site_auto_str_17') || '\')" title=\'删除站点\'>删除') + '</a>					</td></tr>');
      $("#webBody").append(body);
    }

    // 使用事件委托统一绑定有效期点击事件，避免内存泄漏和重复绑定
    $('#webBody').off('click', '.setTimes').on('click', '.setTimes', function () {
      var _this = $(this);
      var id = _this.attr('data-ids');
      if (!_this.data('laydate-initialized')) {
        laydate.render({
          elem: '#site_' + id,
          min: getDate(-1),
          max: '9999-12-31',
          vlue: getDate(365),
          type: 'date',
          format: 'yyyy-MM-dd',
          trigger: 'click',
          btns: ['perpetual', 'confirm'],
          theme: '#20a53a',
          done: function (dates) {
            if (_this.html() == (lan && lan.site && t('site.site_auto_str_18') || "")) {
              dates = '0000-00-00';
            }
            var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_19') || "", {
              icon: 16,
              time: 0,
              shade: [0.3, "#000"]
            });
            $.post('/site/set_end_date', 'id=' + id + '&edate=' + dates, function (rdata) {
              layer.close(loadT);
              layer.msg(rdata.msg, {
                icon: rdata.status ? 1 : 5
              });
            }, 'json');
          }
        });
        _this.data('laydate-initialized', true);
        this.click(); // 初始化后模拟点击以触发 laydate 弹窗
      }
    });
    if (body.length < 10) {
      body = '<tr><td colspan=\'9\' style=\'text-align: center;\'>' + (lan && lan.site && t('site.site_auto_str_20') || '当前没有站点数据') + '</td></tr>';
      $("#webBody").html(body);
    }
    //输出数据列表
    $(".btn-more").on('mouseenter', function () {
      $(this).addClass("open");
    }).on('mouseleave', function () {
      $(this).removeClass("open");
    });

    //输出分页
    $("#webPage").html(data.page);
    $(".btlinkbed").on('click', function () {
      var dataid = $(this).attr("data-id");
      var databak = $(this).text();
      if (databak == null) {
        databak = '';
      }
      $(this).hide().after("<input class='baktext' type='text' data-id='" + dataid + "' data-page='" + page + "' name='bak' value='" + databak + ((lan && lan.site && t('site.site_auto_str_21') || '\' placeholder=\'备注信息\' onblur=\'getBakPost("sites")\' />')));
      $(".baktext").trigger('focus');
    });
    readerTableChecked();
  }, 'json');
}
function getBakPost(b) {
  $(".baktext").hide().prev().show();
  var id = $(".baktext").attr("data-id");
  var page = $(".baktext").attr("data-page");
  var a = $(".baktext").val();
  if (a == "") {
    a = lan && lan.site && t('site.site_auto_str_22') || "";
  }
  setWebPs(b, id, a, page);
  $("a[data-id='" + id + "']").html(a);
  $(".baktext").remove();
}
function setWebPs(b, id, ps, page) {
  var d = layer.load({
    shade: true,
    shadeClose: false
  });
  var ps = 'ps=' + ps;
  $.post('/site/set_ps', 'id=' + id + "&" + ps, function (data) {
    if (data['status']) {
      getWeb(page);
      layer.closeAll();
      layer.msg(lan && lan.site && t('site.site_auto_str_23') || "", {
        icon: 1
      });
    } else {
      layer.closeAll();
      layer.msg(lan && lan.site && t('site.site_auto_str_24') || "", {
        icon: 2
      });
    }
  }, 'json');
}

//创建站点前,检查服务是否开启
function webAdd(type) {
  loading = layer.msg(lan && lan.site && t('site.site_auto_str_25') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, "#000"]
  });
  $.post('/site/check_web_status', function (data) {
    layer.close(loading);
    if (data.status) {
      webAddPage(type);
    } else {
      layer.msg(data.msg, {
        icon: 0,
        time: 3000,
        shade: [0.3, "#000"]
      });
    }
  }, 'json');
}

//添加站点
function webAddPage(type) {
  if (type == 1) {
    var array;
    var str = "";
    var domainlist = '';
    var domain = array = $("#mainDomain").val().replace('http://', '').replace('https://', '').split("\n");
    var webport = [];
    var checkDomain = domain[0].split('.');
    if (checkDomain.length < 1) {
      layer.msg(t('site.domain_err_txt'), {
        icon: 2
      });
      return;
    }
    for (var i = 1; i < domain.length; i++) {
      domainlist += '"' + domain[i] + '",';
    }
    webport = domain[0].split(":")[1]; //主域名端口
    if (webport == undefined) {
      webport = "80";
    }
    domainlist = domainlist.substring(0, domainlist.length - 1); //子域名json
    domain = '{"domain":"' + domain[0] + '","domainlist":[' + domainlist + '],"count":' + domain.length + '}'; //拼接json
    var loadT = layer.msg(t('public.the_get'), {
      icon: 16,
      time: 0,
      shade: [0.3, "#000"]
    });
    var data = $("#addweb").serialize() + "&port=" + webport + "&webinfo=" + domain;
    $.post('/site/add', data, function (ret) {
      if (ret.status == true) {
        getWeb(1);
        layer.closeAll();
        layer.msg(lan && lan.site && t('site.site_auto_str_26') || "", {
          icon: 1
        });
      } else {
        layer.msg(ret.msg, {
          icon: 2
        });
      }
      layer.close(loadT);
    }, 'json');
    return;
  }
  $.post('/site/get_php_version', function (data) {
    var rdata = data.data;
    var defaultPath = $("#defaultPath").html();
    var php_version = "<div class='line'><span class='tname'>" + t('site.php_ver') + "</span><select class='bt-input-text' name='version' id='c_k3' style='width:100px'>";
    for (var i = rdata.length - 1; i >= 0; i--) {
      php_version += "<option value='" + rdata[i].version + "'>" + rdata[i].name + "</option>";
    }
    $.post('/site/get_root_dir', function (www) {
      php_version += "</select><span id='php_w' style='color:red;margin-left: 10px;'></span></div>";
      layer.open({
        type: 1,
        skin: 'demo-class',
        area: '640px',
        title: lan && lan.site && t('site.site_auto_str_27') || "",
        closeBtn: 1,
        shift: 0,
        shadeClose: false,
        content: "<form class='bt-form pd20 pb70' id='addweb'>\
				<div class='line'>\
                    <span class='tname'>" + t('site.domain') + ('</span>                    <div class=\'info-r c4\'>						<textarea id=\'mainDomain\' class=\'bt-input-text\' name=\'webname\' style=\'width:458px;height:100px;line-height:22px\'></textarea>					</div>				</div>                <div class=\'line\'>                <span class=\'tname\'>' + (lan && lan.site && t('site.site_auto_str_28') || '备注') + '</span>                <div class=\'info-r c4\'>                	<input id=\'Wbeizhu\' class=\'bt-input-text\' type=\'text\' name=\'ps\' placeholder=\'网站备注\' style=\'width:458px\' />                </div>                </div>                <div class=\'line\'>                <span class=\'tname\'>' + (lan && lan.site && t('site.site_auto_str_28_1') || '根目录') + '</span>                <div class=\'info-r c4\'>                	<input id=\'inputPath\' class=\'bt-input-text mr5\' type=\'text\' name=\'path\' value=\'') + www['dir'] + "/' placeholder='" + www['dir'] + "' style='width:458px' />\
                	<span class='glyphicon glyphicon-folder-open cursor' onclick='changePath(\"inputPath\")'></span>\
                </div>\
                </div>\
				" + php_version + ('                <div class=\'bt-form-submit-btn\'>					<button type=\'button\' class=\'btn btn-danger btn-sm btn-title\' onclick=\'layer.closeAll()\'>' + (lan && lan.site && t('site.site_auto_str_29') || '取消') + '</button>					<button type=\'button\' class=\'btn btn-success btn-sm btn-title\' onclick="webAdd(1)">' + (lan && lan.site && t('site.site_auto_str_29_1') || '提交') + '</button>				</div>            </form>')
      });
      $(function () {
        var placeholder = "<div class='placeholder c9' style='top:10px;left:10px'>" + t('site.domain_help') + "</div>";
        $('#mainDomain').after(placeholder);
        $(".placeholder").on('click', function () {
          $(this).hide();
          $('#mainDomain').trigger('focus');
        });
        $('#mainDomain').on('focus', function () {
          $(".placeholder").hide();
        });
        $('#mainDomain').on('blur', function () {
          if ($(this).val().length == 0) {
            $(".placeholder").show();
          }
        });

        //验证PHP版本
        $("select[name='version']").on('change', function () {
          if ($(this).val() == '52') {
            var msgerr = lan && lan.site && t('site.site_auto_str_30') || "";
            $('#php_w').text(msgerr);
          } else {
            $('#php_w').text('');
          }
        });
        $('#mainDomain').on('input', function () {
          var array;
          var res, ress;
          var str = $(this).val().replace('http://', '').replace('https://', '');
          var len = str.replace(/[^\x00-\xff]/g, "**").length;
          array = str.split("\n");
          ress = array[0].split(":")[0];
          res = ress.replace(new RegExp(/([-.])/g), '_');
          if (res.length > 15) {
            res = res.substr(0, 15);
          }
          var placeholder = $("#inputPath").attr('placeholder');
          $("#inputPath").val(placeholder + '/' + ress);
          if (res.length > 15) {
            res = res.substr(0, 15);
          }
          $("#Wbeizhu").val(ress);
        });

        //备注
        $('#Wbeizhu').on('input', function () {
          var str = $(this).val();
          var len = str.replace(/[^\x00-\xff]/g, "**").length;
          if (len > 20) {
            str = str.substring(0, 20);
            $(this).val(str);
            layer.msg(lan && lan.site && t('site.site_auto_str_31') || "", {
              icon: 0
            });
          }
        });
        //获取当前时间时间戳，截取后6位
        var timestamp = new Date().getTime().toString();
        var dtpw = timestamp.substring(7);
      });
    }, 'json');
  }, 'json');
}

//修改网站目录
function webPathEdit(id) {
  $.post('/site/get_dir_user_ini', 'id=' + id, function (data) {
    var data = data['data'];
    var site_path = data['path'];
    var site_name = data['name'];
    var run_path = data['run_path']['run_path'];
    var user_ini_checked = data.user_ini ? 'checked' : '';
    var logs_checked = data.logs ? 'checked' : '';
    var opt = '';
    var selected = '';
    for (var i = 0; i < data.run_path.dirs.length; i++) {
      selected = '';
      if (data.run_path.dirs[i] == data.run_path.path) {
        selected = 'selected';
      }
      opt += '<option value="' + data.run_path.dirs[i] + '" ' + selected + '>' + data.run_path.dirs[i] + '</option>';
    }
    var content = "<div class='webedit-box soft-man-con'>\
					<div class='label-input-group ptb10'>\
						<input type='checkbox' name='userini' id='userini'" + user_ini_checked + (' /><label class=\'mr20\' for=\'userini\' style=\'font-weight:normal\'>' + (lan && lan.site && t('site.site_auto_str_32') || '防跨站攻击(open_basedir)') + '</label>						<input type=\'checkbox\' name=\'logs\' id=\'logs\'') + logs_checked + (' /><label for=\'logs\' style=\'font-weight:normal\'>' + (lan && lan.site && t('site.site_auto_str_33') || '写访问日志') + '</label>					</div>					<div class=\'line mt10\'>						<span class=\'mr5\'>' + (lan && lan.site && t('site.site_auto_str_33_1') || '网站目录') + '</span>						' + (lan && lan.site && t('site.site_auto_str_33_2') || '<input class=\'bt-input-text mr5\' type=\'text\' style=\'width:50%\' placeholder=\'网站根目录\' value=\'')) + site_path + "' name='webdir' id='inputPath'>\
						<span onclick='changePath(&quot;inputPath&quot;)' class='glyphicon glyphicon-folder-open cursor mr20'></span>\
						<button class='btn btn-success btn-sm' onclick='setSitePath(" + id + ((lan && lan.site && t('site.site_auto_str_34') || ')\'>保存') + '</button>					</div>					<div class=\'line mtb15\'>						<span class=\'mr5\'>' + (lan && lan.site && t('site.site_auto_str_34_1') || '运行目录') + '</span>						<select class=\'bt-input-text\' type=\'text\' style=\'width:50%; margin-right:41px\' name=\'runPath\' id=\'runPath\'>') + opt + "</select>\
						<button class='btn btn-success btn-sm' onclick='setSiteRunPath(" + id + ((lan && lan.site && t('site.site_auto_str_35') || ')\' style=\'margin-top: -1px;\'>保存') + '</button>					</div>					<ul class=\'help-info-text c7 ptb10\'>						<li>' + (lan && lan.site && t('site.site_auto_str_35_1') || '部分程序需要指定二级目录作为运行目录，如ThinkPHP5，Laravel') + '</li>						<li>' + (lan && lan.site && t('site.site_auto_str_35_2') || '选择您的运行目录，点保存即可') + '</li>					</ul>') + '<div class="user_pw_tit" style="margin-top: -8px;padding-top: 11px;">' + ('<span class="tit">' + (lan && lan.site && t('site.site_auto_str_36') || '密码访问') + '</span>') + '<span class="btswitch-p"><input ' + (data.pass ? 'checked' : '') + ' class="btswitch btswitch-ios" id="pathSafe" type="checkbox">' + '<label class="btswitch-btn phpmyadmin-btn" for="pathSafe" onclick="pathSafe(' + id + ')"></label>' + '</span>' + '</div>' + '<div class="user_pw" style="margin-top: 10px;display:' + (data.pass ? 'block;' : 'none;') + '">' + ('<p><span>' + (lan && lan.site && t('site.site_auto_str_37') || '授权账号') + '</span><input id="username_get" class="bt-input-text" name="username_get" value="" type="text" placeholder="不修改请留空"></p>') + ('<p><span>' + (lan && lan.site && t('site.site_auto_str_38') || '访问密码') + '</span><input id="password_get_1" class="bt-input-text" name="password_get_1" value="" type="password" placeholder="不修改请留空"></p>') + ('<p><span>' + (lan && lan.site && t('site.site_auto_str_39') || '重复密码') + '</span><input id="password_get_2" class="bt-input-text" name="password_get_1" value="" type="password" placeholder="不修改请留空"></p>') + '<p><button class="btn btn-success btn-sm" onclick="setPathSafe(' + id + ((lan && lan.site && t('site.site_auto_str_40') || ')">保存') + '</button></p>') + '</div>' + '</div>';
    $("#webedit-con").html(content);
    $("#userini").on('change', function () {
      $.post('/site/set_dir_user_ini', {
        'path': site_path,
        'run_path': run_path
      }, function (userini) {
        layer.msg(data.msg + ('<p style="color:red;">' + (lan && lan.site && t('site.site_auto_str_41') || '注意：设置防跨站需要重启PHP才能生效!') + '</p>'), {
          icon: data.status ? 1 : 2
        });
        tryRestartPHP(site_name);
      }, 'json');
    });
    $("#logs").on('change', function () {
      var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_42') || "", {
        icon: 16,
        time: 10000,
        shade: [0.3, '#000']
      });
      $.post('/site/logs_open', 'id=' + id, function (rdata) {
        layer.close(loadT);
        layer.msg(rdata.msg, {
          icon: rdata.status ? 1 : 2
        });
      }, 'json');
    });
  }, 'json');
}

//是否设置访问密码
function pathSafe(id) {
  var isPass = $('#pathSafe').prop('checked');
  if (!isPass) {
    $(".user_pw").show();
  } else {
    var loadT = layer.msg(t('public.the'), {
      icon: 16,
      time: 10000,
      shade: [0.3, '#000']
    });
    $.post('/site/close_has_pwd', {
      id: id
    }, function (rdata) {
      layer.close(loadT);
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
      $(".user_pw").hide();
    }, 'json');
  }
}

//设置访问密码
function setPathSafe(id) {
  var username = $("#username_get").val();
  var pass1 = $("#password_get_1").val();
  var pass2 = $("#password_get_2").val();
  if (pass1 != pass2) {
    layer.msg(lan && lan.site && t('site.site_auto_str_43') || "", {
      icon: 2
    });
    return;
  }
  var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_44') || "", {
    icon: 16,
    time: 10000,
    shade: [0.3, '#000']
  });
  $.post('/site/set_has_pwd', {
    id: id,
    username: username,
    password: pass1
  }, function (rdata) {
    layer.close(loadT);
    layer.msg(rdata.msg, {
      icon: rdata.status ? 1 : 2
    });
  }, 'json');
}

//提交运行目录
function setSiteRunPath(id) {
  var NewPath = $("#runPath").val();
  var loadT = layer.msg(t('public.the'), {
    icon: 16,
    time: 10000,
    shade: [0.3, '#000']
  });
  $.post('/site/set_site_run_path', 'id=' + id + '&run_path=' + NewPath, function (rdata) {
    layer.close(loadT);
    layer.msg(rdata.msg, {
      icon: rdata.status ? 1 : 2
    });
  }, 'json');
}

//提交网站目录
function setSitePath(id) {
  var NewPath = $("#inputPath").val();
  var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_45') || "", {
    icon: 16,
    time: 10000,
    shade: [0.3, '#000']
  });
  $.post('/site/set_path', 'id=' + id + '&path=' + NewPath, function (rdata) {
    layer.close(loadT);
    layer.msg(rdata.msg, {
      icon: rdata.status ? 1 : 2
    });
  }, 'json');
}

//修改网站备注
function webBakEdit(id) {
  $.post("/data?action=getKey','table=sites&key=ps&id=" + id, function (rdata) {
    var webBakHtml = "<div class='webEdit-box padding-10'>\
			<div class='line'>\
			<label><span>" + t('site.note_ph') + "</span></label>\
			<div class='info-r'>\
			<textarea name='beizhu' id='webbeizhu' col='5' style='width:96%'>" + rdata + "</textarea>\
			<br><br><button class='btn btn-success btn-sm' onclick='SetSitePs(" + id + ((lan && lan.site && t('site.site_auto_str_46') || ')\'>保存') + '</button>			</div>		</div>');
    $("#webedit-con").html(webBakHtml);
  });
}

//设置默认文档
function setIndexEdit(id) {
  $.post('/site/get_index', 'id=' + id, function (data) {
    var rdata = data['index'];
    rdata = rdata.replace(new RegExp(/(,)/g), "\n");
    var setIndexHtml = "<div id='SetIndex'><div class='SetIndex'>\
				<div class='line'>\
						<textarea class='bt-input-text' id='Dindex' name='files' style='height: 180px; width:50%; line-height:20px'>" + rdata + "</textarea>\
						<button type='button' class='btn btn-success btn-sm pull-right' onclick='setIndexList(" + id + ")' style='margin: 70px 130px 0px 0px;'>" + t('public.save') + ('</button>				</div>				<ul class=\'help-info-text c7 ptb10\'>					<li>' + (lan && lan.site && t('site.site_auto_str_47') || '默认文档，每行一个，优先级由上至下。') + '</li>				</ul>				</div></div>');
    $("#webedit-con").html(setIndexHtml);
  }, 'json');
}

/**
 * 停止一个站点
 * @param {Int} wid  网站ID
 * @param {String} wname 网站名称
 */
function webStop(wid, wname) {
  layer.confirm(lan && lan.site && t('site.site_auto_str_48') || "", {
    icon: 3,
    closeBtn: 2
  }, function (index) {
    if (index > 0) {
      var loadT = layer.load();
      $.post("/site/stop", "id=" + wid + "&name=" + wname, function (ret) {
        layer.msg(ret.msg, {
          icon: ret.status ? 1 : 2
        });
        layer.close(loadT);
        getWeb(1);
      }, 'json');
    }
  });
}

/**
 * 启动一个网站
 * @param {Number} wid 网站ID
 * @param {String} wname 网站名称
 */
function webStart(wid, wname) {
  layer.confirm(lan && lan.site && t('site.site_auto_str_49') || "", {
    icon: 3,
    closeBtn: 2
  }, function (index) {
    if (index > 0) {
      var loadT = layer.load();
      $.post("/site/start", "id=" + wid + "&name=" + wname, function (ret) {
        layer.msg(ret.msg, {
          icon: ret.status ? 1 : 2
        });
        layer.close(loadT);
        getWeb(1);
      }, 'json');
    }
  });
}

/**
 * 删除一个网站
 * @param {Number} wid 网站ID
 * @param {String} wname 网站名称
 */
function webDelete(wid, wname) {
  var thtml = '<div class=\'options\'>	    	<label><input type=\'checkbox\' id=\'delpath\' name=\'path\'><span>' + (lan && lan.site && t('site.site_auto_str_50') || '根目录') + '</span></label>	    	</div>';
  var info = lan && lan.site && t('site.site_auto_str_51') || "";
  safeMessage((lan && lan.site && t('site.site_auto_str_52') || "") + "【" + wname + "】", info, function () {
    var path = '';
    if ($("#delpath").is(":checked")) {
      path = '&path=1';
    }
    var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_53') || "", {
      icon: 16,
      time: 10000,
      shade: [0.3, '#000']
    });
    $.post("/site/delete", "id=" + wid + "&webname=" + wname + path, function (ret) {
      layer.closeAll();
      layer.msg(ret.msg, {
        icon: ret.status ? 1 : 2
      });
      getWeb(1);
    }, 'json');
  }, thtml);
}

//批量删除
function allDeleteSite() {
  var checkList = $("input[name=id]");
  var dataList = new Array();
  for (var i = 0; i < checkList.length; i++) {
    if (!checkList[i].checked) continue;
    var tmp = new Object();
    tmp.name = checkList[i].title;
    tmp.id = checkList[i].value;
    dataList.push(tmp);
  }
  var thtml = "<div class='options'>\
	    	<label style=\"width:100%;\"><input type='checkbox' id='delpath' name='path'><span>" + t('site.all_del_info') + "</span></label>\
	    	</div>";
  safeMessage(t('site.all_del_site'), "<a style='color:red;'>" + t('del_all_site', [dataList.length]) + "</a>", function () {
    layer.closeAll();
    var path = '';
    if ($("#delpath").is(":checked")) {
      path = '&path=1';
    }
    syncDeleteSite(dataList, 0, '', path);
  }, thtml);
}

//模拟同步开始批量删除
function syncDeleteSite(dataList, successCount, errorMsg, path) {
  if (dataList.length < 1) {
    showMsg(t('del_all_site_ok', [successCount]), function () {
      // location.reload();
    }, {
      icon: 1
    });
    return;
  }
  var loadT = layer.msg(t('del_all_task_the', [dataList[0].name]), {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/site/delete', 'id=' + dataList[0].id + '&webname=' + dataList[0].name + path, function (rdata) {
    layer.close(loadT);
    if (rdata.status) {
      successCount++;
      $("input[title='" + dataList[0].name + "']").parents("tr").remove();
    } else {
      if (!errorMsg) {
        errorMsg = '<br><p>' + t('site.del_err') + ':</p>';
      }
      errorMsg += '<li>' + dataList[0].name + ' -> ' + rdata.msg + '</li>';
    }
    dataList.splice(0, 1);
    syncDeleteSite(dataList, successCount, errorMsg, path);
  }, 'json');
}

/**
 * 域名管理
 * @param {Int} id 网站ID
 */
function domainEdit(id, name, msg, status) {
  $.post('/site/get_domain', {
    pid: id
  }, function (data) {
    var domain = data.data;
    var echoHtml = "";
    for (var i = 0; i < domain.length; i++) {
      echoHtml += "<tr>\
				<td><a title='" + t('site.click_access') + "' target='_blank' href='http://" + domain[i].name + (domain[i].port == '80' ? '' : ':' + domain[i].port) + "' class='btlinkbed'>" + domain[i].name + "</a></td>\
				<td><a class='btlinkbed'>" + domain[i].port + "</a></td>\
				<td class='text-center'><a class='table-btn-del' href='javascript:;' onclick=\"delDomain(" + id + ",'" + name + "','" + domain[i].name + "','" + domain[i].port + "',1)\"><span class='glyphicon glyphicon-trash'></span></a></td>\
				</tr>";
    }
    var bodyHtml = "<textarea id='newdomain' class='bt-input-text' style='height: 100px; width: 340px;padding:5px 10px;line-height:20px'></textarea>\
								<input type='hidden' id='newport' value='80' />\
								<button type='button' class='btn btn-success btn-sm pull-right' style='margin:30px 35px 0 0' onclick=\"domainAdd(" + id + ",'" + name + ((lan && lan.site && t('site.site_auto_str_54') || '\',1)">添加') + '</button>							<div class=\'divtable mtb15\' style=\'height:420px;overflow:auto\'>								<table class=\'table table-hover\' width=\'100%\'>								<thead><tr><th>') + t('site.domain') + ('</th><th width=\'70px\'>' + (lan && lan.site && t('site.site_auto_str_55') || '端口') + '</th><th width=\'50px\' class=\'text-center\'>' + (lan && lan.site && t('site.site_auto_str_55_1') || '操作') + '</th></tr></thead>								<tbody id=\'checkDomain\'>') + echoHtml + "</tbody>\
								</table>\
							</div>";
    $("#webedit-con").html(bodyHtml);
    if (msg != undefined) {
      layer.msg(msg, {
        icon: status ? 1 : 5
      });
    }
    var placeholder = '<div class=\'placeholder c9\' style=\'left:28px;width:330px;top:16px;\'>' + (lan && lan.site && t('site.site_auto_str_56') || '每行填写一个域名，默认为80端口') + '<br>' + (lan && lan.site && t('site.site_auto_str_56_1') || '泛解析添加方法 *.domain.com') + '<br>' + (lan && lan.site && t('site.site_auto_str_56_2') || '如另加端口格式为 www.domain.com:88') + '</div>';
    $('#newdomain').after(placeholder);
    $(".placeholder").on('click', function () {
      $(this).hide();
      $('#newdomain').trigger('focus');
    });
    $('#newdomain').on('focus', function () {
      $(".placeholder").hide();
    });
    $('#newdomain').on('blur', function () {
      if ($(this).val().length == 0) {
        $(".placeholder").show();
      }
    });
    $("#newdomain").on("input", function () {
      var str = $(this).val();
      if (isChineseChar(str)) {
        $('.btn-zhm').show();
      } else {
        $('.btn-zhm').hide();
      }
    });
    //checkDomain();
  }, 'json');
}

//编辑域名/端口
function cancelSend() {
  $(".changeDomain,.changePort").hide().prev().show();
  $(".changeDomain,.changePort").remove();
}
//遍历域名
function checkDomain() {
  $("#checkDomain tr").each(function () {
    var $this = $(this);
    var domain = $(this).find("td:first-child").text();
    $(this).find("td:first-child").append("<i class='lading'></i>");
  });
}

/**
 * 添加域名
 * @param {Int} id  网站ID
 * @param {String} webname 主域名
 */
function domainAdd(id, webname, type) {
  var Domain = $("#newdomain").val().split("\n");
  var domainlist = '';
  for (var i = 0; i < Domain.length; i++) {
    domainlist += Domain[i] + ',';
  }
  if (domainlist.length < 3) {
    layer.msg(t('site.domain_empty'), {
      icon: 5
    });
    return;
  }
  domainlist = domainlist.substring(0, domainlist.length - 1);
  var loadT = layer.load();
  var data = "domain=" + domainlist + "&site_name=" + webname + "&id=" + id;
  $.post('/site/add_domain', data, function (retuls) {
    layer.close(loadT);
    domainEdit(id, webname, retuls.msg, retuls.status);
  }, 'json');
}

/**
 * 删除域名
 * @param {Number} wid 网站ID
 * @param {String} wname 主域名
 * @param {String} domain 欲删除的域名
 * @param {Number} port 对应的端口
 */
function delDomain(wid, wname, domain, port, type) {
  var num = $("#checkDomain").find("tr").length;
  if (num == 1) {
    layer.msg(t('site.domain_last_cannot'));
  }
  layer.confirm(t('site.domain_del_confirm'), {
    icon: 3,
    closeBtn: 2
  }, function (index) {
    var data = "id=" + wid + "&site_name=" + wname + "&domain=" + domain + "&port=" + port;
    var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_57') || "", {
      time: 0,
      icon: 16
    });
    $.post('/site/del_domain', data, function (ret) {
      layer.close(loadT);
      layer.msg(ret.msg, {
        icon: ret.status ? 1 : 2
      });
      if (type == 1) {
        layer.close(loadT);
        domainEdit(wid, wname);
      } else {
        layer.closeAll();
        DomainRoot(wid, wname);
      }
    }, 'json');
  });
}

/**
 * 判断IP/域名格式
 * @param {String} domain  源文本
 * @return bool
 */
function isDomain(domain) {
  //domain = 'http://'+domain;
  var re = new RegExp();
  re.compile("^[A-Za-z0-9-_]+\\.[A-Za-z0-9-_%&\?\/.=]+$");
  if (re.test(domain)) {
    return true;
  } else {
    return false;
  }
}

/**
 *设置数据库备份
 * @param {Number} sign	操作标识
 * @param {Number} id	编号
 * @param {String} name	主域名
 */
function webBackup(id, name) {
  var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_58') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/site/to_backup', "id=" + id, function (rdata) {
    layer.closeAll();
    layer.msg(rdata.msg, {
      icon: rdata.status ? 1 : 2
    });
    getBackup(id);
  }, 'json');
}

/**
 *删除网站备份
 * @param {Number} webid	网站编号
 * @param {Number} id	文件编号
 * @param {String} name	主域名
 */
function webBackupDelete(id, pid) {
  layer.confirm(lan && lan.site && t('site.site_auto_str_59') || "", {
    title: lan && lan.site && t('site.site_auto_str_60') || "",
    icon: 3,
    closeBtn: 2
  }, function (index) {
    var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_61') || "", {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.post('/site/del_backup', 'id=' + id, function (rdata) {
      layer.closeAll();
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
      getBackup(pid);
    }, 'json');
  });
}
function getBackup(id, name, page) {
  if (typeof page == 'undefined') {
    page = '1';
  }
  $.post('/site/get_backup', 'search=' + id + '&limit=5&p=' + page, function (frdata) {
    var body = '';
    for (var i = 0; i < frdata.data.length; i++) {
      if (frdata.data[i].type == '1') {
        continue;
      }
      var ftpdown = "<a class='btlink' href='/files/download?filename=" + frdata.data[i].filename + "&name=" + frdata.data[i].name + ((lan && lan.site && t('site.site_auto_str_62') || '\' target=\'_blank\'>下载') + '</a> | ');
      body += "<tr><td><span class='glyphicon glyphicon-file'></span>" + frdata.data[i].name + "</td>\
					<td>" + toSize(frdata.data[i].size) + "</td>\
					<td>" + frdata.data[i].add_time + "</td>\
					<td class='text-right' style='color:#ccc'>" + ftpdown + "<a class='btlink' href='javascript:;' onclick=\"webBackupDelete('" + frdata.data[i].id + "'," + id + ((lan && lan.site && t('site.site_auto_str_63') || ')">删除') + '</a></td>				</tr>');
    }
    var ftpdown = '';
    frdata.page = frdata.page.replace(/'/g, '"').replace(/getBackup\(/g, "getBackup(" + id + ",0,");
    if (name == 0) {
      var sBody = ('<table width=\'100%\' id=\'webBackupList\' class=\'table table-hover\'>				<thead><tr><th>' + (lan && lan.site && t('site.site_auto_str_64') || '文件名称') + '</th><th>' + (lan && lan.site && t('site.site_auto_str_64_1') || '文件大小') + '</th><th>' + (lan && lan.site && t('site.site_auto_str_64_2') || '打包时间') + '</th><th width=\'140px\' class=\'text-right\'>' + (lan && lan.site && t('site.site_auto_str_64_3') || '操作') + '</th></tr></thead>				<tbody id=\'webBackupBody\' class=\'list-list\'>') + body + "</tbody>\
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
      title: lan && lan.site && t('site.site_auto_str_65') || "",
      closeBtn: 1,
      shift: 0,
      shadeClose: false,
      content: "<div class='bt-form ptb15 mlr15' id='webBackup'>\
				<button class='btn btn-default btn-sm' style='margin-right:10px' type='button' onclick=\"webBackup('" + frdata['site']['id'] + "','" + frdata['site']['name'] + ((lan && lan.site && t('site.site_auto_str_66') || '\')">打包备份') + '</button>				<div class=\'divtable mtb15\' style=\'margin-bottom:0\'>					<table width=\'100%\' id=\'webBackupList\' class=\'table table-hover\'>					<thead>						<tr><th>' + (lan && lan.site && t('site.site_auto_str_66_1') || '文件名称') + '</th><th>' + (lan && lan.site && t('site.site_auto_str_66_2') || '文件大小') + '</th><th>' + (lan && lan.site && t('site.site_auto_str_66_3') || '打包时间') + '</th><th width=\'140px\' class=\'text-right\'>' + (lan && lan.site && t('site.site_auto_str_66_4') || '操作') + '</th></tr>					</thead>					<tbody id=\'webBackupBody\' class=\'list-list\'>') + body + "</tbody>\
					</table>\
					<div class='page'>" + frdata.page + "</div>\
				</div>\
			</div>"
    });
  }, 'json');
}
function goSet(num) {
  //取选中对象
  var el = document.getElementsByTagName('input');
  var len = el.length;
  var data = '';
  var a = '';
  var count = 0;
  //构造POST数据
  for (var i = 0; i < len; i++) {
    if (el[i].checked == true && el[i].value != 'on') {
      data += a + count + '=' + el[i].value;
      a = '&';
      count++;
    }
  }
  //判断操作类别
  if (num == 1) {
    reAdd(data);
  } else if (num == 2) {
    shift(data);
  }
}

//设置默认文档
function setIndex(id) {
  var quanju = id == undefined ? t('site.public_set') : t('site.local_site');
  var data = id == undefined ? "" : "id=" + id;
  $.post('/site?action=GetIndex', data, function (rdata) {
    rdata = rdata.replace(new RegExp(/(,)/g), "\n");
    layer.open({
      type: 1,
      area: '500px',
      title: t('site.setindex'),
      closeBtn: 1,
      shift: 5,
      shadeClose: true,
      content: "<form class='bt-form' id='SetIndex'><div class='SetIndex'>" + "<div class='line'>" + "	<span class='tname' style='padding-right:2px'>" + t('site.default_doc') + "</span>" + "	<div class='info-r'>" + "		<textarea id='Dindex' name='files' style='line-height:20px'>" + rdata + "</textarea>" + "		<p>" + quanju + t('site.default_doc_help') + "</p>" + "	</div>" + "</div>" + "<div class='bt-form-submit-btn'>" + "	<button type='button' id='web_end_time' class='btn btn-danger btn-sm btn-title' onclick='layer.closeAll()'>" + t('public.cancel') + "</button>" + "    <button type='button' class='btn btn-success btn-sm btn-title' onclick='setIndexList(" + id + ")'>" + t('public.ok') + "</button>" + "</div>" + "</div></form>"
    });
  });
}

//设置默认站点
function setDefaultSite() {
  var name = $("#default_site").val();
  var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_67') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/site/set_default_site', 'name=' + name, function (rdata) {
    layer.closeAll();
    layer.msg(rdata.msg, {
      icon: rdata.status ? 1 : 5
    });
  }, 'json');
}

//默认站点
function getDefaultSite() {
  $.post('/site/get_default_site', '', function (rdata) {
    var opt = '<option value="off">' + (lan && lan.site && t('site.site_auto_str_68') || '未设置默认站点') + '</option>';
    var selected = '';
    for (var i = 0; i < rdata.sites.length; i++) {
      selected = '';
      if (rdata.default_site == rdata.sites[i].name) selected = 'selected';
      opt += '<option value="' + rdata.sites[i].name + '" ' + selected + '>' + rdata.sites[i].name + '</option>';
    }
    layer.open({
      type: 1,
      area: '530px',
      title: lan && lan.site && t('site.site_auto_str_69') || "",
      closeBtn: 1,
      shift: 5,
      shadeClose: true,
      content: ('<div class="bt-form ptb15 pb70">						<p class="line">							<span class="tname text-right">' + (lan && lan.site && t('site.site_auto_str_70') || '默认站点') + '</span>							<select id="default_site" class="bt-input-text" style="width: 300px;">') + opt + ('</select>						</p>						<ul class="help-info-text c6 plr20">						    <li>' + (lan && lan.site && t('site.site_auto_str_71') || '设置默认站点后,所有未绑定的域名和IP都被定向到默认站点') + '</li>						    <li>' + (lan && lan.site && t('site.site_auto_str_71_1') || '可有效防止恶意解析') + '</li>					    </ul>						<div class="bt-form-submit-btn">							<button type="button" class="btn btn-danger btn-sm btn-title" onclick="layer.closeAll()">' + (lan && lan.site && t('site.site_auto_str_71_2') || '取消') + '</button>							<button class="btn btn-success btn-sm btn-title" onclick="setDefaultSite()">' + (lan && lan.site && t('site.site_auto_str_71_3') || '确定') + '</button>						</div>					</div>')
    });
  }, 'json');
}
function setPHPVer() {
  $.post('/site/get_cli_php_version', '', function (rdata) {
    if (typeof rdata['status'] != 'undefined') {
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
      return;
    }
    var opt = '';
    var selected = '';
    for (var i = 0; i < rdata.versions.length; i++) {
      selected = '';
      if (rdata.select.version == rdata.versions[i].version) selected = 'selected';
      if (rdata.versions[i].version.indexOf("yum") > -1) {
        continue;
      }
      if (rdata.versions[i].version.indexOf("apt") > -1) {
        continue;
      }
      opt += '<option value="' + rdata.versions[i].version + '" ' + selected + '>' + rdata.versions[i].name + '</option>';
    }
    var phpver_layer = layer.open({
      type: 1,
      area: '530px',
      title: lan && lan.site && t('site.site_auto_str_72') || "",
      closeBtn: 1,
      shift: 5,
      shadeClose: true,
      btn: [lan && lan.site && t('site.site_auto_str_73') || "", lan && lan.site && t('site.site_auto_str_74') || ""],
      content: ('<div class="bt-form ptb15">						<p class="line">							<span class="tname text-right">' + (lan && lan.site && t('site.site_auto_str_75') || 'PHP-CLI版本') + '</span>							<select id="default_ver" class="bt-input-text" style="width: 300px;">') + opt + ('</select>						</p>						<ul class="help-info-text c6 plr20">						    <li>' + (lan && lan.site && t('site.site_auto_str_76') || '此处可设置命令行运行php时使用的PHP版本') + '</li>						    <li>' + (lan && lan.site && t('site.site_auto_str_76_1') || '安装新的PHP版本后此处需要重新设置') + '</li>					    </ul>					</div>'),
      yes: function (layero, index) {
        var version = $("#default_ver").val();
        var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_77') || "", {
          icon: 16,
          time: 0,
          shade: [0.3, '#000']
        });
        $.post('/site/set_cli_php_version', 'version=' + version, function (rdata) {
          layer.close(loadT);
          showMsg(rdata.msg, function () {
            if (rdata.status) {
              layer.close(phpver_layer);
            }
          }, {
            icon: rdata.status ? 1 : 5
          }, 2000);
        }, 'json');
      }
    });
  }, 'json');
}
function setIndexList(id) {
  var Dindex = $("#Dindex").val().replace(new RegExp(/(\n)/g), ",");
  if (id == undefined) {
    var data = "id=&index=" + Dindex;
  } else {
    var data = "id=" + id + "&index=" + Dindex;
  }
  var loadT = layer.load(2);
  $.post('/site/set_index', data, function (rdata) {
    layer.close(loadT);
    var ico = rdata.status ? 1 : 5;
    layer.msg(rdata.msg, {
      icon: ico
    });
  }, 'json');
}

/* 站点修改 */
function webEdit(id, website, endTime, addtime, defaultTab) {
  var hasProxy = false;
  if (window.site_list_cache) {
    for (var i = 0; i < window.site_list_cache.length; i++) {
      if (window.site_list_cache[i].id == id) {
        hasProxy = window.site_list_cache[i].has_proxy;
        break;
      }
    }
  }
  // 暂时关闭 - 子目录绑定
  // <p onclick='dirBinding("+id+")'>子目录绑定</p>\
  layer.open({
    type: 1,
    area: ['950px', '780px'],
    title: (lan && lan.site && t('site.site_auto_str_78') || "") + website + (lan && lan.site && t('site.site_auto_str_79') || "") + addtime + ']',
    closeBtn: 1,
    shift: 0,
    content: "<div class='bt-form'>\
			<div class='bt-w-menu pull-left'>\
				<p class='bgw' onclick=\"domainEdit(" + id + ",'" + website + ((lan && lan.site && t('site.site_auto_str_80') || '\')">域名管理') + '</p>				<p onclick=\'dirBinding(') + id + ((lan && lan.site && t('site.site_auto_str_81') || ')\'>子目录绑定') + '</p>				<p onclick=\'webPathEdit(') + id + ((lan && lan.site && t('site.site_auto_str_82') || ')\'>网站目录') + '</p>				<p onclick=\'limitNet(') + id + ((lan && lan.site && t('site.site_auto_str_83') || ')\'>流量限制') + '</p>				<p onclick="rewrite(\'') + website + ((lan && lan.site && t('site.site_auto_str_84') || '\')">伪静态') + '</p>				<p onclick=\'setIndexEdit(') + id + ((lan && lan.site && t('site.site_auto_str_85') || ')\'>默认文档') + '</p>				<p onclick="configFile(\'') + website + ((lan && lan.site && t('site.site_auto_str_86') || '\')">配置文件') + '</p>				<p onclick="setSSL(') + id + ",'" + website + "')\">SSL</p>\
				<p onclick=\"phpVersion('" + website + ((lan && lan.site && t('site.site_auto_str_87') || '\')">PHP版本') + '</p>				<p onclick="to301(\'') + website + ((lan && lan.site && t('site.site_auto_str_88') || '\')">重定向') + '</p>				<p onclick="toProxy(\'') + website + ((lan && lan.site && t('site.site_auto_str_89') || '\')">反向代理')) + (hasProxy ? "<span style='color:red; font-size:12px; margin-left:3px'>●</span>" : "") + "</p>\
				<p id='site_" + id + "' onclick=\"security('" + id + "','" + website + ((lan && lan.site && t('site.site_auto_str_90') || '\')">防盗链') + '</p>				<p id=\'site_') + id + "' onclick=\"getSiteLogs('" + website + ((lan && lan.site && t('site.site_auto_str_91') || '\')">响应日志') + '</p>				<p id=\'site_') + id + "' onclick=\"getSiteErrorLogs('" + website + ((lan && lan.site && t('site.site_auto_str_92') || '\')">错误日志') + '</p>			</div>			<div id=\'webedit-con\' class=\'bt-w-con webedit-con pd15\' style=\'height: 100%;overflow: auto;\'></div>		</div>'),
    success: function () {
      //域名输入提示
      var placeholder = '<div class=\'placeholder\'>' + (lan && lan.site && t('site.site_auto_str_93') || '每行填写一个域名，默认为80端口') + '<br>' + (lan && lan.site && t('site.site_auto_str_93_1') || '泛解析添加方法 *.domain.com') + '<br>' + (lan && lan.site && t('site.site_auto_str_93_2') || '如另加端口格式为 www.domain.com:88') + '</div>';
      $('#newdomain').after(placeholder);
      $(".placeholder").on('click', function () {
        $(this).hide();
        $('#newdomain').trigger('focus');
      });
      $('#newdomain').on('focus', function () {
        $(".placeholder").hide();
      });
      $('#newdomain').on('blur', function () {
        if ($(this).val().length == 0) {
          $(".placeholder").show();
        }
      });

      //切换
      $(".bt-w-menu p").on('click', function () {
        $(this).addClass("bgw").siblings().removeClass("bgw");
      });
      if (defaultTab === 'ssl') {
        var sslTab = $(".bt-w-menu p:contains('SSL')");
        sslTab.addClass("bgw").siblings().removeClass("bgw");
        setSSL(id, website);
      } else if (defaultTab === 'config') {
        var configTab = $(lan && lan.site && t('site.site_auto_str_94') || "");
        configTab.addClass("bgw").siblings().removeClass("bgw");
        configFile(website);
      } else {
        domainEdit(id, website);
      }
    }
  });
}

//取网站日志pluginLogs
function getSiteLogs(siteName) {
  var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_95') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/site/get_logs', {
    siteName: siteName
  }, function (logs) {
    layer.close(loadT);
    if (logs.status !== true) {
      logs.msg = '';
    }
    if (logs.msg == '') logs.msg = lan && lan.site && t('site.site_auto_str_96') || "";
    var h = parseInt($('.bt-w-menu').css('height')) - 35;
    var con = '<textarea wrap="off" style="white-space:pre;margin: 0px;width: 800px;height: ' + h + 'px;background-color: #333;color:#fff; padding:0 5px;" id="site_log">' + logs.msg + '</textarea>';
    $("#webedit-con").html(con);
    var ob = document.getElementById('site_log');
    ob.scrollTop = ob.scrollHeight;
  }, 'json');
}

//取网站错误日志
function getSiteErrorLogs(siteName) {
  var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_97') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/site/get_error_logs', {
    siteName: siteName
  }, function (logs) {
    layer.close(loadT);
    if (logs.status !== true) {
      logs.msg = '';
    }
    if (logs.msg == '') logs.msg = lan && lan.site && t('site.site_auto_str_98') || "";
    var h = parseInt($('.bt-w-menu').css('height')) - 35;
    var con = '<textarea wrap="off" style="white-space:pre;margin:0px;width:800px;height:' + h + 'px;background-color: #333;color:#fff; padding:0 5px;" id="error_log">' + logs.msg + '</textarea>';
    $("#webedit-con").html(con);
    var ob = document.getElementById('error_log');
    ob.scrollTop = ob.scrollHeight;
  }, 'json');
}

//防盗链
function security(id, name) {
  var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_99') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/site/get_security', {
    id: id,
    name: name
  }, function (rdata) {
    layer.close(loadT);
    var mbody = '<div>' + ('<p style="margin-bottom:8px"><span style="display: inline-block; width: 60px;">' + (lan && lan.site && t('site.site_auto_str_100') || 'URL后缀') + '</span><input class="bt-input-text" type="text" name="sec_fix" value="') + rdata.fix + '" style="margin-left: 5px;width: 425px;height: 30px;margin-right:10px;' + (rdata.status ? 'background-color: #eee;' : '') + (lan && lan.site && t('site.site_auto_str_101') || "") + (rdata.status ? 'readonly' : '') + '></p>' + ('<p style="margin-bottom:8px"><span style="display: inline-block; width: 60px;">' + (lan && lan.site && t('site.site_auto_str_102') || '许可域名') + '</span><input class="bt-input-text" type="text" name="sec_domains" value="') + rdata.domains + '" style="margin-left: 5px;width: 425px;height: 30px;margin-right:10px;' + (rdata.status ? 'background-color: #eee;' : '') + (lan && lan.site && t('site.site_auto_str_103') || "") + (rdata.status ? 'readonly' : '') + '></p>' + '<div class="label-input-group ptb10"><label style="font-weight:normal"><input type="checkbox" name="sec_status" onclick="setSecurity(\'' + name + '\',' + id + ')" ' + (rdata.status ? 'checked' : '') + ((lan && lan.site && t('site.site_auto_str_104') || '>启用防盗链') + '</label></div>') + '<div class="label-input-group ptb10"><label style="font-weight:normal"><input type="checkbox" name="sec_none_status" onclick="setSecurity(\'' + name + '\',' + id + ')" ' + (rdata.none ? 'checked' : '') + ((lan && lan.site && t('site.site_auto_str_105') || '>允许空HTTP_REFERER请求') + '</label></div>') + '<ul class="help-info-text c7 ptb10">' + ('<li>' + (lan && lan.site && t('site.site_auto_str_106') || '默认允许资源被直接访问,即不限制HTTP_REFERER为空的请求') + '</li>') + ('<li>' + (lan && lan.site && t('site.site_auto_str_107') || '多个URL后缀与域名请使用逗号(,)隔开,如: png,jpeg,zip,js') + '</li>') + ('<li>' + (lan && lan.site && t('site.site_auto_str_108') || '当触发防盗链时,将直接返回404状态') + '</li>') + '</ul>' + '</div>';
    $("#webedit-con").html(mbody);
  }, 'json');
}

//设置防盗链
function setSecurity(name, id, none) {
  setTimeout(function () {
    var data = {
      fix: $("input[name='sec_fix']").val(),
      domains: $("input[name='sec_domains']").val(),
      status: $("input[name='sec_status']").prop("checked"),
      none: $("input[name='sec_none_status']").prop("checked"),
      name: name,
      id: id
    };
    var loadT = layer.msg(t('site.the_msg'), {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.post('/site/set_security', data, function (rdata) {
      layer.close(loadT);
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
      if (rdata.status) setTimeout(function () {
        security(id, name);
      }, 1000);
    }, 'json');
  }, 100);
}

//流量限制
function limitNet(id) {
  $.post('/site/get_limit_net', 'id=' + id, function (rdata) {
    var status_selected = rdata.perserver != 0 ? 'checked' : '';
    if (rdata.perserver == 0) {
      rdata.perserver = 300;
      rdata.perip = 25;
      rdata.limit_rate = 512;
    }
    var limitList = "<option value='1' " + (rdata.perserver == 0 || rdata.perserver == 300 ? 'selected' : '') + ">" + t('site.limit_net_1') + "</option>" + "<option value='2' " + (rdata.perserver == 200 ? 'selected' : '') + ">" + t('site.limit_net_2') + "</option>" + "<option value='3' " + (rdata.perserver == 50 ? 'selected' : '') + ">" + t('site.limit_net_3') + "</option>" + "<option value='4' " + (rdata.perserver == 500 ? 'selected' : '') + ">" + t('site.limit_net_4') + "</option>" + "<option value='5'  " + (rdata.perserver == 400 ? 'selected' : '') + ">" + t('site.limit_net_5') + "</option>" + "<option value='6' " + (rdata.perserver == 60 ? 'selected' : '') + ">" + t('site.limit_net_6') + "</option>" + "<option value='7' " + (rdata.perserver == 150 ? 'selected' : '') + ">" + t('site.limit_net_7') + "</option>";
    var body = "<div class='dirBinding flow c4'>" + '<p class="label-input-group ptb10"><label style="font-weight:normal"><input type="checkbox" name="status" ' + status_selected + ' onclick="saveLimitNet(' + id + ')" style="width:15px;height:15px;margin-right:5px" />' + t('site.limit_net_8') + '</label></p>' + "<p class='line' style='padding:10px 0'><span class='span_tit mr5'>" + t('site.limit_net_9') + "：</span><select class='bt-input-text mr20' name='limit' style='width:90px'>" + limitList + "</select></p>" + "<p class='line' style='padding:10px 0'><span class='span_tit mr5'>" + t('site.limit_net_10') + "：</span><input class='bt-input-text mr20' style='width: 90px;' type='number' name='perserver' value='" + rdata.perserver + "' /></p>" + "<p class='line' style='padding:10px 0'><span class='span_tit mr5'>" + t('site.limit_net_12') + "：</span><input class='bt-input-text mr20' style='width: 90px;' type='number' name='perip' value='" + rdata.perip + "' /></p>" + "<p class='line' style='padding:10px 0'><span class='span_tit mr5'>" + t('site.limit_net_14') + "：</span><input class='bt-input-text mr20' style='width: 90px;' type='number' name='limit_rate' value='" + rdata.limit_rate + "' /></p>" + "<button class='btn btn-success btn-sm mt10' onclick='saveLimitNet(" + id + ",1)'>" + t('public.save') + "</button>" + "</div>" + "<ul class='help-info-text c7 mtb15'><li>" + t('site.limit_net_11') + "</li><li>" + t('site.limit_net_13') + "</li><li>" + t('site.limit_net_15') + "</li></ul>";
    $("#webedit-con").html(body);
    $("select[name='limit']").on('change', function () {
      var type = $(this).val();
      perserver = 300;
      perip = 25;
      limit_rate = 512;
      switch (type) {
        case '1':
          perserver = 300;
          perip = 25;
          limit_rate = 512;
          break;
        case '2':
          perserver = 200;
          perip = 10;
          limit_rate = 1024;
          break;
        case '3':
          perserver = 50;
          perip = 3;
          limit_rate = 2048;
          break;
        case '4':
          perserver = 500;
          perip = 10;
          limit_rate = 2048;
          break;
        case '5':
          perserver = 400;
          perip = 15;
          limit_rate = 1024;
          break;
        case '6':
          perserver = 60;
          perip = 10;
          limit_rate = 512;
          break;
        case '7':
          perserver = 150;
          perip = 4;
          limit_rate = 1024;
          break;
      }
      $("input[name='perserver']").val(perserver);
      $("input[name='perip']").val(perip);
      $("input[name='limit_rate']").val(limit_rate);
    });
  }, 'json');
}

//保存流量限制配置
function saveLimitNet(id, type) {
  var isChecked = $("input[name='status']").attr('checked');
  if (isChecked == undefined || type == 1) {
    var data = 'id=' + id + '&perserver=' + $("input[name='perserver']").val() + '&perip=' + $("input[name='perip']").val() + '&limit_rate=' + $("input[name='limit_rate']").val();
    var loadT = layer.msg(t('public.config'), {
      icon: 16,
      time: 10000
    });
    $.post('/site/set_limit_net', data, function (rdata) {
      layer.close(loadT);
      limitNet(id);
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
    }, 'json');
  } else {
    var loadT = layer.msg(t('public.config'), {
      icon: 16,
      time: 10000
    });
    $.post('/site/close_limit_net', {
      id: id
    }, function (rdata) {
      layer.close(loadT);
      limitNet(id);
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
    }, 'json');
  }
}

//子目录绑定
function dirBinding(id) {
  $.post('/site/get_dir_binding', {
    'id': id
  }, function (data) {
    var rdata = data['data'];
    var echoHtml = '';
    for (var i = 0; i < rdata.binding.length; i++) {
      echoHtml += "<tr><td>" + rdata.binding[i].domain + "</td><td>" + rdata.binding[i].port + "</td><td>" + rdata.binding[i].path + "</td><td class='text-right'><a class='btlink' href='javascript:setDirRewrite(" + rdata.binding[i].id + ((lan && lan.site && t('site.site_auto_str_109') || ');\'>伪静态') + '</a> | <a class=\'btlink\' href=\'javascript:delDirBind(') + rdata.binding[i].id + "," + id + ((lan && lan.site && t('site.site_auto_str_110') || ');\'>删除') + '</a></td></tr>');
    }
    var dirList = '';
    for (var n = 0; n < rdata.dirs.length; n++) {
      dirList += "<option value='" + rdata.dirs[n] + "'>" + rdata.dirs[n] + "</option>";
    }
    var body = "<div class='dirBinding c5'>" + ((lan && lan.site && t('site.site_auto_str_111') || '域名：') + '<input class=\'bt-input-text mr20\' type=\'text\' name=\'domain\' />') + ((lan && lan.site && t('site.site_auto_str_112') || '子目录：') + '<select class=\'bt-input-text mr20\' name=\'dirName\'>') + dirList + "</select>" + "<button class='btn btn-success btn-sm' onclick='addDirBinding(" + id + ((lan && lan.site && t('site.site_auto_str_113') || ')\'>添加') + '</button>') + "</div>" + "<div class='divtable mtb15' style='height:540px;overflow:auto'><table class='table table-hover' width='100%' style='margin-bottom:0'>" + ('<thead><tr><th>' + (lan && lan.site && t('site.site_auto_str_114') || '域名') + '</th><th width=\'70\'>' + (lan && lan.site && t('site.site_auto_str_114_1') || '端口') + '</th><th width=\'100\'>' + (lan && lan.site && t('site.site_auto_str_114_2') || '子目录') + '</th><th width=\'100\' class=\'text-right\'>' + (lan && lan.site && t('site.site_auto_str_114_3') || '操作') + '</th></tr></thead>') + "<tbody id='checkDomain'>" + echoHtml + "</tbody>" + "</table></div>";
    $("#webedit-con").html(body);
  }, 'json');
}

//子目录伪静态
function setDirRewrite(id) {
  $.post('/site/get_dir_bind_rewrite', 'id=' + id, function (rdata) {
    if (!rdata.status) {
      var confirmObj = layer.confirm(lan && lan.site && t('site.site_auto_str_115') || "", {
        icon: 3,
        closeBtn: 2
      }, function () {
        $.post('/site/get_dir_bind_rewrite', 'id=' + id + '&add=1', function (rdata) {
          layer.close(confirmObj);
          showRewrite(rdata);
        }, 'json');
      });
      return;
    }
    showRewrite(rdata);
  }, 'json');
}

//显示伪静态
function showRewrite(rdata) {
  var rList = '';
  for (var i = 0; i < rdata.rlist.length; i++) {
    rList += "<option value='" + rdata.rlist[i] + "'>" + rdata.rlist[i] + "</option>";
  }
  var webBakHtml = "<div class='c5 plr15'>\
				<div class='line'>\
					<select class='bt-input-text mr20' id='myRewrite' name='rewrite' style='width:30%;'>" + rList + "</select>\
					<textarea class='bt-input-text mtb15' style='height: 260px; width: 470px; line-height:18px;padding:5px;' id='rewriteBody'>" + rdata.data + ('</textarea>				</div>				<button id=\'setRewriteBtn\' class=\'btn btn-success btn-sm\'>' + (lan && lan.site && t('site.site_auto_str_116') || '保存') + '</button>				<ul class=\'help-info-text c7 ptb10\'>					<li>' + (lan && lan.site && t('site.site_auto_str_116_1') || '请选择您的应用，若设置伪静态后，网站无法正常访问，请尝试设置回default') + '</li>					<li>' + (lan && lan.site && t('site.site_auto_str_116_2') || '您可以对伪静态规则进行修改，修改完后保存即可。') + '</li>				</ul>			</div>');
  layer.open({
    type: 1,
    area: '500px',
    title: lan && lan.site && t('site.site_auto_str_117') || "",
    closeBtn: 1,
    shift: 5,
    shadeClose: true,
    content: webBakHtml,
    success: function () {
      $("#myRewrite").on('change', function () {
        var rewriteName = $(this).val();
        $.post('/files/get_body', 'path=' + rdata['rewrite_dir'] + '/' + rewriteName + '.conf', function (fileBody) {
          $("#rewriteBody").val(fileBody.data.data);
        }, 'json');
      });
      $('#setRewriteBtn').on('click', function () {
        var data = $("#rewriteBody").val();
        setRewrite(rdata.filename, encodeURIComponent(data));
      });
    }
  });
}

//添加子目录绑定
function addDirBinding(id) {
  var domain = $("input[name='domain']").val();
  var dir_name = $("select[name='dirName']").val();
  if (domain == '' || dir_name == '' || dir_name == null) {
    layer.msg(t('site.d_s_empty'), {
      icon: 2
    });
    return;
  }
  var data = 'id=' + id + '&domain=' + domain + '&dir_name=' + dir_name;
  $.post('/site/add_dir_bind', data, function (rdata) {
    dirBinding(id);
    layer.msg(rdata.msg, {
      icon: rdata.status ? 1 : 2
    });
  }, 'json');
}

//删除子目录绑定
function delDirBind(id, siteId) {
  layer.confirm(t('site.s_bin_del'), {
    icon: 3,
    closeBtn: 2
  }, function () {
    $.post('/site/del_dir_bind', 'id=' + id, function (rdata) {
      dirBinding(siteId);
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
    }, 'json');
  });
}

//301重定向
function to301(siteName, type, obj) {
  // 设置 页面展示
  if (type == 1) {
    var obj = {
      type: 1,
      keep_path: 1,
      to: 'http://',
      from: '',
      r_type: '',
      type: 'path'
    };
    var keep_path_ht = obj.keep_path == 1 ? 'checked="checked"' : '';
    var redirect_title = type == 1 ? lan && lan.site && t('site.site_auto_str_118') || "" : (lan && lan.site && t('site.site_auto_str_119') || "") + obj.redirectname + ']';
    layer.open({
      type: 1,
      area: ['650px', '270px'],
      title: redirect_title,
      closeBtn: 1,
      shift: 5,
      btn: [lan && lan.site && t('site.site_auto_str_120') || "", lan && lan.site && t('site.site_auto_str_121') || ""],
      shadeClose: false,
      content: ('<form id=\'form_redirect\' class=\'divtable pd20\'>			<div class=\'line\' style=\'overflow:hidden;height: 40px;\'>				<div style=\'display: inline-block;\'>					<span class=\'tname\' style=\'margin-left:10px;position: relative;top: -5px;\'>' + (lan && lan.site && t('site.site_auto_str_122') || '保留URI参数') + '</span>					<input class=\'btswitch btswitch-ios\' id=\'keep_path\' type=\'checkbox\' name=\'keep_path\' ') + keep_path_ht + (' />					<label class=\'btswitch-btn\' for=\'keep_path\' style=\'float:left\'></label>				</div>			</div>			<div class=\'line\' style=\'clear:both;\'><span class=\'tname\'>' + (lan && lan.site && t('site.site_auto_str_123') || '重定向类型') + '</span>				<div class=\'info-r ml0\'>					<select class=\'bt-input-text mr5\' name=\'type\' style=\'width:100px\'>						<option value=\'domain\' ') + (obj.type == 'domain' ? 'selected ="selected"' : "") + ((lan && lan.site && t('site.site_auto_str_124') || '>域名') + '</option>						<option value=\'path\'  ') + (obj.type == 'path' ? 'selected ="selected"' : "") + ((lan && lan.site && t('site.site_auto_str_125') || '>路径') + '</option>					</select>					<span class=\'mlr15\'>' + (lan && lan.site && t('site.site_auto_str_125_1') || '重定向方式') + '</span>					<select class=\'bt-input-text ml10\' name=\'r_type\' style=\'width:100px\'>						<option value=\'301\' ') + (obj.r_type == '301' ? 'selected ="selected"' : "") + " >301</option>\
						<option value='302' " + (obj.r_type == '302' ? 'selected ="selected"' : "") + ('>302</option>					</select>				</div>			</div>			<div class=\'line redirectdomain\'>				<span class=\'tname\'>' + (lan && lan.site && t('site.site_auto_str_126') || '重定向源') + '</span>				<div class=\'info-r ml0\'>					' + (lan && lan.site && t('site.site_auto_str_126_1') || '<input  name=\'from\' placeholder=\'域名或路径\' class=\'bt-input-text mr5\' type=\'text\' style=\'width:200px;float: left;margin-right:0px\' value=\'')) + obj.from + ('\'>					<span class=\'tname\' style=\'width:90px\'>' + (lan && lan.site && t('site.site_auto_str_127') || '目标URL') + '</span>					<input name=\'to\' class=\'bt-input-text mr5\' type=\'text\' style=\'width:200px\' value=\'') + obj.to + "'>\
				</div>\
			</div>\
			</form>",
      success: function (index, layero) {},
      yes: function (index, index1) {
        var keep_path = $('[name="keep_path"]').prop('checked') ? 1 : 0;
        var r_type = $('[name="r_type"]').val();
        var type = $('[name="type"]').val();
        var from = $('[name="from"]').val();
        var to = $('[name="to"]').val();
        var pdata = {
          siteName: siteName,
          type: type,
          r_type: r_type,
          from: from,
          to: to,
          keep_path: keep_path
        };
        $.post('/site/set_redirect', pdata, function (data) {
          if (data.status) {
            layer.close(index);
            to301(siteName);
          } else {
            layer.msg(data.msg, {
              icon: 2
            });
          }
        }, 'json');
      }
    });
  }
  if (type == 2) {
    $.post('/site/del_redirect', {
      siteName: siteName,
      id: obj
    }, function (res) {
      if (res.status == true) {
        layer.msg(lan && lan.site && t('site.site_auto_str_128') || "", {
          time: 1000,
          icon: 1
        });
        to301(siteName);
      } else {
        layer.msg(res.msg, {
          time: 1000,
          icon: 2
        });
      }
    }, 'json');
    return;
  }
  if (type == 3) {
    var laoding = layer.load();
    var data = {
      siteName: siteName,
      id: obj
    };
    $.post('/site/get_redirect_conf', data, function (res) {
      layer.close(laoding);
      if (res.status == true) {
        var mBody = "<div class='webEdit-box' style='padding: 20px'>\
				<textarea style='height: 320px; width: 445px; margin-left: 20px; line-height:18px' id='configRedirectBody'>" + res.data.result + ('</textarea>					<div class=\'info-r\'>						<ul class=\'help-info-text c7 ptb10\'>							<li>' + (lan && lan.site && t('site.site_auto_str_129') || '此处为重定向配置文件,若您不了解配置规则,请勿随意修改.') + '</li>						</ul>					</div>				</div>');
        var editor;
        var index = layer.open({
          type: 1,
          title: lan && lan.site && t('site.site_auto_str_130') || "",
          closeBtn: 1,
          shadeClose: true,
          area: ['500px', '500px'],
          btn: [lan && lan.site && t('site.site_auto_str_131') || "", lan && lan.site && t('site.site_auto_str_132') || ""],
          content: mBody,
          success: function () {
            editor = CodeMirror.fromTextArea(document.getElementById("configRedirectBody"), {
              extraKeys: {
                "Ctrl-Space": "autocomplete",
                "Ctrl-/": function (cm) {
                  cm.toggleComment({
                    lineComment: "#"
                  });
                },
                "Ctrl-F": "findPersistent",
                "Ctrl-H": "replace"
              },
              lineNumbers: true,
              matchBrackets: true,
              mode: "text/x-nginx-conf"
            });
            editor.focus();
            $(".CodeMirror-scroll").css({
              "height": "300px",
              "margin": 0,
              "padding": 0
            });
            $("#onlineEditFileBtn").off('click');
          },
          yes: function (index, layero) {
            $("#configRedirectBody").empty().text(editor.getValue());
            var load = layer.load();
            var data = {
              siteName: siteName,
              id: obj,
              config: editor.getValue()
            };
            $.post('/site/save_redirect_conf', data, function (res) {
              layer.close(load);
              if (res.status == true) {
                layer.msg(lan && lan.site && t('site.site_auto_str_133') || "", {
                  icon: 1
                });
                layer.close(index);
              } else {
                layer.msg(res.msg, {
                  time: 3000,
                  icon: 2
                });
              }
            }, 'json');
            return true;
          }
        });
      } else {
        layer.msg(lan && lan.site && t('site.site_auto_str_134') || "", {
          time: 3000,
          icon: 2
        });
      }
    });
    return;
  }
  var body = ('<div id="redirect_list" class="bt_table">		<div style="padding-bottom: 10px">			' + (lan && lan.site && t('site.site_auto_str_135') || '<button type="button" title="添加重定向" class="btn btn-success btn-sm mr5" onclick="to301(\'')) + siteName + ('\',1)" >			<span>' + (lan && lan.site && t('site.site_auto_str_136') || '添加重定向') + '</span>		</button>		</div>		<div class="divtable" style="max-height:500px;">			<table class="table table-hover" >				<thead style="position: relative;z-index: 1;">					<tr>						<th><span data-index="1"><span>' + (lan && lan.site && t('site.site_auto_str_136_1') || '重定向类型') + '</span></span></th>						<th><span data-index="2"><span>' + (lan && lan.site && t('site.site_auto_str_136_2') || '重定向方式') + '</span></span></th>						<th><span data-index="3"><span>' + (lan && lan.site && t('site.site_auto_str_136_3') || '保留URL参数') + '</span></span></th>						<th><span data-index="4"><span>' + (lan && lan.site && t('site.site_auto_str_136_4') || '状态') + '</span></span></th>						<th><span data-index="5"><span>' + (lan && lan.site && t('site.site_auto_str_136_5') || '操作') + '</span></span></th>					</tr>				</thead>				<tbody id="md-301-body">				</tbody>			</table>		</div>	</div>');
  $("#webedit-con").html(body);
  var loadT = layer.msg(t('site.the_msg'), {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/site/get_redirect', 'siteName=' + siteName, function (res) {
    layer.close(loadT);
    $("#md-301-loading").remove();
    if (res.status) {
      var data = res.data.result;
      data.forEach(function (item) {
        var lan_r_type = item.r_type == 0 ? lan && lan.site && t('site.site_auto_str_137') || "" : lan && lan.site && t('site.site_auto_str_138') || "";
        var keep_path = item.keep_path == 0 ? lan && lan.site && t('site.site_auto_str_139') || "" : lan && lan.site && t('site.site_auto_str_140') || "";
        var switchProxy = '<span onclick="toRedirect(\'' + siteName + '\',\'' + item.id + '\',10)" style="color:rgb(92, 184, 92);" class="btlink glyphicon glyphicon-play"></span>';
        if (!item['status']) {
          switchProxy = '<span onclick="toRedirect(\'' + siteName + '\',\'' + item.id + '\',11)" style="color:rgb(255, 0, 0);" class="btlink glyphicon glyphicon-pause"></span>';
        }
        let tmp = '<tr>\
					<td><span data-index="1"><span>' + item.r_from + '</span></span></td>\
					<td><span data-index="2"><span>' + lan_r_type + '</span></span></td>\
					<td><span data-index="3"><span>' + keep_path + '</span></span></td>\
					<td><span data-index="4"><span>' + switchProxy + '</span></span></td>\
					<td>\
						<span data-index="5" onclick="to301(\'' + siteName + '\', 3, \'' + item.id + ((lan && lan.site && t('site.site_auto_str_141') || '\')"  class="btlink">详细') + '</span> | 						<span data-index="5" onclick="to301(\'') + siteName + '\', 2, \'' + item.id + ((lan && lan.site && t('site.site_auto_str_142') || '\')" class="btlink">删除') + '</span>					</td>				</tr>');
        $("#md-301-body").append(tmp);
      });
    } else {
      layer.msg(res.msg, {
        icon: 2
      });
    }
  }, 'json');
}
function toRedirect(siteName, redirect_id, type) {
  if (type == 10 || type == 11) {
    //[11]启动 或 停止[10]
    var status = type == 10 ? '0' : '1';
    var loading = layer.msg(t('site.the_msg'), {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    var pdata = {
      siteName: siteName,
      'status': status,
      'id': redirect_id
    };
    $.post('/site/set_redirect_status', pdata, function (rdata) {
      layer.close(loading);
      if (!rdata.status) {
        layer.msg(res.msg, {
          time: 3000,
          icon: 2
        });
        return;
      }
      showMsg(lan && lan.site && t('site.site_auto_str_143') || "", function () {
        to301(siteName);
      }, {
        icon: 1,
        time: 2000
      });
    }, 'json');
    return;
  }
}

//反向代理
function toProxy(siteName, type, obj) {
  // 设置 页面展示
  if (type == 1) {
    var proxy_title = lan && lan.site && t('site.site_auto_str_144') || "";
    if (typeof obj != 'undefined') {
      proxy_title = lan && lan.site && t('site.site_auto_str_145') || "";
    }
    layer.open({
      type: 1,
      area: '650px',
      title: proxy_title,
      closeBtn: 1,
      shift: 5,
      shadeClose: false,
      btn: [lan && lan.site && t('site.site_auto_str_146') || "", lan && lan.site && t('site.site_auto_str_147') || ""],
      content: '<form id=\'form_proxy\' class=\'divtable pd15\' style=\'padding-bottom: 10px\'>				<div class=\'line\'>					<span class=\'tname\' style=\'line-height:20px;\'>' + (lan && lan.site && t('site.site_auto_str_148') || '开启代理') + '</span>					<div class=\'info-r ml0 mt5\'>						<input name=\'open_proxy\' class=\'btswitch btswitch-ios\' type=\'checkbox\' checked>						<label id=\'open_proxy\' class=\'btswitch-btn\' for=\'openProxy\' style=\'float:left\'></label>						<div style=\'display: inline-block\'>							<span class=\'tname\' style=\'position: relative;top: -5px;\'>' + (lan && lan.site && t('site.site_auto_str_148_1') || '是否缓存') + '</span>							<input class=\'btswitch btswitch-ios\' type=\'checkbox\' name=\'open_cache\'>							<label class=\'btswitch-btn\' id=\'open_cache\' for=\'openCache\' style=\'float:left\'></label>						</div>						<div style=\'display: inline-block\'>							<span class=\'tname\' style=\'position: relative;top: -5px;\'>' + (lan && lan.site && t('site.site_auto_str_148_2') || '是否跨域') + '</span>							<input class=\'btswitch btswitch-ios\' type=\'checkbox\' name=\'open_cors\'>							<label class=\'btswitch-btn\' id=\'open_cors\' for=\'open_cors\' style=\'float:left\'></label>						</div>						<div style=\'display: inline-block\'>							<span class=\'tname\' style=\'position: relative;top: -5px;\'>' + (lan && lan.site && t('site.site_auto_str_148_3') || '是否H3') + '</span>							<input class=\'btswitch btswitch-ios\' type=\'checkbox\' name=\'open_http3\'>							<label class=\'btswitch-btn\' id=\'open_http3\' for=\'open_http3\' style=\'float:left\'></label>						</div>					</div>				</div>				<div class=\'line\'>					<span class=\'tname\'>' + (lan && lan.site && t('site.site_auto_str_148_4') || '名称') + '</span>					<div class=\'info-r ml0\'>					<input name=\'name\' value=\'index\' placeholder=\'请输入名称\' class=\'bt-input-text mr5\' type=\'text\' style=\'width:200px\'\'>					</div>				</div>				<div class=\'line\' style=\'display:none\' id=\'cache_time\'>					<span class=\'tname\'>' + (lan && lan.site && t('site.site_auto_str_148_5') || '缓存时间') + '</span>					<div class=\'info-r ml0\'>					<input name=\'cache_time\' value=\'1\' class=\'bt-input-text mr5\' type=\'number\' style=\'width:200px\'\'>' + (lan && lan.site && t('site.site_auto_str_148_6') || '分钟') + '					</div>				</div>				<div class=\'line\'>					<span class=\'tname\'>' + (lan && lan.site && t('site.site_auto_str_148_7') || '代理目录') + '</span>					<div class=\'info-r ml0\'>					<input name=\'from\' value=\'/\' placeholder=\'/\' class=\'bt-input-text mr5\' type=\'text\' style=\'width:200px\'\'>					</div>				</div>				<div class=\'line\'>					<span class=\'tname\'>' + (lan && lan.site && t('site.site_auto_str_148_8') || '目标URL') + '</span>					<div class=\'info-r ml0\'>					<input name=\'proxy_url\' class=\'bt-input-text mr5\' type=\'text\' value=\'http://127.0.0.1\' style=\'width:150px;float: left;margin-right:5px\'>					<span style=\'float: left; margin-right: 5px; line-height: 30px; font-weight: bold;\'>:</span>					<input name=\'proxy_port\' class=\'bt-input-text mr5\' type=\'number\' placeholder=\'端口\' style=\'width:65px;float: left;margin-right:15px\'>					<input name=\'to\' type=\'hidden\' value=\'http://127.0.0.1\'>					<span class=\'tname\' style=\'width:90px\'>' + (lan && lan.site && t('site.site_auto_str_148_9') || '发送域名') + '</span>					<input name=\'host\' value=\'$host\' class=\'bt-input-text mr5\' type=\'text\' style=\'width:100px\'>					</div>				</div>				<input name=\'id\' value=\'\' type=\'hidden\'>				<div class=\'help-info-text c7\'>					<ul class=\'help-info-text c7\'>					<li>' + (lan && lan.site && t('site.site_auto_str_148_10') || '代理目录：访问这个目录时将会把目标URL的内容返回并显示') + '</li>					<li>' + (lan && lan.site && t('site.site_auto_str_148_11') || '目标URL：可以填写你需要代理的站点，目标URL必须为可正常访问的URL，否则将返回错误') + '</li>					<li>' + (lan && lan.site && t('site.site_auto_str_148_12') || '发送域名：将域名添加到请求头传递到代理服务器，默认为目标URL域名，若设置不当可能导致代理无法正常运行') + '</li>					</ul>				</div>				</form>',
      success: function () {
        if (typeof obj != 'undefined') {
          console.log(obj);
          $('input[name="name"]').val(obj['name']).attr('readonly', 'readonly').addClass('disabled');
          if (obj['open_cache'] == 'on') {
            $("input[name='open_cache']").prop("checked", true);
            $('#cache_time').show();
          }
          if (obj['open_cors'] == 'on') {
            $("input[name='open_cors']").prop("checked", true);
          }
          if (obj['open_http3'] == 'on') {
            $("input[name='open_http3']").prop("checked", true);
          }
          if (obj['open_proxy'] == 'on') {
            $("input[name='open_proxy']").prop("checked", true);
          }
          $('input[name="from"]').val(obj['from']);
          $('input[name="to"]').val(obj['to']);
          var url = obj['to'];
          var ip_reg = /^(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\.(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\.(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\.(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])$/;
          url = url.replace(/^http[s]?:\/\//, '');
          url = url.replace(/(:|\?|\/|\\)(.*)$/, '');
          if (ip_reg.test(url)) {
            $("[name='host']").val('$host');
          } else {
            $("[name='host']").val(url);
          }
          $('input[name="id"]').val(obj['id']);
          $('input[name="cache_time"]').val(obj['cache_time']);
          if (obj['to']) {
            var proxyUrl = obj['to'];
            var proxyPort = '';
            var portMatch = obj['to'].match(/:(\d+)(\/.*)?$/);
            if (portMatch) {
              proxyPort = portMatch[1];
              proxyUrl = obj['to'].replace(':' + portMatch[1], '');
            }
            $('input[name="proxy_url"]').val(proxyUrl);
            $('input[name="proxy_port"]').val(proxyPort);
          }
        }
        function updateTargetUrl() {
          var url = $('input[name="proxy_url"]').val();
          var port = $('input[name="proxy_port"]').val();
          var finalUrl = url;
          if (port) {
            if (url.indexOf('://') == -1) {
              url = 'http://' + url;
              $('input[name="proxy_url"]').val(url);
            }
            finalUrl = url + ':' + port;
          }
          $('input[name="to"]').val(finalUrl);
          var hostUrl = finalUrl;
          var ip_reg = /^(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\.(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\.(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\.(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])$/;
          hostUrl = hostUrl.replace(/^http[s]?:\/\//, '');
          hostUrl = hostUrl.replace(/(:|\?|\/|\\)(.*)$/, '');
          if (ip_reg.test(hostUrl)) {
            $("[name='host']").val('$host');
          } else {
            $("[name='host']").val(hostUrl);
          }
        }
        $('input[name="proxy_url"], input[name="proxy_port"]').on('input keyup', function () {
          updateTargetUrl();
        });
        $("#open_proxy").on('click', function () {
          var status = $("input[name='open_proxy']").prop("checked") == true ? 1 : 0;
          if (status == 1) {
            $("input[name='open_proxy']").prop("checked", false);
          } else {
            $("input[name='open_proxy']").prop("checked", true);
          }
        });
        $('#open_cache').on('click', function () {
          var status = $("input[name='open_cache']").prop("checked") == true ? 1 : 0;
          if (status == 1) {
            $('#cache_time').hide();
            $("input[name='open_cache']").prop("checked", false);
          } else {
            $('#cache_time').show();
            $("input[name='open_cache']").prop("checked", true);
          }
        });
        $('#open_cors').on('click', function () {
          var status = $("input[name='open_cors']").prop("checked") == true ? 1 : 0;
          if (status == 1) {
            $("input[name='open_cors']").prop("checked", false);
          } else {
            $("input[name='open_cors']").prop("checked", true);
          }
        });
        $('#open_http3').on('click', function () {
          var status = $("input[name='open_http3']").prop("checked") == true ? 1 : 0;
          if (status == 1) {
            $("input[name='open_http3']").prop("checked", false);
          } else {
            $("input[name='open_http3']").prop("checked", true);
          }
        });
      },
      yes: function (index, layer_ro) {
        var data = $('#form_proxy').serializeArray();
        var t = {};
        t['name'] = 'siteName';
        t['value'] = siteName;
        data.push(t);

        // console.log(data);
        var loading = layer.msg((lan && lan.site && t('site.site_auto_str_149') || "") + proxy_title + '...', {
          icon: 16,
          time: 0,
          shade: [0.3, '#000']
        });
        $.post('/site/set_proxy', data, function (res) {
          layer.close(loading);
          if (!res.status) {
            layer.msg(res.msg, {
              icon: 2,
              time: 10000
            });
            return;
          }
          showMsg(proxy_title + (lan && lan.site && t('site.site_auto_str_150') || ""), function () {
            layer.close(index);
            toProxy(siteName);
          }, {
            icon: 1,
            time: 2000
          });
        }, 'json');
      }
    });
  }
  if (type == 2) {
    var loading = layer.msg(lan && lan.site && t('site.site_auto_str_151') || "", {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.post('/site/del_proxy', {
      siteName: siteName,
      id: obj
    }, function (res) {
      layer.close(loading);
      if (res.status == true) {
        showMsg(lan && lan.site && t('site.site_auto_str_152') || "", function () {
          toProxy(siteName);
        }, {
          time: 1000,
          icon: 1
        });
      } else {
        layer.msg(res.msg, {
          time: 1000,
          icon: 2
        });
      }
    }, 'json');
    return;
  }
  if (type == 3) {
    var laoding = layer.load();
    var data = {
      siteName: siteName,
      id: obj
    };
    $.post('/site/get_proxy_conf', data, function (res) {
      layer.close(laoding);
      if (!res.status) {
        layer.msg(lan && lan.site && t('site.site_auto_str_153') || "", {
          time: 3000,
          icon: 2
        });
        return;
      }
      var mBody = "<div class='webEdit-box' style='padding: 20px'>\
			<textarea style='height: 320px; width: 445px; margin-left: 20px; line-height:18px' id='configProxyBody'>" + res.data.result + ('</textarea>				<div class=\'info-r\'>					<ul class=\'help-info-text c7 ptb10\'>						<li>' + (lan && lan.site && t('site.site_auto_str_154') || '此处为反向代理配置文件,若您不了解配置规则,请勿随意修改.') + '</li>					</ul>				</div>			</div>');
      var editor;
      function saveDataFunc() {
        $("#configProxyBody").empty().text(editor.getValue());
        var load = layer.load();
        var data = {
          siteName: siteName,
          id: obj,
          config: editor.getValue()
        };
        $.post('/site/save_proxy_conf', data, function (res) {
          layer.close(load);
          if (res.status == true) {
            layer.msg(lan && lan.site && t('site.site_auto_str_155') || "", {
              icon: 1
            });
            layer.close(index);
          } else {
            layer.msg(res.msg, {
              time: 3000,
              icon: 2
            });
          }
        }, 'json');
      }
      var index = layer.open({
        type: 1,
        title: lan && lan.site && t('site.site_auto_str_156') || "",
        closeBtn: 1,
        shadeClose: true,
        area: ['700px', '700px'],
        btn: [lan && lan.site && t('site.site_auto_str_157') || "", lan && lan.site && t('site.site_auto_str_158') || ""],
        content: mBody,
        success: function () {
          editor = CodeMirror.fromTextArea(document.getElementById("configProxyBody"), {
            lineNumbers: true,
            matchBrackets: true,
            mode: "text/x-nginx-conf",
            extraKeys: {
              "Ctrl-Space": "autocomplete",
              "Ctrl-F": "findPersistent",
              "Ctrl-H": "replace",
              "Ctrl-/": function (cm) {
                cm.toggleComment({
                  lineComment: "#"
                });
              },
              "Ctrl-S": function () {
                saveDataFunc();
              },
              "Cmd-S": function () {
                saveDataFunc();
              }
            }
          });
          editor.focus();
          $(".CodeMirror-scroll").css({
            "height": "500px",
            "margin": 0,
            "padding": 0
          });
          $("#onlineEditFileBtn").off('click');
        },
        yes: function (index, layero) {
          saveDataFunc();
          return true;
        }
      });
    }, 'json');
    return;
  }
  if (type == 10 || type == 11) {
    //[11]启动 或 停止[10]
    status = type == 10 ? '0' : '1';
    var loading = layer.msg(t('site.the_msg'), {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.post('/site/set_proxy_status', {
      siteName: siteName,
      'status': status,
      'id': obj
    }, function (rdata) {
      layer.close(loading);
      if (!rdata.status) {
        layer.msg(rdata.msg, {
          time: 3000,
          icon: 2
        });
        return;
      }
      showMsg(lan && lan.site && t('site.site_auto_str_159') || "", function () {
        toProxy(siteName);
      }, {
        icon: 1,
        time: 2000
      });
    }, 'json');
    return;
  }
  if (type == 20 || type == 21) {
    //[20] 开始缓存 或 [21] 停止缓存
    var status = type == 20 ? 'on' : '';
    obj['open_cache'] = status;
    obj['siteName'] = siteName;
    var loading = layer.msg(lan && lan.site && t('site.site_auto_str_160') || "", {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.post('/site/set_proxy', obj, function (rdata) {
      layer.close(loading);
      if (!rdata.status) {
        layer.msg(rdata.msg, {
          icon: 2,
          time: 2000
        });
        return;
      }
      showMsg(lan && lan.site && t('site.site_auto_str_161') || "", function () {
        toProxy(siteName);
      }, {
        icon: 1,
        time: 2000
      });
    }, 'json');
    return;
  }
  var body = ('<div id="proxy_list" class="bt_table">		<div style="padding-bottom: 10px">			' + (lan && lan.site && t('site.site_auto_str_162') || '<button type="button" title="添加反向代理" class="btn btn-success btn-sm mr5" onclick="toProxy(\'')) + siteName + ('\',1)" >				<span>' + (lan && lan.site && t('site.site_auto_str_163') || '添加反向代理') + '</span>			</button>		</div>		<div class="divtable" style="max-height:500px;">			<table class="table table-hover" >				<thead style="position: relative;z-index: 1;">					<tr>						<th>' + (lan && lan.site && t('site.site_auto_str_163_1') || '名称') + '</th>						<th>' + (lan && lan.site && t('site.site_auto_str_163_2') || '代理目录') + '</th>						<th>' + (lan && lan.site && t('site.site_auto_str_163_3') || '目标地址') + '</th>						<th>' + (lan && lan.site && t('site.site_auto_str_163_4') || '缓存') + '</th>						<th>' + (lan && lan.site && t('site.site_auto_str_163_5') || '状态') + '</th>						<th>' + (lan && lan.site && t('site.site_auto_str_163_6') || '操作') + '</th>					</tr>				</thead>				<tbody id="md-301-body"></tbody>			</table>		</div>	</div>');
  $("#webedit-con").html(body);
  var loading = layer.msg(t('site.the_msg'), {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post("/site/get_proxy_list", {
    siteName: siteName
  }, function (res) {
    layer.close(loading);
    if (!res.status) {
      layer.msg(res.msg, {
        icon: 2
      });
      return;
    }
    var data = res.data.result;
    for (var i = 0; i < data.length; i++) {
      var item = data[i];
      var switchProxy = '<span onclick="toProxy(\'' + siteName + '\', 10, \'' + item.id + '\')" style="color:rgb(92, 184, 92);" class="btlink glyphicon glyphicon-play"></span>';
      if (!item['status']) {
        switchProxy = '<span onclick="toProxy(\'' + siteName + '\', 11, \'' + item.id + '\')" style="color:rgb(255, 0, 0);" class="btlink glyphicon glyphicon-pause"></span>';
      }
      var openCache = '<span  data-index="' + i + ((lan && lan.site && t('site.site_auto_str_164') || '" class="btlink cache off">未开启') + '</span>');
      if (item['open_cache'] == 'on') {
        openCache = '<span  data-index="' + i + ((lan && lan.site && t('site.site_auto_str_165') || '" class="btlink cache on">已开启') + '</span>');
      }
      let tmp = '<tr>\
				<td>' + item.name + '</td>\
				<td>' + item.from + '</td>\
				<td>' + item.to + '</td>\
				<td>' + openCache + '</td>\
				<td>' + switchProxy + '</td>\
				<td>\
				   <span data-index="' + i + ((lan && lan.site && t('site.site_auto_str_166') || '" class="btlink detail">详细') + '</span> |				   <span data-index="') + i + ((lan && lan.site && t('site.site_auto_str_167') || '" class="btlink edit">编辑') + '</span> |				   <span data-index="') + i + ((lan && lan.site && t('site.site_auto_str_168') || '" class="btlink delete">删除') + '</span>				</td>			</tr>');
      $("#md-301-body").append(tmp);
    }
    $('#md-301-body .detail').on('click', function () {
      var index = $(this).data('index');
      toProxy(siteName, 3, data[index]['id']);
    });
    $('#md-301-body .edit').on('click', function () {
      var index = $(this).data('index');
      toProxy(siteName, 1, data[index]);
    });
    $('#md-301-body .delete').on('click', function () {
      var index = $(this).data('index');
      toProxy(siteName, 2, data[index]['id']);
    });
    $('#md-301-body .cache').on('click', function () {
      var index = $(this).data('index');
      if ($(this).hasClass('on')) {
        toProxy(siteName, 21, data[index]);
      } else {
        toProxy(siteName, 20, data[index]);
      }
    });
  }, 'json');
  /////////
}

//证书夹
function sslAdmin(siteName) {
  var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_169') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.get('/site/get_cert_list', function (data) {
    layer.close(loadT);
    var rdata = data['data'];
    var tbody = '';
    for (var i = 0; i < rdata.length; i++) {
      tbody += '<tr>\
				<td>' + rdata[i].subject + '</td>\
				<td>' + rdata[i].dns.join('<br>') + '</td>\
				<td>' + rdata[i].notAfter + '</td>\
				<td>' + rdata[i].issuer.split(' ')[0] + '</td>\
				<td style="text-align: right;"><a onclick="setCertSsl(\'' + rdata[i].subject + '\',\'' + siteName + ((lan && lan.site && t('site.site_auto_str_170') || '\')" class="btlink">部署') + '</a> | <a onclick="removeSsl(\'') + rdata[i].subject + ((lan && lan.site && t('site.site_auto_str_171') || '\')" class="btlink">删除') + '</a></td>			</tr>');
    }
    var txt = ('<div class="mtb15" style="line-height:30px">		<button style="margin-bottom: 7px;display:none;" class="btn btn-success btn-sm">' + (lan && lan.site && t('site.site_auto_str_172') || '添加') + '</button>		<div class="divtable"><table class="table table-hover"><thead><tr><th>' + (lan && lan.site && t('site.site_auto_str_172_1') || '域名') + '</th><th>' + (lan && lan.site && t('site.site_auto_str_172_2') || '信任名称') + '</th><th>' + (lan && lan.site && t('site.site_auto_str_172_3') || '到期时间') + '</th><th>' + (lan && lan.site && t('site.site_auto_str_172_4') || '品牌') + '</th><th class="text-right" width="75">' + (lan && lan.site && t('site.site_auto_str_172_5') || '操作') + '</th></tr></thead>		<tbody>') + tbody + '</tbody>\
		</table></div></div>';
    $(".tab-con").html(txt);
  }, 'json');
}

//删除证书
function removeSsl(certName) {
  safeMessage(lan && lan.site && t('site.site_auto_str_173') || "", lan && lan.site && t('site.site_auto_str_174') || "", function () {
    var loadT = layer.msg(t('site.the_msg'), {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.post('/site/remove_cert', {
      certName: certName
    }, function (rdata) {
      layer.close(loadT);
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
      $("#ssl_admin").click();
    }, 'json');
  });
}

//从证书夹部署
function setCertSsl(certName, siteName) {
  var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_175') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/site/set_cert_to_site', {
    certName: certName,
    siteName: siteName
  }, function (rdata) {
    layer.close(loadT);
    showMsg(rdata.msg, function () {
      $(".tab-nav span:first-child").click();
    }, {
      icon: rdata.status ? 1 : 2
    }, 2000);
  }, 'json');
}

//ssl
function setSSL(id, siteName) {
  // <span onclick="opSSL(\'lets\','+id+',\''+siteName+'\')">Let\'s Encrypt</span>
  // 暂时关闭 Let 申请模式
  var sslHtml = ('<div class="warning_info mb10" style="display:none;">					<p>' + (lan && lan.site && t('site.site_auto_str_176') || '温馨提示：当前站点未开启SSL证书访问，站点访问可能存在风险。') + '<button class="btn btn-success btn-xs ml10 cutTabView">' + (lan && lan.site && t('site.site_auto_str_176_1') || '申请证书') + '</button></p>				</div>				<div class="tab-nav" style="margin-top: 10px;">					<span class="on" id="now_ssl" onclick="opSSL(\'now\',') + id + ',\'' + siteName + ((lan && lan.site && t('site.site_auto_str_177') || '\')">当前证书 -') + ' <i class="error">' + (lan && lan.site && t('site.site_auto_str_177_1') || '[未部署SSL]') + '</i></span>										<span onclick="opSSL(\'acme\',') + id + ',\'' + siteName + '\')">ACME</span>\
					<span id="ssl_admin" onclick="sslAdmin(\'' + siteName + ((lan && lan.site && t('site.site_auto_str_178') || '\')">证书夹') + '</span>') + '<div class="ss-text pull-right mr30" style="position: relative;top:-4px">\
	                </div></div>' + '<div class="tab-con" style="padding: 0px;"></div>';
  $("#webedit-con").html(sslHtml);
  $(".tab-nav span").on('click', function () {
    $(this).addClass("on").siblings().removeClass("on");
  });
  $('.cutTabView').on('click', function () {
    $('.tab-nav span').eq(1).click();
  });
  opSSL('now', id, siteName);
}

//设置httpToHttps
function httpToHttps(siteName) {
  var isHttps = $("#toHttps").prop('checked');
  if (isHttps) {
    layer.confirm(lan && lan.site && t('site.site_auto_str_179') || "", {
      icon: 3,
      title: lan && lan.site && t('site.site_auto_str_180') || ""
    }, function () {
      $.post('/site/close_to_https', 'siteName=' + siteName, function (rdata) {
        layer.msg(rdata.msg, {
          icon: rdata.status ? 1 : 2
        });
      }, 'json');
    });
  } else {
    $.post('/site/http_to_https', 'siteName=' + siteName, function (rdata) {
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
    }, 'json');
  }
}
function deleteSSL(type, id, siteName) {
  $.post('/site/delete_ssl', 'site_name=' + siteName + '&ssl_type=' + type, function (rdata) {
    showMsg(rdata.msg, function () {
      opSSL(type, id, siteName);
    }, {
      icon: rdata.status ? 1 : 2
    }, 2000);
  }, 'json');
}
function deploySSL(type, id, siteName) {
  $.post('/site/deploy_ssl', 'site_name=' + siteName + '&ssl_type=' + type, function (rdata) {
    showMsg(rdata.msg, function () {
      if (rdata.status) {
        $('#now_ssl').click();
      } else {
        opSSL(type, id, siteName);
      }
    }, {
      icon: rdata.status ? 1 : 2
    }, 2000);
  }, 'json');
}
function renewSSL(type, id, siteName) {
  showSpeedWindow(lan && lan.site && t('site.site_auto_str_181') || "", 'site.get_acme_logs', function (layers, index) {
    $.post('/site/renew_ssl', 'site_name=' + siteName + '&ssl_type=' + type, function (rdata) {
      showMsg(rdata.msg, function () {
        if (rdata.status) {
          layer.close(index);
          if (rdata.data !== undefined && rdata.data !== -1) {
            var ssl_days = rdata.data;
            var a_tag = $("#ssl_state_" + siteName.replace(/\./g, '_')).find('a');
            if (a_tag.length > 0) {
              a_tag.text((lan && lan.site && t('site.site_auto_str_182') || "") + ssl_days + (lan && lan.site && t('site.site_auto_str_183') || ""));
              if (ssl_days < 10) {
                a_tag.css('color', 'red');
              } else {
                a_tag.css('color', '#20a53a');
              }
            }
          }
          opSSL(type, id, siteName);
        }
      }, {
        icon: rdata.status ? 1 : 2
      }, 2000);
    }, 'json');
  });
}
function renderDnsapiHtml(data) {
  var fields = data.data;
  var fields_html = '';
  for (var d in fields) {
    fields_html += "<span class='tname tips' data-toggle='tooltip' data-original-title='" + d + "'>" + d + "</span>\
	    <div class='info-r'>\
	        <input name='" + d + "' class='bt-input-text mr5' style='width:100%;' value='" + fields[d] + "' type='text'>\
	    </div>";
  }
  layer.open({
    type: 1,
    area: '500px',
    title: (lan && lan.site && t('site.site_auto_str_184') || "") + data['title'] + (lan && lan.site && t('site.site_auto_str_185') || ""),
    closeBtn: 1,
    shift: 5,
    shadeClose: true,
    btn: [lan && lan.site && t('site.site_auto_str_186') || "", lan && lan.site && t('site.site_auto_str_187') || ""],
    content: ('<form class=\'bt-form pd15\'>			<div class=\'line\'>			    <span class=\'tname\'>' + (lan && lan.site && t('site.site_auto_str_188') || 'DNSAPI类型') + '</span>			    <div class=\'info-r\'>			        <select class=\'bt-input-text mr5\' name=\'type_name\' style=\'width:100%;\'>			            <option name=\'cf\'>') + data['name'] + "</option>\
			        </select>\
			    </div>\
			</div>\
			<div class='line' id='dnsapi_option'>\
			    " + fields_html + ('			</div>			<div class=\'line\'>				<div>					<ul class=\'help-info-text c7\' style=\'margin-top:0px;\'>						<li>' + (lan && lan.site && t('site.site_auto_str_189') || '使用【')) + data['title'] + ((lan && lan.site && t('site.site_auto_str_190') || '】的API接口自动解析申请SSL') + '</li>					</ul>				</div>			</div>		</form>'),
    success: function () {
      $('[data-toggle="tooltip"]').tooltip();
    },
    yes: function (index, l) {
      var type_name = $('select[name="type_name"]').val();
      var data_field = {};
      for (var d in fields) {
        data_field[d] = $('input[name="' + d + '"]').val();
      }
      $.post('/site/set_dnsapi', {
        'type': type_name,
        'data': JSON.stringify(data_field)
      }, function (rdata) {
        showMsg(rdata.msg, function () {
          if (rdata.status) {
            layer.close(index);
            renderDnsapi();
          }
        }, {
          icon: rdata.status ? 1 : 2
        });
      }, 'json');
    }
  });
}
function renderDnsapi() {
  $('#dnsapi_set').css('display', 'none');
  $.post('/site/get_dnsapi', {}, function (data) {
    var dnsapi_option = '';
    for (var i = 0; i < data.length; i++) {
      dnsapi_option += '<option value="' + data[i]['name'] + '" index="' + i + '">' + data[i]['title'] + '</option>';
    }
    $('#dnsapi_option select').html(dnsapi_option);
    $('#dnsapi_option select').on('change', function () {
      var val = $(this).val();
      var index = $('#dnsapi_option option:selected').attr('index');
      if (val == 'none') {
        $('#dnsapi_option button').css('display', 'none');
      } else {
        $('#dnsapi_option button').css('display', 'inline-block');
        if (!(data[index]['title'].indexOf('[') > 0)) {
          renderDnsapiHtml(data[index]);
        }
      }
    });
    $('#dnsapi_set').off('click').on('click', function () {
      var index = $('#dnsapi_option option:selected').attr('index');
      renderDnsapiHtml(data[index]);
    });
  }, 'json');
}
function opSSLNow(type, id, siteName, callback) {
  var now = ('<div class="myKeyCon ptb15">			<div class="ssl_state_info" style="display:none;"></div>		<div class="custom_certificate_info">			<div class="ssl-con-key pull-left mr20">' + (lan && lan.site && t('site.site_auto_str_191') || '密钥(KEY)') + '<br><textarea id="key" class="bt-input-text"></textarea></div>			<div class="ssl-con-key pull-left">' + (lan && lan.site && t('site.site_auto_str_191_1') || '证书(PEM格式)') + '<br><textarea id="csr" class="bt-input-text"></textarea></div>		</div>		<div class="ssl-btn pull-left mtb15" style="width:100%">			<button class="btn btn-success btn-sm" onclick="saveSSL(\'') + siteName + ((lan && lan.site && t('site.site_auto_str_192') || '\')">保存') + '</button>		</div>	</div>	<ul class="help-info-text c7 pull-left">		<li>' + (lan && lan.site && t('site.site_auto_str_192_1') || '粘贴您的*.key以及*.pem内容，然后保存即可。') + '</li>		<li>' + (lan && lan.site && t('site.site_auto_str_192_2') || '如果浏览器提示证书链不完整,请检查是否正确拼接PEM证书') + '</li><li>' + (lan && lan.site && t('site.site_auto_str_192_3') || 'PEM格式证书 = 域名证书.crt + 根证书(root_bundle).crt') + '</li>		<li>' + (lan && lan.site && t('site.site_auto_str_192_4') || '在未指定SSL默认站点时,未开启SSL的站点使用HTTPS会直接访问到已开启SSL的站点') + '</li>	</ul>');
  $(".tab-con").html(now);
  var key = '';
  var csr = '';
  var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_193') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/site/get_ssl', 'site_name=' + siteName, function (data) {
    layer.close(loadT);
    var rdata = data['data'];
    if (rdata['cert_data']) {
      var issuer_o = rdata['cert_data']['issuer_o'] || '<div class=\'state_info_flex\'>				<div class=\'state_item\'><span>' + (lan && lan.site && t('site.site_auto_str_194') || '证书分类：') + '</span><span class=\'ellipsis_text\'>';
      var issuer = rdata['cert_data']['issuer'] || '</span></div>				<div class=\'state_item\'><span>' + (lan && lan.site && t('site.site_auto_str_195') || '证书品牌：') + '</span><span class=\'ellipsis_text\'>';
      var domains = rdata['cert_data']['dns'].join("、");
      var cert_data = ('</span></div>			</div>			<div class=\'state_info_flex\'>				<div class=\'state_item\'><span>' + (lan && lan.site && t('site.site_auto_str_196') || '到期时间：') + '</span><span class=\'btlink\'>' + (lan && lan.site && t('site.site_auto_str_196_1') || '剩余')) + issuer_o + ((lan && lan.site && t('site.site_auto_str_197') || '天到期') + '</span></div>				<div class=\'state_item\'><span>' + (lan && lan.site && t('site.site_auto_str_197_1') || '认证域名：') + '</span><span class=\'ellipsis_text\'>') + issuer + ('</span></div>			</div>			<div class=\'state_info_flex\'>				<div class=\'state_item\'><span>' + (lan && lan.site && t('site.site_auto_str_198') || '强制HTTPS：') + '</span><span class=\'switch\'>					<input class=\'btswitch btswitch-ios\' id=\'toHttps\' type=\'checkbox\'>                    <label class=\'btswitch-btn\' for=\'toHttps\' onclick="httpToHttps(\'') + rdata['cert_data']['endtime'] + ((lan && lan.site && t('site.site_auto_str_199') || '\')">删除') + '</button>') + domains + ((lan && lan.site && t('site.site_auto_str_200') || '\')" style=\'margin-left:3px;\'>关闭SSL') + '</button>') + siteName + "')\">\
				</span></div>\
			</div>";
      $(".ssl_state_info").html(cert_data);
      $(".ssl_state_info").css('display', 'block');
    }
    if (rdata.key == false) {
      rdata.key = '';
    } else {
      $(".ssl-btn").append('<button style=\'margin-left:3px;\' class="btn btn-success btn-sm" onclick="deleteSSL(\'now\',' + id + ',\'' + siteName + ((lan && lan.site && t('site.site_auto_str_201') || '\')" style=\'margin-left:3px;\'>手动续签') + '</button>'));
    }
    if (rdata.csr == false) {
      rdata.csr = '';
    }
    $("#key").val(rdata.key);
    $("#csr").val(rdata.csr);
    $("#toHttps").attr('checked', rdata.httpTohttps);
    if (rdata.status) {
      $('.warning_info').css('display', 'none');
      $(".ssl-btn").append("<button class='btn btn-success btn-sm' onclick=\"ocSSL('close_ssl_conf','" + siteName + ((lan && lan.site && t('site.site_auto_str_202') || '当前证书 -') + ' <i style="color:#20a53a;">' + (lan && lan.site && t('site.site_auto_str_202_1') || '[已部署SSL]') + '</i>'));
      $(".ssl-btn").append("<button class='btn btn-success btn-sm' onclick=\"renewSSL('acme'," + id + ",'" + siteName + ((lan && lan.site && t('site.site_auto_str_203') || '当前证书 -') + ' <i style="color:red;">' + (lan && lan.site && t('site.site_auto_str_203_1') || '[未部署SSL]') + '</i>'));
      $('#now_ssl').html('<div class="apply_ssl">		<div class="label-input-group">			<div class="line">				<span class="tname text-center">' + (lan && lan.site && t('site.site_auto_str_204') || '验证方式') + '</span>				<div style="margin-top:7px;display:inline-block">					<input type="radio" name="apply_type" value="file" id="check_file" checked="checked"/>  					<label class="mr20" for="check_file" style="font-weight:normal">' + (lan && lan.site && t('site.site_auto_str_204_1') || '文件验证') + '</label></label>  					<input type="radio" name="apply_type" value="dns" id="check_dns"/>  					<label class="mr20" for="check_dns" style="font-weight:normal">' + (lan && lan.site && t('site.site_auto_str_204_2') || 'DNS验证') + '</label></label>  				</div>	  		</div>	  		<div class="line">				<span class="tname text-center">' + (lan && lan.site && t('site.site_auto_str_204_3') || '证书') + '</span>				<div style="margin-top:7px;display:inline-block">					<input type="radio" name="apply_ca" value="default" id="ca_default" checked="checked"/>  					<label class="mr20" for="ca_default" style="font-weight:normal">' + (lan && lan.site && t('site.site_auto_str_204_4') || '默认') + '</label></label>  					<input type="radio" name="apply_ca" value="let" id="ca_letsencrypt"/>  					<label class="mr20" for="ca_letsencrypt" style="font-weight:normal">letsencrypt</label></label>  					<input type="radio" name="apply_ca" value="zerossl" id="ca_zerossl/>  					<label class="mr20" for="ca_zerossl" style="font-weight:normal">zerossl</label></label>  					<input type="radio" name="apply_ca" value="buypass" id="ca_buypass/>  					<label class="mr20" for="ca_buypass" style="font-weight:normal">buypass</label></label>  				</div>	  		</div>	  		<div class="line mtb10" id="dnsapi_option" style="display:none;">				<span class="tname text-center" style="line-height: 42px;">' + (lan && lan.site && t('site.site_auto_str_204_5') || '选择DNS接口') + '</span>				<div style="margin-top:7px;display:inline-block">					<select name="dnspai" class="bt-input-text mr20">						<option value="none">' + (lan && lan.site && t('site.site_auto_str_204_6') || '手动解析') + '</option>					</select>					<button id="dnsapi_set" class="btn btn-default btn-sm btn-title" style="display:none;">' + (lan && lan.site && t('site.site_auto_str_204_7') || '配置') + '</button>  				</div>	  		</div>  			<div class="check_message line" id="wildcard_domain_block" style="display:none;">  				<div style="margin-left:100px">  					<input type="checkbox" name="wildcard_domain" id="wildcard_domain" checked="checked">  					<label class="mr20" for="wildcard_domain" style="font-weight:normal">' + (lan && lan.site && t('site.site_auto_str_204_8') || '自动组合泛域名') + '</label>  				</div>  			</div>  			<div class="check_message line">  				<div style="margin-left:100px; margin-top:8px;">  					<input type="checkbox" name="checkDomain" id="checkDomain" checked="">  					<label class="mr20" for="checkDomain" style="font-weight:normal">' + (lan && lan.site && t('site.site_auto_str_204_9') || '提前校验域名(提前发现问题,减少失败率)') + '</label>  				</div>  			</div>  		</div>  		<div class="line mtb10">  			<span class="tname text-center">' + (lan && lan.site && t('site.site_auto_str_204_10') || '邮箱') + '</span>  			<input class="bt-input-text" style="width:240px;" type="text" name="admin_email" />  		</div>  		<div class="line mtb10" id="dns_alias" style="display:none;">			<span class="tname text-center">' + (lan && lan.site && t('site.site_auto_str_204_11') || '别名验证') + '</span>			<input class="bt-input-text" style="width:240px;" type="text" name="dns_alias" />			<span> ' + (lan && lan.site && t('site.site_auto_str_204_12') || '(建议别用)') + ' <a class="btlink" target="_blank" href="https://github.com/acmesh-official/acme.sh/wiki/DNS-alias-mode#7-challenge-alias-or-domain-alias">' + (lan && lan.site && t('site.site_auto_str_204_13') || '文档说明') + '</a><span>		</div>  		<div class="line mtb10">  			<span class="tname text-center">' + (lan && lan.site && t('site.site_auto_str_204_14') || '域名') + '</span>  			<ul id="ymlist" style="padding: 5px 10px;max-height:180px;overflow:auto; width:240px;border:#ccc 1px solid;border-radius:3px"></ul>  		</div>  		<div class="line mtb10" style="margin-left:100px">  			<button class="btn btn-success btn-sm letsApply">' + (lan && lan.site && t('site.site_auto_str_204_15') || '申请') + '</button>  		</div>		<ul class="help-info-text c7" id="lets_help">			<li>' + (lan && lan.site && t('site.site_auto_str_204_16') || '申请之前，请确保域名已解析，如未解析会导致审核失败') + '</li>			<li>' + (lan && lan.site && t('site.site_auto_str_204_17') || '由ACME免费申请证书，有效期3个月，支持多域名。默认会自动续签') + '</li>			<li>' + (lan && lan.site && t('site.site_auto_str_204_18') || '若您的站点使用了CDN或301重定向会导致续签失败') + '</li>			<li>' + (lan && lan.site && t('site.site_auto_str_204_19') || '在未指定SSL默认站点时,未开启SSL的站点使用HTTPS会直接访问到已开启SSL的站点') + '</li></ul>	 	</ul>	</div>');
    } else {
      $('.warning_info').css('display', 'block');
      $('#now_ssl').html('<div class="myKeyCon ptb15">				<div class="ssl_state_info" style="display:none;"></div>				<div class="custom_certificate_info">					<div class="ssl-con-key pull-left mr20" readonly>' + (lan && lan.site && t('site.site_auto_str_205') || '密钥(KEY)') + '<br><textarea id="key" class="bt-input-text">');
    }
    if (typeof callback != 'undefined') {
      callback(rdata);
    }
  }, 'json');
}
function opSSLAcme(type, id, siteName, callback) {
  var acme = '</textarea></div>					<div class="ssl-con-key pull-left" readonly>' + (lan && lan.site && t('site.site_auto_str_206') || '证书(PEM格式)') + '<br><textarea id="csr" class="bt-input-text">';
  $(".tab-con").html(acme);
  $('input[name="apply_type"]').on('change', function () {
    var val = $(this).val();
    if (val == 'file') {
      $('#dnsapi_option').css('display', 'none');
      $('#wildcard_domain_block').css('display', 'none');
      $('#dns_alias').css('display', 'none');
    } else {
      $('#dnsapi_option').css('display', 'block');
      $('#wildcard_domain_block').css('display', 'block');

      // 关闭,咱不开发,没有验证通过
      $('#dns_alias').css('display', 'block');
    }
  });
  renderDnsapi();
  $.post('/site/get_ssl', 'site_name=' + siteName + '&ssl_type=acme', function (data) {
    var rdata = data['data'];
    if (rdata.csr == false) {
      $.post('/site/get_site_domains', 'id=' + id, function (rdata) {
        var data = rdata['data'];
        var opt = '';
        for (var i = 0; i < data.domains.length; i++) {
          var isIP = isValidIP(data.domains[i].name);
          var x = isContains(data.domains[i].name, '*');
          if (!isIP && !x) {
            opt += '<li style="line-height:26px">\
							<input type="checkbox" style="margin-right:5px; vertical-align:-2px" value="' + data.domains[i].name + '">' + data.domains[i].name + '</li>';
          }
        }
        $("input[name='admin_email']").val(data.email);
        $("#ymlist").html(opt);
        $("#ymlist li input").on('click', function (e) {
          e.stopPropagation();
        });
        $("#ymlist li").on('click', function () {
          var o = $(this).find("input");
          if (o.prop("checked")) {
            o.prop("checked", false);
          } else {
            o.prop("checked", true);
          }
        });
        $(".letsApply").on('click', function () {
          var c = $("#ymlist input[type='checkbox']");
          var str = [];
          var domains = '';
          for (var i = 0; i < c.length; i++) {
            if (c[i].checked) {
              str.push(c[i].value);
            }
          }
          domains = JSON.stringify(str);
          newAcmeSSL(siteName, id, domains);
        });
        if (typeof callback != 'undefined') {
          callback(rdata);
        }
      }, 'json');
      return;
    }
    var acme = ((lan && lan.site && t('site.site_auto_str_207') || '\')">部署') + '</button>					<button class="btn btn-success btn-sm" onclick="deleteSSL(\'acme\',') + rdata.key + ((lan && lan.site && t('site.site_auto_str_208') || '\')">删除') + '</button>				</div>			</div>			<ul class="help-info-text c7 pull-left">				<li>' + (lan && lan.site && t('site.site_auto_str_208_1') || '已为您自动生成ACME免费证书') + '</li>				<li>' + (lan && lan.site && t('site.site_auto_str_208_2') || '由ACME免费申请证书，有效期3个月，支持多域名。默认会自动续签') + '</li>				<li>' + (lan && lan.site && t('site.site_auto_str_208_3') || '如需使用其他SSL,请切换其他证书后粘贴您的KEY以及PEM内容，然后保存即可。') + '</li>			</ul>') + rdata.csr + '</textarea></div>\
				</div>\
				<div class="ssl-btn pull-left mtb15" style="width:100%">\
					<button class="btn btn-success btn-sm" onclick="deploySSL(\'acme\',' + id + ',\'' + siteName + ('<div class=\'state_info_flex\'>				<div class=\'state_item\'><span>' + (lan && lan.site && t('site.site_auto_str_209') || '证书分类：') + '</span><span class=\'ellipsis_text\'>') + id + ',\'' + siteName + ('</span></div>				<div class=\'state_item\'><span>' + (lan && lan.site && t('site.site_auto_str_210') || '证书品牌：') + '</span><span class=\'ellipsis_text\'>');
    $(".tab-con").html(acme);
    if (rdata['cert_data']) {
      var issuer_o = rdata['cert_data']['issuer_o'] || '</span></div>			</div>			<div class=\'state_info_flex\'>				<div class=\'state_item\'><span>' + (lan && lan.site && t('site.site_auto_str_211') || '到期时间：') + '</span><span class=\'btlink\'>' + (lan && lan.site && t('site.site_auto_str_211_1') || '剩余');
      var issuer = rdata['cert_data']['issuer'] || (lan && lan.site && t('site.site_auto_str_212') || '天到期') + '</span></div>				<div class=\'state_item\'><span>' + (lan && lan.site && t('site.site_auto_str_212_1') || '认证域名：') + '</span><span class=\'ellipsis_text\'>';
      var domains = rdata['cert_data']['dns'].join("、");
      var cert_data = ('<div class="apply_ssl">		<div class="label-input-group">			<div class="line mtb10">				<span class="tname text-center">' + (lan && lan.site && t('site.site_auto_str_213') || '验证方式') + '</span>				<div style="margin-top:7px;display:inline-block">					<input type="radio" name="apply_type" value="file" id="check_file" checked="checked"/>  					<label class="mr20" for="check_file" style="font-weight:normal">' + (lan && lan.site && t('site.site_auto_str_213_1') || '文件验证') + '</label></label>  					<input type="radio" name="apply_type" value="dns" id="check_dns"/>  					<label class="mr20" for="check_dns" style="font-weight:normal">' + (lan && lan.site && t('site.site_auto_str_213_2') || 'DNS验证') + '</label></label>  				</div>	  		</div>	  		<div class="line mtb10" id="dnsapi_option" style="display:none;">				<span class="tname text-center" style="line-height: 42px;">' + (lan && lan.site && t('site.site_auto_str_213_3') || '选择DNS接口') + '</span>				<div style="margin-top:7px;display:inline-block">					<select name="dnspai" class="bt-input-text mr20">						<option value="none">' + (lan && lan.site && t('site.site_auto_str_213_4') || '手动解析') + '</option>					</select>					<button id="dnsapi_set" class="btn btn-default btn-sm btn-title" style="display:none;">' + (lan && lan.site && t('site.site_auto_str_213_5') || '配置') + '</button>  				</div>	  		</div>	  		<div class="check_message line" id="wildcard_domain_block" style="display:none;">  				<div style="margin-left:100px">  					<input type="checkbox" name="wildcard_domain" id="wildcard_domain" checked="checked">  					<label class="mr20" for="wildcard_domain" style="font-weight:normal">' + (lan && lan.site && t('site.site_auto_str_213_6') || '自动组合泛域名') + '</label>  				</div>  			</div>  			<div class="check_message line">  				<div style="margin-left:100px">  					<input type="checkbox" name="checkDomain" id="checkDomain" checked="">  					<label class="mr20" for="checkDomain" style="font-weight:normal">' + (lan && lan.site && t('site.site_auto_str_213_7') || '提前校验域名(提前发现问题,减少失败率)') + '</label>  				</div>  			</div>  		</div>  		<div class="line mtb10">  			<span class="tname text-center">' + (lan && lan.site && t('site.site_auto_str_213_8') || '邮箱') + '</span>  			<input class="bt-input-text" style="width:240px;" type="text" name="admin_email" />  		</div>  		<div class="line mtb10">  			<span class="tname text-center">' + (lan && lan.site && t('site.site_auto_str_213_9') || '域名') + '</span>  			<ul id="ymlist" style="padding: 5px 10px;max-height:180px;overflow:auto; width:240px;border:#ccc 1px solid;border-radius:3px"></ul>  		</div>  		<div class="line mtb10" style="margin-left:100px">  			<button class="btn btn-success btn-sm letsApply">' + (lan && lan.site && t('site.site_auto_str_213_10') || '申请') + '</button>  		</div>	  	<ul class="help-info-text c7" id="lets_help">	  		<li>' + (lan && lan.site && t('site.site_auto_str_213_11') || '申请之前，请确保域名已解析，如未解析会导致审核失败') + '</li>	  		<li>' + (lan && lan.site && t('site.site_auto_str_213_12') || 'Let\'s Encrypt免费证书，有效期3个月，支持多域名。默认会自动续签') + '</li>	  		<li>' + (lan && lan.site && t('site.site_auto_str_213_13') || '若您的站点使用了CDN或301重定向会导致续签失败') + '</li>	  		<li>' + (lan && lan.site && t('site.site_auto_str_213_14') || '在未指定SSL默认站点时,未开启SSL的站点使用HTTPS会直接访问到已开启SSL的站点') + '</li>	  	</ul>  	</div>') + issuer_o + ('<div class="myKeyCon ptb15">				<div class="ssl_state_info" style="display:none;"></div>				<div class="custom_certificate_info">					<div class="ssl-con-key pull-left mr20" readonly>' + (lan && lan.site && t('site.site_auto_str_214') || '密钥(KEY)') + '<br><textarea id="key" class="bt-input-text">') + issuer + ('</textarea></div>					<div class="ssl-con-key pull-left" readonly>' + (lan && lan.site && t('site.site_auto_str_215') || '证书(PEM格式)') + '<br><textarea id="csr" class="bt-input-text">') + rdata['cert_data']['endtime'] + ((lan && lan.site && t('site.site_auto_str_216') || '\')">部署') + '</button>					<button class="btn btn-success btn-sm" onclick="renewSSL(\'lets\',') + domains + "</span></div>\
			</div>";
      $(".ssl_state_info").html(cert_data);
      $(".ssl_state_info").css('display', 'block');
    }
  }, 'json');
}
function opSSLLet(type, id, siteName, callback) {
  var lets = (lan && lan.site && t('site.site_auto_str_217') || '\')">续期') + '</button>					<button class="btn btn-success btn-sm" onclick="deleteSSL(\'lets\',';
  $(".tab-con").html(lets);
  $('input[name="apply_type"]').on('change', function () {
    var val = $(this).val();
    if (val == 'file') {
      $('#dnsapi_option').css('display', 'none');
      $('#wildcard_domain_block').css('display', 'none');
    } else {
      $('#dnsapi_option').css('display', 'block');
      $('#wildcard_domain_block').css('display', 'block');
    }
  });
  renderDnsapi();
  $.post('/site/get_ssl', 'site_name=' + siteName + '&ssl_type=lets', function (data) {
    var rdata = data['data'];
    if (rdata.csr == false) {
      $.post('/site/get_site_domains', 'id=' + id, function (rdata) {
        var data = rdata['data'];
        var opt = '';
        for (var i = 0; i < data.domains.length; i++) {
          var isIP = isValidIP(data.domains[i].name);
          var x = isContains(data.domains[i].name, '*');
          if (!isIP && !x) {
            opt += '<li style="line-height:26px"><input type="checkbox" style="margin-right:5px; vertical-align:-2px" value="' + data.domains[i].name + '">' + data.domains[i].name + '</li>';
          }
        }
        $("input[name='admin_email']").val(data.email);
        $("#ymlist").html(opt);
        $("#ymlist li input").on('click', function (e) {
          e.stopPropagation();
        });
        $("#ymlist li").on('click', function () {
          var o = $(this).find("input");
          if (o.prop("checked")) {
            o.prop("checked", false);
          } else {
            o.prop("checked", true);
          }
        });
        $(".letsApply").on('click', function () {
          var c = $("#ymlist input[type='checkbox']");
          var str = [];
          var domains = '';
          for (var i = 0; i < c.length; i++) {
            if (c[i].checked) {
              str.push(c[i].value);
            }
          }
          domains = JSON.stringify(str);
          newSSL(siteName, id, domains);
        });
        if (typeof callback != 'undefined') {
          callback(rdata);
        }
      }, 'json');
      return;
    }
    var lets = ((lan && lan.site && t('site.site_auto_str_218') || '\')">删除') + '</button>				</div>			</div>			<ul class="help-info-text c7 pull-left">				<li>' + (lan && lan.site && t('site.site_auto_str_218_1') || '已为您自动生成Let\'s Encrypt免费证书') + '</li>				<li>' + (lan && lan.site && t('site.site_auto_str_218_2') || '由Let\'s Encrypt免费申请证书，有效期3个月，支持多域名。默认会自动续签') + '</li>				<li>' + (lan && lan.site && t('site.site_auto_str_218_3') || '如需使用其他SSL,请切换其他证书后粘贴您的KEY以及PEM内容，然后保存即可。') + '</li>			</ul>') + rdata.key + ('<div class=\'state_info_flex\'>				<div class=\'state_item\'><span>' + (lan && lan.site && t('site.site_auto_str_219') || '证书分类：') + '</span><span class=\'ellipsis_text\'>') + rdata.csr + '</textarea></div>\
				</div>\
				<div class="ssl-btn pull-left mtb15" style="width:100%">\
					<button class="btn btn-success btn-sm" onclick="deploySSL(\'lets\',' + id + ',\'' + siteName + ('</span></div>				<div class=\'state_item\'><span>' + (lan && lan.site && t('site.site_auto_str_220') || '证书品牌：') + '</span><span class=\'ellipsis_text\'>') + id + ',\'' + siteName + ('</span></div>			</div>			<div class=\'state_info_flex\'>				<div class=\'state_item\'><span>' + (lan && lan.site && t('site.site_auto_str_221') || '到期时间：') + '</span><span class=\'btlink\'>' + (lan && lan.site && t('site.site_auto_str_221_1') || '剩余')) + id + ',\'' + siteName + ((lan && lan.site && t('site.site_auto_str_222') || '天到期') + '</span></div>				<div class=\'state_item\'><span>' + (lan && lan.site && t('site.site_auto_str_222_1') || '认证域名：') + '</span><span class=\'ellipsis_text\'>');
    $(".tab-con").html(lets);
    if (rdata['cert_data']) {
      var issuer_o = rdata['cert_data']['issuer_o'] || lan && lan.site && t('site.site_auto_str_223') || "";
      var issuer = rdata['cert_data']['issuer'] || lan && lan.site && t('site.site_auto_str_224') || "";
      var domains = rdata['cert_data']['dns'].join("、");
      var cert_data = ('<p>' + (lan && lan.site && t('site.site_auto_str_225') || '证书获取失败：') + '</p><hr />') + issuer_o + ('<p>' + (lan && lan.site && t('site.site_auto_str_226') || '域名:') + ' ') + issuer + ('<p>' + (lan && lan.site && t('site.site_auto_str_227') || '错误类型:') + ' ') + rdata['cert_data']['endtime'] + ('<p>' + (lan && lan.site && t('site.site_auto_str_228') || '详情:') + ' ') + domains + "</span></div>\
			</div>";
      $(".ssl_state_info").html(cert_data);
      $(".ssl_state_info").css('display', 'block');
    }
  }, 'json');
}

//SSL
function opSSL(type, id, siteName, callback) {
  switch (type) {
    case 'lets':
      opSSLLet(type, id, siteName, callback);
      break;
    case 'acme':
      opSSLAcme(type, id, siteName, callback);
      break;
    case 'now':
      opSSLNow(type, id, siteName, callback);
      break;
    default:
      layer.msg(lan && lan.site && t('site.site_auto_str_229') || "", {
        icon: 5
      });
      break;
  }
}

//开启与关闭SSL
function ocSSL(action, siteName) {
  var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_230') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post("/site/" + action, 'siteName=' + siteName + '&updateOf=1', function (rdata) {
    layer.close(loadT);
    if (!rdata.status) {
      if (!rdata.out) {
        layer.msg(rdata.msg, {
          icon: rdata.status ? 1 : 2
        });
        setSSL(siteName);
        return;
      }
      data = lan && lan.site && t('site.site_auto_str_231') || "";
      for (var i = 0; i < rdata.out.length; i++) {
        data += (lan && lan.site && t('site.site_auto_str_232') || "") + rdata.out[i].Domain + "</p>" + (lan && lan.site && t('site.site_auto_str_233') || "") + rdata.out[i].Type + "</p>" + ('<div class="bt-form" style="padding: 10px 20px;">			<div class="line"><span>' + (lan && lan.site && t('site.site_auto_str_234') || '请按以下列表做TXT解析:') + ' </span></div>			<div id="acme_hand_ssl_notice" class="divtable mtb10">                <div class="tablescroll">                    <table class="table table-hover" width="100%" cellspacing="0" cellpadding="0" border="0" style="border: 0 none;">                    <thead><tr><th>' + (lan && lan.site && t('site.site_auto_str_234_1') || '解析域名') + '</th><th>' + (lan && lan.site && t('site.site_auto_str_234_2') || '记录值') + '</th><th>' + (lan && lan.site && t('site.site_auto_str_234_3') || '类型') + '</th><th>' + (lan && lan.site && t('site.site_auto_str_234_4') || '必需') + '</th></tr></thead>                    <tbody></tbody>                    </table>                </div>            </div>			<ul id="acme_hand_ssl_notice_help" class="help-info-text c6">			    <li>' + (lan && lan.site && t('site.site_auto_str_234_5') || '解析域名需要一定时间来生效,完成所以上所有解析操作后,请等待1分钟后再点击【验证】按钮') + '</li>			    <li>' + (lan && lan.site && t('site.site_auto_str_234_6') || '可通过CMD命令来手动验证域名解析是否生效: nslookup -q=txt _acme-challenge.xx.cn') + '</li>			    <li>' + (lan && lan.site && t('site.site_auto_str_234_7') || '若您使用的是阿里云DNS,DnsPod等等作为DNS,可使用DNS接口自动解析') + '</li>		    </ul>		</div>') + rdata.out[i].Detail + "</p>" + "<hr />";
      }
      layer.msg(data, {
        icon: 2,
        time: 0,
        shade: 0.3,
        shadeClose: true
      });
      return;
    }
    layer.msg(rdata.msg, {
      icon: rdata.status ? 1 : 2
    });
    if (action == 'close_ssl_conf') {
      layer.msg('<td>' + (lan && lan.site && t('site.site_auto_str_235') || '必需') + '</td>', {
        icon: 1,
        time: 5000
      });
    }
    $(".tab-nav .on").click();
  }, 'json');
}

//生成SSL
function newSSL(siteName, id, domains) {
  showSpeedWindow('<td>' + (lan && lan.site && t('site.site_auto_str_236') || '可选') + '</td>', 'site.get_let_logs', function (layers, index) {
    var pdata = {};
    pdata['siteName'] = siteName;
    pdata['domains'] = domains;
    pdata['email'] = $("input[name='admin_email']").val();
    if ($("#checkDomain").prop("checked")) {
      pdata['force'] = 'true';
    }
    if ($("#wildcard_domain").prop("checked")) {
      pdata['wildcard_domain'] = 'true';
    }
    var apply_type = $('input[name="apply_type"]:checked').val();
    pdata['apply_type'] = apply_type;
    if (apply_type == 'dns') {
      pdata['dnspai'] = $('#dnsapi_option option:selected').val();
    }
    $.post('/site/create_let', pdata, function (rdata) {
      showMsg(rdata.msg, function () {
        layer.close(index);
        if (rdata.status) {
          $(".tab-nav span:first-child").click();
        }
      }, {
        icon: rdata.status ? 1 : 2
      }, 3000);
    }, 'json');
  });
}

// 手动申请dns提示
function newAcmeHandApplyNotice(siteName, id, domains, data) {
  // console.log(siteName, id, domains, data);
  layer.open({
    type: 1,
    area: '700px',
    title: lan && lan.site && t('site.site_auto_str_237') || "",
    closeBtn: 1,
    shift: 5,
    shadeClose: true,
    btn: [lan && lan.site && t('site.site_auto_str_238') || "", lan && lan.site && t('site.site_auto_str_239') || ""],
    content: lan && lan.site && t('site.site_auto_str_240') || "",
    success: function () {
      var list = '';
      for (var i = 0; i < data.length; i++) {
        list += '<tr>';
        list += '<td>' + data[i]['domain'] + '</td>';
        list += '<td>' + data[i]['val'] + '</td>';
        list += '<td>' + data[i]['type'] + '</td>';
        if (data[i]['must']) {
          list += '<div class=\'webEdit-box\'>									<div class=\'line\'>										<span class=\'tname\' style=\'width:100px\'>' + (lan && lan.site && t('site.site_auto_str_241') || 'PHP版本') + '</span>										<div class=\'info-r\'>											<select id=\'phpVersion\' class=\'bt-input-text mr5\' name=\'phpVersion\' style=\'width:110px\'>';
        } else {
          list += '</button>							</div>							<span id=\'php_w\' style=\'color:red;margin-left: 32px;\'></span>						</div>							<ul class=\'help-info-text c7 ptb10\'>								<li>' + (lan && lan.site && t('site.site_auto_str_242') || '请根据您的程序需求选择版本') + '</li>								<li>' + (lan && lan.site && t('site.site_auto_str_242_1') || '若非必要,请尽量不要使用PHP5.2,这会降低您的服务器安全性；') + '</li>								<li>' + (lan && lan.site && t('site.site_auto_str_242_2') || 'PHP7不支持mysql扩展，默认安装mysqli以及mysql-pdo。') + '</li>							</ul>						</div>					</div>';
        }
        list += '</tr>';
      }
      $('#acme_hand_ssl_notice tbody').html(list);
      if (data.length > 0) {
        var help_txt = (lan && lan.site && t('site.site_auto_str_243') || "") + data[0]['domain'];
        $('#acme_hand_ssl_notice_help li:eq(1)').text(help_txt);
      }
    },
    yes: function (layero, index) {
      layer.close(layero);
      showSpeedWindow(lan && lan.site && t('site.site_auto_str_244') || "", 'site.get_acme_logs', function (layers, index) {
        var pdata = {};
        pdata['siteName'] = siteName;
        pdata['domains'] = domains;
        pdata['email'] = $("input[name='admin_email']").val();
        if ($("#checkDomain").prop("checked")) {
          pdata['force'] = 'true';
        }
        if ($("#wildcard_domain").prop("checked")) {
          pdata['wildcard_domain'] = 'true';
        }
        var apply_type = $('input[name="apply_type"]:checked').val();
        pdata['apply_type'] = apply_type;
        var apply_ca = $('input[name="apply_ca"]:checked').val();
        pdata['apply_ca'] = apply_ca;
        if (apply_type == 'dns') {
          pdata['dnspai'] = $('#dnsapi_option option:selected').val();
        }
        pdata['dns_alias'] = $("input[name='dns_alias']").val();
        pdata['renew'] = 'true';
        $.post('/site/create_acme', pdata, function (rdata) {
          showMsg(rdata.msg, function () {
            if (rdata.status) {
              layer.close(index);
              $(".tab-nav span:first-child").click();
            }
          }, {
            icon: rdata.status ? 1 : 2
          }, 3000);
        }, 'json');
      });
    }
  });
}
function newAcmeSSL(siteName, id, domains) {
  showSpeedWindow(lan && lan.site && t('site.site_auto_str_245') || "", 'site.get_acme_logs', function (layers, index) {
    var pdata = {};
    pdata['siteName'] = siteName;
    pdata['domains'] = domains;
    pdata['email'] = $("input[name='admin_email']").val();
    if ($("#checkDomain").prop("checked")) {
      pdata['force'] = 'true';
    }
    if ($("#wildcard_domain").prop("checked")) {
      pdata['wildcard_domain'] = 'true';
    }
    var apply_type = $('input[name="apply_type"]:checked').val();
    pdata['apply_type'] = apply_type;
    var apply_ca = $('input[name="apply_ca"]:checked').val();
    pdata['apply_ca'] = apply_ca;
    if (apply_type == 'dns') {
      pdata['dnspai'] = $('#dnsapi_option option:selected').val();
    }
    pdata['dns_alias'] = $("input[name='dns_alias']").val();
    $.post('/site/create_acme', pdata, function (rdata) {
      showMsg(rdata.msg, function () {
        if (rdata.status) {
          layer.close(index);
          if (rdata.msg == (lan && lan.site && t('site.site_auto_str_246') || "")) {
            newAcmeHandApplyNotice(siteName, id, domains, rdata.data);
          } else {
            $(".tab-nav span:first-child").click();
          }
        }
      }, {
        icon: rdata.status ? 1 : 2
      }, 3000);
    }, 'json');
  });
}

//保存SSL
function saveSSL(siteName) {
  var data = 'type=1&siteName=' + siteName + '&key=' + encodeURIComponent($("#key").val()) + '&csr=' + encodeURIComponent($("#csr").val());
  var loadT = layer.msg(t('site.saving_txt'), {
    icon: 16,
    time: 20000,
    shade: [0.3, '#000']
  });
  $.post('/site/set_ssl', data, function (rdata) {
    layer.close(loadT);
    if (rdata.status) {
      layer.msg(rdata.msg, {
        icon: 1
      });
      $(".ssl-btn").find(".btn-default").remove();
      $(".ssl-btn").append("<button class='btn btn-default btn-sm' onclick=\"ocSSL('close_ssl_conf','" + siteName + "')\" style='margin-left:10px'>" + t('site.ssl_close') + "</button>");
    } else {
      layer.msg(rdata.msg, {
        icon: 2,
        time: 0,
        shade: 0.3,
        shadeClose: true
      });
    }
  }, 'json');
}

//PHP版本
function phpVersion(siteName) {
  $.post('/site/get_site_php_version', 'siteName=' + siteName, function (version) {
    // console.log(version);
    if (version.status === false) {
      layer.msg(version.msg, {
        icon: 5
      });
      return;
    }
    $.post('/site/get_php_version', function (data) {
      var rdata = data.data;
      var versionSelect = '<div class=\'bt-form pd20\' style=\'padding-bottom: 50px;\'>							<p style=\'font-size: 14px;\'>' + (lan && lan.site && t('site.site_auto_str_247') || '修改域名【');
      var optionSelect = '';
      for (var i = 0; i < rdata.length; i++) {
        optionSelect = version.phpversion == rdata[i].version ? 'selected' : '';
        versionSelect += "<option value='" + rdata[i].version + "' " + optionSelect + ">" + rdata[i].name + "</option>";
      }
      versionSelect += "</select>\
							<button class='btn btn-success btn-sm' onclick=\"setPHPVersion('" + siteName + "')\">" + t('site.switch') + (lan && lan.site && t('site.site_auto_str_248') || "");
      $("#webedit-con").html(versionSelect);
      //验证PHP版本
      $("select[name='phpVersion']").on('change', function () {
        if ($(this).val() == '52') {
          var msgerr = '</p>							<p class=\'line\' style=\'margin-top:15px;\'>								<span class=\'tname\' style=\'width:120px;text-align:left;\'>' + (lan && lan.site && t('site.site_auto_str_249') || '修改 PHP 版本号为：') + '</span>								<select id=\'newPHPVersion\' class=\'bt-input-text\' style=\'width:150px;\'>';
          $('#php_w').text(msgerr);
        } else {
          $('#php_w').text('');
        }
      });
    }, 'json');
  }, 'json');
}

//设置PHP版本
function setPHPVersion(siteName) {
  var data = 'version=' + $("#phpVersion").val() + '&siteName=' + siteName;
  var loadT = layer.msg('</select>							</p>							<div class=\'bt-form-submit-btn\'>								<button type=\'button\' class=\'btn btn-danger btn-sm\' onclick=\'layer.closeAll()\'>' + (lan && lan.site && t('site.site_auto_str_250') || '取消') + '</button>								<button type=\'button\' class=\'btn btn-success btn-sm\' onclick="submitChangePHPVersion(\'', {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/site/set_php_version', data, function (rdata) {
    layer.close(loadT);
    layer.msg(rdata.msg, {
      icon: rdata.status ? 1 : 2
    });
    if (rdata.status) {
      var php_version = $("#phpVersion").val();
      var php_show_text = php_version == '00' ? (lan && lan.site && t('site.site_auto_str_251') || '\')">确定') + '</button>							</div>						</div>' : php_version.length == 2 ? php_version.substring(0, 1) + '.' + php_version.substring(1) : php_version;
      var php_text = "<a class='btlink php_version_click' href='javascript:;' onclick=\"changePHPVersion(0, '" + siteName + "', '" + php_version + "')\" style='color:#20a53a'>" + php_show_text + "</a>";
      $("input[name='id'][title='" + siteName + "']").closest("tr").find("td").eq(7).html(php_text);
    }
  }, 'json');
}

//直接在列表页修改PHP版本
function changePHPVersion(id, siteName, currentVersion) {
  var currentVersionText = currentVersion == '00' ? lan && lan.site && t('site.site_auto_str_252') || "" : currentVersion.length == 2 ? currentVersion.substring(0, 1) + '.' + currentVersion.substring(1) : currentVersion;
  $.post('/site/get_php_version', function (data) {
    var rdata = data.data;
    var optionsHtml = '';
    for (var i = 0; i < rdata.length; i++) {
      var isSelected = currentVersion == rdata[i].version ? 'selected' : '';
      optionsHtml += "<option value='" + rdata[i].version + "' " + isSelected + ">" + rdata[i].name + "</option>";
    }
    var msgHTML = t('site.change_php_version_msg', [siteName, currentVersionText, optionsHtml]);
    var btnHTML = t('site.confirm_change_php');
    var bodyContent = "<div class='info-r'>" + msgHTML + "</div><div class='info-r'><button class='btn btn-success btn-sm' onclick=\"setPHPVersion('" + siteName + "', '" + currentVersionText + "')\">" + btnHTML + "</button></div>";
    layer.open({
      type: 1,
      skin: 'demo-class',
      area: '480px',
      title: lan && lan.site && t('site.site_auto_str_258') || "",
      closeBtn: 1,
      shift: 0,
      shadeClose: false,
      content: bodyContent
    });
  }, 'json');
}

//提交列表直接修改的PHP版本并进行二次确认
function submitChangePHPVersion(siteName, currentVersionText) {
  var newVersion = $("#newPHPVersion").val();
  var newVersionText = $("#newPHPVersion option:selected").text();
  var confirmMsg = (lan && lan.site && t('site.site_auto_str_259') || "") + siteName + ('</textarea>			<div class=\'info-r\'>				<button id=\'SaveConfigFileBtn\' class=\'btn btn-success btn-sm\' style=\'margin-top:15px;\'>' + (lan && lan.site && t('site.site_auto_str_260') || '保存') + '</button>				<ul class=\'help-info-text c7 ptb10\'>					<li>' + (lan && lan.site && t('site.site_auto_str_260_1') || '此处为站点主配置文件,若您不了解配置规则,请勿随意修改.') + '</li>				</ul>			</div>		</div>') + currentVersionText + (lan && lan.site && t('site.site_auto_str_261') || "") + newVersionText + (lan && lan.site && t('site.site_auto_str_262') || "");
  layer.confirm(confirmMsg, {
    icon: 3,
    title: lan && lan.site && t('site.site_auto_str_263') || "",
    closeBtn: 2
  }, function (index) {
    layer.close(index);
    var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_264') || "", {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    var data = 'version=' + newVersion + '&siteName=' + siteName;
    $.post('/site/set_php_version', data, function (rdata) {
      layer.close(loadT);
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
      if (rdata.status) {
        layer.closeAll();
        var php_show_text = newVersion == '00' ? lan && lan.site && t('site.site_auto_str_265') || "" : newVersion.length == 2 ? newVersion.substring(0, 1) + '.' + newVersion.substring(1) : newVersion;
        var php_text = "<a class='btlink php_version_click' href='javascript:;' onclick=\"changePHPVersion(0, '" + siteName + "', '" + newVersion + "')\" style='color:#20a53a'>" + php_show_text + "</a>";
        $("input[name='id'][title='" + siteName + "']").closest("tr").find("td").eq(7).html(php_text);
      }
    }, 'json');
  });
}

//配置文件
function configFile(webSite) {
  $.post('/site/get_host_conf', {
    siteName: webSite
  }, function (info) {
    $.post('/files/get_body', 'path=' + info['host'], function (rdata) {
      var mBody = "<div class='webEdit-box padding-10'>\
		<textarea style='height: 320px; width: 740px; margin-left: 20px;line-height:18px' id='configBody'>" + rdata.data.data + (lan && lan.site && t('site.site_auto_str_266') || "");
      $("#webedit-con").html(mBody);
      var editor = CodeMirror.fromTextArea(document.getElementById("configBody"), {
        extraKeys: {
          "Ctrl-Space": "autocomplete",
          "Ctrl-F": "findPersistent",
          "Ctrl-H": "replace",
          "Ctrl-/": function (cm) {
            cm.toggleComment({
              lineComment: "#"
            });
          },
          "Ctrl-S": function () {
            $("#configBody").empty();
            $("#configBody").text(editor.getValue());
            saveConfigFile(webSite, rdata.data.encoding, info['host']);
          },
          "Cmd-S": function () {
            $("#configBody").empty();
            $("#configBody").text(editor.getValue());
            saveConfigFile(webSite, rdata.data.encoding, info['host']);
          }
        },
        lineNumbers: true,
        matchBrackets: true,
        mode: "text/x-nginx-conf"
      });
      editor.setSize("795px", "580px");
      $(".CodeMirror").css({
        "margin-left": "20px"
      });
      $(".CodeMirror-scroll").css({
        "height": "580px",
        "margin": 0,
        "padding": 0
      });
      $("#SaveConfigFileBtn").on('click', function () {
        $("#configBody").empty();
        $("#configBody").text(editor.getValue());
        saveConfigFile(webSite, rdata.data.encoding, info['host']);
      });
    }, 'json');
  }, 'json');
}

//保存配置文件
function saveConfigFile(webSite, encoding, path) {
  var data = 'encoding=' + encoding + '&data=' + encodeURIComponent($("#configBody").val()) + '&path=' + path;
  var loadT = layer.msg('</textarea></div>						<button id=\'SetRewriteBtn\' class=\'btn btn-success btn-sm\'>' + (lan && lan.site && t('site.site_auto_str_267') || '保存') + '</button>						<button id=\'SetRewriteBtnTel\' class=\'btn btn-success btn-sm\'>' + (lan && lan.site && t('site.site_auto_str_267_1') || '另存为模板') + '</button>						<ul class=\'help-info-text c7 ptb15\'>							<li>' + (lan && lan.site && t('site.site_auto_str_267_2') || '请选择您的应用，若设置伪静态后，网站无法正常访问，请尝试设置回default') + '</li>							<li>' + (lan && lan.site && t('site.site_auto_str_267_3') || '您可以对伪静态规则进行修改，修改完后保存即可。') + '</li>						</ul>						</div>', {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/site/save_host_conf', data, function (rdata) {
    layer.close(loadT);
    if (rdata.status) {
      layer.msg(rdata.msg, {
        icon: 1
      });
    } else {
      layer.msg(rdata.msg, {
        icon: 2,
        time: 0,
        shade: 0.3,
        shadeClose: true
      });
    }
  }, 'json');
}

//伪静态
function rewrite(siteName) {
  $.post("/site/get_rewrite_list", 'siteName=' + siteName, function (rdata) {
    $.post('/site/get_rewrite_conf', {
      siteName: siteName
    }, function (info) {
      var filename = info['rewrite'];
      $.post('/files/get_body', 'path=' + filename, function (fileBody) {
        var centent = fileBody['data']['data'];
        var rList = '';
        var rewriteNames = {
          'EmpireCMS': lan && lan.site && t('site.site_auto_str_268') || "",
          'dedecms': lan && lan.site && t('site.site_auto_str_269') || "",
          'discuzx': 'discuzx (Discuz!)',
          'discuzx2': 'discuzx2 (Discuz!)',
          'discuzx3': 'discuzx3 (Discuz!)',
          'drupal': 'drupal (Drupal)',
          'ecshop': 'ecshop (ECShop)',
          'emlog': 'emlog (Emlog)',
          'fastapi-web': 'fastapi-web (FastAPI)',
          'laravel5': 'laravel5 (Laravel)',
          'mvc': '<div class="changeDefault pd20">			<button class="btn btn-default btn-sm mg10" style="width:188px" onclick="changeDefault(1,this)">' + (lan && lan.site && t('site.site_auto_str_270') || '默认文档') + '</button>			<button class="btn btn-default btn-sm mg10" style="width:188px" onclick="changeDefault(2,this)">' + (lan && lan.site && t('site.site_auto_str_270_1') || '404错误页') + '</button>			<button class="btn btn-default btn-sm mg10" style="width:188px" onclick="changeDefault(3,this)">' + (lan && lan.site && t('site.site_auto_str_270_2') || '空白页') + '</button>			<button class="btn btn-default btn-sm mg10" style="width:188px" onclick="changeDefault(4,this)">' + (lan && lan.site && t('site.site_auto_str_270_3') || '默认站点停止页') + '</button>		</div>',
          'phpcms': 'phpcms (PHPCMS)',
          'phpwind': 'phpwind (PHPWind)',
          'sablog': 'sablog (SaBlog-X)',
          'seacms': '<option value="-1">' + (lan && lan.site && t('site.site_auto_str_271') || '全部分类') + '</option>',
          'shopex': 'shopex (ShopEx)',
          'thinkphp': 'thinkphp (ThinkPHP)',
          'typecho': 'typecho (Typecho)',
          'whmcs': 'whmcs (WHMCS)',
          'wmcms': (lan && lan.site && t('site.site_auto_str_272') || '\')">编辑') + '</a> | <a class="btlink del_type" onclick="removeClassType(\'',
          'wordpress': 'wordpress (WordPress)',
          'zblog': 'zblog (Z-Blog)'
        };
        for (var i = 0; i < rdata.rewrite.length; i++) {
          var name = rdata.rewrite[i];
          var displayName = rewriteNames[name] || name;
          if (i == 0) {
            rList += "<option value='0'>" + name + "</option>";
          } else {
            rList += "<option value='" + name + "'>" + displayName + "</option>";
          }
        }
        var webBakHtml = "<div class='bt-form'>\
						<div class='line'>\
						<select id='myRewrite' class='bt-input-text mr20' name='rewrite' style='width:30%;'>" + rList + "</select>\
						<textarea class='bt-input-text' style='height: 260px; width: 740px; line-height:18px;margin-top:10px;padding:5px;' id='rewriteBody'>" + centent + ((lan && lan.site && t('site.site_auto_str_273') || '\')">删除') + '</a>				</td></tr>');
        $("#webedit-con").html(webBakHtml);
        var editor = CodeMirror.fromTextArea(document.getElementById("rewriteBody"), {
          extraKeys: {
            "Ctrl-Space": "autocomplete",
            "Ctrl-F": "findPersistent",
            "Ctrl-H": "replace",
            "Ctrl-/": function (cm) {
              cm.toggleComment({
                lineComment: "#"
              });
            },
            "Ctrl-S": function () {
              $("#rewriteBody").empty();
              $("#rewriteBody").text(editor.getValue());
              setRewrite(filename, encodeURIComponent(editor.getValue()));
            },
            "Cmd-S": function () {
              $("#rewriteBody").empty();
              $("#rewriteBody").text(editor.getValue());
              setRewrite(filename, encodeURIComponent(editor.getValue()));
            }
          },
          lineNumbers: true,
          matchBrackets: true,
          mode: "text/x-nginx-conf"
        });
        editor.setSize("795px", "480px");
        $(".CodeMirror-scroll").css({
          "height": "560px",
          "margin": 0,
          "padding": 0
        });
        $("#SetRewriteBtn").on('click', function () {
          $("#rewriteBody").empty();
          $("#rewriteBody").text(editor.getValue());
          setRewrite(filename, encodeURIComponent(editor.getValue()));
        });
        $("#SetRewriteBtnTel").on('click', function () {
          $("#rewriteBody").empty();
          $("#rewriteBody").text(editor.getValue());
          setRewriteTel();
        });
        $("#myRewrite").on('change', function () {
          var rewriteName = $(this).val();
          if (rewriteName == '0') {
            rpath = filename;
            $.post('/files/get_body', 'path=' + rpath, function (fileBody) {
              $("#rewriteBody").val(fileBody['data']['data']);
              editor.setValue(fileBody['data']['data']);
            }, 'json');
          } else {
            $.post('/site/get_rewrite_tpl', {
              tplname: rewriteName
            }, function (info) {
              if (!info['status']) {
                layer.msg(info['msg']);
                return;
              }
              rpath = info['data'];
              $.post('/files/get_body', 'path=' + rpath, function (fileBody) {
                $("#rewriteBody").val(fileBody['data']['data']);
                editor.setValue(fileBody['data']['data']);
              }, 'json');
            }, 'json');
          }
        });
      }, 'json');
    }, 'json');
  }, 'json');
}

//设置伪静态
function setRewrite(filename, data) {
  var data = 'data=' + data + '&path=' + filename + '&encoding=utf-8';
  var loadT = layer.msg(t('site.saving_txt'), {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/site/set_rewrite', data, function (rdata) {
    layer.close(loadT);
    if (rdata.status) {
      layer.msg(rdata.msg, {
        icon: 1
      });
    } else {
      layer.msg(rdata.msg, {
        icon: 2,
        time: 0,
        shade: 0.3,
        shadeClose: true
      });
    }
  }, 'json');
}
var aindex = null;

//保存为模板
function setRewriteTel(act) {
  aindex = layer.open({
    type: 1,
    shift: 5,
    closeBtn: 1,
    area: '320px',
    //宽高
    title: lan && lan.site && t('site.site_auto_str_274') || "",
    btn: [t('public.ok'), t('public.cancel')],
    content: '<div class="bt-form pd20">\
					<div class="line">\
						<input type="text" class="bt-input-text" name="rewriteName" id="rewriteName" value="" placeholder="' + t('site.template_name') + '" style="width:100%" />\
					</div>\
				</div>',
    success: function (index) {
      $("#rewriteName").trigger('focus').on('keyup', function (e) {
        if (e.keyCode == 13) $("#rewriteNameBtn").click();
      });
    },
    yes: function (index) {
      name = $("#rewriteName").val();
      if (name == '') {
        layer.msg(t('site.template_empty'), {
          icon: 5
        });
        return;
      }
      var data = 'data=' + encodeURIComponent($("#rewriteBody").val()) + '&name=' + name;
      var loadT = layer.msg(t('site.saving_txt'), {
        icon: 16,
        time: 0,
        shade: [0.3, '#000']
      });
      $.post('/site/set_rewrite_tpl', data, function (rdata) {
        layer.close(loadT);
        layer.close(index);
        layer.msg(rdata.msg, {
          icon: rdata.status ? 1 : 5
        });
        if (rdata.status) {
          if ($("#myRewrite option[value='" + name + "']").length == 0) {
            $("#myRewrite").append("<option value='" + name + "'>" + name + "</option>");
          }
          $("#myRewrite").val(name);
        }
      }, 'json');
      return;
    }
  });
}
//修改默认页
function siteDefaultPage() {
  stype = getCookie('serverType');
  layer.open({
    type: 1,
    area: '460px',
    title: '<div class="bt-form edit_site_type">				<div class="divtable mtb15" style="overflow:auto">					<div class="line "><div class="info-r  ml0">						<input name="type_name" class="bt-input-text mr5 type_name" placeholder="请填写分类名称" type="text" style="width:50%" value=""><button name="btn_submit" class="btn btn-success btn-sm mr5 ml5 btn_submit" onclick="addClassType();">' + (lan && lan.site && t('site.site_auto_str_275') || '添加') + '</button></div>					</div>					<table id="type_table" class="table table-hover" width="100%">						<thead><tr><th>' + (lan && lan.site && t('site.site_auto_str_275_1') || '名称') + '</th><th width="80px">' + (lan && lan.site && t('site.site_auto_str_275_2') || '操作') + '</th></tr></thead>						<tbody>',
    closeBtn: 1,
    shift: 0,
    content: lan && lan.site && t('site.site_auto_str_276') || ""
  });
}
function changeDefault(type, obj) {
  $(obj).attr('disabled', true);
  $.post('/site/get_site_doc', 'type=' + type, function (rdata) {
    setTimeout(function () {
      $(obj).attr('disabled', false);
    }, 3000);
    if (rdata.status) {
      var path = rdata.data.path;
      onlineEditFile(0, path);
    }
  }, 'json');
}
function getClassType() {
  var select = $('.site_type > select');
  $.post('/site/get_site_types', function (rdata) {
    var rdata = rdata.data;
    $(select).html('');
    $(select).append(lan && lan.site && t('site.site_auto_str_277') || "");
    for (var i = 0; i < rdata.length; i++) {
      $(select).append('<option value="' + rdata[i]['id'] + '">' + rdata[i]['name'] + '</option>');
    }
    $(select).on('change', function () {
      var select_id = $(this).val();
      getWeb(1, select_id, '');
    });
  }, 'json');
}
getClassType();
function setClassType() {
  $.post('/site/get_site_types', function (rdata) {
    var rdata = rdata.data;
    var list = '';
    for (var i = 0; i < rdata.length; i++) {
      list += '<tr><td>' + rdata[i]['name'] + '</td>\
				<td><a class="btlink edit_type" onclick="editClassType(\'' + rdata[i]['id'] + '\',\'' + rdata[i]['name'] + (lan && lan.site && t('site.site_auto_str_278') || "") + rdata[i]['id'] + '\',\'' + rdata[i]['name'] + (lan && lan.site && t('site.site_auto_str_279') || "");
    }
    layer.open({
      type: 1,
      area: '350px',
      title: lan && lan.site && t('site.site_auto_str_280') || "",
      closeBtn: 1,
      shift: 0,
      content: ('<form class=\'bt-form bt-form pd20 pb70\' id=\'mod_pwd\'>                    <div class=\'line\'>                        <span class=\'tname\'>' + (lan && lan.site && t('site.site_auto_str_281') || '分类名称') + '</span>                        <div class=\'info-r\'><input name="site_type_mod" class=\'bt-input-text mr5\' type=\'text\' value=\'') + list + '</tbody>\
					</table>\
				</div>\
			</div>'
    });
  }, 'json');
}
function addClassType() {
  var name = $("input[name=type_name]").val();
  $.post('/site/add_site_type', 'name=' + name, function (rdata) {
    showMsg(rdata.msg, function () {
      if (rdata.status) {
        layer.closeAll();
        setClassType();
        getClassType();
      }
    }, {
      icon: rdata.status ? 1 : 2
    });
  }, 'json');
}
function removeClassType(id, name) {
  if (id == 0) {
    layer.msg('\' /></div>                    </div>                    <div class=\'bt-form-submit-btn\'>                        <button id=\'site_type_mod\' type=\'button\' class=\'btn btn-success btn-sm btn-title\'>' + (lan && lan.site && t('site.site_auto_str_282') || '提交') + '</button>                    </div>                  </form>', {
      icon: 2
    });
    return;
  }
  layer.confirm(lan && lan.site && t('site.site_auto_str_283') || "", {
    title: ('<div class="bt-form edit_site_type">					<div class="divtable mtb15" style="overflow:auto;height:80px;">						<div class="line"><span class="tname">' + (lan && lan.site && t('site.site_auto_str_284') || '默认站点') + '</span>							<div class="info-r">							<select class="bt-input-text mr5" name="type_id" style="width:200px">') + name + '】'
  }, function () {
    $.post('/site/remove_site_type', 'id=' + id, function (rdata) {
      showMsg(rdata.msg, function () {
        if (rdata.status) {
          layer.closeAll();
          setClassType();
          getClassType();
        }
      }, {
        icon: rdata.status ? 1 : 2
      });
    }, 'json');
  });
}
function editClassType(id, name) {
  if (id == 0) {
    layer.msg('							</select>							</div>						</div>					</div>					<div class="bt-form-submit-btn"><button onclick="setSizeClassType();" type="button" class="btn btn-sm btn-success">' + (lan && lan.site && t('site.site_auto_str_285') || '提交') + '</button></div>				</div>', {
      icon: 2
    });
    return;
  }
  layer.open({
    type: 1,
    area: '350px',
    title: (lan && lan.site && t('site.site_auto_str_286') || "") + name + '】',
    closeBtn: 1,
    shift: 0,
    content: (lan && lan.site && t('site.site_auto_str_287') || "") + name + (lan && lan.site && t('site.site_auto_str_288') || "")
  });
  $('#site_type_mod').off().on('click', function () {
    var _name = $('input[name=site_type_mod]').val();
    $.post('/site/modify_site_type_name', 'id=' + id + '&name=' + _name, function (rdata) {
      showMsg(rdata.msg, function () {
        if (rdata.status) {
          layer.closeAll();
          setClassType();
          getClassType();
        }
      }, {
        icon: rdata.status ? 1 : 2
      });
    }, 'json');
  });
}
function moveClassTYpe() {
  $.post('/site/get_site_types', function (rdata) {
    var option = '';
    for (var i = 0; i < rdata.length; i++) {
      option += '<option value="' + rdata[i]['id'] + '">' + rdata[i]['name'] + '</option>';
    }
    layer.open({
      type: 1,
      area: '350px',
      title: lan && lan.site && t('site.site_auto_str_289') || "",
      closeBtn: 1,
      shift: 0,
      content: (lan && lan.site && t('site.site_auto_str_290') || "") + option + (lan && lan.site && t('site.site_auto_str_291') || "")
    });
  }, 'json');
}
function setSizeClassType() {
  var data = {};
  data['id'] = $('select[name=type_id]').val();
  var ids = [];
  $('table').find('td').find('input').each(function (i, obj) {
    checked = $(this).prop('checked');
    if (checked) {
      ids.push($(this).val());
    }
  });
  data['site_ids'] = JSON.stringify(ids);
  $.post('/site/set_site_type', data, function (rdata) {
    showMsg(rdata.msg, function () {
      if (rdata.status) {
        layer.closeAll();
      }
    }, {
      icon: rdata.status ? 1 : 2
    });
  }, 'json');
}

// 尝试重启PHP
function tryRestartPHP(siteName) {
  $.post('/site/get_site_php_version', 'siteName=' + siteName, function (data) {
    var phpversion = data.phpversion;
    if (phpversion == "00") {
      return;
    }
    var php_sign = 'php';
    if (phpversion.indexOf('yum') > -1) {
      php_sign = 'php-yum';
      phpversion = phpversion.replace('yum', '');
    }
    if (phpversion.indexOf('apt') > -1) {
      php_sign = 'php-apt';
      phpversion = phpversion.replace('apt', '');
    }
    var reqData = {
      name: php_sign,
      func: 'restart'
    };
    reqData['version'] = phpversion;
    var loadT = layer.msg((lan && lan.site && t('site.site_auto_str_292') || "") + phpversion + ']...', {
      icon: 16,
      time: 0,
      shade: 0.3
    });
    $.post('/plugins/run', reqData, function (data) {
      layer.close(loadT);
      layer.msg('PHP[' + phpversion + ']' + (data.status ? lan && lan.site && t('site.site_auto_str_293') || "" : lan && lan.site && t('site.site_auto_str_294') || ""), {
        icon: data.status ? 1 : 2,
        time: 3000,
        shade: [0.3, '#000']
      });
    }, 'json');
  }, 'json');
}

// 导出所有站点
function exportAllSites() {
  var loadT = layer.load(0, {
    shade: [0.3, '#000']
  });
  $.post('/site/export_all', function (rdata) {
    layer.close(loadT);
    if (rdata.status) {
      var blob = new Blob([JSON.stringify(rdata.data, null, 4)], {
        type: "application/json"
      });
      var url = URL.createObjectURL(blob);
      var dateStr = new Date().toISOString().slice(0, 10);
      var downloadAnchor = document.createElement('a');
      downloadAnchor.setAttribute("href", url);
      downloadAnchor.setAttribute("download", "sites_backup_" + dateStr + ".json");
      document.body.appendChild(downloadAnchor);
      downloadAnchor.click();
      downloadAnchor.remove();
      URL.revokeObjectURL(url);
      layer.msg(lan && lan.site && t('site.site_auto_str_295') || "", {
        icon: 1
      });
    } else {
      layer.msg(rdata.msg, {
        icon: 2
      });
    }
  }, 'json');
}

// 导入所有站点
function importAllSites() {
  $('#import_sites_file').val('');
  $('#import_sites_file').click();
}
$(function () {
  $('#import_sites_file').on('change', function (e) {
    var file = e.target.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function (evt) {
      try {
        var importData = JSON.parse(evt.target.result);
        if (!importData.sites || importData.sites.length === 0) {
          layer.msg(lan && lan.site && t('site.site_auto_str_296') || "", {
            icon: 2
          });
          return;
        }
        var loadT = layer.msg('<p>' + (lan && lan.site && t('site.site_auto_str_297') || '以下站点存在冲突，请选择是否覆盖更新（覆盖将清除原配置信息重建）：') + '</p>', {
          icon: 16,
          time: 0,
          shade: [0.3, '#000']
        });
        $.post('/site/check_import_conflicts', {
          data: JSON.stringify(importData)
        }, function (checkData) {
          layer.close(loadT);
          if (!checkData.status) {
            layer.msg(checkData.msg, {
              icon: 2
            });
            return;
          }
          var conflicts = checkData.data.conflicts || [];
          var normal = checkData.data.normal || [];
          if (conflicts.length === 0) {
            // 没有冲突，直接导入
            layer.confirm('</b> <span style="color:red;font-size:12px;">' + t('site.import_conflict_msg', [normal.length, err.length]) + '</span>', {
              title: t('site.import_confirm'),
              icon: 3,
              btn: [lan && lan.site && t('site.site_auto_str_301') || "", lan && lan.site && t('site.site_auto_str_302') || ""]
            }, function (index) {
              layer.close(index);
              doImportAllSites(importData);
            });
          } else {
            // 有冲突，弹出选择框
            var html = '<div style="padding:20px;">';
            html += lan && lan.site && t('site.site_auto_str_303') || "";
            html += '<div style="max-height: 250px; overflow-y: auto; margin-bottom: 15px; border: 1px solid #ddd; padding: 10px;">';
            for (var i = 0; i < conflicts.length; i++) {
              var c = conflicts[i];
              html += '<div style="margin-bottom: 8px;">';
              html += '<label><input type="checkbox" class="conflict-checkbox" data-site="' + c.name + '" /> <b>' + c.name + (lan && lan.site && t('site.site_auto_str_304') || "") + c.reasons + ')</span></label>';
              html += '</div>';
            }
            html += '</div>';
            if (normal.length > 0) {
              html += (lan && lan.site && t('site.site_auto_str_305') || "") + normal.length + (lan && lan.site && t('site.site_auto_str_306') || "");
            }
            html += '</div>';
            layer.open({
              type: 1,
              title: t('site.import_result_msg', [res.success, res.skip]),
              area: '500px',
              content: html,
              btn: [t('site.confirm')],
              yes: function (index, layero) {
                var overwriteSites = [];
                layero.find('.conflict-checkbox:checked').each(function () {
                  overwriteSites.push($(this).attr('data-site'));
                });

                // 整理最终数据
                var finalSites = [];
                for (var i = 0; i < importData.sites.length; i++) {
                  var sName = importData.sites[i].site.name;
                  var isConflict = conflicts.some(function (item) {
                    return item.name === sName;
                  });
                  if (isConflict) {
                    if (overwriteSites.indexOf(sName) !== -1) {
                      importData.sites[i].overwrite = true;
                      finalSites.push(importData.sites[i]);
                    }
                    // 不勾选的冲突站点将被抛弃，不放入 finalSites
                  } else {
                    finalSites.push(importData.sites[i]);
                  }
                }
                layer.close(index);
                if (finalSites.length === 0) {
                  layer.msg(lan && lan.site && t('site.site_auto_str_310') || "", {
                    icon: 0
                  });
                  return;
                }
                importData.sites = finalSites;
                doImportAllSites(importData);
              }
            });
          }
        }, 'json');
      } catch (err) {
        layer.msg(lan && lan.site && t('site.site_auto_str_311') || "", {
          icon: 2
        });
      }
    };
    reader.readAsText(file);
  });
});
function doImportAllSites(importData) {
  var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_312') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/site/import_all', {
    data: JSON.stringify(importData)
  }, function (rdata) {
    layer.close(loadT);
    if (rdata.status) {
      var res = rdata.data;
      layer.alert(t('site.import_result_msg', [res.success, res.skip]), {
        title: t('site.import_result'),
        icon: 1
      }, function (index) {
        layer.close(index);
        getWeb(1); // 重新加载列表
      });
    } else {
      layer.msg(rdata.msg, {
        icon: 2
      });
    }
  }, 'json');
}