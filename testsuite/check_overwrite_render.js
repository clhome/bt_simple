const fs = require('fs');
const path = require('path');
const vm = require('vm');

const baseDir = path.resolve(__dirname, '..');
const filesJsPath = path.join(baseDir, 'web/static/app/files.js');

if (!fs.existsSync(filesJsPath)) {
    console.error(`[MISSING] ${filesJsPath} does not exist`);
    process.exit(1);
}

const content = fs.readFileSync(filesJsPath, 'utf8');

// 提取 renderFileOverwriteHtml 函数代码
const startMarker = 'function renderFileOverwriteHtml(result)';
const startIndex = content.indexOf(startMarker);
if (startIndex === -1) {
    console.error(`[ERROR] ${startMarker} not found in files.js`);
    process.exit(1);
}

// 找到函数结尾
const endMarker = '\n}\n\n//粘贴';
const endIndex = content.indexOf(endMarker, startIndex);
if (endIndex === -1) {
    console.error(`[ERROR] End of renderFileOverwriteHtml not found in files.js`);
    process.exit(1);
}

const fnCode = content.substring(startIndex, endIndex + 2); // 包含最后的 }

// 模拟上下文环境
function toSize(b) {
    if (b >= 1024 * 1024) return (b / 1024 / 1024).toFixed(2) + ' MB';
    if (b >= 1024) return (b / 1024).toFixed(2) + ' KB';
    return b + ' B';
}

function getMatchTime(t) {
    return '2026/09/08 09:41:11';
}

function t(key, defVal) {
    return defVal;
}

const sandbox = {
    toSize: toSize,
    getMatchTime: getMatchTime,
    t: t,
    window: {},
    lan: { files: {} }
};

const ctx = vm.createContext(sandbox);

// renderFileOverwriteHtml 会把文件名拼进 HTML（含 title 属性位），依赖 public.js 的
// yfMsgEscape（运行时由基础模板 layout.html 先行加载，故生产环境必然存在）。
// 这里抽取**真实实现**注入沙箱，而不是手写替身 —— 替身会与生产口径悄悄漂移。
const publicJsPath = path.join(baseDir, 'web/static/app/public.js');
const publicJs = fs.readFileSync(publicJsPath, 'utf8');
const pStart = publicJs.indexOf('// safeMessage 的 HTML 安全层');
const pEnd = publicJs.indexOf('function safeMessage(', pStart);
if (pStart === -1 || pEnd === -1 || pEnd <= pStart) {
    console.error('[ERROR] 无法从 public.js 抽取 yfMsgEscape（净化层标记缺失？）');
    process.exit(1);
}
new vm.Script(publicJs.substring(pStart, pEnd) + '\nthis.yfMsgEscape = yfMsgEscape;').runInContext(ctx);
if (typeof sandbox.yfMsgEscape !== 'function') {
    console.error('[ERROR] yfMsgEscape 未能注入沙箱');
    process.exit(1);
}

const script = new vm.Script(fnCode + '\nthis.renderFileOverwriteHtml = renderFileOverwriteHtml;');
script.runInContext(ctx);

if (typeof sandbox.renderFileOverwriteHtml !== 'function') {
    console.error('[ERROR] renderFileOverwriteHtml is not a function');
    process.exit(1);
}

// 模拟测试数据: 旧文件 200KB (204800字节), 新文件 501KB (513024字节)
const testData = [{
    filename: '1.txt',
    size: 204800,
    new_size: 513024,
    mtime: '1725759671'
}];

const html = sandbox.renderFileOverwriteHtml(testData);

if (!html.includes('200.00 KB')) {
    console.error('[FAIL] Missing old size 200.00 KB in rendered HTML');
    process.exit(1);
}

if (!html.includes('501.00 KB')) {
    console.error('[FAIL] Missing new size 501.00 KB in rendered HTML');
    process.exit(1);
}

if (!html.includes('&lt;=')) {
    console.error('[FAIL] Missing <= comparison symbol in rendered HTML');
    process.exit(1);
}

if (!html.includes('1.txt')) {
    console.error('[FAIL] Missing filename 1.txt in rendered HTML');
    process.exit(1);
}

if (!html.includes('目标目录已存在以下同名文件')) {
    console.error('[FAIL] Missing tip message banner in rendered HTML');
    process.exit(1);
}

// ---- 文件名 XSS：恶意文件名不得在渲染结果中造出活标签 ----
// 文件名同时落在 title="..." 属性位与单元格文本位，未转义时可越出属性执行脚本。
const evilNames = [
    '"><img src=x onerror=alert(1)>.txt',
    "<script>alert(1)</script>",
    "' onmouseover='alert(1)",
    '<svg onload=alert(1)>'
];
const evilHtml = sandbox.renderFileOverwriteHtml(
    evilNames.map(function (n) { return { filename: n, size: 1024, mtime: '1725759671' }; }));

['<img', '<script', '<svg'].forEach(function (bad) {
    if (evilHtml.indexOf(bad) !== -1) {
        console.error('[FAIL] 恶意文件名在渲染结果中产生了活标签: ' + bad);
        process.exit(1);
    }
});
// 事件属性只能以转义文本出现，不得成为标签属性。
// 必须「先取活标签、再剥掉引号内的值」：
//   - 直接对整段 HTML 跑 /\son\w+=/ 会被转义文本里的 ` onerror=` 误判；
//   - 直接对标签跑也会被属性值误判（title="&quot;…onerror=…"）。
function liveTags(s) {
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
const badTags = liveTags(evilHtml).filter(function (tag) {
    const stripped = tag.replace(/"[^"]*"/g, '""').replace(/'[^']*'/g, "''");
    return /\son[a-z]+\s*=/i.test(stripped);
});
if (badTags.length) {
    console.error('[FAIL] 渲染结果中存在事件属性: ' + badTags[0]);
    process.exit(1);
}
// 自证：确认测试向量本身确实含危险片段（否则上面的断言可能恒真）
if (evilNames.join('').indexOf('<img') === -1) {
    console.error('[FAIL] 测试向量无效');
    process.exit(1);
}
console.log('[PASS] 恶意文件名已被转义，未产生活标签');

console.log('[PASS] renderFileOverwriteHtml output matches 200KB <= 501KB comparison specifications perfectly!');
