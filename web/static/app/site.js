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
        var status = (lan && lan.site && t('site.site_auto_str_2') || "") + list[i].id + ",'" + list[i].name + (lan && lan.site && t('site.site_auto_str_3') || "");
      } else {
        var status = (lan && lan.site && t('site.site_auto_str_4') || "") + list[i].id + ",'" + list[i].name + (lan && lan.site && t('site.site_auto_str_5') || "");
        trClass = ' class="danger-row"';
      }

      //是否有备份
      if (list[i].backup_count > 0) {
        var backup = "<a href='javascript:;' class='btlink' onclick=\"getBackup(" + list[i].id + (lan && lan.site && t('site.site_auto_str_6') || "");
      } else {
        var backup = "<a href='javascript:;' class='btlink' onclick=\"getBackup(" + list[i].id + (lan && lan.site && t('site.site_auto_str_7') || "");
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
      var ssl_text = list[i].ssl_days == -1 ? "<a class='btlink' href='javascript:;' onclick=\"webEdit(" + list[i].id + ",'" + list[i].name + "','" + list[i].edate + "','" + list[i].add_time + (lan && lan.site && t('site.site_auto_str_10') || "") : list[i].ssl_days < 10 ? "<a class='btlink' href='javascript:;' onclick=\"webEdit(" + list[i].id + ",'" + list[i].name + "','" + list[i].edate + "','" + list[i].add_time + (lan && lan.site && t('site.site_auto_str_11') || "") + list[i].ssl_days + (lan && lan.site && t('site.site_auto_str_12') || "") : "<a class='btlink' href='javascript:;' onclick=\"webEdit(" + list[i].id + ",'" + list[i].name + "','" + list[i].edate + "','" + list[i].add_time + (lan && lan.site && t('site.site_auto_str_13') || "") + list[i].ssl_days + (lan && lan.site && t('site.site_auto_str_14') || "");
      var daily_traffic = toSize(list[i].daily_traffic);
      var add_time_str = list[i].add_time && list[i].add_time.length >= 10 ? list[i].add_time.substring(0, 10) : list[i].add_time;
      body = "<tr" + trClass + "><td><input type='checkbox' name='id' title='" + list[i].name + "' onclick='checkSelect();' value='" + list[i].id + "'></td>\
					<td><a class='btlink webtips' href='javascript:;' onclick=\"webEdit(" + list[i].id + ",'" + list[i].name + "','" + list[i].edate + "','" + list[i].add_time + "')\" title='" + list[i].name + "'>" + shortwebname + "</td>\
					<td>" + status + "</td>\
					<td>" + backup + (lan && lan.site && t('site.site_auto_str_15') || "") + list[i].path + "' href=\"javascript:openPath('" + data.data[i].path + "');\">" + shortpath + "</a></td>\
					<td>" + add_time_str + "</td>\
					<td>" + daily_traffic + "</td>\
					<td>" + php_text + "</td>\
					<td id='ssl_state_" + idname + "'>" + ssl_text + "</td>\
					<td><a class='btlink setTimes' id='site_" + list[i].id + "' data-ids='" + list[i].id + "'>" + web_end_time + "</a></td>\
					<td><a class='btlinkbed' href='javascript:;' data-id='" + list[i].id + "'>" + list[i].ps + "</a></td>\
					<td style='text-align:right; color:#bbb'>\
					<a href='javascript:;' class='btlink' onclick=\"webEdit(" + list[i].id + ",'" + list[i].name + "','" + list[i].edate + "','" + list[i].add_time + (lan && lan.site && t('site.site_auto_str_16') || "") + list[i].id + "','" + list[i].name + (lan && lan.site && t('site.site_auto_str_17') || "");
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
      body = lan && lan.site && t('site.site_auto_str_20') || "";
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
      $(this).hide().after("<input class='baktext' type='text' data-id='" + dataid + "' data-page='" + page + "' name='bak' value='" + databak + (lan && lan.site && t('site.site_auto_str_21') || ""));
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
                    <span class='tname'>" + t('site.domain') + (lan && lan.site && t('site.site_auto_str_28') || "") + www['dir'] + "/' placeholder='" + www['dir'] + "' style='width:458px' />\
                	<span class='glyphicon glyphicon-folder-open cursor' onclick='changePath(\"inputPath\")'></span>\
                </div>\
                </div>\
				" + php_version + (lan && lan.site && t('site.site_auto_str_29') || "")
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
						<input type='checkbox' name='userini' id='userini'" + user_ini_checked + (lan && lan.site && t('site.site_auto_str_32') || "") + logs_checked + (lan && lan.site && t('site.site_auto_str_33') || "") + site_path + "' name='webdir' id='inputPath'>\
						<span onclick='changePath(&quot;inputPath&quot;)' class='glyphicon glyphicon-folder-open cursor mr20'></span>\
						<button class='btn btn-success btn-sm' onclick='setSitePath(" + id + (lan && lan.site && t('site.site_auto_str_34') || "") + opt + "</select>\
						<button class='btn btn-success btn-sm' onclick='setSiteRunPath(" + id + (lan && lan.site && t('site.site_auto_str_35') || "") + '<div class="user_pw_tit" style="margin-top: -8px;padding-top: 11px;">' + (lan && lan.site && t('site.site_auto_str_36') || "") + '<span class="btswitch-p"><input ' + (data.pass ? 'checked' : '') + ' class="btswitch btswitch-ios" id="pathSafe" type="checkbox">' + '<label class="btswitch-btn phpmyadmin-btn" for="pathSafe" onclick="pathSafe(' + id + ')"></label>' + '</span>' + '</div>' + '<div class="user_pw" style="margin-top: 10px;display:' + (data.pass ? 'block;' : 'none;') + '">' + (lan && lan.site && t('site.site_auto_str_37') || "") + (lan && lan.site && t('site.site_auto_str_38') || "") + (lan && lan.site && t('site.site_auto_str_39') || "") + '<p><button class="btn btn-success btn-sm" onclick="setPathSafe(' + id + (lan && lan.site && t('site.site_auto_str_40') || "") + '</div>' + '</div>';
    $("#webedit-con").html(content);
    $("#userini").on('change', function () {
      $.post('/site/set_dir_user_ini', {
        'path': site_path,
        'run_path': run_path
      }, function (userini) {
        layer.msg(data.msg + (lan && lan.site && t('site.site_auto_str_41') || ""), {
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
			<br><br><button class='btn btn-success btn-sm' onclick='SetSitePs(" + id + (lan && lan.site && t('site.site_auto_str_46') || "");
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
						<button type='button' class='btn btn-success btn-sm pull-right' onclick='setIndexList(" + id + ")' style='margin: 70px 130px 0px 0px;'>" + t('public.save') + (lan && lan.site && t('site.site_auto_str_47') || "");
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
  var thtml = lan && lan.site && t('site.site_auto_str_50') || "";
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
								<button type='button' class='btn btn-success btn-sm pull-right' style='margin:30px 35px 0 0' onclick=\"domainAdd(" + id + ",'" + name + (lan && lan.site && t('site.site_auto_str_54') || "") + t('site.domain') + (lan && lan.site && t('site.site_auto_str_55') || "") + echoHtml + "</tbody>\
								</table>\
							</div>";
    $("#webedit-con").html(bodyHtml);
    if (msg != undefined) {
      layer.msg(msg, {
        icon: status ? 1 : 5
      });
    }
    var placeholder = lan && lan.site && t('site.site_auto_str_56') || "";
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
      var ftpdown = "<a class='btlink' href='/files/download?filename=" + frdata.data[i].filename + "&name=" + frdata.data[i].name + (lan && lan.site && t('site.site_auto_str_62') || "");
      body += "<tr><td><span class='glyphicon glyphicon-file'></span>" + frdata.data[i].name + "</td>\
					<td>" + toSize(frdata.data[i].size) + "</td>\
					<td>" + frdata.data[i].add_time + "</td>\
					<td class='text-right' style='color:#ccc'>" + ftpdown + "<a class='btlink' href='javascript:;' onclick=\"webBackupDelete('" + frdata.data[i].id + "'," + id + (lan && lan.site && t('site.site_auto_str_63') || "");
    }
    var ftpdown = '';
    frdata.page = frdata.page.replace(/'/g, '"').replace(/getBackup\(/g, "getBackup(" + id + ",0,");
    if (name == 0) {
      var sBody = (lan && lan.site && t('site.site_auto_str_64') || "") + body + "</tbody>\
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
				<button class='btn btn-default btn-sm' style='margin-right:10px' type='button' onclick=\"webBackup('" + frdata['site']['id'] + "','" + frdata['site']['name'] + (lan && lan.site && t('site.site_auto_str_66') || "") + body + "</tbody>\
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
    var opt = lan && lan.site && t('site.site_auto_str_68') || "";
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
      content: (lan && lan.site && t('site.site_auto_str_70') || "") + opt + (lan && lan.site && t('site.site_auto_str_71') || "")
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
      content: (lan && lan.site && t('site.site_auto_str_75') || "") + opt + (lan && lan.site && t('site.site_auto_str_76') || ""),
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
				<p class='bgw' onclick=\"domainEdit(" + id + ",'" + website + (lan && lan.site && t('site.site_auto_str_80') || "") + id + (lan && lan.site && t('site.site_auto_str_81') || "") + id + (lan && lan.site && t('site.site_auto_str_82') || "") + id + (lan && lan.site && t('site.site_auto_str_83') || "") + website + (lan && lan.site && t('site.site_auto_str_84') || "") + id + (lan && lan.site && t('site.site_auto_str_85') || "") + website + (lan && lan.site && t('site.site_auto_str_86') || "") + id + ",'" + website + "')\">SSL</p>\
				<p onclick=\"phpVersion('" + website + (lan && lan.site && t('site.site_auto_str_87') || "") + website + (lan && lan.site && t('site.site_auto_str_88') || "") + website + (lan && lan.site && t('site.site_auto_str_89') || "") + (hasProxy ? "<span style='color:red; font-size:12px; margin-left:3px'>●</span>" : "") + "</p>\
				<p id='site_" + id + "' onclick=\"security('" + id + "','" + website + (lan && lan.site && t('site.site_auto_str_90') || "") + id + "' onclick=\"getSiteLogs('" + website + (lan && lan.site && t('site.site_auto_str_91') || "") + id + "' onclick=\"getSiteErrorLogs('" + website + (lan && lan.site && t('site.site_auto_str_92') || ""),
    success: function () {
      //域名输入提示
      var placeholder = lan && lan.site && t('site.site_auto_str_93') || "";
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
    var mbody = '<div>' + (lan && lan.site && t('site.site_auto_str_100') || "") + rdata.fix + '" style="margin-left: 5px;width: 425px;height: 30px;margin-right:10px;' + (rdata.status ? 'background-color: #eee;' : '') + (lan && lan.site && t('site.site_auto_str_101') || "") + (rdata.status ? 'readonly' : '') + '></p>' + (lan && lan.site && t('site.site_auto_str_102') || "") + rdata.domains + '" style="margin-left: 5px;width: 425px;height: 30px;margin-right:10px;' + (rdata.status ? 'background-color: #eee;' : '') + (lan && lan.site && t('site.site_auto_str_103') || "") + (rdata.status ? 'readonly' : '') + '></p>' + '<div class="label-input-group ptb10"><label style="font-weight:normal"><input type="checkbox" name="sec_status" onclick="setSecurity(\'' + name + '\',' + id + ')" ' + (rdata.status ? 'checked' : '') + (lan && lan.site && t('site.site_auto_str_104') || "") + '<div class="label-input-group ptb10"><label style="font-weight:normal"><input type="checkbox" name="sec_none_status" onclick="setSecurity(\'' + name + '\',' + id + ')" ' + (rdata.none ? 'checked' : '') + (lan && lan.site && t('site.site_auto_str_105') || "") + '<ul class="help-info-text c7 ptb10">' + (lan && lan.site && t('site.site_auto_str_106') || "") + (lan && lan.site && t('site.site_auto_str_107') || "") + (lan && lan.site && t('site.site_auto_str_108') || "") + '</ul>' + '</div>';
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
      echoHtml += "<tr><td>" + rdata.binding[i].domain + "</td><td>" + rdata.binding[i].port + "</td><td>" + rdata.binding[i].path + "</td><td class='text-right'><a class='btlink' href='javascript:setDirRewrite(" + rdata.binding[i].id + (lan && lan.site && t('site.site_auto_str_109') || "") + rdata.binding[i].id + "," + id + (lan && lan.site && t('site.site_auto_str_110') || "");
    }
    var dirList = '';
    for (var n = 0; n < rdata.dirs.length; n++) {
      dirList += "<option value='" + rdata.dirs[n] + "'>" + rdata.dirs[n] + "</option>";
    }
    var body = "<div class='dirBinding c5'>" + (lan && lan.site && t('site.site_auto_str_111') || "") + (lan && lan.site && t('site.site_auto_str_112') || "") + dirList + "</select>" + "<button class='btn btn-success btn-sm' onclick='addDirBinding(" + id + (lan && lan.site && t('site.site_auto_str_113') || "") + "</div>" + "<div class='divtable mtb15' style='height:540px;overflow:auto'><table class='table table-hover' width='100%' style='margin-bottom:0'>" + (lan && lan.site && t('site.site_auto_str_114') || "") + "<tbody id='checkDomain'>" + echoHtml + "</tbody>" + "</table></div>";
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
					<textarea class='bt-input-text mtb15' style='height: 260px; width: 470px; line-height:18px;padding:5px;' id='rewriteBody'>" + rdata.data + (lan && lan.site && t('site.site_auto_str_116') || "");
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
      content: (lan && lan.site && t('site.site_auto_str_122') || "") + keep_path_ht + (lan && lan.site && t('site.site_auto_str_123') || "") + (obj.type == 'domain' ? 'selected ="selected"' : "") + (lan && lan.site && t('site.site_auto_str_124') || "") + (obj.type == 'path' ? 'selected ="selected"' : "") + (lan && lan.site && t('site.site_auto_str_125') || "") + (obj.r_type == '301' ? 'selected ="selected"' : "") + " >301</option>\
						<option value='302' " + (obj.r_type == '302' ? 'selected ="selected"' : "") + (lan && lan.site && t('site.site_auto_str_126') || "") + obj.from + (lan && lan.site && t('site.site_auto_str_127') || "") + obj.to + "'>\
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
				<textarea style='height: 320px; width: 445px; margin-left: 20px; line-height:18px' id='configRedirectBody'>" + res.data.result + (lan && lan.site && t('site.site_auto_str_129') || "");
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
  var body = (lan && lan.site && t('site.site_auto_str_135') || "") + siteName + (lan && lan.site && t('site.site_auto_str_136') || "");
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
						<span data-index="5" onclick="to301(\'' + siteName + '\', 3, \'' + item.id + (lan && lan.site && t('site.site_auto_str_141') || "") + siteName + '\', 2, \'' + item.id + (lan && lan.site && t('site.site_auto_str_142') || "");
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
      content: lan && lan.site && t('site.site_auto_str_148') || "",
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
			<textarea style='height: 320px; width: 445px; margin-left: 20px; line-height:18px' id='configProxyBody'>" + res.data.result + (lan && lan.site && t('site.site_auto_str_154') || "");
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
  var body = (lan && lan.site && t('site.site_auto_str_162') || "") + siteName + (lan && lan.site && t('site.site_auto_str_163') || "");
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
      var openCache = '<span  data-index="' + i + (lan && lan.site && t('site.site_auto_str_164') || "");
      if (item['open_cache'] == 'on') {
        openCache = '<span  data-index="' + i + (lan && lan.site && t('site.site_auto_str_165') || "");
      }
      let tmp = '<tr>\
				<td>' + item.name + '</td>\
				<td>' + item.from + '</td>\
				<td>' + item.to + '</td>\
				<td>' + openCache + '</td>\
				<td>' + switchProxy + '</td>\
				<td>\
				   <span data-index="' + i + (lan && lan.site && t('site.site_auto_str_166') || "") + i + (lan && lan.site && t('site.site_auto_str_167') || "") + i + (lan && lan.site && t('site.site_auto_str_168') || "");
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
				<td style="text-align: right;"><a onclick="setCertSsl(\'' + rdata[i].subject + '\',\'' + siteName + (lan && lan.site && t('site.site_auto_str_170') || "") + rdata[i].subject + (lan && lan.site && t('site.site_auto_str_171') || "");
    }
    var txt = (lan && lan.site && t('site.site_auto_str_172') || "") + tbody + '</tbody>\
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
  var sslHtml = (lan && lan.site && t('site.site_auto_str_176') || "") + id + ',\'' + siteName + (lan && lan.site && t('site.site_auto_str_177') || "") + id + ',\'' + siteName + '\')">ACME</span>\
					<span id="ssl_admin" onclick="sslAdmin(\'' + siteName + (lan && lan.site && t('site.site_auto_str_178') || "") + '<div class="ss-text pull-right mr30" style="position: relative;top:-4px">\
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
    content: (lan && lan.site && t('site.site_auto_str_188') || "") + data['name'] + "</option>\
			        </select>\
			    </div>\
			</div>\
			<div class='line' id='dnsapi_option'>\
			    " + fields_html + (lan && lan.site && t('site.site_auto_str_189') || "") + data['title'] + (lan && lan.site && t('site.site_auto_str_190') || ""),
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
  var now = (lan && lan.site && t('site.site_auto_str_191') || "") + siteName + (lan && lan.site && t('site.site_auto_str_192') || "");
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
      var issuer_o = rdata['cert_data']['issuer_o'] || lan && lan.site && t('site.site_auto_str_194') || "";
      var issuer = rdata['cert_data']['issuer'] || lan && lan.site && t('site.site_auto_str_195') || "";
      var domains = rdata['cert_data']['dns'].join("、");
      var cert_data = (lan && lan.site && t('site.site_auto_str_196') || "") + issuer_o + (lan && lan.site && t('site.site_auto_str_197') || "") + issuer + (lan && lan.site && t('site.site_auto_str_198') || "") + rdata['cert_data']['endtime'] + (lan && lan.site && t('site.site_auto_str_199') || "") + domains + (lan && lan.site && t('site.site_auto_str_200') || "") + siteName + "')\">\
				</span></div>\
			</div>";
      $(".ssl_state_info").html(cert_data);
      $(".ssl_state_info").css('display', 'block');
    }
    if (rdata.key == false) {
      rdata.key = '';
    } else {
      $(".ssl-btn").append('<button style=\'margin-left:3px;\' class="btn btn-success btn-sm" onclick="deleteSSL(\'now\',' + id + ',\'' + siteName + (lan && lan.site && t('site.site_auto_str_201') || ""));
    }
    if (rdata.csr == false) {
      rdata.csr = '';
    }
    $("#key").val(rdata.key);
    $("#csr").val(rdata.csr);
    $("#toHttps").attr('checked', rdata.httpTohttps);
    if (rdata.status) {
      $('.warning_info').css('display', 'none');
      $(".ssl-btn").append("<button class='btn btn-success btn-sm' onclick=\"ocSSL('close_ssl_conf','" + siteName + (lan && lan.site && t('site.site_auto_str_202') || ""));
      $(".ssl-btn").append("<button class='btn btn-success btn-sm' onclick=\"renewSSL('acme'," + id + ",'" + siteName + (lan && lan.site && t('site.site_auto_str_203') || ""));
      $('#now_ssl').html(lan && lan.site && t('site.site_auto_str_204') || "");
    } else {
      $('.warning_info').css('display', 'block');
      $('#now_ssl').html(lan && lan.site && t('site.site_auto_str_205') || "");
    }
    if (typeof callback != 'undefined') {
      callback(rdata);
    }
  }, 'json');
}
function opSSLAcme(type, id, siteName, callback) {
  var acme = lan && lan.site && t('site.site_auto_str_206') || "";
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
    var acme = (lan && lan.site && t('site.site_auto_str_207') || "") + rdata.key + (lan && lan.site && t('site.site_auto_str_208') || "") + rdata.csr + '</textarea></div>\
				</div>\
				<div class="ssl-btn pull-left mtb15" style="width:100%">\
					<button class="btn btn-success btn-sm" onclick="deploySSL(\'acme\',' + id + ',\'' + siteName + (lan && lan.site && t('site.site_auto_str_209') || "") + id + ',\'' + siteName + (lan && lan.site && t('site.site_auto_str_210') || "");
    $(".tab-con").html(acme);
    if (rdata['cert_data']) {
      var issuer_o = rdata['cert_data']['issuer_o'] || lan && lan.site && t('site.site_auto_str_211') || "";
      var issuer = rdata['cert_data']['issuer'] || lan && lan.site && t('site.site_auto_str_212') || "";
      var domains = rdata['cert_data']['dns'].join("、");
      var cert_data = (lan && lan.site && t('site.site_auto_str_213') || "") + issuer_o + (lan && lan.site && t('site.site_auto_str_214') || "") + issuer + (lan && lan.site && t('site.site_auto_str_215') || "") + rdata['cert_data']['endtime'] + (lan && lan.site && t('site.site_auto_str_216') || "") + domains + "</span></div>\
			</div>";
      $(".ssl_state_info").html(cert_data);
      $(".ssl_state_info").css('display', 'block');
    }
  }, 'json');
}
function opSSLLet(type, id, siteName, callback) {
  var lets = lan && lan.site && t('site.site_auto_str_217') || "";
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
    var lets = (lan && lan.site && t('site.site_auto_str_218') || "") + rdata.key + (lan && lan.site && t('site.site_auto_str_219') || "") + rdata.csr + '</textarea></div>\
				</div>\
				<div class="ssl-btn pull-left mtb15" style="width:100%">\
					<button class="btn btn-success btn-sm" onclick="deploySSL(\'lets\',' + id + ',\'' + siteName + (lan && lan.site && t('site.site_auto_str_220') || "") + id + ',\'' + siteName + (lan && lan.site && t('site.site_auto_str_221') || "") + id + ',\'' + siteName + (lan && lan.site && t('site.site_auto_str_222') || "");
    $(".tab-con").html(lets);
    if (rdata['cert_data']) {
      var issuer_o = rdata['cert_data']['issuer_o'] || lan && lan.site && t('site.site_auto_str_223') || "";
      var issuer = rdata['cert_data']['issuer'] || lan && lan.site && t('site.site_auto_str_224') || "";
      var domains = rdata['cert_data']['dns'].join("、");
      var cert_data = (lan && lan.site && t('site.site_auto_str_225') || "") + issuer_o + (lan && lan.site && t('site.site_auto_str_226') || "") + issuer + (lan && lan.site && t('site.site_auto_str_227') || "") + rdata['cert_data']['endtime'] + (lan && lan.site && t('site.site_auto_str_228') || "") + domains + "</span></div>\
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
        data += (lan && lan.site && t('site.site_auto_str_232') || "") + rdata.out[i].Domain + "</p>" + (lan && lan.site && t('site.site_auto_str_233') || "") + rdata.out[i].Type + "</p>" + (lan && lan.site && t('site.site_auto_str_234') || "") + rdata.out[i].Detail + "</p>" + "<hr />";
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
      layer.msg(lan && lan.site && t('site.site_auto_str_235') || "", {
        icon: 1,
        time: 5000
      });
    }
    $(".tab-nav .on").click();
  }, 'json');
}

//生成SSL
function newSSL(siteName, id, domains) {
  showSpeedWindow(lan && lan.site && t('site.site_auto_str_236') || "", 'site.get_let_logs', function (layers, index) {
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
          list += lan && lan.site && t('site.site_auto_str_241') || "";
        } else {
          list += lan && lan.site && t('site.site_auto_str_242') || "";
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
      var versionSelect = lan && lan.site && t('site.site_auto_str_247') || "";
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
          var msgerr = lan && lan.site && t('site.site_auto_str_249') || "";
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
  var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_250') || "", {
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
      var php_show_text = php_version == '00' ? lan && lan.site && t('site.site_auto_str_251') || "" : php_version.length == 2 ? php_version.substring(0, 1) + '.' + php_version.substring(1) : php_version;
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
    var bodyContent = (lan && lan.site && t('site.site_auto_str_253') || "") + siteName + (lan && lan.site && t('site.site_auto_str_254') || "") + currentVersionText + (lan && lan.site && t('site.site_auto_str_255') || "") + optionsHtml + (lan && lan.site && t('site.site_auto_str_256') || "") + siteName + "', '" + currentVersionText + (lan && lan.site && t('site.site_auto_str_257') || "");
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
  var confirmMsg = (lan && lan.site && t('site.site_auto_str_259') || "") + siteName + (lan && lan.site && t('site.site_auto_str_260') || "") + currentVersionText + (lan && lan.site && t('site.site_auto_str_261') || "") + newVersionText + (lan && lan.site && t('site.site_auto_str_262') || "");
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
  var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_267') || "", {
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
          'mvc': lan && lan.site && t('site.site_auto_str_270') || "",
          'phpcms': 'phpcms (PHPCMS)',
          'phpwind': 'phpwind (PHPWind)',
          'sablog': 'sablog (SaBlog-X)',
          'seacms': lan && lan.site && t('site.site_auto_str_271') || "",
          'shopex': 'shopex (ShopEx)',
          'thinkphp': 'thinkphp (ThinkPHP)',
          'typecho': 'typecho (Typecho)',
          'whmcs': 'whmcs (WHMCS)',
          'wmcms': lan && lan.site && t('site.site_auto_str_272') || "",
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
						<textarea class='bt-input-text' style='height: 260px; width: 740px; line-height:18px;margin-top:10px;padding:5px;' id='rewriteBody'>" + centent + (lan && lan.site && t('site.site_auto_str_273') || "");
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
    title: lan && lan.site && t('site.site_auto_str_275') || "",
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
      content: (lan && lan.site && t('site.site_auto_str_281') || "") + list + '</tbody>\
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
    layer.msg(lan && lan.site && t('site.site_auto_str_282') || "", {
      icon: 2
    });
    return;
  }
  layer.confirm(lan && lan.site && t('site.site_auto_str_283') || "", {
    title: (lan && lan.site && t('site.site_auto_str_284') || "") + name + '】'
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
    layer.msg(lan && lan.site && t('site.site_auto_str_285') || "", {
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
        var loadT = layer.msg(lan && lan.site && t('site.site_auto_str_297') || "", {
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
            layer.confirm((lan && lan.site && t('site.site_auto_str_298') || "") + normal.length + (lan && lan.site && t('site.site_auto_str_299') || ""), {
              title: lan && lan.site && t('site.site_auto_str_300') || "",
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
              title: lan && lan.site && t('site.site_auto_str_307') || "",
              area: '500px',
              content: html,
              btn: [lan && lan.site && t('site.site_auto_str_308') || "", lan && lan.site && t('site.site_auto_str_309') || ""],
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
      layer.alert((lan && lan.site && t('site.site_auto_str_313') || "") + res.success + (lan && lan.site && t('site.site_auto_str_314') || "") + res.skip + (lan && lan.site && t('site.site_auto_str_315') || ""), {
        title: lan && lan.site && t('site.site_auto_str_316') || "",
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