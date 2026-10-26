// ---------------------------------------------------------------------------------
// A07 soft：软件列表 / 第三方插件包弹窗的转义工具
//
// 为什么需要：插件 info.json（**包括用户上传的第三方插件包**）里的 title / ps /
// author / home / path / icon / versions 会被直接拼进列表与弹窗的 HTML，以及行内
// onclick 里的 '...' 字符串（HTML + JS 双上下文）。上传一份
// title='<img src=x onerror=alert(1)>' 的包，列表渲染即可在面板里执行脚本；
// home 写 'javascript:alert(1)' 还能变成可点击的伪协议链接。
//   yfSoftText  → HTML 文本/属性上下文
//   yfSoftJsStr → 行内 onclick 的 '...' 字符串参数
//   yfSoftUrl   → 只放行 http(s) 链接，其余返回空串
// ---------------------------------------------------------------------------------
function yfSoftText(v) {
  return String(v === undefined || v === null ? '' : v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
function yfSoftJsStr(v) {
  return String(v === undefined || v === null ? '' : v)
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/"/g, '\\"')
    .replace(/</g, '\\x3c')
    .replace(/>/g, '\\x3e')
    .replace(/\r?\n/g, '\\n');
}
function yfSoftUrl(v) {
  var s = String(v === undefined || v === null ? '' : v).trim();
  if (!/^https?:\/\//i.test(s)) return '';
  return yfSoftText(s);
}

//重置插件弹出框宽度
function resetPluginWinWidth(width) {
  $("div[id^='layui-layer'][class*='layui-layer-page']").width(width);
}

//重置插件弹出框高度
function resetPluginWinHeight(height) {
  var $layer = $("div[id^='layui-layer'][class*='layui-layer-page']");
  $layer.height(height);
  $layer.find(".layui-layer-content").height(height - 42).css({ 'overflow': 'hidden', 'height': (height - 42) + 'px' });
  $(".bt-form").height(height - 42);
  $(".bt-form .bt-w-main").height(height - 42);
  $(".bt-form .bt-w-menu").height(height - 42);
  $(".bt-form .bt-w-con").height(height - 42);
}

//嵌套子窗口 i18n 兜底
//
//为什么需要：插件常在自己的弹窗内再用 layer.open / layer.alert / layer.confirm
//打开二级窗口（新增表单、列表、确认框）。这些二级窗口挂到 document.body 下，
//不在主弹窗容器内，translatePluginDOM 的主 MutationObserver 够不着 —— 表现就是
//「主界面已翻译，点开的子窗口依然中文」（键与译文其实都在，属假翻译）。
//
//layer.open 是所有弹层的统一入口（alert / confirm / msg / tips / prompt / tab /
//photos 内部都调用同一个 r.open，而 layer === r），因此在插件窗口存续期间改写
//layer.open，把二级窗口也交给同一插件字典翻译即可一处覆盖全部插件。
//translatePluginDOM 自带的 MutationObserver 会继续兜住插件 success / ajax 后续渲染。
function installPluginLayerTranslation() {
  if (!window.layer || typeof window.layer.open !== 'function') return;
  if (window.layer.__yfPluginPatched) return;
  var origOpen = window.layer.open;
  window.layer.open = function (opts) {
    var pluginName = window._yfActivePlugin;
    if (pluginName && window.YfI18n && typeof window.YfI18n.translatePluginDOM === 'function' && opts && typeof opts === 'object') {
      var origSuccess = opts.success;
      opts.success = function (layero, index) {
        try { window.YfI18n.translatePluginDOM(layero, pluginName); } catch (e) {}
        if (typeof origSuccess === 'function') return origSuccess(layero, index);
      };
    }
    return origOpen.call(this, opts);
  };
  window.layer.__yfPluginPatched = true;
}

//软件管理窗口
function softMain(name, title, version) {
  installPluginLayerTranslation();
  window._yfActivePlugin = name;
  var _title = title;
  if (version && String(version).trim() !== '' && String(version).trim() !== 'undefined') {
    var vStr = String(version).trim();
    _title = _title.replace('-' + vStr, '').replace(' ' + vStr, '').replace(vStr, '').trim();
  }
  if (window.YfI18n && typeof window.YfI18n.loadPluginLangAsync === 'function') {
    window.YfI18n.loadPluginLangAsync(name);
  }
  var loadT = layer.msg(lan && lan.soft && t('soft.processing_please_wait') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.get('/plugins/setting?name=' + encodeURIComponent(name), function (rdata) {
    layer.close(loadT);
    var currentLang = (window.YfI18n && typeof window.YfI18n.getLanguage === 'function' ? window.YfI18n.getLanguage() : null) || (window.YfI18n && window.YfI18n.currentLang) || 'zh-CN';
    var isZh = currentLang === 'zh-CN' || currentLang === 'zh-TW';
    var manageText = (window.t && (window.t('soft.management_action') || window.t('management_action') || window.t('public.manage') || window.t('public.management_action'))) || 'Manage';
    var hasVer = (version && String(version).trim() !== '' && String(version).trim() !== 'undefined');
    var winTitle = isZh
      ? (hasVer ? (_title + '【' + version + '】管理') : (_title + '管理'))
      : (hasVer ? (_title + ' [' + version + '] ' + manageText) : (_title + ' ' + manageText));
    layer.open({
      type: 1,
      area: '640px',
      title: winTitle,
      closeBtn: 1,
      shift: 0,
      content: rdata,
      success: function (layero, index) {
        if (window.YfI18n && typeof window.YfI18n.translatePluginDOM === 'function') {
          window.YfI18n.translatePluginDOM(layero, name);
        }
      },
      end: function () {
        window._yfActivePlugin = null;
        if (typeof window.refreshExternalPluginStatus === 'function') {
          window.refreshExternalPluginStatus(name);
        }
      }
    });
    $(".bt-w-menu p").on('click', function () {
      $(this).addClass("bgw").siblings().removeClass("bgw");
    });

    //version to
    $(".plugin_version").attr('version', version).hide();
  }).fail(function () {
    // 500/网络异常时 loadT 遮罩必须关掉，否则整个面板被蒙层卡死
    layer.close(loadT);
    layer.msg(t('public.load_fail', '加载失败'), {
      icon: 2,
      time: 3000
    });
  });
}
function toggleThirdParty(isChecked) {
  localStorage.setItem('show_third_party', isChecked ? 'true' : 'false');
  getSList(1);
}
function clearPluginCache() {
  layer.confirm(lan && lan.soft && t('soft.this_action_will_clear') || "", {
    title: lan && lan.soft && t('soft.clear_the_installation_cache') || "",
    icon: 3
  }, function (index) {
    var loadT = layer.msg(lan && lan.soft && t('soft.clearing_data_please_wait') || "", {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
    $.post('/plugins/clear_cache', {
      purge_source: '1'
    }, function (rdata) {
      layer.close(loadT);
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
      $('#third_party_setting_box').hide();
    }, 'json').fail(function () {
      layer.close(loadT);
      layer.msg(t('public.operation_error', '操作失败'), {
        icon: 2
      });
    });
  });
}

//取软件列表
// 解析 URL 里的 soft_* 参数（首页「PHP 安全基线」跳转过来时用）
function softQueryParams() {
  var q = {};
  var raw = String(location.search || '').replace(/^\?/, '');
  if (!raw) return q;
  var parts = raw.split('&');
  for (var i = 0; i < parts.length; i++) {
    var kv = parts[i].split('=');
    if (!kv[0]) continue;
    try {
      q[decodeURIComponent(kv[0])] = decodeURIComponent((kv[1] || '').replace(/\+/g, ' '));
    } catch (e) {
      q[kv[0]] = kv[1] || '';
    }
  }
  return q;
}

// 定位到指定插件的指定版本，并直接打开它的管理面板（卸载按钮在里面）。
//
// 使用场景：首页「PHP 安全基线」里 7.4/8.0/8.1 那一行的「建议卸载该版本并升级到
// PHP 8.2 及以上」是可点的 —— 点了要能一步到那个版本的卸载入口，而不是让用户自己在
// 几十个插件、多个分页里翻。
function softFocusTarget() {
  var q = softQueryParams();
  var name = q.soft_name || '';
  if (!name) return;
  var ver = q.soft_version || '';
  // 只认面板里的插件名形态（字母/数字/下划线/连字符），避免把任意参数拼进选择器
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(name)) return;
  if (ver && !/^[A-Za-z0-9._-]{1,32}$/.test(ver)) return;
  var sel = '#softList tr[data-name="' + name + '"]' + (ver ? '[data-version="' + ver + '"]' : '');
  var $row = $(sel).first();
  if (!$row.length) return;
  $row.css('background-color', '#fff7e6');
  try {
    if ($row[0].scrollIntoView) $row[0].scrollIntoView({ block: 'center' });
  } catch (e) {}
  if (window.__yfSoftFocused === name + '|' + ver) return;   // 避免轮询反复弹窗
  window.__yfSoftFocused = name + '|' + ver;
  var title = $.trim($row.find('td').eq(0).text()) || (name + (ver ? '-' + ver : ''));
  softMain(name, title, ver);
}

function getSList(isdisplay) {
  var loadT = null;
  if (isdisplay !== true) {
    loadT = layer.msg(lan && lan.soft && t('soft.retrieving_the_list') || "", {
      icon: 16,
      time: 0,
      shade: [0.3, '#000']
    });
  }
  if (!isdisplay || isdisplay === true) isdisplay = getCookie('p' + getCookie('soft_type'));
  if (isdisplay == true || isdisplay == 'true') isdisplay = 1;
  var search = $("#SearchValue").val();
  if (search != '') {
    search = '&search=' + search;
  }
  var type = '';
  var istype = getCookie('soft_type');
  if (istype == 'undefined' || istype == 'null' || !istype) {
    istype = '0';
  }
  type = '&type=' + istype;
  var page = '';
  if (isdisplay) {
    page = '&p=' + isdisplay;
    setCookie('p' + getCookie('soft_type'), isdisplay);
  }
  var show_third_party = '';
  var isShowThirdParty = localStorage.getItem('show_third_party') === 'true';
  if (isShowThirdParty) {
    show_third_party = '&show_third_party=1';
  }

  // 更新checkbox状态
  setTimeout(function () {
    var chk = document.getElementById('show_third_party_chk');
    if (chk) chk.checked = isShowThirdParty;
  }, 100);
  var condition = (search + type + page + show_third_party).slice(1);
  var reqUrl = '/plugins/list?' + condition + (condition ? '&' : '') + '_t=' + new Date().getTime();
  $.get(reqUrl, '', function (rdata) {
    if (loadT) {
      layer.close(loadT);
    }
    var tBody = '';
    var sBody = '';
    var pBody = '';
    var typeKeyMap = {
      '0': 'soft.type_all',
      '-1': 'soft.type_installed',
      '1': 'soft.type_runtime',
      '2': 'soft.type_database',
      '3': 'soft.type_code_mgr',
      '4': 'soft.type_system_tools',
      '5': 'soft.type_other_plugins',
      '6': 'soft.type_php'
    };
    for (var i = 0; i < rdata.type.length; i++) {
      var typeItem = rdata.type[i];
      var c = '';
      if (istype == typeItem.type) {
        c = 'class="on"';
      }
      var i18nKey = typeItem.key || typeKeyMap[typeItem.type] || ('soft.type_' + typeItem.type);
      var typeTitle = (typeof t === 'function') ? t(i18nKey, typeItem.title) : typeItem.title;
      tBody += '<span typeid="' + typeItem.type + '" data-i18n="' + i18nKey + '" ' + c + '>' + typeTitle + '</span>';
    }
    $(".softtype").html(tBody);
    $("#softPage").html(rdata.list);
    $("#softPage .Pcount").css({
      "position": "absolute",
      "left": "0"
    });
    $(".task").text(rdata.data[rdata.length - 1]);
    for (var i = 0; i < rdata.data.length; i++) {
      var plugin = rdata.data[i];
      var len = plugin.versions.length;
      var version_info = '';
      var version = '';
      var softPath = '';
      var titleClick = '';
      var state = '';
      var indexshow = '';
      var checked = '';
      checked = plugin.display ? 'checked' : '';
      if (typeof plugin.versions == "string") {
        version_info += plugin.versions + '|';
      } else {
        for (var j = 0; j < len; j++) {
          version_info += plugin.versions[j] + '|';
        }
      }
      if (version_info != '') {
        version_info = version_info.substring(0, version_info.length - 1);
      }
      var raw_title = t('plugins.' + plugin.name + '.title', plugin.title);
      var raw_ps = t('plugins.' + plugin.name + '.ps', plugin.ps);
      var display_title = raw_title;
      if (plugin.coexist) {
        // 已安装的 coexist 插件（PHP 各分支）：连「真实运行时版本」一起显示。
        // 以前只有分支号（PHP-83），用户看不出自己跑的是 8.3.30 还是 8.3.36。
        display_title = raw_title + '-' + plugin.versions;
        if (plugin.php_current_version) {
          display_title += ' ' + plugin.php_current_version;
        }
      } else if (plugin.setup && plugin.setup_version) {
        display_title = raw_title + ' ' + plugin.setup_version;
      }

      var handle = '<a class="btlink" onclick="addVersion(\'' + yfSoftJsStr(plugin.name) + '\',\'' + yfSoftJsStr(version_info) + '\',\'' + yfSoftJsStr(plugin.tip) + '\',this,\'' + yfSoftJsStr(display_title) + '\',' + plugin.install_pre_inspection + ');">' + t('public.install', '安装') + '</a>';
      if (plugin.setup == true) {
        var mupdate = '';
        var latest_version = '';
        if (plugin.versions) {
          if (typeof plugin.versions == 'string') {
            latest_version = plugin.versions;
          } else if (Array.isArray(plugin.versions) && plugin.versions.length > 0) {
            latest_version = plugin.versions[plugin.versions.length - 1];
          }
        }
        if (plugin.setup_version && latest_version && plugin.setup_version != latest_version) {
          // 主版本一致性安全校验，防止跨分支/大版本强制升级导致依赖的服务及数据崩溃
          var current_major = plugin.setup_version.toString().split('.')[0];
          var latest_major = latest_version.toString().split('.')[0];
          if (current_major === latest_major) {
            // 语义化版本对比：如果当前安装版本(current_ver)低于官方最新版本(latest_ver)，才提示更新
            var needUpdate = false;
            var c_parts = plugin.setup_version.toString().split('.');
            var l_parts = latest_version.toString().split('.');
            var maxLen = Math.max(c_parts.length, l_parts.length);
            for (var vi = 0; vi < maxLen; vi++) {
              var cp = parseInt(c_parts[vi]) || 0;
              var lp = parseInt(l_parts[vi]) || 0;
              if (cp < lp) {
                needUpdate = true;
                break;
              } else if (cp > lp) {
                needUpdate = false;
                break;
              }
            }
            if (needUpdate) {
              mupdate = '<a class="btlink" onclick="softUpdate(\'' + yfSoftJsStr(plugin.name) + '\',\'' + yfSoftJsStr(latest_version) + '\',\'' + yfSoftJsStr(plugin.setup_version) + '\');">' + t('public.update', '更新') + '</a> | ';
            }
          }
        }
        var settingsLink = '<a class="btlink" onclick="softMain(\'' + yfSoftJsStr(plugin.name) + '\',\'' + yfSoftJsStr(display_title) + '\',\'' + yfSoftJsStr(plugin.setup_version) + '\')">' + t('public.set', '设置') + '</a>';
        var uninstallLink = '<a class="btlink" onclick="uninstallVersion(\'' + yfSoftJsStr(plugin.name) + '\',\'' + yfSoftJsStr(display_title) + '\',\'' + yfSoftJsStr(plugin.setup_version) + '\',' + plugin.uninstall_pre_inspection + ')">' + t('public.uninstall', '卸载') + '</a>';
        // PHP 分支有新补丁版时给一个「升级到 x.y.z」入口：只投递后台任务
        // （目标版本与官方哈希由后端决定，见 plugins/php/index.py::getUpgradeTarget）。
        var phpUpdateLink = '';
        if (plugin.php_update_available && plugin.php_update) {
          phpUpdateLink = '<a class="btlink" style="color:#ff2020" title="' +
            yfSoftText(t('soft.php_upgrade_tip', '将重新编译 PHP（约 10~30 分钟），完成后自动重启 FPM；失败会自动还原旧版本。')) + '"' +
            ' onclick="phpUpgradeSoft(\'' + yfSoftJsStr(plugin.name) + '\',\'' + yfSoftJsStr(plugin.versions) +
            '\',\'' + yfSoftJsStr(plugin.php_update.current || '') + '\',\'' + yfSoftJsStr(plugin.php_update.latest || '') + '\')">' +
            yfSoftText(t('soft.upgrade_to', '升级到')) + ' ' + yfSoftText(plugin.php_update.latest || '') + '</a> | ';
        }
        handle = mupdate + phpUpdateLink + settingsLink + ' | ' + uninstallLink;
        titleClick = 'onclick="softMain(\'' + yfSoftJsStr(plugin.name) + '\',\'' + yfSoftJsStr(display_title) + '\',\'' + yfSoftJsStr(plugin.setup_version) + '\')" style="cursor:pointer"';
        softPath = '<span class="glyphicon glyphicon-folder-open" title="' + yfSoftText(plugin.path) + '" onclick="openPath(\'' + yfSoftJsStr(plugin.path) + '\')"></span>';
        if (plugin.coexist) {
          indexshow = '<div class="index-item">\
                        <input class="btswitch btswitch-ios" id="index_' + yfSoftText(plugin.name) + yfSoftText(plugin.versions) + '" type="checkbox" ' + checked + '>\
                        <label class="btswitch-btn" for="index_' + yfSoftText(plugin.name) + yfSoftText(plugin.versions) + '" onclick="toIndexDisplay(\'' + yfSoftJsStr(plugin.name) + '\',\'' + yfSoftJsStr(plugin.versions) + '\',\'' + yfSoftJsStr(plugin.coexist) + '\')"></label>\
                    </div>';
        } else {
          indexshow = '<div class="index-item">\
                        <input class="btswitch btswitch-ios" id="index_' + yfSoftText(plugin.name) + '" type="checkbox" ' + checked + '>\
                        <label class="btswitch-btn" for="index_' + yfSoftText(plugin.name) + '" onclick="toIndexDisplay(\'' + yfSoftJsStr(plugin.name) + '\',\'' + yfSoftJsStr(plugin.setup_version) + '\')"></label>\
                    </div>';
        }
        var pluginStatusVal = plugin.status;
        if (window.__plugin_pending_status && plugin.name) {
          var pNameKey = String(plugin.name).toLowerCase();
          if (window.__plugin_pending_status[pNameKey]) {
            var pItem = window.__plugin_pending_status[pNameKey];
            if (Date.now() < pItem.expire) {
              pluginStatusVal = pItem.status;
            } else {
              delete window.__plugin_pending_status[pNameKey];
            }
          }
        }
        if (plugin.display_status === false) {
          state = '<span style="color:#999">-</span>';
        } else if (pluginStatusVal == true) {
          state = '<span style="color:#20a53a" class="glyphicon glyphicon-play"></span>';
        } else {
          state = '<span style="color:red" class="glyphicon glyphicon-pause"></span>';
        }
      }
      if (plugin.task == '-2') {
        handle = '<a style="color:green;" href="javascript:task();">' + t('public.uninstalling', '正在卸载...') + '</a>';
      } else if (plugin.task == '-1') {
        handle = '<a style="color:green;" href="javascript:task();">' + t('public.installing', '正在安装...') + '</a>';
      } else if (plugin.task == '0') {
        handle = '<a style="color:#C0C0C0;" href="javascript:task();">' + t('public.waiting', '等待中...') + '</a>';
      }

      var plugin_title = yfSoftText(display_title);
      if (plugin.display_level == 1) {
        plugin_title += t('soft.size_third_party', ' (第三方插件)');
      }
      if (plugin.php_update_available && plugin.php_update) {
        plugin_title += '<span class="php-update-badge" style="margin-left:6px;padding:1px 6px;border-radius:9px;' +
          'background:#ff2020;color:#fff;font-size:11px;line-height:16px;display:inline-block;vertical-align:middle;">' +
          yfSoftText(t('soft.php_upgradable', '可更新')) + '</span>';
      }
      // PHP < 8.2 已停止维护：后端只在**确实装了**的情况下把旧分支留在列表里
      // （未安装的直接不返回），这里红字提醒升级，别让人继续拿它跑业务。
      if (plugin.php_eol) {
        plugin_title += '<span class="php-eol-badge" style="margin-left:6px;padding:1px 6px;border-radius:9px;' +
          'background:#ff2020;color:#fff;font-size:11px;line-height:16px;display:inline-block;vertical-align:middle;"' +
          ' title="' + yfSoftText(t('soft.php_eol_tip', '该 PHP 分支官方已停止维护，不再提供安全修复，建议卸载后升级到 PHP 8.2 及以上。')) + '">' +
          yfSoftText(t('soft.php_eol', [plugin.php_eol_min || '8.2'],
            '建议升级到 ' + (plugin.php_eol_min || '8.2') + ' 及以上')) + '</span>';
      }
      if (plugin.service_alarm) {
        // 《问题报告》P2-2：已装插件的服务存在崩循环/启动失败/刚被停掉时，
        // 在插件名旁边打一个红色标记，并把「插件名 + 最近失败原因」放进 tooltip。
        // 数据来自后台 5 分钟一次的服务存活巡检（data/service_patrol.json），
        // 前端不做任何探测、不自动重启。
        var _alarm = plugin.service_alarm || {};
        var _alarmTip = String(_alarm.label || '') + (String(_alarm.reason || '').trim() ? '：' + String(_alarm.reason) : '');
        if (_alarm.unit) {
          _alarmTip += ' [' + String(_alarm.unit) + ']';
        }
        plugin_title += '<span class="service-alarm-badge" style="margin-left:6px;padding:1px 6px;border-radius:9px;' +
          'background:#c0392b;color:#fff;font-size:11px;line-height:16px;display:inline-block;vertical-align:middle;"' +
          ' title="' + yfSoftText(_alarmTip) + '">' +
          yfSoftText(t('soft.service_alarm', '服务异常')) + '</span>';
      }
      icon_link = "/plugins/file?name=" + encodeURIComponent(plugin.name) + "&f=ico.png";
      if (plugin.icon != '') {
        icon_link = "/plugins/file?name=" + encodeURIComponent(plugin.name) + "&f=" + encodeURIComponent(plugin.icon);
      }
      var homeLink = yfSoftUrl(plugin.home) ? ('<a class="btlink" href="' + yfSoftUrl(plugin.home) + '" target="_blank">' + t('soft.official_site', '官网') + '</a>') : '-';
      // data-version 让「从首页跳过来定位某个 PHP 版本」能精确命中这一行
      // （coexist 插件每行 data-name 都相同，只有版本不同）
      sBody += '<tr data-name="' + yfSoftText(plugin.name) + '" data-version="' + yfSoftText(plugin.versions) + '">' + '<td><span ' + titleClick + '>' + '<img data-src="' + icon_link + '" src="/static/img/loading.gif">' + plugin_title + '</span></td>' + '<td>' + yfSoftText(raw_ps) + '</td>' + '<td>' + homeLink + '</td>' + '<td>' + yfSoftText(plugin.date ? plugin.date : '-') + '</td>' + '<td>' + softPath + '</td>' + '<td class="plugin-status-col" data-plugin="' + yfSoftText(plugin.name) + '">' + state + '</td>' + '<td>' + indexshow + '</td>' + '<td style="text-align: right;">' + handle + '</td>' + '</tr>';
    }
    sBody += pBody;
    $("#softList").html(sBody);
    softFocusTarget();
    $(".menu-sub span").off("click").on('click', function () {
      setCookie('soft_type', $(this).attr('typeid'));
      $(this).addClass("on").siblings().removeClass("on");
      getSList();
    });
    loadImage();

    // 渲染完软件列表后同步左上角任务角标
    getTaskCount();

    // 智能自适应轮询
    var has_active_task = false;
    if (rdata.data) {
      for (var k = 0; k < rdata.data.length; k++) {
        var p_item = rdata.data[k];
        if (p_item && (p_item.task == '-2' || p_item.task == '-1' || p_item.task == '0')) {
          has_active_task = true;
          break;
        }
      }
    }
    if (window.softTimer) clearTimeout(window.softTimer);
    if (window.document.location.pathname.indexOf('/soft') === 0 || window.document.location.pathname.indexOf('/plugins') === 0) {
      var delay = has_active_task ? 8000 : 30000; // 有任务8秒，无任务30秒
      if (document.visibilityState !== 'visible') delay = 60000; // 后台标签页进一步降频
      window.softTimer = setTimeout(function () {
        getSList(true); // 传入 true，避免弹出 loading 遮罩
      }, delay);
    }
  }, 'json').fail(function () {
    // 只在「有遮罩」的主动刷新里提示；轮询失败静默，但遮罩一定要关
    if (loadT) {
      layer.close(loadT);
      layer.msg(t('public.load_fail', '加载失败'), {
        icon: 2,
        time: 3000
      });
    }
  });
}
function installPreInspection(name, ver, callback) {
  var loading = layer.msg(lan && lan.soft && t('soft.checking_the_installation_environment') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post("/plugins/run", {
    'name': name,
    'version': ver,
    'func': 'install_pre_inspection'
  }, function (rdata) {
    layer.close(loading);
    if (rdata.status) {
      if (rdata.data == 'ok') {
        callback();
      } else {
        layer.msg(rdata.data, {
          icon: 2
        });
      }
    } else {
      layer.msg(rdata.data, {
        icon: rdata.status ? 1 : 2
      });
    }
  }, 'json').fail(function () {
    layer.close(loading);
    layer.msg(t('public.ERROR', '操作失败'), {
      icon: 2
    });
  });
}
function runInstall(data) {
  var loadT = layer.msg(lan && lan.soft && t('soft.adding_to_the_installer') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post("/plugins/install", data, function (rdata) {
    layer.closeAll();
    layer.msg(rdata.msg, {
      icon: rdata.status ? 1 : 2
    });
    getSList();
    getTaskCount();
  }, 'json').fail(function () {
    layer.closeAll();
    layer.msg(t('public.ERROR', '操作失败'), {
      icon: 2
    });
  });
}
function addVersion(name, ver, type, obj, title, install_pre_inspection) {
  var option = '';
  var titlename = title.replace("-" + ver, "");
  // 安装弹窗会把插件自带的 install.html 原样注入（见下方 customHtmlPath），
  // 那段内容是插件的界面文案，必须走插件字典翻译。与 softMain 保持一致：
  // 先异步预热语言包（命中缓存则零开销），弹窗 success 里再做 DOM 翻译。
  if (window.YfI18n && typeof window.YfI18n.loadPluginLangAsync === 'function') {
    window.YfI18n.loadPluginLangAsync(name);
  }
  if (ver.indexOf('|') >= 0) {
    var veropt = ver.split("|");
    var selectVersion = '';
    for (var i = veropt.length - 1; i >= 0; i--) {
      selectVersion += '<option>' + yfSoftText(name + ' ' + veropt[i]) + '</option>';
    }
    option = "<select id='selectVersion' class='bt-input-text' style='margin-left:30px'>" + selectVersion + "</select>";
  } else {
    option = '<span id="selectVersion" val="' + yfSoftText(name + ' ' + ver) + '">【' + yfSoftText(titlename) + '】 ' + yfSoftText(ver) + '</span>';
  }
  var customHtmlPath = "/plugins/file?name=" + encodeURIComponent(name) + "&f=install.html";
  $.get(customHtmlPath, function (customHtml) {
    if (typeof customHtml !== 'string' || customHtml.indexOf('404 Not Found') > -1 || customHtml.indexOf('{"status":false') > -1 || customHtml.trim() === '') {
      customHtml = '';
    }
    var layerArea = customHtml ? '540px' : '380px';
    layer.open({
      type: 1,
      title: (lan && lan.soft && t('soft.installation') || "") + yfSoftText(titlename),
      area: layerArea,
      closeBtn: 1,
      shadeClose: true,
      btn: [lan && lan.soft && t('soft.submit') || "", lan && lan.soft && t('soft.close') || ""],
      content: "<div class='bt-form pd20 c6'><div class='version line'>" + (lan && lan.soft && lan.soft.install_version || '安装版本：') + option + "</div>" + customHtml + "\
            </div>",
      success: function (layero) {
        // install.html 里的中文（安装方式、耗时预估、说明段落等）在此翻译。
        // 字典未预热时 translatePluginDOM 内部会同步保底拉取，不会漏翻。
        if (window.YfI18n && typeof window.YfI18n.translatePluginDOM === 'function') {
          window.YfI18n.translatePluginDOM(layero, name);
        }
        $('.fangshi input').on('click', function () {
          $(this).attr('checked', 'checked').parent().siblings().find("input").removeAttr('checked');
        });
        installTips();
      },
      yes: function (index, layero) {
        var info = $("#selectVersion").val();
        if (info == null || info == undefined || info == '') {
          info = $("#selectVersion").attr('val');
        }
        info = info.toLowerCase();
        var info_split = info.split(' ');
        var plugin_name = info_split[0];
        var version = info_split[1];
        if (typeof window['install_hook_' + plugin_name] === 'function') {
          version = window['install_hook_' + plugin_name](version);
        }
        var type = $('.fangshi').prop("checked") ? '1' : '0';
        installPluginScriptConfirm(plugin_name, function (token) {
          var request_args = "name=" + plugin_name + "&version=" + version + "&type=" + type;
          if (token) {
            request_args += "&confirm_token=" + encodeURIComponent(token);
          }
          if (install_pre_inspection) {
            //安装前置检测
            installPreInspection(plugin_name, version, function () {
              runInstall(request_args);
              flySlow('layui-layer-btn0');
            });
            return;
          }
          runInstall(request_args);
          flySlow('layui-layer-btn0');
        });
      }
    });
  }).fail(function () {
    layer.open({
      type: 1,
      title: (lan && lan.soft && t('soft.installation_1') || "") + yfSoftText(titlename),
      area: '380px',
      closeBtn: 1,
      shadeClose: true,
      btn: [lan && lan.soft && t('soft.submit_1') || "", lan && lan.soft && t('soft.close_1') || ""],
      content: "<div class='bt-form pd20 c6'><div class='version line'>" + (lan && lan.soft && lan.soft.install_version || '安装版本：') + option + "</div>\
            </div>",
      success: function () {
        $('.fangshi input').on('click', function () {
          $(this).attr('checked', 'checked').parent().siblings().find("input").removeAttr('checked');
        });
        installTips();
      },
      yes: function (index, layero) {
        var info = $("#selectVersion").val();
        if (info == null || info == undefined || info == '') {
          info = $("#selectVersion").attr('val');
        }
        info = info.toLowerCase();
        var info_split = info.split(' ');
        var plugin_name = info_split[0];
        var version = info_split[1];
        var type = $('.fangshi').prop("checked") ? '1' : '0';
        installPluginScriptConfirm(plugin_name, function (token) {
          var request_args = "name=" + plugin_name + "&version=" + version + "&type=" + type;
          if (token) {
            request_args += "&confirm_token=" + encodeURIComponent(token);
          }
          if (install_pre_inspection) {
            //安装前置检测
            installPreInspection(plugin_name, version, function () {
              runInstall(request_args);
              flySlow('layui-layer-btn0');
            });
            return;
          }
          runInstall(request_args);
          flySlow('layui-layer-btn0');
        });
      }
    });
  });
}

// 强制删除插件
function forceUninstallPlugin(name, version) {
  var contentHtml = "<div class='bt-form pd20 c6'><div style='color: red; font-weight: bold; font-size: 14px; margin-bottom: 10px;'>" + t('soft.uninstall_warning1') + yfSoftText(name) + t('soft.uninstall_warning2') + "</div><div class='line' style='margin-bottom: 0px;'><span style='display: block; margin-bottom: 10px;'>" + t('soft.uninstall_warning3') + " <b>" + yfSoftText(name) + "</b> " + t('soft.uninstall_warning4') + "</span><input type='text' id='force_uninstall_confirm_name' class='bt-input-text' style='width: 200px;' placeholder='" + t('soft.please_input') + "' /></div>" +
    "<div style='margin-top: 15px; display: flex; align-items: center; justify-content: flex-start;'>" +
    "<label style='font-weight: normal; cursor: pointer; display: flex; align-items: center; margin-bottom: 0;'>" +
    "<input type='checkbox' id='force_uninstall_backup_chk' checked='checked' style='margin-right: 8px; width: 16px; height: 16px; cursor: pointer;' />" +
    t('soft.uninstall_backup_tip', '卸载前将数据打包备份到 /www/backup (.tar.gz)') +
    "</label>" +
    "</div>" +
    "</div>";
  layer.open({
    type: 1,
    title: lan && lan.soft && t('soft.confirm_forced_deletion_high') || "",
    area: '420px',
    closeBtn: 1,
    shadeClose: false,
    btn: [lan && lan.soft && t('soft.forced_deletion') || "", lan && lan.soft && t('soft.cancel') || ""],
    content: contentHtml,
    yes: function (index, layero) {
      var confirmName = String($("#force_uninstall_confirm_name").val()).trim();
      if (confirmName !== name) {
        layer.msg(lan && lan.soft && t('soft.the_plugin_name_you') || "", {
          icon: 2
        });
        return false;
      }
      var isBackup = $("#force_uninstall_backup_chk").prop("checked") ? 1 : 0;
      layer.close(index);
      var forceLoad = layer.msg(lan && lan.soft && t('soft.forced_deletion_in_progress') || "", {
        icon: 16,
        time: 0,
        shade: [0.3, '#000']
      });
      $.post('/plugins/uninstall', {
        name: name,
        version: version,
        force: 1,
        backup: isBackup
      }, function (forceRdata) {
        layer.close(forceLoad);
        getSList();
        getTaskCount();
        layer.msg(forceRdata.msg, {
          icon: forceRdata.status ? 1 : 2
        });
      }, 'json').fail(function () {
        layer.close(forceLoad);
        layer.msg(t('public.ERROR', '操作失败'), {
          icon: 2
        });
      });
    }
  });
}

//卸载软件
function uninstallPreInspection(name, title, ver, callback) {
  var loading = layer.msg(lan && lan.soft && t('soft.checking_the_uninstallation_environment') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post("/plugins/run", {
    'name': name,
    'version': ver,
    'func': 'uninstall_pre_inspection'
  }, function (rdata) {
    layer.close(loading);
    if (rdata.status) {
      if (rdata.data == 'ok') {
        if (typeof callback == 'function') {
          callback();
        }
      } else {
        layer.confirm(rdata.data + '<br><span style="color: red;">' + (lan && lan.soft && lan.soft.uninstall_fail_confirm || '卸载环境检查失败，是否要强制删除该插件？') + '</span>', {
          title: lan && lan.soft && t('soft.uninstall_failure_message') || "",
          icon: 2,
          closeBtn: 1,
          btn: [lan && lan.soft && t('soft.forced_deletion_1') || "", lan && lan.soft && t('soft.cancel_1') || ""]
        }, function () {
          forceUninstallPlugin(name, ver);
        });
      }
    } else {
      layer.confirm(rdata.data + '<br><span style="color: red;">' + (lan && lan.soft && lan.soft.uninstall_fail_confirm || '卸载环境检查失败，是否要强制删除该插件？') + '</span>', {
        title: lan && lan.soft && t('soft.uninstall_failure_message_1') || "",
        icon: 2,
        closeBtn: 1,
        btn: [lan && lan.soft && t('soft.forced_deletion_2') || "", lan && lan.soft && t('soft.cancel_2') || ""]
      }, function () {
        forceUninstallPlugin(name, ver);
      });
    }
  }, 'json').fail(function () {
    layer.close(loading);
    layer.msg(t('public.ERROR', '操作失败'), {
      icon: 2
    });
  });
}
function runUninstallVersion(name, title, version) {
  var pureTitle = title.replace("-" + version, "");
  var pluginTitle = pureTitle + "-" + version;
  var confirmTip = t('soft.uninstall_confirm_prefix', '您真的要卸载【') + yfSoftText(pluginTitle) + t('soft.uninstall_confirm_suffix', '】吗？');
  var backupTip = t('soft.uninstall_backup_tip', '卸载前将数据打包备份到 /www/backup (.tar.gz)');
  var contentHtml = "<div class='bt-form pd20 c6'>" +
    "<div class='line' style='margin-bottom: 15px;'>" +
    "<span style='font-size:14px;'>" + confirmTip + "</span>" +
    "</div>" +
    "<div style='margin-top: 15px; display: flex; align-items: center; justify-content: flex-start;'>" +
    "<label style='font-weight: normal; cursor: pointer; display: flex; align-items: center; margin-bottom: 0;'>" +
    "<input type='checkbox' id='normal_uninstall_backup_chk' checked='checked' style='margin-right: 8px; width: 16px; height: 16px; cursor: pointer;' />" +
    backupTip +
    "</label>" +
    "</div>" +
    "</div>";
  layer.open({
    type: 1,
    title: t('soft.software_uninstallation_confirmation', '卸载软件确认'),
    area: '420px',
    closeBtn: 1,
    shadeClose: false,
    btn: [t('soft.confirm_uninstall', '确认卸载'), t('soft.cancel', '取消')],
    content: contentHtml,
    yes: function (index, layero) {
      var isBackup = $("#normal_uninstall_backup_chk").prop("checked") ? 1 : 0;
      layer.close(index);
      var data = 'name=' + name + '&version=' + version + '&backup=' + isBackup;
      var loadT = layer.msg(t('soft.processing_please_wait_1', '正在处理,请稍候...'), {
        icon: 16,
        time: 0,
        shade: [0.3, '#000']
      });
      $.post('/plugins/uninstall', data, function (rdata) {
        layer.close(loadT);
        if (rdata.status) {
          getSList();
          getTaskCount();
          layer.msg(rdata.msg, {
            icon: 1
          });
        } else {
          layer.confirm(rdata.msg + (lan && lan.soft && t('soft.red_the_red_plugin') || ""), {
            title: lan && lan.soft && t('soft.uninstall_failure_message_2') || "",
            icon: 2,
            closeBtn: 1,
            btn: [lan && lan.soft && t('soft.forced_deletion_3') || "", lan && lan.soft && t('soft.cancel_4') || ""]
          }, function () {
            forceUninstallPlugin(name, version);
          });
        }
      }, 'json').fail(function () {
        layer.close(loadT);
        layer.msg(t('public.ERROR', '操作失败'), {
          icon: 2
        });
      });
    }
  });
}
function uninstallVersion(name, title, version, uninstall_pre_inspection) {
  if (uninstall_pre_inspection) {
    uninstallPreInspection(name, title, version, function () {
      runUninstallVersion(name, title, version);
    });
  } else {
    runUninstallVersion(name, title, version);
  }
}

//首页显示
function toIndexDisplay(name, version, coexist) {
  var status = $("#index_" + name).prop("checked") ? "0" : "1";
  if (coexist == "true") {
    var verinfo = version.replace(/\./, "");
    status = $("#index_" + name + verinfo).prop("checked") ? "0" : "1";
  }
  var data = "name=" + name + "&status=" + status + "&version=" + version;
  $.post("/plugins/set_index", data, function (rdata) {
    if (rdata.status) {
      layer.msg(rdata.msg, {
        icon: 1
      });
    } else {
      layer.msg(rdata.msg, {
        icon: 2
      });
    }
  }, 'json').fail(function () {
    // 失败要如实反馈，否则开关停在假状态（服务端实际没改）
    layer.msg(t('public.ERROR', '操作失败'), {
      icon: 2
    });
  });
}
var SOFT_CACHE_KEY = 'index_soft_cache_html_v3';

function indexListHtml(callback) {
  // 自动清理旧版本带版本号的历史缓存，确保即时呈现纯净软件标题
  try {
    localStorage.removeItem('index_soft_cache_html');
  } catch (e) {}

  var cacheHtml = localStorage.getItem(SOFT_CACHE_KEY);
  var hasCache = false;
  if (cacheHtml) {
    $("#indexsoft").html(cacheHtml);
    autoFitSoftName();
    hasCache = true;
    if (typeof callback == 'function') {
      callback();
    }
  } else {
    // init
    $("#indexsoft").html('');
    var index_soft = '';
    for (var i = 0; i < 18; i++) {
      index_soft += '<div class="col-xs-4 col-sm-3 col-md-2 col-lg-2 no-bg"></div>';
    }
    $("#indexsoft").html(index_soft);
  }

  // var loadT = layer.msg('正在获取列表...', { icon: 16, time: 0, shade: [0.3, '#000'] });
  $.get('/plugins/index_list?simple=1', function (rdata) {
    var rdata = rdata.data;
    // layer.close(loadT);
    var con = '';
    for (var i = 0; i < rdata.length; i++) {
      var plugin = rdata[i];
      var len = plugin.versions.length;
      var version_info = '';
      if (typeof plugin.versions == "string") {
        version_info += plugin.versions + '|';
      } else {
        for (var j = 0; j < len; j++) {
          version_info += plugin.versions[j] + '|';
        }
      }
      if (version_info != '') {
        version_info = version_info.substring(0, version_info.length - 1);
      }
      var state = '';
      if (plugin.display_status === false) {
        state = '';
      } else if (plugin.status == true) {
        state = '<span class="glyphicon glyphicon-play"></span>';
      } else {
        state = '<span class="glyphicon glyphicon-pause"></span>';
      }
      var raw_title = t('plugins.' + plugin.name + '.title', plugin.title);
      // 首页卡片名称不显示版本号，大幅精简文本长度提升美观度
      var name = raw_title;
      var data_id = plugin.name + '-' + plugin.setup_version;
      if (plugin.coexist) {
        data_id = plugin.name + '-' + plugin.versions;
      }
      // 根据软件标题视觉字数预赋最佳初始字号，杜绝首屏跳动
      var vlen = 0;
      for (var k = 0; k < raw_title.length; k++) {
        vlen += raw_title.charCodeAt(k) > 127 ? 1 : 0.55;
      }
      var fontStyle = '';
      if (vlen > 8.5) {
        fontStyle = ' style="font-size: 10px;"';
      } else if (vlen > 6.5) {
        fontStyle = ' style="font-size: 11px;"';
      }

      con += '<div class="col-xs-4 col-sm-3 col-md-2 col-lg-2" data-id="' + yfSoftText(data_id) + '">\
                <span class="spanmove"></span>\
                <div class="soft-card-box neu-btn-card" onclick="softMain(\'' + yfSoftJsStr(plugin.name) + '\',\'' + yfSoftJsStr(raw_title) + '\',\'' + yfSoftJsStr(plugin.setup_version) + '\')">\
                <div class="image"><img bk-src="/static/img/loading.gif" src="/plugins/file?name=' + encodeURIComponent(plugin.name) + '&f=ico.png" style="max-width:36px;"></div>\
                <div class="sname"' + fontStyle + ' title="' + yfSoftText(raw_title) + '">' + yfSoftText(name) + state + '</div>\
                </div>\
            </div>';

      // loadImage();
    }

    // 软件位置移动与补充18个卡片槽位
    var softboxlen = rdata.length;
    var softboxsum = 18;
    var softboxcon = '';
    if (softboxlen <= softboxsum) {
      for (var i = 0; i < softboxsum - softboxlen; i++) {
        softboxcon += '<div class="col-xs-4 col-sm-3 col-md-2 col-lg-2 no-bg" data-id=""></div>';
      }
    }
    var newFullHtml = con + softboxcon;

    // Anti-Flicker 防抖防闪烁比对
    if (hasCache && cacheHtml === newFullHtml) {
      autoFitSoftName();
      return;
    }
    // 拖拽防扰保护：若用户正在按住拖拽卡片，暂缓 DOM 覆盖，交由拖拽完成后的 saveOrder 同步
    if ($("#indexsoft .dashed-border").length > 0 || $("#indexsoft > div[style*='position: absolute']").length > 0) {
      return;
    }
    $("#indexsoft").html(newFullHtml);
    localStorage.setItem(SOFT_CACHE_KEY, newFullHtml);
    autoFitSoftName();
    if (typeof callback == 'function') {
      callback();
    }
  }, 'json');
}

// 自动测量并缩小长标题字体以完美适配卡片宽度
function autoFitSoftName() {
  $("#indexsoft .soft-card-box .sname").each(function () {
    var el = this;
    if (el.scrollWidth > el.clientWidth && el.clientWidth > 0) {
      for (var s = 11.5; s >= 9; s -= 0.5) {
        el.style.fontSize = s + 'px';
        if (el.scrollWidth <= el.clientWidth) {
          break;
        }
      }
    }
  });
}

// 监听窗口尺寸变化，动态微调卡片文本字号
$(window).off('resize.softName').on('resize.softName', function () {
  autoFitSoftName();
});

//首页软件列表
function indexSoft(onFirstRender) {
  indexListHtml(function () {
    autoFitSoftName();
    // 彻底解绑旧监听，防范重复初始化导致的多控制器冲突与双虚线框
    try {
      $("#indexsoft").trigger("dragsort-uninit");
      $("#indexsoft").dragsort("destroy");
    } catch (e) {}

    $("#indexsoft").dragsort({
      dragSelector: ".spanmove",
      dragBetween: false,
      dragEnd: saveOrder,
      placeHolderTemplate: "<div class='col-xs-4 col-sm-3 col-md-2 col-lg-2 dashed-border'></div>"
    });

    // 软件卡片第一次被绘制（无论是缓存秒开，还是首发远端）
    if (typeof onFirstRender == 'function' && !window.isStatusLoaded) {
      window.isStatusLoaded = true;
      onFirstRender();
    }
  });

  function saveOrder() {
    var data = $("#indexsoft > div").map(function () {
      return $(this).attr("data-id");
    }).get();
    var tmp = [];
    for (var i = 0; i < data.length; i++) {
      var did = data[i];
      if (did && String(did).trim() !== '') {
        tmp.push(String(did).trim());
      }
    }
    var ssort = tmp.join("|");
    $("input[name=list1SortOrder]").val(ssort);

    // 严禁在此处同步直接操作 DOM 子节点，以防打断 dragsort 内部 dropItem 归位生命周期导致图标丢失；
    // 延迟 50ms 写入本地缓存，确保拖拽库彻底恢复原始状态和完成 DOM 归位
    setTimeout(function () {
      localStorage.setItem(SOFT_CACHE_KEY, $("#indexsoft").html());
    }, 50);

    $.post("/plugins/index_sort", 'ssort=' + ssort, function (rdata) {
      if (!rdata.status) {
        showMsg((lan && lan.soft && t('soft.setup_failed') || "") + (rdata.msg || ''), function () {
          indexListHtml();
        }, {
          icon: 16,
          time: 0,
          shade: [0.3, '#000']
        });
      } else {
        localStorage.setItem(SOFT_CACHE_KEY, $("#indexsoft").html());
      }
    }, 'json').fail(function () {
      showMsg(t('soft.setup_failed', '保存排序失败'), function () {
        indexListHtml();
      }, {
        icon: 2,
        time: 2000
      });
    });
  }
}
function importPluginOpen() {
  $("#update_zip").on("change", function () {
    var files = $("#update_zip")[0].files;
    if (files.length == 0) {
      return;
    }
    importPlugin(files[0]);
    $("#update_zip").val('');
  });
  $("#update_zip").click();
}
function importPlugin(file) {
  var formData = new FormData();
  formData.append("plugin_zip", file);
  $.ajax({
    url: "/plugins/update_zip",
    type: "POST",
    data: formData,
    processData: false,
    dataType: 'json',
    contentType: false,
    success: function (data) {
      if (data.status === false) {
        layer.msg(data.msg, {
          icon: 2
        });
        return;
      }
      var loadT = layer.open({
        type: 1,
        area: "500px",
        title: lan && lan.soft && t('soft.install_third_party_plugin') || "",
        closeBtn: 1,
        shift: 5,
        shadeClose: false,
        content: '<style>.install_three_plugin{padding:25px;padding-bottom:70px}.install_three_plugin .box{border:1px solid #ccc;padding:15px;line-height:22px;border-radius:2px}.install_three_plugin .box .title{font-size:16px;font-weight:600;margin-bottom:10px}.install_three_plugin .box p{margin-bottom:5px}.install_three_plugin .box p b{color:#666}.install_three_plugin .help-info-text{margin-top:15px;color:red}.install_three_plugin .bt-form-submit-btn{position:absolute;bottom:20px;text-align:center;width:100%;left:0}</style>' +
                    '<div class="install_three_plugin">' +
                    '<div class="box">' +
                    '<div class="title">' + yfSoftText(data.title) + '</div>' +
                    '<p><b>' + (lan && lan.soft && lan.soft.version || '版本：') + '</b>' + yfSoftText(data.versions) + '</p>' +
                    '<p><b>' + (lan && lan.soft && lan.soft.desc || '描述：') + '</b>' + yfSoftText(data.ps) + '</p>' +
                    '<p><b>' + (lan && lan.soft && lan.soft.size || '大小：') + '</b>' + toSize(data.size) + '</p>' +
                    '<p><b>' + (lan && lan.soft && lan.soft.author || '作者：') + '</b>' + yfSoftText(data.author) + '</p>' +
                    '<p><b>' + (lan && lan.soft && lan.soft.source || '来源：') + '</b>' + (yfSoftUrl(data.home) ? ('<a class="btlink" href="' + yfSoftUrl(data.home) + '" target="_blank">' + yfSoftUrl(data.home) + '</a>') : '-') + '</p>' +
                    '</div>' +
                    // 安装前确认：把将被 root 执行的脚本原样展示（yfSoftText 做 HTML 转义）
                    (data.install_sh ? ('<div class="box"><div class="title">' + yfSoftText(data.shell || 'install.sh') + '</div>' +
                      '<pre class="yf-plugin-script" style="max-height:220px;overflow:auto;white-space:pre-wrap;word-break:break-all;background:#1e1e1e;color:#d4d4d4;padding:10px;border-radius:2px;margin:0;">' + yfSoftText(data.install_sh) + '</pre></div>') : '') +
                    '<ul class="help-info-text c7"><li>' + (lan && lan.soft && lan.soft.third_warn1 || '第三方插件未经官方安全认证，请自行核实插件安全性；') + '</li><li>' + (lan && lan.soft && lan.soft.third_warn2 || '使用第三方插件可能会影响面板稳定性；') + '</li><li>' + (lan && lan.soft && lan.soft.third_warn3 || '安装时将执行以上脚本（root 权限），安装时需再次确认。') + '</li></ul>' +
                    '<div class="bt-form-submit-btn"><button type="button" class="btn btn-danger btn-sm" onclick="layer.closeAll()">' + (lan && lan.public && lan.public.cancel || '取消') + '</button>' +
                    '<button type="button" class="btn btn-success btn-sm" onclick="importPluginInstall(\'' + yfSoftJsStr(data.name) + '\',\'' + yfSoftJsStr(data.tmp_path) + '\')">' + (lan && lan.soft && lan.soft.confirm_install || '确定安装') + '</button></div>' +
                    '</div>'
      });
    },
    error: function (responseStr) {
      layer.msg((lan && lan.soft && t('soft.upload_failed') || "") + responseStr, {
        icon: 2
      });
    }
  });
}
function importPluginInstall(plugin_name, tmp_path) {
  layer.msg(lan && lan.soft && t('soft.installing_this_may_take') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/plugins/input_zip', {
    plugin_name: plugin_name,
    tmp_path: tmp_path
  }, function (rdata) {
    layer.closeAll();
    if (rdata.status) {
      getSList(true);
      getTaskCount();
    }
    setTimeout(function () {
      layer.msg(rdata.msg, {
        icon: rdata.status ? 1 : 2
      });
    }, 1000);
  }, 'json').fail(function () {
    layer.closeAll();
    layer.msg(t('public.ERROR', '操作失败'), {
      icon: 2
    });
  });
}
// 第三方插件「安装前确认」：展示将被 root 执行的 install.sh + info.json 关键字段，
// 要求管理员输入插件名二次确认，确认后才带上与包内容绑定的 confirm_token 发起安装。
// 官方插件（后端 require_confirm=false）不弹此窗，直接 onConfirm('')，安装成功率不变。
function installPluginScriptConfirm(name, onConfirm) {
  $.post('/plugins/confirm_preview', {
    name: name
  }, function (rdata) {
    if (rdata.status === false) {
      layer.msg(rdata.msg, {
        icon: 2
      });
      return;
    }
    var info = rdata.data || {};
    if (!info.require_confirm) {
      onConfirm('');
      return;
    }
    layer.open({
      type: 1,
      area: '640px',
      title: (lan && lan.soft && t('soft.install_third_party_plugin') || "安装第三方插件包"),
      closeBtn: 1,
      shift: 5,
      shadeClose: false,
      content: '<div class="install_three_plugin">' +
        '<div class="box">' +
        '<div class="title">' + yfSoftText(info.title || name) + '</div>' +
        '<p><b>' + (lan && lan.soft && lan.soft.version || '版本：') + '</b>' + yfSoftText(info.versions) + '</p>' +
        '<p><b>' + (lan && lan.soft && lan.soft.desc || '描述：') + '</b>' + yfSoftText(info.ps) + '</p>' +
        '<p><b>' + (lan && lan.soft && lan.soft.author || '作者：') + '</b>' + yfSoftText(info.author) + '</p>' +
        '</div>' +
        '<div class="box">' +
        '<div class="title">' + yfSoftText(info.shell || 'install.sh') + '</div>' +
        '<pre class="yf-plugin-script" style="max-height:260px;overflow:auto;white-space:pre-wrap;word-break:break-all;background:#1e1e1e;color:#d4d4d4;padding:10px;border-radius:2px;margin:0;">' + yfSoftText(info.install_sh) + '</pre>' +
        '</div>' +
        '<ul class="help-info-text c7"><li>' + (lan && lan.soft && lan.soft.third_warn3 || '以上脚本将以 root 权限执行，请确认无误后再安装。') + '</li></ul>' +
        '<div class="line"><input type="text" id="yf_confirm_plugin_name" class="bt-input-text" style="width:260px;" placeholder="' + (lan && lan.soft && t('soft.please_input') || '请输入') + yfSoftText(name) + '" /></div>' +
        '<div class="bt-form-submit-btn"><button type="button" class="btn btn-danger btn-sm" onclick="layer.closeAll()">' + (lan && lan.public && lan.public.cancel || '取消') + '</button>' +
        '<button type="button" class="btn btn-success btn-sm" id="yf_confirm_plugin_btn">' + (lan && lan.soft && lan.soft.confirm_install || '确定安装') + '</button></div>' +
        '</div>',
      success: function () {
        $('#yf_confirm_plugin_btn').on('click', function () {
          if (String($('#yf_confirm_plugin_name').val()).trim() !== name) {
            layer.msg(lan && lan.soft && t('soft.the_plugin_name_you') || "输入的插件名称不匹配，操作已取消！", {
              icon: 2
            });
            return;
          }
          layer.closeAll();
          onConfirm(info.confirm_token || '');
        });
      }
    });
  }, 'json').fail(function () {
    // 预览接口异常时不得挡住官方插件的既有安装路径：不带凭据继续。
    // 第三方插件会在后端因缺少凭据被拒（fail-closed），官方插件照常入队。
    onConfirm('');
  });
}
// PHP 分支升级：只投递后台任务。
// 编译 10~30 分钟，绝不能塞进同步请求里 —— 面板是单 worker，整段编译会把整个面板
// 拖住，「点升级后面板卡死」就是这么来的（apt 渠道同理，见 php-apt/index.py）。
function phpUpgradeSoft(name, branch, current_ver, latest_ver) {
  var tip = t('soft.php_upgrade_tip', '将重新编译 PHP（约 10~30 分钟），完成后自动重启 FPM；失败会自动还原旧版本。');
  var title = (current_ver ? (current_ver + ' → ' + latest_ver) : latest_ver);
  layer.confirm('<b>' + yfSoftText(name) + ' ' + yfSoftText(branch) + '</b> ' + yfSoftText(title) +
    '<br><span class="c9">' + yfSoftText(tip) + '</span>', {
    title: t('soft.upgrade_to', '升级到') + ' PHP ' + yfSoftText(latest_ver || ''),
    icon: 3,
    closeBtn: 1,
    btn: [t('public.confirm', '确认'), t('public.cancel', '取消')]
  }, function (index) {
    layer.close(index);
    var loadT = layer.msg(t('public.getting', '正在获取中...'), { icon: 16, time: 0, shade: 0.2 });
    $.post('/plugins/run', {
      name: name,
      func: 'submit_baseline_upgrade',
      version: branch
    }, function (rdata) {
      if (loadT) layer.close(loadT);
      var info = null;
      if (rdata && typeof rdata.data === 'string' && rdata.data.charAt(0) === '{') {
        try { info = JSON.parse(rdata.data); } catch (e) { info = null; }
      }
      var ok = info ? !!info.status : !!(rdata && rdata.status);
      var text = (info && info.msg) ? info.msg : ((rdata && rdata.msg) || '');
      layer.msg(yfSoftText(text) || (ok ? 'OK' : 'ERROR'), { icon: ok ? 1 : 0, time: 5000, shade: [0.3, '#000'] });
      getSList(true);
      getTaskCount();
      if (ok && typeof messageBox === 'function') {
        // 直接打开消息盒子：失败会显示「失败」并可查看日志（不再伪装成「等待」）
        setTimeout(function () { messageBox(); }, 800);
      }
    }, 'json').fail(function () {
      if (loadT) layer.close(loadT);
      layer.msg(t('public.ERROR', '操作失败'), { icon: 2 });
    });
  });
}

function softUpdate(name, ver, current_ver) {
  layer.confirm((lan && lan.soft && t('soft.are_you_sure_you') || "") + name + (lan && lan.soft && t('soft.from') || "") + current_ver + (lan && lan.soft && t('soft.upgrade_to') || "") + ver + (lan && lan.soft && t('soft.msg_1') || ""), {
    icon: 3,
    closeBtn: 1
  }, function () {
    installPluginScriptConfirm(name, function (token) {
      var request_args = "name=" + name + "&version=" + ver + "&type=0&upgrade=1";
      if (token) {
        request_args += "&confirm_token=" + encodeURIComponent(token);
      }
      runInstall(request_args);
    });
  });
}
function refreshPluginList() {
  var loading = layer.msg(lan && lan.soft && t('soft.clearing_the_cache_and') || "", {
    icon: 16,
    time: 0,
    shade: [0.3, '#000']
  });
  $.post('/plugins/clear_cache', {}, function (rdata) {
    layer.close(loading);
    getSList(true);
    layer.msg(lan && lan.soft && t('soft.refresh_successful') || "", {
      icon: 1,
      time: 1000
    });
  }, 'json').fail(function () {
    layer.close(loading);
    layer.msg(t('public.ERROR', '操作失败'), {
      icon: 2
    });
  });
}
// 从首页「PHP 安全基线」的「建议卸载该版本并升级到 PHP 8.2 及以上」跳过来时，
// URL 带 soft_name/soft_version/soft_search：先把「类型 + 搜索框 + 页码」预设好，
// 保证目标行落在第一页（否则 40 多个插件、每页 10 条，用户还得自己翻页找），
// 再由 softFocusTarget() 精确定位并打开该版本的管理面板（卸载入口就在里面）。
(function () {
  var q = softQueryParams();
  if (!q.soft_name) return;
  try {
    if (q.soft_type) {
      setCookie('soft_type', q.soft_type);
      setCookie('p' + q.soft_type, 1);
    }
    if (q.soft_search && $("#SearchValue").length) {
      $("#SearchValue").val(q.soft_search);
      if ($("#resetSearchBtn").length) $("#resetSearchBtn").show();
    }
  } catch (e) {}
})();

$(function () {
  // 点击外部隐藏设置下拉框
  $(document).on('click', function (e) {
    if (!$(e.target).closest('.plugin-settings-dropdown').length) {
      $('#third_party_setting_box').hide();
    }
  });
});