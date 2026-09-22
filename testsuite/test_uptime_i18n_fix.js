const fs = require('fs');
const vm = require('vm');

const context = {
    window: {},
    document: {
        cookie: '',
        addEventListener: () => {},
        getElementsByTagName: () => [],
        querySelectorAll: () => [],
        head: { appendChild: () => {} }
    },
    location: { search: '', href: '' },
    navigator: { language: 'en-US' },
    localStorage: { getItem: () => null, setItem: () => {} }
};
context.window = context;
context.$ = function() {
    return { ready: () => {} };
};
vm.createContext(context);

// 加载英文语言包
const lanCode = fs.readFileSync('web/static/language/en/lan.js', 'utf8');
vm.runInContext(lanCode, context);

// 提取 i18n.js 中的代码并执行
const i18nCode = fs.readFileSync('web/static/app/i18n.js', 'utf8');
vm.runInContext(i18nCode, context);

const t = context.window.t;

const res1 = t('public.SYS_BOOT_TIME', [38, 3, 46]);
const res2 = t('public.SYS_BOOT_TIME', 38, 3, 46);
const prefix = t('index.running_prefix', '已运行: ');

console.log('前缀: ' + prefix);
console.log('测试 1 (数组形式): ' + prefix + res1);
console.log('测试 2 (变长形式): ' + prefix + res2);

if (res1.includes('{') || res2.includes('{')) {
    console.error('FAIL: 结果中仍包含大括号 {} !');
    process.exit(1);
}

if (res1 !== '38 day 3 hours 46 minutes' || res2 !== '38 day 3 hours 46 minutes') {
    console.error('FAIL: 文本内容不符合预期:', res1, res2);
    process.exit(1);
}

console.log('[PASS] 运行时间多语言占位符替换完美，不再有 {} 符号！');
