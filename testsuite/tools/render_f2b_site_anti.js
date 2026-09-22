/**
 * fail2ban「网站防护」页职责边界提示条 —— 真实渲染验证工装
 *
 * 目的：静态断言只能证明「源码里有这段文案」，不能证明「渲染出来是对的」。
 * 本工装用最小替身（jQuery / layer / api / pt）在 Node 里真正执行
 * `f2bSiteAnti()`，把渲染结果交给 Python 侧断言。
 *
 * 用法：node test/tools/render_f2b_site_anti.js <语言> <状态> [js路径]
 *   语言：zh-CN | zh-TW | en | de | fr | it
 *   状态：active        —— 仍在重复接管 Web 层（应出黄色警告条 + 停用按钮）
 *         delegated     —— 已停用，联动已开启（应出绿色已托管条 + 内核层说明）
 *         delegated_off —— 已停用，联动未开启（应出绿色已托管条 + 提示去开启）
 *         clean         —— 未停用也没接管（未配置）→ 同样走绿色已托管条
 *   js路径：可选，默认用仓库当前的 fail2ban.js。
 *           传别的路径即可渲染历史版本（如 `git show HEAD:...` 导出的旧文件），
 *           用于产出可信的「修改前」对照，而不是手工拼一份假 HTML。
 *
 * 输出：stdout 打印渲染出的 HTML 片段（单行）。
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', '..');
const LANG = process.argv[2] || 'zh-CN';
const STATE = process.argv[3] || 'delegated';
const JS_PATH = process.argv[4] || path.join(ROOT, 'plugins', 'fail2ban', 'js', 'fail2ban.js');

// ---- 语言包 ----
const dict = JSON.parse(
    fs.readFileSync(path.join(ROOT, 'plugins', 'fail2ban', 'lang', LANG + '.json'), 'utf8'));

function pt(key, arg1) {
    let out = Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : key;
    if (arg1 !== undefined && arg1 !== null) {
        out = String(out).replace('{1}', arg1);
    }
    return out;
}

// ---- 最小 DOM / jQuery 替身 ----
const captured = { html: '' };

function makeNode() {
    const node = {
        length: 1,
        html(v) {
            if (v === undefined) return captured.html;
            captured.html = v;
            return node;
        },
        on() { return node; },
        each() { return node; },
        attr() { return ''; },
        val() { return ''; },
        is() { return false; },
        find() { return node; },
        append() { return node; },
        remove() { return node; },
        text() { return ''; },
        addClass() { return node; },
        removeClass() { return node; }
    };
    return node;
}

function $(sel) {
    return makeNode();
}
$.each = function (obj, cb) {
    if (Array.isArray(obj)) {
        for (let i = 0; i < obj.length; i++) cb(i, obj[i]);
    } else if (obj && typeof obj === 'object') {
        Object.keys(obj).forEach(function (k) { cb(k, obj[k]); });
    }
    return obj;
};
$.ajax = function () {};
$.get = function () {};

global.$ = $;
global.jQuery = $;
global.window = { YfI18n: { getLanguage: function () { return LANG; } }, innerHeight: 1000 };
global.document = { title: '' };

global.layer = {
    msg: function () { return 0; },
    close: function () {},
    closeAll: function () {},
    confirm: function () {},
    load: function () { return 0; }
};

global.YfI18n = {
    createPluginTranslator: function () { return pt; },
    getLanguage: function () { return LANG; }
};

// ---- 构造 get_anti_info 响应 ----
function buildPayload() {
    const offRule = function (mode, maxretry) {
        return { mode: mode, port: '80,443', maxretry: maxretry, findtime: '60',
                 bantime: '86400', act: 'false' };
    };
    const onRule = function (mode, maxretry) {
        return { mode: mode, port: '80,443', maxretry: maxretry, findtime: '60',
                 bantime: '86400', act: 'true' };
    };

    const site = (STATE === 'active')
        ? [onRule('global-cc', '60'), onRule('global-scan', '30')]
        : [offRule('global-cc', '60'), offRule('global-scan', '30')];

    return {
        status: true,
        data: {
            server: [], site: site, strict: true,
            op_waf: {
                installed: true,
                linked: STATE !== 'delegated_off',
                spool: '/www/server/op_waf/logs/ban_spool.log',
                jail: 'op-waf'
            },
            op_waf_link: { bantime: 86400 }
        }
    };
}

const payload = buildPayload();

global.YfPlugin = {
    createApi: function () {
        return {
            post: function (func, ver, args, cb) {
                if (func === 'get_anti_info') {
                    cb({ data: JSON.stringify(payload) });
                } else if (cb) {
                    cb({ data: JSON.stringify({ status: true, msg: 'ok' }) });
                }
            }
        };
    }
};

// ---- 加载插件 JS（去掉末尾的自动初始化，避免依赖真实 DOM） ----
let src = fs.readFileSync(JS_PATH, 'utf8');
// 屏蔽页面初始化入口（若存在）
src = src.replace(/^\s*\$\(function[\s\S]*$/m, '');

const vm = require('vm');
const sandbox = {
    $: $, jQuery: $, window: global.window, document: global.document,
    layer: global.layer, YfPlugin: global.YfPlugin, YfI18n: global.YfI18n,
    console: console, setTimeout: setTimeout, JSON: JSON, Math: Math,
    parseInt: parseInt, parseFloat: parseFloat, String: String, Number: Number,
    Array: Array, Object: Object, RegExp: RegExp, Date: Date, isNaN: isNaN,
    encodeURIComponent: encodeURIComponent, decodeURIComponent: decodeURIComponent
};
sandbox.global = sandbox;
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: 'fail2ban.js' });

vm.runInContext('f2bSiteAnti();', sandbox, { filename: 'invoke.js' });

process.stdout.write(captured.html.replace(/\s*\n\s*/g, ''));
