// soft.js::addVersion 安装弹窗的行为测试（Node，无外部依赖）
//
// 为什么要有它：Redis「3 个系列」的界面收敛全靠这段代码 ——
//   * 选项必须带 value（`yes` 回调靠 `$('#selectVersion').val()` 解析 "redis 7.2"，
//     而选项文本里现在多了「· 说明 (推荐)」，没有 value 就会把说明当成版本号）；
//   * 默认/推荐系列必须**预选**（用户点安装不选就直接提交时，装的是推荐版本）；
//   * 有推荐系列时按后端声明顺序列（7.2 在最前），没有时仍按历史行为倒序
//     （PHP/mysql 等共存插件依赖倒序把最新版放最前）。
//
// 做法：从 web/static/app/soft.js **原样抽取** addVersion 函数源码，在 Node 里
// 用桩件求值，捕获 layer.open 收到的 HTML 后断言。测的是真实生产代码，不是复制品。
//
// 用法：node testsuite/i18n_scripts/tools/test_soft_addversion_series.js
//       YF_SOFT_JS=<替身路径> 可指向变异体（供 python 侧做变异自证）
// 退出码：0 全部通过 / 1 断言失败 / 2 无法定位生产代码

'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..', '..');
const SOFT_JS = process.env.YF_SOFT_JS || path.join(ROOT, 'web', 'static', 'app', 'soft.js');

const src = fs.readFileSync(SOFT_JS, 'utf8');

// ---------------------------------------------------------------------------
// 抽取 addVersion（按花括号配平；匹配时跳过字符串字面量里的括号）
// ---------------------------------------------------------------------------
function extractFunction(text, startMarker) {
    const start = text.indexOf(startMarker);
    if (start < 0) return '';
    let depth = 0;
    let quote = null;
    for (let i = start; i < text.length; i++) {
        const c = text[i];
        if (quote) {
            if (c === '\\') { i++; continue; }
            if (c === quote) quote = null;
            continue;
        }
        if (c === "'" || c === '"' || c === '`') { quote = c; continue; }
        if (c === '{') depth++;
        else if (c === '}') {
            depth--;
            if (depth === 0) return text.slice(start, i + 1);
        }
    }
    return '';
}

const fnSrc = extractFunction(src, 'function addVersion(');
if (!fnSrc) {
    console.error('[FATAL] 无法在 soft.js 中定位 addVersion');
    process.exit(2);
}
for (const marker of ['data-vdefault', 'data-vnotes']) {
    if (src.indexOf(marker) < 0) {
        console.error('[FATAL] soft.js 的安装链接没有 ' + marker + '（系列元数据丢了）');
        process.exit(2);
    }
}

let failures = 0;
function ok(cond, msg) {
    if (!cond) {
        failures++;
        console.error('  [FAIL] ' + msg);
    } else {
        console.log('  [ok  ] ' + msg);
    }
}
function eq(actual, expected, msg) {
    ok(actual === expected, msg + '（期望 ' + JSON.stringify(expected)
        + '，实际 ' + JSON.stringify(actual) + '）');
}

// ---------------------------------------------------------------------------
// 桩件
// ---------------------------------------------------------------------------
function esc(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const NOTES = {
    '7.2': 'soft.redis_series_72',
    '8.2': 'soft.redis_series_82',
    '6.2': 'soft.redis_series_62',
};
const NOTE_TEXT = {
    'soft.redis_series_72': '经典稳定',
    'soft.redis_series_82': 'LTS 长期演进',
    'soft.redis_series_62': '极简轻量',
    'soft.recommended': '推荐',
};

function makeEnv(attrMap) {
    const captured = { content: '' };
    function $(sel) {
        const self = {
            attr: function (name) { return Object.prototype.hasOwnProperty.call(attrMap, name) ? attrMap[name] : undefined; },
            val: function () { return ''; },
            on: function () { return self; },
            off: function () { return self; },
            find: function () { return self; },
            prop: function () { return false; },
            addClass: function () { return self; },
            removeClass: function () { return self; },
            siblings: function () { return self; },
            each: function () { return self; },
            length: 0,
        };
        return self;
    }
    $.get = function (url, cb) {
        if (typeof cb === 'function') cb('');
        return { fail: function () { return this; } };
    };
    const layer = {
        open: function (opts) { captured.content = String(opts.content || ''); return 1; },
        msg: function () { return 1; },
        close: function () {}, closeAll: function () {},
    };
    function t(key, args, defaultText) {
        if (Object.prototype.hasOwnProperty.call(NOTE_TEXT, key)) return NOTE_TEXT[key];
        if (typeof args === 'string') return args;      // t(key, '默认文案')
        if (typeof defaultText === 'string') return defaultText || key;
        return key;
    }
    const window_ = { YfI18n: null };
    const lan = { soft: {} };
    const console_ = console;
    const factory = new Function(
        '$', 'layer', 't', 'yfSoftText', 'yfSoftJsStr', 'window', 'lan', 'console',
        fnSrc + '\nreturn addVersion;');
    const addVersion = factory($, layer, t, esc, function (s) { return s; }, window_, lan, console_);
    return { addVersion: addVersion, captured: captured };
}

function optionsOf(html) {
    const out = [];
    const re = /<option\b([^>]*)>([\s\S]*?)<\/option>/g;
    let m;
    while ((m = re.exec(html)) !== null) {
        const attrs = m[1] || '';
        const v = /value="([^"]*)"/.exec(attrs);
        out.push({
            value: v ? v[1] : '',
            hasValueAttr: !!v,
            selected: /\bselected\b/.test(attrs),
            text: m[2],
        });
    }
    return out;
}

// ---------------------------------------------------------------------------
// 用例 A：Redis（后端声明了推荐系列与说明）
// ---------------------------------------------------------------------------
console.log('[A] Redis 3 系列：声明顺序 + 预选推荐 + 说明文案');
{
    const attrMap = {
        'data-vdefault': '7.2',
        'data-vnotes': JSON.stringify(NOTES),
    };
    const env = makeEnv(attrMap);
    env.addVersion('redis', '7.2|8.2|6.2', 'soft', {}, 'Redis', 0);
    const opts = optionsOf(env.captured.content);
    eq(opts.length, 3, '必须恰好 3 个系列选项');
    eq(opts.map(function (o) { return o.value; }).join(','),
        'redis 7.2,redis 8.2,redis 6.2',
        '选项 value 必须是「插件名 系列号」且按声明顺序（7.2 在最前）');
    ok(opts.every(function (o) { return o.hasValueAttr; }),
        '每个 option 都必须显式带 value（否则 .val() 会回退到含说明的文本）');
    eq(opts.filter(function (o) { return o.selected; }).length, 1,
        '必须恰好预选一个选项');
    ok(opts[0].selected, '预选的必须是推荐系列 7.2（第一个）');
    ok(opts[0].text.indexOf('经典稳定') >= 0, '7.2 的选项要带说明文案');
    ok(opts[0].text.indexOf('推荐') >= 0, '推荐系列要标「推荐」');
    ok(opts[1].text.indexOf('LTS') >= 0, '8.2 的选项要带说明文案');
    ok(opts[2].text.indexOf('极简轻量') >= 0, '6.2 的选项要带说明文案');
    ok(env.captured.content.indexOf('selectVersion') >= 0, '必须渲染成下拉框');
}

// ---------------------------------------------------------------------------
// 用例 B：没有系列元数据的插件 —— 保持历史行为（倒序，最新在最前，不预选）
// ---------------------------------------------------------------------------
console.log('[B] 无推荐系列：沿用历史倒序');
{
    const env = makeEnv({});
    env.addVersion('php', '74|80|81|82|83', '', {}, 'PHP', 0);
    const opts = optionsOf(env.captured.content);
    eq(opts.map(function (o) { return o.value; }).join(','),
        'php 83,php 82,php 81,php 80,php 74',
        '没有推荐系列时必须倒序（最新在最前），不能改变既有插件的行为');
    eq(opts.filter(function (o) { return o.selected; }).length, 0,
        '没有推荐系列时不加 selected（保持浏览器默认）');
    ok(opts.every(function (o) { return o.text.indexOf('·') < 0; }),
        '没有说明文案时不能出现多余的「·」分隔符');
}

// ---------------------------------------------------------------------------
// 用例 C：notes 是坏 JSON —— 不能抛异常、不能把弹窗搞坏
// ---------------------------------------------------------------------------
console.log('[C] 坏 JSON 容错');
{
    const env = makeEnv({ 'data-vdefault': '7.2', 'data-vnotes': '{not-json' });
    let threw = false;
    try {
        env.addVersion('redis', '7.2|8.2|6.2', 'soft', {}, 'Redis', 0);
    } catch (e) {
        threw = true;
        console.error('  异常：' + e.message);
    }
    ok(!threw, 'vnotes 是坏 JSON 时不能抛异常');
    const opts = optionsOf(env.captured.content);
    eq(opts.length, 3, '坏 JSON 时仍要有 3 个选项');
    ok(opts[0].selected, '坏 JSON 时推荐系列仍应预选（vdefault 是独立字段）');
}

if (failures) {
    console.error('\n[FAIL] ' + failures + ' 项断言失败');
    process.exit(1);
}
console.log('\n[PASS] addVersion 系列化行为全部通过');
