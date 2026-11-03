/**
 * 验证：首页每次点开「PHP 安全基线」按钮，自动进行一次检测。
 * 由 testsuite/test_php_rescan_and_shop_policy.py 调用。
 */
'use strict';

const fs = require('fs');
const path = require('path');

const indexJsPath = process.argv[2] || path.resolve(__dirname, '../../web/static/app/index.js');
const indexJsContent = fs.readFileSync(indexJsPath, 'utf8');

const postCalls = [];
let layerOpenCalls = 0;
let modalIndexSeq = 100;

const mockDom = {
    '#phpSecCard': { length: 1, hide: function() {}, show: function() {} },
    '#phpSecBody': { length: 1, htmlStr: '<div>php items</div>', html: function(v) { if (v !== undefined) this.htmlStr = v; return this.htmlStr; } },
    '#phpSecMeta': { length: 1, text: function() {} },
    '#phpSecRescanBtn': {
        length: 1,
        disabled: false,
        classes: [],
        htmlContent: '',
        prop: function(key, val) { if (val !== undefined) { this[key] = val; return this; } return this[key]; },
        addClass: function(cls) { if (!this.classes.includes(cls)) this.classes.push(cls); return this; },
        removeClass: function(cls) { this.classes = this.classes.filter(c => c !== cls); return this; },
        css: function() { return this; },
        html: function(val) { if (val !== undefined) this.htmlContent = val; return this.htmlContent; }
    },
    '#phpSecModalBody': {
        length: 1,
        content: '',
        html: function(val) { if (val !== undefined) this.content = val; return this.content; }
    },
    '#indexSecurityBox': { length: 1, hide: function() {}, show: function() {}, is: function() { return true; } },
    '#securityItemsContainer': { length: 1, html: function() {}, empty: function() {} },
    '.recent-logins-box': { length: 1, outerHeight: function() { return 100; } }
};

const mockObj = {
    length: 1,
    attr: function() { return ''; },
    html: function() { return ''; },
    text: function() { return ''; },
    hide: function() { return this; },
    show: function() { return this; },
    empty: function() { return this; },
    css: function() { return this; },
    prop: function() { return this; },
    addClass: function() { return this; },
    removeClass: function() { return this; },
    on: function() { return this; },
    hover: function() { return this; },
    click: function() { return this; },
    is: function() { return true; },
    outerHeight: function() { return 100; },
    ready: function() { return this; }
};

const $ = function(selector) {
    if (typeof selector === 'function') return;
    if (mockDom[selector]) return mockDom[selector];
    return Object.assign({}, mockObj);
};

$.post = function(url, data, success, dataType) {
    const p = {
        url, data, success, dataType,
        fail: function(fn) { this._fail = fn; return this; },
        always: function(fn) { this._always = fn; return this; }
    };
    postCalls.push(p);
    return p;
};

const layer = {
    open: function() {
        layerOpenCalls++;
        return modalIndexSeq++;
    },
    close: function() {},
    msg: function() { return 1; }
};

const sessionStorage = {
    store: {},
    getItem: function(k) { return this.store[k] || null; },
    setItem: function(k, v) { this.store[k] = String(v); },
    removeItem: function(k) { delete this.store[k]; }
};

const document = { ready: function() {} };
const window = {
    $: $,
    layer: layer,
    sessionStorage: sessionStorage,
    location: { hostname: 'localhost' },
    document: document
};

function t(key, def) { return def || key; }

const vm = require('vm');
const context = {
    $,
    jQuery: $,
    window,
    document,
    layer,
    sessionStorage,
    Date,
    JSON,
    Array,
    String,
    parseInt,
    setTimeout,
    clearTimeout,
    t,
    console
};
vm.createContext(context);
vm.runInContext(indexJsContent, context);

const btSecurityCenter = context.window.btSecurityCenter;
const result = { ok: true, checks: [], failures: [] };

function check(name, cond, msg) {
    result.checks.push(name);
    if (!cond) {
        result.ok = false;
        result.failures.push(name + (msg ? ': ' + msg : ''));
    }
}

check('btSecurityCenter exists', !!btSecurityCenter);

// 1. 初始化报警状态
btSecurityCenter.updatePhpStatus({
    state: 'alarm',
    count: 1,
    baseline_date: '2026-10-22',
    scan_time_text: '2026-11-03 12:00:00',
    items: [{ branch: '80', channel: 'apt', version: '8.0.30', alarm: true, status: 'need_upgrade' }]
});
check('initial phpAlarmCount is 1', btSecurityCenter.phpAlarmCount === 1);

// 2. 第一次打开弹窗：立即调起 layer.open 且自动发送 force:1 的检测请求
postCalls.length = 0;
layerOpenCalls = 0;
btSecurityCenter.showPhpSecModal();
check('layer.open called', layerOpenCalls === 1);
check('post sent with force:1', postCalls.length === 1 && postCalls[0].url === '/get_php_security_status' && postCalls[0].data.force === 1);
check('button in disabled/scanning state', !!mockDom['#phpSecRescanBtn'].disabled);

// 3. 模拟检测成功返回，数据更新，按钮恢复
const req1 = postCalls[0];
req1.success({
    status: true,
    data: {
        state: 'ok',
        count: 1,
        baseline_date: '2026-10-22',
        scan_time_text: '2026-11-03 14:28:00',
        items: [{ branch: '82', channel: 'apt', version: '8.2.26', alarm: false, status: 'ok' }]
    }
});
if (req1._always) req1._always();

check('button re-enabled after scan', mockDom['#phpSecRescanBtn'].disabled === false);
check('count updated to 0', btSecurityCenter.phpAlarmCount === 0);

// 4. 第二次点开弹窗：依然自动进行一次检测（force: 1）
postCalls.length = 0;
btSecurityCenter.showPhpSecModal();
check('second open triggers scan', postCalls.length === 1 && postCalls[0].data.force === 1);

console.log(JSON.stringify(result));
process.exit(result.ok ? 0 : 1);

