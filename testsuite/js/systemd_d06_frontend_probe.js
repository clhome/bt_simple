/**
 * D06 yufeng_systemd 前端守卫夹具（由 testsuite/test_systemd_d06_hardening.py 调用）。
 *
 * 用法：node systemd_d06_frontend_probe.js <yufeng_systemd.js 绝对路径>
 * 输出：一行 JSON，形如 {"ok":true,"checks":[...],"failures":[...]}
 *
 * 为什么需要它：`request()` 旧实现只在成功分支 layer.close(loadT)，而插件侧
 * 一旦 returnJson(False)（业务失败）或网络失败，time:0 的遮罩就永久留在页面上
 * 把弹窗点死。这属于「只在失败路径才出现」的缺陷，读代码容易看漏，所以在
 * 假 layer/$ 上真跑一次 request()，断言三个分支都关闭了 loading。
 */
'use strict';

const fs = require('fs');
const path = require('path');

const jsPath = process.argv[2];
const failures = [];
const checks = [];

function check(name, cond, extra) {
    checks.push(name);
    if (!cond) {
        failures.push(name + (extra ? ' -> ' + extra : ''));
    }
}

const layerSeq = { n: 0 };
const closed = [];
const opened = [];

const window = {};
window.$ = function () { return { length: 0 }; };

const layer = {
    // 只把 time:0（常驻）的那次计为 loading —— 平时的 toast（默认 3s 自关）不计。
    msg: function (content, opts) {
        layerSeq.n += 1;
        if (opts && opts.time === 0) {
            opened.push(layerSeq.n);
            return layerSeq.n;
        }
        return -layerSeq.n;
    },
    close: function (id) { closed.push(id); },
    open: function () { return 1; },
    closeAll: function () {},
    confirm: function () { return 1; },
    alert: function () {}
};

let ajaxOpts = null;
const $ = function () {
    return {
        length: 0,
        html: function () { return this; },
        val: function () { return ''; },
        show: function () { return this; },
        hide: function () { return this; },
        text: function () { return this; }
    };
};
$.ajax = function (opts) { ajaxOpts = opts; return {}; };
$.getScript = function () {};
$.post = function () {};

const YfPlugin = { createApi: function () { return { post: function () {} }; } };
const YfI18n = { createPluginTranslator: function () { return function (k) { return k; }; } };
const btoa = function (s) { return Buffer.from(s, 'binary').toString('base64'); };
const alert = function () {};
const console_fail = function () {};

const src = fs.readFileSync(jsPath, 'utf8');

// 直接 eval（非 strict）让文件里的 function/var 声明进入本作用域，便于断言。
const sandbox = new Function('window', 'layer', '$', 'YfPlugin', 'YfI18n', 'btoa', 'alert', 'document',
    src + '\n;return {ysEsc: (typeof ysEsc === "function" ? ysEsc : null), ' +
    'ysArg: (typeof ysArg === "function" ? ysArg : null), mod: yufeng_systemd};');

const out = sandbox(window, layer, $, YfPlugin, YfI18n, btoa, alert, {});
const ysEsc = out.ysEsc;
const ysArg = out.ysArg;
const mod = out.mod;

function esc(v) { return typeof ysEsc === 'function' ? ysEsc(v) : ''; }
function arg(v) { return typeof ysArg === 'function' ? ysArg(v) : ''; }
check('ysEsc/ysArg 转义助手存在', typeof ysEsc === 'function' && typeof ysArg === 'function');

// ---- 1. 转义助手 ----
const xss = '<img src=x onerror=alert(1)>';
check('ysEsc 转义尖括号', esc(xss).indexOf('<') === -1 && esc(xss).indexOf('>') === -1, esc(xss));
check('ysEsc 转义引号', esc('a"b\'c').indexOf('"') === -1 && esc("a'b").indexOf("'") === -1);
check('ysEsc null 安全', esc(null) === '' && esc(undefined) === '');
check('ysArg 转义单引号', arg("a'b").indexOf("\\'") >= 0, arg("a'b"));
check('ysArg 去掉换行', arg('a\nb').indexOf('\n') === -1);
check('ysArg 反斜杠加倍', arg('a\\b') === 'a\\\\b', arg('a\\b'));

// ---- 2. loading 遮罩：成功 / 业务失败 / 网络失败 三个分支都必须关闭 ----
function runRequest(fire) {
    if (typeof mod.request !== 'function') {
        failures.push('request 方法缺失');
        return { closedCount: -1, cbCalled: false };
    }
    closed.length = 0;
    opened.length = 0;
    ajaxOpts = null;
    let cbCalled = false;
    mod.request('get_services', {}, function () { cbCalled = true; }, 'LOADING');
    if (!ajaxOpts) {
        failures.push('request 未发出 $.ajax');
        return { closedCount: -1, cbCalled: cbCalled };
    }
    fire(ajaxOpts);
    return { closedCount: closed.length, cbCalled: cbCalled };
}

let r = runRequest(function (o) { o.success({ status: true, data: '{"status":true,"msg":"ok","data":[]}' }); });
check('成功分支关闭 loading', r.closedCount === 1 && r.cbCalled === true, JSON.stringify(r));

r = runRequest(function (o) { o.success({ status: false, msg: 'BOOM' }); });
check('业务失败(status:false)关闭 loading 且不回调', r.closedCount === 1 && r.cbCalled === false, JSON.stringify(r));

r = runRequest(function (o) { o.error(); });
check('网络失败关闭 loading', r.closedCount === 1, JSON.stringify(r));

r = runRequest(function (o) { o.success({ status: true, data: 'not-json' }); });
check('data 非法 JSON 时也关闭 loading', r.closedCount === 1 && r.cbCalled === true, JSON.stringify(r));

// 三个分支各只开一次 loading（不能出现叠加遮罩）
r = runRequest(function (o) { o.error(); });
check('单次请求只开一个 loading', opened.length === 1, JSON.stringify(opened));

// ---- 3. 静态：除了 request 内部，不应再有 time:0 的常驻 loading ----
const stripped = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
const permanent = (stripped.match(/time:\s*0/g) || []).length;
check('time:0 常驻 loading 只允许出现在 request 内', permanent === 1, 'time:0 出现 ' + permanent + ' 处');

// ---- 4. 列表渲染：动态值必须经过转义助手 ----
check('列表 unit 名经 ysEsc 输出', /ysEsc\(item\.name\)/.test(stripped));
check('onclick 参数经 ysArg 输出', /ysArg\(item\.name\)/.test(stripped) && /'\+sname\+'/.test(stripped));

console.log(JSON.stringify({ ok: failures.length === 0, checks: checks, failures: failures }));
process.exit(failures.length === 0 ? 0 : 1);
