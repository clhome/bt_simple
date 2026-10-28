/**
 * 回归探针：/files/get_dir 返回「非目录列表」时，Files 页面的 success 回调必须不炸。
 *
 * 背景（真机现象）：
 *   面包屑 /www/server/yufeng_panel -> 点上层的 www 或 server，后端 safePath 拒绝
 *   （_SENSITIVE_EXACT 里就有 /www、/www/server），get_dir 回的是
 *   {status:false, msg:'FILE_DANGER'} —— 没有 dir / files / page。
 *   旧版回调直接往下走，第一处 rdata.files.length 抛
 *     Uncaught TypeError: Cannot read properties of undefined (reading 'length')
 *   loading 已经关了、列表还停在上一个目录，用户只看到控制台红字。
 *
 * 做法：把 files.js 里那段 ajax success 回调按花括号配对整段抠出来，塞进 vm 里跑，
 * 用真实的失败 payload / 残缺 payload 直接调用，断言：
 *   1) 不抛异常；
 *   2) 失败时走提示分支（layer.msg 收到服务端 msg，且 msg 被 HTML 转义）；
 *   3) 残缺 payload 被规整成空数组（下表不炸）。
 *
 * 输出：最后一行 `OK` 或 `FAIL: ...`，退出码 0/1（Python 用例据此断言）。
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const filesJsPath = path.join(__dirname, '..', '..', 'web', 'static', 'app', 'files.js');
const src = fs.readFileSync(filesJsPath, 'utf8');

const MARKER = "$.post('/files/get_dir', post, function(rdata) {";

function extractCallback(text) {
    const startMarker = text.indexOf(MARKER);
    if (startMarker === -1) {
        throw new Error('files.js 里找不到 getFiles 的 get_dir 请求（marker 变了？）');
    }
    // 从 function(rdata) 之后的 `{` 开始做括号配对（引号 / 注释感知，避免被模板串里的 { } 骗）
    let i = text.indexOf('{', startMarker + MARKER.length - 1);
    const bodyStart = i;
    let depth = 0;
    let quote = null;
    for (; i < text.length; i++) {
        const ch = text[i];
        const next = text[i + 1];
        if (quote) {
            if (ch === '\\') { i++; continue; }
            if (ch === quote) quote = null;
            continue;
        }
        if (ch === '/' && next === '/') {
            const nl = text.indexOf('\n', i);
            i = nl === -1 ? text.length : nl;
            continue;
        }
        if (ch === '/' && next === '*') {
            const end = text.indexOf('*/', i + 2);
            i = end === -1 ? text.length : end + 1;
            continue;
        }
        if (ch === '"' || ch === "'" || ch === '`') { quote = ch; continue; }
        if (ch === '{') { depth++; continue; }
        if (ch === '}') {
            depth--;
            if (depth === 0) {
                return text.slice(bodyStart + 1, i);
            }
        }
    }
    throw new Error('回调体括号不配对');
}

const body = extractCallback(src);

function anyStub() {
    const fn = function () { return anyStub(); };
    return new Proxy(fn, {
        get: function (target, key) {
            if (key === 'length') return 0;
            if (key === Symbol.toPrimitive) return function () { return ''; };
            if (key === 'toString') return function () { return ''; };
            return anyStub();
        },
        apply: function () { return anyStub(); }
    });
}

function makeSandbox() {
    const log = { msgs: [], closed: [] };
    const jq = function () { return anyStub(); };
    jq.post = function (url, data, cb) { log.posted = { url: url, data: data, cb: cb }; };
    const sandbox = {
        console: console,
        setTimeout: setTimeout,
        JSON: JSON,
        parseInt: parseInt,
        parseFloat: parseFloat,
        Number: Number,
        String: String,
        Math: Math,
        Date: Date,
        isNaN: isNaN,
        // 业务桩：只关心「会不会炸」，不关心渲染细节
        $: jq,
        jQuery: jq,
        layer: {
            load: function () { return 1; },
            close: function (t) { log.closed.push(t); },
            msg: function (m, opt) { log.msgs.push({ msg: m, opt: opt }); },
            closeAll: function () {}
        },
        window: { currentFiles: [], currentFilesMap: {} },
        document: anyStub(),
        t: function (key, def) { return def; },
        lan: {},
        getCookie: function (name) { return name === 'rank' ? 'a' : null; },
        setCookie: function () {},
        yfMsgEscape: function (s) {
            if (s == null) return '';
            return String(s)
                .replace(/&(?!(?:[a-zA-Z][a-zA-Z0-9]{1,31}|#\d{1,7}|#[xX][0-9a-fA-F]{1,6});)/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        },
        yfFilesText: function (s) { return s == null ? '' : String(s); },
        yfFilesJsStr: function (s) { return s == null ? '' : String(s); },
        makeFilePage: function () {},
        calcPathWidth: function () {},
        pathPlaceBtn: function () {},
        pathLeft: function () {},
        isDiskWidth: function () {},
        showSeclect: function () {},
        getPathSize: function () {},
        getExtName: function () { return 'folder'; },
        toSize: function (b) { return String(b) + ' B'; },
        getMatchTime: function () { return '2026/10/28 12:00:00'; },
        getLocalTime: function () { return '2026/10/28 12:00:00'; },
        isChineseChar: function () { return false; },
        isCompressFile: function () { return false; },
        isText: function () { return false; },
        isImage: function () { return false; },
        bindselect: function () {},
        showSeclect: function () {},
        totalFile: function () { return 0; },
        rightMenuClick: function () {},
        rightMenuClickAll: function () {},
        updateActiveTabPath: function () {},
        renderFileTabs: function () {},
        getFiles: function () {},
        initDragDrop: function () {},
        plusFileTabs: function () {},
        initFileTabs: function () {}
    };
    sandbox.global = sandbox;
    vm.createContext(sandbox);
    // getFiles() 作用域里的局部变量：回调体闭包引用它们，这里按原值补齐
    vm.runInContext(
        'var file_row = "100"; var loadT = 1; var post = {path: "/www"};' +
        ' var body = ""; var totalSize = 0; var Path = "/www";', sandbox);
    return { sandbox: sandbox, log: log };
}

function runCase(payload) {
    const ctx = makeSandbox();
    const runner = vm.runInContext(
        '(function(rdata) {' + body + '})', ctx.sandbox);
    let thrown = null;
    try {
        runner(payload);
    } catch (e) {
        thrown = e;
    }
    return { thrown: thrown, log: ctx.log, payload: payload, sandbox: ctx.sandbox };
}

const failures = [];

// ---- 场景 1：安全拒绝（真机复现的那个） ----
const c1 = runCase({ status: false, msg: 'FILE_DANGER' });
if (c1.thrown) {
    failures.push('安全拒绝 payload 仍然抛异常: ' + c1.thrown.message);
} else if (!c1.log.msgs.length) {
    failures.push('安全拒绝 payload 没有给用户任何提示（layer.msg 未被调用）');
} else if (String(c1.log.msgs[0].msg).indexOf('FILE_DANGER') === -1) {
    failures.push('提示没有使用服务端 msg: ' + JSON.stringify(c1.log.msgs[0].msg));
}

// ---- 场景 2：服务端 msg 含 HTML（提示必须转义，不许当 HTML 注入） ----
const c2 = runCase({ status: false, msg: '<img src=x onerror=alert(1)>' });
if (c2.thrown) {
    failures.push('含 HTML 的 msg 抛异常: ' + c2.thrown.message);
} else if (!c2.log.msgs.length || String(c2.log.msgs[0].msg).indexOf('<img') !== -1) {
    failures.push('提示未转义，可注入 HTML: ' + JSON.stringify(c2.log.msgs));
}

// ---- 场景 3：历史/插件回调的残缺 payload（无 dir/files） ----
const c3 = runCase({ path: '/www/wwwroot' });
if (c3.thrown) {
    failures.push('缺失 dir/files 的 payload 抛异常: ' + c3.thrown.message);
}

// ---- 场景 4：正常空目录（不能因为加了守卫就变红） ----
const c4 = runCase({ path: '/www/wwwroot/empty', dir: [], files: [], count: 0, page: '', status: true });
if (c4.thrown) {
    failures.push('正常空目录 payload 抛异常: ' + c4.thrown.message);
} else if (c4.log.msgs.length) {
    failures.push('正常空目录不该弹错误提示: ' + JSON.stringify(c4.log.msgs));
}

// ---- 场景 5：一条目录 + 一条文件（渲染链路仍要能走完） ----
const c5 = runCase({
    path: '/www/wwwroot/site',
    dir: ['upload;;;755;root;0; -> /data'],
    files: ['index.php;1024;2026/10/28 12:00:00;644;www;'],
    count: 2,
    page: '',
    status: true
});
if (c5.thrown) {
    failures.push('正常列表 payload 抛异常: ' + c5.thrown.message);
}

if (failures.length) {
    console.log('FAIL: ' + failures.join(' | '));
    process.exit(1);
}
console.log('OK');
