
// ============================================
// 动态资源加载器（按需加载 JS/CSS，带缓存防重复）
// ============================================
var _loadedResources = {};

/**
 * 动态加载单个 JS 文件，返回 Promise
 * @param {string} url - JS 文件 URL
 * @returns {Promise}
 */
function loadScript(url) {
    if (_loadedResources[url]) return _loadedResources[url];
    _loadedResources[url] = new Promise(function(resolve, reject) {
        var s = document.createElement('script');
        s.src = url;
        s.onload = resolve;
        s.onerror = function() {
            delete _loadedResources[url];
            reject(new Error('Failed to load: ' + url));
        };
        document.head.appendChild(s);
    });
    return _loadedResources[url];
}

/**
 * 动态加载单个 CSS 文件，返回 Promise
 * @param {string} url - CSS 文件 URL
 * @returns {Promise}
 */
function loadCSS(url) {
    if (_loadedResources[url]) return _loadedResources[url];
    _loadedResources[url] = new Promise(function(resolve, reject) {
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = url;
        link.onload = resolve;
        link.onerror = function() {
            delete _loadedResources[url];
            reject(new Error('Failed to load: ' + url));
        };
        document.head.appendChild(link);
    });
    return _loadedResources[url];
}

/**
 * 批量加载多个资源，返回 Promise
 * @param {Array} urls - [{type:'js'|'css', url:'...'}]
 * @returns {Promise}
 */
function loadResources(urls) {
    var promises = [];
    for (var i = 0; i < urls.length; i++) {
        if (urls[i].type === 'css') {
            promises.push(loadCSS(urls[i].url));
        } else {
            promises.push(loadScript(urls[i].url));
        }
    }
    return Promise.all(promises);
}

/**
 * 获取带版本号的静态资源URL（从页面已有 script 标签提取版本号用于缓存控制）
 */
var _staticVersion = '';
(function() {
    var scripts = document.querySelectorAll('script[src*="v="]');
    for (var i = 0; i < scripts.length; i++) {
        var match = scripts[i].src.match(/[?&]v=([^&]+)/);
        if (match) { _staticVersion = match[1]; break; }
    }
})();
function staticUrl(path) {
    var sep = path.indexOf('?') > -1 ? '&' : '?';
    return path + (_staticVersion ? sep + 'v=' + _staticVersion : '');
}

// WebSSH 终端资源按需加载（约 510KB，仅在打开终端时才加载）
var _webshellReady = null;
function loadWebShellResources() {
    if (_webshellReady) return _webshellReady;
    _webshellReady = loadResources([
        {type: 'css', url: staticUrl('/static/build/xterm.css')},
        {type: 'css', url: staticUrl('/static/build/addons/fullscreen/fullscreen.css')},
        {type: 'js',  url: staticUrl('/static/build/xterm.js')},
        {type: 'js',  url: staticUrl('/static/js/socket.io.min.js')}
    ]).then(function() {
        return loadResources([
            {type: 'js', url: staticUrl('/static/build/addons/attach/attach.js')},
            {type: 'js', url: staticUrl('/static/build/addons/fit/fit.js')},
            {type: 'js', url: staticUrl('/static/build/addons/fullscreen/fullscreen.js')},
            {type: 'js', url: staticUrl('/static/build/addons/winptyCompat/winptyCompat.js')},
            {type: 'js', url: staticUrl('/static/js/term-websocketio.js')}
        ]);
    });
    return _webshellReady;
}

$(function() {
	$(".sub-menu a.sub-menu-a").on('click', function() {
		$(this).next(".sub").slideToggle("slow").siblings(".sub").filter(":visible").slideUp("slow");
	});

	// 事件委托：选择目录弹窗中的文件夹点击
	$(document).on('click', '#tbody td.folder-link', function() {
		var path = $(this).attr('data-path');
		getDiskList(path);
	});

	// 事件委托：选择目录弹窗中的删除文件夹
	$(document).on('click', '#tbody .delfile-btn', function() {
		var path = $(this).attr('data-path');
		newDelFile(path);
	});

	// 事件委托：新建文件夹确定按钮
	$(document).on('click', '#tbody .nameOk', function() {
		var c = $("#newFolderName").val();
		var b = $("#PathPlace").find("span").text();
		var newTxt = b.replace(new RegExp(/(\/\/)/g), "/") + c;
		var d = "path=" + newTxt;
		$.post("/files/create_dir", d, function(e) {
			if(e.status == true) {
				layer.msg(e.msg, {
					icon: 1
				});
			} else {
				layer.msg(e.msg, {
					icon: 2
				});
			}
			getDiskList(b);
		},'json');
	});

	// 事件委托：新建文件夹取消按钮
	$(document).on('click', '#tbody .nameNOk', function() {
		$(this).parents("tr").remove();
	});
});

function toSize(a) {
	var d = [" B", " KB", " MB", " GB", " TB", " PB"];
	var e = 1024;
	for(var b = 0; b < d.length; b++) {
		if(a < e) {
			return(b == 0 ? a : a.toFixed(2)) + d[b]
		}
		a /= e;
	}
}

function toSizePos(a, pos = 0) {
	var d = [" B", " KB", " MB", " GB", " TB", " PB"];
	var e = 1024;
	var r = {};
	for(var b = 0; b < d.length; b++) {
		if (pos > 0){
			if (b == pos){
				r['name'] = (b == 0 ? a : a.toFixed(2)) + d[b];
				r['pos'] = b;
				return r
			}
		} else {
			if( a < e) {
				r['name'] = (b == 0 ? a : a.toFixed(2)) + d[b];
				r['pos'] = b;
				return r
			}
		}
		a /= e;
	}
}

function toSizeMB(a) {
	var d = [" KB", " MB"];
	var e = 1024;
	var i = 0;
	for(var b = 0; b < d.length; b++) {
		a /= e;
		i = b;
	}
	return a.toFixed(2) + d[i]
}

function toTrim(x) {
    return x.replace(/^\s+|\s+$/gm,'');
}

function inArray(f, arr){
	for (var i = 0; i < arr.length; i++) {
		if (f == arr[i]) {
			return true;
		}
	}
	return false;
}

//表格头固定
// 修复：原来使用 transform: translateY() 实现表头固定，
// 但 CSS transform 会创建新的层叠上下文，导致 layer 弹窗的
// position:fixed 定位基准变为该元素而非视口，弹窗跑到页面底部。
// 改用 position: sticky 实现，不影响 fixed 定位。
function tableFixed(name) {
    var tableName = document.querySelector('#' + name);
    $(tableName).find('thead tr th').css({
        'position': 'sticky',
        'top': '0',
        'z-index': '1'
    });
}

function escapeHTML(a){
    a = "" + a;
    return a.replace(/&/g, "&amp;").replace(/</g, "&lt;").
    replace(/>/g, "&gt;").replace(/"/g, '&quot;').
    replace(/'/g,"&#x27;").replace(/\(/g,"&#40;").replace(/\&&#60;/g,"&lt;").
    replace(/\&&#62;/g,"&gt;").replace(/`/g,"&#96;").replace(/=/g,"＝");
}

// scrollHandle 已废弃，保留空函数以防外部调用（不再对 thead 施加 transform）
function scrollHandle(e) {
    // 原来: $(this).find("thead").css({ "transform": "translateY(" + scrollTop + "px)", ... });
    // transform 会破坏 position:fixed 弹窗定位，已改用 sticky 方案
}


//转换单们到MB
function toSizeM(byteLen) {
    var a = parseInt(byteLen) / 1024 / 1024;
    return a || 0;
}

//字节单位转换MB
function toSizeG(bytes){
	var c = 1024 * 1024;
	var b = 0;
	if(bytes > 0){
		var b = (bytes/c).toFixed(2);
	}
	return b;
}

//to unixtime
function toUnixTime(txt){
        var unix = new Date(Date.parse(txt.replace(/-/g,'/'))).getTime();
        return unix/1000;
    }

function randomStrPwd(b) {
	b = b || 32;
	// &!@%
	var c = "AaBbCcDdEeFfGHhiJjKkLMmNnPpRSrTsWtXwYxZyz2345678";
	var a = c.length;
	var d = "";
	for(i = 0; i < b; i++) {
		d += c.charAt(Math.floor(Math.random() * a))
	}
	return d
}

function getRandomString(len) {
	len = len || 32;
	var chars = 'ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678'; // 默认去掉了容易混淆的字符oOLl,9gq,Vv,Uu,I1  
	var maxPos = chars.length;
	var pwd = '';
	for (i = 0; i < len; i++) {
		pwd += chars.charAt(Math.floor(Math.random() * maxPos));
	}
	return pwd;
}

//验证IP地址
function isValidIP(ip) {
    var reg = /^(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\.(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\.(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\.(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])$/
    return reg.test(ip);
}

function isContains(str, substr) {
    return str.indexOf(substr) >= 0;
}


function filterPath(path){
	var path_arr = path.split('/');
	var path_new = [];
	for (var i = 0; i < path_arr.length; i++) {
		if (path_arr[i]!=''){
			path_new.push(path_arr[i]);
		}
	}
	var rdata = "/"+path_new.join('/');
	return rdata;
}

function msgTpl(msg, args){
	if (typeof args == 'string'){
		return msg.replace('{1}', args);
	} else if (typeof args == 'object'){
		for (var i = 0; i < args.length; i++) {
			rep = '{' + (i + 1) + '}';
			msg = msg.replace(rep, args[i]);
		}	
	}
	return msg;
}

function refresh() {
	window.location.reload()
}

function mwsPost(path, args, callback){
	$.post(path, args, function(rdata){
		if(typeof(callback) == 'function'){
			callback(rdata);
		}
	},'json');
}

async function syncPost(path, args) {
	try {
		return await $.ajax({
			type: 'post',
			url: path,
			data: args,
			dataType: 'json'
		});
	} catch (e) {
		console.error("syncPost error:", e);
		return null;
	}
}

function repeatPwd(a) {
	$("#MyPassword").val(randomStrPwd(a))
}

$(".menu-icon").on('click', function() {
	$(".sidebar-scroll").toggleClass("sidebar-close");
	$(".main-content").toggleClass("main-content-open");
	if($(".sidebar-close")) {
		$(".sub-menu").find(".sub").css("display", "none");
	}
});

var Upload, percentage;
Date.prototype.format = function(b) {
	var c = {
		"M+": this.getMonth() + 1,
		"d+": this.getDate(),
		"h+": this.getHours(),
		"m+": this.getMinutes(),
		"s+": this.getSeconds(),
		"q+": Math.floor((this.getMonth() + 3) / 3),
		S: this.getMilliseconds()
	};
	if(/(y+)/.test(b)) {
		b = b.replace(RegExp.$1, (this.getFullYear() + "").substr(4 - RegExp.$1.length))
	}
	for(var a in c) {
		if(new RegExp("(" + a + ")").test(b)) {
			b = b.replace(RegExp.$1, RegExp.$1.length == 1 ? c[a] : ("00" + c[a]).substr(("" + c[a]).length))
		}
	}
	return b
};

function getLocalTime(a) {
	a = a.toString();
	if(a.length > 10) {
		a = a.substring(0, 10)
	}
	return new Date(parseInt(a) * 1000).format("yyyy/MM/dd hh:mm:ss")
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

function getFormatTime(tm, format) {
	if (format == undefined) format = "yyyy/MM/dd hh:mm:ss";
	tm = tm.toString();
	if (tm.length > 10) {
	  tm = tm.substring(0, 10);
	}
	var data = new Date(parseInt(tm) * 1000);
	var o = {
	  "M+": data.getMonth() + 1, //month
	  "d+": data.getDate(), //day
	  "h+": data.getHours(), //hour
	  "m+": data.getMinutes(), //minute
	  "s+": data.getSeconds(), //second
	  "q+": Math.floor((data.getMonth() + 3) / 3), //quarter
	  "S": data.getMilliseconds() //millisecond
	}
	if (/(y+)/.test(format)) format = format.replace(RegExp.$1,
	    (data.getFullYear() + "").substr(4 - RegExp.$1.length));
	for (var k in o)
	  if (new RegExp("(" + k + ")").test(format))
	    format = format.replace(RegExp.$1,RegExp.$1.length == 1 ? o[k] : ("00" + o[k]).substr(("" + o[k]).length));
	return format;
}



function changePathCallback(default_dir, callback) {
	var c = layer.open({
		type: 1,
		area: "650px",
		title: '选择目录',
		closeBtn: 1,
		shift: 5,
		shadeClose: false,
		content: "<div class='changepath'>\
			<div class='path-top'>\
				<button type='button' class='btn btn-default btn-sm' onclick='backFile()'>\
					<span class='glyphicon glyphicon-share-alt'></span>返回\
				</button>\
				<div class='place' id='PathPlace'>当前路径：<span></span></div>\
			</div>\
			<div class='path-con'>\
				<div class='path-con-left'>\
					<dl><dt id='changecomlist' onclick='backMyComputer()'>计算机</dt></dl>\
				</div>\
				<div class='path-con-right'>\
					<ul class='default' id='computerDefautl'></ul>\
					<div class='file-list divtable'>\
						<table class='table table-hover' style='border:0 none'>\
							<thead>\
								<tr class='file-list-head'>\
									<th width='40%'>文件名</th>\
									<th width='20%'>修改时间</th>\
									<th width='10%'>权限</th>\
									<th width='10%'>所有者</th>\
									<th width='10%'></th>\
								</tr>\
							</thead>\
							<tbody id='tbody' class='list-list'></tbody>\
						</table>\
					</div>\
				</div>\
			</div>\
		</div>\
		<div class='getfile-btn' style='margin-top:0'>\
			<button type='button' class='btn btn-default btn-sm pull-left' onclick='createFolder()'>新建文件夹</button>\
			<button type='button' class='btn btn-danger btn-sm mr5 btn-close'>关闭</button>\
			<button type='button' class='btn btn-success btn-sm btn-choose'>选择</button>\
		</div>",
		success:function(layero,layer_index){
			$('.btn-close').on('click', function(){
				layer.close(layer_index);
			});

			$('.btn-choose').on('click', function(){
				var a = $("#PathPlace").find("span").text();
				a = a.replace(new RegExp(/(\\)/g), "/");
				a_len = a.length;
				if (a[a_len-1] == '/'){
					a = a.substr(0,a_len-1);
				}
				callback(a);
				layer.close(layer_index);
			});
		}
	});
	getDiskList(default_dir);
	activeDisk();
}

function changePath(d) {
	setCookie('SetId', d);
	setCookie('SetName', '');
	var c = layer.open({
		type: 1,
		area: "650px",
		title: '选择目录',
		closeBtn: 1,
		shift: 5,
		shadeClose: false,
		content: "<div class='changepath'>\
			<div class='path-top'>\
				<button type='button' class='btn btn-default btn-sm' onclick='backFile()'><span class='glyphicon glyphicon-share-alt'></span>返回</button>\
				<div class='place' id='PathPlace'>当前路径：<span></span></div>\
			</div>\
			<div class='path-con'>\
				<div class='path-con-left'><dl><dt id='changecomlist' onclick='backMyComputer()'>计算机</dt></dl></div>\
				<div class='path-con-right'>\
					<ul class='default' id='computerDefautl'></ul>\
					<div class='file-list divtable'>\
						<table class='table table-hover' style='border:0 none'>\
							<thead>\
								<tr class='file-list-head'>\
									<th width='40%'>文件名</th>\
									<th width='20%'>修改时间</th>\
									<th width='10%'>权限</th>\
									<th width='10%'>所有者</th>\
									<th width='10%'></th>\
								</tr>\
							</thead>\
							<tbody id='tbody' class='list-list'></tbody>\
						</table>\
					</div>\
				</div>\
			</div>\
		</div>\
		<div class='getfile-btn' style='margin-top:0'>\
			<button type='button' class='btn btn-default btn-sm pull-left' onclick='createFolder()'>新建文件夹</button>\
			<button type='button' class='btn btn-danger btn-sm mr5' onclick=\"layer.close(getCookie('changePath'))\">关闭</button>\
			<button type='button' class='btn btn-success btn-sm' onclick='getfilePath()'>选择</button>\
		</div>"
	});
	setCookie("changePath", c);
	var b = $("#" + d).val();
	tmp = b.split(".");
	if(tmp[tmp.length - 1] == "gz") {
		tmp = b.split("/");
		b = "";
		for(var a = 0; a < tmp.length - 1; a++) {
			b += "/" + tmp[a]
		}
		setCookie("SetName", tmp[tmp.length - 1])
	}
	b = b.replace(/\/\//g, "/");
	getDiskList(b);
	activeDisk();
}

function getDiskList(b) {
	var d = "";
	var a = "";
	var c = "path=" + b + "&disk=True&row=1000";
	$.post("/files/get_dir", c, function(h) {
		// console.log(h);
		// if(h.dir != undefined) {
		// 	for(var f = 0; f < h.dir.length; f++) {
		// 		a += "<dd onclick=\"getDiskList('" + h.dir[f].path + "')\"><span class='glyphicon glyphicon-hdd'></span>&nbsp;" + h.dir[f].path + "</dd>";
		// 	}
		// 	$("#changecomlist").html(a);
		// }
		for(var f = 0; f < h.dir.length; f++) {
			var g = h.dir[f].split(";");
			var e = g[0];
		
			if(isChineseChar(e)) {
				if(e.length > 10) {
					e = e.substring(0, 10) + "...";
				}
			} else{
				if(e.length > 20) {
					e = e.substring(0, 20) + "...";
				}
			}

			d += "<tr>\
				<td class='folder-link' data-path='" + h.path + "/" + g[0] + "' title='" + g[0] + "'>\
					<span class='glyphicon glyphicon-folder-open'></span>" + e + "</td><td>" + getMatchTime(g[2]) + "</td>\
				<td>" + g[3] + "</td>\
				<td>" + g[4] + "</td>\
				<td><span class='delfile-btn' data-path='" + h.path + "/" + g[0] + "'>X</span></td>\
			</tr>";
		}
		if(h.files != null && h.files != "") {
			for(var f = 0; f < h.files.length; f++) {
				var g = h.files[f].split(";");
				var e = g[0];
				if(isChineseChar(e)) {
					if(e.length > 10) {
						e = e.substring(0, 10) + "..."
					}
				} else{
					if(e.length > 20) {
						e = e.substring(0, 20) + "..."
					}
				}

				d += "<tr>\
					<td title='" + g[0] + "'><span class='glyphicon glyphicon-file'></span>" + e + "</td>\
					<td>" + getMatchTime(g[2]) + "</td>\
					<td>" + g[3] + "</td>\
					<td>" + g[4] + "</td>\
					<td></td>\
				</tr>";
			}
		}
		$(".default").hide();
		$(".file-list").show();
		$("#tbody").html(d);
		if(h.path.substr(h.path.length - 1, 1) != "/") {
			h.path += "/";
		}
		$("#PathPlace").find("span").html(h.path);
		activeDisk();
		return;
	},'json');
}

function createFolder() {
	var a = "<tr>\
		<td colspan='2'><span class='glyphicon glyphicon-folder-open'></span><input id='newFolderName' class='newFolderName' type='text' value=''></td>\
		<td colspan='3'><button id='nameOk' type='button' class='btn btn-success btn-sm nameOk'>确定</button>\
			&nbsp;&nbsp;<button id='nameNOk' type='button' class='btn btn-default btn-sm nameNOk'>取消</button></td>\
		</tr>";
	if($("#tbody tr").length == 0) {
		$("#tbody").append(a)
	} else {
		$("#tbody tr:first-child").before(a)
	}
	$(".newFolderName").trigger('focus');
}

function newDelFile(c) {
	var a = $("#PathPlace").find("span").text();
	newTxt = c.replace(new RegExp(/(\/\/)/g), "/");
	var b = "path=" + newTxt + "&empty=True";
	$.post("/files/delete_dir", b, function(d) {
		if(d.status == true) {
			layer.msg(d.msg, {
				icon: 1
			})
		} else {
			layer.msg(d.msg, {
				icon: 2
			})
		}
		getDiskList(a);
	},'json');
}

function activeDisk() {
	var a = $("#PathPlace").find("span").text().substring(0, 1);
	switch(a) {
		case "C":
			$(".path-con-left dd:nth-of-type(1)").css("background", "#eee").siblings().removeAttr("style");
			break;
		case "D":
			$(".path-con-left dd:nth-of-type(2)").css("background", "#eee").siblings().removeAttr("style");
			break;
		case "E":
			$(".path-con-left dd:nth-of-type(3)").css("background", "#eee").siblings().removeAttr("style");
			break;
		case "F":
			$(".path-con-left dd:nth-of-type(4)").css("background", "#eee").siblings().removeAttr("style");
			break;
		case "G":
			$(".path-con-left dd:nth-of-type(5)").css("background", "#eee").siblings().removeAttr("style");
			break;
		case "H":
			$(".path-con-left dd:nth-of-type(6)").css("background", "#eee").siblings().removeAttr("style");
			break;
		default:
			$(".path-con-left dd").removeAttr("style")
	}
}

function backMyComputer() {
	// $(".default").show();
	// $(".file-list").hide();
	// $("#PathPlace").find("span").html("");
	// activeDisk();
	return;
}

function backFile() {
	var c = $("#PathPlace").find("span").text();
	if(c.substr(c.length - 1, 1) == "/") {
		c = c.substr(0, c.length - 1)
	}
	var d = c.split("/");
	var a = "";
	if(d.length > 1) {
		var e = d.length - 1;
		for(var b = 0; b < e; b++) {
			a += d[b] + "/"
		}
		getDiskList(a.replace("//", "/"))
	} else {
		a = d[0]
	}
	if(d.length == 1) {}
}

function getfilePath() {
	var a = $("#PathPlace").find("span").text();
	a = a.replace(new RegExp(/(\\)/g), "/");
	a_len = a.length;
	if (a[a_len-1] == '/'){
		a = a.substr(0,a_len-1);
	}

	$("#" + getCookie("SetId")).val(a + getCookie("SetName"));
	layer.close(getCookie("changePath"));
	return a;
}

function setCookie(a, c) {
	var b = 30;
	var d = new Date();
	d.setTime(d.getTime() + b * 24 * 60 * 60 * 1000);
	document.cookie = a + "=" + escape(c) + ";path=/;expires=" + d.toGMTString();
}

function getCookie(b) {
	var a, c = new RegExp("(^| )" + b + "=([^;]*)(;|$)");
	if(a = document.cookie.match(c)) {
		return unescape(a[2])
	} else {
		return null
	}
}

function autoHeight() {
	var a = $("body").height() - 40;
	$(".main-content").css("min-height", a);
}

function showMsg(msg, callback ,icon, time){

	if (typeof time == 'undefined'){
		time = 2000;
	}

	if (typeof icon == 'undefined'){
		icon = {};
	}

	var loadT = layer.msg(msg, icon);
	setTimeout(function() {
		layer.close(loadT);
		if (typeof callback == 'function'){
			callback();
		}
	}, time);
}

function openPath(a) {
	setCookie("open_dir_path", a);
	window.location.href = "/files/index";
}

function onlineEditFile(k, f, callback) {
	if(k != 0) {
		var l = $("#PathPlace input").val();
		var h = encodeURIComponent($("#textBody").val());
		var a = $("select[name=encoding]").val();
		var loadT = layer.msg('正在保存,请稍候...', {icon: 16,time: 0});
		$.post("/files/save_body", "data=" + h + "&path=" + encodeURIComponent(f) + "&encoding=" + a, function(data) {
			if(k == 1) {
				layer.close(loadT);
			}
			layer.msg(data.msg, {icon: data.status ? 1 : 2});
			if (data.status && typeof(callback) == 'function'){
				callback(k, f);
			}
		},'json');
		return
	}
	
	var g = f.split(".");
	var b = g[g.length - 1];
	var d;
	switch(b) {
		case "html":
			var j = {
				name: "htmlmixed",
				scriptTypes: [{
					matches: /\/x-handlebars-template|\/x-mustache/i,
					mode: null
				}, {
					matches: /(text|application)\/(x-)?vb(a|script)/i,
					mode: "vbscript"
				}]
			};
			d = j;
			break;
		case "htm":
			var j = {
				name: "htmlmixed",
				scriptTypes: [{
					matches: /\/x-handlebars-template|\/x-mustache/i,
					mode: null
				}, {
					matches: /(text|application)\/(x-)?vb(a|script)/i,
					mode: "vbscript"
				}]
			};
			d = j;
			break;
		case "js":
			d = "text/javascript";
			break;
		case "json":
			d = "application/ld+json";
			break;
		case "css":
			d = "text/css";
			break;
		case "php":
			d = "application/x-httpd-php";
			break;
		case "tpl":
			d = "application/x-httpd-php";
			break;
		case "xml":
			d = "application/xml";
			break;
		case "sql":
			d = "text/x-sql";
			break;
		case "conf":
			d = "text/x-nginx-conf";
			break;
		case "py":
			d = "text/x-python";
			break;
		case "sh":
		case "bash":
			d = "text/x-sh";
			break;
		case "md":
			d = "text/x-markdown";
			break;
		case "yaml":
		case "yml":
			d = "text/x-yaml";
			break;
		case "ini":
			d = "text/x-ini";
			break;
		default:
			var j = {
				name: "htmlmixed",
				scriptTypes: [
					{matches: /\/x-handlebars-template|\/x-mustache/i,mode: null}, 
					{matches: /(text|application)\/(x-)?vb(a|script)/i,mode: "vbscript"}
				]
			};
			d = j;
	}

	

	var codding = ["utf-8", "GBK", "GB2312", "BIG5"];
	var code_mirror = null;
	var code_timer = null;

	function getBody(callback){
		$.post("/files/get_body", "path=" + encodeURIComponent(f), function(rdata) {
			if (typeof(callback) == 'function'){
				callback(rdata);
			}
		},'json');
	}

	
	function renderBody(callback){
		getBody(function(rdata){
			if(rdata.status === false){
				layer.close(r);
				layer.msg(rdata.msg,{icon:5});
				return;
			}

			if (typeof(callback) == 'function'){
				callback(rdata);
			}
			
			var coding_html = "";
			for(var p = 0; p < codding.length; p++) {
				var coding_selected = rdata.data.encoding == codding[p] ? "selected" : "";
				coding_html += '<option value="' + codding[p] + '" ' + coding_selected + ">" + codding[p] + "</option>";
			}

			$("select[name=encoding]").html(coding_html);
		});
	}

	var r = layer.open({
		type: 1,
		shift: 5,
		closeBtn: 1,
		area: ["90%", "90%"],
		btn:['<span class="glyphicon glyphicon-floppy-disk"></span> 保存', '<span class="glyphicon glyphicon-refresh"></span> 刷新'],
		title: "在线编辑[" + f + "]",
		shade: 0.0000001,
		content: '<form class="bt-form pd20">\
			<div class="line">\
				<p style="color:red;margin-bottom:10px">提示：Ctrl+F 搜索关键字，Ctrl+G 查找下一个，Ctrl+S 保存，Ctrl+H 查找替换!\
					<select class="bt-input-text" name="encoding" style="width: 74px;position: absolute;top: 31px;right: 19px;height: 22px;z-index: 9999;border-radius: 0;"><option value="utf-8" selected>utf-8</option></select>\
				</p>\
				<textarea class="mCustomScrollbar bt-input-text" id="textBody" style="width:100%;margin:0 auto;line-height: 1.8;position: relative;top: 10px;"></textarea>\
			</div>\
		</form>',
		success:function(layero){
			$(layero).hide();
			var layer_id = $(layero).attr('id').replace("layui-layer","");
			var loading = layer.msg('正在读取文件,请稍候...', {icon: 16,time: 0});
			renderBody(function(rdata){
				$('#layui-layer-shade'+layer_id).css('opacity',0.3);
				$(layero).show();
				layer.close(loading);
				

				$("#textBody").text(rdata.data.data);
				var q = $(window).height() * 0.9;
				$("#textBody").height(q - 190);

				code_mirror = CodeMirror.fromTextArea(document.getElementById("textBody"), {
					extraKeys: {
						"Ctrl-F": function(cm){ showAdvancedSearchDialog(cm, false); },
						"Ctrl-H": function(cm){ showAdvancedSearchDialog(cm, true); },
						"Ctrl-/": "toggleComment",
						"Ctrl-S": function() {
							$("#textBody").text(code_mirror.getValue());
							onlineEditFile(2, f, callback);
						},
						"Cmd-S":function() {
							$("#textBody").text(code_mirror.getValue());
							onlineEditFile(2, f, callback);
						},
					},
					mode: d,
					lineNumbers: true,
					matchBrackets: true,
					matchtags: true,
					autoMatchParens: true
				});
				code_mirror.focus();
				code_mirror.setSize("auto", q - 180);

				$(window).on('resize', function(){
	                var q = $(window).height() * 0.9;
	                code_mirror.setSize("auto", q - 180);
	            });
				
				// 自动刷新滑块
				var toggleHtml = '<div class="auto-refresh-toggle" style="position: absolute; bottom: 12px; left: 15px; display: flex; align-items: center; height: 28px; padding: 0 12px; border-radius: 14px; cursor: pointer; user-select: none; transition: all 0.3s; background: transparent; z-index: 10000;">\
					<div class="toggle-track" style="width: 36px; height: 18px; border: 1px solid #ccc; border-radius: 10px; position: relative; margin-right: 8px; transition: all 0.3s; background: #fff;">\
						<div class="toggle-thumb" style="width: 14px; height: 14px; border: 1px solid #ccc; background: #fff; border-radius: 50%; position: absolute; top: 1px; right: 2px; transition: all 0.3s;"></div>\
					</div>\
					<span class="toggle-text" style="color: #999; font-size: 14px; transition: all 0.3s;">自动刷新</span>\
				</div>';
				layero.append(toggleHtml);
				
				layero.find('.auto-refresh-toggle').on('click', function() {
					var $track = $(this).find('.toggle-track');
					var $thumb = $(this).find('.toggle-thumb');
					var $text = $(this).find('.toggle-text');
					var isActive = $(this).hasClass('active');
					
					if (isActive) {
						// 关闭自动刷新
						$(this).removeClass('active');
						$(this).css('background', 'transparent');
						$track.css({'border-color': '#ccc', 'background': '#fff'});
						$thumb.css({'border-color': '#ccc', 'right': '2px', 'background': '#fff'});
						$text.css('color', '#999');
						clearInterval(code_timer);
					} else {
						// 开启自动刷新
						$(this).addClass('active');
						$(this).css('background', '#5FB878');
						$track.css({'border-color': '#fff', 'background': 'transparent'});
						$thumb.css({'border-color': '#fff', 'right': '18px', 'background': '#fff'});
						$text.css('color', '#fff');
						
						code_timer = setInterval(function(){
							renderBody(function(rdata){
								code_mirror.setValue(rdata.data.data);
								var scrollInfo = code_mirror.getScrollInfo();
								code_mirror.scrollTo(null, scrollInfo.height);
							});
						}, 5000);
					}
				});
				
				// 调整刷新按钮的背景色，并增加两个按钮之间的间距
				layero.find('.layui-layer-btn1').css({
					'background-color': '#7488bf',
					'border-color': '#7488bf',
					'color': '#fff',
					'margin-right': '15px'
				});
			});
		},
		end:function(){
			clearInterval(code_timer);
		},
		yes:function(){
			$("#textBody").text(code_mirror.getValue());
			onlineEditFile(1, f, callback);
		},
		btn2:function(){
			var loading_refresh = layer.msg('正在刷新中,请稍候...', {icon: 16,time: 0});
			renderBody(function(rdata){
				layer.close(loading_refresh);
				code_mirror.setValue(rdata.data.data);
			});
			return false;
		}
	});
	
}

function divcenter() {
	$(".layui-layer").css("position", "absolute");
	var c = $(window).width();
	var b = $(".layui-layer").outerWidth();
	var g = $(window).height();
	var f = $(".layui-layer").outerHeight();
	var a = (c - b) / 2;
	var e = (g - f) / 2 > 0 ? (g - f) / 2 : 10;
	var d = $(".layui-layer").offset().left - $(".layui-layer").position().left;
	var h = $(".layui-layer").offset().top - $(".layui-layer").position().top;
	a = a + $(window).scrollLeft() - d;
	e = e + $(window).scrollTop() - h;
	$(".layui-layer").css("left", a + "px");
	$(".layui-layer").css("top", e + "px")
}

function copyText(value) {
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(value).then(function() {
            layer.msg('复制成功',{icon:1,time:2000});
        }).catch(function() {
            layer.msg('复制失败，浏览器不兼容!',{icon:2,time:2000});
        });
    } else {
        var textArea = document.createElement("textarea");
        textArea.value = value;
        textArea.style.top = "0";
        textArea.style.left = "0";
        textArea.style.position = "fixed";
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        try {
            var successful = document.execCommand('copy');
            if (successful) {
                layer.msg('复制成功',{icon:1,time:2000});
            } else {
                layer.msg('复制失败，浏览器不兼容!',{icon:2,time:2000});
            }
        } catch (err) {
            layer.msg('复制失败，浏览器不兼容!',{icon:2,time:2000});
        }
        document.body.removeChild(textArea);
    }
}

function copyPass(value){
	if (value == ''){
		layer.msg('空,不能复制',{icon:2,time:2000});
		return;
	}
	copyText(value);
}

function isChineseChar(b) {
	var a = /[\u4E00-\u9FA5\uF900-\uFA2D]/;
	return a.test(b)
}

function safeMessage(j, h, g, f, checkName) {
	if(f == undefined) {
		f = ""
	}
	var d = Math.round(Math.random() * 9 + 1);
	var c = Math.round(Math.random() * 9 + 1);
	var e = "";
	e = d + c;
	sumtext = d + " + " + c;
	setCookie("vcodesum", e);
	var checkHtml = "";
	var dbNameMsg = (lan.bt && lan.bt.db_name_msg) ? lan.bt.db_name_msg : "我需要删除的数据库名称是";
	var dbNameErr = (lan.bt && lan.bt.db_name_err) ? lan.bt.db_name_err : "数据库名称输入错误!";
	if (checkName) {
		checkHtml = "<div style='margin-top: 15px; font-size: 14px; color: #d9534f; font-weight: bold; text-align: left;'>" + dbNameMsg + " <input type='text' id='dbNameResult' value='' style='width: 120px; height: 28px; line-height: 28px; border: 1.5px solid #d9534f; border-radius: 8px; padding: 0 8px; color: #444; outline: none; margin-left: 5px; display: inline-block;'></div>";
	}
	var mess = layer.open({
		type: 1,
		title: j,
		area: checkName ? "380px" : "350px",
		closeBtn: 1,
		shadeClose: true,
		content: "<div class='bt-form webDelete pd20 pb70'>\
			<p>" + h + "</p>" + f + "<div class='vcode'>"+lan.bt.cal_msg+"<span class='text'>" + sumtext + "</span>=<input type='number' id='vcodeResult' value=''></div>\
			" + checkHtml + "\
			<div class='bt-form-submit-btn'>\
				<button type='button' class='btn btn-danger btn-sm bt-cancel'>"+lan.public.cancel+"</button>\
				<button type='button' id='toSubmit' class='btn btn-success btn-sm' >"+lan.public.ok+"</button></div>\
			</div>"
	});
	$("#vcodeResult").trigger('focus').on('keyup', function(a) {
		if(a.keyCode == 13) {
			$("#toSubmit").click()
		}
	});
	if (checkName) {
		$("#dbNameResult").on('keyup', function(a) {
			if(a.keyCode == 13) {
				$("#toSubmit").click()
			}
		});
	}
	$(".bt-cancel").on('click', function(){
		layer.close(mess);
	});
	$("#toSubmit").on('click', function() {
		var a = $("#vcodeResult").val().replace(/ /g, "");
		if(a == undefined || a == "") {
			layer.msg('请正确输入计算结果!');
			return
		}
		if(a != getCookie("vcodesum")) {
			layer.msg('请正确输入计算结果!');
			return
		}
		if (checkName) {
			var b = $("#dbNameResult").val().replace(/ /g, "");
			if (b != checkName) {
				layer.msg(dbNameErr);
				return
			}
		}
		layer.close(mess);
		g();
	})
}
//isAction();

function isAction() {
	hrefs = window.location.href.split("/");
	name = hrefs[hrefs.length - 1];
	if(!name) {
		$("#memuA").addClass("current");
		return
	}
	$("#memuA" + name).addClass("current")
}

var W_window = $(window).width();
if(W_window <= 980) {
	$(window).on('scroll', function() {
		var a = $(window).scrollTop();
		$(".sidebar-scroll").css({
			position: "absolute",
			top: a
		})
	})
} else {
	$(".sidebar-scroll").css({
		position: "fixed",
		top: "0"
	})
}
$(function() {
	$(".fb-ico").on('mouseenter', function() {
		$(".fb-text").css({
			left: "36px",
			top: 0,
			width: "80px"
		})
	}).on('mouseleave', function() {
		$(".fb-text").css({
			left: 0,
			width: "36px"
		})
	}).on('click', function() {
		$(".fb-text").css({
			left: 0,
			width: "36px"
		});
		$(".zun-feedback-suggestion").show()
	});
	$(".fb-close").on('click', function() {
		$(".zun-feedback-suggestion").hide()
	});
	$(".fb-attitudes li").on('click', function() {
		$(this).addClass("fb-selected").siblings().removeClass("fb-selected")
	})
});

$("#signout").on('click', function() {
	layer.confirm('您真的要退出面板吗?', {icon:3,closeBtn: 1}, function() {
		window.location.href = "/login?signout=True"
	});
	return false
});


var openWindow = null;
var downLoad = null;
var speed = null;

function task() {
	messageBox();
}

function removeTask(b) {
	var a = layer.msg('正在删除,请稍候...', {
		icon: 16,
		time: 0,
		shade: [0.3, "#000"]
	});
	$.post("/task/remove_task", "id=" + b, function(c) {
		layer.close(a);
		layer.msg(c.msg, {
			icon: c.status ? 1 : 5
		});
	},'json').fail(function(){
		layer.msg(lan.bt.task_close,{icon:1});
	});
}

//获取任务总数
function getTaskCount() {
	$.get("/task/count", '', function(data) {
		$(".task").text(data.data);
	},'json');
}
getTaskCount();
// 仅在非首页时，启动每 6 秒的任务数轮询（首页已由 getNet 高频接口大合并接管，彻底消除了首页并发 API 队头阻塞）
if (!(window.location.pathname === '/' || window.location.pathname === '/index' || window.location.pathname === '')) {
	setInterval(function(){
		if (document.visibilityState !== 'visible') {
			return; // 页面挂在后台，自动暂停高频轮询
		}
		getTaskCount();
	},6000);
}

function setSelectChecked(c, d) {
	var a = document.getElementById(c);
	for(var b = 0; b < a.options.length; b++) {
		if(a.options[b].innerHTML == d) {
			a.options[b].selected = true;
			break
		}
	}
}

function jump() {
	layer.closeAll();
	window.location.href = "/soft";
}

function installTips() {
	$(".fangshi label").on('mouseover', function() {
		var a = $(this).attr("data-title");
		layer.tips(a, this, {tips: [1, "#787878"],time: 0});
	}).on('mouseout', function() {
		$(".layui-layer-tips").remove()
	})
}


// function fly(a) {
// 	var b = $("#task").offset();
// 	$("." + a).on('click', function(d) {
// 		var e = $(this);
// 		var c = $('<span class="yuandian"></span>');
// 		c.fly({
// 			start: {
// 				left: d.pageX,
// 				top: d.pageY
// 			},
// 			end: {
// 				left: b.left + 10,
// 				top: b.top + 10,
// 				width: 0,
// 				height: 0
// 			},
// 			onEnd: function() {
// 				layer.closeAll();
// 				layer.msg(lan.bt.task_add, {icon: 1});
// 				getTaskCount();
// 			}
// 		});
// 	});
// };

function flySlow(a) {
	var b = $("#task").offset();
	var c = $('<span class="yuandian"></span>');
	var d = $("." + a);
	c.fly({
		start: {
			left: d.offset().left,
			top: d.offset().top,
		},
		end: {
			left: b.left + 10,
			top: b.top + 10,
			width: 0,
			height: 0
		},
		speed: 0.65,
		onEnd: function() {
			layer.closeAll();
			layer.msg(lan.bt.task_add, {icon: 1});
			getTaskCount();
			$('.yuandian').remove();
		}
	});
	
};

function readerTableChecked(){
    $('thead').find('input').off('click').on('click', function(){
        $('tbody').find('tr').each(function(i,obj){
        	var fin = $(this).find('td')[0];
        	checked = $(fin).find('input').prop('checked');
        	$(fin).find('input').prop('checked',!checked);
        });
    });    
}

//检查选中项
function checkSelect(){
	setTimeout(function(){
		var num = $('tbody').find('input[type="checkbox"]:checked').length;
        if (num == 1) {
            $('button[batch="true"]').hide();
            $('button[batch="false"]').show();
        }else if (num>1){
            $('button[batch="true"]').show();
            $('button[batch="false"]').show();
		}else{
            $('button[batch="true"]').hide();
            $('button[batch="false"]').hide();
		}
	},5);
}

//处理排序
function listOrder(skey,type,obj){
	or = getCookie('order');
	orderType = 'desc';
	if(or){
		if(or.split(' ')[1] == 'desc'){
			orderType = 'asc';
		} else if(or.split(' ')[1] == 'asc'){
			orderType = 'none';
		}
	}
	setCookie('order',skey + ' ' + orderType);
	getWeb(1);
	$(obj).find(".glyphicon-triangle-bottom").remove();
	$(obj).find(".glyphicon-triangle-top").remove();
	$(obj).find(".glyphicon-stop").remove();
	if(orderType == 'none'){
		$(obj).append("<span class='glyphicon glyphicon glyphicon-stop' style='margin-left:5px;color:#bbb'></span>");
	} else if(orderType == 'asc') {
		$(obj).append("<span class='glyphicon glyphicon-triangle-bottom' style='margin-left:5px;color:#bbb'></span>");
	} else {
		$(obj).append("<span class='glyphicon glyphicon-triangle-top' style='margin-left:5px;color:#bbb'></span>");
	}
}


//获取关联列表
function getPanelList(){
	var con ='';
	$.post("/setting/get_panel_list",function(rdata){
		if (!rdata.status){
			return;
		}

		var rdata = rdata.data;

		for(var i=0; i<rdata.length; i++){
			con +='<h3 class="mypcip mypcipnew" style="opacity:.6;cursor: pointer;" data-url="'+rdata[i].url+'" data-user="'+rdata[i].username+'" data-pw="'+rdata[i].password+'">\
				<span class="f14 cw">'+rdata[i].title+'</span>\
				<em class="btedit" onclick="bindPanel(0,\'c\',\''+rdata[i].title+'\',\''+rdata[i].id+'\',\''+rdata[i].url+'\',\''+rdata[i].username+'\',\''+rdata[i].password+'\')"></em>\
				</h3>';
		}

		$("#newbtpc").html(con);
		$(".mypcipnew").on('mouseenter', function(){
			$(this).css("opacity","1");
		}).on('mouseleave', function(){
			$(this).css("opacity",".6");
		}).on('click', function(){
			// $("#panel_form").remove();
			var murl = $(this).attr("data-url");
			var user = $(this).attr("data-user");
			var pw = $(this).attr("data-pw");

			var random_str = getRandomString(8);

			var timestamp = Date.parse(new Date());
			var data = {
				'rand':random_str,
				'username':user,
				'password':pw,
				'time':timestamp
			};


			data_json =JSON.stringify(data);
			login_args = base64_encode(data_json);

			endpoint_url = murl + '?login='+login_args;
			window.open(endpoint_url);
			// layer.open({
			// 	type: 2,
			// 	title: false,
			//  	closeBtn: 0, //不显示关闭按钮
			// 	shade: [0],
			// 	area: ['340px', '215px'],
			// 	offset: 'rb', //右下角弹出
			// 	time: 5, //2秒后自动关闭
			// 	anim: 2,
			// 	content: [murl, 'no']
			// });
			// window.open(murl);
			// 
			// var loginForm ='<div id="panel_form" style="display:none"><form id="toBtpanel" action="'+now_url.origin+'/do_login" method="post" target="btpfrom">\
			// 	<input name="username" value="'+user+'" type="text">\
			// 	<input name="password" value="'+pw+'" type="password">\
			// 	<input name="code" id="bt_code" value="" type="text">\
			// </form><iframe name="btpfrom" src=""></iframe></div>';
			// $("body").append(loginForm);
			// // console.log($("panel_form").html());
			// layer.msg('正在打开面板...',{icon:16,shade: [0.3, '#000'],time:1000});
			// setTimeout(function(){
			// 	$("#toBtpanel").submit();
			// },1000);
			// setTimeout(function(){
			// 	window.open(murl);
			// },2000);
		});
		$(".btedit").on('click', function(e){
			e.stopPropagation();
		});
	},'json');
}
getPanelList();

//添加面板快捷登录
function bindPanel(a,type,ip,btid,url,user,pw){
	var titleName = '关联面板';
	if(type == "b"){
		btn = "<button type='button' class='btn btn-success btn-sm' onclick=\"bindPanel(1,'b')\">添加</button>";
	} else {
		titleName = '修改关联' + ip;
		btn = "<button type='button' class='btn btn-default btn-sm' onclick=\"bindPaneldel('"+btid+"')\">删除</button>\
		<button type='button' class='btn btn-success btn-sm' onclick=\"bindPanel(1,'c','"+ip+"','"+btid+"')\" style='margin-left:7px'>修改</button>";
	}
	if(url == undefined) url="http://";
	if(user == undefined) user="";
	if(pw == undefined) pw="";
	if(ip == undefined) ip="";
	if(a == 1) {
		var gurl = "/setting/add_panel_info";
		var btaddress = $("#btaddress").val();
		if(!btaddress.match(/^(http|https)+:\/\/([\w-]+\.)+[\w-]+:\d+/)){
			layer.msg('面板地址格式不正确，示例：<p>http://192.168.0.1:8888</p>',{icon:5,time:5000});
			return;
		}
		var btuser = encodeURIComponent($("#btuser").val());
		var btpassword = encodeURIComponent($("#btpassword").val());
		var bttitle = $("#bttitle").val();
		var data = "title="+bttitle+"&url="+encodeURIComponent(btaddress)+"&username="+btuser+"&password="+btpassword;
		if(btaddress =="" || btuser=="" || btpassword=="" || bttitle==""){
			layer.msg(lan.bt.panel_err_empty,{icon:8});
			return;
		}
		if(type=="c"){
			gurl = "/setting/set_panel_info";
			data = data+"&id="+btid;
		}
		$.post(gurl, data, function(b) {
			if(b.status) {
				layer.closeAll();
				layer.msg(b.msg, {icon: 1});
				getPanelList();
			} else {
				layer.msg(b.msg, {icon: 2})
			}
		},'json');
		return
	}
	layer.open({
		type: 1,
		area: "400px",
		title: titleName,
		closeBtn: 1,
		shift: 5,
		shadeClose: false,
		content: "<div class='bt-form pd20 pb70'>\
				<div class='line'><span class='tname'>面板地址</span>\
				<div class='info-r'><input class='bt-input-text' type='text' name='btaddress' id='btaddress' value='"+url+"' placeholder='面板地址' style='width:100%'/></div>\
				</div>\
				<div class='line'><span class='tname'>用户名</span>\
				<div class='info-r'><input class='bt-input-text' type='text' name='btuser' id='btuser' value='"+user+"' placeholder='用户名' style='width:100%'/></div>\
				</div>\
				<div class='line'><span class='tname'>密码</span>\
				<div class='info-r'><input class='bt-input-text' type='password' name='btpassword' id='btpassword' value='"+pw+"' placeholder='密码' style='width:100%'/></div>\
				</div>\
				<div class='line'><span class='tname'>备注</span>\
				<div class='info-r'><input class='bt-input-text' type='text' name='bttitle' id='bttitle' value='"+ip+"' placeholder='备注' style='width:100%'/></div>\
				</div>\
				<div class='line'><ul class='help-info-text c7'>\
					<li>收藏其它服务器面板资料，实现一键登录面板功能</li><li>面板备注不可重复</li>\
					<li><font style='color:red'>注意，开启广告拦截会导致无法快捷登录。</font></li></ul>\
				</div>\
				<div class='bt-form-submit-btn'><button type='button' class='btn btn-danger btn-sm' onclick=\"layer.closeAll()\">关闭</button> "+btn+"</div>\
			</div>",

		success:function(){
			$("#btaddress").on("input",function(){
				var str =$(this).val();
				var isip = /([\w-]+\.){2,6}\w+/;
				var iptext = str.match(isip);
				if(iptext) {
					var bttitle_val = $("#bttitle").val();
					if (bttitle_val == '') {
						$("#bttitle").val(iptext[0]);
					}
				}
			}).on('blur', function(){
				var str =$(this).val();
				var isip = /([\w-]+\.){2,6}\w+/;
				var iptext = str.match(isip);
				if(iptext) {
					var bttitle_val = $("#bttitle").val();
					if (bttitle_val == '') {
						$("#bttitle").val(iptext[0]);
					}
				}
			});
		}
	});
}
//删除快捷登录
function bindPaneldel(id){
	$.post("/setting/del_panel_info","id="+id,function(rdata){
		layer.closeAll();
		layer.msg(rdata.msg,{icon:rdata.status?1:2});
		getPanelList();
	},'json');
}

function getSpeed(sele){
	if(!$(sele)) {
		return;
	}
	$.get('/files/get_speed',function(data){
		var speed = data['data'];
		if(speed.title === null){
			return;
		}
		var mspeed = '';
		if(speed.speed > 0){
			mspeed = '<span class="pull-right">'+toSize(speed.speed)+'/s</span>';
		}
		var body = '<p>'+speed.title+' <img src="/static/img/ing.gif"></p>\
		<div class="bt-progress"><div class="bt-progress-bar" style="width:'+speed.progress+'%"><span class="bt-progress-text">'+speed.progress+'%</span></div></div>\
		<p class="f12 c9"><span class="pull-left">'+speed.used+'/'+speed.total+'</span>'+mspeed+'</p>';
		$(sele).prev().hide();
		$(sele).css({"margin-left":"-37px","width":"380px"});
		$(sele).parents(".layui-layer").css({"margin-left":"-100px"});
		
		$(sele).html(body);
		setTimeout(function(){
			getSpeed(sele);
		},1000);
	},'json');
}

function tasklist(){
	var con='<div style="height: 520px; position: relative;"><ul class="cmdlist" style="margin: 0; padding: 0; height: 100%; overflow: auto;"></ul><div style="position: absolute; bottom: -15px; left: 0; right: 0; text-align: center; color: #999; font-size: 12px; line-height: 1;">若任务长时间未执行，请尝试在首页点【重启面板】来重置任务队列</div></div>';
	$("#msg_box .taskcon").html(con);
	$.post("/task/list", "tojs=getTaskList&table=tasks&limit=10&p=1", function(g) {
		$('#msg_box .msg_count').html(g.count);
	},'json');

	setTimeout(function(){
		getReloads();
	},100);
}

//消息盒子
function messageBox() {
	layer.open({
		type: 1,
		title: '消息盒子',
		area: "670px",
		closeBtn: 1,
		shadeClose: false,
		content: '<div class="bt-form">\
			<div class="bt-w-main" id="msg_box">\
				<div class="bt-w-menu">\
					<p class="bgw" id="taskList" onclick="tasklist()">任务列表(<span class="task_count">0</span>)</p>\
					<p onclick="remind()">消息列表(<span class="msg_count">0</span>)</p>\
					<p onclick="execLog()">执行日志</p>\
				</div>\
				<div class="bt-w-con pd15">\
					<div class="taskcon"></div>\
				</div>\
			</div>\
			<div id="msg_box_sys_info" style="margin: 0 15px 15px 15px; border-top: 1px solid #efefef; padding-top: 10px; font-size: 13px; color: #666; display: flex; justify-content: space-between;">\
				<span>CPU: <span id="msg_box_cpu" style="color:#20a53a">0%</span></span>\
				<span>内存: <span id="msg_box_mem" style="color:#20a53a">0%</span></span>\
				<span>上行: <span id="msg_box_up" style="color:#f7b851">0 B/s</span></span>\
				<span>下行: <span id="msg_box_down" style="color:#52a9ff">0 B/s</span></span>\
			</div>\
		</div>',
		success:function(){
			$(".bt-w-menu p").on('click', function(){
				$(this).addClass("bgw").siblings().removeClass("bgw");
			});
			tasklist();
			
			function updateSysInfo() {
				if ($("#msg_box_sys_info").length === 0) return;
				$.get("/system/network", function(net) {
					if ($("#msg_box_sys_info").length === 0) return;
					if (net.cpu) {
						$("#msg_box_cpu").text(net.cpu[0] + "%");
					}
					if (net.mem) {
						var memUsed = net.mem.memRealUsed;
						var memTotal = net.mem.memTotal;
						var memPercent = memTotal > 0 ? ((memUsed / memTotal) * 100).toFixed(1) : 0;
						$("#msg_box_mem").text(memPercent + "% (" + toSize(memUsed) + "/" + toSize(memTotal) + ")");
					}
					if (net.network && net.network.ALL) {
						$("#msg_box_up").text(toSize(net.network.ALL.up) + "/s");
						$("#msg_box_down").text(toSize(net.network.ALL.down) + "/s");
					}
				}, 'json');
			}
			updateSysInfo();
			window.msgBoxSysInfoInterval = setInterval(updateSysInfo, 3000);
		},
		end: function() {
			if (window.msgBoxSysInfoInterval) {
				clearInterval(window.msgBoxSysInfoInterval);
			}
		}
	});
}

//取执行日志
function execLog(){
	$.post('/task/get_exec_log',{},function(logs){
		var lbody = '<textarea readonly="" style="margin: 0px;width: 530px;height: 520px;background-color: #333;color:#fff; padding:0 5px" id="exec_log">'+logs+'</textarea>';
		$(".taskcon").html(lbody);
		var ob = document.getElementById('exec_log');
		ob.scrollTop = ob.scrollHeight;
	});
}

//查看指定任务的日志
function showTaskLog(id, name) {
	var loadT = layer.msg('正在获取日志...', { icon: 16, time: 0, shade: 0.3 });
	$.post('/task/get_task_log_by_id', {id: id}, function(rdata) {
		layer.close(loadT);
		var logContent = '';
		if (rdata.status) {
			logContent = rdata.msg;
		} else {
			logContent = rdata.msg;
		}
		layer.open({
			type: 1,
			title: name + ' - 执行日志',
			area: ['670px', '500px'],
			shadeClose: false,
			closeBtn: 1,
			content: '<div class="pd15"><textarea readonly style="margin: 0px;width: 100%;height: 400px;background-color: #333;color:#fff; padding:5px; border:none">' + logContent + '</textarea></div>'
		});
	}, 'json');
}

/**
 * 获取时分秒
 * @param {Number} seconds 总秒数
 * @param {String} dateFormat 返回的日期格式，默认为'H:i:s'
 */
function getSFM(seconds, dateFormat = 'H:i:s') {

	var obj = {};
 	obj.H = Number.parseInt(seconds / 3600);
 	obj.i = Number.parseInt((seconds - obj.H * 3600) / 60);
 	obj.s = Number.parseInt(seconds - obj.H * 3600 - obj.i * 60);
 	if (obj.H < 10) {
    	obj.H = '0' + obj.H;
  	}
  	if (obj.i < 10) {
    	obj.i = '0' + obj.i;
  	}
  	if (obj.s < 10) {
    	obj.s = '0' + obj.s;
  	}
 
  	// 3.解析
  	var rs = dateFormat.replace('H', obj.H).replace('i', obj.i).replace('s', obj.s);
  	return rs;
}

function remind(a){
	a = a == undefined ? 1 : a;
	$(".taskcon").html('');
	$.post("/task/list", "table=tasks&result=2,4,6,8&limit=10&p=" + a, function(g) {
		var e = '';
		var f = false;
		for(var d = 0; d < g.data.length; d++) {
			var status = g.data[d].status;
			var status_text = '已经完成';
			var cos_text = '';
			if (status == '1'){
				status_text = '完成';
				cos_text = '耗时['+getSFM(g.data[d].end - g.data[d].start)+']'
			} else if (status == '0'){
				status_text = '正在处理';
				cos_text = '等待中..';
			} else if (status == '-1'){
				status_text = '安装中';
				cos_text = '..';
			}

			e += '<tr>\
				<td><input type="checkbox"></td>\
				<td>\
					<div class="titlename c3"><a href="javascript:;" class="btlink" onclick="showTaskLog('+g.data[d].id+', \''+g.data[d].name+'\')">'+g.data[d].name+'</a></span>\
						<span class="rs-status">【'+status_text+'】<span>\
						<span class="rs-time">'+cos_text+'</span>\
					</div>\
				</td>\
				<td class="text-right c3">'+g.data[d].add_time+'</td>\
			</tr>';
		}
		var con = '<div class="divtable"><table class="table table-hover">\
					<thead>\
						<tr>\
							<th width="20"><input id="Rs-checkAll" type="checkbox" onclick="RscheckSelect()"></th>\
							<th>'+lan.bt.task_name+'</th><th class="text-right">'+lan.bt.task_time+'</th>\
						</tr>\
					</thead>\
					<tbody id="remind">'+e+'</tbody>\
					</table>\
				</div>\
				<div class="mtb15" style="height:32px">\
					<div class="pull-left buttongroup" style="display:none;">\
						<button class="btn btn-default btn-sm mr5 rs-del" disabled="disabled">'+lan.public.del+'</button>\
						<button class="btn btn-default btn-sm mr5 rs-read" disabled="disabled">'+lan.bt.task_tip_read+'</button>\
						<button class="btn btn-default btn-sm">'+lan.bt.task_tip_all+'</button>\
					</div>\
					<div id="taskPage" class="page"></div>\
				</div>';
		$(".taskcon").html(con);

		$(".msg_count").text(g.count);
		$("#taskPage").html(g.page);
		$("#Rs-checkAll").on('click', function(){
			if($(this).prop("checked")){
				$("#remind").find("input").prop("checked",true);
			} else {
				$("#remind").find("input").prop("checked",false);
			}
		});
	},'json');
}

function getReloads() {
	var mm = $("#msg_box .bt-w-menu .bgw").html();
	if(mm == undefined || mm.indexOf('任务列表') == -1) {
		clearInterval(speed);
		speed = null;
		return
	}
	if(speed) {return;}

	function renderRunTask(){
		var mm = $("#msg_box .bt-w-menu .bgw").html();
		if(mm == undefined || mm.indexOf('任务列表') == -1) {
			clearInterval(speed);
			speed = null;
			a = 0;
			return
		}
		$.post('/task/get_task_speed', '', function(h) {
			if(h.task == undefined) {
				$(".task_count").text(0);
				$(".cmdlist").html('当前没有任务!');
				return;
			}
			var b = '';
			var d = '';
			for(var g = 0; g < h.task.length; g++) {
				if(h.task[g].status == "-1") {
					if(h.task[g].type != "download") {
						var c = "";
						var f = h.msg.split("\n");
						for(var e = 0; e < f.length; e++) {
							c += f[e] + "<br>";
						}
						if(h.task[g].name.indexOf("扫描") != -1) {
							b = "<li>\
								<span class='titlename'>" + h.task[g].name + "</span>\
								<span class='state'>正在扫描<img src='/static/img/ing.gif'> | <a href=\"javascript:removeTask(" + h.task[g].id + ")\">关闭</a></span>\
								<span class='opencmd'></span>\
								<div class='cmd'>" + c + "</div>\
							</li>";
						} else {
							b = "<li>\
								<span class='titlename'>" + h.task[g].name + "</span>\
								<span class='state'>正在安装<img src='/static/img/ing.gif'> | <a href=\"javascript:removeTask(" + h.task[g].id + ")\">关闭</a></span>\
								<div class='cmd'>" + c + "</div>\
							</li>";
						}
					} else {
						b = "<li>\
								<div class='line-progress' style='width:" + h.msg.pre + "%'></div>\
								<span class='titlename'>" + h.task[g].name + "<a style='margin-left:130px;'>" + (toSize(h.msg.used) + "/" + toSize(h.msg.total)) + "</a></span>\
								<span class='com-progress'>" + h.msg.pre + "%</span>\
								<span class='state'>下载中<img src='/static/img/ing.gif'> | <a href=\"javascript:removeTask(" + h.task[g].id + ")\">"+lan.public.close+"</a></span>\
							</li>"
					}
				} else {
					d += "<li><span class='titlename'>" + h.task[g].name + "</span><span class='state'>等待 | <a style='color:green' href=\"javascript:removeTask(" + h.task[g].id + ')">删除</a></span></li>'
				}
			}
			$("#task").text(h.count);
			$(".task_count").text(h.count);
			$(".cmdlist").html(b + d);
			$(".cmd").html(c);
			try{
				if($(".cmd")[0].scrollHeight) $(".cmd").scrollTop($(".cmd")[0].scrollHeight);
			}catch(e){
				return;
			}
		},'json').fail(function(){});
	}

	renderRunTask();
	speed = setInterval(function() {
		renderRunTask();
	}, 2000);
}

//检查选中项
function RscheckSelect(){
	setTimeout(function(){
		var checkList = $("#remind").find("input");
		var count = 0;
		for(var i=0;i<checkList.length;i++){
			if(checkList[i].checked) count++;
		}
		if(count > 0){
			$(".buttongroup .btn").removeAttr("disabled");
		}else{
			$(".rs-del,.rs-read").attr("disabled","disabled");
		}
	},5);
}

function activeDisk() {
	var a = $("#PathPlace").find("span").text().substring(0, 1);
	switch(a) {
		case "C":
			$(".path-con-left dd:nth-of-type(1)").css("background", "#eee").siblings().removeAttr("style");
			break;
		case "D":
			$(".path-con-left dd:nth-of-type(2)").css("background", "#eee").siblings().removeAttr("style");
			break;
		case "E":
			$(".path-con-left dd:nth-of-type(3)").css("background", "#eee").siblings().removeAttr("style");
			break;
		case "F":
			$(".path-con-left dd:nth-of-type(4)").css("background", "#eee").siblings().removeAttr("style");
			break;
		case "G":
			$(".path-con-left dd:nth-of-type(5)").css("background", "#eee").siblings().removeAttr("style");
			break;
		case "H":
			$(".path-con-left dd:nth-of-type(6)").css("background", "#eee").siblings().removeAttr("style");
			break;
		default:
			$(".path-con-left dd").removeAttr("style");
	}
}


//检查登陆状态
function check_login(){
	$.post('/check_login',{},function(rdata){
		if(!rdata.status){
			location.reload();
		}
	},'json');
}

//登陆跳转
function to_login(){
	layer.confirm('您的登陆状态已过期，请重新登陆!',{title:'会话已过期',icon:2,closeBtn: 1,shift: 5},function(){
		location.reload();
	});
}
//表格头固定
function table_fixed(name){
	var tableName = document.querySelector('#'+name);
	tableName.addEventListener('scroll',scroll_handle);
}
function scroll_handle(e){
	var scrollTop = this.scrollTop;
	$(this).find("thead").css({"transform":"translateY("+scrollTop+"px)","position":"relative","z-index":"1"});
}

function asyncLoadImage(obj, url){
	
	if (typeof(url) == 'undefined'){
		return;
	}

	function loadImage(obj,url,callback){
	    var img = new Image();
	    img.src = url;
	    
	    if(img.complete){
	        callback.call(img,obj);
	        return;
	    }
	    img.onload = function(){
	        callback.call(img,obj);
	    }
	}

	function showImage(obj){
	    obj.src = this.src;
	    $(obj).attr('data-src', '');
	}
	loadImage(obj, url, showImage);
}

function loadImage(){
	$('img').each(function(i){
		// console.log($(this).attr('data-src'));
		if ($(this).attr('data-src') != ''){
			asyncLoadImage(this, $(this).attr('data-src'));
		} 
    });
}

var socket, gterm;
function webShell(dir) {
    var loadT = layer.msg('正在加载终端组件...', {icon: 16, time: 0, shade: [0.1, '#000']});
    loadWebShellResources().then(function() {
        layer.close(loadT);
        _webShellInit(dir);
    }).catch(function(err) {
        layer.close(loadT);
        layer.msg('终端组件加载失败，请刷新页面重试', {icon: 2});
        console.fail(err);
    });
}
function _webShellInit(dir) {
    var termCols = 83;
    var termRows = 21;
    var sendTotal = 0;
    if(!socket)socket = io.connect();

    // 移除已有的同一监听器，避免重复绑定内存泄漏和写冲突
    socket.off('server_response');

    var isFirstResponse = true;
    var term = new Terminal({
        cols: termCols,
        rows: termRows,
        screenKeys: true,
        useStyle: true,
        fontFamily: 'Consolas, "Courier New", Courier, monospace',
        fontSize: 14,
        lineHeight: 1.25,
        letterSpacing: 1
    });
    gterm = term;

    socket.on('server_response', function (data) {
        term.write(data.data);

        // 自动切换工作目录
        if (isFirstResponse && dir) {
            isFirstResponse = false;
            setTimeout(function() {
                socket.emit('webssh', 'cd "' + dir + '"\r');
            }, 100);
        }

        if (data.data == '\r\n登出\r\n' || 
            data.data == '登出\r\n' || 
            data.data == '\r\nlogout\r\n' || 
            data.data == 'logout\r\n') {
            setTimeout(function () {
                layer.closeAll();
                term.destroy();
                clearInterval(interval);
            }, 500);
        }
    });

    $(window).unload(function(){
  　     term.destroy();
        clearInterval(interval);
    });

    if (socket) {
        socket.emit('webssh', '');
        interval = setInterval(function () {
            socket.emit('webssh', '');
        }, 500);
    }
    
    term.on('data', function (data) {
        socket.emit('webssh', data);
    });


    var tryFit = function() {
        try {
            if (typeof fit !== 'undefined') {
                Terminal.applyAddon(fit);
            }
            if (term && term.element && typeof term.fit === 'function') {
                term.fit();
                if (socket) {
                    socket.emit('webssh', {resize: 1, cols: term.cols, rows: term.rows});
                }
            }
        } catch(e) {
            console.log(e);
        }
    };

    function resizeTerm(layero) {
        try {
            var content = layero.find('.layui-layer-content');
            var termBox = layero.find('.term-box');
            var termEl = layero.find('#term');
            var h = content.height();
            var w = content.width();
            termBox.css({
                width: w + 'px',
                height: h + 'px',
                padding: '5px 10px 10px',
                'box-sizing': 'border-box'
            });
            termEl.css({
                width: (w - 20) + 'px',
                height: (h - 15) + 'px'
            });
        } catch(e) {
            console.log(e);
        }
    }

    var term_box = layer.open({
        type: 1,
        title: "本地终端",
        area: ['900px', '550px'],
        closeBtn: 1,
        shadeClose: false,
        maxmin: true,
        content: '<div class="term-box" style="overflow:hidden; box-sizing:border-box;"><div id="term" style="overflow:hidden;"></div></div>',
        success: function(layero, index){
            layero.find('.layui-layer-content').css('overflow', 'hidden');
            
            // 动态向页面头部注入极致防跳与防滚动样式
            if ($("#webshell-prevent-jump-style").length === 0) {
                $("<style id='webshell-prevent-jump-style'>")
                    .prop("type", "text/css")
                    .html("\
                        .xterm-helper-textarea {\
                            position: fixed !important;\
                            top: 0px !important;\
                            left: 0px !important;\
                            width: 0px !important;\
                            height: 0px !important;\
                            opacity: 0 !important;\
                            pointer-events: none !important;\
                        }\
                        .term-box, #term {\
                            overflow: hidden !important;\
                        }\
                    ")
                    .appendTo("head");
            }

            var canEl = document.getElementById('term');
            var termBox = layero.find('.term-box')[0];

            // 锁定滚动容器：捕获任何滚动行为并强行重置为 0，双重保险
            if (canEl) {
                canEl.addEventListener('scroll', function() {
                    canEl.scrollTop = 0;
                    canEl.scrollLeft = 0;
                }, true);
            }
            if (termBox) {
                termBox.addEventListener('scroll', function() {
                    termBox.scrollTop = 0;
                    termBox.scrollLeft = 0;
                }, true);
            }

            // 3. 智能右击“有选中即复制，无选中弹出浮动粘贴气泡”高品质交互
            if (canEl) {
                canEl.addEventListener('contextmenu', function (e) {
                    e.preventDefault();
                    e.stopPropagation();

                    var mouseX = e.pageX;
                    var mouseY = e.pageY;
                    
                    // 清除残留气泡
                    $("#term-paste-bubble").remove();

                    // 判定是否有选中内容
                    var selectText = term.getSelection();
                    if (selectText) {
                        // A 通道：智能自动复制
                        var tempTextarea = $("<textarea>")
                            .val(selectText)
                            .css({ position: "fixed", top: "0", left: "0", opacity: "0" })
                            .appendTo("body");
                        tempTextarea.select();
                        try {
                            document.execCommand("copy");
                            layer.msg('已自动复制选中内容！', {icon: 1, time: 1000});
                        } catch(err) {
                            layer.msg('自动复制失败，浏览器不兼容', {icon: 2});
                        }
                        tempTextarea.remove();
                        term.focus();
                        return false;
                    }

                    // B 通道：磨砂悬浮粘贴气泡（KISS 原则，100% 规避 HTTP 剪贴板安全屏蔽）
                    var menudiv = '\
                        <div id="term-paste-bubble" style="position: absolute; z-index: 29891015; padding: 6px 10px; background: rgba(30, 30, 30, 0.85); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 6px; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.36);">\
                            <input type="text" id="term-paste-input" placeholder="快捷粘贴：请在此处 Ctrl+V 并回车发送" style="width: 250px; background: transparent; border: none; outline: none; color: #fff; font-size: 13px; font-family: Consolas, monospace;" autocomplete="off" />\
                        </div>';
                    $("body").append(menudiv);
                    
                    // 气泡溢出边界保护
                    var bubbleW = 280;
                    var bubbleH = 40;
                    var winW = $(window).width();
                    var winH = $(window).height();
                    var leftPos = mouseX - 20;
                    var topPos = mouseY - 20;
                    if (leftPos + bubbleW > winW) leftPos = winW - bubbleW - 10;
                    if (topPos + bubbleH > winH) topPos = winH - bubbleH - 10;
                    
                    $("#term-paste-bubble").css({
                        "left": leftPos + "px",
                        "top": topPos + "px"
                    });

                    var pInput = $("#term-paste-input");
                    pInput.focus();

                    // 监听粘贴（paste）和回车/Esc事件
                    pInput.on('paste', function(pe) {
                        setTimeout(function() {
                            var text = pInput.val();
                            if (text && socket) {
                                socket.emit('webssh', text);
                            }
                            $("#term-paste-bubble").remove();
                            term.focus();
                        }, 50);
                    });

                    pInput.on('keydown', function(ke) {
                        if (ke.keyCode === 13) { // Enter 发送
                            var text = pInput.val();
                            if (text && socket) {
                                socket.emit('webssh', text);
                            }
                            $("#term-paste-bubble").remove();
                            term.focus();
                        } else if (ke.keyCode === 27) { // Esc 退出
                            $("#term-paste-bubble").remove();
                            term.focus();
                        }
                    });
                }, true);
            }

            // 点击外部或气泡外，自动关闭粘贴框并聚焦终端
            $(document).off('click.ssh_menu').on('click.ssh_menu', function (e) {
                if ($(e.target).closest("#term-paste-bubble").length === 0) {
                    $("#term-paste-bubble").remove();
                }
            });

            resizeTerm(layero);
            setTimeout(function() {
                tryFit();
            }, 100);
            setTimeout(function() {
                tryFit();
            }, 300);
        },
        full: function(layero){
            resizeTerm(layero);
            setTimeout(function() {
                tryFit();
            }, 100);
            setTimeout(function() {
                tryFit();
            }, 300);
        },
        restore: function(layero){
            resizeTerm(layero);
            setTimeout(function() {
                tryFit();
            }, 100);
            setTimeout(function() {
                tryFit();
            }, 300);
        },
        cancel: function () {
            term.destroy();
            clearInterval(interval);
        }
    });
	
    setTimeout(function () {
        term.open(document.getElementById('term'));
        $("#term").show();
        term.setOption('cursorBlink', true);
        term.setOption('fontSize', 14);
        term.setOption('fontFamily', 'Consolas, "Courier New", Courier, monospace');
        term.setOption('lineHeight', 1.25);
        term.setOption('letterSpacing', 1);
        $('#term').css('font-family', 'Consolas, "Courier New", Courier, monospace');
        
        tryFit();
        socket.emit('webssh', "\n");
        term.focus();
        setTimeout(function() {
            tryFit();
        }, 150);
        setTimeout(function() {
            tryFit();
        }, 300);
    }, 100);
}

function shell_to_baidu() {
    var selectText = getCookie('ssh_selection');
    remove_ssh_menu();
    window.open('https://www.baidu.com/s?wd=' + selectText)
    gterm.focus();
}

function shell_paste_text(){
    socket.emit('webssh', getCookie('ssh_selection'));
    remove_ssh_menu();
    gterm.focus();
}

function shell_paste_clipboard() {
    remove_ssh_menu();
    if (navigator.clipboard && navigator.clipboard.readText) {
        navigator.clipboard.readText().then(function(text) {
            if (socket) {
                socket.emit('webssh', text);
            }
            if (gterm) {
                gterm.focus();
            }
        }).catch(function(err) {
            layer.msg('粘贴失败，请在浏览器地址栏左侧允许该网页的“剪贴板”权限，或直接使用 Ctrl+V 粘贴！', {icon: 2});
            if (gterm) {
                gterm.focus();
            }
        });
    } else {
        layer.msg('您的浏览器安全设置不支持脚本读取剪贴板，请直接使用 Ctrl+V 粘贴！', {icon: 2});
        if (gterm) {
            gterm.focus();
        }
    }
}

function remove_ssh_menu() {
    $(".contextmenu").remove();
}

//显示进度
function showSpeed(filename) {
    $.post('/files/get_last_body', { num: 10,path: filename}, function (rdata) {
    	if ($("#speed_log_lst").length < 1){
    		return;
    	}
		if (rdata.status) {
			$("#speed_log_lst").html(rdata.data);
			$("#speed_log_lst").scrollTop($("#speed_log_lst")[0].scrollHeight);
		}
		setTimeout(function () { showSpeed(filename); }, 1000);
    },'json');
}
/**
 * 显示进度窗口
 */
function showSpeedWindow(msg, speed_log_func_name, callback){
	var speed_msg = "<pre style='margin-bottom: 0px;height:250px;text-align: left;background-color: #000;\
		color: #fff;white-space: pre-wrap;' id='speed_log_lst'>[MSG]</pre>";
	var showSpeedKey = layer.open({
		title: false,
		type: 1,
		closeBtn: 2,
		shade: 0.3,
		area: "700px",
		offset: "30%",
		content: speed_msg.replace('[MSG]', msg),
		success: function (layers, index) {
			var url = speed_log_func_name.replace('.','/');
			$.post('/'+url, {}, function(rdata){
				if (rdata.status){
					setTimeout(function () {
						showSpeed(rdata.data);
					}, 1000);
				} else {
					layer.msg("缺少指定文件!");
				}
			},'json');
			if (callback) {callback(layers,index,showSpeedKey);}
		}
    });
}


/*** 其中功能,针对插件通过库使用 start ***/

function toUrlParam(json) {
    return Object.keys(json).map(key => key + '=' + json[key]).join('&');
}

//字符串转数组对象
function toArrayObject(str){
	var data = {};
    kv = str.split('&');
    for(i in kv){
        v = kv[i].split('=');
        data[v[0]] = v[1];
    }
    return data;
}

/**
* 实体字符编码
* @param {*} text 待编码的文本
* @returns
*/
function entitiesEncode(text) {
    text = text.replace(/&/g, "&amp;");
    text = text.replace(/</g, "&lt;");
    text = text.replace(/>/g, "&gt;");
    text = text.replace(/ /g, "&nbsp;");
    text = text.replace(/"/g, "&quot;");
    return text;
}
/**
* 实体字符解码
* @param {*} text 待解码的文本
* @returns
*/
function entitiesDecode(text) {
    text = text.replace(/&amp;/g, "&");
    text = text.replace(/&lt;/g, "<");
    text = text.replace(/&gt;/g, ">");
    text = text.replace(/&nbsp;/g, " ");
    text = text.replace(/&quot;/g, "'");
    return text;
}

// base64.js
// base64加密
function base64_encode(str) {
    var base64EncodeChars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    var out, i, len;
    var c1, c2, c3;

    len = str.length;
    i = 0;
    out = "";
    while(i < len) {
        c1 = str.charCodeAt(i++) & 0xff;
        if(i == len)
        {
            out += base64EncodeChars.charAt(c1 >> 2);
            out += base64EncodeChars.charAt((c1 & 0x3) << 4);
            out += "==";
            break;
        }
        c2 = str.charCodeAt(i++);
        if(i == len)
        {
            out += base64EncodeChars.charAt(c1 >> 2);
            out += base64EncodeChars.charAt(((c1 & 0x3)<< 4) | ((c2 & 0xF0) >> 4));
            out += base64EncodeChars.charAt((c2 & 0xF) << 2);
            out += "=";
            break;
        }
        c3 = str.charCodeAt(i++);
        out += base64EncodeChars.charAt(c1 >> 2);
        out += base64EncodeChars.charAt(((c1 & 0x3)<< 4) | ((c2 & 0xF0) >> 4));
        out += base64EncodeChars.charAt(((c2 & 0xF) << 2) | ((c3 & 0xC0) >>6));
        out += base64EncodeChars.charAt(c3 & 0x3F);
    }
    return out;
}


// base64解密
function base64_decode(str) {
    var base64DecodeChars = new Array(
        -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
        -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
        -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, 62, -1, -1, -1, 63,
        52, 53, 54, 55, 56, 57, 58, 59, 60, 61, -1, -1, -1, -1, -1, -1,
        -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14,
        15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, -1, -1, -1, -1, -1,
        -1, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40,
        41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, -1, -1, -1, -1, -1);
    var c1, c2, c3, c4;
    var i, len, out;

    len = str.length;
    i = 0;
    out = "";
    while(i < len) {
        /* c1 */
        do {
            c1 = base64DecodeChars[str.charCodeAt(i++) & 0xff];
        } while(i < len && c1 == -1);
        if(c1 == -1)
            break;

        /* c2 */
        do {
            c2 = base64DecodeChars[str.charCodeAt(i++) & 0xff];
        } while(i < len && c2 == -1);
        if(c2 == -1)
            break;

        out += String.fromCharCode((c1 << 2) | ((c2 & 0x30) >> 4));

        /* c3 */
        do {
            c3 = str.charCodeAt(i++) & 0xff;
            if(c3 == 61)
                return out;
            c3 = base64DecodeChars[c3];
        } while(i < len && c3 == -1);
        if(c3 == -1)
            break;

        out += String.fromCharCode(((c2 & 0XF) << 4) | ((c3 & 0x3C) >> 2));

        /* c4 */
        do {
            c4 = str.charCodeAt(i++) & 0xff;
            if(c4 == 61)
                return out;
            c4 = base64DecodeChars[c4];
        } while(i < len && c4 == -1);
        if(c4 == -1)
            break;
        out += String.fromCharCode(((c3 & 0x03) << 6) | c4);
    }
    return out;
}

function utf16to8(str) {
    var out, i, len, c;

    out = "";
    len = str.length;
    for(i = 0; i < len; i++) {
        c = str.charCodeAt(i);
        if ((c >= 0x0001) && (c <= 0x007F)) {
            out += str.charAt(i);
        } else if (c > 0x07FF) {
            out += String.fromCharCode(0xE0 | ((c >> 12) & 0x0F));
            out += String.fromCharCode(0x80 | ((c >> 6) & 0x3F));
            out += String.fromCharCode(0x80 | ((c >> 0) & 0x3F));
        } else {
            out += String.fromCharCode(0xC0 | ((c >> 6) & 0x1F));
            out += String.fromCharCode(0x80 | ((c >> 0) & 0x3F));
        }
    }
    return out;
}

function utf8to16(str) {
    var out, i, len, c;
    var char2, char3;

    out = "";
    len = str.length;
    i = 0;
    while(i < len) {
        c = str.charCodeAt(i++);
        switch(c >> 4)
        {
            case 0: case 1: case 2: case 3: case 4: case 5: case 6: case 7:
            // 0xxxxxxx
            out += str.charAt(i-1);
            break;
            case 12: case 13:
            // 110x xxxx 10xx xxxx
            char2 = str.charCodeAt(i++);
            out += String.fromCharCode(((c & 0x1F) << 6) | (char2 & 0x3F));
            break;
            case 14:
                // 1110 xxxx 10xx xxxx 10xx xxxx
                char2 = str.charCodeAt(i++);
                char3 = str.charCodeAt(i++);
                out += String.fromCharCode(((c & 0x0F) << 12) |
                    ((char2 & 0x3F) << 6) |
                    ((char3 & 0x3F) << 0));
                break;
        }
    }

    return out;
}


function pluginService(_name, version, _suffix_name=''){

	var default_name = 'status';
	if ( _suffix_name != '' ){
		default_name = 'status_'+_suffix_name;
	}

	var data = {name:_name, func:default_name};
	if ( typeof(version) != 'undefined' ){
		data['version'] = version;
	} else {
		version = '';
	}

	var loadT = layer.msg('正在获取...', { icon: 16, time: 0, shade: 0.3 });
	$.post('/plugins/run', data, function(data) {
		layer.close(loadT);
        if(!data.status){
            layer.msg(data.msg,{icon:0,time:3000,shade: [0.3, '#000']});
            return;
        }
        if (data.data == 'start'){
            pluginSetService(_name, true, version, _suffix_name);
        } else {
            pluginSetService(_name, false, version, _suffix_name);
        }
    },'json');
}

function pluginSetService(_name ,status, version, _suffix_name=''){

	var default_name = 'status';
	var restart_name = 'restart';
	var reload_name = 'reload';
	var status_ss = (status?'stop':'start');
	if ( _suffix_name != '' ){
		default_name = 'status_'+_suffix_name;
		restart_name = 'restart_'+_suffix_name;
		reload_name = 'reload_'+_suffix_name;
		status_ss = status_ss+'_'+_suffix_name;
	}

	var serviceCon ='<p class="status">当前状态：<span>'+(status ? '开启' : '关闭' )+
        '</span><span style="color: '+
        (status?'#20a53a;':'red;')+
        ' margin-left: 3px;" class="glyphicon ' + (status?'glyphicon glyphicon-play':'glyphicon-pause')+'"></span></p><div class="sfm-opt">\
            <button class="btn btn-default btn-sm" onclick="pluginOpService(\''+_name+'\',\''+status_ss+'\',\''+version+'\',\''+_suffix_name+'\')">'+(status?'停止':'启动')+'</button>\
            <button class="btn btn-default btn-sm" onclick="pluginOpService(\''+_name+'\',\''+restart_name+'\',\''+version+'\',\''+_suffix_name+'\')">重启</button>\
            <button class="btn btn-default btn-sm" onclick="pluginOpService(\''+_name+'\',\''+reload_name+'\',\''+version+'\',\''+_suffix_name+'\')">重载配置</button>\
        </div>'; 
        
    if (_name.indexOf('php') !== -1) {
        serviceCon += '<div class="service-notice" style="margin-top: 20px; padding: 15px; background-color: #f8f9fa; border-left: 4px solid #20a53a; border-radius: 4px; font-size: 13px; color: #555; line-height: 1.6; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">\
            <div style="margin-bottom: 6px; font-size: 14px; color: #333; font-weight: 600;"><span class="glyphicon glyphicon-info-sign" style="margin-right: 5px; color: #20a53a;"></span>操作指引</div>\
            <div style="margin-bottom: 4px;"><b style="color:#333;">重载配置 (Reload)</b>：平滑加载最新配置。进程重新读取配置而不断开现有连接，实现<b style="color:#20a53a;">业务零中断</b>，推荐日常修改配置后使用。</div>\
            <div><b style="color:#333;">重启服务 (Restart)</b>：强制终止并重启所有进程。会导致进行中的请求（如订单提交、文件上传）瞬间中断并抛出 502 错误，仅在极少数异常恢复时使用。</div>\
        </div>';
        serviceCon += '<div style="margin-top: 20px;">\
            <button class="btn btn-danger btn-sm" onclick="pluginOpService(\''+_name+'\',\'kill_all_php\',\''+version+'\',\''+_suffix_name+'\')">kill所有php进程</button>\
            <div class="service-notice" style="margin-top: 15px; padding: 15px; background-color: #fff3f3; border-left: 4px solid #d9534f; border-radius: 4px; font-size: 13px; color: #555; line-height: 1.6; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">\
                <div><b style="color:#d9534f;">注意</b>：强制杀掉服务器上所有的 PHP-FPM 进程（包括其他正常运行的 PHP 版本）。这会中断所有 PHP 网站的访问。此功能主要用于解决面板 PHP 启动时报“端口已被占用”、“Socket冲突”等异常问题，<b style="color:red;">执行后需要手动回到各个 PHP 版本中重新点击【启动】服务。</b></div>\
            </div>\
        </div>';
    }

    $(".soft-man-con").html(serviceCon);
}


function pluginOpService(a, b, v, _suffix_name='') {

    var c = "name=" + a + "&func=" + b;
    if(v != ''){
    	c = c + '&version='+v;
    }

    var d = "";

    b = b.split('_')[0];
    switch(b) {
        case "stop":d = '停止';break;
        case "start":d = '启动';break;
        case "restart":d = '重启';break;
        case "reload":d = '重载';break;
        case "kill":d = '强制停止(kill)';break;
    }

    _ver = v;
    if(v != ''){
    	_ver = '【' + v + '】';
    }

    layer.confirm( msgTpl('您真的要{1}{2}{3}服务吗？', [d,a,_ver]), {
    	area: ['400px','auto'],
    	icon: 3, 
    	closeBtn: 1
    }, function() {
        var e = layer.msg(msgTpl('正在{1}{2}{3}服务,请稍候...',[d,a,_ver]), {area: ['400px','auto'],icon: 16,time: 0});
        $.post("/plugins/run", c, function(g) {
            layer.close(e);
            
            var f = g.data == 'ok' ? msgTpl('{1}{2}服务已{3}',[a,_ver,d],{area: ['400px','auto'],time: 0}) : msgTpl('{1}{2}服务{3}失败!',[a,_ver,d],{area: ['400px','auto'],time: 0});
            layer.msg(f, {icon: g.data == 'ok' ? 1 : 2});
            
            if( b != "reload" && g.data == 'ok' ) {
                if ( b == 'start' ) {
                    pluginSetService(a, true, v, _suffix_name);
                } else if ( b == 'stop' ){
                    pluginSetService(a, false, v, _suffix_name);
                }
            }

            if( g.status && g.data != 'ok' ) {
                layer.msg(g.data, {icon: 2,time: 6000,shade: 0.3,shadeClose: true});
            }

            var checkCount = 0;
            var checkInterval = setInterval(function(){
                if (typeof getSList === 'function' && $("#softList").length > 0) {
                    getSList(true);
                }
                if (typeof indexListHtml === 'function' && $("#indexsoft").length > 0) {
                    indexListHtml();
                }
                checkCount++;
                if (checkCount >= 5) {
                    clearInterval(checkInterval);
                }
            }, 2000);
        },'json').fail(function() {
            layer.close(e);
            layer.msg('操作异常!', {icon: 1});
        });
    })
}

//配置修改 --- start
function pluginConfig(_name, version, func){
	if ( typeof(version) == 'undefined' ){
		version = '';
	}

	var func_name = 'conf';
    if ( typeof(func) != 'undefined' ){
        func_name = func;
    }

    var con = '<p style="color: #666; margin-bottom: 7px">提示：Ctrl+F 搜索关键字，Ctrl+G 查找下一个，Ctrl+S 保存，Ctrl+H 查找替换!</p>\
    			<textarea class="bt-input-text" style="height: 320px; line-height:18px;" id="textBody"></textarea>\
                <button id="onlineEditFileBtn" class="btn btn-success btn-sm" style="margin-top:10px;">保存</button>\
                <ul class="help-info-text c7 ptb15">\
                    <li>此处为'+ _name + version +'主配置文件,若您不了解配置规则,请勿随意修改。</li>\
                </ul>';


    var loadT = layer.msg('配置文件路径获取中...',{icon:16,time:0,shade: [0.3, '#000']});
    var editor;
    $.post('/plugins/run', {name:_name, func:func_name,version:version},function (data) {
        layer.close(loadT);

        try{
        	var jdata = JSON.parse(data.data);
        	if (!jdata['status']){
        		layer.msg(jdata.msg,{icon:0,time:2000,shade: [0.3, '#000']});
                return;
        	}
		}catch(err){/*console.log(err);*/}

		$(".soft-man-con").html(con);
		
        var loadT2 = layer.msg('文件内容获取中...',{icon:16,time:0,shade: [0.3, '#000']});
        var fileName = data.data;
        $.post('/files/get_body', 'path=' + fileName, function(rdata) {
            layer.close(loadT2);
            if (!rdata.status){
                layer.msg(rdata.msg,{icon:0,time:2000,shade: [0.3, '#000']});
                return;
            }
            $("#textBody").empty().text(rdata.data.data);
            $(".CodeMirror").remove();

            function saveDataFunc(){
		    	$("#textBody").text(editor.getValue());
		        pluginConfigSave(fileName);
		    }
            
            editor = CodeMirror.fromTextArea(document.getElementById("textBody"), {
            	lineNumbers: true,
                matchBrackets:true,
                extraKeys: {
                    "Ctrl-Space": "autocomplete",
                    "Ctrl-F": function(cm){ showAdvancedSearchDialog(cm, false); },
                    "Ctrl-H": function(cm){ showAdvancedSearchDialog(cm, true); },
                    "Ctrl-S": function() {
                    	saveDataFunc();
                    },
                    "Cmd-S":function() {
						saveDataFunc();
					}
                }
            });
            editor.focus();
            $(".CodeMirror-scroll").css({"height":"300px","margin":0,"padding":0});
            $("#onlineEditFileBtn").on('click', function(){
                saveDataFunc();
            });
        },'json');
    },'json');
}


//配置修改模版 --- start
function pluginConfigTpl(_name, version, func, config_tpl_func, read_config_tpl_func, save_callback_func){
	if ( typeof(version) == 'undefined' ){
		version = '';
	}

	var func_name = 'conf';
    if ( typeof(func) != 'undefined' ){
        func_name = func;
    }

    var _config_tpl_func = 'config_tpl';
    if ( typeof(config_tpl_func) != 'undefined' ){
        _config_tpl_func = config_tpl_func;
    }

    var _read_config_tpl_func = 'read_config_tpl';
    if ( typeof(read_config_tpl_func) != 'undefined' ){
        _read_config_tpl_func = read_config_tpl_func;
    }


    var con = '<p style="color: #666; margin-bottom: 7px">提示：Ctrl+F 搜索关键字，Ctrl+G 查找下一个，Ctrl+S 保存，Ctrl+H 查找替换!</p>\
    			<select id="config_tpl" class="bt-input-text mr20" style="width:30%;margin-bottom: 3px;"><option value="0">请选择</option></select>\
    			<textarea class="bt-input-text" style="height: 320px; line-height:18px;" id="textBody"></textarea>\
                <button id="onlineEditFileBtn" class="btn btn-success btn-sm" style="margin-top:10px;">保存</button>\
                <ul class="help-info-text c7 ptb15">\
                    <li>此处为【'+ _name + version +'】主配置文件,若您不了解配置规则,请勿随意修改。</li>\
                </ul>';
    $(".soft-man-con").html(con);

    function getFileName(file){
    	var list = file.split('/');
    	var f = list[list.length-1];
    	return f 
    }

    var editor;
    function saveDataFunc(){
    	$("#textBody").text(editor.getValue());
        pluginConfigSave(fileName,save_callback_func);
    }


    var fileName = '';
    $.post('/plugins/run',{name:_name, func:_config_tpl_func,version:version}, function(data){
    	var rdata = JSON.parse(data.data);
    	for (var i = 0; i < rdata.length; i++) {
    		$('#config_tpl').append('<option value="'+rdata[i]+'"">'+getFileName(rdata[i])+'</option>');
    	}

    	$('#config_tpl').on('change', function(){
    		var selected = $(this).val();
    		if (selected != '0'){
    			var loadT = layer.msg('配置模版获取中...',{icon:16,time:0,shade: [0.3, '#000']});

    			var _args = JSON.stringify({file:selected});

    			
    			$.post('/plugins/run', {name:_name, func:_read_config_tpl_func,version:version,args:_args}, function(data){
    				layer.close(loadT);
    				var rdata = JSON.parse(data.data);
    				if (!rdata.status){
		                layer.msg(rdata.msg,{icon:0,time:2000,shade: [0.3, '#000']});
		                return;
		            }

		            

    				$("#textBody").empty().text(rdata.data);
    				$(".CodeMirror").remove();
		            editor = CodeMirror.fromTextArea(document.getElementById("textBody"), {
		            	lineNumbers: true,
		                matchBrackets:true,
		                extraKeys: {
		                    "Ctrl-Space": "autocomplete",
		                    "Ctrl-F": function(cm){ showAdvancedSearchDialog(cm, false); },
		                    "Ctrl-H": function(cm){ showAdvancedSearchDialog(cm, true); },
		                    "Ctrl-S": function() {
		                    	saveDataFunc();
		                    },
		                    "Cmd-S":function() {
								saveDataFunc();
							}
		                }
		            });
		            editor.focus();
		            $(".CodeMirror-scroll").css({"height":"300px","margin":0,"padding":0});
		            $("#onlineEditFileBtn").off('click').on('click', function(){
		                saveDataFunc();
		            });
    			},'json');
    		}
    	});

    },'json');

    var loadT = layer.msg('配置文件路径获取中...',{icon:16,time:0,shade: [0.3, '#000']});
    $.post('/plugins/run', {name:_name, func:func_name,version:version}, function (data) {
        layer.close(loadT);

        var loadT2 = layer.msg('文件内容获取中...',{icon:16,time:0,shade: [0.3, '#000']});
        fileName = data.data;
        $.post('/files/get_body', 'path=' + fileName, function(rdata) {
            layer.close(loadT2);
            if (!rdata.status){
                layer.msg(rdata.msg,{icon:0,time:2000,shade: [0.3, '#000']});
                return;
            }
            $("#textBody").empty().text(rdata.data.data);
            $(".CodeMirror").remove();
            editor = CodeMirror.fromTextArea(document.getElementById("textBody"), {
                extraKeys: {
                    "Ctrl-Space": "autocomplete",
                    "Ctrl-F": "findPersistent",
                    "Ctrl-H": "replaceAll",
                    "Ctrl-S": function() {
                    	saveDataFunc();
                    },
                    "Cmd-S":function() {
						saveDataFunc();
					}
                },
                lineNumbers: true,
                matchBrackets:true,
            });
            editor.focus();
            $(".CodeMirror-scroll").css({"height":"300px","margin":0,"padding":0});
            $("#onlineEditFileBtn").on('click', function(){
                saveDataFunc();
            });
        },'json');
    },'json');
}

//配置模版列表 --- start
function pluginConfigListTpl(_name, version, config_tpl_func, read_config_tpl_func){
	if ( typeof(version) == 'undefined' ){
		version = '';
	}

    var _config_tpl_func = 'config_tpl';
    if ( typeof(config_tpl_func) != 'undefined' ){
        _config_tpl_func = config_tpl_func;
    }

    var _read_config_tpl_func = 'read_config_tpl';
    if ( typeof(read_config_tpl_func) != 'undefined' ){
        _read_config_tpl_func = read_config_tpl_func;
    }


    var con = '<p style="color: #666; margin-bottom: 7px">提示：Ctrl+F 搜索关键字，Ctrl+G 查找下一个，Ctrl+S 保存，Ctrl+H 查找替换!</p>\
    			<select id="config_tpl" class="bt-input-text mr20" style="width:30%;margin-bottom: 3px;"></select>\
    			<textarea class="bt-input-text" style="height: 320px; line-height:18px;" id="textBody"></textarea>\
                <button id="onlineEditFileBtn" class="btn btn-success btn-sm" style="margin-top:10px;">保存</button>\
                <ul class="help-info-text c7 ptb15">\
                    <li>此处为'+ _name + version +'主配置文件,若您不了解配置规则,请勿随意修改。</li>\
                </ul>';
    $(".soft-man-con").html(con);

    function getFileName(file){
    	var list = file.split('/');
    	var f = list[list.length-1];
    	return f 
    }

    var editor;
    function saveDataFunc(){
    	$("#textBody").text(editor.getValue());
        pluginConfigSave(fileName);
    }

    function loadTextBody(fileName){
        $.post('/files/get_body', 'path=' + fileName, function(rdata) {
            if (!rdata.status){
                layer.msg(rdata.msg,{icon:0,time:2000,shade: [0.3, '#000']});
                return;
            }
            $("#textBody").empty().text(rdata.data.data);
            $(".CodeMirror").remove();
            editor = CodeMirror.fromTextArea(document.getElementById("textBody"), {
                extraKeys: {
                    "Ctrl-Space": "autocomplete",
                    "Ctrl-F": function(cm){ showAdvancedSearchDialog(cm, false); },
                    "Ctrl-H": function(cm){ showAdvancedSearchDialog(cm, true); },
                    "Ctrl-S": function() {
                    	saveDataFunc();
                    },
                    "Cmd-S": function() {
                    	saveDataFunc();
                    }
                },
                lineNumbers: true,
                matchBrackets:true,
            });
            editor.focus();
            $(".CodeMirror-scroll").css({"height":"300px","margin":0,"padding":0});
            $("#onlineEditFileBtn").on('click', function(){
                saveDataFunc();
            });
        },'json');
    }



    var fileName = '';
    $.post('/plugins/run',{name:_name, func:_config_tpl_func,version:version}, function(data){
    	var rdata = JSON.parse(data.data);
    	for (var i = 0; i < rdata.length; i++) {
    		$('#config_tpl').append('<option value="'+rdata[i]+'">'+getFileName(rdata[i])+'</option>');
    	}

    	if (rdata.length>0){
    		loadTextBody(rdata[0]);
    	}

    	$('#config_tpl').on('change', function(){
    		var selected = $(this).val();
    		fileName = selected;
    
			var loadT = layer.msg('配置模版获取中...',{icon:16,time:0,shade: [0.3, '#000']});

			var _args = JSON.stringify({file:selected});
			$.post('/plugins/run', {name:_name, func:_read_config_tpl_func,version:version,args:_args}, function(data){
				layer.close(loadT);
				var rdata = JSON.parse(data.data);
				if (!rdata.status){
	                layer.msg(rdata.msg,{icon:0,time:2000,shade: [0.3, '#000']});
	                return;
	            }

				$("#textBody").empty().text(rdata.data);
				$(".CodeMirror").remove();
	            editor = CodeMirror.fromTextArea(document.getElementById("textBody"), {
	                extraKeys: {
	                    "Ctrl-Space": "autocomplete",
	                    "Ctrl-F": "findPersistent",
	                    "Ctrl-H": "replaceAll",
	                    "Ctrl-S": function() {
	                    	saveDataFunc();
	                    },
		                "Cmd-S":function() {
							saveDataFunc();
						}
	                },
	                lineNumbers: true,
	                matchBrackets:true,
	            });
	            editor.focus();
	            $(".CodeMirror-scroll").css({"height":"300px","margin":0,"padding":0});
	            $("#onlineEditFileBtn").off('click').on('click', function(){
	                saveDataFunc();
	            });
			},'json');
    		
    	});

    },'json');
}


//配置保存
function pluginConfigSave(fileName, callback) {
    var data = encodeURIComponent($("#textBody").val());
    var encoding = 'utf-8';
    var loadT = layer.msg('保存中...', {icon: 16,time: 0});
    $.post('/files/save_body', 'data=' + data + '&path=' + fileName + '&encoding=' + encoding, function(rdata) {
        layer.close(loadT);

        showMsg(rdata.msg, function(){
        	if ( rdata.status && typeof(callback) == 'function'){
	        	callback();
	        }
        },{icon: rdata.status ? 1 : 2});
     
    },'json');
}

function pluginInitD(_name, _version, _suffix_name=''){
	if (typeof _version == 'undefined'){
    	_version = '';
    }

    var default_name = 'initd_status';
	if ( _suffix_name != '' ){
		default_name = 'initd_status_'+_suffix_name;
	}

	var loadT = layer.msg('正在获取...', { icon: 16, time: 0, shade: 0.3 });
	$.post('/plugins/run', {name:_name, func:default_name, version : _version}, function(data) {
		layer.close(loadT);
        if( !data.status ){
            layer.msg(data.msg,{icon:0,time:3000,shade: [0.3, '#000']});
            return;
        }
        if( data.data!='ok' && data.data!='fail' ){
            layer.msg(data.data,{icon:0,time:3000,shade: [0.3, '#000']});
            return;
        }
        if (data.data == 'ok'){
            pluginSetInitD(_name, _version, true, _suffix_name);
        } else {
            pluginSetInitD(_name, _version, false, _suffix_name);
        }
    },'json');
}

function pluginSetInitD(_name, _version, status,_suffix_name=''){

	var default_name = (status?'initd_uninstall':'initd_install');
	if ( _suffix_name != '' ){
		default_name = default_name + '_' + _suffix_name;
	}

	var serviceCon ='<p class="status">当前状态：<span>'+(status ? '已加载' : '未加载' )+
        '</span><span style="color: '+
        (status?'#20a53a;':'red;')+
        ' margin-left: 3px;" class="glyphicon ' + (status?'glyphicon glyphicon-play':'glyphicon-pause')+'"></span></p><div class="sfm-opt">\
            <button class="btn btn-default btn-sm" onclick="pluginOpInitD(\''+_name+'\',\''+_version+'\',\''+default_name+'\',\''+_suffix_name+'\')">'+(status?'卸载':'加载')+'</button>\
        </div>'; 
    $(".soft-man-con").html(serviceCon);
}

function pluginOpInitD(a, _version, b, _suffix_name='') {
    var c = "name=" + a + "&func=" + b + "&version="+_version;
    var d = "";
    b = b.split('_'+_suffix_name)[0];
    switch(b) {
        case "initd_install":d = '加载';break;
        case "initd_uninstall":d = '卸载';break;
    }

    _ver = _version;
    if(_version != ''){
    	_ver = '【' + _version + '】';
    }

    layer.confirm( msgTpl('您真的要{1}{2}{3}服务吗？', [d,a,_ver]), {icon:3,closeBtn: 1}, function() {
        var e = layer.msg(msgTpl('正在{1}{2}{3}服务,请稍候...',[d,a,_ver]), {icon: 16,time: 0});
        $.post("/plugins/run", c, function(g) {
            layer.close(e);
            var f = g.data == 'ok' ? msgTpl('{1}{3}服务已{2}',[a,d,_ver]) : msgTpl('{1}{3}服务{2}失败!',[a,d,_ver]);
            layer.msg(f, {icon: g.data == 'ok' ? 1 : 2});
            
            if ( b == 'initd_install' && g.data == 'ok' ) {
                pluginSetInitD(a, _version, true);
            }else{
                pluginSetInitD(a, _version, false);
            }
            if(g.data != 'ok') {
                layer.msg(g.data, {icon: 2,time: 0,shade: 0.3,shadeClose: true});
            }
        },'json').fail(function() {
            layer.close(e);
            layer.msg('系统异常!', {icon: 0});
        });
    })
}

function pluginLogs(_name, version, func, line){

	var _this = this;
    if ( typeof(version) == 'undefined' ){
        version = '';
    }

    var func_name = 'error_log';
    if ( typeof(func) != 'undefined' ){
        func_name = func;
    }

    var file_line = 100;
    if ( typeof(line) != 'undefined' ){
        file_line = line;
    }


    var loadT = layer.msg('日志路径获取中...',{icon:16,time:0,shade: [0.3, '#000']});
    $.post('/plugins/run', {name:_name, func:func_name, version:version},function (data) {
        layer.close(loadT);

        try{
        	var jdata = JSON.parse(data.data);
        	if (!jdata['status']){
        		layer.msg(jdata.msg,{icon:0,time:2000,shade: [0.3, '#000']});
                return;
        	}
		}catch(err){/*console.log(err);*/}


        var loadT2 = layer.msg('文件内容获取中...',{icon:16,time:0,shade: [0.3, '#000']});
        var fileName = data.data;
        $.post('/files/get_last_body', 'path=' + fileName+'&line='+file_line, function(rdata) {
            layer.close(loadT2);
            if (!rdata.status){
                layer.msg(rdata.msg,{icon:0,time:2000,shade: [0.3, '#000']});
                return;
            }
            
            if(rdata.data == '') {
            	rdata.data = '当前没有日志!';
            }

     
            var h =  parseInt($('.bt-w-menu').css('height')) - 40;
            var ebody = '<textarea readonly="" style="margin: 0px;height: '+h+'px;width: 100%;background-color: #333;color:#fff; padding:0 5px" id="info_log">'+rdata.data+'</textarea>';
            $(".soft-man-con").html(ebody);
            var ob = document.getElementById('info_log');
            ob.scrollTop = ob.scrollHeight; 
        },'json');
    },'json');
}


function pluginRollingLogs(_name, version, func, _args, line){
	if ( typeof(version) == 'undefined' ){
        version = '';
    }

    var func_name = 'error_log';
    if ( typeof(func) != 'undefined' ){
        func_name = func;
    }

    var file_line = 100;
    if ( typeof(line) != 'undefined' ){
        file_line = line;
    }

    var reqTimer = null;

    function requestLogs(fileName){
    	$.post('/files/get_last_body', 'path=' + fileName+'&line='+file_line, function(rdata) {
            if (!rdata.status){   
                return;
            }
            
            if(rdata.data == '') {
            	rdata.data = '当前没有日志!';
            }
            var ebody = '<textarea readonly="readonly" style="margin: 0px;width: 100%;height: 360px;background-color: #333;color:#fff; padding:0 5px" id="roll_info_log">'+rdata.data+'</textarea>';
            $("#plugins_rolling_logs").html(ebody);
            var ob = document.getElementById('roll_info_log');
            ob.scrollTop = ob.scrollHeight; 
        },'json');
    }


    layer.open({
        type: 1,
        title: _name + '日志',
        area: '640px',
        end: function(){
        	if (reqTimer){
        		clearInterval(reqTimer);
        	}
        },
        content:'<div class="change-default pd20" id="plugins_rolling_logs">\
        	<textarea readonly="readonly" style="margin: 0px;width: 100%;height: 360px;background-color: #333;color:#fff; padding:0 5px" id="roll_info_log"></textarea>\
        </div>',
        success:function(){
        	$.post('/plugins/run', {name:_name, func:func_name, version:version, args:_args},function (data) {
		    	var fileName = data.data;
		    	requestLogs(fileName);
		    	reqTimer = setInterval(function(){
		    		requestLogs(fileName);
		    	},1000);
		    },'json');
        }
    });
}


function pluginStandAloneLogs(_name, version, func, _args, line){
	if ( typeof(version) == 'undefined' ){
        version = '';
    }

    var func_name = 'error_log';
    if ( typeof(func) != 'undefined' ){
        func_name = func;
    }

    var file_line = 100;
    if ( typeof(line) != 'undefined' ){
        file_line = line;
    }


    layer.open({
        type: 1,
        title: _name + '日志',
        area: '640px',
        content:'<div class="change-default pd20" id="plugins_stand_alone_logs">\
        	<textarea readonly="readonly" style="margin: 0px;width: 100%;height: 360px;background-color: #333;color:#fff; padding:0 5px"></textarea>\
        	</div>'
    });

    $.post('/plugins/run', {name:_name, func:func_name, version:version,args:_args},function (data) {
    	var fileName = data.data;
		$.post('/files/get_last_body', 'path=' + fileName+'&line='+file_line, function(rdata) {
            if (!rdata.status){   
                return;
            }
            
            if(rdata.data == '') {
            	rdata.data = '当前没有日志!';
            }
            var ebody = '<textarea readonly="" style="margin: 0px;width: 100%;height: 360px;background-color: #333;color:#fff; padding:0 5px">'+rdata.data+'</textarea>';
            $("#plugins_stand_alone_logs").html(ebody);
            var ob = document.getElementById('plugins_stand_alone_logs');
            ob.scrollTop = ob.scrollHeight; 
        },'json');
    },'json');
}
/*** 其中功能,针对插件通过库使用 end ***/

$(function() {
	setInterval(function(){check_login();},6000);
	autoHeight();
});
$(window).on('resize', function() {
	autoHeight();
});
function aboutPanel() {
    var loadT = layer.msg('正在获取说明...', { icon: 16, time: 0, shade: 0.3 });
    $.get('/system/get_release_info', function(rdata) {
        layer.close(loadT);
        if (!rdata.status) {
            layer.msg(rdata.msg, { icon: 2 });
            return;
        }
        
        var content = rdata.data;
        var renderContent = function() {
            var htmlContent = '';
            try {
                htmlContent = marked.parse(content);
            } catch (e) {
                htmlContent = '<pre>' + content + '</pre>';
            }
            return htmlContent;
        };

        var showRelease = function(htmlContent) {
        
        layer.open({
            type: 1,
            title: false,
            closeBtn: 0,
            area: ['850px', '812px'],
            shadeClose: true,
            content: '<div class=\"about-container\" style=\"position: relative; padding-top: 5px;\">' +
                        '<div class=\"about-close\" style=\"position: absolute; top: 15px; right: 20px; cursor: pointer; color: #999; font-size: 24px; font-weight: normal; transition: color 0.3s; line-height: 1;\" onmouseover=\"this.style.color=\'#333\'\" onmouseout=\"this.style.color=\'#999\'\" onclick=\"layer.closeAll(\'page\')\">×</div>' +
                        '<div class=\"about-header\" style=\"padding-top: 10px;\">' +
                            '<img src=\"/static/img/logo.webp\" style=\"width: 160px; margin-bottom: 5px;\">' +
                            '<h2 style=\"margin-top: 5px;\">御风面板（BtSimple）</h2>' +
                            '<p><a href=\"https://www.yftec.top\" target=\"_blank\" class=\"btlink\" style=\"font-weight: bold;\">衢州御风科技有限公司</a> 荣誉出品</p>' +
                            '<div id=\"panel_resource_info\" style=\"margin-top: 15px; height: 30px; line-height: 30px; margin-bottom: 10px;\"></div>' +
                        '</div>' +
                        '<div class=\"about-content markdown-body\" style=\"padding-top: 0;\">' + htmlContent + '</div>' +
                        '<div class=\"about-footer\">' +
                            '<p>&copy; 2026 <a href=\"https://www.yftec.top\" target=\"_blank\" class=\"btlink\">衢州御风科技 (YFTEC)</a> 版权所有 | admin@yftec.top</p>' +
                        '</div>' +
                     '</div>',
            success: function() {
                setTimeout(function() {
                    $('#panel_resource_info').html('<span style=\"font-size: 13px; color: #666;\"><img src=\"/static/img/loading.gif\" style=\"width:14px; vertical-align:middle; margin-right:5px;\" onerror=\"this.style.display=\'none\'\">正在获取面板占用资源...</span>');
                    $.get('/system/get_panel_resources', function(res) {
                        if (res.status) {
                            var resHtml = '<div style=\"display:inline-block; border-top: 1px solid #eaeaea; border-bottom: 1px solid #eaeaea; padding: 0 15px; font-size: 13px; background-color: #fcfcfc; border-radius: 2px;\">' +
                                          '<span style=\"color:#666; margin-right: 15px;\">御风面板当前占用服务器资源：</span>' +
                                          '<span><i class=\"glyphicon glyphicon-tasks\" style=\"margin-right:4px; font-size:12px; color: #888;\"></i>CPU <b style=\"color:#20a53a; font-family: \'Inter\', sans-serif;\">' + res.data.cpu + '%</b></span>' +
                                          '<span style=\"color:#ddd; margin: 0 15px;\">|</span>' + 
                                          '<span><i class=\"glyphicon glyphicon-hdd\" style=\"margin-right:4px; font-size:12px; color: #888;\"></i>内存 <b style=\"color:#20a53a; font-family: \'Inter\', sans-serif;\">' + res.data.mem + ' MB</b></span>' +
                                          '</div>';
                            $('#panel_resource_info').html(resHtml);
                        } else {
                            $('#panel_resource_info').html('<span style=\"color: red;\">获取资源失败</span>');
                        }
                    }, 'json');
                }, 1000);
            }
        });
        };

        // 按需加载 marked（如果已全局可用则直接用，否则动态加载）
        if (typeof marked !== 'undefined') {
            showRelease(renderContent());
        } else {
            loadScript(staticUrl('/static/js/marked.min.js')).then(function() {
                showRelease(renderContent());
            }).catch(function() {
                showRelease('<pre>' + content + '</pre>');
            });
        }
    }, 'json');
}

function toggleMenuMini() {
    var body = document.body;
    var isMini = body.classList.toggle('sidebar-mini');
    localStorage.setItem('menuMini', isMini);
}
function showAdvancedSearchDialog(cm, isReplaceMode) {
    if (cm.state.advSearch) {
        if (isReplaceMode && !cm.state.advSearch.isReplaceMode) {
            cm.state.advSearch.replaceRow.style.display = 'flex';
            cm.state.advSearch.isReplaceMode = true;
        }
        cm.state.advSearch.searchInput.focus();
        return;
    }
    var wrapper = cm.getWrapperElement();
    var dialog = document.createElement('div');
    dialog.className = 'cm-advanced-search-dialog';
    dialog.style.cssText = 'position: absolute; top: 15px; right: 30px; z-index: 999; background: #fff; padding: 12px; border: 1px solid #ddd; box-shadow: 0 4px 12px rgba(0,0,0,0.15); border-radius: 4px; font-size: 13px; width: 320px; transition: all 0.2s;';
    var html = '<div style=\'display: flex; align-items: center; margin-bottom: 8px;\'>' +
        '<input type=\'text\' class=\'cm-search-input bt-input-text\' placeholder=\'查找内容...\' style=\'height: 28px; line-height: 28px; padding: 0 8px; flex: 1; margin-right: 5px; min-width: 0;\'>' +
        '<button type=\'button\' class=\'btn btn-default btn-sm cm-search-prev\' style=\'padding: 4px 8px; margin-left: 2px;\' title=\'上一个\'><i class=\'glyphicon glyphicon-chevron-up\'></i></button>' +
        '<button type=\'button\' class=\'btn btn-default btn-sm cm-search-next\' style=\'padding: 4px 8px; margin-left: 2px;\' title=\'下一个\'><i class=\'glyphicon glyphicon-chevron-down\'></i></button>' +
        '<button type=\'button\' class=\'btn btn-default btn-sm cm-search-close\' style=\'padding: 4px 8px; margin-left: 5px;\' title=\'关闭\'><i class=\'glyphicon glyphicon-remove\'></i></button>' +
    '</div>' +
    '<div class=\'cm-replace-row\' style=\'display: ' + (isReplaceMode ? 'flex' : 'none') + '; align-items: center;\'>' +
        '<input type=\'text\' class=\'cm-replace-input bt-input-text\' placeholder=\'替换为...\' style=\'height: 28px; line-height: 28px; padding: 0 8px; flex: 1; margin-right: 5px; min-width: 0;\'>' +
        '<button type=\'button\' class=\'btn btn-default btn-sm cm-replace-btn\' style=\'padding: 4px 8px; margin-left: 2px;\' title=\'替换当前\'>替换</button>' +
        '<button type=\'button\' class=\'btn btn-default btn-sm cm-replace-all-btn\' style=\'padding: 4px 8px; margin-left: 2px;\' title=\'替换全部\'>全部</button>' +
    '</div>' +
    '<div class=\'cm-search-info\' style=\'font-size: 12px; color: #999; margin-top: 5px; height: 16px;\'></div>';
    dialog.innerHTML = html;
    wrapper.appendChild(dialog);
    var searchInput = dialog.querySelector('.cm-search-input');
    var replaceInput = dialog.querySelector('.cm-replace-input');
    var replaceRow = dialog.querySelector('.cm-replace-row');
    var infoText = dialog.querySelector('.cm-search-info');
    var state = { isReplaceMode: isReplaceMode, replaceRow: replaceRow, searchInput: searchInput, lastQuery: null, overlay: null };
    cm.state.advSearch = state;
    function getQuery() { return searchInput.value; }
    function clearOverlay() {
        if (state.overlay) { cm.removeOverlay(state.overlay); state.overlay = null; }
    }
    function searchOverlay(query) {
        if (typeof query == 'string') query = new RegExp(query.replace(/[\-\[\]\/\{\}\(\)\*\+\?\.\\\^\$\|]/g, '\\$&'), 'gi');
        return {
            token: function(stream) {
                query.lastIndex = stream.pos;
                var match = query.exec(stream.string);
                if (match && match.index == stream.pos) {
                    stream.pos += match[0].length || 1;
                    return 'searching';
                } else if (match) {
                    stream.pos = match.index;
                } else {
                    stream.skipToEnd();
                }
            }
        };
    }
    function updateMatchCount(pos) {
        var query = getQuery();
        if (!query) { infoText.innerText = '0 / 0'; clearOverlay(); return; }
        if (query !== state.lastQuery) {
            clearOverlay();
            state.overlay = searchOverlay(query);
            cm.addOverlay(state.overlay);
            state.lastQuery = query;
        }
        var cursor = cm.getSearchCursor(query, CodeMirror.Pos(cm.firstLine(), 0), false);
        var total = 0, current = 0;
        while(cursor.findNext()) {
            total++;
            if (current === 0 && CodeMirror.cmpPos(cursor.from(), pos) >= 0) { current = total; }
        }
        if (total > 0) { infoText.innerText = (current || 1) + ' / ' + total; } else { infoText.innerText = '未找到匹配项'; }
    }
    function findNext(reverse) {
        var query = getQuery();
        if (!query) return;
        var cursor = cm.getSearchCursor(query, reverse ? cm.getCursor('from') : cm.getCursor('to'), false);
        if (reverse ? !cursor.findPrevious() : !cursor.findNext()) {
            cursor = cm.getSearchCursor(query, reverse ? CodeMirror.Pos(cm.lastLine()) : CodeMirror.Pos(cm.firstLine(), 0), false);
            if (reverse ? !cursor.findPrevious() : !cursor.findNext()) return;
        }
        cm.setSelection(cursor.from(), cursor.to());
        cm.scrollIntoView({from: cursor.from(), to: cursor.to()}, 20);
        updateMatchCount(cursor.from());
    }
    function replaceNext() {
        var query = getQuery();
        if (!query) return;
        var replacement = replaceInput.value;
        var cursor = cm.getSearchCursor(query, cm.getCursor('from'), false);
        if (cursor.findNext()) {
            var selection = cm.getSelection();
            if (selection.toLowerCase() === query.toLowerCase()) {
                cursor.replace(replacement);
                findNext(false);
            } else {
                findNext(false);
            }
        }
    }
    function replaceAll() {
        var query = getQuery();
        if (!query) return;
        var replacement = replaceInput.value;
        cm.operation(function() {
            var cursor = cm.getSearchCursor(query, CodeMirror.Pos(cm.firstLine(), 0), false);
            while(cursor.findNext()) { cursor.replace(replacement); }
        });
        updateMatchCount(cm.getCursor('from'));
    }
    function closeDialog() {
        clearOverlay();
        if (dialog.parentNode) dialog.parentNode.removeChild(dialog);
        delete cm.state.advSearch;
        cm.focus();
    }
    dialog.querySelector('.cm-search-next').onclick = function() { findNext(false); };
    dialog.querySelector('.cm-search-prev').onclick = function() { findNext(true); };
    dialog.querySelector('.cm-replace-btn').onclick = function() { replaceNext(); };
    dialog.querySelector('.cm-replace-all-btn').onclick = function() { replaceAll(); };
    dialog.querySelector('.cm-search-close').onclick = function() { closeDialog(); };
    searchInput.onkeyup = function(e) {
        if (e.keyCode === 13) findNext(e.shiftKey);
        else if (e.keyCode === 27) closeDialog();
        else updateMatchCount(cm.getCursor('from'));
    };
    replaceInput.onkeyup = function(e) {
        if (e.keyCode === 13) replaceNext();
        else if (e.keyCode === 27) closeDialog();
    };
    var selection = cm.getSelection();
    if (selection && selection.indexOf('\n') === -1) {
        searchInput.value = selection;
        updateMatchCount(cm.getCursor('from'));
    }
    searchInput.focus();
}
