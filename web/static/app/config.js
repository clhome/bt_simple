/** op **/
// $(".set-submit").on('click', function(){
// 	var data = $("#set_config").serialize();
// 	layer.msg('正在保存配置...',{icon:16,time:0,shade: [0.3, '#000']});
// 	$.post('/config/set',data,function(rdata){
// 		layer.closeAll();
// 		layer.msg(rdata.msg,{icon:rdata.status?1:2});
// 		if(rdata.status){
// 			setTimeout(function(){
// 				window.location.href = ((window.location.protocol.indexOf('https') != -1)?'https://':'http://') + rdata.data.host + window.location.pathname;
// 			},2500);
// 		}
// 	},'json');
// });

$('input[name="webname"]').on('change', function () {
  var webname = $(this).val();
  $('.btn_webname').removeAttr('disabled');
  $('.btn_webname').off().on('click', function () {
    $.post('/setting/set_webname', 'webname=' + webname, function (rdata) {
      showMsg(rdata.msg, function () {
        window.location.reload();
      }, {
        icon: rdata.status ? 1 : 2
      }, 2000);
    }, 'json');
  });
});
$('input[name="host_ip"]').on('change', function () {
  var host_ip = $(this).val();
  $('.btn_host_ip').removeAttr('disabled');
  $('.btn_host_ip').off().on('click', function () {
    $.post('/setting/set_ip', 'host_ip=' + host_ip, function (rdata) {
      showMsg(rdata.msg, function () {
        window.location.reload();
      }, {
        icon: rdata.status ? 1 : 2
      }, 2000);
    }, 'json');
  });
});
$('input[name="port"]').on('change', function () {
  var port = $(this).val();
  var old_port = $(this).data('port');
  $('.btn_port').removeAttr('disabled');
  $('.btn_port').off().on('click', function () {
    $.post('/setting/set_port', 'port=' + port, function (rdata) {
      showMsg(rdata.msg, function () {
        window.location.href = window.location.href.replace(old_port, port);
        // window.location.reload();
      }, {
        icon: rdata.status ? 1 : 2
      }, 5000);
    }, 'json');
  });
});
$('input[name="sites_path"]').on('change', function () {
  var sites_path = $(this).val();
  $('.btn_sites_path').removeAttr('disabled');
  $('.btn_sites_path').off().on('click', function () {
    $.post('/setting/set_www_dir', 'sites_path=' + sites_path, function (rdata) {
      showMsg(rdata.msg, function () {
        window.location.reload();
      }, {
        icon: rdata.status ? 1 : 2
      }, 2000);
    }, 'json');
  });
});
$('input[name="backup_path"]').on('change', function () {
  var backup_path = $(this).val();
  $('.btn_backup_path').removeAttr('disabled');
  $('.btn_backup_path').off().on('click', function () {
    $.post('/setting/set_backup_dir', 'backup_path=' + backup_path, function (rdata) {
      showMsg(rdata.msg, function () {
        window.location.reload();
      }, {
        icon: rdata.status ? 1 : 2
      }, 2000);
    }, 'json');
  });
});
$('input[name="bind_domain"]').on('change', function () {
  var domain = $(this).val();
  $('.btn_bind_domain').removeAttr('disabled');
  $('.btn_bind_domain').off().on('click', function () {
    $.post('/setting/set_panel_domain', 'domain=' + domain, function (rdata) {
      if (domain == '') {
        // 清空域名直接重启跳转
        showMsg(rdata.msg, function () {
          window.location.href = rdata.data;
        }, {
          icon: rdata.status ? 1 : 2
        }, 5000);
        return;
      }
      if (rdata.status) {
        var new_url = rdata.data;
        // 弹出一个精美弹窗，提示用户保存域名并确认重启
        layer.open({
          type: 1,
          title: lan && lan.config && lan.config.config_auto_str_1 || "",
          area: ['520px', '280px'],
          closeBtn: 1,
          shadeClose: false,
          content: (lan && lan.config && lan.config.config_auto_str_2 || "") + new_url + (lan && lan.config && lan.config.config_auto_str_3 || ""),
          success: function (layero, index) {
            // 鼠标悬停变色效果
            $('#new-domain-box').on('mouseenter', function () {
              $(this).css('background', '#eef9ef');
            }).on('mouseleave', function () {
              $(this).css('background', '#f8f9fa');
            });

            // 点击复制事件
            $('#new-domain-box').on('click', function () {
              copyTextToClipboard(new_url);
            });

            // 确认并重启
            $('#btn-reboot-confirm').on('click', function () {
              layer.close(index);
              var loadT = layer.load(2);
              $.post('/system/restart', '', function () {
                layer.close(loadT);
                var count = 10;
                var msgBox = layer.msg((lan && lan.config && lan.config.config_auto_str_4 || "") + count + (lan && lan.config && lan.config.config_auto_str_5 || ""), {
                  icon: 16,
                  time: 0,
                  shade: [0.3, '#000']
                });
                var timer = setInterval(function () {
                  count--;
                  if (count <= 0) {
                    clearInterval(timer);
                    layer.close(msgBox);
                    window.location.href = new_url;
                  } else {
                    $('#restart-countdown').text(count);
                  }
                }, 1000);
              });
            });
          }
        });
      } else {
        layer.msg(rdata.msg, {
          icon: 2
        });
      }
    }, 'json');
  });
});

// 兼容性良好的一键复制函数
function copyTextToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function () {
      layer.msg(lan && lan.config && lan.config.config_auto_str_6 || "", {
        icon: 1,
        time: 1000
      });
    }).catch(function () {
      fallbackCopyText(text);
    });
  } else {
    fallbackCopyText(text);
  }
}
function fallbackCopyText(text) {
  var textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.style.position = "fixed";
  textArea.style.top = "0";
  textArea.style.left = "0";
  textArea.style.width = "2em";
  textArea.style.height = "2em";
  textArea.style.padding = "0";
  textArea.style.border = "none";
  textArea.style.outline = "none";
  textArea.style.boxShadow = "none";
  textArea.style.background = "transparent";
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();
  try {
    var successful = document.execCommand('copy');
    if (successful) {
      layer.msg(lan && lan.config && lan.config.config_auto_str_7 || "", {
        icon: 1,
        time: 1000
      });
    } else {
      layer.msg(lan && lan.config && lan.config.config_auto_str_8 || "", {
        icon: 2
      });
    }
  } catch (err) {
    layer.msg(lan && lan.config && lan.config.config_auto_str_9 || "", {
      icon: 2
    });
  }
  document.body.removeChild(textArea);
}

// SSL 申请/配置成功后的弹窗，支持点击一键复制，点击确定重启面板后进行 10 秒倒计时跳转 https 地址
function showSSLSuccessWindow(new_url, title) {
  title = title || lan && lan.config && lan.config.config_auto_str_10 || "";
  // 自动修复 127.0.0.1 和 0.0.0.0 为当前主机的实际域名/IP，以确保在任何环境下均可平顺访问
  if (new_url.indexOf('127.0.0.1') != -1 || new_url.indexOf('0.0.0.0') != -1) {
    new_url = new_url.replace(/127\.0\.0\.1|0\.0\.0\.0/, window.location.hostname);
  }
  layer.open({
    type: 1,
    title: title,
    area: ['520px', '280px'],
    closeBtn: 1,
    shadeClose: false,
    content: (lan && lan.config && lan.config.config_auto_str_11 || "") + new_url + (lan && lan.config && lan.config.config_auto_str_12 || ""),
    success: function (layero, index) {
      // 鼠标悬停变色效果
      $('#ssl-domain-box').on('mouseenter', function () {
        $(this).css('background', '#eef9ef');
      }).on('mouseleave', function () {
        $(this).css('background', '#f8f9fa');
      });

      // 点击复制事件
      $('#ssl-domain-box').on('click', function () {
        copyTextToClipboard(new_url);
      });

      // 确认并重启
      $('#btn-ssl-reboot-confirm').on('click', function () {
        layer.close(index);
        var loadT = layer.load(2);
        $.post('/system/restart', '', function () {
          layer.close(loadT);
          var count = 10;
          var msgBox = layer.msg((lan && lan.config && lan.config.config_auto_str_13 || "") + count + (lan && lan.config && lan.config.config_auto_str_14 || ""), {
            icon: 16,
            time: 0,
            shade: [0.3, '#000']
          });
          var timer = setInterval(function () {
            count--;
            if (count <= 0) {
              clearInterval(timer);
              layer.close(msgBox);
              window.location.href = new_url;
            } else {
              $('#restart-countdown').text(count);
            }
          }, 1000);
        });
      });
    }
  });
}
$('input[name="bind_ssl"]').on('click', function () {
  var panel_ssl = $(this).prop("checked");
  $(this).prop("checked", !panel_ssl);

  //开启证书
  if (panel_ssl) {
    // <option value="1">ACME</option>
    layer.open({
      type: 1,
      closeBtn: 1,
      title: lan && lan.config && lan.config.config_auto_str_15 || "",
      area: ['600px', '440px'],
      btn: [lan && lan.config && lan.config.config_auto_str_16 || ""],
      maxmin: false,
      shadeClose: true,
      content: lan && lan.config && lan.config.config_auto_str_17 || "",
      yes: function () {
        var cert_type = $('select[name=cert_type]').val();
        $.post('/setting/set_panel_local_ssl', {
          'cert_type': cert_type
        }, function (rdata) {
          if (rdata.status) {
            showSSLSuccessWindow(rdata.data, lan && lan.config && lan.config.config_auto_str_18 || "");
          } else {
            layer.msg(rdata.msg, {
              icon: 2
            });
          }
        }, 'json');
      }
    });
  } else {
    //关闭SSL
    layer.open({
      type: 1,
      closeBtn: 1,
      title: lan && lan.config && lan.config.config_auto_str_19 || "",
      area: ['480px', '280px'],
      btn: [lan && lan.config && lan.config.config_auto_str_20 || "", lan && lan.config && lan.config.config_auto_str_21 || ""],
      shadeClose: true,
      content: lan && lan.config && lan.config.config_auto_str_22 || "",
      yes: function (index) {
        var val = $('#prompt_input_box').val();
        if (val != (lan && lan.config && lan.config.config_auto_str_23 || "")) {
          layer.msg(lan && lan.config && lan.config.config_auto_str_24 || "");
          return;
        }
        $.post('/setting/close_panel_ssl', {}, function (rdata) {
          var to_http = window.location.href.replace('https', 'http');
          showMsg(rdata.msg, function () {
            if (rdata.status) {
              window.location.href = to_http;
            }
          }, {
            icon: rdata.status ? 1 : 2
          }, 5000);
        }, 'json');
      }
    });
  }
});

/** op **/

// VIP -- start
function setVipInfo() {
  layer.open({
    type: 1,
    area: "400px",
    title: lan && lan.config && lan.config.config_auto_str_25 || "",
    closeBtn: 1,
    shift: 5,
    btn: [lan && lan.config && lan.config.config_auto_str_26 || "", lan && lan.config && lan.config.config_auto_str_27 || ""],
    shadeClose: false,
    content: lan && lan.config && lan.config.config_auto_str_28 || "",
    yes: function (index) {
      var pdata = {};
      pdata['username'] = $('input[name="username"]').val();
      pdata['password'] = $('input[name="password"]').val();
      if (pdata['username'] == '') {
        layer.msg(lan && lan.config && lan.config.config_auto_str_29 || "", {
          icon: 2
        });
        return false;
      }
      if (pdata['password'] == '') {
        layer.msg(lan && lan.config && lan.config.config_auto_str_30 || "", {
          icon: 2
        });
        return false;
      }
      $.post('/vip/login', {
        'username': pdata['username'],
        'password': pdata['password']
      }, function (rdata) {
        showMsg(rdata.msg, function () {
          if (rdata.status) {
            layer.close(index);
          }
        }, {
          icon: rdata.status ? 1 : 2
        }, 2000);
      }, 'json');
    }
  });
}
// VIP -- end

//关闭面板
function closePanel() {
  layer.confirm(lan && lan.config && lan.config.config_auto_str_31 || "", {
    title: lan && lan.config && lan.config.config_auto_str_32 || "",
    closeBtn: 2,
    icon: 13,
    cancel: function () {
      $("#closePl").prop("checked", false);
    }
  }, function () {
    $.post('/setting/close_panel', '', function (rdata) {
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
      setTimeout(function () {
        window.location.reload();
      }, 1000);
    }, 'json');
  }, function () {
    $("#closePl").prop("checked", false);
  });
}

//开发模式
function debugMode() {
  var loadT = layer.msg(lan && lan.config && lan.config.config_auto_str_33 || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/setting/open_debug', {}, function (rdata) {
    layer.close(loadT);
    showMsg(rdata.msg, function () {
      window.location.reload();
    }, {
      icon: rdata.status ? 1 : 2
    }, 1000);
  }, 'json');
}
function modifyAuthPath() {
  var auth_path = $("#admin_path").val();
  layer.open({
    type: 1,
    area: "500px",
    title: lan && lan.config && lan.config.config_auto_str_34 || "",
    closeBtn: 1,
    shift: 5,
    btn: [lan && lan.config && lan.config.config_auto_str_35 || "", lan && lan.config && lan.config.config_auto_str_36 || "", lan && lan.config && lan.config.config_auto_str_37 || ""],
    shadeClose: false,
    content: (lan && lan.config && lan.config.config_auto_str_38 || "") + auth_path + '">\
                </div>\
            </div>\
        </div>',
    yes: function (index) {
      var auth_path = $("input[name='auth_path_set']").val();
      if (auth_path == '/' || auth_path == '') {
        layer.confirm(lan && lan.config && lan.config.config_auto_str_39 || "", {
          title: lan && lan.config && lan.config.config_auto_str_40 || "",
          closeBtn: 1,
          icon: 13,
          cancel: function () {}
        }, function () {
          var loadT = layer.msg(lan.config.config_save, {
            icon: 16,
            time: 0,
            shade: [0.3, '#000']
          });
          $.post('/setting/set_admin_path', {
            admin_path: auth_path
          }, function (rdata) {
            showMsg(rdata.msg, function () {
              layer.close(index);
              layer.close(loadT);
              location.reload();
            }, {
              icon: rdata.status ? 1 : 2
            }, 2000);
          }, 'json');
        });
        return;
      } else {
        var loadT = layer.msg(lan.config.config_save, {
          icon: 16,
          time: 0,
          shade: [0.3, '#000']
        });
        $.post('/setting/set_admin_path', {
          admin_path: auth_path
        }, function (rdata) {
          showMsg(rdata.msg, function () {
            layer.close(index);
            layer.close(loadT);
            location.reload();
          }, {
            icon: rdata.status ? 1 : 2
          }, 2000);
        }, 'json');
      }
    },
    btn3: function () {
      var rand_str = getRandomString(8);
      $("input[name='auth_path_set']").val('/' + rand_str);
      return false;
    }
  });
}
function setPassword() {
  layer.open({
    type: 1,
    area: ["350px", 'auto'],
    title: lan && lan.config && lan.config.config_auto_str_41 || "",
    closeBtn: 1,
    shift: 5,
    shadeClose: false,
    btn: [lan && lan.config && lan.config.config_auto_str_42 || "", lan && lan.config && lan.config.config_auto_str_43 || "", lan && lan.config && lan.config.config_auto_str_44 || ""],
    content: lan && lan.config && lan.config.config_auto_str_45 || "",
    yes: function () {
      var p1 = $("#p1").val();
      var p2 = $("#p2").val();
      if (p1 == "" || p1.length < 8) {
        layer.msg(lan && lan.config && lan.config.config_auto_str_46 || "", {
          icon: 2
        });
        return;
      }

      //准备弱口令匹配元素
      var checks = ['admin888', '123123123', '12345678', '45678910', '87654321', 'asdfghjkl', 'password', 'qwerqwer'];
      pchecks = 'abcdefghijklmnopqrstuvwxyz1234567890';
      for (var i = 0; i < pchecks.length; i++) {
        checks.push(pchecks[i] + pchecks[i] + pchecks[i] + pchecks[i] + pchecks[i] + pchecks[i] + pchecks[i] + pchecks[i]);
      }

      //检查弱口令
      cps = p1.toLowerCase();
      var isError = "";
      for (var i = 0; i < checks.length; i++) {
        if (cps == checks[i]) {
          isError += '[' + checks[i] + '] ';
        }
      }
      if (isError != "") {
        layer.msg((lan && lan.config && lan.config.config_auto_str_47 || "") + isError, {
          icon: 5
        });
        return;
      }
      if (p1 != p2) {
        layer.msg(lan && lan.config && lan.config.config_auto_str_48 || "", {
          icon: 2
        });
        return;
      }
      $.post("/setting/set_password", "password1=" + encodeURIComponent(p1) + "&password2=" + encodeURIComponent(p2), function (b) {
        if (b.status) {
          layer.closeAll();
          layer.msg(b.msg, {
            icon: 1
          });
        } else {
          layer.msg(b.msg, {
            icon: 2
          });
        }
      }, 'json');
      return;
    },
    btn3: function () {
      var pwd = randomStrPwd(12);
      $("#p1").val(pwd);
      $("#p2").val(pwd);
      layer.msg(lan && lan.config && lan.config.config_auto_str_49 || "", {
        time: 2000
      });
      return false;
    }
  });
}
function setUserName() {
  layer.open({
    type: 1,
    area: ["350px", 'auto'],
    title: lan && lan.config && lan.config.config_auto_str_50 || "",
    closeBtn: 1,
    shift: 5,
    shadeClose: false,
    btn: [lan && lan.config && lan.config.config_auto_str_51 || "", lan && lan.config && lan.config.config_auto_str_52 || "", lan && lan.config && lan.config.config_auto_str_53 || ""],
    content: lan && lan.config && lan.config.config_auto_str_54 || "",
    yes: function () {
      p1 = $("#p1").val();
      p2 = $("#p2").val();
      if (p1 == "" || p1.length < 3) {
        layer.msg(lan && lan.config && lan.config.config_auto_str_55 || "", {
          icon: 2
        });
        return;
      }
      if (p1 != p2) {
        layer.msg(lan && lan.config && lan.config.config_auto_str_56 || "", {
          icon: 2
        });
        return;
      }
      $.post("/setting/set_name", "name1=" + encodeURIComponent(p1) + "&name2=" + encodeURIComponent(p2), function (b) {
        if (b.status) {
          layer.closeAll();
          layer.msg(b.msg, {
            icon: 1
          });
          $("input[name='username_']").val(p1);
        } else {
          layer.msg(b.msg, {
            icon: 2
          });
        }
      }, 'json');
      return;
    },
    btn3: function () {
      var pwd = randomStrPwd(12);
      $("#p1").val(pwd);
      $("#p2").val(pwd);
      layer.msg(lan && lan.config && lan.config.config_auto_str_57 || "", {
        time: 2000
      });
      return false;
    }
  });
}
function setTimezone() {
  layer.open({
    type: 1,
    area: ["400px", "200px"],
    title: lan && lan.config && lan.config.config_auto_str_58 || "",
    closeBtn: 1,
    shift: 5,
    shadeClose: false,
    btn: [lan && lan.config && lan.config.config_auto_str_59 || "", lan && lan.config && lan.config.config_auto_str_60 || "", lan && lan.config && lan.config.config_auto_str_61 || ""],
    content: lan && lan.config && lan.config.config_auto_str_62 || "",
    success: function () {
      var tbody = '';
      $.post('/setting/get_timezone_list', {}, function (data) {
        var rdata = data['data'];
        for (var i = 0; i < rdata.length; i++) {
          if (rdata[i] == 'Asia/Shanghai') {
            tbody += '<option value="' + rdata[i] + '" selected="selected">' + rdata[i] + '</option>';
          } else {
            tbody += '<option value="' + rdata[i] + '">' + rdata[i] + '</option>';
          }
        }
        $('select[name="timezone"]').append(tbody);
      }, 'json');
    },
    yes: function (index) {
      var loadT = layer.msg(lan && lan.config && lan.config.config_auto_str_63 || "", {
        icon: 16,
        time: 0,
        shade: [0.3, '#000']
      });
      var timezone = $('select[name="timezone"]').val();
      $.post('/setting/set_timezone', {
        timezone: timezone
      }, function (rdata) {
        showMsg(rdata.msg, function () {
          layer.close(index);
          layer.close(loadT);
          location.reload();
        }, {
          icon: rdata.status ? 1 : 2
        }, 2000);
      }, 'json');
    },
    btn3: function () {
      var loadT = layer.msg(lan && lan.config && lan.config.config_auto_str_64 || "", {
        icon: 16,
        time: 0,
        shade: [0.3, '#000']
      });
      $.post('/setting/sync_date', '', function (rdata) {
        layer.close(loadT);
        layer.msg(rdata.msg, {
          icon: rdata.status ? 1 : 2
        });
        setTimeout(function () {
          window.location.reload();
        }, 1500);
      }, 'json');
    }
  });
}
function setIPv6() {
  var loadT = layer.msg(lan && lan.config && lan.config.config_auto_str_65 || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/setting/set_ipv6_status', {}, function (rdata) {
    layer.close(loadT);
    layer.msg(rdata.msg, {
      icon: rdata.status ? 1 : 2
    });
    setTimeout(function () {
      window.location.reload();
    }, 5000);
  }, 'json');
}
function setCDN() {
  var loadT = layer.msg(lan && lan.config && lan.config.config_auto_str_66 || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/setting/set_cdn_status', {}, function (rdata) {
    layer.close(loadT);
    layer.msg(rdata.msg, {
      icon: rdata.status ? 1 : 2
    });
    setTimeout(function () {
      window.location.reload();
    }, 1500);
  }, 'json');
}
function setGpuDetect() {
  // 延迟获取最新状态，避免 label 的 onclick 获取到旧状态
  setTimeout(function () {
    var isChecked = $("#gpuDetect").prop("checked");
    if (isChecked) {
      var loadT = layer.msg(lan && lan.config && lan.config.config_auto_str_67 || "", {
        icon: 16,
        time: 0,
        shade: [0.3, '#000']
      });
      $.get('/system/get_gpu_info', function (res) {
        layer.close(loadT);
        if (!res.status || !res.data || res.data.length === 0) {
          // 未检测到显卡，回退开关状态
          $("#gpuDetect").prop("checked", false);
          layer.msg(lan && lan.config && lan.config.config_auto_str_68 || "", {
            icon: 2,
            time: 3000
          });
          return;
        }
        // 验证通过，保存设置
        doSetGpuDetect(true);
      }, 'json').fail(function () {
        layer.close(loadT);
        $("#gpuDetect").prop("checked", false);
        layer.msg(lan && lan.config && lan.config.config_auto_str_69 || "", {
          icon: 2
        });
      });
    } else {
      doSetGpuDetect(false);
    }
  }, 10);
}
function doSetGpuDetect(isEnable) {
  var loadT = layer.msg(lan && lan.config && lan.config.config_auto_str_70 || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/setting/set_gpu_detect', {}, function (rdata) {
    layer.close(loadT);
    if (rdata.status && isEnable) {
      layer.confirm(lan && lan.config && lan.config.config_auto_str_71 || "", {
        title: lan && lan.config && lan.config.config_auto_str_72 || "",
        icon: 1,
        btn: [lan && lan.config && lan.config.config_auto_str_73 || "", lan && lan.config && lan.config.config_auto_str_74 || ""]
      }, function () {
        window.location.href = '/';
      }, function () {
        window.location.reload();
      });
    } else {
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
      setTimeout(function () {
        window.location.reload();
      }, 1500);
    }
  }, 'json');
}

//设置面板SSL
function setPanelSSL() {
  var status = $("#sshswitch").prop("checked") == true ? 1 : 0;
  var msg = $("#panelSSL").attr('checked') ? lan && lan.config && lan.config.config_auto_str_75 || "" : lan && lan.config && lan.config.config_auto_str_76 || "";
  layer.confirm(msg, {
    title: lan && lan.config && lan.config.config_auto_str_77 || "",
    closeBtn: 1,
    icon: 3,
    area: '550px',
    cancel: function () {
      $("#panelSSL").prop("checked", status == 0 ? false : true);
    }
  }, function () {
    if (window.location.protocol.indexOf('https') == -1) {
      if (!$("#checkSSL").prop('checked')) {
        layer.msg(lan.config.ssl_ps, {
          icon: 2
        });
        return false;
      }
    }
    var loadT = layer.msg(lan && lan.config && lan.config.config_auto_str_78 || "", {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.post('/setting/set_panel_ssl', '', function (rdata) {
      layer.close(loadT);
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 5
      });
      if (rdata.status === true) {
        $.post('/system/restart', '', function (rdata) {
          layer.close(loadT);
          layer.msg(rdata.msg);
          setTimeout(function () {
            window.location.href = (window.location.protocol.indexOf('https') != -1 ? 'http://' : 'https://') + window.location.host + window.location.pathname;
          }, 3000);
        }, 'json');
      }
    }, 'json');
  }, function () {
    if (status == 0) {
      $("#panelSSL").prop("checked", false);
    } else {
      $("#panelSSL").prop("checked", true);
    }
  });
}
function setNotifyTgbot(obj) {
  var enable = $(obj).prop("checked");
  $.post('/setting/set_notify_tgbot_enable', {
    'enable': enable
  }, function (rdata) {
    showMsg(rdata.msg, function () {
      if (rdata.status) {}
    }, {
      icon: rdata.status ? 1 : 2
    }, 1000);
  }, 'json');
}
function setNotifyEmail(obj) {
  var enable = $(obj).prop("checked");
  $.post('/setting/set_notify_email_enable', {
    'enable': enable
  }, function (rdata) {
    showMsg(rdata.msg, function () {
      if (rdata.status) {}
    }, {
      icon: rdata.status ? 1 : 2
    }, 1000);
  }, 'json');
}
function getTgbot() {
  var loadT = layer.msg(lan && lan.config && lan.config.config_auto_str_79 || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/setting/get_notify_tgbot', {}, function (data) {
    layer.close(loadT);
    var app_token = '';
    var chat_id = '';
    if (data.status) {
      if (data['data']['tgbot'].length != 0) {
        app_token = data['data']['tgbot']['app_token'];
        chat_id = data['data']['tgbot']['chat_id'];
      }
    }
    layer.open({
      type: 1,
      area: "500px",
      title: lan && lan.config && lan.config.config_auto_str_80 || "",
      closeBtn: 1,
      shift: 5,
      btn: [lan && lan.config && lan.config.config_auto_str_81 || "", lan && lan.config && lan.config.config_auto_str_82 || "", lan && lan.config && lan.config.config_auto_str_83 || ""],
      shadeClose: false,
      content: "<div class='bt-form pd20'>\
					<div class='line'>\
						<span class='tname'>APP_TOKEN</span>\
						<div class='info-r'><input class='bt-input-text' type='text' name='app_token' value='" + app_token + "' style='width:100%'/></div>\
					</div>\
					<div class='line'>\
						<span class='tname'>CHAT_ID</span>\
						<div class='info-r'><input class='bt-input-text' type='text' name='chat_id' value='" + chat_id + "' style='width:100%' /></div>\
					</div>\
				</div>",
      yes: function (index) {
        var pdata = {};
        pdata['app_token'] = $('input[name="app_token"]').val();
        pdata['chat_id'] = $('input[name="chat_id"]').val();
        if (pdata['app_token'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_84 || "", {
            icon: 2
          });
          return false;
        }
        if (pdata['chat_id'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_85 || "", {
            icon: 2
          });
          return false;
        }
        $.post('/setting/set_notify_tgbot', {
          'tag': 'tgbot',
          'data': JSON.stringify(pdata)
        }, function (rdata) {
          showMsg(rdata.msg, function () {
            if (rdata.status) {
              layer.close(index);
            }
          }, {
            icon: rdata.status ? 1 : 2
          }, 2000);
        });
      },
      btn3: function (index) {
        var pdata = {};
        pdata['app_token'] = $('input[name="app_token"]').val();
        pdata['chat_id'] = $('input[name="chat_id"]').val();
        if (pdata['app_token'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_86 || "", {
            icon: 2
          });
          return false;
        }
        if (pdata['chat_id'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_87 || "", {
            icon: 2
          });
          return false;
        }
        $.post('/setting/set_notify_tgbot_test', {
          'tag': 'tgbot',
          'data': JSON.stringify(pdata)
        }, function (rdata) {
          showMsg(rdata.msg, function () {
            if (rdata.status) {
              layer.close(index);
            }
          }, {
            icon: rdata.status ? 1 : 2
          }, 2000);
        });
        return false;
      }
    });
  });
}
function getEmailCfg() {
  var loadT = layer.msg(lan && lan.config && lan.config.config_auto_str_88 || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/setting/get_notify_email', {}, function (data) {
    layer.close(loadT);
    var smtp_host = 'smtp.163.com';
    var smtp_port = '25';
    var username = 'admin';
    var password = '';
    var to_mail_addr = '';
    var smtp_ssl_no = 'checked';
    var smtp_ssl_yes = '';
    if (data.status) {
      if (typeof data['data']['email'] != 'undefined') {
        smtp_host = data['data']['email']['smtp_host'];
        smtp_port = data['data']['email']['smtp_port'];
        username = data['data']['email']['username'];
        password = data['data']['email']['password'];
        to_mail_addr = data['data']['email']['to_mail_addr'];
        var smtp_ssl = data['data']['email']['smtp_ssl'];
        if (smtp_ssl == 'ssl') {
          smtp_ssl_no = '';
          smtp_ssl_yes = 'checked';
        }
      }
    }
    layer.open({
      type: 1,
      area: "500px",
      title: lan && lan.config && lan.config.config_auto_str_89 || "",
      closeBtn: 1,
      shift: 5,
      btn: [lan && lan.config && lan.config.config_auto_str_90 || "", lan && lan.config && lan.config.config_auto_str_91 || "", lan && lan.config && lan.config.config_auto_str_92 || ""],
      shadeClose: false,
      content: (lan && lan.config && lan.config.config_auto_str_93 || "") + smtp_host + (lan && lan.config && lan.config.config_auto_str_94 || "") + smtp_ssl_no + ">None</label>\
							<label><input name='smtp_ssl' type='radio' value='ssl' style='margin-right: 4px;' " + smtp_ssl_yes + (lan && lan.config && lan.config.config_auto_str_95 || "") + smtp_port + (lan && lan.config && lan.config.config_auto_str_96 || "") + username + (lan && lan.config && lan.config.config_auto_str_97 || "") + password + (lan && lan.config && lan.config.config_auto_str_98 || "") + to_mail_addr + (lan && lan.config && lan.config.config_auto_str_99 || ""),
      yes: function (index) {
        var pdata = {};
        pdata['smtp_host'] = $('input[name="smtp_host"]').val();
        pdata['smtp_port'] = $('input[name="smtp_port"]').val();
        pdata['smtp_ssl'] = $('input[name="smtp_ssl"]:checked').val();
        pdata['username'] = $('input[name="username"]').val();
        pdata['password'] = $('input[name="password"]').val();
        pdata['to_mail_addr'] = $('input[name="to_mail_addr"]').val();
        if (pdata['smtp_host'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_100 || "", {
            icon: 2
          });
          return false;
        }
        if (pdata['smtp_port'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_101 || "", {
            icon: 2
          });
          return false;
        }
        if (pdata['username'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_102 || "", {
            icon: 2
          });
          return false;
        }
        if (pdata['password'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_103 || "", {
            icon: 2
          });
          return false;
        }
        if (pdata['to_mail_addr'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_104 || "", {
            icon: 2
          });
          return false;
        }
        $.post('/setting/set_notify_email', {
          'tag': 'email',
          'data': JSON.stringify(pdata)
        }, function (rdata) {
          showMsg(rdata.msg, function () {
            if (rdata.status) {
              layer.close(index);
            }
          }, {
            icon: rdata.status ? 1 : 2
          }, 2000);
        }, 'json');
      },
      btn3: function (index) {
        var pdata = {};
        pdata['smtp_host'] = $('input[name="smtp_host"]').val();
        pdata['smtp_port'] = $('input[name="smtp_port"]').val();
        pdata['smtp_ssl'] = $('input[name="smtp_ssl"]:checked').val();
        pdata['username'] = $('input[name="username"]').val();
        pdata['password'] = $('input[name="password"]').val();
        pdata['to_mail_addr'] = $('input[name="to_mail_addr"]').val();
        pdata['mail_test'] = $('textarea[name="mail_test"]').val();
        if (pdata['smtp_host'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_105 || "", {
            icon: 2
          });
          return false;
        }
        if (pdata['smtp_port'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_106 || "", {
            icon: 2
          });
          return false;
        }
        if (pdata['username'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_107 || "", {
            icon: 2
          });
          return false;
        }
        if (pdata['password'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_108 || "", {
            icon: 2
          });
          return false;
        }
        if (pdata['to_mail_addr'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_109 || "", {
            icon: 2
          });
          return false;
        }
        if (pdata['mail_test'] == '') {
          layer.msg(lan && lan.config && lan.config.config_auto_str_110 || "", {
            icon: 2
          });
          return false;
        }
        $.post('/setting/set_notify_email_test', {
          'tag': 'email',
          'data': JSON.stringify(pdata)
        }, function (rdata) {
          showMsg(rdata.msg, function () {
            if (rdata.status) {
              layer.close(index);
            }
          }, {
            icon: rdata.status ? 1 : 2
          }, 2000);
        }, 'json');
        return false;
      }
    });
  }, 'json');
}
function renderPanelSSLApply(panel_domain, ssl_email) {
  var lets = (lan && lan.config && lan.config.config_auto_str_111 || "") + ssl_email + (lan && lan.config && lan.config.config_auto_str_112 || "") + panel_domain + '" checked="checked" disabled="disabled">' + panel_domain + (lan && lan.config && lan.config.config_auto_str_113 || "");
  return lets;
}
function newAcmeHandApplyNoticeForPanel(panel_domain, data) {
  layer.open({
    type: 1,
    area: '700px',
    title: lan && lan.config && lan.config.config_auto_str_114 || "",
    closeBtn: 1,
    shift: 5,
    shadeClose: true,
    btn: [lan && lan.config && lan.config.config_auto_str_115 || "", lan && lan.config && lan.config.config_auto_str_116 || ""],
    content: lan && lan.config && lan.config.config_auto_str_117 || "",
    success: function () {
      var list = '';
      for (var i = 0; i < data.length; i++) {
        list += '<tr>';
        list += '<td>' + data[i]['domain'] + '</td>';
        list += '<td>' + data[i]['val'] + '</td>';
        list += '<td>' + data[i]['type'] + '</td>';
        list += '<td>' + (data[i]['must'] ? lan && lan.config && lan.config.config_auto_str_118 || "" : lan && lan.config && lan.config.config_auto_str_119 || "") + '</td>';
        list += '</tr>';
      }
      $('#acme_hand_ssl_notice tbody').html(list);
      if (data.length > 0) {
        var help_txt = (lan && lan.config && lan.config.config_auto_str_120 || "") + data[0]['domain'];
        $('#acme_hand_ssl_notice_help li:eq(1)').text(help_txt);
      }
    },
    yes: function (layero, index) {
      layer.close(layero);
      showSpeedWindow(lan && lan.config && lan.config.config_auto_str_121 || "", 'site.get_acme_logs', function (layers, index) {
        var pdata = {};
        pdata['domains'] = JSON.stringify([panel_domain]);
        pdata['email'] = $("input[name='panel_admin_email']").val();
        if ($("#panel_checkDomain").prop("checked")) {
          pdata['force'] = 'true';
        }
        var apply_type = $('input[name="panel_apply_type"]:checked').val();
        pdata['apply_type'] = apply_type;
        if (apply_type == 'dns') {
          pdata['dnspai'] = $('select[name="panel_dnspai"] option:selected').val();
        }
        pdata['renew'] = 'true';
        $.post('/setting/apply_panel_acme_ssl', pdata, function (rdata) {
          showMsg(rdata.msg, function () {
            if (rdata.status) {
              layer.close(index);
              setTimeout(function () {
                location.reload();
              }, 2000);
            }
          }, {
            icon: rdata.status ? 1 : 2
          }, 3000);
        }, 'json');
      });
    }
  });
}
function getPanelSSL() {
  var loadT = layer.msg(lan && lan.config && lan.config.config_auto_str_122 || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/setting/get_panel_ssl', {}, function (cert_all) {
    layer.close(loadT);
    var choose = cert_all['choose'];
    var choose_local = choose == 'local' ? 'selected="selected"' : '';
    var choose_nginx = choose == 'nginx' ? 'selected="selected"' : '';
    var select_options = '<option value="local" ' + choose_local + (lan && lan.config && lan.config.config_auto_str_123 || "");
    if (cert_all['panel_domain']) {
      select_options += '<option value="nginx" ' + choose_nginx + (lan && lan.config && lan.config.config_auto_str_124 || "");
    }
    var certBody = '<div class="tab-con" style="padding: 0 15px;">\
			<div id="panel_ssl_content"></div>\
			<div class="ssl-btn pull-left mtb15" style="width:100%">\
				<div id="panel_ssl_buttons" style="display:inline-block;"></div>\
				<select class="bt-input-text" name="choose" style="width:100px;vertical-align:middle;margin-left:10px;height:30px;line-height:30px;padding:2px 5px;">\
					' + select_options + '\
				</select>\
			</div>\
			<div style="clear:both"></div>\
			<ul class="help-info-text c7 pull-left" id="panel_ssl_help" style="width:100%;margin-top:10px;padding-left:15px;"></ul>\
		</div>';
    layer.open({
      type: 1,
      area: "600px",
      title: lan && lan.config && lan.config.config_auto_str_125 || "",
      closeBtn: 1,
      shift: 5,
      shadeClose: false,
      content: certBody,
      success: function (layero, layer_id) {
        function switchPanelSSLView(selected_choose) {
          if (selected_choose == 'local') {
            var cert = cert_all['local'];
            var cert_data = '';
            if (cert['info'] && cert['info']['issuer']) {
              var issuer_o = cert['info']['issuer_o'] || lan && lan.config && lan.config.config_auto_str_126 || "";
              cert_data = (lan && lan.config && lan.config.config_auto_str_127 || "") + issuer_o + (lan && lan.config && lan.config.config_auto_str_128 || "") + cert['info']['issuer'] + (lan && lan.config && lan.config.config_auto_str_129 || "") + cert['info']['endtime'] + (lan && lan.config && lan.config.config_auto_str_130 || "") + cert['info']['subject'] + "</span></div>\
							</div></div>";
            }
            var html = cert_data + (lan && lan.config && lan.config.config_auto_str_131 || "") + (cert.privateKey || '') + (lan && lan.config && lan.config.config_auto_str_132 || "") + (cert.certPem || '') + '</textarea>\
							</div>\
						</div>';
            $('#panel_ssl_content').html(html);
            var buttons = lan && lan.config && lan.config.config_auto_str_133 || "";
            $('#panel_ssl_buttons').html(buttons);
            var help = lan && lan.config && lan.config.config_auto_str_134 || "";
            $('#panel_ssl_help').html(help);
          } else if (selected_choose == 'nginx') {
            if (cert_all['nginx'] && cert_all['nginx']['certPem']) {
              var cert = cert_all['nginx'];
              var cert_data = '';
              if (cert['info'] && cert['info']['issuer']) {
                var issuer_o = cert['info']['issuer_o'] || lan && lan.config && lan.config.config_auto_str_135 || "";
                cert_data = (lan && lan.config && lan.config.config_auto_str_136 || "") + issuer_o + (lan && lan.config && lan.config.config_auto_str_137 || "") + cert['info']['issuer'] + (lan && lan.config && lan.config.config_auto_str_138 || "") + cert['info']['endtime'] + (lan && lan.config && lan.config.config_auto_str_139 || "") + cert['info']['subject'] + "</span></div>\
								</div></div>";
              }
              var html = cert_data + (lan && lan.config && lan.config.config_auto_str_140 || "") + (cert.privateKey || '') + (lan && lan.config && lan.config.config_auto_str_141 || "") + (cert.certPem || '') + '</textarea>\
								</div>\
							</div>';
              $('#panel_ssl_content').html(html);
              var buttons = lan && lan.config && lan.config.config_auto_str_142 || "";
              $('#panel_ssl_buttons').html(buttons);
              var help = lan && lan.config && lan.config.config_auto_str_143 || "";
              $('#panel_ssl_help').html(help);
            } else {
              // 渲染申请界面
              $('#panel_ssl_content').html(renderPanelSSLApply(cert_all['panel_domain'], cert_all['ssl_email']));
              $('#panel_ssl_buttons').html('');
              $('#panel_ssl_help').html('');

              // 获取 DNS API
              $.post('/site/get_dnsapi', {}, function (rdata) {
                var opt = lan && lan.config && lan.config.config_auto_str_144 || "";
                for (var i = 0; i < rdata.length; i++) {
                  opt += '<option value="' + rdata[i]['name'] + '">' + rdata[i]['title'] + '</option>';
                }
                $('select[name="panel_dnspai"]').html(opt);
              }, 'json');
            }
          }
        }

        // 首次切换到数据库对应的值
        switchPanelSSLView(choose);

        // 监听下拉切换
        $('select[name="choose"]').on('change', function () {
          switchPanelSSLView($(this).val());
        });

        // 监听验证类型单选框
        $(layero).on('change', 'input[name="panel_apply_type"]', function () {
          var val = $(this).val();
          if (val == 'file') {
            $('#panel_dnsapi_option').css('display', 'none');
          } else {
            $('#panel_dnsapi_option').css('display', 'block');
          }
        });

        // 监听一键申请
        $(layero).on('click', '.panel_letsApply', function () {
          var pdata = {};
          pdata['domains'] = JSON.stringify([cert_all['panel_domain']]);
          pdata['email'] = $("input[name='panel_admin_email']").val();
          if ($("#panel_checkDomain").prop("checked")) {
            pdata['force'] = 'true';
          }
          var apply_type = $('input[name="panel_apply_type"]:checked').val();
          pdata['apply_type'] = apply_type;
          if (apply_type == 'dns') {
            pdata['dnspai'] = $('select[name="panel_dnspai"] option:selected').val();
          }
          showSpeedWindow(lan && lan.config && lan.config.config_auto_str_145 || "", 'site.get_acme_logs', function (layers, index) {
            $.post('/setting/apply_panel_acme_ssl', pdata, function (rdata) {
              if (rdata.status) {
                layer.close(index);
                if (rdata.msg == (lan && lan.config && lan.config.config_auto_str_146 || "")) {
                  newAcmeHandApplyNoticeForPanel(cert_all['panel_domain'], rdata.data);
                } else {
                  showSSLSuccessWindow(rdata.data, lan && lan.config && lan.config.config_auto_str_147 || "");
                }
              } else {
                layer.close(index);
                layer.msg(rdata.msg, {
                  icon: 2
                });
              }
            }, 'json');
          });
        });

        // 续期/重新申请
        $(layero).on('click', '.panel-renew-ssl', function () {
          // 强制渲染申请表单
          $('#panel_ssl_content').html(renderPanelSSLApply(cert_all['panel_domain'], cert_all['ssl_email']));
          $('#panel_ssl_buttons').html('');
          $('#panel_ssl_help').html('');
          $.post('/site/get_dnsapi', {}, function (rdata) {
            var opt = lan && lan.config && lan.config.config_auto_str_148 || "";
            for (var i = 0; i < rdata.length; i++) {
              opt += '<option value="' + rdata[i]['name'] + '">' + rdata[i]['title'] + '</option>';
            }
            $('select[name="panel_dnspai"]').html(opt);
          }, 'json');
        });

        // 保存/部署
        $(layero).on('click', '.save-panel-ssl', function () {
          var data = {
            privateKey: $("#key").val(),
            certPem: $("#csr").val(),
            choose: $('select[name="choose"]').val()
          };
          var loadT = layer.msg(lan && lan.config && lan.config.config_auto_str_149 || "", {
            icon: 16,
            time: 0,
            shade: [0.3, '#000']
          });
          $.post('/setting/save_panel_ssl', data, function (rdata) {
            layer.close(loadT);
            if (rdata.status) {
              layer.closeAll();
              showSSLSuccessWindow(rdata.data, lan && lan.config && lan.config.config_auto_str_150 || "");
            } else {
              layer.msg(rdata.msg, {
                icon: 2
              });
            }
          }, 'json');
        });

        // 删除证书
        $(layero).on('click', '.del-panel-ssl', function () {
          var current_choose = $('select[name="choose"]').val();
          var confirm_msg = current_choose == 'local' ? lan && lan.config && lan.config.config_auto_str_151 || "" : lan && lan.config && lan.config.config_auto_str_152 || "";
          layer.confirm(confirm_msg, {
            title: lan && lan.config && lan.config.config_auto_str_153 || "",
            shade: 0.001,
            btn: [lan && lan.config && lan.config.config_auto_str_154 || "", lan && lan.config && lan.config.config_auto_str_155 || ""]
          }, function (index) {
            layer.close(index);
            var data = {
              choose: current_choose
            };
            var loadT = layer.msg(lan && lan.config && lan.config.config_auto_str_156 || "", {
              icon: 16,
              time: 0,
              shade: [0.3, '#000']
            });
            $.post('/setting/del_panel_ssl', data, function (rdata) {
              layer.close(loadT);
              showMsg(rdata.msg, function () {
                if (rdata.status) {
                  location.href = rdata.data;
                }
              }, {
                icon: rdata.status ? 1 : 2
              }, 3000);
            }, 'json');
          });
        });
      }
    });
  }, 'json');
}
function removeTempAccess(id) {
  $.post('/setting/remove_temp_login', {
    id: id
  }, function (rdata) {
    showMsg(rdata.msg, function () {
      setTempAccessReq();
    }, {
      icon: rdata.status ? 1 : 2
    }, 2000);
  }, 'json');
}
function getTempAccessLogsReq(id) {
  $.post('/setting/get_temp_login_logs', {
    id: id
  }, function (rdata) {
    var tbody = '';
    for (var i = 0; i < rdata.data.length; i++) {
      tbody += '<tr>';
      tbody += '<td>' + rdata.data[i]['type'] + '</td>';
      tbody += '<td>' + rdata.data[i]['addtime'] + '</td>';
      tbody += '<td>' + rdata.data[i]['log'] + '</td>';
      tbody += '</tr>';
    }
    $('#logs_list').html(tbody);
  }, 'json');
}
function getTempAccessLogs(id) {
  layer.open({
    area: ['700px', '250px'],
    title: lan && lan.config && lan.config.config_auto_str_157 || "",
    closeBtn: 1,
    shift: 0,
    type: 1,
    content: lan && lan.config && lan.config.config_auto_str_158 || "",
    success: function () {
      getTempAccessLogsReq(id);
      $('.refresh_log').on('click', function () {
        getTempAccessLogsReq(id);
      });
    }
  });
}
function setTempAccessReq(page) {
  if (typeof page == 'undefined') {
    page = 1;
  }
  $.post('/setting/get_temp_login', {
    page: page
  }, function (rdata) {
    console.log(rdata);
    if (typeof rdata.status != 'undefined' && !rdata.status) {
      showMsg(rdata.msg, function () {
        layer.closeAll();
      }, {
        icon: 2
      }, 2000);
      return;
    }
    var tbody = '';
    for (var i = 0; i < rdata.data.length; i++) {
      tbody += '<tr>';
      tbody += '<td>' + (rdata.data[i]['login_addr'] || lan && lan.config && lan.config.config_auto_str_159 || "") + '</td>';
      tbody += '<td>';
      switch (parseInt(rdata.data[i]['state'])) {
        case 0:
          tbody += lan && lan.config && lan.config.config_auto_str_160 || "";
          break;
        case 1:
          tbody += lan && lan.config && lan.config.config_auto_str_161 || "";
          break;
        case -1:
          tbody += lan && lan.config && lan.config.config_auto_str_162 || "";
          break;
      }
      tbody += '</td>';
      tbody += '<td>' + (getLocalTime(rdata.data[i]['login_time']) || lan && lan.config && lan.config.config_auto_str_163 || "") + '</td>';
      tbody += '<td>' + getLocalTime(rdata.data[i]['expire']) + '</td>';
      tbody += '<td>';
      if (rdata.data[i]['state'] == '1') {
        tbody += '<a class="btlink" onclick="getTempAccessLogs(\'' + rdata.data[i]['id'] + (lan && lan.config && lan.config.config_auto_str_164 || "");
      } else {
        tbody += '<a class="btlink" onclick="removeTempAccess(\'' + rdata.data[i]['id'] + (lan && lan.config && lan.config.config_auto_str_165 || "");
      }
      tbody += '</td>';
      tbody += '</tr>';
    }
    $('#temp_login_view_tbody').html(tbody);
    $('.temp_login_view_page').html(rdata.page);
  }, 'json');
}
function setStatusCode(o) {
  var code = $(o).data('code');
  layer.open({
    type: 1,
    area: ['420px', '220px'],
    title: lan && lan.config && lan.config.config_auto_str_166 || "",
    closeBtn: 1,
    shift: 5,
    btn: [lan && lan.config && lan.config.config_auto_str_167 || "", lan && lan.config && lan.config.config_auto_str_168 || ""],
    shadeClose: false,
    content: lan && lan.config && lan.config.config_auto_str_169 || "",
    success: function () {
      var msg_list = [{
        'code': '0',
        'msg': lan && lan.config && lan.config.config_auto_str_170 || ""
      }, {
        'code': '403',
        'msg': lan && lan.config && lan.config.config_auto_str_171 || ""
      }, {
        'code': '404',
        'msg': lan && lan.config && lan.config.config_auto_str_172 || ""
      }, {
        'code': '416',
        'msg': lan && lan.config && lan.config.config_auto_str_173 || ""
      }, {
        'code': '408',
        'msg': lan && lan.config && lan.config.config_auto_str_174 || ""
      }, {
        'code': '400',
        'msg': lan && lan.config && lan.config.config_auto_str_175 || ""
      }, {
        'code': '401',
        'msg': lan && lan.config && lan.config.config_auto_str_176 || ""
      }];
      var tbody = '';
      for (i in msg_list) {
        if (msg_list[i]['code'] == code) {
          tbody += '<option value="' + msg_list[i]['code'] + '" selected>' + msg_list[i]['msg'] + '</option>';
        } else {
          tbody += '<option value="' + msg_list[i]['code'] + '">' + msg_list[i]['msg'] + '</option>';
        }
      }
      $('select[name="status_code"]').append(tbody);
    },
    yes: function (index) {
      var loadT = layer.msg(lan && lan.config && lan.config.config_auto_str_177 || "", {
        icon: 16,
        time: 0,
        shade: [0.3, '#000']
      });
      var status_code = $('select[name="status_code"]').val();
      $.post('/setting/set_status_code', {
        status_code: status_code
      }, function (rdata) {
        showMsg(rdata.msg, function () {
          layer.close(index);
          layer.close(loadT);
          location.reload();
        }, {
          icon: rdata.status ? 1 : 2
        }, 2000);
      }, 'json');
    }
  });
}
function setTempAccess() {
  layer.open({
    area: ['700px', '380px'],
    title: lan && lan.config && lan.config.config_auto_str_178 || "",
    closeBtn: 1,
    shift: 0,
    type: 1,
    content: lan && lan.config && lan.config.config_auto_str_179 || "",
    success: function () {
      setTempAccessReq();
      $('.create_temp_login').on('click', function () {
        layer.confirm(lan && lan.config && lan.config.config_auto_str_180 || "", {
          title: lan && lan.config && lan.config.config_auto_str_181 || "",
          closeBtn: 1,
          icon: 13
        }, function (create_temp_login_layer) {
          $.post('/setting/set_temp_login', {}, function (rdata) {
            layer.close(create_temp_login_layer);
            setTempAccessReq();
            layer.open({
              area: '570px',
              title: lan && lan.config && lan.config.config_auto_str_182 || "",
              shift: 0,
              type: 1,
              content: lan && lan.config && lan.config.config_auto_str_183 || "",
              success: function () {
                var temp_link = "".concat(location.origin, "/login?tmp_token=").concat(rdata.token);
                $('#temp_link').val(temp_link);
                copyText(temp_link);
                $('.btn-copy-temp-link').on('click', function () {
                  copyText(temp_link);
                });
              }
            });
          }, 'json');
        });
      });
    }
  });
}

//二步验证
function setAuthBind() {
  $.post('/setting/get_auth_secret', {}, function (rdata) {
    console.log(rdata);
    var tip = layer.open({
      area: ['500px', '355px'],
      title: lan && lan.config && lan.config.config_auto_str_184 || "",
      closeBtn: 1,
      shift: 0,
      type: 1,
      content: lan && lan.config && lan.config.config_auto_str_185 || "",
      success: function (layero, index) {
        $('input[name="secret"]').val(rdata.data['secret']);
        var renderQRCode = function () {
          $('.qrcode').qrcode({
            text: rdata.data['url']
          });
        };
        if ($.fn.qrcode) {
          renderQRCode();
        } else {
          loadScript(staticUrl('/static/js/jquery-qrcode-0.18.0.min.js')).then(renderQRCode);
        }
        $('.reset_secret').on('click', function () {
          layer.confirm(lan && lan.config && lan.config.config_auto_str_186 || "", {
            title: lan && lan.config && lan.config.config_auto_str_187 || "",
            closeBtn: 2,
            icon: 13,
            cancel: function () {}
          }, function () {
            $.post('/setting/get_auth_secret', {
              'reset': "1"
            }, function (rdata) {
              showMsg(lan && lan.config && lan.config.config_auto_str_188 || "", function () {
                $('input[name="secret"]').val(rdata.data['secret']);
                $('.qrcode').html('');
                if ($.fn.qrcode) {
                  $('.qrcode').qrcode({
                    text: rdata.data['url']
                  });
                } else {
                  loadScript(staticUrl('/static/js/jquery-qrcode-0.18.0.min.js')).then(function () {
                    $('.qrcode').qrcode({
                      text: rdata.data['url']
                    });
                  });
                }
              }, {
                icon: 1
              }, 2000);
            }, 'json');
          });
        });
      }
    });
  }, 'json');
}
function setAuthSecretApi() {
  var cfg_panel_auth = $('#cfg_panel_auth').prop("checked");
  $.post('/setting/set_auth_secret', {
    'op_type': "2"
  }, function (rdata) {
    showMsg(rdata.msg, function () {
      if (rdata.data == 1) {
        setAuthBind();
      }
    }, {
      icon: rdata.status ? 1 : 2
    }, 1000);
  }, 'json');
}
function setBasicAuthTip(callback) {
  var tip = layer.open({
    area: ['500px', '385px'],
    title: lan && lan.config && lan.config.config_auto_str_189 || "",
    closeBtn: 0,
    shift: 0,
    type: 1,
    content: lan && lan.config && lan.config.config_auto_str_190 || "",
    btn: [lan && lan.config && lan.config.config_auto_str_191 || "", lan && lan.config && lan.config.config_auto_str_192 || ""],
    yes: function (l, index) {
      is_agree = $('#agreement_more').prop("checked");
      if (is_agree) {
        layer.close(tip);
        callback();
      }
      return is_agree;
    },
    btn2: function (index, layero) {
      $('#cfg_basic_auth').prop("checked", false);
    }
  });
}
function setBasicAuth() {
  var basic_auth = $('#cfg_basic_auth').prop("checked");
  if (!basic_auth) {
    setBasicAuthTip(function () {
      var tip = layer.open({
        area: ['500px', '385px'],
        title: lan && lan.config && lan.config.config_auto_str_193 || "",
        closeBtn: 1,
        shift: 0,
        type: 1,
        content: lan && lan.config && lan.config.config_auto_str_194 || "",
        success: function () {
          $('.save_auth_cfg').on('click', function () {
            var basic_user = $('input[name="basic_user"]').val();
            var basic_pwd = $('input[name="basic_pwd"]').val();
            $.post('/setting/set_basic_auth', {
              'basic_user': basic_user,
              'basic_pwd': basic_pwd
            }, function (rdata) {
              showMsg(rdata.msg, function () {
                window.location.reload();
              }, {
                icon: rdata.status ? 1 : 2
              }, 2000);
            }, 'json');
          });
        },
        cancel: function () {
          $('#cfg_basic_auth').prop("checked", false);
        }
      });
    });
  } else {
    layer.confirm(lan && lan.config && lan.config.config_auto_str_195 || "", {
      btn: [lan && lan.config && lan.config.config_auto_str_196 || "", lan && lan.config && lan.config.config_auto_str_197 || ""],
      title: lan && lan.config && lan.config.config_auto_str_198 || "",
      icon: 13
    }, function (index) {
      var basic_user = '';
      var basic_pwd = '';
      $.post('/setting/set_basic_auth', {
        'is_open': 'false'
      }, function (rdata) {
        showMsg(rdata.msg, function () {
          layer.close(index);
          window.location.reload();
        }, {
          icon: rdata.status ? 1 : 2
        }, 2000);
      }, 'json');
    }, function () {
      $('#cfg_basic_auth').prop("checked", true);
    });
  }
}
function showPanelApi() {
  $.post('/setting/get_panel_token', '', function (rdata) {
    var tip = layer.open({
      area: ['500px', '355px'],
      title: lan && lan.config && lan.config.config_auto_str_199 || "",
      closeBtn: 1,
      shift: 0,
      type: 1,
      content: lan && lan.config && lan.config.config_auto_str_200 || "",
      success: function (layero, index) {
        $('input[name="token"]').val(rdata.data.token);
        $('textarea[name="api_limit_addr"]').val(rdata.data.limit_addr);
        $('.reset_token').on('click', function () {
          layer.confirm(lan && lan.config && lan.config.config_auto_str_201 || "", {
            title: lan && lan.config && lan.config.config_auto_str_202 || "",
            closeBtn: 2,
            icon: 13,
            cancel: function () {}
          }, function () {
            $.post('/config/set_panel_token', {
              'op_type': "1"
            }, function (rdata) {
              showMsg(lan && lan.config && lan.config.config_auto_str_203 || "", function () {
                $('input[name="token"]').val(rdata.data);
              }, {
                icon: 1
              }, 2000);
            }, 'json');
          });
        });
        $('.save_api').on('click', function () {
          var limit_addr = $('textarea[name="api_limit_addr"]').val();
          $.post('/config/set_panel_token', {
            'op_type': "3",
            'limit_addr': limit_addr
          }, function (rdata) {
            showMsg(rdata.msg, function () {}, {
              icon: rdata.status ? 1 : 2
            }, 2000);
          }, 'json');
        });
      }
    });
  }, 'json');
}
function setPanelApi() {
  var cfg_panel_api = $('#cfg_panel_api').prop("checked");
  $.post('/setting/set_panel_api', {}, function (rdata) {
    showMsg(rdata.msg, function () {
      if (rdata.status) {
        addApp();
      }
    }, {
      icon: rdata.status ? 1 : 2
    }, 1000);
  }, 'json');
}
function deleteApp(id) {
  layer.confirm(lan && lan.config && lan.config.config_auto_str_204 || "", {
    title: lan && lan.config && lan.config.config_auto_str_205 || "",
    closeBtn: 2,
    icon: 13,
    cancel: function () {}
  }, function () {
    $.post('/setting/delete_app', {
      'id': id
    }, function (rdata) {
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
      if (rdata.status) {
        getAppList();
      }
    }, 'json');
  });
}
function toggleAppstatus(id) {
  $.post('/setting/toggle_app_status', {
    id: id
  }, function (rdata) {
    showMsg(rdata.msg, function () {
      if (rdata.status) {
        getAppList();
      }
    }, {
      icon: rdata.status ? 1 : 2
    }, 2000);
  }, 'json');
}
function getAppList(page) {
  if (typeof page == 'undefined') {
    page = 1;
  }
  $.post('/setting/get_app_list', {
    page: page
  }, function (rdata) {
    var tbody = '';
    for (var i = 0; i < rdata.data.length; i++) {
      var row = rdata.data[i];
      tbody += '<tr>';
      tbody += '<td>' + row['app_id'] + '</td>';
      tbody += '<td>' + row['app_secret'] + '</td>';
      tbody += '<td>' + row['white_list'] + '</td>';
      if (row['status'] == 1) {
        tbody += '<td><a class="btlink" onclick="toggleAppstatus(' + row['id'] + (lan && lan.config && lan.config.config_auto_str_206 || "");
      } else {
        tbody += '<td><a style="color:red;" onclick="toggleAppstatus(' + row['id'] + (lan && lan.config && lan.config.config_auto_str_207 || "");
      }
      tbody += '<td>' + row['add_time'] + '</td>';
      tbody += '<td>';
      tbody += '<a class="btlink" onclick="deleteApp(\'' + row['id'] + (lan && lan.config && lan.config.config_auto_str_208 || "");
      tbody += '</td>';
      tbody += '</tr>';
    }
    $('#app_list_body tbody').html(tbody);
    $('#app_list_body .page').html(rdata.page);
  }, 'json');
}
function addApp() {
  layer.open({
    area: '570px',
    title: lan && lan.config && lan.config.config_auto_str_209 || "",
    shift: 0,
    type: 1,
    content: lan && lan.config && lan.config.config_auto_str_210 || "",
    success: function (obj, cur_layer) {
      $('input[name="app_id"]').val(getRandomString(10));
      $('input[name="app_secret"]').val(getRandomString(20));
      $('.app_id').on('click', function () {
        $('input[name="app_id"]').val(getRandomString(10));
      });
      $('.app_secret').on('click', function () {
        $('input[name="app_secret"]').val(getRandomString(20));
      });
      $('.save_app_data').on('click', function () {
        var app_id = $('input[name="app_id"]').val();
        var app_secret = $('input[name="app_secret"]').val();
        var limit_addr = $('textarea[name="api_limit_addr"]').val();
        $.post('/setting/add_app', {
          'app_id': app_id,
          'app_secret': app_secret,
          'limit_addr': limit_addr
        }, function (rdata) {
          showMsg(rdata.msg, function () {
            if (rdata.status) {
              getAppList();
              layer.close(cur_layer);
            }
          }, {
            icon: rdata.status ? 1 : 2
          }, 2000);
        }, 'json');
      });
    }
  });
}
function appPage() {
  layer.open({
    area: ['900px', '380px'],
    title: lan && lan.config && lan.config.config_auto_str_211 || "",
    closeBtn: 1,
    shift: 0,
    type: 1,
    content: lan && lan.config && lan.config.config_auto_str_212 || "",
    success: function () {
      getAppList();
      $('.app_add').on('click', function () {
        addApp();
      });
    }
  });
}
function savePanelLanguage() {
  var lang = $("#panelLanguageSelect").val();
  var loadT = layer.msg(window.lan && lan.public && lan.public.the || "正在保存...", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/setting/set_language', {
    lang: lang
  }, function (rdata) {
    layer.close(loadT);
    if (rdata.status) {
      layer.msg(window.lan && lan.public && lan.public.config_ok || "设置成功!", {
        icon: 1
      });
      setTimeout(function () {
        if (window.YfI18n) {
          YfI18n.setLanguage(lang, true);
        } else {
          window.location.reload();
        }
      }, 500);
    } else {
      layer.msg(rdata.msg, {
        icon: 2
      });
    }
  }, 'json');
}