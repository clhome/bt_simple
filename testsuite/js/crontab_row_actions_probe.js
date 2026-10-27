/**
 * 计划任务列表「行内操作」前端夹具（由 testsuite/test_crontab_frontend_inline_js.py 调用）。
 *
 * 用法：在仓库根目录执行  node testsuite/js/crontab_row_actions_probe.js
 * 输出：一行 JSON {"ok":bool,"checks":[...],"failures":[...],"html":{...},"calls":[...]}
 *
 * 为什么需要它：真机 Chrome 复现过两次同类事故，都出在「把数据拼进内联代码」：
 *   a) 拼接处少写了一个收尾单引号（getLogs(\'' + id + ", '"）→ 生成
 *      getLogs('437, 'test') → 点「日志」报
 *      Uncaught SyntaxError: missing ) after argument list (at …:1:9)，
 *      每一行都点不动（和任务名无关的硬错，planDel/删除同样废掉）；
 *   b) 任务名本身是用户输入（创建/导入 JSON/从服务器同步），可以合法包含
 *      双引号、单引号、反斜杠、换行，拼进 onclick 会被 HTML 解析截断。
 *
 * ## 为什么**不用** jsdom（2026-10-27 CI 红）
 *   本夹具原来 `require('jsdom')`，而 GitHub Actions 只装 Python 依赖，
 *   没有 node_modules → `Error: Cannot find module 'jsdom'` → 门禁红。
 *   现在拆成两层：
 *     * 本文件只负责「真跑 crontab.js」（vm + 最小桩），把**生成的 HTML 字符串**
 *       和**委派点击时的实参**吐给 Python；
 *     * Python 侧（test_crontab_frontend_inline_js.py）用标准库 html.parser
 *       做**真实 HTML 解析**（属性实体解码、引号截断都按浏览器语义），
 *       再用解析出的 data-* 喂给 Node 侧的委派函数验证实参。
 *   这样既不依赖第三方模块，又保留「真实 HTML 解析」这一关键断言能力。
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

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

// ---- 1. 最小运行环境（不依赖任何 DOM 库）----
const sandbox = {
  console: console,
  JSON: JSON,
  String: String,
  Number: Number,
  Object: Object,
  Array: Array,
  Math: Math,
  RegExp: RegExp,
  encodeURIComponent: encodeURIComponent,
  parseInt: parseInt,
  setTimeout: function () { return 0; },
  setInterval: function () { return 0; },
  clearInterval: function () {},
  __htmlMap: {},
  __posts: [],
  __open: null,
  __calls: [],
  setSortUI: function () {},
  document: {
    visibilityState: 'visible',
    getElementById: function () { return null; },
    addEventListener: function () {},
    createElement: function () { return {style: {}, appendChild: function () {}}; }
  }
};
sandbox.window = sandbox;
sandbox.lan = {
  crontab: {},
  public: {execute: '执行', edit: '编辑', log: '日志', del: '删除', normal: '正常'},
  site: {}
};
sandbox.t = function (key, dflt) { return typeof dflt === 'string' ? dflt : ''; };

const bindings = [];
sandbox.$ = function (sel) {
  const obj = {
    val: function () { return ''; },
    html: function (v) {
      if (v === undefined) { return sandbox.__htmlMap[sel] || ''; }
      sandbox.__htmlMap[sel] = v;
      return obj;
    },
    on: function (ev, s, fn) { bindings.push({ev: ev, sel: s, fn: fn}); return obj; },
    off: function () { return obj; },
    prop: function () { return false; },
    find: function () { return {css: function () { return {}; }, on: function () { return {}; }}; },
    css: function () { return obj; },
    scrollTop: 0
  };
  return obj;
};
sandbox.$.post = function (url, data, cb) {
  sandbox.__posts.push({url: url, data: data, cb: cb});
};
sandbox.layer = {
  msg: function () { return 0; },
  close: function () {},
  closeAll: function () {},
  confirm: function () { return 0; },
  alert: function () {},
  open: function (opts) { sandbox.__open = opts; return 1; }
};

vm.createContext(sandbox);
vm.runInContext(src, sandbox, {filename: 'crontab.js'});

const realGetLogs = sandbox.getLogs;

check('行内操作注册了事件委派', bindings.some(function (b) {
  return b.ev === 'click.cronRowAct' && b.sel === '.cron-row-act' && typeof b.fn === 'function';
}));
const delegated = (bindings.filter(function (b) { return b.sel === '.cron-row-act'; })[0] || {}).fn;

// ---- 2. 恶劣任务名：跑 getCronData，把 HTML 吐给 Python 解析 ----
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

const rendered = [];
for (const name of hostileNames) {
  const rdata = {
    status: true, msg: '', page: '', backup_hook: [],
    data: [{
      id: 42, name: name, type: '每天', cycle: '每天 1点30分 执行', save: '', backup_to: 'localhost',
      stype: 'toShell', attr: '', day_type: '0', last_run_time: '', sync_ok: true, status: '1'
    }]
  };
  sandbox.__htmlMap = {};
  sandbox.$.post = function (url, data, cb) { cb(rdata); };
  sandbox.getCronData(1);
  rendered.push({name: name, html: sandbox.__htmlMap['#cronbody'] || ''});
}

// ---- 3. 委派点击：Python 把解析出的 data-* 通过环境变量传进来 ----
//   （Python 侧用真实 HTML 解析器回读属性，再调本脚本的第二阶段）
let delegatedCalls = [];
let delegatedCases = [];
const attrsJson = process.env.CRON_ATTRS || '';
if (attrsJson) {
  const cases = JSON.parse(attrsJson);
  delegatedCases = cases;
  const spies = {
    startTask: function (id, nm, isOpen) { delegatedCalls.push({fn: 'startTask', args: [id, nm, isOpen]}); },
    editTaskInfo: function (id) { delegatedCalls.push({fn: 'editTaskInfo', args: [id]}); },
    getLogs: function (id, nm) { delegatedCalls.push({fn: 'getLogs', args: [id, nm]}); },
    planDel: function (id, nm) { delegatedCalls.push({fn: 'planDel', args: [id, nm]}); },
    setTaskStatus: function (id, st) { delegatedCalls.push({fn: 'setTaskStatus', args: [id, st]}); }
  };
  Object.keys(spies).forEach(function (k) { sandbox[k] = spies[k]; });
  for (const c of cases) {
    delegatedCalls = [];
    const fakeEl = {
      getAttribute: function (k) { return (k in c.attrs) ? c.attrs[k] : null; }
    };
    try {
      delegated.call(fakeEl, {preventDefault: function () {}});
      c.calls = JSON.parse(JSON.stringify(delegatedCalls));
      c.error = null;
    } catch (e) {
      c.calls = [];
      c.error = String(e && e.message || e);
    }
  }
}

// ---- 4. 日志弹窗：任务名不进内联 JS ----
const dialogProbes = [];
for (const name of hostileNames) {
  if (name.indexOf(NL) !== -1) { continue; }   // 换行在属性/文本里对比意义不大
  sandbox.getLogs = realGetLogs;
  sandbox.__open = null;
  let clickHandler = null;
  try {
    sandbox.getLogs('42', name);
  } catch (e) {
    dialogProbes.push({name: name, error: String(e && e.message || e), content: ''});
    continue;
  }
  const opts = sandbox.__open;
  const content = opts ? String(opts.content || '') : '';
  const probe = {name: name, content: content, error: null, bound: false};
  if (opts && typeof opts.success === 'function') {
    const fakeLayero = {
      find: function (sel) {
        return {
          css: function () { return {}; },
          find: function () { return {css: function () { return {}; }}; },
          on: function (ev, fn) {
            if (sel === '#cron_log_run' && ev === 'click') { clickHandler = fn; }
            return {};
          }
        };
      }
    };
    try {
      opts.success(fakeLayero, 1);
    } catch (e) {
      probe.error = String(e && e.message || e);
    }
  }
  probe.bound = typeof clickHandler === 'function';
  if (probe.bound) {
    const calls = [];
    sandbox.startTask = function (id, nm, isOpen) { calls.push([id, nm, isOpen]); };
    sandbox.$.post = function () {};
    try {
      clickHandler();
    } catch (e) {
      probe.error = String(e && e.message || e);
    }
    probe.calls = calls;
  }
  dialogProbes.push(probe);
}

// ---- 5. 空 id 不发请求 ----
sandbox.getLogs = realGetLogs;
sandbox.__open = null;
sandbox.__posts = [];
let emptyIdError = null;
try {
  sandbox.getLogs(undefined, 'x');
} catch (e) {
  emptyIdError = String(e && e.message || e);
}

const result = {
  ok: failures.length === 0,
  checks: checks,
  failures: failures,
  rendered: rendered,
  delegatedProbe: delegatedCases,
  dialogProbes: dialogProbes,
  emptyId: {open: sandbox.__open, posts: sandbox.__posts.length, error: emptyIdError}
};
console.log(JSON.stringify(result));
process.exit(failures.length === 0 ? 0 : 1);
