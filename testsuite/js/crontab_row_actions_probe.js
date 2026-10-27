/**
 * 计划任务列表「行内操作」前端守卫夹具（由 testsuite/test_crontab_frontend_inline_js.py 调用）。
 *
 * 用法：在仓库根目录执行  node testsuite/js/crontab_row_actions_probe.js
 * 输出：一行 JSON {"ok":bool,"checks":[...],"failures":[...]}
 *
 * 为什么需要它：真机 Chrome 复现过两次同类事故，都出在「把数据拼进内联代码」：
 *   a) 拼接处少写了一个收尾单引号（getLogs('' + id + ", '"）→ 生成
 *      getLogs('437, 'test') → 点「日志」报
 *      Uncaught SyntaxError: missing ) after argument list (at …:1:9)，
 *      每一行都点不动（和任务名无关的硬错，planDel/删除同样废掉）；
 *   b) 任务名本身是用户输入（创建/导入 JSON/从服务器同步），可以合法包含
 *      双引号、单引号、反斜杠、换行，拼进 onclick 会被 HTML 解析截断。
 *
 * 现在用户数据只允许出现在 data-* 属性里（经 cronEsc 转义），点击由事件委派处理。
 * 本夹具用真实 HTML 解析器（jsdom）回读属性，断言：
 *   1) 行内不再有任何携带数据的 javascript:/onclick；
 *   2) 恶意/畸形任务名在 data-* 里能原样取回（不篡改名字）；
 *   3) 列表 HTML 不被任务名注入标签；
 *   4) 日志弹窗里「执行任务」按钮不带内联 JS，且点击时参数正确、名字只作文本显示。
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const {JSDOM} = require('jsdom');

const ROOT = path.resolve(__dirname, '..', '..');
const CRONTAB_JS = process.env.CRONTAB_JS || path.join(ROOT, 'web', 'static', 'app', 'crontab.js');

const checks = [];
const failures = [];
function check(name, cond, detail) {
  if (cond) {
    checks.push(name);
  } else {
    failures.push(detail ? name + ' :: ' + detail : name);
  }
}

const src = fs.readFileSync(CRONTAB_JS, 'utf8');
// 注释里会提到旧写法（为了解释为什么不能这么写），断言只看可执行代码
const LINE_RE = new RegExp('\r?\n');
const codeOnly = src.split(LINE_RE).filter(function (line) {
  return line.trim().indexOf('//') !== 0;
}).join('\n');

// ---- 0. 源码层：内联 JS 拼接必须彻底消失 ----
const forbidden = [
  'javascript:startTask(',
  'javascript:getLogs(',
  'javascript:editTaskInfo(',
  'javascript:planDel(',
  'onclick="startTask(',
  'function cronEscJs('
];
for (const bad of forbidden) {
  check('源码不再包含 ' + bad, codeOnly.indexOf(bad) === -1);
}
check('源码含 data-cron-act 委派', codeOnly.indexOf('data-cron-act="log"') !== -1);
check('源码含事件委派注册',
  codeOnly.indexOf("$(document).off('click.cronRowAct').on('click.cronRowAct', '.cron-row-act'") !== -1);

// ---- 1. 搭一个只有本页需要的假环境 ----
const dom = new JSDOM('<!doctype html><html><body><table><tbody id="cronbody"></tbody></table><ul id="softPage"></ul></body></html>',
  {runScripts: 'outside-only'});
const win = dom.window;

win.lan = {
  crontab: {},
  public: {execute: '执行', edit: '编辑', log: '日志', del: '删除', normal: '正常'},
  site: {}
};
win.t = function (key, dflt) {
  return typeof dflt === 'string' ? dflt : '';
};

const bindings = [];
function jq(sel) {
  const obj = {
    val: function () { return ''; },
    html: function (v) {
      if (v === undefined) { return win.__htmlMap[sel] || ''; }
      win.__htmlMap[sel] = v;   // 按选择器存：#cronbody 与 #softPage 互不覆盖
      return obj;
    },
    on: function (ev, s, fn) { bindings.push({ev: ev, sel: s, fn: fn}); return obj; },
    off: function () { return obj; },
    prop: function () { return false; },
    find: function () {
      return {css: function () { return {}; }, on: function () { return {}; }};
    },
    css: function () { return obj; },
    scrollTop: 0
  };
  return obj;
}
jq.post = function (url, data, cb) { win.__posts.push({url: url, data: data, cb: cb}); };
win.$ = jq;
win.layer = {
  msg: function () { return 0; },
  close: function () {},
  closeAll: function () {},
  confirm: function () { return 0; },
  alert: function () {},
  open: function (opts) { win.__open = opts; return 1; }
};
win.setInterval = function () { return 0; };
win.clearInterval = function () {};
win.setSortUI = function () {};   // crontab.html 里的内联函数，本夹具不测排序 UI
win.__posts = [];
win.__htmlMap = {};

vm.runInContext(src, dom.getInternalVMContext ? dom.getInternalVMContext() : win);

const realGetLogs = win.getLogs;

// 事件委派是否注册
check('行内操作注册了事件委派', bindings.some(function (b) {
  return b.ev === 'click.cronRowAct' && b.sel === '.cron-row-act' && typeof b.fn === 'function';
}));
const delegated = (bindings.filter(function (b) { return b.sel === '.cron-row-act'; })[0] || {}).fn;

// ---- 2. 恶劣任务名：列表渲染 ----
const BACKSLASH = String.fromCharCode(92);
const QUOTE = String.fromCharCode(34);
const APOS = String.fromCharCode(39);
const NL = String.fromCharCode(10);
const hostileNames = [
  'test',
  '[系统任务] ' + QUOTE + '/root/.acme.sh/acme.sh' + QUOTE + ' --cron --home ' + QUOTE + '/root/.acme.sh' + QUOTE,
  'it' + APOS + 's a ' + APOS + 'trap' + APOS,
  'back' + BACKSLASH + 'slash',
  'line' + NL + 'break',
  '</a><img src=x onerror=alert(1)>',
  '中文名（含括号）[clean]'
];

for (const name of hostileNames) {
  const rdata = {
    status: true, msg: '', page: '', backup_hook: [],
    data: [{
      id: 42, name: name, type: '每天', cycle: '每天 1点30分 执行', save: '', backup_to: 'localhost',
      stype: 'toShell', attr: '', day_type: '0', last_run_time: '', sync_ok: true, status: '1'
    }]
  };
  win.$.post = function (url, data, cb) { cb(rdata); };
  win.getCronData(1);
  const html = win.__htmlMap['#cronbody'] || '';
  const tag = 'name=' + JSON.stringify(name);

  check('列表不被任务名注入标签 ' + tag, html.indexOf('<img') === -1 && html.indexOf('<script') === -1);

  const doc = new JSDOM('<table><tbody>' + html + '</tbody></table>').window.document;
  const anchors = Array.prototype.slice.call(doc.querySelectorAll('a'));
  check('每行有 4 个行内操作 ' + tag, anchors.length === 4, 'anchors=' + anchors.length);

  for (const a of anchors) {
    const href = a.getAttribute('href') || '';
    check('行内链接不带参数化 JS（' + a.textContent + '）' + tag, /^javascript:;?$/.test(href), 'href=' + JSON.stringify(href));
    check('行内链接无 onclick（' + a.textContent + '）' + tag, a.getAttribute('onclick') === null);
  }

  const acts = Array.prototype.slice.call(doc.querySelectorAll('[data-cron-act]')).map(function (el) {
    return el.getAttribute('data-cron-act');
  });
  for (const act of ['run', 'edit', 'log', 'del', 'toggle']) {
    check('存在操作 data-cron-act=' + act + ' ' + tag, acts.indexOf(act) !== -1, 'got=' + acts.join(','));
  }

  // 名字必须能原样取回（不能被转义污染）
  const logEl = doc.querySelector('[data-cron-act="log"]');
  check('日志按钮 data-cron-id 正确 ' + tag, !!logEl && logEl.getAttribute('data-cron-id') === '42');
  check('日志按钮 data-cron-name 原样回读 ' + tag,
    !!logEl && logEl.getAttribute('data-cron-name') === name,
    logEl ? JSON.stringify(logEl.getAttribute('data-cron-name')) : 'missing');

  // ---- 3. 点击委派：真正调到对应函数、参数正确 ----
  const calls = [];
  win.startTask = function (id, nm, isOpen) { calls.push(['startTask', id, nm, isOpen]); };
  win.editTaskInfo = function (id) { calls.push(['editTaskInfo', id]); };
  win.getLogs = function (id, nm) { calls.push(['getLogs', id, nm]); };
  win.planDel = function (id, nm) { calls.push(['planDel', id, nm]); };
  win.setTaskStatus = function (id, st) { calls.push(['setTaskStatus', id, st]); };

  const map = {run: 'startTask', edit: 'editTaskInfo', log: 'getLogs', del: 'planDel', toggle: 'setTaskStatus'};
  for (const act of Object.keys(map)) {
    const el = doc.querySelector('[data-cron-act="' + act + '"]');
    check('找到操作元素 ' + act + ' ' + tag, !!el);
    if (!el) { continue; }
    delegated.call(el, {preventDefault: function () {}});
    const last = calls[calls.length - 1] || [];
    check('点击 ' + act + ' 调到 ' + map[act] + ' ' + tag, last[0] === map[act], 'got=' + JSON.stringify(last));
    check('点击 ' + act + ' 传对 id ' + tag, String(last[1]) === '42', 'got=' + JSON.stringify(last));
    if (act === 'log' || act === 'del') {
      check('点击 ' + act + ' 传对名字 ' + tag, last[2] === name, 'got=' + JSON.stringify(last));
    }
    if (act === 'toggle') {
      check('启用按钮状态值正确 ' + tag, last[2] === 0, 'got=' + JSON.stringify(last));
    }
  }
}

// ---- 4. 日志弹窗：「执行任务」不带内联 JS，名字只作文本 ----
win.getLogs = realGetLogs; // 还原第 3 段的 spy
for (const name of hostileNames) {
  const tag = 'name=' + JSON.stringify(name);
  if (name.indexOf(NL) !== -1) { continue; } // 换行在属性/文本里对比意义不大
  win.__open = null;
  win.getLogs('42', name);
  const opts = win.__open;
  check('日志弹窗被打开 ' + tag, !!opts);
  if (!opts) { continue; }
  const content = String(opts.content || '');
  check('日志弹窗无内联 onclick ' + tag, content.indexOf('onclick') === -1);
  check('日志弹窗不被任务名注入标签 ' + tag, content.indexOf('<img') === -1 && content.indexOf('<script') === -1);

  const doc = new JSDOM('<div>' + content + '</div>').window.document;
  const runBtn = doc.querySelector('#cron_log_run');
  check('日志弹窗有执行任务按钮 ' + tag, !!runBtn);
  // 名字在弹窗里只能作为文本出现（等价于原文）
  const spans = Array.prototype.slice.call(doc.querySelectorAll('span'))
    .filter(function (s) { return s.textContent === name; });
  check('弹窗里任务名以纯文本呈现 ' + tag, spans.length > 0);

  // 点击执行：闭包参数必须原样（含引号/反斜杠）
  let clickHandler = null;
  const fakeLayero = {
    find: function (sel) {
      return {
        css: function () { return {}; },
        // 弹窗里的按钮行还要再 find 一层（layero.find('.layui-layer-btn').find('.layui-layer-btn0').css(...)）
        find: function () { return {css: function () { return {}; }}; },
        on: function (ev, fn) { if (sel === '#cron_log_run' && ev === 'click') { clickHandler = fn; } return {}; }
      };
    }
  };
  opts.success(fakeLayero, 1);
  check('执行任务按钮已绑定 click ' + tag, typeof clickHandler === 'function');
  const calls = [];
  win.startTask = function (id, nm, isOpen) { calls.push([id, nm, isOpen]); };
  win.$.post = function () {};
  if (typeof clickHandler === 'function') {
    clickHandler();
    const got = calls[0] || [];
    check('弹窗内执行任务传对 id ' + tag, String(got[0]) === '42', 'got=' + JSON.stringify(got));
    check('弹窗内执行任务传对名字 ' + tag, got[1] === name, 'got=' + JSON.stringify(got));
    check('弹窗内执行任务带 is_log_open ' + tag, got[2] === true, 'got=' + JSON.stringify(got));
  }
}

// ---- 5. 空 id 不发请求 ----
win.getLogs = realGetLogs;
win.__open = null;
win.__posts = [];
win.getLogs(undefined, 'x');
check('无 id 时不打开日志弹窗', win.__open === null);
check('无 id 时不发日志请求', win.__posts.length === 0);

console.log(JSON.stringify({ok: failures.length === 0, checks: checks, failures: failures}));
process.exit(failures.length === 0 ? 0 : 1);
