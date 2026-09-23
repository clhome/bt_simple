// 回归守卫：插件二级弹窗（layer.open）i18n 兜底
//
// 背景：插件在自己的弹窗内用 layer.open/alert/confirm 打开的二级窗口挂到
// document.body 下，不在 translatePluginDOM 的主容器内 —— 主监听器够不着，
// 表现为「主界面已翻译、点开的子窗口仍是中文」。soft.js 的
// installPluginLayerTranslation() 在插件窗口存续期间改写 layer.open，把二级
// 窗口也交给同一插件字典翻译。
//
// 本脚本从 soft.js 抽取「真实函数体」在最小 vm 环境里执行，断言：
//   1. 无插件激活时不做任何翻译（不误伤面板自身弹层）
//   2. 插件激活时对二级窗口调用 translatePluginDOM(layero, 插件名)
//   3. 保留插件原本的 success 回调
//   4. 重复安装是幂等的（不会层层包裹）
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..', '..');
const SOFT = path.join(ROOT, 'web', 'static', 'app', 'soft.js');
const src = fs.readFileSync(SOFT, 'utf8');

function extractFn(s, name) {
    const start = s.indexOf('function ' + name + '(');
    if (start < 0) throw new Error('soft.js 缺少函数 ' + name);
    let i = s.indexOf('{', start), depth = 0;
    for (; i < s.length; i++) {
        if (s[i] === '{') depth++;
        else if (s[i] === '}') { depth--; if (depth === 0) return s.slice(start, i + 1); }
    }
    throw new Error('函数 ' + name + ' 花括号不配对');
}

const fnSrc = extractFn(src, 'installPluginLayerTranslation');
const translated = [];
const ctx = {
    window: {
        layer: {
            open: function (opts) {
                const layero = { tag: 'layer', opts };
                if (typeof opts.success === 'function') opts.success(layero, 1);
                return 1;
            }
        },
        YfI18n: { translatePluginDOM: (layero, name) => translated.push(name + ':' + layero.tag) },
        _yfActivePlugin: null
    }
};
ctx.window.window = ctx.window;
vm.createContext(ctx);
vm.runInContext(fnSrc, ctx);
ctx.installPluginLayerTranslation();

const fails = [];
function ok(cond, msg) { if (!cond) fails.push(msg); }

// 1) 无插件激活：不翻译
translated.length = 0;
ctx.window.layer.open({ content: 'x' });
ok(translated.length === 0, '无插件激活时不应翻译，实际 ' + JSON.stringify(translated));

// 2) 插件激活：翻译二级窗口，且保留原 success
ctx.window._yfActivePlugin = 'docker';
translated.length = 0;
let origSuccessCalled = false;
ctx.window.layer.open({ content: 'y', success: () => { origSuccessCalled = true; } });
ok(translated.length === 1 && translated[0] === 'docker:layer',
    '插件激活时应以插件名翻译二级窗口，实际 ' + JSON.stringify(translated));
ok(origSuccessCalled, '原 success 回调必须仍被调用');

// 3) 幂等：重复安装不叠加
ctx.installPluginLayerTranslation();
translated.length = 0;
ctx.window.layer.open({ content: 'z' });
ok(translated.length === 1, '重复安装后应仅翻译一次，实际 ' + JSON.stringify(translated));

if (fails.length) {
    console.log('FAIL');
    fails.forEach(f => console.log('  - ' + f));
    process.exit(1);
}
console.log('ALL PASS');
