// 生成浏览器级验证页：把「净化后的 XSS 载荷」真正塞进 DOM，
// 由 headless Chrome 加载后看 window.__pwned 是否被置位。
//
// 与 Node 里的字符串断言互补：字符串断言只能证明「危险子串不在了」，
// 浏览器验证能证明「即便有漏网，浏览器也不会执行」。
//
// ---------------------------------------------------------------------------
// 2026-10-13 加固：CI 上「对照组未发生脚本执行」的假红
// ---------------------------------------------------------------------------
// 旧版对照组靠「浏览器自己派发 img.onerror / svg.onload / details.ontoggle …」
// 来置位 __pwned，再用一个一次性的 60ms 定时器把结果写进标题。这条路径依赖
// headless Chrome 在 `--virtual-time-budget` 下**何时**派发异步事件 —— CI（Linux）
// 实测一个都没派发（标题停在 `{"pwned":0}`），于是「探针抓不到执行」被判红，
// 但被验证的净化器其实没有问题：这是**探针的时序假设错了**，不是回归。
//
// 现在改成两层与事件时序无关的证据：
//   ① 强制派发（确定性）：注入后遍历 DOM，把每个元素上 `on*` 属性对应的事件
//      显式 dispatch 一遍。只要「内联事件处理器会被执行」这个前提成立，对照组
//      就必然置位；而净化后的产物里根本没有 `on*` 属性，所以仍然是 0。
//      —— 这把「对照组能否执行」从「依赖浏览器何时派发」变成确定性事实。
//   ② DOM 级危险属性计数（浏览器解析后的形态，比字符串匹配更可信）：
//      `on*` 属性、`javascript:/vbscript:/data:` 协议属性、`srcdoc`、可执行的
//      `style`（url()/expression()）。对照组必须 > 0（证明探测器本身在工作），
//      净化组必须 == 0。
//
// 结果在注入后**同步**写入标题（延迟定时器只用于补充「浏览器自然派发」的
// 诊断值 natural），因此即使定时器一次都不跑，结论照样成立。
'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..', '..');
// YF_PUBLIC_JS 可指向变异体（与 test_safemessage_sanitize.js 同口径）：
// 用于自证「净化器退化为恒等函数时，浏览器级断言必须变红」。
const PUBLIC_JS = process.env.YF_PUBLIC_JS || path.join(ROOT, 'web', 'static', 'app', 'public.js');
const OUTDIR = process.env.YF_PROBE_OUT || require('os').tmpdir();
const OUT = path.join(OUTDIR, 'xss_browser_probe.html');

const src = fs.readFileSync(PUBLIC_JS, 'utf8');
const a = src.indexOf('// safeMessage 的 HTML 安全层');
const b = src.indexOf('function safeMessage(', a);
const api = new Function(src.slice(a, b) + '\nreturn yfMsgSanitize;')();
const sanitize = api;

// 把数据安全嵌入内联 <script>：把**所有** `<` 转成 `\u003c`。
// 只转义 `</` 还不够 —— 载荷里同时含 `<!--` 与 `<script`，会让 HTML 分词器
// 进入 script-data-escaped / double-escaped 状态（mXSS 的经典触发形态），
// 整个内联脚本的边界就不可控了。全部转义后脚本文本里再无 `<`。
function jstr(o) { return JSON.stringify(o).replace(/</g, '\\u003c'); }

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

// 页面端公共探针。放在两页共用的一段 <script> 里，保证对照组与净化组
// 走的是**同一套**探测逻辑（否则对照就失去意义）。
const HARNESS = [
    'window.__pwned = 0;',
    // 可携带协议的属性：出现 javascript:/vbscript:/data: 即视为危险
    "var DANGER_URL_ATTRS = ['href','src','action','formaction','data','xlink:href',",
    "                        'poster','background','cite','dynsrc','lowsrc'];",
    'function yfInject(id, arr) {',
    '  var host = document.getElementById(id);',
    '  arr.forEach(function (h) {',
    '    var d = document.createElement("div");',
    '    d.innerHTML = h;                 // 与 safeMessage 的真实注入路径一致',
    '    host.appendChild(d);',
    '  });',
    '  return host;',
    '}',
    // DOM 级危险属性计数：浏览器已经完成解析（实体、大小写、命名空间都已归一），
    // 比在字符串上做正则更接近真相。
    'function yfDanger(root) {',
    '  var n = 0;',
    '  var all = [root].concat(Array.prototype.slice.call(root.querySelectorAll("*")));',
    '  all.forEach(function (el) {',
    '    if (!el.attributes) return;',
    '    for (var i = 0; i < el.attributes.length; i++) {',
    '      var name = String(el.attributes[i].name).toLowerCase();',
    '      var val = String(el.attributes[i].value || "");',
    '      var norm = val.replace(/[\\s\\u0000-\\u0020]+/g, "").toLowerCase();',
    '      if (name.indexOf("on") === 0) { n++; continue; }',
    '      if (name === "srcdoc") { n++; continue; }',
    '      if (DANGER_URL_ATTRS.indexOf(name) >= 0 &&',
    '          /^(javascript|vbscript|data):/.test(norm)) { n++; continue; }',
    '      if (name === "style" &&',
    '          /url\\s*\\(|expression\\s*\\(|javascript\\s*:/i.test(val)) { n++; continue; }',
    '    }',
    '  });',
    '  return n;',
    '}',
    // 强制派发：把每个元素上 on* 属性对应的事件显式 dispatch 一遍。
    // 这证明「内联事件处理器确实会被浏览器执行」——不依赖浏览器何时自然派发。
    'function yfForce(root) {',
    '  var fired = 0;',
    '  Array.prototype.slice.call(root.querySelectorAll("*")).forEach(function (el) {',
    '    var types = [];',
    '    for (var i = 0; i < el.attributes.length; i++) {',
    '      var name = String(el.attributes[i].name).toLowerCase();',
    '      if (name.indexOf("on") === 0 && name.length > 2) types.push(name.slice(2));',
    '    }',
    '    types.forEach(function (t) {',
    '      try {',
    '        el.dispatchEvent(new Event(t, { bubbles: false, cancelable: true }));',
    '        fired++;',
    '      } catch (e) { /* 未知事件类型等：忽略 */ }',
    '    });',
    '  });',
    '  return fired;',
    '}',
    'function yfReport(obj) { document.title = JSON.stringify(obj); }',
    // 先同步出一份结果（不依赖任何定时器）；再延迟补一次：净化组在强制派发后
    // 仍为 0，若有「晚到的自然执行」这第二次就能抓到。natural 记录的是强制派发
    // **之前**的自然执行次数（CI 上恒为 0，仅作诊断）。
    'function yfSnap(host, extra, natural0) {',
    '  var o = { pwned: window.__pwned, natural: natural0 };',
    '  for (var k in extra) { if (Object.prototype.hasOwnProperty.call(extra, k)) o[k] = extra[k]; }',
    '  o.tags = host.getElementsByTagName("*").length;',
    '  yfReport(o);',
    '}'
].join('\n');

// ---------- 对照组：未净化的原始载荷（必须能置位 __pwned） ----------
const rawBody = HARNESS + '\n'
    + 'var host = yfInject("strict", ' + jstr(PAYLOADS) + ');\n'
    + 'var natural0 = window.__pwned;\n'
    + 'var dangerous = yfDanger(host);\n'
    + 'var forced = yfForce(host);\n'
    + 'yfSnap(host, { dangerous: dangerous, forcedFired: forced }, natural0);\n'
    + 'setTimeout(function () { yfSnap(host, { dangerous: dangerous, forcedFired: forced }, natural0); }, 300);';

const rawHtml = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>pending</title></head><body>'
    + '<div id="strict"></div>'
    + '<script>' + rawBody + '<\/script></body></html>';

// ---------- 净化组：严格档 + 宽松档（都必须为 0） ----------
const sanBody = HARNESS + '\n'
    + 'var strictHost = yfInject("strict", ' + jstr(strictOut) + ');\n'
    + 'var extHost = yfInject("ext", ' + jstr(extOut) + ');\n'
    + 'var natural0 = window.__pwned;\n'
    + 'var dangerous = yfDanger(strictHost) + yfDanger(extHost);\n'
    + 'var forced = yfForce(strictHost) + yfForce(extHost);\n'
    + 'var extra = { dangerous: dangerous, forcedFired: forced,\n'
    + '  strictTags: strictHost.getElementsByTagName("*").length,\n'
    + '  extTags: extHost.getElementsByTagName("*").length };\n'
    + 'yfSnap(strictHost, extra, natural0);\n'
    + 'setTimeout(function () { yfSnap(strictHost, extra, natural0); }, 300);';

const html = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>pending</title></head><body>'
    + '<div id="strict"></div><div id="ext"></div>'
    + '<script>' + sanBody + '<\/script></body></html>';

fs.mkdirSync(OUTDIR, { recursive: true });
fs.writeFileSync(OUT, html, 'utf8');
fs.writeFileSync(path.join(OUTDIR, 'xss_browser_probe_raw.html'), rawHtml, 'utf8');
console.log('OUT=' + OUT);
console.log('RAW_OUT=' + path.join(OUTDIR, 'xss_browser_probe_raw.html'));

console.log('严格档输出样例:');
strictOut.forEach(function (h, i) { console.log('  [' + i + '] ' + JSON.stringify(h)); });
