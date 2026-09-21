// 生成浏览器级验证页：把「净化后的 XSS 载荷」真正塞进 DOM，
// 由 headless Chrome 加载后看 window.__pwned 是否被置位。
//
// 与 Node 里的字符串断言互补：字符串断言只能证明「危险子串不在了」，
// 浏览器验证能证明「即便有漏网，浏览器也不会执行」。
'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..', '..');
const PUBLIC_JS = path.join(ROOT, 'web', 'static', 'app', 'public.js');
const OUTDIR = process.env.YF_PROBE_OUT || require('os').tmpdir();
const OUT = path.join(OUTDIR, 'xss_browser_probe.html');

const src = fs.readFileSync(PUBLIC_JS, 'utf8');
const a = src.indexOf('// safeMessage 的 HTML 安全层');
const b = src.indexOf('function safeMessage(', a);
const api = new Function(src.slice(a, b) + '\nreturn yfMsgSanitize;')();
const sanitize = api;

// 把数据安全嵌入内联 <script>：必须转义 </ 否则会提前闭合脚本元素
function jstr(o) { return JSON.stringify(o).replace(/<\//g, '<\\/'); }

const PAYLOADS = [
    '<img src=x onerror="window.__pwned=1">',
    '<script>window.__pwned=1<\/script>',
    '<a href="javascript:window.__pwned=1">click</a>',
    '<svg onload="window.__pwned=1"></svg>',
    '<iframe src="javascript:window.__pwned=1"></iframe>',
    '"><img src=x onerror="window.__pwned=1">',
    '<body onload="window.__pwned=1">',
    '<input autofocus onfocus="window.__pwned=1">',
    '<a style="color:red;" onmouseover="window.__pwned=1">hover</a>',
    '<div style="background:url(javascript:window.__pwned=1)">x</div>',
    '<math><mtext><script>window.__pwned=1<\/script></mtext></math>',
    '<!--<script>window.__pwned=1<\/script>-->',
    '<base href="javascript:window.__pwned=1">',
    '<form action="javascript:window.__pwned=1"><button>go</button></form>',
    '<template><script>window.__pwned=1<\/script></template>'
];

// 严格档 + 宽松档都跑（宽松档放行 input/label，是更宽的暴露面）
const strictOut = PAYLOADS.map(function (p) { return sanitize(p, false); });
const extOut = PAYLOADS.map(function (p) { return sanitize(p, true); });

const html = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>pending</title></head><body>'
    + '<div id="strict"></div><div id="ext"></div>'
    + '<script>'
    + 'window.__pwned = 0;'
    + 'function inject(id, arr){ var host = document.getElementById(id);'
    + '  arr.forEach(function(h){ var d = document.createElement("div"); d.innerHTML = h; host.appendChild(d); }); }'
    + 'inject("strict", ' + jstr(strictOut) + ');'
    + 'inject("ext", ' + jstr(extOut) + ');'
    + 'setTimeout(function(){'
    + '  document.title = JSON.stringify({pwned: window.__pwned,'
    + '    strictTags: document.getElementById("strict").getElementsByTagName("*").length,'
    + '    extTags: document.getElementById("ext").getElementsByTagName("*").length});'
    + '}, 60);'
    + '<\/script></body></html>';

fs.mkdirSync(OUTDIR, { recursive: true });
fs.writeFileSync(OUT, html, 'utf8');
console.log('OUT=' + OUT);

// 对照组：**未净化**的原始载荷。它必须能置位 __pwned，
// 否则说明探针本身抓不到执行，「净化后未置位」的结论就没有意义。
const RAW_OUT = path.join(OUTDIR, 'xss_browser_probe_raw.html');
const rawHtml = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>pending</title></head><body>'
    + '<div id="strict"></div>'
    + '<script>'
    + 'window.__pwned = 0;'
    + 'function inject(id, arr){ var host = document.getElementById(id);'
    + '  arr.forEach(function(h){ var d = document.createElement("div"); d.innerHTML = h; host.appendChild(d); }); }'
    + 'inject("strict", ' + jstr(PAYLOADS) + ');'
    + 'setTimeout(function(){ document.title = JSON.stringify({pwned: window.__pwned}); }, 60);'
    + '<\/script></body></html>';
fs.writeFileSync(RAW_OUT, rawHtml, 'utf8');
console.log('RAW_OUT=' + RAW_OUT);

console.log('严格档输出样例:');
strictOut.forEach(function (h, i) { console.log('  [' + i + '] ' + JSON.stringify(h)); });
