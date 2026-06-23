//判断磁盘数量超出宽度
function isDiskWidth(){
    // $("#comlist").css({"width":(body_width-520)+"px","height":"34px","overflow":"auto"});
    $("#comlist").css({"max-width":"500px","height":"34px","overflow":"auto","display":"inline-block"});
}


//打开回收站
function recycleBin(type){
    $.post('/files/get_recycle_bin','',function(data){
        // console.log(rdata);
        var rdata = data['data'];
        var body = ''
        switch(type){
            case 1:
                for(var i=0;i<rdata.dirs.length;i++){
                    var shortwebname = rdata.dirs[i].name.replace(/'/,"\\'");
                    var shortpath = rdata.dirs[i].dname;
                    if(shortwebname.length > 20) shortwebname = shortwebname.substring(0, 20) + "...";
                    if(shortpath.length > 20) shortpath = shortpath.substring(0, 20) + "...";
                    body += '<tr>\
                        <td><span class=\'ico ico-folder\'></span><span class="tname" title="'+rdata.dirs[i].name+'">'+shortwebname+'</span></td>\
                        <td><span title="'+rdata.dirs[i].dname+'">'+shortpath+'</span></td>\
                        <td>'+toSize(rdata.dirs[i].size)+'</td>\
                        <td>'+getLocalTime(rdata.dirs[i].time)+'</td>\
                        <td style="text-align: right;">\
                            <a class="btlink" href="javascript:;" onclick="reRecycleBin(\'' + rdata.dirs[i].rname.replace(/'/,"\\'") + '\',this)">'+lan.files.recycle_bin_re+'</a>\
                             | <a class="btlink" href="javascript:;" onclick="delRecycleBin(\'' + rdata.dirs[i].rname.replace(/'/,"\\'") + '\',this)">'+lan.files.recycle_bin_del+'</a>\
                        </td>\
                    </tr>';
                }
                for(var i=0;i<rdata.files.length;i++){
                    if(rdata.files[i].name.indexOf('BTDB_') != -1){
                        var shortwebname = rdata.files[i].name.replace(/'/,"\\'");
                        var shortpath = rdata.files[i].dname;
                        if(shortwebname.length > 20) shortwebname = shortwebname.substring(0, 20) + "...";
                        if(shortpath.length > 20) shortpath = shortpath.substring(0, 20) + "...";
                        body += '<tr>\
                            <td><span class="ico ico-'+(getExtName(rdata.files[i].name))+'"></span><span class="tname" title="'+rdata.files[i].name+'">'+shortwebname.replace('BTDB_','')+'</span></td>\
                            <td><span title="'+rdata.files[i].dname+'">mysql://'+shortpath.replace('BTDB_','')+'</span></td>\
                            <td>-</td>\
                            <td>'+getLocalTime(rdata.files[i].time)+'</td>\
                            <td style="text-align: right;">\
                                <a class="btlink" href="javascript:;" onclick="reRecycleBin(\'' + rdata.files[i].rname.replace(/'/,"\\'") + '\',this)">'+lan.files.recycle_bin_re+'</a>\
                                 | <a class="btlink" href="javascript:;" onclick="delRecycleBin(\'' + rdata.files[i].rname.replace(/'/,"\\'") + '\',this)">'+lan.files.recycle_bin_del+'</a>\
                            </td>\
                        </tr>';
                            
                        continue;
                    }
                    var shortwebname = rdata.files[i].name.replace(/'/,"\\'");
                    var shortpath = rdata.files[i].dname;
                    if(shortwebname.length > 20) shortwebname = shortwebname.substring(0, 20) + "...";
                    if(shortpath.length > 20) shortpath = shortpath.substring(0, 20) + "...";
                    body += '<tr>\
                                <td><span class="ico ico-'+(getExtName(rdata.files[i].name))+'"></span><span class="tname" title="'+rdata.files[i].name+'">'+shortwebname+'</span></td>\
                                <td><span title="'+rdata.files[i].dname+'">'+shortpath+'</span></td>\
                                <td>'+toSize(rdata.files[i].size)+'</td>\
                                <td>'+getLocalTime(rdata.files[i].time)+'</td>\
                                <td style="text-align: right;">\
                                    <a class="btlink" href="javascript:;" onclick="reRecycleBin(\'' + rdata.files[i].rname.replace(/'/,"\\'") + '\',this)">'+lan.files.recycle_bin_re+'</a>\
                                     | <a class="btlink" href="javascript:;" onclick="delRecycleBin(\'' + rdata.files[i].rname.replace(/'/,"\\'") + '\',this)">'+lan.files.recycle_bin_del+'</a>\
                                </td>\
                            </tr>'
                }
                $("#RecycleBody").html(body);
                return;
                break;
            case 2:
                for(var i=0;i<rdata.dirs.length;i++){
                    var shortwebname = rdata.dirs[i].name.replace(/'/,"\\'");
                    var shortpath = rdata.dirs[i].dname;
                    if(shortwebname.length > 20) shortwebname = shortwebname.substring(0, 20) + "...";
                    if(shortpath.length > 20) shortpath = shortpath.substring(0, 20) + "...";
                    body += '<tr>\
                        <td><span class=\'ico ico-folder\'></span><span class="tname" title="'+rdata.dirs[i].name+'">'+shortwebname+'</span></td>\
                        <td><span title="'+rdata.dirs[i].dname+'">'+shortpath+'</span></td>\
                        <td>'+toSize(rdata.dirs[i].size)+'</td>\
                        <td>'+getLocalTime(rdata.dirs[i].time)+'</td>\
                        <td style="text-align: right;">\
                            <a class="btlink" href="javascript:;" onclick="reRecycleBin(\'' + rdata.dirs[i].rname.replace(/'/,"\\'") + '\',this)">'+lan.files.recycle_bin_re+'</a>\
                             | <a class="btlink" href="javascript:;" onclick="delRecycleBin(\'' + rdata.dirs[i].rname.replace(/'/,"\\'") + '\',this)">'+lan.files.recycle_bin_del+'</a>\
                        </td>\
                    </tr>'
                }
                $("#RecycleBody").html(body);
                return;
                break;
            case 3:
                for(var i=0;i<rdata.files.length;i++){
                    if(rdata.files[i].name.indexOf('BTDB_') != -1) continue;
                    var shortwebname = rdata.files[i].name.replace(/'/,"\\'");
                    var shortpath = rdata.files[i].dname;
                    if(shortwebname.length > 20) shortwebname = shortwebname.substring(0, 20) + "...";
                    if(shortpath.length > 20) shortpath = shortpath.substring(0, 20) + "...";
                    body += '<tr>\
                        <td><span class="ico ico-'+(getExtName(rdata.files[i].name))+'"></span><span class="tname" title="'+rdata.files[i].name+'">'+shortwebname+'</span></td>\
                        <td><span title="'+rdata.files[i].dname+'">'+shortpath+'</span></td>\
                        <td>'+toSize(rdata.files[i].size)+'</td>\
                        <td>'+getLocalTime(rdata.files[i].time)+'</td>\
                        <td style="text-align: right;">\
                            <a class="btlink" href="javascript:;" onclick="reRecycleBin(\'' + rdata.files[i].rname.replace(/'/,"\\'") + '\',this)">'+lan.files.recycle_bin_re+'</a>\
                             | <a class="btlink" href="javascript:;" onclick="delRecycleBin(\'' + rdata.files[i].rname.replace(/'/,"\\'") + '\',this)">'+lan.files.recycle_bin_del+'</a>\
                        </td>\
                    </tr>';
                }
                $("#RecycleBody").html(body);
                return;
                break;
            case 4:
                for(var i=0;i<rdata.files.length;i++){
                    if(reisImage(getFileName(rdata.files[i].name))){
                        var shortwebname = rdata.files[i].name.replace(/'/,"\\'");
                        var shortpath = rdata.files[i].dname;
                        if(shortwebname.length > 20) shortwebname = shortwebname.substring(0, 20) + "...";
                        if(shortpath.length > 20) shortpath = shortpath.substring(0, 20) + "...";
                        body += '<tr>\
                            <td><span class="ico ico-'+(getExtName(rdata.files[i].name))+'"></span><span class="tname" title="'+rdata.files[i].name+'">'+shortwebname+'</span></td>\
                            <td><span title="'+rdata.files[i].dname+'">'+shortpath+'</span></td>\
                            <td>'+toSize(rdata.files[i].size)+'</td>\
                            <td>'+getLocalTime(rdata.files[i].time)+'</td>\
                            <td style="text-align: right;">\
                                <a class="btlink" href="javascript:;" onclick="reRecycleBin(\'' + rdata.files[i].rname.replace(/'/,"\\'") + '\',this)">'+lan.files.recycle_bin_re+'</a>\
                                 | <a class="btlink" href="javascript:;" onclick="delRecycleBin(\'' + rdata.files[i].rname.replace(/'/,"\\'") + '\',this)">'+lan.files.recycle_bin_del+'</a>\
                            </td>\
                        </tr>';
                    }
                }
                $("#RecycleBody").html(body);
                return;
                break;
            case 5:
                for(var i=0;i<rdata.files.length;i++){
                    if(rdata.files[i].name.indexOf('BTDB_') != -1) continue;
                    if(!(reisImage(getFileName(rdata.files[i].name)))){
                        var shortwebname = rdata.files[i].name.replace(/'/,"\\'");
                        var shortpath = rdata.files[i].dname;
                        if(shortwebname.length > 20) shortwebname = shortwebname.substring(0, 20) + "...";
                        if(shortpath.length > 20) shortpath = shortpath.substring(0, 20) + "...";
                        body += '<tr>\
                                <td><span class="ico ico-'+(getExtName(rdata.files[i].name))+'"></span><span class="tname" title="'+rdata.files[i].name+'">'+shortwebname+'</span></td>\
                                <td><span title="'+rdata.files[i].dname+'">'+shortpath+'</span></td>\
                                <td>'+toSize(rdata.files[i].size)+'</td>\
                                <td>'+getLocalTime(rdata.files[i].time)+'</td>\
                                <td style="text-align: right;">\
                                    <a class="btlink" href="javascript:;" onclick="reRecycleBin(\'' + rdata.files[i].rname.replace(/'/,"\\'") + '\',this)">'+lan.files.recycle_bin_re+'</a>\
                                     | <a class="btlink" href="javascript:;" onclick="delRecycleBin(\'' + rdata.files[i].rname.replace(/'/,"\\'") + '\',this)">'+lan.files.recycle_bin_del+'</a>\
                                </td>\
                            </tr>'
                    }
                }
                $("#RecycleBody").html(body);
                return;
        }
                
        
        var tablehtml = '<div class="re-head">\
                <div style="margin-left: 3px;" class="ss-text">\
                        <em>文件回收站</em>\
                        <div class="ssh-item">\
                                <input class="btswitch btswitch-ios" id="setRecycleBin" type="checkbox" '+(rdata.status?'checked':'')+'>\
                                <label class="btswitch-btn" for="setRecycleBin" onclick="setRecycleBin()"></label>\
                        </div>\
                </div>\
                <span style="line-height: 32px; margin-left: 30px;">注意：关闭回收站，删除的文件无法恢复！</span>\
                <button style="float: right" class="btn btn-default btn-sm" onclick="closeRecycleBin();">清空回收站</button>\
                </div>\
                <div class="re-con">\
                    <div class="re-con-menu">\
                        <p class="on" onclick="recycleBin(1)">全部</p>\
                        <p onclick="recycleBin(2)">文件夹</p>\
                        <p onclick="recycleBin(3)">文件</p>\
                        <p onclick="recycleBin(4)">图片</p>\
                        <p onclick="recycleBin(5)">文档</p>\
                    </div>\
                    <div class="re-con-con">\
                    <div style="margin: 15px;" class="divtable">\
                    <table width="100%" class="table table-hover">\
                        <thead>\
                            <tr>\
                                <th>文件名</th><th>原位置</th>\
                                <th>大小</th><th width="150">删除时间</th>\
                                <th style="text-align: right;" width="110">操作</th>\
                            </tr>\
                        </thead>\
                    <tbody id="RecycleBody" class="list-list">'+body+'</tbody>\
            </table></div></div></div>';
        if(type == 'open'){
            layer.open({
                type: 1,
                shift: 5,
                closeBtn: 1,
                area: ['80%','606px'],
                title: lan.files.recycle_bin_title,
                content: tablehtml
            });
            
            if(window.location.href.indexOf("database") != -1){
                recycleBin(6);
                $(".re-con-menu p:last-child").addClass("on").siblings().removeClass("on");
            }else{
                recycleBin(1);
            }
        }
        $(".re-con-menu p").click(function(){
            $(this).addClass("on").siblings().removeClass("on");
        })
    },'json');
}

//去扩展名不处理
function getFileName(name){
    var text = name.split("/");
    var n = text.length-1;
    text = text[n];
    return text;
}

//判断图片文件
function reisImage(fileName){
    var exts = ['jpg','jpeg','png','bmp','gif','tiff','ico'];
    for(var i=0; i<exts.length; i++){
        if(fileName == exts[i]) {
            return true;
        }
    }
    return false;
}

//从回收站恢复文件
function reRecycleBin(path,obj){
    layer.confirm(lan.files.recycle_bin_re_msg,{title:lan.files.recycle_bin_re_title,closeBtn:2,icon:3},function(){
        var loadT = layer.msg(lan.files.recycle_bin_re_the,{icon:16,time:0,shade: [0.3, '#000']});
        $.post('/files/re_recycle_bin','path='+encodeURIComponent(path),function(rdata){
            layer.close(loadT);
            layer.msg(rdata.msg,{icon:rdata.status?1:5});
            $(obj).parents('tr').remove();
        },'json');
    });
}

//从回收站删除
function delRecycleBin(path,obj){
    layer.confirm(lan.files.recycle_bin_del_msg,{title:lan.files.recycle_bin_del_title,closeBtn:2,icon:3},function(){
        var loadT = layer.msg(lan.files.recycle_bin_del_the,{icon:16,time:0,shade: [0.3, '#000']});
        $.post('/files/del_recycle_bin','path='+encodeURIComponent(path),function(rdata){
            layer.close(loadT);
            layer.msg(rdata.msg,{icon:rdata.status?1:5});
            $(obj).parents('tr').remove();
        },'json');
    });
}

//清空回收站
function closeRecycleBin(){
    layer.confirm('清空回收站操作会永久删除回收站中的文件，继续吗？',{title:'清空回收站',closeBtn:2,icon:3},function(){
        var loadT = layer.msg("<div class='myspeed'>正在删除,请稍候...</div>",{icon:16,time:0,shade: [0.3, '#000']});
        setTimeout(function(){
            getSpeed('.myspeed');
        },1000);
        $.post('/files/close_recycle_bin', '', function(rdata){
            layer.close(loadT);
            layer.msg(rdata.msg,{icon:rdata.status?1:5});
            $("#RecycleBody").html('');
        },'json');
    });
}


//回收站开关
function setRecycleBin(db){
    var loadT = layer.msg('正在处理,请稍候...',{icon:16,time:0,shade: [0.3, '#000']});
    var data = {}
    if(db == 1){
        data = {db:db};
    }
    $.post('/files/recycle_bin',data,function(rdata){
        layer.close(loadT);
        layer.msg(rdata.msg,{icon:rdata.status?1:5});
    },'json');
}

function openFilename(obj){
    var path = $(obj).attr('data-path');
    var ext = getSuffixName(path);

    // console.log(path,ext);
    if (inArray(ext,['html','htm','php','lua','rs','py','txt','md','js','css','scss','json','c','h','pl','java','log','conf','sh','json','ini', 'yml','yaml'])){
        onlineEditFile(0, path);
    }

    if (inArray(ext,['png','jpeg','jpg','gif','webp','bmp','ico'])){
        getImage(path);
    }

    if (inArray(ext,['svg'])){
        var url = '/files/download?filename='+path;
        layer.open({
            type:1,
            closeBtn: 1,
            title:"SVG预览",
            area: ['600px','500px'],
            maxmin:true,
            shadeClose: true,
            content: '<iframe width="100%" height="100%"\
                src="'+url+'"\
                frameborder="0"\
                border="0"\
                marginwidth="0"\
                marginheight="0"\
                scrolling="yes"\
                noresize=""\
                allowfullscreen="allowfullscreen"\
                mozallowfullscreen="mozallowfullscreen"\
                msallowfullscreen="msallowfullscreen"\
                oallowfullscreen="oallowfullscreen"\
                webkitallowfullscreen="webkitallowfullscreen"\
                allowfullscreen="true"></iframe>'
        });
    }
}

function searchFile(p){
    getFiles(p);
}

//处理排序
function listFileOrder(skey, obj){
    var or = getCookie('file_order');
    var orderType = 'desc';
    if(or){
        var or_arr = or.split('|');
        if(or.split('|')[1] == 'desc'){
            orderType = 'asc';
        } else if (or_arr[1] == 'asc'){
            orderType = 'none';
        } else {
            orderType = 'desc';
        }
    }
    setCookie('file_order',skey + '|' + orderType);
    getFiles(1);
    // console.log(obj,orderType);
    // if(orderType == 'desc'){
    //  $(obj).find(".glyphicon-triangle-top").remove();
    //  $(obj).append("<span class='glyphicon glyphicon-triangle-bottom' style='margin-left:5px;color:#bbb'></span>");
    // } else {
    //  $(obj).find(".glyphicon-triangle-bottom").remove();
    //  $(obj).append("<span class='glyphicon glyphicon-triangle-top' style='margin-left:5px;color:#bbb'></span>");
    // }
}

function makeFilePage(showRow, page = ''){
    var rows = ['10','50','100','200','500','1000','2000'];
    var rowOption = '';
    for(var i=0;i<rows.length;i++){
        var rowSelected = '';
        if(showRow == rows[i]) rowSelected = 'selected';
        rowOption += '<option value="'+rows[i]+'" '+rowSelected+'>'+rows[i]+'</option>';
    }
    
    //分页
    $("#filePage").html(page);
    $("#filePage div").append("<span class='Pcount-item'>每页<select name='file_page' style='margin-left: 3px;margin-right: 3px;border:#ddd 1px solid;' class='showRow'>"+rowOption+"</select>条</span>");
    $("#filePage .Pcount").css("left","16px"); 
}

//获取符合当前时间的高亮时间字符串
function getMatchTime(a) {
    var fileTimeStr = getLocalTime(a);
    var currentTimeStr = new Date().format("yyyy/MM/dd hh:mm:ss");
    
    var fileParts = fileTimeStr.split(/([\/\s:])/);
    var currParts = currentTimeStr.split(/([\/\s:])/);
    
    var matchStr = "";
    var restStr = "";
    var matched = true;
    
    for (var i = 0; i < fileParts.length; i++) {
        if (matched && fileParts[i] === currParts[i]) {
            if (i % 2 !== 0) {
                if (i + 1 < fileParts.length && fileParts[i+1] === currParts[i+1]) {
                    matchStr += fileParts[i];
                } else {
                    matched = false;
                    restStr += fileParts[i];
                }
            } else {
                matchStr += fileParts[i];
            }
        } else {
            matched = false;
            restStr += fileParts[i];
        }
    }
    
    if (matchStr !== "") {
        return "<span style='color:red;'>" + matchStr + "</span>" + restStr;
    }
    return restStr;
}

//取数据
function getFiles(Path) {
    if(isNaN(Path)){
        var p = 1;
    } else {
        var p = Path;
        Path = getCookie('open_dir_path');
    }

    var post = {};
    post['path'] = Path;
    post['p'] = p;

    var file_row = $.cookie('file_row');
    if(!file_row) {
        file_row = '100';
    }
    post['row'] = file_row;

    var body = '';
    var totalSize = 0;

    var search = '';
    var search_file = $("#search_file").val();

    if(search_file.length > 0){
        post['search'] = search_file;
    }

    var search_all = '';
    var all = $('#search_all').hasClass('active');
    if(all){
        post['all'] = 'yes';
    }

    var file_order = $.cookie('file_order');
    if (file_order){
        post['order'] = file_order.replace('|',' ');
    } else {
        post['order'] = 'fname asc';
    }


    var loadT = layer.load();
    $.post('/files/get_dir', post, function(rdata) {
        layer.close(loadT);
        
        window.currentFiles = [];
        window.currentFilesMap = {};
        if (rdata.dir) {
            for (var i = 0; i < rdata.dir.length; i++) {
                var fmp = rdata.dir[i].split(";");
                window.currentFiles.push(fmp[0]);
                window.currentFilesMap[fmp[0]] = {
                    size: parseInt(fmp[1]),
                    isDir: true
                };
            }
        }
        if (rdata.files) {
            for (var i = 0; i < rdata.files.length; i++) {
                if (rdata.files[i] == null) continue;
                var fmp = rdata.files[i].split(";");
                window.currentFiles.push(fmp[0]);
                window.currentFilesMap[fmp[0]] = {
                    size: parseInt(fmp[1]),
                    isDir: false
                };
            }
        }

        //构建分页
        makeFilePage(file_row,rdata.page);

        if(rdata.dir == null) {
            rdata.dir = [];
        }

        for (var i = 0; i < rdata.dir.length; i++) {
            var fmp = rdata.dir[i].split(";");
            var cnametext =fmp[0] + fmp[5];

            fmp[0] = fmp[0].replace(/'/, "\\'");
            if(cnametext.length>20){
                cnametext = cnametext.substring(0,20) + '...';
            }

            if(isChineseChar(cnametext)){
                if(cnametext.length>10){
                    cnametext = cnametext.substring(0,10) + '...';
                }
            }

            var timetext ='--';
            if(getCookie('rank') == 'a'){
                //列表展示
                $("#set_list").addClass("active");
                $("#set_icon").removeClass("active");
                body += "<tr class='folderBoxTr' data-path='" + rdata.path + "/" + fmp[0] + "' filetype='dir'>\
                    <td><input type='checkbox' name='id' value='"+fmp[0]+"'></td>\
                    <td class='column-name'><span class='cursor' onclick=\"getFiles('" + rdata.path + "/" + fmp[0] + "')\">\
                    <span class='ico ico-folder'></span><a class='text' title='" + fmp[0] + fmp[5] + "'>" + cnametext + "</a></span></td>\
                    <td><a class='btlink calculate-size-btn' onclick=\"calculateDirSize(event, this, '" + rdata.path + "/" + fmp[0] + "')\">计算</a></td>\
                    <td>"+getMatchTime(fmp[2])+"</td>\
                    <td>"+fmp[3]+"</td>\
                    <td>"+fmp[4]+"</td>\
                    <td class='editmenu'><span>\
                        <a class='btlink' href='javascript:;' onclick=\"copyFile('" + rdata.path +"/"+ fmp[0] + "')\">复制</a> | \
                        <a class='btlink' href='javascript:;' onclick=\"cutFile('" + rdata.path +"/"+ fmp[0]+ "')\">剪切</a> | \
                        <a class='btlink' href='javascript:;' onclick=\"reName(0,'" + fmp[0] + "');\">重命名</a> | \
                        <a class='btlink' href='javascript:;' onclick=\"setChmod(0,'" + rdata.path + "/"+fmp[0] + "');\">权限</a> | \
                        <a class='btlink' href='javascript:;' onclick=\"zip('" + rdata.path +"/" +fmp[0] + "');\">压缩</a> | \
                        <a class='btlink' href='javascript:;' onclick=\"deleteDir('" + rdata.path +"/"+ fmp[0] + "')\">删除</a></span>\
                    </td>\
                </tr>";
            } else {
                //图标展示
                $("#set_icon").addClass("active");
                $("#set_list").removeClass("active");
                body += "<div class='file folderBox menufolder' data-path='" + rdata.path + "/" + fmp[0] + "' filetype='dir' title='"+lan.files.file_name+"：" + fmp[0]+"&#13;"+lan.files.file_size+"：" 
                        + toSize(fmp[1])+"&#13;"+lan.files.file_etime+"："+getLocalTime(fmp[2])+"&#13;"+lan.files.file_auth+"："+fmp[3]+"&#13;"+lan.files.file_own+"："+fmp[4]+"'>\
                        <input type='checkbox' name='id' value='"+fmp[0]+"'>\
                        <div class='ico ico-folder' ondblclick=\"getFiles('" + rdata.path + "/" + fmp[0] + "')\"></div>\
                        <div class='titleBox' onclick=\"getFiles('" + rdata.path + "/" + fmp[0] + "')\">\
                            <span class='tname'>" + fmp[0] + "</span>\
                        </div>\
                    </div>";
            }
        }

        for (var i = 0; i < rdata.files.length; i++) {
            if(rdata.files[i] == null) continue;
            var fmp = rdata.files[i].split(";");
            var bodyZip = '';
            var download = '';
            var cnametext =fmp[0] + fmp[5];
            fmp[0] = fmp[0].replace(/'/,"\\'");

            if(isChineseChar(cnametext)){
                if(cnametext.length>16){
                    cnametext = cnametext.substring(0,16) + '...';
                }
            } else{
                if( cnametext.length > 48 ){
                    cnametext = cnametext.substring(0,48) + '...';
                }
            }

            var displayCompress = 1;
            if(isCompressFile(fmp[0])){
                bodyZip = "<a class='btlink' href='javascript:;' onclick=\"unCompressFile('" + rdata.path +"/" +fmp[0] + "')\">解压</a> | ";
            } else {
                bodyZip = "<a class='btlink' href='javascript:;' onclick=\"zip('" + rdata.path +"/" +fmp[0] + "');\">压缩</a> | ";
            }
            
            if(isText(fmp[0])){
                bodyZip += "<a class='btlink' href='javascript:;' onclick=\"onlineEditFile(0,'" + rdata.path +"/"+ fmp[0] + "')\">编辑</a> | ";
            }

            if(isImage(fmp[0])){
                download = "<a class='btlink' href='javascript:;' onclick=\"getImage('" + rdata.path +"/"+ fmp[0] + "')\">预览</a> | ";
            } else {
                download = "<a class='btlink' href='javascript:;' onclick=\"getFileBytes('" + rdata.path +"/"+ fmp[0] + "',"+fmp[1]+")\">下载</a> | ";
            }
            
            totalSize +=  parseInt(fmp[1]);
            if(getCookie("rank")=="a"){
                body += "<tr style='cursor:pointer;' class='folderBoxTr' data-path='" + rdata.path +"/"+ fmp[0] + "' filetype='" + fmp[0] + "' ondblclick='openFilename(this)'>\
                    <td><input type='checkbox' name='id' value='"+fmp[0]+"'></td>\
                    <td class='column-name'><span class='ico ico-"+(getExtName(fmp[0]))+"'></span><a class='text' title='" + fmp[0] + fmp[5] + "'>" + cnametext + "</a></td>\
                    <td>" + (toSize(fmp[1])) + "</td>\
                    <td>" + ((fmp[2].length > 11)?fmp[2]:getMatchTime(fmp[2])) + "</td>\
                    <td>"+fmp[3]+"</td>\
                    <td>"+fmp[4]+"</td>\
                    <td class='editmenu'>\
                    <span><a class='btlink' href='javascript:;' onclick=\"copyFile('" + rdata.path +"/"+ fmp[0] + "')\">复制</a> | \
                    <a class='btlink' href='javascript:;' onclick=\"cutFile('" + rdata.path +"/"+ fmp[0] + "')\">剪切</a> | \
                    <a class='btlink' href='javascript:;' onclick=\"reName(0,'" + fmp[0] + "')\">重命名</a> | \
                    <a class='btlink' href=\"javascript:setChmod(0,'" + rdata.path +"/"+ fmp[0] + "');\">权限</a> | "
                    + bodyZip
                    + download
                    + "<a class='btlink' href='javascript:;' onclick=\"deleteFile('" + rdata.path +"/"+ fmp[0] + "')\">删除</a>\
                    </span></td>\
                </tr>";
            }
            else{
                body += "<div class='file folderBox menufile' data-path='" + rdata.path +"/"+ fmp[0] + "' filetype='"+fmp[0]+"' title='文件名：" + fmp[0]+"&#13;大小："
                    + toSize(fmp[1])+"&#13;修改时间："+getLocalTime(fmp[2])+"&#13;权限："+fmp[3]+"&#13;所有者："+fmp[4]+"' >\
                    <input type='checkbox' name='id' value='"+fmp[0]+"' />\
                    <div data-path='" + rdata.path +"/"+ fmp[0] + "' filetype='"+fmp[0]+"' class='ico ico-"+(getExtName(fmp[0]))+"' ondblclick='javascript;openFilename(this);'></div>\
                    <div class='titleBox'>\
                        <span class='tname'>" + fmp[0] + "</span>\
                    </div>\
                </div>";
            }
        }
        var dirInfo = '(共{1}个目录与{2}个文件,大小:'.replace('{1}',rdata.dir.length+'').replace('{2}',rdata.files.length+'')+'<font id="pathSize">'
            + (toSize(totalSize))+'<a class="btlink ml5" onClick="getPathSize()">获取</a></font>)';
        $("#dir_info").html(dirInfo);
        if( getCookie('rank') == 'a' ){

            // console.log(post['order']);
            var size_icon = '<span class="glyphicon glyphicon-triangle-top" style="margin-left:5px;color:#bbb">';
            if (post['order'] == 'size desc'){
                size_icon = '<span class="glyphicon glyphicon-triangle-bottom" style="margin-left:5px;color:#bbb">';
            } else if (post['order'] == 'size asc'){
                size_icon = '<span class="glyphicon glyphicon-triangle-top" style="margin-left:5px;color:#bbb">';
            } else {
                size_icon = '<span class="glyphicon glyphicon-option-horizontal" style="top:3px;margin-left:5px;color:#bbb">';
            }

            var mtime_icon = '<span class="glyphicon glyphicon-triangle-top" style="margin-left:5px;color:#bbb">';
            if (post['order'] == 'mtime desc'){
                mtime_icon = '<span class="glyphicon glyphicon-triangle-bottom" style="margin-left:5px;color:#bbb">';
            } else if (post['order'] == 'mtime asc'){
                mtime_icon = '<span class="glyphicon glyphicon-triangle-top" style="margin-left:5px;color:#bbb">';
            } else {
                mtime_icon = '<span class="glyphicon glyphicon-option-horizontal" style="top:3px;margin-left:5px;color:#bbb">';
            }

            var fname_icon = '<span class="glyphicon glyphicon-triangle-top" style="margin-left:5px;color:#bbb">';
            if (post['order'] == 'fname desc'){
                fname_icon = '<span class="glyphicon glyphicon-triangle-bottom" style="margin-left:5px;color:#bbb">';
            } else if (post['order'] == 'fname asc'){
                fname_icon = '<span class="glyphicon glyphicon-triangle-top" style="margin-left:5px;color:#bbb">';
            } else {
                fname_icon = '<span class="glyphicon glyphicon-option-horizontal" style="top:3px;margin-left:5px;color:#bbb">';
            }

            var tablehtml = '<table width="100%" border="0" cellpadding="0" cellspacing="0" class="table table-hover">\
                <thead>\
                    <tr>\
                        <th width="30"><input type="checkbox" id="setBox" placeholder=""></th>\
                        <th onclick="listFileOrder(\'fname\',this)" style="cursor: pointer;">文件名'+fname_icon+'</th>\
                        <th onclick="listFileOrder(\'size\',this)" style="cursor: pointer;">大小'+size_icon+'</th>\
                        <th onclick="listFileOrder(\'mtime\',this)" style="cursor: pointer;">修改时间'+mtime_icon+'</th>\
                        <th>权限</th>\
                        <th>所有者</th>\
                        <th style="text-align: right;" width="330">操作</th>\
                    </tr>\
                </thead>\
                <tbody id="filesBody" class="list-list">'+body+'</tbody>\
            </table>';
            $("#fileCon").removeClass("fileList").html(tablehtml);
            $("#tipTools").width($("#fileCon").width());
        } else {
            $("#fileCon").addClass("fileList").html(body);
            $("#tipTools").width($("#fileCon").width());
        }
        $("#DirPathPlace input").val(rdata.path);
        var BarTools = '<div class="btn-group">\
            <button class="btn btn-default btn-sm dropdown-toggle" type="button" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">\
                新建<span class="caret"></span>\
            </button>\
            <ul class="dropdown-menu">\
                <li><a href="javascript:createFile(0,\'' + Path + '\');">新建空白文件</a></li>\
                <li><a href="javascript:createDir(0,\'' + Path + '\');">新建目录</a></li>\
            </ul>\
        </div>';
        if (rdata.path != '/') {
            BarTools += ' <button onclick="javascript:backDir();" class="btn btn-default btn-sm glyphicon glyphicon-arrow-left" title="返回上一级"></button>';
        }
        setCookie('open_dir_path',rdata.path);
        BarTools += ' <button onclick="javascript:getFiles(\'' + rdata.path + '\');" class="btn btn-default btn-sm glyphicon glyphicon-refresh" title="刷新"></button>\
            <button onclick="webShell()" title="终端" type="button" class="btn btn-default btn-sm"><em class="ico-cmd"></em></button>';
        var copyName = getCookie('copyFileName');
        var cutName = getCookie('cutFileName');
        var isPaste = (copyName == 'null') ? cutName : copyName;
        // console.log('isPaste:',isPaste);
        //---
        if (isPaste != 'null' && isPaste != undefined) {
            BarTools += ' <button onclick="javascript:pasteFile(\'' + (getFileName(isPaste)) + '\');" class="btn btn-Warning btn-sm">粘贴</button>';
        }
        
        $("#Batch").html('');
        var batchTools = '';
        var isBatch = getCookie('BatchSelected');
        if (isBatch == 1 || isBatch == '1') {
            batchTools += ' <button onclick="javascript:batchPaste();" class="btn btn-default btn-sm">粘贴所有</button>';
        }
        $("#Batch").html(batchTools);

        $("#setBox").prop("checked", false);
        
        $("#BarTools").html(BarTools);
        
        $("input[name=id]").off("click").click(function(){
            if($(this).prop("checked")) {
                $(this).prop("checked", true);
                $(this).parents("tr").addClass("ui-selected");
            }
            else{
                $(this).prop("checked", false);
                $(this).parents("tr").removeClass("ui-selected");
            }
            showSeclect();
        });

        $("#setBox").off("click").click(function() {
            if ($(this).prop("checked")) {
                $("input[name=id]").prop("checked", true);
                $("#filesBody > tr").addClass("ui-selected");
                
            } else {
                $("input[name=id]").prop("checked", false);
                $("#filesBody > tr").removeClass("ui-selected");
            }
            showSeclect();
        });
        //阻止冒泡
        $("#filesBody .btlink").off("click").click(function(e){
            e.stopPropagation();
        });
        $("input[name=id]").off("dblclick").dblclick(function(e){
            e.stopPropagation();
        });


        //禁用右键
        $("#fileCon").off("contextmenu").bind("contextmenu",function(e){
            return false;
        });
        bindselect();

        // //绑定右键
        $("#fileCon").off("mousedown").mousedown(function(e){
            var count = totalFile();
            if(e.which == 3) {
                if(count>1){
                    rightMenuClickAll(e);
                } else {
                    return;
                }
            }
        });

        $(".folderBox,.folderBoxTr").off("mousedown").mousedown(function(e){
            var box = $(this);
            var option = rightMenuClick(box.attr("filetype"),box.attr("data-path"),box.find("input").val());
            box.contextify(option);
        });
        
        //每页行数
        $(".showRow").off("change").change(function(){
            setCookie('file_row',$(this).val());
            getFiles(p);
        });
        pathPlaceBtn(rdata.path);
        if(typeof(updateActiveTabPath) == "function") updateActiveTabPath(rdata.path);
        if(typeof(renderFileTabs) == "function") renderFileTabs();
    },'json');
    // setTimeout(function(){getCookie('open_dir_path');},200);
}


//统计选择数量
function totalFile(){
    var el = $("input[name='id']");
    var len = el.length;
    var count = 0;
    for(var i=0;i<len;i++){
        if(el[i].checked == true){
            count++;
        }
    }
    return count;
}
//绑定操作
function bindselect(){
    $("#filesBody,#fileCon").selectable({
        autoRefresh: false,
        filter:"tr,.folderBox",
        cancel: "a,span,input,.ico-folder",
        selecting:function(e){
            $(".ui-selecting").find("input").prop("checked", true);
            showSeclect();
        },
        selected:function(e){
            $(".ui-selectee").find("input").prop("checked", false);
            $(".ui-selected", this).each(function() {
                $(this).find("input").prop("checked", true);
                showSeclect();
            });
        },
        unselecting:function(e){
            $(".ui-selectee").find("input").prop("checked", false);
            $(".ui-selecting").find("input").prop("checked", true);
            showSeclect();
            $("#rmenu").hide();
        }
    });
    $("#filesBody,#fileCon").selectable("refresh");
    //重绑图标点击事件
    $(".ico-folder").click(function(){
        $(this).parent().addClass("ui-selected").siblings().removeClass("ui-selected");
        $(".ui-selectee").find("input").prop("checked", false);
        $(this).prev("input").prop("checked", true);
        showSeclect();
    })
}
//选择操作
function showSeclect(){
    var count = totalFile();
    var batchTools = '';
    if(count > 1){
        batchTools = '<button onclick="javascript:batch(1);" class="btn btn-default btn-sm">复制</button>\
          <button onclick="javascript:batch(2);" class="btn btn-default btn-sm">剪切</button>\
          <button onclick="javascript:batch(3);" class="btn btn-default btn-sm">权限</button>\
          <button onclick="javascript:batch(5);" class="btn btn-default btn-sm">压缩</button>\
          <button onclick="javascript:batch(4);" class="btn btn-default btn-sm">删除</button>';
    }else{
        //setCookie('BatchSelected', null);
    }
    $("#Batch").html(batchTools);
}

//滚动条事件
$(window).scroll(function () {
    if($(window).scrollTop() > 16){
        $("#tipTools").css({"position":"fixed","top":"0","left":"195px","box-shadow":"0 1px 10px 3px #ccc"});
    }else{
        $("#tipTools").css({"position":"absolute","top":"42px","left":"0","box-shadow":"none"});
    }
});
$("#tipTools").width($(".file-box").width());
$("#PathPlaceBtn").width($(".file-box").width()-700);
$("#DirPathPlace input").width($(".file-box").width()-700);
if($(window).width()<1160){
    $("#PathPlaceBtn").width(290);
}
window.onresize = function(){
    $("#tipTools").width($(".file-box").width()-30);
    $("#PathPlaceBtn").width($(".file-box").width()-700);
    $("#DirPathPlace input").width($(".file-box").width()-700);
    if($(window).width()<1160){
        $("#PathPlaceBtn,#DirPathPlace input").width(290);
    }
    pathLeft();
    isDiskWidth();
}

//批量操作
function batch(type,access){
    var path = $("#DirPathPlace input").val();
    var el = document.getElementsByTagName('input');
    var len = el.length;
    var data='path='+path+'&type='+type;
    var name = 'data';
    var datas = [];
    
    var oldType = getCookie('BatchPaste');

    for(var i=0;i<len;i++){
        if(el[i].checked == true && el[i].value != 'on'){
            datas.push(el[i].value)
        }
    }
    data += "&data=" + encodeURIComponent(JSON.stringify(datas))
    
    if(type == 3 && access == undefined){
        setChmod(0,lan.files.all);
        return;
    }
    
    if(type < 3) setCookie('BatchSelected', '1');
    setCookie('BatchPaste',type);
    
    if(access == 1){
        var access = $("#access").val();
        var chown = $("#chown").val();
        data += '&access='+access+'&user='+chown;
        layer.closeAll();
    }
    if(type == 4){
        allDeleteFileSub(data,path);
        setCookie('BatchPaste',oldType);
        return;
    }
    
    if(type == 5){
        var names = '';
        for(var i=0;i<len;i++){
            if(el[i].checked == true && el[i].value != 'on'){
                names += path + "/" + el[i].value + ',';
            }
        }
        // console.log(names);
        zip(names);
        return;
    }
        
    myloadT = layer.msg("<div class='myspeed'>正在处理,请稍候...</div>",{icon:16,time:0,shade: [0.3, '#000']});
    setTimeout(function(){getSpeed('.myspeed');},1000);
    // console.log(data);
    $.post('/files/set_batch_data',data,function(rdata){
        layer.close(myloadT);
        getFiles(path);
        layer.msg(rdata.msg,{icon:1});
    },'json');
}

//批量粘贴
function batchPaste(){
    var path = $("#DirPathPlace input").val();
    var type = getCookie('BatchPaste');
    var data = 'type='+type+'&path='+path;

    $.post('/files/check_exists_files',{dfile:path},function(rdata){
        var result = rdata['data'];
        if(result.length > 0){
            var tbody = '';
            for(var i=0;i<result.length;i++){
                tbody += '<tr><td>'+result[i].filename+'</td><td>'+toSize(result[i].size)+'</td><td>'+getLocalTime(result[i].mtime)+'</td></tr>';
            }
            var mbody = '<div class="divtable"><table class="table table-hover" width="100%" border="0" cellpadding="0" cellspacing="0"><thead><th>文件名</th><th>大小</th><th>最后修改时间</th></thead>\
                        <tbody>'+tbody+'</tbody>\
                        </table></div>';
            safeMessage('即将覆盖以下文件',mbody,function(){
                batchPasteTo(data,path);
            });
            $(".layui-layer-page").css("width","500px");
        }else{
            batchPasteTo(data,path);
        }
    },'json');
}
    
function batchPasteTo(data,path){
    myloadT = layer.msg("<div class='myspeed'>正在处理,请稍候...</div>",{icon:16,time:0,shade: [0.3, '#000']});
    setTimeout(function(){getSpeed('.myspeed');},1000);
    $.post('/files/batch_paste',data,function(rdata){
        layer.close(myloadT);
        setCookie('BatchSelected', null);
        getFiles(path);
        layer.msg(rdata.msg,{icon:1});
    },'json');
}


function getSuffixName(fileName){
    var extArr = fileName.split(".");   
    var exts = ['folder-unempty','sql','c','cpp','cs','flv','css','js',
    'htm','html','java','log','mht','url','xml','ai','bmp','cdr','gif','ico',
    'jpeg','jpg','JPG','png','psd','webp','ape','avi','mkv','mov','mp3','mp4',
    'mpeg','mpg','rm','rmvb','swf','wav','webm','wma','wmv','rtf','docx','fdf','potm',
    'pptx','txt','xlsb','xlsx','7z','cab','iso','rar','zip','gz','bt','file','apk','bookfolder',
    'folder','folder-empty','fromchromefolder','documentfolder','fromphonefolder',
    'mix','musicfolder','picturefolder','videofolder','sefolder','access','mdb','accdb',
    'fla','doc','docm','dotx','dotm','dot','pdf',
    'ppt','pptm','pot','xls','csv','xlsm','scss','svg','pl','py','php','md','json','sh','conf'];
    var extLastName = extArr[extArr.length - 1];
    for(var i=0; i<exts.length; i++){
        if(exts[i]==extLastName){
            return exts[i];
        }
    }
    return 'file';
}

//取扩展名
function getExtName(fileName){
    var extArr = fileName.split(".");   
    var exts = ['folder','folder-unempty','sql','c','cpp','cs','flv','css','js',
    'htm','html','java','log','mht','php','url','xml','ai','bmp','cdr','gif','ico',
    'jpeg','jpg','JPG','png','psd','webp','ape','avi','flv','mkv','mov','mp3','mp4',
    'mpeg','mpg','rm','rmvb','swf','wav','webm','wma','wmv','rtf','docx','fdf','potm',
    'pptx','txt','xlsb','xlsx','7z','cab','iso','rar','zip','gz','bt','file','apk','bookfolder',
    'folder-empty','fromchromefolder','documentfolder','fromphonefolder',
    'mix','musicfolder','picturefolder','videofolder','sefolder','access','mdb','accdb',
    'fla','flv','doc','docm','dotx','dotm','dot','pdf','ppt','pptm','pot','xls','csv','xlsm'];
    var extLastName = extArr[extArr.length - 1];
    for(var i=0; i<exts.length; i++){
        if(exts[i]==extLastName){
            return exts[i];
        }
    }
    return 'file';
}

//操作显示
function ShowEditMenu(){
    $("#filesBody > tr").hover(function(){
        $(this).addClass("hover");
    },function(){
        $(this).removeClass("hover");
    }).click(function(){
        $(this).addClass("on").siblings().removeClass("on");
    });
}

//取磁盘
function getDisk() {
    var LBody = '';

    $.get('/system/disk_info', function(rdata) {
        var rdata = rdata.data;
        for (var i = 0; i < rdata.length; i++) {
            LBody += "<span onclick=\"getFiles('" + rdata[i].path + "')\" style=\"cursor:pointer;margin-right:10px;\">\
                <span class='glyphicon glyphicon-hdd'></span>&nbsp;" + (rdata[i].path=='/'?lan.files.path_root:rdata[i].path) + "(" + rdata[i].size[2] + ")</span>";
        }
        var trash = '<span id="recycle_bin" onclick="recycleBin(\'open\')" title="回收站" style="position: absolute; border-color: #ccc; right: 77px;">\
            <span class="glyphicon glyphicon-trash"></span>&nbsp;回收站</span>';
        $("#comlist").html(LBody+trash);
        isDiskWidth();
    },'json');
}

//返回上一级
function backDir() {
    var str = $("#DirPathPlace input").val().replace('//','/');
    if(str.substr(str.length-1,1) == '/'){
            str = str.substr(0,str.length-1);
    }
    var Path = str.split("/");
    var back = '/';
    if (Path.length > 2) {
        var count = Path.length - 1;
        for (var i = 0; i < count; i++) {
            back += Path[i] + '/';
        }
        if(back.substr(back.length-1,1) == '/'){
            back = back.substr(0,back.length-1);
        }
        getFiles(back);
    } else {
        back += Path[0];
        getFiles(back);
    }
    setTimeout('pathPlaceBtn(getCookie("open_dir_path"));',200);
}
//新建文件
function createFile(type, path) {
    if (type == 1) {
        var fileName = $("#newFileName").val();
        layer.msg(lan.public.the, {
            icon: 16,
            time: 10000
        });
        $.post('/files/create_file', 'path=' + encodeURIComponent(path + '/' + fileName), function(rdata) {
            layer.closeAll();
            layer.msg(rdata.msg, {
                icon: rdata.status ? 1 : 2
            });
            if(rdata.status){
                getFiles($("#DirPathPlace input").val());
                onlineEditFile(0,path + '/' + fileName);
            }
        },'json');
        return;
    }
    layer.open({
        type: 1,
        shift: 5,
        closeBtn: 1,
        area: '320px', 
        title: '新建空白文件',
        content: '<div class="bt-form pd20 pb70">\
                    <div class="line">\
                    <input type="text" class="bt-input-text" name="Name" id="newFileName" value="" placeholder="文件名" style="width:100%" />\
                    </div>\
                    <div class="bt-form-submit-btn">\
                    <button type="button" class="btn btn-danger btn-sm" onclick="layer.closeAll()">关闭</button>\
                    <button id="createFileBtn" type="button" class="btn btn-success btn-sm" onclick="createFile(1,\'' + path + '\')">新建</button>\
                    </div>\
                </div>',
        success:function(){
            $("#newFileName").focus().keyup(function(e){
                if(e.keyCode == 13) $("#createFileBtn").click();
            });
        }
    });
    
}
//新建目录
function createDir(type, path) {
    if (type == 1) {
        var dirName = $("#newDirName").val();
        layer.msg('正在处理,请稍候...', {
            icon: 16,
            time: 10000
        });
        $.post('/files/create_dir', 'path=' + encodeURIComponent(path + '/' + dirName), function(rdata) {
            layer.closeAll();
            layer.msg(rdata.msg, {
                icon: rdata.status ? 1 : 2
            });
            getFiles($("#DirPathPlace input").val());
        },'json');
        return;
    }
    layer.open({
        type: 1,
        shift: 5,
        closeBtn: 1,
        area: '320px',
        title: '新建目录',
        content: '<div class="bt-form pd20 pb70">\
                    <div class="line">\
                    <input type="text" class="bt-input-text" name="Name" id="newDirName" value="" placeholder="目录名称" style="width:100%" />\
                    </div>\
                    <div class="bt-form-submit-btn">\
                    <button type="button" class="btn btn-danger btn-sm btn-title" onclick="layer.closeAll()">关闭</button>\
                    <button type="button" id="createDirBtn" class="btn btn-success btn-sm btn-title" onclick="createDir(1,\'' + path + '\')">新建</button>\
                    </div>\
                </div>',
        success:function(){
            $("#newDirName").focus().keyup(function(e){
                if(e.keyCode == 13) {
                    $("#createDirBtn").click();
                }
            });
        }
    });
    
}

//删除文件
function deleteFile(fileName){
    layer.confirm(lan.get('recycle_bin_confirm',[fileName]),{title:'删除文件',closeBtn:2,icon:3},function(){
        layer.msg('正在处理,请稍候...',{icon:16,time:0,shade: [0.3, '#000']});
        $.post('/files/delete', 'path=' + encodeURIComponent(fileName), function(rdata) {
            layer.closeAll();
            layer.msg(rdata.msg, {
                icon: rdata.status ? 1 : 2,
            });
            getFiles($("#DirPathPlace input").val());
        },'json');
    });
}

//删除目录
function deleteDir(dirName){
    layer.confirm(lan.get('recycle_bin_confirm_dir',[dirName]),{title:'删除目录',closeBtn:2,icon:3},function(){
        layer.msg('正在处理,请稍候...',{icon:16,time:0,shade: [0.3, '#000']});
        $.post('/files/delete_dir', 'path=' + encodeURIComponent(dirName), function(rdata) {
            layer.closeAll();
            layer.msg(rdata.msg, {
                icon: rdata.status ? 1 : 2
            });
            getFiles($("#DirPathPlace input").val());
        },'json');
    });
}
//批量删除文件
function allDeleteFileSub(data,path){
    layer.confirm('您确实要把这些文件放入回收站吗?',{title:'批量删除文件',closeBtn:2,icon:3},function(){
        layer.msg("<div class='myspeed'>正在处理,请稍候...</div>",{icon:16,time:0,shade: [0.3, '#000']});
        setTimeout(function(){getSpeed('.myspeed');},1000);
        $.post('/files/set_batch_data',data,function(rdata){
            layer.closeAll();
            getFiles(path);
            layer.msg(rdata.msg,{icon:1});
        },'json');
    });
}

//重载文件列表
function reloadFiles(){
    setInterval(function(){
        var path = $("#DirPathPlace input").val();
        getFiles(path);
    },3000);
}
            
//下载文件
function downloadFile(action){
    
    if(action == 1){
        var fUrl = $("#mUrl").val();
        fUrl = encodeURIComponent(fUrl);

        var fpath = $("#dpath").val();
        fname = encodeURIComponent($("#dfilename").val());

        if (fUrl == "" ){
            layer.msg("URL地址不能为空!",{icon:2});
            return;
        }

        layer.closeAll();
        layer.msg(lan.files.down_task,{time:0,icon:16,shade: [0.3, '#000']});

        $.post('/files/download_file','path='+fpath+'&url='+fUrl+'&filename='+fname,function(rdata){
            layer.closeAll();
            getFiles(fpath);
            getTaskCount();
            layer.msg(rdata.msg,{icon:rdata.status?1:2});
        },'json');
        return;
    }

    var path = $("#DirPathPlace input").val();
    layer.open({
        type: 1,
        shift: 5,
        closeBtn: 1,
        area: '500px',
        btn:["确定","关闭"],
        title: lan.files.down_title,
        content: '<form class="bt-form pd20">\
                    <div class="line">\
                        <span class="tname">URL地址:</span>\
                        <input type="text" class="bt-input-text" name="url" id="mUrl" placeholder="URL地址" style="width:330px" />\
                    </div>\
                    <div class="line">\
                        <span class="tname ">下载到:</span>\
                        <input type="text" class="bt-input-text" name="path" id="dpath" value="'+path+'" placeholder="下载到" style="width:330px" />\
                    </div>\
                    <div class="line">\
                        <span class="tname">文件名:</span>\
                        <input type="text" class="bt-input-text" name="filename" id="dfilename" value="" placeholder="文件名" style="width:330px" />\
                    </div>\
                </form>',
        success:function(){
            $("#mUrl").keyup(function(){
                durl = $(this).val();
                tmp = durl.split('/');
                $("#dfilename").val(tmp[tmp.length-1]);
            });
        },
        yes:function(){
            downloadFile(1);
        }
    });
}

//重命名
function reName(type, fileName) {
    if (type == 1) {
        var path = $("#DirPathPlace input").val();
        var newFileName = encodeURIComponent(path + '/' + $("#newFileName").val());
        var oldFileName = encodeURIComponent(path + '/' + fileName);
        layer.msg(lan.public.the, {
            icon: 16,
            time: 10000
        });
        $.post('/files/mv_file', 'sfile=' + oldFileName + '&dfile=' + newFileName, function(rdata) {
            layer.closeAll();
            layer.msg(rdata.msg, {
                icon: rdata.status ? 1 : 2
            });
            getFiles(path);
        },'json');
        return;
    }
    layer.open({
        type: 1,
        shift: 5,
        closeBtn: 1,
        area: '320px', 
        title: '重命名',
        btn:["确定","取消"],
        content: '<div class="bt-form pd20">\
                    <div class="line">\
                    <input type="text" class="bt-input-text" name="Name" id="newFileName" value="' + fileName + '" placeholder="文件名" style="width:100%" />\
                    </div>\
                </div>',
        success:function(){
            $("#newFileName").focus().keyup(function(e){
                if(e.keyCode == 13) $(".layui-layer-btn0").click();
            });
        },
        yes:function(){
            reName(1,fileName.replace(/'/,"\\'"));
        }
    });
    
}
//剪切
function cutFile(fileName) {
    var path = $("#DirPathPlace input").val();
    setCookie('cutFileName', fileName);
    setCookie('copyFileName', null);
    layer.msg('已剪切', {
        icon: 1,
        time: 1000,
    });
    setTimeout(function(){
        getFiles(path);
    },1000);
}
//复制
function copyFile(fileName) {
    var path = $("#DirPathPlace input").val();
    setCookie('copyFileName', fileName);
    setCookie('cutFileName', null);
    layer.msg('已复制', {
        icon: 1,
        time: 1000,
    });

    setTimeout(function(){
        getFiles(path);
    },1000);
}
//粘贴
function pasteFile(fileName) {
    var path = $("#DirPathPlace input").val();
    var copyName = getCookie('copyFileName');
    var cutName = getCookie('cutFileName');
    var filename = copyName;
    if(cutName != 'null' && cutName != undefined) filename=cutName;
    filename = filename.split('/').pop();
    $.post('/files/check_exists_files',{dfile:path,filename:filename},function(result){
        if(result.length > 0){
            var tbody = '';
            for(var i=0;i<result.length;i++){
                tbody += '<tr><td>'+result[i].filename+'</td><td>'+toSize(result[i].size)+'</td><td>'+getMatchTime(result[i].mtime)+'</td></tr>';
            }
            var mbody = '<div class="divtable"><table class="table table-hover" width="100%" border="0" cellpadding="0" cellspacing="0"><thead><th>文件名</th><th>大小</th><th>最后修改时间</th></thead>\
                        <tbody>'+tbody+'</tbody>\
                        </table></div>';
            safeMessage('即将覆盖以下文件',mbody,function(){
                pasteTo(path,copyName,cutName,fileName);
            });
        } else {
            pasteTo(path,copyName,cutName,fileName);
        }
    },'json');
}


function pasteTo(path,copyName,cutName,fileName){
    if (copyName != 'null' && copyName != undefined) {
        layer.msg(lan.files.copy_the, {
            icon: 16,
            time: 0,shade: [0.3, '#000']
        });

        //同目录下
        if (copyName == path +'/'+ fileName){
            fileName = '__copy__'+ fileName;
        }

        $.post('/files/copy_file', 'sfile=' + encodeURIComponent(copyName) + '&dfile=' + encodeURIComponent(path +'/'+ fileName), function(rdata) {
            layer.closeAll();
            layer.msg(rdata.msg, {
                icon: rdata.status ? 1 : 2
            });
            getFiles(path);
        },'json');
        setCookie('copyFileName', null);
        setCookie('cutFileName', null);
        return;
    }
    
    if (cutName != 'null' && cutName != undefined) {
        layer.msg(lan.files.mv_the, {
            icon: 16,
            time: 0,shade: [0.3, '#000']
        });
        $.post('/files/mv_file', 'sfile=' + encodeURIComponent(cutName) + '&dfile=' + encodeURIComponent(path + '/'+fileName), function(rdata) {
            layer.closeAll();
            layer.msg(rdata.msg, {icon: rdata.status ? 1 : 2});
            getFiles(path);
        },'json');
        setCookie('copyFileName', null);
        setCookie('cutFileName', null);
    }
}


//压缩目录
function zip(dirName,submits) {
    if(submits != undefined){
        var sfile = $("#sfile").val();
        var path = $("#path").val();
        var ztype = $('select[name="z_type"]').val();
        var dfile = $("#dfile").val();

        layer.msg('正在压缩,请稍候...', {icon: 16,time: 0,shade: [0.3, '#000']});
        $.post('/files/zip', 'sfile=' + sfile + '&dfile=' + dfile + '&type='+ztype+'&path='+encodeURIComponent(path), function(rdata) {
            layer.closeAll();
            if(rdata == null || rdata == undefined){
                layer.msg('服务器正在后台压缩文件,请稍候刷新文件列表查看进度!',{icon:1});
                getFiles($("#DirPathPlace input").val());
                reloadFiles();
                return;
            }

            showMsg(rdata.msg, function(){
                if(rdata.status) {
                    getFiles($("#DirPathPlace input").val());
                }
            },{icon: rdata.status ? 1 : 2});
        },'json');
        return
    }

    var randStr = getRandomString(6);

    if(dirName.indexOf(',') != -1){
        dirNameArrs = dirName.split(',');
        dirNameArr = dirNameArrs[0].split('/');
        fileName = dirNameArr[dirNameArr.length-1];
        sfile = dirName;
        pathName = dirNameArrs[0].replace('/'+fileName,'');
    } else {
        dirNameArr = dirName.split('/');
        fileName = dirNameArr[dirNameArr.length-1];
        sfile = fileName;
        pathName = dirName.replace('/'+fileName,'');
    }

    var defaultDfile = pathName + '/' + fileName+'_'+randStr+'.tar.gz';

    layer.open({
        type: 1,
        shift: 5,
        closeBtn: 1,
        area: '650px',
        title: '压缩文件['+fileName+']',
        btn: ['确定','取消'],
        content: '<div class="bt-form pd20">'
                    + '<div class="line noborder">'
                    + '<span class="tname">压缩类型</span>\
                        <div class="info-r">\
                            <select class="bt-input-text mr5" name="z_type" style="width:458px;">\
                            <option value="tar_gz" selected>tar.gz (推荐)</option>\
                            <option value="zip">zip (通用格式)</option>\
                            <option value="rar">rar (WinRAR对中文兼容较好)</option>\
                            <option value="7z">7z (压缩率极高的压缩格式)</option>\
                            <option value="xz">xz (压缩率极高的压缩格式)</option>\
                            <option value="bz2">bz2 (压缩率极高的压缩格式)</option>\
                            </select>\
                        </div>\
                    </div>'
                    //
                    + '<div class="line noborder">'
                    + '<input type="text" id="sfile" value="' + sfile + '" style="display:none" />'
                    + '<input type="text" id="path" value="' + pathName + '" style="display:none" />'
                    + '<span class="tname">压缩路径</span>\
                    <input type="text" class="bt-input-text" id="dfile" value="' + defaultDfile + '" placeholder="压缩到" style="width: 75%; display: inline-block; margin: 0px 10px 0px 0px;" />\
                    <span  id="change_dir" class="glyphicon glyphicon-folder-open cursor"></span>'
                    + '</div>'
                +'</div>',
        success:function(){
            $('#change_dir').click(function(){
                changePathCallback('dfile', function(val){
                    var z_type = $('select[name="z_type"]').val();
                    $('#dfile').val(val+'/'+fileName+'_'+randStr+'.'+z_type.replace('_','.'));
                    $('#path').val(val);
                });
            });

            $('select[name="z_type"]').change(function(){
                var z_type = $(this).val();
                var path = $('#path').val();
                var newPathName = path+'/'+fileName+'_'+randStr;
                if (z_type == 'tar_gz') {
                    $("#dfile").val(newPathName + '.tar.gz');
                } else if (z_type == 'zip') {
                    $("#dfile").val(newPathName + '.zip');
                } else if (z_type == 'rar') {
                    $("#dfile").val(newPathName + '.rar');
                } else if (z_type == 'gz') {
                    $("#dfile").val(newPathName + '.gz');
                } else if (z_type == '7z') {
                    $("#dfile").val(newPathName + '.7z');
                } else if (z_type == 'xz') {
                    $("#dfile").val(newPathName + '.xz');
                } else if (z_type == 'bz2') {
                    $("#dfile").val(newPathName + '.tar.bz2');
                }
            });

            $("#dfile").change(function(){
                var dfile = $(this).val();
                $(this).val(dfile.replace(/\/\//g,'/'));
            });
        },
        btn1: function(index){
            zip(dirName,1);
            return false;
        }
    });
    
}
        
//解压目录
function unZip(fileName, type) {
    var path = $("#DirPathPlace input").val();
    if(type.length ==3){
        var sfile = encodeURIComponent($("#sfile").val());
        var dfile = encodeURIComponent($("#dfile").val());
        var coding = $("select[name='coding']").val();
        var tip = layer.msg(lan.files.unzip_the, {icon: 16,time: 0,shade: [0.3, '#000']});
        $.post('/files/unzip', 'sfile=' + sfile + '&dfile=' + dfile +'&type=' + type + '&path='+encodeURIComponent(path), function(rdata) {
            layer.close(tip);
            showMsg(rdata.msg, function(){
                getFiles(path);
            },{icon: rdata.status ? 1 : 2},2000);
        },'json');
        return;
    }
    
    type = (type == 1) ? 'tar':'zip';
    var umpass = '';
    if(type == 'zip'){
        umpass = '<div class="line">\
            <span class="tname">'+lan.files.zip_pass_title+'</span>\
            <input type="text" class="bt-input-text" id="unpass" value="" placeholder="'+lan.files.zip_pass_msg+'" style="width:330px" />\
        </div>';
    }
    layer.open({
        type: 1,
        shift: 5,
        closeBtn: 1,
        area: '490px',
        title: '解压文件',
        content: '<div class="bt-form pd20 pb70">'
            +'<div class="line unzipdiv">'
            +'<span class="tname">'+lan.files.unzip_name+'</span><input type="text" class="bt-input-text" id="sfile" value="' +fileName + '" placeholder="'+lan.files.unzip_name_title+'" style="width:330px" /></div>'
            +'<div class="line"><span class="tname">'+lan.files.unzip_to+'</span><input type="text" class="bt-input-text" id="dfile" value="'+path + '" placeholder="'+lan.files.unzip_to+'" style="width:330px" /></div>' 
            + umpass +'<div class="line"><span class="tname">'+lan.files.unzip_coding+'</span><select class="bt-input-text" name="coding">'
                +'<option value="UTF-8">UTF-8</option>'
                +'<option value="gb18030">GBK</option>'
            +'</select>'
            +'</div>'
            +'<div class="bt-form-submit-btn">'
            +'<button type="button" class="btn btn-danger btn-sm btn-title" onclick="layer.closeAll()">'+lan.public.close+'</button>'
            +'<button type="button" id="ReNameBtn" class="btn btn-success btn-sm btn-title" onclick="unZip(\'' + fileName + '\',\''+type+'\')">'+lan.files.file_menu_unzip+'</button>'
            +'</div>'
        +'</div>'
    });
}

function isCompressFile(fileName){
    var ext = fileName.split('.');
    var extName = ext[ext.length-1].toLowerCase();
    var support = ['zip','gz','tgz','rar','7z','xz','bz2'];
    for (x in support) {
        if (support[x]==extName){
            return true;
        }
    }
    return false;
}

function unCompressFile(fileName, type = 0){
    // 解压文件
    var path = $("#DirPathPlace input").val();
    if(type == 3){
        var sfile = encodeURIComponent($("#sfile").val());
        var dfile = encodeURIComponent($("#dfile").val());
        var coding = $("select[name='coding']").val();
        var tip = layer.msg('正在解压,请稍候...', {icon: 16,time: 0,shade: [0.3, '#000']});
        $.post('/files/uncompress', 'sfile=' + sfile + '&dfile=' + dfile +'&type=' + type + '&path='+encodeURIComponent(path), function(rdata) {
            layer.close(tip);
            showMsg(rdata.msg, function(){
                layer.closeAll();
                getFiles(path);
            },{icon: rdata.status ? 1 : 2},2000);
        },'json');
        return;
    }
    
    // var umpass = '<div class="line">\
    //      <span class="tname">解压密码</span>\
    //      <input type="text" class="bt-input-text" id="unpass" value="" placeholder="不需要请留空" style="width:330px" />\
    //  </div>';
    layer.open({
        type: 1,
        shift: 5,
        closeBtn: 1,
        area: '490px',
        title: '解压文件',
        content: '<div class="bt-form pd20 pb70">\
            <div class="line unzipdiv">\
                <span class="tname">文件名</span>\
                <input type="text" class="bt-input-text" id="sfile" value="' +fileName + '" placeholder="压缩文件名" style="width:330px" />\
            </div>\
            <div class="line">\
                <span class="tname">解压到</span>\
                <input type="text" class="bt-input-text" id="dfile" value="'+path + '" placeholder="解压到" style="width:330px" />\
            </div>\
            <div class="line">\
                <span class="tname">编码</span>\
                <select class="bt-input-text" name="coding">\
                    <option value="UTF-8">UTF-8</option>\
                    <option value="gb18030">GBK</option>\
                </select>\
            </div>\
            <div class="bt-form-submit-btn">\
                <button type="button" class="btn btn-danger btn-sm btn-title" onclick="layer.closeAll()">关闭</button>\
                <button type="button" id="ReNameBtn" class="btn btn-success btn-sm btn-title" onclick="unCompressFile(\'' + fileName + '\',\'3\')">解压</button>\
            </div>\
        </div>'
    });
}

//是否压缩文件
function isZip(fileName){
    var ext = fileName.split('.');
    var extName = ext[ext.length-1].toLowerCase();
    if( extName == 'zip') return 0;
    if( extName == 'gz' || extName == 'tgz') return 1;
    return -1;
}

//是否文本文件
function isText(fileName){
    var exts = ['rar','zip','tar.gz','gz','iso','xsl','doc','xdoc','jpeg',
        'jpg','png','gif','bmp','tiff','exe','so','7z','bz'];
    return isExts(fileName,exts)?false:true;
}

//是否图片文件
function isImage(fileName){
    var exts = ['jpg','jpeg','png','bmp','gif','tiff','ico'];
    return isExts(fileName,exts);
}

//是否为指定扩展名
function isExts(fileName,exts){
    var ext = fileName.split('.');
    if(ext.length < 2) return false;
    var extName = ext[ext.length-1].toLowerCase();
    for(var i=0;i<exts.length;i++){
        if(extName == exts[i]) return true;
    }
    return false;
}

//图片预览
function getImage(fileName){
    var imgUrl = '/files/download?filename='+fileName;
    layer.open({
        type:1,
        offset: '150px',
        closeBtn: 1,
        title:"图片预览",
        area: '400px',
        shadeClose: true,
        content: '<div class="showpicdiv"><img style="max-width:400px;" src="'+imgUrl+'"></div>'
    });
}

//获取文件数据
function getFileBytes(fileName, fileSize){
    window.open('/files/download?filename='+encodeURIComponent(fileName));
}


//上传文件
function uploadFiles(){
    pendingUploadFiles = [];
    showConfirmUpload();
}

//设置权限
function setChmod(action,fileName){
    if(action == 1){
        var chmod = $("#access").val();
        var chown = $("#chown").val();
        var data = 'filename='+ encodeURIComponent(fileName)+'&user='+chown+'&access='+chmod;
        var loadT = layer.msg('正在设置...',{icon:16,time:0,shade: [0.3, '#000']});
        $.post('/files/set_file_access',data,function(rdata){
            layer.close(loadT);
            if(rdata.status) layer.closeAll();
            layer.msg(rdata.msg,{icon:rdata.status?1:2});
            var path = $("#DirPathPlace input").val();
            getFiles(path)
        },'json');
        return;
    }
    
    var toExec = fileName == lan.files.all?'batch(3,1)':'setChmod(1,\''+fileName+'\')';
    $.post('/files/file_access','filename='+encodeURIComponent(fileName),function(rdata){
        // console.log(rdata);
        var sys_users = rdata.sys_users;
        var own_html = '';
        var is_find_own_option = false;
        for (var i = 0; i < sys_users.length; i++) {
            var own = sys_users[i];
            if (rdata.chown==own){
                is_find_own_option = true;
                own_html += '<option value="'+own+'" selected="selected">'+own+'</option>';
            } else {
                own_html += '<option value="'+own+'">'+own+'</option>';
            }
        }
        if (!is_find_own_option){
            own_html += '<option value="'+rdata.chown+'" selected="selected">'+rdata.chown+'</option>';
        }

        layer.open({
            type:1,
            closeBtn: 1,
            title: '设置权限['+fileName+']',
            area: '400px', 
            shadeClose:false,
            content:'<div class="setchmod bt-form ptb15 pb70">\
                        <fieldset>\
                            <legend>所有者</legend>\
                            <p><input type="checkbox" id="owner_r" />读取</p>\
                            <p><input type="checkbox" id="owner_w" />写入</p>\
                            <p><input type="checkbox" id="owner_x" />执行</p>\
                        </fieldset>\
                        <fieldset>\
                            <legend>用户组</legend>\
                            <p><input type="checkbox" id="group_r" />读取</p>\
                            <p><input type="checkbox" id="group_w" />写入</p>\
                            <p><input type="checkbox" id="group_x" />执行</p>\
                        </fieldset>\
                        <fieldset>\
                            <legend>公共</legend>\
                            <p><input type="checkbox" id="public_r" />读取</p>\
                            <p><input type="checkbox" id="public_w" />写入</p>\
                            <p><input type="checkbox" id="public_x" />执行</p>\
                        </fieldset>\
                        <div class="setchmodnum"><input class="bt-input-text" type="text" id="access" maxlength="3" value="'+rdata.chmod+'">权限，\
                        <span>所有者\
                        <select id="chown" class="bt-input-text" style="width:100px;">\
                            '+own_html+'\
                        </select></span></div>\
                        <div class="bt-form-submit-btn">\
                            <button type="button" class="btn btn-danger btn-sm btn-title" onclick="layer.closeAll()">关闭</button>\
                            <button type="button" class="btn btn-success btn-sm btn-title" onclick="'+toExec+'" >确定</button>\
                        </div>\
                    </div>'
        });
        
        onAccess();
        $("#access").keyup(function(){
            onAccess();
        });
        
        $("input[type=checkbox]").change(function(){
            var idName = ['owner','group','public'];
            var onacc = '';
            for(var n=0;n<idName.length;n++){
                var access = 0;
                access += $("#"+idName[n]+"_x").prop('checked')?1:0;
                access += $("#"+idName[n]+"_w").prop('checked')?2:0;
                access += $("#"+idName[n]+"_r").prop('checked')?4:0;
                onacc += access;
            }
            $("#access").val(onacc);
        });

    },'json');
}

function onAccess(){
    var access = $("#access").val();
    var idName = ['owner','group','public'];                
    for(var n=0;n<idName.length;n++){
        $("#"+idName[n]+"_x").prop('checked',false);
        $("#"+idName[n]+"_w").prop('checked',false);
        $("#"+idName[n]+"_r").prop('checked',false);
    }
    for(var i=0;i<access.length;i++){
        var onacc = access.substr(i,1);
        if(i > idName.length) continue;
        if(onacc > 7) $("#access").val(access.substr(0,access.length-1));
        switch(onacc){
            case '1':
                $("#"+idName[i]+"_x").prop('checked',true);
                break;
            case '2':
                $("#"+idName[i]+"_w").prop('checked',true);
                break;
            case '3':
                $("#"+idName[i]+"_x").prop('checked',true);
                $("#"+idName[i]+"_w").prop('checked',true);
                break;
            case '4':
                $("#"+idName[i]+"_r").prop('checked',true);
                break;
            case '5':
                $("#"+idName[i]+"_r").prop('checked',true);
                $("#"+idName[i]+"_x").prop('checked',true);
                break;
            case '6':
                $("#"+idName[i]+"_r").prop('checked',true);
                $("#"+idName[i]+"_w").prop('checked',true);
                break;
            case '7':
                $("#"+idName[i]+"_r").prop('checked',true);
                $("#"+idName[i]+"_w").prop('checked',true);
                $("#"+idName[i]+"_x").prop('checked',true);
                break;
        }
    }
}

function forcePpageRefresh(){
    location.reload(true);
}

//右键菜单
function rightMenuClick(type,path,name){
    // console.log(type,path,name);
    var displayZip = isZip(type);
    var options = {items:[
        {text: "复制", onclick: function() {copyFile(path)}},
        {text: "剪切",    onclick: function() {cutFile(path)}},
        {text: "重命名", onclick: function() {reName(0,name)}},
        {text: lan.files.file_menu_auth, onclick: function() {setChmod(0,path)}},
        {text: lan.files.file_menu_zip, onclick: function() {zip(path)}},
    ]};
    if(type == "dir"){
        options.items.push({text: lan.files.file_menu_del, onclick: function() {
            deleteDir(path)}
        });
    } else if(isText(type)){
        options.items.push({text: lan.files.file_menu_edit, onclick: function() {
            onlineEditFile(0,path);
        }},{text: lan.files.file_menu_down, onclick: function() {
            getFileBytes(path);
        }},{ text: lan.files.file_menu_del, onclick: function() {
            deleteFile(path);
        }});
    } else if(displayZip != -1){
        options.items.push({text: lan.files.file_menu_unzip, onclick: function() {
            unZip(path,displayZip);
        }},{text: lan.files.file_menu_down, onclick: function() {
            getFileBytes(path);
        }},{text: lan.files.file_menu_del, onclick: function() {
            deleteFile(path);
        }});
    } else if(isImage(type)){
        options.items.push({text: lan.files.file_menu_img, onclick: function() {
            getImage(path);
        }},{text: lan.files.file_menu_down, onclick: function() {
            getFileBytes(path);
        }},{text: lan.files.file_menu_del, onclick: function() {
            deleteFile(path);
        }});
    } else {
        options.items.push({text: lan.files.file_menu_down, onclick: function() {
            getFileBytes(path);
        }},{text: lan.files.file_menu_del, onclick: function() {
            deleteFile(path);
        }});
    }

    options.items.push({text: '强制刷新页面', onclick: function() {
        forcePpageRefresh();
    }});
    return options;
}

//右键批量操作
function rightMenuClickAll(e){
    var menu = $("#rmenu");
    var windowWidth = $(window).width(),
        windowHeight = $(window).height(),
        menuWidth = menu.outerWidth(),
        menuHeight = menu.outerHeight(),
        x = (menuWidth + e.clientX < windowWidth) ? e.clientX : windowWidth - menuWidth,
        y = (menuHeight + e.clientY < windowHeight) ? e.clientY : windowHeight - menuHeight;

    menu.css('top', y)
        .css('left', x)
        .css('position', 'fixed')
        .css("z-index","1")
        .show();
}
//取目录大小
function getPathSize(){
    var path = encodeURIComponent($("#DirPathPlace input").val());
    layer.msg("正在计算，请稍候...",{icon:16,time:0,shade: [0.3, '#000']})
    $.post("/files/get_dir_size","path="+path,function(rdata){
        layer.closeAll();
        $("#pathSize").text(rdata.msg);
    },'json');
}

$("body").not(".def-log").click(function(){
    $("#rmenu").hide();
});

//指定路径
$("#DirPathPlace input").keyup(function(e){
    if(e.keyCode == 13) {
        var fpath = $(this).val();
        fpath = filterPath(fpath);
        getFiles(fpath);
    }
});

function pathPlaceBtn(path){
    var html = '';
    var title = '';
    if(path == '/'){
        html = '<li><a title="/">'+lan.files.path_root+'</a></li>';
    } else {
        var dst_path = path.split("/");
        for(var i = 0; i<dst_path.length; i++ ){
            title += dst_path[i]+'/';
            dst_path[0] = lan.files.path_root;
            html += '<li><a title="'+title+'">'+dst_path[i]+'</a></li>';
        }
    }
    
    html = '<div style="width:1200px;height:26px"><ul>'+html+'</ul></div>';
    $("#PathPlaceBtn").html(html);
    $("#PathPlaceBtn ul li a").click(function(e){
        var go_path = $(this).attr("title");
        if(go_path.length>1){
            if(go_path.substr(go_path.length-1,go_path.length) =='/'){
                go_path = go_path.substr(0,go_path.length-1);
            }
        }
        getFiles(go_path);
        e.stopPropagation();
    });
    pathLeft();
}
//计算当前目录偏移
function pathLeft(){
    var UlWidth = $("#PathPlaceBtn ul").width();
    var SpanPathWidth = $("#PathPlaceBtn").width() - 50;
    var Ml = UlWidth - SpanPathWidth;
    if(UlWidth > SpanPathWidth ){
        $("#PathPlaceBtn ul").css("left",-Ml);
    }
    else{
        $("#PathPlaceBtn ul").css("left",0);
    }
}

//路径快捷点击
$("#PathPlaceBtn").on("click", function(e){
    if($("#DirPathPlace").is(":hidden")){
        $("#DirPathPlace").css("display","inline");
        $("#DirPathPlace input").focus();
        $(this).hide();
    }else{
        $("#DirPathPlace").hide();
        $(this).css("display","inline");
    }
    $(document).one("click", function(){
        $("#DirPathPlace").hide();
        $("#PathPlaceBtn").css("display","inline");
    });
    e.stopPropagation(); 
}); 
$("#DirPathPlace").on("click", function(e){
    e.stopPropagation();
});

/**
 * 初始化拖拽上传
 */
var pendingUploadFiles = [];

function initDragDrop() {
    var dropOverlay = document.getElementById('dropOverlay');
    var dragTimer;

    window.addEventListener('dragenter', function(e) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        $(dropOverlay).addClass('active');
    }, true);

    window.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        $(dropOverlay).addClass('active');
    }, true);

    window.addEventListener('dragleave', function(e) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        dragTimer = window.setTimeout(function() {
            $(dropOverlay).removeClass('active');
        }, 100);
    }, true);

    window.addEventListener('drop', function(e) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        $(dropOverlay).removeClass('active');
        if (dragTimer) window.clearTimeout(dragTimer);

        var items = e.dataTransfer.items;
        if (items) {
            handleDroppedItems(items);
        }
    }, true);

    $('#manual_upload_files').change(function(e) {
        handleManualSelect(e.target.files);
        $(this).val('');
    });
    $('#manual_upload_dir').change(function(e) {
        handleManualSelect(e.target.files);
        $(this).val('');
    });
}

function handleManualSelect(files) {
    var filesToUpload = [];
    for (var i = 0; i < files.length; i++) {
        var file = files[i];
        file.fullPath = file.webkitRelativePath || file.name;
        filesToUpload.push(file);
    }
    if (filesToUpload.length > 0) {
        addFilesToPending(filesToUpload);
        showConfirmUpload();
    }
}

/**
 * 将新文件添加到待上传列表，并根据 fullPath 去重
 */
function addFilesToPending(newFiles) {
    var existingPaths = pendingUploadFiles.map(function(f) { return f.fullPath; });
    for (var i = 0; i < newFiles.length; i++) {
        var idx = existingPaths.indexOf(newFiles[i].fullPath);
        if (idx >= 0) {
            // 如果已存在同名文件，覆盖它
            pendingUploadFiles[idx] = newFiles[i];
        } else {
            pendingUploadFiles.push(newFiles[i]);
            existingPaths.push(newFiles[i].fullPath);
        }
    }
}

/**
 * 处理拖拽落下的项
 */
function handleDroppedItems(items) {
    var filesToUpload = [];
    var loadingIndex = layer.msg('正在解析文件结构...', { icon: 16, time: 0, shade: [0.3, '#000'] });

    var promises = [];
    for (var i = 0; i < items.length; i++) {
        var entry = items[i].webkitGetAsEntry();
        if (entry) {
            promises.push(traverseFileTree(entry, filesToUpload));
        }
    }

    Promise.all(promises).then(function() {
        layer.close(loadingIndex);
        if (filesToUpload.length > 0) {
            addFilesToPending(filesToUpload);
            showConfirmUpload();
        } else if (pendingUploadFiles.length === 0) {
            layer.msg('未发现可上传的文件', { icon: 5 });
        }
    });
}

/**
 * 递归遍历目录树
 */
function traverseFileTree(item, filesToUpload, path) {
    path = path || "";
    return new Promise(function(resolve) {
        if (item.isFile) {
            item.file(function(file) {
                file.fullPath = path + file.name;
                filesToUpload.push(file);
                resolve();
            });
        } else if (item.isDirectory) {
            var dirReader = item.createReader();
            var readEntries = function() {
                dirReader.readEntries(function(entries) {
                    if (entries.length > 0) {
                        var subPromises = [];
                        for (var i = 0; i < entries.length; i++) {
                            subPromises.push(traverseFileTree(entries[i], filesToUpload, path + item.name + "/"));
                        }
                        Promise.all(subPromises).then(readEntries);
                    } else {
                        resolve();
                    }
                });
            };
            readEntries();
        } else {
            resolve();
        }
    });
}

/**
 * 显示上传确认对话框
 */
function showConfirmUpload(existMap) {
    var files = pendingUploadFiles;
    var path = $("#DirPathPlace input").val();
    if (path.substring(path.length - 1) != '/') path += '/';
    
    // 若没有传入检测缓存且存在待上传文件，先发起异步批量覆盖检测
    if (!existMap && files.length > 0) {
        var relativePaths = [];
        for (var i = 0; i < files.length; i++) {
            relativePaths.push(files[i].fullPath);
        }
        
        var loadingIndex = layer.msg('正在检测文件覆盖状态...', { icon: 16, time: 0, shade: [0.3, '#000'] });
        $.post('/files/check_exists_files', {
            dfile: path,
            filename: JSON.stringify(relativePaths)
        }, function(rdata) {
            layer.close(loadingIndex);
            var map = {};
            if (rdata && rdata.status && Array.isArray(rdata.data)) {
                for (var j = 0; j < rdata.data.length; j++) {
                    var item = rdata.data[j];
                    map[item.filename] = item;
                }
            }
            showConfirmUpload(map);
        }, 'json').fail(function() {
            layer.close(loadingIndex);
            showConfirmUpload({});
        });
        return;
    }
    
    existMap = existMap || {};
    var fileListHtml = '';
    var totalSize = 0;
    var maxDisplay = 200;
    
    // 双通道提取当前目录下已有的全部文件名列表，实现多重保险检测
    var existFiles = [];
    if (window.currentFiles && Array.isArray(window.currentFiles)) {
        existFiles = [...window.currentFiles];
    }
    // 防御性策略：从当前文件列表 DOM 复选框的 value 中提取文件名
    $("input[name='id']").each(function() {
        var val = $(this).val();
        if (val && existFiles.indexOf(val) < 0) {
            existFiles.push(val);
        }
    });

    for (var i = 0; i < files.length; i++) {
        totalSize += files[i].size;
        if (i < maxDisplay) {
            var fileName = files[i].fullPath;
            // 清洗掉相对路径前缀
            var cleanName = fileName;
            if (fileName.indexOf('/') >= 0) {
                cleanName = fileName.split('/').pop();
            }
            
            // 是否覆盖的判断：高精度路径匹配优先，同级匹配为兜底
            var isOverwrite = false;
            var origFileInfo = null;
            if (existMap.hasOwnProperty(fileName)) {
                isOverwrite = true;
                origFileInfo = existMap[fileName];
            } else if (fileName.indexOf('/') < 0 && (existFiles.indexOf(fileName) >= 0 || existMap.hasOwnProperty(cleanName))) {
                isOverwrite = true;
                origFileInfo = existMap[cleanName];
            }
            
            // 获取原文件大小并展示对比
            var sizeHtml = toSize(files[i].size);
            if (isOverwrite) {
                var sizeBytes = null;
                if (origFileInfo && typeof origFileInfo.size === 'number') {
                    sizeBytes = origFileInfo.size;
                } else if (window.currentFilesMap) {
                    var mapFile = window.currentFilesMap[fileName] || window.currentFilesMap[cleanName];
                    if (mapFile && typeof mapFile.size === 'number') {
                        sizeBytes = mapFile.size;
                    }
                }
                
                if (sizeBytes !== null) {
                    sizeHtml = toSize(sizeBytes) + ' <= ' + toSize(files[i].size);
                }
            }
            
            var overwriteHtml = isOverwrite ? '<span class="overwrite-warn" style="color:#5cb85c;margin-left:10px;">(会覆盖)</span>' : '';
            fileListHtml += '<li>\
                <span class="filename" title="' + fileName + '">' + fileName + '</span>\
                <span class="filesize">' + sizeHtml + '</span>\
                ' + overwriteHtml + '\
                <a class="del_up_file" href="javascript:;" onclick="removeFileFromUpload(' + i + ')">移除</a>\
            </li>';
        }
    }
    
    if (files.length === 0) {
        fileListHtml = '<div style="text-align:center; padding: 50px 0; color: #999;">\
            <div class="glyphicon glyphicon-cloud-upload" style="font-size: 40px; margin-bottom: 15px; opacity: 0.2;"></div>\
            <p>暂无待上传项目</p>\
            <p style="font-size:12px;">请拖拽文件到此处或点击左下角添加</p>\
        </div>';
    } else if (files.length > maxDisplay) {
        fileListHtml += '<li><em style="color: #999;">... 还有 ' + (files.length - maxDisplay) + ' 个项目</em></li>';
    }

    layer.close(window.confirmLayerIndex);
    window.confirmLayerIndex = layer.open({
        type: 1,
        closeBtn: 1,
        title: '确认上传 (' + files.length + ' 个项目)',
        area: '600px',
        shadeClose: false,
        cancel: function(){
            pendingUploadFiles = [];
        },
        content: '<div class="fileUploadDiv confirmUpload">\
                <style>\
                    .confirmUpload .up_box li { padding: 8px 10px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; transition: background-color 0.1s; }\
                    .confirmUpload .up_box li:hover { background-color: #C6F5C9 !important; cursor: pointer; }\
                </style>\
                <div class="upload-target">上传到目录: <code>' + path + '</code></div>\
                <ul id="confirm_up_box" class="up_box">' + fileListHtml + '</ul>\
                <div class="upload-footer">\
                    <div class="footer-left">\
                        <span class="total-info">总大小: ' + toSize(totalSize) + '</span>\
                        <button type="button" class="btn btn-default btn-xs ml10" onclick="showAddMoreMenu(this)" style="color:#20a53a;border-color:#20a53a;padding: 2px 8px;">添加项目 <span class="caret"></span></button>\
                    </div>\
                    <div class="footer-right">\
                        <button type="button" class="btn btn-default btn-sm" onClick="pendingUploadFiles=[];layer.closeAll()">取消</button>\
                        <button type="button" id="confirmUpBtn" class="btn btn-success btn-sm ml10">开始上传</button>\
                    </div>\
                </div>\
            </div>',
        success: function(layero, index) {
            layero.find('#confirmUpBtn').click(function() {
                if (pendingUploadFiles.length === 0) {
                    layer.msg('请先添加要上传的项目', { icon: 0 });
                    return;
                }
                var filesToUpload = [...pendingUploadFiles];
                pendingUploadFiles = [];
                executeUpload(filesToUpload, path);
            });
        }
    });
}

/**
 * 显示添加更多文件的菜单
 */
function showAddMoreMenu(obj) {
    var tips = layer.tips('<div class="add-more-menu">\
        <a href="javascript:;" onclick="$(\'#manual_upload_files\').click(); layer.closeAll(\'tips\')">添加文件</a>\
        <a href="javascript:;" onclick="$(\'#manual_upload_dir\').click(); layer.closeAll(\'tips\')">添加文件夹</a>\
    </div>', obj, {
        tips: [1, '#fff'],
        time: 0,
        shade: 0.1,
        shadeClose: true,
        success: function(layero, index) {
            $(layero).find('.add-more-menu a').css({
                'display': 'block',
                'padding': '8px 15px',
                'color': '#333',
                'text-decoration': 'none',
                'border-bottom': '1px solid #f0f0f0',
                'transition': 'all 0.2s'
            }).hover(function() {
                $(this).css('background-color', '#f5f5f5');
            }, function() {
                $(this).css('background-color', '#fff');
            });
            $(layero).find('.add-more-menu a:last-child').css('border-bottom', 'none');
        }
    });
}

/**
 * 从待上传列表中移除文件
 */
function removeFileFromUpload(index) {
    pendingUploadFiles.splice(index, 1);
    showConfirmUpload();
}

/**
 * 实现带目录结构的上传逻辑
 */
function executeUpload(files, basePath) {
    layer.closeAll();
    layer.open({
        type: 1,
        closeBtn: 0,
        title: '正在上传...',
        area: '500px',
        shadeClose: false,
        content: '<div class="fileUploadDiv">\
                <div id="totalProgress"></div>\
                <ul id="up_box"></ul>\
                <div style="text-align:center; margin-top:10px;"><button class="btn btn-default btn-sm" id="stopUp" style="display:none">停止</button></div>\
            </div>'
    });

    var up_box = document.getElementById("up_box");
    var totalProgress = document.getElementById("totalProgress");
    var ajax = new MyAjax();
    var isStop = false;

    $('#stopUp').show().click(function() {
        isStop = true;
        ajax.stop = true;
        layer.msg('已停止上传');
        setTimeout(function() { layer.closeAll(); getFiles(getCookie("open_dir_path")); }, 1000);
    });

    function uploadNext(index) {
        if (isStop) return;
        if (index >= files.length) {
            layer.msg('全部上传完成', { icon: 1 });
            setTimeout(function() { layer.closeAll(); getFiles(getCookie("open_dir_path")); }, 1000);
            return;
        }

        var file = files[index];
        var parts = file.fullPath.split('/');
        parts.pop();
        var subDir = parts.join('/');
        var targetPath = basePath + (subDir ? subDir + "/" : "");

        var li = document.createElement("li");
        li.innerHTML = "<span class='filename'>" + file.fullPath + "</span><span class='filesize'>" + toSize(file.size) + "</span><em>等待上传...</em>";
        up_box.appendChild(li);
        up_box.scrollTop = up_box.scrollHeight;

        var em = li.getElementsByTagName("em")[0];
        var formData = new FormData();
        formData.append("zunfile", file);

        var url = "/files/upload_file?path=" + encodeURIComponent(targetPath);
        totalProgress.innerHTML = "<p>上传进度: " + (index + 1) + "/" + files.length + "</p><progress value='" + (index + 1) + "' max='" + files.length + "'></progress>";

        ajax.carry({
            url: url,
            data: formData,
            type: "POST",
            async: true,
            progress: function(e) {
                var progress = Math.floor(e.loaded / e.total * 100) + "%";
                em.innerHTML = "上传中: " + progress;
                em.style.color = "#005100";
            },
            success: function(res) {
                em.innerHTML = "已成功";
                em.style.color = "#005100";
                uploadNext(index + 1);
            },
            error: function(err) {
                em.innerHTML = "上传失败";
                em.style.color = "red";
                uploadNext(index + 1);
            }
        });
    }

    uploadNext(0);
}

/**
 * 初始化标签页功能
 */
function initFileTabs() {
    var tabs = loadFileTabs();
    if (tabs.length === 0) {
        var currentPath = getCookie('open_dir_path') || '/www/wwwroot';
        var name = currentPath.replace(/\/$/, '').split('/').pop() || '根目录';
        tabs.push({ name: name, path: currentPath, active: true });
        saveFileTabs(tabs);
    }
    renderFileTabs();
}

/**
 * 从 localStorage 加载标签页
 */
function loadFileTabs() {
    var tabsJson = localStorage.getItem('bt_file_tabs');
    if (tabsJson) {
        try {
            return JSON.parse(tabsJson);
        } catch (e) {
            return [];
        }
    }
    return [];
}

/**
 * 保存标签页到 localStorage
 */
function saveFileTabs(tabs) {
    localStorage.setItem('bt_file_tabs', JSON.stringify(tabs));
}

/**
 * 渲染标签页
 */
function renderFileTabs() {
    var tabs = loadFileTabs();
    var html = '';
    
    for (var i = 0; i < tabs.length; i++) {
        var isActive = tabs[i].active ? 'active' : '';
        html += '<div class="file-tab ' + isActive + '" data-index="' + i + '" onclick="switchFileTab(' + i + ')">\
                    <span class="tab-icon glyphicon glyphicon-folder-open"></span>\
                    <span class="tab-name" title="' + tabs[i].path + '">' + tabs[i].name + '</span>\
                    <span class="close-tab glyphicon glyphicon-remove" onclick="removeFileTab(event, ' + i + ')"></span>\
                </div>';
    }
    
    html += '<button class="add-tab-btn" onclick="addNewFileTab()" title="新建标签页">+</button>';
    
    $('#file-tabs').html(html);
}

/**
 * 更新当前激活标签的路径
 */
function updateActiveTabPath(path) {
    var tabs = loadFileTabs();
    var changed = false;
    for (var i = 0; i < tabs.length; i++) {
        if (tabs[i].active) {
            if (tabs[i].path !== path) {
                tabs[i].path = path;
                tabs[i].name = path.replace(/\/$/, '').split('/').pop() || '根目录';
                changed = true;
            }
            break;
        }
    }
    if (changed) {
        saveFileTabs(tabs);
    }
}

/**
 * 切换标签页
 */
function switchFileTab(index) {
    var tabs = loadFileTabs();
    for (var i = 0; i < tabs.length; i++) {
        tabs[i].active = (i === index);
    }
    saveFileTabs(tabs);
    if (tabs[index]) {
        getFiles(tabs[index].path);
    }
}

/**
 * 新建标签页
 */
function addNewFileTab() {
    var tabs = loadFileTabs();
    for (var i = 0; i < tabs.length; i++) {
        tabs[i].active = false;
    }
    
    var path = getCookie('open_dir_path') || '/www/wwwroot';
    var name = path.replace(/\/$/, '').split('/').pop() || '根目录';
    tabs.push({ name: name, path: path, active: true });
    saveFileTabs(tabs);
    getFiles(path);
}

/**
 * 删除标签页
 */
function removeFileTab(event, index) {
    event.stopPropagation();
    var tabs = loadFileTabs();
    if (tabs.length <= 0) return;
    
    var wasActive = tabs[index].active;
    tabs.splice(index, 1);
    
    if (tabs.length === 0) {
        var path = '/www/wwwroot';
        tabs.push({ name: 'wwwroot', path: path, active: true });
        getFiles(path);
    } else if (wasActive) {
        var newActiveIndex = Math.min(index, tabs.length - 1);
        tabs[newActiveIndex].active = true;
        getFiles(tabs[newActiveIndex].path);
    }
    
    saveFileTabs(tabs);
    renderFileTabs();
}

/**
 * 动态计算目录大小并更新前端显示
 */
function calculateDirSize(event, obj, path) {
    if (event) {
        event.stopPropagation();
    }
    
    // 显示优雅的 loading 动效
    $(obj).html("<img src='/static/img/loading.gif' style='width: 14px; height: 14px; vertical-align: middle; margin-right: 4px;' />计算中...");
    // 移除点击事件，防止重复点击
    $(obj).attr("onclick", "");
    
    $.post('/files/get_dir_size', { path: path }, function(rdata) {
        if (rdata.status) {
            var sizeStr = rdata.msg;
            if (sizeStr) {
                sizeStr = sizeStr.toUpperCase();
                // 格式化单位：如果以 K/M/G/T 结尾，自动加 B；如果是字节数字，也可以合理转换
                if (sizeStr.endsWith('K') || sizeStr.endsWith('M') || sizeStr.endsWith('G') || sizeStr.endsWith('T')) {
                    sizeStr += 'B';
                }
            } else {
                sizeStr = '0B';
            }
            // 完美替换原来的“计算”二字，直接显示具体的容量
            $(obj).parent().html(sizeStr);
        } else {
            // 失败时还原
            $(obj).html("计算");
            $(obj).attr("onclick", "calculateDirSize(event, this, '" + path.replace(/'/g, "\\'") + "')");
            layer.msg(rdata.msg, { icon: 5 });
        }
    }, 'json').fail(function() {
        $(obj).html("计算");
        $(obj).attr("onclick", "calculateDirSize(event, this, '" + path.replace(/'/g, "\\'") + "')");
        layer.msg("获取目录大小失败", { icon: 5 });
    });
}

