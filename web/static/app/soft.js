

//重置插件弹出框宽度
function resetPluginWinWidth(width){
    $("div[id^='layui-layer'][class*='layui-layer-page']").width(width);
}

//重置插件弹出框宽度
function resetPluginWinHeight(height){
    $("div[id^='layui-layer'][class*='layui-layer-page']").height(height);
    $(".bt-form .bt-w-main").height(height-42);
}

//软件管理窗口
function softMain(name, title, version) {

    var _title = title.replace('-'+version,'')

    var loadT = layer.msg("正在处理,请稍后...", { icon: 16, time: 0, shade: [0.3, '#000'] });
    $.get('/plugins/setting?name='+name, function(rdata) {
        layer.close(loadT);
        layer.open({
            type: 1,
            area: '640px',
            title: _title + '【' + version + "】管理",
            closeBtn: 1,
            shift: 0,
            content: rdata
        });
        $(".bt-w-menu p").click(function() {
            $(this).addClass("bgw").siblings().removeClass("bgw");
        });

        //version to
        $(".plugin_version").attr('version',version).hide();
    });
}

function toggleThirdParty(isChecked) {
    localStorage.setItem('show_third_party', isChecked ? 'true' : 'false');
    getSList(1);
}

function clearPluginCache() {
    layer.confirm('此操作将清空 /www/server/source/ 下所有的下载包缓存文件。<br>清理后再次安装软件将重新从网络下载安装包，确认清理吗？', { title: '清理安装缓存', icon: 3 }, function(index) {
        var loadT = layer.msg('正在清理，请稍后...', { icon: 16, time: 0, shade: [0.3, '#000'] });
        $.post('/plugins/clear_cache', {}, function(rdata) {
            layer.close(loadT);
            layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
            $('#third_party_setting_box').hide();
        }, 'json');
    });
}

//取软件列表
function getSList(isdisplay) {
    if (isdisplay !== true) {
        var loadT = layer.msg('正在获取列表...', { icon: 16, time: 0, shade: [0.3, '#000'] })
    }
    if (!isdisplay || isdisplay === true)
        isdisplay = getCookie('p' + getCookie('soft_type'));
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
    setTimeout(function(){
        var chk = document.getElementById('show_third_party_chk');
        if(chk) chk.checked = isShowThirdParty;
    }, 100);

    var condition = (search + type + page + show_third_party).slice(1);
    $.get('/plugins/list?' + condition, '', function(rdata) {
        layer.close(loadT);
        var tBody = '';
        var sBody = '';
        var pBody = '';

        for (var i = 0; i < rdata.type.length; i++) {
            var c = '';
            if (istype == rdata.type[i].type) {
                c = 'class="on"';
            }
            tBody += '<span typeid="' + rdata.type[i].type + '" ' + c + '>' + rdata.type[i].title + '</span>';
        }

        $(".softtype").html(tBody);
        $("#softPage").html(rdata.list);
        $("#softPage .Pcount").css({ "position": "absolute", "left": "0" })

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
    
            if (typeof(plugin.versions) == "string" ){
                version_info += plugin.versions + '|';
            } else {
                for (var j = 0; j < len; j++) {
                    version_info += plugin.versions[j] + '|';
                }
            }
            if (version_info != '') {
                version_info = version_info.substring(0, version_info.length - 1);
            }

            var handle = '<a class="btlink" onclick="addVersion(\'' + plugin.name + '\',\'' + version_info + '\',\'' + plugin.tip + '\',this,\'' + plugin.title + '\',' + plugin.install_pre_inspection + ')">安装</a>';
            
            if (plugin.setup == true) {

                var mupdate = '';
                var latest_version = '';
                if (plugin.versions) {
                    if (typeof(plugin.versions) == 'string') {
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
                            mupdate = '<a class="btlink" onclick="softUpdate(\'' + plugin.name + '\',\'' + latest_version + '\',\'' + plugin.setup_version + '\')">更新</a> | ';
                        }
                    }
                }
                handle = mupdate + '<a class="btlink" onclick="softMain(\'' + plugin.name + '\',\'' + plugin.title + '\',\'' + plugin.setup_version + '\')">设置</a> | <a class="btlink" onclick="uninstallVersion(\'' + plugin.name + '\',\'' + plugin.title +'\',\'' + plugin.setup_version + '\',' + plugin.uninstall_pre_inspection +')">卸载</a>';
                titleClick = 'onclick="softMain(\'' + plugin.name + '\',\'' + plugin.title + '\',\'' + plugin.setup_version + '\')" style="cursor:pointer"';
             
                softPath = '<span class="glyphicon glyphicon-folder-open" title="' + plugin.path + '" onclick="openPath(\'' + plugin.path + '\')"></span>';
                if (plugin.coexist){
                    indexshow = '<div class="index-item">\
                        <input class="btswitch btswitch-ios" id="index_' + plugin.name  + plugin.versions + '" type="checkbox" ' + checked + '>\
                        <label class="btswitch-btn" for="index_' + plugin.name + plugin.versions + '" onclick="toIndexDisplay(\'' + plugin.name + '\',\'' + plugin.versions + '\',\'' + plugin.coexist +'\')"></label>\
                    </div>';
                } else {
                    indexshow = '<div class="index-item">\
                        <input class="btswitch btswitch-ios" id="index_' + plugin.name + '" type="checkbox" ' + checked + '>\
                        <label class="btswitch-btn" for="index_' + plugin.name + '" onclick="toIndexDisplay(\'' + plugin.name + '\',\'' + plugin.setup_version + '\')"></label>\
                    </div>';
                }
                
                if (plugin.display_status === false) {
                    state = '<span style="color:#999">-</span>';
                } else if (plugin.status == true) {
                    state = '<span style="color:#20a53a" class="glyphicon glyphicon-play"></span>'
                } else {
                    state = '<span style="color:red" class="glyphicon glyphicon-pause"></span>'
                }
            }

            if (plugin.task == '-2') {
                handle = '<a style="color:green;" href="javascript:task();">正在卸载...</a>';
            } else if (plugin.task == '-1') {
                handle = '<a style="color:green;" href="javascript:task();">正在安装...</a>';
            } else if (plugin.task == '0') {
                handle = '<a style="color:#C0C0C0;" href="javascript:task();">等待中...</a>';
            }

            var plugin_title = plugin.title;
            if (plugin.setup && !plugin.coexist){
                plugin_title = plugin.title + ' ' + plugin.setup_version;
            }
            if (plugin.display_level == 1) {
                plugin_title += ' <span style="color: #f39c12; font-size: 12px;">(第三方)</span>';
            }

            icon_link = "/plugins/file?name="+plugin.name+"&f=ico.png";
            if (plugin.icon != ''){
                icon_link = "/plugins/file?name="+plugin.name+"&f="+plugin.icon;
            }

            sBody += '<tr>' +
                '<td><span ' + titleClick + '>'+
                '<img data-src="'+icon_link+'" src="/static/img/loading.gif">' + plugin_title + '</span></td>' +
                '<td>' + plugin.ps + '</td>' +
                '<td>' + (plugin.home ? '<a class="btlink" href="' + plugin.home + '" target="_blank">官网</a>' : '-') + '</td>' +
                '<td>' + (plugin.date ? plugin.date : '-') + '</td>' +
                '<td>' + softPath + '</td>' +
                '<td>' + state + '</td>' +
                '<td>' + indexshow + '</td>' +
                '<td style="text-align: right;">' + handle + '</td>' +
                '</tr>';
        }

        sBody += pBody;


        $("#softList").html(sBody);
        $(".menu-sub span").off("click").click(function() {
            setCookie('soft_type', $(this).attr('typeid'));
            $(this).addClass("on").siblings().removeClass("on");
            getSList();
        });

        loadImage();

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
        if (window.document.location.pathname == '/soft/') {
            var delay = has_active_task ? 8000 : 30000; // 有任务8秒，无任务30秒
            window.softTimer = setTimeout(function() {
                getSList(true); // 传入 true，避免弹出 loading 遮罩
            }, delay);
        }
    },'json');
}

function installPreInspection(name, ver, callback){
    var loading = layer.msg('正在检查安装环境...', { icon: 16, time: 0, shade: [0.3, '#000'] });
     $.post("/plugins/run", {'name':name,'version':ver,'func':'install_pre_inspection'}, function(rdata) {
        layer.close(loading);
        if (rdata.status){
            if (rdata.data == 'ok'){
                callback();
            } else {
                layer.msg(rdata.data, { icon: 2 });
            }
        } else {
            layer.msg(rdata.data, { icon: rdata.status ? 1 : 2 });
        }
    },'json');
}

function runInstall(data){
    var loadT = layer.msg('正在添加到安装器...', { icon: 16, time: 0, shade: [0.3, '#000'] });
    $.post("/plugins/install", data, function(rdata) {
        layer.closeAll();
        layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 });
        getSList();
    },'json');
}

function addVersion(name, ver, type, obj, title, install_pre_inspection) {
    var option = '';
    var titlename = title.replace("-"+ver,"");
    if (ver.indexOf('|') >= 0){
        var veropt = ver.split("|");
        var selectVersion = '';
        for (var i = veropt.length - 1; i >= 0; i--) {
            selectVersion += '<option>' + name + ' ' + veropt[i] + '</option>';
        }
        option = "<select id='selectVersion' class='bt-input-text' style='margin-left:30px'>" + selectVersion + "</select>";
    } else {
        option = '<span id="selectVersion" val="' + name + ' ' + ver + '">【' + titlename + '】 ' + ver + '</span>';
    }

    var customHtmlPath = "/plugins/file?name=" + name + "&f=install.html";
    $.get(customHtmlPath, function(customHtml) {
        if (typeof customHtml !== 'string' || customHtml.indexOf('404 Not Found') > -1 || customHtml.indexOf('{"status":false') > -1 || customHtml.trim() === '') {
            customHtml = '';
        }
        var layerArea = customHtml ? '540px' : '380px';
        
        layer.open({
            type: 1,
            title: "安装"+titlename,
            area: layerArea,
            closeBtn: 1,
            shadeClose: true,
            btn: ['提交','关闭'],
            content: "<div class='bt-form pd20 c6'>\
                <div class='version line'>安装版本：" + option + "</div>" + customHtml + "\
            </div>",
            success:function(){
                $('.fangshi input').click(function() {
                    $(this).attr('checked', 'checked').parent().siblings().find("input").removeAttr('checked');
                });
                installTips();
            },
            yes:function(index,layero){
                var info = $("#selectVersion").val();
                if (info == null || info == undefined || info == ''){
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
                var request_args = "name=" + plugin_name + "&version=" + version + "&type=" + type;

                if (install_pre_inspection){
                    //安装前置检测
                    installPreInspection(plugin_name, version, function(){
                        runInstall(request_args);
                        flySlow('layui-layer-btn0');
                    });      
                    return;
                }

                runInstall(request_args);
                flySlow('layui-layer-btn0');
            }
        });
    }).fail(function() {
        layer.open({
            type: 1,
            title: "安装"+titlename,
            area: '380px',
            closeBtn: 1,
            shadeClose: true,
            btn: ['提交','关闭'],
            content: "<div class='bt-form pd20 c6'>\
                <div class='version line'>安装版本：" + option + "</div>\
            </div>",
            success:function(){
                $('.fangshi input').click(function() {
                    $(this).attr('checked', 'checked').parent().siblings().find("input").removeAttr('checked');
                });
                installTips();
            },
            yes:function(index,layero){
                var info = $("#selectVersion").val();
                if (info == null || info == undefined || info == ''){
                    info = $("#selectVersion").attr('val');
                }
                info = info.toLowerCase();
                var info_split = info.split(' ');
                var plugin_name = info_split[0];
                var version = info_split[1];

                var type = $('.fangshi').prop("checked") ? '1' : '0';
                var request_args = "name=" + plugin_name + "&version=" + version + "&type=" + type;

                if (install_pre_inspection){
                    //安装前置检测
                    installPreInspection(plugin_name, version, function(){
                        runInstall(request_args);
                        flySlow('layui-layer-btn0');
                    });      
                    return;
                }

                runInstall(request_args);
                flySlow('layui-layer-btn0');
            }
        });
    });
}

// 强制删除插件
function forceUninstallPlugin(name, version) {
    var contentHtml = "<div class='bt-form pd20 c6'>\
        <div style='color: red; font-weight: bold; margin-bottom: 15px; line-height: 20px;'>\
            ⚠️ 警告：此操作将物理清除该插件的代码、相关配置以及位于 /www/server/" + name + " 的所有运行文件与数据库数据（请务必提前做好备份，一经删除绝不可恢复）！\
        </div>\
        <div class='line' style='margin-bottom: 15px;'>\
            <span>请输入插件名 <b>" + name + "</b> 以确认：</span>\
            <input type='text' id='force_uninstall_confirm_name' class='bt-input-text' style='width: 100%; margin-top: 10px;' placeholder='请输入插件名' />\
        </div>\
        <div style='margin-top: 15px; display: flex; align-items: center; justify-content: flex-start;'>\
            <label style='font-weight: normal; cursor: pointer; color: #d9534f; display: flex; align-items: center; margin-bottom: 0;'>\
                <input type='checkbox' id='force_uninstall_backup_chk' checked='checked' style='margin-right: 8px; width: 16px; height: 16px; cursor: pointer;' />\
                删除前打包备份到 /www/backup\
            </label>\
        </div>\
    </div>";

    layer.open({
        type: 1,
        title: "强制删除确认 (高危操作)",
        area: '420px',
        closeBtn: 1,
        shadeClose: false,
        btn: ['强制删除', '取消'],
        content: contentHtml,
        yes: function(index, layero) {
            var confirmName = String($("#force_uninstall_confirm_name").val()).trim();
            if (confirmName !== name) {
                layer.msg('输入的插件名称不匹配，操作已取消！', { icon: 2 });
                return false;
            }
            var isBackup = $("#force_uninstall_backup_chk").prop("checked") ? 1 : 0;
            layer.close(index);
            var forceLoad = layer.msg('正在强制删除,请稍候...', { icon: 16, time: 0, shade: [0.3, '#000'] });
            $.post('/plugins/uninstall', { name: name, version: version, force: 1, backup: isBackup }, function(forceRdata) {
                layer.close(forceLoad);
                getSList();
                layer.msg(forceRdata.msg, { icon: forceRdata.status ? 1 : 2 });
            }, 'json');
        }
    });
}

//卸载软件
function uninstallPreInspection(name, title, ver, callback){
    var loading = layer.msg('正在检查卸载环境...', { icon: 16, time: 0, shade: [0.3, '#000'] });
     $.post("/plugins/run", {'name':name,'version':ver,'func':'uninstall_pre_inspection'}, function(rdata) {
        layer.close(loading);
        if (rdata.status){
            if (rdata.data == 'ok'){
                if (typeof(callback) == 'function'){
                    callback();
                }
            } else {
                layer.confirm(rdata.data + '<br><span style="color: red;">卸载环境检查失败，是否要强制删除该插件？</span>', {
                    title: '卸载失败提示',
                    icon: 2,
                    closeBtn: 1,
                    btn: ['强制删除', '取消']
                }, function() {
                    forceUninstallPlugin(name, ver);
                });
            }
        } else {
            layer.confirm(rdata.data + '<br><span style="color: red;">卸载环境检查失败，是否要强制删除该插件？</span>', {
                title: '卸载失败提示',
                icon: 2,
                closeBtn: 1,
                btn: ['强制删除', '取消']
            }, function() {
                forceUninstallPlugin(name, ver);
            });
        }
    },'json');
}


function runUninstallVersion(name, title, version){
    var title = title.replace("-"+version,"");
    var contentHtml = "<div class='bt-form pd20 c6'>\
        <div class='line' style='margin-bottom: 15px;'>\
            <span style='font-size:14px;'>您真的要卸载【" + title + "-" + version + "】吗？</span>\
        </div>\
        <div style='margin-top: 15px; display: flex; align-items: center; justify-content: flex-start;'>\
            <label style='font-weight: normal; cursor: pointer; display: flex; align-items: center; margin-bottom: 0;'>\
                <input type='checkbox' id='normal_uninstall_backup_chk' style='margin-right: 8px; width: 16px; height: 16px; cursor: pointer;' />\
                卸载前将数据打包备份到 /www/backup (.tar.gz)\
            </label>\
        </div>\
    </div>";

    layer.open({
        type: 1,
        title: "卸载软件确认",
        area: '400px',
        closeBtn: 1,
        shadeClose: false,
        btn: ['确认卸载', '取消'],
        content: contentHtml,
        yes: function(index, layero) {
            var isBackup = $("#normal_uninstall_backup_chk").prop("checked") ? 1 : 0;
            layer.close(index);
            var data = 'name=' + name + '&version=' + version + '&backup=' + isBackup;
            var loadT = layer.msg('正在处理,请稍候...', { icon: 16, time: 0, shade: [0.3, '#000'] });
            $.post('/plugins/uninstall', data, function(rdata) {
                layer.close(loadT)
                if (rdata.status) {
                    getSList();
                    layer.msg(rdata.msg, { icon: 1 });
                } else {
                    layer.confirm(rdata.msg + '<br><span style="color: red;">插件卸载失败，是否要强制删除该插件？</span>', {
                        title: '卸载失败提示',
                        icon: 2,
                        closeBtn: 1,
                        btn: ['强制删除', '取消']
                    }, function() {
                        forceUninstallPlugin(name, version);
                    });
                }
            },'json');
        }
    });
}


function uninstallVersion(name, title, version, uninstall_pre_inspection) {
    if (uninstall_pre_inspection) {
        uninstallPreInspection(name,title,version,function(){
            runUninstallVersion(name,title,version);
        });
    } else {
        runUninstallVersion(name,title,version);
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
    $.post("/plugins/set_index", data, function(rdata) {
        if (rdata.status) {
            layer.msg(rdata.msg, { icon: 1 })
        } else {
            layer.msg(rdata.msg, { icon: 2 })
        }
    },'json');
}

function indexListHtml(callback){
    var cacheHtml = localStorage.getItem('index_soft_cache_html');
    var hasCache = false;
    
    if (cacheHtml) {
        $("#indexsoft").html(cacheHtml);
        hasCache = true;
        if (typeof callback == 'function'){
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
    $.get('/plugins/index_list?simple=1', function(rdata) {
        var rdata = rdata.data;
        // layer.close(loadT);
        var con = '';
        for (var i = 0; i < rdata.length; i++) {
            var plugin = rdata[i];
            var len = plugin.versions.length;
            var version_info = '';

            if (typeof plugin.versions == "string"){
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
                state = '<span style="color:#20a53a" class="glyphicon glyphicon-play"></span>';
            } else {
                state = '<span style="color:red" class="glyphicon glyphicon-pause"></span>';
            }

            var name = plugin.title + ' ' + plugin.setup_version + '  ';
            var data_id = plugin.name + '-' + plugin.setup_version;
            if (plugin.coexist){
                name = plugin.title + '  ';
                data_id = plugin.name + '-' + plugin.versions;
            }

            con += '<div class="col-xs-4 col-sm-3 col-md-2 col-lg-2" data-id="' + data_id + '">\
                <span class="spanmove"></span>\
                <div onclick="softMain(\'' + plugin.name + '\',\'' + plugin.title + '\',\'' + plugin.setup_version + '\')">\
                <div class="image"><img bk-src="/static/img/loading.gif" src="/plugins/file?name=' + plugin.name + '&f=ico.png" style="max-width:48px;"></div>\
                <div class="sname">' +  name + state + '</div>\
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
            return;
        }

        $("#indexsoft").html(newFullHtml);
        localStorage.setItem('index_soft_cache_html', newFullHtml);

        if (typeof callback == 'function'){
            callback();
        }
    },'json');
}


//首页软件列表
function indexSoft(onFirstRender) {
    indexListHtml(function(){
        $("#indexsoft").dragsort({ 
            dragSelector: ".spanmove", 
            dragBetween: true, 
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
        var data = $("#indexsoft > div").map(function() { return $(this).attr("data-id"); }).get();
        tmp = [];
        for(i in data){
            // console.log(data[i]);
            if (data[i] != ''){
                tmp.push(String(data[i]).trim());
            }
        }
        var ssort = tmp.join("|");
        $("input[name=list1SortOrder]").val(ssort);
        $.post("/plugins/index_sort", 'ssort=' + ssort, function(rdata) {
            if (!rdata.status){
                showMsg('设置失败:'+ rdata.msg, function(){
                    indexListHtml();
                }, { icon: 16, time: 0, shade: [0.3, '#000'] });
            }
        },'json');
    };
}


function importPluginOpen(){
    $("#update_zip").on("change", function () {
        var files = $("#update_zip")[0].files;
        if (files.length == 0) {
            return;
        }
        importPlugin(files[0]);
        $("#update_zip").val('')
    });
    $("#update_zip").click();
}


function importPlugin(file){
    var formData = new FormData();
    formData.append("plugin_zip", file);
    $.ajax({
        url: "/plugins/update_zip",
        type: "POST",
        data: formData,
        processData: false,
        dataType:'json',
        contentType: false,
        success: function (data) {
            if (data.status === false) {
                layer.msg(data.msg, { icon: 2 });
                return;
            }
            var loadT = layer.open({
                type: 1,
                area: "500px",
                title: "安装第三方插件包",
                closeBtn: 1,
                shift: 5,
                shadeClose: false,
                content: '<style>\
                    .install_three_plugin{padding:25px;padding-bottom:70px}\
                    .plugin_user_info p { font-size: 14px;}\
                    .plugin_user_info {padding: 15px 30px;line-height: 26px;background: #f5f6fa;border-radius: 5px;border: 1px solid #efefef;}\
                    .btn-content{text-align: center;margin-top: 25px;}\
                </style>\
                <div class="bt-form c7  install_three_plugin pb70">\
                    <div class="plugin_user_info">\
                        <p><b>名称：</b>'+ data.title + '</p>\
                        <p><b>版本：</b>' + data.versions +'</p>\
                        <p><b>描述：</b>' + data.ps + '</p>\
                        <p><b>大小：</b>' + toSize(data.size) + '</p>\
                        <p><b>作者：</b>' + data.author + '</p>\
                        <p><b>来源：</b><a class="btlink" href="'+data.home+'" target="_blank">' + data.home + '</a></p>\
                    </div>\
                    <ul class="help-info-text c7">\
                        <li style="color:red;">此为第三方开发的插件，无法验证其可靠性!</li>\
                        <li>安装过程可能需要几分钟时间，请耐心等候!</li>\
                        <li>如果已存在此插件，将被替换!</li>\
                    </ul>\
                    <div class="bt-form-submit-btn"><button type="button" class="btn btn-sm btn-danger mr5" onclick="layer.closeAll()">取消</button><button type="button" class="btn btn-sm btn-success" onclick="importPluginInstall(\''+ data.name + '\',\'' + data.tmp_path +'\')">确定安装</button></div>\
                </div>'
            });

        },error: function (responseStr) {
            layer.msg('上传失败2!:' + responseStr, { icon: 2 });
        }
    });
}


function importPluginInstall(plugin_name, tmp_path) {
    layer.msg('正在安装,这可能需要几分钟时间...', { icon: 16, time: 0, shade: [0.3, '#000'] });
    $.post('/plugins/input_zip', { plugin_name: plugin_name, tmp_path: tmp_path }, function (rdata) {
        layer.closeAll()
        if (rdata.status) {
            getSList(true);
        }
        setTimeout(function () { layer.msg(rdata.msg, { icon: rdata.status ? 1 : 2 }) }, 1000);
    },'json');
}

function softUpdate(name, ver, current_ver) {
    layer.confirm('您确定要将【' + name + '】从 ' + current_ver + ' 升级到 ' + ver + ' 吗？', { icon: 3, closeBtn: 1 }, function() {
        var request_args = "name=" + name + "&version=" + ver + "&type=0&upgrade=1";
        runInstall(request_args);
    });
}

function refreshPluginList() {
    var loading = layer.msg('正在清理缓存并刷新列表...', { icon: 16, time: 0, shade: [0.3, '#000'] });
    $.post('/plugins/clear_cache', {}, function(rdata) {
        layer.close(loading);
        getSList(true);
        layer.msg('刷新成功', { icon: 1, time: 1000 });
    }, 'json');
}

$(function() {


    // 点击外部隐藏设置下拉框
    $(document).click(function(e) {
        if (!$(e.target).closest('.plugin-settings-dropdown').length) {
            $('#third_party_setting_box').hide();
        }
    });
});