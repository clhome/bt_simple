/* 御风面板 i18n 纯文本化后的受信 HTML 模板（单例，不随语言复制，便于强缓存） */
window.YF_TPL = window.YF_TPL || {};

YF_TPL.newFolderRow = [
  "<tr>",
  "  <td colspan=\"2\"><span class=\"glyphicon glyphicon-folder-open\"></span><input id=\"newFolderName\" class=\"newFolderName\" type=\"text\" value=\"\"></td>",
  "  <td colspan=\"3\"><button id=\"nameOk\" type=\"button\" class=\"btn btn-success btn-sm nameOk\" data-i18n=\"public.confirm\"></button>",
  "    &nbsp;&nbsp;<button id=\"nameNOk\" type=\"button\" class=\"btn btn-default btn-sm nameNOk\" data-i18n=\"public.cancel\"></button></td>",
  "</tr>"
].join("");

YF_TPL.onlineEdit = [
  "<form class=\"bt-form pd20\"><div class=\"line\">",
  "  <p style=\"color:red;margin-bottom:10px\" data-i18n=\"public.editor_tip\"></p>",
  "  <select class=\"bt-input-text\" name=\"encoding\" style=\"width:74px;position:absolute;top:31px;right:19px;height:22px;z-index:9999;border-radius:0;\"><option value=\"utf-8\" selected>utf-8</option></select>",
  "  <textarea class=\"mCustomScrollbar bt-input-text\" id=\"textBody\" style=\"width:100%;margin:0 auto;line-height:1.8;position:relative;top:10px;\"></textarea>",
  "</div></form>"
].join("");

YF_TPL.autoRefreshToggle = [
  "<div class=\"auto-refresh-toggle\" style=\"position:absolute;bottom:12px;left:15px;display:flex;align-items:center;height:28px;padding:0 12px;border-radius:14px;cursor:pointer;user-select:none;transition:all 0.3s;background:transparent;z-index:10000;\">",
  "  <div class=\"toggle-track\" style=\"width:36px;height:18px;border:1px solid #ccc;border-radius:10px;position:relative;margin-right:8px;transition:all 0.3s;background:#fff;\">",
  "    <div class=\"toggle-thumb\" style=\"width:14px;height:14px;border:1px solid #ccc;background:#fff;border-radius:50%;position:absolute;top:1px;right:2px;transition:all 0.3s;\"></div>",
  "  </div>",
  "  <span class=\"toggle-text\" style=\"color:#999;font-size:14px;transition:all 0.3s;\" data-i18n=\"public.auto_refresh\"></span>",
  "</div>"
].join("");

YF_TPL.panelBind = [
  "<div class=\"bt-form pd20 pb70\">",
  "  <div class=\"line\"><span class=\"tname\" data-i18n=\"public.panel_address\"></span><div class=\"info-r\"><input class=\"bt-input-text\" type=\"text\" name=\"btaddress\" id=\"btaddress\" value=\"{{panel_url}}\" data-i18n=\"public.panel_address\" data-i18n-attr=\"placeholder\" style=\"width:100%\"></div></div>",
  "  <div class=\"line\"><span class=\"tname\" data-i18n=\"public.username\"></span><div class=\"info-r\"><input class=\"bt-input-text\" type=\"text\" name=\"btuser\" id=\"btuser\" value=\"{{panel_user}}\" data-i18n=\"public.username\" data-i18n-attr=\"placeholder\" style=\"width:100%\"></div></div>",
  "  <div class=\"line\"><span class=\"tname\" data-i18n=\"public.password\"></span><div class=\"info-r\"><input class=\"bt-input-text\" type=\"password\" name=\"btpassword\" id=\"btpassword\" value=\"{{panel_pwd}}\" data-i18n=\"public.password\" data-i18n-attr=\"placeholder\" style=\"width:100%\"></div></div>",
  "  <div class=\"line\"><span class=\"tname\" data-i18n=\"public.notes\"></span><div class=\"info-r\"><input class=\"bt-input-text\" type=\"text\" name=\"bttitle\" id=\"bttitle\" value=\"{{panel_title}}\" data-i18n=\"public.notes\" data-i18n-attr=\"placeholder\" style=\"width:100%\"></div></div>",
  "  <div class=\"line\"><ul class=\"help-info-text c7\"><li data-i18n=\"public.bind_panel_help_1\"></li><li data-i18n=\"public.bind_panel_help_2\"></li><li><font style=\"color:red\" data-i18n=\"public.bind_panel_help_3\"></font></li></ul></div>",
  "  <div class=\"bt-form-submit-btn\"><button type=\"button\" class=\"btn btn-danger btn-sm\" onclick=\"layer.closeAll()\" data-i18n=\"public.close\"></button> {{html_btns}}</div>",
  "</div>"
].join("");

YF_TPL.msgBox = [
  "<div class=\"bt-form\"><div class=\"bt-w-main\" id=\"msg_box\">",
  "  <div class=\"bt-w-menu\">",
  "    <p class=\"bgw\" id=\"taskList\" onclick=\"tasklist()\"><span data-i18n=\"public.task_list\"></span>(<span class=\"task_count\">0</span>)</p>",
  "    <p onclick=\"remind()\"><span data-i18n=\"public.message_list\"></span>(<span class=\"msg_count\">0</span>)</p>",
  "    <p onclick=\"execLog()\" data-i18n=\"public.execution_log\"></p>",
  "  </div>",
  "  <div class=\"bt-w-con pd15\"><div class=\"taskcon\"></div></div>",
  "</div>",
  "<div id=\"msg_box_sys_info\" style=\"margin:0 15px 15px;border-top:1px solid #efefef;padding-top:10px;font-size:13px;color:#666;display:flex;justify-content:space-between;\">",
  "  <span>CPU: <span id=\"msg_box_cpu\" style=\"color:#20a53a\">0%</span></span>",
  "  <span><span data-i18n=\"public.memory_1\"></span> <span id=\"msg_box_mem\" style=\"color:#20a53a\">0%</span></span>",
  "  <span><span data-i18n=\"public.uplink\"></span> <span id=\"msg_box_up\" style=\"color:#f7b851\">0 B/s</span></span>",
  "  <span><span data-i18n=\"public.downstream\"></span> <span id=\"msg_box_down\" style=\"color:#52a9ff\">0 B/s</span></span>",
  "</div></div>"
].join("");

YF_TPL.serviceNotice = [
  "<div class=\"service-notice\" style=\"margin-top:20px;padding:15px;background:#f8f9fa;border-left:4px solid #20a53a;border-radius:4px;font-size:13px;color:#555;line-height:1.6;\">",
  "  <div style=\"margin-bottom:6px;font-size:14px;color:#333;font-weight:600;\"><span class=\"glyphicon glyphicon-info-sign\" style=\"margin-right:5px;color:#20a53a;\"></span><span data-i18n=\"public.operating_instructions\"></span></div>",
  "  <div style=\"margin-bottom:4px;\"><b style=\"color:#333;\" data-i18n=\"public.reload_configuration_reload\"></b><span data-i18n=\"public.smoothly_loads_the_latest\"></span><b style=\"color:#20a53a;\" data-i18n=\"public.zero_business_disruption\"></b><span data-i18n=\"public.recommended_for_use_after\"></span></div>",
  "  <div><b style=\"color:#333;\" data-i18n=\"public.restart_the_service_restart\"></b><span data-i18n=\"public.forcibly_terminates_and_restarts\"></span></div>",
  "</div>"
].join("");

YF_TPL.cmSearch = {
  input: "<input type='text' class='cm-search-input bt-input-text' data-i18n='public.search_content' data-i18n-attr='placeholder' style='height:28px;line-height:28px;padding:0 8px;flex:1;margin-right:5px;min-width:0;'>",
  prev: "<button type='button' class='btn btn-default btn-sm cm-search-prev' style='padding:4px 8px;margin-left:2px;' data-i18n='public.previous' data-i18n-attr='title'><i class='glyphicon glyphicon-chevron-up'></i></button>",
  next: "<button type='button' class='btn btn-default btn-sm cm-search-next' style='padding:4px 8px;margin-left:2px;' data-i18n='public.next' data-i18n-attr='title'><i class='glyphicon glyphicon-chevron-down'></i></button>",
  close: "<button type='button' class='btn btn-default btn-sm cm-search-close' style='padding:4px 8px;margin-left:5px;' data-i18n='public.close' data-i18n-attr='title'><i class='glyphicon glyphicon-remove'></i></button>",
  replaceInput: "<input type='text' class='cm-replace-input bt-input-text' data-i18n='public.replace_with' data-i18n-attr='placeholder' style='height:28px;line-height:28px;padding:0 8px;flex:1;margin-right:5px;min-width:0;'>",
  replaceBtn: "<button type='button' class='btn btn-default btn-sm cm-replace-btn' style='padding:4px 8px;margin-left:2px;' data-i18n='public.replace_current' data-i18n-attr='title'><span data-i18n='public.replace'></span></button>",
  replaceAllBtn: "<button type='button' class='btn btn-default btn-sm cm-replace-all-btn' style='padding:4px 8px;margin-left:2px;' data-i18n='public.replace_all' data-i18n-attr='title'><span data-i18n='public.all_1'></span></button>"
};

YF_TPL.aboutHeader = [
  "<img src=\"/static/img/logo.webp\" style=\"width:160px;margin-bottom:5px;\">",
  "<h2 style=\"margin-top:5px;\" data-i18n=\"public.yufeng_panel_btsimple\"></h2>"
].join("");
