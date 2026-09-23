#!/usr/bin/env node
/**
 * 插件弹窗 DOM 翻译覆盖率探针（jsdom 版，无 Chrome 依赖）
 *
 * 为什么需要它：
 *   `web/static/app/i18n.js::translatePluginDOM()` 的定向规则是**枚举式白名单**，
 *   各插件自定义的说明容器（卡片标题 / 步骤标题 / 提示框 / 内联 <strong> / <li> …）
 *   一旦不在白名单里，界面就仍是中文 —— 而语言包看起来「键全、译文全」，门禁也全绿。
 *   这是**静默失效**：静态扫描抓不到，只有真实渲染才看得见。
 *
 * 判据（oracle）：以「当前语言语言包的译文值集合」为准
 *   含 CJK 且**不在**值集合中 => 未被翻译（仍是原文）=> 真残留
 *   含 CJK 且**在**值集合中   => 已是该语言译文（如 zh-TW 的繁体）=> 正常
 *
 * 用法：
 *   node testsuite/js/dom_i18n_probe.js [--root <仓库根>] [--lang en]
 *        [--plugins a,b,c] [--i18n <覆盖用的 i18n.js 路径>]
 * 输出：stdout 一行 JSON
 *   { plugins: <扫描到的插件数>, results: [ {plugin, error, totalTexts,
 *     leftovers: [...], attrLeftovers: [...] } ], fatal: null }
 * 退出码恒为 0（判定交给调用方，避免「进程失败 = 假绿」）
 */
'use strict';

const fs = require('fs');
const path = require('path');

function arg(name, def) {
    const i = process.argv.indexOf('--' + name);
    return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}

const ROOT = path.resolve(arg('root', path.join(__dirname, '..', '..')));
const LANG = arg('lang', 'en');
const I18N = path.resolve(arg('i18n', path.join(ROOT, 'web', 'static', 'app', 'i18n.js')));
const ONLY = arg('plugins', '') ? arg('plugins').split(',').filter(Boolean) : null;
const SKIP_TAGS = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, IFRAME: 1, TEXTAREA: 1, TITLE: 1 };
const ATTRS = ['title', 'placeholder', 'alt', 'value'];

function emit(obj) {
    process.stdout.write(JSON.stringify(obj));
}

let JSDOM;
try {
    ({ JSDOM } = require(path.join(ROOT, 'node_modules', 'jsdom')));
} catch (e) {
    emit({ fatal: 'jsdom 不可用: ' + e.message, results: [], plugins: 0 });
    process.exit(0);
}

const jqSrc = fs.readFileSync(
    path.join(ROOT, 'web', 'static', 'js', 'jquery-3.7.1.min.js'), 'utf8');

let i18nSrc = fs.readFileSync(I18N, 'utf8');
const NEEDLE = 'var _currentLang = detectLanguage();';
if (i18nSrc.indexOf(NEEDLE) < 0) {
    emit({ fatal: 'i18n.js 中找不到 ' + NEEDLE + '（初始化语句已变，探针需同步更新）',
           results: [], plugins: 0 });
    process.exit(0);
}
// 强制语言：直接替换初始化语句，避免依赖 cookie / localStorage / navigator
i18nSrc = i18nSrc.replace(NEEDLE, 'var _currentLang = ' + JSON.stringify(LANG) + ';');

const pluginRoot = path.join(ROOT, 'plugins');
let names = fs.readdirSync(pluginRoot).filter(function (n) {
    return fs.existsSync(path.join(pluginRoot, n, 'index.html'));
});
if (ONLY) {
    names = names.filter(function (n) { return ONLY.indexOf(n) >= 0; });
}
names.sort();

function probe(plugin) {
    const out = { plugin: plugin, lang: LANG, error: null, totalTexts: 0,
                  leftovers: [], attrLeftovers: [] };
    let dict;
    try {
        let dp = path.join(pluginRoot, plugin, 'lang', LANG + '.json');
        if (!fs.existsSync(dp)) dp = path.join(pluginRoot, plugin, 'lang', 'zh-CN.json');
        dict = JSON.parse(fs.readFileSync(dp, 'utf8'));
    } catch (e) {
        out.error = '语言包读取失败: ' + e.message;
        return out;
    }
    let dom;
    try {
        dom = new JSDOM(
            '<!DOCTYPE html><html><head><meta charset="utf-8"></head>' +
            '<body><div id="mount"></div></body></html>',
            { runScripts: 'dangerously', url: 'http://localhost/' });
    } catch (e) {
        out.error = 'jsdom 初始化失败: ' + e.message;
        return out;
    }
    const win = dom.window;
    try {
        win.eval(jqSrc);
        win.eval(i18nSrc);
        if (!win.YfI18n || typeof win.YfI18n.translatePluginDOM !== 'function') {
            throw new Error('YfI18n.translatePluginDOM 不可用');
        }
        win._pluginDicts = {};
        win._pluginDicts[plugin] = dict;

        const html = fs.readFileSync(path.join(pluginRoot, plugin, 'index.html'), 'utf8');
        const body = html.replace(/<script\b[\s\S]*?<\/script>/gi, '');
        const mount = win.document.getElementById('mount');
        mount.innerHTML = body;
        win.YfI18n.translatePluginDOM(mount, plugin);

        const vals = {};
        Object.keys(dict).forEach(function (k) { vals[dict[k]] = 1; });
        function untranslated(s) {
            return /[\u4e00-\u9fff]/.test(s) && !vals[s];
        }
        const walker = win.document.createTreeWalker(mount, 4, null, false);
        let n;
        while ((n = walker.nextNode())) {
            const p = n.parentNode;
            if (!p || SKIP_TAGS[p.nodeName]) continue;
            const v = (n.nodeValue || '').trim();
            if (!v) continue;
            out.totalTexts++;
            if (untranslated(v)) {
                out.leftovers.push({
                    tag: p.nodeName,
                    cls: String(p.className || '').slice(0, 40),
                    text: v.slice(0, 80)
                });
            }
        }
        const all = mount.querySelectorAll('*');
        for (let i = 0; i < all.length; i++) {
            for (let k = 0; k < ATTRS.length; k++) {
                const av = all[i].getAttribute(ATTRS[k]);
                if (av && untranslated(av.trim())) {
                    out.attrLeftovers.push({
                        tag: all[i].nodeName, attr: ATTRS[k], text: av.slice(0, 80)
                    });
                }
            }
        }
    } catch (e) {
        out.error = String((e && e.message) || e);
    } finally {
        try { win.close(); } catch (e) { /* ignore */ }
    }
    return out;
}

const results = names.map(probe);
emit({ fatal: null, lang: LANG, plugins: names.length, results: results });
