// safeMessage HTML 净化层的行为测试（Node，无外部依赖）
//
// 做法：从 web/static/app/public.js 中**原样抽取**净化层代码块（标记注释 →
// function safeMessage( 之间），在 Node 里 eval 后跑断言。
// 这样测试的是真实生产代码，而不是复制品 —— 复制品会漂移。
//
// 两层断言：
//   ① 逐条用例：特定危险子串必须消失 / 特定既有 UI 必须保留
//   ② 全局不变量：输出里的**每个活标签**都必须满足
//        - 标签名在白名单内
//        - 不含 on* 事件属性
//        - 不含 href/src/action/formaction/srcdoc/xlink:href 等可携带协议的属性
//        - 不含 javascript: / vbscript:
//      不变量比逐条断言强：新增一条净化规则时，任何漏网标签都会被兜住。
//
// 自证纪律：每个「必须拦截」用例先断言**原始输入本身确实含危险子串**
// （证明测试向量有效），再断言输出不含它。缺了前一半，断言可能在
// 「向量本身就无害」的情况下恒真，等于没有测试。
//
// 用法：
//   node test/i18n_scripts/tools/test_safemessage_sanitize.js
// 退出码：0 全部通过 / 1 存在失败 / 2 无法定位生产代码

'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..', '..');
// 允许指向替身文件，用于「变异测试」自证：把净化器改成恒等函数后，
// 本测试必须转为失败，否则说明断言恒真、形同虚设。
const PUBLIC_JS = process.env.YF_PUBLIC_JS || path.join(ROOT, 'web', 'static', 'app', 'public.js');

const src = fs.readFileSync(PUBLIC_JS, 'utf8');
const START = '// safeMessage 的 HTML 安全层';
const END = 'function safeMessage(';
const a = src.indexOf(START);
const b = src.indexOf(END, a);
if (a < 0 || b < 0 || b <= a) {
    console.error('[FATAL] 无法在 public.js 中定位净化层代码块');
    process.exit(2);
}
const block = src.slice(a, b);

let api;
try {
    api = new Function(block + '\nreturn { yfMsgEscape: yfMsgEscape,'
        + ' yfMsgSanitize: yfMsgSanitize,'
        + ' YF_MSG_TAGS: YF_MSG_TAGS, YF_MSG_ATTRS: YF_MSG_ATTRS,'
        + ' YF_MSG_TAGS_EXT: YF_MSG_TAGS_EXT, YF_MSG_ATTRS_EXT: YF_MSG_ATTRS_EXT };')();
} catch (e) {
    console.error('[FATAL] 净化层代码块无法求值: ' + e.message);
    process.exit(2);
}

const { yfMsgEscape, yfMsgSanitize } = api;

const TAG_ALLOW = Object.create(null);
api.YF_MSG_TAGS.forEach(function (t) { TAG_ALLOW[t] = 1; });
const TAG_ALLOW_EXT = Object.create(null);
api.YF_MSG_TAGS_EXT.forEach(function (t) { TAG_ALLOW_EXT[t] = 1; });

let pass = 0;
const failures = [];

function ok() { pass++; }
function fail(name, detail) {
    failures.push(name + ' :: ' + detail);
    console.log('  [FAIL] ' + name + '\n         ' + detail);
}

// 取出字符串里所有「活标签」（跳过引号内的 >）
function collectTags(s) {
    const out = [];
    let i = 0;
    while (true) {
        const lt = s.indexOf('<', i);
        if (lt < 0) break;
        let q = null, gt = -1;
        for (let j = lt + 1; j < s.length; j++) {
            const ch = s.charAt(j);
            if (q) { if (ch === q) q = null; }
            else if (ch === '"' || ch === "'") q = ch;
            else if (ch === '>') { gt = j; break; }
        }
        if (gt < 0) break;
        out.push(s.slice(lt, gt + 1));
        i = gt + 1;
    }
    return out;
}

const URL_ATTRS = ['href', 'src', 'action', 'formaction', 'srcdoc', 'xlink:href',
    'background', 'dynsrc', 'lowsrc', 'poster', 'data'];
const PROTO_RE = /(?:javascript|vbscript)\s*:/i;

// 引号感知地取出标签名与属性名。
// 必须先剥掉引号内的值，否则 `title="a&quot; onmouseover=&quot;x"` 里的
// `onmouseover=` 只是属性值中的文本，会被误判成事件属性（假阳性）。
// 这里刻意不复用净化器内部的解析器，避免「同一处 bug 两边都错」的循环论证。
function tagParts(tag) {
    const m = /^<\s*\/?\s*([a-zA-Z][a-zA-Z0-9]*)/.exec(tag);
    if (!m) return null;
    const stripped = tag.replace(/"[^"]*"/g, '""').replace(/'[^']*'/g, "''");
    const attrs = [];
    const re = /\s([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*(?:=|[\s>\/]|$)/g;
    let am;
    while ((am = re.exec(stripped)) !== null) attrs.push(am[1].toLowerCase());
    return { name: m[1].toLowerCase(), attrs: attrs };
}

// 全局不变量：输出里的每个活标签都必须安全
function invariant(name, out, extended) {
    const allow = extended ? TAG_ALLOW_EXT : TAG_ALLOW;
    const bad = [];
    collectTags(out).forEach(function (tag) {
        const p = tagParts(tag);
        if (!p) { bad.push('无法解析: ' + tag); return; }
        if (!allow[p.name]) bad.push('非白名单标签: ' + tag);
        p.attrs.forEach(function (an) {
            if (/^on/.test(an)) bad.push('事件属性 ' + an + ': ' + tag);
            else if (URL_ATTRS.indexOf(an) >= 0) bad.push('协议属性 ' + an + ': ' + tag);
        });
        if (PROTO_RE.test(tag)) bad.push('危险协议: ' + tag);
    });
    if (bad.length) { fail(name + ' [不变量]', bad.join(' | ')); return false; }
    return true;
}

// ① 输入本身必须含 marker（证明向量有效）→ ② 净化后不得含 marker ③ 不变量
function blocks(name, input, marker, extended) {
    if (String(input).indexOf(marker) < 0) {
        fail(name, '自证失败：向量本身不含 ' + JSON.stringify(marker) + '，断言会恒真');
        return;
    }
    const out = yfMsgSanitize(input, extended);
    if (out.indexOf(marker) >= 0) {
        fail(name, '净化后仍含 ' + JSON.stringify(marker) + ' → ' + JSON.stringify(out));
        return;
    }
    if (!invariant(name, out, extended)) return;
    ok();
}

function contains(name, input, marker, extended) {
    const out = yfMsgSanitize(input, extended);
    if (out.indexOf(marker) < 0) {
        fail(name, '净化后丢失了 ' + JSON.stringify(marker) + ' → ' + JSON.stringify(out));
        return;
    }
    if (!invariant(name, out, extended)) return;
    ok();
}

function equals(name, input, want, extended) {
    const out = yfMsgSanitize(input, extended);
    if (out !== want) {
        fail(name, '期望 ' + JSON.stringify(want) + '，实得 ' + JSON.stringify(out));
        return;
    }
    if (!invariant(name, out, extended)) return;
    ok();
}

console.log('== A. 必须拦截（XSS 向量） ==');
blocks('A1 img 标签', '<img src=x onerror=alert(1)>', '<img');
blocks('A2 script 标签', '<script>alert(1)</script>', '<script');
blocks('A3 a+href:javascript', '<a href="javascript:alert(1)">x</a>', 'href');
blocks('A4 a+onclick', '<a onclick="alert(1)">x</a>', 'onclick');
blocks('A5 属性越出（文件名注入形态）', '"><img src=x onerror=alert(1)>', '<img');
blocks('A6 svg onload', '<svg onload=alert(1)>', '<svg');
blocks('A7 iframe', '<iframe src="javascript:alert(1)"></iframe>', '<iframe');
blocks('A8 style 标签', '<style>body{}</style>', '<style');
blocks('A9 style:url(javascript:)', '<div style="background:url(javascript:alert(1))">x</div>', 'url(');
blocks('A9b style:javascript:', '<div style="background:url(javascript:alert(1))">x</div>', 'javascript:');
blocks('A10 HTML 注释夹带', '<!--<script>alert(1)</script>-->', '<script');
blocks('A11 大小写变形 on*', '<a STYLE="x" OnClick="alert(1)">x</a>', 'OnClick');
blocks('A12 input（严格档）', '<input id="toSubmit" value="x">', '<input');
blocks('A13 object', '<object data="x"></object>', '<object');
blocks('A14 无空格斜杠属性', '<a/onclick=alert(1)>x</a>', 'onclick');
blocks('A15 无引号 href', '<a style="x" href=javascript:alert(1)>x</a>', 'href');
blocks('A16 实体编码协议', '<a href="&#106;avascript:alert(1)">x</a>', 'href');
blocks('A17 math/MathML 命名空间', '<math><mtext><script>alert(1)</script></mtext></math>', '<math');
blocks('A18 onmouseover', '<a style="color:red;" onmouseover="alert(1)">x</a>', 'onmouseover');
blocks('A19 未闭合标签', '<img src=x onerror=alert(1)', '<img');
blocks('A20 属性值内藏标签', '<a title="a<b">x</a>', '<b');
blocks('A21 embed', '<embed src="x">', '<embed');
blocks('A22 link', '<link rel=stylesheet href="x">', '<link');
blocks('A23 form/formaction', '<form action="javascript:alert(1)"><button formaction="x">a</button></form>', '<form');
blocks('A24 base 标签', '<base href="//evil/">', '<base');
blocks('A25 meta refresh', '<meta http-equiv="refresh" content="0;url=javascript:alert(1)">', '<meta');
// A26：属性位越出。无 < 的输入只会被当成文本，`onmouseover=` 以转义文本保留是无害的；
//      真正要防的是「文件名被拼进 title="..." 时用引号越出属性」。故按属性上下文测。
(function () {
    const payload = 'a" onmouseover="alert(1)';
    if (payload.indexOf('"') < 0) {
        fail('A26 自证', '向量本身不含双引号，断言会恒真');
        return;
    }
    const esc = yfMsgEscape(payload);
    if (esc.indexOf('"') >= 0) {
        fail('A26 属性位引号越出', '转义后仍含裸双引号 → ' + JSON.stringify(esc));
        return;
    }
    const tag = '<td title="' + esc + '">x</td>';
    const p = tagParts(tag);
    if (!p || p.attrs.indexOf('onmouseover') >= 0) {
        fail('A26 属性位引号越出', '拼接后产生了事件属性 → ' + tag);
        return;
    }
    ok();
})();

console.log('== B. 必须保留（既有 UI 不被破坏） ==');
equals('B1 插件红色提示 <a>', "<a style='color:red;'>您共选择了[2]个数据库</a>",
    '<a style="color:red;">您共选择了[2]个数据库</a>');
equals('B2 站点删除正文', '<a style="color:red;">确定删除全部站点？</a>',
    '<a style="color:red;">确定删除全部站点？</a>');
equals('B3 实体 &lt;= 不重复转义', '&lt;= 12.5 MB', '&lt;= 12.5 MB');
equals('B4 裸 & 转义', 'A & B', 'A &amp; B');
equals('B5 中文纯文本', '您真的要删除【测试库】吗？', '您真的要删除【测试库】吗？');
equals('B6 br', '第一行<br>第二行', '第一行<br>第二行');
equals('B7 未闭合 < 当文本', 'a < b', 'a &lt; b');
equals('B8 双引号归一', "<span class='glyphicon glyphicon-exclamation-sign'></span>",
    '<span class="glyphicon glyphicon-exclamation-sign"></span>');
contains('B9 表格结构保留', '<table class="table table-hover" style="width: 100%;"><thead><tr>'
    + '<th style="padding: 9px 12px;">文件名</th></tr></thead><tbody><tr>'
    + '<td title="a.txt" style="padding: 10px 12px;">a.txt</td></tr></tbody></table>', '<table');
contains('B9b 表格 td 保留', '<table><tbody><tr><td title="a.txt">a.txt</td></tr></tbody></table>', '<td');
contains('B9c title 属性保留', '<td title="1.2 MB">1.2 MB</td>', 'title="1.2 MB"');
contains('B10 站点选项块（宽松档）',
    "<div class='options'><label><input type='checkbox' id='delpath' name='path'>"
    + '<span>根目录</span></label></div>', '<input', true);
contains('B10b 宽松档保留 id', "<div class='options'><label><input type='checkbox' id='delpath'>"
    + '</label></div>', 'id="delpath"', true);
contains('B10c 宽松档保留 name', "<input type='checkbox' name='path'>", 'name="path"', true);
equals('B11 glyphicon + style', '<span class="glyphicon glyphicon-exclamation-sign" style="font-size: 15px;"></span>',
    '<span class="glyphicon glyphicon-exclamation-sign" style="font-size: 15px;"></span>');
equals('B12 rgba 不被误伤', '<div style="background: rgba(230, 162, 60, 0.08);">x</div>',
    '<div style="background: rgba(230, 162, 60, 0.08);">x</div>');
equals('B13 hr', 'a<hr>b', 'a<hr>b');
equals('B14 null', null, '');
equals('B15 数字', 12345, '12345');
equals('B16 列表', '<ul><li>a</li><li>b</li></ul>', '<ul><li>a</li><li>b</li></ul>');
equals('B17 自闭合', 'a<br/>b', 'a<br />b');

console.log('== C. 严格档 / 宽松档差异 ==');
(function () {
    const probe = "<input type='checkbox' id='x'>";
    const strict = yfMsgSanitize(probe, false);
    const ext = yfMsgSanitize(probe, true);
    let good = true;
    if (strict.indexOf('<input') >= 0) {
        fail('C1 严格档必须拦 input', '严格档放行了 <input> → ' + JSON.stringify(strict));
        good = false;
    }
    if (ext.indexOf('<input') < 0) {
        fail('C2 宽松档必须放行 input', '宽松档误拦 <input> → ' + JSON.stringify(ext));
        good = false;
    }
    // 两档都必须拦事件属性
    const evil = "<input type='checkbox' onfocus='alert(1)'>";
    if (yfMsgSanitize(evil, true).indexOf('onfocus') >= 0) {
        fail('C3 宽松档仍须拦 on*', JSON.stringify(yfMsgSanitize(evil, true)));
        good = false;
    }
    if (good) { ok(); ok(); ok(); }
})();

console.log('== D. 自证：净化器不是恒等函数 ==');
(function () {
    const danger = '<img src=x onerror=alert(1)>';
    const out = yfMsgSanitize(danger);
    if (out === danger) {
        fail('D1 净化器对危险输入必须改变输出', '输入与输出相同 → 净化器可能失效');
        return;
    }
    const naive = String(danger);   // 反向对照：未净化的实现确实会漏
    if (naive.indexOf('<img') < 0) {
        fail('D2 对照实现应原样透传', '对照实现未透传危险标签，测试向量无效');
        return;
    }
    ok(); ok();
})();

console.log('== E. 转义函数本身 ==');
(function () {
    const cases = [
        ['<', '&lt;'], ['>', '&gt;'], ['"', '&quot;'], ["'", '&#39;'],
        ['&', '&amp;'], ['&amp;', '&amp;'], ['&lt;', '&lt;'], ['&#39;', '&#39;'],
        ['&nbsp;', '&nbsp;'], ['&notanentity', '&amp;notanentity'], ['a&b', 'a&amp;b'],
        ['&amp', '&amp;amp']
    ];
    cases.forEach(function (c) {
        const got = yfMsgEscape(c[0]);
        if (got !== c[1]) fail('E ' + JSON.stringify(c[0]), '期望 ' + JSON.stringify(c[1]) + ' 实得 ' + JSON.stringify(got));
        else ok();
    });
})();

console.log('');
console.log('通过: ' + pass + '  失败: ' + failures.length);
if (failures.length) {
    console.log('失败明细:');
    failures.forEach(function (f) { console.log('  - ' + f); });
    process.exit(1);
}
console.log('全部通过');
process.exit(0);
